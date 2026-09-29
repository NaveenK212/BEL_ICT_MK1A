"""
ICT Report Analyzer  v7.0
Auto-watch folder · Dashboard · Search · Reports
"""
import os, datetime, threading, shutil, zipfile
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from ict_parser     import ICTParser
from db_manager     import DBManager
from report_generator import ReportGenerator
from analytics_window import AnalyticsWindow
from file_watcher   import FileWatcher
from config         import Config

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Colours — BEL / Tejas Defence Avionics ────────────────────────
BG  = "#0a1929"; S1 = "#0d2137"; S2 = "#112a45"; S3 = "#163354"
BD  = "#1e4976"; BD2= "#2a5f8f"; TXT= "#e3edf7"; MUT= "#6e96bf"
DIM = "#3d6a96"; PASS="#00e676"; FAIL="#ff1744"; WARN="#ffab00"
INFO= "#00bcd4"; PUR = "#7c4dff"
PBG = "#0a3320"; FBG = "#3d0a14"; WBG = "#3d2e00"; IBG = "#003545"

plt.rcParams.update({
    "figure.facecolor":S2,"axes.facecolor":S3,"axes.edgecolor":BD,
    "axes.labelcolor":MUT,"xtick.color":MUT,"ytick.color":MUT,
    "text.color":TXT,"grid.color":BD,"grid.linestyle":"--","grid.alpha":.45,
    "font.family":"monospace","font.size":10,
    "axes.spines.top":False,"axes.spines.right":False,
})


# ── CHART POPUP ───────────────────────────────────────────────────
class ChartPopup(ctk.CTkToplevel):
    def __init__(self, parent, title, render_fn, figsize=(9,6)):
        super().__init__(parent)
        self.title(f"  {title}")
        self.geometry("960x660"); self.minsize(700,500)
        self.configure(fg_color=BG)
        self.transient(parent); self.lift()
        self.focus_force(); self.attributes("-topmost", True)
        hdr = ctk.CTkFrame(self, fg_color=S2, corner_radius=0, height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"  {title}",
                     font=("Segoe UI",13,"bold"), text_color=INFO).pack(side="left",padx=16)
        ctk.CTkButton(hdr, text="✕  Close", width=90, height=30,
                       fg_color=S3, hover_color=FBG, border_color=BD, border_width=1,
                       font=("Segoe UI",10), text_color=MUT,
                       command=self.destroy).pack(side="right", padx=14)
        fig = Figure(figsize=figsize, dpi=100)
        fig.patch.set_facecolor(S2)
        render_fn(fig)
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        tb = NavigationToolbar2Tk(canvas, self, pack_toolbar=False)
        tb.config(background=S3); tb.pack(side="bottom", fill="x", padx=10, pady=(0,6))
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(8,0))


# ── METRIC CARD ───────────────────────────────────────────────────
class KPICard(ctk.CTkFrame):
    def __init__(self, parent, label, value="——", color=TXT, sub="", **kw):
        super().__init__(parent, fg_color=S2, corner_radius=10,
                         border_width=1, border_color=BD, **kw)
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=14, pady=12)
        ctk.CTkLabel(inner, text=label, font=("Segoe UI",10,"bold"),
                     text_color=MUT).pack()
        self._v = ctk.CTkLabel(inner, text=str(value),
                                font=("Segoe UI",22,"bold"), text_color=color)
        self._v.pack(pady=(3,0))
        self._s = ctk.CTkLabel(inner, text=str(sub),
                                font=("Segoe UI",9), text_color=DIM)
        self._s.pack()

    def update(self, value, color=None, sub=None):
        self._v.configure(text=str(value), text_color=color or TXT)
        if sub is not None: self._s.configure(text=str(sub))


