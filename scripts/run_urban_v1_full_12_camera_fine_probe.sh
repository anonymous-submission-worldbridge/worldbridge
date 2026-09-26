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
set -eu

# Second visual-review pass for the five camera specifications refined after
# inspecting their first exact target-layer rasters.  Like the main target
# probe, this updates authoritative layer EXRs through the production renderer.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_runtime="$c2w_city/render_runtime/camera_fine_probe"
c2w_log="$c2w_runtime/camera_fine_probe.log"
c2w_status="$c2w_runtime/camera_fine_probe.status"
c2w_cache="$c2w_runtime/cache"

mkdir -p "$c2w_runtime/tmp" "$c2w_cache"
: > "$c2w_log"
printf 'RUNNING %s camera_revision=full12_authored_asset_framing_v2 views=5\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

render_target() {
    c2w_layer="$1"
    c2w_view="$2"
    c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
    printf 'FULL12_CAMERA_FINE_BEGIN utc=%s layer=%s view=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_view" \
        >> "$c2w_log"
    /usr/bin/env \
        C2W_FULL12_RENDER_FORCE=1 \
        C2W_FULL12_RENDER_ENGINE=WORKBENCH \
        C2W_FULL12_WORKBENCH_AA=16 \
        TMPDIR="$c2w_runtime/tmp" \
        XDG_CACHE_HOME="$c2w_cache" \
        /usr/local/bin/blender --gpu-backend vulkan \
            --disable-depsgraph-on-file-load -b "$c2w_pack" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- "$c2w_layer" "$c2w_view" >> "$c2w_log" 2>&1
    printf 'FULL12_CAMERA_FINE_DONE utc=%s layer=%s view=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_view" \
        >> "$c2w_log"
}

render_target base diagonal_road_near
render_target residential_delivery residential_delivery_03_delivery_station_near
render_target education_buildings interior_school_cafeteria_threshold
render_target health interior_hospital_lobby
render_target commercial_services interior_bank_atrium

printf 'PASS %s revised_views=5 native_resolution=1920x1080\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_CAMERA_FINE_FINISH utc=%s status=PASS views=5\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
