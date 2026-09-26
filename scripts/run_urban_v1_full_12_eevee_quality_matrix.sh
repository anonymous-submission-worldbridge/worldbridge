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

# Three balanced workers upgrade all thirteen exact raster partitions.  The
# final compositor is intentionally not allowed to run until every layer and
# every one of its 80 frame records proves Eevee material evaluation.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_status="$c2w_city/quality_upgrade.status"
c2w_log="$c2w_city/quality_upgrade.log"
c2w_fail_dir="$c2w_city/render_runtime/eevee_quality/failures"

mkdir -p "$c2w_fail_dir"
find "$c2w_fail_dir" -maxdepth 1 -type f -name '*.fail' -delete
: > "$c2w_log"
printf 'RUNNING %s engine=BLENDER_EEVEE samples=32 parallelism=3 layers=13\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

run_worker() {
    c2w_worker="$1"
    shift
    for c2w_layer in "$@"; do
        printf 'FULL12_EEVEE_MATRIX_LAUNCH utc=%s worker=%s layer=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_worker" "$c2w_layer" \
            >> "$c2w_log"
        if C2W_FULL12_EEVEE_SAMPLES=32 \
            /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_eevee_layer_chunks.sh" \
            "$c2w_layer"; then
            printf 'FULL12_EEVEE_MATRIX_DONE utc=%s worker=%s layer=%s status=PASS\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_worker" "$c2w_layer" \
                >> "$c2w_log"
        else
            : > "$c2w_fail_dir/$c2w_layer.fail"
            printf 'FULL12_EEVEE_MATRIX_DONE utc=%s worker=%s layer=%s status=FAIL\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_worker" "$c2w_layer" \
                >> "$c2w_log"
            return 1
        fi
    done
}

# The heaviest linked sources are distributed across workers; each worker
# advances independently so a long river frame never leaves the other two
# renderer slots idle.
run_worker 1 river5_nature residential_delivery public_safety base &
c2w_pid_1=$!
run_worker 2 artificial_lake all44_leisure health park_leisure_support &
c2w_pid_2=$!
run_worker 3 education_buildings commercial_services river3_residential all45_unique_buildings industrial &
c2w_pid_3=$!

c2w_failed=0
wait "$c2w_pid_1" || c2w_failed=1
wait "$c2w_pid_2" || c2w_failed=1
wait "$c2w_pid_3" || c2w_failed=1

if [ "$c2w_failed" -ne 0 ] || find "$c2w_fail_dir" -maxdepth 1 -type f -name '*.fail' | grep -q .; then
    printf 'FAIL %s engine=BLENDER_EEVEE samples=32 layers=13\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 1
fi

printf 'PASS %s engine=BLENDER_EEVEE samples=32 parallelism=3 layers=13 views_per_layer=80\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_EEVEE_MATRIX_FINISH utc=%s status=PASS layers=13 views_per_layer=80\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
