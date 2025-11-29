#!/bin/bash
set -euo pipefail

# Script to set RAID6 recovery drives to read-only mode
# NON-DESTRUCTIVE - only sets read-only flag, does not modify data

# Function to check if device is the root filesystem
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

# Function to check if device is mounted
is_mounted() {
    local dev="$1"
    mount | grep -q "^$dev " || findmnt "$dev" >/dev/null 2>&1
}

echo "=========================================="
echo "Setting RAID6 Recovery Drives to Read-Only"
echo "=========================================="
echo ""

# Identify root device for protection
root_device=$(findmnt -n -o SOURCE / 2>/dev/null || echo "unknown")
if [ "$root_device" != "unknown" ]; then
    echo "Root filesystem device: $root_device"
    echo "This device will be PROTECTED from read-only setting"
    echo ""
fi

# List of devices to set read-only
DEVICES=(sdb sdc sdd sde sdf sdg sdh sdi sdj sdk sdl sdm)

echo "Setting devices to read-only..."
echo ""

SET_COUNT=0
SKIP_COUNT=0
ERROR_COUNT=0

for dev in "${DEVICES[@]}"; do
    dev_path="/dev/$dev"
    
    # Check if device exists
    if [ ! -b "$dev_path" ]; then
        echo "  [SKIP] $dev_path does not exist"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi
    
    # Check if device is root filesystem
    if is_root_device "$dev_path"; then
        echo "  [PROTECT] $dev_path is the root filesystem - SKIPPING"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi
    
    # Check if device is mounted
    if is_mounted "$dev_path"; then
        echo "  [WARN] $dev_path is mounted - setting read-only anyway"
        echo "         (Consider unmounting first for safety)"
    fi
    
    # Set read-only
    echo "  [SETRO] Setting $dev_path read-only..."
    if blockdev --setro "$dev_path" 2>/dev/null; then
        SET_COUNT=$((SET_COUNT + 1))
        echo "  [OK] $dev_path set to read-only"
    else
        echo "  [ERROR] Failed to set $dev_path read-only"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done

echo ""
echo "=========================================="
echo "Verifying Read-Only Status"
echo "=========================================="
echo ""

for dev in "${DEVICES[@]}"; do
    dev_path="/dev/$dev"
    
    if [ ! -b "$dev_path" ]; then
        continue
    fi
    
    ro_status=$(blockdev --getro "$dev_path" 2>/dev/null || echo "unknown")
    if [ "$ro_status" = "1" ]; then
        echo "  ✓ $dev_path: READ-ONLY (1)"
    elif [ "$ro_status" = "0" ]; then
        echo "  ✗ $dev_path: READ-WRITE (0) - NOT PROTECTED"
    else
        echo "  ? $dev_path: Status unknown"
    fi
done

echo ""
echo "=========================================="
echo "Device List (lsblk)"
echo "=========================================="
lsblk -o NAME,SIZE,MODEL,SERIAL,RO

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Devices set to read-only: $SET_COUNT"
echo "Devices skipped: $SKIP_COUNT"
echo "Errors: $ERROR_COUNT"
echo ""
echo "Note: Read-only flag prevents accidental writes but does not"
echo "      guarantee protection if the device is forcibly written to."
echo ""

cat << EOF
Expected RAID6 member mapping:
member0 = slot0  -> /dev/sdm   (Z1Z37RJW clone)
member1 = slot1  -> /dev/sdd   (Z1Z3894R)
member2 = slot2  -> /dev/sde   (Z1Z77Q2M)
member3 = slot11 -> /dev/sdc   (Z1Z3J1PX clone: V1G186HF)
member4 = slot3  -> [dead Z1Z37RFX]  <-- will be replaced by Z1Z7C2G5
member5 = slot4  -> /dev/sdf   (S1Z0XVRX)
member6 = slot5  -> /dev/sdg   (Z1Z4FFQ8)
member7 = slot6  -> /dev/sdh   (Z1Z70R2W clone on Toshiba)
member8 = slot7  -> /dev/sdi   (Z1Z4EYWA)
member9 = slot8  -> /dev/sdj   (Z1Z71RT0)
member10= slot9  -> /dev/sdk   (Z1Z7VYXA clone on WD)
EOF
