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

from pathlib import Path as _AssetPath
_ASSET_PROJECT_ROOT = next(p for p in _AssetPath(__file__).resolve().parents if (p / "worldbridge").is_dir())


import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(str(_ASSET_PROJECT_ROOT))
ASSET_ID = "urban_v3_delivery"
# Keep the logical pipeline asset id stable while publishing this requested
# refinement as a new, reproducible output revision.
OUTPUT_ID = os.environ.get("C2W_DELIVERY_OUTPUT_ID", "urban_v3_delivery5")
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
}

# The ten-column food cabinet is wider than the previous five-column revision.
# Its center is shifted left so the cabinet and the parcel-locker canopy retain
# a physically credible service gap in the combined production composition.
FOOD_CENTER_X = -12.80
PARCEL_CENTER_X = -3.2
STATION_CENTER_X = 11.6

_MATERIALS: dict[str, bpy.types.Material] = {}
_PART_MESHES: dict[tuple, bpy.types.Mesh] = {}


# ---------------------------------------------------------------------------
# Core scene, geometry and material helpers

def set_prefix(value: str):
    """Set the namespace used when the generator is embedded in another scene."""
    global PREFIX
    PREFIX = value


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIALS.clear()
    _PART_MESHES.clear()


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
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def box(coll, name, loc, dims, material, bevel=.012, rot=(0.0, 0.0, 0.0),
        parent=None, sem="fixture", detail=None):
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
        mod.segments = 2 if bevel >= .008 else 1
        mod.limit_method = "ANGLE"
    if detail is None:
        detail = sem in {
            "locker_hardware", "signage", "rack_detail", "workstation",
            "parcel_detail", "lighting_fixture", "architectural_detail",
        }
    return semantic(obj, sem, detail)


def front_frame(coll, name, loc, outer_dims, opening_dims, depth, material,
                bevel=.010, parent=None, sem="fixture", detail=True):
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
        raise ValueError("Frame opening must be positive and smaller than outer dimensions")

    verts = []
    for y in (-half_y, half_y):
        verts.extend([
            (-outer_x, y, -outer_z), (outer_x, y, -outer_z),
            (outer_x, y, outer_z), (-outer_x, y, outer_z),
            (-inner_x, y, -inner_z), (inner_x, y, -inner_z),
            (inner_x, y, inner_z), (-inner_x, y, inner_z),
        ])
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


