"""
ICT PDF Report Generator v6.0
8 charts with summaries, no component tables. One-click export.
"""
import os, io, datetime
import numpy as np

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, KeepTogether, PageBreak
    )
    RL_OK = True
    RL_ERR = ""
except ImportError as _e:
    RL_OK = False
    RL_ERR = str(_e)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MPL_OK = True
    MPL_ERR = ""
except ImportError as _e:
    MPL_OK = False
    MPL_ERR = str(_e)

import sys as _sys

if getattr(_sys, 'frozen', False):
    _APP_ROOT = os.path.dirname(_sys.executable)
else:
    _APP_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_ROOT = os.path.join(_APP_ROOT, "ICT_Reports")

# Load theme from config
from themes import get_theme
from config import Config as _Cfg
_theme = get_theme(_Cfg().get("theme", "dark_navy"))

HX = {
    "bg": _theme["bg"], "s1": _theme["s1"], "s2": _theme["s2"], "s3": _theme["s3"],
    "bd": _theme["bd"], "txt": _theme["txt"], "muted": _theme["mut"], "dim": _theme["dim"],
    "pass": _theme["pass"], "fail": _theme["fail"], "warn": _theme["warn"], "info": _theme["info"],
    "fbg": _theme["fbg"], "pbg": _theme["pbg"], "wbg": _theme["wbg"],
}
def C(k): return colors.HexColor(HX[k])

CHART_RC = {
    "figure.facecolor": HX["s2"], "axes.facecolor": HX["s3"],
    "axes.edgecolor": HX["bd"], "axes.labelcolor": HX["muted"],
    "xtick.color": HX["muted"], "ytick.color": HX["muted"],
    "text.color": HX["txt"], "grid.color": HX["bd"],
    "grid.linestyle": "--", "grid.alpha": 0.4, "font.size": 10,
}


