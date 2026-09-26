"""Production procedural ATM family used directly by the urban pipeline.

This is the source generator, not a post-process for a hand-authored ``.blend``.
It exposes :func:`build_atm` for scene assembly and, when executed by Blender,
builds all five structurally distinct machines visible in the four references,
saves an editable asset library, performs a geometry/semantics audit, and makes
daylight near and wide validation renders in ``urban_v3_atm4``.

Coordinate convention for generated assets: +Z is up and the customer stands
on the -Y side. Every variant is built around a local origin at floor level so
that a collection can be instanced by the existing WorldBridge urban pipeline.
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
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_atm4"
RENDERS = OUT / "renders"
PREFIX = "urban_v3_atm4:"
GENERATOR_VERSION = 4

REFERENCES = [
    "https://preview.free3d.com/img/2017/12/2188221942400550492/rokdrbnf.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTLrBlf7Oog74nj15UmmYjEUNTgIEceypHsYJwWaFt1SgxZxm3z1sSAuKg&s=10",
    "https://imagedelivery.net/S4svCqSolndHzMne84t1OQ/A23DMOD050003A_Preview/public",
    "https://media.cgtrader.com/variants/X7Jhy45BMN8J2QbXEXj6jFLP/78add9c2f02fbd73a43ffb3970be38683c5f15eff6ca849dc78c644f4ff9ce1b/Cover01.webp",
]

VARIANT_NAMES = (
    "silver_freestanding_2in1",
    "silver_through_wall_2in1",
    "white_oxford_through_wall",
    "bronze_deep_recess",
    "bank_branded_narrow",
)

COLLECTION_NAMES = (
    "ATM_01A_SILVER_FREESTANDING",
    "ATM_01B_SILVER_THROUGH_WALL",
    "ATM_02_WHITE_OXFORD_WALL",
    "ATM_03_BRONZE_DEEP_RECESS",
    "ATM_04_BANK_BRANDED_NARROW",
)

sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all45 as G

G.PREFIX = PREFIX


# -----------------------------------------------------------------------------
# Core procedural geometry and material helpers
# -----------------------------------------------------------------------------


def collection(name, parent=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def _set_input(node, key, value):
    if key in node.inputs:
        node.inputs[key].default_value = value


def material(name, color, rough=0.48, metal=0.0, noise=0.018, coat=0.06):
    """Physically scaled painted/metal material.

    The previous ATM pass inherited a city-scale noise shader whose bump was
    centimetres deep.  On a machine fascia that reads like cloudy plastic.  ATM
    finishes instead need sub-millimetre orange peel and subtle albedo drift.
    """
    mat = G.clear_material(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    _set_input(bsdf, "Roughness", rough)
    _set_input(bsdf, "Metallic", metal)
    _set_input(bsdf, "Coat Weight", coat)
    _set_input(bsdf, "Coat Roughness", min(0.45, rough * 0.72))
    if metal > 0.25:
        _set_input(bsdf, "Anisotropic IOR Level", min(0.55, metal * 0.42))
    if noise:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 245.0
        tex.inputs["Detail"].default_value = 3.2
        tex.inputs["Roughness"].default_value = 0.56
        ramp = nodes.new("ShaderNodeValToRGB")
        spread = min(0.055, noise * 0.75)
        ramp.color_ramp.elements[0].color = (
            *[max(0.0, c * (1.0 - spread)) for c in color],
            1,
        )
        ramp.color_ramp.elements[1].color = (
            *[min(1.0, c * (1.0 + spread) + 0.003) for c in color],
            1,
        )
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = min(0.16, noise * 3.0)
        bump.inputs["Distance"].default_value = 0.00032
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*color, 1)
    return mat


def emissive_material(name, color, strength=2.0, rough=0.22):
    mat = G.material(name, color, rough, 0.0, 0.0)
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*color, 1)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def brushed_metal(name, dark=(0.31, 0.33, 0.34), light=(0.48, 0.50, 0.51), rough=0.29):
    mat = G.clear_material(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    mapping = nodes.new("ShaderNodeMapping")
    tex = nodes.new("ShaderNodeTexCoord")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    mapping.inputs["Scale"].default_value = (2.5, 360.0, 3.0)
    noise.inputs["Scale"].default_value = 2.2
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.48
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    bsdf.inputs["Metallic"].default_value = 0.84
    bsdf.inputs["Roughness"].default_value = rough
    _set_input(bsdf, "Anisotropic IOR Level", 0.38)
    _set_input(bsdf, "Coat Weight", 0.035)
    bump.inputs["Strength"].default_value = 0.075
    bump.inputs["Distance"].default_value = 0.00024
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*light, 1)
    return mat


def glass_material(name, tint=(0.012, 0.020, 0.028), rough=0.075, transmission=0.16):
    mat = G.clear_material(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*tint, 1)
    _set_input(bsdf, "Roughness", rough)
    _set_input(bsdf, "Metallic", 0.02)
    _set_input(bsdf, "Transmission Weight", transmission)
    _set_input(bsdf, "IOR", 1.48)
    _set_input(bsdf, "Coat Weight", 0.42)
    _set_input(bsdf, "Coat Roughness", 0.045)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*tint, 1)
    return mat


def rubber_material(name, color=(0.008, 0.010, 0.012), rough=0.60):
    mat = material(name, color, rough, 0.0, 0.006, coat=0.015)
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        _set_input(bsdf, "Specular IOR Level", 0.27)
    return mat


def decal_material(name, color, rough=0.52):
    return material(name, color, rough, 0.0, 0.002, coat=0.02)


def concrete_material(name, base=(0.30, 0.32, 0.33)):
    mat = G.clear_material(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    coarse = nodes.new("ShaderNodeTexNoise")
    fine = nodes.new("ShaderNodeTexNoise")
    mix = nodes.new("ShaderNodeMixRGB")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    coarse.inputs["Scale"].default_value = 8.0
    coarse.inputs["Detail"].default_value = 6.0
    coarse.inputs["Roughness"].default_value = 0.72
    fine.inputs["Scale"].default_value = 175.0
    fine.inputs["Detail"].default_value = 2.0
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.26
    ramp.color_ramp.elements[0].color = (*[c * 0.72 for c in base], 1)
    ramp.color_ramp.elements[1].color = (*[c * 1.12 for c in base], 1)
    _set_input(bsdf, "Roughness", 0.78)
    _set_input(bsdf, "Coat Weight", 0.01)
    bump.inputs["Strength"].default_value = 0.19
    bump.inputs["Distance"].default_value = 0.0022
    links.new(coarse.outputs["Fac"], mix.inputs[1])
    links.new(fine.outputs["Fac"], mix.inputs[2])
    links.new(mix.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def tag(obj, role, detail=""):
    obj["c2w_role"] = role
    obj["c2w_detail"] = detail or role
    obj["c2w_generator"] = str(Path(__file__).resolve())
    obj["c2w_generator_version"] = GENERATOR_VERSION
    return obj


def cuboid(
    c, name, loc, dims, mat, bevel=0.008, rot=(0.0, 0.0, 0.0), role="detail", detail=""
):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dims
    if mat:
        obj.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        G.add_bevel(obj, min(bevel, min(dims) * 0.42), 5 if bevel >= 0.008 else 3)
    G.link_to(obj, c)
    return tag(obj, role, detail)


def cylinder(
    c,
    name,
    loc,
    radius,
    depth,
    mat,
    rot=(0.0, 0.0, 0.0),
    vertices=48,
    bevel=0.003,
    role="detail",
    detail="",
):
    obj = G.cylinder(
        name, loc, radius, depth, mat, c, vertices=vertices, rot=rot, bevel=bevel
    )
    return tag(obj, role, detail)


def sphere(c, name, loc, radius, mat, scale=(1, 1, 1), role="detail", detail=""):
    obj = G.sphere(name, loc, radius, mat, c, scale=scale, segments=32)
    return tag(obj, role, detail)


def prism_yz(
    c, name, x0, x1, profile, mat, bevel=0.008, role="custom_profile", detail=""
):
    """Extrude a closed Y/Z profile between x0 and x1."""
    verts = [(x0, y, z) for y, z in profile] + [(x1, y, z) for y, z in profile]
    n = len(profile)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    if bevel > 0:
        G.add_bevel(obj, bevel, 3)
    obj["c2w_geometry"] = "custom_yz_profile"
    return tag(obj, role, detail or "custom formed sheet-metal profile")


def prism_xz(
    c, name, y0, y1, profile, mat, bevel=0.008, role="custom_profile", detail=""
):
    """Extrude a closed X/Z profile between y0 and y1."""
    verts = [(x, y0, z) for x, z in profile] + [(x, y1, z) for x, z in profile]
    n = len(profile)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    if bevel > 0:
        G.add_bevel(obj, bevel, 3)
    obj["c2w_geometry"] = "custom_xz_profile"
    return tag(obj, role, detail or "custom formed sheet-metal profile")


def tube(c, name, points, radius, mat, role="hardware", detail=""):
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = radius
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.data.materials.append(mat)
    return tag(obj, role, detail or "formed metal tube")


def torus(
    c,
    name,
    loc,
    major_radius,
    minor_radius,
    mat,
    rot=(math.pi / 2, 0.0, 0.0),
    role="detail",
    detail="",
):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=64,
        minor_segments=12,
        location=loc,
        rotation=rot,
    )
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    G.link_to(obj, c)
    return tag(obj, role, detail or role)


def mesh_object(
    c,
    name,
    verts,
    faces,
    mat,
    bevel=0.0,
    role="custom_profile",
    detail="procedural non-primitive mesh",
):
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    if bevel:
        G.add_bevel(obj, bevel, 3)
    obj["c2w_geometry"] = "bespoke_procedural_mesh"
    return tag(obj, role, detail)


def diamond_vent_field(c, name, x, y0, z0, width, height, M, side=-1, rows=17, cols=4):
    """Reference-1 punched diamond ventilation field on a side skin."""
    for row in range(rows):
        for col in range(cols):
            yy = y0 - width / 2 + (col + 0.5 + 0.5 * (row % 2)) * width / cols
            if yy > y0 + width / 2 - 0.015:
                continue
            zz = z0 - height / 2 + (row + 0.5) * height / rows
            cuboid(
                c,
                f"{name}:diamond:{row}:{col}",
                (x, yy, zz),
                (0.007, 0.045, 0.019),
                M["void"],
                0.002,
                rot=(math.radians(43), 0, 0),
                role="ventilation",
                detail="punched diamond cooling perforation",
            )
    # The cabinet side itself remains visible between the punched openings;
    # each black diamond supplies its own depth cue.  A full dark backing sheet
    # would incorrectly read as a single plastic rectangle from oblique views.


def micro_perforation_patch(
    c, name, origin, u_axis, v_axis, cols, rows, pitch_u, pitch_v, radius, mat
):
    """One efficient mesh containing hundreds of small worktop dimples."""
    o, u, v = Vector(origin), Vector(u_axis).normalized(), Vector(v_axis).normalized()
    verts, faces = [], []
    for row in range(rows):
        for col in range(cols):
            center = (
                o
                + (col - (cols - 1) / 2) * pitch_u * u
                + (row - (rows - 1) / 2) * pitch_v * v
            )
            idx = len(verts)
            verts.extend(
                (
                    center + u * radius,
                    center + v * radius,
                    center - u * radius,
                    center - v * radius,
                )
            )
            faces.append((idx, idx + 1, idx + 2, idx + 3))
    return mesh_object(
        c,
        name,
        verts,
        faces,
        mat,
        0.0,
        "surface_detail",
        "dense anti-slip punched stainless worktop texture",
    )


def leveling_foot(c, name, x, y, M, z=0.018, radius=0.042):
    cylinder(
        c,
        name + ":pad",
        (x, y, z),
        radius,
        z * 2,
        M["rubber"],
        vertices=48,
        bevel=0.003,
        role="ground_contact",
        detail="load-bearing elastomer levelling foot on floor plane",
    )
    cylinder(
        c,
        name + ":stud",
        (x, y, z + 0.034),
        radius * 0.30,
        0.055,
        M["screw"],
        vertices=24,
        bevel=0.0015,
        role="floor_anchor",
        detail="threaded cabinet levelling stud",
    )


def hinge(c, name, x, y, z, height, M):
    cylinder(
        c,
        name + ":pin",
        (x, y, z),
        0.013,
        height,
        M["chrome"],
        vertices=36,
        bevel=0.002,
        role="service_hinge",
        detail="stainless piano-hinge barrel",
    )
    for dz in (-height * 0.30, height * 0.30):
        cuboid(
            c,
            f"{name}:leaf:{dz:+.3f}",
            (x + 0.025, y + 0.006, z + dz),
            (0.065, 0.010, height * 0.24),
            M["body_silver"],
            0.002,
            role="service_hinge",
            detail="folded service-door hinge leaf",
        )


def security_camera(c, name, x, y, z, M, radius=0.026):
    cylinder(
        c,
        name + ":cup",
        (x, y, z),
        radius * 1.55,
        0.025,
        M["black"],
        rot=(math.pi / 2, 0, 0),
        vertices=48,
        bevel=0.003,
        role="security_camera",
        detail="recessed anti-tamper camera cup",
    )
    torus(
        c,
        name + ":lens_ring",
        (x, y - 0.016, z),
        radius,
        radius * 0.16,
        M["chrome"],
        role="security_camera",
        detail="machined camera-lens retaining ring",
    )
    sphere(
        c,
        name + ":lens",
        (x, y - 0.022, z),
        radius * 0.78,
        M["camera_glass"],
        scale=(1, 0.25, 1),
        role="security_camera",
        detail="convex tinted camera optic",
    )


def barcode_label(c, name, x, y, z, w, h, M, heading="EQUIPMENT ID"):
    front_panel(
        c,
        name + ":decal",
        x,
        y,
        z,
        w,
        h,
        M["vinyl"],
        0.002,
        role="serial_label",
        detail="thin laminated equipment and serial-number decal",
    )
    text_front(
        c,
        name + ":heading",
        heading,
        (x, y - 0.012, z + h * 0.31),
        h * 0.17,
        M["ink"],
        0.00015,
        role="serial_label",
    )
    widths = (1, 2, 1, 1, 3, 1, 2, 1, 3, 1, 1, 2, 1, 2, 1)
    cursor = x - w * 0.38
    unit = w * 0.011
    for i, units in enumerate(widths):
        bw = unit * units
        cuboid(
            c,
            f"{name}:barcode:{i}",
            (cursor + bw / 2, y - 0.012, z - h * 0.08),
            (bw, 0.0015, h * 0.33),
            M["ink"],
            0.0002,
            role="serial_label",
            detail="printed asset barcode",
        )
        cursor += bw + unit
    text_front(
        c,
        name + ":serial",
        "ATM 04 2817",
        (x, y - 0.012, z - h * 0.34),
        h * 0.11,
        M["ink"],
        0.0001,
        role="serial_label",
    )


def floor_mount_set(c, name, x_span, y_span, M, foot_radius=0.035):
    """Four explicit, coplanar load paths plus front floor anchor caps."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            leveling_foot(
                c,
                f"{name}:foot:{sx}:{sy}",
                sx * x_span,
                sy * y_span,
                M,
                z=0.010,
                radius=foot_radius,
            )
    for sx in (-1, 1):
        cylinder(
            c,
            f"{name}:anchor_cap:{sx}",
            (sx * x_span * 0.78, -y_span - 0.018, 0.009),
            0.014,
            0.018,
            M["screw"],
            vertices=6,
            bevel=0.0015,
            role="floor_anchor",
            detail="visible hexagonal anti-tip floor anchor cap",
        )


