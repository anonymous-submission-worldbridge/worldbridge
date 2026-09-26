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

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
c2w_layer_root="$c2w_city/renders/camera_diagnostics_r2"
c2w_log="$c2w_city/camera_diagnostics_r2.log"
c2w_blender="/usr/local/bin/blender"

run_preview() {
    c2w_layer="$1"
    c2w_gpu="$2"
    c2w_prime="$3"
    shift 3
    printf 'FULL13_CAMERA_DIAGNOSTIC_BEGIN utc=%s layer=%s gpu=%s views=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_gpu" "$*" >> "$c2w_log"
    DRI_PRIME="$c2w_prime" CUDA_VISIBLE_DEVICES="$c2w_gpu" \
        C2W_FULL13_RUN_ID=full13-20260911T110030 \
        C2W_FULL13_LAYER_ROOT="$c2w_layer_root" \
        C2W_FULL13_RENDER_ENGINE=EEVEE C2W_FULL13_EEVEE_SAMPLES=32 \
        C2W_FULL12_RENDER_ENGINE=EEVEE C2W_FULL12_EEVEE_SAMPLES=32 \
        C2W_FULL12_RENDER_FORCE=1 C2W_FULL12_PERSISTENT_DATA=0 \
        TMPDIR="$c2w_city/render_runtime/$c2w_layer/tmp" \
        XDG_CACHE_HOME="$c2w_city/render_runtime/$c2w_layer/cache" \
        "$c2w_blender" --gpu-backend vulkan --disable-depsgraph-on-file-load \
            -b "$c2w_city/render_dependency_packs/$c2w_layer.blend" \
            --python "$c2w_root/scripts/render_urban_v1_full_13_zdepth_layer.py" \
            -- "$c2w_layer" "$@" >> "$c2w_log" 2>&1
    printf 'FULL13_CAMERA_DIAGNOSTIC_DONE utc=%s layer=%s gpu=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_gpu" >> "$c2w_log"
}

mkdir -p "$c2w_layer_root"
: > "$c2w_log"
run_preview health 0 pci-0000_4f_00_0 hospital_outskirts_atrium_near &
c2w_p1=$!
run_preview artificial_lake 1 pci-0000_52_00_0 artificial_lake_pavilion_near &
c2w_p2=$!
run_preview commercial_services 2 pci-0000_53_00_0 atm_row_front interior_commercial_bar &
c2w_p3=$!
run_preview all45_unique_buildings 3 pci-0000_57_00_0 interior_residential_native &
c2w_p4=$!
run_preview full13_semantic_interiors 4 pci-0000_98_00_0 interior_bank_atrium interior_hospital_lobby &
c2w_p5=$!
run_preview education_buildings 5 pci-0000_ce_00_0 police_library_near &
c2w_p6=$!
c2w_failed=0
for c2w_pid in "$c2w_p1" "$c2w_p2" "$c2w_p3" "$c2w_p4" "$c2w_p5" "$c2w_p6"; do
    wait "$c2w_pid" || c2w_failed=1
done
[ "$c2w_failed" -eq 0 ]
run_preview public_safety 0 pci-0000_4f_00_0 police_library_near
printf 'FULL13_CAMERA_DIAGNOSTICS_PASS utc=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
