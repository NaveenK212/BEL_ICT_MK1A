"""
Config manager — stores app settings in a JSON file next to the app.
"""
import os, json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DESKTOP     = os.path.join(os.path.expanduser("~"), "Desktop")

DEFAULTS = {
    "watch_folder":   os.path.join(DESKTOP, "ICT_Incoming"),
    "output_root":    os.path.join(DESKTOP, "ICT_Reports"),
    "auto_pdf":       True,
    "poll_interval":  2,          # seconds between folder checks
    "admin_user":     "admin",
    "admin_pass":     "bel@2026",
}


class Config:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def watch_folder(self):  return self._data["watch_folder"]
    @property
    def output_root(self):   return self._data["output_root"]
    @property
    def auto_pdf(self):      return self._data["auto_pdf"]
    @property
    def poll_interval(self): return self._data["poll_interval"]
