"""Render complete native-scale Infinigen Indoor views from all45_09.

The renderer isolates one genuine Indoor floor instance at a time from the
saved production scene. It combines each solve's authored Infinigen camera rig
with complete-plan, two-sided dollhouse, and room-composition views. The rich
showcase residence receives substantially more views than either companion.
Normal rig views preserve the full room shell. Cutaways are render-only and
never saved.
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


import json
import math
import os
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09"
RENDERS = OUT / "renders"
PREVIEWS = OUT / "interior_previews"
PREFIX = "all45_09:indoor_render:"
VALIDATE = os.environ.get("C2W_INTERIOR_VALIDATE", "0") == "1"
INDOOR_SOURCES = [
    OUT / "indoor_sources/showcase/scene.blend",
    OUT / "indoor_sources/companion_b/scene.blend",
    OUT / "indoor_sources/companion_b/scene.blend",
]


def world_point(instance, source_point):
    return instance.matrix_world @ Vector(source_point)


def object_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "min": Vector(
            tuple(min(point[axis] for point in corners) for axis in range(3))
        ),
        "max": Vector(
            tuple(max(point[axis] for point in corners) for axis in range(3))
        ),
    }


def bounds_center(bounds):
    return (bounds["min"] + bounds["max"]) * 0.5


def combine_bounds(objects):
    bounds = [object_bounds(obj) for obj in objects]
    return {
        "min": Vector(
            tuple(min(item["min"][axis] for item in bounds) for axis in range(3))
        ),
        "max": Vector(
            tuple(max(item["max"][axis] for item in bounds) for axis in range(3))
        ),
    }


def room_floor(master, room_type, tokens=None):
    candidates = [
        obj
        for obj in master.all_objects
        if obj.type == "MESH"
        and obj.name.startswith(room_type + "_")
        and ".floor" in obj.name
    ]
    if not candidates:
        raise RuntimeError(f"{master.name} has no generated {room_type} floor")
    if tokens:
        # A solve may contain multiple rooms of the same semantic type. Select
        # the one that actually contains the most requested furnishings rather
        # than relying on lexical object order.
        candidates.sort(
            key=lambda floor: len(subject_objects(master, tokens, floor)),
            reverse=True,
        )
        return candidates[0]
    return sorted(candidates, key=lambda obj: obj.name)[0]


def room_floors(master):
    floors = [
        obj for obj in master.all_objects if obj.type == "MESH" and ".floor" in obj.name
    ]
    if not floors:
        raise RuntimeError(f"{master.name} contains no generated room floors")
    return floors


def room_catalog(master):
    catalog = {}
    for room_type in ("living-room", "dining-room", "kitchen", "bedroom", "bathroom"):
        floor = room_floor(master, room_type)
        bounds = object_bounds(floor)
        catalog[room_type] = {
            "floor_object": floor.name,
            "min": [round(value, 4) for value in bounds["min"]],
            "max": [round(value, 4) for value in bounds["max"]],
        }
    return catalog


def source_object_center(obj):
    return bounds_center(object_bounds(obj))


FLOOR_TRIANGLE_CACHE = {}


def floor_triangles_xy(floor):
    key = floor.as_pointer()
    if key in FLOOR_TRIANGLE_CACHE:
        return FLOOR_TRIANGLE_CACHE[key]
    triangles = []
    matrix = floor.matrix_world
    normal_matrix = matrix.to_3x3()
    floor.data.calc_loop_triangles()
    for triangle in floor.data.loop_triangles:
        polygon = floor.data.polygons[triangle.polygon_index]
        normal = (normal_matrix @ polygon.normal).normalized()
        if abs(normal.z) < 0.75:
            continue
        vertices = [
            matrix @ floor.data.vertices[index].co for index in triangle.vertices
        ]
        triangles.append(
            tuple((float(vertex.x), float(vertex.y)) for vertex in vertices)
        )
    FLOOR_TRIANGLE_CACHE[key] = triangles
    return triangles


def point_in_triangle_xy(point, triangle, tolerance=0.02):
    px, py = float(point.x), float(point.y)

    def edge(a, b):
        return (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])

    values = [edge(triangle[index], triangle[(index + 1) % 3]) for index in range(3)]
    return not (
        any(value < -tolerance for value in values)
        and any(value > tolerance for value in values)
    )


def floor_contains_xy(floor, point):
    return any(
        point_in_triangle_xy(point, triangle) for triangle in floor_triangles_xy(floor)
    )


def subject_objects(master, tokens, room_floor=None):
    matches = []
    for obj in master.all_objects:
        if obj.type != "MESH" or ".spawn_asset(" not in obj.name:
            continue
        if not any(token in obj.name for token in tokens):
            continue
        center = source_object_center(obj)
        if room_floor is not None and not floor_contains_xy(room_floor, center):
            continue
        matches.append(obj)
    return matches


def whole_floor_camera_points(master, oblique=False, reverse=False):
    floors = room_floors(master)
    bounds = combine_bounds(floors)
    center = bounds_center(bounds)
    if oblique:
        span_x = bounds["max"].x - bounds["min"].x
        span_y = bounds["max"].y - bounds["min"].y
        direction = -1.0 if reverse else 1.0
        location = Vector(
            (
                center.x + direction * span_x * 0.82,
                center.y - direction * span_y * 0.82,
                bounds["max"].z + 15.0,
            )
        )
        target = Vector((center.x, center.y, bounds["min"].z + 0.45))
    else:
        span_x = bounds["max"].x - bounds["min"].x
        span_y = bounds["max"].y - bounds["min"].y
        # The showcase solve is substantially longer than the previous source
        # plan.  Derive the top-camera height from its real floor extents so no
        # rooms are clipped at the portrait axis of the 1100x700 render.
        height = max(24.0, span_y * 1.42, span_x * 0.98)
        location = Vector((center.x, center.y, bounds["max"].z + height))
        target = Vector((center.x, center.y, bounds["min"].z + 0.35))
    return location, target, [obj.name for obj in floors]


def composition_camera_points(master, room_type, tokens, reverse=False, diagonal=False):
    floor = room_floor(master, room_type, tokens)
    room_bounds = object_bounds(floor)
    subjects = subject_objects(master, tokens, floor)
    if not subjects:
        subjects = subject_objects(master, tokens)
    focus_bounds = combine_bounds(subjects) if subjects else room_bounds
    target = bounds_center(focus_bounds)
    target.z = room_bounds["min"].z + 0.9
    width = max(3.0, room_bounds["max"].x - room_bounds["min"].x)
    depth = max(3.0, room_bounds["max"].y - room_bounds["min"].y)
    focus_width = max(1.0, focus_bounds["max"].x - focus_bounds["min"].x)
    focus_depth = max(1.0, focus_bounds["max"].y - focus_bounds["min"].y)
    # Use an elevated architectural composition rather than a near-horizontal
    # side elevation.  Large showcase rooms are 9--13 m across; a fixed 3 m
    # camera height reduced their furniture to a thin line on the horizon.
    # The distance-derived height keeps the whole genuine room legible while
    # remaining substantially closer than a complete-plan/dollhouse view.
    distance = max(4.8, max(focus_width, focus_depth) * 1.35, max(width, depth) * 0.62)
    camera_z = room_bounds["min"].z + max(5.4, distance * 0.78)
    if diagonal:
        direction = 1.0 if reverse else -1.0
        location = Vector(
            (
                target.x + direction * distance * 0.82,
                target.y - direction * distance * 0.82,
                camera_z,
            )
        )
    elif focus_width >= focus_depth:
        y = target.y + distance if reverse else target.y - distance
        location = Vector((target.x, y, camera_z))
    else:
        x = target.x + distance if reverse else target.x - distance
        location = Vector((x, target.y, camera_z))
    return location, target, [obj.name for obj in subjects], floor.name


def native_camera_specs():
    specs = {}
    for source_index, path in enumerate(INDOOR_SOURCES):
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.collections = [
                name
                for name in source.collections
                if name in {"cameras", "camera_rigs"}
            ]
        cameras = [
            obj
            for collection in filter(None, target.collections)
            for obj in collection.all_objects
            if obj.type == "CAMERA"
        ]
        camera = min(cameras, key=lambda obj: abs(float(obj.location.x)))
        matrix = camera.matrix_basis
        child = camera
        parent = camera.parent
        while parent is not None:
            matrix = parent.matrix_basis @ child.matrix_parent_inverse @ matrix
            child, parent = parent, parent.parent
        location = matrix.translation
        forward = matrix.to_quaternion() @ Vector((0, 0, -1))
        specs[source_index] = {
            "source_blend": str(path),
            "camera_name": camera.name,
            "source_location": location,
            "source_target": location + forward * 5.0,
            "fov": math.degrees(camera.data.angle),
        }
    return specs


def add_camera(name, instance, source_location, source_target, fov):
    location = world_point(instance, source_location)
    target = world_point(instance, source_target)
    data = bpy.data.cameras.new(PREFIX + name + "_data")
    data.lens_unit = "FOV"
    data.angle = math.radians(fov)
    data.clip_start = 0.025
    data.clip_end = 500.0
    camera = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    return camera, target


def add_area_light(name, location, target, energy, size, color):
    data = bpy.data.lights.new(PREFIX + name + "_data", "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    return light


def add_room_lights(name, camera, target):
    warm = add_area_light(
        name + "_camera_fill",
        camera.location + Vector((0, 0, 0.35)),
        target,
        560,
        2.8,
        (1.0, 0.82, 0.68),
    )
    neutral = add_area_light(
        name + "_ceiling_fill",
        target + Vector((0, 0, 1.75)),
        target,
        470,
        2.4,
        (0.82, 0.90, 1.0),
    )
    return [warm, neutral]


def furniture_counts(master):
    names = [obj.name for obj in master.all_objects]
    categories = {
        "beds": ("BedFactory",),
        "sofas": ("SofaFactory",),
        "chairs": ("ChairFactory",),
        "dining_tables": ("TableDiningFactory",),
        "side_and_coffee_tables": (
            "TableCoffeeFactory",
            "TableSideFactory",
            "SideTableFactory",
        ),
        "kitchen_cabinets": ("KitchenCabinetFactory", "SingleCabinetFactory"),
        "kitchen_spaces": ("KitchenSpaceFactory",),
        "ovens": ("OvenFactory",),
        "dishwashers": ("DishwasherFactory",),
        "tv_stands": ("TVStandFactory",),
        "bookcases_and_shelves": ("BookcaseFactory", "ShelfFactory"),
        "rugs": ("RugFactory",),
        "sanitary_fixtures": ("ToiletFactory", "SinkFactory"),
        "plants": ("PlantContainerFactory",),
        "lamps": ("LampFactory",),
    }
    counts = {
        category: sum(
            ".spawn_asset(" in name and any(token in name for token in tokens)
            for name in names
        )
        for category, tokens in categories.items()
    }
    counts["all_placed_asset_objects"] = sum(".spawn_asset(" in name for name in names)
    counts["furniture_and_display_category_total"] = sum(
        value
        for category, value in counts.items()
        if category not in {"all_placed_asset_objects"}
    )
    return counts


def hide_override(objects):
    states = [(obj, bool(obj.hide_render)) for obj in dict.fromkeys(objects)]
    for obj, _ in states:
        obj.hide_render = True
    return states


def restore_hidden(states):
    for obj, hidden in states:
        obj.hide_render = hidden


def architecture_for_cutaway(master, mode, active_room_type=None):
    if mode == "none":
        return []
    if mode == "ceiling_exterior":
        tokens = (".ceiling", ".exterior")
    elif mode == "room_context":
        if active_room_type is None:
            raise RuntimeError("room_context requires an active room type")
        # Room compositions use an outside-looking-in camera.  Hide every room
        # shell surface, including the active room shell, so walls cannot block
        # the furniture.  Floors and all genuine assets remain visible.
        tokens = (".wall", ".ceiling", ".exterior")
        return [
            obj
            for obj in master.all_objects
            if any(token in obj.name for token in tokens)
        ]
    else:
        tokens = (".wall", ".ceiling", ".exterior")
    return [
        obj for obj in master.all_objects if any(token in obj.name for token in tokens)
    ]


def objects_outside_bounds(master, bounds, margin):
    outside = set()
    master_objects = set(master.all_objects)
    for obj in master.all_objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT"}:
            continue
        obj_bounds = object_bounds(obj)
        center = bounds_center(obj_bounds)
        outside_xy = not (
            bounds["min"].x - margin <= center.x <= bounds["max"].x + margin
            and bounds["min"].y - margin <= center.y <= bounds["max"].y + margin
        )
        # Some Indoor source blends retain an unplaced door/window factory
        # object at the source origin. Its geometry straddles Z=0 and appears
        # as a floating panel beside otherwise valid plans. Placed room assets
        # rest on the generated floor; reject only the clearly subterranean
        # source remnants and their child meshes.
        unplaced_source_remnant = obj_bounds["min"].z < bounds["min"].z - 0.15
        if outside_xy or unplaced_source_remnant:
            outside.add(obj)
            if unplaced_source_remnant:
                outside.update(
                    child for child in obj.children_recursive if child in master_objects
                )
    return list(outside)


def composition_exclusions(master, active_floor_name, subject_names):
    """Hide other room floors/assets using actual floor polygons, not AABBs."""
    active_floor = next(
        obj for obj in room_floors(master) if obj.name == active_floor_name
    )
    other_floors = [obj for obj in room_floors(master) if obj.name != active_floor_name]
    exclusions = set(other_floors)
    keep = set(subject_names)
    for obj in master.all_objects:
        if obj.name in keep or obj.type != "MESH" or ".spawn_asset(" not in obj.name:
            continue
        if not floor_contains_xy(active_floor, source_object_center(obj)):
            exclusions.add(obj)
    return list(exclusions)


def isolate_target_scene(instances, target_instance):
    for obj in instances:
        obj.hide_render = obj != target_instance
    # Source master objects live only in unlinked collections and therefore are
    # absent from scene.objects. Hide every production-scene object so exterior
    # roofs, towers, and landscape cannot occlude an Indoor-only camera.
    for obj in bpy.context.scene.objects:
        if obj != target_instance:
            obj.hide_render = True


def configure_render(scene):
    if VALIDATE:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.resolution_x, scene.render.resolution_y = 640, 400
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 40
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.02
        scene.render.resolution_x, scene.render.resolution_y = 1100, 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"


def main():
    started = time.time()
    output_dir = PREVIEWS if VALIDATE else RENDERS
    output_dir.mkdir(parents=True, exist_ok=True)
    masters = sorted(
        [
            collection
            for collection in bpy.data.collections
            if collection.get("native_infinigen_indoor") is True
        ],
        key=lambda collection: int(collection.get("source_index", 0)),
    )
    if len(masters) != 3:
        raise RuntimeError(
            f"Expected three native Infinigen Indoor production masters, found {len(masters)}"
        )
    instances = sorted(
        [
            obj
            for obj in bpy.data.objects
            if obj.get("native_infinigen_indoor") is True
            and obj.type == "EMPTY"
            and obj.instance_type == "COLLECTION"
            and obj.instance_collection is not None
        ],
        key=lambda obj: (
            str(obj.get("building_name", "")),
            int(obj.get("floor_index", 0)),
        ),
    )
    if len(instances) != 6:
        raise RuntimeError(
            f"Expected 6 low-rise Indoor floor instances, found {len(instances)}"
        )
    if any(
        not 0.95 <= float(obj.get("native_scale_xy", 0.0)) <= 1.08 for obj in instances
    ):
        raise RuntimeError(
            "A low-rise Indoor instance is outside the native-scale quality range"
        )
    prohibited_tokens = ("placeholder", "toy", "proxy", "blob", ".bbox_")
    prohibited = [
        obj.name
        for master in masters
        for obj in master.all_objects
        if any(token in obj.name.lower() for token in prohibited_tokens)
    ]
    if prohibited:
        raise RuntimeError(
            f"Degenerate/proxy geometry reached an all45_09 Indoor production master: {prohibited[:12]}"
        )

    primary = next(
        obj
        for obj in instances
        if obj.get("building_name") == "townhouse_01"
        and int(obj.get("floor_index")) == 0
    )
    secondary = next(
        obj
        for obj in instances
        if obj.get("building_name") == "townhouse_02"
        and int(obj.get("floor_index")) == 0
    )
    tertiary = next(
        obj
        for obj in instances
        if obj.get("building_name") == "townhouse_03"
        and int(obj.get("floor_index")) == 0
    )
    targets = {"a": primary, "b": secondary, "c": tertiary}
    if primary.get("interior_role") != "showcase_rich":
        raise RuntimeError("townhouse_01 must be the showcase_rich Indoor instance")
    if any(
        targets[key].get("interior_role") != "companion_reduced" for key in ("b", "c")
    ):
        raise RuntimeError(
            "townhouse_02 and townhouse_03 must be companion_reduced Indoor instances"
        )
    role_metrics = {
        key: furniture_counts(target.instance_collection)
        for key, target in targets.items()
    }
    showcase_assets = role_metrics["a"]["all_placed_asset_objects"]
    companion_assets = [
        role_metrics[key]["all_placed_asset_objects"] for key in ("b", "c")
    ]
    if showcase_assets <= max(companion_assets):
        raise RuntimeError(
            f"Showcase furniture/display count must exceed both companions: "
            f"showcase={showcase_assets}, companions={companion_assets}"
        )
    rigs = native_camera_specs()
    specs = [
        (
            "07_showcase_complete_floorplan",
            "a",
            "floorplan",
            None,
            68,
            "ceiling_exterior",
            "Complete showcase plan with all generated rooms, walls, furniture, and displays",
        ),
        (
            "08_showcase_native_camera",
            "a",
            "native",
            None,
            None,
            "none",
            "Original camera rig authored by the showcase Infinigen Indoor solve",
        ),
        (
            "09_showcase_dollhouse_front",
            "a",
            "dollhouse",
            None,
            64,
            "ceiling_exterior",
            "Front oblique showcase dollhouse retaining all room walls",
        ),
        (
            "10_showcase_dollhouse_rear",
            "a",
            "dollhouse_reverse",
            None,
            64,
            "ceiling_exterior",
            "Reverse oblique showcase dollhouse completing spatial coverage",
        ),
        (
            "11_showcase_living_room",
            "a",
            "composition",
            (
                "living-room",
                (
                    "SofaFactory",
                    "TVStandFactory",
                    "TableCoffeeFactory",
                    "ChairFactory",
                    "ShelfFactory",
                    "RugFactory",
                ),
            ),
            68,
            "room_context",
            "Showcase living room and its authored furnishings",
        ),
        (
            "12_showcase_living_room_reverse",
            "a",
            "composition_reverse",
            (
                "living-room",
                (
                    "SofaFactory",
                    "TVStandFactory",
                    "TableCoffeeFactory",
                    "ChairFactory",
                    "ShelfFactory",
                    "RugFactory",
                ),
            ),
            68,
            "room_context",
            "Reverse showcase living-room view",
        ),
        (
            "13_showcase_kitchen",
            "a",
            "composition",
            (
                "kitchen",
                (
                    "KitchenCabinetFactory",
                    "SingleCabinetFactory",
                    "KitchenSpaceFactory",
                    "OvenFactory",
                    "DishwasherFactory",
                ),
            ),
            68,
            "room_context",
            "Showcase kitchen cabinetry, appliances, and circulation",
        ),
        (
            "14_showcase_kitchen_reverse",
            "a",
            "composition_reverse",
            (
                "kitchen",
                (
                    "KitchenCabinetFactory",
                    "SingleCabinetFactory",
                    "KitchenSpaceFactory",
                    "OvenFactory",
                    "DishwasherFactory",
                ),
            ),
            68,
            "room_context",
            "Reverse showcase kitchen view",
        ),
        (
            "15_showcase_dining_room",
            "a",
            "composition_diagonal",
            ("dining-room", ("TableDiningFactory", "ChairFactory")),
            72,
            "room_context",
            "Showcase dining room and surrounding display objects",
        ),
        (
            "16_showcase_bedroom",
            "a",
            "composition_diagonal",
            ("bedroom", ("BedFactory", "WardrobeFactory", "SideTableFactory")),
            72,
            "room_context",
            "Showcase bedroom with complete authored context",
        ),
        (
            "17_showcase_bathroom",
            "a",
            "composition",
            (
                "bathroom",
                ("ToiletFactory", "SinkFactory", "BathtubFactory", "ShowerFactory"),
            ),
            72,
            "room_context",
            "Showcase bathroom and sanitary fixtures",
        ),
        (
            "18_companion_a_complete_floorplan",
            "b",
            "floorplan",
            None,
            68,
            "ceiling_exterior",
            "Complete moderately furnished companion A plan",
        ),
        (
            "19_companion_a_native_camera",
            "b",
            "native",
            None,
            None,
            "none",
            "Original companion A Infinigen Indoor camera rig",
        ),
        (
            "20_companion_a_dollhouse",
            "b",
            "dollhouse",
            None,
            64,
            "ceiling_exterior",
            "Companion A dollhouse",
        ),
        (
            "21_companion_a_kitchen",
            "b",
            "composition",
            (
                "kitchen",
                (
                    "KitchenCabinetFactory",
                    "SingleCabinetFactory",
                    "KitchenSpaceFactory",
                    "OvenFactory",
                    "DishwasherFactory",
                ),
            ),
            68,
            "room_context",
            "Companion A kitchen",
        ),
        (
            "22_companion_b_complete_floorplan",
            "c",
            "floorplan",
            None,
            68,
            "ceiling_exterior",
            "Complete moderately furnished companion B plan",
        ),
        (
            "23_companion_b_native_camera",
            "c",
            "native",
            None,
            None,
            "none",
            "Original companion B Infinigen Indoor camera rig",
        ),
        (
            "24_companion_b_dollhouse",
            "c",
            "dollhouse",
            None,
            64,
            "ceiling_exterior",
            "Companion B dollhouse",
        ),
        (
            "25_companion_b_living_room",
            "c",
            "composition",
            (
                "living-room",
                (
                    "SofaFactory",
                    "TVStandFactory",
                    "ChairFactory",
                    "ShelfFactory",
                    "RugFactory",
                ),
            ),
            68,
            "room_context",
            "Companion B living room",
        ),
    ]
    if VALIDATE:
        # Layout/dollhouse framing was validated before the final render. This
        # fast pass focuses on all eye-level room-context compositions.
        validation_views = {
            "11_showcase_living_room",
            "12_showcase_living_room_reverse",
            "13_showcase_kitchen",
            "14_showcase_kitchen_reverse",
            "15_showcase_dining_room",
            "16_showcase_bedroom",
            "17_showcase_bathroom",
            "21_companion_a_kitchen",
            "25_companion_b_living_room",
        }
        specs = [spec for spec in specs if spec[0] in validation_views]

    scene = bpy.context.scene
    configure_render(scene)
    rendered = []
    for name, target_key, view_type, subject, fov, cutaway_mode, description in specs:
        target_instance = targets[target_key]
        target_master = target_instance.instance_collection
        isolate_target_scene(instances, target_instance)

        subject_names = []
        floor_names = []
        view_bounds = None
        composition_objects = []
        active_room_type = None
        if view_type == "native":
            rig = rigs[int(target_instance.get("source_index", 0))]
            source_location = rig["source_location"]
            source_target = rig["source_target"]
            fov = rig["fov"]
        elif view_type == "floorplan":
            source_location, source_target, floor_names = whole_floor_camera_points(
                target_master, oblique=False
            )
            view_bounds = combine_bounds(room_floors(target_master))
        elif view_type in {"dollhouse", "dollhouse_reverse"}:
            source_location, source_target, floor_names = whole_floor_camera_points(
                target_master, oblique=True, reverse=view_type == "dollhouse_reverse"
            )
            view_bounds = combine_bounds(room_floors(target_master))
        else:
            room_type, tokens = subject
            active_room_type = room_type
            (
                source_location,
                source_target,
                subject_names,
                floor_name,
            ) = composition_camera_points(
                target_master,
                room_type,
                tokens,
                reverse=view_type == "composition_reverse",
                diagonal=view_type == "composition_diagonal",
            )
            floor_names = [floor_name]
            # room_floor(..., tokens) above may select a different member when
            # a solve contains several bedrooms/living rooms.  Use that exact
            # floor for clipping too; otherwise the selected furniture can be
            # mistakenly hidden against another same-semantic room's bounds.
            active_floor = next(
                obj for obj in room_floors(target_master) if obj.name == floor_name
            )
            view_bounds = object_bounds(active_floor)
            composition_objects = composition_exclusions(
                target_master, floor_name, subject_names
            )

        outside_objects = []
        if view_bounds is not None:
            outside_objects = objects_outside_bounds(
                target_master,
                view_bounds,
                0.25
                if view_type in {"floorplan", "dollhouse", "dollhouse_reverse"}
                else 0.45,
            )
        architecture_objects = architecture_for_cutaway(
            target_master, cutaway_mode, active_room_type
        )
        hidden_states = hide_override(
            architecture_objects + outside_objects + composition_objects
        )
        camera, target = add_camera(
            name, target_instance, source_location, source_target, fov
        )
        lights = add_room_lights(name, camera, target)
        for obj in lights + [camera]:
            obj.hide_render = False
        scene.camera = camera
        filepath = output_dir / f"{name}.png"
        scene.render.filepath = str(filepath)
        bpy.ops.render.render(write_still=True)
        rendered.append(
            {
                "file": str(filepath),
                "description": description,
                "view_type": view_type,
                "instance": target_instance.name,
                "source_master": target_master.name,
                "source_camera": [round(value, 4) for value in source_location],
                "source_target": [round(value, 4) for value in source_target],
                "cutaway_mode": cutaway_mode,
                "temporarily_hidden_architecture": len(architecture_objects),
                "temporarily_hidden_outside_view_bounds": len(outside_objects),
                "temporarily_hidden_overlapping_room_objects": len(composition_objects),
                "room_floor_objects": floor_names,
                "subject_objects": subject_names,
            }
        )
        restore_hidden(hidden_states)
        for obj in lights + [camera]:
            bpy.data.objects.remove(obj, do_unlink=True)
        print(f"[all45_09 indoor] rendered {filepath.name}", flush=True)

    master_audits = [
        {
            "name": master.name,
            "source_blend": master.get("source_blend", ""),
            "interior_role": master.get("interior_role", ""),
            "object_count": len(master.all_objects),
            "room_catalog": room_catalog(master),
            "furniture_counts": furniture_counts(master),
            "normalized_chair_assets": int(master.get("normalized_chair_assets", 0)),
            "placeholder_objects": sum(
                "placeholder" in obj.name.lower() for obj in master.all_objects
            ),
        }
        for master in masters
    ]
    audit = {
        "source_blend": str(OUT / "urban_v3_all45_09.blend"),
        "validation_preview": VALIDATE,
        "native_infinigen_indoor_masters": master_audits,
        "native_camera_rigs": {
            str(index): {
                "source_blend": rig["source_blend"],
                "camera_name": rig["camera_name"],
                "source_location": [
                    round(value, 5) for value in rig["source_location"]
                ],
                "source_target": [round(value, 5) for value in rig["source_target"]],
                "fov": round(rig["fov"], 4),
            }
            for index, rig in rigs.items()
        },
        "lowrise_indoor_instance_count": len(instances),
        "instance_native_scale_range": [
            round(min(float(obj["native_scale_xy"]) for obj in instances), 4),
            round(max(float(obj["native_scale_xy"]) for obj in instances), 4),
        ],
        "render_engine": scene.render.engine,
        "samples": None if VALIDATE else 40,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "scene_isolation": "all production-scene geometry hidden render-only; target genuine Indoor instance retained",
        "view_policy": "showcase: native rig + complete plan + two-sided wall-preserving dollhouse + every principal room + reverse living/kitchen views; companions: concise plan/native/dollhouse/room coverage",
        "temporary_cutaway": {
            "native_views": "none",
            "floorplan_and_dollhouse": "ceilings and source exterior surfaces; room walls retained",
            "composition_views": "all room shell walls/ceilings/exteriors hidden render-only; target floor and genuine room assets retained",
            "saved_to_blend": False,
        },
        "toy_or_placeholder_assets": 0,
        "prohibited_asset_name_tokens": list(prohibited_tokens),
        "role_furnishing_metrics": role_metrics,
        "showcase_render_count": sum(item[1] == "a" for item in specs),
        "companion_render_counts": {
            "townhouse_02": sum(item[1] == "b" for item in specs),
            "townhouse_03": sum(item[1] == "c" for item in specs),
        },
        "renders": rendered,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    audit_name = (
        "lowrise_interior_preview_audit.json"
        if VALIDATE
        else "lowrise_interior_render_audit.json"
    )
    (OUT / audit_name).write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("LOWRISE_INTERIOR_AUDIT=" + json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
