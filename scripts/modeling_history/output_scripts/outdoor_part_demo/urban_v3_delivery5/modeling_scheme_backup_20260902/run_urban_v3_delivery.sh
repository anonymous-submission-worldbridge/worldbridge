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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_delivery5"
REFERENCE_SOURCE="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_delivery4/references"
BLENDER=${BLENDER_BIN}
mkdir -p "$OUT/renders" "$OUT/references"
cp -a "$REFERENCE_SOURCE/." "$OUT/references/"
cd "$ROOT"
C2W_DELIVERY_OUTPUT_ID=urban_v3_delivery5 \
  "$BLENDER" -b --python "$ROOT/scripts/generate_urban_v3_delivery.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_delivery5.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/quality_report.json"
test -s "$OUT/SUCCESS"
for view in \
  01_delivery_row_daylight_far.png \
  02_delivery_row_oblique_far.png \
  03_food_locker_reference_close.png \
  04_food_locker_hardware_close.png \
  05_parcel_locker_reference_close.png \
  06_parcel_terminal_close.png \
  07_station_glazed_exterior_close.png \
  08_station_open_entry_interior.png \
  09_station_counter_workstation.png \
  10_station_rack_inventory.png
do
  test -s "$OUT/renders/$view"
done
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf8")); r=d["requested_refinement_audit"]; assert d["all_checks_passed"] and d["pipeline_connected"] and d["output_revision_id"]=="urban_v3_delivery5" and len(d["render_views"])==10 and d["parcel_support_audit"]["passed"] and r["passed"] and r["counts"]["food_white_powdercoat_doors"]==59 and r["counts"]["food_clear_tempered_windows"]==59 and r["counts"]["food_glass_printed_numbers"]==59 and r["counts"]["food_glass_number_contrast_keylines"]==59 and r["counts"]["food_glass_vertical_bars"]==0 and all(d["checks"].values())' "$OUT/manifest.json"
