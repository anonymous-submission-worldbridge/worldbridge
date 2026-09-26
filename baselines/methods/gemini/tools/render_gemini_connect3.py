#!/usr/bin/env python3
"""Build and brightly render Gemini connect3 compact multi-building districts."""
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


import hashlib
import math
from pathlib import Path
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))
import baselines.methods.gemini.tools.render_gemini_connect as renderer  # noqa: E402


renderer.OUTPUT = (BASELINES / "annotations/gemini_3_1_pro/connect3").resolve()
renderer.LOWER_LIMITS = (-35.1, -35.1, -2.1)
renderer.UPPER_LIMITS = (35.1, 35.1, 21.1)
renderer.VIDEO_FRAME_COUNT = 48
renderer.VIDEO_DIRECTIONS = [
    "indoor_to_outdoor",
    "outdoor_to_indoor",
    "neighborhood_orbit",
]
renderer.STILL_VIEWS = [
    ((0.0, 9.1, 1.82), (0.0, 2.8, 1.25), "interior_wide_axis"),
    ((-0.9, 10.2, 1.95), (-3.4, 1.5, 1.23), "interior_far_left"),
    ((0.9, 10.2, 1.95), (3.4, 1.5, 1.23), "interior_far_right"),
    ((-1.1, 6.2, 1.76), (-3.0, -1.5, 1.16), "interior_mid_left"),
    ((1.1, 6.2, 1.76), (3.0, -1.5, 1.16), "interior_mid_right"),
    ((0.0, 7.3, 1.74), (0.0, -12.5, 1.30), "inside_to_outside_far"),
    ((0.0, 2.5, 1.70), (0.0, -15.5, 1.25), "inside_to_outside_mid"),
    ((-1.2, -0.15, 1.67), (0.2, -8.0, 1.20), "threshold_inside_oblique"),
    ((0.0, -24.5, 2.70), (0.0, 3.8, 1.35), "outside_to_inside_far"),
    ((0.0, -11.5, 1.74), (0.0, 3.7, 1.28), "outside_to_inside_mid"),
    ((1.25, -2.45, 1.68), (-0.1, 2.8, 1.24), "threshold_outside_oblique"),
    ((0.0, -29.0, 5.2), (0.0, -4.0, 2.0), "neighborhood_front_axis"),
    ((-24.0, -42.0, 9.0), (-8.0, -4.0, 2.6), "streetscape_far_left"),
    ((24.0, -42.0, 9.0), (8.0, -4.0, 2.6), "streetscape_far_right"),
    ((-8.0, -42.0, 8.0), (-18.0, -6.0, 2.0), "cross_street_from_west"),
    ((8.0, -42.0, 8.0), (18.0, -6.0, 2.0), "cross_street_from_east"),
    ((-42.0, -42.0, 28.0), (0.0, -1.0, 2.4), "district_aerial_southwest"),
    ((42.0, -42.0, 28.0), (0.0, -1.0, 2.4), "district_aerial_southeast"),
    ((-40.0, 34.0, 24.0), (-1.0, 1.0, 2.5), "district_oblique_northwest"),
    ((40.0, 34.0, 24.0), (1.0, 1.0, 2.5), "district_oblique_northeast"),
    ((-15.0, -39.0, 5.0), (-8.0, -7.0, 1.45), "public_realm_left"),
    ((15.0, -39.0, 5.0), (8.0, -7.0, 1.45), "public_realm_right"),
]

