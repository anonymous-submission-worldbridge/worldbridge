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

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/Unity_license.ulf" >&2
  exit 2
fi

ROOT_DIR="${ROOT_DIR:-${WORLDBRIDGE_ROOT}/infinigen}"
UNITY_BIN="${UNITY_BIN:-${WORLDBRIDGE_EXTERNAL}/unity/Editors/6000.4.12f1/Editor/Unity}"
EXPORT_DIR="${EXPORT_DIR:-$ROOT_DIR/outputs/urban_block_10/unity_export}"
RUNTIME_DIR="${RUNTIME_DIR:-$EXPORT_DIR/unity_runtime}"
ULF_FILE="$1"

mkdir -p \
  "$RUNTIME_DIR/home" \
  "$RUNTIME_DIR/config" \
  "$RUNTIME_DIR/cache" \
  "$RUNTIME_DIR/data" \
  "$RUNTIME_DIR/tmp" \
  "$RUNTIME_DIR/upm-cache"

export HOME="$RUNTIME_DIR/home"
export XDG_CONFIG_HOME="$RUNTIME_DIR/config"
export XDG_CACHE_HOME="$RUNTIME_DIR/cache"
export XDG_DATA_HOME="$RUNTIME_DIR/data"
export TMPDIR="$RUNTIME_DIR/tmp"
export UPM_CACHE_PATH="$RUNTIME_DIR/upm-cache"

"$UNITY_BIN" -batchmode -nographics -quit \
  -manualLicenseFile "$ULF_FILE" \
  -logFile "$EXPORT_DIR/unity_manual_license.log"
