#!/bin/bash
set -euo pipefail

## Setting Variables
LOG_DIR="/mnt/cephfs01/filestore_images/logs"
POOL="filestore_raw"

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <sdX|/dev/disk/by-id/...> [resume]"
    exit 1
fi
ARG="$1"
RESUME_MODE="${2:-no}"  # Optional: pass 'resume' to force resume if possible

# Normalize to a full path
if [[ "$ARG" =~ ^sd[a-z]{1,2}$ ]]; then
    DEV="/dev/$ARG"
elif [[ "$ARG" =~ ^/dev/ ]]; then
    DEV="$ARG"
else
    echo "Error: argument must be sdX or a full /dev/... path"
    exit 1
fi

# Resolve symlink to underlying device
REALDEV=$(realpath "$DEV" 2>/dev/null || echo "$DEV")
if [ ! -b "$REALDEV" ]; then
    echo "Error: $REALDEV is not a valid block device."
    lsblk
    exit 1
fi

# Derive a nice, stable image/log name
BASENAME=$(basename "$ARG")
IMGBASE=$(echo "$BASENAME" | sed -e 's/^scsi-//' -e 's/^ata-//')
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/${IMGBASE}.log"
IMG="${POOL}/${IMGBASE}"

echo ">> Source device: $REALDEV"
echo ">> RBD image name: $IMG"
echo ">> ddrescue log: $LOG"

# Safety check: prevent overwriting existing non-empty log unless resuming
if [ -f "$LOG" ] && [ -s "$LOG" ] && [ "$RESUME_MODE" != "resume" ]; then
    echo "Error: Log file $LOG already exists and is not empty."
    echo "To resume, run with 'resume' as second argument: $0 $ARG resume"
    exit 1
fi

# Determine size of source block device (in bytes for precision, then MB)
SIZE_BYTES=$(blockdev --getsize64 "$REALDEV")
SIZE_MB=$(( (SIZE_BYTES + 1048575) / 1048576 ))  # Round up slightly for safety

if [ "$SIZE_MB" -le 0 ]; then
    echo "Error: could not determine size of $REALDEV"
    exit 1
fi
echo ">> Source size: $SIZE_MB MB ($SIZE_BYTES bytes)"

# Check if we can/should resume
if rbd info "$IMG" >/dev/null 2>&1; then
    if [ -f "$LOG" ] && [ "$RESUME_MODE" = "resume" ]; then
        echo ">> Resuming existing imaging for $IMG using log $LOG"
    else
        echo "Error: RBD image $IMG already exists. To resume, run with 'resume' as second arg."
        exit 1
    fi
else
    echo ">> Creating new RBD image..."
    rbd create "$IMG" --size "$SIZE_MB" --image-format 2
fi

# Map the RBD image
echo ">> Mapping RBD image..."
RBD_DEV=$(rbd map "$IMG")
echo ">> RBD mapped as: $RBD_DEV"

cleanup() {
    echo ">> Unmapping RBD image $IMG from $RBD_DEV"
    rbd unmap "$RBD_DEV" || true
}
trap cleanup EXIT INT TERM  # Handle signals better for reboots

# Run ddrescue with lower priority to reduce system stress
ionice -c2 -n7 nice -n19 ddrescue -f -d -n "$REALDEV" "$RBD_DEV" "$LOG"  # First: non-scratch pass
ionice -c2 -n7 nice -n19 ddrescue -f -d -r3 "$REALDEV" "$RBD_DEV" "$LOG"  # Then: retry pass (resumes if log exists)

echo ">> Imaging completed for $REALDEV -> $IMG"