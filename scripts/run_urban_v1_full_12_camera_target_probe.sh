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

# Re-render only the exact asset-bearing layers for the camera compositions
# revised after the first full-12 visual contact-sheet review.  These are not
# proxy/demo renders: every invocation updates the authoritative native
# 1920x1080 multilayer EXR and its layer manifest through the production
# z-depth renderer.  The remaining partitions are filled after these target
# layers pass visual inspection.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_runtime="$c2w_city/render_runtime/camera_target_probe"
c2w_log="$c2w_runtime/camera_target_probe.log"
c2w_status="$c2w_runtime/camera_target_probe.status"
c2w_cache="$c2w_runtime/cache"

mkdir -p "$c2w_runtime/tmp" "$c2w_cache"
: > "$c2w_log"
printf 'RUNNING %s camera_revision=full12_authored_asset_framing_v2\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

render_target_layer() {
    c2w_layer="$1"
    c2w_views="$2"
    c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
    printf 'FULL12_CAMERA_TARGET_BEGIN utc=%s layer=%s views=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_views" \
        >> "$c2w_log"
    if [ ! -s "$c2w_pack" ]; then
        printf 'FAIL %s layer=%s reason=missing_dependency_pack\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
        return 97
    fi
    /usr/bin/env \
        C2W_FULL12_RENDER_FORCE=1 \
        C2W_FULL12_RENDER_ENGINE=WORKBENCH \
        C2W_FULL12_WORKBENCH_AA=16 \
        TMPDIR="$c2w_runtime/tmp" \
        XDG_CACHE_HOME="$c2w_cache" \
        /usr/local/bin/blender --gpu-backend vulkan \
            --disable-depsgraph-on-file-load -b "$c2w_pack" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- "$c2w_layer" "$c2w_views" >> "$c2w_log" 2>&1
    printf 'FULL12_CAMERA_TARGET_DONE utc=%s layer=%s views=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_views" \
        >> "$c2w_log"
}

render_target_layer base \
    diagonal_road_near
render_target_layer commercial_services \
    bank_low_row_entrance_near,bank_headquarters_near,interior_bank_atrium
render_target_layer public_safety \
    police_library_near
render_target_layer park_leisure_support \
    park_fitness_near,leisure_fitness_near
render_target_layer residential_delivery \
    residential_delivery_01_food_delivery_locker_near,residential_delivery_02_parcel_locker_near,residential_delivery_03_delivery_station_near
render_target_layer river3_residential \
    residential_near,residential_01_river3_indoor_near,residential_02_river3_north_extension_near
render_target_layer river5_nature \
    park_near
render_target_layer artificial_lake \
    artificial_lake_pavilion_near,artificial_lake_shore_near
render_target_layer all45_unique_buildings \
    interior_residential_native
render_target_layer education_buildings \
    interior_school_cafeteria_threshold
render_target_layer health \
    interior_hospital_lobby

printf 'PASS %s target_layers=11 revised_views=19 native_resolution=1920x1080\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_CAMERA_TARGET_FINISH utc=%s status=PASS\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
