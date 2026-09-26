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

# Finish the authoritative full-12 pipeline after the first render matrix and
# its already-running finalizer have reached a terminal state.  The first
# matrix may retain a historical non-zero result from a layer that is now
# being recovered by a separately locked job.  A clean matrix pass validates
# and reuses every committed native bundle, waits on the same per-layer locks,
# and renders only genuinely missing frames before final composition.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_matrix_status="$c2w_city/render_matrix.status"
c2w_finalize_status="$c2w_city/finalize.status"
c2w_status="$c2w_city/completion.status"
c2w_log="$c2w_city/completion.log"
c2w_attempt=0

mkdir -p "$c2w_city"
: > "$c2w_log"
printf 'WAITING %s for=initial_render_matrix\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

while :; do
    c2w_state="MISSING"
    if [ -f "$c2w_matrix_status" ]; then
        read -r c2w_state c2w_rest < "$c2w_matrix_status" || true
    fi
    case "$c2w_state" in
        PASS|FAIL) break ;;
    esac
    sleep 30
done

# The original finalizer must observe the initial terminal matrix result before
# this script replaces the matrix status with a clean validation pass.  This
# prevents two delivery compositors from ever running concurrently.
printf 'WAITING %s for=initial_finalizer_terminal\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
while :; do
    c2w_state="MISSING"
    if [ -f "$c2w_finalize_status" ]; then
        read -r c2w_state c2w_rest < "$c2w_finalize_status" || true
    fi
    case "$c2w_state" in
        PASS)
            printf 'PASS %s reason=initial_finalizer_already_completed\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
            exit 0
            ;;
        FAIL) break ;;
    esac
    sleep 30
done

while [ "$c2w_attempt" -lt 3 ]; do
    c2w_attempt=$((c2w_attempt + 1))
    printf 'RUNNING %s stage=clean_render_matrix attempt=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" > "$c2w_status"
    printf 'FULL12_COMPLETION_MATRIX_BEGIN utc=%s attempt=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" >> "$c2w_log"
    if /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_zdepth_matrix.sh" \
        >> "$c2w_log" 2>&1
    then
        printf 'FULL12_COMPLETION_MATRIX_PASS utc=%s attempt=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" >> "$c2w_log"
        break
    fi
    printf 'FULL12_COMPLETION_MATRIX_RETRY utc=%s attempt=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" >> "$c2w_log"
done

if [ ! -f "$c2w_matrix_status" ] || ! grep -q '^PASS ' "$c2w_matrix_status"; then
    printf 'FAIL %s stage=clean_render_matrix attempts=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" > "$c2w_status"
    exit 93
fi

printf 'RUNNING %s stage=finalize\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_COMPLETION_FINALIZE_BEGIN utc=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
if ! /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_finalize.sh" \
    >> "$c2w_log" 2>&1
then
    printf 'FAIL %s stage=finalize\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 94
fi

if [ ! -f "$c2w_finalize_status" ] || \
    ! grep -q '^PASS ' "$c2w_finalize_status"
then
    printf 'FAIL %s stage=finalize_status\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 95
fi

printf 'PASS %s matrix_attempts=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" > "$c2w_status"
printf 'FULL12_COMPLETION_PASS utc=%s matrix_attempts=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" >> "$c2w_log"
