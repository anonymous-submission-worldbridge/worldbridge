#!/bin/sh

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
set -u

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_layer="${1:?expected full-12 projection layer key}"
c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
c2w_output="$c2w_city/renders/zdepth_projection_layers"
c2w_runtime="$c2w_city/render_runtime/projection/$c2w_layer"
c2w_log="$c2w_city/projection_${c2w_layer}.log"
c2w_status="$c2w_city/projection_${c2w_layer}.status"
c2w_shared_cache="$c2w_city/render_runtime/shared_material_cache"
c2w_gpu_backend="${C2W_FULL12_GPU_BACKEND:-vulkan}"

case "$c2w_gpu_backend" in
    opengl|vulkan) ;;
    *)
        printf 'FAIL %s layer=%s reason=invalid_gpu_backend value=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_gpu_backend" > "$c2w_status"
        exit 95
        ;;
esac

mkdir -p "$c2w_runtime/tmp" "$c2w_shared_cache" "$c2w_output"
: > "$c2w_log"
printf 'RUNNING %s layer=%s resolution=2048x2048\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"

if [ ! -s "$c2w_pack" ]; then
    printf 'FAIL %s layer=%s reason=missing_pack\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
    exit 97
fi

cd "$c2w_root" || exit 98
TMPDIR="$c2w_runtime/tmp" \
XDG_CACHE_HOME="$c2w_shared_cache" \
C2W_FULL12_RENDER_ENGINE="WORKBENCH" \
C2W_FULL12_WORKBENCH_AA="8" \
C2W_FULL12_RENDER_RESOLUTION="2048x2048" \
C2W_FULL12_LAYER_ROOT="$c2w_output" \
/usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
    --disable-depsgraph-on-file-load -b "$c2w_pack" \
    --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
    -- "$c2w_layer" city_top_down_coverage >> "$c2w_log" 2>&1
c2w_code=$?

if [ "$c2w_code" -eq 0 ]; then
    printf 'PASS %s layer=%s exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_code" > "$c2w_status"
else
    printf 'FAIL %s layer=%s exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_code" > "$c2w_status"
fi
exit "$c2w_code"
