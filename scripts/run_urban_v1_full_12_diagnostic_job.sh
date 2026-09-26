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
c2w_keys="${1:-}"
c2w_out="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_label="$(printf '%s' "${c2w_keys:-structural}" | tr ',' '_')"
c2w_log="$c2w_out/diagnostic_${c2w_label}.log"
c2w_status="$c2w_out/diagnostic_${c2w_label}.status"
: > "$c2w_log"
printf 'RUNNING %s keys=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_keys" > "$c2w_status"
cd "$c2w_root" || exit 97
/usr/local/bin/blender --disable-depsgraph-on-file-load -b \
    "$c2w_out/urban_v1_full_12.blend" \
    --python "$c2w_root/scripts/diagnose_urban_v1_full_12_subset.py" \
    -- "$c2w_keys" >> "$c2w_log" 2>&1 &
c2w_pid=$!
while kill -0 "$c2w_pid" 2>/dev/null; do
    c2w_rss="$(awk '/^VmRSS:/ {print $2}' "/proc/$c2w_pid/status" 2>/dev/null)"
    printf 'FULL12_DIAGNOSTIC_RESOURCE utc=%s rss_kib=%s\n' \
        "$(date -u +%H:%M:%S)" "${c2w_rss:-0}" >> "$c2w_log"
    sleep 5
done
wait "$c2w_pid"
c2w_code=$?
if [ "$c2w_code" -eq 0 ]; then
    printf 'PASS %s exit=%s keys=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" "$c2w_keys" > "$c2w_status"
else
    printf 'FAIL %s exit=%s keys=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" "$c2w_keys" > "$c2w_status"
fi
exit "$c2w_code"
