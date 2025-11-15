#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Rich + Pandas Edition

Features:
- Beautiful color-coded terminal output with Rich
- Data analysis and export with Pandas
- Historical tracking for trend analysis
- SCSI addresses for ALL drives (not just mapped ones)
- Export to CSV, JSON, Excel
- Foundation for web dashboard
"""

import subprocess
import json
import sys
import os
import re
from datetime import datetime
from pathlib import Path

# Check for required libraries
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("WARNING: pandas not installed. Install with: pip install pandas")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import track, Progress
    from rich.text import Text
    from rich import box
    from rich.layout import Layout
    from rich.live import Live
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("WARNING: rich not installed. Install with: pip install rich")

DEBUG = True

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

def get_controller_info(controller_dev):
    """Get RAID controller information including SCSI mapping."""
    # Try to get controller info with smartctl
    info = run_command(["smartctl", "-i", controller_dev], is_json=False, silent=True)
    
    controller_info = {
        'device': controller_dev,
        'type': 'Unknown',
        'model': 'Unknown',
        'scsi_host': 0,  # Default host number
    }
    
    if info:
        # Try to extract controller model
        for line in info.split('\n'):
            if 'device model' in line.lower() or 'product' in line.lower():
                controller_info['model'] = line.split(':', 1)[1].strip()
            if 'perc' in line.lower():
                controller_info['type'] = 'PERC'
            elif 'megaraid' in line.lower() or 'lsi' in line.lower():
                controller_info['type'] = 'MegaRAID'
    
    # Try to determine SCSI host from /sys
    # For most RAID controllers, drives are on host 0
    # But we can check /sys/class/scsi_host/ to be sure
    try:
        scsi_hosts = list(Path('/sys/class/scsi_host').glob('host*'))
        if scsi_hosts:
            # Usually the first host (host0) is the RAID controller
            controller_info['scsi_host'] = 0
            debug_print(f"Found SCSI hosts: {[h.name for h in scsi_hosts]}")
    except:
        pass
    
    debug_print(f"Controller: {controller_info['model']} ({controller_info['type']})")
    return controller_info

def build_scsi_address_from_phy(phy_id, controller_info):
    """
    Build SCSI address from PHY ID.
    For most RAID controllers: [Host:Channel:Target:LUN]
    - Host: Usually 0 (the controller)
    - Channel: Usually 0
    - Target: Usually equals PHY ID or slot number
    - LUN: Usually 0
    """
    host = controller_info.get('scsi_host', 0)
    channel = 0  # Most controllers use channel 0
    target = phy_id  # PHY ID typically maps to target
    lun = 0  # Single LUN per drive
    
    return f"{host}:{channel}:{target}:{lun}"

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

def get_local_physical_drives(controller_dev, controller_info):
    """
    Scan local RAID controller for ALL physical drives.
    Returns: {serial: {phy_id, serial, model, vendor, health_hw, smart_details, size, scsi_address}}
    """
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 1: Scanning Local Hardware[/bold cyan]")
        progress_range = track(range(32), description="Scanning PHY slots...")
    else:
        print("\n" + "="*80)
        print("STEP 1: Scanning Local Hardware")
        print("="*80)
        progress_range = range(32)

    drives = {}

    for phy_id in progress_range:
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
                size_info = info['user_capacity']
                if isinstance(size_info, dict) and 'bytes' in size_info:
                    size = format_size_bytes(size_info['bytes'])
            
            # Build SCSI address from PHY ID
            scsi_address = build_scsi_address_from_phy(phy_id, controller_info)

            drives[serial] = {
                'phy_id': phy_id,
                'serial': serial,
                'model': model,
                'vendor': vendor,
                'health_hw': 'OK' if health_passed else 'FAIL',
                'smart_details': smart_details,
                'current_device': None,  # Will be updated in mapping step
                'scsi_address': scsi_address,  # Now set for ALL drives
                'size': size,
            }

            debug_print(f"PHY {phy_id}: {model} S/N:{serial} SCSI:{scsi_address} Size:{size or 'N/A'}")

    if HAS_RICH:
        console.print(f"[green]✓ Found {len(drives)} physical drives on RAID controller[/green]")
    else:
        print(f"Found {len(drives)} physical drives on RAID controller")
    
    return drives

def map_drives_to_devices(drives):
    """
    Map physical drives to current /dev/sdX device names using lsscsi.
    Updates drives dict with current_device and better size info.
    """
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 2: Mapping to Current Device Names[/bold cyan]")
    else:
        print("\n" + "="*80)
        print("STEP 2: Mapping to Current Device Names and SCSI Addresses")
        print("="*80)

    # Use lsscsi to get device mappings
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
                        # Update SCSI address with actual mapped address (more accurate)
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
    
    if HAS_RICH:
        console.print(f"[green]✓ Mapped {mapped}/{len(drives)} physical drives to device names[/green]")
        if unmapped > 0:
            console.print(f"[yellow]  {unmapped} drive(s) not visible to OS (may be available for new OSDs)[/yellow]")
    else:
        print(f"Mapped {mapped}/{len(drives)} physical drives to device names")
        if unmapped > 0:
            print(f"  {unmapped} drive(s) not visible to OS (may be available for new OSDs)")

def get_ceph_osds():
    """Get ALL Ceph OSDs metadata."""
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 3: Querying Ceph Cluster for ALL OSDs[/bold cyan]")
    else:
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

    if HAS_RICH:
        console = Console()
        console.print(f"[green]✓ Found {len(osds)} OSDs in cluster[/green]")
    else:
        print(f"Found {len(osds)} OSDs in cluster")
    
    return osds

def get_osd_performance():
    """Get OSD performance metrics (latency)."""
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 4: Getting OSD Performance Metrics[/bold cyan]")
    else:
        print("\n" + "="*80)
        print("STEP 4: Getting OSD Performance Metrics")
        print("="*80)

    perf = {}
    output = run_command(["ceph", "osd", "perf"], is_json=False, silent=True)
    
    if output:
        for line in output.splitlines():
            if 'osd' in line and 'commit_latency' in line:
                continue
            
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
    
    if HAS_RICH:
        console = Console()
        console.print(f"[green]✓ Got performance data for {len(perf)} OSDs[/green]")
    else:
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
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 5: Matching Local Drives to OSDs[/bold cyan]")
    else:
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
            if HAS_RICH:
                console = Console()
                console.print(f"[green]✓ OSD {osd_id} (on {hostname}): Matched to local drive[/green]")
            else:
                print(f"✓ OSD {osd_id} (on {hostname}): Matched to local drive")
            debug_print(f"  Serial: {osd_serial}, PHY: {drives[osd_serial]['phy_id']}, "
                       f"Device: {drives[osd_serial].get('current_device', 'N/A')}")
        else:
            debug_print(f"OSD {osd_id} (on {hostname}): Serial {osd_serial} not found locally")

    if HAS_RICH:
        console = Console()
        console.print(f"\n[green]✓ Matched {len(osd_to_drive)} OSDs to local drives[/green]")
    else:
        print(f"\nMatched {len(osd_to_drive)} OSDs to local drives")
    
    return osd_to_drive

def get_osd_status():
    """Get OSD status information: up/down and in/out."""
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 6: Getting OSD Status[/bold cyan]")
    else:
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
    if HAS_RICH:
        console = Console()
        console.print("\n[bold cyan]STEP 7: Checking Systemd Service Status[/bold cyan]")
    else:
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

def build_dataframe(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Build Pandas DataFrame from drive data."""
    if not HAS_PANDAS:
        return None
    
    data = []
    timestamp = datetime.now().isoformat()
    
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
            perf = osd_perf.get(osd_id, {})
        else:
            status = {}
            systemd = None
            perf = {}
        
        smart = drive.get('smart_details', {})
        
        data.append({
            'timestamp': timestamp,
            'osd_id': osd_id,
            'phy_id': drive['phy_id'],
            'scsi_address': drive.get('scsi_address'),
            'current_device': drive.get('current_device'),
            'serial': drive['serial'],
            'model': drive['model'],
            'vendor': drive.get('vendor'),
            'size': drive.get('size'),
            'status_up': status.get('up', None),
            'status_in': status.get('in', None),
            'systemd_status': systemd,
            'commit_latency_ms': perf.get('commit_latency_ms'),
            'apply_latency_ms': perf.get('apply_latency_ms'),
            'hw_health': drive.get('health_hw'),
            'smart_realloc': smart.get('reallocated_sectors'),
            'smart_pending': smart.get('pending_sectors'),
            'smart_uncorr': smart.get('uncorrectable'),
            'temperature_c': smart.get('temperature'),
            'power_on_hours': smart.get('power_on_hours'),
        })
    
    df = pd.DataFrame(data)
    
    # Sort by SCSI address, then PHY ID
    df = df.sort_values(['scsi_address', 'phy_id'])
    
    return df

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

