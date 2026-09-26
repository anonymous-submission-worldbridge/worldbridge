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

repo_root="${WORLDBRIDGE_ROOT}"
baseline_root="${repo_root}/baselines"
spatial_site="${baseline_root}/envs/spatialgen/lib/python3.10/site-packages"
source_root="${baseline_root}/vendor/SpatialGen/src/recons/Sparse-RaDeGS/submodules/diff-gaussian-rasterization"
target_root="${baseline_root}/work/spatialgen/table3/rebuilt_site"
task_tmp="${baseline_root}/work/spatialgen/table3/tmp"

mkdir -p "${target_root}" "${task_tmp}"
env \
  PYTHONPATH="${spatial_site}" \
  CUDA_HOME=/usr/local/cuda-12.4 \
  TORCH_CUDA_ARCH_LIST=8.6 \
  MAX_JOBS=4 \
  TMPDIR="${task_tmp}" \
  PATH=/usr/local/cuda-12.4/bin:/usr/bin:/bin \
  ${WORLDBRIDGE_PYTHON} -m pip install \
    --no-build-isolation --no-deps --target "${target_root}" "${source_root}"

sha256sum "${target_root}"/diff_gaussian_rasterization/_C*.so
