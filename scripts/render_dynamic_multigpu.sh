#!/bin/sh

# Render an already animated .blend as interleaved PNG frames on every GPU,
# then encode the complete frame sequence as H.264 MP4.
#
# Usage:
#   sh scripts/render_dynamic_multigpu.sh DYNAMIC.blend OUTPUT.mp4 [GPU_COUNT]

set -eu

if [ "$#" -lt 2 ]; then
    echo "Usage: sh scripts/render_dynamic_multigpu.sh DYNAMIC.blend OUTPUT.mp4 [GPU_COUNT]"
    exit 1
fi

BLEND_PATH=$1
VIDEO_PATH=$2
GPU_COUNT=${3:-$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)}
BLENDER_COMMAND=${BLENDER_BIN:-blender}

if [ ! -f "$BLEND_PATH" ]; then
    echo "Error: dynamic scene does not exist: $BLEND_PATH"
    exit 1
fi
if [ "$GPU_COUNT" -lt 1 ]; then
    echo "Error: no GPU was selected"
    exit 1
fi

VIDEO_DIR=$(dirname -- "$VIDEO_PATH")
VIDEO_FILE=$(basename -- "$VIDEO_PATH")
VIDEO_STEM=${VIDEO_FILE%.*}
FRAME_DIR="$VIDEO_DIR/${VIDEO_STEM}_frames"
RUNTIME_DIR="$VIDEO_DIR/${VIDEO_STEM}_runtime"
REPORT_PATH=${BLEND_PATH%.blend}.dynamics.json
mkdir -p "$FRAME_DIR" "$RUNTIME_DIR" "$VIDEO_DIR"

if [ ! -f "$REPORT_PATH" ]; then
    echo "Error: dynamics report is missing: $REPORT_PATH"
    exit 1
fi

TIMELINE=$(python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); t=d["timeline"]; print(t["frame_start"], t["frame_end"], t["fps"])' "$REPORT_PATH")
set -- $TIMELINE
FRAME_START=$1
FRAME_END=$2
FPS=$3

gpu_pci_tag() {
    if [ -n "${C2W_GPU_PCI_TAGS:-}" ]; then
        printf '%s\n' "$C2W_GPU_PCI_TAGS" | awk -v item="$(( $1 + 1 ))" '{print $item}'
        return
    fi
    nvidia-smi --query-gpu=index,pci.bus_id --format=csv,noheader \
        | awk -F',' -v wanted="$1" '$1 + 0 == wanted {gsub(/ /, "", $2); print tolower($2)}' \
        | sed -e 's/^00000000:/pci-0000_/' -e 's/:/_/g' -e 's/\./_/g'
}

PIDS=""
GPU_INDEX=0
while [ "$GPU_INDEX" -lt "$GPU_COUNT" ]; do
    WORKER_START=$((FRAME_START + GPU_INDEX))
    if [ "$WORKER_START" -gt "$FRAME_END" ]; then
        break
    fi
    PCI_TAG=$(gpu_pci_tag "$GPU_INDEX")
    if [ -z "$PCI_TAG" ]; then
        echo "Error: could not resolve PCI device for GPU $GPU_INDEX"
        exit 1
    fi
    WORKER_DIR="$RUNTIME_DIR/gpu_${GPU_INDEX}"
    mkdir -p "$WORKER_DIR/tmp" "$WORKER_DIR/cache"
    LOG_PATH="$WORKER_DIR/render.log"
    echo "[multi-gpu] GPU $GPU_INDEX ($PCI_TAG): frames $WORKER_START..$FRAME_END step $GPU_COUNT"
    DRI_PRIME="$PCI_TAG" \
    CUDA_VISIBLE_DEVICES="$GPU_INDEX" \
    TMPDIR="$WORKER_DIR/tmp" \
    XDG_CACHE_HOME="$WORKER_DIR/cache" \
    nice -n 10 "$BLENDER_COMMAND" --gpu-backend vulkan --disable-depsgraph-on-file-load \
        --background "$BLEND_PATH" \
        --render-output "$FRAME_DIR/frame_####" \
        --render-format PNG \
        --frame-start "$WORKER_START" \
        --frame-end "$FRAME_END" \
        --frame-jump "$GPU_COUNT" \
        --render-anim >"$LOG_PATH" 2>&1 &
    PIDS="$PIDS $!"
    GPU_INDEX=$((GPU_INDEX + 1))
done

FAILED=0
for PID in $PIDS; do
    if ! wait "$PID"; then
        FAILED=1
    fi
done
if [ "$FAILED" -ne 0 ]; then
    echo "Error: at least one GPU worker failed; inspect $RUNTIME_DIR/gpu_*/render.log"
    exit 1
fi

FRAME=$FRAME_START
while [ "$FRAME" -le "$FRAME_END" ]; do
    FILE=$(printf '%s/frame_%04d.png' "$FRAME_DIR" "$FRAME")
    if [ ! -s "$FILE" ]; then
        echo "Error: missing rendered frame: $FILE"
        exit 1
    fi
    FRAME=$((FRAME + 1))
done

ffmpeg -y -framerate "$FPS" -start_number "$FRAME_START" \
    -i "$FRAME_DIR/frame_%04d.png" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart \
    "$VIDEO_PATH"

if [ "${C2W_KEEP_FRAMES:-0}" != "1" ]; then
    FRAME=$FRAME_START
    while [ "$FRAME" -le "$FRAME_END" ]; do
        FILE=$(printf '%s/frame_%04d.png' "$FRAME_DIR" "$FRAME")
        rm -f -- "$FILE"
        FRAME=$((FRAME + 1))
    done
    rmdir "$FRAME_DIR" 2>/dev/null || true
fi

echo "[multi-gpu] Video complete: $VIDEO_PATH"
