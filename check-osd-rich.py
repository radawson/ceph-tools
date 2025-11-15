#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Rich + Pandas Frontend

Uses the pure Python osd_core module for data collection.
Requires: rich, pandas, openpyxl

Usage:
    sudo python3 check-osd-rich.py
    
Install dependencies:
    pip install rich pandas openpyxl
"""

import sys
import os
import argparse
from datetime import datetime

# Import the core module
try:
    from osd_core import OSDMonitor
except ImportError:
    print("ERROR: Could not import osd_core module")
    print("Make sure osd_core.py is in the same directory")
    sys.exit(1)

# Check for optional libraries
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import track
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

def build_dataframe(data):
    """Build Pandas DataFrame from scan data."""
    if not HAS_PANDAS:
        return None
    
    drives = data['drives']
    osd_to_drive = data['osd_to_drive']
    osd_status = data['osd_status']
    systemd_status = data['systemd_status']
    osd_perf = data['osd_perf']
    
    records = []
    
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
        
        records.append({
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
    
    df = pd.DataFrame(records)
    df = df.sort_values(['scsi_address', 'phy_id'])
    
    return df

def display_rich_output(data):
    """Display beautiful output using Rich."""
    if not HAS_RICH:
        print("ERROR: Rich not installed. Install with: pip install rich")
        return
    
    console = Console()
    
    # Build DataFrame for easier manipulation
    if HAS_PANDAS:
        df = build_dataframe(data)
    else:
        df = None
    
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
    
    # Build rows
    drives = data['drives']
    osd_to_drive = data['osd_to_drive']
    osd_status = data['osd_status']
    systemd_status = data['systemd_status']
    osd_perf = data['osd_perf']
    
    # Sort drives by SCSI address
    sorted_drives = sorted(drives.items(), key=lambda x: (
        x[1].get('scsi_address', 'ZZZ'),
        x[1]['phy_id']
    ))
    
    for serial, drive in sorted_drives:
        # Find OSD
        osd_id = None
        for oid, drv_serial in osd_to_drive.items():
            if drv_serial == serial:
                osd_id = oid
                break
        
        # Format OSD ID
        osd_text = str(osd_id) if osd_id else "[dim]N/A[/dim]"
        
        # Format status with colors
        status_parts = []
        if osd_id:
            status = osd_status.get(osd_id, {})
            systemd = systemd_status.get(osd_id)
            
            if status.get('up'):
                status_parts.append("[green]up[/green]")
            else:
                status_parts.append("[red bold]DOWN[/red bold]")
            
            if status.get('in'):
                status_parts.append("[green]in[/green]")
            else:
                status_parts.append("[yellow]OUT[/yellow]")
            
            if systemd == 'active':
                status_parts.append("[green]✓[/green]")
            elif systemd == 'inactive':
                status_parts.append("[red]✗[/red]")
            else:
                status_parts.append("[yellow]?[/yellow]")
        
        status_text = " ".join(status_parts) if status_parts else "[dim]N/A[/dim]"
        
        # Format latency with colors
        if osd_id:
            perf = osd_perf.get(osd_id, {})
            latency = perf.get('commit_latency_ms')
            if latency:
                if latency > 150:
                    latency_text = f"[red bold]{latency}ms[/red bold]"
                elif latency > 100:
                    latency_text = f"[yellow]{latency}ms[/yellow]"
                else:
                    latency_text = f"[green]{latency}ms[/green]"
            else:
                latency_text = "[dim]N/A[/dim]"
        else:
            latency_text = "[dim]N/A[/dim]"
        
        # Format device
        device = drive.get('current_device')
        device_text = f"/dev/{device}" if device else "[dim]NOT MAPPED[/dim]"
        
        # Format HW health
        hw_health = drive.get('health_hw')
        if hw_health == 'OK':
            hw_text = "[green]OK[/green]"
        elif hw_health == 'FAIL':
            hw_text = "[red bold]FAIL[/red bold]"
        else:
            hw_text = "[dim]N/A[/dim]"
        
        # Format SMART
        smart = drive.get('smart_details', {})
        realloc = smart.get('reallocated_sectors') or 0
        pending = smart.get('pending_sectors') or 0
        uncorr = smart.get('uncorrectable') or 0
        
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
        temp = smart.get('temperature')
        if temp:
            if temp > 50:
                temp_text = f"[red bold]{temp}°C[/red bold]"
            elif temp > 40:
                temp_text = f"[yellow]{temp}°C[/yellow]"
            else:
                temp_text = f"[green]{temp}°C[/green]"
        else:
            temp_text = "[dim]N/A[/dim]"
        
        # Format age
        age_text = OSDMonitor.format_age(smart.get('power_on_hours')) or "[dim]N/A[/dim]"
        
        # Truncate model
        model = drive.get('model', 'Unknown')
        if len(model) > 24:
            model = model[:21] + "..."
        
        table.add_row(
            osd_text,
            status_text,
            latency_text,
            drive.get('scsi_address', 'N/A'),
            device_text,
            drive.get('size', 'N/A'),
            str(drive['phy_id']),
            drive['serial'][:20],
            hw_text,
            smart_text,
            temp_text,
            age_text,
            model
        )
    
    console.print("\n")
    console.print(table)
    
    # Summary panel
    total_drives = len(drives)
    drives_with_osds = len(osd_to_drive)
    osds_up = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('up', False))
    osds_down = len(osd_to_drive) - osds_up
    osds_in = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('in', False))
    osds_out = len(osd_to_drive) - osds_in
    systemd_active = sum(1 for oid in osd_to_drive if systemd_status.get(oid) == 'active')
    hw_failures = sum(1 for d in drives.values() if d.get('health_hw') == 'FAIL')
    available = total_drives - drives_with_osds
    
    # Calculate stats
    temps = [d['smart_details'].get('temperature') for d in drives.values() 
             if d['smart_details'].get('temperature')]
    latencies = [osd_perf.get(oid, {}).get('commit_latency_ms') for oid in osd_to_drive
                if osd_perf.get(oid, {}).get('commit_latency_ms')]
    
    temp_stats = ""
    if temps:
        avg_temp = sum(temps) / len(temps)
        max_temp = max(temps)
        temp_stats = f"[bold]Temp:[/bold] Avg {avg_temp:.1f}°C, Max {max_temp:.1f}°C"
    
    latency_stats = ""
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        latency_stats = f"[bold]Latency:[/bold] Avg {avg_lat:.1f}ms, Max {max_lat:.1f}ms"
    
    summary_text = f"""[bold]Physical drives:[/bold] {total_drives}
