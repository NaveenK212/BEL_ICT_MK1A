"""
Analytics Window — historical trend analysis dashboard.
Opens as a Toplevel window from the main app.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

BG_DARK    = "#0a1929"
BG_CARD    = "#112a45"
BG_SURFACE = "#163354"
BORDER     = "#1e4976"
TEXT       = "#e3edf7"
TEXT_MUTED = "#6e96bf"
PASS_COLOR = "#00e676"
FAIL_COLOR = "#ff1744"
WARN_COLOR = "#ffab00"
INFO_COLOR = "#00bcd4"
PURPLE     = "#7c4dff"

plt.rcParams.update({
    "figure.facecolor": BG_CARD,
    "axes.facecolor":   BG_SURFACE,
    "axes.edgecolor":   BORDER,
    "axes.labelcolor":  TEXT_MUTED,
    "xtick.color":      TEXT_MUTED,
    "ytick.color":      TEXT_MUTED,
    "text.color":       TEXT,
    "grid.color":       BORDER,
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
})


class AnalyticsWindow(ctk.CTkToplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("Analytics Dashboard — ICT Report Analyzer")
        self.geometry("1100x760")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DARK)
        self._canvases = []
        self._board_filter = tk.StringVar(value="All Boards")

        self._build_header()
        self._build_body()
        self._load_data()
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)

    # ── LAYOUT ────────────────────────────────────────────────────
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0,
                            border_width=1, border_color=BORDER, height=50)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="⚡  Analytics Dashboard",
                     font=("Segoe UI", 14, "bold"),
                     text_color=PURPLE).pack(side="left", padx=16, pady=12)

        ctk.CTkLabel(bar, text="Board Filter:",
                     font=("Segoe UI", 10), text_color=TEXT_MUTED).pack(
            side="left", padx=(20, 4))

        self.board_menu = ctk.CTkOptionMenu(
            bar, variable=self._board_filter,
            values=["All Boards"],
            fg_color=BG_SURFACE, button_color=BORDER,
            button_hover_color=BG_DARK, text_color=TEXT,
            font=("JetBrains Mono", 10), width=200,
            command=self._on_filter_change
        )
        self.board_menu.pack(side="left", padx=4)

        ctk.CTkButton(bar, text="↻  Refresh", width=90, height=30,
                       fg_color=BG_SURFACE, hover_color=BG_DARK,
                       border_color=BORDER, border_width=1,
                       font=("Segoe UI", 10), text_color=TEXT_MUTED,
                       command=self._load_data).pack(side="left", padx=4)

        ctk.CTkButton(bar, text="✕  Close", width=80, height=30,
                       fg_color=BG_SURFACE, hover_color="#3f1515",
                       border_color=BORDER, border_width=1,
                       font=("Segoe UI", 10), text_color=TEXT_MUTED,
                       command=self._on_close).pack(side="right", padx=16)

    def _build_body(self):
        # Main scrollable area
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Top row: KPI cards
        self.kpi_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.kpi_frame.pack(fill="x", padx=14, pady=(14, 6))

        # Chart row 1: trend + failure freq
        row1 = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=6)
        self.trend_card   = self._chart_card(row1, "Pass Rate Trend", side="left",  expand=True)
        self.failfreq_card= self._chart_card(row1, "Failure Frequency by Component", side="right", expand=True)

        # Chart row 2: board comparison
        row2 = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=6)
        self.boardcomp_card = self._chart_card(row2, "Board Pass Rate Comparison", side="left", expand=True)
        self.status_card    = self._chart_card(row2, "Run Status Distribution", side="right", expand=True)

        # Past runs table
        self.runs_frame = ctk.CTkFrame(self.scroll, fg_color=BG_CARD,
                                        corner_radius=6,
                                        border_width=1, border_color=BORDER)
        self.runs_frame.pack(fill="x", padx=14, pady=(6, 14))
        self._section_label(self.runs_frame, "PAST RUNS")
        self._build_runs_table()

    def _chart_card(self, parent, title, side="left", expand=False):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=6,
                             border_width=1, border_color=BORDER)
        card.pack(side=side, fill="both", expand=expand,
                  padx=(0, 6) if side == "left" else (0, 0), pady=0)
        self._section_label(card, title)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        return inner

    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=f"  {text}",
                     font=("Segoe UI", 9, "bold"),
                     text_color=TEXT_MUTED, anchor="w").pack(
            fill="x", pady=(8, 4), padx=4)

    def _build_runs_table(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Ana.Treeview",
                         background=BG_SURFACE, fieldbackground=BG_SURFACE,
                         foreground=TEXT, rowheight=26,
                         font=("JetBrains Mono", 10))
        style.configure("Ana.Treeview.Heading",
                         background=BG_CARD, foreground=TEXT_MUTED,
                         font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Ana.Treeview", background=[("selected", BG_DARK)])
        style.layout("Ana.Treeview",[("Ana.Treeview.treearea",{"sticky":"nswe"})])

        cols = ("ID", "Board", "Serial", "Timestamp", "Total", "Pass", "Fail", "Rate", "Status")
        frame = tk.Frame(self.runs_frame, bg=BG_DARK, height=200)
        frame.pack(fill="x", padx=10, pady=(0, 10))
        frame.pack_propagate(False)
        sb = ttk.Scrollbar(frame, orient="vertical")
        self.runs_tv = ttk.Treeview(frame, columns=cols, show="headings",
                                     style="Ana.Treeview",
                                     yscrollcommand=sb.set, height=7)
        sb.config(command=self.runs_tv.yview)
        sb.pack(side="right", fill="y")
        self.runs_tv.pack(fill="both", expand=True)

        widths = [40, 160, 160, 150, 60, 60, 60, 75, 70]
        for col, w in zip(cols, widths):
            self.runs_tv.heading(col, text=col)
            self.runs_tv.column(col, width=w, anchor="w", minwidth=40)
        self.runs_tv.tag_configure("pass", foreground=PASS_COLOR)
        self.runs_tv.tag_configure("fail", foreground=FAIL_COLOR)

    # ── DATA LOADING ──────────────────────────────────────────────
    def _load_data(self):
        # Seed demo data if DB is empty so analytics always shows something
        if not self.db.get_runs():
            self.db.seed_demo_data()

        boards = ["All Boards"] + self.db.get_board_names()
        self.board_menu.configure(values=boards)
        if self._board_filter.get() not in boards:
            self._board_filter.set("All Boards")

        board = None if self._board_filter.get() == "All Boards" \
                else self._board_filter.get()
        runs      = self.db.get_runs(board_name=board, limit=50)
        trend     = self.db.get_pass_rate_trend(board_name=board, limit=20)
        fail_freq = self.db.get_failure_frequency(board_name=board)
        board_cmp = self.db.get_board_comparison()

        self._render_kpis(runs)
        self._render_trend(trend)
        self._render_fail_freq(fail_freq)
        self._render_board_comparison(board_cmp)
        self._render_status_pie(runs)
        self._render_runs_table(runs)

    def _on_filter_change(self, val):
        self._load_data()

    # ── KPI CARDS ─────────────────────────────────────────────────
    def _render_kpis(self, runs):
        for w in self.kpi_frame.winfo_children():
            w.destroy()
        if not runs:
            ctk.CTkLabel(self.kpi_frame, text="No data — generate some reports first.",
                         text_color=TEXT_MUTED, font=("Segoe UI", 11)).pack()
            return

        avg_rate  = sum(r["pass_rate"] for r in runs) / len(runs)
        min_rate  = min(r["pass_rate"] for r in runs)
        max_rate  = max(r["pass_rate"] for r in runs)
        total_fail= sum(r["failed"] for r in runs)
        pass_runs = sum(1 for r in runs if r["status"] == "PASS")
        fail_runs = len(runs) - pass_runs

        kpis = [
            ("Total Runs",     str(len(runs)),       TEXT,       None),
            ("Avg Pass Rate",  f"{avg_rate:.1f}%",   WARN_COLOR if avg_rate < 98 else PASS_COLOR, None),
            ("Min Pass Rate",  f"{min_rate:.1f}%",   FAIL_COLOR if min_rate < 90 else WARN_COLOR,  None),
            ("Max Pass Rate",  f"{max_rate:.1f}%",   PASS_COLOR, None),
            ("Board Passes",   str(pass_runs),        PASS_COLOR, None),
            ("Board Fails",    str(fail_runs),        FAIL_COLOR if fail_runs > 0 else TEXT_MUTED, None),
            ("Total Failures", str(total_fail),       FAIL_COLOR if total_fail > 0 else TEXT_MUTED, None),
        ]
        for label, val, color, _ in kpis:
            card = ctk.CTkFrame(self.kpi_frame, fg_color=BG_CARD, corner_radius=6,
                                 border_width=1, border_color=BORDER)
            card.pack(side="left", padx=(0, 8), fill="y")
            ctk.CTkLabel(card, text=label, font=("Segoe UI", 9),
                         text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(8,0))
            ctk.CTkLabel(card, text=val, font=("JetBrains Mono", 20, "bold"),
                         text_color=color).pack(anchor="w", padx=10, pady=(0,8))

    # ── CHARTS ────────────────────────────────────────────────────
    def _embed(self, fig, parent):
        for w in parent.winfo_children():
            w.destroy()
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvases.append(canvas)

    def _render_trend(self, trend):
        fig = Figure(figsize=(5.5, 2.8), dpi=90)
        ax  = fig.add_subplot(111)
        fig.patch.set_facecolor(BG_CARD)
        if not trend:
            ax.text(0.5, 0.5, "No historical data yet.\nGenerate reports to build trend.",
                    ha="center", va="center", transform=ax.transAxes,
                    color=TEXT_MUTED, fontsize=9)
        else:
            labels = [r["timestamp"][:10] for r in trend]
            rates  = [r["pass_rate"] for r in trend]
            xs     = np.arange(len(labels))
            ax.fill_between(xs, rates, alpha=0.15, color=PURPLE)
            ax.plot(xs, rates, color=PURPLE, linewidth=2, marker="o",
                    markersize=5, markerfacecolor=PURPLE)
            for i, (x, r) in enumerate(zip(xs, rates)):
                color = PASS_COLOR if r >= 98 else FAIL_COLOR
                ax.plot(x, r, "o", color=color, markersize=6, zorder=5)
            ax.axhline(98, color=WARN_COLOR, linewidth=1,
                        linestyle="--", alpha=0.7, label="98% target")
            ax.set_xticks(xs)
            ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
            ax.set_ylabel("Pass Rate (%)", fontsize=8)
            ax.set_ylim(max(0, min(rates) - 3), 101)
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
            ax.legend(fontsize=7, framealpha=0, labelcolor=WARN_COLOR)
            ax.grid(True)
        fig.tight_layout()
        self._embed(fig, self.trend_card)

    def _render_fail_freq(self, fail_freq):
        fig = Figure(figsize=(5.5, 2.8), dpi=90)
        ax  = fig.add_subplot(111)
        fig.patch.set_facecolor(BG_CARD)
        if not fail_freq:
            ax.text(0.5, 0.5, "No failures recorded.",
                    ha="center", va="center", transform=ax.transAxes,
                    color=PASS_COLOR, fontsize=10)
        else:
            names  = [f["ref"] for f in fail_freq[:8]]
            counts = [f["fail_count"] for f in fail_freq[:8]]
            colors = [FAIL_COLOR] * len(names)
            bars = ax.barh(names, counts, color=colors, alpha=0.85, height=0.55)
            ax.bar_label(bars, padding=3, fontsize=8, color=TEXT_MUTED)
            ax.set_xlabel("Failure Count", fontsize=8)
            ax.invert_yaxis()
            ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        self._embed(fig, self.failfreq_card)

    def _render_board_comparison(self, board_cmp):
        fig = Figure(figsize=(5.5, 2.8), dpi=90)
        ax  = fig.add_subplot(111)
        fig.patch.set_facecolor(BG_CARD)
        if not board_cmp:
            ax.text(0.5, 0.5, "No data yet.", ha="center", va="center",
                    transform=ax.transAxes, color=TEXT_MUTED, fontsize=9)
        else:
            names    = [b["board_name"] for b in board_cmp]
            avg_rates= [b["avg_rate"] for b in board_cmp]
            colors   = [PASS_COLOR if r >= 98 else WARN_COLOR if r >= 92 else FAIL_COLOR
                        for r in avg_rates]
            bars = ax.bar(names, avg_rates, color=colors, alpha=0.8, width=0.5)
            ax.axhline(98, color=WARN_COLOR, linewidth=1, linestyle="--", alpha=0.7)
            ax.bar_label(bars, fmt="%.1f%%", padding=2, fontsize=8, color=TEXT_MUTED)
            ax.set_ylabel("Avg Pass Rate (%)", fontsize=8)
            ax.set_ylim(0, 105)
            ax.tick_params(axis="x", labelsize=7, rotation=10)
            ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        self._embed(fig, self.boardcomp_card)

    def _render_status_pie(self, runs):
        fig = Figure(figsize=(5.5, 2.8), dpi=90)
        ax  = fig.add_subplot(111)
        fig.patch.set_facecolor(BG_CARD)
        if not runs:
            ax.text(0.5, 0.5, "No data yet.", ha="center", va="center",
                    transform=ax.transAxes, color=TEXT_MUTED, fontsize=9)
        else:
            pass_c = sum(1 for r in runs if r["status"] == "PASS")
            fail_c = len(runs) - pass_c
            sizes  = [x for x in [pass_c, fail_c] if x > 0]
            clrs   = [c for c, x in [(PASS_COLOR, pass_c), (FAIL_COLOR, fail_c)] if x > 0]
            labels = [l for l, x in [(f"PASS ({pass_c})", pass_c), (f"FAIL ({fail_c})", fail_c)] if x > 0]
            wedges, texts = ax.pie(sizes, colors=clrs, startangle=90,
                                    labels=labels,
                                    wedgeprops=dict(width=0.5, edgecolor=BG_CARD, linewidth=2))
            for t in texts:
                t.set_fontsize(9)
                t.set_color(TEXT_MUTED)
            ax.set_title(f"{len(runs)} total runs", fontsize=9, color=TEXT_MUTED, pad=4)
        fig.tight_layout()
        self._embed(fig, self.status_card)

    # ── RUNS TABLE ────────────────────────────────────────────────
    def _render_runs_table(self, runs):
        for row in self.runs_tv.get_children():
            self.runs_tv.delete(row)
        for r in runs:
            tag = "pass" if r["status"] == "PASS" else "fail"
            ts  = r["timestamp"][:19] if r["timestamp"] else "—"
            self.runs_tv.insert("", "end", values=(
                r["id"], r["board_name"], r["serial"], ts,
                r["total"], r["passed"], r["failed"],
                f"{r['pass_rate']:.1f}%", r["status"]
            ), tags=(tag,))

    # ── CLOSE ─────────────────────────────────────────────────────
    def _on_close(self):
        plt.close("all")
        self.destroy()
