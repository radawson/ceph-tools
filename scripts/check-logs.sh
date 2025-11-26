#!/bin/bash

function check_logs() {
    LOG_DIR=$1
    if [ -z "$LOG_DIR" ]; then
        echo "LOG_DIR is not set"
        exit 1
    fi
    elseif [ ! -d "$LOG_DIR" ]; then
        echo "LOG_DIR does not exist"
        exit 1
    else
        echo "Reading logs from $LOG_DIR"
    fi


    # Find and sort logs by modification time (newest first)
    LOGS=$(find "$LOG_DIR" -name 'SSEAGATE_ST4000NM0023_*.log' -printf '%T@ %p\n' | sort -n -r | cut -d' ' -f2-)

    if [ -z "$LOGS" ]; then
        echo "No ddrescue logs found in $LOG_DIR."
        exit 0
    fi

    for log in $LOGS; do
        echo "==== $log ===="
        if [ -s "$log" ]; then
            ddrescuelog -t "$log"
        else
            echo "Log is empty or missing."
        fi
        echo
    done
}

echo "Checking RBD logs"    
check_logs "/mnt/cephfs01/filestore_images/logs"

echo "Check physical device logs"
check_logs ~/ddrescue-logs