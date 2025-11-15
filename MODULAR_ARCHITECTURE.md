# Ceph OSD Drive Monitor - Modular Architecture

## Overview

This is a modular Ceph OSD monitoring system with a pure Python core and multiple frontend options.

```
┌─────────────────────────────────────────────────────────┐
│                   osd_core.py                           │
│         Pure Python - NO Dependencies                    │
│  • Scans RAID controller                                │
│  • Queries Ceph cluster                                 │
│  • Collects SMART data                                  │
│  • Matches drives to OSDs                               │
│  • Gets performance metrics                             │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Plain Text   │   │ Rich Output  │   │ Custom       │
│ Frontend     │   │ + Pandas     │   │ Frontend     │
│              │   │ Export       │   │ (Your own!)  │
│ No deps      │   │ Requires:    │   │              │
│ ✓ Always     │   │ • rich       │   │ Use core     │
│   works      │   │ • pandas     │   │ module API   │
└──────────────┘   └──────────────┘   └──────────────┘
```

## Architecture Benefits

1. **Core is pure Python** - Works anywhere, no dependencies
2. **Multiple frontends** - Choose what you need
3. **Easy to test** - Core logic separate from display
4. **Extensible** - Add your own frontend
5. **Maintainable** - One place for business logic

---

## Files

### Core Module (Required)

**`osd_core.py`** - Pure Python data collection
- No external dependencies
- Can be imported by any frontend
- Standalone testing mode
- ~500 lines, well-documented

### Frontend Options

**`check-osd-plain.py`** - Plain text output
- Uses osd_core for data collection
- No dependencies beyond core
- CSV/JSON export via command line
- Good for scripts and automation

**`check-osd-rich.py`** - Beautiful output + export
- Uses osd_core for data collection
- Requires: `rich`, `pandas`, `openpyxl`
- Color-coded visual output
- Auto-export to CSV, JSON, Excel
- Historical tracking

---

## Installation

### Minimal (Plain Text Only)

```bash
# No installation needed!
# Just need Python 3 and root access

sudo python3 check-osd-plain.py
```

### Full Featured (Rich + Pandas)

```bash
# Install dependencies
pip install rich pandas openpyxl

# Run it
sudo python3 check-osd-rich.py
```

---

## Usage

### Plain Text Version

```bash
# Basic scan (terminal output only)
sudo python3 check-osd-plain.py

# Export to CSV
sudo python3 check-osd-plain.py --export-csv

# Export to JSON
sudo python3 check-osd-plain.py --export-json

# Both
sudo python3 check-osd-plain.py --export-csv --export-json

# Custom filenames
sudo python3 check-osd-plain.py --csv-file my_scan.csv --json-file my_scan.json
```

### Rich + Pandas Version

```bash
# Full scan with beautiful output + auto export
sudo python3 check-osd-rich.py

# Skip export (display only)
sudo python3 check-osd-rich.py --no-export

# Skip historical tracking
sudo python3 check-osd-rich.py --no-history
```

### Using Core Module Programmatically

```python
#!/usr/bin/env python3
from osd_core import OSDMonitor

# Create monitor
monitor = OSDMonitor()

# Scan everything
data = monitor.scan()

# Access the data
for serial, drive in data['drives'].items():
    print(f"Drive {serial}: PHY {drive['phy_id']}, SCSI {drive['scsi_address']}")

# Analyze health
issues = OSDMonitor.analyze_health(data)
print(f"SMART problems: {len(issues['smart_problems'])}")
print(f"High latency: {len(issues['high_latency'])}")

# Export your own way
import json
with open('my_custom_export.json', 'w') as f:
    json.dump(data, f, indent=2)
```

---

## Key Features Fixed

### 1. SCSI Addresses for ALL Drives ✓

**All SAS drives now show SCSI addresses**, not just mapped ones:

```
Before (only 5 drives):
OSD 50: SCSI 0:0:0:0 ✓
OSD 51: SCSI 0:0:1:0 ✓
...
PHY 6: N/A           ✗ Missing!
PHY 7: N/A           ✗ Missing!

After (all 11 drives):
OSD 50: SCSI 0:0:0:0 ✓
OSD 51: SCSI 0:0:1:0 ✓
...
PHY 6: SCSI 0:0:6:0  ✓ Now shown!
PHY 7: SCSI 0:0:7:0  ✓ Now shown!
```

