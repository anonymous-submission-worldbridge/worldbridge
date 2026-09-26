#!/usr/bin/env python3
"""Bright, multi-view renderer for refined Gemini connect2 demos."""
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


import math
from pathlib import Path
import sys

import bpy


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))
import baselines.methods.gemini.tools.render_gemini_connect as renderer  # noqa: E402


renderer.OUTPUT = (BASELINES / "annotations/gemini_3_1_pro/connect2").resolve()
renderer.LOWER_LIMITS = (-22.0, -36.0, -2.0)
renderer.UPPER_LIMITS = (22.0, 14.0, 12.5)
renderer.VIDEO_FRAME_COUNT = 48
base_build_scene = renderer.build_scene
base_configure_render = renderer.configure_render
base_set_quality = renderer.set_quality
base_render_stills = renderer.render_stills
renderer.STILL_VIEWS = [
    ((0.0, 7.2, 1.78), (0.0, 0.8, 1.25), "interior_wide_axis"),
    ((-5.15, 6.35, 1.90), (-1.4, 1.3, 1.22), "interior_far_left"),
    ((5.15, 6.35, 1.90), (1.4, 1.3, 1.22), "interior_far_right"),
    ((-4.75, 3.25, 1.78), (-2.2, 0.8, 1.12), "interior_mid_left"),
    ((4.75, 3.25, 1.78), (2.2, 0.8, 1.12), "interior_mid_right"),
    ((-4.35, 1.2, 1.60), (-3.2, 0.0, 1.05), "interior_detail_left"),
    ((4.35, 1.2, 1.60), (3.2, 0.0, 1.05), "interior_detail_right"),
    ((0.0, 4.25, 1.72), (0.0, -7.5, 1.25), "inside_to_outside_far"),
    ((0.0, 0.55, 1.67), (0.0, -9.2, 1.22), "inside_to_outside_mid"),
    ((-1.0, -2.65, 1.68), (0.0, -6.2, 1.22), "threshold_inside_oblique"),
    ((0.0, -17.0, 2.85), (0.0, -4.7, 1.40), "exterior_establishing_front"),
    ((-8.5, -16.0, 4.60), (0.0, -5.5, 1.35), "exterior_far_left"),
    ((8.5, -16.0, 4.60), (0.0, -5.5, 1.35), "exterior_far_right"),
    ((-5.0, -11.5, 2.60), (0.0, -5.0, 1.25), "exterior_mid_left"),
    ((5.0, -11.5, 2.60), (0.0, -5.0, 1.25), "exterior_mid_right"),
    ((0.0, -13.0, 1.78), (0.0, 1.8, 1.28), "outside_to_inside_far"),
    ((0.0, -8.0, 1.68), (0.0, 1.2, 1.28), "outside_to_inside_mid"),
    ((1.0, -6.2, 1.70), (0.0, -2.8, 1.24), "threshold_outside_oblique"),
]


def build_scene(run: Path, manifest: dict) -> dict:
    generated = run / "source/generated.py"
    if generated.stat().st_size < 18_000:
        raise RuntimeError(
            f"Refined source is too short for the requested detail: {generated.stat().st_size} bytes"
        )
    geometry = base_build_scene(run, manifest)
    source_vertices = geometry["vertices"]
    source_polygons = geometry["polygons"]
    refined_objects = 0
    meshes = [
        item
        for item in bpy.context.scene.objects
        if item.type == "MESH" and not item.hide_render
    ]
    preexisting_modifier_objects = sum(bool(obj.modifiers) for obj in meshes)
    candidates = sorted(
        (
            obj
            for obj in meshes
            if not any(modifier.type == "BEVEL" for modifier in obj.modifiers)
        ),
        key=lambda obj: abs(obj.dimensions.x * obj.dimensions.y * obj.dimensions.z),
        reverse=True,
    )[:400]
    for obj in candidates:
        polygon_count = len(obj.data.polygons)
        minimum_dimension = min(abs(value) for value in obj.dimensions)
        if polygon_count < 6 or polygon_count > 500 or minimum_dimension < 0.015:
            continue
        modifier = obj.modifiers.new("Connect2EdgeRefinement", "BEVEL")
        modifier.width = max(0.004, min(0.03, minimum_dimension * 0.04))
        modifier.segments = 3 if polygon_count <= 50 else 2
        modifier.limit_method = "ANGLE"
        refined_objects += 1
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.convert(target="MESH")
    bpy.context.view_layer.update()
    meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
    ]
    geometry["vertices"] = sum(len(obj.data.vertices) for obj in meshes)
    geometry["polygons"] = sum(len(obj.data.polygons) for obj in meshes)
    geometry["standardized_edge_refinement"] = {
        "method": "baked Gemini modifier geometry plus angle-limited 2-3 segment bevels where absent",
        "gemini_modifier_objects_baked": preexisting_modifier_objects,
        "objects_refined": refined_objects,
        "source_vertices": source_vertices,
        "source_polygons": source_polygons,
        "is_image_postprocess": False,
    }
    if geometry["visible_mesh_objects"] < 250:
        raise RuntimeError(
            f"Refined scene has too few mesh objects: {geometry['visible_mesh_objects']}"
        )
    if geometry["polygons"] < 60_000:
        raise RuntimeError(
            f"Refined scene has too few polygons: {geometry['polygons']}"
        )
    geometry["connect2_quality_gate"] = {
        "minimum_source_bytes": 18000,
        "minimum_visible_mesh_objects": 250,
        "minimum_polygons": 60000,
        "passed": True,
    }
    return geometry


