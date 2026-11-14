"""
Trends tab — component-wise trend across runs.

Pick a board, pick a component (C121, R15, ...) and see how its MEASURED value
moved from run to run, against its nominal, lower / upper limit and the
limit +/- margin band (default 5 %, same rule as the Excel report):

      OUT  =  Measured < Lower x (1 - margin)   or   Measured > Upper x (1 + margin)

Components with no numeric reading (ICs, diodes, relays, testjet) show a
PASS / FAIL timeline instead.

The data / chart code is plain Python (no Tk) so it can be tested headless:
    parse_rows(), summarise(), draw_trend()
"""
import re
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from themes import get_theme
from config import Config

_T = get_theme(Config().get("theme", "dark_navy"))
BG, S1, S2, S3 = _T["bg"], _T["s1"], _T["s2"], _T["s3"]
BD, TXT, MUT, DIM = _T["bd"], _T["txt"], _T["mut"], _T["dim"]
PASS, FAIL, WARN, INFO = _T["pass"], _T["fail"], _T["warn"], _T["info"]
PALETTE = dict(bg=BG, s1=S1, s2=S2, s3=S3, bd=BD, txt=TXT, mut=MUT, dim=DIM,
               pas=PASS, fail=FAIL, warn=WARN, info=INFO)

DEFAULT_MARGIN = 0.05

