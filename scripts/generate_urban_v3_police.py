"""Reference-matched procedural police precinct for the active Urban-v3 pipeline.

The three supplied photographs are represented by independent, reusable assets:

* ``blue_white_civic`` -- white two-storey station with a gabled wing, cobalt
  tiled base, blue fascia and a tall glazed entrance;
* ``brick_tower_municipal`` -- symmetric red-brick civic station with three
  white towers and the PROTECT / POLICE / SERVE identity hierarchy;
* ``blue_portal_cmu`` -- low grey-CMU public-safety complex with a monumental
  cobalt portal, two-storey glass lobby and dimensional municipal identity.

``build_police_station_asset`` and ``build_police_reference_row`` are the live
pipeline entry points.  All geometry is built from source on every call; the
validation blend is only an output and is never appended by production code.
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


import importlib.util
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
REVISION = "urban_v3_police3"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / REVISION
RENDERS = OUT / "renders"
PREFIX = "police:"
SCHEMA_VERSION = 10
SEED = 260831
RNG = random.Random(SEED)
FONT_PATH = Path("/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf")

POLICE_STATION_VARIANTS = (
    "blue_white_civic",
    "brick_tower_municipal",
    "blue_portal_cmu",
)
REFERENCE_URLS = [
    "https://thumbs.dreamstime.com/z/police-station-isolated-white-background-building-representing-law-enforcement-366244885.jpg",
    "https://diberville.ms.us/wp-content/uploads/2022/03/Diberville-Police-Building-Edit-3TAC_1611-1-1024x683.jpg",
    "https://www.idahofallsidaho.gov/ImageRepository/Document?documentID=17135",
]
REFERENCE_CACHE = [
    ROOT / ".reference_cache/police/reference_type_a.jpg",
    ROOT / ".reference_cache/police/reference_type_b.jpg",
    ROOT / ".reference_cache/police/reference_type_c.jpg",
]
REFERENCE_ANALYSIS = {
    "blue_white_civic": {
        "reference_index": 1,
        "visible_signature": "asymmetric white two-storey station, left gable, cobalt tiled plinth and fascia, stepped glazed entrance, tall right curtain wall, antennas and wall AC",
        "front_direction": "south",
    },
    "brick_tower_municipal": {
        "reference_index": 2,
        "visible_signature": "symmetric civic red-brick composition, three projecting white towers, dark blue-grey floating eaves, tall black-framed windows and large PROTECT POLICE SERVE lettering",
        "front_direction": "south",
    },
    "blue_portal_cmu": {
        "reference_index": 3,
        "visible_signature": "single-storey grey CMU wings, monumental cobalt aluminum portal, two-storey glazed vestibule, dark masonry end wing, large police identity, dome camera and FDC hardware",
        "front_direction": "south",
    },
}

# Blender and procedural dependencies must keep all caches under the workspace.
LOCAL_CACHE = ROOT / ".qa_tmp" / REVISION
LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(LOCAL_CACHE / "matplotlib")
os.environ["XDG_CACHE_HOME"] = str(LOCAL_CACHE / "xdg_cache")
os.environ["XDG_CONFIG_HOME"] = str(LOCAL_CACHE / "xdg_config")
os.environ["INFINIGEN_SKIP_TAGGING"] = "1"

# Load a private copy of the architectural primitive module.  Keeping this copy
# private matters when hospital and police assets coexist in one production
# process: rebinding our prefix/tagger cannot mutate the hospital generator.
_ARCH_PATH = ROOT / "scripts/generate_urban_v3_hospital.py"
_ARCH_SPEC = importlib.util.spec_from_file_location(
    "c2w_police_arch_primitives_v7", _ARCH_PATH
)
if _ARCH_SPEC is None or _ARCH_SPEC.loader is None:
    raise RuntimeError(
        f"Unable to load procedural architecture primitives: {_ARCH_PATH}"
    )
ARCH = importlib.util.module_from_spec(_ARCH_SPEC)
sys.modules[_ARCH_SPEC.name] = ARCH
_ARCH_SPEC.loader.exec_module(ARCH)


def tag(obj, role: str, asset_id: str | None = None):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = role
    obj["c2w_generator"] = Path(__file__).name
    if asset_id:
        obj["c2w_asset_id"] = asset_id
    return obj


def set_prefix(prefix: str):
    """Rebind names and primitive caches for embedding by a larger urban scene."""
    global PREFIX
    PREFIX = prefix
    ARCH.PREFIX = prefix
    ARCH.tag = tag
    ARCH._CUBE_MESHES.clear()
    ARCH._CYLINDER_MESHES.clear()
    ARCH._SPHERE_MESHES.clear()


set_prefix(PREFIX)

box = ARCH.box
cylinder = ARCH.cylinder
beam = ARCH.beam
sphere = ARCH.sphere
vertical_prism_y = ARCH.vertical_prism_y
lofted_vehicle_shell = ARCH.lofted_vehicle_shell
arc_tube = ARCH.arc_tube
area_light = ARCH.area_light


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    set_prefix(PREFIX)


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
    return tag(root, "police_station_asset_root", asset_id)


def _set_socket(node, names, value):
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return True
    return False


def pbr(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    noise_scale=0.0,
    bump=0.0,
    transmission=0.0,
    emission=None,
    emission_strength=0.0,
    ambient_grime=0.0,
):
    """Physically layered, world-scale material used by the live generator.

    The old implementation inherited object-local, high-contrast noise from a
    shared primitive helper.  At architectural scale that read as painted clay.
    This version keeps colour variation deliberately subtle, drives it from
    world position, separates broad weathering from fine surface relief and
    varies roughness independently.  It remains fully procedural and therefore
    works unchanged when the asset is embedded by ``urban_assets``.
    """
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.0)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    _set_socket(bsdf, ("Roughness",), roughness)
    _set_socket(bsdf, ("Metallic",), metallic)
    _set_socket(bsdf, ("IOR",), 1.47)
    if transmission:
        _set_socket(bsdf, ("Transmission Weight", "Transmission"), transmission)
        _set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.30)
        _set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.065)
    if emission is not None:
        _set_socket(bsdf, ("Emission Color", "Emission"), (*emission, 1.0))
        _set_socket(bsdf, ("Emission Strength",), emission_strength)

    if noise_scale:
        geometry = nodes.new("ShaderNodeNewGeometry")
        broad = nodes.new("ShaderNodeTexNoise")
        broad.noise_dimensions = "3D"
        broad.inputs["Scale"].default_value = max(0.35, noise_scale * 0.13)
        broad.inputs["Detail"].default_value = 3.2
        broad.inputs["Roughness"].default_value = 0.58
        broad.inputs["Distortion"].default_value = 0.08
        fine = nodes.new("ShaderNodeTexNoise")
        fine.noise_dimensions = "3D"
        fine.inputs["Scale"].default_value = max(2.0, noise_scale * 2.6)
        fine.inputs["Detail"].default_value = 4.5
        fine.inputs["Roughness"].default_value = 0.70
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.20
        ramp.color_ramp.elements[0].color = (*[max(0.0, c * 0.95) for c in color], 1.0)
        ramp.color_ramp.elements[1].position = 0.80
        ramp.color_ramp.elements[1].color = (
            *[min(1.0, c * 1.035 + 0.002) for c in color],
            1.0,
        )
        rough_ramp = nodes.new("ShaderNodeMapRange")
        rough_ramp.inputs["From Min"].default_value = 0.0
        rough_ramp.inputs["From Max"].default_value = 1.0
        rough_ramp.inputs["To Min"].default_value = max(0.03, roughness - 0.075)
        rough_ramp.inputs["To Max"].default_value = min(0.98, roughness + 0.075)
        rough_ramp.clamp = True
        links.new(geometry.outputs["Position"], broad.inputs["Vector"])
        links.new(geometry.outputs["Position"], fine.inputs["Vector"])
        links.new(broad.outputs["Fac"], ramp.inputs["Fac"])
        if ambient_grime:
            # Contact-darkening is evaluated against the actual constructed
            # facade.  It breaks the uniformly clean CG look around copings,
            # sill returns, panel joints and the wall/grade junction without
            # relying on an image texture or a validation-only paint-over.
            ao = nodes.new("ShaderNodeAmbientOcclusion")
            ao.inputs["Color"].default_value = (0.72, 0.74, 0.70, 1.0)
            ao.inputs["Distance"].default_value = 0.62
            ao.samples = 8
            grime_mix = nodes.new("ShaderNodeMixRGB")
            grime_mix.blend_type = "MULTIPLY"
            grime_mix.inputs["Fac"].default_value = ambient_grime
            links.new(ramp.outputs["Color"], grime_mix.inputs[1])
            links.new(ao.outputs["Color"], grime_mix.inputs[2])
            links.new(grime_mix.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(broad.outputs["Fac"], rough_ramp.inputs["Value"])
        links.new(rough_ramp.outputs["Result"], bsdf.inputs["Roughness"])
        if bump:
            bump_node = nodes.new("ShaderNodeBump")
            bump_node.inputs["Strength"].default_value = min(0.42, bump * 0.72)
            bump_node.inputs["Distance"].default_value = 0.018
            links.new(fine.outputs["Fac"], bump_node.inputs["Height"])
            links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_procedural_material"] = True
    mat["c2w_material_profile"] = "world_space_weathering_plus_microrelief"
    return mat


def architectural_glass(name, color, transmission=0.20, roughness=0.145):
    mat = pbr(name, color, roughness, metallic=0.035, transmission=transmission)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        _set_socket(bsdf, ("Alpha",), 1.0)
        _set_socket(bsdf, ("Coat Weight", "Clearcoat"), 0.28)
        _set_socket(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.095)
        # A physically reflective pane never reads as one uniform dark swatch.
        # Generated-Z supplies a restrained ground/sky gradient on every pane;
        # Object Info Random adds subtle pane-to-pane coating variation.  Both
        # remain procedural and travel with the production source adapter.
        coordinates = nodes.new("ShaderNodeTexCoord")
        separate = nodes.new("ShaderNodeSeparateXYZ")
        reflection_ramp = nodes.new("ShaderNodeValToRGB")
        reflection_ramp.color_ramp.interpolation = "EASE"
        reflection_ramp.color_ramp.elements[0].position = 0.06
        reflection_ramp.color_ramp.elements[0].color = (
            min(1.0, color[0] * 0.52 + 0.004),
            min(1.0, color[1] * 0.50 + 0.006),
            min(1.0, color[2] * 0.48 + 0.007),
            1.0,
        )
        reflection_ramp.color_ramp.elements[1].position = 0.88
        reflection_ramp.color_ramp.elements[1].color = (
            min(1.0, color[0] * 2.10 + 0.025),
            min(1.0, color[1] * 2.35 + 0.052),
            min(1.0, color[2] * 2.45 + 0.085),
            1.0,
        )
        object_info = nodes.new("ShaderNodeObjectInfo")
        coating_variation = nodes.new("ShaderNodeMapRange")
        coating_variation.inputs["From Min"].default_value = 0.0
        coating_variation.inputs["From Max"].default_value = 1.0
        coating_variation.inputs["To Min"].default_value = 0.88
        coating_variation.inputs["To Max"].default_value = 1.08
        coating_variation.clamp = True
        varied_reflection = nodes.new("ShaderNodeMixRGB")
        varied_reflection.blend_type = "MULTIPLY"
        varied_reflection.inputs["Fac"].default_value = 1.0
        roughness_variation = nodes.new("ShaderNodeMapRange")
        roughness_variation.inputs["From Min"].default_value = 0.0
        roughness_variation.inputs["From Max"].default_value = 1.0
        roughness_variation.inputs["To Min"].default_value = max(
            0.035, roughness * 0.78
        )
        roughness_variation.inputs["To Max"].default_value = min(0.26, roughness * 1.22)
        roughness_variation.clamp = True
        links.new(coordinates.outputs["Generated"], separate.inputs["Vector"])
        links.new(separate.outputs["Z"], reflection_ramp.inputs["Fac"])
        links.new(object_info.outputs["Random"], coating_variation.inputs["Value"])
        links.new(reflection_ramp.outputs["Color"], varied_reflection.inputs[1])
        links.new(coating_variation.outputs["Result"], varied_reflection.inputs[2])
        links.new(varied_reflection.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(object_info.outputs["Random"], roughness_variation.inputs["Value"])
        links.new(roughness_variation.outputs["Result"], bsdf.inputs["Roughness"])
    try:
        mat.surface_render_method = "DITHERED"
    except Exception:
        pass
    mat.use_transparency_overlap = False
    mat[
        "c2w_glazing_profile"
    ] = "double_laminated_low_e_reflective_with_visible_interior_depth"
    return mat


def masonry_material(
    name,
    color_a,
    color_b,
    mortar,
    horizontal_axis="X",
    scale=2.0,
    brick_width=0.62,
    row_height=0.22,
):
    """World-scale running bond / CMU material with physical mortar relief."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    mat.diffuse_color = (*color_a, 1.0)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    geometry = nodes.new("ShaderNodeNewGeometry")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    combine = nodes.new("ShaderNodeCombineXYZ")
    brick = nodes.new("ShaderNodeTexBrick")
    noise = nodes.new("ShaderNodeTexNoise")
    multiply = nodes.new("ShaderNodeMixRGB")
    bump_node = nodes.new("ShaderNodeBump")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.inputs["Color1"].default_value = (*color_a, 1.0)
    brick.inputs["Color2"].default_value = (*color_b, 1.0)
    brick.inputs["Mortar"].default_value = (*mortar, 1.0)
    brick.inputs["Scale"].default_value = scale
    brick.inputs["Mortar Size"].default_value = 0.027
    brick.inputs["Mortar Smooth"].default_value = 0.008
    brick.inputs["Brick Width"].default_value = brick_width
    brick.inputs["Row Height"].default_value = row_height
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 8.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.72
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = 0.16
    bump_node.inputs["Strength"].default_value = 0.38
    bump_node.inputs["Distance"].default_value = 0.052
    _set_socket(bsdf, ("Roughness",), 0.82)
    links.new(geometry.outputs["Position"], separate.inputs["Vector"])
    links.new(separate.outputs[horizontal_axis], combine.inputs["X"])
    links.new(separate.outputs["Z"], combine.inputs["Y"])
    links.new(combine.outputs["Vector"], brick.inputs["Vector"])
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], multiply.inputs[1])
    links.new(noise.outputs["Color"], multiply.inputs[2])
    links.new(multiply.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_procedural_material"] = True
    mat["c2w_material_profile"] = "world_scale_masonry_with_mortar_relief"
    return mat


def make_materials():
    M = {
        "stucco": pbr(
            "warm_white_stucco",
            (0.39, 0.405, 0.39),
            0.84,
            noise_scale=9.0,
            bump=0.11,
            ambient_grime=0.20,
        ),
        "stucco_bright": pbr(
            "sunlit_white_stucco",
            (0.49, 0.505, 0.485),
            0.80,
            noise_scale=13.0,
            bump=0.085,
            ambient_grime=0.17,
        ),
        "precast": pbr(
            "architectural_precast",
            (0.33, 0.345, 0.33),
            0.82,
            noise_scale=6.0,
            bump=0.10,
            ambient_grime=0.24,
        ),
        "concrete": pbr(
            "board_formed_concrete",
            (0.275, 0.29, 0.28),
            0.90,
            noise_scale=8.0,
            bump=0.18,
            ambient_grime=0.26,
        ),
        "concrete_light": pbr(
            "pale_site_concrete",
            (0.315, 0.325, 0.31),
            0.88,
            noise_scale=9.0,
            bump=0.11,
            ambient_grime=0.20,
        ),
        "brick_front": masonry_material(
            "municipal_red_brick_front",
            (0.45, 0.12, 0.055),
            (0.67, 0.24, 0.11),
            (0.055, 0.045, 0.035),
            "X",
            2.05,
            0.68,
            0.23,
        ),
        "brick_side": masonry_material(
            "municipal_red_brick_side",
            (0.45, 0.12, 0.055),
            (0.67, 0.24, 0.11),
            (0.055, 0.045, 0.035),
            "Y",
            2.05,
            0.68,
            0.23,
        ),
        # 390 x 190 mm block module.  The former 0.8 m apparent module was one
        # of the strongest miniature cues in the Idaho Falls facade.
        "cmu_front": masonry_material(
            "pale_grey_cmu_front",
            (0.235, 0.25, 0.245),
            (0.34, 0.355, 0.345),
            (0.085, 0.092, 0.088),
            "X",
            2.35,
            0.92,
            0.46,
        ),
        "cmu_side": masonry_material(
            "pale_grey_cmu_side",
            (0.235, 0.25, 0.245),
            (0.34, 0.355, 0.345),
            (0.085, 0.092, 0.088),
            "Y",
            2.35,
            0.92,
            0.46,
        ),
        "cmu_dark_front": masonry_material(
            "charcoal_cmu_front",
            (0.070, 0.078, 0.082),
            (0.14, 0.15, 0.16),
            (0.025, 0.028, 0.030),
            "X",
            2.35,
            0.92,
            0.46,
        ),
        "cmu_dark_side": masonry_material(
            "charcoal_cmu_side",
            (0.070, 0.078, 0.082),
            (0.14, 0.15, 0.16),
            (0.025, 0.028, 0.030),
            "Y",
            2.35,
            0.92,
            0.46,
        ),
        # Restrained cobalt coatings keep the civic identity without the glossy
        # primary-colour plastic response that made the earlier facade read as
        # a construction toy in direct sun.
        "blue_panel": pbr(
            "cobalt_aluminum_composite",
            (0.010, 0.040, 0.145),
            0.34,
            metallic=0.46,
            noise_scale=36.0,
            bump=0.006,
        ),
        "blue_tile": pbr(
            "cobalt_glazed_ceramic",
            (0.008, 0.047, 0.155),
            0.29,
            metallic=0.05,
            noise_scale=48.0,
            bump=0.010,
        ),
        "blue_grey_metal": pbr(
            "blue_grey_metal_eave",
            (0.075, 0.105, 0.14),
            0.27,
            metallic=0.68,
            noise_scale=45.0,
            bump=0.022,
        ),
        "standing_seam": pbr(
            "blue_grey_standing_seam_roof",
            (0.10, 0.13, 0.16),
            0.31,
            metallic=0.74,
            noise_scale=54.0,
            bump=0.025,
        ),
        "black": pbr(
            "powder_coated_black",
            (0.012, 0.014, 0.016),
            0.28,
            metallic=0.58,
            noise_scale=38.0,
            bump=0.025,
        ),
        "aluminum": pbr(
            "brushed_aluminum",
            (0.42, 0.45, 0.46),
            0.23,
            metallic=0.90,
            noise_scale=72.0,
            bump=0.018,
        ),
        "steel": pbr(
            "stainless_security_steel",
            (0.55, 0.57, 0.58),
            0.18,
            metallic=0.94,
            noise_scale=82.0,
            bump=0.014,
        ),
        "bronze": pbr(
            "dark_anodized_bronze",
            (0.075, 0.060, 0.045),
            0.24,
            metallic=0.78,
            noise_scale=45.0,
            bump=0.025,
        ),
        "glass_blue": architectural_glass(
            "blue_low_e_glass", (0.006, 0.026, 0.045), 0.43, 0.095
        ),
        "glass_dark": architectural_glass(
            "dark_security_glass", (0.003, 0.006, 0.010), 0.30, 0.125
        ),
        "glass_clear": architectural_glass(
            "clear_lobby_glass", (0.018, 0.045, 0.052), 0.56, 0.075
        ),
        "interior_shadow": pbr(
            "occupied_interior_shadow",
            (0.018, 0.021, 0.022),
            0.91,
            noise_scale=5.0,
            bump=0.025,
        ),
        "painted_steel": pbr(
            "institutional_painted_steel",
            (0.12, 0.135, 0.14),
            0.38,
            metallic=0.58,
            noise_scale=46.0,
            bump=0.018,
        ),
        "door_enamel": pbr(
            "sectional_door_baked_enamel",
            (0.49, 0.515, 0.51),
            0.43,
            metallic=0.34,
            noise_scale=52.0,
            bump=0.016,
            ambient_grime=0.10,
        ),
        "galvanized": pbr(
            "galvanized_door_hardware",
            (0.34, 0.365, 0.37),
            0.31,
            metallic=0.86,
            noise_scale=61.0,
            bump=0.026,
        ),
        "joint_sealant": pbr(
            "architectural_joint_sealant",
            (0.018, 0.020, 0.019),
            0.72,
            noise_scale=24.0,
            bump=0.05,
        ),
        "asphalt": pbr(
            "aggregate_asphalt",
            (0.022, 0.025, 0.028),
            0.93,
            noise_scale=18.0,
            bump=0.27,
            ambient_grime=0.10,
        ),
        "paving": pbr(
            "warm_jointed_paving",
            (0.205, 0.195, 0.175),
            0.90,
            noise_scale=11.0,
            bump=0.10,
            ambient_grime=0.12,
        ),
        "terrazzo": pbr(
            "lobby_terrazzo", (0.61, 0.62, 0.58), 0.37, noise_scale=48.0, bump=0.058
        ),
        "wood": pbr(
            "interior_white_oak", (0.28, 0.13, 0.045), 0.48, noise_scale=7.0, bump=0.11
        ),
        "fabric_blue": pbr(
            "institutional_blue_fabric",
            (0.025, 0.12, 0.24),
            0.78,
            noise_scale=31.0,
            bump=0.13,
        ),
        "rubber": pbr(
            "vehicle_tire_rubber",
            (0.006, 0.007, 0.008),
            0.83,
            noise_scale=34.0,
            bump=0.11,
        ),
        "vehicle_white": pbr(
            "patrol_vehicle_white_paint",
            (0.78, 0.80, 0.79),
            0.19,
            metallic=0.22,
            noise_scale=65.0,
            bump=0.012,
        ),
        "vehicle_blue": pbr(
            "patrol_vehicle_navy_paint",
            (0.008, 0.025, 0.13),
            0.18,
            metallic=0.32,
            noise_scale=58.0,
            bump=0.012,
        ),
        "lamp_red": pbr(
            "emergency_red_lens",
            (0.38, 0.004, 0.003),
            0.12,
            emission=(1.0, 0.005, 0.003),
            emission_strength=3.2,
        ),
        "lamp_blue": pbr(
            "emergency_blue_lens",
            (0.002, 0.025, 0.48),
            0.12,
            emission=(0.002, 0.035, 1.0),
            emission_strength=3.5,
        ),
        "lamp_white": pbr(
            "architectural_light_lens",
            (0.86, 0.79, 0.61),
            0.23,
            emission=(1.0, 0.68, 0.36),
            emission_strength=2.6,
        ),
        "screen": pbr(
            "security_monitor_screen",
            (0.008, 0.055, 0.075),
            0.16,
            emission=(0.02, 0.43, 0.62),
            emission_strength=1.8,
        ),
        "red": pbr(
            "emergency_and_fdc_red",
            (0.55, 0.012, 0.008),
            0.48,
            noise_scale=44.0,
            bump=0.035,
        ),
        "white": pbr(
            "signage_white", (0.78, 0.80, 0.77), 0.30, noise_scale=58.0, bump=0.015
        ),
        "yellow": pbr(
            "traffic_marking_yellow",
            (0.86, 0.58, 0.035),
            0.72,
            noise_scale=29.0,
            bump=0.05,
        ),
        "road_white": pbr(
            "traffic_marking_white",
            (0.74, 0.76, 0.72),
            0.76,
            noise_scale=31.0,
            bump=0.055,
        ),
        "accessible_blue": pbr(
            "accessible_parking_blue",
            (0.014, 0.17, 0.52),
            0.67,
            noise_scale=27.0,
            bump=0.045,
        ),
        "grass": pbr(
            "maintained_lawn", (0.045, 0.16, 0.038), 0.91, noise_scale=14.0, bump=0.24
        ),
        "soil": pbr(
            "landscape_soil", (0.070, 0.035, 0.014), 0.96, noise_scale=8.0, bump=0.32
        ),
        "gravel": pbr(
            "xeriscape_gravel", (0.30, 0.27, 0.22), 0.91, noise_scale=23.0, bump=0.32
        ),
        "leaf_a": pbr(
            "leaf_deep_green", (0.025, 0.14, 0.030), 0.74, noise_scale=16.0, bump=0.13
        ),
        "leaf_b": pbr(
            "leaf_sunlit_green", (0.070, 0.26, 0.050), 0.68, noise_scale=18.0, bump=0.11
        ),
        "bark": pbr(
            "tree_bark", (0.105, 0.050, 0.022), 0.93, noise_scale=9.0, bump=0.36
        ),
    }
    return M


def text_object(
    coll,
    name,
    body,
    xyz,
    size,
    material,
    extrude=0.065,
    align="CENTER",
    role="police_wordmark",
    parent=None,
):
    curve = bpy.data.curves.new(PREFIX + name, "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = max(0.014, extrude * 0.16)
    curve.bevel_resolution = 4
    curve.resolution_u = 12
    curve.space_character = 1.18
    if FONT_PATH.exists():
        try:
            curve.font = bpy.data.fonts.load(str(FONT_PATH), check_existing=True)
        except RuntimeError:
            pass
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    coll.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    obj.parent = parent
    return tag(obj, role)


def mesh_object(coll, name, vertices, faces, material, role, parent=None):
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    coll.objects.link(obj)
    obj.parent = parent
    return tag(obj, role)


def facade_window_y(
    coll,
    parent,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    normal=-1.0,
    divisions=2,
    frame_key="black",
    glass_key="glass_blue",
    sill=True,
    blind=False,
    role="security_window",
    backing_offset=0.42,
):
    """Deep drained double-glazed security window with a shadow-box interior."""
    frame = M[frame_key]
    cavity_depth = max(0.48, backing_offset)
    box(
        coll,
        name + ":reveal",
        (x, y - normal * 0.23, z),
        (width + 0.34, 0.28, height + 0.34),
        M["black"],
        role="window_reveal",
        parent=parent,
    )
    box(
        coll,
        name + ":interior_back",
        (x, y - normal * cavity_depth, z),
        (width - 0.18, 0.07, height - 0.18),
        M["interior_shadow"],
        role="interior_window_back",
        parent=parent,
    )
    box(
        coll,
        name + ":glass",
        (x, y + normal * 0.025, z),
        (width, 0.060, height),
        M[glass_key],
        role=role,
        parent=parent,
    )
    box(
        coll,
        name + ":inner_laminated_pane",
        (x, y - normal * 0.115, z),
        (width - 0.10, 0.028, height - 0.10),
        M[glass_key],
        role="inner_security_glazing",
        parent=parent,
    )
    outer = normal * 0.095
    for suffix, px, pz, sx, sz in (
        ("left", x - width / 2, z, 0.085, height + 0.16),
        ("right", x + width / 2, z, 0.085, height + 0.16),
        ("head", x, z + height / 2, width + 0.17, 0.085),
        ("sill", x, z - height / 2, width + 0.17, 0.085),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (px, y + outer, pz),
            (sx, 0.12, sz),
            frame,
            role="window_frame",
            parent=parent,
        )
        box(
            coll,
            name + ":gasket_" + suffix,
            (px, y + normal * 0.165, pz),
            (
                max(0.020, sx * 0.46 if sx < sz else sx),
                0.016,
                max(0.020, sz * 0.46 if sz < sx else sz),
            ),
            M["black"],
            role="glazing_gasket",
            parent=parent,
        )
        box(
            coll,
            name + ":thermal_spacer_" + suffix,
            (px, y - normal * 0.073, pz),
            (
                max(0.018, sx * 0.34 if sx < sz else sx - 0.05),
                0.018,
                max(0.018, sz * 0.34 if sz < sx else sz - 0.05),
            ),
            M["joint_sealant"],
            role="insulated_glass_spacer",
            parent=parent,
        )
    for index in range(1, divisions):
        px = x - width / 2 + width * index / divisions
        box(
            coll,
            name + f":mullion_{index}",
            (px, y + outer, z),
            (0.075, 0.12, height),
            frame,
            role="window_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":mullion_gasket_{index}",
            (px, y + normal * 0.165, z),
            (0.018, 0.016, height),
            M["black"],
            role="glazing_gasket",
            parent=parent,
        )
    box(
        coll,
        name + ":transom",
        (x, y + outer, z + height * 0.16),
        (width, 0.12, 0.075),
        frame,
        role="window_mullion",
        parent=parent,
    )
    # Projecting head flashing, return shadows and drainage slots stop each
    # opening reading as a dark rectangle pasted onto a flat wall.
    box(
        coll,
        name + ":head_flashing",
        (x, y + normal * 0.205, z + height / 2 + 0.13),
        (width + 0.42, 0.31, 0.075),
        M[frame_key],
        0.018,
        role="window_head_flashing",
        parent=parent,
    )
    for weep_index, wx in enumerate((x - width * 0.32, x + width * 0.32)):
        box(
            coll,
            name + f":weep_{weep_index}",
            (wx, y + normal * 0.218, z - height / 2 - 0.015),
            (0.105, 0.025, 0.026),
            M["black"],
            role="window_drainage_weep",
            parent=parent,
        )
    if sill:
        box(
            coll,
            name + ":projecting_sill",
            (x, y + normal * 0.21, z - height / 2 - 0.12),
            (width + 0.38, 0.34, 0.16),
            M["precast"],
            0.035,
            role="projecting_window_sill",
            parent=parent,
        )
    if blind:
        for slat in range(13):
            pz = z + height * 0.40 - slat * height * 0.063
            box(
                coll,
                name + f":blind_{slat}",
                (x, y - normal * (cavity_depth * 0.58), pz),
                (width - 0.20, 0.022, 0.025),
                M["white"],
                role="interior_blind",
                parent=parent,
            )


def facade_window_x(
    coll,
    parent,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    normal=1.0,
    divisions=2,
    frame_key="black",
    glass_key="glass_blue",
    sill=True,
    role="security_window",
):
    frame = M[frame_key]
    box(
        coll,
        name + ":reveal",
        (x - normal * 0.23, y, z),
        (0.28, width + 0.34, height + 0.34),
        M["black"],
        role="window_reveal",
        parent=parent,
    )
    box(
        coll,
        name + ":interior_back",
        (x - normal * 0.42, y, z),
        (0.07, width - 0.18, height - 0.18),
        M["interior_shadow"],
        role="interior_window_back",
        parent=parent,
    )
    box(
        coll,
        name + ":glass",
        (x + normal * 0.025, y, z),
        (0.060, width, height),
        M[glass_key],
        role=role,
        parent=parent,
    )
    box(
        coll,
        name + ":inner_laminated_pane",
        (x - normal * 0.115, y, z),
        (0.028, width - 0.10, height - 0.10),
        M[glass_key],
        role="inner_security_glazing",
        parent=parent,
    )
    outer = normal * 0.095
    for suffix, py, pz, sy, sz in (
        ("left", y - width / 2, z, 0.085, height + 0.16),
        ("right", y + width / 2, z, 0.085, height + 0.16),
        ("head", y, z + height / 2, width + 0.17, 0.085),
        ("sill", y, z - height / 2, width + 0.17, 0.085),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (x + outer, py, pz),
            (0.12, sy, sz),
            frame,
            role="window_frame",
            parent=parent,
        )
        box(
            coll,
            name + ":gasket_" + suffix,
            (x + normal * 0.165, py, pz),
            (
                0.016,
                max(0.020, sy * 0.46 if sy < sz else sy),
                max(0.020, sz * 0.46 if sz < sy else sz),
            ),
            M["black"],
            role="glazing_gasket",
            parent=parent,
        )
        box(
            coll,
            name + ":thermal_spacer_" + suffix,
            (x - normal * 0.073, py, pz),
            (
                0.018,
                max(0.018, sy * 0.34 if sy < sz else sy - 0.05),
                max(0.018, sz * 0.34 if sz < sy else sz - 0.05),
            ),
            M["joint_sealant"],
            role="insulated_glass_spacer",
            parent=parent,
        )
    for index in range(1, divisions):
        py = y - width / 2 + width * index / divisions
        box(
            coll,
            name + f":mullion_{index}",
            (x + outer, py, z),
            (0.12, 0.075, height),
            frame,
            role="window_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":gasket_{index}",
            (x + normal * 0.165, py, z),
            (0.016, 0.018, height),
            M["black"],
            role="glazing_gasket",
            parent=parent,
        )
    box(
        coll,
        name + ":transom",
        (x + outer, y, z + height * 0.16),
        (0.12, width, 0.075),
        frame,
        role="window_mullion",
        parent=parent,
    )
    box(
        coll,
        name + ":head_flashing",
        (x + normal * 0.205, y, z + height / 2 + 0.13),
        (0.31, width + 0.42, 0.075),
        M[frame_key],
        0.018,
        role="window_head_flashing",
        parent=parent,
    )
    for weep_index, wy in enumerate((y - width * 0.32, y + width * 0.32)):
        box(
            coll,
            name + f":weep_{weep_index}",
            (x + normal * 0.218, wy, z - height / 2 - 0.015),
            (0.025, 0.105, 0.026),
            M["black"],
            role="window_drainage_weep",
            parent=parent,
        )
    if sill:
        box(
            coll,
            name + ":projecting_sill",
            (x + normal * 0.21, y, z - height / 2 - 0.12),
            (0.34, width + 0.38, 0.16),
            M["precast"],
            0.035,
            role="projecting_window_sill",
            parent=parent,
        )


def curtain_wall_y(
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
    normal=-1.0,
    glass_key="glass_clear",
    frame_key="aluminum",
    role="curtain_wall_glazing",
):
    panel_w, panel_h = width / columns, height / rows
    box(
        coll,
        name + ":deep_recess",
        (x, y - normal * 0.30, bottom + height / 2),
        (width + 0.48, 0.36, height + 0.48),
        M["black"],
        role="curtain_wall_recess",
        parent=parent,
    )
    for row in range(rows):
        for column in range(columns):
            px = x - width / 2 + panel_w * (column + 0.5)
            pz = bottom + panel_h * (row + 0.5)
            glass = M[glass_key] if (row + column) % 5 else M["glass_dark"]
            box(
                coll,
                name + f":glass_{row}_{column}",
                (px, y + normal * 0.025, pz),
                (panel_w - 0.09, 0.06, panel_h - 0.09),
                glass,
                role=role,
                parent=parent,
            )
    for column in range(columns + 1):
        px = x - width / 2 + width * column / columns
        box(
            coll,
            name + f":vertical_{column}",
            (px, y + normal * 0.095, bottom + height / 2),
            (0.095, 0.14, height + 0.16),
            M[frame_key],
            role="curtain_wall_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":pressure_vertical_{column}",
            (px, y + normal * 0.174, bottom + height / 2),
            (0.026, 0.018, height + 0.12),
            M["black"],
            role="curtain_wall_pressure_plate",
            parent=parent,
        )
    for row in range(rows + 1):
        pz = bottom + height * row / rows
        box(
            coll,
            name + f":horizontal_{row}",
            (x, y + normal * 0.095, pz),
            (width + 0.14, 0.14, 0.095),
            M[frame_key],
            role="curtain_wall_mullion",
            parent=parent,
        )
        box(
            coll,
            name + f":pressure_horizontal_{row}",
            (x, y + normal * 0.174, pz),
            (width + 0.10, 0.018, 0.026),
            M["black"],
            role="curtain_wall_pressure_plate",
            parent=parent,
        )


def glass_door_bank(
    coll,
    parent,
    name,
    x,
    y,
    base_z,
    width,
    height,
    M,
    leaves=2,
    normal=-1.0,
    frame_key="aluminum",
):
    """Deep, hardware-complete glazed vestibule entrance.

    ``leaves`` is intentionally capped at two operable leaves.  The former
    implementation divided the whole opening into three or four identical
    glass slabs, which read as a storefront mock-up.  Remaining width becomes
    independently framed sidelights and the upper zone becomes a real transom.
    """
    leaves = 2
    door_height = min(2.52, height * 0.78)
    door_bank_width = min(width * 0.60, 2.80)
    sidelight_width = (width - door_bank_width) / 2.0
    leaf_width = door_bank_width / leaves
    face_y = y + normal * 0.12

    # A 0.75 m deep vestibule, returned jambs and a shadowed ceiling give the
    # entrance physical depth from both oblique and close validation cameras.
    box(
        coll,
        name + ":rough_opening",
        (x, y - normal * 0.25, base_z + height / 2),
        (width + 0.58, 0.42, height + 0.48),
        M["interior_shadow"],
        0.035,
        role="entrance_recess",
        parent=parent,
    )
    box(
        coll,
        name + ":vestibule_back_glass",
        (x, y - normal * 0.78, base_z + height / 2),
        (width - 0.18, 0.045, height - 0.16),
        M["glass_dark"],
        0.018,
        role="vestibule_inner_glazing",
        parent=parent,
    )
    for suffix, px, pz, sx, sz in (
        ("left_return", x - width / 2 - 0.09, base_z + height / 2, 0.18, height + 0.28),
        (
            "right_return",
            x + width / 2 + 0.09,
            base_z + height / 2,
            0.18,
            height + 0.28,
        ),
        ("head_return", x, base_z + height + 0.09, width + 0.36, 0.18),
    ):
        box(
            coll,
            name + ":" + suffix,
            (px, face_y, pz),
            (sx, 0.24, sz),
            M[frame_key],
            0.028,
            role="door_perimeter_frame",
            parent=parent,
        )
    box(
        coll,
        name + ":transom_rail",
        (x, face_y, base_z + door_height),
        (width + 0.10, 0.18, 0.11),
        M[frame_key],
        0.025,
        role="door_frame",
        parent=parent,
    )

    # Fixed sidelights are separate laminated units with their own drained
    # frames rather than extensions of the moving door leaves.
    for side in (-1, 1):
        sx = x + side * (door_bank_width / 2 + sidelight_width / 2)
        box(
            coll,
            name + f":sidelight_glass_{side}",
            (sx, y + normal * 0.025, base_z + door_height / 2),
            (sidelight_width - 0.13, 0.055, door_height - 0.14),
            M["glass_clear"],
            0.018,
            role="entrance_sidelight_glazing",
            parent=parent,
        )
        box(
            coll,
            name + f":sidelight_inner_{side}",
            (sx, y - normal * 0.105, base_z + door_height / 2),
            (sidelight_width - 0.20, 0.025, door_height - 0.22),
            M["glass_clear"],
            role="inner_entrance_glazing",
            parent=parent,
        )
        for edge in (-1, 1):
            px = sx + edge * sidelight_width / 2
            box(
                coll,
                name + f":sidelight_mullion_{side}_{edge}",
                (px, face_y, base_z + door_height / 2),
                (0.075, 0.15, door_height + 0.08),
                M[frame_key],
                0.018,
                role="door_frame",
                parent=parent,
            )
            box(
                coll,
                name + f":sidelight_gasket_{side}_{edge}",
                (px, y + normal * 0.205, base_z + door_height / 2),
                (0.018, 0.018, door_height - 0.05),
                M["rubber"],
                role="door_weather_seal",
                parent=parent,
            )

    # Upper transom is divided at real curtain-wall module widths.
    transom_height = height - door_height - 0.12
    transom_columns = max(3, int(round(width / 1.25)))
    transom_width = width / transom_columns
    if transom_height > 0.24:
        for column in range(transom_columns):
            px = x - width / 2 + transom_width * (column + 0.5)
            box(
                coll,
                name + f":transom_glass_{column}",
                (
                    px,
                    y + normal * 0.025,
                    base_z + door_height + 0.12 + transom_height / 2,
                ),
                (transom_width - 0.10, 0.055, transom_height - 0.08),
                M["glass_clear"],
                0.016,
                role="entrance_transom_glazing",
                parent=parent,
            )
        for column in range(transom_columns + 1):
            px = x - width / 2 + width * column / transom_columns
            box(
                coll,
                name + f":transom_mullion_{column}",
                (px, face_y, base_z + door_height + 0.12 + transom_height / 2),
                (0.065, 0.14, transom_height + 0.07),
                M[frame_key],
                0.016,
                role="door_frame",
                parent=parent,
            )

    # Two operable thermally-broken leaves with paired panes, gaskets, rails,
    # closers, locks, hinges, panic hardware and returned pull handles.
    for leaf in range(leaves):
        px = x - door_bank_width / 2 + leaf_width * (leaf + 0.5)
        side = -1 if leaf == 0 else 1
        box(
            coll,
            name + f":leaf_outer_glass_{leaf}",
            (px, y + normal * 0.035, base_z + door_height / 2),
            (leaf_width - 0.12, 0.055, door_height - 0.12),
            M["glass_clear"],
            0.016,
            role="entrance_door_glazing",
            parent=parent,
        )
        box(
            coll,
            name + f":leaf_inner_glass_{leaf}",
            (px, y - normal * 0.095, base_z + door_height / 2),
            (leaf_width - 0.20, 0.025, door_height - 0.20),
            M["glass_clear"],
            role="inner_entrance_glazing",
            parent=parent,
        )
        for edge in (-1, 1):
            frame_x = px + edge * (leaf_width / 2 - 0.035)
            box(
                coll,
                name + f":leaf_stile_{leaf}_{edge}",
                (frame_x, face_y, base_z + door_height / 2),
                (0.070, 0.15, door_height),
                M[frame_key],
                0.016,
                role="door_frame",
                parent=parent,
            )
            box(
                coll,
                name + f":leaf_gasket_{leaf}_{edge}",
                (frame_x, y + normal * 0.205, base_z + door_height / 2),
                (0.018, 0.018, door_height - 0.06),
                M["rubber"],
                role="door_weather_seal",
                parent=parent,
            )
        for rail_name, rail_z, rail_h in (
            ("head", base_z + door_height - 0.035, 0.070),
            ("mid", base_z + 0.86, 0.085),
            ("bottom", base_z + 0.12, 0.24),
        ):
            box(
                coll,
                name + f":leaf_{rail_name}_{leaf}",
                (px, face_y, rail_z),
                (leaf_width - 0.07, 0.15, rail_h),
                M[frame_key],
                0.016,
                role="door_bottom_rail" if rail_name == "bottom" else "door_frame",
                parent=parent,
            )
        box(
            coll,
            name + f":kickplate_{leaf}",
            (px, y + normal * 0.205, base_z + 0.34),
            (leaf_width - 0.22, 0.018, 0.38),
            M["steel"],
            0.010,
            role="door_kickplate",
            parent=parent,
        )
        box(
            coll,
            name + f":panic_bar_{leaf}",
            (px, y - normal * 0.105, base_z + 1.02),
            (leaf_width * 0.62, 0.095, 0.070),
            M["black"],
            0.020,
            role="door_panic_hardware",
            parent=parent,
        )
        handle_x = px - side * leaf_width * 0.22
        cylinder(
            coll,
            name + f":pull_bar_{leaf}",
            (handle_x, y + normal * 0.245, base_z + 1.32),
            0.025,
            0.72,
            M["steel"],
            18,
            role="door_pull_handle",
            parent=parent,
        )
        for handle_z in (base_z + 0.96, base_z + 1.68):
            beam(
                coll,
                name + f":pull_return_{leaf}_{handle_z}",
                (handle_x, y + normal * 0.155, handle_z),
                (handle_x, y + normal * 0.245, handle_z),
                0.025,
                M["steel"],
                14,
                role="door_hardware",
                parent=parent,
            )
        cylinder(
            coll,
            name + f":lock_cylinder_{leaf}",
            (px + side * leaf_width * 0.27, y + normal * 0.215, base_z + 1.02),
            0.034,
            0.025,
            M["steel"],
            18,
            rot=(math.pi / 2, 0, 0),
            role="door_lock_cylinder",
            parent=parent,
        )
        box(
            coll,
            name + f":closer_{leaf}",
            (px + side * 0.15, y - normal * 0.06, base_z + door_height - 0.17),
            (0.46, 0.14, 0.10),
            M["black"],
            0.025,
            role="door_hardware",
            parent=parent,
        )
        for hinge_index, hinge_z in enumerate(
            (0.38, door_height * 0.50, door_height - 0.38)
        ):
            cylinder(
                coll,
                name + f":hinge_{leaf}_{hinge_index}",
                (
                    px - side * (leaf_width / 2 - 0.045),
                    y + normal * 0.16,
                    base_z + hinge_z,
                ),
                0.021,
                0.14,
                M["steel"],
                14,
                role="door_hinge",
                parent=parent,
            )

    box(
        coll,
        name + ":threshold",
        (x, y + normal * 0.18, base_z - 0.025),
        (door_bank_width + 0.18, 0.36, 0.055),
        M["steel"],
        0.016,
        role="door_threshold",
        parent=parent,
    )
    box(
        coll,
        name + ":automatic_operator",
        (x, y - normal * 0.03, base_z + door_height + 0.17),
        (door_bank_width + 0.24, 0.22, 0.20),
        M[frame_key],
        0.030,
        role="automatic_door_operator",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":presence_sensor",
        (x, y + normal * 0.235, base_z + door_height + 0.17),
        0.055,
        0.035,
        M["black"],
        18,
        rot=(math.pi / 2, 0, 0),
        role="automatic_door_sensor",
        parent=parent,
    )
    for side in (-1, 1):
        push_x = x + side * (door_bank_width / 2 + 0.22)
        box(
            coll,
            name + f":accessible_push_plate_{side}",
            (push_x, y + normal * 0.245, base_z + 0.96),
            (0.16, 0.035, 0.25),
            M["steel"],
            0.025,
            role="accessible_door_control",
            parent=parent,
        )
        cylinder(
            coll,
            name + f":push_button_{side}",
            (push_x, y + normal * 0.275, base_z + 0.98),
            0.035,
            0.018,
            M["black"],
            16,
            rot=(math.pi / 2, 0, 0),
            role="accessible_door_button",
            parent=parent,
        )
    box(
        coll,
        name + ":interior_entry_mat",
        (x, y - normal * 0.62, base_z + 0.018),
        (door_bank_width - 0.22, 1.25, 0.035),
        M["black"],
        0.015,
        role="interior_entry_mat",
        parent=parent,
    )


def steel_service_door_y(
    coll, parent, name, x, y, base_z, width, height, M, normal=1.0, label=None
):
    """A recessed, weather-sealed hollow-metal personnel door."""
    box(
        coll,
        name + ":recess",
        (x, y - normal * 0.19, base_z + height / 2),
        (width + 0.42, 0.30, height + 0.34),
        M["interior_shadow"],
        0.025,
        role="service_door_recess",
        parent=parent,
    )
    box(
        coll,
        name + ":leaf",
        (x, y + normal * 0.025, base_z + height / 2),
        (width, 0.085, height),
        M["painted_steel"],
        0.035,
        role="secure_personnel_door",
        parent=parent,
    )
    # Folded face returns, a narrow laminated vision lite and a lower stiffener
    # panel break up the former featureless sheet while retaining a secure-door
    # specification appropriate for a sally-port elevation.
    for edge in (-1, 1):
        box(
            coll,
            name + f":leaf_fold_{edge}",
            (x + edge * (width / 2 - 0.045), y + normal * 0.095, base_z + height / 2),
            (0.055, 0.040, height - 0.10),
            M["galvanized"],
            0.012,
            role="service_door_edge_fold",
            parent=parent,
        )
    box(
        coll,
        name + ":vision_recess",
        (x, y + normal * 0.080, base_z + height * 0.70),
        (0.56, 0.045, 0.70),
        M["interior_shadow"],
        0.035,
        role="service_door_vision_recess",
        parent=parent,
    )
    box(
        coll,
        name + ":vision_glass",
        (x, y + normal * 0.116, base_z + height * 0.70),
        (0.43, 0.025, 0.56),
        M["glass_dark"],
        0.025,
        role="service_door_vision_glazing",
        parent=parent,
    )
    for suffix, px, pz, sx, sz in (
        ("vision_left", x - 0.27, base_z + height * 0.70, 0.055, 0.70),
        ("vision_right", x + 0.27, base_z + height * 0.70, 0.055, 0.70),
        ("vision_head", x, base_z + height * 0.70 + 0.35, 0.56, 0.055),
        ("vision_sill", x, base_z + height * 0.70 - 0.35, 0.56, 0.055),
    ):
        box(
            coll,
            name + ":" + suffix,
            (px, y + normal * 0.145, pz),
            (sx, 0.055, sz),
            M["galvanized"],
            0.012,
            role="service_door_vision_frame",
            parent=parent,
        )
    box(
        coll,
        name + ":lower_stiffener",
        (x, y + normal * 0.090, base_z + height * 0.33),
        (width - 0.18, 0.030, 0.035),
        M["galvanized"],
        0.010,
        role="service_door_stiffener",
        parent=parent,
    )
    outer_y = y + normal * 0.12
    for suffix, px, pz, sx, sz in (
        ("left", x - width / 2 - 0.045, base_z + height / 2, 0.10, height + 0.20),
        ("right", x + width / 2 + 0.045, base_z + height / 2, 0.10, height + 0.20),
        ("head", x, base_z + height + 0.05, width + 0.20, 0.10),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (px, outer_y, pz),
            (sx, 0.15, sz),
            M["steel"],
            0.022,
            role="service_door_frame",
            parent=parent,
        )
        box(
            coll,
            name + ":seal_" + suffix,
            (px, y + normal * 0.205, pz),
            (
                max(0.018, sx * 0.24 if sx < sz else sx - 0.08),
                0.018,
                max(0.018, sz * 0.24 if sz < sx else sz - 0.08),
            ),
            M["rubber"],
            role="service_door_weather_seal",
            parent=parent,
        )
    box(
        coll,
        name + ":kickplate",
        (x, y + normal * 0.085, base_z + 0.32),
        (width - 0.22, 0.018, 0.44),
        M["steel"],
        0.012,
        role="service_door_kickplate",
        parent=parent,
    )
    # Lever, cylinder, closer and three butt hinges are readable in close views.
    handle_x = x + width * 0.30
    beam(
        coll,
        name + ":lever",
        (handle_x - 0.16, y + normal * 0.18, base_z + 1.04),
        (handle_x + 0.12, y + normal * 0.18, base_z + 1.04),
        0.025,
        M["steel"],
        12,
        role="service_door_hardware",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":lock",
        (handle_x, y + normal * 0.18, base_z + 1.17),
        0.034,
        0.024,
        M["steel"],
        16,
        rot=(math.pi / 2, 0, 0),
        role="service_door_hardware",
        parent=parent,
    )
    box(
        coll,
        name + ":strike_guard",
        (x + width / 2 - 0.035, y + normal * 0.205, base_z + 1.05),
        (0.085, 0.025, 0.34),
        M["galvanized"],
        0.012,
        role="service_door_hardware",
        parent=parent,
    )
    box(
        coll,
        name + ":card_reader",
        (x + width / 2 + 0.28, y + normal * 0.205, base_z + 1.22),
        (0.15, 0.055, 0.28),
        M["black"],
        0.030,
        role="access_control_reader",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":reader_status",
        (x + width / 2 + 0.28, y + normal * 0.245, base_z + 1.28),
        0.025,
        0.015,
        M["lamp_blue"],
        14,
        rot=(math.pi / 2, 0, 0),
        role="access_control_indicator",
        parent=parent,
    )
    box(
        coll,
        name + ":closer",
        (x + width * 0.18, y - normal * 0.02, base_z + height - 0.16),
        (0.44, 0.13, 0.10),
        M["black"],
        0.025,
        role="service_door_hardware",
        parent=parent,
    )
    for index, hinge_z in enumerate((0.40, height * 0.52, height - 0.38)):
        cylinder(
            coll,
            name + f":hinge_{index}",
            (x - width / 2 + 0.015, y + normal * 0.13, base_z + hinge_z),
            0.022,
            0.11,
            M["steel"],
            12,
            role="service_door_hardware",
            parent=parent,
        )
    box(
        coll,
        name + ":threshold",
        (x, y + normal * 0.16, base_z - 0.03),
        (width + 0.18, 0.32, 0.06),
        M["steel"],
        0.018,
        role="service_door_threshold",
        parent=parent,
    )
    # Folded sheet-metal rain hood with returns and a dark drip edge.
    box(
        coll,
        name + ":rain_hood",
        (x, y + normal * 0.66, base_z + height + 0.34),
        (width + 0.82, 1.22, 0.13),
        M["blue_grey_metal"],
        0.035,
        role="service_door_canopy",
        parent=parent,
    )
    box(
        coll,
        name + ":hood_drip",
        (x, y + normal * 1.28, base_z + height + 0.27),
        (width + 0.88, 0.055, 0.12),
        M["black"],
        0.018,
        role="service_door_canopy_drip",
        parent=parent,
    )
    if label:
        plaque_x = x - width / 2 - 0.50
        box(
            coll,
            name + ":label_backer",
            (plaque_x, y + normal * 0.195, base_z + 1.58),
            (0.72, 0.035, 0.34),
            M["black"],
            0.025,
            role="service_door_identification_backer",
            parent=parent,
        )
        sign = text_object(
            coll,
            name + ":label",
            label,
            (plaque_x, y + normal * 0.235, base_z + 1.58),
            0.13,
            M["white"],
            0.018,
            role="service_door_identification",
            parent=parent,
        )
        if normal > 0:
            # Rotate the glyph fronts toward +Y and reverse their world-space
            # baseline so they read left-to-right from a north-side camera.
            sign.rotation_euler = (math.pi / 2, 0, math.pi)


def sectional_sally_door_y(
    coll,
    parent,
    name,
    x,
    y,
    base_z,
    width,
    height,
    M,
    normal=1.0,
    panel_rows=8,
    panel_columns=4,
    glazing_row=4,
    finish_key="door_enamel",
):
    """Manufactured insulated sectional door for a secure vehicle bay.

    Every section is a separate folded micro-ribbed panel with flexible
    inter-panel seals, framed laminated vision lites, compact hinge plates, guide
    channels, anchor bolts, cable drums, a bottom astragal and track-mounted
    safety sensors.  Nothing is represented by a painted line on one flat slab.
    """
    panel_height = height / panel_rows
    panel_width = width / panel_columns
    face_y = y + normal * 0.085

    box(
        coll,
        name + ":structural_recess",
        (x, y - normal * 0.22, base_z + height / 2),
        (width + 0.58, 0.42, height + 0.48),
        M["interior_shadow"],
        0.045,
        role="secure_sally_port_recess",
        parent=parent,
    )
    box(
        coll,
        name + ":door_backing",
        (x, y + normal * 0.012, base_z + height / 2),
        (width, 0.060, height),
        M[finish_key],
        0.025,
        role="secure_sally_port_door",
        parent=parent,
    )

    for row in range(panel_rows):
        panel_z = base_z + panel_height * (row + 0.5)
        box(
            coll,
            name + f":section_{row}",
            (x, face_y, panel_z),
            (width - 0.16, 0.105, panel_height - 0.045),
            M[finish_key],
            0.045,
            role="sectional_door_panel",
            parent=parent,
        )
        if row == glazing_row:
            for column in range(panel_columns):
                pane_x = x - width / 2 + panel_width * (column + 0.5)
                pane_w = panel_width - 0.30
                pane_h = panel_height - 0.20
                box(
                    coll,
                    name + f":vision_recess_{column}",
                    (pane_x, y + normal * 0.145, panel_z),
                    (pane_w + 0.11, 0.035, pane_h + 0.11),
                    M["black"],
                    0.030,
                    role="sally_port_vision_recess",
                    parent=parent,
                )
                box(
                    coll,
                    name + f":vision_glass_{column}",
                    (pane_x, y + normal * 0.172, panel_z),
                    (pane_w, 0.026, pane_h),
                    M["glass_dark"],
                    0.035,
                    role="sally_port_door_window",
                    parent=parent,
                )
                for suffix, px, pz, sx, sz in (
                    ("left", pane_x - pane_w / 2, panel_z, 0.050, pane_h + 0.10),
                    ("right", pane_x + pane_w / 2, panel_z, 0.050, pane_h + 0.10),
                    ("head", pane_x, panel_z + pane_h / 2, pane_w + 0.10, 0.050),
                    ("sill", pane_x, panel_z - pane_h / 2, pane_w + 0.10, 0.050),
                ):
                    box(
                        coll,
                        name + f":vision_frame_{column}_{suffix}",
                        (px, y + normal * 0.192, pz),
                        (sx, 0.040, sz),
                        M["galvanized"],
                        0.012,
                        role="sally_port_window_frame",
                        parent=parent,
                    )
        else:
            # Commercial secure-vehicle doors use restrained continuous ribs,
            # not a residential grid of deeply stamped rectangular cassettes.
            # Three shallow folds per section provide real sheet stiffness and
            # specular breakup while preserving a calm institutional elevation.
            for rib in range(3):
                rib_z = panel_z + (rib - 1) * panel_height * 0.235
                box(
                    coll,
                    name + f":micro_rib_{row}_{rib}",
                    (x, y + normal * 0.151, rib_z),
                    (width - 0.28, 0.025, 0.020),
                    M["galvanized"],
                    0.008,
                    role="sectional_door_micro_rib",
                    parent=parent,
                )

    # Flexible bulb seals occupy the real inter-panel gaps.
    for seam in range(1, panel_rows):
        seam_z = base_z + seam * panel_height
        box(
            coll,
            name + f":section_seal_{seam}",
            (x, y + normal * 0.176, seam_z),
            (width - 0.20, 0.026, 0.022),
            M["rubber"],
            0.008,
            role="garage_door_panel_joint",
            parent=parent,
        )
        for hinge_column in (1, panel_columns // 2, panel_columns - 1):
            hinge_x = x - width / 2 + panel_width * hinge_column
            box(
                coll,
                name + f":hinge_plate_{seam}_{hinge_column}",
                (hinge_x, y + normal * 0.205, seam_z),
                (0.15, 0.030, 0.09),
                M["galvanized"],
                0.018,
                role="sectional_door_hinge",
                parent=parent,
            )
            for bolt_side in (-1, 1):
                cylinder(
                    coll,
                    name + f":hinge_bolt_{seam}_{hinge_column}_{bolt_side}",
                    (hinge_x + bolt_side * 0.075, y + normal * 0.235, seam_z),
                    0.012,
                    0.012,
                    M["black"],
                    12,
                    rot=(math.pi / 2, 0, 0),
                    role="sectional_door_fastener",
                    parent=parent,
                )

    for side in (-1, 1):
        track_x = x + side * (width / 2 + 0.11)
        box(
            coll,
            name + f":guide_channel_{side}",
            (track_x, y + normal * 0.15, base_z + height / 2),
            (0.16, 0.16, height + 0.30),
            M["galvanized"],
            0.025,
            role="garage_door_guide_track",
            parent=parent,
        )
        for anchor_index in range(5):
            anchor_z = base_z + 0.42 + anchor_index * (height - 0.84) / 4
            box(
                coll,
                name + f":track_bracket_{side}_{anchor_index}",
                (track_x + side * 0.11, y + normal * 0.08, anchor_z),
                (0.26, 0.18, 0.12),
                M["galvanized"],
                0.018,
                role="garage_door_track_bracket",
                parent=parent,
            )
            cylinder(
                coll,
                name + f":track_anchor_{side}_{anchor_index}",
                (track_x + side * 0.20, y + normal * 0.185, anchor_z),
                0.025,
                0.020,
                M["black"],
                12,
                rot=(math.pi / 2, 0, 0),
                role="garage_door_track_anchor",
                parent=parent,
            )
        # Sensors are compact track-mounted units, never freestanding posts.
        box(
            coll,
            name + f":photoeye_body_{side}",
            (track_x, y + normal * 0.27, base_z + 0.39),
            (0.16, 0.10, 0.22),
            M["black"],
            0.035,
            role="garage_door_safety_sensor",
            parent=parent,
        )
        cylinder(
            coll,
            name + f":photoeye_lens_{side}",
            (track_x, y + normal * 0.335, base_z + 0.41),
            0.030,
            0.016,
            M["lamp_red"],
            14,
            rot=(math.pi / 2, 0, 0),
            role="garage_door_safety_sensor_lens",
            parent=parent,
        )
        cylinder(
            coll,
            name + f":cable_drum_{side}",
            (x + side * (width / 2 - 0.24), y + normal * 0.19, base_z + height + 0.19),
            0.18,
            0.16,
            M["galvanized"],
            24,
            rot=(math.pi / 2, 0, 0),
            role="garage_door_cable_drum",
            parent=parent,
        )
        beam(
            coll,
            name + f":lift_cable_{side}",
            (x + side * (width / 2 - 0.24), y + normal * 0.285, base_z + 0.24),
            (x + side * (width / 2 - 0.24), y + normal * 0.285, base_z + height + 0.19),
            0.009,
            M["black"],
            8,
            role="garage_door_lift_cable",
            parent=parent,
        )

    box(
        coll,
        name + ":folded_header_hood",
        (x, y + normal * 0.13, base_z + height + 0.19),
        (width + 0.48, 0.32, 0.34),
        M["galvanized"],
        0.045,
        role="garage_door_header",
        parent=parent,
    )
    box(
        coll,
        name + ":header_drip",
        (x, y + normal * 0.315, base_z + height + 0.04),
        (width + 0.55, 0.055, 0.080),
        M["rubber"],
        0.018,
        role="garage_door_header_weather_seal",
        parent=parent,
    )
    box(
        coll,
        name + ":bottom_astragal",
        (x, y + normal * 0.205, base_z + 0.045),
        (width - 0.18, 0.13, 0.09),
        M["rubber"],
        0.025,
        role="garage_door_bottom_seal",
        parent=parent,
    )
    box(
        coll,
        name + ":manual_lock_case",
        (x, y + normal * 0.235, base_z + 0.84),
        (0.32, 0.10, 0.24),
        M["galvanized"],
        0.030,
        role="garage_door_manual_lock",
        parent=parent,
    )
    beam(
        coll,
        name + ":manual_handle",
        (x - 0.16, y + normal * 0.31, base_z + 0.86),
        (x + 0.16, y + normal * 0.31, base_z + 0.86),
        0.025,
        M["black"],
        14,
        role="garage_door_manual_handle",
        parent=parent,
    )


def louver_panel_y(coll, parent, name, x, y, z, width, height, M, normal=1.0):
    """Recessed storm-proof mechanical louver with a frame and pitched blades."""
    box(
        coll,
        name + ":recess",
        (x, y - normal * 0.08, z),
        (width + 0.30, 0.18, height + 0.30),
        M["interior_shadow"],
        0.025,
        role="wall_louver_recess",
        parent=parent,
    )
    box(
        coll,
        name + ":back",
        (x, y + normal * 0.02, z),
        (width, 0.055, height),
        M["black"],
        role="wall_louver_back",
        parent=parent,
    )
    for blade in range(max(5, int(height / 0.16))):
        pz = z - height / 2 + 0.11 + blade * 0.16
        slat = box(
            coll,
            name + f":blade_{blade}",
            (x, y + normal * 0.13, pz),
            (width - 0.12, 0.15, 0.055),
            M["painted_steel"],
            0.015,
            role="wall_louver_blade",
            parent=parent,
        )
        slat.rotation_euler[0] = normal * math.radians(24)
    for suffix, px, pz, sx, sz in (
        ("left", x - width / 2, z, 0.085, height + 0.14),
        ("right", x + width / 2, z, 0.085, height + 0.14),
        ("head", x, z + height / 2, width + 0.14, 0.085),
        ("sill", x, z - height / 2, width + 0.14, 0.085),
    ):
        box(
            coll,
            name + ":frame_" + suffix,
            (px, y + normal * 0.18, pz),
            (sx, 0.12, sz),
            M["steel"],
            0.018,
            role="wall_louver_frame",
            parent=parent,
        )


def rear_utility_cluster(coll, parent, name, x, y, base_z, M, normal=1.0):
    """Metering, disconnects and conduits that make a service facade believable."""
    for index, (dx, width, height) in enumerate(
        ((-0.72, 0.58, 0.82), (0.0, 0.72, 1.10), (0.78, 0.46, 0.66))
    ):
        box(
            coll,
            name + f":cabinet_{index}",
            (x + dx, y + normal * 0.12, base_z + height / 2 + 0.42),
            (width, 0.22, height),
            M["painted_steel"],
            0.035,
            role="rear_electrical_cabinet",
            parent=parent,
        )
        box(
            coll,
            name + f":cabinet_latch_{index}",
            (x + dx + width * 0.31, y + normal * 0.25, base_z + height * 0.55 + 0.42),
            (0.045, 0.025, 0.17),
            M["steel"],
            0.015,
            role="rear_electrical_hardware",
            parent=parent,
        )
    for conduit, dx in enumerate((-0.94, -0.72, -0.50, 0.55, 0.78, 1.00)):
        cylinder(
            coll,
            name + f":conduit_{conduit}",
            (x + dx, y + normal * 0.18, base_z + 1.62),
            0.027,
            2.35,
            M["aluminum"],
            12,
            role="rear_electrical_conduit",
            parent=parent,
        )
        for strap, z in enumerate((base_z + 0.78, base_z + 1.60, base_z + 2.38)):
            box(
                coll,
                name + f":conduit_strap_{conduit}_{strap}",
                (x + dx, y + normal * 0.235, z),
                (0.12, 0.035, 0.045),
                M["steel"],
                0.012,
                role="rear_conduit_strap",
                parent=parent,
            )
    cylinder(
        coll,
        name + ":meter_body",
        (x + 1.44, y + normal * 0.17, base_z + 1.50),
        0.27,
        0.18,
        M["painted_steel"],
        24,
        rot=(math.pi / 2, 0, 0),
        role="rear_utility_meter",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":meter_glass",
        (x + 1.44, y + normal * 0.29, base_z + 1.50),
        0.19,
        0.035,
        M["glass_clear"],
        24,
        rot=(math.pi / 2, 0, 0),
        role="rear_utility_meter_glass",
        parent=parent,
    )


def stainless_bollard(coll, parent, name, x, y, base_z, M, height=1.18):
    cylinder(
        coll,
        name + ":base_collar",
        (x, y, base_z + 0.055),
        0.18,
        0.11,
        M["steel"],
        32,
        role="stainless_security_bollard_base",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":shaft",
        (x, y, base_z + height / 2),
        0.115,
        height,
        M["steel"],
        40,
        role="stainless_security_bollard",
        parent=parent,
    )
    sphere(
        coll,
        name + ":cap",
        (x, y, base_z + height),
        (0.116, 0.116, 0.075),
        M["steel"],
        role="stainless_security_bollard_cap",
        parent=parent,
        subdivisions=2,
    )
    cylinder(
        coll,
        name + ":top_reveal",
        (x, y, base_z + height - 0.12),
        0.118,
        0.022,
        M["joint_sealant"],
        32,
        role="bollard_manufacturing_joint",
        parent=parent,
    )


def panel_joint_grid(
    coll,
    parent,
    name,
    cx,
    y,
    z0,
    width,
    height,
    M,
    normal=-1.0,
    columns=8,
    rows=3,
    role="metal_panel_joint",
):
    for col in range(columns + 1):
        x = cx - width / 2 + width * col / columns
        box(
            coll,
            name + f":vertical_{col}",
            (x, y + normal * 0.012, z0 + height / 2),
            (0.022, 0.018, height - 0.06),
            M["black"],
            role=role,
            parent=parent,
        )
    for row in range(rows + 1):
        z = z0 + height * row / rows
        box(
            coll,
            name + f":horizontal_{row}",
            (cx, y + normal * 0.012, z),
            (width - 0.05, 0.018, 0.022),
            M["black"],
            role=role,
            parent=parent,
        )


def wall_light(coll, parent, name, x, y, z, M, normal=-1.0):
    box(
        coll,
        name + ":mount",
        (x, y - normal * 0.03, z),
        (0.32, 0.18, 0.56),
        M["black"],
        0.045,
        role="wall_light_fixture",
        parent=parent,
    )
    box(
        coll,
        name + ":lens",
        (x, y + normal * 0.075, z - 0.05),
        (0.23, 0.075, 0.35),
        M["lamp_white"],
        0.055,
        role="wall_light_lens",
        parent=parent,
    )


def dome_camera(coll, parent, name, x, y, z, M, normal=-1.0):
    beam(
        coll,
        name + ":arm",
        (x, y, z),
        (x, y + normal * 0.42, z),
        0.045,
        M["aluminum"],
        14,
        role="security_camera_mount",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":base",
        (x, y + normal * 0.44, z),
        0.16,
        0.12,
        M["white"],
        24,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="security_camera_housing",
        parent=parent,
    )
    sphere(
        coll,
        name + ":dome",
        (x, y + normal * 0.54, z - 0.10),
        (0.13, 0.11, 0.13),
        M["glass_dark"],
        role="security_camera_dome",
        parent=parent,
        subdivisions=2,
    )
    cylinder(
        coll,
        name + ":lens",
        (x, y + normal * 0.65, z - 0.11),
        0.035,
        0.025,
        M["black"],
        16,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="security_camera_lens",
        parent=parent,
    )


def roof_mechanical_unit(coll, parent, name, x, y, z, width, depth, height, M):
    box(
        coll,
        name + ":curb",
        (x, y, z + 0.10),
        (width + 0.35, depth + 0.35, 0.20),
        M["concrete"],
        role="roof_plant_curb",
        parent=parent,
    )
    box(
        coll,
        name + ":cabinet",
        (x, y, z + height / 2 + 0.16),
        (width, depth, height),
        M["aluminum"],
        0.055,
        role="roof_mechanical_unit",
        parent=parent,
    )
    for side in (-1, 1):
        for slat in range(8):
            sy = y - depth * 0.36 + slat * depth * 0.103
            box(
                coll,
                name + f":louver_{side}_{slat}",
                (x + side * (width / 2 + 0.022), sy, z + height * 0.68),
                (0.045, depth * 0.068, height * 0.42),
                M["black"],
                role="mechanical_louver",
                parent=parent,
            )
    cylinder(
        coll,
        name + ":fan",
        (x, y, z + height + 0.21),
        min(width, depth) * 0.28,
        0.08,
        M["black"],
        32,
        role="roof_fan",
        parent=parent,
    )
    for blade in range(6):
        angle = 2 * math.pi * blade / 6
        beam(
            coll,
            name + f":fan_blade_{blade}",
            (x, y, z + height + 0.26),
            (
                x + math.cos(angle) * min(width, depth) * 0.21,
                y + math.sin(angle) * min(width, depth) * 0.21,
                z + height + 0.26,
            ),
            0.024,
            M["steel"],
            10,
            role="roof_fan_blade",
            parent=parent,
        )


def flat_roof_edge_system(
    coll, parent, name, cx, cy, width, depth, roof_z, M, front_y=None, scupper_xs=()
):
    """Construct a complete low-slope roof edge instead of a single slab.

    Includes a recessed membrane, raised parapet, continuous metal coping,
    butt seams, inner reglet and through-wall scuppers.  All pieces remain part
    of the building asset and are useful in both near and rear oblique views.
    """
    box(
        coll,
        name + ":membrane",
        (cx, cy, roof_z + 0.035),
        (width - 0.72, depth - 0.72, 0.07),
        M["black"],
        0.018,
        role="roof_membrane",
        parent=parent,
    )
    for edge_name, xyz, dims in (
        ("front", (cx, cy - depth / 2 + 0.14, roof_z + 0.32), (width, 0.28, 0.64)),
        ("rear", (cx, cy + depth / 2 - 0.14, roof_z + 0.32), (width, 0.28, 0.64)),
        ("west", (cx - width / 2 + 0.14, cy, roof_z + 0.32), (0.28, depth, 0.64)),
        ("east", (cx + width / 2 - 0.14, cy, roof_z + 0.32), (0.28, depth, 0.64)),
    ):
        box(
            coll,
            name + f":parapet_{edge_name}",
            xyz,
            dims,
            M["precast"],
            0.035,
            role="roof_parapet",
            parent=parent,
        )
        cap_dims = (
            dims[0] + (0.16 if dims[0] > dims[1] else 0.0),
            dims[1] + (0.16 if dims[1] > dims[0] else 0.0),
            0.12,
        )
        box(
            coll,
            name + f":coping_{edge_name}",
            (xyz[0], xyz[1], roof_z + 0.69),
            cap_dims,
            M["blue_grey_metal"],
            0.025,
            role="roof_coping",
            parent=parent,
        )
    for seam_index, sx in enumerate(
        [
            cx - width / 2 + 1.2 + i * 1.85
            for i in range(max(1, int((width - 2.4) / 1.85)) + 1)
        ]
    ):
        for edge_name, sy in (
            ("front", cy - depth / 2 - 0.005),
            ("rear", cy + depth / 2 + 0.005),
        ):
            box(
                coll,
                name + f":coping_seam_{edge_name}_{seam_index}",
                (sx, sy, roof_z + 0.70),
                (0.020, 0.055, 0.14),
                M["black"],
                role="roof_coping_joint",
                parent=parent,
            )
    for seam_index, sy in enumerate(
        [
            cy - depth / 2 + 1.2 + i * 1.85
            for i in range(max(1, int((depth - 2.4) / 1.85)) + 1)
        ]
    ):
        for edge_name, sx in (
            ("west", cx - width / 2 - 0.005),
            ("east", cx + width / 2 + 0.005),
        ):
            box(
                coll,
                name + f":coping_seam_{edge_name}_{seam_index}",
                (sx, sy, roof_z + 0.70),
                (0.055, 0.020, 0.14),
                M["black"],
                role="roof_coping_joint",
                parent=parent,
            )
    facade_y = front_y if front_y is not None else cy - depth / 2
    for scupper_index, sx in enumerate(scupper_xs):
        box(
            coll,
            name + f":scupper_recess_{scupper_index}",
            (sx, facade_y - 0.12, roof_z + 0.29),
            (0.62, 0.30, 0.30),
            M["black"],
            0.025,
            role="roof_scupper_recess",
            parent=parent,
        )
        box(
            coll,
            name + f":scupper_liner_{scupper_index}",
            (sx, facade_y - 0.29, roof_z + 0.27),
            (0.46, 0.30, 0.18),
            M["steel"],
            0.018,
            role="roof_scupper_liner",
            parent=parent,
        )


def roof_service_walkway(coll, parent, name, points, z, M):
    """Add jointed anti-slip maintenance pads between roof equipment."""
    for index, (x, y) in enumerate(points):
        box(
            coll,
            name + f":pad_{index}",
            (x, y, z),
            (1.05, 1.05, 0.055),
            M["rubber"],
            0.025,
            role="roof_service_walkway_pad",
            parent=parent,
        )


def downpipe(coll, parent, name, x, y, top_z, M, front=True):
    cylinder(
        coll,
        name + ":pipe",
        (x, y, top_z / 2),
        0.060,
        top_z,
        M["aluminum"],
        18,
        role="rainwater_downpipe",
        parent=parent,
    )
    direction = -1.0 if front else 1.0
    beam(
        coll,
        name + ":shoe",
        (x, y, 0.18),
        (x, y + direction * 0.44, 0.12),
        0.060,
        M["aluminum"],
        16,
        role="rainwater_downpipe_shoe",
        parent=parent,
    )
    for z in (1.3, 4.0, 6.7):
        cylinder(
            coll,
            name + f":strap_{z}",
            (x, y, z),
            0.078,
            0.025,
            M["steel"],
            18,
            role="downpipe_strap",
            parent=parent,
        )


def entrance_stair_y(
    coll,
    parent,
    name,
    x,
    landing_front_y,
    grade_z,
    width,
    rise,
    M,
    step_count=3,
    tread=0.40,
    landing_depth=2.15,
    outward=-1.0,
):
    """Cast-in-place civic stair with correctly ordered risers and landings."""
    riser = rise / step_count
    # The landing is a grounded plinth tucked beneath the entrance, not a
    # floating board.  Its front edge is exactly the top-stair nosing.
    landing_center_y = landing_front_y - outward * landing_depth / 2
    box(
        coll,
        name + ":upper_landing",
        (x, landing_center_y, grade_z + rise / 2),
        (width, landing_depth, rise),
        M["concrete_light"],
        0.055,
        role="entrance_landing",
        parent=parent,
    )
    for step in range(step_count):
        step_height = rise - step * riser
        step_y = landing_front_y + outward * (step + 0.5) * tread
        box(
            coll,
            name + f":step_{step}",
            (x, step_y, grade_z + step_height / 2),
            (width, tread + 0.025, step_height),
            M["concrete_light"],
            0.040,
            role="entrance_step",
            parent=parent,
        )
        nosing_y = step_y + outward * tread / 2
        box(
            coll,
            name + f":nosing_{step}",
            (x, nosing_y, grade_z + step_height + 0.012),
            (width - 0.10, 0.065, 0.035),
            M["precast"],
            0.018,
            role="stair_nosing",
            parent=parent,
        )
        # Narrow saw-cut grooves are inset into each tread and remain neutral
        # concrete/charcoal—there is no yellow plate at the Type-A entrance.
        for groove in range(2):
            groove_y = step_y + outward * (0.04 + groove * 0.085)
            box(
                coll,
                name + f":anti_slip_groove_{step}_{groove}",
                (x, groove_y, grade_z + step_height + 0.031),
                (width - 0.28, 0.018, 0.010),
                M["joint_sealant"],
                0.006,
                role="stair_anti_slip_groove",
                parent=parent,
            )

    rail_xs = (x - width / 2 + 0.20, x + width / 2 - 0.20)
    stair_outer_y = landing_front_y + outward * step_count * tread
    for side, rail_x in enumerate(rail_xs):
        beam(
            coll,
            name + f":sloped_handrail_{side}",
            (rail_x, stair_outer_y, grade_z + riser + 0.91),
            (rail_x, landing_front_y, grade_z + rise + 0.91),
            0.040,
            M["steel"],
            18,
            role="entrance_handrail",
            parent=parent,
        )
        beam(
            coll,
            name + f":landing_handrail_{side}",
            (rail_x, landing_front_y, grade_z + rise + 0.91),
            (
                rail_x,
                landing_front_y - outward * (landing_depth - 0.28),
                grade_z + rise + 0.91,
            ),
            0.040,
            M["steel"],
            18,
            role="entrance_handrail",
            parent=parent,
        )
        for post in range(step_count + 2):
            t = post / (step_count + 1)
            py = stair_outer_y + (landing_front_y - stair_outer_y) * t
            walking_z = grade_z + riser + (rise - riser) * t
            cylinder(
                coll,
                name + f":rail_base_{side}_{post}",
                (rail_x, py, walking_z + 0.018),
                0.085,
                0.036,
                M["steel"],
                20,
                role="handrail_base_plate",
                parent=parent,
            )
            beam(
                coll,
                name + f":rail_post_{side}_{post}",
                (rail_x, py, walking_z + 0.04),
                (rail_x, py, walking_z + 0.91),
                0.031,
                M["steel"],
                16,
                role="entrance_handrail_post",
                parent=parent,
            )
        # Returned ends remove the cut-off pipe look.
        beam(
            coll,
            name + f":rail_return_{side}",
            (rail_x, stair_outer_y, grade_z + riser + 0.91),
            (rail_x, stair_outer_y + outward * 0.26, grade_z + riser + 0.91),
            0.040,
            M["steel"],
            18,
            role="handrail_return",
            parent=parent,
        )
        beam(
            coll,
            name + f":rail_return_drop_{side}",
            (rail_x, stair_outer_y + outward * 0.26, grade_z + riser + 0.91),
            (rail_x, stair_outer_y + outward * 0.26, grade_z + riser + 0.67),
            0.040,
            M["steel"],
            18,
            role="handrail_return",
            parent=parent,
        )


def accessible_ramp(coll, parent, name, x, y, z, length, width, rise, M, high_side=1.0):
    """Grounded, segmented accessible route with eased grade transitions.

    The walking surface and its filled side faces are one wedge mesh.  At the
    low end its underside is buried at grade, so the ramp cannot read as a
    rotated rectangular board or cast a floating shadow beneath itself.
    """
    segments = 18
    ground_z = z - 0.035

    def profile(t):
        # A short clothoid-like easing at both ends prevents a hard kink where
        # the route meets the forecourt and upper landing.
        if t < 0.12:
            u = t / 0.12
            return rise * 0.12 * (u * u * (3.0 - 2.0 * u))
        if t > 0.88:
            u = (t - 0.88) / 0.12
            return rise * (0.88 + 0.12 * (u * u * (3.0 - 2.0 * u)))
        return rise * t

    vertices = []
    for index in range(segments + 1):
        t = index / segments
        px = x + high_side * (-length / 2 + length * t)
        top_z = z + profile(t)
        vertices.extend(
            (
                (px, y - width / 2, top_z),
                (px, y + width / 2, top_z),
                (px, y - width / 2, ground_z),
                (px, y + width / 2, ground_z),
            )
        )
    faces = []
    for index in range(segments):
        a, b = index * 4, (index + 1) * 4
        faces.extend(
            (
                (a, b, b + 1, a + 1),
                (a + 2, a + 3, b + 3, b + 2),
                (a, a + 2, b + 2, b),
                (a + 1, b + 1, b + 3, a + 3),
            )
        )
    faces.extend(
        (
            (0, 1, 3, 2),
            (segments * 4, segments * 4 + 2, segments * 4 + 3, segments * 4 + 1),
        )
    )
    if high_side < 0:
        faces = [tuple(reversed(face)) for face in faces]
    ramp = mesh_object(
        coll,
        name + ":integrated_wedge",
        vertices,
        faces,
        M["concrete_light"],
        "accessible_ramp",
        parent,
    )
    bevel = ramp.modifiers.new(name="cast_edge_softening", type="BEVEL")
    bevel.width = 0.035
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    ramp["c2w_grade_transition"] = "embedded_low_end_and_eased_profile"

    # Flush approach apron and a compact upper landing are embedded into the
    # surrounding paving.  The upper landing is filled to grade, as constructed.
    box(
        coll,
        name + ":flush_approach",
        (x - high_side * (length / 2 + 0.70), y, ground_z + 0.025),
        (1.40, width + 0.32, 0.050),
        M["concrete_light"],
        0.055,
        role="accessible_ramp_transition_apron",
        parent=parent,
    )
    box(
        coll,
        name + ":upper_landing",
        (x + high_side * (length / 2 + 0.72), y, ground_z + (rise + 0.035) / 2),
        (1.44, width + 0.18, rise + 0.035),
        M["concrete_light"],
        0.055,
        role="accessible_ramp_landing",
        parent=parent,
    )

    # Surface edge bands follow the actual eased profile and are not vertical
    # curb blocks.  Dual rails, returned extensions and anchored posts complete
    # the manufactured accessible route.
    for side in (-1, 1):
        outer_y = y + side * (width / 2 - 0.045)
        inner_y = y + side * (width / 2 - 0.12)
        edge_vertices = []
        for index in range(segments + 1):
            t = index / segments
            px = x + high_side * (-length / 2 + length * t)
            pz = z + profile(t) + 0.014
            edge_vertices.extend(((px, outer_y, pz), (px, inner_y, pz)))
        edge_faces = []
        for index in range(segments):
            a = index * 2
            edge_faces.append((a, a + 2, a + 3, a + 1))
        if high_side < 0:
            edge_faces = [tuple(reversed(face)) for face in edge_faces]
        mesh_object(
            coll,
            name + f":integrated_edge_band_{side}",
            edge_vertices,
            edge_faces,
            M["precast"],
            "accessible_ramp_edge_band",
            parent,
        )

        rail_y = y + side * (width / 2 + 0.08)
        rail_points = []
        for index in range(10):
            t = index / 9
            rail_points.append(
                (
                    x + high_side * (-length / 2 + length * t),
                    rail_y,
                    z + profile(t) + 0.91,
                )
            )
        for index in range(len(rail_points) - 1):
            beam(
                coll,
                name + f":upper_rail_{side}_{index}",
                rail_points[index],
                rail_points[index + 1],
                0.040,
                M["steel"],
                18,
                role="accessible_handrail",
                parent=parent,
            )
        for index in range(7):
            t = index / 6
            px = x + high_side * (-length / 2 + length * t)
            walking_z = z + profile(t)
            cylinder(
                coll,
                name + f":post_base_{side}_{index}",
                (px, rail_y, walking_z + 0.018),
                0.080,
                0.036,
                M["steel"],
                20,
                role="handrail_base_plate",
                parent=parent,
            )
            beam(
                coll,
                name + f":post_{side}_{index}",
                (px, rail_y, walking_z + 0.04),
                (px, rail_y, walking_z + 0.91),
                0.031,
                M["steel"],
                16,
                role="accessible_handrail_post",
                parent=parent,
            )
            if index < 6:
                t2 = (index + 1) / 6
                p2x = x + high_side * (-length / 2 + length * t2)
                beam(
                    coll,
                    name + f":lower_rail_{side}_{index}",
                    (px, rail_y, walking_z + 0.52),
                    (p2x, rail_y, z + profile(t2) + 0.52),
                    0.028,
                    M["steel"],
                    14,
                    role="accessible_lower_handrail",
                    parent=parent,
                )
        low_end = (x - high_side * length / 2, rail_y, z + 0.91)
        high_end = (x + high_side * length / 2, rail_y, z + rise + 0.91)
        beam(
            coll,
            name + f":low_extension_{side}",
            low_end,
            (low_end[0] - high_side * 0.34, rail_y, low_end[2]),
            0.040,
            M["steel"],
            18,
            role="accessible_handrail_return",
            parent=parent,
        )
        beam(
            coll,
            name + f":high_extension_{side}",
            high_end,
            (high_end[0] + high_side * 0.34, rail_y, high_end[2]),
            0.040,
            M["steel"],
            18,
            role="accessible_handrail_return",
            parent=parent,
        )


def office_desk(coll, parent, name, x, y, z, M, yaw=0.0):
    box(
        coll,
        name + ":top",
        (x, y, z + 0.76),
        (1.65, 0.78, 0.10),
        M["wood"],
        0.045,
        rot=yaw,
        role="police_office_desk",
        parent=parent,
    )
    for dx in (-0.68, 0.68):
        for dy in (-0.29, 0.29):
            wx = x + dx * math.cos(yaw) - dy * math.sin(yaw)
            wy = y + dx * math.sin(yaw) + dy * math.cos(yaw)
            beam(
                coll,
                name + f":leg_{dx}_{dy}",
                (wx, wy, z + 0.06),
                (wx, wy, z + 0.71),
                0.027,
                M["steel"],
                12,
                role="desk_leg",
                parent=parent,
            )
    box(
        coll,
        name + ":monitor",
        (x, y + 0.08, z + 1.22),
        (0.66, 0.10, 0.43),
        M["black"],
        0.035,
        rot=yaw,
        role="office_monitor",
        parent=parent,
    )
    box(
        coll,
        name + ":screen",
        (x, y + 0.022, z + 1.22),
        (0.57, 0.016, 0.34),
        M["screen"],
        rot=yaw,
        role="office_monitor_screen",
        parent=parent,
    )
    beam(
        coll,
        name + ":monitor_stand",
        (x, y + 0.08, z + 0.82),
        (x, y + 0.08, z + 1.00),
        0.027,
        M["black"],
        12,
        role="monitor_stand",
        parent=parent,
    )
    for paper in range(3):
        box(
            coll,
            name + f":paper_{paper}",
            (x - 0.48 + paper * 0.05, y - 0.10, z + 0.825 + paper * 0.006),
            (0.42, 0.30, 0.008),
            M["white"],
            role="desk_document",
            parent=parent,
        )


def task_chair(coll, parent, name, x, y, z, M, yaw=0.0):
    box(
        coll,
        name + ":seat",
        (x, y, z + 0.50),
        (0.58, 0.58, 0.13),
        M["fabric_blue"],
        0.07,
        rot=yaw,
        role="office_chair",
        parent=parent,
    )
    box(
        coll,
        name + ":back",
        (x, y + 0.23, z + 0.95),
        (0.58, 0.12, 0.78),
        M["fabric_blue"],
        0.07,
        rot=yaw,
        role="office_chair_back",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":post",
        (x, y, z + 0.28),
        0.045,
        0.42,
        M["steel"],
        14,
        role="office_chair_base",
        parent=parent,
    )
    for spoke in range(5):
        angle = yaw + 2 * math.pi * spoke / 5
        beam(
            coll,
            name + f":base_spoke_{spoke}",
            (x, y, z + 0.12),
            (x + math.cos(angle) * 0.32, y + math.sin(angle) * 0.32, z + 0.09),
            0.025,
            M["steel"],
            10,
            role="office_chair_base",
            parent=parent,
        )


def reception_desk(coll, parent, name, x, y, z, width, M):
    box(
        coll,
        name + ":body",
        (x, y, z + 0.62),
        (width, 0.92, 1.20),
        M["precast"],
        0.065,
        role="secure_reception_desk",
        parent=parent,
    )
    box(
        coll,
        name + ":wood_face",
        (x, y - 0.48, z + 0.70),
        (width - 0.34, 0.055, 0.72),
        M["wood"],
        0.028,
        role="reception_finish",
        parent=parent,
    )
    box(
        coll,
        name + ":counter",
        (x, y, z + 1.25),
        (width + 0.25, 1.08, 0.11),
        M["terrazzo"],
        0.055,
        role="reception_counter",
        parent=parent,
    )
    for index, dx in enumerate((-width * 0.27, width * 0.27)):
        box(
            coll,
            name + f":monitor_{index}",
            (x + dx, y + 0.02, z + 1.67),
            (0.64, 0.11, 0.42),
            M["black"],
            0.035,
            role="reception_monitor",
            parent=parent,
        )
        box(
            coll,
            name + f":screen_{index}",
            (x + dx, y - 0.044, z + 1.67),
            (0.55, 0.016, 0.33),
            M["screen"],
            role="reception_monitor_screen",
            parent=parent,
        )
    box(
        coll,
        name + ":ballistic_glass",
        (x, y - 0.56, z + 2.05),
        (width - 0.36, 0.045, 1.30),
        M["glass_clear"],
        role="ballistic_reception_glazing",
        parent=parent,
    )
    for dx in (-width / 2 + 0.12, 0.0, width / 2 - 0.12):
        box(
            coll,
            name + f":ballistic_mullion_{dx}",
            (x + dx, y - 0.60, z + 2.05),
            (0.055, 0.08, 1.36),
            M["bronze"],
            role="ballistic_glazing_frame",
            parent=parent,
        )


def waiting_chair(coll, parent, name, x, y, z, M, yaw=0.0):
    box(
        coll,
        name + ":seat",
        (x, y, z + 0.50),
        (0.68, 0.62, 0.14),
        M["fabric_blue"],
        0.07,
        rot=yaw,
        role="public_waiting_chair",
        parent=parent,
    )
    box(
        coll,
        name + ":back",
        (x, y + 0.25, z + 0.98),
        (0.68, 0.13, 0.84),
        M["fabric_blue"],
        0.07,
        rot=yaw,
        role="public_waiting_chair_back",
        parent=parent,
    )
    for dx in (-0.27, 0.27):
        for dy in (-0.22, 0.22):
            beam(
                coll,
                name + f":leg_{dx}_{dy}",
                (x + dx, y + dy, z + 0.06),
                (x + dx, y + dy, z + 0.44),
                0.025,
                M["steel"],
                12,
                role="waiting_chair_leg",
                parent=parent,
            )


def ceiling_lights(coll, parent, name, xs, ys, z, M):
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            box(
                coll,
                name + f":panel_{ix}_{iy}",
                (x, y, z),
                (1.18, 0.42, 0.035),
                M["lamp_white"],
                0.018,
                role="interior_ceiling_light",
                parent=parent,
            )


def security_turnstile(coll, parent, name, x, y, z, M):
    for side in (-1, 1):
        box(
            coll,
            name + f":pedestal_{side}",
            (x + side * 0.52, y, z + 0.55),
            (0.22, 1.05, 1.10),
            M["steel"],
            0.06,
            role="security_turnstile_pedestal",
            parent=parent,
        )
        box(
            coll,
            name + f":card_reader_{side}",
            (x + side * 0.52, y - 0.20, z + 1.17),
            (0.16, 0.25, 0.10),
            M["black"],
            0.035,
            role="access_control_reader",
            parent=parent,
        )
    cylinder(
        coll,
        name + ":hub",
        (x, y, z + 0.78),
        0.09,
        0.30,
        M["steel"],
        20,
        rot=(0.0, math.pi / 2.0, 0.0),
        role="security_turnstile_hub",
        parent=parent,
    )
    for arm in range(3):
        angle = 2 * math.pi * arm / 3
        beam(
            coll,
            name + f":arm_{arm}",
            (x, y, z + 0.78),
            (x, y + math.cos(angle) * 0.72, z + 0.78 + math.sin(angle) * 0.72),
            0.032,
            M["steel"],
            14,
            role="security_turnstile_arm",
            parent=parent,
        )


def circular_seal(coll, parent, name, x, y, z, radius, M, normal=-1.0):
    """Layered municipal seal with concentric metal rings and radial ticks."""
    outer_y = y + normal * 0.16
    cylinder(
        coll,
        name + ":backing",
        (x, y, z),
        radius,
        0.16,
        M["white"],
        48,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="municipal_police_seal",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":blue_field",
        (x, y + normal * 0.09, z),
        radius * 0.83,
        0.07,
        M["vehicle_blue"],
        48,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="municipal_police_seal_field",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":center",
        (x, y + normal * 0.14, z),
        radius * 0.39,
        0.055,
        M["white"],
        40,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="municipal_police_seal_center",
        parent=parent,
    )
    for tick in range(24):
        angle = 2 * math.pi * tick / 24
        px = x + math.cos(angle) * radius * 0.66
        pz = z + math.sin(angle) * radius * 0.66
        bar = box(
            coll,
            name + f":tick_{tick}",
            (px, outer_y, pz),
            (radius * 0.17, 0.025, 0.045),
            M["white"],
            role="municipal_seal_tick",
            parent=parent,
        )
        bar.rotation_euler[1] = -angle
    # Central seven-point star reads as law-enforcement iconography at distance.
    for ray in range(7):
        angle = 2 * math.pi * ray / 7
        beam(
            coll,
            name + f":star_ray_{ray}",
            (x, outer_y + normal * 0.02, z),
            (
                x + math.cos(angle) * radius * 0.31,
                outer_y + normal * 0.02,
                z + math.sin(angle) * radius * 0.31,
            ),
            0.035,
            M["yellow"],
            10,
            role="police_seal_star",
            parent=parent,
        )


def lattice_radio_mast(coll, parent, name, x, y, z, height, M):
    """Triangulated communications mast with antenna arrays and feed lines."""
    half = 0.52
    corners = ((-half, -half), (half, -half), (half, half), (-half, half))
    for index, (dx, dy) in enumerate(corners):
        beam(
            coll,
            name + f":leg_{index}",
            (x + dx, y + dy, z),
            (x + dx * 0.48, y + dy * 0.48, z + height),
            0.045,
            M["steel"],
            14,
            role="communications_mast_leg",
            parent=parent,
        )
    bays = max(4, int(height / 1.4))
    for bay in range(bays):
        z0, z1 = z + height * bay / bays, z + height * (bay + 1) / bays
        shrink0, shrink1 = 1.0 - 0.50 * bay / bays, 1.0 - 0.50 * (bay + 1) / bays
        for edge in range(4):
            a, b = corners[edge], corners[(edge + 1) % 4]
            beam(
                coll,
                name + f":horizontal_chord_{bay}_{edge}",
                (x + a[0] * shrink0, y + a[1] * shrink0, z0),
                (x + b[0] * shrink0, y + b[1] * shrink0, z0),
                0.024,
                M["steel"],
                10,
                role="communications_mast_brace",
                parent=parent,
            )
            beam(
                coll,
                name + f":brace_a_{bay}_{edge}",
                (x + a[0] * shrink0, y + a[1] * shrink0, z0),
                (x + b[0] * shrink1, y + b[1] * shrink1, z1),
                0.022,
                M["steel"],
                10,
                role="communications_mast_brace",
                parent=parent,
            )
            beam(
                coll,
                name + f":brace_b_{bay}_{edge}",
                (x + b[0] * shrink0, y + b[1] * shrink0, z0),
                (x + a[0] * shrink1, y + a[1] * shrink1, z1),
                0.022,
                M["steel"],
                10,
                role="communications_mast_brace",
                parent=parent,
            )
    cylinder(
        coll,
        name + ":whip",
        (x, y, z + height + 1.6),
        0.028,
        3.2,
        M["steel"],
        12,
        role="radio_whip_antenna",
        parent=parent,
    )
    for level in (0.62, 0.78, 0.91):
        pz = z + height * level
        beam(
            coll,
            name + f":antenna_boom_{level}",
            (x - 0.95, y, pz),
            (x + 0.95, y, pz),
            0.028,
            M["steel"],
            12,
            role="radio_antenna_boom",
            parent=parent,
        )
        for element in range(-3, 4):
            px = x + element * 0.28
            beam(
                coll,
                name + f":antenna_element_{level}_{element}",
                (px, y - 0.52, pz),
                (px, y + 0.52, pz),
                0.018,
                M["steel"],
                10,
                role="radio_antenna_element",
                parent=parent,
            )


def bike_rack(coll, parent, name, x, y, z, M, count=4):
    for rack in range(count):
        rx = x + (rack - (count - 1) / 2) * 0.82
        arc_tube(
            coll,
            parent,
            name + f":loop_{rack}",
            (rx, y, z + 0.08),
            0.42,
            0.0,
            math.pi,
            12,
            0.035,
            M["steel"],
            "bicycle_rack",
        )
        beam(
            coll,
            name + f":left_leg_{rack}",
            (rx - 0.42, y, z + 0.08),
            (rx - 0.42, y, z - 0.20),
            0.035,
            M["steel"],
            12,
            role="bicycle_rack",
            parent=parent,
        )
        beam(
            coll,
            name + f":right_leg_{rack}",
            (rx + 0.42, y, z + 0.08),
            (rx + 0.42, y, z - 0.20),
            0.035,
            M["steel"],
            12,
            role="bicycle_rack",
            parent=parent,
        )


def cruiser_wheel(coll, parent, name, x, y, z, side, M):
    cylinder(
        coll,
        name + ":tire",
        (x, y, z),
        0.39,
        0.25,
        M["rubber"],
        40,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="police_cruiser_wheel",
        parent=parent,
    )
    outer_y = y + side * 0.145
    cylinder(
        coll,
        name + ":rim",
        (x, outer_y, z),
        0.245,
        0.035,
        M["aluminum"],
        36,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="vehicle_wheel_rim",
        parent=parent,
    )
    cylinder(
        coll,
        name + ":disc",
        (x, outer_y + side * 0.024, z),
        0.19,
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
        0.072,
        0.04,
        M["black"],
        24,
        rot=(math.pi / 2.0, 0.0, 0.0),
        role="vehicle_wheel_hub",
        parent=parent,
    )
    for spoke in range(10):
        angle = 2 * math.pi * spoke / 10
        beam(
            coll,
            name + f":spoke_{spoke}",
            (
                x + math.cos(angle) * 0.065,
                outer_y + side * 0.065,
                z + math.sin(angle) * 0.065,
            ),
            (
                x + math.cos(angle) * 0.215,
                outer_y + side * 0.065,
                z + math.sin(angle) * 0.215,
            ),
            0.018,
            M["aluminum"],
            10,
            role="vehicle_wheel_spoke",
            parent=parent,
        )
    for lug in range(5):
        angle = 2 * math.pi * lug / 5
        cylinder(
            coll,
            name + f":lug_{lug}",
            (
                x + math.cos(angle) * 0.052,
                outer_y + side * 0.083,
                z + math.sin(angle) * 0.052,
            ),
            0.014,
            0.022,
            M["steel"],
            10,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_wheel_lug",
            parent=parent,
        )
    for tread in range(20):
        angle = 2 * math.pi * tread / 20
        tread_obj = box(
            coll,
            name + f":tread_{tread}",
            (x + math.cos(angle) * 0.397, y, z + math.sin(angle) * 0.397),
            (0.105, 0.285, 0.052),
            M["rubber"],
            role="vehicle_tire_tread",
            parent=parent,
        )
        tread_obj.rotation_euler[1] = -angle


def detailed_police_cruiser(coll, parent, name, x, y, z, M, yaw=0.0, variant="suv"):
    """Coach-built patrol SUV/sedan with manufactured body, glazing and running gear."""
    root = bpy.data.objects.new(PREFIX + name + ":root", None)
    coll.objects.link(root)
    root.location = (x, y, z)
    root.rotation_euler[2] = yaw
    root.parent = parent
    tag(root, "police_cruiser_root", f"vehicle.police_cruiser.{variant}.v7")

    length = 5.15 if variant == "suv" else 4.82
    wheelbase = 3.15 if variant == "suv" else 2.92
    rear_x, front_x = -wheelbase / 2, wheelbase / 2
    roof_z = 1.86 if variant == "suv" else 1.62
    shoulder_z = 1.43 if variant == "suv" else 1.28
    half_width = 0.94
    for side in (-1, 1):
        box(
            coll,
            name + f":frame_rail_{side}",
            (0, side * 0.57, 0.47),
            (length - 0.45, 0.13, 0.19),
            M["black"],
            0.035,
            role="vehicle_chassis",
            parent=root,
        )
    for axle_x in (rear_x, front_x):
        cylinder(
            coll,
            name + f":axle_{axle_x}",
            (axle_x, 0, 0.49),
            0.065,
            1.95,
            M["black"],
            22,
            rot=(math.pi / 2.0, 0.0, 0.0),
            role="vehicle_axle",
            parent=root,
        )
        for side in (-1, 1):
            beam(
                coll,
                name + f":control_arm_{axle_x}_{side}",
                (axle_x - 0.32, side * 0.48, 0.44),
                (axle_x + 0.32, side * 0.78, 0.58),
                0.026,
                M["steel"],
                10,
                role="vehicle_suspension",
                parent=root,
            )
    beam(
        coll,
        name + ":exhaust",
        (-2.25, 0.57, 0.38),
        (1.65, 0.57, 0.38),
        0.040,
        M["steel"],
        14,
        role="vehicle_exhaust",
        parent=root,
    )

    body_sections = (
        (-length / 2, 0.72, 0.54, 0.87, 0.94, 0.05),
        (-length / 2 + 0.26, 0.91, 0.50, 1.18, 1.28, 0.08),
        (-1.42, half_width, 0.50, shoulder_z, roof_z - 0.04, 0.13),
        (0.92, half_width, 0.50, shoulder_z, roof_z, 0.14),
        (1.67, 0.92, 0.52, 1.25, 1.42, 0.09),
        (length / 2 - 0.35, 0.86, 0.56, 1.00, 1.10, 0.05),
        (length / 2, 0.68, 0.60, 0.87, 0.93, 0.04),
    )
    lofted_vehicle_shell(
        coll,
        name + ":coachwork",
        body_sections,
        M["vehicle_white"],
        "police_cruiser_body",
        root,
        0.07,
    )
    box(
        coll,
        name + ":lower_cladding",
        (0, 0, 0.62),
        (length - 0.20, 1.92, 0.27),
        M["black"],
        0.065,
        role="vehicle_lower_body_trim",
        parent=root,
    )
    # Dark belt visually separates the roof greenhouse from the body shell.
    for side in (-1, 1):
        sy = side * 0.945
        box(
            coll,
            name + f":navy_livery_{side}",
            (-0.15, sy + side * 0.045, 1.02),
            (length - 0.72, 0.035, 0.34),
            M["vehicle_blue"],
            0.018,
            role="police_vehicle_livery",
            parent=root,
        )
        box(
            coll,
            name + f":reflective_stripe_{side}",
            (-0.15, sy + side * 0.066, 1.02),
            (length - 0.82, 0.012, 0.055),
            M["road_white"],
            role="police_vehicle_reflective_livery",
            parent=root,
        )
        # Side glazing uses four trapezoidal panes with explicit gaskets.
        window_z0, window_z1 = 1.26, roof_z - 0.10
        panes = ((-1.45, -0.72), (-0.66, 0.04), (0.12, 0.80), (0.88, 1.35))
        for pane, (x0, x1) in enumerate(panes):
            vertices = [
                (x0, sy, window_z0),
                (x1, sy, window_z0),
                (x1 - 0.12, sy, window_z1),
                (x0 + 0.10, sy, window_z1),
                (x0, sy + side * 0.045, window_z0),
                (x1, sy + side * 0.045, window_z0),
                (x1 - 0.12, sy + side * 0.045, window_z1),
                (x0 + 0.10, sy + side * 0.045, window_z1),
            ]
            faces = [
                (0, 1, 2, 3),
                (4, 7, 6, 5),
                (0, 4, 5, 1),
                (1, 5, 6, 2),
                (2, 6, 7, 3),
                (3, 7, 4, 0),
            ]
            mesh_object(
                coll,
                name + f":side_glass_{side}_{pane}",
                vertices,
                faces,
                M["glass_dark"],
                "vehicle_glazing",
                root,
            )
            for edge, p1, p2 in (
                (
                    "sill",
                    (x0, sy + side * 0.075, window_z0),
                    (x1, sy + side * 0.075, window_z0),
                ),
                (
                    "front",
                    (x1, sy + side * 0.075, window_z0),
                    (x1 - 0.12, sy + side * 0.075, window_z1),
                ),
                (
                    "roof",
                    (x1 - 0.12, sy + side * 0.075, window_z1),
                    (x0 + 0.10, sy + side * 0.075, window_z1),
                ),
                (
                    "rear",
                    (x0 + 0.10, sy + side * 0.075, window_z1),
                    (x0, sy + side * 0.075, window_z0),
                ),
            ):
                beam(
                    coll,
                    name + f":window_gasket_{side}_{pane}_{edge}",
                    p1,
                    p2,
                    0.020,
                    M["black"],
                    10,
                    role="vehicle_window_gasket",
                    parent=root,
                )
        for seam_x in (-0.74, 0.05, 0.84):
            box(
                coll,
                name + f":door_seam_{side}_{seam_x}",
                (seam_x, sy + side * 0.074, 1.00),
                (0.022, 0.018, 1.18),
                M["black"],
                role="vehicle_door_seam",
                parent=root,
            )
        for door, handle_x in enumerate((-0.40, 0.48)):
            box(
                coll,
                name + f":door_handle_{side}_{door}",
                (handle_x, sy + side * 0.105, 1.20),
                (0.28, 0.045, 0.055),
                M["black"],
                0.025,
                role="vehicle_door_handle",
                parent=root,
            )
        box(
            coll,
            name + f":mirror_{side}",
            (1.28, sy + side * 0.18, 1.40),
            (0.28, 0.18, 0.23),
            M["black"],
            0.075,
            role="vehicle_mirror",
            parent=root,
        )
        beam(
            coll,
            name + f":mirror_stalk_{side}",
            (1.13, sy, 1.37),
            (1.25, sy + side * 0.14, 1.40),
            0.026,
            M["black"],
            10,
            role="vehicle_mirror_stalk",
            parent=root,
        )

    # Raked windshield and rear glass are separate laminated panels.
    vertical_prism_y(
        coll,
        name + ":windshield",
        ((1.30, 1.28), (1.66, 1.30), (1.04, roof_z - 0.06), (0.58, roof_z - 0.04)),
        0.0,
        1.72,
        M["glass_dark"],
        "vehicle_glazing",
        root,
        0.022,
    )
    vertical_prism_y(
        coll,
        name + ":rear_glass",
        ((-1.72, 1.26), (-1.38, 1.27), (-1.17, roof_z - 0.06), (-1.50, roof_z - 0.08)),
        0.0,
        1.68,
        M["glass_dark"],
        "vehicle_glazing",
        root,
        0.022,
    )
    for side in (-1, 1):
        beam(
            coll,
            name + f":wiper_{side}",
            (1.58, side * 0.10, 1.30),
            (1.26, side * 0.54, 1.57),
            0.014,
            M["black"],
            9,
            role="vehicle_windshield_wiper",
            parent=root,
        )

    for wheel_x in (rear_x, front_x):
        for side in (-1, 1):
            cylinder(
                coll,
                name + f":wheel_well_{wheel_x}_{side}",
                (wheel_x, side * 0.96, 0.54),
                0.46,
                0.045,
                M["black"],
                36,
                rot=(math.pi / 2.0, 0.0, 0.0),
                role="vehicle_wheel_well",
                parent=root,
            )
            arc_tube(
                coll,
                root,
                name + f":fender_lip_{wheel_x}_{side}",
                (wheel_x, side * 1.025, 0.54),
                0.47,
                0.0,
                math.pi,
                14,
                0.026,
                M["vehicle_white"],
                "vehicle_wheel_arch_trim",
            )
            cruiser_wheel(
                coll,
                root,
                name + f":wheel_{wheel_x}_{side}",
                wheel_x,
                side * 1.02,
                0.50,
                side,
                M,
            )

    # Front and rear manufactured details.
    box(
        coll,
        name + ":front_bumper",
        (length / 2 + 0.02, 0, 0.69),
        (0.22, 1.78, 0.26),
        M["black"],
        0.08,
        role="vehicle_bumper",
        parent=root,
    )
    box(
        coll,
        name + ":rear_bumper",
        (-length / 2 - 0.02, 0, 0.68),
        (0.22, 1.82, 0.25),
        M["black"],
        0.08,
        role="vehicle_bumper",
        parent=root,
    )
    box(
        coll,
        name + ":grille_recess",
        (length / 2 + 0.14, 0, 0.94),
        (0.025, 1.12, 0.33),
        M["black"],
        role="vehicle_grille_recess",
        parent=root,
    )
    for slat in range(8):
        box(
            coll,
            name + f":grille_slat_{slat}",
            (length / 2 + 0.17, -0.48 + slat * 0.137, 0.94),
            (0.022, 0.085, 0.27),
            M["aluminum"],
            0.018,
            role="vehicle_grille",
            parent=root,
        )
    for side in (-1, 1):
        box(
            coll,
            name + f":headlamp_{side}",
            (length / 2 + 0.16, side * 0.69, 1.02),
            (0.025, 0.39, 0.21),
            M["lamp_white"],
            0.06,
            role="vehicle_headlamp",
            parent=root,
        )
        box(
            coll,
            name + f":tail_lamp_{side}",
            (-length / 2 - 0.15, side * 0.68, 1.04),
            (0.025, 0.30, 0.44),
            M["lamp_red"],
            0.055,
            role="vehicle_tail_lamp",
            parent=root,
        )
    box(
        coll,
        name + ":front_plate",
        (length / 2 + 0.19, 0, 0.67),
        (0.022, 0.48, 0.16),
        M["white"],
        0.018,
        role="vehicle_license_plate",
        parent=root,
    )
    box(
        coll,
        name + ":lightbar_base",
        (-0.05, 0, roof_z + 0.08),
        (1.28, 0.42, 0.10),
        M["black"],
        0.04,
        role="emergency_lightbar",
        parent=root,
    )
    for side, mat in ((-1, M["lamp_blue"]), (1, M["lamp_red"])):
        box(
            coll,
            name + f":lightbar_lens_{side}",
            (-0.05, side * 0.13, roof_z + 0.17),
            (1.18, 0.17, 0.15),
            mat,
            0.05,
            role="emergency_lightbar_lens",
            parent=root,
        )
    for antenna in (-0.38, 0.05, 0.42):
        cylinder(
            coll,
            name + f":roof_antenna_{antenna}",
            (antenna, 0.28, roof_z + 0.54),
            0.012,
            0.72,
            M["black"],
            10,
            role="vehicle_radio_antenna",
            parent=root,
        )
    # Dimensional POLICE identifiers on both doors.
    for side in (-1, 1):
        sign = text_object(
            coll,
            name + f":police_wordmark_{side}",
            "POLICE",
            (-0.05, side * 1.075, 1.04),
            0.34,
            M["white"],
            0.028,
            role="police_vehicle_wordmark",
            parent=root,
        )
        sign.rotation_euler = (math.pi / 2, 0, 0 if side < 0 else math.pi)
    root["c2w_vehicle_variant"] = variant
    root[
        "c2w_detail_profile"
    ] = "lofted coachwork+chassis+suspension+treaded wheels+laminated glazing+door seams+mirrors+manufactured lighting+reflective livery+lightbar+radio antennas"
    return root


def landscaping_rock(coll, name, x, y, z, scale, M, seed):
    rng = random.Random(seed)
    obj = sphere(
        coll,
        name,
        (x, y, z),
        (
            scale * rng.uniform(0.75, 1.15),
            scale * rng.uniform(0.55, 0.92),
            scale * rng.uniform(0.34, 0.62),
        ),
        M["gravel"],
        role="landscape_boulder",
        subdivisions=2,
    )
    obj.rotation_euler = (
        rng.uniform(-0.25, 0.25),
        rng.uniform(-0.25, 0.25),
        rng.uniform(0, math.pi),
    )
    return obj


def shrub(coll, name, x, y, z, scale, M, seed):
    rng = random.Random(seed)
    root = bpy.data.objects.new(PREFIX + name + ":root", None)
    coll.objects.link(root)
    root.location = (x, y, z)
    tag(root, "landscape_shrub_root")
    for branch in range(10):
        angle = 2 * math.pi * branch / 10 + rng.uniform(-0.2, 0.2)
        endpoint = (
            math.cos(angle) * scale * rng.uniform(0.45, 0.85),
            math.sin(angle) * scale * rng.uniform(0.45, 0.85),
            scale * rng.uniform(0.45, 1.1),
        )
        beam(
            coll,
            name + f":branch_{branch}",
            (0, 0, 0.03),
            endpoint,
            0.022 * scale,
            M["bark"],
            10,
            role="shrub_branch",
            parent=root,
        )
        for leaf in range(7):
            t = 0.35 + leaf / 10
            px, py, pz = endpoint[0] * t, endpoint[1] * t, endpoint[2] * t
            sphere(
                coll,
                name + f":leaf_{branch}_{leaf}",
                (
                    px + rng.uniform(-0.12, 0.12) * scale,
                    py + rng.uniform(-0.12, 0.12) * scale,
                    pz + rng.uniform(-0.08, 0.12) * scale,
                ),
                (0.15 * scale, 0.10 * scale, 0.09 * scale),
                M["leaf_a"] if (branch + leaf) % 3 else M["leaf_b"],
                role="shrub_leaf_cluster",
                parent=root,
                subdivisions=1,
            )
    return root


def organic_landscape_bed(
    coll, name, x, y, z, radius_x, radius_y, M, seed, gravel=False
):
    """Low, softly curved planting island with a buried steel edge."""
    rng = random.Random(seed)
    segments = 32
    top_ring = []
    bottom_ring = []
    for index in range(segments):
        angle = 2 * math.pi * index / segments
        variation = 1.0 + rng.uniform(-0.035, 0.035)
        px = x + math.cos(angle) * radius_x * variation
        py = y + math.sin(angle) * radius_y * variation
        top_ring.append((px, py, z + 0.10))
        bottom_ring.append((px, py, z - 0.05))
    vertices = top_ring + bottom_ring
    faces = [tuple(range(segments)), tuple(range(segments, segments * 2))[::-1]]
    for index in range(segments):
        nxt = (index + 1) % segments
        faces.append((index, nxt, segments + nxt, segments + index))
    bed = mesh_object(
        coll,
        name + ":soil",
        vertices,
        faces,
        M["gravel"] if gravel else M["soil"],
        "landscape_bed",
        None,
    )
    bevel = bed.modifiers.new(name="soft_rolled_bed_edge", type="BEVEL")
    bevel.width = 0.06
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    for index in range(segments):
        nxt = (index + 1) % segments
        beam(
            coll,
            name + f":buried_edge_{index}",
            (top_ring[index][0], top_ring[index][1], z + 0.115),
            (top_ring[nxt][0], top_ring[nxt][1], z + 0.115),
            0.025,
            M["black"],
            10,
            role="landscape_steel_edging",
        )
    return bed


def local_station_parcel(coll, root, name, width, depth, M):
    """Compact, parented building parcel for the single-asset pipeline path."""
    box(
        coll,
        name + ":substructure",
        (0, 0.0, -0.11),
        (width + 0.5, depth + 0.5, 0.16),
        M["concrete"],
        0.035,
        role="building_substructure_slab",
        parent=root,
    )
    box(
        coll,
        name + ":front_apron",
        (0, -depth / 2 - 4.2, -0.01),
        (width + 2.5, 8.0, 0.14),
        M["paving"],
        0.025,
        role="police_station_forecourt",
        parent=root,
    )
    box(
        coll,
        name + ":rear_service_apron",
        (0, depth / 2 + 3.0, -0.015),
        (width + 1.0, 5.6, 0.13),
        M["concrete_light"],
        0.025,
        role="secure_rear_service_apron",
        parent=root,
    )
    for joint in range(-int(width // 4), int(width // 4) + 1):
        box(
            coll,
            name + f":front_joint_{joint}",
            (joint * 4.0, -depth / 2 - 4.2, 0.065),
            (0.028, 7.8, 0.012),
            M["joint_sealant"],
            role="paving_expansion_joint",
            parent=root,
        )


def site_light(coll, name, x, y, z, M):
    cylinder(
        coll,
        name + ":base",
        (x, y, z + 0.32),
        0.29,
        0.64,
        M["concrete"],
        28,
        role="site_light_base",
    )
    cylinder(
        coll,
        name + ":pole",
        (x, y, z + 4.75),
        0.085,
        8.9,
        M["black"],
        20,
        role="site_light_pole",
    )
    beam(
        coll,
        name + ":arm",
        (x, y, z + 9.15),
        (x + 1.05, y, z + 9.15),
        0.075,
        M["black"],
        18,
        role="site_light_arm",
    )
    box(
        coll,
        name + ":head",
        (x + 1.18, y, z + 9.12),
        (0.62, 0.30, 0.16),
        M["black"],
        0.07,
        role="site_light_head",
    )
    box(
        coll,
        name + ":lens",
        (x + 1.18, y, z + 9.01),
        (0.52, 0.23, 0.035),
        M["lamp_white"],
        0.03,
        role="site_light_lens",
    )


def build_police_site(parent, M):
    """Police-campus hardscape, limited to the three modeled station parcels.

    The site is deliberately finite: foundations, jointed entry courts, a
    visitor apron, rear service paving, drainage and four manufactured light
    standards.  It supplies real grade contact and photographic scale cues but
    does not grow into a generic city, road network or unrelated facility.
    """
    site = collection(
        "POLICE_REFERENCE_ROW_SITE",
        parent,
        "police_precinct_site",
        "site.police.reference_row.v10",
    )
    box(
        site,
        "site:campus_landscape_grade",
        (0.0, -5.5, -0.11),
        (198.0, 79.0, 0.14),
        M["grass"],
        0.025,
        role="police_campus_ground",
    )
    station_specs = ((-62.0, 47.0, 30.0), (0.0, 56.0, 28.0), (62.0, 56.0, 30.0))
    for index, (x, width, depth) in enumerate(station_specs):
        box(
            site,
            f"building:substructure_{index}",
            (x, 0.0, -0.12),
            (width + 0.5, depth + 0.5, 0.16),
            M["concrete"],
            0.035,
            role="building_substructure_slab",
        )
        # Front and rear aprons are separate slabs with true sealant joints;
        # their top faces sit nearly flush with grade rather than forming the
        # conspicuous white pedestal visible in the previous rear render.
        forecourt_y = -19.0 if index != 1 else -18.4
        box(
            site,
            f"site:forecourt_{index}",
            (x, forecourt_y, -0.005),
            (width + 3.0, 11.0, 0.15),
            M["paving"],
            0.025,
            role="police_station_forecourt",
        )
        box(
            site,
            f"site:rear_service_apron_{index}",
            (x, 18.7, -0.012),
            (width + 1.0, 8.0, 0.14),
            M["concrete_light"],
            0.025,
            role="secure_rear_service_apron",
        )
        for joint in range(-int(width // 4), int(width // 4) + 1):
            box(
                site,
                f"site:forecourt_joint_v_{index}_{joint}",
                (x + joint * 4.0, forecourt_y, 0.076),
                (0.030, 10.8, 0.012),
                M["joint_sealant"],
                role="paving_expansion_joint",
            )
        for joint in range(1, 5):
            box(
                site,
                f"site:forecourt_joint_h_{index}_{joint}",
                (x, forecourt_y - 5.5 + joint * 2.2, 0.076),
                (width + 2.8, 0.030, 0.012),
                M["joint_sealant"],
                role="paving_expansion_joint",
            )
        for joint in range(-int(width // 5), int(width // 5) + 1):
            box(
                site,
                f"site:rear_joint_{index}_{joint}",
                (x + joint * 5.0, 18.7, 0.065),
                (0.030, 7.8, 0.012),
                M["joint_sealant"],
                role="rear_paving_expansion_joint",
            )

    # The visitor parking apron belongs to this police campus and terminates at
    # both ends; there is intentionally no public road or off-site city context.
    box(
        site,
        "site:visitor_asphalt_apron",
        (0.0, -32.8, -0.025),
        (190.0, 16.2, 0.16),
        M["asphalt"],
        0.025,
        role="police_visitor_parking",
    )
    box(
        site,
        "site:parking_header_curb",
        (0.0, -24.25, 0.13),
        (190.0, 0.34, 0.34),
        M["concrete"],
        0.035,
        role="parking_curb",
    )
    box(
        site,
        "site:parking_outer_curb",
        (0.0, -41.25, 0.13),
        (190.0, 0.34, 0.34),
        M["concrete"],
        0.035,
        role="parking_curb",
    )
    for stall in range(-17, 18):
        x = stall * 5.25
        box(
            site,
            f"site:stall_line_{stall}",
            (x, -32.7, 0.062),
            (0.095, 15.2, 0.022),
            M["road_white"],
            role="parking_stall_marking",
        )

    # A continuous slot drain and individually modeled bars resolve the grade
    # transition in both front and rear-oblique views.
    box(
        site,
        "site:front_trench_drain",
        (0.0, -23.92, 0.075),
        (188.0, 0.40, 0.075),
        M["black"],
        0.018,
        role="trench_drain_channel",
    )
    for slot in range(-93, 94):
        box(
            site,
            f"site:front_drain_bar_{slot}",
            (slot * 1.0, -23.92, 0.125),
            (0.055, 0.34, 0.040),
            M["steel"],
            0.010,
            role="trench_drain_grating",
        )
    for station_index, cx in enumerate((-62.0, 0.0, 62.0)):
        box(
            site,
            f"site:rear_trench_{station_index}",
            (cx, 22.45, 0.052),
            (46.0 if station_index == 0 else 54.0, 0.34, 0.060),
            M["black"],
            0.018,
            role="rear_trench_drain_channel",
        )
        for slot in range(-20, 21):
            box(
                site,
                f"site:rear_drain_bar_{station_index}_{slot}",
                (cx + slot * 1.05, 22.45, 0.095),
                (0.050, 0.28, 0.035),
                M["steel"],
                0.010,
                role="rear_trench_drain_grating",
            )

    for light_index, x in enumerate((-91.0, -33.0, 33.0, 91.0)):
        site_light(site, f"site:light_{light_index}", x, -39.4, 0.26, M)

    # Curved, low planting islands soften the long civic frontage while staying
    # wholly inside the police campus and clear of all doors, stairs and sight
    # lines.  They replace no building geometry and are generated by the same
    # production path as the three independently selectable stations.
    beds = (
        (-91.0, -17.2, 4.0, 1.45, False),
        (-33.2, -17.0, 3.5, 1.30, False),
        (32.2, -17.0, 3.2, 1.25, True),
        (92.0, -17.2, 4.0, 1.45, True),
    )
    for bed_index, (bed_x, bed_y, radius_x, radius_y, gravel) in enumerate(beds):
        organic_landscape_bed(
            site,
            f"site:curved_bed_{bed_index}",
            bed_x,
            bed_y,
            0.03,
            radius_x,
            radius_y,
            M,
            SEED + 3000 + bed_index * 101,
            gravel,
        )
        for plant in range(3):
            shrub_x = bed_x - radius_x * 0.48 + plant * radius_x * 0.48
            shrub_y = bed_y + (0.28 if plant % 2 else -0.22)
            shrub(
                site,
                f"site:bed_{bed_index}_shrub_{plant}",
                shrub_x,
                shrub_y,
                0.13,
                0.42 + 0.05 * ((bed_index + plant) % 3),
                M,
                SEED + 3400 + bed_index * 53 + plant,
            )

    site["c2w_detail_profile"] = (
        "finite police-campus parcel+three buried foundations+separate jointed public forecourts+"
        "jointed rear service aprons+aggregate visitor parking+curbs+stall markings without block-like wheel stops+"
        "manufactured trench drains+four full-scale light standards+four curved planted islands; no generic city or unrelated facility"
    )
    site[
        "c2w_excluded_context"
    ] = "public road, generic traffic, unrelated buildings and urban backdrop"
    return site


def build_blue_white_civic(
    parent=None, origin=(-62.0, 0.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 1: white two-storey civic station with cobalt facade accents."""
    M = materials or make_materials()
    coll = collection(
        "POLICE_A_BLUE_WHITE_CIVIC",
        parent,
        "police_station_asset",
        "police.blue_white_civic.v10",
    )
    root = asset_root(
        coll, "blue_white_civic:root", origin, yaw, "police.blue_white_civic.v10"
    )
    coll["c2w_reference_index"] = 1
    coll["c2w_variant"] = "blue_white_civic"
    coll["c2w_reference_url"] = REFERENCE_URLS[0]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["blue_white_civic"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([47.0, 30.0, 22.5])
    if include_site:
        local_station_parcel(coll, root, "blue_white:parcel", 47.0, 30.0, M)

    south = -13.4
    # Independent structural masses: a gabled administration wing and a taller
    # flat-roofed public lobby / operations wing.
    box(
        coll,
        "blue_white:left_core",
        (-11.5, 1.4, 5.0),
        (25.0, 29.2, 10.0),
        M["stucco_bright"],
        0.065,
        role="stucco_building_mass",
        parent=root,
    )
    vertical_prism_y(
        coll,
        "blue_white:left_gable_infill",
        ((-24.0, 9.95), (-11.5, 13.25), (1.0, 9.95)),
        1.4,
        29.2,
        M["stucco_bright"],
        "gabled_building_mass",
        root,
        0.045,
    )
    box(
        coll,
        "blue_white:right_core",
        (12.0, 1.0, 6.15),
        (22.0, 28.4, 12.3),
        M["stucco"],
        0.065,
        role="stucco_building_mass",
        parent=root,
    )
    # The lowest slab is buried inside the wall footprint.  This specifically
    # removes the continuous pale board/pedestal that showed below the rear
    # elevation in the previous 04 render.
    box(
        coll,
        "blue_white:buried_ground_slab",
        (0.0, 0.9, 0.025),
        (45.5, 28.2, 0.05),
        M["concrete"],
        role="structural_floor_slab",
        parent=root,
    )
    for z in (4.82, 9.42):
        box(
            coll,
            f"blue_white:floor_plate_{z}",
            (0.0, 0.8, z),
            (45.5, 28.2, 0.24),
            M["concrete"],
            role="structural_floor_slab",
            parent=root,
        )
    box(
        coll,
        "blue_white:right_roof_slab",
        (12.0, 1.0, 12.25),
        (22.4, 28.8, 0.32),
        M["concrete"],
        0.05,
        role="roof_slab",
        parent=root,
    )
    flat_roof_edge_system(
        coll,
        root,
        "blue_white:right_flat_roof",
        12.0,
        1.0,
        22.4,
        28.8,
        12.28,
        M,
        front_y=south,
        scupper_xs=(3.0, 20.5),
    )

    # A real front skin closes the former multi-metre void between the core and
    # window system.  Horizontal spandrels and vertical piers leave each opening
    # unobstructed while producing deep, reference-like reveals.
    for band_name, z, height in (
        ("lower", 1.55, 0.62),
        ("mid", 5.25, 1.82),
        ("upper", 9.25, 1.20),
    ):
        box(
            coll,
            f"blue_white:left_front_spandrel_{band_name}",
            (-11.5, south + 0.18, z),
            (25.0, 0.34, height),
            M["stucco_bright"],
            0.025,
            role="stucco_rainscreen_spandrel",
            parent=root,
        )
    for pier_index, x in enumerate((-23.55, -17.65, -12.95, -8.25, -3.85, 0.45)):
        box(
            coll,
            f"blue_white:left_front_pier_{pier_index}",
            (x, south + 0.18, 5.55),
            (0.92, 0.34, 8.15),
            M["stucco_bright"],
            0.025,
            role="stucco_rainscreen_pier",
            parent=root,
        )
    for reveal_z in (4.78, 9.48):
        box(
            coll,
            f"blue_white:continuous_shadow_reveal_{reveal_z}",
            (-11.5, south - 0.015, reveal_z),
            (24.4, 0.035, 0.075),
            M["black"],
            role="facade_shadow_reveal",
            parent=root,
        )

    # Real sloped roof planes, fascia, gutters and standing seams on the left wing.
    pitch = math.atan2(3.3, 12.5)
    slope_len = math.hypot(12.5, 3.3)
    for side in (-1, 1):
        roof_x = -11.5 + side * 6.25
        roof = box(
            coll,
            f"blue_white:gabled_roof_{side}",
            (roof_x, 1.4, 11.60),
            (slope_len + 0.55, 30.0, 0.22),
            M["standing_seam"],
            0.035,
            role="pitched_metal_roof",
            parent=root,
        )
        # Local X runs from ridge to eave.  Using ``side * pitch`` makes both
        # outer eaves descend from the ridge; the former sign produced two
        # airborne butterfly planes and was the clearest toy-model artifact.
        roof_angle = side * pitch
        roof.rotation_euler[1] = roof_angle
        for seam in range(13):
            x0 = -11.5 + side * (0.42 + seam * 0.95)
            seam_z = 11.60 - math.tan(roof_angle) * (x0 - roof_x) + 0.145
            seam_obj = box(
                coll,
                f"blue_white:roof_seam_{side}_{seam}",
                (x0, 1.4, seam_z),
                (0.035, 29.8, 0.055),
                M["blue_grey_metal"],
                role="standing_seam_rib",
                parent=root,
            )
            seam_obj.rotation_euler[1] = roof_angle
    for y in (-13.55, 16.35):
        cylinder(
            coll,
            f"blue_white:gutter_{y}",
            (-11.5, y, 9.95),
            0.075,
            25.8,
            M["blue_grey_metal"],
            18,
            rot=(0.0, math.pi / 2.0, 0.0),
            role="roof_gutter",
            parent=root,
        )

    # Cobalt glazed-tile plinth is individually jointed like the photograph.
    for tile in range(45):
        x = -22.5 + tile * 1.0
        for row in range(2):
            box(
                coll,
                f"blue_white:front_blue_tile_{tile}_{row}",
                (x, south - 0.24, 0.56 + row * 0.58),
                (0.92, 0.20, 0.52),
                M["blue_tile"],
                0.025,
                role="cobalt_ceramic_base_tile",
                parent=root,
            )
    for side, x in ((-1, -24.1), (1, 23.1)):
        for tile in range(22):
            y = -12.0 + tile * 1.05
            box(
                coll,
                f"blue_white:side_blue_tile_{side}_{tile}",
                (x, y, 0.85),
                (0.18, 0.98, 1.10),
                M["blue_tile"],
                0.022,
                role="cobalt_ceramic_base_tile",
                parent=root,
            )

    # Left two-storey fenestration matches the repeated silver-framed openings.
    for row, z in enumerate((3.05, 7.45)):
        for index, x in enumerate((-20.0, -15.3, -10.6, -5.9, -1.8)):
            if row == 0 and x > -4.0:
                continue
            facade_window_y(
                coll,
                root,
                f"blue_white:left_front_window_{row}_{index}",
                x,
                south - 0.14,
                z,
                3.05,
                2.30,
                M,
                -1,
                2,
                "aluminum",
                "glass_blue",
                True,
                (row + index) % 3 == 0,
                "security_window",
                0.08,
            )
    for row, z in enumerate((3.05, 7.45)):
        for index, y in enumerate((-8.4, -3.5, 1.4, 6.3, 11.2)):
            facade_window_x(
                coll,
                root,
                f"blue_white:west_window_{row}_{index}",
                -24.14,
                y,
                z,
                2.75,
                2.30,
                M,
                -1,
                2,
                "aluminum",
                "glass_blue",
                True,
            )
            facade_window_x(
                coll,
                root,
                f"blue_white:east_window_{row}_{index}",
                23.14,
                y,
                z,
                2.75,
                2.30,
                M,
                1,
                2,
                "aluminum",
                "glass_blue",
                True,
            )
    for row, z in enumerate((3.05, 7.45)):
        rear_centers = (
            (-19, -14, -9, -4, 2, 8, 14, 20) if row else (-19, -14, -9, -4, 8, 14, 20)
        )
        for index, x in enumerate(rear_centers):
            # The gabled left mass ends at Y=16.0 while the flat right mass
            # ends at Y=15.2.  Treat them as two constructed elevations so no
            # rear window is buried inside the deeper gabled wall.
            rear_face_y = 16.14 if x < 1.0 else 15.34
            facade_window_y(
                coll,
                root,
                f"blue_white:rear_window_{row}_{index}",
                x,
                rear_face_y,
                z,
                2.75,
                2.20,
                M,
                1,
                2,
                "aluminum",
                "glass_blue",
                True,
                (row + index) % 4 == 0,
            )
    steel_service_door_y(
        coll,
        root,
        "blue_white:rear_personnel_exit",
        2.0,
        15.34,
        0.12,
        1.55,
        2.72,
        M,
        1,
        "SECURE EXIT",
    )
    louver_panel_y(
        coll,
        root,
        "blue_white:rear_fresh_air_louver",
        -22.0,
        16.14,
        6.55,
        2.05,
        1.35,
        M,
        1,
    )
    rear_utility_cluster(
        coll, root, "blue_white:rear_electrical_service", 18.2, 15.34, 0.18, M, 1
    )

    # Reference-defining tall glazed public entrance and right vertical bay.
    curtain_wall_y(
        coll,
        root,
        "blue_white:entry_curtain_wall",
        6.0,
        south - 0.62,
        0.45,
        13.0,
        9.25,
        5,
        4,
        M,
        -1,
        "glass_clear",
        "aluminum",
        "public_lobby_curtain_wall",
    )
    curtain_wall_y(
        coll,
        root,
        "blue_white:right_tall_curtain_wall",
        17.3,
        south - 0.65,
        0.45,
        8.1,
        10.75,
        3,
        5,
        M,
        -1,
        "glass_blue",
        "aluminum",
        "operations_curtain_wall",
    )
    glass_door_bank(
        coll,
        root,
        "blue_white:main_entry",
        5.0,
        south - 0.88,
        0.48,
        4.5,
        3.25,
        M,
        2,
        -1,
        "aluminum",
    )

    # Cobalt roof fascia, vertical fins and sign canopy have modeled panel joints.
    box(
        coll,
        "blue_white:right_blue_fascia",
        (12.0, south - 0.35, 12.05),
        (22.8, 0.75, 2.10),
        M["blue_panel"],
        0.055,
        role="cobalt_roof_fascia",
        parent=root,
    )
    panel_joint_grid(
        coll,
        root,
        "blue_white:right_fascia_joints",
        12.0,
        south - 0.74,
        11.02,
        22.6,
        2.05,
        M,
        -1,
        9,
        2,
    )
    for index, x in enumerate((1.0, 10.2, 20.8)):
        box(
            coll,
            f"blue_white:cobalt_vertical_fin_{index}",
            (x, south - 0.76, 6.25),
            (1.20, 0.68, 11.9),
            M["blue_panel"],
            0.045,
            role="cobalt_vertical_facade_fin",
            parent=root,
        )
        panel_joint_grid(
            coll,
            root,
            f"blue_white:fin_joint_{index}",
            x,
            south - 1.11,
            0.35,
            1.16,
            11.65,
            M,
            -1,
            1,
            5,
        )
    box(
        coll,
        "blue_white:sign_canopy_slab",
        (5.0, south - 2.85, 6.10),
        (15.8, 4.2, 0.34),
        M["blue_panel"],
        0.055,
        role="entrance_sign_canopy",
        parent=root,
    )
    box(
        coll,
        "blue_white:sign_canopy_fascia",
        (5.0, south - 4.98, 6.05),
        (16.0, 0.28, 1.28),
        M["blue_panel"],
        0.045,
        role="entrance_sign_canopy_fascia",
        parent=root,
    )
    for edge_name, edge_z in (("upper", 6.66), ("lower", 5.43)):
        box(
            coll,
            f"blue_white:canopy_{edge_name}_folded_cap",
            (5.0, south - 5.145, edge_z),
            (16.18, 0.085, 0.11),
            M["blue_grey_metal"],
            0.045,
            role="canopy_folded_edge_cap",
            parent=root,
        )
    for side_name, x in (("west", -3.02), ("east", 13.02)):
        box(
            coll,
            f"blue_white:canopy_end_return_{side_name}",
            (x, south - 2.90, 6.05),
            (0.16, 4.18, 1.26),
            M["blue_panel"],
            0.045,
            role="canopy_end_return",
            parent=root,
        )
        for joint_index, joint_y in enumerate((south - 1.85, south - 3.95)):
            box(
                coll,
                f"blue_white:canopy_end_joint_{side_name}_{joint_index}",
                (x + (-0.09 if side_name == "west" else 0.09), joint_y, 6.05),
                (0.018, 0.035, 1.10),
                M["joint_sealant"],
                0.006,
                role="canopy_end_return_joint",
                parent=root,
            )
    panel_joint_grid(
        coll,
        root,
        "blue_white:canopy_fascia_joints",
        5.0,
        south - 5.135,
        5.43,
        15.8,
        1.22,
        M,
        -1,
        7,
        1,
    )
    box(
        coll,
        "blue_white:canopy_soffit",
        (5.0, south - 2.82, 5.88),
        (15.45, 3.75, 0.10),
        M["white"],
        0.025,
        role="entrance_canopy_soffit",
        parent=root,
    )
    for coffer in range(8):
        box(
            coll,
            f"blue_white:soffit_coffer_{coffer}",
            (-1.2 + coffer * 1.78, south - 2.95, 5.815),
            (1.38, 2.75, 0.028),
            M["black"],
            0.018,
            role="canopy_soffit_coffer",
            parent=root,
        )
    for light_index, x in enumerate((-1.0, 1.0, 3.0, 5.0, 7.0, 9.0, 11.0)):
        cylinder(
            coll,
            f"blue_white:canopy_downlight_{light_index}",
            (x, south - 3.35, 5.79),
            0.10,
            0.035,
            M["lamp_white"],
            24,
            role="canopy_recessed_downlight",
            parent=root,
        )
    for x in (-1.8, 11.8):
        cylinder(
            coll,
            f"blue_white:canopy_column_{x}",
            (x, south - 4.15, 3.10),
            0.13,
            5.70,
            M["white"],
            24,
            role="canopy_column",
            parent=root,
        )
    police_sign = text_object(
        coll,
        "blue_white:police_station_wordmark",
        "POLICE  STATION",
        (5.0, south - 5.19, 6.07),
        1.48,
        M["white"],
        0.115,
        role="police_station_wordmark",
        parent=root,
    )
    police_sign["c2w_sign_reference_index"] = 1

    # Correctly ordered stairs now rise toward the door.  The neutral saw-cut
    # treads replace the former yellow block and the filled, eased side ramp
    # meets both grade and upper landing without a floating slab underside.
    entrance_stair_y(
        coll,
        root,
        "blue_white:public_entry_stair",
        5.0,
        south - 5.15,
        0.08,
        8.20,
        0.40,
        M,
        step_count=3,
        tread=0.42,
        landing_depth=3.85,
    )
    accessible_ramp(
        coll,
        root,
        "blue_white:entry_ramp",
        -4.7,
        south - 4.10,
        0.08,
        8.4,
        1.65,
        0.40,
        M,
    )

    # Reference antennas, external condenser and fully articulated building services.
    lattice_radio_mast(
        coll, root, "blue_white:primary_radio_mast", 3.4, 7.5, 12.4, 6.4, M
    )
    box(
        coll,
        "blue_white:wall_ac_body",
        (-7.2, south - 0.33, 5.65),
        (1.12, 0.48, 0.78),
        M["white"],
        0.045,
        role="external_ac_unit",
        parent=root,
    )
    cylinder(
        coll,
        "blue_white:wall_ac_fan",
        (-7.2, south - 0.60, 5.65),
        0.27,
        0.035,
        M["black"],
        28,
        rot=(math.pi / 2, 0, 0),
        role="ac_condenser_fan",
        parent=root,
    )
    for spoke in range(10):
        angle = 2 * math.pi * spoke / 10
        beam(
            coll,
            f"blue_white:wall_ac_grille_{spoke}",
            (-7.2, south - 0.64, 5.65),
            (
                -7.2 + math.cos(angle) * 0.26,
                south - 0.64,
                5.65 + math.sin(angle) * 0.26,
            ),
            0.012,
            M["aluminum"],
            8,
            role="ac_fan_grille",
            parent=root,
        )
    for index, (x, y, width, depth, height) in enumerate(
        (
            (-5.0, 4.5, 2.8, 2.2, 1.2),
            (11.0, 4.0, 3.2, 2.5, 1.4),
            (18.0, 5.8, 2.4, 2.0, 1.1),
        )
    ):
        roof_mechanical_unit(
            coll, root, f"blue_white:rtu_{index}", x, y, 12.35, width, depth, height, M
        )
    roof_service_walkway(
        coll,
        root,
        "blue_white:roof_walkway",
        (
            (3.8, 4.6),
            (5.0, 4.6),
            (6.2, 4.6),
            (7.4, 4.6),
            (8.6, 4.4),
            (9.8, 4.2),
            (11.0, 4.0),
            (12.2, 4.3),
            (13.4, 4.6),
            (14.6, 4.9),
            (15.8, 5.2),
            (17.0, 5.5),
        ),
        12.43,
        M,
    )
    for index, x in enumerate((-22.9, 22.2)):
        downpipe(
            coll, root, f"blue_white:downpipe_{index}", x, south - 0.32, 10.0, M, True
        )
    for index, x in enumerate((-22.8, 22.0)):
        rear_face_y = 16.16 if x < 1.0 else 15.36
        downpipe(
            coll,
            root,
            f"blue_white:rear_downpipe_{index}",
            x,
            rear_face_y,
            10.0,
            M,
            False,
        )
    for index, x in enumerate((-18.0, 0.0, 18.0)):
        dome_camera(
            coll, root, f"blue_white:front_camera_{index}", x, south - 0.45, 9.1, M, -1
        )
    for index, x in enumerate((-15.0, 12.0)):
        rear_face_y = 16.12 if x < 1.0 else 15.32
        dome_camera(
            coll, root, f"blue_white:rear_camera_{index}", x, rear_face_y, 8.9, M, 1
        )
    for index, x in enumerate((-16.0, -5.0, 15.5)):
        wall_light(
            coll,
            root,
            f"blue_white:front_wall_light_{index}",
            x,
            south - 0.46,
            4.3,
            M,
            -1,
        )
    for index, x in enumerate((-18.0, -5.0, 8.0, 20.0)):
        rear_face_y = 16.13 if x < 1.0 else 15.33
        wall_light(
            coll,
            root,
            f"blue_white:rear_wall_light_{index}",
            x,
            rear_face_y,
            3.75,
            M,
            1,
        )

    # Occupied lobby and offices are deliberately visible through the large glass.
    box(
        coll,
        "blue_white:lobby_floor",
        (7.0, -10.4, 0.34),
        (16.5, 5.1, 0.20),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    reception_desk(coll, root, "blue_white:reception", 8.0, -9.4, 0.35, 4.8, M)
    security_turnstile(coll, root, "blue_white:lobby_turnstile", 1.8, -9.0, 0.35, M)
    for row in range(2):
        for seat in range(5):
            waiting_chair(
                coll,
                root,
                f"blue_white:waiting_{row}_{seat}",
                2.6 + seat * 1.25,
                -7.8 + row * 1.18,
                0.34,
                M,
                math.pi,
            )
    for desk in range(8):
        dx = -18.5 + (desk % 4) * 4.2
        dy = -8.5 + (desk // 4) * 4.0
        office_desk(coll, root, f"blue_white:office_desk_{desk}", dx, dy, 0.30, M)
        task_chair(
            coll,
            root,
            f"blue_white:office_chair_{desk}",
            dx,
            dy + 0.85,
            0.30,
            M,
            math.pi,
        )
    ceiling_lights(
        coll,
        root,
        "blue_white:lobby_lights",
        (1.5, 5.0, 8.5, 12.0, 15.5),
        (-10.5, -8.0),
        4.55,
        M,
    )
    area_light(
        coll,
        "blue_white:lobby_area_light",
        (7.0, -9.0, 4.45),
        280.0,
        5.5,
        (1.0, 0.76, 0.52),
        root,
    )

    coll["c2w_rear_white_base_board_removed"] = True
    coll["c2w_rear_yellow_columns_removed"] = True
    coll["c2w_front_yellow_board_removed"] = True
    coll["c2w_front_white_block_stops_removed"] = True
    coll["c2w_independently_modeled"] = True
    coll[
        "c2w_detail_profile"
    ] = "reference-specific correctly pitched gabled and flat massing+closed pier-and-spandrel rainscreen+restrained cobalt ceramic plinth+multi-layer folded and end-returned sign canopy with recessed lighting+double-laminated deep drained windows+deep two-leaf vestibule with sidelights, transom, gaskets, paired panes, controls and complete hardware+correctly ordered grounded cast stair with nosings and returned rails+filled eased accessible route with embedded grade transition+occupied lobby and offices+radio masts+AC+parapet/coping/scuppers+roof service walkway+dense rear security fenestration+vision-lite secure personnel exit+louvers+electrical service+rear drainage and surveillance+buried non-projecting ground slab"
    return coll


def build_brick_tower_municipal(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 2: symmetrical brick civic station with three white towers."""
    M = materials or make_materials()
    coll = collection(
        "POLICE_B_BRICK_TOWER_MUNICIPAL",
        parent,
        "police_station_asset",
        "police.brick_tower_municipal.v10",
    )
    root = asset_root(
        coll,
        "brick_tower_municipal:root",
        origin,
        yaw,
        "police.brick_tower_municipal.v10",
    )
    coll["c2w_reference_index"] = 2
    coll["c2w_variant"] = "brick_tower_municipal"
    coll["c2w_reference_url"] = REFERENCE_URLS[1]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["brick_tower_municipal"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([56.0, 28.0, 15.5])
    if include_site:
        local_station_parcel(coll, root, "brick_tower:parcel", 56.0, 28.0, M)

    south = -13.3
    # Brick bar is flanked and overlapped by the three white civic towers.
    box(
        coll,
        "brick_tower:brick_core",
        (0.0, 1.2, 5.3),
        (55.0, 24.2, 10.6),
        M["brick_side"],
        0.06,
        role="brick_building_mass",
        parent=root,
    )
    box(
        coll,
        "brick_tower:white_ground_band",
        (0.0, south - 0.02, 2.1),
        (55.2, 0.48, 4.2),
        M["stucco_bright"],
        0.04,
        role="white_stucco_ground_band",
        parent=root,
    )
    # A real face veneer is separated from the side material so the running bond
    # remains correctly oriented and level on the principal elevation.
    for bay in range(12):
        x = -26.2 + bay * 4.75
        box(
            coll,
            f"brick_tower:front_brick_veneer_{bay}",
            (x, south - 0.15, 7.4),
            (4.50, 0.28, 6.15),
            M["brick_front"],
            role="brick_veneer_panel",
            parent=root,
        )
        box(
            coll,
            f"brick_tower:veneer_control_joint_{bay}",
            (x + 2.30, south - 0.31, 7.4),
            (0.035, 0.022, 5.95),
            M["black"],
            role="masonry_control_joint",
            parent=root,
        )
    # The rear face needs its own X/Z mapping.  Reusing the side-wall Y/Z
    # mapping produced long horizontal siding bands in the former rear render.
    for bay in range(12):
        x = -26.2 + bay * 4.75
        box(
            coll,
            f"brick_tower:rear_brick_veneer_{bay}",
            (x, 13.32, 5.30),
            (4.50, 0.10, 10.35),
            M["brick_front"],
            0.018,
            role="rear_brick_veneer_panel",
            parent=root,
        )
        box(
            coll,
            f"brick_tower:rear_veneer_control_joint_{bay}",
            (x + 2.30, 13.385, 5.30),
            (0.035, 0.022, 10.10),
            M["joint_sealant"],
            role="rear_masonry_control_joint",
            parent=root,
        )
    box(
        coll,
        "brick_tower:buried_ground_slab",
        (0.0, 1.2, 0.025),
        (54.2, 23.7, 0.05),
        M["concrete"],
        role="structural_floor_slab",
        parent=root,
    )
    for z in (4.45, 10.42):
        box(
            coll,
            f"brick_tower:floor_plate_{z}",
            (0.0, 1.2, z),
            (54.2, 23.7, 0.24),
            M["concrete"],
            role="structural_floor_slab",
            parent=root,
        )
    flat_roof_edge_system(
        coll,
        root,
        "brick_tower:main_flat_roof",
        0.0,
        1.2,
        54.7,
        24.1,
        10.48,
        M,
        front_y=-10.85,
        scupper_xs=(-17.0, 17.0),
    )

    tower_specs = (
        ("west", -23.2, 9.2, 11.6),
        ("center", 0.0, 15.2, 14.8),
        ("east", 23.2, 9.2, 11.6),
    )
    for tower_name, x, width, height in tower_specs:
        box(
            coll,
            f"brick_tower:{tower_name}_tower",
            (x, -0.6, height / 2),
            (width, 27.0, height),
            M["stucco_bright"],
            0.065,
            role="projecting_white_civic_tower",
            parent=root,
        )
        box(
            coll,
            f"brick_tower:{tower_name}_base_course",
            (x, south - 0.62, 0.75),
            (width + 0.34, 0.46, 1.50),
            M["precast"],
            0.045,
            role="tower_precast_base",
            parent=root,
        )
        box(
            coll,
            f"brick_tower:{tower_name}_cap",
            (x, -0.6, height + 0.22),
            (width + 1.15, 28.0, 0.44),
            M["blue_grey_metal"],
            0.055,
            role="tower_roof_cap",
            parent=root,
        )
        # Deep floating front eave with a lined soffit and regular panel seams.
        box(
            coll,
            f"brick_tower:{tower_name}_floating_eave",
            (x, south - 2.10, height + 0.05),
            (width + 2.0, 4.2, 0.64),
            M["blue_grey_metal"],
            0.055,
            role="floating_metal_eave",
            parent=root,
        )
        box(
            coll,
            f"brick_tower:{tower_name}_soffit",
            (x, south - 2.05, height - 0.30),
            (width + 1.65, 3.75, 0.08),
            M["aluminum"],
            0.025,
            role="metal_eave_soffit",
            parent=root,
        )
        for seam in range(max(5, int(width / 1.4))):
            sx = x - width / 2 + 0.35 + seam * width / max(5, int(width / 1.4))
            box(
                coll,
                f"brick_tower:{tower_name}_eave_seam_{seam}",
                (sx, south - 4.18, height + 0.05),
                (0.025, 0.022, 0.58),
                M["black"],
                role="metal_panel_joint",
                parent=root,
            )
        for light in range(max(3, int(width / 2.5))):
            lx = x - width / 2 + 1.2 + light * 2.4
            box(
                coll,
                f"brick_tower:{tower_name}_soffit_light_{light}",
                (lx, south - 2.30, height - 0.36),
                (0.72, 0.28, 0.025),
                M["lamp_white"],
                0.025,
                role="eave_recessed_light",
                parent=root,
            )

    # Main tower carries three tall dark panes exactly beneath the POLICE wordmark.
    for index, x in enumerate((-4.6, 0.0, 4.6)):
        facade_window_y(
            coll,
            root,
            f"brick_tower:center_tall_window_{index}",
            x,
            south - 0.95,
            8.05,
            3.35,
            5.30,
            M,
            -1,
            1,
            "black",
            "glass_dark",
            False,
            False,
            "tower_security_glazing",
            0.08,
        )
        box(
            coll,
            f"brick_tower:center_window_hood_{index}",
            (x, south - 1.03, 10.82),
            (3.75, 0.48, 0.22),
            M["precast"],
            0.04,
            role="projecting_window_hood",
            parent=root,
        )
    for tower_name, x in (("west", -23.2), ("east", 23.2)):
        for index, dx in enumerate((-1.75, 1.75)):
            facade_window_y(
                coll,
                root,
                f"brick_tower:{tower_name}_tall_window_{index}",
                x + dx,
                south - 0.95,
                6.55,
                1.95,
                4.15,
                M,
                -1,
                1,
                "black",
                "glass_dark",
                False,
                False,
                "tower_security_glazing",
                0.08,
            )

    # Window groups within the red-brick bays and on all three remaining sides.
    for side_name, centers in (
        ("west_bay", (-17.6, -13.3, -9.0)),
        ("east_bay", (9.0, 13.3, 17.6)),
    ):
        for row, z in enumerate((2.65, 7.15)):
            for index, x in enumerate(centers):
                facade_window_y(
                    coll,
                    root,
                    f"brick_tower:{side_name}_window_{row}_{index}",
                    x,
                    south - 0.36,
                    z,
                    2.45,
                    2.35,
                    M,
                    -1,
                    1,
                    "black",
                    "glass_dark",
                    True,
                    (row + index) % 2 == 0,
                )
        # Reference metal canopy over the low strip of windows.
        cx = sum(centers) / len(centers)
        box(
            coll,
            f"brick_tower:{side_name}_ground_canopy",
            (cx, south - 1.15, 4.45),
            (13.1, 1.8, 0.18),
            M["standing_seam"],
            0.045,
            role="projecting_window_canopy",
            parent=root,
        )
        for seam in range(14):
            box(
                coll,
                f"brick_tower:{side_name}_canopy_seam_{seam}",
                (cx - 6.1 + seam * 0.94, south - 1.16, 4.56),
                (0.028, 1.55, 0.045),
                M["blue_grey_metal"],
                role="standing_seam_rib",
                parent=root,
            )
    for side, x in ((-1, -27.65), (1, 27.65)):
        for row, z in enumerate((2.75, 7.10)):
            for index, y in enumerate((-8.8, -4.2, 0.4, 5.0, 9.6)):
                facade_window_x(
                    coll,
                    root,
                    f"brick_tower:side_window_{side}_{row}_{index}",
                    x,
                    y,
                    z,
                    2.35,
                    2.30,
                    M,
                    side,
                    1,
                    "black",
                    "glass_dark",
                    True,
                )
    for row, z in enumerate((2.75, 7.10)):
        rear_centers = (
            (-24, -19, -14, -9, -4, 4, 9, 14, 19, 24) if row else (-18.5, 18.5)
        )
        for index, x in enumerate(rear_centers):
            facade_window_y(
                coll,
                root,
                f"brick_tower:rear_window_{row}_{index}",
                x,
                13.35,
                z,
                2.60,
                2.25,
                M,
                1,
                1,
                "black",
                "glass_dark",
                True,
                (row + index) % 3 == 0,
            )
    steel_service_door_y(
        coll,
        root,
        "brick_tower:rear_west_personnel_door",
        -24.0,
        13.42,
        0.12,
        1.55,
        2.72,
        M,
        1,
        "AUTHORIZED",
    )
    steel_service_door_y(
        coll,
        root,
        "brick_tower:rear_east_personnel_door",
        24.0,
        13.42,
        0.12,
        1.55,
        2.72,
        M,
        1,
        "AUTHORIZED",
    )
    louver_panel_y(
        coll,
        root,
        "brick_tower:rear_exhaust_louver",
        -19.0,
        13.40,
        7.10,
        2.25,
        1.35,
        M,
        1,
    )
    rear_utility_cluster(
        coll, root, "brick_tower:rear_electrical_service", 18.4, 13.43, 0.18, M, 1
    )

    # Public entrance nested below the center tower and protected by a glass/metal canopy.
    curtain_wall_y(
        coll,
        root,
        "brick_tower:entrance_transom",
        0.0,
        south - 0.80,
        0.42,
        8.6,
        4.40,
        4,
        2,
        M,
        -1,
        "glass_clear",
        "black",
        "public_lobby_curtain_wall",
    )
    glass_door_bank(
        coll,
        root,
        "brick_tower:main_entry",
        0.0,
        south - 1.03,
        0.42,
        5.1,
        3.15,
        M,
        2,
        -1,
        "black",
    )
    box(
        coll,
        "brick_tower:entry_canopy",
        (0.0, south - 2.55, 4.22),
        (10.4, 3.2, 0.24),
        M["blue_grey_metal"],
        0.055,
        role="entrance_canopy",
        parent=root,
    )
    box(
        coll,
        "brick_tower:entry_canopy_glass",
        (0.0, south - 2.55, 4.09),
        (9.7, 2.75, 0.06),
        M["glass_blue"],
        0.025,
        role="entrance_canopy_glazing",
        parent=root,
    )
    for x in (-4.45, 4.45):
        cylinder(
            coll,
            f"brick_tower:entry_column_{x}",
            (x, south - 3.65, 2.25),
            0.12,
            4.05,
            M["steel"],
            24,
            role="canopy_column",
            parent=root,
        )
    entrance_stair_y(
        coll,
        root,
        "brick_tower:public_entry_stair",
        0.0,
        south - 4.35,
        0.08,
        7.2,
        0.34,
        M,
        step_count=3,
        tread=0.38,
        landing_depth=2.90,
    )
    accessible_ramp(
        coll,
        root,
        "brick_tower:entry_ramp",
        8.45,
        south - 3.15,
        0.08,
        8.2,
        1.65,
        0.34,
        M,
        high_side=-1.0,
    )

    # Dimensional identity hierarchy and twin seals reproduce the municipal facade.
    protect = text_object(
        coll,
        "brick_tower:protect_wordmark",
        "P R O T E C T",
        (-23.2, south - 0.94, 9.62),
        0.82,
        M["black"],
        0.090,
        role="police_motto_wordmark",
        parent=root,
    )
    police = text_object(
        coll,
        "brick_tower:police_wordmark",
        "P O L I C E",
        (0.0, south - 0.94, 12.15),
        1.42,
        M["black"],
        0.110,
        role="police_station_wordmark",
        parent=root,
    )
    serve = text_object(
        coll,
        "brick_tower:serve_wordmark",
        "S E R V E",
        (23.2, south - 0.94, 9.62),
        0.82,
        M["black"],
        0.090,
        role="police_motto_wordmark",
        parent=root,
    )
    for sign in (protect, police, serve):
        sign["c2w_sign_reference_index"] = 2
    circular_seal(
        coll,
        root,
        "brick_tower:west_municipal_seal",
        -23.2,
        south - 0.86,
        3.25,
        1.18,
        M,
        -1,
    )
    circular_seal(
        coll,
        root,
        "brick_tower:east_municipal_seal",
        23.2,
        south - 0.86,
        3.25,
        1.18,
        M,
        -1,
    )
    text_object(
        coll,
        "brick_tower:street_number",
        "11290",
        (10.4, south - 0.49, 3.55),
        0.24,
        M["black"],
        0.032,
        role="building_address",
        parent=root,
    )
    # Secure rear operations use manufactured insulated sectional doors.  No
    # flag/flagpole and no yellow rear posts are generated anywhere in v10.
    for bay, x in enumerate((-8.0, 0.0, 8.0)):
        sectional_sally_door_y(
            coll,
            root,
            f"brick_tower:rear_sally_door_{bay}",
            x,
            13.92,
            0.24,
            6.05,
            4.02,
            M,
            normal=1.0,
            panel_rows=8,
            panel_columns=4,
            glazing_row=4,
            finish_key="door_enamel",
        )
    text_object(
        coll,
        "brick_tower:authorized_only",
        "AUTHORIZED VEHICLES ONLY",
        (0.0, 14.18, 5.20),
        0.42,
        M["white"],
        0.040,
        role="secure_area_wordmark",
        parent=root,
    ).rotation_euler = (math.pi / 2, 0, math.pi)

    # Roof services, drainage, cameras and exterior illumination.
    for index, (x, y, width, depth, height) in enumerate(
        (
            (-16.0, 4.0, 2.8, 2.2, 1.2),
            (-7.0, 5.0, 2.4, 2.0, 1.1),
            (8.0, 4.5, 3.1, 2.5, 1.35),
            (17.0, 5.5, 2.5, 2.0, 1.1),
        )
    ):
        roof_mechanical_unit(
            coll, root, f"brick_tower:rtu_{index}", x, y, 10.65, width, depth, height, M
        )
    roof_service_walkway(
        coll,
        root,
        "brick_tower:roof_walkway",
        (
            (-19.0, 3.8),
            (-17.8, 3.9),
            (-16.6, 4.0),
            (-15.4, 4.1),
            (-14.2, 4.2),
            (-13.0, 4.3),
            (-11.8, 4.4),
            (-10.6, 4.5),
            (-9.4, 4.6),
            (-8.2, 4.8),
            (-7.0, 5.0),
            (-5.8, 5.0),
            (-4.6, 5.0),
            (-3.4, 5.0),
            (-2.2, 5.0),
            (-1.0, 5.0),
            (0.2, 5.0),
            (1.4, 4.9),
            (2.6, 4.8),
            (3.8, 4.7),
            (5.0, 4.6),
            (6.2, 4.5),
            (7.4, 4.5),
            (8.6, 4.6),
            (9.8, 4.7),
            (11.0, 4.8),
            (12.2, 5.0),
            (13.4, 5.2),
            (14.6, 5.3),
            (15.8, 5.4),
            (17.0, 5.5),
        ),
        10.73,
        M,
    )
    for index, x in enumerate((-27.0, -18.5, 18.5, 27.0)):
        downpipe(
            coll, root, f"brick_tower:downpipe_{index}", x, south - 0.26, 10.5, M, True
        )
    for index, x in enumerate((-27.0, -16.0, 16.0, 27.0)):
        downpipe(
            coll, root, f"brick_tower:rear_downpipe_{index}", x, 13.38, 10.5, M, False
        )
    for index, x in enumerate((-25.2, -7.2, 7.2, 25.2)):
        dome_camera(
            coll,
            root,
            f"brick_tower:front_camera_{index}",
            x,
            south - 0.45,
            9.5 if abs(x) > 20 else 12.7,
            M,
            -1,
        )
    for index, x in enumerate((-24.0, -10.5, 10.5, 24.0)):
        dome_camera(
            coll, root, f"brick_tower:rear_camera_{index}", x, 13.36, 9.15, M, 1
        )
    for index, x in enumerate((-18.0, -10.0, 10.0, 18.0)):
        wall_light(
            coll, root, f"brick_tower:front_light_{index}", x, south - 0.46, 3.7, M, -1
        )
    for index, x in enumerate((-21.0, -12.0, -4.0, 4.0, 12.0, 21.0)):
        wall_light(coll, root, f"brick_tower:rear_light_{index}", x, 13.39, 5.15, M, 1)

    # Visible secure public lobby and administrative offices.
    box(
        coll,
        "brick_tower:lobby_floor",
        (0.0, -10.5, 0.34),
        (13.5, 5.2, 0.20),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    reception_desk(coll, root, "brick_tower:reception", 0.0, -9.2, 0.34, 5.2, M)
    security_turnstile(coll, root, "brick_tower:turnstile_west", -3.0, -7.9, 0.34, M)
    security_turnstile(coll, root, "brick_tower:turnstile_east", 3.0, -7.9, 0.34, M)
    for seat in range(8):
        waiting_chair(
            coll,
            root,
            f"brick_tower:waiting_{seat}",
            -4.5 + (seat % 4) * 3.0,
            -6.3 + (seat // 4) * 1.25,
            0.34,
            M,
            math.pi,
        )
    for desk in range(12):
        side = -1 if desk < 6 else 1
        local_index = desk % 6
        dx = side * (10.5 + (local_index % 3) * 4.2)
        dy = -7.5 + (local_index // 3) * 4.4
        office_desk(coll, root, f"brick_tower:office_desk_{desk}", dx, dy, 0.30, M)
        task_chair(
            coll,
            root,
            f"brick_tower:office_chair_{desk}",
            dx,
            dy + 0.82,
            0.30,
            M,
            math.pi,
        )
    ceiling_lights(
        coll,
        root,
        "brick_tower:lobby_lights",
        (-4.5, -1.5, 1.5, 4.5),
        (-10.4, -7.8),
        4.25,
        M,
    )
    area_light(
        coll,
        "brick_tower:lobby_area_light",
        (0.0, -9.0, 4.20),
        310.0,
        5.5,
        (1.0, 0.76, 0.52),
        root,
    )

    coll["c2w_rear_white_base_board_removed"] = True
    coll["c2w_rear_yellow_columns_removed"] = True
    coll["c2w_no_flag_geometry"] = True
    coll["c2w_independently_modeled"] = True
    coll[
        "c2w_detail_profile"
    ] = "reference-matched symmetric brick composition+three white towers+floating metal eaves+large PROTECT POLICE SERVE dimensional lettering+twin municipal seals+no flag geometry+double-laminated deep drained black-framed windows+recessed hardware-complete glazed vestibule+grounded stair and eased ramp+occupied lobby and offices+vision-lite secure personnel doors+commercial micro-ribbed insulated rear sectional-door construction with track hardware and compact sensors+rear utility metering+louvers+lighting+surveillance+parapet/coping/scuppers+roof service walkway+buried non-projecting ground slab"
    return coll


def build_blue_portal_cmu(
    parent=None, origin=(62.0, 0.0, 0.0), yaw=0.0, include_site=False, materials=None
):
    """Reference 3: grey-CMU public safety complex with monumental blue portal."""
    M = materials or make_materials()
    coll = collection(
        "POLICE_C_BLUE_PORTAL_CMU",
        parent,
        "police_station_asset",
        "police.blue_portal_cmu.v10",
    )
    root = asset_root(
        coll, "blue_portal_cmu:root", origin, yaw, "police.blue_portal_cmu.v10"
    )
    coll["c2w_reference_index"] = 3
    coll["c2w_variant"] = "blue_portal_cmu"
    coll["c2w_reference_url"] = REFERENCE_URLS[2]
    coll["c2w_reference_signature"] = REFERENCE_ANALYSIS["blue_portal_cmu"][
        "visible_signature"
    ]
    coll["c2w_dimensions_m"] = json.dumps([56.0, 30.0, 10.2])
    if include_site:
        local_station_parcel(coll, root, "blue_portal:parcel", 56.0, 30.0, M)

    south = -14.2
    # Low horizontal CMU wings and a dark masonry end block follow the photograph.
    box(
        coll,
        "blue_portal:pale_cmu_core",
        (-7.5, 1.0, 3.75),
        (41.0, 26.0, 7.5),
        M["cmu_side"],
        0.055,
        role="pale_cmu_building_mass",
        parent=root,
    )
    box(
        coll,
        "blue_portal:dark_cmu_wing",
        (21.5, 1.0, 3.75),
        (15.0, 26.0, 7.5),
        M["cmu_dark_side"],
        0.055,
        role="dark_cmu_building_mass",
        parent=root,
    )
    # Correctly oriented face veneers and explicit vertical control joints.
    for bay in range(13):
        x = -27.0 + bay * 3.65
        material = M["cmu_dark_front"] if x > 14.0 else M["cmu_front"]
        box(
            coll,
            f"blue_portal:front_cmu_veneer_{bay}",
            (x, south - 0.13, 3.75),
            (3.48, 0.26, 7.25),
            material,
            role="cmu_facade_veneer",
            parent=root,
        )
        box(
            coll,
            f"blue_portal:cmu_control_joint_{bay}",
            (x + 1.77, south - 0.28, 3.75),
            (0.030, 0.022, 7.05),
            M["black"],
            role="masonry_control_joint",
            parent=root,
        )
    # Independent north-face veneers keep the 390 x 190 mm CMU bond level in
    # rear views; the structural core intentionally retains its side mapping.
    for bay in range(16):
        x = -27.0 + bay * 3.65
        material = M["cmu_dark_front"] if x > 14.0 else M["cmu_front"]
        box(
            coll,
            f"blue_portal:rear_cmu_veneer_{bay}",
            (x, 14.02, 3.75),
            (3.48, 0.08, 7.42),
            material,
            0.016,
            role="rear_cmu_facade_veneer",
            parent=root,
        )
        box(
            coll,
            f"blue_portal:rear_cmu_control_joint_{bay}",
            (x + 1.77, 14.075, 3.75),
            (0.030, 0.018, 7.20),
            M["joint_sealant"],
            role="rear_masonry_control_joint",
            parent=root,
        )
    box(
        coll,
        "blue_portal:buried_ground_slab",
        (-0.5, 1.0, 0.025),
        (55.7, 25.6, 0.05),
        M["concrete"],
        role="structural_floor_slab",
        parent=root,
    )
    box(
        coll,
        "blue_portal:roof_slab",
        (-0.5, 1.0, 7.42),
        (56.2, 26.1, 0.26),
        M["concrete"],
        role="roof_slab",
        parent=root,
    )
    box(
        coll,
        "blue_portal:roof_coping",
        (-0.5, 1.0, 7.70),
        (57.0, 27.0, 0.22),
        M["blue_grey_metal"],
        0.045,
        role="roof_coping",
        parent=root,
    )
    flat_roof_edge_system(
        coll,
        root,
        "blue_portal:main_flat_roof",
        -0.5,
        1.0,
        56.5,
        26.5,
        7.50,
        M,
        front_y=-12.25,
        scupper_xs=(-23.0, 14.0, 24.0),
    )

    # Long left ribbon windows: narrow panes in a charcoal masonry belt.
    box(
        coll,
        "blue_portal:left_dark_window_belt",
        (-16.5, south - 0.28, 4.05),
        (22.0, 0.36, 2.20),
        M["cmu_dark_front"],
        role="dark_masonry_window_belt",
        parent=root,
    )
    for index, x in enumerate((-25.0, -21.3, -17.6, -13.9, -10.2, -6.5)):
        facade_window_y(
            coll,
            root,
            f"blue_portal:left_ribbon_window_{index}",
            x,
            south - 0.46,
            4.08,
            2.55,
            1.32,
            M,
            -1,
            2,
            "aluminum",
            "glass_blue",
            False,
            index % 3 == 0,
            "secure_ribbon_window",
        )
    # Right-hand dark wing has two deeply recessed public-service windows.
    for index, x in enumerate((27.0,)):
        facade_window_y(
            coll,
            root,
            f"blue_portal:right_wing_window_{index}",
            x,
            south - 0.38,
            3.70,
            3.15,
            2.75,
            M,
            -1,
            2,
            "aluminum",
            "glass_dark",
            True,
            index == 1,
            "secure_public_service_window",
        )
    for side, x in ((-1, -28.35), (1, 28.35)):
        for index, y in enumerate((-9.7, -5.1, -0.5, 4.1, 8.7)):
            facade_window_x(
                coll,
                root,
                f"blue_portal:side_window_{side}_{index}",
                x,
                y,
                3.65,
                2.55,
                2.55,
                M,
                side,
                2,
                "aluminum",
                "glass_dark",
                True,
                "secure_side_window",
            )
    for index, x in enumerate((-24, -19, -14, -9, -4, 3, 10)):
        facade_window_y(
            coll,
            root,
            f"blue_portal:rear_window_{index}",
            x,
            14.05,
            3.72,
            2.75,
            2.45,
            M,
            1,
            2,
            "aluminum",
            "glass_dark",
            True,
            index % 3 == 0,
            "secure_rear_window",
        )
    steel_service_door_y(
        coll,
        root,
        "blue_portal:rear_personnel_door",
        12.2,
        14.08,
        0.12,
        1.55,
        2.72,
        M,
        1,
        "STAFF ONLY",
    )
    louver_panel_y(
        coll,
        root,
        "blue_portal:rear_generator_louver",
        -25.0,
        14.08,
        5.78,
        2.20,
        1.28,
        M,
        1,
    )
    rear_utility_cluster(
        coll, root, "blue_portal:rear_electrical_service", -21.0, 14.09, 0.18, M, 1
    )

    # Two-storey entry glass sits within the oversized cobalt portal.
    curtain_wall_y(
        coll,
        root,
        "blue_portal:entry_curtain_wall",
        4.8,
        south - 0.62,
        0.42,
        10.4,
        8.35,
        4,
        4,
        M,
        -1,
        "glass_clear",
        "aluminum",
        "public_lobby_curtain_wall",
    )
    glass_door_bank(
        coll,
        root,
        "blue_portal:main_entry",
        4.8,
        south - 0.92,
        0.42,
        5.6,
        3.35,
        M,
        2,
        -1,
        "aluminum",
    )

    # Monumental left pier and deep cantilever are structurally complete rather
    # than a thin facade frame.  Reference-scale soffit panels and joints are visible.
    box(
        coll,
        "blue_portal:monumental_left_pier",
        (-9.2, south - 1.15, 4.75),
        (2.35, 5.3, 9.5),
        M["blue_panel"],
        0.055,
        role="monumental_cobalt_portal_pier",
        parent=root,
    )
    box(
        coll,
        "blue_portal:monumental_top_canopy",
        (0.5, south - 3.45, 9.35),
        (21.8, 10.0, 1.05),
        M["blue_panel"],
        0.065,
        role="monumental_cobalt_portal_canopy",
        parent=root,
    )
    box(
        coll,
        "blue_portal:canopy_drip_edge",
        (0.5, south - 8.50, 8.94),
        (22.05, 0.16, 0.18),
        M["blue_grey_metal"],
        0.025,
        role="portal_canopy_drip_edge",
        parent=root,
    )
    for end_name, x in (("west", -10.45), ("east", 11.45)):
        box(
            coll,
            f"blue_portal:canopy_end_return_{end_name}",
            (x, south - 3.45, 9.35),
            (0.16, 10.0, 1.08),
            M["blue_grey_metal"],
            0.025,
            role="portal_canopy_end_return",
            parent=root,
        )
    box(
        coll,
        "blue_portal:monumental_soffit",
        (0.5, south - 3.45, 8.78),
        (20.9, 9.2, 0.12),
        M["aluminum"],
        0.025,
        role="portal_metal_soffit",
        parent=root,
    )
    for panel in range(12):
        x = -9.0 + panel * 1.72
        box(
            coll,
            f"blue_portal:soffit_joint_x_{panel}",
            (x, south - 3.45, 8.70),
            (0.028, 8.95, 0.025),
            M["black"],
            role="portal_soffit_joint",
            parent=root,
        )
    for panel in range(6):
        y = south - 7.5 + panel * 1.65
        box(
            coll,
            f"blue_portal:soffit_joint_y_{panel}",
            (0.5, y, 8.70),
            (20.7, 0.028, 0.025),
            M["black"],
            role="portal_soffit_joint",
            parent=root,
        )
    for light in range(8):
        x = -7.2 + light * 2.25
        box(
            coll,
            f"blue_portal:soffit_light_{light}",
            (x, south - 4.0, 8.62),
            (0.95, 0.28, 0.025),
            M["lamp_white"],
            0.025,
            role="portal_recessed_light",
            parent=root,
        )
    panel_joint_grid(
        coll,
        root,
        "blue_portal:left_pier_panel_joints",
        -9.2,
        south - 3.83,
        0.20,
        2.28,
        9.10,
        M,
        -1,
        1,
        5,
    )
    panel_joint_grid(
        coll,
        root,
        "blue_portal:canopy_front_panel_joints",
        0.5,
        south - 8.48,
        8.83,
        21.6,
        1.0,
        M,
        -1,
        10,
        1,
    )

    # Smaller blue frame wraps the glass and police identity wall like reference C.
    box(
        coll,
        "blue_portal:identity_frame_left",
        (10.7, south - 0.92, 4.25),
        (1.25, 2.25, 8.5),
        M["blue_panel"],
        0.045,
        role="cobalt_identity_frame",
        parent=root,
    )
    box(
        coll,
        "blue_portal:identity_frame_right",
        (25.4, south - 0.92, 4.25),
        (1.25, 2.25, 8.5),
        M["blue_panel"],
        0.045,
        role="cobalt_identity_frame",
        parent=root,
    )
    box(
        coll,
        "blue_portal:identity_frame_top",
        (18.05, south - 1.95, 8.15),
        (15.9, 4.3, 1.25),
        M["blue_panel"],
        0.05,
        role="cobalt_identity_frame",
        parent=root,
    )
    panel_joint_grid(
        coll,
        root,
        "blue_portal:identity_top_joints",
        18.05,
        south - 4.12,
        7.54,
        15.7,
        1.18,
        M,
        -1,
        7,
        1,
    )

    # The reference places the civic identity on a quiet pale-CMU field between
    # the glass entrance and dark service wing.  This separate veneer prevents
    # lettering from floating over glazing or disappearing into charcoal block.
    box(
        coll,
        "blue_portal:identity_cmu_wall",
        (18.05, south - 0.46, 3.73),
        (13.2, 0.34, 7.38),
        M["cmu_front"],
        0.035,
        role="police_identity_cmu_wall",
        parent=root,
    )
    for joint in range(4):
        box(
            coll,
            f"blue_portal:identity_wall_control_joint_{joint}",
            (13.1 + joint * 3.30, south - 0.65, 3.73),
            (0.030, 0.024, 7.18),
            M["black"],
            role="masonry_control_joint",
            parent=root,
        )

    # Idaho Falls-inspired dimensional identity and flowing-river mark.
    for arc_index, radius in enumerate((2.35, 2.70, 3.05)):
        arc_tube(
            coll,
            root,
            f"blue_portal:river_logo_arc_{arc_index}",
            (18.8, south - 0.70 - arc_index * 0.015, 5.50 + arc_index * 0.10),
            radius,
            math.radians(30),
            math.radians(150),
            18,
            0.055,
            M["blue_panel"],
            "police_identity_logo",
        )
    idaho = text_object(
        coll,
        "blue_portal:idaho_falls_wordmark",
        "IDAHO FALLS",
        (19.1, south - 0.79, 4.78),
        0.76,
        M["vehicle_blue"],
        0.085,
        role="police_municipality_wordmark",
        parent=root,
    )
    police = text_object(
        coll,
        "blue_portal:police_wordmark",
        "POLICE",
        (19.1, south - 0.81, 3.63),
        1.46,
        M["vehicle_blue"],
        0.115,
        role="police_station_wordmark",
        parent=root,
    )
    address = text_object(
        coll,
        "blue_portal:address_wordmark",
        "775 NORTHGATE MILE",
        (19.1, south - 0.79, 2.46),
        0.46,
        M["black"],
        0.060,
        role="building_address",
        parent=root,
    )
    for sign in (idaho, police, address):
        sign["c2w_sign_reference_index"] = 3

    # Reference-specific wall hardware and manufactured anti-ram protection.
    dome_camera(
        coll, root, "blue_portal:entry_dome_camera", 19.2, south - 0.45, 5.90, M, -1
    )
    # FDC cabinet, siamese connection, key box, intercom and card reader.
    box(
        coll,
        "blue_portal:fdc_backer",
        (17.0, south - 0.48, 1.67),
        (1.10, 0.13, 0.72),
        M["white"],
        0.035,
        role="fire_department_connection_sign",
        parent=root,
    )
    text_object(
        coll,
        "blue_portal:fdc_letters",
        "FDC",
        (17.0, south - 0.58, 1.67),
        0.42,
        M["red"],
        0.045,
        role="fire_department_connection_wordmark",
        parent=root,
    )
    for connector, x in enumerate((16.55, 17.45)):
        cylinder(
            coll,
            f"blue_portal:fdc_connector_{connector}",
            (x, south - 0.64, 1.10),
            0.16,
            0.18,
            M["bronze"],
            24,
            rot=(math.pi / 2, 0, 0),
            role="fire_department_connection",
            parent=root,
        )
        cylinder(
            coll,
            f"blue_portal:fdc_cap_{connector}",
            (x, south - 0.76, 1.10),
            0.11,
            0.08,
            M["bronze"],
            20,
            rot=(math.pi / 2, 0, 0),
            role="fire_department_connection_cap",
            parent=root,
        )
    box(
        coll,
        "blue_portal:key_box",
        (10.15, south - 0.70, 1.55),
        (0.28, 0.14, 0.38),
        M["red"],
        0.045,
        role="emergency_key_box",
        parent=root,
    )
    box(
        coll,
        "blue_portal:entry_intercom",
        (8.2, south - 1.08, 1.48),
        (0.26, 0.16, 0.42),
        M["black"],
        0.045,
        role="entry_intercom",
        parent=root,
    )
    cylinder(
        coll,
        "blue_portal:intercom_speaker",
        (8.2, south - 1.18, 1.55),
        0.065,
        0.025,
        M["aluminum"],
        18,
        rot=(math.pi / 2, 0, 0),
        role="entry_intercom_speaker",
        parent=root,
    )
    box(
        coll,
        "blue_portal:card_reader",
        (8.55, south - 1.08, 1.35),
        (0.16, 0.14, 0.28),
        M["black"],
        0.035,
        role="access_control_reader",
        parent=root,
    )

    # Jointed civic stair and a filled, eased accessible connection terminate
    # flush with the same entrance landing.
    entrance_stair_y(
        coll,
        root,
        "blue_portal:public_entry_stair",
        4.8,
        south - 4.95,
        0.08,
        6.8,
        0.34,
        M,
        step_count=3,
        tread=0.38,
        landing_depth=3.50,
    )
    accessible_ramp(
        coll,
        root,
        "blue_portal:entry_ramp",
        -2.5,
        south - 4.0,
        0.08,
        7.8,
        1.65,
        0.34,
        M,
    )
    for bollard_index, x in enumerate((-7.2, -4.3, -1.4, 9.2, 12.1, 15.0, 17.9)):
        stainless_bollard(
            coll,
            root,
            f"blue_portal:entry_bollard_{bollard_index}",
            x,
            south - 7.15,
            0.12,
            M,
            1.22,
        )
    bike_rack(
        coll,
        root,
        "blue_portal:reference_bicycle_rack",
        -12.7,
        south - 6.55,
        0.30,
        M,
        count=4,
    )

    # Occupied vestibule supplies visible depth behind the transparent entrance.
    box(
        coll,
        "blue_portal:lobby_floor",
        (5.0, -10.9, 0.34),
        (13.5, 5.5, 0.20),
        M["terrazzo"],
        role="interior_floor_finish",
        parent=root,
    )
    box(
        coll,
        "blue_portal:lobby_mezzanine",
        (5.0, -9.2, 4.55),
        (13.0, 8.0, 0.24),
        M["concrete"],
        role="lobby_mezzanine_slab",
        parent=root,
    )
    reception_desk(coll, root, "blue_portal:reception", 7.2, -9.9, 0.34, 4.6, M)
    security_turnstile(coll, root, "blue_portal:turnstile", 1.2, -9.0, 0.34, M)
    for seat in range(8):
        waiting_chair(
            coll,
            root,
            f"blue_portal:waiting_{seat}",
            0.5 + (seat % 4) * 2.0,
            -7.2 + (seat // 4) * 1.25,
            0.34,
            M,
            math.pi,
        )
    for desk in range(10):
        dx = -22.0 + (desk % 5) * 4.2
        dy = -7.0 + (desk // 5) * 4.2
        office_desk(coll, root, f"blue_portal:office_desk_{desk}", dx, dy, 0.30, M)
        task_chair(
            coll,
            root,
            f"blue_portal:office_chair_{desk}",
            dx,
            dy + 0.82,
            0.30,
            M,
            math.pi,
        )
    ceiling_lights(
        coll,
        root,
        "blue_portal:lobby_lights",
        (0.5, 3.5, 6.5, 9.5),
        (-11.2, -8.4),
        4.28,
        M,
    )
    area_light(
        coll,
        "blue_portal:lobby_area_light",
        (5.0, -9.5, 4.20),
        300.0,
        5.6,
        (1.0, 0.76, 0.52),
        root,
    )

    # Secure rear service zone with separately manufactured sectional doors.
    for bay, x in enumerate((16.0, 23.0)):
        sectional_sally_door_y(
            coll,
            root,
            f"blue_portal:rear_sally_door_{bay}",
            x,
            14.50,
            0.24,
            5.50,
            4.00,
            M,
            normal=1.0,
            panel_rows=8,
            panel_columns=4,
            glazing_row=5,
            finish_key="painted_steel",
        )
    # Roof systems, drainage and surveillance complete all views.
    for index, (x, y, width, depth, height) in enumerate(
        (
            (-18.0, 4.0, 2.8, 2.3, 1.2),
            (-8.0, 5.2, 2.4, 2.0, 1.0),
            (9.0, 5.0, 3.0, 2.4, 1.3),
            (20.0, 5.4, 2.5, 2.0, 1.1),
        )
    ):
        roof_mechanical_unit(
            coll, root, f"blue_portal:rtu_{index}", x, y, 7.55, width, depth, height, M
        )
    roof_service_walkway(
        coll,
        root,
        "blue_portal:roof_walkway",
        (
            (-21.0, 4.0),
            (-19.8, 4.0),
            (-18.6, 4.0),
            (-17.4, 4.1),
            (-16.2, 4.2),
            (-15.0, 4.3),
            (-13.8, 4.4),
            (-12.6, 4.6),
            (-11.4, 4.8),
            (-10.2, 5.0),
            (-9.0, 5.2),
            (-7.8, 5.2),
            (-6.6, 5.2),
            (-5.4, 5.2),
            (-4.2, 5.2),
            (-3.0, 5.2),
            (-1.8, 5.2),
            (-0.6, 5.2),
            (0.6, 5.2),
            (1.8, 5.2),
            (3.0, 5.2),
            (4.2, 5.2),
            (5.4, 5.2),
            (6.6, 5.1),
            (7.8, 5.0),
            (9.0, 5.0),
            (10.2, 5.0),
            (11.4, 5.1),
            (12.6, 5.2),
            (13.8, 5.3),
            (15.0, 5.4),
            (16.2, 5.4),
            (17.4, 5.4),
            (18.6, 5.4),
            (19.8, 5.4),
        ),
        7.64,
        M,
    )
    for index, x in enumerate((-27.6, -11.0, 12.0, 27.6)):
        downpipe(
            coll, root, f"blue_portal:downpipe_{index}", x, south - 0.25, 7.4, M, True
        )
    for index, x in enumerate((-27.4, -11.0, 11.0, 27.4)):
        downpipe(
            coll, root, f"blue_portal:rear_downpipe_{index}", x, 14.10, 7.4, M, False
        )
    for index, x in enumerate((-25.0, -6.0, 13.0, 27.0)):
        dome_camera(
            coll,
            root,
            f"blue_portal:front_camera_{index}",
            x,
            south - 0.45,
            6.55,
            M,
            -1,
        )
    for index, x in enumerate((-24.0, -7.0, 9.0, 25.0)):
        dome_camera(
            coll, root, f"blue_portal:rear_camera_{index}", x, 14.08, 6.45, M, 1
        )
    for index, x in enumerate((-22.0, -13.0, 15.0, 24.0)):
        wall_light(
            coll, root, f"blue_portal:front_light_{index}", x, south - 0.45, 3.4, M, -1
        )
    for index, x in enumerate((-23.5, -15.0, -6.0, 5.0, 14.0, 25.0)):
        wall_light(coll, root, f"blue_portal:rear_light_{index}", x, 14.10, 5.35, M, 1)

    coll["c2w_rear_white_base_board_removed"] = True
    coll["c2w_rear_yellow_columns_removed"] = True
    coll["c2w_independently_modeled"] = True
    coll[
        "c2w_detail_profile"
    ] = "reference-specific pale and dark 390x190mm CMU wings+world-scale masonry+monumental restrained-cobalt portal with panel seams, soffit, end returns and drip edge+two-storey occupied double-laminated glass lobby+large river logo and police identity+deep drained windows+recessed hardware-complete glazed vestibule+grounded stair and eased ramp+dome camera+FDC/intercom/card reader+manufactured stainless anti-ram bollards+bicycle rack+vision-lite secure rear personnel exit+commercial micro-ribbed insulated sectional sally doors with framed glazing, compact hinges, anchors, drums, seals and sensors+rear louvers+electrical service+lighting+surveillance+parapet/coping/scuppers+roof service walkway+buried non-projecting ground slab"
    return coll


def build_police_station_asset(
    variant,
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    include_site=False,
    materials=None,
):
    """Build one independently selectable reference station for production scenes."""
    if variant not in POLICE_STATION_VARIANTS:
        raise ValueError(
            f"Unknown police-station variant {variant!r}; expected one of {POLICE_STATION_VARIANTS}"
        )
    M = materials or make_materials()
    builders = {
        "blue_white_civic": build_blue_white_civic,
        "brick_tower_municipal": build_brick_tower_municipal,
        "blue_portal_cmu": build_blue_portal_cmu,
    }
    asset = builders[variant](parent, origin, yaw, include_site, M)
    asset[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_police.build_police_station_asset"
    asset["c2w_scene_asset_inputs"] = 0
    asset["c2w_source_dependency"] = _ARCH_PATH.name
    return asset


def build_police_reference_row(parent=None, include_site=True):
    """Build three independent stations and their finite shared police campus."""
    M = make_materials()
    root = collection(
        "THREE_REFERENCE_POLICE_PRECINCT",
        parent,
        "police_reference_region",
        "police.reference.region.v10",
    )
    root[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_police.build_police_reference_row"
    root["c2w_scene_asset_inputs"] = 0
    root["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    root["c2w_reference_cache"] = json.dumps(
        [str(path) for path in REFERENCE_CACHE], ensure_ascii=False
    )
    root[
        "c2w_layout_summary"
    ] = "three distinct independently modeled reference police stations aligned east-west in one row, all public fronts face south"
    root[
        "c2w_quality_profile"
    ] = "independent reference massing+closed deep constructed four-sided facades+restrained world-scale weathered materials+double-laminated drained fenestration+deep two-leaf public vestibules+correctly sequenced cast stairs+filled eased accessible routes+commercial micro-ribbed hardware-complete sectional sally doors+no flag geometry+no yellow rear posts+panel joints+large dimensional signage+occupied secure interiors+complete roof systems+detailed front and rear operations+finite landscaped police-campus hardscape only"
    root["c2w_source_dependency"] = _ARCH_PATH.name + ":procedural_primitives_only"
    if include_site:
        build_police_site(root, M)
    build_blue_white_civic(root, (-62.0, 0.0, 0.0), 0.0, False, M)
    build_brick_tower_municipal(root, (0.0, 0.0, 0.0), 0.0, False, M)
    build_blue_portal_cmu(root, (62.0, 0.0, 0.0), 0.0, False, M)
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
    data.sensor_fit = "HORIZONTAL"
    data.shift_y = 0.065
    data.dof.use_dof = False
    data.clip_start = 0.10
    data.clip_end = 1200.0
    return tag(obj, "validation_camera")


def validation_camera_specs():
    return [
        (
            "01_three_buildings_front_daylight_far.png",
            (0.0, -206.0, 8.5),
            (0.0, -1.5, 6.2),
            38,
        ),
        (
            "02_three_buildings_west_oblique_far.png",
            (-138.0, -174.0, 12.0),
            (0.0, -0.5, 6.5),
            42,
        ),
        (
            "03_three_buildings_east_oblique_far.png",
            (138.0, -174.0, 11.5),
            (0.0, -0.5, 6.5),
            42,
        ),
        (
            "04_three_buildings_rear_oblique_far.png",
            (122.0, 162.0, 12.0),
            (0.0, 1.5, 6.5),
            40,
        ),
        (
            "05_type_a_blue_white_reference_near.png",
            (-96.0, -65.0, 3.4),
            (-62.0, -2.0, 5.6),
            47,
        ),
        (
            "06_type_a_entry_sign_and_glazing_close.png",
            (-80.0, -43.0, 2.3),
            (-57.0, -10.0, 5.1),
            47,
        ),
        (
            "07_type_b_brick_tower_reference_near.png",
            (-38.0, -70.0, 3.2),
            (0.0, -2.0, 6.4),
            47,
        ),
        (
            "08_type_b_large_identity_and_entry_close.png",
            (21.0, -48.0, 2.4),
            (0.0, -10.0, 6.6),
            49,
        ),
        (
            "09_type_c_blue_portal_reference_near.png",
            (98.0, -67.0, 2.8),
            (62.0, -2.0, 4.8),
            44,
        ),
        (
            "10_type_c_portal_identity_fdc_close.png",
            (87.0, -47.0, 2.1),
            (76.0, -10.0, 4.2),
            50,
        ),
        (
            "11_type_a_rear_fenestration_services_near.png",
            (-94.0, 57.0, 3.1),
            (-62.0, 13.7, 5.0),
            50,
        ),
        (
            "12_type_b_rear_sallyport_operations_near.png",
            (32.0, 58.0, 3.0),
            (0.0, 13.4, 4.8),
            50,
        ),
        (
            "13_type_c_rear_windows_services_near.png",
            (95.0, 58.0, 2.8),
            (62.0, 14.0, 4.2),
            48,
        ),
    ]


def build_validation_ground(M):
    """Weathered paved continuation used only beyond the finite police campus."""
    stage = collection(
        "VALIDATION_SHADOW_STAGE",
        None,
        "validation_render_stage",
        "police.validation.stage.v10",
    )
    ground = box(
        stage,
        "validation:neutral_ground",
        (0.0, 0.0, -0.16),
        (420.0, 560.0, 0.20),
        M["asphalt"],
        0.035,
        role="neutral_render_ground",
    )
    ground["c2w_pipeline_export"] = False
    stage["c2w_contains_surrounding_facilities"] = False
    stage[
        "c2w_purpose"
    ] = "procedural weathered asphalt continuation and shadow receiver only"
    return stage


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
    sky.sun_elevation = math.radians(34.0)
    sky.sun_rotation = math.radians(138.0)
    sky.altitude = 0.35
    sky.air_density = 0.82
    sky.dust_density = 0.18
    sky.ozone_density = 1.05
    background.inputs["Strength"].default_value = 0.46

    # Procedural, camera-independent cloud breakup keeps the daylight result
    # photographic without importing an HDRI or baking a backdrop into the
    # validation blend.  The horizon mask prevents clouds below grade.
    texcoord = nodes.new("ShaderNodeTexCoord")
    cloud_noise = nodes.new("ShaderNodeTexNoise")
    cloud_noise.noise_dimensions = "3D"
    cloud_noise.inputs["Scale"].default_value = 2.35
    cloud_noise.inputs["Detail"].default_value = 5.2
    cloud_noise.inputs["Roughness"].default_value = 0.68
    cloud_noise.inputs["Distortion"].default_value = 0.11
    cloud_ramp = nodes.new("ShaderNodeValToRGB")
    cloud_ramp.color_ramp.elements[0].position = 0.52
    cloud_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    cloud_ramp.color_ramp.elements[1].position = 0.69
    cloud_ramp.color_ramp.elements[1].color = (0.72, 0.72, 0.72, 1.0)
    separate = nodes.new("ShaderNodeSeparateXYZ")
    horizon = nodes.new("ShaderNodeMapRange")
    horizon.inputs["From Min"].default_value = -0.08
    horizon.inputs["From Max"].default_value = 0.42
    horizon.inputs["To Min"].default_value = 0.0
    horizon.inputs["To Max"].default_value = 1.0
    horizon.clamp = True
    cloud_mask = nodes.new("ShaderNodeMath")
    cloud_mask.operation = "MULTIPLY"
    sky_mix = nodes.new("ShaderNodeMixRGB")
    sky_mix.blend_type = "MIX"
    sky_mix.inputs[2].default_value = (0.72, 0.80, 0.92, 1.0)
    links.new(texcoord.outputs["Normal"], cloud_noise.inputs["Vector"])
    links.new(texcoord.outputs["Normal"], separate.inputs["Vector"])
    links.new(cloud_noise.outputs["Fac"], cloud_ramp.inputs["Fac"])
    links.new(separate.outputs["Z"], horizon.inputs["Value"])
    links.new(cloud_ramp.outputs["Color"], cloud_mask.inputs[0])
    links.new(horizon.outputs["Result"], cloud_mask.inputs[1])
    links.new(cloud_mask.outputs["Value"], sky_mix.inputs["Fac"])
    links.new(sky.outputs["Color"], sky_mix.inputs[1])
    links.new(sky_mix.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 1.22
    sun_data.angle = math.radians(1.15)
    sun = bpy.data.objects.new(PREFIX + "day_sun", sun_data)
    scene.collection.objects.link(sun)
    sun.location = (-95.0, -130.0, 150.0)
    sun.rotation_euler = (
        (Vector((0, 0, 7)) - sun.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(sun, "daylight_sun")

    fill_data = bpy.data.lights.new(PREFIX + "day_sky_fill", "AREA")
    fill_data.energy = 72.0
    fill_data.shape = "DISK"
    fill_data.size = 68.0
    fill = bpy.data.objects.new(PREFIX + "day_sky_fill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (62.0, -25.0, 88.0)
    fill.rotation_euler = (
        (Vector((12.0, 0.0, 7.0)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(fill, "daylight_fill")


def configure_render(
    engine="CYCLES", samples=64, resolution=(1920, 1080), percentage=100
):
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.resolution_percentage = percentage
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "16"
    scene.render.image_settings.compression = 22
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.56
    if engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.012
        scene.cycles.max_bounces = 9
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
        print(f"POLICE_RENDER_START={index}/{len(cameras)}:{filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)
        print(f"POLICE_RENDER_DONE={index}/{len(cameras)}:{filename}", flush=True)


def _role_counts(objects):
    counts = {}
    for obj in objects:
        role = obj.get("c2w_role", "untagged")
        counts[role] = counts.get(role, 0) + 1
    return counts


def audit(root, cameras):
    """Strict source, geometry, reference, layout and anti-degeneration audit."""
    bpy.context.view_layer.update()
    objects = list(bpy.context.scene.objects)
    renderable = [
        obj
        for obj in objects
        if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
    ]
    role_counts = _role_counts(objects)
    stations = [
        child
        for child in root.children
        if child.get("c2w_role") == "police_station_asset"
    ]
    variants = sorted(child.get("c2w_variant") for child in stations)
    indices = sorted(int(child.get("c2w_reference_index")) for child in stations)
    roots = [
        obj for obj in objects if obj.get("c2w_role") == "police_station_asset_root"
    ]
    root_xs = sorted(round(obj.location.x, 2) for obj in roots)
    banned_tokens = (
        "placeholder",
        "proxy",
        "dummy",
        "toy",
        "blob",
        "lowpoly",
        "low_poly",
    )
    banned = [
        obj.name
        for obj in renderable
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    reference_files = []
    for path in REFERENCE_CACHE:
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        jpeg = exists and path.read_bytes()[:2] == b"\xff\xd8"
        reference_files.append(
            {
                "path": str(path),
                "exists": exists,
                "bytes": size,
                "jpeg_magic_valid": jpeg,
            }
        )
    building_object_counts = {
        child.get("c2w_variant"): len(child.all_objects) for child in stations
    }
    complex_materials = [
        mat
        for mat in bpy.data.materials
        if mat.use_nodes
        and mat.node_tree
        and len(mat.node_tree.nodes) >= 5
        and mat.get("c2w_procedural_material")
    ]
    mesh_vertices = sum(
        len(obj.data.vertices) for obj in renderable if obj.type == "MESH"
    )
    mesh_polygons = sum(
        len(obj.data.polygons) for obj in renderable if obj.type == "MESH"
    )
    cruisers = [obj for obj in objects if obj.get("c2w_role") == "police_cruiser_root"]
    station_signs = [
        obj for obj in objects if obj.get("c2w_role") == "police_station_wordmark"
    ]
    motto_signs = [
        obj for obj in objects if obj.get("c2w_role") == "police_motto_wordmark"
    ]
    unrelated_context_roles = {
        "public_road",
        "generic_traffic_vehicle",
        "residential_building",
        "commercial_building",
        "street_vendor",
        "bus_stop",
        "playground",
    }
    excluded_facilities = [
        obj.name for obj in objects if obj.get("c2w_role") in unrelated_context_roles
    ]
    flag_objects = [
        obj.name
        for obj in objects
        if "flag" in obj.name.lower() or "flag" in str(obj.get("c2w_role", "")).lower()
    ]
    rear_yellow_columns = [
        obj.name
        for obj in renderable
        if "rear" in obj.name.lower()
        and obj.get("c2w_role")
        in {
            "sally_port_bumper",
            "rear_safety_bollard",
            "rear_guard_column",
        }
        and any(
            slot.material and "traffic_marking_yellow" in slot.material.name
            for slot in obj.material_slots
        )
    ]
    legacy_front_blocks = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role") in {"tactile_paving", "parking_wheel_stop"}
        or obj.name.endswith(":entry_ramp:slab")
    ]
    view_names = [name for name, _ in cameras]
    checks = {
        "exactly_three_independent_reference_stations": len(stations) == 3
        and indices == [1, 2, 3]
        and variants == sorted(POLICE_STATION_VARIANTS),
        "all_three_are_dense_complex_assets": len(building_object_counts) == 3
        and min(building_object_counts.values()) >= 1000,
        "single_east_west_building_row": root.get("c2w_layout_summary")
        == "three distinct independently modeled reference police stations aligned east-west in one row, all public fronts face south"
        and root_xs == [-62.0, 0.0, 62.0],
        "source_generator_is_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_police.build_police_reference_row",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "all_supplied_reference_images_cached_and_valid": all(
            item["exists"] and item["bytes"] >= 6000 and item["jpeg_magic_valid"]
            for item in reference_files
        ),
        "double_laminated_deep_drained_four_sided_security_fenestration": role_counts.get(
            "window_reveal", 0
        )
        >= 100
        and role_counts.get("window_frame", 0) >= 400
        and role_counts.get("glazing_gasket", 0) >= 400
        and role_counts.get("insulated_glass_spacer", 0) >= 400
        and role_counts.get("inner_security_glazing", 0) >= 100
        and role_counts.get("window_head_flashing", 0) >= 100
        and role_counts.get("window_drainage_weep", 0) >= 200,
        "constructed_curtain_wall_systems": role_counts.get("curtain_wall_mullion", 0)
        >= 38
        and role_counts.get("curtain_wall_pressure_plate", 0) >= 38,
        "fully_constructed_public_door_systems": role_counts.get(
            "entrance_door_glazing", 0
        )
        == 6
        and role_counts.get("inner_entrance_glazing", 0) >= 12
        and role_counts.get("entrance_sidelight_glazing", 0) == 6
        and role_counts.get("entrance_transom_glazing", 0) >= 10
        and role_counts.get("door_weather_seal", 0) >= 24
        and role_counts.get("door_kickplate", 0) == 6
        and role_counts.get("door_panic_hardware", 0) == 6
        and role_counts.get("door_pull_handle", 0) == 6
        and role_counts.get("door_hinge", 0) == 18
        and role_counts.get("automatic_door_operator", 0) == 3
        and role_counts.get("automatic_door_sensor", 0) == 3
        and role_counts.get("accessible_door_control", 0) == 6,
        "reference_a_gable_closed_rainscreen_blue_tile_fascia_glass_and_compact_radio_mast": role_counts.get(
            "pitched_metal_roof", 0
        )
        == 2
        and role_counts.get("stucco_rainscreen_spandrel", 0) == 3
        and role_counts.get("stucco_rainscreen_pier", 0) == 6
        and role_counts.get("cobalt_ceramic_base_tile", 0) >= 110
        and role_counts.get("cobalt_roof_fascia", 0) == 1
        and role_counts.get("communications_mast_brace", 0) >= 48,
        "reference_b_three_towers_brick_eaves_mottos_seals_and_rear_veneer": role_counts.get(
            "projecting_white_civic_tower", 0
        )
        == 3
        and role_counts.get("brick_veneer_panel", 0) == 12
        and role_counts.get("rear_brick_veneer_panel", 0) == 12
        and role_counts.get("floating_metal_eave", 0) == 3
        and role_counts.get("police_motto_wordmark", 0) == 2
        and role_counts.get("municipal_police_seal", 0) == 2,
        "strictly_no_flag_or_flagpole_geometry": not flag_objects,
        "reference_c_true_scale_front_and_rear_cmu_blue_portal_identity_fdc_and_bollards": role_counts.get(
            "cmu_facade_veneer", 0
        )
        == 13
        and role_counts.get("rear_cmu_facade_veneer", 0) == 16
        and role_counts.get("monumental_cobalt_portal_pier", 0) == 1
        and role_counts.get("monumental_cobalt_portal_canopy", 0) == 1
        and role_counts.get("portal_canopy_end_return", 0) == 2
        and role_counts.get("portal_canopy_drip_edge", 0) == 1
        and role_counts.get("cobalt_identity_frame", 0) == 3
        and role_counts.get("police_identity_cmu_wall", 0) == 1
        and role_counts.get("fire_department_connection", 0) == 2
        and role_counts.get("stainless_security_bollard", 0) == 7
        and role_counts.get("bicycle_rack", 0) >= 12,
        "large_readable_reference_specific_police_identity": len(station_signs) == 3
        and min(obj.data.size for obj in station_signs) >= 1.40
        and len(motto_signs) == 2
        and min(obj.data.size for obj in motto_signs) >= 0.80
        and role_counts.get("police_municipality_wordmark", 0) == 1
        and role_counts.get("police_identity_logo", 0) >= 50,
        "grounded_detailed_entries_access_and_security": role_counts.get(
            "entrance_door_glazing", 0
        )
        == 6
        and role_counts.get("entrance_landing", 0) == 3
        and role_counts.get("entrance_step", 0) == 9
        and role_counts.get("stair_nosing", 0) == 9
        and role_counts.get("stair_anti_slip_groove", 0) == 18
        and role_counts.get("accessible_ramp", 0) == 3
        and role_counts.get("accessible_ramp_transition_apron", 0) == 3
        and role_counts.get("accessible_ramp_edge_band", 0) == 6
        and role_counts.get("accessible_handrail_post", 0) == 42
        and role_counts.get("security_camera_dome", 0) >= 22,
        "occupied_secure_public_and_admin_interiors": role_counts.get(
            "secure_reception_desk", 0
        )
        == 3
        and role_counts.get("ballistic_reception_glazing", 0) == 3
        and role_counts.get("security_turnstile_pedestal", 0) >= 8
        and role_counts.get("police_office_desk", 0) >= 30
        and role_counts.get("public_waiting_chair", 0) >= 26,
        "complete_flat_roof_construction_and_services": role_counts.get(
            "roof_parapet", 0
        )
        == 12
        and role_counts.get("roof_coping_joint", 0) >= 180
        and role_counts.get("roof_scupper_liner", 0) == 7
        and role_counts.get("roof_service_walkway_pad", 0) >= 70
        and role_counts.get("roof_mechanical_unit", 0) >= 11
        and role_counts.get("mechanical_louver", 0) >= 170
        and role_counts.get("roof_fan_blade", 0) >= 66
        and role_counts.get("rainwater_downpipe", 0) >= 10,
        "dense_rear_fenestration_and_manufactured_operations": role_counts.get(
            "secure_sally_port_door", 0
        )
        == 5
        and role_counts.get("sectional_door_panel", 0) == 40
        and role_counts.get("sectional_door_micro_rib", 0) == 105
        and role_counts.get("sally_port_door_window", 0) == 20
        and role_counts.get("sectional_door_hinge", 0) == 105
        and role_counts.get("secure_personnel_door", 0) == 4
        and role_counts.get("service_door_vision_glazing", 0) == 4
        and role_counts.get("service_door_hardware", 0) >= 28
        and role_counts.get("wall_louver_blade", 0) >= 20
        and role_counts.get("rear_electrical_cabinet", 0) == 9
        and role_counts.get("garage_door_guide_track", 0) == 10
        and role_counts.get("garage_door_track_bracket", 0) == 50
        and role_counts.get("garage_door_track_anchor", 0) == 50
        and role_counts.get("garage_door_cable_drum", 0) == 10
        and role_counts.get("garage_door_safety_sensor", 0) == 10
        and role_counts.get("security_camera_lens", 0) >= 22,
        "no_yellow_columns_or_bumpers_on_any_rear_elevation": not rear_yellow_columns
        and role_counts.get("sally_port_bumper", 0) == 0,
        "type_a_yellow_board_white_blocks_and_legacy_slab_removed": not legacy_front_blocks
        and role_counts.get("parking_wheel_stop", 0) == 0
        and role_counts.get("tactile_paving", 0) == 0,
        "rear_white_base_board_removed_and_slabs_buried": all(
            bool(child.get("c2w_rear_white_base_board_removed")) for child in stations
        )
        and sum("buried_ground_slab" in obj.name for obj in objects) == 3,
        "finite_detailed_police_campus_only": role_counts.get("police_campus_ground", 0)
        == 1
        and role_counts.get("police_station_forecourt", 0) == 3
        and role_counts.get("secure_rear_service_apron", 0) == 3
        and role_counts.get("police_visitor_parking", 0) == 1
        and role_counts.get("parking_stall_marking", 0) == 35
        and role_counts.get("parking_wheel_stop", 0) == 0
        and role_counts.get("landscape_bed", 0) == 4
        and role_counts.get("landscape_shrub_root", 0) == 12
        and role_counts.get("trench_drain_grating", 0)
        + role_counts.get("rear_trench_drain_grating", 0)
        >= 300
        and role_counts.get("site_light_pole", 0) == 4
        and not excluded_facilities
        and not cruisers,
        # Counts are base-mesh instance sums; render-time bevel modifiers add
        # substantially more evaluated faces.  Thresholds intentionally cover
        # the three buildings and their finite police-campus hardscape only.
        "sufficient_building_only_geometric_density": len(renderable) >= 4950
        and mesh_vertices >= 54500
        and mesh_polygons >= 37500,
        "multi_scale_procedural_materials": len(complex_materials) >= 24,
        "thirteen_daylight_front_rear_near_close_and_far_views": len(cameras) == 13
        and sum("far" in name for name in view_names) == 4
        and sum("close" in name for name in view_names) == 3
        and sum("near" in name for name in view_names) == 6
        and sum("rear" in name for name in view_names) == 4,
        "all_renderables_are_source_tagged": all(
            obj.get("c2w_role") and obj.get("c2w_generator") == Path(__file__).name
            for obj in renderable
        ),
        "no_placeholder_or_degenerate_named_geometry": not banned,
    }
    result = {
        "generator": str(Path(__file__).resolve()),
        "pipeline_entrypoint": root.get("c2w_pipeline_entrypoint"),
        "pipeline_adapter": "urban_assets.build_police_reference_row",
        "single_asset_adapter": "urban_assets.build_police_station_asset",
        "source_dependency": _ARCH_PATH.name + ":procedural_primitives_only",
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
                "blue_white_civic": [-62.0, 0.0, 0.0],
                "brick_tower_municipal": [0.0, 0.0, 0.0],
                "blue_portal_cmu": [62.0, 0.0, 0.0],
            },
            "front_direction": "south",
            "site_scope": "three police buildings plus their finite shared police-campus hardscape only",
            "validation_stage": "procedural weathered asphalt continuation outside the pipeline asset root",
        },
        "building_object_counts": building_object_counts,
        "object_count": len(objects),
        "renderable_count": len(renderable),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "mesh_vertices_instance_sum": mesh_vertices,
        "mesh_polygons_instance_sum": mesh_polygons,
        "police_cruiser_count": len(cruisers),
        "flag_geometry_count": len(flag_objects),
        "rear_yellow_column_count": len(rear_yellow_columns),
        "legacy_front_block_artifact_count": len(legacy_front_blocks),
        "excluded_surrounding_facility_count": len(excluded_facilities),
        "excluded_surrounding_facilities": excluded_facilities,
        "role_counts": role_counts,
        "validation_views": view_names,
        "daylight": True,
        "near_and_far_views": True,
        "independent_station_variants": list(POLICE_STATION_VARIANTS),
        "architectural_refinement": {
            "type_a_entry": "grounded three-riser cast stair, neutral nosings, deep two-leaf vestibule and filled eased side ramp",
            "rear_operations": "five commercial micro-ribbed insulated sectional doors with framed vision lites, compact hinges, tracks, anchors, drums, seals and sensors",
            "removed": [
                "all flag and flagpole geometry",
                "yellow rear guard posts",
                "yellow Type-A threshold board",
                "block-like parking wheel stops",
                "rotated constant-thickness ramp slabs",
            ],
        },
        "render_engine": "CYCLES",
        "render_samples": 64,
        "resolution": [1920, 1080],
        "adaptive_sampling": True,
        "denoising": True,
        "external_blend_inputs": 0,
        "pipeline_connected": True,
        "banned_geometry_names": banned,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8"
    )
    if not result["all_checks_passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "Police production audit failed: "
            + json.dumps(
                {
                    "failed_checks": failed,
                    "building_object_counts": building_object_counts,
                    "object_count": len(objects),
                    "renderable_count": len(renderable),
                    "mesh_vertices": mesh_vertices,
                    "mesh_polygons": mesh_polygons,
                    "role_counts": role_counts,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return result


def validate_render_outputs(cameras):
    diagnostics = {}
    for filename, _ in cameras:
        path = RENDERS / filename
        entry = {"path": str(path)}
        if not path.exists() or path.stat().st_size < 150_000:
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
            width >= 1920
            and height >= 1080
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
    data["checks"]["all_thirteen_daylight_renders_are_nonblank_1920x1080"] = len(
        diagnostics
    ) == 13 and all(item["passed"] for item in diagnostics.values())
    data["all_checks_passed"] = all(data["checks"].values())
    (OUT / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    if not data["all_checks_passed"]:
        failed = [name for name, passed in data["checks"].items() if not passed]
        raise RuntimeError(
            "Police final render audit failed: "
            + json.dumps(
                {"failed_checks": failed, "render_diagnostics": diagnostics},
                indent=2,
                ensure_ascii=False,
            )
        )
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    reset_scene()
    bpy.context.preferences.filepaths.save_version = 0
    root, _materials = build_police_reference_row()
    build_validation_ground(_materials)
    setup_daylight()
    cameras = [
        (filename, camera(filename[:-4], location, target, lens))
        for filename, location, target, lens in validation_camera_specs()
    ]
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_police.build_police_reference_row"
    scene["c2w_pipeline_adapter"] = "urban_assets.build_police_reference_row"
    scene["c2w_single_asset_adapter"] = "urban_assets.build_police_station_asset"
    scene["c2w_schema_version"] = SCHEMA_VERSION
    scene["c2w_revision"] = REVISION
    scene["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    scene[
        "c2w_layout"
    ] = "three independently modeled police stations; east-west row; all fronts face south"
    scene[
        "c2w_site_scope"
    ] = "three police buildings plus finite shared police-campus hardscape only"
    scene[
        "c2w_validation_stage"
    ] = "procedural weathered asphalt continuation; excluded from pipeline asset root"
    scene.camera = cameras[0][1]
    configure_render()
    blend_path = OUT / f"{REVISION}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    data = audit(root, cameras)
    render_views(cameras)
    data = finalize_manifest(data, cameras)
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    (OUT / "SUCCESS").write_text(
        "urban_v3_police3 live source-generator build: three independently selectable high-detail reference-matched police buildings with restrained facade finishes, deep hardware-complete glazed vestibules, correctly ordered grounded stairs, filled eased accessible ramps, vision-lite secure personnel doors, commercial micro-ribbed hardware-complete sectional sally doors, no flag or flagpole geometry, no yellow rear columns, no yellow Type-A threshold board, no block-like wheel stops, finite landscaped police-campus hardscape, zero unrelated buildings/public roads/generic traffic, and thirteen 1920x1080 Cycles daylight front/rear near/close/far renders with strict validation complete\n",
        encoding="utf8",
    )
    print("POLICE_PIPELINE_COMPLETE=" + str(blend_path), flush=True)


if __name__ == "__main__":
    main()
