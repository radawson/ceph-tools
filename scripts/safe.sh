#!/bin/bash
set -euo pipefail

# Script to stop processes that might interfere with drive recovery
# WARNING: This will stop RAID arrays, multipath, and LVM volume groups
# The OS drive (RAID1) will be protected from being stopped

echo "=========================================="
echo "Drive Recovery Safety Script"
echo "=========================================="
echo ""

# Function to check if a device is mounted
is_mounted() {
    local dev="$1"
    mount | grep -q "^$dev " || findmnt "$dev" >/dev/null 2>&1
}

# Function to check if a device is the root filesystem
is_root_device() {
    local dev="$1"
    local root_dev=$(findmnt -n -o SOURCE / 2>/dev/null || echo "")
    if [ -z "$root_dev" ]; then
        return 1
    fi
    # Check direct match
    [ "$dev" = "$root_dev" ] && return 0
    # Check if dev is a symlink that resolves to root
    if [ -L "$dev" ]; then
        local resolved=$(readlink -f "$dev" 2>/dev/null || echo "")
        [ "$resolved" = "$root_dev" ] && return 0
    fi
    # Check if root_dev resolves to dev
    if [ -L "$root_dev" ]; then
        local root_resolved=$(readlink -f "$root_dev" 2>/dev/null || echo "")
        [ "$root_resolved" = "$dev" ] && return 0
    fi
    return 1
}

# Function to safely stop mdadm array
stop_md_array() {
    local md_dev="$1"
    if [ ! -b "$md_dev" ]; then
        echo "  [SKIP] $md_dev does not exist (this is normal)"
        return 0
    fi
    
    # Check if this is the root device
    if is_root_device "$md_dev" || is_mounted "$md_dev"; then
        echo "  [PROTECT] $md_dev appears to be the OS drive or is mounted - SKIPPING"
        return 0
    fi
    
    echo "  [STOP] Stopping $md_dev..."
    if mdadm --stop "$md_dev" 2>/dev/null; then
        echo "  [OK] $md_dev stopped"
    else
        echo "  [WARN] Failed to stop $md_dev (may be in use)"
    fi
}

# Function to check for active ddrescue processes
check_ddrescue() {
    if pgrep -f "ddrescue" >/dev/null 2>&1; then
        echo "  [WARN] Active ddrescue processes detected:"
        pgrep -af "ddrescue" | sed 's/^/    /'
        echo "  [INFO] Consider stopping these before running recovery operations"
    else
        echo "  [OK] No active ddrescue processes"
    fi
}

# Function to check for filesystem mounts on non-root devices
check_mounts() {
    echo "  [CHECK] Checking for filesystem mounts..."
    local found_mounts=false
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            local dev=$(echo "$line" | awk '{print $1}')
            local mountpoint=$(echo "$line" | awk '{print $2}')
            if [ "$mountpoint" != "/" ] && [ "$mountpoint" != "/boot" ] && [ "$mountpoint" != "/boot/efi" ]; then
                echo "    [WARN] $dev mounted at $mountpoint"
                found_mounts=true
            fi
    fi
    done < <(findmnt -n -o SOURCE,TARGET 2>/dev/null | grep -E "^/dev/(sd|md|dm-)" || true)
    
    if [ "$found_mounts" = false ]; then
        echo "  [OK] No non-root filesystem mounts found"
    fi
}

echo "[1/7] Checking for active ddrescue processes..."
check_ddrescue
echo ""

echo "[2/7] Checking for filesystem mounts and root device..."
# Identify root device for protection
root_device=$(findmnt -n -o SOURCE / 2>/dev/null || echo "unknown")
if [ "$root_device" != "unknown" ]; then
    echo "  [INFO] Root filesystem device: $root_device"
    # Check if root is on a software RAID
    if [[ "$root_device" =~ ^/dev/md ]]; then
        echo "  [PROTECT] Root is on software RAID - will protect this device"
    elif [[ "$root_device" =~ ^/dev/dm- ]]; then
        echo "  [INFO] Root is on device mapper (likely LVM) - will protect LVM VG"
    else
        echo "  [INFO] Root appears to be on hardware RAID or direct device"
    fi
else
    echo "  [WARN] Could not determine root device"
fi
check_mounts
echo ""

echo "[3/7] Stopping non-OS RAID arrays..."
# Find all active MD arrays and stop non-root ones
if [ -f /proc/mdstat ]; then
    # Parse mdstat to find active arrays (lines starting with md* that have : after the name)
    active_arrays=$(grep -E "^md[0-9]+ :" /proc/mdstat | awk '{print $1}' || true)
    
    if [ -z "$active_arrays" ]; then
        echo "  [INFO] No active software RAID arrays found in /proc/mdstat"
        echo "  [INFO] OS may be using hardware RAID or no RAID"
    else
        echo "  [INFO] Found active software RAID arrays, checking each..."
        while IFS= read -r md_dev; do
            if [ -n "$md_dev" ]; then
                stop_md_array "/dev/$md_dev"
            fi
        done <<< "$active_arrays"
    fi
else
    echo "  [INFO] /proc/mdstat not found - no software RAID arrays detected"
