#!/usr/bin/env python3
"""Render a corrected unobstructed view from an opened refined Blender scene."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

    scene = bpy.context.scene
    camera = scene.camera or bpy.data.objects.get("ConnectDemoCamera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("Scene camera is unavailable")

    position = Vector((-2.60, 6.10, 2.10))
    target = Vector((0.0, -5.40, 1.25))
    horizontal_fov = 74.0
    camera.data.sensor_width = 36.0
    camera.data.lens = 36.0 / (2.0 * math.tan(math.radians(horizontal_fov) / 2.0))
    camera.data.clip_start = 0.05
    camera.data.clip_end = 200.0
    camera.location = position
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = (target - position).to_track_quat("-Z", "Y")

    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 35
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.75
    scene.view_settings.gamma = 1.0

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output)
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)
    print(f"REFINED_CORRECTION_COMPLETE {output}", flush=True)


if __name__ == "__main__":
    main()