base_build_scene = renderer.build_scene
base_configure_render = renderer.configure_render
base_set_quality = renderer.set_quality
base_render_stills = renderer.render_stills


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_scene(run: Path, manifest: dict) -> dict:
    generated = run / "source/generated.py"
    if generated.stat().st_size < 10_000:
        raise RuntimeError(
            f"Neighborhood source is too short for the requested density: {generated.stat().st_size} bytes"
        )
    geometry = base_build_scene(run, manifest)
    source_vertices = geometry["vertices"]
    source_polygons = geometry["polygons"]
    meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
    ]

    centers = {
        obj.name: sum(
            (obj.matrix_world @ Vector(corner) for corner in obj.bound_box), Vector()
        )
        / 8.0
        for obj in meshes
    }
    zone_counts = {
        "anchor": sum(
            -8.0 <= point.x <= 8.0 and -2.0 <= point.y <= 13.0
            for point in centers.values()
        ),
        "west": sum(point.x < -8.0 for point in centers.values()),
        "east": sum(point.x > 8.0 for point in centers.values()),
        "north": sum(point.y > 13.0 for point in centers.values()),
        "public_realm": sum(-23.0 <= point.y < -2.0 for point in centers.values()),
    }
    occupied_context_zones = sum(
        zone_counts[name] >= 8 for name in ("west", "east", "north")
    )
    if occupied_context_zones < 2:
        raise RuntimeError(
            f"Neighborhood does not occupy enough separate building zones: {zone_counts}"
        )
    if zone_counts["public_realm"] < 35:
        raise RuntimeError(f"Public realm is too sparse: {zone_counts}")

    preexisting_modifier_objects = sum(bool(obj.modifiers) for obj in meshes)
    upgraded_gemini_bevels = 0
    for obj in meshes:
        for modifier in obj.modifiers:
            if modifier.type == "BEVEL" and modifier.segments < 4:
                modifier.segments = 4
                upgraded_gemini_bevels += 1
    refined_objects = 0
    candidates = sorted(
        (
            obj
            for obj in meshes
            if not any(mod.type == "BEVEL" for mod in obj.modifiers)
        ),
        key=lambda obj: abs(obj.dimensions.x * obj.dimensions.y * obj.dimensions.z),
        reverse=True,
    )[:650]
    for obj in candidates:
        polygon_count = len(obj.data.polygons)
        minimum_dimension = min(abs(value) for value in obj.dimensions)
        if polygon_count < 6 or polygon_count > 800 or minimum_dimension < 0.012:
            continue
        modifier = obj.modifiers.new("Connect3EdgeRefinement", "BEVEL")
        modifier.width = max(0.003, min(0.035, minimum_dimension * 0.035))
        modifier.segments = 5 if polygon_count <= 80 else 3
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
    geometry["spatial_zone_mesh_counts"] = zone_counts
    geometry["occupied_context_building_zones"] = occupied_context_zones
    geometry["standardized_edge_refinement"] = {
        "method": "baked Gemini modifier geometry plus angle-limited bevels standardized to as many as four segments",
        "gemini_modifier_objects_baked": preexisting_modifier_objects,
        "gemini_bevel_modifiers_upgraded_to_four_segments": upgraded_gemini_bevels,
        "objects_refined": refined_objects,
        "source_vertices": source_vertices,
        "source_polygons": source_polygons,
        "is_image_postprocess": False,
    }
    if geometry["visible_mesh_objects"] < 350:
        raise RuntimeError(
            f"Neighborhood has too few visible mesh objects: {geometry['visible_mesh_objects']}"
        )
    if geometry["polygons"] < 90_000:
        raise RuntimeError(f"Neighborhood has too few polygons: {geometry['polygons']}")
    geometry["connect3_quality_gate"] = {
        "minimum_source_bytes": 10_000,
        "minimum_visible_mesh_objects": 350,
        "minimum_baked_polygons": 90_000,
        "minimum_occupied_context_zones": 2,
        "minimum_public_realm_objects": 35,
        "passed": True,
    }
    return geometry


