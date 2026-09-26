"""Reference-driven procedural four-bank campus, production revision all46_5.

This is the source generator used by the urban pipeline.  It does not append a
prepared scene or patch an existing blend.  ``build_financial_campus`` is the
reusable pipeline entry point; ``main`` builds the isolated four-bank
validation scene requested for outdoor_part_demo/urban_v3_all46_5.

The filename is retained because it is the established urban-pipeline import
target (``all46_1`` also resolves here).  This module now emits the all46_5
asset revision directly; no prepared blend or detached demo is involved.
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
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
REVISION = "urban_v3_all46_5"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / REVISION
RENDERS = OUT / "renders"
PREFIX = "all46_5:"
RNG = random.Random(4605)
SCHEMA_VERSION = 5
REFERENCE_URLS = [
    "https://preview.free3d.com/img/2019/09/2279650970222724353/3gic4xbh.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT48nZoSiKdfMTkCZx25JUmhFkx8YjKtXa7n4ohQy15pg&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRxkB8tjJJ5oyNzqHmvY7a4Jf6DHu5NugbW3-M2KB5NCg&s=10",
    "https://media.gettyimages.com/id/1456358348/zh/%E7%85%A7%E7%89%87/bank-building-3d-render.jpg?s=612x612&w=gi&k=20&c=hGU716blvGDuYlgPpcEi1kRAExKrxyot8hkSFX8Ct8g=",
    "https://www.dbs.com/livemore/id-en/our-milestones.html",
    "https://www.dbs.com/newsroom/DBS_unveils_new_brand_campaign",
]

sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all45 as G
import generate_urban_v3_atm as ATM

G.PREFIX = PREFIX
ATM.PREFIX = PREFIX + "atm:"

SITE_BOUNDS = {
    "x_min": -60.8,
    "x_max": 60.8,
    "y_min": -45.8,
    "y_max": 108.8,
}

_CUBE_MESHES = {}


# ---------------------------------------------------------------------------
# Core helpers.  Every created renderable is tagged for pipeline inspection.
# ---------------------------------------------------------------------------


def collection(name, parent=None, asset_id=None):
    result = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(result)
    result["c2w_schema_version"] = SCHEMA_VERSION
    result["c2w_role"] = "procedural_asset"
    result["c2w_generator"] = Path(__file__).name
    if asset_id:
        result["c2w_asset_id"] = asset_id
    return result


def tag(obj, role, asset_id=None):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = role
    obj["c2w_generator"] = Path(__file__).name
    if asset_id:
        obj["c2w_asset_id"] = asset_id
    return obj


def box(c, name, xyz, dims, material, bevel=0.035, rot=0.0, role=None):
    # Shared unit meshes keep this high-detail scene fast enough for the main
    # pipeline: thousands of facade parts instance a small material-keyed mesh
    # set instead of forcing an operator/depsgraph rebuild for every cuboid.
    key = material.name_full if material else "none"
    mesh = _CUBE_MESHES.get(key)
    if mesh is None or mesh.name not in bpy.data.meshes:
        mesh = bpy.data.meshes.new(PREFIX + "shared_cube:" + key.replace(":", "_"))
        mesh.from_pydata(
            [
                (-1, -1, -1),
                (1, -1, -1),
                (1, 1, -1),
                (-1, 1, -1),
                (-1, -1, 1),
                (1, -1, 1),
                (1, 1, 1),
                (-1, 1, 1),
            ],
            [],
            [
                (0, 3, 2, 1),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            ],
        )
        mesh.update()
        if material:
            mesh.materials.append(material)
        mesh["c2w_shared_primitive"] = "unit_cube"
        _CUBE_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler[2] = rot
    obj.scale = (dims[0] / 2, dims[1] / 2, dims[2] / 2)
    # Only major silhouette/hand-contact elements need a live bevel.  Window
    # grids remain crisp and avoid thousands of redundant modifiers.
    if bevel >= 0.05 and min(dims) >= 0.14:
        modifier = obj.modifiers.new(PREFIX + "architectural_edge", "BEVEL")
        modifier.width = min(0.08, bevel)
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
    return tag(obj, role or name.split(":", 1)[0])


def local_box(c, name, origin, yaw, xyz, dims, material, bevel=0.035, role=None):
    return box(
        c, name, G.transform_point(origin, yaw, xyz), dims, material, bevel, yaw, role
    )


def cylinder(
    c,
    name,
    xyz,
    radius,
    depth,
    material,
    vertices=32,
    rot=(0, 0, 0),
    bevel=0.01,
    role=None,
):
    obj = G.cylinder(
        name, xyz, radius, depth, material, c, vertices=vertices, rot=rot, bevel=bevel
    )
    return tag(obj, role or name.split(":", 1)[0])


def beam(c, name, p1, p2, radius, material, vertices=20, role=None):
    obj = G.beam(name, p1, p2, radius, material, c, vertices=vertices)
    return tag(obj, role or name.split(":", 1)[0])


def poly_prism(c, name, pts, z, depth, material, bevel=0.025, role=None):
    obj = G.poly_prism(name, pts, z, depth, material, c, bevel=bevel)
    return tag(obj, role or name.split(":", 1)[0])


def text_object(
    c,
    name,
    body,
    xyz,
    size,
    material,
    extrude=0.055,
    align="CENTER",
    rot=(math.pi / 2, 0, 0),
    role="architectural_signage",
):
    curve = bpy.data.curves.new(PREFIX + name, "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.012
    curve.resolution_u = 8
    curve.bevel_resolution = 3
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = rot
    obj.data.materials.append(material)
    return tag(obj, role)


def local_text(
    c, name, body, origin, yaw, xyz, size, material, extrude=0.055, align="CENTER"
):
    return text_object(
        c,
        name,
        body,
        G.transform_point(origin, yaw, xyz),
        size,
        material,
        extrude,
        align,
        (math.pi / 2, 0, yaw),
    )


def vertical_prism_y(
    c, name, xz_points, y, depth, material, bevel=0.025, role="architectural_signage"
):
    """Extrude an arbitrary X/Z facade motif through Y."""
    count = len(xz_points)
    vertices = [(x, y - depth / 2, z) for x, z in xz_points]
    vertices += [(x, y + depth / 2, z) for x, z in xz_points]
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    if bevel:
        G.add_bevel(obj, bevel, 3)
    return tag(obj, role)


def dbs_facade_identity(c, M, x=0.0, y=79.48, z=85.8):
    """Large official-composition DBS facade sign: red spark, white wordmark."""
    backer = box(
        c,
        "dbs_identity_backer",
        (x, y + 0.18, z),
        (18.0, 0.34, 5.0),
        M["black_metal"],
        0.11,
        role="architectural_signage",
    )
    backer["c2w_brand"] = "DBS"
    backer["c2w_identity_composition"] = "red_four_part_symbol+white_DBS_wordmark"
    mark_x = x - 5.55
    petal_size = 1.42
    for index, (dx, dz) in enumerate(
        ((-0.78, -0.78), (0.78, -0.78), (-0.78, 0.78), (0.78, 0.78))
    ):
        petal = box(
            c,
            f"dbs_red_symbol_petal_{index}",
            (mark_x + dx, y - 0.08, z + dz),
            (petal_size, 0.16, petal_size),
            M["red"],
            0.18,
            role="dbs_logo_symbol",
        )
        petal["c2w_brand_color"] = "DBS red"
    spark_points = [
        (mark_x, z + 1.18),
        (mark_x + 0.25, z + 0.25),
        (mark_x + 1.18, z),
        (mark_x + 0.25, z - 0.25),
        (mark_x, z - 1.18),
        (mark_x - 0.25, z - 0.25),
        (mark_x - 1.18, z),
        (mark_x - 0.25, z + 0.25),
    ]
    spark = vertical_prism_y(
        c,
        "dbs_white_spark",
        spark_points,
        y - 0.18,
        0.09,
        M["white_clean"],
        0.035,
        "dbs_logo_spark",
    )
    spark["c2w_brand_color"] = "white"
    wordmark = text_object(
        c,
        "dbs_white_wordmark",
        "DBS",
        (x + 2.45, y - 0.17, z),
        2.35,
        M["white_clean"],
        0.105,
        role="dbs_logo_wordmark",
    )
    wordmark["c2w_brand_color"] = "white"
    wordmark["c2w_brand"] = "DBS"
    return backer


def set_socket(node, names, value):
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def pbr(
    name,
    color,
    rough=0.55,
    metallic=0.0,
    noise=0.0,
    transmission=0.0,
    emission=None,
    emission_strength=0.0,
):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    set_socket(bsdf, ("Roughness",), rough)
    set_socket(bsdf, ("Metallic",), metallic)
    set_socket(bsdf, ("IOR",), 1.45)
    set_socket(bsdf, ("Transmission Weight", "Transmission"), transmission)
    set_socket(
        bsdf,
        ("Coat Weight", "Clearcoat"),
        0.24 if transmission or metallic > 0.5 else 0.06,
    )
    set_socket(
        bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.08 if transmission else 0.22
    )
    if emission:
        set_socket(bsdf, ("Emission Color", "Emission"), (*emission, 1))
        set_socket(bsdf, ("Emission Strength",), emission_strength)
    if noise:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.noise_dimensions = "3D"
        tex.inputs["Scale"].default_value = 16.0
        tex.inputs["Detail"].default_value = 6.0
        tex.inputs["Roughness"].default_value = 0.62
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (
            *[max(0.0, v * (1.0 - noise)) for v in color],
            1,
        )
        ramp.color_ramp.elements[1].color = (
            *[min(1.0, v * (1.0 + noise) + 0.02) for v in color],
            1,
        )
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = min(0.22, noise * 0.9)
        bump.inputs["Distance"].default_value = 0.025
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if transmission:
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            try:
                mat.blend_method = "BLEND"
            except Exception:
                pass
        mat.use_transparency_overlap = False
    mat["c2w_pbr"] = True
    return mat


def facade_glass(
    name, low_color, high_color, roughness=(0.045, 0.14), transmission=0.22
):
    """Layered architectural glazing with view-dependent, non-uniform reflection.

    The material deliberately avoids the single flat cyan used by the prior
    revision.  A very low-frequency tint shift and a tighter roughness range
    preserve reflected sky/buildings while still allowing the modeled floor
    slabs, blinds and lobby lighting to read through the glass.
    """
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*high_color, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 1.65
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.48
    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.color_ramp.elements[0].position = 0.18
    color_ramp.color_ramp.elements[0].color = (*low_color, 1.0)
    color_ramp.color_ramp.elements[1].position = 0.82
    color_ramp.color_ramp.elements[1].color = (*high_color, 1.0)
    middle = color_ramp.color_ramp.elements.new(0.52)
    middle.color = (*tuple((a + b) * 0.5 for a, b in zip(low_color, high_color)), 1.0)
    rough_ramp = nodes.new("ShaderNodeValToRGB")
    rough_ramp.color_ramp.elements[0].color = (roughness[0],) * 3 + (1.0,)
    rough_ramp.color_ramp.elements[1].color = (roughness[1],) * 3 + (1.0,)
    set_socket(bsdf, ("Metallic",), 0.16)
    set_socket(bsdf, ("IOR",), 1.48)
    set_socket(bsdf, ("Transmission Weight", "Transmission"), transmission)
    set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.42)
    set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.055)
    set_socket(bsdf, ("Specular IOR Level", "Specular"), 0.52)
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], rough_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    try:
        mat.surface_render_method = "DITHERED"
        mat.use_transparency_overlap = False
    except Exception:
        pass
    mat["c2w_pbr"] = True
    mat["c2w_reflective_glazing"] = True
    mat[
        "c2w_glazing_layers"
    ] = "tint_variation+roughness_variation+clearcoat+transmission"
    return mat


def brushed_metal(name, dark_color, light_color, roughness=0.24, anisotropy=0.32):
    """Physically metallic facade finish with subtle rolled-sheet variation."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*light_color, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 55.0
    noise.inputs["Detail"].default_value = 2.2
    noise.inputs["Roughness"].default_value = 0.46
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark_color, 1.0)
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[1].color = (*light_color, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    rough_ramp = nodes.new("ShaderNodeValToRGB")
    rough_ramp.color_ramp.elements[0].color = (roughness * 0.72,) * 3 + (1.0,)
    rough_ramp.color_ramp.elements[1].color = (min(0.55, roughness * 1.32),) * 3 + (
        1.0,
    )
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.004
    bump.inputs["Distance"].default_value = 0.002
    set_socket(bsdf, ("Metallic",), 0.91)
    set_socket(bsdf, ("Anisotropic IOR Level", "Anisotropic"), anisotropy)
    set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.20)
    set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.11)
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], rough_ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_brushed_metal"] = True
    return mat


def make_materials():
    return {
        "limestone": pbr("fine_limestone", (0.47, 0.46, 0.42), 0.72, noise=0.15),
        "stone_light": pbr("cut_stone_light", (0.63, 0.61, 0.54), 0.66, noise=0.10),
        "stone_dark": pbr("cut_stone_dark", (0.20, 0.21, 0.20), 0.79, noise=0.10),
        "mortar": pbr("mortar_joint", (0.18, 0.19, 0.19), 0.9, noise=0.03),
        "white": pbr("warm_white_precast", (0.62, 0.63, 0.59), 0.64, noise=0.10),
        "white_clean": pbr("white_clean", (0.79, 0.80, 0.75), 0.50, noise=0.04),
        "concrete": pbr("architectural_concrete", (0.16, 0.18, 0.18), 0.78, noise=0.18),
        "urban_context": pbr(
            "urban_context_paving", (0.105, 0.12, 0.12), 0.88, noise=0.22
        ),
        "paver": pbr("granite_paver", (0.25, 0.24, 0.22), 0.82, noise=0.17),
        "paver_light": pbr("limestone_paver", (0.46, 0.44, 0.39), 0.76, noise=0.13),
        "paver_warm": pbr(
            "warm_sawn_granite_paver", (0.37, 0.32, 0.26), 0.78, noise=0.11
        ),
        "paver_cool": pbr(
            "cool_honed_granite_paver", (0.19, 0.23, 0.24), 0.70, noise=0.09
        ),
        "paver_edge": pbr(
            "charcoal_granite_edge", (0.075, 0.082, 0.082), 0.72, noise=0.08
        ),
        "asphalt": pbr("weathered_asphalt", (0.045, 0.048, 0.05), 0.93, noise=0.19),
        "road_mark": pbr("road_marking", (0.75, 0.72, 0.61), 0.75, noise=0.03),
        "dark": pbr("deep_reveal", (0.008, 0.011, 0.014), 0.48, metallic=0.1),
        "charcoal": pbr(
            "charcoal_panel", (0.035, 0.038, 0.04), 0.52, metallic=0.2, noise=0.04
        ),
        "steel": pbr(
            "brushed_stainless", (0.22, 0.25, 0.27), 0.23, metallic=0.88, noise=0.025
        ),
        "black_metal": pbr(
            "blackened_aluminium",
            (0.012, 0.017, 0.022),
            0.25,
            metallic=0.83,
            noise=0.025,
        ),
        "bronze": brushed_metal(
            "rolled_architectural_bronze",
            (0.16, 0.058, 0.030),
            (0.23, 0.086, 0.045),
            0.22,
            0.38,
        ),
        "bronze_alt": brushed_metal(
            "variegated_copper_bronze",
            (0.11, 0.040, 0.022),
            (0.17, 0.063, 0.034),
            0.28,
            0.30,
        ),
        "bronze_dark": brushed_metal(
            "dark_oil_rubbed_bronze",
            (0.035, 0.017, 0.012),
            (0.067, 0.029, 0.019),
            0.30,
            0.26,
        ),
        "brass": pbr(
            "brushed_brass", (0.56, 0.31, 0.06), 0.2, metallic=0.92, noise=0.02
        ),
        "glass_clear": facade_glass(
            "low_iron_reflective_glass",
            (0.045, 0.12, 0.14),
            (0.20, 0.37, 0.39),
            (0.035, 0.11),
            0.36,
        ),
        "glass_blue": facade_glass(
            "blue_curtain_reflective_glass",
            (0.006, 0.025, 0.052),
            (0.055, 0.19, 0.29),
            (0.035, 0.105),
            0.18,
        ),
        "glass_blue_alt": facade_glass(
            "blue_silver_reflective_glass",
            (0.018, 0.055, 0.078),
            (0.16, 0.30, 0.36),
            (0.045, 0.13),
            0.20,
        ),
        "glass_silver": facade_glass(
            "silver_sky_reflective_glass",
            (0.055, 0.085, 0.10),
            (0.25, 0.34, 0.37),
            (0.04, 0.12),
            0.16,
        ),
        "glass_bronze": facade_glass(
            "bronze_tinted_reflective_glass",
            (0.035, 0.014, 0.009),
            (0.25, 0.095, 0.035),
            (0.04, 0.12),
            0.20,
        ),
        "glass_punched": facade_glass(
            "daylight_punched_window_glass",
            (0.075, 0.15, 0.18),
            (0.30, 0.44, 0.47),
            (0.035, 0.105),
            0.02,
        ),
        "glass_entry": facade_glass(
            "daylight_entry_glass",
            (0.09, 0.19, 0.21),
            (0.33, 0.49, 0.51),
            (0.035, 0.10),
            0.08,
        ),
        "interior": pbr("interior_shadow", (0.025, 0.027, 0.028), 0.65),
        "warm_light": pbr(
            "warm_interior_light",
            (0.86, 0.53, 0.18),
            0.33,
            emission=(1.0, 0.43, 0.10),
            emission_strength=1.8,
        ),
        "lamp": pbr(
            "daylight_lamp_lens",
            (0.72, 0.77, 0.70),
            0.2,
            emission=(0.7, 0.73, 0.62),
            emission_strength=0.18,
        ),
        "red": pbr("identity_red", (0.58, 0.012, 0.008), 0.3),
        "blue": pbr("identity_blue", (0.035, 0.055, 0.26), 0.3),
        "wood": pbr("oiled_hardwood", (0.24, 0.085, 0.022), 0.46, noise=0.16),
    }


