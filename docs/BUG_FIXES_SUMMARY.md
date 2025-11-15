# Bug Fixes and Improvements for check-osd2.py

## Bug Fixed

### TypeError: '>' not supported between instances of 'NoneType' and 'int'

**Location:** Line 580 in the `format_output()` function

**Problem:** 
The code was using `smart.get('pending_sectors', 0)` which returns `None` when the key exists but has a `None` value, instead of using the default `0`. This caused a TypeError when trying to compare `None > 0`.

**Original Code:**
```python
if (smart.get('reallocated_sectors', 0) > 0 or 
    smart.get('pending_sectors', 0) > 0 or
    smart.get('uncorrectable', 0) > 0):
```

**Fixed Code:**
```python
if ((smart.get('reallocated_sectors') or 0) > 0 or 
    (smart.get('pending_sectors') or 0) > 0 or 
    (smart.get('uncorrectable') or 0) > 0):
```

**Explanation:** 
Using `(value or 0)` ensures that if the value is `None`, it will be replaced with `0` before the comparison, preventing the TypeError.

---

## Feature Added: Drive Size for All Drives

### Enhancement to `get_local_physical_drives()` function

**Changes:**

1. **Added `format_size_bytes()` function:** Converts byte values to human-readable format (TB, GB, MB)

2. **Extract size from smartctl output:** 
   - Added code to extract the `user_capacity` field from smartctl JSON output
   - This provides size information even for drives that aren't currently mapped to `/dev/sdX` devices

3. **Debug output updated:** 
   - Now shows size information when scanning drives: `PHY {phy_id}: {model} S/N:{serial} Size:{size or 'N/A'}`

**Code Added:**
```python
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
```

**In `get_local_physical_drives()`:**
```python
# Extract size from smartctl output
size = None
if 'user_capacity' in info:
    # user_capacity is in format {"blocks": X, "bytes": Y}
    size_info = info['user_capacity']
    if isinstance(size_info, dict) and 'bytes' in size_info:
        size = format_size_bytes(size_info['bytes'])

drives[serial] = {
    # ... other fields ...
    'size': size,  # Now populated from smartctl
}
```

---

## Benefits

1. **No more crashes:** The script will now run to completion without the TypeError
2. **Complete size information:** All drives will show their size, not just those mapped to `/dev/sdX` devices
3. **Better debugging:** Size information is included in debug output for all discovered drives
4. **Consistent size format:** Uses the same human-readable format (TB/GB) for both smartctl-detected and lsblk-detected sizes

---

## Testing Recommendation

Run the fixed script with:
```bash
sudo python3 check-osd2.py
```

The script should now:
- Complete without errors
- Show size information for all 11 physical drives
- Display sizes for unmapped drives (PHY 6, 7, 9, 10, 12, 13)
