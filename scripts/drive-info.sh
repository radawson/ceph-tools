#!/bin/bash
set -euo pipefail

# Script to gather comprehensive information about physical drives
# Shows device names, device IDs, model, serial, size, and more

echo "=========================================="
echo "Physical Drive Information"
echo "=========================================="
echo ""

# Function to get human-readable size
format_size() {
    local bytes=$1
    if [ -z "$bytes" ] || [ "$bytes" = "0" ]; then
        echo "N/A"
        return
    fi
    local size=$(numfmt --to=iec-i --suffix=B "$bytes" 2>/dev/null || echo "${bytes}B")
    echo "$size"
}

# Function to get device information using smartctl
get_smart_info() {
    local dev="$1"
    local info=""
    
    if command -v smartctl >/dev/null 2>&1; then
        # Try without device type first (for direct SCSI/SATA)
        info=$(smartctl -i "$dev" 2>/dev/null || true)
        if [ -z "$info" ] || echo "$info" | grep -q "Unknown USB bridge"; then
            # Try with megaraid if it's behind a RAID controller
            info=$(smartctl -i -d megaraid,0 "$dev" 2>/dev/null || true)
        fi
    fi
    echo "$info"
}

# Function to extract serial from smartctl output
extract_serial() {
    local smart_output="$1"
    echo "$smart_output" | grep -i "serial number" | sed 's/.*[Ss]erial [Nn]umber[[:space:]]*:[[:space:]]*//' | tr -d ' ' || echo "N/A"
}

# Function to extract model from smartctl output
extract_model() {
    local smart_output="$1"
    echo "$smart_output" | grep -i "device model\|model family\|model name" | head -1 | sed 's/.*:[[:space:]]*//' | sed 's/[[:space:]]*$//' || echo "N/A"
}

# Function to get SCSI address using lsscsi
get_scsi_address() {
    local dev="$1"
    if command -v lsscsi >/dev/null 2>&1; then
        lsscsi | grep "$(basename "$dev")" | awk '{print "[" $1 "]"}'
    fi
}

# Function to get all device ID links
get_all_device_ids() {
    local dev_name="$1"
    local ids=()
    
    # by-id links
    while IFS= read -r link; do
        if [ -n "$link" ]; then
            ids+=("by-id: $(basename "$link")")
        fi
    done < <(find /dev/disk/by-id/ -lname "*$dev_name" 2>/dev/null | sort)
    
    # by-path links
    while IFS= read -r link; do
        if [ -n "$link" ]; then
            ids+=("by-path: $(basename "$link")")
        fi
    done < <(find /dev/disk/by-path/ -lname "*$dev_name" 2>/dev/null | sort)
    
    # by-uuid links (usually for partitions, but check anyway)
    while IFS= read -r link; do
        if [ -n "$link" ]; then
            ids+=("by-uuid: $(basename "$link")")
        fi
    done < <(find /dev/disk/by-uuid/ -lname "*$dev_name" 2>/dev/null | sort)
    
    # by-serial links
    while IFS= read -r link; do
        if [ -n "$link" ]; then
            ids+=("by-serial: $(basename "$link")")
        fi
    done < <(find /dev/disk/by-serial/ -lname "*$dev_name" 2>/dev/null | sort)
    
    printf '%s\n' "${ids[@]}"
}

# Function to get device size
get_device_size() {
    local dev="$1"
    if [ -b "$dev" ]; then
        local size_bytes=$(blockdev --getsize64 "$dev" 2>/dev/null || echo "0")
        format_size "$size_bytes"
    else
        echo "N/A"
    fi
}

# Function to check if device is a physical drive (not a partition)
is_physical_drive() {
    local dev="$1"
    local dev_name=$(basename "$dev")
    
    # Physical drives don't have numbers in their name (sda, not sda1)
    if [[ "$dev_name" =~ ^(sd[a-z]+|nvme[0-9]+n[0-9]+|hd[a-z]+)$ ]]; then
        return 0
    fi
    return 1
}

# Function to get comprehensive drive information
get_drive_info() {
    local device="$1"
    local dev_name=$(basename "$device")
    
    if ! is_physical_drive "$device"; then
        return 0  # Skip partitions
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Device: $device"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Get size
    local size=$(get_device_size "$device")
    echo "  Size: $size"
    
    # Get SCSI address
    local scsi_addr=$(get_scsi_address "$device")
    if [ -n "$scsi_addr" ]; then
        echo "  SCSI Address: $scsi_addr"
    fi
    
    # Get SMART information
    local smart_info=$(get_smart_info "$device")
    if [ -n "$smart_info" ]; then
        local model=$(extract_model "$smart_info")
        local serial=$(extract_serial "$smart_info")
        echo "  Model: $model"
        echo "  Serial: $serial"
    else
        echo "  Model: N/A (smartctl not available or device not accessible)"
        echo "  Serial: N/A"
    fi
    
    # Get all device ID links
    echo "  Device IDs:"
    local device_ids=$(get_all_device_ids "$dev_name")
    if [ -n "$device_ids" ]; then
        echo "$device_ids" | sed 's/^/    /'
    else
        echo "    No device ID links found"
    fi
    
    # Get realpath (resolved symlink)
    if [ -L "$device" ]; then
        local realpath=$(readlink -f "$device" 2>/dev/null || echo "N/A")
        echo "  Real Path: $realpath"
    fi
    
    # Check if mounted
    local mount_info=$(findmnt -n -o TARGET "$device" 2>/dev/null || true)
    if [ -n "$mount_info" ]; then
        echo "  Mounted at: $mount_info"
    else
        echo "  Mounted at: (not mounted)"
    fi
    
    # Check if device is in use by LVM
    if command -v pvs >/dev/null 2>&1; then
        local lvm_info=$(pvs --noheadings -o vg_name "$device" 2>/dev/null | tr -d ' ' || true)
        if [ -n "$lvm_info" ]; then
            echo "  LVM Volume Group: $lvm_info"
        fi
    fi
    
    # Check if device is part of a RAID array
    if [ -f /proc/mdstat ]; then
        local md_info=$(grep -E "^md[0-9]+.*$dev_name" /proc/mdstat | awk '{print $1}' || true)
        if [ -n "$md_info" ]; then
            echo "  RAID Array: /dev/$md_info"
        fi
    fi
    
    echo ""
}

# Main execution
echo "Scanning for physical drives..."
echo ""

# Check for SCSI/SATA drives (sd*)
found_drives=false
for device in /dev/sd[a-z]; do
    if [ -b "$device" ]; then
        get_drive_info "$device"
        found_drives=true
    fi
done

# Check for NVMe drives
for device in /dev/nvme[0-9]n[0-9]; do
    if [ -b "$device" ]; then
        get_drive_info "$device"
        found_drives=true
    fi
done

# Check for IDE/PATA drives (hd*)
for device in /dev/hd[a-z]; do
    if [ -b "$device" ]; then
        get_drive_info "$device"
        found_drives=true
    fi
done

if [ "$found_drives" = false ]; then
    echo "No physical drives found."
    echo ""
    echo "Available block devices:"
    lsblk -d -o NAME,SIZE,MODEL,SERIAL 2>/dev/null || echo "  (lsblk not available)"
fi

echo "=========================================="
echo "Scan complete!"
echo "=========================================="
echo ""
echo "Usage tips:"
echo "  - Use device IDs (by-id) for stable references in scripts"
echo "  - Use by-path for physical location references"
echo "  - Device names (sdX) may change after reboots"
echo ""