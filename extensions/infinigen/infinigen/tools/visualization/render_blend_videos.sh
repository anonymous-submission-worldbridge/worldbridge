#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

SCENE_INPUT="${1:-${SCENE:-outputs/indoor_outdoor_villa_demo/coarse_gpu_limited/scene.blend}}"
VIDEO_DIR_INPUT="${2:-${VIDEO_DIR:-outputs/rendered_videos/$(basename "${SCENE_INPUT%.*}")}}"
BLENDER_BIN="${BLENDER_BIN:-blender}"

THIRD_SCRIPT="${SCRIPT_DIR}/render_third_person_orbit.py"
FIRST_SCRIPT="${SCRIPT_DIR}/render_first_person_walkthrough.py"

if [[ ! -f "${SCENE_INPUT}" ]]; then
  echo "[error] scene file not found: ${SCENE_INPUT}" >&2
  echo "usage: bash render_blend_videos.sh /path/to/scene.blend [output_dir]" >&2
  exit 1
fi

SCENE="$(readlink -f "${SCENE_INPUT}")"
mkdir -p "${VIDEO_DIR_INPUT}"
VIDEO_DIR="$(readlink -f "${VIDEO_DIR_INPUT}")"
THIRD_OUT="${VIDEO_DIR}/third_person_orbit.mp4"
FIRST_OUT="${VIDEO_DIR}/first_person_walkthrough.mp4"

echo "[info] scene: ${SCENE}"
echo "[info] output dir: ${VIDEO_DIR}"
echo "[info] blender: ${BLENDER_BIN}"
echo "[info] VIDEO_ENGINE=${VIDEO_ENGINE:-CYCLES}"
echo "[info] VIDEO_RES_X=${VIDEO_RES_X:-1920}"
echo "[info] VIDEO_RES_Y=${VIDEO_RES_Y:-1080}"
echo "[info] VIDEO_SAMPLES=${VIDEO_SAMPLES:-64}"
echo "[info] THIRD_PERSON_FRAMES=${THIRD_PERSON_FRAMES:-240}"
echo "[info] FIRST_PERSON_FRAMES=${FIRST_PERSON_FRAMES:-288}"
echo "[info] PARALLEL_VIDEOS=${PARALLEL_VIDEOS:-0}"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi || true
else
  echo "[warn] nvidia-smi not found in PATH; Blender will still try configured GPU devices."
fi

render_third_person() {
  echo "[render] third-person orbit"
  "${BLENDER_BIN}" -b "${SCENE}" \
    --python "${THIRD_SCRIPT}" -- \
    --output "${THIRD_OUT}" \
    --frames "${THIRD_PERSON_FRAMES:-240}"

  if [[ ! -s "${THIRD_OUT}" ]]; then
    echo "[error] third-person render did not produce ${THIRD_OUT}" >&2
    return 1
  fi
}

render_first_person() {
  echo "[render] first-person walkthrough"
  "${BLENDER_BIN}" -b "${SCENE}" \
    --python "${FIRST_SCRIPT}" -- \
    --output "${FIRST_OUT}" \
    --frames "${FIRST_PERSON_FRAMES:-288}"

  if [[ ! -s "${FIRST_OUT}" ]]; then
    echo "[error] first-person render did not produce ${FIRST_OUT}" >&2
    return 1
  fi
}

if [[ "${PARALLEL_VIDEOS:-0}" == "1" ]]; then
  echo "[render] running third-person and first-person renders in parallel"
  render_third_person &
  third_pid=$!
  render_first_person &
  first_pid=$!
  wait "${third_pid}"
  wait "${first_pid}"
else
  render_third_person
  render_first_person
fi

echo "[done] videos:"
ls -lh "${THIRD_OUT}" "${FIRST_OUT}"
