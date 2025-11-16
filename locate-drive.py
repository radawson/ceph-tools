#!/usr/bin/env python3
"""
Drive LED Locator Tool

Blink the locate LED on a drive to physically identify it.

Usage:
    sudo ./locate-drive.py on /dev/sda
    sudo ./locate-drive.py off /dev/sda
    sudo ./locate-drive.py on OSD.42
    sudo ./locate-drive.py list   # Show all drives with enclosure info
"""

import sys
import subprocess
import json
import os
import shutil

VERSION = "1.0.3"


def check_dependencies():
    """Check if required system packages are installed."""
    missing = []
    
    # Check for sg_ses (from sg3-utils)
    if not shutil.which("sg_ses"):
        missing.append("sg3-utils (provides sg_ses for enclosure bay mapping)")
    
    # Check for ledctl (from ledmon) - optional but recommended
    if not shutil.which("ledctl"):
        missing.append("ledmon (provides ledctl for LED control) - OPTIONAL")
    
    if missing:
        print("⚠️  Some packages are not installed:", file=sys.stderr)
        for pkg in missing:
            print(f"   - {pkg}", file=sys.stderr)
        print("\nInstall with:", file=sys.stderr)
        print("  sudo apt install -y sg3-utils ledmon", file=sys.stderr)
        print("\nNote: The script will still run but some features may not work.\n", file=sys.stderr)


def run_command(cmd, silent=False):
    """Run a command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not silent:
            print(f"Error: {e.stderr}", file=sys.stderr)
        return None


def find_device_for_osd(osd_id):
    """Find the /dev/sdX device for an OSD."""
    # Get OSD metadata
    metadata = run_command(["ceph", "osd", "metadata", str(osd_id)], silent=True)
    if not metadata:
        return None

    try:
        data = json.loads(metadata)
        device_ids = data.get("device_ids", "")
        # Parse device_ids like "sda=VENDOR_MODEL_SERIAL"
        for item in device_ids.split(","):
            if "=" in item:
                dev = item.split("=")[0].strip()
                if dev.startswith("sd"):
                    return f"/dev/{dev}"
    except:
        pass

    return None


def led_control(device, action):
    """Control LED for a device."""
    if action not in ["on", "off"]:
        print(f"Error: Action must be 'on' or 'off'", file=sys.stderr)
        return False

    locate_cmd = "locate" if action == "on" else "locate_off"

    # Try ledctl first (part of Intel LED monitor package)
    result = run_command(["ledctl", f"{locate_cmd}={device}"], silent=True)
    if result is not None:
        print(f"✓ LED {action.upper()} for {device} (via ledctl)")
        return True

    # Try sg_ses for enclosure-based control
    # This is more complex and requires knowing the enclosure and slot
    print(f"⚠  ledctl not available. Install with: apt install ledmon")
    print(f"   Alternative: Use sg_ses directly if you know the enclosure slot")
    return False


def list_drives():
    """List all drives with enclosure information."""
    print("Discovering drives and enclosures...")
    print()

    # Import our module
    try:
        from osd_core import OSDMonitor
    except ImportError:
        print("Error: Could not import osd_core module", file=sys.stderr)
        return

    monitor = OSDMonitor()
    data = monitor.scan()

    if not data:
        print("Error: Could not scan drives", file=sys.stderr)
        return

    print("=" * 100)
    print(
        f"{'Device':<12} {'OSD':<6} {'Serial':<20} {'Model':<30} {'Enclosure Bay':<15}"
    )
    print("=" * 100)

    # Show drives with their info
    for serial, drive in sorted(
        data["drives"].items(), key=lambda x: x[1].get("current_device", "")
    ):
        device = drive.get("current_device", "N/A")
        if device == "N/A":
            device = "NOT MAPPED"
        else:
            device = f"/dev/{device}"

        # Find OSD for this drive
        osd_id = None
        for oid, ser in data["osd_to_drive"].items():
            if ser == serial:
                osd_id = f"OSD.{oid}"
                break
        if not osd_id:
            osd_id = "-"

        model = drive.get("model", "Unknown")[:30]
        enclosure_info = "-"
        if "enclosure_slot" in drive:
            enclosure_info = f"Slot {drive['enclosure_slot']}"

        print(f"{device:<12} {osd_id:<6} {serial:<20} {model:<30} {enclosure_info:<15}")

    print("=" * 100)
    print()

    if data["enclosures"]:
        print("Enclosures found:")
        for host, enc in data["enclosures"].items():
            print(
                f"  Host {host}: {enc['name']} ({enc['device']}) - {len(enc['slots'])} mapped slots"
            )
    else:
        print("Note: No SES enclosures detected. Bay mapping not available.")

    print()
    print("To locate a drive:")
    print("  sudo ./locate-drive.py on /dev/sda")
    print("  sudo ./locate-drive.py on OSD.42")


def main():
    if os.geteuid() != 0:
        print("Error: This script must be run with sudo", file=sys.stderr)
        sys.exit(1)
    
    # Check for required dependencies
    check_dependencies()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "list":
        list_drives()
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: Missing device argument", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    device_arg = sys.argv[2]

    # Handle OSD.XX format
    if device_arg.lower().startswith("osd.") or device_arg.lower().startswith("osd"):
        osd_id = (
            device_arg.replace("OSD.", "")
            .replace("osd.", "")
            .replace("OSD", "")
            .replace("osd", "")
        )
        device = find_device_for_osd(osd_id)
        if not device:
            print(f"Error: Could not find device for {device_arg}", file=sys.stderr)
            sys.exit(1)
        print(f"{device_arg} -> {device}")
    else:
        device = device_arg
        if not device.startswith("/dev/"):
            device = f"/dev/{device}"

    if action in ["on", "off"]:
        success = led_control(device, action)
        sys.exit(0 if success else 1)
    else:
        print(f"Error: Unknown action '{action}'", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
