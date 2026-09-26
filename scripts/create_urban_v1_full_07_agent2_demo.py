"""Build a colored indoor-to-store humanoid robot mission demo.

The 5 GB production scene is opened read-only.  This script writes a compact
overlay, multi-view PNGs, and first/third-person MP4 previews into
``urban_v1_full_07_agent2``.
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
_wb_BLENDER_BIN = _wb_paths["BLENDER_BIN"]


import argparse
import hashlib
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
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent2"
PREFIX = "C2W_AGENT2:"
FRAME_END = 148
FPS = 15

sys.path.insert(0, str(ROOT / "scripts"))
import create_urban_v1_full_07_agent_demo as base  # noqa: E402

# Reuse the stable geometry helpers from v1 while isolating all v2 datablocks.
base.OUT = OUT
base.PREFIX = PREFIX
base.FRAME_END = FRAME_END
base.FPS = FPS


# The first five keys traverse the actual imported residential bedroom and its
# east-facing doorway.  The outdoor section follows the verified v1 crossing
# and Fresh Mart entrance.  The return path finishes back inside the room.
ROUTE_KEYS = [
    (1, (-16.20, 30.60, 1.46), "bedroom_start"),
    (8, (-13.40, 30.65, 1.46), "cross_bedroom"),
    (14, (-11.35, 30.75, 1.46), "wait_inside_front_door"),
    (20, (-10.15, 30.85, 1.22), "pass_front_door"),
    (26, (-8.90, 30.95, 0.58), "descend_entry_steps"),
    (34, (-7.10, 31.00, 0.18), "residential_sidewalk"),
    (45, (-7.10, 8.40, 0.18), "approach_crosswalk"),
    (51, (-3.45, 7.45, 0.18), "wait_at_crosswalk"),
    (59, (-3.45, -7.45, 0.18), "cross_road"),
    (64, (-7.40, -8.35, 0.18), "commercial_sidewalk"),
    (70, (-7.40, -20.00, 0.18), "commercial_edge_sidewalk"),
    (78, (-7.40, -36.40, 0.18), "reach_clear_parking_aisle"),
    (86, (-40.50, -36.40, 0.18), "align_with_store_entrance"),
    (90, (-40.50, -26.20, 0.18), "arrive_fresh_mart"),
    (96, (-40.50, -26.20, 0.18), "shopping_complete"),
    (103, (-40.50, -36.40, 0.18), "exit_to_clear_parking_aisle"),
    (111, (-7.40, -36.40, 0.18), "return_across_clear_aisle"),
    (119, (-7.40, -20.00, 0.18), "return_commercial_edge"),
    (124, (-7.40, -8.35, 0.18), "return_commercial_sidewalk"),
    (130, (-4.10, -7.45, 0.18), "return_crosswalk_south"),
    (136, (-4.10, 7.45, 0.18), "return_cross_road"),
    (139, (-7.65, 9.10, 0.18), "return_residential_sidewalk"),
    (143, (-8.90, 30.95, 0.58), "return_entry_steps"),
    (146, (-10.35, 30.85, 1.28), "reenter_front_door"),
    (148, (-13.80, 30.65, 1.46), "mission_complete_inside_home"),
]

STORE_ARRIVAL_INDEX = next(
    i for i, key in enumerate(ROUTE_KEYS) if key[2] == "arrive_fresh_mart"
)
OUTBOUND_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[: STORE_ARRIVAL_INDEX + 1]]
RETURN_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[STORE_ARRIVAL_INDEX + 1 :]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("build", "stills", "video", "all"), default="all"
    )
    parser.add_argument("--still-width", type=int, default=1280)
    parser.add_argument("--still-height", type=int, default=720)
    parser.add_argument("--video-width", type=int, default=640)
    parser.add_argument("--video-height", type=int, default=360)
    parser.add_argument(
        "--engine", choices=("workbench", "eevee", "cycles"), default="workbench"
    )
    parser.add_argument("--cycles-samples", type=int, default=12)
    parser.add_argument("--vegetation", choices=("light", "full"), default="light")
    parser.add_argument("--only-still", type=int, choices=range(13), default=None)
    parser.add_argument("--video-step", type=int, choices=(1, 2, 3, 4), default=3)
    parser.add_argument(
        "--video-view", choices=("first", "third", "both"), default="both"
    )
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def log(message: str) -> None:
    print(f"[agent2] {message}", flush=True)


def joint(name: str, location, coll, parent=None):
    obj = bpy.data.objects.new(PREFIX + name, None)
    coll.objects.link(obj)
    obj.location = location
    obj.parent = parent
    return obj


def create_humanoid_robot(coll, mats):
    """Create a generic research-grade biped with articulated rigid links."""
    root = joint("humanoid_root", ROUTE_KEYS[0][1], coll)
    root["c2w_agent_type"] = "generic_biped_research_robot"
    root["c2w_reference_class"] = "Unitree-H1/G1-like humanoid, non-branded"
    root["c2w_sensor_suite"] = "stereo RGB, depth camera, IMU"
    root["c2w_task"] = "bedroom_to_fresh_mart_and_return"

    # Pelvis, armored torso, waist and power/status details.
    base.cube(
        "pelvis", (0, 0, 0.78), (0.43, 0.27, 0.24), mats["graphite"], coll, 0.07, root
    )
    base.cylinder(
        "waist_yaw", (0, 0, 0.94), 0.15, 0.13, mats["metal"], coll, parent=root
    )
    base.cube(
        "torso_core", (0, 0, 1.18), (0.49, 0.30, 0.48), mats["body"], coll, 0.09, root
    )
    base.cube(
        "chest_armor",
        (0, 0.165, 1.21),
        (0.37, 0.055, 0.31),
        mats["orange"],
        coll,
        0.025,
        root,
    )
    base.cube(
        "back_battery",
        (0, -0.185, 1.16),
        (0.33, 0.10, 0.34),
        mats["graphite"],
        coll,
        0.035,
        root,
    )
    base.sphere("chest_status", (0, 0.202, 1.31), 0.035, mats["cyan"], coll, root)

    # Sensor head: protective shell, glowing stereo/depth visor and antenna.
    base.cylinder("neck", (0, 0, 1.49), 0.09, 0.13, mats["metal"], coll, parent=root)
    base.cube(
        "sensor_head", (0, 0, 1.65), (0.31, 0.27, 0.27), mats["body"], coll, 0.075, root
    )
    base.cube(
        "sensor_visor",
        (0, 0.151, 1.67),
        (0.235, 0.045, 0.09),
        mats["lens"],
        coll,
        0.018,
        root,
    )
    for x in (-0.072, 0.072):
        base.sphere(
            f"stereo_eye_{x:+.3f}", (x, 0.18, 1.675), 0.024, mats["cyan"], coll, root
        )
    base.cylinder(
        "head_antenna",
        (-0.095, -0.02, 1.86),
        0.018,
        0.16,
        mats["graphite"],
        coll,
        vertices=16,
        parent=root,
    )
    base.sphere("head_beacon", (-0.095, -0.02, 1.95), 0.035, mats["orange"], coll, root)

    # Articulated legs.  Each complete leg swings from a hip pivot; the rigid
    # link geometry makes the platform read as a simulation robot, not a car.
    hip_pivots = []
    for side, x in (("L", -0.15), ("R", 0.15)):
        hip = joint(f"hip_{side}", (x, 0, 0.73), coll, root)
        hip_pivots.append(hip)
        base.sphere(f"hip_joint_{side}", (0, 0, 0), 0.085, mats["metal"], coll, hip)
        base.cube(
            f"thigh_{side}",
            (0, 0, -0.205),
            (0.17, 0.18, 0.38),
            mats["body"],
            coll,
            0.055,
            hip,
        )
        base.sphere(
            f"knee_joint_{side}", (0, 0.015, -0.42), 0.078, mats["orange"], coll, hip
        )
        base.cube(
            f"shin_{side}",
            (0, 0, -0.595),
            (0.15, 0.16, 0.31),
            mats["graphite"],
            coll,
            0.045,
            hip,
        )
        base.cube(
            f"foot_{side}",
            (0, 0.075, -0.735),
            (0.19, 0.34, 0.115),
            mats["rubber"],
            coll,
            0.045,
            hip,
        )

    shoulder_pivots = []
    for side, x in (("L", -0.33), ("R", 0.33)):
        shoulder = joint(f"shoulder_{side}", (x, 0, 1.39), coll, root)
        shoulder_pivots.append(shoulder)
        base.sphere(
            f"shoulder_joint_{side}", (0, 0, 0), 0.09, mats["metal"], coll, shoulder
        )
        base.cube(
            f"upper_arm_{side}",
            (0, 0, -0.20),
            (0.15, 0.16, 0.34),
            mats["body"],
            coll,
            0.05,
            shoulder,
        )
        base.sphere(
            f"elbow_{side}", (0, 0.01, -0.39), 0.072, mats["orange"], coll, shoulder
        )
        base.cube(
            f"forearm_{side}",
            (0, 0.025, -0.54),
            (0.135, 0.15, 0.27),
            mats["graphite"],
            coll,
            0.045,
            shoulder,
        )
        base.cube(
            f"hand_{side}",
            (0, 0.055, -0.705),
            (0.13, 0.13, 0.12),
            mats["rubber"],
            coll,
            0.035,
            shoulder,
        )

    # A grocery bag becomes visible once the shopping phase completes.
    bag = base.cube(
        "grocery_bag",
        (0.47, 0.065, 0.64),
        (0.31, 0.22, 0.40),
        mats["grocery"],
        coll,
        0.035,
        root,
    )
    handle = base.torus(
        "grocery_handle", (0.47, 0.065, 0.87), 0.12, 0.025, mats["grocery_dark"], coll
    )
    handle.rotation_euler[0] = math.pi / 2
    handle.parent = root
    for obj in (bag, handle):
        obj.scale = (0.001, 0.001, 0.001)
        obj.keyframe_insert("scale", frame=95)
        obj.scale = (1, 1, 1)
        obj.keyframe_insert("scale", frame=96)

    # Root translation/yaw follows the verified route.
    previous_yaw = 0.0
    previous_point = Vector(ROUTE_KEYS[0][1])
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        direction = (
            Vector(ROUTE_KEYS[index + 1][1]) - point
            if index < len(ROUTE_KEYS) - 1
            else point - previous_point
        )
        if direction.length > 1e-5:
            yaw = math.atan2(-direction.x, direction.y)
            while yaw - previous_yaw > math.pi:
                yaw -= math.tau
            while yaw - previous_yaw < -math.pi:
                yaw += math.tau
            previous_yaw = yaw
        root.location = point
        root.rotation_euler[2] = previous_yaw
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_euler", index=2, frame=frame)
        previous_point = point

    # Readable procedural walk cycle for the preview animation.
    stationary = ((1, 2), (13, 15), (89, 96), (147, 148))
    for frame in range(1, FRAME_END + 1, 2):
        moving = not any(a <= frame <= b for a, b in stationary)
        swing = 0.34 * math.sin(frame * 0.63) if moving else 0.0
        hip_pivots[0].rotation_euler[0] = swing
        hip_pivots[1].rotation_euler[0] = -swing
        shoulder_pivots[0].rotation_euler[0] = -0.72 * swing
        shoulder_pivots[1].rotation_euler[0] = 0.72 * swing
        for pivot in (*hip_pivots, *shoulder_pivots):
            pivot.keyframe_insert("rotation_euler", index=0, frame=frame)

    return root


def create_front_door_and_steps(coll, mats):
    """Add an explicitly animated entrance at the imported bedroom opening."""
    # A compact five-tread transition makes the elevated Infinigen indoor floor
    # visually connect to the lower urban sidewalk.
    for i in range(5):
        top = 1.34 - i * 0.235
        x = -10.12 + i * 0.43
        base.cube(
            f"entry_step_{i}",
            (x, 30.84, top / 2),
            (0.46, 1.45, top),
            mats["step"],
            coll,
            0.025,
        )

    pivot = joint("front_door_hinge", (-10.47, 30.10, 1.45), coll)
    leaf = base.cube(
        "front_door_leaf",
        (0, 0.66, 1.03),
        (0.075, 1.32, 2.06),
        mats["door"],
        coll,
        0.045,
        pivot,
    )
    base.cube(
        "front_door_inset",
        (0.047, 0.66, 1.08),
        (0.018, 0.92, 1.35),
        mats["door_inset"],
        coll,
        0.012,
        pivot,
    )
    base.sphere(
        "front_door_handle", (0.09, 1.13, 1.06), 0.045, mats["metal"], coll, pivot
    )
    for frame, angle in (
        (1, 0),
        (10, 0),
        (16, -96),
        (25, -96),
        (32, 0),
        (138, 0),
        (142, -96),
        (147, -96),
        (148, 0),
    ):
        pivot.rotation_euler[2] = math.radians(angle)
        pivot.keyframe_insert("rotation_euler", index=2, frame=frame)
    return pivot, leaf


def add_dynamic_camera(name, coll, locations, targets, lens):
    cam = base.camera(name, locations[0][1], targets[0][1], lens, coll)
    target = joint(name + "_target", targets[0][1], coll)
    constraint = cam.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    for frame, position in locations:
        cam.location = position
        cam.keyframe_insert("location", frame=frame)
    for frame, position in targets:
        target.location = position
        target.keyframe_insert("location", frame=frame)
    return cam, target


def route_forward(index: int, previous: Vector) -> Vector:
    here = Vector(ROUTE_KEYS[index][1])
    if index < len(ROUTE_KEYS) - 1:
        forward = Vector(ROUTE_KEYS[index + 1][1]) - here
    else:
        forward = here - previous
    forward.z = 0
    if forward.length <= 1e-5:
        forward = here - previous
        forward.z = 0
    return forward.normalized() if forward.length > 1e-5 else Vector((1, 0, 0))


def add_cameras(coll):
    cams = {
        "overview": base.camera(
            "camera_overview", (70, -90, 108), (-21, 2, 0), 52, coll
        ),
        "room": base.camera(
            "camera_room", (-18.8, 27.1, 2.85), (-15.2, 30.7, 2.15), 44, coll
        ),
        "door_inside": base.camera(
            "camera_door_inside", (-14.2, 32.8, 3.75), (-10.85, 30.8, 1.90), 50, coll
        ),
        "door_outside": base.camera(
            "camera_door_outside", (-6.8, 35.0, 3.25), (-10.2, 30.8, 1.65), 48, coll
        ),
        "crosswalk": base.camera(
            "camera_crosswalk", (8.5, -2.0, 5.4), (-3.6, 0.0, 0.85), 52, coll
        ),
        "shop": base.camera(
            "camera_shop", (-28.0, -40.5, 5.2), (-40.5, -26.0, 1.05), 50, coll
        ),
    }

    first_locations = []
    first_targets = []
    third_locations = []
    third_targets = []
    previous = Vector(ROUTE_KEYS[0][1]) - Vector((1, 0, 0))
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        forward = route_forward(index, previous)
        side = Vector((-forward.y, forward.x, 0))
        # Keep the optical center safely in front of the physical visor.  The
        # extra clearance prevents the interpolated camera path from entering
        # the robot head during sharp route turns.
        first_locations.append((frame, point + forward * 0.48 + Vector((0, 0, 1.70))))
        first_targets.append((frame, point + forward * 8.0 + Vector((0, 0, 1.48))))

        # The room sequence uses a tighter shoulder camera; the exterior gets a
        # broader chase view that exposes the robot and urban context.
        distance = 3.0 if frame <= 26 or frame >= 142 else 4.3
        height = 2.25 if frame <= 26 or frame >= 142 else 3.15
        lateral = 1.15 if frame <= 26 or frame >= 142 else 2.15
        if 90 <= frame <= 96:
            # Keep the shop facade between neither camera nor robot while the
            # route pauses and reverses direction at the checkout phase.
            third_position = Vector((-31.0, -37.0, 4.1))
        else:
            third_position = (
                point - forward * distance + side * lateral + Vector((0, 0, height))
            )
        third_locations.append((frame, third_position))
        third_targets.append((frame, point + Vector((0, 0, 0.95))))
        previous = point

    first, first_target = add_dynamic_camera(
        "camera_first_person", coll, first_locations, first_targets, 58
    )
    third, third_target = add_dynamic_camera(
        "camera_third_person", coll, third_locations, third_targets, 50
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


def material_viewport_color(mat):
    """Derive a useful viewport color from nodes and semantic material names."""
    name = mat.name.lower()
    semantic = (
        (("grass", "lawn", "leaf", "foliage", "plant", "shrub"), (0.18, 0.42, 0.16, 1)),
        (("flower", "petal"), (0.72, 0.20, 0.30, 1)),
        (("wood", "timber", "hardwood"), (0.43, 0.24, 0.10, 1)),
        (("soil", "dirt", "earth"), (0.25, 0.13, 0.07, 1)),
        (("brick", "terracotta"), (0.55, 0.20, 0.10, 1)),
        (("road", "asphalt"), (0.07, 0.09, 0.12, 1)),
        (("glass", "window"), (0.22, 0.48, 0.62, 1)),
        (("metal", "steel", "iron"), (0.18, 0.23, 0.28, 1)),
        (("roof", "tile"), (0.30, 0.22, 0.20, 1)),
        (("plaster", "facade", "ceiling"), (0.72, 0.68, 0.61, 1)),
        (("concrete", "stone", "marble", "cobble"), (0.48, 0.52, 0.55, 1)),
    )
    for tokens, color in semantic:
        if any(token in name for token in tokens):
            return color

    if mat.use_nodes and mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Base Color" in bsdf.inputs:
            value = tuple(bsdf.inputs["Base Color"].default_value)
            if max(value[:3]) - min(value[:3]) > 0.035 or max(value[:3]) < 0.58:
                return value

    # Deterministic restrained palette for generic procedural materials whose
    # viewport color otherwise defaults to the same grey.
    palette = (
        (0.58, 0.66, 0.72, 1),
        (0.69, 0.56, 0.43, 1),
        (0.54, 0.64, 0.50, 1),
        (0.66, 0.52, 0.58, 1),
        (0.48, 0.57, 0.66, 1),
        (0.72, 0.66, 0.48, 1),
    )
    digest = hashlib.sha1(mat.name.encode("utf-8", "ignore")).digest()[0]
    return palette[digest % len(palette)]


def sync_viewport_material_colors():
    changed = 0
    for mat in bpy.data.materials:
        if mat.name.startswith(PREFIX):
            continue
        mat.diffuse_color = material_viewport_color(mat)
        changed += 1
    log(f"synchronized {changed} source material viewport colors")


def configure_cycles_gpu(scene, samples: int):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU"
    scene.render.use_persistent_data = True
    selected = []
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.refresh_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
            if device.use:
                selected.append(f"{device.name}:{device.type}")
        if not selected:
            prefs.compute_device_type = "CUDA"
            prefs.refresh_devices()
            for device in prefs.devices:
                device.use = device.type == "CUDA"
                if device.use:
                    selected.append(f"{device.name}:{device.type}")
    except Exception as exc:
        log(f"CUDA selection warning: {exc}; Blender may fall back to CPU")
    log(
        f"Cycles devices={selected or ['CPU fallback']} CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}"
    )


def configure_render(scene, width, height, engine, cycles_samples):
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    if engine == "workbench":
        scene.view_settings.exposure = 0.45
        scene.render.engine = "BLENDER_WORKBENCH"
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.studio_light = "outdoor.sl"
        shading.studiolight_rotate_z = math.radians(125)
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        shading.background_color = (0.72, 0.80, 0.89)
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "WORLD"
        shading.show_specular_highlight = True
        sync_viewport_material_colors()
    elif engine == "eevee":
        scene.view_settings.exposure = -0.90
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    else:
        scene.view_settings.exposure = -0.90
        configure_cycles_gpu(scene, cycles_samples)


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
    coll["c2w_demo_kind"] = "colored_indoor_outdoor_humanoid_mission"

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
        "door": base.material("mat_front_door", (0.30, 0.09, 0.035, 1), 0.0, 0.42),
        "door_inset": base.material(
            "mat_front_door_inset", (0.56, 0.22, 0.07, 1), 0.0, 0.38
        ),
        "step": base.material("mat_entry_step", (0.38, 0.43, 0.48, 1), 0.0, 0.72),
    }

    base.route_curve(
        "outbound_route", OUTBOUND_POINTS, mats["cyan"], coll, radius=0.105
    )
    base.route_curve("return_route", RETURN_POINTS, mats["return"], coll, radius=0.105)
    base.add_route_arrows(OUTBOUND_POINTS, mats["cyan"], coll, "outbound")
    base.add_route_arrows(RETURN_POINTS, mats["return"], coll, "return")
    base.add_marker(
        "01", "HOME / BEDROOM", (-8.2, 33.0), mats["cyan"], mats["white"], coll
    )
    base.add_marker(
        "02", "SAFE CROSSING", (-3.75, 0.0), mats["cyan"], mats["white"], coll
    )
    base.add_marker(
        "03", "FRESH MART", (-40.5, -26.2), mats["return"], mats["white"], coll
    )
    create_front_door_and_steps(coll, mats)
    robot = create_humanoid_robot(coll, mats)
    cams = add_cameras(coll)
    base.set_linear_animation(list(coll.all_objects))

    overlay_path = OUT / "urban_v1_full_07_agent2_overlay.blend"
    if write_overlay:
        bpy.data.libraries.write(
            str(overlay_path), {coll}, fake_user=True, compress=True
        )
        log(f"wrote overlay {overlay_path}")

    manifest = {
        "title": "Humanoid Grocery Errand: Bedroom to Fresh Mart and Return",
        "source_blend": str(SOURCE_BLEND),
        "overlay_blend": str(overlay_path),
        "demo_type": "colored kinematic simulation visualization",
        "robot": {
            "type": "generic articulated biped research robot",
            "height_m": 1.95,
            "sensors": ["stereo RGB", "depth visor", "IMU/status beacon"],
            "motion": "root trajectory plus procedural arm/leg walk cycle",
        },
        "indoor_start": {
            "room": "imported bedroom_0/0 in House_large_indoor",
            "floor_z_m": 1.46,
            "animated_front_door": True,
            "entry_steps": 5,
        },
        "commercial_clearance": {
            "aisle_y_m": -36.4,
            "north_vehicle_row_south_edge_y_m": -35.07,
            "south_vehicle_row_north_edge_y_m": -37.78,
            "minimum_centerline_clearance_m": 1.3,
        },
        "route": [
            {"frame": f, "xyz": list(xyz), "stage": stage}
            for f, xyz, stage in ROUTE_KEYS
        ],
        "videos": {
            "first_person": "head-mounted sensor camera",
            "third_person": "dynamic chase camera",
        },
        "note": "Preview trajectory is deterministic and not yet closed-loop physics/navigation.",
    }
    (OUT / "mission_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return coll, robot, cams


def render_stills(scene, cams, args):
    configure_render(
        scene, args.still_width, args.still_height, args.engine, args.cycles_samples
    )
    scene.render.image_settings.file_format = "PNG"
    stills = [
        ("00_mission_overview.png", cams["overview"], 55),
        ("01_bedroom_start.png", cams["room"], 1),
        ("02_approach_front_door.png", cams["door_inside"], 14),
        ("03_exit_front_door.png", cams["door_outside"], 22),
        ("04_crosswalk_outbound.png", cams["crosswalk"], 56),
        ("05_arrive_fresh_mart.png", cams["shop"], 90),
        ("06_shopping_complete.png", cams["shop"], 96),
        ("07_return_home.png", cams["door_outside"], 145),
        ("08_mission_complete_inside.png", cams["room"], 148),
        ("09_first_person_bedroom_departure.png", cams["first"], 8),
        ("10_first_person_road_crossing.png", cams["first"], 56),
        ("11_third_person_residential_sidewalk.png", cams["third"], 40),
        ("12_third_person_arrive_shop.png", cams["third"], 90),
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


def render_one_video(scene, camera, filepath, args):
    configure_render(
        scene, args.video_width, args.video_height, args.engine, args.cycles_samples
    )
    scene.frame_step = args.video_step
    scene.render.fps = max(1, FPS // args.video_step)
    scene.camera = camera
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(filepath)
    started = time.time()
    bpy.ops.render.render(animation=True)
    log(f"rendered {filepath.name} in {time.time() - started:.1f}s")


def render_videos(scene, cams, args):
    if args.video_view in ("first", "both"):
        render_one_video(
            scene, cams["first"], OUT / "urban_v1_full_07_agent2_first_person.mp4", args
        )
    if args.video_view in ("third", "both"):
        render_one_video(
            scene, cams["third"], OUT / "urban_v1_full_07_agent2_third_person.mp4", args
        )


def write_readme(args):
    text = f"""# Urban Agent Demo v2

