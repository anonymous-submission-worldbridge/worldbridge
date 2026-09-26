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
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
c2w_blender="${C2W_BLENDER_BIN:-${BLENDER_BIN}}"
c2w_layer="${1:?layer key required}"
c2w_gpu="${2:?GPU index required}"
c2w_prime="${3:?DRI_PRIME PCI tag required}"
c2w_run_id="${C2W_FULL14_RUN_ID:?C2W_FULL14_RUN_ID required}"
c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
c2w_layer_log="$c2w_city/render_${c2w_layer}.log"
c2w_layer_status="$c2w_city/render_${c2w_layer}.status.json"
c2w_frame_planner="$c2w_root/scripts/plan_urban_v1_full_14_layer_frames.py"

[ -f "$c2w_pack" ] || { printf 'Missing render pack: %s\n' "$c2w_pack" >&2; exit 2; }
mkdir -p "$c2w_city/render_runtime/$c2w_layer/tmp" \
    "$c2w_city/render_runtime/$c2w_layer/cache"
: > "$c2w_layer_log"
c2w_pending_shots="$(C2W_FULL14_RUN_ID="$c2w_run_id" \
    python3 "$c2w_frame_planner" "$c2w_layer")"
c2w_pending_count="$(printf '%s\n' "$c2w_pending_shots" | awk 'NF {count++} END {print count+0}')"
printf 'FULL14_LAYER_FRAME_PLAN utc=%s layer=%s pending=%s process_boundary=one_view\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_pending_count" >> "$c2w_layer_log"

for c2w_shot in $c2w_pending_shots; do
    c2w_attempt=0
    c2w_shot_pass=0
    while [ "$c2w_attempt" -lt 3 ]; do
        c2w_attempt=$((c2w_attempt + 1))
        printf 'FULL14_FRAME_ATTEMPT_BEGIN utc=%s layer=%s shot=%s gpu=%s pci=%s backend=vulkan attempt=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
            "$c2w_gpu" "$c2w_prime" "$c2w_attempt" >> "$c2w_layer_log"
        printf '{"run_id":"%s","stage":"frame_render","layer":"%s","shot":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":%s,"status":"RUNNING","updated_utc":"%s"}\n' \
            "$c2w_run_id" "$c2w_layer" "$c2w_shot" "$c2w_gpu" "$c2w_prime" \
            "$c2w_attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
        c2w_process_exit=0
        DRI_PRIME="$c2w_prime" \
            CUDA_VISIBLE_DEVICES="$c2w_gpu" \
            C2W_FULL14_RUN_ID="$c2w_run_id" \
            C2W_FULL14_RENDER_FORCE=1 \
            C2W_FULL14_RENDER_ENGINE=EEVEE \
            C2W_FULL14_EEVEE_SAMPLES=64 \
            C2W_FULL12_RENDER_ENGINE=EEVEE \
            C2W_FULL12_EEVEE_SAMPLES=64 \
            C2W_FULL12_PERSISTENT_DATA=0 \
            TMPDIR="$c2w_city/render_runtime/$c2w_layer/tmp" \
            XDG_CACHE_HOME="$c2w_city/render_runtime/$c2w_layer/cache" \
            "$c2w_blender" --gpu-backend vulkan --disable-depsgraph-on-file-load \
                -b "$c2w_pack" \
                --python "$c2w_root/scripts/render_urban_v1_full_14_zdepth_layer.py" \
                -- "$c2w_layer" "$c2w_shot" >> "$c2w_layer_log" 2>&1 \
            || c2w_process_exit=$?
        if C2W_FULL14_RUN_ID="$c2w_run_id" \
            python3 "$c2w_frame_planner" "$c2w_layer" \
                --assert-shot "$c2w_shot" >> "$c2w_layer_log" 2>&1
        then
            c2w_shot_pass=1
            printf 'FULL14_FRAME_ATTEMPT_DONE utc=%s layer=%s shot=%s attempt=%s process_exit=%s status=PASS\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
                "$c2w_attempt" "$c2w_process_exit" >> "$c2w_layer_log"
            break
        fi
        printf 'FULL14_FRAME_RETRY utc=%s layer=%s shot=%s gpu=%s attempt=%s process_exit=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
            "$c2w_gpu" "$c2w_attempt" "$c2w_process_exit" >> "$c2w_layer_log"
    done
    if [ "$c2w_shot_pass" -ne 1 ]; then
        printf '{"run_id":"%s","stage":"frame_render","layer":"%s","shot":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":%s,"status":"FAIL","updated_utc":"%s"}\n' \
            "$c2w_run_id" "$c2w_layer" "$c2w_shot" "$c2w_gpu" "$c2w_prime" \
            "$c2w_attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
        exit 1
    fi
done

C2W_FULL14_RUN_ID="$c2w_run_id" \
    python3 "$c2w_frame_planner" "$c2w_layer" --assert-complete \
        >> "$c2w_layer_log" 2>&1
printf '{"run_id":"%s","stage":"layer_render","layer":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":1,"status":"PASS","updated_utc":"%s"}\n' \
    "$c2w_run_id" "$c2w_layer" "$c2w_gpu" "$c2w_prime" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
