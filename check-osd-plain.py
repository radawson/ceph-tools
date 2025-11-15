#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Plain Text Frontend

Uses the pure Python osd_core module for data collection.
No external dependencies required.

Usage:
    sudo python3 check-osd-plain.py
    sudo python3 check-osd-plain.py --export-csv
    sudo python3 check-osd-plain.py --export-json
"""

VERSION = "1.0.2"

import sys
import os
import argparse
import json
import csv
from datetime import datetime

# Import the core module
try:
    from osd_core import OSDMonitor
except ImportError:
    print("ERROR: Could not import osd_core module")
    print("Make sure osd_core.py is in the same directory")
    sys.exit(1)

def format_status(osd_id, osd_status, systemd_status):
    """Format combined status string."""
    if not osd_id:
        return "N/A"
    
    status = osd_status.get(osd_id, {})
    systemd = systemd_status.get(osd_id, 'unknown')
    
    parts = []
    parts.append("up" if status.get('up', False) else "DOWN")
    parts.append("in" if status.get('in', False) else "OUT")
    
    if systemd == 'active':
        parts.append("âœ“")
    elif systemd == 'inactive':
        parts.append("âœ—")
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

def display_plain_output(data):
    """Display output in plain text format."""
    drives = data['drives']
    osd_to_drive = data['osd_to_drive']
    osd_status = data['osd_status']
    systemd_status = data['systemd_status']
    osd_perf = data['osd_perf']
    controller_info = data.get('controller', {})
    
    # Display controller information
    print("\n" + "="*80)
    print("RAID CONTROLLER INFORMATION")
    print("="*80)
    controllers = controller_info.get('controllers', [])
    if controllers:
        for ctrl in controllers:
            print(f"  {ctrl['device']}: {ctrl['type']} - {ctrl['model']}")
        print(f"\nTotal controllers: {len(controllers)}")
    else:
        print("  No controller information available")
    print("="*80)
    
    # Build rows
    rows = []
    for serial, drive in drives.items():
        # Find OSD for this drive
        osd_id = None
        for oid, drv_serial in osd_to_drive.items():
            if drv_serial == serial:
                osd_id = oid
                break
        
        # Get data
        if osd_id:
            status_str = format_status(osd_id, osd_status, systemd_status)
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
        
        scsi_addr = drive.get('scsi_address') or 'N/A'
        controller = drive.get('controller', 'Unknown')
        if controller and len(controller) > 15:
            controller = controller[:12] + "..."
        
        smart = drive.get('smart_details', {})
        smart_health = format_smart_health(smart)
        temp_str = f"{smart.get('temperature')}Â°C" if smart.get('temperature') else "N/A"
        age_str = OSDMonitor.format_age(smart.get('power_on_hours'))
        
        row = {
            'osd_id': str(osd_id) if osd_id else 'N/A',
            'status': status_str,
            'latency': latency_str,
            'controller': controller,
            'scsi_addr': scsi_addr,
            'device': current_dev_str,
            'size': drive.get('size') or 'N/A',
            'phy_id': str(drive['phy_id']),
            'serial': serial,
            'health': drive.get('health_hw') or 'N/A',
            'smart_health': smart_health,
            'temp': temp_str,
            'age': age_str,
            'model': model
        }
        
        rows.append(row)
    
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
            phy_id = int(row['phy_id'])
            return (1, phy_id)
        except:
            return (2, 999)
    
    rows.sort(key=sort_key)
    
    # Print header
    print("\n" + "="*180)
    print("DRIVE INVENTORY & OSD STATUS")
    print("="*180)
    print("="*180)
    
    header_fmt = "{:<6} | {:<13} | {:<7} | {:<15} | {:<11} | {:<14} | {:<7} | {:<5} | {:<20} | {:<5} | {:<15} | {:<5} | {:<5} | {:<24}"
    print(header_fmt.format("OSD ID", "Status", "Latency", "Controller", "SCSI Addr", "Current Device", 
                           "Size", "PHY", "Serial Number", "HW", "SMART Health", 
                           "Temp", "Age", "Model"))
    print("="*180)
    
    # Print rows
    for row in rows:
        print(header_fmt.format(
            row['osd_id'],
            row['status'],
            row['latency'],
            row['controller'],
            row['scsi_addr'],
            row['device'],
            row['size'],
            row['phy_id'],
            row['serial'][:20],
            row['health'],
            row['smart_health'],
            row['temp'],
            row['age'],
            row['model']
        ))
    
    print("="*180)
    
    # Summary
    total_drives = len(drives)
    drives_with_osds = len(osd_to_drive)
    osds_up = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('up', False))
    osds_down = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('up', True))
    osds_in = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('in', False))
    osds_out = sum(1 for oid in osd_to_drive if not osd_status.get(oid, {}).get('in', True))
    systemd_active = sum(1 for oid in osd_to_drive if systemd_status.get(oid) == 'active')
    hw_failed = sum(1 for d in drives.values() if d['health_hw'] == 'FAIL')
    # Count drives that are mapped but not assigned to OSDs
    drives_available = 0
    for serial, drive in drives.items():
        if drive.get('current_device'):
            # Check if this drive is assigned to any OSD
            is_assigned = any(osd_to_drive.get(oid) == serial for oid in osd_to_drive)
            if not is_assigned:
                drives_available += 1
    
    print(f"\nSummary:")
    print(f"  Physical drives: {total_drives}")
    print(f"  Drives with OSDs: {drives_with_osds}")
    print(f"  Available for new OSDs: {len(drives) - drives_with_osds}")
    print(f"  OSD Status: {osds_up} up/{osds_down} down, {osds_in} in/{osds_out} out")
    print(f"  Systemd: {systemd_active} active services")
    print(f"  Hardware failures: {hw_failed}")
    
    # Analyze health
    issues = OSDMonitor.analyze_health(data)
    
    print(f"\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    if issues['smart_problems']:
        print("âš ï¸  URGENT: Drives with SMART errors (REPLACE IMMEDIATELY!):")
        for problem in issues['smart_problems']:
            drive = problem['drive']
            smart = drive['smart_details']
            osd_text = f"OSD {problem['osd_id']}" if problem['osd_id'] else "No OSD"
            print(f"  {osd_text} (PHY {drive['phy_id']}): "
                  f"Realloc={smart.get('reallocated_sectors') or 0}, "
                  f"Pending={smart.get('pending_sectors') or 0}, "
                  f"Uncorr={smart.get('uncorrectable') or 0}")
    else:
        print("âœ“ No drives with SMART errors detected")
    
    if issues['high_latency']:
        print(f"\nâš ï¸  OSDs with high latency (>100ms):")
        for item in sorted(issues['high_latency'], key=lambda x: x['latency'], reverse=True)[:5]:
            drive = item['drive']
            if drive:
                age = OSDMonitor.format_age(drive['smart_details'].get('power_on_hours'))
                print(f"  OSD {item['osd_id']}: {item['latency']}ms (PHY {drive['phy_id']}, Age: {age})")
            else:
                print(f"  OSD {item['osd_id']}: {item['latency']}ms (drive info not available)")
    
    if issues['available_drives']:
        print(f"\n" + "="*80)
        print(f"DRIVES AVAILABLE FOR NEW OSDS ({len(issues['available_drives'])})")
        print("="*80)
        for item in issues['available_drives']:
            drive = item['drive']
            print(f"  PHY {drive['phy_id']}: /dev/{drive['current_device']} - {drive['size']} - {drive['model']}")
            print(f"    Serial: {drive['serial']}, SCSI: {drive['scsi_address']}, "
                  f"Age: {OSDMonitor.format_age(drive['smart_details'].get('power_on_hours'))}, "
                  f"Temp: {drive['smart_details'].get('temperature')}Â°C")
            print(f"    Command: sudo ceph-volume lvm create --data /dev/{drive['current_device']}")
    
    print(f"\nStatus Legend: [up/DOWN] [in/OUT] [âœ“ active / âœ— inactive / ? unknown]")
    print(f"SCSI Address: [Host:Channel:Target:LUN] - Physical location on controller")

def export_csv(data, filename=None):
    """Export data to CSV format."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"osd_status_{timestamp}.csv"
    
    drives = data['drives']
    osd_to_drive = data['osd_to_drive']
    osd_status = data['osd_status']
    systemd_status = data['systemd_status']
    osd_perf = data['osd_perf']
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'osd_id', 'phy_id', 'scsi_address', 'current_device',
            'serial', 'model', 'vendor', 'size', 'status_up', 'status_in',
            'systemd_status', 'commit_latency_ms', 'apply_latency_ms',
            'hw_health', 'smart_realloc', 'smart_pending', 'smart_uncorr',
            'temperature_c', 'power_on_hours'
        ])
        
        for serial, drive in drives.items():
            # Find OSD
            osd_id = None
            for oid, drv_serial in osd_to_drive.items():
                if drv_serial == serial:
                    osd_id = oid
                    break
            
            # Get status
            if osd_id:
                status = osd_status.get(osd_id, {})
                systemd = systemd_status.get(osd_id, None)
                perf = osd_perf.get(osd_id, {})
            else:
                status = {}
                systemd = None
                perf = {}
            
            smart = drive.get('smart_details', {})
            
            writer.writerow([
                data['timestamp'],
                osd_id,
                drive['phy_id'],
                drive.get('scsi_address'),
                drive.get('current_device'),
                drive['serial'],
                drive['model'],
                drive.get('vendor'),
                drive.get('size'),
                status.get('up'),
                status.get('in'),
                systemd,
                perf.get('commit_latency_ms'),
                perf.get('apply_latency_ms'),
                drive.get('health_hw'),
                smart.get('reallocated_sectors'),
                smart.get('pending_sectors'),
                smart.get('uncorrectable'),
                smart.get('temperature'),
                smart.get('power_on_hours'),
            ])
    
    print(f"âœ“ Exported to CSV: {filename}")
    return filename

