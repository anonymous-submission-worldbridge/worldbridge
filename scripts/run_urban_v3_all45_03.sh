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

ROOT=${WORLDBRIDGE_ROOT}
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_all45_03"
BLENDER=${BLENDER_BIN}
export PYTHONPATH="${WORLDBRIDGE_SITE_PACKAGES}:$ROOT/infinigen"
export MPLCONFIGDIR=/tmp/all45_03_mpl
export XDG_CACHE_HOME=/tmp/all45_03_cache
mkdir -p "$OUT/indoor_sources/house_a" "$OUT/indoor_sources/house_b" "$OUT/renders"
cd "$ROOT/infinigen"

echo '[LowRise-01] Indoor enabled: True; running native Infinigen Indoor...'
INFINIGEN_INDOOR_OUTPUT="$OUT/indoor_sources/house_a" INFINIGEN_INDOOR_SEED=all4503_house_a INFINIGEN_INDOOR_SOLVE_CONFIG=residential_fast ALL41_HOUSE_VARIANT=large \
  "$BLENDER" -b --python-use-system-env --python "$ROOT/scripts/run_generate_indoors_all41.py"
test -s "$OUT/indoor_sources/house_a/scene.blend"

echo '[LowRise-02] Indoor enabled: True; running native Infinigen Indoor...'
INFINIGEN_INDOOR_OUTPUT="$OUT/indoor_sources/house_b" INFINIGEN_INDOOR_SEED=all4503_house_b INFINIGEN_INDOOR_SOLVE_CONFIG=residential_fast ALL41_HOUSE_VARIANT=large \
  "$BLENDER" -b --python-use-system-env --python "$ROOT/scripts/run_generate_indoors_all41.py"
test -s "$OUT/indoor_sources/house_b/scene.blend"

echo '[Residential] Native Indoor solves complete; generating exterior and landscape from a clean scene...'
"$BLENDER" -b --python-use-system-env --python "$ROOT/scripts/generate_urban_v3_all45_03.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_all45_03.blend"
