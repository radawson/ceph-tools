#!/bin/bash
set -euo pipefail

# Script to test RAID6 reconstruction in READ-ONLY mode
# NON-DESTRUCTIVE - uses mdadm --build with --assume-clean and --readonly
# This does NOT write superblocks or modify data on member drives

echo "=========================================="
echo "RAID6 Test Assembly (Read-Only)"
echo "=========================================="
echo ""
echo "WARNING: This script will assemble a RAID6 array for testing."
echo "The array will be assembled in READ-ONLY mode with --assume-clean."
echo "This should NOT modify data on the member drives."
echo ""

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

# Check if /dev/md10 already exists
if [ -b "/dev/md10" ]; then
    echo "⚠️  WARNING: /dev/md10 already exists!"
    echo "   Current status:"
    if command -v mdadm >/dev/null 2>&1; then
        mdadm --detail /dev/md10 2>/dev/null || echo "   (Could not get details)"
    fi
    echo ""
    echo "   Options:"
    echo "   1. Stop existing array: mdadm --stop /dev/md10"
    echo "   2. Use a different device (e.g., /dev/md11)"
    echo ""
    read -p "   Stop /dev/md10 and continue? (yes/no): " response
    if [ "$response" != "yes" ]; then
        echo "   Aborting."
        exit 1
    fi
    echo "   Stopping /dev/md10..."
    if mdadm --stop /dev/md10 2>/dev/null; then
        echo "   ✓ Stopped"
    else
        echo "   ✗ Failed to stop /dev/md10"
        exit 1
    fi
    echo ""
fi

# Define RAID members
RAID_DEV="/dev/md10"
MEMBERS=(
    "/dev/sdm"   # member0
    "/dev/sdd"   # member1
    "/dev/sde"   # member2
    "/dev/sdc"   # member3
    "missing"    # member4 (dead drive)
    "/dev/sdf"   # member5
    "/dev/sdg"   # member6
    "/dev/sdh"   # member7
    "/dev/sdi"   # member8
    "/dev/sdj"   # member9
    "/dev/sdk"   # member10
)

echo "Verifying member devices..."
echo ""

# Verify devices exist and are not root
for member in "${MEMBERS[@]}"; do
    if [ "$member" = "missing" ]; then
        continue
    fi
    
    if [ ! -b "$member" ]; then
        echo "  ✗ ERROR: $member does not exist!"
        exit 1
    fi
    
    if is_root_device "$member"; then
        echo "  ✗ ERROR: $member is the root filesystem - ABORTING!"
        exit 1
    fi
    
    # Check if device is read-only (good sign)
    ro_status=$(blockdev --getro "$member" 2>/dev/null || echo "unknown")
    if [ "$ro_status" = "1" ]; then
        echo "  ✓ $member exists (read-only)"
    else
        echo "  ⚠️  $member exists (read-write) - consider setting read-only first"
    fi
done

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

echo ""
echo "=========================================="
echo "Assembling RAID6 array (READ-ONLY)"
echo "=========================================="
echo ""
echo "Command: mdadm --build $RAID_DEV --level=6 --raid-devices=11 --chunk=64 --assume-clean --readonly"
echo ""
echo "Safety flags:"
echo "  --assume-clean: Prevents resync/resync (no writes)"
echo "  --readonly: Sets array to read-only mode"
echo "  --build: Does NOT write superblocks (safer than --create)"
echo ""

# Assemble the array
if mdadm --build "$RAID_DEV" \
  --verbose \
  --level=6 \
  --raid-devices=11 \
  --chunk=64 \
  --assume-clean \
  --readonly \
  "${MEMBERS[@]}"; then
    echo ""
    echo "✓ RAID array assembled successfully!"
else
    echo ""
    echo "✗ ERROR: Failed to assemble RAID array"
    exit 1
fi

echo ""
echo "=========================================="
echo "Array Status (/proc/mdstat)"
echo "=========================================="
cat /proc/mdstat
echo ""

echo "=========================================="
echo "Array Details"
echo "=========================================="
mdadm --detail "$RAID_DEV"
echo ""

echo "=========================================="
echo "Partition Table (fdisk -l)"
echo "=========================================="
fdisk -l "$RAID_DEV" 2>&1 || echo "(fdisk may show errors if no partition table)"
echo ""

echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Array device: $RAID_DEV"
echo "Status: READ-ONLY (should not allow writes)"
echo ""
echo "To stop the array: mdadm --stop $RAID_DEV"
echo ""
