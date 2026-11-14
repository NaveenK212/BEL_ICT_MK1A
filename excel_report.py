"""
ICT Excel Report Generator
--------------------------
Creates an .xlsx report for one ICT run.

* Every component is listed with Nominal, Measured, Deviation % and limits.
* A component is highlighted RED (whole row) when its measured value is
      below  Lower Limit - 5 %   (= Lower x 0.95)   or
      above  Upper Limit + 5 %   (= Upper x 1.05)
* The 5 % margin lives in ONE cell (Summary!B8). Change it and the
  check + red highlighting update by themselves.

Input is the same `data` dict that ReportGenerator.generate() receives
(data["summary"], data["components"]).
"""
import os, re, datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.utils import get_column_letter
    XL_OK, XL_ERR = True, ""
except ImportError as _e:                      # pragma: no cover
    XL_OK, XL_ERR = False, str(_e)

DEFAULT_TOLERANCE = 0.05          # +/-5 %
TOL_CELL = "Summary!$B$8"

FONT = "Arial"
_SI = {"G": 1e9, "M": 1e6, "k": 1e3, "": 1.0,
       "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
_NUM_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([GMkmuµnpf]?)\s*$")


def _to_float(text):
    """'4.700k' -> 4700.0 ; 'NA' / '—' / '∞' -> None."""
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.match(str(text or ""))
    if not m:
        return None
    return float(m.group(1)) * _SI[m.group(2)]


class ExcelReportGenerator:

    def generate(self, data: dict, save_path: str = None,
                 tolerance: float = DEFAULT_TOLERANCE) -> str:
        if not XL_OK:
            raise RuntimeError(
                "Cannot create an Excel report: the 'openpyxl' library could "
                f"not be loaded ({XL_ERR}).\n\nInstall it in the same Python "
                "that runs this app:\n    pip install openpyxl\n"
                "then restart the app.")

        s = data["summary"]
        comps = data.get("components", [])

        if not save_path:
            safe = lambda t: re.sub(r'[\\/:*?"<>|]', "_", str(t))
            folder = data.get("run_folder") or os.getcwd()
            os.makedirs(folder, exist_ok=True)
            try:
                ts = datetime.datetime.fromisoformat(
                    s.get("timestamp", "")).strftime("%Y%m%d_%H%M%S")
            except Exception:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(
                folder, f"ICT_{safe(s['board_name'])}_{safe(s['serial'])}_{ts}.xlsx")

        wb = Workbook()
        ws_sum = wb.active
        ws_sum.title = "Summary"
        ws_cmp = wb.create_sheet("Components")

        n_rows = self._components_sheet(ws_cmp, comps)
        self._summary_sheet(ws_sum, s, n_rows, tolerance)

        wb.save(save_path)
        return save_path

    # ── COMPONENTS SHEET ──────────────────────────────────────────
    # Column order:  Nominal | Lower | Upper | Measured | Status | ...extras
    def _components_sheet(self, ws, comps):
        thin = Side(style="thin", color="BFBFBF")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        head_fill = PatternFill("solid", fgColor="0A1929")
        head_font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        base_font = Font(name=FONT, size=10)

        heads = ["#", "Component", "Type",
                 "Nominal", "Lower Limit", "Upper Limit", "Measured",
                 "Tester Status", "Limit Check",
                 "Deviation %", "Lower −5%", "Upper +5%", "Note"]
        for c, h in enumerate(heads, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font, cell.fill, cell.border = head_font, head_fill, border
            cell.alignment = Alignment(horizontal="center", vertical="center",
                                       wrap_text=True)
        ws.row_dimensions[1].height = 24

        eng = "##0.000E+0"     # engineering notation: 4.700E+3 = 4.7k
        for i, c in enumerate(comps, 1):
            r = i + 1
            nom = _to_float(c.get("nominal"))
            lo = _to_float(c.get("lower_limit"))
            hi = _to_float(c.get("upper_limit"))
            mea = _to_float(c.get("measured"))

            ws.cell(r, 1, i)                       # A  #
            ws.cell(r, 2, c.get("ref", ""))        # B  Component
            ws.cell(r, 3, c.get("type", ""))       # C  Type
            ws.cell(r, 4, nom)                     # D  Nominal
            ws.cell(r, 5, lo)                      # E  Lower Limit
            ws.cell(r, 6, hi)                      # F  Upper Limit
            ws.cell(r, 7, mea)                     # G  Measured
            ws.cell(r, 8, c.get("status", ""))     # H  Tester Status
            # I  Limit Check: below (Lower - margin) or above (Upper + margin)
            # K = Lower - margin, L = Upper + margin
            ws.cell(r, 9,
                    f'=IF(OR(NOT(ISNUMBER(G{r})),AND(K{r}="",L{r}="")),"N/A",'
                    f'IF(OR(AND(K{r}<>"",G{r}<K{r}),AND(L{r}<>"",G{r}>L{r})),'
                    f'"OUT OF RANGE","OK"))')
            # J  Deviation % from nominal (information only)
            ws.cell(r, 10, f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(G{r})),'
                           f'IF(D{r}<>0,(G{r}-D{r})/ABS(D{r}),""),"")')
            # K / L  thresholds with the margin applied
            ws.cell(r, 11, f'=IF(ISNUMBER(E{r}),E{r}-ABS(E{r})*{TOL_CELL},"")')
            ws.cell(r, 12, f'=IF(ISNUMBER(F{r}),F{r}+ABS(F{r})*{TOL_CELL},"")')
            ws.cell(r, 13, c.get("note", ""))      # M  Note

            for col in range(1, 14):
                cell = ws.cell(r, col)
                cell.font, cell.border = base_font, border
                cell.alignment = Alignment(vertical="center",
                                           horizontal="left" if col in (2, 3, 13) else "center",
                                           wrap_text=(col == 13))
            for col in (4, 5, 6, 7, 11, 12):
                ws.cell(r, col).number_format = eng
            ws.cell(r, 10).number_format = '+0.00%;-0.00%;0.00%'
            if str(c.get("status", "")).upper() == "FAIL":
                ws.cell(r, 8).font = Font(name=FONT, size=10, bold=True, color="C00000")

        last = len(comps) + 1
        widths = [6, 24, 16, 13, 13, 13, 13, 13, 16, 13, 13, 13, 60]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        if comps:
            # RED highlight: whole row where Limit Check = OUT OF RANGE
            red_fill = PatternFill("solid", bgColor="FFC7CE", fgColor="FFC7CE")
            red_font = Font(name=FONT, color="9C0006", bold=True)
            ws.conditional_formatting.add(
                f"A2:M{last}",
                FormulaRule(formula=['$I2="OUT OF RANGE"'],
                            fill=red_fill, font=red_font))
            ws.auto_filter.ref = f"A1:M{last}"
        ws.freeze_panes = "C2"
        return last

    # ── SUMMARY SHEET ─────────────────────────────────────────────
    def _summary_sheet(self, ws, s, last, tolerance):
        label = Font(name=FONT, bold=True, size=10, color="44546A")
        val = Font(name=FONT, size=10)
        title = Font(name=FONT, bold=True, size=16, color="0A1929")

        ws["A1"] = "ICT TEST REPORT"
        ws["A1"].font = title
        ws["A2"] = "Components below (Lower Limit − margin) or above (Upper Limit + margin) are highlighted RED on the Components sheet."
        ws["A2"].font = Font(name=FONT, italic=True, size=9, color="7F7F7F")

        rows = [
            (3, "Board Name", s.get("board_name", "")),
            (4, "Serial", s.get("serial", "")),
            (5, "Test Time", str(s.get("timestamp", ""))[:19].replace("T", " ")),
            (6, "Tester Result", s.get("status", "")),
        ]
        for r, k, v in rows:
            ws.cell(r, 1, k).font = label
            ws.cell(r, 2, v).font = val
        status_cell = ws["B6"]
        status_cell.font = Font(name=FONT, bold=True, size=11,
                                color="00B050" if s.get("status") == "PASS" else "C00000")

        # Input: tolerance
        ws["A8"] = "Margin beyond limits (±)"
        ws["A8"].font = label
        ws["B8"] = tolerance
        ws["B8"].number_format = "0.0%"
        ws["B8"].font = Font(name=FONT, size=11, bold=True, color="0000FF")   # input
        ws["B8"].fill = PatternFill("solid", fgColor="FFFF00")
        ws["C8"] = "← Input: change to re-check (default 5%)"
        ws["C8"].font = Font(name=FONT, italic=True, size=9, color="7F7F7F")

        rng = lambda col: f"Components!${col}$2:${col}${max(last, 2)}"
        stats = [
            (10, "Total test rows",              f"=COUNTA({rng('B')})"),
            (11, "Checked against limits ±margin",   f'=COUNTIF({rng("I")},"OK")+COUNTIF({rng("I")},"OUT OF RANGE")'),
            (12, "OUT OF RANGE (red)",           f'=COUNTIF({rng("I")},"OUT OF RANGE")'),
            (13, "Within tolerance",             f'=COUNTIF({rng("I")},"OK")'),
            (14, "Not checked (no measured value / limits, e.g. ICs, diodes)",
                                                 f'=COUNTIF({rng("I")},"N/A")'),
            (15, "Tester FAIL rows",             f'=COUNTIF({rng("H")},"FAIL")'),
        ]
        for r, k, f in stats:
            ws.cell(r, 1, k).font = label
            c = ws.cell(r, 2, f)
            c.font = val
            c.number_format = "0"
            c.alignment = Alignment(horizontal="left")
        ws["A12"].font = Font(name=FONT, bold=True, size=10, color="C00000")
        ws["B12"].font = Font(name=FONT, bold=True, size=11, color="C00000")

        notes = [
            "Notes",
            "• OUT OF RANGE when Measured < Lower Limit × (1 − margin)  or  Measured > Upper Limit × (1 + margin).",
            "• Example (5%): lower limit 85 nF → red below 80.75 nF; upper limit 115 nF → red above 120.75 nF.",
            "• Deviation % = (Measured − Nominal) / |Nominal| is shown for information only; it does not set the colour.",
            "• Values are shown in engineering notation (E+3 = k, E+6 = M, E−3 = m, E−6 = µ, E−9 = n, E−12 = p).",
            "• Rows with no numeric measured value / limits (ICs, diodes, relays, testjet) cannot be checked; "
            "their tester PASS/FAIL is shown in 'Tester Status'.",
            "• Use the filter on the Components sheet's 'Limit Check' column to list only OUT OF RANGE parts.",
        ]
        for i, t in enumerate(notes):
            c = ws.cell(17 + i, 1, t)
            c.font = Font(name=FONT, size=9, bold=(i == 0), color="595959")

        ws.column_dimensions["A"].width = 52
        ws.column_dimensions["B"].width = 26
        ws.column_dimensions["C"].width = 48
        ws.sheet_view.showGridLines = False