[bold]Drives with OSDs:[/bold] {drives_with_osds}
[bold]Available for new OSDs:[/bold] [yellow]{available}[/yellow]
[bold]OSD Status:[/bold] [green]{osds_up} up[/green] / [red]{osds_down} down[/red], [green]{osds_in} in[/green] / [yellow]{osds_out} out[/yellow]
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
    issues = OSDMonitor.analyze_health(data)
    alerts = []
    
    if issues['smart_problems']:
        alerts.append(f"[red bold]⚠️  {len(issues['smart_problems'])} drive(s) with SMART errors - REPLACE IMMEDIATELY![/red bold]")
        for problem in issues['smart_problems']:
            drive = problem['drive']
            smart = drive['smart_details']
            osd_text = f"OSD {problem['osd_id']}" if problem['osd_id'] else "No OSD"
            alerts.append(f"   • {osd_text} (PHY {drive['phy_id']}): "
                         f"Realloc={smart.get('reallocated_sectors') or 0}, "
                         f"Pending={smart.get('pending_sectors') or 0}, "
                         f"Uncorr={smart.get('uncorrectable') or 0}")
    
    if issues['high_latency']:
        alerts.append(f"\n[yellow]⚠️  {len(issues['high_latency'])} OSD(s) with high latency (>100ms):[/yellow]")
        for item in sorted(issues['high_latency'], key=lambda x: x['latency'], reverse=True)[:5]:
            drive = item['drive']
            age = OSDMonitor.format_age(drive['smart_details'].get('power_on_hours')) if drive else 'N/A'
            alerts.append(f"   • OSD {item['osd_id']}: {item['latency']}ms "
                         f"(PHY {drive['phy_id']}, Age: {age})")
    
    if issues['high_temp']:
        alerts.append(f"\n[yellow]⚠️  {len(issues['high_temp'])} drive(s) running hot (>45°C):[/yellow]")
        for item in issues['high_temp'][:5]:
            drive = item['drive']
            osd_text = f"OSD {item['osd_id']}" if item['osd_id'] else "No OSD"
            alerts.append(f"   • {osd_text} (PHY {drive['phy_id']}): {item['temperature']}°C")
    
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
    
    # Excel export
    try:
        excel_file = f"{base_filename}_{timestamp}.xlsx"
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
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
            
            # Problem drives
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
        print(f"WARNING: Could not export to Excel: {e}")

