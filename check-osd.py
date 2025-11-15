#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Enhanced Edition

New features:
- Shows ALL drives (even those without /dev/sdX mappings)
- SMART health details (reallocated sectors, power-on hours, temperature)
- OSD performance metrics (commit/apply latency)
- Identifies drives available for new OSDs
- Provides recommendations for drive replacement
"""

import subprocess
import json
import sys
import os
import re
from datetime import datetime

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

def extract_smart_details(smart_info):
    """Extract key SMART attributes from smartctl JSON output."""
    details = {
        'temperature': None,
        'power_on_hours': None,
        'reallocated_sectors': None,
        'pending_sectors': None,
        'uncorrectable': None,
        'load_cycle_count': None,
    }
    
    # Get temperature
    if 'temperature' in smart_info:
        details['temperature'] = smart_info['temperature'].get('current')
    
    # Get SMART attributes (for ATA drives)
    if 'ata_smart_attributes' in smart_info and 'table' in smart_info['ata_smart_attributes']:
        for attr in smart_info['ata_smart_attributes']['table']:
            attr_id = attr.get('id')
            raw_value = attr.get('raw', {}).get('value', 0)
            
            if attr_id == 5:  # Reallocated_Sector_Ct
                details['reallocated_sectors'] = raw_value
            elif attr_id == 9:  # Power_On_Hours
                details['power_on_hours'] = raw_value
            elif attr_id == 193:  # Load_Cycle_Count
                details['load_cycle_count'] = raw_value
            elif attr_id == 197:  # Current_Pending_Sector
                details['pending_sectors'] = raw_value
            elif attr_id == 198:  # Offline_Uncorrectable
                details['uncorrectable'] = raw_value
    
    # For SCSI/SAS drives, look in different location
    if 'scsi_grown_defect_list' in smart_info:
        details['reallocated_sectors'] = smart_info.get('scsi_grown_defect_list', 0)
    
    return details

def format_size_bytes(size_bytes):
    """Convert bytes to human-readable format."""
    if not size_bytes:
        return None
    
    try:
        size_bytes = int(size_bytes)
    except (ValueError, TypeError):
        return None
    
    # Convert to TB/GB
    if size_bytes >= 1e12:  # 1 TB
        return f"{size_bytes / 1e12:.1f}T"
    elif size_bytes >= 1e9:  # 1 GB
        return f"{size_bytes / 1e9:.0f}G"
    else:
        return f"{size_bytes / 1e6:.0f}M"

def get_local_physical_drives():
    """
    Scan local RAID controller for ALL physical drives.
    Returns: {serial: {phy_id, serial, model, vendor, health_hw, smart_details, size}}
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
                vendor_match = re.match(r'^(\w+)', model)
                if vendor_match:
                    vendor = vendor_match.group(1)

            health_passed = info.get('smart_status', {}).get('passed', False)
            
            # Extract detailed SMART attributes
            smart_details = extract_smart_details(info)
            
            # Extract size from smartctl output
            size = None
            if 'user_capacity' in info:
                # user_capacity is in format {"blocks": X, "bytes": Y}
                size_info = info['user_capacity']
                if isinstance(size_info, dict) and 'bytes' in size_info:
                    size = format_size_bytes(size_info['bytes'])
            
            # Alternative: check for logical_block_size and total blocks
            if not size and 'logical_block_size' in info:
                try:
                    block_size = info.get('logical_block_size', 0)
                    # Try to find total blocks
                    if 'ata_device_statistics' in info:
                        # Look for total blocks in ATA stats
                        pass
                    # For now, if we couldn't get size, leave it as None
                except:
                    pass

            drives[serial] = {
                'phy_id': phy_id,
                'serial': serial,
                'model': model,
                'vendor': vendor,
                'health_hw': 'OK' if health_passed else 'FAIL',
                'smart_details': smart_details,
                'current_device': None,
                'scsi_address': None,
                'size': size,  # Now populated from smartctl
            }

            debug_print(f"PHY {phy_id}: {model} S/N:{serial} Size:{size or 'N/A'}")

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
            match = re.match(r'\[([^\]]+)\]\s+(\w+)\s+(\S+)\s+(\S+)\s+\S+\s+(/dev/\w+)', line)
            if match:
                scsi_addr = match.group(1)
                dev_type = match.group(2)
                vendor = match.group(3)
                model = match.group(4)
                dev_path = match.group(5)
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

                        # Get size from lsblk (this will override smartctl size if available)
                        lsblk_info = run_command(["lsblk", "-J", "-o", "NAME,SIZE", dev_path],
                                                is_json=True, silent=True)
                        if lsblk_info and 'blockdevices' in lsblk_info:
                            lsblk_size = lsblk_info['blockdevices'][0].get('size', None)
                            if lsblk_size:
                                drives[serial]['size'] = lsblk_size

                        debug_print(f"{dev_name}: SCSI {scsi_addr}, Serial {serial}, PHY {drives[serial]['phy_id']}, Size {drives[serial]['size']}")

    mapped = sum(1 for d in drives.values() if d.get('current_device'))
    unmapped = len(drives) - mapped
    print(f"Mapped {mapped}/{len(drives)} physical drives to device names")
    if unmapped > 0:
        print(f"  {unmapped} drive(s) not visible to OS (may be available for new OSDs)")

