"""Create and render a paper-style autonomous shopping mission demo.

Run with the production scene already opened, for example::

    blender -b urban_v1_full_07.blend --python create_urban_v1_full_07_agent_demo.py -- --mode all

The source scene is never saved or modified on disk.  The script writes a small
overlay blend containing the robot, task route, annotations, and cameras, plus
PNG stills and an optional MP4 to ``urban_v1_full_07_agent``.
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
import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SOURCE_BLEND = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07/urban_v1_full_07.blend"
)
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent"
PREFIX = "C2W_AGENT:"
FRAME_END = 102
FPS = 12

# Local +Y is the robot forward axis.  The route goes through the residential
# front door, follows the west sidewalk, uses the zebra crossing at the main
# junction, reaches the real Fresh Mart entrance, then returns on a slightly
# offset track so both directions remain legible in an aerial figure.
ROUTE_KEYS = [
    (1, (-11.25, 31.00, 0.18), "inside_home"),
    (6, (-9.10, 31.00, 0.18), "exit_home"),
    (14, (-7.10, 31.00, 0.18), "residential_sidewalk"),
    (25, (-7.10, 8.40, 0.18), "approach_crosswalk"),
    (31, (-3.45, 7.45, 0.18), "wait_at_crosswalk"),
    (39, (-3.45, -7.45, 0.18), "cross_road"),
    (44, (-7.40, -8.35, 0.18), "commercial_sidewalk"),
    (50, (-17.00, -9.30, 0.18), "enter_commercial_zone"),
    (58, (-18.50, -29.50, 0.18), "commercial_forecourt"),
    (64, (-40.50, -26.20, 0.18), "arrive_fresh_mart"),
    (70, (-40.50, -26.20, 0.18), "shopping_complete"),
    (77, (-18.50, -29.50, 0.18), "return_from_store"),
    (83, (-17.00, -10.20, 0.18), "return_commercial_sidewalk"),
    (88, (-4.10, -7.45, 0.18), "return_crosswalk_south"),
    (94, (-4.10, 7.45, 0.18), "return_cross_road"),
    (97, (-7.65, 9.10, 0.18), "return_residential_sidewalk"),
    (100, (-7.65, 31.00, 0.18), "arrive_home"),
    (102, (-11.25, 31.00, 0.18), "mission_complete"),
]

OUTBOUND_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[:10]]
RETURN_POINTS = [Vector(xyz) for _, xyz, _ in ROUTE_KEYS[10:]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("build", "stills", "video", "all"), default="all"
    )
    parser.add_argument("--still-width", type=int, default=1280)
    parser.add_argument("--still-height", type=int, default=720)
    parser.add_argument("--video-width", type=int, default=640)
    parser.add_argument("--video-height", type=int, default=360)
    parser.add_argument("--engine", choices=("workbench", "eevee"), default="workbench")
    parser.add_argument("--vegetation", choices=("light", "full"), default="light")
    parser.add_argument("--only-still", type=int, choices=range(7), default=None)
    parser.add_argument("--video-step", type=int, choices=(1, 2, 3), default=2)
    argv = []
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    return parser.parse_args(argv)


def log(message: str) -> None:
    print(f"[agent-demo] {message}", flush=True)


def material(
    name: str, color, metallic=0.0, roughness=0.45, emission=None, emission_strength=0.0
):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        emission_name = (
            "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        )
        bsdf.inputs[emission_name].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def move_to_collection(
    obj: bpy.types.Object, coll: bpy.types.Collection
) -> bpy.types.Object:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def cube(name, location, dimensions, mat, coll, bevel=0.0, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = move_to_collection(bpy.context.object, coll)
    obj.name = PREFIX + name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new(PREFIX + "edge_softening", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    obj.parent = parent
    return obj


def cylinder(
    name,
    location,
    radius,
    depth,
    mat,
    coll,
    vertices=32,
    rotation=(0, 0, 0),
    parent=None,
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = move_to_collection(bpy.context.object, coll)
    obj.name = PREFIX + name
    if mat:
        obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def sphere(name, location, radius, mat, coll, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=12, radius=radius, location=location
    )
    obj = move_to_collection(bpy.context.object, coll)
    obj.name = PREFIX + name
    if mat:
        obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.parent = parent
    return obj


def torus(name, location, major_radius, minor_radius, mat, coll):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=48,
        minor_segments=10,
        location=location,
    )
    obj = move_to_collection(bpy.context.object, coll)
    obj.name = PREFIX + name
    obj.data.materials.append(mat)
    return obj


def route_curve(name: str, points: list[Vector], mat, coll, radius=0.13):
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (coordinate.x, coordinate.y, coordinate.z + 0.08, 1.0)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    coll.objects.link(obj)
    curve.materials.append(mat)
    return obj


def arrow(name: str, location: Vector, direction: Vector, mat, coll):
    bpy.ops.mesh.primitive_cone_add(
        vertices=24, radius1=0.30, radius2=0.0, depth=0.76, location=location
    )
    obj = move_to_collection(bpy.context.object, coll)
    obj.name = PREFIX + name
    obj.data.materials.append(mat)
    direction = direction.normalized()
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction)
    return obj


def add_route_arrows(points: list[Vector], mat, coll, label: str):
    distances = []
    total = 0.0
    for index in range(len(points) - 1):
        length = (points[index + 1] - points[index]).length
        distances.append((total, total + length, index))
        total += length
    cursor = 6.0
    arrow_index = 0
    while cursor < total - 2.0:
        for start, end, segment_index in distances:
            if start <= cursor <= end:
                a, b = points[segment_index], points[segment_index + 1]
                factor = (cursor - start) / max(end - start, 1e-6)
                position = a.lerp(b, factor) + Vector((0, 0, 0.21))
                arrow(f"{label}_arrow_{arrow_index:02d}", position, b - a, mat, coll)
                arrow_index += 1
                break
        cursor += 8.0


def add_ground_text(name: str, body: str, location, size: float, mat, coll):
    data = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = 0.018
    data.bevel_depth = 0.004
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = location
    data.materials.append(mat)
    return obj


def add_marker(number: str, title: str, location, color_mat, white_mat, coll):
    x, y = location
    torus(f"marker_{number}_ring", (x, y, 0.27), 0.72, 0.09, color_mat, coll)
    cylinder(
        f"marker_{number}_mast", (x, y, 1.18), 0.055, 1.75, color_mat, coll, vertices=18
    )
    sphere(f"marker_{number}_beacon", (x, y, 2.10), 0.16, color_mat, coll)
    add_ground_text(
        f"marker_{number}_number", number, (x, y, 0.38), 0.78, white_mat, coll
    )
    add_ground_text(
        f"marker_{number}_title", title, (x, y - 1.15, 0.27), 0.42, white_mat, coll
    )


def make_robot(coll, mats):
    root = bpy.data.objects.new(PREFIX + "robot_root", None)
    coll.objects.link(root)
    root.location = ROUTE_KEYS[0][1]
    root["c2w_agent_type"] = "four_wheel_mobile_manipulator"
    root["c2w_task"] = "home_to_fresh_mart_and_return"

    cube(
        "robot_lower_chassis",
        (0, 0, 0.34),
        (1.02, 1.24, 0.25),
        mats["dark"],
        coll,
        0.10,
        root,
    )
    cube(
        "robot_upper_chassis",
        (0, 0.02, 0.63),
        (0.86, 0.86, 0.34),
        mats["body"],
        coll,
        0.12,
        root,
    )
    cube(
        "robot_front_sensor_bar",
        (0, 0.47, 0.67),
        (0.68, 0.09, 0.13),
        mats["dark"],
        coll,
        0.025,
        root,
    )
    for side, x in (("left", -0.23), ("right", 0.23)):
        sphere(
            f"stereo_camera_{side}", (x, 0.525, 0.69), 0.065, mats["lens"], coll, root
        )

    wheels = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            wheel = cylinder(
                f"wheel_{sx:+d}_{sy:+d}",
                (0.56 * sx, 0.39 * sy, 0.28),
                0.225,
                0.15,
                mats["rubber"],
                coll,
                vertices=32,
                rotation=(0, math.pi / 2, 0),
                parent=root,
            )
            cylinder(
                f"wheel_hub_{sx:+d}_{sy:+d}",
                (0.645 * sx, 0.39 * sy, 0.28),
                0.095,
                0.025,
                mats["metal"],
                coll,
                vertices=24,
                rotation=(0, math.pi / 2, 0),
                parent=root,
            )
            wheels.append(wheel)

    cylinder(
        "lidar_pedestal", (0, -0.06, 0.90), 0.13, 0.17, mats["metal"], coll, parent=root
    )
    lidar = cylinder(
        "lidar_head",
        (0, -0.06, 1.03),
        0.20,
        0.11,
        mats["dark"],
        coll,
        vertices=40,
        parent=root,
    )
    cube(
        "lidar_window",
        (0, 0.14, 1.03),
        (0.25, 0.025, 0.055),
        mats["lens"],
        coll,
        0.008,
        root,
    )
    sphere("status_beacon", (0, -0.06, 1.16), 0.075, mats["cyan"], coll, root)

    # Compact mobile-manipulator arm and a visible grocery carrier.
    cylinder(
        "arm_shoulder",
        (-0.34, -0.20, 0.93),
        0.12,
        0.22,
        mats["metal"],
        coll,
        rotation=(0, math.pi / 2, 0),
        parent=root,
    )
    arm1 = cube(
        "arm_upper",
        (-0.36, -0.20, 1.22),
        (0.16, 0.18, 0.56),
        mats["body"],
        coll,
        0.06,
        root,
    )
    arm1.rotation_euler[0] = math.radians(-12)
    cylinder(
        "arm_elbow",
        (-0.36, -0.13, 1.48),
        0.11,
        0.22,
        mats["metal"],
        coll,
        rotation=(0, math.pi / 2, 0),
        parent=root,
    )
    arm2 = cube(
        "arm_forearm",
        (-0.36, 0.02, 1.62),
        (0.14, 0.44, 0.16),
        mats["body"],
        coll,
        0.05,
        root,
    )
    arm2.rotation_euler[0] = math.radians(18)
    cube(
        "robot_cargo_bin",
        (0.25, -0.19, 0.98),
        (0.44, 0.48, 0.32),
        mats["cargo"],
        coll,
        0.055,
        root,
    )
    cube(
        "cargo_lid",
        (0.25, -0.19, 1.16),
        (0.48, 0.52, 0.055),
        mats["dark"],
        coll,
        0.025,
        root,
    )
    grocery = cube(
        "grocery_bag",
        (0.25, -0.18, 1.40),
        (0.34, 0.28, 0.43),
        mats["grocery"],
        coll,
        0.035,
        root,
    )
    grocery.scale = (0.001, 0.001, 0.001)
    grocery.keyframe_insert("scale", frame=69)
    grocery.scale = (1.0, 1.0, 1.0)
    grocery.keyframe_insert("scale", frame=70)
    add_ground_text(
        "robot_side_id", "A01", (-0.27, 0.636, 0.62), 0.17, mats["cyan"], coll
    ).parent = root

    # Animate chassis motion, yaw, wheel rotation, and lidar scan.
    previous_yaw = 0.0
    travel = 0.0
    previous_point = Vector(ROUTE_KEYS[0][1])
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        if index < len(ROUTE_KEYS) - 1:
            direction = Vector(ROUTE_KEYS[index + 1][1]) - point
        else:
            direction = point - previous_point
        if direction.length > 1e-5:
            target_yaw = math.atan2(-direction.x, direction.y)
            while target_yaw - previous_yaw > math.pi:
                target_yaw -= math.tau
            while target_yaw - previous_yaw < -math.pi:
                target_yaw += math.tau
            previous_yaw = target_yaw
        root.location = point
        root.rotation_euler[2] = previous_yaw
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_euler", index=2, frame=frame)
        travel += (point - previous_point).length
        for wheel in wheels:
            wheel.rotation_euler[2] = travel / 0.225
            wheel.keyframe_insert("rotation_euler", index=2, frame=frame)
        previous_point = point
    lidar.rotation_euler[2] = 0
    lidar.keyframe_insert("rotation_euler", index=2, frame=1)
    lidar.rotation_euler[2] = math.tau * 14
    lidar.keyframe_insert("rotation_euler", index=2, frame=FRAME_END)
    return root


def set_linear_animation(objects):
    for obj in objects:
        if obj.animation_data and obj.animation_data.action:
            for curve in obj.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "LINEAR"


def look_at(obj: bpy.types.Object, target) -> None:
    obj.rotation_euler = (
        (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )


def camera(name: str, location, target, lens: float, coll):
    data = bpy.data.cameras.new(PREFIX + name + ":data")
    data.lens = lens
    data.sensor_width = 36
    data.clip_start = 0.05
    data.clip_end = 500
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def add_cameras(coll):
    cams = {
        "overview": camera("camera_overview", (70, -90, 108), (-21, 2, 0), 52, coll),
        "home": camera("camera_home", (0.5, 38.0, 4.7), (-10.3, 31.0, 0.8), 52, coll),
        "crosswalk": camera(
            "camera_crosswalk", (8.5, -2.0, 5.4), (-3.6, 0.0, 0.7), 52, coll
        ),
        "shop": camera(
            "camera_shop", (-28.0, -40.5, 5.2), (-40.5, -26.0, 1.0), 50, coll
        ),
    }
    follow = camera("camera_follow", (0, 0, 9), ROUTE_KEYS[0][1], 48, coll)
    target = bpy.data.objects.new(PREFIX + "follow_target", None)
    coll.objects.link(target)
    constraint = follow.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    for frame, xyz, _ in ROUTE_KEYS:
        position = Vector(xyz)
        offset = (
            Vector((10.0, -12.0, 11.0)) if frame <= 70 else Vector((8.0, 0.0, 18.0))
        )
        follow.location = position + offset
        target.location = position + Vector((0, 0, 0.72))
        follow.keyframe_insert("location", frame=frame)
        target.keyframe_insert("location", frame=frame)
    cams["follow"] = follow
    cams["follow_target"] = target
    return cams


def configure_render(scene, width: int, height: int, engine: str):
    scene.render.engine = (
        "BLENDER_WORKBENCH" if engine == "workbench" else "BLENDER_EEVEE_NEXT"
    )
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.use_file_extension = True
    if engine == "workbench":
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.studio_light = "outdoor.sl"
        shading.studiolight_rotate_z = math.radians(135)
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        shading.background_color = (0.86, 0.89, 0.93)
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "WORLD"
        shading.show_specular_highlight = True
        scene.view_settings.exposure = 1.25
    # Moderate-quality settings keep the 5 GB scene practical without a GPU.
    elif hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 4


def build_demo(write_overlay: bool = True):
    OUT.mkdir(parents=True, exist_ok=True)
    old = bpy.data.collections.get(PREFIX + "DEMO")
    if old:
        for obj in list(old.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(PREFIX + "DEMO")
    bpy.context.scene.collection.children.link(coll)
    coll["c2w_overlay_for"] = str(SOURCE_BLEND)
    coll["c2w_demo_kind"] = "kinematic_autonomous_errand_visualization"

    mats = {
        "body": material("mat_robot_ceramic", (0.74, 0.78, 0.80, 1), 0.42, 0.24),
        "dark": material("mat_robot_graphite", (0.035, 0.045, 0.055, 1), 0.72, 0.24),
        "rubber": material("mat_tire", (0.012, 0.014, 0.016, 1), 0.0, 0.88),
        "metal": material("mat_brushed_metal", (0.24, 0.29, 0.33, 1), 0.80, 0.22),
        "lens": material(
            "mat_sensor_lens",
            (0.006, 0.035, 0.055, 1),
            0.35,
            0.12,
            (0.0, 0.45, 0.85, 1),
            2.4,
        ),
        "cyan": material(
            "mat_outbound_cyan",
            (0.0, 0.42, 0.66, 1),
            0.25,
            0.20,
            (0.0, 0.65, 1.0, 1),
            3.0,
        ),
        "orange": material(
            "mat_return_orange",
            (0.82, 0.22, 0.035, 1),
            0.18,
            0.25,
            (1.0, 0.18, 0.02, 1),
            2.8,
        ),
        "white": material(
            "mat_annotation_white",
            (0.92, 0.96, 1.0, 1),
            0.0,
            0.38,
            (0.55, 0.70, 0.85, 1),
            0.7,
        ),
        "cargo": material("mat_cargo_bin", (0.055, 0.18, 0.24, 1), 0.22, 0.34),
        "grocery": material("mat_grocery_bag", (0.95, 0.58, 0.06, 1), 0.0, 0.64),
    }

    route_curve("outbound_route", OUTBOUND_POINTS, mats["cyan"], coll)
    route_curve("return_route", RETURN_POINTS, mats["orange"], coll)
    add_route_arrows(OUTBOUND_POINTS, mats["cyan"], coll, "outbound")
    add_route_arrows(RETURN_POINTS, mats["orange"], coll, "return")
    add_marker("01", "HOME", (-10.4, 31.0), mats["cyan"], mats["white"], coll)
    add_marker("02", "SAFE CROSSING", (-3.75, 0.0), mats["cyan"], mats["white"], coll)
    add_marker("03", "FRESH MART", (-40.5, -26.2), mats["orange"], mats["white"], coll)
    add_ground_text(
        "route_legend_out", "OUTBOUND", (-14.0, 11.0, 0.28), 0.44, mats["cyan"], coll
    )
    add_ground_text(
        "route_legend_return",
        "RETURN + GROCERIES",
        (-25.0, -12.8, 0.28),
        0.44,
        mats["orange"],
        coll,
    )
    robot = make_robot(coll, mats)
    cams = add_cameras(coll)
    set_linear_animation(list(coll.all_objects))

    overlay_path = OUT / "urban_v1_full_07_agent_overlay.blend"
    if write_overlay:
        bpy.data.libraries.write(
            str(overlay_path), {coll}, fake_user=True, compress=True
        )
        log(f"wrote reusable overlay {overlay_path}")
    else:
        log("skipped overlay rewrite for render-only mode")

    manifest = {
        "title": "Autonomous Grocery Errand: Residential to Fresh Mart and Return",
        "source_blend": str(SOURCE_BLEND),
        "overlay_blend": str(overlay_path),
        "demo_type": "kinematic visualization; not yet a physics/navigation simulation",
        "robot": {
            "type": "four-wheel mobile manipulator",
            "sensors": ["spinning lidar", "stereo front cameras"],
            "payload": "animated grocery carrier",
        },
        "route": [
            {"frame": frame, "xyz": list(xyz), "stage": stage}
            for frame, xyz, stage in ROUTE_KEYS
        ],
        "visual_encoding": {
            "cyan": "outbound route",
            "orange": "return route with groceries",
            "markers": ["01 HOME", "02 SAFE CROSSING", "03 FRESH MART"],
        },
        "render": {
            "default_engine": "Workbench",
            "optional_engine": "Eevee Next",
            "fps": FPS,
            "frame_end": FRAME_END,
        },
    }
    (OUT / "mission_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return coll, robot, cams


def simplify_vegetation_for_preview() -> list[str]:
    """Hide only expensive vegetation instances/scatters for quick rendering."""
    hidden = []
    master_tokens = ("treefactory", "treeprototype", "shrubprototype", "tree_master")
    object_tokens = (
        "full06_road_flowerbed_flowers",
        "full06_road_flowerbed_grass_understory",
        "park_lawn_grid",
        "park_lawn_s_grid",
        "wst_lawn_n_grid",
        "wst_lawn_s_grid",
    )
    for obj in bpy.context.scene.objects:
        if obj.name.startswith(PREFIX):
            continue
        master_name = (
            obj.instance_collection.name.lower() if obj.instance_collection else ""
        )
        has_nodes = any(
            modifier.type == "NODES" and modifier.show_render
            for modifier in obj.modifiers
        )
        is_heavy_instance = bool(master_name) and any(
            token in master_name for token in master_tokens
        )
        is_heavy_scatter = has_nodes or any(
            token in obj.name.lower() for token in object_tokens
        )
        if is_heavy_instance or is_heavy_scatter:
            obj.hide_render = True
            hidden.append(obj.name)
    log(f"light vegetation preview hid {len(hidden)} expensive instances/scatters")
    return hidden


def render_stills(scene, cams, width: int, height: int, engine: str, only_still=None):
    configure_render(scene, width, height, engine)
    scene.render.image_settings.file_format = "PNG"
    stills = [
        ("00_mission_overview.png", cams["overview"], 33),
        ("01_depart_home.png", cams["home"], 7),
        ("02_crosswalk_outbound.png", cams["crosswalk"], 35),
        ("03_arrive_fresh_mart.png", cams["shop"], 64),
        ("04_shopping_complete.png", cams["shop"], 70),
        ("05_crosswalk_return.png", cams["crosswalk"], 91),
        ("06_arrive_home.png", cams["home"], 101),
    ]
    if only_still is not None:
        stills = [stills[only_still]]
    for filename, cam, frame in stills:
        scene.frame_set(frame)
        scene.camera = cam
        scene.render.filepath = str(OUT / filename)
        started = time.time()
        bpy.ops.render.render(write_still=True)
        log(f"rendered {filename} in {time.time() - started:.1f}s")


def render_video(scene, cams, width: int, height: int, engine: str, frame_step: int):
    configure_render(scene, width, height, engine)
    scene.frame_step = frame_step
    scene.render.fps = max(1, FPS // frame_step)
    scene.camera = cams["follow"]
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(OUT / "urban_v1_full_07_agent_demo.mp4")
    started = time.time()
    bpy.ops.render.render(animation=True)
    log(f"rendered MP4 in {time.time() - started:.1f}s")


def write_readme(args):
    text = f"""# Urban Agent Demo

