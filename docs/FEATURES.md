# Enhanced OSD Monitor Script - New Features

## What's New in check-osd-enhanced.py

### 1. Shows ALL Physical Drives ✨
**Problem:** Old script only showed drives that were mapped to /dev/sdX  
**Solution:** Now shows every drive detected on RAID controller, even if not visible to OS

**Example:**
```
Old: Mapped 5/11 drives (6 hidden!)
New: Shows all 11 drives
     - 5 with /dev/sdX mappings
     - 6 showing "NOT MAPPED" (available for use!)
```

### 2. SMART Health Details 🔬
Adds critical health metrics for each drive:
- **Reallocated Sectors** - Bad sectors drive has remapped
- **Pending Sectors** - Sectors waiting to be remapped (failing!)
- **Uncorrectable Errors** - Unrecoverable data errors
- **Power-On Hours** - Drive age in hours/years
- **Temperature** - Current drive temperature
- **Load Cycle Count** - Head parking cycles

**New Columns:**
```
SMART Health | Temp  | Age
OK           | 26°C  | 5.7y
Realloc:12   | 45°C  | 8.2y  ← Replace this drive!
```

### 3. OSD Performance Metrics 📊
Shows real-time latency from `ceph osd perf`:
- **Commit Latency** - Time to commit write to journal
- **Apply Latency** - Time to apply write to disk

**New Column:**
```
Latency
53ms     ← Normal for HDD
140ms    ← Slow! Investigate
2ms      ← Fast SSD
```

### 4. Available Drives Section 🆕
Separate section showing drives ready for new OSDs:

```
DRIVES AVAILABLE FOR NEW OSDS (6)
  PHY 6: /dev/sdg - 3.0T - ST3000DM001-9YN166
    Serial: Z1F0MLQF, SCSI: N/A, Age: 2.1y, Temp: 28°C
    Command: sudo ceph-volume lvm create --data /dev/sdg
```

**Instant answers to:**
- "Which drives can I add as new OSDs?"
- "What's the exact command to add them?"

### 5. Intelligent Recommendations 🧠

#### A. Critical SMART Errors
```
⚠️ URGENT: Drives with SMART errors (REPLACE IMMEDIATELY!)
  OSD 22 (PHY 5): Realloc=12, Pending=3, Uncorr=1
```

#### B. High Latency Detection
```
⚠️ OSDs with high latency (>100ms):
  OSD 1: 140ms
    PHY 4, Age: 5.7y
```

Helps you decide **which drives to replace first**!

### 6. Enhanced Output Table

**Old format (80 chars):**
```
OSD ID | Status | Device | Size | Serial
```

**New format (160 chars):**
```
OSD ID | Status | Latency | SCSI Addr | Device | Size | PHY | Serial | HW | SMART | Temp | Age | Model
```

## Usage

```bash
# Run the enhanced version
sudo ./check-osd-enhanced.py

# Compare output
sudo ./check-osd.py              # Original
sudo ./check-osd-enhanced.py     # Enhanced
```

## Key Improvements

### Before (Original Script):
```
Summary:
  Physical drives: 11
  Drives with OSDs: 5
  
❌ 6 drives missing - where are they?
❌ Can't see drive health
❌ Can't see OSD performance  
❌ Don't know which drives to add
❌ Don't know which drives to replace
```

### After (Enhanced Script):
```
Summary:
  Physical drives: 11
  Drives with OSDs: 5
  Available for new OSDs: 6  ← Shows unmapped drives!
  
DRIVES AVAILABLE FOR NEW OSDS (6)
  [Lists each with command to add]

RECOMMENDATIONS
  ⚠️ URGENT: Drives with SMART errors
  ⚠️ OSDs with high latency
  
✅ See ALL drives
✅ See drive health (SMART)
✅ See OSD performance (latency)
✅ Know which to add (ready list)
✅ Know which to replace (recommendations)
```

## Real-World Example

### Scenario: You want to add 2 new OSDs to fs02

