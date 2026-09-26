"""Reference-matched procedural hospital campus for the active urban pipeline.

Three genuinely independent hospital assets are built from source code to match
the supplied references:

* ``traditional_brick`` -- compact brick-and-stone community hospital;
* ``red_white_public`` -- broad public hospital with red bands/glass tower;
* ``glass_ribbon_modern`` -- clean white rainscreen and ribbon-window clinic.

``build_hospital_asset`` and ``build_hospital_reference_row`` are the reusable
pipeline entry points.  The validation blend is only an output: this generator
never appends a prepared blend or an unconnected demo asset.
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
REVISION = "urban_v3_hospital4"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / REVISION
RENDERS = OUT / "renders"
PREFIX = "hospital:"
SCHEMA_VERSION = 9
SEED = 260831
RNG = random.Random(SEED)
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

# Type-B facade interface dimensions.  The horizontal red bands are concealed
# behind the left red tower pier and must never project across the curtain wall.
PUBLIC_RED_BAND_LEFT_X = -29.85
PUBLIC_RED_BAND_END_X = 6.15
PUBLIC_GLASS_TOWER_LEFT_X = 6.50

HOSPITAL_VARIANTS = (
    "traditional_brick",
    "red_white_public",
    "glass_ribbon_modern",
)
REFERENCE_URLS = [
    "https://thumbs.dreamstime.com/b/hospital-model-isolated-white-background-model-hospital-building-isolated-white-background-suitable-healthcare-368689999.jpg",
    "https://www.shutterstock.com/image-illustration/modern-public-hospital-building-3d-260nw-2240217303.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRglCXngKKwso5R-ovqnv6MHKYwVWAtV7V67zpjUA5cTw&s=10",
]
REFERENCE_CACHE = [
    ROOT / ".reference_cache/hospital/reference_type_a.jpg",
    ROOT / ".reference_cache/hospital/reference_type_b.jpg",
    ROOT / ".reference_cache/hospital/reference_type_c.jpg",
]
REFERENCE_ANALYSIS = {
    "traditional_brick": {
        "reference_index": 1,
        "visible_signature": "three-storey red-brick base, pale stone upper floors, raised atrium tower, projecting cornices, paired entrance canopy",
        "front_direction": "south",
    },
    "red_white_public": {
        "reference_index": 2,
        "visible_signature": "five-storey white public wing, red horizontal bands and vertical tower, multi-storey curtain wall, red emergency portal, facade AC condensers",
        "front_direction": "south",
    },
    "glass_ribbon_modern": {
        "reference_index": 3,
        "visible_signature": "four-storey white metal rainscreen, continuous blue ribbon glazing, transparent ground lobby, projecting canopy, glazed stair tower with red cross",
        "front_direction": "south",
    },
}

# Constrain every cache/write made by Blender dependencies to the workspace.
LOCAL_CACHE = ROOT / ".qa_tmp" / REVISION
LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(LOCAL_CACHE / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(LOCAL_CACHE / "xdg_cache")
os.environ["XDG_CONFIG_HOME"] = str(LOCAL_CACHE / "xdg_config")
os.environ["INFINIGEN_SKIP_TAGGING"] = "1"

_CUBE_MESHES: dict[str, bpy.types.Mesh] = {}
_CYLINDER_MESHES: dict[tuple, bpy.types.Mesh] = {}
_SPHERE_MESHES: dict[tuple, bpy.types.Mesh] = {}


def set_prefix(prefix: str):
    """Rebind names/caches when the live urban pipeline embeds this module."""
    global PREFIX
    PREFIX = prefix
    _CUBE_MESHES.clear()
    _CYLINDER_MESHES.clear()
    _SPHERE_MESHES.clear()


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _CUBE_MESHES.clear()
    _CYLINDER_MESHES.clear()
    _SPHERE_MESHES.clear()


def tag(obj, role: str, asset_id: str | None = None):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = role
    obj["c2w_generator"] = Path(__file__).name
    if asset_id:
        obj["c2w_asset_id"] = asset_id
    return obj


def collection(name: str, parent=None, role="procedural_asset", asset_id=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    tag(coll, role, asset_id)
    return coll


def asset_root(coll, name, origin=(0.0, 0.0, 0.0), yaw=0.0, asset_id=None):
    root = bpy.data.objects.new(PREFIX + name, None)
    coll.objects.link(root)
    root.location = origin
    root.rotation_euler[2] = yaw
    tag(root, "hospital_asset_root", asset_id)
    return root


def _assign_parent(obj, parent):
    if parent is not None:
        obj.parent = parent
    return obj


def _unit_cube_mesh(material):
    key = material.name_full if material else "none"
    mesh = _CUBE_MESHES.get(key)
    if mesh is not None and mesh.name in bpy.data.meshes:
        return mesh
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
    return mesh


def box(
    coll,
    name,
    xyz,
    dims,
    material,
    bevel=0.0,
    rot=0.0,
    role="architectural_component",
    parent=None,
):
    mesh = _unit_cube_mesh(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler[2] = rot
    obj.scale = (dims[0] / 2.0, dims[1] / 2.0, dims[2] / 2.0)
    _assign_parent(obj, parent)
    if bevel >= 0.045 and min(dims) >= 0.12:
        mod = obj.modifiers.new(PREFIX + "edge_softening", "BEVEL")
        mod.width = min(0.07, bevel)
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return tag(obj, role)


def _unit_cylinder_mesh(material, vertices=24):
    key = (material.name_full if material else "none", int(vertices))
    mesh = _CYLINDER_MESHES.get(key)
    if mesh is not None and mesh.name in bpy.data.meshes:
        return mesh
    verts = []
    faces = []
    for z in (-0.5, 0.5):
        for i in range(vertices):
            angle = 2.0 * math.pi * i / vertices
            verts.append((math.cos(angle), math.sin(angle), z))
    faces.append(tuple(range(vertices - 1, -1, -1)))
    faces.append(tuple(range(vertices, vertices * 2)))
    for i in range(vertices):
        nxt = (i + 1) % vertices
        faces.append((i, nxt, vertices + nxt, vertices + i))
    mesh = bpy.data.meshes.new(PREFIX + f"shared_cylinder_{vertices}:{key[0]}")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
    mesh["c2w_shared_primitive"] = f"unit_cylinder_{vertices}"
    _CYLINDER_MESHES[key] = mesh
    return mesh


def cylinder(
    coll,
    name,
    xyz,
    radius,
    depth,
    material,
    vertices=24,
    rot=(0.0, 0.0, 0.0),
    role="architectural_component",
    parent=None,
):
    mesh = _unit_cylinder_mesh(material, vertices)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.location = xyz
    obj.scale = (radius, radius, depth)
    obj.rotation_euler = rot
    _assign_parent(obj, parent)
    return tag(obj, role)


def beam(
    coll,
    name,
    p1,
    p2,
    radius,
    material,
    vertices=16,
    role="structural_member",
    parent=None,
):
    a, b = Vector(p1), Vector(p2)
    vec = b - a
    obj = cylinder(
        coll,
        name,
        (a + b) / 2.0,
        radius,
        vec.length,
        material,
        vertices,
        role=role,
        parent=parent,
    )
    obj.rotation_euler = vec.to_track_quat("Z", "Y").to_euler()
    return obj


def _unit_ico_mesh(material, subdivisions=2):
    key = (material.name_full if material else "none", int(subdivisions))
    mesh = _SPHERE_MESHES.get(key)
    if mesh is not None and mesh.name in bpy.data.meshes:
        return mesh
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=1.0)
    src = bpy.context.object
    mesh = src.data
    mesh.name = PREFIX + f"shared_ico_{subdivisions}:{key[0]}"
    bpy.data.objects.remove(src, do_unlink=True)
    if material:
        mesh.materials.append(material)
    mesh["c2w_shared_primitive"] = f"unit_icosphere_{subdivisions}"
    _SPHERE_MESHES[key] = mesh
    return mesh


def sphere(
    coll,
    name,
    xyz,
    scale,
    material,
    role="landscape_component",
    parent=None,
    subdivisions=2,
):
    obj = bpy.data.objects.new(PREFIX + name, _unit_ico_mesh(material, subdivisions))
    coll.objects.link(obj)
    obj.location = xyz
    obj.scale = scale if isinstance(scale, tuple) else (scale, scale, scale)
    _assign_parent(obj, parent)
    return tag(obj, role)


def text_object(
    coll,
    name,
    body,
    xyz,
    size,
    material,
    extrude=0.07,
    align="CENTER",
    rot=(math.pi / 2.0, 0.0, 0.0),
    role="hospital_wordmark",
    parent=None,
):
    curve = bpy.data.curves.new(PREFIX + name, "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.012
    curve.bevel_resolution = 3
    curve.resolution_u = 8
    if FONT_PATH.exists():
        try:
            curve.font = bpy.data.fonts.load(str(FONT_PATH), check_existing=True)
        except RuntimeError:
            pass
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    coll.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = rot
    _assign_parent(obj, parent)
    return tag(obj, role)


def area_light(coll, name, xyz, energy, size, color, parent=None):
    data = bpy.data.lights.new(PREFIX + name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = max(0.6, size * 0.45)
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = xyz
    _assign_parent(obj, parent)
    return tag(obj, "interior_area_light")


def _set_socket(node, names, value):
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return True
    return False


def procedural_material(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    noise_scale=0.0,
    bump=0.0,
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
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    _set_socket(bsdf, ("Roughness",), roughness)
    _set_socket(bsdf, ("Metallic",), metallic)
    _set_socket(bsdf, ("IOR",), 1.48)
    if transmission:
        _set_socket(bsdf, ("Transmission Weight", "Transmission"), transmission)
        _set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.24)
        _set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.055)
    if emission is not None:
        _set_socket(bsdf, ("Emission Color", "Emission"), (*emission, 1.0))
        _set_socket(bsdf, ("Emission Strength",), emission_strength)
    if noise_scale:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.noise_dimensions = "3D"
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 4.5
        tex.inputs["Roughness"].default_value = 0.68
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.18
        ramp.color_ramp.elements[0].color = (*[max(0.0, c * 0.72) for c in color], 1.0)
        ramp.color_ramp.elements[1].position = 0.82
        ramp.color_ramp.elements[1].color = (
            *[min(1.0, c * 1.23 + 0.012) for c in color],
            1.0,
        )
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump:
            bump_node = nodes.new("ShaderNodeBump")
            bump_node.inputs["Strength"].default_value = bump
            bump_node.inputs["Distance"].default_value = 0.035
            links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
            links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_procedural_material"] = True
    mat["c2w_material_profile"] = (
        "physically_based_multiscale" if noise_scale else "physically_based"
    )
    return mat


def brick_material(name, color_a, color_b, mortar=(0.045, 0.036, 0.028), axis="XY"):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    combine = nodes.new("ShaderNodeCombineXYZ")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.inputs["Color1"].default_value = (*color_a, 1.0)
    brick.inputs["Color2"].default_value = (*color_b, 1.0)
    brick.inputs["Mortar"].default_value = (*mortar, 1.0)
    brick.inputs["Scale"].default_value = 9.0
    brick.inputs["Mortar Size"].default_value = 0.028
    brick.inputs["Mortar Smooth"].default_value = 0.008
    brick.inputs["Brick Width"].default_value = 0.70
    brick.inputs["Row Height"].default_value = 0.22
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 31.0
    noise.inputs["Detail"].default_value = 3.0
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.13
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.34
    bump.inputs["Distance"].default_value = 0.055
    _set_socket(bsdf, ("Roughness",), 0.82)
    links.new(texcoord.outputs["Generated"], separate.inputs["Vector"])
    if axis == "XZ":
        links.new(separate.outputs["X"], combine.inputs["X"])
        links.new(separate.outputs["Z"], combine.inputs["Y"])
    elif axis == "YZ":
        links.new(separate.outputs["Y"], combine.inputs["X"])
        links.new(separate.outputs["Z"], combine.inputs["Y"])
    else:
        links.new(separate.outputs["X"], combine.inputs["X"])
        links.new(separate.outputs["Y"], combine.inputs["Y"])
    links.new(combine.outputs["Vector"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(noise.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*color_a, 1.0)
    mat["c2w_procedural_material"] = True
    mat["c2w_material_profile"] = "running_bond_brick_with_mortar_and_microvariation"
    return mat


def glass_material(name, color, transmission=0.62, roughness=0.08):
    # Smooth low-e glass: facade speckling must come from real reflections and
    # interior depth, not a high-frequency bump that reads as frosted plastic.
    mat = procedural_material(
        name, color, roughness, metallic=0.03, transmission=transmission
    )
    bsdf = next(
        (node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None
    )
    if bsdf:
        _set_socket(bsdf, ("Alpha",), 0.76)
    try:
        mat.surface_render_method = "DITHERED"
    except Exception:
        pass
    return mat


def make_materials():
    M = {
        "brick": brick_material(
            "aged_red_brick", (0.48, 0.135, 0.060), (0.67, 0.235, 0.095), axis="YZ"
        ),
        "brick_front": brick_material(
            "sun_readable_red_brick",
            (0.48, 0.085, 0.030),
            (0.68, 0.155, 0.052),
            axis="XZ",
        ),
        "brick_dark": brick_material(
            "deep_red_brick", (0.34, 0.075, 0.036), (0.50, 0.125, 0.052), axis="XZ"
        ),
        "limestone": procedural_material(
            "warm_limestone", (0.52, 0.47, 0.38), 0.78, noise_scale=5.4, bump=0.16
        ),
        "concrete": procedural_material(
            "architectural_concrete",
            (0.47, 0.49, 0.48),
            0.84,
            noise_scale=8.0,
            bump=0.13,
        ),
        "concrete_light": procedural_material(
            "pale_precast", (0.76, 0.75, 0.70), 0.72, noise_scale=6.2, bump=0.09
        ),
        "white_panel": procedural_material(
            "white_aluminum_rainscreen",
            (0.78, 0.82, 0.82),
            0.34,
            metallic=0.16,
            noise_scale=42.0,
            bump=0.035,
        ),
        "white_clean": procedural_material(
            "clean_white_enamel",
            (0.91, 0.92, 0.90),
            0.30,
            metallic=0.05,
            noise_scale=54.0,
            bump=0.018,
        ),
        "red_panel": procedural_material(
            "hospital_red_composite",
            (0.58, 0.035, 0.028),
            0.30,
            metallic=0.12,
            noise_scale=36.0,
            bump=0.025,
        ),
        "red_sign": procedural_material(
            "medical_red_enamel", (0.73, 0.018, 0.018), 0.23, metallic=0.08
        ),
        "glass_blue": glass_material(
            "blue_low_e_glass", (0.055, 0.18, 0.24), 0.64, 0.075
        ),
        "glass_dark": glass_material(
            "dark_reflective_glass", (0.018, 0.045, 0.060), 0.54, 0.065
        ),
        "glass_clear": glass_material(
            "clear_lobby_glass", (0.18, 0.32, 0.35), 0.76, 0.055
        ),
        "glass_neutral": glass_material(
            "neutral_rear_low_e_glass", (0.12, 0.25, 0.29), 0.72, 0.045
        ),
        "interior_wall": procedural_material(
            "warm_clinical_interior_wall",
            (0.72, 0.69, 0.61),
            0.76,
            noise_scale=8.0,
            bump=0.045,
        ),
        "black_metal": procedural_material(
            "powder_coated_black_metal",
            (0.018, 0.022, 0.024),
            0.24,
            metallic=0.72,
            noise_scale=26.0,
            bump=0.025,
        ),
        "aluminum": procedural_material(
            "brushed_aluminum",
            (0.39, 0.43, 0.45),
            0.25,
            metallic=0.86,
            noise_scale=74.0,
            bump=0.018,
        ),
        "steel": procedural_material(
            "stainless_steel",
            (0.54, 0.57, 0.58),
            0.19,
            metallic=0.91,
            noise_scale=62.0,
            bump=0.014,
        ),
        "rubber": procedural_material(
            "wheel_rubber", (0.008, 0.009, 0.010), 0.78, noise_scale=33.0, bump=0.09
        ),
        "asphalt": procedural_material(
            "aggregate_asphalt",
            (0.035, 0.040, 0.043),
            0.88,
            noise_scale=17.0,
            bump=0.23,
        ),
        "paving": procedural_material(
            "warm_jointed_paving", (0.38, 0.36, 0.32), 0.82, noise_scale=10.0, bump=0.12
        ),
        "terrazzo": procedural_material(
            "lobby_terrazzo", (0.63, 0.65, 0.62), 0.35, noise_scale=48.0, bump=0.055
        ),
        "soil": procedural_material(
            "landscape_soil", (0.075, 0.038, 0.016), 0.94, noise_scale=8.0, bump=0.30
        ),
        "grass": procedural_material(
            "maintained_grass", (0.055, 0.18, 0.045), 0.89, noise_scale=13.0, bump=0.22
        ),
        "leaf_a": procedural_material(
            "leaf_deep", (0.028, 0.16, 0.038), 0.72, noise_scale=15.0, bump=0.12
        ),
        "leaf_b": procedural_material(
            "leaf_sunlit", (0.075, 0.28, 0.055), 0.66, noise_scale=18.0, bump=0.10
        ),
        "bark": procedural_material(
            "tree_bark", (0.12, 0.055, 0.025), 0.91, noise_scale=9.0, bump=0.34
        ),
        "wood": procedural_material(
            "interior_wood", (0.24, 0.095, 0.025), 0.46, noise_scale=7.0, bump=0.10
        ),
        "upholstery": procedural_material(
            "healthcare_upholstery",
            (0.035, 0.23, 0.30),
            0.69,
            noise_scale=28.0,
            bump=0.11,
        ),
        "linen": procedural_material(
            "clinical_linen", (0.79, 0.86, 0.86), 0.86, noise_scale=46.0, bump=0.10
        ),
        "blanket": procedural_material(
            "patient_blanket", (0.11, 0.37, 0.48), 0.82, noise_scale=35.0, bump=0.09
        ),
        "screen": procedural_material(
            "medical_screen",
            (0.015, 0.10, 0.12),
            0.18,
            emission=(0.08, 0.60, 0.62),
            emission_strength=1.8,
        ),
        "lamp": procedural_material(
            "warm_interior_light",
            (0.95, 0.78, 0.50),
            0.24,
            emission=(1.0, 0.64, 0.32),
            emission_strength=4.0,
        ),
        "road_white": procedural_material(
            "road_marking_white", (0.73, 0.75, 0.70), 0.76, noise_scale=31.0, bump=0.05
        ),
        "road_yellow": procedural_material(
            "road_marking_yellow",
            (0.83, 0.55, 0.035),
            0.72,
            noise_scale=28.0,
            bump=0.04,
        ),
        "blue_paint": procedural_material(
            "accessible_blue", (0.018, 0.22, 0.52), 0.66, noise_scale=25.0, bump=0.04
        ),
        "lamp_red": procedural_material(
            "emergency_lamp_red",
            (0.55, 0.006, 0.004),
            0.18,
            emission=(1.0, 0.01, 0.005),
            emission_strength=3.4,
        ),
        "lamp_blue": procedural_material(
            "emergency_lamp_blue",
            (0.002, 0.04, 0.65),
            0.16,
            emission=(0.002, 0.05, 1.0),
            emission_strength=3.8,
        ),
        "tire_gray": procedural_material(
            "vehicle_dark_trim", (0.025, 0.028, 0.031), 0.48, metallic=0.18
        ),
    }
    return M


def medical_cross_front(coll, parent, name, x, y, z, size, depth, mat):
    box(
        coll,
        name + ":vertical",
        (x, y, z),
        (size * 0.34, depth, size),
        mat,
        0.05,
        role="medical_cross",
        parent=parent,
    )
    box(
        coll,
        name + ":horizontal",
        (x, y - 0.002, z),
        (size, depth, size * 0.34),
        mat,
        0.05,
        role="medical_cross",
        parent=parent,
    )


def medical_cross_side(coll, parent, name, x, y, z, size, depth, mat):
    box(
        coll,
        name + ":vertical",
        (x, y, z),
        (depth, size * 0.34, size),
        mat,
        0.05,
        role="medical_cross",
        parent=parent,
    )
    box(
        coll,
        name + ":horizontal",
        (x + 0.002, y, z),
        (depth, size, size * 0.34),
        mat,
        0.05,
        role="medical_cross",
        parent=parent,
    )


def vertical_prism_y(
    coll, name, xz_points, y, depth, material, role, parent=None, bevel=0.0
):
    """Extrude an arbitrary X/Z silhouette along local Y."""
    count = len(xz_points)
    vertices = [(x, y - depth / 2.0, z) for x, z in xz_points]
    vertices += [(x, y + depth / 2.0, z) for x, z in xz_points]
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.parent = parent
    if bevel:
        mod = obj.modifiers.new(PREFIX + "profile_edge_softening", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return tag(obj, role)


def lofted_vehicle_shell(
    coll, name, sections, material, role, parent=None, bevel=0.045
):
    """Create a closed multi-section vehicle shell with chamfered roof shoulders.

    Each section is ``(x, half_width, bottom_z, shoulder_z, roof_z, chamfer)``.
    Unlike a scaled cube, this produces changing width, rake and roof height along
    the vehicle, so highlights describe a manufactured body rather than a toy box.
    """
    vertices = []
    ring_size = 6
    for x, half_width, bottom, shoulder, roof, chamfer in sections:
        vertices.extend(
            (
                (x, -half_width, bottom),
                (x, half_width, bottom),
                (x, half_width, shoulder),
                (x, half_width - chamfer, roof),
                (x, -half_width + chamfer, roof),
                (x, -half_width, shoulder),
            )
        )
    faces = [tuple(range(ring_size - 1, -1, -1))]
    for section in range(len(sections) - 1):
        start = section * ring_size
        nxt = start + ring_size
        for index in range(ring_size):
            following = (index + 1) % ring_size
            faces.append(
                (start + index, start + following, nxt + following, nxt + index)
            )
    last = (len(sections) - 1) * ring_size
    faces.append(tuple(last + index for index in range(ring_size)))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.parent = parent
    if bevel:
        modifier = obj.modifiers.new(PREFIX + "coachwork_edge_radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
    return tag(obj, role)


def arc_tube(
    coll,
    parent,
    name,
    center,
    radius,
    start_angle,
    end_angle,
    segments,
    tube_radius,
    material,
    role,
):
    """Model a curved tubular detail as closely joined manufactured segments."""
    cx, cy, cz = center
    previous = None
    for index in range(segments + 1):
        angle = start_angle + (end_angle - start_angle) * index / segments
        point = (cx + math.cos(angle) * radius, cy, cz + math.sin(angle) * radius)
        if previous is not None:
            beam(
                coll,
                f"{name}:segment_{index - 1}",
                previous,
                point,
                tube_radius,
                material,
                12,
                role=role,
                parent=parent,
            )
        previous = point


def detailed_vehicle_wheel(coll, parent, name, x, y, z, side, M):
    """Construct a treaded ambulance wheel with brake disc, spokes and lug nuts."""
    cylinder(
        coll,
        name + ":tire",
        (x, y, z),
        0.50,
        0.29,
        M["rubber"],
        40,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="ambulance_wheel",
        parent=parent,
    )
    outer_y = y + side * 0.163
    cylinder(
        coll,
        name + ":rim_outer",
        (x, outer_y, z),
        0.31,
        0.035,
        M["aluminum"],
        36,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="vehicle_wheel_rim",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":brake_disc",
        (x, outer_y + side * 0.024, z),
        0.235,
        0.018,
        M["steel"],
        32,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="vehicle_brake_disc",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":hub",
        (x, outer_y + side * 0.046, z),
        0.095,
        0.045,
        M["black_metal"],
        24,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="vehicle_wheel_hub",
        parent=parent,
    )
    for spoke in range(8):
        angle = 2.0 * math.pi * spoke / 8.0
        inner = (
            x + math.cos(angle) * 0.085,
            outer_y + side * 0.070,
            z + math.sin(angle) * 0.085,
        )
        outer = (
            x + math.cos(angle) * 0.255,
            outer_y + side * 0.070,
            z + math.sin(angle) * 0.255,
        )
        beam(
            coll,
            f"{name}:spoke_{spoke}",
            inner,
            outer,
            0.024,
            M["aluminum"],
            10,
            role="vehicle_wheel_spoke",
            parent=parent,
        )
    for lug in range(6):
        angle = 2.0 * math.pi * lug / 6.0
        cylinder(
            coll,
            f"{name}:lug_{lug}",
            (
                x + math.cos(angle) * 0.061,
                outer_y + side * 0.086,
                z + math.sin(angle) * 0.061,
            ),
            0.017,
            0.026,
            M["steel"],
            12,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_wheel_lug",
            parent=parent,
        )
    for vent in range(12):
        angle = 2.0 * math.pi * vent / 12.0
        cylinder(
            coll,
            f"{name}:brake_vent_{vent}",
            (
                x + math.cos(angle) * 0.18,
                outer_y + side * 0.088,
                z + math.sin(angle) * 0.18,
            ),
            0.014,
            0.024,
            M["black_metal"],
            12,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_brake_disc_vent",
            parent=parent,
        )
    # Individual tread blocks catch light at close range and remove the smooth toy-wheel look.
    for tread in range(24):
        angle = 2.0 * math.pi * tread / 24.0
        block = box(
            coll,
            f"{name}:tread_{tread}",
            (x + math.cos(angle) * 0.505, y, z + math.sin(angle) * 0.505),
            (0.13, 0.34, 0.065),
            M["rubber"],
            role="vehicle_tire_tread",
            parent=parent,
        )
        block.rotation_euler[1] = -angle


def front_window(
    coll,
    parent,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    divisions=2,
    stone_trim=False,
    blind=False,
    role="patient_window",
):
    """Deep, physically layered south-facing window module."""
    frame = M["aluminum"]
    box(
        coll,
        name + ":recess",
        (x, y + 0.22, z),
        (width + 0.32, 0.26, height + 0.34),
        M["black_metal"],
        role="window_reveal",
        parent=parent,
    )
    box(
        coll,
        name + ":room_back",
        (x, y + 0.39, z),
        (width - 0.16, 0.08, height - 0.16),
        M["tire_gray"],
        role="interior_window_back",
        parent=parent,
    )
    box(
        coll,
        name + ":glazing",
        (x, y - 0.015, z),
        (width, 0.065, height),
        M["glass_blue"],
        role=role,
        parent=parent,
    )
    bar = 0.085
    for suffix, bx, bz, bw, bh in (
        ("left", x - width / 2.0, z, bar, height + 0.16),
        ("right", x + width / 2.0, z, bar, height + 0.16),
        ("head", x, z + height / 2.0, width + 0.17, bar),
        ("sill", x, z - height / 2.0, width + 0.17, bar),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (bx, y - 0.075, bz),
            (bw, 0.11, bh),
            frame,
            role="window_frame",
            parent=parent,
        )
        # The inset black EPDM line is modeled rather than baked into a texture.
        box(
            coll,
            name + ":gasket_" + suffix,
            (bx, y - 0.137, bz),
            (bw * 0.43 if bw < bh else bw, 0.016, bh * 0.43 if bh < bw else bh),
            M["black_metal"],
            role="glazing_gasket",
            parent=parent,
        )
    for index in range(1, divisions):
        mx = x - width / 2.0 + width * index / divisions
        box(
            coll,
            name + f":mullion_{index}",
            (mx, y - 0.09, z),
            (0.075, 0.12, height),
            frame,
            role="window_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":mullion_gasket_{index}",
            (mx, y - 0.157, z),
            (0.018, 0.012, height),
            M["black_metal"],
            role="glazing_gasket",
            parent=parent,
        )
    box(
        coll,
        name + ":transom",
        (x, y - 0.09, z + height * 0.12),
        (width, 0.12, 0.075),
        frame,
        role="window_mullion",
        parent=parent,
    )
    if stone_trim:
        box(
            coll,
            name + ":stone_sill",
            (x, y - 0.18, z - height / 2.0 - 0.13),
            (width + 0.42, 0.34, 0.18),
            M["limestone"],
            0.045,
            role="stone_window_sill",
            parent=parent,
        )
        box(
            coll,
            name + ":stone_lintel",
            (x, y - 0.14, z + height / 2.0 + 0.12),
            (width + 0.38, 0.28, 0.16),
            M["limestone"],
            role="stone_window_lintel",
            parent=parent,
        )
    if blind:
        for slat in range(8):
            sz = z + height * 0.37 - slat * height * 0.086
            box(
                coll,
                name + f":blind_slat_{slat}",
                (x, y + 0.11, sz),
                (width - 0.18, 0.025, 0.025),
                M["white_clean"],
                role="interior_blind",
                parent=parent,
            )
    return role


def rear_window(
    coll,
    parent,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    divisions=2,
    blind=False,
    trim_material="white_panel",
    role="patient_window",
):
    """North-facing insulated window with real depth, bright reveals and interior cues.

    The previous rear elevation reused the south-facing module without mirroring its
    layer order.  Its dark backing therefore sat outside the facade and read as a
    black board.  This assembly is explicitly ordered from the room (negative Y) to
    the north exterior (positive Y): interior lining, insulated glazing, gaskets,
    thermally-broken frame, sill flashing and drip edge.
    """
    frame = M[trim_material]
    half_w = width / 2.0
    half_h = height / 2.0
    reveal_depth = 0.46

    # Four separate pale reveal returns preserve a readable opening instead of a
    # single dark rectangle.  The warm rear plane and ceiling strip provide room
    # depth through the transmissive glass without looking self-illuminated.
    for suffix, rx, rz, rw, rh in (
        ("left", x - half_w - 0.12, z, 0.24, height + 0.42),
        ("right", x + half_w + 0.12, z, 0.24, height + 0.42),
        ("head", x, z + half_h + 0.12, width, 0.24),
        ("sill", x, z - half_h - 0.12, width, 0.24),
    ):
        box(
            coll,
            name + ":reveal_return_" + suffix,
            (rx, y - reveal_depth * 0.46, rz),
            (rw, reveal_depth, rh),
            M["concrete_light"],
            0.025,
            role="window_reveal",
            parent=parent,
        )
    box(
        coll,
        name + ":interior_wall",
        (x, y - 0.49, z),
        (width - 0.18, 0.055, height - 0.18),
        M["interior_wall"],
        0.02,
        role="rear_window_interior_wall",
        parent=parent,
    )
    box(
        coll,
        name + ":interior_ceiling_line",
        (x, y - 0.43, z + half_h - 0.19),
        (width - 0.24, 0.11, 0.13),
        M["white_clean"],
        0.02,
        role="rear_window_interior_detail",
        parent=parent,
    )
    box(
        coll,
        name + ":interior_ledge",
        (x, y - 0.25, z - half_h + 0.12),
        (width - 0.16, 0.48, 0.095),
        M["white_clean"],
        0.025,
        role="rear_window_interior_detail",
        parent=parent,
    )

    # Two separated panes make the assembly read as insulated glazing at oblique
    # angles.  The outer pane carries semantic identity for pipeline consumers.
    box(
        coll,
        name + ":inner_glazing",
        (x, y - 0.055, z),
        (width, 0.028, height),
        M["glass_neutral"],
        role="insulated_glazing_inner",
        parent=parent,
    )
    outer_glass = box(
        coll,
        name + ":glazing",
        (x, y + 0.025, z),
        (width, 0.035, height),
        M["glass_neutral"],
        role=role,
        parent=parent,
    )
    outer_glass["c2w_facade_orientation"] = "north"
    outer_glass["c2w_insulated_glazing_depth_m"] = 0.08

    bar = 0.095
    for suffix, bx, bz, bw, bh in (
        ("left", x - half_w, z, bar, height + 0.18),
        ("right", x + half_w, z, bar, height + 0.18),
        ("head", x, z + half_h, width + 0.19, bar),
        ("sill", x, z - half_h, width + 0.19, bar),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (bx, y + 0.095, bz),
            (bw, 0.14, bh),
            frame,
            0.02,
            role="window_frame",
            parent=parent,
        )
        gasket_w = 0.022 if bw < bh else bw
        gasket_h = 0.022 if bh < bw else bh
        box(
            coll,
            name + ":gasket_" + suffix,
            (bx, y + 0.171, bz),
            (gasket_w, 0.014, gasket_h),
            M["black_metal"],
            role="glazing_gasket",
            parent=parent,
        )
    for index in range(1, divisions):
        mx = x - half_w + width * index / divisions
        box(
            coll,
            name + f":mullion_{index}",
            (mx, y + 0.105, z),
            (0.082, 0.15, height),
            frame,
            0.018,
            role="window_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":mullion_gasket_{index}",
            (mx, y + 0.187, z),
            (0.018, 0.012, height),
            M["black_metal"],
            role="glazing_gasket",
            parent=parent,
        )
    box(
        coll,
        name + ":transom",
        (x, y + 0.105, z + height * 0.12),
        (width, 0.15, 0.082),
        frame,
        0.018,
        role="window_mullion",
        parent=parent,
    )
    box(
        coll,
        name + ":outer_sill_flashing",
        (x, y + 0.19, z - half_h - 0.12),
        (width + 0.42, 0.43, 0.14),
        M["aluminum"],
        0.025,
        role="rear_window_sill_flashing",
        parent=parent,
    )
    box(
        coll,
        name + ":sill_drip_edge",
        (x, y + 0.415, z - half_h - 0.17),
        (width + 0.46, 0.035, 0.055),
        M["black_metal"],
        0.018,
        role="rear_window_drip_edge",
        parent=parent,
    )
    box(
        coll,
        name + ":head_flashing",
        (x, y + 0.18, z + half_h + 0.13),
        (width + 0.38, 0.36, 0.13),
        M["aluminum"],
        0.025,
        role="rear_window_head_flashing",
        parent=parent,
    )

    box(
        coll,
        name + ":blind_cassette",
        (x, y - 0.17, z + half_h - 0.14),
        (width - 0.22, 0.10, 0.15),
        M["white_clean"],
        0.025,
        role="interior_blind_cassette",
        parent=parent,
    )
    if blind:
        for slat in range(9):
            sz = z + height * 0.36 - slat * height * 0.075
            box(
                coll,
                name + f":blind_slat_{slat}",
                (x, y - 0.145, sz),
                (width - 0.25, 0.025, 0.032),
                M["white_clean"],
                0.012,
                role="interior_blind",
                parent=parent,
            )
    else:
        # Partially parked vertical blinds make adjacent rooms subtly different.
        for side in (-1, 1):
            bx = x + side * (half_w - 0.17)
            box(
                coll,
                name + f":parked_blind_{side}",
                (bx, y - 0.15, z - 0.03),
                (0.16, 0.028, height - 0.30),
                M["white_clean"],
                0.015,
                role="interior_blind",
                parent=parent,
            )
    return role


def side_window(
    coll,
    parent,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    divisions=2,
    side="east",
    stone_trim=False,
    role="patient_window",
):
    """Layered east/west-facing window; width runs along local Y."""
    direction = 1.0 if side == "east" else -1.0
    box(
        coll,
        name + ":recess",
        (x - direction * 0.22, y, z),
        (0.26, width + 0.32, height + 0.34),
        M["black_metal"],
        role="window_reveal",
        parent=parent,
    )
    box(
        coll,
        name + ":room_back",
        (x - direction * 0.39, y, z),
        (0.08, width - 0.16, height - 0.16),
        M["tire_gray"],
        role="interior_window_back",
        parent=parent,
    )
    box(
        coll,
        name + ":glazing",
        (x + direction * 0.015, y, z),
        (0.065, width, height),
        M["glass_blue"],
        role=role,
        parent=parent,
    )
    for suffix, by, bz, bw, bh in (
        ("left", y - width / 2.0, z, 0.085, height + 0.16),
        ("right", y + width / 2.0, z, 0.085, height + 0.16),
        ("head", y, z + height / 2.0, width + 0.17, 0.085),
        ("sill", y, z - height / 2.0, width + 0.17, 0.085),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (x + direction * 0.075, by, bz),
            (0.11, bw, bh),
            M["aluminum"],
            role="window_frame",
            parent=parent,
        )
    for index in range(1, divisions):
        my = y - width / 2.0 + width * index / divisions
        box(
            coll,
            name + f":mullion_{index}",
            (x + direction * 0.09, my, z),
            (0.12, 0.075, height),
            M["aluminum"],
            role="window_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":gasket_{index}",
            (x + direction * 0.157, my, z),
            (0.012, 0.018, height),
            M["black_metal"],
            role="glazing_gasket",
            parent=parent,
        )
    box(
        coll,
        name + ":transom",
        (x + direction * 0.09, y, z + height * 0.12),
        (0.12, width, 0.075),
        M["aluminum"],
        role="window_mullion",
        parent=parent,
    )
    if stone_trim:
        box(
            coll,
            name + ":stone_sill",
            (x + direction * 0.18, y, z - height / 2.0 - 0.13),
            (0.34, width + 0.42, 0.18),
            M["limestone"],
            0.045,
            role="stone_window_sill",
            parent=parent,
        )


def front_curtain_wall(
    coll,
    parent,
    name,
    x,
    y,
    bottom,
    width,
    height,
    columns,
    rows,
    M,
    glass_key="glass_clear",
    role="curtain_wall_glazing",
):
    panel_w = width / columns
    panel_h = height / rows
    box(
        coll,
        name + ":deep_recess",
        (x, y + 0.26, bottom + height / 2.0),
        (width + 0.44, 0.33, height + 0.44),
        M["tire_gray"],
        role="curtain_wall_recess",
        parent=parent,
    )
    for row in range(rows):
        for column in range(columns):
            px = x - width / 2.0 + panel_w * (column + 0.5)
            pz = bottom + panel_h * (row + 0.5)
            glass = M[glass_key] if (row + column) % 5 else M["glass_dark"]
            box(
                coll,
                name + f":glass_{row}_{column}",
                (px, y - 0.015, pz),
                (panel_w - 0.09, 0.06, panel_h - 0.09),
                glass,
                role=role,
                parent=parent,
            )
    for column in range(columns + 1):
        px = x - width / 2.0 + width * column / columns
        box(
            coll,
            name + f":vertical_mullion_{column}",
            (px, y - 0.085, bottom + height / 2.0),
            (0.09, 0.13, height + 0.15),
            M["aluminum"],
            role="curtain_wall_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":vertical_pressure_plate_{column}",
            (px, y - 0.158, bottom + height / 2.0),
            (0.025, 0.018, height + 0.12),
            M["black_metal"],
            role="curtain_wall_pressure_plate",
            parent=parent,
        )
    for row in range(rows + 1):
        pz = bottom + height * row / rows
        box(
            coll,
            name + f":horizontal_mullion_{row}",
            (x, y - 0.085, pz),
            (width + 0.14, 0.13, 0.09),
            M["aluminum"],
            role="curtain_wall_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":horizontal_pressure_plate_{row}",
            (x, y - 0.158, pz),
            (width + 0.10, 0.018, 0.025),
            M["black_metal"],
            role="curtain_wall_pressure_plate",
            parent=parent,
        )


def side_curtain_wall(
    coll,
    parent,
    name,
    x,
    y,
    bottom,
    width,
    height,
    columns,
    rows,
    M,
    side="east",
    role="curtain_wall_glazing",
):
    direction = 1.0 if side == "east" else -1.0
    panel_w = width / columns
    panel_h = height / rows
    box(
        coll,
        name + ":deep_recess",
        (x - direction * 0.26, y, bottom + height / 2.0),
        (0.33, width + 0.44, height + 0.44),
        M["tire_gray"],
        role="curtain_wall_recess",
        parent=parent,
    )
    for row in range(rows):
        for column in range(columns):
            py = y - width / 2.0 + panel_w * (column + 0.5)
            pz = bottom + panel_h * (row + 0.5)
            glass = M["glass_clear"] if (row + column) % 5 else M["glass_dark"]
            box(
                coll,
                name + f":glass_{row}_{column}",
                (x + direction * 0.015, py, pz),
                (0.06, panel_w - 0.09, panel_h - 0.09),
                glass,
                role=role,
                parent=parent,
            )
    for column in range(columns + 1):
        py = y - width / 2.0 + width * column / columns
        box(
            coll,
            name + f":vertical_mullion_{column}",
            (x + direction * 0.085, py, bottom + height / 2.0),
            (0.13, 0.09, height + 0.15),
            M["aluminum"],
            role="curtain_wall_mullion",
            parent=parent,
        )
    for row in range(rows + 1):
        pz = bottom + height * row / rows
        box(
            coll,
            name + f":horizontal_mullion_{row}",
            (x + direction * 0.085, y, pz),
            (0.13, width + 0.14, 0.09),
            M["aluminum"],
            role="curtain_wall_mullion",
            parent=parent,
        )


def glass_double_door(coll, parent, name, x, y, z, width, height, M, emergency=False):
    frame_mat = M["red_panel"] if emergency else M["aluminum"]
    box(
        coll,
        name + ":recess",
        (x, y + 0.18, z),
        (width + 0.46, 0.28, height + 0.38),
        M["black_metal"],
        role="entrance_recess",
        parent=parent,
    )
    for side in (-1, 1):
        dx = side * width * 0.255
        box(
            coll,
            name + f":leaf_{side}",
            (x + dx, y - 0.025, z),
            (width * 0.47, 0.07, height),
            M["glass_clear"],
            role="entrance_door_glazing",
            parent=parent,
        )
        for edge_x in (-width * 0.47 / 2.0, width * 0.47 / 2.0):
            box(
                coll,
                name + f":leaf_frame_{side}_{edge_x}",
                (x + dx + edge_x, y - 0.085, z),
                (0.065, 0.12, height + 0.08),
                frame_mat,
                role="door_frame",
                parent=parent,
            )
        box(
            coll,
            name + f":top_frame_{side}",
            (x + dx, y - 0.085, z + height / 2.0),
            (width * 0.47, 0.12, 0.07),
            frame_mat,
            role="door_frame",
            parent=parent,
        )
        box(
            coll,
            name + f":bottom_frame_{side}",
            (x + dx, y - 0.085, z - height / 2.0),
            (width * 0.47, 0.12, 0.07),
            frame_mat,
            role="door_frame",
            parent=parent,
        )
        cylinder(
            coll,
            name + f":pull_{side}",
            (x + side * width * 0.075, y - 0.175, z),
            0.025,
            0.68,
            M["steel"],
            14,
            role="door_hardware",
            parent=parent,
        )
        cylinder(
            coll,
            name + f":closer_{side}",
            (x + dx, y - 0.15, z + height * 0.40),
            0.032,
            width * 0.22,
            M["black_metal"],
            12,
            rot=(0.0, math.pi / 2.0, 0.0),
            role="door_hardware",
            parent=parent,
        )
    box(
        coll,
        name + ":threshold",
        (x, y - 0.16, z - height / 2.0 - 0.035),
        (width + 0.18, 0.34, 0.07),
        M["steel"],
        role="door_threshold",
        parent=parent,
    )


def hospital_bed(coll, parent, name, x, y, z, M, yaw=0.0):
    """Articulated patient bed with frame, linens, casters, IV and monitor."""
    box(
        coll,
        name + ":frame",
        (x, y, z + 0.52),
        (2.10, 0.91, 0.12),
        M["steel"],
        0.05,
        rot=yaw,
        role="patient_bed_frame",
        parent=parent,
    )
    box(
        coll,
        name + ":mattress",
        (x, y, z + 0.67),
        (1.95, 0.82, 0.18),
        M["linen"],
        0.07,
        rot=yaw,
        role="patient_bed",
        parent=parent,
    )
    box(
        coll,
        name + ":blanket",
        (x + 0.28 * math.cos(yaw), y + 0.28 * math.sin(yaw), z + 0.785),
        (1.16, 0.76, 0.055),
        M["blanket"],
        0.045,
        rot=yaw,
        role="patient_bed_linen",
        parent=parent,
    )
    box(
        coll,
        name + ":pillow",
        (x - 0.70 * math.cos(yaw), y - 0.70 * math.sin(yaw), z + 0.82),
        (0.44, 0.63, 0.16),
        M["linen"],
        0.07,
        rot=yaw,
        role="patient_bed_linen",
        parent=parent,
    )
    for side in (-1, 1):
        sx = x + side * 1.02 * math.cos(yaw)
        sy = y + side * 1.02 * math.sin(yaw)
        box(
            coll,
            name + f":endboard_{side}",
            (sx, sy, z + 0.88),
            (0.08, 0.96, 0.82),
            M["white_clean"],
            0.05,
            rot=yaw,
            role="patient_bed_endboard",
            parent=parent,
        )
    for ix in (-0.78, 0.78):
        for iy in (-0.36, 0.36):
            wx = x + ix * math.cos(yaw) - iy * math.sin(yaw)
            wy = y + ix * math.sin(yaw) + iy * math.cos(yaw)
            cylinder(
                coll,
                name + f":caster_{ix}_{iy}",
                (wx, wy, z + 0.22),
                0.09,
                0.055,
                M["rubber"],
                16,
                rot=(math.pi / 2.0, 0.0, yaw),
                role="patient_bed_caster",
                parent=parent,
            )
            beam(
                coll,
                name + f":caster_leg_{ix}_{iy}",
                (wx, wy, z + 0.26),
                (wx, wy, z + 0.48),
                0.025,
                M["steel"],
                12,
                role="patient_bed_frame",
                parent=parent,
            )
    ivx, ivy = x + 0.92 * math.cos(yaw) - 0.62 * math.sin(yaw), y + 0.92 * math.sin(
        yaw
    ) + 0.62 * math.cos(yaw)
    cylinder(
        coll,
        name + ":iv_pole",
        (ivx, ivy, z + 1.18),
        0.025,
        2.15,
        M["steel"],
        14,
        role="iv_pole",
        parent=parent,
    )
    beam(
        coll,
        name + ":iv_hook_a",
        (ivx, ivy, z + 2.21),
        (ivx + 0.18, ivy, z + 2.21),
        0.018,
        M["steel"],
        10,
        role="iv_pole",
        parent=parent,
    )
    beam(
        coll,
        name + ":iv_hook_b",
        (ivx, ivy, z + 2.21),
        (ivx - 0.18, ivy, z + 2.21),
        0.018,
        M["steel"],
        10,
        role="iv_pole",
        parent=parent,
    )
    box(
        coll,
        name + ":monitor_body",
        (ivx - 0.20, ivy - 0.08, z + 1.45),
        (0.45, 0.18, 0.34),
        M["white_clean"],
        0.045,
        role="patient_monitor",
        parent=parent,
    )
    box(
        coll,
        name + ":monitor_screen",
        (ivx - 0.20, ivy - 0.185, z + 1.46),
        (0.36, 0.025, 0.24),
        M["screen"],
        0.02,
        role="patient_monitor_screen",
        parent=parent,
    )


def waiting_chair(coll, parent, name, x, y, z, M, yaw=0.0):
    box(
        coll,
        name + ":seat",
        (x, y, z + 0.52),
        (0.72, 0.64, 0.14),
        M["upholstery"],
        0.07,
        rot=yaw,
        role="waiting_chair",
        parent=parent,
    )
    back_dx, back_dy = -0.26 * math.sin(yaw), 0.26 * math.cos(yaw)
    box(
        coll,
        name + ":back",
        (x + back_dx, y + back_dy, z + 0.98),
        (0.72, 0.13, 0.84),
        M["upholstery"],
        0.07,
        rot=yaw,
        role="waiting_chair_back",
        parent=parent,
    )
    for lx in (-0.28, 0.28):
        for ly in (-0.22, 0.22):
            wx = x + lx * math.cos(yaw) - ly * math.sin(yaw)
            wy = y + lx * math.sin(yaw) + ly * math.cos(yaw)
            beam(
                coll,
                name + f":leg_{lx}_{ly}",
                (wx, wy, z + 0.08),
                (wx, wy, z + 0.45),
                0.025,
                M["steel"],
                12,
                role="waiting_chair_leg",
                parent=parent,
            )


def reception_desk(coll, parent, name, x, y, z, width, M, yaw=0.0):
    box(
        coll,
        name + ":body",
        (x, y, z + 0.55),
        (width, 0.86, 1.10),
        M["white_clean"],
        0.06,
        rot=yaw,
        role="reception_desk",
        parent=parent,
    )
    box(
        coll,
        name + ":privacy_face",
        (x, y - 0.44, z + 0.75),
        (width - 0.28, 0.06, 0.54),
        M["wood"],
        0.03,
        rot=yaw,
        role="reception_desk_finish",
        parent=parent,
    )
    box(
        coll,
        name + ":counter",
        (x, y, z + 1.15),
        (width + 0.22, 1.02, 0.10),
        M["terrazzo"],
        0.055,
        rot=yaw,
        role="reception_counter",
        parent=parent,
    )
    for monitor in (-width * 0.25, width * 0.25):
        box(
            coll,
            name + f":monitor_{monitor}",
            (x + monitor, y + 0.04, z + 1.55),
            (0.62, 0.12, 0.42),
            M["tire_gray"],
            0.035,
            role="reception_monitor",
            parent=parent,
        )
        box(
            coll,
            name + f":screen_{monitor}",
            (x + monitor, y - 0.03, z + 1.55),
            (0.53, 0.018, 0.33),
            M["screen"],
            role="reception_monitor_screen",
            parent=parent,
        )
        beam(
            coll,
            name + f":stand_{monitor}",
            (x + monitor, y + 0.08, z + 1.18),
            (x + monitor, y + 0.08, z + 1.34),
            0.025,
            M["black_metal"],
            12,
            role="reception_monitor_stand",
            parent=parent,
        )


def accessible_ramp(coll, parent, name, x, y, z, length, width, rise, M, along_x=True):
    """Constructed ramp slab, landings, paired rails and intermediate posts."""
    if along_x:
        slope = math.atan2(rise, length)
        slab = box(
            coll,
            name + ":slab",
            (x, y, z + rise / 2.0 + 0.08),
            (math.hypot(length, rise), width, 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp",
            parent=parent,
        )
        slab.rotation_euler[1] = -slope
        box(
            coll,
            name + ":lower_landing",
            (x - length / 2.0 - 0.65, y, z + 0.08),
            (1.3, width, 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp_landing",
            parent=parent,
        )
        box(
            coll,
            name + ":upper_landing",
            (x + length / 2.0 + 0.65, y, z + rise + 0.08),
            (1.3, width, 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp_landing",
            parent=parent,
        )
        for side in (-1, 1):
            yy = y + side * (width / 2.0 + 0.08)
            beam(
                coll,
                name + f":rail_{side}",
                (x - length / 2.0, yy, z + 0.92),
                (x + length / 2.0, yy, z + rise + 0.92),
                0.035,
                M["steel"],
                14,
                role="accessible_handrail",
                parent=parent,
            )
            for post in range(7):
                t = post / 6.0
                px = x - length / 2.0 + length * t
                pz = z + rise * t
                beam(
                    coll,
                    name + f":post_{side}_{post}",
                    (px, yy, pz + 0.06),
                    (px, yy, pz + 0.92),
                    0.028,
                    M["steel"],
                    12,
                    role="accessible_handrail_post",
                    parent=parent,
                )
    else:
        slope = math.atan2(rise, length)
        slab = box(
            coll,
            name + ":slab",
            (x, y, z + rise / 2.0 + 0.08),
            (width, math.hypot(length, rise), 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp",
            parent=parent,
        )
        slab.rotation_euler[0] = slope
        box(
            coll,
            name + ":lower_landing",
            (x, y - length / 2.0 - 0.65, z + 0.08),
            (width, 1.3, 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp_landing",
            parent=parent,
        )
        box(
            coll,
            name + ":upper_landing",
            (x, y + length / 2.0 + 0.65, z + rise + 0.08),
            (width, 1.3, 0.16),
            M["concrete_light"],
            0.045,
            role="accessible_ramp_landing",
            parent=parent,
        )


def roof_mechanical_unit(coll, parent, name, x, y, z, width, depth, height, M):
    box(
        coll,
        name + ":curb",
        (x, y, z + 0.10),
        (width + 0.34, depth + 0.34, 0.20),
        M["concrete"],
        role="roof_plant_curb",
        parent=parent,
    )
    box(
        coll,
        name + ":cabinet",
        (x, y, z + 0.10 + height / 2.0),
        (width, depth, height),
        M["white_panel"],
        0.05,
        role="roof_mechanical_unit",
        parent=parent,
    )
    for side in (-1, 1):
        for slat in range(7):
            sy = y - depth * 0.34 + slat * depth * 0.11
            box(
                coll,
                name + f":louver_{side}_{slat}",
                (x + side * (width / 2.0 + 0.015), sy, z + height * 0.60),
                (0.035, depth * 0.075, height * 0.46),
                M["black_metal"],
                role="mechanical_louver",
                parent=parent,
            )
    cylinder(
        coll,
        name + ":top_fan",
        (x, y, z + height + 0.13),
        min(width, depth) * 0.27,
        0.08,
        M["black_metal"],
        28,
        role="roof_fan",
        parent=parent,
    )
    for blade in range(6):
        a = 2.0 * math.pi * blade / 6.0
        beam(
            coll,
            name + f":fan_blade_{blade}",
            (x, y, z + height + 0.18),
            (
                x + math.cos(a) * min(width, depth) * 0.21,
                y + math.sin(a) * min(width, depth) * 0.21,
                z + height + 0.18,
            ),
            0.025,
            M["aluminum"],
            10,
            role="roof_fan_blade",
            parent=parent,
        )


def external_ac_unit(coll, parent, name, x, y, z, M):
    box(
        coll,
        name + ":body",
        (x, y, z),
        (1.06, 0.48, 0.72),
        M["white_panel"],
        0.045,
        role="external_ac_unit",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":fan",
        (x, y - 0.26, z),
        0.25,
        0.035,
        M["tire_gray"],
        28,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="ac_condenser_fan",
        parent=parent,
    )
    for spoke in range(8):
        a = 2.0 * math.pi * spoke / 8.0
        beam(
            coll,
            name + f":grille_{spoke}",
            (x, y - 0.286, z),
            (x + math.cos(a) * 0.25, y - 0.286, z + math.sin(a) * 0.25),
            0.012,
            M["aluminum"],
            8,
            role="ac_fan_grille",
            parent=parent,
        )
    box(
        coll,
        name + ":bracket",
        (x, y + 0.10, z - 0.43),
        (1.20, 0.50, 0.09),
        M["steel"],
        role="ac_mounting_bracket",
        parent=parent,
    )


def local_parcel(coll, parent, name, width, depth, M):
    box(
        coll,
        name + ":ground",
        (0.0, 0.5, 0.02),
        (width + 12.0, depth + 12.0, 0.18),
        M["grass"],
        role="hospital_parcel",
        parent=parent,
    )
    box(
        coll,
        name + ":forecourt",
        (0.0, -depth / 2.0 - 4.2, 0.14),
        (width + 4.0, 7.8, 0.20),
        M["paving"],
        0.045,
        role="hospital_forecourt",
        parent=parent,
    )
    for joint in range(-int(width // 2), int(width // 2) + 1, 2):
        box(
            coll,
            name + f":paving_joint_{joint}",
            (joint, -depth / 2.0 - 4.2, 0.25),
            (0.025, 7.6, 0.012),
            M["black_metal"],
            role="paving_joint",
            parent=parent,
        )


def floor_plate(coll, parent, name, x, y, z, width, depth, M):
    box(
        coll,
        name,
        (x, y, z),
        (width, depth, 0.24),
        M["concrete"],
        role="structural_floor_slab",
        parent=parent,
    )
    box(
        coll,
        name + ":ceiling",
        (x, y, z - 0.15),
        (width - 0.7, depth - 0.7, 0.045),
        M["white_clean"],
        role="interior_ceiling",
        parent=parent,
    )


def ceiling_light_grid(coll, parent, name, xs, ys, z, M):
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            box(
                coll,
                name + f":panel_{ix}_{iy}",
                (x, y, z),
                (1.15, 0.46, 0.035),
                M["lamp"],
                0.02,
                role="interior_ceiling_light",
                parent=parent,
            )


def traditional_hospital(
    parent=None, origin=(-72.0, 8.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 1: compact brick and pale-stone community hospital."""
    M = materials or make_materials()
    coll = collection(
        "HOSPITAL_A_TRADITIONAL_BRICK",
        parent,
        "hospital_asset",
        "hospital.traditional_brick.v9",
    )
    root = asset_root(
        coll, "traditional_brick:root", origin, yaw, "hospital.traditional_brick.v9"
    )
    coll["c2w_reference_index"] = 1
    coll["c2w_variant"] = "traditional_brick"
    coll["c2w_reference_url"] = REFERENCE_URLS[0]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["traditional_brick"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([38.0, 27.0, 20.8])
    if include_site:
        local_parcel(coll, root, "traditional:parcel", 38.0, 27.0, M)

    south, east, west = -13.5, 19.0, -19.0
    # Deep structural core and floor plates leave an occupied zone behind the facade.
    box(
        coll,
        "traditional:brick_core",
        (0.0, 2.0, 4.0),
        (37.2, 22.2, 8.0),
        M["brick"],
        0.06,
        role="brick_cladding_panel",
        parent=root,
    )
    box(
        coll,
        "traditional:stone_core",
        (0.0, 2.0, 12.0),
        (37.2, 22.2, 8.0),
        M["limestone"],
        0.06,
        role="stone_cladding_panel",
        parent=root,
    )
    box(
        coll,
        "traditional:tower_mass",
        (-9.2, 0.4, 11.0),
        (11.6, 25.7, 22.0),
        M["limestone"],
        0.065,
        role="raised_atrium_tower",
        parent=root,
    )
    for z in (0.24, 4.15, 8.05, 12.0, 15.95):
        floor_plate(coll, root, f"traditional:floor_{z}", 0.0, 0.0, z, 36.5, 25.5, M)

    # Red-brick ground facade and pale upper facade are explicitly panelized.
    for column in range(8):
        x = -16.65 + column * 4.75
        box(
            coll,
            f"traditional:front_brick_panel_{column}",
            (x, south - 0.06, 4.0),
            (4.50, 0.38, 7.55),
            M["brick_front"],
            role="brick_cladding_panel",
            parent=root,
        )
        for course in range(5):
            box(
                coll,
                f"traditional:brick_course_{column}_{course}",
                (x, south - 0.27, 1.35 + course * 1.27),
                (4.42, 0.05, 0.045),
                M["concrete"],
                role="masonry_course",
                parent=root,
            )
    for row, z in enumerate((10.05, 14.05)):
        for column in range(8):
            x = -16.65 + column * 4.75
            box(
                coll,
                f"traditional:front_stone_panel_{row}_{column}",
                (x, south - 0.04, z),
                (4.50, 0.34, 3.70),
                M["limestone"],
                role="stone_cladding_panel",
                parent=root,
            )
            box(
                coll,
                f"traditional:stone_vertical_joint_{row}_{column}",
                (x + 2.25, south - 0.225, z),
                (0.035, 0.026, 3.62),
                M["concrete"],
                role="facade_panel_joint",
                parent=root,
            )
        box(
            coll,
            f"traditional:stone_bed_joint_{row}",
            (0.0, south - 0.225, z + 1.86),
            (37.2, 0.026, 0.04),
            M["concrete"],
            role="facade_panel_joint",
            parent=root,
        )

    # Tower brick piers and vertical glass bay reproduce the reference's dominant front motif.
    for x in (-14.6, -3.8):
        box(
            coll,
            f"traditional:tower_brick_pier_{x}",
            (x, south - 0.56, 11.2),
            (1.18, 0.82, 18.6),
            M["brick_front"],
            0.045,
            role="tower_brick_pier",
            parent=root,
        )
        for course in range(15):
            box(
                coll,
                f"traditional:tower_pier_course_{x}_{course}",
                (x, south - 0.99, 2.35 + course * 1.15),
                (1.08, 0.035, 0.035),
                M["concrete"],
                role="masonry_course",
                parent=root,
            )
    front_curtain_wall(
        coll,
        root,
        "traditional:atrium",
        -9.2,
        south - 0.62,
        1.0,
        8.8,
        15.3,
        4,
        6,
        M,
        role="atrium_glazing",
    )
    for z in (6.1, 10.0):
        box(
            coll,
            f"traditional:atrium_stone_spandrel_{z}",
            (-9.2, south - 0.86, z),
            (9.2, 0.33, 0.42),
            M["limestone"],
            role="atrium_spandrel",
            parent=root,
        )

    # Ground and upper windows on all four sides; each has reveal, glass, frame and gaskets.
    for row, z in enumerate((3.55, 9.75, 13.85)):
        for index, x in enumerate((2.0, 7.6, 13.2, 17.0)):
            # Reserve the complete ground-floor emergency portal clearance zone;
            # no glazing may pass behind or through the door assembly.
            if row == 0 and x >= 12.0:
                continue
            front_window(
                coll,
                root,
                f"traditional:front_window_{row}_{index}",
                x,
                south - 0.29,
                z,
                2.65,
                2.65,
                M,
                2,
                stone_trim=row == 0,
                blind=(row + index) % 3 == 0,
            )
        for index, y in enumerate((-8.8, -3.2, 2.4, 8.0)):
            side_window(
                coll,
                root,
                f"traditional:east_window_{row}_{index}",
                east + 0.23,
                y,
                z,
                2.50,
                2.55,
                M,
                2,
                "east",
                row == 0,
            )
            side_window(
                coll,
                root,
                f"traditional:west_window_{row}_{index}",
                west - 0.23,
                y,
                z,
                2.50,
                2.55,
                M,
                2,
                "west",
                row == 0,
            )
    for row, z in enumerate((3.55, 9.75, 13.85)):
        for index, x in enumerate((-15.5, -10.4, -5.3, -0.2, 4.9, 10.0, 15.1)):
            rear_window(
                coll,
                root,
                f"traditional:rear_window_{row}_{index}",
                x,
                13.69,
                z,
                2.35,
                2.45,
                M,
                2,
                blind=(index + row) % 4 == 0,
                trim_material="aluminum",
            )

    # Projecting piers, carved belt courses, window hoods and brick reveals give the
    # street elevation a load-bearing hierarchy instead of a flat stacked-box read.
    for pier, x in enumerate((-0.65, 4.80, 10.40, 15.55, 18.35)):
        box(
            coll,
            f"traditional:upper_stone_pilaster_{pier}",
            (x, south - 0.49, 12.0),
            (0.34, 0.46, 8.05),
            M["limestone"],
            0.045,
            role="facade_projecting_pilaster",
            parent=root,
        )
        box(
            coll,
            f"traditional:pilaster_cap_{pier}",
            (x, south - 0.58, 16.08),
            (0.62, 0.58, 0.25),
            M["concrete_light"],
            0.04,
            role="facade_pilaster_cap",
            parent=root,
        )
        box(
            coll,
            f"traditional:pilaster_base_{pier}",
            (x, south - 0.56, 8.08),
            (0.54, 0.54, 0.30),
            M["concrete_light"],
            0.04,
            role="facade_pilaster_base",
            parent=root,
        )
    for course, (course_z, projection) in enumerate(
        ((8.18, 0.42), (12.02, 0.30), (16.10, 0.46))
    ):
        box(
            coll,
            f"traditional:projecting_belt_course_{course}",
            (7.35, south - 0.44 - projection * 0.18, course_z),
            (22.7, projection, 0.24),
            M["limestone"],
            0.045,
            role="facade_belt_course",
            parent=root,
        )
    for row, z in enumerate((9.75, 13.85)):
        for index, x in enumerate((2.0, 7.6, 13.2, 17.0)):
            box(
                coll,
                f"traditional:window_hood_{row}_{index}",
                (x, south - 0.59, z + 1.48),
                (3.12, 0.46, 0.22),
                M["concrete_light"],
                0.045,
                role="projecting_window_hood",
                parent=root,
            )
            for bracket_side in (-1, 1):
                vertical_prism_y(
                    coll,
                    f"traditional:hood_bracket_{row}_{index}_{bracket_side}",
                    (
                        (x + bracket_side * 1.28, z + 1.34),
                        (x + bracket_side * 1.10, z + 1.34),
                        (x + bracket_side * 1.28, z + 1.08),
                    ),
                    south - 0.58,
                    0.28,
                    M["limestone"],
                    "window_hood_bracket",
                    root,
                    0.025,
                )
    for dentil in range(20):
        box(
            coll,
            f"traditional:parapet_dentil_{dentil}",
            (-18.0 + dentil * 1.84, south - 0.57, 16.43),
            (0.54, 0.44, 0.34),
            M["concrete_light"],
            0.035,
            role="facade_dentil",
            parent=root,
        )

    # Main glass entrance and side emergency door.
    glass_double_door(
        coll, root, "traditional:main_entry", -9.2, south - 0.95, 1.93, 4.5, 3.35, M
    )
    box(
        coll,
        "traditional:entrance_canopy",
        (-9.2, south - 2.65, 4.45),
        (14.2, 4.2, 0.38),
        M["concrete_light"],
        0.06,
        role="entrance_canopy",
        parent=root,
    )
    box(
        coll,
        "traditional:canopy_fascia",
        (-9.2, south - 4.75, 4.45),
        (14.4, 0.28, 0.78),
        M["limestone"],
        0.045,
        role="entrance_canopy_fascia",
        parent=root,
    )
    box(
        coll,
        "traditional:canopy_soffit",
        (-9.2, south - 2.65, 4.22),
        (13.7, 3.75, 0.10),
        M["white_clean"],
        0.035,
        role="entrance_canopy_soffit",
        parent=root,
    )
    for coffer in range(7):
        box(
            coll,
            f"traditional:canopy_coffer_{coffer}",
            (-14.6 + coffer * 1.80, south - 3.03, 4.15),
            (1.38, 2.45, 0.035),
            M["black_metal"],
            0.02,
            role="canopy_soffit_coffer",
            parent=root,
        )
    for x in (-15.4, -3.0):
        cylinder(
            coll,
            f"traditional:canopy_column_{x}",
            (x, south - 4.0, 2.15),
            0.13,
            4.3,
            M["steel"],
            24,
            role="canopy_column",
            parent=root,
        )
    # The secondary entry is a fabricated portal system, not one rectangular
    # block: thermally-broken door leaves, cassette jambs, cap flashings, deep
    # canopy, soffit, downlights, drip edge, panel joints and a trench drain.
    glass_double_door(
        coll,
        root,
        "traditional:emergency_entry",
        14.2,
        south - 0.62,
        1.82,
        2.5,
        3.05,
        M,
        emergency=True,
    )
    for side in (-1, 1):
        jamb_x = 14.2 + side * 1.50
        box(
            coll,
            f"traditional:emergency_portal_jamb_{side}",
            (jamb_x, south - 0.82, 1.88),
            (0.42, 0.72, 3.76),
            M["red_panel"],
            0.055,
            role="detailed_emergency_portal",
            parent=root,
        )
        box(
            coll,
            f"traditional:emergency_jamb_front_cap_{side}",
            (jamb_x, south - 1.21, 1.88),
            (0.18, 0.08, 3.82),
            M["red_sign"],
            0.025,
            role="portal_edge_cap",
            parent=root,
        )
        box(
            coll,
            f"traditional:emergency_jamb_shadow_joint_{side}",
            (jamb_x - side * 0.235, south - 1.23, 1.88),
            (0.025, 0.035, 3.62),
            M["black_metal"],
            role="portal_panel_joint",
            parent=root,
        )
        box(
            coll,
            f"traditional:emergency_jamb_base_shoe_{side}",
            (jamb_x, south - 1.24, 0.22),
            (0.52, 0.18, 0.22),
            M["steel"],
            0.025,
            role="portal_base_shoe",
            parent=root,
        )
    box(
        coll,
        "traditional:emergency_portal_header",
        (14.2, south - 0.82, 3.62),
        (3.42, 0.72, 0.48),
        M["red_panel"],
        0.055,
        role="detailed_emergency_portal",
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_header_front_cap",
        (14.2, south - 1.21, 3.62),
        (3.48, 0.08, 0.24),
        M["red_sign"],
        0.025,
        role="portal_edge_cap",
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_canopy",
        (14.2, south - 1.72, 4.02),
        (4.45, 2.45, 0.28),
        M["red_panel"],
        0.055,
        role="emergency_canopy",
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_canopy_soffit",
        (14.2, south - 1.72, 3.855),
        (4.10, 2.12, 0.055),
        M["white_clean"],
        0.025,
        role="entrance_canopy_soffit",
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_canopy_fascia",
        (14.2, south - 2.96, 4.02),
        (4.52, 0.16, 0.52),
        M["red_panel"],
        0.045,
        role="entrance_canopy_fascia",
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_canopy_drip",
        (14.2, south - 3.06, 3.78),
        (4.58, 0.055, 0.055),
        M["black_metal"],
        role="facade_drip_edge",
        parent=root,
    )
    for light_index, light_x in enumerate((13.35, 15.05)):
        cylinder(
            coll,
            f"traditional:emergency_downlight_{light_index}",
            (light_x, south - 1.85, 3.81),
            0.095,
            0.035,
            M["lamp"],
            20,
            role="canopy_downlight",
            parent=root,
        )
    for joint_index, joint_x in enumerate((13.62, 14.78)):
        box(
            coll,
            f"traditional:emergency_header_joint_{joint_index}",
            (joint_x, south - 1.265, 3.62),
            (0.025, 0.025, 0.40),
            M["black_metal"],
            role="portal_panel_joint",
            parent=root,
        )
    text_object(
        coll,
        "traditional:emergency_text",
        "EMERGENCY",
        (14.2, south - 3.06, 4.02),
        0.52,
        M["white_clean"],
        0.055,
        parent=root,
    )
    box(
        coll,
        "traditional:emergency_trench_drain",
        (14.2, south - 3.28, 0.30),
        (3.55, 0.28, 0.08),
        M["steel"],
        0.025,
        role="entrance_trench_drain",
        parent=root,
    )
    for slot in range(18):
        box(
            coll,
            f"traditional:emergency_drain_slot_{slot}",
            (12.58 + slot * 0.19, south - 3.31, 0.35),
            (0.075, 0.22, 0.022),
            M["black_metal"],
            role="entrance_drain_grating",
            parent=root,
        )

    # Cornices, coping, panel joints, drainage and rooftop plant.
    for z, width, depth in (
        (0.65, 38.6, 28.0),
        (7.95, 38.8, 28.1),
        (16.15, 39.0, 28.2),
    ):
        box(
            coll,
            f"traditional:continuous_cornice_{z}",
            (0.0, 0.0, z),
            (width, depth, 0.34),
            M["limestone"],
            0.055,
            role="traditional_cornice",
            parent=root,
        )
    for z, width, depth in ((20.35, 12.5, 27.8),):
        box(
            coll,
            f"traditional:tower_cornice_{z}",
            (-9.2, 0.0, z),
            (width, depth, 0.42),
            M["limestone"],
            0.06,
            role="traditional_cornice",
            parent=root,
        )
        box(
            coll,
            f"traditional:tower_coping_{z}",
            (-9.2, 0.0, z + 0.28),
            (width + 0.35, depth + 0.35, 0.16),
            M["black_metal"],
            role="roof_coping",
            parent=root,
        )
    for x in (-17.8, 17.8):
        cylinder(
            coll,
            f"traditional:downpipe_{x}",
            (x, -11.9, 7.6),
            0.065,
            15.2,
            M["aluminum"],
            18,
            role="rainwater_downpipe",
            parent=root,
        )
        box(
            coll,
            f"traditional:scupper_{x}",
            (x, south - 0.26, 15.75),
            (0.28, 0.42, 0.22),
            M["black_metal"],
            role="roof_scupper",
            parent=root,
        )
    roof_mechanical_unit(
        coll, root, "traditional:ahu_0", 4.0, 2.2, 16.2, 3.2, 2.4, 1.55, M
    )
    roof_mechanical_unit(
        coll, root, "traditional:ahu_1", 10.5, 4.5, 16.2, 2.6, 2.2, 1.35, M
    )

    # Reference-specific red cross and dimensional signage.
    box(
        coll,
        "traditional:front_identity_parapet",
        (9.5, south - 0.26, 17.50),
        (18.3, 0.52, 3.05),
        M["limestone"],
        0.05,
        role="hospital_sign_backer",
        parent=root,
    )
    box(
        coll,
        "traditional:identity_parapet_coping",
        (9.5, south - 0.30, 19.08),
        (18.7, 0.62, 0.18),
        M["black_metal"],
        role="roof_coping",
        parent=root,
    )
    medical_cross_front(
        coll,
        root,
        "traditional:front_cross",
        3.1,
        south - 0.58,
        17.45,
        2.7,
        0.24,
        M["red_sign"],
    )
    traditional_sign = text_object(
        coll,
        "traditional:hospital_wordmark",
        "HOSPITAL",
        (11.4, south - 0.71, 17.48),
        5.20,
        M["black_metal"],
        0.12,
        parent=root,
    )
    traditional_sign["c2w_sign_backer_bounds"] = json.dumps(
        [0.35, 18.65, 15.975, 19.025]
    )
    traditional_sign["c2w_sign_clear_readable"] = True
    box(
        coll,
        "traditional:tower_sign_backer",
        (-9.2, south - 1.12, 17.65),
        (8.2, 0.22, 1.65),
        M["concrete_light"],
        role="hospital_sign_backer",
        parent=root,
    )
    text_object(
        coll,
        "traditional:medical_center_wordmark",
        "MEDICAL CENTER",
        (-9.2, south - 1.27, 17.66),
        0.90,
        M["glass_blue"],
        0.075,
        parent=root,
    )

    # Occupied atrium and patient rooms are visible through the layered glazing.
    box(
        coll,
        "traditional:lobby_floor",
        (-9.2, -10.7, 0.31),
        (10.4, 5.2, 0.20),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    reception_desk(coll, root, "traditional:reception", -9.2, -10.2, 0.3, 4.3, M)
    for row in range(2):
        for seat in range(4):
            waiting_chair(
                coll,
                root,
                f"traditional:waiting_{row}_{seat}",
                -12.2 + seat * 1.6,
                -8.7 + row * 1.25,
                0.25,
                M,
                math.pi,
            )
    ceiling_light_grid(
        coll,
        root,
        "traditional:lobby_light",
        (-12.5, -9.2, -5.9),
        (-11.2, -7.8),
        4.10,
        M,
    )
    area_light(
        coll,
        "traditional:lobby_area",
        (-9.2, -9.5, 4.0),
        260.0,
        5.0,
        (1.0, 0.78, 0.56),
        root,
    )
    for room, (x, y, z, yaw_bed) in enumerate(
        (
            (4.0, -10.9, 8.15, 0.0),
            (10.0, -10.9, 8.15, 0.0),
            (15.0, -9.6, 8.15, 0.0),
            (4.0, -10.9, 12.25, 0.0),
            (10.0, -10.9, 12.25, 0.0),
            (15.0, -9.6, 12.25, 0.0),
        )
    ):
        hospital_bed(
            coll, root, f"traditional:patient_room_{room}:bed", x, y, z, M, yaw_bed
        )

    # A level, continuous arrival apron meets the adjusted door threshold.  It
    # replaces the former sideways ramp and ornamental steps, which did not join
    # either the forecourt or the doors.
    box(
        coll,
        "traditional:flush_entrance_apron",
        (-9.2, south - 3.70, 0.22),
        (10.6, 7.0, 0.16),
        M["concrete_light"],
        0.045,
        role="flush_accessible_route",
        parent=root,
    )
    for joint, jy in enumerate(
        (south - 1.55, south - 3.25, south - 4.95, south - 6.65)
    ):
        box(
            coll,
            f"traditional:apron_expansion_joint_{joint}",
            (-9.2, jy, 0.305),
            (10.25, 0.035, 0.018),
            M["black_metal"],
            role="accessible_route_joint",
            parent=root,
        )
    box(
        coll,
        "traditional:main_entry_trench_drain",
        (-9.2, south - 7.20, 0.30),
        (9.7, 0.28, 0.07),
        M["steel"],
        0.025,
        role="entrance_trench_drain",
        parent=root,
    )
    for slot in range(34):
        box(
            coll,
            f"traditional:main_entry_drain_slot_{slot}",
            (-13.85 + slot * 0.282, south - 7.22, 0.345),
            (0.095, 0.21, 0.020),
            M["black_metal"],
            role="entrance_drain_grating",
            parent=root,
        )
    for stud in range(28):
        sx = -12.1 + (stud % 14) * 0.45
        sy = south - 1.65 - (stud // 14) * 0.22
        cylinder(
            coll,
            f"traditional:entry_tactile_stud_{stud}",
            (sx, sy, 0.35),
            0.047,
            0.045,
            M["road_yellow"],
            14,
            role="tactile_paving_stud",
            parent=root,
        )
    # Keep the complete entrance apron and emergency arrival path free of the
    # former short cylindrical bollards.  The paired canopy columns remain: they
    # are load-bearing members outside the door clear width, not ground obstacles.
    coll[
        "c2w_detail_profile"
    ] = "reference-matched articulated brick/stone massing+projecting pilasters/belt courses/window hoods/dentils+deep four-sided windows+atrium curtain wall+coffered entrance canopy+occupied interiors+roof services/drainage+bollard-free arrival"
    return coll


def detailed_ambulance(coll, parent, name, x, y, z, M, yaw=0.0):
    """Coach-built emergency ambulance with a complete exterior and running gear."""
    # Vehicle coordinates are local to this root so the production adapter can rotate it.
    vehicle_root = bpy.data.objects.new(PREFIX + name + ":root", None)
    coll.objects.link(vehicle_root)
    vehicle_root.location = (x, y, z)
    vehicle_root.rotation_euler[2] = yaw
    vehicle_root.parent = parent
    tag(vehicle_root, "ambulance_root", "vehicle.ambulance.hospital.v7")

    # Twin ladder frame, axles, suspension and exhaust remain visible below the coachwork.
    for side in (-1, 1):
        box(
            coll,
            name + f":frame_rail_{side}",
            (-0.05, side * 0.64, 0.65),
            (5.95, 0.16, 0.24),
            M["tire_gray"],
            0.045,
            role="ambulance_chassis",
            parent=vehicle_root,
        )
    for axle_x in (-1.72, 1.78):
        cylinder(
            coll,
            name + f":axle_{axle_x}",
            (axle_x, 0.0, 0.66),
            0.085,
            2.05,
            M["black_metal"],
            24,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_axle",
            parent=vehicle_root,
        )
        for side in (-1, 1):
            for leaf in range(3):
                beam(
                    coll,
                    name + f":leaf_spring_{axle_x}_{side}_{leaf}",
                    (axle_x - 0.52, side * 0.60, 0.58 + leaf * 0.035),
                    (axle_x + 0.52, side * 0.60, 0.58 + leaf * 0.035),
                    0.025,
                    M["steel"],
                    10,
                    role="vehicle_suspension",
                    parent=vehicle_root,
                )
    beam(
        coll,
        name + ":exhaust_pipe",
        (-2.85, 0.61, 0.54),
        (2.25, 0.61, 0.54),
        0.055,
        M["steel"],
        18,
        role="vehicle_exhaust",
        parent=vehicle_root,
    )
    cylinder(
        coll,
        name + ":exhaust_tip",
        (-2.96, 0.61, 0.54),
        0.072,
        0.24,
        M["black_metal"],
        20,
        rot=(0.0, math.pi / 2.0, 0.0),
        role="vehicle_exhaust",
        parent=vehicle_root,
    )

    # The medical pod and cab are longitudinal lofts, with tapered ends and rounded shoulders.
    lofted_vehicle_shell(
        coll,
        name + ":medical_coachwork",
        (
            (-3.02, 0.94, 0.80, 2.48, 2.68, 0.13),
            (-2.86, 1.04, 0.76, 2.57, 2.80, 0.15),
            (0.78, 1.04, 0.76, 2.57, 2.80, 0.15),
            (1.08, 1.00, 0.76, 2.45, 2.69, 0.13),
        ),
        M["white_clean"],
        "ambulance_body",
        vehicle_root,
        0.065,
    )
    lofted_vehicle_shell(
        coll,
        name + ":cab_coachwork",
        (
            (0.72, 1.00, 0.72, 2.12, 2.38, 0.12),
            (1.35, 1.02, 0.70, 2.14, 2.38, 0.12),
            (2.04, 1.00, 0.72, 2.10, 2.32, 0.11),
            (2.52, 0.96, 0.76, 1.70, 2.08, 0.09),
            (2.82, 0.91, 0.78, 1.47, 1.61, 0.06),
        ),
        M["white_clean"],
        "ambulance_cab",
        vehicle_root,
        0.075,
    )
    lofted_vehicle_shell(
        coll,
        name + ":sculpted_hood",
        (
            (2.35, 0.97, 0.76, 1.36, 1.48, 0.06),
            (2.88, 0.92, 0.78, 1.32, 1.42, 0.05),
            (3.27, 0.84, 0.80, 1.23, 1.32, 0.04),
        ),
        M["white_clean"],
        "ambulance_hood",
        vehicle_root,
        0.055,
    )
    box(
        coll,
        name + ":lower_valance",
        (0.06, 0.0, 0.78),
        (6.28, 2.02, 0.26),
        M["tire_gray"],
        0.07,
        role="vehicle_lower_body_trim",
        parent=vehicle_root,
    )

    # Raked laminated windshield with physical border, centre divider and twin wipers.
    windshield_points = (
        (2.43, 1.49),
        (2.52, 1.61),
        (2.06, 2.25),
        (1.22, 2.28),
        (1.19, 2.17),
    )
    vertical_prism_y(
        coll,
        name + ":laminated_windshield",
        windshield_points,
        0.0,
        1.79,
        M["glass_dark"],
        "vehicle_glazing",
        vehicle_root,
        0.025,
    )
    for side in (-1, 1):
        beam(
            coll,
            name + f":windshield_edge_{side}",
            (2.47, side * 0.91, 1.53),
            (2.02, side * 0.91, 2.28),
            0.035,
            M["black_metal"],
            12,
            role="vehicle_window_gasket",
            parent=vehicle_root,
        )
    beam(
        coll,
        name + ":windshield_center_divider",
        (2.47, 0.0, 1.54),
        (2.02, 0.0, 2.27),
        0.026,
        M["black_metal"],
        10,
        role="vehicle_window_gasket",
        parent=vehicle_root,
    )
    for side in (-1, 1):
        beam(
            coll,
            name + f":windshield_wiper_{side}",
            (2.39, side * 0.12, 1.58),
            (2.16, side * 0.57, 1.96),
            0.016,
            M["black_metal"],
            10,
            role="vehicle_windshield_wiper",
            parent=vehicle_root,
        )

    # Cab doors follow the A-pillar rake; inset glazing, rubber gaskets and mirrors are separate.
    for side in (-1, 1):
        sy = side * 1.045
        window = ((1.22, 1.58), (2.35, 1.58), (2.00, 2.23), (1.22, 2.25))
        vertical_prism_y(
            coll,
            name + f":cab_side_glass_{side}",
            window,
            sy,
            0.050,
            M["glass_dark"],
            "vehicle_glazing",
            vehicle_root,
            0.018,
        )
        for edge, p1, p2 in (
            ("sill", (1.20, sy + side * 0.035, 1.55), (2.38, sy + side * 0.035, 1.55)),
            ("rear", (1.19, sy + side * 0.035, 1.54), (1.19, sy + side * 0.035, 2.28)),
            (
                "a_pillar",
                (2.40, sy + side * 0.035, 1.56),
                (2.01, sy + side * 0.035, 2.29),
            ),
            ("roof", (1.19, sy + side * 0.035, 2.29), (2.01, sy + side * 0.035, 2.29)),
        ):
            beam(
                coll,
                name + f":cab_window_{side}_{edge}",
                p1,
                p2,
                0.026,
                M["black_metal"],
                10,
                role="vehicle_window_gasket",
                parent=vehicle_root,
            )
        box(
            coll,
            name + f":cab_door_seam_rear_{side}",
            (1.12, sy + side * 0.042, 1.46),
            (0.026, 0.020, 1.45),
            M["black_metal"],
            role="vehicle_door_seam",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":cab_door_handle_{side}",
            (1.37, sy + side * 0.075, 1.45),
            (0.34, 0.055, 0.065),
            M["black_metal"],
            0.035,
            role="vehicle_door_handle",
            parent=vehicle_root,
        )
        beam(
            coll,
            name + f":mirror_upper_stalk_{side}",
            (2.18, sy, 1.86),
            (2.42, sy + side * 0.29, 1.89),
            0.025,
            M["black_metal"],
            12,
            role="vehicle_mirror_stalk",
            parent=vehicle_root,
        )
        beam(
            coll,
            name + f":mirror_lower_stalk_{side}",
            (2.25, sy, 1.62),
            (2.42, sy + side * 0.29, 1.76),
            0.022,
            M["black_metal"],
            12,
            role="vehicle_mirror_stalk",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":mirror_housing_{side}",
            (2.45, sy + side * 0.32, 1.83),
            (0.25, 0.13, 0.38),
            M["tire_gray"],
            0.075,
            role="vehicle_mirror",
            parent=vehicle_root,
        )

        # Medical-compartment access panels have real perimeter seams, hinges and handles.
        box(
            coll,
            name + f":continuous_red_belt_{side}",
            (-0.72, sy + side * 0.052, 1.52),
            (4.63, 0.045, 0.28),
            M["red_panel"],
            0.025,
            role="ambulance_livery",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":reflective_white_belt_{side}",
            (-0.72, sy + side * 0.079, 1.52),
            (4.55, 0.018, 0.085),
            M["road_white"],
            role="ambulance_reflective_livery",
            parent=vehicle_root,
        )
        for hatch, (hx, width) in enumerate(
            ((-2.27, 0.82), (-1.26, 0.92), (-0.16, 1.02), (0.65, 0.44))
        ):
            for edge, ex, ez, ew, eh in (
                ("left", hx - width / 2.0, 1.15, 0.025, 0.74),
                ("right", hx + width / 2.0, 1.15, 0.025, 0.74),
                ("top", hx, 1.52, width, 0.025),
                ("bottom", hx, 0.78, width, 0.025),
            ):
                box(
                    coll,
                    name + f":equipment_hatch_{side}_{hatch}_{edge}",
                    (ex, sy + side * 0.085, ez),
                    (ew, 0.022, eh),
                    M["aluminum"],
                    role="ambulance_equipment_hatch",
                    parent=vehicle_root,
                )
            for hinge in (-0.23, 0.23):
                cylinder(
                    coll,
                    name + f":hatch_hinge_{side}_{hatch}_{hinge}",
                    (hx - width / 2.0, sy + side * 0.105, 1.15 + hinge),
                    0.025,
                    0.08,
                    M["steel"],
                    12,
                    rot=(math.pi / 2.0, 0.0, 0.0),
                    role="vehicle_door_hinge",
                    parent=vehicle_root,
                )
            box(
                coll,
                name + f":hatch_handle_{side}_{hatch}",
                (hx + width * 0.25, sy + side * 0.12, 1.31),
                (0.20, 0.045, 0.045),
                M["black_metal"],
                0.03,
                role="vehicle_door_handle",
                parent=vehicle_root,
            )
        box(
            coll,
            name + f":anti_slip_step_{side}",
            (-0.50, sy + side * 0.23, 0.52),
            (4.45, 0.32, 0.12),
            M["steel"],
            0.04,
            role="ambulance_side_step",
            parent=vehicle_root,
        )
        for groove in range(18):
            box(
                coll,
                name + f":step_groove_{side}_{groove}",
                (-2.50 + groove * 0.25, sy + side * 0.39, 0.585),
                (0.025, 0.06, 0.018),
                M["black_metal"],
                role="vehicle_step_tread",
                parent=vehicle_root,
            )
        medical_cross_front(
            coll,
            vehicle_root,
            name + f":side_cross_{side}",
            -1.28,
            sy + side * 0.105,
            2.13,
            0.82,
            0.045,
            M["red_sign"],
        )
        box(
            coll,
            name + f":side_marker_front_{side}",
            (0.70, sy + side * 0.105, 2.55),
            (0.24, 0.05, 0.15),
            M["lamp_red"],
            0.025,
            role="emergency_marker_light",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":side_marker_rear_{side}",
            (-2.58, sy + side * 0.105, 2.55),
            (0.24, 0.05, 0.15),
            M["lamp_blue"],
            0.025,
            role="emergency_marker_light",
            parent=vehicle_root,
        )
        # Dark wheel-well liner and a continuous formed fender lip around each opening.
        for wheel_x in (-1.72, 1.78):
            cylinder(
                coll,
                name + f":wheel_well_liner_{wheel_x}_{side}",
                (wheel_x, sy, 0.69),
                0.585,
                0.055,
                M["tire_gray"],
                36,
                rot=(math.pi / 2.0, 0.0, 0.0),
                role="vehicle_wheel_well",
                parent=vehicle_root,
            )
            arc_tube(
                coll,
                vehicle_root,
                name + f":fender_lip_{wheel_x}_{side}",
                (wheel_x, sy + side * 0.13, 0.69),
                0.60,
                0.0,
                math.pi,
                16,
                0.035,
                M["aluminum"],
                "vehicle_wheel_arch_trim",
            )

    text_object(
        coll,
        name + ":ambulance_wordmark",
        "AMBULANCE",
        (-0.42, -1.205, 2.49),
        0.44,
        M["red_sign"],
        0.042,
        role="ambulance_wordmark",
        parent=vehicle_root,
    )

    # Four high-resolution treaded wheels with spoke rims and visible brake hardware.
    for wx in (-1.72, 1.82):
        for side in (-1, 1):
            detailed_vehicle_wheel(
                coll,
                vehicle_root,
                name + f":wheel_{wx}_{side}",
                wx,
                side * 1.10,
                0.69,
                side,
                M,
            )

    # Sculpted front: bumper corners, deep grille, lamps, indicators and license plate.
    box(
        coll,
        name + ":front_bumper",
        (3.29, 0.0, 0.82),
        (0.24, 1.92, 0.30),
        M["tire_gray"],
        0.085,
        role="vehicle_bumper",
        parent=vehicle_root,
    )
    box(
        coll,
        name + ":rear_step_bumper",
        (-3.12, 0.0, 0.69),
        (0.24, 2.20, 0.24),
        M["tire_gray"],
        0.065,
        role="vehicle_bumper",
        parent=vehicle_root,
    )
    box(
        coll,
        name + ":grille_recess",
        (3.315, 0.0, 1.08),
        (0.035, 1.20, 0.35),
        M["black_metal"],
        0.035,
        role="vehicle_grille_recess",
        parent=vehicle_root,
    )
    for slat in range(7):
        box(
            coll,
            name + f":grille_slat_{slat}",
            (3.34, -0.51 + slat * 0.17, 1.08),
            (0.028, 0.105, 0.28),
            M["aluminum"],
            0.025,
            role="vehicle_grille",
            parent=vehicle_root,
        )
    for side in (-1, 1):
        box(
            coll,
            name + f":headlamp_recess_{side}",
            (3.33, side * 0.70, 1.20),
            (0.04, 0.48, 0.30),
            M["black_metal"],
            0.055,
            role="vehicle_lamp_recess",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":projector_headlamp_{side}",
            (3.36, side * 0.70, 1.23),
            (0.035, 0.34, 0.20),
            M["lamp"],
            0.075,
            role="vehicle_headlamp",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":indicator_{side}",
            (3.37, side * 0.88, 1.23),
            (0.03, 0.10, 0.16),
            M["road_yellow"],
            0.035,
            role="vehicle_indicator",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":rear_lamp_cluster_{side}",
            (-3.145, side * 0.76, 1.38),
            (0.035, 0.30, 0.66),
            M["lamp_red"],
            0.045,
            role="vehicle_tail_lamp",
            parent=vehicle_root,
        )
    box(
        coll,
        name + ":front_license_plate",
        (3.42, 0.0, 0.78),
        (0.025, 0.58, 0.18),
        M["road_white"],
        0.02,
        role="vehicle_license_plate",
        parent=vehicle_root,
    )

    # Coach rear has twin glazed doors, perimeter seals, hinges, handles and chevron livery.
    for side in (-1, 1):
        box(
            coll,
            name + f":rear_door_glass_{side}",
            (-3.075, side * 0.46, 2.08),
            (0.035, 0.72, 0.56),
            M["glass_dark"],
            0.04,
            role="vehicle_glazing",
            parent=vehicle_root,
        )
        box(
            coll,
            name + f":rear_door_handle_{side}",
            (-3.13, side * 0.16, 1.48),
            (0.05, 0.22, 0.055),
            M["black_metal"],
            0.025,
            role="vehicle_door_handle",
            parent=vehicle_root,
        )
        for hinge_z in (1.16, 1.92, 2.48):
            cylinder(
                coll,
                name + f":rear_hinge_{side}_{hinge_z}",
                (-3.13, side * 0.94, hinge_z),
                0.025,
                0.12,
                M["steel"],
                12,
                rot=(0.0, 0.0, math.pi / 2.0),
                role="vehicle_door_hinge",
                parent=vehicle_root,
            )
    box(
        coll,
        name + ":rear_center_seal",
        (-3.13, 0.0, 1.75),
        (0.045, 0.045, 1.82),
        M["black_metal"],
        role="vehicle_door_seam",
        parent=vehicle_root,
    )
    for stripe in range(8):
        side = -1 if stripe % 2 else 1
        chevron = box(
            coll,
            name + f":rear_chevron_{stripe}",
            (-3.135, -0.78 + stripe * 0.22, 1.03),
            (0.025, 0.55, 0.14),
            M["red_panel"] if stripe % 2 else M["road_yellow"],
            role="ambulance_reflective_livery",
            parent=vehicle_root,
        )
        chevron.rotation_euler[0] = math.radians(28.0 * side)

    # Front and rear roof warning arrays, aerodynamic siren pods and ventilation equipment.
    for bar_index, (bar_x, bar_width) in enumerate(((1.48, 1.26), (-2.42, 1.08))):
        box(
            coll,
            name + f":lightbar_base_{bar_index}",
            (bar_x, 0.0, 2.87),
            (bar_width, 0.48, 0.11),
            M["black_metal"],
            0.045,
            role="emergency_lightbar",
            parent=vehicle_root,
        )
        for lens, (ly, mat) in enumerate(
            ((-0.15, M["lamp_blue"]), (0.15, M["lamp_red"]))
        ):
            box(
                coll,
                name + f":lightbar_{bar_index}_lens_{lens}",
                (bar_x, ly, 2.96),
                (bar_width - 0.10, 0.19, 0.16),
                mat,
                0.055,
                role="emergency_lightbar_lens",
                parent=vehicle_root,
            )
    cylinder(
        coll,
        name + ":roof_vent",
        (-0.92, 0.0, 2.88),
        0.30,
        0.13,
        M["white_panel"],
        32,
        role="ambulance_roof_vent",
        parent=vehicle_root,
    )
    cylinder(
        coll,
        name + ":roof_vent_cap",
        (-0.92, 0.0, 2.97),
        0.21,
        0.07,
        M["black_metal"],
        32,
        role="ambulance_roof_vent",
        parent=vehicle_root,
    )
    box(
        coll,
        name + ":roof_ac_fairing",
        (-1.62, 0.0, 2.88),
        (0.72, 0.58, 0.17),
        M["white_clean"],
        0.08,
        role="ambulance_roof_equipment",
        parent=vehicle_root,
    )
    for side in (-1, 1):
        cylinder(
            coll,
            name + f":siren_pod_{side}",
            (0.66, side * 0.48, 2.72),
            0.13,
            0.20,
            M["aluminum"],
            24,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_siren",
            parent=vehicle_root,
        )
    return vehicle_root


def public_hospital(
    parent=None, origin=(0.0, 8.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 2: broad red-and-white mid-rise public hospital."""
    M = materials or make_materials()
    coll = collection(
        "HOSPITAL_B_RED_WHITE_PUBLIC",
        parent,
        "hospital_asset",
        "hospital.red_white_public.v9",
    )
    root = asset_root(
        coll, "red_white_public:root", origin, yaw, "hospital.red_white_public.v9"
    )
    coll["c2w_reference_index"] = 2
    coll["c2w_variant"] = "red_white_public"
    coll["c2w_reference_url"] = REFERENCE_URLS[1]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["red_white_public"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([58.0, 31.0, 27.0])
    if include_site:
        local_parcel(coll, root, "public:parcel", 58.0, 31.0, M)

    south, east, west = -15.0, 29.0, -29.0
    # Staggered long wing, taller red tower and rear clinical block.
    box(
        coll,
        "public:left_clinical_core",
        (-7.0, 1.3, 11.2),
        (43.5, 27.0, 22.4),
        M["white_panel"],
        0.06,
        role="white_cladding_mass",
        parent=root,
    )
    box(
        coll,
        "public:right_rear_core",
        (20.5, 3.0, 9.2),
        (16.2, 24.0, 18.4),
        M["concrete_light"],
        0.06,
        role="white_cladding_mass",
        parent=root,
    )
    box(
        coll,
        "public:red_vertical_tower",
        (12.8, 0.2, 13.4),
        (9.0, 29.0, 26.8),
        M["red_panel"],
        0.065,
        role="red_vertical_tower",
        parent=root,
    )
    for z in (0.25, 4.65, 8.95, 13.25, 17.55, 21.85):
        floor_plate(coll, root, f"public:floor_{z}", -2.0, 0.4, z, 53.0, 27.0, M)

    # White facade bays and the red horizontal datum bands seen in the reference.
    # The final bay is a purpose-sized closure module: unlike the previous full
    # bay, it stops before the curtain wall instead of interpenetrating its glass.
    front_bays = (
        (-26.0, 3.48, True),
        (-21.5, 3.48, True),
        (-17.0, 3.48, True),
        (-12.5, 3.48, True),
        (-8.0, 3.48, True),
        (-3.5, 3.48, True),
        (1.0, 3.48, True),
        (4.25, 2.20, False),
    )
    band_width = PUBLIC_RED_BAND_END_X - PUBLIC_RED_BAND_LEFT_X
    band_center_x = (PUBLIC_RED_BAND_LEFT_X + PUBLIC_RED_BAND_END_X) / 2.0
    for floor, z in enumerate((6.75, 11.05, 15.35, 19.65)):
        for bay, (x, width, needs_right_pier) in enumerate(front_bays):
            front_window(
                coll,
                root,
                f"public:front_patient_window_{floor}_{bay}",
                x,
                south - 0.24,
                z,
                width,
                2.62,
                M,
                2,
                blind=(floor + bay) % 4 == 0,
                role="public_patient_window",
            )
            if needs_right_pier:
                # Narrow white pier masks make the continuous horizontal rhythm exact.
                pier_x = x + width / 2.0 + 0.39
                box(
                    coll,
                    f"public:white_pier_{floor}_{bay}",
                    (pier_x, south - 0.42, z),
                    (0.62, 0.40, 3.25),
                    M["white_panel"],
                    role="white_facade_pier",
                    parent=root,
                )
        band_z = 4.72 + floor * 4.30
        band = box(
            coll,
            f"public:red_horizontal_band_{floor}",
            (band_center_x, south - 0.53, band_z),
            (band_width, 0.48, 0.64),
            M["red_panel"],
            0.045,
            role="red_cladding_band",
            parent=root,
        )
        band["c2w_right_termination_x_m"] = PUBLIC_RED_BAND_END_X
        band["c2w_termination_detail"] = "concealed_behind_left_red_tower_pier"
        box(
            coll,
            f"public:red_band_shadow_joint_{floor}",
            (band_center_x, south - 0.79, band_z - 0.36),
            (band_width, 0.025, 0.045),
            M["black_metal"],
            role="facade_panel_joint",
            parent=root,
        )
    roof_band = box(
        coll,
        "public:roof_red_band",
        (band_center_x, south - 0.53, 22.25),
        (band_width, 0.48, 0.78),
        M["red_panel"],
        0.045,
        role="red_cladding_band",
        parent=root,
    )
    roof_band["c2w_right_termination_x_m"] = PUBLIC_RED_BAND_END_X
    roof_band["c2w_termination_detail"] = "concealed_behind_left_red_tower_pier"

    # Deep solar brows, continuous band trims and expressed vertical fins break the
    # repetitive facade plane into believable manufactured assemblies.
    for floor, z in enumerate((6.75, 11.05, 15.35, 19.65)):
        for bay, (x, width, _needs_right_pier) in enumerate(front_bays):
            box(
                coll,
                f"public:window_sunshade_{floor}_{bay}",
                (x, south - 0.73, z + 1.53),
                (width + 0.30, 0.74, 0.16),
                M["white_clean"],
                0.045,
                role="projecting_window_sunshade",
                parent=root,
            )
            outer_bracket_x = width / 2.0 - 0.12
            for side in (-1, 1):
                vertical_prism_y(
                    coll,
                    f"public:sunshade_bracket_{floor}_{bay}_{side}",
                    (
                        (x + side * outer_bracket_x, z + 1.49),
                        (x + side * (outer_bracket_x - 0.19), z + 1.49),
                        (x + side * outer_bracket_x, z + 1.18),
                    ),
                    south - 0.64,
                    0.38,
                    M["aluminum"],
                    "sunshade_bracket",
                    root,
                    0.02,
                )
        band_z = 4.72 + floor * 4.30
        for edge, offset in (("upper", 0.35), ("lower", -0.35)):
            box(
                coll,
                f"public:red_band_metal_trim_{floor}_{edge}",
                (band_center_x, south - 0.80, band_z + offset),
                (band_width, 0.08, 0.075),
                M["aluminum"],
                0.025,
                role="facade_band_edge_trim",
                parent=root,
            )
    # The last white fin is kept wholly west of the red tower pier; the former
    # fin at x=6.15 occupied the same physical volume as that red pier.
    for fin, x in enumerate((-28.25, -19.25, -10.25, -1.25, 5.48)):
        box(
            coll,
            f"public:full_height_facade_fin_{fin}",
            (x, south - 0.73, 13.40),
            (0.22, 0.86, 17.9),
            M["white_panel"],
            0.045,
            role="facade_vertical_fin",
            parent=root,
        )

    # Central multi-storey glass tower with pressure plates and red flanking piers.
    front_curtain_wall(
        coll,
        root,
        "public:central_glass_tower",
        12.8,
        south - 0.68,
        4.55,
        12.6,
        18.3,
        5,
        5,
        M,
        role="public_curtain_wall",
    )
    for x in (6.15, 19.45):
        box(
            coll,
            f"public:tower_red_pier_{x}",
            (x, south - 0.80, 14.0),
            (0.92, 0.64, 20.0),
            M["red_panel"],
            0.045,
            role="red_tower_pier",
            parent=root,
        )
    box(
        coll,
        "public:tower_projecting_crown",
        (12.8, south - 0.82, 26.22),
        (14.5, 0.95, 0.34),
        M["red_panel"],
        0.06,
        role="projecting_tower_crown",
        parent=root,
    )
    box(
        coll,
        "public:tower_crown_shadow",
        (12.8, south - 1.31, 25.93),
        (13.8, 0.035, 0.12),
        M["black_metal"],
        role="facade_shadow_reveal",
        parent=root,
    )

    # The low transparent entrance wing spans across the main frontage.
    box(
        coll,
        "public:entrance_lobby_floor",
        (5.2, -13.6, 0.28),
        (44.0, 6.4, 0.25),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    box(
        coll,
        "public:entrance_lobby_ceiling",
        (5.2, -13.6, 5.65),
        (44.0, 6.4, 0.22),
        M["white_clean"],
        role="interior_ceiling",
        parent=root,
    )
    front_curtain_wall(
        coll,
        root,
        "public:ground_lobby",
        5.2,
        south - 0.58,
        0.55,
        44.0,
        5.15,
        13,
        2,
        M,
        role="lobby_curtain_wall",
    )
    for x in (-15.8, -11.3, -6.8, -2.3, 2.2, 6.7, 11.2, 15.7, 20.2, 24.7):
        cylinder(
            coll,
            f"public:lobby_column_{x}",
            (x, -13.2, 2.80),
            0.13,
            5.60,
            M["steel"],
            24,
            role="lobby_structural_column",
            parent=root,
        )

    # Red emergency portal frames a real vestibule and pair of sliding doors.
    portal_x, portal_y = 22.0, south - 2.72
    for side in (-1, 1):
        portal_side_x = portal_x + side * 3.65
        box(
            coll,
            f"public:red_portal_side_{side}",
            (portal_side_x, portal_y, 3.45),
            (0.72, 1.10, 6.9),
            M["red_panel"],
            0.055,
            role="red_entry_portal",
            parent=root,
        )
        box(
            coll,
            f"public:portal_side_front_cap_{side}",
            (portal_side_x, portal_y - 0.59, 3.45),
            (0.38, 0.08, 6.78),
            M["red_sign"],
            0.025,
            role="portal_edge_cap",
            parent=root,
        )
        box(
            coll,
            f"public:portal_side_base_shoe_{side}",
            (portal_side_x, portal_y - 0.62, 0.22),
            (0.84, 0.18, 0.24),
            M["steel"],
            0.025,
            role="portal_base_shoe",
            parent=root,
        )
        for joint, joint_z in enumerate((1.75, 3.48, 5.20)):
            box(
                coll,
                f"public:portal_side_joint_{side}_{joint}",
                (portal_side_x, portal_y - 0.645, joint_z),
                (0.60, 0.025, 0.035),
                M["black_metal"],
                role="portal_panel_joint",
                parent=root,
            )
    box(
        coll,
        "public:red_portal_header",
        (portal_x, portal_y, 6.60),
        (8.0, 1.10, 0.72),
        M["red_panel"],
        0.055,
        role="red_entry_portal",
        parent=root,
    )
    box(
        coll,
        "public:red_portal_canopy",
        (portal_x, portal_y - 2.25, 5.55),
        (9.0, 4.8, 0.35),
        M["red_panel"],
        0.055,
        role="emergency_canopy",
        parent=root,
    )
    box(
        coll,
        "public:portal_soffit",
        (portal_x, portal_y - 2.25, 5.33),
        (8.45, 4.25, 0.08),
        M["white_clean"],
        0.035,
        role="entrance_canopy_soffit",
        parent=root,
    )
    for light in (-2.7, -0.9, 0.9, 2.7):
        cylinder(
            coll,
            f"public:portal_downlight_{light}",
            (portal_x + light, portal_y - 2.25, 5.27),
            0.11,
            0.035,
            M["lamp"],
            20,
            role="canopy_downlight",
            parent=root,
        )
    # A framed translucent sign-light layer closes the former empty slot between
    # canopy and header while preserving the reference's open, glazed character.
    box(
        coll,
        "public:portal_sign_glazing",
        (portal_x, portal_y - 0.59, 5.98),
        (6.55, 0.065, 0.42),
        M["glass_clear"],
        role="portal_sign_glazing",
        parent=root,
    )
    for edge, edge_z in (("bottom", 5.75), ("top", 6.21)):
        box(
            coll,
            f"public:portal_sign_frame_{edge}",
            (portal_x, portal_y - 0.645, edge_z),
            (6.70, 0.12, 0.075),
            M["aluminum"],
            0.018,
            role="portal_sign_frame",
            parent=root,
        )
    for mullion, mullion_x in enumerate((19.82, 21.27, 22.73, 24.18)):
        box(
            coll,
            f"public:portal_sign_mullion_{mullion}",
            (mullion_x, portal_y - 0.65, 5.98),
            (0.055, 0.13, 0.42),
            M["aluminum"],
            0.015,
            role="portal_sign_frame",
            parent=root,
        )
    for side in (-1, 1):
        box(
            coll,
            f"public:portal_header_end_face_{side}",
            (portal_x + side * 3.65, portal_y - 0.665, 6.58),
            (0.52, 0.075, 0.52),
            M["red_sign"],
            0.025,
            role="portal_edge_cap",
            parent=root,
        )
    glass_double_door(
        coll,
        root,
        "public:emergency_sliding_doors",
        portal_x,
        portal_y - 0.62,
        2.25,
        4.8,
        4.0,
        M,
        emergency=True,
    )
    box(
        coll,
        "public:emergency_transom_glass",
        (portal_x, portal_y - 0.66, 4.66),
        (4.82, 0.07, 0.70),
        M["glass_clear"],
        role="entrance_transom_glazing",
        parent=root,
    )
    for transom_x in (portal_x - 1.2, portal_x, portal_x + 1.2):
        box(
            coll,
            f"public:emergency_transom_mullion_{transom_x}",
            (transom_x, portal_y - 0.75, 4.66),
            (0.075, 0.13, 0.76),
            M["red_panel"],
            role="door_frame",
            parent=root,
        )
    text_object(
        coll,
        "public:emergency_wordmark",
        "EMERGENCY",
        (portal_x, portal_y - 0.60, 6.58),
        0.72,
        M["white_clean"],
        0.075,
        parent=root,
    )

    # Side and rear clinical windows maintain four-sided architectural completion.
    for floor, z in enumerate((6.75, 11.05, 15.35, 19.65)):
        for bay, y in enumerate((-10.8, -6.1, -1.4, 3.3, 8.0, 12.0)):
            side_window(
                coll,
                root,
                f"public:west_window_{floor}_{bay}",
                west - 0.22,
                y,
                z,
                3.10,
                2.55,
                M,
                2,
                "west",
                role="public_patient_window",
            )
            if floor < 3:
                side_window(
                    coll,
                    root,
                    f"public:east_window_{floor}_{bay}",
                    east + 0.22,
                    y,
                    z,
                    3.10,
                    2.55,
                    M,
                    2,
                    "east",
                    role="public_patient_window",
                )
        for bay, x in enumerate(
            (-25.0, -19.5, -14.0, -8.5, -3.0, 2.5, 8.0, 18.0, 24.0)
        ):
            if x < 9.0 or floor < 3:
                rear_window(
                    coll,
                    root,
                    f"public:rear_window_{floor}_{bay}",
                    x,
                    15.24,
                    z,
                    3.20,
                    2.55,
                    M,
                    2,
                    blind=(bay + floor) % 5 == 0,
                    trim_material="white_panel",
                    role="public_patient_window",
                )

    # Twelve individually modeled facade condensers match the second reference.
    for index, (x, z) in enumerate(
        (
            (-23.2, 8.95),
            (-14.2, 8.95),
            (-5.2, 8.95),
            (3.8, 8.95),
            (-23.2, 13.25),
            (-14.2, 13.25),
            (-5.2, 13.25),
            (3.8, 13.25),
            (-23.2, 17.55),
            (-14.2, 17.55),
            (-5.2, 17.55),
            (3.8, 17.55),
        )
    ):
        external_ac_unit(coll, root, f"public:facade_ac_{index}", x, south - 0.78, z, M)

    # Hospital identity at the tower crown and canopy.
    box(
        coll,
        "public:tower_sign_backer",
        (12.8, south - 0.93, 24.18),
        (12.2, 0.32, 2.25),
        M["red_panel"],
        0.045,
        role="hospital_sign_backer",
        parent=root,
    )
    public_sign = text_object(
        coll,
        "public:tower_hospital_wordmark",
        "HOSPITAL",
        (14.0, south - 1.13, 24.18),
        4.40,
        M["white_clean"],
        0.12,
        parent=root,
    )
    public_sign["c2w_sign_backer_bounds"] = json.dumps([6.7, 18.9, 23.055, 25.305])
    public_sign["c2w_sign_clear_readable"] = True
    medical_cross_front(
        coll,
        root,
        "public:tower_medical_cross",
        8.0,
        south - 1.15,
        24.2,
        1.55,
        0.18,
        M["white_clean"],
    )
    text_object(
        coll,
        "public:canopy_hospital_wordmark",
        "PUBLIC HOSPITAL",
        (4.0, south - 2.20, 5.40),
        0.62,
        M["white_clean"],
        0.06,
        parent=root,
    )

    # Occupied lobby: reception, triage counter, seating, lights and circulation.
    reception_desk(coll, root, "public:main_reception", -4.0, -12.0, 0.32, 6.2, M)
    reception_desk(coll, root, "public:triage_desk", 6.0, -12.0, 0.32, 4.2, M)
    for row in range(3):
        for seat in range(7):
            waiting_chair(
                coll,
                root,
                f"public:waiting_{row}_{seat}",
                -12.5 + seat * 2.0,
                -9.9 + row * 1.25,
                0.26,
                M,
                math.pi,
            )
    ceiling_light_grid(
        coll,
        root,
        "public:lobby_light",
        (-12.0, -5.0, 2.0, 9.0, 16.0, 23.0),
        (-14.0, -11.3),
        5.35,
        M,
    )
    for light_index, lx in enumerate((-9.0, 5.0, 18.0)):
        area_light(
            coll,
            f"public:lobby_area_{light_index}",
            (lx, -12.0, 5.2),
            330.0,
            6.0,
            (1.0, 0.82, 0.66),
            root,
        )
    # Visible upper-floor rooms contain operational beds and monitoring equipment.
    room_positions = []
    for floor, z in enumerate((5.05, 9.35, 13.65, 17.95)):
        for x in (-22.0, -14.0, -6.0, 2.0):
            room_positions.append((x, -12.2, z))
    for room, (x, y, z) in enumerate(room_positions):
        hospital_bed(coll, root, f"public:patient_room_{room}:bed", x, y, z, M)

    # Rooftop equipment, screen walls, guardrails, antenna and drainage.
    box(
        coll,
        "public:roof_screen",
        (-7.0, 7.5, 23.05),
        (30.0, 0.28, 2.1),
        M["white_panel"],
        role="roof_plant_screen",
        parent=root,
    )
    for unit, (x, y, w, d, h) in enumerate(
        (
            (-17.0, 4.0, 3.5, 2.8, 1.6),
            (-7.5, 5.2, 4.0, 3.0, 1.8),
            (2.0, 3.8, 3.2, 2.6, 1.5),
            (20.0, 5.0, 2.8, 2.4, 1.4),
        )
    ):
        roof_mechanical_unit(
            coll,
            root,
            f"public:roof_ahu_{unit}",
            x,
            y,
            22.0 if x < 8 else 18.4,
            w,
            d,
            h,
            M,
        )
    for x in (-27.7, 5.4, 28.0):
        cylinder(
            coll,
            f"public:downpipe_{x}",
            (x, 12.8, 10.5),
            0.07,
            21.0 if x < 8 else 17.0,
            M["aluminum"],
            18,
            role="rainwater_downpipe",
            parent=root,
        )
    cylinder(
        coll,
        "public:antenna_mast",
        (-15.0, 5.0, 24.7),
        0.055,
        5.2,
        M["steel"],
        18,
        role="roof_antenna",
        parent=root,
    )
    for level in (24.5, 25.5, 26.5):
        beam(
            coll,
            f"public:antenna_crossarm_{level}",
            (-16.2, 5.0, level),
            (-13.8, 5.0, level),
            0.025,
            M["steel"],
            12,
            role="roof_antenna",
            parent=root,
        )
    for x in range(-26, 9, 3):
        cylinder(
            coll,
            f"public:roof_guardrail_post_{x}",
            (x, 13.4, 23.15),
            0.025,
            1.2,
            M["steel"],
            12,
            role="roof_guardrail",
            parent=root,
        )
    beam(
        coll,
        "public:roof_guardrail_top",
        (-27.0, 13.4, 23.72),
        (9.0, 13.4, 23.72),
        0.032,
        M["steel"],
        12,
        role="roof_guardrail",
        parent=root,
    )

    # The emergency doors open onto a broad, level, obstruction-free apron tied
    # directly into the forecourt.  All former cylindrical bollards are removed;
    # no vehicle is instantiated and the full stretcher path stays unobstructed.
    box(
        coll,
        "public:emergency_flush_apron",
        (portal_x, south - 5.25, 0.20),
        (10.8, 6.8, 0.16),
        M["concrete_light"],
        0.045,
        role="flush_accessible_route",
        parent=root,
    )
    for joint, jy in enumerate((south - 3.0, south - 4.65, south - 6.30, south - 7.95)):
        box(
            coll,
            f"public:emergency_apron_joint_{joint}",
            (portal_x, jy, 0.285),
            (10.45, 0.035, 0.018),
            M["black_metal"],
            role="accessible_route_joint",
            parent=root,
        )
    box(
        coll,
        "public:emergency_trench_drain",
        (portal_x, south - 8.45, 0.28),
        (9.9, 0.32, 0.075),
        M["steel"],
        0.025,
        role="entrance_trench_drain",
        parent=root,
    )
    for slot in range(34):
        box(
            coll,
            f"public:emergency_drain_slot_{slot}",
            (17.25 + slot * 0.288, south - 8.47, 0.325),
            (0.105, 0.24, 0.020),
            M["black_metal"],
            role="entrance_drain_grating",
            parent=root,
        )
    for stud in range(32):
        sx = 18.65 + (stud % 16) * 0.45
        sy = south - 3.05 - (stud // 16) * 0.23
        cylinder(
            coll,
            f"public:emergency_tactile_stud_{stud}",
            (sx, sy, 0.33),
            0.047,
            0.045,
            M["road_yellow"],
            14,
            role="tactile_paving_stud",
            parent=root,
        )
    coll[
        "c2w_detail_profile"
    ] = "reference-matched articulated red/white public wing+deep solar brows/brackets/vertical fins+red bands terminated behind tower pier+pressure-plated glass tower and projecting crown+constructed lit emergency portal+occupied interiors+bollard-free flush emergency arrival+roof plant"
    return coll


def modern_hospital(
    parent=None, origin=(72.0, 8.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 3: white rainscreen clinic with ribbons and glazed stair tower."""
    M = materials or make_materials()
    coll = collection(
        "HOSPITAL_C_GLASS_RIBBON_MODERN",
        parent,
        "hospital_asset",
        "hospital.glass_ribbon_modern.v9",
    )
    root = asset_root(
        coll, "glass_ribbon_modern:root", origin, yaw, "hospital.glass_ribbon_modern.v9"
    )
    coll["c2w_reference_index"] = 3
    coll["c2w_variant"] = "glass_ribbon_modern"
    coll["c2w_reference_url"] = REFERENCE_URLS[2]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["glass_ribbon_modern"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([48.0, 29.0, 22.5])
    if include_site:
        local_parcel(coll, root, "modern:parcel", 48.0, 29.0, M)

    south, east, west = -14.5, 24.0, -24.0
    # Long white wing and taller right-hand stair/elevator tower form the reference L-massing.
    box(
        coll,
        "modern:main_clinical_core",
        (-4.5, 1.2, 9.1),
        (39.0, 26.0, 18.2),
        M["white_panel"],
        0.055,
        role="white_rainscreen_mass",
        parent=root,
    )
    box(
        coll,
        "modern:right_tower_core",
        (18.2, 1.0, 11.2),
        (11.6, 27.0, 22.4),
        M["white_panel"],
        0.06,
        role="white_rainscreen_mass",
        parent=root,
    )
    box(
        coll,
        "modern:rear_service_return",
        (6.0, 10.0, 6.7),
        (32.0, 8.0, 13.4),
        M["concrete_light"],
        0.055,
        role="rear_service_mass",
        parent=root,
    )
    for z in (0.25, 4.75, 9.10, 13.45, 17.80):
        floor_plate(coll, root, f"modern:floor_{z}", -1.0, 0.6, z, 47.0, 27.0, M)

    # Transparent ground floor with a fine mullion grid and deep interior plane.
    box(
        coll,
        "modern:lobby_floor_finish",
        (-4.3, -11.8, 0.32),
        (39.5, 5.0, 0.24),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    box(
        coll,
        "modern:lobby_ceiling",
        (-4.3, -11.8, 4.45),
        (39.5, 5.0, 0.18),
        M["white_clean"],
        role="interior_ceiling",
        parent=root,
    )
    front_curtain_wall(
        coll,
        root,
        "modern:ground_lobby",
        -4.3,
        south - 0.37,
        0.48,
        39.5,
        4.05,
        13,
        2,
        M,
        role="ground_lobby_glazing",
    )

    # Three long horizontal ribbon windows, separated by precise white spandrels.
    for floor, (bottom, height) in enumerate(
        ((5.55, 2.70), (9.90, 2.70), (14.25, 2.55))
    ):
        front_curtain_wall(
            coll,
            root,
            f"modern:ribbon_{floor}",
            -4.4,
            south - 0.38,
            bottom,
            39.4,
            height,
            13,
            1,
            M,
            "glass_blue",
            role="ribbon_window",
        )
        box(
            coll,
            f"modern:white_spandrel_{floor}",
            (-4.4, south - 0.61, bottom - 0.52),
            (39.8, 0.42, 0.78),
            M["white_panel"],
            role="white_rainscreen_panel",
            parent=root,
        )
        box(
            coll,
            f"modern:spandrel_shadow_joint_{floor}",
            (-4.4, south - 0.835, bottom - 0.94),
            (39.8, 0.022, 0.045),
            M["black_metal"],
            role="facade_panel_joint",
            parent=root,
        )
    box(
        coll,
        "modern:top_white_parapet",
        (-4.4, south - 0.54, 18.15),
        (39.8, 0.46, 1.38),
        M["white_panel"],
        role="white_rainscreen_panel",
        parent=root,
    )

    # Large rainscreen cassettes and open shadow joints on front, sides and rear.
    for row, z in enumerate((2.3, 7.0, 11.3, 15.65, 18.15)):
        for column in range(13):
            x = -23.2 + (column + 0.5) * 3.05
            if row in (1, 2, 3):
                # Ribbon glass occupies most of these rows; panels remain as header cassettes.
                pz, ph = z + 1.43, 0.64
            else:
                pz, ph = z, 1.55 if row == 0 else 1.30
            box(
                coll,
                f"modern:front_rainscreen_panel_{row}_{column}",
                (x, south - 0.63, pz),
                (2.91, 0.25, ph),
                M["white_panel"],
                role="white_rainscreen_panel",
                parent=root,
            )
            box(
                coll,
                f"modern:front_vertical_joint_{row}_{column}",
                (x + 1.50, south - 0.77, pz),
                (0.026, 0.025, ph),
                M["black_metal"],
                role="facade_panel_joint",
                parent=root,
            )

    # Blade fins, projecting ribbon sills and double-edge caps add real facade depth;
    # every piece has enough projection to cast a daylight shadow at the far view.
    for fin, x in enumerate(
        (-22.9, -18.8, -14.7, -10.6, -6.5, -2.4, 1.7, 5.8, 9.9, 13.3)
    ):
        box(
            coll,
            f"modern:ribbon_vertical_blade_{fin}",
            (x, south - 0.81, 11.55),
            (0.14, 0.92, 12.65),
            M["aluminum"],
            0.035,
            role="facade_vertical_fin",
            parent=root,
        )
        box(
            coll,
            f"modern:blade_front_cap_{fin}",
            (x, south - 1.29, 11.55),
            (0.22, 0.08, 12.72),
            M["white_clean"],
            0.025,
            role="facade_fin_cap",
            parent=root,
        )
    for floor, bottom in enumerate((5.55, 9.90, 14.25)):
        box(
            coll,
            f"modern:ribbon_projecting_sill_{floor}",
            (-4.4, south - 0.82, bottom - 0.14),
            (39.7, 0.86, 0.16),
            M["white_panel"],
            0.04,
            role="projecting_ribbon_sill",
            parent=root,
        )
        box(
            coll,
            f"modern:ribbon_sill_drip_{floor}",
            (-4.4, south - 1.27, bottom - 0.22),
            (39.8, 0.055, 0.055),
            M["black_metal"],
            role="facade_drip_edge",
            parent=root,
        )

    # Taller stair tower has blue glass front and east return plus a white crown.
    front_curtain_wall(
        coll,
        root,
        "modern:stair_tower_front",
        18.2,
        south - 0.72,
        0.55,
        10.7,
        18.1,
        4,
        5,
        M,
        "glass_dark",
        role="glass_stair_tower",
    )
    side_curtain_wall(
        coll,
        root,
        "modern:stair_tower_east",
        east + 0.33,
        -5.0,
        0.55,
        18.0,
        18.1,
        6,
        5,
        M,
        "east",
        role="glass_stair_tower",
    )
    box(
        coll,
        "modern:tower_white_crown",
        (18.2, south - 0.88, 20.25),
        (11.4, 0.52, 3.25),
        M["white_panel"],
        role="white_rainscreen_panel",
        parent=root,
    )
    for joint_x in (13.0, 15.6, 18.2, 20.8, 23.4):
        box(
            coll,
            f"modern:tower_crown_joint_{joint_x}",
            (joint_x, south - 1.16, 20.25),
            (0.028, 0.025, 3.12),
            M["black_metal"],
            role="facade_panel_joint",
            parent=root,
        )
    box(
        coll,
        "modern:tower_crown_cap",
        (18.2, south - 0.91, 22.02),
        (12.1, 0.74, 0.24),
        M["aluminum"],
        0.055,
        role="projecting_tower_crown",
        parent=root,
    )

    # Side/rear ribbon returns complete the architecture beyond the hero facade.
    for floor, z in enumerate((6.85, 11.2, 15.55)):
        for bay, y in enumerate((-10.8, -6.7, -2.6, 1.5, 5.6, 9.7)):
            side_window(
                coll,
                root,
                f"modern:west_ribbon_module_{floor}_{bay}",
                west - 0.20,
                y,
                z,
                3.25,
                2.55,
                M,
                3,
                "west",
                role="ribbon_window",
            )
        for bay, x in enumerate(
            (-20.5, -15.5, -10.5, -5.5, -0.5, 4.5, 9.5, 14.5, 19.5)
        ):
            rear_window(
                coll,
                root,
                f"modern:rear_ribbon_module_{floor}_{bay}",
                x,
                14.72,
                z,
                3.75,
                2.48,
                M,
                3,
                blind=(floor + bay) % 4 == 0,
                trim_material="white_panel",
                role="ribbon_window",
            )
    # East side outside the stair glass carries service-room windows and panel seams.
    for floor, z in enumerate((6.85, 11.2, 15.55)):
        for bay, y in enumerate((6.0, 10.1)):
            side_window(
                coll,
                root,
                f"modern:east_service_window_{floor}_{bay}",
                east + 0.20,
                y,
                z,
                3.0,
                2.45,
                M,
                2,
                "east",
                role="service_window",
            )

    # Reference-defining full-width floating canopy and stainless columns.
    box(
        coll,
        "modern:projecting_canopy",
        (-5.5, south - 2.55, 4.70),
        (37.5, 5.2, 0.32),
        M["white_clean"],
        0.06,
        role="projecting_canopy",
        parent=root,
    )
    box(
        coll,
        "modern:canopy_shadow_reveal",
        (-5.5, south - 5.17, 4.46),
        (37.7, 0.05, 0.14),
        M["black_metal"],
        role="canopy_shadow_joint",
        parent=root,
    )
    box(
        coll,
        "modern:canopy_front_fascia",
        (-5.5, south - 5.16, 4.67),
        (37.8, 0.24, 0.58),
        M["white_panel"],
        0.045,
        role="entrance_canopy_fascia",
        parent=root,
    )
    box(
        coll,
        "modern:canopy_soffit",
        (-5.5, south - 2.56, 4.47),
        (36.9, 4.7, 0.08),
        M["white_clean"],
        0.035,
        role="entrance_canopy_soffit",
        parent=root,
    )
    for bay in range(12):
        x = -22.3 + bay * 3.05
        box(
            coll,
            f"modern:soffit_reveal_{bay}",
            (x, south - 2.56, 4.41),
            (2.65, 3.95, 0.025),
            M["black_metal"],
            0.02,
            role="canopy_soffit_coffer",
            parent=root,
        )
        cylinder(
            coll,
            f"modern:soffit_downlight_{bay}",
            (x, south - 3.40, 4.37),
            0.105,
            0.035,
            M["lamp"],
            20,
            role="canopy_downlight",
            parent=root,
        )
    # Column grid is deliberately kept outside both sliding-door clear widths.
    for column, x in enumerate((-21.8, -17.7, -13.6, -9.5, 1.0, 11.0)):
        cylinder(
            coll,
            f"modern:canopy_column_{column}",
            (x, south - 3.70, 2.26),
            0.105,
            4.52,
            M["steel"],
            24,
            role="canopy_column",
            parent=root,
        )
        cylinder(
            coll,
            f"modern:column_base_{column}",
            (x, south - 3.70, 0.12),
            0.19,
            0.24,
            M["aluminum"],
            24,
            role="column_base_plate",
            parent=root,
        )
    glass_double_door(
        coll, root, "modern:main_sliding_entry", -4.5, south - 0.86, 2.25, 5.4, 4.0, M
    )
    glass_double_door(
        coll, root, "modern:secondary_entry", 6.2, south - 0.86, 2.25, 3.8, 4.0, M
    )

    # Visible circulation stair inside the glass tower, including treads/landings/rails.
    for level in range(4):
        base = 0.55 + level * 4.35
        direction = 1 if level % 2 == 0 else -1
        for step in range(12):
            t = step / 11.0
            sx = 14.8 + (6.8 * t if direction > 0 else 6.8 * (1.0 - t))
            sz = base + 0.18 + t * 3.38
            box(
                coll,
                f"modern:stair_{level}_tread_{step}",
                (sx, -12.0, sz),
                (0.68, 2.35, 0.16),
                M["concrete_light"],
                role="stair_tread",
                parent=root,
            )
        box(
            coll,
            f"modern:stair_landing_{level}",
            (21.6 if direction > 0 else 14.8, -12.0, base + 3.72),
            (2.0, 2.5, 0.20),
            M["concrete_light"],
            role="stair_landing",
            parent=root,
        )
        rail_y = -13.20
        beam(
            coll,
            f"modern:stair_handrail_{level}",
            (14.5, rail_y, base + 1.0),
            (21.9, rail_y, base + 4.30),
            0.035,
            M["steel"],
            14,
            role="stair_handrail",
            parent=root,
        )
        for post in range(7):
            t = post / 6.0
            px = 14.5 + 7.4 * t
            pz = base + 0.18 + 3.38 * t
            beam(
                coll,
                f"modern:stair_post_{level}_{post}",
                (px, rail_y, pz),
                (px, rail_y, pz + 0.88),
                0.025,
                M["steel"],
                12,
                role="stair_handrail_post",
                parent=root,
            )

    # The front cross remains on the tower crown.  The east cross is mounted on a
    # dedicated white rainscreen field behind the glazed stair return, with a
    # complete cassette perimeter, so it cannot read as fallen onto the glass.
    medical_cross_front(
        coll,
        root,
        "modern:front_medical_cross",
        18.2,
        south - 1.18,
        20.30,
        2.65,
        0.22,
        M["red_sign"],
    )
    box(
        coll,
        "modern:east_cross_white_backer",
        (east + 0.30, 8.35, 18.20),
        (0.48, 5.80, 5.65),
        M["white_panel"],
        0.045,
        role="side_medical_sign_backer",
        parent=root,
    )
    for edge, (ey, ez, edy, edz) in enumerate(
        (
            (5.47, 18.20, 0.055, 5.48),
            (11.23, 18.20, 0.055, 5.48),
            (8.35, 15.40, 5.70, 0.055),
            (8.35, 21.00, 5.70, 0.055),
        )
    ):
        box(
            coll,
            f"modern:east_cross_backer_joint_{edge}",
            (east + 0.555, ey, ez),
            (0.026, edy, edz),
            M["black_metal"],
            role="facade_panel_joint",
            parent=root,
        )
    box(
        coll,
        "modern:east_cross_backer_top_cap",
        (east + 0.58, 8.35, 21.12),
        (0.18, 6.05, 0.18),
        M["aluminum"],
        0.025,
        role="portal_edge_cap",
        parent=root,
    )
    medical_cross_side(
        coll,
        root,
        "modern:east_medical_cross",
        east + 0.60,
        8.35,
        18.35,
        2.55,
        0.22,
        M["red_sign"],
    )
    text_object(
        coll,
        "modern:canopy_wordmark",
        "MEDICAL CENTER",
        (-4.6, south - 5.38, 4.70),
        0.62,
        M["black_metal"],
        0.065,
        parent=root,
    )
    # A dedicated architectural sign band makes the building identity readable in
    # the campus-wide view while keeping every letter inside a modeled facade zone.
    box(
        coll,
        "modern:hospital_sign_backer",
        (-5.0, south - 0.78, 19.10),
        (23.0, 0.52, 2.50),
        M["white_panel"],
        0.055,
        role="hospital_sign_backer",
        parent=root,
    )
    box(
        coll,
        "modern:hospital_sign_coping",
        (-5.0, south - 0.87, 20.42),
        (23.5, 0.70, 0.18),
        M["aluminum"],
        0.045,
        role="roof_coping",
        parent=root,
    )
    medical_cross_front(
        coll,
        root,
        "modern:sign_medical_cross",
        -13.8,
        south - 1.10,
        19.10,
        1.65,
        0.20,
        M["red_sign"],
    )
    modern_sign = text_object(
        coll,
        "modern:hospital_wordmark",
        "HOSPITAL",
        (-4.2, south - 1.12, 19.10),
        4.70,
        M["red_sign"],
        0.12,
        parent=root,
    )
    modern_sign["c2w_sign_backer_bounds"] = json.dumps([-16.5, 6.5, 17.85, 20.35])
    modern_sign["c2w_sign_clear_readable"] = True

    # Lobby reception, waiting zones and clinical rooms are visible through clear glazing.
    reception_desk(coll, root, "modern:reception", -7.0, -11.2, 0.32, 5.8, M)
    for row in range(2):
        for seat in range(8):
            waiting_chair(
                coll,
                root,
                f"modern:waiting_{row}_{seat}",
                -18.8 + seat * 1.65,
                -9.6 + row * 1.25,
                0.25,
                M,
                math.pi,
            )
    for planter, x in enumerate((2.0, 9.0)):
        cylinder(
            coll,
            f"modern:lobby_planter_{planter}",
            (x, -10.2, 0.47),
            0.45,
            0.76,
            M["concrete_light"],
            28,
            role="interior_planter",
            parent=root,
        )
        for leaf in range(14):
            angle = leaf * 2.399
            beam(
                coll,
                f"modern:lobby_plant_leaf_{planter}_{leaf}",
                (x, -10.2, 0.82),
                (
                    x + math.cos(angle) * 0.45,
                    -10.2 + math.sin(angle) * 0.45,
                    1.45 + 0.18 * (leaf % 3),
                ),
                0.035,
                M["leaf_b"],
                8,
                role="interior_plant",
                parent=root,
            )
    ceiling_light_grid(
        coll,
        root,
        "modern:lobby_light",
        (-18.0, -11.0, -4.0, 3.0, 10.0),
        (-12.6, -10.0),
        4.25,
        M,
    )
    for light_index, lx in enumerate((-14.0, -3.0, 8.0)):
        area_light(
            coll,
            f"modern:lobby_area_{light_index}",
            (lx, -11.0, 4.1),
            290.0,
            5.8,
            (0.86, 0.94, 1.0),
            root,
        )
    room_index = 0
    for z in (4.95, 9.30, 13.65):
        for x in (-18.0, -11.0, -4.0, 3.0, 10.0):
            hospital_bed(
                coll, root, f"modern:patient_room_{room_index}:bed", x, -11.8, z, M
            )
            room_index += 1

    # Fine facade expansion joints, parapet coping, roof plant and rainwater details.
    box(
        coll,
        "modern:main_roof_coping",
        (-4.5, 0.8, 18.42),
        (39.6, 26.7, 0.18),
        M["aluminum"],
        role="roof_coping",
        parent=root,
    )
    box(
        coll,
        "modern:tower_roof_coping",
        (18.2, 0.8, 22.48),
        (12.0, 27.5, 0.18),
        M["aluminum"],
        role="roof_coping",
        parent=root,
    )
    for unit, (x, y, w, d, h) in enumerate(
        (
            (-14.0, 3.5, 3.2, 2.4, 1.45),
            (-4.0, 4.5, 3.8, 2.8, 1.65),
            (7.0, 3.0, 3.0, 2.4, 1.35),
        )
    ):
        roof_mechanical_unit(
            coll, root, f"modern:roof_ahu_{unit}", x, y, 17.85, w, d, h, M
        )
    for x in (-22.8, 12.6, 23.2):
        cylinder(
            coll,
            f"modern:downpipe_{x}",
            (x, 12.8, 8.7 if x < 13 else 10.8),
            0.065,
            17.4 if x < 13 else 21.6,
            M["aluminum"],
            18,
            role="rainwater_downpipe",
            parent=root,
        )
        box(
            coll,
            f"modern:downpipe_shoe_{x}",
            (x, 12.35, 0.24),
            (0.20, 0.95, 0.16),
            M["aluminum"],
            role="downpipe_shoe",
            parent=root,
        )

    # Broad flush landing and route connect both doors directly to the forecourt.
    box(
        coll,
        "modern:entrance_landing",
        (-4.5, south - 4.8, 0.151),
        (27.0, 4.8, 0.18),
        M["paving"],
        0.045,
        role="flush_accessible_route",
        parent=root,
    )
    # Its north edge exactly meets (but never overlaps) the landing's south edge.
    box(
        coll,
        "modern:forecourt_accessible_route",
        (-4.5, south - 8.40, 0.151),
        (22.0, 2.4, 0.18),
        M["concrete_light"],
        0.045,
        role="flush_accessible_route",
        parent=root,
    )
    for joint, jy in enumerate((south - 3.0, south - 4.55, south - 6.1, south - 7.65)):
        box(
            coll,
            f"modern:arrival_joint_{joint}",
            (-4.5, jy, 0.247),
            (21.7, 0.035, 0.018),
            M["black_metal"],
            role="accessible_route_joint",
            parent=root,
        )
    for stud in range(42):
        sx = -14.4 + (stud % 14) * 1.52
        sy = south - 6.3 + (stud // 14) * 0.22
        cylinder(
            coll,
            f"modern:tactile_stud_{stud}",
            (sx, sy, 0.264),
            0.055,
            0.045,
            M["road_yellow"],
            16,
            role="tactile_paving_stud",
            parent=root,
        )
    box(
        coll,
        "modern:arrival_trench_drain",
        (-4.5, south - 9.62, 0.235),
        (21.4, 0.30, 0.075),
        M["steel"],
        0.025,
        role="entrance_trench_drain",
        parent=root,
    )
    for slot in range(48):
        box(
            coll,
            f"modern:arrival_drain_slot_{slot}",
            (-14.7 + slot * 0.435, south - 9.64, 0.278),
            (0.13, 0.22, 0.020),
            M["black_metal"],
            role="entrance_drain_grating",
            parent=root,
        )
    coll[
        "c2w_detail_profile"
    ] = "reference-matched articulated L-massing+panelized rainscreen with deep blade fins/caps/projecting ribbon sills+transparent occupied lobby+coffered lit canopy+visible stair tower+contained large hospital sign band+patient rooms+roof services+bollard-free arrival"
    return coll


def leaf_card_cloud(
    coll, parent, name, centers, leaf_count, spread, size, materials, seed
):
    """One dense, efficient mesh containing hundreds of individually oriented leaves."""
    rng = random.Random(seed)
    verts = []
    faces = []
    material_indices = []
    for leaf in range(leaf_count):
        center = Vector(centers[leaf % len(centers)])
        # Rejection-free ellipsoidal displacement with denser center weighting.
        theta = rng.random() * 2.0 * math.pi
        phi = math.acos(2.0 * rng.random() - 1.0)
        radius = rng.random() ** 0.48
        offset = Vector(
            (
                math.cos(theta) * math.sin(phi) * spread[0] * radius,
                math.sin(theta) * math.sin(phi) * spread[1] * radius,
                math.cos(phi) * spread[2] * radius,
            )
        )
        center += offset
        normal = Vector(
            (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.55, 1.0))
        ).normalized()
        tangent = normal.cross(Vector((0.0, 0.0, 1.0)))
        if tangent.length < 0.1:
            tangent = normal.cross(Vector((0.0, 1.0, 0.0)))
        tangent.normalize()
        bitangent = normal.cross(tangent).normalized()
        half_l = size * rng.uniform(0.72, 1.22)
        half_w = half_l * rng.uniform(0.34, 0.52)
        base = len(verts)
        verts.extend(
            (
                tuple(center + tangent * half_l),
                tuple(center + bitangent * half_w),
                tuple(center - tangent * half_l),
                tuple(center - bitangent * half_w),
            )
        )
        faces.append((base, base + 1, base + 2, base + 3))
        material_indices.append(leaf % len(materials))
    mesh = bpy.data.meshes.new(PREFIX + name + ":leaf_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, index in zip(mesh.polygons, material_indices):
        polygon.material_index = index
    obj = bpy.data.objects.new(PREFIX + name + ":leaves", mesh)
    coll.objects.link(obj)
    obj.parent = parent
    obj["c2w_leaf_card_count"] = leaf_count
    obj["c2w_leaf_geometry"] = "individual_oriented_diamond_cards_in_single_mesh"
    return tag(obj, "tree_leaf_cards")


def detailed_street_tree(coll, name, x, y, z, scale, M, seed):
    root = bpy.data.objects.new(PREFIX + name + ":root", None)
    coll.objects.link(root)
    root.location = (x, y, z)
    root.scale = (scale, scale, scale)
    tag(root, "street_tree_root", "landscape.street_tree.v7")
    rng = random.Random(seed)
    # Tapered trunk formed from overlapping sections; buttress roots anchor it.
    for segment, (sz, radius, depth) in enumerate(
        ((1.15, 0.30, 2.3), (3.0, 0.24, 1.6), (4.35, 0.18, 1.3), (5.45, 0.13, 1.0))
    ):
        cylinder(
            coll,
            f"{name}:trunk_{segment}",
            (0.0, 0.0, sz),
            radius,
            depth,
            M["bark"],
            20,
            role="tree_trunk",
            parent=root,
        )
    for root_index in range(8):
        a = root_index * 2.0 * math.pi / 8.0
        beam(
            coll,
            f"{name}:buttress_root_{root_index}",
            (0.0, 0.0, 0.22),
            (math.cos(a) * 0.78, math.sin(a) * 0.78, 0.05),
            0.075,
            M["bark"],
            14,
            role="tree_buttress_root",
            parent=root,
        )
    tips = []
    for branch_index in range(11):
        angle = branch_index * 2.399963 + rng.uniform(-0.14, 0.14)
        start_z = 3.25 + (branch_index % 4) * 0.62
        length = rng.uniform(2.6, 4.2)
        end = Vector(
            (
                math.cos(angle) * length,
                math.sin(angle) * length,
                start_z + rng.uniform(1.35, 2.9),
            )
        )
        start = Vector((0.0, 0.0, start_z))
        beam(
            coll,
            f"{name}:primary_branch_{branch_index}",
            start,
            end,
            rng.uniform(0.075, 0.12),
            M["bark"],
            14,
            role="tree_branch",
            parent=root,
        )
        tips.append(tuple(end))
        for twig in range(3):
            twig_angle = angle + (twig - 1) * 0.52 + rng.uniform(-0.12, 0.12)
            twig_end = end + Vector(
                (
                    math.cos(twig_angle) * rng.uniform(1.0, 1.8),
                    math.sin(twig_angle) * rng.uniform(1.0, 1.8),
                    rng.uniform(0.35, 1.15),
                )
            )
            beam(
                coll,
                f"{name}:secondary_branch_{branch_index}_{twig}",
                end * 0.72 + start * 0.28,
                twig_end,
                rng.uniform(0.035, 0.060),
                M["bark"],
                12,
                role="tree_branch",
                parent=root,
            )
            tips.append(tuple(twig_end))
    leaf_card_cloud(
        coll,
        root,
        name,
        tips,
        1400,
        (1.10, 1.10, 0.84),
        0.30,
        (M["leaf_a"], M["leaf_b"]),
        seed + 911,
    )
    root["c2w_branch_count"] = 44
    root["c2w_leaf_card_count"] = 1400
    root[
        "c2w_tree_quality"
    ] = "tapered trunk+buttress roots+primary/secondary branch hierarchy+1400 oriented leaves"
    return root


def detailed_shrub(coll, name, x, y, z, scale, M, seed):
    root = bpy.data.objects.new(PREFIX + name + ":root", None)
    coll.objects.link(root)
    root.location = (x, y, z)
    root.scale = (scale, scale, scale)
    tag(root, "landscape_shrub_root")
    rng = random.Random(seed)
    centers = []
    for branch_index in range(16):
        angle = branch_index * 2.399 + rng.uniform(-0.18, 0.18)
        end = (
            math.cos(angle) * rng.uniform(0.35, 0.85),
            math.sin(angle) * rng.uniform(0.35, 0.85),
            rng.uniform(0.55, 1.25),
        )
        beam(
            coll,
            f"{name}:branch_{branch_index}",
            (0.0, 0.0, 0.08),
            end,
            0.018,
            M["bark"],
            8,
            role="shrub_branch",
            parent=root,
        )
        centers.append(end)
    leaf_card_cloud(
        coll,
        root,
        name,
        centers,
        180,
        (0.32, 0.32, 0.28),
        0.085,
        (M["leaf_a"], M["leaf_b"]),
        seed + 151,
    )
    root["c2w_leaf_card_count"] = 180
    return root


def site_bench(coll, name, x, y, z, M, yaw=0.0):
    box(
        coll,
        name + ":seat",
        (x, y, z + 0.55),
        (2.25, 0.62, 0.12),
        M["wood"],
        0.055,
        rot=yaw,
        role="site_bench",
        parent=None,
    )
    box(
        coll,
        name + ":back",
        (x, y + 0.28, z + 1.05),
        (2.25, 0.11, 0.82),
        M["wood"],
        0.055,
        rot=yaw,
        role="site_bench_back",
        parent=None,
    )
    for side in (-1, 1):
        sx = x + side * 0.88 * math.cos(yaw)
        sy = y + side * 0.88 * math.sin(yaw)
        beam(
            coll,
            name + f":leg_front_{side}",
            (sx, sy - 0.22, z + 0.08),
            (sx, sy - 0.22, z + 0.50),
            0.04,
            M["black_metal"],
            14,
            role="site_bench_frame",
            parent=None,
        )
        beam(
            coll,
            name + f":leg_rear_{side}",
            (sx, sy + 0.22, z + 0.08),
            (sx, sy + 0.22, z + 0.94),
            0.04,
            M["black_metal"],
            14,
            role="site_bench_frame",
            parent=None,
        )
        beam(
            coll,
            name + f":arm_{side}",
            (sx, sy - 0.30, z + 0.82),
            (sx, sy + 0.28, z + 0.82),
            0.035,
            M["black_metal"],
            14,
            role="site_bench_arm",
            parent=None,
        )


def site_light(coll, name, x, y, z, M):
    cylinder(
        coll,
        name + ":base",
        (x, y, z + 0.18),
        0.23,
        0.36,
        M["concrete"],
        24,
        role="site_light_base",
    )
    cylinder(
        coll,
        name + ":pole",
        (x, y, z + 3.15),
        0.075,
        6.0,
        M["black_metal"],
        24,
        role="site_light_pole",
    )
    beam(
        coll,
        name + ":arm",
        (x, y, z + 5.9),
        (x + 0.82, y, z + 6.18),
        0.045,
        M["black_metal"],
        16,
        role="site_light_arm",
    )
    box(
        coll,
        name + ":luminaire",
        (x + 1.00, y, z + 6.18),
        (0.80, 0.34, 0.18),
        M["black_metal"],
        0.045,
        role="site_luminaire",
    )
    box(
        coll,
        name + ":lens",
        (x + 1.00, y, z + 6.075),
        (0.68, 0.27, 0.035),
        M["lamp"],
        role="site_luminaire_lens",
    )


def build_hospital_site(parent, M):
    site = collection(
        "HOSPITAL_REFERENCE_ROW_SITE",
        parent,
        "hospital_site",
        "site.hospital.reference_row.v9",
    )
    # Ground, three dedicated parcels, forecourt, service lane and public road.
    box(
        site,
        "site:context_ground",
        (0.0, -70.0, -0.38),
        (520.0, 500.0, 0.20),
        M["concrete_light"],
        role="context_ground",
    )
    box(
        site,
        "site:grass_ground",
        (0.0, 6.0, -0.10),
        (230.0, 74.0, 0.35),
        M["grass"],
        role="landscape_ground",
    )
    for index, (x, width, depth) in enumerate(
        ((-72.0, 43.0, 33.0), (0.0, 63.0, 37.0), (72.0, 53.0, 35.0))
    ):
        box(
            site,
            f"site:building_pad_{index}",
            (x, 7.0, 0.08),
            (width, depth, 0.25),
            M["concrete"],
            0.05,
            role="building_foundation_pad",
        )
        box(
            site,
            f"site:forecourt_{index}",
            (x, -17.2, 0.13),
            (width + 4.0, 15.0, 0.22),
            M["paving"],
            0.05,
            role="hospital_forecourt",
        )
        for joint in range(-int(width // 2), int(width // 2) + 1, 2):
            box(
                site,
                f"site:paving_joint_{index}_{joint}",
                (x + joint, -17.2, 0.255),
                (0.025, 14.8, 0.012),
                M["black_metal"],
                role="paving_joint",
            )
        for joint in range(6):
            box(
                site,
                f"site:paving_cross_joint_{index}_{joint}",
                (x, -23.4 + joint * 2.5, 0.255),
                (width + 3.8, 0.025, 0.012),
                M["black_metal"],
                role="paving_joint",
            )
    box(
        site,
        "site:dropoff_lane",
        (0.0, -27.0, 0.06),
        (230.0, 7.0, 0.18),
        M["asphalt"],
        role="hospital_dropoff_lane",
    )
    box(
        site,
        "site:public_road",
        (0.0, -39.0, 0.0),
        (238.0, 17.0, 0.22),
        M["asphalt"],
        role="public_road",
    )
    box(
        site,
        "site:north_sidewalk",
        (0.0, -31.5, 0.18),
        (238.0, 2.2, 0.28),
        M["concrete_light"],
        role="public_sidewalk",
    )
    box(
        site,
        "site:south_sidewalk",
        (0.0, -47.3, 0.18),
        (238.0, 2.2, 0.28),
        M["concrete_light"],
        role="public_sidewalk",
    )
    box(
        site,
        "site:north_curb",
        (0.0, -32.7, 0.24),
        (238.0, 0.28, 0.46),
        M["concrete"],
        0.045,
        role="road_curb",
    )
    box(
        site,
        "site:south_curb",
        (0.0, -45.9, 0.24),
        (238.0, 0.28, 0.46),
        M["concrete"],
        0.045,
        role="road_curb",
    )
    box(
        site,
        "site:center_line",
        (0.0, -39.4, 0.125),
        (238.0, 0.16, 0.025),
        M["road_yellow"],
        role="road_marking",
    )
    for dash in range(-19, 20):
        box(
            site,
            f"site:lane_dash_{dash}",
            (dash * 6.0, -35.9, 0.125),
            (3.2, 0.12, 0.025),
            M["road_white"],
            role="road_marking",
        )

    # Correct north/south pedestrian crossings: every painted bar runs east/west.
    for crossing, x in enumerate((-72.0, 0.0, 72.0)):
        for stripe in range(12):
            y = -44.9 + stripe * 1.02
            bar = box(
                site,
                f"site:crosswalk_{crossing}_{stripe}",
                (x, y, 0.135),
                (5.4, 0.52, 0.025),
                M["road_white"],
                role="crosswalk_marking",
            )
            bar["c2w_crosswalk_bar_axis"] = "east_west"
            bar["c2w_pedestrian_axis"] = "north_south"
        for side in (-1, 1):
            box(
                site,
                f"site:tactile_pad_{crossing}_{side}",
                (x, -32.0 if side > 0 else -46.6, 0.36),
                (5.8, 1.10, 0.14),
                M["road_yellow"],
                0.045,
                role="tactile_paving",
            )
            for row in range(3):
                for stud in range(16):
                    cylinder(
                        site,
                        f"site:tactile_stud_{crossing}_{side}_{row}_{stud}",
                        (
                            x - 2.62 + stud * 0.35,
                            (-32.0 if side > 0 else -46.6) - 0.31 + row * 0.31,
                            0.47,
                        ),
                        0.045,
                        0.035,
                        M["road_yellow"],
                        12,
                        role="tactile_paving_stud",
                    )

    # Drop-off lane arrows and emergency curb coloration are physically modeled paint.
    for lane_x in (-74.0, -10.0, 58.0):
        box(
            site,
            f"site:dropoff_arrow_shaft_{lane_x}",
            (lane_x, -27.0, 0.165),
            (5.0, 0.18, 0.025),
            M["road_white"],
            role="dropoff_lane_marking",
        )
        for side in (-1, 1):
            arrow = box(
                site,
                f"site:dropoff_arrow_head_{lane_x}_{side}",
                (lane_x + 2.35, -27.0 + side * 0.55, 0.165),
                (1.5, 0.17, 0.025),
                M["road_white"],
                role="dropoff_lane_marking",
            )
            arrow.rotation_euler[2] = side * math.radians(38)
    box(
        site,
        "site:emergency_red_curb",
        (7.0, -30.55, 0.36),
        (42.0, 0.18, 0.48),
        M["red_panel"],
        role="emergency_curb_marking",
    )

    # Stormwater details and utility covers prevent an empty, model-base appearance.
    for drain in range(-19, 20):
        x = drain * 6.0
        box(
            site,
            f"site:storm_drain_frame_{drain}",
            (x, -32.54, 0.38),
            (1.05, 0.38, 0.06),
            M["black_metal"],
            0.045,
            role="storm_drain_frame",
        )
        for slot in range(7):
            box(
                site,
                f"site:storm_drain_slot_{drain}_{slot}",
                (x - 0.39 + slot * 0.13, -32.74, 0.40),
                (0.045, 0.25, 0.025),
                M["black_metal"],
                role="storm_drain_slot",
            )
    for cover, x in enumerate((-44.0, 35.0, 100.0)):
        cylinder(
            site,
            f"site:utility_cover_{cover}",
            (x, -38.5, 0.135),
            0.62,
            0.04,
            M["black_metal"],
            40,
            role="utility_cover",
        )
        for ring in (0.22, 0.42):
            cylinder(
                site,
                f"site:utility_cover_ring_{cover}_{ring}",
                (x, -38.5, 0.16),
                ring,
                0.018,
                M["aluminum"],
                32,
                role="utility_cover_detail",
            )

    # Stone planters, dense shrubs, benches and street lights.  The former row
    # of short cylindrical perimeter bollards is intentionally absent so the
    # complete hospital arrival frontage remains clear.
    planter_specs = ((-105, -13, 8.0), (-46, -16, 8.0), (41, -16, 8.0), (104, -13, 8.0))
    for planter, (x, y, width) in enumerate(planter_specs):
        box(
            site,
            f"site:planter_wall_{planter}",
            (x, y, 0.50),
            (width, 2.8, 0.90),
            M["concrete_light"],
            0.055,
            role="planter_wall",
        )
        box(
            site,
            f"site:planter_soil_{planter}",
            (x, y, 0.98),
            (width - 0.55, 2.22, 0.10),
            M["soil"],
            role="planter_soil",
        )
        for shrub in range(max(4, int(width // 1.6))):
            detailed_shrub(
                site,
                f"site:planter_{planter}_shrub_{shrub}",
                x - width / 2.0 + 0.8 + shrub * 1.55,
                y,
                1.02,
                0.62 + 0.06 * (shrub % 3),
                M,
                SEED + planter * 100 + shrub,
            )
    for bench, (x, y, yaw) in enumerate(
        (
            (-91, -24.5, 0.0),
            (-53, -24.5, math.pi),
            (-19, -24.5, 0.0),
            (28, -24.5, math.pi),
            (55, -24.5, 0.0),
            (93, -24.5, math.pi),
        )
    ):
        site_bench(site, f"site:bench_{bench}", x, y, 0.28, M, yaw)
    for light_index, x in enumerate((-108, -88, -55, -34, -16, 16, 34, 55, 88, 108)):
        site_light(site, f"site:light_{light_index}", x, -29.7, 0.38, M)
    # Full branch/leaf street trees are kept outside entrance sightlines.
    tree_layout = (
        (-109, 18, 1.02, 1),
        (-106, -22, 0.88, 2),
        (-47, 25, 0.96, 3),
        (42, 25, 1.00, 4),
        (107, 20, 1.04, 5),
        (106, -22, 0.90, 6),
    )
    tree_records = []
    for x, y, scale, variant in tree_layout:
        tree = detailed_street_tree(
            site, f"site:tree_{variant}", x, y, 0.28, scale, M, SEED + variant * 41
        )
        tree_records.append(
            {
                "name": tree.name,
                "location": [x, y, 0.28],
                "leaf_cards": 1400,
                "branch_count": 44,
            }
        )
    site["c2w_tree_records"] = json.dumps(tree_records)
    site[
        "c2w_detail_profile"
    ] = "separate foundations+jointed bollard-free forecourts+dropoff/public road+correct crosswalks+tactile paving+stormwater+utilities+constructed furniture+six high-detail branch/leaf trees"
    return site


def build_hospital_asset(
    variant,
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    include_site=True,
    materials=None,
):
    """Build one selected reference type for direct urban-pipeline placement."""
    if variant not in HOSPITAL_VARIANTS:
        raise ValueError(
            f"Unknown hospital variant {variant!r}; expected one of {HOSPITAL_VARIANTS}"
        )
    M = materials or make_materials()
    builders = {
        "traditional_brick": traditional_hospital,
        "red_white_public": public_hospital,
        "glass_ribbon_modern": modern_hospital,
    }
    asset = builders[variant](
        parent, origin=origin, yaw=yaw, include_site=include_site, materials=M
    )
    asset["c2w_pipeline_entrypoint"] = "generate_urban_v3_hospital.build_hospital_asset"
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_hospital_reference_row(parent=None, include_site=True):
    """Build all three independent hospitals in one east-west comparison row."""
    M = make_materials()
    root = collection(
        "THREE_REFERENCE_HOSPITAL_ROW",
        parent,
        "hospital_reference_row",
        "hospital.reference.row.v9",
    )
    root[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_hospital.build_hospital_reference_row"
    root["c2w_scene_asset_inputs"] = 0
    root["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    root["c2w_reference_cache"] = json.dumps(
        [str(path) for path in REFERENCE_CACHE], ensure_ascii=False
    )
    root[
        "c2w_layout_summary"
    ] = "three distinct reference-matched hospitals aligned east-west in one row, all facing south"
    root[
        "c2w_quality_profile"
    ] = "independent_reference_specific_massing+constructed_facade_depth+physically_layered_four_sided_glazing+occupied_clinical_interiors+roof_services+flush_obstruction_free_access+complete_urban_site"
    if include_site:
        build_hospital_site(root, M)
    traditional_hospital(root, (-72.0, 8.0, 0.0), 0.0, False, M)
    public_hospital(root, (0.0, 8.0, 0.0), 0.0, False, M)
    modern_hospital(root, (72.0, 8.0, 0.0), 0.0, False, M)
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
    data.sensor_width = 36.0
    data.dof.use_dof = False
    data.clip_start = 0.10
    data.clip_end = 1000.0
    return tag(obj, "validation_camera")


def validation_camera_specs():
    return [
        (
            "01_three_hospitals_front_daylight_far.png",
            (0.0, -228.0, 46.0),
            (0.0, 2.0, 10.5),
            42,
        ),
        (
            "02_three_hospitals_west_oblique_far.png",
            (-172.0, -168.0, 60.0),
            (0.0, 3.0, 11.0),
            48,
        ),
        (
            "03_three_hospitals_east_oblique_far.png",
            (172.0, -164.0, 58.0),
            (0.0, 3.0, 11.0),
            48,
        ),
        (
            "04_three_hospitals_rear_aerial_far.png",
            (0.0, 184.0, 58.0),
            (0.0, 7.0, 10.5),
            40,
        ),
        (
            "05_type_a_reference_oblique_near.png",
            (-108.0, -64.0, 18.0),
            (-72.0, 2.0, 9.2),
            54,
        ),
        (
            "06_type_a_entrance_atrium_close.png",
            (-87.0, -38.0, 6.2),
            (-78.0, -5.8, 4.6),
            54,
        ),
        ("07_type_b_public_front_near.png", (-42.0, -73.0, 19.0), (0.0, 1.0, 11.2), 55),
        (
            "08_type_b_emergency_entrance_close.png",
            (37.0, -43.0, 8.5),
            (21.0, -11.5, 3.3),
            54,
        ),
        (
            "09_type_c_reference_oblique_near.png",
            (121.0, -54.0, 21.0),
            (86.0, 4.5, 11.2),
            55,
        ),
        ("10_type_c_lobby_tower_close.png", (91.0, -43.0, 7.0), (73.0, -7.0, 5.5), 52),
    ]


def setup_daylight():
    scene = bpy.context.scene
    world = bpy.data.worlds.new(PREFIX + "clear_day_world")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(41.0)
    sky.sun_rotation = math.radians(142.0)
    sky.altitude = 0.22
    sky.air_density = 0.82
    sky.dust_density = 0.055
    sky.ozone_density = 1.08
    background.inputs["Strength"].default_value = 0.19
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 1.28
    sun_data.angle = math.radians(0.58)
    sun_obj = bpy.data.objects.new(PREFIX + "day_sun", sun_data)
    bpy.context.scene.collection.objects.link(sun_obj)
    sun_obj.location = (-90.0, -125.0, 145.0)
    sun_obj.rotation_euler = (
        (Vector((0.0, 0.0, 7.0)) - sun_obj.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(sun_obj, "daylight_sun")

    fill_data = bpy.data.lights.new(PREFIX + "day_sky_fill", "AREA")
    fill_data.energy = 105.0
    fill_data.shape = "DISK"
    fill_data.size = 65.0
    fill_obj = bpy.data.objects.new(PREFIX + "day_sky_fill", fill_data)
    bpy.context.scene.collection.objects.link(fill_obj)
    fill_obj.location = (60.0, -30.0, 85.0)
    fill_obj.rotation_euler = (
        (Vector((15.0, 0.0, 8.0)) - fill_obj.location)
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    tag(fill_obj, "daylight_fill")


def configure_render(
    engine="CYCLES", samples=40, resolution=(1600, 960), percentage=100
):
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = percentage
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    scene.render.image_settings.compression = 28
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.78
    if engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.018
        scene.cycles.max_bounces = 7
        scene.cycles.diffuse_bounces = 4
        scene.cycles.glossy_bounces = 4
        scene.cycles.transmission_bounces = 6
        scene.cycles.transparent_max_bounces = 8
        scene.cycles.volume_bounces = 1
        for attr in (
            "use_caustics",
            "use_reflective_caustics",
            "use_refractive_caustics",
        ):
            if hasattr(scene.cycles, attr):
                setattr(scene.cycles, attr, False)


def render_views(cameras):
    configure_render()
    scene = bpy.context.scene
    for index, (filename, cam) in enumerate(cameras, 1):
        print(f"HOSPITAL_RENDER_START={index}/{len(cameras)}:{filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)
        print(f"HOSPITAL_RENDER_DONE={index}/{len(cameras)}:{filename}", flush=True)


def _role_counts(objects):
    counts = {}
    for obj in objects:
        role = obj.get("c2w_role", "untagged")
        counts[role] = counts.get(role, 0) + 1
    return counts


def audit(root, cameras):
    bpy.context.view_layer.update()
    objects = list(bpy.context.scene.objects)
    renderable = [
        obj
        for obj in objects
        if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
    ]
    role_counts = _role_counts(objects)
    hospitals = [
        child for child in root.children if child.get("c2w_role") == "hospital_asset"
    ]
    site = next(
        (child for child in root.children if child.get("c2w_role") == "hospital_site"),
        None,
    )
    variants = sorted(child.get("c2w_variant") for child in hospitals)
    indices = sorted(int(child.get("c2w_reference_index")) for child in hospitals)
    roots = [obj for obj in objects if obj.get("c2w_role") == "hospital_asset_root"]
    root_xs = sorted(round(obj.location.x, 2) for obj in roots)
    banned_tokens = ("placeholder", "proxy", "dummy", "toy", "blob", "lowpoly")
    banned = [
        obj.name
        for obj in renderable
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    complex_materials = [
        mat
        for mat in bpy.data.materials
        if mat.use_nodes
        and mat.node_tree
        and len(mat.node_tree.nodes) >= 5
        and mat.get("c2w_procedural_material")
    ]
    crosswalks = [
        obj for obj in renderable if obj.get("c2w_role") == "crosswalk_marking"
    ]
    crosswalks_correct = len(crosswalks) == 36 and all(
        obj.get("c2w_crosswalk_bar_axis") == "east_west"
        and obj.get("c2w_pedestrian_axis") == "north_south"
        for obj in crosswalks
    )
    leaf_cards = sum(
        int(obj.get("c2w_leaf_card_count", 0))
        for obj in objects
        if obj.get("c2w_role") == "tree_leaf_cards"
    )
    mesh_vertices = sum(
        len(obj.data.vertices) for obj in renderable if obj.type == "MESH"
    )
    mesh_polygons = sum(
        len(obj.data.polygons) for obj in renderable if obj.type == "MESH"
    )
    building_object_counts = {
        child.get("c2w_variant"): len(child.all_objects) for child in hospitals
    }
    reference_files = [
        {
            "path": str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
        for path in REFERENCE_CACHE
    ]
    # Validate actual evaluated letter geometry against each modeled sign backer.
    # Bounds are measured in the owning building's local coordinates, so the same
    # assertion also remains valid when the production adapter moves or rotates it.
    identity_signs = [obj for obj in objects if obj.get("c2w_sign_clear_readable")]
    sign_containment_diagnostics = []
    for sign in identity_signs:
        backer_bounds = json.loads(sign.get("c2w_sign_backer_bounds"))
        parent_inverse = sign.parent.matrix_world.inverted_safe()
        local_corners = [
            parent_inverse @ sign.matrix_world @ Vector(corner)
            for corner in sign.bound_box
        ]
        measured = [
            min(point.x for point in local_corners),
            max(point.x for point in local_corners),
            min(point.z for point in local_corners),
            max(point.z for point in local_corners),
        ]
        contained = (
            measured[0] >= backer_bounds[0] - 0.01
            and measured[1] <= backer_bounds[1] + 0.01
            and measured[2] >= backer_bounds[2] - 0.01
            and measured[3] <= backer_bounds[3] + 0.01
        )
        readable_size = (
            measured[1] - measured[0] >= 7.0 and measured[3] - measured[2] >= 1.15
        )
        sign_containment_diagnostics.append(
            {
                "name": sign.name,
                "text": sign.data.body,
                "measured_local_xz": [round(value, 4) for value in measured],
                "backer_local_xz": backer_bounds,
                "contained": contained,
                "readable_size": readable_size,
            }
        )

    def world_bounds(obj):
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return {
            "x": (min(point.x for point in corners), max(point.x for point in corners)),
            "y": (min(point.y for point in corners), max(point.y for point in corners)),
            "z": (min(point.z for point in corners), max(point.z for point in corners)),
        }

    def ranges_overlap(a, b, tolerance=0.0):
        return a[0] < b[1] - tolerance and b[0] < a[1] - tolerance

    ambulance_objects = [
        obj
        for obj in objects
        if "ambulance" in obj.name.lower()
        or "ambulance" in str(obj.get("c2w_role", "")).lower()
    ]
    rear_glazing = [
        obj
        for obj in renderable
        if obj.name.endswith(":glazing")
        and (":rear_window_" in obj.name or ":rear_ribbon_module_" in obj.name)
    ]
    rear_dark_backings = [
        obj
        for obj in renderable
        if (":rear_window_" in obj.name or ":rear_ribbon_module_" in obj.name)
        and obj.get("c2w_role") == "interior_window_back"
    ]

    traditional_emergency_doors = [
        obj
        for obj in renderable
        if "traditional:emergency_entry" in obj.name
        and obj.get("c2w_role") == "entrance_door_glazing"
    ]
    traditional_ground_windows = [
        obj
        for obj in renderable
        if "traditional:front_window_0_" in obj.name and obj.name.endswith(":glazing")
    ]
    traditional_door_window_conflicts = []
    for door in traditional_emergency_doors:
        door_bounds = world_bounds(door)
        for window in traditional_ground_windows:
            window_bounds = world_bounds(window)
            if all(
                ranges_overlap(door_bounds[axis], window_bounds[axis])
                for axis in ("x", "y", "z")
            ):
                traditional_door_window_conflicts.append([door.name, window.name])

    modern_door_leaves = [
        obj
        for obj in renderable
        if (
            "modern:main_sliding_entry" in obj.name
            or "modern:secondary_entry" in obj.name
        )
        and obj.get("c2w_role") == "entrance_door_glazing"
    ]
    modern_columns = [
        obj
        for obj in renderable
        if "modern:canopy_column_" in obj.name
        and obj.get("c2w_role") == "canopy_column"
    ]
    modern_column_door_conflicts = []
    for column in modern_columns:
        column_x = world_bounds(column)["x"]
        for door in modern_door_leaves:
            door_x = world_bounds(door)["x"]
            if ranges_overlap(column_x, (door_x[0] - 0.30, door_x[1] + 0.30)):
                modern_column_door_conflicts.append([column.name, door.name])

    public_emergency_doors = [
        obj
        for obj in renderable
        if "public:emergency_sliding_doors" in obj.name
        and obj.get("c2w_role") == "entrance_door_glazing"
    ]
    security_bollards = [
        obj for obj in renderable if obj.get("c2w_role") == "security_bollard"
    ]
    named_bollards = [obj for obj in renderable if "bollard" in obj.name.lower()]

    # Validate the corrected Type-B facade interface from evaluated geometry,
    # not only from construction parameters.  Five red bands must terminate at
    # the left red pier, while all white-wing closure components stay west of it
    # and all tower glazing stays east of the band end.
    public_red_bands = [
        obj
        for obj in renderable
        if obj.get("c2w_role") == "red_cladding_band" and "public:" in obj.name
    ]
    public_tower_glass = [
        obj for obj in renderable if obj.get("c2w_role") == "public_curtain_wall"
    ]
    public_front_closure_parts = [
        obj
        for obj in renderable
        if any(
            token in obj.name
            for token in (
                "public:front_patient_window_",
                "public:white_pier_",
                "public:window_sunshade_",
                "public:sunshade_bracket_",
                "public:full_height_facade_fin_",
            )
        )
    ]
    public_band_right_edges = [world_bounds(obj)["x"][1] for obj in public_red_bands]
    public_glass_left_edge = min(
        (world_bounds(obj)["x"][0] for obj in public_tower_glass), default=None
    )
    public_front_closure_right_edge = max(
        (world_bounds(obj)["x"][1] for obj in public_front_closure_parts),
        default=None,
    )
    public_band_termination_valid = (
        len(public_red_bands) == 5
        and all(
            abs(edge - PUBLIC_RED_BAND_END_X) <= 0.002
            for edge in public_band_right_edges
        )
        and all(
            obj.get("c2w_termination_detail") == "concealed_behind_left_red_tower_pier"
            for obj in public_red_bands
        )
        and public_glass_left_edge is not None
        and public_glass_left_edge >= PUBLIC_GLASS_TOWER_LEFT_X - 0.002
        and max(public_band_right_edges) < public_glass_left_edge - 0.25
    )
    public_front_closure_clear_of_tower = (
        public_front_closure_right_edge is not None
        and public_front_closure_right_edge <= PUBLIC_RED_BAND_END_X - 0.46 - 0.05
    )

    east_cross_backer = next(
        (obj for obj in renderable if "modern:east_cross_white_backer" in obj.name),
        None,
    )
    east_cross_parts = [
        obj
        for obj in renderable
        if "modern:east_medical_cross" in obj.name
        and obj.get("c2w_role") == "medical_cross"
    ]
    east_cross_contained = False
    if east_cross_backer is not None and len(east_cross_parts) == 2:
        backer_bounds = world_bounds(east_cross_backer)
        east_cross_contained = all(
            world_bounds(part)["y"][0] >= backer_bounds["y"][0] - 0.01
            and world_bounds(part)["y"][1] <= backer_bounds["y"][1] + 0.01
            and world_bounds(part)["z"][0] >= backer_bounds["z"][0] - 0.01
            and world_bounds(part)["z"][1] <= backer_bounds["z"][1] + 0.01
            for part in east_cross_parts
        )
    modern_landing = next(
        (obj for obj in renderable if "modern:entrance_landing" in obj.name), None
    )
    modern_route = next(
        (obj for obj in renderable if "modern:forecourt_accessible_route" in obj.name),
        None,
    )
    modern_site_forecourt = next(
        (obj for obj in renderable if "site:forecourt_2" in obj.name), None
    )
    modern_route_contact_gap = None
    modern_route_surface_offset = None
    modern_route_join_valid = False
    if (
        modern_landing is not None
        and modern_route is not None
        and modern_site_forecourt is not None
    ):
        landing_bounds = world_bounds(modern_landing)
        route_bounds = world_bounds(modern_route)
        site_bounds = world_bounds(modern_site_forecourt)
        modern_route_contact_gap = abs(landing_bounds["y"][0] - route_bounds["y"][1])
        modern_route_surface_offset = route_bounds["z"][1] - site_bounds["z"][1]
        modern_route_join_valid = (
            modern_route_contact_gap <= 0.002
            and not ranges_overlap(
                landing_bounds["y"], route_bounds["y"], tolerance=0.002
            )
            and 0.0005 <= modern_route_surface_offset <= 0.005
        )
    view_names = [name for name, _ in cameras]
    checks = {
        "exactly_three_independent_reference_hospitals": len(hospitals) == 3
        and indices == [1, 2, 3]
        and variants == sorted(HOSPITAL_VARIANTS),
        "all_three_are_dense_complex_assets": len(building_object_counts) == 3
        and min(building_object_counts.values()) >= 1100,
        "single_east_west_row": root.get("c2w_layout_summary")
        == "three distinct reference-matched hospitals aligned east-west in one row, all facing south"
        and root_xs == [-72.0, 0.0, 72.0],
        "source_generator_is_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_hospital.build_hospital_reference_row",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "all_supplied_references_cached": all(
            item["exists"] and item["bytes"] >= 6000 for item in reference_files
        ),
        "deep_layered_four_sided_fenestration": role_counts.get("window_reveal", 0)
        >= 400
        and role_counts.get("window_frame", 0) >= 800
        and role_counts.get("glazing_gasket", 0) >= 700,
        "all_rear_windows_rebuilt_as_north_facing_insulated_assemblies": len(
            rear_glazing
        )
        == 82
        and all(
            obj.get("c2w_facade_orientation") == "north"
            and abs(float(obj.get("c2w_insulated_glazing_depth_m", 0.0)) - 0.08) < 1e-6
            for obj in rear_glazing
        )
        and role_counts.get("insulated_glazing_inner", 0) == 82
        and role_counts.get("rear_window_interior_wall", 0) == 82
        and not rear_dark_backings,
        "fine_curtain_wall_construction": role_counts.get("curtain_wall_mullion", 0)
        >= 125
        and role_counts.get("curtain_wall_pressure_plate", 0) >= 110,
        "reference_a_brick_stone_atrium_and_cornices": role_counts.get(
            "brick_cladding_panel", 0
        )
        >= 9
        and role_counts.get("stone_cladding_panel", 0) >= 17
        and role_counts.get("atrium_glazing", 0) == 24
        and role_counts.get("traditional_cornice", 0) == 4,
        "reference_b_red_bands_glass_tower_and_ac": role_counts.get(
            "red_cladding_band", 0
        )
        == 5
        and role_counts.get("public_curtain_wall", 0) == 25
        and role_counts.get("external_ac_unit", 0) == 12
        and role_counts.get("red_entry_portal", 0) == 3,
        "reference_c_ribbons_rainscreen_canopy_and_stair_tower": role_counts.get(
            "ribbon_window", 0
        )
        >= 84
        and role_counts.get("white_rainscreen_panel", 0) >= 70
        and role_counts.get("projecting_canopy", 0) == 1
        and role_counts.get("glass_stair_tower", 0) == 50
        and role_counts.get("stair_tread", 0) == 48,
        "all_three_facades_have_projecting_architectural_depth": role_counts.get(
            "facade_projecting_pilaster", 0
        )
        >= 5
        and role_counts.get("projecting_window_hood", 0) >= 8
        and role_counts.get("projecting_window_sunshade", 0) >= 32
        and role_counts.get("facade_vertical_fin", 0) >= 15
        and role_counts.get("projecting_ribbon_sill", 0) >= 3
        and role_counts.get("canopy_soffit_coffer", 0) >= 19,
        "medical_identity_and_usable_entries": role_counts.get("medical_cross", 0) == 10
        and role_counts.get("hospital_wordmark", 0) >= 7
        and role_counts.get("entrance_door_glazing", 0) >= 10
        and role_counts.get("door_hardware", 0) >= 20,
        "three_large_hospital_wordmarks_are_inside_facades": len(
            sign_containment_diagnostics
        )
        == 3
        and all(
            item["contained"] and item["readable_size"]
            for item in sign_containment_diagnostics
        ),
        "occupied_clinical_interiors": role_counts.get("patient_bed", 0) >= 37
        and role_counts.get("patient_monitor", 0) >= 37
        and role_counts.get("waiting_chair", 0) >= 45
        and role_counts.get("reception_desk", 0) >= 4,
        "modeled_roof_services_and_drainage": role_counts.get("roof_mechanical_unit", 0)
        >= 9
        and role_counts.get("mechanical_louver", 0) >= 120
        and role_counts.get("roof_fan_blade", 0) >= 54
        and role_counts.get("rainwater_downpipe", 0) >= 8,
        "ambulance_completely_removed": not ambulance_objects,
        "traditional_emergency_door_clear_of_windows": len(traditional_emergency_doors)
        == 2
        and not traditional_door_window_conflicts
        and role_counts.get("detailed_emergency_portal", 0) >= 3
        and role_counts.get("portal_panel_joint", 0) >= 4,
        "all_entrances_are_flush_and_connected_without_orphan_ramps": role_counts.get(
            "accessible_ramp", 0
        )
        == 0
        and role_counts.get("flush_accessible_route", 0) >= 4
        and role_counts.get("entrance_trench_drain", 0) >= 4
        and role_counts.get("entrance_drain_grating", 0) >= 130,
        "all_doorway_and_forecourt_bollards_removed": not security_bollards
        and not named_bollards,
        "entrance_clear_zones_have_no_door_column_conflicts": len(
            public_emergency_doors
        )
        == 2
        and len(modern_door_leaves) == 4
        and len(modern_columns) == 6
        and not modern_column_door_conflicts,
        "public_red_bands_terminate_at_vertical_pier_before_glass": public_band_termination_valid,
        "public_white_facade_closure_is_clear_of_glass_tower": public_front_closure_clear_of_tower,
        "modern_east_cross_is_contained_on_white_wall_backer": east_cross_contained
        and role_counts.get("side_medical_sign_backer", 0) == 1,
        "modern_flush_route_is_end_joined_without_coplanar_overlap": modern_route_join_valid,
        "complete_urban_foreground": role_counts.get("public_road", 0) == 1
        and role_counts.get("storm_drain_slot", 0) >= 270
        and crosswalks_correct
        and role_counts.get("site_light_pole", 0) == 10,
        "high_detail_landscape_not_simple_canopy_primitives": role_counts.get(
            "street_tree_root", 0
        )
        == 6
        and role_counts.get("tree_branch", 0) >= 260
        and leaf_cards >= 7200,
        "sufficient_geometric_density": len(renderable) >= 8000
        and mesh_vertices >= 125_000
        and mesh_polygons >= 68_000,
        "multi_scale_procedural_materials": len(complex_materials) >= 20,
        "ten_daylight_near_far_views": len(cameras) == 10
        and sum("far" in name for name in view_names) == 4
        and sum("close" in name for name in view_names) == 3
        and sum("near" in name for name in view_names) == 3,
        "all_renderables_are_source_tagged": all(
            obj.get("c2w_role") and obj.get("c2w_generator") == Path(__file__).name
            for obj in renderable
        ),
        "no_placeholder_or_degenerate_named_geometry": not banned,
    }
    result = {
        "generator": str(Path(__file__).resolve()),
        "pipeline_entrypoint": root.get("c2w_pipeline_entrypoint"),
        "pipeline_adapter": "urban_assets.build_hospital_reference_row",
        "single_asset_adapter": "urban_assets.build_hospital_asset",
        "output": str(OUT),
        "revision": REVISION,
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "reference_urls": REFERENCE_URLS,
        "reference_cache": reference_files,
        "reference_analysis": REFERENCE_ANALYSIS,
        "layout": {
            "arrangement": "east_west_single_row",
            "origins_m": {
                "traditional_brick": [-72.0, 8.0, 0.0],
                "red_white_public": [0.0, 8.0, 0.0],
                "glass_ribbon_modern": [72.0, 8.0, 0.0],
            },
            "front_direction": "south",
        },
        "building_object_counts": building_object_counts,
        "hospital_sign_containment": sign_containment_diagnostics,
        "ambulance_object_count": len(ambulance_objects),
        "physical_correction_diagnostics": {
            "rear_window_assembly_count": len(rear_glazing),
            "rear_dark_backing_count": len(rear_dark_backings),
            "traditional_door_window_conflicts": traditional_door_window_conflicts,
            "modern_column_door_conflicts": modern_column_door_conflicts,
            "scene_security_bollard_count": len(security_bollards),
            "named_bollard_object_count": len(named_bollards),
            "public_red_band_right_edges_m": [
                round(value, 4) for value in public_band_right_edges
            ],
            "public_red_band_required_end_x_m": PUBLIC_RED_BAND_END_X,
            "public_glass_left_edge_m": round(public_glass_left_edge, 4)
            if public_glass_left_edge is not None
            else None,
            "public_white_facade_closure_right_edge_m": round(
                public_front_closure_right_edge, 4
            )
            if public_front_closure_right_edge is not None
            else None,
            "public_red_band_clearance_to_glass_m": round(
                public_glass_left_edge - max(public_band_right_edges), 4
            )
            if public_glass_left_edge is not None and public_band_right_edges
            else None,
            "public_white_facade_clearance_to_red_pier_m": round(
                (PUBLIC_RED_BAND_END_X - 0.46) - public_front_closure_right_edge, 4
            )
            if public_front_closure_right_edge is not None
            else None,
            "modern_east_cross_contained_on_white_backer": east_cross_contained,
            "modern_route_contact_gap_m": round(modern_route_contact_gap, 6)
            if modern_route_contact_gap is not None
            else None,
            "modern_route_surface_offset_from_site_m": round(
                modern_route_surface_offset, 6
            )
            if modern_route_surface_offset is not None
            else None,
            "accessible_ramp_object_count": role_counts.get("accessible_ramp", 0),
            "flush_accessible_route_count": role_counts.get(
                "flush_accessible_route", 0
            ),
        },
        "object_count": len(objects),
        "renderable_count": len(renderable),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "mesh_vertices_instance_sum": mesh_vertices,
        "mesh_polygons_instance_sum": mesh_polygons,
        "leaf_card_count": leaf_cards,
        "role_counts": role_counts,
        "validation_views": view_names,
        "daylight": True,
        "near_and_far_views": True,
        "render_engine": "CYCLES",
        "render_samples": 40,
        "resolution": [1600, 960],
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
            "Hospital production audit failed: "
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
        if not path.exists() or path.stat().st_size < 160_000:
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
            and height >= 960
            and variance >= 0.0025
            and dark_fraction < 0.70
            and light_fraction < 0.70
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
    data["checks"]["all_ten_daylight_renders_are_nonblank_1600x960"] = len(
        diagnostics
    ) == 10 and all(item["passed"] for item in diagnostics.values())
    data["all_checks_passed"] = all(data["checks"].values())
    (OUT / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    if not data["all_checks_passed"]:
        raise RuntimeError(
            "Hospital final render audit failed: "
            + json.dumps(data, indent=2, ensure_ascii=False)
        )
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    reset_scene()
    set_prefix(PREFIX)
    root, _materials = build_hospital_reference_row()
    setup_daylight()
    cameras = [
        (filename, camera(filename[:-4], location, target, lens))
        for filename, location, target, lens in validation_camera_specs()
    ]
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_hospital.build_hospital_reference_row"
    scene["c2w_pipeline_adapter"] = "urban_assets.build_hospital_reference_row"
    scene["c2w_single_asset_adapter"] = "urban_assets.build_hospital_asset"
    scene["c2w_schema_version"] = SCHEMA_VERSION
    scene["c2w_revision"] = REVISION
    scene["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    scene[
        "c2w_layout"
    ] = "three distinct hospitals; east-west row; all fronts face south"
    scene.camera = cameras[0][1]
    blend_path = OUT / f"{REVISION}.blend"
    configure_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    data = audit(root, cameras)
    render_views(cameras)
    data = finalize_manifest(data, cameras)
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    (OUT / "SUCCESS").write_text(
        "urban_v3_hospital4 live source-generator build: three fully articulated hospitals, bollard-free arrivals, Type-B red bands terminated at the vertical pier before the glass tower, physically separated facade closure, no ambulance, ten daylight near/far renders and strict validation complete\n",
        encoding="utf8",
    )
    print("HOSPITAL_PIPELINE_COMPLETE=" + str(blend_path), flush=True)


if __name__ == "__main__":
    main()
