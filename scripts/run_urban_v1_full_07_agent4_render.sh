#!/usr/bin/env bash

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
set -euo pipefail

# Render the two halves of the production agent4 deliverable on dedicated GPUs.
# This is only an orchestration wrapper: the connected generator entry remains
# generate_urban_v1_full_07.py and the full saved scene is always rendered.

ROOT=${WORLDBRIDGE_ROOT}
OUT="$ROOT/infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent4"
BLENDER=${BLENDER_BIN}
BLEND="$OUT/urban_v1_full_07_agent4.blend"
ENTRY="$ROOT/scripts/generate_urban_v1_full_07.py"

case "${1:-}" in
  gpu2)
    DEVICE=2
    JOB=stills_first
    INDICES=0,1,2,3,4,5,6,7
    REPORT=gpu2
    PIPELINE_ENV=(C2W_AGENT4_RENDER=1)
    EXPOSURE=0.0
    ;;
  gpu5)
    DEVICE=5
    JOB=stills_third
    INDICES=8,9,10,11,12,13,14,15
    REPORT=gpu5
    PIPELINE_ENV=(C2W_AGENT4_RENDER=1)
    EXPOSURE=0.0
    ;;
  gpu2_first)
    DEVICE=2
    JOB=stills_first
    INDICES=10,11,12
    REPORT=gpu2
    PIPELINE_ENV=(C2W_AGENT4_CAMERA_REPAIR=1 C2W_AGENT4_RENDER_AFTER_REPAIR=1)
    EXPOSURE=-0.7
    ;;
  *)
    echo "usage: $0 {gpu2|gpu5|gpu2_first}" >&2
    exit 2
    ;;
esac

cd "$ROOT"
exec env \
  CUDA_VISIBLE_DEVICES="$DEVICE" \
  "${PIPELINE_ENV[@]}" \
  C2W_OUTPUT_REVISION=urban_v1_full_07_agent4 \
  C2W_AGENT4_RENDER_ENGINE=cycles \
  C2W_AGENT4_EXPOSURE="$EXPOSURE" \
  C2W_AGENT4_RENDER_JOB="$JOB" \
  C2W_AGENT4_STILL_INDICES="$INDICES" \
  C2W_AGENT4_STILL_WIDTH=960 \
  C2W_AGENT4_STILL_HEIGHT=540 \
  C2W_AGENT4_STILL_SAMPLES=4 \
  C2W_AGENT4_VIDEO_WIDTH=640 \
  C2W_AGENT4_VIDEO_HEIGHT=360 \
  C2W_AGENT4_VIDEO_SAMPLES=2 \
  C2W_AGENT4_VIDEO_FRAME_STEP=6 \
  C2W_AGENT4_VIDEO_FPS=5 \
  C2W_AGENT4_RENDER_REPORT="$REPORT" \
  "$BLENDER" -b "$BLEND" --python-exit-code 1 --python "$ENTRY" \
  >"$OUT/render_console_${REPORT}.log" 2>&1
