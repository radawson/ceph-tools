# Drive Location and LED Control Guide

## Prerequisites

Before using the drive location features, install required packages:

```bash
sudo apt update
sudo apt install -y sg3-utils ledmon
```

- **sg3-utils** - Provides `sg_ses` for querying enclosure bay mappings
- **ledmon** - Provides `ledctl` for LED control (optional but recommended)

---

## The Problem: Finding Physical Drives

When you need to replace a failing drive, you face a challenge: **How do you know which physical drive in the rack corresponds to `/dev/sda` or `OSD.42`?**

### Why SCSI IDs Don't Match Physical Bays

The SCSI target ID (the third number in `[H:C:T:L]`) is **NOT** the same as the physical bay number because:

1. **SAS Expander Assignment**: The enclosure's SAS expander assigns SCSI IDs based on discovery order, not physical position
2. **Cabling Effects**: How the enclosure connects to the controller affects numbering
3. **Hot-Swap Changes**: Removing/adding drives can renumber everything
4. **Multiple Paths**: Multipath configurations create multiple IDs for the same drive

Example from hv03:
```
[7:0:0:0]  disk  TOSHIBA   MG04SCA40EN  /dev/sdc   <- Might be bay 5
[7:0:1:0]  disk  SEAGATE   ST4000NM0023 /dev/sdd   <- Might be bay 1
```

The target IDs (0, 1) don't necessarily mean bays 0 and 1!

## The Solution: SES (SCSI Enclosure Services)

Modern enclosures like the Dell MD1400 support **SES**, which provides:

- **Accurate bay/slot mapping**
- **LED control** (locate/fault/etc.)
- **Temperature monitoring**
- **Fan and power supply status**

## Quick Start: Blinking a Drive LED

### Option 1: Use Our Tool (Simplest)

```bash
# List all drives with their enclosure bay info
sudo ./locate-drive.py list

# Turn ON locate LED for a specific drive
sudo ./locate-drive.py on /dev/sda
sudo ./locate-drive.py on OSD.42

# Turn OFF locate LED
sudo ./locate-drive.py off /dev/sda
```

### Option 2: Use ledctl (If Available)

```bash
# Install ledmon package (contains ledctl)
sudo apt install ledmon

# Turn on locate LED
sudo ledctl locate=/dev/sda

# Turn off locate LED
sudo ledctl locate_off=/dev/sda
```

### Option 3: Use sg_ses Directly (Most Control)

```bash
# Install sg3-utils
sudo apt install sg3-utils

# Find the enclosure device
lsscsi | grep enclosu
# Output: [7:0:7:0]   enclosu DELL     MD1400           1.07  -

# Find which sg device that is
lsscsi -g | grep "7:0:7:0"
# Output: [7:0:7:0]   enclosu DELL     MD1400           1.07  -          /dev/sg10

# View all slots in the enclosure
sudo sg_ses /dev/sg10

# Turn ON locate LED for slot 3
sudo sg_ses --index=3 --set=locate /dev/sg10

# Turn OFF locate LED for slot 3
sudo sg_ses --index=3 --clear=locate /dev/sg10
```

## Understanding the Enclosure Mapping

### Step 1: Find Your Enclosures

```bash
lsscsi | grep enclosu
```

Example output:
```
[7:0:7:0]   enclosu DELL     MD1400           1.07  -
```

This means:
- **Host 7**: All drives on this SCSI host are in this enclosure
- The enclosure controller itself is at target 7

### Step 2: View SES Data

```bash
# Find the sg device for the enclosure
lsscsi -g | grep "7:0:7:0"
# Output: [7:0:7:0]   enclosu DELL     MD1400           1.07  -          /dev/sg10

# Query the enclosure
sudo sg_ses /dev/sg10
```

This shows:
- All drive slots and their status
- Which SCSI addresses map to which physical bays
- Temperature, LED status, etc.

### Step 3: Map Drives to Bays

Our monitoring tool automatically does this! Run:

```bash
sudo ./check-osd-plain.py
```

Look for the "Bay/Slot" column in the output (if SES is working).

## Integration with Monitoring Tool

The `osd_core.py` module now includes:

### Automatic Enclosure Discovery

```python
from osd_core import OSDMonitor

monitor = OSDMonitor()
data = monitor.scan()

# View enclosures
for host, enclosure in data['enclosures'].items():
    print(f"Host {host}: {enclosure['name']}")
    print(f"  Device: {enclosure['device']}")
    print(f"  Slots mapped: {len(enclosure['slots'])}")
    
# View drives with bay info
for serial, drive in data['drives'].items():
    if 'enclosure_slot' in drive:
        print(f"Drive {serial}: Bay {drive['enclosure_slot']}")
```

### LED Control API

```python
from osd_core import OSDMonitor

# Turn on locate LED
OSDMonitor.locate_drive_on("/dev/sda")

# Turn off locate LED
OSDMonitor.locate_drive_off("/dev/sda")
```

## Troubleshooting

### ledctl Not Available

```bash
sudo apt install ledmon
```

If still not working, the drives/enclosure might not support SGPIO/AHCI LED control.

### sg_ses Not Available

```bash
sudo apt install sg3-utils
```

### No Enclosure Detected

Check if SES is enabled:
```bash
lsscsi | grep enclosu
```

If nothing appears, the enclosure either:
- Doesn't support SES
- Needs a firmware update
- Isn't connected properly

### Enclosure Found But No Slot Mapping

Run with debug:
```bash
sudo sg_ses -v /dev/sgX
```

Look for "Array device slot" sections. If they're missing, the enclosure might not report slot mappings properly.

## Best Practices

1. **Always blink before pulling**: Turn on the locate LED BEFORE going to the datacenter
2. **Document your layout**: Create a diagram showing SCSI addresses -> physical bays
3. **Use serial numbers**: Match drive serial numbers (visible on label) with `smartctl` output
4. **Test new drives**: When adding drives, blink the LED to confirm correct bay assignment
5. **Leave LEDs off**: Turn off locate LEDs after confirming - saves confusion later

## Additional Resources

- [sg3_utils documentation](https://sg.danny.cz/sg/sg3_utils.html)
- [SES-3 Standard (SCSI Enclosure Services)](http://www.t10.org/drafts.htm)
- [Dell MD1400 Manual](https://www.dell.com/support) - Search for MD1400

## Notes

- Some enclosures only support blinking on drives that are accessed, not idle
- LED colors/patterns vary by vendor (Dell, Supermicro, etc.)
- Some HBAs/RAIDcards intercept LED commands and don't pass them to enclosures
- In IT mode (non-RAID), LED control is more reliable than in RAID mode