def warning_label(c, name, x, y, z, w, h, M, body="CAUTION"):
    cuboid(
        c,
        name + ":yellow",
        (x, y, z),
        (w, 0.002, h),
        M["warning_yellow"],
        0.0015,
        role="safety_label",
        detail="laminated electrical/service warning label",
    )
    text_front(
        c,
        name + ":text",
        body,
        (x, y - 0.003, z + h * 0.22),
        h * 0.20,
        M["ink"],
        0.00008,
        role="safety_label",
    )
    for i in range(3):
        cuboid(
            c,
            f"{name}:fineprint:{i}",
            (x, y - 0.003, z - h * (0.02 + i * 0.16)),
            (w * 0.70, 0.001, h * 0.035),
            M["ink"],
            0.0002,
            role="safety_label",
            detail="service warning fine print",
        )


def headphone_jack(c, name, x, y, z, M):
    torus(
        c,
        name + ":ring",
        (x, y, z),
        0.017,
        0.0035,
        M["brushed_trim"],
        role="accessibility_control",
        detail="accessible audio-jack trim ring",
    )
    cylinder(
        c,
        name + ":socket",
        (x, y - 0.005, z),
        0.009,
        0.014,
        M["void"],
        rot=(math.pi / 2, 0, 0),
        vertices=32,
        bevel=0.001,
        role="accessibility_control",
        detail="3.5 mm speech-assistance socket",
    )
    text_front(
        c,
        name + ":mark",
        "AUDIO",
        (x, y - 0.014, z - 0.031),
        0.010,
        M["key_legend"],
        0.00008,
        role="accessibility_detail",
    )


def text_front(
    c, name, body, loc, size, mat, extrude=0.00035, align="CENTER", role="printed_label"
):
    curve = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = min(0.00018, extrude * 0.25)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(mat)
    return tag(obj, role, "raised/printed front-panel lettering")


def text_top(
    c, name, body, loc, size, mat, rot_x=0.0, extrude=0.00025, role="key_legend"
):
    curve = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (rot_x, 0, 0)
    obj.data.materials.append(mat)
    return tag(obj, role, "tactile control legend")


def front_panel(
    c, name, x, y, z, w, h, mat, bevel=0.008, role="interface_panel", detail=""
):
    return cuboid(
        c, name, (x, y, z), (w, 0.016, h), mat, bevel, role=role, detail=detail
    )


def fastener(c, name, x, y, z, M, radius=0.012):
    cylinder(
        c,
        name + ":head",
        (x, y, z),
        radius,
        0.012,
        M["screw"],
        rot=(math.pi / 2, 0, 0),
        vertices=32,
        bevel=0.001,
        role="fastener",
        detail="countersunk service fastener",
    )
    cuboid(
        c,
        name + ":slot",
        (x, y - 0.008, z),
        (radius * 1.25, 0.005, 0.0025),
        M["void"],
        0.0005,
        role="fastener",
        detail="screwdriver recess",
    )


def seam(c, name, x, y, z, w, M, vertical=False):
    dims = (0.008, 0.008, w) if vertical else (w, 0.008, 0.008)
    return cuboid(
        c,
        name,
        (x, y, z),
        dims,
        M["seam"],
        0.001,
        role="panel_seam",
        detail="serviceable sheet-metal joint",
    )


def status_lamp(c, name, x, y, z, M, color="green", r=0.034):
    cylinder(
        c,
        name + ":bezel",
        (x, y, z),
        r * 1.42,
        0.025,
        M["chrome"],
        rot=(math.pi / 2, 0, 0),
        role="status_indicator",
        detail="machined status-lamp bezel",
    )
    cylinder(
        c,
        name + ":lens",
        (x, y - 0.016, z),
        r,
        0.018,
        M[color],
        rot=(math.pi / 2, 0, 0),
        role="status_light",
        detail="illuminated status lens",
    )


def label_strip(c, name, body, x, y, z, w, M, color="black"):
    front_panel(
        c,
        name + ":plate",
        x,
        y,
        z,
        w,
        0.055,
        M[color],
        0.004,
        role="equipment_label",
        detail="recessed equipment function label",
    )
    text_size = min(0.026, max(0.010, w * 0.86 / (max(1, len(body)) * 0.58)))
    text_front(
        c,
        name + ":text",
        body,
        (x, y - 0.018, z),
        text_size,
        M["white"],
        0.00018,
        role="equipment_label",
    )


def task_light(c, name, x, y, z, w, M):
    front_panel(
        c,
        name + ":housing",
        x,
        y,
        z,
        w + 0.075,
        0.105,
        M["steel_dark"],
        0.014,
        role="task_light_housing",
        detail="recessed fluorescent/LED task-light housing",
    )
    front_panel(
        c,
        name + ":diffuser",
        x,
        y - 0.018,
        z,
        w,
        0.064,
        M["warm_light"],
        0.010,
        role="task_light",
        detail="frosted illuminated task-light diffuser",
    )


def speaker_grille(c, name, x, y, z, cols, rows, spacing, M):
    for row in range(rows):
        for col in range(cols):
            xx = x + (col - (cols - 1) / 2) * spacing
            zz = z + (row - (rows - 1) / 2) * spacing
            cylinder(
                c,
                f"{name}:hole:{row}:{col}",
                (xx, y, zz),
                0.0075,
                0.012,
                M["void"],
                rot=(math.pi / 2, 0, 0),
                vertices=20,
                bevel=0.001,
                role="speaker_grille",
                detail="acoustic perforation",
            )


def ui_screen(c, name, x, y, z, w, h, M, theme="blue", side_keys=True, title="WELCOME"):
    # Multi-part bezel with a thin rubber gasket, recessed LCD and separate
    # cover glass.  These depth cues remain visible from oblique cameras.
    front_panel(
        c,
        name + ":outer_bezel",
        x,
        y,
        z,
        w + 0.092,
        h + 0.088,
        M["black"],
        0.016,
        role="screen_bezel",
        detail="moulded display bezel with radiused corners",
    )
    front_panel(
        c,
        name + ":bezel_step",
        x,
        y - 0.013,
        z,
        w + 0.056,
        h + 0.052,
        M["bezel"],
        0.009,
        role="screen_bezel",
        detail="stepped inner display bezel",
    )
    front_panel(
        c,
        name + ":rubber_gasket",
        x,
        y - 0.023,
        z,
        w + 0.020,
        h + 0.020,
        M["rubber"],
        0.006,
        role="screen_gasket",
        detail="continuous anti-glare LCD glazing gasket",
    )
    display_mat = M["lcd_blue"] if theme == "blue" else M["lcd_black"]
    front_panel(
        c,
        name + ":lcd",
        x,
        y - 0.031,
        z,
        w,
        h,
        display_mat,
        0.004,
        role="display",
        detail="recessed active LCD panel",
    )

    # Restrained, bank-like interface: typographic menu rows and small icons,
    # not luminous toy blocks.  All elements are independent procedural decals.
    front_panel(
        c,
        name + ":header_rule",
        x,
        y - 0.042,
        z + h * 0.36,
        w * 0.90,
        0.006,
        M["ui_blue"],
        0.001,
        role="screen_ui",
        detail="screen header divider",
    )
    text_front(
        c,
        name + ":secure",
        "SECURE BANKING",
        (x - w * 0.30, y - 0.044, z + h * 0.425),
        min(0.016, h * 0.045),
        M["ui_muted"],
        0.00012,
        align="LEFT",
        role="screen_ui",
    )
    text_front(
        c,
        name + ":title",
        title,
        (x, y - 0.044, z + h * 0.295),
        min(0.026, h * 0.067),
        M["ui_white"],
        0.00016,
        role="screen_ui",
    )
    menu = ("CASH WITHDRAWAL", "BALANCE / RECEIPT", "DEPOSIT", "MORE SERVICES")
    for i, label in enumerate(menu):
        zz = z + h * (0.125 - i * 0.145)
        front_panel(
            c,
            f"{name}:menu_rule:{i}",
            x + w * 0.06,
            y - 0.043,
            zz - h * 0.047,
            w * 0.73,
            0.003,
            M["ui_rule"],
            0.0006,
            role="screen_ui",
            detail="fine LCD menu separator",
        )
        front_panel(
            c,
            f"{name}:icon_box:{i}",
            x - w * 0.34,
            y - 0.044,
            zz,
            w * 0.075,
            h * 0.070,
            M["ui_blue" if i != 2 else "screen_green"],
            0.002,
            role="screen_ui",
            detail="small transaction pictogram tile",
        )
        text_front(
            c,
            f"{name}:menu_text:{i}",
            label,
            (x - w * 0.245, y - 0.045, zz),
            min(0.0145, h * 0.041),
            M["ui_text"],
            0.00010,
            align="LEFT",
            role="screen_ui",
        )
        text_front(
            c,
            f"{name}:menu_arrow:{i}",
            ">",
            (x + w * 0.39, y - 0.045, zz),
            min(0.017, h * 0.047),
            M["ui_muted"],
            0.00010,
            role="screen_ui",
        )
    text_front(
        c,
        name + ":footer_left",
        "ENGLISH",
        (x - w * 0.40, y - 0.044, z - h * 0.425),
        min(0.011, h * 0.032),
        M["ui_muted"],
        0.00010,
        align="LEFT",
        role="screen_ui",
    )
    text_front(
        c,
        name + ":footer_right",
        "12:08",
        (x + w * 0.40, y - 0.044, z - h * 0.425),
        min(0.011, h * 0.032),
        M["ui_muted"],
        0.00010,
        align="RIGHT",
        role="screen_ui",
    )
    prism_xz(
        c,
        name + ":subtle_glass_reflection",
        y - 0.047,
        y - 0.046,
        [
            (x - w * 0.45, z + h * 0.45),
            (x - w * 0.40, z + h * 0.45),
            (x - w * 0.20, z - h * 0.45),
            (x - w * 0.25, z - h * 0.45),
        ],
        M["screen_reflection"],
        0.0004,
        role="display_glass",
        detail="subtle diagonal reflection in anti-glare cover glass",
    )
    # Eevee transmission is intentionally not placed over the UI as a full
    # opaque sheet.  Four bonded glass edges and the reflection layer preserve
    # the glazing read without hiding fine screen typography in daylight.
    for suffix, loc, dims in (
        ("top", (x, y - 0.049, z + h / 2 + 0.003), (w + 0.010, 0.0025, 0.005)),
        ("bottom", (x, y - 0.049, z - h / 2 - 0.003), (w + 0.010, 0.0025, 0.005)),
        ("left", (x - w / 2 - 0.003, y - 0.049, z), (0.005, 0.0025, h)),
        ("right", (x + w / 2 + 0.003, y - 0.049, z), (0.005, 0.0025, h)),
    ):
        cuboid(
            c,
            f"{name}:cover_glass_edge:{suffix}",
            loc,
            dims,
            M["lcd_glass"],
            0.001,
            role="display_glass",
            detail="bonded anti-reflection cover-glass edge",
        )
    if side_keys:
        for side in (-1, 1):
            for i in range(4):
                zz = z + h * (0.28 - i * 0.18)
                xx = x + side * (w / 2 + 0.052)
                cuboid(
                    c,
                    f"{name}:softkey:{side}:{i}",
                    (xx, y - 0.014, zz),
                    (0.036, 0.027, 0.034),
                    M["button"],
                    0.004,
                    role="screen_softkey",
                    detail="physical display selection key",
                )
                text_front(
                    c,
                    f"{name}:arrow:{side}:{i}",
                    "<" if side > 0 else ">",
                    (xx, y - 0.030, zz),
                    0.014,
                    M["key_legend"],
                    0.00012,
                    role="screen_softkey",
                )
                cylinder(
                    c,
                    f"{name}:key_pip:{side}:{i}",
                    (xx + side * 0.010, y - 0.031, zz + 0.010),
                    0.0023,
                    0.003,
                    M["ui_muted"],
                    rot=(math.pi / 2, 0, 0),
                    vertices=16,
                    role="accessibility_detail",
                    detail="raised soft-key locator pip",
                )


