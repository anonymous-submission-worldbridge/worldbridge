#!/bin/sh

# Portable defaults; caller-provided environment variables take precedence.
_wb_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ ! -d "$_wb_dir/worldbridge" ] && [ "$_wb_dir" != / ]; do
    _wb_dir=$(dirname -- "$_wb_dir")
done
WORLDBRIDGE_ROOT=${WORLDBRIDGE_ROOT:-$_wb_dir}
WORLDBRIDGE_EXTERNAL=${WORLDBRIDGE_EXTERNAL:-$WORLDBRIDGE_ROOT/external}
WORLDBRIDGE_MODELS=${WORLDBRIDGE_MODELS:-$WORLDBRIDGE_ROOT/models}
WORLDBRIDGE_CACHE=${WORLDBRIDGE_CACHE:-$WORLDBRIDGE_ROOT/.cache}
WORLDBRIDGE_PYTHON=${WORLDBRIDGE_PYTHON:-python}
WORLDBRIDGE_SITE_PACKAGES=${WORLDBRIDGE_SITE_PACKAGES:-$WORLDBRIDGE_EXTERNAL/site-packages}
BLENDER_BIN=${BLENDER_BIN:-blender}
BLENDER_RESOURCES=${BLENDER_RESOURCES:-$WORLDBRIDGE_EXTERNAL/blender/resources}
export WORLDBRIDGE_ROOT WORLDBRIDGE_EXTERNAL WORLDBRIDGE_MODELS WORLDBRIDGE_CACHE

# Wait for all eight local RTX 4090 cards to have enough free memory for the
# connected villa scene, then render the interleaved frame sequence.

set -eu

ROOT="${WORLDBRIDGE_ROOT}"
DYNAMIC_BLEND="$ROOT/infinigen/outputs/indoor_outdoor_villa_demo2/dynamics/scene_dynamic.blend"
VIDEO="$ROOT/infinigen/outputs/indoor_outdoor_villa_demo2/videos/dynamic_all_gpus.mp4"
STATUS="$ROOT/infinigen/outputs/indoor_outdoor_villa_demo2/dynamics/all_gpus_render.status"
LOG="$ROOT/infinigen/outputs/indoor_outdoor_villa_demo2/dynamics/all_gpus_render.log"
MAX_USED_MIB=${C2W_MAX_GPU_USED_MIB:-4096}
GPU_COUNT=8
PCI_TAGS="pci-0000_4f_00_0 pci-0000_52_00_0 pci-0000_53_00_0 pci-0000_57_00_0 pci-0000_98_00_0 pci-0000_ce_00_0 pci-0000_d1_00_0 pci-0000_d6_00_0"

mkdir -p "$(dirname -- "$STATUS")" "$(dirname -- "$VIDEO")"

while :; do
    MEMORY=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null || true)
    COUNT=$(printf '%s\n' "$MEMORY" | awk 'NF {count++} END {print count+0}')
    if [ "$COUNT" -eq "$GPU_COUNT" ]; then
        MAX_USED=$(printf '%s\n' "$MEMORY" | awk 'NF && $1+0 > max {max=$1+0} END {print max+0}')
        if [ "$MAX_USED" -le "$MAX_USED_MIB" ]; then
            printf 'READY utc=%s max_used_mib=%s threshold_mib=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MAX_USED" "$MAX_USED_MIB" >"$STATUS"
            break
        fi
        printf 'WAITING utc=%s max_used_mib=%s threshold_mib=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MAX_USED" "$MAX_USED_MIB" >"$STATUS"
    else
        printf 'WAITING utc=%s reason=nvidia-smi-query-failed gpu_count=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$COUNT" >"$STATUS"
    fi
    sleep 45
done

printf 'RENDERING utc=%s GPUs=0,1,2,3,4,5,6,7\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$STATUS"

if C2W_GPU_PCI_TAGS="$PCI_TAGS" C2W_KEEP_FRAMES=0 \
    sh "$ROOT/scripts/render_dynamic_multigpu.sh" "$DYNAMIC_BLEND" "$VIDEO" "$GPU_COUNT" \
    >>"$LOG" 2>&1
then
    printf 'COMPLETE utc=%s video=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$VIDEO" >"$STATUS"
else
    code=$?
    printf 'FAILED utc=%s exit_code=%s log=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$code" "$LOG" >"$STATUS"
    exit "$code"
fi
