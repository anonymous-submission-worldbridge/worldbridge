"""Render daylight near/far multi-view validation for urban_v3_all43_25."""
from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import json
import os
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SCENE_PATH = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_25/urban_v3_all43_25.blend"
)
OUTPUT_DIR = SCENE_PATH.parent / "renders"
PREVIEW = os.environ.get("C2W_RENDER_PREVIEW") == "1"
FORCE_CPU = os.environ.get("C2W_RENDER_CPU") == "1"
GPU_INDEX = (
    int(os.environ["C2W_RENDER_GPU_INDEX"])
    if os.environ.get("C2W_RENDER_GPU_INDEX")
    else None
)
FINAL_SAMPLES = int(os.environ.get("C2W_RENDER_SAMPLES", "40"))
RENDER_ONLY = {
    name.strip()
    for name in os.environ.get("C2W_RENDER_ONLY", "").split(",")
    if name.strip()
}


# location, look-at, filename, lens; first five are near validations, remaining
# cameras show the complete inverse-L commercial street from every useful side.
VIEWS = [
    (
        (-54.25, 2.6, 5.4),
        (-54.25, -11.25, 2.35),
        "01_copper_tap_reference_front_near.png",
        46.0,
    ),
    (
        (-46.05, 2.8, 6.0),
        (-46.05, -11.15, 2.80),
        "02_hawthorn_reference_front_near.png",
        47.0,
    ),
    (
        (-64.0, -0.5, 8.4),
        (-50.1, -11.7, 2.85),
        "03_adjacent_bar_pair_west_oblique.png",
        50.0,
    ),
    (
        (-37.0, -0.5, 7.2),
        (-48.2, -11.6, 2.70),
        "04_adjacent_bar_pair_east_oblique.png",
        50.0,
    ),
    (
        (-49.0, -3.0, 2.25),
        (-47.0, -10.50, 1.55),
        "05_bar_entrances_and_frontage_near.png",
        52.0,
    ),
    (
        (28.0, 20.0, 25.0),
        (-26.0, -24.0, 3.0),
        "06_complete_inverse_l_northeast_far.png",
        53.0,
    ),
    (
        (-105.0, 43.0, 38.0),
        (-30.0, -24.0, 3.0),
        "07_complete_inverse_l_northwest_far.png",
        58.0,
    ),
    (
        (42.0, -98.0, 39.0),
        (-30.0, -26.0, 3.0),
        "08_complete_inverse_l_southeast_far.png",
        58.0,
    ),
    (
        (-104.0, -98.0, 42.0),
        (-31.0, -26.0, 3.0),
        "09_complete_inverse_l_southwest_far.png",
        60.0,
    ),
    (
        (-30.0, 62.0, 28.0),
        (-30.0, -23.0, 3.0),
        "10_complete_north_frontage_far.png",
        48.0,
    ),
    (
        (-76.0, 19.0, 37.0),
        (-31.0, -25.0, 2.8),
        "11_complete_commercial_aerial.png",
        54.0,
    ),
    (
        (-31.0, -25.0, 112.0),
        (-31.0, -25.0, 0.0),
        "12_complete_layout_top_down.png",
        52.0,
    ),
]


def configure_cycles(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8 if PREVIEW else FINAL_SAMPLES
    scene.cycles.use_denoising = True
    scene.cycles.device = "CPU" if FORCE_CPU else "GPU"
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    device_summary = "CPU fallback"
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is not None and not FORCE_CPU:
        prefs = addon.preferences
        try:
            prefs.compute_device_type = "CUDA"
            prefs.get_devices()
            enabled = []
            cuda_devices = [device for device in prefs.devices if device.type == "CUDA"]
            for device in prefs.devices:
                device.use = False
            selected_devices = (
                [cuda_devices[GPU_INDEX]]
                if GPU_INDEX is not None and 0 <= GPU_INDEX < len(cuda_devices)
                else cuda_devices
            )
            for device in selected_devices:
                device.use = True
                enabled.append(
                    device.name
                    + (f" [CUDA index {GPU_INDEX}]" if GPU_INDEX is not None else "")
                )
            if enabled:
                device_summary = "CUDA: " + ", ".join(enabled)
            else:
                scene.cycles.device = "CPU"
        except Exception as exc:
            scene.cycles.device = "CPU"
            device_summary = f"CPU fallback ({exc})"
    if FORCE_CPU:
        device_summary = "CPU (explicit fallback after CUDA capacity check)"
    scene.render.resolution_x = 960 if PREVIEW else 1600
    scene.render.resolution_y = 540 if PREVIEW else 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 42 if PREVIEW else 35
    scene.render.film_transparent = False
    # The inherited all43 daylight world is retained; these settings prevent a
    # presentation render from accidentally becoming a night scene.
    scene.view_settings.look = "AgX - Medium High Contrast"
    return device_summary


def render_view(scene, camera, location, target, filename, lens):
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.10
    camera.data.clip_end = 1500.0
    scene.camera = camera
    scene.render.filepath = str(OUTPUT_DIR / filename)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    return round(time.perf_counter() - started, 2)


def main():
    if not SCENE_PATH.exists():
        raise FileNotFoundError(SCENE_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if Path(bpy.data.filepath).resolve() != SCENE_PATH.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(SCENE_PATH), load_ui=False)
    scene = bpy.context.scene
    camera = bpy.data.objects.get("all43_01:camera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("Expected production camera 'all43_01:camera' is missing")
    device = configure_cycles(scene)
    selected = [view for view in VIEWS if not RENDER_ONLY or view[2] in RENDER_ONLY]
    if not selected:
        raise RuntimeError({"unknown_render_selection": sorted(RENDER_ONLY)})
    render_times = {}
    for view in selected:
        print("C2W_RENDER_START=" + view[2], flush=True)
        render_times[view[2]] = render_view(scene, camera, *view)
        print(f"C2W_RENDER_DONE={view[2]}:{render_times[view[2]]}", flush=True)
    available = [view for view in VIEWS if (OUTPUT_DIR / view[2]).exists()]
    manifest = {
        "source_blend": str(SCENE_PATH),
        "output_dir": str(OUTPUT_DIR),
        "lighting": "inherited all43 daylight world with sun shadows, warm storefront practicals and neutral sky fill",
        "preview": PREVIEW,
        "engine": scene.render.engine,
        "device": device,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "samples": scene.cycles.samples,
        "near_view_count": sum(
            filename.startswith(tuple(f"0{i}" for i in range(1, 6)))
            for _, _, filename, _ in available
        ),
        "far_view_count": sum(
            not filename.startswith(tuple(f"0{i}" for i in range(1, 6)))
            for _, _, filename, _ in available
        ),
        "renders": [str(OUTPUT_DIR / view[2]) for view in available],
        "rendered_this_run": [view[2] for view in selected],
        "render_times_seconds": render_times,
    }
    name = "preview_manifest.json" if PREVIEW else "render_manifest.json"
    (OUTPUT_DIR / name).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("C2W_RENDER_MANIFEST=" + json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
