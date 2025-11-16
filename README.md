# Ceph OSD Drive Monitor - Complete Package

version 1.0.3

## 📋 All Files Index

### 🐍 Python Scripts (5 files, 119 KB total)

| File | Size | Dependencies | Purpose |
|------|------|--------------|---------|
| **osd_core.py** | 23 KB | None | Core data collection module (import this) |
| **check-osd-plain.py** | 15 KB | None | Plain text frontend (for automation) |
| **check-osd-rich.py** | 19 KB | rich, pandas | Beautiful frontend (for interactive use) |
| **check-osd2.py** | 25 KB | None | Standalone fixed version (drop-in replacement) |
| **check-osd-rich-pandas.py** | 37 KB | rich, pandas | Monolithic Rich+Pandas (all-in-one) |

### 📚 Documentation (10 files, 86 KB total)

| File | Size | What's Inside |
|------|------|---------------|
| **DELIVERABLES.md** | 11 KB | ⭐ **START HERE** - Complete summary of everything |
| **MODULAR_ARCHITECTURE.md** | 13 KB | How the modular system works + API reference |
| **WHICH_SCRIPT.md** | 8.3 KB | Decision guide - which script to use when |
| **QUICK_START.md** | 6.9 KB | Get running in 5 minutes |
| **INSTALLATION_GUIDE.md** | 7.1 KB | Detailed setup and usage instructions |
| **CHANGELOG.md** | 8.1 KB | What changed from original (before/after) |
| **LIBRARY_COMPARISON.md** | 8.6 KB | Why Rich vs Pandas vs Plain Python |
| **CODE_COMPARISON.md** | 16 KB | Side-by-side code examples |
| **DECISION_GUIDE.md** | 4.8 KB | Library selection flowchart |
| **BUG_FIXES_SUMMARY.md** | 3.1 KB | Technical details of bug fixes |

---

## 📦 System Requirements

### Required OS Packages

These system packages must be installed on all nodes:

```bash
# Install all required packages
sudo apt update
sudo apt install -y smartmontools lsscsi sg3-utils ledmon
```

**Package Details:**

| Package | Purpose | Used By |
|---------|---------|---------|
| **smartmontools** | Provides `smartctl` for drive SMART data | All scripts |
| **lsscsi** | Lists SCSI devices and topology | All scripts |
| **sg3-utils** | Provides `sg_ses` for enclosure management | Enclosure bay mapping & LED control |
| **ledmon** | Provides `ledctl` for LED control (optional) | LED blinking feature |
| **ceph** | Ceph cluster commands | All scripts (already installed) |

**Pre-installed (no action needed):**
- `lsblk` - Block device info (from util-linux)
- `systemctl` - Service status (from systemd)
- `pvs`, `lvs` - LVM info (from lvm2)

### Optional Python Dependencies

For the Rich/Pandas versions only:

```bash
pip3 install rich pandas openpyxl
```

| Package | Size | Purpose |
|---------|------|---------|
| **rich** | ~500 KB | Beautiful color output |
| **pandas** | ~30 MB | Data analysis |
| **openpyxl** | ~2 MB | Excel export |

---

## 🚀 Quick Start (Choose Your Path)

### Path A: Minimal (System Dependencies Already Installed)

```bash
# 1. Copy files
cp osd_core.py check-osd-plain.py /home/torvaldsl/

# 2. Run
cd /home/torvaldsl
sudo python3 check-osd-plain.py
```

**Get:** Plain text output, CSV/JSON export on demand

---

### Path B: Full Featured (Recommended)

```bash
# 1. Install dependencies (one time)
pip3 install rich pandas openpyxl

# 2. Copy files
cp osd_core.py check-osd-rich.py /home/torvaldsl/

# 3. Run
cd /home/torvaldsl
sudo python3 check-osd-rich.py
```

**Get:** Beautiful colors, auto-export (CSV, JSON, Excel), historical tracking

---

### Path C: Just Fix Original

```bash
# 1. Copy file
cp check-osd2.py /home/torvaldsl/

# 2. Run
cd /home/torvaldsl
sudo python3 check-osd2.py
```

**Get:** Same as original but bugs fixed

---

## 🎯 Reading Guide

### If You Want To...

**Get started immediately:**
→ Read **DELIVERABLES.md** (this has everything)

