"""ALL44-12: reference-driven oval gymnasium for the production leisure region.

The generator keeps the complete ALL44-10 playground, outdoor court, service
building, landscape and circulation system, then extends that parcel southward
with a civic gymnasium based on the supplied reference image.  The building is
authored from source as a reusable collection master: an elliptical podium,
glazed structural facade, deep perimeter eave, two asymmetric curved roof
shells, clerestory, concourse, entrance construction and a connected public
forecourt.

``add_service_building_details`` preserves the hook consumed by
``generate_urban_v1_full_01.py``.  In a clean full-city build it generates both
the retained ALL44-10 service building and this stadium.  The focused entry
point opens the requested ALL44-10 result and installs only the new stadium,
so existing source-authored leisure objects are never duplicated.
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
OUTPUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_12"
PREFIX = "all44_12:"
MASTER_NAME = PREFIX + "MASTER:REFERENCE_OVAL_GYMNASIUM"
SITE_NAME = PREFIX + "GYMNASIUM_AND_CONNECTED_FORECOURT"
_BOX_MESH_CACHE = {}
_CYLINDER_MESH_CACHE = {}

# The west edge clears the existing K6 commercial pavement by 0.35 m, the
# east edge remains inside the established x=54.5 planning limit, and the
# 2.55 m north clearance is deliberately used as the connected entrance plaza.
STADIUM_CENTER = Vector((39.70, -53.35, 0.18))
FACADE_RX = 14.05
FACADE_RY = 7.85
EAVE_RX = 14.55
EAVE_RY = 8.65
EAVE_Z = 7.28

# Re-export the stable ALL44-10 leisure interface and material names.
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
    parser.add_argument(
        "--skip-save",
        action="store_true",
        help="Render-only development pass; production runs always omit this flag.",
    )
    return parser.parse_args(values)


def _material(
    name, color, roughness, metallic=0.0, noise=0.0, transmission=0.0, emission=0.0
):
    material = bpy.data.materials.new(PREFIX + name)
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
    if bsdf.inputs.get("IOR") is not None:
        bsdf.inputs["IOR"].default_value = 1.46
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
        texture.inputs["Scale"].default_value = 24
        texture.inputs["Detail"].default_value = 5
        texture.inputs["Roughness"].default_value = 0.63
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise
        bump.inputs["Distance"].default_value = 0.035
        material.node_tree.links.new(texture.outputs["Fac"], bump.inputs["Height"])
        material.node_tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*tuple(max(0, c * 0.86) for c in color), 1)
        ramp.color_ramp.elements[1].color = (
            *tuple(min(1, c * 1.08 + 0.018) for c in color),
            1,
        )
        material.node_tree.links.new(texture.outputs["Fac"], ramp.inputs["Fac"])
        material.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def stadium_materials():
    return {
        "glass": _material(
            "MAT_CURTAIN_WALL_LOW_IRON_GLASS",
            (0.12, 0.22, 0.25),
            0.16,
            0.04,
            transmission=0.36,
        ),
        "glass_alt": _material(
            "MAT_CURTAIN_WALL_SMOKE_GLASS",
            (0.055, 0.10, 0.12),
            0.19,
            0.03,
            transmission=0.28,
        ),
        "clerestory": _material(
            "MAT_ROOF_CLERESTORY_GLASS",
            (0.025, 0.052, 0.065),
            0.13,
            0.12,
            transmission=0.22,
        ),
        "aluminum": _material(
            "MAT_SATIN_ALUMINUM_FRAME", (0.33, 0.36, 0.37), 0.28, 0.76, noise=0.025
        ),
        "steel": _material(
            "MAT_EXPOSED_STRUCTURAL_STEEL",
            (0.075, 0.085, 0.087),
            0.32,
            0.78,
            noise=0.018,
        ),
        "fascia": _material(
            "MAT_WARM_SILVER_FASCIA", (0.55, 0.54, 0.52), 0.38, 0.58, noise=0.045
        ),
        "roof_a": _material(
            "MAT_STANDING_SEAM_ROOF_LIGHT", (0.58, 0.57, 0.55), 0.54, 0.38, noise=0.055
        ),
        "roof_b": _material(
            "MAT_STANDING_SEAM_ROOF_PEARL", (0.68, 0.66, 0.63), 0.48, 0.42, noise=0.045
        ),
        "membrane": _material(
            "MAT_ROOF_EDGE_MEMBRANE", (0.075, 0.077, 0.074), 0.82, 0.08, noise=0.06
        ),
        "concrete": _material(
            "MAT_ARCHITECTURAL_CONCRETE", (0.39, 0.37, 0.34), 0.88, noise=0.16
        ),
        "concrete_dark": _material(
            "MAT_INNER_BOWL_CONCRETE", (0.12, 0.13, 0.13), 0.90, noise=0.13
        ),
        "paver_a": _material(
            "MAT_FORECOURT_GRANITE_LIGHT", (0.47, 0.45, 0.42), 0.88, noise=0.10
        ),
        "paver_b": _material(
            "MAT_FORECOURT_GRANITE_MID", (0.33, 0.32, 0.30), 0.90, noise=0.11
        ),
        "tactile": _material(
            "MAT_ENTRANCE_TACTILE_STONE", (0.56, 0.39, 0.13), 0.86, noise=0.08
        ),
        "door": _material(
            "MAT_ENTRANCE_DOOR_GLASS",
            (0.085, 0.16, 0.18),
            0.14,
            0.08,
            transmission=0.32,
        ),
        "interior": _material(
            "MAT_CONCOURSE_WARM_INTERIOR", (0.30, 0.20, 0.12), 0.72, noise=0.05
        ),
        "seat": _material(
            "MAT_ARENA_SEATING_GRAPHITE", (0.075, 0.09, 0.095), 0.68, 0.02, noise=0.05
        ),
        "light": _material(
            "MAT_CONCOURSE_LINEAR_LIGHT", (0.96, 0.78, 0.50), 0.26, emission=4.2
        ),
        "sign": _material(
            "MAT_CIVIC_SIGNAGE", (0.78, 0.79, 0.76), 0.32, 0.62, noise=0.015
        ),
        "soil": _material(
            "MAT_STADIUM_TREE_SOIL", (0.095, 0.055, 0.028), 0.96, noise=0.24
        ),
        "drain": _material(
            "MAT_STADIUM_DRAIN_CAST_IRON", (0.035, 0.04, 0.04), 0.43, 0.76, noise=0.035
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
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    return obj


def _box_mesh(dimensions, material):
    dimensions = tuple(round(float(value), 6) for value in dimensions)
    key = (dimensions, material.name)
    mesh = _BOX_MESH_CACHE.get(key)
    if mesh is not None:
        return mesh
    x, y, z = (value / 2 for value in dimensions)
    vertices = [
        (-x, -y, -z),
        (x, -y, -z),
        (x, y, -z),
        (-x, y, -z),
        (-x, -y, z),
        (x, -y, z),
        (x, y, z),
        (-x, y, z),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(
        PREFIX + f"shared_manufactured_box_{len(_BOX_MESH_CACHE):04d}"
    )
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    _BOX_MESH_CACHE[key] = mesh
    return mesh


def _cube(name, location, dimensions, material, collection, bevel=0.025, rotation=0.0):
    obj = bpy.data.objects.new(PREFIX + name, _box_mesh(dimensions, material))
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler[2] = rotation
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    return obj


def _cylinder_mesh(radius, depth, vertices, material):
    key = (
        round(float(radius), 6),
        round(float(depth), 6),
        int(vertices),
        material.name,
    )
    mesh = _CYLINDER_MESH_CACHE.get(key)
    if mesh is not None:
        return mesh
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
    mesh = bpy.data.meshes.new(
        PREFIX + f"shared_manufactured_cylinder_{len(_CYLINDER_MESH_CACHE):04d}"
    )
    mesh.from_pydata(coordinates, [], faces)
    mesh.materials.append(material)
    mesh.update()
    _CYLINDER_MESH_CACHE[key] = mesh
    return mesh


def _cylinder(
    name,
    location,
    radius,
    depth,
    material,
    collection,
    vertices=28,
    rotation=(0, 0, 0),
    bevel=0.012,
):
    obj = bpy.data.objects.new(
        PREFIX + name, _cylinder_mesh(radius, depth, vertices, material)
    )
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def _beam(name, start, end, radius, material, collection, vertices=24):
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
        bevel=0.008,
    )
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def _curve(name, points, radius, material, collection, cyclic=False, resolution=2):
    curve = bpy.data.curves.new(PREFIX + name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.resolution_u = resolution
    spline = curve.splines.new("NURBS" if len(points) > 4 else "POLY")
    spline.points.add(len(points) - 1)
    for point, coordinate in zip(spline.points, points):
        point.co = (*coordinate, 1)
    if spline.type == "NURBS":
        spline.order_u = min(3, len(points))
        spline.use_endpoint_u = not cyclic
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(PREFIX + name, curve)
    collection.objects.link(obj)
    curve.materials.append(material)
    return obj


def _ellipse_points(rx, ry, z, count=128):
    return [
        (
            rx * math.cos(math.tau * index / count),
            ry * math.sin(math.tau * index / count),
            z,
        )
        for index in range(count)
    ]


def _ellipse_solid(
    name, rx, ry, z0, z1, material, collection, segments=128, bevel=0.02
):
    vertices = [(0, 0, z0), (0, 0, z1)]
    vertices += _ellipse_points(rx, ry, z0, segments)
    vertices += _ellipse_points(rx, ry, z1, segments)
    faces = []
    for index in range(segments):
        nxt = (index + 1) % segments
        faces.append((0, 2 + nxt, 2 + index))
        faces.append((1, 2 + segments + index, 2 + segments + nxt))
        faces.append((2 + index, 2 + nxt, 2 + segments + nxt, 2 + segments + index))
    return _mesh_object(name, vertices, faces, collection, [material], bevel=bevel)


def _ellipse_ring(
    name,
    outer_rx,
    outer_ry,
    inner_rx,
    inner_ry,
    z0,
    z1,
    material,
    collection,
    segments=128,
):
    vertices = []
    for z in (z0, z1):
        vertices.extend(_ellipse_points(outer_rx, outer_ry, z, segments))
        vertices.extend(_ellipse_points(inner_rx, inner_ry, z, segments))
    faces = []
    for index in range(segments):
        nxt = (index + 1) % segments
        ob, ib = index, segments + index
        ot, it = segments * 2 + index, segments * 3 + index
        obn, ibn = nxt, segments + nxt
        otn, itn = segments * 2 + nxt, segments * 3 + nxt
        faces.extend(
            (
                (ot, otn, itn, it),
                (ob, ib, ibn, obn),
                (obn, otn, ot, ob),
                (ib, it, itn, ibn),
            )
        )
    return _mesh_object(name, vertices, faces, collection, [material], bevel=0.018)


def _facade_mesh(collection, materials, segments=96):
    levels = (1.18, 2.62, 3.02, 4.72, 5.10, 6.52)
    vertices, faces, indices = [], [], []
    for segment in range(segments):
        a0 = math.tau * segment / segments
        a1 = math.tau * (segment + 1) / segments
        amid = (a0 + a1) / 2
        entrance = (
            abs(math.atan2(math.sin(amid - math.pi / 2), math.cos(amid - math.pi / 2)))
            < 0.34
        )
        for level in range(len(levels) - 1):
            if entrance and levels[level] < 4.72:
                continue
            z0, z1 = levels[level], levels[level + 1]
            start = len(vertices)
            vertices.extend(
                (
                    (FACADE_RX * math.cos(a0), FACADE_RY * math.sin(a0), z0),
                    (FACADE_RX * math.cos(a1), FACADE_RY * math.sin(a1), z0),
                    (FACADE_RX * math.cos(a1), FACADE_RY * math.sin(a1), z1),
                    (FACADE_RX * math.cos(a0), FACADE_RY * math.sin(a0), z1),
                )
            )
            faces.append((start, start + 1, start + 2, start + 3))
            indices.append(1 if level in (1, 3) else (segment % 9 == 0))
    facade = _mesh_object(
        "segmented_low_iron_curtain_wall",
        vertices,
        faces,
        collection,
        [materials["glass"], materials["glass_alt"]],
        indices,
    )
    solidify = facade.modifiers.new("laminated_glass_thickness", "SOLIDIFY")
    solidify.thickness = 0.055
    return facade


def _roof_height(u, v, side, cross_fraction):
    dome = max(0.0, 1.0 - u * u - v * v)
    base_height = EAVE_Z + 0.32 + 3.42 * dome**0.62
    if side == "north":
        base_height += 0.72 * max(0.0, 1.0 - u * u) * (1.0 - cross_fraction) ** 1.55
    return base_height


def _roof_shell(name, side, material, collection, nx=48, ny=22):
    vertices = []
    samples = []
    for ix in range(nx + 1):
        u = -0.995 + 1.99 * ix / nx
        ymax = math.sqrt(max(0.0, 1.0 - u * u))
        ridge = 0.075 * (1 - u * u) + 0.020 * math.sin(math.pi * u)
        gap = 0.043
        if side == "north":
            start, end = ridge + gap, ymax
        else:
            start, end = -ymax, ridge - gap
        row = []
        for iy in range(ny + 1):
            fraction = iy / ny
            v = start + (end - start) * fraction
            z = _roof_height(u, v, side, fraction)
            row.append(len(vertices))
            vertices.append((13.62 * u, 7.38 * v, z))
        samples.append(row)
    faces = []
    for ix in range(nx):
        for iy in range(ny):
            faces.append(
                (
                    samples[ix][iy],
                    samples[ix + 1][iy],
                    samples[ix + 1][iy + 1],
                    samples[ix][iy + 1],
                )
            )
    shell = _mesh_object(name, vertices, faces, collection, [material])
    for polygon in shell.data.polygons:
        polygon.use_smooth = True
    solidify = shell.modifiers.new("formed_metal_shell_thickness", "SOLIDIFY")
    solidify.thickness = 0.12
    solidify.offset = -1
    bevel = shell.modifiers.new("folded_shell_edge_softness", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 3
    return shell


def _roof_ribs(collection, materials):
    ribs = 0
    for side in ("north", "south"):
        for index, u in enumerate(
            (-0.88, -0.72, -0.55, -0.36, -0.18, 0, 0.18, 0.36, 0.55, 0.72, 0.88)
        ):
            ymax = math.sqrt(max(0.0, 1 - u * u))
            ridge = 0.075 * (1 - u * u) + 0.020 * math.sin(math.pi * u)
            gap = 0.043
            start, end = (
                (ridge + gap, ymax) if side == "north" else (-ymax, ridge - gap)
            )
            points = []
            for step in range(25):
                fraction = step / 24
                v = start + (end - start) * fraction
                points.append(
                    (13.62 * u, 7.38 * v, _roof_height(u, v, side, fraction) + 0.075)
                )
            _curve(
                f"standing_seam_roof_rib_{side}_{index:02d}",
                points,
                0.018,
                materials["membrane"],
                collection,
            )
            ribs += 1

    # Two continuous raised edges frame the glazed ventilation/clerestory slot.
    for edge, side in ((1, "north"), (-1, "south")):
        points = []
        for index in range(65):
            u = -0.97 + 1.94 * index / 64
            ridge = 0.075 * (1 - u * u) + 0.020 * math.sin(math.pi * u)
            v = ridge + edge * 0.043
            fraction = 0.0 if side == "north" else 1.0
            points.append(
                (13.62 * u, 7.38 * v, _roof_height(u, v, side, fraction) + 0.08)
            )
        _curve(
            f"clerestory_edge_arch_{side}",
            points,
            0.052,
            materials["steel"],
            collection,
        )
        ribs += 1
    return ribs


def _clerestory(collection, materials, segments=64):
    vertices, faces = [], []
    for index in range(segments + 1):
        u = -0.97 + 1.94 * index / segments
        ridge = 0.075 * (1 - u * u) + 0.020 * math.sin(math.pi * u)
        for edge, side, fraction in ((-0.040, "south", 1.0), (0.040, "north", 0.0)):
            v = ridge + edge
            z = _roof_height(u, v, side, fraction) - 0.10
            vertices.append((13.62 * u, 7.38 * v, z))
    for index in range(segments):
        a = index * 2
        b = (index + 1) * 2
        faces.append((a, b, b + 1, a + 1))
    clerestory = _mesh_object(
        "continuous_curved_roof_clerestory",
        vertices,
        faces,
        collection,
        [materials["clerestory"]],
    )
    solidify = clerestory.modifiers.new("clerestory_laminated_thickness", "SOLIDIFY")
    solidify.thickness = 0.065
    return clerestory


def _add_concourse_and_bowl(master, materials):
    _ellipse_solid(
        "reinforced_elliptical_foundation",
        14.18,
        8.02,
        -0.08,
        0.24,
        materials["concrete"],
        master,
        128,
        0.035,
    )
    _ellipse_solid(
        "raised_public_concourse_floor",
        13.85,
        7.72,
        0.24,
        1.15,
        materials["concrete"],
        master,
        128,
        0.035,
    )
    _ellipse_ring(
        "upper_concourse_floor",
        13.36,
        7.18,
        10.65,
        4.82,
        3.46,
        3.68,
        materials["concrete"],
        master,
    )
    _ellipse_ring(
        "lower_facade_plinth",
        14.12,
        7.92,
        13.62,
        7.42,
        0.62,
        1.22,
        materials["concrete"],
        master,
    )
    _ellipse_ring(
        "inner_acoustic_bowl_wall",
        10.75,
        4.92,
        10.35,
        4.52,
        1.12,
        6.42,
        materials["concrete_dark"],
        master,
    )

    # Tiered seating is visible behind the transparent concourse instead of an
    # empty black shell.  Each tier is a real elliptical concrete/seat ring.
    for tier in range(5):
        outer_rx = 10.45 + tier * 0.50
        outer_ry = 4.62 + tier * 0.38
        _ellipse_ring(
            f"arena_seating_tier_{tier:02d}",
            outer_rx,
            outer_ry,
            outer_rx - 0.38,
            outer_ry - 0.28,
            1.28 + tier * 0.42,
            1.52 + tier * 0.42,
            materials["seat"] if tier % 2 else materials["interior"],
            master,
            112,
        )

    # Warm continuous concourse lights make the glazed facade legible without
    # adding dozens of expensive point lights.
    for level, z in enumerate((3.25, 5.84)):
        for index in range(28):
            angle = math.tau * (index + 0.5 * level) / 28
            x, y = 12.25 * math.cos(angle), 6.28 * math.sin(angle)
            tangent = math.atan2(6.28 * math.cos(angle), -12.25 * math.sin(angle))
            _cube(
                f"concourse_linear_light_{level}_{index:02d}",
                (x, y, z),
                (0.64, 0.075, 0.055),
                materials["light"],
                master,
                0.008,
                tangent,
            )


def _add_curtain_wall_and_structure(master, materials):
    _facade_mesh(master, materials)
    # Continuous horizontal pressure caps and spandrel rails.
    for index, z in enumerate((1.18, 2.62, 3.02, 4.72, 5.10, 6.52)):
        _curve(
            f"elliptical_curtain_wall_rail_{index:02d}",
            _ellipse_points(FACADE_RX + 0.045, FACADE_RY + 0.045, z, 128),
            0.035,
            materials["aluminum"],
            master,
            True,
        )

    # Slender mullions and larger outward-raking structural columns reproduce
    # the layered transparent facade in the reference.
    for index in range(64):
        angle = math.tau * index / 64
        bottom = (FACADE_RX * math.cos(angle), FACADE_RY * math.sin(angle), 1.16)
        top = (FACADE_RX * math.cos(angle), FACADE_RY * math.sin(angle), 6.55)
        _beam(
            f"curtain_wall_vertical_mullion_{index:02d}",
            bottom,
            top,
            0.027,
            materials["aluminum"],
            master,
            16,
        )
    for index in range(32):
        angle = math.tau * (index + 0.5) / 32
        bottom = (13.82 * math.cos(angle), 7.56 * math.sin(angle), 0.88)
        top = (14.43 * math.cos(angle), 8.34 * math.sin(angle), 7.05)
        _beam(
            f"raking_perimeter_structure_{index:02d}",
            bottom,
            top,
            0.085,
            materials["steel"],
            master,
            28,
        )
        inner = (13.18 * math.cos(angle), 6.92 * math.sin(angle), 7.48)
        _beam(
            f"radial_eave_cantilever_{index:02d}",
            top,
            inner,
            0.060,
            materials["steel"],
            master,
            24,
        )

    _ellipse_ring(
        "deep_elliptical_perimeter_eave",
        EAVE_RX,
        EAVE_RY,
        13.28,
        7.04,
        6.98,
        7.58,
        materials["fascia"],
        master,
        160,
    )
    _curve(
        "continuous_outer_gutter",
        _ellipse_points(EAVE_RX + 0.02, EAVE_RY + 0.02, 7.02, 160),
        0.045,
        materials["steel"],
        master,
        True,
    )

    # Roof drainage is attached to real columns and terminates at formed shoes.
    for index, angle in enumerate(
        (
            0,
            math.pi / 2,
            math.pi,
            3 * math.pi / 2,
            math.pi / 4,
            3 * math.pi / 4,
            5 * math.pi / 4,
            7 * math.pi / 4,
        )
    ):
        x, y = 14.18 * math.cos(angle), 8.04 * math.sin(angle)
        _cylinder(
            f"concealed_roof_downpipe_{index:02d}",
            (x, y, 3.62),
            0.044,
            6.45,
            materials["steel"],
            master,
            24,
            bevel=0.008,
        )
        _cube(
            f"formed_downpipe_shoe_{index:02d}",
            (x, y, 0.42),
            (0.22, 0.30, 0.18),
            materials["steel"],
            master,
            0.018,
            angle,
        )


def _add_entrances_and_service(master, materials):
    # Five full-height entrance bays face north toward the existing court.
    for bay, x in enumerate((-2.36, -1.18, 0, 1.18, 2.36)):
        y = FACADE_RY * math.sqrt(max(0, 1 - (x / FACADE_RX) ** 2)) + 0.035
        _cube(
            f"main_entrance_glazed_door_{bay:02d}",
            (x, y, 2.14),
            (1.04, 0.075, 2.08),
            materials["door"],
            master,
            0.014,
        )
        for side in (-0.55, 0.55):
            _cube(
                f"main_entrance_door_jamb_{bay:02d}",
                (x + side, y + 0.025, 2.14),
                (0.055, 0.12, 2.18),
                materials["aluminum"],
                master,
                0.007,
            )
        _cube(
            f"main_entrance_door_header_{bay:02d}",
            (x, y + 0.025, 3.24),
            (1.14, 0.12, 0.075),
            materials["aluminum"],
            master,
            0.008,
        )
        _cylinder(
            f"main_entrance_pull_handle_{bay:02d}",
            (x + 0.30, y + 0.09, 2.10),
            0.018,
            0.62,
            materials["sign"],
            master,
            16,
            bevel=0.004,
        )
    _cube(
        "entrance_transom_glazing",
        (0, FACADE_RY + 0.05, 3.90),
        (6.45, 0.075, 1.06),
        materials["glass"],
        master,
        0.012,
    )
    _cube(
        "entrance_header_beam",
        (0, FACADE_RY + 0.09, 4.48),
        (7.05, 0.18, 0.18),
        materials["steel"],
        master,
        0.018,
    )
    for x in (-3.45, 3.45):
        _beam(
            "entrance_canopy_tie_rod",
            (x, 7.72, 4.52),
            (x, 8.55, 5.28),
            0.025,
            materials["steel"],
            master,
            20,
        )
    _cube(
        "entrance_weather_canopy",
        (0, 8.28, 4.38),
        (7.35, 1.15, 0.18),
        materials["fascia"],
        master,
        0.045,
    )

    text_curve = bpy.data.curves.new(PREFIX + "civic_gymnasium_sign_text", "FONT")
    text_curve.body = "CIVIC SPORTS CENTRE"
    text_curve.align_x = "CENTER"
    text_curve.align_y = "CENTER"
    text_curve.size = 0.58
    text_curve.extrude = 0.025
    text_curve.bevel_depth = 0.008
    text_curve.materials.append(materials["sign"])
    sign = bpy.data.objects.new(PREFIX + "civic_gymnasium_entrance_sign", text_curve)
    master.objects.link(sign)
    sign.location = (0, 8.04, 5.66)
    # Front face points north toward the arrival plaza.  Font-local +Y must be
    # inverted after the -90 degree wall rotation so the lettering remains
    # upright and readable rather than showing its mirrored back face.
    sign.rotation_euler = (-math.pi / 2, 0, 0)
    sign.scale = (-1, -1, 1)

    # Rear service elevation: paired doors, ventilation bank, protected plant
    # curb and conduit.  These prevent the back from becoming a blank toy wall.
    for bay, x in enumerate((-2.2, 2.2)):
        y = -FACADE_RY - 0.04
        _cube(
            f"rear_service_door_{bay:02d}",
            (x, y, 2.05),
            (1.65, 0.095, 2.62),
            materials["steel"],
            master,
            0.025,
        )
        _cube(
            f"rear_service_door_header_{bay:02d}",
            (x, y - 0.04, 3.42),
            (1.82, 0.15, 0.12),
            materials["aluminum"],
            master,
            0.012,
        )
    for row in range(9):
        _cube(
            "rear_mechanical_louver_blade",
            (5.35, -FACADE_RY - 0.10, 1.45 + row * 0.25),
            (2.80, 0.10, 0.075),
            materials["aluminum"],
            master,
            0.008,
        )
    _cube(
        "rear_mechanical_louver_frame",
        (5.35, -FACADE_RY - 0.08, 2.45),
        (3.12, 0.14, 2.56),
        materials["steel"],
        master,
        0.018,
    )
    _curve(
        "rear_service_conduit",
        [
            (6.85, -7.96, 1.0),
            (7.35, -7.96, 1.0),
            (7.35, -7.96, 4.15),
            (6.55, -7.96, 4.15),
        ],
        0.028,
        materials["aluminum"],
        master,
    )


def build_stadium_master(materials):
    existing = bpy.data.collections.get(MASTER_NAME)
    if existing is not None:
        return existing
    master = bpy.data.collections.new(MASTER_NAME)
    master["c2w_asset_class"] = "full-scale civic oval gymnasium"
    master[
        "reference_translation"
    ] = "elliptical glazed bowl, continuous silver eave, overlapping asymmetric roof shells and broad entrance steps"
    master["real_world_footprint_m"] = [round(EAVE_RX * 2, 2), round(EAVE_RY * 2, 2)]
    master[
        "construction_system"
    ] = "reinforced podium, raking steel frame, unitized curtain wall and formed standing-seam roof"

    _add_concourse_and_bowl(master, materials)
    _add_curtain_wall_and_structure(master, materials)
    _add_entrances_and_service(master, materials)
    _roof_shell("lower_south_curved_roof_shell", "south", materials["roof_a"], master)
    _roof_shell("raised_north_curved_roof_shell", "north", materials["roof_b"], master)
    _clerestory(master, materials)
    rib_count = _roof_ribs(master, materials)
    master["standing_seam_and_arch_ribs"] = rib_count
    return master


def _instance(collection, master, name, location, rotation=0.0, scale=1.0):
    obj = bpy.data.objects.new(PREFIX + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = location
    obj.rotation_euler[2] = rotation
    obj.scale = (scale, scale, scale)
    obj["c2w_role"] = "high-detail collection instance"
    obj["c2w_asset_id"] = master.name
    return obj


def _paver_field(site, materials):
    x0, x1 = 25.25, 54.40
    y0, y1 = -44.78, -41.82
    _cube(
        "forecourt_compacted_subbase",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.10),
        (x1 - x0, y1 - y0, 0.20),
        materials["concrete"],
        site,
        0.025,
    )
    nx, ny = 28, 5
    cell_x, cell_y = (x1 - x0) / nx, (y1 - y0) / ny
    for row in range(ny):
        for column in range(nx):
            material = (
                materials["paver_b"]
                if (row * 7 + column * 3) % 13 == 0
                else materials["paver_a"]
            )
            _cube(
                f"forecourt_modular_granite_paver_{row:02d}_{column:02d}",
                (x0 + (column + 0.5) * cell_x, y0 + (row + 0.5) * cell_y, 0.235),
                (cell_x - 0.025, cell_y - 0.025, 0.07),
                material,
                site,
                0.008,
            )
    return nx * ny


def _connect_forecourt_to_existing_court(site, materials):
    """Open one real fence bay and build the missing pedestrian link.

    The stadium sits beyond the court's south fence.  Leaving every retained
    ALL44-10 panel closed would force visitors around the parcel edge, so the
    southeast bay is replaced at source by a 2.6 m controlled passage with
    permanent posts, threshold paving and drainage continuity.
    """
    candidates = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith("all44_10:fence_s:")
        and abs(obj.location.x - 42.5) < 0.35
        and abs(obj.location.y + 39.7) < 0.35
    ]
    removed = len(candidates)
    if candidates:
        bpy.data.batch_remove(candidates)

    # Flush modular pavers bridge the retained court buffer to the forecourt.
    _cube(
        "court_to_stadium_passage_subbase",
        (42.50, -40.78, 0.105),
        (2.60, 2.18, 0.21),
        materials["concrete"],
        site,
        0.025,
    )
    path_pavers = 0
    for row in range(4):
        for column in range(4):
            _cube(
                f"court_to_stadium_passage_paver_{row:02d}_{column:02d}",
                (41.525 + column * 0.65, -39.97 - row * 0.55, 0.245),
                (0.625, 0.525, 0.075),
                materials["paver_b"]
                if (row + column) % 7 == 0
                else materials["paver_a"],
                site,
                0.008,
            )
            path_pavers += 1

    # Fixed posts, hinge barrels, base plates and latch plate make the opening
    # read as a deliberate serviceable gate rather than a missing fence panel.
    for side, x in (("west", 41.20), ("east", 43.80)):
        _cube(
            f"court_passage_gate_base_{side}",
            (x, -39.70, 0.18),
            (0.42, 0.42, 0.24),
            materials["concrete"],
            site,
            0.035,
        )
        _cylinder(
            f"court_passage_gate_post_{side}",
            (x, -39.70, 1.55),
            0.075,
            2.72,
            materials["steel"],
            site,
            28,
            bevel=0.012,
        )
        _cylinder(
            f"court_passage_post_cap_{side}",
            (x, -39.70, 2.96),
            0.105,
            0.08,
            materials["aluminum"],
            site,
            28,
            bevel=0.012,
        )
        for index, z in enumerate((0.78, 2.05)):
            _cylinder(
                f"court_passage_hinge_barrel_{side}_{index:02d}",
                (x + (0.10 if side == "west" else -0.10), -39.70, z),
                0.032,
                0.20,
                materials["aluminum"],
                site,
                18,
                (math.pi / 2, 0, 0),
                0.006,
            )
    _cube(
        "court_passage_latch_keeper",
        (43.65, -39.78, 1.18),
        (0.28, 0.16, 0.12),
        materials["aluminum"],
        site,
        0.018,
    )

    # Short transverse drain prevents the new threshold from interrupting the
    # established low-edge court drainage.
    _cube(
        "court_passage_threshold_drain",
        (42.50, -41.70, 0.285),
        (2.45, 0.26, 0.12),
        materials["drain"],
        site,
        0.015,
    )
    for index in range(9):
        _cube(
            "court_passage_threshold_drain_bar",
            (41.46 + index * 0.26, -41.70, 0.353),
            (0.035, 0.21, 0.022),
            materials["aluminum"],
            site,
            0.004,
        )
    return {
        "retained_south_fence_panels_replaced_by_gate": removed,
        "court_connection_is_open": not any(
            obj.name.startswith("all44_10:fence_s:")
            and abs(obj.location.x - 42.5) < 0.35
            and abs(obj.location.y + 39.7) < 0.35
            for obj in bpy.data.objects
        ),
        "court_connection_path_pavers": path_pavers,
    }


def _inclined_slab(name, x0, x1, y0, y1, z0, z1, thickness, material, site):
    vertices = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z1),
        (x0, y1, z1),
        (x0, y0, z0 - thickness),
        (x1, y0, z0 - thickness),
        (x1, y1, z1 - thickness),
        (x0, y1, z1 - thickness),
    ]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return _mesh_object(name, vertices, faces, site, [material], bevel=0.018)


def _entrance_steps_and_access(site, materials):
    center_x = STADIUM_CENTER.x
    door_y = STADIUM_CENTER.y + FACADE_RY + 0.02
    front_y = -42.72
    stair_count = 6
    for index in range(stair_count):
        near = front_y - index * 0.49
        width = 13.3 - index * 0.22
        top = 0.34 + index * 0.157
        _cube(
            f"broad_entrance_step_{index:02d}",
            (center_x, (near + door_y) / 2, top / 2),
            (width, abs(door_y - near), top),
            materials["concrete"],
            site,
            0.018,
        )
    # Tactile warning field is modular rather than a flat painted strip.
    for row in range(2):
        for column in range(20):
            _cube(
                f"entrance_tactile_paver_{row:02d}_{column:02d}",
                (center_x - 5.70 + column * 0.60, front_y + 0.30 - row * 0.31, 0.305),
                (0.55, 0.26, 0.055),
                materials["tactile"],
                site,
                0.006,
            )

    ramp_y0, ramp_y1 = front_y + 0.10, door_y
    ramp_bottom, ramp_top = 0.27, 1.30
    for side, xa, xb in (
        ("west", center_x - 8.10, center_x - 6.70),
        ("east", center_x + 6.70, center_x + 8.10),
    ):
        _inclined_slab(
            f"accessible_entrance_ramp_{side}",
            xa,
            xb,
            ramp_y0,
            ramp_y1,
            ramp_bottom,
            ramp_top,
            0.13,
            materials["concrete"],
            site,
        )
        for x in (xa + 0.08, xb - 0.08):
            _beam(
                f"accessible_ramp_handrail_{side}",
                (x, ramp_y0, ramp_bottom + 0.88),
                (x, ramp_y1, ramp_top + 0.88),
                0.030,
                materials["steel"],
                site,
                20,
            )
            for fraction in (0, 0.5, 1):
                y = ramp_y0 + (ramp_y1 - ramp_y0) * fraction
                z = ramp_bottom + (ramp_top - ramp_bottom) * fraction
                _beam(
                    f"accessible_ramp_baluster_{side}",
                    (x, y, z + 0.04),
                    (x, y, z + 0.88),
                    0.024,
                    materials["steel"],
                    site,
                    18,
                )

    # Paired handrails divide the broad stair into safe arrival lanes.
    for x in (center_x - 3.9, center_x, center_x + 3.9):
        _beam(
            "entrance_stair_sloping_handrail",
            (x, front_y, 1.10),
            (x, door_y + 0.25, 2.18),
            0.032,
            materials["steel"],
            site,
            20,
        )
        for fraction in (0, 0.33, 0.66, 1):
            y = front_y + (door_y + 0.25 - front_y) * fraction
            z = 0.34 + (1.30 - 0.34) * fraction
            _beam(
                "entrance_stair_handrail_baluster",
                (x, y, z),
                (x, y, z + 0.82),
                0.024,
                materials["steel"],
                site,
                18,
            )


def _shared_collection_height(master):
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in master.all_objects
        if obj.type == "MESH" and obj.data
        for corner in obj.bound_box
    ]
    return (
        (max(point.z for point in points) - min(point.z for point in points))
        if points
        else 0.0
    )


def _add_forecourt_details(site, materials):
    instances = 0
    bench = bpy.data.collections.get("all44_10:MASTER_EDGE_BENCH")
    bin_master = bpy.data.collections.get("all44_10:MASTER_BIN")
    lamp = bpy.data.collections.get("all44_10:MASTER_LAMP")
    if bench:
        _instance(
            site, bench, "forecourt_west_bench", (28.10, -43.05, 0.29), math.pi / 2
        )
        _instance(
            site, bench, "forecourt_east_bench", (51.75, -43.05, 0.29), -math.pi / 2
        )
        instances += 2
    if bin_master:
        _instance(site, bin_master, "forecourt_waste_bin", (49.95, -42.75, 0.29))
        instances += 1
    if lamp:
        for index, x in enumerate((26.55, 53.10)):
            _instance(
                site,
                lamp,
                f"forecourt_area_light_{index:02d}",
                (x, -44.00, 0.28),
                math.pi / 2,
            )
            instances += 1

    # Reuse real TreeFactory assets from the backbone.  Scaling is derived
    # from their actual mesh height, never guessed from a proxy cylinder.
    tree_masters = sorted(
        [
            collection
            for collection in bpy.data.collections
            if collection.name.startswith("assets:GenericTreeFactory")
        ],
        key=lambda collection: collection.name,
    )
    tree_instances = 0
    if tree_masters:
        for index, (x, y) in enumerate(((26.55, -42.60), (53.15, -42.60))):
            master = tree_masters[index % len(tree_masters)]
            source_height = _shared_collection_height(master)
            if source_height <= 0:
                continue
            scale = (6.2 + index * 0.4) / source_height
            _cube(
                f"forecourt_tree_bed_{index:02d}",
                (x, y, 0.20),
                (2.15, 1.70, 0.22),
                materials["soil"],
                site,
                0.12,
            )
            tree = _instance(
                site,
                master,
                f"forecourt_high_detail_tree_{index:02d}",
                (x, y, 0.31),
                index * 1.37,
                scale,
            )
            tree["c2w_real_world_tree_height_m"] = 6.2 + index * 0.4
            tree[
                "c2w_landscape_asset_policy"
            ] = "existing procedural TreeFactory master"
            tree_instances += 1
            instances += 1

    # Six stainless bicycle hoops, protective bollards and a connected linear
    # drain complete the operational forecourt.
    for index in range(6):
        x = 29.15 + index * 0.72
        y = -44.05
        _beam(
            "forecourt_bicycle_hoop_leg",
            (x - 0.24, y, 0.29),
            (x - 0.24, y, 1.08),
            0.032,
            materials["steel"],
            site,
            20,
        )
        _beam(
            "forecourt_bicycle_hoop_leg",
            (x + 0.24, y, 0.29),
            (x + 0.24, y, 1.08),
            0.032,
            materials["steel"],
            site,
            20,
        )
        points = [
            (
                x + 0.24 * math.cos(math.pi * step / 12),
                y,
                1.08 + 0.24 * math.sin(math.pi * step / 12),
            )
            for step in range(13)
        ]
        _curve("forecourt_bicycle_hoop_arch", points, 0.032, materials["steel"], site)
    for index, x in enumerate((31.0, 32.6, 47.1, 48.7)):
        _cylinder(
            f"entrance_protective_bollard_{index:02d}",
            (x, -42.38, 0.64),
            0.075,
            0.72,
            materials["steel"],
            site,
            28,
            bevel=0.018,
        )
        _curve(
            f"bollard_reflective_band_{index:02d}",
            _ellipse_points(0.081, 0.081, 0, 32),
            0.010,
            materials["sign"],
            site,
            True,
        )
        band = bpy.data.objects[PREFIX + f"bollard_reflective_band_{index:02d}"]
        band.location = (x, -42.38, 0.84)

    _cube(
        "forecourt_linear_drain_frame",
        (39.80, -41.94, 0.275),
        (22.6, 0.32, 0.13),
        materials["drain"],
        site,
        0.018,
    )
    for index in range(72):
        _cube(
            "forecourt_linear_drain_bar",
            (28.55 + index * 0.317, -41.94, 0.348),
            (0.045, 0.265, 0.022),
            materials["aluminum"],
            site,
            0.004,
        )
    return {"shared_asset_instances": instances, "tree_instances": tree_instances}


def clear_stale_revision():
    objects = [obj for obj in bpy.data.objects if obj.name.startswith(PREFIX)]
    if objects:
        bpy.data.batch_remove(objects)
    collections = [
        collection
        for collection in bpy.data.collections
        if collection.name.startswith(PREFIX)
    ]
    if collections:
        bpy.data.batch_remove(collections)
    return len(objects)


def _audit(master, stadium, site, paver_count, detail_stats):
    master_objects = list(master.all_objects)
    revision_objects = [obj for obj in bpy.data.objects if obj.name.startswith(PREFIX)]
    roof_shells = [obj for obj in master_objects if "curved_roof_shell" in obj.name]
    structural_columns = [
        obj for obj in master_objects if "raking_perimeter_structure" in obj.name
    ]
    mullions = [
        obj for obj in master_objects if "curtain_wall_vertical_mullion" in obj.name
    ]
    doors = [obj for obj in master_objects if "main_entrance_glazed_door" in obj.name]
    forbidden = [
        obj.name
        for obj in revision_objects
        if any(
            token in obj.name.lower()
            for token in ("toy", "proxy", "placeholder", "dummy", "lowpoly", "low_poly")
        )
    ]
    invalid_dimensions = []
    for obj in revision_objects:
        if obj.type != "MESH" or not obj.data or not obj.data.vertices:
            continue
        # Read the authored mesh coordinates directly.  Querying
        # ``Object.dimensions`` here asks Blender to update the complete
        # inherited dependency graph once per component, which is pathological
        # in the 4 GB city scene even though the audit only concerns new meshes.
        axes = tuple(
            tuple(vertex.co[axis] for vertex in obj.data.vertices) for axis in range(3)
        )
        if any(max(values) - min(values) <= 0 for values in axes):
            invalid_dimensions.append(obj.name)
    mesh_vertices = sum(
        len(obj.data.vertices)
        for obj in master_objects
        if obj.type == "MESH" and obj.data
    )
    checks = {
        "stadium_is_collection_instance": stadium.instance_type == "COLLECTION"
        and stadium.instance_collection == master,
        "master_component_count": len(master_objects),
        "revision_object_count": len(revision_objects),
        "master_mesh_vertices": mesh_vertices,
        "curved_roof_shells": len(roof_shells),
        "standing_seam_and_arch_ribs": master.get("standing_seam_and_arch_ribs", 0),
        "raking_structural_columns": len(structural_columns),
        "curtain_wall_mullions": len(mullions),
        "full_height_entrance_doors": len(doors),
        "modular_forecourt_pavers": paver_count,
        "shared_asset_instances": detail_stats["shared_asset_instances"],
        "high_detail_tree_instances": detail_stats["tree_instances"],
        "retained_south_fence_panels_replaced_by_gate": detail_stats[
            "retained_south_fence_panels_replaced_by_gate"
        ],
        "court_connection_is_open": detail_stats["court_connection_is_open"],
        "court_connection_path_pavers": detail_stats["court_connection_path_pavers"],
        "world_footprint_bounds": [
            [
                round(STADIUM_CENTER.x - EAVE_RX, 3),
                round(STADIUM_CENTER.y - EAVE_RY, 3),
                round(STADIUM_CENTER.z, 3),
            ],
            [
                round(STADIUM_CENTER.x + EAVE_RX, 3),
                round(STADIUM_CENTER.y + EAVE_RY, 3),
                round(STADIUM_CENTER.z + 11.8, 3),
            ],
        ],
        "layout_clearances_m": {
            "to_existing_leisure_south_edge": round(
                (-42.15) - (STADIUM_CENTER.y + EAVE_RY), 3
            ),
            "to_commercial_k6_pavement_east_edge": round(
                (STADIUM_CENTER.x - EAVE_RX) - 24.90, 3
            ),
            "to_east_planning_limit": round(54.50 - (STADIUM_CENTER.x + EAVE_RX), 3),
        },
        "forbidden_degenerate_asset_names": forbidden,
        "non_positive_mesh_dimensions": invalid_dimensions,
    }
    failures = []
    required_minimums = {
        "master_component_count": 180,
        "master_mesh_vertices": 9000,
        "curved_roof_shells": 2,
        "standing_seam_and_arch_ribs": 24,
        "raking_structural_columns": 32,
        "curtain_wall_mullions": 64,
        "full_height_entrance_doors": 5,
        "modular_forecourt_pavers": 140,
        "court_connection_path_pavers": 16,
    }
    for key, minimum in required_minimums.items():
        if checks[key] < minimum:
            failures.append(f"{key}={checks[key]} below required {minimum}")
    if not checks["stadium_is_collection_instance"]:
        failures.append("stadium is not a reusable collection instance")
    if not checks["court_connection_is_open"]:
        failures.append(
            "stadium forecourt is blocked by the retained south court fence"
        )
    if min(checks["layout_clearances_m"].values()) < 0.20:
        failures.append(f"unsafe site clearance: {checks['layout_clearances_m']}")
    if forbidden:
        failures.append(f"forbidden asset naming: {forbidden[:20]}")
    if invalid_dimensions:
        failures.append(f"non-positive mesh dimensions: {invalid_dimensions[:20]}")
    if failures:
        raise RuntimeError(
            {"all44_12_stadium_quality_audit_failed": failures, "checks": checks}
        )

    site["c2w_quality_audit"] = json.dumps(checks, sort_keys=True)
    return {
        "pipeline_stage": "generate_urban_v3_all44_12.py",
        "asset_master": master.name,
        "architectural_program": "full-scale civic indoor sports and events gymnasium",
        "reference_translation": master["reference_translation"],
        "roof_system": "two asymmetric formed shells, standing seams, dark curved clerestory and deep elliptical eave",
        "facade_system": "segmented low-iron curtain wall, pressure caps, spandrels and outward-raking steel columns",
        "public_realm_system": "modular granite forecourt, broad steps, paired accessible ramps, tactile paving, drainage, bicycle parking and shared high-detail assets",
        "quality_policy": "production-scale curved construction; forbidden degenerate-asset and dimensional audits passed",
        **checks,
    }


def install_parametric_stadium(root, center=STADIUM_CENTER, manage_viewport=True):
    """Build and place the gymnasium using the production regional interface.

    ``center`` is exposed for future descriptor-driven parcel placement.  The
    validated default is used by today's fixed four-zone city pipeline.
    """
    if tuple(center) != tuple(STADIUM_CENTER):
        raise ValueError(
            "ALL44-12 forecourt is validated only for the production leisure parcel center"
        )
    # The inherited city contains dense procedural scatter graphs.  Pausing
    # their viewport evaluation while adding manufactured objects avoids a full
    # vegetation re-evaluation after every paver/column.  Render visibility and
    # final geometry are unchanged, and every paused modifier is restored even
    # if the quality audit raises.
    paused_modifiers = []
    if manage_viewport:
        for obj in bpy.context.scene.objects:
            for modifier in obj.modifiers:
                if modifier.type == "NODES" and modifier.show_viewport:
                    modifier.show_viewport = False
                    paused_modifiers.append(modifier)
    try:
        clear_stale_revision()
        materials = stadium_materials()
        site = bpy.data.collections.new(SITE_NAME)
        root.children.link(site)
        site[
            "c2w_semantic_zone"
        ] = "leisure-serving civic gymnasium and connected forecourt"
        site[
            "c2w_layout_policy"
        ] = "south extension preserves ALL44-10 court, playground and service building"
        master = build_stadium_master(materials)
        stadium = _instance(site, master, "reference_oval_gymnasium", center)
        stadium["c2w_semantic_role"] = "full-scale civic sports venue"
        stadium["c2w_pipeline_stage"] = "all44_12"
        stadium["reference_image"] = "3d66 oval arena with overlapping roof shells"
        paver_count = _paver_field(site, materials)
        connection_stats = _connect_forecourt_to_existing_court(site, materials)
        _entrance_steps_and_access(site, materials)
        detail_stats = _add_forecourt_details(site, materials)
        detail_stats.update(connection_stats)
        audit = _audit(master, stadium, site, paver_count, detail_stats)
        audit["viewport_scatter_modifiers_paused_during_assembly"] = len(
            paused_modifiers
        )
        root["all44_12_stadium_audit"] = json.dumps(audit, sort_keys=True)
        return site, audit
    finally:
        for modifier in paused_modifiers:
            modifier.show_viewport = True


def add_service_building_details(materials, root):
    """Full-city hook: retain ALL44-10 service building and add the stadium."""
    service_building = previous.add_service_building_details(materials, root)
    site, audit = install_parametric_stadium(root)
    root["all44_12_retained_service_building"] = service_building.name
    root["all44_12_stadium_audit"] = json.dumps(audit, sort_keys=True)
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
    samples = 12 if config.quality == "final" else 3
    base.aim(camera, (-3.5, 5.5, 61.0), (31.2, -35.5, 2.4), 31)
    base.render(
        config.output / "activity_zone_with_stadium_overview.png", (1280, 720), samples
    )

    base.aim(camera, (5.5, -20.5, 33.0), (39.70, -53.35, 4.7), 45)
    base.render(config.output / "stadium_reference_aerial.png", (1280, 720), samples)

    base.aim(camera, (15.5, -28.5, 11.2), (39.70, -50.7, 3.8), 45)
    base.render(config.output / "stadium_entrance_connection.png", (1280, 720), samples)

    if config.quality == "final":
        base.aim(camera, (18.2, -47.0, 13.6), (39.3, -53.2, 6.4), 55)
        base.render(
            config.output / "stadium_facade_structure_close.png", (1280, 720), 14
        )
        base.aim(camera, (22.5, -39.0, 29.0), (39.70, -53.35, 7.2), 54)
        base.render(
            config.output / "stadium_overlapping_roof_close.png", (1280, 720), 14
        )


def main():
    config = args()
    config.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(config.input), load_ui=False)
    root = bpy.data.collections.get("all44_10:COURT_PLAYGROUND_REBUILD")
    if root is None:
        raise RuntimeError(
            "ALL44-12 focused generation requires the ALL44-10 leisure root collection"
        )

    # Keep inherited scatter modifiers out of viewport evaluation across the
    # whole focused assembly/render sequence.  Their show_render flags remain
    # untouched, so visible leisure vegetation is still evaluated by Cycles;
    # this merely avoids a redundant full-city viewport rebuild between asset
    # assembly and the first render.
    focused_paused_modifiers = []
    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type == "NODES" and modifier.show_viewport:
                modifier.show_viewport = False
                focused_paused_modifiers.append(modifier)
    _site, audit = install_parametric_stadium(root)
    audit["focused_viewport_modifiers_held_paused_until_save"] = len(
        focused_paused_modifiers
    )
    old_visibility = _focused_render_visibility()
    try:
        render_outputs(config, bpy.context.scene.camera)
    finally:
        _restore_render_visibility(old_visibility)
    if not config.skip_save:
        for modifier in focused_paused_modifiers:
            modifier.show_viewport = True

    blend_path = config.output / "urban_v3_all44_12.blend"
    bpy.context.scene["c2w_leisure_generator"] = "generate_urban_v3_all44_12.py"
    bpy.context.scene["c2w_leisure_revision"] = "urban_v3_all44_12"
    bpy.context.scene[
        "c2w_reference_scope"
    ] = "oval civic gymnasium with overlapping roof shells"
    bpy.context.scene["c2w_source_level_generation"] = True
    if not config.skip_save:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    render_names = [
        "activity_zone_with_stadium_overview.png",
        "stadium_reference_aerial.png",
        "stadium_entrance_connection.png",
    ]
    if config.quality == "final":
        render_names.extend(
            ("stadium_facade_structure_close.png", "stadium_overlapping_roof_close.png")
        )
    stats = {
        "output": str(blend_path),
        "input": str(config.input),
        "quality": config.quality,
        "source_level_generator": True,
        "pipeline_interface": "add_service_building_details(materials, root)",
        "retained_all44_10_leisure_zone": True,
        "retained_all44_10_service_building": True,
        "stadium_added_as_reusable_master": True,
        "render_outputs": render_names,
        "stadium_audit": audit,
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
    print("ALL44_12_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