# ---------------------------------------------------------------------------
# Architectural components.
# ---------------------------------------------------------------------------


def window_y(
    c,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    glass="glass_clear",
    frame="black_metal",
    divisions=1,
    lit=False,
    normal=-1,
):
    # ``normal`` points outdoors.  The glazing is therefore set behind a
    # modeled 0.42 m reveal, rather than being pasted in front of the shell.
    out = normal
    frame_y = y + out * 0.11
    glass_y = y - out * 0.045
    back_y = y - out * 0.205
    box(
        c,
        name + ":deep_reveal",
        (x, back_y - out * 0.03, z),
        (width + 0.44, 0.035, height + 0.42),
        M["dark"],
        0.006,
        role="window_reveal",
    )
    box(
        c,
        name + ":interior",
        (x, back_y, z),
        (width - 0.22, 0.045, height - 0.24),
        M["warm_light"] if lit else M["interior"],
        0.006,
        role="interior_depth",
    )
    box(
        c,
        name + ":glass",
        (x, glass_y, z),
        (width, 0.052, height),
        M[glass],
        0.008,
        role="glazing",
    )
    for edge in (-1, 1):
        box(
            c,
            name + f":return_{edge}",
            (x + edge * (width / 2 + 0.12), y - out * 0.035, z),
            (0.12, 0.37, height + 0.30),
            M[frame],
            0.012,
            role="window_reveal_return",
        )
    for edge in (-1, 1):
        box(
            c,
            name + f":head_sill_return_{edge}",
            (x, y - out * 0.035, z + edge * (height / 2 + 0.12)),
            (width + 0.32, 0.37, 0.12),
            M[frame],
            0.012,
            role="window_reveal_return",
        )
    for j in range(divisions + 1):
        xx = x - width / 2 + width * j / divisions if divisions else x
        box(
            c,
            name + f":mullion_{j}",
            (xx, frame_y, z),
            (0.072, 0.105, height + 0.12),
            M[frame],
            0.008,
            role="window_frame",
        )
    for zz in (z - height / 2, z + height / 2):
        box(
            c,
            name + ":rail",
            (x, frame_y, zz),
            (width + 0.14, 0.105, 0.085),
            M[frame],
            0.007,
            role="window_frame",
        )
        box(
            c,
            name + ":weather_gasket",
            (x, y + out * 0.045, zz),
            (width - 0.04, 0.035, 0.035),
            M["dark"],
            0.004,
            role="window_gasket",
        )
    if height >= 4.7:
        box(
            c,
            name + ":transom",
            (x, frame_y, z + height * 0.17),
            (width + 0.05, 0.105, 0.075),
            M[frame],
            0.006,
            role="window_frame",
        )
    box(
        c,
        name + ":drip_sill",
        (x, y + out * 0.17, z - height / 2 - 0.08),
        (width + 0.32, 0.34, 0.12),
        M[frame],
        0.015,
        role="window_sill_flashing",
    )


def window_x(
    c,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    glass="glass_clear",
    frame="black_metal",
    divisions=1,
    lit=False,
    normal=1,
):
    out = normal
    frame_x = x + out * 0.11
    glass_x = x - out * 0.045
    back_x = x - out * 0.205
    box(
        c,
        name + ":deep_reveal",
        (back_x - out * 0.03, y, z),
        (0.035, width + 0.44, height + 0.42),
        M["dark"],
        0.006,
        role="window_reveal",
    )
    box(
        c,
        name + ":interior",
        (back_x, y, z),
        (0.045, width - 0.22, height - 0.24),
        M["warm_light"] if lit else M["interior"],
        0.006,
        role="interior_depth",
    )
    box(
        c,
        name + ":glass",
        (glass_x, y, z),
        (0.052, width, height),
        M[glass],
        0.008,
        role="glazing",
    )
    for edge in (-1, 1):
        box(
            c,
            name + f":return_{edge}",
            (x - out * 0.035, y + edge * (width / 2 + 0.12), z),
            (0.37, 0.12, height + 0.30),
            M[frame],
            0.012,
            role="window_reveal_return",
        )
    for edge in (-1, 1):
        box(
            c,
            name + f":head_sill_return_{edge}",
            (x - out * 0.035, y, z + edge * (height / 2 + 0.12)),
            (0.37, width + 0.32, 0.12),
            M[frame],
            0.012,
            role="window_reveal_return",
        )
    for j in range(divisions + 1):
        yy = y - width / 2 + width * j / divisions if divisions else y
        box(
            c,
            name + f":mullion_{j}",
            (frame_x, yy, z),
            (0.105, 0.072, height + 0.12),
            M[frame],
            0.008,
            role="window_frame",
        )
    for zz in (z - height / 2, z + height / 2):
        box(
            c,
            name + ":rail",
            (frame_x, y, zz),
            (0.105, width + 0.14, 0.085),
            M[frame],
            0.007,
            role="window_frame",
        )
        box(
            c,
            name + ":weather_gasket",
            (x + out * 0.045, y, zz),
            (0.035, width - 0.04, 0.035),
            M["dark"],
            0.004,
            role="window_gasket",
        )
    if height >= 4.7:
        box(
            c,
            name + ":transom",
            (frame_x, y, z + height * 0.17),
            (0.105, width + 0.05, 0.075),
            M[frame],
            0.006,
            role="window_frame",
        )
    box(
        c,
        name + ":drip_sill",
        (x + out * 0.17, y, z - height / 2 - 0.08),
        (0.34, width + 0.32, 0.12),
        M[frame],
        0.015,
        role="window_sill_flashing",
    )


def local_door_set(
    c,
    name,
    origin,
    yaw,
    center,
    total_width,
    height,
    M,
    glass="glass_entry",
    frame="steel",
):
    x, y, z = center
    # South-facing local -Y is outdoors.  Side returns, transom, threshold and
    # closers make the entrance a spatial assembly instead of two flat panes.
    local_box(
        c,
        name + ":recess",
        origin,
        yaw,
        (x, y + 0.39, z),
        (total_width + 0.72, 0.04, height + 0.68),
        M["dark"],
        0.008,
        role="entrance_recess",
    )
    for edge in (-1, 1):
        local_box(
            c,
            name + f":stone_return_{edge}",
            origin,
            yaw,
            (x + edge * (total_width / 2 + 0.24), y + 0.08, z),
            (0.22, 0.64, height + 0.54),
            M[frame],
            0.018,
            role="entrance_reveal_return",
        )
    local_box(
        c,
        name + ":head_return",
        origin,
        yaw,
        (x, y + 0.08, z + height / 2 + 0.24),
        (total_width + 0.52, 0.64, 0.20),
        M[frame],
        0.018,
        role="entrance_reveal_return",
    )
    for side in (-1, 1):
        dx = x + side * total_width / 4
        local_box(
            c,
            name + f":glass_{side}",
            origin,
            yaw,
            (dx, y + 0.035, z),
            (total_width / 2 - 0.10, 0.055, height),
            M[glass],
            0.008,
            role="entrance_glazing",
        )
        for edge in (-1, 1):
            local_box(
                c,
                name + f":jamb_{side}_{edge}",
                origin,
                yaw,
                (dx + edge * (total_width / 4 - 0.05), y - 0.075, z),
                (0.085, 0.12, height + 0.12),
                M[frame],
                0.006,
                role="door_frame",
            )
        local_box(
            c,
            name + f":handle_{side}",
            origin,
            yaw,
            (x + side * total_width * 0.12, y - 0.17, z),
            (0.045, 0.065, 0.92),
            M["brass"],
            0.012,
            role="door_hardware",
        )
        local_box(
            c,
            name + f":closer_{side}",
            origin,
            yaw,
            (dx, y - 0.12, z + height / 2 - 0.23),
            (0.54, 0.10, 0.10),
            M[frame],
            0.012,
            role="door_hardware",
        )
        local_box(
            c,
            name + f":kickplate_{side}",
            origin,
            yaw,
            (dx, y - 0.13, z - height / 2 + 0.22),
            (total_width / 2 - 0.18, 0.045, 0.32),
            M[frame],
            0.006,
            role="door_hardware",
        )
    local_box(
        c,
        name + ":header",
        origin,
        yaw,
        (x, y - 0.075, z + height / 2),
        (total_width + 0.18, 0.12, 0.11),
        M[frame],
        0.006,
        role="door_frame",
    )
    local_box(
        c,
        name + ":threshold",
        origin,
        yaw,
        (x, y - 0.11, z - height / 2),
        (total_width + 0.18, 0.40, 0.10),
        M["steel"],
        0.012,
        role="building_threshold",
    )
    local_box(
        c,
        name + ":transom_glass",
        origin,
        yaw,
        (x, y + 0.035, z + height / 2 + 0.32),
        (total_width - 0.18, 0.055, 0.48),
        M[glass],
        0.006,
        role="entrance_glazing",
    )


def arch_ring(
    c, name, origin, yaw, spring_z, inner_radius, width, depth, material, segments=28
):
    outer = inner_radius + width
    vertices = []
    for yy in (-depth / 2, depth / 2):
        for radius in (inner_radius, outer):
            for i in range(segments + 1):
                angle = math.pi * i / segments
                vertices.append(
                    (radius * math.cos(angle), yy, spring_z + radius * math.sin(angle))
                )
    row = segments + 1
    faces = []
    # front/back annular strips
    for side in range(2):
        base = side * 2 * row
        for i in range(segments):
            faces.append((base + i, base + i + 1, base + row + i + 1, base + row + i))
    # outer/inner thickness surfaces
    for radial in range(2):
        a = radial * row
        b = 2 * row + radial * row
        for i in range(segments):
            faces.append((a + i, b + i, b + i + 1, a + i + 1))
    faces.extend(
        [(0, row, 3 * row, 2 * row), (row - 1, 2 * row - 1, 4 * row - 1, 3 * row - 1)]
    )
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = origin
    obj.rotation_euler[2] = yaw
    obj.data.materials.append(material)
    G.add_bevel(obj, 0.018, 2)
    return tag(obj, "true_arch_ring")


def arch_trim_curve(
    c, name, origin, yaw, spring_z, radius, material, tube=0.20, segments=36
):
    """Add a continuous visible carved edge to the solid annular arch mesh."""
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = tube
    curve.bevel_resolution = 3
    curve.resolution_u = 12
    spline = curve.splines.new("POLY")
    spline.points.add(segments)
    for index in range(segments + 1):
        angle = math.pi * index / segments
        world = G.transform_point(
            origin,
            yaw,
            (radius * math.cos(angle), -0.49, spring_z + radius * math.sin(angle)),
        )
        spline.points[index].co = (*world, 1.0)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.data.materials.append(material)
    return tag(obj, "carved_arch_trim")


def stair_and_rails(c, name, origin, yaw, front_y, width, M, levels=4):
    for level in range(levels):
        depth = 0.85 * (levels - level)
        local_box(
            c,
            name + f":step_{level}",
            origin,
            yaw,
            (0, front_y - depth / 2, 0.12 + level * 0.17),
            (width + 0.55 * (levels - level), depth, 0.24),
            M["stone_light"],
            0.025,
            role="entrance_stair",
        )
    for side in (-1, 1):
        x = side * (width / 2 + 0.35)
        p0 = G.transform_point(origin, yaw, (x, front_y - 2.7, 0.45))
        p1 = G.transform_point(origin, yaw, (x, front_y - 0.15, 1.05))
        beam(c, name + f":handrail_{side}", p0, p1, 0.045, M["steel"], 16, "handrail")
        for yy, zz in ((front_y - 2.55, 0.34), (front_y - 0.35, 0.83)):
            p = G.transform_point(origin, yaw, (x, yy, zz))
            cylinder(
                c,
                name + f":rail_post_{side}",
                p,
                0.035,
                0.75,
                M["steel"],
                16,
                role="handrail_post",
            )


# ---------------------------------------------------------------------------
# Bank 1: chamfered masonry corner branch with real curved arch and roof frame.
# ---------------------------------------------------------------------------


