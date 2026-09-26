# Render Blend Videos

Generic video rendering tools for any Blender scene.

Files in this visualization tool directory:

- `render_third_person_orbit.py`: renders a third-person orbit around the scene.
- `render_first_person_walkthrough.py`: renders a first-person walkthrough path.
- `render_blend_videos.sh`: runs both scripts and writes two MP4 files.

Default example:

```bash
cd external/infinigen
CUDA_VISIBLE_DEVICES=0 bash infinigen/tools/visualization/render_blend_videos.sh \
  outputs/indoor_outdoor_villa_demo/coarse_gpu_limited/scene.blend \
  outputs/indoor_outdoor_villa_demo/videos
```

Outputs:

```bash
outputs/indoor_outdoor_villa_demo/videos/third_person_orbit.mp4
outputs/indoor_outdoor_villa_demo/videos/first_person_walkthrough.mp4
```

Fast preview:

```bash
cd external/infinigen
VIDEO_RES_X=960 VIDEO_RES_Y=540 VIDEO_SAMPLES=16 THIRD_PERSON_FRAMES=96 FIRST_PERSON_FRAMES=120 \
CUDA_VISIBLE_DEVICES=0 bash infinigen/tools/visualization/render_blend_videos.sh /path/to/scene.blend /path/to/video_dir
```

Higher quality:

```bash
cd external/infinigen
VIDEO_RES_X=1920 VIDEO_RES_Y=1080 VIDEO_SAMPLES=128 THIRD_PERSON_FRAMES=360 FIRST_PERSON_FRAMES=420 \
CUDA_VISIBLE_DEVICES=0 bash infinigen/tools/visualization/render_blend_videos.sh /path/to/scene.blend /path/to/video_dir
```

Useful environment variables:

- `VIDEO_ENGINE=CYCLES` for final rendering; `VIDEO_ENGINE=BLENDER_EEVEE_NEXT` for fast preview.
- `VIDEO_SAMPLES=64` controls Cycles samples.
- `VIDEO_RES_X` and `VIDEO_RES_Y` control resolution.
- `THIRD_PERSON_FRAMES` and `FIRST_PERSON_FRAMES` control video length.
- `BLENDER_BIN=/path/to/blender` selects a Blender executable.
- `FIRST_PERSON_PATH_JSON=/path/to/path.json` uses a custom first-person route.

Custom first-person path JSON:

```json
{
  "waypoints": [
    {"location": [3.2, -6.0, 1.62], "target": [6.0, 4.5, 2.2]},
    {"location": [3.2, 2.2, 1.62], "target": [8.0, 2.0, 1.6]}
  ]
}
```
