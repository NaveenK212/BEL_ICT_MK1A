# ICT Report Analyzer

A professional desktop GUI application for processing ICT (In-Circuit Test) report files.
Built with Python, CustomTkinter, Matplotlib, and ReportLab.

---

## Features

- **File Input** — Load any `.ict`, `.txt`, `.csv`, or `.log` ICT report file
- **Live Console** — Timestamped processing log streamed in real time
- **Summary Dashboard** — Board name, serial, pass/fail status, pass rate
- **4 Embedded Charts** — Donut overview, component bar, test type bar, Pareto chart
- **3 Data Tables** — Component results, failed components, power supply rails
- **Insights Bar** — Auto-generated warnings and risk flags
- **PDF Reports** — Saved to `~/Desktop/ICT_Reports/<BoardName>/`
- **SQLite Database** — All runs stored in `~/Desktop/ICT_Reports/ict_results.db`
- **Analytics Window** — Pass rate trends, failure frequency, board comparison
- **Excel Export** — Export component data to `.xlsx`

---

## Installation

### 1. Clone / download this folder

```
ict_gui/
  app.py
  ict_parser.py
  db_manager.py
  report_generator.py
  analytics_window.py
  requirements.txt
  sample_report.ict
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

---

## Quick Start

1. Click **Select File** → choose `sample_report.ict` (included) to try it out
2. Click **Generate Report** → watch the console, charts, and tables populate
3. Click **Run Analytics** → view trends and board comparisons
4. Click **Export XLSX** → save component data to Excel

---

## Supported File Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| Agilent / Keysight 3070 | `.ict` `.txt` | Auto-detected via header keywords |
| Generic CSV | `.csv` | Columns: ref, type, nominal, measured, status |
| Generic text | `.txt` `.log` | Best-effort line parsing |
| Unknown | any | Falls back to generating realistic demo data |

### Sample ICT file structure (Agilent-style)

```
BOARD_NAME: MAIN-PCB-v2.3
SERIAL: SN20260428-001

R01, Resistor, 10000, 9970, PASS,
R23, Resistor, 4700, 5210, FAIL, High resistance drift
U12, IC, LM358, fail_output_offset, FAIL, Offset exceeded

VCC, 3.300V, 3.312V, PASS
VREF, 2.495V, 2.411V, FAIL
```

---

## Output Files

All output is saved under `~/Desktop/ICT_Reports/`:

```
~/Desktop/ICT_Reports/
  ict_results.db                          ← SQLite database (all runs)
  MAIN-PCB-v2.3/
    SN20260428-001_20260428_142311.pdf    ← PDF report
  CTRL-BOARD-v1.1/
    SN20260425-002_20260425_113012.pdf
```

---

## Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| customtkinter | ≥ 5.2 | Modern dark-mode GUI |
| matplotlib | ≥ 3.8 | Embedded charts |
| reportlab | ≥ 4.1 | PDF generation |
| openpyxl | ≥ 3.1 | Excel export |
| numpy | ≥ 1.26 | Chart calculations |
| Pillow | ≥ 10.0 | CustomTkinter dependency |

> **Note:** If `reportlab` is not installed, reports are saved as `.txt` instead of `.pdf`.
> If `openpyxl` is not installed, Excel export shows an installation prompt.

---

## Database Schema

```sql
runs (id, board_name, serial, timestamp, total, passed, failed, pass_rate, status, filepath)
components (id, run_id, ref, type, nominal, measured, deviation, status, note)
power_rails (id, run_id, rail, nominal, measured, deviation, ripple, status)
```

---

## Python Version

Requires **Python 3.10+**. Tested on Windows 10/11, macOS 13+, Ubuntu 22.04.
