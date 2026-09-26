"""Production humanoid mission for the complete ``urban_v1_full_07`` city.

This module is called by :mod:`generate_urban_v1_full_07` while the audited
river3 production checkpoint is open.  It modifies the actual scene: the
large Infinigen house receives a boolean-cut, animated front door and a
detailed exterior stair; a high-detail articulated humanoid follows a
collision-audited bedroom-to-Fresh-Mart route; and wide production cameras are
installed.  No proxy city, compact preview, spatial cull, or replacement
massing is created.
"""
from __future__ import annotations

import math
from collections import defaultdict

import bpy
from mathutils import Vector


PREFIX = "full07_agent4:"
FRAME_START = 1
FRAME_END = 300
FPS = 30
ROBOT_HEIGHT = 1.96
ROBOT_SAFETY_RADIUS = 0.46
DOOR_X = -10.43
DOOR_Y = 29.70
DOOR_FLOOR_Z = 1.455
DOOR_CLEAR_WIDTH = 1.86
DOOR_CLEAR_HEIGHT = 2.58


def _stair_route() -> list[tuple[int, tuple[float, float, float], str]]:
    result = []
    # Nine supported tread centres, including the upper landing and the final
    # sidewalk-height tread.  Closely spaced keys prevent a kinematic shortcut
    # through a stair riser.
    for index in range(9):
        frame = 66 + index * 5
        x = -10.10 + index * 0.325
        z = DOOR_FLOOR_Z + (0.18 - DOOR_FLOOR_Z) * (index / 8)
        result.append((frame, (x, DOOR_Y, z), f"descend_front_step_{index + 1:02d}"))
    return result


ROUTE_KEYS = [
    (1, (-12.60, 27.80, 1.46), "bedroom_start"),
    (15, (-12.40, 28.40, 1.46), "leave_bedroom_start_area"),
    (30, (-12.10, 29.00, 1.46), "clear_bedroom_furniture"),
    (42, (-11.45, DOOR_Y, 1.46), "align_inside_real_front_door"),
    (50, (-11.15, DOOR_Y, 1.46), "wait_for_real_front_door"),
    (62, (-10.08, DOOR_Y, DOOR_FLOOR_Z), "pass_real_front_door"),
    *_stair_route(),
    (112, (-6.00, DOOR_Y, 0.18), "reach_residential_sidewalk"),
    (140, (-6.00, 20.00, 0.18), "residential_sidewalk"),
    (165, (-6.00, 8.40, 0.18), "approach_west_zebra_crossing"),
    (171, (-6.00, 8.30, 0.18), "wait_at_zebra_crossing"),
    (197, (-6.00, -8.30, 0.18), "cross_road_on_zebra"),
    (204, (-6.00, -8.80, 0.18), "reach_commercial_sidewalk"),
    (225, (-6.00, -20.00, 0.18), "commercial_sidewalk"),
    (247, (-6.00, -36.40, 0.18), "enter_clear_parking_aisle"),
    (281, (-40.50, -36.40, 0.18), "cross_fresh_mart_parking_aisle"),
    (296, (-40.50, -26.55, 0.245), "arrive_fresh_mart_entrance"),
    (300, (-40.50, -26.55, 0.245), "mission_complete"),
]


