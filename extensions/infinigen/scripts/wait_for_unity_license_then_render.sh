#!/usr/bin/env bash

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
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-${WORLDBRIDGE_ROOT}/infinigen}"
UNITY_ROOT="${UNITY_ROOT:-${WORLDBRIDGE_EXTERNAL}/unity}"
UNITY_BIN="${UNITY_BIN:-$UNITY_ROOT/Editors/6000.4.12f1/Editor/Unity}"
ULC_BIN="${ULC_BIN:-$UNITY_ROOT/Editors/6000.4.12f1/Editor/Data/Resources/Licensing/Client/Unity.Licensing.Client}"
EXPORT_DIR="${EXPORT_DIR:-$ROOT_DIR/outputs/urban_block_10/unity_export}"
RUNTIME_DIR="${RUNTIME_DIR:-$EXPORT_DIR/unity_runtime}"
UNITY_TMPDIR="${UNITY_TMPDIR:-${WORLDBRIDGE_EXTERNAL}/unity_tmp}"
POLL_SECONDS="${POLL_SECONDS:-30}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-480}"
LOG_FILE="${LOG_FILE:-$EXPORT_DIR/wait_for_license_then_render.log}"

mkdir -p \
  "$RUNTIME_DIR/home" \
  "$RUNTIME_DIR/config" \
  "$RUNTIME_DIR/cache" \
  "$RUNTIME_DIR/data" \
  "$UNITY_TMPDIR" \
  "$RUNTIME_DIR/upm-cache"

export HOME="$RUNTIME_DIR/home"
export XDG_CONFIG_HOME="$RUNTIME_DIR/config"
export XDG_CACHE_HOME="$RUNTIME_DIR/cache"
export XDG_DATA_HOME="$RUNTIME_DIR/data"
export TMPDIR="$UNITY_TMPDIR"
export UPM_CACHE_PATH="$RUNTIME_DIR/upm-cache"

log() {
  printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*" | tee -a "$LOG_FILE"
}

license_is_active() {
  local output
  output="$("$ULC_BIN" --showEntitlements 2>&1 || true)"
  if grep -q "No licenses were found" <<<"$output"; then
    return 1
  fi
  [[ -n "${output//[[:space:]]/}" ]]
}

log "Waiting for Unity license. Runtime/cache directory: $RUNTIME_DIR"

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  if license_is_active; then
    log "Unity license detected on attempt $attempt. Starting render."
    cd "$ROOT_DIR"
    scripts/render_unity_urban_block10.sh 2>&1 | tee -a "$LOG_FILE"
    log "Render command finished."
    exit 0
  fi

  log "Unity license not active yet ($attempt/$MAX_ATTEMPTS). Sleeping ${POLL_SECONDS}s."
  sleep "$POLL_SECONDS"
done

log "Timed out waiting for Unity license."
exit 1
