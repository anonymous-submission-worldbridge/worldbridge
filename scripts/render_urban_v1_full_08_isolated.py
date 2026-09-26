"""Render full08 validation cameras without changing the generated scene.

This is the production recovery stage for dense scenes whose Cycles BVH can
exceed the worker memory limit when every camera is rendered in the generator
process.  Blender opens the same-run final blend read-only; this script never
saves it and skips validation frames that already exist.
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


import os
from pathlib import Path

import bpy


OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/" "outdoor_full_demo/urban_v1_full_08"
)


def configure_cycles() -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type != "CPU"
        scene.cycles.device = "GPU"
    except Exception as exc:
        scene.cycles.device = "CPU"
        print(f"[Full08 isolated render] OPTIX unavailable; CPU fallback: {exc}")
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    # Geometry is identical for every validation camera.  Reuse the read-only
    # Cycles scene/BVH so only the camera transform changes between frames.
    scene.render.use_persistent_data = True


def main() -> None:
    requested = {
        item.strip()
        for item in os.environ.get("C2W_VALIDATION_CAMERAS", "").split(",")
        if item.strip()
    }
    cameras = sorted(
        (
            (obj, obj.name.removeprefix("full:"))
            for obj in bpy.data.objects
            if obj.type == "CAMERA" and obj.name.startswith("full:")
        ),
        key=lambda item: item[1],
    )
    if requested:
        cameras = [item for item in cameras if item[1] in requested]
    if not cameras:
        raise RuntimeError("No matching full08 validation cameras found")

    configure_cycles()
    rendered = 0
    for camera, filename in cameras:
        target = OUT / filename
        if target.exists() and target.stat().st_size > 100_000:
            print(f"[Full08 isolated render] existing: {filename}")
            continue
        bpy.context.scene.camera = camera
        bpy.context.scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        rendered += 1
        print(f"[Full08 isolated render] rendered: {filename}")
    print(f"[Full08 isolated render] complete; new frames={rendered}")


if __name__ == "__main__":
    main()
