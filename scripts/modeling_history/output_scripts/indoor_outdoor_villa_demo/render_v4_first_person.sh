#!/usr/bin/env bash

_wb_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ ! -d "$_wb_dir/worldbridge" ] && [ "$_wb_dir" != / ]; do
    _wb_dir=$(dirname -- "$_wb_dir")
done
WORLDBRIDGE_ROOT=${WORLDBRIDGE_ROOT:-$_wb_dir}
set -euo pipefail

SCENE="${SCENE:-outputs/indoor_outdoor_villa_demo/coarse_gpu_limited/scene.blend}"
ROUTE="${ROUTE:-${WORLDBRIDGE_ROOT}/configs/modeling/indoor_outdoor_villa_demo/villa_first_person_route_v4_human_forward.json}"
OUTPUT="${OUTPUT:-outputs/indoor_outdoor_villa_demo/videos/first_person_walkthrough_v4.mp4}"
BLENDER_BIN="${BLENDER_BIN:-blender}"

FRAMES="${FRAMES:-1440}"
FPS="${FPS:-24}"
SAMPLES="${SAMPLES:-64}"
RES_X="${RES_X:-1920}"
RES_Y="${RES_Y:-1080}"
ENGINE="${ENGINE:-CYCLES}"

"${BLENDER_BIN}" -b "${SCENE}" \
  --python infinigen/tools/visualization/render_first_person_walkthrough.py -- \
  --path-json "${ROUTE}" \
  --output "${OUTPUT}" \
  --frames "${FRAMES}" \
  --fps "${FPS}" \
  --samples "${SAMPLES}" \
  --resolution-x "${RES_X}" \
  --resolution-y "${RES_Y}" \
  --engine "${ENGINE}"

echo "[done] ${OUTPUT}"
