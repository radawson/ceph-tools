# Quick Reference: Which Script Should I Use?

## File Overview

| File | Purpose | Dependencies | Size |
|------|---------|--------------|------|
| `osd_core.py` | Core data collection | None | ~500 lines |
| `check-osd-plain.py` | Plain text output | None (uses osd_core) | ~400 lines |
| `check-osd-rich.py` | Beautiful output + export | rich, pandas, openpyxl | ~600 lines |
| `check-osd2.py` | Original fixed version | None | ~650 lines |
| `check-osd-rich-pandas.py` | Monolithic Rich+Pandas | rich, pandas, openpyxl | ~1000 lines |

---

## Decision Tree

```
Do you want modular architecture?
│
├─ YES → Use osd_core.py + frontend
│   │
│   ├─ Do you need colors/visual output?
│   │   ├─ YES → check-osd-rich.py (requires: rich, pandas)
│   │   └─ NO  → check-osd-plain.py (no dependencies)
│   │
│   └─ Want to build your own frontend?
│       └─ Import osd_core.py in your script
│
└─ NO (want standalone)
    │
    ├─ Need colors/export? → check-osd-rich-pandas.py
    └─ Plain text only?    → check-osd2.py
```

---

## Use Case Guide

### For Daily Monitoring (Interactive)

**Recommended: `check-osd-rich.py`**

```bash
pip install rich pandas openpyxl
sudo python3 check-osd-rich.py
```

**Why?**
- Beautiful color-coded output
- Problems jump out visually
- Auto-export to CSV, JSON, Excel
- Historical tracking
- Modular (uses core)

**Output:**
```
🖥️  Ceph OSD Drive Inventory & Status
┌─────┬──────────┬─────────┬────────────┬────────┐
│ OSD │ Status   │ Latency │ SCSI Addr  │ Temp   │
├─────┼──────────┼─────────┼────────────┼────────┤
│ 50  │ up in ✓  │ 52ms    │ 0:0:0:0    │ 26°C   │  (green)
│ 1   │ up in ✓  │ 113ms   │ 0:0:4:0    │ 26°C   │  (yellow - warning!)
└─────┴──────────┴─────────┴────────────┴────────┘
```

---

### For Automation/Scripts (Cron)

**Recommended: `check-osd-plain.py`**

```bash
# No installation needed!
sudo python3 check-osd-plain.py --export-csv
```

**Why?**
- Zero dependencies (except Python stdlib)
- Fast and lightweight
- CSV/JSON export on demand
- Works in minimal environments
- Modular (uses core)

**Cron Example:**
```bash
0 * * * * cd /root && python3 check-osd-plain.py --export-csv >> /var/log/osd.log 2>&1
```

---

### For One-Time Fix (Just Want It Working)

**Recommended: `check-osd2.py`**

```bash
# No installation needed!
sudo python3 check-osd2.py
```

**Why?**
- Single file, standalone
- No dependencies
- Fixed all the bugs
- Drop-in replacement for original

**Use if:**
- You don't want to change anything
- You just need the bugs fixed
- You don't plan to extend it

---

### For Web Dashboard Development

**Recommended: `osd_core.py` + custom frontend**

```python
from osd_core import OSDMonitor
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/osds')
def get_osds():
    monitor = OSDMonitor()
    data = monitor.scan()
    return jsonify(data)
```

**Why?**
- Core module does the heavy lifting
- You control the output format
- Easy to integrate with any framework
- Pure Python core works anywhere

---

### For Management Reports

**Recommended: `check-osd-rich.py`**

```bash
pip install rich pandas openpyxl
sudo python3 check-osd-rich.py
```

**Why?**
- Auto-generates Excel file with 3 sheets:
  - Current Status
  - Summary Statistics
  - Problem Drives
- Perfect for sharing with management
- Professional formatting

**Output Files:**
- `osd_status_20251114_143022.xlsx` ← Send this to management

---

### For Building Historical Database

**Recommended: `check-osd-rich.py`**

```bash
# Run hourly via cron
0 * * * * cd /root && python3 check-osd-rich.py
```

**Why?**
- Automatically appends to `osd_history.csv`
- Tracks changes over time
- Foundation for trend analysis
- Can detect gradual degradation

**After 1 month:**
```bash
# 720 scans (hourly for 30 days)
wc -l osd_history.csv
# 7920 lines (11 drives × 720 scans)

# Analyze trends
python3 analyze_trends.py osd_history.csv
```

---

## Feature Comparison

### Core Features (All Scripts)