# ── NUMBER HELPERS ────────────────────────────────────────────────
_SI = {"G": 1e9, "M": 1e6, "k": 1e3, "": 1.0, "m": 1e-3, "u": 1e-6,
       "µ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
_NUM_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([GMkmuµnpf]?)\s*$")


def to_float(text):
    """'4.700k' -> 4700.0 ;  'NA' / '—' / '∞' -> None."""
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.match(str(text or ""))
    return float(m.group(1)) * _SI[m.group(2)] if m else None


def eng(v, digits=4):
    """4700 -> '4.7k', 9.383e-8 -> '93.83n'."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if v == 0:
        return "0"
    a = abs(v)
    for lim, suf in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
                     (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"),
                     (1e-12, "p"), (1e-15, "f")):
        if a >= lim * 0.9995:
            return f"{v / lim:.{digits}g}{suf}"
    return f"{v:.3e}"


def is_out(meas, lo, hi, margin):
    """True when beyond Lower x (1-margin) or Upper x (1+margin)."""
    if meas is None:
        return False
    if lo is not None and meas < lo - abs(lo) * margin:
        return True
    if hi is not None and meas > hi + abs(hi) * margin:
        return True
    return False


def out_detail(meas, lo, hi, margin):
    """None if inside Lower x (1-margin) .. Upper x (1+margin), else which
    limit was crossed and by how much (fraction of that limit)."""
    if meas is None:
        return None
    if lo is not None and meas < lo - abs(lo) * margin:
        return {"side": "BELOW LOWER", "limit": lo,
                "beyond": abs(lo - meas) / abs(lo) if lo else None}
    if hi is not None and meas > hi + abs(hi) * margin:
        return {"side": "ABOVE UPPER", "limit": hi,
                "beyond": abs(meas - hi) / abs(hi) if hi else None}
    return None


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", str(s))]


# ── DATA ──────────────────────────────────────────────────────────
def parse_rows(raw_rows):
    """Group DB rows by component ref, add numeric fields. Rows must already
    be in test-time order. Returns {ref: [row, ...]}."""
    by = {}
    for r in raw_rows:
        d = dict(r)
        d["m"] = to_float(d.get("measured"))
        d["nom"] = to_float(d.get("nominal"))
        d["lo"] = to_float(d.get("lower_limit"))
        d["hi"] = to_float(d.get("upper_limit"))
        d["fail"] = str(d.get("status", "")).upper() == "FAIL"
        if d["m"] is not None and d["nom"]:
            d["dev"] = (d["m"] - d["nom"]) / abs(d["nom"])
        else:
            d["dev"] = None
        by.setdefault(d["ref"], []).append(d)
    return by


def summarise(rows, margin):
    """Per-component numbers for the list + the stats strip."""
    vals = [r["m"] for r in rows if r["m"] is not None]
    out, worst = 0, None
    for r in rows:
        d = out_detail(r["m"], r["lo"], r["hi"], margin)
        if d:
            out += 1
            k = d["beyond"] if d["beyond"] is not None else 1e9
            if worst is None or k > worst["_k"]:
                worst = dict(d, _k=k, m=r["m"], serial=r["serial"],
                             run_id=r["run_id"])
    s = {"runs": len(rows), "out": out, "worst": worst,
         "fail": sum(1 for r in rows if r["fail"]),
         "type": rows[-1].get("type", "") if rows else "",
         "numeric": bool(vals)}
    if vals:
        a = np.array(vals)
        s.update(mean=float(a.mean()), min=float(a.min()),
                 max=float(a.max()), std=float(a.std()))
    return s


def out_list(sums):
    """Components that went beyond Lower -margin / Upper +margin, worst first."""
    items = []
    for ref, sm in sums.items():
        w = sm.get("worst")
        if w:
            items.append(dict(ref=ref, side=w["side"], m=w["m"],
                              limit=w["limit"], beyond=w["beyond"],
                              serial=w["serial"], run_id=w["run_id"],
                              out=sm["out"], runs=sm["runs"]))
    items.sort(key=lambda d: (-(d["beyond"] if d["beyond"] is not None else 1e9),
                              natural_key(d["ref"])))
    return items


# ── CHART ─────────────────────────────────────────────────────────
def draw_trend(fig, ref, rows, margin, P=PALETTE):
    """Draw the trend of ONE component onto `fig` (clears it first)."""
    fig.clear()
    fig.patch.set_facecolor(P["s2"])
    ax = fig.add_subplot(111)
    ax.set_facecolor(P["s3"])
    for sp in ax.spines.values():
        sp.set_color(P["bd"])
    ax.tick_params(colors=P["mut"], labelsize=9)
    ax.grid(True, color=P["bd"], linestyle="--", alpha=0.4)

    n = len(rows)
    if n == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color=P["mut"], fontsize=13)
        return
    x = np.arange(n)
    nan = float("nan")
    col = lambda k: np.array([r[k] if r[k] is not None else nan for r in rows])
    meas, nom, lo, hi = col("m"), col("nom"), col("lo"), col("hi")
    typ = rows[-1].get("type", "")

    if np.isfinite(meas).any():
        # ── numeric trend ─────────────────────────────────────
        lo_m = lo - np.abs(lo) * margin          # lower - margin
        hi_m = hi + np.abs(hi) * margin          # upper + margin
        pct = f"{margin * 100:g}%"
        if np.isfinite(lo).any() and np.isfinite(hi).any():
            ax.fill_between(x, lo, hi, color=P["pas"], alpha=0.08,
                            label="Lower–Upper limit")
        if np.isfinite(lo).any():
            ax.plot(x, lo, color=P["warn"], lw=1.2, ls="--", label="Lower limit")
            ax.plot(x, lo_m, color=P["fail"], lw=1.2, ls=":",
                    label=f"Lower −{pct}")
        if np.isfinite(hi).any():
            ax.plot(x, hi, color=P["warn"], lw=1.2, ls="--", label="Upper limit")
            ax.plot(x, hi_m, color=P["fail"], lw=1.2, ls=":",
                    label=f"Upper +{pct}")
        if np.isfinite(nom).any():
            ax.plot(x, nom, color=P["pas"], lw=1.4, label="Nominal")

        ax.plot(x, meas, color=P["info"], lw=1.6, alpha=0.9, zorder=3)
        out = np.array([is_out(r["m"], r["lo"], r["hi"], margin) for r in rows])
        tfail = np.array([r["fail"] for r in rows]) & ~out
        ok = ~(out | tfail) & np.isfinite(meas)
        ax.scatter(x[ok], meas[ok], s=46, color=P["info"], zorder=4,
                   label="Measured")
        if tfail.any():
            ax.scatter(x[tfail], meas[tfail], s=70, color=P["warn"], zorder=5,
                       edgecolor=P["txt"], linewidth=0.8, label="Tester FAIL")
        if out.any():
            ax.scatter(x[out], meas[out], s=90, color=P["fail"], zorder=6,
                       edgecolor=P["txt"], linewidth=1.0,
                       label=f"OUT (beyond limit ±{pct})")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: eng(v, 3)))
        ax.set_ylabel("Measured", color=P["mut"], fontsize=10)
        title = f"{ref}  ·  {typ}  ·  {n} run(s)"
    else:
        # ── no readings (IC, diode, relay, testjet): PASS/FAIL timeline ──
        y = np.array([0 if r["fail"] else 1 for r in rows])
        ax.plot(x, y, color=P["dim"], lw=1.2, drawstyle="steps-mid")
        ax.scatter(x[y == 1], y[y == 1], s=60, color=P["pas"], zorder=4,
                   label="PASS")
        if (y == 0).any():
            ax.scatter(x[y == 0], y[y == 0], s=90, color=P["fail"], zorder=5,
                       edgecolor=P["txt"], linewidth=1.0, label="FAIL")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["FAIL", "PASS"])
        ax.set_ylim(-0.4, 1.4)
        title = f"{ref}  ·  {typ}  ·  {n} run(s)  ·  PASS / FAIL only (no readings)"

    # x axis: serial + run id
    step = max(1, int(np.ceil(n / 14)))
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{rows[i]['serial']}\n#{rows[i]['run_id']}"
                        for i in ticks], fontsize=8)
    ax.set_xlim(-0.4, max(n - 1, 0) + 0.4)
    ax.set_title(title, color=P["txt"], fontsize=12, pad=10, loc="left")
    leg = ax.legend(fontsize=8, framealpha=0, ncol=4, loc="upper center",
                    bbox_to_anchor=(0.5, -0.17))
    for t in leg.get_texts():
        t.set_color(P["mut"])
    try:
        fig.tight_layout(pad=1.0)
    except Exception:
        pass


# ── PAGE ──────────────────────────────────────────────────────────
class TrendsPage(ctk.CTkFrame):
    """Component-wise trend tab. Needs db.get_board_names() and
    db.get_board_component_rows(board)."""

    def __init__(self, parent, db, on_view_report=None, **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        self.db = db
        self._on_view = on_view_report
        self._by_ref = {}            # {ref: [rows]}
        self._sum = {}               # {ref: summary}
        self._ref = None
        self._build()

    # ── layout ────────────────────────────────────────────────
    def _build(self):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        bar = ctk.CTkFrame(self, fg_color=S2, corner_radius=0,
                           border_width=1, border_color=BD, height=56)
        bar.pack(fill="x"); bar.pack_propagate(False)
        lab = lambda t: ctk.CTkLabel(bar, text=t, font=("Segoe UI", 10, "bold"),
                                     text_color=INFO)
        lab("  BOARD").pack(side="left", padx=(14, 6))
        self._board_var = tk.StringVar(value="")
        self._board_menu = ctk.CTkOptionMenu(
            bar, variable=self._board_var, values=["—"], width=250, height=32,
            font=("Segoe UI", 11), dropdown_font=("Segoe UI", 11),
            fg_color=S3, button_color=BD, button_hover_color=INFO,
            dropdown_fg_color=S2, dropdown_hover_color=BD,
            dropdown_text_color=TXT, text_color=TXT,
            command=lambda _v: self._load_board())
        self._board_menu.pack(side="left", padx=4)

        lab("FIND").pack(side="left", padx=(16, 6))
        self._q = tk.StringVar()
        self._q.trace_add("write", lambda *_: self._sync())
        ctk.CTkEntry(bar, textvariable=self._q, width=170, height=32,
                     font=("Courier New", 12), fg_color=S3, text_color=TXT,
                     border_color=BD, placeholder_text="C121, R15 ..."
                     ).pack(side="left", padx=4)

        lab("MARGIN %").pack(side="left", padx=(16, 6))
        self._margin_var = tk.StringVar(value=f"{DEFAULT_MARGIN * 100:g}")
        me = ctk.CTkEntry(bar, textvariable=self._margin_var, width=54,
                          height=32, font=("Courier New", 12), fg_color=S3,
                          text_color=TXT, border_color=BD, justify="center")
        me.pack(side="left", padx=4)
        me.bind("<Return>", lambda _e: self._margin_changed())
        me.bind("<FocusOut>", lambda _e: self._margin_changed())

        self._only_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Only flagged", variable=self._only_var,
                        command=self._sync, font=("Segoe UI", 11),
                        text_color=TXT, fg_color=INFO, hover_color=INFO,
                        border_color=BD, width=20).pack(side="left", padx=(16, 4))

        ctk.CTkButton(bar, text="⟳  Refresh", width=90, height=32,
                      fg_color=S3, hover_color=S1, border_color=BD,
                      border_width=1, font=("Segoe UI", 10), text_color=MUT,
                      command=self.refresh).pack(side="left", padx=8)
        self._count = ctk.CTkLabel(bar, text="", font=("Segoe UI", 9),
                                   text_color=MUT)
        self._count.pack(side="right", padx=14)

        # body: component list (left) | chart + table (right)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=BG, width=490)
        left.pack(side="left", fill="y", padx=(12, 6), pady=8)
        left.pack_propagate(False)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=8)

        s = ttk.Style()
        s.configure("Trend.Treeview", background=S3, fieldbackground=S3,
                    foreground=TXT, rowheight=28, font=("Segoe UI", 11))
        s.configure("Trend.Treeview.Heading", background=S2, foreground=INFO,
                    font=("Segoe UI", 10, "bold"), relief="flat", padding=(6, 6))
        s.map("Trend.Treeview", background=[("selected", S1)])
        s.layout("Trend.Treeview", [("Trend.Treeview.treearea", {"sticky": "nswe"})])

        # view switch: all components | out of range
        self._view_var = tk.StringVar(value="Out of range")
        self._seg = ctk.CTkSegmentedButton(
            left, values=["All components", "Out of range"],
            variable=self._view_var, command=lambda _v: self._switch_view(),
            font=("Segoe UI", 11, "bold"), fg_color=S3,
            selected_color=INFO, selected_hover_color=INFO,
            unselected_color=S3, unselected_hover_color=BD, text_color=TXT)
        self._seg.pack(fill="x", pady=(0, 6))
        self._list_box = tk.Frame(left, bg=BG)
        self._out_box = tk.Frame(left, bg=BG)
        self._out_hdr = ctk.CTkLabel(self._out_box, text="", anchor="w",
                                     justify="left", wraplength=470,
                                     font=("Segoe UI", 10), text_color=WARN)
        self._out_hdr.pack(fill="x", pady=(0, 4))

        # component list
        sb = ttk.Scrollbar(self._list_box, orient="vertical")
        cols = ("Ref", "Type", "Runs", "Out", "Fail")
        self._lv = ttk.Treeview(self._list_box, columns=cols, show="headings",
                                style="Trend.Treeview", yscrollcommand=sb.set,
                                selectmode="browse")
        sb.config(command=self._lv.yview)
        sb.pack(side="right", fill="y"); self._lv.pack(fill="both", expand=True)
        for c, w, a in zip(cols, (110, 90, 45, 40, 40),
                           ("w", "w", "center", "center", "center")):
            self._lv.heading(c, text=c, anchor=a)
            self._lv.column(c, width=w, anchor=a, minwidth=36,
                            stretch=(c == "Ref"))
        self._lv.tag_configure("out", foreground=FAIL)
        self._lv.tag_configure("fail", foreground=WARN)
        self._lv.tag_configure("ok", foreground=TXT)
        self._lv.bind("<<TreeviewSelect>>", self._on_select)

        # out-of-range table (beyond Lower -margin / Upper +margin)
        osb = ttk.Scrollbar(self._out_box, orient="vertical")
        ocols = ("Component", "Side", "Worst", "Limit", "Beyond", "Out runs")
        self._ov = ttk.Treeview(self._out_box, columns=ocols, show="headings",
                                style="Trend.Treeview", yscrollcommand=osb.set,
                                selectmode="browse")
        osb.config(command=self._ov.yview)
        osb.pack(side="right", fill="y"); self._ov.pack(fill="both", expand=True)
        for c, w, a in zip(ocols, (95, 110, 75, 75, 60, 60),
                           ("w", "w", "center", "center", "center", "center")):
            self._ov.heading(c, text=c, anchor=a)
            self._ov.column(c, width=w, anchor=a, minwidth=40,
                            stretch=(c == "Component"))
        self._ov.tag_configure("out", foreground=FAIL)
        self._ov.bind("<<TreeviewSelect>>", self._on_select_out)

        # stats strip
        self._stats = ctk.CTkLabel(right, text="", anchor="w", justify="left",
                                   font=("Courier New", 11), text_color=MUT)
        self._stats.pack(fill="x", pady=(0, 4))

        # chart
        chart_box = tk.Frame(right, bg=S2)
        chart_box.pack(fill="both", expand=True)
        self._fig = Figure(figsize=(8, 4), dpi=100)
        self._canvas = FigureCanvasTkAgg(self._fig, master=chart_box)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

        # run table
        tbox = tk.Frame(right, bg=BG, height=210)
        tbox.pack(fill="x", pady=(8, 0)); tbox.pack_propagate(False)
        sby = ttk.Scrollbar(tbox, orient="vertical")
        tcols = ("Run", "Serial", "Test Date", "Test Time", "Nominal",
                 "Lower Limit", "Upper Limit", "Measured", "Dev %",
                 "Status", "Check", "Beyond Limit")
        self._tv = ttk.Treeview(tbox, columns=tcols, show="headings",
                                style="Trend.Treeview", yscrollcommand=sby.set)
        sby.config(command=self._tv.yview)
        sby.pack(side="right", fill="y"); self._tv.pack(fill="both", expand=True)
        for c, w in zip(tcols, (45, 80, 90, 75, 80, 80, 80, 80, 65, 60, 105, 85)):
            self._tv.heading(c, text=c, anchor="center")
            self._tv.column(c, width=w, anchor="center", minwidth=40,
                            stretch=True)
        self._tv.tag_configure("pass", foreground=PASS)
        self._tv.tag_configure("fail", foreground=WARN)
        self._tv.tag_configure("out", foreground=FAIL)
        self._tv.bind("<Double-1>", self._on_row_dbl)

        ctk.CTkLabel(self, text="Click a component to see its trend  ·  "
                     "double-click a run row to open that report",
                     font=("Segoe UI", 9), text_color=DIM).pack(pady=(0, 6))
        self._switch_view()

    # ── data ──────────────────────────────────────────────────
    def refresh(self):
        """Called whenever the tab is shown / new data arrives."""
        try:
            boards = self.db.get_board_names()
        except Exception:
            boards = []
        self._board_menu.configure(values=boards or ["—"])
        if self._board_var.get() not in boards:
            self._board_var.set(boards[0] if boards else "—")
        self._load_board()

    def _margin(self):
        try:
            v = float(self._margin_var.get().replace("%", "").strip())
            return min(max(v, 0.0), 100.0) / 100.0
        except ValueError:
            return DEFAULT_MARGIN

    def _margin_changed(self):
        self._resummarise()
        self._sync()

    def _load_board(self):
        board = self._board_var.get()
        try:
            raw = self.db.get_board_component_rows(board) if board != "—" else []
        except Exception:
            raw = []
        self._by_ref = parse_rows(raw)
        self._resummarise()
        self._sync()

    def _resummarise(self):
        m = self._margin()
        self._sum = {ref: summarise(rows, m) for ref, rows in self._by_ref.items()}

    def _sync(self):
        """Rebuild both lists, then select / draw the active one."""
        self._fill_list()
        self._fill_out()
        self._select_active()

    def _active_tree(self):
        return self._ov if self._view_var.get() == "Out of range" else self._lv

    def _switch_view(self):
        self._list_box.pack_forget()
        self._out_box.pack_forget()
        (self._out_box if self._view_var.get() == "Out of range"
         else self._list_box).pack(fill="both", expand=True)
        self._select_active()

    def _select_active(self):
        tree = self._active_tree()
        kids = tree.get_children()
        if kids:
            target = self._ref if self._ref in kids else kids[0]
            tree.selection_set(target)
            tree.see(target)
            self._show(target)
        else:
            self._show(None)

    def _fill_list(self):
        q = self._q.get().strip().lower()
        only = self._only_var.get()
        for i in self._lv.get_children():
            self._lv.delete(i)
        shown = flagged = 0
        for ref in sorted(self._by_ref, key=natural_key):
            sm = self._sum[ref]
            is_flag = sm["out"] > 0 or sm["fail"] > 0
            flagged += is_flag
            if q and q not in ref.lower() and q not in sm["type"].lower():
                continue
            if only and not is_flag:
                continue
            tag = "out" if sm["out"] else "fail" if sm["fail"] else "ok"
            self._lv.insert("", "end", iid=ref, tags=(tag,), values=(
                ref, sm["type"], sm["runs"],
                sm["out"] or "", sm["fail"] or ""))
            shown += 1
        n_out = sum(1 for sm in self._sum.values() if sm["out"])
        self._count.configure(
            text=f"{shown} of {len(self._by_ref)} components  ·  "
                 f"{flagged} flagged  ·  {n_out} beyond ±{self._margin() * 100:g}%")

    def _fill_out(self):
        """Components that went beyond Lower -margin / Upper +margin."""
        q = self._q.get().strip().lower()
        for i in self._ov.get_children():
            self._ov.delete(i)
        items = out_list(self._sum)
        pct = f"{self._margin() * 100:g}%"
        if items:
            self._out_hdr.configure(
                text=f"{len(items)} component(s) went beyond Lower −{pct} / "
                     f"Upper +{pct}.  Worst first — click one to see its trend.",
                text_color=FAIL)
        else:
            self._out_hdr.configure(
                text=f"No component went beyond Lower −{pct} / Upper +{pct} "
                     f"on this board.", text_color=PASS)
        for it in items:
            if q and q not in it["ref"].lower():
                continue
            beyond = (f"{it['beyond'] * 100:.1f}%"
                      if it["beyond"] is not None else "—")
            self._ov.insert("", "end", iid=it["ref"], tags=("out",), values=(
                it["ref"], it["side"], eng(it["m"]), eng(it["limit"]),
                beyond, f"{it['out']}/{it['runs']}"))

    # ── selection / drawing ───────────────────────────────────
    def _on_select(self, _e=None):
        sel = self._lv.selection()
        if sel and self._active_tree() is self._lv:
            self._show(sel[0])

    def _on_select_out(self, _e=None):
        sel = self._ov.selection()
        if sel and self._active_tree() is self._ov:
            self._show(sel[0])

    def _show(self, ref):
        self._ref = ref
        for i in self._tv.get_children():
            self._tv.delete(i)
        if not ref or ref not in self._by_ref:
            self._stats.configure(text="No components for this board yet.")
            draw_trend(self._fig, "", [], self._margin())
            self._canvas.draw_idle()
            return
        rows, m = self._by_ref[ref], self._margin()
        sm = self._sum[ref]
        if sm["numeric"]:
            txt = (f"{ref}   runs {sm['runs']}   mean {eng(sm['mean'])}   "
                   f"min {eng(sm['min'])}   max {eng(sm['max'])}   "
                   f"std {eng(sm['std'])}   OUT {sm['out']}   "
                   f"tester FAIL {sm['fail']}")
        else:
            txt = (f"{ref}   runs {sm['runs']}   PASS/FAIL only (no readings)   "
                   f"tester FAIL {sm['fail']}")
        w = sm.get("worst")
        if w:
            b = (f"{w['beyond'] * 100:.1f}% beyond"
                 if w["beyond"] is not None else "beyond")
            txt += (f"\n⚠ OUT in {sm['out']} of {sm['runs']} run(s) — worst: "
                    f"{w['side']} limit  {eng(w['m'])} vs {eng(w['limit'])} "
                    f"({b}) in {w['serial']} #{w['run_id']}")
        self._stats.configure(text=txt, text_color=FAIL if w else MUT)

        def mask(v):
            v = "" if v is None else str(v).strip()
            return "" if v.upper() == "NA" else (v or "—")

        for r in rows:
            d = out_detail(r["m"], r["lo"], r["hi"], m)
            out = d is not None
            ts = str(r.get("timestamp") or "")
            chk = (d["side"] if out else "ok") if r["m"] is not None else ""
            bey = (f"{d['beyond'] * 100:.1f}%"
                   if out and d["beyond"] is not None else "")
            dev = f"{r['dev'] * 100:+.2f}%" if r["dev"] is not None else ""
            self._tv.insert("", "end", iid=f"{r['run_id']}", tags=(
                "out" if out else "fail" if r["fail"] else "pass",),
                values=(r["run_id"], r["serial"], ts[:10], ts[11:19],
                        mask(r.get("nominal")), mask(r.get("lower_limit")),
                        mask(r.get("upper_limit")), mask(r.get("measured")),
                        dev, r.get("status", ""), chk, bey))
        draw_trend(self._fig, ref, rows, m)
        self._canvas.draw_idle()

    def _on_row_dbl(self, _e):
        sel = self._tv.selection()
        if sel and self._on_view:
            try:
                self._on_view(int(sel[0]))
            except ValueError:
                pass