def transaction_slot(
    c, name, x, y, z, w, h, M, label=None, green=False, paper=False, deep=0.050
):
    front_panel(
        c,
        name + ":surround",
        x,
        y,
        z,
        w + 0.050,
        h + 0.040,
        M["slot_trim"],
        0.008,
        role="slot_surround",
        detail="thin die-cast transaction-slot escutcheon",
    )
    front_panel(
        c,
        name + ":inner_trim",
        x,
        y - 0.011,
        z,
        w + 0.018,
        h + 0.014,
        M["brushed_trim"],
        0.004,
        role="slot_surround",
        detail="machined inner slot trim",
    )
    front_panel(
        c,
        name + ":cavity",
        x,
        y - 0.025,
        z,
        w,
        h,
        M["void"],
        0.005,
        role="functional_slot",
        detail="true recessed transaction opening",
    )
    cuboid(
        c,
        name + ":upper_lip",
        (x, y - deep, z + h * 0.48),
        (w * 0.92, deep, 0.013),
        M["brushed_trim"],
        0.003,
        role="slot_mechanism",
        detail="upper media transport lip",
    )
    cuboid(
        c,
        name + ":lower_lip",
        (x, y - deep, z - h * 0.48),
        (w * 0.92, deep, 0.013),
        M["brushed_trim"],
        0.003,
        role="slot_mechanism",
        detail="lower media transport lip",
    )
    # Two internal rubber rollers remain visible in close views and make the
    # opening read as a mechanism rather than a black rectangle.
    for i, dz in enumerate((-h * 0.19, h * 0.19)):
        cylinder(
            c,
            f"{name}:transport_roller:{i}",
            (x, y - deep * 1.12, z + dz),
            max(0.006, h * 0.105),
            w * 0.80,
            M["roller"],
            rot=(0, math.pi / 2, 0),
            vertices=40,
            bevel=0.0015,
            role="slot_mechanism",
            detail="recessed elastomer media transport roller",
        )
    cuboid(
        c,
        name + ":rear_shutter",
        (x, y - deep * 1.52, z),
        (w * 0.88, 0.009, h * 0.46),
        M["shutter"],
        0.002,
        role="slot_mechanism",
        detail="internal anti-fishing shutter",
    )
    if green:
        cuboid(
            c,
            name + ":guide_left",
            (x - w * 0.52, y - 0.030, z),
            (0.012, 0.012, h * 0.72),
            M["green"],
            0.003,
            role="status_light",
            detail="illuminated media guide",
        )
        cuboid(
            c,
            name + ":guide_right",
            (x + w * 0.52, y - 0.030, z),
            (0.012, 0.012, h * 0.72),
            M["green"],
            0.003,
            role="status_light",
            detail="illuminated media guide",
        )
    if paper:
        cuboid(
            c,
            name + ":paper",
            (x, y - 0.073, z - h * 0.10),
            (w * 0.64, 0.0025, h * 0.90),
            M["paper"],
            0.002,
            role="receipt_paper",
            detail="partially presented receipt",
        )
        for i in range(6):
            cuboid(
                c,
                f"{name}:print:{i}",
                (x, y - 0.076, z + h * 0.24 - i * h * 0.11),
                (w * (0.44 if i % 3 else 0.27), 0.001, 0.0022),
                M["ink"],
                0.0003,
                role="receipt_print",
                detail="printed receipt line",
            )
    if label:
        label_strip(
            c, name + ":label", label, x, y + 0.003, z + h / 2 + 0.052, w + 0.015, M
        )


def card_reader(c, name, x, y, z, M, w=0.19, h=0.105, label="CARD"):
    label_strip(c, name + ":label", label, x, y, z + 0.090, w + 0.012, M)
    front_panel(
        c,
        name + ":mount",
        x,
        y,
        z,
        w + 0.060,
        h + 0.065,
        M["slot_trim"],
        0.010,
        role="card_reader",
        detail="cast anti-skimming card-reader bezel",
    )
    transaction_slot(
        c, name + ":slot", x, y - 0.018, z, w, h * 0.25, M, green=True, deep=0.035
    )
    prism_yz(
        c,
        name + ":left_funnel",
        x - w * 0.65,
        x - w * 0.49,
        [
            (y - 0.010, z - h * 0.37),
            (y - 0.058, z - h * 0.24),
            (y - 0.058, z + h * 0.24),
            (y - 0.010, z + h * 0.37),
        ],
        M["brushed_trim"],
        0.003,
        role="card_reader",
        detail="tapered anti-skimming card guide",
    )
    prism_yz(
        c,
        name + ":right_funnel",
        x + w * 0.49,
        x + w * 0.65,
        [
            (y - 0.010, z - h * 0.37),
            (y - 0.058, z - h * 0.24),
            (y - 0.058, z + h * 0.24),
            (y - 0.010, z + h * 0.37),
        ],
        M["brushed_trim"],
        0.003,
        role="card_reader",
        detail="tapered anti-skimming card guide",
    )
    # Directional arrow and contactless indicator are moulded into the bezel.
    verts = [
        (x, y - 0.068, z + h * 0.28),
        (x - w * 0.08, y - 0.068, z + h * 0.08),
        (x - w * 0.025, y - 0.068, z + h * 0.08),
        (x - w * 0.025, y - 0.068, z - h * 0.27),
        (x + w * 0.025, y - 0.068, z - h * 0.27),
        (x + w * 0.025, y - 0.068, z + h * 0.08),
        (x + w * 0.08, y - 0.068, z + h * 0.08),
    ]
    mesh_object(
        c,
        name + ":insert_arrow",
        verts,
        [tuple(range(len(verts)))],
        M["green"],
        0,
        "status_light",
        "illuminated card insertion arrow",
    )


def keypad(
    c,
    name,
    center,
    M,
    width=0.34,
    depth=0.245,
    rot_x=math.radians(11),
    with_privacy_wings=False,
):
    """Build a 16-key EPP keypad on a tilted stainless control bed."""
    cx, cy, cz = center
    rot = Matrix.Rotation(rot_x, 4, "X")

    def world(local):
        return Vector((cx, cy, cz)) + rot @ Vector(local)

    cuboid(
        c,
        name + ":epp_outer",
        center,
        (width + 0.076, depth + 0.070, 0.032),
        M["rubber"],
        0.010,
        rot=(rot_x, 0, 0),
        role="keypad_bed",
        detail="sealed EPP mounting gasket",
    )
    cuboid(
        c,
        name + ":epp_bed",
        world((0, 0, 0.014)),
        (width + 0.056, depth + 0.050, 0.025),
        M["keypad_bed"],
        0.009,
        rot=(rot_x, 0, 0),
        role="keypad_bed",
        detail="PCI-style brushed stainless encrypting PIN pad",
    )
    cuboid(
        c,
        name + ":key_well",
        world((0, 0, 0.030)),
        (width + 0.008, depth + 0.005, 0.008),
        M["void"],
        0.004,
        rot=(rot_x, 0, 0),
        role="keypad_bed",
        detail="recessed black key separator well",
    )
    legends = (
        ("1", "2", "3", "C"),
        ("4", "5", "6", "<"),
        ("7", "8", "9", ">"),
        ("0", "00", ".", "OK"),
    )
    key_w = width / 4.72
    key_d = depth / 4.72
    for row in range(4):
        for col in range(4):
            lx = (col - 1.5) * width / 4.05
            ly = (1.5 - row) * depth / 4.05
            p = world((lx, ly, 0.043))
            kmat = M["key"]
            if col == 3:
                kmat = (
                    M["cancel"]
                    if row == 0
                    else M["clear"]
                    if row in (1, 2)
                    else M["enter"]
                )
            cuboid(
                c,
                f"{name}:key:{row}:{col}",
                p,
                (key_w * (0.82 if col == 3 else 1.0), key_d, 0.020),
                kmat,
                0.004,
                rot=(rot_x, 0, 0),
                role="keypad_key",
                detail="individual sculpted tactile keycap",
            )
            lp = world((lx, ly - 0.003, 0.054))
            text_top(
                c,
                f"{name}:legend:{row}:{col}",
                legends[row][col],
                lp,
                0.018 if len(legends[row][col]) == 1 else 0.012,
                M["key_legend"],
                rot_x,
                role="key_legend",
            )
    p5 = world((-0.5 * width / 4.05, 0.5 * depth / 4.05, 0.061))
    sphere(
        c,
        name + ":five_locator",
        p5,
        0.0042,
        M["key_legend"],
        scale=(1.0, 1.0, 0.35),
        role="accessibility_detail",
        detail="raised tactile locator on numeral five",
    )
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = world((sx * (width / 2 + 0.017), sy * (depth / 2 + 0.014), 0.034))
            cylinder(
                c,
                f"{name}:security_screw:{sx}:{sy}",
                p,
                0.0062,
                0.006,
                M["screw"],
                rot=(rot_x, 0, 0),
                vertices=32,
                bevel=0.001,
                role="fastener",
                detail="tamper-resistant EPP mounting screw",
            )
    if with_privacy_wings:
        for side in (-1, 1):
            cuboid(
                c,
                f"{name}:privacy:{side}",
                world((side * (width / 2 + 0.025), 0, 0.060)),
                (0.035, depth + 0.045, 0.13),
                M["keypad_bed"],
                0.010,
                rot=(rot_x, 0, 0),
                role="privacy_shield",
                detail="PIN-entry privacy wing",
            )


def payment_logos(c, name, x, y, z, w, h, M):
    cuboid(
        c,
        name + ":backing",
        (x, y, z),
        (w, 0.003, h),
        M["vinyl"],
        0.002,
        role="payment_logo_panel",
        detail="thin accepted-card network vinyl decal",
    )
    # Individually constructed flat marks avoid the chunky coloured tiles of
    # the earlier pass while remaining completely procedural and editable.
    xx, zz = x - w * 0.24, z + h * 0.24
    cuboid(
        c,
        name + ":visa_blue",
        (xx, y - 0.003, zz),
        (w * 0.39, 0.0015, h * 0.27),
        M["brand_blue"],
        0.001,
        role="payment_logo",
        detail="VISA decal field",
    )
    text_front(
        c,
        name + ":visa_text",
        "VISA",
        (xx, y - 0.005, zz),
        min(0.020, h * 0.115),
        M["white"],
        0.00008,
        role="payment_logo",
    )
    xx = x + w * 0.24
    for j, dx in enumerate((-0.055, 0.055)):
        cylinder(
            c,
            f"{name}:mc_disc:{j}",
            (xx + dx * w, y - 0.004, zz),
            h * 0.085,
            0.002,
            M["brand_red" if j == 0 else "screen_gold"],
            rot=(math.pi / 2, 0, 0),
            vertices=48,
            role="payment_logo",
            detail="overlapping Mastercard decal disc",
        )
    text_front(
        c,
        name + ":mc_text",
        "MC",
        (xx, y - 0.006, zz),
        min(0.013, h * 0.075),
        M["white"],
        0.00008,
        role="payment_logo",
    )
    xx, zz = x - w * 0.24, z - h * 0.24
    cuboid(
        c,
        name + ":amex_field",
        (xx, y - 0.003, zz),
        (w * 0.39, 0.0015, h * 0.27),
        M["screen_cyan"],
        0.001,
        role="payment_logo",
        detail="American Express decal field",
    )
    text_front(
        c,
        name + ":amex_text",
        "AMEX",
        (xx, y - 0.005, zz),
        min(0.014, h * 0.078),
        M["white"],
        0.00008,
        role="payment_logo",
    )
    xx = x + w * 0.24
    text_front(
        c,
        name + ":contactless",
        ")))",
        (xx, y - 0.005, zz),
        min(0.020, h * 0.12),
        M["screen_green"],
        0.00008,
        role="payment_logo",
    )


def instruction_placard(
    c, name, x, y, z, w, h, M, warning=False, qr=False, warning_arrow=True
):
    cuboid(
        c,
        name + ":plate",
        (x, y, z),
        (w, 0.0035, h),
        M["vinyl"],
        0.003,
        role="instruction_placard",
        detail="laminated operating instruction decal",
    )
    text_front(
        c,
        name + ":heading",
        "NO ENVELOPE" if warning else "TRANSACTION GUIDE",
        (x, y - 0.005, z + h * 0.37),
        min(0.022, h * 0.085),
        M["warning" if warning else "brand_blue"],
        0.00008,
        role="instruction_print",
    )
    line_w = w * 0.52 if qr else w * 0.72
    for i in range(8):
        cuboid(
            c,
            f"{name}:line:{i}",
            (x + (w * 0.12 if qr else 0), y - 0.005, z + h * (0.20 - i * 0.067)),
            (line_w * (1 - 0.07 * (i % 3)), 0.001, 0.003),
            M["ink" if i % 3 else "screen_green"],
            0.0003,
            role="instruction_print",
            detail="printed instruction rule",
        )
    if warning and warning_arrow:
        cuboid(
            c,
            name + ":arrow_stem",
            (x + w * 0.26, y - 0.007, z - h * 0.04),
            (0.016, 0.0015, h * 0.42),
            M["warning"],
            0.003,
            rot=(0, 0, math.radians(-18)),
            role="instruction_print",
        )
        cuboid(
            c,
            name + ":arrow_head_a",
            (x + w * 0.20, y - 0.007, z - h * 0.24),
            (0.16, 0.0015, 0.016),
            M["warning"],
            0.003,
            rot=(0, 0, math.radians(25)),
            role="instruction_print",
        )
        cuboid(
            c,
            name + ":arrow_head_b",
            (x + w * 0.31, y - 0.007, z - h * 0.22),
            (0.14, 0.0015, 0.016),
            M["warning"],
            0.003,
            rot=(0, 0, math.radians(-25)),
            role="instruction_print",
        )
    if qr:
        qx, qz = x - w * 0.31, z - h * 0.02
        pattern = (
            (1, 1, 1, 0, 1),
            (1, 0, 1, 1, 0),
            (1, 1, 1, 0, 1),
            (0, 1, 0, 1, 1),
            (1, 0, 1, 1, 0),
        )
        cell = min(w, h) * 0.045
        for row, values in enumerate(pattern):
            for col, value in enumerate(values):
                if value:
                    cuboid(
                        c,
                        f"{name}:qr:{row}:{col}",
                        (qx + (col - 2) * cell, y - 0.005, qz + (2 - row) * cell),
                        (cell * 0.88, 0.001, cell * 0.88),
                        M["ink"],
                        0.0003,
                        role="qr_code",
                        detail="machine-readable QR module",
                    )