**Understand the architecture:**
→ Read **MODULAR_ARCHITECTURE.md**

**Choose which script to use:**
→ Read **WHICH_SCRIPT.md**

**Install and configure:**
→ Read **INSTALLATION_GUIDE.md**

**See what changed:**
→ Read **CHANGELOG.md**

**Understand library choices:**
→ Read **LIBRARY_COMPARISON.md**

**See code examples:**
→ Read **CODE_COMPARISON.md**

---

## ✅ What's Fixed

### Bug #1: TypeError Crash
- **Before:** Script crashed on line 580
- **After:** Completes successfully
- **Fix:** Changed `smart.get('key', 0)` to `(smart.get('key') or 0)`

### Bug #2: Missing SCSI Addresses
- **Before:** Only 5/11 drives showed SCSI addresses
- **After:** ALL 11 drives show SCSI addresses
- **Fix:** Generate from PHY ID for unmapped drives

### Bug #3: Missing Drive Sizes
- **Before:** Unmapped drives showed "N/A" for size
- **After:** All drives show sizes
- **Fix:** Extract from smartctl `user_capacity` field

---

## 🏗️ Architecture

```
osd_core.py          ← Pure Python core (data collection)
     │
     ├──→ check-osd-plain.py      ← Plain text frontend
     ├──→ check-osd-rich.py       ← Rich+Pandas frontend
     └──→ your_custom_frontend.py ← Build your own!

Standalone alternatives:
     • check-osd2.py              ← Fixed original
     • check-osd-rich-pandas.py   ← Monolithic Rich+Pandas
```

**Benefits:**
- Core is reusable across frontends
- Easy to test and maintain
- Can add new frontends without changing core
- Single source of truth for data collection

---

## 📊 Feature Matrix

| Feature | Plain | Rich | Fixed Original | Monolithic |
|---------|-------|------|----------------|------------|
| No dependencies | ✅ | ❌ | ✅ | ❌ |
| Modular | ✅ | ✅ | ❌ | ❌ |
| Color output | ❌ | ✅ | ❌ | ✅ |
| CSV export | CLI flag | Auto | ❌ | Auto |
| JSON export | CLI flag | Auto | ❌ | Auto |
| Excel export | ❌ | ✅ | ❌ | ✅ |
| Historical tracking | ❌ | ✅ | ❌ | ✅ |
| SCSI for all drives | ✅ | ✅ | ✅ | ✅ |
| Sizes for all drives | ✅ | ✅ | ✅ | ✅ |
| No crashes | ✅ | ✅ | ✅ | ✅ |

---

## 💾 Output Files (Rich Version)

When you run `check-osd-rich.py`, you get:

1. **osd_status_YYYYMMDD_HHMMSS.csv**
   - Complete data in CSV format
   - Import into databases or Excel

2. **osd_status_YYYYMMDD_HHMMSS.json**
   - JSON format for web APIs
   - Perfect for your web dashboard

3. **osd_status_YYYYMMDD_HHMMSS.xlsx**
   - Excel workbook with 3 sheets:
     - Current Status (full inventory)
     - Summary (statistics)
     - Problem Drives (alerts)

4. **osd_history.csv**
   - Cumulative history (appends each run)
   - Foundation for trend analysis

---

## 🔧 Use Cases

### Daily Monitoring
```bash
sudo python3 check-osd-rich.py
```
Beautiful color output, see problems at a glance

### Automation/Cron
```bash
sudo python3 check-osd-plain.py --export-csv
```
Lightweight, no dependencies, CSV for analysis

### Management Reports
```bash
sudo python3 check-osd-rich.py
# Send the .xlsx file to management
```
Professional Excel report with summary

### Web Dashboard
```python
from osd_core import OSDMonitor
# Build your custom API/UI
```
Import core module, use data however you want

---

## 📈 Typical Workflow

**Week 1: Setup**
```bash
# Install dependencies
pip3 install rich pandas openpyxl

# Run manually to verify
sudo python3 check-osd-rich.py

# Review output files
ls -lh osd_status_*
```

**Week 2: Automation**
```bash
# Set up hourly cron job
sudo crontab -e
# Add: 0 * * * * cd /root && python3 check-osd-rich.py
```

**Week 3-4: Collect Data**
```bash
# Let it run, building osd_history.csv
# 168 scans (hourly for 1 week)
# 11 drives × 168 = 1,848 records
```

