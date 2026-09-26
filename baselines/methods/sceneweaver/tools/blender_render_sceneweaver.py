"""Render a SceneWeaver ``.blend`` file to the frozen Table-2 contract.

This script runs inside Blender 4.2.  SceneWeaver stores an overhead inspection
camera but no traversing trajectory, so a deterministic collision-clearance
grid is derived from its exported layout and used for all 50 camera poses.
"""

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
import json
import math
import sys
from collections import deque
from pathlib import Path

import bpy
from mathutils import Vector


ANCHOR_FRAMES = [1, 8, 15, 22, 29, 36, 43, 50]
HORIZONTAL_FOV_DEGREES = 70.0
CAMERA_HEIGHT_METERS = 1.55
COLLISION_CLEARANCE_METERS = 0.3
GRID_STEP_METERS = 0.2
ROOM_MARGIN_METERS = 0.4


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, required=True)
    return parser.parse_args(argv)


def configure_visibility() -> None:
    """Convert SceneWeaver's saved overhead-view visibility to eye level."""
    hide = {
        "placeholders:room_shells",
        "placeholders:portal_cutters",
        "unique_assets:room_ceiling",
        "unique_assets:room_exterior",
        "mark",
    }
    show = {
        "placeholders",
        "placeholders:room_meshes",
        "unique_assets:room_wall",
        "unique_assets:room_floor",
        "unique_assets:windows",
        "unique_assets:doors",
    }
    for collection in bpy.data.collections:
        if collection.name in hide:
            collection.hide_viewport = True
            collection.hide_render = True
        elif collection.name in show:
            collection.hide_viewport = False
            collection.hide_render = False

    # SceneWeaver's recorded refinement scenes keep furniture proxy boxes as
    # direct members of ``placeholders`` and the actual room surface in its
    # ``placeholders:room_meshes`` child.  Hiding the parent collection hides
    # both.  Keep the parent enabled, then hide only its direct proxy objects.
    placeholders = bpy.data.collections.get("placeholders")
    if placeholders is not None:
        for obj in placeholders.objects:
            obj.hide_viewport = True
            obj.hide_render = True
    room_meshes = bpy.data.collections.get("placeholders:room_meshes")
    if room_meshes is not None:
        for obj in room_meshes.objects:
            obj.hide_viewport = False
            obj.hide_render = False
    room_shells = bpy.data.collections.get("placeholders:room_shells")
    if room_shells is not None:
        for obj in room_shells.objects:
            obj.hide_viewport = True
            obj.hide_render = True

    # Populated assets can inherit the visibility used for SceneWeaver's
    # overhead inspection image.  The Table-2 camera must see all of them.
    unique_assets = bpy.data.collections.get("unique_assets")
    if unique_assets is not None:
        for obj in unique_assets.objects:
            obj.hide_viewport = False
            obj.hide_render = False


