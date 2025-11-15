# Ceph OSD Monitor: Library Comparison & Recommendations

## Current Approach: Pure Python (stdlib only)

### Pros:
- ✓ No dependencies - runs anywhere Python 3 is installed
- ✓ Lightweight and fast
- ✓ Full control over output format
- ✓ Easy to deploy on production servers

### Cons:
- ✗ Manual string formatting is tedious and error-prone
- ✗ Column alignment requires careful calculation
- ✗ No built-in export to CSV/JSON/Excel
- ✗ Sorting/filtering requires custom code
- ✗ No colors or rich formatting
- ✗ Harder to maintain complex table layouts

---

## Option 1: Add Rich (Recommended for monitoring scripts)

**Installation:** `pip install rich`
**Size:** ~500KB, pure Python, no C dependencies

### Pros:
- ✓ Beautiful terminal output with colors, borders, alignment
- ✓ Built-in progress bars for long operations
- ✓ Automatic column width calculation
- ✓ Tree views, panels, and layouts
- ✓ Syntax highlighting for logs
- ✓ Still relatively lightweight
- ✓ Great for interactive monitoring

### Cons:
- ✗ One dependency to manage
- ✗ Overkill if you only want CSV export

### Example Output:
```python
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich import box

console = Console()

# Create beautiful tables
table = Table(title="Ceph OSD Drive Status", box=box.ROUNDED)
table.add_column("OSD ID", style="cyan", justify="right")
table.add_column("Status", style="green")
table.add_column("Latency", justify="right")
table.add_column("Size", justify="right")
table.add_column("Temp", justify="right")
table.add_column("Age", justify="right")

# Add rows with conditional coloring
for drive in drives:
    latency_color = "red" if latency > 100 else "green"
    table.add_row(
        str(osd_id),
        "[green]up in ✓[/green]" if status else "[red]DOWN[/red]",
        f"[{latency_color}]{latency}ms[/{latency_color}]",
        size,
        temp,
        age
    )

console.print(table)

# Progress bars for scanning
for phy_id in track(range(32), description="Scanning drives..."):
    scan_drive(phy_id)
```

---

## Option 2: Add Pandas (Best for data analysis)

**Installation:** `pip install pandas`
**Size:** ~30MB with numpy dependency

### Pros:
- ✓ Powerful data manipulation (filter, sort, group, aggregate)
- ✓ Easy export to CSV, Excel, JSON, HTML, SQL
- ✓ Built-in statistics and analysis
- ✓ Great for historical tracking and trends
- ✓ Can create pivot tables, time series
- ✓ Easy to extend with data science tools

### Cons:
- ✗ Heavy dependency (~30MB)
- ✗ Slower startup time
- ✗ Overkill for simple table display
- ✗ Terminal output not as pretty as Rich

### Example Output:
```python
import pandas as pd

# Build DataFrame
df = pd.DataFrame([
    {
        'osd_id': osd_id,
        'status': status,
        'latency_ms': latency,
        'size_tb': size,
        'temp_c': temp,
        'age_years': age,
        'smart_realloc': realloc,
        'smart_pending': pending,
    }
    for drive in drives
])

# Easy filtering and analysis
high_latency = df[df['latency_ms'] > 100]
old_drives = df[df['age_years'] > 5]
failed_drives = df[df['smart_realloc'] > 0]

# Statistics
print(df.describe())
print(f"Average latency: {df['latency_ms'].mean():.2f}ms")
print(f"Drives needing replacement: {len(failed_drives)}")

# Export options
df.to_csv('osd_status.csv', index=False)
df.to_excel('osd_status.xlsx', index=False)
df.to_json('osd_status.json', orient='records')
df.to_html('osd_status.html', index=False)

# Pretty terminal output (still not as nice as Rich)
print(df.to_string())
```

---

## Option 3: Hybrid - Pandas + Rich (Best of both worlds)

**Installation:** `pip install pandas rich`

### Pros:
- ✓ Data manipulation with Pandas
- ✓ Beautiful display with Rich
- ✓ Export to any format
- ✓ Easy analysis and filtering

### Cons:
- ✗ Two dependencies, ~30MB total

