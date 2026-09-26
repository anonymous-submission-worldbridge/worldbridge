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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_delivery6"
REFERENCE_SOURCE="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_delivery5/references"
METHOD_REFERENCE="$ROOT/.reference_cache/2505.10755.pdf"
BLENDER=${BLENDER_BIN}
mkdir -p "$OUT/renders" "$OUT/references"
cp -a "$REFERENCE_SOURCE/." "$OUT/references/"
cp -a "$METHOD_REFERENCE" "$OUT/references/infinigen_articulated_2505.10755.pdf"
cd "$ROOT"
C2W_DELIVERY_OUTPUT_ID=urban_v3_delivery6 \
  "$BLENDER" -b --python-exit-code 1 --python "$ROOT/scripts/generate_urban_v3_delivery.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_delivery6.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/quality_report.json"
test -s "$OUT/articulation_manifest.json"
test -s "$OUT/native_kinematic_blueprints.json"
test -s "$OUT/hinge_clearance_sweep_report.json"
test -s "$OUT/SUCCESS"
for view in \
  01_delivery_row_daylight_closed_panorama.png \
  02_delivery_row_daylight_open_panorama.png \
  03_delivery_row_open_oblique.png \
  04_food_locker_closed_front.png \
  05_food_locker_open_front.png \
  06_food_hinge_closed_closeup.png \
  07_food_hinge_open_closeup.png \
  08_parcel_locker_closed_front.png \
  09_parcel_locker_open_front.png \
  10_parcel_hinge_closed_closeup.png \
  11_parcel_hinge_open_closeup.png \
  12_articulated_lockers_open_oblique_close.png
do
  test -s "$OUT/renders/$view"
done
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf8")); r=d["requested_refinement_audit"]; a=d["articulation_audit"]; assert d["all_checks_passed"] and d["pipeline_connected"] and d["output_revision_id"]=="urban_v3_delivery6" and len(d["render_views"])==12 and d["parcel_support_audit"]["passed"] and r["passed"] and a["passed"] and a["counts"]["food_revolute_links"]==59 and a["counts"]["parcel_revolute_links"]==56 and a["counts"]["hinge_constraints"]==115 and d["native_kinematic_blueprints"]["compiled_revolute_joint_count"]==115 and d["hinge_clearance_sweep"]["evaluated_joint_poses"]==1495 and d["render_pose_audit"]["passed"] and r["counts"]["food_white_powdercoat_doors"]==59 and r["counts"]["food_clear_tempered_windows"]==59 and r["counts"]["food_glass_printed_numbers"]==59 and r["counts"]["food_glass_number_contrast_keylines"]==59 and r["counts"]["food_glass_vertical_bars"]==0 and all(d["checks"].values())' "$OUT/manifest.json"
"$BLENDER" -b "$OUT/urban_v3_delivery6.blend" --python-exit-code 1 \
  --python "$ROOT/scripts/verify_urban_v3_delivery_articulation.py" -- \
  "$OUT/post_save_blend_audit.json"
test -s "$OUT/post_save_blend_audit.json"
