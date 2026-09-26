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
OUT="$ROOT/infinigen/outputs/outdoor_part_demo/urban_v3_all45_09"
BLENDER=${BLENDER_BIN}
export PYTHONPATH="${WORLDBRIDGE_SITE_PACKAGES}:$ROOT/infinigen"
export MPLCONFIGDIR=/tmp/all45_09_mpl
export XDG_CACHE_HOME=/tmp/all45_09_cache
mkdir -p "$OUT/indoor_sources/showcase" "$OUT/indoor_sources/companion_a" "$OUT/indoor_sources/companion_b" "$OUT/renders"
cd "$ROOT/infinigen"

run_indoor() {
  local label="$1"
  local folder="$2"
  local seed="$3"
  local profile="$4"
  local success_marker="$folder/all45_09_indoor_success.json"
  local force_rebuild=0
  if [[ "$label" == "showcase" && "${C2W_REBUILD_SHOWCASE:-0}" == "1" ]]; then
    force_rebuild=1
  fi
  if [[ "${C2W_REUSE_INDOOR:-0}" == "1" && "$force_rebuild" == "0" && -s "$folder/scene.blend" && -s "$success_marker" ]]; then
    echo "[all45_09] Reusing verified native Indoor solve for $label: $folder/scene.blend"
    return
  fi
  local started_at
  started_at="$(date +%s)"
  echo "[all45_09] Running genuine Infinigen Indoor for $label with profile=$profile..."
  INFINIGEN_INDOOR_OUTPUT="$folder" \
    INFINIGEN_INDOOR_SEED="$seed" \
    INFINIGEN_INDOOR_SOLVE_CONFIG="$profile" \
    INFINIGEN_INDOOR_ROLE="$label" \
    INFINIGEN_DISABLE_KITCHEN_ISLAND=1 \
    ALL41_HOUSE_VARIANT=large \
    "$BLENDER" -b --python-exit-code 1 --python-use-system-env --python "$ROOT/scripts/run_generate_indoors_all41.py" \
    2>&1 | tee "$folder/indoor_generation.log"
  if [[ ! -s "$folder/scene.blend" || ! -s "$success_marker" ]]; then
    echo "[all45_09] ERROR: $label did not produce both scene.blend and a success marker" >&2
    return 1
  fi
  if (( $(stat -c %Y "$folder/scene.blend") < started_at || $(stat -c %Y "$success_marker") < started_at )); then
    echo "[all45_09] ERROR: $label left stale Indoor outputs after the requested rebuild" >&2
    return 1
  fi
}

run_indoor showcase "$OUT/indoor_sources/showcase" all4509_showcase residential_showcase_09
run_indoor companion_b "$OUT/indoor_sources/companion_b" all4509_companion_b residential_companion_09

echo '[all45_09] Generating the revised native-scale residential district from the production generator...'
EXTRA_ARGS=()
if [[ -n "${C2W_RESIDENTIAL_CONFIG:-}" ]]; then
  EXTRA_ARGS=(-- --config "$C2W_RESIDENTIAL_CONFIG")
fi
"$BLENDER" -b --python-exit-code 1 --python-use-system-env --python "$ROOT/scripts/generate_urban_v3_all45_03.py" "${EXTRA_ARGS[@]}" 2>&1 | tee "$OUT/generation.log"
test -s "$OUT/urban_v3_all45_09.blend"
test -s "$OUT/generation_config.json"
test -s "$OUT/generation_audit.json"
test -s "$OUT/renders/01_spaced_district_overview.png"

echo '[all45_09] Rendering expanded showcase views and concise companion views from verified native Infinigen Indoor solves...'
"$BLENDER" -b "$OUT/urban_v3_all45_09.blend" --python-exit-code 1 --python "$ROOT/scripts/render_lowrise_interiors_all45_08.py" 2>&1 | tee "$OUT/interior_render.log"
test -s "$OUT/lowrise_interior_render_audit.json"
test -s "$OUT/renders/07_showcase_complete_floorplan.png"
test -s "$OUT/renders/10_showcase_dollhouse_rear.png"
test -s "$OUT/renders/17_showcase_bathroom.png"
test -s "$OUT/renders/18_companion_a_complete_floorplan.png"
test -s "$OUT/renders/22_companion_b_complete_floorplan.png"
test -s "$OUT/renders/25_companion_b_living_room.png"
