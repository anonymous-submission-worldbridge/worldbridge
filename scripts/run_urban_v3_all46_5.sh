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

PROJECT_ROOT=${WORLDBRIDGE_ROOT}
OUTPUT_DIR="$PROJECT_ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_all46_5"
BLENDER_EXECUTABLE=${BLENDER_BIN:-${BLENDER_BIN}}

mkdir -p "$OUTPUT_DIR/renders"
cd "$PROJECT_ROOT"
"$BLENDER_EXECUTABLE" -b --python "$PROJECT_ROOT/scripts/generate_urban_v3_all46_2.py" 2>&1 | tee "$OUTPUT_DIR/generation.log"

test -s "$OUTPUT_DIR/urban_v3_all46_5.blend"
test -s "$OUTPUT_DIR/manifest.json"
test -s "$OUTPUT_DIR/SUCCESS"
