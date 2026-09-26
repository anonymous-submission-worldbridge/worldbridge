"""Render presentation views for the completed urban_v3_all43_24 scene.

The hero camera intentionally reproduces the all43_21 inverse-L overview.
The remaining cameras are farther away and circle the complete commercial
street block so that the full layout is readable from several directions.
"""
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
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_24"
    / "urban_v3_all43_24.blend"
)
OUTPUT_DIR = SCENE_PATH.parent / "renders"
PREVIEW = os.environ.get("C2W_RENDER_PREVIEW") == "1"
RENDER_ONLY = {
    name.strip()
    for name in os.environ.get("C2W_RENDER_ONLY", "").split(",")
    if name.strip()
}


# (camera location, look-at target, filename, focal length in mm)
VIEWS = [
    (
        (25.0, 17.0, 24.0),
        (-23.0, -25.0, 3.0),
        "01_reference_inverse_l_overview.png",
        53.0,
    ),
    (
        (48.0, 42.0, 38.0),
        (-28.0, -25.0, 3.0),
        "02_far_northeast_full_street.png",
        56.0,
    ),
    (
        (-92.0, 45.0, 40.0),
        (-28.0, -25.0, 3.0),
        "03_far_northwest_full_street.png",
        58.0,
    ),
    (
        (50.0, -105.0, 42.0),
        (-28.0, -25.0, 3.0),
        "04_far_southeast_full_street.png",
        58.0,
    ),
    (
        (-98.0, -108.0, 44.0),
        (-28.0, -25.0, 3.0),
        "05_far_southwest_full_street.png",
        60.0,
    ),
    (
        (62.0, -20.0, 30.0),
        (-28.0, -25.0, 3.0),
        "06_far_east_full_street.png",
        56.0,
    ),
    (
        (-112.0, -20.0, 31.0),
        (-28.0, -25.0, 3.0),
        "07_far_west_full_street.png",
        56.0,
    ),
    (
        (-28.0, 62.0, 24.0),
        (-28.0, -23.0, 3.0),
        "08_far_north_frontage_full_street.png",
        46.0,
    ),
]


def configure_cycles(scene: bpy.types.Scene) -> str:
    # Cycles is also used for previews because Eevee needs an EGL context in
    # headless mode on this render host and may fail before producing an image.
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 6 if PREVIEW else 40
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU"
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3

    device_summary = "CPU fallback"
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is not None:
        prefs = addon.preferences
        try:
            prefs.compute_device_type = "CUDA"
            prefs.get_devices()
            enabled = []
            for device in prefs.devices:
                device.use = device.type == "CUDA"
                if device.use:
                    enabled.append(device.name)
            if enabled:
                device_summary = "CUDA: " + ", ".join(enabled)
            else:
                scene.cycles.device = "CPU"
        except Exception as exc:  # Blender builds differ in device backends.
            scene.cycles.device = "CPU"
            device_summary = f"CPU fallback ({exc})"

    scene.render.resolution_x = 800 if PREVIEW else 1600
    scene.render.resolution_y = 450 if PREVIEW else 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.compression = 45 if PREVIEW else 35
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    return device_summary


def render_view(scene, camera, location, target, filename, lens):
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.1
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
    # Prefer passing the Blend on Blender's command line.  Keep this fallback
    # for interactive/script-editor use, where no production file is loaded.
    if Path(bpy.data.filepath).resolve() != SCENE_PATH.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(SCENE_PATH), load_ui=False)
    scene = bpy.context.scene
    camera = bpy.data.objects.get("all43_01:camera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("Expected camera 'all43_01:camera' is missing")

    device = configure_cycles(scene)
    selected = [view for view in VIEWS if not RENDER_ONLY or view[2] in RENDER_ONLY]
    if not selected:
        raise RuntimeError({"unknown_render_selection": sorted(RENDER_ONLY)})

    render_times = {}
    for view in selected:
        print(f"C2W_RENDER_START={view[2]}", flush=True)
        render_times[view[2]] = render_view(scene, camera, *view)
        print(f"C2W_RENDER_DONE={view[2]}:{render_times[view[2]]}", flush=True)

    manifest = {
        "source_blend": str(SCENE_PATH),
        "output_dir": str(OUTPUT_DIR),
        "reference_view": str(
            ROOT
            / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_21"
            / "commercial_inverse_l_overview_1600.png"
        ),
        "reference_camera": {
            "location": list(VIEWS[0][0]),
            "target": list(VIEWS[0][1]),
            "lens_mm": VIEWS[0][3],
        },
        "lighting": "Saved all43 daylight world, warm sun, and cool sky fill; matches reference scene",
        "preview": PREVIEW,
        "engine": scene.render.engine,
        "device": device,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "samples": None if PREVIEW else scene.cycles.samples,
        "renders": [str(OUTPUT_DIR / view[2]) for view in selected],
        "render_times_seconds": render_times,
    }
    manifest_name = "preview_manifest.json" if PREVIEW else "render_manifest.json"
    (OUTPUT_DIR / manifest_name).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("C2W_RENDER_MANIFEST=" + json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
