#!/usr/bin/env python3
"""Render a diagnostic top view with a selected source-key subset.

This never creates delivery images and exists only to locate pathological
dependency expansion in third-party reference assets.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
RENDERER_PATH = ROOT / "scripts/render_urban_v1_full_12_daytime.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "full12_renderer_diagnostic", RENDERER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise RuntimeError("Expected comma-separated visible source keys")
    visible_keys = {token.strip() for token in args[0].split(",") if token.strip()}
    renderer = load_renderer()
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    scene = bpy.context.scene
    renderer.force_all_regions_visible()
    disabled, names = renderer.disable_hidden_zero_face_geometry_node_controllers()
    kept = []
    hidden = []
    for record in layout["placements"]:
        obj = bpy.data.objects[record["name"]]
        structural = record["collision_class"] in {"base", "road", "road_amenity"}
        show = structural or record["source_key"] in visible_keys
        obj.hide_viewport = not show
        obj.hide_render = not show
        (kept if show else hidden).append(record["placement_id"])
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_simplify = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    camera_data = bpy.data.cameras.new("__full12_diagnostic_camera_data")
    camera = bpy.data.objects.new("__full12_diagnostic_camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    bounds = (
        Vector(layout["city_bounds"]["min"]),
        Vector(layout["city_bounds"]["max"]),
    )
    shot = renderer.Shot(
        name="diagnostic",
        filename="diagnostic.png",
        kind="diagnostic",
        direction=(0.001, -0.001, 1.0),
        margin=1.025,
        projection="ORTHO",
    )
    renderer.fit_camera(camera, bounds, shot, (960, 540))
    label = "_".join(sorted(visible_keys)) or "structural_only"
    target = CITY / "renders/audit" / f"diagnostic_visible_{label}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(target)
    print(
        f"FULL12_DIAGNOSTIC_BEGIN visible_keys={sorted(visible_keys)} "
        f"kept={len(kept)} hidden={len(hidden)} disabled_hidden_controllers={len(names)}",
        flush=True,
    )
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)
    print(
        f"FULL12_DIAGNOSTIC_DONE path={target} bytes={target.stat().st_size}",
        flush=True,
    )


if __name__ == "__main__":
    main()
