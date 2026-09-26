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

cd ${WORLDBRIDGE_EXTERNAL}/infinigen

echo "[check] GPU visibility"
nvidia-smi

export MPLCONFIGDIR=/tmp/infinigen-matplotlib-cache
export INFINIGEN_DISABLE_KITCHEN_ISLAND=1
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

SEED="country-villa-showcase-001"
FLOOR_PLAN="${WORLDBRIDGE_ROOT}/configs/modeling/indoor_outdoor_villa_demo/country_villa_floor_plan.json"
COARSE_OUT="outputs/indoor_outdoor_villa_demo/coarse_gpu_limited"
FRAMES_OUT="outputs/indoor_outdoor_villa_demo/frames_gpu_limited"

COMMON_CONFIGS=(
  plain.gin
  real_geometry.gin
  high_quality_terrain.gin
)

COMMON_OVERRIDES=(
  "Solver.floor_plan='${FLOOR_PLAN}'"
  "compose_indoors.terrain_enabled=True"
  "compose_indoors.nature_backdrop_enabled=True"
  "compose_indoors.grass_chance=1.0"
  "compose_indoors.rocks_chance=1.0"
  "compose_indoors.fancy_clouds_chance=1.0"
  "compose_indoors.lights_off_chance=0.0"
  "compose_indoors.invisible_room_ceilings_enabled=False"
  "compose_indoors.hide_other_rooms_enabled=False"
  "compose_indoors.overhead_cam_enabled=False"
  "compose_indoors.floating_objs_enabled=False"
  "compose_indoors.solve_steps_large=80"
  "compose_indoors.solve_steps_medium=45"
  "compose_indoors.solve_steps_small=15"
)

echo "[coarse] generating indoor/outdoor villa scene"
conda run --no-capture-output -n infinigen python -m infinigen_examples.generate_indoors \
  --seed "${SEED}" \
  --task coarse \
  --output_folder "${COARSE_OUT}" \
  -g "${COMMON_CONFIGS[@]}" \
  -p "${COMMON_OVERRIDES[@]}"

echo "[render] rendering RGB frames with GPU-visible Blender/Cycles"
conda run --no-capture-output -n infinigen python -m infinigen_examples.generate_indoors \
  --seed "${SEED}" \
  --task render \
  --input_folder "${COARSE_OUT}" \
  --output_folder "${FRAMES_OUT}" \
  -g "${COMMON_CONFIGS[@]}" \
  -p \
    "configure_render_cycles.num_samples=512" \
    "configure_render_cycles.min_samples=32" \
    "configure_render_cycles.adaptive_threshold=0.02" \
    "configure_render_cycles.denoise=True"

echo "[done]"
echo "Coarse scene: ${COARSE_OUT}/scene.blend"
echo "Rendered frames: ${FRAMES_OUT}"
