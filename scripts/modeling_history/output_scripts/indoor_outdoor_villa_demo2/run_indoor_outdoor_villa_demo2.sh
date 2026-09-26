#!/usr/bin/env bash

_wb_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ ! -d "$_wb_dir/worldbridge" ] && [ "$_wb_dir" != / ]; do
    _wb_dir=$(dirname -- "$_wb_dir")
done
WORLDBRIDGE_ROOT=${WORLDBRIDGE_ROOT:-$_wb_dir}
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFINIGEN_ROOT="${WORLDBRIDGE_ROOT}/infinigen"
cd "${INFINIGEN_ROOT}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/infinigen-matplotlib-cache}"
export INFINIGEN_DISABLE_KITCHEN_ISLAND="${INFINIGEN_DISABLE_KITCHEN_ISLAND:-1}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

echo "[check] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi
else
  echo "[warn] nvidia-smi not found; Blender/Cycles will still try visible CUDA devices."
fi

SEED="${SEED:-indoor-outdoor-villa-demo2-001}"
FLOOR_PLAN="${WORLDBRIDGE_ROOT}/configs/modeling/indoor_outdoor_villa_demo2/connection_floor_plan.json"
COARSE_OUT="outputs/indoor_outdoor_villa_demo2/coarse"
CONNECTED_OUT="outputs/indoor_outdoor_villa_demo2/connected"
FRAMES_OUT="outputs/indoor_outdoor_villa_demo2/frames"
EXPORT_OUT="outputs/indoor_outdoor_villa_demo2/export_usdc"
REPORT_OUT="outputs/indoor_outdoor_villa_demo2/reports/connection_report.json"

COMMON_CONFIGS=(
  plain.gin
  real_geometry.gin
  high_quality_terrain.gin
)

COMMON_OVERRIDES=(
  "Solver.floor_plan='${FLOOR_PLAN}'"
  "Terrain.device='cuda'"
  "compose_indoors.terrain_enabled=True"
  "compose_indoors.nature_backdrop_enabled=True"
  "compose_indoors.grass_chance=0.05"
  "compose_indoors.rocks_chance=0.0"
  "compose_indoors.fancy_clouds_chance=0.25"
  "compose_indoors.lights_off_chance=0.0"
  "compose_indoors.invisible_room_ceilings_enabled=False"
  "compose_indoors.hide_other_rooms_enabled=False"
  "compose_indoors.overhead_cam_enabled=False"
  "compose_indoors.floating_objs_enabled=False"
  "compose_indoors.solve_steps_large=100"
  "compose_indoors.solve_steps_medium=55"
  "compose_indoors.solve_steps_small=15"
)

echo "[coarse] complete indoor house with one explicit front access door"
conda run --no-capture-output -n infinigen python -m infinigen_examples.generate_indoors \
  --seed "${SEED}" \
  --task coarse \
  --output_folder "${COARSE_OUT}" \
  -g "${COMMON_CONFIGS[@]}" \
  -p "${COMMON_OVERRIDES[@]}"

echo "[patch] adding urban sidewalk, curb ramp, zebra crossing, road, trees, pedestrians, vehicles"
conda run --no-capture-output -n infinigen python \
  "${WORLDBRIDGE_ROOT}/scripts/modeling_history/indoor_scenes/indoor_outdoor_villa_demo2/scripts/patch_connection.py" \
  --input "${COARSE_OUT}/scene.blend" \
  --output "${CONNECTED_OUT}/scene.blend" \
  --report "${REPORT_OUT}"

echo "[metadata] copying render metadata from coarse scene to patched scene"
for name in MaskTag.json solve_state.json version.txt polycounts.txt pipeline_coarse.csv; do
  if [ -f "${COARSE_OUT}/${name}" ]; then
    cp "${COARSE_OUT}/${name}" "${CONNECTED_OUT}/${name}"
  fi
done
if [ -e "${CONNECTED_OUT}/assets" ] || [ -L "${CONNECTED_OUT}/assets" ]; then
  rm -rf "${CONNECTED_OUT}/assets"
fi
ln -s "../coarse/assets" "${CONNECTED_OUT}/assets"

echo "[render] rendering patched connection-aware scene"
conda run --no-capture-output -n infinigen python -m infinigen_examples.generate_indoors \
  --seed "${SEED}" \
  --task render \
  --input_folder "${CONNECTED_OUT}" \
  --output_folder "${FRAMES_OUT}" \
  -g "${COMMON_CONFIGS[@]}" \
  -p \
    "configure_render_cycles.num_samples=256" \
    "configure_render_cycles.min_samples=32" \
    "configure_render_cycles.adaptive_threshold=0.02" \
    "configure_render_cycles.denoise=True"

echo "[export] exporting patched scene for simulator import"
conda run --no-capture-output -n infinigen python -m infinigen.tools.export \
  --input_folder "${CONNECTED_OUT}" \
  --output_folder "${EXPORT_OUT}" \
  -f usdc \
  -r 512 \
  --omniverse

echo "[done]"
echo "Coarse scene: ${COARSE_OUT}/scene.blend"
echo "Patched scene: ${CONNECTED_OUT}/scene.blend"
echo "Connection report: ${REPORT_OUT}"
echo "Rendered frames: ${FRAMES_OUT}"
echo "USDC export: ${EXPORT_OUT}"
