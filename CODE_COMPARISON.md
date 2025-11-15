# Side-by-Side Code Comparison

## Current Approach (Pure Python)

```python
def format_output(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Format and display the final output table."""
    print("\n" + "="*160)
    print("DRIVE INVENTORY & OSD STATUS")
    print("="*160)
    
    # Print header
    print("="*160)
    header_fmt = "{:<6} | {:<13} | {:<7} | {:<11} | {:<14} | {:<7} | {:<5} | {:<20} | {:<5} | {:<15} | {:<5} | {:<5} | {:<24}"
    print(header_fmt.format("OSD ID", "Status", "Latency", "SCSI Addr", 
                           "Current Device", "Size", "PHY", "Serial Number", 
                           "HW", "SMART Health", "Temp", "Age", "Model"))
    print("="*160)
    
    # Print rows
    for row in rows:
        print(header_fmt.format(
            row['osd_id'],
            row['status'],
            row['latency'],
            # ... 10 more fields ...
        ))
```

**Issues:**
- Manual column width calculation
- No colors - problems not visually obvious
- Hard to maintain if columns change
- No visual hierarchy

---

## Rich Approach (Recommended)

```python
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich.panel import Panel
from rich.text import Text
from rich import box

def format_output_rich(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Format and display output using Rich library."""
    console = Console()
    
    # Create main table with automatic column sizing
    table = Table(
        title="🖥️  Ceph OSD Drive Inventory & Status",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="blue"
    )
    
    # Add columns (Rich auto-calculates widths)
    table.add_column("OSD", justify="right", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")
    table.add_column("SCSI", style="dim")
    table.add_column("Device", style="yellow")
    table.add_column("Size", justify="right")
    table.add_column("PHY", justify="right", style="dim")
    table.add_column("Serial", style="dim")
    table.add_column("HW", justify="center")
    table.add_column("SMART", justify="center")
    table.add_column("Temp", justify="right")
    table.add_column("Age", justify="right")
    table.add_column("Model")
    
    # Build rows with conditional formatting
    for serial, drive in drives.items():
        # Find OSD
        osd_id = find_osd_for_drive(serial, osd_to_drive)
        
        # Get data
        smart = drive.get('smart_details', {})
        temp = smart.get('temperature')
        latency = get_latency(osd_id, osd_perf)
        
        # Format with colors based on status
        status_text = format_status_colored(osd_id, osd_status, systemd_status)
        latency_text = format_latency_colored(latency)
        temp_text = format_temp_colored(temp)
        smart_text = format_smart_colored(smart)
        
        table.add_row(
            str(osd_id) if osd_id else "[dim]N/A[/dim]",
            status_text,
            latency_text,
            drive.get('scsi_address', 'N/A'),
            drive.get('current_device', '[dim]NOT MAPPED[/dim]'),
            drive.get('size', 'N/A'),
            str(drive['phy_id']),
            drive['serial'][:20],
            "[green]OK[/green]" if drive['health_hw'] == 'OK' else "[red]FAIL[/red]",
            smart_text,
            temp_text,
            format_age(smart.get('power_on_hours')),
            drive['model'][:24]
        )
    
    console.print(table)
    
    # Summary panel
    summary = create_summary_panel(drives, osd_to_drive, osd_status)
    console.print(summary)
    
    # Alerts panel (if needed)
    alerts = create_alerts_panel(drives, osd_to_drive, osd_perf)
    if alerts:
        console.print(alerts)

def format_status_colored(osd_id, osd_status, systemd_status):
    """Return colored status string."""
    if not osd_id:
        return "[dim]N/A[/dim]"
    
    status = osd_status.get(osd_id, {})
    systemd = systemd_status.get(osd_id, 'unknown')
    
    parts = []
    
    # Up/Down
    if status.get('up'):
        parts.append("[green]up[/green]")
    else:
        parts.append("[red bold]DOWN[/red bold]")
    
    # In/Out
    if status.get('in'):
        parts.append("[green]in[/green]")
    else:
        parts.append("[yellow]OUT[/yellow]")
    
    # Systemd
    if systemd == 'active':
        parts.append("[green]✓[/green]")
    elif systemd == 'inactive':
        parts.append("[red]✗[/red]")
    else:
        parts.append("[yellow]?[/yellow]")
    
    return " ".join(parts)

def format_latency_colored(latency_ms):
    """Return colored latency string."""
    if not latency_ms or latency_ms == 'N/A':
        return "[dim]N/A[/dim]"
    
    if latency_ms > 150:
        return f"[red bold]{latency_ms}ms[/red bold]"
    elif latency_ms > 100:
        return f"[yellow]{latency_ms}ms[/yellow]"
    else:
        return f"[green]{latency_ms}ms[/green]"

def format_temp_colored(temp):
    """Return colored temperature string."""
    if not temp:
        return "[dim]N/A[/dim]"
    
    if temp > 50:
        return f"[red bold]{temp}°C[/red bold]"
    elif temp > 40:
        return f"[yellow]{temp}°C[/yellow]"
    else:
        return f"[green]{temp}°C[/green]"

def format_smart_colored(smart):
    """Return colored SMART status."""
    realloc = smart.get('reallocated_sectors') or 0
    pending = smart.get('pending_sectors') or 0
    uncorr = smart.get('uncorrectable') or 0
    
    if realloc > 0 or pending > 0 or uncorr > 0:
        issues = []
        if realloc > 0:
            issues.append(f"Realloc:{realloc}")
        if pending > 0:
            issues.append(f"Pending:{pending}")
        if uncorr > 0:
            issues.append(f"Uncorr:{uncorr}")
        return f"[red bold]{' '.join(issues)}[/red bold]"
    
    return "[green]OK[/green]"

def create_summary_panel(drives, osd_to_drive, osd_status):
    """Create a summary panel."""
    total = len(drives)
    with_osds = len(osd_to_drive)
    osds_up = sum(1 for oid in osd_to_drive if osd_status.get(oid, {}).get('up'))
    
    summary_text = f"""
[bold]Physical drives:[/bold] {total}
[bold]Drives with OSDs:[/bold] {with_osds}
[bold]OSD Status:[/bold] [green]{osds_up} up[/green]
"""
    
    return Panel(
        summary_text,
        title="📊 Summary",
        border_style="green",
        box=box.ROUNDED
    )

def create_alerts_panel(drives, osd_to_drive, osd_perf):
    """Create alerts panel for problems."""
    alerts = []
    
    # Check SMART
    for serial, drive in drives.items():
        smart = drive.get('smart_details', {})
        if (smart.get('reallocated_sectors') or 0) > 0:
            osd_id = find_osd_for_drive(serial, osd_to_drive)
            alerts.append(f"⚠️  [red]OSD {osd_id} (PHY {drive['phy_id']}): SMART errors detected[/red]")
    
    # Check latency
    for osd_id, perf in osd_perf.items():
        if perf.get('commit_latency_ms', 0) > 150:
            alerts.append(f"⚠️  [yellow]OSD {osd_id}: High latency ({perf['commit_latency_ms']}ms)[/yellow]")
    
    if alerts:
        return Panel(
            "\n".join(alerts),
            title="⚠️  Alerts",
            border_style="red",
            box=box.HEAVY
        )
    
    return None
```

