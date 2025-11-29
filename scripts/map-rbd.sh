#!/bin/bash
set -euo pipefail

# Script to map RBD devices
# Reads image names from images.txt and maps them
# Checks for existing mappings before creating new ones

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_FILE="${SCRIPT_DIR}/images.txt"
POOL="filestore_raw"  # Default pool name

# Function to check if RBD image is already mapped
is_rbd_mapped() {
    local image_name="$1"
    local rbd_image="${POOL}/${image_name}"
    
    # Check if image is already mapped
    local mapped_dev=$(rbd showmapped 2>/dev/null | awk -v img="$rbd_image" '$3 == img {print $5}')
    if [ -n "$mapped_dev" ] && [ -b "$mapped_dev" ]; then
        echo "$mapped_dev"
        return 0
    fi
    return 1
}

# Check if images.txt exists
if [ ! -f "$IMAGES_FILE" ]; then
    echo "Error: Images file not found: $IMAGES_FILE"
    exit 1
fi

echo "=========================================="
echo "Mapping RBD Devices"
echo "=========================================="
echo "Reading images from: $IMAGES_FILE"
echo "Pool: $POOL"
echo ""

MAPPED_COUNT=0
ALREADY_MAPPED_COUNT=0
ERROR_COUNT=0

# Read and process each image
while IFS= read -r image_name || [ -n "$image_name" ]; do
    # Trim whitespace and skip empty lines/comments
    image_name=$(echo "$image_name" | xargs)
    if [ -z "$image_name" ] || [[ "$image_name" =~ ^# ]]; then
        continue
    fi
    
    rbd_image="${POOL}/${image_name}"
    
    # Check if already mapped
    existing_dev=$(is_rbd_mapped "$image_name")
    if [ $? -eq 0 ] && [ -n "$existing_dev" ]; then
        echo "  [SKIP] $rbd_image is already mapped to $existing_dev"
        ALREADY_MAPPED_COUNT=$((ALREADY_MAPPED_COUNT + 1))
        continue
    fi
    
    # Map the RBD device
    echo "  [MAP] Mapping $rbd_image..."
    mapped_dev=$(rbd map "$rbd_image" 2>&1)
    map_exit_code=$?
    
    if [ $map_exit_code -eq 0 ]; then
        # rbd map outputs the device path on success
        # Check if output is a valid block device
        if [ -b "$mapped_dev" ]; then
            echo "  [OK] Mapped to $mapped_dev"
            MAPPED_COUNT=$((MAPPED_COUNT + 1))
        else
            # Sometimes rbd map outputs just the device name, try to verify
            # Check if it's now mapped
            verify_dev=$(is_rbd_mapped "$image_name")
            if [ $? -eq 0 ] && [ -n "$verify_dev" ]; then
                echo "  [OK] Mapped to $verify_dev"
                MAPPED_COUNT=$((MAPPED_COUNT + 1))
            else
                echo "  [WARN] Mapping reported success but device not found"
                echo "         Output: $mapped_dev"
                MAPPED_COUNT=$((MAPPED_COUNT + 1))
            fi
        fi
    else
        echo "  [ERROR] Failed to map $rbd_image"
        echo "          Error: $mapped_dev"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done < "$IMAGES_FILE"

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Newly mapped: $MAPPED_COUNT"
echo "Already mapped: $ALREADY_MAPPED_COUNT"
echo "Errors: $ERROR_COUNT"
echo ""

echo "=========================================="
echo "All Mapped RBD Devices"
echo "=========================================="
if command -v rbd >/dev/null 2>&1; then
    rbd showmapped 2>/dev/null || echo "(No mapped devices or rbd command failed)"
else
    echo "Error: rbd command not found"
fi
echo "=========================================="
echo ""
echo "Done"