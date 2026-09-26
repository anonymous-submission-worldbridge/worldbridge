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
# Supervised long-running render wrapper for the production full-12 blend.
# All logs and state stay inside the requested full-12 output directory.
set -u

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_out="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_log="$c2w_out/render_job.log"
c2w_status="$c2w_out/render_job.status"
c2w_args="${1:-all}"

: > "$c2w_log"
: > "$c2w_status"
printf 'RUNNING %s request=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_args" > "$c2w_status"

cd "$c2w_root" || exit 97
C2W_FULL12_RENDER_FORCE="${C2W_FULL12_RENDER_FORCE:-0}" \
    /usr/local/bin/blender --disable-depsgraph-on-file-load -b \
    "$c2w_out/urban_v1_full_12.blend" \
    --python "$c2w_root/scripts/render_urban_v1_full_12_daytime.py" \
    -- "$c2w_args" >> "$c2w_log" 2>&1 &
c2w_blender_pid=$!
while kill -0 "$c2w_blender_pid" 2>/dev/null; do
    c2w_rss_kib="$(awk '/^VmRSS:/ {print $2}' "/proc/$c2w_blender_pid/status" 2>/dev/null)"
    c2w_vms_kib="$(awk '/^VmSize:/ {print $2}' "/proc/$c2w_blender_pid/status" 2>/dev/null)"
    printf 'FULL12_RESOURCE utc=%s rss_kib=%s vms_kib=%s\n' \
        "$(date -u +%H:%M:%S)" "${c2w_rss_kib:-0}" "${c2w_vms_kib:-0}" >> "$c2w_log"
    sleep 5
done
wait "$c2w_blender_pid"
c2w_code=$?

if [ "$c2w_code" -eq 0 ]; then
    printf 'PASS %s exit=%s request=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" "$c2w_args" > "$c2w_status"
else
    printf 'FAIL %s exit=%s request=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" "$c2w_args" > "$c2w_status"
fi
exit "$c2w_code"