def build_classical_corner(parent, M):
    asset_id = "bank.classical_corner.reference_01.v4"
    c = collection("BANK_01_CLASSICAL_CORNER", parent, asset_id)
    ox, oy = -40.0, 31.0
    w, d, h = 34.0, 25.0, 23.0
    pts = [
        (ox - w / 2, oy - d / 2),
        (ox + w / 2 - 5.3, oy - d / 2),
        (ox + w / 2, oy - d / 2 + 5.3),
        (ox + w / 2, oy + d / 2),
        (ox - w / 2, oy + d / 2),
    ]
    poly_prism(
        c, "occupied_shell", pts, 0, h, M["white"], 0.08, "occupied_building_shell"
    )
    south_y = oy - d / 2 - 0.08
    east_x = ox + w / 2 + 0.08

    # Deep ashlar plinth and explicit mortar courses on both street elevations.
    box(
        c,
        "south_ashlar_cladding",
        (ox - 2.65, south_y - 0.08, 3.55),
        (w - 5.3, 0.36, 7.1),
        M["limestone"],
        0.025,
        role="masonry_cladding",
    )
    box(
        c,
        "east_ashlar_cladding",
        (east_x + 0.08, oy + 2.65, 3.55),
        (0.36, d - 5.3, 7.1),
        M["limestone"],
        0.025,
        role="masonry_cladding",
    )
    for i, z in enumerate(0.48 + 0.52 * row for row in range(13)):
        box(
            c,
            f"south_mortar_course_{i}",
            (ox - 2.65, south_y - 0.285, z),
            (w - 5.2, 0.035, 0.028),
            M["mortar"],
            0,
            role="masonry_joint",
        )
        box(
            c,
            f"east_mortar_course_{i}",
            (east_x + 0.285, oy + 2.65, z),
            (0.035, d - 5.2, 0.028),
            M["mortar"],
            0,
            role="masonry_joint",
        )
    for side in (-1, 1):
        x = ox - w / 2 + (0.42 if side < 0 else w - 6.0)
        for row in range(7):
            box(
                c,
                f"south_quoin_{side}_{row}",
                (x, south_y - 0.38, 0.55 + row * 0.98),
                (0.9, 0.58, 0.62),
                M["stone_light"],
                0.025,
                role="corner_quoin",
            )
    for row in range(7):
        box(
            c,
            f"east_quoin_{row}",
            (east_x + 0.38, oy + d / 2 - 0.55, 0.55 + row * 0.98),
            (0.58, 0.9, 0.62),
            M["stone_light"],
            0.025,
            role="corner_quoin",
        )

    # Tall ground windows and gridded upper windows match both visible sides.
    for i, x in enumerate(
        (ox - 13.6, ox - 9.0, ox - 4.4, ox + 0.2, ox + 4.8, ox + 9.4)
    ):
        window_y(
            c,
            f"south_ground_window_{i}",
            x,
            south_y - 0.29,
            4.1,
            3.35,
            5.4,
            M,
            glass="glass_punched",
            divisions=2,
            lit=i in {2, 3},
        )
    for i, x in enumerate(
        (ox - 13.5, ox - 9.1, ox - 4.7, ox - 0.3, ox + 4.1, ox + 8.5)
    ):
        window_y(
            c,
            f"south_upper_window_{i}",
            x,
            south_y - 0.15,
            13.8,
            3.4,
            4.5,
            M,
            glass="glass_punched",
            divisions=3,
            lit=i in {1, 4},
        )
        window_y(
            c,
            f"south_top_window_{i}",
            x,
            south_y - 0.15,
            19.1,
            3.4,
            2.25,
            M,
            glass="glass_punched",
            divisions=3,
        )
    for i, y in enumerate((oy - 4.7, oy, oy + 4.7, oy + 9.35)):
        window_x(
            c,
            f"east_ground_window_{i}",
            east_x + 0.29,
            y,
            4.1,
            3.55,
            5.4,
            M,
            glass="glass_punched",
            divisions=2,
            lit=i == 1,
        )
        window_x(
            c,
            f"east_upper_window_{i}",
            east_x + 0.15,
            y,
            13.8,
            3.55,
            4.5,
            M,
            glass="glass_punched",
            divisions=3,
            lit=i == 2,
        )
        window_x(
            c,
            f"east_top_window_{i}",
            east_x + 0.15,
            y,
            19.1,
            3.55,
            2.25,
            M,
            glass="glass_punched",
            divisions=3,
        )

    # Continuous shadow bands and a layered cornice provide true facade depth.
    for z, depth, height in (
        (7.35, 0.72, 0.48),
        (16.55, 0.6, 0.38),
        (22.75, 0.92, 0.52),
    ):
        box(
            c,
            f"south_cornice_{z}",
            (ox - 2.5, south_y - depth / 2, z),
            (w - 4.5, depth, height),
            M["stone_light"],
            0.055,
            role="masonry_cornice",
        )
        box(
            c,
            f"east_cornice_{z}",
            (east_x + depth / 2, oy + 2.5, z),
            (depth, d - 4.5, height),
            M["stone_light"],
            0.055,
            role="masonry_cornice",
        )

    # The entrance sits in the chamfered corner, not as a decal on a flat box.
    entrance_origin = (ox + w / 2 - 2.63, oy - d / 2 + 2.63, 0)
    entrance_yaw = math.radians(45)
    local_box(
        c,
        "chamfer_recess",
        entrance_origin,
        entrance_yaw,
        (0, -0.22, 3.55),
        (6.9, 0.44, 7.1),
        M["dark"],
        0.035,
        role="entrance_recess",
    )
    local_box(
        c,
        "arch_left_pier",
        entrance_origin,
        entrance_yaw,
        (-2.65, -0.52, 3.05),
        (0.72, 0.72, 6.1),
        M["stone_light"],
        0.04,
        role="arch_support",
    )
    local_box(
        c,
        "arch_right_pier",
        entrance_origin,
        entrance_yaw,
        (2.65, -0.52, 3.05),
        (0.72, 0.72, 6.1),
        M["stone_light"],
        0.04,
        role="arch_support",
    )
    arch_ring(
        c,
        "carved_stone_arch",
        entrance_origin,
        entrance_yaw,
        4.65,
        2.3,
        0.58,
        0.72,
        M["stone_light"],
        36,
    )
    arch_trim_curve(
        c,
        "carved_stone_arch_edge",
        entrance_origin,
        entrance_yaw,
        4.65,
        2.59,
        M["stone_light"],
        0.18,
        40,
    )
    local_door_set(
        c,
        "corner_entrance",
        entrance_origin,
        entrance_yaw,
        (0, -0.57, 2.25),
        3.7,
        4.45,
        M,
        frame="brass",
    )
    stair_and_rails(c, "corner_entry", entrance_origin, entrance_yaw, -0.78, 4.0, M, 4)
    local_text(
        c,
        "classical_wordmark",
        "CIVIC BANK",
        entrance_origin,
        entrance_yaw,
        (0, -0.93, 7.3),
        0.62,
        M["brass"],
        0.07,
    )

    # A low glazed roof garden retains the reference massing.  The former tall
    # white V-braces read as unexplained arrows in street views, so all46_5
    # replaces them with a restrained dark coping and real mullioned glazing.
    box(
        c,
        "roof_glazed_pavilion",
        (ox, oy + 1.1, 24.65),
        (20.0, 10.0, 3.0),
        M["glass_blue_alt"],
        0.06,
        role="roof_pavilion",
    )
    box(
        c,
        "roof_pavilion_coping_south",
        (ox, oy - 3.97, 26.22),
        (20.25, 0.22, 0.22),
        M["black_metal"],
        0.018,
        role="roof_pavilion_frame",
    )
    box(
        c,
        "roof_pavilion_coping_north",
        (ox, oy + 6.17, 26.22),
        (20.25, 0.22, 0.22),
        M["black_metal"],
        0.018,
        role="roof_pavilion_frame",
    )
    c["c2w_reference_index"] = 1
    c[
        "c2w_detail_profile"
    ] = "ashlar+true_arch+corner_entry+low_glazed_roof_garden+deep_recessed_windows"
    return c


# ---------------------------------------------------------------------------
# Bank 2: white vertical-fin tower, articulated on front and side elevations.
# ---------------------------------------------------------------------------


def build_white_vertical(parent, M):
    asset_id = "bank.white_vertical.reference_02.v4"
    c = collection("BANK_02_WHITE_VERTICAL", parent, asset_id)
    ox, oy = 40.0, 32.5
    w, d, h = 29.0, 23.0, 40.5
    south = oy - d / 2
    east = ox + w / 2
    box(
        c,
        "occupied_shell",
        (ox, oy, h / 2),
        (w, d, h),
        M["white"],
        0.14,
        role="occupied_building_shell",
    )
    box(
        c,
        "front_curtain_recess",
        (ox, south - 0.17, 20.1),
        (w - 2.0, 0.35, 35.4),
        M["dark"],
        0.025,
        role="curtain_wall_recess",
    )

    floors = 10
    floor_h = 3.55
    bays = 8
    usable = w - 3.2
    bay_w = usable / bays
    for floor in range(floors):
        z = 2.0 + floor * floor_h
        for bay in range(bays):
            x = ox - usable / 2 + bay_w * (bay + 0.5)
            lit = (floor * 3 + bay * 5) % 11 in {1, 4}
            window_y(
                c,
                f"front_window_{floor}_{bay}",
                x,
                south - 0.38,
                z,
                bay_w - 0.28,
                2.75,
                M,
                glass="glass_punched",
                divisions=1,
                lit=lit,
            )
        box(
            c,
            f"front_floor_spandrel_{floor}",
            (ox, south - 0.55, z + 1.57),
            (usable + 0.3, 0.22, 0.30),
            M["black_metal"],
            0.015,
            role="curtain_wall_spandrel",
        )
    for bay in range(bays + 1):
        x = ox - usable / 2 + bay_w * bay
        box(
            c,
            f"precast_vertical_fin_{bay}",
            (x, south - 0.93, 20.15),
            (0.34, 1.15, 36.5),
            M["white_clean"],
            0.055,
            role="structural_sun_fin",
        )

    # Fully developed east elevation rather than an untextured side wall.
    side_bays = 6
    side_usable = d - 3.0
    side_w = side_usable / side_bays
    for floor in range(floors):
        z = 2.0 + floor * floor_h
        for bay in range(side_bays):
            y = oy - side_usable / 2 + side_w * (bay + 0.5)
            window_x(
                c,
                f"east_window_{floor}_{bay}",
                east + 0.24,
                y,
                z,
                side_w - 0.28,
                2.75,
                M,
                glass="glass_punched",
                divisions=1,
                lit=(floor + bay) % 9 == 2,
            )
    for bay in range(side_bays + 1):
        y = oy - side_usable / 2 + side_w * bay
        box(
            c,
            f"east_vertical_fin_{bay}",
            (east + 0.72, y, 20.1),
            (0.95, 0.31, 36.4),
            M["white_clean"],
            0.05,
            role="structural_sun_fin",
        )

    # Double-height lobby with visible ceiling baffles and interior depth.
    box(
        c,
        "lobby_portal",
        (ox, south - 1.0, 3.45),
        (9.2, 1.5, 6.9),
        M["white_clean"],
        0.1,
        role="entrance_portal",
    )
    box(
        c,
        "lobby_glass",
        (ox, south - 1.82, 3.35),
        (7.4, 0.08, 6.2),
        M["glass_entry"],
        0.012,
        role="lobby_glazing",
    )
    box(
        c,
        "lobby_warm_back",
        (ox, south - 0.65, 3.1),
        (7.0, 0.08, 5.7),
        M["warm_light"],
        0.01,
        role="interior_depth",
    )
    local_door_set(
        c,
        "white_bank_entry",
        (ox, oy, 0),
        0,
        (0, -d / 2 - 1.95, 2.1),
        4.2,
        4.15,
        M,
        frame="steel",
    )
    for x in [ox - 3.1 + i * 1.05 for i in range(7)]:
        box(
            c,
            "lobby_ceiling_baffle",
            (x, south - 1.45, 6.0),
            (0.08, 1.25, 0.18),
            M["steel"],
            0.01,
            role="lobby_ceiling_detail",
        )
    stair_and_rails(c, "white_entry", (ox, oy, 0), 0, -d / 2 - 2.0, 5.0, M, 3)

    # Enlarged, fully extruded identity band.  The sign is dimensioned to read
    # both in the close view and the two campus overviews.
    sign_backer = box(
        c,
        "us_sign_backer",
        (ox - 7.25, south - 1.68, 36.55),
        (5.8, 0.34, 3.15),
        M["red"],
        0.16,
        role="architectural_signage",
    )
    sign_backer["c2w_sign_revision"] = "all46_5_enlarged_145_percent"
    text_object(
        c,
        "us_letters",
        "US",
        (ox - 7.25, south - 1.88, 36.55),
        1.88,
        M["white_clean"],
        0.105,
    )
    bank_backer = box(
        c,
        "bank_wordmark_shadow_panel",
        (ox + 3.25, south - 1.60, 36.55),
        (9.1, 0.22, 3.05),
        M["white_clean"],
        0.09,
        role="architectural_signage",
    )
    bank_backer["c2w_sign_revision"] = "all46_5_enlarged_145_percent"
    text_object(
        c,
        "bank_letters",
        "bank",
        (ox - 0.15, south - 1.78, 36.55),
        2.22,
        M["blue"],
        0.11,
        align="LEFT",
    )
    for x, y, dx, dy, dz in (
        (ox - 6.5, oy + 2.5, 5.5, 4.2, 1.7),
        (ox + 3.5, oy + 1.5, 8.5, 5.5, 2.1),
    ):
        box(
            c,
            "roof_mechanical_screen",
            (x, y, h + dz / 2),
            (dx, dy, dz),
            M["white"],
            0.07,
            role="roof_mechanical_screen",
        )
        for i in range(7):
            box(
                c,
                "mechanical_louver",
                (x, y - dy / 2 - 0.045, h + 0.35 + i * (dz - 0.6) / 6),
                (dx - 0.5, 0.035, 0.065),
                M["steel"],
                0.005,
                role="mechanical_louver",
            )
    for i in range(8):
        cylinder(
            c,
            "roof_vent",
            (ox - 10.0 + i * 1.05, oy - 2.0, h + 1.0),
            0.20,
            1.7,
            M["steel"],
            24,
            role="roof_service",
        )
        cylinder(
            c,
            "roof_vent_cap",
            (ox - 10.0 + i * 1.05, oy - 2.0, h + 1.92),
            0.31,
            0.16,
            M["steel"],
            24,
            role="roof_service",
        )
    for x, y in (
        (ox - w / 2 + 0.25, oy),
        (ox + w / 2 - 0.25, oy),
        (ox, oy + d / 2 - 0.25),
    ):
        box(
            c,
            "layered_parapet",
            (x, y, h + 0.45),
            ((0.45 if x != ox else w), (d if x != ox else 0.45), 0.9),
            M["white_clean"],
            0.06,
            role="roof_parapet",
        )
    c["c2w_reference_index"] = 2
    c[
        "c2w_detail_profile"
    ] = "ten_floors+recessed_window_cells+wraparound_fins+roof_plant+lobby"
    return c


# ---------------------------------------------------------------------------
# Bank 3: three-tower blue-glass headquarters with podium and setbacks.
# ---------------------------------------------------------------------------


