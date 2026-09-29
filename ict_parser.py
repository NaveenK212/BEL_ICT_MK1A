"""
ICT File Parser v6.1
Supports: Keysight/Agilent ICT (@BATCH/@BTEST/@BLOCK), CSV, generic text.
NEVER generates fake demo data — always raises an error for unrecognised files.
"""
import os, re, csv, datetime


class ICTParser:

    # ── PUBLIC ENTRY POINT ────────────────────────────────────────
    def parse(self, filepath: str) -> dict:
        # Reject binary files immediately
        with open(filepath, "rb") as f:
            header = f.read(16)
        if header[:6] == b"SQLite":
            raise ValueError(
                f"'{os.path.basename(filepath)}' is the database file — not an ICT report.\n\n"
                "Select a .ict / .txt / .log file from your ICT machine.")
        if header[:4] in (b"PK\x03\x04", b"\x89PNG", b"%PDF"):
            raise ValueError(
                f"'{os.path.basename(filepath)}' is a binary file.\n\n"
                "Select a .ict / .txt / .log file from your ICT machine.")

        with open(filepath, "r", errors="replace") as f:
            raw = f.read()

        if "@BATCH" in raw or "@BTEST" in raw or "@BLOCK" in raw:
            return self._parse_keysight(raw, filepath)

        if os.path.splitext(filepath)[1].lower() == ".csv":
            return self._parse_csv(filepath)

        return self._parse_generic(raw, filepath)

    # ── KEYSIGHT / AGILENT ICT ────────────────────────────────────
    def _parse_keysight(self, raw: str, filepath: str) -> dict:
        lines      = raw.splitlines()
        meta       = {}
        components = []
        power_rails= []
        parse_log  = []

        cur_ref    = None
        cur_status = None
        cur_meas   = None
        cur_upper  = None
        cur_lower  = None

        def flush():
            nonlocal cur_ref
            if cur_ref is None:
                return
            c = self._make_comp(cur_ref, cur_status, cur_meas, cur_upper, cur_lower)
            components.append(c)
            if c["status"] == "FAIL":
                parse_log.append(
                    f"  → {c['ref']}: FAIL  "
                    f"[meas={c['measured']}  limits: "
                    f"{self._fmt(cur_lower)}–{self._fmt(cur_upper)}]")
            cur_ref = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Board name from @BATCH line
            if line.startswith("@BATCH"):
                parts = line.split("|")
                if len(parts) > 1 and parts[1].strip():
                    meta["board_name"] = parts[1].strip()

            # Serial from @BTEST line
            elif "@BTEST" in line:
                parts = line.lstrip("{").split("|")
                if len(parts) > 1 and parts[1].strip():
                    meta["serial"] = parts[1].strip()

            # Block start
            elif "@BLOCK" in line:
                flush()
                parts = line.lstrip("{").split("|")
                cur_ref    = parts[1].strip().upper() if len(parts) > 1 else "?"
                raw_st     = parts[2].strip(" }") if len(parts) > 2 else "00"
                cur_status = "PASS" if raw_st == "00" else "FAIL"
                cur_meas   = None
                cur_upper  = None
                cur_lower  = None

            # Measurement line
            elif any(t in line for t in ("@A-JUM","@A-CAP","@A-RES",
                                          "@A-IND","@A-DIO","@A-Z")):
                m = re.search(r'\|\s*([+-]?[\d.Ee+\-]+)\s*\{', line)
                if m:
                    try: cur_meas = float(m.group(1))
                    except Exception: pass

                m2 = re.search(r'@LIM2\|([+-]?[\d.Ee+\-]+)\|([+-]?[\d.Ee+\-]+)', line)
                if m2:
                    try:
                        cur_upper = float(m2.group(1))
                        cur_lower = float(m2.group(2))
                    except Exception:
                        pass
                    # Re-evaluate from actual values
                    if cur_meas is not None and \
                       cur_upper is not None and cur_lower is not None:
                        lo = min(cur_upper, cur_lower)
                        hi = max(cur_upper, cur_lower)
                        cur_status = "PASS" if lo <= cur_meas <= hi else "FAIL"

            # Block close
            elif line == "}" and cur_ref is not None:
                flush()

        flush()  # final block

        if not components:
            raise ValueError(
                f"File parsed as Keysight ICT but no @BLOCK components found.\n"
                f"File: {os.path.basename(filepath)}")

        meta.setdefault("board_name",
                        os.path.splitext(os.path.basename(filepath))[0])
        meta.setdefault("serial",
                        f"SN{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")

        return self._build(meta, components, power_rails,
                           parse_log, filepath, "Keysight ICT")

    # ── CSV ───────────────────────────────────────────────────────
    def _parse_csv(self, filepath: str) -> dict:
        components = []; parse_log = []; meta = {}
        with open(filepath, newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ref    = (row.get("ref") or row.get("Ref") or "?").strip()
                ctype  = (row.get("type") or row.get("Type") or "Component").strip()
                nom    = (row.get("nominal") or row.get("Nominal") or "—").strip()
                meas   = (row.get("measured") or row.get("Measured") or "—").strip()
                status = (row.get("status") or row.get("Status") or "PASS").strip().upper()
                dev    = self._calc_dev(nom, meas)
                components.append({"ref": ref, "type": ctype,
                    "nominal": nom, "measured": meas,
                    "deviation": dev, "status": status, "note": ""})
                if status == "FAIL":
                    parse_log.append(f"  → {ref}: FAIL")
        if not components:
            raise ValueError(
                f"CSV file '{os.path.basename(filepath)}' has no recognised data.\n"
                "Expected columns: ref, type, nominal, measured, status")
        meta["board_name"] = os.path.splitext(os.path.basename(filepath))[0]
        meta["serial"]     = f"SN{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        return self._build(meta, components, [], parse_log, filepath, "CSV")

    # ── GENERIC TEXT ──────────────────────────────────────────────
    def _parse_generic(self, raw: str, filepath: str) -> dict:
        components = []; parse_log = []; meta = {}
        for line in raw.splitlines():
            line = line.strip()
            for key, pat in [
                ("board_name", r"board[_ ]?name\s*[:=]\s*(.+)"),
                ("serial",     r"serial\s*[:=]\s*(.+)"),
            ]:
                m = re.search(pat, line, re.I)
                if m: meta[key] = m.group(1).strip()

            m = re.match(
                r"([A-Z]\d+)\s+(\w+)\s+([\d.]+\s*\S*)\s+"
                r"([\d.]+\s*\S*)\s+(PASS|FAIL)",
                line, re.I)
            if m:
                ref, ctype, nom, meas, status = m.groups()
                components.append({
                    "ref": ref, "type": ctype,
                    "nominal": nom, "measured": meas,
                    "deviation": self._calc_dev(nom, meas),
                    "status": status.upper(), "note": ""})
                if status.upper() == "FAIL":
                    parse_log.append(f"  → {ref}: FAIL")

        if not components:
            raise ValueError(
                f"Cannot parse '{os.path.basename(filepath)}'.\n\n"
                "Supported formats:\n"
                "  • Keysight/Agilent ICT  (@BATCH / @BTEST / @BLOCK)\n"
                "  • CSV  (columns: ref, type, nominal, measured, status)\n"
                "  • Generic text  (REF  TYPE  NOMINAL  MEASURED  PASS/FAIL)\n\n"
                "Load one of the sample files from the demo_reports/ folder to test.")

        meta.setdefault("board_name",
                        os.path.splitext(os.path.basename(filepath))[0])
        meta.setdefault("serial",
                        f"SN{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
        return self._build(meta, components, [], parse_log, filepath, "Generic Text")

    # ── HELPERS ───────────────────────────────────────────────────
    def _fmt(self, val):
        if val is None: return "—"
        v = abs(val)
        if v >= 1e9:  return f"{val/1e9:.3f}G"
        if v >= 1e6:  return f"{val/1e6:.3f}M"
        if v >= 1e3:  return f"{val/1e3:.3f}k"
        if v >= 1:    return f"{val:.4f}"
        if v >= 1e-3: return f"{val*1e3:.4f}m"
        if v >= 1e-6: return f"{val*1e6:.4f}µ"
        if v >= 1e-9: return f"{val*1e9:.4f}n"
        return f"{val:.4e}"

    def _infer_type(self, ref: str) -> str:
        r = ref.lower()
        if r.startswith("r"):  return "Resistor"
        if r.startswith("c"):  return "Capacitor"
        if r.startswith("l"):  return "Inductor"
        if r.startswith("u"):  return "IC"
        if r.startswith("q"):  return "Transistor"
        if r.startswith("d"):  return "Diode"
        if r.startswith("t"):  return "Transformer"
        if r[0] in ("j","p","k","e"): return "Connector"
        return "Component"

    def _make_comp(self, ref, status, meas, upper, lower):
        ctype = self._infer_type(ref)
        nominal = "—"; dev = "—"
        if meas is not None and upper is not None and lower is not None:
            lo = min(upper, lower); hi = max(upper, lower)
            mid = (hi + lo) / 2
            nominal = self._fmt(mid)
            if mid != 0:
                pct = (meas - mid) / abs(mid) * 100
                dev = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
        return {
            "ref": ref, "type": ctype,
            "nominal": nominal,
            "measured": self._fmt(meas) if meas is not None else "—",
            "deviation": dev,
            "status": status,
            "note": "Out of tolerance" if status == "FAIL" else "",
        }

    def _calc_dev(self, nom, meas):
        try:
            n = float(re.sub(r"[^\d.]", "", str(nom)))
            m = float(re.sub(r"[^\d.]", "", str(meas)))
            if n == 0: return "—"
            p = (m - n) / n * 100
            return f"{'+' if p >= 0 else ''}{p:.1f}%"
        except Exception:
            return "—"

    # ── BUILD RESULT DICT ─────────────────────────────────────────
    def _build(self, meta, components, power_rails,
               parse_log, filepath, fmt) -> dict:
        total  = len(components)
        passed = sum(1 for c in components if c["status"] == "PASS")
        failed = total - passed
        rate   = round(passed / total * 100, 2) if total else 0

        failed_detail = [c for c in components if c["status"] == "FAIL"]

        comp_types: dict = {}
        for c in components:
            t = c["type"]
            if t not in comp_types:
                comp_types[t] = {"pass": 0, "fail": 0}
            comp_types[t]["pass" if c["status"] == "PASS" else "fail"] += 1

        type_map = {
            "Resistor": "Resistance", "Capacitor": "Capacitance",
            "Inductor": "Inductance", "IC": "In-Circuit",
            "Transistor": "In-Circuit", "Diode": "In-Circuit",
            "Connector": "Continuity", "Transformer": "In-Circuit",
            "Component": "Other",
        }
        test_types: dict = {}
        for c in components:
            tt = type_map.get(c["type"], "Other")
            if tt not in test_types:
                test_types[tt] = {"total": 0, "pass": 0, "fail": 0}
            test_types[tt]["total"] += 1
            test_types[tt]["pass" if c["status"] == "PASS" else "fail"] += 1

        from collections import Counter
        top_failures = [{"component": k, "count": v}
                        for k, v in Counter(
                            c["ref"] for c in failed_detail
                        ).most_common(8)]

        insights = []
        if failed > 0:
            insights.append(
                f"WARNING: {failed} component(s) failed — board requires rework")
        if rate < 98:
            insights.append(
                f"WARNING: Pass rate {rate:.1f}% is below 98% threshold")
        if any(p["status"] == "FAIL" for p in power_rails):
            insights.append(
                "WARNING: One or more power rails out of specification")

        return {
            "format":   fmt,
            "filepath": filepath,
            "summary": {
                "board_name": meta.get("board_name", "Unknown"),
                "serial":     meta.get("serial", "—"),
                "total":      total,
                "passed":     passed,
                "failed":     failed,
                "pass_rate":  rate,
                "status":     "PASS" if failed == 0 else "FAIL",
                "test_time":  datetime.datetime.now().strftime("%H:%M:%S"),
                "timestamp":  datetime.datetime.now().isoformat(),
            },
            "components":       components,
            "failed_detail":    failed_detail,
            "power_rails":      power_rails,
            "component_types":  comp_types,
            "test_types":       test_types,
            "top_failures":     top_failures,
            "insights":         insights,
            "parse_log":        parse_log,
        }
