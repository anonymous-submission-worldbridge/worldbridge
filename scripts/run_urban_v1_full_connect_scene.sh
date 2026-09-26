#!/bin/sh
set -eu
connect_scene="$1"
connect_gpu="$2"
connect_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
connect_out="$connect_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
export CUDA_VISIBLE_DEVICES="$connect_gpu"
blender -b -t 4 -P "$connect_root/scripts/render_urban_v1_full_connect.py" -- --scene "$connect_scene" --mode final --width 1920 --samples 96 --overwrite > "$connect_out/logs/delivery_stills_${connect_scene}.log" 2>&1
blender -b -t 4 -P "$connect_root/scripts/render_urban_v1_full_connect.py" -- --scene "$connect_scene" --mode video --width 1280 --samples 24 --frames 72 > "$connect_out/logs/delivery_video_${connect_scene}.log" 2>&1
