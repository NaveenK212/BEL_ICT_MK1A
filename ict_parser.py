"""
ICT File Parser v6.1
Supports: Keysight/Agilent ICT (@BATCH/@BTEST/@BLOCK), CSV, generic text.
NEVER generates fake demo data — always raises an error for unrecognised files.
"""
import os, re, csv, datetime


class ICTParser:
    # Bump whenever parsing rules change: the app re-parses stored runs
    # saved by an older version automatically at startup.
    VERSION = 14

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
    #  Board result : @BTEST field 3  ->  "00" = PASS, anything else = FAIL
    #  Each @BLOCK  : may hold several @A-xxx measurement lines; every
    #                 measurement becomes its own component row.
    #  A block ends only when the next @BLOCK starts (the tester interleaves
    #  @D-T / @TJET lines, each closed by "}", inside a block).
    def _parse_keysight(self, raw: str, filepath: str) -> dict:
        meta       = {}
        parse_log  = []
        blocks     = []
        blk        = None

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Board name from @BATCH line
            if "@BATCH" in line and "board_name" not in meta:
                parts = line.lstrip("{").split("|")
                # Board name: field 10 (after the fixture id) if present,
                # otherwise field 1 (right after @BATCH).
                name10 = parts[10].strip() if len(parts) > 10 else ""
                name1  = parts[1].strip()  if len(parts) > 1  else ""
                if name10 or name1:
                    meta["board_name"] = name10 or name1

            # Serial + overall board result from @BTEST line
            elif "@BTEST" in line:
                parts = line.lstrip("{").split("|")
                if len(parts) > 1 and parts[1].strip():
                    meta["serial_raw"] = parts[1].strip()
                    meta["serial"] = self._clean_serial(
                        parts[1].strip(), meta.get("board_name", ""))
                if len(parts) > 3:
                    dt = self._parse_test_dt(parts[3])
                    if dt and "test_dt" not in meta:
                        meta["test_dt"] = dt
                if len(parts) > 2:
                    code = parts[2].strip(" }")
                    if code != "00":
                        meta["board_fail"] = True
                        meta["board_code"] = code
                    meta.setdefault("board_code", code)

            # Block start
            elif "@BLOCK" in line:
                parts = line.lstrip("{").split("|")
                ref_raw = parts[1].strip() if len(parts) > 1 else "?"
                code    = parts[2].strip(" }") if len(parts) > 2 else "00"
                base, _, tag = ref_raw.partition("%")   # "k1%unp%jp1" -> K1
                blk = {"base": base.upper(), "tag": tag.replace("%", " "),
                       "tester_fail": code != "00", "code": code,
                       "meas": [], "tjet": []}
                blocks.append(blk)

            # Testjet device result:  {@TJET|00|0000|u5   (00 = PASS, else FAIL)
            elif "@TJET" in line and blk is not None:
                tp = line.lstrip("{").split("|")
                if len(tp) >= 4:
                    tcode = tp[1].strip(" }")
                    tref  = tp[3].strip(" }")
                    if tref:
                        blk["tjet"].append((tcode, tref))

            # Any Agilent measurement line (CAP RES JUM DIO ZEN NFE PFE MEA ...)
            elif "@A-" in line and blk is not None:
                m = self._parse_measurement(line)
                if m:
                    blk["meas"].append(m)

        # ── turn blocks into component rows ──────────────────────
        #  PASSIVE (RES CAP JUM MEA ...): one row per measurement, judged
        #      against its lower / upper limit.
        #  ACTIVE  (DIO ZEN NFE PFE MEA): one row per block, limits shown as NA,
        #      result taken ONLY from the block code (00 = PASS, else FAIL).
        ACTIVE = ("DIO", "ZEN", "NFE", "PFE", "MEA")

        # The board result (@BTEST code) is authoritative: when the tester
        # passed the board (00), block-level codes do not make a component
        # fail. Only a measurement really outside its limits still does.
        if meta.get("board_code") == "00":
            ignored = sum(1 for b in blocks
                          if b["tester_fail"] or any(c != "00" for c, _ in b["tjet"]))
            for b in blocks:
                b["tester_fail"] = False
                b["tjet"] = [("00", r) for _, r in b["tjet"]]
            if ignored:
                parse_log.append(
                    f"  → Board result is PASS (@BTEST 00): {ignored} block(s) "
                    f"with a non-00 block code were counted as PASS")
        entries = []
        for b in blocks:
            act = [m for m in b["meas"] if m["kind"] in ACTIVE]
            pas = [m for m in b["meas"] if m["kind"] not in ACTIVE]
            oks     = [self._in_limits(m["meas"], m["upper"], m["lower"])
                       for m in pas]
            any_out = any(ok is False for ok in oks)
            for m, ok in zip(pas, oks):
                if ok is False:
                    status, note = "FAIL", self._limit_reason(m)
                elif b["tester_fail"] and not any_out and not act:
                    status = "FAIL"
                    note = (f"Readings within limits, but tester marked "
                            f"this block FAIL (code {b['code']})")
                else:
                    status, note = "PASS", ""
                entries.append((b, m, status, note))
            if act:
                kinds = [m["kind"] for m in act]
                kind  = ("ZEN" if "ZEN" in kinds else
                         "NFE" if "NFE" in kinds else
                         "PFE" if "PFE" in kinds else
                         "DIO" if "DIO" in kinds else "MEA")
                summ  = {"meas": None, "label": "", "kind": kind, "active": True,
                         "nominal": None, "upper": None, "lower": None}
                if b["tester_fail"]:
                    status, note = "FAIL", self._active_reason(kind, b, act)
                else:
                    status, note = "PASS", ""
                entries.append((b, summ, status, note))
            if not b["meas"] and not b["tjet"] and b["tester_fail"]:
                entries.append((b, None, "FAIL",
                                f"Tester marked this block FAIL (code {b['code']}), "
                                f"no measurement recorded"))

            # TESTJET: one summary row (block code) + one row per device
            if b["tjet"]:
                bad = b["tester_fail"] or any(c != "00" for c, _ in b["tjet"])
                base_m = {"meas": None, "label": "", "kind": "TJ", "active": True,
                          "nominal": None, "upper": None, "lower": None}
                entries.append((b, dict(base_m, tj_summary=True),
                                "FAIL" if bad else "PASS",
                                (f"Testjet FAILED (code {b['code']})")
                                if bad else ""))
                for tcode, tref in b["tjet"]:
                    dev = {"base": tref.upper(), "tag": "testjet",
                           "tester_fail": tcode != "00", "meas": [], "tjet": []}
                    entries.append((dev, dict(base_m, tj_device=True),
                                    "FAIL" if tcode != "00" else "PASS",
                                    (f"Testjet FAILED on {tref.upper()} "
                                     f"(code {tcode})")
                                    if tcode != "00" else ""))

        # The tester may split one part (e.g. U16%diode) over several blocks:
        # merge active rows with the same ref + tag; FAIL if any part failed.
        merged, seen = [], {}
        for b, m, status, note in entries:
            if m and m.get("active"):
                key = (b["base"], b["tag"], m["kind"])
                if key in seen:
                    i = seen[key]
                    ob, om, ost, onote = merged[i]
                    if status == "FAIL":
                        merged[i] = (ob, om, "FAIL", note)
                    continue
                seen[key] = len(merged)
            merged.append((b, m, status, note))
        entries = merged

        # ── unique, readable refs (only when a ref repeats) ──────
        from collections import Counter
        counts = Counter(b["base"] for b, _, _, _ in entries)
        used   = Counter()
        components = []
        for b, m, status, note in entries:
            ref = b["base"]
            if m and m.get("tj_device"):
                ref = f"{ref} (testjet)"
            elif counts[ref] > 1:
                bits = [t for t in (b["tag"], m["label"] if m else "") if t]
                if bits:
                    ref = f"{ref} ({' / '.join(bits)})"
            used[ref] += 1
            if used[ref] > 1:
                ref = f"{ref} #{used[ref]}"
            if m:
                c = self._make_comp(ref, status, m["meas"], m["nominal"],
                                    m["upper"], m["lower"], note=note,
                                    ctype=self._type_for(b["base"], m["kind"]),
                                    active=m.get("active", False))
            else:
                c = self._make_comp(ref, status, None, None, None, None,
                                    note=note,
                                    ctype=self._infer_type(b["base"]))
            c["base"] = b["base"]          # physical part this row belongs to
            components.append(c)
            if status == "FAIL":
                parse_log.append(
                    f"  → {c['ref']}: FAIL  "
                    f"[meas={c['measured']}  nom={c['nominal']}]  {note}")

        if not components:
            raise ValueError(
                f"File parsed as Keysight ICT but no @BLOCK components found.\n"
                f"File: {os.path.basename(filepath)}")

        if meta.get("board_fail"):
            parse_log.insert(0, f"  → BOARD: tester result code "
                                f"{meta['board_code']} (FAIL)")

        meta.setdefault("board_name",
                        os.path.splitext(os.path.basename(filepath))[0])
        meta.setdefault("serial",
                        f"SN{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")

        return self._build(meta, components,
                           parse_log, filepath, "Keysight ICT")

    def _parse_measurement(self, line: str):
        """Parse one @A-xxx line, with or without a text label.
        {@A-MEA|0|+2.97E+00|FET_OFF{@LIM2|+3.5E+00|+1.5E+00}}"""
        body    = line.lstrip("{")
        lim_idx = body.find("@LIM")
        head    = body[:lim_idx] if lim_idx >= 0 else body
        parts   = head.rstrip("{} ").split("|")
        if len(parts) < 3:
            return None
        try:
            meas = float(parts[2])
        except ValueError:
            return None
        label = parts[3].strip() if len(parts) > 3 else ""
        km   = re.search(r"@A-([A-Z]+)", head)
        kind = km.group(1) if km else ""
        nominal = upper = lower = None
        if lim_idx >= 0:
            lp = body[lim_idx:].rstrip("} ").split("|")
            try:
                if lp[0] == "@LIM3" and len(lp) >= 4:
                    nominal, upper, lower = (float(x) for x in lp[1:4])
                elif lp[0] == "@LIM2" and len(lp) >= 3:
                    upper, lower = (float(x) for x in lp[1:3])
            except ValueError:
                pass
        return {"meas": meas, "label": label, "kind": kind,
                "nominal": nominal, "upper": upper, "lower": lower}

    # ── FAILURE REASONS (shown in the "Why it failed" column) ─────
    _KIND_NAME = {"RES": "Resistor", "CAP": "Capacitor", "JUM": "Jumper",
                  "DIO": "Diode", "ZEN": "Zener diode", "NFE": "N-FET",
                  "PFE": "P-FET", "MEA": "Measurement", "TJ": "Testjet"}

    def _limit_reason(self, m):
        """Plain-English reason for a passive part measured out of limits."""
        meas, kind = m["meas"], m["kind"]
        vals = [v for v in (m["upper"], m["lower"]) if v is not None]
        hi, lo = max(vals), min(vals)
        if hi >= 1e90: hi = None
        if lo <= -1e90: lo = None
        if lo is not None and meas < lo:
            side, lim, word = "BELOW the lower limit", lo, "low"
        else:
            side, lim, word = "ABOVE the upper limit", hi, "high"
        txt = f"Measured {self._fmt(meas)} is {side} of {self._fmt(lim)}"
        nom = m["nominal"]
        if nom is not None and abs(nom) < 1e90 and nom != 0:
            pct = (meas - nom) / abs(nom) * 100
            txt += f" (nominal {self._fmt(nom)}, {pct:+.1f}%)"
        return txt

    def _active_reason(self, kind, b, act):
        """Reason for a diode / zener / transistor / MEA block the tester failed."""
        name = self._KIND_NAME.get(kind, "Active")
        txt = f"{name} test FAILED (tester code {b['code']})"
        for m in act:
            if kind == "MEA" and m["kind"] == "MEA" and \
                    self._in_limits(m["meas"], m["upper"], m["lower"]) is False:
                vals = [v for v in (m["upper"], m["lower"]) if v is not None]
                txt += (f"; {m['label'] or 'reading'} = {self._fmt(m['meas'])} "
                        f"(limits {self._fmt_limit(min(vals))} to "
                        f"{self._fmt_limit(max(vals))})")
                break
        return txt

    @staticmethod
    def _parse_test_dt(raw):
        """@BTEST test start time 'YYMMDDhhmmss' -> datetime, or None."""
        s = (raw or "").strip(" }")
        if len(s) != 12 or not s.isdigit():
            return None
        try:
            return datetime.datetime.strptime(s, "%y%m%d%H%M%S")
        except ValueError:
            return None

    @staticmethod
    def _in_limits(meas, upper, lower):
        """True / False, or None when there are no usable limits.
        A 9.999999E+99 limit means 'no limit on that side'."""
        vals = [v for v in (upper, lower) if v is not None]
        if len(vals) < 2:
            return None
        lo, hi = min(vals), max(vals)
        if lo <= -1e90: lo = None
        if hi >=  1e90: hi = None
        if lo is None and hi is None:
            return None
        if lo is not None and meas < lo: return False
        if hi is not None and meas > hi: return False
        return True

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
        return self._build(meta, components, parse_log, filepath, "CSV")

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
        return self._build(meta, components, parse_log, filepath, "Generic Text")

    # ── HELPERS ───────────────────────────────────────────────────
    def _clean_serial(self, raw: str, board_name: str = "") -> str:
        """Extract just the serial number from a raw serial string.
        e.g. 'SN_TEJAS_RWR_1004_260504_FAIL' → 'SN1004'
        """
        s = raw.strip()
        # Remove PASS/FAIL suffix
        for suffix in ("_PASS", "_FAIL", "-PASS", "-FAIL"):
            if s.upper().endswith(suffix):
                s = s[:len(s)-len(suffix)]
        # Remove board name prefix if present
        if board_name:
            # Try variations: exact, underscored, partial
            for bn in [board_name, board_name.replace(" ","_")]:
                for prefix_fmt in [f"SN_{bn}_", f"SN_{bn[:10]}_", f"SN_{bn[:9]}_"]:
                    if s.startswith(prefix_fmt):
                        s = s[len(prefix_fmt):]
                        break
        # Remove trailing date-like patterns (6+ digits at end: YYMMDD or YYMMDDHHMMSS)
        m = re.match(r'^(\d+)_\d{6,}$', s)
        if m:
            s = m.group(1)
        # If we still have the original messy string, find the core serial number
        nums = re.findall(r'\d{3,}', s)
        if nums:
            return f"SN{nums[0]}"
        # Fallback: return cleaned string
        return s if s else raw

    def _fmt(self, val):
        if val is None: return "—"
        v = abs(val)
        if v >= 1e90: return "—"  # sentinel / extreme value
        if v >= 1e9:  return f"{val/1e9:.3f}G"
        if v >= 1e6:  return f"{val/1e6:.3f}M"
        if v >= 1e3:  return f"{val/1e3:.3f}k"
        if v >= 1:    return f"{val:.4f}"
        if v >= 1e-3: return f"{val*1e3:.4f}m"
        if v >= 1e-6: return f"{val*1e6:.4f}µ"
        if v >= 1e-9: return f"{val*1e9:.4f}n"
        if v >= 1e-12: return f"{val*1e12:.4f}p"
        if v >= 1e-15: return f"{val*1e15:.4f}f"
        if v == 0:    return "0"
        return f"{val:.4e}"

    def _type_for(self, base: str, kind: str) -> str:
        """Component type from the @A-xxx measurement kind first,
        falling back to the reference-designator prefix."""
        b = base.lower()
        if kind == "TJ": return "Testjet"
        if kind == "ZEN": return "Zener Diode"
        if kind in ("NFE", "PFE"): return "Transistor"
        if kind == "DIO":
            return "Transistor" if b.startswith("q") else "Diode"
        if kind == "RES": return "Resistor"
        if kind == "CAP": return "Capacitor"
        if kind == "JUM":
            if b.startswith("r"): return "Jumper Resistor"
            if b.startswith("j"): return "Connector"
        return self._infer_type(base)

    def _fmt_limit(self, v):
        if v is None: return "—"
        if v >=  1e90: return "∞"
        if v <= -1e90: return "-∞"
        return self._fmt(v)

    def _infer_type(self, ref: str) -> str:
        r = ref.lower()
        if r.startswith("testjet"): return "Testjet"
        if r.startswith("cr"): return "Diode"
        if r.startswith("r"):  return "Resistor"
        if r.startswith("c"):  return "Capacitor"
        if r.startswith("l"):  return "Inductor"
        if r.startswith("u"):  return "IC"
        if r.startswith("q"):  return "Transistor"
        if r.startswith("d"):  return "Diode"
        if r.startswith("t"):  return "Transformer"
        if r[0] in ("j","p","k","e"): return "Connector"
        return "Component"

    def _make_comp(self, ref, status, meas, nominal_val, upper, lower,
                   note=None, ctype=None, active=False):
        ctype = ctype or self._infer_type(ref)
        nominal = "—"; dev = "—"

        if active:      # diode / zener / transistor: PASS-FAIL only
            return {"ref": ref, "type": ctype, "nominal": "NA",
                    "measured": "NA", "deviation": "—",
                    "lower_limit": "NA", "upper_limit": "NA",
                    "status": status,
                    "note": note if note is not None else ""}

        lower_s = upper_s = "—"
        if upper is not None and lower is not None:
            lower_s = self._fmt_limit(min(upper, lower))
            upper_s = self._fmt_limit(max(upper, lower))

        # Use actual nominal from @LIM3 if available
        if nominal_val is not None and abs(nominal_val) < 1e90:
            nominal = self._fmt(nominal_val)
            if nominal_val != 0 and meas is not None:
                pct = (meas - nominal_val) / abs(nominal_val) * 100
                dev = f"{'+' if pct >= 0 else ''}{pct:.1f}%"
        elif meas is not None and upper is not None and lower is not None:
            lo = min(upper, lower); hi = max(upper, lower)
            # Skip extreme sentinel values
            if hi < 1e90 and lo > -1e90:
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
            "lower_limit": lower_s,
            "upper_limit": upper_s,
            "status": status,
            "note": note if note is not None else
                    ("Out of tolerance" if status == "FAIL" else ""),
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
    def _build(self, meta, components,
               parse_log, filepath, fmt) -> dict:
        # Count PHYSICAL COMPONENTS, not test rows: a part that has several
        # measurements (or a testjet + device rows) counts once, and it is
        # FAIL if any of its tests failed.
        parts = {}
        for c in components:
            key = c.get("base") or c["ref"]
            parts[key] = parts.get(key, False) or c["status"] == "FAIL"
        total  = len(parts)
        failed = sum(1 for bad in parts.values() if bad)
        passed = total - failed
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
            "Zener Diode": "In-Circuit", "Jumper Resistor": "Resistance",
            "Testjet": "Testjet",
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

        # Board result: the tester's @BTEST code is authoritative when the
        # file has one (00 = PASS, anything else = FAIL); otherwise derive it.
        if meta.get("board_code") is not None:
            board_status = "PASS" if meta["board_code"] == "00" else "FAIL"
        else:
            board_status = "FAIL" if failed > 0 else "PASS"

        # Test time: the tester's own start time when the file has one,
        # otherwise the file's last-modified time, otherwise now.
        test_dt = meta.get("test_dt")
        if test_dt is None:
            try:
                test_dt = datetime.datetime.fromtimestamp(
                    os.path.getmtime(filepath))
            except Exception:
                test_dt = datetime.datetime.now()

        insights = []
        if failed > 0 and board_status == "FAIL":
            insights.append(
                f"WARNING: {failed} component(s) failed — board requires rework")
        if failed > 0 and board_status == "PASS":
            refs = ", ".join(c["ref"] for c in failed_detail[:6])
            insights.append(
                f"NOTE: Tester result is PASS (@BTEST code 00) but {failed} "
                f"block(s) are flagged FAIL: {refs} — verify the file")
        if meta.get("board_fail") and failed == 0:
            insights.append(
                f"WARNING: Tester marked this board FAIL "
                f"(@BTEST code {meta.get('board_code')}) but no measurement is "
                f"out of limits — check digital / testjet results or an "
                f"aborted run")
        if rate < 98:
            insights.append(
                f"WARNING: Pass rate {rate:.1f}% is below 98% threshold")

        return {
            "format":   fmt,
            "parser_version": self.VERSION,
            "filepath": filepath,
            "summary": {
                "board_name": meta.get("board_name", "Unknown"),
                "serial":     meta.get("serial", "—"),
                "total":      total,
                "passed":     passed,
                "failed":     failed,
                "pass_rate":  rate,
                "status":     board_status,
                "test_time":  test_dt.strftime("%H:%M:%S"),
                "timestamp":  test_dt.isoformat(timespec="seconds"),
            },
            "components":       components,
            "failed_detail":    failed_detail,
            "component_types":  comp_types,
            "test_types":       test_types,
            "top_failures":     top_failures,
            "insights":         insights,
            "parse_log":        parse_log,
        }
