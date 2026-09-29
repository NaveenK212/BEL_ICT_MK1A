"""
ICT PDF Report Generator v5.0
Charts stacked vertically, full page width.
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
except ImportError:
    RL_OK = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    MPL_OK = True
except ImportError:
    MPL_OK = False

OUTPUT_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "ICT_Reports")

# ── colours — BEL / Tejas Defence Avionics ────────────────────────
HX = {
    "bg":   "#0a1929", "s1": "#0d2137", "s2": "#112a45", "s3": "#163354",
    "bd":   "#1e4976", "txt": "#e3edf7", "muted": "#6e96bf", "dim": "#3d6a96",
    "pass": "#00e676", "fail": "#ff1744", "warn": "#ffab00", "info": "#00bcd4",
    "fbg":  "#3d0a14", "pbg": "#0a3320", "wbg": "#3d2e00",
}
def C(k): return colors.HexColor(HX[k])

CHART_RC = {
    "figure.facecolor": HX["s2"], "axes.facecolor": HX["s3"],
    "axes.edgecolor":   HX["bd"], "axes.labelcolor": HX["muted"],
    "xtick.color": HX["muted"],   "ytick.color":  HX["muted"],
    "text.color":  HX["txt"],     "grid.color":   HX["bd"],
    "grid.linestyle": "--",       "grid.alpha":   0.4,
    "font.size": 10,
}


class ReportGenerator:

    # ── PUBLIC ────────────────────────────────────────────────────
    def generate(self, data: dict, save_path: str = None,
                 sections: dict = None, charts: dict = None) -> str:
        if not RL_OK:
            return self._txt_fallback(data)
        return self._pdf(data, save_path, sections, charts)

    # ── HELPERS ───────────────────────────────────────────────────
    def _fig_bytes(self, fig) -> io.BytesIO:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150,
                    bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf

    def _full_img(self, fig, h_mm=95) -> "Image":
        """Embed fig as a full-page-width image."""
        buf = self._fig_bytes(fig)
        page_w = A4[0] - 32 * mm          # usable width
        return Image(buf, width=page_w, height=h_mm * mm)

    # ── CHART BUILDERS ────────────────────────────────────────────
    def _fig(self, w=9.5, h=3.8):
        with plt.rc_context(CHART_RC):
            fig, ax = plt.subplots(figsize=(w, h))
        fig.patch.set_facecolor(HX["s2"])
        return fig, ax

    def _chart_donut_gauge(self, data) -> "Image":
        """Donut + gauge side by side in one figure."""
        with plt.rc_context(CHART_RC):
            fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
        fig.patch.set_facecolor(HX["s2"])

        p  = data["summary"]["passed"]
        f  = data["summary"]["failed"]
        rt = data["summary"]["pass_rate"]
        rc = HX["pass"] if rt >= 98 else HX["warn"] if rt >= 90 else HX["fail"]

        # Donut
        ax = axes[0]
        ax.set_facecolor(HX["s3"])
        sizes = [p, f] if f > 0 else [p]
        clrs  = [HX["pass"], HX["fail"]] if f > 0 else [HX["pass"]]
        ax.pie(sizes, colors=clrs, startangle=90,
               wedgeprops=dict(width=0.48, edgecolor=HX["bg"], linewidth=2))
        ax.text(0,  0.10, f"{rt:.1f}%", ha="center", va="center",
                fontsize=18, fontweight="bold", color=rc, fontfamily="monospace")
        ax.text(0, -0.14, f"{p}P / {f}F",
                ha="center", va="center", fontsize=9, color=HX["muted"])
        ax.set_title("Pass / Fail Overview", fontsize=11,
                     color=HX["muted"], pad=8)
        ax.axis("equal")

        # Gauge
        ax2 = axes[1]
        ax2.set_facecolor(HX["s2"])
        ax2.set_xlim(-1.3, 1.3); ax2.set_ylim(-0.2, 1.3); ax2.axis("off")
        for t1, t2, c in [(np.pi, np.pi*0.67, HX["fail"]),
                           (np.pi*0.67, np.pi*0.33, HX["warn"]),
                           (np.pi*0.33, 0, HX["pass"])]:
            th = np.linspace(t1, t2, 80)
            ax2.plot(np.cos(th)*0.85, np.sin(th)*0.85,
                     color=c, linewidth=12, alpha=0.85, solid_capstyle="butt")
        angle = np.pi * (1 - rt / 100)
        ax2.annotate("", xy=(np.cos(angle)*0.7, np.sin(angle)*0.7),
                     xytext=(0, 0),
                     arrowprops=dict(arrowstyle="-|>", color=HX["txt"],
                                     lw=2, mutation_scale=14))
        ax2.plot(0, 0, "o", color=HX["txt"], markersize=8, zorder=5)
        ax2.text(0, 0.28, f"{rt:.1f}%", ha="center", va="center",
                 fontsize=18, fontweight="bold", color=rc,
                 fontfamily="monospace")
        ax2.text(0, 0.08, "Pass Rate", ha="center", va="center",
                 fontsize=9, color=HX["muted"])
        for pct, lbl in [(0,"0%"),(50,"50%"),(80,"80%"),(98,"98%"),(100,"100%")]:
            a = np.pi*(1-pct/100)
            ax2.text(np.cos(a)*1.1, np.sin(a)*1.1, lbl,
                     ha="center", va="center", fontsize=7.5, color=HX["dim"])
        ax2.set_title("Pass Rate Gauge", fontsize=11,
                      color=HX["muted"], pad=8)

        fig.tight_layout(pad=1.0)
        return self._full_img(fig, 95)

    def _chart_pareto(self, data) -> "Image":
        with plt.rc_context(CHART_RC):
            fig, ax1 = plt.subplots(figsize=(9.5, 3.6))
        fig.patch.set_facecolor(HX["s2"])
        ax2 = ax1.twinx()
        failures = data.get("top_failures", [])
        if not failures:
            ax1.text(0.5, 0.5, "✓  No failures recorded",
                     ha="center", va="center", transform=ax1.transAxes,
                     color=HX["pass"], fontsize=13)
        else:
            names  = [f["component"] for f in failures]
            counts = [f["count"] for f in failures]
            xs     = np.arange(len(names))
            cum    = np.cumsum(counts) / sum(counts) * 100
            bars = ax1.bar(xs, counts, color=HX["fail"], alpha=0.82, width=0.55)
            ax1.bar_label(bars, padding=4, fontsize=9, color=HX["muted"])
            ax2.plot(xs, cum, color=HX["warn"], marker="o",
                     linewidth=2, markersize=6, linestyle="--", label="Cumulative %")
            ax2.axhline(80, color=HX["info"], linewidth=1,
                        linestyle=":", alpha=0.8, label="80% line")
            ax2.set_ylim(0, 115)
            ax2.set_ylabel("Cumulative %", fontsize=9, color=HX["warn"])
            ax2.tick_params(colors=HX["warn"], labelsize=9)
            ax1.set_xticks(xs)
            ax1.set_xticklabels(names, fontsize=10, rotation=15, ha="right")
            ax1.set_ylabel("Failure Count", fontsize=9)
            ax1.tick_params(axis="y", labelsize=9)
            ax1.grid(axis="y", alpha=0.3)
            ax2.legend(fontsize=8, framealpha=0, loc="lower right")
        ax1.set_title("Pareto — Top Failing Components",
                      fontsize=11, color=HX["muted"], pad=8)
        fig.tight_layout(pad=1.2)
        return self._full_img(fig, 90)

    def _chart_comp_types(self, data) -> "Image":
        fig, ax = self._fig(9.5, 3.4)
        types = data.get("component_types", {})
        if types:
            labels = list(types.keys())
            passed = [types[k]["pass"] for k in labels]
            failed = [types[k]["fail"] for k in labels]
            y  = np.arange(len(labels))
            ax.barh(y, passed, color=HX["pass"], alpha=0.85,
                    height=0.45, label="Pass")
            ax.barh(y, failed, left=passed, color=HX["fail"],
                    alpha=0.85, height=0.45, label="Fail")
            ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=10)
            ax.tick_params(axis="x", labelsize=9)
            ax.set_xlabel("Component Count", fontsize=9)
            ax.legend(fontsize=9, framealpha=0)
            ax.grid(axis="x", alpha=0.3)
        ax.set_title("Component Type Breakdown",
                     fontsize=11, color=HX["muted"], pad=8)
        fig.tight_layout(pad=1.2)
        return self._full_img(fig, 88)

    def _chart_power(self, data) -> "Image":
        fig, ax = self._fig(9.5, 3.4)
        rails = data.get("power_rails", [])
        if rails:
            names, noms, meas, clrs = [], [], [], []
            for r in rails:
                names.append(r["rail"])
                try:
                    noms.append(float(str(r["nominal"]).replace("V","")))
                    meas.append(float(str(r["measured"]).replace("V","")))
                except Exception:
                    noms.append(0); meas.append(0)
                clrs.append(HX["pass"] if r["status"] == "PASS" else HX["fail"])
            x = np.arange(len(names)); w = 0.32
            ax.bar(x-w/2, noms, w, color=HX["info"], alpha=0.7, label="Nominal")
            bars = ax.bar(x+w/2, meas, w, color=clrs, alpha=0.88, label="Measured")
            ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8, color=HX["muted"])
            ax.set_xticks(x); ax.set_xticklabels(names, fontsize=11)
            ax.tick_params(axis="y", labelsize=9)
            ax.set_ylabel("Voltage (V)", fontsize=9)
            ax.legend(fontsize=9, framealpha=0)
            ax.grid(axis="y", alpha=0.3)
        ax.set_title("Power Supply — Nominal vs Measured",
                     fontsize=11, color=HX["muted"], pad=8)
        fig.tight_layout(pad=1.2)
        return self._full_img(fig, 88)

    def _chart_deviation(self, data) -> "Image":
        fig, ax = self._fig(9.5, 3.4)
        devs = []
        for c in data.get("components", []):
            try:
                devs.append(float(str(c.get("deviation",""))
                            .replace("%","").replace("+","")))
            except Exception:
                pass
        if devs:
            ax.hist(devs, bins=20, color=HX["info"], alpha=0.7,
                    edgecolor=HX["bd"], linewidth=0.5)
            ax.axvline(-5, color=HX["warn"], linewidth=1.5,
                       linestyle="--", alpha=0.8, label="±5% limit")
            ax.axvline( 5, color=HX["warn"], linewidth=1.5,
                       linestyle="--", alpha=0.8)
            ax.axvline( 0, color=HX["muted"], linewidth=0.8, alpha=0.5)
            ax.set_xlabel("Deviation (%)", fontsize=9)
            ax.set_ylabel("Count", fontsize=9)
            ax.tick_params(labelsize=9)
            ax.legend(fontsize=9, framealpha=0)
            ax.grid(axis="y", alpha=0.3)
        ax.set_title("Measurement Deviation Distribution",
                     fontsize=11, color=HX["muted"], pad=8)
        fig.tight_layout(pad=1.2)
        return self._full_img(fig, 88)

    # ── STYLES ────────────────────────────────────────────────────
    def _S(self):
        return {
            "h1": ParagraphStyle("h1", fontSize=20, fontName="Helvetica-Bold",
                                  textColor=C("txt"), leading=24),
            "sub": ParagraphStyle("sub", fontSize=10, fontName="Helvetica",
                                   textColor=C("muted"), leading=14),
            "sec": ParagraphStyle("sec", fontSize=14, fontName="Helvetica-Bold",
                                   textColor=C("info"), letterSpacing=1.2,
                                   spaceBefore=4, spaceAfter=2),
            "sec_fail": ParagraphStyle("sec_fail", fontSize=14, fontName="Helvetica-Bold",
                                        textColor=C("fail"),
                                        spaceBefore=4, spaceAfter=2),
            "sec_warn": ParagraphStyle("sec_warn", fontSize=14, fontName="Helvetica-Bold",
                                        textColor=C("warn"),
                                        spaceBefore=4, spaceAfter=2),
            "insight": ParagraphStyle("ins", fontSize=11, fontName="Helvetica",
                                       textColor=C("warn"), leftIndent=8),
            "footer": ParagraphStyle("foot", fontSize=8, fontName="Helvetica",
                                      textColor=C("muted"), alignment=TA_CENTER),
        }

    # ── TABLE HELPERS ─────────────────────────────────────────────
    def _base_ts(self, hdr_bg="s1", hdr_fg="info"):
        return TableStyle([
            ("BACKGROUND",    (0,0),(-1, 0), C(hdr_bg)),
            ("TEXTCOLOR",     (0,0),(-1, 0), C(hdr_fg)),
            ("FONTNAME",      (0,0),(-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1, 0), 10),
            ("FONTSIZE",      (0,1),(-1,-1), 9),
            ("FONTNAME",      (0,1),(-1,-1), "Courier"),
            ("TEXTCOLOR",     (0,1),(-1,-1), C("txt")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C("s2"), C("s3")]),
            ("GRID",          (0,0),(-1,-1), 0.4, C("bd")),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 7),
            ("RIGHTPADDING",  (0,0),(-1,-1), 7),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ])

    def _comp_table(self, components):
        hdr  = ["Ref","Type","Nominal","Measured","Deviation","Status"]
        rows = [hdr] + [[c["ref"], c["type"], c.get("nominal","—"),
                          c.get("measured","—"), c.get("deviation","—"),
                          c["status"]] for c in components]
        t  = Table(rows, colWidths=["11%","16%","18%","18%","17%","14%"],
                   repeatRows=1)
        ts = self._base_ts()
        for i, c in enumerate(components, 1):
            cl = C("pass") if c["status"]=="PASS" else C("fail")
            ts.add("TEXTCOLOR", (5,i),(5,i), cl)
            ts.add("FONTNAME",  (5,i),(5,i), "Courier-Bold")
            if c["status"] == "FAIL":
                ts.add("TEXTCOLOR", (0,i),(0,i), C("fail"))
        t.setStyle(ts)
        return t

    def _fail_table(self, failed):
        hdr  = ["Ref","Type","Nominal","Measured","Deviation","Limit","Note"]
        rows = [hdr] + [[c["ref"], c["type"], c.get("nominal","—"),
                          c.get("measured","—"), c.get("deviation","—"),
                          c.get("limit","—"), c.get("note","—")] for c in failed]
        t  = Table(rows, colWidths=["9%","11%","13%","13%","11%","11%","32%"],
                   repeatRows=1)
        ts = self._base_ts("fbg", "fail")
        for i in range(1, len(rows)):
            ts.add("TEXTCOLOR", (0,i),(0,i), C("fail"))
            ts.add("FONTNAME",  (0,i),(0,i), "Courier-Bold")
        t.setStyle(ts)
        return t

    def _power_table(self, rails):
        hdr  = ["Rail","Nominal","Measured","Deviation","Ripple","Status"]
        rows = [hdr] + [[p["rail"], p["nominal"], p["measured"],
                          p.get("deviation","—"), p.get("ripple","—"),
                          p["status"]] for p in rails]
        t  = Table(rows, colWidths=["15%","18%","18%","16%","16%","17%"],
                   repeatRows=1)
        ts = self._base_ts()
        for i, p in enumerate(rails, 1):
            cl = C("pass") if p["status"]=="PASS" else C("fail")
            ts.add("TEXTCOLOR", (5,i),(5,i), cl)
            ts.add("FONTNAME",  (5,i),(5,i), "Courier-Bold")
            ts.add("TEXTCOLOR", (0,i),(0,i), C("info"))
        t.setStyle(ts)
        return t

    def _exec_table(self, s):
        is_pass = s["status"] == "PASS"
        rt = s["pass_rate"]
        rc = C("pass") if rt >= 98 else C("warn") if rt >= 90 else C("fail")
        sc = C("pass") if is_pass else C("fail")

        def kp(t): return Paragraph(t, ParagraphStyle("k", fontSize=10,
                                     fontName="Helvetica-Bold", textColor=C("muted")))
        def vp(t, bold=False, color=None):
            return Paragraph(t, ParagraphStyle("v", fontSize=11,
                              fontName="Courier-Bold" if bold else "Courier",
                              textColor=color or C("txt")))
        rows = [
            [kp("Board Name"),    vp(s["board_name"], True),
             kp("Serial Number"), vp(s["serial"], True)],
            [kp("Test Status"),   vp(s["status"], True, sc),
             kp("Pass Rate"),     vp(f"{rt:.1f}%", True, rc)],
            [kp("Total Tested"),  vp(str(s["total"])),
             kp("Test Time"),     vp(s.get("test_time","—"))],
            [kp("Passed"),        vp(str(s["passed"]), True, C("pass")),
             kp("Failed"),        vp(str(s["failed"]), True,
                                      C("fail") if s["failed"]>0 else C("pass"))],
        ]
        t = Table(rows, colWidths=["22%","28%","22%","28%"])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C("s2")),
            ("BACKGROUND",    (0,0),(0,-1),  C("s1")),
            ("BACKGROUND",    (2,0),(2,-1),  C("s1")),
            ("GRID",          (0,0),(-1,-1), 0.5, C("bd")),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        return t

    # ── PDF BUILD ─────────────────────────────────────────────────
    def _pdf(self, data: dict, save_path: str = None,
             sections: dict = None, charts: dict = None) -> str:
        inc = {
            "cover": True, "summary": True,
            "failed": True, "power": True,
            "insights": True, "components": True,
        }
        if sections:
            inc.update(sections)

        chrt = {
            "chart_donut": True, "chart_pareto": True,
            "chart_comp": True, "chart_power": True,
            "chart_deviation": True,
        }
        if charts:
            chrt.update(charts)

        s    = data["summary"]
        name = s["board_name"].replace("/","-").replace("\\","-")
        sn   = s["serial"].replace("/","-")
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(OUTPUT_ROOT, name)
        os.makedirs(folder, exist_ok=True)
        # Auto-save PDF into run folder if available, else board folder
        run_folder = data.get("run_folder", folder)
        auto_pdf   = os.path.join(run_folder, f"{sn}_{ts}.pdf")
        path       = save_path or auto_pdf

        doc = SimpleDocTemplate(
            path, pagesize=A4,
            leftMargin=16*mm, rightMargin=16*mm,
            topMargin=16*mm, bottomMargin=16*mm,
            title=f"ICT Report — {name}",
            author="ICT Report Analyzer v5.0"
        )
        ST    = self._S()
        story = []
        rt    = s["pass_rate"]
        rc    = "#22c55e" if rt >= 98 else "#f59e0b" if rt >= 90 else "#ef4444"
        sc    = "#22c55e" if s["status"] == "PASS" else "#ef4444"

        # ── COVER ─────────────────────────────────────────────────
        if inc["cover"]:
            cl = Paragraph(
                f"<font size='20'><b>{s['board_name']}</b></font><br/>"
                f"<font size='3'> </font><br/>"
                f"<font size='10' color='{HX['muted']}'>Serial: </font>"
                f"<font size='10' color='{HX['txt']}'><b>{s['serial']}</b></font><br/>"
                f"<font size='9' color='{HX['dim']}'>Tested: {s.get('timestamp','')[:19]}</font>",
                ParagraphStyle("cl", fontName="Helvetica", textColor=C("txt"), leading=16))
            cr = Paragraph(
                f"<font size='26' color='{sc}'><b>{s['status']}</b></font><br/>"
                f"<font size='3'> </font><br/>"
                f"<font size='15' color='{rc}'><b>{rt:.1f}%</b></font>"
                f"<font size='10' color='{HX['muted']}'> pass rate</font><br/>"
                f"<font size='9' color='{HX['dim']}'>{s['passed']} pass / {s['failed']} fail / {s['total']} total</font>",
                ParagraphStyle("cr", fontName="Helvetica", textColor=C("txt"),
                               alignment=TA_RIGHT, leading=18))
            cov = Table([[cl, cr]], colWidths=["55%","45%"])
            cov.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C("s2")),
                ("BOX",           (0,0),(-1,-1), 1, C("bd")),
                ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                ("LEFTPADDING",   (0,0),(-1,-1), 16),
                ("RIGHTPADDING",  (0,0),(-1,-1), 16),
                ("TOPPADDING",    (0,0),(-1,-1), 16),
                ("BOTTOMPADDING", (0,0),(-1,-1), 16),
                ("LINEAFTER",     (0,0),(0,-1),  2, C("info")),
            ]))
            story.append(cov)
            story.append(Spacer(1, 5*mm))
            story.append(HRFlowable(width="100%", thickness=1.5,
                                      color=C("info"), spaceAfter=4*mm))

        if inc["summary"]:
            story.append(Paragraph("EXECUTIVE SUMMARY", ST["sec"]))
            story.append(Spacer(1, 2*mm))
            story.append(self._exec_table(s))
            story.append(Spacer(1, 6*mm))

        if MPL_OK and any(chrt.values()):
            story.append(Paragraph("TEST RESULT CHARTS", ST["sec"]))
            story.append(Spacer(1, 3*mm))
            chart_map = [
                ("chart_donut",     "Pass / Fail Overview + Gauge",       lambda: self._chart_donut_gauge(data)),
                ("chart_pareto",    "Pareto — Top Failing Components",    lambda: self._chart_pareto(data)),
                ("chart_comp",      "Component Type Breakdown",           lambda: self._chart_comp_types(data)),
                ("chart_power",     "Power Supply Rails",                 lambda: self._chart_power(data)),
                ("chart_deviation", "Measurement Deviation Distribution", lambda: self._chart_deviation(data)),
            ]
            for key, title, fn in chart_map:
                if chrt.get(key, True):
                    story.append(KeepTogether([
                        Paragraph(title, ParagraphStyle("ct", fontSize=11,
                            fontName="Helvetica-Bold", textColor=C("muted"),
                            spaceBefore=2, spaceAfter=2)),
                        fn(), Spacer(1, 5*mm),
                    ]))

        if inc["failed"] and data.get("failed_detail"):
            story.append(KeepTogether([
                Paragraph("⚠  FAILED COMPONENTS", ST["sec_fail"]),
                Spacer(1, 2*mm),
                self._fail_table(data["failed_detail"]),
                Spacer(1, 5*mm),
            ]))

        if inc["power"] and data.get("power_rails"):
            story.append(KeepTogether([
                Paragraph("POWER SUPPLY MEASUREMENTS", ST["sec"]),
                Spacer(1, 2*mm),
                self._power_table(data["power_rails"]),
                Spacer(1, 5*mm),
            ]))

        if inc["insights"] and data.get("insights"):
            story.append(Paragraph("INSIGHTS & WARNINGS", ST["sec_warn"]))
            story.append(Spacer(1, 2*mm))
            for ins in data["insights"]:
                story.append(Paragraph(f"⚠  {ins}", ST["insight"]))
                story.append(Spacer(1, 2*mm))
            story.append(Spacer(1, 4*mm))

        if inc["components"]:
            story.append(PageBreak())
            story.append(Paragraph("COMPLETE COMPONENT TEST RESULTS", ST["sec"]))
            story.append(Spacer(1, 3*mm))
            story.append(self._comp_table(data.get("components",[])))

        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                  color=C("bd"), spaceAfter=2*mm))
        story.append(Paragraph(
            f"ICT Report Analyzer v5.0  ·  "
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ·  "
            f"ict_results.db",
            ST["footer"]
        ))

        doc.build(story)
        return path

    # ── TEXT FALLBACK ─────────────────────────────────────────────
    def _txt_fallback(self, data: dict) -> str:
        s      = data["summary"]
        folder = os.path.join(OUTPUT_ROOT, s["board_name"].replace("/","-"))
        os.makedirs(folder, exist_ok=True)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"{s['serial']}_{ts}.txt")
        with open(path,"w") as f:
            f.write(f"ICT REPORT  {s['board_name']}\n{'='*50}\n")
            f.write(f"Serial:    {s['serial']}\n")
            f.write(f"Status:    {s['status']}\n")
            f.write(f"Pass Rate: {s['pass_rate']:.1f}%\n")
            f.write(f"Total: {s['total']}  Pass: {s['passed']}  Fail: {s['failed']}\n")
            f.write("\nInstall reportlab + matplotlib for PDF:\n")
            f.write("  pip install reportlab matplotlib\n")
        return path