**With old script:**
```bash
$ sudo ./check-osd.py
Mapped 5/11 physical drives

# Now what? Where are the other 6 drives?
# Are they usable?
# What are their details?
# 🤷 No idea!
```

**With new script:**
```bash
$ sudo ./check-osd-enhanced.py
Available for new OSDs: 6

DRIVES AVAILABLE FOR NEW OSDS (6)
  PHY 6: /dev/sdg - 3.0T - ST3000DM001-9YN166
    Command: sudo ceph-volume lvm create --data /dev/sdg
  PHY 7: /dev/sdh - 3.0T - ST3000DM008-2DM166
    Command: sudo ceph-volume lvm create --data /dev/sdh

# Perfect! Just copy-paste these commands! ✨
```

### Scenario: Drive replacement decision

**Old script:**
```
OSD 1: up in ✓

# Should I replace this? 
# Is it old?
# Is it failing?
# Is it slow?
# 🤷 No idea!
```

**New script:**
```
OSD ID | Status    | Latency | SMART Health | Temp | Age  | Model
1      | up in ✓   | 140ms   | Realloc:12   | 45°C | 8.2y | SEAGATE ST8000

RECOMMENDATIONS
⚠️ URGENT: Drives with SMART errors (REPLACE IMMEDIATELY!)
  OSD 1 (PHY 4): Realloc=12, Pending=3, Uncorr=0

⚠️ OSDs with high latency (>100ms):
  OSD 1: 140ms (PHY 4, Age: 8.2y)

# ✅ Clear answer: YES! Replace OSD 1 ASAP!
# - It has reallocated sectors (failing!)
# - It's 3x slower than others
# - It's over 8 years old
```

## Technical Details

### SMART Data Collection
```python
def extract_smart_details(smart_info):
    """Extract critical SMART attributes"""
    - ID 5:   Reallocated_Sector_Ct
    - ID 9:   Power_On_Hours
    - ID 193: Load_Cycle_Count
    - ID 197: Current_Pending_Sector
    - ID 198: Offline_Uncorrectable
```

### Performance Integration
```python
# Gets live data from cluster
sudo ceph osd perf

# Parses latency for each OSD
# Flags anything >100ms as slow
```

### Unmapped Drive Detection
```python
# Old: Only showed drives with /dev/sdX
# New: Shows ALL drives from RAID controller
#      Marks unmapped as "NOT MAPPED"
#      Adds to "Available" list
```

## Migration Guide

### Keep Both Scripts:
```bash
# For quick check (original)
sudo ./check-osd.py

# For detailed analysis (enhanced)
sudo ./check-osd-enhanced.py
```

### Or Replace Completely:
```bash
# Backup old version
mv check-osd.py check-osd-old.py

# Use enhanced as default
mv check-osd-enhanced.py check-osd.py
```

## Performance Impact

**Additional data collected:**
- SMART details: +0.5s per drive
- OSD performance: +0.2s total
- Total overhead: ~5-6 seconds for 11 drives

**Worth it?** Absolutely! The insights gained far outweigh the extra time.

## Future Enhancements (Ideas)

1. **Historical tracking** - Store metrics over time
2. **Alerting** - Email when SMART errors detected
3. **Predictive failure** - ML-based failure prediction
4. **Capacity planning** - Show utilization trends
5. **Cross-host comparison** - Compare all hosts in cluster

## Summary

The enhanced script answers all the questions the original couldn't:

| Question | Original | Enhanced |
|----------|----------|----------|
| Where are my unmapped drives? | ❌ | ✅ |
| Which drives can I add as OSDs? | ❌ | ✅ |
| Which drives are failing? | ❌ | ✅ |
| Which drives are slow? | ❌ | ✅ |
| How old are my drives? | ❌ | ✅ |
| What should I replace first? | ❌ | ✅ |
| Ready-to-run commands? | ❌ | ✅ |

**Upgrade recommended!** 🚀