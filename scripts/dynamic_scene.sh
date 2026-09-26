#!/bin/sh

# Add common 4D effects to an already generated scene without modifying it.
#
# Usage:
#   sh scripts/dynamic_scene.sh INPUT.blend [OUTPUT.blend] [CONFIG.json] [VIDEO.mp4]
#
# Set C2W_APPLY_ONLY=1 to build the dynamic .blend without rendering the MP4.

set -eu

if [ "$#" -lt 1 ]; then
    echo "Usage: sh scripts/dynamic_scene.sh INPUT.blend [OUTPUT.blend] [CONFIG.json] [VIDEO.mp4]"
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
INPUT_BLEND=$1
OUTPUT_BLEND=${2:-"$REPO_ROOT/output/dynamics/dynamic_scene.blend"}
CONFIG_PATH=${3:-"$REPO_ROOT/configs/dynamics/default.json"}
VIDEO_PATH=${4:-"$REPO_ROOT/output/dynamics/dynamic_scene.mp4"}
BLENDER_COMMAND=${BLENDER_BIN:-blender}

if [ ! -f "$INPUT_BLEND" ]; then
    echo "Error: input scene does not exist: $INPUT_BLEND"
    exit 1
fi

set -- "$BLENDER_COMMAND" --background --python "$REPO_ROOT/worldbridge/postprocess/dynamics.py" -- \
    --input "$INPUT_BLEND" --output "$OUTPUT_BLEND" --config "$CONFIG_PATH" --video "$VIDEO_PATH"

if [ "${WORLDBRIDGE_APPLY_ONLY:-${C2W_APPLY_ONLY:-0}}" != "1" ]; then
    set -- "$@" --render
fi

cd "$REPO_ROOT"
"$@"
