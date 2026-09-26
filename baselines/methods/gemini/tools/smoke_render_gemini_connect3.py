#!/usr/bin/env python3
"""Low-resolution visual-audit views from an already built connect3 blend."""
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
from pathlib import Path
import sys

import bpy


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = (BASELINES / "annotations/gemini_3_1_pro/connect3").resolve()
sys.path.insert(0, str(BASELINES / "tools"))
import baselines.methods.gemini.tools.render_gemini_connect as renderer  # noqa: E402


VIEWS = [
    ((0.0, 9.1, 1.82), (0.0, 2.8, 1.25), "interior_wide_axis"),
    ((0.0, -24.5, 2.70), (0.0, 3.8, 1.35), "outside_to_inside_far"),
    ((-42.0, -42.0, 28.0), (0.0, -1.0, 2.4), "district_aerial_southwest"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(ROOT):
        raise ValueError("Run escapes connect3 root")
    camera = next(
        (obj for obj in bpy.context.scene.objects if obj.type == "CAMERA"), None
    )
    if camera is None:
        camera = renderer.make_camera()
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.exposure = 0.60
    for obj in scene.objects:
        if obj.type == "LIGHT" and obj.data.type == "AREA":
            obj.data.use_shadow = False
        if obj.type == "LIGHT" and obj.data.type == "SUN":
            obj.data.angle = 0.0174533
    output = Path("/tmp/gemini_connect3_visual_audit") / run.name
    output.mkdir(parents=True, exist_ok=True)
    for position, target, role in VIEWS:
        renderer.point_camera(camera, position, target)
        scene.render.filepath = str(output / f"{role}.png")
        bpy.ops.render.render(write_still=True)
        print(f"GEMINI_CONNECT3_SMOKE_COMPLETE {run.name} {role}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
