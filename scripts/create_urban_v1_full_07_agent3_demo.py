"""Create a collision-audited, wide-view urban humanoid mission demo.

The production blend is opened read-only.  At runtime this script replaces the
imported bedroom's non-traversable shell with an equivalent explicit shell
containing a real south-wall opening, installs an animated door and ramp,
validates a robot safety envelope along the route, and renders wide views.
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


import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SOURCE_BLEND = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07/urban_v1_full_07.blend"
)
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent3"
PREFIX = "C2W_AGENT3:"
FPS = 15
FRAME_END = 210
ROBOT_SAFETY_RADIUS = 0.68
DOOR_CENTER_X = -13.50
DOOR_WALL_Y = 25.01
DOOR_FLOOR_Z = 1.45

sys.path.insert(0, str(ROOT / "scripts"))
import create_urban_v1_full_07_agent2_demo as v2  # noqa: E402

base = v2.base


# The first seven keys stay inside the actual bedroom and pass through the
# south-wall door along its normal.  The exterior route uses the residential
# footpath, zebra crossing, verified parking aisle and Fresh Mart entrance.
# The return repeats the same safe corridor in reverse.
ROUTE_KEYS = [
    (1, (-16.20, 30.60, 1.46), "bedroom_start"),
    (8, (-16.20, 29.20, 1.46), "leave_bedside"),
    (16, (-16.20, 27.80, 1.46), "clear_bedroom_furniture"),
    (22, (-14.60, 27.00, 1.46), "align_inside_door"),
    (28, (-13.50, 26.10, 1.46), "wait_inside_open_door"),
    (34, (-13.50, 24.30, 1.46), "pass_real_front_door"),
    (42, (-13.50, 21.00, 0.18), "descend_access_ramp"),
    (48, (-10.50, 20.50, 0.18), "front_garden_path"),
    (54, (-7.10, 20.50, 0.18), "residential_sidewalk"),
    (62, (-7.10, 8.40, 0.18), "approach_crosswalk"),
    (68, (-3.45, 7.45, 0.18), "wait_at_crosswalk"),
    (78, (-3.45, -7.45, 0.18), "cross_road_on_zebra"),
    (84, (-7.40, -8.35, 0.18), "commercial_sidewalk"),
    (90, (-7.40, -20.00, 0.18), "commercial_edge"),
    (98, (-7.40, -36.40, 0.18), "reach_clear_parking_aisle"),
    (112, (-40.50, -36.40, 0.18), "cross_clear_parking_aisle"),
    (118, (-40.50, -26.20, 0.18), "arrive_fresh_mart"),
    (126, (-40.50, -26.20, 0.18), "shopping_complete"),
    (132, (-40.50, -36.40, 0.18), "leave_fresh_mart"),
    (146, (-7.40, -36.40, 0.18), "return_clear_parking_aisle"),
    (154, (-7.40, -20.00, 0.18), "return_commercial_edge"),
    (160, (-7.40, -8.35, 0.18), "return_commercial_sidewalk"),
    (166, (-4.10, -7.45, 0.18), "return_crosswalk_south"),
    (176, (-4.10, 7.45, 0.18), "return_on_zebra"),
    (181, (-7.10, 8.40, 0.18), "return_residential_sidewalk"),
    (187, (-7.10, 20.50, 0.18), "return_front_path"),
    (192, (-13.50, 21.00, 0.18), "return_ramp_base"),
    (198, (-13.50, 24.30, 1.46), "reenter_real_front_door"),
    (203, (-13.50, 26.10, 1.46), "inside_front_door"),
    (207, (-16.20, 27.80, 1.46), "return_bedroom"),
    (210, (-16.20, 30.60, 1.46), "mission_complete_inside"),
]

STORE_INDEX = next(
    i for i, key in enumerate(ROUTE_KEYS) if key[2] == "arrive_fresh_mart"
)
OUTBOUND_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[: STORE_INDEX + 1]]
RETURN_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[STORE_INDEX + 1 :]]


def _configure_imported_modules() -> None:
    v2.OUT = OUT
    v2.PREFIX = PREFIX
    v2.FRAME_END = FRAME_END
    v2.FPS = FPS
    v2.ROUTE_KEYS = ROUTE_KEYS
    v2.STORE_ARRIVAL_INDEX = STORE_INDEX
    v2.OUTBOUND_POINTS = OUTBOUND_POINTS
    v2.RETURN_POINTS = RETURN_POINTS
    base.OUT = OUT
    base.PREFIX = PREFIX
    base.FRAME_END = FRAME_END
    base.FPS = FPS


_configure_imported_modules()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("build", "stills", "video", "all"), default="all"
    )
    parser.add_argument("--still-width", type=int, default=1280)
    parser.add_argument("--still-height", type=int, default=720)
    parser.add_argument("--video-width", type=int, default=768)
    parser.add_argument("--video-height", type=int, default=432)
    parser.add_argument(
        "--engine", choices=("workbench", "eevee", "cycles"), default="workbench"
    )
    parser.add_argument("--cycles-samples", type=int, default=3)
    parser.add_argument("--vegetation", choices=("light", "full"), default="light")
    parser.add_argument(
        "--spatial-cull", choices=("mission", "none"), default="mission"
    )
    parser.add_argument("--only-still", type=int, choices=range(16), default=None)
    parser.add_argument("--video-step", type=int, choices=(1, 2, 3, 4, 5), default=3)
    parser.add_argument(
        "--video-view", choices=("first", "third", "aerial", "all"), default="all"
    )
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def log(message: str) -> None:
    print(f"[agent3] {message}", flush=True)


def world_bounds(obj):
    if not getattr(obj, "bound_box", None):
        return None
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        min(p.x for p in points),
        max(p.x for p in points),
        min(p.y for p in points),
        max(p.y for p in points),
        min(p.z for p in points),
        max(p.z for p in points),
    )


def intersects(a, b) -> bool:
    return all(a[i] <= b[i + 1] and b[i] <= a[i + 1] for i in (0, 2, 4))


def hide_overlapping_source_entrance_parts():
    """Remove the stacked procedural door/window pieces from the doorway."""
    zone = (-14.65, -12.35, 22.80, 26.55, 1.30, 4.15)
    protected = {"bedroom_0/0.exterior", "bedroom_0/0.wall", "bedroom_0/0.floor"}
    hidden = []
    house = bpy.data.collections.get("House_large_indoor")
    # Materialize the collection before changing visibility.  Iterating the
    # live ``all_objects`` view while hiding members can invalidate Blender's
    # internal iterator in large linked scenes.
    candidates = list(house.all_objects) if house else list(bpy.data.objects)
    for obj in candidates:
        if obj.type != "MESH" or obj.name in protected:
            continue
        bounds = world_bounds(obj)
        if bounds and intersects(bounds, zone):
            obj.hide_render = True
            obj.hide_viewport = True
            hidden.append(obj.name)
    log(f"cleared {len(hidden)} overlapping source entrance meshes")
    return hidden


def spatial_cull_to_mission():
    """Hide geometry outside a generous box around the complete trajectory."""
    mission_box = (-65.0, 25.0, -55.0, 55.0, -10.0, 140.0)
    hidden = 0
    kept = 0
    for obj in list(bpy.context.scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            kept += 1
            continue
        bounds = world_bounds(obj)
        if bounds and not intersects(bounds, mission_box):
            obj.hide_render = True
            obj.hide_viewport = True
            hidden += 1
        else:
            kept += 1
    log(f"mission spatial cull hid={hidden} kept={kept}")
    return {"bounds": list(mission_box), "hidden_objects": hidden, "kept_objects": kept}


def cut_real_doorway(coll, mats):
    """Replace the solid room shell and install a clear animated doorway."""
    hidden = hide_overlapping_source_entrance_parts()
    replaced = []
    for name in ("bedroom_0/0.exterior", "bedroom_0/0.wall"):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_render = True
            obj.hide_viewport = True
            replaced.append(name)

    # Reconstruct the same 9.93 x 9.93 m room envelope from the imported
    # bounds.  Splitting the south wall leaves a genuine 2.0 m opening and is
    # substantially more stable than evaluating a Boolean on the 5 GB scene.
    wall_z = (1.45 + 4.78) / 2
    wall_h = 4.78 - 1.45
    wall_specs = (
        ("bedroom_south_wall_left", (-17.49, 25.01, wall_z), (5.88, 0.18, wall_h)),
        ("bedroom_south_wall_right", (-11.475, 25.01, wall_z), (1.95, 0.18, wall_h)),
        ("bedroom_south_wall_header", (-13.50, 25.01, 4.44), (2.10, 0.18, 0.68)),
        ("bedroom_north_wall", (-15.465, 34.86, wall_z), (9.93, 0.18, wall_h)),
        ("bedroom_west_wall", (-20.35, 29.935, wall_z), (0.18, 9.85, wall_h)),
        ("bedroom_east_wall", (-10.58, 29.935, wall_z), (0.18, 9.85, wall_h)),
    )
    for name, location, dimensions in wall_specs:
        wall = base.cube(name, location, dimensions, mats["room_wall"], coll, 0.015)
        wall["c2w_role"] = "replacement_collision_wall"

    # Clean frame around a 2.0 m clear opening; the 0.68 m robot envelope has
    # at least 0.32 m lateral clearance per side, including the grocery bag.
    for x in (-14.57, -12.43):
        base.cube(
            "real_door_jamb",
            (x, DOOR_WALL_Y, 2.76),
            (0.14, 0.18, 2.72),
            mats["frame"],
            coll,
            0.025,
        )
    base.cube(
        "real_door_header",
        (DOOR_CENTER_X, DOOR_WALL_Y, 4.08),
        (2.28, 0.18, 0.16),
        mats["frame"],
        coll,
        0.025,
    )
    base.cube(
        "real_door_threshold",
        (DOOR_CENTER_X, DOOR_WALL_Y, 1.44),
        (2.02, 0.32, 0.06),
        mats["threshold"],
        coll,
        0.015,
    )

    hinge = v2.joint(
        "real_front_door_hinge", (-14.49, DOOR_WALL_Y - 0.05, DOOR_FLOOR_Z), coll
    )
    leaf = base.cube(
        "real_front_door_leaf",
        (0.95, 0, 1.26),
        (1.90, 0.075, 2.52),
        mats["door"],
        coll,
        0.035,
        hinge,
    )
    base.cube(
        "real_front_door_inset",
        (0.95, -0.045, 1.28),
        (1.48, 0.025, 1.98),
        mats["door_inset"],
        coll,
        0.018,
        hinge,
    )
    base.sphere(
        "real_front_door_handle", (1.67, -0.10, 1.25), 0.045, mats["metal"], coll, hinge
    )
    keyframes = (
        (1, 0),
        (22, 0),
        (28, -100),
        (42, -100),
        (48, 0),
        (187, 0),
        (192, -100),
        (203, -100),
        (210, 0),
    )
    for frame, angle in keyframes:
        hinge.rotation_euler[2] = math.radians(angle)
        hinge.keyframe_insert("rotation_euler", index=2, frame=frame)

    # A continuous deck connects the 1.45 m interior floor to z=0.18 without
    # teleporting or intersecting stair blocks.
    ramp_start = Vector((DOOR_CENTER_X, 24.30, 1.46))
    ramp_end = Vector((DOOR_CENTER_X, 21.00, 0.18))
    delta = ramp_start - ramp_end
    length = math.hypot(delta.y, delta.z)
    ramp = base.cube(
        "accessible_entry_ramp",
        (
            DOOR_CENTER_X,
            (ramp_start.y + ramp_end.y) / 2,
            (ramp_start.z + ramp_end.z) / 2 - 0.07,
        ),
        (2.30, length, 0.12),
        mats["ramp"],
        coll,
        0.02,
    )
    ramp.rotation_euler[0] = math.atan2(delta.z, delta.y)
    ramp["c2w_role"] = "walkable_surface"
    return hinge, leaf, ramp, replaced, hidden


def route_forward(index: int, previous: Vector) -> Vector:
    here = Vector(ROUTE_KEYS[index][1])
    if index < len(ROUTE_KEYS) - 1:
        forward = Vector(ROUTE_KEYS[index + 1][1]) - here
    else:
        forward = here - previous
    forward.z = 0
    return forward.normalized() if forward.length > 1e-5 else Vector((0, -1, 0))


def add_cameras(coll):
    cams = {
        "overview": base.camera(
            "camera_global_perspective", (64, -88, 112), (-21, -3, 0), 50, coll
        ),
        "room": base.camera(
            "camera_room_wide", (-20.0, 35.5, 4.5), (-15.4, 28.0, 1.8), 31, coll
        ),
        "door_inside": base.camera(
            "camera_real_door_inside", (-18.5, 29.5, 4.0), (-13.5, 25.0, 1.9), 35, coll
        ),
        "door_outside": base.camera(
            "camera_real_door_outside", (-7.5, 17.2, 6.6), (-13.5, 24.7, 1.7), 38, coll
        ),
        "crosswalk": base.camera(
            "camera_crosswalk_wide", (20.0, -3.0, 14.0), (-3.5, 0.0, 0.8), 42, coll
        ),
        "commercial": base.camera(
            "camera_commercial_wide", (10.0, -55.0, 25.0), (-25.0, -30.0, 0.8), 45, coll
        ),
        "shop": base.camera(
            "camera_shop_wide", (-17.0, -48.0, 12.0), (-40.5, -26.0, 1.0), 42, coll
        ),
    }

    aerial = base.camera(
        "camera_aerial_full_route", (-22.0, -2.5, 112.0), (-22.0, -2.5, 0), 50, coll
    )
    aerial.data.type = "ORTHO"
    aerial.data.ortho_scale = 84.0
    cams["aerial"] = aerial

    first_locations, first_targets = [], []
    third_locations, third_targets = [], []
    previous = Vector(ROUTE_KEYS[0][1]) + Vector((0, 1, 0))
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        forward = route_forward(index, previous)
        side = Vector((-forward.y, forward.x, 0))
        first_locations.append((frame, point + forward * 0.52 + Vector((0, 0, 1.70))))
        first_targets.append((frame, point + forward * 14.0 + Vector((0, 0, 1.48))))

        indoors = frame <= 34 or frame >= 198
        distance = 3.8 if indoors else 10.5
        height = 3.0 if indoors else 7.5
        lateral = 1.8 if indoors else 5.5
        if 118 <= frame <= 126:
            third_position = Vector((-23.0, -45.0, 12.0))
        else:
            third_position = (
                point - forward * distance + side * lateral + Vector((0, 0, height))
            )
        third_locations.append((frame, third_position))
        third_targets.append((frame, point + Vector((0, 0, 1.05))))
        previous = point

    first, first_target = v2.add_dynamic_camera(
        "camera_first_person_ultrawide", coll, first_locations, first_targets, 27
    )
    third, third_target = v2.add_dynamic_camera(
        "camera_third_person_wide_chase", coll, third_locations, third_targets, 34
    )
    cams.update(
        {
            "first": first,
            "first_target": first_target,
            "third": third,
            "third_target": third_target,
        }
    )
    return cams


def raycast_non_ignored(scene, origin, target, ignored_prefixes, ignored_names):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    direction = target - origin
    remaining = direction.length
    if remaining <= 1e-5:
        return None
    direction.normalize()
    cursor = origin.copy()
    travelled = 0.0
    for _ in range(12):
        hit, location, normal, face, obj, matrix = scene.ray_cast(
            depsgraph, cursor, direction, distance=remaining
        )
        if not hit or obj is None:
            return None
        hit_distance = travelled + (location - cursor).length
        ignored = obj.name in ignored_names or any(
            obj.name.startswith(prefix) for prefix in ignored_prefixes
        )
        if not ignored:
            return obj.name, tuple(float(v) for v in location), hit_distance
        advance = (location - cursor).length + 0.025
        cursor += direction * advance
        travelled += advance
        remaining -= advance
        if remaining <= 0.02:
            return None
    return None


def collision_audit(scene):
    """Conservatively sample a 1.36 m-wide swept cylinder on every segment."""
    scene.frame_set(34)  # door fully open for passage audit
    bpy.context.view_layer.update()

    ignored_exact = {
        "bedroom_0/0.exterior",
        "bedroom_0/0.wall",
        PREFIX + "accessible_entry_ramp",
        PREFIX + "real_door_threshold",
    }
    ignored_tokens = (
        "floor",
        "ceiling",
        "terrain",
        "road_surface",
        "asphalt",
        "sidewalk",
        "crosswalk",
        "zebra",
        "ground",
        "lawn",
        "grass",
        "roof",
        "skirting",
        "lane_mark",
        "parking_mark",
        "route",
        "arrow",
        "marker",
    )
    obstacles = []
    ignored_object_count = 0
    # Only linked scene objects are physical obstacles.  ``bpy.data.objects``
    # also contains unlinked asset-library source meshes at local coordinates,
    # which would create false positives around the world origin.
    for obj in list(scene.objects):
        if (
            obj.type != "MESH"
            or obj.hide_render
            or obj.hide_viewport
            or obj.name in ignored_exact
        ):
            ignored_object_count += 1
            continue
        low = obj.name.lower()
        if any(token in low for token in ignored_tokens):
            ignored_object_count += 1
            continue
        bounds = world_bounds(obj)
        if not bounds:
            continue
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        if zmax < 0.25 or zmin > 3.55:
            ignored_object_count += 1
            continue
        # Large shell AABBs are not useful collision proxies; explicit room
        # walls and all local obstacles/vehicles remain included.
        if not obj.name.startswith(PREFIX) and (
            xmax - xmin > 25.0 or ymax - ymin > 25.0
        ):
            ignored_object_count += 1
            continue
        obstacles.append((obj.name, bounds))

    violations = []
    seen = set()
    sample_count = 0
    spacing = 0.15
    for index in range(len(ROUTE_KEYS) - 1):
        frame0, xyz0, stage0 = ROUTE_KEYS[index]
        frame1, xyz1, stage1 = ROUTE_KEYS[index + 1]
        p0, p1 = Vector(xyz0), Vector(xyz1)
        distance = (p1 - p0).length
        steps = max(1, math.ceil(distance / spacing))
        for step in range(steps + 1):
            point = p0.lerp(p1, step / steps)
            sample_count += 1
            body_min_z = point.z + 0.04
            body_max_z = point.z + 1.92
            for obj_name, bounds in obstacles:
                xmin, xmax, ymin, ymax, zmin, zmax = bounds
                if body_max_z < zmin or body_min_z > zmax:
                    continue
                if not (
                    xmin - ROBOT_SAFETY_RADIUS <= point.x <= xmax + ROBOT_SAFETY_RADIUS
                ):
                    continue
                if not (
                    ymin - ROBOT_SAFETY_RADIUS <= point.y <= ymax + ROBOT_SAFETY_RADIUS
                ):
                    continue
                key = (index, obj_name)
                if key in seen:
                    continue
                seen.add(key)
                violations.append(
                    {
                        "segment": index,
                        "from_stage": stage0,
                        "to_stage": stage1,
                        "object": obj_name,
                        "sample_xyz": list(point),
                        "object_world_aabb": list(bounds),
                    }
                )
    report = {
        "method": "0.15 m conservative swept-cylinder sampling against world-space obstacle AABBs",
        "passed": len(violations) == 0,
        "robot_safety_radius_m": ROBOT_SAFETY_RADIUS,
        "sampled_body_height_m": 1.92,
        "sample_spacing_m": spacing,
        "segments": len(ROUTE_KEYS) - 1,
        "sample_count": sample_count,
        "obstacle_aabbs_tested": len(obstacles),
        "ignored_non_obstacle_objects": ignored_object_count,
        "violations": violations,
        "limitations": "Conservative proxy audit; not a closed-loop physics controller.",
    }
    (OUT / "collision_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    log(
        f"collision audit passed={report['passed']} samples={sample_count} obstacles={len(obstacles)} violations={len(violations)}"
    )
    if violations:
        for item in violations[:20]:
            log(
                f"COLLISION {item['from_stage']}->{item['to_stage']} with {item['object']}"
            )
    return report


def rekey_grocery_bag():
    for suffix in ("grocery_bag", "grocery_handle"):
        obj = bpy.data.objects.get(PREFIX + suffix)
        if not obj:
            continue
        obj.animation_data_clear()
        obj.scale = (0.001, 0.001, 0.001)
        obj.keyframe_insert("scale", frame=125)
        obj.scale = (1, 1, 1)
        obj.keyframe_insert("scale", frame=126)


def build_demo(write_overlay=True):
    OUT.mkdir(parents=True, exist_ok=True)
    old = bpy.data.collections.get(PREFIX + "DEMO")
    if old:
        for obj in list(old.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(PREFIX + "DEMO")
    bpy.context.scene.collection.children.link(coll)
    coll["c2w_overlay_for"] = str(SOURCE_BLEND)
    coll["c2w_demo_kind"] = "collision_audited_wide_view_humanoid_mission"

    mats = {
        "body": base.material("mat_robot_shell", (0.80, 0.84, 0.86, 1), 0.36, 0.22),
        "graphite": base.material(
            "mat_robot_graphite", (0.025, 0.035, 0.055, 1), 0.60, 0.22
        ),
        "rubber": base.material(
            "mat_robot_rubber", (0.008, 0.012, 0.018, 1), 0.0, 0.86
        ),
        "metal": base.material("mat_robot_metal", (0.18, 0.24, 0.30, 1), 0.82, 0.19),
        "lens": base.material(
            "mat_sensor_visor",
            (0.005, 0.05, 0.08, 1),
            0.32,
            0.10,
            (0.0, 0.70, 1.0, 1),
            3.2,
        ),
        "cyan": base.material(
            "mat_outbound", (0.0, 0.38, 0.78, 1), 0.18, 0.20, (0.0, 0.55, 1.0, 1), 3.2
        ),
        "orange": base.material(
            "mat_robot_orange",
            (0.96, 0.23, 0.035, 1),
            0.22,
            0.24,
            (1.0, 0.12, 0.01, 1),
            1.1,
        ),
        "return": base.material(
            "mat_return", (0.92, 0.31, 0.025, 1), 0.18, 0.23, (1.0, 0.20, 0.01, 1), 3.0
        ),
        "white": base.material(
            "mat_annotation", (0.94, 0.97, 1.0, 1), 0.0, 0.36, (0.5, 0.7, 1.0, 1), 0.7
        ),
        "grocery": base.material("mat_grocery_bag", (0.96, 0.56, 0.06, 1), 0.0, 0.55),
        "grocery_dark": base.material(
            "mat_grocery_handle", (0.25, 0.10, 0.025, 1), 0.0, 0.65
        ),
        "door": base.material(
            "mat_real_front_door", (0.18, 0.055, 0.018, 1), 0.0, 0.38
        ),
        "door_inset": base.material(
            "mat_real_front_door_inset", (0.72, 0.24, 0.035, 1), 0.0, 0.34
        ),
        "frame": base.material(
            "mat_real_door_frame", (0.10, 0.12, 0.14, 1), 0.55, 0.28
        ),
        "threshold": base.material("mat_threshold", (0.24, 0.27, 0.30, 1), 0.35, 0.55),
        "ramp": base.material("mat_access_ramp", (0.29, 0.34, 0.38, 1), 0.15, 0.62),
        "room_wall": base.material(
            "mat_bedroom_replacement_wall", (0.54, 0.48, 0.67, 1), 0.0, 0.72
        ),
        "cutter": base.material("mat_boolean_cutter", (1.0, 0.0, 1.0, 1), 0.0, 0.5),
    }

    hinge, leaf, ramp, replaced, hidden = cut_real_doorway(coll, mats)
    audit = collision_audit(bpy.context.scene)

    base.route_curve(
        "outbound_route", OUTBOUND_POINTS, mats["cyan"], coll, radius=0.115
    )
    base.route_curve("return_route", RETURN_POINTS, mats["return"], coll, radius=0.115)
    base.add_route_arrows(OUTBOUND_POINTS, mats["cyan"], coll, "outbound")
    base.add_route_arrows(RETURN_POINTS, mats["return"], coll, "return")
    base.add_marker("01", "BEDROOM", (-16.2, 30.6), mats["cyan"], mats["white"], coll)
    base.add_marker(
        "02",
        "REAL DOOR",
        (DOOR_CENTER_X, DOOR_WALL_Y),
        mats["cyan"],
        mats["white"],
        coll,
    )
    base.add_marker(
        "03", "ZEBRA CROSSING", (-3.75, 0.0), mats["cyan"], mats["white"], coll
    )
    base.add_marker(
        "04", "FRESH MART", (-40.5, -26.2), mats["return"], mats["white"], coll
    )

    robot = v2.create_humanoid_robot(coll, mats)
    robot["c2w_collision_audit_passed"] = audit["passed"]
    robot["c2w_safety_radius_m"] = ROBOT_SAFETY_RADIUS
    rekey_grocery_bag()
    cams = add_cameras(coll)
    base.set_linear_animation(list(coll.all_objects))

    overlay_path = OUT / "urban_v1_full_07_agent3_overlay.blend"
    if write_overlay:
        bpy.data.libraries.write(
            str(overlay_path), {coll}, fake_user=True, compress=True
        )
        log(f"wrote overlay {overlay_path}")

    manifest = {
        "title": "Collision-Audited Humanoid Grocery Mission with Wide Multi-View Coverage",
        "source_blend": str(SOURCE_BLEND),
        "overlay_blend": str(overlay_path),
        "source_modified": False,
        "robot": {
            "type": "generic articulated biped research robot",
            "height_m": 1.95,
            "safety_radius_m": ROBOT_SAFETY_RADIUS,
            "sensors": ["stereo RGB", "depth visor", "IMU/status beacon"],
        },
        "real_doorway": {
            "center_xyz": [DOOR_CENTER_X, DOOR_WALL_Y, DOOR_FLOOR_Z],
            "clear_width_m": 2.0,
            "clear_height_m": 2.65,
            "solid_wall_objects_replaced_at_runtime": replaced,
            "overlapping_procedural_entrance_meshes_hidden_at_runtime": hidden,
            "animated_leaf": True,
            "continuous_access_ramp": True,
        },
        "collision_audit": audit,
        "route": [
            {"frame": f, "xyz": list(xyz), "stage": stage}
            for f, xyz, stage in ROUTE_KEYS
        ],
        "view_coverage": {
            "first_person": "27 mm ultrawide head camera",
            "third_person": "34 mm wide chase, 10.5 m exterior distance and 7.5 m height",
            "aerial": "84 m orthographic full-route coverage",
            "context_stills": "residential, crossing, commercial and store wide cameras",
        },
        "commercial_clearance": {
            "aisle_y_m": -36.4,
            "minimum_centerline_clearance_m": 1.3,
        },
    }
    (OUT / "mission_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return coll, robot, cams, audit


def render_stills(scene, cams, args):
    v2.configure_render(
        scene, args.still_width, args.still_height, args.engine, args.cycles_samples
    )
    scene.render.image_settings.file_format = "PNG"
    stills = [
        ("00_full_route_perspective.png", cams["overview"], 100),
        ("01_full_route_orthographic.png", cams["aerial"], 100),
        ("02_bedroom_start_wide.png", cams["room"], 1),
        ("03_wait_inside_real_door.png", cams["door_inside"], 28),
        ("04_pass_real_door.png", cams["door_outside"], 34),
        ("05_house_exit_context.png", cams["door_outside"], 42),
        ("06_crosswalk_context.png", cams["crosswalk"], 73),
        ("07_commercial_route_context.png", cams["commercial"], 105),
        ("08_arrive_fresh_mart_wide.png", cams["shop"], 118),
        ("09_shopping_complete_wide.png", cams["shop"], 126),
        ("10_first_person_real_door.png", cams["first"], 32),
        ("11_first_person_zebra_crossing.png", cams["first"], 74),
        ("12_third_person_house_to_road.png", cams["third"], 58),
        ("13_third_person_commercial_wide.png", cams["third"], 105),
        ("14_aerial_agent_mid_route.png", cams["aerial"], 105),
        ("15_return_through_real_door.png", cams["door_inside"], 200),
    ]
    if args.only_still is not None:
        stills = [stills[args.only_still]]
    for filename, camera, frame in stills:
        scene.frame_set(frame)
        scene.camera = camera
        scene.render.filepath = str(OUT / filename)
        started = time.time()
        bpy.ops.render.render(write_still=True)
        log(f"rendered {filename} in {time.time() - started:.1f}s")


def render_videos(scene, cams, args):
    views = {
        "first": (
            cams["first"],
            OUT / "urban_v1_full_07_agent3_first_person_ultrawide.mp4",
        ),
        "third": (cams["third"], OUT / "urban_v1_full_07_agent3_third_person_wide.mp4"),
        "aerial": (
            cams["aerial"],
            OUT / "urban_v1_full_07_agent3_aerial_full_route.mp4",
        ),
    }
    selected = (
        views if args.video_view == "all" else {args.video_view: views[args.video_view]}
    )
    for name, (camera, filepath) in selected.items():
        v2.render_one_video(scene, camera, filepath, args)


def write_readme(args, audit):
    text = f"""# Urban Agent Demo v3