class ReportGenerator:

    def _fig(self, w=9.5, h=3.8):
        plt.rcParams.update(CHART_RC)
        fig, ax = plt.subplots(figsize=(w, h))
        fig.patch.set_facecolor(HX["s2"])
        ax.set_facecolor(HX["s3"])
        return fig, ax

    def _fig_nax(self, w=9.5, h=3.8):
        plt.rcParams.update(CHART_RC)
        fig = plt.figure(figsize=(w, h))
        fig.patch.set_facecolor(HX["s2"])
        return fig

    def _full_img(self, fig, pct=92):
        buf = io.BytesIO()
        fig.tight_layout(pad=1.2)
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        pw = A4[0] * pct / 100
        from PIL import Image as PILImage
        img = PILImage.open(buf)
        aspect = img.height / img.width
        return Image(buf, width=pw, height=pw * aspect)

    def generate(self, data: dict, save_path: str = None) -> str:
        # Never silently write a .txt and call it a PDF: fail loudly instead.
        if not RL_OK:
            raise RuntimeError(
                "Cannot create a PDF: the 'reportlab' library could not be "
                f"loaded ({RL_ERR}).\n\nInstall it in the same Python that runs "
                "this app:\n    pip install reportlab\nthen restart the app.")
        if not MPL_OK:
            raise RuntimeError(
                "Cannot create a PDF: the 'matplotlib' library could not be "
                f"loaded ({MPL_ERR}).\n\nInstall it in the same Python that runs "
                "this app:\n    pip install matplotlib\nthen restart the app.")
        return self._pdf(data, save_path)

    def _pdf(self, data: dict, save_path: str = None) -> str:
        s = data["summary"]
        name = s["board_name"].replace("/", "-").replace("\\", "-")
        sn = s["serial"].replace("/", "-")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_path:
            path = save_path
        else:
            folder = os.path.join(OUTPUT_ROOT, name)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{sn}_{ts}.pdf")

        ST = {
            "title": ParagraphStyle("title", fontSize=22, fontName="Helvetica-Bold",
                                     textColor=C("info"), alignment=TA_CENTER,
                                     leading=28, spaceAfter=10),
            "subtitle": ParagraphStyle("sub", fontSize=11, fontName="Courier",
                                        textColor=C("muted"), alignment=TA_CENTER,
                                        leading=16, spaceAfter=12),
            "section": ParagraphStyle("sec", fontSize=14, fontName="Helvetica-Bold",
                                       textColor=C("info"), spaceBefore=10, spaceAfter=4),
            "body": ParagraphStyle("body", fontSize=10, fontName="Helvetica",
                                    textColor=C("txt"), leading=14, spaceAfter=6),
            "sbox": ParagraphStyle("sbox", fontSize=9, fontName="Helvetica",
                                    textColor=C("muted"), leading=12,
                                    spaceBefore=2, spaceAfter=8),
            "warn": ParagraphStyle("warn", fontSize=10, fontName="Helvetica-Bold",
                                    textColor=C("fail"), spaceBefore=2, spaceAfter=2),
        }

        story = []

        # Cover
        story.append(Spacer(1, 20 * mm))
        story.append(Paragraph("ICT TEST REPORT", ST["title"]))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"{s['board_name']}  &middot;  {s['serial']}  &middot;  "
            f"{s.get('timestamp', '')[:10]}", ST["subtitle"]))
        story.append(Spacer(1, 8 * mm))

        # Summary table
        rt = s["pass_rate"]
        sc = C("pass") if s["status"] == "PASS" else C("fail")
        rc = C("pass") if rt >= 98 else C("warn") if rt >= 90 else C("fail")
        def kp(t):
            return Paragraph(t, ParagraphStyle("k", fontSize=10,
                             fontName="Helvetica-Bold", textColor=C("muted")))
        def vp(t, bold=False, color=None):
            return Paragraph(t, ParagraphStyle("v", fontSize=11,
                             fontName="Courier-Bold" if bold else "Courier",
                             textColor=color or C("txt")))
        rows = [
            [kp("Board Name"), vp(s["board_name"], True),
             kp("Serial"), vp(s["serial"], True)],
            [kp("Status"), vp(s["status"], True, sc),
             kp("Pass Rate"), vp(f"{rt:.1f}%", True, rc)],
            [kp("Total Tested"), vp(str(s["total"])),
             kp("Timestamp"), vp(s.get("timestamp", "")[:19])],
            [kp("Passed"), vp(str(s["passed"]), True, C("pass")),
             kp("Failed"), vp(str(s["failed"]), True,
                              C("fail") if s["failed"] > 0 else C("pass"))],
        ]
        t = Table(rows, colWidths=["22%", "28%", "22%", "28%"])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C("s2")),
            ("BACKGROUND", (0, 0), (0, -1), C("s1")),
            ("BACKGROUND", (2, 0), (2, -1), C("s1")),
            ("GRID", (0, 0), (-1, -1), 0.5, C("bd")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(Spacer(1, 5 * mm))

        # General summary
        if s["status"] == "PASS":
            gen = (f"Board {s['board_name']} (Serial: {s['serial']}) passed ICT with a "
                   f"{rt:.1f}% pass rate. All {s['total']} tested within tolerance. No rework required.")
        else:
            fp = round(s["failed"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            gen = (f"Board {s['board_name']} (Serial: {s['serial']}) failed ICT with a "
                   f"{rt:.1f}% pass rate. {s['failed']} out of {s['total']} ({fp}%) "
                   f"exceeded tolerance limits. Rework required before retest.")
        story.append(Paragraph("SUMMARY", ST["section"]))
        story.append(Paragraph(gen, ST["body"]))
        for ins in data.get("insights", []):
            story.append(Paragraph(f"&#9632; {ins}", ST["warn"]))
        story.append(Spacer(1, 5 * mm))
        story.append(HRFlowable(width="100%", thickness=1, color=C("bd"), spaceAfter=8))

        # 8 Charts
        charts = self._build_charts(data)
        for title, img, summary_text in charts:
            story.append(KeepTogether([
                Paragraph(title, ST["section"]),
                img,
                Paragraph(summary_text, ST["sbox"]),
                Spacer(1, 3 * mm),
            ]))

        doc = SimpleDocTemplate(
            path, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm,
            topMargin=12*mm, bottomMargin=12*mm,
            title=f"ICT Report - {s['board_name']}",
            author="ICT Report Analyzer")

        def _page_bg(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(C("bg"))
            canvas.rect(0, 0, A4[0], A4[1], fill=True, stroke=False)
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(C("dim"))
            canvas.drawString(15*mm, 6*mm,
                f"ICT Report | {s['board_name']} | {s['serial']} | "
                f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            canvas.drawRightString(A4[0] - 15*mm, 6*mm, f"Page {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=_page_bg, onLaterPages=_page_bg)
        return path

    def _build_charts(self, data):
        s = data["summary"]
        return [
            self._chart_donut(data),
            self._chart_gauge(data),
            self._chart_pareto(data),
            self._chart_test_types(data),
            self._chart_pass_rate_by_type(data),
            self._chart_deviation(data),
            self._chart_failure_categories(data),
            self._chart_metrics_overview(data),
        ]

    def _chart_donut(self, data):
        s = data["summary"]
        fig = self._fig_nax(9.5, 4)
        ax = fig.add_subplot(111)
        p, f = s["passed"], s["failed"]
        rt = s["pass_rate"]
        rc = HX["pass"] if rt >= 98 else HX["warn"] if rt >= 90 else HX["fail"]
        sizes = [p, f] if f > 0 else [p]
        clrs = [HX["pass"], HX["fail"]] if f > 0 else [HX["pass"]]
        ax.pie(sizes, colors=clrs, startangle=90,
               wedgeprops=dict(width=0.5, edgecolor=HX["bg"], linewidth=3))
        ax.text(0, 0.1, f"{rt:.1f}%", ha="center", va="center",
                fontsize=28, fontweight="bold", color=rc, fontfamily="monospace")
        ax.text(0, -0.15, f"{p} Pass / {f} Fail", ha="center",
                va="center", fontsize=11, color=HX["muted"])
        ax.set_title("Pass / Fail Overview", fontsize=13, color=HX["txt"], pad=10)
        ax.axis("equal")
        summary = (f"Out of {s['total']} tested, {p} passed and {f} failed, "
                   f"yielding a {rt:.1f}% pass rate. "
                   f"{'Board meets acceptance criteria.' if rt >= 98 else 'Pass rate below 98% threshold.'}")
        return ("Pass / Fail Overview", self._full_img(fig, 85), summary)

    def _chart_gauge(self, data):
        s = data["summary"]
        fig = self._fig_nax(9.5, 4)
        ax = fig.add_subplot(111, aspect="equal")
        ax.set_xlim(-1.3, 1.3); ax.set_ylim(-0.2, 1.3); ax.axis("off")
        rt = s["pass_rate"]
        rc = HX["pass"] if rt >= 98 else HX["warn"] if rt >= 90 else HX["fail"]
        for t1, t2, c in [(np.pi, np.pi*0.67, HX["fail"]),
                           (np.pi*0.67, np.pi*0.33, HX["warn"]),
                           (np.pi*0.33, 0, HX["pass"])]:
            th = np.linspace(t1, t2, 80)
            ax.plot(np.cos(th)*0.85, np.sin(th)*0.85, color=c,
                    linewidth=16, alpha=0.85, solid_capstyle="butt")
        angle = np.pi * (1 - rt / 100)
        ax.annotate("", xy=(np.cos(angle)*0.7, np.sin(angle)*0.7),
                    xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color=HX["txt"],
                                    lw=2.5, mutation_scale=16))
        ax.plot(0, 0, "o", color=HX["txt"], markersize=9, zorder=5)
        ax.text(0, 0.28, f"{rt:.1f}%", ha="center", va="center",
                fontsize=26, fontweight="bold", color=rc, fontfamily="monospace")
        ax.text(0, 0.08, "Pass Rate", ha="center", va="center",
                fontsize=11, color=HX["muted"])
        ax.set_title("Pass Rate Gauge", fontsize=13, color=HX["txt"], pad=10)
        zone = "green (>=98%)" if rt >= 98 else "amber (90-98%)" if rt >= 90 else "red (<90%)"
        summary = (f"Pass rate gauge reads {rt:.1f}%, placing this board in the {zone} zone. "
                   f"The 98% threshold is the standard acceptance limit.")
        return ("Pass Rate Gauge", self._full_img(fig, 85), summary)

    def _chart_pareto(self, data):
        fig, ax1 = self._fig(9.5, 3.8)
        failures = data.get("top_failures", [])
        if not failures:
            ax1.text(0.5, 0.5, "No failures recorded", ha="center",
                     va="center", transform=ax1.transAxes, color=HX["pass"], fontsize=14)
            summary = "No failures detected. All tested within specified tolerances."
        else:
            names = [f["component"] for f in failures]
            counts = [f["count"] for f in failures]
            xs = np.arange(len(names))
            cum = np.cumsum(counts) / sum(counts) * 100
            bars = ax1.bar(xs, counts, color=HX["fail"], alpha=0.82, width=0.55)
            ax1.bar_label(bars, padding=4, fontsize=10, color=HX["muted"])
            ax2 = ax1.twinx()
            ax2.plot(xs, cum, color=HX["warn"], marker="o", linewidth=2,
                     markersize=7, linestyle="--")
            ax2.axhline(80, color=HX["info"], linewidth=1, linestyle=":", alpha=0.8)
            ax2.set_ylim(0, 115)
            ax2.set_ylabel("Cumulative %", fontsize=10, color=HX["warn"])
            ax2.tick_params(colors=HX["warn"], labelsize=10)
            ax1.set_xticks(xs)
            ax1.set_xticklabels(names, fontsize=11, rotation=15, ha="right")
            ax1.set_ylabel("Failure Count", fontsize=10)
            ax1.grid(axis="y", alpha=0.3)
            summary = (f"{len(failures)} unique refs failed. {names[0]} is most frequent "
                       f"({cum[0]:.0f}% of all failures). Focus rework on top items to resolve majority of issues.")
        ax1.set_title("Pareto - Top Failing Components", fontsize=13, color=HX["txt"], pad=10)
        return ("Pareto - Top Failing", self._full_img(fig, 88), summary)

    def _chart_test_types(self, data):
        fig, ax = self._fig(9.5, 3.8)
        tests = data.get("test_types", {})
        if tests:
            labels = list(tests.keys())
            passed = [tests[k]["pass"] for k in labels]
            failed = [tests[k]["fail"] for k in labels]
            x = np.arange(len(labels)); w = 0.35
            ax.bar(x - w/2, passed, w, color=HX["pass"], alpha=0.85, label="Pass")
            ax.bar(x + w/2, failed, w, color=HX["fail"], alpha=0.85, label="Fail")
            ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=11)
            ax.legend(fontsize=10, framealpha=0); ax.grid(axis="y", alpha=0.3)
            worst = max(tests, key=lambda k: tests[k]["fail"])
            summary = (f"{len(tests)} test types. {worst} tests had highest failure count "
                       f"({tests[worst]['fail']}). Helps identify which categories need process improvement.")
        else:
            ax.text(0.5, 0.5, "No test type data", ha="center", va="center",
                     transform=ax.transAxes, color=HX["muted"], fontsize=12)
            summary = "No test type categorization data available."
        ax.set_title("Test Type Breakdown", fontsize=13, color=HX["txt"], pad=10)
        return ("Test Type Breakdown", self._full_img(fig, 88), summary)

    def _chart_pass_rate_by_type(self, data):
        fig, ax = self._fig(9.5, 3.8)
        types = data.get("component_types", {})
        if types:
            labels = list(types.keys())
            pass_pct = []
            for k in labels:
                total = types[k]["pass"] + types[k]["fail"]
                pass_pct.append(types[k]["pass"] / total * 100 if total > 0 else 0)
            fail_pct = [100 - p for p in pass_pct]
            x = np.arange(len(labels))
            ax.bar(x, pass_pct, color=HX["pass"], alpha=0.85, width=0.5, label="Pass %")
            ax.bar(x, fail_pct, bottom=pass_pct, color=HX["fail"], alpha=0.85, width=0.5, label="Fail %")
            ax.axhline(98, color=HX["warn"], linewidth=1.5, linestyle="--", alpha=0.8, label="98% target")
            for i, p in enumerate(pass_pct):
                ax.text(i, p/2, f"{p:.0f}%", ha="center", va="center",
                        fontsize=10, color="white", fontweight="bold")
            ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=11)
            ax.set_ylim(0, 115); ax.legend(fontsize=10, framealpha=0); ax.grid(axis="y", alpha=0.3)
            below = [l for l, p in zip(labels, pass_pct) if p < 98]
            if below:
                summary = f"{', '.join(below)} fell below 98% threshold. Prioritize for root cause analysis."
            else:
                summary = "All types achieved pass rates at or above the 98% threshold."
        else:
            ax.text(0.5, 0.5, "No type data", ha="center", va="center",
                     transform=ax.transAxes, color=HX["muted"], fontsize=12)
            summary = "No type data available."
        ax.set_title("Pass Rate by Type", fontsize=13, color=HX["txt"], pad=10)
        return ("Pass Rate by Type", self._full_img(fig, 88), summary)

    def _chart_deviation(self, data):
        fig, ax = self._fig(9.5, 3.8)
        devs = []
        for c in data.get("components", []):
            try:
                v = str(c.get("deviation", "")).replace("%", "").replace("+", "").replace("—", "").replace("–", "").strip()
                if v:
                    devs.append(float(v))
            except (ValueError, TypeError):
                pass
        if devs and len(devs) > 2:
            d = np.array(devs)
            q1, q3 = np.percentile(d, [25, 75])
            iqr = q3 - q1
            lo_f = q1 - 2.0 * iqr
            hi_f = q3 + 2.0 * iqr
            d_clean = d[(d >= lo_f) & (d <= hi_f)]
            if len(d_clean) < 3:
                d_clean = d
            ax.hist(d_clean, bins=40, color=HX["info"], alpha=0.7, edgecolor=HX["bd"])
            ax.axvline(0, color=HX["pass"], linewidth=1.5, alpha=0.8, label="Nominal")
            mean_d = np.mean(d_clean)
            std_d = np.std(d_clean)
            if std_d > 0:
                ax.axvline(mean_d, color=HX["warn"], linewidth=1, linestyle="--",
                           alpha=0.8, label=f"u={mean_d:.2f}%")
                ax.axvline(mean_d + 2*std_d, color=HX["fail"], linewidth=1,
                           linestyle=":", alpha=0.6, label=f"+/-2s={2*std_d:.2f}%")
                ax.axvline(mean_d - 2*std_d, color=HX["fail"], linewidth=1,
                           linestyle=":", alpha=0.6)
            ax.set_xlabel("Deviation %", fontsize=10)
            ax.set_ylabel("Count", fontsize=10)
            ax.legend(fontsize=9, framealpha=0); ax.grid(axis="y", alpha=0.3)
            outliers = len(d) - len(d_clean)
            summary = (f"Deviations centered at mean={mean_d:.2f}% with std={std_d:.2f}%. "
                       f"{len(d_clean)} measurements shown"
                       f"{f', {outliers} outliers excluded' if outliers > 0 else ''}. "
                       f"Values outside +/-2 sigma bands warrant investigation.")
        else:
            ax.text(0.5, 0.5, "Insufficient deviation data", ha="center",
                     va="center", transform=ax.transAxes, color=HX["muted"], fontsize=12)
            summary = "Insufficient numeric deviation data for statistical analysis."
        ax.set_title("Deviation Distribution (2 sigma bands)", fontsize=13, color=HX["txt"], pad=10)
        return ("Deviation Distribution", self._full_img(fig, 88), summary)

    def _chart_failure_categories(self, data):
        fig = self._fig_nax(9.5, 4)
        ax = fig.add_subplot(111)
        types = data.get("component_types", {})
        fail_types = {k: v["fail"] for k, v in types.items() if v["fail"] > 0}
        if fail_types:
            labels = list(fail_types.keys())
            vals = list(fail_types.values())
            clrs = [HX["fail"], HX["warn"], HX["info"], "#7c4dff",
                    "#ff6d00", "#e040fb", "#00e5ff", "#76ff03"]
            wedges, texts, autotexts = ax.pie(
                vals, labels=labels, colors=clrs[:len(labels)],
                autopct="%1.0f%%", startangle=140,
                wedgeprops=dict(edgecolor=HX["bg"], linewidth=2),
                textprops={"fontsize": 10, "color": HX["txt"]})
            for at in autotexts:
                at.set_fontsize(9); at.set_color("white"); at.set_fontweight("bold")
            ax.axis("equal")
            top = max(fail_types, key=fail_types.get)
            summary = (f"Failures across {len(fail_types)} types. "
                       f"{top} accounts for the largest share ({fail_types[top]} failures). "
                       f"Targeted inspection of {top} recommended.")
        else:
            ax.text(0.5, 0.5, "No failures to categorize", ha="center",
                     va="center", transform=ax.transAxes, color=HX["pass"], fontsize=14)
            ax.axis("equal")
            summary = "No failures detected. No categorization needed."
        ax.set_title("Failure Category Breakdown", fontsize=13, color=HX["txt"], pad=10)
        return ("Failure Category Breakdown", self._full_img(fig, 85), summary)

    def _chart_metrics_overview(self, data):
        s = data["summary"]
        fig, ax = self._fig(9.5, 3.8)
        metrics = ["Total", "Passed", "Failed"]
        values = [s["total"], s["passed"], s["failed"]]
        clrs = [HX["info"], HX["pass"], HX["fail"] if s["failed"] > 0 else HX["dim"]]
        bars = ax.bar(metrics, values, color=clrs, alpha=0.85, width=0.5,
                      edgecolor=HX["bd"], linewidth=0.5)
        ax.bar_label(bars, padding=5, fontsize=14, fontweight="bold", color=HX["txt"])
        ax.set_ylabel("Count", fontsize=11); ax.grid(axis="y", alpha=0.3)
        ax.set_title("Run Metrics Overview", fontsize=13, color=HX["txt"], pad=10)
        summary = (f"{s['total']} tested total. {s['passed']} passed ({s['pass_rate']:.1f}%), "
                   f"{s['failed']} failed ({100-s['pass_rate']:.1f}%). "
                   f"{'Board is production-ready.' if s['status'] == 'PASS' else 'Board requires rework.'}")
        return ("Run Metrics Overview", self._full_img(fig, 88), summary)

    def _txt_fallback(self, data):
        s = data["summary"]
        folder = os.path.join(OUTPUT_ROOT, s["board_name"].replace("/", "-"))
        os.makedirs(folder, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"{s['serial']}_{ts}.txt")
        with open(path, "w") as f:
            f.write(f"ICT REPORT  {s['board_name']}\n{'='*50}\n")
            f.write(f"Serial:    {s['serial']}\nStatus:    {s['status']}\n")
            f.write(f"Total:     {s['total']}\nPassed:    {s['passed']}\n")
            f.write(f"Failed:    {s['failed']}\nPass Rate: {s['pass_rate']:.1f}%\n")
        return path