**Benefits:**
- Automatic column sizing
- Color-coded problems stand out
- Visual hierarchy with panels
- Much easier to maintain
- Professional appearance

---

## Pandas Approach (Data Analysis Focus)

```python
import pandas as pd
from datetime import datetime

def format_output_pandas(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Format output using Pandas for analysis and export."""
    
    # Build DataFrame
    data = []
    for serial, drive in drives.items():
        osd_id = find_osd_for_drive(serial, osd_to_drive)
        
        if osd_id:
            status = osd_status.get(osd_id, {})
            perf = osd_perf.get(osd_id, {})
            systemd = systemd_status.get(osd_id, 'unknown')
        else:
            status = {}
            perf = {}
            systemd = None
        
        smart = drive.get('smart_details', {})
        
        data.append({
            'osd_id': osd_id,
            'phy_id': drive['phy_id'],
            'serial': drive['serial'],
            'model': drive['model'],
            'size': drive.get('size'),
            'current_device': drive.get('current_device'),
            'scsi_address': drive.get('scsi_address'),
            'status_up': status.get('up', None),
            'status_in': status.get('in', None),
            'systemd_status': systemd,
            'latency_ms': perf.get('commit_latency_ms'),
            'hw_health': drive.get('health_hw'),
            'smart_realloc': smart.get('reallocated_sectors'),
            'smart_pending': smart.get('pending_sectors'),
            'smart_uncorr': smart.get('uncorrectable'),
            'temperature_c': smart.get('temperature'),
            'power_on_hours': smart.get('power_on_hours'),
            'scan_timestamp': datetime.now().isoformat()
        })
    
    df = pd.DataFrame(data)
    
    # Display summary statistics
    print("\n" + "="*80)
    print("CEPH OSD SUMMARY STATISTICS")
    print("="*80)
    
    print(f"\nTotal Drives: {len(df)}")
    print(f"Drives with OSDs: {df['osd_id'].notna().sum()}")
    print(f"Available for new OSDs: {df['osd_id'].isna().sum()}")
    
    # Temperature stats
    if df['temperature_c'].notna().any():
        print(f"\nTemperature:")
        print(f"  Average: {df['temperature_c'].mean():.1f}°C")
        print(f"  Max: {df['temperature_c'].max():.1f}°C")
        print(f"  Min: {df['temperature_c'].min():.1f}°C")
    
    # Latency stats
    if df['latency_ms'].notna().any():
        print(f"\nLatency:")
        print(f"  Average: {df['latency_ms'].mean():.1f}ms")
        print(f"  Max: {df['latency_ms'].max():.1f}ms")
        print(f"  Median: {df['latency_ms'].median():.1f}ms")
    
    # Problem drives
    print("\n" + "="*80)
    print("PROBLEM ANALYSIS")
    print("="*80)
    
    # SMART issues
    smart_problems = df[
        (df['smart_realloc'].fillna(0) > 0) | 
        (df['smart_pending'].fillna(0) > 0) |
        (df['smart_uncorr'].fillna(0) > 0)
    ]
    
    if len(smart_problems) > 0:
        print(f"\n⚠️  {len(smart_problems)} drive(s) with SMART errors:")
        print(smart_problems[['osd_id', 'phy_id', 'smart_realloc', 
                             'smart_pending', 'smart_uncorr']].to_string(index=False))
    else:
        print("\n✓ No SMART errors detected")
    
    # High latency
    high_latency = df[df['latency_ms'].fillna(0) > 100].sort_values('latency_ms', ascending=False)
    
    if len(high_latency) > 0:
        print(f"\n⚠️  {len(high_latency)} OSD(s) with high latency:")
        print(high_latency[['osd_id', 'latency_ms', 'temperature_c', 
                           'power_on_hours']].head(10).to_string(index=False))
    
    # Display full table
    print("\n" + "="*80)
    print("FULL DRIVE INVENTORY")
    print("="*80)
    print(df.to_string(index=False))
    
    # Export to multiple formats
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # CSV for scripting
    csv_file = f"osd_status_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    print(f"\n✓ Exported to CSV: {csv_file}")
    
    # JSON for APIs
    json_file = f"osd_status_{timestamp}.json"
    df.to_json(json_file, orient='records', indent=2)
    print(f"✓ Exported to JSON: {json_file}")
    
    # Excel for management
    excel_file = f"osd_status_{timestamp}.xlsx"
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Current Status', index=False)
        
        # Add summary sheet
        summary_df = pd.DataFrame({
            'Metric': ['Total Drives', 'With OSDs', 'Average Temp', 
                      'Average Latency', 'SMART Errors'],
            'Value': [
                len(df),
                df['osd_id'].notna().sum(),
                f"{df['temperature_c'].mean():.1f}°C",
                f"{df['latency_ms'].mean():.1f}ms",
                len(smart_problems)
            ]
        })
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"✓ Exported to Excel: {excel_file}")
    
    return df

# Historical tracking
def append_to_history(df, history_file='osd_history.csv'):
    """Append current scan to historical database."""
    if os.path.exists(history_file):
        history = pd.read_csv(history_file)
        combined = pd.concat([history, df], ignore_index=True)
    else:
        combined = df
    
    combined.to_csv(history_file, index=False)
    print(f"\n✓ Appended to history: {history_file}")

# Trend analysis
def analyze_trends(history_file='osd_history.csv'):
    """Analyze trends over time."""
    if not os.path.exists(history_file):
        print("No history file found")
        return
    
    df = pd.read_csv(history_file)
    df['scan_timestamp'] = pd.to_datetime(df['scan_timestamp'])
    
    # Group by OSD and analyze
    for osd_id in df['osd_id'].unique():
        if pd.isna(osd_id):
            continue
        
        osd_data = df[df['osd_id'] == osd_id].sort_values('scan_timestamp')
        
        # Check if latency is increasing
        if len(osd_data) >= 3:
            recent_latency = osd_data['latency_ms'].tail(3).mean()
            old_latency = osd_data['latency_ms'].head(3).mean()
            
            if recent_latency > old_latency * 1.5:  # 50% increase
                print(f"⚠️  OSD {osd_id}: Latency trending up "
                      f"({old_latency:.1f}ms → {recent_latency:.1f}ms)")
        
        # Check temperature trends
        if len(osd_data) >= 3:
            recent_temp = osd_data['temperature_c'].tail(3).mean()
            old_temp = osd_data['temperature_c'].head(3).mean()
            
            if recent_temp > old_temp + 5:  # 5°C increase
                print(f"⚠️  OSD {osd_id}: Temperature trending up "
                      f"({old_temp:.1f}°C → {recent_temp:.1f}°C)")
```

