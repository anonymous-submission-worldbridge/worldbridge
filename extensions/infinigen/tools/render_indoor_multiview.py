#!/usr/bin/env python3
"""Render balanced multi-view images for every room in an Infinigen home.

Run this with the Python environment that provides bpy.  The source scene is
not modified: cameras and fill lights are temporary and no .blend is saved.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

# Direct script execution makes Python use tools/ as sys.path[0]. Add the
# repository root so the sibling ``infinigen`` package is always importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
import numpy as np
from imageio.v3 import imread
from mathutils import Vector

from infinigen.core import init


PRIMARY_ROOM_TYPES = {"bedroom", "living-room", "kitchen", "bathroom"}
ROOM_RE = re.compile(r"^(?P<kind>[a-z-]+)_\d+/\d+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views-per-room", type=int, default=3)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--source-label")
    parser.add_argument("--room-limit", type=int, default=0)
    parser.add_argument("--view-limit", type=int, default=0)
    parser.add_argument("--repair-manifest", type=Path)
    parser.add_argument("--repair-file")
    parser.add_argument("--repair-attempts", type=int, default=8)
    return parser.parse_args()


def atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def world_vertices(obj: bpy.types.Object) -> np.ndarray:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world
        return np.asarray([tuple(matrix @ v.co) for v in mesh.vertices], dtype=float)
    finally:
        evaluated.to_mesh_clear()


def room_floors() -> list[tuple[str, str, bpy.types.Object]]:
    collection = bpy.data.collections.get("unique_assets:room_floor")
    objects = list(collection.objects) if collection else list(bpy.data.objects)
    rooms = []
    for obj in objects:
        if obj.type != "MESH" or not obj.name.endswith(".floor"):
            continue
        room_name = obj.name[: -len(".floor")]
        match = ROOM_RE.match(room_name)
        if not match:
            continue
        rooms.append((match.group("kind"), room_name, obj))
    rooms.sort(key=lambda item: (item[0] not in PRIMARY_ROOM_TYPES, item[0], item[1]))
    return rooms


def point_in_polygon(point: tuple[float, float], polygon: np.ndarray) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i, :2]
        xj, yj = polygon[j, :2]
        crosses = (yi > y) != (yj > y)
        if crosses and x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def floor_polygons(obj: bpy.types.Object) -> list[np.ndarray]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world
        coords = [np.asarray(tuple(matrix @ v.co), dtype=float) for v in mesh.vertices]
        return [np.asarray([coords[i] for i in poly.vertices]) for poly in mesh.polygons]
    finally:
        evaluated.to_mesh_clear()


def horizontal_clearance(position: Vector, max_distance: float = 1.5) -> float:
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    distances = []
    for angle in np.linspace(0.0, 2.0 * math.pi, 12, endpoint=False):
        direction = Vector((math.cos(angle), math.sin(angle), 0.0))
        hit, location, *_ = scene.ray_cast(
            depsgraph, position, direction, distance=max_distance
        )
        distances.append((location - position).length if hit else max_distance)
    return min(distances)


def choose_positions(
    floor_obj: bpy.types.Object, views: int
) -> tuple[list[Vector], Vector, dict]:
    vertices = world_vertices(floor_obj)
    polygons = floor_polygons(floor_obj)
    lower = vertices.min(axis=0)
    upper = vertices.max(axis=0)
    floor_z = float(np.median(vertices[:, 2]))
    fractions = np.linspace(0.16, 0.84, 7)
    candidates = []
    for fx in fractions:
        for fy in fractions:
            x = float(lower[0] + fx * (upper[0] - lower[0]))
            y = float(lower[1] + fy * (upper[1] - lower[1]))
            if not any(point_in_polygon((x, y), polygon) for polygon in polygons):
                continue
            position = Vector((x, y, floor_z + 1.52))
            clearance = horizontal_clearance(position)
            candidates.append((clearance, position))

    if not candidates:
        center = Vector(
            (
                float((lower[0] + upper[0]) / 2),
                float((lower[1] + upper[1]) / 2),
                floor_z + 1.52,
            )
        )
        candidates = [(0.0, center)]

    candidates.sort(key=lambda item: item[0], reverse=True)
    center_xy = np.asarray([(lower[0] + upper[0]) / 2, (lower[1] + upper[1]) / 2])
    preferred = [
        np.asarray([lower[0], lower[1]]),
        np.asarray([upper[0], upper[1]]),
        np.asarray([lower[0], upper[1]]),
        np.asarray([upper[0], lower[1]]),
    ]
    selected: list[Vector] = []
    usable = [item for item in candidates if item[0] >= 0.28] or candidates
    min_separation = max(0.75, min(upper[0] - lower[0], upper[1] - lower[1]) * 0.28)
    for desired in preferred:
        ranked = sorted(
            usable,
            key=lambda item: np.linalg.norm(np.asarray(item[1][:2]) - desired)
            - 0.35 * item[0],
        )
        for _, position in ranked:
            if all((position - prior).length >= min_separation for prior in selected):
                selected.append(position.copy())
                break
        if len(selected) >= views:
            break
    for _, position in usable:
        if len(selected) >= views:
            break
        if all((position - prior).length >= min_separation * 0.65 for prior in selected):
            selected.append(position.copy())
    while len(selected) < views:
        selected.append(usable[len(selected) % len(usable)][1].copy())

    target = Vector((float(center_xy[0]), float(center_xy[1]), floor_z + 1.08))
    bbox = {
        "min": [round(float(v), 4) for v in lower],
        "max": [round(float(v), 4) for v in upper],
    }
    return selected[:views], target, bbox


def room_ceiling_z(room_name: str, fallback: float) -> float:
    ceiling = bpy.data.objects.get(f"{room_name}.ceiling")
    if ceiling is None:
        return fallback
    vertices = world_vertices(ceiling)
    return float(np.max(vertices[:, 2])) if len(vertices) else fallback


def add_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("BatchRoomCameraData")
    data.sensor_width = 36.0
    data.lens = 22.0
    camera = bpy.data.objects.new("BatchRoomCamera", data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def add_fill_light(name: str, center: Vector, ceiling_z: float, area: float) -> bpy.types.Object:
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = float(np.clip(220.0 + area * 10.0, 280.0, 620.0))
    data.shape = "DISK"
    data.size = float(np.clip(math.sqrt(max(area, 1.0)) * 0.42, 1.5, 4.0))
    data.color = (1.0, 0.88, 0.74)
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = (center.x, center.y, ceiling_z - 0.18)
    light.rotation_euler = (0.0, 0.0, 0.0)
    return light


def configure_render(width: int, height: int, samples: int) -> list[dict]:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    devices = init.configure_cycles_devices()
    if scene.cycles.device != "GPU":
        raise RuntimeError("Cycles did not select a GPU")
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    scene.cycles.adaptive_min_samples = min(16, samples)
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.film_exposure = 1.0
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    for look in ("AgX - Medium High Contrast", "AgX - Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            pass
    return [
        {"name": device.name, "type": device.type}
        for device in (devices or [])
        if device.use
    ]


def image_stats(path: Path) -> dict:
    image = imread(path)
    rgb = image[..., :3].astype(np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    return {
        "mean_luminance": round(float(luminance.mean()), 5),
        "median_luminance": round(float(np.median(luminance)), 5),
        "p05_luminance": round(float(np.quantile(luminance, 0.05)), 5),
        "p95_luminance": round(float(np.quantile(luminance, 0.95)), 5),
        "dark_fraction": round(float(np.mean(luminance < 0.025)), 5),
        "bright_fraction": round(float(np.mean(luminance > 0.985)), 5),
    }


def render_balanced(path: Path) -> tuple[dict, float, int]:
    scene = bpy.context.scene
    # Native indoor scenes use a generous film exposure.  Start one stop lower
    # because the temporary ceiling fill is deliberately broad and neutral.
    exposure = -1.0
    rerenders = 0
    stats = {}
    for attempt in range(3):
        scene.view_settings.exposure = exposure
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        stats = image_stats(path)
        mean = stats["mean_luminance"]
        median = stats["median_luminance"]
        bright = stats["bright_fraction"]
        delta = 0.0
        if mean < 0.16 or median < 0.08:
            delta = float(np.clip(math.log2(0.26 / max(mean, 0.025)), 0.45, 1.5))
        elif mean > 0.58 or bright > 0.10:
            delta = float(np.clip(math.log2(0.43 / max(mean, 0.01)), -1.5, -0.35))
        if delta == 0.0 or attempt == 2:
            break
        exposure += delta
        rerenders += 1
    return stats, round(exposure, 4), rerenders


def repair_view(args: argparse.Namespace) -> None:
    manifest_path = args.repair_manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    room_record = next(
        (
            room
            for room in manifest["rooms"]
            if any(view["file"] == args.repair_file for view in room["views"])
        ),
        None,
    )
    if room_record is None:
        raise RuntimeError(f"View is not present in manifest: {args.repair_file}")
    view_record = next(
        view for view in room_record["views"] if view["file"] == args.repair_file
    )

    bpy.ops.wm.open_mainfile(filepath=str(args.scene))
    manifest["gpu_devices"] = configure_render(
        manifest["resolution"][0], manifest["resolution"][1], manifest["samples"]
    )
    room_entry = next(
        (entry for entry in room_floors() if entry[1] == room_record["room_name"]),
        None,
    )
    if room_entry is None:
        raise RuntimeError(f"Room floor was not found: {room_record['room_name']}")
    _, room_name, floor_obj = room_entry
    positions, target, bbox = choose_positions(
        floor_obj, max(args.repair_attempts + len(room_record["views"]), 12)
    )
    used = [Vector(view["camera_location"]) for view in room_record["views"]]
    alternatives = [
        position
        for position in positions
        if all((position - prior).length >= 0.55 for prior in used)
    ]
    if not alternatives:
        alternatives = positions

    width = bbox["max"][0] - bbox["min"][0]
    depth = bbox["max"][1] - bbox["min"][1]
    area = max(width * depth, 1.0)
    ceiling_z = room_ceiling_z(room_name, bbox["min"][2] + 2.7)
    light = add_fill_light("BatchRepairFill", target, ceiling_z, area)
    camera = add_camera()
    camera.data.lens = float(view_record.get("lens_mm", 23.0))
    camera.data.dof.use_dof = False
    output_path = args.output / args.repair_file
    repair_path = output_path.with_name(f"{output_path.stem}.repair{output_path.suffix}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    attempts = []
    try:
        for attempt, position in enumerate(alternatives[: args.repair_attempts], start=1):
            # A slightly higher eye line further reduces the chance of landing
            # inside a sofa or tall-backed chair while preserving a natural view.
            position = position.copy()
            position.z += 0.16
            camera.location = position
            camera.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
            started = time.time()
            stats, exposure, rerenders = render_balanced(repair_path)
            attempt_record = {
                "attempt": attempt,
                "camera_location": [round(float(v), 4) for v in position],
                "mean_luminance": stats["mean_luminance"],
                "dark_fraction": stats["dark_fraction"],
            }
            attempts.append(attempt_record)
            print(f"[repair] {args.repair_file} {attempt_record}", flush=True)
            if (
                stats["mean_luminance"] >= 0.16
                and stats["dark_fraction"] <= 0.45
                and stats["bright_fraction"] <= 0.10
            ):
                repair_path.replace(output_path)
                view_record.update(
                    {
                        "camera_location": [round(float(v), 4) for v in position],
                        "camera_target": [round(float(v), 4) for v in target],
                        "lens_mm": camera.data.lens,
                        "exposure_adjustment": exposure,
                        "rerenders": rerenders,
                        "seconds": round(time.time() - started, 2),
                        "repaired": True,
                        "repair_attempt": attempt,
                        **stats,
                    }
                )
                manifest.setdefault("repairs", []).append(
                    {
                        "file": args.repair_file,
                        "reason": "occluded_or_too_dark",
                        "attempts": attempts,
                    }
                )
                manifest["status"] = "complete"
                atomic_json(manifest_path, manifest)
                print(
                    f"[repair-complete] {args.repair_file} "
                    f"mean={stats['mean_luminance']} dark={stats['dark_fraction']}",
                    flush=True,
                )
                return
        raise RuntimeError(
            f"No unoccluded repair camera found after {len(attempts)} attempts"
        )
    finally:
        repair_path.unlink(missing_ok=True)
        bpy.data.objects.remove(light, do_unlink=True)


def main() -> None:
    args = parse_args()
    args.scene = args.scene.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if bool(args.repair_manifest) != bool(args.repair_file):
        raise ValueError("--repair-manifest and --repair-file must be used together")
    if args.repair_manifest:
        repair_view(args)
        return
    manifest_path = args.output / "manifest.json"
    started = time.time()
    manifest = {
        "status": "loading",
        "source_blend": args.source_label or str(args.scene),
        "resolution": [args.width, args.height],
        "samples": args.samples,
        "views_per_room": args.views_per_room,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "rooms": [],
    }
    atomic_json(manifest_path, manifest)
    bpy.ops.wm.open_mainfile(filepath=str(args.scene))
    manifest["gpu_devices"] = configure_render(args.width, args.height, args.samples)
    rooms = room_floors()
    if args.room_limit:
        rooms = rooms[: args.room_limit]
    if not rooms:
        raise RuntimeError("No Infinigen room floor meshes were found")
    found_primary = {kind for kind, _, _ in rooms} & PRIMARY_ROOM_TYPES
    if not args.room_limit and found_primary != PRIMARY_ROOM_TYPES:
        missing = sorted(PRIMARY_ROOM_TYPES - found_primary)
        raise RuntimeError(f"Missing required room types: {missing}")

    camera = add_camera()
    manifest["status"] = "rendering"
    manifest["room_count"] = len(rooms)
    atomic_json(manifest_path, manifest)

    for room_index, (kind, room_name, floor_obj) in enumerate(rooms, start=1):
        positions, target, bbox = choose_positions(floor_obj, args.views_per_room)
        if args.view_limit:
            positions = positions[: args.view_limit]
        width = bbox["max"][0] - bbox["min"][0]
        depth = bbox["max"][1] - bbox["min"][1]
        area = max(width * depth, 1.0)
        ceiling_z = room_ceiling_z(room_name, bbox["min"][2] + 2.7)
        light = add_fill_light(
            f"BatchFill_{room_index:02d}", target, ceiling_z, area
        )
        room_dir = args.output / re.sub(r"[^a-zA-Z0-9_-]+", "_", room_name)
        room_dir.mkdir(parents=True, exist_ok=True)
        room_record = {
            "room_name": room_name,
            "room_type": kind,
            "bbox": bbox,
            "fill_light_watts": round(float(light.data.energy), 2),
            "views": [],
        }
        manifest["rooms"].append(room_record)
        atomic_json(manifest_path, manifest)

        for view_index, position in enumerate(positions, start=1):
            camera.location = position
            camera.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
            camera.data.lens = 20.0 if min(width, depth) < 4.2 else 23.0
            camera.data.dof.use_dof = False
            output_path = room_dir / f"view_{view_index:02d}.png"
            print(
                f"[render] room={room_name} view={view_index}/{len(positions)} "
                f"gpu={os.environ.get('CUDA_VISIBLE_DEVICES')} path={output_path}",
                flush=True,
            )
            view_started = time.time()
            stats, exposure, rerenders = render_balanced(output_path)
            room_record["views"].append(
                {
                    "file": str(output_path.relative_to(args.output)),
                    "camera_location": [round(float(v), 4) for v in position],
                    "camera_target": [round(float(v), 4) for v in target],
                    "lens_mm": camera.data.lens,
                    "exposure_adjustment": exposure,
                    "rerenders": rerenders,
                    "seconds": round(time.time() - view_started, 2),
                    **stats,
                }
            )
            atomic_json(manifest_path, manifest)
        bpy.data.objects.remove(light, do_unlink=True)

    manifest["status"] = "complete"
    manifest["elapsed_seconds"] = round(time.time() - started, 2)
    manifest["total_images"] = sum(len(room["views"]) for room in manifest["rooms"])
    manifest["required_room_types"] = sorted(PRIMARY_ROOM_TYPES)
    manifest["present_room_types"] = sorted({room["room_type"] for room in manifest["rooms"]})
    atomic_json(manifest_path, manifest)
    print(
        f"[complete] rooms={manifest['room_count']} images={manifest['total_images']} "
        f"seconds={manifest['elapsed_seconds']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