def tapered_box(coll, name, loc, bottom_dims, top_dims, height, material,
                bevel=.010, rot=(0.0, 0.0, 0.0), parent=None,
                sem="fixture", detail=True):
    """Create a manufactured tapered housing instead of a blocky stand-in."""
    bx, by = (float(v) / 2 for v in bottom_dims)
    tx, ty = (float(v) / 2 for v in top_dims)
    hz = float(height) / 2
    verts = [
        (-bx, -by, -hz), (bx, -by, -hz), (bx, by, -hz), (-bx, by, -hz),
        (-tx, -ty, hz), (tx, -ty, hz), (tx, ty, hz), (-tx, ty, hz),
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
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


def part_box(coll, name, loc, dims, material, rot=(0.0, 0.0, 0.0),
             parent=None, sem="fixture", detail=True):
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


def cyl(coll, name, loc, radius, depth, material, vertices=24,
        rot=(0.0, 0.0, 0.0), parent=None, sem="fixture", bevel=.004):
    verts = []
    for z in (-depth / 2, depth / 2):
        verts.extend(
            (radius * math.cos(math.tau * i / vertices),
             radius * math.sin(math.tau * i / vertices), z)
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


def text_obj(coll, name, body, loc, size, material, extrude=.018,
             align="CENTER", parent=None, xscale=1.0, rot=(math.pi / 2, 0.0, 0.0),
             sem="signage", bold=True):
    cu = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    cu.body = body
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = min(.006, extrude * .22)
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


def tilted_ui_box(coll, name, center, dx, dz, dims, material, tilt, parent,
                  front_offset=.070, depth=.006, sem="terminal_ui"):
    loc = _tilted_front_point(center, dx, dz, front_offset, tilt)
    return box(coll, name, loc, (dims[0], depth, dims[1]), material,
               min(.004, depth * .45), (tilt, 0.0, 0.0), parent, sem)


def tilted_ui_text(coll, name, body, center, dx, dz, size, material, tilt,
                   parent, xscale=1.0, front_offset=.079, align="CENTER",
                   sem="terminal_ui", bold=True):
    loc = _tilted_front_point(center, dx, dz, front_offset, tilt)
    return text_obj(
        coll, name, body, loc, size, material, .0015, align, parent, xscale,
        (math.pi / 2 + tilt, 0.0, 0.0), sem, bold)


def qr_code(coll, name, center, size, y, dark_material, light_material,
            parent, modules=13, sem="terminal_ui"):
    """Build a deterministic physical QR-like matrix with finder patterns."""
    cx, cz = center
    box(coll, f"{name}:paper", (cx, y, cz), (size, .006, size),
        light_material, .003, parent=parent, sem=sem)
    cell = size / modules

    def finder(ix, iz, ox, oz):
        dx, dz = ix - ox, iz - oz
        if 0 <= dx < 5 and 0 <= dz < 5:
            return dx in {0, 4} or dz in {0, 4} or (1 < dx < 4 and 1 < dz < 4)
        return False

    for iz in range(modules):
        for ix in range(modules):
            fixed = (finder(ix, iz, 0, 0) or
                     finder(ix, iz, modules - 5, 0) or
                     finder(ix, iz, 0, modules - 5))
            payload = ((ix * 17 + iz * 31 + ix * iz * 3) % 11) < 5
            if not (fixed or payload):
                continue
            x = cx - size / 2 + (ix + .5) * cell
            z = cz + size / 2 - (iz + .5) * cell
            part_box(coll, f"{name}:module_{ix:02d}_{iz:02d}",
                     (x, y + .006, z), (cell * .82, .005, cell * .82),
                     dark_material, parent=parent, sem=sem)


def area_light(coll, name, loc, energy, size, color=(1.0, .94, .84),
               rot=(0.0, 0.0, 0.0), parent=None):
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
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    obj["c2w_semantic"] = "camera"
    return obj


def _principled(name, color, rough=.45, metal=0.0, emission=None,
                emission_strength=0.0, alpha=1.0):
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


def _powdercoat(name, color_a, color_b, roughness=.34, scale=120.0):
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
    noise.inputs["Roughness"].default_value = .52
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .030
    bump.inputs["Distance"].default_value = .0012
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = .30
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


def _paint(name, color_a, color_b, rough=.30, metal=.55, scale=8.0):
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
    noise.inputs["Roughness"].default_value = .62
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .055
    bump.inputs["Distance"].default_value = .025
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
    noise.inputs["Roughness"].default_value = .78
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .14
    bump.inputs["Distance"].default_value = .035
    bsdf.inputs["Roughness"].default_value = .82
    links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _glass(name="architectural_glass", tint=(.18, .44, .58), alpha=.30,
           transmission=.72, roughness=.055):
    full = PREFIX + "mat:" + name
    old = bpy.data.materials.get(full)
    if old:
        return old
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = .0
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
    M["yellow"] = _paint("food_yellow", (.90, .56, .025), (1.0, .72, .06), .28, .58, 10)
    M["yellow_dark"] = _paint("food_yellow_dark", (.62, .32, .015), (.82, .48, .02), .34, .62, 12)
    # Delivery5 uses genuinely non-metallic bright-white polyester powder coat.
    # The narrow value range preserves subtle formed-edge highlights while
    # eliminating the grey/brushed-metal read of the preceding revision.
    M["food_door_white"] = _powdercoat(
        "food_door_hygienic_white_powdercoat",
        (.925, .945, .958), (.985, .990, .995), .33, 135.0)
    M["food_door_white_edge"] = _powdercoat(
        "food_door_white_folded_edge",
        (.855, .875, .892), (.945, .955, .965), .37, 145.0)
    M["food_cavity_white"] = _principled(
        "food_compartment_hygienic_liner", (.70, .73, .72), .48, .025)
    M["food_clear_glass"] = _glass(
        "food_door_clear_tempered_glass", (.925, .970, 1.0), .12, .96, .018)
    # Each pane is isolated and non-overlapping, so ordered alpha blending is
    # both stable and markedly cleaner than stochastic dithering in close-ups.
    M["food_clear_glass"].surface_render_method = "BLENDED"
    M["food_clear_glass"].use_transparency_overlap = False
    M["food_glass_print"] = _principled(
        "food_glass_number_black_ceramic_ink", (.003, .004, .005), .48, .0)
    M["food_glass_number_keyline"] = _principled(
        "food_glass_number_pale_contrast_keyline", (.88, .90, .91), .52, .0)
    M["white_metal"] = _paint("warm_white_metal", (.76, .77, .74), (.94, .95, .91), .34, .48, 12)
    M["door_warm"] = _paint("locker_door_warm", (.76, .72, .67), (.91, .87, .79), .38, .42, 16)
    M["green"] = _paint("fengchao_green", (.29, .63, .045), (.50, .82, .09), .33, .52, 13)
    M["green_alt"] = _paint("fengchao_green_alt", (.22, .50, .035), (.43, .73, .075), .36, .48, 15)
    M["blue"] = _paint("cainiao_blue", (.015, .34, .66), (.02, .56, .88), .27, .40, 10)
    M["cyan_emit"] = _principled("cyan_sign", (.02, .64, .92), .24, .12, (.01, .56, 1.0), 1.4)
    M["charcoal"] = _paint("charcoal_powdercoat", (.025, .032, .035), (.075, .085, .09), .25, .78, 8)
    M["black"] = _principled("black_hardware", (.012, .015, .018), .27, .76)
    M["rubber"] = _principled("rubber_gasket", (.008, .009, .008), .72, .0)
    M["steel"] = _paint("brushed_stainless", (.35, .38, .39), (.72, .75, .76), .19, .92, 24)
    M["aluminium"] = _paint("anodized_aluminium", (.12, .14, .15), (.23, .26, .27), .24, .88, 18)
    M["screen"] = _principled("screen_glass", (.008, .035, .055), .055, .18, (.015, .30, .62), 1.8)
    M["screen_ui"] = _principled("screen_ui", (.02, .55, .88), .22, .0, (.01, .42, .92), 2.8)
    M["ui_white"] = _principled("screen_ui_white", (.82, .85, .82), .30, .0,
                                 (.80, .86, .88), 1.15)
    M["ui_pale"] = _principled("screen_ui_pale", (.55, .68, .72), .34, .0,
                                (.36, .52, .58), .65)
    M["ui_navy"] = _principled("screen_ui_navy", (.012, .055, .105), .23, .06,
                                (.01, .10, .22), 1.25)
    M["ui_teal"] = _principled("screen_ui_teal", (.015, .43, .44), .28, .0,
                                (.01, .48, .50), 1.55)
    M["ui_yellow"] = _principled("screen_ui_yellow", (.88, .58, .025), .30, .0,
                                  (1.0, .56, .01), 1.0)
    M["ui_gray"] = _principled("screen_ui_gray", (.24, .29, .31), .44, .0)
    M["led_green"] = _principled("status_green", (.01, .36, .03), .18, .0, (.01, .95, .04), 5.0)
    M["led_red"] = _principled("status_red", (.45, .01, .005), .18, .0, (1.0, .015, .005), 5.0)
    M["white_emit"] = _principled("white_emission", (.82, .90, 1.0), .16, .0, (.85, .94, 1.0), 4.0)
    M["white"] = _principled("clean_white", (.88, .90, .91), .43, .08)
    M["offwhite"] = _principled("counter_solid_surface", (.78, .81, .82), .25, .04)
    M["glass"] = _glass()
    M["glass_dark"] = _glass("smoked_glass", (.035, .09, .12))
    M["locker_glass"] = _glass("food_locker_tempered_glass", (.48, .58, .60),
                                .0, .98, .015)
    M["etched_glass"] = _glass("etched_number_glass", (.72, .75, .72),
                                .48, .52, .20)
    M["compartment_inner"] = _principled("food_compartment_inner", (.050, .060, .062),
                                          .52, .46)
    M["thermal_box"] = _principled("food_thermal_container", (.52, .54, .50),
                                    .58, .08)
    M["thermal_white"] = _principled(
        "food_thermal_container_white", (.72, .74, .69), .54, .06,
        (.42, .44, .40), .34)
    M["thermal_yellow"] = _principled(
        "food_thermal_container_yellow", (.82, .48, .025), .46, .10,
        (.62, .28, .008), .38)
    M["cardboard_a"] = _cardboard("corrugated_kraft_a", (.30, .19, .095), (.57, .39, .20))
    M["cardboard_b"] = _cardboard("corrugated_kraft_b", (.46, .32, .16), (.70, .54, .31))
    M["cardboard_c"] = _cardboard("corrugated_white", (.62, .60, .53), (.86, .84, .74))
    M["tape"] = _principled("packing_tape", (.60, .44, .20), .34, .0)
    M["label"] = _principled("shipping_label", (.89, .89, .84), .72, .0)
    M["ink"] = _principled("printed_ink", (.012, .014, .015), .72, .0)
    M["floor"] = _principled("epoxy_floor", (.63, .70, .73), .31, .08)
    M["concrete"] = _cardboard("pavement_concrete", (.32, .34, .34), (.55, .57, .56))
    M["asphalt"] = _cardboard("access_lane_asphalt", (.012, .016, .018), (.055, .064, .068))
    M["joint"] = _principled("paving_joint", (.055, .06, .06), .82, .05)
    M["tactile"] = _principled("tactile_yellow", (.86, .54, .025), .68, .10)
    M["red"] = _paint("safety_red", (.42, .012, .006), (.78, .035, .012), .30, .55, 10)
    return M


def _front_screw(coll, name, x, y, z, mat, parent, radius=.018):
    return cyl(coll, name, (x, y, z), radius, .012, mat, 16,
               (math.pi / 2, 0.0, 0.0), parent, "locker_hardware", .002)


def _hex_logo(coll, name, loc, radius, depth, mat, parent, rot=(math.pi / 2, 0.0, 0.0)):
    return cyl(coll, name, loc, radius, depth, mat, 6, rot, parent, "signage", .002)


# ---------------------------------------------------------------------------
# Asset 1: insulated food-delivery locker wall

def build_food_delivery_locker(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Build a ten-column, white-door food locker as a production asset.

    Every service leaf is a real powder-coated frame surrounding clear
    tempered glazing.  The opening exposes a modeled insulated compartment,
    rather than a solid panel masquerading as glass; ceramic numbers sit on
    the outer glass face.  Six stacked rows and one integrated terminal yield
    59 individually numbered doors across ten columns.
    """
    M = materials()
    coll = collection("FOOD_DELIVERY_LOCKER", parent)
    root = anchor(coll, "food_locker_anchor", origin, yaw)
    coll["c2w_asset_id"] = "delivery.food_locker.clear_glass.v4"
    coll["c2w_asset_type"] = "food_delivery_locker"
    coll["c2w_independent_builder"] = "build_food_delivery_locker"
    coll["c2w_reference_file"] = "food_locker_user_reference.jpg"
    coll["c2w_reference_geometry_profile"] = (
        "ten_column_yellow_carcass_bright_white_nonmetal_frames_"
        "large_uninterrupted_clear_glass_large_black_numbers")
    coll["c2w_requested_revision"] = OUTPUT_ID

    bay_w, bay_count, row_count = .56, 10, 6
    grid_w = bay_w * bay_count
    width, depth, height = grid_w + .42, .90, 2.72
    grid_left = -grid_w / 2
    row_h, row_gap, row_start = .355, .030, .255
    row_centers = tuple(
        row_start + row_h / 2 + row * (row_h + row_gap)
        for row in range(row_count))
    door_outer = (bay_w - .105, row_h - .052)
    # The uninterrupted glazing now occupies roughly 80% of each leaf's width
    # and 77% of its height.  A 32--45 mm formed white perimeter remains for a
    # structurally credible door while the interior cavity reads clearly.
    glass_opening = (.365, .232)

    # A back skin, structural rails and bay partitions form a genuinely hollow
    # carcass.  This is crucial for the clear door glazing: the viewer sees
    # compartment depth and contents, not the front face of one solid block.
    box(coll, "food:rear_back_skin", (0, -.805, 1.40),
        (width, .060, 2.50), M["yellow_dark"], .018, parent=root,
        sem="locker_structure")
    for rail_index, rail_z in enumerate((.315, 1.40, 2.585)):
        box(coll, f"food:rear_structural_rail_{rail_index}",
            (0, -.665, rail_z), (width - .24, .235, .095),
            M["yellow_dark"], .012, parent=root, sem="locker_structure")
    box(coll, "food:lower_structural_plinth", (0, -.34, .245),
        (width + .015, .88, .19), M["yellow_dark"], .028, parent=root,
        sem="locker_structure")
    box(coll, "food:front_yellow_toe_skin", (0, .015, .245),
        (grid_w + .18, .055, .19), M["yellow"], .020, parent=root,
        sem="locker_structure")
    box(coll, "food:roof_skin", (0, -.34, 2.665),
        (width + .035, .90, .105), M["yellow"], .030, parent=root,
        sem="locker_structure")
    box(coll, "food:rear_service_spine", (0, -.846, 1.43),
        (width - .28, .030, 2.38), M["yellow_dark"], .006, parent=root,
        sem="architectural_detail")

    # Rolled end cheeks, folded returns and ventilation slots preserve a
    # believable fabricated-sheet enclosure at both ends of the 6 m bank.
    for side in (-1, 1):
        sx = side * (width / 2 - .085)
        box(coll, f"food:end_shroud_{side}", (sx, -.335, 1.42),
            (.205, .88, 2.50), M["yellow"], .060, parent=root,
            sem="locker_structure")
        box(coll, f"food:end_shroud_{side}:front_return",
            (sx - side * .052, .055, 1.43), (.095, .080, 2.42),
            M["yellow"], .030, parent=root, sem="architectural_detail")
        for slot in range(9):
            box(coll, f"food:end_shroud_{side}:rear_vent_{slot}",
                (sx + side * .108, -.675 + slot * .068, 1.65),
                (.012, .042, .150), M["black"], .004,
                parent=root, sem="architectural_detail")

    # Every column has a full-depth insulated partition, a rear liner and seven
    # shelf plates.  Narrow yellow front mullions remain separate folded parts.
    for edge in range(bay_count + 1):
        x = grid_left + edge * bay_w
        box(coll, f"food:bay_partition_{edge}", (x, -.350, 1.43),
            (.048, .760, 2.42), M["yellow_dark"], .009, parent=root,
            sem="locker_structure")
        box(coll, f"food:vertical_mullion_{edge}", (x, .018, 1.43),
            (.050, .096, 2.42), M["yellow"], .011, parent=root,
            sem="architectural_detail")
    for bay in range(bay_count):
        cx = grid_left + (bay + .5) * bay_w
        box(coll, f"food:bay_{bay}:insulated_back", (cx, -.735, 1.43),
            (bay_w - .065, .032, 2.40), M["food_cavity_white"], .008,
            parent=root, sem="locker_structure")
        for seam in range(row_count + 1):
            z = row_start + seam * (row_h + row_gap) - row_gap / 2
            box(coll, f"food:bay_{bay}:insulated_shelf_{seam}",
                (cx, -.295, z), (bay_w - .075, .720, .026),
                M["food_cavity_white"], .006, parent=root,
                sem="locker_structure")
            part_box(coll, f"food:bay_{bay}:front_shadow_joint_{seam}",
                     (cx, .037, z), (bay_w - .080, .028, .018),
                     M["rubber"], parent=root, sem="locker_hardware")

    # The frontal camera reverses world X.  Bay 8 therefore reads as the second
    # visible column, retaining an intuitive terminal/door numbering sequence.
    terminal_slot = (bay_count - 2, row_count - 1)
    door_count = 0
    clear_glass_count = 0
    visible_content_count = 0
    for bay in range(bay_count):
        cx = grid_left + (bay + .5) * bay_w
        for row_idx, cz in enumerate(row_centers):
            if (bay, row_idx) == terminal_slot:
                continue
            visual_bay = bay_count - 1 - bay
            compartment_number = 2 + visual_bay * row_count + (row_count - 1 - row_idx)
            key = f"food:door_{compartment_number:03d}"

            # Recessed cavity: rear panel, two side liners, threshold and vent
            # slots.  Their depth remains visible through the transparent pane.
            box(coll, f"{key}:cavity_back", (cx, -.515, cz),
                (glass_opening[0] + .045, .026, glass_opening[1] + .048),
                M["compartment_inner"], .010, parent=root,
                sem="locker_hardware")
            for side in (-1, 1):
                box(coll, f"{key}:liner_side_{side}",
                    (cx + side * (glass_opening[0] / 2 + .018), -.255, cz),
                    (.025, .500, glass_opening[1] + .060),
                    M["food_cavity_white"], .005, parent=root,
                    sem="locker_hardware")
            box(coll, f"{key}:threshold", (cx, -.245,
                cz - glass_opening[1] / 2 - .010),
                (glass_opening[0] + .060, .520, .024),
                M["food_cavity_white"], .006, parent=root,
                sem="locker_hardware")
            for vent in range(3):
                part_box(coll, f"{key}:rear_air_slot_{vent}",
                    (cx - .060 + vent * .060, -.498, cz + .057),
                    (.038, .006, .009), M["rubber"], parent=root,
                    sem="locker_hardware")

            # A varied subset contains a fully modeled insulated delivery bag,
            # making the clear glazing visually and geometrically unambiguous.
            if compartment_number % 7 in (0, 2):
                content_mat = (M["thermal_yellow"] if compartment_number % 2
                               else M["thermal_white"])
                bag_x = cx + (-.025 if compartment_number % 3 else .025)
                box(coll, f"{key}:thermal_bag_body", (bag_x, -.335, cz - .020),
                    (.205, .170, .120), content_mat, .018, parent=root,
                    sem="locker_contents", detail=True)
                box(coll, f"{key}:thermal_bag_lid", (bag_x, -.335, cz + .046),
                    (.218, .180, .028), content_mat, .012, parent=root,
                    sem="locker_contents", detail=True)
                box(coll, f"{key}:thermal_bag_label", (bag_x, -.244, cz - .020),
                    (.082, .006, .046), M["ui_white"], .004, parent=root,
                    sem="locker_contents", detail=True)
                tube(coll, f"{key}:thermal_bag_handle", (
                    (bag_x - .060, -.247, cz + .050),
                    (bag_x - .060, -.247, cz + .090),
                    (bag_x + .060, -.247, cz + .090),
                    (bag_x + .060, -.247, cz + .050)),
                    .007, M["rubber"], root, "locker_contents")
                visible_content_count += 1

            # One watertight bright-white powder-coated ring is the actual door leaf.
            # A separate elastomeric ring seats it against the insulated bay.
            front_frame(coll, f"{key}:perimeter_gasket", (cx, .052, cz),
                        (door_outer[0] + .020, door_outer[1] + .020),
                        (glass_opening[0] + .028, glass_opening[1] + .028),
                        .026, M["rubber"], .008, root, "locker_hardware")
            door = front_frame(
                coll, f"{key}:white_powdercoat_door_frame", (cx, .086, cz),
                door_outer, glass_opening, .044, M["food_door_white"],
                .012, root, "food_locker_door")
            door["c2w_compartment_number"] = compartment_number
            door["c2w_door_independent"] = True
            door["c2w_reference_door_style"] = (
                "bright_white_nonmetal_powdercoat_frame_with_large_clear_center_glass")
            door["c2w_white_door_leaf"] = True
            door["c2w_bright_white_nonmetal_finish"] = True
            door["c2w_door_metallic"] = 0.0
            door["c2w_true_center_opening"] = True

            window = box(coll, f"{key}:clear_tempered_center_glass",
                         (cx, .114, cz),
                         (glass_opening[0] - .006, .008,
                          glass_opening[1] - .006),
                         M["food_clear_glass"], .0035, parent=root,
                         sem="food_locker_window")
            window["c2w_clear_tempered_glass"] = True
            window["c2w_transmission_weight"] = .96
            window["c2w_reference_window_proportion"] = "large_clear_center_inset"
            window["c2w_uninterrupted_center_glazing"] = True
            window["c2w_glass_width_ratio"] = glass_opening[0] / door_outer[0]
            window["c2w_glass_height_ratio"] = glass_opening[1] / door_outer[1]

            # A narrow pale ceramic keyline guarantees contrast against both the
            # charcoal cavity back and light compartment liner.  The larger,
            # frontmost glyph remains an opaque-black marking fired directly
            # onto the glass; this reverses the prior white-fill treatment.
            keyline = text_obj(
                coll, f"{key}:glass_number_contrast_keyline",
                str(compartment_number), (cx, .124, cz - .010), .172,
                M["food_glass_number_keyline"], .0015, parent=root,
                xscale=.78, bold=True, sem="locker_hardware")
            keyline["c2w_black_number_contrast_keyline"] = True
            number = text_obj(
                coll, f"{key}:glass_number_black", str(compartment_number),
                (cx, .128, cz - .010), .158, M["food_glass_print"], .0018,
                parent=root, xscale=.78, bold=True, sem="locker_hardware")
            number["c2w_legible_compartment_number"] = True
            number["c2w_number_printed_on_glass"] = True
            number["c2w_black_ceramic_ink"] = True
            number["c2w_nominal_font_size_m"] = .158

            # Compact hardware stays on the white perimeter rails, never across
            # the clear center pane: recessed latch, status lamp, twin hinges,
            # hinge guards and four tamper-resistant fasteners.
            hardware_x = cx - door_outer[0] / 2 + .021
            box(coll, f"{key}:latch_housing", (hardware_x, .119, cz - .006),
                (.028, .026, .078), M["food_door_white_edge"], .007,
                parent=root, sem="locker_hardware")
            box(coll, f"{key}:latch_rocker", (hardware_x, .137, cz - .010),
                (.014, .010, .042), M["black"], .004,
                parent=root, sem="locker_hardware")
            _front_screw(coll, f"{key}:status_led", hardware_x, .145,
                         cz + .047,
                         M["led_green"] if compartment_number % 9 else M["led_red"],
                         root, .0055)
            hinge_x = cx + door_outer[0] / 2 + .006
            for hinge_idx, hz in enumerate((-.095, .095)):
                cyl(coll, f"{key}:hinge_{hinge_idx}",
                     (hinge_x, .111, cz + hz), .008, .050,
                     M["food_door_white_edge"], 16, parent=root,
                     sem="locker_hardware", bevel=.002)
                box(coll, f"{key}:hinge_guard_{hinge_idx}",
                    (hinge_x - .010, .108, cz + hz),
                    (.022, .018, .056), M["food_door_white"], .005,
                    parent=root, sem="locker_hardware")
            for sx, sz in ((-.210, -.137), (-.210, .137),
                           (.210, -.137), (.210, .137)):
                _front_screw(coll, f"{key}:fastener_{sx:+.3f}_{sz:+.3f}",
                             cx + sx, .119, cz + sz,
                             M["food_door_white_edge"], root, .0038)
            door_count += 1
            clear_glass_count += 1

    # The second visible column's top service bay contains a real operating
    # terminal in a white enclosure, consistent with the new door family.
    tx = grid_left + (terminal_slot[0] + .5) * bay_w
    terminal_z = row_centers[terminal_slot[1]]
    front_frame(coll, "food:terminal:perimeter_gasket", (tx, .052, terminal_z),
                (door_outer[0] + .020, door_outer[1] + .020),
                (.365, .218), .026, M["rubber"], .008,
                root, "locker_hardware")
    box(coll, "food:terminal:white_service_panel", (tx, .082, terminal_z),
        (door_outer[0], .044, door_outer[1]), M["food_door_white"], .018,
        parent=root, sem="workstation")
    box(coll, "food:terminal:screen_recess", (tx - .012, .116, terminal_z + .012),
        (.385, .030, .236), M["food_door_white_edge"], .026,
        parent=root, sem="workstation")
    box(coll, "food:terminal:screen_bezel", (tx - .012, .139, terminal_z + .012),
        (.357, .024, .208), M["black"], .021,
        parent=root, sem="workstation")
    box(coll, "food:terminal:screen_glass", (tx - .012, .157, terminal_z + .012),
        (.327, .011, .178), M["ui_navy"], .015,
        parent=root, sem="workstation")
    box(coll, "food:terminal:ui_header", (tx - .012, .166, terminal_z + .072),
        (.302, .006, .041), M["ui_teal"], .005, parent=root,
        sem="terminal_ui")
    text_obj(coll, "food:terminal:ui_title", "PICKUP",
             (tx - .060, .173, terminal_z + .072), .031,
             M["white_emit"], .0013, parent=root, xscale=.95,
             sem="terminal_ui")
    box(coll, "food:terminal:ui_code_field", (tx - .067, .168, terminal_z - .008),
        (.165, .006, .056), M["ui_white"], .006, parent=root,
        sem="terminal_ui")
    text_obj(coll, "food:terminal:ui_code_hint", "CODE",
             (tx - .067, .174, terminal_z - .008), .020, M["ui_gray"], .001,
             parent=root, xscale=.92, bold=False, sem="terminal_ui")
    qr_code(coll, "food:terminal:ui_qr", (tx + .105, terminal_z - .015),
            .074, .169, M["ink"], M["ui_white"], root, modules=9)
    _front_screw(coll, "food:terminal:camera", tx - .012, .174,
                 terminal_z + .121, M["glass_dark"], root, .007)
    _front_screw(coll, "food:terminal:status_led", tx + .205, .164,
                 terminal_z + .065, M["led_green"], root, .007)
    box(coll, "food:terminal:service_key", (tx + .195, .151, terminal_z - .032),
        (.045, .016, .075), M["steel"], .009, parent=root,
        sem="workstation")
    for row in range(3):
        for col in range(4):
            part_box(coll, f"food:terminal:keypad_{row}_{col}",
                     (tx - .112 + col * .037, .175,
                      terminal_z - .064 + row * .031),
                     (.031, .006, .020),
                     M["ui_yellow"] if (row, col) == (0, 3) else M["ui_pale"],
                     parent=root, sem="terminal_ui")
    for i in range(6):
        _front_screw(coll, f"food:terminal:speaker_{i}",
                     tx + .130 + (i % 3) * .020, .166,
                     terminal_z - .088 + (i // 3) * .022,
                     M["black"], root, .0038)
    for sx, sz in ((-.218, -.130), (-.218, .130),
                   (.218, -.130), (.218, .130)):
        _front_screw(coll, f"food:terminal:panel_fastener_{sx:+.3f}_{sz:+.3f}",
                     tx + sx, .153, terminal_z + sz, M["steel"], root, .0045)

    # Six industrial swivel casters distribute the doubled cabinet width; four
    # independent leveling feet stabilize the bank.  Forks, axles, bearing
    # rings and tread remain explicitly modeled rather than implied cylinders.
    caster_xs = (-2.46, -1.48, -.50, .50, 1.48, 2.46)
    for i, x in enumerate(caster_xs):
        box(coll, f"food:caster_{i}:mount_plate", (x, -.28, .145),
            (.190, .160, .026), M["steel"], .010, parent=root,
            sem="locker_hardware")
        cyl(coll, f"food:caster_{i}:swivel_bearing", (x, -.28, .118),
             .055, .038, M["steel"], 24, parent=root,
             sem="locker_hardware", bevel=.003)
        cyl(coll, f"food:caster_{i}:stem", (x, -.28, .155),
             .022, .085, M["steel"], 18, parent=root,
             sem="locker_hardware", bevel=.002)
        for side in (-1, 1):
            box(coll, f"food:caster_{i}:fork_{side}",
                (x, -.28 + side * .052, .077), (.038, .026, .110),
                M["steel"], .008, (0, math.radians(-8 * side), 0),
                root, "locker_hardware")
        cyl(coll, f"food:caster_{i}:wheel", (x, -.28, .066),
             .063, .074, M["rubber"], 28, (math.pi / 2, 0, 0), root,
             "locker_hardware", .004)
        cyl(coll, f"food:caster_{i}:axle", (x, -.28, .066),
             .014, .104, M["steel"], 18, (math.pi / 2, 0, 0), root,
             "locker_hardware", .002)
    leveling_xs = (-2.78, -.93, .93, 2.78)
    for i, x in enumerate(leveling_xs):
        cyl(coll, f"food:leveling_foot_{i}:stem", (x, -.18, .090),
             .023, .150, M["steel"], 18, parent=root,
             sem="locker_hardware", bevel=.002)
        cyl(coll, f"food:leveling_foot_{i}:pad", (x, -.18, .027),
             .064, .032, M["rubber"], 24, parent=root,
             sem="locker_hardware", bevel=.004)

    coll["c2w_column_count"] = bay_count
    coll["c2w_row_count"] = row_count
    coll["c2w_compartment_count"] = door_count
    coll["c2w_terminal_count"] = 1
    coll["c2w_white_powdercoat_door_count"] = door_count
    coll["c2w_clear_tempered_glass_count"] = clear_glass_count
    coll["c2w_glass_number_count"] = door_count
    coll["c2w_large_glazing_width_ratio"] = glass_opening[0] / door_outer[0]
    coll["c2w_large_glazing_height_ratio"] = glass_opening[1] / door_outer[1]
    coll["c2w_vertical_glass_bar_count"] = 0
    coll["c2w_number_finish"] = "large_opaque_black_ceramic_ink"
    coll["c2w_visible_insulated_bag_count"] = visible_content_count
    coll["c2w_caster_count"] = len(caster_xs)
    coll["c2w_leveling_foot_count"] = len(leveling_xs)
    coll["c2w_terminal_detail_level"] = "modeled_operational_interface"
    return coll


# ---------------------------------------------------------------------------
# Asset 2: Fengchao-style parcel locker and canopy

def build_parcel_locker(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Build the long lime-green parcel locker with a detailed steel canopy."""
    M = materials()
    coll = collection("PARCEL_LOCKER", parent)
    root = anchor(coll, "parcel_locker_anchor", origin, yaw)
    coll["c2w_asset_id"] = "delivery.parcel_locker.fengchao.v1"
    coll["c2w_asset_type"] = "parcel_locker"
    coll["c2w_independent_builder"] = "build_parcel_locker"
    coll["c2w_reference_file"] = "parcel_locker.jpg"

    width, depth = 11.45, .92
    box(coll, "parcel:rear_carcass", (0, -.49, 1.20), (width, .82, 2.30),
        M["green_alt"], .018, parent=root, sem="locker_structure")
    box(coll, "parcel:base_rail", (0, -.42, .13), (width + .08, .90, .22),
        M["charcoal"], .012, parent=root, sem="locker_structure")
    box(coll, "parcel:top_rail", (0, -.43, 2.34), (width + .10, .94, .15),
        M["charcoal"], .014, parent=root, sem="locker_structure")

    bay_w = 1.19
    bay_count = 9
    total_grid = bay_w * bay_count
    grid_left = -total_grid / 2
    row_h = (.25, .25, .26, .25, .26, .25, .26)
    z_cursor = .285
    row_centers = []
    for h in row_h:
        row_centers.append(z_cursor + h / 2)
        z_cursor += h + .033

    door_index = 1
    for bay in range(bay_count):
        bx = grid_left + (bay + .5) * bay_w
        for edge in (-1, 1):
            box(coll, f"parcel:bay_{bay}:jamb_{edge}",
                (bx + edge * (bay_w / 2 - .020), .025, 1.20),
                (.044, .092, 1.95), M["green_alt"], .007,
                parent=root, sem="architectural_detail")
        if bay == 4:
            continue
        for row, (cz, rh) in enumerate(zip(row_centers, row_h)):
            box(coll, f"parcel:door_{door_index:03d}:reveal", (bx, .040, cz),
                (bay_w - .075, .030, rh - .010), M["rubber"], .008,
                parent=root, sem="locker_hardware")
            door_mat = M["green"] if (bay + row) % 3 else M["green_alt"]
            door = box(coll, f"parcel:door_{door_index:03d}:panel", (bx, .067, cz),
                       (bay_w - .105, .034, rh - .038), door_mat, .010,
                       parent=root, sem="parcel_locker_door")
            door["c2w_compartment_number"] = door_index
            door["c2w_door_independent"] = True
            # Reference-scale hinges, latch, ID strip and powered status indicator.
            for hz in (-.065, .065):
                _front_screw(coll, f"parcel:door_{door_index:03d}:hinge_{hz:+.3f}",
                             bx - bay_w / 2 + .085, .105, cz + hz,
                             M["steel"], root, .012)
            _front_screw(coll, f"parcel:door_{door_index:03d}:latch",
                         bx + bay_w / 2 - .085, .108, cz,
                         M["black"], root, .014)
            box(coll, f"parcel:door_{door_index:03d}:id_plate",
                (bx + .31, .109, cz + .064), (.245, .012, .056),
                M["yellow"], .006, parent=root, sem="locker_hardware")
            id_text = text_obj(
                coll, f"parcel:door_{door_index:03d}:id_text",
                f"{door_index:03d}", (bx + .31, .119, cz + .064),
                .055, M["charcoal"], .002, parent=root,
                xscale=.78, bold=True, sem="locker_hardware")
            id_text["c2w_legible_compartment_number"] = True
            _front_screw(coll, f"parcel:door_{door_index:03d}:status",
                         bx + .43, .115, cz - .060,
                         M["led_green"] if door_index % 7 else M["led_red"],
                         root, .006)
            door_index += 1

    # Full-height central terminal follows the supplied real Hive Box reference:
    # portrait glass, stainless trim, dense operational UI and integrated readers.
    tx = grid_left + 4.5 * bay_w
    box(coll, "parcel:terminal:recess", (tx, .045, 1.23),
        (bay_w - .065, .038, 1.98), M["rubber"], .012,
        parent=root, sem="locker_hardware")
    box(coll, "parcel:terminal:panel", (tx, .079, 1.23),
        (bay_w - .102, .045, 1.94), M["green_alt"], .014,
        parent=root, sem="workstation")
    for side in (-1, 1):
        box(coll, f"parcel:terminal:stainless_reveal_{side}",
            (tx + side * .498, .118, 1.27), (.062, .055, 1.86),
            M["steel"], .009, parent=root, sem="workstation")
    box(coll, "parcel:terminal:brand_header", (tx, .120, 2.110),
        (.900, .036, .245), M["green"], .012, parent=root, sem="signage")
    _hex_logo(coll, "parcel:terminal:brand_icon", (tx - .345, .146, 2.110),
              .078, .018, M["yellow"], root)
    text_obj(coll, "parcel:terminal:brand_text", "HIVE BOX",
             (tx + .095, .148, 2.115), .200, M["charcoal"], .006,
             parent=root, xscale=.74, sem="signage")
    for side in (-1, 1):
        for i in range(7):
            _front_screw(coll, f"parcel:terminal:header_speaker_{side}_{i}",
                         tx + side * (.24 + i * .017), .149, 1.985,
                         M["black"], root, .0038)

    # Portrait touchscreen assembly with a narrow aluminum reveal and laminated bezel.
    box(coll, "parcel:terminal:screen_mount", (tx, .121, 1.355),
        (.790, .038, 1.245), M["aluminium"], .024, parent=root, sem="workstation")
    box(coll, "parcel:terminal:screen_bezel", (tx, .149, 1.355),
        (.735, .028, 1.185), M["charcoal"], .018, parent=root, sem="workstation")
    box(coll, "parcel:terminal:screen", (tx, .169, 1.355),
        (.660, .012, 1.095), M["ui_white"], .010, parent=root, sem="workstation")
    # Promotional header and operating navigation.
    box(coll, "parcel:terminal:ui_promo", (tx, .180, 1.785),
        (.618, .008, .205), M["screen_ui"], .005, parent=root,
        sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_promo_title", "SMART PARCEL SERVICE",
             (tx - .118, .187, 1.820), .060, M["white_emit"], .0015,
             parent=root, xscale=.80, sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_promo_sub", "SCAN TO OPEN",
             (tx - .145, .187, 1.748), .031, M["white_emit"], .001,
             parent=root, xscale=.78, bold=False, sem="terminal_ui")
    for i, height in enumerate((.065, .105, .150)):
        box(coll, f"parcel:terminal:ui_locker_graphic_{i}",
            (tx + .205 + i * .062, .186, 1.735 + height / 2),
            (.046, .008, height), M["ui_yellow"], .004,
            parent=root, sem="terminal_ui")
    box(coll, "parcel:terminal:ui_nav", (tx, .180, 1.625),
        (.618, .008, .070), M["ui_pale"], .003, parent=root,
        sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_nav_text", "COLLECT    SEND    TRACK",
             (tx, .187, 1.625), .035, M["ink"], .001,
             parent=root, xscale=.82, sem="terminal_ui")
    # QR workflow on the left, retrieval-code workflow on the right.
    qr_code(coll, "parcel:terminal:ui_qr", (tx - .170, 1.355),
            .250, .185, M["ink"], M["white"], root, modules=15)
    text_obj(coll, "parcel:terminal:ui_qr_label", "SCAN TO COLLECT",
             (tx - .170, .190, 1.185), .041, M["ink"], .0012,
             parent=root, xscale=.84, sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_code_label", "ENTER COLLECTION CODE",
             (tx + .168, .188, 1.465), .035, M["ui_gray"], .001,
             parent=root, xscale=.82, sem="terminal_ui")
    for i in range(3):
        box(coll, f"parcel:terminal:ui_code_cell_{i}",
            (tx + .095 + i * .074, .186, 1.378),
            (.060, .008, .072), M["ui_pale"], .004,
            parent=root, sem="terminal_ui")
    box(coll, "parcel:terminal:ui_confirm", (tx + .168, .186, 1.265),
        (.242, .009, .082), M["ui_yellow"], .006, parent=root,
        sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_confirm_text", "CONFIRM AND OPEN",
             (tx + .168, .193, 1.265), .038, M["ink"], .001,
             parent=root, xscale=.84, sem="terminal_ui")
    # Screen footer includes service notices and a second contact QR block.
    box(coll, "parcel:terminal:ui_footer_rule", (tx, .184, 1.090),
        (.600, .006, .012), M["ui_gray"], .002, parent=root,
        sem="terminal_ui")
    text_obj(coll, "parcel:terminal:ui_footer", "SERVICE 95333  |  HELP",
             (tx - .060, .190, 1.025), .025, M["ui_gray"], .001,
             parent=root, xscale=.78, bold=False, sem="terminal_ui")
    _front_screw(coll, "parcel:terminal:camera", tx, .193, 1.940,
                 M["glass_dark"], root, .016)
    _hex_logo(coll, "parcel:terminal:nfc_reader", (tx + .270, .191, 1.530),
              .035, .010, M["ui_teal"], root)

    # Service hardware remains below the glass as a real maintainable assembly.
    box(coll, "parcel:terminal:scanner_bezel", (tx - .245, .145, .655),
        (.235, .032, .155), M["black"], .010, parent=root, sem="workstation")
    box(coll, "parcel:terminal:scanner_glass", (tx - .245, .165, .655),
        (.175, .012, .100), M["glass_dark"], .006, parent=root, sem="workstation")
    box(coll, "parcel:terminal:receipt_slot", (tx + .225, .153, .705),
        (.280, .020, .030), M["black"], .005, parent=root, sem="workstation")
    text_obj(coll, "parcel:terminal:hardware_label", "RECEIPT SLOT",
             (tx + .225, .166, .650), .031, M["charcoal"], .001,
             parent=root, xscale=.82, sem="workstation")
    box(coll, "parcel:terminal:service_hatch", (tx, .118, .390),
        (.800, .032, .265), M["green"], .010, parent=root, sem="workstation")
    for side in (-1, 1):
        _front_screw(coll, f"parcel:terminal:service_screw_{side}",
                     tx + side * .34, .140, .390, M["steel"], root, .010)
    for i in range(8):
        _front_screw(coll, f"parcel:terminal:lower_speaker_{i}",
                     tx - .105 + i * .030, .155, .535,
                     M["black"], root, .0045)

    # Brand mark and icon are modeled proud of the doors, matching the reference.
    box(coll, "parcel:fengchao_sign_back", (4.10, .106, 2.090),
        (3.05, .035, .300), M["green"], .010, parent=root, sem="signage")
    text_obj(coll, "parcel:fengchao_wordmark", "HIVE BOX SMART LOCKERS",
             (4.25, .137, 2.095), .310, M["charcoal"], .012,
             parent=root, xscale=.72)
    _hex_logo(coll, "parcel:fengchao_hex", (2.85, .140, 2.09),
              .16, .022, M["charcoal"], root)
    _hex_logo(coll, "parcel:fengchao_hex_inner", (2.85, .154, 2.09),
              .072, .026, M["green"], root)

    # Deep rain canopy, posts, front gutter and triangulated brackets.
    box(coll, "parcel:canopy_roof", (0, -.15, 2.78),
        (width + .75, 1.66, .14), M["charcoal"], .012,
        (math.radians(-3.0), 0, 0), root, "canopy_structure")
    box(coll, "parcel:canopy_front_gutter", (0, .69, 2.70),
        (width + .82, .13, .26), M["charcoal"], .008,
        parent=root, sem="canopy_structure")
    box(coll, "parcel:canopy_rear_beam", (0, -.93, 2.60),
        (width + .32, .12, .18), M["black"], .006,
        parent=root, sem="canopy_structure")
    post_xs = (-5.42, -3.55, -1.78, 0, 1.78, 3.55, 5.42)
    for i, px in enumerate(post_xs):
        box(coll, f"parcel:canopy_post_{i}", (px, -.86, 1.38),
            (.095, .095, 2.56), M["charcoal"], .006,
            parent=root, sem="canopy_structure")
        tube(coll, f"parcel:canopy_brace_{i}",
             ((px, -.84, 2.48), (px, .42, 2.67)), .027,
             M["steel"], root, "architectural_detail")
        box(coll, f"parcel:post_foot_{i}", (px, -.86, .035),
            (.23, .22, .06), M["steel"], .007, parent=root,
            sem="locker_hardware")
        for sx in (-.07, .07):
            _front_screw(coll, f"parcel:post_anchor_{i}_{sx:+.2f}",
                         px + sx, -.74, .068, M["black"], root, .010)

    # Side panels have real ventilation slots and a rainwater downpipe.
    for side in (-1, 1):
        sx = side * (width / 2 + .035)
        box(coll, f"parcel:end_cheek_{side}", (sx, -.45, 1.20),
            (.105, .92, 2.30), M["green_alt"], .013,
            parent=root, sem="locker_structure")
        for i in range(8):
            box(coll, f"parcel:end_{side}:vent_{i}",
                (sx + side * .059, -.65 + i * .075, 1.45),
                (.012, .048, .22), M["black"], .002,
                parent=root, sem="architectural_detail")
    cyl(coll, "parcel:downpipe", (5.65, -.90, 1.27), .035, 2.54,
         M["charcoal"], 20, parent=root, sem="architectural_detail", bevel=.003)
    tube(coll, "parcel:downpipe_offset",
         ((5.65, -.90, .12), (5.65, -.72, .05), (5.65, -.54, .05)),
         .036, M["charcoal"], root, "architectural_detail")

    coll["c2w_compartment_count"] = door_index - 1
    coll["c2w_terminal_count"] = 1
    coll["c2w_canopy_post_count"] = len(post_xs)
    coll["c2w_numbered_compartment_count"] = door_index - 1
    coll["c2w_terminal_detail_level"] = "portrait_operational_touchscreen"
    return coll


# ---------------------------------------------------------------------------
# Asset 3 helpers: physically supported parcels and industrial shelving

def _xy(point, center, yaw):
    x, y = point
    cx, cy = center
    c, s = math.cos(yaw), math.sin(yaw)
    return cx + c * x - s * y, cy + s * x + c * y


def _rack_box(coll, name, center, yaw, loc, dims, material, parent,
              sem="rack_structure", bevel=0.0, detail=True):
    x, y = _xy((loc[0], loc[1]), center, yaw)
    if bevel > 0:
        return box(coll, name, (x, y, loc[2]), dims, material, bevel,
                   (0, 0, yaw), parent, sem, detail)
    return part_box(coll, name, (x, y, loc[2]), dims, material,
                    (0, 0, yaw), parent, sem, detail)


def _parcel(coll, root, name, center, yaw, local_xy, support_top,
            dims, material, support_name, label_side=1):
    """Build a taped, labeled parcel whose body exactly rests on a shelf."""
    M = materials()
    w, d, h = dims
    x, y = _xy(local_xy, center, yaw)
    body = box(coll, name + ":body", (x, y, support_top + h / 2), dims,
               material, .006, (0, 0, yaw), root, "parcel", False)
    body["c2w_support_relation"] = "rests_on_modeled_shelf"
    body["c2w_support_name"] = support_name
    body["c2w_support_top_z"] = float(support_top)
    body["c2w_declared_base_z"] = float(support_top)
    body["c2w_parcel_assembly"] = name

    # Crossed packing tape on the lid and down the customer-facing panel.
    _rack_box(coll, name + ":top_tape_long", center, yaw,
              (local_xy[0], local_xy[1], support_top + h + .006),
              (.064, d * .92, .012), M["tape"], root, "parcel_detail")
    _rack_box(coll, name + ":top_tape_cross", center, yaw,
              (local_xy[0], local_xy[1], support_top + h + .013),
              (w * .88, .055, .010), M["tape"], root, "parcel_detail")
    front_y = local_xy[1] + label_side * (d / 2 + .008)
    _rack_box(coll, name + ":front_tape", center, yaw,
              (local_xy[0], front_y, support_top + h / 2),
              (.064, .012, h * .86), M["tape"], root, "parcel_detail")
    label_z = support_top + h * .58
    label = _rack_box(coll, name + ":shipping_label", center, yaw,
                      (local_xy[0] + w * .12, front_y + label_side * .009, label_z),
                      (min(.205, w * .62), .010, min(.132, h * .48)),
                      M["label"], root, "shipping_label")
    label["c2w_attached_to"] = body.name
    # Printed barcode is physical geometry, so it survives any texture-free export.
    for bar in range(4):
        bw = .008 if bar % 2 else .014
        _rack_box(coll, name + f":barcode_{bar}", center, yaw,
                  (local_xy[0] + w * .08 + (bar - 1.5) * .029,
                   front_y + label_side * .015,
                   label_z - .012),
                  (bw, .006, min(.075, h * .27)), M["ink"], root,
                  "parcel_detail")
    return body


def _build_rack(coll, root, name, center, yaw, length, depth, bays,
                levels, seed, parcels_per_bay=2):
    """Build one perforated steel rack and fill every deck with supported parcels."""
    M = materials()
    rng = random.Random(seed)
    height = max(levels) + .62
    bay_w = length / bays
    uprights = [(-length / 2 + i * bay_w) for i in range(bays + 1)]
    for ui, ux in enumerate(uprights):
        for side in (-1, 1):
            uy = side * depth / 2
            _rack_box(coll, f"{name}:upright_{ui}_{side}", center, yaw,
                      (ux, uy, height / 2), (.062, .062, height),
                      M["blue"], root, "rack_structure", .004)
            _rack_box(coll, f"{name}:foot_{ui}_{side}", center, yaw,
                      (ux, uy, .035), (.20, .15, .055), M["steel"],
                      root, "rack_detail", .004)
            # Regular punched slots reveal the industrial rack construction.
            for pi, pz in enumerate((.31, .58, .85, 1.12, 1.39, 1.66, 1.93, 2.20, 2.47, 2.74, 3.01)):
                if pz >= height - .12:
                    continue
                _rack_box(coll, f"{name}:perforation_{ui}_{side}_{pi}", center, yaw,
                          (ux, uy + side * .035, pz), (.018, .012, .055),
                          M["charcoal"], root, "rack_detail")

    parcel_count = 0
    for li, shelf_z in enumerate(levels):
        shelf = _rack_box(coll, f"{name}:shelf_{li}", center, yaw,
                          (0, 0, shelf_z), (length + .08, depth + .08, .065),
                          M["steel"], root, "rack_shelf", .005)
        shelf_top = shelf_z + .0325
        shelf["c2w_support_top_z"] = shelf_top
        for side in (-1, 1):
            _rack_box(coll, f"{name}:beam_{li}_{side}", center, yaw,
                      (0, side * (depth / 2 + .015), shelf_z - .035),
                      (length + .11, .075, .105), M["blue"], root,
                      "rack_structure", .004)
        # Back X braces prevent the rack from reading as unsupported shelves.
        if li < len(levels) - 1:
            z2 = levels[li + 1] - .04
            for bi in range(bays):
                x0 = -length / 2 + bi * bay_w
                x1 = x0 + bay_w
                p0 = _xy((x0 + .06, -depth / 2, ), center, yaw)
                p1 = _xy((x1 - .06, -depth / 2, ), center, yaw)
                tube(coll, f"{name}:crossbrace_{li}_{bi}_a",
                     ((p0[0], p0[1], shelf_z + .05), (p1[0], p1[1], z2)),
                     .012, M["aluminium"], root, "rack_detail")
                tube(coll, f"{name}:crossbrace_{li}_{bi}_b",
                     ((p1[0], p1[1], shelf_z + .05), (p0[0], p0[1], z2)),
                     .012, M["aluminium"], root, "rack_detail")

        for bi in range(bays):
            slot_w = bay_w / parcels_per_bay
            for si in range(parcels_per_bay):
                max_w = slot_w * .78
                pw = min(max_w, rng.choice((.25, .30, .34, .38, .42)))
                pd = min(depth * .75, rng.choice((.28, .34, .40, .46, .50)))
                ph = rng.choice((.20, .24, .28, .33, .38, .43))
                px = -length / 2 + bi * bay_w + (si + .5) * slot_w
                py = rng.uniform(-.035, .035)
                material = M[rng.choice(("cardboard_a", "cardboard_a", "cardboard_b", "cardboard_c"))]
                _parcel(
                    coll, root, f"{name}:parcel_{li}_{bi}_{si}", center, yaw,
                    (px, py), shelf_top, (pw, pd, ph), material, shelf.name,
                    1,
                )
                parcel_count += 1
    return parcel_count


# ---------------------------------------------------------------------------
# Asset 3: glazed parcel station with complete interior

def build_delivery_station(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Build the reference glass parcel station, fitted and stocked inside."""
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
    box(coll, "station:foundation", (0, -depth / 2, .06),
        (width + .22, depth + .20, .28), M["concrete"], .018,
        parent=root, sem="architecture")
    box(coll, "station:epoxy_floor", (0, -depth / 2, .225),
        (width, depth, .075), M["floor"], .008,
        parent=root, sem="floor_finish")
    box(coll, "station:roof_deck", (0, -depth / 2, wall_h),
        (width + .26, depth + .24, .22), M["white_metal"], .012,
        parent=root, sem="architecture")
    box(coll, "station:rear_wall", (0, back_y + .07, 2.10),
        (width, .14, 3.85), M["white_metal"], .008,
        parent=root, sem="architecture")
    box(coll, "station:left_wall", (-width / 2 + .07, -depth / 2, 2.10),
        (.14, depth, 3.85), M["white_metal"], .008,
        parent=root, sem="architecture")
    box(coll, "station:right_service_wall", (width / 2 - .07, -7.0, 2.10),
        (.14, 3.15, 3.85), M["white_metal"], .008,
        parent=root, sem="architecture")

    # Modeled corrugations on opaque wall/ceiling surfaces catch daylight at real scale.
    for i, x in enumerate([(-width / 2 + .16) + i * .16 for i in range(76)]):
        part_box(coll, f"station:rear_corrugation_{i}", (x, back_y + .145, 2.08),
                 (.026, .025, 3.68), M["aluminium"], parent=root,
                 sem="architectural_detail")
    for i, y in enumerate([back_y + .18 + i * .16 for i in range(52)]):
        part_box(coll, f"station:left_corrugation_{i}",
                 (-width / 2 + .145, y, 2.08),
                 (.025, .026, 3.68), M["aluminium"], parent=root,
                 sem="architectural_detail")
    for i, y in enumerate([back_y + .15 + i * .27 for i in range(32)]):
        part_box(coll, f"station:ceiling_rib_{i}", (0, y, 3.985),
                 (width - .18, .026, .035), M["aluminium"], parent=root,
                 sem="architectural_detail")

    # Epoxy floor control joints and a flush entry threshold.
    for i, x in enumerate([(-width / 2 + .8) + i * 1.0 for i in range(12)]):
        part_box(coll, f"station:floor_joint_x_{i}", (x, -depth / 2, .266),
                 (.010, depth - .20, .006), M["joint"], parent=root,
                 sem="floor_detail")
    for i, y in enumerate([-.75 - i * 1.0 for i in range(8)]):
        part_box(coll, f"station:floor_joint_y_{i}", (0, y, .266),
                 (width - .20, .010, .006), M["joint"], parent=root,
                 sem="floor_detail")
    box(coll, "station:entry_threshold", (-4.55, .055, .245),
        (2.35, .24, .075), M["steel"], .006, parent=root,
        sem="architectural_detail")

    # Black aluminum glazed storefront and open sliding entrance.
    front_divisions = (-6.2, -5.65, -3.45, -1.40, .70, 2.80, 4.90, 6.20)
    for i, (x0, x1) in enumerate(zip(front_divisions, front_divisions[1:])):
        if i == 1:  # physical doorway, with one leaf slid aside below
            continue
        pane_w = x1 - x0 - .10
        box(coll, f"station:front_glass_{i}", ((x0 + x1) / 2, .015, 1.78),
            (pane_w, .025, 3.02), M["glass"], .002, parent=root,
            sem="glazing")
    for i, x in enumerate(front_divisions):
        box(coll, f"station:front_mullion_{i}", (x, .035, 1.80),
            (.075, .095, 3.30), M["charcoal"], .006, parent=root,
            sem="architectural_detail")
    for z, name in ((.28, "sill"), (3.31, "head")):
        box(coll, f"station:front_{name}_rail", (0, .035, z),
            (width + .05, .095, .095), M["charcoal"], .006,
            parent=root, sem="architectural_detail")
    # Sliding glass door is visibly open, with floor track, pull handles and rollers.
    box(coll, "station:entry_fixed_leaf", (-5.08, .020, 1.70),
        (1.02, .028, 2.80), M["glass"], .002, parent=root, sem="door_glazing")
    for x in (-5.61, -4.55):
        box(coll, f"station:entry_frame_{x:+.2f}", (x, .045, 1.70),
            (.065, .085, 2.95), M["charcoal"], .005, parent=root,
            sem="architectural_detail")
    # Moving leaf parked behind the fixed panel, leaving a 1.05 m clear opening.
    box(coll, "station:entry_sliding_leaf_open", (-5.02, -.075, 1.70),
        (.94, .025, 2.72), M["glass"], .002, parent=root, sem="door_glazing")
    for z in (1.08, 1.72):
        cyl(coll, f"station:door_handle_{z:.2f}", (-4.50, .080, z),
             .018, .48, M["steel"], 18, parent=root,
             sem="architectural_detail", bevel=.002)
    box(coll, "station:sliding_floor_track", (-4.55, .03, .295),
        (2.28, .085, .032), M["steel"], .003, parent=root,
        sem="architectural_detail")

    # Transparent right return facade forms the reference's glazed corner box.
    side_divisions = (0.0, -1.65, -3.30, -4.95, -5.55)
    for i, (y0, y1) in enumerate(zip(side_divisions, side_divisions[1:])):
        box(coll, f"station:right_glass_{i}", (width / 2 - .015, (y0 + y1) / 2, 1.78),
            (.025, abs(y1 - y0) - .10, 3.02), M["glass"], .002,
            parent=root, sem="glazing")
    for i, y in enumerate(side_divisions):
        box(coll, f"station:right_mullion_{i}", (width / 2 - .035, y, 1.80),
            (.095, .075, 3.30), M["charcoal"], .006, parent=root,
            sem="architectural_detail")
    for z, name in ((.28, "sill"), (3.31, "head")):
        box(coll, f"station:right_{name}_rail", (width / 2 - .035, -2.77, z),
            (.095, 5.60, .095), M["charcoal"], .006, parent=root,
            sem="architectural_detail")

    # Cyan illuminated fascia wraps the corner and is held by a black carrier frame.
    box(coll, "station:front_fascia_frame", (0, -.015, 3.69),
        (width + .12, .14, .82), M["charcoal"], .008, parent=root,
        sem="signage")
    box(coll, "station:front_fascia_blue", (0, .069, 3.69),
        (width - .17, .035, .65), M["cyan_emit"], .006, parent=root,
        sem="signage")
    box(coll, "station:right_fascia_frame", (width / 2 + .015, -2.75, 3.69),
        (.14, 5.62, .82), M["charcoal"], .008, parent=root,
        sem="signage")
    box(coll, "station:right_fascia_blue", (width / 2 + .091, -2.75, 3.69),
        (.025, 5.42, .65), M["cyan_emit"], .004, parent=root,
        sem="signage")
    # The public-facing fascia intentionally carries one large English-only
    # wordmark.  Its dimensions are audited against the cyan carrier below so
    # it remains crisply legible in the full-row daylight camera without ever
    # crossing the sign boundary.
    primary_sign = text_obj(
        coll, "station:primary_wordmark", "CAINIAO PARCEL STATION",
        (.62, .104, 3.70), 1.250, M["white_emit"], .024,
        parent=root, xscale=1.65)
    primary_sign["c2w_front_sign_language"] = "English"
    primary_sign["c2w_enlarged_for_far_view"] = True
    coll["c2w_front_sign_language"] = "English"
    _hex_logo(coll, "station:brand_hex", (-4.70, .105, 3.79),
              .23, .025, M["white_emit"], root)
    _hex_logo(coll, "station:brand_hex_inner", (-4.70, .122, 3.79),
              .105, .029, M["cyan_emit"], root)

    # Rack layout follows the interior reference: long blue runs, open aisles,
    # a dense glazed display side and a rear wall run.
    parcel_total = 0
    rack_specs = (
        ("rear_wall_rack", (0.0, -7.70), 0.0, 10.45, .66, 8, (.48, 1.18, 1.88, 2.58), 3101, 2),
        ("left_aisle_rack", (-4.63, -4.45), math.pi / 2, 5.30, .68, 5, (.48, 1.17, 1.86, 2.55), 3102, 2),
        ("middle_aisle_rack", (-2.12, -4.45), math.pi / 2, 5.30, .68, 5, (.48, 1.17, 1.86, 2.55), 3103, 2),
        ("glass_side_rack", (5.20, -3.80), math.pi / 2, 4.95, .66, 4, (.48, 1.17, 1.86, 2.55), 3104, 2),
        ("front_display_rack", (2.86, -.72), 0.0, 4.55, .60, 4, (.47, 1.15, 1.83), 3105, 2),
    )
    for spec in rack_specs:
        parcel_total += _build_rack(coll, root, *spec)

    # Blue-white reception counter and packing workbench.
    box(coll, "station:counter:front_carcass", (2.25, -4.48, .72),
        (3.55, .78, 1.18), M["blue"], .028, parent=root, sem="counter")
    box(coll, "station:counter:solid_top", (2.25, -4.45, 1.35),
        (3.78, .96, .105), M["offwhite"], .028, parent=root, sem="counter")
    box(coll, "station:counter:kick", (2.25, -4.02, .25),
        (3.48, .10, .22), M["charcoal"], .006, parent=root, sem="counter_detail")
    for i in range(4):
        box(coll, f"station:counter:front_panel_{i}",
            (.93 + i * .88, -4.005, .76), (.78, .045, .83),
            M["blue"], .008, parent=root, sem="counter_detail")
        box(coll, f"station:counter:panel_reveal_{i}",
            (.93 + i * .88, -3.978, .76), (.67, .010, .70),
            M["cyan_emit"] if i == 1 else M["blue"], .004,
            parent=root, sem="counter_detail")
    # Accessible lower return table, white top, steel legs and under-table drawer.
    box(coll, "station:packing_table:top", (4.35, -5.47, 1.03),
        (2.22, 1.05, .095), M["offwhite"], .018, parent=root, sem="counter")
    for px in (3.40, 5.30):
        for py in (-5.10, -5.84):
            box(coll, f"station:packing_table:leg_{px:.2f}_{py:.2f}",
                (px, py, .55), (.070, .070, .96), M["steel"], .006,
                parent=root, sem="counter_detail")
    box(coll, "station:packing_table:drawer", (4.35, -5.05, .82),
        (1.08, .42, .25), M["blue"], .010, parent=root, sem="counter_detail")
    box(coll, "station:packing_table:drawer_pull", (4.35, -4.82, .82),
        (.45, .045, .035), M["steel"], .010, parent=root, sem="counter_detail")

    # Reference-shaped all-in-one POS: broad weighted base, tapered aluminum
    # column, serviceable hinge and a thin laminated touchscreen rather than a
    # slab on a pole.  The screen carries a complete parcel-station workflow.
    monitor_center = (2.30, -4.34, 1.965)
    monitor_tilt = math.radians(-8.0)
    box(coll, "station:pos:weighted_base", (2.30, -4.42, 1.445),
        (.760, .420, .070), M["white_metal"], .035,
        parent=root, sem="workstation")
    box(coll, "station:pos:base_inset", (2.30, -4.205, 1.447),
        (.520, .030, .025), M["aluminium"], .008,
        parent=root, sem="workstation")
    for side in (-1, 1):
        box(coll, f"station:pos:base_port_{side}",
            (2.30 + side * .205, -4.196, 1.450), (.110, .010, .018),
            M["black"], .003, parent=root, sem="workstation")
    tapered_box(coll, "station:pos:tapered_column", (2.30, -4.43, 1.650),
                (.340, .245), (.185, .130), .390, M["white_metal"], .016,
                parent=root, sem="workstation")
    cyl(coll, "station:pos:tilt_hinge", (2.30, -4.375, 1.825),
         .072, .360, M["steel"], 28, (0, math.pi / 2, 0), root,
         "workstation", .005)
    box(coll, "station:pos:rear_shell", monitor_center,
        (1.010, .085, .655), M["white_metal"], .035,
        (monitor_tilt, 0, 0), root, "workstation")
    box(coll, "station:pos:vent_band",
        _tilted_front_point(monitor_center, 0, -.275, -.050, monitor_tilt),
        (.610, .012, .045), M["aluminium"], .005,
        (monitor_tilt, 0, 0), root, "workstation")
    for i in range(11):
        tilted_ui_box(coll, f"station:pos:rear_vent_{i}", monitor_center,
                      -.250 + i * .050, -.275, (.025, .016), M["black"],
                      monitor_tilt, root, front_offset=-.058, depth=.006,
                      sem="workstation")
    box(coll, "station:pos:front_bezel",
        _tilted_front_point(monitor_center, 0, 0, .058, monitor_tilt),
        (.960, .045, .605), M["charcoal"], .025,
        (monitor_tilt, 0, 0), root, "workstation")
    box(coll, "station:pos:monitor_glass",
        _tilted_front_point(monitor_center, 0, 0, .084, monitor_tilt),
        (.895, .010, .535), M["screen"], .012,
        (monitor_tilt, 0, 0), root, "workstation")
    tilted_ui_box(coll, "station:pos:ui_canvas", monitor_center, 0, 0,
                  (.855, .495), M["ui_white"], monitor_tilt, root,
                  front_offset=.092, depth=.006)
    tilted_ui_box(coll, "station:pos:ui_header", monitor_center, 0, .205,
                  (.855, .085), M["ui_navy"], monitor_tilt, root,
                  front_offset=.100)
    tilted_ui_text(coll, "station:pos:ui_title", "STATION WORKSTATION", monitor_center,
                   -.275, .207, .046, M["white_emit"], monitor_tilt, root,
                   xscale=.84, front_offset=.106, align="LEFT")
    tilted_ui_text(coll, "station:pos:ui_clock", "09:36", monitor_center,
                   .330, .207, .027, M["white_emit"], monitor_tilt, root,
                   xscale=.78, front_offset=.106, bold=False)
    # Left navigation rail with icon glyphs.
    tilted_ui_box(coll, "station:pos:ui_sidebar", monitor_center, -.375, -.045,
                  (.105, .405), M["ui_gray"], monitor_tilt, root,
                  front_offset=.101)
    for i, label in enumerate(("IN", "OUT", "FIND", "SET")):
        dz = .095 - i * .092
        tilted_ui_box(coll, f"station:pos:nav_icon_back_{i}", monitor_center,
                      -.375, dz, (.058, .058),
                      M["screen_ui"] if i == 0 else M["ui_pale"],
                      monitor_tilt, root, front_offset=.108)
        tilted_ui_text(coll, f"station:pos:nav_icon_{i}", label, monitor_center,
                       -.375, dz, .026, M["white_emit"] if i == 0 else M["ink"],
                       monitor_tilt, root, xscale=.82, front_offset=.114)
    # Summary cards and a real tabular order list.
    for i, (dx, label, value, material) in enumerate((
        (-.205, "PENDING INTAKE", "12", M["screen_ui"]),
        (.045, "AWAITING COLLECTION", "36", M["ui_teal"]),
        (.295, "EXCEPTIONS", "03", M["ui_yellow"]),
    )):
        tilted_ui_box(coll, f"station:pos:summary_{i}", monitor_center,
                      dx, .108, (.215, .110), M["ui_pale"], monitor_tilt,
                      root, front_offset=.102)
        tilted_ui_text(coll, f"station:pos:summary_label_{i}", label,
                       monitor_center, dx - .045, .130, .024, M["ui_gray"],
                       monitor_tilt, root, xscale=.78, front_offset=.110,
                       bold=False)
        tilted_ui_text(coll, f"station:pos:summary_value_{i}", value,
                       monitor_center, dx + .055, .092, .041, material,
                       monitor_tilt, root, xscale=.86, front_offset=.111)
    tilted_ui_box(coll, "station:pos:table_header", monitor_center, .045, .018,
                  (.650, .052), M["ui_gray"], monitor_tilt, root,
                  front_offset=.103)
    tilted_ui_text(coll, "station:pos:table_header_text",
                   "ORDER       PHONE       STATUS", monitor_center,
                   -.045, .018, .022, M["white_emit"], monitor_tilt, root,
                   xscale=.77, front_offset=.111, bold=False)
    rows = (("A260831", "4821", "AWAITING COLLECTION"),
            ("B260829", "1760", "STORED"),
            ("C260824", "9035", "AWAITING VERIFICATION"))
    for i, (order, phone, state) in enumerate(rows):
        dz = -.048 - i * .061
        tilted_ui_box(coll, f"station:pos:table_row_{i}", monitor_center,
                      .045, dz, (.650, .052),
                      M["ui_white"] if i % 2 == 0 else M["ui_pale"],
                      monitor_tilt, root, front_offset=.104)
        tilted_ui_text(coll, f"station:pos:order_{i}", order, monitor_center,
                       -.210, dz, .019, M["ink"], monitor_tilt, root,
                       xscale=.73, front_offset=.112, bold=False)
        tilted_ui_text(coll, f"station:pos:phone_{i}", phone, monitor_center,
                       .025, dz, .019, M["ink"], monitor_tilt, root,
                       xscale=.76, front_offset=.112, bold=False)
        tilted_ui_box(coll, f"station:pos:state_chip_{i}", monitor_center,
                      .260, dz, (.135, .034),
                      M["screen_ui"] if i == 0 else M["ui_teal"],
                      monitor_tilt, root, front_offset=.110)
        tilted_ui_text(coll, f"station:pos:state_{i}", state, monitor_center,
                       .260, dz, .018, M["white_emit"], monitor_tilt, root,
                       xscale=.74, front_offset=.116, bold=False)
    tilted_ui_box(coll, "station:pos:action_button", monitor_center, .250, -.210,
                  (.230, .052), M["screen_ui"], monitor_tilt, root,
                  front_offset=.106)
    tilted_ui_text(coll, "station:pos:action_text", "CONFIRM COLLECTION", monitor_center,
                   .250, -.210, .023, M["white_emit"], monitor_tilt, root,
                   xscale=.80, front_offset=.114)
    _front_screw(coll, "station:pos:status_led", 2.30, -4.242, 1.704,
                 M["led_green"], root, .006)
    _front_screw(coll, "station:pos:side_power_button", 2.792, -4.285, 1.845,
                 M["steel"], root, .010)

    # Low-profile service keyboard with staggered rows and realistic special keys.
    box(coll, "station:pos:keyboard_base", (1.30, -3.98, 1.435),
        (.990, .380, .050), M["charcoal"], .020,
        (math.radians(4), 0, 0), root, "workstation")
    for row in range(4):
        row_offset = (row % 2) * .018
        for key in range(12):
            part_box(coll, f"station:pos:key_{row}_{key}",
                     (.855 + row_offset + key * .074,
                      -3.845 - row * .066, 1.467 + row * .004),
                     (.057, .044, .012), M["white_metal"], parent=root,
                     sem="workstation")
    part_box(coll, "station:pos:key_space",
             (1.300, -4.117, 1.482), (.330, .046, .012), M["white_metal"],
             parent=root, sem="workstation")
    part_box(coll, "station:pos:key_enter",
             (1.690, -4.052, 1.477), (.100, .050, .012), M["ui_teal"],
             parent=root, sem="workstation")
    box(coll, "station:scale:platform", (3.45, -4.35, 1.43),
        (1.10, .70, .065), M["steel"], .012, parent=root, sem="workstation")
    box(coll, "station:scale:display", (3.84, -4.00, 1.53),
        (.31, .10, .18), M["screen"], .010, parent=root, sem="workstation")
    box(coll, "station:scanner:base", (.78, -4.22, 1.47),
        (.24, .26, .16), M["charcoal"], .012, parent=root, sem="workstation")
    box(coll, "station:scanner:head", (.78, -4.12, 1.68),
        (.19, .12, .26), M["glass_dark"], .025,
        (math.radians(-16), 0, 0), root, "workstation")
    box(coll, "station:label_printer:body", (4.82, -5.30, 1.24),
        (.58, .49, .38), M["white_metal"], .035, parent=root, sem="workstation")
    box(coll, "station:label_printer:slot", (4.82, -5.03, 1.27),
        (.36, .025, .065), M["black"], .006, parent=root, sem="workstation")
    box(coll, "station:receipt_printer:body", (1.15, -4.42, 1.54),
        (.38, .38, .25), M["white_metal"], .025, parent=root, sem="workstation")
    box(coll, "station:receipt_printer:paper", (1.15, -4.20, 1.58),
        (.24, .018, .12), M["label"], .004, parent=root, sem="workstation")
    cyl(coll, "station:tape_dispenser:roll", (4.08, -5.22, 1.30),
         .15, .09, M["tape"], 28, (math.pi / 2, 0, 0), root,
         "workstation", .003)
    cyl(coll, "station:tape_dispenser:hub", (4.08, -5.165, 1.30),
         .050, .11, M["charcoal"], 24, (math.pi / 2, 0, 0), root,
         "workstation", .002)

    # Ergonomic operator chair with five-star base and casters.
    cyl(coll, "station:chair:column", (2.45, -5.72, .62), .055, .72,
         M["steel"], 24, parent=root, sem="furniture", bevel=.004)
    box(coll, "station:chair:seat", (2.45, -5.72, .93),
        (.66, .66, .15), M["charcoal"], .075, parent=root, sem="furniture")
    box(coll, "station:chair:back", (2.45, -6.00, 1.48),
        (.64, .13, .86), M["charcoal"], .085,
        (math.radians(-7), 0, 0), root, "furniture")
    for i in range(5):
        angle = math.tau * i / 5
        ex = 2.45 + math.cos(angle) * .40
        ey = -5.72 + math.sin(angle) * .40
        tube(coll, f"station:chair:star_arm_{i}",
             ((2.45, -5.72, .34), (ex, ey, .22)), .032,
             M["steel"], root, "furniture_detail")
        cyl(coll, f"station:chair:caster_{i}", (ex, ey, .16), .055, .045,
             M["rubber"], 16, (math.pi / 2, 0, angle), root,
             "furniture_detail", .002)

    # Service equipment: parcel trolley, CCTV, extinguisher, data cabinet and conduits.
    for px in (-5.40, -4.65):
        cyl(coll, f"station:trolley:wheel_{px:.2f}", (px, -1.24, .23),
             .16, .075, M["rubber"], 20, (math.pi / 2, 0, 0), root,
             "equipment", .003)
    box(coll, "station:trolley:platform", (-5.02, -1.25, .27),
        (.92, .62, .095), M["steel"], .012, parent=root, sem="equipment")
    tube(coll, "station:trolley:handle",
         ((-5.42, -1.52, .30), (-5.42, -1.52, 1.58),
          (-4.73, -1.52, 1.58), (-4.73, -1.52, .30)),
         .035, M["blue"], root, "equipment")
    cyl(coll, "station:extinguisher:tank", (-5.63, -7.82, .58),
         .14, .82, M["red"], 28, parent=root, sem="safety_equipment", bevel=.008)
    box(coll, "station:extinguisher:label", (-5.63, -7.67, .64),
        (.16, .018, .28), M["label"], .004, parent=root, sem="safety_equipment")
    tube(coll, "station:extinguisher:hose",
         ((-5.56, -7.80, .91), (-5.43, -7.70, .89), (-5.45, -7.66, .63)),
         .018, M["rubber"], root, "safety_equipment")
    box(coll, "station:data_cabinet", (5.78, -7.28, 2.12),
        (.38, .22, 1.30), M["charcoal"], .018, parent=root, sem="equipment")
    for i in range(8):
        box(coll, f"station:data_cabinet:vent_{i}",
            (5.57, -7.16 + i * .025, 2.22), (.018, .012, .70),
            M["black"], .002, parent=root, sem="equipment_detail")
    tube(coll, "station:data_conduit",
         ((5.78, -7.40, 2.76), (5.78, -7.40, 3.60),
          (4.85, -7.40, 3.60)), .025, M["steel"], root, "equipment_detail")
    box(coll, "station:cctv:wall_mount", (5.86, -7.62, 3.47),
        (.23, .20, .18), M["steel"], .012, parent=root, sem="equipment")
    cyl(coll, "station:cctv:camera_body", (5.62, -7.40, 3.36),
         .105, .34, M["white_metal"], 28,
         (0, math.pi / 2, math.radians(-35)), root, "equipment", .006)
    cyl(coll, "station:cctv:lens", (5.48, -7.30, 3.29),
         .072, .025, M["glass_dark"], 24,
         (0, math.pi / 2, math.radians(-35)), root, "equipment", .003)

    # Linear and pendant luminaires match the bright ribbed interior reference.
    for i, x in enumerate((-4.6, -2.3, 0.0, 2.3, 4.6)):
        box(coll, f"station:linear_light_{i}:housing", (x, -4.45, 3.82),
            (1.55, .13, .085), M["white_metal"], .010,
            parent=root, sem="lighting_fixture")
        box(coll, f"station:linear_light_{i}:diffuser", (x, -4.45, 3.765),
            (1.42, .095, .025), M["white_emit"], .006,
            parent=root, sem="lighting_fixture")
        area_light(coll, f"station:linear_light_{i}:area",
                   (x, -4.45, 3.72), 115, (1.30, .22),
                   (1.0, .94, .86), (0, 0, 0), root)
    for i, (x, y) in enumerate(((-4.1, -1.15), (-1.5, -1.15), (1.0, -1.15),
                                (3.7, -1.15), (-3.2, -6.65), (3.4, -6.65))):
        cyl(coll, f"station:pendant_{i}:cable", (x, y, 3.60),
             .010, .58, M["black"], 12, parent=root,
             sem="lighting_fixture", bevel=.001)
        cyl(coll, f"station:pendant_{i}:housing", (x, y, 3.25),
             .105, .28, M["charcoal"], 28, parent=root,
             sem="lighting_fixture", bevel=.009)
        cyl(coll, f"station:pendant_{i}:diffuser", (x, y, 3.105),
             .095, .035, M["white_emit"], 28, parent=root,
             sem="lighting_fixture", bevel=.004)
        area_light(coll, f"station:pendant_{i}:area", (x, y, 3.06),
                   75, (.36, .36), (1.0, .92, .78), (0, 0, 0), root)

    # Back-wall service identity panel and operating notice board.
    box(coll, "station:rear_identity_panel", (2.5, -8.48, 2.15),
        (4.20, .035, 1.65), M["blue"], .016, parent=root, sem="signage")
    text_obj(coll, "station:rear_identity_text", "CAINIAO SERVICE CENTER",
             (2.5, -8.455, 2.48), .345, M["white_emit"], .016,
             parent=root, xscale=.90, sem="signage")
    for i in range(3):
        box(coll, f"station:notice_board_{i}",
            (1.30 + i * 1.18, -8.43, 1.86), (.92, .035, .63),
            M["label"], .008, parent=root, sem="signage")
        for line in range(5):
            part_box(coll, f"station:notice_{i}:line_{line}",
                     (1.30 + i * 1.18, -8.405, 2.03 - line * .085),
                     (.61 - line * .035, .007, .016), M["ink"],
                     parent=root, sem="signage")

    coll["c2w_modeled_parcel_count"] = parcel_total
    coll["c2w_rack_count"] = len(rack_specs)
    coll["c2w_glazed_storefront"] = True
    coll["c2w_working_interior"] = True
    coll["c2w_pos_terminal_detail_level"] = "all_in_one_operational_ui"
    coll["c2w_signage_profile"] = "enlarged_constrained_to_fascia"
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
    box(coll, "site:subgrade", (site_cx, -3.20, -.30),
        (site_w + 1.8, site_d + 2.0, .65), M["concrete"], .018,
        parent=root, sem="site")
    box(coll, "site:paved_apron", (site_cx, -2.55, .025),
        (site_w, site_d, .18), M["concrete"], .014,
        parent=root, sem="site")
    # A real access lane continues toward the camera so wide views terminate
    # on physical ground rather than the world background below the kerb.
    box(coll, "site:foreground_access_lane", (site_cx, 14.65, -.055),
        (site_w + 2.0, 16.0, .18), M["asphalt"], .010,
        parent=root, sem="site")
    part_box(coll, "site:access_lane_edge_line", (site_cx, 7.05, .042),
             (site_w - .25, .11, .018), M["white"], parent=root,
             sem="site_detail")
    # Fine paver joints, staggered brass datum tabs and perimeter kerb.
    for i, x in enumerate([site_cx - site_w / 2 + .7 + i * 1.20 for i in range(34)]):
        part_box(coll, f"site:paver_joint_x_{i}", (x, -2.55, .119),
                 (.012, site_d - .20, .008), M["joint"], parent=root,
                 sem="site_detail")
    for i, y in enumerate([-11.10 + i * 1.20 for i in range(15)]):
        part_box(coll, f"site:paver_joint_y_{i}", (site_cx, y, .119),
                 (site_w - .20, .012, .008), M["joint"], parent=root,
                 sem="site_detail")
        if i % 2:
            for x in (-15.0, -3.0, 9.0):
                part_box(coll, f"site:brass_datum_{i}_{x:+.0f}",
                         (x, y, .125), (.34, .028, .010), M["steel"],
                         parent=root, sem="site_detail")
    box(coll, "site:front_kerb", (site_cx, 6.60, .17),
        (site_w + .25, .34, .34), M["offwhite"], .025,
        parent=root, sem="site_detail")
    box(coll, "site:rear_kerb", (site_cx, -11.72, .15),
        (site_w + .25, .22, .28), M["offwhite"], .020,
        parent=root, sem="site_detail")
    # Continuous slotted drain at the front edge.
    box(coll, "site:trench_drain_frame", (site_cx, 5.93, .15),
        (site_w - .30, .38, .11), M["charcoal"], .008,
        parent=root, sem="site_detail")
    for i, x in enumerate([site_cx - site_w / 2 + .22 + i * .24 for i in range(173)]):
        part_box(coll, f"site:drain_slot_{i}", (x, 5.93, .211),
                 (.065, .30, .018), M["steel"], parent=root,
                 sem="site_detail")

    # The prior revision's three yellow studded plates have been deliberately
    # removed from the public realm.  The paved apron remains continuous and
    # flush at every operating point, as requested.
    coll["c2w_yellow_ground_plate_count"] = 0

    # Stainless bollards protect projecting terminals without blocking access.
    for i, (x, y) in enumerate(((-16.05, .58), (-9.52, .58),
                                (2.55, .58),
                                (5.42, .55), (17.40, .55))):
        cyl(coll, f"site:bollard_{i}:post", (x, y, .58),
             .090, 1.08, M["steel"], 24, parent=root,
             sem="site_detail", bevel=.007)
        cyl(coll, f"site:bollard_{i}:band", (x, y, .82),
             .096, .11, M["white"], 24, parent=root,
             sem="site_detail", bevel=.003)
        box(coll, f"site:bollard_{i}:base", (x, y, .15),
            (.26, .26, .045), M["steel"], .010, parent=root,
            sem="site_detail")
        for j, (dx, dy) in enumerate(((-.08, -.08), (.08, -.08),
                                      (-.08, .08), (.08, .08))):
            cyl(coll, f"site:bollard_{i}:anchor_{j}",
                 (x + dx, y + dy, .184), .010, .030, M["black"], 12,
                 parent=root, sem="site_detail", bevel=.001)
    return coll


def _placed_origin(local_x, local_y, origin, yaw):
    x, y = _xy((local_x, local_y), (origin[0], origin[1]), yaw)
    return (x, y, origin[2])


def build_delivery_reference_row(parent=None, include_site=True,
                                 origin=(0.0, 0.0, 0.0), yaw=0.0):
    """Live pipeline entrypoint: compose the three separately modeled assets."""
    RNG.seed(260831)
    M = materials()
    row = collection("URBAN_V3_DELIVERY_REFERENCE_ROW", parent)
    row["c2w_asset_id"] = ASSET_ID
    row["c2w_pipeline_entrypoint"] = "generate_urban_v3_delivery.build_delivery_reference_row"
    row["c2w_reference_driven"] = True
    row["c2w_scene_asset_inputs"] = 0
    row["c2w_separate_asset_count"] = 3
    row["c2w_layout"] = "single_expanded_row"
    food_origin = _placed_origin(FOOD_CENTER_X, 0, origin, yaw)
    # The shared presentation apron finishes 0.115 m above the row origin;
    # lift the independently grade-correct cabinet so its caster treads rest on
    # that modeled surface instead of being hidden inside it.
    if include_site:
        food_origin = (food_origin[0], food_origin[1], food_origin[2] + .112)
    build_food_delivery_locker(row, food_origin, yaw)
    build_parcel_locker(
        row, _placed_origin(PARCEL_CENTER_X, 0, origin, yaw), yaw)
    build_delivery_station(
        row, _placed_origin(STATION_CENTER_X, 0, origin, yaw), yaw)
    if include_site:
        build_delivery_site(row, origin, yaw)
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
    sky.altitude = .20
    sky.air_density = 1.05
    bg.inputs["Strength"].default_value = .34
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bpy.context.scene.world = world
    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 2.35
    sun_data.angle = math.radians(7.5)
    sun_data.color = (1.0, .91, .78)
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
    scene.view_settings.exposure = -.15
    scene.view_settings.view_transform = "AgX"
    # Blender 4.5 samples are exposed directly on the scene in Eevee Next.
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 12 if preview else 24
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "shadow_pool_size"):
        scene.eevee.shadow_pool_size = "1024"
    scene.camera = None


def camera_specs():
    return [
        ("01_delivery_row_daylight_far.png", (.95, 34.0, 6.8), (.95, -2.5, 1.78), 35, "far"),
        ("02_delivery_row_oblique_far.png", (29.0, 28.5, 8.7), (-.65, -2.3, 2.00), 46, "far"),
        ("03_food_locker_reference_close.png", (FOOD_CENTER_X, 13.65, 3.55),
         (FOOD_CENTER_X, -.05, 1.52), 64, "near_food"),
        ("04_food_locker_hardware_close.png", (FOOD_CENTER_X + 1.15, 4.25, 2.30),
         (FOOD_CENTER_X + .12, .02, 1.46), 62, "detail_food"),
        ("05_parcel_locker_reference_close.png", (-3.2, 10.5, 3.55), (-3.2, -.10, 1.48), 50, "near_parcel"),
        ("06_parcel_terminal_close.png", (-3.2, 3.25, 1.65), (-3.2, .09, 1.28), 66, "detail_parcel"),
        ("07_station_glazed_exterior_close.png", (21.8, 14.5, 5.25), (11.6, -2.35, 2.08), 49, "near_station"),
        ("08_station_open_entry_interior.png", (7.10, 1.05, 1.72), (9.65, -5.55, 1.58), 35, "interior"),
        ("09_station_counter_workstation.png", (14.85, -1.10, 1.92), (13.75, -4.72, 1.30), 32, "interior_close"),
        ("10_station_rack_inventory.png", (8.25, -1.55, 1.72), (8.25, -6.35, 1.48), 40, "inventory_close"),
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
    shelves = {obj.name: obj for obj in bpy.data.objects
               if obj.get("c2w_semantic") == "rack_shelf"}
    parcels = [obj for obj in bpy.data.objects if obj.get("c2w_semantic") == "parcel"]
    errors = []
    worst = 0.0
    for parcel in parcels:
        support_name = parcel.get("c2w_support_name", "")
        shelf = shelves.get(support_name)
        if shelf is None or parcel.get("c2w_support_relation") != "rests_on_modeled_shelf":
            errors.append({"object": parcel.name, "reason": "missing_modeled_shelf"})
            continue
        base_z = min((parcel.matrix_world @ Vector(corner)).z for corner in parcel.bound_box)
        declared = float(parcel.get("c2w_support_top_z", -999.0))
        gap = base_z - declared
        worst = max(worst, abs(gap))
        if abs(gap) > .0015:
            errors.append({
                "object": parcel.name,
                "reason": "floating" if gap > 0 else "penetrating",
                "gap_m": round(gap, 6),
            })
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
        ("parcel_wordmark",
         bpy.data.objects.get(PREFIX + "parcel:fengchao_wordmark"),
         bpy.data.objects.get(PREFIX + "parcel:fengchao_sign_back")),
        ("parcel_terminal_brand",
         bpy.data.objects.get(PREFIX + "parcel:terminal:brand_text"),
         bpy.data.objects.get(PREFIX + "parcel:terminal:brand_header")),
        ("station_primary",
         bpy.data.objects.get(PREFIX + "station:primary_wordmark"),
         bpy.data.objects.get(PREFIX + "station:front_fascia_blue")),
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
        tolerance = .012
        if (lb["xmin"] < cb["xmin"] - tolerance or
                lb["xmax"] > cb["xmax"] + tolerance or
                lb["zmin"] < cb["zmin"] - tolerance or
                lb["zmax"] > cb["zmax"] + tolerance):
            errors.append({"label": label, "reason": "outside_carrier",
                           "measurement": measured[label]})
    return {"measured": measured, "errors": errors, "passed": not errors}


def requested_refinement_audit():
    """Audit delivery5's bright-white, large-clear-glass food-locker refinement."""
    assets = _asset_collections()
    food = assets.get("food_delivery_locker")
    parcel = assets.get("parcel_locker")
    names = [obj.name for obj in bpy.data.objects]
    food_doors = [obj for obj in bpy.data.objects
                  if obj.get("c2w_semantic") == "food_locker_door"]
    white_doors = [obj for obj in food_doors
                   if obj.get("c2w_reference_door_style")
                   == "bright_white_nonmetal_powdercoat_frame_with_large_clear_center_glass"
                   and obj.get("c2w_white_door_leaf") is True
                   and obj.get("c2w_bright_white_nonmetal_finish") is True
                   and obj.get("c2w_door_metallic") == 0.0
                   and obj.get("c2w_true_center_opening") is True
                   and obj.active_material is not None
                   and obj.active_material.name.endswith(
                       "mat:food_door_hygienic_white_powdercoat")]
    food_windows = [obj for obj in bpy.data.objects
                    if obj.get("c2w_clear_tempered_glass") is True
                    and obj.get("c2w_transmission_weight", 0.0) >= .95
                    and obj.get("c2w_uninterrupted_center_glazing") is True
                    and obj.get("c2w_glass_width_ratio", 0.0) >= .80
                    and obj.get("c2w_glass_height_ratio", 0.0) >= .76
                    and obj.active_material is not None
                    and obj.active_material.surface_render_method == "BLENDED"
                    and obj.active_material.name.endswith(
                        "mat:food_door_clear_tempered_glass")]
    food_numbers = [obj for obj in bpy.data.objects
                    if obj.get("c2w_legible_compartment_number") is True
                    and obj.get("c2w_number_printed_on_glass") is True
                    and obj.get("c2w_black_ceramic_ink") is True
                    and obj.get("c2w_nominal_font_size_m", 0.0) >= .155
                    and obj.active_material is not None
                    and obj.active_material.name.endswith(
                        "mat:food_glass_number_black_ceramic_ink")
                    and ":food:door_" in obj.name]
    food_number_keylines = [obj for obj in bpy.data.objects
                            if obj.get("c2w_black_number_contrast_keyline") is True
                            and ":food:door_" in obj.name]
    vertical_glass_bars = [obj for obj in bpy.data.objects
                           if ":food:door_" in obj.name
                           and any(token in obj.name for token in (
                               ":glass_edge_glint", ":glass_vertical_bar",
                               ":glass_highlight_strip"))]
    parcel_numbers = [obj for obj in bpy.data.objects
                      if obj.get("c2w_legible_compartment_number") is True
                      and ":parcel:door_" in obj.name]
    food_ui = [name for name in names if ":food:terminal:" in name]
    parcel_ui = [name for name in names if ":parcel:terminal:" in name]
    station_ui = [name for name in names if ":station:pos:" in name]
    casters = [name for name in names if ":food:caster_" in name and ":wheel" in name]
    leveling_feet = [name for name in names
                     if ":food:leveling_foot_" in name and ":pad" in name]
    food_contents = [obj for obj in bpy.data.objects
                     if obj.get("c2w_semantic") == "locker_contents"]
    obsolete_food_materials = [mat.name for mat in bpy.data.materials
                               if "food_door_graphite" in mat.name
                               or "food_window_frosted" in mat.name
                               or "food_glass_number_white_ink" in mat.name
                               or "tempered_glass_edge_glint" in mat.name]
    compartment_numbers = sorted(int(obj.get("c2w_compartment_number"))
                                 for obj in food_doors)
    expected_numbers = [number for number in range(2, 62) if number != 8]
    yellow_ground = [name for name in names if ":site:tactile_" in name]
    bounds = signage_bounds_audit()
    station_sign = bpy.data.objects.get(PREFIX + "station:primary_wordmark")
    station_body = (station_sign.data.body if station_sign is not None
                    and station_sign.type == "FONT" else "")
    station_measurement = bounds["measured"].get("station_primary", {})
    checks = {
        "no_yellow_ground_building_plates": not yellow_ground,
        "food_locker_has_requested_ten_by_six_layout":
            len(food_doors) == 59
            and food is not None
            and food.get("c2w_column_count", 0) == 10
            and food.get("c2w_row_count", 0) == 6
            and food.get("c2w_compartment_count", 0) == 59
            and food.get("c2w_terminal_count", 0) == 1,
        "every_food_door_is_bright_white_nonmetal_powdercoat_with_real_center_opening":
            len(white_doors) == len(food_doors)
            and food.get("c2w_white_powdercoat_door_count", 0) == len(food_doors),
        "every_food_door_has_large_uninterrupted_clear_transmissive_center_glass":
            len(food_windows) == len(food_doors)
            and food is not None
            and food.get("c2w_clear_tempered_glass_count", 0) == len(food_doors)
            and food.get("c2w_large_glazing_width_ratio", 0.0) >= .80
            and food.get("c2w_large_glazing_height_ratio", 0.0) >= .76,
        "every_food_number_is_large_black_print_on_glass":
            len(food_numbers) == len(food_doors)
            and len(food_number_keylines) == len(food_doors)
            and food.get("c2w_glass_number_count", 0) == len(food_doors),
        "food_glazing_has_no_vertical_bar_or_glint_geometry":
            not vertical_glass_bars
            and food.get("c2w_vertical_glass_bar_count", -1) == 0,
        "food_compartment_number_sequence_is_complete":
            compartment_numbers == expected_numbers,
        "clear_glazing_reveals_modeled_compartment_contents":
            len(food_contents) >= 60
            and food.get("c2w_visible_insulated_bag_count", 0) >= 15,
        "obsolete_graphite_and_frosted_food_materials_removed":
            not obsolete_food_materials,
        "wide_food_locker_has_modeled_distributed_supports":
            len(casters) == 6
            and len(leveling_feet) == 4
            and food.get("c2w_caster_count", 0) == 6
            and food.get("c2w_leveling_foot_count", 0) == 4,
        "every_parcel_door_has_enlarged_number":
            len(parcel_numbers) >= 56
            and parcel is not None
            and parcel.get("c2w_numbered_compartment_count", 0) == len(parcel_numbers),
        "food_terminal_has_modeled_operational_interface": len(food_ui) >= 55,
        "parcel_terminal_has_portrait_operational_interface": len(parcel_ui) >= 150,
        "station_pos_has_all_in_one_operational_interface": len(station_ui) >= 115,
        "station_front_signage_is_english_only":
            station_body == "CAINIAO PARCEL STATION" and station_body.isascii(),
        "station_primary_signage_is_enlarged_for_far_view":
            station_sign is not None
            and station_sign.get("c2w_enlarged_for_far_view") is True
            and station_measurement.get("letter_height_m", 0.0) >= .30,
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


def validate(row, cameras, rendered=False):
    counts = object_counts()
    assets = _asset_collections()
    support = parcel_support_audit()
    refinement = requested_refinement_audit()
    names = [obj.name.lower() for obj in bpy.data.objects]
    forbidden = [name for name in names
                 if any(token in name for token in ("toy", "placeholder", "dummy", "lowpoly"))]
    reference_sizes = {
        filename: (REFERENCES / filename).stat().st_size
        if (REFERENCES / filename).is_file() else 0
        for filename in REFERENCE_URLS
    }
    render_sizes = {
        filename: (RENDERS / filename).stat().st_size
        if (RENDERS / filename).is_file() else 0
        for filename, *_ in camera_specs()
    }
    asset_object_counts = {
        key: len(coll.all_objects) for key, coll in assets.items()
    }
    checks = {
        "three_independently_modeled_asset_collections":
            set(assets) == {"food_delivery_locker", "parcel_locker", "parcel_station"}
            and all(coll.get("c2w_independent_builder") for coll in assets.values()),
        "single_expanded_row_composition":
            row.get("c2w_layout") == "single_expanded_row"
            and row.get("c2w_separate_asset_count") == 3,
        "detailed_food_locker_door_grid":
            counts.get("food_locker_door", 0) == 59
            and counts.get("food_locker_window", 0) == 59
            and counts.get("locker_contents", 0) >= 60
            and assets.get("food_delivery_locker", {}).get("c2w_column_count", 0) == 10
            and assets.get("food_delivery_locker", {}).get("c2w_terminal_count", 0) == 1,
        "detailed_parcel_locker_door_grid":
            counts.get("parcel_locker_door", 0) >= 56
            and assets.get("parcel_locker", {}).get("c2w_canopy_post_count", 0) >= 7,
        "individual_locker_hardware": counts.get("locker_hardware", 0) >= 1200,
        "glazed_station_with_open_real_door":
            counts.get("glazing", 0) >= 10 and counts.get("door_glazing", 0) >= 2,
        "complete_industrial_rack_system":
            counts.get("rack_shelf", 0) >= 19
            and counts.get("rack_structure", 0) >= 100
            and counts.get("rack_detail", 0) >= 500,
        "dense_varied_station_inventory":
            counts.get("parcel", 0) >= 200
            and counts.get("shipping_label", 0) >= 200
            and counts.get("parcel_detail", 0) >= 1400,
        "all_parcels_physically_supported": support["passed"],
        "complete_counter_and_workstation":
            counts.get("workstation", 0) >= 65
            and counts.get("counter", 0) >= 3
            and counts.get("counter_detail", 0) >= 10,
        "modeled_operational_and_safety_equipment":
            counts.get("equipment", 0) >= 8
            and counts.get("safety_equipment", 0) >= 3,
        "modeled_interior_lighting":
            counts.get("lighting_fixture", 0) >= 28 and counts.get("lighting", 0) >= 11,
        "reference_images_archived_in_workspace": min(reference_sizes.values(), default=0) > 4000,
        "daylight_near_far_and_interior_camera_set":
            len(cameras) == 10
            and {role for *_, role in camera_specs()} >= {
                "far", "near_food", "near_parcel", "near_station", "interior",
                "interior_close", "inventory_close",
            },
        "production_generator_metadata":
            row.get("c2w_pipeline_entrypoint")
            == "generate_urban_v3_delivery.build_delivery_reference_row",
        "no_scene_asset_input_blends": row.get("c2w_scene_asset_inputs") == 0,
        "no_placeholder_or_toy_named_assets": not forbidden,
        "all_three_assets_are_complex":
            asset_object_counts.get("food_delivery_locker", 0) >= 1400
            and asset_object_counts.get("parcel_locker", 0) >= 450
            and asset_object_counts.get("parcel_station", 0) >= 2500,
        "requested_delivery5_refinements_passed": refinement["passed"],
    }
    if rendered:
        checks["all_ten_render_artifacts_nonempty"] = min(render_sizes.values(), default=0) > 18000
    return {
        "schema": "legacyworld.urban_asset_manifest.v2",
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
            "food_locker": "expanded ten-column yellow carcass with 59 independent bright-white non-metallic powder-coated door frames, enlarged uninterrupted clear tempered center glazing, large opaque-black ceramic numbers printed directly on the glass, recessed insulated cavities, visible thermal bags, distributed casters and leveling feet",
            "parcel_locker": "long lime-green Fengchao grid with supplied-reference portrait QR terminal and continuous charcoal steel rain canopy",
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
        "render_views": [
            {"file": filename, "role": role, "bytes": render_sizes[filename]}
            for filename, _loc, _target, _lens, role in camera_specs()
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
    selected = {item.strip() for item in
                os.environ.get("C2W_DELIVERY_VIEW_FILTER", "").split(",")
                if item.strip()}
    for filename, cam, role in cameras:
        if selected and not any(filename.startswith(prefix) for prefix in selected):
            continue
        print(f"[delivery] rendering {role}: {filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def main():
    print("[delivery] starting production generator", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    REFERENCES.mkdir(parents=True, exist_ok=True)
    missing = [filename for filename in REFERENCE_URLS
               if not (REFERENCES / filename).is_file()
               or (REFERENCES / filename).stat().st_size <= 4000]
    if missing:
        raise FileNotFoundError(
            "Missing archived user reference images in workspace: " + ", ".join(missing))
    for stale in (OUT / "SUCCESS", OUT / "manifest.json", OUT / "quality_report.json",
                  OUT / "FAILED_AUDIT.json"):
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
    for filename, loc, target, lens, role in camera_specs():
        cameras.append((filename, camera(filename[:-4], loc, target, lens), role))
    initial = validate(row, cameras, rendered=False)
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_runner"] = str((ROOT / "scripts/run_urban_v3_delivery.sh").resolve())
    scene["c2w_asset_id"] = ASSET_ID
    scene["c2w_domain"] = "urban_delivery"
    scene["c2w_reference_driven"] = True
    scene["c2w_pipeline_entrypoint"] = "generate_urban_v3_delivery.build_delivery_reference_row"
    scene["c2w_quality_profile"] = "reference_grade_procedural_modeled_detail"
    scene["c2w_manifest"] = json.dumps(initial, ensure_ascii=False)
    (OUT / "build_audit.json").write_text(
        json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8")
    failed_initial = [key for key, passed in initial["checks"].items() if not passed]
    if failed_initial:
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8")
        raise RuntimeError("Delivery production build audit failed: " + ", ".join(failed_initial))
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    if build_only:
        print(json.dumps({
            "status": "BUILD_ONLY_COMPLETE", "output": str(OUT),
            "objects": initial["object_count"], "support": initial["parcel_support_audit"],
        }, ensure_ascii=False), flush=True)
        return
    if not finalize_existing:
        render_all(cameras)
    if preview or partial:
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
        print(json.dumps({"status": "PREVIEW_COMPLETE", "output": str(OUT)},
                         ensure_ascii=False), flush=True)
        return
    final = validate(row, cameras, rendered=True)
    failed = [key for key, passed in final["checks"].items() if not passed]
    if failed:
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8")
        raise RuntimeError("Delivery production render audit failed: " + ", ".join(failed))
    scene["c2w_manifest"] = json.dumps(final, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    (OUT / "manifest.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8")
    quality = {
        "result": "PASS",
        "all_checks_passed": True,
        "checks": final["checks"],
        "semantic_counts": final["semantic_counts"],
        "asset_object_counts": final["asset_object_counts"],
        "parcel_support_audit": final["parcel_support_audit"],
        "requested_refinement_audit": final["requested_refinement_audit"],
        "reference_observations": final["reference_observations"],
        "note": "Quality gates require named operational subassemblies and physical parcel support; raw object count alone is not accepted.",
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf8")
    (OUT / "SUCCESS").write_text(
        f"{OUTPUT_ID} production generation and validation complete\n", encoding="utf8")
    print(json.dumps({
        "status": "SUCCESS", "output": str(OUT),
        "objects": final["object_count"], "checks": final["checks"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