def get_ceph_osds():
    """Get ALL Ceph OSDs metadata."""
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

def get_osd_performance():
    """Get OSD performance metrics (latency)."""
    print("\n" + "="*80)
    print("STEP 4: Getting OSD Performance Metrics")
    print("="*80)

    perf = {}
    output = run_command(["ceph", "osd", "perf"], is_json=False, silent=True)
    
    if output:
        for line in output.splitlines():
            # Skip header
            if 'osd' in line and 'commit_latency' in line:
                continue
            
            # Parse lines like: " 51                  61                 61"
            match = re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)', line)
            if match:
                osd_id = match.group(1)
                commit_lat = int(match.group(2))
                apply_lat = int(match.group(3))
                perf[osd_id] = {
                    'commit_latency_ms': commit_lat,
                    'apply_latency_ms': apply_lat
                }
                debug_print(f"OSD {osd_id}: commit={commit_lat}ms, apply={apply_lat}ms")
    
    print(f"Got performance data for {len(perf)} OSDs")
    return perf

def parse_device_id(device_ids_string):
    """Parse device_ids string from Ceph metadata."""
    if not device_ids_string:
        return None

    for part in device_ids_string.split(','):
        if '=' not in part:
            continue

        device_name, identifier = part.split('=', 1)
        device_name = device_name.strip()
        identifier = identifier.strip()

        parts = identifier.split('_')
        if len(parts) >= 3:
            vendor = parts[0]
            serial = parts[-1]
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
    """Match local physical drives to OSDs using device_ids."""
    print("\n" + "="*80)
    print("STEP 5: Matching Local Drives to OSDs")
    print("="*80)

    osd_to_drive = {}

    for osd_id, osd_meta in osds.items():
        device_ids = osd_meta.get('device_ids', '')
        hostname = osd_meta.get('hostname', 'unknown')

        parsed = parse_device_id(device_ids)
        if not parsed:
            debug_print(f"OSD {osd_id}: Could not parse device_ids: {device_ids}")
            continue

        osd_serial = parsed['serial']

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
    """Get OSD status information: up/down and in/out."""
    print("\n" + "="*80)
    print("STEP 6: Getting OSD Status")
    print("="*80)

    status_map = {}

    # Get up/down status from tree
    tree_output = run_command(["ceph", "osd", "tree"], is_json=False)
    if tree_output:
        for line in tree_output.splitlines():
            match = re.match(r'\s*(\d+)\s+\w+\s+[\d\.]+\s+osd\.\d+\s+(\w+)\s+.*', line)
            if match:
                osd_id = match.group(1)
                up_status = match.group(2)
                status_map[osd_id] = {
                    'up': (up_status == 'up'),
                    'in': None
                }

    # Get in/out status from dump
    dump_output = run_command(["ceph", "osd", "dump"], is_json=False)
    if dump_output:
        for line in dump_output.splitlines():
            match = re.search(r'osd\.(\d+)\s+(\w+)\s+(\w+)', line)
            if match:
                osd_id = match.group(1)
                in_status = match.group(3)
                if osd_id in status_map:
                    status_map[osd_id]['in'] = (in_status == 'in')

    debug_print(f"Got status for {len(status_map)} OSDs")
    return status_map

def check_systemd_status(osd_ids):
    """Check systemd service status for OSDs."""
    print("\n" + "="*80)
    print("STEP 7: Checking Systemd Service Status")
    print("="*80)

    systemd_status = {}

    for osd_id in osd_ids:
        service_name = f"ceph-osd@{osd_id}.service"
        result = run_command(["systemctl", "is-active", service_name],
                           is_json=False, silent=True)

        if result and result.strip() in ['active', 'activating']:
            systemd_status[osd_id] = 'active'
            debug_print(f"OSD {osd_id} systemd: active")
        elif result and result.strip() in ['inactive', 'failed', 'deactivating']:
            systemd_status[osd_id] = 'inactive'
            debug_print(f"OSD {osd_id} systemd: inactive ({result.strip()})")
        else:
            systemd_status[osd_id] = 'unknown'
            debug_print(f"OSD {osd_id} systemd: unknown")

    return systemd_status