def display_rich_output(df):
    """Display beautiful output using Rich."""
    if not HAS_RICH:
        return
    
    console = Console()
    
    # Main table
    table = Table(
        title="🖥️  Ceph OSD Drive Inventory & Status",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        title_style="bold magenta"
    )
    
    # Add columns
    table.add_column("OSD", justify="right", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Latency", justify="right", no_wrap=True)
    table.add_column("SCSI Addr", style="dim", no_wrap=True)
    table.add_column("Device", style="yellow", no_wrap=True)
    table.add_column("Size", justify="right", no_wrap=True)
    table.add_column("PHY", justify="right", style="dim", no_wrap=True)
    table.add_column("Serial", style="dim")
    table.add_column("HW", justify="center", no_wrap=True)
    table.add_column("SMART", justify="center")
    table.add_column("Temp", justify="right", no_wrap=True)
    table.add_column("Age", justify="right", no_wrap=True)
    table.add_column("Model")
    
    # Add rows with conditional formatting
    for _, row in df.iterrows():
        # Format OSD ID
        osd_text = str(int(row['osd_id'])) if pd.notna(row['osd_id']) else "[dim]N/A[/dim]"
        
        # Format status with colors
        status_parts = []
        if pd.notna(row['status_up']):
            if row['status_up']:
                status_parts.append("[green]up[/green]")
            else:
                status_parts.append("[red bold]DOWN[/red bold]")
        
        if pd.notna(row['status_in']):
            if row['status_in']:
                status_parts.append("[green]in[/green]")
            else:
                status_parts.append("[yellow]OUT[/yellow]")
        
        if row['systemd_status'] == 'active':
            status_parts.append("[green]✓[/green]")
        elif row['systemd_status'] == 'inactive':
            status_parts.append("[red]✗[/red]")
        elif pd.notna(row['systemd_status']):
            status_parts.append("[yellow]?[/yellow]")
        
        status_text = " ".join(status_parts) if status_parts else "[dim]N/A[/dim]"
        
        # Format latency with colors
        latency = row['commit_latency_ms']
        if pd.notna(latency):
            latency = int(latency)
            if latency > 150:
                latency_text = f"[red bold]{latency}ms[/red bold]"
            elif latency > 100:
                latency_text = f"[yellow]{latency}ms[/yellow]"
            else:
                latency_text = f"[green]{latency}ms[/green]"
        else:
            latency_text = "[dim]N/A[/dim]"
        
        # Format device
        device = row['current_device']
        device_text = f"/dev/{device}" if pd.notna(device) else "[dim]NOT MAPPED[/dim]"
        
        # Format HW health
        hw_health = row['hw_health']
        if hw_health == 'OK':
            hw_text = "[green]OK[/green]"
        elif hw_health == 'FAIL':
            hw_text = "[red bold]FAIL[/red bold]"
        else:
            hw_text = "[dim]N/A[/dim]"
        
        # Format SMART
        realloc = row['smart_realloc'] if pd.notna(row['smart_realloc']) else 0
        pending = row['smart_pending'] if pd.notna(row['smart_pending']) else 0
        uncorr = row['smart_uncorr'] if pd.notna(row['smart_uncorr']) else 0
        
        if realloc > 0 or pending > 0 or uncorr > 0:
            smart_issues = []
            if realloc > 0:
                smart_issues.append(f"R:{int(realloc)}")
            if pending > 0:
                smart_issues.append(f"P:{int(pending)}")
            if uncorr > 0:
                smart_issues.append(f"U:{int(uncorr)}")
            smart_text = f"[red bold]{' '.join(smart_issues)}[/red bold]"
        else:
            smart_text = "[green]OK[/green]"
        
        # Format temperature
        temp = row['temperature_c']
        if pd.notna(temp):
            temp = int(temp)
            if temp > 50:
                temp_text = f"[red bold]{temp}°C[/red bold]"
            elif temp > 40:
                temp_text = f"[yellow]{temp}°C[/yellow]"
            else:
                temp_text = f"[green]{temp}°C[/green]"
        else:
            temp_text = "[dim]N/A[/dim]"
        
        # Format age
        age_text = format_age(row['power_on_hours']) if pd.notna(row['power_on_hours']) else "[dim]N/A[/dim]"
        
        # Truncate model
        model = str(row['model']) if pd.notna(row['model']) else 'Unknown'
        if len(model) > 24:
            model = model[:21] + "..."
        
        table.add_row(
            osd_text,
            status_text,
            latency_text,
            str(row['scsi_address']) if pd.notna(row['scsi_address']) else 'N/A',
            device_text,
            str(row['size']) if pd.notna(row['size']) else 'N/A',
            str(int(row['phy_id'])),
            str(row['serial'])[:20],
            hw_text,
            smart_text,
            temp_text,
            age_text,
            model
        )
    
    console.print("\n")
    console.print(table)
    
    # Summary panel
    total_drives = len(df)
    drives_with_osds = df['osd_id'].notna().sum()
    osds_up = df['status_up'].sum() if df['status_up'].notna().any() else 0
    osds_down = (~df['status_up']).sum() if df['status_up'].notna().any() else 0
    osds_in = df['status_in'].sum() if df['status_in'].notna().any() else 0
    osds_out = (~df['status_in']).sum() if df['status_in'].notna().any() else 0
    systemd_active = (df['systemd_status'] == 'active').sum()
    hw_failures = (df['hw_health'] == 'FAIL').sum()
    available = total_drives - drives_with_osds
    
    # Temperature stats
    temp_stats = ""
    if df['temperature_c'].notna().any():
        avg_temp = df['temperature_c'].mean()
        max_temp = df['temperature_c'].max()
        temp_stats = f"[bold]Temp:[/bold] Avg {avg_temp:.1f}°C, Max {max_temp:.1f}°C"
    
    # Latency stats
    latency_stats = ""
    if df['commit_latency_ms'].notna().any():
        avg_lat = df['commit_latency_ms'].mean()
        max_lat = df['commit_latency_ms'].max()
        latency_stats = f"[bold]Latency:[/bold] Avg {avg_lat:.1f}ms, Max {max_lat:.1f}ms"
    
    summary_text = f"""[bold]Physical drives:[/bold] {total_drives}
[bold]Drives with OSDs:[/bold] {drives_with_osds}
[bold]Available for new OSDs:[/bold] [yellow]{available}[/yellow]
[bold]OSD Status:[/bold] [green]{int(osds_up)} up[/green] / [red]{int(osds_down)} down[/red], [green]{int(osds_in)} in[/green] / [yellow]{int(osds_out)} out[/yellow]
[bold]Systemd Services:[/bold] [green]{systemd_active} active[/green]
[bold]Hardware Failures:[/bold] {"[red]" + str(hw_failures) + "[/red]" if hw_failures > 0 else "[green]0[/green]"}
{temp_stats}
{latency_stats}"""
    
    console.print(Panel(
        summary_text,
        title="📊 Summary Statistics",
        border_style="green",
        box=box.ROUNDED
    ))
    
    # Alerts panel
    alerts = []
    
    # SMART issues
    smart_problems = df[
        (df['smart_realloc'].fillna(0) > 0) | 
        (df['smart_pending'].fillna(0) > 0) |
        (df['smart_uncorr'].fillna(0) > 0)
    ]
    
    if len(smart_problems) > 0:
        alerts.append(f"[red bold]⚠️  {len(smart_problems)} drive(s) with SMART errors - REPLACE IMMEDIATELY![/red bold]")
        for _, drive in smart_problems.iterrows():
            osd_text = f"OSD {int(drive['osd_id'])}" if pd.notna(drive['osd_id']) else "No OSD"
            alerts.append(f"   • {osd_text} (PHY {int(drive['phy_id'])}): "
                         f"Realloc={int(drive['smart_realloc'] or 0)}, "
                         f"Pending={int(drive['smart_pending'] or 0)}, "
                         f"Uncorr={int(drive['smart_uncorr'] or 0)}")
    
    # High latency
    high_latency = df[df['commit_latency_ms'].fillna(0) > 100].sort_values('commit_latency_ms', ascending=False)
    if len(high_latency) > 0:
        alerts.append(f"\n[yellow]⚠️  {len(high_latency)} OSD(s) with high latency (>100ms):[/yellow]")
        for _, drive in high_latency.head(5).iterrows():
            alerts.append(f"   • OSD {int(drive['osd_id'])}: {int(drive['commit_latency_ms'])}ms "
                         f"(PHY {int(drive['phy_id'])}, Age: {format_age(drive['power_on_hours'])})")
    
    # High temperature
    hot_drives = df[df['temperature_c'].fillna(0) > 45]
    if len(hot_drives) > 0:
        alerts.append(f"\n[yellow]⚠️  {len(hot_drives)} drive(s) running hot (>45°C):[/yellow]")
        for _, drive in hot_drives.head(5).iterrows():
            osd_text = f"OSD {int(drive['osd_id'])}" if pd.notna(drive['osd_id']) else "No OSD"
            alerts.append(f"   • {osd_text} (PHY {int(drive['phy_id'])}): {int(drive['temperature_c'])}°C")
    
    if alerts:
        console.print(Panel(
            "\n".join(alerts),
            title="⚠️  Alerts & Recommendations",
            border_style="red",
            box=box.HEAVY
        ))
    else:
        console.print(Panel(
            "[green bold]✓ No critical issues detected[/green bold]",
            title="✓ System Health",
            border_style="green",
            box=box.ROUNDED
        ))
    
    console.print("\n[dim]Legend: R=Reallocated, P=Pending, U=Uncorrectable sectors[/dim]")

def export_data(df, base_filename='osd_status'):
    """Export data to CSV, JSON, and Excel."""
    if not HAS_PANDAS:
        print("WARNING: Pandas not available, cannot export data")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # CSV export
    csv_file = f"{base_filename}_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    print(f"✓ Exported to CSV: {csv_file}")
    
    # JSON export
    json_file = f"{base_filename}_{timestamp}.json"
    df.to_json(json_file, orient='records', indent=2, date_format='iso')
    print(f"✓ Exported to JSON: {json_file}")
    
    # Excel export with multiple sheets
    try:
        excel_file = f"{base_filename}_{timestamp}.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            # Main data sheet
            df.to_excel(writer, sheet_name='Current Status', index=False)
            
            # Summary sheet
            summary_data = {
                'Metric': [
                    'Total Drives',
                    'Drives with OSDs',
                    'Available Drives',
                    'OSDs Up',
                    'OSDs Down',
                    'Average Temperature (°C)',
                    'Max Temperature (°C)',
                    'Average Latency (ms)',
                    'Max Latency (ms)',
                    'SMART Errors',
                    'Hardware Failures'
                ],
                'Value': [
                    len(df),
                    df['osd_id'].notna().sum(),
                    len(df) - df['osd_id'].notna().sum(),
                    df['status_up'].sum() if df['status_up'].notna().any() else 0,
                    (~df['status_up']).sum() if df['status_up'].notna().any() else 0,
                    round(df['temperature_c'].mean(), 1) if df['temperature_c'].notna().any() else 'N/A',
                    round(df['temperature_c'].max(), 1) if df['temperature_c'].notna().any() else 'N/A',
                    round(df['commit_latency_ms'].mean(), 1) if df['commit_latency_ms'].notna().any() else 'N/A',
                    round(df['commit_latency_ms'].max(), 1) if df['commit_latency_ms'].notna().any() else 'N/A',
                    ((df['smart_realloc'].fillna(0) > 0) | 
                     (df['smart_pending'].fillna(0) > 0) | 
                     (df['smart_uncorr'].fillna(0) > 0)).sum(),
                    (df['hw_health'] == 'FAIL').sum()
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Problem drives sheet
            problem_drives = df[
                (df['smart_realloc'].fillna(0) > 0) | 
                (df['smart_pending'].fillna(0) > 0) |
                (df['smart_uncorr'].fillna(0) > 0) |
                (df['commit_latency_ms'].fillna(0) > 100) |
                (df['temperature_c'].fillna(0) > 45)
            ]
            if len(problem_drives) > 0:
                problem_drives.to_excel(writer, sheet_name='Problem Drives', index=False)
        
        print(f"✓ Exported to Excel: {excel_file}")
    except Exception as e:
        debug_print(f"Could not export to Excel: {e}")

def append_to_history(df, history_file='osd_history.csv'):
    """Append current scan to historical tracking file."""
    if not HAS_PANDAS:
        return
    
    try:
        if os.path.exists(history_file):
            # Load existing history
            history = pd.read_csv(history_file)
            # Append new data
            combined = pd.concat([history, df], ignore_index=True)
        else:
            combined = df
        
        # Save updated history
        combined.to_csv(history_file, index=False)
        print(f"✓ Appended to history: {history_file}")
        print(f"  Total records: {len(combined)}")
    except Exception as e:
        debug_print(f"Could not append to history: {e}")

def main():
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)

    # Print header
    if HAS_RICH:
        console = Console()
        console.print("\n[bold magenta]="*40 + "[/bold magenta]")
        console.print("[bold cyan]CEPH OSD DRIVE MONITOR - Rich + Pandas Edition[/bold cyan]")
        console.print("[bold magenta]="*40 + "[/bold magenta]\n")
    else:
        print("\n" + "="*80)
        print("CEPH OSD DRIVE MONITOR - Rich + Pandas Edition")
        print("="*80)
    
    if not HAS_PANDAS:
        print("WARNING: pandas not installed - data export features disabled")
        print("Install with: pip install pandas")
    
    if not HAS_RICH:
        print("WARNING: rich not installed - using plain text output")
        print("Install with: pip install rich")

    # Step 1: Find and get controller info
    controller_dev = find_raid_controller()
    controller_info = get_controller_info(controller_dev)

    # Step 2: Scan local hardware (now includes SCSI addresses for ALL drives)
    drives = get_local_physical_drives(controller_dev, controller_info)
    if not drives:
        print("ERROR: No drives found on local RAID controller")
        sys.exit(1)

    # Step 3: Map to device names (updates device names and refines SCSI addresses)
    map_drives_to_devices(drives)

    # Step 4: Get all OSDs from Ceph
    osds = get_ceph_osds()
    if not osds:
        print("ERROR: Could not get OSD metadata from Ceph")
        sys.exit(1)

    # Step 5: Get OSD performance
    osd_perf = get_osd_performance()

    # Step 6: Match local drives to OSDs
    osd_to_drive = match_drives_to_osds(drives, osds)

    # Step 7: Get OSD status (up/down, in/out)
    osd_status = get_osd_status()

    # Step 8: Check systemd status
    systemd_status = check_systemd_status(osd_to_drive.keys())

    # Build DataFrame
    if HAS_PANDAS:
        df = build_dataframe(drives, osd_to_drive, osd_status, systemd_status, osd_perf)
        
        # Display results
        if HAS_RICH:
            display_rich_output(df)
        else:
            print("\n" + "="*80)
            print("DRIVE INVENTORY")
            print("="*80)
            print(df.to_string(index=False))
        
        # Export data
        print("\n" + "="*80)
        print("EXPORTING DATA")
        print("="*80)
        export_data(df)
        
        # Append to history
        append_to_history(df)
    else:
        print("ERROR: pandas required for this version")
        sys.exit(1)

if __name__ == "__main__":
    main()