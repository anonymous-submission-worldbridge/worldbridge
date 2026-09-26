"""Reference-driven delivery facilities for the live Urban-v3 pipeline.

The module procedurally builds three independent production assets and can
compose them into one presentation row:

* a ten-column yellow/white food-delivery locker with clear numbered glazing;
* a long Fengchao-style green parcel locker beneath a steel rain canopy; and
* a glazed Cainiao-style parcel station with a complete working interior.

``build_food_delivery_locker``, ``build_parcel_locker`` and
``build_delivery_station`` are independent pipeline entrypoints.
``build_delivery_reference_row`` is the combined entrypoint used by
``scripts.urban_assets`` and by this file's daylight validation run.  The
generated blend is always an output, never an input to the production path.
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


import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
ASSET_ID = "urban_v3_delivery"
# Keep the logical pipeline asset id stable while publishing this requested
# refinement as a new, reproducible output revision.
OUTPUT_ID = os.environ.get("C2W_DELIVERY_OUTPUT_ID", "urban_v3_delivery6")
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / OUTPUT_ID
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
BLEND = OUT / f"{OUTPUT_ID}.blend"
PREFIX = "delivery:"
RNG = random.Random(260831)

FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
REFERENCE_URLS = {
    "food_locker_user_reference.jpg": "https://k.sinaimg.cn/n/sinakd10120/195/w485h510/20260602/afff-32baabfd0afdfa042a156231654cf64b.png/w700d1q75cms.jpg",
    "parcel_locker.jpg": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQWGjDgE8bXdc24xd6a94lNWKdffhfOTc7wl4EIqS2yEg&s",
    "station_exterior.jpg": "https://respic.3d66.com/coverimg/cache/290c/6e32e526f973ea774972482f4d064487.jpg!medium-size-2?v=30533812&k=D41D8CD98F00B204E9800998ECF8427E",
    "station_interior.jpg": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRoYfzWXy2MaHqvgHVm20aOFIMb6p4Q-z-uHX78La4eBw&s=10",
    "parcel_terminal_user_reference.jpg": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS7AAjB0eg1Ua96Q7UPIt3jDQLIio8E6pLja15HQINr3w&s=10",
    "station_screen_user_reference.jpg": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQFuj7DLPIjeXOPnp8ssC39vD9i6rd21RjKC7k8_cm4Uw&s",
    "infinigen_articulated_2505.10755.pdf": "https://arxiv.org/pdf/2505.10755",
}
METHOD_REFERENCE_URL = "https://arxiv.org/pdf/2505.10755"
METHOD_REFERENCE_FILE = "infinigen_articulated_2505.10755.pdf"
ARTICULATION_STANDARD = (
    "Infinigen-Articulated native hinge node groups + explicit rigid links + "
    "Blender hinge constraints + full-range clearance sweep"
)

# The ten-column food cabinet is wider than the previous five-column revision.
# Its center is shifted left so the cabinet and the parcel-locker canopy retain
# a physically credible service gap in the combined production composition.
FOOD_CENTER_X = -12.80
PARCEL_CENTER_X = -3.2
STATION_CENTER_X = 11.6

_MATERIALS: dict[str, bpy.types.Material] = {}
_PART_MESHES: dict[tuple, bpy.types.Mesh] = {}
_ARTICULATION_NODEGROUPS: dict[str, bpy.types.NodeTree] = {}
_PHYSICS_STATE: dict[str, object] = {}

# Only a non-adjacent subset is opened in presentation renders; every one of
# the 115 service doors is independently articulated and can be posed through
# its joint ID by the production builders.
_FOOD_SHOWCASE_DOORS = (13, 20, 29, 42, 55)
_PARCEL_SHOWCASE_DOORS = (4, 18, 25, 32, 46, 53)


# ---------------------------------------------------------------------------
# Core scene, geometry and material helpers


def set_prefix(value: str):
    """Set the namespace used when the generator is embedded in another scene."""
    global PREFIX
    PREFIX = value


def reset_scene():
    global _ARTICULATION_NODEGROUPS, _PHYSICS_STATE
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIALS.clear()
    _PART_MESHES.clear()
    _ARTICULATION_NODEGROUPS = {}
    _PHYSICS_STATE = {}


def collection(name: str, parent=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def anchor(coll, name: str, origin=(0.0, 0.0, 0.0), yaw=0.0):
    obj = bpy.data.objects.new(PREFIX + name, None)
    coll.objects.link(obj)
    obj.location = origin
    obj.rotation_euler.z = yaw
    obj["c2w_semantic"] = "asset_anchor"
    return obj


def semantic(obj, value: str, detail=False):
    obj["c2w_semantic"] = value
    obj["c2w_asset_part"] = True
    if detail:
        obj["c2w_quality_detail"] = True
    # Flush paper/tape layers are visible geometry but do not form a perceptible
    # independent shadow at their sub-centimetre offset.  Excluding only these
    # layers prevents Eevee's shadow atlas from being consumed by 1,600 tiny
    # rectangles while parcel bodies and every structural component still cast.
    if value in {"parcel_detail", "shipping_label"} and hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
        obj["c2w_shadow_policy"] = "attached_microdetail_no_independent_shadow"
    return obj


def _cube_mesh(name: str, dims):
    hx, hy, hz = (float(v) / 2 for v in dims)
    verts = [
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def box(
    coll,
    name,
    loc,
    dims,
    material,
    bevel=0.012,
    rot=(0.0, 0.0, 0.0),
    parent=None,
    sem="fixture",
    detail=None,
):
    mesh = _cube_mesh(name, dims)
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
    if bevel > 0:
        mod = obj.modifiers.new("manufactured_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2 if bevel >= 0.008 else 1
        mod.limit_method = "ANGLE"
    if detail is None:
        detail = sem in {
            "locker_hardware",
            "signage",
            "rack_detail",
            "workstation",
            "parcel_detail",
            "lighting_fixture",
            "architectural_detail",
        }
    return semantic(obj, sem, detail)


def front_frame(
    coll,
    name,
    loc,
    outer_dims,
    opening_dims,
    depth,
    material,
    bevel=0.010,
    parent=None,
    sem="fixture",
    detail=True,
):
    """Create one watertight manufactured frame with a real center opening.

    Four overlapping boxes read poorly at close range and cannot represent one
    fabricated door leaf.  This ring mesh includes front/back faces plus outer
    and inner reveal walls, so transparent glazing can expose a genuinely
    recessed compartment rather than a painted rectangle.
    """
    outer_x, outer_z = (float(value) / 2 for value in outer_dims)
    inner_x, inner_z = (float(value) / 2 for value in opening_dims)
    half_y = float(depth) / 2
    if inner_x <= 0 or inner_z <= 0 or inner_x >= outer_x or inner_z >= outer_z:
        raise ValueError(
            "Frame opening must be positive and smaller than outer dimensions"
        )

    verts = []
    for y in (-half_y, half_y):
        verts.extend(
            [
                (-outer_x, y, -outer_z),
                (outer_x, y, -outer_z),
                (outer_x, y, outer_z),
                (-outer_x, y, outer_z),
                (-inner_x, y, -inner_z),
                (inner_x, y, -inner_z),
                (inner_x, y, inner_z),
                (-inner_x, y, inner_z),
            ]
        )
    faces = []
    # Back and front annuli.
    for base, reverse in ((0, True), (8, False)):
        ring = [
            (base + 0, base + 1, base + 5, base + 4),
            (base + 1, base + 2, base + 6, base + 5),
            (base + 2, base + 3, base + 7, base + 6),
            (base + 3, base + 0, base + 4, base + 7),
        ]
        faces.extend(tuple(reversed(face)) if reverse else face for face in ring)
    # Outer perimeter and the four center-opening reveal walls.
    for index in range(4):
        nxt = (index + 1) % 4
        faces.append((index, 8 + index, 8 + nxt, nxt))
        faces.append((4 + index, 4 + nxt, 12 + nxt, 12 + index))

    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    if parent:
        obj.parent = parent
    if bevel > 0:
        mod = obj.modifiers.new("formed_frame_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    return semantic(obj, sem, detail)


def tapered_box(
    coll,
    name,
    loc,
    bottom_dims,
    top_dims,
    height,
    material,
    bevel=0.010,
    rot=(0.0, 0.0, 0.0),
    parent=None,
    sem="fixture",
    detail=True,
):
    """Create a manufactured tapered housing instead of a blocky stand-in."""
    bx, by = (float(v) / 2 for v in bottom_dims)
    tx, ty = (float(v) / 2 for v in top_dims)
    hz = float(height) / 2
    verts = [
        (-bx, -by, -hz),
        (bx, -by, -hz),
        (bx, by, -hz),
        (-bx, by, -hz),
        (-tx, -ty, hz),
        (tx, -ty, hz),
        (tx, ty, hz),
        (-tx, ty, hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
    if bevel:
        mod = obj.modifiers.new("manufactured_tapered_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return semantic(obj, sem, detail)


def part_box(
    coll,
    name,
    loc,
    dims,
    material,
    rot=(0.0, 0.0, 0.0),
    parent=None,
    sem="fixture",
    detail=True,
):
    """Create a repeated manufactured part backed by a shared metric mesh."""
    key = (
        tuple(round(float(v), 4) for v in dims),
        material.name_full if material else "",
    )
    mesh = _PART_MESHES.get(key)
    if mesh is None:
        mesh = _cube_mesh("shared_part_" + str(len(_PART_MESHES)).zfill(4), dims)
        if material:
            mesh.materials.append(material)
        mesh["c2w_shared_metric_part"] = True
        _PART_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
    return semantic(obj, sem, detail)


def cyl(
    coll,
    name,
    loc,
    radius,
    depth,
    material,
    vertices=24,
    rot=(0.0, 0.0, 0.0),
    parent=None,
    sem="fixture",
    bevel=0.004,
):
    verts = []
    for z in (-depth / 2, depth / 2):
        verts.extend(
            (
                radius * math.cos(math.tau * i / vertices),
                radius * math.sin(math.tau * i / vertices),
                z,
            )
            for i in range(vertices)
        )
    faces = [tuple(range(vertices - 1, -1, -1)), tuple(range(vertices, vertices * 2))]
    for i in range(vertices):
        j = (i + 1) % vertices
        faces.append((i, j, vertices + j, vertices + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
    for poly in mesh.polygons:
        if len(poly.vertices) == 4:
            poly.use_smooth = True
    if bevel:
        mod = obj.modifiers.new("turned_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 1
        mod.limit_method = "ANGLE"
    return semantic(obj, sem, sem != "structure")


def tube(coll, name, points, radius, material, parent=None, sem="architectural_detail"):
    cu = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 2
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    spl = cu.splines.new("POLY")
    spl.points.add(len(points) - 1)
    for p, co in zip(spl.points, points):
        p.co = (*co, 1.0)
    if material:
        cu.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, cu)
    coll.objects.link(obj)
    if parent:
        obj.parent = parent
    return semantic(obj, sem, True)


def text_obj(
    coll,
    name,
    body,
    loc,
    size,
    material,
    extrude=0.018,
    align="CENTER",
    parent=None,
    xscale=1.0,
    rot=(math.pi / 2, 0.0, 0.0),
    sem="signage",
    bold=True,
):
    cu = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    cu.body = body
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = min(0.006, extrude * 0.22)
    font = FONT_BOLD if bold else FONT_REGULAR
    if Path(font).is_file():
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    if material:
        cu.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, cu)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    obj.scale.x = -xscale
    if parent:
        obj.parent = parent
    return semantic(obj, sem, True)


def _tilted_front_point(center, dx, dz, front_offset, tilt):
    """Map local monitor-face coordinates onto a screen tilted around X."""
    cx, cy, cz = center
    cosine, sine = math.cos(tilt), math.sin(tilt)
    return (
        cx + dx,
        cy + front_offset * cosine - dz * sine,
        cz + front_offset * sine + dz * cosine,
    )


def tilted_ui_box(
    coll,
    name,
    center,
    dx,
    dz,
    dims,
    material,
    tilt,
    parent,
    front_offset=0.070,
    depth=0.006,
    sem="terminal_ui",
):
    loc = _tilted_front_point(center, dx, dz, front_offset, tilt)
    return box(
        coll,
        name,
        loc,
        (dims[0], depth, dims[1]),
        material,
        min(0.004, depth * 0.45),
        (tilt, 0.0, 0.0),
        parent,
        sem,
    )


def tilted_ui_text(
    coll,
    name,
    body,
    center,
    dx,
    dz,
    size,
    material,
    tilt,
    parent,
    xscale=1.0,
    front_offset=0.079,
    align="CENTER",
    sem="terminal_ui",
    bold=True,
):
    loc = _tilted_front_point(center, dx, dz, front_offset, tilt)
    return text_obj(
        coll,
        name,
        body,
        loc,
        size,
        material,
        0.0015,
        align,
        parent,
        xscale,
        (math.pi / 2 + tilt, 0.0, 0.0),
        sem,
        bold,
    )


def qr_code(
    coll,
    name,
    center,
    size,
    y,
    dark_material,
    light_material,
    parent,
    modules=13,
    sem="terminal_ui",
):
    """Build a deterministic physical QR-like matrix with finder patterns."""
    cx, cz = center
    box(
        coll,
        f"{name}:paper",
        (cx, y, cz),
        (size, 0.006, size),
        light_material,
        0.003,
        parent=parent,
        sem=sem,
    )
    cell = size / modules

    def finder(ix, iz, ox, oz):
        dx, dz = ix - ox, iz - oz
        if 0 <= dx < 5 and 0 <= dz < 5:
            return dx in {0, 4} or dz in {0, 4} or (1 < dx < 4 and 1 < dz < 4)
        return False

    for iz in range(modules):
        for ix in range(modules):
            fixed = (
                finder(ix, iz, 0, 0)
                or finder(ix, iz, modules - 5, 0)
                or finder(ix, iz, 0, modules - 5)
            )
            payload = ((ix * 17 + iz * 31 + ix * iz * 3) % 11) < 5
            if not (fixed or payload):
                continue
            x = cx - size / 2 + (ix + 0.5) * cell
            z = cz + size / 2 - (iz + 0.5) * cell
            part_box(
                coll,
                f"{name}:module_{ix:02d}_{iz:02d}",
                (x, y + 0.006, z),
                (cell * 0.82, 0.005, cell * 0.82),
                dark_material,
                parent=parent,
                sem=sem,
            )


def area_light(
    coll,
    name,
    loc,
    energy,
    size,
    color=(1.0, 0.94, 0.84),
    rot=(0.0, 0.0, 0.0),
    parent=None,
):
    data = bpy.data.lights.new(PREFIX + name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size[0]
    data.size_y = size[1]
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
    obj["c2w_semantic"] = "lighting"
    return obj


def camera(name, loc, target, lens=46):
    data = bpy.data.cameras.new(PREFIX + name)
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = False
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    obj["c2w_semantic"] = "camera"
    return obj


def _principled(
    name, color, rough=0.45, metal=0.0, emission=None, emission_strength=0.0, alpha=1.0
):
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            mat.surface_render_method = "DITHERED"
        except (AttributeError, TypeError):
            pass
    return mat


def _powdercoat(name, color_a, color_b, roughness=0.34, scale=120.0):
    """Create a fine, non-metallic polyester powder-coat finish.

    Locker door paint should read as a continuous white coating rather than
    brushed or exposed metal.  A high-frequency, sub-millimetre bump gives the
    close views a believable orange-peel finish without darkening the panels or
    introducing a directional metallic grain.
    """
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 2.2
    noise.inputs["Roughness"].default_value = 0.52
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.030
    bump.inputs["Distance"].default_value = 0.0012
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.30
    links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_finish"] = "fine_nonmetallic_polyester_powdercoat"
    mat["c2w_metallic"] = 0.0
    mat["c2w_bright_white"] = True
    return mat


def _paint(name, color_a, color_b, rough=0.30, metal=0.55, scale=8.0):
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 3.5
    noise.inputs["Roughness"].default_value = 0.62
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.025
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _cardboard(name, color_a, color_b):
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.78
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.14
    bump.inputs["Distance"].default_value = 0.035
    bsdf.inputs["Roughness"].default_value = 0.82
    links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _glass(
    name="architectural_glass",
    tint=(0.18, 0.44, 0.58),
    alpha=0.30,
    transmission=0.72,
    roughness=0.055,
):
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.45
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Alpha"].default_value = alpha
    try:
        mat.surface_render_method = "DITHERED"
        mat.use_transparency_overlap = False
    except (AttributeError, TypeError):
        pass
    return mat


def materials():
    if _MATERIALS:
        return _MATERIALS
    M = _MATERIALS
    M["yellow"] = _paint(
        "food_yellow", (0.90, 0.56, 0.025), (1.0, 0.72, 0.06), 0.28, 0.58, 10
    )
    M["yellow_dark"] = _paint(
        "food_yellow_dark", (0.62, 0.32, 0.015), (0.82, 0.48, 0.02), 0.34, 0.62, 12
    )
    # Delivery5 uses genuinely non-metallic bright-white polyester powder coat.
    # The narrow value range preserves subtle formed-edge highlights while
    # eliminating the grey/brushed-metal read of the preceding revision.
    M["food_door_white"] = _powdercoat(
        "food_door_hygienic_white_powdercoat",
        (0.925, 0.945, 0.958),
        (0.985, 0.990, 0.995),
        0.33,
        135.0,
    )
    M["food_door_white_edge"] = _powdercoat(
        "food_door_white_folded_edge",
        (0.855, 0.875, 0.892),
        (0.945, 0.955, 0.965),
        0.37,
        145.0,
    )
    M["food_cavity_white"] = _principled(
        "food_compartment_hygienic_liner", (0.70, 0.73, 0.72), 0.48, 0.025
    )
    M["food_clear_glass"] = _glass(
        "food_door_clear_tempered_glass", (0.925, 0.970, 1.0), 0.12, 0.96, 0.018
    )
    # Each pane is isolated and non-overlapping, so ordered alpha blending is
    # both stable and markedly cleaner than stochastic dithering in close-ups.
    M["food_clear_glass"].surface_render_method = "BLENDED"
    M["food_clear_glass"].use_transparency_overlap = False
    M["food_glass_print"] = _principled(
        "food_glass_number_black_ceramic_ink", (0.003, 0.004, 0.005), 0.48, 0.0
    )
    M["food_glass_number_keyline"] = _principled(
        "food_glass_number_pale_contrast_keyline", (0.88, 0.90, 0.91), 0.52, 0.0
    )
    M["white_metal"] = _paint(
        "warm_white_metal", (0.76, 0.77, 0.74), (0.94, 0.95, 0.91), 0.34, 0.48, 12
    )
    M["door_warm"] = _paint(
        "locker_door_warm", (0.76, 0.72, 0.67), (0.91, 0.87, 0.79), 0.38, 0.42, 16
    )
    M["green"] = _paint(
        "fengchao_green", (0.29, 0.63, 0.045), (0.50, 0.82, 0.09), 0.33, 0.52, 13
    )
    M["green_alt"] = _paint(
        "fengchao_green_alt", (0.22, 0.50, 0.035), (0.43, 0.73, 0.075), 0.36, 0.48, 15
    )
    M["blue"] = _paint(
        "cainiao_blue", (0.015, 0.34, 0.66), (0.02, 0.56, 0.88), 0.27, 0.40, 10
    )
    M["cyan_emit"] = _principled(
        "cyan_sign", (0.02, 0.64, 0.92), 0.24, 0.12, (0.01, 0.56, 1.0), 1.4
    )
    M["charcoal"] = _paint(
        "charcoal_powdercoat",
        (0.025, 0.032, 0.035),
        (0.075, 0.085, 0.09),
        0.25,
        0.78,
        8,
    )
    M["black"] = _principled("black_hardware", (0.012, 0.015, 0.018), 0.27, 0.76)
    M["rubber"] = _principled("rubber_gasket", (0.008, 0.009, 0.008), 0.72, 0.0)
    M["steel"] = _paint(
        "brushed_stainless", (0.35, 0.38, 0.39), (0.72, 0.75, 0.76), 0.19, 0.92, 24
    )
    M["aluminium"] = _paint(
        "anodized_aluminium", (0.12, 0.14, 0.15), (0.23, 0.26, 0.27), 0.24, 0.88, 18
    )
    M["screen"] = _principled(
        "screen_glass", (0.008, 0.035, 0.055), 0.055, 0.18, (0.015, 0.30, 0.62), 1.8
    )
    M["screen_ui"] = _principled(
        "screen_ui", (0.02, 0.55, 0.88), 0.22, 0.0, (0.01, 0.42, 0.92), 2.8
    )
    M["ui_white"] = _principled(
        "screen_ui_white", (0.82, 0.85, 0.82), 0.30, 0.0, (0.80, 0.86, 0.88), 1.15
    )
    M["ui_pale"] = _principled(
        "screen_ui_pale", (0.55, 0.68, 0.72), 0.34, 0.0, (0.36, 0.52, 0.58), 0.65
    )
    M["ui_navy"] = _principled(
        "screen_ui_navy", (0.012, 0.055, 0.105), 0.23, 0.06, (0.01, 0.10, 0.22), 1.25
    )
    M["ui_teal"] = _principled(
        "screen_ui_teal", (0.015, 0.43, 0.44), 0.28, 0.0, (0.01, 0.48, 0.50), 1.55
    )
    M["ui_yellow"] = _principled(
        "screen_ui_yellow", (0.88, 0.58, 0.025), 0.30, 0.0, (1.0, 0.56, 0.01), 1.0
    )
    M["ui_gray"] = _principled("screen_ui_gray", (0.24, 0.29, 0.31), 0.44, 0.0)
    M["led_green"] = _principled(
        "status_green", (0.01, 0.36, 0.03), 0.18, 0.0, (0.01, 0.95, 0.04), 5.0
    )
    M["led_red"] = _principled(
        "status_red", (0.45, 0.01, 0.005), 0.18, 0.0, (1.0, 0.015, 0.005), 5.0
    )
    M["white_emit"] = _principled(
        "white_emission", (0.82, 0.90, 1.0), 0.16, 0.0, (0.85, 0.94, 1.0), 4.0
    )
    M["white"] = _principled("clean_white", (0.88, 0.90, 0.91), 0.43, 0.08)
    M["offwhite"] = _principled("counter_solid_surface", (0.78, 0.81, 0.82), 0.25, 0.04)
    M["glass"] = _glass()
    M["glass_dark"] = _glass("smoked_glass", (0.035, 0.09, 0.12))
    M["locker_glass"] = _glass(
        "food_locker_tempered_glass", (0.48, 0.58, 0.60), 0.0, 0.98, 0.015
    )
    M["etched_glass"] = _glass(
        "etched_number_glass", (0.72, 0.75, 0.72), 0.48, 0.52, 0.20
    )
    M["compartment_inner"] = _principled(
        "food_compartment_inner", (0.050, 0.060, 0.062), 0.52, 0.46
    )
    M["thermal_box"] = _principled(
        "food_thermal_container", (0.52, 0.54, 0.50), 0.58, 0.08
    )
    M["thermal_white"] = _principled(
        "food_thermal_container_white",
        (0.72, 0.74, 0.69),
        0.54,
        0.06,
        (0.42, 0.44, 0.40),
        0.34,
    )
    M["thermal_yellow"] = _principled(
        "food_thermal_container_yellow",
        (0.82, 0.48, 0.025),
        0.46,
        0.10,
        (0.62, 0.28, 0.008),
        0.38,
    )
    M["cardboard_a"] = _cardboard(
        "corrugated_kraft_a", (0.30, 0.19, 0.095), (0.57, 0.39, 0.20)
    )
    M["cardboard_b"] = _cardboard(
        "corrugated_kraft_b", (0.46, 0.32, 0.16), (0.70, 0.54, 0.31)
    )
    M["cardboard_c"] = _cardboard(
        "corrugated_white", (0.62, 0.60, 0.53), (0.86, 0.84, 0.74)
    )
    M["tape"] = _principled("packing_tape", (0.60, 0.44, 0.20), 0.34, 0.0)
    M["label"] = _principled("shipping_label", (0.89, 0.89, 0.84), 0.72, 0.0)
    M["ink"] = _principled("printed_ink", (0.012, 0.014, 0.015), 0.72, 0.0)
    M["floor"] = _principled("epoxy_floor", (0.63, 0.70, 0.73), 0.31, 0.08)
    M["concrete"] = _cardboard(
        "pavement_concrete", (0.32, 0.34, 0.34), (0.55, 0.57, 0.56)
    )
    M["asphalt"] = _cardboard(
        "access_lane_asphalt", (0.012, 0.016, 0.018), (0.055, 0.064, 0.068)
    )
    M["joint"] = _principled("paving_joint", (0.055, 0.06, 0.06), 0.82, 0.05)
    M["tactile"] = _principled("tactile_yellow", (0.86, 0.54, 0.025), 0.68, 0.10)
    M["red"] = _paint(
        "safety_red", (0.42, 0.012, 0.006), (0.78, 0.035, 0.012), 0.30, 0.55, 10
    )
    return M


def _front_screw(coll, name, x, y, z, mat, parent, radius=0.018):
    return cyl(
        coll,
        name,
        (x, y, z),
        radius,
        0.012,
        mat,
        16,
        (math.pi / 2, 0.0, 0.0),
        parent,
        "locker_hardware",
        0.002,
    )


def _hex_logo(coll, name, loc, radius, depth, mat, parent, rot=(math.pi / 2, 0.0, 0.0)):
    return cyl(coll, name, loc, radius, depth, mat, 6, rot, parent, "signage", 0.002)


# ---------------------------------------------------------------------------
# Simulation-ready articulation helpers


def _axis_vector(axis):
    if isinstance(axis, str):
        axis = {
            "x": (1.0, 0.0, 0.0),
            "y": (0.0, 1.0, 0.0),
            "z": (0.0, 0.0, 1.0),
        }[axis.lower()]
    result = Vector(axis)
    if result.length <= 1e-8:
        raise ValueError("A joint axis must be non-zero")
    return result.normalized()


def _collision_box_mesh(name, center, dimensions):
    """Create a closed metric box whose object origin remains at the joint."""
    cx, cy, cz = (float(value) for value in center)
    hx, hy, hz = (max(float(value), 0.004) * 0.5 for value in dimensions)
    verts = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + ":collision_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh["c2w_collision_geometry"] = "closed_metric_box"
    return mesh


def _activate_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _configure_rigid_body(obj, body_type, mass=1.0, damping=0.24, friction=0.18):
    """Configure physics data after the proxies have been batch-registered."""
    rigid = obj.rigid_body
    if rigid is None:
        raise RuntimeError(f"Rigid-body batch registration failed for {obj.name}")
    rigid.type = body_type
    rigid.collision_shape = "BOX"
    rigid.use_margin = True
    rigid.collision_margin = 0.0025
    rigid.friction = float(friction)
    rigid.restitution = 0.01
    if body_type == "ACTIVE":
        rigid.mass = max(0.05, float(mass))
        rigid.linear_damping = min(max(float(damping), 0.0), 1.0)
        rigid.angular_damping = min(max(float(damping) * 1.25, 0.0), 1.0)
        rigid.use_deactivation = True
        rigid.use_start_deactivated = True
        rigid.kinematic = False
    obj.select_set(False)


def _batch_select(objects):
    bpy.ops.object.select_all(action="DESELECT")
    objects = list(objects)
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]
    return objects


def _ensure_physics_templates():
    """Create one native body and constraint template for off-scene copies."""
    global _PHYSICS_STATE
    if _PHYSICS_STATE:
        return _PHYSICS_STATE
    scene = bpy.context.scene
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    # Avoid an expensive Bullet solve while this generator is only assembling
    # and rendering static validation poses. All bodies/constraints are fully
    # authored; users can enable the world for native Blender simulation.
    world.enabled = False
    existing_bodies = (
        list(world.collection.objects) if world.collection is not None else []
    )
    existing_constraints = (
        list(world.constraints.objects) if world.constraints is not None else []
    )
    body_collection = bpy.data.collections.new(PREFIX + "RIGID_BODY_LINKS")
    body_collection["c2w_role"] = "delivery_rigid_body_links"
    constraint_collection = bpy.data.collections.new(PREFIX + "HINGE_CONSTRAINTS")
    constraint_collection["c2w_role"] = "delivery_hinge_constraints"
    for obj in existing_bodies:
        body_collection.objects.link(obj)
    for obj in existing_constraints:
        constraint_collection.objects.link(obj)

    template_mesh = _collision_box_mesh(
        "rigid_body_template", (0.0, 0.0, 0.0), (0.10, 0.10, 0.10)
    )
    body_template = bpy.data.objects.new(PREFIX + "rigid_body_template", template_mesh)
    body_template.hide_render = True
    scene.collection.objects.link(body_template)
    _activate_only(body_template)
    bpy.ops.rigidbody.object_add(type="ACTIVE")
    constraint_template = bpy.data.objects.new(
        PREFIX + "hinge_constraint_template", None
    )
    scene.collection.objects.link(constraint_template)
    _activate_only(constraint_template)
    bpy.ops.rigidbody.constraint_add()
    _PHYSICS_STATE = {
        "world": world,
        "body_collection": body_collection,
        "constraint_collection": constraint_collection,
        "body_template": body_template,
        "constraint_template": constraint_template,
        "new_bodies": [],
        "new_constraints": [],
    }
    return _PHYSICS_STATE


def _new_rigid_body_object(name, mesh):
    state = _ensure_physics_templates()
    obj = state["body_template"].copy()
    obj.name = PREFIX + name
    obj.data = mesh
    for key in list(obj.keys()):
        del obj[key]
    state["body_collection"].objects.link(obj)
    state["new_bodies"].append(obj)
    return obj


def _new_rigid_constraint_object(name):
    state = _ensure_physics_templates()
    obj = state["constraint_template"].copy()
    obj.name = PREFIX + name
    for key in list(obj.keys()):
        del obj[key]
    state["constraint_collection"].objects.link(obj)
    state["new_constraints"].append(obj)
    return obj


def _batch_finalize_blender_physics(_sim_collections):
    """Attach all preconfigured links/constraints to the scene in two updates."""
    global _PHYSICS_STATE
    if not _PHYSICS_STATE:
        return (0, 0, 0)
    state = _PHYSICS_STATE
    bodies = list(state["new_bodies"])
    constraints = list(state["new_constraints"])
    base_count = sum(
        obj.get("c2w_role") == "simulation_collision_proxy" for obj in bodies
    )
    link_count = sum(obj.get("c2w_role") == "articulated_link" for obj in bodies)
    world = state["world"]
    world.enabled = False
    print("[delivery] physics: assigning body collection", flush=True)
    world.collection = state["body_collection"]
    print("[delivery] physics: assigning constraint collection", flush=True)
    world.constraints = state["constraint_collection"]
    scene = bpy.context.scene
    print("[delivery] physics: linking body collection", flush=True)
    scene.collection.children.link(state["body_collection"])
    print("[delivery] physics: linking constraint collection", flush=True)
    scene.collection.children.link(state["constraint_collection"])
    print("[delivery] physics: collections linked", flush=True)
    scene["c2w_blender_rigidbody_world_authored"] = True
    scene["c2w_blender_rigidbody_world_enabled_for_render"] = False
    # Keep the two inert templates outside the rigid-body collections. Removing
    # them here forces Blender to rebuild the just-authored 115-link graph.
    state["body_template"]["c2w_role"] = "physics_authoring_template"
    state["constraint_template"]["c2w_role"] = "physics_authoring_template"
    state["body_template"].hide_render = True
    state["constraint_template"].hide_render = True
    state["body_template"].select_set(False)
    state["constraint_template"].select_set(False)
    _PHYSICS_STATE = {}
    return base_count, link_count, len(constraints)


def _reparent_keep_world(obj, parent):
    """Reparent without relying on a not-yet-evaluated depsgraph matrix.

    Procedural parts and their new link object are siblings under the same
    asset root.  Blender can return a stale ``matrix_world`` between object
    creation and the next dependency-graph update, which used to collapse the
    rendered door parts onto the hinge origin.  Converting the two sibling
    basis matrices analytically is deterministic and keeps every panel,
    latch, label and moving hinge leaf at its true offset from the pivot.
    """
    old_parent = obj.parent
    common_parent = parent.parent
    if old_parent is common_parent:
        object_in_common = obj.matrix_basis.copy()
        parent_in_common = parent.matrix_basis.copy()
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = parent_in_common.inverted_safe() @ object_in_common
        return
    # Fallback for externally supplied objects whose hierarchy differs from
    # the production builders; force one update before preserving world space.
    bpy.context.view_layer.update()
    matrix_world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_world = matrix_world


def _joint_rotation(axis):
    axis_vec = _axis_vector(axis)
    up = "X" if abs(axis_vec.y) > 0.92 else "Y"
    return axis_vec.to_track_quat("Z", up)


def _make_base_collision(sim_coll, root, asset_name, center, dimensions, front_plane_y):
    mesh = _collision_box_mesh(asset_name + ":base_link", center, dimensions)
    obj = _new_rigid_body_object(asset_name + ":base_link_collision", mesh)
    obj.parent = root
    obj.location = (0.0, 0.0, 0.0)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj["c2w_role"] = "simulation_collision_proxy"
    obj["c2w_link_id"] = asset_name + "_base_link"
    obj["c2w_collision_geometry"] = "procedural_carcass_box"
    obj["c2w_collision_dimensions_m"] = [float(value) for value in dimensions]
    obj["c2w_front_clearance_plane_y"] = float(front_plane_y)
    obj["c2w_procedural_source"] = True
    obj["c2w_requested_rigid_body_type"] = "PASSIVE"
    obj["c2w_owner_simulation_collection"] = sim_coll.name
    _configure_rigid_body(obj, "PASSIVE", friction=0.64)
    return obj


def _make_link_collision(
    sim_coll,
    root,
    name,
    moving_objects,
    pivot,
    collision_center,
    collision_dimensions,
    mass,
    damping,
    friction,
):
    pivot_vec = Vector(pivot)
    relative_center = Vector(collision_center) - pivot_vec
    mesh = _collision_box_mesh(name + ":link", relative_center, collision_dimensions)
    obj = _new_rigid_body_object(name + ":link_collision", mesh)
    obj.parent = root
    obj.location = pivot_vec
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj["c2w_role"] = "articulated_link"
    obj["c2w_link_id"] = name + "_link"
    obj["c2w_joint_id"] = name
    obj["c2w_collision_geometry"] = "procedural_door_envelope_box"
    obj["c2w_collision_dimensions_m"] = [float(value) for value in collision_dimensions]
    obj["c2w_collision_center_local_m"] = [float(value) for value in collision_center]
    obj["c2w_procedural_source"] = True
    obj["c2w_requested_rigid_body_type"] = "ACTIVE"
    obj["c2w_mass_kg"] = float(mass)
    obj["c2w_damping"] = float(damping)
    obj["c2w_friction"] = float(friction)
    obj["c2w_owner_simulation_collection"] = sim_coll.name
    _configure_rigid_body(obj, "ACTIVE", mass, damping, friction)
    for part in moving_objects:
        _reparent_keep_world(part, obj)
        part["c2w_link_id"] = name + "_link"
        part["c2w_joint_id"] = name
        part["c2w_movable"] = True
    return obj


def _make_hinge_constraint(sim_coll, root, base, child, name, pivot, axis, limits):
    obj = _new_rigid_constraint_object(name + ":hinge_constraint")
    obj.parent = root
    obj.location = pivot
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = _joint_rotation(axis)
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = 0.095
    obj["c2w_role"] = "simulation_joint_constraint"
    obj["c2w_joint_id"] = name
    obj["c2w_joint_type"] = "revolute"
    obj["c2w_joint_axis_local"] = [float(value) for value in _axis_vector(axis)]
    obj["c2w_joint_pivot_local_m"] = [float(value) for value in pivot]
    obj["c2w_joint_lower_rad"] = float(limits[0])
    obj["c2w_joint_upper_rad"] = float(limits[1])
    obj["c2w_parent_collision_object"] = base.name
    obj["c2w_child_collision_object"] = child.name
    obj["c2w_owner_simulation_collection"] = sim_coll.name
    obj["c2w_procedural_source"] = True
    constraint = obj.rigid_body_constraint
    if constraint is None:
        raise RuntimeError(f"Missing native rigid-body constraint for {name}")
    constraint.type = "HINGE"
    constraint.object1 = base
    constraint.object2 = child
    constraint.disable_collisions = True
    constraint.use_limit_ang_z = True
    constraint.limit_ang_z_lower = float(limits[0])
    constraint.limit_ang_z_upper = float(limits[1])
    return obj


def _infinigen_articulation_groups():
    """Load the exact joint/metadata nodes published with the cited paper."""
    global _ARTICULATION_NODEGROUPS
    if _ARTICULATION_NODEGROUPS:
        return _ARTICULATION_NODEGROUPS
    infinigen_root = ROOT / "infinigen"
    if str(infinigen_root) not in sys.path:
        sys.path.insert(0, str(infinigen_root))
    mpl_cache = ROOT / ".qa_tmp/matplotlib_delivery"
    mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))
    from infinigen.assets.utils.joints import (  # pylint: disable=import-outside-toplevel
        nodegroup_add_jointed_geometry_metadata,
        nodegroup_hinge_joint,
    )

    _ARTICULATION_NODEGROUPS = {
        "HINGE": nodegroup_hinge_joint(),
        "METADATA": nodegroup_add_jointed_geometry_metadata(),
    }
    return _ARTICULATION_NODEGROUPS


def _collection_info_node(nodes, target_collection):
    node = nodes.new("GeometryNodeCollectionInfo")
    node.transform_space = "RELATIVE"
    node.inputs["Collection"].default_value = target_collection
    if "Separate Children" in node.inputs:
        node.inputs["Separate Children"].default_value = False
    if "Reset Children" in node.inputs:
        node.inputs["Reset Children"].default_value = False
    return node


def _metadata_node(nodes, links, metadata_group, geometry_socket, label):
    node = nodes.new("GeometryNodeGroup")
    node.node_tree = metadata_group
    node.inputs["Label"].default_value = label
    links.new(geometry_socket, node.inputs["Geometry"])
    return node


def _make_native_articulation_carrier(
    sim_coll, root, asset_name, static_collection, joint_records
):
    """Build one native Infinigen-Articulated graph for the complete cabinet.

    The graph carries the actual detailed static and per-door collections, not
    simplified visual stand-ins. Hidden link boxes remain collision proxies for
    Blender physics only; downstream Infinigen exporters query this carrier.
    """
    groups = _infinigen_articulation_groups()
    tree = bpy.data.node_groups.new(
        PREFIX + asset_name + ":native_kinematics", "GeometryNodeTree"
    )
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    nodes, links = tree.nodes, tree.links
    output = nodes.new("NodeGroupOutput")
    base_info = _collection_info_node(nodes, static_collection)
    base_meta = _metadata_node(
        nodes,
        links,
        groups["METADATA"],
        base_info.outputs["Instances"],
        asset_name + "_base_link",
    )
    current_parent = base_meta.outputs["Geometry"]
    for record in joint_records:
        child_info = _collection_info_node(nodes, record["_visual_collection"])
        child_meta = _metadata_node(
            nodes,
            links,
            groups["METADATA"],
            child_info.outputs["Instances"],
            record["child_link"],
        )
        joint = nodes.new("GeometryNodeGroup")
        joint.node_tree = groups["HINGE"]
        joint.inputs["Joint Label"].default_value = record["joint_id"]
        joint.inputs["Position"].default_value = Vector(record["pivot_local_m"])
        joint.inputs["Axis"].default_value = Vector(record["axis_local"])
        # The Blender link already carries the requested display pose; keeping
        # this at zero avoids applying that transform twice during scene use.
        joint.inputs["Value"].default_value = 0.0
        joint.inputs["Min"].default_value = record["limit_lower_rad"]
        joint.inputs["Max"].default_value = record["limit_upper_rad"]
        joint.inputs["Show Joint"].default_value = False
        links.new(current_parent, joint.inputs["Parent"])
        links.new(child_meta.outputs["Geometry"], joint.inputs["Child"])
        current_parent = joint.outputs["Geometry"]
        record["native_nodegroup"] = groups["HINGE"].name
    links.new(current_parent, output.inputs["Geometry"])

    carrier_mesh = bpy.data.meshes.new(PREFIX + asset_name + ":carrier_mesh")
    carrier_mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    carrier = bpy.data.objects.new(
        PREFIX + asset_name + ":native_articulation_carrier", carrier_mesh
    )
    sim_coll.objects.link(carrier)
    carrier.parent = root
    carrier.location = (0.0, 0.0, 0.0)
    carrier.hide_render = True
    carrier.hide_viewport = True
    carrier.display_type = "WIRE"
    modifier = carrier.modifiers.new("Infinigen_Articulated_Kinematic_Tree", "NODES")
    modifier.node_group = tree
    carrier["c2w_role"] = "infinigen_articulated_asset_carrier"
    carrier["c2w_asset_id"] = asset_name
    carrier["c2w_joint_count"] = len(joint_records)
    carrier["c2w_native_hinge_nodegroup"] = groups["HINGE"].name
    carrier["c2w_native_metadata_nodegroup"] = groups["METADATA"].name
    carrier["c2w_direct_method_reuse"] = True
    carrier["c2w_supported_export_formats"] = "URDF,USD,MJCF"
    carrier["c2w_procedural_source"] = True
    for record in joint_records:
        record["native_carrier"] = carrier.name
    return carrier


def _requested_joint_value(joint_values, name, default=0.0):
    joint_values = joint_values or {}
    return float(joint_values.get(name, joint_values.get("*", default)))


def articulate_hinged_door(
    sim_coll,
    root,
    base_collision,
    name,
    visual_collection,
    moving_objects,
    pivot,
    axis,
    limits,
    joint_values,
    collision_center,
    collision_dimensions,
    door_center,
    door_width,
    hinge_side,
    front_plane_y,
    mass,
    damping,
    friction,
):
    """Create one independently movable revolute door link and constraint."""
    moving_objects = list(dict.fromkeys(moving_objects))
    if not moving_objects:
        raise RuntimeError(f"{name} has no moving geometry")
    lower, upper = (float(limits[0]), float(limits[1]))
    if not lower < upper:
        raise ValueError(f"Invalid hinge limits for {name}: {limits}")
    value = min(max(_requested_joint_value(joint_values, name), lower), upper)
    axis_vec = _axis_vector(axis)
    child = _make_link_collision(
        sim_coll,
        root,
        name,
        moving_objects,
        pivot,
        collision_center,
        collision_dimensions,
        mass,
        damping,
        friction,
    )
    child.rotation_mode = "QUATERNION"
    child.rotation_quaternion = Quaternion(axis_vec, value)
    child["c2w_joint_type"] = "revolute"
    child["c2w_joint_value_rad"] = value
    child["c2w_joint_axis_local"] = [float(v) for v in axis_vec]
    child["c2w_joint_pivot_local_m"] = [float(v) for v in pivot]
    child["c2w_joint_limit_lower_rad"] = lower
    child["c2w_joint_limit_upper_rad"] = upper
    child["c2w_mass_kg"] = float(mass)
    child["c2w_damping"] = float(damping)
    child["c2w_friction"] = float(friction)
    child["c2w_hinge_side"] = int(hinge_side)
    child["c2w_door_center_local_m"] = [float(v) for v in door_center]
    child["c2w_door_width_m"] = float(door_width)
    child["c2w_front_clearance_plane_y"] = float(front_plane_y)
    constraint = _make_hinge_constraint(
        sim_coll, root, base_collision, child, name, pivot, axis_vec, (lower, upper)
    )
    visual_collection["c2w_role"] = "articulated_visual_link"
    visual_collection["c2w_link_id"] = name + "_link"
    visual_collection["c2w_joint_id"] = name
    visual_collection["c2w_movable"] = True
    return {
        "joint_id": name,
        "joint_type": "revolute",
        "parent_link": str(base_collision["c2w_link_id"]),
        "child_link": name + "_link",
        "pivot_local_m": [float(v) for v in pivot],
        "axis_local": [float(v) for v in axis_vec],
        "limit_lower_rad": lower,
        "limit_upper_rad": upper,
        "initial_value_rad": value,
        "mass_kg": float(mass),
        "damping": float(damping),
        "friction": float(friction),
        "moving_object_count": len(moving_objects),
        "hinge_side": int(hinge_side),
        "door_center_local_m": [float(v) for v in door_center],
        "door_width_m": float(door_width),
        "collision_dimensions_m": [float(v) for v in collision_dimensions],
        "front_clearance_plane_y": float(front_plane_y),
        "controller": child.name,
        "constraint": constraint.name,
        "visual_collection": visual_collection.name,
        "_child_object": child,
        "_visual_collection": visual_collection,
    }


def _serializable_joint_records(records):
    return [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in records
    ]


def _hinge_component(obj, attachment):
    obj["c2w_physical_hinge_component"] = True
    obj["c2w_hinge_attachment"] = attachment
    return obj


def articulation_render_pose(pose_name):
    food_angle = math.radians(-98.0)
    parcel_angle = math.radians(102.0)
    food = {
        f"food_door_{number:03d}_hinge": food_angle for number in _FOOD_SHOWCASE_DOORS
    }
    parcel = {
        f"parcel_door_{number:03d}_hinge": parcel_angle
        for number in _PARCEL_SHOWCASE_DOORS
    }
    poses = {
        "closed": {},
        "food_open": food,
        "parcel_open": parcel,
        "both_open": {**food, **parcel},
        "food_hinge_open": {"food_door_029_hinge": math.radians(-106.0)},
        "parcel_hinge_open": {"parcel_door_025_hinge": math.radians(106.0)},
    }
    if pose_name not in poses:
        raise KeyError(f"Unknown articulation render pose: {pose_name}")
    return poses[pose_name]


def apply_articulation_pose(joint_values=None, render_control=False):
    """Pose every generated door by joint ID while preserving hinge origins."""
    joint_values = joint_values or {}
    controllers = [
        obj for obj in bpy.data.objects if obj.get("c2w_role") == "articulated_link"
    ]
    for child in controllers:
        joint_id = str(child.get("c2w_joint_id", ""))
        lower = float(child.get("c2w_joint_limit_lower_rad", 0.0))
        upper = float(child.get("c2w_joint_limit_upper_rad", 0.0))
        value = min(max(float(joint_values.get(joint_id, 0.0)), lower), upper)
        pivot = Vector(child.get("c2w_joint_pivot_local_m", child.location))
        axis = _axis_vector(child.get("c2w_joint_axis_local", (0.0, 0.0, 1.0)))
        child.location = pivot
        child.rotation_mode = "QUATERNION"
        child.rotation_quaternion = Quaternion(axis, value)
        child["c2w_joint_value_rad"] = value
        if child.rigid_body is not None:
            child.rigid_body.kinematic = bool(render_control)
    bpy.context.view_layer.update()
    return len(controllers)


# ---------------------------------------------------------------------------
# Asset 1: insulated food-delivery locker wall


def build_food_delivery_locker(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, joint_values=None, defer_physics=False
):
    """Build a ten-column, white-door food locker as a production asset.

    Every service leaf is a real powder-coated frame surrounding clear
    tempered glazing.  The opening exposes a modeled insulated compartment,
    rather than a solid panel masquerading as glass; ceramic numbers sit on
    the outer glass face.  Six stacked rows and one integrated terminal yield
    59 individually numbered doors across ten columns.
    """
    print("[delivery] food locker: detailed geometry", flush=True)
    M = materials()
    asset_coll = collection("FOOD_DELIVERY_LOCKER", parent)
    root = anchor(asset_coll, "food_locker_anchor", origin, yaw)
    static_coll = collection("FOOD_DELIVERY_LOCKER:STATIC", asset_coll)
    sim_coll = collection("FOOD_DELIVERY_LOCKER:SIMULATION", asset_coll)
    coll = static_coll
    asset_coll["c2w_asset_id"] = "delivery.food_locker.articulated.v5"
    asset_coll["c2w_asset_type"] = "food_delivery_locker"
    asset_coll["c2w_independent_builder"] = "build_food_delivery_locker"
    asset_coll["c2w_reference_file"] = "food_locker_user_reference.jpg"
    asset_coll["c2w_reference_geometry_profile"] = (
        "ten_column_yellow_carcass_bright_white_nonmetal_frames_"
        "large_uninterrupted_clear_glass_large_black_numbers_real_hinges"
    )
    asset_coll["c2w_requested_revision"] = OUTPUT_ID
    asset_coll["c2w_articulation_standard"] = ARTICULATION_STANDARD
    asset_coll["c2w_method_reference"] = METHOD_REFERENCE_URL
    asset_coll["c2w_simulation_collection"] = sim_coll.name

    bay_w, bay_count, row_count = 0.56, 10, 6
    grid_w = bay_w * bay_count
    width, depth, height = grid_w + 0.42, 0.90, 2.72
    grid_left = -grid_w / 2
    row_h, row_gap, row_start = 0.355, 0.030, 0.255
    row_centers = tuple(
        row_start + row_h / 2 + row * (row_h + row_gap) for row in range(row_count)
    )
    door_outer = (bay_w - 0.105, row_h - 0.052)
    # The uninterrupted glazing now occupies roughly 80% of each leaf's width
    # and 77% of its height.  A 32--45 mm formed white perimeter remains for a
    # structurally credible door while the interior cavity reads clearly.
    glass_opening = (0.365, 0.232)
    base_collision = _make_base_collision(
        sim_coll, root, "food_locker", (0.0, -0.35, 1.43), (width, 0.90, 2.50), 0.050
    )
    joint_records = []

    # A back skin, structural rails and bay partitions form a genuinely hollow
    # carcass.  This is crucial for the clear door glazing: the viewer sees
    # compartment depth and contents, not the front face of one solid block.
    box(
        coll,
        "food:rear_back_skin",
        (0, -0.805, 1.40),
        (width, 0.060, 2.50),
        M["yellow_dark"],
        0.018,
        parent=root,
        sem="locker_structure",
    )
    for rail_index, rail_z in enumerate((0.315, 1.40, 2.585)):
        box(
            coll,
            f"food:rear_structural_rail_{rail_index}",
            (0, -0.665, rail_z),
            (width - 0.24, 0.235, 0.095),
            M["yellow_dark"],
            0.012,
            parent=root,
            sem="locker_structure",
        )
    box(
        coll,
        "food:lower_structural_plinth",
        (0, -0.34, 0.245),
        (width + 0.015, 0.88, 0.19),
        M["yellow_dark"],
        0.028,
        parent=root,
        sem="locker_structure",
    )
    box(
        coll,
        "food:front_yellow_toe_skin",
        (0, 0.015, 0.245),
        (grid_w + 0.18, 0.055, 0.19),
        M["yellow"],
        0.020,
        parent=root,
        sem="locker_structure",
    )
    box(
        coll,
        "food:roof_skin",
        (0, -0.34, 2.665),
        (width + 0.035, 0.90, 0.105),
        M["yellow"],
        0.030,
        parent=root,
        sem="locker_structure",
    )
    box(
        coll,
        "food:rear_service_spine",
        (0, -0.846, 1.43),
        (width - 0.28, 0.030, 2.38),
        M["yellow_dark"],
        0.006,
        parent=root,
        sem="architectural_detail",
    )

    # Rolled end cheeks, folded returns and ventilation slots preserve a
    # believable fabricated-sheet enclosure at both ends of the 6 m bank.
    for side in (-1, 1):
        sx = side * (width / 2 - 0.085)
        box(
            coll,
            f"food:end_shroud_{side}",
            (sx, -0.335, 1.42),
            (0.205, 0.88, 2.50),
            M["yellow"],
            0.060,
            parent=root,
            sem="locker_structure",
        )
        box(
            coll,
            f"food:end_shroud_{side}:front_return",
            (sx - side * 0.052, 0.055, 1.43),
            (0.095, 0.080, 2.42),
            M["yellow"],
            0.030,
            parent=root,
            sem="architectural_detail",
        )
        for slot in range(9):
            box(
                coll,
                f"food:end_shroud_{side}:rear_vent_{slot}",
                (sx + side * 0.108, -0.675 + slot * 0.068, 1.65),
                (0.012, 0.042, 0.150),
                M["black"],
                0.004,
                parent=root,
                sem="architectural_detail",
            )

    # Every column has a full-depth insulated partition, a rear liner and seven
    # shelf plates.  Narrow yellow front mullions remain separate folded parts.
    for edge in range(bay_count + 1):
        x = grid_left + edge * bay_w
        box(
            coll,
            f"food:bay_partition_{edge}",
            (x, -0.350, 1.43),
            (0.048, 0.760, 2.42),
            M["yellow_dark"],
            0.009,
            parent=root,
            sem="locker_structure",
        )
        box(
            coll,
            f"food:vertical_mullion_{edge}",
            (x, 0.018, 1.43),
            (0.050, 0.096, 2.42),
            M["yellow"],
            0.011,
            parent=root,
            sem="architectural_detail",
        )
    for bay in range(bay_count):
        cx = grid_left + (bay + 0.5) * bay_w
        box(
            coll,
            f"food:bay_{bay}:insulated_back",
            (cx, -0.735, 1.43),
            (bay_w - 0.065, 0.032, 2.40),
            M["food_cavity_white"],
            0.008,
            parent=root,
            sem="locker_structure",
        )
        for seam in range(row_count + 1):
            z = row_start + seam * (row_h + row_gap) - row_gap / 2
            box(
                coll,
                f"food:bay_{bay}:insulated_shelf_{seam}",
                (cx, -0.295, z),
                (bay_w - 0.075, 0.720, 0.026),
                M["food_cavity_white"],
                0.006,
                parent=root,
                sem="locker_structure",
            )
            part_box(
                coll,
                f"food:bay_{bay}:front_shadow_joint_{seam}",
                (cx, 0.037, z),
                (bay_w - 0.080, 0.028, 0.018),
                M["rubber"],
                parent=root,
                sem="locker_hardware",
            )

    # The frontal camera reverses world X.  Bay 8 therefore reads as the second
    # visible column, retaining an intuitive terminal/door numbering sequence.
    terminal_slot = (bay_count - 2, row_count - 1)
    door_count = 0
    clear_glass_count = 0
    visible_content_count = 0
    for bay in range(bay_count):
        cx = grid_left + (bay + 0.5) * bay_w
        for row_idx, cz in enumerate(row_centers):
            if (bay, row_idx) == terminal_slot:
                continue
            visual_bay = bay_count - 1 - bay
            compartment_number = 2 + visual_bay * row_count + (row_count - 1 - row_idx)
            key = f"food:door_{compartment_number:03d}"
            door_coll = collection(
                f"FOOD_DOOR_LINK_{compartment_number:03d}", asset_coll
            )
            moving_parts = []

            # Recessed cavity: rear panel, two side liners, threshold and vent
            # slots.  Their depth remains visible through the transparent pane.
            box(
                coll,
                f"{key}:cavity_back",
                (cx, -0.515, cz),
                (glass_opening[0] + 0.045, 0.026, glass_opening[1] + 0.048),
                M["compartment_inner"],
                0.010,
                parent=root,
                sem="locker_hardware",
            )
            for side in (-1, 1):
                box(
                    coll,
                    f"{key}:liner_side_{side}",
                    (cx + side * (glass_opening[0] / 2 + 0.018), -0.255, cz),
                    (0.025, 0.500, glass_opening[1] + 0.060),
                    M["food_cavity_white"],
                    0.005,
                    parent=root,
                    sem="locker_hardware",
                )
            box(
                coll,
                f"{key}:threshold",
                (cx, -0.245, cz - glass_opening[1] / 2 - 0.010),
                (glass_opening[0] + 0.060, 0.520, 0.024),
                M["food_cavity_white"],
                0.006,
                parent=root,
                sem="locker_hardware",
            )
            for vent in range(3):
                part_box(
                    coll,
                    f"{key}:rear_air_slot_{vent}",
                    (cx - 0.060 + vent * 0.060, -0.498, cz + 0.057),
                    (0.038, 0.006, 0.009),
                    M["rubber"],
                    parent=root,
                    sem="locker_hardware",
                )

            # A varied subset contains a fully modeled insulated delivery bag,
            # making the clear glazing visually and geometrically unambiguous.
            if compartment_number % 7 in (0, 2):
                content_mat = (
                    M["thermal_yellow"]
                    if compartment_number % 2
                    else M["thermal_white"]
                )
                bag_x = cx + (-0.025 if compartment_number % 3 else 0.025)
                box(
                    coll,
                    f"{key}:thermal_bag_body",
                    (bag_x, -0.335, cz - 0.020),
                    (0.205, 0.170, 0.120),
                    content_mat,
                    0.018,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )
                box(
                    coll,
                    f"{key}:thermal_bag_lid",
                    (bag_x, -0.335, cz + 0.046),
                    (0.218, 0.180, 0.028),
                    content_mat,
                    0.012,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )
                box(
                    coll,
                    f"{key}:thermal_bag_label",
                    (bag_x, -0.244, cz - 0.020),
                    (0.082, 0.006, 0.046),
                    M["ui_white"],
                    0.004,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )
                tube(
                    coll,
                    f"{key}:thermal_bag_handle",
                    (
                        (bag_x - 0.060, -0.247, cz + 0.050),
                        (bag_x - 0.060, -0.247, cz + 0.090),
                        (bag_x + 0.060, -0.247, cz + 0.090),
                        (bag_x + 0.060, -0.247, cz + 0.050),
                    ),
                    0.007,
                    M["rubber"],
                    root,
                    "locker_contents",
                )
                visible_content_count += 1

            # One watertight bright-white powder-coated ring is the actual door leaf.
            # A separate elastomeric ring seats it against the insulated bay.
            front_frame(
                coll,
                f"{key}:perimeter_gasket",
                (cx, 0.052, cz),
                (door_outer[0] + 0.020, door_outer[1] + 0.020),
                (glass_opening[0] + 0.028, glass_opening[1] + 0.028),
                0.026,
                M["rubber"],
                0.008,
                root,
                "locker_hardware",
            )
            door = front_frame(
                door_coll,
                f"{key}:white_powdercoat_door_frame",
                (cx, 0.086, cz),
                door_outer,
                glass_opening,
                0.044,
                M["food_door_white"],
                0.012,
                root,
                "food_locker_door",
            )
            moving_parts.append(door)
            door["c2w_compartment_number"] = compartment_number
            door["c2w_door_independent"] = True
            door[
                "c2w_reference_door_style"
            ] = "bright_white_nonmetal_powdercoat_frame_with_large_clear_center_glass"
            door["c2w_white_door_leaf"] = True
            door["c2w_bright_white_nonmetal_finish"] = True
            door["c2w_door_metallic"] = 0.0
            door["c2w_true_center_opening"] = True

            window = box(
                door_coll,
                f"{key}:clear_tempered_center_glass",
                (cx, 0.114, cz),
                (glass_opening[0] - 0.006, 0.008, glass_opening[1] - 0.006),
                M["food_clear_glass"],
                0.0035,
                parent=root,
                sem="food_locker_window",
            )
            moving_parts.append(window)
            window["c2w_clear_tempered_glass"] = True
            window["c2w_transmission_weight"] = 0.96
            window["c2w_reference_window_proportion"] = "large_clear_center_inset"
            window["c2w_uninterrupted_center_glazing"] = True
            window["c2w_glass_width_ratio"] = glass_opening[0] / door_outer[0]
            window["c2w_glass_height_ratio"] = glass_opening[1] / door_outer[1]

            # A narrow pale ceramic keyline guarantees contrast against both the
            # charcoal cavity back and light compartment liner.  The larger,
            # frontmost glyph remains an opaque-black marking fired directly
            # onto the glass; this reverses the prior white-fill treatment.
            keyline = text_obj(
                door_coll,
                f"{key}:glass_number_contrast_keyline",
                str(compartment_number),
                (cx, 0.124, cz - 0.010),
                0.172,
                M["food_glass_number_keyline"],
                0.0015,
                parent=root,
                xscale=0.78,
                bold=True,
                sem="locker_hardware",
            )
            moving_parts.append(keyline)
            keyline["c2w_black_number_contrast_keyline"] = True
            number = text_obj(
                door_coll,
                f"{key}:glass_number_black",
                str(compartment_number),
                (cx, 0.128, cz - 0.010),
                0.158,
                M["food_glass_print"],
                0.0018,
                parent=root,
                xscale=0.78,
                bold=True,
                sem="locker_hardware",
            )
            moving_parts.append(number)
            number["c2w_legible_compartment_number"] = True
            number["c2w_number_printed_on_glass"] = True
            number["c2w_black_ceramic_ink"] = True
            number["c2w_nominal_font_size_m"] = 0.158

            # Compact hardware stays on the white perimeter rails.  The two
            # hinges are complete interleaved barrel assemblies with a fixed
            # carcass leaf, moving door leaf, three knuckles and a through-pin.
            hardware_x = cx - door_outer[0] / 2 + 0.021
            moving_parts.append(
                box(
                    door_coll,
                    f"{key}:latch_housing",
                    (hardware_x, 0.119, cz - 0.006),
                    (0.028, 0.026, 0.078),
                    M["food_door_white_edge"],
                    0.007,
                    parent=root,
                    sem="locker_hardware",
                )
            )
            moving_parts.append(
                box(
                    door_coll,
                    f"{key}:latch_rocker",
                    (hardware_x, 0.137, cz - 0.010),
                    (0.014, 0.010, 0.042),
                    M["black"],
                    0.004,
                    parent=root,
                    sem="locker_hardware",
                )
            )
            moving_parts.append(
                _front_screw(
                    door_coll,
                    f"{key}:status_led",
                    hardware_x,
                    0.145,
                    cz + 0.047,
                    M["led_green"] if compartment_number % 9 else M["led_red"],
                    root,
                    0.0055,
                )
            )
            hinge_x = cx + door_outer[0] / 2 + 0.006
            for hinge_idx, hz in enumerate((-0.095, 0.095)):
                hinge_z = cz + hz
                _hinge_component(
                    cyl(
                        coll,
                        f"{key}:hinge_{hinge_idx}:through_pin",
                        (hinge_x, 0.113, hinge_z),
                        0.0038,
                        0.074,
                        M["steel"],
                        20,
                        parent=root,
                        sem="locker_hardware",
                        bevel=0.0012,
                    ),
                    "fixed_pin",
                )
                _hinge_component(
                    box(
                        coll,
                        f"{key}:hinge_{hinge_idx}:carcass_leaf",
                        (hinge_x + 0.020, 0.101, hinge_z),
                        (0.042, 0.016, 0.062),
                        M["food_door_white_edge"],
                        0.004,
                        parent=root,
                        sem="locker_hardware",
                    ),
                    "fixed_leaf",
                )
                for knuckle_idx, offset in enumerate((-0.025, 0.025)):
                    _hinge_component(
                        cyl(
                            coll,
                            f"{key}:hinge_{hinge_idx}:fixed_knuckle_{knuckle_idx}",
                            (hinge_x, 0.113, hinge_z + offset),
                            0.0092,
                            0.021,
                            M["food_door_white_edge"],
                            24,
                            parent=root,
                            sem="locker_hardware",
                            bevel=0.0015,
                        ),
                        "fixed_knuckle",
                    )
                moving_leaf = _hinge_component(
                    box(
                        door_coll,
                        f"{key}:hinge_{hinge_idx}:door_leaf",
                        (hinge_x - 0.026, 0.115, hinge_z),
                        (0.052, 0.014, 0.050),
                        M["food_door_white"],
                        0.004,
                        parent=root,
                        sem="locker_hardware",
                    ),
                    "moving_leaf",
                )
                moving_knuckle = _hinge_component(
                    cyl(
                        door_coll,
                        f"{key}:hinge_{hinge_idx}:moving_knuckle",
                        (hinge_x, 0.113, hinge_z),
                        0.0092,
                        0.027,
                        M["food_door_white_edge"],
                        24,
                        parent=root,
                        sem="locker_hardware",
                        bevel=0.0015,
                    ),
                    "moving_knuckle",
                )
                moving_parts.extend((moving_leaf, moving_knuckle))
            for sx, sz in (
                (-0.210, -0.137),
                (-0.210, 0.137),
                (0.210, -0.137),
                (0.210, 0.137),
            ):
                moving_parts.append(
                    _front_screw(
                        door_coll,
                        f"{key}:fastener_{sx:+.3f}_{sz:+.3f}",
                        cx + sx,
                        0.119,
                        cz + sz,
                        M["food_door_white_edge"],
                        root,
                        0.0038,
                    )
                )
            joint_name = f"food_door_{compartment_number:03d}_hinge"
            joint_records.append(
                articulate_hinged_door(
                    sim_coll,
                    root,
                    base_collision,
                    joint_name,
                    door_coll,
                    moving_parts,
                    (hinge_x, 0.113, cz),
                    (0.0, 0.0, 1.0),
                    (math.radians(-110.0), 0.0),
                    joint_values,
                    (cx, 0.096, cz),
                    (door_outer[0], 0.076, door_outer[1]),
                    (cx, 0.096, cz),
                    door_outer[0],
                    1,
                    0.050,
                    1.85,
                    0.30,
                    0.16,
                )
            )
            door_count += 1
            clear_glass_count += 1

    # The second visible column's top service bay contains a real operating
    # terminal in a white enclosure, consistent with the new door family.
    tx = grid_left + (terminal_slot[0] + 0.5) * bay_w
    terminal_z = row_centers[terminal_slot[1]]
    front_frame(
        coll,
        "food:terminal:perimeter_gasket",
        (tx, 0.052, terminal_z),
        (door_outer[0] + 0.020, door_outer[1] + 0.020),
        (0.365, 0.218),
        0.026,
        M["rubber"],
        0.008,
        root,
        "locker_hardware",
    )
    box(
        coll,
        "food:terminal:white_service_panel",
        (tx, 0.082, terminal_z),
        (door_outer[0], 0.044, door_outer[1]),
        M["food_door_white"],
        0.018,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "food:terminal:screen_recess",
        (tx - 0.012, 0.116, terminal_z + 0.012),
        (0.385, 0.030, 0.236),
        M["food_door_white_edge"],
        0.026,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "food:terminal:screen_bezel",
        (tx - 0.012, 0.139, terminal_z + 0.012),
        (0.357, 0.024, 0.208),
        M["black"],
        0.021,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "food:terminal:screen_glass",
        (tx - 0.012, 0.157, terminal_z + 0.012),
        (0.327, 0.011, 0.178),
        M["ui_navy"],
        0.015,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "food:terminal:ui_header",
        (tx - 0.012, 0.166, terminal_z + 0.072),
        (0.302, 0.006, 0.041),
        M["ui_teal"],
        0.005,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "food:terminal:ui_title",
        "PICKUP",
        (tx - 0.060, 0.173, terminal_z + 0.072),
        0.031,
        M["white_emit"],
        0.0013,
        parent=root,
        xscale=0.95,
        sem="terminal_ui",
    )
    box(
        coll,
        "food:terminal:ui_code_field",
        (tx - 0.067, 0.168, terminal_z - 0.008),
        (0.165, 0.006, 0.056),
        M["ui_white"],
        0.006,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "food:terminal:ui_code_hint",
        "CODE",
        (tx - 0.067, 0.174, terminal_z - 0.008),
        0.020,
        M["ui_gray"],
        0.001,
        parent=root,
        xscale=0.92,
        bold=False,
        sem="terminal_ui",
    )
    qr_code(
        coll,
        "food:terminal:ui_qr",
        (tx + 0.105, terminal_z - 0.015),
        0.074,
        0.169,
        M["ink"],
        M["ui_white"],
        root,
        modules=9,
    )
    _front_screw(
        coll,
        "food:terminal:camera",
        tx - 0.012,
        0.174,
        terminal_z + 0.121,
        M["glass_dark"],
        root,
        0.007,
    )
    _front_screw(
        coll,
        "food:terminal:status_led",
        tx + 0.205,
        0.164,
        terminal_z + 0.065,
        M["led_green"],
        root,
        0.007,
    )
    box(
        coll,
        "food:terminal:service_key",
        (tx + 0.195, 0.151, terminal_z - 0.032),
        (0.045, 0.016, 0.075),
        M["steel"],
        0.009,
        parent=root,
        sem="workstation",
    )
    for row in range(3):
        for col in range(4):
            part_box(
                coll,
                f"food:terminal:keypad_{row}_{col}",
                (tx - 0.112 + col * 0.037, 0.175, terminal_z - 0.064 + row * 0.031),
                (0.031, 0.006, 0.020),
                M["ui_yellow"] if (row, col) == (0, 3) else M["ui_pale"],
                parent=root,
                sem="terminal_ui",
            )
    for i in range(6):
        _front_screw(
            coll,
            f"food:terminal:speaker_{i}",
            tx + 0.130 + (i % 3) * 0.020,
            0.166,
            terminal_z - 0.088 + (i // 3) * 0.022,
            M["black"],
            root,
            0.0038,
        )
    for sx, sz in ((-0.218, -0.130), (-0.218, 0.130), (0.218, -0.130), (0.218, 0.130)):
        _front_screw(
            coll,
            f"food:terminal:panel_fastener_{sx:+.3f}_{sz:+.3f}",
            tx + sx,
            0.153,
            terminal_z + sz,
            M["steel"],
            root,
            0.0045,
        )

    # Six industrial swivel casters distribute the doubled cabinet width; four
    # independent leveling feet stabilize the bank.  Forks, axles, bearing
    # rings and tread remain explicitly modeled rather than implied cylinders.
    caster_xs = (-2.46, -1.48, -0.50, 0.50, 1.48, 2.46)
    for i, x in enumerate(caster_xs):
        box(
            coll,
            f"food:caster_{i}:mount_plate",
            (x, -0.28, 0.145),
            (0.190, 0.160, 0.026),
            M["steel"],
            0.010,
            parent=root,
            sem="locker_hardware",
        )
        cyl(
            coll,
            f"food:caster_{i}:swivel_bearing",
            (x, -0.28, 0.118),
            0.055,
            0.038,
            M["steel"],
            24,
            parent=root,
            sem="locker_hardware",
            bevel=0.003,
        )
        cyl(
            coll,
            f"food:caster_{i}:stem",
            (x, -0.28, 0.155),
            0.022,
            0.085,
            M["steel"],
            18,
            parent=root,
            sem="locker_hardware",
            bevel=0.002,
        )
        for side in (-1, 1):
            box(
                coll,
                f"food:caster_{i}:fork_{side}",
                (x, -0.28 + side * 0.052, 0.077),
                (0.038, 0.026, 0.110),
                M["steel"],
                0.008,
                (0, math.radians(-8 * side), 0),
                root,
                "locker_hardware",
            )
        cyl(
            coll,
            f"food:caster_{i}:wheel",
            (x, -0.28, 0.066),
            0.063,
            0.074,
            M["rubber"],
            28,
            (math.pi / 2, 0, 0),
            root,
            "locker_hardware",
            0.004,
        )
        cyl(
            coll,
            f"food:caster_{i}:axle",
            (x, -0.28, 0.066),
            0.014,
            0.104,
            M["steel"],
            18,
            (math.pi / 2, 0, 0),
            root,
            "locker_hardware",
            0.002,
        )
    leveling_xs = (-2.78, -0.93, 0.93, 2.78)
    for i, x in enumerate(leveling_xs):
        cyl(
            coll,
            f"food:leveling_foot_{i}:stem",
            (x, -0.18, 0.090),
            0.023,
            0.150,
            M["steel"],
            18,
            parent=root,
            sem="locker_hardware",
            bevel=0.002,
        )
        cyl(
            coll,
            f"food:leveling_foot_{i}:pad",
            (x, -0.18, 0.027),
            0.064,
            0.032,
            M["rubber"],
            24,
            parent=root,
            sem="locker_hardware",
            bevel=0.004,
        )

    if defer_physics:
        physics_counts = (1, len(joint_records), len(joint_records))
        asset_coll["c2w_physics_registration_deferred"] = True
    else:
        print("[delivery] food locker: batch physics", flush=True)
        physics_counts = _batch_finalize_blender_physics(sim_coll)
        asset_coll["c2w_physics_registration_deferred"] = False
    print("[delivery] food locker: native articulation graph", flush=True)
    carrier = _make_native_articulation_carrier(
        sim_coll, root, "food_locker", static_coll, joint_records
    )
    serialized_joints = _serializable_joint_records(joint_records)
    root["c2w_kinematic_tree"] = json.dumps(serialized_joints, sort_keys=True)
    root["c2w_articulation_standard"] = ARTICULATION_STANDARD
    root["c2w_native_articulation_carrier"] = carrier.name
    root["c2w_revolute_joint_count"] = len(joint_records)
    asset_coll["c2w_column_count"] = bay_count
    asset_coll["c2w_row_count"] = row_count
    asset_coll["c2w_compartment_count"] = door_count
    asset_coll["c2w_terminal_count"] = 1
    asset_coll["c2w_white_powdercoat_door_count"] = door_count
    asset_coll["c2w_clear_tempered_glass_count"] = clear_glass_count
    asset_coll["c2w_glass_number_count"] = door_count
    asset_coll["c2w_large_glazing_width_ratio"] = glass_opening[0] / door_outer[0]
    asset_coll["c2w_large_glazing_height_ratio"] = glass_opening[1] / door_outer[1]
    asset_coll["c2w_vertical_glass_bar_count"] = 0
    asset_coll["c2w_number_finish"] = "large_opaque_black_ceramic_ink"
    asset_coll["c2w_visible_insulated_bag_count"] = visible_content_count
    asset_coll["c2w_caster_count"] = len(caster_xs)
    asset_coll["c2w_leveling_foot_count"] = len(leveling_xs)
    asset_coll["c2w_terminal_detail_level"] = "modeled_operational_interface"
    asset_coll["c2w_revolute_joint_count"] = len(joint_records)
    asset_coll["c2w_articulated_visual_link_count"] = len(joint_records)
    asset_coll["c2w_blender_physics_batch_counts"] = list(physics_counts)
    print("[delivery] food locker: complete", flush=True)
    return asset_coll


# ---------------------------------------------------------------------------
# Asset 2: Fengchao-style parcel locker and canopy


def build_parcel_locker(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, joint_values=None, defer_physics=False
):
    """Build the long lime-green parcel locker with a detailed steel canopy."""
    print("[delivery] parcel locker: detailed geometry", flush=True)
    M = materials()
    asset_coll = collection("PARCEL_LOCKER", parent)
    root = anchor(asset_coll, "parcel_locker_anchor", origin, yaw)
    static_coll = collection("PARCEL_LOCKER:STATIC", asset_coll)
    sim_coll = collection("PARCEL_LOCKER:SIMULATION", asset_coll)
    coll = static_coll
    asset_coll["c2w_asset_id"] = "delivery.parcel_locker.fengchao.articulated.v2"
    asset_coll["c2w_asset_type"] = "parcel_locker"
    asset_coll["c2w_independent_builder"] = "build_parcel_locker"
    asset_coll["c2w_reference_file"] = "parcel_locker.jpg"
    asset_coll["c2w_articulation_standard"] = ARTICULATION_STANDARD
    asset_coll["c2w_method_reference"] = METHOD_REFERENCE_URL
    asset_coll["c2w_simulation_collection"] = sim_coll.name

    width, depth = 11.45, 0.92
    # The previous monolithic block is replaced by a fabricated hollow shell;
    # opening a door now reveals a real compartment instead of a green wall.
    box(
        coll,
        "parcel:rear_back_skin",
        (0, -0.845, 1.20),
        (width, 0.055, 2.30),
        M["green_alt"],
        0.014,
        parent=root,
        sem="locker_structure",
    )
    box(
        coll,
        "parcel:base_rail",
        (0, -0.42, 0.13),
        (width + 0.08, 0.90, 0.22),
        M["charcoal"],
        0.012,
        parent=root,
        sem="locker_structure",
    )
    box(
        coll,
        "parcel:top_rail",
        (0, -0.43, 2.34),
        (width + 0.10, 0.94, 0.15),
        M["charcoal"],
        0.014,
        parent=root,
        sem="locker_structure",
    )
    for side in (-1, 1):
        box(
            coll,
            f"parcel:end_shroud_{side}",
            (side * (width / 2 - 0.075), -0.42, 1.20),
            (0.150, 0.88, 2.30),
            M["green_alt"],
            0.028,
            parent=root,
            sem="locker_structure",
        )

    bay_w = 1.19
    bay_count = 9
    total_grid = bay_w * bay_count
    grid_left = -total_grid / 2
    row_h = (0.25, 0.25, 0.26, 0.25, 0.26, 0.25, 0.26)
    z_cursor = 0.285
    row_centers = []
    for h in row_h:
        row_centers.append(z_cursor + h / 2)
        z_cursor += h + 0.033

    base_collision = _make_base_collision(
        sim_coll, root, "parcel_locker", (0.0, -0.42, 1.20), (width, 0.92, 2.30), 0.030
    )
    joint_records = []
    for edge in range(bay_count + 1):
        x = grid_left + edge * bay_w
        box(
            coll,
            f"parcel:grid_partition_{edge}",
            (x, -0.41, 1.20),
            (0.052, 0.78, 2.04),
            M["green_alt"],
            0.007,
            parent=root,
            sem="locker_structure",
        )

    door_index = 1
    for bay in range(bay_count):
        bx = grid_left + (bay + 0.5) * bay_w
        for edge in (-1, 1):
            box(
                coll,
                f"parcel:bay_{bay}:jamb_{edge}",
                (bx + edge * (bay_w / 2 - 0.020), 0.025, 1.20),
                (0.044, 0.092, 1.95),
                M["green_alt"],
                0.007,
                parent=root,
                sem="architectural_detail",
            )
        if bay == 4:
            continue
        for row, (cz, rh) in enumerate(zip(row_centers, row_h)):
            key = f"parcel:door_{door_index:03d}"
            door_coll = collection(f"PARCEL_DOOR_LINK_{door_index:03d}", asset_coll)
            moving_parts = []
            door_w, door_h = bay_w - 0.105, rh - 0.038
            opening_w, opening_h = door_w - 0.090, door_h - 0.060

            # A powder-coated inner liner, threshold and deep back sheet are
            # visible whenever the solid service leaf rotates out of the way.
            box(
                coll,
                f"{key}:cavity_back",
                (bx, -0.700, cz),
                (door_w - 0.070, 0.026, door_h - 0.026),
                M["compartment_inner"],
                0.007,
                parent=root,
                sem="locker_hardware",
            )
            for side in (-1, 1):
                box(
                    coll,
                    f"{key}:cavity_side_{side}",
                    (bx + side * (door_w / 2 - 0.025), -0.345, cz),
                    (0.032, 0.660, door_h + 0.018),
                    M["green_alt"],
                    0.005,
                    parent=root,
                    sem="locker_hardware",
                )
            box(
                coll,
                f"{key}:cavity_floor",
                (bx, -0.345, cz - door_h / 2 - 0.010),
                (door_w - 0.045, 0.660, 0.022),
                M["steel"],
                0.004,
                parent=root,
                sem="locker_hardware",
            )
            box(
                coll,
                f"{key}:cavity_ceiling",
                (bx, -0.345, cz + door_h / 2 + 0.010),
                (door_w - 0.045, 0.660, 0.022),
                M["green_alt"],
                0.004,
                parent=root,
                sem="locker_hardware",
            )
            for vent in range(5):
                part_box(
                    coll,
                    f"{key}:rear_vent_{vent}",
                    (bx - 0.120 + vent * 0.060, -0.684, cz + door_h * 0.20),
                    (0.036, 0.006, 0.008),
                    M["black"],
                    parent=root,
                    sem="locker_hardware",
                )

            # Several compartments contain supported parcels; all showcase
            # doors intentionally reveal non-empty, label-rich interiors.
            if door_index % 8 in (0, 1, 4) or door_index in _PARCEL_SHOWCASE_DOORS:
                package_h = min(0.105, door_h * 0.46)
                package_w = 0.32 + 0.055 * (door_index % 4)
                package_y = -0.275
                package_z = cz - door_h / 2 + 0.012 + package_h / 2
                package_mat = (M["cardboard_a"], M["cardboard_b"], M["cardboard_c"])[
                    door_index % 3
                ]
                box(
                    coll,
                    f"{key}:stored_parcel",
                    (bx, package_y, package_z),
                    (package_w, 0.285, package_h),
                    package_mat,
                    0.010,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )
                box(
                    coll,
                    f"{key}:stored_parcel_tape",
                    (bx, package_y + 0.147, package_z),
                    (0.042, 0.006, package_h * 0.78),
                    M["tape"],
                    0.002,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )
                box(
                    coll,
                    f"{key}:stored_parcel_label",
                    (bx + package_w * 0.19, package_y + 0.151, package_z),
                    (0.105, 0.005, package_h * 0.55),
                    M["label"],
                    0.002,
                    parent=root,
                    sem="locker_contents",
                    detail=True,
                )

            front_frame(
                coll,
                f"{key}:compression_gasket",
                (bx, 0.036, cz),
                (bay_w - 0.075, rh - 0.010),
                (opening_w, opening_h),
                0.030,
                M["rubber"],
                0.007,
                root,
                "locker_hardware",
            )
            door_mat = M["green"] if (bay + row) % 3 else M["green_alt"]
            door = box(
                door_coll,
                f"{key}:panel",
                (bx, 0.067, cz),
                (door_w, 0.034, door_h),
                door_mat,
                0.010,
                parent=root,
                sem="parcel_locker_door",
            )
            moving_parts.append(door)
            door["c2w_compartment_number"] = door_index
            door["c2w_door_independent"] = True
            door["c2w_true_compartment_opening"] = True

            # Surface-mount steel hinges use a left jamb pivot and interleaved
            # knuckles; the latch and electronic ID hardware move with the leaf.
            # Keep the barrel centre a full knuckle radius outboard of the
            # folded door edge.  This is the clearance used by a real
            # surface-mount hinge: the alternating knuckles remain visible
            # and the leaf can pass 90 degrees without scraping the skin.
            hinge_x = bx - door_w / 2 - 0.018
            hinge_offset = min(0.070, door_h * 0.30)
            for hinge_idx, hz in enumerate((-hinge_offset, hinge_offset)):
                hinge_z = cz + hz
                _hinge_component(
                    cyl(
                        coll,
                        f"{key}:hinge_{hinge_idx}:through_pin",
                        (hinge_x, 0.105, hinge_z),
                        0.0042,
                        0.060,
                        M["steel"],
                        20,
                        parent=root,
                        sem="locker_hardware",
                        bevel=0.0012,
                    ),
                    "fixed_pin",
                )
                _hinge_component(
                    box(
                        coll,
                        f"{key}:hinge_{hinge_idx}:jamb_leaf",
                        (hinge_x - 0.025, 0.094, hinge_z),
                        (0.050, 0.015, 0.050),
                        M["steel"],
                        0.004,
                        parent=root,
                        sem="locker_hardware",
                    ),
                    "fixed_leaf",
                )
                for knuckle_idx, offset in enumerate((-0.020, 0.020)):
                    _hinge_component(
                        cyl(
                            coll,
                            f"{key}:hinge_{hinge_idx}:fixed_knuckle_{knuckle_idx}",
                            (hinge_x, 0.105, hinge_z + offset),
                            0.0105,
                            0.017,
                            M["steel"],
                            24,
                            parent=root,
                            sem="locker_hardware",
                            bevel=0.0015,
                        ),
                        "fixed_knuckle",
                    )
                moving_leaf = _hinge_component(
                    box(
                        door_coll,
                        f"{key}:hinge_{hinge_idx}:door_leaf",
                        (hinge_x + 0.032, 0.108, hinge_z),
                        (0.064, 0.014, 0.044),
                        M["green_alt"],
                        0.004,
                        parent=root,
                        sem="locker_hardware",
                    ),
                    "moving_leaf",
                )
                moving_knuckle = _hinge_component(
                    cyl(
                        door_coll,
                        f"{key}:hinge_{hinge_idx}:moving_knuckle",
                        (hinge_x, 0.105, hinge_z),
                        0.0105,
                        0.023,
                        M["steel"],
                        24,
                        parent=root,
                        sem="locker_hardware",
                        bevel=0.0015,
                    ),
                    "moving_knuckle",
                )
                moving_parts.extend((moving_leaf, moving_knuckle))
            moving_parts.append(
                _front_screw(
                    door_coll,
                    f"{key}:latch",
                    bx + bay_w / 2 - 0.085,
                    0.108,
                    cz,
                    M["black"],
                    root,
                    0.014,
                )
            )
            moving_parts.append(
                box(
                    door_coll,
                    f"{key}:id_plate",
                    (bx + 0.31, 0.109, cz + 0.064),
                    (0.245, 0.012, 0.056),
                    M["yellow"],
                    0.006,
                    parent=root,
                    sem="locker_hardware",
                )
            )
            id_text = text_obj(
                door_coll,
                f"{key}:id_text",
                f"{door_index:03d}",
                (bx + 0.31, 0.119, cz + 0.064),
                0.055,
                M["charcoal"],
                0.002,
                parent=root,
                xscale=0.78,
                bold=True,
                sem="locker_hardware",
            )
            moving_parts.append(id_text)
            id_text["c2w_legible_compartment_number"] = True
            moving_parts.append(
                _front_screw(
                    door_coll,
                    f"{key}:status",
                    bx + 0.43,
                    0.115,
                    cz - 0.060,
                    M["led_green"] if door_index % 7 else M["led_red"],
                    root,
                    0.006,
                )
            )
            joint_name = f"parcel_door_{door_index:03d}_hinge"
            joint_records.append(
                articulate_hinged_door(
                    sim_coll,
                    root,
                    base_collision,
                    joint_name,
                    door_coll,
                    moving_parts,
                    (hinge_x, 0.105, cz),
                    (0.0, 0.0, 1.0),
                    (0.0, math.radians(108.0)),
                    joint_values,
                    (bx, 0.075, cz),
                    (door_w, 0.066, door_h),
                    (bx, 0.075, cz),
                    door_w,
                    -1,
                    0.030,
                    3.25,
                    0.32,
                    0.18,
                )
            )
            door_index += 1

    # Full-height central terminal follows the supplied real Hive Box reference:
    # portrait glass, stainless trim, dense operational UI and integrated readers.
    tx = grid_left + 4.5 * bay_w
    box(
        coll,
        "parcel:terminal:recess",
        (tx, 0.045, 1.23),
        (bay_w - 0.065, 0.038, 1.98),
        M["rubber"],
        0.012,
        parent=root,
        sem="locker_hardware",
    )
    box(
        coll,
        "parcel:terminal:panel",
        (tx, 0.079, 1.23),
        (bay_w - 0.102, 0.045, 1.94),
        M["green_alt"],
        0.014,
        parent=root,
        sem="workstation",
    )
    for side in (-1, 1):
        box(
            coll,
            f"parcel:terminal:stainless_reveal_{side}",
            (tx + side * 0.498, 0.118, 1.27),
            (0.062, 0.055, 1.86),
            M["steel"],
            0.009,
            parent=root,
            sem="workstation",
        )
    box(
        coll,
        "parcel:terminal:brand_header",
        (tx, 0.120, 2.110),
        (0.900, 0.036, 0.245),
        M["green"],
        0.012,
        parent=root,
        sem="signage",
    )
    _hex_logo(
        coll,
        "parcel:terminal:brand_icon",
        (tx - 0.345, 0.146, 2.110),
        0.078,
        0.018,
        M["yellow"],
        root,
    )
    text_obj(
        coll,
        "parcel:terminal:brand_text",
        "FengCai Hive Box",
        (tx + 0.095, 0.148, 2.115),
        0.200,
        M["charcoal"],
        0.006,
        parent=root,
        xscale=0.74,
        sem="signage",
    )
    for side in (-1, 1):
        for i in range(7):
            _front_screw(
                coll,
                f"parcel:terminal:header_speaker_{side}_{i}",
                tx + side * (0.24 + i * 0.017),
                0.149,
                1.985,
                M["black"],
                root,
                0.0038,
            )

    # Portrait touchscreen assembly with a narrow aluminum reveal and laminated bezel.
    box(
        coll,
        "parcel:terminal:screen_mount",
        (tx, 0.121, 1.355),
        (0.790, 0.038, 1.245),
        M["aluminium"],
        0.024,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "parcel:terminal:screen_bezel",
        (tx, 0.149, 1.355),
        (0.735, 0.028, 1.185),
        M["charcoal"],
        0.018,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "parcel:terminal:screen",
        (tx, 0.169, 1.355),
        (0.660, 0.012, 1.095),
        M["ui_white"],
        0.010,
        parent=root,
        sem="workstation",
    )
    # Promotional header and operating navigation.
    box(
        coll,
        "parcel:terminal:ui_promo",
        (tx, 0.180, 1.785),
        (0.618, 0.008, 0.205),
        M["screen_ui"],
        0.005,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_promo_title",
        "Smart delivery and pickup service",
        (tx - 0.118, 0.187, 1.820),
        0.060,
        M["white_emit"],
        0.0015,
        parent=root,
        xscale=0.80,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_promo_sub",
        "Scan to open cabinet",
        (tx - 0.145, 0.187, 1.748),
        0.031,
        M["white_emit"],
        0.001,
        parent=root,
        xscale=0.78,
        bold=False,
        sem="terminal_ui",
    )
    for i, height in enumerate((0.065, 0.105, 0.150)):
        box(
            coll,
            f"parcel:terminal:ui_locker_graphic_{i}",
            (tx + 0.205 + i * 0.062, 0.186, 1.735 + height / 2),
            (0.046, 0.008, height),
            M["ui_yellow"],
            0.004,
            parent=root,
            sem="terminal_ui",
        )
    box(
        coll,
        "parcel:terminal:ui_nav",
        (tx, 0.180, 1.625),
        (0.618, 0.008, 0.070),
        M["ui_pale"],
        0.003,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_nav_text",
        "pickup    shipping    tracking",
        (tx, 0.187, 1.625),
        0.035,
        M["ink"],
        0.001,
        parent=root,
        xscale=0.82,
        sem="terminal_ui",
    )
    # QR workflow on the left, retrieval-code workflow on the right.
    qr_code(
        coll,
        "parcel:terminal:ui_qr",
        (tx - 0.170, 1.355),
        0.250,
        0.185,
        M["ink"],
        M["white"],
        root,
        modules=15,
    )
    text_obj(
        coll,
        "parcel:terminal:ui_qr_label",
        "Scan to pick up the item.",
        (tx - 0.170, 0.190, 1.185),
        0.041,
        M["ink"],
        0.0012,
        parent=root,
        xscale=0.84,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_code_label",
        "Please provide the pick-up code.",
        (tx + 0.168, 0.188, 1.465),
        0.035,
        M["ui_gray"],
        0.001,
        parent=root,
        xscale=0.82,
        sem="terminal_ui",
    )
    for i in range(3):
        box(
            coll,
            f"parcel:terminal:ui_code_cell_{i}",
            (tx + 0.095 + i * 0.074, 0.186, 1.378),
            (0.060, 0.008, 0.072),
            M["ui_pale"],
            0.004,
            parent=root,
            sem="terminal_ui",
        )
    box(
        coll,
        "parcel:terminal:ui_confirm",
        (tx + 0.168, 0.186, 1.265),
        (0.242, 0.009, 0.082),
        M["ui_yellow"],
        0.006,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_confirm_text",
        "Confirm opening the cabinet.",
        (tx + 0.168, 0.193, 1.265),
        0.038,
        M["ink"],
        0.001,
        parent=root,
        xscale=0.84,
        sem="terminal_ui",
    )
    # Screen footer includes service notices and a second contact QR block.
    box(
        coll,
        "parcel:terminal:ui_footer_rule",
        (tx, 0.184, 1.090),
        (0.600, 0.006, 0.012),
        M["ui_gray"],
        0.002,
        parent=root,
        sem="terminal_ui",
    )
    text_obj(
        coll,
        "parcel:terminal:ui_footer",
        "Customer service hotline: 95333; Operation assistance.",
        (tx - 0.060, 0.190, 1.025),
        0.025,
        M["ui_gray"],
        0.001,
        parent=root,
        xscale=0.78,
        bold=False,
        sem="terminal_ui",
    )
    _front_screw(
        coll, "parcel:terminal:camera", tx, 0.193, 1.940, M["glass_dark"], root, 0.016
    )
    _hex_logo(
        coll,
        "parcel:terminal:nfc_reader",
        (tx + 0.270, 0.191, 1.530),
        0.035,
        0.010,
        M["ui_teal"],
        root,
    )

    # Service hardware remains below the glass as a real maintainable assembly.
    box(
        coll,
        "parcel:terminal:scanner_bezel",
        (tx - 0.245, 0.145, 0.655),
        (0.235, 0.032, 0.155),
        M["black"],
        0.010,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "parcel:terminal:scanner_glass",
        (tx - 0.245, 0.165, 0.655),
        (0.175, 0.012, 0.100),
        M["glass_dark"],
        0.006,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "parcel:terminal:receipt_slot",
        (tx + 0.225, 0.153, 0.705),
        (0.280, 0.020, 0.030),
        M["black"],
        0.005,
        parent=root,
        sem="workstation",
    )
    text_obj(
        coll,
        "parcel:terminal:hardware_label",
        "print/export invoice",
        (tx + 0.225, 0.166, 0.650),
        0.031,
        M["charcoal"],
        0.001,
        parent=root,
        xscale=0.82,
        sem="workstation",
    )
    box(
        coll,
        "parcel:terminal:service_hatch",
        (tx, 0.118, 0.390),
        (0.800, 0.032, 0.265),
        M["green"],
        0.010,
        parent=root,
        sem="workstation",
    )
    for side in (-1, 1):
        _front_screw(
            coll,
            f"parcel:terminal:service_screw_{side}",
            tx + side * 0.34,
            0.140,
            0.390,
            M["steel"],
            root,
            0.010,
        )
    for i in range(8):
        _front_screw(
            coll,
            f"parcel:terminal:lower_speaker_{i}",
            tx - 0.105 + i * 0.030,
            0.155,
            0.535,
            M["black"],
            root,
            0.0045,
        )

    # Brand mark and icon are modeled proud of the doors, matching the reference.
    box(
        coll,
        "parcel:fengchao_sign_back",
        (4.10, 0.106, 2.090),
        (3.05, 0.035, 0.300),
        M["green"],
        0.010,
        parent=root,
        sem="signage",
    )
    text_obj(
        coll,
        "parcel:fengchao_wordmark",
        "FengCai Intelligent Locker - Hive Box",
        (4.25, 0.137, 2.095),
        0.310,
        M["charcoal"],
        0.012,
        parent=root,
        xscale=0.72,
    )
    _hex_logo(
        coll,
        "parcel:fengchao_hex",
        (2.85, 0.140, 2.09),
        0.16,
        0.022,
        M["charcoal"],
        root,
    )
    _hex_logo(
        coll,
        "parcel:fengchao_hex_inner",
        (2.85, 0.154, 2.09),
        0.072,
        0.026,
        M["green"],
        root,
    )

    # Deep rain canopy, posts, front gutter and triangulated brackets.
    box(
        coll,
        "parcel:canopy_roof",
        (0, -0.15, 2.78),
        (width + 0.75, 1.66, 0.14),
        M["charcoal"],
        0.012,
        (math.radians(-3.0), 0, 0),
        root,
        "canopy_structure",
    )
    box(
        coll,
        "parcel:canopy_front_gutter",
        (0, 0.69, 2.70),
        (width + 0.82, 0.13, 0.26),
        M["charcoal"],
        0.008,
        parent=root,
        sem="canopy_structure",
    )
    box(
        coll,
        "parcel:canopy_rear_beam",
        (0, -0.93, 2.60),
        (width + 0.32, 0.12, 0.18),
        M["black"],
        0.006,
        parent=root,
        sem="canopy_structure",
    )
    post_xs = (-5.42, -3.55, -1.78, 0, 1.78, 3.55, 5.42)
    for i, px in enumerate(post_xs):
        box(
            coll,
            f"parcel:canopy_post_{i}",
            (px, -0.86, 1.38),
            (0.095, 0.095, 2.56),
            M["charcoal"],
            0.006,
            parent=root,
            sem="canopy_structure",
        )
        tube(
            coll,
            f"parcel:canopy_brace_{i}",
            ((px, -0.84, 2.48), (px, 0.42, 2.67)),
            0.027,
            M["steel"],
            root,
            "architectural_detail",
        )
        box(
            coll,
            f"parcel:post_foot_{i}",
            (px, -0.86, 0.035),
            (0.23, 0.22, 0.06),
            M["steel"],
            0.007,
            parent=root,
            sem="locker_hardware",
        )
        for sx in (-0.07, 0.07):
            _front_screw(
                coll,
                f"parcel:post_anchor_{i}_{sx:+.2f}",
                px + sx,
                -0.74,
                0.068,
                M["black"],
                root,
                0.010,
            )

    # Side panels have real ventilation slots and a rainwater downpipe.
    for side in (-1, 1):
        sx = side * (width / 2 + 0.035)
        box(
            coll,
            f"parcel:end_cheek_{side}",
            (sx, -0.45, 1.20),
            (0.105, 0.92, 2.30),
            M["green_alt"],
            0.013,
            parent=root,
            sem="locker_structure",
        )
        for i in range(8):
            box(
                coll,
                f"parcel:end_{side}:vent_{i}",
                (sx + side * 0.059, -0.65 + i * 0.075, 1.45),
                (0.012, 0.048, 0.22),
                M["black"],
                0.002,
                parent=root,
                sem="architectural_detail",
            )
    cyl(
        coll,
        "parcel:downpipe",
        (5.65, -0.90, 1.27),
        0.035,
        2.54,
        M["charcoal"],
        20,
        parent=root,
        sem="architectural_detail",
        bevel=0.003,
    )
    tube(
        coll,
        "parcel:downpipe_offset",
        ((5.65, -0.90, 0.12), (5.65, -0.72, 0.05), (5.65, -0.54, 0.05)),
        0.036,
        M["charcoal"],
        root,
        "architectural_detail",
    )

    if defer_physics:
        physics_counts = (1, len(joint_records), len(joint_records))
        asset_coll["c2w_physics_registration_deferred"] = True
    else:
        print("[delivery] parcel locker: batch physics", flush=True)
        physics_counts = _batch_finalize_blender_physics(sim_coll)
        asset_coll["c2w_physics_registration_deferred"] = False
    print("[delivery] parcel locker: native articulation graph", flush=True)
    carrier = _make_native_articulation_carrier(
        sim_coll, root, "parcel_locker", static_coll, joint_records
    )
    serialized_joints = _serializable_joint_records(joint_records)
    root["c2w_kinematic_tree"] = json.dumps(serialized_joints, sort_keys=True)
    root["c2w_articulation_standard"] = ARTICULATION_STANDARD
    root["c2w_native_articulation_carrier"] = carrier.name
    root["c2w_revolute_joint_count"] = len(joint_records)
    asset_coll["c2w_compartment_count"] = door_index - 1
    asset_coll["c2w_terminal_count"] = 1
    asset_coll["c2w_canopy_post_count"] = len(post_xs)
    asset_coll["c2w_numbered_compartment_count"] = door_index - 1
    asset_coll["c2w_terminal_detail_level"] = "portrait_operational_touchscreen"
    asset_coll["c2w_revolute_joint_count"] = len(joint_records)
    asset_coll["c2w_articulated_visual_link_count"] = len(joint_records)
    asset_coll["c2w_hollow_compartment_count"] = len(joint_records)
    asset_coll["c2w_blender_physics_batch_counts"] = list(physics_counts)
    print("[delivery] parcel locker: complete", flush=True)
    return asset_coll


# ---------------------------------------------------------------------------
# Asset 3 helpers: physically supported parcels and industrial shelving


def _xy(point, center, yaw):
    x, y = point
    cx, cy = center
    c, s = math.cos(yaw), math.sin(yaw)
    return cx + c * x - s * y, cy + s * x + c * y


def _rack_box(
    coll,
    name,
    center,
    yaw,
    loc,
    dims,
    material,
    parent,
    sem="rack_structure",
    bevel=0.0,
    detail=True,
):
    x, y = _xy((loc[0], loc[1]), center, yaw)
    if bevel > 0:
        return box(
            coll,
            name,
            (x, y, loc[2]),
            dims,
            material,
            bevel,
            (0, 0, yaw),
            parent,
            sem,
            detail,
        )
    return part_box(
        coll, name, (x, y, loc[2]), dims, material, (0, 0, yaw), parent, sem, detail
    )


def _parcel(
    coll,
    root,
    name,
    center,
    yaw,
    local_xy,
    support_top,
    dims,
    material,
    support_name,
    label_side=1,
):
    """Build a taped, labeled parcel whose body exactly rests on a shelf."""
    M = materials()
    w, d, h = dims
    x, y = _xy(local_xy, center, yaw)
    body = box(
        coll,
        name + ":body",
        (x, y, support_top + h / 2),
        dims,
        material,
        0.006,
        (0, 0, yaw),
        root,
        "parcel",
        False,
    )
    body["c2w_support_relation"] = "rests_on_modeled_shelf"
    body["c2w_support_name"] = support_name
    body["c2w_support_top_z"] = float(support_top)
    body["c2w_declared_base_z"] = float(support_top)
    body["c2w_parcel_assembly"] = name

    # Crossed packing tape on the lid and down the customer-facing panel.
    _rack_box(
        coll,
        name + ":top_tape_long",
        center,
        yaw,
        (local_xy[0], local_xy[1], support_top + h + 0.006),
        (0.064, d * 0.92, 0.012),
        M["tape"],
        root,
        "parcel_detail",
    )
    _rack_box(
        coll,
        name + ":top_tape_cross",
        center,
        yaw,
        (local_xy[0], local_xy[1], support_top + h + 0.013),
        (w * 0.88, 0.055, 0.010),
        M["tape"],
        root,
        "parcel_detail",
    )
    front_y = local_xy[1] + label_side * (d / 2 + 0.008)
    _rack_box(
        coll,
        name + ":front_tape",
        center,
        yaw,
        (local_xy[0], front_y, support_top + h / 2),
        (0.064, 0.012, h * 0.86),
        M["tape"],
        root,
        "parcel_detail",
    )
    label_z = support_top + h * 0.58
    label = _rack_box(
        coll,
        name + ":shipping_label",
        center,
        yaw,
        (local_xy[0] + w * 0.12, front_y + label_side * 0.009, label_z),
        (min(0.205, w * 0.62), 0.010, min(0.132, h * 0.48)),
        M["label"],
        root,
        "shipping_label",
    )
    label["c2w_attached_to"] = body.name
    # Printed barcode is physical geometry, so it survives any texture-free export.
    for bar in range(4):
        bw = 0.008 if bar % 2 else 0.014
        _rack_box(
            coll,
            name + f":barcode_{bar}",
            center,
            yaw,
            (
                local_xy[0] + w * 0.08 + (bar - 1.5) * 0.029,
                front_y + label_side * 0.015,
                label_z - 0.012,
            ),
            (bw, 0.006, min(0.075, h * 0.27)),
            M["ink"],
            root,
            "parcel_detail",
        )
    return body


def _build_rack(
    coll, root, name, center, yaw, length, depth, bays, levels, seed, parcels_per_bay=2
):
    """Build one perforated steel rack and fill every deck with supported parcels."""
    M = materials()
    rng = random.Random(seed)
    height = max(levels) + 0.62
    bay_w = length / bays
    uprights = [(-length / 2 + i * bay_w) for i in range(bays + 1)]
    for ui, ux in enumerate(uprights):
        for side in (-1, 1):
            uy = side * depth / 2
            _rack_box(
                coll,
                f"{name}:upright_{ui}_{side}",
                center,
                yaw,
                (ux, uy, height / 2),
                (0.062, 0.062, height),
                M["blue"],
                root,
                "rack_structure",
                0.004,
            )
            _rack_box(
                coll,
                f"{name}:foot_{ui}_{side}",
                center,
                yaw,
                (ux, uy, 0.035),
                (0.20, 0.15, 0.055),
                M["steel"],
                root,
                "rack_detail",
                0.004,
            )
            # Regular punched slots reveal the industrial rack construction.
            for pi, pz in enumerate(
                (0.31, 0.58, 0.85, 1.12, 1.39, 1.66, 1.93, 2.20, 2.47, 2.74, 3.01)
            ):
                if pz >= height - 0.12:
                    continue
                _rack_box(
                    coll,
                    f"{name}:perforation_{ui}_{side}_{pi}",
                    center,
                    yaw,
                    (ux, uy + side * 0.035, pz),
                    (0.018, 0.012, 0.055),
                    M["charcoal"],
                    root,
                    "rack_detail",
                )

    parcel_count = 0
    for li, shelf_z in enumerate(levels):
        shelf = _rack_box(
            coll,
            f"{name}:shelf_{li}",
            center,
            yaw,
            (0, 0, shelf_z),
            (length + 0.08, depth + 0.08, 0.065),
            M["steel"],
            root,
            "rack_shelf",
            0.005,
        )
        shelf_top = shelf_z + 0.0325
        shelf["c2w_support_top_z"] = shelf_top
        for side in (-1, 1):
            _rack_box(
                coll,
                f"{name}:beam_{li}_{side}",
                center,
                yaw,
                (0, side * (depth / 2 + 0.015), shelf_z - 0.035),
                (length + 0.11, 0.075, 0.105),
                M["blue"],
                root,
                "rack_structure",
                0.004,
            )
        # Back X braces prevent the rack from reading as unsupported shelves.
        if li < len(levels) - 1:
            z2 = levels[li + 1] - 0.04
            for bi in range(bays):
                x0 = -length / 2 + bi * bay_w
                x1 = x0 + bay_w
                p0 = _xy(
                    (
                        x0 + 0.06,
                        -depth / 2,
                    ),
                    center,
                    yaw,
                )
                p1 = _xy(
                    (
                        x1 - 0.06,
                        -depth / 2,
                    ),
                    center,
                    yaw,
                )
                tube(
                    coll,
                    f"{name}:crossbrace_{li}_{bi}_a",
                    ((p0[0], p0[1], shelf_z + 0.05), (p1[0], p1[1], z2)),
                    0.012,
                    M["aluminium"],
                    root,
                    "rack_detail",
                )
                tube(
                    coll,
                    f"{name}:crossbrace_{li}_{bi}_b",
                    ((p1[0], p1[1], shelf_z + 0.05), (p0[0], p0[1], z2)),
                    0.012,
                    M["aluminium"],
                    root,
                    "rack_detail",
                )

        for bi in range(bays):
            slot_w = bay_w / parcels_per_bay
            for si in range(parcels_per_bay):
                max_w = slot_w * 0.78
                pw = min(max_w, rng.choice((0.25, 0.30, 0.34, 0.38, 0.42)))
                pd = min(depth * 0.75, rng.choice((0.28, 0.34, 0.40, 0.46, 0.50)))
                ph = rng.choice((0.20, 0.24, 0.28, 0.33, 0.38, 0.43))
                px = -length / 2 + bi * bay_w + (si + 0.5) * slot_w
                py = rng.uniform(-0.035, 0.035)
                material = M[
                    rng.choice(
                        ("cardboard_a", "cardboard_a", "cardboard_b", "cardboard_c")
                    )
                ]
                _parcel(
                    coll,
                    root,
                    f"{name}:parcel_{li}_{bi}_{si}",
                    center,
                    yaw,
                    (px, py),
                    shelf_top,
                    (pw, pd, ph),
                    material,
                    shelf.name,
                    1,
                )
                parcel_count += 1
    return parcel_count


# ---------------------------------------------------------------------------
# Asset 3: glazed parcel station with complete interior


def build_delivery_station(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Build the reference glass parcel station, fitted and stocked inside."""
    print("[delivery] parcel station: detailed geometry", flush=True)
    M = materials()
    coll = collection("DELIVERY_STATION", parent)
    root = anchor(coll, "station_anchor", origin, yaw)
    coll["c2w_asset_id"] = "delivery.station.cainiao.v1"
    coll["c2w_asset_type"] = "parcel_station"
    coll["c2w_independent_builder"] = "build_delivery_station"
    coll["c2w_reference_files"] = "station_exterior.jpg;station_interior.jpg"

    width, depth, wall_h = 12.4, 8.6, 4.15
    front_y, back_y = 0.0, -depth
    # Occupied shell: floor build-up, roof, opaque service walls and corner posts.
    box(
        coll,
        "station:foundation",
        (0, -depth / 2, 0.06),
        (width + 0.22, depth + 0.20, 0.28),
        M["concrete"],
        0.018,
        parent=root,
        sem="architecture",
    )
    box(
        coll,
        "station:epoxy_floor",
        (0, -depth / 2, 0.225),
        (width, depth, 0.075),
        M["floor"],
        0.008,
        parent=root,
        sem="floor_finish",
    )
    box(
        coll,
        "station:roof_deck",
        (0, -depth / 2, wall_h),
        (width + 0.26, depth + 0.24, 0.22),
        M["white_metal"],
        0.012,
        parent=root,
        sem="architecture",
    )
    box(
        coll,
        "station:rear_wall",
        (0, back_y + 0.07, 2.10),
        (width, 0.14, 3.85),
        M["white_metal"],
        0.008,
        parent=root,
        sem="architecture",
    )
    box(
        coll,
        "station:left_wall",
        (-width / 2 + 0.07, -depth / 2, 2.10),
        (0.14, depth, 3.85),
        M["white_metal"],
        0.008,
        parent=root,
        sem="architecture",
    )
    box(
        coll,
        "station:right_service_wall",
        (width / 2 - 0.07, -7.0, 2.10),
        (0.14, 3.15, 3.85),
        M["white_metal"],
        0.008,
        parent=root,
        sem="architecture",
    )

    # Modeled corrugations on opaque wall/ceiling surfaces catch daylight at real scale.
    for i, x in enumerate([(-width / 2 + 0.16) + i * 0.16 for i in range(76)]):
        part_box(
            coll,
            f"station:rear_corrugation_{i}",
            (x, back_y + 0.145, 2.08),
            (0.026, 0.025, 3.68),
            M["aluminium"],
            parent=root,
            sem="architectural_detail",
        )
    for i, y in enumerate([back_y + 0.18 + i * 0.16 for i in range(52)]):
        part_box(
            coll,
            f"station:left_corrugation_{i}",
            (-width / 2 + 0.145, y, 2.08),
            (0.025, 0.026, 3.68),
            M["aluminium"],
            parent=root,
            sem="architectural_detail",
        )
    for i, y in enumerate([back_y + 0.15 + i * 0.27 for i in range(32)]):
        part_box(
            coll,
            f"station:ceiling_rib_{i}",
            (0, y, 3.985),
            (width - 0.18, 0.026, 0.035),
            M["aluminium"],
            parent=root,
            sem="architectural_detail",
        )

    # Epoxy floor control joints and a flush entry threshold.
    for i, x in enumerate([(-width / 2 + 0.8) + i * 1.0 for i in range(12)]):
        part_box(
            coll,
            f"station:floor_joint_x_{i}",
            (x, -depth / 2, 0.266),
            (0.010, depth - 0.20, 0.006),
            M["joint"],
            parent=root,
            sem="floor_detail",
        )
    for i, y in enumerate([-0.75 - i * 1.0 for i in range(8)]):
        part_box(
            coll,
            f"station:floor_joint_y_{i}",
            (0, y, 0.266),
            (width - 0.20, 0.010, 0.006),
            M["joint"],
            parent=root,
            sem="floor_detail",
        )
    box(
        coll,
        "station:entry_threshold",
        (-4.55, 0.055, 0.245),
        (2.35, 0.24, 0.075),
        M["steel"],
        0.006,
        parent=root,
        sem="architectural_detail",
    )

    # Black aluminum glazed storefront and open sliding entrance.
    front_divisions = (-6.2, -5.65, -3.45, -1.40, 0.70, 2.80, 4.90, 6.20)
    for i, (x0, x1) in enumerate(zip(front_divisions, front_divisions[1:])):
        if i == 1:  # physical doorway, with one leaf slid aside below
            continue
        pane_w = x1 - x0 - 0.10
        box(
            coll,
            f"station:front_glass_{i}",
            ((x0 + x1) / 2, 0.015, 1.78),
            (pane_w, 0.025, 3.02),
            M["glass"],
            0.002,
            parent=root,
            sem="glazing",
        )
    for i, x in enumerate(front_divisions):
        box(
            coll,
            f"station:front_mullion_{i}",
            (x, 0.035, 1.80),
            (0.075, 0.095, 3.30),
            M["charcoal"],
            0.006,
            parent=root,
            sem="architectural_detail",
        )
    for z, name in ((0.28, "sill"), (3.31, "head")):
        box(
            coll,
            f"station:front_{name}_rail",
            (0, 0.035, z),
            (width + 0.05, 0.095, 0.095),
            M["charcoal"],
            0.006,
            parent=root,
            sem="architectural_detail",
        )
    # Sliding glass door is visibly open, with floor track, pull handles and rollers.
    box(
        coll,
        "station:entry_fixed_leaf",
        (-5.08, 0.020, 1.70),
        (1.02, 0.028, 2.80),
        M["glass"],
        0.002,
        parent=root,
        sem="door_glazing",
    )
    for x in (-5.61, -4.55):
        box(
            coll,
            f"station:entry_frame_{x:+.2f}",
            (x, 0.045, 1.70),
            (0.065, 0.085, 2.95),
            M["charcoal"],
            0.005,
            parent=root,
            sem="architectural_detail",
        )
    # Moving leaf parked behind the fixed panel, leaving a 1.05 m clear opening.
    box(
        coll,
        "station:entry_sliding_leaf_open",
        (-5.02, -0.075, 1.70),
        (0.94, 0.025, 2.72),
        M["glass"],
        0.002,
        parent=root,
        sem="door_glazing",
    )
    for z in (1.08, 1.72):
        cyl(
            coll,
            f"station:door_handle_{z:.2f}",
            (-4.50, 0.080, z),
            0.018,
            0.48,
            M["steel"],
            18,
            parent=root,
            sem="architectural_detail",
            bevel=0.002,
        )
    box(
        coll,
        "station:sliding_floor_track",
        (-4.55, 0.03, 0.295),
        (2.28, 0.085, 0.032),
        M["steel"],
        0.003,
        parent=root,
        sem="architectural_detail",
    )

    # Transparent right return facade forms the reference's glazed corner box.
    side_divisions = (0.0, -1.65, -3.30, -4.95, -5.55)
    for i, (y0, y1) in enumerate(zip(side_divisions, side_divisions[1:])):
        box(
            coll,
            f"station:right_glass_{i}",
            (width / 2 - 0.015, (y0 + y1) / 2, 1.78),
            (0.025, abs(y1 - y0) - 0.10, 3.02),
            M["glass"],
            0.002,
            parent=root,
            sem="glazing",
        )
    for i, y in enumerate(side_divisions):
        box(
            coll,
            f"station:right_mullion_{i}",
            (width / 2 - 0.035, y, 1.80),
            (0.095, 0.075, 3.30),
            M["charcoal"],
            0.006,
            parent=root,
            sem="architectural_detail",
        )
    for z, name in ((0.28, "sill"), (3.31, "head")):
        box(
            coll,
            f"station:right_{name}_rail",
            (width / 2 - 0.035, -2.77, z),
            (0.095, 5.60, 0.095),
            M["charcoal"],
            0.006,
            parent=root,
            sem="architectural_detail",
        )

    # Cyan illuminated fascia wraps the corner and is held by a black carrier frame.
    box(
        coll,
        "station:front_fascia_frame",
        (0, -0.015, 3.69),
        (width + 0.12, 0.14, 0.82),
        M["charcoal"],
        0.008,
        parent=root,
        sem="signage",
    )
    box(
        coll,
        "station:front_fascia_blue",
        (0, 0.069, 3.69),
        (width - 0.17, 0.035, 0.65),
        M["cyan_emit"],
        0.006,
        parent=root,
        sem="signage",
    )
    box(
        coll,
        "station:right_fascia_frame",
        (width / 2 + 0.015, -2.75, 3.69),
        (0.14, 5.62, 0.82),
        M["charcoal"],
        0.008,
        parent=root,
        sem="signage",
    )
    box(
        coll,
        "station:right_fascia_blue",
        (width / 2 + 0.091, -2.75, 3.69),
        (0.025, 5.42, 0.65),
        M["cyan_emit"],
        0.004,
        parent=root,
        sem="signage",
    )
    # The public-facing fascia intentionally carries one large English-only
    # wordmark.  Its dimensions are audited against the cyan carrier below so
    # it remains crisply legible in the full-row daylight camera without ever
    # crossing the sign boundary.
    primary_sign = text_obj(
        coll,
        "station:primary_wordmark",
        "CAINIAO PARCEL STATION",
        (0.62, 0.104, 3.70),
        1.250,
        M["white_emit"],
        0.024,
        parent=root,
        xscale=1.65,
    )
    primary_sign["c2w_front_sign_language"] = "English"
    primary_sign["c2w_enlarged_for_far_view"] = True
    coll["c2w_front_sign_language"] = "English"
    _hex_logo(
        coll,
        "station:brand_hex",
        (-4.70, 0.105, 3.79),
        0.23,
        0.025,
        M["white_emit"],
        root,
    )
    _hex_logo(
        coll,
        "station:brand_hex_inner",
        (-4.70, 0.122, 3.79),
        0.105,
        0.029,
        M["cyan_emit"],
        root,
    )

    # Rack layout follows the interior reference: long blue runs, open aisles,
    # a dense glazed display side and a rear wall run.
    parcel_total = 0
    rack_specs = (
        (
            "rear_wall_rack",
            (0.0, -7.70),
            0.0,
            10.45,
            0.66,
            8,
            (0.48, 1.18, 1.88, 2.58),
            3101,
            2,
        ),
        (
            "left_aisle_rack",
            (-4.63, -4.45),
            math.pi / 2,
            5.30,
            0.68,
            5,
            (0.48, 1.17, 1.86, 2.55),
            3102,
            2,
        ),
        (
            "middle_aisle_rack",
            (-2.12, -4.45),
            math.pi / 2,
            5.30,
            0.68,
            5,
            (0.48, 1.17, 1.86, 2.55),
            3103,
            2,
        ),
        (
            "glass_side_rack",
            (5.20, -3.80),
            math.pi / 2,
            4.95,
            0.66,
            4,
            (0.48, 1.17, 1.86, 2.55),
            3104,
            2,
        ),
        (
            "front_display_rack",
            (2.86, -0.72),
            0.0,
            4.55,
            0.60,
            4,
            (0.47, 1.15, 1.83),
            3105,
            2,
        ),
    )
    for spec in rack_specs:
        parcel_total += _build_rack(coll, root, *spec)

    # Blue-white reception counter and packing workbench.
    box(
        coll,
        "station:counter:front_carcass",
        (2.25, -4.48, 0.72),
        (3.55, 0.78, 1.18),
        M["blue"],
        0.028,
        parent=root,
        sem="counter",
    )
    box(
        coll,
        "station:counter:solid_top",
        (2.25, -4.45, 1.35),
        (3.78, 0.96, 0.105),
        M["offwhite"],
        0.028,
        parent=root,
        sem="counter",
    )
    box(
        coll,
        "station:counter:kick",
        (2.25, -4.02, 0.25),
        (3.48, 0.10, 0.22),
        M["charcoal"],
        0.006,
        parent=root,
        sem="counter_detail",
    )
    for i in range(4):
        box(
            coll,
            f"station:counter:front_panel_{i}",
            (0.93 + i * 0.88, -4.005, 0.76),
            (0.78, 0.045, 0.83),
            M["blue"],
            0.008,
            parent=root,
            sem="counter_detail",
        )
        box(
            coll,
            f"station:counter:panel_reveal_{i}",
            (0.93 + i * 0.88, -3.978, 0.76),
            (0.67, 0.010, 0.70),
            M["cyan_emit"] if i == 1 else M["blue"],
            0.004,
            parent=root,
            sem="counter_detail",
        )
    # Accessible lower return table, white top, steel legs and under-table drawer.
    box(
        coll,
        "station:packing_table:top",
        (4.35, -5.47, 1.03),
        (2.22, 1.05, 0.095),
        M["offwhite"],
        0.018,
        parent=root,
        sem="counter",
    )
    for px in (3.40, 5.30):
        for py in (-5.10, -5.84):
            box(
                coll,
                f"station:packing_table:leg_{px:.2f}_{py:.2f}",
                (px, py, 0.55),
                (0.070, 0.070, 0.96),
                M["steel"],
                0.006,
                parent=root,
                sem="counter_detail",
            )
    box(
        coll,
        "station:packing_table:drawer",
        (4.35, -5.05, 0.82),
        (1.08, 0.42, 0.25),
        M["blue"],
        0.010,
        parent=root,
        sem="counter_detail",
    )
    box(
        coll,
        "station:packing_table:drawer_pull",
        (4.35, -4.82, 0.82),
        (0.45, 0.045, 0.035),
        M["steel"],
        0.010,
        parent=root,
        sem="counter_detail",
    )

    # Reference-shaped all-in-one POS: broad weighted base, tapered aluminum
    # column, serviceable hinge and a thin laminated touchscreen rather than a
    # slab on a pole.  The screen carries a complete parcel-station workflow.
    monitor_center = (2.30, -4.34, 1.965)
    monitor_tilt = math.radians(-8.0)
    box(
        coll,
        "station:pos:weighted_base",
        (2.30, -4.42, 1.445),
        (0.760, 0.420, 0.070),
        M["white_metal"],
        0.035,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:pos:base_inset",
        (2.30, -4.205, 1.447),
        (0.520, 0.030, 0.025),
        M["aluminium"],
        0.008,
        parent=root,
        sem="workstation",
    )
    for side in (-1, 1):
        box(
            coll,
            f"station:pos:base_port_{side}",
            (2.30 + side * 0.205, -4.196, 1.450),
            (0.110, 0.010, 0.018),
            M["black"],
            0.003,
            parent=root,
            sem="workstation",
        )
    tapered_box(
        coll,
        "station:pos:tapered_column",
        (2.30, -4.43, 1.650),
        (0.340, 0.245),
        (0.185, 0.130),
        0.390,
        M["white_metal"],
        0.016,
        parent=root,
        sem="workstation",
    )
    cyl(
        coll,
        "station:pos:tilt_hinge",
        (2.30, -4.375, 1.825),
        0.072,
        0.360,
        M["steel"],
        28,
        (0, math.pi / 2, 0),
        root,
        "workstation",
        0.005,
    )
    box(
        coll,
        "station:pos:rear_shell",
        monitor_center,
        (1.010, 0.085, 0.655),
        M["white_metal"],
        0.035,
        (monitor_tilt, 0, 0),
        root,
        "workstation",
    )
    box(
        coll,
        "station:pos:vent_band",
        _tilted_front_point(monitor_center, 0, -0.275, -0.050, monitor_tilt),
        (0.610, 0.012, 0.045),
        M["aluminium"],
        0.005,
        (monitor_tilt, 0, 0),
        root,
        "workstation",
    )
    for i in range(11):
        tilted_ui_box(
            coll,
            f"station:pos:rear_vent_{i}",
            monitor_center,
            -0.250 + i * 0.050,
            -0.275,
            (0.025, 0.016),
            M["black"],
            monitor_tilt,
            root,
            front_offset=-0.058,
            depth=0.006,
            sem="workstation",
        )
    box(
        coll,
        "station:pos:front_bezel",
        _tilted_front_point(monitor_center, 0, 0, 0.058, monitor_tilt),
        (0.960, 0.045, 0.605),
        M["charcoal"],
        0.025,
        (monitor_tilt, 0, 0),
        root,
        "workstation",
    )
    box(
        coll,
        "station:pos:monitor_glass",
        _tilted_front_point(monitor_center, 0, 0, 0.084, monitor_tilt),
        (0.895, 0.010, 0.535),
        M["screen"],
        0.012,
        (monitor_tilt, 0, 0),
        root,
        "workstation",
    )
    tilted_ui_box(
        coll,
        "station:pos:ui_canvas",
        monitor_center,
        0,
        0,
        (0.855, 0.495),
        M["ui_white"],
        monitor_tilt,
        root,
        front_offset=0.092,
        depth=0.006,
    )
    tilted_ui_box(
        coll,
        "station:pos:ui_header",
        monitor_center,
        0,
        0.205,
        (0.855, 0.085),
        M["ui_navy"],
        monitor_tilt,
        root,
        front_offset=0.100,
    )
    tilted_ui_text(
        coll,
        "station:pos:ui_title",
        "Stationery Workbench",
        monitor_center,
        -0.275,
        0.207,
        0.046,
        M["white_emit"],
        monitor_tilt,
        root,
        xscale=0.84,
        front_offset=0.106,
        align="LEFT",
    )
    tilted_ui_text(
        coll,
        "station:pos:ui_clock",
        "09:36",
        monitor_center,
        0.330,
        0.207,
        0.027,
        M["white_emit"],
        monitor_tilt,
        root,
        xscale=0.78,
        front_offset=0.106,
        bold=False,
    )
    # Left navigation rail with icon glyphs.
    tilted_ui_box(
        coll,
        "station:pos:ui_sidebar",
        monitor_center,
        -0.375,
        -0.045,
        (0.105, 0.405),
        M["ui_gray"],
        monitor_tilt,
        root,
        front_offset=0.101,
    )
    for i, label in enumerate(("enter", "take", "check", "Settings")):
        dz = 0.095 - i * 0.092
        tilted_ui_box(
            coll,
            f"station:pos:nav_icon_back_{i}",
            monitor_center,
            -0.375,
            dz,
            (0.058, 0.058),
            M["screen_ui"] if i == 0 else M["ui_pale"],
            monitor_tilt,
            root,
            front_offset=0.108,
        )
        tilted_ui_text(
            coll,
            f"station:pos:nav_icon_{i}",
            label,
            monitor_center,
            -0.375,
            dz,
            0.026,
            M["white_emit"] if i == 0 else M["ink"],
            monitor_tilt,
            root,
            xscale=0.82,
            front_offset=0.114,
        )
    # Summary cards and a real tabular order list.
    for i, (dx, label, value, material) in enumerate(
        (
            (-0.205, "To be stored", "12", M["screen_ui"]),
            (0.045, "Awaiting pickup", "36", M["ui_teal"]),
            (0.295, "exceptions", "03", M["ui_yellow"]),
        )
    ):
        tilted_ui_box(
            coll,
            f"station:pos:summary_{i}",
            monitor_center,
            dx,
            0.108,
            (0.215, 0.110),
            M["ui_pale"],
            monitor_tilt,
            root,
            front_offset=0.102,
        )
        tilted_ui_text(
            coll,
            f"station:pos:summary_label_{i}",
            label,
            monitor_center,
            dx - 0.045,
            0.130,
            0.024,
            M["ui_gray"],
            monitor_tilt,
            root,
            xscale=0.78,
            front_offset=0.110,
            bold=False,
        )
        tilted_ui_text(
            coll,
            f"station:pos:summary_value_{i}",
            value,
            monitor_center,
            dx + 0.055,
            0.092,
            0.041,
            material,
            monitor_tilt,
            root,
            xscale=0.86,
            front_offset=0.111,
        )
    tilted_ui_box(
        coll,
        "station:pos:table_header",
        monitor_center,
        0.045,
        0.018,
        (0.650, 0.052),
        M["ui_gray"],
        monitor_tilt,
        root,
        front_offset=0.103,
    )
    tilted_ui_text(
        coll,
        "station:pos:table_header_text",
        "Order number    Mobile tail number   Status",
        monitor_center,
        -0.045,
        0.018,
        0.022,
        M["white_emit"],
        monitor_tilt,
        root,
        xscale=0.77,
        front_offset=0.111,
        bold=False,
    )
    rows = (
        ("A260831", "4821", "Awaiting pickup"),
        ("B260829", "1760", "In stock"),
        ("C260824", "9035", "pending verification"),
    )
    for i, (order, phone, state) in enumerate(rows):
        dz = -0.048 - i * 0.061
        tilted_ui_box(
            coll,
            f"station:pos:table_row_{i}",
            monitor_center,
            0.045,
            dz,
            (0.650, 0.052),
            M["ui_white"] if i % 2 == 0 else M["ui_pale"],
            monitor_tilt,
            root,
            front_offset=0.104,
        )
        tilted_ui_text(
            coll,
            f"station:pos:order_{i}",
            order,
            monitor_center,
            -0.210,
            dz,
            0.019,
            M["ink"],
            monitor_tilt,
            root,
            xscale=0.73,
            front_offset=0.112,
            bold=False,
        )
        tilted_ui_text(
            coll,
            f"station:pos:phone_{i}",
            phone,
            monitor_center,
            0.025,
            dz,
            0.019,
            M["ink"],
            monitor_tilt,
            root,
            xscale=0.76,
            front_offset=0.112,
            bold=False,
        )
        tilted_ui_box(
            coll,
            f"station:pos:state_chip_{i}",
            monitor_center,
            0.260,
            dz,
            (0.135, 0.034),
            M["screen_ui"] if i == 0 else M["ui_teal"],
            monitor_tilt,
            root,
            front_offset=0.110,
        )
        tilted_ui_text(
            coll,
            f"station:pos:state_{i}",
            state,
            monitor_center,
            0.260,
            dz,
            0.018,
            M["white_emit"],
            monitor_tilt,
            root,
            xscale=0.74,
            front_offset=0.116,
            bold=False,
        )
    tilted_ui_box(
        coll,
        "station:pos:action_button",
        monitor_center,
        0.250,
        -0.210,
        (0.230, 0.052),
        M["screen_ui"],
        monitor_tilt,
        root,
        front_offset=0.106,
    )
    tilted_ui_text(
        coll,
        "station:pos:action_text",
        "Confirm outbound shipment.",
        monitor_center,
        0.250,
        -0.210,
        0.023,
        M["white_emit"],
        monitor_tilt,
        root,
        xscale=0.80,
        front_offset=0.114,
    )
    _front_screw(
        coll, "station:pos:status_led", 2.30, -4.242, 1.704, M["led_green"], root, 0.006
    )
    _front_screw(
        coll,
        "station:pos:side_power_button",
        2.792,
        -4.285,
        1.845,
        M["steel"],
        root,
        0.010,
    )

    # Low-profile service keyboard with staggered rows and realistic special keys.
    box(
        coll,
        "station:pos:keyboard_base",
        (1.30, -3.98, 1.435),
        (0.990, 0.380, 0.050),
        M["charcoal"],
        0.020,
        (math.radians(4), 0, 0),
        root,
        "workstation",
    )
    for row in range(4):
        row_offset = (row % 2) * 0.018
        for key in range(12):
            part_box(
                coll,
                f"station:pos:key_{row}_{key}",
                (
                    0.855 + row_offset + key * 0.074,
                    -3.845 - row * 0.066,
                    1.467 + row * 0.004,
                ),
                (0.057, 0.044, 0.012),
                M["white_metal"],
                parent=root,
                sem="workstation",
            )
    part_box(
        coll,
        "station:pos:key_space",
        (1.300, -4.117, 1.482),
        (0.330, 0.046, 0.012),
        M["white_metal"],
        parent=root,
        sem="workstation",
    )
    part_box(
        coll,
        "station:pos:key_enter",
        (1.690, -4.052, 1.477),
        (0.100, 0.050, 0.012),
        M["ui_teal"],
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:scale:platform",
        (3.45, -4.35, 1.43),
        (1.10, 0.70, 0.065),
        M["steel"],
        0.012,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:scale:display",
        (3.84, -4.00, 1.53),
        (0.31, 0.10, 0.18),
        M["screen"],
        0.010,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:scanner:base",
        (0.78, -4.22, 1.47),
        (0.24, 0.26, 0.16),
        M["charcoal"],
        0.012,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:scanner:head",
        (0.78, -4.12, 1.68),
        (0.19, 0.12, 0.26),
        M["glass_dark"],
        0.025,
        (math.radians(-16), 0, 0),
        root,
        "workstation",
    )
    box(
        coll,
        "station:label_printer:body",
        (4.82, -5.30, 1.24),
        (0.58, 0.49, 0.38),
        M["white_metal"],
        0.035,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:label_printer:slot",
        (4.82, -5.03, 1.27),
        (0.36, 0.025, 0.065),
        M["black"],
        0.006,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:receipt_printer:body",
        (1.15, -4.42, 1.54),
        (0.38, 0.38, 0.25),
        M["white_metal"],
        0.025,
        parent=root,
        sem="workstation",
    )
    box(
        coll,
        "station:receipt_printer:paper",
        (1.15, -4.20, 1.58),
        (0.24, 0.018, 0.12),
        M["label"],
        0.004,
        parent=root,
        sem="workstation",
    )
    cyl(
        coll,
        "station:tape_dispenser:roll",
        (4.08, -5.22, 1.30),
        0.15,
        0.09,
        M["tape"],
        28,
        (math.pi / 2, 0, 0),
        root,
        "workstation",
        0.003,
    )
    cyl(
        coll,
        "station:tape_dispenser:hub",
        (4.08, -5.165, 1.30),
        0.050,
        0.11,
        M["charcoal"],
        24,
        (math.pi / 2, 0, 0),
        root,
        "workstation",
        0.002,
    )

    # Ergonomic operator chair with five-star base and casters.
    cyl(
        coll,
        "station:chair:column",
        (2.45, -5.72, 0.62),
        0.055,
        0.72,
        M["steel"],
        24,
        parent=root,
        sem="furniture",
        bevel=0.004,
    )
    box(
        coll,
        "station:chair:seat",
        (2.45, -5.72, 0.93),
        (0.66, 0.66, 0.15),
        M["charcoal"],
        0.075,
        parent=root,
        sem="furniture",
    )
    box(
        coll,
        "station:chair:back",
        (2.45, -6.00, 1.48),
        (0.64, 0.13, 0.86),
        M["charcoal"],
        0.085,
        (math.radians(-7), 0, 0),
        root,
        "furniture",
    )
    for i in range(5):
        angle = math.tau * i / 5
        ex = 2.45 + math.cos(angle) * 0.40
        ey = -5.72 + math.sin(angle) * 0.40
        tube(
            coll,
            f"station:chair:star_arm_{i}",
            ((2.45, -5.72, 0.34), (ex, ey, 0.22)),
            0.032,
            M["steel"],
            root,
            "furniture_detail",
        )
        cyl(
            coll,
            f"station:chair:caster_{i}",
            (ex, ey, 0.16),
            0.055,
            0.045,
            M["rubber"],
            16,
            (math.pi / 2, 0, angle),
            root,
            "furniture_detail",
            0.002,
        )

    # Service equipment: parcel trolley, CCTV, extinguisher, data cabinet and conduits.
    for px in (-5.40, -4.65):
        cyl(
            coll,
            f"station:trolley:wheel_{px:.2f}",
            (px, -1.24, 0.23),
            0.16,
            0.075,
            M["rubber"],
            20,
            (math.pi / 2, 0, 0),
            root,
            "equipment",
            0.003,
        )
    box(
        coll,
        "station:trolley:platform",
        (-5.02, -1.25, 0.27),
        (0.92, 0.62, 0.095),
        M["steel"],
        0.012,
        parent=root,
        sem="equipment",
    )
    tube(
        coll,
        "station:trolley:handle",
        (
            (-5.42, -1.52, 0.30),
            (-5.42, -1.52, 1.58),
            (-4.73, -1.52, 1.58),
            (-4.73, -1.52, 0.30),
        ),
        0.035,
        M["blue"],
        root,
        "equipment",
    )
    cyl(
        coll,
        "station:extinguisher:tank",
        (-5.63, -7.82, 0.58),
        0.14,
        0.82,
        M["red"],
        28,
        parent=root,
        sem="safety_equipment",
        bevel=0.008,
    )
    box(
        coll,
        "station:extinguisher:label",
        (-5.63, -7.67, 0.64),
        (0.16, 0.018, 0.28),
        M["label"],
        0.004,
        parent=root,
        sem="safety_equipment",
    )
    tube(
        coll,
        "station:extinguisher:hose",
        ((-5.56, -7.80, 0.91), (-5.43, -7.70, 0.89), (-5.45, -7.66, 0.63)),
        0.018,
        M["rubber"],
        root,
        "safety_equipment",
    )
    box(
        coll,
        "station:data_cabinet",
        (5.78, -7.28, 2.12),
        (0.38, 0.22, 1.30),
        M["charcoal"],
        0.018,
        parent=root,
        sem="equipment",
    )
    for i in range(8):
        box(
            coll,
            f"station:data_cabinet:vent_{i}",
            (5.57, -7.16 + i * 0.025, 2.22),
            (0.018, 0.012, 0.70),
            M["black"],
            0.002,
            parent=root,
            sem="equipment_detail",
        )
    tube(
        coll,
        "station:data_conduit",
        ((5.78, -7.40, 2.76), (5.78, -7.40, 3.60), (4.85, -7.40, 3.60)),
        0.025,
        M["steel"],
        root,
        "equipment_detail",
    )
    box(
        coll,
        "station:cctv:wall_mount",
        (5.86, -7.62, 3.47),
        (0.23, 0.20, 0.18),
        M["steel"],
        0.012,
        parent=root,
        sem="equipment",
    )
    cyl(
        coll,
        "station:cctv:camera_body",
        (5.62, -7.40, 3.36),
        0.105,
        0.34,
        M["white_metal"],
        28,
        (0, math.pi / 2, math.radians(-35)),
        root,
        "equipment",
        0.006,
    )
    cyl(
        coll,
        "station:cctv:lens",
        (5.48, -7.30, 3.29),
        0.072,
        0.025,
        M["glass_dark"],
        24,
        (0, math.pi / 2, math.radians(-35)),
        root,
        "equipment",
        0.003,
    )

    # Linear and pendant luminaires match the bright ribbed interior reference.
    for i, x in enumerate((-4.6, -2.3, 0.0, 2.3, 4.6)):
        box(
            coll,
            f"station:linear_light_{i}:housing",
            (x, -4.45, 3.82),
            (1.55, 0.13, 0.085),
            M["white_metal"],
            0.010,
            parent=root,
            sem="lighting_fixture",
        )
        box(
            coll,
            f"station:linear_light_{i}:diffuser",
            (x, -4.45, 3.765),
            (1.42, 0.095, 0.025),
            M["white_emit"],
            0.006,
            parent=root,
            sem="lighting_fixture",
        )
        area_light(
            coll,
            f"station:linear_light_{i}:area",
            (x, -4.45, 3.72),
            115,
            (1.30, 0.22),
            (1.0, 0.94, 0.86),
            (0, 0, 0),
            root,
        )
    for i, (x, y) in enumerate(
        (
            (-4.1, -1.15),
            (-1.5, -1.15),
            (1.0, -1.15),
            (3.7, -1.15),
            (-3.2, -6.65),
            (3.4, -6.65),
        )
    ):
        cyl(
            coll,
            f"station:pendant_{i}:cable",
            (x, y, 3.60),
            0.010,
            0.58,
            M["black"],
            12,
            parent=root,
            sem="lighting_fixture",
            bevel=0.001,
        )
        cyl(
            coll,
            f"station:pendant_{i}:housing",
            (x, y, 3.25),
            0.105,
            0.28,
            M["charcoal"],
            28,
            parent=root,
            sem="lighting_fixture",
            bevel=0.009,
        )
        cyl(
            coll,
            f"station:pendant_{i}:diffuser",
            (x, y, 3.105),
            0.095,
            0.035,
            M["white_emit"],
            28,
            parent=root,
            sem="lighting_fixture",
            bevel=0.004,
        )
        area_light(
            coll,
            f"station:pendant_{i}:area",
            (x, y, 3.06),
            75,
            (0.36, 0.36),
            (1.0, 0.92, 0.78),
            (0, 0, 0),
            root,
        )

    # Back-wall service identity panel and operating notice board.
    box(
        coll,
        "station:rear_identity_panel",
        (2.5, -8.48, 2.15),
        (4.20, 0.035, 1.65),
        M["blue"],
        0.016,
        parent=root,
        sem="signage",
    )
    text_obj(
        coll,
        "station:rear_identity_text",
        "Cainiao Service Center",
        (2.5, -8.455, 2.48),
        0.345,
        M["white_emit"],
        0.016,
        parent=root,
        xscale=0.90,
        sem="signage",
    )
    for i in range(3):
        box(
            coll,
            f"station:notice_board_{i}",
            (1.30 + i * 1.18, -8.43, 1.86),
            (0.92, 0.035, 0.63),
            M["label"],
            0.008,
            parent=root,
            sem="signage",
        )
        for line in range(5):
            part_box(
                coll,
                f"station:notice_{i}:line_{line}",
                (1.30 + i * 1.18, -8.405, 2.03 - line * 0.085),
                (0.61 - line * 0.035, 0.007, 0.016),
                M["ink"],
                parent=root,
                sem="signage",
            )

    coll["c2w_modeled_parcel_count"] = parcel_total
    coll["c2w_rack_count"] = len(rack_specs)
    coll["c2w_glazed_storefront"] = True
    coll["c2w_working_interior"] = True
    coll["c2w_pos_terminal_detail_level"] = "all_in_one_operational_ui"
    coll["c2w_signage_profile"] = "enlarged_constrained_to_fascia"
    print("[delivery] parcel station: complete", flush=True)
    return coll