def format_status(up, in_status, systemd):
    """Format combined status string."""
    parts = []
    if up:
        parts.append("up")
    else:
        parts.append("DOWN")

    if in_status:
        parts.append("in")
    else:
        parts.append("OUT")

    if systemd == 'active':
        parts.append("✓")
    elif systemd == 'inactive':
        parts.append("✗")
    else:
        parts.append("?")

    return " ".join(parts)

def format_smart_health(smart_details):
    """Format SMART health summary."""
    issues = []
    
    if smart_details.get('reallocated_sectors') and smart_details['reallocated_sectors'] > 0:
        issues.append(f"Realloc:{smart_details['reallocated_sectors']}")
    
    if smart_details.get('pending_sectors') and smart_details['pending_sectors'] > 0:
        issues.append(f"Pending:{smart_details['pending_sectors']}")
    
    if smart_details.get('uncorrectable') and smart_details['uncorrectable'] > 0:
        issues.append(f"Uncorr:{smart_details['uncorrectable']}")
    
    if issues:
        return " ".join(issues)
    
    return "OK"

def format_age(power_on_hours):
    """Format power-on hours as human readable age."""
    if not power_on_hours:
        return "N/A"
    
    years = power_on_hours / 8760  # 24*365
    if years >= 1:
        return f"{years:.1f}y"
    else:
        months = power_on_hours / 730  # ~30*24
        return f"{months:.0f}mo"