This is a lightweight paper-visualization demo over the original
`urban_v1_full_07.blend` scene.  The original 5 GB scene was not duplicated.

Mission: a four-wheel mobile manipulator exits the residential front door,
follows the sidewalk, crosses at the zebra crossing, reaches Fresh Mart, loads
groceries, and returns home.  Cyan encodes the outbound route; orange encodes
the loaded return route.

The current motion is a deterministic kinematic animation for fast visual
evaluation.  It is not yet collision-checked physics or closed-loop navigation.
The small `urban_v1_full_07_agent_overlay.blend` can be appended to the source
scene and contains the robot, task route, markers, animation, and cameras.

Generated results:

- `00_mission_overview.png`: full task and bidirectional route.
- `01_depart_home.png` through `06_arrive_home.png`: action keyframes.
- `urban_v1_full_07_agent_demo.mp4`: 8.5-second following-camera demo.
- `video_contact_sheet.png`: quick MP4 quality-control overview.
- `urban_v1_full_07_agent_overlay.blend`: reusable 3D overlay (about 140 KB).
- `mission_manifest.json`: exact route points, frames, stages, and visual encoding.
- `scene_landmarks.json`: extracted source-scene landmarks used to place the route.

Rebuild/render command:

```bash
{_wb_BLENDER_BIN} -b \\
  {SOURCE_BLEND} \\
  --python {ROOT / 'scripts/create_urban_v1_full_07_agent_demo.py'} -- --mode all
```

Render configuration: {args.engine}, stills {args.still_width}x{args.still_height},
video {args.video_width}x{args.video_height} sampled every {args.video_step} frame(s)
at {max(1, FPS // args.video_step)} fps.  Use `--engine eevee`
for a slower material render when GPU resources are available.  The default
`--vegetation light` omits expensive scatter/tree instances while retaining the
urban geometry; use `--vegetation full` for the complete scene.
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if args.vegetation == "light":
        simplify_vegetation_for_preview()
    coll, _, cams = build_demo(write_overlay=args.mode in ("build", "all"))
    write_readme(args)
    scene = bpy.context.scene
    if args.mode in ("stills", "all"):
        render_stills(
            scene,
            cams,
            args.still_width,
            args.still_height,
            args.engine,
            args.only_still,
        )
    if args.mode in ("video", "all"):
        render_video(
            scene,
            cams,
            args.video_width,
            args.video_height,
            args.engine,
            args.video_step,
        )
    log(
        f"complete mode={args.mode} objects={len(coll.all_objects)} elapsed={time.time() - started:.1f}s"
    )


if __name__ == "__main__":
    main()
