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

repo_root=${WORLDBRIDGE_ROOT}
baseline_root="$repo_root/baselines"
source_root="$baseline_root/sources/HY-World-2.0/hyworld2/worldgen/third_party"
package_root="$baseline_root/table3_worldgen"
output_root="$package_root/runtime/recast_glibc231_clean2"
build_root="$(mktemp -d /tmp/worldgen-recast-build.XXXXXX)"
trap 'rm -rf "$build_root"' EXIT

cp "$source_root/navmesh/setup.py" \
  "$source_root/navmesh/full_recast_bindings.cpp" \
  "$source_root/navmesh/navmesh_builder.cpp" \
  "$source_root/navmesh/navmesh_builder.h" \
  "$build_root/"
mkdir -p "$output_root" "$build_root/objects"

export CC='/usr/bin/gcc -pthread'
export CXX="$package_root/runtime/cxx_glibc231.sh -pthread"
export LDSHARED='/usr/bin/gcc -pthread -shared'
export LDCXXSHARED="$package_root/runtime/cxx_glibc231.sh -pthread -shared"
export LDFLAGS=''
export RECAST_PATH="$source_root/recastnavigation"

cd "$build_root"
"$baseline_root/envs/hyworld2/bin/python" setup.py build_ext \
  --build-lib "$output_root" \
  --build-temp "$build_root/objects"

PYTHONPATH="$output_root" "$baseline_root/environments/worldgen/bin/python" -c \
  'import recast; print(recast.__file__); print(recast.RecastNavMesh().get_version())'
