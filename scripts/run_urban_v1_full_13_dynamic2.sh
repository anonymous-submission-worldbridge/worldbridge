#!/bin/sh
# Independent v2 entry point. The original static/v1 entry points are untouched.
set -eu
cd "$(dirname "$0")/.."
out=infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic2
static=infinigen/outputs/outdoor_full_demo/urban_v1_full_13/urban_v1_full_13.blend
if [ "${1:-}" != "--render-only" ]; then
    blender --disable-depsgraph-on-file-load -b "$static" --python-exit-code 1 \
        --python scripts/build_urban_v1_full_13_dynamic2.py -- --output-dir "$out"
fi
blender --disable-depsgraph-on-file-load \
    -b "$out/urban_v1_full_13_dynamic2.blend" --python-exit-code 1 \
    --python scripts/audit_urban_v1_full_13_dynamic2.py
if [ "${1:-}" != "--render-only" ] || [ ! -f "$out/render_packs/lake_and_wind.blend" ]; then
    blender --disable-depsgraph-on-file-load \
        -b "$out/urban_v1_full_13_dynamic2.blend" --python-exit-code 1 \
        --python scripts/render_urban_v1_full_13_dynamic2.py -- \
        --output-dir "$out/render_packs" --pack-only
fi
python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); a=json.loads((p/"dynamic2_manifest.json").read_text()); b=json.loads((p/"render_packs/render_contract_all.json").read_text()); f=p/"render_packs/native_wind_master_lineage.json"; lineage=json.loads(f.read_text()) if f.exists() else {}; expected=lineage.get("attached_master_sha256",b["blend_sha256"]); assert a["output_blend_sha256"]==expected, "Stale packs: rebuild into a fresh output directory"; assert not lineage or lineage["original_master_sha256"]==b["blend_sha256"], "Invalid pack lineage"' "$out"
for shot in river_and_wind lake_and_wind; do
    blender --disable-depsgraph-on-file-load \
        -b "$out/render_packs/$shot.blend" --python-exit-code 1 \
        --python scripts/factor_urban_v1_full_13_dynamic2_pack.py
done
blender --disable-depsgraph-on-file-load \
    -b "$out/urban_v1_full_13_dynamic2.blend" --python-exit-code 1 \
    --python scripts/attach_urban_v1_full_13_dynamic2_native_wind.py
blender --disable-depsgraph-on-file-load \
    -b "$out/urban_v1_full_13_dynamic2.blend" --python-exit-code 1 \
    --python scripts/audit_urban_v1_full_13_dynamic2.py
for shot in traffic river_and_wind fountain lake_and_wind; do
    if [ "$shot" = river_and_wind ] || [ "$shot" = lake_and_wind ]; then
        python3 scripts/resume_urban_v1_full_13_dynamic2.py --shot "$shot" --gpu "${CUDA_VISIBLE_DEVICES:-0}"
        continue
    fi
    blender --gpu-backend vulkan --disable-depsgraph-on-file-load \
        -b "$out/render_packs/$shot.blend" --python-exit-code 1 \
        --python scripts/render_urban_v1_full_13_dynamic2.py -- \
        --output-dir "$out/frames" --shot "$shot" --engine cycles --width 1280 --height 720 --samples 32
done
ffmpeg -nostdin -y -framerate 24 -start_number 1 -i "$out/frames/frame_%04d.png" \
    -frames:v 384 -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
    -movflags +faststart "$out/urban_v1_full_13_dynamic2.mp4"
ffprobe -v error -count_frames -select_streams v:0 \
    -show_entries stream=width,height,r_frame_rate,nb_read_frames,duration \
    -of json "$out/urban_v1_full_13_dynamic2.mp4"
python3 scripts/verify_urban_v1_full_13_dynamic2_video.py "$out"
