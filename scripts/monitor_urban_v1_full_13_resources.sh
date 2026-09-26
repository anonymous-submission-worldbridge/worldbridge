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

c2w_city="${WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
c2w_run_id="${C2W_FULL13_RUN_ID:-unknown}"
c2w_unit="${C2W_FULL13_MONITORED_UNIT:-worldbridge-full13-pipeline-r2.service}"
c2w_output="$c2w_city/resource_profile.csv"
c2w_temporary="$c2w_output.writing"

if [ ! -s "$c2w_output" ]; then
    printf 'run_id,timestamp_utc,unit,unit_state,service_memory_bytes,service_cpu_nsec,gpu_index,gpu_utilization_percent,gpu_memory_used_mib,gpu_memory_total_mib\n' > "$c2w_temporary"
    mv "$c2w_temporary" "$c2w_output"
fi

while :; do
    c2w_timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    c2w_state="$(systemctl --user show "$c2w_unit" --property=ActiveState --value 2>/dev/null || printf unknown)"
    c2w_memory="$(systemctl --user show "$c2w_unit" --property=MemoryCurrent --value 2>/dev/null || printf 0)"
    c2w_cpu="$(systemctl --user show "$c2w_unit" --property=CPUUsageNSec --value 2>/dev/null || printf 0)"
    [ "$c2w_memory" != "[not set]" ] || c2w_memory=0
    [ "$c2w_cpu" != "[not set]" ] || c2w_cpu=0
    nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total \
        --format=csv,noheader,nounits 2>/dev/null | while IFS=, read -r c2w_gpu c2w_util c2w_used c2w_total; do
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$c2w_run_id" "$c2w_timestamp" "$c2w_unit" "$c2w_state" \
            "$c2w_memory" "$c2w_cpu" \
            "$(printf '%s' "$c2w_gpu" | tr -d ' ')" \
            "$(printf '%s' "$c2w_util" | tr -d ' ')" \
            "$(printf '%s' "$c2w_used" | tr -d ' ')" \
            "$(printf '%s' "$c2w_total" | tr -d ' ')" >> "$c2w_output"
    done
    [ "$c2w_state" = "active" ] || break
    sleep 30
done