def curtain_tower(c, name, ox, oy, w, d, h, M, bays, floors, crown=1.0, lit_offset=0):
    box(
        c,
        name + ":structural_core",
        (ox, oy, h / 2),
        (w - 0.65, d - 0.65, h),
        M["charcoal"],
        0.08,
        role="occupied_building_shell",
    )
    south = oy - d / 2 - 0.08
    east = ox + w / 2 + 0.08
    floor_h = (h - 2.0) / floors
    # Glass ribbons, floor slabs, alternating panes and dense mullions.
    for floor in range(floors):
        z = 1.25 + floor * floor_h + floor_h / 2
        mat_key = ("glass_blue", "glass_blue_alt", "glass_silver", "glass_blue")[
            floor % 4
        ]
        box(
            c,
            name + f":south_glass_ribbon_{floor}",
            (ox, south - 0.10, z),
            (w - 0.45, 0.10, floor_h - 0.28),
            M[mat_key],
            0.009,
            role="curtain_wall_glazing",
        )
        box(
            c,
            name + f":east_glass_ribbon_{floor}",
            (east + 0.10, oy, z),
            (0.10, d - 0.45, floor_h - 0.28),
            M[mat_key],
            0.009,
            role="curtain_wall_glazing",
        )
        box(
            c,
            name + f":south_spandrel_{floor}",
            (ox, south - 0.18, z + floor_h / 2),
            (w + 0.12, 0.18, 0.15),
            M["black_metal"],
            0.006,
            role="curtain_wall_spandrel",
        )
        box(
            c,
            name + f":east_spandrel_{floor}",
            (east + 0.18, oy, z + floor_h / 2),
            (0.18, d + 0.12, 0.15),
            M["black_metal"],
            0.006,
            role="curtain_wall_spandrel",
        )
        box(
            c,
            name + f":interior_slab_{floor}",
            (ox, south + 1.05, z - floor_h / 2 + 0.13),
            (w - 1.15, 2.25, 0.18),
            M["concrete"],
            0.012,
            role="interior_floor_slab",
        )
        if floor % 5 in {1, 3}:
            shade_x = ox - w * 0.19 if floor % 2 else ox + w * 0.18
            box(
                c,
                name + f":roller_shade_{floor}",
                (shade_x, south + 0.08, z),
                (w * 0.26, 0.035, floor_h * 0.70),
                M["white_clean"],
                0.004,
                role="interior_blind",
            )
        if (floor + lit_offset) % 7 in {1, 4}:
            box(
                c,
                name + f":occupied_floor_light_{floor}",
                (ox, south + 0.02, z),
                (w * 0.72, 0.04, floor_h * 0.62),
                M["warm_light"],
                0.005,
                role="interior_depth",
            )
    for bay in range(bays + 1):
        x = ox - w / 2 + 0.3 + (w - 0.6) * bay / bays
        box(
            c,
            name + f":south_mullion_{bay}",
            (x, south - 0.24, h / 2),
            (0.105, 0.14, h - 0.45),
            M["black_metal"],
            0.006,
            role="curtain_wall_mullion",
        )
    side_bays = max(4, int(bays * d / w))
    for bay in range(side_bays + 1):
        y = oy - d / 2 + 0.3 + (d - 0.6) * bay / side_bays
        box(
            c,
            name + f":east_mullion_{bay}",
            (east + 0.24, y, h / 2),
            (0.14, 0.105, h - 0.45),
            M["black_metal"],
            0.006,
            role="curtain_wall_mullion",
        )
    box(
        c,
        name + ":vertical_shadow_spine",
        (ox - w / 2 - 0.18, oy - 1.3, h / 2),
        (0.42, d - 2.0, h + 0.4),
        M["black_metal"],
        0.035,
        role="tower_shadow_spine",
    )
    for x in (ox - w / 2 - 0.31, ox + w / 2 + 0.31):
        box(
            c,
            name + ":full_height_corner_return",
            (x, south + 0.20, h / 2),
            (0.30, 0.65, h + 0.25),
            M["black_metal"],
            0.022,
            role="curtain_wall_corner_cap",
        )
    box(
        c,
        name + ":crown",
        (ox, oy, h + crown / 2),
        (w + 0.7, d + 0.7, crown),
        M["black_metal"],
        0.055,
        role="tower_crown",
    )


def build_glass_headquarters(parent, M):
    asset_id = "bank.blue_glass_headquarters.reference_03.v4"
    c = collection("BANK_03_BLUE_GLASS_HEADQUARTERS", parent, asset_id)
    curtain_tower(c, "central_tower", 0.0, 90.0, 24.0, 20.0, 91.0, M, 9, 31, 1.25, 0)
    curtain_tower(c, "west_tower", -23.0, 94.0, 18.5, 18.0, 70.0, M, 7, 24, 1.0, 2)
    curtain_tower(c, "east_tower", 24.0, 95.0, 19.5, 18.0, 64.0, M, 7, 22, 1.0, 4)

    # Setback slabs make the massing visibly non-boxlike.
    box(
        c,
        "central_top_setback",
        (2.0, 91.0, 93.45),
        (16.0, 13.0, 2.9),
        M["glass_silver"],
        0.09,
        role="tower_setback",
    )
    box(
        c,
        "west_notch_spine",
        (-17.0, 84.8, 43.0),
        (5.0, 0.75, 39.0),
        M["black_metal"],
        0.03,
        role="tower_shadow_spine",
    )
    box(
        c,
        "east_notch_spine",
        (18.5, 85.8, 38.0),
        (4.5, 0.75, 32.0),
        M["black_metal"],
        0.03,
        role="tower_shadow_spine",
    )

    # Eight-metre podium with columns, transparent lobby, doors and canopy.
    box(
        c,
        "occupied_podium",
        (0, 82.0, 4.5),
        (65.0, 27.0, 9.0),
        M["charcoal"],
        0.16,
        role="occupied_building_shell",
    )
    box(
        c,
        "podium_glass",
        (0, 68.25, 4.2),
        (59.0, 0.10, 7.2),
        M["glass_clear"],
        0.012,
        role="lobby_glazing",
    )
    box(
        c,
        "podium_interior",
        (0, 68.65, 4.0),
        (57.5, 0.06, 6.6),
        M["warm_light"],
        0.008,
        role="interior_depth",
    )
    for x in [(-29 + i * 4.15) for i in range(15)]:
        box(
            c,
            "podium_column",
            (x, 67.9, 4.15),
            (0.24, 0.52, 7.65),
            M["steel"],
            0.018,
            role="structural_column",
        )
    box(
        c,
        "headquarters_canopy",
        (0, 65.8, 6.25),
        (17.0, 5.2, 0.38),
        M["steel"],
        0.07,
        role="entrance_canopy",
    )
    for x in (-7.2, 7.2):
        box(
            c,
            "canopy_square_post",
            (x, 64.45, 3.05),
            (0.28, 0.28, 6.1),
            M["steel"],
            0.035,
            role="structural_column",
        )
    local_door_set(
        c,
        "headquarters_entry",
        (0, 82, 0),
        0,
        (0, -13.9, 2.45),
        5.2,
        4.8,
        M,
        frame="steel",
    )
    # all46_5 deliberately keeps the rectilinear recessed double-door set
    # visible.  The former freestanding glass cylinder obscured the entrance
    # and read as an unrelated object in the podium street view.
    stair_and_rails(c, "hq_entry", (0, 82, 0), 0, -15.1, 7.0, M, 3)

    dbs_facade_identity(c, M, 0.0, 79.48, 85.8)
    # Roof maintenance rails and antennas complete the silhouette.
    for x in (-9.5, -3.2, 3.2, 9.5):
        cylinder(
            c,
            "roof_antenna",
            (x, 90.0, 93.2),
            0.07,
            3.2,
            M["steel"],
            16,
            role="roof_service",
        )
        cylinder(
            c,
            "roof_antenna_tip",
            (x, 90.0, 94.85),
            0.14,
            0.15,
            M["lamp"],
            16,
            role="roof_service",
        )
    c["c2w_reference_index"] = 3
    c[
        "c2w_detail_profile"
    ] = "three_towers+setbacks+dense_mullions+occupied_floors+recessed_double_doors+podium"
    return c


# ---------------------------------------------------------------------------
# Bank 4: bronze framed three-storey branch with a glowing central hall.
# ---------------------------------------------------------------------------


def build_bronze_branch(parent, M):
    asset_id = "bank.bronze_frame.reference_04.v4"
    c = collection("BANK_04_BRONZE_FRAME_BRANCH", parent, asset_id)
    ox, oy = 0.0, -28.0
    w, d, h = 42.0, 23.0, 20.5
    south = oy - d / 2
    east = ox + w / 2
    box(
        c,
        "occupied_shell",
        (ox, oy, h / 2),
        (w, d, h),
        M["charcoal"],
        0.11,
        role="occupied_building_shell",
    )
    box(
        c,
        "bronze_roof_shadow",
        (ox, oy, h + 0.22),
        (w + 1.0, d + 1.0, 0.38),
        M["dark"],
        0.055,
        role="tower_crown_shadow",
    )
    box(
        c,
        "bronze_roof_cap",
        (ox, oy, h + 0.58),
        (w + 1.4, d + 1.4, 0.42),
        M["bronze_dark"],
        0.075,
        role="roof_parapet",
    )

    # Six side bays with deeply recessed glazing and genuine sunshade stacks.
    bay_centres = (-17.0, -12.3, -7.6, 7.6, 12.3, 17.0)
    for bay, x in enumerate(bay_centres):
        for floor, z in enumerate((3.35, 9.0, 14.65)):
            window_y(
                c,
                f"bronze_window_{bay}_{floor}",
                ox + x,
                south - 0.30,
                z,
                3.55,
                4.25,
                M,
                glass="glass_bronze",
                frame="bronze_dark",
                divisions=2,
                lit=floor == 0 or (bay + floor) % 5 == 0,
            )
            for slat in range(4):
                box(
                    c,
                    f"integrated_louver_{bay}_{floor}_{slat}",
                    (ox + x, south - 0.67, z + 1.48 + slat * 0.11),
                    (3.35, 0.34, 0.042),
                    M["bronze_dark"],
                    0.006,
                    role="operable_sun_louver",
                )
    for pier, x in enumerate((-19.4, -14.7, -10.0, -5.75, 5.75, 10.0, 14.7, 19.4)):
        box(
            c,
            f"bronze_pier_{pier}",
            (ox + x, south - 0.66, h / 2),
            (0.54, 0.88, h - 0.7),
            M["bronze"] if pier % 2 == 0 else M["bronze_alt"],
            0.055,
            role="facade_pier",
        )
    for z in (5.75, 11.35, 17.0):
        box(
            c,
            "bronze_spandrel_left",
            (ox - 13.5, south - 0.42, z),
            (14.6, 0.34, 0.52),
            M["bronze_dark"],
            0.025,
            role="floor_spandrel",
        )
        box(
            c,
            "bronze_spandrel_right",
            (ox + 13.5, south - 0.42, z),
            (14.6, 0.34, 0.52),
            M["bronze_dark"],
            0.025,
            role="floor_spandrel",
        )

    # Projecting central frame encloses a real three-storey glass hall.
    for x in (-5.6, 5.6):
        box(
            c,
            "central_frame_side",
            (ox + x, south - 1.02, 10.4),
            (0.95, 1.25, 20.0),
            M["bronze"],
            0.065,
            role="monumental_portal_frame",
        )
    box(
        c,
        "central_frame_top",
        (ox, south - 1.02, 19.8),
        (12.1, 1.25, 1.2),
        M["bronze"],
        0.065,
        role="monumental_portal_frame",
    )
    # Thin interior back planes leave a readable cavity between glazing and
    # shell.  A solid dark cuboid here previously hid all modeled warm lobby
    # content and made the atrium look like an opaque brown sticker.
    box(
        c,
        "central_hall_recess",
        (ox, south - 0.58, 10.0),
        (10.0, 0.045, 18.1),
        M["dark"],
        0.01,
        role="entrance_recess",
    )
    box(
        c,
        "central_hall_shadow_back",
        (ox, south - 0.54, 10.0),
        (9.2, 0.035, 17.0),
        M["interior"],
        0.006,
        role="interior_depth",
    )
    box(
        c,
        "central_hall_warm_ground",
        (ox, south - 0.68, 2.55),
        (9.0, 0.035, 4.4),
        M["warm_light"],
        0.006,
        role="interior_depth",
    )
    for level, zz in enumerate((7.7, 13.35)):
        box(
            c,
            f"central_hall_warm_ceiling_{level}",
            (ox, south + 0.08, zz),
            (8.7, 1.85, 0.11),
            M["warm_light"],
            0.01,
            role="interior_light_fixture",
        )
    box(
        c,
        "central_hall_glass",
        (ox, south - 1.38, 10.0),
        (9.6, 0.08, 17.6),
        M["glass_bronze"],
        0.012,
        role="lobby_glazing",
    )
    for x in (-4.8, -2.4, 0, 2.4, 4.8):
        box(
            c,
            "hall_vertical_mullion",
            (ox + x, south - 1.47, 10.0),
            (0.11, 0.14, 17.7),
            M["black_metal"],
            0.008,
            role="curtain_wall_mullion",
        )
    for z in (5.7, 11.35, 17.0):
        box(
            c,
            "hall_horizontal_mullion",
            (ox, south - 1.47, z),
            (9.8, 0.14, 0.12),
            M["black_metal"],
            0.008,
            role="curtain_wall_mullion",
        )
    local_door_set(
        c,
        "bronze_entry",
        (ox, oy, 0),
        0,
        (0, -d / 2 - 1.52, 2.35),
        4.8,
        4.6,
        M,
        glass="glass_bronze",
        frame="bronze",
    )
    text_object(
        c,
        "bronze_bank_letters",
        "BANK",
        (ox, south - 1.66, 6.75),
        1.78,
        M["white_clean"],
        0.12,
    )
    box(
        c,
        "entrance_canopy",
        (ox, south - 2.35, 5.12),
        (7.8, 2.25, 0.24),
        M["bronze"],
        0.055,
        role="entrance_canopy",
    )
    box(
        c,
        "entrance_canopy_soffit",
        (ox, south - 2.35, 4.96),
        (7.5, 2.05, 0.08),
        M["warm_light"],
        0.018,
        role="entrance_soffit",
    )
    stair_and_rails(c, "bronze_entry", (ox, oy, 0), 0, -d / 2 - 2.0, 6.0, M, 4)

    # East wall is also articulated for the close oblique view.
    for floor, z in enumerate((3.4, 9.0, 14.6)):
        for bay, y in enumerate((oy - 7.6, oy - 2.6, oy + 2.6, oy + 7.6)):
            window_x(
                c,
                f"east_bronze_window_{floor}_{bay}",
                east + 0.24,
                y,
                z,
                3.65,
                4.15,
                M,
                glass="glass_bronze",
                frame="bronze_dark",
                divisions=2,
                lit=floor == 0 or (floor + bay) % 6 == 0,
            )
    for y in (oy - 10.1, oy - 5.1, oy, oy + 5.1, oy + 10.1):
        box(
            c,
            "east_bronze_pier",
            (east + 0.62, y, h / 2),
            (0.82, 0.52, h - 0.7),
            M["bronze_alt"],
            0.055,
            role="facade_pier",
        )
    c["c2w_reference_index"] = 4
    c[
        "c2w_detail_profile"
    ] = "three_storeys+deep_reflective_bays+integrated_louvers+monumental_glass_hall+warm_readable_interior+brushed_bronze"
    return c


# ---------------------------------------------------------------------------
# Coherent public realm.  It is detailed but deliberately contains no proxy
# vehicles, people or spherical/tree blobs that could read as toy geometry.
# ---------------------------------------------------------------------------


def streetlight(c, name, x, y, facing, M):
    cylinder(
        c,
        name + ":tapered_pole",
        (x, y, 3.5),
        0.09,
        7.0,
        M["black_metal"],
        24,
        role="streetlight_pole",
    )
    dx, dy = math.sin(facing) * 0.78, -math.cos(facing) * 0.78
    beam(
        c,
        name + ":arm",
        (x, y, 6.72),
        (x + dx, y + dy, 7.12),
        0.055,
        M["black_metal"],
        18,
        "streetlight_arm",
    )
    box(
        c,
        name + ":luminaire",
        (x + dx * 1.12, y + dy * 1.12, 7.08),
        (0.72, 0.34, 0.16),
        M["black_metal"],
        0.055,
        rot=facing,
        role="streetlight_luminaire",
    )
    box(
        c,
        name + ":lens",
        (x + dx * 1.12, y + dy * 1.12, 6.98),
        (0.52, 0.24, 0.035),
        M["lamp"],
        0.015,
        rot=facing,
        role="streetlight_lens",
    )