# ── CONSOLE ───────────────────────────────────────────────────────
class ConsoleFrame(ctk.CTkFrame):
    TAGS = {"ok":PASS,"err":FAIL,"warn":WARN,"info":INFO,"ts":DIM,"dim":MUT}
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="#061220", corner_radius=0, **kw)
        hdr = ctk.CTkFrame(self, fg_color=S2, corner_radius=0, height=30)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  ● OUTPUT CONSOLE",
                     font=("Segoe UI",9,"bold"), text_color=MUT, anchor="w").pack(side="left",pady=5)
        self._st = ctk.CTkLabel(hdr, text="idle", font=("Courier New",9), text_color=MUT)
        self._st.pack(side="right", padx=12)
        self.txt = tk.Text(self, bg="#061220", fg=MUT, font=("Courier New",11),
                           relief="flat", wrap="word", state="disabled",
                           padx=12, pady=4, spacing1=2, spacing3=2,
                           selectbackground=S3, insertbackground=INFO)
        sb = ctk.CTkScrollbar(self, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.txt.pack(fill="both", expand=True)
        for tag, fg in self.TAGS.items():
            self.txt.tag_config(tag, foreground=fg)

    def log(self, msg, tag="dim"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt.configure(state="normal")
        self.txt.insert("end", f"[{ts}]  ", "ts")
        self.txt.insert("end", msg+"\n", tag)
        self.txt.see("end"); self.txt.configure(state="disabled")

    def clear(self):
        self.txt.configure(state="normal"); self.txt.delete("1.0","end")
        self.txt.configure(state="disabled")

    def set_status(self, t, c=MUT): self._st.configure(text=t, text_color=c)


# ── TTK theme (call once) ─────────────────────────────────────────
_ttk_init_done = False
def _init_ttk_theme():
    global _ttk_init_done
    if _ttk_init_done: return
    s = ttk.Style(); s.theme_use("default")
    _ttk_init_done = True

# ── TABLES PANEL ──────────────────────────────────────────────────
class TablesPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        _init_ttk_theme()
        s = ttk.Style()
        s.configure("ICT.Treeview", background=S3, fieldbackground=S3,
                    foreground=TXT, rowheight=38, font=("Segoe UI",12))
        s.configure("ICT.Treeview.Heading", background=S2, foreground=INFO,
                    font=("Segoe UI",11,"bold"), relief="flat", padding=(12,10))
        s.map("ICT.Treeview", background=[("selected",S1)])
        s.layout("ICT.Treeview",[("ICT.Treeview.treearea",{"sticky":"nswe"})])
        self.tabs = ctk.CTkTabview(self, fg_color=S2,
            segmented_button_fg_color=S3, segmented_button_selected_color=INFO,
            segmented_button_selected_hover_color="#0097a7",
            segmented_button_unselected_color=S3,
            segmented_button_unselected_hover_color=BD, text_color=TXT)
        self.tabs.pack(fill="both", expand=True)
        self.tv_comp  = self._tab("Component Results",
            ["Ref","Type","Nominal","Measured","Deviation","Status"],
            [100,140,160,160,140,110])
        self.tv_fail  = self._tab("Failed Components",
            ["Ref","Type","Nominal","Measured","Deviation","Limit","Note"],
            [100,130,140,140,120,120,300])
        self.tv_power = self._tab("Power Supply",
            ["Rail","Nominal","Measured","Deviation","Ripple","Status"],
            [110,150,150,130,130,110])

    def _tab(self, name, cols, widths):
        tab = self.tabs.add(name)
        f = tk.Frame(tab, bg=BG); f.pack(fill="both", expand=True)
        sby = ttk.Scrollbar(f, orient="vertical")
        sbx = ttk.Scrollbar(f, orient="horizontal")
        tv  = ttk.Treeview(f, columns=cols, show="headings", style="ICT.Treeview",
                            yscrollcommand=sby.set, xscrollcommand=sbx.set)
        sby.config(command=tv.yview); sbx.config(command=tv.xview)
        sby.pack(side="right",fill="y"); sbx.pack(side="bottom",fill="x")
        tv.pack(fill="both", expand=True)
        for col, w in zip(cols, widths):
            tv.heading(col, text=col); tv.column(col, width=w, anchor="w", minwidth=60)
        tv.tag_configure("pass", foreground=PASS)
        tv.tag_configure("fail", foreground=FAIL)
        return tv

    def _clear(self):
        for tv in (self.tv_comp, self.tv_fail, self.tv_power):
            for r in tv.get_children(): tv.delete(r)

    def populate(self, data):
        self._clear()
        for c in data.get("components",[]):
            self.tv_comp.insert("","end", values=(
                c["ref"],c["type"],c.get("nominal","—"),c.get("measured","—"),
                c.get("deviation","—"),c["status"]),
                tags=("pass" if c["status"]=="PASS" else "fail",))
        for c in data.get("failed_detail",[]):
            self.tv_fail.insert("","end", values=(
                c["ref"],c["type"],c.get("nominal","—"),c.get("measured","—"),
                c.get("deviation","—"),c.get("limit","—"),c.get("note","—")),
                tags=("fail",))
        for p in data.get("power_rails",[]):
            self.tv_power.insert("","end", values=(
                p["rail"],p["nominal"],p["measured"],
                p.get("deviation","—"),p.get("ripple","—"),p["status"]),
                tags=("pass" if p["status"]=="PASS" else "fail",))


# ── DASHBOARD PAGE ────────────────────────────────────────────────
class DashboardPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, db, open_chart_fn, **kw):
        super().__init__(parent, fg_color=BG, scrollbar_button_color=BD, **kw)
        self.db = db
        self._open_chart = open_chart_fn
        self._canvases   = []
        self._build()

    def _build(self):
        # Section header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16,4))
        ctk.CTkLabel(hdr, text="DASHBOARD", font=("Segoe UI",11,"bold"),
                     text_color=INFO).pack(side="left")
        self._refresh_btn = ctk.CTkButton(
            hdr, text="↻  Refresh", width=90, height=28,
            fg_color=S3, hover_color=S1, border_color=BD, border_width=1,
            font=("Segoe UI",10), text_color=MUT,
            command=self.refresh)
        self._refresh_btn.pack(side="right")

        # KPI cards row
        self._kpi_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._kpi_frame.pack(fill="x", padx=16, pady=(0,8))

        # Charts grid (2 columns)
        self._chart_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._chart_frame.pack(fill="both", expand=True, padx=16, pady=4)
        self._chart_frame.columnconfigure(0, weight=1)
        self._chart_frame.columnconfigure(1, weight=1)

        # Recent runs table
        ctk.CTkLabel(self, text="  RECENT RUNS",
                     font=("Segoe UI",9,"bold"), text_color=MUT,
                     anchor="w").pack(fill="x", padx=16, pady=(8,2))
        self._runs_frame = ctk.CTkFrame(self, fg_color=S2, corner_radius=6,
                                         border_width=1, border_color=BD)
        self._runs_frame.pack(fill="x", padx=16, pady=(0,16))
        self._build_runs_table()

        self.refresh()

    def _build_runs_table(self):
        _init_ttk_theme()
        s = ttk.Style()
        s.configure("Dash.Treeview", background=S3, fieldbackground=S3,
                    foreground=TXT, rowheight=32, font=("Segoe UI",12))
        s.configure("Dash.Treeview.Heading", background=S2, foreground=INFO,
                    font=("Segoe UI",11,"bold"), relief="flat")
        s.map("Dash.Treeview", background=[("selected",S1)])
        s.layout("Dash.Treeview",[("Dash.Treeview.treearea",{"sticky":"nswe"})])
        cols = ("Board","Serial","Date","Components","Pass","Fail","Rate","Status")
        f = tk.Frame(self._runs_frame, bg=BG, height=220)
        f.pack(fill="x", padx=8, pady=8); f.pack_propagate(False)
        sby = ttk.Scrollbar(f, orient="vertical")
        self._runs_tv = ttk.Treeview(f, columns=cols, show="headings",
                                      style="Dash.Treeview", yscrollcommand=sby.set,
                                      height=7)
        sby.config(command=self._runs_tv.yview)
        sby.pack(side="right", fill="y"); self._runs_tv.pack(fill="both", expand=True)
        for col, w in zip(cols,[180,160,140,100,70,60,80,80]):
            self._runs_tv.heading(col, text=col)
            self._runs_tv.column(col, width=w, anchor="w", minwidth=50)
        self._runs_tv.tag_configure("pass", foreground=PASS)
        self._runs_tv.tag_configure("fail", foreground=FAIL)

    def refresh(self):
        stats = self.db.get_dashboard_stats()
        trend = self.db.get_pass_rate_trend(limit=20)
        board_cmp = self.db.get_board_comparison()
        fail_freq = self.db.get_failure_frequency()

        self._render_kpis(stats)
        self._render_charts(stats, trend, board_cmp, fail_freq)
        self._render_recent(stats["recent"])

    def _render_kpis(self, s):
        for w in self._kpi_frame.winfo_children(): w.destroy()
        ar = s["avg_rate"]
        kpis = [
            ("Total Runs",     str(s["total_runs"]),  INFO,  "processed"),
            ("Boards",         str(s["boards"]),       TXT,   "unique"),
            ("Pass Runs",      str(s["pass_runs"]),    PASS,  "boards passed"),
            ("Fail Runs",      str(s["fail_runs"]),    FAIL if s["fail_runs"]>0 else MUT, "boards failed"),
            ("Avg Pass Rate",  f"{ar:.1f}%",           PASS if ar>=98 else WARN if ar>=90 else FAIL, "across all runs"),
            ("Total Comps",    str(s["total_comp"]),   TXT,   "tested"),
            ("Total Failures", str(s["total_fail_comp"]), FAIL if s["total_fail_comp"]>0 else PASS, "components"),
        ]
        for label, val, color, sub in kpis:
            c = KPICard(self._kpi_frame, label, val, color, sub, width=175)
            c.pack(side="left", padx=(0,10), fill="y")

    def _embed_chart(self, fig, row, col, title):
        card = ctk.CTkFrame(self._chart_frame, fg_color=S2, corner_radius=6,
                             border_width=1, border_color=BD)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(card, text=f"  {title}",
                     font=("Segoe UI",9,"bold"), text_color=MUT,
                     anchor="w").pack(fill="x", pady=(8,2), padx=4)
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=(0,8))
        self._canvases.append(canvas)

    def _render_charts(self, stats, trend, board_cmp, fail_freq):
        for w in self._chart_frame.winfo_children(): w.destroy()
        for c in self._canvases: plt.close("all")
        self._canvases = []

        if stats["total_runs"] == 0:
            ctk.CTkLabel(self._chart_frame,
                         text="No data yet — generate some reports to see charts here.",
                         font=("Segoe UI",12), text_color=MUT).grid(
                row=0, column=0, columnspan=2, pady=40)
            return

        # Chart 1: Pass rate trend
        fig1, ax1 = plt.subplots(figsize=(6,3)); fig1.patch.set_facecolor(S2)
        if trend:
            xs  = range(len(trend))
            rts = [r["pass_rate"] for r in trend]
            ax1.fill_between(xs, rts, alpha=0.15, color=PUR)
            ax1.plot(xs, rts, color=PUR, linewidth=2, marker="o",
                     markersize=5, markerfacecolor=PUR)
            for i,(x,r) in enumerate(zip(xs,rts)):
                ax1.plot(x, r, "o", color=PASS if r>=98 else FAIL, markersize=6, zorder=5)
            ax1.axhline(98, color=WARN, linewidth=1, linestyle="--", alpha=0.7)
            lbs = [r["timestamp"][:10] for r in trend]
            step = max(1, len(lbs)//6)
            ax1.set_xticks(list(xs)[::step])
            ax1.set_xticklabels(lbs[::step], rotation=30, ha="right", fontsize=7)
            ax1.set_ylabel("Pass Rate (%)", fontsize=8)
            ax1.set_ylim(max(0,min(rts)-5), 103)
            ax1.grid(True)
        ax1.set_title("Pass Rate Trend", fontsize=10, color=TXT, pad=6)
        fig1.tight_layout()
        self._embed_chart(fig1, 0, 0, "Pass Rate Trend")

        # Chart 2: Board comparison
        fig2, ax2 = plt.subplots(figsize=(6,3)); fig2.patch.set_facecolor(S2)
        if board_cmp:
            names = [b["board_name"][:14] for b in board_cmp[:8]]
            rates = [b["avg_rate"] for b in board_cmp[:8]]
            clrs  = [PASS if r>=98 else WARN if r>=92 else FAIL for r in rates]
            bars  = ax2.barh(names, rates, color=clrs, alpha=0.85, height=0.5)
            ax2.axvline(98, color=WARN, linewidth=1, linestyle="--", alpha=0.7)
            ax2.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=8, color=MUT)
            ax2.set_xlim(0,106); ax2.tick_params(labelsize=8)
            ax2.grid(axis="x", alpha=0.3)
        ax2.set_title("Board Avg Pass Rate", fontsize=10, color=TXT, pad=6)
        fig2.tight_layout()
        self._embed_chart(fig2, 0, 1, "Board Avg Pass Rate")

        # Chart 3: Run pass/fail donut
        fig3, ax3 = plt.subplots(figsize=(6,3)); fig3.patch.set_facecolor(S2)
        p = stats["pass_runs"]; f = stats["fail_runs"]
        if p+f > 0:
            sizes = [p,f] if f>0 else [p]
            clrs  = [PASS,FAIL] if f>0 else [PASS]
            ax3.pie(sizes, colors=clrs, startangle=90,
                    wedgeprops=dict(width=0.48, edgecolor=BG, linewidth=2))
            rt = round(p/(p+f)*100,1)
            ax3.text(0, 0.08, f"{rt}%", ha="center", va="center",
                     fontsize=18, fontweight="bold", color=TXT, fontfamily="monospace")
            ax3.text(0,-0.14, f"{p}P / {f}F", ha="center", va="center",
                     fontsize=9, color=MUT)
        ax3.set_title("Board Run Overview", fontsize=10, color=TXT, pad=6)
        ax3.axis("equal"); fig3.tight_layout()
        self._embed_chart(fig3, 1, 0, "Board Run Overview")

        # Chart 4: Top failing components
        fig4, ax4 = plt.subplots(figsize=(6,3)); fig4.patch.set_facecolor(S2)
        if fail_freq:
            names = [f["ref"] for f in fail_freq[:8]]
            cnts  = [f["fail_count"] for f in fail_freq[:8]]
            bars  = ax4.barh(names, cnts, color=FAIL, alpha=0.82, height=0.5)
            ax4.bar_label(bars, padding=3, fontsize=8, color=MUT)
            ax4.invert_yaxis(); ax4.tick_params(labelsize=8)
            ax4.grid(axis="x", alpha=0.3)
        else:
            ax4.text(0.5,0.5,"No failures recorded", ha="center", va="center",
                     transform=ax4.transAxes, color=PASS, fontsize=11)
        ax4.set_title("Top Failing Components", fontsize=10, color=TXT, pad=6)
        fig4.tight_layout()
        self._embed_chart(fig4, 1, 1, "Top Failing Components")

    def _render_recent(self, runs):
        for r in self._runs_tv.get_children(): self._runs_tv.delete(r)
        for r in runs:
            tag = "pass" if r["status"]=="PASS" else "fail"
            self._runs_tv.insert("","end", values=(
                r["board_name"], r["serial"],
                r["timestamp"][:16] if r["timestamp"] else "—",
                r["total"], r["passed"], r["failed"],
                f"{r['pass_rate']:.1f}%", r["status"]),
                tags=(tag,))