def export_json(data, filename=None):
    """Export data to JSON format."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"osd_status_{timestamp}.json"
    
    drives = data['drives']
    osd_to_drive = data['osd_to_drive']
    osd_status = data['osd_status']
    systemd_status = data['systemd_status']
    osd_perf = data['osd_perf']
    
    export_data = []
    
    for serial, drive in drives.items():
        # Find OSD
        osd_id = None
        for oid, drv_serial in osd_to_drive.items():
            if drv_serial == serial:
                osd_id = oid
                break
        
        # Get status
        if osd_id:
            status = osd_status.get(osd_id, {})
            systemd = systemd_status.get(osd_id, None)
            perf = osd_perf.get(osd_id, {})
        else:
            status = {}
            systemd = None
            perf = {}
        
        smart = drive.get('smart_details', {})
        
        export_data.append({
            'timestamp': data['timestamp'],
            'osd_id': osd_id,
            'phy_id': drive['phy_id'],
            'scsi_address': drive.get('scsi_address'),
            'current_device': drive.get('current_device'),
            'serial': drive['serial'],
            'model': drive['model'],
            'vendor': drive.get('vendor'),
            'size': drive.get('size'),
            'status_up': status.get('up'),
            'status_in': status.get('in'),
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
    
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"âœ“ Exported to JSON: {filename}")
    return filename

def main():
    parser = argparse.ArgumentParser(
        description='Ceph OSD Drive Monitor - Plain Text Frontend'
    )
    parser.add_argument('--export-csv', action='store_true',
                       help='Export data to CSV file')
    parser.add_argument('--export-json', action='store_true',
                       help='Export data to JSON file')
    parser.add_argument('--csv-file', type=str,
                       help='CSV filename (default: osd_status_TIMESTAMP.csv)')
    parser.add_argument('--json-file', type=str,
                       help='JSON filename (default: osd_status_TIMESTAMP.json)')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)
    
    print("="*80)
    print("CEPH OSD DRIVE MONITOR - Plain Text Edition")
    print("="*80)
    
    # Create monitor and scan
    monitor = OSDMonitor()
    data = monitor.scan()
    
    if not data:
        print("ERROR: Scan failed")
        sys.exit(1)
    
    # Display output
    display_plain_output(data)
    
    # Export if requested
    if args.export_csv or args.csv_file:
        print("\n" + "="*80)
        print("EXPORTING TO CSV")
        print("="*80)
        export_csv(data, args.csv_file)
    
    if args.export_json or args.json_file:
        print("\n" + "="*80)
        print("EXPORTING TO JSON")
        print("="*80)
        export_json(data, args.json_file)

if __name__ == "__main__":
    main()