def add_lighting() -> None:
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("Connect3BrightWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.72, 0.84, 1.0, 1.0)
    background.inputs["Strength"].default_value = 0.52

    sun_data = bpy.data.lights.new("Connect3SunData", "SUN")
    sun_data.energy = 3.1
    sun_data.angle = math.radians(1.0)
    sun = bpy.data.objects.new("Connect3Sun", sun_data)
    sun.rotation_euler = (math.radians(29.0), math.radians(-24.0), math.radians(-38.0))
    bpy.context.scene.collection.objects.link(sun)

    interior = [
        (-4.0, 7.4, 3.3),
        (0.0, 7.4, 3.3),
        (4.0, 7.4, 3.3),
        (-4.0, 3.0, 3.3),
        (0.0, 3.0, 3.3),
        (4.0, 3.0, 3.3),
    ]
    for index, location in enumerate(interior):
        data = bpy.data.lights.new(f"Connect3InteriorFillData{index}", "AREA")
        data.energy = 620.0
        data.shape = "DISK"
        data.size = 1.2
        data.use_shadow = False
        data.color = (1.0, 0.90, 0.78)
        obj = bpy.data.objects.new(f"Connect3InteriorFill{index}", data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)

    for index, location in enumerate(
        ((-15.0, -10.0, 11.0), (15.0, -10.0, 11.0), (0.0, 17.0, 12.0))
    ):
        data = bpy.data.lights.new(f"Connect3DistrictFillData{index}", "AREA")
        data.energy = 900.0
        data.shape = "DISK"
        data.size = 2.0
        data.use_shadow = False
        data.color = (0.78, 0.88, 1.0)
        obj = bpy.data.objects.new(f"Connect3DistrictFill{index}", data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)


def configure_render(seed: int) -> dict:
    backend = base_configure_render(seed)
    scene = bpy.context.scene
    scene.view_settings.exposure = 0.60
    return backend


def set_quality(video: bool) -> None:
    base_set_quality(video)
    scene = bpy.context.scene
    if scene.render.engine == "BLENDER_EEVEE_NEXT":
        scene.eevee.taa_render_samples = 4 if video else 32
    elif scene.render.engine == "CYCLES":
        scene.cycles.samples = 16 if video else 48


def render_stills(run: Path, camera: bpy.types.Object) -> list[dict]:
    revision = "6" if run.name == "garden_residential_microdistrict" else "5"
    revision_marker = run / f"images/.connect3_view_revision_{revision}"
    if not revision_marker.is_file():
        for _position, _target, role in renderer.STILL_VIEWS:
            (run / "images" / f"{role}.png").unlink(missing_ok=True)
    records = base_render_stills(run, camera)
    revision_marker.write_text(revision + "\n", encoding="utf-8")
    return records


def render_video(run: Path, camera: bpy.types.Object, direction: str) -> dict:
    if direction not in renderer.VIDEO_DIRECTIONS:
        raise ValueError(direction)
    scene = bpy.context.scene
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    set_quality(video=True)
    videos = run / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    video = videos / f"{direction}.mp4"
    revision_marker = videos / f".connect3_video_revision_2_{direction}"
    if not revision_marker.is_file():
        video.unlink(missing_ok=True)
    if video.is_file() and video.stat().st_size > 10_000:
        print(f"GEMINI_CONNECT3_VIDEO_REUSED {run.name} {direction}", flush=True)
        return {
            "path": str(video.relative_to(run)),
            "role": direction,
            "sha256": _sha256(video),
            "bytes": video.stat().st_size,
            "resolution": [960, 540],
            "fps": 24,
            "frames": renderer.VIDEO_FRAME_COUNT,
            "duration_seconds": renderer.VIDEO_FRAME_COUNT / 24.0,
            "camera_path": "existing verified compact-district traversal",
        }

    frames_root = run / ".render_frames"
    frames = frames_root / direction
    if frames_root.exists():
        shutil.rmtree(frames_root)
    frames.mkdir(parents=True)
    try:
        for frame in range(1, renderer.VIDEO_FRAME_COUNT + 1):
            progress = (frame - 1) / (renderer.VIDEO_FRAME_COUNT - 1)
            eased = progress * progress * (3.0 - 2.0 * progress)
            if direction == "indoor_to_outdoor":
                y = 8.0 + (-25.0 - 8.0) * eased
                position = (
                    0.18 * math.sin(math.pi * progress),
                    y,
                    1.68 + 0.05 * math.sin(math.pi * progress),
                )
                turn = max(0.0, min(1.0, (progress - 0.22) / 0.78))
                turn = turn * turn * (3.0 - 2.0 * turn)
                side = -10.0 if sum(run.name.encode("utf-8")) % 2 else 10.0
                forward = (0.25 * math.sin(math.pi * progress), y - 5.0, 1.28)
                overview = (side, -2.0, 3.0)
                target = tuple(
                    (1.0 - turn) * a + turn * b for a, b in zip(forward, overview)
                )
                description = "continuous step-free path from furnished anchor interior through the open portal into the district"
            elif direction == "outdoor_to_indoor":
                y = -25.0 + (8.0 + 25.0) * eased
                position = (
                    -0.18 * math.sin(math.pi * progress),
                    y,
                    1.68 + 0.05 * math.sin(math.pi * progress),
                )
                turn = max(0.0, min(1.0, (progress - 0.72) / 0.28))
                turn = turn * turn * (3.0 - 2.0 * turn)
                side = -3.2 if sum(run.name.encode("utf-8")) % 2 else 3.2
                forward = (-0.25 * math.sin(math.pi * progress), y + 5.0, 1.28)
                interior = (side, 5.0, 1.25)
                target = tuple(
                    (1.0 - turn) * a + turn * b for a, b in zip(forward, interior)
                )
                description = "continuous step-free path from the public street through the open portal into the furnished interior"
            else:
                angle = math.radians(225.0 - 270.0 * eased)
                radius = 52.0 - 4.0 * math.sin(math.pi * progress)
                position = (
                    radius * math.cos(angle),
                    -2.0 + radius * math.sin(angle),
                    20.0 + 6.0 * math.sin(math.pi * progress),
                )
                target = (0.0, -2.0, 2.4)
                description = "wide oblique orbit revealing the compact multi-building neighborhood and public realm"
            renderer.point_camera(camera, position, target)
            scene.frame_set(frame)
            path = frames / f"frame_{frame:04d}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if frame == 1 or frame % 24 == 0 or frame == renderer.VIDEO_FRAME_COUNT:
                print(
                    f"GEMINI_CONNECT3_VIDEO_FRAME {run.name} {direction} {frame}/{renderer.VIDEO_FRAME_COUNT}",
                    flush=True,
                )
        command = [
            "/usr/bin/ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video),
        ]
        subprocess.run(command, check=True)
        revision_marker.write_text("2\n", encoding="utf-8")
        return {
            "path": str(video.relative_to(run)),
            "role": direction,
            "sha256": _sha256(video),
            "bytes": video.stat().st_size,
            "resolution": [960, 540],
            "fps": 24,
            "frames": renderer.VIDEO_FRAME_COUNT,
            "duration_seconds": renderer.VIDEO_FRAME_COUNT / 24.0,
            "camera_path": description,
        }
    finally:
        if frames_root.exists():
            shutil.rmtree(frames_root)


renderer.build_scene = build_scene
renderer.add_lighting = add_lighting
renderer.configure_render = configure_render
renderer.set_quality = set_quality
renderer.render_stills = render_stills
renderer.render_video = render_video


if __name__ == "__main__":
    raise SystemExit(renderer.main())
