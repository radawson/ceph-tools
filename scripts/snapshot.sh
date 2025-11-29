#!/bin/bash
set -euo pipefail

POOL="filestore_raw"
SNAP_NAME="pre-raid-test"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <IMAGE_NAME>"
    exit 1
fi

IMAGE_NAME="$1"
SRC_IMAGE="${POOL}/${IMAGE_NAME}"
SNAP_SPEC="${SRC_IMAGE}@${SNAP_NAME}"
CLONE_IMAGE="${POOL}/${IMAGE_NAME}_rebuild"

echo "Source image : ${SRC_IMAGE}"
echo "Snapshot     : ${SNAP_SPEC}"
echo "Clone target : ${CLONE_IMAGE}"
echo ""

# Sanity check: source image exists
if ! rbd info "${SRC_IMAGE}" >/dev/null 2>&1; then
    echo "ERROR: RBD image ${SRC_IMAGE} does not exist."
    exit 1
fi

# Create snapshot if it doesn't already exist
if rbd snap ls "${SRC_IMAGE}" | awk '{print $2}' | grep -qx "${SNAP_NAME}"; then
    echo "[SKIP] Snapshot ${SNAP_SPEC} already exists"
else
    echo "[SNAP] Creating snapshot ${SNAP_SPEC}..."
    rbd snap create "${SNAP_SPEC}"
fi

# Protect snapshot if not already protected
if rbd snap ls "${SRC_IMAGE}" | grep -q "${SNAP_NAME}.*protected"; then
    echo "[SKIP] Snapshot ${SNAP_SPEC} already protected"
else
    echo "[PROTECT] Protecting snapshot ${SNAP_SPEC}..."
    rbd snap protect "${SNAP_SPEC}"
fi

# Create clone if it doesn't already exist
if rbd info "${CLONE_IMAGE}" >/dev/null 2>&1; then
    echo "[SKIP] Clone ${CLONE_IMAGE} already exists"
else
    echo "[CLONE] Creating clone ${CLONE_IMAGE} from ${SNAP_SPEC}..."
    rbd clone "${SNAP_SPEC}" "${CLONE_IMAGE}"
fi

echo ""
echo "Done. Use ${CLONE_IMAGE} for RAID test assembly (NOT the original)."
