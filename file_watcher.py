"""
File Watcher — polls the watch folder for new ICT files.
Runs in a background thread. Calls callback(filepath) for each new file.
Tracks processed files in DB so same file is never double-processed.
"""
import os, threading, time, hashlib


SUPPORTED = (".ict", ".txt", ".log", ".csv", "")  # empty string = no extension


def _has_supported_ext(fname: str) -> bool:
    _, ext = os.path.splitext(fname)
    return ext.lower() in SUPPORTED


def _file_hash(path: str) -> str:
    """MD5 of first 64KB — fast fingerprint."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            h.update(f.read(65536))
    except Exception:
        pass
    return h.hexdigest()


class FileWatcher:
    def __init__(self, db, config, on_new_file):
        """
        db          — DBManager instance (for tracking processed files)
        config      — Config instance
        on_new_file — callable(filepath: str) called for each new file found
        """
        self._db          = db
        self._cfg         = config
        self._callback    = on_new_file
        self._running     = False
        self._thread      = None
        self._seen        = set()   # "filepath::hash" keys seen this session
        self._lock        = threading.Lock()

    # ── PUBLIC ────────────────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._running = True
        # Pre-load seen set with correct key format
        self._seen = set()
        for fp in self._db.get_processed_files():
            self._seen.add(fp)   # path-only fallback
        folder = self._cfg.watch_folder
        os.makedirs(folder, exist_ok=True)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def scan_now(self):
        """Force an immediate scan (called on startup or manual refresh)."""
        self._scan()

    def reset(self):
        """Clear seen set so all files in current folder are re-evaluated."""
        self._seen.clear()

    # ── PRIVATE ───────────────────────────────────────────────────
    def _loop(self):
        while self._running:
            self._scan()
            time.sleep(self._cfg.poll_interval)

    def _scan(self):
        with self._lock:
            folder = self._cfg.watch_folder
            if not os.path.isdir(folder):
                return
            for fname in sorted(os.listdir(folder)):
                if not _has_supported_ext(fname):
                    continue
                fpath = os.path.join(folder, fname)
                if not os.path.isfile(fpath):
                    continue

                # Skip if already processed (by exact path — not hash,
                # so same content in a new folder still gets processed)
                fhash = _file_hash(fpath)
                key   = f"{fpath}::{fhash}"
                if key in self._seen:
                    continue
                if self._db.is_processed(fpath):
                    self._seen.add(key)
                    continue

                # New file — fire callback
                self._seen.add(key)
                try:
                    self._callback(fpath)
                except Exception as e:
                    print(f"[Watcher] Error processing {fname}: {e}")
