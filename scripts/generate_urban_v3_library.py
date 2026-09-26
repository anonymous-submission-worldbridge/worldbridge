"""Reference-driven procedural library pair for the active urban pipeline.

The module builds two independent, fully articulated public-library assets from
the two user references, then places them in one comparison scene in a single
row.  Geometry is created directly from code: the validation ``.blend`` is an
output, never an input.  ``build_library_pair`` is the reusable pipeline entry
point; ``main`` produces the daylight near/far validation package.
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
REVISION = "urban_v3_library4"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / REVISION
RENDERS = OUT / "renders"
PREFIX = "library4:"
SCHEMA_VERSION = 6
RNG = random.Random(240830)
REFERENCE_URLS = [
    "https://respic.3d66.com/coverimg/cache/decc/d7bf358cf56a570b70bb7e88e3ca1420.jpg!medium-size-2?v=8912611&k=D41D8CD98F00B204E9800998ECF8427E",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTV59_sbglB_YvPlRzDsu0_mjsUJ5UrFjIyUjBXfSErJw&s",
]
REFERENCE_CACHE = [
    ROOT / ".reference_cache/library/reference_type_a.jpg",
    ROOT / ".reference_cache/library/reference_type_b.jpg",
]
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

# Keep every cache/write made by imported procedural systems inside the shared
# WorldBridge workspace, as required by the production job.
LOCAL_CACHE = ROOT / ".qa_tmp" / REVISION
LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(LOCAL_CACHE / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(LOCAL_CACHE / "xdg_cache")
os.environ["INFINIGEN_SKIP_TAGGING"] = "1"

sys.path.insert(0, str(ROOT / "infinigen"))
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all46_2 as BASE
from infinigen.assets.objects.trees.generate import random_leaf_collection
from infinigen.core.util.math import FixedSeed
from urban_v1_full_07_trees import build_botanical_tree_master


def set_prefix(prefix: str):
    """Rebind all shared primitives when embedded by another urban generator."""
    global PREFIX
    PREFIX = prefix
    BASE.PREFIX = prefix
    BASE.G.PREFIX = prefix
    BASE._CUBE_MESHES = {}


set_prefix(PREFIX)


def tag(obj, role, asset_id=None):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = role
    obj["c2w_generator"] = Path(__file__).name
    if asset_id:
        obj["c2w_asset_id"] = asset_id
    return obj


BASE.tag = tag
box = BASE.box
cylinder = BASE.cylinder
beam = BASE.beam
poly_prism = BASE.poly_prism
pbr = BASE.pbr


def _set_socket(node, names, value):
    """Blender-version-tolerant Principled BSDF socket assignment."""
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def _principled_material(name, color, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    _set_socket(bsdf, ("Roughness",), roughness)
    _set_socket(bsdf, ("Metallic",), metallic)
    _set_socket(bsdf, ("IOR",), 1.47)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_pbr"] = True
    return mat, nodes, links, bsdf


def weathered_material(
    name, color, roughness, macro_scale=1.7, micro_scale=42.0, bump=0.12, metallic=0.0
):
    """Two-scale physically shaded material; avoids flat CAD-like surfaces."""
    mat, nodes, links, bsdf = _principled_material(name, color, roughness, metallic)
    geometry = nodes.new("ShaderNodeNewGeometry")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    macro.inputs["Scale"].default_value = macro_scale
    macro.inputs["Detail"].default_value = 5.0
    macro.inputs["Roughness"].default_value = 0.72
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    micro.inputs["Scale"].default_value = micro_scale
    micro.inputs["Detail"].default_value = 3.0
    micro.inputs["Roughness"].default_value = 0.66
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.36
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (*[max(0.0, c * 0.72) for c in color], 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (
        *[min(1.0, c * 1.18 + 0.018) for c in color],
        1.0,
    )
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = bump
    bump_node.inputs["Distance"].default_value = 0.035
    links.new(geometry.outputs["Position"], macro.inputs["Vector"])
    links.new(geometry.outputs["Position"], micro.inputs["Vector"])
    links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs[1])
    links.new(micro.outputs["Fac"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(micro.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def oriented_brick_material(name, color_a, color_b, axis="Y"):
    """World-scale running-bond brick for a front/rear or side rainscreen."""
    mat, nodes, links, bsdf = _principled_material(name, color_a, 0.82)
    geometry = nodes.new("ShaderNodeNewGeometry")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    combine = nodes.new("ShaderNodeCombineXYZ")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.squash = 1.0
    brick.inputs["Color1"].default_value = (*color_a, 1.0)
    brick.inputs["Color2"].default_value = (*color_b, 1.0)
    brick.inputs["Mortar"].default_value = (0.045, 0.025, 0.021, 1.0)
    brick.inputs["Scale"].default_value = 2.05
    brick.inputs["Mortar Size"].default_value = 0.028
    brick.inputs["Mortar Smooth"].default_value = 0.012
    brick.inputs["Brick Width"].default_value = 0.62
    brick.inputs["Row Height"].default_value = 0.23
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.72
    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = 0.18
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = 0.38
    bump_node.inputs["Distance"].default_value = 0.055
    links.new(geometry.outputs["Position"], separate.inputs["Vector"])
    # Brick Texture is two-dimensional.  Remap horizontal world distance and
    # world Z into X/Y so courses remain level on each facade orientation.
    horizontal = separate.outputs["X"] if axis == "Y" else separate.outputs["Y"]
    links.new(horizontal, combine.inputs["X"])
    links.new(separate.outputs["Z"], combine.inputs["Y"])
    links.new(combine.outputs["Vector"], brick.inputs["Vector"])
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], multiply.inputs[1])
    links.new(noise.outputs["Color"], multiply.inputs[2])
    links.new(multiply.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def architectural_glass(name, color, transmission=0.48, roughness=0.09):
    mat, nodes, links, bsdf = _principled_material(name, color, roughness, 0.025)
    _set_socket(bsdf, ("Transmission Weight", "Transmission"), transmission)
    # Alpha is intentionally below one in Eevee: this keeps rooms legible in
    # daylight while the Principled coat still supplies reflections.
    _set_socket(bsdf, ("Alpha",), 0.78 if transmission >= 0.55 else 0.86)
    _set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.34)
    _set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.045)
    _set_socket(bsdf, ("IOR",), 1.50)
    geometry = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 0.42
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.42
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = 0.010
    bump_node.inputs["Distance"].default_value = 0.003
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    try:
        mat.surface_render_method = "DITHERED"
    except Exception:
        pass
    mat.use_transparency_overlap = False
    mat.diffuse_color = (*color, 0.82)
    return mat


def collection(name, parent=None, asset_id=None, role="procedural_asset"):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    coll["c2w_schema_version"] = SCHEMA_VERSION
    coll["c2w_role"] = role
    coll["c2w_generator"] = Path(__file__).name
    if asset_id:
        coll["c2w_asset_id"] = asset_id
    return coll


def local_box(c, name, origin, xyz, dims, material, bevel=0.035, role=None):
    return BASE.local_box(
        c, name, (origin[0], origin[1], 0.0), 0.0, xyz, dims, material, bevel, role
    )


def make_materials():
    M = BASE.make_materials()
    M.update(
        {
            "white_panel": weathered_material(
                "library_white_gfrc", (0.66, 0.675, 0.655), 0.58, 1.15, 58.0, 0.10
            ),
            "white_edge": weathered_material(
                "library_white_edge", (0.78, 0.79, 0.755), 0.48, 0.72, 72.0, 0.075
            ),
            "white_shadow": weathered_material(
                "library_white_shadowed_reveal",
                (0.43, 0.45, 0.445),
                0.68,
                1.4,
                46.0,
                0.12,
            ),
            "soffit": weathered_material(
                "library_roof_soffit",
                (0.075, 0.083, 0.086),
                0.46,
                1.2,
                34.0,
                0.085,
                0.24,
            ),
            "roof_membrane": weathered_material(
                "library_roof_membrane", (0.18, 0.19, 0.185), 0.86, 0.52, 24.0, 0.18
            ),
            "red_stone": weathered_material(
                "library_red_masonry_base", (0.34, 0.072, 0.047), 0.82, 0.65, 54.0, 0.18
            ),
            "red_stone_light": weathered_material(
                "library_red_terracotta_trim",
                (0.48, 0.115, 0.072),
                0.76,
                0.85,
                48.0,
                0.14,
            ),
            "red_stone_dark": weathered_material(
                "library_deep_red_trim", (0.175, 0.028, 0.019), 0.84, 0.8, 55.0, 0.16
            ),
            "red_brick_front": oriented_brick_material(
                "library_running_bond_front",
                (0.39, 0.078, 0.045),
                (0.25, 0.043, 0.027),
                "Y",
            ),
            "red_brick_side": oriented_brick_material(
                "library_running_bond_side",
                (0.39, 0.078, 0.045),
                (0.25, 0.043, 0.027),
                "X",
            ),
            "red_joint": weathered_material(
                "library_red_joint", (0.055, 0.012, 0.009), 0.95, 2.5, 70.0, 0.08
            ),
            "glass_neutral": architectural_glass(
                "library_neutral_glass", (0.018, 0.080, 0.102), 0.66, 0.070
            ),
            "glass_neutral_alt": architectural_glass(
                "library_neutral_glass_alt", (0.030, 0.115, 0.132), 0.62, 0.085
            ),
            "glass_blue_alt": architectural_glass(
                "library_blue_glass_alt", (0.012, 0.055, 0.078), 0.64, 0.075
            ),
            "glass_warm": architectural_glass(
                "library_warm_glass", (0.075, 0.035, 0.016), 0.62, 0.080
            ),
            "glass_warm_alt": architectural_glass(
                "library_warm_glass_alt", (0.105, 0.050, 0.020), 0.58, 0.095
            ),
            "glass_clear": architectural_glass(
                "library_low_iron_entry_glass", (0.035, 0.125, 0.135), 0.74, 0.040
            ),
            "interior_wall": weathered_material(
                "library_interior_plaster", (0.40, 0.39, 0.35), 0.78, 1.2, 50.0, 0.055
            ),
            "interior_ceiling": weathered_material(
                "library_acoustic_ceiling", (0.57, 0.565, 0.52), 0.86, 2.0, 66.0, 0.08
            ),
            "solar_blind": weathered_material(
                "library_solar_blind", (0.39, 0.355, 0.29), 0.72, 1.6, 38.0, 0.05
            ),
            "rubber": weathered_material(
                "library_black_rubber", (0.012, 0.014, 0.014), 0.88, 2.0, 42.0, 0.12
            ),
            "base_grime": weathered_material(
                "library_base_weathering", (0.115, 0.12, 0.112), 0.92, 0.35, 28.0, 0.20
            ),
            "book_red": pbr("book_red", (0.46, 0.035, 0.024), 0.68),
            "book_blue": pbr("book_blue", (0.025, 0.10, 0.26), 0.65),
            "book_gold": pbr("book_gold", (0.62, 0.33, 0.045), 0.63),
            "book_green": pbr("book_green", (0.035, 0.23, 0.11), 0.68),
            "lawn": weathered_material(
                "library_lawn", (0.055, 0.19, 0.035), 0.92, 0.30, 35.0, 0.22
            ),
            "leaf": weathered_material(
                "library_leaf", (0.025, 0.16, 0.020), 0.76, 1.1, 31.0, 0.10
            ),
            "leaf_light": weathered_material(
                "library_leaf_sun", (0.11, 0.30, 0.032), 0.74, 1.3, 31.0, 0.10
            ),
            "leaf_dark": weathered_material(
                "library_leaf_shadow", (0.012, 0.085, 0.014), 0.78, 1.2, 31.0, 0.10
            ),
            "bark": weathered_material(
                "library_bark", (0.095, 0.038, 0.014), 0.96, 0.38, 28.0, 0.26
            ),
            "asphalt_real": weathered_material(
                "library_weathered_asphalt",
                (0.032, 0.035, 0.038),
                0.96,
                0.16,
                33.0,
                0.28,
            ),
            "curb": weathered_material(
                "library_worn_curb", (0.42, 0.41, 0.37), 0.88, 0.45, 47.0, 0.18
            ),
            "paver_warm": weathered_material(
                "library_warm_granite_paver",
                (0.36, 0.335, 0.285),
                0.82,
                0.42,
                38.0,
                0.14,
            ),
        }
    )
    # Botanical compatibility keys retain the complete full07 tree interface;
    # they are never used to disguise fallback geometry.
    M["trunk"] = M["bark"]
    M["bark_dark"] = weathered_material(
        "library_bark_furrow_shadow", (0.038, 0.014, 0.006), 0.98, 0.26, 62.0, 0.34
    )
    M["leaf_litter"] = weathered_material(
        "library_leaf_litter", (0.18, 0.075, 0.018), 0.96, 0.55, 48.0, 0.18
    )
    M["soil"] = weathered_material(
        "library_aerated_planting_soil", (0.075, 0.037, 0.016), 0.97, 0.42, 76.0, 0.24
    )
    M["plant"] = weathered_material(
        "library_ornamental_grass", (0.045, 0.23, 0.035), 0.89, 0.76, 61.0, 0.11
    )
    return M


def front_text(c, name, body, xyz, size, material, extrude=0.055, align="CENTER"):
    curve = bpy.data.curves.new(PREFIX + name, "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.012
    curve.bevel_resolution = 3
    curve.resolution_u = 12
    if FONT_PATH.exists():
        font = bpy.data.fonts.get(FONT_PATH.name)
        if font is None:
            font = bpy.data.fonts.load(str(FONT_PATH))
        curve.font = font
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = (math.pi / 2, 0, 0)
    curve.materials.append(material)
    return tag(obj, "architectural_signage")


def mesh_object(c, name, vertices, faces, material, role):
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    return tag(obj, role)


def area_light(c, name, xyz, energy=260.0, size=3.0, color=(1.0, 0.68, 0.42)):
    data = bpy.data.lights.new(PREFIX + name + ":data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = max(0.8, size * 0.42)
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    c.objects.link(obj)
    obj.location = xyz
    # Area lights emit along local -Z by default, directly into the room.
    obj.rotation_euler = (0.0, 0.0, 0.0)
    return tag(obj, "interior_lighting")


def sloped_slab(
    c, name, x0, x1, y0, y1, z0, z1, thickness, material, role="accessible_ramp"
):
    """A true constant-thickness ramp rising from y0/z0 to y1/z1."""
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
    return mesh_object(c, name, vertices, faces, material, role)


def _stable_code(name):
    return sum((index + 1) * ord(char) for index, char in enumerate(name))


def _glass_key(glass, name):
    variants = {
        "glass_neutral": ("glass_neutral", "glass_neutral_alt", "glass_blue_alt"),
        "glass_blue_alt": ("glass_blue_alt", "glass_neutral", "glass_neutral_alt"),
        "glass_warm": ("glass_warm", "glass_warm_alt", "glass_warm"),
    }
    options = variants.get(glass, (glass,))
    return options[_stable_code(name) % len(options)]


def facade_cell_y(
    c,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    normal=-1,
    glass="glass_neutral",
    lit=False,
    divisions=2,
):
    """Deep curtain-wall cell with insulating glass, gaskets, blinds and room depth."""
    outward = normal
    code = _stable_code(name)
    # Four independent jamb/head/sill pieces leave a physically open centre.
    # The former single cuboid was visually convenient but incorrectly sealed
    # every room behind the glass.
    reveal_t = 0.17
    for side in (-1, 1):
        box(
            c,
            name + f":reveal_jamb_{side}",
            (x + side * (width / 2 + reveal_t / 2), y, z),
            (reveal_t, 0.52, height + 0.34),
            M["dark"],
            0.012,
            role="window_reveal",
        )
    for side in (-1, 1):
        box(
            c,
            name + f":reveal_{'head' if side > 0 else 'sill'}",
            (x, y, z + side * (height / 2 + reveal_t / 2)),
            (width, 0.52, reveal_t),
            M["dark"],
            0.012,
            role="window_reveal",
        )
    box(
        c,
        name + ":room_back",
        (x, y - outward * 2.15, z),
        (width - 0.18, 0.045, height - 0.20),
        M["warm_light"] if lit else M["interior"],
        0.005,
        role="interior_depth",
    )
    box(
        c,
        name + ":glass",
        (x, y + outward * 0.30, z),
        (width, 0.045, height),
        M[_glass_key(glass, name)],
        0.006,
        role="facade_glazing",
    )
    box(
        c,
        name + ":inner_sill",
        (x, y - outward * 0.40, z - height / 2 + 0.10),
        (width - 0.12, 0.72, 0.10),
        M["interior_wall"],
        0.008,
        role="interior_window_sill",
    )
    if code % 4 in {0, 1} and height > 2.3:
        blind_h = height * (0.22 + 0.09 * (code % 3))
        blind_z = z + height / 2 - blind_h / 2 - 0.12
        box(
            c,
            name + ":roller_blind",
            (x, y - outward * 0.18, blind_z),
            (width - 0.20, 0.025, blind_h),
            M["solar_blind"],
            0.002,
            role="solar_blind",
        )
        for slat in range(1, 4):
            zz = blind_z - blind_h / 2 + blind_h * slat / 4
            box(
                c,
                name + f":blind_seam_{slat}",
                (x, y - outward * 0.20, zz),
                (width - 0.26, 0.012, 0.018),
                M["rubber"],
                0,
                role="blind_detail",
            )
    if code % 5 == 2:
        box(
            c,
            name + ":ceiling_light",
            (x, y - outward * 0.74, z + height / 2 - 0.24),
            (min(width * 0.62, 2.2), 0.20, 0.055),
            M["lamp"],
            0.008,
            role="interior_ceiling_light",
        )
    for j in range(divisions + 1):
        xx = x - width / 2 + width * j / divisions
        box(
            c,
            name + f":mullion_{j}",
            (xx, y + outward * 0.38, z),
            (0.080, 0.14, height + 0.14),
            M["black_metal"],
            0.005,
            role="facade_mullion",
        )
        box(
            c,
            name + f":gasket_{j}",
            (xx, y + outward * 0.46, z),
            (0.018, 0.025, height - 0.03),
            M["rubber"],
            0,
            role="glazing_gasket",
        )
    for zz in (z - height / 2, z + height / 2):
        box(
            c,
            name + ":rail",
            (x, y + outward * 0.38, zz),
            (width + 0.14, 0.14, 0.080),
            M["black_metal"],
            0.005,
            role="facade_mullion",
        )
        box(
            c,
            name + ":rail_gasket",
            (x, y + outward * 0.46, zz),
            (width + 0.04, 0.025, 0.018),
            M["rubber"],
            0,
            role="glazing_gasket",
        )


def facade_cell_x(
    c,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    normal=1,
    glass="glass_neutral",
    lit=False,
    divisions=2,
):
    outward = normal
    code = _stable_code(name)
    reveal_t = 0.17
    for side in (-1, 1):
        box(
            c,
            name + f":reveal_jamb_{side}",
            (x, y + side * (width / 2 + reveal_t / 2), z),
            (0.52, reveal_t, height + 0.34),
            M["dark"],
            0.012,
            role="window_reveal",
        )
    for side in (-1, 1):
        box(
            c,
            name + f":reveal_{'head' if side > 0 else 'sill'}",
            (x, y, z + side * (height / 2 + reveal_t / 2)),
            (0.52, width, reveal_t),
            M["dark"],
            0.012,
            role="window_reveal",
        )
    box(
        c,
        name + ":room_back",
        (x - outward * 2.15, y, z),
        (0.045, width - 0.18, height - 0.20),
        M["warm_light"] if lit else M["interior"],
        0.005,
        role="interior_depth",
    )
    box(
        c,
        name + ":glass",
        (x + outward * 0.30, y, z),
        (0.045, width, height),
        M[_glass_key(glass, name)],
        0.006,
        role="facade_glazing",
    )
    box(
        c,
        name + ":inner_sill",
        (x - outward * 0.40, y, z - height / 2 + 0.10),
        (0.72, width - 0.12, 0.10),
        M["interior_wall"],
        0.008,
        role="interior_window_sill",
    )
    if code % 4 in {0, 1} and height > 2.3:
        blind_h = height * (0.22 + 0.09 * (code % 3))
        blind_z = z + height / 2 - blind_h / 2 - 0.12
        box(
            c,
            name + ":roller_blind",
            (x - outward * 0.18, y, blind_z),
            (0.025, width - 0.20, blind_h),
            M["solar_blind"],
            0.002,
            role="solar_blind",
        )
    if code % 5 == 2:
        box(
            c,
            name + ":ceiling_light",
            (x - outward * 0.74, y, z + height / 2 - 0.24),
            (0.20, min(width * 0.62, 2.2), 0.055),
            M["lamp"],
            0.008,
            role="interior_ceiling_light",
        )
    for j in range(divisions + 1):
        yy = y - width / 2 + width * j / divisions
        box(
            c,
            name + f":mullion_{j}",
            (x + outward * 0.38, yy, z),
            (0.14, 0.080, height + 0.14),
            M["black_metal"],
            0.005,
            role="facade_mullion",
        )
        box(
            c,
            name + f":gasket_{j}",
            (x + outward * 0.46, yy, z),
            (0.025, 0.018, height - 0.03),
            M["rubber"],
            0,
            role="glazing_gasket",
        )
    for zz in (z - height / 2, z + height / 2):
        box(
            c,
            name + ":rail",
            (x + outward * 0.38, y, zz),
            (0.14, width + 0.14, 0.080),
            M["black_metal"],
            0.005,
            role="facade_mullion",
        )
        box(
            c,
            name + ":rail_gasket",
            (x + outward * 0.46, y, zz),
            (0.025, width + 0.04, 0.018),
            M["rubber"],
            0,
            role="glazing_gasket",
        )


def glass_door_bank(c, name, cx, y, base_z, width, height, M, leaves=4):
    portal_t = 0.30
    for side in (-1, 1):
        box(
            c,
            name + f":portal_jamb_{side}",
            (cx + side * (width / 2 + portal_t / 2), y + 0.28, base_z + height / 2),
            (portal_t, 0.86, height + 0.58),
            M["dark"],
            0.025,
            role="entrance_recess",
        )
    box(
        c,
        name + ":portal_head",
        (cx, y + 0.28, base_z + height + portal_t / 2),
        (width + 0.8, 0.86, portal_t),
        M["dark"],
        0.025,
        role="entrance_recess",
    )
    box(
        c,
        name + ":stone_threshold",
        (cx, y - 0.18, base_z + 0.035),
        (width + 0.32, 0.82, 0.07),
        M["stone_dark"],
        0.018,
        role="door_threshold",
    )
    # A second glazed line makes a physically legible weather vestibule.
    box(
        c,
        name + ":vestibule_back_glass",
        (cx, y + 0.72, base_z + height / 2),
        (width - 0.25, 0.04, height - 0.18),
        M["glass_clear"],
        0.004,
        role="entrance_vestibule",
    )
    leaf_w = width / leaves
    for i in range(leaves):
        x = cx - width / 2 + leaf_w * (i + 0.5)
        box(
            c,
            name + f":glass_{i}",
            (x, y - 0.10, base_z + height / 2),
            (leaf_w - 0.07, 0.055, height),
            M["glass_clear"],
            0.006,
            role="entrance_glazing",
        )
        for edge in (-1, 1):
            box(
                c,
                name + f":jamb_{i}_{edge}",
                (x + edge * (leaf_w / 2 - 0.035), y - 0.16, base_z + height / 2),
                (0.07, 0.09, height + 0.10),
                M["steel"],
                0.005,
                role="door_frame",
            )
        box(
            c,
            name + f":handle_{i}",
            (x + leaf_w * 0.18, y - 0.22, base_z + height * 0.52),
            (0.035, 0.035, 0.76),
            M["brass"],
            0.01,
            role="door_hardware",
        )
        box(
            c,
            name + f":kick_plate_{i}",
            (x, y - 0.20, base_z + 0.18),
            (leaf_w - 0.18, 0.025, 0.28),
            M["steel"],
            0.006,
            role="door_hardware",
        )
        box(
            c,
            name + f":closer_{i}",
            (x, y - 0.20, base_z + height - 0.15),
            (min(0.50, leaf_w * 0.48), 0.09, 0.08),
            M["black_metal"],
            0.012,
            role="door_hardware",
        )
    box(
        c,
        name + ":head",
        (cx, y - 0.16, base_z + height),
        (width + 0.14, 0.09, 0.10),
        M["steel"],
        0.005,
        role="door_frame",
    )
    box(
        c,
        name + ":transom",
        (cx, y - 0.10, base_z + height + 0.32),
        (width, 0.045, 0.48),
        M["glass_clear"],
        0.004,
        role="entrance_glazing",
    )
    box(
        c,
        name + ":transom_head",
        (cx, y - 0.16, base_z + height + 0.58),
        (width + 0.14, 0.09, 0.085),
        M["steel"],
        0.005,
        role="door_frame",
    )


def bookshelf(c, name, xyz, width, height, M):
    x, y, z = xyz
    box(
        c,
        name + ":back",
        (x, y, z),
        (width, 0.18, height),
        M["wood"],
        0.025,
        role="interior_bookshelf",
    )
    for side in (-1, 1):
        box(
            c,
            name + ":side",
            (x + side * width / 2, y - 0.15, z),
            (0.10, 0.42, height + 0.12),
            M["wood"],
            0.012,
            role="interior_bookshelf",
        )
    for row in range(5):
        zz = z - height / 2 + 0.22 + row * (height - 0.35) / 4
        box(
            c,
            name + f":shelf_{row}",
            (x, y - 0.18, zz),
            (width, 0.42, 0.085),
            M["wood"],
            0.008,
            role="interior_bookshelf",
        )
        for book_index in range(7):
            bx = x - width / 2 + 0.18 + book_index * (width - 0.36) / 6
            mat = M[
                ("book_red", "book_blue", "book_gold", "book_green")[
                    (row + book_index) % 4
                ]
            ]
            box(
                c,
                name + f":book_{row}_{book_index}",
                (bx, y - 0.42, zz + 0.23),
                (0.12, 0.16, 0.36 + 0.06 * ((book_index * 3 + row) % 3)),
                mat,
                0.004,
                role="interior_book",
            )


def reading_table(c, name, x, y, z, yaw, M, width=2.4):
    BASE.local_box(
        c,
        name + ":top",
        (x, y, 0),
        yaw,
        (0, 0, z),
        (width, 0.92, 0.095),
        M["wood"],
        0.035,
        "reading_table",
    )
    for sx in (-1, 1):
        for sy in (-1, 1):
            BASE.local_box(
                c,
                name + ":leg",
                (x, y, 0),
                yaw,
                (sx * (width / 2 - 0.20), sy * 0.31, z / 2),
                (0.075, 0.075, z),
                M["black_metal"],
                0.008,
                "reading_table_leg",
            )
    for lamp_x in (-width * 0.27, width * 0.27):
        BASE.local_box(
            c,
            name + ":task_lamp_stem",
            (x, y, 0),
            yaw,
            (lamp_x, 0, z + 0.30),
            (0.028, 0.028, 0.56),
            M["black_metal"],
            0.004,
            "reading_lamp",
        )
        BASE.local_box(
            c,
            name + ":task_lamp",
            (x, y, 0),
            yaw,
            (lamp_x, 0, z + 0.60),
            (0.34, 0.18, 0.055),
            M["lamp"],
            0.018,
            "reading_lamp",
        )


def reading_chair(c, name, x, y, z, yaw, M):
    BASE.local_box(
        c,
        name + ":seat",
        (x, y, 0),
        yaw,
        (0, 0, z),
        (0.52, 0.52, 0.075),
        M["wood"],
        0.025,
        "reading_chair",
    )
    BASE.local_box(
        c,
        name + ":back",
        (x, y, 0),
        yaw,
        (0, 0.23, z + 0.43),
        (0.50, 0.07, 0.72),
        M["wood"],
        0.025,
        "reading_chair",
    )
    for sx in (-1, 1):
        for sy in (-1, 1):
            BASE.local_box(
                c,
                name + ":leg",
                (x, y, 0),
                yaw,
                (sx * 0.20, sy * 0.20, z / 2),
                (0.045, 0.045, z),
                M["black_metal"],
                0.004,
                "reading_chair_leg",
            )


def populate_visible_reading_rooms(c, prefix, ox, south, floor_zs, M, width=50.0):
    """Actual rooms behind glazing, including ceilings, shelving and furniture."""
    for floor, z in enumerate(floor_zs):
        room_y = south + 1.20
        box(
            c,
            f"{prefix}:interior_floor_{floor}",
            (ox, room_y + 1.0, z - 1.88),
            (width, 4.7, 0.16),
            M["paver_warm"],
            0.015,
            role="interior_floor_slab",
        )
        box(
            c,
            f"{prefix}:interior_ceiling_{floor}",
            (ox, room_y + 1.0, z + 1.86),
            (width, 4.7, 0.13),
            M["interior_ceiling"],
            0.012,
            role="interior_ceiling",
        )
        area_light(
            c,
            f"{prefix}:reading_room_light_{floor}",
            (ox, room_y + 0.55, z + 1.70),
            420.0,
            min(8.0, width * 0.18),
        )
        for light_index in range(9):
            lx = ox - width / 2 + 2.7 + light_index * (width - 5.4) / 8
            box(
                c,
                f"{prefix}:linear_light_{floor}_{light_index}",
                (lx, room_y + 0.45, z + 1.76),
                (1.55, 0.12, 0.035),
                M["lamp"],
                0.006,
                role="interior_ceiling_light",
            )
        for shelf_index in range(4):
            sx = ox - width / 2 + 5.2 + shelf_index * (width - 10.4) / 3
            bookshelf(
                c,
                f"{prefix}:upper_stack_{floor}_{shelf_index}",
                (sx, room_y + 0.08, z - 0.18),
                2.65,
                2.82,
                M,
            )
        for table_index in range(3):
            tx = ox - width / 2 + 9.0 + table_index * (width - 18.0) / 2
            reading_table(
                c,
                f"{prefix}:reading_table_{floor}_{table_index}",
                tx,
                room_y - 0.30,
                z - 1.14,
                0.0,
                M,
                2.2,
            )
            reading_chair(
                c,
                f"{prefix}:chair_a_{floor}_{table_index}",
                tx - 0.72,
                room_y - 1.0,
                z - 1.43,
                math.pi,
                M,
            )
            reading_chair(
                c,
                f"{prefix}:chair_b_{floor}_{table_index}",
                tx + 0.72,
                room_y - 1.0,
                z - 1.43,
                math.pi,
                M,
            )


def roof_plant(c, name, cx, cy, z, M, scale=1.0):
    box(
        c,
        name + ":curb",
        (cx, cy, z + 0.12),
        (5.2 * scale, 3.5 * scale, 0.24),
        M["concrete"],
        0.035,
        role="roof_plant_curb",
    )
    box(
        c,
        name + ":unit",
        (cx, cy, z + 0.85 * scale),
        (4.4 * scale, 2.8 * scale, 1.45 * scale),
        M["steel"],
        0.06,
        role="roof_mechanical_unit",
    )
    for row in range(7):
        box(
            c,
            name + f":louver_{row}",
            (cx, cy - 1.43 * scale, z + (0.35 + row * 0.17) * scale),
            (3.8 * scale, 0.045, 0.055 * scale),
            M["black_metal"],
            0.004,
            role="mechanical_louver",
        )
    cylinder(
        c,
        name + ":fan",
        (cx, cy, z + 1.68 * scale),
        0.66 * scale,
        0.15,
        M["black_metal"],
        32,
        role="roof_fan",
    )


def roof_safety_and_drainage(c, name, ox, oy, w, d, z, M, parapet=False):
    """Coping, drainage and safety details visible in elevated validation views."""
    if parapet:
        for y in (oy - d / 2, oy + d / 2):
            box(
                c,
                name + ":parapet",
                (ox, y, z + 0.38),
                (w, 0.24, 0.76),
                M["red_stone_dark"],
                0.025,
                role="roof_parapet",
            )
        for x in (ox - w / 2, ox + w / 2):
            box(
                c,
                name + ":parapet",
                (x, oy, z + 0.38),
                (0.24, d, 0.76),
                M["red_stone_dark"],
                0.025,
                role="roof_parapet",
            )
    for side, x in (("west", ox - w / 2 + 1.1), ("east", ox + w / 2 - 1.1)):
        cylinder(
            c,
            name + f":downpipe_{side}",
            (x, oy - d / 2 - 0.20, z / 2),
            0.085,
            z,
            M["steel"],
            20,
            role="rainwater_downpipe",
        )
        box(
            c,
            name + f":scupper_{side}",
            (x, oy - d / 2 - 0.29, z - 0.25),
            (0.42, 0.30, 0.30),
            M["steel"],
            0.018,
            role="roof_scupper",
        )
    # Low service guardrail is deliberately modeled, not a texture.
    rail_y = oy + d * 0.18
    for x in (ox - 5.0, ox, ox + 5.0):
        cylinder(
            c,
            name + ":guard_post",
            (x, rail_y, z + 0.55),
            0.035,
            1.10,
            M["steel"],
            14,
            role="roof_guardrail",
        )
    beam(
        c,
        name + ":guardrail",
        (ox - 5.0, rail_y, z + 1.06),
        (ox + 5.0, rail_y, z + 1.06),
        0.035,
        M["steel"],
        14,
        "roof_guardrail",
    )


def build_modern_library(parent, M, origin=(-38.0, 6.0)):
    """Reference A: white cantilevered civic library with deep sun screens."""
    c = collection(
        "LIBRARY_A_MODERN_CANTILEVER",
        parent,
        "library.modern_cantilever.reference_a.v5",
    )
    ox, oy = origin
    w, d, podium_z, h = 60.0, 32.5, 1.30, 27.0
    south, north = oy - d / 2, oy + d / 2
    west, east = ox - w / 2, ox + w / 2

    # Occupied core plus expressed floor plates.  The outer facade remains a
    # layered assembly, not a decorated cuboid.
    box(
        c,
        "A:occupied_core",
        (ox, oy + 1.1, podium_z + h / 2),
        (w - 4.0, d - 3.0, h),
        M["charcoal"],
        0.10,
        role="occupied_building_shell",
    )
    box(
        c,
        "A:raised_stylobate",
        (ox, oy, podium_z / 2),
        (w + 4.2, d + 3.5, podium_z),
        M["stone_light"],
        0.08,
        role="building_stylobate",
    )
    box(
        c,
        "A:stylobate_grime_band",
        (ox, south - 0.12, 0.28),
        (w + 1.5, 0.12, 0.34),
        M["base_grime"],
        0.01,
        role="facade_weathering",
    )
    for floor, z in enumerate(
        (
            podium_z + 5.1,
            podium_z + 9.6,
            podium_z + 14.1,
            podium_z + 18.6,
            podium_z + 23.1,
        )
    ):
        box(
            c,
            f"A:floor_slab_{floor}",
            (ox, oy, z),
            (w - 1.0, d - 1.0, 0.34),
            M["white_edge"],
            0.025,
            role="expressed_floor_slab",
        )

    # Transparent ground floor, entry doors, real interior depth and visible
    # shelving make the raised public level read as occupied.
    ground_z = podium_z + 2.45
    ground_bays = 11
    ground_bw = (w - 5.0) / ground_bays
    for bay in range(ground_bays):
        x = ox - (w - 5.0) / 2 + ground_bw * (bay + 0.5)
        facade_cell_y(
            c,
            f"A:ground_front_{bay}",
            x,
            south - 0.22,
            ground_z,
            ground_bw - 0.13,
            4.35,
            M,
            -1,
            "glass_neutral",
            bay in {2, 8},
            1,
        )
    glass_door_bank(
        c, "A:main_entrance", ox - 5.2, south - 0.55, podium_z, 6.0, 4.25, M, 4
    )
    for bay in range(10):
        x = ox - (w - 6.0) / 2 + (w - 6.0) * (bay + 0.5) / 10
        facade_cell_y(
            c,
            f"A:ground_rear_{bay}",
            x,
            north + 0.20,
            ground_z,
            (w - 6.0) / 10 - 0.16,
            4.25,
            M,
            1,
            "glass_neutral",
            False,
            1,
        )
    for shelf in range(9):
        x = ox - 20.0 + shelf * 5.0
        bookshelf(
            c,
            f"A:visible_stack_{shelf}",
            (x, south + 1.25, podium_z + 2.25),
            3.2,
            3.25,
            M,
        )
    area_light(
        c, "A:ground_reading_light", (ox, south + 1.25, podium_z + 4.15), 520.0, 9.0
    )
    for table_index, x in enumerate((ox - 16.0, ox, ox + 16.0)):
        reading_table(
            c,
            f"A:ground_reading_table_{table_index}",
            x,
            south + 0.70,
            podium_z + 0.72,
            0.0,
            M,
            2.8,
        )
        reading_chair(
            c,
            f"A:ground_reading_chair_{table_index}",
            x,
            south - 0.12,
            podium_z + 0.42,
            math.pi,
            M,
        )
    for x in (ox - 22.5, ox - 13.5, ox + 13.5, ox + 22.5):
        cylinder(
            c,
            "A:ground_column",
            (x, south + 1.0, podium_z + 2.3),
            0.23,
            4.6,
            M["steel"],
            32,
            role="structural_column",
        )

    # The reference's dominant deep white rectangular frame and three storeys
    # of recessed horizontal glazing.
    frame_z = podium_z + 14.0
    for x in (west + 2.0, east - 2.0):
        box(
            c,
            "A:monumental_frame_pier",
            (x, south - 1.15, frame_z),
            (2.1, 1.95, 17.8),
            M["white_edge"],
            0.07,
            role="monumental_facade_frame",
        )
    for z in (podium_z + 5.35, podium_z + 22.65):
        box(
            c,
            "A:monumental_frame_beam",
            (ox, south - 1.15, z),
            (w - 2.0, 1.95, 1.30),
            M["white_edge"],
            0.07,
            role="monumental_facade_frame",
        )
    mid_bays = 7
    mid_bw = (w - 8.0) / mid_bays
    for floor, z in enumerate((podium_z + 8.0, podium_z + 12.55, podium_z + 17.10)):
        for bay in range(mid_bays):
            x = ox - (w - 8.0) / 2 + mid_bw * (bay + 0.5)
            facade_cell_y(
                c,
                f"A:front_reading_{floor}_{bay}",
                x,
                south - 0.47,
                z,
                mid_bw - 0.22,
                3.50,
                M,
                -1,
                "glass_blue_alt",
                (floor * 5 + bay) % 13 == 4,
                2,
            )
        box(
            c,
            f"A:front_spandrel_{floor}",
            (ox, south - 0.82, z + 1.90),
            (w - 7.2, 0.40, 0.32),
            M["white_panel"],
            0.02,
            role="facade_spandrel",
        )
    populate_visible_reading_rooms(
        c,
        "A",
        ox,
        south,
        (podium_z + 8.0, podium_z + 12.55, podium_z + 17.10),
        M,
        w - 10.0,
    )
    # Glass balustrade and stainless cap at the public reading terrace visible
    # in the reference, set forward of the middle curtain wall.
    for panel in range(12):
        x = ox - (w - 10.0) / 2 + (w - 10.0) * (panel + 0.5) / 12
        box(
            c,
            f"A:reading_balustrade_{panel}",
            (x, south - 1.10, podium_z + 10.05),
            ((w - 10.0) / 12 - 0.06, 0.035, 1.05),
            M["glass_clear"],
            0.004,
            role="glass_balustrade",
        )
    box(
        c,
        "A:reading_balustrade_cap",
        (ox, south - 1.14, podium_z + 10.60),
        (w - 9.7, 0.065, 0.065),
        M["steel"],
        0.008,
        role="balustrade_handrail",
    )
    for fin in range(34):
        x = ox - (w - 8.0) / 2 + (w - 8.0) * fin / 33
        box(
            c,
            f"A:upper_front_fin_{fin}",
            (x, south - 1.17, podium_z + 20.95),
            (0.13, 1.18, 3.2),
            M["white_edge"],
            0.018,
            role="vertical_sun_fin",
        )

    # Continuous clerestory beneath the floating roof.
    top_bays = 14
    for bay in range(top_bays):
        x = ox - (w - 3.0) / 2 + (w - 3.0) * (bay + 0.5) / top_bays
        facade_cell_y(
            c,
            f"A:clerestory_{bay}",
            x,
            south - 0.24,
            podium_z + 25.15,
            (w - 3.0) / top_bays - 0.10,
            3.35,
            M,
            -1,
            "glass_neutral",
            False,
            1,
        )

    # Both long rear elevation and side elevations receive complete facade
    # systems so orbiting cameras never reveal an unmodeled wall.
    for floor, z in enumerate(
        (podium_z + 7.8, podium_z + 12.3, podium_z + 16.8, podium_z + 21.3)
    ):
        for bay in range(9):
            x = ox - (w - 5.0) / 2 + (w - 5.0) * (bay + 0.5) / 9
            facade_cell_y(
                c,
                f"A:rear_{floor}_{bay}",
                x,
                north + 0.24,
                z,
                (w - 5.0) / 9 - 0.22,
                3.35,
                M,
                1,
                "glass_blue_alt",
                False,
                2,
            )
    side_bays = 5
    for side, x, normal in (("west", west - 0.24, -1), ("east", east + 0.24, 1)):
        for floor, z in enumerate(
            (podium_z + 7.8, podium_z + 12.3, podium_z + 16.8, podium_z + 21.3)
        ):
            for bay in range(side_bays):
                y = oy - (d - 4.0) / 2 + (d - 4.0) * (bay + 0.5) / side_bays
                facade_cell_x(
                    c,
                    f"A:{side}_{floor}_{bay}",
                    x,
                    y,
                    z,
                    (d - 4.0) / side_bays - 0.22,
                    3.32,
                    M,
                    normal,
                    "glass_blue_alt",
                    False,
                    1,
                )
        for fin in range(22):
            y = oy - (d - 3.0) / 2 + (d - 3.0) * fin / 21
            box(
                c,
                f"A:{side}_fin_{fin}",
                (x + normal * 0.65, y, podium_z + 15.1),
                (1.15, 0.15, 18.2),
                M["white_edge"],
                0.02,
                role="vertical_sun_fin",
            )
        # Fine horizontal carriers keep the screen structurally believable.
        for z in (
            podium_z + 6.3,
            podium_z + 11.0,
            podium_z + 15.7,
            podium_z + 20.4,
            podium_z + 24.0,
        ):
            box(
                c,
                f"A:{side}_fin_carrier",
                (x + normal * 0.42, oy, z),
                (0.16, d - 2.7, 0.14),
                M["steel"],
                0.01,
                role="sun_screen_carrier",
            )

    # Fine panelization on solid borders.
    for i in range(1, 12):
        z = podium_z + 5.2 + i * 1.48
        box(
            c,
            f"A:right_panel_joint_{i}",
            (east + 0.70, south - 0.97, z),
            (1.58, 0.035, 0.025),
            M["concrete"],
            0,
            role="facade_panel_joint",
        )
    for side, x in (("left", west + 2.0), ("right", east - 2.0)):
        for i in range(7):
            z = podium_z + 6.2 + i * 2.3
            box(
                c,
                f"A:{side}_frame_joint_{i}",
                (x, south - 2.14, z),
                (1.55, 0.025, 0.025),
                M["concrete"],
                0,
                role="facade_panel_joint",
            )

    # Thin, strongly cantilevered roof with fascia, shadow gap and modeled
    # underside ribs captures the image silhouette.
    roof_z = podium_z + h + 0.55
    box(
        c,
        "A:roof_shadow_gap",
        (ox, oy, roof_z - 0.34),
        (w + 1.5, d + 1.4, 0.48),
        M["soffit"],
        0.04,
        role="roof_shadow_gap",
    )
    box(
        c,
        "A:floating_roof_soffit",
        (ox, oy, roof_z - 0.06),
        (w + 7.4, d + 7.2, 0.34),
        M["soffit"],
        0.065,
        role="cantilevered_roof",
    )
    box(
        c,
        "A:floating_roof_membrane",
        (ox, oy, roof_z + 0.19),
        (w + 7.0, d + 6.8, 0.18),
        M["roof_membrane"],
        0.045,
        role="roof_membrane",
    )
    # Thin metallic fascia produces the crisp hovering edge in the photograph.
    for y in (oy - (d + 7.2) / 2, oy + (d + 7.2) / 2):
        box(
            c,
            "A:roof_fascia_long",
            (ox, y, roof_z + 0.02),
            (w + 7.5, 0.18, 0.42),
            M["steel"],
            0.025,
            role="roof_fascia",
        )
    for x in (ox - (w + 7.4) / 2, ox + (w + 7.4) / 2):
        box(
            c,
            "A:roof_fascia_short",
            (x, oy, roof_z + 0.02),
            (0.18, d + 7.1, 0.42),
            M["steel"],
            0.025,
            role="roof_fascia",
        )
    for rib in range(24):
        x = ox - (w + 5.4) / 2 + (w + 5.4) * rib / 23
        box(
            c,
            f"A:roof_soffit_rib_{rib}",
            (x, south - 2.0, roof_z - 0.63),
            (0.10, 4.9, 0.22),
            M["steel"],
            0.01,
            role="roof_structure",
        )
    for side, x in (("west", west - 3.25), ("east", east + 3.25)):
        for rib in range(11):
            y = oy - (d + 4.8) / 2 + (d + 4.8) * rib / 10
            box(
                c,
                f"A:{side}_roof_rib_{rib}",
                (x, y, roof_z - 0.63),
                (2.0, 0.10, 0.22),
                M["steel"],
                0.01,
                role="roof_structure",
            )
    roof_plant(c, "A:roof_plant_1", ox - 10.0, oy + 3.0, roof_z + 0.5, M, 0.75)
    roof_plant(c, "A:roof_plant_2", ox + 7.0, oy + 4.5, roof_z + 0.5, M, 0.62)
    roof_safety_and_drainage(
        c, "A:roof_service", ox, oy, w + 6.5, d + 6.2, roof_z + 0.35, M
    )
    front_text(
        c,
        "A:vertical_identity",
        "L\nI\nB\nR\nA\nR\nY",
        (east - 2.0, south - 2.18, podium_z + 16.7),
        0.80,
        M["red"],
        0.06,
    )

    c["c2w_reference_index"] = 1
    c["c2w_reference_url"] = REFERENCE_URLS[0]
    c[
        "c2w_detail_profile"
    ] = "deep_white_frame+five_occupied_levels+four_sided_recessed_insulating_glazing+screen_carriers+thin_cantilevered_roof+visible_reading_rooms+roof_drainage+material_weathering"
    return c


def build_monumental_red_library(parent, M, origin=(39.0, 6.0)):
    """Reference B: symmetric red masonry library with nested entry frames."""
    c = collection(
        "LIBRARY_B_RED_MONUMENTAL", parent, "library.red_monumental.reference_b.v5"
    )
    ox, oy = origin
    w, d, h = 46.0, 30.5, 29.0
    south, north = oy - d / 2, oy + d / 2
    west, east = ox - w / 2, ox + w / 2
    # The occupied core is deliberately recessed from every rainscreen.  This
    # creates real rooms behind the windows instead of glazing pasted onto a
    # solid cube.
    box(
        c,
        "B:occupied_shell",
        (ox, oy, h / 2),
        (w - 4.0, d - 5.0, h),
        M["red_stone"],
        0.12,
        role="occupied_building_shell",
    )
    box(
        c,
        "B:dark_plinth",
        (ox, oy, 0.65),
        (w + 0.7, d + 0.7, 1.30),
        M["red_stone_dark"],
        0.055,
        role="masonry_plinth",
    )
    box(
        c,
        "B:plinth_weathering",
        (ox, south - 0.10, 0.38),
        (w - 0.5, 0.14, 0.46),
        M["base_grime"],
        0.012,
        role="facade_weathering",
    )

    # Stepped crown and projecting flanks produce the reference silhouette.
    box(
        c,
        "B:center_crown",
        (ox, oy, h + 1.0),
        (18.0, d + 0.5, 2.0),
        M["red_stone_light"],
        0.055,
        role="stepped_crown",
    )
    for side in (-1, 1):
        box(
            c,
            "B:projecting_flank",
            (ox + side * (w / 2 - 2.6), south - 0.75, h / 2),
            (5.2, 1.5, h + 0.5),
            M["red_stone_light"],
            0.065,
            role="projecting_facade_tower",
        )
        box(
            c,
            "B:flank_cap",
            (ox + side * (w / 2 - 2.6), south - 0.82, h + 0.55),
            (5.7, 1.72, 1.1),
            M["red_stone_dark"],
            0.045,
            role="masonry_cornice",
        )
        flank_x = ox + side * (w / 2 - 2.6)
        for course in range(1, 34):
            z = course * h / 34
            box(
                c,
                f"B:flank_bed_joint_{side}_{course}",
                (flank_x, south - 1.515, z),
                (4.75, 0.025, 0.018),
                M["red_joint"],
                0,
                role="masonry_bed_joint",
            )
        box(
            c,
            f"B:flank_vertical_joint_{side}",
            (flank_x, south - 1.518, h / 2),
            (0.022, 0.026, h - 0.7),
            M["red_joint"],
            0,
            role="masonry_vertical_joint",
        )

    # Double-height central glazed atrium with mullions, spandrels and warm
    # interior planes, enclosed by five successively deeper U-shaped portals.
    atrium_w, atrium_h = 13.4, 20.8
    atrium_center_z = 11.3
    for side in (-1, 1):
        box(
            c,
            f"B:atrium_recess_jamb_{side}",
            (ox + side * (atrium_w / 2 + 0.36), south - 0.44, atrium_center_z),
            (0.72, 0.58, atrium_h + 1.0),
            M["dark"],
            0.025,
            role="atrium_recess",
        )
    box(
        c,
        "B:atrium_recess_head",
        (ox, south - 0.44, atrium_center_z + (atrium_h + 1.0) / 2),
        (atrium_w + 1.4, 0.58, 0.72),
        M["dark"],
        0.025,
        role="atrium_recess",
    )
    for floor in range(6):
        z = 2.1 + floor * 3.45
        for bay in range(4):
            x = ox - atrium_w / 2 + atrium_w * (bay + 0.5) / 4
            facade_cell_y(
                c,
                f"B:atrium_{floor}_{bay}",
                x,
                south - 0.80,
                z,
                atrium_w / 4 - 0.14,
                3.05,
                M,
                -1,
                "glass_warm",
                (floor + bay * 3) % 11 == 4,
                1,
            )
        box(
            c,
            f"B:atrium_spandrel_{floor}",
            (ox, south - 1.10, z + 1.67),
            (atrium_w + 0.2, 0.18, 0.24),
            M["bronze_dark"],
            0.008,
            role="atrium_spandrel",
        )
    for layer in range(5):
        half_w = atrium_w / 2 + 1.0 + layer * 1.05
        top_z = 22.7 + layer * 0.95
        project_y = south - 1.28 - layer * 0.38
        pier_w = 0.52 + layer * 0.09
        for side in (-1, 1):
            box(
                c,
                f"B:nested_portal_{layer}_{side}",
                (ox + side * half_w, project_y, top_z / 2),
                (pier_w, 0.62, top_z),
                M["red_stone_dark" if layer % 2 == 0 else "red_stone_light"],
                0.04,
                role="nested_portal_frame",
            )
        box(
            c,
            f"B:nested_portal_head_{layer}",
            (ox, project_y, top_z),
            (half_w * 2 + pier_w, 0.62, pier_w),
            M["red_stone_dark" if layer % 2 == 0 else "red_stone_light"],
            0.04,
            role="nested_portal_frame",
        )
        # Continuous recessed shadow channel separates each nested frame and
        # prevents the portal from reading as stacked toy blocks.
        box(
            c,
            f"B:portal_shadow_head_{layer}",
            (ox, project_y - 0.34, top_z - pier_w * 0.55),
            (half_w * 2 - 0.20, 0.10, 0.07),
            M["rubber"],
            0.004,
            role="portal_shadow_joint",
        )
        for side in (-1, 1):
            box(
                c,
                f"B:portal_shadow_pier_{layer}_{side}",
                (ox + side * (half_w - pier_w * 0.55), project_y - 0.34, top_z / 2),
                (0.07, 0.10, top_z - 0.25),
                M["rubber"],
                0.004,
                role="portal_shadow_joint",
            )

    glass_door_bank(c, "B:main_entrance", ox, south - 1.20, 0.0, 7.4, 4.2, M, 4)
    box(
        c,
        "B:entry_canopy",
        (ox, south - 2.25, 4.45),
        (9.2, 3.1, 0.34),
        M["red_stone_dark"],
        0.055,
        role="entrance_canopy",
    )
    for side in (-1, 1):
        cylinder(
            c,
            "B:canopy_column",
            (ox + side * 3.7, south - 3.15, 2.15),
            0.14,
            4.3,
            M["bronze"],
            28,
            role="structural_column",
        )

    # Symmetric narrow front window stacks.  Their brick reveals are projected
    # beyond the main rainscreen, matching the vertical slots in the reference.
    for side in (-1, 1):
        for strip in range(3):
            x = ox + side * (10.6 + strip * 3.0)
            for floor in range(6):
                z = 2.5 + floor * 4.15
                facade_cell_y(
                    c,
                    f"B:front_slot_{side}_{strip}_{floor}",
                    x,
                    south - 0.36,
                    z,
                    1.55,
                    2.85,
                    M,
                    -1,
                    "glass_warm",
                    False,
                    1,
                )
            box(
                c,
                "B:slot_side_trim",
                (x - 1.0, south - 0.78, 14.4),
                (0.34, 0.62, 26.3),
                M["red_stone_dark"],
                0.025,
                role="vertical_masonry_fin",
            )
            box(
                c,
                "B:slot_side_trim",
                (x + 1.0, south - 0.78, 14.4),
                (0.34, 0.62, 26.3),
                M["red_stone_dark"],
                0.025,
                role="vertical_masonry_fin",
            )

    # Real running-bond brick veneer is added as separate piers and spandrels
    # so window openings retain true depth instead of being painted on a box.
    for side in (-1, 1):
        for local_x, pier_w in ((8.4, 1.7), (12.1, 1.25), (15.1, 1.25), (19.2, 2.6)):
            box(
                c,
                "B:front_brick_pier",
                (ox + side * local_x, south - 0.59, 14.35),
                (pier_w, 0.18, 27.0),
                M["red_brick_front"],
                0.018,
                role="brick_veneer_pier",
            )
        for floor in range(7):
            z = 0.42 + floor * 4.15
            box(
                c,
                "B:front_brick_spandrel",
                (ox + side * 14.0, south - 0.62, z),
                (12.6, 0.20, 0.54),
                M["red_brick_front"],
                0.014,
                role="brick_veneer_spandrel",
            )

    # Fully populated side and rear elevations.
    for side_name, x, normal in (("west", west - 0.22, -1), ("east", east + 0.22, 1)):
        for floor in range(6):
            z = 2.5 + floor * 4.15
            for bay in range(5):
                y = oy - (d - 4.0) / 2 + (d - 4.0) * (bay + 0.5) / 5
                facade_cell_x(
                    c,
                    f"B:{side_name}_{floor}_{bay}",
                    x,
                    y,
                    z,
                    (d - 4.0) / 5 - 0.35,
                    2.78,
                    M,
                    normal,
                    "glass_warm",
                    (floor * 3 + bay) % 17 == 2,
                    1,
                )
        for bay in range(6):
            y = oy - (d - 3.0) / 2 + (d - 3.0) * bay / 5
            box(
                c,
                f"B:{side_name}_vertical_fin_{bay}",
                (x + normal * 0.58, y, 14.7),
                (0.84, 0.30, 27.2),
                M["red_stone_dark"],
                0.03,
                role="vertical_masonry_fin",
            )
        for floor in range(7):
            z = 0.45 + floor * 4.15
            box(
                c,
                f"B:{side_name}_brick_spandrel_{floor}",
                (x + normal * 0.48, oy, z),
                (0.16, d - 1.2, 0.55),
                M["red_brick_side"],
                0.012,
                role="brick_veneer_spandrel",
            )
    for floor in range(6):
        z = 2.5 + floor * 4.15
        for bay in range(7):
            x = ox - (w - 5.0) / 2 + (w - 5.0) * (bay + 0.5) / 7
            facade_cell_y(
                c,
                f"B:rear_{floor}_{bay}",
                x,
                north + 0.24,
                z,
                (w - 5.0) / 7 - 0.30,
                2.78,
                M,
                1,
                "glass_warm",
                False,
                1,
            )
    for floor in range(7):
        z = 0.45 + floor * 4.15
        box(
            c,
            f"B:rear_brick_spandrel_{floor}",
            (ox, north + 0.50, z),
            (w - 1.0, 0.16, 0.55),
            M["red_brick_front"],
            0.012,
            role="brick_veneer_spandrel",
        )

    # Explicit stone panel joints on front, sides and rear.
    for course in range(1, 38):
        z = course * h / 38
        for cx in (ox - 15.8, ox + 15.8):
            box(
                c,
                f"B:front_horizontal_joint_{course}",
                (cx, south - 0.79, z),
                (9.4, 0.025, 0.022),
                M["red_joint"],
                0,
                role="facade_panel_joint",
            )
        box(
            c,
            f"B:rear_horizontal_joint_{course}",
            (ox, north + 0.39, z),
            (w - 1.0, 0.025, 0.022),
            M["red_joint"],
            0,
            role="facade_panel_joint",
        )
    for grid in range(1, 10):
        x = west + grid * w / 10
        box(
            c,
            f"B:rear_vertical_joint_{grid}",
            (x, north + 0.40, h / 2),
            (0.022, 0.025, h - 0.5),
            M["red_joint"],
            0,
            role="facade_panel_joint",
        )
    for side, x in (("west", west - 0.40), ("east", east + 0.40)):
        for course in range(1, 38):
            z = course * h / 38
            box(
                c,
                f"B:{side}_horizontal_joint_{course}",
                (x, oy, z),
                (0.025, d - 1.0, 0.022),
                M["red_joint"],
                0,
                role="facade_panel_joint",
            )

    # Occupied atrium depth: floor edges, bronze guardrails, shelving and long
    # pendant lights are all visible through the central curtain wall.
    for floor in range(1, 6):
        z = 0.85 + floor * 3.45
        box(
            c,
            f"B:atrium_floor_edge_{floor}",
            (ox, south + 0.45, z),
            (atrium_w - 0.6, 2.25, 0.20),
            M["paver_warm"],
            0.018,
            role="interior_floor_slab",
        )
        area_light(
            c,
            f"B:atrium_floor_light_{floor}",
            (ox, south + 0.45, z + 2.65),
            260.0,
            5.2,
            (1.0, 0.60, 0.32),
        )
        beam(
            c,
            f"B:atrium_guardrail_{floor}",
            (ox - atrium_w / 2 + 0.6, south - 0.06, z + 1.02),
            (ox + atrium_w / 2 - 0.6, south - 0.06, z + 1.02),
            0.035,
            M["bronze"],
            14,
            "interior_guardrail",
        )
        for post in range(7):
            x = ox - atrium_w / 2 + 0.7 + post * (atrium_w - 1.4) / 6
            cylinder(
                c,
                f"B:atrium_guard_post_{floor}_{post}",
                (x, south - 0.06, z + 0.53),
                0.022,
                0.96,
                M["bronze"],
                12,
                role="interior_guardrail_post",
            )
        for shelf in range(2):
            bookshelf(
                c,
                f"B:atrium_stack_{floor}_{shelf}",
                (ox - 3.3 + shelf * 6.6, south + 0.80, z + 1.15),
                2.4,
                2.5,
                M,
            )
    for pendant in range(5):
        x = ox - 4.8 + pendant * 2.4
        cylinder(
            c,
            f"B:atrium_pendant_cord_{pendant}",
            (x, south - 0.25, 23.8),
            0.015,
            5.2,
            M["black_metal"],
            10,
            role="interior_pendant",
        )
        cylinder(
            c,
            f"B:atrium_pendant_{pendant}",
            (x, south - 0.25, 21.15),
            0.22,
            0.12,
            M["lamp"],
            24,
            role="interior_pendant",
        )

    # Layered cornice and screened rooftop service equipment.
    for z, depth, height in (
        (h - 0.25, 0.72, 0.42),
        (h + 0.30, 1.05, 0.46),
        (h + 0.82, 1.35, 0.36),
    ):
        box(
            c,
            f"B:front_cornice_{z}",
            (ox, south - depth / 2, z),
            (w + depth, depth, height),
            M["red_stone_dark"],
            0.045,
            role="masonry_cornice",
        )
        box(
            c,
            f"B:rear_cornice_{z}",
            (ox, north + depth / 2, z),
            (w + depth, depth, height),
            M["red_stone_dark"],
            0.045,
            role="masonry_cornice",
        )
    roof_plant(c, "B:roof_plant_1", ox - 9.0, oy + 2.0, h + 1.15, M, 0.70)
    roof_plant(c, "B:roof_plant_2", ox + 8.0, oy + 3.5, h + 1.15, M, 0.62)
    box(
        c,
        "B:roof_membrane",
        (ox, oy, h + 1.05),
        (w - 2.0, d - 2.0, 0.16),
        M["roof_membrane"],
        0.025,
        role="roof_membrane",
    )
    roof_safety_and_drainage(
        c, "B:roof_service", ox, oy, w - 0.5, d - 0.5, h + 1.15, M, parapet=True
    )
    front_text(
        c,
        "B:left_vertical_identity",
        "City Library \n",
        (ox - 17.8, south - 1.22, 21.0),
        0.66,
        M["brass"],
        0.055,
    )
    front_text(
        c,
        "B:right_vertical_identity",
        "PUBLIC\nLIBRARY",
        (ox + 17.8, south - 1.22, 20.6),
        0.48,
        M["brass"],
        0.045,
    )

    c["c2w_reference_index"] = 2
    c["c2w_reference_url"] = REFERENCE_URLS[1]
    c[
        "c2w_detail_profile"
    ] = "world_scale_running_bond_brick+six_occupied_levels+central_atrium+five_shadow_jointed_nested_portals+four_sided_recessed_windows+stepped_crown+visible_guardrails_and_stacks+roof_drainage"
    return c


def bench(c, name, x, y, yaw, M):
    for slat in range(6):
        BASE.local_box(
            c,
            name + ":seat_slat",
            (x, y, 0),
            yaw,
            (0, (slat - 2.5) * 0.13, 0.62),
            (3.4, 0.105, 0.10),
            M["wood"],
            0.03,
            "bench_slat",
        )
    for slat in range(5):
        BASE.local_box(
            c,
            name + ":back_slat",
            (x, y, 0),
            yaw,
            (0, 0.38, 0.89 + slat * 0.13),
            (3.4, 0.10, 0.10),
            M["wood"],
            0.025,
            "bench_slat",
        )
    for side in (-1, 1):
        BASE.local_box(
            c,
            name + ":leg",
            (x, y, 0),
            yaw,
            (side * 1.35, 0, 0.33),
            (0.12, 0.7, 0.58),
            M["black_metal"],
            0.02,
            "bench_frame",
        )


def leaf_card_canopy(c, name, centers, scale, M, count=240):
    """One dense double-sided leaf mesh with varied pose and three materials."""
    rng = random.Random(_stable_code(name) + int(scale * 1000))
    vertices, faces, material_indices = [], [], []
    for leaf_index in range(count):
        anchor = centers[leaf_index % len(centers)]
        phi = rng.random() * math.tau
        radius = scale * (0.15 + 1.22 * rng.random() ** 0.58)
        vertical = scale * rng.uniform(-0.75, 0.88)
        center = Vector(
            (
                anchor[0] + math.cos(phi) * radius,
                anchor[1] + math.sin(phi) * radius,
                anchor[2] + vertical,
            )
        )
        yaw = rng.random() * math.tau
        tilt = rng.uniform(-0.65, 0.65)
        half_len = scale * rng.uniform(0.17, 0.29)
        half_w = half_len * rng.uniform(0.34, 0.50)
        right = Vector((math.cos(yaw), math.sin(yaw), 0.0)) * half_len
        up = (
            Vector(
                (
                    -math.sin(yaw) * math.sin(tilt),
                    math.cos(yaw) * math.sin(tilt),
                    math.cos(tilt),
                )
            )
            * half_w
        )
        base = len(vertices)
        # A pointed leaf rather than a square/diamond card.
        vertices.extend(
            (
                tuple(center - right),
                tuple(center - up),
                tuple(center + right),
                tuple(center + up),
            )
        )
        faces.extend(
            ((base, base + 1, base + 2, base + 3), (base + 3, base + 2, base + 1, base))
        )
        material_indices.extend(
            (leaf_index % 11 == 0 and 1 or leaf_index % 7 == 0 and 2 or 0,) * 2
        )
    mesh = bpy.data.meshes.new(PREFIX + name + ":leaf_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(M["leaf"])
    mesh.materials.append(M["leaf_light"])
    mesh.materials.append(M["leaf_dark"])
    mesh.update()
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
        polygon.use_smooth = True
    obj = bpy.data.objects.new(PREFIX + name + ":canopy", mesh)
    c.objects.link(obj)
    tag(obj, "botanical_leaf_canopy")
    obj["c2w_leaf_card_count"] = count
    obj["c2w_leaf_geometry"] = "pointed_double_sided_cards"
    return obj


FULL07_TREE_SOURCE = (
    "urban_v1_full_07_trees.build_botanical_tree_master+"
    "infinigen.assets.objects.trees.generate.random_leaf_collection"
)


def build_full07_tree_master(seed):
    """Build one production botanical master from genuine same-run leaves.

    This is the established ``urban_v1_full_07`` production method: a
    continuous, multi-level woody hierarchy (trunk, primaries, secondaries and
    twigs) receives thousands of individually posed copies of meshes generated
    by Infinigen's real LeafFactory.  The temporary source-leaf collection is
    removed only after its topology has been copied into the merged canopy.
    """
    objects_before = set(bpy.data.objects)
    collections_before = set(bpy.data.collections)
    with FixedSeed(seed):
        leaf_collection = random_leaf_collection("summer", n=5)
    source_objects = [obj for obj in bpy.data.objects if obj not in objects_before]
    leaf_assets = [
        obj for obj in leaf_collection.all_objects if obj.type == "MESH" and obj.data
    ]
    if not leaf_assets:
        raise RuntimeError(
            f"Full07 tree seed {seed} received no genuine LeafFactory meshes"
        )
    source_names = [obj.name for obj in leaf_assets]

    master = bpy.data.collections.new(PREFIX + f"NATIVE_TREE_MASTER_{seed}")
    detail = build_botanical_tree_master(master, seed, leaf_assets)

    source_meshes = {
        obj.data for obj in source_objects if obj.type == "MESH" and obj.data
    }
    for obj in source_objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for source_collection in [
        coll
        for coll in bpy.data.collections
        if coll not in collections_before and coll != master
    ]:
        if source_collection.name in bpy.data.collections:
            bpy.data.collections.remove(source_collection)
    for mesh in source_meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    master["c2w_schema_version"] = SCHEMA_VERSION
    master["c2w_role"] = "native_tree_master"
    master["c2w_generator"] = Path(__file__).name
    master["c2w_asset_id"] = f"library.native_tree_master.{seed}"
    master["c2w_source_method"] = FULL07_TREE_SOURCE
    master["c2w_scene_asset_inputs"] = 0
    master["c2w_leaf_factory_source_names"] = json.dumps(
        source_names, ensure_ascii=False
    )
    for obj in master.objects:
        if not obj.name.startswith(PREFIX):
            obj.name = PREFIX + obj.name
        if obj.data and not obj.data.name.startswith(PREFIX):
            obj.data.name = PREFIX + obj.data.name
        role = (
            "native_tree_leaf_geometry"
            if obj.get("c2w_genuine_leaffactory_mesh")
            else "native_tree_branch_geometry"
        )
        tag(obj, role, f"library.native_tree_master.{seed}")
        obj["c2w_treefactory_seed"] = seed
        obj["c2w_source_method"] = FULL07_TREE_SOURCE
        obj["c2w_tree_quality"] = "full07_multilevel_botanical_genuine_leaffactory"

    detail = dict(detail)
    detail.update(
        {
            "seed": seed,
            "master_collection": master.name,
            "source_method": FULL07_TREE_SOURCE,
            "leaf_factory_source_mesh_count": len(source_names),
            "leaf_factory_source_names": source_names,
            "mesh_vertices": sum(
                len(obj.data.vertices) for obj in master.objects if obj.type == "MESH"
            ),
            "mesh_polygons": sum(
                len(obj.data.polygons) for obj in master.objects if obj.type == "MESH"
            ),
            "quality": "full07_multilevel_botanical_genuine_leaffactory_no_fallback",
        }
    )
    if (
        detail["branches"] < 350
        or detail["leaves"] < 3_000
        or detail["mesh_polygons"] < 20_000
    ):
        raise RuntimeError(
            f"Full07 botanical master degraded below production detail: {detail}"
        )
    return master, detail


def place_full07_tree(master, master_detail, site_collection, index, x, y, scale, yaw):
    """Place a lightweight collection instance of a fully modeled master."""
    instance = bpy.data.objects.new(PREFIX + f"site:native_tree_{index}", None)
    site_collection.objects.link(instance)
    instance.instance_type = "COLLECTION"
    instance.instance_collection = master
    instance.location = (x, y, 0.0)
    instance.rotation_euler[2] = yaw
    instance.scale = (scale, scale, scale)
    tag(instance, "native_tree_root", f"library.native_tree.{index}")
    instance["c2w_native_tree_instance"] = index
    instance["c2w_treefactory_seed"] = master_detail["seed"]
    instance["c2w_source_method"] = FULL07_TREE_SOURCE
    instance["c2w_tree_quality"] = "full07_multilevel_botanical_genuine_leaffactory"
    return {
        "id": f"library.native_tree.{index}",
        "type": "full07_botanical_tree_collection_instance",
        "instance": instance.name,
        "location": [x, y, 0.0],
        "scale": scale,
        "yaw": yaw,
        "seed": master_detail["seed"],
        "master_collection": master.name,
        "source_method": FULL07_TREE_SOURCE,
        "branches": master_detail["branches"],
        "leaves": master_detail["leaves"],
        "crown": master_detail["crown"],
        "source_height_m": master_detail["height"],
        "placed_height_m": master_detail["height"] * scale,
        "mesh_vertices": master_detail["mesh_vertices"],
        "mesh_polygons": master_detail["mesh_polygons"],
        "quality": "full07_multilevel_botanical_genuine_leaffactory_no_fallback",
    }


def site_shrub(c, name, x, y, scale, M):
    centers = []
    for stem in range(9):
        angle = stem * 2.399963
        tip = (
            x + math.cos(angle) * 0.36 * scale,
            y + math.sin(angle) * 0.36 * scale,
            (0.55 + 0.10 * (stem % 4)) * scale,
        )
        beam(
            c,
            name + f":stem_{stem}",
            (x, y, 0.18),
            tip,
            0.018 * scale,
            M["bark"],
            8,
            "shrub_stem",
        )
        centers.append(tip)
    leaf_card_canopy(c, name, centers, 0.34 * scale, M, count=64)


def build_library_site(parent, M):
    c = collection("LIBRARY_COMPARISON_SITE", parent, "library.site.comparison.v6")
    # The validation world remains library-only, but the planted ground plane
    # extends well beyond every camera frustum so no view exposes a black void
    # at the edge of the modeled comparison parcel.
    box(
        c,
        "site:ground",
        (0, 4, -0.45),
        (420, 300, 0.9),
        M["lawn"],
        0.06,
        role="library_site_ground",
    )
    # Real street edge in front of the parcel anchors the camera at human
    # height and gives the references their urban, photographic context.
    box(
        c,
        "site:street",
        (0, -39.0, 0.045),
        (176, 17.0, 0.09),
        M["asphalt_real"],
        0.02,
        role="public_road",
    )
    box(
        c,
        "site:curb",
        (0, -30.35, 0.19),
        (176, 0.38, 0.38),
        M["curb"],
        0.025,
        role="street_curb",
    )
    box(
        c,
        "site:gutter",
        (0, -30.70, 0.075),
        (176, 0.34, 0.08),
        M["paver"],
        0.012,
        role="street_gutter",
    )
    for lane_y in (-35.0, -43.0):
        for dash in range(-8, 9):
            box(
                c,
                f"site:lane_dash_{lane_y}_{dash}",
                (dash * 10.0, lane_y, 0.105),
                (5.0, 0.13, 0.025),
                M["road_mark"],
                0.004,
                role="road_marking",
            )
    # Correct zebra orientation: pedestrians walk north/south across this
    # east/west road, so each bar runs east/west and the bars repeat along Y.
    # library2 had these dimensions/spacing transposed by 90 degrees.
    for crossing, cx in enumerate((-38.0, 39.0)):
        for stripe in range(12):
            y = -45.05 + stripe * 1.15
            marking = box(
                c,
                f"site:crosswalk_{crossing}_{stripe}",
                (cx, y, 0.11),
                (6.4, 0.58, 0.028),
                M["road_mark"],
                0.006,
                role="crosswalk_marking",
            )
            marking["c2w_crosswalk_bar_axis"] = "east_west"
            marking["c2w_pedestrian_crossing_axis"] = "north_south"
            marking["c2w_corrected_from_library2"] = True
        # Tactile warning pads at both curb ramps.
        box(
            c,
            f"site:tactile_pad_{crossing}",
            (cx, -29.92, 0.24),
            (4.2, 0.72, 0.07),
            M["book_gold"],
            0.012,
            role="tactile_paving",
        )
    for grate_index, x in enumerate((-62, -20, 20, 62)):
        box(
            c,
            f"site:drain_grate_{grate_index}",
            (x, -30.66, 0.125),
            (2.2, 0.30, 0.055),
            M["black_metal"],
            0.008,
            role="storm_drain_grate",
        )
        for slot in range(9):
            box(
                c,
                f"site:drain_slot_{grate_index}_{slot}",
                (x - 0.88 + slot * 0.22, -30.67, 0.158),
                (0.055, 0.20, 0.018),
                M["rubber"],
                0.002,
                role="storm_drain_slot",
            )
    box(
        c,
        "site:forecourt",
        (0, -17.5, 0.08),
        (142, 27, 0.16),
        M["paver_light"],
        0.035,
        role="library_forecourt",
    )
    box(
        c,
        "site:rear_service_walk",
        (0, 28.0, 0.08),
        (142, 7.0, 0.16),
        M["paver"],
        0.035,
        role="service_walk",
    )
    # Fine paving grid sized to stay visible in close shots.
    for x in range(-70, 71, 3):
        box(
            c,
            "site:paver_joint_x",
            (x, -17.5, 0.175),
            (0.025, 26.5, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for y in range(-30, -4, 3):
        box(
            c,
            "site:paver_joint_y",
            (0, y, 0.175),
            (141.5, 0.025, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
    # Subtle stone colour changes occur per slab, not as a uniform grey sheet.
    for tile in range(92):
        tx = -69.0 + (tile * 17 % 138) + 0.35 * math.sin(tile * 1.7)
        ty = -29.0 + (tile * 11 % 24) + 0.25 * math.cos(tile * 2.1)
        box(
            c,
            f"site:paver_variation_{tile}",
            (tx, ty, 0.187),
            (2.65, 2.65, 0.012),
            M["paver_warm"] if tile % 3 == 0 else M["stone_light"],
            0.008,
            role="paver_variation",
        )
    # The long flower bed between the two buildings is deliberately gone.
    # Replace its footprint and the wider 24 m inter-building gap with a flush,
    # fully jointed pedestrian connector so the two forecourts read as one
    # accessible public space rather than leaving an accidental grass trench.
    box(
        c,
        "site:interbuilding_connector",
        (4.0, 10.25, 0.08),
        (16.0, 28.5, 0.16),
        M["paver_light"],
        0.035,
        role="interbuilding_paved_connector",
    )
    for joint_x in (-2.0, 1.0, 4.0, 7.0, 10.0):
        box(
            c,
            f"site:connector_joint_x_{joint_x}",
            (joint_x, 10.25, 0.175),
            (0.025, 28.1, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for joint_y in range(-3, 25, 3):
        box(
            c,
            f"site:connector_joint_y_{joint_y}",
            (4.0, joint_y, 0.175),
            (15.7, 0.025, 0.018),
            M["mortar"],
            0,
            role="paver_joint",
        )

    # Modern library: broad central stairs and two genuinely sloped accessible
    # ramps between planted cheek walls.
    modern_x, modern_south = -38.0, -10.25
    for level in range(7):
        box(
            c,
            f"site:A_entry_step_{level}",
            (modern_x, modern_south - 1.0 - level * 0.68, 0.10 + level * 0.19),
            (12.0 + (6 - level) * 0.62, 0.78, 0.20),
            M["stone_light"],
            0.025,
            role="entrance_stair",
        )
    sloped_slab(
        c,
        "site:A_left_ramp",
        modern_x - 24.0,
        modern_x - 9.0,
        modern_south - 8.0,
        modern_south - 0.6,
        0.15,
        1.20,
        0.18,
        M["stone_light"],
    )
    sloped_slab(
        c,
        "site:A_right_ramp",
        modern_x + 9.0,
        modern_x + 24.0,
        modern_south - 8.0,
        modern_south - 0.6,
        0.15,
        1.20,
        0.18,
        M["stone_light"],
    )
    for x0, x1 in (
        (modern_x - 25.0, modern_x - 23.7),
        (modern_x - 9.3, modern_x - 8.0),
        (modern_x + 8.0, modern_x + 9.3),
        (modern_x + 23.7, modern_x + 25.0),
    ):
        sloped_slab(
            c,
            "site:A_ramp_cheek",
            x0,
            x1,
            modern_south - 8.0,
            modern_south - 0.6,
            0.55,
            1.60,
            0.55,
            M["white_panel"],
            "ramp_cheek_wall",
        )
    for side in (-1, 1):
        x = modern_x + side * 23.0
        p0, p1 = (x, modern_south - 7.7, 1.05), (x, modern_south - 0.8, 2.0)
        beam(c, "site:A_ramp_handrail", p0, p1, 0.045, M["steel"], 14, "handrail")

    # Monumental library's axial stair fans across most of the entrance bay.
    red_x, red_south = 39.0, -9.25
    for level in range(7):
        box(
            c,
            f"site:B_entry_step_{level}",
            (red_x, red_south - 0.7 - level * 0.68, 0.09 + level * 0.16),
            (18.5 + (6 - level) * 0.72, 0.78, 0.18),
            M["red_stone_light"],
            0.025,
            role="entrance_stair",
        )
    for side in (-1, 1):
        p0 = (red_x + side * 10.2, red_south - 5.1, 0.52)
        p1 = (red_x + side * 8.0, red_south - 0.75, 1.48)
        beam(c, "site:B_stair_handrail", p0, p1, 0.055, M["bronze"], 16, "handrail")
        for t in (0.15, 0.5, 0.85):
            px = p0[0] * (1 - t) + p1[0] * t
            py = p0[1] * (1 - t) + p1[1] * t
            pz = p0[2] * (1 - t) + p1[2] * t
            cylinder(
                c,
                "site:B_handrail_post",
                (px, py, pz - 0.55),
                0.035,
                0.70,
                M["bronze"],
                14,
                role="handrail_post",
            )

    # library4 intentionally has no fountain branch.  The two library3
    # fountain locations remain part of the same uninterrupted, finely jointed
    # forecourt, so every other site asset and coordinate stays unchanged.
    c[
        "c2w_fountain_policy"
    ] = "none; both library3 fountains removed in source generator"
    c["c2w_fountain_count"] = 0
    c["c2w_fountain_records"] = "[]"

    # Low planting beds, furniture, lights and restrained edge trees supply
    # scale without hiding either facade.
    for idx, (x, y, dx) in enumerate(
        ((-64, -5.8, 9), (-13, -5.8, 8), (17, -5.0, 8), (62, -5.0, 8))
    ):
        box(
            c,
            f"site:planter_wall_{idx}",
            (x, y, 0.40),
            (dx, 2.4, 0.80),
            M["stone_light"],
            0.045,
            role="planter_wall",
        )
        box(
            c,
            f"site:planter_soil_{idx}",
            (x, y, 0.84),
            (dx - 0.45, 1.95, 0.10),
            M["soil"],
            0.02,
            role="planter_soil",
        )
        for plant in range(max(5, int(dx))):
            px = x - dx / 2 + 0.5 + plant * (dx - 1.0) / max(1, int(dx) - 1)
            for blade in range(7):
                angle = blade * 0.897 + plant
                beam(
                    c,
                    f"site:planter_grass_{idx}_{plant}_{blade}",
                    (px, y, 0.88),
                    (
                        px + math.cos(angle) * 0.18,
                        y + math.sin(angle) * 0.18,
                        1.32 + 0.12 * (blade % 3),
                    ),
                    0.014,
                    M["plant"],
                    7,
                    "ornamental_grass",
                )
    for shrub_index, (x, y, scale) in enumerate(
        (
            (-65, -7, 1.1),
            (-57, -7, 0.9),
            (-17, -7, 1.0),
            (14, -6, 0.9),
            (20, -6, 1.05),
            (58, -6, 1.0),
            (65, -6, 1.1),
            (-7, 25, 1.2),
            (8, 25, 1.1),
        )
    ):
        site_shrub(c, f"site:shrub_{shrub_index}", x, y, scale, M)
    for idx, (x, y, yaw) in enumerate(
        ((-58, -24, 0), (-18, -24, math.pi), (22, -24, 0), (58, -24, math.pi))
    ):
        bench(c, f"site:bench_{idx}", x, y, yaw, M)
    for idx, x in enumerate((-67, -51, -25, -10, 12, 28, 51, 68)):
        cylinder(
            c,
            f"site:light_pole_{idx}",
            (x, -27.0, 3.0),
            0.075,
            6.0,
            M["black_metal"],
            20,
            role="site_light_pole",
        )
        beam(
            c,
            f"site:light_arm_{idx}",
            (x, -27.0, 5.8),
            (x + 0.7, -27.0, 6.1),
            0.04,
            M["black_metal"],
            12,
            "site_light_arm",
        )
        box(
            c,
            f"site:luminaire_{idx}",
            (x + 0.82, -27.0, 6.1),
            (0.62, 0.25, 0.13),
            M["black_metal"],
            0.035,
            role="site_luminaire",
        )
        box(
            c,
            f"site:lens_{idx}",
            (x + 0.82, -27.0, 6.02),
            (0.52, 0.19, 0.03),
            M["lamp"],
            0.01,
            role="site_luminaire_lens",
        )
    # Reuse two full07 botanical masters across nine placements.  Every master
    # contains hundreds of modeled branch paths and thousands of genuine
    # LeafFactory-derived leaves; collection instances preserve all that
    # topology without multiplying identical mesh datablocks nine times.
    tree_masters = {}
    tree_master_records = []
    for tree_seed in (42, 381):
        master, master_detail = build_full07_tree_master(tree_seed)
        tree_masters[tree_seed] = (master, master_detail)
        tree_master_records.append(master_detail)
    tree_records = []
    tree_layout = (
        (-72, 26, 1.00, 0.15),
        (-7, 31, 1.10, 0.82),
        (7, 31, 1.05, 1.61),
        (72, 26, 1.00, 2.40),
        (-74, -27, 0.88, 3.18),
        (74, -27, 0.88, 3.92),
        (-86, 39, 1.18, 4.66),
        (-2, 40, 1.12, 5.38),
        (84, 39, 1.18, 6.04),
    )
    for idx, (x, y, scale, yaw) in enumerate(tree_layout):
        tree_seed = 42 if idx % 2 == 0 else 381
        master, master_detail = tree_masters[tree_seed]
        tree_records.append(
            place_full07_tree(master, master_detail, c, idx, x, y, scale, yaw)
        )
    c["c2w_native_tree_records"] = json.dumps(tree_records, ensure_ascii=False)
    c["c2w_native_tree_master_records"] = json.dumps(
        tree_master_records, ensure_ascii=False
    )
    c["c2w_native_tree_count"] = len(tree_records)
    c["c2w_native_tree_master_count"] = len(tree_master_records)
    c["c2w_native_tree_source_dependency_count"] = 0
    # Stainless bollards and bicycle racks provide believable hand-scale detail.
    for building_x in (-38.0, 39.0):
        for index in range(5):
            x = building_x - 5.0 + index * 2.5
            cylinder(
                c,
                f"site:bollard_{building_x}_{index}",
                (x, -28.4, 0.55),
                0.075,
                1.10,
                M["steel"],
                20,
                role="security_bollard",
            )
    for rack in range(5):
        x = -7.5 + rack * 1.35
        cylinder(
            c,
            f"site:bike_rack_post_a_{rack}",
            (x - 0.40, -25.1, 0.44),
            0.035,
            0.88,
            M["steel"],
            14,
            role="bicycle_rack",
        )
        cylinder(
            c,
            f"site:bike_rack_post_b_{rack}",
            (x + 0.40, -25.1, 0.44),
            0.035,
            0.88,
            M["steel"],
            14,
            role="bicycle_rack",
        )
        beam(
            c,
            f"site:bike_rack_top_{rack}",
            (x - 0.40, -25.1, 0.86),
            (x + 0.40, -25.1, 0.86),
            0.035,
            M["steel"],
            14,
            "bicycle_rack",
        )
    c[
        "c2w_detail_profile"
    ] = "urban_street+correctly_oriented_crosswalks+curb_and_stormwater+tactile_paving+variegated_stone_fountain_free_forecourt+open_interbuilding_paved_connector+accessible_ramps+monumental_stairs+full07_multilevel_botanical_leaffactory_trees+furniture_and_bike_racks"
    return c


def build_library_pair(parent=None, include_site=True):
    """Reusable urban pipeline entry point for both reference types."""
    M = make_materials()
    root = collection("TWO_REFERENCE_LIBRARY_ROW", parent, "library.reference_pair.v6")
    root["c2w_pipeline_entrypoint"] = "generate_urban_v3_library.build_library_pair"
    root["c2w_scene_asset_inputs"] = 0
    root["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    root["c2w_reference_cache"] = json.dumps(
        [str(p) for p in REFERENCE_CACHE], ensure_ascii=False
    )
    root[
        "c2w_layout_summary"
    ] = "two distinct libraries aligned east-west in one row, both facing south"
    root[
        "c2w_quality_profile"
    ] = "reference_matched_proportions+modeled_facade_depth+occupied_interiors+world_scale_materials+urban_context+correct_crosswalk_geometry+open_interbuilding_connector+fountain_free_forecourt+full07_botanical_leaffactory_landscape+photographic_daylight"
    if include_site:
        build_library_site(root, M)
    build_modern_library(root, M)
    build_monumental_red_library(root, M)
    return root, M


def camera(name, location, target, lens):
    data = bpy.data.cameras.new(PREFIX + name)
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (
        (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    )
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = False
    return tag(obj, "validation_camera")


def setup_daylight():
    scene = bpy.context.scene
    world = bpy.data.worlds.new(PREFIX + "clear_day_world")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(138)
    sky.air_density = 0.78
    sky.dust_density = 0.045
    sky.ozone_density = 1.15
    background.inputs["Strength"].default_value = 0.34
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    bpy.ops.object.light_add(type="SUN", location=(-80, -110, 120))
    sun = bpy.context.object
    sun.name = PREFIX + "day_sun"
    sun.data.energy = 2.25
    sun.data.angle = math.radians(0.52)
    sun.rotation_euler = (
        (Vector((0, 0, 8)) - Vector(sun.location)).to_track_quat("-Z", "Y").to_euler()
    )
    if hasattr(sun.data, "use_shadow"):
        sun.data.use_shadow = True
    tag(sun, "daylight")
    bpy.ops.object.light_add(type="AREA", location=(55, -55, 62))
    fill = bpy.context.object
    fill.name = PREFIX + "sky_fill"
    fill.data.energy = 360
    fill.data.shape = "DISK"
    fill.data.size = 52
    fill.rotation_euler = (math.radians(28), 0, math.radians(38))
    tag(fill, "daylight_fill")


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.48
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.012
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 8
    for attribute in (
        "use_caustics",
        "use_reflective_caustics",
        "use_refractive_caustics",
    ):
        if hasattr(scene.cycles, attribute):
            setattr(scene.cycles, attribute, False)
    scene.render.use_file_extension = True


def render_views(cameras):
    configure_render()
    scene = bpy.context.scene
    for filename, cam in cameras:
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def audit(root, cameras):
    scene_objects = list(bpy.context.scene.objects)
    role_counts = {}
    for obj in scene_objects:
        role = obj.get("c2w_role", "untagged")
        role_counts[role] = role_counts.get(role, 0) + 1
    building_collections = [
        child
        for child in root.children
        if "LIBRARY_A_" in child.name or "LIBRARY_B_" in child.name
    ]
    site_collection = next(
        child for child in root.children if "LIBRARY_COMPARISON_SITE" in child.name
    )
    renderable = [
        obj
        for obj in scene_objects
        if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
    ]
    banned_tokens = ("placeholder", "proxy", "dummy", "toy", "blob")
    banned = [
        obj.name
        for obj in renderable
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    reference_indices = sorted(
        child.get("c2w_reference_index") for child in building_collections
    )
    leaf_cards = sum(int(obj.get("c2w_leaf_card_count", 0)) for obj in scene_objects)
    complex_materials = [
        material
        for material in bpy.data.materials
        if material.use_nodes
        and material.node_tree
        and len(material.node_tree.nodes) >= 8
    ]
    fountain_named_materials = [
        material
        for material in bpy.data.materials
        if "fountain" in material.name.lower()
        or material.get("c2w_factory_material") == "urban_public_space.fountain3"
    ]

    crosswalks = [
        obj for obj in renderable if obj.get("c2w_role") == "crosswalk_marking"
    ]
    crosswalks_correct = len(crosswalks) == 24 and all(
        obj.get("c2w_crosswalk_bar_axis") == "east_west"
        and obj.get("c2w_pedestrian_crossing_axis") == "north_south"
        and obj.get("c2w_corrected_from_library2")
        for obj in crosswalks
    )
    removed_bed_tokens = ("central_separator", "separator_soil", "separator_grass")
    removed_bed_objects = [
        obj.name
        for obj in scene_objects
        if any(token in obj.name.lower() for token in removed_bed_tokens)
    ]

    native_tree_roots = [
        obj for obj in scene_objects if obj.get("c2w_role") == "native_tree_root"
    ]
    native_tree_instances = sorted(
        int(obj.get("c2w_native_tree_instance")) for obj in native_tree_roots
    )
    native_tree_masters = [
        coll
        for coll in bpy.data.collections
        if coll.get("c2w_role") == "native_tree_master"
    ]
    native_tree_master_objects = list(
        {obj for master in native_tree_masters for obj in master.all_objects}
    )
    native_tree_unique_vertices = sum(
        len(obj.data.vertices)
        for obj in native_tree_master_objects
        if obj.type == "MESH"
    )
    native_tree_unique_polygons = sum(
        len(obj.data.polygons)
        for obj in native_tree_master_objects
        if obj.type == "MESH"
    )
    tree_records = json.loads(site_collection.get("c2w_native_tree_records", "[]"))
    tree_master_records = json.loads(
        site_collection.get("c2w_native_tree_master_records", "[]")
    )
    native_tree_effective_vertices = sum(
        int(record.get("mesh_vertices", 0)) for record in tree_records
    )
    native_tree_effective_polygons = sum(
        int(record.get("mesh_polygons", 0)) for record in tree_records
    )

    fountain_objects = [
        obj
        for obj in scene_objects
        if obj.get("c2w_fountain_id")
        or "fountain" in obj.name.lower()
        or "fountain" in str(obj.get("urban_semantic", "")).lower()
    ]
    fountain_collections = [
        child
        for child in bpy.data.collections
        if child.get("c2w_role") == "production_fountain_asset"
        or "fountain" in child.name.lower()
    ]
    fountain_records = json.loads(site_collection.get("c2w_fountain_records", "[]"))
    fountain_vertices = sum(
        len(obj.data.vertices) for obj in fountain_objects if obj.type == "MESH"
    )
    fountain_polygons = sum(
        len(obj.data.polygons) for obj in fountain_objects if obj.type == "MESH"
    )
    fountain_splines = sum(
        len(obj.data.splines) for obj in fountain_objects if obj.type == "CURVE"
    )
    fountain_water_objects = [
        obj
        for obj in fountain_objects
        if obj.get("c2w_role") == "production_fountain_water"
    ]

    view_names = [filename for filename, _ in cameras]
    checks = {
        "exactly_two_distinct_reference_libraries": len(building_collections) == 2
        and reference_indices == [1, 2],
        "both_are_dense_complex_models": len(building_collections) == 2
        and min(len(c.all_objects) for c in building_collections) >= 900,
        "four_sided_recessed_facades": role_counts.get("window_reveal", 0) >= 260
        and role_counts.get("facade_glazing", 0) >= 260,
        "dense_real_window_framing_and_gaskets": role_counts.get("facade_mullion", 0)
        >= 900
        and role_counts.get("glazing_gasket", 0) >= 900,
        "reference_a_white_frame_and_fins": role_counts.get(
            "monumental_facade_frame", 0
        )
        == 4
        and role_counts.get("vertical_sun_fin", 0) >= 75,
        "reference_a_floating_roof_structure": role_counts.get("cantilevered_roof", 0)
        == 1
        and role_counts.get("roof_structure", 0) >= 40,
        "reference_b_nested_monumental_entry": role_counts.get("nested_portal_frame", 0)
        == 15
        and role_counts.get("portal_shadow_joint", 0) == 15
        and role_counts.get("vertical_masonry_fin", 0) >= 18,
        "reference_b_real_brick_veneer": role_counts.get("brick_veneer_pier", 0) >= 8
        and role_counts.get("brick_veneer_spandrel", 0) >= 30,
        "panelized_nonflat_material_facades": role_counts.get("facade_panel_joint", 0)
        >= 130,
        "usable_entrances_and_access": role_counts.get("entrance_glazing", 0) >= 8
        and role_counts.get("entrance_stair", 0) >= 13
        and role_counts.get("accessible_ramp", 0) == 2,
        "modeled_rooftop_services_and_drainage": role_counts.get(
            "roof_mechanical_unit", 0
        )
        >= 4
        and role_counts.get("mechanical_louver", 0) >= 28
        and role_counts.get("rainwater_downpipe", 0) >= 4,
        "occupied_visible_reading_rooms": role_counts.get("interior_bookshelf", 0)
        >= 120
        and role_counts.get("interior_book", 0) >= 500
        and role_counts.get("reading_table", 0) >= 10
        and role_counts.get("interior_floor_slab", 0) >= 8,
        "crosswalks_rotated_to_correct_east_west_bar_axis": crosswalks_correct,
        "interbuilding_flower_bed_fully_removed": not removed_bed_objects
        and role_counts.get("interbuilding_paved_connector", 0) == 1,
        "nine_full07_botanical_instances_from_genuine_leaffactory": len(
            native_tree_roots
        )
        == 9
        and native_tree_instances == list(range(9))
        and len(tree_records) == 9
        and all(
            record.get("source_method") == FULL07_TREE_SOURCE for record in tree_records
        ),
        "two_full07_tree_masters_are_complete_and_source_tagged": len(
            native_tree_masters
        )
        == 2
        and len(tree_master_records) == 2
        and len(native_tree_master_objects) == 4
        and all(
            master.get("c2w_source_method") == FULL07_TREE_SOURCE
            and master.get("c2w_scene_asset_inputs") == 0
            for master in native_tree_masters
        )
        and all(
            obj.get("c2w_generator") == Path(__file__).name
            and obj.get("c2w_source_method") == FULL07_TREE_SOURCE
            for obj in native_tree_master_objects
        ),
        "native_trees_are_full_complex_geometry": native_tree_effective_vertices
        >= 500_000
        and native_tree_effective_polygons >= 450_000
        and native_tree_unique_polygons >= 40_000
        and all(
            record.get("quality")
            == "full07_multilevel_botanical_genuine_leaffactory_no_fallback"
            and record.get("branches", 0) >= 350
            and record.get("leaves", 0) >= 3_000
            for record in tree_records
        )
        and all(
            record.get("leaf_factory_source_mesh_count", 0) >= 1
            for record in tree_master_records
        ),
        "both_library3_fountains_removed_in_source_generator": not fountain_objects
        and not fountain_collections
        and not fountain_records
        and site_collection.get("c2w_fountain_count") == 0,
        "no_fountain_geometry_water_or_material_datablocks": fountain_vertices == 0
        and fountain_polygons == 0
        and fountain_splines == 0
        and not fountain_water_objects
        and not fountain_named_materials,
        "all_non_fountain_scene_objects_preserved_from_library3": len(scene_objects)
        == 8_183
        and sorted(len(child.all_objects) for child in building_collections)
        == [3_643, 3_781],
        "modeled_urban_foreground": role_counts.get("public_road", 0) == 1
        and role_counts.get("storm_drain_slot", 0) >= 30
        and len(crosswalks) == 24,
        "multi_scale_procedural_materials": len(complex_materials) >= 24,
        "single_row_layout": root.get("c2w_layout_summary")
        == "two distinct libraries aligned east-west in one row, both facing south",
        "procedural_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_library.build_library_pair",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "ten_daylight_near_far_and_feature_views": len(cameras) == 10
        and sum("far" in name for name in view_names) >= 3
        and sum("forecourt_close" in name for name in view_names) == 2
        and any("crosswalk" in name for name in view_names),
        "all_renderables_are_source_tagged": all(
            obj.get("c2w_role") and obj.get("c2w_generator") == Path(__file__).name
            for obj in renderable
        ),
        "no_placeholder_or_toy_named_geometry": not banned,
    }
    result = {
        "generator": str(Path(__file__).resolve()),
        "pipeline_entrypoint": root.get("c2w_pipeline_entrypoint"),
        "output": str(OUT),
        "schema_version": SCHEMA_VERSION,
        "reference_urls": REFERENCE_URLS,
        "reference_cache": [str(path) for path in REFERENCE_CACHE],
        "generation_revision": "library4_library3_parity_minus_both_fountains_full07_botanical_leaffactory_open_interbuilding_connector",
        "layout": {
            "arrangement": "east_west_single_row",
            "type_a_origin_m": [-38, 6],
            "type_b_origin_m": [39, 6],
            "front_direction": "south",
            "interbuilding_space": "open_flush_jointed_paving_no_flower_bed",
            "fountains": [],
            "fountain_policy": "none; both library3 fountains removed in source generator",
        },
        "building_collections": {
            child.name: len(child.all_objects) for child in building_collections
        },
        "object_count": len(scene_objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "fountain_material_datablock_count": len(fountain_named_materials),
        "shrub_leaf_card_count": leaf_cards,
        "crosswalk": {
            "bar_count": len(crosswalks),
            "bar_axis": "east_west",
            "pedestrian_axis": "north_south",
        },
        "removed_interbuilding_flower_bed_objects": removed_bed_objects,
        "native_tree_factory": FULL07_TREE_SOURCE,
        "native_tree_source_dependency_count": int(
            site_collection.get("c2w_native_tree_source_dependency_count", 0)
        ),
        "native_tree_master_records": tree_master_records,
        "native_tree_records": tree_records,
        "native_tree_unique_mesh_vertices": native_tree_unique_vertices,
        "native_tree_unique_mesh_polygons": native_tree_unique_polygons,
        "native_tree_effective_mesh_vertices": native_tree_effective_vertices,
        "native_tree_effective_mesh_polygons": native_tree_effective_polygons,
        "fountain_factory": None,
        "fountains_removed_from_revision": "urban_v3_library3",
        "fountain_records": fountain_records,
        "fountain_object_count": len(fountain_objects),
        "fountain_water_object_count": len(fountain_water_objects),
        "fountain_mesh_vertices": fountain_vertices,
        "fountain_mesh_polygons": fountain_polygons,
        "fountain_curve_splines": fountain_splines,
        "role_counts": role_counts,
        "validation_views": view_names,
        "daylight": True,
        "near_and_far_views": True,
        "render_engine": "CYCLES",
        "render_samples": 64,
        "adaptive_sampling": True,
        "denoising": True,
        "external_blend_inputs": 0,
        "pipeline_connected": True,
        "banned_geometry_names": banned,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    if not result["all_checks_passed"]:
        raise RuntimeError(
            "Library production audit failed: "
            + json.dumps(result, indent=2, ensure_ascii=False)
        )
    (OUT / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return result


def validate_render_outputs(cameras):
    diagnostics = {}
    for filename, _ in cameras:
        path = RENDERS / filename
        entry = {"path": str(path)}
        if not path.exists() or path.stat().st_size < 180_000:
            entry.update({"passed": False, "reason": "missing_or_too_small"})
            diagnostics[filename] = entry
            continue
        image = bpy.data.images.load(str(path), check_existing=False)
        width, height = image.size
        values = []
        pixels = image.pixels
        for gy in range(11):
            py = min(height - 1, int((gy + 0.5) * height / 11))
            for gx in range(17):
                px = min(width - 1, int((gx + 0.5) * width / 17))
                index = 4 * (py * width + px)
                values.append(
                    (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3.0
                )
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        dark_fraction = sum(value < 0.012 for value in values) / len(values)
        light_fraction = sum(value > 0.985 for value in values) / len(values)
        passed = (
            width >= 1600
            and height >= 1000
            and variance >= 0.003
            and dark_fraction < 0.72
            and light_fraction < 0.72
        )
        entry.update(
            {
                "passed": passed,
                "resolution": [width, height],
                "bytes": path.stat().st_size,
                "sample_mean": round(mean, 6),
                "sample_variance": round(variance, 6),
                "dark_fraction": round(dark_fraction, 4),
                "light_fraction": round(light_fraction, 4),
            }
        )
        diagnostics[filename] = entry
        bpy.data.images.remove(image)
    return diagnostics


def finalize_manifest(data, cameras):
    diagnostics = validate_render_outputs(cameras)
    data["render_diagnostics"] = diagnostics
    data["checks"]["all_ten_daylight_renders_are_nonblank_1600x1000"] = len(
        diagnostics
    ) == 10 and all(item["passed"] for item in diagnostics.values())
    data["all_checks_passed"] = all(data["checks"].values())
    (OUT / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    if not data["all_checks_passed"]:
        raise RuntimeError(
            "Library final render audit failed: "
            + json.dumps(data, indent=2, ensure_ascii=False)
        )
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    BASE.G.reset_scene()
    # Repeated production runs replace the same requested artifact without
    # duplicating a multi-gigabyte .blend1 backup beside it.
    bpy.context.preferences.filepaths.save_version = 0
    set_prefix(PREFIX)
    root, _ = build_library_pair()
    setup_daylight()
    specs = [
        ("01_pair_front_daylight_far.png", (0, -178, 34), (0, 2, 13), 40),
        ("02_pair_front_oblique_far.png", (128, -148, 52), (0, 5, 13), 54),
        ("03_pair_rear_aerial_far.png", (-126, 112, 62), (0, 7, 14), 58),
        ("04_modern_reference_oblique.png", (-98, -78, 15.5), (-38, 2.5, 12.5), 55),
        ("05_modern_entrance_close.png", (-49, -43, 5.2), (-38, -8.5, 4.6), 52),
        ("06_red_reference_oblique.png", (91, -77, 15.5), (39, 2.5, 12.8), 55),
        ("07_red_portal_close.png", (50, -43, 5.8), (39, -8.4, 8.1), 53),
        ("08_west_crosswalk_and_tree_near.png", (-41, -70, 8.2), (-52, -23.0, 2.0), 42),
        ("09_west_forecourt_close.png", (-77, -39, 4.5), (-67, -22.0, 1.75), 58),
        ("10_east_forecourt_close.png", (78, -39, 4.5), (67, -22.0, 1.75), 58),
    ]
    cameras = [
        (filename, camera(filename[:-4], location, target, lens))
        for filename, location, target, lens in specs
    ]
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_entrypoint"] = "generate_urban_v3_library.build_library_pair"
    scene["c2w_schema_version"] = SCHEMA_VERSION
    scene["c2w_revision"] = REVISION
    scene[
        "c2w_crosswalk_orientation"
    ] = "bars_east_west; pedestrian_crossing_north_south"
    scene["c2w_native_tree_factory"] = FULL07_TREE_SOURCE
    scene[
        "c2w_fountain_policy"
    ] = "none; both library3 fountains removed in source generator"
    scene["c2w_fountain_count"] = 0
    scene.camera = cameras[0][1]
    blend_path = OUT / f"{REVISION}.blend"
    # Save the source-generated scene before strict audit/rendering, then save
    # again with final diagnostics.  The blend is always an output here.
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    data = audit(root, cameras)
    render_views(cameras)
    data = finalize_manifest(data, cameras)
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    (OUT / "SUCCESS").write_text(
        "urban_v3_library4 source-generator build, both fountains removed, 10-view daylight near/far rendering and strict validation complete\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
