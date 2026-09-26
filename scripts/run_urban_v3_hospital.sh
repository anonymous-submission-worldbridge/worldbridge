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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_hospital3"
BLENDER=${BLENDER_BIN:-${BLENDER_BIN}}

mkdir -p "$OUT/renders" "$ROOT/.qa_tmp/urban_v3_hospital3/xdg_config"
export XDG_CONFIG_HOME="$ROOT/.qa_tmp/urban_v3_hospital3/xdg_config"
cd "$ROOT"

"$BLENDER" -b --python-exit-code 1 --python "$ROOT/scripts/generate_urban_v3_hospital.py" 2>&1 | tee "$OUT/generation.log"

test -s "$OUT/urban_v3_hospital3.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/SUCCESS"
test "$(find "$OUT/renders" -maxdepth 1 -name '*.png' -size +150k | wc -l)" -eq 10
python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); assert d["all_checks_passed"] is True; assert len(d["render_diagnostics"]) == 10' "$OUT/manifest.json"