def service_door(c, name, x, y, z, w, h, M, mat_key="body_silver", handle="bar"):
    front_panel(
        c,
        name + ":door",
        x,
        y,
        z,
        w,
        h,
        M[mat_key],
        0.010,
        role="service_door",
        detail="full-height lockable service access door",
    )
    seam(c, name + ":top_seam", x, y - 0.017, z + h / 2, w, M)
    seam(c, name + ":bottom_seam", x, y - 0.017, z - h / 2, w, M)
    seam(c, name + ":left_seam", x - w / 2, y - 0.017, z, h, M, vertical=True)
    seam(c, name + ":right_seam", x + w / 2, y - 0.017, z, h, M, vertical=True)
    for sx in (-1, 1):
        fastener(
            c, f"{name}:corner:{sx}:top", x + sx * w * 0.45, y - 0.024, z + h * 0.43, M
        )
        fastener(
            c,
            f"{name}:corner:{sx}:bottom",
            x + sx * w * 0.45,
            y - 0.024,
            z - h * 0.43,
            M,
        )
    if handle == "bar":
        tube(
            c,
            name + ":pull_handle",
            [
                (x - w * 0.29, y - 0.060, z + h * 0.17),
                (x - w * 0.14, y - 0.092, z + h * 0.21),
                (x + w * 0.15, y - 0.092, z + h * 0.21),
                (x + w * 0.29, y - 0.060, z + h * 0.17),
            ],
            0.018,
            M["chrome"],
            role="service_handle",
            detail="bowed stainless service-door pull",
        )
    elif handle == "vertical":
        tube(
            c,
            name + ":vertical_handle",
            [
                (x - w * 0.37, y - 0.055, z - 0.18),
                (x - w * 0.40, y - 0.090, z - 0.09),
                (x - w * 0.40, y - 0.090, z + 0.18),
                (x - w * 0.37, y - 0.055, z + 0.27),
            ],
            0.014,
            M["chrome"],
            role="service_handle",
            detail="vertical service-door pull",
        )
    cylinder(
        c,
        name + ":lock",
        (x - w * 0.34, y - 0.035, z - h * 0.19),
        0.027,
        0.025,
        M["chrome"],
        rot=(math.pi / 2, 0, 0),
        role="service_lock",
        detail="keyed service lock cylinder",
    )


def side_vent_field(c, name, x, y0, z0, M, rows=12, cols=3, side=-1):
    """Actual recessed side ventilation slots, visible in oblique renders."""
    for row in range(rows):
        for col in range(cols):
            yy = y0 + (col - (cols - 1) / 2) * 0.145
            zz = z0 + row * 0.115
            cuboid(
                c,
                f"{name}:slot:{row}:{col}",
                (x, yy, zz),
                (0.012, 0.082, 0.024),
                M["void"],
                0.004,
                rot=(0, math.radians(9 * side), 0),
                role="ventilation",
                detail="recessed punched side-panel ventilation slot",
            )
    for yy in (y0 - 0.23, y0 + 0.23):
        for zz in (z0 - 0.08, z0 + (rows - 1) * 0.115 + 0.08):
            cylinder(
                c,
                f"{name}:side_screw:{yy:.2f}:{zz:.2f}",
                (x - 0.005 * side, yy, zz),
                0.010,
                0.012,
                M["screw"],
                rot=(0, math.pi / 2, 0),
                vertices=24,
                bevel=0.001,
                role="fastener",
                detail="side service-panel fastener",
            )


def _fit_front_text_width(obj, max_width):
    """Constrain raised front lettering to a measured physical width.

    Font metrics vary between Blender builds.  Measuring the evaluated text
    keeps long bank names inside their sign face instead of relying on a
    guessed character count.
    """
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    width = max(point.x for point in points) - min(point.x for point in points)
    if width > max_width:
        obj.scale.x *= max_width / width
        bpy.context.view_layer.update()
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        width = max(point.x for point in points) - min(point.x for point in points)
    obj["c2w_text_max_width_m"] = max_width
    obj["c2w_text_fitted_width_m"] = width
    return obj


def add_brand_lightbox(
    c,
    name,
    x,
    y,
    z,
    w,
    h,
    M,
    body="ATM",
    face_mat="brand_blue",
    text_size=None,
    text_offset_x=0.0,
    text_max_width=None,
):
    cuboid(
        c,
        name + ":case",
        (x, y, z),
        (w, 0.18, h),
        M["black"],
        0.015,
        role="brand_lightbox",
        detail="projecting illuminated bank sign cabinet",
    )
    front_panel(
        c,
        name + ":face",
        x,
        y - 0.105,
        z,
        w * 0.90,
        h * 0.72,
        M[face_mat],
        0.006,
        role="brand_face",
        detail="replaceable translucent brand sign face",
    )
    text_mat = (
        M["ink"] if face_mat in {"paper", "vinyl", "body_white"} else M["ui_white"]
    )
    label = text_front(
        c,
        name + ":text",
        body,
        (x + text_offset_x, y - 0.123, z),
        text_size or min(0.13, h * 0.43),
        text_mat,
        0.00045,
        role="brand_face",
    )
    if text_max_width is not None:
        _fit_front_text_width(label, text_max_width)
    for sx in (-1, 1):
        fastener(
            c, f"{name}:fastener:{sx}", x + sx * w * 0.45, y - 0.116, z, M, radius=0.009
        )


def materials():
    return {
        "body_silver": brushed_metal(
            "atm3_body_silver", (0.16, 0.18, 0.19), (0.32, 0.34, 0.35), 0.33
        ),
        "stainless": brushed_metal(
            "atm3_stainless_worktop", (0.14, 0.155, 0.165), (0.31, 0.33, 0.34), 0.29
        ),
        "brushed_trim": brushed_metal(
            "atm3_machined_slot_trim", (0.25, 0.27, 0.28), (0.49, 0.51, 0.52), 0.22
        ),
        "chrome": material(
            "atm3_chrome", (0.52, 0.57, 0.59), 0.14, 0.94, 0.003, coat=0.10
        ),
        "steel_dark": material(
            "atm3_dark_steel", (0.038, 0.045, 0.051), 0.34, 0.70, 0.010
        ),
        "slot_trim": material(
            "atm3_slot_trim", (0.105, 0.116, 0.123), 0.32, 0.64, 0.006
        ),
        "body_white": material(
            "atm3_powder_coat_white", (0.70, 0.72, 0.70), 0.43, 0.04, 0.012
        ),
        "body_bronze": material(
            "atm3_copper_bronze", (0.235, 0.070, 0.034), 0.43, 0.50, 0.010
        ),
        "bronze_dark": material(
            "atm3_bronze_recess", (0.068, 0.024, 0.014), 0.47, 0.24, 0.006
        ),
        "body_charcoal": material(
            "atm3_charcoal_body", (0.021, 0.026, 0.029), 0.55, 0.31, 0.012
        ),
        "body_gray": material(
            "atm3_service_gray", (0.27, 0.29, 0.29), 0.56, 0.23, 0.010
        ),
        "black": material("atm3_black", (0.004, 0.006, 0.007), 0.43, 0.26, 0.002),
        "bezel": material("atm3_bezel", (0.011, 0.014, 0.017), 0.27, 0.37, 0.003),
        "void": material(
            "atm3_deep_void", (0.0002, 0.0003, 0.0004), 0.82, 0.0, 0, coat=0
        ),
        "vent_shadow": material(
            "atm3_vent_shadow", (0.001, 0.002, 0.0025), 0.88, 0, 0, coat=0
        ),
        "seam": material(
            "atm3_panel_seam", (0.006, 0.008, 0.009), 0.78, 0.08, 0, coat=0
        ),
        "rubber": rubber_material("atm3_seal_rubber"),
        "roller": rubber_material("atm3_transport_roller", (0.012, 0.014, 0.014), 0.72),
        "shutter": material(
            "atm3_anti_fishing_shutter", (0.075, 0.081, 0.083), 0.42, 0.70, 0.003
        ),
        "screw": material("atm3_fastener_steel", (0.17, 0.18, 0.19), 0.22, 0.90, 0.002),
        "button": material("atm3_softkey", (0.085, 0.095, 0.101), 0.43, 0.18, 0.004),
        "keypad_bed": brushed_metal(
            "atm3_keypad_bed", (0.14, 0.15, 0.155), (0.27, 0.285, 0.29), 0.32
        ),
        "key": material("atm3_keycap", (0.16, 0.17, 0.175), 0.44, 0.20, 0.004),
        "key_legend": decal_material("atm3_key_legend", (0.70, 0.72, 0.70), 0.51),
        "cancel": material("atm3_cancel_key", (0.53, 0.018, 0.012), 0.39, 0.03, 0.004),
        "clear": material("atm3_clear_key", (0.70, 0.39, 0.010), 0.39, 0.03, 0.004),
        "enter": material("atm3_enter_key", (0.018, 0.37, 0.064), 0.38, 0.03, 0.004),
        "red": material("atm3_brand_red", (0.48, 0.008, 0.013), 0.32, 0.20, 0.009),
        "gold": material("atm3_brand_gold", (0.48, 0.27, 0.035), 0.33, 0.62, 0.008),
        "brand_blue": decal_material("atm3_brand_blue", (0.020, 0.075, 0.30), 0.32),
        "brand_red": decal_material("atm3_brand_mark_red", (0.58, 0.021, 0.016), 0.36),
        "green": emissive_material("atm3_status_green", (0.010, 0.55, 0.055), 1.45),
        "amber": emissive_material("atm3_status_amber", (0.86, 0.27, 0.012), 1.35),
        "warm_light": emissive_material(
            "atm3_warm_task_light", (1.0, 0.72, 0.32), 2.2, 0.22
        ),
        "lcd_blue": emissive_material(
            "atm3_lcd_blue", (0.003, 0.018, 0.042), 0.20, 0.13
        ),
        "lcd_black": emissive_material(
            "atm3_lcd_black", (0.0015, 0.004, 0.007), 0.11, 0.11
        ),
        "lcd_glass": glass_material(
            "atm3_lcd_cover_glass", (0.010, 0.018, 0.024), 0.055, 0.72
        ),
        "camera_glass": glass_material(
            "atm3_camera_optic", (0.004, 0.018, 0.030), 0.035, 0.54
        ),
        "screen_blue": emissive_material(
            "atm3_secondary_lcd_blue", (0.004, 0.045, 0.105), 0.30, 0.16
        ),
        "screen_black": emissive_material(
            "atm3_active_screen_black", (0.002, 0.006, 0.010), 0.16, 0.13
        ),
        "screen_cyan": emissive_material(
            "atm3_screen_cyan", (0.055, 0.35, 0.58), 0.48, 0.23
        ),
        "screen_green": emissive_material(
            "atm3_screen_green", (0.035, 0.42, 0.13), 0.43, 0.24
        ),
        "screen_gold": emissive_material(
            "atm3_screen_gold", (0.72, 0.34, 0.025), 0.38, 0.25
        ),
        "screen_reflection": material(
            "atm3_screen_reflection", (0.025, 0.055, 0.075), 0.06, 0.06, 0, coat=0.30
        ),
        "ui_blue": emissive_material("atm3_ui_blue", (0.035, 0.20, 0.46), 0.34, 0.26),
        "ui_rule": emissive_material("atm3_ui_rule", (0.040, 0.10, 0.16), 0.18, 0.35),
        "ui_muted": emissive_material("atm3_ui_muted", (0.34, 0.48, 0.56), 0.22, 0.35),
        "ui_text": emissive_material("atm3_ui_text", (0.62, 0.73, 0.76), 0.25, 0.32),
        "ui_dark": material("atm3_ui_dark", (0.006, 0.014, 0.027), 0.31, 0.01, 0),
        "ui_white": emissive_material("atm3_ui_white", (0.70, 0.79, 0.82), 0.31, 0.30),
        "white": decal_material("atm3_print_white", (0.80, 0.81, 0.78), 0.57),
        "vinyl": decal_material("atm3_laminated_vinyl", (0.79, 0.79, 0.74), 0.46),
        "paper": material("atm3_paper", (0.78, 0.76, 0.68), 0.72, 0, 0.005, coat=0.01),
        "ink": decal_material("atm3_print_ink", (0.012, 0.016, 0.018), 0.72),
        "warning": decal_material("atm3_warning_red", (0.61, 0.012, 0.010), 0.44),
        "warning_yellow": decal_material(
            "atm3_warning_yellow", (0.82, 0.58, 0.025), 0.48
        ),
    }


