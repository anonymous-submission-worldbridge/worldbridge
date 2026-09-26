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
c2w_status="$c2w_city/render_matrix.status"
c2w_log="$c2w_city/render_matrix.log"
# Pair the three heaviest exact source families with comparably expensive or
# lighter partners so both of the proven-safe renderer slots stay useful.  The
# layer partition and final Z composition order are unchanged by launch order.
c2w_layers="river5_nature river3_residential artificial_lake all45_unique_buildings education_buildings commercial_services industrial public_safety residential_delivery all44_leisure park_leisure_support health base"
c2w_fail=0

: > "$c2w_log"
printf 'RUNNING %s parallelism=2\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
set -- $c2w_layers

while [ "$#" -gt 0 ]; do
    c2w_pids=""
    c2w_batch=""
    c2w_index=0
    while [ "$#" -gt 0 ] && [ "$c2w_index" -lt 2 ]; do
        c2w_layer="$1"
        shift
        c2w_index=$((c2w_index + 1))
        printf 'FULL12_MATRIX_LAUNCH utc=%s layer=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
        if [ "$c2w_layer" = "base" ]; then
            /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_base_alpha_chunks.sh" all &
        else
            /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_zdepth_layer_chunks.sh" "$c2w_layer" &
        fi
        c2w_pids="$c2w_pids $!"
        c2w_batch="$c2w_batch $c2w_layer"
    done
    c2w_position=1
    for c2w_pid in $c2w_pids; do
        c2w_layer="$(printf '%s\n' "$c2w_batch" | awk -v n="$c2w_position" '{print $n}')"
        if wait "$c2w_pid"; then
            printf 'FULL12_MATRIX_DONE utc=%s layer=%s status=PASS\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
        else
            c2w_fail=1
            printf 'FULL12_MATRIX_DONE utc=%s layer=%s status=FAIL\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
        fi
        c2w_position=$((c2w_position + 1))
    done
done

if [ "$c2w_fail" -eq 0 ]; then
    printf 'PASS %s parallelism=2 layers=13\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
else
    printf 'FAIL %s parallelism=2 layers=13\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
fi
exit "$c2w_fail"