def format_output(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Format and display the final output table."""
    print("\n" + "="*160)
    print("DRIVE INVENTORY & OSD STATUS")
    print("="*160)

    # Build rows
    rows = []
    available_drives = []
    
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
            
            # Get performance
            perf = osd_perf.get(osd_id, {})
            latency_str = f"{perf.get('commit_latency_ms', 'N/A')}ms" if perf else "N/A"
        else:
            status_str = "N/A"
            latency_str = "N/A"

        current_dev = drive.get('current_device')
        current_dev_str = f"/dev/{current_dev}" if current_dev else "NOT MAPPED"

        model = drive.get('model', 'Unknown')
        if model and len(model) > 24:
            model = model[:21] + "..."
        elif not model:
            model = 'Unknown'

        scsi_addr = drive.get('scsi_address') or 'N/A'
        
        # SMART details
        smart = drive.get('smart_details', {})
        smart_health = format_smart_health(smart)
        temp_str = f"{smart.get('temperature')}°C" if smart.get('temperature') else "N/A"
        age_str = format_age(smart.get('power_on_hours'))

        row = {
            'osd_id': str(osd_id) if osd_id else 'N/A',
            'status': status_str or 'N/A',
            'latency': latency_str,
            'scsi_addr': scsi_addr if scsi_addr else 'N/A',
            'device': current_dev_str,
            'size': drive.get('size') or 'N/A',
            'phy_id': str(drive['phy_id']),
            'serial': serial or 'N/A',
            'health': drive.get('health_hw') or 'N/A',
            'smart_health': smart_health,
            'temp': temp_str,
            'age': age_str,
            'model': model or 'Unknown'
        }
        
        rows.append(row)
        
        # Track available drives
        if not osd_id and current_dev:
            available_drives.append(row)

    # Sort by SCSI address, then PHY ID
    def sort_key(row):
        scsi = row.get('scsi_addr')
        if scsi and scsi != 'N/A':
            try:
                parts = [int(x) for x in scsi.split(':')]
                return (0, parts)
            except:
                pass
        try:
            phy_id = int(row['phy_id']) if isinstance(row['phy_id'], str) else row['phy_id']
            return (1, phy_id)
        except:
            return (2, 999)

    rows.sort(key=sort_key)

    # Print header
    print("="*160)
    header_fmt = "{:<6} | {:<13} | {:<7} | {:<11} | {:<14} | {:<7} | {:<5} | {:<20} | {:<5} | {:<15} | {:<5} | {:<5} | {:<24}"
    print(header_fmt.format("OSD ID", "Status", "Latency", "SCSI Addr", "Current Device", "Size", "PHY", 
                           "Serial Number", "HW", "SMART Health", "Temp", "Age", "Model"))
    print("="*160)

    # Print rows
    for row in rows:
        print(header_fmt.format(
            row['osd_id'],
            row['status'],
            row['latency'],
            row['scsi_addr'],
            row['device'],
            row['size'],
            row['phy_id'],
            row['serial'][:20],  # Truncate long serials
            row['health'],
            row['smart_health'],
            row['temp'],
            row['age'],
            row['model']
        ))

    print("="*160)

    # Summary
    total_drives = len(drives)
    drives_with_osds = len(osd_to_drive)
    osds_up = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('up', False))
    osds_down = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('up', True))
    osds_in = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('in', False))
    osds_out = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('in', True))
    systemd_active = sum(1 for oid in osd_to_drive if systemd_status.get(oid) == 'active')
    hw_failed = sum(1 for d in drives.values() if d['health_hw'] == 'FAIL')
    drives_available = len(available_drives)

    print(f"\nSummary:")
    print(f"  Physical drives: {total_drives}")
    print(f"  Drives with OSDs: {drives_with_osds}")
    print(f"  Available for new OSDs: {drives_available}")
    print(f"  OSD Status: {osds_up} up/{osds_down} down, {osds_in} in/{osds_out} out")
    print(f"  Systemd: {systemd_active} active services")
    print(f"  Hardware failures: {hw_failed}")
    
    # Show available drives
    if available_drives:
        print(f"\n" + "="*80)
        print(f"DRIVES AVAILABLE FOR NEW OSDS ({len(available_drives)})")
        print("="*80)
        for avail in available_drives:
            print(f"  PHY {avail['phy_id']}: {avail['device']} - {avail['size']} - {avail['model']}")
            print(f"    Serial: {avail['serial']}, SCSI: {avail['scsi_addr']}, Age: {avail['age']}, Temp: {avail['temp']}")
            print(f"    Command: sudo ceph-volume lvm create --data {avail['device']}")
    
    # Recommendations
    print(f"\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    # Check for drives with SMART issues - FIXED: Handle None values properly
    problematic_drives = []
    for serial, drive in drives.items():
        smart = drive.get('smart_details', {})
        if ((smart.get('reallocated_sectors') or 0) > 0 or 
            (smart.get('pending_sectors') or 0) > 0 or 
            (smart.get('uncorrectable') or 0) > 0):
            # Find OSD ID
            osd_id = None
            for oid, drv_serial in osd_to_drive.items():
                if drv_serial == serial:
                    osd_id = oid
                    break
            problematic_drives.append((osd_id, drive))
    
    if problematic_drives:
        print("⚠️  URGENT: Drives with SMART errors (REPLACE IMMEDIATELY!):")
        for osd_id, drive in problematic_drives:
            smart = drive['smart_details']
            print(f"  OSD {osd_id if osd_id else 'N/A'} (PHY {drive['phy_id']}): "
                  f"Realloc={smart.get('reallocated_sectors') or 0}, "
                  f"Pending={smart.get('pending_sectors') or 0}, "
                  f"Uncorr={smart.get('uncorrectable') or 0}")
    else:
        print("✓ No drives with SMART errors detected")
    
    # Check for high latency OSDs
    high_latency = []
    for osd_id, perf in osd_perf.items():
        if perf.get('commit_latency_ms', 0) > 100:
            high_latency.append((osd_id, perf['commit_latency_ms']))
    
    if high_latency:
        high_latency.sort(key=lambda x: x[1], reverse=True)
        print(f"\n⚠️  OSDs with high latency (>100ms):")
        for osd_id, lat in high_latency[:5]:  # Show top 5
            print(f"  OSD {osd_id}: {lat}ms")
            # Find drive info
            for oid, serial in osd_to_drive.items():
                if oid == osd_id:
                    drive = drives[serial]
                    print(f"    PHY {drive['phy_id']}, Age: {format_age(drive['smart_details'].get('power_on_hours'))}")
                    break
    
    print(f"\nStatus Legend: [up/DOWN] [in/OUT] [✓ active / ✗ inactive / ? unknown]")
    print(f"SCSI Address: [Host:Channel:Target:LUN] - Physical location on controller")

def main():
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)

    print("="*80)
    print("CEPH OSD DRIVE MONITOR - Enhanced Edition")
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

    # Step 4: Get OSD performance
    osd_perf = get_osd_performance()

    # Step 5: Match local drives to OSDs
    osd_to_drive = match_drives_to_osds(drives, osds)

    # Step 6: Get OSD status (up/down, in/out)
    osd_status = get_osd_status()

    # Step 7: Check systemd status
    systemd_status = check_systemd_status(osd_to_drive.keys())

    # Display results
    format_output(drives, osd_to_drive, osd_status, systemd_status, osd_perf)

if __name__ == "__main__":
    main()