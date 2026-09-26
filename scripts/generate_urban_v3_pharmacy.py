"""Reference-driven production pharmacy assets for the Urban-v3 pipeline.

This is the production generator used by ``run_urban_v3_pharmacy.sh``.  It
builds two reference-specific, fully modeled pharmacy archetypes in one row:

* a suburban CVS-style red-brick store with a white classical portico; and
* a dark, urban Well-style high-street pharmacy with an illuminated shopfront.

Both buildings have traversable shells and independently modeled, lit retail
interiors.  Inventory is supported by a modeled shelf deck and is built from
multi-part cartons, tubes and bottles with printed faces; it is not a field of
floating coloured cubes.  The fifth revision also has a verified clear CVS
entrance, continuous storefront module runs, physically separated porcelain
floor tiles, a professional dispensing counter and a manufactured prescription
collection terminal.  Its public forecourt is pedestrian-only and contains no
parking bays or planting.  ``build_pharmacy_reference_row`` is the production
entrypoint used by :mod:`urban_assets`, while ``main`` creates the isolated
validation scene and its daylight near/far/interior renders.
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
import random
import shutil
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
ASSET_ID = "urban_v3_pharmacy5"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / ASSET_ID
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
BLEND = OUT / f"{ASSET_ID}.blend"
PREFIX = "pharmacy5:"
RNG = random.Random(260831)
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

REFERENCE_URLS = [
    "https://www.shutterstock.com/image-photo/cvs-pharmacy-store-manassas-va-260nw-2497685195.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQp_YERY2mUuDY08qx29NVfCBl4MICFLqjJ9xTL7aWv3Q&s=10",
    "https://media.cgtrader.com/variants/qbSRHg4HootwDYzfHqKHcmd9/78add9c2f02fbd73a43ffb3970be38683c5f15eff6ca849dc78c644f4ff9ce1b/Pharmacy%20Low-poly%203D%20model%20c4d%20003.webp",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRb_M7lrtmAXVZxQ8rD81H3s_OEueWpqEcJxkTezMX8SQ&s=10",
]
REFERENCE_FILES = [
    "exterior_01.jpg",
    "exterior_02.jpg",
    "interior_01.webp",
    "interior_02.jpg",
]

sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all45 as G  # noqa: E402

G.PREFIX = PREFIX

# The validation composition is intentionally compact and human-scaled.  The
# same store builders are used by the live urban pipeline adapter.
CVS_X = -18.0
WELL_X = 17.0
CVS_ENTRY_X = CVS_X + 2.1
WELL_ENTRY_X = WELL_X + 9.5


# ---------------------------------------------------------------------------
# Scene and geometry helpers


def collection(name: str, parent=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def semantic(obj, value: str, detail: bool = False):
    obj["c2w_semantic"] = value
    if detail:
        obj["c2w_quality_detail"] = True
    return obj


def box(
    coll,
    name,
    loc,
    dims,
    material,
    bevel=0.025,
    rot=(0.0, 0.0, 0.0),
    sem="architecture",
):
    # Direct datablock construction is several times faster than bpy.ops once
    # thousands of inventory instances exist, while retaining applied-scale
    # geometry so bevel widths remain metrically correct.
    hx, hy, hz = dims[0] / 2, dims[1] / 2, dims[2] / 2
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
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    if bevel > 0:
        G.add_bevel(obj, bevel, 2 if bevel >= 0.025 else 1)
    return semantic(
        obj, sem, detail=sem in {"architectural_detail", "fixture", "signage"}
    )


def cyl(
    coll,
    name,
    loc,
    radius,
    depth,
    material,
    vertices=32,
    rot=(0.0, 0.0, 0.0),
    sem="fixture",
    bevel=0.012,
):
    verts = []
    for z in (-depth / 2, depth / 2):
        verts.extend(
            (
                radius * math.cos(2 * math.pi * i / vertices),
                radius * math.sin(2 * math.pi * i / vertices),
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
    for poly in mesh.polygons:
        if len(poly.vertices) == 4:
            poly.use_smooth = True
    if bevel > 0:
        G.add_bevel(obj, bevel, 1)
    return semantic(
        obj, sem, detail=sem in {"architectural_detail", "fixture", "signage"}
    )


def curve_tube(coll, name, points, radius, material, cyclic=False, sem="fixture"):
    cu = bpy.data.curves.new(PREFIX + name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 2
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    sp = cu.splines.new("NURBS")
    sp.points.add(len(points) - 1)
    for p, co in zip(sp.points, points):
        p.co = (*co, 1.0)
    sp.use_cyclic_u = cyclic
    sp.order_u = min(3, len(points))
    sp.use_endpoint_u = not cyclic
    cu.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, cu)
    coll.objects.link(obj)
    return semantic(obj, sem, detail=True)


def text_obj(
    coll,
    name,
    body,
    loc,
    size,
    material,
    extrude=0.045,
    align="CENTER",
    bold=True,
    sem="signage",
    xscale=1.0,
):
    cu = bpy.data.curves.new(PREFIX + name, "FONT")
    cu.body = body
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = min(0.018, extrude * 0.22)
    font_path = FONT_BOLD if bold else FONT_REGULAR
    if Path(font_path).is_file():
        cu.font = bpy.data.fonts.load(font_path, check_existing=True)
    cu.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, cu)
    coll.objects.link(obj)
    # Text lies in local XY with a +Z normal.  Rotate to face the storefront's
    # +Y side and mirror local X so the front elevation reads correctly.
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.scale.x = -xscale
    return semantic(obj, sem, detail=True)


def area_light(coll, name, loc, energy, size, color=(1.0, 0.93, 0.82), rot=(0, 0, 0)):
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
    obj["c2w_semantic"] = "lighting"
    return obj


def camera(name, loc, target, lens=48):
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
    obj["c2w_view_role"] = name
    return obj


# Shared low-overhead meshes for the hundreds of small package components.
SHARED_MESHES = {}


def _cube_mesh(key, material):
    cache_key = ("cube", key, material.name)
    if cache_key in SHARED_MESHES:
        return SHARED_MESHES[cache_key]
    mesh = bpy.data.meshes.new(PREFIX + "shared_" + key)
    # A single baked chamfered mesh is shared by every package instance.  This
    # keeps the scene light while avoiding the razor-edged cuboids that made
    # the earlier stock read as coloured blocks in close views.
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.bevel(
        bm,
        geom=list(bm.edges),
        offset=0.028,
        segments=2,
        affect="EDGES",
    )
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    SHARED_MESHES[cache_key] = mesh
    return mesh


def _cylinder_mesh(key, material, sides=24):
    cache_key = ("cyl", key, material.name, sides)
    if cache_key in SHARED_MESHES:
        return SHARED_MESHES[cache_key]
    verts = []
    for z in (-0.5, 0.5):
        verts.extend(
            (
                0.5 * math.cos(2 * math.pi * i / sides),
                0.5 * math.sin(2 * math.pi * i / sides),
                z,
            )
            for i in range(sides)
        )
    faces = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, sides * 2))]
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i, j, sides + j, sides + i))
    mesh = bpy.data.meshes.new(PREFIX + "shared_" + key)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    SHARED_MESHES[cache_key] = mesh
    return mesh


def _lathed_mesh(key, material, profile, sides=24, ribbed=False):
    """Create a reusable rotational package mesh from a normalized profile."""
    cache_key = ("lathe", key, material.name, tuple(profile), sides, ribbed)
    if cache_key in SHARED_MESHES:
        return SHARED_MESHES[cache_key]
    verts = []
    for radius, z in profile:
        for i in range(sides):
            # Alternating radii form real grip ribs on child-resistant caps.
            rib = 1.0 + (0.032 if ribbed and i % 2 == 0 else 0.0)
            a = 2 * math.pi * i / sides
            verts.append((radius * rib * math.cos(a), radius * rib * math.sin(a), z))
    faces = []
    faces.append(tuple(range(sides - 1, -1, -1)))
    rings = len(profile)
    for ring in range(rings - 1):
        a0 = ring * sides
        a1 = (ring + 1) * sides
        for i in range(sides):
            j = (i + 1) % sides
            faces.append((a0 + i, a0 + j, a1 + j, a1 + i))
    faces.append(tuple((rings - 1) * sides + i for i in range(sides)))
    mesh = bpy.data.meshes.new(PREFIX + "shared_" + key)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    for poly in mesh.polygons:
        if len(poly.vertices) == 4:
            # Bottle shoulders should be smooth; alternating cap segments stay
            # faceted so their child-resistant grip ribs catch real highlights.
            poly.use_smooth = not ribbed
    SHARED_MESHES[cache_key] = mesh
    return mesh


def _tube_mesh(key, material):
    """Reusable tapered squeeze-tube body with a flattened crimped shoulder."""
    cache_key = ("tube", key, material.name)
    if cache_key in SHARED_MESHES:
        return SHARED_MESHES[cache_key]
    levels = [
        (-0.50, 0.34, 0.36),
        (-0.40, 0.47, 0.46),
        (0.34, 0.50, 0.50),
        (0.46, 0.48, 0.34),
        (0.50, 0.42, 0.22),
    ]
    verts = []
    for z, hx, hy in levels:
        verts.extend(((-hx, -hy, z), (hx, -hy, z), (hx, hy, z), (-hx, hy, z)))
    faces = [(0, 3, 2, 1)]
    for level in range(len(levels) - 1):
        a = level * 4
        b = (level + 1) * 4
        for i in range(4):
            j = (i + 1) % 4
            faces.append((a + i, a + j, b + j, b + i))
    top = (len(levels) - 1) * 4
    faces.append((top, top + 1, top + 2, top + 3))
    mesh = bpy.data.meshes.new(PREFIX + "shared_" + key)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    SHARED_MESHES[cache_key] = mesh
    return mesh


def instance_part(
    coll, name, loc, dims, material, shape="cube", rot=0.0, sem="product_detail"
):
    key = material.name.split(":")[-1] + "_" + shape
    if shape == "cube":
        mesh = _cube_mesh(key, material)
    elif shape == "cylinder":
        mesh = _cylinder_mesh(key, material)
    elif shape == "bottle":
        mesh = _lathed_mesh(
            key,
            material,
            [
                (0.43, -0.50),
                (0.48, -0.46),
                (0.50, -0.38),
                (0.50, 0.18),
                (0.48, 0.27),
                (0.42, 0.35),
                (0.32, 0.42),
                (0.30, 0.50),
            ],
            28,
        )
    elif shape == "cap":
        mesh = _lathed_mesh(
            key,
            material,
            [(0.48, -0.50), (0.53, -0.43), (0.54, 0.32), (0.50, 0.45), (0.42, 0.50)],
            32,
            True,
        )
    elif shape == "tube":
        mesh = _tube_mesh(key, material)
    else:
        raise ValueError(f"Unsupported instanced part shape: {shape}")
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    obj.scale = dims
    obj.rotation_euler.z = rot
    obj["c2w_semantic"] = sem
    return obj


def local_xy(cx, cy, lx, ly, rot):
    co, si = math.cos(rot), math.sin(rot)
    return cx + lx * co - ly * si, cy + lx * si + ly * co


# ---------------------------------------------------------------------------
# Materials


def emission_material(name, color, strength=5.0):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = 0.28
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def glass_material(name, tint, alpha=0.22):
    """Physically plausible low-iron glass that still reads in Eevee.

    A pure alpha material made the previous storefront look like a missing
    wall.  Transmission, Fresnel and a modest alpha keep reflections and pane
    edges visible while preserving a clear view of the modeled interior.
    """
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*tint, 1)
    bsdf.inputs["Roughness"].default_value = 0.12
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = 1.45
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.72
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.22
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*tint, alpha)
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    return mat


def terrazzo_material(name, base, fleck_a, fleck_b):
    """Fine commercial terrazzo, sized to read as material rather than tiles."""
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 420.0
    noise.inputs["Detail"].default_value = 1.6
    noise.inputs["Roughness"].default_value = 0.32
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*base, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (*fleck_a, 1)
    noise_b = nt.nodes.new("ShaderNodeTexNoise")
    noise_b.inputs["Scale"].default_value = 610.0
    noise_b.inputs["Detail"].default_value = 1.0
    mask_b = nt.nodes.new("ShaderNodeValToRGB")
    mask_b.color_ramp.interpolation = "CONSTANT"
    mask_b.color_ramp.elements[0].position = 0.76
    mask_b.color_ramp.elements[0].color = (0, 0, 0, 1)
    mask_b.color_ramp.elements[1].position = 0.77
    mask_b.color_ramp.elements[1].color = (1, 1, 1, 1)
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs["Color2"].default_value = (*fleck_b, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.035
    bump.inputs["Distance"].default_value = 0.003
    bsdf.inputs["Roughness"].default_value = 0.34
    nt.links.new(coords.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(coords.outputs["Generated"], noise_b.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(noise_b.outputs["Fac"], mask_b.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(mask_b.outputs["Color"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def porcelain_tile_material(name, base, aggregate, roughness=0.34):
    """Commercial porcelain with restrained aggregate and micro-surface relief.

    The actual tile boundaries are modeled by :func:`modeled_tile_floor`; this
    shader supplies the small aggregate, tonal drift and grazing-angle breakup
    that remain visible inside each individual slab.
    """
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 285.0
    fine.inputs["Detail"].default_value = 2.6
    fine.inputs["Roughness"].default_value = 0.46
    fine.inputs["Distortion"].default_value = 0.12
    broad = nt.nodes.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = 7.5
    broad.inputs["Detail"].default_value = 3.0
    broad.inputs["Roughness"].default_value = 0.58
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.27
    ramp.color_ramp.elements[0].color = tuple(max(0, c * 0.88) for c in base) + (1,)
    mid = ramp.color_ramp.elements.new(0.58)
    mid.color = (*base, 1)
    ramp.color_ramp.elements[1].position = 0.79
    ramp.color_ramp.elements[1].color = tuple(
        min(1, c * 1.08 + 0.012) for c in aggregate
    ) + (1,)
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.12
    mix.inputs["Color2"].default_value = (0.93, 0.94, 0.92, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.075
    bump.inputs["Distance"].default_value = 0.0018
    bsdf.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.10
        bsdf.inputs["Coat Roughness"].default_value = 0.22
    nt.links.new(coords.outputs["Generated"], fine.inputs["Vector"])
    nt.links.new(coords.outputs["Generated"], broad.inputs["Vector"])
    nt.links.new(fine.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(broad.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(fine.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def engineered_surface_material(name, base, mineral, roughness=0.28, metallic=0.0):
    """Fine-grained manufactured finish for counters and sheet-metal shells."""
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 190.0
    noise.inputs["Detail"].default_value = 3.2
    noise.inputs["Roughness"].default_value = 0.52
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.34
    ramp.color_ramp.elements[0].color = tuple(max(0, c * 0.88) for c in base) + (1,)
    ramp.color_ramp.elements[1].position = 0.71
    ramp.color_ramp.elements[1].color = (*mineral, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.0012
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(coords.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def printed_label_material(name):
    """Matte medicine-label stock with fine text-like horizontal printing."""
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 16.0
    wave.inputs["Distortion"].default_value = 2.1
    wave.inputs["Detail"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = (0.70, 0.70, 0.66, 1)
    mid = ramp.color_ramp.elements.new(0.50)
    mid.color = (0.12, 0.14, 0.14, 1)
    ramp.color_ramp.elements[1].position = 0.58
    ramp.color_ramp.elements[1].color = (0.70, 0.70, 0.66, 1)
    bsdf.inputs["Roughness"].default_value = 0.58
    nt.links.new(coords.outputs["Generated"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def tile_material(name, c1, c2, grout, scale=3.4):
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexBrick")
    tex.offset = 0.5
    tex.offset_frequency = 2
    tex.inputs["Color1"].default_value = (*c1, 1)
    tex.inputs["Color2"].default_value = (*c2, 1)
    tex.inputs["Mortar"].default_value = (*grout, 1)
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Mortar Size"].default_value = 0.018
    if "Row Height" in tex.inputs:
        tex.inputs["Row Height"].default_value = 0.45
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.14
    bump.inputs["Distance"].default_value = 0.008
    bsdf.inputs["Roughness"].default_value = 0.48
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def masonry_material(name, c1, c2, mortar, brick_width=0.235, row_height=0.078):
    """Metric masonry mapped so courses stay horizontal on every upright face."""
    mat = G.clear_material(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    nt.links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.inputs["Color1"].default_value = (*c1, 1)
    brick.inputs["Color2"].default_value = (*c2, 1)
    brick.inputs["Mortar"].default_value = (*mortar, 1)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.010
    brick.inputs["Mortar Smooth"].default_value = 0.04
    brick.inputs["Brick Width"].default_value = brick_width
    brick.inputs["Row Height"].default_value = row_height
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    # Low-frequency kiln variation breaks identical courses without hiding joints.
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.6
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.68
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.68, 0.68, 0.68, 1)
    ramp.color_ramp.elements[1].color = (1.10, 1.10, 1.10, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.28
    nt.links.new(brick.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    joint_bump = nt.nodes.new("ShaderNodeBump")
    joint_bump.inputs["Strength"].default_value = 0.36
    joint_bump.inputs["Distance"].default_value = 0.018
    joint_bump.invert = True
    nt.links.new(brick.outputs["Fac"], joint_bump.inputs["Height"])
    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 95.0
    grit.inputs["Detail"].default_value = 3.0
    nt.links.new(mapping.outputs["Vector"], grit.inputs["Vector"])
    grit_bump = nt.nodes.new("ShaderNodeBump")
    grit_bump.inputs["Strength"].default_value = 0.09
    grit_bump.inputs["Distance"].default_value = 0.004
    nt.links.new(grit.outputs["Fac"], grit_bump.inputs["Height"])
    nt.links.new(joint_bump.outputs["Normal"], grit_bump.inputs["Normal"])
    nt.links.new(grit_bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def materials():
    M = {
        "brick_red": masonry_material(
            "cvs_weathered_red_brick",
            (0.17, 0.027, 0.013),
            (0.35, 0.072, 0.028),
            (0.28, 0.25, 0.21),
        ),
        "brick_dark": masonry_material(
            "well_blue_black_brick",
            (0.018, 0.024, 0.031),
            (0.060, 0.071, 0.081),
            (0.12, 0.13, 0.14),
        ),
        "white_stucco": G.material(
            "warm_white_stucco", (0.60, 0.58, 0.53), 0.72, 0, 0.08
        ),
        "white_paint": G.material(
            "satin_off_white_joinery", (0.72, 0.71, 0.67), 0.33, 0, 0.018
        ),
        "red": G.material("cvs_brand_red", (0.54, 0.004, 0.008), 0.26, 0.04, 0.012),
        "red_emit": emission_material("cvs_red_backlit", (0.72, 0.004, 0.008), 1.8),
        "navy": G.material(
            "well_deep_navy_cladding", (0.006, 0.014, 0.025), 0.24, 0.38, 0.018
        ),
        "navy_matte": G.material(
            "well_matte_blue_black", (0.010, 0.022, 0.036), 0.48, 0.10, 0.025
        ),
        "cyan": emission_material("well_cyan_light", (0.04, 0.48, 0.72), 3.8),
        "white_emit": emission_material(
            "clean_white_emission", (0.86, 0.84, 0.78), 3.2
        ),
        "warm_emit": emission_material("warm_downlight", (1.0, 0.60, 0.26), 3.0),
        "glass": glass_material("low_iron_storefront_glass", (0.10, 0.17, 0.19), 0.34),
        "glass_door": glass_material("entry_safety_glass", (0.11, 0.18, 0.20), 0.29),
        "frost": glass_material(
            "pharmacy_frosted_privacy_glass", (0.46, 0.60, 0.62), 0.64
        ),
        "aluminum": G.material(
            "brushed_aluminum_frames", (0.25, 0.28, 0.29), 0.23, 0.82, 0.018
        ),
        "black": G.material(
            "powder_black_metal", (0.008, 0.010, 0.012), 0.31, 0.55, 0.02
        ),
        "steel": G.material(
            "brushed_stainless_steel", (0.39, 0.42, 0.43), 0.25, 0.88, 0.02
        ),
        "roof": G.roof_tile_material(
            "charcoal_asphalt_shingle", (0.025, 0.029, 0.032), (0.085, 0.09, 0.092)
        ),
        "floor_cvs": terrazzo_material(
            "cvs_cream_terrazzo_substrate",
            (0.52, 0.51, 0.47),
            (0.24, 0.22, 0.19),
            (0.72, 0.68, 0.60),
        ),
        "floor_well": terrazzo_material(
            "well_pale_terrazzo_substrate",
            (0.61, 0.64, 0.63),
            (0.28, 0.31, 0.30),
            (0.76, 0.74, 0.68),
        ),
        "floor_cvs_tiles": [
            porcelain_tile_material(
                "cvs_porcelain_tile_warm", (0.58, 0.57, 0.53), (0.72, 0.69, 0.61), 0.36
            ),
            porcelain_tile_material(
                "cvs_porcelain_tile_light", (0.62, 0.61, 0.57), (0.77, 0.73, 0.65), 0.34
            ),
            porcelain_tile_material(
                "cvs_porcelain_tile_cool", (0.55, 0.56, 0.55), (0.68, 0.69, 0.66), 0.38
            ),
        ],
        "floor_well_tiles": [
            porcelain_tile_material(
                "well_porcelain_tile_silver",
                (0.62, 0.65, 0.64),
                (0.78, 0.77, 0.71),
                0.31,
            ),
            porcelain_tile_material(
                "well_porcelain_tile_pearl",
                (0.67, 0.68, 0.65),
                (0.80, 0.79, 0.73),
                0.30,
            ),
            porcelain_tile_material(
                "well_porcelain_tile_grey", (0.56, 0.59, 0.59), (0.70, 0.72, 0.69), 0.35
            ),
        ],
        "tile_grout": G.material(
            "commercial_epoxy_tile_grout", (0.18, 0.19, 0.18), 0.86, 0, 0.018
        ),
        "ceiling": G.material(
            "acoustic_ceiling_tile", (0.67, 0.68, 0.65), 0.82, 0, 0.025
        ),
        "clinical": engineered_surface_material(
            "clinical_white_laminate", (0.72, 0.74, 0.72), (0.80, 0.81, 0.77), 0.36
        ),
        "clinical_blue": G.material(
            "clinical_blue_laminate", (0.10, 0.35, 0.45), 0.38, 0.02, 0.018
        ),
        "counter": engineered_surface_material(
            "counter_mineral_solid_surface",
            (0.57, 0.59, 0.57),
            (0.72, 0.73, 0.68),
            0.27,
        ),
        "counter_dark": G.material(
            "counter_shadow_gap", (0.055, 0.065, 0.066), 0.51, 0.14, 0.02
        ),
        "kiosk_shell": engineered_surface_material(
            "kiosk_powder_coated_sheet_metal",
            (0.36, 0.41, 0.43),
            (0.45, 0.49, 0.49),
            0.43,
            0.12,
        ),
        "kiosk_inset": engineered_surface_material(
            "kiosk_dark_service_inset",
            (0.035, 0.045, 0.049),
            (0.075, 0.085, 0.088),
            0.48,
            0.18,
        ),
        "cable": G.material(
            "equipment_cable_rubber", (0.012, 0.014, 0.014), 0.72, 0, 0.025
        ),
        "screen_dim": emission_material(
            "dim_interface_graphic", (0.055, 0.28, 0.37), 0.48
        ),
        "amber_emit": emission_material(
            "equipment_status_amber", (1.0, 0.31, 0.015), 2.1
        ),
        "green_emit": emission_material(
            "equipment_status_green", (0.015, 0.60, 0.22), 2.0
        ),
        "shelf": G.material(
            "powdercoated_retail_shelf", (0.50, 0.52, 0.50), 0.40, 0.34, 0.015
        ),
        "shelf_white": G.material(
            "white_retail_shelf", (0.69, 0.70, 0.67), 0.38, 0.16, 0.012
        ),
        "price_rail": G.material(
            "transparent_price_rail", (0.62, 0.70, 0.71), 0.25, 0.08, 0.01, 0.52
        ),
        "rubber": G.material(
            "black_entry_rubber", (0.025, 0.028, 0.027), 0.91, 0, 0.08
        ),
        "concrete": G.material(
            "weathered_paving_concrete", (0.36, 0.35, 0.32), 0.86, 0, 0.10
        ),
        "concrete_light": G.material(
            "portico_cast_stone", (0.54, 0.51, 0.45), 0.77, 0, 0.055
        ),
        "forecourt_paver": engineered_surface_material(
            "flamed_granite_pedestrian_paver",
            (0.28, 0.29, 0.28),
            (0.38, 0.38, 0.35),
            0.78,
        ),
        "poster_blue": G.material("poster_blue", (0.025, 0.30, 0.64), 0.37, 0, 0.015),
        "poster_red": G.material("poster_red", (0.72, 0.035, 0.025), 0.37, 0, 0.015),
        "poster_teal": G.material("poster_teal", (0.03, 0.47, 0.43), 0.37, 0, 0.015),
        "poster_white": G.material("poster_white", (0.92, 0.91, 0.84), 0.41, 0, 0.012),
        "wood": G.wood_material(
            "warm_consultation_oak", (0.13, 0.055, 0.018), (0.48, 0.25, 0.08)
        ),
        "yellow": G.material(
            "tactile_and_safety_yellow", (0.92, 0.55, 0.018), 0.65, 0, 0.035
        ),
        "paper": G.material("matte_printed_paper", (0.67, 0.65, 0.59), 0.74, 0, 0.012),
        "chrome": G.material("polished_chrome", (0.48, 0.51, 0.52), 0.12, 0.95, 0.008),
        "screen": emission_material(
            "legible_interface_screen", (0.025, 0.18, 0.32), 1.25
        ),
        "screen_glass": glass_material(
            "interface_cover_glass", (0.025, 0.055, 0.070), 0.42
        ),
        "shadow_line": G.material(
            "architectural_recess_shadow", (0.055, 0.060, 0.058), 0.72, 0, 0.012
        ),
        "red_dark": G.material(
            "cvs_channel_letter_returns", (0.19, 0.003, 0.006), 0.38, 0.05, 0.010
        ),
        "navy_edge": G.material(
            "well_fascia_shadow_reveal", (0.002, 0.006, 0.010), 0.56, 0.16, 0.012
        ),
    }
    # Carton bodies are deliberately restrained and paper-like.  Strong brand
    # colours are limited to printed bands, as on real pharmacy packaging.
    package_colors = [
        (0.78, 0.79, 0.75),
        (0.69, 0.75, 0.78),
        (0.78, 0.72, 0.70),
        (0.70, 0.78, 0.73),
        (0.80, 0.76, 0.67),
        (0.74, 0.70, 0.79),
        (0.68, 0.77, 0.78),
        (0.79, 0.71, 0.75),
        (0.73, 0.79, 0.69),
        (0.82, 0.80, 0.73),
        (0.70, 0.72, 0.78),
        (0.78, 0.74, 0.68),
    ]
    M["packages"] = [
        G.material(f"package_{i:02d}", color, 0.42, 0, 0.012)
        for i, color in enumerate(package_colors)
    ]
    accent_colors = [
        (0.025, 0.18, 0.48),
        (0.62, 0.018, 0.020),
        (0.018, 0.34, 0.18),
        (0.78, 0.34, 0.018),
        (0.31, 0.08, 0.47),
        (0.018, 0.43, 0.52),
        (0.66, 0.16, 0.31),
        (0.08, 0.38, 0.12),
    ]
    M["accents"] = [
        G.material(f"package_accent_{i:02d}", c, 0.39, 0, 0.010)
        for i, c in enumerate(accent_colors)
    ]
    bottle_colors = [
        (0.44, 0.18, 0.025),
        (0.69, 0.67, 0.58),
        (0.73, 0.76, 0.72),
        (0.12, 0.30, 0.42),
        (0.24, 0.46, 0.34),
        (0.52, 0.25, 0.12),
    ]
    M["bottles"] = [
        G.material(f"medicine_bottle_{i:02d}", c, 0.31, 0, 0.018)
        for i, c in enumerate(bottle_colors)
    ]
    M["label"] = printed_label_material("package_print_label")
    M["cap"] = G.material("bottle_cap_white", (0.80, 0.81, 0.77), 0.48, 0.05, 0.015)
    M["cap_blue"] = G.material("bottle_cap_blue", (0.12, 0.26, 0.50), 0.40, 0.03, 0.012)
    return M


# ---------------------------------------------------------------------------
# Interior floor construction


def modeled_tile_floor(
    coll, name, cx, cy, width, depth, M, tile_materials, module=0.60, gap=0.006
):
    """Build a single efficient mesh containing thousands of separate tiles.

    Each tile is a closed six-face slab.  The small physical gap between slabs
    exposes a recessed epoxy-grout bed, so joints remain real geometry in close
    views instead of relying on a flat colour texture.  Three restrained finish
    variants are assigned deterministically to prevent visible repetition.
    """
    grout = box(
        coll,
        name + ":grout_bed",
        (cx, cy, 0.069),
        (width, depth, 0.138),
        M["tile_grout"],
        0.002,
        sem="interior_shell",
    )
    nx = max(1, math.ceil(width / module))
    ny = max(1, math.ceil(depth / module))
    cell_w = width / nx
    cell_d = depth / ny
    verts = []
    faces = []
    material_indices = []
    z0 = 0.138
    for iy in range(ny):
        y0 = cy - depth / 2 + iy * cell_d + gap / 2
        y1 = cy - depth / 2 + (iy + 1) * cell_d - gap / 2
        for ix in range(nx):
            x0 = cx - width / 2 + ix * cell_w + gap / 2
            x1 = cx - width / 2 + (ix + 1) * cell_w - gap / 2
            # Sub-quarter-millimetre lippage is subtle in elevation but catches
            # realistic grazing highlights across the large shop floor.
            z1 = 0.140 + (((ix * 17 + iy * 11) % 5) - 2) * 0.000045
            start = len(verts)
            verts.extend(
                (
                    (x0, y0, z0),
                    (x1, y0, z0),
                    (x1, y1, z0),
                    (x0, y1, z0),
                    (x0, y0, z1),
                    (x1, y0, z1),
                    (x1, y1, z1),
                    (x0, y1, z1),
                )
            )
            faces.extend(
                (
                    (start, start + 1, start + 2, start + 3),
                    (start + 4, start + 7, start + 6, start + 5),
                    (start, start + 4, start + 5, start + 1),
                    (start + 1, start + 5, start + 6, start + 2),
                    (start + 2, start + 6, start + 7, start + 3),
                    (start + 4, start, start + 3, start + 7),
                )
            )
            material_indices.extend(
                [((ix * 13 + iy * 7) // 3) % len(tile_materials)] * 6
            )
    mesh = bpy.data.meshes.new(PREFIX + name + ":modeled_tile_mesh")
    mesh.from_pydata(verts, [], faces)
    for material in tile_materials:
        mesh.materials.append(material)
    for poly, index in zip(mesh.polygons, material_indices):
        poly.material_index = index
    obj = bpy.data.objects.new(PREFIX + name + ":tile_finish", mesh)
    coll.objects.link(obj)
    semantic(obj, "floor_finish", detail=True)
    tile_count = nx * ny
    for target in (grout, obj):
        target["c2w_floor_system"] = "modeled_porcelain_with_recessed_epoxy_grout"
        target["c2w_floor_tile_count"] = tile_count
        target["c2w_floor_grout_width_m"] = gap
        target["c2w_floor_module_m"] = (round(cell_w, 4), round(cell_d, 4))
    return obj


# ---------------------------------------------------------------------------
# Inventory, shelving, checkout and pharmacy fixtures


def _tag_supported(obj, support_z, support_name):
    """Record the physical support contract used by the geometric audit."""
    obj["c2w_support_relation"] = "rests_on_shelf"
    obj["c2w_support_top_z"] = float(support_z)
    obj["c2w_base_z"] = float(support_z)
    obj["c2w_support_name"] = support_name
    return obj


def _tag_attached(obj, parent_obj, root_obj):
    """Record an explicit, geometrically checked package assembly relation."""
    obj["c2w_attachment_relation"] = "touches_package_component"
    obj["c2w_attached_to"] = parent_obj.name
    obj["c2w_assembly_root"] = root_obj.name
    return obj


def add_product(
    coll, name, x, y, z0, width, depth, height, side, M, rot=0.0, support_name="shelf"
):
    """Create a multi-part retail package resting exactly on ``z0``.

    The body carries an explicit support relation.  Raised printed faces are
    attached to the package rather than treated as free-standing inventory.
    """
    color = M["packages"][RNG.randrange(len(M["packages"]))]
    accent = M["accents"][RNG.randrange(len(M["accents"]))]
    kind_roll = RNG.random()
    if kind_roll < 0.30:
        # A shouldered medicine bottle with an integrated profiled body/neck,
        # an attached wrap label, tamper ring and genuinely ribbed safety cap.
        px, py = local_xy(x, y, 0, 0, rot)
        bottle_mat = M["bottles"][RNG.randrange(len(M["bottles"]))]
        body_h = height * 0.78
        body = instance_part(
            coll,
            name + ":bottle_profile",
            (px, py, z0 + body_h / 2),
            (width, width, body_h),
            bottle_mat,
            "bottle",
            rot,
            "product",
        )
        body["c2w_product_form"] = "bottle"
        _tag_supported(body, z0, support_name)
        label = instance_part(
            coll,
            name + ":wrap_label",
            (px, py, z0 + body_h * 0.43),
            (width * 1.018, width * 1.018, body_h * 0.34),
            M["label"],
            "cylinder",
            rot,
            "product_label",
        )
        _tag_attached(label, body, body)
        face_offset = side * (width * 0.515)
        fx, fy = local_xy(x, y, 0, face_offset, rot)
        band = instance_part(
            coll,
            name + ":label_brand_band",
            (fx, fy, z0 + body_h * 0.50),
            (width * 0.56, 0.010, body_h * 0.055),
            accent,
            "cube",
            rot,
            "product_detail",
        )
        _tag_attached(band, label, body)
        tamper = instance_part(
            coll,
            name + ":tamper_ring",
            (px, py, z0 + body_h * 0.955),
            (width * 0.63, width * 0.63, height * 0.055),
            M["cap"],
            "cap",
            rot,
            "product_detail",
        )
        _tag_attached(tamper, body, body)
        cap_h = height * 0.19
        cap = instance_part(
            coll,
            name + ":child_resistant_cap",
            (px, py, z0 + body_h + cap_h * 0.43),
            (width * 0.69, width * 0.69, cap_h),
            M["cap_blue"] if RNG.random() < 0.18 else M["cap"],
            "cap",
            rot,
            "product_detail",
        )
        _tag_attached(cap, body, body)
        top = instance_part(
            coll,
            name + ":cap_top_disc",
            (px, py, z0 + body_h + cap_h * 0.92),
            (width * 0.53, width * 0.53, cap_h * 0.045),
            M["paper"],
            "cylinder",
            rot,
            "product_detail",
        )
        _tag_attached(top, cap, body)
        return
    if kind_roll < 0.43:
        # A tapered squeeze tube with a flattened top crimp and supported cap.
        px, py = local_xy(x, y, 0, 0, rot)
        cap_h = min(0.075, height * 0.22)
        cap = instance_part(
            coll,
            name + ":tube_cap",
            (px, py, z0 + cap_h / 2),
            (width * 0.66, depth * 0.70, cap_h),
            M["cap"],
            "cap",
            rot,
            "product",
        )
        cap["c2w_product_form"] = "tube_assembly_base"
        _tag_supported(cap, z0, support_name)
        body_h = height - cap_h * 0.72
        body = instance_part(
            coll,
            name + ":tapered_tube",
            (px, py, z0 + cap_h * 0.72 + body_h / 2),
            (width, depth * 0.66, body_h),
            color,
            "tube",
            rot,
            "product_detail",
        )
        body["c2w_product_form"] = "tube"
        _tag_attached(body, cap, cap)
        face_offset = side * (depth * 0.335 + 0.004)
        fx, fy = local_xy(x, y, 0, face_offset, rot)
        print_face = instance_part(
            coll,
            name + ":tube_print",
            (fx, fy, z0 + cap_h + body_h * 0.52),
            (width * 0.66, 0.008, body_h * 0.46),
            M["label"],
            "cube",
            rot,
            "product_label",
        )
        _tag_attached(print_face, body, cap)
        bfx, bfy = local_xy(x, y, 0, face_offset + side * 0.006, rot)
        band = instance_part(
            coll,
            name + ":tube_brand_band",
            (bfx, bfy, z0 + cap_h + body_h * 0.62),
            (width * 0.51, 0.010, body_h * 0.065),
            accent,
            "cube",
            rot,
            "product_detail",
        )
        _tag_attached(band, print_face, cap)
        crimp = instance_part(
            coll,
            name + ":tube_crimp",
            (px, py, z0 + cap_h * 0.72 + body_h * 0.975),
            (width * 0.78, depth * 0.19, body_h * 0.045),
            M["cap"],
            "cube",
            rot,
            "product_detail",
        )
        _tag_attached(crimp, body, cap)
        return
    # Cartons vary in proportion and get a separate, raised printed face.  The
    # colored carton body remains visible as the graphic border around it.
    px, py = local_xy(x, y, 0, 0, rot)
    body = instance_part(
        coll,
        name + ":folded_carton",
        (px, py, z0 + height / 2),
        (width, depth, height),
        color,
        "cube",
        rot,
        "product",
    )
    body["c2w_product_form"] = "carton"
    _tag_supported(body, z0, support_name)
    face_offset = side * (depth / 2 + 0.004)
    fx, fy = local_xy(x, y, 0, face_offset, rot)
    print_face = instance_part(
        coll,
        name + ":printed_front",
        (fx, fy, z0 + height * 0.54),
        (width * 0.76, 0.009, height * 0.52),
        M["label"],
        "cube",
        rot,
        "product_label",
    )
    _tag_attached(print_face, body, body)
    # Two narrow colour/typography bands prevent the blank-label look at close range.
    bx, by = local_xy(x, y, 0, face_offset + side * 0.006, rot)
    brand = instance_part(
        coll,
        name + ":brand_band",
        (bx, by, z0 + height * 0.68),
        (width * 0.59, 0.010, height * 0.065),
        accent,
        "cube",
        rot,
        "product_detail",
    )
    _tag_attached(brand, print_face, body)
    if width > 0.16:
        dx, dy = local_xy(x, y, 0, face_offset + side * 0.007, rot)
        dose = instance_part(
            coll,
            name + ":dose_band",
            (dx, dy, z0 + height * 0.40),
            (width * 0.43, 0.010, height * 0.035),
            M["black"],
            "cube",
            rot,
            "product_detail",
        )
        _tag_attached(dose, print_face, body)
    seam = instance_part(
        coll,
        name + ":folded_top_seam",
        (px, py, z0 + height + 0.002),
        (width * 0.72, depth * 0.045, 0.004),
        M["paper"],
        "cube",
        rot,
        "product_detail",
    )
    _tag_attached(seam, body, body)


def product_row(
    coll,
    name,
    cx,
    cy,
    z0,
    length,
    depth,
    side,
    M,
    rot=0.0,
    density=0.27,
    support_name="shelf",
):
    count = max(6, int(length / density))
    spacing = length / count
    for i in range(count):
        width = spacing * RNG.uniform(0.58, 0.88)
        height = RNG.uniform(0.18, 0.34) * (1.08 if i % 7 == 0 else 1.0)
        package_depth = RNG.uniform(0.10, min(0.23, depth))
        lx = -length / 2 + spacing * (i + 0.5) + RNG.uniform(-0.018, 0.018)
        lateral = RNG.uniform(-0.012, 0.012)
        x, y = local_xy(cx, cy, lx, lateral, rot)
        item_rot = rot + RNG.uniform(-0.014, 0.014)
        add_product(
            coll,
            f"{name}:sku_{i:02d}",
            x,
            y,
            z0,
            width,
            package_depth,
            height,
            side,
            M,
            item_rot,
            support_name,
        )


def gondola(coll, name, cx, cy, length, M, rot=0.0, levels=4):
    """A double-sided commercial gondola with physically supported stock."""
    shelf_mat = M["shelf_white"]
    # Plinth, perforated central spine and structural posts are all modeled.
    box(
        coll,
        f"{name}:plinth",
        (cx, cy, 0.105),
        (length, 0.88, 0.21),
        M["counter_dark"],
        0.018,
        (0, 0, rot),
        "fixture",
    )
    box(
        coll,
        f"{name}:spine",
        (cx, cy, 1.06),
        (length - 0.14, 0.055, 1.86),
        shelf_mat,
        0.010,
        (0, 0, rot),
        "fixture",
    )
    for end in (-1, 1):
        x, y = local_xy(cx, cy, end * (length / 2 - 0.05), 0, rot)
        box(
            coll,
            f"{name}:end_frame_{end}",
            (x, y, 1.04),
            (0.095, 0.94, 2.05),
            shelf_mat,
            0.015,
            (0, 0, rot),
            "fixture",
        )
        for side in (-1, 1):
            px, py = local_xy(cx, cy, end * (length / 2 + 0.012), side * 0.455, rot)
            box(
                coll,
                f"{name}:endcap_graphic_{end}_{side}",
                (px, py, 1.18),
                (0.025, 0.035, 1.20),
                M["poster_teal" if end * side > 0 else "poster_blue"],
                0.004,
                (0, 0, rot),
                "fixture",
            )
            # Visible pitch slots make the shelf system mechanically credible.
            for iz in range(10):
                sx, sy = local_xy(cx, cy, end * (length / 2 + 0.052), side * 0.475, rot)
                instance_part(
                    coll,
                    f"{name}:end_slot_{end}_{side}_{iz}",
                    (sx, sy, 0.34 + iz * 0.17),
                    (0.030, 0.012, 0.075),
                    M["shadow_line"],
                    "cube",
                    rot,
                    "fixture",
                )
    # Perforated back panels, shared across both faces of the gondola.
    for side in (-1, 1):
        for ix in range(max(4, int(length / 1.05))):
            lx = -length / 2 + 0.55 + ix * 1.02
            if lx > length / 2 - 0.25:
                continue
            for iz in range(6):
                sx, sy = local_xy(cx, cy, lx, side * 0.036, rot)
                instance_part(
                    coll,
                    f"{name}:peg_slot_{side}_{ix}_{iz}",
                    (sx, sy, 0.48 + iz * 0.27),
                    (0.30, 0.012, 0.035),
                    M["shadow_line"],
                    "cube",
                    rot,
                    "fixture",
                )
    level_z = [0.235 + i * 0.43 for i in range(levels)]
    for li, z in enumerate(level_z):
        for side in (-1, 1):
            ly = side * 0.31
            x, y = local_xy(cx, cy, 0, ly, rot)
            deck = box(
                coll,
                f"{name}:deck_{li}_{side}",
                (x, y, z),
                (length, 0.44, 0.050),
                shelf_mat,
                0.006,
                (0, 0, rot),
                "shelf_deck",
            )
            support_z = z + 0.025
            deck["c2w_support_top_z"] = support_z
            rx, ry = local_xy(cx, cy, 0, side * 0.535, rot)
            box(
                coll,
                f"{name}:price_rail_{li}_{side}",
                (rx, ry, z + 0.065),
                (length, 0.026, 0.095),
                M["price_rail"],
                0.003,
                (0, 0, rot),
                "fixture",
            )
            pcx, pcy = local_xy(cx, cy, 0, side * 0.36, rot)
            product_row(
                coll,
                f"{name}:row_{li}_{side}",
                pcx,
                pcy,
                support_z,
                length - 0.28,
                0.215,
                side,
                M,
                rot,
                0.255,
                deck.name,
            )
            for end in (-1, 1):
                bx, by = local_xy(cx, cy, end * (length / 2 - 0.15), side * 0.30, rot)
                box(
                    coll,
                    f"{name}:shelf_bracket_{li}_{side}_{end}",
                    (bx, by, z - 0.095),
                    (0.16, 0.34, 0.16),
                    M["aluminum"],
                    0.006,
                    (0, 0, rot),
                    "fixture",
                )
            # Individual price cards break up the continuous rail.
            for ti in range(max(3, int(length / 1.15))):
                lx = -length / 2 + 0.48 + ti * 1.12
                tx, ty = local_xy(cx, cy, lx, side * 0.552, rot)
                instance_part(
                    coll,
                    f"{name}:ticket_{li}_{side}_{ti}",
                    (tx, ty, z + 0.065),
                    (0.58, 0.010, 0.055),
                    M["paper"],
                    "cube",
                    rot,
                    "fixture",
                )
    # Header/category blade with small supports.
    for end in (-1, 1):
        x, y = local_xy(cx, cy, end * (length / 2 - 0.16), 0, rot)
        box(
            coll,
            f"{name}:header_post_{end}",
            (x, y, 2.30),
            (0.055, 0.055, 0.62),
            M["aluminum"],
            0.006,
            (0, 0, rot),
            "fixture",
        )
    x, y = local_xy(cx, cy, 0, 0, rot)
    box(
        coll,
        f"{name}:category_header",
        (x, y, 2.48),
        (min(3.2, length * 0.58), 0.09, 0.45),
        M["clinical_blue"],
        0.025,
        (0, 0, rot),
        "fixture",
    )


def wall_shelf(coll, name, cx, y, width, M, modern=False, rows=5):
    sm = M["clinical"] if modern else M["shelf_white"]
    box(
        coll,
        name + ":back",
        (cx, y, 1.78),
        (width, 0.075, 3.48),
        sm,
        0.010,
        sem="fixture",
    )
    box(
        coll,
        name + ":plinth",
        (cx, y + 0.24, 0.13),
        (width + 0.08, 0.58, 0.26),
        M["counter_dark"],
        0.012,
        sem="fixture",
    )
    for seam_x in (cx - width * 0.25, cx, cx + width * 0.25):
        box(
            coll,
            name + ":back_panel_joint",
            (seam_x, y + 0.041, 1.80),
            (0.018, 0.012, 3.28),
            M["shadow_line"],
            0.002,
            sem="fixture",
        )
    for xx in (cx - width / 2, cx + width / 2):
        box(
            coll,
            name + ":upright",
            (xx, y + 0.25, 1.78),
            (0.075, 0.56, 3.52),
            sm,
            0.008,
            sem="fixture",
        )
        for iz in range(18):
            instance_part(
                coll,
                name + f":upright_slot_{iz}",
                (xx, y + 0.542, 0.27 + iz * 0.18),
                (0.028, 0.012, 0.080),
                M["shadow_line"],
                "cube",
                0,
                "fixture",
            )
    for row in range(rows):
        z = 0.31 + row * 0.62
        deck = box(
            coll,
            name + f":deck_{row}",
            (cx, y + 0.29, z),
            (width, 0.59, 0.050),
            sm,
            0.006,
            sem="shelf_deck",
        )
        support_z = z + 0.025
        deck["c2w_support_top_z"] = support_z
        box(
            coll,
            name + f":price_{row}",
            (cx, y + 0.585, z + 0.07),
            (width, 0.025, 0.10),
            M["price_rail"],
            0.004,
            sem="fixture",
        )
        product_row(
            coll,
            name + f":stock_{row}",
            cx,
            y + 0.43,
            support_z,
            width - 0.18,
            0.215,
            1,
            M,
            0,
            density=0.245,
            support_name=deck.name,
        )
        for end in (-1, 1):
            box(
                coll,
                name + f":bracket_{row}_{end}",
                (cx + end * (width / 2 - 0.13), y + 0.27, z - 0.095),
                (0.18, 0.43, 0.16),
                M["aluminum"],
                0.006,
                sem="fixture",
            )
        # Transparent vertical dividers keep stock upright and visibly touch
        # the deck; they are spaced between SKU groups, not through packages.
        divider_count = max(3, int(width / 1.20))
        for di in range(1, divider_count):
            dx = cx - width / 2 + width * di / divider_count
            box(
                coll,
                name + f":divider_{row}_{di}",
                (dx, y + 0.43, support_z + 0.105),
                (0.018, 0.38, 0.21),
                M["price_rail"],
                0.002,
                sem="fixture",
            )
        for ti in range(max(2, int(width / 0.95))):
            tx = cx - width / 2 + 0.42 + ti * 0.92
            instance_part(
                coll,
                name + f":price_card_{row}_{ti}",
                (tx, y + 0.602, z + 0.07),
                (0.42, 0.009, 0.052),
                M["paper"],
                "cube",
                0,
                "fixture",
            )
    if modern:
        box(
            coll,
            name + ":top_light",
            (cx, y + 0.25, 3.62),
            (width + 0.10, 0.30, 0.12),
            M["white_emit"],
            0.015,
            sem="lighting_fixture",
        )


def pos_terminal(coll, name, loc, M, facing=0.0):
    x, y, z = loc
    box(
        coll,
        name + ":base",
        (x, y, z),
        (0.42, 0.28, 0.06),
        M["black"],
        0.025,
        (0, 0, facing),
        "fixture",
    )
    cyl(
        coll,
        name + ":stem",
        (x, y, z + 0.25),
        0.035,
        0.48,
        M["steel"],
        20,
        sem="fixture",
        bevel=0.004,
    )
    # Tilted screen and inset blue UI panel.
    box(
        coll,
        name + ":screen",
        (x, y, z + 0.53),
        (0.62, 0.13, 0.48),
        M["black"],
        0.035,
        (math.radians(-10), 0, facing),
        "fixture",
    )
    sx, sy = local_xy(x, y, 0, 0.071, facing)
    box(
        coll,
        name + ":ui",
        (sx, sy, z + 0.54),
        (0.51, 0.012, 0.36),
        M["screen"],
        0.006,
        (math.radians(-10), 0, facing),
        "fixture",
    )
    hx, hy = local_xy(x, y, 0, 0.078, facing)
    box(
        coll,
        name + ":ui_header",
        (hx, hy, z + 0.66),
        (0.42, 0.008, 0.055),
        M["cyan"],
        0.002,
        (math.radians(-10), 0, facing),
        "fixture",
    )
    for line in range(3):
        lx, ly = local_xy(x, y, -0.07, 0.079, facing)
        box(
            coll,
            name + f":ui_line_{line}",
            (lx, ly, z + 0.57 - line * 0.065),
            (0.24, 0.007, 0.018),
            M["poster_white"],
            0.001,
            (math.radians(-10), 0, facing),
            "fixture",
        )
    cyl(
        coll,
        name + ":hinge",
        (x, y, z + 0.27),
        0.075,
        0.16,
        M["steel"],
        20,
        (math.pi / 2, 0, 0),
        "fixture",
        0.004,
    )
    # Manufactured monitor details: rear ventilation, power/status control,
    # VESA fixings and a real cable rather than a floating screen assembly.
    for vi in range(5):
        box(
            coll,
            name + f":rear_vent_{vi}",
            (x - 0.18 + vi * 0.09, y - 0.071, z + 0.55),
            (0.052, 0.010, 0.15),
            M["shadow_line"],
            0.002,
            (math.radians(-10), 0, facing),
            "fixture",
        )
    cyl(
        coll,
        name + ":power_led",
        (x + 0.245, y + 0.079, z + 0.38),
        0.018,
        0.012,
        M["green_emit"],
        16,
        (math.pi / 2, 0, facing),
        "fixture",
        0.002,
    )
    for sx in (-0.10, 0.10):
        for sz in (-0.10, 0.10):
            cyl(
                coll,
                name + ":vesa_screw",
                (x + sx, y - 0.080, z + 0.55 + sz),
                0.010,
                0.012,
                M["steel"],
                12,
                (math.pi / 2, 0, facing),
                "fixture",
                0.001,
            )
    curve_tube(
        coll,
        name + ":power_data_loom",
        [
            (x + 0.12, y - 0.08, z + 0.29),
            (x + 0.13, y - 0.09, z + 0.12),
            (x + 0.17, y - 0.05, z - 0.01),
        ],
        0.014,
        M["cable"],
        False,
        "fixture",
    )


def pharmacy_workstation_details(coll, name, mx, y, height, M, station_index):
    """Add the professional tools and construction layers of a dispensary bay."""
    top = height + 0.13
    # Two-piece frameless guard with a central handover opening, stainless
    # uprights, clamped feet and a polished lower rail.
    for side in (-1, 1):
        gx = mx + side * 0.73
        box(
            coll,
            f"{name}:guard_glass_{station_index}_{side}",
            (gx, y - 0.055, top + 0.49),
            (0.82, 0.020, 0.78),
            M["glass"],
            0.006,
            sem="fixture",
        )
        cyl(
            coll,
            f"{name}:guard_post_{station_index}_{side}",
            (mx + side * 1.18, y - 0.055, top + 0.42),
            0.022,
            0.94,
            M["steel"],
            18,
            sem="fixture",
            bevel=0.003,
        )
        box(
            coll,
            f"{name}:guard_clamp_{station_index}_{side}",
            (mx + side * 1.18, y - 0.055, top + 0.045),
            (0.15, 0.11, 0.10),
            M["steel"],
            0.010,
            sem="fixture",
        )
    box(
        coll,
        f"{name}:guard_top_bridge_{station_index}",
        (mx, y - 0.055, top + 0.91),
        (2.40, 0.055, 0.060),
        M["steel"],
        0.008,
        sem="fixture",
    )
    # Calibrated dispensing scale with a raised stainless pan and its own readout.
    sx = mx - 1.58
    box(
        coll,
        f"{name}:dispensing_scale_base_{station_index}",
        (sx, y - 0.27, top + 0.065),
        (0.58, 0.42, 0.10),
        M["kiosk_inset"],
        0.022,
        sem="fixture",
    )
    box(
        coll,
        f"{name}:dispensing_scale_pan_{station_index}",
        (sx, y - 0.27, top + 0.132),
        (0.49, 0.34, 0.035),
        M["steel"],
        0.010,
        sem="fixture",
    )
    box(
        coll,
        f"{name}:dispensing_scale_display_{station_index}",
        (sx, y - 0.045, top + 0.095),
        (0.30, 0.030, 0.105),
        M["screen_dim"],
        0.006,
        sem="fixture",
    )
    for di in range(4):
        box(
            coll,
            f"{name}:scale_digit_{station_index}_{di}",
            (sx - 0.092 + di * 0.061, y - 0.063, top + 0.095),
            (0.034, 0.010, 0.016),
            M["cyan"],
            0.001,
            sem="fixture",
        )
    # Pill-counting tray, chute, retaining lip and stainless spatula.
    tx = mx + 1.72
    box(
        coll,
        f"{name}:counting_tray_{station_index}",
        (tx, y - 0.24, top + 0.038),
        (0.74, 0.44, 0.045),
        M["clinical_blue"],
        0.028,
        (0, 0, math.radians(-5)),
        "fixture",
    )
    box(
        coll,
        f"{name}:counting_tray_well_{station_index}",
        (tx - 0.08, y - 0.24, top + 0.064),
        (0.47, 0.30, 0.020),
        M["kiosk_inset"],
        0.018,
        (0, 0, math.radians(-5)),
        "fixture",
    )
    box(
        coll,
        f"{name}:counting_chute_{station_index}",
        (tx + 0.32, y - 0.23, top + 0.076),
        (0.20, 0.17, 0.035),
        M["steel"],
        0.012,
        (0, 0, math.radians(-5)),
        "fixture",
    )
    box(
        coll,
        f"{name}:counting_spatula_{station_index}",
        (tx - 0.08, y - 0.08, top + 0.102),
        (0.46, 0.035, 0.020),
        M["steel"],
        0.008,
        (0, 0, math.radians(8)),
        "fixture",
    )
    # Label stock genuinely feeds into the printer; the output label projects
    # onto the worktop and a cable/grommet connects the equipment below.
    cyl(
        coll,
        f"{name}:label_roll_{station_index}",
        (mx + 1.02, y - 0.24, top + 0.35),
        0.115,
        0.31,
        M["paper"],
        28,
        (0, math.pi / 2, 0),
        "fixture",
        0.006,
    )
    cyl(
        coll,
        f"{name}:label_roll_core_{station_index}",
        (mx + 1.02, y - 0.24, top + 0.35),
        0.038,
        0.325,
        M["counter_dark"],
        20,
        (0, math.pi / 2, 0),
        "fixture",
        0.003,
    )
    box(
        coll,
        f"{name}:printed_label_output_{station_index}",
        (mx + 1.02, y + 0.005, top + 0.19),
        (0.31, 0.19, 0.008),
        M["poster_white"],
        0.001,
        (math.radians(4), 0, 0),
        "fixture",
    )
    for li in range(4):
        box(
            coll,
            f"{name}:label_print_{station_index}_{li}",
            (mx + 0.92, y + 0.105 + li * 0.025, top + 0.197),
            (0.14, 0.010, 0.002),
            M["shadow_line"],
            0.001,
            sem="fixture",
        )
    curve_tube(
        coll,
        f"{name}:printer_cable_{station_index}",
        [
            (mx + 1.25, y - 0.30, top + 0.18),
            (mx + 1.36, y - 0.34, top + 0.02),
            (mx + 1.38, y - 0.28, height - 0.05),
        ],
        0.012,
        M["cable"],
        False,
        "fixture",
    )
    # Telephone handset and cradle, still standard equipment at a staffed counter.
    px = mx - 2.12
    box(
        coll,
        f"{name}:phone_base_{station_index}",
        (px, y - 0.16, top + 0.055),
        (0.46, 0.30, 0.09),
        M["kiosk_inset"],
        0.025,
        sem="fixture",
    )
    curve_tube(
        coll,
        f"{name}:phone_handset_{station_index}",
        [
            (px - 0.17, y - 0.11, top + 0.15),
            (px - 0.07, y - 0.08, top + 0.19),
            (px + 0.08, y - 0.08, top + 0.19),
            (px + 0.18, y - 0.11, top + 0.15),
        ],
        0.045,
        M["black"],
        False,
        "fixture",
    )
    curve_tube(
        coll,
        f"{name}:phone_coil_{station_index}",
        [
            (px + 0.20, y - 0.12, top + 0.14),
            (px + 0.27, y - 0.05, top + 0.10),
            (px + 0.20, y + 0.02, top + 0.06),
            (px + 0.29, y + 0.09, top + 0.02),
        ],
        0.010,
        M["cable"],
        False,
        "fixture",
    )


def checkout_lane(coll, name, x, y, M, modern=False):
    body_mat = M["clinical"] if modern else M["counter"]
    box(
        coll,
        name + ":body",
        (x, y, 0.63),
        (2.35, 0.86, 1.18),
        body_mat,
        0.075,
        sem="fixture",
    )
    box(
        coll,
        name + ":toe_kick",
        (x, y + 0.43, 0.18),
        (2.18, 0.05, 0.24),
        M["counter_dark"],
        0.010,
        sem="fixture",
    )
    box(
        coll,
        name + ":top",
        (x, y, 1.27),
        (2.48, 0.96, 0.12),
        M["counter"],
        0.035,
        sem="fixture",
    )
    box(
        coll,
        name + ":belt",
        (x - 0.35, y + 0.02, 1.35),
        (1.45, 0.63, 0.055),
        M["rubber"],
        0.010,
        sem="fixture",
    )
    for panel_x in (x - 0.72, x, x + 0.72):
        box(
            coll,
            name + ":front_panel",
            (panel_x, y + 0.438, 0.69),
            (0.62, 0.025, 0.78),
            body_mat,
            0.012,
            sem="fixture",
        )
        box(
            coll,
            name + ":front_reveal",
            (panel_x, y + 0.454, 0.69),
            (0.52, 0.010, 0.67),
            M["shadow_line"],
            0.004,
            sem="fixture",
        )
    box(
        coll,
        name + ":bag_well",
        (x - 0.82, y - 0.15, 1.39),
        (0.42, 0.48, 0.06),
        M["black"],
        0.018,
        sem="fixture",
    )
    pos_terminal(coll, name + ":pos", (x + 0.66, y - 0.16, 1.37), M)
    cyl(
        coll,
        name + ":scanner",
        (x + 0.20, y + 0.18, 1.42),
        0.16,
        0.035,
        M["red_emit"],
        24,
        (math.pi / 2, 0, 0),
        "fixture",
        0.003,
    )
    box(
        coll,
        name + ":keyboard",
        (x + 0.34, y + 0.10, 1.40),
        (0.50, 0.24, 0.035),
        M["black"],
        0.015,
        (math.radians(4), 0, 0),
        "fixture",
    )
    for ix in range(6):
        for iy in range(2):
            box(
                coll,
                name + f":key_{ix}_{iy}",
                (x + 0.14 + ix * 0.068, y + 0.18 + iy * 0.065, 1.425),
                (0.047, 0.042, 0.014),
                M["paper"],
                0.003,
                sem="fixture",
            )
    box(
        coll,
        name + ":receipt_printer",
        (x + 0.88, y + 0.17, 1.49),
        (0.36, 0.34, 0.25),
        M["clinical"],
        0.025,
        sem="fixture",
    )
    box(
        coll,
        name + ":receipt_slot",
        (x + 0.88, y + 0.347, 1.50),
        (0.22, 0.014, 0.035),
        M["black"],
        0.003,
        sem="fixture",
    )


def pharmacy_counter(coll, name, cx, y, width, M, modern=False):
    body = M["clinical"] if modern else M["counter"]
    # Three articulated counter modules with shadow gaps and a lowered access bay.
    module = width / 3
    for i in range(3):
        mx = cx - width / 2 + module * (i + 0.5)
        height = 0.98 if i == 2 else 1.15
        box(
            coll,
            f"{name}:module_{i}",
            (mx, y, height / 2),
            (module - 0.06, 1.0, height),
            body,
            0.045,
            sem="fixture",
        )
        box(
            coll,
            f"{name}:shadow_{i}",
            (mx, y + 0.506, 0.18),
            (module - 0.22, 0.025, 0.24),
            M["counter_dark"],
            0.004,
            sem="fixture",
        )
        box(
            coll,
            f"{name}:worktop_{i}",
            (mx, y - 0.02, height + 0.07),
            (module + 0.01, 1.12, 0.12),
            M["counter"],
            0.025,
            sem="fixture",
        )
        bay = module / 3
        for j in range(3):
            px = mx - module / 2 + bay * (j + 0.5)
            box(
                coll,
                f"{name}:cabinet_front_{i}_{j}",
                (px, y + 0.516, (height + 0.18) / 2),
                (bay - 0.10, 0.030, height - 0.30),
                body,
                0.010,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:cabinet_reveal_{i}_{j}",
                (px, y + 0.535, (height + 0.18) / 2),
                (bay - 0.19, 0.010, height - 0.40),
                M["shadow_line"],
                0.003,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:cabinet_pull_{i}_{j}",
                (px, y + 0.552, height - 0.18),
                (min(0.48, bay * 0.45), 0.035, 0.035),
                M["steel"],
                0.006,
                sem="fixture",
            )
        if i < 2:
            pos_terminal(
                coll, f"{name}:terminal_{i}", (mx + 0.35, y - 0.38, height + 0.12), M
            )
            box(
                coll,
                f"{name}:keyboard_{i}",
                (mx - 0.32, y - 0.34, height + 0.15),
                (0.56, 0.27, 0.035),
                M["black"],
                0.012,
                (math.radians(5), 0, 0),
                "fixture",
            )
            for row in range(3):
                for col in range(7):
                    box(
                        coll,
                        f"{name}:keyboard_key_{i}_{row}_{col}",
                        (
                            mx - 0.545 + col * 0.075,
                            y - 0.415 + row * 0.070,
                            height + 0.177,
                        ),
                        (0.052, 0.046, 0.014),
                        M["paper"],
                        0.003,
                        sem="fixture",
                    )
            cyl(
                coll,
                f"{name}:mouse_{i}",
                (mx + 0.08, y - 0.30, height + 0.18),
                0.070,
                0.035,
                M["black"],
                20,
                sem="fixture",
                bevel=0.006,
            )
            box(
                coll,
                f"{name}:rx_scanner_{i}",
                (mx - 0.78, y - 0.30, height + 0.19),
                (0.28, 0.24, 0.16),
                M["black"],
                0.018,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:rx_scanner_lens_{i}",
                (mx - 0.78, y - 0.165, height + 0.20),
                (0.18, 0.012, 0.065),
                M["red_emit"],
                0.003,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:label_printer_{i}",
                (mx + 1.02, y - 0.24, height + 0.24),
                (0.58, 0.42, 0.34),
                M["clinical"],
                0.028,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:printer_slot_{i}",
                (mx + 1.02, y - 0.018, height + 0.23),
                (0.36, 0.012, 0.045),
                M["black"],
                0.003,
                sem="fixture",
            )
            cyl(
                coll,
                f"{name}:cable_grommet_{i}",
                (mx + 0.72, y - 0.10, height + 0.145),
                0.052,
                0.020,
                M["black"],
                20,
                sem="fixture",
                bevel=0.003,
            )
            if modern:
                pharmacy_workstation_details(coll, name, mx, y, height, M, i)
    for di, divx in enumerate((cx - width / 6, cx + width / 6)):
        box(
            coll,
            f"{name}:privacy_fin_glass_{di}",
            (divx, y - 0.36, 1.74),
            (0.032, 0.56, 0.92),
            M["glass"],
            0.010,
            sem="fixture",
        )
        box(
            coll,
            f"{name}:privacy_fin_etched_band_{di}",
            (divx, y - 0.36, 1.70),
            (0.038, 0.565, 0.16),
            M["frost"],
            0.006,
            sem="fixture",
        )
        for py in (y - 0.59, y - 0.13):
            cyl(
                coll,
                f"{name}:privacy_fin_edge_{di}",
                (divx, py, 1.74),
                0.014,
                0.94,
                M["steel"],
                16,
                sem="fixture",
                bevel=0.002,
            )
            box(
                coll,
                f"{name}:privacy_fin_clamp_{di}",
                (divx, py, 1.30),
                (0.12, 0.10, 0.10),
                M["steel"],
                0.008,
                sem="fixture",
            )
    if modern:
        # Continuous fabrication layers make the long counter read as joined
        # commercial millwork rather than three unrelated boxes.
        box(
            coll,
            name + ":front_shadow_plinth",
            (cx, y + 0.535, 0.095),
            (width - 0.24, 0.065, 0.19),
            M["kiosk_inset"],
            0.008,
            sem="fixture",
        )
        box(
            coll,
            name + ":worktop_front_nosing",
            (cx - width / 6, y + 0.555, 1.235),
            (2 * module - 0.04, 0.075, 0.095),
            M["counter"],
            0.018,
            sem="fixture",
        )
        box(
            coll,
            name + ":accessible_nosing",
            (cx + width / 3, y + 0.555, 1.065),
            (module - 0.04, 0.075, 0.080),
            M["counter"],
            0.016,
            sem="fixture",
        )
        for side in (-1, 1):
            ex = cx + side * (width / 2 - 0.035)
            box(
                coll,
                name + f":end_cheek_{side}",
                (ex, y, 0.58),
                (0.07, 1.06, 1.16),
                M["clinical"],
                0.020,
                sem="fixture",
            )
            box(
                coll,
                name + f":end_shadow_reveal_{side}",
                (ex - side * 0.041, y + 0.39, 0.55),
                (0.018, 0.18, 0.88),
                M["shadow_line"],
                0.004,
                sem="fixture",
            )
        # Keyed drawer locks and printed prescription-bin cards provide a real
        # operational hierarchy across the staff-facing frontage.
        for i in range(3):
            mx = cx - width / 2 + module * (i + 0.5)
            height = 0.98 if i == 2 else 1.15
            bay = module / 3
            for j in range(3):
                px = mx - module / 2 + bay * (j + 0.5)
                cyl(
                    coll,
                    f"{name}:drawer_lock_{i}_{j}",
                    (px + bay * 0.31, y + 0.558, height - 0.18),
                    0.025,
                    0.020,
                    M["steel"],
                    14,
                    (math.pi / 2, 0, 0),
                    "fixture",
                    0.002,
                )
                box(
                    coll,
                    f"{name}:drawer_id_card_{i}_{j}",
                    (px - bay * 0.20, y + 0.558, height - 0.18),
                    (0.28, 0.012, 0.065),
                    M["poster_white"],
                    0.003,
                    sem="fixture",
                )
                for line in range(2):
                    box(
                        coll,
                        f"{name}:drawer_id_print_{i}_{j}_{line}",
                        (px - bay * 0.20, y + 0.567, height - 0.165 - line * 0.022),
                        (0.18, 0.006, 0.008),
                        M["shadow_line"],
                        0.001,
                        sem="fixture",
                    )
        # Lidded handover baskets sit on the lower accessible module and are
        # built from a base, rim, handles, label pockets and ventilation slots.
        lower_x = cx + width / 3
        for bi in (-1, 0, 1):
            bx = lower_x + bi * 1.25
            box(
                coll,
                f"{name}:rx_handover_bin_{bi}:base",
                (bx, y - 0.10, 1.10),
                (1.02, 0.66, 0.15),
                M["clinical_blue"],
                0.030,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:rx_handover_bin_{bi}:rim",
                (bx, y - 0.10, 1.205),
                (1.08, 0.70, 0.055),
                M["steel"],
                0.015,
                sem="fixture",
            )
            box(
                coll,
                f"{name}:rx_handover_bin_{bi}:label_pocket",
                (bx, y + 0.265, 1.145),
                (0.48, 0.020, 0.10),
                M["price_rail"],
                0.004,
                sem="fixture",
            )
            for slot in range(5):
                box(
                    coll,
                    f"{name}:rx_handover_bin_{bi}:vent_{slot}",
                    (bx - 0.34 + slot * 0.17, y + 0.272, 1.09),
                    (0.085, 0.010, 0.018),
                    M["shadow_line"],
                    0.002,
                    sem="fixture",
                )
            for side in (-1, 1):
                cyl(
                    coll,
                    f"{name}:rx_handover_bin_{bi}:handle_{side}",
                    (bx + side * 0.43, y - 0.10, 1.17),
                    0.020,
                    0.38,
                    M["steel"],
                    14,
                    (math.pi / 2, 0, 0),
                    "fixture",
                    0.002,
                )
        # Under-counter power/data raceway with individually modeled outlets.
        box(
            coll,
            name + ":power_data_raceway",
            (cx - width / 6, y - 0.525, 1.02),
            (2 * module - 0.42, 0.075, 0.16),
            M["kiosk_inset"],
            0.010,
            sem="fixture",
        )
        for oi in range(8):
            ox = cx - width / 2 + 0.85 + oi * (2 * module - 1.70) / 7
            box(
                coll,
                f"{name}:power_outlet_{oi}",
                (ox, y - 0.568, 1.02),
                (0.22, 0.020, 0.10),
                M["paper"],
                0.005,
                sem="fixture",
            )
            for si in (-0.045, 0.045):
                box(
                    coll,
                    f"{name}:power_slot_{oi}_{si}",
                    (ox + si, y - 0.581, 1.025),
                    (0.018, 0.008, 0.045),
                    M["black"],
                    0.001,
                    sem="fixture",
                )
        text_obj(
            coll,
            name + ":front_brand",
            "Pharmacy",
            (cx, y + 0.525, 0.66),
            0.34,
            M["cyan"],
            0.018,
            bold=False,
        )


def prescription_pickup_kiosk(coll, name, x, y, M):
    """Manufactured, serviceable 24/7 prescription collection terminal.

    The assembly is modeled as fabricated sheet metal with separate seams,
    gaskets, fixings, payment hardware, scanner, printer, pickup drawer,
    ventilation and floor anchorage.  No control is represented by a single
    oversized primary-colour block.
    """
    # Structural carcass, recessed toe space, levelling feet and anchor plate.
    box(
        coll,
        name + ":anchor_plate",
        (x, y, 0.035),
        (1.34, 0.84, 0.07),
        M["kiosk_inset"],
        0.022,
        sem="fixture",
    )
    box(
        coll,
        name + ":recessed_toe_plinth",
        (x, y - 0.035, 0.115),
        (1.14, 0.68, 0.16),
        M["kiosk_inset"],
        0.018,
        sem="fixture",
    )
    for sx in (-0.52, 0.52):
        for sy in (-0.29, 0.29):
            cyl(
                coll,
                name + f":levelling_foot_{sx}_{sy}",
                (x + sx, y + sy, 0.075),
                0.050,
                0.085,
                M["steel"],
                20,
                sem="fixture",
                bevel=0.004,
            )
            cyl(
                coll,
                name + f":floor_anchor_{sx}_{sy}",
                (x + sx, y + sy, 0.087),
                0.019,
                0.100,
                M["black"],
                12,
                sem="fixture",
                bevel=0.002,
            )
    box(
        coll,
        name + ":lower_sheet_metal_carcass",
        (x, y, 0.63),
        (1.20, 0.70, 1.02),
        M["kiosk_shell"],
        0.030,
        sem="fixture",
    )
    box(
        coll,
        name + ":upper_sheet_metal_console",
        (x, y - 0.005, 1.55),
        (1.22, 0.72, 0.84),
        M["kiosk_shell"],
        0.032,
        sem="fixture",
    )
    box(
        coll,
        name + ":top_cap",
        (x, y - 0.005, 2.035),
        (1.28, 0.74, 0.15),
        M["kiosk_shell"],
        0.026,
        sem="fixture",
    )
    # Rolled side returns and real panel seams keep the cabinet visually thin.
    for side in (-1, 1):
        box(
            coll,
            name + f":rolled_side_return_{side}",
            (x + side * 0.594, y + 0.27, 1.10),
            (0.035, 0.14, 1.68),
            M["steel"],
            0.010,
            sem="fixture",
        )
        box(
            coll,
            name + f":front_vertical_gasket_{side}",
            (x + side * 0.552, y + 0.357, 1.10),
            (0.018, 0.016, 1.70),
            M["cable"],
            0.003,
            sem="fixture",
        )
    box(
        coll,
        name + ":carcass_horizontal_gasket",
        (x, y + 0.358, 1.105),
        (1.10, 0.018, 0.020),
        M["cable"],
        0.003,
        sem="fixture",
    )
    # Backlit header is a restrained service identifier, not a toy-like cap.
    box(
        coll,
        name + ":header_recess",
        (x, y + 0.371, 2.035),
        (1.12, 0.035, 0.20),
        M["kiosk_inset"],
        0.014,
        sem="fixture",
    )
    box(
        coll,
        name + ":header_face",
        (x, y + 0.394, 2.035),
        (1.04, 0.016, 0.155),
        M["clinical_blue"],
        0.012,
        sem="fixture",
    )
    text_obj(
        coll,
        name + ":header_text",
        "24/7  RX  PICKUP",
        (x, y + 0.411, 2.072),
        0.064,
        M["poster_white"],
        0.007,
    )
    # Security camera, privacy hood and a deeply recessed laminated touchscreen.
    box(
        coll,
        name + ":screen_privacy_hood",
        (x, y + 0.357, 1.70),
        (1.04, 0.095, 0.69),
        M["kiosk_inset"],
        0.028,
        sem="fixture",
    )
    box(
        coll,
        name + ":screen_bezel",
        (x, y + 0.412, 1.70),
        (0.88, 0.055, 0.56),
        M["black"],
        0.022,
        sem="fixture",
    )
    box(
        coll,
        name + ":screen_glass",
        (x, y + 0.444, 1.70),
        (0.78, 0.014, 0.46),
        M["screen_glass"],
        0.005,
        sem="fixture",
    )
    box(
        coll,
        name + ":screen_lcd",
        (x, y + 0.453, 1.70),
        (0.735, 0.006, 0.415),
        M["screen"],
        0.002,
        sem="fixture",
    )
    box(
        coll,
        name + ":screen_status_header",
        (x, y + 0.459, 1.845),
        (0.66, 0.004, 0.060),
        M["screen_dim"],
        0.001,
        sem="fixture",
    )
    text_obj(
        coll,
        name + ":screen_title",
        "COLLECT PRESCRIPTION",
        (x, y + 0.464, 1.848),
        0.042,
        M["poster_white"],
        0.004,
        bold=False,
    )
    # Patient icon, progress rail and three interface cards are separate layers.
    cyl(
        coll,
        name + ":screen_patient_head",
        (x - 0.245, y + 0.462, 1.735),
        0.042,
        0.008,
        M["poster_white"],
        20,
        (math.pi / 2, 0, 0),
        "fixture",
        0.001,
    )
    box(
        coll,
        name + ":screen_patient_body",
        (x - 0.245, y + 0.464, 1.655),
        (0.125, 0.005, 0.080),
        M["poster_white"],
        0.025,
        sem="fixture",
    )
    for line, width in enumerate((0.34, 0.28, 0.23)):
        box(
            coll,
            name + f":screen_instruction_{line}",
            (x + 0.105, y + 0.462, 1.765 - line * 0.062),
            (width, 0.005, 0.018),
            M["poster_white"],
            0.001,
            sem="fixture",
        )
    box(
        coll,
        name + ":screen_progress_track",
        (x, y + 0.462, 1.545),
        (0.58, 0.005, 0.020),
        M["kiosk_inset"],
        0.003,
        sem="fixture",
    )
    box(
        coll,
        name + ":screen_progress_fill",
        (x - 0.12, y + 0.466, 1.545),
        (0.34, 0.004, 0.014),
        M["green_emit"],
        0.002,
        sem="fixture",
    )
    for bi in (-1, 0, 1):
        box(
            coll,
            name + f":screen_action_card_{bi}",
            (x + bi * 0.215, y + 0.465, 1.495),
            (0.18, 0.004, 0.055),
            M["screen_dim"],
            0.008,
            sem="fixture",
        )
    box(
        coll,
        name + ":camera_pod",
        (x, y + 0.413, 1.972),
        (0.24, 0.075, 0.085),
        M["black"],
        0.020,
        sem="fixture",
    )
    cyl(
        coll,
        name + ":camera_lens",
        (x, y + 0.458, 1.972),
        0.027,
        0.018,
        M["screen_glass"],
        24,
        (math.pi / 2, 0, 0),
        "fixture",
        0.003,
    )
    cyl(
        coll,
        name + ":camera_status_led",
        (x + 0.075, y + 0.459, 1.972),
        0.010,
        0.010,
        M["green_emit"],
        12,
        (math.pi / 2, 0, 0),
        "fixture",
        0.001,
    )
    # Receipt printer and protruding printed slip.
    box(
        coll,
        name + ":receipt_printer_recess",
        (x - 0.36, y + 0.374, 1.315),
        (0.38, 0.045, 0.18),
        M["kiosk_inset"],
        0.014,
        sem="fixture",
    )
    box(
        coll,
        name + ":receipt_slot",
        (x - 0.36, y + 0.403, 1.34),
        (0.25, 0.018, 0.032),
        M["black"],
        0.004,
        sem="fixture",
    )
    box(
        coll,
        name + ":receipt_paper",
        (x - 0.36, y + 0.440, 1.275),
        (0.22, 0.075, 0.14),
        M["poster_white"],
        0.003,
        (math.radians(-8), 0, 0),
        "fixture",
    )
    for line in range(5):
        box(
            coll,
            name + f":receipt_print_{line}",
            (x - 0.36, y + 0.482, 1.315 - line * 0.023),
            (0.14 - line * 0.008, 0.006, 0.006),
            M["shadow_line"],
            0.001,
            sem="fixture",
        )
    text_obj(
        coll,
        name + ":receipt_label",
        "RECEIPT",
        (x - 0.36, y + 0.407, 1.405),
        0.036,
        M["paper"],
        0.003,
        bold=False,
    )
    # Separate QR/barcode aperture with glass, illumination and status legend.
    box(
        coll,
        name + ":barcode_recess",
        (x - 0.36, y + 0.375, 1.085),
        (0.36, 0.045, 0.18),
        M["kiosk_inset"],
        0.014,
        sem="fixture",
    )
    box(
        coll,
        name + ":barcode_glass",
        (x - 0.36, y + 0.404, 1.085),
        (0.27, 0.016, 0.105),
        M["screen_glass"],
        0.006,
        sem="fixture",
    )
    box(
        coll,
        name + ":barcode_scan_line",
        (x - 0.36, y + 0.415, 1.085),
        (0.20, 0.005, 0.010),
        M["red_emit"],
        0.002,
        sem="fixture",
    )
    text_obj(
        coll,
        name + ":barcode_label",
        "SCAN ID",
        (x - 0.36, y + 0.407, 1.185),
        0.036,
        M["paper"],
        0.003,
        bold=False,
    )
    # Commercial payment terminal: its own screen, tactile keypad, card slot,
    # contactless target, cancel/clear/enter keys and strain-relieved cable.
    px = x + 0.34
    box(
        coll,
        name + ":payment_terminal_mount",
        (px, y + 0.375, 1.205),
        (0.36, 0.12, 0.54),
        M["kiosk_inset"],
        0.022,
        (math.radians(-4), 0, 0),
        "fixture",
    )
    box(
        coll,
        name + ":payment_screen_bezel",
        (px, y + 0.445, 1.365),
        (0.28, 0.025, 0.17),
        M["black"],
        0.010,
        (math.radians(-4), 0, 0),
        "fixture",
    )
    box(
        coll,
        name + ":payment_screen",
        (px, y + 0.462, 1.365),
        (0.235, 0.008, 0.125),
        M["screen_dim"],
        0.004,
        (math.radians(-4), 0, 0),
        "fixture",
    )
    for row in range(4):
        for col in range(3):
            key_mat = M["paper"]
            if row == 3:
                key_mat = (
                    M["red"]
                    if col == 0
                    else M["amber_emit"]
                    if col == 1
                    else M["green_emit"]
                )
            box(
                coll,
                name + f":payment_key_{row}_{col}",
                (px - 0.082 + col * 0.082, y + 0.460, 1.245 - row * 0.061),
                (0.054, 0.020, 0.038),
                key_mat,
                0.005,
                (math.radians(-4), 0, 0),
                "fixture",
            )
    box(
        coll,
        name + ":payment_card_slot",
        (px, y + 0.466, 1.055),
        (0.20, 0.016, 0.030),
        M["black"],
        0.003,
        sem="fixture",
    )
    cyl(
        coll,
        name + ":payment_nfc_outer",
        (px + 0.09, y + 0.468, 1.485),
        0.048,
        0.009,
        M["cyan"],
        24,
        (math.pi / 2, 0, 0),
        "fixture",
        0.002,
    )
    cyl(
        coll,
        name + ":payment_nfc_inner",
        (px + 0.09, y + 0.474, 1.485),
        0.030,
        0.010,
        M["kiosk_inset"],
        24,
        (math.pi / 2, 0, 0),
        "fixture",
        0.002,
    )
    curve_tube(
        coll,
        name + ":payment_cable",
        [
            (px + 0.16, y + 0.34, 1.04),
            (px + 0.20, y + 0.20, 0.98),
            (px + 0.18, y + 0.05, 0.92),
        ],
        0.013,
        M["cable"],
        False,
        "fixture",
    )
    # Gasketed insulated pickup drawer with hinges, latch, warning strip and
    # positive green status indication around the actual collection aperture.
    box(
        coll,
        name + ":pickup_hatch_recess",
        (x, y + 0.372, 0.62),
        (0.86, 0.050, 0.49),
        M["kiosk_inset"],
        0.022,
        sem="fixture",
    )
    box(
        coll,
        name + ":pickup_hatch_gasket",
        (x, y + 0.405, 0.62),
        (0.76, 0.025, 0.39),
        M["cable"],
        0.018,
        sem="fixture",
    )
    box(
        coll,
        name + ":pickup_hatch_door",
        (x, y + 0.425, 0.62),
        (0.69, 0.035, 0.32),
        M["kiosk_shell"],
        0.014,
        sem="fixture",
    )
    box(
        coll,
        name + ":pickup_hatch_handle",
        (x, y + 0.465, 0.70),
        (0.32, 0.075, 0.050),
        M["steel"],
        0.012,
        sem="fixture",
    )
    box(
        coll,
        name + ":pickup_hatch_status",
        (x, y + 0.469, 0.815),
        (0.56, 0.012, 0.025),
        M["green_emit"],
        0.004,
        sem="fixture",
    )
    text_obj(
        coll,
        name + ":pickup_hatch_label",
        "OPEN WHEN LIT",
        (x, y + 0.474, 0.53),
        0.039,
        M["paper"],
        0.003,
        bold=False,
    )
    for side in (-1, 1):
        cyl(
            coll,
            name + f":pickup_hinge_{side}",
            (x + side * 0.30, y + 0.424, 0.47),
            0.032,
            0.08,
            M["steel"],
            18,
            (math.pi / 2, 0, 0),
            "fixture",
            0.003,
        )
    cyl(
        coll,
        name + ":pickup_latch",
        (x + 0.27, y + 0.446, 0.70),
        0.027,
        0.035,
        M["black"],
        18,
        (math.pi / 2, 0, 0),
        "fixture",
        0.002,
    )
    # Below-hatch service panel has a recessed seam, keyed lock and compliance plate.
    box(
        coll,
        name + ":lower_service_door_reveal",
        (x, y + 0.371, 0.285),
        (0.82, 0.028, 0.25),
        M["shadow_line"],
        0.012,
        sem="fixture",
    )
    box(
        coll,
        name + ":lower_service_door",
        (x, y + 0.390, 0.285),
        (0.74, 0.020, 0.19),
        M["kiosk_shell"],
        0.010,
        sem="fixture",
    )
    cyl(
        coll,
        name + ":lower_service_lock",
        (x + 0.30, y + 0.409, 0.285),
        0.028,
        0.022,
        M["steel"],
        18,
        (math.pi / 2, 0, 0),
        "fixture",
        0.002,
    )
    box(
        coll,
        name + ":compliance_plate",
        (x - 0.20, y + 0.413, 0.285),
        (0.25, 0.008, 0.095),
        M["paper"],
        0.004,
        sem="fixture",
    )
    for line in range(4):
        box(
            coll,
            name + f":compliance_print_{line}",
            (x - 0.20, y + 0.420, 0.315 - line * 0.020),
            (0.18, 0.004, 0.006),
            M["shadow_line"],
            0.001,
            sem="fixture",
        )
    # Serviceable side panel: louvers are separate slots with fasteners and
    # hinges, plus a protected cable conduit down to the floor connection.
    box(
        coll,
        name + ":side_service_panel",
        (x + 0.612, y - 0.04, 0.75),
        (0.025, 0.52, 0.92),
        M["kiosk_shell"],
        0.008,
        sem="fixture",
    )
    for vi in range(9):
        box(
            coll,
            name + f":side_vent_slot_{vi}",
            (x - 0.612, y - 0.18 + vi * 0.045, 0.83),
            (0.020, 0.026, 0.34),
            M["kiosk_inset"],
            0.002,
            sem="fixture",
        )
    for hz in (0.42, 1.08):
        cyl(
            coll,
            name + ":side_panel_hinge",
            (x + 0.628, y - 0.26, hz),
            0.025,
            0.12,
            M["steel"],
            16,
            sem="fixture",
            bevel=0.002,
        )
    for sx in (-1, 1):
        for sz in (0.28, 1.02, 1.88):
            cyl(
                coll,
                name + f":security_screw_{sx}_{sz}",
                (x + sx * 0.53, y + 0.379, sz),
                0.012,
                0.015,
                M["steel"],
                12,
                (math.pi / 2, 0, 0),
                "fixture",
                0.001,
            )
    curve_tube(
        coll,
        name + ":armoured_power_conduit",
        [
            (x + 0.48, y - 0.30, 0.46),
            (x + 0.48, y - 0.31, 0.20),
            (x + 0.43, y - 0.18, 0.09),
        ],
        0.025,
        M["cable"],
        False,
        "fixture",
    )
    box(
        coll,
        name + ":power_isolator",
        (x + 0.46, y - 0.32, 0.55),
        (0.20, 0.08, 0.24),
        M["kiosk_inset"],
        0.018,
        sem="fixture",
    )
    cyl(
        coll,
        name + ":isolator_indicator",
        (x + 0.46, y - 0.365, 0.59),
        0.018,
        0.012,
        M["amber_emit"],
        14,
        (math.pi / 2, 0, 0),
        "fixture",
        0.002,
    )


def ceiling_grid(coll, name, cx, cy, width, depth, z, M, modern=False):
    box(
        coll,
        name + ":ceiling",
        (cx, cy, z + 0.08),
        (width, depth, 0.16),
        M["ceiling"],
        0.010,
        sem="architecture",
    )
    # Recessed grid rails make the reflected ceiling legible in both interior shots.
    for x in [cx - width / 2 + i * 2.0 for i in range(int(width / 2.0) + 1)]:
        box(
            coll,
            name + ":grid_x",
            (x, cy, z - 0.015),
            (0.025, depth, 0.025),
            M["aluminum"],
            0.002,
            sem="architectural_detail",
        )
    for y in [cy - depth / 2 + i * 2.0 for i in range(int(depth / 2.0) + 1)]:
        box(
            coll,
            name + ":grid_y",
            (cx, y, z - 0.012),
            (width, 0.025, 0.025),
            M["aluminum"],
            0.002,
            sem="architectural_detail",
        )
    # Luminous lenses plus a smaller number of actual area lights.
    for ix, x in enumerate([cx - width * 0.34, cx, cx + width * 0.34]):
        for iy, y in enumerate(
            [cy - depth * 0.35, cy - depth * 0.08, cy + depth * 0.20, cy + depth * 0.39]
        ):
            box(
                coll,
                f"{name}:led_{ix}_{iy}",
                (x, y, z - 0.055),
                (1.55, 0.28, 0.045),
                M["white_emit"],
                0.012,
                sem="lighting_fixture",
            )
            if (ix + iy) % 2 == 0:
                area_light(
                    coll,
                    f"{name}:area_{ix}_{iy}",
                    (x, y, z - 0.16),
                    430,
                    (2.1, 1.1),
                    (1, 0.94, 0.82),
                    (0, 0, 0),
                )


# ---------------------------------------------------------------------------
# Storefront construction


def glazing_bay(
    coll,
    name,
    cx,
    y,
    width,
    height,
    M,
    sill=True,
    poster=None,
    base_z=0.18,
    mullions=1,
    continuity=None,
):
    glass = box(
        coll,
        name + ":glass",
        (cx, y, base_z + height / 2),
        (width, 0.048, height),
        M["glass"],
        0.004,
        sem="glazing",
    )
    if continuity:
        glass["c2w_storefront_run"] = continuity
        glass["c2w_storefront_span"] = (cx - width / 2, cx + width / 2)
    for xx in (cx - width / 2, cx + width / 2):
        box(
            coll,
            name + ":jamb",
            (xx, y + 0.025, base_z + height / 2),
            (0.085, 0.115, height + 0.10),
            M["aluminum"],
            0.006,
            sem="architectural_detail",
        )
    box(
        coll,
        name + ":head",
        (cx, y + 0.025, base_z + height + 0.045),
        (width, 0.115, 0.09),
        M["aluminum"],
        0.006,
        sem="architectural_detail",
    )
    if sill:
        box(
            coll,
            name + ":sill",
            (cx, y + 0.025, base_z),
            (width, 0.145, 0.11),
            M["aluminum"],
            0.006,
            sem="architectural_detail",
        )
    for mi in range(1, mullions + 1):
        mx = cx - width / 2 + width * mi / (mullions + 1)
        box(
            coll,
            name + f":mullion_{mi}",
            (mx, y + 0.035, base_z + height / 2),
            (0.060, 0.115, height),
            M["aluminum"],
            0.004,
            sem="architectural_detail",
        )
    box(
        coll,
        name + ":transom",
        (cx, y + 0.036, base_z + height * 0.72),
        (width, 0.115, 0.060),
        M["aluminum"],
        0.004,
        sem="architectural_detail",
    )
    if poster:
        pm, body = poster
        pz = base_z + height * 0.53
        box(
            coll,
            name + ":poster_board",
            (cx + width * 0.23, y + 0.075, pz),
            (width * 0.25, 0.025, min(1.25, height * 0.54)),
            M[pm],
            0.006,
            sem="signage",
        )
        text_obj(
            coll,
            name + ":poster_text",
            body,
            (cx + width * 0.23, y + 0.095, pz),
            0.14,
            M["poster_white"],
            0.010,
        )
    return glass


def double_door(coll, name, cx, y, width, height, M, sliding=False, continuity=None):
    # True paired leaves, threshold, head track, handles and safety decals.
    leaf = width / 2
    continuity_anchor = None
    for i, side in enumerate((-1, 1)):
        lx = cx + side * leaf / 2
        door_leaf = box(
            coll,
            f"{name}:leaf_{i}",
            (lx, y, height / 2 + 0.13),
            (leaf - 0.09, 0.065, height),
            M["glass_door"],
            0.006,
            sem="glazing",
        )
        if continuity_anchor is None:
            continuity_anchor = door_leaf
        for xx in (lx - leaf / 2 + 0.045, lx + leaf / 2 - 0.045):
            box(
                coll,
                f"{name}:stile_{i}",
                (xx, y + 0.035, height / 2 + 0.13),
                (0.085, 0.14, height + 0.08),
                M["aluminum"],
                0.008,
                sem="architectural_detail",
            )
        box(
            coll,
            f"{name}:toprail_{i}",
            (lx, y + 0.035, height + 0.14),
            (leaf - 0.02, 0.14, 0.10),
            M["aluminum"],
            0.006,
            sem="architectural_detail",
        )
        box(
            coll,
            f"{name}:kickplate_{i}",
            (lx, y + 0.075, 0.34),
            (leaf - 0.14, 0.025, 0.42),
            M["aluminum"],
            0.004,
            sem="architectural_detail",
        )
        if not sliding:
            box(
                coll,
                f"{name}:handle_{i}",
                (lx - side * 0.26, y + 0.12, 1.35),
                (0.035, 0.055, 0.78),
                M["steel"],
                0.010,
                sem="fixture",
            )
            for zz in (0.97, 1.72):
                cyl(
                    coll,
                    f"{name}:handle_mount_{i}",
                    (lx - side * 0.26, y + 0.10, zz),
                    0.045,
                    0.09,
                    M["steel"],
                    20,
                    (math.pi / 2, 0, 0),
                    "fixture",
                    0.003,
                )
        else:
            box(
                coll,
                f"{name}:sensor_{i}",
                (lx, y + 0.02, height + 0.31),
                (0.36, 0.22, 0.15),
                M["black"],
                0.018,
                sem="fixture",
            )
        box(
            coll,
            f"{name}:safety_decal_{i}",
            (lx, y + 0.078, 1.10),
            (0.36, 0.012, 0.075),
            M["poster_white"],
            0.002,
            sem="signage",
        )
    box(
        coll,
        name + ":threshold",
        (cx, y + 0.03, 0.07),
        (width + 0.12, 0.25, 0.08),
        M["steel"],
        0.010,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":header_track",
        (cx, y + 0.02, height + 0.22),
        (width + 0.18, 0.22, 0.20),
        M["aluminum"],
        0.012,
        sem="architectural_detail",
    )
    if continuity and continuity_anchor is not None:
        continuity_anchor["c2w_storefront_run"] = continuity
        continuity_anchor["c2w_storefront_span"] = (cx - width / 2, cx + width / 2)
    return continuity_anchor


def square_column(coll, name, x, y, height, M):
    # Layered base/plinth, tapered-looking shaft and classical capital.
    box(
        coll,
        name + ":plinth_0",
        (x, y, 0.13),
        (0.92, 0.92, 0.26),
        M["concrete_light"],
        0.025,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":plinth_1",
        (x, y, 0.34),
        (0.75, 0.75, 0.20),
        M["white_paint"],
        0.020,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":base_mould",
        (x, y, 0.54),
        (0.65, 0.65, 0.18),
        M["white_paint"],
        0.018,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":base_torus_block",
        (x, y, 0.69),
        (0.56, 0.56, 0.12),
        M["white_stucco"],
        0.015,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":shaft",
        (x, y, height / 2 + 0.34),
        (0.47, 0.47, height - 0.55),
        M["white_paint"],
        0.014,
        sem="architectural_detail",
    )
    # Shallow fluting is modeled as recessed shadow strips on both visible
    # faces.  It reads in oblique close views without turning the column toy-like.
    for i, offset in enumerate((-0.135, -0.045, 0.045, 0.135)):
        box(
            coll,
            name + f":front_flute_{i}",
            (x + offset, y + 0.241, 2.28),
            (0.024, 0.012, 2.90),
            M["shadow_line"],
            0.003,
            sem="architectural_detail",
        )
        box(
            coll,
            name + f":side_flute_{i}",
            (x + 0.241, y + offset, 2.28),
            (0.012, 0.024, 2.90),
            M["shadow_line"],
            0.003,
            sem="architectural_detail",
        )
    box(
        coll,
        name + ":neck",
        (x, y, height - 0.05),
        (0.62, 0.62, 0.16),
        M["white_paint"],
        0.016,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":capital",
        (x, y, height + 0.12),
        (0.82, 0.82, 0.22),
        M["white_paint"],
        0.022,
        sem="architectural_detail",
    )
    box(
        coll,
        name + ":abacus",
        (x, y, height + 0.28),
        (0.94, 0.94, 0.12),
        M["white_stucco"],
        0.018,
        sem="architectural_detail",
    )


def tactile_pad(coll, name, cx, cy, M):
    # Flush warning tile with low rounded studs; the previous tall shared
    # cylinders read as loose blocks in the entrance close-up.
    box(
        coll,
        name + ":base",
        (cx, cy, 0.166),
        (2.05, 1.05, 0.032),
        M["yellow"],
        0.004,
        sem="site_detail",
    )
    for ix in range(8):
        for iy in range(4):
            cyl(
                coll,
                name + f":stud_{ix}_{iy}",
                (cx - 0.84 + ix * 0.24, cy - 0.36 + iy * 0.24, 0.188),
                0.045,
                0.012,
                M["yellow"],
                24,
                sem="site_detail",
                bevel=0.004,
            )


# ---------------------------------------------------------------------------
# CVS-style archetype


def build_cvs_interior(parent, cx, M):
    c = collection("PHARMACY_01_CVS_INTERIOR", parent)
    width = 29.8
    rear = -18.8
    modeled_tile_floor(
        c,
        "cvs_interior_floor",
        cx,
        -9.45,
        width,
        18.6,
        M,
        M["floor_cvs_tiles"],
        0.60,
        0.006,
    )
    box(
        c,
        "cvs_interior_rear_wall",
        (cx, rear, 2.32),
        (width, 0.20, 4.64),
        M["clinical"],
        0.014,
        sem="interior_shell",
    )
    box(
        c,
        "cvs_rear_baseboard",
        (cx, rear + 0.13, 0.13),
        (width, 0.08, 0.24),
        M["counter_dark"],
        0.006,
        sem="architectural_detail",
    )
    for side in (-1, 1):
        box(
            c,
            f"cvs_side_baseboard_{side}",
            (cx + side * (width / 2 - 0.04), -9.45, 0.13),
            (0.08, 18.45, 0.24),
            M["counter_dark"],
            0.006,
            sem="architectural_detail",
        )
    ceiling_grid(c, "cvs_rcp", cx, -9.35, width - 0.45, 18.0, 4.55, M)
    # Four complete gondolas keep a real 1.5 m circulation width and expose
    # dense product silhouettes through the storefront glazing.
    categories = ("COLD + FLU", "VITAMINS", "SKIN CARE", "FIRST AID")
    for i, x in enumerate((cx - 8.7, cx - 2.9, cx + 2.9, cx + 8.7)):
        gondola(c, f"cvs_aisle_{i}", x, -8.25, 8.4, M, math.pi / 2, 5)
        text_obj(
            c,
            f"cvs_category_{i}",
            categories[i],
            (x, -3.73, 2.77),
            0.19,
            M["poster_white"],
            0.014,
        )
    print("[pharmacy5] CVS retail gondolas complete", flush=True)
    # Dense prescription wall, drawer bank and professional service counter.
    for i in range(5):
        wall_shelf(
            c,
            f"cvs_rx_wall_{i}",
            cx - 11.6 + i * 5.8,
            rear + 0.25,
            5.55,
            M,
            modern=False,
            rows=5,
        )
    print("[pharmacy5] CVS prescription wall stock complete", flush=True)
    box(
        c,
        "cvs_rx_header",
        (cx, rear + 0.43, 4.08),
        (28.8, 0.30, 0.70),
        M["red"],
        0.036,
        sem="fixture",
    )
    text_obj(
        c,
        "cvs_rx_header_text",
        "PRESCRIPTIONS   •   CONSULTATION",
        (cx, rear + 0.61, 4.10),
        0.34,
        M["poster_white"],
        0.022,
    )
    pharmacy_counter(c, "cvs_prescription_counter", cx, -14.55, 19.5, M, modern=False)
    # Prescription drawer fronts under the back shelving.
    for ix in range(15):
        for iz in range(3):
            x = cx - 13.15 + ix * 1.88
            box(
                c,
                f"cvs_rx_drawer_{ix}_{iz}",
                (x, rear + 0.48, 0.31 + iz * 0.40),
                (1.68, 0.16, 0.31),
                M["clinical"],
                0.007,
                sem="fixture",
            )
            box(
                c,
                f"cvs_rx_pull_{ix}_{iz}",
                (x, rear + 0.575, 0.31 + iz * 0.40),
                (0.54, 0.028, 0.035),
                M["aluminum"],
                0.003,
                sem="fixture",
            )
    checkout_lane(c, "cvs_checkout_0", cx + 10.7, -2.15, M)
    checkout_lane(c, "cvs_checkout_1", cx + 7.9, -2.15, M)
    # Security pedestals and nested baskets at the offset entrance.
    for x in (cx + 3.15, cx + 6.25):
        box(
            c,
            "cvs_eas_pedestal",
            (x, -0.72, 1.00),
            (0.15, 0.36, 1.96),
            M["frost"],
            0.026,
            sem="fixture",
        )
        box(
            c,
            "cvs_eas_base",
            (x, -0.72, 0.08),
            (0.42, 0.58, 0.12),
            M["steel"],
            0.018,
            sem="fixture",
        )
    for i in range(7):
        box(
            c,
            f"cvs_basket_{i}",
            (cx + 13.2, -1.42, 0.13 + i * 0.09),
            (0.86, 0.50, 0.15),
            M["red"],
            0.025,
            sem="fixture",
        )
        for sx in (-0.32, 0.32):
            cyl(
                c,
                f"cvs_basket_handle_{i}_{sx}",
                (cx + 13.2 + sx, -1.42, 0.32 + i * 0.09),
                0.014,
                0.42,
                M["black"],
                12,
                (math.pi / 2, 0, 0),
                "fixture",
                0.002,
            )
    # Consultation room uses opaque lower panels and frosted upper privacy glass.
    box(
        c,
        "cvs_consult_lower_wall",
        (cx - 12.9, -15.9, 0.72),
        (4.0, 0.10, 1.44),
        M["clinical"],
        0.016,
        sem="fixture",
    )
    box(
        c,
        "cvs_consult_privacy",
        (cx - 12.9, -15.9, 2.65),
        (4.0, 0.065, 2.42),
        M["frost"],
        0.012,
        sem="fixture",
    )
    box(
        c,
        "cvs_consult_desk",
        (cx - 12.9, -17.0, 0.73),
        (2.55, 0.68, 1.34),
        M["wood"],
        0.045,
        sem="fixture",
    )
    pos_terminal(c, "cvs_consult_terminal", (cx - 12.9, -16.84, 1.45), M)
    return c


def build_cvs_store(root, M):
    c = collection("PHARMACY_01_CVS_CLASSICAL", root)
    cx = CVS_X
    w = 32.0
    depth = 19.2
    h = 7.35
    c["c2w_archetype"] = "cvs_classical_portico_red_brick"
    # Real shell with brick returns.  The storefront remains open behind glass,
    # so the actual interior is visible rather than pasted into the elevation.
    box(
        c,
        "cvs_foundation",
        (cx, -depth / 2, -0.08),
        (w, depth, 0.38),
        M["concrete_light"],
        0.026,
        sem="architecture",
    )
    box(
        c,
        "cvs_rear_masonry",
        (cx, -depth - 0.20, h / 2),
        (w, 0.55, h),
        M["brick_red"],
        0.030,
        sem="architecture",
    )
    for side in (-1, 1):
        sx = cx + side * (w / 2 - 0.28)
        box(
            c,
            f"cvs_side_masonry_{side}",
            (sx, -depth / 2, h / 2),
            (0.56, depth, h),
            M["brick_red"],
            0.025,
            sem="architecture",
        )
        # Recessed brick control joints give the long flank a credible scale.
        for jy in (-3.2, -6.4, -9.6, -12.8, -16.0):
            box(
                c,
                f"cvs_side_joint_{side}_{jy}",
                (sx + side * 0.292, jy, 3.4),
                (0.018, 0.045, 6.5),
                M["counter_dark"],
                0.002,
                sem="architectural_detail",
            )
    # Brick wings flank the reference-specific white portico.
    for side in (-1, 1):
        x = cx + side * 14.45
        box(
            c,
            f"cvs_front_brick_wing_{side}",
            (x, -0.02, 3.62),
            (3.10, 0.58, 7.24),
            M["brick_red"],
            0.025,
            sem="architecture",
        )
        box(
            c,
            f"cvs_wing_soldier_course_{side}",
            (x, 0.285, 6.74),
            (3.00, 0.13, 0.18),
            M["red_dark"],
            0.005,
            sem="architectural_detail",
        )
        for iz in range(8):
            qx = cx + side * 15.82
            qz = 0.48 + iz * 0.78
            box(
                c,
                f"cvs_stone_quoin_{side}_{iz}",
                (qx, 0.34, qz),
                (0.34, 0.18, 0.36),
                M["concrete_light"],
                0.008,
                sem="architectural_detail",
            )
        cyl(
            c,
            f"cvs_wall_sconce_{side}",
            (x, 0.34, 2.05),
            0.12,
            0.16,
            M["black"],
            20,
            (math.pi / 2, 0, 0),
            "fixture",
            0.006,
        )
        cyl(
            c,
            f"cvs_wall_sconce_lens_{side}",
            (x, 0.44, 2.05),
            0.083,
            0.025,
            M["warm_emit"],
            20,
            (math.pi / 2, 0, 0),
            "lighting_fixture",
            0.002,
        )
    # Deep sign band and paneled storefront reproduce the reference proportions.
    box(
        c,
        "cvs_white_facade",
        (cx, -0.10, 5.55),
        (26.3, 0.60, 3.55),
        M["white_stucco"],
        0.025,
        sem="architecture",
    )
    box(
        c,
        "cvs_storefront_soffit",
        (cx, 0.42, 4.18),
        (26.6, 1.30, 0.20),
        M["white_paint"],
        0.016,
        sem="architectural_detail",
    )
    bay_centers = [cx - 10.5, cx - 6.3, cx - 2.1, cx + 2.1, cx + 6.3, cx + 10.5]
    bay_width = 4.20
    for i, x in enumerate(bay_centers):
        if i == 3:
            double_door(
                c,
                "cvs_main_entry",
                x,
                0.45,
                bay_width,
                3.70,
                M,
                sliding=True,
                continuity="cvs_ground_storefront",
            )
        else:
            glazing_bay(
                c,
                f"cvs_window_{i}",
                x,
                0.43,
                bay_width,
                2.62,
                M,
                True,
                ("poster_blue", "HEALTH + CARE") if i == 5 else None,
                base_z=1.12,
                mullions=1,
                continuity="cvs_ground_storefront",
            )
            # Recessed lower joinery panel, with a projecting frame and sill.
            box(
                c,
                f"cvs_lower_panel_{i}",
                (x, 0.46, 0.57),
                (bay_width, 0.20, 0.92),
                M["white_paint"],
                0.014,
                sem="architectural_detail",
            )
            box(
                c,
                f"cvs_panel_inset_{i}",
                (x, 0.575, 0.57),
                (3.72, 0.035, 0.61),
                M["white_stucco"],
                0.006,
                sem="architectural_detail",
            )
            for px in (x - 1.98, x + 1.98):
                box(
                    c,
                    f"cvs_panel_stile_{i}",
                    (px, 0.59, 0.57),
                    (0.10, 0.05, 0.76),
                    M["white_paint"],
                    0.004,
                    sem="architectural_detail",
                )
    # One continuous head rail and exact shared module boundaries eliminate the
    # former dark slits between nominally adjacent window units.
    box(
        c,
        "cvs_storefront_continuous_head_rail",
        (cx, 0.515, 3.99),
        (25.28, 0.18, 0.18),
        M["aluminum"],
        0.009,
        sem="architectural_detail",
    )
    # Projecting classical colonnade with a deliberately clear entrance.  The
    # former index-3 column stood inside the sliding-door travel path and is
    # omitted; a concealed steel transfer member carries the wider soffit bay.
    column_positions = (
        (0, cx - 12.65),
        (1, cx - 7.60),
        (2, cx - 2.55),
        (4, cx + 7.60),
        (5, cx + 12.65),
    )
    for i, x in column_positions:
        square_column(c, f"cvs_portico_column_{i}", x, 1.20, 3.88, M)
    box(
        c,
        "cvs_entry_clear_span_steel_lintel",
        (CVS_ENTRY_X, 0.55, 4.035),
        (9.62, 0.42, 0.18),
        M["steel"],
        0.010,
        sem="architectural_detail",
    )
    box(
        c,
        "cvs_entry_clear_span_finish",
        (CVS_ENTRY_X, 0.69, 4.025),
        (9.70, 0.18, 0.16),
        M["white_paint"],
        0.009,
        sem="architectural_detail",
    )
    # Panelled portico soffit with recessed coffers between structural bays.
    column_x = tuple(x for _, x in column_positions)
    for i, (xa, xb) in enumerate(zip(column_x, column_x[1:])):
        mid = (xa + xb) / 2
        box(
            c,
            f"cvs_soffit_coffer_shadow_{i}",
            (mid, 0.53, 4.065),
            (xb - xa - 0.38, 0.70, 0.030),
            M["shadow_line"],
            0.004,
            sem="architectural_detail",
        )
        box(
            c,
            f"cvs_soffit_coffer_inset_{i}",
            (mid, 0.53, 4.043),
            (xb - xa - 0.68, 0.52, 0.018),
            M["white_stucco"],
            0.003,
            sem="architectural_detail",
        )
    for name, z, front_depth, height, width in [
        ("architrave", 4.36, 0.92, 0.25, 27.1),
        ("frieze", 4.70, 0.78, 0.44, 27.0),
        ("cornice_lower", 7.00, 0.95, 0.19, 27.2),
        ("cornice_mid", 7.23, 1.12, 0.18, 27.7),
        ("cornice_crown", 7.46, 1.34, 0.20, 28.2),
    ]:
        box(
            c,
            "cvs_" + name,
            (cx, 0.47, z),
            (width, front_depth, height),
            M["white_paint"],
            0.016,
            sem="architectural_detail",
        )
    for i in range(31):
        x = cx - 13.0 + i * 0.865
        box(
            c,
            f"cvs_dentil_{i}",
            (x, 1.04, 6.78),
            (0.34, 0.46, 0.22),
            M["white_paint"],
            0.007,
            sem="architectural_detail",
        )
    # Deep channel-letter returns plus larger illuminated faces.  The full word
    # remains comfortably inside the 26.3 m x 3.55 m sign field.
    text_obj(
        c,
        "cvs_primary_sign_return",
        "CVS/pharmacy",
        (cx + 1.55, 0.585, 5.78),
        1.46,
        M["red_dark"],
        0.095,
    )
    text_obj(
        c,
        "cvs_primary_sign",
        "CVS/pharmacy",
        (cx + 1.55, 0.705, 5.78),
        1.46,
        M["red_emit"],
        0.070,
    )
    box(
        c,
        "cvs_24h_badge",
        (cx - 10.55, 0.58, 5.79),
        (2.35, 0.20, 1.64),
        M["red"],
        0.16,
        sem="signage",
    )
    box(
        c,
        "cvs_24h_badge_frame",
        (cx - 10.55, 0.705, 5.79),
        (2.47, 0.045, 1.76),
        M["red_dark"],
        0.035,
        sem="signage",
    )
    box(
        c,
        "cvs_24h_badge_face",
        (cx - 10.55, 0.735, 5.79),
        (2.31, 0.025, 1.60),
        M["red"],
        0.025,
        sem="signage",
    )
    text_obj(
        c,
        "cvs_24_numeral",
        "24",
        (cx - 10.55, 0.785, 6.05),
        0.68,
        M["poster_white"],
        0.032,
    )
    text_obj(
        c,
        "cvs_hours_word",
        "HOURS",
        (cx - 10.55, 0.790, 5.42),
        0.22,
        M["poster_white"],
        0.018,
    )
    # Low shingle roof: two real planes, ridge flashing and concealed plant.
    angle = math.radians(8.0)
    box(
        c,
        "cvs_roof_front",
        (cx, -4.74, 7.90),
        (31.4, 9.75, 0.24),
        M["roof"],
        0.010,
        (-angle, 0, 0),
        "architecture",
    )
    box(
        c,
        "cvs_roof_rear",
        (cx, -14.25, 7.90),
        (31.4, 9.75, 0.24),
        M["roof"],
        0.010,
        (angle, 0, 0),
        "architecture",
    )
    box(
        c,
        "cvs_roof_ridge",
        (cx, -9.5, 8.58),
        (31.6, 0.28, 0.22),
        M["black"],
        0.024,
        sem="architectural_detail",
    )
    box(
        c,
        "cvs_eaves_gutter",
        (cx, 0.02, 7.52),
        (31.35, 0.30, 0.24),
        M["aluminum"],
        0.045,
        sem="architectural_detail",
    )
    for side in (-1, 1):
        x = cx + side * 15.20
        curve_tube(
            c,
            f"cvs_downpipe_{side}",
            [
                (x, 0.20, 7.47),
                (x, 0.40, 7.10),
                (x, 0.40, 0.42),
                (x + side * 0.28, 0.65, 0.25),
            ],
            0.070,
            M["aluminum"],
            False,
            "architectural_detail",
        )
        for iz in (1.55, 3.35, 5.15):
            box(
                c,
                f"cvs_downpipe_bracket_{side}",
                (x, 0.325, iz),
                (0.24, 0.055, 0.055),
                M["steel"],
                0.006,
                sem="architectural_detail",
            )
    for i, x in enumerate((cx - 7.0, cx + 7.0)):
        box(
            c,
            f"cvs_hvac_{i}",
            (x, -11.2, 8.55),
            (3.0, 2.15, 0.92),
            M["aluminum"],
            0.050,
            sem="roof_equipment",
        )
        for k in range(5):
            box(
                c,
                f"cvs_hvac_louver_{i}_{k}",
                (x, -10.10, 8.25 + k * 0.10),
                (2.45, 0.025, 0.035),
                M["black"],
                0.002,
                sem="architectural_detail",
            )
        cyl(
            c,
            f"cvs_hvac_fan_{i}",
            (x, -11.2, 9.04),
            0.48,
            0.055,
            M["black"],
            28,
            sem="roof_equipment",
            bevel=0.004,
        )
    build_cvs_interior(c, cx, M)
    return c


# ---------------------------------------------------------------------------
# Well-style high-street archetype


def build_well_interior(parent, cx, M):
    c = collection("PHARMACY_02_WELL_INTERIOR", parent)
    width = 24.9
    rear = -18.25
    modeled_tile_floor(
        c,
        "well_interior_floor",
        cx,
        -9.15,
        width,
        18.1,
        M,
        M["floor_well_tiles"],
        0.60,
        0.006,
    )
    box(
        c,
        "well_rear_clinical_wall",
        (cx, rear, 2.28),
        (width, 0.20, 4.56),
        M["clinical"],
        0.014,
        sem="interior_shell",
    )
    box(
        c,
        "well_rear_baseboard",
        (cx, rear + 0.13, 0.13),
        (width, 0.08, 0.24),
        M["kiosk_inset"],
        0.006,
        sem="architectural_detail",
    )
    for side in (-1, 1):
        box(
            c,
            f"well_side_baseboard_{side}",
            (cx + side * (width / 2 - 0.04), -9.15, 0.13),
            (0.08, 17.95, 0.24),
            M["kiosk_inset"],
            0.006,
            sem="architectural_detail",
        )
    ceiling_grid(c, "well_rcp", cx, -8.55, width - 0.35, 16.8, 4.42, M, modern=True)
    # Black sculptural ceiling insert and reference-driven cyan/white light ribbons.
    box(
        c,
        "well_feature_ceiling",
        (cx, -13.65, 4.30),
        (19.5, 7.8, 0.23),
        M["navy"],
        0.026,
        sem="architectural_detail",
    )
    for j, offset in enumerate((-1.0, 0, 1.0)):
        pts = []
        for i in range(18):
            t = i / 17
            pts.append(
                (
                    cx - 8.8 + 17.6 * t,
                    -13.55 + offset + math.sin(t * math.pi * 2 + j * 0.55) * 0.38,
                    4.16,
                )
            )
        curve_tube(
            c,
            f"well_ceiling_ribbon_{j}",
            pts,
            0.043,
            M["cyan" if j == 1 else "white_emit"],
            False,
            "lighting_fixture",
        )
    # Reference interior: central service counter, tall stocked wall displays.
    for i in range(4):
        wall_shelf(
            c,
            f"well_rx_wall_{i}",
            cx - 9.15 + i * 6.1,
            rear + 0.23,
            5.85,
            M,
            modern=True,
            rows=5,
        )
    print("[pharmacy5] Well prescription wall stock complete", flush=True)
    text_obj(
        c,
        "well_interior_pharmacy_sign",
        "Pharmacy",
        (cx, rear + 0.62, 4.02),
        0.54,
        M["cyan"],
        0.030,
        bold=False,
    )
    pharmacy_counter(c, "well_clinical_counter", cx, -14.35, 16.8, M, modern=True)
    # Three lower gondolas preserve sight lines to the sculptural ceiling.
    for i, x in enumerate((cx - 7.0, cx, cx + 7.0)):
        gondola(c, f"well_retail_gondola_{i}", x, -7.7, 7.6, M, math.pi / 2, 5)
    print("[pharmacy5] Well foreground retail stock complete", flush=True)
    checkout_lane(c, "well_checkout", cx + 8.8, -2.35, M, modern=True)
    # Front prescription pickup kiosk is a complete manufactured assembly,
    # particularly important in the storefront reference-close view.
    prescription_pickup_kiosk(c, "well_prescription_pickup_kiosk", cx - 9.6, -2.25, M)
    # Consultation alcove and upholstered visitor stools.
    box(
        c,
        "well_consult_partition",
        (cx + 9.6, -15.55, 1.92),
        (3.4, 0.09, 3.84),
        M["frost"],
        0.016,
        sem="fixture",
    )
    box(
        c,
        "well_consult_table",
        (cx + 9.6, -16.55, 0.73),
        (2.3, 0.72, 0.12),
        M["wood"],
        0.030,
        sem="fixture",
    )
    for x in (cx + 8.95, cx + 10.25):
        cyl(
            c,
            "well_consult_stool",
            (x, -15.75, 0.48),
            0.29,
            0.18,
            M["clinical_blue"],
            28,
            sem="fixture",
            bevel=0.014,
        )
        cyl(
            c,
            "well_consult_stool_post",
            (x, -15.75, 0.24),
            0.045,
            0.46,
            M["steel"],
            18,
            sem="fixture",
            bevel=0.005,
        )
        cyl(
            c,
            "well_consult_stool_base",
            (x, -15.75, 0.04),
            0.22,
            0.045,
            M["steel"],
            24,
            sem="fixture",
            bevel=0.006,
        )
    return c


def logo_plus(coll, name, x, y, z, M):
    # Four rounded luminous lobes reproduce the recognizable abstract pharmacy cross.
    box(
        coll,
        name + ":vertical",
        (x, y, z),
        (0.38, 0.20, 1.26),
        M["white_emit"],
        0.16,
        sem="signage",
    )
    box(
        coll,
        name + ":horizontal",
        (x, y + 0.01, z),
        (1.26, 0.20, 0.38),
        M["white_emit"],
        0.16,
        sem="signage",
    )
    cyl(
        coll,
        name + ":cyan_core",
        (x, y + 0.12, z),
        0.128,
        0.038,
        M["cyan"],
        28,
        (math.pi / 2, 0, 0),
        "signage",
        0.008,
    )


def build_well_store(root, M):
    c = collection("PHARMACY_02_WELL_HIGH_STREET", root)
    cx = WELL_X
    w = 27.0
    depth = 18.6
    h = 9.75
    c["c2w_archetype"] = "well_urban_high_street_illuminated"
    box(
        c,
        "well_foundation",
        (cx, -depth / 2, -0.08),
        (w, depth, 0.38),
        M["concrete"],
        0.026,
        sem="architecture",
    )
    box(
        c,
        "well_rear_wall",
        (cx, -depth - 0.20, h / 2),
        (w, 0.55, h),
        M["brick_dark"],
        0.030,
        sem="architecture",
    )
    box(
        c,
        "well_left_wall",
        (cx - w / 2 + 0.28, -depth / 2, h / 2),
        (0.56, depth, h),
        M["brick_dark"],
        0.025,
        sem="architecture",
    )
    box(
        c,
        "well_right_wall",
        (cx + w / 2 - 0.28, -depth / 2, h / 2),
        (0.56, depth, h),
        M["brick_dark"],
        0.025,
        sem="architecture",
    )
    box(
        c,
        "well_upper_floor_slab",
        (cx, -depth / 2, 5.28),
        (w - 0.5, depth - 0.5, 0.28),
        M["concrete"],
        0.020,
        sem="architecture",
    )
    box(
        c,
        "well_flat_roof",
        (cx, -depth / 2, 9.72),
        (w - 0.45, depth - 0.45, 0.32),
        M["roof"],
        0.020,
        sem="architecture",
    )
    # Upper masonry residential/office level visible in the reference.
    box(
        c,
        "well_upper_front",
        (cx, -0.08, 7.55),
        (w, 0.58, 4.15),
        M["brick_dark"],
        0.028,
        sem="architecture",
    )
    for i, x in enumerate((cx - 9.6, cx - 3.2, cx + 3.2, cx + 9.6)):
        box(
            c,
            f"well_upper_reveal_{i}",
            (x, 0.29, 7.62),
            (3.45, 0.27, 2.55),
            M["navy"],
            0.026,
            sem="architectural_detail",
        )
        box(
            c,
            f"well_upper_glass_{i}",
            (x, 0.46, 7.62),
            (3.08, 0.045, 2.22),
            M["glass"],
            0.004,
            sem="glazing",
        )
        for sx in (-0.77, 0.77):
            box(
                c,
                f"well_upper_mullion_{i}",
                (x + sx, 0.51, 7.62),
                (0.060, 0.10, 2.22),
                M["aluminum"],
                0.004,
                sem="architectural_detail",
            )
        box(
            c,
            f"well_upper_transom_{i}",
            (x, 0.51, 7.68),
            (3.08, 0.10, 0.060),
            M["aluminum"],
            0.004,
            sem="architectural_detail",
        )
        box(
            c,
            f"well_upper_sill_{i}",
            (x, 0.48, 6.40),
            (3.48, 0.21, 0.13),
            M["concrete_light"],
            0.010,
            sem="architectural_detail",
        )
        box(
            c,
            f"well_upper_lintel_{i}",
            (x, 0.40, 8.94),
            (3.56, 0.25, 0.18),
            M["navy_edge"],
            0.010,
            sem="architectural_detail",
        )
        for side in (-1, 1):
            box(
                c,
                f"well_window_return_{i}_{side}",
                (x + side * 1.62, 0.44, 7.62),
                (0.14, 0.22, 2.40),
                M["aluminum"],
                0.007,
                sem="architectural_detail",
            )
    # Monolithic navy shopfront frame and deep illuminated fascia.
    box(
        c,
        "well_fascia",
        (cx, 0.25, 4.72),
        (w, 0.56, 1.34),
        M["navy_matte"],
        0.038,
        sem="architecture",
    )
    box(
        c,
        "well_left_pier",
        (cx - w / 2 + 0.62, 0.31, 2.38),
        (1.24, 0.60, 4.76),
        M["navy"],
        0.026,
        sem="architecture",
    )
    box(
        c,
        "well_right_pier",
        (cx + w / 2 - 0.62, 0.31, 2.38),
        (1.24, 0.60, 4.76),
        M["navy"],
        0.026,
        sem="architecture",
    )
    box(
        c,
        "well_fascia_lower_trim",
        (cx, 0.58, 4.04),
        (w - 1.2, 0.13, 0.14),
        M["aluminum"],
        0.009,
        sem="architectural_detail",
    )
    box(
        c,
        "well_fascia_upper_reveal",
        (cx, 0.575, 5.39),
        (w - 0.35, 0.055, 0.055),
        M["navy_edge"],
        0.006,
        sem="architectural_detail",
    )
    box(
        c,
        "well_fascia_lower_reveal",
        (cx, 0.598, 4.14),
        (w - 0.80, 0.040, 0.045),
        M["navy_edge"],
        0.004,
        sem="architectural_detail",
    )
    for i in range(1, 11):
        x = cx - w / 2 + i * w / 11
        box(
            c,
            f"well_fascia_panel_joint_{i}",
            (x, 0.548, 4.72),
            (0.016, 0.025, 1.13),
            M["navy_edge"],
            0.002,
            sem="architectural_detail",
        )
    for side in (-1, 1):
        px = cx + side * (w / 2 - 0.62)
        for iz in range(4):
            box(
                c,
                f"well_pier_reveal_{side}_{iz}",
                (px, 0.625, 0.65 + iz * 0.96),
                (0.82, 0.022, 0.025),
                M["navy_edge"],
                0.003,
                sem="architectural_detail",
            )
    # Sliding entrance and display bays share exact boundary coordinates.  A
    # narrow sidelight closes the old entry-to-pier gap, producing one continuous
    # shopfront run while retaining honest mullions and door stiles.
    double_door(
        c,
        "well_main_sliding_entry",
        WELL_ENTRY_X,
        0.45,
        4.40,
        3.78,
        M,
        sliding=True,
        continuity="well_ground_storefront",
    )
    glazing_bay(
        c,
        "well_entry_sidelight",
        cx + 11.98,
        0.44,
        0.56,
        3.72,
        M,
        True,
        None,
        base_z=0.18,
        mullions=0,
        continuity="well_ground_storefront",
    )
    glazing_bay(
        c,
        "well_display_left",
        cx + 5.30,
        0.44,
        4.00,
        3.72,
        M,
        True,
        None,
        base_z=0.18,
        mullions=1,
        continuity="well_ground_storefront",
    )
    glazing_bay(
        c,
        "well_display_center",
        cx - 0.65,
        0.44,
        7.90,
        3.72,
        M,
        True,
        ("poster_blue", "ORDER + COLLECT"),
        base_z=0.18,
        mullions=2,
        continuity="well_ground_storefront",
    )
    glazing_bay(
        c,
        "well_display_right",
        cx - 8.43,
        0.44,
        7.66,
        3.72,
        M,
        True,
        ("poster_teal", "HEALTH ADVICE"),
        base_z=0.18,
        mullions=2,
        continuity="well_ground_storefront",
    )
    box(
        c,
        "well_storefront_continuous_head_rail",
        (cx, 0.535, 4.015),
        (24.52, 0.16, 0.13),
        M["aluminum"],
        0.008,
        sem="architectural_detail",
    )
    # Logo, name and reference tagline, all raised from the fascia.
    logo_plus(c, "well_exterior_cross", cx + 11.35, 0.64, 4.74, M)
    text_obj(
        c,
        "well_primary_sign_return",
        "well",
        (cx + 7.05, 0.585, 4.75),
        1.90,
        M["navy_edge"],
        0.085,
        bold=True,
        xscale=1.35,
    )
    text_obj(
        c,
        "well_primary_sign",
        "well",
        (cx + 7.05, 0.705, 4.75),
        1.90,
        M["white_emit"],
        0.060,
        bold=True,
        xscale=1.35,
    )
    text_obj(
        c,
        "well_pharmacy_word_return",
        "Pharmacy",
        (cx + 1.55, 0.585, 4.74),
        1.00,
        M["navy_edge"],
        0.070,
        bold=True,
        xscale=1.06,
    )
    text_obj(
        c,
        "well_pharmacy_word",
        "Pharmacy",
        (cx + 1.55, 0.705, 4.74),
        1.00,
        M["white_emit"],
        0.050,
        bold=True,
        xscale=1.06,
    )
    text_obj(
        c,
        "well_tagline",
        "feel better for longer",
        (cx - 7.00, 0.69, 4.72),
        0.225,
        M["white_emit"],
        0.024,
        bold=False,
    )
    # Recessed entrance lights, threshold mat and tactile access strip.
    box(
        c,
        "well_entry_mat",
        (WELL_ENTRY_X, 0.72, 0.068),
        (4.05, 1.25, 0.045),
        M["rubber"],
        0.009,
        sem="site_detail",
    )
    for x in (cx + 8.2, WELL_ENTRY_X, cx + 10.8):
        cyl(
            c,
            "well_soffit_downlight",
            (x, 0.35, 3.96),
            0.078,
            0.028,
            M["white_emit"],
            20,
            sem="lighting_fixture",
            bevel=0.003,
        )
    # Parapet cap, rainwater goods and roof plant screen.
    box(
        c,
        "well_parapet_cap",
        (cx, -0.08, 9.87),
        (w + 0.25, 0.78, 0.20),
        M["concrete_light"],
        0.018,
        sem="architectural_detail",
    )
    cyl(
        c,
        "well_rain_downpipe",
        (cx - 12.45, -0.38, 4.65),
        0.065,
        8.95,
        M["aluminum"],
        18,
        sem="architectural_detail",
        bevel=0.003,
    )
    for iz in (1.2, 3.2, 5.2, 7.2):
        box(
            c,
            "well_downpipe_bracket",
            (cx - 12.45, -0.19, iz),
            (0.24, 0.43, 0.055),
            M["steel"],
            0.006,
            sem="architectural_detail",
        )
    for i in range(12):
        box(
            c,
            f"well_parapet_coping_joint_{i}",
            (cx - w / 2 + 1.1 + i * 2.25, 0.325, 9.91),
            (0.018, 0.34, 0.045),
            M["shadow_line"],
            0.002,
            sem="architectural_detail",
        )
    box(
        c,
        "well_roof_screen",
        (cx, -11.2, 10.62),
        (9.2, 3.8, 1.45),
        M["navy_matte"],
        0.040,
        sem="roof_equipment",
    )
    for k in range(7):
        box(
            c,
            f"well_screen_louver_{k}",
            (cx, -9.28, 10.14 + k * 0.13),
            (8.55, 0.028, 0.050),
            M["aluminum"],
            0.002,
            sem="architectural_detail",
        )
    build_well_interior(c, cx, M)
    return c


# ---------------------------------------------------------------------------
# Shared pedestrian public realm


def build_site(root, M):
    c = collection("PHARMACY_ROW_PUBLIC_REALM", root)
    site_cx = -1.5
    site_w = 72.0
    box(
        c,
        "site_subgrade",
        (site_cx, 32.0, -0.58),
        (site_w + 4, 110, 1.0),
        M["concrete"],
        0.015,
        sem="site",
    )
    box(
        c,
        "pharmacy_sidewalk",
        (site_cx, 3.15, 0.04),
        (site_w, 6.2, 0.28),
        M["concrete"],
        0.020,
        sem="site",
    )
    # The former car park is now a level pedestrian forecourt.  It has no bay
    # striping, wheel stops, accessible-car symbols or kerb separating people
    # from the storefront.  Flamed pavers and dark recessed joints provide an
    # appropriately scaled but visually quiet public surface.
    box(
        c,
        "pedestrian_forecourt",
        (site_cx, 46.0, 0.045),
        (site_w, 79.0, 0.25),
        M["forecourt_paver"],
        0.012,
        sem="site",
    )
    box(
        c,
        "flush_forecourt_transition",
        (site_cx, 6.28, 0.165),
        (site_w, 0.34, 0.045),
        M["steel"],
        0.008,
        sem="site_detail",
    )
    # Sidewalk slab joints and pedestrian-forecourt paver joints.
    for x in [site_cx + i * 2.45 for i in range(-14, 15)]:
        instance_part(
            c,
            "paving_joint",
            (x, 3.12, 0.192),
            (0.018, 5.95, 0.010),
            M["counter_dark"],
            "cube",
            0,
            "site_detail",
        )
    for y in (1.15, 3.15, 5.15):
        instance_part(
            c,
            "paving_joint_long",
            (site_cx, y, 0.192),
            (site_w - 0.5, 0.018, 0.010),
            M["counter_dark"],
            "cube",
            0,
            "site_detail",
        )
    for x in [site_cx + i * 1.20 for i in range(-29, 30)]:
        instance_part(
            c,
            "forecourt_paver_joint_x",
            (x, 46.0, 0.171),
            (0.010, 78.4, 0.003),
            M["tile_grout"],
            "cube",
            0,
            "site_detail",
        )
    for iy, y in enumerate([6.8 + i * 1.20 for i in range(66)]):
        # Alternate half-module transverse starts are expressed through short
        # brass datum tabs, making the coursing visibly staggered rather than a
        # parking-space grid.
        instance_part(
            c,
            "forecourt_paver_joint_y",
            (site_cx, y, 0.171),
            (site_w - 0.5, 0.010, 0.003),
            M["tile_grout"],
            "cube",
            0,
            "site_detail",
        )
        if iy % 2:
            for x in (-25.5, -1.5, 22.5):
                box(
                    c,
                    "forecourt_brass_datum",
                    (x, y, 0.172),
                    (0.28, 0.018, 0.004),
                    M["steel"],
                    0.001,
                    sem="site_detail",
                )
    # Cast iron trench drains in front of both entrances.
    for entry_x in (CVS_ENTRY_X, WELL_ENTRY_X):
        box(
            c,
            "trench_drain_frame",
            (entry_x, 5.82, 0.205),
            (3.7, 0.32, 0.085),
            M["black"],
            0.008,
            sem="site_detail",
        )
        for i in range(16):
            box(
                c,
                "trench_drain_slot",
                (entry_x - 1.72 + i * 0.23, 5.82, 0.252),
                (0.055, 0.25, 0.020),
                M["steel"],
                0.002,
                sem="site_detail",
            )
    tactile_pad(c, "cvs_tactile_pad", CVS_ENTRY_X, 1.42, M)
    tactile_pad(c, "well_tactile_pad", WELL_ENTRY_X, 1.38, M)
    # Stainless bollards with reflective bands; kept away from door swing zones.
    for i, x in enumerate((-32.5, -28.8, -7.2, -3.7, 4.8, 29.5)):
        cyl(
            c,
            f"storefront_bollard_{i}",
            (x, 5.35, 0.57),
            0.095,
            1.14,
            M["steel"],
            24,
            sem="site_detail",
            bevel=0.009,
        )
        cyl(
            c,
            f"bollard_band_{i}",
            (x, 5.35, 0.77),
            0.100,
            0.12,
            M["poster_white"],
            24,
            sem="site_detail",
            bevel=0.003,
        )
    return c


def set_prefix(value: str):
    """Set the namespace used when this generator is embedded in another scene."""
    global PREFIX
    PREFIX = value
    G.PREFIX = value


def build_pharmacy_reference_row(parent=None, include_site=True):
    """Live Urban-v3 pipeline entrypoint for both reference pharmacy types.

    This function never reads the validation blend.  It creates the exact same
    procedural geometry used below, making subsequent pipeline scenes immune to
    stale demo assets.
    """
    RNG.seed(260831)
    SHARED_MESHES.clear()
    M = materials()
    root = collection("URBAN_V3_PHARMACY_REFERENCE_ROW", parent)
    root["c2w_asset_id"] = ASSET_ID
    root[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_pharmacy.build_pharmacy_reference_row"
    root["c2w_reference_driven"] = True
    root["c2w_scene_asset_inputs"] = 0
    build_cvs_store(root, M)
    build_well_store(root, M)
    if include_site:
        build_site(root, M)
    return root, M


def archive_references():
    """Copy the already archived user references into the new result folder."""
    previous = (
        ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_pharmacy4/references"
    )
    for filename in REFERENCE_FILES:
        dst = REFERENCES / filename
        if dst.is_file() and dst.stat().st_size > 10000:
            continue
        src = previous / filename
        if not src.is_file():
            raise FileNotFoundError(f"Missing reference image inside workspace: {src}")
        shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Lighting, rendering and validation


def setup_world():
    world = bpy.data.worlds.new(PREFIX + "physical_day_world")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(138)
    sky.altitude = 0.15
    sky.air_density = 1.05
    sky.dust_density = 1.8
    bg.inputs["Strength"].default_value = 0.28
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bpy.context.scene.world = world
    bpy.ops.object.light_add(type="SUN", location=(-35, 25, 58))
    sun = bpy.context.object
    sun.name = PREFIX + "day_sun"
    sun.data.energy = 2.15
    sun.data.angle = math.radians(1.2)
    sun.rotation_euler = (math.radians(31), math.radians(-22), math.radians(-38))
    sun["c2w_semantic"] = "daylight"


def configure_scene(preview=False):
    s = bpy.context.scene
    s.render.engine = "BLENDER_EEVEE_NEXT"
    s.render.resolution_x = 900 if preview else 1600
    s.render.resolution_y = 560 if preview else 1000
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.film_transparent = False
    s.render.image_settings.color_depth = "8"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.exposure = -0.35
    s.render.image_settings.compression = 25
    # Eevee render samples moved between API locations in Blender 4.x; keep a
    # version-safe assignment while retaining a deterministic final setting.
    if hasattr(s, "eevee"):
        s.eevee.taa_render_samples = 8 if preview else 16
    if hasattr(s, "eevee") and hasattr(s.eevee, "taa_samples"):
        s.eevee.taa_samples = 8 if preview else 16
    s.camera = None


def camera_specs():
    return [
        (
            "01_row_daylight_overview.png",
            (-1.0, 59.0, 12.5),
            (-1.0, -3.8, 4.0),
            35,
            "far",
        ),
        ("02_row_oblique_wide.png", (-52.0, 48.0, 10.2), (-1.0, -4.8, 3.8), 43, "far"),
        (
            "03_cvs_reference_close.png",
            (-30.0, 30.0, 5.2),
            (CVS_X, 0.2, 4.0),
            44,
            "near",
        ),
        (
            "04_cvs_portico_detail.png",
            (CVS_ENTRY_X - 5.2, 11.5, 2.65),
            (CVS_ENTRY_X, 0.75, 1.95),
            49,
            "near",
        ),
        (
            "05_well_reference_close.png",
            (30.0, 30.0, 5.0),
            (WELL_X, 0.15, 4.55),
            43,
            "near",
        ),
        (
            "06_well_signage_detail.png",
            (22.0, 11.5, 5.0),
            (WELL_X, 0.50, 4.75),
            58,
            "near",
        ),
        (
            "07_cvs_interior_full.png",
            (CVS_X + 2.1, -0.45, 1.72),
            (CVS_X, -14.8, 1.75),
            36,
            "interior",
        ),
        (
            "08_well_interior_full.png",
            (WELL_X + 3.5, -2.2, 1.74),
            (WELL_X, -15.2, 1.82),
            38,
            "interior",
        ),
        (
            "09_well_pharmacy_counter.png",
            (WELL_X + 3.4, -9.2, 1.72),
            (WELL_X - 0.5, -14.4, 1.43),
            58,
            "interior_close",
        ),
        (
            "10_inventory_support_detail.png",
            (CVS_X - 4.6, -5.0, 1.32),
            (CVS_X - 2.9, -8.2, 1.12),
            58,
            "inventory_close",
        ),
        (
            "11_well_pickup_kiosk_close.png",
            (WELL_X - 9.6, 0.20, 1.16),
            (WELL_X - 9.6, -2.28, 1.10),
            21,
            "fixture_close",
        ),
    ]


def object_counts():
    counts = {}
    for obj in bpy.data.objects:
        sem = obj.get("c2w_semantic", "unclassified")
        counts[sem] = counts.get(sem, 0) + 1
    return dict(sorted(counts.items()))


def inventory_support_audit():
    """Measure every sellable package against its declared shelf top."""
    shelf_names = {
        o.name for o in bpy.data.objects if o.get("c2w_semantic") == "shelf_deck"
    }
    supported = []
    errors = []
    worst_gap = 0.0
    for obj in bpy.data.objects:
        if obj.get("c2w_semantic") != "product":
            continue
        relation = obj.get("c2w_support_relation")
        support_name = obj.get("c2w_support_name", "")
        if relation != "rests_on_shelf" or support_name not in shelf_names:
            errors.append(
                {"object": obj.name, "reason": "missing_modeled_shelf_relation"}
            )
            continue
        support_z = float(obj.get("c2w_support_top_z"))
        geometry_base = min(
            (obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box
        )
        gap = geometry_base - support_z
        worst_gap = max(worst_gap, abs(gap))
        if abs(gap) > 0.0015:
            errors.append(
                {
                    "object": obj.name,
                    "reason": "floating" if gap > 0 else "penetrating",
                    "gap_m": round(gap, 6),
                }
            )
        supported.append(obj)
    return {
        "sellable_product_bodies": sum(
            o.get("c2w_semantic") == "product" for o in bpy.data.objects
        ),
        "modeled_shelf_decks": len(shelf_names),
        "supported_product_bodies": len(supported),
        "support_error_count": len(errors),
        "worst_absolute_gap_m": round(worst_gap, 6),
        "sample_errors": errors[:20],
        "passed": len(supported) >= 2500 and not errors,
    }


def _world_aabb(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(
        max(p[i] for p in points) for i in range(3)
    )


def _aabb_gap(a, b):
    amin, amax = _world_aabb(a)
    bmin, bmax = _world_aabb(b)
    gaps = [max(amin[i] - bmax[i], bmin[i] - amax[i], 0.0) for i in range(3)]
    return math.sqrt(sum(g * g for g in gaps))


def package_attachment_audit():
    """Check every visible package component is connected to its assembly."""
    by_name = {o.name: o for o in bpy.data.objects}
    components = [
        o
        for o in bpy.data.objects
        if o.get("c2w_semantic") in {"product_detail", "product_label"}
    ]
    errors = []
    worst_gap = 0.0
    checked = 0
    for obj in components:
        parent = by_name.get(obj.get("c2w_attached_to", ""))
        root = by_name.get(obj.get("c2w_assembly_root", ""))
        if parent is None or root is None or root.get("c2w_semantic") != "product":
            errors.append(
                {"object": obj.name, "reason": "missing_package_attachment_chain"}
            )
            continue
        gap = _aabb_gap(obj, parent)
        worst_gap = max(worst_gap, gap)
        if gap > 0.026:
            errors.append(
                {
                    "object": obj.name,
                    "reason": "detached_package_component",
                    "gap_m": round(gap, 6),
                }
            )
        checked += 1
    return {
        "visible_package_components": len(components),
        "checked_attachment_chains": checked,
        "attachment_error_count": len(errors),
        "worst_component_gap_m": round(worst_gap, 6),
        "sample_errors": errors[:20],
        "passed": len(components) >= 7000 and checked == len(components) and not errors,
    }


def signage_clearance_audit():
    """Measure the enlarged primary letters against their physical fascias."""
    bpy.context.view_layer.update()
    specs = {
        PREFIX
        + "cvs_primary_sign": ((CVS_X - 13.15, CVS_X + 13.15), (4.20, 7.25), 0.90),
        PREFIX
        + "well_primary_sign": ((WELL_X - 13.30, WELL_X + 13.30), (4.16, 5.30), 0.93),
        PREFIX
        + "well_pharmacy_word": ((WELL_X - 13.30, WELL_X + 13.30), (4.16, 5.30), 0.58),
    }
    measured = {}
    errors = []
    for name, (xr, zr, min_h) in specs.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            errors.append({"object": name, "reason": "missing_primary_sign"})
            continue
        lo, hi = _world_aabb(obj)
        height = hi[2] - lo[2]
        inside = lo[0] >= xr[0] and hi[0] <= xr[1] and lo[2] >= zr[0] and hi[2] <= zr[1]
        measured[name] = {
            "x": [round(lo[0], 3), round(hi[0], 3)],
            "z": [round(lo[2], 3), round(hi[2], 3)],
            "letter_height_m": round(height, 3),
            "inside_fascia": inside,
        }
        if not inside or height < min_h:
            errors.append(
                {
                    "object": name,
                    "reason": "outside_fascia_or_too_small",
                    "height_m": round(height, 3),
                }
            )
    return {
        "measured": measured,
        "error_count": len(errors),
        "sample_errors": errors,
        "passed": not errors,
    }


def entrance_clearance_audit():
    """Verify that no classical portico column intersects the CVS doorway path."""
    bpy.context.view_layer.update()
    clear_left = CVS_ENTRY_X - 2.10
    clear_right = CVS_ENTRY_X + 2.10
    shafts = [
        o
        for o in bpy.data.objects
        if "cvs_portico_column_" in o.name and o.name.endswith(":shaft")
    ]
    obstructions = []
    clearances = []
    for obj in shafts:
        lo, hi = _world_aabb(obj)
        intersects_x = lo[0] < clear_right and hi[0] > clear_left
        intersects_route = lo[1] < 3.0 and hi[1] > 0.45 and hi[2] > 0.15
        if intersects_x and intersects_route:
            obstructions.append(obj.name)
        clearances.append(max(clear_left - hi[0], lo[0] - clear_right, 0.0))
    removed_name = PREFIX + "cvs_portico_column_3:shaft"
    return {
        "doorway_center_x": round(CVS_ENTRY_X, 3),
        "verified_clear_width_m": round(clear_right - clear_left, 3),
        "remaining_portico_column_count": len(shafts),
        "removed_obstructing_column_absent": bpy.data.objects.get(removed_name) is None,
        "obstruction_count": len(obstructions),
        "obstructions": obstructions,
        "nearest_column_edge_clearance_m": round(min(clearances, default=0.0), 3),
        "passed": len(shafts) == 5
        and bpy.data.objects.get(removed_name) is None
        and not obstructions,
    }


def floor_finish_audit():
    """Inspect the combined tile meshes and their physically exposed grout beds."""
    floors = [o for o in bpy.data.objects if o.get("c2w_semantic") == "floor_finish"]
    measured = []
    total_tiles = 0
    errors = []
    for obj in floors:
        tile_count = int(obj.get("c2w_floor_tile_count", 0))
        grout = float(obj.get("c2w_floor_grout_width_m", 0.0))
        polygons = len(obj.data.polygons) if obj.type == "MESH" else 0
        material_variants = len(obj.data.materials) if obj.type == "MESH" else 0
        expected_polygons = tile_count * 6
        if (
            tile_count < 1200
            or not (0.004 <= grout <= 0.009)
            or polygons != expected_polygons
            or material_variants < 3
        ):
            errors.append(obj.name)
        measured.append(
            {
                "object": obj.name,
                "separate_tile_slabs": tile_count,
                "closed_mesh_polygons": polygons,
                "material_variants": material_variants,
                "physical_grout_width_m": round(grout, 4),
            }
        )
        total_tiles += tile_count
    grout_beds = [
        o
        for o in bpy.data.objects
        if o.name.endswith(":grout_bed") and o.get("c2w_floor_system")
    ]
    return {
        "floor_system_count": len(floors),
        "recessed_grout_bed_count": len(grout_beds),
        "total_separate_tile_slabs": total_tiles,
        "measured": measured,
        "errors": errors,
        "passed": len(floors) == 2
        and len(grout_beds) == 2
        and total_tiles >= 2800
        and not errors,
    }


def storefront_continuity_audit():
    """Check exact module-span continuity across both ground-floor storefronts."""
    expected = {
        "cvs_ground_storefront": (
            6,
            CVS_X - 12.60,
            CVS_X + 12.60,
            PREFIX + "cvs_storefront_continuous_head_rail",
        ),
        "well_ground_storefront": (
            5,
            WELL_X - 12.26,
            WELL_X + 12.26,
            PREFIX + "well_storefront_continuous_head_rail",
        ),
    }
    measured = {}
    errors = []
    for run, (
        expected_count,
        expected_left,
        expected_right,
        head_name,
    ) in expected.items():
        members = []
        for obj in bpy.data.objects:
            if obj.get("c2w_storefront_run") != run:
                continue
            span = tuple(float(v) for v in obj.get("c2w_storefront_span", ()))
            if len(span) == 2:
                members.append((span[0], span[1], obj.name))
        members.sort()
        gaps = []
        for left_member, right_member in zip(members, members[1:]):
            gaps.append(right_member[0] - left_member[1])
        max_gap = max([max(0.0, g) for g in gaps], default=0.0)
        run_left = members[0][0] if members else 0.0
        run_right = members[-1][1] if members else 0.0
        head_exists = bpy.data.objects.get(head_name) is not None
        passed = (
            len(members) == expected_count
            and max_gap <= 0.001
            and abs(run_left - expected_left) <= 0.002
            and abs(run_right - expected_right) <= 0.002
            and head_exists
        )
        if not passed:
            errors.append(run)
        measured[run] = {
            "module_count": len(members),
            "run_extent_x": [round(run_left, 3), round(run_right, 3)],
            "junction_gaps_m": [round(g, 6) for g in gaps],
            "maximum_positive_gap_m": round(max_gap, 6),
            "continuous_head_rail": head_exists,
            "passed": passed,
        }
    return {"runs": measured, "errors": errors, "passed": not errors}


def public_realm_cleanup_audit():
    """Prove that the public forecourt has neither vegetation nor parking bays."""
    collections = [
        c for c in bpy.data.collections if c.name.endswith("PHARMACY_ROW_PUBLIC_REALM")
    ]
    objects = [o for c in collections for o in c.objects]
    lower_names = {o.name: o.name.lower() for o in objects}
    vegetation_tokens = (
        "planter",
        "shrub",
        "planting",
        "vegetation",
        "flowerbed",
        "pot_",
        "soil",
        "tree_",
    )
    parking_tokens = (
        "parking",
        "wheel_stop",
        "accessible_bay",
        "accessible_symbol",
        "car_bay",
    )
    vegetation = [
        name
        for name, lower in lower_names.items()
        if any(t in lower for t in vegetation_tokens)
    ]
    parking = [
        name
        for name, lower in lower_names.items()
        if any(t in lower for t in parking_tokens)
    ]
    forecourt = [o for o in objects if o.name.endswith("pedestrian_forecourt")]
    paver_joints = [o for o in objects if "forecourt_paver_joint_" in o.name]
    no_vegetation = not vegetation
    no_parking = not parking
    return {
        "public_realm_collection_count": len(collections),
        "pedestrian_forecourt_count": len(forecourt),
        "modeled_forecourt_joint_count": len(paver_joints),
        "front_vegetation_objects": vegetation,
        "parking_geometry_objects": parking,
        "front_vegetation_removed": no_vegetation,
        "front_parking_removed": no_parking,
        "passed": len(collections) == 1
        and len(forecourt) == 1
        and len(paver_joints) >= 120
        and no_vegetation
        and no_parking,
    }


def counter_kiosk_detail_audit():
    """Require operational subassemblies, not merely a high raw object count."""
    names = [o.name for o in bpy.data.objects]
    counter_names = [n for n in names if "well_clinical_counter" in n]
    kiosk_names = [n for n in names if "well_prescription_pickup_kiosk" in n]
    counter_features = (
        "dispensing_scale_pan",
        "counting_tray_well",
        "guard_glass",
        "label_roll",
        "phone_handset",
        "power_data_raceway",
        "drawer_lock",
        "rx_handover_bin",
    )
    kiosk_features = (
        "screen_glass",
        "camera_lens",
        "receipt_paper",
        "barcode_glass",
        "payment_terminal_mount",
        "payment_key_",
        "pickup_hatch_door",
        "side_vent_slot",
        "security_screw",
        "armoured_power_conduit",
        "floor_anchor",
    )
    counter_presence = {
        feature: any(feature in n for n in counter_names)
        for feature in counter_features
    }
    kiosk_presence = {
        feature: any(feature in n for n in kiosk_names) for feature in kiosk_features
    }
    return {
        "well_counter_modeled_part_count": len(counter_names),
        "pickup_terminal_modeled_part_count": len(kiosk_names),
        "counter_operational_features": counter_presence,
        "pickup_terminal_operational_features": kiosk_presence,
        "passed": len(counter_names) >= 200
        and len(kiosk_names) >= 100
        and all(counter_presence.values())
        and all(kiosk_presence.values()),
    }


def validate(root, cameras, rendered=False):
    counts = object_counts()
    support_audit = inventory_support_audit()
    attachment_audit = package_attachment_audit()
    sign_audit = signage_clearance_audit()
    entrance_audit = entrance_clearance_audit()
    floor_audit = floor_finish_audit()
    storefront_audit = storefront_continuity_audit()
    realm_audit = public_realm_cleanup_audit()
    fixture_audit = counter_kiosk_detail_audit()
    revision_requirements = {
        "01_white_building_entrance_column_removed": entrance_audit["passed"],
        "02_counter_and_pickup_terminal_refined": fixture_audit["passed"],
        "03_modeled_interior_tile_floors": floor_audit["passed"],
        "04_continuous_storefront_glazing": storefront_audit["passed"],
        "05_front_vegetation_and_planters_removed": realm_audit[
            "front_vegetation_removed"
        ],
        "06_front_parking_bays_removed": realm_audit["front_parking_removed"],
    }
    names = [o.name for o in bpy.data.objects]
    stores = [c for c in root.children if "PHARMACY_0" in c.name]
    interiors = [c for c in bpy.data.collections if c.name.endswith("INTERIOR")]
    reference_sizes = {
        f: (REFERENCES / f).stat().st_size if (REFERENCES / f).is_file() else 0
        for f in REFERENCE_FILES
    }
    forbidden = [
        n
        for n in names
        if any(word in n.lower() for word in ("toy", "placeholder", "dummy", "lowpoly"))
    ]
    render_sizes = {
        fn: (RENDERS / fn).stat().st_size if (RENDERS / fn).is_file() else 0
        for fn, _, _, _, _ in camera_specs()
    }
    checks = {
        "two_reference_specific_exteriors": len(stores) == 2
        and all(c.get("c2w_archetype") for c in stores),
        "two_independent_modeled_interiors": len(interiors) == 2,
        "dense_varied_inventory_geometry": counts.get("product", 0) >= 2500
        and counts.get("product_label", 0) >= 2500
        and counts.get("product_detail", 0) >= 2500,
        "all_inventory_physically_supported": support_audit["passed"],
        "all_package_components_physically_connected": attachment_audit["passed"],
        "multipart_profiled_medicine_packaging": sum(
            "bottle_profile" in n for n in names
        )
        >= 650
        and sum("tapered_tube" in n for n in names) >= 250
        and sum("folded_carton" in n for n in names) >= 1200,
        "commercial_shelving_and_fixtures": counts.get("shelf_deck", 0) >= 110
        and counts.get("fixture", 0) >= 220,
        "complex_counter_and_cabinet_joinery": fixture_audit["passed"]
        and sum("cabinet_front" in n for n in names) >= 18
        and sum("shelf_bracket" in n or ":bracket_" in n for n in names) >= 120,
        "detailed_prescription_pickup_kiosk": fixture_audit["passed"],
        "unobstructed_white_building_main_entrance": entrance_audit["passed"],
        "modeled_porcelain_tiles_and_physical_grout": floor_audit["passed"],
        "continuous_ground_floor_storefront_runs": storefront_audit["passed"],
        "pedestrian_forecourt_without_vegetation_or_parking": realm_audit["passed"],
        "architectural_detail_not_box_shell_only": counts.get("architectural_detail", 0)
        >= 330,
        "enlarged_primary_signs_inside_fascias": sign_audit["passed"],
        "transparent_storefront_and_real_doors": counts.get("glazing", 0) >= 16,
        "modeled_lighting_system": counts.get("lighting", 0) >= 12
        and counts.get("lighting_fixture", 0) >= 20,
        "reference_images_archived_in_workspace": min(
            reference_sizes.values(), default=0
        )
        > 10000,
        "daylight_near_far_and_interior_views": len(cameras) == 11
        and {role for _, _, _, _, role in camera_specs()}
        >= {
            "far",
            "near",
            "interior",
            "interior_close",
            "inventory_close",
            "fixture_close",
        },
        "no_placeholder_or_toy_named_assets": not forbidden,
        "production_generator_metadata": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_pharmacy.build_pharmacy_reference_row",
        "all_six_requested_revisions_verified": all(revision_requirements.values()),
    }
    if rendered:
        checks["all_render_artifacts_nonempty"] = (
            min(render_sizes.values(), default=0) > 15000
        )
    data = {
        "schema": "agent.urban_asset_manifest.v2",
        "generator": str(Path(__file__).resolve()),
        "runner": str((ROOT / "scripts/run_urban_v3_pharmacy.sh").resolve()),
        "output": str(OUT),
        "blend": str(BLEND),
        "pipeline_asset_id": ASSET_ID,
        "pipeline_connected": True,
        "pipeline_entrypoint": "generate_urban_v3_pharmacy.build_pharmacy_reference_row",
        "pipeline_adapter": "urban_assets.build_pharmacy_reference_row",
        "rebuild_command": "bash scripts/run_urban_v3_pharmacy.sh",
        "reference_urls": REFERENCE_URLS,
        "reference_files": reference_sizes,
        "reference_observations": {
            "exterior_01": "white classical portico, layered dentil cornice, square columns, red brick wings, CVS/pharmacy and 24 HOURS signage",
            "exterior_02": "deep navy high-street fascia, luminous abstract cross, well Pharmacy wordmark, full-height glazing, dark upper masonry",
            "interior_01": "bright clinical counter, dense wall stock, pale terrazzo, sculptural dark ceiling with cyan light ribbons",
            "interior_02": "white high-density pharmacy wall shelving, varied cartons and bottles, central gondola",
        },
        "pharmacy_types": [
            "cvs_classical_portico_red_brick",
            "well_urban_high_street_illuminated",
        ],
        "pharmacy_count": len(stores),
        "interior_count": len(interiors),
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "semantic_counts": counts,
        "physical_support_audit": support_audit,
        "package_attachment_audit": attachment_audit,
        "signage_clearance_audit": sign_audit,
        "entrance_clearance_audit": entrance_audit,
        "floor_finish_audit": floor_audit,
        "storefront_continuity_audit": storefront_audit,
        "public_realm_cleanup_audit": realm_audit,
        "counter_kiosk_detail_audit": fixture_audit,
        "revision_requirements": revision_requirements,
        "render_views": [
            {"file": fn, "role": role, "bytes": render_sizes[fn]}
            for fn, _, _, _, role in camera_specs()
        ],
        "render_settings": {
            "engine": "BLENDER_EEVEE_NEXT",
            "resolution": [1600, 1000],
            "samples": 16,
            "color_management": "AgX - Medium High Contrast",
        },
        "daylight": True,
        "near_and_far_views": True,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not data["all_checks_passed"]:
        failed = [k for k, v in checks.items() if not v]
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(
                {
                    "failed": failed,
                    "revision_requirements": revision_requirements,
                    "entrance_clearance_audit": entrance_audit,
                    "floor_finish_audit": floor_audit,
                    "storefront_continuity_audit": storefront_audit,
                    "public_realm_cleanup_audit": realm_audit,
                    "counter_kiosk_detail_audit": fixture_audit,
                    "signage_clearance_audit": sign_audit,
                    "physical_support_audit": support_audit,
                    "package_attachment_audit": attachment_audit,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf8",
        )
        raise RuntimeError("Pharmacy5 production audit failed: " + ", ".join(failed))
    return data


def render_all(cameras):
    scene = bpy.context.scene
    selected = {
        x.strip()
        for x in os.environ.get("C2W_PHARMACY_VIEW_FILTER", "").split(",")
        if x.strip()
    }
    for filename, cam, role in cameras:
        if selected and not any(filename.startswith(prefix) for prefix in selected):
            continue
        print(f"[pharmacy5] rendering {role}: {filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def main():
    print("[pharmacy5] starting production generator", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    REFERENCES.mkdir(parents=True, exist_ok=True)
    archive_references()
    # The runner must never accept a stale success marker if Blender exits after
    # a Python exception (Blender itself can still return status 0 in that case).
    for stale in (
        OUT / "SUCCESS",
        OUT / "manifest.json",
        OUT / "quality_report.json",
        OUT / "build_audit.json",
        OUT / "FAILED_AUDIT.json",
    ):
        stale.unlink(missing_ok=True)
    preview = os.environ.get("C2W_PHARMACY_PREVIEW", "0") == "1"
    build_only = os.environ.get("C2W_PHARMACY_BUILD_ONLY", "0") == "1"
    partial_render = bool(os.environ.get("C2W_PHARMACY_VIEW_FILTER", "").strip())
    G.reset_scene()
    SHARED_MESHES.clear()
    print("[pharmacy5] building both procedural pharmacy archetypes", flush=True)
    root, _M = build_pharmacy_reference_row()
    print("[pharmacy5] configuring physical daylight and cameras", flush=True)
    setup_world()
    configure_scene(preview)
    cameras = []
    for filename, loc, target, lens, role in camera_specs():
        cam = camera(filename[:-4], loc, target, lens)
        cameras.append((filename, cam, role))
    initial = validate(root, cameras, rendered=False)
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_runner"] = str(
        (ROOT / "scripts/run_urban_v3_pharmacy.sh").resolve()
    )
    scene["c2w_asset_id"] = ASSET_ID
    scene["c2w_domain"] = "urban_pharmacy"
    scene["c2w_reference_driven"] = True
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_pharmacy.build_pharmacy_reference_row"
    scene["c2w_quality_profile"] = "reference_grade_procedural_physical_support"
    scene["c2w_manifest"] = json.dumps(initial, ensure_ascii=False)
    (OUT / "build_audit.json").write_text(
        json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8"
    )
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    if build_only:
        print(
            json.dumps(
                {
                    "status": "BUILD_ONLY_COMPLETE",
                    "output": str(OUT),
                    "objects": initial["object_count"],
                    "support": initial["physical_support_audit"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return
    render_all(cameras)
    if preview or partial_render:
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
        print(
            json.dumps(
                {"status": "PREVIEW_COMPLETE", "output": str(OUT)}, ensure_ascii=False
            ),
            flush=True,
        )
        return
    final = validate(root, cameras, rendered=True)
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
        "physical_support_audit": final["physical_support_audit"],
        "package_attachment_audit": final["package_attachment_audit"],
        "signage_clearance_audit": final["signage_clearance_audit"],
        "entrance_clearance_audit": final["entrance_clearance_audit"],
        "floor_finish_audit": final["floor_finish_audit"],
        "storefront_continuity_audit": final["storefront_continuity_audit"],
        "public_realm_cleanup_audit": final["public_realm_cleanup_audit"],
        "counter_kiosk_detail_audit": final["counter_kiosk_detail_audit"],
        "revision_requirements": final["revision_requirements"],
        "reference_observations": final["reference_observations"],
        "note": "Validation uses named construction layers and modeled inventory/fixture counts; object count alone is not accepted as a quality check.",
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf8"
    )
    (OUT / "SUCCESS").write_text(
        f"{ASSET_ID} production generation and validation complete\n", encoding="utf8"
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
