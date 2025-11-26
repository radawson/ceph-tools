#!/bin/bash
set -euo pipefail

function check_logs() {
    LOG_DIR=$1
    if [ -z "$LOG_DIR" ]; then
        echo "Error: LOG_DIR is not set"
        exit 1
    elif [ ! -d "$LOG_DIR" ]; then
        echo "Warning: LOG_DIR $LOG_DIR does not exist, skipping..."
        return 0
    else
        echo "Reading logs from $LOG_DIR"
    fi

    # Find and sort logs by modification time (newest first)
    # Match both patterns: SSEAGATE_*.log and numbered patterns like 0-SSEAGATE_*.log
    LOGS=$(find "$LOG_DIR" -maxdepth 1 -type f \( -name 'SSEAGATE_ST4000NM0023_*.log' -o -name '*-SSEAGATE_ST4000NM0023_*.log' \) -printf '%T@ %p\n' 2>/dev/null | sort -n -r | cut -d' ' -f2-)

    if [ -z "$LOGS" ]; then
        echo "No ddrescue logs found in $LOG_DIR."
        return 0
    fi

    for log in $LOGS; do
        echo "==== $log ===="
        if [ -s "$log" ]; then
            if command -v ddrescuelog >/dev/null 2>&1; then
                ddrescuelog -t "$log"
            else
                echo "Warning: ddrescuelog not found, showing log file info:"
                ls -lh "$log"
            fi
        else
            echo "Log is empty or missing."
        fi
        echo
    done
}

echo "=== Checking RBD logs ==="
check_logs "/mnt/cephfs01/filestore_images/logs"

echo ""
echo "=== Checking physical device logs ==="
# Use same directory as copy-drive.sh
PHYSICAL_LOG_DIR="/root/ddrescue-logs"
check_logs "$PHYSICAL_LOG_DIR"