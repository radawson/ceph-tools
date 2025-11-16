# Installation Guide

Complete installation instructions for the Ceph OSD Drive Monitor tools.

## Prerequisites

- **Operating System**: Linux (tested on Ubuntu 20.04+, Debian 11+)
- **Python**: Version 3.6 or higher
- **Access**: Root/sudo access required
- **Ceph**: Ceph cluster must be installed and running

## System Dependencies

### Required Packages

These packages must be installed on **every node** where you run the monitoring tools:

```bash
sudo apt update
sudo apt install -y smartmontools lsscsi sg3-utils
```

| Package | Version | Purpose | Required By |
|---------|---------|---------|-------------|
| **smartmontools** | 7.0+ | Drive SMART data collection via `smartctl` | All scripts |
| **lsscsi** | 0.30+ | SCSI device listing and topology | All scripts |
| **sg3-utils** | 1.42+ | Enclosure management via `sg_ses` | Bay mapping, LED control |

### Optional Packages

For enhanced features:

```bash
sudo apt install -y ledmon
```

| Package | Version | Purpose | Required By |
|---------|---------|---------|-------------|
| **ledmon** | 0.90+ | LED control via `ledctl` | Drive location features |

### Pre-installed Packages

These are typically already installed on most Linux systems:

- **util-linux** - Provides `lsblk` (block device info)
- **systemd** - Provides `systemctl` (service status)
- **lvm2** - Provides `pvs`, `lvs` (LVM info)

## Python Dependencies

### Option A: Plain Version (No Dependencies)

For `check-osd-plain.py` and basic `locate-drive.py`:

```bash
# No additional Python packages needed!
# Works with standard Python 3.6+
```

### Option B: Rich Version (Recommended)

For `check-osd-rich.py` with beautiful output:

```bash
sudo pip3 install rich pandas openpyxl
```

| Package | Version | Size | Purpose |
|---------|---------|------|---------|
| **rich** | 12.0+ | ~500 KB | Terminal colors and formatting |
| **pandas** | 1.3+ | ~30 MB | Data analysis and manipulation |
| **openpyxl** | 3.0+ | ~2 MB | Excel file export |

**Total additional space**: ~32 MB

## Installation Steps

### Step 1: Install System Packages

On **each Ceph node** where you want to run monitoring:

```bash
# Update package lists
sudo apt update

# Install required packages
sudo apt install -y smartmontools lsscsi sg3-utils ledmon

# Verify installation
smartctl --version
lsscsi --version
sg_ses --version
ledctl --version  # Optional
```

### Step 2: Install Python Dependencies (Optional)

For the Rich/Pandas version:

```bash
# Install Python packages
sudo pip3 install rich pandas openpyxl

# Verify installation
python3 -c "import rich; print(f'Rich {rich.__version__}')"
python3 -c "import pandas; print(f'Pandas {pandas.__version__}')"
python3 -c "import openpyxl; print(f'OpenPyXL {openpyxl.__version__}')"
```

### Step 3: Copy Script Files

Choose ONE of these methods:

#### Method A: Install to /usr/local/bin (System-wide)

```bash
# Copy core module
sudo cp osd_core.py /usr/local/bin/

# Copy monitoring scripts
sudo cp check-osd-plain.py /usr/local/bin/
sudo cp check-osd-rich.py /usr/local/bin/    # If using Rich version

# Copy utility scripts
sudo cp locate-drive.py /usr/local/bin/

# Make executable
sudo chmod +x /usr/local/bin/check-osd-*.py
sudo chmod +x /usr/local/bin/locate-drive.py
```

#### Method B: Install to user directory

```bash
# Create directory
mkdir -p ~/ceph-tools
cd ~/ceph-tools

# Copy files
cp /path/to/osd_core.py .
cp /path/to/check-osd-plain.py .
cp /path/to/check-osd-rich.py .  # If using Rich version
cp /path/to/locate-drive.py .

# Make executable
chmod +x *.py
```

### Step 4: Verify Installation

