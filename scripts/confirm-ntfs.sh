#!/bin/bash
set -euo pipefail

# Script to confirm NTFS alignment on RAID6 array members
# Checks for NTFS boot sector patterns at stripe offsets
# NON-DESTRUCTIVE - read-only operations only

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVEORDER_FILE="${SCRIPT_DIR}/driveorder.txt"
SUMMARY_FILE="${SCRIPT_DIR}/ntfs-alignment-summary-$(date +%Y%m%d-%H%M%S).txt"

# Parse arguments - simple approach
ARG1="${1:-}"
ARG2="${2:-}"

# Default stripe size
STRIPE_SIZE="65536"  # Default 64KB, common for Dell PERC830

# Determine mode: check if first argument is a device or RBD, otherwise assume it's a filename
if [ -z "$ARG1" ] || [ "$ARG1" = "--file" ]; then
    # No argument or explicit --file: use default file
    MODE="--file"
    # ARG2 might be stripe size
    if [ -n "$ARG2" ] && [[ "$ARG2" =~ ^[0-9]+$ ]] && [ "$ARG2" -gt 0 ]; then
        STRIPE_SIZE="$ARG2"
    fi
elif [[ "$ARG1" =~ ^/dev/ ]] || [[ "$ARG1" =~ ^rbd[[:space:]]+ ]]; then
    # First argument is a device path or RBD: single device mode
    MODE="$ARG1"
    # ARG2 might be stripe size
    if [ -n "$ARG2" ] && [[ "$ARG2" =~ ^[0-9]+$ ]] && [ "$ARG2" -gt 0 ]; then
        STRIPE_SIZE="$ARG2"
    fi
else
    # First argument is not a device: assume it's a filename
    MODE="--file"
    # Resolve file path (try multiple locations)
    if [ -f "$ARG1" ]; then
        DRIVEORDER_FILE="$ARG1"
    elif [ -f "${SCRIPT_DIR}/${ARG1}" ]; then
        DRIVEORDER_FILE="${SCRIPT_DIR}/${ARG1}"
    else
        echo "Error: File not found: $ARG1"
        exit 1
    fi
    # ARG2 might be stripe size
    if [ -n "$ARG2" ] && [[ "$ARG2" =~ ^[0-9]+$ ]] && [ "$ARG2" -gt 0 ]; then
        STRIPE_SIZE="$ARG2"
    fi
fi

# Validate stripe size is a positive integer
if ! [[ "$STRIPE_SIZE" =~ ^[0-9]+$ ]] || [ "$STRIPE_SIZE" -le 0 ]; then
    echo "Error: Stripe size must be a positive integer (bytes)"
    exit 1
fi

# Function to resolve RBD device
# Input: "rbd pool/image" or "rbd pool//image" (handles double slash)
# Output: mapped device path (e.g., /dev/rbd0)
map_rbd_device() {
    local rbd_spec="$1"
    local pool image
    
    # Parse "rbd pool/image" or "rbd pool//image" (handles both single and double slash)
    if [[ "$rbd_spec" =~ ^rbd[[:space:]]+([^/]+)/+(.+)$ ]]; then
        pool="${BASH_REMATCH[1]}"
        image="${BASH_REMATCH[2]}"
    else
        echo "Error: Invalid RBD format: $rbd_spec" >&2
        return 1
    fi
    
    local rbd_image="${pool}/${image}"
    
    # Check if already mapped
    local mapped_dev=$(rbd showmapped 2>/dev/null | awk -v img="$rbd_image" '$3 == img {print $5}')
    if [ -n "$mapped_dev" ] && [ -b "$mapped_dev" ]; then
        echo "$mapped_dev"
        return 0
    fi
    
    # Map the RBD device
    mapped_dev=$(rbd map "$rbd_image" 2>/dev/null)
    if [ -n "$mapped_dev" ] && [ -b "$mapped_dev" ]; then
        echo "$mapped_dev"
        return 0
    fi
    
    echo "Error: Failed to map RBD device: $rbd_image" >&2
    return 1
}

