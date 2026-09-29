"""
Database manager — SQLite backend for ICT run history + processed file tracking.
"""
import sqlite3, os, datetime, re, sys

# App root: next to EXE if frozen, next to script if running from source
if getattr(sys, 'frozen', False):
    _APP_ROOT = os.path.dirname(sys.executable)
else:
    _APP_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_ROOT = os.path.join(_APP_ROOT, "ICT_Reports")
DB_PATH     = os.path.join(OUTPUT_ROOT, "ict_results.db")


class DBManager:
    def __init__(self, db_path: str = None):
        os.makedirs(OUTPUT_ROOT, exist_ok=True)
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def close(self):
        """Force-close any lingering SQLite connections."""
        try:
            with self._connect() as con:
                con.execute("PRAGMA optimize")
            self.db_path = ":memory:"
        except Exception:
            pass

    def _init_db(self):
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_name    TEXT,
                    serial        TEXT,
                    timestamp     TEXT,
                    total         INTEGER,
                    passed        INTEGER,
                    failed        INTEGER,
                    pass_rate     REAL,
                    status        TEXT,
                    filepath      TEXT,
                    report_folder TEXT
                );
                CREATE TABLE IF NOT EXISTS components (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id    INTEGER REFERENCES runs(id) ON DELETE CASCADE,
                    ref       TEXT,
                    type      TEXT,
                    nominal   TEXT,
                    measured  TEXT,
                    deviation TEXT,
                    status    TEXT,
                    note      TEXT
                );
                CREATE TABLE IF NOT EXISTS processed_files (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath  TEXT,
                    filehash  TEXT,
                    processed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_board ON runs(board_name);
                CREATE INDEX IF NOT EXISTS idx_runs_ts    ON runs(timestamp);
                CREATE INDEX IF NOT EXISTS idx_pf_path   ON processed_files(filepath);
                CREATE INDEX IF NOT EXISTS idx_pf_hash   ON processed_files(filehash);
            """)
            cols = [r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()]
            if "report_folder" not in cols:
                con.execute("ALTER TABLE runs ADD COLUMN report_folder TEXT")

    # ── PROCESSED FILES ───────────────────────────────────────────
    def is_processed(self, filepath: str, filehash: str = None) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT id FROM processed_files WHERE filepath=?",
                (filepath,)
            ).fetchone()
        return row is not None

    def mark_processed(self, filepath: str, filehash: str):
        with self._connect() as con:
            con.execute(
                "INSERT INTO processed_files (filepath, filehash, processed_at) VALUES (?,?,?)",
                (filepath, filehash, datetime.datetime.now().isoformat())
            )

    def get_processed_files(self) -> list:
        with self._connect() as con:
            rows = con.execute("SELECT filepath FROM processed_files").fetchall()
        return [r["filepath"] for r in rows]

    # ── SAVE RUN ──────────────────────────────────────────────────
    def save_run(self, data: dict) -> int:
        s  = data["summary"]
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        safe_board  = re.sub(r'[\\/:*?"<>|]', "_", s["board_name"])
        safe_serial = re.sub(r'[\\/:*?"<>|]', "_", s["serial"])
        run_folder  = os.path.join(OUTPUT_ROOT, safe_board, f"{safe_serial}_{ts}")
        # Folder is NOT created here — only when user explicitly saves a PDF

        with self._connect() as con:
            cur = con.execute(
                """INSERT INTO runs
                   (board_name, serial, timestamp, total, passed, failed,
                    pass_rate, status, filepath, report_folder)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (s["board_name"], s["serial"],
                 s.get("timestamp", datetime.datetime.now().isoformat()),
                 s["total"], s["passed"], s["failed"],
                 s["pass_rate"], s["status"],
                 data.get("filepath", ""), run_folder)
            )
            run_id = cur.lastrowid
            con.executemany(
                """INSERT INTO components
                   (run_id, ref, type, nominal, measured, deviation, status, note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(run_id, c["ref"], c["type"], c.get("nominal",""),
                  c.get("measured",""), c.get("deviation",""),
                  c["status"], c.get("note",""))
                 for c in data.get("components", [])]
            )

        data["run_folder"] = run_folder
        return run_id

    # ── SEARCH ────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 100) -> list:
        q = f"%{query}%"
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM runs
                   WHERE board_name LIKE ? OR serial LIKE ? OR status LIKE ?
                   ORDER BY id ASC LIMIT ?""",
                (q, q, q, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run_detail(self, run_id: int) -> dict:
        with self._connect() as con:
            run = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return {}
            comps = con.execute(
                "SELECT * FROM components WHERE run_id=? ORDER BY ref", (run_id,)
            ).fetchall()
        return {
            "run":        dict(run),
            "components": [dict(c) for c in comps],
        }

    # ── READ ──────────────────────────────────────────────────────
    def get_runs(self, board_name: str = None, limit: int = 200) -> list:
        sql = "SELECT * FROM runs"
        params = []
        if board_name:
            sql += " WHERE board_name LIKE ?"
            params.append(f"%{board_name}%")
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_board_names(self) -> list:
        with self._connect() as con:
            rows = con.execute(
                "SELECT DISTINCT board_name FROM runs ORDER BY board_name"
            ).fetchall()
        return [r["board_name"] for r in rows]

    def get_pass_rate_trend(self, board_name: str = None, limit: int = 30) -> list:
        sql = "SELECT timestamp, pass_rate, status, board_name FROM runs"
        params = []
        if board_name:
            sql += " WHERE board_name LIKE ?"
            params.append(f"%{board_name}%")
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_failure_frequency(self, board_name: str = None) -> list:
        sql = """SELECT c.ref, c.type, COUNT(*) as fail_count
                 FROM components c JOIN runs r ON c.run_id=r.id
                 WHERE c.status='FAIL'"""
        params = []
        if board_name:
            sql += " AND r.board_name LIKE ?"
            params.append(f"%{board_name}%")
        sql += " GROUP BY c.ref, c.type ORDER BY fail_count DESC LIMIT 10"
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_board_comparison(self) -> list:
        sql = """SELECT board_name,
                        COUNT(*) as run_count,
                        AVG(pass_rate) as avg_rate,
                        MIN(pass_rate) as min_rate,
                        MAX(pass_rate) as max_rate,
                        SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) as pass_runs,
                        SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as fail_runs
                 FROM runs GROUP BY board_name ORDER BY avg_rate DESC"""
        with self._connect() as con:
            rows = con.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_dashboard_stats(self) -> dict:
        with self._connect() as con:
            total_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            pass_runs  = con.execute("SELECT COUNT(*) FROM runs WHERE status='PASS'").fetchone()[0]
            fail_runs  = con.execute("SELECT COUNT(*) FROM runs WHERE status='FAIL'").fetchone()[0]
            total_comp = con.execute("SELECT SUM(total) FROM runs").fetchone()[0] or 0
            total_fail = con.execute("SELECT SUM(failed) FROM runs").fetchone()[0] or 0
            avg_rate   = con.execute("SELECT AVG(pass_rate) FROM runs").fetchone()[0] or 0
            boards     = con.execute("SELECT COUNT(DISTINCT board_name) FROM runs").fetchone()[0]
            min_rate   = con.execute("SELECT MIN(pass_rate) FROM runs").fetchone()[0] or 0
            max_rate   = con.execute("SELECT MAX(pass_rate) FROM runs").fetchone()[0] or 0
            recent     = con.execute(
                "SELECT * FROM runs ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
            worst = con.execute(
                "SELECT board_name, AVG(pass_rate) as avg FROM runs GROUP BY board_name ORDER BY avg ASC LIMIT 1"
            ).fetchone()
            best = con.execute(
                "SELECT board_name, AVG(pass_rate) as avg FROM runs GROUP BY board_name ORDER BY avg DESC LIMIT 1"
            ).fetchone()
        return {
            "total_runs":      total_runs,
            "pass_runs":       pass_runs,
            "fail_runs":       fail_runs,
            "total_comp":      total_comp,
            "total_fail_comp": total_fail,
            "avg_rate":        round(avg_rate, 2),
            "min_rate":        round(min_rate, 2),
            "max_rate":        round(max_rate, 2),
            "boards":          boards,
            "recent":          [dict(r) for r in recent],
            "worst_board":     dict(worst) if worst else None,
            "best_board":      dict(best) if best else None,
            "fpy":             round(pass_runs / total_runs * 100, 1) if total_runs > 0 else 0,
        }

    def get_component_type_failures(self) -> list:
        with self._connect() as con:
            rows = con.execute(
                """SELECT type, COUNT(*) as total,
                          SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as fails
                   FROM components GROUP BY type ORDER BY fails DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_throughput(self) -> list:
        with self._connect() as con:
            rows = con.execute(
                """SELECT DATE(timestamp) as day, COUNT(*) as count,
                          SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) as passed,
                          SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as failed
                   FROM runs GROUP BY DATE(timestamp) ORDER BY day"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_board_pass_fail_counts(self) -> list:
        with self._connect() as con:
            rows = con.execute(
                """SELECT board_name,
                          SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) as pass_count,
                          SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as fail_count,
                          COUNT(*) as total
                   FROM runs GROUP BY board_name ORDER BY board_name"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_deviation_distribution(self) -> list:
        """Deviation values for histogram (numeric deviations only)."""
        with self._connect() as con:
            rows = con.execute(
                """SELECT deviation FROM components
                   WHERE deviation != '' AND deviation IS NOT NULL"""
            ).fetchall()
        devs = []
        for r in rows:
            try:
                val = str(r["deviation"]).replace("%", "").replace("+", "").replace("—", "").replace("–", "").strip()
                if val and val != "—":
                    devs.append(float(val))
            except (ValueError, TypeError):
                pass
        return devs

    def get_failure_timeline(self) -> list:
        with self._connect() as con:
            rows = con.execute(
                """SELECT DATE(timestamp) as day, SUM(failed) as fails
                   FROM runs GROUP BY DATE(timestamp) ORDER BY day"""
            ).fetchall()
        cumulative = []
        total = 0
        for r in rows:
            total += r["fails"]
            cumulative.append({"day": r["day"], "fails": r["fails"], "cumulative": total})
        return cumulative

    def get_deviation_by_type(self) -> dict:
        """Deviation values grouped by component type for box plots."""
        with self._connect() as con:
            rows = con.execute(
                """SELECT type, deviation FROM components
                   WHERE deviation != '' AND deviation IS NOT NULL"""
            ).fetchall()
        result = {}
        for r in rows:
            try:
                val = str(r["deviation"]).replace("%","").replace("+","").replace("—","").replace("–","").strip()
                if val:
                    t = r["type"] or "Other"
                    if t not in result:
                        result[t] = []
                    result[t].append(float(val))
            except (ValueError, TypeError):
                pass
        return result

    def get_repeat_failures(self) -> list:
        """Components that fail across multiple distinct runs."""
        with self._connect() as con:
            rows = con.execute(
                """SELECT ref, type, COUNT(DISTINCT run_id) as run_count,
                          COUNT(*) as total_fails
                   FROM components WHERE status='FAIL'
                   GROUP BY ref HAVING run_count > 1
                   ORDER BY run_count DESC, total_fails DESC LIMIT 15"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pass_rate_histogram(self) -> list:
        """All pass rates for histogram distribution."""
        with self._connect() as con:
            rows = con.execute("SELECT pass_rate FROM runs ORDER BY pass_rate").fetchall()
        return [r["pass_rate"] for r in rows]

    def seed_demo_data(self):
        import random
        rng = random.Random(99)
        boards = ["MAIN-PCB-v2.3","MAIN-PCB-v2.2","CTRL-BOARD-v1.1","PWR-MODULE-v3"]
        base   = datetime.datetime(2026, 4, 1)
        for i in range(20):
            board  = rng.choice(boards)
            ts     = (base + datetime.timedelta(hours=i*11)).isoformat()
            total  = rng.randint(40, 90)
            failed = rng.randint(0, 5)
            passed = total - failed
            rate   = round(passed/total*100, 2)
            status = "PASS" if failed == 0 else "FAIL"
            serial = f"SN{base.strftime('%Y%m%d')}-{str(i+1).zfill(3)}"
            with self._connect() as con:
                cur = con.execute(
                    """INSERT INTO runs
                       (board_name,serial,timestamp,total,passed,failed,
                        pass_rate,status,filepath,report_folder)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (board, serial, ts, total, passed, failed,
                     rate, status, "", "")
                )
                rid = cur.lastrowid
                for j in range(min(failed, 4)):
                    ref = rng.choice(["R23","C47","U12","U14","J3","Q07","L02"])
                    con.execute(
                        """INSERT INTO components
                           (run_id,ref,type,nominal,measured,deviation,status,note)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (rid, ref, "IC", "—", "—", "—", "FAIL", "Demo failure")
                    )

    def delete_run(self, run_id: int):
        with self._connect() as con:
            con.execute("DELETE FROM components WHERE run_id=?", (run_id,))
            con.execute("DELETE FROM runs WHERE id=?", (run_id,))
