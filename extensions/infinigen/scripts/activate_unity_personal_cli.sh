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
ACTIVATION_LOG="$EXPORT_DIR/unity_personal_activation.log"
CHECK_LOG="$EXPORT_DIR/unity_license_check.log"
CLIENT_LOG="$RUNTIME_DIR/config/unity3d/Unity/Unity.Licensing.Client.log"

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

if [[ ! -x "$ULC_BIN" ]]; then
  echo "Unity Licensing Client not found: $ULC_BIN" >&2
  exit 1
fi

if [[ ! -x "$UNITY_BIN" ]]; then
  echo "Unity Editor not found: $UNITY_BIN" >&2
  exit 1
fi

sanitize_logs() {
  local secret="${1:-}"
  local account="${2:-}"
  local file

  for file in "$ACTIVATION_LOG" "$CLIENT_LOG"; do
    [[ -f "$file" ]] || continue
    if [[ -n "$secret" ]]; then
      UNITY_SECRET_TO_REDACT="$secret" perl -0pi -e '$s=$ENV{UNITY_SECRET_TO_REDACT}; s/\Q$s\E/<redacted-password>/g if length($s)' "$file"
    fi
    if [[ -n "$account" ]]; then
      UNITY_ACCOUNT_TO_REDACT="$account" perl -0pi -e '$s=$ENV{UNITY_ACCOUNT_TO_REDACT}; s/\Q$s\E/<redacted-account>/g if length($s)' "$file"
    fi
  done
}

echo "Unity Personal CLI activation"
echo "Runtime/cache directory: $RUNTIME_DIR"
echo
echo "Note: Unity's CLI requires the password as a process argument during activation."
echo "This script does not echo it and redacts Unity logs immediately after the command exits."
echo

default_username="${UNITY_USERNAME:-}"
if [[ -n "$default_username" ]]; then
  read -r -p "Unity account email [$default_username]: " input_username
  UNITY_USERNAME="${input_username:-$default_username}"
else
  read -r -p "Unity account email: " UNITY_USERNAME
fi

read -r -s -p "Unity password: " UNITY_PASSWORD
echo

if [[ -z "$UNITY_USERNAME" || -z "$UNITY_PASSWORD" ]]; then
  echo "Unity account email and password are required." >&2
  exit 2
fi

set +e
"$ULC_BIN" \
  --username "$UNITY_USERNAME" \
  --password "$UNITY_PASSWORD" \
  --activate-all \
  --include-personal \
  >"$ACTIVATION_LOG" 2>&1
activation_status=$?
set -e

sanitize_logs "$UNITY_PASSWORD" "$UNITY_USERNAME"
unset UNITY_PASSWORD

if [[ $activation_status -ne 0 ]]; then
  echo "Unity activation failed. Redacted log:"
  echo "  $ACTIVATION_LOG"
  tail -n 80 "$ACTIVATION_LOG" || true
  exit "$activation_status"
fi

echo
echo "Activation command completed. Current entitlements:"
"$ULC_BIN" --showEntitlements || true

echo
echo "Checking Unity Editor license state..."
set +e
"$UNITY_BIN" -batchmode -nographics -quit -logFile "$CHECK_LOG"
check_status=$?
set -e

sanitize_logs "" "$UNITY_USERNAME"

if [[ $check_status -ne 0 ]]; then
  echo "Unity Editor license check failed. Log:"
  echo "  $CHECK_LOG"
  tail -n 100 "$CHECK_LOG" || true
  exit "$check_status"
fi

echo "Unity license is active and the Editor can start in batch mode."
echo "Next render command:"
echo "  cd $ROOT_DIR && scripts/render_unity_urban_block10.sh"