# ── SEARCH PAGE ───────────────────────────────────────────────────
class SearchPage(ctk.CTkFrame):
    def __init__(self, parent, db, on_view_report, **kw):
        super().__init__(parent, fg_color=BG, corner_radius=0, **kw)
        self.db = db
        self._on_view = on_view_report
        self._build()

    def _build(self):
        # Search bar
        bar = ctk.CTkFrame(self, fg_color=S2, corner_radius=0,
                            border_width=1, border_color=BD, height=56)
        bar.pack(fill="x"); bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="  SEARCH",
                     font=("Segoe UI",11,"bold"), text_color=INFO).pack(side="left", padx=14)
        self._q = tk.StringVar()
        self._q.trace_add("write", lambda *_: self._search())
        entry = ctk.CTkEntry(bar, textvariable=self._q, width=400, height=34,
                              font=("Courier New",12), fg_color=S3, text_color=TXT,
                              border_color=BD, placeholder_text="Type board name, serial, or status...")
        entry.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="⌫  Clear", width=80, height=34,
                       fg_color=S3, hover_color=S1, border_color=BD, border_width=1,
                       font=("Segoe UI",10), text_color=MUT,
                       command=lambda: self._q.set("")).pack(side="left", padx=4)
        self._count_lbl = ctk.CTkLabel(bar, text="",
                                        font=("Segoe UI",9), text_color=MUT)
        self._count_lbl.pack(side="right", padx=14)

        # Results table
        _init_ttk_theme()
        s = ttk.Style()
        s.configure("Srch.Treeview", background=S3, fieldbackground=S3,
                    foreground=TXT, rowheight=34, font=("Segoe UI",12))
        s.configure("Srch.Treeview.Heading", background=S2, foreground=INFO,
                    font=("Segoe UI",11,"bold"), relief="flat", padding=(8,6))
        s.map("Srch.Treeview", background=[("selected",S1)])
        s.layout("Srch.Treeview",[("Srch.Treeview.treearea",{"sticky":"nswe"})])

        cols = ("ID","Board","Serial","Date","Total","Pass","Fail","Rate","Status")
        f = tk.Frame(self, bg=BG); f.pack(fill="both", expand=True, padx=12, pady=8)
        sby = ttk.Scrollbar(f, orient="vertical")
        self._tv = ttk.Treeview(f, columns=cols, show="headings",
                                 style="Srch.Treeview", yscrollcommand=sby.set)
        sby.config(command=self._tv.yview)
        sby.pack(side="right", fill="y"); self._tv.pack(fill="both", expand=True)
        for col, w in zip(cols,[50,180,160,140,70,60,60,80,80]):
            self._tv.heading(col, text=col)
            self._tv.column(col, width=w, anchor="w", minwidth=40)
        self._tv.tag_configure("pass", foreground=PASS)
        self._tv.tag_configure("fail", foreground=FAIL)
        self._tv.bind("<Double-1>", self._on_double_click)

        ctk.CTkLabel(self, text="Double-click a row to view full report details",
                     font=("Segoe UI",9), text_color=DIM).pack(pady=(0,6))

        self._search()  # load all on init

    def _search(self):
        q = self._q.get().strip()
        if q:
            results = self.db.search(q, limit=200)
        else:
            results = self.db.get_runs(limit=200)
        for r in self._tv.get_children(): self._tv.delete(r)
        for r in results:
            tag = "pass" if r["status"]=="PASS" else "fail"
            self._tv.insert("","end", values=(
                r["id"], r["board_name"], r["serial"],
                r["timestamp"][:16] if r["timestamp"] else "—",
                r["total"], r["passed"], r["failed"],
                f"{r['pass_rate']:.1f}%", r["status"]),
                tags=(tag,))
        self._count_lbl.configure(text=f"{len(results)} result(s)")

    def _on_double_click(self, event):
        sel = self._tv.selection()
        if not sel: return
        row = self._tv.item(sel[0])["values"]
        run_id = int(row[0])
        self._on_view(run_id)

    def refresh(self):
        self._search()


# ── RUN DETAIL POPUP ─────────────────────────────────────────────
class RunDetailPopup(ctk.CTkToplevel):
    def __init__(self, parent, run_id, db):
        super().__init__(parent)
        detail = db.get_run_detail(run_id)
        if not detail:
            self.destroy(); return
        r = detail["run"]
        self.title(f"  {r['board_name']}  ·  {r['serial']}")
        self.geometry("1100x700"); self.configure(fg_color=BG)
        self.transient(parent); self.lift()
        self.focus_force(); self.attributes("-topmost", True)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=S2, corner_radius=0, height=50)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        sc = PASS if r["status"]=="PASS" else FAIL
        ctk.CTkLabel(hdr, text=f"  {r['board_name']}",
                     font=("Segoe UI",13,"bold"), text_color=TXT).pack(side="left",padx=14)
        ctk.CTkLabel(hdr, text=f"Serial: {r['serial']}",
                     font=("Courier New",11), text_color=MUT).pack(side="left",padx=8)
        ctk.CTkLabel(hdr, text=r["status"],
                     font=("Courier New",14,"bold"), text_color=sc).pack(side="left",padx=16)
        ctk.CTkLabel(hdr, text=f"{r['pass_rate']:.1f}% pass  ·  {r['passed']}P/{r['failed']}F/{r['total']} total",
                     font=("Segoe UI",10), text_color=MUT).pack(side="left",padx=8)
        ctk.CTkButton(hdr, text="✕  Close", width=90, height=32,
                       fg_color=S3, hover_color=FBG, border_color=BD, border_width=1,
                       font=("Segoe UI",10), text_color=MUT,
                       command=self.destroy).pack(side="right", padx=14)

        # Fake data object for TablesPanel
        data = {
            "components": detail["components"],
            "failed_detail": [c for c in detail["components"] if c["status"]=="FAIL"],
            "power_rails": detail["power_rails"],
        }
        tp = TablesPanel(self)
        tp.pack(fill="both", expand=True)
        tp.populate(data)


# ── WATCHER STATUS BAR ────────────────────────────────────────────
class WatcherBar(ctk.CTkFrame):
    def __init__(self, parent, cfg, on_set_folder, **kw):
        super().__init__(parent, fg_color=S1, corner_radius=0,
                         border_width=1, border_color=BD, height=38, **kw)
        self.pack_propagate(False)
        self._dot = ctk.CTkLabel(self, text="●", font=("Segoe UI",12),
                                  text_color=DIM)
        self._dot.pack(side="left", padx=(12,4))
        ctk.CTkLabel(self, text="WATCHING:", font=("Segoe UI",9,"bold"),
                     text_color=MUT).pack(side="left", padx=(0,4))
        self._folder_lbl = ctk.CTkLabel(self, text=cfg.watch_folder,
                                         font=("Courier New",10), text_color=TXT)
        self._folder_lbl.pack(side="left", padx=4)
        ctk.CTkButton(self, text="Change Folder", width=110, height=26,
                       fg_color=S3, hover_color=S1, border_color=BD, border_width=1,
                       font=("Segoe UI",9), text_color=MUT,
                       command=on_set_folder).pack(side="left", padx=6)
        self._status = ctk.CTkLabel(self, text="",
                                     font=("Segoe UI",9), text_color=MUT)
        self._status.pack(side="right", padx=14)

    def set_active(self, active: bool):
        self._dot.configure(text_color=PASS if active else DIM)

    def set_status(self, text, color=MUT):
        self._status.configure(text=text, text_color=color)

    def set_folder(self, path):
        self._folder_lbl.configure(text=path)