✅ Scan RAID controller  
✅ Get Ceph OSD metadata  
✅ Match drives to OSDs  
✅ SMART health monitoring  
✅ Performance metrics  
✅ **SCSI addresses for ALL drives** (FIXED!)  
✅ **Drive sizes for ALL drives** (FIXED!)  
✅ **No TypeError crash** (FIXED!)  

### Modular Scripts Only

| Feature | Plain | Rich |
|---------|-------|------|
| Uses osd_core | ✅ | ✅ |
| Pure Python fallback | ✅ | ✅ |
| Extensible | ✅ | ✅ |
| CSV export | CLI flag | Auto |
| JSON export | CLI flag | Auto |
| Excel export | ❌ | ✅ |
| Historical tracking | ❌ | ✅ |
| Color output | ❌ | ✅ |
| Visual hierarchy | ❌ | ✅ |

### Standalone Scripts

| Feature | check-osd2.py | check-osd-rich-pandas.py |
|---------|---------------|--------------------------|
| Single file | ✅ | ✅ |
| No dependencies | ✅ | ❌ (needs rich, pandas) |
| CSV export | ❌ | ✅ |
| JSON export | ❌ | ✅ |
| Excel export | ❌ | ✅ |
| Color output | ❌ | ✅ |
| Modular | ❌ | ❌ |

---

## Migration Path

### From Original Script

**Current:**
```bash
sudo python3 check-osd.py  # (crashes with TypeError)
```

**Quick Fix:**
```bash
sudo python3 check-osd2.py  # (fixed version)
```

**Better:**
```bash
sudo python3 check-osd-plain.py  # (modular)
```

**Best:**
```bash
pip install rich pandas openpyxl
sudo python3 check-osd-rich.py  # (beautiful + modular)
```

---

## Installation Commands

### Minimal (Plain Text)

```bash
# Copy files
cp osd_core.py /usr/local/bin/
cp check-osd-plain.py /usr/local/bin/check-osd

# Make executable
chmod +x /usr/local/bin/check-osd

# Run
sudo check-osd
```

### Full (Rich + Pandas)

```bash
# Install dependencies
pip3 install rich pandas openpyxl

# Copy files
cp osd_core.py /usr/local/bin/
cp check-osd-rich.py /usr/local/bin/check-osd

# Make executable
chmod +x /usr/local/bin/check-osd

# Run
sudo check-osd
```

### Both (Flexible)

```bash
# Install dependencies
pip3 install rich pandas openpyxl

# Copy all files
cp osd_core.py /usr/local/bin/
cp check-osd-plain.py /usr/local/bin/check-osd-plain
cp check-osd-rich.py /usr/local/bin/check-osd-rich

# Make executable
chmod +x /usr/local/bin/check-osd-*

# Use as needed
sudo check-osd-plain     # For scripts
sudo check-osd-rich      # For interactive
```

---

## Recommendations

### Best Overall Setup

**Install both frontends:**

```bash
# 1. Install dependencies
pip3 install rich pandas openpyxl

# 2. Set up for interactive use
cp osd_core.py /usr/local/bin/
cp check-osd-rich.py /usr/local/bin/check-osd
chmod +x /usr/local/bin/check-osd

# 3. Set up for automation
cp check-osd-plain.py /usr/local/bin/check-osd-auto
chmod +x /usr/local/bin/check-osd-auto

# 4. Interactive monitoring
sudo check-osd

# 5. Cron job (hourly CSV export)
echo "0 * * * * root check-osd-auto --export-csv" > /etc/cron.d/osd-monitor
```

**This gives you:**
- Beautiful interactive output (Rich)
- Lightweight automation (Plain)
- Historical tracking (Rich auto-saves)
- Hourly CSV exports (Plain cron)
- Single core module (easy to maintain)

---

## Summary Table

| Script | When to Use | Dependencies | Best For |
|--------|-------------|--------------|----------|
| **osd_core.py** | Building custom tools | None | Your own frontend |
| **check-osd-plain.py** | Scripts, cron, minimal systems | None | Automation |
| **check-osd-rich.py** | Daily monitoring, reports | rich, pandas | Interactive use |
| **check-osd2.py** | One-off replacement | None | Quick fix |
| **check-osd-rich-pandas.py** | Standalone full-featured | rich, pandas | All-in-one |

---

## My Recommendation

**Start with:**
1. `check-osd-rich.py` for interactive use
2. `check-osd-plain.py` for automation

**Why both?**
- Rich for daily troubleshooting (visual, beautiful)
- Plain for cron jobs (lightweight, efficient)
- Both use same core (consistent data)
- Modular architecture (easy to extend)

**Install:**
```bash
pip3 install rich pandas openpyxl
sudo python3 check-osd-rich.py  # Start using immediately!
```
