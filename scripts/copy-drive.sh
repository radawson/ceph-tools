#!/bin/bash
set -euo pipefail

LOG_DIR="/root/ddrescue-logs"

function copy_drive() {
    SRC=$1
    DST=$2
    LOG_PATH=$3
    
    # Safety check: prevent overwriting existing log unless it's empty or user confirms
    if [ -f "$LOG_PATH" ] && [ -s "$LOG_PATH" ]; then
        echo "Error: Log file $LOG_PATH already exists and is not empty."
        echo "To resume, use ddrescue directly or remove/backup the existing log first."
        exit 1
    fi
    
    # Create log directory if it doesn't exist
    mkdir -p "$LOG_DIR"
    
    # Run ddrescue
    ddrescue -f -n "$SRC" "$DST" "$LOG_PATH"
}

# Check input variables
if [ -z "${1:-}" ] || [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
    echo "Usage: $0 <src> <dst> <physical drive location>"
    exit 1
fi

# Validate source and destination exist
SRC="/dev/disk/by-id/scsi-$1"
DST="/dev/disk/by-id/scsi-$2"

if [ ! -b "$SRC" ]; then
    echo "Error: Source device $SRC does not exist or is not a block device."
    exit 1
fi

if [ ! -b "$DST" ]; then
    echo "Error: Destination device $DST does not exist or is not a block device."
    exit 1
fi

# Generate log filename: <location>-<src_id>.log
LOG_NAME="${3}-${1}"
LOG_PATH="${LOG_DIR}/${LOG_NAME}.log"

echo ">> Source: $SRC"
echo ">> Destination: $DST"
echo ">> Log file: $LOG_PATH"

copy_drive "$SRC" "$DST" "$LOG_PATH"