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
BLENDER_BIN="${BLENDER_BIN:-blender}"
OUTPUT_DIR="${1:-}"
SEED="${2:-2037}"
UNITY_PROJECT_NAME="${UNITY_PROJECT_NAME:-}"
EXPORT_FORMAT="${EXPORT_FORMAT:-unity}"
BLENDER_TMPDIR="${BLENDER_TMPDIR:-${WORLDBRIDGE_EXTERNAL}/blender_tmp}"

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/generate_and_render_urban_block.sh /abs/or/relative/output_dir [seed]

Example:
  scripts/generate_and_render_urban_block.sh outputs/urban_block_12 2038
EOF
}

if [[ -z "$OUTPUT_DIR" ]]; then
  usage
  exit 2
fi

if [[ "$OUTPUT_DIR" != /* ]]; then
  OUTPUT_DIR="$ROOT_DIR/$OUTPUT_DIR"
fi

if [[ -z "$UNITY_PROJECT_NAME" ]]; then
  UNITY_PROJECT_NAME="Unity$(basename "$OUTPUT_DIR" | sed -E 's/(^|_)([a-z])/\U\2/g')"
fi

mkdir -p "$OUTPUT_DIR" "$BLENDER_TMPDIR"
export TMPDIR="$BLENDER_TMPDIR"

cd "$ROOT_DIR"

echo "[urban-pipeline] generating scene output=$OUTPUT_DIR seed=$SEED unity_project=$UNITY_PROJECT_NAME"
"$BLENDER_BIN" -b --python infinigen_examples/generate_urban.py -- \
  --output "$OUTPUT_DIR" \
  --export-format "$EXPORT_FORMAT" \
  --seed "$SEED" \
  --unity-project-name "$UNITY_PROJECT_NAME" \
  2>&1 | tee "$OUTPUT_DIR/generate.log"

if rg -n "Nature TreeFactory failed|fallback leaf mesh|Traceback|ERROR|Exception|Aborted|Segmentation" "$OUTPUT_DIR/generate.log"; then
  echo "[urban-pipeline] generation log contains a fatal/fallback marker; refusing to render." >&2
  exit 1
fi

echo "[urban-pipeline] rendering Unity orbit mp4"
scripts/render_unity_urban_orbit.sh "$OUTPUT_DIR"
