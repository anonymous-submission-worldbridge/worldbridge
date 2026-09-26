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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_pharmacy5"
BLENDER=${BLENDER_BIN}
mkdir -p "$OUT/renders" "$OUT/references"
cd "$ROOT"
"$BLENDER" -b --python "$ROOT/scripts/generate_urban_v3_pharmacy.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_pharmacy5.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/quality_report.json"
test -s "$OUT/SUCCESS"
for view in \
  01_row_daylight_overview.png \
  02_row_oblique_wide.png \
  03_cvs_reference_close.png \
  04_cvs_portico_detail.png \
  05_well_reference_close.png \
  06_well_signage_detail.png \
  07_cvs_interior_full.png \
  08_well_interior_full.png \
  09_well_pharmacy_counter.png \
  10_inventory_support_detail.png \
  11_well_pickup_kiosk_close.png
do
  test -s "$OUT/renders/$view"
done
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf8")); assert d["all_checks_passed"] and d["pipeline_connected"] and len(d["render_views"])==11 and all(d["revision_requirements"].values()) and d["entrance_clearance_audit"]["passed"] and d["floor_finish_audit"]["passed"] and d["storefront_continuity_audit"]["passed"] and d["public_realm_cleanup_audit"]["passed"] and d["counter_kiosk_detail_audit"]["passed"] and d["physical_support_audit"]["passed"] and d["package_attachment_audit"]["passed"] and d["signage_clearance_audit"]["passed"]' "$OUT/manifest.json"
