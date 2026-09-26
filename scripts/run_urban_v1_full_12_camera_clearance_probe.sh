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

# Final two-shot clearance probe after resolving the cafeteria fence plane and
# the hospital's three overlapping authored massing cores.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_runtime="$c2w_city/render_runtime/camera_clearance_probe"
c2w_log="$c2w_runtime/camera_clearance_probe.log"
c2w_status="$c2w_runtime/camera_clearance_probe.status"

mkdir -p "$c2w_runtime/tmp" "$c2w_runtime/cache"
: > "$c2w_log"
printf 'RUNNING %s views=2\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

render_target() {
    c2w_layer="$1"
    c2w_view="$2"
    printf 'FULL12_CAMERA_CLEARANCE_BEGIN utc=%s layer=%s view=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_view" \
        >> "$c2w_log"
    /usr/bin/env C2W_FULL12_RENDER_FORCE=1 \
        C2W_FULL12_RENDER_ENGINE=WORKBENCH C2W_FULL12_WORKBENCH_AA=16 \
        TMPDIR="$c2w_runtime/tmp" XDG_CACHE_HOME="$c2w_runtime/cache" \
        /usr/local/bin/blender --gpu-backend vulkan \
            --disable-depsgraph-on-file-load -b \
            "$c2w_city/render_dependency_packs/$c2w_layer.blend" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- "$c2w_layer" "$c2w_view" >> "$c2w_log" 2>&1
    printf 'FULL12_CAMERA_CLEARANCE_DONE utc=%s layer=%s view=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_view" \
        >> "$c2w_log"
}

render_target education_buildings interior_school_cafeteria_threshold
render_target health interior_hospital_lobby

printf 'PASS %s views=2 native_resolution=1920x1080\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_CAMERA_CLEARANCE_FINISH utc=%s status=PASS views=2\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