# ── MAIN APPLICATION ──────────────────────────────────────────────
class ICTApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ICT Report Analyzer  v7.1")
        self.geometry("1500x940"); self.minsize(1100,720)
        self.configure(fg_color=BG)

        self.cfg      = Config()
        self.db       = DBManager()
        self.parser   = ICTParser()
        self.reporter = ReportGenerator()
        self._data    = None  # set when user opens a run detail

        self._build()

        # Start file watcher
        self.watcher = FileWatcher(self.db, self.cfg,
                                    on_new_file=self._on_new_file)
        self.watcher.start()

    # ── BUILD UI ──────────────────────────────────────────────────
    def _build(self):
        self._topbar()
        self._watcher_bar()
        self._nav_tabs()

    def _topbar(self):
        bar = ctk.CTkFrame(self, fg_color=S2, corner_radius=0,
                            border_width=1, border_color=BD, height=56)
        bar.pack(fill="x"); bar.pack_propagate(False)

        logo = ctk.CTkFrame(bar, fg_color=INFO, corner_radius=6, width=36, height=36)
        logo.pack(side="left", padx=(16,8), pady=10); logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="ICT", font=("Courier New",10,"bold"),
                     text_color="white").place(relx=.5,rely=.5,anchor="center")
        ctk.CTkLabel(bar, text="Report Analyzer",
                     font=("Segoe UI",14,"bold"), text_color=TXT).pack(side="left",padx=(0,16))

        sep = ctk.CTkFrame(bar, fg_color=BD, width=1, height=30)
        sep.pack(side="left", padx=10, pady=13)

        ctk.CTkLabel(bar, text="Auto-processing active",
                     font=("Segoe UI",10), text_color=MUT).pack(side="left", padx=8)

        # Right buttons
        self._export_btn = ctk.CTkButton(
            bar, text="⬇  Export XLSX", width=130, height=34,
            fg_color=S3, hover_color=BG, border_color=BD2, border_width=1,
            font=("Segoe UI",11), command=self._export_excel, state="disabled")
        self._export_btn.pack(side="right", padx=(0,14))

        self._pdf_btn = ctk.CTkButton(
            bar, text="📄  Save PDF", width=120, height=34,
            fg_color=WBG, hover_color="#4d3a00",
            border_color=WARN, border_width=1,
            font=("Segoe UI",11), text_color=WARN,
            command=self._save_pdf, state="disabled")
        self._pdf_btn.pack(side="right", padx=4)

        ctk.CTkButton(
            bar, text="⚡  Analytics", width=120, height=34,
            fg_color="#2a1050", hover_color="#5c35cc",
            border_color=PUR, border_width=1,
            font=("Segoe UI",11), text_color=PUR,
            command=lambda: AnalyticsWindow(self, self.db)).pack(side="right",padx=4)

        ctk.CTkButton(
            bar, text="🔒  Reset", width=100, height=34,
            fg_color=FBG, hover_color="#5a0f1a",
            border_color=FAIL, border_width=1,
            font=("Segoe UI",11), text_color=FAIL,
            command=self._reset_data).pack(side="right",padx=4)

    def _watcher_bar(self):
        self._wbar = WatcherBar(self, self.cfg,
                                 on_set_folder=self._set_watch_folder)
        self._wbar.pack(fill="x")

    def _nav_tabs(self):
        tabs = ctk.CTkFrame(self, fg_color=S1, corner_radius=0,
                             border_width=1, border_color=BD, height=40)
        tabs.pack(fill="x"); tabs.pack_propagate(False)

        self._pages = {}
        self._tab_btns = {}
        self._active_page = None

        container = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        container.pack(fill="both", expand=True)

        self._pages["dashboard"] = DashboardPage(
            container, self.db, open_chart_fn=self._open_chart_fn)
        self._pages["reports"]   = self._build_reports_page(container)
        self._pages["search"]    = SearchPage(
            container, self.db, on_view_report=self._view_run)

        for key, label in [("dashboard","📊  Dashboard"),
                            ("reports",  "📋  Reports"),
                            ("search",   "🔍  Search")]:
            btn = ctk.CTkButton(
                tabs, text=label, width=0, height=38,
                fg_color="transparent", hover_color=S2,
                border_width=0, font=("Segoe UI",11),
                text_color=MUT, corner_radius=0,
                command=lambda k=key: self._show_page(k))
            btn.pack(side="left", padx=2)
            self._tab_btns[key] = btn

        self._show_page("dashboard")

    def _build_reports_page(self, parent):
        """Reports page: all processed runs with filter."""
        frame = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        hdr = ctk.CTkFrame(frame, fg_color=S2, corner_radius=0,
                            border_width=1, border_color=BD, height=48)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  ALL REPORTS",
                     font=("Segoe UI",11,"bold"), text_color=INFO).pack(side="left",padx=14)
        self._reports_count = ctk.CTkLabel(hdr, text="",
                                            font=("Segoe UI",9), text_color=MUT)
        self._reports_count.pack(side="right", padx=14)
        ctk.CTkButton(hdr, text="↻  Refresh", width=90, height=30,
                       fg_color=S3, hover_color=S1, border_color=BD, border_width=1,
                       font=("Segoe UI",10), text_color=MUT,
                       command=self._refresh_reports).pack(side="right",padx=4)

        # Filter bar
        fbar = ctk.CTkFrame(frame, fg_color=S1, corner_radius=0,
                             border_width=1, border_color=BD, height=40)
        fbar.pack(fill="x"); fbar.pack_propagate(False)
        ctk.CTkLabel(fbar, text="  Filter by board:",
                     font=("Segoe UI",9), text_color=MUT).pack(side="left",padx=8)
        self._filter_var = tk.StringVar(value="All Boards")
        self._filter_menu = ctk.CTkOptionMenu(
            fbar, variable=self._filter_var, values=["All Boards"],
            fg_color=S3, button_color=BD, button_hover_color=S1,
            text_color=TXT, font=("Courier New",10), width=200,
            command=lambda _: self._refresh_reports())
        self._filter_menu.pack(side="left", padx=4)

        # Table
        _init_ttk_theme()
        s = ttk.Style()
        s.configure("Rep.Treeview", background=S3, fieldbackground=S3,
                    foreground=TXT, rowheight=40, font=("Segoe UI",13))
        s.configure("Rep.Treeview.Heading", background=S2, foreground=INFO,
                    font=("Segoe UI",12,"bold"), relief="flat", padding=(10,8))
        s.map("Rep.Treeview", background=[("selected",S1)])
        s.layout("Rep.Treeview",[("Rep.Treeview.treearea",{"sticky":"nswe"})])
        cols = ("ID","Board","Serial","Date","Total","Pass","Fail","Rate","Status","Folder")
        tf = tk.Frame(frame, bg=BG); tf.pack(fill="both", expand=True, padx=8, pady=8)
        sby = ttk.Scrollbar(tf, orient="vertical")
        sbx = ttk.Scrollbar(tf, orient="horizontal")
        self._rep_tv = ttk.Treeview(tf, columns=cols, show="headings",
                                     style="Rep.Treeview",
                                     yscrollcommand=sby.set, xscrollcommand=sbx.set)
        sby.config(command=self._rep_tv.yview)
        sbx.config(command=self._rep_tv.xview)
        sby.pack(side="right",fill="y"); sbx.pack(side="bottom",fill="x")
        self._rep_tv.pack(fill="both", expand=True)
        for col, w in zip(cols,[50,200,180,160,80,70,70,90,90,500]):
            self._rep_tv.heading(col, text=col)
            self._rep_tv.column(col, width=w, anchor="w", minwidth=50)
        self._rep_tv.tag_configure("pass", foreground=PASS)
        self._rep_tv.tag_configure("fail", foreground=FAIL)
        self._rep_tv.bind("<Double-1>", lambda e: self._rep_double_click(e))
        ctk.CTkLabel(frame, text="Double-click a row to view full report",
                     font=("Segoe UI",9), text_color=DIM).pack(pady=(0,4))
        return frame

    def _build_manual_page(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Summary cards
        bar = ctk.CTkFrame(frame, fg_color=S1, corner_radius=0, height=96)
        bar.pack(fill="x"); bar.pack_propagate(False)
        scr = ctk.CTkScrollableFrame(bar, fg_color="transparent",
                                      orientation="horizontal",
                                      height=92, scrollbar_button_color=BD)
        scr.pack(fill="both", expand=True, padx=10, pady=8)
        self._cards = {}
        for label, accent in [("Board",None),("Serial No.",None),("Status",None),
                               ("Components",None),("Passed",PASS),("Failed",FAIL),
                               ("Pass Rate",None),("Test Time",None)]:
            c = self._make_card(scr, label, accent)
            c.pack(side="left", padx=(0,8), fill="y")
            self._cards[label] = c

        # Chart buttons
        cbar = ctk.CTkFrame(frame, fg_color=S2, corner_radius=0,
                             border_width=1, border_color=BD, height=50)
        cbar.pack(fill="x"); cbar.pack_propagate(False)
        ctk.CTkLabel(cbar, text="  CHARTS", font=("Segoe UI",9,"bold"),
                     text_color=MUT).pack(side="left",padx=(14,8))
        ctk.CTkFrame(cbar, fg_color=BD, width=1, height=28).pack(side="left",padx=6,pady=11)
        self._chart_btns = []
        for lbl, key in [("🍩 Pass/Fail","donut"),("🎯 Gauge","gauge"),
                          ("📈 Pareto","pareto"),("📊 Comp Types","comp"),
                          ("📊 Test Types","test"),("⚡ Power Rails","power"),
                          ("📉 Deviations","deviation"),("🔢 Type Pass Rate","typerate")]:
            btn = ctk.CTkButton(cbar, text=lbl, width=0, height=32,
                                 fg_color=S3, hover_color=S1,
                                 border_color=BD, border_width=1,
                                 font=("Segoe UI",10), text_color=MUT,
                                 command=lambda k=key: self._open_chart(k),
                                 state="disabled")
            btn.pack(side="left", padx=3, pady=9)
            self._chart_btns.append(btn)

        # Tables
        self._tables_panel = TablesPanel(frame)
        self._tables_panel.pack(fill="both", expand=True)

        # Insights
        self._ins_bar = self._make_insights(frame)
        self._ins_bar.pack(fill="x")
        self._set_insights([("Run a report to see insights","info")])

        # Console
        self._con = ConsoleFrame(frame, height=130)
        self._con.pack(fill="x", side="bottom")
        self._con.log("ICT Report Analyzer v7.0 ready.")

        return frame

    def _make_card(self, parent, label, accent):
        f = ctk.CTkFrame(parent, fg_color=S2, corner_radius=8,
                          border_width=1, border_color=BD, width=185)
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=10, pady=8)
        ctk.CTkLabel(inner, text=label, font=("Segoe UI",9,"bold"),
                     text_color=MUT).pack()
        lbl = ctk.CTkLabel(inner, text="——",
                            font=("Courier New",13,"bold"),
                            text_color=accent or TXT)
        lbl.pack(pady=(2,0))
        sub = ctk.CTkLabel(inner, text="", font=("Segoe UI",9), text_color=DIM)
        sub.pack()
        f._val_lbl = lbl
        f._sub_lbl = sub
        f._default_color = accent or TXT
        return f

    def _set_card(self, card, value, color=None, sub=""):
        card._val_lbl.configure(text=str(value),
                                  text_color=color or card._default_color)
        card._sub_lbl.configure(text=str(sub))

    def _make_insights(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=S2, corner_radius=0,
                            border_width=1, border_color=BD, height=44)
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="  INSIGHTS", font=("Segoe UI",9,"bold"),
                     text_color=MUT).pack(side="left",padx=(12,8))
        scroll = ctk.CTkScrollableFrame(bar, fg_color="transparent",
                                         orientation="horizontal",
                                         height=38, scrollbar_button_color=BD)
        scroll.pack(side="left", fill="both", expand=True)
        bar._scroll = scroll
        return bar

    def _set_insights(self, items):
        for w in self._ins_bar._scroll.winfo_children(): w.destroy()
        COLOR = {"fail":(FAIL,FBG),"warn":(WARN,WBG),"pass":(PASS,PBG),"info":(INFO,IBG)}
        for text, level in items:
            fg, bg = COLOR.get(level,(MUT,S3))
            chip = ctk.CTkFrame(self._ins_bar._scroll, fg_color=bg,
                                 corner_radius=14, border_width=1, border_color=fg)
            chip.pack(side="left", padx=3, pady=6)
            ctk.CTkLabel(chip, text=text, font=("Segoe UI",10),
                         text_color=fg).pack(padx=10, pady=3)

    def _show_page(self, key):
        if self._active_page:
            self._pages[self._active_page].pack_forget()
            self._tab_btns[self._active_page].configure(
                text_color=MUT, fg_color="transparent")
        self._pages[key].pack(fill="both", expand=True)
        self._tab_btns[key].configure(text_color=INFO, fg_color=S2)
        self._active_page = key
        if key == "dashboard":   self._pages["dashboard"].refresh()
        elif key == "reports":   self._refresh_reports()
        elif key == "search":    self._pages["search"].refresh()

    # ── WATCHER ───────────────────────────────────────────────────
    def _set_watch_folder(self):
        folder = filedialog.askdirectory(title="Select ICT Watch Folder")
        if folder:
            self.cfg.set("watch_folder", folder)
            self._wbar.set_folder(folder)
            # Fully stop old watcher (waits for thread to exit)
            self.watcher.stop()
            # Create new watcher for new folder
            self.watcher = FileWatcher(self.db, self.cfg,
                                        on_new_file=self._on_new_file)
            self.watcher.start()
            self._wbar.set_active(True)
            self._wbar.set_status(f"Watching: {folder}", INFO)
            # Immediate scan of the new folder
            threading.Thread(target=self.watcher.scan_now, daemon=True).start()

    def _scan_now(self):
        self._wbar.set_status("Scanning...", WARN)
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        self.watcher.scan_now()
        self.after(500, lambda: self._wbar.set_status(
            f"Last scan: {datetime.datetime.now().strftime('%H:%M:%S')}", MUT))

    def _on_new_file(self, filepath):
        """Called by FileWatcher for each new file — runs in background thread."""
        import hashlib
        h = hashlib.md5()
        try:
            with open(filepath,"rb") as f: h.update(f.read(65536))
        except Exception: pass
        fhash = h.hexdigest()

        self.after(0, lambda: self._wbar.set_status(
            f"Processing: {os.path.basename(filepath)}", WARN))
        self.after(0, lambda: self._wbar.set_active(True))

        try:
            data = self.parser.parse(filepath)
            run_id = self.db.save_run(data)
            self.db.mark_processed(filepath, fhash)

            s = data["summary"]
            msg = (f"Auto-processed: {os.path.basename(filepath)}  "
                   f"→ {s['board_name']} | {s['serial']} | "
                   f"{s['pass_rate']:.1f}% | {s['status']}")
            self.after(0, lambda: self._wbar.set_status(
                f"✓ {os.path.basename(filepath)} → {s['status']}", 
                PASS if s["status"]=="PASS" else FAIL))

            # If Manual Run page is visible, update it
            if self._active_page == "console_frame":
                self.after(0, lambda: self._con.log(msg, "ok"))
            # Always refresh dashboard/reports/search in background
            self.after(500, self._bg_refresh)

        except Exception as e:
            self.after(0, lambda: self._wbar.set_status(
                f"Error: {os.path.basename(filepath)}", FAIL))

    def _bg_refresh(self):
        if self._active_page == "dashboard":  self._pages["dashboard"].refresh()
        elif self._active_page == "reports":  self._refresh_reports()
        elif self._active_page == "search":   self._pages["search"].refresh()

    # ── MANUAL GENERATE ───────────────────────────────────────────
    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Select ICT Report File",
            filetypes=[("ICT files","*.ict *.txt *.log"),
                       ("CSV","*.csv"),("All","*.*")])
        if path:
            if path.lower().endswith(".db"):
                messagebox.showerror("Wrong File",
                    "That's the database file.\nSelect an ICT .ict/.txt/.log file.")
                return
            self._manual_file = path
            self._filepath.set(path)
            self._gen_btn.configure(state="normal")

    def _generate_manual(self):
        if not hasattr(self,"_manual_file"):
            messagebox.showwarning("No File","Select a file first.")
            return
        self._show_page("console_frame")
        self._gen_btn.configure(state="disabled", text="Processing…")
        self._pdf_btn.configure(state="disabled")
        self._export_btn.configure(state="disabled")
        for b in self._chart_btns: b.configure(state="disabled", text_color=MUT)
        self._con.clear()
        self._con.set_status("running…", INFO)
        threading.Thread(target=self._run_manual, daemon=True).start()

    def _run_manual(self):
        def upd(v): self.after(0, lambda: None)  # progress placeholder
        try:
            self._con.log(f"Reading: {os.path.basename(self._manual_file)}", "info")
            data = self.parser.parse(self._manual_file)
            self._data = data
            self._con.log(f"Format: {data.get('format','Generic')}", "info")
            self._con.log(f"Found {data['summary']['total']} components")
            for m in data.get("parse_log",[]):
                self._con.log(m, "err" if "FAIL" in m else "dim")
            s = data["summary"]
            self._con.log(f"{s['passed']} PASS / {s['failed']} FAIL — {s['pass_rate']:.1f}%",
                           "ok" if s["pass_rate"]>=98 else "warn")
            run_id = self.db.save_run(data)

            import hashlib
            h = hashlib.md5()
            with open(self._manual_file,"rb") as f: h.update(f.read(65536))
            self.db.mark_processed(self._manual_file, h.hexdigest())

            self._con.log(f"Folder: {data.get('run_folder','')}", "ok")
            for ins in data.get("insights",[]): self._con.log(ins, "warn")
            self._con.log(f"✓ Done — {s['status']}",
                           "ok" if s["status"]=="PASS" else "err")
            self._con.set_status("done", PASS if s["status"]=="PASS" else FAIL)
            self.after(0, lambda: self._populate(data))
        except Exception as e:
            self._con.log(f"ERROR: {e}", "err")
            self._con.set_status("error", FAIL)
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._gen_btn.configure(
                state="normal", text="▶  Generate Report"))

    def _populate(self, data):
        s  = data["summary"]
        rt = s["pass_rate"]
        rc = PASS if rt>=98 else WARN if rt>=90 else FAIL
        sc = PASS if s["status"]=="PASS" else FAIL
        self._set_card(self._cards["Board"],       str(s.get("board_name","—")))
        self._set_card(self._cards["Serial No."],  str(s.get("serial","—")))
        self._set_card(self._cards["Status"],      str(s["status"]), sc)
        self._set_card(self._cards["Components"],  str(s["total"]), sub="tested")
        self._set_card(self._cards["Passed"],      str(s["passed"]), PASS)
        self._set_card(self._cards["Failed"],      str(s["failed"]), FAIL if s["failed"]>0 else PASS)
        self._set_card(self._cards["Pass Rate"],   f"{rt:.1f}%", rc,
                       sub="↓ below 98%" if rt<98 else "✓ on target")
        self._set_card(self._cards["Test Time"],   str(s.get("test_time","—")))
        self._tables_panel.populate(data)
        for b in self._chart_btns: b.configure(state="normal", text_color=INFO)
        self._pdf_btn.configure(state="normal")
        self._export_btn.configure(state="normal")
        fd = data.get("failed_detail",[])
        chips = [(f"⚠ {len(fd)} component failures","fail")] if fd else [("✓ All passed","pass")]
        for ins in data.get("insights",[]): chips.append((ins[:65],"warn"))
        self._set_insights(chips)
        self.update_idletasks()

    # ── CHARTS ────────────────────────────────────────────────────
    def _open_chart(self, key):
        if not self._data:
            messagebox.showinfo("No Data",
                "Open a report from the Reports or Search tab first.")
            return
        self._open_chart_fn(key, self._data)

    def _open_chart_fn(self, key, data=None):
        from app import (chart_donut, chart_gauge, chart_pareto,
                          chart_comp_types, chart_test_types,
                          chart_power, chart_deviation, chart_pass_rate_by_type)
        REGISTRY = {
            "donut":    ("Pass / Fail Overview",           lambda f: chart_donut(f,data),          (7,6.5)),
            "gauge":    ("Pass Rate Gauge",                 lambda f: chart_gauge(f,data),          (7,6.5)),
            "pareto":   ("Pareto — Top Failures",          lambda f: chart_pareto(f,data),         (10,6.5)),
            "comp":     ("Component Type Breakdown",       lambda f: chart_comp_types(f,data),     (9,6.5)),
            "test":     ("Test Type Breakdown",            lambda f: chart_test_types(f,data),     (9,6.5)),
            "power":    ("Power Supply Rails",             lambda f: chart_power(f,data),          (10,6.5)),
            "deviation":("Deviation Distribution",        lambda f: chart_deviation(f,data),       (9,6.5)),
            "typerate": ("Pass Rate by Component Type",   lambda f: chart_pass_rate_by_type(f,data),(9,6.5)),
        }
        title, fn, fsz = REGISTRY[key]
        ChartPopup(self, title, fn, figsize=fsz)

    # ── REPORTS PAGE ──────────────────────────────────────────────
    def _refresh_reports(self):
        boards = ["All Boards"] + self.db.get_board_names()
        self._filter_menu.configure(values=boards)
        board = None if self._filter_var.get()=="All Boards" else self._filter_var.get()
        runs  = self.db.get_runs(board_name=board, limit=500)
        for r in self._rep_tv.get_children(): self._rep_tv.delete(r)
        for r in runs:
            tag = "pass" if r["status"]=="PASS" else "fail"
            self._rep_tv.insert("","end", values=(
                r["id"], r["board_name"], r["serial"],
                r["timestamp"][:16] if r["timestamp"] else "—",
                r["total"], r["passed"], r["failed"],
                f"{r['pass_rate']:.1f}%", r["status"],
                r.get("report_folder","—")),
                tags=(tag,))
        self._reports_count.configure(text=f"{len(runs)} report(s)")

    def _rep_double_click(self, event):
        sel = self._rep_tv.selection()
        if not sel: return
        run_id = int(self._rep_tv.item(sel[0])["values"][0])
        self._view_run(run_id)

    def _view_run(self, run_id: int):
        """Open run detail popup AND load data into self._data for PDF/XLSX export."""
        detail = self.db.get_run_detail(run_id)
        if not detail:
            messagebox.showerror("Not Found", f"Run ID {run_id} not found in database.")
            return

        r = detail["run"]
        # Build a minimal data dict so PDF/XLSX work
        failed_detail = [c for c in detail["components"] if c["status"] == "FAIL"]
        self._data = {
            "summary": {
                "board_name": r["board_name"],
                "serial":     r["serial"],
                "total":      r["total"],
                "passed":     r["passed"],
                "failed":     r["failed"],
                "pass_rate":  r["pass_rate"],
                "status":     r["status"],
                "test_time":  r["timestamp"][11:19] if r["timestamp"] else "—",
                "timestamp":  r["timestamp"] or "",
            },
            "components":    detail["components"],
            "failed_detail": failed_detail,
            "power_rails":   detail["power_rails"],
            "component_types": self._build_comp_types(detail["components"]),
            "test_types":      self._build_test_types(detail["components"]),
            "top_failures":    self._build_top_failures(failed_detail),
            "insights":        self._build_insights(r, failed_detail),
            "parse_log":       [],
            "run_folder":      r.get("report_folder", ""),
        }
        # Enable PDF / XLSX buttons
        self._pdf_btn.configure(state="normal")
        self._export_btn.configure(state="normal")

        RunDetailPopup(self, run_id, self.db)

    def _build_comp_types(self, components):
        ct = {}
        for c in components:
            t = c["type"]
            if t not in ct: ct[t] = {"pass":0,"fail":0}
            ct[t]["pass" if c["status"]=="PASS" else "fail"] += 1
        return ct

    def _build_test_types(self, components):
        tm = {"Resistor":"Resistance","Capacitor":"Capacitance","Inductor":"Inductance",
              "IC":"In-Circuit","Transistor":"In-Circuit","Diode":"In-Circuit",
              "Connector":"Continuity","Component":"Other"}
        tt = {}
        for c in components:
            k = tm.get(c["type"],"Other")
            if k not in tt: tt[k] = {"total":0,"pass":0,"fail":0}
            tt[k]["total"] += 1
            tt[k]["pass" if c["status"]=="PASS" else "fail"] += 1
        return tt

    def _build_top_failures(self, failed_detail):
        from collections import Counter
        return [{"component":k,"count":v}
                for k,v in Counter(c["ref"] for c in failed_detail).most_common(8)]

    def _build_insights(self, r, failed_detail):
        ins = []
        if r["failed"] > 0:
            ins.append(f"WARNING: {r['failed']} component(s) failed — board requires rework")
        if r["pass_rate"] < 98:
            ins.append(f"WARNING: Pass rate {r['pass_rate']:.1f}% is below 98% threshold")
        return ins

    # ── SAVE PDF ──────────────────────────────────────────────────
    def _save_pdf(self):
        if not self._data:
            messagebox.showinfo("No Data","Generate a report first.")
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title("PDF Export Options"); dlg.geometry("460x700")
        dlg.resizable(False,False); dlg.configure(fg_color=BG)
        dlg.transient(self); dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text="Select sections to include",
                     font=("Segoe UI",13,"bold"), text_color=TXT).pack(
            padx=24, pady=(20,2), anchor="w")
        ctk.CTkLabel(dlg, text="PDF auto-saves to ICT_Reports folder",
                     font=("Segoe UI",10), text_color=MUT).pack(
            padx=24, pady=(0,10), anchor="w")

        ctk.CTkLabel(dlg, text="  REPORT SECTIONS",
                     font=("Segoe UI",9,"bold"), text_color=INFO).pack(
            anchor="w", padx=20, pady=(4,2))
        sf = ctk.CTkFrame(dlg, fg_color=S2, corner_radius=8,
                           border_width=1, border_color=BD)
        sf.pack(fill="x", padx=20, pady=(0,8))
        sec_vars = {}
        for key, lbl, default in [
            ("cover","Cover Page & Board Info",True),
            ("summary","Executive Summary Table",True),
            ("failed","Failed Components Table",True),
            ("power","Power Supply Measurements",True),
            ("insights","Insights & Warnings",True),
            ("components","Full Component Results Table",True),
        ]:
            v = tk.BooleanVar(value=default); sec_vars[key] = v
            row = ctk.CTkFrame(sf, fg_color="transparent"); row.pack(fill="x",padx=12,pady=3)
            ctk.CTkCheckBox(row, text=lbl, variable=v, font=("Segoe UI",11),
                            text_color=TXT, fg_color=INFO, hover_color="#0097a7",
                            border_color=BD2).pack(side="left")

        ctk.CTkLabel(dlg, text="  CHARTS",
                     font=("Segoe UI",9,"bold"), text_color=PUR).pack(
            anchor="w", padx=20, pady=(4,2))
        cf = ctk.CTkFrame(dlg, fg_color=S2, corner_radius=8,
                           border_width=1, border_color=BD)
        cf.pack(fill="x", padx=20, pady=(0,8))
        chart_vars = {}
        for key, lbl, default in [
            ("chart_donut","Pass / Fail Donut + Gauge",True),
            ("chart_pareto","Pareto — Top Failures",True),
            ("chart_comp","Component Type Breakdown",True),
            ("chart_power","Power Supply Rails",True),
            ("chart_deviation","Deviation Distribution",True),
        ]:
            v = tk.BooleanVar(value=default); chart_vars[key] = v
            row = ctk.CTkFrame(cf, fg_color="transparent"); row.pack(fill="x",padx=12,pady=3)
            ctk.CTkCheckBox(row, text=lbl, variable=v, font=("Segoe UI",11),
                            text_color=TXT, fg_color=PUR, hover_color="#6a3de8",
                            border_color=BD2).pack(side="left")

        result = {"go":False}
        def on_export(): result["go"]=True; dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8,20))
        ctk.CTkButton(btn_row, text="Cancel", width=120, height=36,
                       fg_color=S3, hover_color=BG, border_color=BD, border_width=1,
                       font=("Segoe UI",11), text_color=MUT,
                       command=dlg.destroy).pack(side="left")
        ctk.CTkButton(btn_row, text="📄  Export PDF", width=160, height=36,
                       fg_color=WBG, hover_color="#4d3a00",
                       border_color=WARN, border_width=1,
                       font=("Segoe UI",11,"bold"), text_color=WARN,
                       command=on_export).pack(side="right")
        dlg.wait_window()
        if not result["go"]: return

        try:
            out = self.reporter.generate(self._data, save_path=None,
                sections={k:v.get() for k,v in sec_vars.items()},
                charts={k:v.get() for k,v in chart_vars.items()})
            messagebox.showinfo("Saved", f"PDF auto-saved:\n{out}")
        except Exception as e:
            messagebox.showerror("PDF Error", str(e))

    # ── EXPORT EXCEL ──────────────────────────────────────────────
    def _export_excel(self):
        if not self._data:
            messagebox.showinfo("No Data","Generate a report first.")
            return
        try:
            import openpyxl
            from openpyxl.styles import Font
            path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel","*.xlsx")],
                initialfile=f"ICT_{self._data['summary']['serial']}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx")
            if not path: return
            wb = openpyxl.Workbook()
            ws = wb.active; ws.title="Summary"; s=self._data["summary"]
            for r,(k,v) in enumerate([
                ("Board",s["board_name"]),("Serial",s["serial"]),
                ("Status",s["status"]),("Total",s["total"]),
                ("Passed",s["passed"]),("Failed",s["failed"]),
                ("Pass Rate",f"{s['pass_rate']:.1f}%"),
                ("Timestamp",s.get("timestamp",""))],1):
                ws.cell(r,1,k).font=Font(bold=True); ws.cell(r,2,v)
            ws2=wb.create_sheet("Component Results")
            ws2.append(["Ref","Type","Nominal","Measured","Deviation","Status"])
            for c in self._data.get("components",[]):
                ws2.append([c["ref"],c["type"],c.get("nominal","—"),
                             c.get("measured","—"),c.get("deviation","—"),c["status"]])
            ws3=wb.create_sheet("Failed Components")
            ws3.append(["Ref","Type","Nominal","Measured","Deviation","Limit","Note"])
            for c in self._data.get("failed_detail",[]):
                ws3.append([c["ref"],c["type"],c.get("nominal","—"),
                             c.get("measured","—"),c.get("deviation","—"),
                             c.get("limit","—"),c.get("note","—")])
            ws4=wb.create_sheet("Power Supply")
            ws4.append(["Rail","Nominal","Measured","Deviation","Ripple","Status"])
            for p in self._data.get("power_rails",[]):
                ws4.append([p["rail"],p["nominal"],p["measured"],
                             p.get("deviation","—"),p.get("ripple","—"),p["status"]])
            wb.save(path)
            messagebox.showinfo("Exported",f"Saved:\n{path}")
        except ImportError:
            messagebox.showerror("Missing","pip install openpyxl")
        except Exception as e:
            messagebox.showerror("Export Error",str(e))

    # ── RESET DATA ─────────────────────────────────────────────────
    def _reset_data(self):
        """Admin-authenticated reset: backup everything to zip, then wipe."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Admin Authentication"); dlg.geometry("380x300")
        dlg.resizable(False, False); dlg.configure(fg_color=BG)
        dlg.transient(self); dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text="🔒  Admin Login Required",
                     font=("Segoe UI",15,"bold"), text_color=FAIL).pack(
            pady=(24,4))
        ctk.CTkLabel(dlg, text="This will backup and erase all reports & data",
                     font=("Segoe UI",10), text_color=MUT).pack(pady=(0,16))

        form = ctk.CTkFrame(dlg, fg_color=S2, corner_radius=8,
                             border_width=1, border_color=BD)
        form.pack(fill="x", padx=28, pady=(0,12))

        ctk.CTkLabel(form, text="Username", font=("Segoe UI",10,"bold"),
                     text_color=MUT).pack(anchor="w", padx=16, pady=(12,2))
        user_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=user_var, width=280, height=34,
                      font=("Courier New",12), fg_color=S3, text_color=TXT,
                      border_color=BD).pack(padx=16, pady=(0,8))

        ctk.CTkLabel(form, text="Password", font=("Segoe UI",10,"bold"),
                     text_color=MUT).pack(anchor="w", padx=16, pady=(4,2))
        pass_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=pass_var, width=280, height=34,
                      font=("Courier New",12), fg_color=S3, text_color=TXT,
                      border_color=BD, show="●").pack(padx=16, pady=(0,14))

        result = {"go": False}
        err_lbl = ctk.CTkLabel(dlg, text="", font=("Segoe UI",10), text_color=FAIL)
        err_lbl.pack()

        def on_login():
            u = user_var.get().strip()
            p = pass_var.get().strip()
            if u == self.cfg.get("admin_user") and p == self.cfg.get("admin_pass"):
                result["go"] = True
                dlg.destroy()
            else:
                err_lbl.configure(text="✗  Invalid credentials")

        dlg.bind("<Return>", lambda e: on_login())

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=28, pady=(4,16))
        ctk.CTkButton(btn_row, text="Cancel", width=100, height=34,
                       fg_color=S3, hover_color=BG, border_color=BD, border_width=1,
                       font=("Segoe UI",11), text_color=MUT,
                       command=dlg.destroy).pack(side="left")
        ctk.CTkButton(btn_row, text="🔓  Authenticate", width=160, height=34,
                       fg_color=FBG, hover_color="#5a0f1a",
                       border_color=FAIL, border_width=1,
                       font=("Segoe UI",11,"bold"), text_color=FAIL,
                       command=on_login).pack(side="right")

        dlg.wait_window()
        if not result["go"]:
            return

        # ── Backup & wipe ──
        try:
            output_root = self.cfg.output_root
            if not os.path.isdir(output_root):
                messagebox.showinfo("Nothing to Reset",
                    "ICT_Reports folder doesn't exist — nothing to clear.")
                return

            # Stop watcher during reset
            self.watcher.stop()

            # Create timestamped backup zip on Desktop
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"ICT_Reports_Backup_{ts}"
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            backup_zip = os.path.join(desktop, f"{backup_name}.zip")

            with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(output_root):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        arcname = os.path.join(backup_name,
                                    os.path.relpath(fpath, output_root))
                        zf.write(fpath, arcname)

            # Close old DB so Windows releases the file lock
            self.db.close()
            import gc; gc.collect()

            # Wipe ICT_Reports with retry for locked files
            import time as _time
            for attempt in range(5):
                shutil.rmtree(output_root, ignore_errors=True)
                if not os.path.isdir(output_root):
                    break
                _time.sleep(0.3)

            # Recreate fresh DB and folders
            os.makedirs(output_root, exist_ok=True)
            self.db = DBManager()
            self._data = None
            self._pdf_btn.configure(state="disabled")
            self._export_btn.configure(state="disabled")

            # Update DB reference in all pages
            if "dashboard" in self._pages:
                self._pages["dashboard"].db = self.db
            if "search" in self._pages:
                self._pages["search"].db = self.db

            # Mark all existing files in watch folder as processed
            # so the watcher doesn't re-ingest them after reset
            watch = self.cfg.watch_folder
            if os.path.isdir(watch):
                import hashlib as _hl
                for fname in os.listdir(watch):
                    fpath = os.path.join(watch, fname)
                    if os.path.isfile(fpath):
                        h = _hl.md5()
                        try:
                            with open(fpath, "rb") as f: h.update(f.read(65536))
                        except Exception: pass
                        self.db.mark_processed(fpath, h.hexdigest())

            # Restart watcher
            self.watcher = FileWatcher(self.db, self.cfg,
                                        on_new_file=self._on_new_file)
            self.watcher.start()
            self._wbar.set_active(True)

            # Refresh all pages
            self._bg_refresh()

            messagebox.showinfo("Reset Complete",
                f"Backup saved to:\n{backup_zip}\n\n"
                f"All reports and database have been cleared.")

        except Exception as e:
            messagebox.showerror("Reset Error", str(e))

    def on_close(self):
        self.watcher.stop()
        plt.close("all")
        self.destroy()


# ── CHART FUNCTIONS (must be importable from app.py) ─────────────
def chart_donut(fig, data):
    ax=fig.add_subplot(111); p=data["summary"]["passed"]; f=data["summary"]["failed"]
    rt=data["summary"]["pass_rate"]; rc=PASS if rt>=98 else WARN if rt>=90 else FAIL
    sizes=[p,f] if f>0 else [p]; clrs=[PASS,FAIL] if f>0 else [PASS]
    ax.pie(sizes,colors=clrs,startangle=90,wedgeprops=dict(width=0.5,edgecolor=BG,linewidth=3))
    ax.text(0,0.12,f"{rt:.1f}%",ha="center",va="center",fontsize=26,fontweight="bold",
            color=rc,fontfamily="monospace")
    ax.text(0,-0.12,f"{p} pass  /  {f} fail",ha="center",va="center",fontsize=10,color=MUT)
    ax.set_title("Pass / Fail Overview",fontsize=13,color=TXT,pad=14); ax.axis("equal")
    fig.tight_layout()

def chart_gauge(fig, data):
    ax=fig.add_subplot(111,aspect="equal")
    ax.set_xlim(-1.3,1.3); ax.set_ylim(-0.2,1.3); ax.axis("off")
    rt=data["summary"]["pass_rate"]; rc=PASS if rt>=98 else WARN if rt>=90 else FAIL
    for t1,t2,c in [(np.pi,np.pi*0.67,FAIL),(np.pi*0.67,np.pi*0.33,WARN),(np.pi*0.33,0,PASS)]:
        th=np.linspace(t1,t2,80)
        ax.plot(np.cos(th)*0.85,np.sin(th)*0.85,color=c,linewidth=14,alpha=0.85,solid_capstyle="butt")
    angle=np.pi*(1-rt/100)
    ax.annotate("",xy=(np.cos(angle)*0.7,np.sin(angle)*0.7),xytext=(0,0),
                arrowprops=dict(arrowstyle="-|>",color=TXT,lw=2.5,mutation_scale=16))
    ax.plot(0,0,"o",color=TXT,markersize=9,zorder=5)
    ax.text(0,0.28,f"{rt:.1f}%",ha="center",va="center",fontsize=24,fontweight="bold",
            color=rc,fontfamily="monospace")
    ax.text(0,0.08,"Pass Rate",ha="center",va="center",fontsize=10,color=MUT)
    ax.set_title("Pass Rate Gauge",fontsize=13,color=TXT,pad=14); fig.tight_layout()

def chart_pareto(fig, data):
    ax1=fig.add_subplot(111); ax2=ax1.twinx()
    failures=data.get("top_failures",[])
    if not failures:
        ax1.text(0.5,0.5,"✓  No failures",ha="center",va="center",
                 transform=ax1.transAxes,color=PASS,fontsize=13)
    else:
        names=[f["component"] for f in failures]; counts=[f["count"] for f in failures]
        xs=np.arange(len(names)); cum=np.cumsum(counts)/sum(counts)*100
        bars=ax1.bar(xs,counts,color=FAIL,alpha=0.82,width=0.55)
        ax1.bar_label(bars,padding=4,fontsize=10,color=MUT)
        ax2.plot(xs,cum,color=WARN,marker="o",linewidth=2,markersize=7,linestyle="--")
        ax2.axhline(80,color=INFO,linewidth=1,linestyle=":",alpha=0.8)
        ax2.set_ylim(0,115); ax2.set_ylabel("Cumulative %",fontsize=10,color=WARN)
        ax2.tick_params(colors=WARN,labelsize=10)
        ax1.set_xticks(xs); ax1.set_xticklabels(names,fontsize=11,rotation=15,ha="right")
        ax1.set_ylabel("Failure Count",fontsize=10); ax1.grid(axis="y",alpha=0.3)
    ax1.set_title("Pareto — Top Failing Components",fontsize=13,color=TXT,pad=14)
    fig.tight_layout()

def chart_comp_types(fig, data):
    ax=fig.add_subplot(111); types=data.get("component_types",{})
    if types:
        labels=list(types.keys())
        passed=[types[k]["pass"] for k in labels]; failed=[types[k]["fail"] for k in labels]
        y=np.arange(len(labels))
        ax.barh(y,passed,color=PASS,alpha=0.85,height=0.5,label="Pass")
        ax.barh(y,failed,left=passed,color=FAIL,alpha=0.85,height=0.5,label="Fail")
        ax.set_yticks(y); ax.set_yticklabels(labels,fontsize=12)
        ax.tick_params(axis="x",labelsize=10); ax.legend(fontsize=10,framealpha=0)
        ax.grid(axis="x",alpha=0.3)
    ax.set_title("Component Type Breakdown",fontsize=13,color=TXT,pad=14); fig.tight_layout()

def chart_test_types(fig, data):
    ax=fig.add_subplot(111); tests=data.get("test_types",{})
    if tests:
        labels=list(tests.keys())
        passed=[tests[k]["pass"] for k in labels]; failed=[tests[k]["fail"] for k in labels]
        x=np.arange(len(labels)); w=0.35
        ax.bar(x-w/2,passed,w,color=PASS,alpha=0.85,label="Pass")
        ax.bar(x+w/2,failed,w,color=FAIL,alpha=0.85,label="Fail")
        ax.set_xticks(x); ax.set_xticklabels(labels,fontsize=12)
        ax.tick_params(axis="y",labelsize=10); ax.legend(fontsize=10,framealpha=0)
        ax.grid(axis="y",alpha=0.3)
    ax.set_title("Test Type Breakdown",fontsize=13,color=TXT,pad=14); fig.tight_layout()

def chart_power(fig, data):
    ax=fig.add_subplot(111); rails=data.get("power_rails",[])
    if rails:
        names,noms,meas,clrs=[],[],[],[]
        for r in rails:
            names.append(r["rail"])
            try: noms.append(float(str(r["nominal"]).replace("V",""))); meas.append(float(str(r["measured"]).replace("V","")))
            except: noms.append(0); meas.append(0)
            clrs.append(PASS if r["status"]=="PASS" else FAIL)
        x=np.arange(len(names)); w=0.32
        ax.bar(x-w/2,noms,w,color=INFO,alpha=0.7,label="Nominal")
        bars=ax.bar(x+w/2,meas,w,color=clrs,alpha=0.88,label="Measured")
        ax.bar_label(bars,fmt="%.3f",padding=3,fontsize=9,color=MUT)
        ax.set_xticks(x); ax.set_xticklabels(names,fontsize=12)
        ax.tick_params(axis="y",labelsize=10); ax.legend(fontsize=10,framealpha=0)
        ax.grid(axis="y",alpha=0.3)
    ax.set_title("Power Supply — Nominal vs Measured",fontsize=13,color=TXT,pad=14); fig.tight_layout()

def chart_deviation(fig, data):
    ax=fig.add_subplot(111); devs=[]
    for c in data.get("components",[]):
        try: devs.append(float(str(c.get("deviation","")).replace("%","").replace("+","")))
        except: pass
    if devs:
        ax.hist(devs,bins=20,color=INFO,alpha=0.7,edgecolor=BD,linewidth=0.5)
        ax.axvline(-5,color=WARN,linewidth=1.5,linestyle="--",alpha=0.8,label="±5% limit")
        ax.axvline(5,color=WARN,linewidth=1.5,linestyle="--",alpha=0.8)
        ax.axvline(0,color=MUT,linewidth=0.8,alpha=0.5)
        ax.legend(fontsize=10,framealpha=0); ax.grid(axis="y",alpha=0.3)
    ax.set_title("Measurement Deviation Distribution",fontsize=13,color=TXT,pad=14)
    fig.tight_layout()

def chart_pass_rate_by_type(fig, data):
    ax=fig.add_subplot(111); types=data.get("component_types",{})
    if types:
        labels=list(types.keys())
        pass_pct=[types[k]["pass"]/(types[k]["pass"]+types[k]["fail"])*100
                  if (types[k]["pass"]+types[k]["fail"])>0 else 0 for k in labels]
        fail_pct=[100-p for p in pass_pct]; x=np.arange(len(labels))
        ax.bar(x,pass_pct,color=PASS,alpha=0.85,width=0.5,label="Pass %")
        ax.bar(x,fail_pct,bottom=pass_pct,color=FAIL,alpha=0.85,width=0.5,label="Fail %")
        ax.axhline(98,color=WARN,linewidth=1.5,linestyle="--",alpha=0.8,label="98% target")
        for i,p in enumerate(pass_pct):
            ax.text(i,p/2,f"{p:.0f}%",ha="center",va="center",fontsize=10,color="white",fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(labels,fontsize=12)
        ax.set_ylim(0,115); ax.legend(fontsize=10,framealpha=0); ax.grid(axis="y",alpha=0.3)
    ax.set_title("Pass Rate by Component Type",fontsize=13,color=TXT,pad=14); fig.tight_layout()


if __name__ == "__main__":
    app = ICTApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
