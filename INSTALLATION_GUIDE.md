# Ceph OSD Monitor - Rich + Pandas Edition
## Installation & Usage Guide

## Installation

### 1. Install Required Libraries

```bash
# Install both Rich and Pandas
pip install rich pandas openpyxl

# Or if you prefer pip3
pip3 install rich pandas openpyxl

# System-wide installation (requires sudo)
sudo pip3 install rich pandas openpyxl
```

**Package Sizes:**
- `rich`: ~500KB (pure Python, no C dependencies)
- `pandas`: ~30MB (includes numpy)
- `openpyxl`: ~2MB (for Excel export)

**Total:** ~32MB

### 2. Copy the Script

```bash
# Make the script executable
chmod +x check-osd-rich-pandas.py

# Run it
sudo python3 check-osd-rich-pandas.py
```

---

## Features

### 1. **SCSI Addresses for ALL Drives** ✓ FIXED
- Now shows SCSI addresses for all drives on the RAID controller
- Not just the ones mapped to /dev/sdX
- Format: `[Host:Channel:Target:LUN]`
- Derived from PHY ID and controller info

### 2. **Beautiful Rich Terminal Output**
- Color-coded status (green=good, yellow=warning, red=critical)
- Automatic column alignment
- Visual hierarchy with panels and borders
- Alerts stand out immediately

### 3. **Pandas Data Analysis**
- Full statistical analysis
- Easy filtering and sorting
- Export to multiple formats

### 4. **Multiple Export Formats**
- **CSV**: For scripts and databases
- **JSON**: For APIs and web dashboards
- **Excel**: For management reports (with Summary and Problem Drives sheets)

### 5. **Historical Tracking**
- Automatically appends to `osd_history.csv`
- Track drive health over time
- Foundation for trend analysis

---

## Output Files

When you run the script, it creates:

1. **osd_status_YYYYMMDD_HHMMSS.csv**
   - Complete data in CSV format
   - Easy to import into databases or analysis tools

2. **osd_status_YYYYMMDD_HHMMSS.json**
   - JSON format for web APIs
   - Perfect for your future web dashboard

3. **osd_status_YYYYMMDD_HHMMSS.xlsx**
   - Excel workbook with 3 sheets:
     - Current Status: Full drive inventory
     - Summary: Key statistics
     - Problem Drives: Drives needing attention (if any)

4. **osd_history.csv**
   - Cumulative history of all scans
   - Grows over time for trend analysis

---

## Color-Coded Output Guide

### Status Colors
- **Green**: Good/Normal (up, in, active, OK)
- **Yellow**: Warning (out, high latency, warm temp)
- **Red**: Critical (down, failed, SMART errors, hot)

### Latency Colors
- **Green**: < 100ms (good)
- **Yellow**: 100-150ms (warning)
- **Red**: > 150ms (critical)

### Temperature Colors
- **Green**: < 40°C (normal)
- **Yellow**: 40-50°C (warm)
- **Red**: > 50°C (hot)

### SMART Status
- **Green**: OK (no errors)
- **Red**: Shows error counts
  - R: Reallocated sectors
  - P: Pending sectors
  - U: Uncorrectable errors

---

## Example Usage

### Basic Scan
```bash
sudo python3 check-osd-rich-pandas.py
```

This will:
1. Scan all drives on the RAID controller
2. Show beautiful color-coded output
3. Export to CSV, JSON, and Excel
4. Append to history file

### Automated Monitoring
```bash
# Run every hour via cron
0 * * * * cd /home/torvaldsl && sudo python3 check-osd-rich-pandas.py

# Or as a systemd timer
# /etc/systemd/system/osd-monitor.timer
[Unit]
Description=OSD Drive Monitor (hourly)

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

### Integration with Web Dashboard

The JSON export is perfect for web dashboards:

```python
# Example: Load latest data for web dashboard
import json
import glob

# Find most recent JSON file
json_files = glob.glob('osd_status_*.json')
latest = max(json_files)

# Load data
with open(latest) as f:
    osd_data = json.load(f)

# Use in your web app
for drive in osd_data:
    print(f"OSD {drive['osd_id']}: {drive['commit_latency_ms']}ms")
```

---

## Future Enhancements

### Trend Analysis (Next Step)

Add this function to analyze trends:

```python
def analyze_trends(history_file='osd_history.csv', days=7):
    """Analyze drive trends over the last N days."""
    df = pd.read_csv(history_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Filter to last N days
    cutoff = datetime.now() - timedelta(days=days)
    recent = df[df['timestamp'] > cutoff]
    
    # Group by OSD and analyze
    for osd_id in recent['osd_id'].dropna().unique():
        osd_data = recent[recent['osd_id'] == osd_id].sort_values('timestamp')
        
        # Check latency trend
        if len(osd_data) >= 3:
            latency_trend = osd_data['commit_latency_ms'].diff().mean()
            if latency_trend > 10:  # Increasing by 10ms on average
                print(f"⚠️  OSD {osd_id}: Latency trending up (+{latency_trend:.1f}ms/scan)")
        
        # Check temperature trend
        if len(osd_data) >= 3:
            temp_trend = osd_data['temperature_c'].diff().mean()
            if temp_trend > 2:  # Increasing by 2°C on average
                print(f"⚠️  OSD {osd_id}: Temperature trending up (+{temp_trend:.1f}°C/scan)")
```

### Web Dashboard with Flask

```python
from flask import Flask, jsonify
import pandas as pd

app = Flask(__name__)

@app.route('/api/osds')
def get_osds():
    # Load latest data
    df = pd.read_csv('osd_history.csv')
    latest = df[df['timestamp'] == df['timestamp'].max()]
    return jsonify(latest.to_dict(orient='records'))

@app.route('/api/osds/<int:osd_id>/history')
def get_osd_history(osd_id):
    df = pd.read_csv('osd_history.csv')
    osd_data = df[df['osd_id'] == osd_id]
    return jsonify(osd_data.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### Grafana Integration

1. Export to InfluxDB or Prometheus
2. Create Grafana dashboard
3. Set up alerts for:
   - SMART errors
   - High latency
   - Temperature spikes
   - Latency trends

---

## Troubleshooting

### "pandas not installed"
```bash
pip install pandas
```

### "rich not installed"
```bash
pip install rich
```

### "openpyxl not installed" (Excel export fails)
```bash
pip install openpyxl
```

### Permission denied
```bash
# Must run as root to access RAID controller and ceph commands
sudo python3 check-osd-rich-pandas.py
```

### SCSI addresses showing as N/A
- This shouldn't happen anymore!
- All drives on the RAID controller now get SCSI addresses
- Even unmapped drives show SCSI addresses based on PHY ID

### No drives found
- Check RAID controller is accessible: `ls -l /dev/sg*`
- Verify smartctl works: `sudo smartctl -i /dev/sg6`
- Check controller type is supported (MegaRAID/PERC)

---

## Performance Notes

- Scanning 32 PHY slots takes ~10-15 seconds
- Most time is spent querying smartctl for each slot
- Rich output adds negligible overhead
- Pandas operations are fast (< 1 second)

---

## What's Next?

Once you have historical data accumulated, you can:

1. **Identify failing drives early** - before complete failure
2. **Plan maintenance windows** - based on drive age and health
3. **Optimize performance** - identify slow drives affecting cluster
4. **Capacity planning** - track available slots and drive sizes
5. **Build web dashboard** - real-time monitoring
6. **Set up alerts** - email/Slack notifications for critical issues

The JSON export makes it easy to integrate with any monitoring system!
