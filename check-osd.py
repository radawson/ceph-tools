#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Metadata-First Approach

Strategy:
1. Query ceph metadata for ALL OSDs (complete source of truth)
2. Scan local hardware to find physical drives
3. Match local drives to OSDs using model+serial from device_ids
4. Get complete status: up/down, in/out, systemd service
5. Show everything with proper debugging
"""

import subprocess
import json
import sys
import os
import re

DEBUG = True  # Set to False to reduce output

def debug_print(message):
    """Print debug messages if DEBUG is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}", file=sys.stderr)

def run_command(command, is_json=False, silent=False):
    """Helper function to run shell commands and return output."""
    try:
        if len(command) > 0 and command[0] in ['ceph', 'pvs', 'lvs', 'systemctl'] and command[0] != 'sudo':
            command.insert(0, 'sudo')

        if not silent:
            debug_print(f"Running: {' '.join(command)}")

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        if is_json:
            return json.loads(result.stdout)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not silent:
            debug_print(f"Command failed: {' '.join(command)}")
            debug_print(f"Error: {e.stderr}")
        return None
    except json.JSONDecodeError as e:
        debug_print(f"JSON decode failed: {e}")
        return None

def find_raid_controller():
    """Find the RAID controller device."""
    debug_print("Looking for RAID controller...")
    for i in range(20):
        sg_dev = f"/dev/sg{i}"
        if os.path.exists(sg_dev):
            info = run_command(["smartctl", "-i", sg_dev], is_json=False, silent=True)
            if info and ('megaraid' in info.lower() or 'raid' in info.lower() or 'perc' in info.lower()):
                debug_print(f"Found RAID controller at {sg_dev}")
                return sg_dev
    debug_print("No RAID controller found, defaulting to /dev/sg6")
    return "/dev/sg6"

def get_local_physical_drives():
    """
    Scan local RAID controller for physical drives.
    Returns: {serial: {phy_id, serial, model, vendor, health_hw}}
    """
    print("\n" + "="*80)
    print("STEP 1: Scanning Local Hardware")
    print("="*80)

    controller_dev = find_raid_controller()
    drives = {}

    for phy_id in range(32):
        info = run_command(["smartctl", "-j", "-a", "-d", f"megaraid,{phy_id}", controller_dev],
                          is_json=True, silent=True)

        if info and 'serial_number' in info:
            serial = info['serial_number']
            model = info.get('model_name', info.get('model_family', 'Unknown'))
            vendor = info.get('vendor', '')

            # Extract vendor from model if not separate
            if not vendor and model:
                # Models often start with vendor name
                vendor_match = re.match(r'^(\w+)', model)
                if vendor_match:
                    vendor = vendor_match.group(1)

            health_passed = info.get('smart_status', {}).get('passed', False)

            drives[serial] = {
                'phy_id': phy_id,
                'serial': serial,
                'model': model,
                'vendor': vendor,
                'health_hw': 'OK' if health_passed else 'FAIL',
                'current_device': None,
                'scsi_address': None,
                'size': None,
            }

            debug_print(f"PHY {phy_id}: {model} S/N:{serial}")

    print(f"Found {len(drives)} physical drives on RAID controller")
    return drives