# ---------------------------------------------------------------------------
# Combined row, public realm, daylight cameras and production validation


def build_delivery_site(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Build a detailed paved apron shared by the three independent assets."""
    M = materials()
    coll = collection("DELIVERY_ROW_PUBLIC_REALM", parent)
    root = anchor(coll, "site_anchor", origin, yaw)
    coll["c2w_asset_type"] = "delivery_public_realm"
    site_cx, site_w, site_d = -1.35, 41.8, 18.2
    box(
        coll,
        "site:subgrade",
        (site_cx, -3.20, -0.30),
        (site_w + 1.8, site_d + 2.0, 0.65),
        M["concrete"],
        0.018,
        parent=root,
        sem="site",
    )
    box(
        coll,
        "site:paved_apron",
        (site_cx, -2.55, 0.025),
        (site_w, site_d, 0.18),
        M["concrete"],
        0.014,
        parent=root,
        sem="site",
    )
    # A real access lane continues toward the camera so wide views terminate
    # on physical ground rather than the world background below the kerb.
    box(
        coll,
        "site:foreground_access_lane",
        (site_cx, 14.65, -0.055),
        (site_w + 2.0, 16.0, 0.18),
        M["asphalt"],
        0.010,
        parent=root,
        sem="site",
    )
    part_box(
        coll,
        "site:access_lane_edge_line",
        (site_cx, 7.05, 0.042),
        (site_w - 0.25, 0.11, 0.018),
        M["white"],
        parent=root,
        sem="site_detail",
    )
    # Fine paver joints, staggered brass datum tabs and perimeter kerb.
    for i, x in enumerate([site_cx - site_w / 2 + 0.7 + i * 1.20 for i in range(34)]):
        part_box(
            coll,
            f"site:paver_joint_x_{i}",
            (x, -2.55, 0.119),
            (0.012, site_d - 0.20, 0.008),
            M["joint"],
            parent=root,
            sem="site_detail",
        )
    for i, y in enumerate([-11.10 + i * 1.20 for i in range(15)]):
        part_box(
            coll,
            f"site:paver_joint_y_{i}",
            (site_cx, y, 0.119),
            (site_w - 0.20, 0.012, 0.008),
            M["joint"],
            parent=root,
            sem="site_detail",
        )
        if i % 2:
            for x in (-15.0, -3.0, 9.0):
                part_box(
                    coll,
                    f"site:brass_datum_{i}_{x:+.0f}",
                    (x, y, 0.125),
                    (0.34, 0.028, 0.010),
                    M["steel"],
                    parent=root,
                    sem="site_detail",
                )
    box(
        coll,
        "site:front_kerb",
        (site_cx, 6.60, 0.17),
        (site_w + 0.25, 0.34, 0.34),
        M["offwhite"],
        0.025,
        parent=root,
        sem="site_detail",
    )
    box(
        coll,
        "site:rear_kerb",
        (site_cx, -11.72, 0.15),
        (site_w + 0.25, 0.22, 0.28),
        M["offwhite"],
        0.020,
        parent=root,
        sem="site_detail",
    )
    # Continuous slotted drain at the front edge.
    box(
        coll,
        "site:trench_drain_frame",
        (site_cx, 5.93, 0.15),
        (site_w - 0.30, 0.38, 0.11),
        M["charcoal"],
        0.008,
        parent=root,
        sem="site_detail",
    )
    for i, x in enumerate([site_cx - site_w / 2 + 0.22 + i * 0.24 for i in range(173)]):
        part_box(
            coll,
            f"site:drain_slot_{i}",
            (x, 5.93, 0.211),
            (0.065, 0.30, 0.018),
            M["steel"],
            parent=root,
            sem="site_detail",
        )

    # The prior revision's three yellow studded plates have been deliberately
    # removed from the public realm.  The paved apron remains continuous and
    # flush at every operating point, as requested.
    coll["c2w_yellow_ground_plate_count"] = 0

    # Stainless bollards protect projecting terminals without blocking access.
    for i, (x, y) in enumerate(
        ((-16.05, 0.58), (-9.52, 0.58), (2.55, 0.58), (5.42, 0.55), (17.40, 0.55))
    ):
        cyl(
            coll,
            f"site:bollard_{i}:post",
            (x, y, 0.58),
            0.090,
            1.08,
            M["steel"],
            24,
            parent=root,
            sem="site_detail",
            bevel=0.007,
        )
        cyl(
            coll,
            f"site:bollard_{i}:band",
            (x, y, 0.82),
            0.096,
            0.11,
            M["white"],
            24,
            parent=root,
            sem="site_detail",
            bevel=0.003,
        )
        box(
            coll,
            f"site:bollard_{i}:base",
            (x, y, 0.15),
            (0.26, 0.26, 0.045),
            M["steel"],
            0.010,
            parent=root,
            sem="site_detail",
        )
        for j, (dx, dy) in enumerate(
            ((-0.08, -0.08), (0.08, -0.08), (-0.08, 0.08), (0.08, 0.08))
        ):
            cyl(
                coll,
                f"site:bollard_{i}:anchor_{j}",
                (x + dx, y + dy, 0.184),
                0.010,
                0.030,
                M["black"],
                12,
                parent=root,
                sem="site_detail",
                bevel=0.001,
            )
    return coll


def _placed_origin(local_x, local_y, origin, yaw):
    x, y = _xy((local_x, local_y), (origin[0], origin[1]), yaw)
    return (x, y, origin[2])


def build_delivery_reference_row(
    parent=None, include_site=True, origin=(0.0, 0.0, 0.0), yaw=0.0, joint_values=None
):
    """Live pipeline entrypoint: compose the three separately modeled assets."""
    RNG.seed(260831)
    M = materials()
    row = collection("URBAN_V3_DELIVERY_REFERENCE_ROW", parent)
    row["c2w_asset_id"] = ASSET_ID
    row[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_delivery.build_delivery_reference_row"
    row["c2w_reference_driven"] = True
    row["c2w_scene_asset_inputs"] = 0
    row["c2w_separate_asset_count"] = 3
    row["c2w_layout"] = "single_expanded_row"
    food_origin = _placed_origin(FOOD_CENTER_X, 0, origin, yaw)
    # The shared presentation apron finishes 0.115 m above the row origin;
    # lift the independently grade-correct cabinet so its caster treads rest on
    # that modeled surface instead of being hidden inside it.
    if include_site:
        food_origin = (food_origin[0], food_origin[1], food_origin[2] + 0.112)
    food_asset = build_food_delivery_locker(
        row, food_origin, yaw, joint_values=joint_values, defer_physics=True
    )
    parcel_asset = build_parcel_locker(
        row,
        _placed_origin(PARCEL_CENTER_X, 0, origin, yaw),
        yaw,
        joint_values=joint_values,
        defer_physics=True,
    )
    print("[delivery] lockers: combined batch physics for 115 hinges", flush=True)
    sim_collections = [
        bpy.data.collections[str(asset["c2w_simulation_collection"])]
        for asset in (food_asset, parcel_asset)
    ]
    physics_counts = _batch_finalize_blender_physics(sim_collections)
    if physics_counts != (2, 115, 115):
        raise RuntimeError(
            f"Unexpected combined delivery physics counts: {physics_counts}"
        )
    for asset, counts in ((food_asset, (1, 59, 59)), (parcel_asset, (1, 56, 56))):
        asset["c2w_physics_registration_deferred"] = False
        asset["c2w_blender_physics_batch_counts"] = list(counts)
    build_delivery_station(row, _placed_origin(STATION_CENTER_X, 0, origin, yaw), yaw)
    if include_site:
        build_delivery_site(row, origin, yaw)
    row["c2w_articulation_standard"] = ARTICULATION_STANDARD
    row["c2w_revolute_joint_count"] = 115
    row["c2w_method_reference"] = METHOD_REFERENCE_URL
    return row, M


def setup_world():
    world = bpy.data.worlds.new(PREFIX + "physical_day_world")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(142)
    sky.altitude = 0.20
    sky.air_density = 1.05
    bg.inputs["Strength"].default_value = 0.34
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bpy.context.scene.world = world
    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 2.35
    sun_data.angle = math.radians(7.5)
    sun_data.color = (1.0, 0.91, 0.78)
    sun = bpy.data.objects.new(PREFIX + "day_sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(31), math.radians(-18), math.radians(-128))
    sun["c2w_semantic"] = "daylight"


def configure_scene(preview=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 960 if preview else 1600
    scene.render.resolution_y = 600 if preview else 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 24
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.15
    scene.view_settings.view_transform = "AgX"
    # Blender 4.5 samples are exposed directly on the scene in Eevee Next.
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 12 if preview else 24
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "shadow_pool_size"):
        scene.eevee.shadow_pool_size = "1024"
    scene.camera = None


def camera_specs():
    return [
        (
            "01_delivery_row_daylight_closed_panorama.png",
            (0.95, 34.0, 6.8),
            (0.95, -2.5, 1.78),
            35,
            "panorama_closed",
            "closed",
        ),
        (
            "02_delivery_row_daylight_open_panorama.png",
            (0.95, 34.0, 6.8),
            (0.95, -2.5, 1.78),
            35,
            "panorama_open",
            "both_open",
        ),
        (
            "03_delivery_row_open_oblique.png",
            (29.0, 28.5, 8.7),
            (-0.65, -2.3, 2.00),
            46,
            "panorama_oblique_open",
            "both_open",
        ),
        (
            "04_food_locker_closed_front.png",
            (FOOD_CENTER_X, 13.65, 3.55),
            (FOOD_CENTER_X, -0.05, 1.52),
            64,
            "food_closed",
            "closed",
        ),
        (
            "05_food_locker_open_front.png",
            (FOOD_CENTER_X, 13.65, 3.55),
            (FOOD_CENTER_X, -0.05, 1.52),
            64,
            "food_open",
            "food_open",
        ),
        (
            "06_food_hinge_closed_closeup.png",
            (-11.52, 2.55, 1.72),
            (-12.28, 0.10, 1.21),
            72,
            "food_hinge_closed",
            "closed",
        ),
        (
            "07_food_hinge_open_closeup.png",
            (-11.52, 2.55, 1.72),
            (-12.28, 0.19, 1.21),
            72,
            "food_hinge_open",
            "food_hinge_open",
        ),
        (
            "08_parcel_locker_closed_front.png",
            (PARCEL_CENTER_X, 10.5, 3.55),
            (PARCEL_CENTER_X, -0.10, 1.48),
            50,
            "parcel_closed",
            "closed",
        ),
        (
            "09_parcel_locker_open_front.png",
            (PARCEL_CENTER_X, 10.5, 3.55),
            (PARCEL_CENTER_X, -0.10, 1.48),
            50,
            "parcel_open",
            "parcel_open",
        ),
        (
            "10_parcel_hinge_closed_closeup.png",
            (-4.28, 1.08, 1.48),
            (-4.95, 0.105, 1.20),
            72,
            "parcel_hinge_closed",
            "closed",
        ),
        (
            "11_parcel_hinge_open_closeup.png",
            (-3.90, 0.60, 1.48),
            (-4.95, 0.105, 1.20),
            72,
            "parcel_hinge_open",
            "parcel_hinge_open",
        ),
        (
            "12_articulated_lockers_open_oblique_close.png",
            (-5.85, 9.20, 3.70),
            (-8.20, -0.10, 1.48),
            44,
            "lockers_open_oblique",
            "both_open",
        ),
    ]


def object_counts():
    counts = {}
    for obj in bpy.data.objects:
        sem = obj.get("c2w_semantic", "unclassified")
        counts[sem] = counts.get(sem, 0) + 1
    return dict(sorted(counts.items()))


def _asset_collections():
    result = {}
    for coll in bpy.data.collections:
        asset_type = coll.get("c2w_asset_type")
        if asset_type in {"food_delivery_locker", "parcel_locker", "parcel_station"}:
            result[asset_type] = coll
    return result


def parcel_support_audit():
    """Verify every sellable parcel rests exactly on a modeled rack shelf."""
    bpy.context.view_layer.update()
    shelves = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.get("c2w_semantic") == "rack_shelf"
    }
    parcels = [obj for obj in bpy.data.objects if obj.get("c2w_semantic") == "parcel"]
    errors = []
    worst = 0.0
    for parcel in parcels:
        support_name = parcel.get("c2w_support_name", "")
        shelf = shelves.get(support_name)
        if (
            shelf is None
            or parcel.get("c2w_support_relation") != "rests_on_modeled_shelf"
        ):
            errors.append({"object": parcel.name, "reason": "missing_modeled_shelf"})
            continue
        base_z = min(
            (parcel.matrix_world @ Vector(corner)).z for corner in parcel.bound_box
        )
        declared = float(parcel.get("c2w_support_top_z", -999.0))
        gap = base_z - declared
        worst = max(worst, abs(gap))
        if abs(gap) > 0.0015:
            errors.append(
                {
                    "object": parcel.name,
                    "reason": "floating" if gap > 0 else "penetrating",
                    "gap_m": round(gap, 6),
                }
            )
    return {
        "modeled_shelf_count": len(shelves),
        "parcel_body_count": len(parcels),
        "verified_support_count": len(parcels) - len(errors),
        "worst_absolute_gap_m": round(worst, 6),
        "error_count": len(errors),
        "sample_errors": errors[:20],
        "passed": len(parcels) >= 200 and not errors,
    }


def _world_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "xmin": min(point.x for point in corners),
        "xmax": max(point.x for point in corners),
        "zmin": min(point.z for point in corners),
        "zmax": max(point.z for point in corners),
    }


def signage_bounds_audit():
    """Verify enlarged lettering remains within its modeled sign carrier."""
    bpy.context.view_layer.update()
    pairs = [
        (
            "parcel_wordmark",
            bpy.data.objects.get(PREFIX + "parcel:fengchao_wordmark"),
            bpy.data.objects.get(PREFIX + "parcel:fengchao_sign_back"),
        ),
        (
            "parcel_terminal_brand",
            bpy.data.objects.get(PREFIX + "parcel:terminal:brand_text"),
            bpy.data.objects.get(PREFIX + "parcel:terminal:brand_header"),
        ),
        (
            "station_primary",
            bpy.data.objects.get(PREFIX + "station:primary_wordmark"),
            bpy.data.objects.get(PREFIX + "station:front_fascia_blue"),
        ),
    ]
    errors = []
    measured = {}
    for label, lettering, carrier in pairs:
        if lettering is None or carrier is None:
            errors.append({"label": label, "reason": "missing_geometry"})
            continue
        lb, cb = _world_bounds(lettering), _world_bounds(carrier)
        height = lb["zmax"] - lb["zmin"]
        measured[label] = {
            "letter_height_m": round(height, 4),
            "left_clearance_m": round(lb["xmin"] - cb["xmin"], 4),
            "right_clearance_m": round(cb["xmax"] - lb["xmax"], 4),
            "bottom_clearance_m": round(lb["zmin"] - cb["zmin"], 4),
            "top_clearance_m": round(cb["zmax"] - lb["zmax"], 4),
        }
        tolerance = 0.012
        if (
            lb["xmin"] < cb["xmin"] - tolerance
            or lb["xmax"] > cb["xmax"] + tolerance
            or lb["zmin"] < cb["zmin"] - tolerance
            or lb["zmax"] > cb["zmax"] + tolerance
        ):
            errors.append(
                {
                    "label": label,
                    "reason": "outside_carrier",
                    "measurement": measured[label],
                }
            )
    return {"measured": measured, "errors": errors, "passed": not errors}


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def method_reference_record():
    path = REFERENCES / METHOD_REFERENCE_FILE
    available = path.is_file() and path.stat().st_size > 500000
    record = {
        "title": "Procedural Generation of Articulated Simulation-Ready Assets",
        "url": METHOD_REFERENCE_URL,
        "arxiv_id": "2505.10755v3",
        "file": METHOD_REFERENCE_FILE,
        "available": available,
        "bytes": path.stat().st_size if available else 0,
        "sha256": _file_sha256(path) if available else "",
        "direct_method_reuse": [
            "infinigen.assets.utils.joints.nodegroup_hinge_joint",
            "infinigen.assets.utils.joints.nodegroup_add_jointed_geometry_metadata",
            "infinigen.core.sim.kinematic_compiler.compile",
        ],
        "implemented_principles": [
            "explicit parent-child rigid links",
            "procedurally exact revolute pivot position and axis",
            "hard joint range and dynamics metadata",
            "native URDF/USD/MJCF-compatible kinematic graph",
            "full-range collision and cabinet-front clearance sweep",
        ],
    }
    (REFERENCES / "method_reference.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return record


def compile_native_kinematic_blueprints():
    """Compile both detailed collection graphs with the paper's own compiler."""
    infinigen_root = ROOT / "infinigen"
    if str(infinigen_root) not in sys.path:
        sys.path.insert(0, str(infinigen_root))
    from infinigen.core.sim import (
        kinematic_compiler,
    )  # pylint: disable=import-outside-toplevel

    assets = {}
    for carrier in sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.get("c2w_role") == "infinigen_articulated_asset_carrier"
        ),
        key=lambda obj: obj.name,
    ):
        blueprint = kinematic_compiler.compile(carrier)
        asset_name = str(carrier.get("c2w_asset_id"))
        blueprint["name"] = asset_name
        hinge_count = sum(
            int(node.get("joint_type", -1)) == 1
            for node in blueprint.get("graph", {}).values()
        )
        expected = int(carrier.get("c2w_joint_count", 0))
        assets[asset_name] = {
            "carrier": carrier.name,
            "expected_revolute_joint_count": expected,
            "compiled_revolute_joint_count": hinge_count,
            "semantic_label_count": len(blueprint.get("labels", [])),
            "passed": hinge_count == expected and expected > 0,
            "blueprint": blueprint,
        }
    report = {
        "schema": "agent.infinigen_articulated_blueprints.v1",
        "compiler": "infinigen.core.sim.kinematic_compiler.compile",
        "asset_count": len(assets),
        "compiled_revolute_joint_count": sum(
            item["compiled_revolute_joint_count"] for item in assets.values()
        ),
        "assets": assets,
        "passed": (
            set(assets) == {"food_locker", "parcel_locker"}
            and all(item["passed"] for item in assets.values())
        ),
    }
    (OUT / "native_kinematic_blueprints.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return report


def _oriented_door_rectangle(child, angle):
    pivot = Vector(child.get("c2w_joint_pivot_local_m"))
    center = Vector(child.get("c2w_collision_center_local_m"))
    dims = child.get("c2w_collision_dimensions_m")
    half_x, half_y = float(dims[0]) / 2, float(dims[1]) / 2
    cosine, sine = math.cos(angle), math.sin(angle)
    result = []
    for dx, dy in (
        (-half_x, -half_y),
        (half_x, -half_y),
        (half_x, half_y),
        (-half_x, half_y),
    ):
        rel_x, rel_y = center.x + dx - pivot.x, center.y + dy - pivot.y
        result.append(
            (
                pivot.x + cosine * rel_x - sine * rel_y,
                pivot.y + sine * rel_x + cosine * rel_y,
            )
        )
    return result


def _polygon_axes(points):
    axes = []
    for index in range(len(points)):
        p0, p1 = points[index], points[(index + 1) % len(points)]
        nx, ny = -(p1[1] - p0[1]), p1[0] - p0[0]
        length = math.hypot(nx, ny)
        if length > 1e-9:
            axes.append((nx / length, ny / length))
    return axes


def _rectangles_penetrate(a, b, tolerance=0.001):
    for axis in _polygon_axes(a) + _polygon_axes(b):
        projection_a = [point[0] * axis[0] + point[1] * axis[1] for point in a]
        projection_b = [point[0] * axis[0] + point[1] * axis[1] for point in b]
        overlap = min(max(projection_a), max(projection_b)) - max(
            min(projection_a), min(projection_b)
        )
        if overlap <= tolerance:
            return False
    return True


def hinge_clearance_sweep(samples=13):
    """Sweep all 115 door envelopes through their full legal joint ranges."""
    controllers = sorted(
        (obj for obj in bpy.data.objects if obj.get("c2w_role") == "articulated_link"),
        key=lambda obj: str(obj.get("c2w_joint_id")),
    )
    records = []
    errors = []
    sampled_rectangles = {sample: [] for sample in range(samples)}
    for child in controllers:
        joint_id = str(child.get("c2w_joint_id"))
        pivot = Vector(child.get("c2w_joint_pivot_local_m"))
        center = Vector(child.get("c2w_door_center_local_m"))
        width = float(child.get("c2w_door_width_m"))
        side = int(child.get("c2w_hinge_side", 0))
        lower = float(child.get("c2w_joint_limit_lower_rad"))
        upper = float(child.get("c2w_joint_limit_upper_rad"))
        axis = Vector(child.get("c2w_joint_axis_local"))
        front_plane = float(child.get("c2w_front_clearance_plane_y"))
        edge_error = abs(abs(pivot.x - center.x) - width / 2)
        min_front_clearance = float("inf")
        target = lower if abs(lower) > abs(upper) else upper
        for sample in range(samples):
            fraction = sample / (samples - 1)
            angle = target * fraction
            rectangle = _oriented_door_rectangle(child, angle)
            min_front_clearance = min(
                min_front_clearance, min(point[1] for point in rectangle) - front_plane
            )
            sampled_rectangles[sample].append((child, rectangle))
        # A surface-mount barrel is intentionally centred slightly outboard
        # of the nominal sheet-metal edge.  Allow up to 25 mm (covering the
        # modeled 21 mm parcel knuckle) while still rejecting a detached or
        # implausibly remote pivot.
        surface_hinge_standoff_limit = 0.025
        passed = (
            (axis - Vector((0.0, 0.0, 1.0))).length <= 1e-7
            and edge_error <= surface_hinge_standoff_limit
            and min_front_clearance >= -0.003
            and side in {-1, 1}
            and math.radians(100.0) <= upper - lower <= math.radians(112.0)
        )
        record = {
            "joint_id": joint_id,
            "axis_local": [round(float(value), 7) for value in axis],
            "pivot_to_door_edge_error_m": round(edge_error, 6),
            "physical_surface_hinge_standoff_limit_m": surface_hinge_standoff_limit,
            "minimum_front_clearance_m": round(min_front_clearance, 6),
            "range_degrees": round(math.degrees(upper - lower), 3),
            "samples": samples,
            "passed": passed,
        }
        records.append(record)
        if not passed:
            errors.append(record)

    pair_collisions = []
    for sample, items in sampled_rectangles.items():
        for index, (first, first_rect) in enumerate(items):
            first_id = str(first.get("c2w_joint_id"))
            first_asset = first_id.split("_door_", 1)[0]
            first_center = Vector(first.get("c2w_door_center_local_m"))
            first_height = float(first.get("c2w_collision_dimensions_m")[2])
            for second, second_rect in items[index + 1 :]:
                second_id = str(second.get("c2w_joint_id"))
                if second_id.split("_door_", 1)[0] != first_asset:
                    continue
                second_center = Vector(second.get("c2w_door_center_local_m"))
                second_height = float(second.get("c2w_collision_dimensions_m")[2])
                z_overlap = min(
                    first_center.z + first_height / 2,
                    second_center.z + second_height / 2,
                ) - max(
                    first_center.z - first_height / 2,
                    second_center.z - second_height / 2,
                )
                if z_overlap > 0.001 and _rectangles_penetrate(first_rect, second_rect):
                    pair_collisions.append(
                        {
                            "sample": sample,
                            "joint_a": first_id,
                            "joint_b": second_id,
                            "z_overlap_m": round(z_overlap, 6),
                        }
                    )
    report = {
        "schema": "agent.hinge_clearance_sweep.v1",
        "joint_count": len(controllers),
        "samples_per_joint": samples,
        "evaluated_joint_poses": len(controllers) * samples,
        "failed_joint_count": len(errors),
        "inter_door_collision_count": len(pair_collisions),
        "failures": errors[:30],
        "inter_door_collisions": pair_collisions[:30],
        "records": records,
        "passed": len(controllers) == 115 and not errors and not pair_collisions,
    }
    (OUT / "hinge_clearance_sweep_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return report


def articulation_audit(native_report, clearance_report, method_reference):
    controllers = [
        obj for obj in bpy.data.objects if obj.get("c2w_role") == "articulated_link"
    ]
    constraints = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_joint_constraint"
    ]
    base_proxies = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_collision_proxy"
    ]
    carriers = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "infinigen_articulated_asset_carrier"
    ]
    moving_doors = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_semantic") in {"food_locker_door", "parcel_locker_door"}
    ]
    physical_hinges = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_physical_hinge_component") is True
    ]
    food_links = [
        obj
        for obj in controllers
        if str(obj.get("c2w_joint_id", "")).startswith("food_door_")
    ]
    parcel_links = [
        obj
        for obj in controllers
        if str(obj.get("c2w_joint_id", "")).startswith("parcel_door_")
    ]
    constraint_links_valid = all(
        obj.rigid_body_constraint is not None
        and obj.rigid_body_constraint.type == "HINGE"
        and obj.rigid_body_constraint.object1 is not None
        and obj.rigid_body_constraint.object2 is not None
        and obj.rigid_body_constraint.use_limit_ang_z
        for obj in constraints
    )
    checks = {
        "all_115_service_doors_are_independent_revolute_links": len(food_links) == 59
        and len(parcel_links) == 56,
        "every_rendered_door_leaf_is_parented_to_its_movable_link": len(moving_doors)
        == 115
        and all(
            obj.get("c2w_movable") is True
            and obj.parent is not None
            and obj.parent.get("c2w_role") == "articulated_link"
            for obj in moving_doors
        ),
        "native_blender_hinge_constraints_and_limits_complete": len(constraints) == 115
        and constraint_links_valid,
        "fixed_carcass_and_active_door_collision_links_complete": len(base_proxies) == 2
        and len(controllers) == 115
        and all(obj.rigid_body is not None for obj in base_proxies + controllers),
        "physical_interleaved_hinge_hardware_is_modeled": len(physical_hinges)
        >= 12 * 115,
        "paper_native_hinge_and_metadata_nodes_directly_reused": len(carriers) == 2
        and all(
            obj.get("c2w_direct_method_reuse") is True
            and "nodegroup_hinge_joint"
            in str(obj.get("c2w_native_hinge_nodegroup", ""))
            for obj in carriers
        ),
        "native_kinematic_compiler_accepts_both_complete_assets": bool(
            native_report
            and native_report.get("passed")
            and native_report.get("compiled_revolute_joint_count") == 115
        ),
        "hinge_axes_pivots_ranges_and_clearance_pass_full_sweep": bool(
            clearance_report
            and clearance_report.get("passed")
            and clearance_report.get("evaluated_joint_poses") == 1495
        ),
        "cited_method_paper_archived_in_workspace": bool(
            method_reference.get("available")
            and method_reference.get("bytes", 0) > 5000000
        ),
    }
    return {
        "standard": ARTICULATION_STANDARD,
        "checks": checks,
        "counts": {
            "food_revolute_links": len(food_links),
            "parcel_revolute_links": len(parcel_links),
            "hinge_constraints": len(constraints),
            "base_collision_proxies": len(base_proxies),
            "door_collision_proxies": len(controllers),
            "native_asset_carriers": len(carriers),
            "physical_hinge_components": len(physical_hinges),
            "movable_rendered_door_leaves": len(moving_doors),
        },
        "native_compile_summary": {
            "passed": bool(native_report.get("passed")),
            "compiled_revolute_joint_count": int(
                native_report.get("compiled_revolute_joint_count", 0)
            ),
        },
        "clearance_sweep_summary": {
            key: clearance_report.get(key)
            for key in (
                "passed",
                "joint_count",
                "samples_per_joint",
                "evaluated_joint_poses",
                "failed_joint_count",
                "inter_door_collision_count",
            )
        },
        "passed": all(checks.values()),
    }


