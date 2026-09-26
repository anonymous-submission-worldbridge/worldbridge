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

set -eu

if [ "$#" -lt 2 ]; then
    echo "Usage: sh scripts/render_dynamic_cycles_allgpus.sh DYNAMIC.blend OUTPUT.mp4"
    exit 1
fi

ROOT="${WORLDBRIDGE_ROOT}"
BLEND_PATH=$1
VIDEO_PATH=$2
REPORT_PATH=${BLEND_PATH%.blend}.dynamics.json
VIDEO_DIR=$(dirname -- "$VIDEO_PATH")
VIDEO_FILE=$(basename -- "$VIDEO_PATH")
VIDEO_STEM=${VIDEO_FILE%.*}
FRAME_DIR="$VIDEO_DIR/${VIDEO_STEM}_frames"
LOG_PATH="$VIDEO_DIR/${VIDEO_STEM}_cycles_allgpus.log"
BLENDER_COMMAND=${BLENDER_BIN:-blender}
RESOLUTION_X=${C2W_RESOLUTION_X:-1280}
RESOLUTION_Y=${C2W_RESOLUTION_Y:-720}
SAMPLES=${C2W_CYCLES_SAMPLES:-8}
ADAPTIVE_THRESHOLD=${C2W_ADAPTIVE_THRESHOLD:-0.12}

mkdir -p "$FRAME_DIR" "$VIDEO_DIR"
TIMELINE=$(python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); t=d["timeline"]; print(t["frame_start"], t["frame_end"], t["fps"])' "$REPORT_PATH")
set -- $TIMELINE
FRAME_START=$1
FRAME_END=$2
FPS=$3

: >"$LOG_PATH"
MAX_ATTEMPTS=${C2W_RENDER_ATTEMPTS:-6}
CHUNK_SIZE=${C2W_RENDER_CHUNK_SIZE:-8}
CURRENT_START=$FRAME_START
while [ "$CURRENT_START" -le "$FRAME_END" ]; do
    while [ "$CURRENT_START" -le "$FRAME_END" ]; do
        FILE=$(printf '%s/frame_%04d.png' "$FRAME_DIR" "$CURRENT_START")
        [ ! -s "$FILE" ] && break
        CURRENT_START=$((CURRENT_START + 1))
    done
    [ "$CURRENT_START" -gt "$FRAME_END" ] && break

    CHUNK_END=$((CURRENT_START + CHUNK_SIZE - 1))
    [ "$CHUNK_END" -gt "$FRAME_END" ] && CHUNK_END=$FRAME_END
    ATTEMPT=1
    while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
        MESSAGE="[cycles-all-gpus] attempt=$ATTEMPT frames=$CURRENT_START..$CHUNK_END"
        echo "$MESSAGE"
        echo "$MESSAGE" >>"$LOG_PATH"
        # A lightweight factory-startup process initializes the shared NVIDIA
        # driver state.  On busy multi-user hosts this avoids Blender 5.1
        # intermittently seeing zero OptiX devices after loading a 6GB blend.
        if ! "$BLENDER_COMMAND" --background --factory-startup \
            --python "$ROOT/scripts/warmup_cycles_allgpus.py"; then
            echo "[cycles-all-gpus] OptiX warmup failed; retrying this chunk"
            ATTEMPT=$((ATTEMPT + 1))
            [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ] && sleep 15
            continue
        fi
        if "$BLENDER_COMMAND" --background "$BLEND_PATH" \
            --python "$ROOT/scripts/render_dynamic_cycles_allgpus.py" -- \
            --output-dir "$FRAME_DIR" \
            --frame-start "$CURRENT_START" --frame-end "$CHUNK_END" \
            --resolution-x "$RESOLUTION_X" --resolution-y "$RESOLUTION_Y" \
            --samples "$SAMPLES" --adaptive-threshold "$ADAPTIVE_THRESHOLD"; then
            :
        else
            echo "[cycles-all-gpus] Blender exited non-zero; preserving completed frames"
        fi

        NEXT_FRAME=$CURRENT_START
        while [ "$NEXT_FRAME" -le "$CHUNK_END" ]; do
            FILE=$(printf '%s/frame_%04d.png' "$FRAME_DIR" "$NEXT_FRAME")
            [ ! -s "$FILE" ] && break
            NEXT_FRAME=$((NEXT_FRAME + 1))
        done
        if [ "$NEXT_FRAME" -gt "$CHUNK_END" ]; then
            CURRENT_START=$((CHUNK_END + 1))
            break
        fi
        CURRENT_START=$NEXT_FRAME
        ATTEMPT=$((ATTEMPT + 1))
        [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ] && sleep 15
    done

    if [ "$CURRENT_START" -le "$CHUNK_END" ]; then
        echo "Error: failed to finish chunk through frame $CHUNK_END"
        exit 1
    fi
done

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

echo "[cycles-all-gpus] Video complete: $VIDEO_PATH"
