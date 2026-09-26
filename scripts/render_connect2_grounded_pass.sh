#!/bin/sh
set -eu
scene="$1"
card="$2"
clips="$3"
out="infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
export CUDA_VISIBLE_DEVICES="$card"
blender -b -t 5 -P scripts/render_urban_v1_full_connect2.py -- --scene "$scene" --mode final --width 1920 --samples 96 --overwrite > "$out/logs/grounded_final_$scene.log" 2>&1
blender -b -t 5 -P scripts/render_urban_v1_full_connect2.py -- --scene "$scene" --mode video --shots "$clips" --width 1280 --samples 24 --frames 144 --overwrite > "$out/logs/grounded_video_$scene.log" 2>&1
