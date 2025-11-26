#!/bin/bash

function copy_drive() {
    SRC=$1
    DST=$2
    LOG_NAME=$3
    ddrescue -f -n "$SRC" "$DST" "/root/ddrescue-logs/$LOG_NAME.log"
}

# Check input variables
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Usage: $0 <src> <dst> <physical drive location>"
    exit 1
fi


SRC=/dev/disk/by-id/scsi-$1
DST=/dev/disk/by-id/scsi-$2
LOG_NAME=~/ddrescue-logs/${3}-${1}.log

copy_drive "$SRC" "$DST" "$LOG_NAME"