def render_pose_audit():
    pairs = [
        (
            "01_delivery_row_daylight_closed_panorama.png",
            "02_delivery_row_daylight_open_panorama.png",
        ),
        ("04_food_locker_closed_front.png", "05_food_locker_open_front.png"),
        ("06_food_hinge_closed_closeup.png", "07_food_hinge_open_closeup.png"),
        ("08_parcel_locker_closed_front.png", "09_parcel_locker_open_front.png"),
        ("10_parcel_hinge_closed_closeup.png", "11_parcel_hinge_open_closeup.png"),
    ]
    records = []
    for closed_name, open_name in pairs:
        closed_path, open_path = RENDERS / closed_name, RENDERS / open_name
        available = closed_path.is_file() and open_path.is_file()
        closed_hash = _file_sha256(closed_path) if available else ""
        open_hash = _file_sha256(open_path) if available else ""
        records.append(
            {
                "closed": closed_name,
                "open": open_name,
                "closed_sha256": closed_hash,
                "open_sha256": open_hash,
                "distinct": available and closed_hash != open_hash,
            }
        )
    return {"pairs": records, "passed": all(item["distinct"] for item in records)}


def write_articulation_manifest(articulation_report, method_reference):
    joints = []
    for root in bpy.data.objects:
        encoded = root.get("c2w_kinematic_tree")
        if encoded:
            joints.extend(json.loads(str(encoded)))
    joints.sort(key=lambda record: record["joint_id"])
    document = {
        "schema": "agent.articulated_asset_manifest.v1",
        "asset_revision": OUTPUT_ID,
        "units": "meters_radians_kilograms",
        "articulation_standard": ARTICULATION_STANDARD,
        "method_reference": method_reference,
        "joint_count": len(joints),
        "joint_types": {"revolute": len(joints)},
        "pose_api": {
            "production_builder_argument": "joint_values: dict[joint_id, radians]",
            "runtime_blender_function": "generate_urban_v3_delivery.apply_articulation_pose",
            "closed_value_rad": 0.0,
        },
        "native_export_bridge": {
            "formats": ["URDF", "USD", "MJCF"],
            "compiler_output": "native_kinematic_blueprints.json",
            "source_nodegroup": "infinigen.assets.utils.joints.nodegroup_hinge_joint",
            "detailed_visual_geometry": True,
            "separate_collision_proxies": True,
        },
        "audit": articulation_report,
        "joints": joints,
    }
    (OUT / "articulation_manifest.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return document


def requested_refinement_audit():
    """Audit delivery5's bright-white, large-clear-glass food-locker refinement."""
    assets = _asset_collections()
    food = assets.get("food_delivery_locker")
    parcel = assets.get("parcel_locker")
    names = [obj.name for obj in bpy.data.objects]
    food_doors = [
        obj for obj in bpy.data.objects if obj.get("c2w_semantic") == "food_locker_door"
    ]
    white_doors = [
        obj
        for obj in food_doors
        if obj.get("c2w_reference_door_style")
        == "bright_white_nonmetal_powdercoat_frame_with_large_clear_center_glass"
        and obj.get("c2w_white_door_leaf") is True
        and obj.get("c2w_bright_white_nonmetal_finish") is True
        and obj.get("c2w_door_metallic") == 0.0
        and obj.get("c2w_true_center_opening") is True
        and obj.active_material is not None
        and obj.active_material.name.endswith("mat:food_door_hygienic_white_powdercoat")
    ]
    food_windows = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_clear_tempered_glass") is True
        and obj.get("c2w_transmission_weight", 0.0) >= 0.95
        and obj.get("c2w_uninterrupted_center_glazing") is True
        and obj.get("c2w_glass_width_ratio", 0.0) >= 0.80
        and obj.get("c2w_glass_height_ratio", 0.0) >= 0.76
        and obj.active_material is not None
        and obj.active_material.surface_render_method == "BLENDED"
        and obj.active_material.name.endswith("mat:food_door_clear_tempered_glass")
    ]
    food_numbers = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_legible_compartment_number") is True
        and obj.get("c2w_number_printed_on_glass") is True
        and obj.get("c2w_black_ceramic_ink") is True
        and obj.get("c2w_nominal_font_size_m", 0.0) >= 0.155
        and obj.active_material is not None
        and obj.active_material.name.endswith("mat:food_glass_number_black_ceramic_ink")
        and ":food:door_" in obj.name
    ]
    food_number_keylines = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_black_number_contrast_keyline") is True
        and ":food:door_" in obj.name
    ]
    vertical_glass_bars = [
        obj
        for obj in bpy.data.objects
        if ":food:door_" in obj.name
        and any(
            token in obj.name
            for token in (
                ":glass_edge_glint",
                ":glass_vertical_bar",
                ":glass_highlight_strip",
            )
        )
    ]
    parcel_numbers = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_legible_compartment_number") is True
        and ":parcel:door_" in obj.name
    ]
    food_ui = [name for name in names if ":food:terminal:" in name]
    parcel_ui = [name for name in names if ":parcel:terminal:" in name]
    station_ui = [name for name in names if ":station:pos:" in name]
    casters = [name for name in names if ":food:caster_" in name and ":wheel" in name]
    leveling_feet = [
        name for name in names if ":food:leveling_foot_" in name and ":pad" in name
    ]
    food_contents = [
        obj for obj in bpy.data.objects if obj.get("c2w_semantic") == "locker_contents"
    ]
    obsolete_food_materials = [
        mat.name
        for mat in bpy.data.materials
        if "food_door_graphite" in mat.name
        or "food_window_frosted" in mat.name
        or "food_glass_number_white_ink" in mat.name
        or "tempered_glass_edge_glint" in mat.name
    ]
    compartment_numbers = sorted(
        int(obj.get("c2w_compartment_number")) for obj in food_doors
    )
    expected_numbers = [number for number in range(2, 62) if number != 8]
    yellow_ground = [name for name in names if ":site:tactile_" in name]
    bounds = signage_bounds_audit()
    station_sign = bpy.data.objects.get(PREFIX + "station:primary_wordmark")
    station_body = (
        station_sign.data.body
        if station_sign is not None and station_sign.type == "FONT"
        else ""
    )
    station_measurement = bounds["measured"].get("station_primary", {})
    checks = {
        "no_yellow_ground_building_plates": not yellow_ground,
        "food_locker_has_requested_ten_by_six_layout": len(food_doors) == 59
        and food is not None
        and food.get("c2w_column_count", 0) == 10
        and food.get("c2w_row_count", 0) == 6
        and food.get("c2w_compartment_count", 0) == 59
        and food.get("c2w_terminal_count", 0) == 1,
        "every_food_door_is_bright_white_nonmetal_powdercoat_with_real_center_opening": len(
            white_doors
        )
        == len(food_doors)
        and food.get("c2w_white_powdercoat_door_count", 0) == len(food_doors),
        "every_food_door_has_large_uninterrupted_clear_transmissive_center_glass": len(
            food_windows
        )
        == len(food_doors)
        and food is not None
        and food.get("c2w_clear_tempered_glass_count", 0) == len(food_doors)
        and food.get("c2w_large_glazing_width_ratio", 0.0) >= 0.80
        and food.get("c2w_large_glazing_height_ratio", 0.0) >= 0.76,
        "every_food_number_is_large_black_print_on_glass": len(food_numbers)
        == len(food_doors)
        and len(food_number_keylines) == len(food_doors)
        and food.get("c2w_glass_number_count", 0) == len(food_doors),
        "food_glazing_has_no_vertical_bar_or_glint_geometry": not vertical_glass_bars
        and food.get("c2w_vertical_glass_bar_count", -1) == 0,
        "food_compartment_number_sequence_is_complete": compartment_numbers
        == expected_numbers,
        "clear_glazing_reveals_modeled_compartment_contents": len(food_contents) >= 60
        and food.get("c2w_visible_insulated_bag_count", 0) >= 15,
        "obsolete_graphite_and_frosted_food_materials_removed": not obsolete_food_materials,
        "wide_food_locker_has_modeled_distributed_supports": len(casters) == 6
        and len(leveling_feet) == 4
        and food.get("c2w_caster_count", 0) == 6
        and food.get("c2w_leveling_foot_count", 0) == 4,
        "every_parcel_door_has_enlarged_number": len(parcel_numbers) >= 56
        and parcel is not None
        and parcel.get("c2w_numbered_compartment_count", 0) == len(parcel_numbers),
        "food_terminal_has_modeled_operational_interface": len(food_ui) >= 55,
        "parcel_terminal_has_portrait_operational_interface": len(parcel_ui) >= 150,
        "station_pos_has_all_in_one_operational_interface": len(station_ui) >= 115,
        "station_front_signage_is_english_only": station_body
        == "CAINIAO PARCEL STATION"
        and station_body.isascii(),
        "station_primary_signage_is_enlarged_for_far_view": station_sign is not None
        and station_sign.get("c2w_enlarged_for_far_view") is True
        and station_measurement.get("letter_height_m", 0.0) >= 0.30,
        "enlarged_signage_remains_inside_carriers": bounds["passed"],
    }
    return {
        "checks": checks,
        "counts": {
            "yellow_ground_plate_parts": len(yellow_ground),
            "food_white_powdercoat_doors": len(white_doors),
            "food_clear_tempered_windows": len(food_windows),
            "food_glass_printed_numbers": len(food_numbers),
            "food_glass_number_contrast_keylines": len(food_number_keylines),
            "food_glass_vertical_bars": len(vertical_glass_bars),
            "food_compartment_content_parts": len(food_contents),
            "obsolete_food_materials": len(obsolete_food_materials),
            "food_caster_wheels": len(casters),
            "food_leveling_feet": len(leveling_feet),
            "parcel_enlarged_numbers": len(parcel_numbers),
            "food_terminal_parts": len(food_ui),
            "parcel_terminal_parts": len(parcel_ui),
            "station_pos_parts": len(station_ui),
        },
        "signage_bounds": bounds,
        "passed": all(checks.values()),
    }