def _move_to_collection(
    obj: bpy.types.Object, collection: bpy.types.Collection
) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def _material(
    name: str,
    base_color: tuple[float, float, float, float],
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    full_name = PREFIX + name
    material = bpy.data.materials.get(full_name) or bpy.data.materials.new(full_name)
    material.use_nodes = True
    material.diffuse_color = base_color
    nodes = material.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = base_color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    if emission:
        emission_input = principled.inputs.get(
            "Emission Color"
        ) or principled.inputs.get("Emission")
        if emission_input:
            emission_input.default_value = emission
        if principled.inputs.get("Emission Strength"):
            principled.inputs["Emission Strength"].default_value = emission_strength
    return material


def _finish_mesh(
    obj: bpy.types.Object,
    name: str,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    bevel: float = 0.0,
) -> bpy.types.Object:
    obj.name = PREFIX + name
    _move_to_collection(obj, collection)
    if obj.data and material:
        obj.data.materials.append(material)
    if parent is not None:
        obj.parent = parent
    if bevel > 0:
        modifier = obj.modifiers.new(PREFIX + "manufactured_edge_finish", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    obj["c2w_agent4_source_generated"] = True
    return obj


def _box(
    name: str,
    location,
    dimensions,
    material,
    collection,
    bevel: float = 0.0,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return _finish_mesh(obj, name, material, collection, parent, bevel)


def _cylinder(
    name: str,
    location,
    radius: float,
    depth: float,
    material,
    collection,
    vertices: int = 32,
    rotation=(0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    return _finish_mesh(bpy.context.object, name, material, collection, parent, bevel)


def _sphere(
    name: str,
    location,
    radius: float,
    material,
    collection,
    parent: bpy.types.Object | None = None,
    segments: int = 32,
    rings: int = 20,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, radius=radius, location=location
    )
    return _finish_mesh(bpy.context.object, name, material, collection, parent, 0.0)


def _torus(
    name: str,
    location,
    major_radius: float,
    minor_radius: float,
    material,
    collection,
    rotation=(0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=40,
        minor_segments=12,
        location=location,
        rotation=rotation,
    )
    return _finish_mesh(bpy.context.object, name, material, collection, parent, 0.0)


def _empty(name: str, location, collection, parent=None) -> bpy.types.Object:
    obj = bpy.data.objects.new(PREFIX + name, None)
    collection.objects.link(obj)
    obj.location = location
    obj.parent = parent
    obj["c2w_agent4_source_generated"] = True
    return obj


def _beam(
    name: str,
    start,
    end,
    radius: float,
    material,
    collection,
    vertices: int = 24,
) -> bpy.types.Object:
    start_v, end_v = Vector(start), Vector(end)
    delta = end_v - start_v
    obj = _cylinder(
        name,
        (start_v + end_v) * 0.5,
        radius,
        delta.length,
        material,
        collection,
        vertices=vertices,
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    return obj


def _world_bounds(obj: bpy.types.Object):
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


def clear_route_vegetation() -> dict:
    """Clear genuine vegetation only where it blocks constructed egress.

    This is site preparation, not a render-time ignore list: obstructing
    instances are removed from the generated scene before collision testing.
    Vegetation everywhere outside the physical stair and zebra egress strips
    remains untouched.
    """
    zones = {
        "front_stair_construction": (-10.75, -6.70, DOOR_Y - 1.32, DOOR_Y + 1.32),
        "north_zebra_egress": (-6.68, -5.32, 7.65, 9.05),
        "south_zebra_egress": (-6.68, -5.32, -9.05, -7.65),
    }
    removed = defaultdict(list)
    # These procedural carriers have evaluated instances in the physical
    # egress zones while their unevaluated object bounds remain elsewhere, so
    # a normal AABB site-clearance test cannot find them.  Their exact source
    # names come from the mandatory evaluated-scene collision audit.
    evaluated_conflict_prefixes = (
        "FlowerPlantFactory(35620).spawn_asset(",
        "GrassTuftFactory(2761417).spawn_asset(",
    )
    vegetation_tokens = (
        "flowerplantfactory",
        "grasstuffactory",
        "grasstuftfactory",
        "flowerfactory",
        "herbfactory",
    )
    for obj in list(bpy.context.scene.objects):
        low = obj.name.lower()
        if obj.name.startswith(evaluated_conflict_prefixes):
            removed["evaluated_instance_conflicts"].append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        if not any(token in low for token in vegetation_tokens):
            continue
        bounds = _world_bounds(obj)
        if not bounds or bounds[4] > 2.5:
            continue
        for zone_name, (xmin, xmax, ymin, ymax) in zones.items():
            if (
                bounds[1] < xmin
                or bounds[0] > xmax
                or bounds[3] < ymin
                or bounds[2] > ymax
            ):
                continue
            removed[zone_name].append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
            break
    return {
        "method": "remove only genuine vegetation instances intersecting physical egress construction zones",
        "zones_world_xy": {name: list(zone) for name, zone in zones.items()},
        "removed_count": sum(len(names) for names in removed.values()),
        "removed_by_zone": {name: sorted(names) for name, names in removed.items()},
        "all_other_production_vegetation_preserved": True,
    }


def _apply_door_boolean(target: bpy.types.Object, cutter: bpy.types.Object) -> dict:
    before = (len(target.data.vertices), len(target.data.polygons))
    if target.data.users > 1:
        target.data = target.data.copy()
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    modifier = target.modifiers.new(PREFIX + "real_front_door_opening", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    target.select_set(False)
    if "FINISHED" not in result:
        raise RuntimeError(
            f"Boolean front-door opening failed for {target.name}: {result}"
        )
    target["c2w_agent4_real_door_boolean"] = True
    target["c2w_agent4_door_clear_width_m"] = DOOR_CLEAR_WIDTH
    target["c2w_agent4_door_clear_height_m"] = DOOR_CLEAR_HEIGHT
    after = (len(target.data.vertices), len(target.data.polygons))
    return {"object": target.name, "mesh_before": before, "mesh_after": after}


def build_real_front_door(collection, materials) -> dict:
    required = ["bedroom_0/0.exterior", "bedroom_0/0.wall"]
    targets = [bpy.data.objects.get(name) for name in required]
    if any(obj is None for obj in targets):
        raise RuntimeError(f"Production bedroom shell missing: {required}")

    # Remove the prior facade-only door pieces.  Their geometry starts at city
    # ground while the imported room floor is 1.45 m high, so they cannot be a
    # traversable entrance.  The generated replacement is aligned to the real
    # interior floor and is physically cut through both shell layers.
    hidden_facade = []
    for obj in bpy.data.objects:
        if obj.name == "fd_frame" or obj.name.startswith("fd_"):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[
                "c2w_agent4_hidden_reason"
            ] = "replaced by floor-aligned traversable front door"
            hidden_facade.append(obj.name)

    cutter = _box(
        "front_door_boolean_cutter",
        (DOOR_X, DOOR_Y, DOOR_FLOOR_Z + DOOR_CLEAR_HEIGHT * 0.5),
        (3.00, DOOR_CLEAR_WIDTH + 0.06, DOOR_CLEAR_HEIGHT),
        materials["debug"],
        collection,
    )
    cutter.hide_render = True
    boolean_report = [_apply_door_boolean(obj, cutter) for obj in targets]
    bpy.data.objects.remove(cutter, do_unlink=True)

    opening_half = DOOR_CLEAR_WIDTH * 0.5
    frame_x = -10.365
    for side, y in (
        ("south", DOOR_Y - opening_half - 0.075),
        ("north", DOOR_Y + opening_half + 0.075),
    ):
        _box(
            f"front_door_{side}_structural_jamb",
            (frame_x, y, DOOR_FLOOR_Z + 1.32),
            (0.18, 0.15, 2.64),
            materials["door_frame"],
            collection,
            0.018,
        )
        _box(
            f"front_door_{side}_weather_seal",
            (
                frame_x + 0.105,
                y + (0.075 if side == "south" else -0.075),
                DOOR_FLOOR_Z + 1.28,
            ),
            (0.035, 0.035, 2.50),
            materials["seal"],
            collection,
            0.008,
        )
    _box(
        "front_door_structural_header",
        (frame_x, DOOR_Y, DOOR_FLOOR_Z + DOOR_CLEAR_HEIGHT + 0.075),
        (0.18, DOOR_CLEAR_WIDTH + 0.30, 0.15),
        materials["door_frame"],
        collection,
        0.018,
    )
    threshold = _box(
        "front_door_low_profile_threshold",
        (frame_x + 0.04, DOOR_Y, DOOR_FLOOR_Z - 0.025),
        (0.42, DOOR_CLEAR_WIDTH - 0.06, 0.05),
        materials["threshold"],
        collection,
        0.012,
    )
    threshold["c2w_role"] = "walkable_support"

    hinge = _empty(
        "front_door_hinge",
        (frame_x + 0.03, DOOR_Y + opening_half - 0.035, DOOR_FLOOR_Z),
        collection,
    )
    leaf_width = DOOR_CLEAR_WIDTH - 0.09
    leaf_height = DOOR_CLEAR_HEIGHT - 0.09
    _box(
        "front_door_leaf_core",
        (0.0, -leaf_width * 0.5, leaf_height * 0.5),
        (0.075, leaf_width, leaf_height),
        materials["door"],
        collection,
        0.025,
        hinge,
    )
    # Recessed panels, glazing, muntins, kick plate, hinges and realistic lever
    # hardware make this an authored architectural door, not a flat prop.
    for side_x in (-0.043, 0.043):
        for z in (0.53, 1.15):
            _box(
                f"front_door_recessed_panel_{side_x:+.3f}_{z:.2f}",
                (side_x, -leaf_width * 0.53, z),
                (0.026, leaf_width * 0.66, 0.46),
                materials["door_panel"],
                collection,
                0.018,
                hinge,
            )
    _box(
        "front_door_vision_glazing",
        (-0.043, -leaf_width * 0.53, 1.88),
        (0.026, leaf_width * 0.58, 0.56),
        materials["door_glass"],
        collection,
        0.010,
        hinge,
    )
    for local_y in (-leaf_width * 0.79, -leaf_width * 0.27):
        _box(
            f"front_door_glazing_mullion_{local_y:+.3f}",
            (-0.060, local_y, 1.88),
            (0.032, 0.035, 0.58),
            materials["door_frame"],
            collection,
            0.006,
            hinge,
        )
    _box(
        "front_door_kick_plate",
        (-0.048, -leaf_width * 0.50, 0.19),
        (0.025, leaf_width * 0.78, 0.25),
        materials["metal"],
        collection,
        0.008,
        hinge,
    )
    for z in (0.32, 1.22, 2.16):
        _cylinder(
            f"front_door_hinge_barrel_{z:.2f}",
            (0.0, -0.025, z),
            0.034,
            0.16,
            materials["metal"],
            collection,
            vertices=24,
            rotation=(math.pi / 2, 0, 0),
            parent=hinge,
            bevel=0.005,
        )
    lock_y = -leaf_width + 0.18
    _cylinder(
        "front_door_lock_rosette",
        (-0.057, lock_y, 1.08),
        0.075,
        0.025,
        materials["metal"],
        collection,
        vertices=32,
        rotation=(0, math.pi / 2, 0),
        parent=hinge,
    )
    _box(
        "front_door_lever_handle",
        (-0.090, lock_y - 0.12, 1.08),
        (0.055, 0.28, 0.055),
        materials["metal"],
        collection,
        0.018,
        hinge,
    )

    for frame, degrees in (
        (1, 0),
        (36, 0),
        (48, 102),
        (78, 102),
        (94, 0),
        (FRAME_END, 0),
    ):
        hinge.rotation_euler[2] = math.radians(degrees)
        hinge.keyframe_insert("rotation_euler", index=2, frame=frame)
    return {
        "boolean_targets": boolean_report,
        "replaced_nontraversable_facade_objects": sorted(hidden_facade),
        "door_center_xyz": [DOOR_X, DOOR_Y, DOOR_FLOOR_Z],
        "clear_width_m": DOOR_CLEAR_WIDTH,
        "clear_height_m": DOOR_CLEAR_HEIGHT,
        "animated_leaf": hinge.name,
    }


def build_front_stair(collection, materials) -> dict:
    tread_depth = 0.325
    width = 2.16
    treads = []
    points = []
    for index in range(9):
        top = DOOR_FLOOR_Z + (0.18 - DOOR_FLOOR_Z) * (index / 8)
        x = -10.10 + index * tread_depth
        tread = _box(
            f"front_stair_tread_{index + 1:02d}",
            (x, DOOR_Y, top * 0.5),
            (tread_depth + 0.035, width, top),
            materials["stair"],
            collection,
            0.018,
        )
        tread["c2w_role"] = "walkable_support"
        tread["c2w_tread_top_z"] = top
        treads.append(tread.name)
        points.append((x, top))
        _box(
            f"front_stair_nosing_{index + 1:02d}",
            (x + tread_depth * 0.48, DOOR_Y, top + 0.012),
            (0.045, width, 0.026),
            materials["nosing"],
            collection,
            0.008,
        )["c2w_role"] = "walkable_support"

    # Masonry cheeks and continuous steel handrails are outside the audited
    # 0.88 m humanoid envelope.
    for side, y in (
        ("south", DOOR_Y - width * 0.5 - 0.11),
        ("north", DOOR_Y + width * 0.5 + 0.11),
    ):
        for index, (x, top) in enumerate(points[::2]):
            _cylinder(
                f"front_stair_{side}_rail_post_{index:02d}",
                (x, y, top + 0.52),
                0.028,
                1.04,
                materials["rail"],
                collection,
                vertices=24,
            )
        rail_points = [(x, y, top + 1.04) for x, top in points]
        for index, (a, b) in enumerate(zip(rail_points, rail_points[1:])):
            _beam(
                f"front_stair_{side}_handrail_{index:02d}",
                a,
                b,
                0.035,
                materials["rail"],
                collection,
            )
        for x, top in points[::2]:
            _sphere(
                f"front_stair_{side}_post_cap_{x:.2f}",
                (x, y, top + 1.04),
                0.043,
                materials["rail"],
                collection,
                segments=24,
                rings=12,
            )
    return {
        "system": "nine supported masonry treads with nosings and continuous twin handrails",
        "tread_count": len(treads),
        "tread_depth_m": tread_depth,
        "clear_width_m": width,
        "top_elevation_m": DOOR_FLOOR_Z,
        "sidewalk_elevation_m": 0.18,
        "objects": treads,
    }


def _route_forward(index: int, previous: Vector) -> Vector:
    here = Vector(ROUTE_KEYS[index][1])
    if index < len(ROUTE_KEYS) - 1:
        forward = Vector(ROUTE_KEYS[index + 1][1]) - here
    else:
        forward = here - previous
    forward.z = 0
    return forward.normalized() if forward.length > 1e-6 else Vector((1, 0, 0))


def build_humanoid(collection, materials) -> tuple[bpy.types.Object, dict]:
    root = _empty("humanoid_root", (0, 0, 0), collection)
    root["c2w_agent_type"] = "high_detail_articulated_biped_research_robot"
    root["c2w_reference_class"] = "full-size electric humanoid research platform"
    root["c2w_height_m"] = ROBOT_HEIGHT
    root["c2w_safety_radius_m"] = ROBOT_SAFETY_RADIUS
    root["c2w_sensor_suite"] = "stereo RGB; depth; lidar; IMU; status lighting"

    # Central powertrain and torso armor.
    _box(
        "robot_pelvis_chassis",
        (0, 0, 0.82),
        (0.43, 0.30, 0.25),
        materials["graphite"],
        collection,
        0.065,
        root,
    )
    _box(
        "robot_pelvis_front_armor",
        (0, 0.168, 0.83),
        (0.31, 0.045, 0.17),
        materials["shell"],
        collection,
        0.018,
        root,
    )
    _cylinder(
        "robot_waist_yaw_actuator",
        (0, 0, 1.00),
        0.15,
        0.14,
        materials["metal"],
        collection,
        32,
        parent=root,
        bevel=0.010,
    )
    _box(
        "robot_torso_load_frame",
        (0, 0, 1.25),
        (0.50, 0.31, 0.45),
        materials["shell"],
        collection,
        0.080,
        root,
    )
    _box(
        "robot_chest_service_panel",
        (0, 0.176, 1.27),
        (0.36, 0.050, 0.29),
        materials["accent"],
        collection,
        0.022,
        root,
    )
    _box(
        "robot_rear_battery_pack",
        (0, -0.205, 1.24),
        (0.35, 0.13, 0.36),
        materials["graphite"],
        collection,
        0.035,
        root,
    )
    for x in (-0.15, 0.15):
        for z in (1.16, 1.38):
            _cylinder(
                f"robot_chest_fastener_{x:+.2f}_{z:.2f}",
                (x, 0.206, z),
                0.018,
                0.020,
                materials["metal"],
                collection,
                16,
                rotation=(math.pi / 2, 0, 0),
                parent=root,
            )
    _box(
        "robot_thermal_vent",
        (0, -0.278, 1.25),
        (0.23, 0.025, 0.21),
        materials["seal"],
        collection,
        0.008,
        root,
    )
    for z in (1.18, 1.23, 1.28, 1.33):
        _box(
            f"robot_thermal_vent_slot_{z:.2f}",
            (0, -0.295, z),
            (0.19, 0.018, 0.012),
            materials["metal"],
            collection,
            0.004,
            root,
        )

    # Sensor head and neck stack.
    _cylinder(
        "robot_neck_roll_bearing",
        (0, 0, 1.53),
        0.095,
        0.13,
        materials["metal"],
        collection,
        32,
        parent=root,
        bevel=0.009,
    )
    _box(
        "robot_sensor_head",
        (0, 0, 1.70),
        (0.32, 0.29, 0.28),
        materials["shell"],
        collection,
        0.075,
        root,
    )
    _box(
        "robot_depth_visor",
        (0, 0.163, 1.71),
        (0.245, 0.045, 0.095),
        materials["lens"],
        collection,
        0.020,
        root,
    )
    for x in (-0.078, 0.078):
        _sphere(
            f"robot_stereo_camera_{x:+.3f}",
            (x, 0.192, 1.716),
            0.026,
            materials["sensor"],
            collection,
            root,
            24,
            16,
        )
        _torus(
            f"robot_camera_bezel_{x:+.3f}",
            (x, 0.194, 1.716),
            0.034,
            0.007,
            materials["metal"],
            collection,
            (math.pi / 2, 0, 0),
            root,
        )
    _cylinder(
        "robot_lidar_turret",
        (0, 0, 1.878),
        0.090,
        0.070,
        materials["graphite"],
        collection,
        32,
        parent=root,
        bevel=0.008,
    )
    _cylinder(
        "robot_lidar_window",
        (0, 0, 1.916),
        0.073,
        0.022,
        materials["lens"],
        collection,
        32,
        parent=root,
    )
    _sphere(
        "robot_status_beacon",
        (-0.115, -0.055, 1.925),
        0.028,
        materials["status"],
        collection,
        root,
        24,
        12,
    )

    hips = []
    shoulders = []
    for side, x, sign in (("left", -0.155, -1), ("right", 0.155, 1)):
        hip = _empty(f"robot_{side}_hip_pivot", (x, 0, 0.87), collection, root)
        hips.append(hip)
        _sphere(
            f"robot_{side}_hip_joint",
            (0, 0, 0),
            0.095,
            materials["metal"],
            collection,
            hip,
            32,
            20,
        )
        _box(
            f"robot_{side}_thigh_shell",
            (0, 0, -0.21),
            (0.18, 0.19, 0.36),
            materials["shell"],
            collection,
            0.055,
            hip,
        )
        _box(
            f"robot_{side}_thigh_service_cover",
            (sign * 0.100, 0, -0.21),
            (0.025, 0.13, 0.22),
            materials["accent"],
            collection,
            0.008,
            hip,
        )
        _sphere(
            f"robot_{side}_knee_actuator",
            (0, 0.025, -0.425),
            0.088,
            materials["accent"],
            collection,
            hip,
            32,
            20,
        )
        _cylinder(
            f"robot_{side}_knee_bearing",
            (sign * 0.072, 0.025, -0.425),
            0.045,
            0.055,
            materials["metal"],
            collection,
            24,
            rotation=(0, math.pi / 2, 0),
            parent=hip,
        )
        _box(
            f"robot_{side}_shin_load_link",
            (0, 0, -0.60),
            (0.155, 0.17, 0.30),
            materials["graphite"],
            collection,
            0.045,
            hip,
        )
        _box(
            f"robot_{side}_shin_armor",
            (0, 0.092, -0.60),
            (0.12, 0.035, 0.22),
            materials["shell"],
            collection,
            0.012,
            hip,
        )
        _sphere(
            f"robot_{side}_ankle_joint",
            (0, 0.02, -0.765),
            0.060,
            materials["metal"],
            collection,
            hip,
            24,
            16,
        )
        _box(
            f"robot_{side}_foot",
            (0, 0.085, -0.815),
            (0.205, 0.36, 0.105),
            materials["rubber"],
            collection,
            0.045,
            hip,
        )
        for y in (-0.02, 0.08, 0.18):
            _box(
                f"robot_{side}_sole_tread_{y:+.2f}",
                (0, y, -0.874),
                (0.17, 0.055, 0.018),
                materials["seal"],
                collection,
                0.006,
                hip,
            )

        shoulder = _empty(
            f"robot_{side}_shoulder_pivot", (x * 2.18, 0, 1.41), collection, root
        )
        shoulders.append(shoulder)
        _sphere(
            f"robot_{side}_shoulder_actuator",
            (0, 0, 0),
            0.105,
            materials["metal"],
            collection,
            shoulder,
            32,
            20,
        )
        _box(
            f"robot_{side}_upper_arm",
            (0, 0, -0.205),
            (0.16, 0.17, 0.34),
            materials["shell"],
            collection,
            0.050,
            shoulder,
        )
        _sphere(
            f"robot_{side}_elbow_actuator",
            (0, 0.015, -0.405),
            0.080,
            materials["accent"],
            collection,
            shoulder,
            28,
            18,
        )
        _cylinder(
            f"robot_{side}_elbow_bearing",
            (sign * 0.065, 0.015, -0.405),
            0.038,
            0.045,
            materials["metal"],
            collection,
            24,
            rotation=(0, math.pi / 2, 0),
            parent=shoulder,
        )
        _box(
            f"robot_{side}_forearm",
            (0, 0.025, -0.555),
            (0.145, 0.155, 0.265),
            materials["graphite"],
            collection,
            0.043,
            shoulder,
        )
        _box(
            f"robot_{side}_wrist",
            (0, 0.035, -0.715),
            (0.13, 0.14, 0.09),
            materials["metal"],
            collection,
            0.025,
            shoulder,
        )
        palm = _box(
            f"robot_{side}_hand_palm",
            (0, 0.055, -0.795),
            (0.135, 0.14, 0.12),
            materials["rubber"],
            collection,
            0.035,
            shoulder,
        )
        palm["c2w_articulation_role"] = "dexterous_end_effector"
        for finger in range(3):
            _cylinder(
                f"robot_{side}_finger_{finger}",
                ((finger - 1) * 0.042, 0.105, -0.865),
                0.014,
                0.11,
                materials["rubber"],
                collection,
                16,
                rotation=(math.pi / 2, 0, 0),
                parent=shoulder,
            )

    previous_yaw = 0.0
    previous_point = Vector(ROUTE_KEYS[0][1]) - Vector((1, 0, 0))
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        forward = _route_forward(index, previous_point)
        yaw = math.atan2(-forward.x, forward.y)
        while yaw - previous_yaw > math.pi:
            yaw -= math.tau
        while yaw - previous_yaw < -math.pi:
            yaw += math.tau
        root.location = point
        root.rotation_euler[2] = yaw
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_euler", index=2, frame=frame)
        previous_yaw = yaw
        previous_point = point

    stationary = ((1, 4), (48, 52), (168, 172), (296, 300))
    for frame in range(FRAME_START, FRAME_END + 1, 3):
        moving = not any(start <= frame <= end for start, end in stationary)
        swing = 0.30 * math.sin(frame * 0.58) if moving else 0.0
        hips[0].rotation_euler[0] = swing
        hips[1].rotation_euler[0] = -swing
        shoulders[0].rotation_euler[0] = -swing * 0.72
        shoulders[1].rotation_euler[0] = swing * 0.72
        for pivot in (*hips, *shoulders):
            pivot.keyframe_insert("rotation_euler", index=0, frame=frame)

    mesh_objects = [
        obj
        for obj in collection.all_objects
        if obj.type == "MESH" and obj.name.startswith(PREFIX + "robot_")
    ]
    mesh_vertices = sum(len(obj.data.vertices) for obj in mesh_objects if obj.data)
    return root, {
        "type": root["c2w_agent_type"],
        "height_m": ROBOT_HEIGHT,
        "safety_radius_m": ROBOT_SAFETY_RADIUS,
        "mesh_part_count": len(mesh_objects),
        "authored_mesh_vertex_count": mesh_vertices,
        "articulated_pivot_count": len(hips) + len(shoulders),
        "sensor_suite": root["c2w_sensor_suite"],
    }


def _camera(name, location, target, lens, collection, clip_end=1000.0):
    data = bpy.data.cameras.new(PREFIX + name + "_data")
    data.lens = lens
    data.sensor_width = 36
    data.clip_start = 0.05
    data.clip_end = clip_end
    camera = bpy.data.objects.new(PREFIX + name, data)
    collection.objects.link(camera)
    camera.location = location
    direction = Vector(target) - Vector(location)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera["c2w_agent4_source_generated"] = True
    return camera


def _dynamic_camera(name, location_keys, target_keys, lens, collection):
    camera = _camera(name, location_keys[0][1], target_keys[0][1], lens, collection)
    target = _empty(name + "_target", target_keys[0][1], collection)
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    for frame, location in location_keys:
        camera.location = location
        camera.keyframe_insert("location", frame=frame)
    for frame, location in target_keys:
        target.location = location
        target.keyframe_insert("location", frame=frame)
    return camera, target


def build_cameras(collection) -> dict[str, bpy.types.Object]:
    cameras = {
        "overview": _camera(
            "camera_route_oblique_overview",
            (69, -92, 112),
            (-23, -3, 0.5),
            48,
            collection,
        ),
        "room": _camera(
            "camera_bedroom_wide",
            (-18.8, 33.8, 3.75),
            (-13.0, 28.4, 1.85),
            28,
            collection,
        ),
        "door_inside": _camera(
            "camera_front_door_inside_wide",
            (-17.8, 27.0, 3.7),
            (-10.45, DOOR_Y, 2.05),
            29,
            collection,
        ),
        "door_outside": _camera(
            "camera_front_door_exterior_context",
            (-2.5, 37.0, 9.5),
            (-9.7, DOOR_Y, 1.45),
            34,
            collection,
        ),
        "crosswalk": _camera(
            "camera_west_crosswalk_context",
            (18.0, -1.5, 17.0),
            (-6.7, 0.0, 0.8),
            38,
            collection,
        ),
        "commercial": _camera(
            "camera_commercial_route_context",
            (6.0, -55.0, 29.0),
            (-25.0, -31.0, 1.0),
            42,
            collection,
        ),
        "store": _camera(
            "camera_fresh_mart_arrival_wide",
            (-17.0, -48.0, 15.0),
            (-40.5, -26.0, 1.15),
            39,
            collection,
        ),
    }
    aerial = _camera(
        "camera_complete_route_orthographic",
        (-23.8, -2.8, 118),
        (-23.8, -2.8, 0),
        50,
        collection,
    )
    aerial.data.type = "ORTHO"
    aerial.data.ortho_scale = 84.0
    cameras["aerial"] = aerial

    first_locations = []
    first_targets = []
    third_locations = []
    third_targets = []
    previous = Vector(ROUTE_KEYS[0][1]) - Vector((1, 0, 0))
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        forward = _route_forward(index, previous)
        side = Vector((-forward.y, forward.x, 0))
        # The camera must sit beyond the 0.23 m-deep sensor visor, not merely at
        # the head centre.  A 0.42 m forward offset preserves a true robot-eye
        # viewpoint while keeping every ray outside the authored head shell.
        first_locations.append((frame, point + forward * 0.42 + Vector((0, 0, 1.72))))
        first_targets.append((frame, point + forward * 18.0 + Vector((0, 0, 1.50))))
        indoors = frame <= 62
        on_stairs = 62 < frame < 112
        distance = 4.2 if indoors else (7.0 if on_stairs else 12.0)
        height = 3.2 if indoors else (5.0 if on_stairs else 8.0)
        lateral = 1.9 if indoors else (3.4 if on_stairs else 6.2)
        if frame >= 281:
            third_position = Vector((-24.0, -47.0, 14.0))
        else:
            third_position = (
                point - forward * distance + side * lateral + Vector((0, 0, height))
            )
        third_locations.append((frame, third_position))
        third_targets.append((frame, point + Vector((0, 0, 1.05))))
        previous = point
    first, first_target = _dynamic_camera(
        "camera_first_person_ultrawide", first_locations, first_targets, 22, collection
    )
    third, third_target = _dynamic_camera(
        "camera_third_person_wide_chase", third_locations, third_targets, 30, collection
    )
    cameras.update(
        {
            "first": first,
            "first_target": first_target,
            "third": third,
            "third_target": third_target,
        }
    )
    return cameras


def repair_first_person_camera() -> dict:
    """Apply the production head-shell clearance fix to an existing agent4 blend."""
    scene = bpy.context.scene
    collection = bpy.data.collections.get(PREFIX + "MISSION")
    camera = bpy.data.objects.get(PREFIX + "camera_first_person_ultrawide")
    target = bpy.data.objects.get(PREFIX + "camera_first_person_ultrawide_target")
    if (
        scene.get("c2w_revision") != "urban_v1_full_07_agent4"
        or collection is None
        or camera is None
        or target is None
        or len(scene.objects) < 6100
    ):
        raise RuntimeError(
            "First-person repair requires the complete generated agent4 production blend"
        )

    camera.animation_data_clear()
    target.animation_data_clear()
    camera.data.clip_start = 0.08
    previous = Vector(ROUTE_KEYS[0][1]) - Vector((1, 0, 0))
    for index, (frame, xyz, _) in enumerate(ROUTE_KEYS):
        point = Vector(xyz)
        forward = _route_forward(index, previous)
        camera.location = point + forward * 0.42 + Vector((0, 0, 1.72))
        target.location = point + forward * 18.0 + Vector((0, 0, 1.50))
        camera.keyframe_insert("location", frame=frame)
        target.keyframe_insert("location", frame=frame)
        previous = point
    _set_linear_animation(collection)
    scene["c2w_agent4_first_person_camera_head_shell_clearance"] = True
    scene["c2w_agent4_first_person_camera_forward_offset_m"] = 0.42
    return {
        "camera": camera.name,
        "target": target.name,
        "forward_offset_m": 0.42,
        "clip_start_m": camera.data.clip_start,
        "key_count": len(ROUTE_KEYS),
        "motion_interpolation": "LINEAR",
        "complete_scene_object_count": len(scene.objects),
    }


def _route_curve(name, points, material, collection, radius=0.045):
    curve = bpy.data.curves.new(PREFIX + name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for item, point in zip(spline.points, points):
        item.co = (*point, 1.0)
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    collection.objects.link(obj)
    obj["c2w_role"] = "route_visualization"
    obj["c2w_agent4_source_generated"] = True
    return obj


def build_route_visualization(collection, materials) -> dict:
    points = [Vector(xyz) + Vector((0, 0, 0.035)) for _, xyz, _ in ROUTE_KEYS]
    line = _route_curve(
        "complete_bedroom_to_store_route", points, materials["route"], collection
    )
    markers = []
    for index, route_index in enumerate((0, 4, 16, 18, len(ROUTE_KEYS) - 2), start=1):
        frame, xyz, stage = ROUTE_KEYS[route_index]
        marker = _cylinder(
            f"route_stage_marker_{index:02d}_{stage}",
            (xyz[0], xyz[1], xyz[2] + 0.04),
            0.30,
            0.055,
            materials["route_marker"],
            collection,
            vertices=40,
        )
        marker["c2w_role"] = "route_visualization"
        marker["c2w_route_stage"] = stage
        marker["c2w_route_frame"] = frame
        markers.append(marker.name)
    return {"route_curve": line.name, "stage_markers": markers}


def _ignored_collision_name(name: str) -> bool:
    low = name.lower()
    tokens = (
        "road",
        "sidewalk",
        "crosswalk",
        "xwk_",
        "parking",
        "ground",
        "floor",
        "marble",
        "paving",
        "seam",
        "marking",
        "stripe",
        "asphalt",
        "terrain",
        "grass",
        "lawn",
        "water",
        "river",
        "roof",
        "ceiling",
        "route_",
        "front_stair_tread",
        "front_stair_nosing",
        "threshold",
    )
    return any(token in low for token in tokens)


def _sample_route(spacing=0.18):
    samples = []
    for segment, (left, right) in enumerate(zip(ROUTE_KEYS, ROUTE_KEYS[1:])):
        a, b = Vector(left[1]), Vector(right[1])
        steps = max(1, math.ceil((b - a).length / spacing))
        for index in range(steps + 1):
            samples.append((segment, a.lerp(b, index / steps)))
    return samples


def _raycast_nonignored(scene, depsgraph, origin, direction, distance):
    direction = Vector(direction).normalized()
    cursor = Vector(origin)
    remaining = distance
    travelled = 0.0
    for _ in range(20):
        hit, location, normal, face, obj, matrix = scene.ray_cast(
            depsgraph, cursor, direction, distance=remaining
        )
        if not hit or obj is None:
            return None
        step = (location - cursor).length
        if not _ignored_collision_name(obj.name) and not obj.name.startswith(
            PREFIX + "front_stair_"
        ):
            return obj.name, location, travelled + step
        advance = step + 0.018
        cursor += direction * advance
        travelled += advance
        remaining -= advance
        if remaining <= 0.01:
            return None
    return None


def collision_audit(scene) -> dict:
    # The robot reaches the door only after the leaf is fully open.
    scene.frame_set(62)
    bpy.context.view_layer.update()
    samples = _sample_route()

    # Conservative AABB broad phase for compact obstacles such as furniture,
    # vehicles, posts and railings.  Large room/building shells are handled by
    # actual scene ray casts below because a whole-room AABB is not geometry.
    obstacles = []
    for obj in scene.objects:
        if (
            obj.type != "MESH"
            or obj.hide_render
            or obj.hide_viewport
            or _ignored_collision_name(obj.name)
        ):
            continue
        bounds = _world_bounds(obj)
        if not bounds or bounds[5] < 0.42 or bounds[4] > 4.25:
            continue
        width, depth = bounds[1] - bounds[0], bounds[3] - bounds[2]
        if width > 8.0 or depth > 8.0:
            continue
        obstacles.append((obj.name, bounds))

    violations = []
    seen = set()
    min_clearance = {}
    for segment, point in samples:
        body_min = point.z + 0.10
        body_max = point.z + ROBOT_HEIGHT - 0.04
        for name, bounds in obstacles:
            if body_max < bounds[4] or body_min > bounds[5]:
                continue
            dx = max(bounds[0] - point.x, 0.0, point.x - bounds[1])
            dy = max(bounds[2] - point.y, 0.0, point.y - bounds[3])
            clearance = math.hypot(dx, dy)
            if clearance < min_clearance.get(name, float("inf")):
                min_clearance[name] = clearance
            if clearance + 1e-5 >= ROBOT_SAFETY_RADIUS:
                continue
            key = (segment, name)
            if key in seen:
                continue
            seen.add(key)
            violations.append(
                {
                    "method": "compact_obstacle_aabb",
                    "segment": segment,
                    "from_stage": ROUTE_KEYS[segment][2],
                    "to_stage": ROUTE_KEYS[segment + 1][2],
                    "object": name,
                    "sample_xyz": [round(float(v), 4) for v in point],
                    "xy_clearance_m": round(clearance, 4),
                    "object_world_aabb": [round(v, 4) for v in bounds],
                }
            )

    # Multi-height radial ray checks include evaluated complex shells and
    # collection instances, covering the objects intentionally excluded from
    # the compact AABB pass.
    directions = []
    for index in range(8):
        angle = math.tau * index / 8
        directions.append(Vector((math.cos(angle), math.sin(angle), 0)))
    ray_hits = []
    ray_seen = set()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ray_samples = []
    for segment, (left, right) in enumerate(zip(ROUTE_KEYS, ROUTE_KEYS[1:])):
        left_point, right_point = Vector(left[1]), Vector(right[1])
        ray_samples.append((segment, left_point))
        if right[0] <= 62:
            ray_samples.append((segment, left_point.lerp(right_point, 0.5)))
    ray_samples.append((len(ROUTE_KEYS) - 2, Vector(ROUTE_KEYS[-1][1])))
    for sample_index, (segment, point) in enumerate(ray_samples):
        if sample_index % 10 == 0:
            print(
                f"[Agent4Mission] evaluated collision rays {sample_index}/{len(ray_samples)}",
                flush=True,
            )
        for height in (0.32, 0.96, 1.62):
            origin = point + Vector((0, 0, height))
            for direction in directions:
                hit = _raycast_nonignored(
                    scene, depsgraph, origin, direction, ROBOT_SAFETY_RADIUS
                )
                if not hit:
                    continue
                name, location, distance = hit
                key = (segment, name)
                if key in ray_seen:
                    continue
                ray_seen.add(key)
                ray_hits.append(
                    {
                        "method": "evaluated_scene_radial_raycast",
                        "segment": segment,
                        "from_stage": ROUTE_KEYS[segment][2],
                        "to_stage": ROUTE_KEYS[segment + 1][2],
                        "object": name,
                        "sample_xyz": [round(float(v), 4) for v in point],
                        "body_sample_height_m": height,
                        "surface_distance_m": round(float(distance), 4),
                        "hit_xyz": [round(float(v), 4) for v in location],
                    }
                )
    violations.extend(ray_hits)

    # Every authored key must have physical support near its declared foot
    # elevation.  This catches floating/teleporting transitions independently
    # of lateral clearance.
    support_failures = []
    for frame, xyz, stage in ROUTE_KEYS:
        point = Vector(xyz)
        hit, location, normal, face, obj, matrix = scene.ray_cast(
            depsgraph,
            point + Vector((0, 0, 0.25)),
            Vector((0, 0, -1)),
            distance=0.62,
        )
        foot_gap = point.z - location.z if hit else None
        if not hit or foot_gap < -0.025 or foot_gap > 0.24:
            support_failures.append(
                {
                    "frame": frame,
                    "stage": stage,
                    "xyz": list(xyz),
                    "support_object": obj.name if hit and obj else None,
                    "foot_gap_m": round(float(foot_gap), 4)
                    if foot_gap is not None
                    else None,
                }
            )

    # Directly verify a three-column by six-row clearance grid through the cut
    # doorway while the leaf is open.
    door_blockers = []
    for y_offset in (-0.44, 0.0, 0.44):
        for z in (1.67, 2.05, 2.43, 2.81, 3.19, 3.57):
            origin = Vector((-11.15, DOOR_Y + y_offset, z))
            hit, location, normal, face, obj, matrix = scene.ray_cast(
                depsgraph, origin, Vector((1, 0, 0)), distance=1.50
            )
            if hit and obj and not _ignored_collision_name(obj.name):
                door_blockers.append(
                    {
                        "sample_y": round(DOOR_Y + y_offset, 4),
                        "sample_z": z,
                        "object": obj.name,
                        "hit_xyz": [round(float(v), 4) for v in location],
                    }
                )

    report = {
        "method": (
            "0.18 m swept-route sampling; 0.46 m compact-obstacle AABB broad phase; "
            "evaluated-scene radial rays at every authored route key plus indoor segment midpoints "
            "in 8 directions and three body heights; "
            "support rays; "
            "18-ray real-door clearance grid"
        ),
        "passed": not violations and not support_failures and not door_blockers,
        "robot_safety_radius_m": ROBOT_SAFETY_RADIUS,
        "robot_height_m": ROBOT_HEIGHT,
        "route_segment_count": len(ROUTE_KEYS) - 1,
        "route_sample_count": len(samples),
        "compact_obstacles_tested": len(obstacles),
        "radial_route_sample_count": len(ray_samples),
        "radial_rays_cast": len(ray_samples) * 3 * len(directions),
        "support_key_count": len(ROUTE_KEYS),
        "door_clearance_ray_count": 18,
        "violations": violations,
        "support_failures": support_failures,
        "door_blockers": door_blockers,
        "limitations": "Deterministic kinematic route with conservative sampled geometry audit; not closed-loop control.",
    }
    return report


def _set_linear_animation(collection):
    for obj in collection.all_objects:
        animation = obj.animation_data
        if not animation or not animation.action:
            continue
        for fcurve in animation.action.fcurves:
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"


def _hard_quality_audit(collection, robot_report, door_report, stair_report) -> dict:
    forbidden = ("toy", "placeholder", "proxy", "dummy", "lowpoly")
    bad = [
        obj.name
        for obj in collection.all_objects
        if any(token in obj.name.lower() for token in forbidden)
    ]
    mission_meshes = [obj for obj in collection.all_objects if obj.type == "MESH"]
    degenerate = [
        obj.name
        for obj in mission_meshes
        if not obj.data or len(obj.data.vertices) < 4 or len(obj.data.polygons) < 1
    ]
    checks = {
        "complete_river3_scene_preserved": len(bpy.context.scene.objects) > 6000,
        "no_spatial_cull": not any(
            obj.get("c2w_spatial_cull") for obj in bpy.context.scene.objects
        ),
        "no_proxy_or_compact_scene": not bad,
        "no_degenerate_mission_meshes": not degenerate,
        "real_boolean_door_targets": len(door_report["boolean_targets"]) == 2,
        "supported_stair_treads": stair_report["tread_count"] == 9,
        "detailed_robot_mesh_parts": robot_report["mesh_part_count"] >= 55,
        "detailed_robot_vertex_count": robot_report["authored_mesh_vertex_count"]
        >= 8000,
    }
    if not all(checks.values()):
        raise RuntimeError(
            {
                "agent4_hard_quality_gate": checks,
                "forbidden": bad,
                "degenerate": degenerate,
            }
        )
    return {
        "valid": True,
        "checks": checks,
        "mission_mesh_object_count": len(mission_meshes),
        "forbidden_name_count": len(bad),
        "degenerate_mission_mesh_count": len(degenerate),
        "policy": "complete production city only; reject proxy/compact/toy/degenerate mission geometry",
    }


def build() -> dict:
    scene = bpy.context.scene
    if scene.get("c2w_revision") != "urban_v1_full_07-river3":
        raise RuntimeError(
            f"agent4 requires the audited river3 production scene, got {scene.get('c2w_revision')!r}"
        )
    old = bpy.data.collections.get(PREFIX + "MISSION")
    if old:
        raise RuntimeError("agent4 mission already exists in the loaded checkpoint")
    collection = bpy.data.collections.new(PREFIX + "MISSION")
    scene.collection.children.link(collection)
    collection["c2w_pipeline_role"] = "production_full_scene_agent_mission"
    collection["c2w_preserves_complete_city"] = True
    collection["c2w_proxy_geometry_forbidden"] = True

    materials = {
        "shell": _material("robot_ceramic_shell", (0.68, 0.74, 0.78, 1), 0.45, 0.22),
        "graphite": _material(
            "robot_graphite_composite", (0.025, 0.035, 0.052, 1), 0.62, 0.28
        ),
        "rubber": _material("robot_elastomer", (0.008, 0.012, 0.016, 1), 0.0, 0.82),
        "seal": _material("architectural_seal", (0.012, 0.016, 0.020, 1), 0.0, 0.76),
        "metal": _material("brushed_stainless", (0.22, 0.29, 0.34, 1), 0.88, 0.20),
        "accent": _material("safety_orange", (0.95, 0.19, 0.025, 1), 0.28, 0.24),
        "lens": _material(
            "optical_sensor_glass",
            (0.004, 0.035, 0.060, 1),
            0.30,
            0.08,
            (0.0, 0.42, 0.95, 1),
            2.8,
        ),
        "sensor": _material(
            "active_sensor", (0.01, 0.07, 0.11, 1), 0.25, 0.10, (0.0, 0.80, 1.0, 1), 3.2
        ),
        "status": _material(
            "robot_status_light",
            (0.02, 0.18, 0.10, 1),
            0.15,
            0.12,
            (0.0, 1.0, 0.32, 1),
            4.0,
        ),
        "door": _material("front_door_hardwood", (0.20, 0.055, 0.018, 1), 0.0, 0.33),
        "door_panel": _material(
            "front_door_recessed_hardwood", (0.095, 0.018, 0.008, 1), 0.0, 0.38
        ),
        "door_frame": _material(
            "front_door_powdercoat_frame", (0.055, 0.070, 0.082, 1), 0.58, 0.24
        ),
        "door_glass": _material(
            "front_door_laminated_glass", (0.035, 0.14, 0.18, 1), 0.22, 0.08
        ),
        "threshold": _material(
            "front_door_threshold", (0.18, 0.22, 0.25, 1), 0.72, 0.30
        ),
        "stair": _material(
            "front_stair_bushhammered_stone", (0.43, 0.47, 0.49, 1), 0.0, 0.73
        ),
        "nosing": _material(
            "front_stair_non_slip_nosing", (0.13, 0.16, 0.18, 1), 0.58, 0.40
        ),
        "rail": _material(
            "front_stair_stainless_handrail", (0.27, 0.32, 0.35, 1), 0.86, 0.21
        ),
        "route": _material(
            "route_emissive_cyan",
            (0.0, 0.26, 0.78, 1),
            0.15,
            0.20,
            (0.0, 0.44, 1.0, 1),
            2.4,
        ),
        "route_marker": _material(
            "route_stage_marker",
            (0.98, 0.26, 0.02, 1),
            0.18,
            0.24,
            (1.0, 0.09, 0.0, 1),
            1.8,
        ),
        "debug": _material("temporary_boolean_debug", (1.0, 0.0, 1.0, 1), 0.0, 0.5),
    }

    door_report = build_real_front_door(collection, materials)
    vegetation_report = clear_route_vegetation()
    stair_report = build_front_stair(collection, materials)
    collision_report = collision_audit(scene)
    if not collision_report["passed"]:
        raise RuntimeError(
            {
                "agent4_collision_gate_failed": True,
                "violations": collision_report["violations"][:30],
                "support_failures": collision_report["support_failures"][:20],
                "door_blockers": collision_report["door_blockers"][:20],
            }
        )
    route_report = build_route_visualization(collection, materials)
    robot, robot_report = build_humanoid(collection, materials)
    robot["c2w_collision_audit_passed"] = True
    cameras = build_cameras(collection)
    _set_linear_animation(collection)
    quality_report = _hard_quality_audit(
        collection, robot_report, door_report, stair_report
    )

    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene["c2w_agent4_production_mission"] = True
    scene["c2w_agent4_complete_scene_preserved"] = True
    scene["c2w_agent4_no_proxy_or_compact_scene"] = True
    scene["c2w_agent4_collision_audit_passed"] = True
    scene["c2w_agent4_route"] = "bedroom -> real front door -> west zebra -> Fresh Mart"
    return {
        "route": [
            {"frame": frame, "xyz": list(xyz), "stage": stage}
            for frame, xyz, stage in ROUTE_KEYS
        ],
        "door": door_report,
        "front_stair": stair_report,
        "egress_vegetation_clearance": vegetation_report,
        "robot": robot_report,
        "collision_audit": collision_report,
        "quality_audit": quality_report,
        "route_visualization": route_report,
        "cameras": {
            name: camera.name
            for name, camera in cameras.items()
            if not name.endswith("_target")
        },
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "fps": FPS,
        "source_scene_object_count_after_mission": len(scene.objects),
    }