### 2. Drive Sizes for ALL Drives ✓

Extracted from smartctl `user_capacity` field:

```
PHY 6: 2.7T  (ST3000DM001-9YN166)
PHY 7: 2.7T  (ST3000DM008-2DM166)
PHY 9: 2.7T  (ST3000DM008-2DM166)
```

### 3. No More Crashes ✓

Fixed `TypeError` with SMART data handling

---

## API Reference

### OSDMonitor Class

```python
from osd_core import OSDMonitor

monitor = OSDMonitor()
```

#### Methods

**`scan(progress_callback=None)`**
- Performs complete scan of drives and OSDs
- Returns: dict with all data
- Optional progress callback: `func(current, total, message)`

**`analyze_health(data)` (static)**
- Analyzes scan data for problems
- Returns: dict with categorized issues

**`format_age(power_on_hours)` (static)**
- Converts hours to human-readable format
- Returns: "5.2y" or "8mo"

#### Data Structure

```python
data = {
    'timestamp': '2025-11-14T14:30:22',
    'controller': {
        'device': '/dev/sg6',
        'type': 'PERC',
        'model': 'PERC H730P Adapter',
    },
    'drives': {
        'SERIAL123': {
            'phy_id': 0,
            'serial': 'SERIAL123',
            'scsi_address': '0:0:0:0',  # Always present!
            'current_device': 'sdi',     # Or None if not mapped
            'model': 'SEAGATE ST8000NM0075',
            'size': '7.3T',
            'health_hw': 'OK',
            'smart_details': {
                'temperature': 26,
                'power_on_hours': 45000,
                'reallocated_sectors': 0,
                'pending_sectors': 0,
                'uncorrectable': 0,
            }
        },
        # ... more drives
    },
    'osds': { ... },
    'osd_to_drive': { '50': 'SERIAL123', ... },
    'osd_status': { '50': {'up': True, 'in': True}, ... },
    'systemd_status': { '50': 'active', ... },
    'osd_perf': { '50': {'commit_latency_ms': 52}, ... },
}
```

---

## Comparison: Which Version?

| Feature | Plain Text | Rich + Pandas |
|---------|-----------|---------------|
| **Dependencies** | None | rich, pandas, openpyxl |
| **Install Size** | 0 MB | ~32 MB |
| **Colors** | No | Yes |
| **Visual Hierarchy** | No | Yes (panels, borders) |
| **CSV Export** | Command line flag | Automatic |
| **JSON Export** | Command line flag | Automatic |
| **Excel Export** | No | Yes (multi-sheet) |
| **Historical Tracking** | No | Yes (auto append) |
| **Summary Stats** | Basic | Detailed |
| **Best For** | Scripts, cron, minimal systems | Interactive use, monitoring, reports |

### Decision Guide

**Choose Plain Text if:**
- You want zero dependencies
- Running in minimal environment
- Using in scripts/automation
- Only need occasional scans

**Choose Rich + Pandas if:**
- Daily interactive monitoring
- Want visual clarity
- Need export to Excel
- Building historical database
- Planning web dashboard

**Use Both!**
- Plain for cron jobs (lightweight)
- Rich for interactive troubleshooting (beautiful)

---

## Integration Examples

### Cron Job (Plain)

```bash
# /etc/cron.d/osd-monitor
0 * * * * root cd /root && python3 check-osd-plain.py --export-csv >> /var/log/osd-monitor.log 2>&1
```

### Systemd Timer (Rich)

```ini
# /etc/systemd/system/osd-monitor.service
[Unit]
Description=OSD Drive Monitor

[Service]
Type=oneshot
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/check-osd-rich.py
User=root
```

```ini
# /etc/systemd/system/osd-monitor.timer
[Unit]
Description=OSD Drive Monitor Timer

[Timer]
OnCalendar=hourly

[Install]
WantedBy=timers.target
```

### Web Dashboard (Flask)

