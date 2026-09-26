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
c2w_run_id="full13-20260911T110030"
c2w_views="${C2W_EXPECTED_CHANGED_VIEWS:?comma-separated changed views required}"
c2w_log="$c2w_city/camera_recovery.log"
c2w_status="$c2w_city/camera_recovery.status.json"
c2w_openexr_python="${WORLDBRIDGE_PYTHON}"
c2w_blender="/usr/local/bin/blender"
c2w_stage="initializing"

status() {
    printf '{"schema":"agent.full13.camera_recovery.v1","run_id":"%s","views":"%s","status":"%s","stage":"%s","updated_utc":"%s"}\n' \
        "$c2w_run_id" "$c2w_views" "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        > "$c2w_status.writing"
    mv "$c2w_status.writing" "$c2w_status"
}

fail() {
    c2w_exit="$?"
    status FAIL "$c2w_stage"
    printf 'FULL13_CAMERA_RECOVERY_FAILED utc=%s stage=%s exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_stage" "$c2w_exit" >> "$c2w_log"
    exit "$c2w_exit"
}
trap fail HUP INT TERM EXIT

run_layer() {
    printf 'FULL13_CAMERA_LAYER_BEGIN utc=%s layer=%s gpu=%s views=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$c2w_views" >> "$c2w_log"
    C2W_FULL13_RUN_ID="$c2w_run_id" \
        "$c2w_root/scripts/run_urban_v1_full_13_layer_worker.sh" \
        "$1" "$2" "$3" >> "$c2w_log" 2>&1
    printf 'FULL13_CAMERA_LAYER_DONE utc=%s layer=%s gpu=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$c2w_log"
}

run_batch() {
    c2w_pids=""
    while [ "$#" -gt 0 ]; do
        c2w_layer="$1"
        c2w_gpu="$2"
        c2w_prime="$3"
        shift 3
        run_layer "$c2w_layer" "$c2w_gpu" "$c2w_prime" &
        c2w_pids="$c2w_pids $!"
    done
    c2w_failed=0
    for c2w_pid in $c2w_pids; do
        wait "$c2w_pid" || c2w_failed=1
    done
    [ "$c2w_failed" -eq 0 ]
}

: > "$c2w_log"
c2w_stage="camera_preflight"
status RUNNING "$c2w_stage"
C2W_FULL13_RUN_ID="$c2w_run_id" \
    "$c2w_blender" -b --factory-startup \
        --python "$c2w_root/scripts/preflight_urban_v1_full_13_cameras.py" \
        >> "$c2w_log" 2>&1

c2w_stage="camera_contract_rebind"
status RUNNING "$c2w_stage"
C2W_EXPECTED_CHANGED_VIEWS="$c2w_views" \
    python3 "$c2w_root/scripts/rebind_urban_v1_full_13_camera_contract.py" \
        >> "$c2w_log" 2>&1

c2w_stage="standard_layers_batch_1"
status RUNNING "$c2w_stage"
run_batch \
    river5_nature 0 pci-0000_4f_00_0 \
    river3_residential 1 pci-0000_52_00_0 \
    artificial_lake 2 pci-0000_53_00_0 \
    all45_unique_buildings 3 pci-0000_57_00_0 \
    education_buildings 4 pci-0000_98_00_0 \
    commercial_services 5 pci-0000_ce_00_0

c2w_stage="standard_layers_batch_2"
status RUNNING "$c2w_stage"
run_batch \
    industrial 0 pci-0000_4f_00_0 \
    public_safety 1 pci-0000_52_00_0 \
    residential_delivery 2 pci-0000_53_00_0 \
    all44_leisure 3 pci-0000_57_00_0 \
    park_leisure_support 4 pci-0000_98_00_0 \
    health 5 pci-0000_ce_00_0

c2w_stage="standard_layers_batch_3"
status RUNNING "$c2w_stage"
run_batch \
    full13_unique_urban_fabric 0 pci-0000_4f_00_0 \
    full13_semantic_interiors 1 pci-0000_52_00_0 \
    full13_public_realm 2 pci-0000_53_00_0 \
    base 3 pci-0000_57_00_0

# The previously certified selective semantic-geometry rebind remains part
# of this same run.  The new change is CAMERA-ONLY; never label freshly
# rerendered views as byte-identical non-raster source-frame reserialization.
c2w_stage="direct_civic_current_camera"
status RUNNING "$c2w_stage"
printf 'FULL13_CAMERA_DIRECT_BEGIN utc=%s key=direct_civic shot=school_library_shared_street gpu=6\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
C2W_FULL13_RUN_ID="$c2w_run_id" C2W_FULL13_RENDER_FORCE=1 \
    C2W_FULL13_RENDER_ENGINE=EEVEE C2W_FULL13_EEVEE_SAMPLES=64 \
    C2W_FULL12_RENDER_ENGINE=EEVEE C2W_FULL12_EEVEE_SAMPLES=64 \
    C2W_FULL12_PERSISTENT_DATA=0 CUDA_VISIBLE_DEVICES=6 \
    DRI_PRIME=pci-0000_d1_00_0 \
    TMPDIR="$c2w_city/render_runtime/direct_civic/tmp" \
    XDG_CACHE_HOME="$c2w_city/render_runtime/direct_civic/cache" \
    "$c2w_blender" --gpu-backend vulkan --disable-depsgraph-on-file-load \
    -b "$c2w_city/render_dependency_packs/direct_civic.blend" \
    --python "$c2w_root/scripts/render_urban_v1_full_13_direct_validation.py" \
    -- direct_civic school_library_shared_street >> "$c2w_log" 2>&1

c2w_stage="direct_manifest_certification"
status RUNNING "$c2w_stage"
python3 "$c2w_root/scripts/certify_urban_v1_full_13_direct_manifests.py" \
    >> "$c2w_log" 2>&1

c2w_stage="direct_equivalence"
status RUNNING "$c2w_stage"
"$c2w_openexr_python" \
    "$c2w_root/scripts/compare_urban_v1_full_13_direct_validation.py" \
    >> "$c2w_log" 2>&1

c2w_stage="composition"
status RUNNING "$c2w_stage"
C2W_FULL13_RUN_ID="$c2w_run_id" C2W_COMPOSE_VIEW_NAMES="$c2w_views" \
    "$c2w_blender" -b --factory-startup \
        --python "$c2w_root/scripts/compose_urban_v1_full_13_zdepth.py" \
        >> "$c2w_log" 2>&1

c2w_stage="resource_audit"
status RUNNING "$c2w_stage"
C2W_FULL13_PIPELINE_UNIT=worldbridge-full13-pipeline-r18.service \
"$c2w_openexr_python" \
    "$c2w_root/scripts/summarize_urban_v1_full_13_resources.py" \
    >> "$c2w_log" 2>&1

c2w_stage="complete"
status PASS "$c2w_stage"
printf 'FULL13_CAMERA_RECOVERY_DONE utc=%s status=PASS views=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_views" >> "$c2w_log"
trap - HUP INT TERM EXIT
