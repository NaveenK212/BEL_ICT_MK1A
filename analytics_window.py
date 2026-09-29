"""
Advanced Analytics Window — unique deep-dive charts not on the main dashboard.
Charts: Pass Rate Distribution, Deviation Box Plot, Cumulative Yield,
        Repeat Failures, Volume vs Quality Bubble, Component Radar.
"""
import customtkinter as ctk
import tkinter as tk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from themes import get_theme
from config import Config as _Cfg
_T = get_theme(_Cfg().get("theme", "dark_navy"))

BG   = _T["bg"];  S1  = _T["s1"];  S2  = _T["s2"];  S3  = _T["s3"]
BD   = _T["bd"];  TXT = _T["txt"]; MUT = _T["mut"]; DIM = _T["dim"]
PASS = _T["pass"];FAIL= _T["fail"];WARN= _T["warn"];INFO= _T["info"]
PUR  = _T["pur"]


class AnalyticsWindow(ctk.CTkToplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("Advanced Analytics — ICT Report Analyzer")
        self.geometry("1200x820")
        self.minsize(1000, 700)
        self.configure(fg_color=BG)
        self._canvases = []
        self._board_filter = tk.StringVar(value="All Boards")

        self._build()
        self._load_data()
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color=S2, corner_radius=0,
                            border_width=1, border_color=BD, height=50)
        bar.pack(fill="x"); bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="⚡  Advanced Analytics",
                     font=("Segoe UI", 14, "bold"),
                     text_color=PUR).pack(side="left", padx=16)

        ctk.CTkLabel(bar, text="Board:",
                     font=("Segoe UI", 10), text_color=MUT).pack(side="left", padx=(20, 4))
        self._menu = ctk.CTkOptionMenu(
            bar, variable=self._board_filter, values=["All Boards"],
            fg_color=S3, button_color=BD, button_hover_color=S1,
            text_color=TXT, font=("Segoe UI", 10), width=200,
            command=lambda _: self._load_data())
        self._menu.pack(side="left", padx=4)

        ctk.CTkButton(bar, text="↻  Refresh", width=90, height=30,
                       fg_color=S3, hover_color=S1, border_color=BD, border_width=1,
                       font=("Segoe UI", 10), text_color=MUT,
                       command=self._load_data).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="✕  Close", width=80, height=30,
                       fg_color=S3, hover_color="#3f1515", border_color=BD, border_width=1,
                       font=("Segoe UI", 10), text_color=MUT,
                       command=self._close).pack(side="right", padx=16)

        self._body = ctk.CTkScrollableFrame(self, fg_color=BG, scrollbar_button_color=BD)
        self._body.pack(fill="both", expand=True)

        self._kpi_frame = ctk.CTkFrame(self._body, fg_color="transparent")
        self._kpi_frame.pack(fill="x", padx=14, pady=(14, 6))

        self._chart_frame = ctk.CTkFrame(self._body, fg_color="transparent")
        self._chart_frame.pack(fill="x", padx=14, pady=6)
        self._chart_frame.columnconfigure(0, weight=1)
        self._chart_frame.columnconfigure(1, weight=1)

    def _embed(self, fig, row, col):
        card = ctk.CTkFrame(self._chart_frame, fg_color=S2, corner_radius=6,
                             border_width=1, border_color=BD)
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        self._canvases.append(canvas)

    def _load_data(self):
        for w in self._chart_frame.winfo_children(): w.destroy()
        for c in self._canvases: plt.close("all")
        self._canvases = []

        boards = ["All Boards"] + self.db.get_board_names()
        self._menu.configure(values=boards)
        board = None if self._board_filter.get() == "All Boards" else self._board_filter.get()

        runs        = self.db.get_runs(board_name=board, limit=500)
        rates       = self.db.get_pass_rate_histogram()
        dev_by_type = self.db.get_deviation_by_type()
        trend       = self.db.get_pass_rate_trend(board_name=board, limit=50)
        repeats     = self.db.get_repeat_failures()
        board_cmp   = self.db.get_board_comparison()
        comp_type   = self.db.get_component_type_failures()

        self._render_kpis(runs, rates, repeats)
        self._chart_pass_rate_dist(rates)
        self._chart_deviation_box(dev_by_type)
        self._chart_cumulative_yield(trend)
        self._chart_repeat_failures(repeats)
        self._chart_volume_vs_quality(board_cmp)
        self._chart_type_radar(comp_type)

    # ── KPIs ──────────────────────────────────────────────────────
    def _render_kpis(self, runs, rates, repeats):
        for w in self._kpi_frame.winfo_children(): w.destroy()
        if not runs:
            ctk.CTkLabel(self._kpi_frame, text="No data available.",
                         text_color=MUT).pack()
            return

        d = np.array(rates) if rates else np.array([0])
        std_dev = float(np.std(d))
        median_r = float(np.median(d))
        below_98 = sum(1 for r in rates if r < 98)
        consistency = max(0, 100 - std_dev * 10)
        sigma = self._sigma(d)

        kpis = [
            ("Median Rate",   f"{median_r:.1f}%",    PASS if median_r >= 98 else WARN),
            ("Std Dev",        f"{std_dev:.2f}",       PASS if std_dev < 2 else WARN if std_dev < 5 else FAIL),
            ("Consistency",    f"{consistency:.0f}%",   PASS if consistency >= 80 else WARN),
            ("Below 98%",      f"{below_98}/{len(rates)}", FAIL if below_98 > 0 else PASS),
            ("Repeat Fails",   str(len(repeats)),       FAIL if repeats else PASS),
            ("Sigma Level",    f"{sigma:.1f}\u03c3",    INFO),
        ]
        for label, val, color in kpis:
            card = ctk.CTkFrame(self._kpi_frame, fg_color=S2, corner_radius=6,
                                 border_width=1, border_color=BD)
            card.pack(side="left", padx=3, fill="both", expand=True)
            ctk.CTkLabel(card, text=label, font=("Segoe UI", 8, "bold"),
                         text_color=MUT).pack(pady=(6, 0))
            ctk.CTkLabel(card, text=val, font=("Segoe UI", 16, "bold"),
                         text_color=color).pack(pady=(0, 6))

    def _sigma(self, rates):
        if len(rates) == 0: return 0
        defect = sum(1 for r in rates if r < 98) / len(rates)
        if defect == 0: return 6.0
        if defect >= 1: return 0.0
        try:
            from scipy.stats import norm
            return float(norm.ppf(1 - defect) + 1.5)
        except Exception:
            if defect < 0.001: return 5.5
            if defect < 0.01: return 4.5
            if defect < 0.05: return 3.5
            if defect < 0.10: return 3.0
            if defect < 0.30: return 2.0
            return 1.0

    # ── CHART 1: Pass Rate Distribution ───────────────────────────
    def _chart_pass_rate_dist(self, rates):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        ax = fig.add_subplot(111); ax.set_facecolor(S3)
        if rates and len(rates) > 1:
            d = np.array(rates)
            n, bins, patches = ax.hist(d, bins=min(20, max(5, len(d)//3)),
                                        color=INFO, alpha=0.7, edgecolor=BD)
            for patch, b in zip(patches, bins):
                if b < 98: patch.set_facecolor(FAIL); patch.set_alpha(0.6)
            ax.axvline(98, color=WARN, linewidth=2, linestyle="--", alpha=0.8, label="98% target")
            ax.axvline(np.mean(d), color=PUR, linewidth=1.5, linestyle="-.",
                       alpha=0.8, label=f"Mean: {np.mean(d):.1f}%")
            ax.set_xlabel("Pass Rate (%)", fontsize=9, color=MUT)
            ax.set_ylabel("Runs", fontsize=9, color=MUT)
            ax.legend(fontsize=7, framealpha=0); ax.grid(axis="y", alpha=0.3, color=BD)
        else:
            ax.text(0.5, 0.5, "Need more runs", ha="center", va="center",
                    transform=ax.transAxes, color=MUT, fontsize=10)
        ax.set_title("Pass Rate Distribution", fontsize=11, color=TXT, pad=8)
        ax.tick_params(colors=MUT); fig.tight_layout()
        self._embed(fig, 0, 0)

    # ── CHART 2: Deviation Box Plot ───────────────────────────────
    def _chart_deviation_box(self, dev_by_type):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        ax = fig.add_subplot(111); ax.set_facecolor(S3)
        if dev_by_type:
            labels = list(dev_by_type.keys())
            data = []
            for k in labels:
                d = np.array(dev_by_type[k])
                q1, q3 = np.percentile(d, [10, 90])
                iqr = max(q3 - q1, 0.5)
                c = d[(d >= q1 - 1.5*iqr) & (d <= q3 + 1.5*iqr)]
                data.append(c if len(c) > 0 else d)
            bp = ax.boxplot(data, labels=labels, patch_artist=True,
                           medianprops=dict(color=WARN, linewidth=2),
                           whiskerprops=dict(color=MUT), capprops=dict(color=MUT),
                           flierprops=dict(marker="o", markerfacecolor=FAIL, markersize=3, alpha=0.5))
            pal = [INFO, PASS, PUR, WARN, FAIL, "#ff6d00", "#76ff03", "#00e5ff"]
            for i, patch in enumerate(bp["boxes"]):
                patch.set_facecolor(pal[i % len(pal)]); patch.set_alpha(0.6)
            ax.axhline(0, color=PASS, linewidth=1, alpha=0.5)
            ax.set_ylabel("Deviation %", fontsize=9, color=MUT)
            ax.tick_params(axis="x", labelsize=8, labelcolor=TXT)
            ax.grid(axis="y", alpha=0.3, color=BD)
        else:
            ax.text(0.5, 0.5, "No deviation data", ha="center", va="center",
                    transform=ax.transAxes, color=MUT, fontsize=10)
        ax.set_title("Deviation Spread by Component Type", fontsize=11, color=TXT, pad=8)
        ax.tick_params(colors=MUT); fig.tight_layout()
        self._embed(fig, 0, 1)

    # ── CHART 3: Cumulative Yield ─────────────────────────────────
    def _chart_cumulative_yield(self, trend):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        ax = fig.add_subplot(111); ax.set_facecolor(S3)
        if trend and len(trend) > 1:
            rates = [r["pass_rate"] for r in trend]
            cum = []; total = 0
            for i, r in enumerate(rates):
                total += r; cum.append(total / (i + 1))
            xs = range(len(rates))
            ax.plot(xs, rates, color=DIM, linewidth=1, alpha=0.4, marker=".", markersize=4, label="Individual")
            ax.plot(xs, cum, color=INFO, linewidth=2.5, label="Cumulative Avg")
            ax.fill_between(xs, cum, alpha=0.1, color=INFO)
            ax.axhline(98, color=WARN, linewidth=1.5, linestyle="--", alpha=0.7, label="98% target")
            if len(cum) > 3:
                ax.axhline(cum[-1], color=PUR, linewidth=1, linestyle=":", alpha=0.5,
                          label=f"Converging: {cum[-1]:.1f}%")
            ax.set_xlabel("Run Sequence", fontsize=9, color=MUT)
            ax.set_ylabel("Pass Rate (%)", fontsize=9, color=MUT)
            ax.set_ylim(max(0, min(rates) - 5), 103)
            ax.legend(fontsize=7, framealpha=0); ax.grid(True, alpha=0.3, color=BD)
        else:
            ax.text(0.5, 0.5, "Need more runs for convergence", ha="center", va="center",
                    transform=ax.transAxes, color=MUT, fontsize=10)
        ax.set_title("Cumulative Yield Convergence", fontsize=11, color=TXT, pad=8)
        ax.tick_params(colors=MUT); fig.tight_layout()
        self._embed(fig, 1, 0)

    # ── CHART 4: Repeat Failures ──────────────────────────────────
    def _chart_repeat_failures(self, repeats):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        ax = fig.add_subplot(111); ax.set_facecolor(S3)
        if repeats:
            refs = [f"{r['ref']} ({r['type'] or '?'})" for r in repeats[:10]]
            runs_c = [r["run_count"] for r in repeats[:10]]
            total_f = [r["total_fails"] for r in repeats[:10]]
            y = np.arange(len(refs))
            ax.barh(y - 0.15, runs_c, height=0.3, color=WARN, alpha=0.85, label="Runs Affected")
            ax.barh(y + 0.15, total_f, height=0.3, color=FAIL, alpha=0.85, label="Total Failures")
            ax.set_yticks(y); ax.set_yticklabels(refs, fontsize=7, color=TXT)
            ax.invert_yaxis()
            ax.set_xlabel("Count", fontsize=9, color=MUT)
            ax.legend(fontsize=7, framealpha=0); ax.grid(axis="x", alpha=0.3, color=BD)
        else:
            ax.text(0.5, 0.5, "No repeat failures detected\n(Good — no component fails across multiple runs)",
                    ha="center", va="center", transform=ax.transAxes, color=PASS, fontsize=10)
        ax.set_title("Repeat Failure Offenders (Multi-Run)", fontsize=11, color=TXT, pad=8)
        ax.tick_params(colors=MUT); fig.tight_layout()
        self._embed(fig, 1, 1)

    # ── CHART 5: Volume vs Quality ────────────────────────────────
    def _chart_volume_vs_quality(self, board_cmp):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        ax = fig.add_subplot(111); ax.set_facecolor(S3)
        if board_cmp:
            names = [b["board_name"][:14] for b in board_cmp]
            vols = [b["run_count"] for b in board_cmp]
            avgs = [b["avg_rate"] for b in board_cmp]
            fails = [b.get("fail_runs", 0) for b in board_cmp]
            sizes = [max(60, f * 80) for f in fails]
            colors = [PASS if r >= 98 else WARN if r >= 92 else FAIL for r in avgs]
            ax.scatter(vols, avgs, s=sizes, c=colors, alpha=0.7, edgecolors="white", linewidth=0.8)
            for i, n in enumerate(names):
                ax.annotate(n, (vols[i], avgs[i]), textcoords="offset points",
                           xytext=(8, 4), fontsize=7, color=MUT)
            ax.axhline(98, color=WARN, linewidth=1.5, linestyle="--", alpha=0.7, label="98% target")
            ax.set_xlabel("Test Volume (Runs)", fontsize=9, color=MUT)
            ax.set_ylabel("Avg Pass Rate (%)", fontsize=9, color=MUT)
            ax.set_ylim(min(avgs) - 3 if avgs else 80, 103)
            ax.legend(fontsize=7, framealpha=0); ax.grid(True, alpha=0.3, color=BD)
        else:
            ax.text(0.5, 0.5, "No board data", ha="center", va="center",
                    transform=ax.transAxes, color=MUT, fontsize=10)
        ax.set_title("Volume vs Quality (bubble = failures)", fontsize=11, color=TXT, pad=8)
        ax.tick_params(colors=MUT); fig.tight_layout()
        self._embed(fig, 2, 0)

    # ── CHART 6: Radar ────────────────────────────────────────────
    def _chart_type_radar(self, comp_type):
        fig = Figure(figsize=(6, 3.2), dpi=90); fig.patch.set_facecolor(S2)
        if comp_type and len(comp_type) >= 3:
            types = [c["type"] or "Other" for c in comp_type]
            totals = [c["total"] for c in comp_type]
            fails = [c["fails"] for c in comp_type]
            rates = [(t - f) / t * 100 if t > 0 else 100 for t, f in zip(totals, fails)]
            N = len(types)
            angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
            rates_p = rates + [rates[0]]
            angles_p = angles + [angles[0]]
            ax = fig.add_subplot(111, polar=True); ax.set_facecolor(S3)
            ax.plot(angles_p, rates_p, color=INFO, linewidth=2, marker="o", markersize=5)
            ax.fill(angles_p, rates_p, color=INFO, alpha=0.15)
            ax.plot(angles_p, [98]*(N+1), color=WARN, linewidth=1, linestyle="--", alpha=0.7)
            ax.set_xticks(angles)
            ax.set_xticklabels(types, fontsize=8, color=TXT)
            ax.set_ylim(max(0, min(rates) - 10), 105)
            ax.set_rticks([70, 80, 90, 98, 100])
            ax.set_yticklabels(["70%","80%","90%","98%","100%"], fontsize=6, color=MUT)
            ax.spines["polar"].set_color(BD); ax.grid(color=BD, alpha=0.4)
            ax.tick_params(axis="y", colors=MUT)
        else:
            ax = fig.add_subplot(111); ax.set_facecolor(S3)
            ax.text(0.5, 0.5, "Need 3+ component types for radar",
                    ha="center", va="center", transform=ax.transAxes, color=MUT, fontsize=10)
        ax.set_title("Component Quality Radar", fontsize=11, color=TXT, pad=16)
        fig.tight_layout()
        self._embed(fig, 2, 1)

    def _close(self):
        plt.close("all")
        self.destroy()
