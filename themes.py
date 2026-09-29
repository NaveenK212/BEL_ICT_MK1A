"""
Theme definitions for ICT Report Analyzer.
Each theme is a dict of color keys used throughout the app, charts, and PDF.
"""

THEMES = {
    "dark_navy": {
        "name": "Dark Navy",
        "bg":  "#0a1929", "s1":  "#0d2137", "s2":  "#112a45", "s3":  "#163354",
        "bd":  "#1e4976", "bd2": "#2a5f8f", "txt": "#e3edf7", "mut": "#6e96bf",
        "dim": "#3d6a96", "pass":"#00e676", "fail":"#ff1744", "warn":"#ffab00",
        "info":"#00bcd4", "pur": "#7c4dff",
        "pbg": "#0a3320", "fbg": "#3d0a14", "wbg": "#3d2e00", "ibg": "#003545",
        "ctk_mode": "dark",
    },
    "light": {
        "name": "Light Mode",
        "bg":  "#f0f2f5", "s1":  "#e4e7ec", "s2":  "#ffffff", "s3":  "#f8f9fb",
        "bd":  "#d0d5dd", "bd2": "#98a2b3", "txt": "#1d2939", "mut": "#475467",
        "dim": "#98a2b3", "pass":"#12b76a", "fail":"#f04438", "warn":"#f79009",
        "info":"#0ea5e9", "pur": "#7a5af8",
        "pbg": "#ecfdf3", "fbg": "#fef3f2", "wbg": "#fffaeb", "ibg": "#f0f9ff",
        "ctk_mode": "light",
    },
    "military": {
        "name": "Military Green",
        "bg":  "#1a1f16", "s1":  "#232b1e", "s2":  "#2d3726", "s3":  "#374430",
        "bd":  "#4a5a3e", "bd2": "#6b7d5a", "txt": "#e8ecd8", "mut": "#9aab7e",
        "dim": "#6b7d5a", "pass":"#76ff03", "fail":"#ff3d00", "warn":"#ffc400",
        "info":"#ccff90", "pur": "#b388ff",
        "pbg": "#1b3a0a", "fbg": "#3d1400", "wbg": "#3d3000", "ibg": "#2d4a1a",
        "ctk_mode": "dark",
    },
    "midnight": {
        "name": "Midnight",
        "bg":  "#010409", "s1":  "#0d1117", "s2":  "#161b22", "s3":  "#21262d",
        "bd":  "#30363d", "bd2": "#484f58", "txt": "#e6edf3", "mut": "#8b949e",
        "dim": "#484f58", "pass":"#3fb950", "fail":"#f85149", "warn":"#d29922",
        "info":"#58a6ff", "pur": "#bc8cff",
        "pbg": "#0d2818", "fbg": "#3d0a14", "wbg": "#3d2e00", "ibg": "#0c2d48",
        "ctk_mode": "dark",
    },
}

THEME_NAMES = list(THEMES.keys())

def get_theme(name: str) -> dict:
    return THEMES.get(name, THEMES["dark_navy"])