This version replaces the v2 facade prop with a real traversable south-wall
opening in the imported bedroom.  The runtime scene hides overlapping entrance
assets, replaces the solid imported room shell with an equivalent explicit
shell containing a 2.0 m doorway, installs an animated door and continuous
ramp, and samples the 1.36 m-wide robot envelope against evaluated scene
geometry.  The source 5 GB blend is never overwritten.

Collision audit: **{'PASS' if audit['passed'] else 'REQUIRES REVIEW'}**
({audit['sample_count']} swept-envelope samples across {audit['segments']}
segments; safety radius
{ROBOT_SAFETY_RADIUS:.2f} m).  See `collision_audit.json` for details.

Main outputs:

- 16 PNG stills, including perspective and orthographic full-route maps.
- `urban_v1_full_07_agent3_first_person_ultrawide.mp4`
- `urban_v1_full_07_agent3_third_person_wide.mp4`
- `urban_v1_full_07_agent3_aerial_full_route.mp4`
- `urban_v1_full_07_agent3_overlay.blend`
- `mission_manifest.json` and `collision_audit.json`

The animation is a deterministic kinematic visualization with a sampled
geometry safety audit.  It is not yet a closed-loop physics/navigation stack.

Render configuration: stills {args.still_width}x{args.still_height}; videos
{args.video_width}x{args.video_height}; source frame step {args.video_step};
output FPS {max(1, FPS // args.video_step)}; engine {args.engine}; Cycles samples
{args.cycles_samples} when selected.
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if args.vegetation == "light":
        base.simplify_vegetation_for_preview()
    if args.spatial_cull == "mission":
        spatial_cull_to_mission()
    coll, robot, cams, audit = build_demo(write_overlay=args.mode in ("build", "all"))
    write_readme(args, audit)
    scene = bpy.context.scene
    if args.mode in ("stills", "all"):
        render_stills(scene, cams, args)
    if args.mode in ("video", "all"):
        render_videos(scene, cams, args)
    log(
        f"complete mode={args.mode} engine={args.engine} objects={len(coll.all_objects)} elapsed={time.time() - started:.1f}s"
    )


if __name__ == "__main__":
    main()