def add_lighting() -> None:
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("Connect2BrightWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.72, 0.82, 1.0, 1.0)
    background.inputs["Strength"].default_value = 0.45

    sun_data = bpy.data.lights.new("Connect2SunData", "SUN")
    sun_data.energy = 2.8
    sun_data.angle = math.radians(8.0)
    sun = bpy.data.objects.new("Connect2Sun", sun_data)
    sun.rotation_euler = (math.radians(27.0), math.radians(-22.0), math.radians(-38.0))
    bpy.context.scene.collection.objects.link(sun)

    interior_lights = [
        (-3.6, 5.4, 3.0),
        (0.0, 5.4, 3.0),
        (3.6, 5.4, 3.0),
        (-3.6, 1.5, 3.0),
        (0.0, 1.5, 3.0),
        (3.6, 1.5, 3.0),
        (-3.6, -2.2, 3.0),
        (3.6, -2.2, 3.0),
    ]
    for index, location in enumerate(interior_lights):
        data = bpy.data.lights.new(f"Connect2InteriorFillData{index}", "AREA")
        data.energy = 520.0
        data.shape = "DISK"
        data.size = 2.7
        data.color = (1.0, 0.88, 0.74)
        obj = bpy.data.objects.new(f"Connect2InteriorFill{index}", data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)

    for index, x in enumerate((-6.5, 6.5)):
        data = bpy.data.lights.new(f"Connect2ExteriorFillData{index}", "AREA")
        data.energy = 700.0
        data.shape = "DISK"
        data.size = 5.0
        data.color = (0.78, 0.88, 1.0)
        obj = bpy.data.objects.new(f"Connect2ExteriorFill{index}", data)
        obj.location = (x, -9.0, 6.5)
        bpy.context.scene.collection.objects.link(obj)


def configure_render(seed: int) -> dict:
    backend = base_configure_render(seed)
    scene = bpy.context.scene
    scene.view_settings.exposure = 0.45
    return backend


def set_quality(video: bool) -> None:
    base_set_quality(video)
    scene = bpy.context.scene
    if scene.render.engine == "BLENDER_EEVEE_NEXT":
        scene.eevee.taa_render_samples = 2 if video else 20


def render_stills(run: Path, camera: bpy.types.Object) -> list[dict]:
    """Invalidate stale stills after camera or geometric-refinement revisions."""
    revision_marker = run / "images/.connect2_view_revision_4"
    if not revision_marker.is_file():
        for _position, _target, role in renderer.STILL_VIEWS:
            (run / "images" / f"{role}.png").unlink(missing_ok=True)
    records = base_render_stills(run, camera)
    revision_marker.write_text("4\n", encoding="utf-8")
    return records


renderer.build_scene = build_scene
renderer.add_lighting = add_lighting
renderer.configure_render = configure_render
renderer.set_quality = set_quality
renderer.render_stills = render_stills


if __name__ == "__main__":
    raise SystemExit(renderer.main())