# Function to resolve device path (handles RBD, /dev paths, etc.)
resolve_device() {
    local device_spec="$1"
    local device
    
    # Trim whitespace
    device_spec=$(echo "$device_spec" | xargs)
    
    # Skip empty lines and comments
    if [ -z "$device_spec" ] || [[ "$device_spec" =~ ^# ]]; then
        return 1
    fi
    
    # Check if it's an RBD device
    if [[ "$device_spec" =~ ^rbd[[:space:]]+ ]]; then
        device=$(map_rbd_device "$device_spec")
        if [ $? -eq 0 ] && [ -n "$device" ]; then
            echo "$device"
            return 0
        fi
        return 1
    fi
    
    # Check if it's already a /dev path
    if [[ "$device_spec" =~ ^/dev/ ]]; then
        # Resolve symlinks
        device=$(readlink -f "$device_spec" 2>/dev/null || echo "$device_spec")
        if [ -b "$device" ]; then
            echo "$device"
            return 0
        fi
    fi
    
    return 1
}

# Function to write summary header to file
write_summary_header() {
    {
        echo "=========================================="
        echo "NTFS Alignment Check Summary"
        echo "=========================================="
        echo "Generated: $(date)"
        echo "Stripe Size: $STRIPE_SIZE bytes ($((STRIPE_SIZE / 1024))KB)"
        echo ""
    } >> "$SUMMARY_FILE"
}

# Function to append device result to summary file
append_summary_result() {
    local device_label="$1"
    local device_path="$2"
    local patterns_found="$3"
    local status="$4"
    
    {
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Device: $device_label"
        echo "Path: $device_path"
        echo "NTFS Patterns Found: $patterns_found"
        echo "Status: $status"
        echo ""
    } >> "$SUMMARY_FILE"
}

# NTFS boot sector signature patterns (global)
# Full signature: EB 52 90 4E 54 46 53 20 20 20 20
# At offset 0x03: "NTFS    " (4E 54 46 53 20 20 20 20)
NTFS_SIG_OFFSET_0x03="4E54465320202020"  # "NTFS    " at offset 0x03
NTFS_SIG_FULL="EB52904E54465320202020"    # Full boot sector signature

# Function to check a single device
check_device() {
    local DEVICE="$1"
    local device_label="$2"
    local summary_patterns=0
    local summary_status=""
    
    if [ ! -b "$DEVICE" ]; then
        echo "Error: $DEVICE is not a valid block device."
        append_summary_result "$device_label" "$DEVICE" "ERROR" "Device not accessible"
        return 1
    fi

    echo ""
    echo "=========================================="
    echo "NTFS Alignment Check for RAID6 Member"
    echo "=========================================="
    echo "Device Label: $device_label"
    echo "Device Path: $DEVICE"
    echo "Stripe Size: $STRIPE_SIZE bytes ($((STRIPE_SIZE / 1024))KB)"
    echo "Mode: READ-ONLY (non-destructive)"
    echo ""

# Function to check for NTFS signature at a specific offset
check_ntfs_at_offset() {
    local dev="$1"
    local offset="$2"
    local sig_type="$3"  # "offset3" or "full"
    
    # Read 11 bytes starting at offset
    local bytes=$(dd if="$dev" bs=1 skip="$offset" count=11 2>/dev/null | xxd -p | tr -d '\n')
    
    if [ -z "$bytes" ] || [ ${#bytes} -lt 22 ]; then
        return 1
    fi
    
    if [ "$sig_type" = "offset3" ]; then
        # Check "NTFS    " at offset 0x03 (bytes 6-13 of the 11-byte read)
        local ntfs_part="${bytes:12:16}"
        if [ "$ntfs_part" = "$NTFS_SIG_OFFSET_0x03" ]; then
            return 0
        fi
    elif [ "$sig_type" = "full" ]; then
        # Check full signature
        if [ "$bytes" = "$NTFS_SIG_FULL" ]; then
            return 0
        fi
    fi
    
    return 1
}

# Function to calculate entropy (simple randomness check)
# Returns a value 0-100, higher = more random
calculate_entropy() {
    local data="$1"
    local len=${#data}
    if [ "$len" -eq 0 ]; then
        echo "0"
        return
    fi
    
    # Count unique byte patterns (simplified)
    local unique=0
    for i in $(seq 0 2 $((len-2))); do
        local byte="${data:$i:2}"
        # This is a simplified check - just count if we see common patterns
        case "$byte" in
            00|FF|AA|55|CC|33) unique=$((unique + 1)) ;;
        esac
    done
    
    # More unique patterns = more random
    local ratio=$((unique * 100 / (len / 2)))
    echo "$ratio"
}

# Function to show hexdump of interesting area
show_hexdump() {
    local dev="$1"
    local offset="$2"
    local size="${3:-512}"
    
    echo "  Hexdump at offset $offset (${size} bytes):"
    dd if="$dev" bs=1 skip="$offset" count="$size" 2>/dev/null | \
        hexdump -C | head -n 20
}

echo "Checking for NTFS signatures at stripe offsets..."
echo ""

# Check at offset 0 (standard boot sector location)
echo "--- Offset 0x00000000 (standard boot sector) ---"
if check_ntfs_at_offset "$DEVICE" 0 "full"; then
    echo "✅ FULL NTFS boot sector signature found at offset 0!"
    echo "   This suggests the device may be the assembled RAID or a single disk."
    show_hexdump "$DEVICE" 0 512
    echo ""
elif check_ntfs_at_offset "$DEVICE" 0 "offset3"; then
    echo "⚠️  Partial NTFS signature (offset 0x03) found at offset 0"
    show_hexdump "$DEVICE" 0 512
    echo ""
else
    echo "❌ No NTFS signature at offset 0 (expected for RAID6 member)"
    echo ""
fi

# Check at multiple stripe offsets
echo "Checking at stripe-aligned offsets..."
echo ""

FOUND_PATTERNS=0
MAX_OFFSET=$((STRIPE_SIZE * 10))  # Check first 10 stripes

for offset in $(seq 0 "$STRIPE_SIZE" "$MAX_OFFSET"); do
    printf "Offset 0x%08X (%d bytes, stripe %d): " "$offset" "$offset" $((offset / STRIPE_SIZE))
    
    # Check for NTFS signature
    if check_ntfs_at_offset "$DEVICE" "$offset" "full"; then
        echo "✅ FULL NTFS SIGNATURE FOUND!"
        echo "   This is a strong indicator of correct first data member alignment."
        show_hexdump "$DEVICE" "$offset" 512
        FOUND_PATTERNS=$((FOUND_PATTERNS + 1))
        echo ""
    elif check_ntfs_at_offset "$DEVICE" "$offset" "offset3"; then
        echo "⚠️  Partial NTFS pattern detected (offset 0x03)"
        show_hexdump "$DEVICE" "$offset" 512
        FOUND_PATTERNS=$((FOUND_PATTERNS + 1))
        echo ""
    else
        # Check entropy to see if it looks random
        sample=$(dd if="$DEVICE" bs=1 skip="$offset" count=64 2>/dev/null | xxd -p | tr -d '\n')
        entropy=$(calculate_entropy "$sample")
        
        if [ "$entropy" -gt 50 ]; then
            echo "Random (entropy: ${entropy}%)"
        else
            echo "Low entropy (${entropy}%) - may contain structured data"
        fi
    fi
done

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Device Label: $device_label"
echo "Device Path: $DEVICE"
echo "Stripe Size: $STRIPE_SIZE bytes"
echo "NTFS Patterns Found: $FOUND_PATTERNS"
echo ""

if [ "$FOUND_PATTERNS" -gt 0 ]; then
    echo "✅ This device shows NTFS boot sector patterns at stripe offsets."
    echo "   This suggests it may be the CORRECT first data member."
    echo "   The patterns are shifted by the stripe size, which is expected"
    echo "   for RAID6 members containing NTFS data."
    summary_status="✅ LIKELY CORRECT - NTFS patterns found at stripe offsets"
else
    echo "❌ No NTFS patterns found at any stripe offset."
    echo "   This device appears random at all checked offsets."
    echo "   This suggests it may be:"
    echo "   - A parity disk"
    echo "   - An incorrectly ordered data member"
    echo "   - A disk from a different array"
    summary_status="❌ NO PATTERNS - Appears random (parity/incorrect order?)"
fi

    echo ""
    echo "Note: This is a READ-ONLY check. No data was modified."
    echo ""
    
    # Store result for summary
    append_summary_result "$device_label" "$DEVICE" "$FOUND_PATTERNS" "$summary_status"
}

# Main execution
if [ "$MODE" = "--help" ] || [ "$MODE" = "-h" ]; then
    echo "Usage: $0 [device|filename] [stripe_size]"
    echo ""
    echo "Modes:"
    echo "  <device>          Check a single device (e.g., /dev/sda or rbd pool/image)"
    echo "                    Usage: $0 <device> [stripe_size]"
    echo ""
    echo "  <filename>       Check all devices listed in file"
    echo "                    Usage: $0 <filename> [stripe_size]"
    echo ""
    echo "  (no args)        Check all devices in driveorder.txt"
    echo ""
    echo "Options:"
    echo "  stripe_size      Stripe size in bytes (default: 65536 = 64KB)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Check all in driveorder.txt"
    echo "  $0 driveorder.txt                     # Check all in specified file"
    echo "  $0 driveorder.txt 131072               # Use custom file + stripe size"
    echo "  $0 /dev/sda                           # Check single device"
    echo "  $0 /dev/sda 131072                    # Single device with stripe size"
    echo "  $0 rbd filestore_raw/image            # Check RBD device"
    echo ""
    echo "Common stripe sizes:"
    echo "  65536  = 64KB (default)"
    echo "  131072 = 128KB"
    echo ""
    echo "Device formats supported:"
    echo "  /dev/disk/by-id/...     Standard device path"
    echo "  /dev/sdX                Direct device"
    echo "  rbd pool/image          RBD device (will be mapped automatically)"
    exit 0
fi

# Determine mode
if [ "$MODE" = "--file" ] || [ -z "$MODE" ]; then
    # Batch mode: read from driveorder.txt
    if [ ! -f "$DRIVEORDER_FILE" ]; then
        echo "Error: Drive order file not found: $DRIVEORDER_FILE"
        exit 1
    fi
    
    # Initialize summary file
    write_summary_header
    
    echo "=========================================="
    echo "Batch NTFS Alignment Check"
    echo "=========================================="
    echo "Reading devices from: $DRIVEORDER_FILE"
    echo "Stripe Size: $STRIPE_SIZE bytes ($((STRIPE_SIZE / 1024))KB)"
    echo "Summary file: $SUMMARY_FILE"
    echo ""
    
    DEVICE_COUNT=0
    MAPPED_RBD_DEVICES=()
    
    # Read and process each line
    while IFS= read -r line || [ -n "$line" ]; do
        device_spec=$(echo "$line" | xargs)
        
        # Skip empty lines and comments
        if [ -z "$device_spec" ] || [[ "$device_spec" =~ ^# ]]; then
            continue
        fi
        
        DEVICE_COUNT=$((DEVICE_COUNT + 1))
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Processing device $DEVICE_COUNT: $device_spec"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Resolve device (handles RBD mapping)
        DEVICE=$(resolve_device "$device_spec")
        
        if [ $? -ne 0 ] || [ -z "$DEVICE" ]; then
            echo "❌ Error: Could not resolve device: $device_spec"
            echo ""
            continue
        fi
        
        # Track RBD devices for cleanup
        if [[ "$device_spec" =~ ^rbd[[:space:]]+ ]]; then
            MAPPED_RBD_DEVICES+=("$DEVICE")
        fi
        
        # Check the device
        check_device "$DEVICE" "$device_spec"
        
    done < "$DRIVEORDER_FILE"
    
    # Cleanup: unmap RBD devices
    if [ ${#MAPPED_RBD_DEVICES[@]} -gt 0 ]; then
        echo "=========================================="
        echo "Cleaning up RBD mappings..."
        echo "=========================================="
        for rbd_dev in "${MAPPED_RBD_DEVICES[@]}"; do
            if [ -b "$rbd_dev" ]; then
                rbd_image=$(rbd showmapped 2>/dev/null | awk -v dev="$rbd_dev" '$5 == dev {print $3}')
                if [ -n "$rbd_image" ]; then
                    echo "Unmapping $rbd_dev ($rbd_image)..."
                    rbd unmap "$rbd_dev" 2>/dev/null || true
                fi
            fi
        done
        echo ""
    fi
    
    echo "=========================================="
    echo "Batch check complete!"
    echo "=========================================="
    echo "Processed $DEVICE_COUNT device(s)"
    echo ""
    echo "Summary saved to: $SUMMARY_FILE"
    echo ""
    
    # Write final summary footer
    {
        echo "=========================================="
        echo "End of Summary"
        echo "=========================================="
        echo "Total devices processed: $DEVICE_COUNT"
        echo ""
    } >> "$SUMMARY_FILE"
    
else
    # Single device mode
    DEVICE=$(resolve_device "$MODE")
    
    if [ $? -ne 0 ] || [ -z "$DEVICE" ]; then
        echo "Error: Could not resolve device: $MODE"
        exit 1
    fi
    
    # Initialize summary file for single device mode
    write_summary_header
    
    # Track if we mapped an RBD device for cleanup
    MAPPED_RBD=false
    if [[ "$MODE" =~ ^rbd[[:space:]]+ ]]; then
        MAPPED_RBD=true
    fi
    
    echo "Summary file: $SUMMARY_FILE"
    echo ""
    
    # Check the device
    check_device "$DEVICE" "$MODE"
    
    # Cleanup RBD if we mapped it
    if [ "$MAPPED_RBD" = true ] && [ -b "$DEVICE" ]; then
        rbd_image=$(rbd showmapped 2>/dev/null | awk -v dev="$DEVICE" '$5 == dev {print $3}')
        if [ -n "$rbd_image" ]; then
            echo "Unmapping RBD device $DEVICE ($rbd_image)..."
            rbd unmap "$DEVICE" 2>/dev/null || true
        fi
    fi
    
    echo ""
    echo "Summary saved to: $SUMMARY_FILE"
    echo ""
fi