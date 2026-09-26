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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_gass4"
BLENDER=${BLENDER_BIN:-${BLENDER_BIN}}

mkdir -p "$OUT/renders" "$OUT/references"
cd "$ROOT"
"$BLENDER" -b --python "$ROOT/scripts/generate_urban_v3_gass.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_gass4.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/quality_report.json"
test -s "$OUT/SUCCESS"
for view in \
  01_three_station_row_front_far.png \
  02_three_station_row_oblique_far.png \
  03_three_station_row_rear_aerial_far.png \
  04_nobile_wave_reference_close.png \
  05_nobile_dispenser_pylon_detail.png \
  06_blue_orange_reference_close.png \
  07_blue_orange_dispenser_detail.png \
  08_red_yellow_reference_close.png \
  09_red_yellow_pylon_pump_detail.png \
  10_blue_storefront_interior_close.png \
  11_nobile_storefront_door_close.png \
  12_red_yellow_storefront_door_close.png
do
  test -s "$OUT/renders/$view"
done
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf8")); assert d["all_checks_passed"] and d["pipeline_connected"] and d["station_count"]==3 and len(d["render_views"])==12 and all(d["dense_geometry_checks"].values()) and all(d["dispenser_assembly_checks"].values()) and all(d["interior_detail_checks"].values()) and all(d["structure_detail_checks"].values()) and all(d["manufactured_form_checks"].values()) and all(d["detailed_door_checks"].values()) and all(d["architectural_detail_checks"].values()) and d["scene_text_audit"]["passed"] and all(d["reference_specific_geometry_checks"].values()) and d["product_support_audit"]["passed"] and all(v["passed"] for v in d["render_diagnostics"].values())' "$OUT/manifest.json"