def validate(
    row, cameras, native_report, clearance_report, method_reference, rendered=False
):
    counts = object_counts()
    assets = _asset_collections()
    support = parcel_support_audit()
    refinement = requested_refinement_audit()
    articulation = articulation_audit(native_report, clearance_report, method_reference)
    pose_audit = render_pose_audit() if rendered else {"pairs": [], "passed": True}
    names = [obj.name.lower() for obj in bpy.data.objects]
    forbidden = [
        name
        for name in names
        if any(token in name for token in ("toy", "placeholder", "dummy", "lowpoly"))
    ]
    reference_sizes = {
        filename: (REFERENCES / filename).stat().st_size
        if (REFERENCES / filename).is_file()
        else 0
        for filename in REFERENCE_URLS
    }
    render_sizes = {
        filename: (RENDERS / filename).stat().st_size
        if (RENDERS / filename).is_file()
        else 0
        for filename, *_ in camera_specs()
    }
    asset_object_counts = {key: len(coll.all_objects) for key, coll in assets.items()}
    checks = {
        "three_independently_modeled_asset_collections": set(assets)
        == {"food_delivery_locker", "parcel_locker", "parcel_station"}
        and all(coll.get("c2w_independent_builder") for coll in assets.values()),
        "single_expanded_row_composition": row.get("c2w_layout")
        == "single_expanded_row"
        and row.get("c2w_separate_asset_count") == 3,
        "detailed_food_locker_door_grid": counts.get("food_locker_door", 0) == 59
        and counts.get("food_locker_window", 0) == 59
        and counts.get("locker_contents", 0) >= 60
        and assets.get("food_delivery_locker", {}).get("c2w_column_count", 0) == 10
        and assets.get("food_delivery_locker", {}).get("c2w_terminal_count", 0) == 1,
        "detailed_parcel_locker_door_grid": counts.get("parcel_locker_door", 0) >= 56
        and assets.get("parcel_locker", {}).get("c2w_canopy_post_count", 0) >= 7,
        "individual_locker_hardware": counts.get("locker_hardware", 0) >= 1200,
        "glazed_station_with_open_real_door": counts.get("glazing", 0) >= 10
        and counts.get("door_glazing", 0) >= 2,
        "complete_industrial_rack_system": counts.get("rack_shelf", 0) >= 19
        and counts.get("rack_structure", 0) >= 100
        and counts.get("rack_detail", 0) >= 500,
        "dense_varied_station_inventory": counts.get("parcel", 0) >= 200
        and counts.get("shipping_label", 0) >= 200
        and counts.get("parcel_detail", 0) >= 1400,
        "all_parcels_physically_supported": support["passed"],
        "complete_counter_and_workstation": counts.get("workstation", 0) >= 65
        and counts.get("counter", 0) >= 3
        and counts.get("counter_detail", 0) >= 10,
        "modeled_operational_and_safety_equipment": counts.get("equipment", 0) >= 8
        and counts.get("safety_equipment", 0) >= 3,
        "modeled_interior_lighting": counts.get("lighting_fixture", 0) >= 28
        and counts.get("lighting", 0) >= 11,
        "reference_images_archived_in_workspace": min(
            reference_sizes.values(), default=0
        )
        > 4000,
        "daylight_open_closed_panorama_and_closeup_camera_set": len(cameras) == 12
        and {spec[4] for spec in camera_specs()}
        >= {
            "panorama_closed",
            "panorama_open",
            "food_closed",
            "food_open",
            "food_hinge_closed",
            "food_hinge_open",
            "parcel_closed",
            "parcel_open",
            "parcel_hinge_closed",
            "parcel_hinge_open",
        },
        "production_generator_metadata": row.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_delivery.build_delivery_reference_row",
        "no_scene_asset_input_blends": row.get("c2w_scene_asset_inputs") == 0,
        "no_placeholder_or_toy_named_assets": not forbidden,
        "all_three_assets_are_complex": asset_object_counts.get(
            "food_delivery_locker", 0
        )
        >= 2100
        and asset_object_counts.get("parcel_locker", 0) >= 1400
        and asset_object_counts.get("parcel_station", 0) >= 2500,
        "delivery5_appearance_baseline_preserved": refinement["passed"],
        "all_food_and_parcel_doors_are_simulation_ready": articulation["passed"],
    }
    if rendered:
        checks["all_twelve_render_artifacts_nonempty"] = (
            len(render_sizes) == 12 and min(render_sizes.values(), default=0) > 18000
        )
        checks["paired_open_closed_render_artifacts_are_distinct"] = pose_audit[
            "passed"
        ]
    return {
        "schema": "agent.urban_asset_manifest.v3",
        "generator": str(Path(__file__).resolve()),
        "runner": str((ROOT / "scripts/run_urban_v3_delivery.sh").resolve()),
        "output": str(OUT),
        "blend": str(BLEND),
        "pipeline_asset_id": ASSET_ID,
        "output_revision_id": OUTPUT_ID,
        "pipeline_connected": True,
        "pipeline_entrypoint": "generate_urban_v3_delivery.build_delivery_reference_row",
        "pipeline_adapter": "urban_assets.build_delivery_reference_row",
        "independent_entrypoints": [
            "generate_urban_v3_delivery.build_food_delivery_locker",
            "generate_urban_v3_delivery.build_parcel_locker",
            "generate_urban_v3_delivery.build_delivery_station",
        ],
        "rebuild_command": "bash scripts/run_urban_v3_delivery.sh",
        "reference_urls": REFERENCE_URLS,
        "reference_files": reference_sizes,
        "reference_observations": {
            "food_locker": "expanded ten-column yellow carcass with 59 independently hinged bright-white powder-coated framed glass doors, exact edge pivots, modeled interleaved hinge hardware, recessed insulated cavities, thermal bags, distributed casters and leveling feet",
            "parcel_locker": "long lime-green Fengchao grid with 56 independently hinged steel doors, hollow lined parcel cavities and stored packages, supplied-reference portrait terminal and continuous charcoal steel rain canopy",
            "station_exterior": "cyan fascia with enlarged English-only CAINIAO PARCEL STATION lettering, black aluminum glazed corner, visible parcel inventory",
            "station_interior": "ribbed metal shell, blue industrial racks, blue-white service counter and supplied-reference all-in-one POS terminal",
        },
        "asset_object_counts": asset_object_counts,
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "semantic_counts": counts,
        "parcel_support_audit": support,
        "requested_refinement_audit": refinement,
        "articulation_audit": articulation,
        "method_reference": method_reference,
        "native_kinematic_blueprints": {
            "file": "native_kinematic_blueprints.json",
            "passed": native_report["passed"],
            "asset_count": native_report["asset_count"],
            "compiled_revolute_joint_count": native_report[
                "compiled_revolute_joint_count"
            ],
        },
        "hinge_clearance_sweep": {
            "file": "hinge_clearance_sweep_report.json",
            **{
                key: clearance_report[key]
                for key in (
                    "passed",
                    "joint_count",
                    "samples_per_joint",
                    "evaluated_joint_poses",
                    "failed_joint_count",
                    "inter_door_collision_count",
                )
            },
        },
        "render_pose_audit": pose_audit,
        "render_views": [
            {
                "file": filename,
                "role": role,
                "pose": pose,
                "bytes": render_sizes[filename],
                "sha256": (
                    _file_sha256(RENDERS / filename) if render_sizes[filename] else ""
                ),
            }
            for filename, _loc, _target, _lens, role, pose in camera_specs()
        ],
        "render_settings": {
            "engine": "BLENDER_EEVEE_NEXT",
            "resolution": [1600, 1000],
            "samples": 24,
            "shadow_pool_mb": 1024,
            "attached_paper_microdetails_cast_independent_shadows": False,
            "daylight": True,
            "color_management": "AgX - Medium High Contrast",
        },
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }


