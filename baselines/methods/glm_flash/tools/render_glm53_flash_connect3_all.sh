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

output=${WORLDBRIDGE_ROOT}/baselines/annotations/glm53_flash/connect3
renderer=${WORLDBRIDGE_ROOT}/baselines/methods/glm_flash/tools/render_glm_flash_connect3.py
scenes=(
  suburban_family_room
  duplex_home_office_lounge
  neighborhood_pharmacy
  local_grocery_market
  casual_family_restaurant
  hardware_home_store
)

for scene_id in "${scenes[@]}"; do
  log="$output/$scene_id/logs/render_final.log"
  mkdir -p "$(dirname "$log")"
  echo "GLM53_CONNECT3_FINAL_START scene=$scene_id"
  if ! ${BLENDER_BIN} --background --factory-startup \
      --python "$renderer" -- \
      --output "$output" \
      --scene-id "$scene_id" \
      --video-frames 48 \
      --force >"$log" 2>&1; then
    tail -n 80 "$log"
    exit 1
  fi
  echo "GLM53_CONNECT3_FINAL_COMPLETE scene=$scene_id"
done