This version starts inside the real imported bedroom, opens a visible front
door, exits to the urban sidewalk, crosses at the zebra crossing, shops at
Fresh Mart, and returns indoors.  The source 5 GB blend is not copied or
modified.

Changes from v1:

- Generic articulated humanoid research robot instead of a wheeled cart.
- Colored source materials plus a high-contrast orange/white robot.
- Bedroom start, animated door, entrance transition, and explicit exit shots.
- Separate head-mounted first-person and dynamic third-person videos.

Outputs:

- `00_mission_overview.png` through `12_third_person_arrive_shop.png`
- `urban_v1_full_07_agent2_first_person.mp4`
- `urban_v1_full_07_agent2_third_person.mp4`
- `urban_v1_full_07_agent2_overlay.blend`
- `mission_manifest.json`

The motion is a deterministic kinematic paper-visualization demo, not yet
closed-loop physics or collision-checked navigation.

Render command (GPU 1 is isolated by CUDA_VISIBLE_DEVICES):

```bash
CUDA_VISIBLE_DEVICES=1 {_wb_BLENDER_BIN} -b \\
  {SOURCE_BLEND} \\
  --python {ROOT / 'scripts/create_urban_v1_full_07_agent2_demo.py'} -- \\
  --mode all --engine {args.engine} --cycles-samples {args.cycles_samples} --vegetation {args.vegetation}
```

Configuration: stills {args.still_width}x{args.still_height}; videos
{args.video_width}x{args.video_height}; source frame step {args.video_step};
output FPS {max(1, FPS // args.video_step)}; Cycles samples {args.cycles_samples}.
The colored Workbench renderer remains available for rapid iteration.
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if args.vegetation == "light":
        base.simplify_vegetation_for_preview()
    coll, _, cams = build_demo(write_overlay=args.mode in ("build", "all"))
    write_readme(args)
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