fi
echo ""

echo "[4/7] Stopping multipath services..."
# Stop socket first to avoid "triggering units" warning
if systemctl is-active --quiet multipathd.socket 2>/dev/null; then
    echo "  [STOP] Stopping multipathd.socket..."
    systemctl stop multipathd.socket 2>&1 || true
fi

if systemctl is-active --quiet multipathd.service 2>/dev/null; then
    echo "  [STOP] Stopping multipathd.service..."
    systemctl stop multipathd.service 2>&1 || true
    echo "  [OK] Multipath services stopped"
elif systemctl is-enabled --quiet multipathd.service 2>/dev/null; then
    echo "  [INFO] multipathd.service is installed but not currently running"
else
    echo "  [SKIP] multipathd is not installed or not running"
fi

echo "  [FLUSH] Flushing multipath devices..."
if command -v multipath >/dev/null 2>&1; then
    if multipath -F 2>/dev/null; then
        echo "  [OK] Multipath devices flushed"
    else
        echo "  [WARN] Failed to flush multipath (may already be clean)"
    fi
else
    echo "  [SKIP] multipath command not found"
fi
echo ""

echo "[5/7] Deactivating LVM volume groups..."
# Check which VGs exist and are not in use by root
if command -v vgs >/dev/null 2>&1; then
    root_vg=""
    root_lv=$(findmnt -n -o SOURCE / | sed 's/.*\///' || true)
    if [ -n "$root_lv" ]; then
        root_vg=$(lvs --noheadings -o vg_name "$root_lv" 2>/dev/null | tr -d ' ' || true)
    fi
    
    while IFS= read -r vg_name; do
        if [ -z "$vg_name" ]; then
            continue
        fi
        if [ "$vg_name" = "$root_vg" ]; then
            echo "  [PROTECT] Volume group '$vg_name' contains root filesystem - SKIPPING"
        else
            echo "  [DEACTIVATE] Deactivating volume group '$vg_name'..."
            if vgchange -an "$vg_name" 2>/dev/null; then
                echo "  [OK] Volume group '$vg_name' deactivated"
            else
                echo "  [WARN] Failed to deactivate '$vg_name' (may be in use)"
            fi
        fi
    done < <(vgs --noheadings -o vg_name 2>/dev/null || true)
else
    echo "  [SKIP] LVM tools not found"
fi
echo ""

echo "[6/7] Checking for SMART monitoring daemon..."
if systemctl is-active --quiet smartd 2>/dev/null; then
    echo "  [WARN] smartd is running - it may interfere with drive recovery"
    echo "  [INFO] Consider stopping it: systemctl stop smartd"
    echo "  [INFO] smartd can cause drive access conflicts during recovery"
else
    echo "  [OK] smartd is not running"
fi
echo ""

echo "[7/7] Checking for processes that may access drives..."
# Check for Ceph OSD processes
if command -v ceph >/dev/null 2>&1; then
    if pgrep -f "ceph-osd" >/dev/null 2>&1; then
        echo "  [WARN] Ceph OSD processes are running:"
        pgrep -af "ceph-osd" | head -5 | sed 's/^/    /'
        echo "  [INFO] Ceph OSDs may be accessing drives - consider stopping if needed"
    else
        echo "  [OK] No Ceph OSD processes detected"
    fi
else
    echo "  [SKIP] Ceph tools not found"
fi

# Check for other processes that might be accessing block devices
if command -v lsof >/dev/null 2>&1; then
    block_access=$(lsof 2>/dev/null | grep -E "^[^ ]+.*/dev/(sd|hd|nvme|md|dm-)" | grep -v " /dev/null" | head -10 || true)
    if [ -n "$block_access" ]; then
        echo "  [WARN] Processes accessing block devices:"
        echo "$block_access" | sed 's/^/    /'
        echo "  [INFO] These processes may interfere with drive recovery"
    else
        echo "  [OK] No processes detected accessing block devices (via lsof)"
    fi
else
    echo "  [SKIP] lsof not available - cannot check for block device access"
fi
echo ""

echo "=========================================="
echo "Safety checks complete!"
echo "=========================================="
echo ""
echo "Summary of actions taken:"
echo "  ✓ Checked for active ddrescue processes"
echo "  ✓ Checked for filesystem mounts"
echo "  ✓ Stopped non-OS software RAID arrays (if any existed)"
echo "  ✓ Stopped multipath services"
echo "  ✓ Deactivated LVM volume groups (except OS)"
echo "  ✓ Checked for SMART monitoring daemon"
echo "  ✓ Checked for Ceph OSD and other drive-accessing processes"
echo ""
echo "IMPORTANT REMINDERS:"
echo "  - OS drive (RAID1) has been protected from being stopped"
echo "  - Verify the target recovery drive is not mounted"
echo "  - Ensure no critical services are using the target drives"
echo "  - If smartd is running, consider stopping it to avoid conflicts:"
echo "    systemctl stop smartd"
echo "  - If Ceph OSDs are running, stop them if they use the target drive:"
echo "    systemctl stop ceph-osd@<id>.service"
echo ""
echo "You can now proceed with drive recovery operations."
echo ""