**Benefits:**
- Export to CSV, JSON, Excel automatically
- Statistical analysis built-in
- Historical tracking and trend detection
- Easy filtering and grouping
- Can create charts with matplotlib

---

## Hybrid: Pandas + Rich (Best of Both)

```python
import pandas as pd
from rich.console import Console
from rich.table import Table

def format_output_hybrid(drives, osd_to_drive, osd_status, systemd_status, osd_perf):
    """Use Pandas for data, Rich for display."""
    
    # Build DataFrame (data manipulation with Pandas)
    df = build_dataframe(drives, osd_to_drive, osd_status, systemd_status, osd_perf)
    
    # Export to files
    df.to_csv('osd_status.csv', index=False)
    df.to_json('osd_status.json', orient='records', indent=2)
    
    # Display with Rich (beautiful terminal output)
    console = Console()
    
    # Main table
    table = Table(title="Ceph OSD Status", box=box.ROUNDED)
    
    for col in df.columns:
        table.add_column(col)
    
    for _, row in df.iterrows():
        # Add color formatting based on values
        colored_row = format_row_with_colors(row)
        table.add_row(*colored_row)
    
    console.print(table)
    
    # Summary stats from Pandas
    print(f"\nAverage latency: {df['latency_ms'].mean():.1f}ms")
    print(f"Drives with SMART errors: {df['smart_realloc'].gt(0).sum()}")
```

This gives you:
- Pandas' data manipulation and export
- Rich's beautiful display
- Best of both worlds!