# -----------------------------------------------------------------------------
# Five reference-driven machine factories
# -----------------------------------------------------------------------------


def _finalize_variant(c, variant, reference_index, nominal_dims):
    c["variant"] = variant
    c["reference_url"] = REFERENCES[reference_index]
    c["reference_index"] = reference_index + 1
    c["nominal_dimensions_m"] = list(nominal_dims)
    c["c2w_asset_id"] = "atm:" + variant
    c["c2w_asset_kind"] = "street_furniture.atm"
    c["c2w_role"] = "procedural_asset"
    c["c2w_generator"] = str(Path(__file__).resolve())
    c["c2w_generator_version"] = GENERATOR_VERSION
    return c


def atm_01a_silver_freestanding(parent, M, palette=None):
    """Reference 1 left: deep full-height 2-in-1 freestanding machine."""
    c = collection(COLLECTION_NAMES[0], parent)
    cuboid(
        c,
        "01a:rear_carcass",
        (0, 0.02, 1.07),
        (1.10, 0.82, 2.14),
        M["body_silver"],
        0.028,
        role="structural_cabinet",
        detail="full-depth welded steel security carcass",
    )
    cuboid(
        c,
        "01a:top_cap",
        (0, -0.01, 2.145),
        (1.12, 0.84, 0.055),
        M["stainless"],
        0.012,
        role="cabinet_cap",
        detail="overlapping stainless top cap",
    )
    for sx in (-1, 1):
        prism_yz(
            c,
            f"01a:formed_front_rail:{sx}",
            sx * 0.55,
            sx * 0.47,
            [
                (-0.44, 0.04),
                (-0.50, 0.10),
                (-0.52, 2.03),
                (-0.44, 2.14),
                (-0.36, 2.14),
                (-0.40, 0.04),
            ],
            M["stainless"],
            0.010,
            role="structural_cabinet",
            detail="continuous rolled stainless front edge rail",
        )
    front_panel(
        c,
        "01a:alcove_back",
        -0.055,
        -0.447,
        1.58,
        0.90,
        0.92,
        M["steel_dark"],
        0.015,
        role="operator_recess",
        detail="deep anti-glare operator alcove",
    )
    prism_yz(
        c,
        "01a:canopy",
        -0.46,
        0.46,
        [(-0.45, 1.94), (-0.61, 1.86), (-0.61, 2.02), (-0.43, 2.12)],
        M["stainless"],
        0.012,
        role="protective_hood",
        detail="projecting formed overhead canopy",
    )
    for sx in (-1, 1):
        prism_yz(
            c,
            f"01a:alcove_cheek:{sx}",
            sx * 0.46,
            sx * 0.38,
            [(-0.44, 1.11), (-0.61, 1.18), (-0.61, 1.96), (-0.45, 2.06)],
            M["body_silver"],
            0.010,
            role="protective_hood",
            detail="tapered deep operator-protection cheek",
        )
    task_light(c, "01a:task_light", -0.05, -0.615, 1.965, 0.70, M)
    cuboid(
        c,
        "01a:left_interface_carrier",
        (-0.17, -0.495, 1.55),
        (0.54, 0.12, 0.73),
        M["body_silver"],
        0.014,
        role="interface_panel",
        detail="removable left transaction module",
    )
    cuboid(
        c,
        "01a:right_io_carrier",
        (0.32, -0.505, 1.55),
        (0.27, 0.13, 0.75),
        M["body_silver"],
        0.012,
        role="io_column",
        detail="stacked removable media module",
    )
    front_panel(
        c,
        "01a:oem_badge",
        -0.15,
        -0.572,
        1.86,
        0.18,
        0.050,
        M["paper"],
        0.004,
        role="equipment_label",
        detail="OEM identification plate",
    )
    text_front(
        c,
        "01a:oem_text",
        "WINCOR",
        (-0.15, -0.590, 1.86),
        0.025,
        M["ink"],
        0.0007,
        role="equipment_label",
    )
    ui_screen(
        c,
        "01a:screen",
        -0.18,
        -0.570,
        1.58,
        0.43,
        0.32,
        M,
        "blue",
        True,
        "ATM / CASH ADVANCE",
    )
    transaction_slot(
        c,
        "01a:cash",
        -0.18,
        -0.570,
        1.315,
        0.41,
        0.070,
        M,
        label="MONEY",
        green=False,
        deep=0.060,
    )
    transaction_slot(
        c,
        "01a:receipt",
        0.32,
        -0.576,
        1.790,
        0.18,
        0.038,
        M,
        label="RECEIPT",
        paper=True,
        deep=0.040,
    )
    card_reader(c, "01a:card", 0.32, -0.576, 1.565, M, 0.17, 0.09, "CARD")
    front_panel(
        c,
        "01a:deposit_bay",
        0.32,
        -0.579,
        1.320,
        0.20,
        0.235,
        M["black"],
        0.008,
        role="deposit_module",
        detail="motorised envelope/check intake bay",
    )
    transaction_slot(
        c,
        "01a:deposit_throat",
        0.32,
        -0.598,
        1.345,
        0.14,
        0.045,
        M,
        green=True,
        deep=0.035,
    )
    cuboid(
        c,
        "01a:deposit_envelope",
        (0.32, -0.632, 1.270),
        (0.11, 0.012, 0.135),
        M["paper"],
        0.003,
        role="deposit_media",
        detail="diagrammatic deposit envelope target",
    )
    status_lamp(c, "01a:deposit_status", 0.41, -0.614, 1.445, M, "green", 0.018)
    speaker_grille(c, "01a:speaker", 0.32, -0.607, 1.155, 3, 2, 0.028, M)
    prism_yz(
        c,
        "01a:work_shelf",
        -0.47,
        0.47,
        [(-0.45, 1.12), (-0.76, 1.02), (-0.76, 0.945), (-0.45, 1.00)],
        M["stainless"],
        0.012,
        role="operator_shelf",
        detail="deep perforated stainless work shelf",
    )
    keypad(
        c, "01a:keypad", (-0.13, -0.645, 1.055), M, 0.34, 0.23, math.radians(12), True
    )
    tube(
        c,
        "01a:shelf_grip",
        [
            (0.20, -0.785, 1.035),
            (0.26, -0.808, 1.048),
            (0.37, -0.808, 1.048),
            (0.41, -0.785, 1.035),
        ],
        0.010,
        M["chrome"],
        role="operator_hardware",
        detail="stainless work-shelf grip",
    )
    service_door(
        c, "01a:lower_service", 0, -0.416, 0.50, 0.91, 0.88, M, "body_silver", "bar"
    )
    tube(
        c,
        "01a:lock_lever",
        [(-0.34, -0.470, 0.38), (-0.36, -0.490, 0.34), (-0.36, -0.490, 0.25)],
        0.012,
        M["chrome"],
        role="service_lock",
        detail="levered cabinet lock handle",
    )
    cuboid(
        c,
        "01a:toe_plinth",
        (0, -0.01, 0.055),
        (1.03, 0.79, 0.11),
        M["steel_dark"],
        0.012,
        role="service_plinth",
        detail="recessed anti-corrosion toe plinth",
    )
    diamond_vent_field(
        c, "01a:left_vent", -0.558, 0.02, 1.14, 0.66, 1.66, M, side=-1, rows=20, cols=5
    )
    diamond_vent_field(
        c, "01a:right_vent", 0.558, 0.02, 1.14, 0.66, 1.66, M, side=1, rows=20, cols=5
    )
    for side in (-1, 1):
        for i, zz in enumerate((0.38, 0.82, 1.34, 1.78)):
            cylinder(
                c,
                f"01a:side_access_plug:{side}:{i}",
                (side * 0.565, 0.30, zz),
                0.030,
                0.012,
                M["brushed_trim"],
                rot=(0, math.pi / 2, 0),
                vertices=48,
                bevel=0.002,
                role="service_access",
                detail="flush side service access plug",
            )
    micro_perforation_patch(
        c,
        "01a:worktop_microperforation",
        (0, -0.605, 1.064),
        (1, 0, 0),
        (0, -0.955, -0.296),
        19,
        6,
        0.044,
        0.034,
        0.0030,
        M["seam"],
    )
    security_camera(c, "01a:operator_camera", 0.325, -0.620, 1.920, M, 0.013)
    headphone_jack(c, "01a:audio", 0.425, -0.625, 1.155, M)
    barcode_label(
        c, "01a:asset_label", 0.255, -0.435, 0.620, 0.22, 0.105, M, "SERVICE / SERIAL"
    )
    warning_label(
        c,
        "01a:electrical_warning",
        0.275,
        -0.436,
        0.345,
        0.19,
        0.105,
        M,
        "HIGH SECURITY",
    )
    for zhinge in (0.31, 0.70):
        hinge(c, f"01a:door_hinge:{zhinge}", 0.452, -0.438, zhinge, 0.17, M)
    floor_mount_set(c, "01a:floor_mount", 0.43, 0.29, M, 0.032)
    return _finalize_variant(c, VARIANT_NAMES[0], 0, (1.12, 0.84, 2.17))


def atm_01b_silver_through_wall(parent, M, palette=None):
    """Reference 1 right: the same product family in flush wall-mount form."""
    c = collection(COLLECTION_NAMES[1], parent)
    cuboid(
        c,
        "01b:mounting_sleeve",
        (0, 0.12, 1.23),
        (1.15, 0.52, 1.72),
        M["steel_dark"],
        0.018,
        role="structural_cabinet",
        detail="through-wall security mounting sleeve",
    )
    front_panel(
        c,
        "01b:recess_back",
        0,
        -0.164,
        1.27,
        0.92,
        1.43,
        M["steel_dark"],
        0.012,
        role="operator_recess",
        detail="deep through-wall operator recess",
    )
    for sx in (-1, 1):
        cuboid(
            c,
            f"01b:frame_side:{sx}",
            (sx * 0.54, -0.205, 1.27),
            (0.12, 0.13, 1.71),
            M["body_silver"],
            0.014,
            role="installation_frame",
            detail="heavy flush-mount stainless frame stile",
        )
    cuboid(
        c,
        "01b:frame_header",
        (0, -0.205, 2.105),
        (1.16, 0.13, 0.12),
        M["body_silver"],
        0.014,
        role="installation_frame",
        detail="flush-mount frame header",
    )
    cuboid(
        c,
        "01b:frame_sill",
        (0, -0.205, 0.425),
        (1.16, 0.13, 0.12),
        M["body_silver"],
        0.014,
        role="installation_frame",
        detail="flush-mount frame sill",
    )
    prism_yz(
        c,
        "01b:canopy",
        -0.47,
        0.47,
        [(-0.22, 1.93), (-0.39, 1.84), (-0.39, 2.01), (-0.20, 2.08)],
        M["stainless"],
        0.010,
        role="protective_hood",
        detail="integrated through-wall task-light canopy",
    )
    task_light(c, "01b:task_light", 0, -0.402, 1.945, 0.70, M)
    cuboid(
        c,
        "01b:left_carrier",
        (-0.15, -0.245, 1.42),
        (0.56, 0.13, 0.72),
        M["body_silver"],
        0.012,
        role="interface_panel",
        detail="screen and cash-dispenser module carrier",
    )
    cuboid(
        c,
        "01b:right_carrier",
        (0.33, -0.245, 1.43),
        (0.28, 0.13, 0.76),
        M["body_silver"],
        0.012,
        role="io_column",
        detail="receipt/card/deposit I/O tower",
    )
    front_panel(
        c,
        "01b:oem_badge",
        -0.15,
        -0.324,
        1.78,
        0.18,
        0.050,
        M["paper"],
        0.004,
        role="equipment_label",
        detail="OEM identification plate",
    )
    text_front(
        c,
        "01b:oem_text",
        "WINCOR",
        (-0.15, -0.342, 1.78),
        0.025,
        M["ink"],
        0.0007,
        role="equipment_label",
    )
    ui_screen(
        c,
        "01b:screen",
        -0.17,
        -0.327,
        1.49,
        0.44,
        0.33,
        M,
        "blue",
        True,
        "ATM / CASH ADVANCE",
    )
    transaction_slot(
        c, "01b:cash", -0.17, -0.327, 1.222, 0.41, 0.070, M, label="MONEY", deep=0.052
    )
    transaction_slot(
        c,
        "01b:receipt",
        0.33,
        -0.330,
        1.690,
        0.18,
        0.038,
        M,
        label="RECEIPT",
        paper=True,
    )
    card_reader(c, "01b:card", 0.33, -0.330, 1.475, M, 0.17, 0.09, "CARD")
    front_panel(
        c,
        "01b:deposit_bay",
        0.33,
        -0.334,
        1.245,
        0.20,
        0.22,
        M["black"],
        0.008,
        role="deposit_module",
        detail="motorised envelope/check intake bay",
    )
    transaction_slot(
        c, "01b:deposit", 0.33, -0.351, 1.278, 0.14, 0.045, M, green=True, deep=0.035
    )
    speaker_grille(c, "01b:speaker", 0.33, -0.356, 1.105, 3, 2, 0.027, M)
    prism_yz(
        c,
        "01b:work_shelf",
        -0.47,
        0.47,
        [(-0.22, 1.08), (-0.52, 0.98), (-0.52, 0.89), (-0.22, 0.96)],
        M["stainless"],
        0.012,
        role="operator_shelf",
        detail="through-wall stainless work shelf",
    )
    keypad(
        c, "01b:keypad", (-0.13, -0.410, 1.005), M, 0.34, 0.23, math.radians(11), True
    )
    tube(
        c,
        "01b:shelf_grip",
        [
            (0.20, -0.534, 0.980),
            (0.27, -0.553, 0.991),
            (0.38, -0.553, 0.991),
            (0.42, -0.534, 0.980),
        ],
        0.010,
        M["chrome"],
        role="operator_hardware",
        detail="work-shelf convenience grip",
    )
    for sx in (-1, 1):
        for zz in (0.50, 0.90, 1.30, 1.70, 2.02):
            fastener(
                c, f"01b:frame_fastener:{sx}:{zz}", sx * 0.54, -0.278, zz, M, 0.010
            )
    seam(c, "01b:module_lower_seam", 0, -0.284, 0.81, 0.92, M)
    # The front fascia is a through-wall product, but its rear safe and base
    # still transfer load to the floor.  Modelling that hidden support removes
    # the physically impossible floating presentation from the previous pass.
    cuboid(
        c,
        "01b:lower_security_safe",
        (0, 0.10, 0.225),
        (1.01, 0.47, 0.45),
        M["steel_dark"],
        0.016,
        role="structural_cabinet",
        detail="floor-bearing through-wall rear security safe",
    )
    cuboid(
        c,
        "01b:toe_plinth",
        (0, 0.10, 0.055),
        (0.96, 0.43, 0.11),
        M["black"],
        0.009,
        role="service_plinth",
        detail="floor-contact through-wall cabinet plinth",
    )
    for sx in (-1, 1):
        cuboid(
            c,
            f"01b:frame_weather_seal:{sx}",
            (sx * 0.475, -0.278, 1.27),
            (0.014, 0.009, 1.53),
            M["rubber"],
            0.003,
            role="installation_seal",
            detail="continuous flush-frame weather gasket",
        )
    micro_perforation_patch(
        c,
        "01b:worktop_microperforation",
        (0, -0.390, 0.993),
        (1, 0, 0),
        (0, -0.955, -0.296),
        19,
        5,
        0.043,
        0.034,
        0.0028,
        M["seam"],
    )
    security_camera(c, "01b:operator_camera", 0.335, -0.376, 1.925, M, 0.012)
    headphone_jack(c, "01b:audio", 0.430, -0.380, 1.105, M)
    barcode_label(
        c, "01b:rear_safe_label", 0.24, -0.145, 0.225, 0.20, 0.095, M, "SAFE MODULE"
    )
    warning_label(
        c, "01b:rear_safe_warning", -0.25, -0.145, 0.225, 0.19, 0.095, M, "SERVICE ONLY"
    )
    floor_mount_set(c, "01b:floor_mount", 0.40, 0.15, M, 0.031)
    return _finalize_variant(c, VARIANT_NAMES[1], 0, (1.16, 0.70, 2.17))


