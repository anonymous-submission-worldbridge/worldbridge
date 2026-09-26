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

# Non-destructive full-13 dynamic build + resume-safe frame render + MP4 encode.
# Existing static generation and static render entrypoints are not modified.

set -eu

ROOT="${WORLDBRIDGE_ROOT}"
OUT=${C2W_FULL13_DYNAMIC_OUT:-"$ROOT/infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic"}
BLEND="$OUT/urban_v1_full_13_dynamic.blend"
FRAMES="$OUT/frames"
VIDEO="$OUT/urban_v1_full_13_dynamic.mp4"
LOG="$OUT/render.log"
BLENDER_COMMAND=${BLENDER_BIN:-blender}
RESOLUTION_X=${C2W_DYNAMIC_RESOLUTION_X:-1280}
RESOLUTION_Y=${C2W_DYNAMIC_RESOLUTION_Y:-720}
SAMPLES=${C2W_DYNAMIC_SAMPLES:-32}
TREE_MODE=${C2W_DYNAMIC_TREE_MODE:-none}
HYBRID_WIND_TAIL=${C2W_DYNAMIC_HYBRID_WIND_TAIL:-1}

mkdir -p "$OUT" "$FRAMES"

if [ "${C2W_DYNAMIC_REBUILD:-0}" = "1" ] || [ ! -s "$BLEND" ]; then
    "$BLENDER_COMMAND" --background --factory-startup \
        --python "$ROOT/scripts/build_urban_v1_full_13_dynamic.py" -- \
        --output-dir "$OUT" 2>&1 | tee "$OUT/build.log"
fi

TIMELINE=$(python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); t=d["timeline"]; print(t["frame_start"], t["frame_end"], t["fps"])' "$OUT/dynamic_manifest.json")
set -- $TIMELINE
FRAME_START=$1
FRAME_END=$2
FPS=$3

if [ "$HYBRID_WIND_TAIL" = "1" ]; then
    # The final quarter uses the already certified 1080p full-13 lake raster.
    # This retains the exact 11--30M-vertex tree appearance without asking
    # Blender 5.1 to place every species in one unsupported Vulkan buffer.
    BLENDER_FRAME_END=$((FRAME_START + 3 * (FRAME_END - FRAME_START + 1) / 4 - 1))
else
    BLENDER_FRAME_END=$FRAME_END
fi

"$BLENDER_COMMAND" --background --disable-depsgraph-on-file-load "$BLEND" \
    --python "$ROOT/scripts/render_urban_v1_full_13_dynamic.py" -- \
    --output-dir "$FRAMES" \
    --frame-start "$FRAME_START" --frame-end "$BLENDER_FRAME_END" \
    --resolution-x "$RESOLUTION_X" --resolution-y "$RESOLUTION_Y" \
    --samples "$SAMPLES" --tree-mode "$TREE_MODE" 2>&1 | tee "$LOG"

if [ "$HYBRID_WIND_TAIL" = "1" ]; then
    python "$ROOT/scripts/render_urban_v1_full_13_dynamic_wind_tail.py" \
        --output-dir "$FRAMES" \
        --frame-start $((BLENDER_FRAME_END + 1)) --frame-end "$FRAME_END" \
        --width "$RESOLUTION_X" --height "$RESOLUTION_Y"
fi

FRAME=$FRAME_START
while [ "$FRAME" -le "$FRAME_END" ]; do
    FILE=$(printf '%s/frame_%04d.png' "$FRAMES" "$FRAME")
    if [ ! -s "$FILE" ]; then
        echo "Error: missing rendered frame: $FILE"
        exit 1
    fi
    FRAME=$((FRAME + 1))
done

ffmpeg -y -framerate "$FPS" -start_number "$FRAME_START" \
    -i "$FRAMES/frame_%04d.png" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart \
    "$VIDEO"

"$BLENDER_COMMAND" --background --disable-depsgraph-on-file-load "$BLEND" \
    --python "$ROOT/scripts/audit_urban_v1_full_13_dynamic.py" -- \
    --output-dir "$OUT"

echo "[full13-dynamic] video=$VIDEO"