```bash
# Test core module
sudo python3 -c "from osd_core import OSDMonitor; print('✓ Core module works')"

# Test plain script
sudo python3 check-osd-plain.py

# Test rich script (if installed)
sudo python3 check-osd-rich.py

# Test locate script
sudo python3 locate-drive.py list
```

## Troubleshooting

### Package Not Found

If `apt install` fails:

```bash
# Update package lists
sudo apt update

# Search for package
apt search smartmontools
apt search lsscsi
apt search sg3-utils
apt search ledmon

# Check distribution
lsb_release -a
```

### Python Package Install Fails

If `pip3 install` fails:

```bash
# Install pip if missing
sudo apt install python3-pip

# Upgrade pip
sudo pip3 install --upgrade pip

# Try installing individually
sudo pip3 install rich
sudo pip3 install pandas
sudo pip3 install openpyxl
```

### Permission Denied

All scripts must be run with sudo:

```bash
sudo python3 check-osd-plain.py
# Not: python3 check-osd-plain.py
```

### Import Error

If you get `ModuleNotFoundError: No module named 'osd_core'`:

```bash
# Make sure osd_core.py is in the same directory
ls -l osd_core.py

# Or add to Python path
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

## Distribution-Specific Notes

### Ubuntu / Debian

```bash
sudo apt install smartmontools lsscsi sg3-utils ledmon
```

### Red Hat / CentOS / Rocky

```bash
sudo yum install smartmontools lsscsi sg3_utils ledmon
# Or
sudo dnf install smartmontools lsscsi sg3_utils ledmon
```

### Arch Linux

```bash
sudo pacman -S smartmontools lsscsi sg3_utils
# ledmon may need AUR
```

## Uninstallation

### Remove Scripts

```bash
# If installed system-wide
sudo rm /usr/local/bin/osd_core.py
sudo rm /usr/local/bin/check-osd-*.py
sudo rm /usr/local/bin/locate-drive.py

# If installed in user directory
rm -rf ~/ceph-tools
```

### Remove Python Packages

```bash
sudo pip3 uninstall rich pandas openpyxl
```

### Remove System Packages (Optional)

**Warning**: Only remove if not used by other applications!

```bash
sudo apt remove smartmontools lsscsi sg3-utils ledmon
sudo apt autoremove
```

## Post-Installation

### Set Up Automated Monitoring

Add to crontab for hourly monitoring:

```bash
sudo crontab -e
```

Add this line:

```cron
# Ceph OSD monitoring - hourly
0 * * * * cd /root && /usr/bin/python3 /usr/local/bin/check-osd-rich.py
```

### Configure Log Rotation

Create `/etc/logrotate.d/ceph-osd-monitor`:

```
/root/osd_history.csv {
    daily
    rotate 90
    compress
    missingok
    notifempty
}
```

## Updating

To update to a newer version:

```bash
# Backup old files
sudo cp /usr/local/bin/osd_core.py /usr/local/bin/osd_core.py.bak

# Copy new files
sudo cp osd_core.py /usr/local/bin/
sudo cp check-osd-plain.py /usr/local/bin/
sudo cp check-osd-rich.py /usr/local/bin/
sudo cp locate-drive.py /usr/local/bin/

# Test
sudo python3 /usr/local/bin/check-osd-plain.py
```

## Version Information

Check versions of all components:

```bash
# Script versions
python3 -c "from osd_core import VERSION; print(f'osd_core: {VERSION}')"

# System package versions
dpkg -l | grep -E 'smartmontools|lsscsi|sg3-utils|ledmon'

# Python package versions
pip3 list | grep -E 'rich|pandas|openpyxl'
```

## Support

If you encounter issues:

1. Check this installation guide
2. Review `TROUBLESHOOTING.md` (if available)
3. Check system logs: `journalctl -xe`
4. Run with debug enabled: Check script help for debug flags
5. Verify Ceph cluster is healthy: `ceph status`

## Next Steps

After installation:

1. Read `QUICK_START.md` for basic usage
2. Read `DRIVE_LOCATION.md` for LED control features
3. Test all functionality with real data
4. Set up automated monitoring (cron)
5. Configure alerting (if needed)