def atm_02_white_oxford(parent, M, palette=None):
    """Reference 2: compact white Oxford through-wall deposit ATM."""
    c = collection(COLLECTION_NAMES[2], parent)
    cuboid(
        c,
        "02:security_sleeve",
        (0, 0.10, 1.20),
        (1.08, 0.50, 1.66),
        M["body_gray"],
        0.018,
        role="structural_cabinet",
        detail="through-wall security chassis",
    )
    front_panel(
        c,
        "02:recess_back",
        0,
        -0.182,
        1.23,
        0.87,
        1.42,
        M["steel_dark"],
        0.012,
        role="operator_recess",
        detail="dark high-contrast operator recess",
    )
    for sx in (-1, 1):
        cuboid(
            c,
            f"02:white_stile:{sx}",
            (sx * 0.49, -0.228, 1.22),
            (0.13, 0.14, 1.75),
            M["body_white"],
            0.016,
            role="installation_frame",
            detail="powder-coated flush-mount frame stile",
        )
    cuboid(
        c,
        "02:white_header",
        (0, -0.228, 2.065),
        (1.10, 0.14, 0.13),
        M["body_white"],
        0.016,
        role="installation_frame",
        detail="powder-coated frame header",
    )
    cuboid(
        c,
        "02:white_sill",
        (0, -0.228, 0.385),
        (1.10, 0.14, 0.13),
        M["body_white"],
        0.016,
        role="installation_frame",
        detail="powder-coated frame sill",
    )
    task_light(c, "02:top_light", -0.18, -0.348, 1.955, 0.46, M)
    ui_screen(
        c, "02:screen", -0.18, -0.336, 1.57, 0.51, 0.39, M, "blue", False, "OXFORD"
    )
    for i in range(5):
        front_panel(
            c,
            f"02:screen_bottom_key:{i}",
            -0.37 + i * 0.095,
            -0.380,
            1.348,
            0.062,
            0.020,
            M["button"],
            0.003,
            role="screen_softkey",
            detail="bottom-edge LCD selection key",
        )
    prism_yz(
        c,
        "02:control_console",
        -0.42,
        0.16,
        [(-0.20, 1.31), (-0.49, 1.20), (-0.49, 1.04), (-0.20, 1.09)],
        M["stainless"],
        0.012,
        role="operator_shelf",
        detail="sloped cast-metal control console",
    )
    keypad(
        c, "02:keypad", (-0.18, -0.395, 1.205), M, 0.27, 0.20, math.radians(12), False
    )
    cuboid(
        c,
        "02:privacy_panel",
        (-0.39, -0.410, 1.175),
        (0.085, 0.19, 0.075),
        M["steel_dark"],
        0.012,
        rot=(math.radians(12), 0, 0),
        role="privacy_shield",
        detail="left-side PIN privacy block",
    )
    cuboid(
        c,
        "02:fingerprint_pad",
        (0.06, -0.408, 1.178),
        (0.10, 0.16, 0.020),
        M["paper"],
        0.008,
        rot=(math.radians(12), 0, 0),
        role="biometric_reader",
        detail="illuminated biometric/contact pad",
    )
    cuboid(
        c,
        "02:io_tower",
        (0.30, -0.272, 1.49),
        (0.30, 0.14, 0.96),
        M["body_silver"],
        0.012,
        role="io_column",
        detail="stacked Oxford transaction I/O module",
    )
    front_panel(
        c,
        "02:camera_window",
        0.30,
        -0.354,
        1.815,
        0.22,
        0.125,
        M["black"],
        0.006,
        role="security_camera",
        detail="tinted dual-camera security window",
    )
    for cx in (0.265, 0.335):
        cylinder(
            c,
            f"02:camera_lens:{cx}",
            (cx, -0.372, 1.815),
            0.024,
            0.012,
            M["screen_black"],
            rot=(math.pi / 2, 0, 0),
            role="security_camera",
            detail="recessed security camera lens",
        )
    transaction_slot(
        c,
        "02:receipt",
        0.30,
        -0.355,
        1.655,
        0.18,
        0.040,
        M,
        label="RECEIPT",
        paper=True,
    )
    card_reader(c, "02:card", 0.30, -0.355, 1.455, M, 0.17, 0.09, "CARD")
    transaction_slot(
        c,
        "02:cash_acceptor",
        0.30,
        -0.355,
        1.235,
        0.19,
        0.070,
        M,
        label="CASH ONLY",
        green=True,
    )
    front_panel(
        c,
        "02:lower_module",
        -0.20,
        -0.299,
        0.82,
        0.53,
        0.30,
        M["body_gray"],
        0.010,
        role="deposit_module",
        detail="lower bulk-note deposit/dispenser module",
    )
    transaction_slot(
        c, "02:lower_cash", -0.20, -0.329, 0.85, 0.38, 0.085, M, deep=0.065
    )
    # The reference's clean instruction plate has no large red arrow.  Keep
    # the fine printed warning but omit the former three-stroke arrow graphic.
    instruction_placard(
        c,
        "02:no_envelope",
        0.27,
        -0.320,
        0.82,
        0.35,
        0.27,
        M,
        warning=True,
        qr=False,
        warning_arrow=False,
    )
    for sx in (-1, 1):
        for zz in (0.44, 2.00):
            fastener(c, f"02:frame_fastener:{sx}:{zz}", sx * 0.49, -0.307, zz, M, 0.010)
    seam(c, "02:frame_module_seam", 0, -0.302, 0.58, 0.84, M)
    cuboid(
        c,
        "02:floor_security_safe",
        (0, 0.09, 0.205),
        (0.96, 0.44, 0.41),
        M["steel_dark"],
        0.014,
        role="structural_cabinet",
        detail="floor-bearing Oxford through-wall safe module",
    )
    cuboid(
        c,
        "02:white_lower_apron",
        (0, -0.228, 0.160),
        (1.10, 0.14, 0.32),
        M["body_white"],
        0.014,
        role="installation_frame",
        detail="grounded lower return of white architectural frame",
    )
    cuboid(
        c,
        "02:toe_plinth",
        (0, 0.08, 0.045),
        (0.91, 0.40, 0.09),
        M["black"],
        0.008,
        role="service_plinth",
        detail="recessed Oxford safe floor plinth",
    )
    for sx in (-1, 1):
        cuboid(
            c,
            f"02:frame_weather_seal:{sx}",
            (sx * 0.425, -0.300, 1.23),
            (0.012, 0.008, 1.40),
            M["rubber"],
            0.0025,
            role="installation_seal",
            detail="black flush-install weather seal",
        )
    micro_perforation_patch(
        c,
        "02:console_microtexture",
        (-0.16, -0.392, 1.180),
        (1, 0, 0),
        (0, -0.970, -0.242),
        13,
        4,
        0.041,
        0.033,
        0.0025,
        M["seam"],
    )
    headphone_jack(c, "02:audio", 0.085, -0.382, 1.605, M)
    barcode_label(
        c, "02:module_label", -0.24, -0.306, 0.600, 0.22, 0.090, M, "OXFORD OXF-R3"
    )
    warning_label(
        c, "02:service_warning", 0.27, -0.240, 0.190, 0.21, 0.090, M, "MAINS ISOLATE"
    )
    floor_mount_set(c, "02:floor_mount", 0.38, 0.14, M, 0.030)
    return _finalize_variant(c, VARIANT_NAMES[2], 1, (1.10, 0.64, 2.14))


def atm_03_bronze(parent, M, palette=None):
    """Reference 3: tall bronze/copper ATM with deeply sculpted alcove."""
    c = collection(COLLECTION_NAMES[3], parent)
    cuboid(
        c,
        "03:security_carcass",
        (0, 0.02, 1.08),
        (1.02, 0.80, 2.16),
        M["body_bronze"],
        0.024,
        role="structural_cabinet",
        detail="full-depth bronze-clad security carcass",
    )
    cuboid(
        c,
        "03:rear_cap",
        (0, 0.385, 1.10),
        (1.04, 0.055, 2.12),
        M["bronze_dark"],
        0.010,
        role="cabinet_cap",
        detail="rear service cap",
    )
    for sx in (-1, 1):
        prism_yz(
            c,
            f"03:sloping_cheek:{sx}",
            sx * 0.51,
            sx * 0.39,
            [
                (-0.39, 0.04),
                (-0.49, 0.12),
                (-0.58, 1.22),
                (-0.56, 2.02),
                (-0.42, 2.16),
                (-0.32, 2.16),
                (-0.38, 0.04),
            ],
            M["body_bronze"],
            0.011,
            role="protective_hood",
            detail="deep tapered bronze operator-protection cheek",
        )
    front_panel(
        c,
        "03:alcove_back",
        -0.08,
        -0.442,
        1.53,
        0.72,
        1.05,
        M["bronze_dark"],
        0.014,
        role="operator_recess",
        detail="deep shadowed transaction alcove",
    )
    prism_yz(
        c,
        "03:header_hood",
        -0.40,
        0.40,
        [(-0.38, 1.92), (-0.60, 1.85), (-0.57, 2.14), (-0.38, 2.19)],
        M["body_bronze"],
        0.012,
        role="protective_hood",
        detail="sloped illuminated bronze header hood",
    )
    add_brand_lightbox(
        c, "03:atm_sign", -0.08, -0.515, 2.055, 0.60, 0.22, M, "ATM", "brand_blue"
    )
    cuboid(
        c,
        "03:left_carrier",
        (-0.15, -0.492, 1.57),
        (0.51, 0.12, 0.71),
        M["body_bronze"],
        0.012,
        role="interface_panel",
        detail="bronze display/cash module carrier",
    )
    ui_screen(
        c,
        "03:screen",
        -0.17,
        -0.566,
        1.61,
        0.40,
        0.38,
        M,
        "black",
        False,
        "SELECT TRANSACTION",
    )
    front_panel(
        c,
        "03:screen_nameplate",
        -0.17,
        -0.588,
        1.355,
        0.22,
        0.045,
        M["paper"],
        0.004,
        role="equipment_label",
        detail="display manufacturer plate",
    )
    transaction_slot(c, "03:cash", -0.17, -0.567, 1.245, 0.39, 0.070, M, deep=0.055)
    cuboid(
        c,
        "03:io_tower",
        (0.31, -0.484, 1.58),
        (0.27, 0.13, 1.09),
        M["body_bronze"],
        0.012,
        role="io_column",
        detail="four-level bronze transaction I/O tower",
    )
    payment_logos(c, "03:logos", 0.31, -0.562, 1.970, 0.23, 0.22, M)
    transaction_slot(
        c,
        "03:receipt",
        0.31,
        -0.565,
        1.760,
        0.17,
        0.040,
        M,
        label="RECEIPT",
        paper=True,
    )
    card_reader(c, "03:card", 0.31, -0.565, 1.560, M, 0.16, 0.09, "CARD")
    transaction_slot(
        c,
        "03:check",
        0.31,
        -0.565,
        1.315,
        0.17,
        0.115,
        M,
        label="CASH / CHECK IN",
        green=True,
    )
    transaction_slot(
        c, "03:aux", 0.31, -0.565, 1.105, 0.17, 0.045, M, label="AUX", deep=0.035
    )
    prism_yz(
        c,
        "03:work_shelf",
        -0.40,
        0.40,
        [(-0.43, 1.14), (-0.72, 1.04), (-0.72, 0.93), (-0.43, 0.99)],
        M["body_bronze"],
        0.013,
        role="operator_shelf",
        detail="deep integral bronze transaction shelf",
    )
    keypad(
        c, "03:keypad", (-0.17, -0.620, 1.050), M, 0.32, 0.22, math.radians(11), True
    )
    tube(
        c,
        "03:right_shelf_lip",
        [
            (0.23, -0.713, 0.985),
            (0.29, -0.733, 1.00),
            (0.39, -0.733, 1.00),
            (0.43, -0.713, 0.985),
        ],
        0.009,
        M["chrome"],
        role="operator_hardware",
        detail="right convenience shelf lip",
    )
    service_door(
        c, "03:lower_safe", 0, -0.397, 0.48, 0.84, 0.82, M, "body_bronze", "vertical"
    )
    cuboid(
        c,
        "03:base_plinth",
        (0, 0.02, 0.055),
        (0.92, 0.72, 0.11),
        M["bronze_dark"],
        0.010,
        role="service_plinth",
        detail="recessed bronze safe plinth",
    )
    seam(c, "03:waist_joint", 0, -0.430, 0.91, 0.88, M)
    for side in (-1, 1):
        side_vent_field(
            c, f"03:side_vent:{side}", side * 0.518, 0.07, 0.30, M, 8, 2, side
        )
    micro_perforation_patch(
        c,
        "03:worktop_microperforation",
        (-0.03, -0.590, 1.035),
        (1, 0, 0),
        (0, -0.965, -0.262),
        17,
        5,
        0.043,
        0.034,
        0.0027,
        M["seam"],
    )
    security_camera(c, "03:operator_camera", 0.095, -0.610, 1.905, M, 0.012)
    headphone_jack(c, "03:audio", 0.400, -0.610, 1.095, M)
    barcode_label(
        c, "03:asset_label", 0.225, -0.420, 0.620, 0.22, 0.100, M, "ATM SAFE / ID"
    )
    warning_label(
        c, "03:tamper_warning", 0.225, -0.421, 0.360, 0.20, 0.098, M, "ALARMED"
    )
    for zhinge in (0.30, 0.69):
        hinge(c, f"03:door_hinge:{zhinge}", 0.420, -0.425, zhinge, 0.16, M)
    for sx in (-1, 1):
        cuboid(
            c,
            f"03:lower_door_gasket:{sx}",
            (sx * 0.405, -0.430, 0.49),
            (0.010, 0.007, 0.72),
            M["rubber"],
            0.002,
            role="service_seal",
            detail="lower safe anti-pry perimeter seal",
        )
    floor_mount_set(c, "03:floor_mount", 0.38, 0.25, M, 0.031)
    return _finalize_variant(c, VARIANT_NAMES[3], 2, (1.05, 0.82, 2.20))