**Month 2: Analysis**
```bash
# Now you have trend data
wc -l osd_history.csv
# 5,000+ records

# Analyze trends
python3 analyze_trends.py osd_history.csv
```

**Month 3: Dashboard**
```python
# Build web dashboard using JSON exports
# Flask/FastAPI backend
# React/Vue frontend
# Real-time charts from osd_history.csv
```

---

## 🎓 Learning Path

### Beginner
1. Read **DELIVERABLES.md**
2. Run **check-osd-plain.py**
3. Read **QUICK_START.md**

### Intermediate
1. Install Rich+Pandas
2. Run **check-osd-rich.py**
3. Read **MODULAR_ARCHITECTURE.md**
4. Set up cron job

### Advanced
1. Import **osd_core.py** in your code
2. Read **CODE_COMPARISON.md**
3. Build custom frontend
4. Create web dashboard

---

## 🚨 Important Notes

### Must Run as Root
```bash
sudo python3 check-osd-*.py
```
Required for:
- Accessing RAID controller
- Running smartctl commands
- Querying Ceph cluster

### Dependencies (Rich Version)
```bash
pip3 install rich pandas openpyxl
```
Total size: ~32 MB
- rich: ~500 KB (colors, formatting)
- pandas: ~30 MB (data analysis)
- openpyxl: ~2 MB (Excel export)

### Compatibility
- Python 3.6+
- Linux (Ubuntu 24)
- MegaRAID/PERC controllers
- Ceph cluster

---

## 🎁 Bonus Content

### All Documentation Includes:
- Complete architecture diagrams
- API reference
- Code examples
- Integration guides
- Troubleshooting sections
- Best practices
- Future enhancement ideas

### All Scripts Include:
- Inline comments
- Error handling
- Debug mode
- Progress indicators
- Help text
- Professional formatting

---

## 📞 Support

### Troubleshooting
Check the documentation:
- **QUICK_START.md** - Common issues
- **INSTALLATION_GUIDE.md** - Setup problems
- **WHICH_SCRIPT.md** - Choosing the right tool

### Testing
```bash
# Test core module
sudo python3 osd_core.py

# Test plain frontend
sudo python3 check-osd-plain.py

# Test rich frontend (if installed)
sudo python3 check-osd-rich.py
```

---

## 📦 File Sizes

**Total Package:** 205 KB
- Scripts: 119 KB (5 files)
- Documentation: 86 KB (10 files)

**Minimal Install:** 38 KB
- osd_core.py: 23 KB
- check-osd-plain.py: 15 KB

**Full Install:** 42 KB
- osd_core.py: 23 KB
- check-osd-rich.py: 19 KB
- (plus ~32 MB dependencies)

---

## ⭐ Highlights

### What Makes This Special

1. **Modular Architecture**
   - Core separate from frontends
   - Easy to maintain
   - Easy to extend

2. **No Vendor Lock-in**
   - Pure Python core
   - Choose your dependencies
   - Build your own frontend

3. **Production Ready**
   - All bugs fixed
   - Comprehensive error handling
   - Well documented
   - Tested and working

4. **Future Proof**
   - Historical tracking
   - JSON exports for APIs
   - Foundation for web dashboard
   - Extensible design

---

## 🎯 Recommended Setup

**For most users:**
```bash
# 1. Install dependencies
pip3 install rich pandas openpyxl

# 2. Use both frontends
cp osd_core.py check-osd-rich.py check-osd-plain.py /usr/local/bin/

# 3. Daily monitoring (interactive)
sudo python3 check-osd-rich.py

# 4. Automation (cron)
sudo python3 check-osd-plain.py --export-csv
```

**You get:**
- Beautiful interactive output (Rich)
- Lightweight automation (Plain)
- Historical tracking (auto)
- Export to all formats
- Single core to maintain

---

## 🏁 Final Notes

**You now have a complete, professional Ceph OSD monitoring system:**
- ✅ All bugs fixed
- ✅ Modular architecture
- ✅ Multiple frontends
- ✅ Comprehensive documentation
- ✅ Production ready
- ✅ Extensible for future needs

**Everything is in `/mnt/user-data/outputs/`**

**Start with DELIVERABLES.md for the complete overview!**

Happy monitoring! 🎉