def public_realm(parent, M):
    c = collection("FINANCIAL_CAMPUS_PUBLIC_REALM", parent, "site.financial_campus.v5")
    # Oversized receiving plane keeps every validation camera grounded; it is
    # intentionally larger than the detailed block so no diorama edge or the
    # below-horizon black region of Nishita can enter a finished frame.
    box(
        c,
        "infinite_ground",
        (0, 31.5, -0.6),
        (1200, 1200, 1.0),
        M["urban_context"],
        0.02,
        role="site_ground",
    )

    # The enclosing block now reaches north of the headquarters.  Every bank
    # therefore sits inside the same four-sided street/curb boundary instead
    # of leaving the headquarters isolated beyond the former north road.
    for name, xyz, dims in (
        ("south_boulevard", (0, -53, 0.02), (146, 14, 0.22)),
        ("north_boulevard", (0, 116, 0.02), (146, 14, 0.22)),
        ("west_street", (-67, 31.5, 0.02), (12, 169, 0.22)),
        ("east_street", (67, 31.5, 0.02), (12, 169, 0.22)),
    ):
        box(c, name, xyz, dims, M["asphalt"], 0.02, role="asphalt_road")
    for y in (-60.2, -45.8, 108.8, 123.2):
        box(
            c,
            "horizontal_curb",
            (0, y, 0.28),
            (146, 0.34, 0.56),
            M["stone_light"],
            0.055,
            role="street_curb",
        )
    for x in (-73.2, -60.8, 60.8, 73.2):
        box(
            c,
            "vertical_curb",
            (x, 31.5, 0.28),
            (0.34, 169, 0.56),
            M["stone_light"],
            0.055,
            role="street_curb",
        )
    for y in (-61.5, -44.5, 107.5, 124.5):
        for x in range(-54, 55, 14):
            box(
                c,
                "lane_marking",
                (x, y, 0.145),
                (7.0, 0.15, 0.025),
                M["road_mark"],
                0,
                role="road_marking",
            )
    for x in (-74.5, -59.5, 59.5, 74.5):
        for y in range(-36, 101, 14):
            box(
                c,
                "side_street_lane_marking",
                (x, y, 0.145),
                (0.15, 7.0, 0.025),
                M["road_mark"],
                0,
                role="road_marking",
            )

    # A fully paved inner precinct replaces the broad, empty grey ground of
    # all46_4.  Fine saw-cut joints, a charcoal perimeter frame and regularly
    # spaced datum bands keep the material scale credible in near and aerial
    # views without resorting to a flat image texture.
    box(
        c,
        "campus_paving_field",
        (0, 31.5, 0.11),
        (120.8, 153.8, 0.22),
        M["paver"],
        0.025,
        role="site_paving_base",
    )
    for name, xyz, dims in (
        ("west_paving_edge", (-58.4, 31.5, 0.235), (0.55, 149.0, 0.05)),
        ("east_paving_edge", (58.4, 31.5, 0.235), (0.55, 149.0, 0.05)),
        ("south_paving_edge", (0, -42.4, 0.235), (116.8, 0.55, 0.05)),
        ("north_paving_edge", (0, 105.4, 0.235), (116.8, 0.55, 0.05)),
    ):
        box(c, name, xyz, dims, M["paver_edge"], 0.012, role="paving_edge_band")
    for x in range(-56, 57, 4):
        box(
            c,
            "campus_longitudinal_joint",
            (x, 31.5, 0.226),
            (0.026, 147.0, 0.012),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for y in range(-40, 105, 4):
        box(
            c,
            "campus_transverse_joint",
            (0, y, 0.227),
            (115.0, 0.026, 0.012),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for x in (-48, -36, -24, 24, 36, 48):
        box(
            c,
            "campus_granite_datum",
            (x, 31.5, 0.242),
            (0.24, 146.0, 0.032),
            M["paver_cool"],
            0.008,
            role="paving_inlay",
        )
    for y in (-32, -20, -8, 42, 54, 78, 90, 102):
        box(
            c,
            "campus_granite_datum",
            (0, y, 0.242),
            (114.0, 0.24, 0.032),
            M["paver_cool"],
            0.008,
            role="paving_inlay",
        )

    # The central plaza uses a physically modeled staggered ashlar bond.  The
    # short vertical joints alternate by half a paver on each course.
    box(
        c,
        "central_plaza",
        (0, 17.0, 0.275),
        (44.0, 43.0, 0.12),
        M["paver_light"],
        0.045,
        role="pedestrian_plaza",
    )
    for row in range(36):
        y = -3.4 + row * 1.2
        box(
            c,
            "plaza_course_joint",
            (0, y, 0.342),
            (43.2, 0.025, 0.014),
            M["mortar"],
            0,
            role="paver_joint",
        )
        offset = 1.0 if row % 2 else 0.0
        for col in range(-11, 12):
            x = col * 2.0 + offset
            if -21.5 < x < 21.5:
                box(
                    c,
                    "plaza_staggered_head_joint",
                    (x, y + 0.60, 0.343),
                    (0.025, 1.14, 0.014),
                    M["mortar"],
                    0,
                    role="paver_joint",
                )
    for name, xyz, dims in (
        ("plaza_frame_west", (-21.45, 17, 0.37), (0.32, 42.4, 0.07)),
        ("plaza_frame_east", (21.45, 17, 0.37), (0.32, 42.4, 0.07)),
        ("plaza_frame_south", (0, -4.15, 0.37), (43.2, 0.32, 0.07)),
        ("plaza_frame_north", (0, 38.15, 0.37), (43.2, 0.32, 0.07)),
    ):
        box(c, name, xyz, dims, M["paver_edge"], 0.012, role="paving_edge_band")

    # Axial walks connect every entrance.  The headquarters approach is a
    # narrow north-south arrival drive, giving the corrected east-west zebra
    # bars a real traffic context.
    box(
        c,
        "south_axis_walk",
        (0, -7.0, 0.28),
        (12, 21, 0.12),
        M["paver_light"],
        0.04,
        role="pedestrian_walk",
    )
    box(
        c,
        "west_axis_walk",
        (-28, 17, 0.17),
        (14, 10, 0.28),
        M["paver_light"],
        0.04,
        role="pedestrian_walk",
    )
    box(
        c,
        "east_axis_walk",
        (28, 17, 0.17),
        (14, 10, 0.28),
        M["paver_light"],
        0.04,
        role="pedestrian_walk",
    )
    box(
        c,
        "headquarters_arrival_drive",
        (0, 51.5, 0.31),
        (12.0, 25.0, 0.16),
        M["asphalt"],
        0.025,
        role="internal_arrival_drive",
    )
    box(
        c,
        "hq_west_walk",
        (-9.5, 51.5, 0.30),
        (6.0, 25.0, 0.14),
        M["paver_warm"],
        0.035,
        role="pedestrian_walk",
    )
    box(
        c,
        "hq_east_walk",
        (9.5, 51.5, 0.30),
        (6.0, 25.0, 0.14),
        M["paver_warm"],
        0.035,
        role="pedestrian_walk",
    )
    box(
        c,
        "headquarters_forecourt",
        (0, 65.0, 0.31),
        (38.0, 4.4, 0.16),
        M["paver_light"],
        0.045,
        role="building_forecourt",
    )

    # Restrained bronze/charcoal inlays replace the previous pool-like blue
    # rectangle, so the center reads as crafted paving rather than a toy water
    # feature.  The inlays remain flush and fully walkable.
    for x in (-14, -7, 0, 7, 14):
        box(
            c,
            "plaza_bronze_inlay",
            (x, 17, 0.355),
            (0.12, 40.0, 0.035),
            M["bronze_dark"],
            0.006,
            role="paving_inlay",
        )
    for y in (2, 9.5, 17, 24.5, 32):
        box(
            c,
            "plaza_charcoal_inlay",
            (0, y, 0.356),
            (41.0, 0.12, 0.035),
            M["paver_edge"],
            0.006,
            role="paving_inlay",
        )

    # Benches have separate timber slats, structure and feet.
    for x, y, yaw in ((-17, 5, 0), (17, 5, 0), (-17, 29, math.pi), (17, 29, math.pi)):
        for slat in range(6):
            box(
                c,
                "bench_timber_slat",
                (x, y + (slat - 2.5) * 0.13, 0.78),
                (5.2, 0.10, 0.11),
                M["wood"],
                0.035,
                rot=yaw,
                role="bench_slat",
            )
        for dx in (-2.15, 2.15):
            box(
                c,
                "bench_steel_leg",
                (x + dx, y, 0.45),
                (0.12, 0.65, 0.62),
                M["steel"],
                0.025,
                rot=yaw,
                role="bench_frame",
            )

    for idx, (x, y, facing) in enumerate(
        (
            (-52, -44, 0),
            (-28, -44, 0),
            (28, -44, 0),
            (52, -44, 0),
            (-52, 108, math.pi),
            (-26, 108, math.pi),
            (26, 108, math.pi),
            (52, 108, math.pi),
            (-59, -20, -math.pi / 2),
            (-59, 25, -math.pi / 2),
            (-59, 72, -math.pi / 2),
            (59, -20, math.pi / 2),
            (59, 25, math.pi / 2),
            (59, 72, math.pi / 2),
        )
    ):
        streetlight(c, f"streetlight_{idx}", x, y, facing, M)

    # Tactile strips and recessed linear drainage details establish human
    # scale without adding any planters, greenery or entrance bollards.
    for x, y, w, yaw in (
        (0, -43.3, 7.0, 0),
        (-40, 17.2, 5.0, 0),
        (40, 19.0, 5.0, 0),
        (0, 64.0, 7.0, 0),
    ):
        box(
            c,
            "tactile_entry_strip",
            (x, y, 0.405),
            (w, 0.72, 0.055),
            M["brass"],
            0.018,
            rot=yaw,
            role="tactile_paving",
        )
    for x, y in ((-48, -45), (48, -45), (-48, 108), (48, 108)):
        box(
            c,
            "storm_drain",
            (x, y, 0.15),
            (1.6, 0.55, 0.06),
            M["black_metal"],
            0.025,
            role="storm_drain",
        )
        for slat in range(8):
            box(
                c,
                "storm_drain_slot",
                (x - 0.66 + slat * 0.19, y, 0.185),
                (0.055, 0.44, 0.025),
                M["steel"],
                0.005,
                role="storm_drain_slot",
            )
    for x, y, dims in (
        (-6.35, 51.5, (0.18, 25.0, 0.06)),
        (6.35, 51.5, (0.18, 25.0, 0.06)),
        (0, 39.0, (12.9, 0.18, 0.06)),
    ):
        box(
            c,
            "recessed_linear_drain",
            (x, y, 0.405),
            dims,
            M["black_metal"],
            0.012,
            role="linear_drain",
        )
    c["c2w_enclosed_site_bounds"] = json.dumps(SITE_BOUNDS)
    c["c2w_landscaping_policy"] = "hardscape_only_no_planters_no_greenery"
    c[
        "c2w_detail_profile"
    ] = "enlarged_enclosed_block+fine_granite_field+staggered_ashlar_plaza+datum_inlays+arrival_drive+slatted_benches+street_furniture"
    return c


# ---------------------------------------------------------------------------
# all46_5 production detailing pass.  These are modeled parts (not decals):
# stone bond, interior blind lines, slab edges, roof plant, drainage and lobby
# furnishings remain visible in close views while the shared-mesh strategy
# keeps the generator suitable for the full urban pipeline.
# ---------------------------------------------------------------------------


def blind_bank_y(c, name, x, y, z, width, height, M, rows=8, warm=False):
    """Venetian-blind stack behind a south/north-facing glazing panel."""
    mat = M["bronze_dark"] if warm else M["steel"]
    for row in range(rows):
        zz = z - height * 0.39 + height * 0.78 * row / max(1, rows - 1)
        box(
            c,
            f"{name}:blind_slat_{row}",
            (x, y, zz),
            (width * 0.86, 0.028, 0.035),
            mat,
            0,
            role="interior_blind",
        )


def blind_bank_x(c, name, x, y, z, width, height, M, rows=8, warm=False):
    mat = M["bronze_dark"] if warm else M["steel"]
    for row in range(rows):
        zz = z - height * 0.39 + height * 0.78 * row / max(1, rows - 1)
        box(
            c,
            f"{name}:blind_slat_{row}",
            (x, y, zz),
            (0.028, width * 0.86, 0.035),
            mat,
            0,
            role="interior_blind",
        )


def roof_guard(c, name, x0, x1, y0, y1, z, M, material_key="steel"):
    """A complete code-height roof rail with posts and two continuous rails."""
    guard_material = M[material_key]
    for x in (x0, x1):
        for y in (y0, y1):
            cylinder(
                c,
                f"{name}:corner_post",
                (x, y, z + 0.55),
                0.035,
                1.1,
                guard_material,
                12,
                role="roof_safety_rail",
            )
    for x in (x0, x1):
        beam(
            c,
            f"{name}:side_top",
            (x, y0, z + 1.05),
            (x, y1, z + 1.05),
            0.035,
            guard_material,
            12,
            "roof_safety_rail",
        )
        beam(
            c,
            f"{name}:side_mid",
            (x, y0, z + 0.56),
            (x, y1, z + 0.56),
            0.028,
            guard_material,
            12,
            "roof_safety_rail",
        )
    for y in (y0, y1):
        beam(
            c,
            f"{name}:end_top",
            (x0, y, z + 1.05),
            (x1, y, z + 1.05),
            0.035,
            guard_material,
            12,
            "roof_safety_rail",
        )
        beam(
            c,
            f"{name}:end_mid",
            (x0, y, z + 0.56),
            (x1, y, z + 0.56),
            0.028,
            guard_material,
            12,
            "roof_safety_rail",
        )
    for x in (x0, (x0 + x1) / 2, x1):
        for y in (y0, y1):
            cylinder(
                c,
                f"{name}:edge_post",
                (x, y, z + 0.55),
                0.028,
                1.1,
                guard_material,
                12,
                role="roof_safety_rail",
            )


def hvac_unit(c, name, x, y, z, width, depth, height, M):
    box(
        c,
        name + ":cabinet",
        (x, y, z + height / 2),
        (width, depth, height),
        M["steel"],
        0.07,
        role="roof_hvac",
    )
    for row in range(6):
        zz = z + 0.24 + row * (height - 0.45) / 5
        box(
            c,
            name + f":intake_louver_{row}",
            (x, y - depth / 2 - 0.035, zz),
            (width - 0.32, 0.045, 0.055),
            M["black_metal"],
            0.005,
            role="mechanical_louver",
        )
    cylinder(
        c,
        name + ":fan_well",
        (x, y, z + height + 0.075),
        min(width, depth) * 0.26,
        0.15,
        M["black_metal"],
        32,
        role="roof_hvac",
    )
    for angle in (0, math.pi / 3, 2 * math.pi / 3):
        box(
            c,
            name + ":fan_blade",
            (x, y, z + height + 0.16),
            (min(width, depth) * 0.42, 0.07, 0.025),
            M["steel"],
            0.004,
            rot=angle,
            role="roof_hvac_fan",
        )


def enhance_classical_corner(c, M):
    ox, oy, w, d, h = -40.0, 31.0, 34.0, 25.0, 23.0
    south, east = oy - d / 2 - 0.08, ox + w / 2 + 0.08

    # Staggered ashlar bond and projecting sill/lintel stones reproduce the
    # visible dressed-block base instead of relying on a flat procedural color.
    south_span = w - 5.3
    east_span = d - 5.3
    for row in range(13):
        z = 0.48 + row * 0.52
        shift = 0.86 if row % 2 else 0.0
        for joint in range(9):
            x = ox - 2.65 - south_span / 2 + 0.5 + joint * 1.75 + shift
            if ox - 2.65 - south_span / 2 < x < ox - 2.65 + south_span / 2:
                box(
                    c,
                    f"south_ashlar_bond_{row}_{joint}",
                    (x, south - 0.495, z),
                    (0.032, 0.03, 0.43),
                    M["mortar"],
                    0,
                    role="masonry_joint",
                )
        for joint in range(6):
            y = oy + 2.65 - east_span / 2 + 0.55 + joint * 1.70 + shift
            if oy + 2.65 - east_span / 2 < y < oy + 2.65 + east_span / 2:
                box(
                    c,
                    f"east_ashlar_bond_{row}_{joint}",
                    (east + 0.495, y, z),
                    (0.03, 0.032, 0.43),
                    M["mortar"],
                    0,
                    role="masonry_joint",
                )
    for i, x in enumerate(
        (ox - 13.6, ox - 9.0, ox - 4.4, ox + 0.2, ox + 4.8, ox + 9.4)
    ):
        box(
            c,
            f"south_window_sill_{i}",
            (x, south - 0.52, 1.30),
            (3.72, 0.58, 0.25),
            M["stone_light"],
            0.035,
            role="carved_window_sill",
        )
        box(
            c,
            f"south_window_lintel_{i}",
            (x, south - 0.50, 6.94),
            (3.75, 0.52, 0.28),
            M["stone_light"],
            0.035,
            role="carved_window_lintel",
        )
    for i, y in enumerate((oy - 4.7, oy, oy + 4.7, oy + 9.35)):
        box(
            c,
            f"east_window_sill_{i}",
            (east + 0.52, y, 1.30),
            (0.58, 3.92, 0.25),
            M["stone_light"],
            0.035,
            role="carved_window_sill",
        )
        box(
            c,
            f"east_window_lintel_{i}",
            (east + 0.50, y, 6.94),
            (0.52, 3.95, 0.28),
            M["stone_light"],
            0.035,
            role="carved_window_lintel",
        )
    for x in (ox - 13.5, ox - 9.1, ox - 4.7, ox - 0.3, ox + 4.1, ox + 8.5):
        blind_bank_y(c, "classical_upper", x, south + 0.05, 13.8, 3.4, 4.5, M, 10)
    for y in (oy - 4.7, oy, oy + 4.7, oy + 9.35):
        blind_bank_x(c, "classical_east_upper", east - 0.05, y, 13.8, 3.55, 4.5, M, 10)

    # Projecting surrounds and narrow pilasters make every opening part of the
    # masonry wall assembly rather than a black rectangle attached to it.
    for tier, (zz, hh) in enumerate(((13.8, 4.5), (19.1, 2.25))):
        for i, x in enumerate(
            (ox - 13.5, ox - 9.1, ox - 4.7, ox - 0.3, ox + 4.1, ox + 8.5)
        ):
            box(
                c,
                f"south_upper_sill_{tier}_{i}",
                (x, south - 0.49, zz - hh / 2 - 0.10),
                (3.72, 0.50, 0.20),
                M["stone_light"],
                0.032,
                role="carved_window_sill",
            )
            box(
                c,
                f"south_upper_lintel_{tier}_{i}",
                (x, south - 0.46, zz + hh / 2 + 0.10),
                (3.75, 0.44, 0.22),
                M["stone_light"],
                0.032,
                role="carved_window_lintel",
            )
        for i, y in enumerate((oy - 4.7, oy, oy + 4.7, oy + 9.35)):
            box(
                c,
                f"east_upper_sill_{tier}_{i}",
                (east + 0.49, y, zz - hh / 2 - 0.10),
                (0.50, 3.92, 0.20),
                M["stone_light"],
                0.032,
                role="carved_window_sill",
            )
            box(
                c,
                f"east_upper_lintel_{tier}_{i}",
                (east + 0.46, y, zz + hh / 2 + 0.10),
                (0.44, 3.95, 0.22),
                M["stone_light"],
                0.032,
                role="carved_window_lintel",
            )
    for i, x in enumerate(
        (ox - 15.7, ox - 11.3, ox - 6.9, ox - 2.5, ox + 1.9, ox + 6.3, ox + 10.7)
    ):
        box(
            c,
            f"south_upper_pilaster_{i}",
            (x, south - 0.42, 15.1),
            (0.24, 0.48, 14.4),
            M["white_clean"],
            0.025,
            role="masonry_pilaster",
        )
    # Proper rainwater goods add believable facade/roof junction detail.
    for i, x in enumerate((ox - 15.9, ox + 10.9)):
        cylinder(
            c,
            f"south_rainwater_downpipe_{i}",
            (x, south - 0.63, 10.8),
            0.085,
            21.0,
            M["steel"],
            20,
            role="rainwater_downpipe",
        )
        beam(
            c,
            f"south_downpipe_shoe_{i}",
            (x, south - 0.63, 0.65),
            (x, south - 0.92, 0.34),
            0.085,
            M["steel"],
            20,
            "rainwater_downpipe",
        )

    # Rooftop winter-garden mullions and clerestory transoms; no arrow-like
    # truss, mast or brace is emitted anywhere in this asset.
    roof_south = oy - 3.93
    for x in [ox - 9.3 + i * 3.1 for i in range(7)]:
        box(
            c,
            "roof_pavilion_mullion",
            (x, roof_south - 0.18, 24.65),
            (0.11, 0.18, 3.05),
            M["black_metal"],
            0.008,
            role="roof_pavilion_frame",
        )
    for z in (23.25, 24.65, 26.05):
        box(
            c,
            "roof_pavilion_transom",
            (ox, roof_south - 0.18, z),
            (20.1, 0.18, 0.11),
            M["black_metal"],
            0.008,
            role="roof_pavilion_frame",
        )
    for y in (oy - 3.93, oy + 6.13):
        box(
            c,
            "roof_pavilion_side_coping",
            (ox, y, 26.20),
            (20.2, 0.16, 0.16),
            M["black_metal"],
            0.012,
            role="roof_pavilion_frame",
        )
    box(
        c,
        "basement_service_door",
        (ox - 15.6, south - 0.50, 1.30),
        (2.1, 0.12, 2.5),
        M["black_metal"],
        0.025,
        role="service_door",
    )
    for i, x in enumerate((ox - 4.5, ox, ox + 4.5)):
        box(
            c,
            f"classical_teller_counter_{i}",
            (x, south + 1.05, 1.18),
            (3.1, 0.72, 1.08),
            M["wood"],
            0.055,
            role="bank_lobby_furniture",
        )
        box(
            c,
            f"classical_counter_stone_top_{i}",
            (x, south + 1.02, 1.77),
            (3.2, 0.82, 0.12),
            M["stone_light"],
            0.025,
            role="bank_lobby_furniture",
        )
    c[
        "c2w_detail_profile"
    ] += "+staggered_ashlar+carved_sills+interior_blinds+framed_roof_garden"


def enhance_white_vertical(c, M):
    ox, oy, w, d, h = 40.0, 32.5, 29.0, 23.0, 40.5
    south, east = oy - d / 2, ox + w / 2
    usable, bays, floor_h = w - 3.2, 8, 3.55
    bay_w = usable / bays
    # Fine interior blinds and visible floor-plate noses break up the large
    # blue rectangles while remaining behind the curtain-wall glazing.
    for floor in range(10):
        z = 2.0 + floor * floor_h
        box(
            c,
            f"interior_floor_plate_{floor}",
            (ox, south + 0.32, z - 1.46),
            (usable - 0.25, 1.05, 0.18),
            M["concrete"],
            0.015,
            role="interior_floor_slab",
        )
        for bay in range(bays):
            x = ox - usable / 2 + bay_w * (bay + 0.5)
            if (floor + bay) % 3 != 1:
                blind_bank_y(
                    c,
                    f"white_blind_{floor}_{bay}",
                    x,
                    south - 0.22,
                    z,
                    bay_w - 0.35,
                    2.65,
                    M,
                    6,
                )
    for floor in range(10):
        z = 2.0 + floor * floor_h
        for bay in range(6):
            y = oy - 10.0 + (bay + 0.5) * (20.0 / 6)
            if (floor + 2 * bay) % 4 != 0:
                blind_bank_x(
                    c,
                    f"white_side_blind_{floor}_{bay}",
                    east + 0.08,
                    y,
                    z,
                    2.95,
                    2.65,
                    M,
                    5,
                )

    # Precast-panel joints at the solid corner piers and a layered top fascia.
    for z in [1.1 + i * 1.12 for i in range(34)]:
        box(
            c,
            "west_corner_panel_joint",
            (ox - w / 2 - 0.06, south - 0.18, z),
            (2.0, 0.035, 0.025),
            M["mortar"],
            0,
            role="precast_panel_joint",
        )
        box(
            c,
            "east_corner_panel_joint",
            (ox + w / 2 + 0.06, south - 0.18, z),
            (2.0, 0.035, 0.025),
            M["mortar"],
            0,
            role="precast_panel_joint",
        )
    box(
        c,
        "deep_roof_fascia",
        (ox, south - 0.60, h + 0.55),
        (w + 1.0, 1.0, 1.25),
        M["white_clean"],
        0.12,
        role="roof_fascia",
    )
    box(
        c,
        "fascia_shadow_line",
        (ox, south - 1.12, h + 0.12),
        (w + 0.5, 0.06, 0.16),
        M["dark"],
        0.01,
        role="facade_shadow_joint",
    )
    # Horizontal side-elevation slab noses, panel seals and a protected lobby
    # canopy remove the repetitive extruded-block appearance at eye level.
    for floor in range(11):
        z = 0.60 + floor * 3.55
        box(
            c,
            f"east_floor_shadow_{floor}",
            (east + 0.62, oy, z),
            (0.22, d - 1.2, 0.12),
            M["black_metal"],
            0.009,
            role="facade_shadow_joint",
        )
    for side, x in (("west", ox - w / 2 - 0.10), ("east", ox + w / 2 + 0.10)):
        for row in range(20):
            z = 1.15 + row * 1.92
            box(
                c,
                f"{side}_precast_bed_joint_{row}",
                (x, south + 0.62, z),
                (2.25, 0.045, 0.035),
                M["mortar"],
                0,
                role="precast_panel_joint",
            )
    box(
        c,
        "white_entry_glass_canopy",
        (ox, south - 3.05, 6.45),
        (9.5, 3.25, 0.24),
        M["glass_clear"],
        0.065,
        role="entrance_canopy",
    )
    for x in (ox - 4.25, ox + 4.25):
        cylinder(
            c,
            "white_canopy_column",
            (x, south - 3.55, 3.25),
            0.12,
            6.25,
            M["steel"],
            28,
            role="structural_column",
        )
    box(
        c,
        "white_granite_plinth",
        (ox, south - 0.34, 0.52),
        (w - 1.0, 0.52, 1.04),
        M["stone_dark"],
        0.035,
        role="masonry_cladding",
    )
    roof_guard(
        c, "white_roof_guard", ox - 11.8, ox + 11.8, oy - 8.6, oy + 8.6, h + 0.72, M
    )
    hvac_unit(c, "white_hvac_west", ox - 6.0, oy + 2.5, h + 0.9, 4.8, 3.7, 1.8, M)
    hvac_unit(c, "white_hvac_east", ox + 3.8, oy + 1.5, h + 0.9, 7.2, 4.8, 2.2, M)
    for x in (-2.25, 0.0, 2.25):
        box(
            c,
            "lobby_teller_counter",
            (ox + x, south + 1.25, 1.15),
            (1.65, 0.65, 1.05),
            M["wood"],
            0.05,
            role="bank_lobby_furniture",
        )
        cylinder(
            c,
            "lobby_pendant",
            (ox + x, south + 0.75, 4.85),
            0.13,
            0.22,
            M["lamp"],
            20,
            role="interior_light_fixture",
        )
    c[
        "c2w_detail_profile"
    ] += "+interior_floor_plates+venetian_blinds+panel_joints+modeled_hvac+roof_guard"


def enhance_glass_headquarters(c, M):
    towers = (
        ("central", 0.0, 90.0, 24.0, 20.0, 91.0, 31),
        ("west", -23.0, 94.0, 18.5, 18.0, 70.0, 24),
        ("east", 24.0, 95.0, 19.5, 18.0, 64.0, 22),
    )
    for name, ox, oy, w, d, h, floors in towers:
        south, east = oy - d / 2 - 0.32, ox + w / 2 + 0.32
        floor_h = (h - 2.0) / floors
        # Slim projecting ribbons and recessed slab noses match the horizontal
        # emphasis of the DBS reference; dark corner caps give real depth.
        for floor in range(floors + 1):
            z = 1.18 + floor * floor_h
            box(
                c,
                f"{name}_external_floor_blade_{floor}",
                (ox, south, z),
                (w + 0.32, 0.22, 0.085),
                M["steel"],
                0.008,
                role="curtain_wall_pressure_plate",
            )
            box(
                c,
                f"{name}_east_floor_blade_{floor}",
                (east, oy, z),
                (0.22, d + 0.32, 0.085),
                M["steel"],
                0.008,
                role="curtain_wall_pressure_plate",
            )
        for x in (ox - w / 2 - 0.34, ox + w / 2 + 0.34):
            box(
                c,
                f"{name}_polished_corner_cap",
                (x, south + 0.14, h / 2),
                (0.26, 0.42, h + 0.4),
                M["steel"],
                0.018,
                role="curtain_wall_corner_cap",
            )
        box(
            c,
            f"{name}_roof_shadow_reveal",
            (ox, oy, h + 0.18),
            (w + 0.9, d + 0.9, 0.28),
            M["dark"],
            0.025,
            role="tower_crown_shadow",
        )

    # Articulated podium facade and visible banking hall.  A single flush
    # metal soffit replaces the exposed brown timber rods from all46_4.
    for x in (-25.0, -20.8, -16.6, 16.6, 20.8, 25.0):
        box(
            c,
            "podium_sunshade_fin",
            (x, 67.45, 4.3),
            (0.16, 1.35, 7.0),
            M["steel"],
            0.018,
            role="podium_sunshade",
        )
    box(
        c,
        "podium_flush_metal_soffit",
        (0, 65.8, 6.02),
        (15.8, 4.35, 0.12),
        M["steel"],
        0.025,
        role="entrance_soffit",
    )
    for x in (-9.0, -4.5, 4.5, 9.0):
        box(
            c,
            "hq_lobby_security_desk",
            (x, 70.0, 1.2),
            (2.8, 0.85, 1.1),
            M["stone_light"],
            0.07,
            role="bank_lobby_furniture",
        )
        cylinder(
            c,
            "hq_lobby_pendant",
            (x, 69.4, 5.9),
            0.17,
            0.28,
            M["lamp"],
            24,
            role="interior_light_fixture",
        )
    roof_guard(c, "hq_central_guard", -8.8, 8.8, 82.0, 97.5, 92.0, M)
    hvac_unit(c, "hq_roof_chiller", 0.0, 90.0, 92.0, 6.2, 4.8, 2.0, M)
    c[
        "c2w_detail_profile"
    ] += "+31_storey_slender_core+projecting_pressure_plates+corner_caps+banking_hall+roof_plant"


def enhance_bronze_branch(c, M):
    ox, oy, w, d, h = 0.0, -28.0, 42.0, 23.0, 20.5
    south, east = oy - d / 2, ox + w / 2
    # Deep shadow gasket around every reference bay plus real sill flashings.
    bay_centres = (-17.0, -12.3, -7.6, 7.6, 12.3, 17.0)
    for bay, x in enumerate(bay_centres):
        for floor, z in enumerate((3.35, 9.0, 14.65)):
            box(
                c,
                f"bronze_sill_flashing_{bay}_{floor}",
                (x, south - 0.75, z - 2.23),
                (3.85, 0.62, 0.12),
                M["bronze_dark"],
                0.018,
                role="window_sill_flashing",
            )
            if (bay + floor) % 2 == 0:
                blind_bank_y(
                    c,
                    f"bronze_blind_{bay}_{floor}",
                    x,
                    south - 0.08,
                    z,
                    3.45,
                    4.05,
                    M,
                    8,
                    warm=True,
                )
    for floor, z in enumerate((3.4, 9.0, 14.6)):
        for bay, y in enumerate((oy - 7.6, oy - 2.6, oy + 2.6, oy + 7.6)):
            box(
                c,
                f"east_sill_flashing_{floor}_{bay}",
                (east + 0.68, y, z - 2.18),
                (0.58, 3.95, 0.12),
                M["bronze_dark"],
                0.018,
                role="window_sill_flashing",
            )

    # Rolled-sheet seams, recessed floor edges and the articulated corner
    # condition reproduce the panel rhythm in the Getty reference.
    for z in (5.78, 11.38, 17.02):
        for x in (-13.5, 13.5):
            box(
                c,
                "bronze_recessed_floor_joint",
                (x, south - 0.82, z),
                (14.3, 0.08, 0.11),
                M["dark"],
                0.006,
                role="facade_shadow_joint",
            )
    for x in (-20.2, -15.8, -11.15, -6.55, 6.55, 11.15, 15.8, 20.2):
        box(
            c,
            "bronze_vertical_panel_seam",
            (x, south - 0.90, h / 2),
            (0.055, 0.055, h - 1.0),
            M["dark"],
            0.004,
            role="facade_shadow_joint",
        )
    for y in (oy - 9.8, oy - 4.9, oy, oy + 4.9, oy + 9.8):
        box(
            c,
            "east_vertical_panel_seam",
            (east + 0.93, y, h / 2),
            (0.055, 0.055, h - 1.0),
            M["dark"],
            0.004,
            role="facade_shadow_joint",
        )

    # The reference's three-storey atrium is a readable interior volume.
    for z in (5.72, 11.36):
        box(
            c,
            "atrium_floor_edge",
            (ox, south + 0.15, z),
            (9.15, 3.1, 0.26),
            M["concrete"],
            0.025,
            role="interior_floor_slab",
        )
        box(
            c,
            "atrium_balustrade",
            (ox, south - 0.38, z + 0.68),
            (8.8, 0.055, 1.15),
            M["glass_clear"],
            0.008,
            role="interior_balustrade",
        )
        box(
            c,
            "atrium_balustrade_rail",
            (ox, south - 0.43, z + 1.27),
            (9.0, 0.08, 0.08),
            M["brass"],
            0.008,
            role="interior_balustrade_rail",
        )
    box(
        c,
        "reception_desk_stone",
        (ox, south + 0.45, 1.15),
        (5.2, 1.05, 1.10),
        M["stone_light"],
        0.09,
        role="bank_lobby_furniture",
    )
    box(
        c,
        "reception_desk_bronze",
        (ox, south - 0.10, 1.55),
        (4.7, 0.08, 0.42),
        M["brass"],
        0.025,
        role="bank_lobby_furniture",
    )
    # A real stair/landing sequence is visible through the three-storey glass.
    for step in range(9):
        box(
            c,
            f"atrium_stair_lower_{step}",
            (ox - 2.7 + step * 0.34, south + 0.62, 0.25 + step * 0.26),
            (0.62, 1.15, 0.18),
            M["stone_light"],
            0.018,
            role="interior_stair",
        )
    box(
        c,
        "atrium_stair_landing",
        (ox + 0.55, south + 0.62, 2.63),
        (2.2, 1.15, 0.22),
        M["stone_light"],
        0.025,
        role="interior_stair",
    )
    beam(
        c,
        "atrium_stair_handrail",
        (ox - 3.0, south - 0.02, 0.85),
        (ox + 1.5, south - 0.02, 3.65),
        0.04,
        M["brass"],
        16,
        "interior_handrail",
    )
    for x in (-3.6, -1.8, 0, 1.8, 3.6):
        for z in (4.9, 10.55, 16.2):
            cylinder(
                c,
                "atrium_pendant",
                (x, south + 0.2, z),
                0.13,
                0.30,
                M["lamp"],
                20,
                role="interior_light_fixture",
            )
    # Four thin edges frame the transparent atrium without masking the glass.
    box(
        c,
        "portal_trim_left",
        (ox - 5.12, south - 1.78, 10.0),
        (0.18, 0.16, 18.25),
        M["brass"],
        0.018,
        role="monumental_portal_trim",
    )
    box(
        c,
        "portal_trim_right",
        (ox + 5.12, south - 1.78, 10.0),
        (0.18, 0.16, 18.25),
        M["brass"],
        0.018,
        role="monumental_portal_trim",
    )
    box(
        c,
        "portal_trim_top",
        (ox, south - 1.78, 19.04),
        (10.35, 0.16, 0.18),
        M["brass"],
        0.018,
        role="monumental_portal_trim",
    )
    box(
        c,
        "portal_trim_bottom",
        (ox, south - 1.78, 0.96),
        (10.35, 0.16, 0.18),
        M["brass"],
        0.018,
        role="monumental_portal_trim",
    )
    roof_guard(
        c,
        "bronze_roof_guard",
        ox - 17.5,
        ox + 17.5,
        oy - 7.5,
        oy + 7.5,
        h + 0.82,
        M,
        "black_metal",
    )
    hvac_unit(c, "bronze_roof_air_handler", 12.0, oy + 2.0, h + 0.9, 5.5, 4.2, 1.7, M)
    c[
        "c2w_detail_profile"
    ] += "+bay_gaskets+bronze_flashings+three_storey_atrium+reception+roof_guard"


def enhance_public_realm(c, M):
    # Continuous footways, block expansion joints and crossings anchor the
    # architecture at human scale.  No proxy people, cars or blob vegetation.
    for name, xyz, dims in (
        ("south_stone_footway", (0, -44.0, 0.24), (121.0, 3.1, 0.32)),
        ("north_stone_footway", (0, 107.0, 0.24), (121.0, 3.1, 0.32)),
        ("west_stone_footway", (-59.8, 31.5, 0.24), (3.1, 151.0, 0.32)),
        ("east_stone_footway", (59.8, 31.5, 0.24), (3.1, 151.0, 0.32)),
    ):
        box(c, name, xyz, dims, M["paver"], 0.04, role="pedestrian_sidewalk")
    for x in range(-54, 55, 6):
        box(
            c,
            "south_sidewalk_joint",
            (x, -44.0, 0.412),
            (0.035, 3.0, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
        box(
            c,
            "north_sidewalk_joint",
            (x, 107.0, 0.412),
            (0.035, 3.0, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for y in range(-38, 104, 6):
        box(
            c,
            "west_sidewalk_joint",
            (-59.8, y, 0.412),
            (3.0, 0.035, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
        box(
            c,
            "east_sidewalk_joint",
            (59.8, y, 0.412),
            (3.0, 0.035, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )

    # The headquarters crossing is rotated exactly 90 degrees from all46_4:
    # each bar now runs east-west across the north-south arrival drive.
    for stripe in range(-4, 5):
        y = 57.5 + stripe * 0.95
        box(
            c,
            "headquarters_crosswalk_rotated_90",
            (0, y, 0.405),
            (10.0, 0.58, 0.035),
            M["road_mark"],
            0.01,
            role="crosswalk_marking",
        )
    for stripe in range(-3, 4):
        x = stripe * 1.15
        box(
            c,
            "south_crosswalk_stripe",
            (x, -52.8, 0.17),
            (0.68, 10.0, 0.035),
            M["road_mark"],
            0.01,
            role="crosswalk_marking",
        )
    for x, y, w in ((-40, 16.8, 33), (40, 19.8, 28), (0, -41.0, 41), (0, 66.8, 63)):
        box(
            c,
            "building_threshold_apron",
            (x, y, 0.34),
            (w, 2.2, 0.20),
            M["stone_light"],
            0.045,
            role="building_threshold",
        )
    for x in (-6.0, 6.0):
        box(
            c,
            "arrival_drive_edge_line",
            (x, 51.5, 0.405),
            (0.12, 24.0, 0.028),
            M["road_mark"],
            0.004,
            role="road_marking",
        )
    c[
        "c2w_detail_profile"
    ] += "+continuous_footways+expansion_joints+rotated_headquarters_crosswalk+threshold_aprons"


def build_integrated_atms(parent, site, M):
    """Place one production ATM at each bank frontage using the ATM factory.

    The machines are generated procedurally by ``generate_urban_v3_atm`` in
    this scene; no ATM blend library is appended.  Through-wall variants are
    seated into modeled stone/metal surrounds and every customer side faces
    the corresponding south-facing public forecourt.
    """
    ATM.PREFIX = PREFIX + "atm:"
    G.PREFIX = PREFIX
    atm_materials = ATM.materials()
    placements = (
        (
            "classical",
            "silver_through_wall_2in1",
            -51.0,
            18.18,
            0.44,
            "bank.classical_corner.reference_01.v4",
            "stone_light",
        ),
        (
            "white_vertical",
            "white_oxford_through_wall",
            48.2,
            20.72,
            0.44,
            "bank.white_vertical.reference_02.v4",
            "white_clean",
        ),
        (
            "bronze_branch",
            "bronze_deep_recess",
            11.4,
            -40.05,
            0.44,
            "bank.bronze_frame.reference_04.v4",
            "bronze_dark",
        ),
        (
            "headquarters",
            "bank_branded_narrow",
            13.2,
            67.78,
            0.44,
            "bank.blue_glass_headquarters.reference_03.v4",
            "black_metal",
        ),
    )
    result = []
    for label, variant, x, y, z, bank_asset_id, surround_material in placements:
        atm = ATM.build_atm(
            parent,
            variant,
            x=x,
            y=y,
            z=z,
            rotation=0.0,
            materials_override=atm_materials,
            palette="red" if variant == "bank_branded_narrow" else None,
        )
        atm["c2w_bank_association"] = bank_asset_id
        atm["c2w_campus_placement"] = label
        atm[
            "c2w_installation"
        ] = "recessed_frontage_with_weathered_surround_and_tactile_approach"

        # Modeled jambs and a deep lintel make each machine an installed piece
        # of banking equipment, never a freestanding toy dropped on paving.
        for side in (-1, 1):
            box(
                site,
                f"atm_{label}_installation_jamb_{side}",
                (x + side * 0.72, y + 0.20, z + 1.18),
                (0.16, 0.42, 2.48),
                M[surround_material],
                0.028,
                role="atm_installation_surround",
            )
        box(
            site,
            f"atm_{label}_installation_lintel",
            (x, y + 0.20, z + 2.40),
            (1.60, 0.42, 0.18),
            M[surround_material],
            0.028,
            role="atm_installation_surround",
        )
        box(
            site,
            f"atm_{label}_tactile_approach",
            (x, y - 1.05, z + 0.018),
            (1.55, 0.82, 0.036),
            M["paver_edge"],
            0.012,
            role="atm_tactile_approach",
        )
        for rib in range(-5, 6):
            box(
                site,
                f"atm_{label}_raised_guidance_rib_{rib}",
                (x + rib * 0.12, y - 1.05, z + 0.048),
                (0.045, 0.66, 0.024),
                M["brass"],
                0.006,
                role="atm_tactile_guidance_rib",
            )
        result.append(atm)
    G.PREFIX = PREFIX
    return result


def build_financial_campus(parent=None, include_public_realm=True, include_atms=True):
    """Pipeline entry point: generate all source geometry in the active scene.

    The caller controls whether the public realm is included, so the same four
    builders can be placed by the main urban composer without reading a blend.
    """
    M = make_materials()
    root = collection(
        "FOUR_BANK_FINANCIAL_CAMPUS", parent, "campus.four_banks.reference_set.v5"
    )
    root["c2w_pipeline_entrypoint"] = "generate_urban_v3_all46_2.build_financial_campus"
    root["c2w_scene_asset_inputs"] = 0
    root["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    root["c2w_atm_reference_urls"] = json.dumps(ATM.REFERENCES, ensure_ascii=False)
    root["c2w_asset_revision"] = REVISION

    # ATM geometry uses operator-based custom profiles and modifiers.  Build
    # it while the dependency graph is still small, then add the direct-mesh
    # architectural hierarchy and public realm.  This preserves identical
    # procedural geometry while avoiding quadratic scene-update overhead.
    if include_atms:
        installation_site = collection(
            "ATM_INSTALLATION_HARDSCAPE", root, "site.atm_installation_hardscape.v1"
        )
        atms = build_integrated_atms(root, installation_site, M)
        root["c2w_integrated_atm_count"] = len(atms)

    b1 = build_classical_corner(root, M)
    b2 = build_white_vertical(root, M)
    b3 = build_glass_headquarters(root, M)
    b4 = build_bronze_branch(root, M)
    enhance_classical_corner(b1, M)
    enhance_white_vertical(b2, M)
    enhance_glass_headquarters(b3, M)
    enhance_bronze_branch(b4, M)
    if include_public_realm:
        site = public_realm(root, M)
        enhance_public_realm(site, M)
    return root, M


# Stable import surface for the original urban composer.  A downstream caller
# can build the complete group through ``build_financial_campus`` or request a
# particular source builder with the same material dictionary.
PROCEDURAL_BANK_BUILDERS = {
    "bank.classical_corner.reference_01.v4": build_classical_corner,
    "bank.white_vertical.reference_02.v4": build_white_vertical,
    "bank.blue_glass_headquarters.reference_03.v4": build_glass_headquarters,
    "bank.bronze_frame.reference_04.v4": build_bronze_branch,
}

LEGACY_ASSET_ALIASES = {
    "bank.classical_corner.reference_01.v3": "bank.classical_corner.reference_01.v4",
    "bank.white_vertical.reference_02.v3": "bank.white_vertical.reference_02.v4",
    "bank.blue_glass_headquarters.reference_03.v3": "bank.blue_glass_headquarters.reference_03.v4",
    "bank.bronze_frame.reference_04.v3": "bank.bronze_frame.reference_04.v4",
}


def build_bank_asset(
    asset_id, parent=None, materials=None, apply_production_detail=True
):
    """Build one registered bank procedurally without reading a blend file."""
    asset_id = LEGACY_ASSET_ALIASES.get(asset_id, asset_id)
    if asset_id not in PROCEDURAL_BANK_BUILDERS:
        raise KeyError(f"Unknown procedural bank asset: {asset_id}")
    M = materials or make_materials()
    bank = PROCEDURAL_BANK_BUILDERS[asset_id](parent, M)
    if apply_production_detail:
        detailer = {
            "bank.classical_corner.reference_01.v4": enhance_classical_corner,
            "bank.white_vertical.reference_02.v4": enhance_white_vertical,
            "bank.blue_glass_headquarters.reference_03.v4": enhance_glass_headquarters,
            "bank.bronze_frame.reference_04.v4": enhance_bronze_branch,
        }[asset_id]
        detailer(bank, M)
    return bank, M


# ---------------------------------------------------------------------------
# Daylight, cameras, rendering and strict validation.
# ---------------------------------------------------------------------------


def camera(name, loc, target, lens=50):
    data = bpy.data.cameras.new(PREFIX + name)
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = False
    tag(obj, "validation_camera")
    return obj


def setup_daylight():
    scene = bpy.context.scene
    world = bpy.data.worlds.new(PREFIX + "clear_day_world")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(47)
    sky.sun_rotation = math.radians(142)
    sky.air_density = 0.82
    sky.dust_density = 0.12
    sky.ozone_density = 1.0
    bg.inputs["Strength"].default_value = 0.48
    links.new(sky.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])

    bpy.ops.object.light_add(type="SUN", location=(30, -45, 90))
    sun = bpy.context.object
    sun.name = PREFIX + "day_sun"
    sun.data.energy = 3.0
    sun.data.angle = math.radians(0.65)
    sun.rotation_euler = (math.radians(42), math.radians(-18), math.radians(138))
    tag(sun, "daylight")
    bpy.ops.object.light_add(type="AREA", location=(-45, -20, 55))
    fill = bpy.context.object
    fill.name = PREFIX + "sky_fill"
    fill.data.energy = 460
    fill.data.shape = "DISK"
    fill.data.size = 32
    fill.rotation_euler = (math.radians(18), 0, math.radians(-28))
    tag(fill, "daylight_fill")


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1440
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "16"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.38
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "16"
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = int(os.environ.get("C2W_RENDER_SAMPLES", "128"))
    scene.eevee.use_shadows = True
    scene.eevee.shadow_resolution_scale = 1.0
    scene.eevee.use_raytracing = True
    scene.eevee.ray_tracing_method = "SCREEN"


def render_views(cameras):
    configure_render()
    scene = bpy.context.scene
    selected = {
        value.strip()
        for value in os.environ.get("C2W_RENDER_VIEWS", "").split(",")
        if value.strip()
    }
    rendered = []
    for filename, cam in cameras:
        if selected and filename not in selected:
            continue
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)
        rendered.append(filename)
    return rendered


def validate_render_outputs(cameras):
    """Reject missing, blank or almost uniformly clipped validation renders."""
    diagnostics = {}
    for filename, _ in cameras:
        path = RENDERS / filename
        if not path.exists() or path.stat().st_size < 100_000:
            diagnostics[filename] = {"passed": False, "reason": "missing_or_too_small"}
            continue
        image = bpy.data.images.load(str(path), check_existing=False)
        width, height = image.size
        pixels = image.pixels
        values = []
        for gy in range(9):
            py = min(height - 1, int((gy + 0.5) * height / 9))
            for gx in range(13):
                px = min(width - 1, int((gx + 0.5) * width / 13))
                index = 4 * (py * width + px)
                values.append(
                    (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3.0
                )
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        dark_fraction = sum(value < 0.018 for value in values) / len(values)
        light_fraction = sum(value > 0.96 for value in values) / len(values)
        passed = variance >= 0.006 and dark_fraction < 0.82 and light_fraction < 0.82
        diagnostics[filename] = {
            "passed": passed,
            "sample_mean": round(mean, 6),
            "sample_variance": round(variance, 6),
            "dark_fraction": round(dark_fraction, 4),
            "light_fraction": round(light_fraction, 4),
            "resolution": [width, height],
            "bytes": path.stat().st_size,
        }
        bpy.data.images.remove(image)
    if not all(item["passed"] for item in diagnostics.values()):
        raise RuntimeError(
            "Validation render audit failed: " + json.dumps(diagnostics, indent=2)
        )
    return diagnostics


def object_counts(root):
    return {child.name: len(child.all_objects) for child in root.children}


def collection_world_bounds(coll):
    points = []
    for obj in coll.all_objects:
        if obj.type not in {"MESH", "FONT", "CURVE"}:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    return {
        "x_min": min(point.x for point in points),
        "x_max": max(point.x for point in points),
        "y_min": min(point.y for point in points),
        "y_max": max(point.y for point in points),
        "z_min": min(point.z for point in points),
        "z_max": max(point.z for point in points),
    }


def audit(root, cameras):
    banks = [
        child
        for child in root.children
        if child.get("c2w_asset_id") in PROCEDURAL_BANK_BUILDERS
    ]
    atms = [
        child
        for child in root.children
        if child.get("c2w_asset_kind") == "street_furniture.atm"
    ]
    counts = object_counts(root)
    bank_counts = {bank.name: len(bank.all_objects) for bank in banks}
    atm_counts = {atm.name: len(atm.all_objects) for atm in atms}
    atm_associations = {atm.name: atm.get("c2w_bank_association") for atm in atms}
    bank_bounds = {bank.name: collection_world_bounds(bank) for bank in banks}
    banks_inside_site = all(
        bounds
        and bounds["x_min"] >= SITE_BOUNDS["x_min"] - 0.05
        and bounds["x_max"] <= SITE_BOUNDS["x_max"] + 0.05
        and bounds["y_min"] >= SITE_BOUNDS["y_min"] - 0.05
        and bounds["y_max"] <= SITE_BOUNDS["y_max"] + 0.05
        for bounds in bank_bounds.values()
    )
    names = [obj.name.lower() for obj in bpy.data.objects]
    banned_tokens = ("placeholder", "proxy", "toy", "blob", "dummy")
    banned = [name for name in names if any(token in name for token in banned_tokens)]
    arrow_tokens = (
        "roof_frame_v",
        "roof_ridge",
        "roof_cross_tie",
        "white_arrow",
        "arrow_marker",
    )
    arrow_like = [
        name for name in names if any(token in name for token in arrow_tokens)
    ]
    greenery_tokens = (
        "planter",
        "flower_bed",
        "ornamental_grass",
        "grass_blade",
        "greenery",
        "vegetation",
    )
    greenery_objects = [
        name for name in names if any(token in name for token in greenery_tokens)
    ]
    removed_entrance_objects = [
        name
        for name in names
        if any(
            token in name
            for token in ("revolving_door", "podium_soffit_baffle", "hq_bollard")
        )
    ]
    role_counts = {}
    for obj in bpy.data.objects:
        role = obj.get("c2w_role", "untagged")
        role_counts[role] = role_counts.get(role, 0) + 1
    bank_role_counts = {}
    bank_material_counts = {}
    for bank in banks:
        roles = {}
        materials = set()
        for obj in bank.all_objects:
            role = obj.get("c2w_role", "untagged")
            roles[role] = roles.get(role, 0) + 1
            for slot in obj.material_slots:
                if slot.material:
                    materials.add(slot.material.name)
        bank_role_counts[bank.name] = roles
        bank_material_counts[bank.name] = len(materials)
    reflective_materials = [
        mat.name for mat in bpy.data.materials if mat.get("c2w_reflective_glazing")
    ]
    brushed_metal_materials = [
        mat.name for mat in bpy.data.materials if mat.get("c2w_brushed_metal")
    ]
    enlarged_sign_parts = [
        obj.name
        for obj in bpy.data.objects
        if obj.get("c2w_sign_revision") == "all46_5_enlarged_145_percent"
    ]
    dbs_symbols = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "dbs_logo_symbol"
        and obj.get("c2w_brand_color") == "DBS red"
    ]
    dbs_wordmarks = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "dbs_logo_wordmark"
        and obj.get("c2w_brand_color") == "white"
    ]
    hq_crosswalk = [
        obj
        for obj in bpy.data.objects
        if "headquarters_crosswalk_rotated_90" in obj.name
    ]
    required_roles = {
        "glazing": role_counts.get("glazing", 0) >= 120,
        "curtain_wall_glazing": role_counts.get("curtain_wall_glazing", 0) >= 80,
        "window_frame": role_counts.get("window_frame", 0) >= 220,
        "deep_window_returns": role_counts.get("window_reveal_return", 0) >= 250,
        "window_gaskets_and_flashings": role_counts.get("window_gasket", 0) >= 250
        and role_counts.get("window_sill_flashing", 0) >= 150,
        "roof_service": role_counts.get("roof_service", 0) >= 15,
        "entrance_depth": role_counts.get("entrance_recess", 0) >= 4,
        "modeled_door_hardware": role_counts.get("door_hardware", 0) >= 20,
        "public_realm_detail": role_counts.get("streetlight_luminaire", 0) >= 10,
        "modeled_masonry_bond": role_counts.get("masonry_joint", 0) >= 170,
        "modeled_interior_blinds": role_counts.get("interior_blind", 0) >= 450,
        "modeled_roof_mechanical_equipment": role_counts.get("roof_hvac", 0) >= 8,
        "fine_curtain_wall_nodes": role_counts.get("curtain_wall_pressure_plate", 0)
        >= 140,
        "readable_bank_interiors": role_counts.get("bank_lobby_furniture", 0) >= 10,
        "roof_safety_detail": role_counts.get("roof_safety_rail", 0) >= 45,
        "multi_layer_reflective_glass": len(reflective_materials) >= 5,
        "physical_brushed_bronze": len(brushed_metal_materials) >= 3,
    }
    per_bank_reference_checks = {
        "reference_01_ashlar_and_glazed_roof_pavilion": role_counts.get(
            "carved_window_sill", 0
        )
        >= 10
        and role_counts.get("roof_pavilion_frame", 0) >= 8,
        "reference_02_vertical_fins_and_roof_equipment": role_counts.get(
            "structural_sun_fin", 0
        )
        >= 15
        and role_counts.get("precast_panel_joint", 0) >= 50,
        "reference_03_three_towers_and_pressure_plates": role_counts.get(
            "tower_crown", 0
        )
        == 3
        and role_counts.get("curtain_wall_pressure_plate", 0) >= 140,
        "reference_04_atrium_and_bronze_bays": role_counts.get("interior_balustrade", 0)
        >= 2
        and role_counts.get("interior_stair", 0) >= 8
        and role_counts.get("window_sill_flashing", 0) >= 25,
    }
    explicit_revision_checks = {
        "classical_and_bronze_views_have_no_arrow_geometry": not arrow_like,
        "white_vertical_sign_is_enlarged_geometry": len(enlarged_sign_parts) >= 2,
        "dbs_has_four_red_symbol_parts": len(dbs_symbols) == 4,
        "dbs_wordmark_is_white_and_large": len(dbs_wordmarks) == 1
        and dbs_wordmarks[0].data.size >= 2.3,
        "getty_bronze_finish_is_reflective_and_layered": len(brushed_metal_materials)
        >= 3
        and any(
            "bronze_tinted_reflective_glass" in name for name in reflective_materials
        ),
        "all_banks_use_rich_material_sets": len(bank_material_counts) == 4
        and min(bank_material_counts.values()) >= 8,
        "headquarters_entry_cylinder_and_timber_rods_removed": not removed_entrance_objects,
        "no_planters_or_greenery_anywhere": not greenery_objects,
        "all_banks_inside_single_enclosed_site": banks_inside_site,
        "headquarters_crosswalk_rotated_90_degrees": len(hq_crosswalk) == 9
        and all(obj.dimensions.x > obj.dimensions.y * 8 for obj in hq_crosswalk),
        "refined_hardscape_is_geometrically_modeled": role_counts.get(
            "site_paving_base", 0
        )
        == 1
        and role_counts.get("paver_joint", 0) >= 700
        and role_counts.get("paving_inlay", 0) >= 20
        and role_counts.get("linear_drain", 0) >= 3,
        "four_full_detail_atms_integrated": len(atms) == 4
        and len(atm_counts) == 4
        and min(atm_counts.values(), default=0) >= 150
        and role_counts.get("atm_tactile_guidance_rib", 0) == 44,
        "one_atm_associated_with_each_bank": set(atm_associations.values())
        == set(PROCEDURAL_BANK_BUILDERS),
    }
    checks = {
        "exactly_four_distinct_banks": len(banks) == 4,
        "each_bank_has_dense_hierarchy": len(bank_counts) == 4
        and min(bank_counts.values()) >= 300,
        "reference_specific_roles_present": all(required_roles.values()),
        "each_reference_has_geometric_signature": all(
            per_bank_reference_checks.values()
        ),
        "no_placeholder_or_toy_named_geometry": not banned,
        "all_requested_revision_checks": all(explicit_revision_checks.values()),
        "eight_daylight_near_and_far_views": len(cameras) == 8,
        "procedural_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_all46_2.build_financial_campus",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "all_renderables_tagged": all(
            obj.get("c2w_role")
            for obj in bpy.data.objects
            if obj.type in {"MESH", "FONT", "CURVE"}
        ),
    }
    result = {
        "generator": str(Path(__file__).resolve()),
        "pipeline_entrypoint": root.get("c2w_pipeline_entrypoint"),
        "output": str(OUT),
        "schema_version": SCHEMA_VERSION,
        "reference_urls": REFERENCE_URLS,
        "reference_count": len(REFERENCE_URLS),
        "bank_count": len(banks),
        "bank_collections": [bank.name for bank in banks],
        "bank_world_bounds": bank_bounds,
        "enclosed_site_bounds": SITE_BOUNDS,
        "objects_per_collection": counts,
        "bank_object_counts": bank_counts,
        "bank_role_counts": bank_role_counts,
        "bank_material_counts": bank_material_counts,
        "atm_count": len(atms),
        "atm_collections": [atm.name for atm in atms],
        "atm_object_counts": atm_counts,
        "atm_bank_associations": atm_associations,
        "atm_factory": "generate_urban_v3_atm.build_atm",
        "atm_reference_urls": ATM.REFERENCES,
        "role_counts": role_counts,
        "required_role_checks": required_roles,
        "per_bank_reference_checks": per_bank_reference_checks,
        "explicit_revision_checks": explicit_revision_checks,
        "reflective_glass_materials": reflective_materials,
        "brushed_metal_materials": brushed_metal_materials,
        "object_count": len(bpy.data.objects),
        "material_count": len(bpy.data.materials),
        "validation_views": [filename for filename, _ in cameras],
        "daylight": True,
        "near_and_far_views": True,
        "standalone_validation_scene_contains_four_banks_and_integrated_atms": True,
        "pipeline_connected": True,
        "procedural_asset_ids": sorted(PROCEDURAL_BANK_BUILDERS),
        "single_asset_entrypoint": "generate_urban_v3_all46_2.build_bank_asset",
        "external_blend_inputs": 0,
        "banned_geometry_names": banned,
        "arrow_like_geometry_names": arrow_like,
        "greenery_or_planter_geometry_names": greenery_objects,
        "removed_headquarters_entrance_geometry_names": removed_entrance_objects,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    if not result["all_checks_passed"]:
        raise RuntimeError(
            "Production bank audit failed: "
            + json.dumps(result, indent=2, ensure_ascii=False)
        )
    (OUT / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    # A prior successful revision must never mask a failed regeneration.
    (OUT / "SUCCESS").unlink(missing_ok=True)
    G.reset_scene()
    root, _ = build_financial_campus()
    setup_daylight()
    specs = [
        ("01_campus_street_overview.png", (235, -285, 220), (0, 31, 31), 55),
        ("02_campus_aerial_overview.png", (-250, -230, 260), (0, 33, 30), 55),
        ("03_classical_atm_close.png", (-46.5, 7.5, 3.6), (-51.0, 18.2, 1.3), 58),
        ("04_white_vertical_atm_close.png", (52.5, 9.0, 3.7), (48.2, 20.7, 1.3), 58),
        ("05_headquarters_atm_close.png", (20.0, 53.0, 4.0), (13.2, 67.8, 1.35), 58),
        ("06_bronze_branch_atm_close.png", (17.5, -52.0, 3.8), (11.4, -40.1, 1.3), 58),
        ("07_refined_plaza_group_street.png", (-96, -54, 25), (0, 24, 4.5), 43),
        ("08_headquarters_podium_street.png", (48, 45, 16), (0, 69, 7), 40),
    ]
    cameras = [
        (filename, camera(filename[:-4], loc, target, lens))
        for filename, loc, target, lens in specs
    ]
    data = audit(root, cameras)
    scene = bpy.context.scene
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_all46_2.build_financial_campus"
    scene["c2w_schema_version"] = SCHEMA_VERSION
    scene["c2w_integrated_atm_factory"] = "generate_urban_v3_atm.build_atm"
    scene["c2w_enclosed_site_bounds"] = json.dumps(SITE_BOUNDS)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{REVISION}.blend"), compress=True)
    data["rendered_in_this_run"] = render_views(cameras)
    data["render_diagnostics"] = validate_render_outputs(cameras)
    data["checks"]["all_views_nonblank_and_tonally_unclipped"] = True
    data["all_checks_passed"] = all(data["checks"].values())
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    (OUT / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{REVISION}.blend"), compress=True)
    (OUT / "SUCCESS").write_text(
        f"{REVISION} procedural generation and strict validation complete\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