def map_drives_to_devices(drives):
    """
    Map physical drives to current /dev/sdX device names using lsscsi.
    Updates drives dict with current_device, size, scsi_address, and better model info.
    """
    print("\n" + "="*80)
    print("STEP 2: Mapping to Current Device Names and SCSI Addresses")
    print("="*80)

    # Use lsscsi to get SCSI addresses and model info
    lsscsi_output = run_command(["lsscsi"], is_json=False, silent=True)

    if lsscsi_output:
        for line in lsscsi_output.splitlines():
            # Parse lsscsi output format:
            # [0:0:2:0]    disk    HITACHI  H0S726T4CLAR4000 S430  /dev/sdd
            match = re.match(r'\[([^\]]+)\]\s+(\w+)\s+(\S+)\s+(\S+)\s+\S+\s+(/dev/\w+)', line)
            if match:
                scsi_addr = match.group(1)  # e.g., "0:0:2:0"
                dev_type = match.group(2)   # e.g., "disk"
                vendor = match.group(3)     # e.g., "HITACHI"
                model = match.group(4)      # e.g., "H0S726T4CLAR4000"
                dev_path = match.group(5)   # e.g., "/dev/sdd"
                dev_name = dev_path.replace('/dev/', '')

                if dev_type != 'disk':
                    continue

                # Get serial number to match with our drives
                info = run_command(["smartctl", "-j", "-i", dev_path], is_json=True, silent=True)
                if info and 'serial_number' in info:
                    serial = info['serial_number']

                    if serial in drives:
                        drives[serial]['current_device'] = dev_name
                        drives[serial]['scsi_address'] = scsi_addr

                        # Update model info from lsscsi (better than smartctl)
                        if vendor and model:
                            drives[serial]['model'] = f"{vendor} {model}"

                        # Get size
                        lsblk_info = run_command(["lsblk", "-J", "-o", "NAME,SIZE", dev_path],
                                                is_json=True, silent=True)
                        if lsblk_info and 'blockdevices' in lsblk_info:
                            drives[serial]['size'] = lsblk_info['blockdevices'][0].get('size', 'N/A')

                        debug_print(f"{dev_name}: SCSI {scsi_addr}, Serial {serial}, PHY {drives[serial]['phy_id']}")

    # Fallback for drives not found via lsscsi
    lsblk_output = run_command(["lsblk", "-d", "-n", "-o", "NAME,TYPE"], is_json=False, silent=True)
    if lsblk_output:
        for line in lsblk_output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'disk' and not parts[0].startswith(('loop', 'ram', 'sr')):
                dev = parts[0]
                dev_path = f"/dev/{dev}"

                # Get device info including serial
                info = run_command(["smartctl", "-j", "-i", dev_path], is_json=True, silent=True)
                if info and 'serial_number' in info:
                    serial = info['serial_number']

                    if serial in drives and not drives[serial].get('current_device'):
                        drives[serial]['current_device'] = dev

                        # Get size
                        lsblk_info = run_command(["lsblk", "-J", "-o", "NAME,SIZE", dev_path],
                                                is_json=True, silent=True)
                        if lsblk_info and 'blockdevices' in lsblk_info:
                            drives[serial]['size'] = lsblk_info['blockdevices'][0].get('size', 'N/A')

                        debug_print(f"{dev}: Serial {serial} (fallback - no SCSI address)")

    mapped = sum(1 for d in drives.values() if d.get('current_device'))
    print(f"Mapped {mapped}/{len(drives)} physical drives to device names")

def get_ceph_osds():
    """
    Get ALL Ceph OSDs metadata.
    Returns: {osd_id: {metadata...}}
    """
    print("\n" + "="*80)
    print("STEP 3: Querying Ceph Cluster for ALL OSDs")
    print("="*80)

    metadata = run_command(["ceph", "osd", "metadata"], is_json=True)
    if not metadata:
        print("ERROR: Could not retrieve Ceph OSD metadata!")
        return {}

    osds = {}
    for osd in metadata:
        osd_id = str(osd.get('id', ''))
        osds[osd_id] = osd
        debug_print(f"OSD {osd_id}: host={osd.get('hostname', 'unknown')} "
                   f"device_ids={osd.get('device_ids', 'N/A')}")

    print(f"Found {len(osds)} OSDs in cluster")
    return osds

def parse_device_id(device_ids_string):
    """
    Parse device_ids string like "sde=SEAGATE_ST8000NM0075_ZA1FMDSH0000C94972BA"
    Returns: (device_name, vendor, model, serial) or None
    """
    if not device_ids_string:
        return None

    # Handle multiple devices (comma-separated)
    for part in device_ids_string.split(','):
        if '=' not in part:
            continue

        device_name, identifier = part.split('=', 1)
        device_name = device_name.strip()
        identifier = identifier.strip()

        # identifier format is typically: VENDOR_MODEL_SERIAL
        # Examples:
        # SEAGATE_ST8000NM0075_ZA1FMDSH0000C94972BA
        # DELL_PERC_H730P_Adp_003856ae11e849eb2900d4318fa06d86
        # SEAGATE_DL2400MM0159_WBM0EQ7T

        parts = identifier.split('_')
        if len(parts) >= 3:
            vendor = parts[0]
            # Serial is usually the last part
            serial = parts[-1]
            # Model is everything in between
            model = '_'.join(parts[1:-1])

            return {
                'device_name': device_name,
                'vendor': vendor,
                'model': model,
                'serial': serial,
                'full_id': identifier
            }

    return None

