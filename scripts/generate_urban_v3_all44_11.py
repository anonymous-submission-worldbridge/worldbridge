"""ALL44-11: reference-driven compact athletics ground for the leisure parcel.

The production generator retains every ALL44-10 leisure asset and adds a
source-authored community athletics ground in the previously unused southern
extension of the same parcel.  The supplied reference is translated into a
four-lane capsule running track, a marked youth football pitch, field-event
practice areas, modular spectator seating, a photo-finish/equipment room,
perimeter fencing, drainage and engineered floodlights.

The reference's unrelated white massing blocks are explicitly excluded.  The
public ``add_service_building_details`` hook is the one consumed by the full
urban pipeline, so this is not a detached Blend-only demonstration.
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
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))

import generate_urban_v3_all44_10 as previous


INPUT = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_10/urban_v3_all44_10.blend"
)
OUTPUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_11"
PREFIX = "all44_11:"
MASTER_NAME = PREFIX + "MASTER:COMPACT_COMMUNITY_ATHLETICS_GROUND"
SITE_NAME = PREFIX + "ATHLETICS_GROUND_SITE_AND_PUBLIC_CONNECTIONS"

# The established production leisure parcel is x[9.5, 54.4], y[-62, -9.5].
# ALL44-10 occupies its northern part through y=-41.9.  These dimensions keep
# the complete new construction inside the southern strip with real clearance.
GROUND_CENTER = Vector((31.95, -52.25, 0.0))
SITE_BOUNDS = (10.05, 53.85, -61.70, -42.08)
STRAIGHT_HALF = 12.40
OUTER_RADIUS = 8.80
LANE_COUNT = 4
LANE_WIDTH = 0.72
INNER_RADIUS = OUTER_RADIUS - LANE_COUNT * LANE_WIDTH
TRACK_TOP_Z = 0.405
PITCH_LENGTH = 22.00
PITCH_WIDTH = 9.80

# Stable ALL44-10 interfaces and materials remain available to downstream
# users.  Their names deliberately retain the all44_10 prefix.
base = previous.base
remove_old_court_playground = previous.remove_old_court_playground
tune_retained_materials = previous.tune_retained_materials
create_shared_materials = previous.create_shared_materials
generate_real_turf = previous.generate_real_turf
generate_playground = previous.generate_playground
populate_playground_details = previous.populate_playground_details


def args():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--quality", choices=("test", "final"), default="final")
    parser.add_argument("--skip-save", action="store_true")
    return parser.parse_args(values)


def _material(
    name, color, roughness, metallic=0.0, noise=0.0, transmission=0.0, emission=0.0
):
    full_name = PREFIX + name
    existing = bpy.data.materials.get(full_name)
    if existing is not None:
        return existing
    material = bpy.data.materials.new(full_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    transmission_input = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get(
        "Transmission"
    )
    if transmission_input is not None:
        transmission_input.default_value = transmission
    if emission:
        emission_color = bsdf.inputs.get("Emission Color") or bsdf.inputs.get(
            "Emission"
        )
        emission_strength = bsdf.inputs.get("Emission Strength")
        if emission_color is not None:
            emission_color.default_value = (*color, 1)
        if emission_strength is not None:
            emission_strength.default_value = emission
    if noise:
        texture = nodes.new("ShaderNodeTexNoise")
        texture.inputs["Scale"].default_value = 34
        texture.inputs["Detail"].default_value = 5
        texture.inputs["Roughness"].default_value = 0.68
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (
            *tuple(max(0, component * 0.82) for component in color),
            1,
        )
        ramp.color_ramp.elements[1].color = (
            *tuple(min(1, component * 1.10 + 0.018) for component in color),
            1,
        )
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise
        bump.inputs["Distance"].default_value = 0.024
        material.node_tree.links.new(texture.outputs["Fac"], ramp.inputs["Fac"])
        material.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        material.node_tree.links.new(texture.outputs["Fac"], bump.inputs["Height"])
        material.node_tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def athletics_materials():
    return {
        "apron": _material(
            "MAT_MINERAL_BOUND_TEAL_APRON", (0.045, 0.245, 0.245), 0.91, noise=0.22
        ),
        "subbase": _material(
            "MAT_TRACK_COMPACTED_SUBBASE", (0.24, 0.22, 0.19), 0.96, noise=0.25
        ),
        "asphalt": _material(
            "MAT_TRACK_ASPHALT_SHOCKPAD", (0.055, 0.050, 0.047), 0.94, noise=0.19
        ),
        "track_a": _material(
            "MAT_EPDM_TRACK_OXIDE_RED", (0.43, 0.075, 0.052), 0.88, noise=0.24
        ),
        "track_b": _material(
            "MAT_EPDM_TRACK_WEATHERED_RED", (0.36, 0.055, 0.039), 0.90, noise=0.22
        ),
        "track_granule": _material(
            "MAT_EPDM_DARK_GRANULE", (0.095, 0.026, 0.020), 0.96, noise=0.09
        ),
        "line": _material(
            "MAT_ATHLETICS_MARKING_WHITE", (0.86, 0.86, 0.81), 0.78, noise=0.035
        ),
        "turf": _material(
            "MAT_PITCH_DENSE_TURF", (0.045, 0.245, 0.055), 0.92, noise=0.31
        ),
        "turf_alt": _material(
            "MAT_PITCH_MOWING_STRIPE", (0.062, 0.295, 0.064), 0.91, noise=0.27
        ),
        "sector": _material(
            "MAT_FIELD_EVENT_TERRACOTTA", (0.40, 0.115, 0.065), 0.91, noise=0.18
        ),
        "sand": _material(
            "MAT_LONG_JUMP_WASHED_SAND", (0.54, 0.39, 0.20), 0.97, noise=0.30
        ),
        "concrete": _material(
            "MAT_PRECAST_SPORT_CONCRETE", (0.43, 0.41, 0.37), 0.91, noise=0.16
        ),
        "concrete_dark": _material(
            "MAT_FORMED_CONCRETE_DARK", (0.21, 0.20, 0.18), 0.94, noise=0.18
        ),
        "steel": _material(
            "MAT_GALVANIZED_SPORT_STEEL", (0.31, 0.34, 0.34), 0.37, 0.72, 0.025
        ),
        "steel_dark": _material(
            "MAT_POWDER_COATED_DARK_STEEL", (0.035, 0.055, 0.054), 0.48, 0.62, 0.035
        ),
        "fence": _material(
            "MAT_GREEN_WELDED_MESH", (0.025, 0.16, 0.105), 0.58, 0.48, 0.04
        ),
        "net": _material(
            "MAT_UV_STABILIZED_GOAL_NET", (0.70, 0.72, 0.67), 0.86, noise=0.02
        ),
        "seat_red": _material(
            "MAT_STAND_SEAT_MUTED_RED", (0.49, 0.075, 0.045), 0.71, 0.01, 0.07
        ),
        "seat_orange": _material(
            "MAT_STAND_SEAT_BURNT_ORANGE", (0.58, 0.19, 0.055), 0.73, 0.01, 0.07
        ),
        "wall": _material(
            "MAT_TIMING_ROOM_FIBRE_CEMENT", (0.19, 0.25, 0.23), 0.83, noise=0.13
        ),
        "roof": _material(
            "MAT_TIMING_ROOM_RED_METAL_ROOF", (0.52, 0.045, 0.025), 0.48, 0.44, 0.06
        ),
        "glass": _material(
            "MAT_TIMING_ROOM_LOW_IRON_GLASS",
            (0.065, 0.145, 0.16),
            0.15,
            0.06,
            transmission=0.34,
        ),
        "dark": _material(
            "MAT_TIMING_ROOM_INTERIOR_SHADOW", (0.018, 0.024, 0.023), 0.93
        ),
        "light": _material(
            "MAT_FLOODLIGHT_LENS", (0.82, 0.86, 0.78), 0.18, emission=2.8
        ),
        "drain": _material(
            "MAT_TRACK_DRAIN_CAST_IRON", (0.035, 0.040, 0.039), 0.45, 0.78, 0.035
        ),
        "yellow": _material(
            "MAT_ACCESS_SAFETY_YELLOW", (0.74, 0.49, 0.035), 0.70, 0.08, 0.045
        ),
    }


def _mesh_object(
    name, vertices, faces, collection, materials, material_indices=None, bevel=0.0
):
    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    for material in materials:
        mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    if material_indices:
        for polygon, index in zip(mesh.polygons, material_indices):
            polygon.material_index = index
    if bevel:
        modifier = obj.modifiers.new("formed_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    return obj


def _cube(name, location, dimensions, material, collection, bevel=0.02, rotation_z=0.0):
    # Direct mesh construction is essential in the 3.8 GB production scene:
    # bpy.ops + transform_apply would evaluate its full dependency graph once
    # for every seat, drain bar and fence fitting.
    half_x, half_y, half_z = (dimension / 2 for dimension in dimensions)
    vertices = [
        (-half_x, -half_y, -half_z),
        (half_x, -half_y, -half_z),
        (half_x, half_y, -half_z),
        (-half_x, half_y, -half_z),
        (-half_x, -half_y, half_z),
        (half_x, -half_y, half_z),
        (half_x, half_y, half_z),
        (-half_x, half_y, half_z),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler[2] = rotation_z
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    return obj


def _cylinder(
    name,
    location,
    radius,
    depth,
    material,
    collection,
    vertices=28,
    rotation=(0, 0, 0),
    bevel=0.01,
):
    coordinates = []
    for z in (-depth / 2, depth / 2):
        coordinates.extend(
            (
                radius * math.cos(math.tau * index / vertices),
                radius * math.sin(math.tau * index / vertices),
                z,
            )
            for index in range(vertices)
        )
    faces = [tuple(reversed(range(vertices))), tuple(range(vertices, vertices * 2))]
    for index in range(vertices):
        nxt = (index + 1) % vertices
        faces.append((index, nxt, vertices + nxt, vertices + index))
    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(coordinates, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def _beam(name, start, end, radius, material, collection, vertices=20):
    start, end = Vector(start), Vector(end)
    delta = end - start
    obj = _cylinder(
        name,
        (start + end) / 2,
        radius,
        delta.length,
        material,
        collection,
        vertices,
        bevel=0.006,
    )
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def _curve(name, points, radius, material, collection, cyclic=False):
    curve = bpy.data.curves.new(PREFIX + name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    curve.resolution_u = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(PREFIX + name, curve)
    collection.objects.link(obj)
    curve.materials.append(material)
    return obj


def _line_ribbon(name, points, width, z, material, collection, cyclic=False):
    coordinates = [Vector((x, y, z)) for x, y in points]
    if cyclic:
        coordinates.append(coordinates[0])
    vertices = []
    for index, point in enumerate(coordinates):
        previous_point = (
            coordinates[index - 1]
            if index
            else (coordinates[-2] if cyclic else coordinates[0])
        )
        next_point = (
            coordinates[index + 1]
            if index < len(coordinates) - 1
            else (coordinates[1] if cyclic else coordinates[-1])
        )
        tangent = (next_point - previous_point).normalized()
        normal = Vector((-tangent.y, tangent.x, 0)) * width / 2
        vertices.extend((tuple(point + normal), tuple(point - normal)))
    faces = [
        (2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(coordinates) - 1)
    ]
    return _mesh_object(name, vertices, faces, collection, [material])


def _rounded_slab(name, cx, cy, width, depth, z, height, radius, material, collection):
    vertices, faces, boundary = [], [], []
    segments = 10
    corners = (
        (cx - width / 2 + radius, cy - depth / 2 + radius, -3 * math.pi / 4),
        (cx + width / 2 - radius, cy - depth / 2 + radius, -math.pi / 4),
        (cx + width / 2 - radius, cy + depth / 2 - radius, math.pi / 4),
        (cx - width / 2 + radius, cy + depth / 2 - radius, 3 * math.pi / 4),
    )
    for x, y, start in corners:
        for index in range(segments + 1):
            angle = start + index * (math.pi / 2 / segments)
            boundary.append(
                (x + radius * math.cos(angle), y + radius * math.sin(angle))
            )
    for level in (z - height / 2, z + height / 2):
        vertices.extend((x, y, level) for x, y in boundary)
    count = len(boundary)
    faces.extend((tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))))
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    return _mesh_object(name, vertices, faces, collection, [material], bevel=0.018)


def _capsule_boundary(radius, z, segments=64):
    points = []
    for index in range(segments + 1):
        angle = -math.pi / 2 + math.pi * index / segments
        points.append(
            (STRAIGHT_HALF + radius * math.cos(angle), radius * math.sin(angle), z)
        )
    for index in range(segments + 1):
        angle = math.pi / 2 + math.pi * index / segments
        points.append(
            (-STRAIGHT_HALF + radius * math.cos(angle), radius * math.sin(angle), z)
        )
    return points


def _capsule_solid(name, radius, z0, z1, material, collection, segments=64):
    bottom = _capsule_boundary(radius, z0, segments)
    top = _capsule_boundary(radius, z1, segments)
    count = len(bottom)
    vertices = bottom + top
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    return _mesh_object(name, vertices, faces, collection, [material], bevel=0.012)


def _capsule_ring(
    name, outer_radius, inner_radius, z0, z1, material, collection, segments=64
):
    outer_bottom = _capsule_boundary(outer_radius, z0, segments)
    inner_bottom = _capsule_boundary(inner_radius, z0, segments)
    outer_top = _capsule_boundary(outer_radius, z1, segments)
    inner_top = _capsule_boundary(inner_radius, z1, segments)
    count = len(outer_bottom)
    vertices = outer_bottom + inner_bottom + outer_top + inner_top
    faces = []
    for index in range(count):
        nxt = (index + 1) % count
        outer_b, inner_b = index, count + index
        outer_t, inner_t = count * 2 + index, count * 3 + index
        outer_bn, inner_bn = nxt, count + nxt
        outer_tn, inner_tn = count * 2 + nxt, count * 3 + nxt
        faces.extend(
            (
                (outer_t, outer_tn, inner_tn, inner_t),
                (outer_b, inner_b, inner_bn, outer_bn),
                (outer_b, outer_bn, outer_tn, outer_t),
                (inner_b, inner_t, inner_tn, inner_bn),
            )
        )
    return _mesh_object(name, vertices, faces, collection, [material], bevel=0.008)


def _instance(collection, master, name, location, rotation=0.0, scale=1.0):
    obj = bpy.data.objects.new(PREFIX + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = location
    obj.rotation_euler[2] = rotation
    obj.scale = (scale, scale, scale)
    obj["c2w_asset_master"] = master.name
    return obj


def _surface_granules(collection, material, count=920):
    rng = random.Random(4411)
    vertices, faces = [], []
    accepted = 0
    while accepted < count:
        x = rng.uniform(-STRAIGHT_HALF - OUTER_RADIUS, STRAIGHT_HALF + OUTER_RADIUS)
        y = rng.uniform(-OUTER_RADIUS, OUTER_RADIUS)
        distance = (
            abs(y) if abs(x) <= STRAIGHT_HALF else math.hypot(abs(x) - STRAIGHT_HALF, y)
        )
        if not (INNER_RADIUS + 0.08 < distance < OUTER_RADIUS - 0.08):
            continue
        radius = rng.uniform(0.010, 0.026)
        start = len(vertices)
        vertices.append((x, y, TRACK_TOP_Z + 0.006))
        for segment in range(6):
            angle = math.tau * segment / 6
            vertices.append(
                (
                    x + radius * math.cos(angle),
                    y + radius * math.sin(angle),
                    TRACK_TOP_Z + 0.006,
                )
            )
        for segment in range(6):
            faces.append((start, start + 1 + segment, start + 1 + (segment + 1) % 6))
        accepted += 1
    return _mesh_object(
        "embedded_epdm_surface_granules", vertices, faces, collection, [material]
    )


def _build_goal(collection, materials, side):
    front_x = side * (PITCH_LENGTH / 2 + 0.06)
    back_x = front_x + side * 0.92
    bottom_z, top_z, half_width = 0.426, 2.10, 1.68
    for y in (-half_width, half_width):
        _beam(
            "football_goal_front_post",
            (front_x, y, bottom_z),
            (front_x, y, top_z),
            0.047,
            materials["steel"],
            collection,
            24,
        )
        _beam(
            "football_goal_ground_return",
            (front_x, y, bottom_z),
            (back_x, y, bottom_z),
            0.034,
            materials["steel"],
            collection,
            20,
        )
        _beam(
            "football_goal_back_stanchion",
            (back_x, y, bottom_z),
            (back_x, y, 1.60),
            0.030,
            materials["steel"],
            collection,
            20,
        )
        _cube(
            "football_goal_anchor_plate",
            (front_x, y, bottom_z - 0.015),
            (0.22, 0.22, 0.055),
            materials["steel_dark"],
            collection,
            0.018,
        )
        for offset_y in (-0.065, 0.065):
            _cylinder(
                "football_goal_anchor_bolt",
                (front_x, y + offset_y, bottom_z + 0.025),
                0.012,
                0.045,
                materials["steel"],
                collection,
                12,
                bevel=0.003,
            )
    _beam(
        "football_goal_crossbar",
        (front_x, -half_width, top_z),
        (front_x, half_width, top_z),
        0.047,
        materials["steel"],
        collection,
        24,
    )
    _beam(
        "football_goal_rear_top_bar",
        (back_x, -half_width, 1.60),
        (back_x, half_width, 1.60),
        0.027,
        materials["steel_dark"],
        collection,
        20,
    )
    for index in range(13):
        y = -half_width + 2 * half_width * index / 12
        _curve(
            "football_goal_net_longitudinal_cord",
            [
                (front_x, y, top_z - 0.02),
                (back_x, y, 1.58),
                (back_x, y, bottom_z + 0.02),
            ],
            0.007,
            materials["net"],
            collection,
        )
    for level in range(6):
        fraction = level / 5
        z = bottom_z + (top_z - bottom_z) * fraction
        x = back_x + (front_x - back_x) * max(0, (fraction - 0.70) / 0.30)
        _curve(
            "football_goal_net_transverse_cord",
            [(x, -half_width, z), (x, half_width, z)],
            0.007,
            materials["net"],
            collection,
        )


def _pitch_markings(collection, materials):
    half_l, half_w = PITCH_LENGTH / 2, PITCH_WIDTH / 2
    z, width = TRACK_TOP_Z + 0.021, 0.055
    _line_ribbon(
        "football_pitch_boundary",
        [(-half_l, -half_w), (half_l, -half_w), (half_l, half_w), (-half_l, half_w)],
        width,
        z,
        materials["line"],
        collection,
        True,
    )
    _line_ribbon(
        "football_pitch_halfway_line",
        [(0, -half_w), (0, half_w)],
        width,
        z,
        materials["line"],
        collection,
    )
    circle = [
        (1.55 * math.cos(math.tau * index / 72), 1.55 * math.sin(math.tau * index / 72))
        for index in range(72)
    ]
    _line_ribbon(
        "football_pitch_centre_circle",
        circle,
        width,
        z,
        materials["line"],
        collection,
        True,
    )
    _cylinder(
        "football_pitch_centre_spot",
        (0, 0, z + 0.003),
        0.075,
        0.012,
        materials["line"],
        collection,
        24,
        bevel=0.002,
    )
    for side in (-1, 1):
        goal_line = side * half_l
        penalty_x = side * (half_l - 3.65)
        goal_area_x = side * (half_l - 1.35)
        _line_ribbon(
            "football_penalty_area",
            [
                (goal_line, -3.45),
                (penalty_x, -3.45),
                (penalty_x, 3.45),
                (goal_line, 3.45),
            ],
            width,
            z,
            materials["line"],
            collection,
        )
        _line_ribbon(
            "football_goal_area",
            [
                (goal_line, -2.25),
                (goal_area_x, -2.25),
                (goal_area_x, 2.25),
                (goal_line, 2.25),
            ],
            width,
            z,
            materials["line"],
            collection,
        )
        _cylinder(
            "football_penalty_spot",
            (side * (half_l - 2.75), 0, z + 0.003),
            0.065,
            0.012,
            materials["line"],
            collection,
            20,
            bevel=0.002,
        )
    for x_sign, y_sign in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        centre_x, centre_y = x_sign * half_l, y_sign * half_w
        angles = (
            (0, math.pi / 2)
            if (x_sign, y_sign) == (-1, -1)
            else (-math.pi / 2, 0)
            if (x_sign, y_sign) == (-1, 1)
            else (math.pi / 2, math.pi)
            if (x_sign, y_sign) == (1, -1)
            else (math.pi, 3 * math.pi / 2)
        )
        points = [
            (
                centre_x
                + 0.40 * math.cos(angles[0] + (angles[1] - angles[0]) * index / 18),
                centre_y
                + 0.40 * math.sin(angles[0] + (angles[1] - angles[0]) * index / 18),
            )
            for index in range(19)
        ]
        _line_ribbon(
            "football_corner_arc", points, width, z, materials["line"], collection
        )


def _field_event_areas(collection, materials):
    z = TRACK_TOP_Z + 0.018
    vertex = (14.25, 2.40, z)
    arc = []
    for index in range(25):
        angle = math.radians(-37 + 74 * index / 24)
        arc.append((14.25 + 3.55 * math.cos(angle), 2.40 + 3.55 * math.sin(angle), z))
    vertices = [vertex] + arc
    faces = [tuple(range(len(vertices)))]
    _mesh_object(
        "shot_put_landing_sector_inlay",
        vertices,
        faces,
        collection,
        [materials["sector"]],
    )
    _curve(
        "shot_put_sector_boundary_lower",
        [vertex, arc[0]],
        0.020,
        materials["line"],
        collection,
    )
    _curve(
        "shot_put_sector_boundary_upper",
        [vertex, arc[-1]],
        0.020,
        materials["line"],
        collection,
    )
    _curve("shot_put_sector_arc", arc, 0.020, materials["line"], collection)
    _cylinder(
        "shot_put_reinforced_circle",
        (14.22, 2.40, z + 0.018),
        0.62,
        0.055,
        materials["concrete"],
        collection,
        48,
        bevel=0.012,
    )
    circle = [
        (
            14.22 + 0.52 * math.cos(math.tau * index / 48),
            2.40 + 0.52 * math.sin(math.tau * index / 48),
            z + 0.050,
        )
        for index in range(48)
    ]
    _curve("shot_put_circle_rim", circle, 0.025, materials["line"], collection, True)
    _cube(
        "shot_put_toe_board",
        (14.78, 2.40, z + 0.090),
        (0.18, 0.74, 0.12),
        materials["line"],
        collection,
        0.04,
    )

    _cube(
        "long_jump_runway",
        (14.32, -3.42, z + 0.010),
        (3.85, 0.82, 0.035),
        materials["sector"],
        collection,
        0.015,
    )
    _cube(
        "long_jump_takeoff_board",
        (15.40, -3.42, z + 0.035),
        (0.14, 0.78, 0.028),
        materials["line"],
        collection,
        0.008,
    )
    _cube(
        "long_jump_sand_pit_retaining_box",
        (17.02, -3.42, z + 0.012),
        (1.35, 1.52, 0.18),
        materials["concrete"],
        collection,
        0.055,
    )
    _cube(
        "long_jump_raked_sand",
        (17.02, -3.42, z + 0.112),
        (1.16, 1.34, 0.055),
        materials["sand"],
        collection,
        0.045,
    )
    for index in range(7):
        _line_ribbon(
            "long_jump_sand_rake_trace",
            [(16.55, -3.92 + index * 0.16), (17.49, -3.92 + index * 0.16)],
            0.012,
            z + 0.143,
            materials["concrete_dark"],
            collection,
        )


def build_athletics_master(materials):
    master = bpy.data.collections.new(MASTER_NAME)
    master[
        "architectural_program"
    ] = "compact four-lane community athletics and youth football ground"
    master[
        "reference_translation"
    ] = "red oval track, green pitch, field-event turn, side stand and red-roof timing room"
    master[
        "real_scale_policy"
    ] = "parcel-constrained training facility; never represented as a regulation 400 m stadium"

    _capsule_solid(
        "engineered_track_subbase",
        OUTER_RADIUS + 0.18,
        0.08,
        0.245,
        materials["subbase"],
        master,
    )
    _capsule_ring(
        "bituminous_track_shockpad",
        OUTER_RADIUS + 0.06,
        INNER_RADIUS - 0.10,
        0.245,
        0.325,
        materials["asphalt"],
        master,
    )
    for lane in range(LANE_COUNT):
        outer = OUTER_RADIUS - lane * LANE_WIDTH
        inner = outer - LANE_WIDTH
        _capsule_ring(
            f"epdm_running_lane_{lane + 1:02d}",
            outer,
            inner,
            0.325,
            TRACK_TOP_Z,
            materials["track_a"] if lane % 2 == 0 else materials["track_b"],
            master,
        )
    for boundary in range(LANE_COUNT + 1):
        radius = OUTER_RADIUS - boundary * LANE_WIDTH
        _curve(
            f"continuous_lane_boundary_{boundary + 1:02d}",
            _capsule_boundary(radius, TRACK_TOP_Z + 0.020),
            0.022,
            materials["line"],
            master,
            True,
        )
    _surface_granules(master, materials["track_granule"])

    # A flush inner curb and physically thick turf system prevent coplanar or
    # floating field surfaces.
    _capsule_ring(
        "precast_inner_track_curb",
        INNER_RADIUS + 0.02,
        INNER_RADIUS - 0.12,
        0.320,
        0.435,
        materials["concrete"],
        master,
    )
    _capsule_solid(
        "football_turf_drainage_base",
        INNER_RADIUS - 0.13,
        0.245,
        0.350,
        materials["subbase"],
        master,
    )
    _capsule_solid(
        "football_turf_carpet",
        INNER_RADIUS - 0.18,
        0.350,
        TRACK_TOP_Z + 0.006,
        materials["turf"],
        master,
    )

    stripe_width = PITCH_LENGTH / 12
    for stripe in range(12):
        if stripe % 2 == 0:
            x = -PITCH_LENGTH / 2 + (stripe + 0.5) * stripe_width
            _cube(
                "alternating_mowing_stripe",
                (x, 0, TRACK_TOP_Z + 0.012),
                (stripe_width - 0.025, PITCH_WIDTH - 0.10, 0.014),
                materials["turf_alt"],
                master,
                0.006,
            )
    _pitch_markings(master, materials)
    _build_goal(master, materials, -1)
    _build_goal(master, materials, 1)
    _field_event_areas(master, materials)

    # Finish line and staggered lane starts reproduce actual running function.
    finish_x = 6.35
    _line_ribbon(
        "photo_finish_line",
        [(finish_x, -OUTER_RADIUS + 0.04), (finish_x, -INNER_RADIUS - 0.04)],
        0.075,
        TRACK_TOP_Z + 0.024,
        materials["line"],
        master,
    )
    for lane in range(LANE_COUNT):
        y0 = -OUTER_RADIUS + lane * LANE_WIDTH + 0.08
        y1 = y0 + LANE_WIDTH - 0.16
        _line_ribbon(
            f"staggered_lane_start_{lane + 1:02d}",
            [(finish_x + 0.48 + lane * 0.20, y0), (finish_x + 0.48 + lane * 0.20, y1)],
            0.065,
            TRACK_TOP_Z + 0.024,
            materials["line"],
            master,
        )
        _cube(
            f"lane_marker_plate_{lane + 1:02d}",
            (finish_x + 0.12, (y0 + y1) / 2, TRACK_TOP_Z + 0.035),
            (0.22, 0.28, 0.025),
            materials["line"],
            master,
            0.015,
        )
    return master


def _build_fence_master(materials):
    master = bpy.data.collections.new(PREFIX + "MASTER:WELDED_MESH_SPORT_FENCE_PANEL")
    width, height = 2.40, 1.80
    for x in (-width / 2, width / 2):
        _cube(
            "fence_post_footing",
            (x, 0, 0.10),
            (0.34, 0.34, 0.20),
            materials["concrete"],
            master,
            0.035,
        )
        _cylinder(
            "fence_post",
            (x, 0, 1.02),
            0.048,
            2.04,
            materials["fence"],
            master,
            24,
            bevel=0.008,
        )
        _cylinder(
            "fence_post_weather_cap",
            (x, 0, 2.055),
            0.063,
            0.055,
            materials["fence"],
            master,
            24,
            bevel=0.008,
        )
    for z in (0.25, 1.03, 1.86):
        _beam(
            "fence_horizontal_rail",
            (-width / 2, 0, z),
            (width / 2, 0, z),
            0.025,
            materials["fence"],
            master,
            16,
        )
    for index in range(11):
        x = -width / 2 + width * index / 10
        _beam(
            "welded_mesh_vertical_wire",
            (x, 0, 0.27),
            (x, 0, 1.84),
            0.006,
            materials["fence"],
            master,
            10,
        )
    for index in range(8):
        z = 0.30 + 1.50 * index / 7
        _beam(
            "welded_mesh_horizontal_wire",
            (-width / 2, 0, z),
            (width / 2, 0, z),
            0.006,
            materials["fence"],
            master,
            10,
        )
    master[
        "construction_system"
    ] = "hot-dip galvanized posts with powder-coated welded wire infill"
    return master


def _add_access_gate(site, materials, x, y, name):
    width, height = 1.80, 1.78
    for side in (-1, 1):
        px = x + side * width / 2
        _cube(
            name + "_post_footing",
            (px, y, 0.14),
            (0.38, 0.38, 0.28),
            materials["concrete"],
            site,
            0.04,
        )
        _cylinder(
            name + "_gate_post",
            (px, y, 1.02),
            0.060,
            2.02,
            materials["fence"],
            site,
            24,
            bevel=0.009,
        )
    for z in (0.30, 1.82):
        _beam(
            name + "_leaf_horizontal",
            (x - width / 2 + 0.08, y, z),
            (x + width / 2 - 0.08, y, z),
            0.032,
            materials["fence"],
            site,
            18,
        )
    for gx in range(8):
        px = x - width / 2 + 0.12 + gx * (width - 0.24) / 7
        _beam(
            name + "_leaf_mesh_vertical",
            (px, y, 0.33),
            (px, y, 1.79),
            0.007,
            materials["fence"],
            site,
            10,
        )
    for gz in range(7):
        pz = 0.36 + gz * 1.38 / 6
        _beam(
            name + "_leaf_mesh_horizontal",
            (x - width / 2 + 0.12, y, pz),
            (x + width / 2 - 0.12, y, pz),
            0.007,
            materials["fence"],
            site,
            10,
        )
    _cube(
        name + "_lock_case",
        (x + width / 2 - 0.18, y - 0.07, 1.08),
        (0.22, 0.16, 0.14),
        materials["steel_dark"],
        site,
        0.022,
    )
    _cylinder(
        name + "_lever_handle",
        (x + width / 2 - 0.29, y - 0.19, 1.10),
        0.018,
        0.30,
        materials["steel"],
        site,
        14,
        (math.pi / 2, 0, 0),
        0.003,
    )


def _add_bleachers(site, materials, cx, north_track_edge):
    front_y = north_track_edge + 0.22
    _cube(
        "bleacher_reinforced_foundation",
        (cx, front_y + 0.58, 0.25),
        (21.0, 1.52, 0.30),
        materials["concrete_dark"],
        site,
        0.045,
    )
    seat_count = 0
    row_specs = (
        (front_y + 0.12, 0.56),
        (front_y + 0.47, 0.84),
        (front_y + 0.82, 1.12),
    )
    for row, (y, z) in enumerate(row_specs):
        depth = 0.40 + row * 0.36
        _cube(
            "bleacher_precast_tier",
            (cx, y + (depth - 0.40) / 2, z - 0.23),
            (20.70, depth, 0.46 + row * 0.02),
            materials["concrete"],
            site,
            0.018,
        )
        _cube(
            "bleacher_anti_slip_nosing",
            (cx, y - 0.175, z + 0.025),
            (20.55, 0.055, 0.045),
            materials["steel_dark"],
            site,
            0.006,
        )
        for slot in range(25):
            if slot in (6, 12, 18):
                continue
            x = cx - 9.55 + slot * 0.795
            seat_material = (
                materials["seat_red"] if (slot + row) % 3 else materials["seat_orange"]
            )
            _cube(
                "modular_bleacher_seat_pan",
                (x, y, z + 0.14),
                (0.68, 0.29, 0.075),
                seat_material,
                site,
                0.045,
            )
            back = _cube(
                "modular_bleacher_seat_back",
                (x, y + 0.11, z + 0.43),
                (0.68, 0.075, 0.53),
                seat_material,
                site,
                0.045,
            )
            back.rotation_euler[0] = math.radians(-8)
            seat_count += 1
    # Three concrete stair aisles and continuous safety rails make the stand
    # usable, not just repeated floating seat blocks.
    for aisle_x in (cx - 4.78, cx, cx + 4.78):
        for step in range(3):
            _cube(
                "bleacher_aisle_step",
                (aisle_x, front_y + 0.13 + step * 0.35, 0.50 + step * 0.28),
                (0.62, 0.36, 0.26),
                materials["concrete_dark"],
                site,
                0.018,
            )
            _cube(
                "bleacher_aisle_tactile_nosing",
                (aisle_x, front_y - 0.035 + step * 0.35, 0.645 + step * 0.28),
                (0.55, 0.045, 0.035),
                materials["yellow"],
                site,
                0.006,
            )
        for side in (-1, 1):
            x = aisle_x + side * 0.30
            _beam(
                "bleacher_aisle_handrail",
                (x, front_y, 1.18),
                (x, front_y + 0.96, 1.95),
                0.026,
                materials["steel"],
                site,
                18,
            )
            for fraction in (0, 0.5, 1):
                y = front_y + 0.96 * fraction
                z = 0.60 + 0.80 * fraction
                _beam(
                    "bleacher_aisle_baluster",
                    (x, y, z),
                    (x, y, z + 0.78),
                    0.020,
                    materials["steel"],
                    site,
                    16,
                )
    rear_y = front_y + 1.08
    _beam(
        "bleacher_rear_top_guardrail",
        (cx - 10.25, rear_y, 2.03),
        (cx + 10.25, rear_y, 2.03),
        0.034,
        materials["steel"],
        site,
        20,
    )
    _beam(
        "bleacher_rear_mid_guardrail",
        (cx - 10.25, rear_y, 1.55),
        (cx + 10.25, rear_y, 1.55),
        0.026,
        materials["steel"],
        site,
        18,
    )
    for index in range(15):
        x = cx - 10.25 + 20.50 * index / 14
        _beam(
            "bleacher_rear_guardrail_post",
            (x, rear_y, 1.12),
            (x, rear_y, 2.07),
            0.025,
            materials["steel"],
            site,
            18,
        )
    for x in (cx - 10.25, cx + 10.25):
        _beam(
            "bleacher_end_guardrail",
            (x, front_y, 0.70),
            (x, rear_y, 2.02),
            0.032,
            materials["steel"],
            site,
            20,
        )
    return seat_count


def _add_timing_room(site, materials, cx, north_track_edge):
    room_x, room_y = cx - 17.10, north_track_edge + 0.78
    _cube(
        "timing_room_foundation",
        (room_x, room_y, 0.28),
        (4.60, 1.34, 0.34),
        materials["concrete"],
        site,
        0.04,
    )
    _cube(
        "timing_room_insulated_rear_wall",
        (room_x, room_y + 0.53, 1.43),
        (4.46, 0.18, 2.08),
        materials["wall"],
        site,
        0.022,
    )
    _cube(
        "timing_room_west_return_wall",
        (room_x - 2.14, room_y, 1.43),
        (0.18, 1.10, 2.08),
        materials["wall"],
        site,
        0.022,
    )
    _cube(
        "timing_room_east_return_wall",
        (room_x + 2.14, room_y, 1.43),
        (0.18, 1.10, 2.08),
        materials["wall"],
        site,
        0.022,
    )
    _cube(
        "timing_room_front_shadow_reveal",
        (room_x, room_y - 0.53, 1.46),
        (4.22, 0.10, 1.90),
        materials["dark"],
        site,
        0.012,
    )
    for index, x in enumerate((room_x - 1.36, room_x, room_x + 1.36)):
        _cube(
            "timing_room_front_glazing",
            (x, room_y - 0.595, 1.53),
            (1.19, 0.045, 1.55),
            materials["glass"],
            site,
            0.012,
        )
        for side in (-1, 1):
            _cube(
                "timing_room_window_jamb",
                (x + side * 0.625, room_y - 0.625, 1.53),
                (0.055, 0.10, 1.70),
                materials["steel_dark"],
                site,
                0.008,
            )
        _cube(
            "timing_room_window_header",
            (x, room_y - 0.625, 2.36),
            (1.30, 0.10, 0.055),
            materials["steel_dark"],
            site,
            0.008,
        )
        _cube(
            "timing_room_window_sill",
            (x, room_y - 0.625, 0.70),
            (1.30, 0.13, 0.065),
            materials["steel_dark"],
            site,
            0.008,
        )
    _cube(
        "timing_room_access_door",
        (room_x - 2.22, room_y + 0.02, 1.31),
        (0.055, 0.78, 1.90),
        materials["steel_dark"],
        site,
        0.012,
    )
    _cylinder(
        "timing_room_door_pull",
        (room_x - 2.285, room_y - 0.20, 1.34),
        0.015,
        0.38,
        materials["steel"],
        site,
        14,
        (0, math.pi / 2, 0),
        0.003,
    )
    # Two genuinely pitched standing-seam roof leaves with fascia and gutters.
    for side in (-1, 1):
        roof = _cube(
            "timing_room_pitched_roof_leaf",
            (room_x, room_y + side * 0.35, 2.68),
            (4.95, 0.82, 0.12),
            materials["roof"],
            site,
            0.012,
        )
        roof.rotation_euler[0] = side * math.radians(10)
    _cube(
        "timing_room_roof_ridge_cap",
        (room_x, room_y, 2.76),
        (5.02, 0.12, 0.12),
        materials["steel_dark"],
        site,
        0.018,
    )
    for index in range(11):
        x = room_x - 2.25 + index * 0.45
        for side in (-1, 1):
            _cube(
                "timing_room_roof_standing_seam",
                (x, room_y + side * 0.34, 2.755),
                (0.025, 0.72, 0.035),
                materials["steel_dark"],
                site,
                0.004,
            )
    _cube(
        "timing_room_gutter",
        (room_x, room_y - 0.79, 2.59),
        (4.92, 0.10, 0.10),
        materials["steel"],
        site,
        0.018,
    )
    _cylinder(
        "timing_room_downpipe",
        (room_x + 2.23, room_y - 0.72, 1.36),
        0.034,
        2.42,
        materials["steel"],
        site,
        18,
        bevel=0.006,
    )
    _cube(
        "timing_room_photo_finish_camera_body",
        (room_x + 2.02, room_y - 0.77, 2.35),
        (0.38, 0.28, 0.24),
        materials["steel_dark"],
        site,
        0.035,
    )
    _cylinder(
        "timing_room_photo_finish_lens",
        (room_x + 2.02, room_y - 0.93, 2.35),
        0.075,
        0.12,
        materials["glass"],
        site,
        24,
        (math.pi / 2, 0, 0),
        0.006,
    )


def _add_floodlight(site, materials, location, target, index):
    x, y = location
    _cube(
        f"floodlight_{index:02d}_reinforced_footing",
        (x, y, 0.20),
        (0.84, 0.84, 0.40),
        materials["concrete"],
        site,
        0.07,
    )
    _cube(
        f"floodlight_{index:02d}_base_plate",
        (x, y, 0.44),
        (0.58, 0.58, 0.075),
        materials["steel"],
        site,
        0.035,
    )
    for dx, dy in ((-0.21, -0.21), (-0.21, 0.21), (0.21, -0.21), (0.21, 0.21)):
        _cylinder(
            f"floodlight_{index:02d}_anchor_bolt",
            (x + dx, y + dy, 0.51),
            0.022,
            0.13,
            materials["steel_dark"],
            site,
            14,
            bevel=0.004,
        )
    _cylinder(
        f"floodlight_{index:02d}_tapered_mast_lower",
        (x, y, 3.15),
        0.105,
        5.35,
        materials["steel"],
        site,
        28,
        bevel=0.012,
    )
    _cylinder(
        f"floodlight_{index:02d}_tapered_mast_upper",
        (x, y, 6.75),
        0.078,
        2.05,
        materials["steel"],
        site,
        28,
        bevel=0.010,
    )
    _beam(
        f"floodlight_{index:02d}_crossarm",
        (x - 0.86, y, 7.78),
        (x + 0.86, y, 7.78),
        0.052,
        materials["steel_dark"],
        site,
        22,
    )
    direction = Vector((target[0] - x, target[1] - y, -5.8)).normalized()
    yaw = math.atan2(direction.y, direction.x)
    for lamp_index, offset in enumerate((-0.58, 0, 0.58)):
        lx = x + offset
        _beam(
            f"floodlight_{index:02d}_luminaire_bracket",
            (lx, y, 7.76),
            (lx, y + direction.y * 0.32, 7.55),
            0.026,
            materials["steel"],
            site,
            16,
        )
        housing = _cube(
            f"floodlight_{index:02d}_luminaire_housing",
            (lx, y + direction.y * 0.37, 7.53),
            (0.48, 0.28, 0.22),
            materials["steel_dark"],
            site,
            0.035,
            yaw - math.pi / 2,
        )
        housing.rotation_euler[0] = math.radians(18 if direction.y < 0 else -18)
        lens = _cube(
            f"floodlight_{index:02d}_luminaire_lens",
            (lx, y + direction.y * 0.525, 7.46),
            (0.36, 0.035, 0.13),
            materials["light"],
            site,
            0.012,
            yaw - math.pi / 2,
        )
        lens.rotation_euler[0] = housing.rotation_euler[0]


def _add_site_drainage(site, materials, cx, cy):
    y = cy - 9.18
    _cube(
        "athletics_linear_drain_channel",
        (cx, y, 0.255),
        (33.8, 0.30, 0.16),
        materials["drain"],
        site,
        0.025,
    )
    bars = 0
    for index in range(96):
        x = cx - 16.55 + index * 33.10 / 95
        _cube(
            "athletics_linear_drain_grate_bar",
            (x, y, 0.347),
            (0.045, 0.245, 0.025),
            materials["steel"],
            site,
            0.004,
        )
        bars += 1
    for x in (cx - 16.9, cx + 16.9):
        _cube(
            "athletics_catch_basin_frame",
            (x, y, 0.29),
            (0.54, 0.54, 0.15),
            materials["drain"],
            site,
            0.025,
        )
        for index in range(7):
            _cube(
                "athletics_catch_basin_bar",
                (x - 0.21 + index * 0.07, y, 0.382),
                (0.028, 0.44, 0.025),
                materials["steel"],
                site,
                0.004,
            )
    return bars


def _add_site_construction(site, materials, center):
    cx, cy = center.x, center.y
    _rounded_slab(
        "permeable_teal_perimeter_apron",
        cx,
        (SITE_BOUNDS[2] + SITE_BOUNDS[3]) / 2,
        SITE_BOUNDS[1] - SITE_BOUNDS[0],
        SITE_BOUNDS[3] - SITE_BOUNDS[2],
        0.17,
        0.26,
        1.25,
        materials["apron"],
        site,
    )
    _rounded_slab(
        "north_access_walk",
        cx,
        -42.22,
        42.90,
        0.42,
        0.315,
        0.18,
        0.16,
        materials["concrete"],
        site,
    )
    for index in range(22):
        x = cx - 20.45 + index * 1.95
        _line_ribbon(
            "north_access_walk_sawcut",
            [(x, -42.40), (x, -42.04)],
            0.014,
            0.410,
            materials["concrete_dark"],
            site,
        )

    north_track_edge = cy + OUTER_RADIUS
    seat_count = _add_bleachers(site, materials, cx, north_track_edge)
    _add_timing_room(site, materials, cx, north_track_edge)

    fence_master = _build_fence_master(materials)
    fence_instances = 0
    # South and end fences follow the parcel edge; north panels leave broad
    # openings for the stand and two controlled pedestrian gates.
    for index in range(18):
        x = SITE_BOUNDS[0] + 1.22 + index * 2.40
        _instance(
            site,
            fence_master,
            f"south_perimeter_fence_panel_{index:02d}",
            (x, SITE_BOUNDS[2] + 0.05, 0.30),
            0,
        )
        fence_instances += 1
    for side, x in (("west", SITE_BOUNDS[0] + 0.05), ("east", SITE_BOUNDS[1] - 0.05)):
        for index in range(7):
            y = SITE_BOUNDS[2] + 1.38 + index * 2.40
            _instance(
                site,
                fence_master,
                f"{side}_perimeter_fence_panel_{index:02d}",
                (x, y, 0.30),
                math.pi / 2,
            )
            fence_instances += 1
    for index, x in enumerate((11.30, 13.70, 18.55, 45.35, 50.20, 52.60)):
        _instance(
            site,
            fence_master,
            f"north_perimeter_fence_panel_{index:02d}",
            (x, SITE_BOUNDS[3] + 0.06, 0.30),
            0,
        )
        fence_instances += 1
    _add_access_gate(
        site,
        materials,
        cx - 12.00,
        SITE_BOUNDS[3] + 0.03,
        "west_pedestrian_access_gate",
    )
    _add_access_gate(
        site,
        materials,
        cx + 12.00,
        SITE_BOUNDS[3] + 0.03,
        "east_pedestrian_access_gate",
    )

    light_sites = (
        (cx - 13.85, SITE_BOUNDS[3] + 0.24),
        (cx + 13.85, SITE_BOUNDS[3] + 0.24),
        (cx - 13.85, SITE_BOUNDS[2] + 0.24),
        (cx + 13.85, SITE_BOUNDS[2] + 0.24),
    )
    for index, location in enumerate(light_sites):
        _add_floodlight(site, materials, location, (cx, cy), index)

    drain_bars = _add_site_drainage(site, materials, cx, cy)
    return {
        "bleacher_seats": seat_count,
        "fence_panel_instances": fence_instances,
        "floodlight_masts": len(light_sites),
        "floodlight_luminaires": len(light_sites) * 3,
        "linear_drain_grate_bars": drain_bars,
    }


def clear_stale_revision():
    stale_objects = [obj for obj in bpy.data.objects if obj.name.startswith(PREFIX)]
    if stale_objects:
        bpy.data.batch_remove(stale_objects)
    stale_collections = [
        collection
        for collection in bpy.data.collections
        if collection.name.startswith(PREFIX)
    ]
    if stale_collections:
        bpy.data.batch_remove(stale_collections)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        stale = [
            block
            for block in datablocks
            if block.name.startswith(PREFIX) and block.users == 0
        ]
        if stale:
            bpy.data.batch_remove(stale)
    return len(stale_objects)


def _audit(master, ground, site, inherited_count, detail_stats):
    master_objects = list(master.all_objects)
    revision_objects = [obj for obj in bpy.data.objects if obj.name.startswith(PREFIX)]
    names = [obj.name.lower() for obj in revision_objects]
    forbidden = [
        obj.name
        for obj in revision_objects
        if any(
            token in obj.name.lower()
            for token in ("toy", "proxy", "placeholder", "dummy", "lowpoly", "low_poly")
        )
    ]
    goal_rear_x = PITCH_LENGTH / 2 + 0.06 + 0.92
    long_jump_nearest_x = 14.32 - 3.85 / 2
    long_jump_nearest_y = -3.42 + 0.82 / 2
    goal_event_clearance = math.hypot(
        long_jump_nearest_x - goal_rear_x,
        abs(long_jump_nearest_y) - 1.68,
    )
    checks = {
        "ground_is_reusable_collection_instance": ground.instance_type == "COLLECTION"
        and ground.instance_collection == master,
        "master_component_count": len(master_objects),
        "revision_object_count": len(revision_objects),
        "inherited_all44_10_object_count": inherited_count,
        "epdm_running_lane_bands": sum("epdm_running_lane_" in name for name in names),
        "continuous_lane_boundaries": sum(
            "continuous_lane_boundary_" in name for name in names
        ),
        "football_pitch_marking_objects": sum(
            "football_pitch_" in name
            or "football_penalty_" in name
            or "football_goal_area" in name
            or "football_corner_arc" in name
            for name in names
        ),
        "football_goal_net_cords": sum("football_goal_net_" in name for name in names),
        "field_event_components": sum(
            "shot_put_" in name or "long_jump_" in name for name in names
        ),
        "minimum_goal_to_field_event_clearance_m": round(goal_event_clearance, 3),
        **detail_stats,
        "world_site_bounds": [list(SITE_BOUNDS[:2]), list(SITE_BOUNDS[2:])],
        "layout_clearances_m": {
            "to_retained_all44_10_south_edge": round((-41.90) - SITE_BOUNDS[3], 3),
            "to_leisure_south_limit": round(SITE_BOUNDS[2] - (-62.0), 3),
            "to_leisure_west_limit": round(SITE_BOUNDS[0] - 9.5, 3),
            "to_leisure_east_limit": round(54.4 - SITE_BOUNDS[1], 3),
        },
        "track_model_class": "parcel-constrained four-lane community training ground",
        "regulation_400m_claimed": False,
        "reference_adjacent_white_building_generated": False,
        "forbidden_degenerate_asset_names": forbidden,
    }
    failures = []
    minimums = {
        "master_component_count": 95,
        "inherited_all44_10_object_count": 150,
        "epdm_running_lane_bands": LANE_COUNT,
        "continuous_lane_boundaries": LANE_COUNT + 1,
        "football_pitch_marking_objects": 12,
        "football_goal_net_cords": 30,
        "field_event_components": 12,
        "bleacher_seats": 55,
        "fence_panel_instances": 35,
        "floodlight_masts": 4,
        "floodlight_luminaires": 12,
        "linear_drain_grate_bars": 90,
    }
    for key, minimum in minimums.items():
        if checks[key] < minimum:
            failures.append(f"{key}={checks[key]} below required {minimum}")
    if not checks["ground_is_reusable_collection_instance"]:
        failures.append("athletics ground is not a reusable collection instance")
    if min(checks["layout_clearances_m"].values()) < 0.15:
        failures.append(f"unsafe site clearance: {checks['layout_clearances_m']}")
    if checks["minimum_goal_to_field_event_clearance_m"] < 1.0:
        failures.append(
            "goal/field-event safety clearance below 1.0 m: "
            f"{checks['minimum_goal_to_field_event_clearance_m']}"
        )
    if forbidden:
        failures.append(f"forbidden degenerate asset names: {forbidden[:20]}")
    if failures:
        raise RuntimeError(
            {"all44_11_athletics_quality_audit_failed": failures, "checks": checks}
        )
    site["c2w_quality_audit"] = json.dumps(checks, sort_keys=True)
    return {
        "pipeline_stage": "generate_urban_v3_all44_11.py",
        "architectural_program": master["architectural_program"],
        "reference_translation": master["reference_translation"],
        "track_system": "compacted subbase, asphalt shockpad, four separately formed EPDM lanes and continuous markings",
        "pitch_system": "drained turf carpet, alternating mowing bands, complete youth football markings and two framed/netted goals",
        "spectator_system": "reinforced three-tier stand with modular seats, aisles, nosings and code-height guardrails",
        "operations_system": "photo-finish room, field-event areas, controlled gates, welded-mesh fence, connected drains and four triple-head floodlights",
        "quality_policy": "real construction assemblies and audited production masters; no toy, proxy or unrelated white massing",
        **checks,
    }


def install_athletics_ground(root, center=GROUND_CENTER, manage_viewport=True):
    """Install the source-generated athletics facility in the leisure root."""
    inherited_count = sum(not obj.name.startswith(PREFIX) for obj in root.all_objects)
    paused_modifiers = []
    if manage_viewport:
        for obj in bpy.context.scene.objects:
            for modifier in obj.modifiers:
                if modifier.type == "NODES" and modifier.show_viewport:
                    modifier.show_viewport = False
                    paused_modifiers.append(modifier)
    try:
        clear_stale_revision()
        materials = athletics_materials()
        site = bpy.data.collections.new(SITE_NAME)
        root.children.link(site)
        site["c2w_semantic_zone"] = "connected outdoor community athletics ground"
        site[
            "c2w_layout_policy"
        ] = "south extension preserves all ALL44-10 leisure construction"
        site[
            "reference_exclusion"
        ] = "unrelated adjacent white building blocks are not generated"
        master = build_athletics_master(materials)
        ground = _instance(site, master, "community_athletics_ground", center)
        ground[
            "c2w_semantic_role"
        ] = "real-scale parcel-constrained athletics training facility"
        ground["c2w_pipeline_stage"] = "all44_11"
        ground[
            "reference_scope"
        ] = "sports ground only; adjacent white massing excluded"
        detail_stats = _add_site_construction(site, materials, center)
        audit = _audit(master, ground, site, inherited_count, detail_stats)
        audit["viewport_scatter_modifiers_paused_during_assembly"] = len(
            paused_modifiers
        )
        root["all44_11_athletics_audit"] = json.dumps(audit, sort_keys=True)
        return site, audit
    finally:
        for modifier in paused_modifiers:
            modifier.show_viewport = True


def add_service_building_details(materials, root):
    """Production hook: retain ALL44-10 service building and add the track."""
    service_building = previous.add_service_building_details(materials, root)
    site, audit = install_athletics_ground(root)
    root["all44_11_retained_service_building"] = service_building.name
    root["all44_11_athletics_audit"] = json.dumps(audit, sort_keys=True)
    return site


def _focused_render_visibility():
    old = {obj: obj.hide_render for obj in bpy.context.scene.objects}
    for obj in bpy.context.scene.objects:
        tree_dependency = any(
            collection.name.startswith("assets:TreeFactory")
            or collection.name.startswith("assets:GenericTreeFactory")
            for collection in obj.users_collection
        )
        keep = (
            obj.name.startswith(("all44_04:", "all44_10:", PREFIX))
            or obj.type == "LIGHT"
            or tree_dependency
        )
        obj.hide_render = not keep
    return old


def _restore_render_visibility(old):
    for obj, hidden in old.items():
        if obj.name in bpy.context.scene.objects:
            obj.hide_render = hidden


def render_outputs(config, camera):
    samples = 10 if config.quality == "final" else 3
    base.aim(camera, (2.0, -3.0, 61.0), (30.5, -37.0, 1.8), 37)
    base.render(
        config.output / "leisure_zone_with_athletics_ground.png", (1280, 720), samples
    )

    base.aim(camera, (5.2, -29.0, 34.0), (GROUND_CENTER.x, GROUND_CENTER.y, 0.65), 45)
    base.render(
        config.output / "athletics_ground_reference_aerial.png", (1280, 720), samples
    )

    if config.quality == "final":
        base.aim(camera, (8.5, -48.0, 7.2), (GROUND_CENTER.x, GROUND_CENTER.y, 1.0), 54)
        base.render(config.output / "athletics_track_pitch_detail.png", (1280, 720), 12)
        base.aim(
            camera,
            (23.0, -58.0, 5.8),
            (GROUND_CENTER.x, SITE_BOUNDS[3] + 0.70, 1.25),
            56,
        )
        base.render(
            config.output / "athletics_stand_timing_room_detail.png", (1280, 720), 12
        )


def main():
    config = args()
    config.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(config.input), load_ui=False)
    root = bpy.data.collections.get("all44_10:COURT_PLAYGROUND_REBUILD")
    if root is None:
        raise RuntimeError(
            "ALL44-11 focused generation requires the ALL44-10 leisure root collection"
        )

    _site, audit = install_athletics_ground(root)
    old_visibility = _focused_render_visibility()
    render_outputs(config, bpy.context.scene.camera)
    _restore_render_visibility(old_visibility)

    blend_path = config.output / "urban_v3_all44_11.blend"
    bpy.context.scene["c2w_leisure_generator"] = "generate_urban_v3_all44_11.py"
    bpy.context.scene["c2w_leisure_revision"] = "urban_v3_all44_11"
    bpy.context.scene[
        "c2w_reference_scope"
    ] = "athletics ground only; adjacent white massing excluded"
    bpy.context.scene["c2w_source_level_generation"] = True
    if not config.skip_save:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    render_names = [
        "leisure_zone_with_athletics_ground.png",
        "athletics_ground_reference_aerial.png",
    ]
    if config.quality == "final":
        render_names.extend(
            (
                "athletics_track_pitch_detail.png",
                "athletics_stand_timing_room_detail.png",
            )
        )
    stats = {
        "output": str(blend_path),
        "input": str(config.input),
        "quality": config.quality,
        "source_level_generator": True,
        "pipeline_interface": "add_service_building_details(materials, root)",
        "retained_all44_10_leisure_zone": True,
        "retained_all44_10_service_building": True,
        "athletics_ground_added_as_reusable_master": True,
        "reference_adjacent_white_building_generated": False,
        "render_outputs": render_names,
        "athletics_audit": audit,
        "skip_save": config.skip_save,
        "total_seconds": round(time.perf_counter() - started, 3),
        "blend_file_bytes": blend_path.stat().st_size
        if blend_path.exists() and not config.skip_save
        else None,
    }
    (config.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf8",
    )
    print("ALL44_11_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
