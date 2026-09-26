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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_fire7"
BLENDER=${BLENDER_BIN:-${BLENDER_BIN}}

mkdir -p "$OUT/renders" "$OUT/references"
cd "$ROOT"
"$BLENDER" -b --python-exit-code 1 --python "$ROOT/scripts/generate_urban_v3_fire.py" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_fire7.blend"
test -s "$OUT/manifest.json"
test -s "$OUT/quality_report.json"
test -s "$OUT/SUCCESS"
for view in \
  01_full_precinct_front_far.png \
  02_full_precinct_southwest_aerial.png \
  03_full_precinct_southeast_aerial.png \
  04_civic_headquarters_front_near.png \
  05_industrial_annex_front_near.png \
  06_reverse_engineered_urban_pumper_close.png \
  07_reverse_engineered_aerial_platform_front_close.png \
  08_reverse_engineered_aerial_ladder_mechanics_close.png \
  09_closed_rolling_shutter_detail.png \
  10_open_apparatus_bay_interior.png
do
  test -s "$OUT/renders/$view"
done
test -s "$OUT/references/fire_truck_mesh_sources/model_49268/Firefighting.obj"
test -s "$OUT/references/fire_truck_mesh_sources/model_49268/fire_engine_49268.rar"
test -s "$OUT/references/fire_truck_mesh_sources/model_29256/Cadnav.com_B0711106.max"
test -s "$OUT/references/fire_truck_mesh_sources/model_28408/Cadnav.com_B0603027.max"
test -s "$OUT/references/fire_truck_mesh_sources/model_46403/Firetruck_US.max"
test -s "$OUT/references/fire_truck_reverse_engineering.json"
test -s "$OUT/references/fire_truck_reverse_engineering_suite.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf8")); s=d["fire_truck_reverse_engineering_suite"]; assert d["all_checks_passed"] and d["pipeline_connected"] and len(d["truck_variants"])==3 and d["scene_truck_instances"]==4 and d["scene_ambulance_instances"]==0 and len(d["station_variants"])==2 and len(d["render_views"])==10 and d["downloaded_reference_mesh_inputs"]==4 and d["downloaded_meshes_used_as_render_geometry"]==0 and s["source_count"]==4 and s["total_published_vertices"]>=500000 and all(v["passed"] for v in d["render_diagnostics"].values())' "$OUT/manifest.json"