def match_drives_to_osds(drives, osds):
    """
    Match local physical drives to OSDs using device_ids.
    Returns: {osd_id: serial}
    """
    print("\n" + "="*80)
    print("STEP 4: Matching Local Drives to OSDs")
    print("="*80)

    osd_to_drive = {}  # {osd_id: serial}

    for osd_id, osd_meta in osds.items():
        device_ids = osd_meta.get('device_ids', '')
        hostname = osd_meta.get('hostname', 'unknown')

        parsed = parse_device_id(device_ids)
        if not parsed:
            debug_print(f"OSD {osd_id}: Could not parse device_ids: {device_ids}")
            continue

        # Try to match by serial number
        osd_serial = parsed['serial']

        # Check if this serial matches any of our local drives
        if osd_serial in drives:
            osd_to_drive[osd_id] = osd_serial
            print(f"✓ OSD {osd_id} (on {hostname}): Matched to local drive")
            debug_print(f"  Serial: {osd_serial}, PHY: {drives[osd_serial]['phy_id']}, "
                       f"Device: {drives[osd_serial].get('current_device', 'N/A')}")
        else:
            debug_print(f"OSD {osd_id} (on {hostname}): Serial {osd_serial} not found locally")

    print(f"\nMatched {len(osd_to_drive)} OSDs to local drives")
    return osd_to_drive

def get_osd_status():
    """
    Get OSD status information: up/down and in/out.
    Returns: {osd_id: {'up': True/False, 'in': True/False}}
    """
    print("\n" + "="*80)
    print("STEP 5: Getting OSD Status")
    print("="*80)

    status_map = {}

    # Get up/down status from tree
    tree_output = run_command(["ceph", "osd", "tree"], is_json=False)
    if tree_output:
        for line in tree_output.splitlines():
            match = re.match(r'\s*(\d+)\s+\w+\s+[\d\.]+\s+osd\.\d+\s+(\w+)\s+.*', line)
            if match:
                osd_id = match.group(1)
                up_status = match.group(2)  # 'up' or 'down'
                status_map[osd_id] = {
                    'up': (up_status == 'up'),
                    'in': None  # Will fill in from dump
                }

    # Get in/out status from dump
    dump_output = run_command(["ceph", "osd", "dump"], is_json=False)
    if dump_output:
        for line in dump_output.splitlines():
            # Look for lines like: osd.1 up   in  weight 1 up_from 123 ...
            match = re.search(r'osd\.(\d+)\s+(\w+)\s+(\w+)', line)
            if match:
                osd_id = match.group(1)
                in_status = match.group(3)  # 'in' or 'out'
                if osd_id in status_map:
                    status_map[osd_id]['in'] = (in_status == 'in')

    debug_print(f"Got status for {len(status_map)} OSDs")
    return status_map

def check_systemd_status(osd_ids):
    """
    Check systemd service status for OSDs.
    Returns: {osd_id: 'active'/'inactive'/'unknown'}
    """
    print("\n" + "="*80)
    print("STEP 6: Checking Systemd Service Status")
    print("="*80)

    systemd_status = {}

    for osd_id in osd_ids:
        service_name = f"ceph-osd@{osd_id}.service"

        # Try to check if service is active
        result = run_command(["systemctl", "is-active", service_name],
                           is_json=False, silent=True)

        if result and result.strip() in ['active', 'activating']:
            systemd_status[osd_id] = 'active'
            debug_print(f"OSD {osd_id} systemd: active")
        elif result and result.strip() in ['inactive', 'failed', 'deactivating']:
            systemd_status[osd_id] = 'inactive'
            debug_print(f"OSD {osd_id} systemd: inactive ({result.strip()})")
        else:
            # Service might not exist or in unknown state
            systemd_status[osd_id] = 'unknown'
            debug_print(f"OSD {osd_id} systemd: unknown")

    return systemd_status

def format_status(up, in_status, systemd):
    """Format combined status string."""
    parts = []

    # Up/Down
    if up:
        parts.append("up")
    else:
        parts.append("DOWN")

    # In/Out
    if in_status:
        parts.append("in")
    else:
        parts.append("OUT")

    # Systemd
    if systemd == 'active':
        parts.append("✓")
    elif systemd == 'inactive':
        parts.append("✗")
    else:
        parts.append("?")

    return " ".join(parts)