def configure_cycles() -> str:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    selected = "CPU"
    for backend in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
        except Exception:
            continue
        devices = [device for device in preferences.devices if device.type == backend]
        if devices:
            for device in preferences.devices:
                device.use = device.type == backend
            selected = backend
            break
    if selected == "CPU":
        raise RuntimeError("No CUDA/OPTIX Cycles device is available")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.fps = 10
    scene.view_settings.view_transform = "Standard"
    for look in ("Medium High Contrast", "AgX - Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    return selected


def configure_neutral_lighting(layout: dict) -> None:
    """Install deterministic indoor lighting for SceneWeaver refinement saves.

    The upstream refinement pipeline deliberately turns its construction
    lights off before recording a scene.  Some saved scenes consequently have
    no active emitter and render as uniform black even though their geometry
    and camera trajectory are valid.  Use the same prompt-independent ceiling
    rig for every SceneWeaver item evaluated by this adapter.
    """

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
            obj.hide_viewport = True

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("Table2NeutralWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.8, 0.82, 0.85, 1.0)
        background.inputs["Strength"].default_value = 0.03

    room_values = layout.get("roomsize", [])
    if len(room_values) < 2:
        raise ValueError("SceneWeaver layout has no two-dimensional roomsize")
    width, depth = float(room_values[0]), float(room_values[1])
    light_height = 2.7
    light_size = max(1.0, min(width, depth) * 0.35)
    for index, x_fraction in enumerate((0.3, 0.7), start=1):
        light_data = bpy.data.lights.new(f"Table2CeilingLightData{index}", "AREA")
        light_data.energy = 30.0
        light_data.shape = "DISK"
        light_data.size = light_size
        light_data.color = (1.0, 0.92, 0.82)
        light = bpy.data.objects.new(f"Table2CeilingLight{index}", light_data)
        light.location = (width * x_fraction, depth * 0.5, light_height)
        bpy.context.scene.collection.objects.link(light)


def make_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("Table2CameraData")
    data.sensor_fit = "HORIZONTAL"
    data.angle = math.radians(HORIZONTAL_FOV_DEGREES)
    data.clip_start = 0.05
    data.clip_end = 1000.0
    camera = bpy.data.objects.new("Table2Camera", data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def obstacle_rectangles(layout: dict) -> list[tuple[float, float, float, float]]:
    rectangles = []
    for record in layout.get("objects", {}).values():
        location = [float(value) for value in record.get("location", [0, 0, 0])]
        size = [abs(float(value)) for value in record.get("size", [0, 0, 0])]
        if len(location) < 3 or len(size) < 3:
            continue
        # Ignore high wall decorations that do not obstruct a 1.55 m camera.
        if location[2] >= CAMERA_HEIGHT_METERS or size[2] <= 0.05:
            continue
        rotation = record.get("rotation", [0, 0, 0])
        theta = (
            float(rotation[2])
            if isinstance(rotation, list) and len(rotation) >= 3
            else 0.0
        )
        half_x = 0.5 * (abs(math.cos(theta)) * size[0] + abs(math.sin(theta)) * size[1])
        half_y = 0.5 * (abs(math.sin(theta)) * size[0] + abs(math.cos(theta)) * size[1])
        rectangles.append(
            (
                location[0] - half_x - COLLISION_CLEARANCE_METERS,
                location[0] + half_x + COLLISION_CLEARANCE_METERS,
                location[1] - half_y - COLLISION_CLEARANCE_METERS,
                location[1] + half_y + COLLISION_CLEARANCE_METERS,
            )
        )
    return rectangles


def point_is_free(
    point: tuple[float, float],
    room_size: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
) -> bool:
    x, y = point
    width, depth = room_size
    if not (
        ROOM_MARGIN_METERS <= x <= width - ROOM_MARGIN_METERS
        and ROOM_MARGIN_METERS <= y <= depth - ROOM_MARGIN_METERS
    ):
        return False
    return not any(
        left <= x <= right and bottom <= y <= top
        for left, right, bottom, top in obstacles
    )


def grid_points(
    room_size: tuple[float, float]
) -> dict[tuple[int, int], tuple[float, float]]:
    width, depth = room_size
    count_x = max(
        1, int(math.floor((width - 2 * ROOM_MARGIN_METERS) / GRID_STEP_METERS)) + 1
    )
    count_y = max(
        1, int(math.floor((depth - 2 * ROOM_MARGIN_METERS) / GRID_STEP_METERS)) + 1
    )
    return {
        (ix, iy): (
            ROOM_MARGIN_METERS + ix * GRID_STEP_METERS,
            ROOM_MARGIN_METERS + iy * GRID_STEP_METERS,
        )
        for ix in range(count_x)
        for iy in range(count_y)
    }


def neighbors(
    cell: tuple[int, int], free: set[tuple[int, int]]
) -> list[tuple[int, int]]:
    x, y = cell
    return sorted(
        candidate
        for candidate in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y))
        if candidate in free
    )


def connected_components(free: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    unseen = set(free)
    components = []
    while unseen:
        start = min(unseen)
        component = {start}
        queue = deque([start])
        unseen.remove(start)
        while queue:
            for candidate in neighbors(queue.popleft(), free):
                if candidate in unseen:
                    unseen.remove(candidate)
                    component.add(candidate)
                    queue.append(candidate)
        components.append(component)
    return components


def bfs(
    start: tuple[int, int], component: set[tuple[int, int]]
) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], tuple[int, int]]]:
    distance = {start: 0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for candidate in neighbors(cell, component):
            if candidate not in distance:
                distance[candidate] = distance[cell] + 1
                parent[candidate] = cell
                queue.append(candidate)
    return distance, parent


def segment_is_free(
    start: tuple[float, float],
    end: tuple[float, float],
    room_size: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
) -> bool:
    distance = math.dist(start, end)
    samples = max(2, int(math.ceil(distance / 0.04)))
    for index in range(samples + 1):
        ratio = index / samples
        point = (
            start[0] + ratio * (end[0] - start[0]),
            start[1] + ratio * (end[1] - start[1]),
        )
        if not point_is_free(point, room_size, obstacles):
            return False
    return True


def simplify_path(
    points: list[tuple[float, float]],
    room_size: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    simplified = [points[0]]
    cursor = 0
    while cursor < len(points) - 1:
        next_index = len(points) - 1
        while next_index > cursor + 1 and not segment_is_free(
            points[cursor], points[next_index], room_size, obstacles
        ):
            next_index -= 1
        simplified.append(points[next_index])
        cursor = next_index
    return simplified


def resample_polyline(
    points: list[tuple[float, float]], count: int
) -> list[tuple[float, float]]:
    lengths = [0.0]
    for previous, current in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.dist(previous, current))
    total = lengths[-1]
    if total < 1.0:
        raise RuntimeError(f"SceneWeaver free-space path is too short: {total:.3f} m")
    result = []
    segment = 0
    for index in range(count):
        target = total * index / (count - 1)
        while segment + 1 < len(lengths) - 1 and lengths[segment + 1] < target:
            segment += 1
        span = lengths[segment + 1] - lengths[segment]
        ratio = 0.0 if span == 0 else (target - lengths[segment]) / span
        start, end = points[segment], points[segment + 1]
        result.append(
            (
                start[0] + ratio * (end[0] - start[0]),
                start[1] + ratio * (end[1] - start[1]),
            )
        )
    return result


def plan_path(layout: dict) -> tuple[list[tuple[float, float]], dict]:
    room_values = layout.get("roomsize", [])
    if len(room_values) < 2:
        raise ValueError("SceneWeaver layout has no two-dimensional roomsize")
    room_size = (float(room_values[0]), float(room_values[1]))
    if min(room_size) <= 2 * ROOM_MARGIN_METERS:
        raise ValueError(f"Invalid SceneWeaver room size: {room_size}")
    obstacles = obstacle_rectangles(layout)
    points_by_cell = grid_points(room_size)
    free = {
        cell
        for cell, point in points_by_cell.items()
        if point_is_free(point, room_size, obstacles)
    }
    if not free:
        raise RuntimeError("No free camera grid cell remains after collision clearance")
    component = max(
        connected_components(free), key=lambda value: (len(value), sorted(value))
    )
    first_distances, _ = bfs(min(component), component)
    endpoint_a = max(first_distances, key=lambda cell: (first_distances[cell], cell))
    second_distances, parent = bfs(endpoint_a, component)
    endpoint_b = max(second_distances, key=lambda cell: (second_distances[cell], cell))
    cells = [endpoint_b]
    while cells[-1] != endpoint_a:
        cells.append(parent[cells[-1]])
    cells.reverse()
    raw_points = [points_by_cell[cell] for cell in cells]
    simplified = simplify_path(raw_points, room_size, obstacles)
    poses = resample_polyline(simplified, 50)
    return poses, {
        "room_size_m": list(room_size),
        "obstacle_count": len(obstacles),
        "grid_step_m": GRID_STEP_METERS,
        "free_cell_count": len(free),
        "selected_component_size": len(component),
        "raw_grid_path_points": len(raw_points),
        "simplified_path": [list(point) for point in simplified],
        "path_length_m": sum(math.dist(a, b) for a, b in zip(poses, poses[1:])),
    }


def orient_camera(
    camera: bpy.types.Object,
    path: list[tuple[float, float]],
    index: int,
    room_center: tuple[float, float] | None = None,
) -> None:
    x, y = path[index]
    camera.location = (x, y, CAMERA_HEIGHT_METERS)
    if room_center is None:
        look_index = min(len(path) - 1, index + 3)
        if look_index == index:
            look_index = max(0, index - 3)
        look_x, look_y = path[look_index]
    else:
        look_x, look_y = room_center
        # If a path point is effectively at the room center, use its tangent
        # instead of degenerating to a straight-down view.
        if math.hypot(look_x - x, look_y - y) < 0.5:
            look_index = min(len(path) - 1, index + 3)
            if look_index == index:
                look_index = max(0, index - 3)
            look_x, look_y = path[look_index]
    direction = Vector((look_x - x, look_y - y, -0.35))
    if direction.length < 1e-8:
        raise RuntimeError(f"Degenerate camera direction at frame {index + 1}")
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()


def matrix_rows(matrix) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def intrinsic_matrix(width: int, height: int) -> list[list[float]]:
    focal = 0.5 * width / math.tan(0.5 * math.radians(HORIZONTAL_FOV_DEGREES))
    return [
        [focal, 0.0, width / 2.0],
        [0.0, focal, height / 2.0],
        [0.0, 0.0, 1.0],
    ]


def render_image(path: Path, width: int, height: int, samples: int) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    layout = json.loads((run_dir / "scene/layout.json").read_text(encoding="utf-8"))
    anchors_dir = run_dir / "renders/anchors"
    sequence_dir = run_dir / "renders/sequence"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    sequence_dir.mkdir(parents=True, exist_ok=True)
    # A render-only retry must replace, rather than mix with, an earlier
    # naming/lighting revision.  These are derived artifacts inside this run.
    for render_dir in (anchors_dir, sequence_dir):
        for stale_image in render_dir.glob("rgb_*.png"):
            stale_image.unlink()

    configure_visibility()
    configure_neutral_lighting(layout)
    backend = configure_cycles()
    camera = make_camera()
    path, planner_metadata = plan_path(layout)
    room_center = (
        float(layout["roomsize"][0]) / 2.0,
        float(layout["roomsize"][1]) / 2.0,
    )
    planner_metadata["camera_orientation"] = "look_at_room_center_with_tangent_fallback"
    camera_records = []
    scene = bpy.context.scene
    for index in range(50):
        frame = index + 1
        scene.frame_set(frame)
        orient_camera(camera, path, index, room_center)
        camera_records.append(
            {
                "frame": frame,
                "camera_to_world_blender": matrix_rows(camera.matrix_world),
                "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
                "resolution": [512, 512],
                "K": intrinsic_matrix(512, 512),
            }
        )
        render_image(sequence_dir / f"rgb_{frame:03d}.png", 512, 512, 64)

    anchor_records = []
    for anchor_index, frame in enumerate(ANCHOR_FRAMES):
        scene.frame_set(frame)
        orient_camera(camera, path, frame - 1, room_center)
        output = anchors_dir / f"rgb_{anchor_index:03d}.png"
        render_image(output, 1280, 720, 256)
        anchor_records.append(
            {
                "frame": frame,
                "path": str(output.relative_to(run_dir)),
                "camera_to_world_blender": matrix_rows(camera.matrix_world),
                "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
                "resolution": [1280, 720],
                "K": intrinsic_matrix(1280, 720),
            }
        )

    payload = {
        "coordinate_convention": "Blender world; camera local -Z forward, local +Y up",
        "camera_pose_contract": {
            "algorithm": "deterministic_free_space_grid_v1",
            "camera_height_m": CAMERA_HEIGHT_METERS,
            "collision_clearance_m": COLLISION_CLEARANCE_METERS,
            "remove_roll_with_global_up": True,
        },
        "render": {
            "engine": "cycles",
            "device": backend.lower(),
            "sequence_samples": 64,
            "anchor_samples": 256,
            "denoise": True,
        },
        "path_planner": planner_metadata,
        "sequence": camera_records,
        "anchors": anchor_records,
    }
    (sequence_dir / "cameras.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"SCENEWEAVER_RENDER_COMPLETE backend={backend} "
        f"path_length_m={planner_metadata['path_length_m']:.3f}"
    )


if __name__ == "__main__":
    main()