def atm_04_branded(parent, M, palette="red"):
    """Reference 4: bank-branded outdoor ATM, palette-parameterized."""
    c = collection(COLLECTION_NAMES[4], parent)
    palette = palette or "red"
    hood_key = {"red": "red", "gold": "gold", "black": "body_charcoal"}.get(
        palette, "red"
    )
    lower_key = "body_gray" if palette == "red" else "body_charcoal"
    # Widen the complete cabinet and its architectural cladding so the bank
    # name is housed by the machine rather than hanging outside its silhouette.
    cuboid(
        c,
        "04:security_carcass",
        (0, 0.02, 1.08),
        (0.96, 0.68, 2.16),
        M["body_charcoal"],
        0.022,
        role="structural_cabinet",
        detail="wide high-security outdoor ATM carcass",
    )
    cuboid(
        c,
        "04:side_skin_left",
        (-0.475, 0.02, 1.02),
        (0.035, 0.65, 1.96),
        M[lower_key],
        0.008,
        role="cabinet_skin",
        detail="replaceable side cladding skin",
    )
    cuboid(
        c,
        "04:side_skin_right",
        (0.475, 0.02, 1.02),
        (0.035, 0.65, 1.96),
        M[lower_key],
        0.008,
        role="cabinet_skin",
        detail="replaceable side cladding skin",
    )
    cuboid(
        c,
        "04:plinth",
        (0, 0.03, 0.10),
        (1.04, 0.72, 0.20),
        M["black"],
        0.015,
        role="service_plinth",
        detail="wide anti-tip service plinth",
    )
    add_brand_lightbox(
        c,
        "04:brand",
        0,
        -0.265,
        2.18,
        0.98,
        0.30,
        M,
        "INTERWORLD\nBANK",
        "paper",
        text_size=0.108,
        text_offset_x=0.075,
        text_max_width=0.68,
    )
    cuboid(
        c,
        "04:hood_header",
        (0, -0.382, 1.825),
        (0.90, 0.25, 0.18),
        M[hood_key],
        0.014,
        role="protective_hood",
        detail="bank-color projecting transaction hood header",
    )
    for sx in (-1, 1):
        prism_yz(
            c,
            f"04:hood_cheek:{sx}",
            sx * 0.45,
            sx * 0.36,
            [(-0.30, 1.21), (-0.48, 1.27), (-0.48, 1.84), (-0.30, 1.91)],
            M[hood_key],
            0.010,
            role="protective_hood",
            detail="bank-color projecting side hood",
        )
    front_panel(
        c,
        "04:alcove_back",
        0,
        -0.358,
        1.54,
        0.67,
        0.62,
        M["black"],
        0.012,
        role="operator_recess",
        detail="deep weather-protected black operator alcove",
    )
    for sx in (-0.27, 0.27):
        cylinder(
            c,
            f"04:downlight:{sx}",
            (sx, -0.513, 1.835),
            0.035,
            0.018,
            M["warm_light"],
            rot=(math.pi / 2, 0, 0),
            vertices=40,
            role="task_light",
            detail="recessed circular hood downlight",
        )
        cylinder(
            c,
            f"04:downlight_trim:{sx}",
            (sx, -0.500, 1.835),
            0.048,
            0.014,
            M["chrome"],
            rot=(math.pi / 2, 0, 0),
            vertices=40,
            role="task_light_housing",
            detail="downlight trim ring",
        )
    ui_screen(
        c,
        "04:screen",
        -0.035,
        -0.481,
        1.590,
        0.37,
        0.30,
        M,
        "black",
        True,
        "BANK SERVICES",
    )
    transaction_slot(
        c, "04:receipt", -0.205, -0.475, 1.335, 0.12, 0.040, M, paper=True, deep=0.032
    )
    front_panel(
        c,
        "04:status_display",
        -0.035,
        -0.477,
        1.335,
        0.14,
        0.065,
        M["screen_blue"],
        0.006,
        role="status_display",
        detail="secondary blue transaction status display",
    )
    for i in range(2):
        front_panel(
            c,
            f"04:status_line:{i}",
            -0.035,
            -0.494,
            1.345 - i * 0.020,
            0.09,
            0.006,
            M["screen_cyan"],
            0.001,
            role="screen_ui",
            detail="secondary status-display graphic",
        )
    status_lamp(c, "04:card_indicator", 0.205, -0.488, 1.335, M, "green", 0.038)
    transaction_slot(c, "04:audio", -0.245, -0.472, 1.235, 0.055, 0.055, M, deep=0.024)
    cylinder(
        c,
        "04:help_button",
        (0.245, -0.493, 1.235),
        0.034,
        0.020,
        M["chrome"],
        rot=(math.pi / 2, 0, 0),
        role="accessibility_control",
        detail="raised assistance button",
    )
    prism_yz(
        c,
        "04:cash_fascia",
        -0.29,
        0.29,
        [(-0.31, 1.20), (-0.49, 1.14), (-0.49, 1.00), (-0.31, 0.96)],
        M[hood_key],
        0.012,
        role="cash_dispenser",
        detail="projecting weather-protected cash fascia",
    )
    transaction_slot(
        c, "04:cash", 0, -0.505, 1.075, 0.38, 0.075, M, green=False, deep=0.055
    )
    front_panel(
        c,
        "04:lower_skin",
        0,
        -0.328,
        0.60,
        0.83,
        0.68,
        M[lower_key],
        0.009,
        role="service_door",
        detail="replaceable lower bank-color service skin",
    )
    instruction_placard(
        c,
        "04:transaction_guide",
        0.04,
        -0.351,
        0.66,
        0.39,
        0.25,
        M,
        warning=False,
        qr=True,
    )
    tube(
        c,
        "04:vertical_door_handle",
        [
            (-0.365, -0.365, 0.48),
            (-0.388, -0.390, 0.54),
            (-0.388, -0.390, 0.74),
            (-0.365, -0.365, 0.80),
        ],
        0.012,
        M["chrome"],
        role="service_handle",
        detail="long vertical service-door pull",
    )
    seam(c, "04:lower_top_seam", 0, -0.350, 0.94, 0.83, M)
    seam(c, "04:lower_bottom_seam", 0, -0.350, 0.26, 0.83, M)
    for sx in (-1, 1):
        fastener(c, f"04:lower_fastener:{sx}:a", sx * 0.38, -0.359, 0.89, M, 0.009)
        fastener(c, f"04:lower_fastener:{sx}:b", sx * 0.38, -0.359, 0.32, M, 0.009)
    security_camera(c, "04:operator_camera", 0, -0.510, 1.825, M, 0.011)
    text_front(
        c,
        "04:contactless_mark",
        ")))",
        (0.205, -0.514, 1.385),
        0.020,
        M["ui_muted"],
        0.00010,
        role="accessibility_detail",
    )
    headphone_jack(c, "04:audio_jack", -0.245, -0.503, 1.235, M)
    barcode_label(
        c, "04:service_serial", 0.115, -0.354, 0.405, 0.27, 0.080, M, "TERMINAL / ID"
    )
    warning_label(
        c, "04:security_warning", 0.115, -0.354, 0.305, 0.24, 0.068, M, "24H MONITORED"
    )
    for side in (-1, 1):
        side_vent_field(
            c, f"04:side_vent:{side}", side * 0.486, 0.08, 0.42, M, 6, 1, side
        )
    for zhinge in (0.42, 0.78):
        hinge(c, f"04:door_hinge:{zhinge}", 0.402, -0.352, zhinge, 0.13, M)
    cylinder(
        c,
        "04:brand_roundel",
        (-0.355, -0.378, 2.185),
        0.055,
        0.010,
        M["brand_blue"],
        rot=(math.pi / 2, 0, 0),
        vertices=64,
        bevel=0.002,
        role="brand_face",
        detail="bank emblem on illuminated sign fascia",
    )
    torus(
        c,
        "04:brand_roundel_ring",
        (-0.355, -0.386, 2.185),
        0.036,
        0.004,
        M["white"],
        role="brand_face",
        detail="fine bank-emblem ring",
    )
    micro_perforation_patch(
        c,
        "04:cash_bezel_microtexture",
        (0, -0.516, 1.075),
        (1, 0, 0),
        (0, 0, 1),
        19,
        2,
        0.018,
        0.018,
        0.0012,
        M["seam"],
    )
    floor_mount_set(c, "04:floor_mount", 0.40, 0.24, M, 0.030)
    c["palette"] = palette
    c["supported_palettes"] = ["black", "gold", "red"]
    return _finalize_variant(c, VARIANT_NAMES[4], 3, (1.04, 0.74, 2.33))


ATM_FACTORIES = (
    atm_01a_silver_freestanding,
    atm_01b_silver_through_wall,
    atm_02_white_oxford,
    atm_03_bronze,
    atm_04_branded,
)


def _resolve_variant(variant):
    if isinstance(variant, str):
        try:
            return VARIANT_NAMES.index(variant)
        except ValueError as exc:
            raise ValueError(
                f"Unknown ATM variant {variant!r}; expected one of {VARIANT_NAMES}"
            ) from exc
    if not isinstance(variant, int) or not 0 <= variant < len(ATM_FACTORIES):
        raise ValueError(
            f"ATM variant must be an integer 0..{len(ATM_FACTORIES)-1} or a canonical name"
        )
    return variant


def _transform_collection(coll, location=(0.0, 0.0, 0.0), rotation=0.0):
    matrix = Matrix.Translation(Vector(location)) @ Matrix.Rotation(rotation, 4, "Z")
    for obj in coll.all_objects:
        obj.matrix_world = matrix @ obj.matrix_world


def _snap_collection_to_floor(coll):
    """Normalize the local asset origin to its real contact patch at Z=0."""
    bbox = _collection_bbox(coll)
    if bbox is None:
        return 0.0
    offset = -bbox[0].z
    if abs(offset) > 1e-7:
        shift = Matrix.Translation(Vector((0, 0, offset)))
        for obj in coll.all_objects:
            obj.matrix_world = shift @ obj.matrix_world
    coll["ground_snap_offset_m"] = offset
    coll["local_floor_z"] = 0.0
    return offset