```python
from flask import Flask, jsonify
from osd_core import OSDMonitor

app = Flask(__name__)

@app.route('/api/scan')
def scan():
    monitor = OSDMonitor()
    data = monitor.scan()
    return jsonify(data)

@app.route('/api/health')
def health():
    monitor = OSDMonitor()
    data = monitor.scan()
    issues = OSDMonitor.analyze_health(data)
    return jsonify(issues)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### Custom Alerting

```python
#!/usr/bin/env python3
from osd_core import OSDMonitor
import smtplib

monitor = OSDMonitor()
data = monitor.scan()
issues = OSDMonitor.analyze_health(data)

if issues['smart_problems']:
    # Send email alert
    subject = f"URGENT: {len(issues['smart_problems'])} drives with SMART errors!"
    body = "\n".join([
        f"OSD {p['osd_id']}: PHY {p['drive']['phy_id']}"
        for p in issues['smart_problems']
    ])
    # send_email(subject, body)
    
if issues['high_latency']:
    # Send Slack notification
    message = f"{len(issues['high_latency'])} OSDs with high latency"
    # send_slack(message)
```

---

## Testing

### Test Core Module

```bash
# Run standalone test
sudo python3 osd_core.py
```

Output:
```
Testing OSD Core Module (Pure Python)
================================================================================
Progress: 0% - Scanning PHY 0
Progress: 3% - Scanning PHY 1
...
Progress: 100% - Scan complete

Scan completed successfully!
Timestamp: 2025-11-14T14:30:22
Drives found: 11
OSDs found: 52
Local OSDs: 5

Health Analysis:
  SMART problems: 0
  High latency: 5
  High temperature: 0
  Down OSDs: 0
  Available drives: 6
```

---

## Troubleshooting

### Import Error

```
ERROR: Could not import osd_core module
```

**Solution:** Make sure `osd_core.py` is in the same directory as the frontend script.

### Permission Denied

```
ERROR: This script must be run with sudo
```

**Solution:** Always use `sudo`:
```bash
sudo python3 check-osd-plain.py
```

### Missing Dependencies (Rich version)

```
WARNING: rich not installed
WARNING: pandas not installed
```

**Solution:**
```bash
pip install rich pandas openpyxl
```

### No Drives Found

**Solution:** Check controller device:
```bash
# Find controller
ls -l /dev/sg*

# Test access
sudo smartctl -i /dev/sg6
```

---

## Future Enhancements

### Easy to Add

Since the core is separate, you can easily add:

1. **New output formats** - XML, YAML, Prometheus metrics
2. **New frontends** - Web UI, GUI, mobile app
3. **New analysis** - ML predictions, failure forecasting
4. **New integrations** - Grafana, InfluxDB, Datadog

### Example: Prometheus Exporter

```python
#!/usr/bin/env python3
from osd_core import OSDMonitor
from prometheus_client import start_http_server, Gauge
import time

# Define metrics
temperature_gauge = Gauge('osd_drive_temperature_celsius', 
                         'Drive temperature', ['osd_id', 'phy_id'])
latency_gauge = Gauge('osd_commit_latency_milliseconds',
                     'OSD commit latency', ['osd_id'])

def collect_metrics():
    monitor = OSDMonitor()
    data = monitor.scan()
    
    for serial, drive in data['drives'].items():
        osd_id = find_osd(serial, data['osd_to_drive'])
        if drive['smart_details']['temperature']:
            temperature_gauge.labels(
                osd_id=osd_id or 'none',
                phy_id=drive['phy_id']
            ).set(drive['smart_details']['temperature'])
    
    for osd_id, perf in data['osd_perf'].items():
        latency_gauge.labels(osd_id=osd_id).set(
            perf['commit_latency_ms']
        )

if __name__ == '__main__':
    start_http_server(8000)
    while True:
        collect_metrics()
        time.sleep(60)
```

---

## Summary

You now have:

✅ **Pure Python core** - Works anywhere, no dependencies  
✅ **Plain text frontend** - For scripts and automation  
✅ **Rich+Pandas frontend** - For interactive monitoring  
✅ **SCSI addresses for ALL drives** - Not just mapped ones  
✅ **Complete drive information** - Size, SMART, performance  
✅ **Modular architecture** - Easy to extend  
✅ **Multiple export formats** - CSV, JSON, Excel  
✅ **Historical tracking** - Foundation for trends  
✅ **Health analysis** - Automatic issue detection  

Pick the frontend that fits your needs, or write your own using the core module!