def format_output(drives, osd_to_drive, osd_status, systemd_status):
    """Format and display the final output table."""
    print("\n" + "="*120)
    print("FINAL RESULTS")
    print("="*120)

    # Build rows
    rows = []
    for serial, drive in drives.items():
        # Find OSD for this drive
        osd_id = None
        for oid, drv_serial in osd_to_drive.items():
            if drv_serial == serial:
                osd_id = oid
                break

        # Get status
        if osd_id:
            status = osd_status.get(osd_id, {})
            systemd = systemd_status.get(osd_id, 'unknown')
            status_str = format_status(status.get('up', False),
                                      status.get('in', False),
                                      systemd)
        else:
            status_str = "N/A"

        current_dev = drive.get('current_device')
        current_dev_str = f"/dev/{current_dev}" if current_dev else "N/A"

        # Ensure all values are strings (not None)
        model = drive.get('model', 'Unknown')
        if model and len(model) > 30:
            model = model[:27] + "..."
        elif not model:
            model = 'Unknown'

        # Get SCSI address - ensure it's never None
        scsi_addr = drive.get('scsi_address') or 'N/A'

        rows.append({
            'osd_id': str(osd_id) if osd_id else 'N/A',
            'status': status_str or 'N/A',
            'scsi_addr': scsi_addr if scsi_addr else 'N/A',
            'device': current_dev_str,
            'size': drive.get('size') or 'N/A',
            'phy_id': str(drive['phy_id']),
            'serial': serial or 'N/A',
            'health': drive.get('health_hw') or 'N/A',
            'model': model or 'Unknown'
        })

    # Sort by SCSI address if available, otherwise by PHY ID
    def sort_key(row):
        scsi = row.get('scsi_addr')
        if scsi and scsi != 'N/A':
            # Parse SCSI address [H:C:T:L] for sorting
            try:
                parts = [int(x) for x in scsi.split(':')]
                return (0, parts)  # SCSI addresses first
            except:
                pass
        # Sort by PHY ID for drives without SCSI address
        try:
            phy_id = int(row['phy_id']) if isinstance(row['phy_id'], str) else row['phy_id']
            return (1, phy_id)
        except:
            return (2, 999)  # Unknown drives last

    rows.sort(key=sort_key)

    # Print header
    print("="*140)
    header_fmt = "{:<6} | {:<14} | {:<11} | {:<14} | {:<8} | {:<6} | {:<24} | {:<10} | {:<30}"
    print(header_fmt.format("OSD ID", "Status", "SCSI Addr", "Current Device", "Size", "PHY ID",
                           "Serial Number", "HW Health", "Model"))
    print("="*140)

    # Print rows
    for row in rows:
        print(header_fmt.format(
            row['osd_id'],
            row['status'],
            row['scsi_addr'],
            row['device'],
            row['size'],
            row['phy_id'],
            row['serial'],
            row['health'],
            row['model']
        ))

    print("="*140)

    # Summary
    total_drives = len(drives)
    drives_with_osds = len(osd_to_drive)
    osds_up = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('up', False))
    osds_down = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('up', True))
    osds_in = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('in', False))
    osds_out = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('in', True))
    systemd_active = sum(1 for oid in osd_to_drive if systemd_status.get(oid) == 'active')
    hw_failed = sum(1 for d in drives.values() if d['health_hw'] == 'FAIL')

    print(f"\nSummary:")
    print(f"  Physical drives: {total_drives}")
    print(f"  Drives with OSDs: {drives_with_osds}")
    print(f"  OSD Status: {osds_up} up/{osds_down} down, {osds_in} in/{osds_out} out")
    print(f"  Systemd: {systemd_active} active services")
    print(f"  Hardware: {hw_failed} failures")
    print(f"\nStatus Legend: [up/DOWN] [in/OUT] [✓ active / ✗ inactive / ? unknown]")
    print(f"SCSI Address: [Host:Channel:Target:LUN] - Physical location on controller (stable across reboots)")

def main():
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)

    print("="*80)
    print("CEPH OSD DRIVE MONITOR - Metadata-First Approach")
    print("="*80)

    # Step 1: Scan local hardware
    drives = get_local_physical_drives()
    if not drives:
        print("ERROR: No drives found on local RAID controller")
        sys.exit(1)

    # Step 2: Map to device names
    map_drives_to_devices(drives)

    # Step 3: Get all OSDs from Ceph
    osds = get_ceph_osds()
    if not osds:
        print("ERROR: Could not get OSD metadata from Ceph")
        sys.exit(1)

    # Step 4: Match local drives to OSDs
    osd_to_drive = match_drives_to_osds(drives, osds)

    # Step 5: Get OSD status (up/down, in/out)
    osd_status = get_osd_status()

    # Step 6: Check systemd status
    systemd_status = check_systemd_status(osd_to_drive.keys())

    # Display results
    format_output(drives, osd_to_drive, osd_status, systemd_status)

if __name__ == "__main__":
    main()