def build_atm(
    parent,
    variant,
    x=0.0,
    y=0.0,
    z=0.0,
    rotation=0.0,
    materials_override=None,
    palette=None,
):
    """Pipeline factory for one high-detail ATM.

    ``variant`` accepts either an index in ``0..4`` or a canonical name from
    :data:`VARIANT_NAMES`. ``palette`` affects the reference-4 terminal and
    accepts ``"black"``, ``"gold"``, or ``"red"``.
    """
    idx = _resolve_variant(variant)
    M = materials_override or materials()
    coll = ATM_FACTORIES[idx](parent, M, palette)
    _snap_collection_to_floor(coll)
    _transform_collection(coll, (x, y, z), rotation)
    coll[
        "factory_api"
    ] = "build_atm(parent, variant, x, y, z, rotation, materials_override, palette)"
    coll["placement_origin"] = [x, y, z]
    coll["placement_rotation"] = rotation
    coll["grounded"] = True
    return coll


# -----------------------------------------------------------------------------
# Daylight validation scene, cameras, rendering and audit
# -----------------------------------------------------------------------------


def camera(name, loc, target, lens=56, dof=False):
    data = bpy.data.cameras.new(PREFIX + name)
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    data.lens = lens
    data.sensor_width = 36
    if dof:
        data.dof.use_dof = True
        data.dof.focus_distance = (Vector(target) - Vector(loc)).length
        data.dof.aperture_fstop = 7.1
    tag(obj, "validation_camera", "daylight close/wide validation camera")
    return obj


def setup_daylight(M):
    scene = bpy.context.scene
    world = bpy.data.worlds.new(PREFIX + "daylight_world")
    world.use_nodes = True
    scene.world = world
    nodes, links = world.node_tree.nodes, world.node_tree.links
    bg = world.node_tree.nodes.get("Background")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(34)
    sky.sun_rotation = math.radians(138)
    sky.altitude = 0.25
    sky.air_density = 1.05
    sky.dust_density = 0.72
    sky.ozone_density = 1.0
    links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.34
    ground_mat = concrete_material("atm3_presentation_pavement", (0.255, 0.275, 0.285))
    cuboid(
        scene.collection,
        "presentation:ground",
        (0, 0.45, -0.055),
        (15.0, 5.8, 0.11),
        ground_mat,
        0.012,
        role="presentation_context",
        detail="neutral daylight validation pavement",
    )
    wall_mat = concrete_material("atm3_presentation_wall", (0.38, 0.405, 0.415))
    cuboid(
        scene.collection,
        "presentation:backdrop",
        (0, 1.55, 2.20),
        (15.0, 0.12, 4.5),
        wall_mat,
        0.010,
        role="presentation_context",
        detail="neutral architectural concrete validation wall",
    )
    # Real-scale formwork and expansion joints keep the neutral context from
    # reading as an unshaded toy slab while remaining visually subordinate.
    for xx in (-4.9, -2.45, 0, 2.45, 4.9):
        cuboid(
            scene.collection,
            f"presentation:wall_joint_x:{xx}",
            (xx, 1.482, 2.20),
            (0.010, 0.008, 4.35),
            M["seam"],
            0.001,
            role="presentation_context",
            detail="architectural concrete formwork joint",
        )
    cuboid(
        scene.collection,
        "presentation:wall_joint_z",
        (0, 1.482, 2.18),
        (14.7, 0.008, 0.010),
        M["seam"],
        0.001,
        role="presentation_context",
        detail="horizontal concrete formwork joint",
    )
    for xx in (-3.75, 0, 3.75):
        cuboid(
            scene.collection,
            f"presentation:floor_joint:{xx}",
            (xx, -0.25, 0.004),
            (0.011, 3.25, 0.004),
            M["seam"],
            0.001,
            role="presentation_context",
            detail="sawn concrete expansion joint",
        )
    bpy.ops.object.light_add(type="SUN", location=(-7, -8, 11))
    sun = bpy.context.object
    sun.name = PREFIX + "day_sun"
    sun.data.energy = 2.15
    sun.data.angle = math.radians(3.8)
    sun.rotation_euler = (math.radians(36), math.radians(-18), math.radians(-31))
    tag(sun, "daylight", "broad warm daylight sun")
    for name, loc, energy, size, color in (
        ("sky_fill", (-5, -4, 7), 640, 5.5, (0.72, 0.84, 1.0)),
        ("front_fill", (5, -5, 4), 360, 4.0, (1.0, 0.92, 0.78)),
    ):
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = PREFIX + name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        light.rotation_euler = (
            (Vector((0, 0, 1.15)) - light.location).to_track_quat("-Z", "Y").to_euler()
        )
        tag(light, "daylight", "daylight-balanced soft fill")


def render_views(cameras):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 40
    scene.eevee.use_gtao = True
    scene.eevee.gtao_quality = 1.35
    scene.eevee.gtao_distance = 2.6
    scene.eevee.shadow_ray_count = 3
    scene.eevee.shadow_step_count = 6
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1050
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 18
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        pass
    scene.view_settings.exposure = 0.20
    for filename, cam in cameras:
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def _collection_bbox(coll):
    points = []
    for obj in coll.all_objects:
        if obj.type not in {"MESH", "CURVE", "FONT"}:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    lo = Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    hi = Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return lo, hi


def _object_bbox(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lo = Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    hi = Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return lo, hi


def audit(root, cameras):
    variants = [
        c for c in root.children if c.get("c2w_asset_kind") == "street_furniture.atm"
    ]
    records = []
    for coll in variants:
        roles = {
            str(obj.get("c2w_role", ""))
            for obj in coll.all_objects
            if obj.get("c2w_role")
        }
        meshes = [obj for obj in coll.all_objects if obj.type == "MESH"]
        curves = [obj for obj in coll.all_objects if obj.type in {"CURVE", "FONT"}]
        custom = [obj for obj in meshes if obj.get("c2w_geometry")]
        material_names = {
            slot.material.name
            for obj in coll.all_objects
            for slot in obj.material_slots
            if slot.material
        }
        poly_count = sum(len(obj.data.polygons) for obj in meshes)
        modifier_count = sum(len(obj.modifiers) for obj in meshes)
        bbox = _collection_bbox(coll)
        dims = list((bbox[1] - bbox[0]) if bbox else Vector((0, 0, 0)))
        records.append(
            {
                "collection": coll.name,
                "variant": coll.get("variant"),
                "reference_index": coll.get("reference_index"),
                "reference_url": coll.get("reference_url"),
                "object_count": len(coll.all_objects),
                "mesh_count": len(meshes),
                "curve_or_font_count": len(curves),
                "polygon_count_before_modifiers": poly_count,
                "modifier_count": modifier_count,
                "material_count": len(material_names),
                "custom_profile_count": len(custom),
                "dimensions_m": [round(v, 3) for v in dims],
                "floor_min_z_m": round(bbox[0].z, 5) if bbox else None,
                "floor_contact_error_mm": round(abs(bbox[0].z) * 1000, 3)
                if bbox
                else None,
                "role_count": len(roles),
                "roles": sorted(roles),
            }
        )
    required_roles = {
        "structural_cabinet",
        "operator_recess",
        "display",
        "functional_slot",
        "panel_seam",
        "fastener",
        "slot_mechanism",
        "screen_gasket",
        "serial_label",
        "ground_contact",
        "floor_anchor",
        "surface_detail",
    }
    branded = next(c for c in variants if c.get("variant") == VARIANT_NAMES[4])
    brand_text = next(
        o for o in branded.all_objects if o.name == PREFIX + "04:brand:text"
    )
    brand_face = next(
        o for o in branded.all_objects if o.name == PREFIX + "04:brand:face"
    )
    text_bbox = _object_bbox(brand_text)
    face_bbox = _object_bbox(brand_face)
    white = next(c for c in variants if c.get("variant") == VARIANT_NAMES[2])
    white_red_arrow_parts = [
        o.name for o in white.all_objects if "02:no_envelope:arrow_" in o.name
    ]
    checks = {
        "all_five_structurally_distinct_models": len(variants) == 5
        and {c.get("variant") for c in variants} == set(VARIANT_NAMES),
        "all_four_references_covered": {c.get("reference_url") for c in variants}
        == set(REFERENCES),
        "reference_1_both_forms_modeled": sum(
            c.get("reference_index") == 1 for c in variants
        )
        == 2,
        "every_model_has_full_mechanical_interface": all(
            required_roles.issubset(set(r["roles"]))
            and ({"keypad_key", "screen_softkey"} & set(r["roles"]))
            for r in records
        ),
        "dense_non_toy_geometry": all(
            r["object_count"] >= 145
            and r["mesh_count"] >= 110
            and r["polygon_count_before_modifiers"] >= 2200
            for r in records
        ),
        "fine_detail_and_material_separation": all(
            r["role_count"] >= 30
            and r["material_count"] >= 18
            and r["curve_or_font_count"] >= 12
            for r in records
        ),
        "formed_sheet_metal_profiles_present": all(
            r["custom_profile_count"] >= 5 for r in records
        ),
        "physically_plausible_scale": all(
            0.65 <= r["dimensions_m"][0] <= 1.35
            and 1.55 <= r["dimensions_m"][2] <= 2.50
            for r in records
        ),
        "all_assets_touch_floor": all(
            r["floor_contact_error_mm"] <= 0.25 and "ground_contact" in r["roles"]
            for r in records
        ),
        "daylight_near_and_far_multiview": len(cameras) >= 8
        and sum("wide" in n for n, _ in cameras) >= 3,
        "source_generator_is_pipeline_factory": callable(build_atm)
        and len(ATM_FACTORIES) == 5,
        "reference_4_palette_family_supported": set(
            next(c for c in variants if c.get("variant") == VARIANT_NAMES[4]).get(
                "supported_palettes", []
            )
        )
        == {"black", "gold", "red"},
        "reference_4_brand_text_inside_sign_face": text_bbox[0].x
        >= face_bbox[0].x + 0.010
        and text_bbox[1].x <= face_bbox[1].x - 0.010,
        "reference_2_red_three_stroke_arrow_removed": not white_red_arrow_parts,
        "no_external_model_or_blend_dependency": True,
    }
    data = {
        "generator": str(Path(__file__).resolve()),
        "generator_version": GENERATOR_VERSION,
        "output": str(OUT),
        "references": REFERENCES,
        "variant_count": len(variants),
        "variants": records,
        "views": [n for n, _ in cameras],
        "lighting": "Nishita daylight plus sun and soft fill",
        "row_layout": True,
        "standalone_test_contains_only_atm_assets_plus_neutral_presentation_context": True,
        "pipeline_entry": str(Path(__file__).resolve()),
        "factory_api": "build_atm(parent, variant, x, y, z, rotation, materials_override, palette)",
        "canonical_variants": list(VARIANT_NAMES),
        "collection_names": [PREFIX + n for n in COLLECTION_NAMES],
        "ground_plane_z_m": 0.0,
        "geometry_policy": "procedural meshes/curves only; no external model dependency",
        "requested_corrections": {
            "red_atm_widened": True,
            "red_atm_brand_text_bounds_x_m": [
                round(text_bbox[0].x, 4),
                round(text_bbox[1].x, 4),
            ],
            "red_atm_brand_face_bounds_x_m": [
                round(face_bbox[0].x, 4),
                round(face_bbox[1].x, 4),
            ],
            "white_atm_red_three_stroke_arrow_object_count": len(white_red_arrow_parts),
        },
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not data["all_checks_passed"]:
        raise RuntimeError(
            f"ATM production audit failed: {json.dumps(checks,indent=2)}"
        )
    (OUT / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    G.reset_scene()
    M = materials()
    root = collection("FIVE_REFERENCE_ATMS")
    xs = (-3.36, -1.68, 0.0, 1.68, 3.36)
    palettes = (None, None, None, None, "red")
    for i, (x, palette) in enumerate(zip(xs, palettes)):
        build_atm(root, i, x=x, palette=palette, materials_override=M)
    setup_daylight(M)
    specs = [
        ("01_atm_row_front_wide.png", (0, -12.4, 2.48), (0, 0, 1.11), 52, False),
        (
            "02_atm_row_right_oblique_wide.png",
            (7.7, -9.7, 3.05),
            (0, 0, 1.08),
            55,
            False,
        ),
        ("03_atm_row_left_low_wide.png", (-7.6, -9.5, 2.00), (0, 0, 1.05), 56, False),
        (
            "04_atm_01a_silver_floor_close.png",
            (-2.82, -3.80, 2.15),
            (-3.36, -0.03, 1.20),
            70,
            True,
        ),
        (
            "05_atm_01b_silver_wall_close.png",
            (-2.00, -3.45, 1.92),
            (-1.68, -0.03, 1.24),
            72,
            True,
        ),
        ("06_atm_02_white_close.png", (-0.34, -3.36, 1.91), (0, -0.03, 1.24), 72, True),
        (
            "07_atm_03_bronze_close.png",
            (2.10, -3.65, 2.13),
            (1.68, -0.03, 1.18),
            72,
            True,
        ),
        (
            "08_atm_04_branded_close.png",
            (3.04, -3.40, 2.08),
            (3.36, -0.03, 1.22),
            74,
            True,
        ),
    ]
    cameras = [
        (fn, camera(fn[:-4], loc, target, lens, dof))
        for fn, loc, target, lens, dof in specs
    ]
    data = audit(root, cameras)
    scene = bpy.context.scene
    scene.camera = cameras[0][1]
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_asset_factory"] = "build_atm"
    scene["c2w_asset_variants"] = json.dumps(VARIANT_NAMES)
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    render_views(cameras)
    # Save after render configuration is applied so reopening the asset file
    # preserves the exact validated daylight resolution/color settings.
    bpy.ops.wm.save_as_mainfile(
        filepath=str(OUT / "urban_v3_atm4.blend"), compress=True
    )
    (OUT / "SUCCESS").write_text(
        "urban_v3_atm4 production procedural generation, audit, pipeline asset save, and daylight renders complete\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
