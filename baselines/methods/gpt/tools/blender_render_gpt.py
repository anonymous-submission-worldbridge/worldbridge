"""Build and render Astra-generated Blender scenes using fixed Table-2 settings."""
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
from collections import deque
import faulthandler
import json
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Vector
import numpy as np

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import check_code

sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.sceneweaver.tools.blender_render_sceneweaver import (
    configure_cycles,
)
from baselines.methods.sceneweaver.tools.blender_render_sceneweaver import make_camera
from baselines.methods.sceneweaver.tools.blender_render_sceneweaver import render_image
from baselines.methods.sceneweaver.tools.blender_render_sceneweaver import (
    intrinsic_matrix,
)
from baselines.methods.sceneweaver.tools.blender_render_sceneweaver import matrix_rows
from baselines.methods.gpt.tools.gpt_camera import corner_preserving_resample


def boxes():
    output = []
    for obj in bpy.context.scene.objects:
        if (
            obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
            or obj.hide_render
        ):
            continue
        pts = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        output.append({"name": obj.name, "min": lo, "max": hi})
    return output


def build(run, spec, seed):
    # Periodic read-only stack snapshots distinguish slow Python operators
    # from a hung process. They do not alter generated geometry or materials.
    faulthandler.dump_traceback_later(300, repeat=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    random.seed(seed)
    np.random.seed(seed)
    code = (run / "scene/generated.py").read_text()
    check_code(code)
    namespace = {"__name__": "astra_scene"}
    exec(compile(code, "generated.py", "exec"), namespace)
    namespace["build_scene"](seed)
    bpy.context.view_layer.update()
    if not any(o.type == "MESH" for o in bpy.context.scene.objects):
        raise ValueError("Generated scene has no mesh geometry")
    for obj in bpy.context.scene.objects:
        if obj.animation_data:
            raise ValueError("Generated scene contains animation")
        if obj.type in {"LIGHT", "CAMERA"}:
            raise ValueError(
                "Generated scene contains lights/cameras contrary to frozen interface"
            )
    (run / "scene/geometry.json").write_text(json.dumps(boxes(), indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(run / "scene/scene.blend"), compress=True)
    faulthandler.cancel_dump_traceback_later()


def plan_path(spec, geometry):
    indoor = spec["domain"] == "indoor"
    width, depth, _ = spec["extent_m"]
    # Indoor uses the room interior; urban uses the central 60 m square ROI.
    halfx = width / 2 - 0.4 if indoor else min(width / 2 - 1, 30)
    halfy = depth / 2 - 0.4 if indoor else min(depth / 2 - 1, 30)
    step = 0.2 if indoor else 0.5
    height = 1.55 if indoor else 1.65
    obstacles = []
    for obj in geometry:
        lo, hi = obj["min"], obj["max"]
        if hi[2] <= 0.2 or lo[2] >= height + 0.2:
            continue
        obstacles.append((lo[0] - 0.3, hi[0] + 0.3, lo[1] - 0.3, hi[1] + 0.3))
    points = {
        (ix, iy): (-halfx + ix * step, -halfy + iy * step)
        for ix in range(int(2 * halfx / step) + 1)
        for iy in range(int(2 * halfy / step) + 1)
    }

    def free(point):
        x, y = point
        return not any(a <= x <= b and c <= y <= d for a, b, c, d in obstacles)

    free_cells = {cell for cell, p in points.items() if free(p)}
    if not free_cells:
        raise ValueError("No traversable camera cells")

    def neighbors(cell):
        x, y = cell
        return [
            p
            for p in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y))
            if p in free_cells
        ]

    def bfs(start):
        dist, parent = {start: 0}, {}
        queue = deque([start])
        while queue:
            p = queue.popleft()
            for q in neighbors(p):
                if q not in dist:
                    dist[q], parent[q] = dist[p] + 1, p
                    queue.append(q)
        return dist, parent

    # Select the component containing the reachable cell nearest ROI center.
    center = min(free_cells, key=lambda c: (math.hypot(*points[c]), c))
    dist, _ = bfs(center)
    a = max(dist, key=lambda c: (dist[c], c))
    dist, parents = bfs(a)
    b = max(dist, key=lambda c: (dist[c], c))
    cells = [b]
    while cells[-1] != a:
        cells.append(parents[cells[-1]])
    raw = [points[c] for c in reversed(cells)]
    # Preserve grid clearance through corners. Limit trajectory to one room
    # long side or 42 m urban, selecting the segment nearest the region center.
    target = max(width, depth) if indoor else 42.0
    required = 0.8 * max(width, depth) if indoor else 35.0
    if (len(raw) - 1) * step < required:
        raise ValueError(
            "Traversable path too short for the preregistered domain trajectory"
        )
    steps = min(len(raw) - 1, int(target / step))
    offset = min(
        range(len(raw) - steps), key=lambda i: (math.hypot(*raw[i + steps // 2]), i)
    )
    raw = raw[offset : offset + steps + 1]
    poses = corner_preserving_resample(raw, count=50)
    # Verify interpolated segments as well as grid nodes to prevent corner cuts.
    for p, q in zip(poses, poses[1:]):
        for t in np.linspace(0, 1, max(3, math.ceil(math.dist(p, q) / 0.025))):
            if not free((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))):
                raise ValueError("Resampled path cuts an obstacle clearance corner")
    displacement = max(math.dist(p, q) for p in poses for q in poses)
    if displacement < 0.5:
        raise ValueError("Insufficient camera displacement")
    # Fit the fixed 75-degree sweep to ALL center-facing directions. Using
    # only endpoint angles loses the winding direction on a curved trajectory.
    desired = np.unwrap([math.atan2(-y, -x) for x, y in poses])
    progress = np.linspace(0, 1, 50)
    slope = float(np.polyfit(progress, desired, 1)[0])
    turn = math.copysign(math.radians(75), slope or 1)
    start_yaw = float(np.mean(desired - turn * progress))
    return (
        poses,
        start_yaw,
        turn,
        {
            "algorithm": "center_component_grid_diameter_corner_preserving_v2",
            "path_length_m": sum(math.dist(p, q) for p, q in zip(poses, poses[1:])),
            "max_displacement_m": displacement,
            "clearance_m": 0.3,
            "grid_step_m": step,
            "height_m": height,
            "yaw_turn_degrees": math.degrees(turn),
            "obstacle_count": len(obstacles),
            "collision_model": "world-space per-object axis-aligned bounding boxes",
            "orientation": "least-squares fixed 75-degree sweep fitted to unwrapped center-facing angles",
            "raw_polyline": raw,
        },
    )


def light_scene(spec):
    world = bpy.data.worlds.new("Table2World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.8, 0.82, 0.85, 1)
    indoor = spec["domain"] == "indoor"
    bg.inputs["Strength"].default_value = 0.03 if indoor else 0.5
    width, depth, height = spec["extent_m"]
    if indoor:
        for i, fraction in enumerate((-0.2, 0.2)):
            data = bpy.data.lights.new(f"Table2Ceiling{i}", "AREA")
            data.energy = 30
            data.shape = "DISK"
            data.size = max(1, min(width, depth) * 0.35)
            data.color = (1, 0.92, 0.82)
            obj = bpy.data.objects.new(data.name, data)
            obj.location = (width * fraction, 0, height - 0.3)
            bpy.context.scene.collection.objects.link(obj)
    else:
        data = bpy.data.lights.new("Table2Sun", "SUN")
        data.energy = 3
        data.angle = math.radians(5)
        obj = bpy.data.objects.new("Table2Sun", data)
        obj.rotation_euler = (math.radians(25), math.radians(-20), math.radians(-30))
        bpy.context.scene.collection.objects.link(obj)


def render(run, spec, seed):
    poses, yaw, turn, metadata = plan_path(
        spec, json.loads((run / "scene/geometry.json").read_text())
    )
    light_scene(spec)
    backend = configure_cycles()
    bpy.context.scene.cycles.seed = seed
    camera = make_camera()
    sequence, anchors = [], []
    for kind, count, resolution, samples in [
        ("sequence", 50, (512, 512), 64),
        ("anchors", 8, (1280, 720), 256),
    ]:
        output = run / "renders" / kind
        output.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            index = i if kind == "sequence" else [0, 7, 14, 21, 28, 35, 42, 49][i]
            x, y = poses[index]
            angle = yaw + turn * index / 49
            camera.location = (x, y, metadata["height_m"])
            direction = Vector((math.cos(angle), math.sin(angle), -0.12))
            camera.rotation_mode = "QUATERNION"
            camera.rotation_quaternion = direction.to_track_quat("-Z", "Y")
            bpy.context.view_layer.update()
            frame = index + 1
            path = output / f'rgb_{frame if kind == "sequence" else i:03d}.png'
            render_image(path, *resolution, samples)
            record = {
                "frame": frame,
                "path": str(path.relative_to(run)),
                "camera_to_world_blender": matrix_rows(camera.matrix_world),
                "world_to_camera_blender": matrix_rows(camera.matrix_world.inverted()),
                "resolution": list(resolution),
                "horizontal_fov_degrees": 70,
                "K": intrinsic_matrix(*resolution),
            }
            (sequence if kind == "sequence" else anchors).append(record)
    payload = {
        "coordinate_convention": "Blender world meters; camera -Z forward, +Y up",
        "path_planner": metadata,
        "sequence": sequence,
        "anchors": anchors,
        "render": {
            "engine": "cycles",
            "device": backend,
            "sequence_samples": 64,
            "anchor_samples": 256,
        },
    }
    (run / "renders/sequence/cameras.json").write_text(json.dumps(payload, indent=2))
    print("ASTRA_RENDER_COMPLETE", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=["build", "render"], required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(ROOT):
        raise ValueError("Run directory escapes baselines")
    spec = json.loads((run / "input/spec.json").read_text())
    seed = json.loads((run / "run_manifest.json").read_text())["logical_seed"]
    if args.phase == "build":
        build(run, spec, seed)
        print("ASTRA_BUILD_COMPLETE", flush=True)
    else:
        render(run, spec, seed)


if __name__ == "__main__":
    main()
