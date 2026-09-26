#!/bin/sh
set -eu
scene="$1"
card="$2"
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
out="infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
python - "$out/$scene/geometry_audit.json" <<'PY'
import json,sys
a=json.load(open(sys.argv[1]))
assert a['passed'],a
PY
export CUDA_VISIBLE_DEVICES="$card"
blender -b -t 6 -P scripts/render_urban_v1_full_connect2.py -- --scene "$scene" --mode final --width 1920 --samples 96 > "$out/logs/final_$scene.log" 2>&1
blender -b -t 6 -P scripts/render_urban_v1_full_connect2.py -- --scene "$scene" --mode video --width 1280 --samples 24 --frames 144 > "$out/logs/video_$scene.log" 2>&1