### Example:
```python
import pandas as pd
from rich.console import Console
from rich.table import Table

# Create data with Pandas
df = pd.DataFrame(drive_data)

# Filter problematic drives
problems = df[(df['latency_ms'] > 100) | (df['smart_realloc'] > 0)]

# Display with Rich
table = Table(title=f"⚠️  {len(problems)} Drives Need Attention")
for col in df.columns:
    table.add_column(col)
for _, row in problems.iterrows():
    table.add_row(*[str(x) for x in row])

Console().print(table)

# Export
df.to_csv('osd_status.csv')
```

---

## Option 4: Lightweight - Just Tabulate

**Installation:** `pip install tabulate`
**Size:** ~30KB, pure Python

### Pros:
- ✓ Very lightweight
- ✓ Simple table formatting
- ✓ Multiple output formats (plain, grid, markdown, html)
- ✓ Easy to use
- ✓ No dependencies

### Cons:
- ✗ No colors or rich formatting
- ✗ No data manipulation features
- ✗ Limited to table display

### Example:
```python
from tabulate import tabulate

headers = ["OSD ID", "Status", "Latency", "Size", "Temp", "Age"]
rows = [
    [osd_id, status, latency, size, temp, age]
    for drive in drives
]

print(tabulate(rows, headers=headers, tablefmt="grid"))

# Export to markdown
with open('report.md', 'w') as f:
    f.write(tabulate(rows, headers=headers, tablefmt="github"))
```

---

## Recommendation by Use Case

### Use Case 1: Simple monitoring, no dependencies
**Recommendation:** Keep current pure Python approach
- Best for: Production servers, minimal dependencies, simple deployment
- Trade-off: More manual formatting code

### Use Case 2: Interactive monitoring and troubleshooting
**Recommendation:** Add Rich only
- Best for: Daily use, visual clarity, operator-friendly
- Trade-off: One dependency (~500KB)

### Use Case 3: Data analysis and historical tracking
**Recommendation:** Pandas + Rich (or Pandas + export to CSV and analyze separately)
- Best for: Capacity planning, trend analysis, reports
- Trade-off: Heavier dependencies (~30MB)

### Use Case 4: Quick improvement with minimal weight
**Recommendation:** Add Tabulate only
- Best for: Clean tables without bloat
- Trade-off: No colors or advanced features

---

## My Specific Recommendation for Your Use Case

Based on your Ceph OSD monitoring needs, I recommend: **Rich**

### Why Rich?
1. Your script is for **operational monitoring** - operators benefit from visual clarity
2. **Color-coded alerts** make problems immediately visible
3. **Progress bars** for the 32-PHY scan improve UX
4. **Conditional formatting** (red for high latency, yellow for warnings)
5. Still **lightweight enough** for server deployment
6. **No C dependencies** - pure Python, works everywhere

### Implementation Strategy:
1. Keep all current logic (data collection, SMART parsing, etc.)
2. Replace only the `format_output()` function with Rich tables
3. Add color-coding for temperature, latency, and SMART status
4. Add progress bars for scanning operations
5. Keep a `--plain` flag to output simple text for parsing by other tools

### When to Add Pandas:
Add Pandas later if you need:
- Historical tracking (save data over time)
- Trend analysis (latency increasing, temperatures rising)
- Capacity planning (predict when drives will fail)
- Complex filtering (find all drives from same batch)
- Export to Excel for management reports

---

## Quick Win: Add Export Without Heavy Dependencies

Even with pure Python, you can easily add CSV export:

```python
import csv

def export_csv(drives, osd_to_drive, filename='osd_status.csv'):
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['OSD_ID', 'Status', 'Latency_ms', 'Size', 'PHY', 
                        'Serial', 'Model', 'Temp_C', 'Age', 'SMART_Status'])
        
        for serial, drive in drives.items():
            # ... build row data ...
            writer.writerow([osd_id, status, latency, size, phy, 
                           serial, model, temp, age, smart_status])
```

And JSON export:

```python
import json

def export_json(drives, osd_to_drive, filename='osd_status.json'):
    data = []
    for serial, drive in drives.items():
        data.append({
            'osd_id': osd_id,
            'status': status,
            # ... all fields ...
        })
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
```

---

## Next Steps

Would you like me to create:

1. **Version with Rich** - Beautiful terminal output, recommended
2. **Version with Pandas** - Data analysis focus
3. **Both versions** - See them side by side
4. **Add CSV/JSON export only** - Keep pure Python but add export
5. **Modular version** - Support multiple output backends (--format=rich|plain|csv|json)

Let me know your preference and I'll implement it!