def render_all(cameras):
    scene = bpy.context.scene
    selected = {
        item.strip()
        for item in os.environ.get("C2W_DELIVERY_VIEW_FILTER", "").split(",")
        if item.strip()
    }
    try:
        for filename, cam, role, pose in cameras:
            if selected and not any(filename.startswith(prefix) for prefix in selected):
                continue
            apply_articulation_pose(articulation_render_pose(pose), render_control=True)
            print(f"[delivery] rendering {role} pose={pose}: {filename}", flush=True)
            scene.camera = cam
            scene.render.filepath = str(RENDERS / filename)
            bpy.ops.render.render(write_still=True)
    finally:
        # The saved production asset remains a dynamic, closed-door assembly;
        # render-time kinematic control never leaks into simulation state.
        apply_articulation_pose({}, render_control=False)


def main():
    print("[delivery] starting production generator", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    REFERENCES.mkdir(parents=True, exist_ok=True)
    missing = [
        filename
        for filename in REFERENCE_URLS
        if not (REFERENCES / filename).is_file()
        or (REFERENCES / filename).stat().st_size <= 4000
    ]
    if missing:
        raise FileNotFoundError(
            "Missing archived user reference images in workspace: " + ", ".join(missing)
        )
    for stale in (
        OUT / "SUCCESS",
        OUT / "manifest.json",
        OUT / "quality_report.json",
        OUT / "FAILED_AUDIT.json",
        OUT / "articulation_manifest.json",
        OUT / "native_kinematic_blueprints.json",
        OUT / "hinge_clearance_sweep_report.json",
    ):
        stale.unlink(missing_ok=True)
    preview = os.environ.get("C2W_DELIVERY_PREVIEW", "0") == "1"
    build_only = os.environ.get("C2W_DELIVERY_BUILD_ONLY", "0") == "1"
    finalize_existing = os.environ.get("C2W_DELIVERY_FINALIZE_EXISTING", "0") == "1"
    partial = bool(os.environ.get("C2W_DELIVERY_VIEW_FILTER", "").strip())
    reset_scene()
    print("[delivery] building three independent procedural assets", flush=True)
    row, _ = build_delivery_reference_row()
    setup_world()
    configure_scene(preview)
    cameras = []
    for filename, loc, target, lens, role, pose in camera_specs():
        cameras.append((filename, camera(filename[:-4], loc, target, lens), role, pose))
    method_reference = method_reference_record()
    print(
        "[delivery] compiling native Infinigen-Articulated kinematic graphs", flush=True
    )
    native_report = compile_native_kinematic_blueprints()
    print("[delivery] sweeping all hinge ranges for clearance", flush=True)
    clearance_report = hinge_clearance_sweep()
    initial = validate(
        row, cameras, native_report, clearance_report, method_reference, rendered=False
    )
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_runner"] = str(
        (ROOT / "scripts/run_urban_v3_delivery.sh").resolve()
    )
    scene["c2w_asset_id"] = ASSET_ID
    scene["c2w_domain"] = "urban_delivery"
    scene["c2w_reference_driven"] = True
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_delivery.build_delivery_reference_row"
    scene["c2w_quality_profile"] = "reference_grade_procedural_modeled_detail"
    scene["c2w_articulation_standard"] = ARTICULATION_STANDARD
    scene["c2w_revolute_joint_count"] = 115
    scene["c2w_method_reference"] = METHOD_REFERENCE_URL
    scene["c2w_manifest"] = json.dumps(initial, ensure_ascii=False)
    (OUT / "build_audit.json").write_text(
        json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8"
    )
    failed_initial = [key for key, passed in initial["checks"].items() if not passed]
    if failed_initial:
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8"
        )
        raise RuntimeError(
            "Delivery production build audit failed: " + ", ".join(failed_initial)
        )
    write_articulation_manifest(initial["articulation_audit"], method_reference)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    if build_only:
        print(
            json.dumps(
                {
                    "status": "BUILD_ONLY_COMPLETE",
                    "output": str(OUT),
                    "objects": initial["object_count"],
                    "support": initial["parcel_support_audit"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return
    if not finalize_existing:
        render_all(cameras)
    if preview or partial:
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
        print(
            json.dumps(
                {"status": "PREVIEW_COMPLETE", "output": str(OUT)}, ensure_ascii=False
            ),
            flush=True,
        )
        return
    final = validate(
        row, cameras, native_report, clearance_report, method_reference, rendered=True
    )
    failed = [key for key, passed in final["checks"].items() if not passed]
    if failed:
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8"
        )
        raise RuntimeError(
            "Delivery production render audit failed: " + ", ".join(failed)
        )
    scene["c2w_manifest"] = json.dumps(final, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    (OUT / "manifest.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8"
    )
    quality = {
        "result": "PASS",
        "all_checks_passed": True,
        "checks": final["checks"],
        "semantic_counts": final["semantic_counts"],
        "asset_object_counts": final["asset_object_counts"],
        "parcel_support_audit": final["parcel_support_audit"],
        "requested_refinement_audit": final["requested_refinement_audit"],
        "articulation_audit": final["articulation_audit"],
        "hinge_clearance_sweep": final["hinge_clearance_sweep"],
        "native_kinematic_blueprints": final["native_kinematic_blueprints"],
        "render_pose_audit": final["render_pose_audit"],
        "method_reference": final["method_reference"],
        "reference_observations": final["reference_observations"],
        "note": "Quality gates require detailed geometry, explicit physical links, native joint compilation, full-range hinge clearance, supported parcels and paired open/closed visual evidence; raw object count alone is not accepted.",
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf8"
    )
    write_articulation_manifest(final["articulation_audit"], method_reference)
    (OUT / "SUCCESS").write_text(
        f"{OUTPUT_ID} production generation and validation complete\n", encoding="utf8"
    )
    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "output": str(OUT),
                "objects": final["object_count"],
                "checks": final["checks"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