def append_to_history(df, history_file='osd_history.csv'):
    """Append current scan to historical tracking file."""
    if not HAS_PANDAS:
        return
    
    try:
        if os.path.exists(history_file):
            history = pd.read_csv(history_file)
            combined = pd.concat([history, df], ignore_index=True)
        else:
            combined = df
        
        combined.to_csv(history_file, index=False)
        print(f"✓ Appended to history: {history_file}")
        print(f"  Total records: {len(combined)}")
    except Exception as e:
        print(f"WARNING: Could not append to history: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Ceph OSD Drive Monitor - Rich + Pandas Frontend'
    )
    parser.add_argument('--no-export', action='store_true',
                       help='Skip automatic export to CSV/JSON/Excel')
    parser.add_argument('--no-history', action='store_true',
                       help='Skip appending to history file')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)
    
    # Check dependencies
    if not HAS_RICH:
        print("WARNING: rich not installed - using plain output")
        print("Install with: pip install rich")
    
    if not HAS_PANDAS:
        print("WARNING: pandas not installed - export features disabled")
        print("Install with: pip install pandas openpyxl")
    
    if HAS_RICH:
        console = Console()
        console.print("\n[bold magenta]" + "="*40 + "[/bold magenta]")
        console.print("[bold cyan]CEPH OSD DRIVE MONITOR - Rich + Pandas Edition[/bold cyan]")
        console.print("[bold magenta]" + "="*40 + "[/bold magenta]\n")
    else:
        print("\n" + "="*80)
        print("CEPH OSD DRIVE MONITOR - Rich + Pandas Edition")
        print("="*80)
    
    # Create monitor and scan
    monitor = OSDMonitor()
    
    if HAS_RICH:
        console = Console()
        
        def progress_rich(current, total, message):
            # Rich progress is handled by track() in the core module
            pass
        
        data = monitor.scan(progress_callback=progress_rich)
    else:
        data = monitor.scan()
    
    if not data:
        print("ERROR: Scan failed")
        sys.exit(1)
    
    # Display output
    if HAS_RICH:
        display_rich_output(data)
    else:
        # Fall back to basic output if Rich not available
        print("\nScan completed. Use --help for options.")
        print("Install Rich for beautiful output: pip install rich")
    
    # Export data
    if HAS_PANDAS and not args.no_export:
        df = build_dataframe(data)
        
        print("\n" + "="*80)
        print("EXPORTING DATA")
        print("="*80)
        export_data(df)
        
        if not args.no_history:
            append_to_history(df)
    elif not HAS_PANDAS:
        print("\nInstall Pandas for export features: pip install pandas openpyxl")

if __name__ == "__main__":
    main()