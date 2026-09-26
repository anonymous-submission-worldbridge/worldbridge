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
UNITY_BIN="${UNITY_BIN:-${WORLDBRIDGE_EXTERNAL}/unity/Editors/6000.4.12f1/Editor/Unity}"
UNITY_TMPDIR="${UNITY_TMPDIR:-${WORLDBRIDGE_EXTERNAL}/unity_tmp}"
UNITY_RUNTIME_DIR="${UNITY_RUNTIME_DIR:-$ROOT_DIR/outputs/unity_runtime}"
LEGACY_RUNTIME_DIR="${LEGACY_RUNTIME_DIR:-$ROOT_DIR/outputs/urban_block_10/unity_export/unity_runtime}"
UNITY_RENDER_DISPLAY="${UNITY_RENDER_DISPLAY:-:1}"
UNITY_RENDER_XAUTHORITY="${UNITY_RENDER_XAUTHORITY:-${WORLDBRIDGE_EXTERNAL}/turbovnc/runtime/home/.Xauthority}"
UNITY_RENDER_WIDTH="${UNITY_RENDER_WIDTH:-2560}"
UNITY_RENDER_HEIGHT="${UNITY_RENDER_HEIGHT:-1440}"
UNITY_RENDER_FRAMES="${UNITY_RENDER_FRAMES:-120}"
UNITY_RENDER_FPS="${UNITY_RENDER_FPS:-24}"
UNITY_VIDEO_CRF="${UNITY_VIDEO_CRF:-18}"

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/render_unity_urban_orbit.sh /path/to/urban_output_or_unity_export

Examples:
  scripts/render_unity_urban_orbit.sh outputs/urban_block_11
  UNITY_RENDER_WIDTH=1920 UNITY_RENDER_HEIGHT=1080 scripts/render_unity_urban_orbit.sh outputs/urban_block_11
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

INPUT_PATH="$1"
if [[ "$INPUT_PATH" != /* ]]; then
  INPUT_PATH="$ROOT_DIR/$INPUT_PATH"
fi

if [[ -d "$INPUT_PATH/unity_export" ]]; then
  SCENE_DIR="$INPUT_PATH"
  EXPORT_DIR="$INPUT_PATH/unity_export"
else
  SCENE_DIR="$(dirname "$INPUT_PATH")"
  EXPORT_DIR="$INPUT_PATH"
fi

if [[ ! -d "$EXPORT_DIR" ]]; then
  echo "Unity export directory not found: $EXPORT_DIR" >&2
  exit 1
fi

PROJECT_DIR="${PROJECT_DIR:-}"
if [[ -z "$PROJECT_DIR" ]]; then
  PROJECT_DIR="$(find "$EXPORT_DIR" -maxdepth 1 -mindepth 1 -type d -name 'Unity*' | sort | head -n 1)"
fi

if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR" ]]; then
  echo "Unity project directory not found under: $EXPORT_DIR" >&2
  exit 1
fi

VIDEO_OUT="${VIDEO_OUT:-$EXPORT_DIR/orbit_preview_1440p.mp4}"
FRAME_DIR="$PROJECT_DIR/Renders/InfinigenUrban/orbit_frames"

mkdir -p \
  "$UNITY_RUNTIME_DIR/home" \
  "$UNITY_RUNTIME_DIR/config" \
  "$UNITY_RUNTIME_DIR/cache" \
  "$UNITY_RUNTIME_DIR/data" \
  "$UNITY_RUNTIME_DIR/upm-cache" \
  "$UNITY_TMPDIR"

if [[ ! -d "$UNITY_RUNTIME_DIR/config/unity3d/Unity/licenses" && -d "$LEGACY_RUNTIME_DIR/config/unity3d/Unity/licenses" ]]; then
  mkdir -p "$UNITY_RUNTIME_DIR/config/unity3d/Unity"
  cp -a "$LEGACY_RUNTIME_DIR/config/unity3d/Unity/licenses" "$UNITY_RUNTIME_DIR/config/unity3d/Unity/"
fi

export HOME="$UNITY_RUNTIME_DIR/home"
export XDG_CONFIG_HOME="$UNITY_RUNTIME_DIR/config"
export XDG_CACHE_HOME="$UNITY_RUNTIME_DIR/cache"
export XDG_DATA_HOME="$UNITY_RUNTIME_DIR/data"
export TMPDIR="$UNITY_TMPDIR"
export UPM_CACHE_PATH="$UNITY_RUNTIME_DIR/upm-cache"

if [[ -d "$FRAME_DIR" ]]; then
  if command -v mustrm >/dev/null 2>&1; then
    mustrm "$FRAME_DIR" >/dev/null
  else
    echo "Frame directory exists and mustrm is unavailable: $FRAME_DIR" >&2
    exit 1
  fi
fi

echo "[unity-render] scene_dir=$SCENE_DIR"
echo "[unity-render] export_dir=$EXPORT_DIR"
echo "[unity-render] project_dir=$PROJECT_DIR"
echo "[unity-render] video_out=$VIDEO_OUT"
echo "[unity-render] resolution=${UNITY_RENDER_WIDTH}x${UNITY_RENDER_HEIGHT} frames=$UNITY_RENDER_FRAMES fps=$UNITY_RENDER_FPS"

"$UNITY_BIN" -batchmode -nographics -quit \
  -projectPath "$PROJECT_DIR" \
  -logFile "$EXPORT_DIR/unity_build_controlled.log" \
  -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.BuildSceneFromManifest

UNITY_RENDER_WIDTH="$UNITY_RENDER_WIDTH" \
UNITY_RENDER_HEIGHT="$UNITY_RENDER_HEIGHT" \
UNITY_RENDER_FRAMES="$UNITY_RENDER_FRAMES" \
DISPLAY="$UNITY_RENDER_DISPLAY" \
XAUTHORITY="$UNITY_RENDER_XAUTHORITY" \
LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
MESA_GL_VERSION_OVERRIDE="${MESA_GL_VERSION_OVERRIDE:-4.5}" \
"$UNITY_BIN" -batchmode -quit -force-glcore \
  -projectPath "$PROJECT_DIR" \
  -logFile "$EXPORT_DIR/unity_render_controlled.log" \
  -executeMethod InfinigenUnity.InfinigenUrbanSceneBuilder.RenderOrbitFrames

ffmpeg -y -framerate "$UNITY_RENDER_FPS" \
  -i "$FRAME_DIR/frame_%04d.png" \
  -c:v libx264 -preset slow -crf "$UNITY_VIDEO_CRF" -pix_fmt yuv420p \
  "$VIDEO_OUT"

echo "$VIDEO_OUT"
