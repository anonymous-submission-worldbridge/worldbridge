"""Reference-driven production gas-station assets for the Urban-v3 pipeline.

The three stations in this source generator correspond one-for-one with the
user supplied references: a sculpted white Nobile canopy with warm swooshes, a
wide blue/orange multi-island station, and a restrained red/yellow flat-canopy
station.  Every validation asset is rebuilt from Python; the output blend is
never read by the production entrypoint.

``build_gas_station_asset`` builds one independently placeable station and
``build_gas_station_reference_row`` builds the requested east-west comparison
row.  The latter is exposed through :mod:`urban_assets` and is also the path
used by ``main`` for validation, preventing drift between the live pipeline and
the presentation scene.
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


from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
import random
import shutil
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
# Keep the stable asset id consumed by urban_assets while writing this visual
# refinement pass to the user-requested validation directory.  Production
# scenes call the source builder below and therefore receive the same revision.
ASSET_ID = "urban_v3_gass"
OUTPUT_RUN_ID = "urban_v3_gass4"
MODEL_REVISION = "reference_refinement_v6_detailed_storefronts_english_only"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / OUTPUT_RUN_ID
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
BLEND = OUT / f"{OUTPUT_RUN_ID}.blend"
PREFIX = "gas_station:"
SCHEMA_VERSION = 6
RNG = random.Random(20260831)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

REFERENCE_URLS = [
    "https://lgpic.3d66.com/linggantuRes/linggantu/ddc2/4a1c219aaa1f92daaaad88d077b1bdbb.jpeg!medium-size?k=D41D8CD98F00B204E9800998ECF8427E&v=55249049",
    "https://respic.3d66.com/coverimg/cache/d085/39ad9b3abf7e9028c9bd1d1e3c0c95ab.jpg!medium-size-2?v=33631403&k=D41D8CD98F00B204E9800998ECF8427E",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRAkeCDUQdDucvCwD3QvRcIU6ql8TFVMPoapfvJAuOexw&s=10",
]
REFERENCE_CACHE = [
    ROOT / f".reference_cache/gass/reference_0{i}.jpg" for i in range(1, 4)
]
REFERENCE_FILES = ["reference_01.jpg", "reference_02.jpg", "reference_03.jpg"]


@dataclass(frozen=True)
class StationStyle:
    variant: str
    reference_index: int
    origin: tuple[float, float, float]
    brand: str
    shop_name: str
    canopy_kind: str
    canopy_width: float
    canopy_depth: float
    pump_x: tuple[float, ...]
    primary: tuple[float, float, float]
    secondary: tuple[float, float, float]
    accent: tuple[float, float, float]
    store_width: float
    store_offset_x: float
    store_depth: float


STYLES = {
    "nobile_wave": StationStyle(
        "nobile_wave",
        1,
        (-38.0, 0.0, 0.0),
        "NOBILE",
        "Benvenuto Market",
        "sculpted_wave",
        28.5,
        14.0,
        (-7.2, 0.0, 7.2),
        (0.56, 0.018, 0.025),
        (0.83, 0.19, 0.018),
        (0.88, 0.50, 0.025),
        24.8,
        -0.8,
        8.2,
    ),
    "blue_orange": StationStyle(
        "blue_orange",
        2,
        (0.0, 0.0, 0.0),
        "BLUEWAY ENERGY",
        "BLUEWAY MARKET",
        "layered_hip",
        30.5,
        16.0,
        (-10.2, -3.4, 3.4, 10.2),
        (0.012, 0.095, 0.42),
        (0.90, 0.29, 0.012),
        (0.018, 0.21, 0.58),
        25.2,
        -2.2,
        8.8,
    ),
    "red_yellow": StationStyle(
        "red_yellow",
        3,
        (38.0, 0.0, 0.0),
        "NOVA FUEL",
        "NOVA MART",
        "flat_banded",
        25.8,
        13.4,
        (-7.0, 0.0, 7.0),
        (0.61, 0.012, 0.016),
        (0.91, 0.50, 0.012),
        (0.12, 0.12, 0.115),
        15.8,
        6.0,
        7.4,
    ),
}


@dataclass
class BuildContext:
    collection: bpy.types.Collection
    anchor: bpy.types.Object
    style: StationStyle

    @property
    def variant(self) -> str:
        return self.style.variant

    @property
    def asset_id(self) -> str:
        return f"gas_station.{self.variant}.v3"


SHARED_MESHES: dict[tuple, bpy.types.Mesh] = {}


def set_prefix(value: str):
    global PREFIX
    PREFIX = value


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    SHARED_MESHES.clear()


def collection(name: str, parent=None, role="procedural_collection", variant=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    coll["c2w_schema_version"] = SCHEMA_VERSION
    coll["c2w_role"] = role
    coll["c2w_generator"] = Path(__file__).name
    if variant:
        coll["c2w_station_variant"] = variant
        coll["c2w_asset_id"] = f"gas_station.{variant}.v3"
    return coll


def tag(obj, semantic: str, ctx: BuildContext | None = None, detail=False):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = "procedural_component"
    obj["c2w_semantic"] = semantic
    obj["c2w_generator"] = Path(__file__).name
    obj["c2w_source_geometry"] = "procedural"
    if ctx is not None:
        obj["c2w_station_variant"] = ctx.variant
        obj["c2w_asset_id"] = ctx.asset_id
    if detail:
        obj["c2w_quality_detail"] = True
    return obj


def contains_cjk(value: str) -> bool:
    """Return True for Chinese/Japanese/Korean ideograph code points.

    The requested presentation is English-only.  Keeping this guard in the
    live source builder prevents a future label change from silently putting
    CJK text back into either an isolated validation render or a production
    scene assembled through ``urban_assets``.
    """
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in value
    )


def _parent_local(obj, ctx: BuildContext | None, location, rotation=(0.0, 0.0, 0.0)):
    if ctx is not None:
        obj.parent = ctx.anchor
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def pbr(
    name,
    color,
    roughness=0.52,
    metallic=0.0,
    emission=None,
    emission_strength=0.0,
    transmission=0.0,
    alpha=1.0,
    coat=0.0,
):
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if transmission and "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = 1.45
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.diffuse_color = (*color, alpha)
        if hasattr(mat, "surface_render_method"):
            # Alpha blending avoids the coarse stochastic grain that dithered
            # transparency produces across the large glazed shopfronts.
            mat.surface_render_method = "BLENDED"
    mat["c2w_pbr"] = True
    return mat


def noise_material(
    name,
    dark,
    light,
    roughness=0.78,
    scale=5.0,
    detail=5.0,
    bump_strength=0.16,
    metallic=0.0,
):
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    geom = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (*light, 1)
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    micro.inputs["Scale"].default_value = scale * 12.0
    micro.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.035
    links.new(geom.outputs["Position"], noise.inputs["Vector"])
    links.new(geom.outputs["Position"], micro.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "world_scale_noise_and_micro_bump"
    return mat


def coated_material(name, color, roughness=0.32, metallic=0.0, scale=7.0, coat=0.18):
    """Microscopically varied coil-coat/paint for large manufactured panels."""
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in shader.inputs:
        shader.inputs["Coat Weight"].default_value = coat
    geom = nodes.new("ShaderNodeNewGeometry")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    macro.inputs["Scale"].default_value = scale
    macro.inputs["Detail"].default_value = 4.2
    macro.inputs["Roughness"].default_value = 0.67
    ramp = nodes.new("ShaderNodeValToRGB")
    # Coil-coated aluminium and automotive paint are visually almost uniform.
    # Keep only a restrained broad variation: the former high-contrast noise
    # made every clean manufactured surface look like speckled modelling clay.
    dark = tuple(max(0.0, c * 0.955) for c in color)
    light = tuple(min(1.0, c * 1.025 + 0.003) for c in color)
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.84
    ramp.color_ramp.elements[1].color = (*light, 1)
    rough_map = nodes.new("ShaderNodeMapRange")
    rough_map.inputs["From Min"].default_value = 0
    rough_map.inputs["From Max"].default_value = 1
    rough_map.inputs["To Min"].default_value = max(0.05, roughness - 0.07)
    rough_map.inputs["To Max"].default_value = min(0.95, roughness + 0.09)
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    micro.inputs["Scale"].default_value = scale * 18
    micro.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.018
    bump.inputs["Distance"].default_value = 0.004
    links.new(geom.outputs["Position"], macro.inputs["Vector"])
    links.new(geom.outputs["Position"], micro.inputs["Vector"])
    links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
    links.new(macro.outputs["Fac"], rough_map.inputs["Value"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(rough_map.outputs["Result"], shader.inputs["Roughness"])
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_surface_system"] = "microvaried_coil_coat"
    return mat


def make_materials():
    M = {
        # Values are authored in Blender's linear space.  The previous pass
        # used near-1.0 whites everywhere, which clipped subtle construction
        # detail and made the scene resemble an untextured maquette.
        "white": coated_material(
            "architectural_white", (0.58, 0.61, 0.60), 0.31, scale=5.0, coat=0.12
        ),
        "white_warm": coated_material(
            "warm_white_cladding", (0.63, 0.60, 0.53), 0.40, scale=4.2, coat=0.08
        ),
        "white_emit": pbr(
            "daylight_sign_white",
            (0.78, 0.78, 0.72),
            0.22,
            emission=(1.0, 0.91, 0.72),
            emission_strength=1.05,
        ),
        "black": pbr("powder_black", (0.009, 0.012, 0.015), 0.38, metallic=0.30),
        "rubber": noise_material(
            "manufactured_rubber",
            (0.012, 0.012, 0.011),
            (0.035, 0.034, 0.032),
            0.84,
            22,
            3,
            0.11,
        ),
        "steel": noise_material(
            "brushed_stainless",
            (0.18, 0.21, 0.23),
            (0.39, 0.43, 0.45),
            0.24,
            7,
            4,
            0.055,
            metallic=0.86,
        ),
        "aluminum": pbr(
            "anodized_aluminum", (0.31, 0.34, 0.36), 0.25, metallic=0.82, coat=0.08
        ),
        "galvanized": noise_material(
            "galvanized_steel",
            (0.19, 0.22, 0.23),
            (0.38, 0.41, 0.40),
            0.39,
            15,
            4,
            0.07,
            metallic=0.70,
        ),
        "chrome": pbr(
            "polished_chrome", (0.50, 0.53, 0.55), 0.12, metallic=0.96, coat=0.25
        ),
        # Daylight storefront glazing is reflective and only mildly
        # transmissive.  This avoids the milky stacked-alpha look while still
        # retaining convincing depth behind non-door facade bays.
        "glass": pbr(
            "laminated_storefront_glass",
            (0.012, 0.042, 0.058),
            0.070,
            metallic=0.06,
            transmission=0.31,
            alpha=0.86,
            coat=0.56,
        ),
        "entry_glass": pbr(
            "commercial_entry_safety_glass",
            (0.010, 0.032, 0.045),
            0.055,
            metallic=0.045,
            transmission=0.38,
            alpha=0.82,
            coat=0.62,
        ),
        "glass_dark": pbr(
            "pump_display_glass",
            (0.003, 0.010, 0.014),
            0.055,
            transmission=0.025,
            coat=0.58,
        ),
        "door_frame": coated_material(
            "commercial_dark_bronze_aluminum",
            (0.045, 0.052, 0.055),
            0.22,
            metallic=0.72,
            scale=22.0,
            coat=0.35,
        ),
        "door_sweep": noise_material(
            "entry_door_brush_seal",
            (0.006, 0.007, 0.007),
            (0.025, 0.027, 0.026),
            0.78,
            48,
            2,
            0.05,
        ),
        "sealant": pbr("architectural_black_sealant", (0.004, 0.006, 0.007), 0.66),
        "display_glass": pbr(
            "anti_glare_display_glass",
            (0.002, 0.008, 0.012),
            0.045,
            metallic=0.06,
            transmission=0.025,
            coat=0.66,
        ),
        "decal_white": pbr("printed_white_vinyl", (0.72, 0.74, 0.70), 0.38),
        "warning": pbr("warning_label_yellow", (0.92, 0.55, 0.018), 0.42),
        "paint_gray": coated_material(
            "equipment_warm_gray",
            (0.28, 0.30, 0.29),
            0.30,
            metallic=0.18,
            scale=15.0,
            coat=0.24,
        ),
        "black_gloss": pbr(
            "equipment_gloss_black",
            (0.004, 0.006, 0.008),
            0.14,
            metallic=0.22,
            coat=0.58,
        ),
        "car_glass": pbr(
            "automotive_solar_glass",
            (0.006, 0.020, 0.028),
            0.075,
            metallic=0.05,
            transmission=0.18,
            coat=0.48,
        ),
        "lcd": pbr(
            "lcd_blue_green",
            (0.025, 0.19, 0.20),
            0.22,
            emission=(0.08, 0.85, 0.76),
            emission_strength=1.15,
        ),
        "concrete": noise_material(
            "broom_finished_concrete",
            (0.16, 0.17, 0.165),
            (0.31, 0.32, 0.30),
            0.84,
            2.8,
            6,
            0.15,
        ),
        "concrete_light": noise_material(
            "precast_light_concrete",
            (0.34, 0.35, 0.33),
            (0.52, 0.51, 0.47),
            0.73,
            3.6,
            5,
            0.10,
        ),
        "asphalt": noise_material(
            "dense_asphalt",
            (0.008, 0.011, 0.014),
            (0.035, 0.039, 0.041),
            0.94,
            7.0,
            7,
            0.20,
        ),
        "forecourt_asphalt": noise_material(
            "sealed_forecourt_asphalt",
            (0.035, 0.040, 0.041),
            (0.090, 0.096, 0.093),
            0.91,
            11.0,
            6,
            0.075,
        ),
        "paver": noise_material(
            "forecourt_paver",
            (0.235, 0.245, 0.24),
            (0.38, 0.39, 0.37),
            0.80,
            4.2,
            6,
            0.12,
        ),
        "joint": pbr("recessed_concrete_joint", (0.045, 0.050, 0.052), 0.86),
        "oil": noise_material(
            "forecourt_oil_and_rubber",
            (0.006, 0.006, 0.005),
            (0.025, 0.022, 0.017),
            0.42,
            9.5,
            5,
            0.10,
        ),
        "soil": noise_material(
            "planting_soil",
            (0.028, 0.016, 0.008),
            (0.095, 0.055, 0.020),
            0.96,
            8,
            5,
            0.20,
        ),
        "grass": noise_material(
            "living_turf",
            (0.005, 0.028, 0.008),
            (0.022, 0.085, 0.018),
            0.95,
            5,
            7,
            0.18,
        ),
        "leaf": noise_material(
            "shrub_leaf", (0.006, 0.045, 0.013), (0.025, 0.16, 0.035), 0.78, 13, 4, 0.09
        ),
        "leaf_light": noise_material(
            "shrub_leaf_sun",
            (0.012, 0.085, 0.022),
            (0.07, 0.24, 0.045),
            0.72,
            17,
            4,
            0.07,
        ),
        "bark": noise_material(
            "shrub_bark", (0.028, 0.013, 0.006), (0.11, 0.048, 0.015), 0.90, 20, 4, 0.17
        ),
        "red": coated_material(
            "brand_red", (0.57, 0.012, 0.018), 0.27, scale=9.0, coat=0.32
        ),
        "red_emit": pbr(
            "brand_red_lit",
            (0.68, 0.010, 0.014),
            0.22,
            emission=(0.92, 0.018, 0.010),
            emission_strength=0.50,
        ),
        "orange": coated_material(
            "brand_orange", (0.86, 0.20, 0.008), 0.29, scale=9.0, coat=0.28
        ),
        "yellow": coated_material(
            "brand_yellow", (0.89, 0.49, 0.009), 0.29, scale=9.0, coat=0.30
        ),
        "blue": coated_material(
            "brand_blue", (0.010, 0.075, 0.39), 0.27, scale=9.0, coat=0.33
        ),
        "blue_light": coated_material(
            "brand_blue_light", (0.010, 0.19, 0.58), 0.26, scale=9.0, coat=0.31
        ),
        "green": coated_material(
            "safety_green", (0.01, 0.27, 0.09), 0.36, scale=10.0, coat=0.12
        ),
        "safety_red": pbr(
            "safety_equipment_red", (0.54, 0.008, 0.010), 0.34, coat=0.20
        ),
        "safety_yellow": pbr("safety_yellow", (0.84, 0.42, 0.008), 0.36),
        "road_white": pbr("traffic_white", (0.62, 0.62, 0.54), 0.57),
        "road_yellow": pbr("traffic_yellow", (0.76, 0.39, 0.012), 0.54),
        "warm_light": pbr(
            "canopy_led_diffuser",
            (0.98, 0.95, 0.81),
            0.19,
            emission=(1.0, 0.90, 0.67),
            emission_strength=3.0,
        ),
        "tile": noise_material(
            "porcelain_tile",
            (0.35, 0.36, 0.34),
            (0.58, 0.56, 0.51),
            0.40,
            3.5,
            4,
            0.055,
        ),
        "grout": pbr("tile_grout", (0.075, 0.078, 0.073), 0.86),
        "wood": noise_material(
            "shop_joinery",
            (0.075, 0.025, 0.010),
            (0.25, 0.085, 0.020),
            0.51,
            4.5,
            5,
            0.12,
        ),
        "cardboard": noise_material(
            "package_cardboard",
            (0.24, 0.13, 0.045),
            (0.43, 0.28, 0.10),
            0.72,
            12,
            3,
            0.06,
        ),
        "screen": pbr(
            "digital_screen",
            (0.015, 0.030, 0.045),
            0.18,
            emission=(0.04, 0.28, 0.42),
            emission_strength=0.75,
        ),
        "car_silver": pbr(
            "automotive_satin_silver",
            (0.32, 0.35, 0.37),
            0.16,
            metallic=0.78,
            coat=0.50,
        ),
        "car_graphite": pbr(
            "automotive_graphite", (0.028, 0.035, 0.043), 0.15, metallic=0.63, coat=0.58
        ),
        "car_teal": pbr(
            "automotive_deep_teal",
            (0.008, 0.075, 0.085),
            0.14,
            metallic=0.47,
            coat=0.62,
        ),
        "car_white": pbr(
            "automotive_pearl_white", (0.54, 0.56, 0.54), 0.15, metallic=0.20, coat=0.66
        ),
        "lamp_clear": pbr(
            "vehicle_clear_lens",
            (0.50, 0.56, 0.47),
            0.12,
            transmission=0.15,
            emission=(0.72, 0.78, 0.62),
            emission_strength=0.35,
            coat=0.45,
        ),
        "lamp_red": pbr(
            "vehicle_red_lens",
            (0.42, 0.006, 0.008),
            0.13,
            emission=(0.60, 0.008, 0.008),
            emission_strength=0.25,
            coat=0.42,
        ),
        "brake": pbr("vehicle_brake_disc", (0.16, 0.17, 0.17), 0.29, metallic=0.88),
        "mountain_near": noise_material(
            "distant_mountain_vegetation",
            (0.018, 0.035, 0.026),
            (0.065, 0.105, 0.072),
            0.91,
            2.4,
            6,
            0.18,
        ),
        "mountain_far": noise_material(
            "atmospheric_far_mountain",
            (0.055, 0.075, 0.080),
            (0.11, 0.14, 0.145),
            0.96,
            3.0,
            5,
            0.10,
        ),
    }
    for i, color in enumerate(
        (
            (0.82, 0.05, 0.04),
            (0.02, 0.32, 0.75),
            (0.96, 0.55, 0.02),
            (0.10, 0.55, 0.26),
            (0.72, 0.13, 0.52),
            (0.90, 0.85, 0.14),
            (0.48, 0.16, 0.78),
            (0.04, 0.62, 0.65),
        )
    ):
        M[f"product_{i}"] = pbr(f"package_color_{i}", color, 0.48)
    return M


def _cube_geometry(dims):
    hx, hy, hz = (v / 2 for v in dims)
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
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return verts, faces


def box(
    ctx,
    name,
    loc,
    dims,
    material,
    bevel=0.025,
    rotation=(0.0, 0.0, 0.0),
    semantic="architectural_detail",
    detail=True,
):
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    verts, faces = _cube_geometry(dims)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    if bevel > 0:
        mod = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        mod.width = min(bevel, min(dims) * 0.22)
        mod.segments = 2 if bevel >= 0.012 else 1
        mod.limit_method = "ANGLE"
    return tag(obj, semantic, ctx, detail)


def _shared_cube(material):
    key = ("cube", material.name)
    if key in SHARED_MESHES:
        return SHARED_MESHES[key]
    mesh = bpy.data.meshes.new(PREFIX + "shared_cube:" + str(len(SHARED_MESHES)))
    verts, faces = _cube_geometry((1, 1, 1))
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh["c2w_shared_procedural_mesh"] = True
    SHARED_MESHES[key] = mesh
    return mesh


def instance_box(
    ctx,
    name,
    loc,
    dims,
    material,
    semantic="manufactured_detail",
    rotation=(0.0, 0.0, 0.0),
    detail=True,
):
    obj = bpy.data.objects.new(PREFIX + name, _shared_cube(material))
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    obj.scale = dims
    return tag(obj, semantic, ctx, detail)


def _cylinder_geometry(radius, depth, vertices=24, radius_top=None):
    rtop = radius if radius_top is None else radius_top
    verts = []
    for z, r in ((-depth / 2, radius), (depth / 2, rtop)):
        verts.extend(
            (
                r * math.cos(2 * math.pi * i / vertices),
                r * math.sin(2 * math.pi * i / vertices),
                z,
            )
            for i in range(vertices)
        )
    faces = [tuple(range(vertices - 1, -1, -1)), tuple(range(vertices, vertices * 2))]
    for i in range(vertices):
        j = (i + 1) % vertices
        faces.append((i, j, vertices + j, vertices + i))
    return verts, faces


def cylinder(
    ctx,
    name,
    loc,
    radius,
    depth,
    material,
    vertices=24,
    rotation=(0.0, 0.0, 0.0),
    semantic="manufactured_detail",
    bevel=0.008,
    radius_top=None,
    detail=True,
):
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    verts, faces = _cylinder_geometry(radius, depth, vertices, radius_top)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    for face in mesh.polygons[2:]:
        face.use_smooth = True
    if bevel:
        mod = obj.modifiers.new("rolled_edge", "BEVEL")
        mod.width = min(bevel, radius * 0.22, depth * 0.12)
        mod.segments = 2
    return tag(obj, semantic, ctx, detail)


def _shared_cylinder(material, vertices=18):
    key = ("cylinder", material.name, vertices)
    if key in SHARED_MESHES:
        return SHARED_MESHES[key]
    mesh = bpy.data.meshes.new(PREFIX + "shared_cylinder:" + str(len(SHARED_MESHES)))
    verts, faces = _cylinder_geometry(0.5, 1.0, vertices)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    for face in mesh.polygons[2:]:
        face.use_smooth = True
    mesh["c2w_shared_procedural_mesh"] = True
    SHARED_MESHES[key] = mesh
    return mesh


def _shared_leaf(material):
    key = ("lanceolate_leaf", material.name)
    if key in SHARED_MESHES:
        return SHARED_MESHES[key]
    # Five longitudinal stations form a cambered, tapered blade.  At close
    # range this reads as an actual leaf with a rolled margin, not the diamond
    # cards that made the original planting look like low-poly decoration.
    stations = ((-0.50, 0.00), (-0.30, 0.34), (-0.04, 0.50), (0.25, 0.37), (0.50, 0.00))
    verts = []
    for z, w in stations:
        camber = 0.045 * (1.0 - (z / 0.5) ** 2)
        verts.extend(
            (
                (-w, -0.045 - camber, z),
                (w, -0.045 - camber, z),
                (-w, 0.045 + camber, z),
                (w, 0.045 + camber, z),
            )
        )
    faces = []
    for i in range(len(stations) - 1):
        a = i * 4
        b = (i + 1) * 4
        faces.extend(
            (
                (a, b, b + 1, a + 1),
                (a + 2, a + 3, b + 3, b + 2),
                (a, a + 2, b + 2, b),
                (a + 1, b + 1, b + 3, a + 3),
            )
        )
    faces.extend(((0, 1, 3, 2), (16, 18, 19, 17)))
    mesh = bpy.data.meshes.new(
        PREFIX + "shared_lanceolate_leaf:" + str(len(SHARED_MESHES))
    )
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh["c2w_shared_procedural_mesh"] = True
    SHARED_MESHES[key] = mesh
    return mesh


def instance_leaf(ctx, name, loc, dims, material, rotation):
    obj = bpy.data.objects.new(PREFIX + name, _shared_leaf(material))
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    obj.scale = dims
    return tag(obj, "shrub_leaf", ctx, True)


def instance_cylinder(
    ctx,
    name,
    loc,
    radius,
    depth,
    material,
    semantic="manufactured_detail",
    rotation=(0.0, 0.0, 0.0),
    vertices=18,
    detail=True,
):
    obj = bpy.data.objects.new(PREFIX + name, _shared_cylinder(material, vertices))
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    obj.scale = (radius * 2, radius * 2, depth)
    return tag(obj, semantic, ctx, detail)


def tube(
    ctx, name, points, radius, material, semantic="hose", cyclic=False, detail=True
):
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("NURBS" if len(points) >= 4 and not cyclic else "POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    if spline.type == "NURBS":
        spline.order_u = min(3, len(points))
        spline.use_endpoint_u = True
    spline.use_cyclic_u = cyclic
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, detail)


def beam(
    ctx, name, start, end, radius, material, semantic="structural_detail", vertices=20
):
    a, b = Vector(start), Vector(end)
    delta = b - a
    obj = cylinder(
        ctx,
        name,
        (a + b) / 2,
        radius,
        delta.length,
        material,
        vertices,
        semantic=semantic,
        bevel=min(radius * 0.2, 0.01),
    )
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def torus(
    ctx,
    name,
    loc,
    major_radius,
    minor_radius,
    material,
    rotation=(0, 0, 0),
    semantic="signage_detail",
    major_segments=40,
    minor_segments=10,
):
    verts = []
    faces = []
    for i in range(major_segments):
        a = 2 * math.pi * i / major_segments
        for j in range(minor_segments):
            b = 2 * math.pi * j / minor_segments
            r = major_radius + minor_radius * math.cos(b)
            verts.append((r * math.cos(a), r * math.sin(a), minor_radius * math.sin(b)))
    for i in range(major_segments):
        ni = (i + 1) % major_segments
        for j in range(minor_segments):
            nj = (j + 1) % minor_segments
            faces.append(
                (
                    i * minor_segments + j,
                    ni * minor_segments + j,
                    ni * minor_segments + nj,
                    i * minor_segments + nj,
                )
            )
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    for face in mesh.polygons:
        face.use_smooth = True
    return tag(obj, semantic, ctx, True)


def vertical_prism(ctx, name, points_xz, y, depth, material, semantic="signage_detail"):
    n = len(points_xz)
    verts = []
    for py in (y - depth / 2, y + depth / 2):
        verts.extend((x, py, z) for x, z in points_xz)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, True)


def rounded_vertical_prism(
    ctx,
    name,
    center_x,
    center_z,
    width,
    height,
    radius,
    y,
    depth,
    material,
    semantic="manufactured_shell",
    corner_segments=6,
):
    """Extrude a genuinely radiused X/Z profile through Y.

    Large equipment shells use this instead of a bevelled pile of cubes.  The
    radius is part of the silhouette and therefore remains clean in close and
    oblique validation views.
    """
    half_w = width / 2
    half_h = height / 2
    radius = max(0.001, min(radius, half_w - 0.001, half_h - 0.001))
    points = []
    corners = (
        (center_x + half_w - radius, center_z + half_h - radius, 0.0),
        (center_x - half_w + radius, center_z + half_h - radius, math.pi / 2),
        (center_x - half_w + radius, center_z - half_h + radius, math.pi),
        (center_x + half_w - radius, center_z - half_h + radius, math.pi * 1.5),
    )
    for cx, cz, start in corners:
        for step in range(corner_segments + 1):
            angle = start + step * (math.pi / 2) / corner_segments
            points.append(
                (cx + radius * math.cos(angle), cz + radius * math.sin(angle))
            )
    obj = vertical_prism(ctx, name, points, y, depth, material, semantic)
    for poly in obj.data.polygons:
        if len(poly.vertices) == 4:
            poly.use_smooth = True
    return obj


def front_panel_frame(
    ctx,
    name,
    center,
    width,
    height,
    rail,
    depth,
    material,
    semantic="equipment_panel_frame",
):
    """Four separate folded rails around a recessed vertical face."""
    x, y, z = center
    box(
        ctx,
        name + ":top",
        (x, y, z + height / 2 - rail / 2),
        (width, depth, rail),
        material,
        rail * 0.20,
        semantic=semantic,
    )
    box(
        ctx,
        name + ":bottom",
        (x, y, z - height / 2 + rail / 2),
        (width, depth, rail),
        material,
        rail * 0.20,
        semantic=semantic,
    )
    side_h = max(0.01, height - 2 * rail)
    for side in (-1, 1):
        box(
            ctx,
            name + f":side_{side}",
            (x + side * (width / 2 - rail / 2), y, z),
            (rail, depth, side_h),
            material,
            rail * 0.20,
            semantic=semantic,
        )


def ground_polygon(
    ctx, name, points_xy, z, thickness, material, semantic="site_marking"
):
    n = len(points_xy)
    verts = []
    for pz in (z - thickness / 2, z + thickness / 2):
        verts.extend((x, y, pz) for x, y in points_xy)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, True)


def extruded_yz(
    ctx,
    name,
    points_yz,
    x,
    depth,
    material,
    semantic="manufactured_profile",
    detail=True,
):
    """Extrude an arbitrary side elevation across X.

    This is used for vehicle glazing and formed metal panels so those parts
    follow real sloping profiles instead of being represented by axis-aligned
    cubes.
    """
    n = len(points_yz)
    verts = []
    for px in (x - depth / 2, x + depth / 2):
        verts.extend((px, y, z) for y, z in points_yz)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    bevel = obj.modifiers.new("pressed_panel_edge", "BEVEL")
    bevel.width = min(0.018, depth * 0.28)
    bevel.segments = 2
    return tag(obj, semantic, ctx, detail)


def elliptical_loft(ctx, name, sections, material, semantic, radial_segments=24):
    """Create a smooth manufactured shell from elliptical cross sections.

    ``sections`` contains ``(y, half_width, center_z, half_height)`` rings.  It
    gives cars, pump crowns and similar objects continuous highlights and a
    controlled silhouette without importing any mesh asset.
    """
    verts = []
    for y, half_w, center_z, half_h in sections:
        for i in range(radial_segments):
            angle = math.tau * i / radial_segments
            # Flatten the underside slightly while retaining rolled shoulders.
            sine = math.sin(angle)
            z = center_z + half_h * (sine if sine >= 0 else sine * 0.72)
            verts.append((half_w * math.cos(angle), y, z))
    faces = []
    rings = len(sections)
    for ring in range(rings - 1):
        a = ring * radial_segments
        b = (ring + 1) * radial_segments
        for i in range(radial_segments):
            j = (i + 1) % radial_segments
            faces.append((a + i, b + i, b + j, a + j))
    faces.append(tuple(range(radial_segments - 1, -1, -1)))
    end = (rings - 1) * radial_segments
    faces.append(tuple(end + i for i in range(radial_segments)))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, True)


def irregular_stain(ctx, name, center, radius_x, radius_y, M, seed):
    rng = random.Random(seed)
    cx, cy = center
    points = []
    for i in range(28):
        a = math.tau * i / 28
        wobble = 1.0 + rng.uniform(-0.22, 0.18) + 0.07 * math.sin(a * 5 + seed)
        points.append(
            (cx + math.cos(a) * radius_x * wobble, cy + math.sin(a) * radius_y * wobble)
        )
    return ground_polygon(
        ctx, name, points, 0.248, 0.007, M["oil"], "forecourt_weathering"
    )


def text_front(
    ctx,
    name,
    body,
    loc,
    size,
    material,
    extrude=0.035,
    align="CENTER",
    font_path=FONT_BOLD,
    semantic="signage",
    xscale=1.0,
):
    if contains_cjk(body):
        raise ValueError(
            f"CJK scene text is prohibited by the English-only presentation profile: {body!r}"
        )
    curve = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = min(0.012, extrude * 0.2)
    if Path(font_path).is_file():
        curve.font = bpy.data.fonts.load(font_path, check_existing=True)
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, (math.pi / 2, 0, 0))
    obj.scale.x = xscale
    return tag(obj, semantic, ctx, True)


def text_front_fitted(
    ctx,
    name,
    body,
    loc,
    panel_width,
    panel_height,
    material,
    extrude=0.025,
    font_path=FONT_BOLD,
    semantic="signage",
    margin=0.10,
):
    """Create the largest readable wordmark that remains inside its panel."""
    obj = text_front(
        ctx,
        name,
        body,
        loc,
        1.0,
        material,
        extrude,
        font_path=font_path,
        semantic=semantic,
    )
    bpy.context.view_layer.update()
    width = max(float(obj.dimensions.x), 1e-5)
    # Blender FONT dimensions are reported in the curve's local axes even
    # after the object is rotated onto a facade: X is word width and Y is the
    # glyph height.  Using Z here measures only extrusion depth and wildly
    # overscaled short words such as CAFÉ and PULL.
    height = max(float(obj.dimensions.y), 1e-5)
    usable_w = max(0.01, panel_width - 2 * margin)
    usable_h = max(0.01, panel_height - 2 * margin)
    factor = min(usable_w / width, usable_h / height)
    obj.scale *= factor
    bpy.context.view_layer.update()
    obj["c2w_sign_panel_width"] = float(panel_width)
    obj["c2w_sign_panel_height"] = float(panel_height)
    obj["c2w_sign_margin"] = float(margin)
    obj["c2w_fitted_text_width"] = float(obj.dimensions.x)
    obj["c2w_fitted_text_height"] = float(obj.dimensions.y)
    obj["c2w_sign_fit"] = (
        obj.dimensions.x <= usable_w + 0.002 and obj.dimensions.y <= usable_h + 0.002
    )
    return obj


def area_light(
    ctx,
    name,
    loc,
    energy,
    size,
    color=(1.0, 0.92, 0.76),
    rotation=(0, 0, 0),
    semantic="lighting",
):
    data = bpy.data.lights.new(PREFIX + name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size[0]
    data.size_y = size[1]
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    return tag(obj, semantic, ctx, True)


# ---------------------------------------------------------------------------
# Sitework, drainage, landscaping and canopy structure


def new_station_context(style: StationStyle, parent, origin=None, yaw=0.0):
    coll = collection(style.variant.upper(), parent, "gas_station_asset", style.variant)
    anchor = bpy.data.objects.new(PREFIX + style.variant + ":asset_root", None)
    coll.objects.link(anchor)
    anchor.location = origin if origin is not None else style.origin
    anchor.rotation_euler[2] = yaw
    ctx = BuildContext(coll, anchor, style)
    tag(anchor, "gas_station_root", ctx)
    anchor["c2w_role"] = "procedural_asset_root"
    anchor["c2w_reference_index"] = style.reference_index
    anchor["c2w_reference_url"] = REFERENCE_URLS[style.reference_index - 1]
    anchor["c2w_archetype"] = style.canopy_kind
    anchor["c2w_model_revision"] = MODEL_REVISION
    return ctx


def build_trench_drain(ctx, name, center, length, axis, M, slots=24):
    x, y = center
    dims = (length, 0.42, 0.10) if axis == "x" else (0.42, length, 0.10)
    box(
        ctx,
        name + ":frame",
        (x, y, 0.20),
        dims,
        M["black"],
        0.018,
        semantic="forecourt_drain",
    )
    for i in range(slots):
        t = -length / 2 + (i + 0.5) * length / slots
        loc = (x + t, y, 0.261) if axis == "x" else (x, y + t, 0.261)
        sdims = (
            (length / slots * 0.38, 0.30, 0.025)
            if axis == "x"
            else (0.30, length / slots * 0.38, 0.025)
        )
        instance_box(
            ctx,
            f"{name}:grate_slot_{i:02d}",
            loc,
            sdims,
            M["galvanized"],
            "drain_grate",
        )


def build_shrub(ctx, name, center, M, seed, radius=0.78, height=1.1):
    """Modeled woody hierarchy plus oriented leaf clusters, not a blob proxy."""
    rng = random.Random(seed)
    cx, cy, cz = center
    branch_tips = []
    for i in range(15):
        a = 2 * math.pi * i / 15 + rng.uniform(-0.14, 0.14)
        start = (cx + rng.uniform(-0.08, 0.08), cy + rng.uniform(-0.08, 0.08), cz)
        tip = (
            cx + radius * math.cos(a) * rng.uniform(0.55, 1.0),
            cy + radius * math.sin(a) * rng.uniform(0.55, 1.0),
            cz + height * rng.uniform(0.62, 1.0),
        )
        beam(
            ctx,
            f"{name}:branch_{i:02d}",
            start,
            tip,
            0.022 + rng.uniform(0, 0.012),
            M["bark"],
            "shrub_branch",
            12,
        )
        branch_tips.append(tip)
        for j in range(3):
            f = 0.36 + j * 0.21
            mid = Vector(start).lerp(Vector(tip), f)
            side = (
                mid.x + math.cos(a + rng.choice((-1, 1)) * 1.05) * radius * 0.30,
                mid.y + math.sin(a + rng.choice((-1, 1)) * 1.05) * radius * 0.30,
                mid.z + rng.uniform(0.04, 0.24),
            )
            beam(
                ctx,
                f"{name}:twig_{i:02d}_{j}",
                mid,
                side,
                0.010,
                M["bark"],
                "shrub_twig",
                10,
            )
            branch_tips.append(side)
    for i in range(150):
        base = Vector(rng.choice(branch_tips))
        a = rng.random() * math.tau
        rr = radius * rng.uniform(0.04, 0.30)
        loc = (
            base.x + math.cos(a) * rr,
            base.y + math.sin(a) * rr,
            base.z + rng.uniform(-0.16, 0.20),
        )
        dims = (
            rng.uniform(0.075, 0.145),
            rng.uniform(0.032, 0.065),
            rng.uniform(0.16, 0.27),
        )
        rotation = (rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), a)
        instance_leaf(
            ctx,
            f"{name}:leaf_{i:03d}",
            loc,
            dims,
            M["leaf_light" if i % 4 == 0 else "leaf"],
            rotation,
        )


def build_landscape_island(ctx, M):
    # A narrow reference-like green median holds the price sign without
    # reducing dispenser clearances or introducing unrelated scenery.
    box(
        ctx,
        "site:landscape_curb_base",
        (-10.8, -12.3, 0.17),
        (11.8, 3.15, 0.34),
        M["concrete_light"],
        0.22,
        semantic="landscape_curb",
    )
    box(
        ctx,
        "site:landscape_soil",
        (-10.8, -12.3, 0.34),
        (11.15, 2.50, 0.16),
        M["soil"],
        0.16,
        semantic="planting_soil",
    )
    box(
        ctx,
        "site:landscape_turf",
        (-10.8, -12.3, 0.435),
        (11.0, 2.34, 0.06),
        M["grass"],
        0.14,
        semantic="living_turf",
    )
    for i, x in enumerate((-8.0, -11.0, -13.4)):
        build_shrub(
            ctx,
            f"site:shrub_{i}",
            (x, -12.3, 0.45),
            M,
            3300 + style_seed(ctx.variant) * 13 + i,
            radius=0.54 if i else 0.70,
            height=0.78 if i else 1.02,
        )


def style_seed(variant):
    return {"nobile_wave": 11, "blue_orange": 23, "red_yellow": 37}[variant]


def build_detailed_vehicle(
    ctx, name, location, yaw, M, kind="sedan", paint_key="car_silver"
):
    """A fully procedural occupied-forecourt vehicle with smooth bodywork.

    Cars are deliberately part of each reusable station asset rather than the
    presentation-only context.  Besides supplying a human scale cue, their
    curved panels and layered glazing prevent the pump islands from reading as
    isolated blocks in production scenes.
    """
    root = bpy.data.objects.new(PREFIX + name + ":root", None)
    ctx.collection.objects.link(root)
    root.parent = ctx.anchor
    root.location = (*location, 0.24)
    root.rotation_euler[2] = yaw
    vctx = BuildContext(ctx.collection, root, ctx.style)
    tag(root, "vehicle_root", ctx, True)
    root["c2w_vehicle_kind"] = kind
    root[
        "c2w_vehicle_detail_profile"
    ] = "smooth lofted body+layered glazing+four engineered wheels+lighting+panel hardware"
    paint = M[paint_key]
    crossover = kind == "crossover"
    half_w = 1.00 if crossover else 0.93
    length = 4.72 if crossover else 4.58
    body_center = 0.82 if crossover else 0.75
    body_half = 0.47 if crossover else 0.40
    sections = []
    for frac, width_scale, height_scale in (
        (-0.50, 0.47, 0.62),
        (-0.47, 0.78, 0.88),
        (-0.38, 0.96, 1.0),
        (-0.18, 1.0, 1.0),
        (0.18, 1.0, 1.0),
        (0.39, 0.94, 0.96),
        (0.47, 0.75, 0.83),
        (0.50, 0.44, 0.58),
    ):
        sections.append(
            (frac * length, half_w * width_scale, body_center, body_half * height_scale)
        )
    elliptical_loft(vctx, name + ":lower_body", sections, paint, "vehicle_body", 28)
    # Deep rocker panel and undertray generate a real shadow line under the car.
    box(
        vctx,
        name + ":undertray",
        (0, 0.04, 0.45),
        (half_w * 1.88, length * 0.82, 0.24),
        M["black"],
        0.10,
        semantic="vehicle_underbody",
    )
    for side in (-1, 1):
        box(
            vctx,
            name + f":rocker_{side}",
            (side * (half_w - 0.035), 0.10, 0.59),
            (0.075, length * 0.69, 0.22),
            M["black"],
            0.035,
            semantic="vehicle_rocker_panel",
        )
    cab_half_h = 0.49 if crossover else 0.43
    cab_center = 1.28 if crossover else 1.18
    cab_sections = (
        (-1.10, half_w * 0.61, cab_center - 0.08, cab_half_h * 0.46),
        (-0.72, half_w * 0.82, cab_center, cab_half_h * 0.93),
        (-0.34, half_w * 0.86, cab_center + 0.05, cab_half_h),
        (0.48, half_w * 0.84, cab_center + 0.055, cab_half_h * 0.98),
        (0.88, half_w * 0.72, cab_center - 0.03, cab_half_h * 0.72),
        (1.10, half_w * 0.52, cab_center - 0.10, cab_half_h * 0.42),
    )
    elliptical_loft(
        vctx, name + ":cabin_shell", cab_sections, paint, "vehicle_cabin", 28
    )
    roof_z = cab_center + cab_half_h + 0.04
    box(
        vctx,
        name + ":roof_skin",
        (0, 0.05, roof_z),
        (half_w * 1.45, 1.44, 0.10),
        paint,
        0.08,
        semantic="vehicle_roof",
    )
    # Windscreens are inset into the sloping shell; seals and wipers sit above
    # the glass rather than being painted marks.
    windshield_z = cab_center + 0.04
    front_glass = box(
        vctx,
        name + ":windshield",
        (0, -0.76, windshield_z),
        (half_w * 1.53, 0.055, 0.71 if crossover else 0.63),
        M["car_glass"],
        0.055,
        rotation=(math.radians(-28), 0, 0),
        semantic="vehicle_glazing",
    )
    rear_glass = box(
        vctx,
        name + ":rear_glass",
        (0, 0.78, windshield_z),
        (half_w * 1.42, 0.055, 0.62 if crossover else 0.56),
        M["car_glass"],
        0.05,
        rotation=(math.radians(25), 0, 0),
        semantic="vehicle_glazing",
    )
    for side in (-1, 1):
        sx = side * (half_w * 0.86 + 0.018)
        points = (
            (-0.68, 0.99),
            (-0.43, cab_center + cab_half_h * 0.84),
            (0.43, cab_center + cab_half_h * 0.88),
            (0.78, 1.01),
        )
        extruded_yz(
            vctx,
            name + f":side_glass_{side}",
            points,
            sx,
            0.038,
            M["car_glass"],
            "vehicle_glazing",
        )
        # A structural B-pillar separates the doors and breaks the continuous
        # tinted surface into believable panes.
        box(
            vctx,
            name + f":b_pillar_{side}",
            (sx + side * 0.025, 0.04, cab_center + 0.08),
            (0.055, 0.11, 0.72),
            M["black"],
            0.018,
            semantic="vehicle_window_pillar",
        )
        for door, yc in (("front", -0.40), ("rear", 0.47)):
            tube(
                vctx,
                name + f":{door}_door_reveal_{side},",
                [
                    (sx + side * 0.035, yc - 0.40, 0.66),
                    (sx + side * 0.035, yc - 0.40, 1.02),
                    (sx + side * 0.035, yc + 0.40, 1.02),
                    (sx + side * 0.035, yc + 0.40, 0.66),
                ],
                0.010,
                M["black"],
                "vehicle_panel_reveal",
            )
            box(
                vctx,
                name + f":{door}_handle_{side}",
                (sx + side * 0.065, yc - 0.12, 1.05),
                (0.045, 0.25, 0.055),
                M["chrome"],
                0.022,
                semantic="vehicle_door_handle",
            )
        # Folded mirror housing, reflective insert and stalk.
        beam(
            vctx,
            name + f":mirror_stalk_{side}",
            (side * half_w * 0.72, -0.63, 1.19),
            (side * (half_w + 0.13), -0.72, 1.18),
            0.022,
            M["black"],
            "vehicle_mirror_stalk",
            12,
        )
        box(
            vctx,
            name + f":mirror_{side}",
            (side * (half_w + 0.17), -0.75, 1.18),
            (0.20, 0.25, 0.13),
            paint,
            0.055,
            semantic="vehicle_mirror",
        )
        box(
            vctx,
            name + f":mirror_glass_{side}",
            (side * (half_w + 0.275), -0.77, 1.18),
            (0.012, 0.18, 0.09),
            M["chrome"],
            0.008,
            semantic="vehicle_mirror_glass",
        )
    # Four multi-layer wheels: toroidal tire, sidewall, brake disc, hub and
    # individual spokes.  The outer faces are detailed on both sides.
    wheel_y = (-1.34, 1.32)
    wheel_radius = 0.42 if crossover else 0.38
    for axle, wy in enumerate(wheel_y):
        for side in (-1, 1):
            wx = side * (half_w + 0.035)
            torus(
                vctx,
                name + f":tire_{axle}_{side}",
                (wx, wy, wheel_radius),
                wheel_radius * 0.73,
                wheel_radius * 0.27,
                M["rubber"],
                (0, math.pi / 2, 0),
                "vehicle_tire",
                36,
                12,
            )
            outside = wx + side * 0.105
            cylinder(
                vctx,
                name + f":rim_{axle}_{side}",
                (outside, wy, wheel_radius),
                wheel_radius * 0.55,
                0.060,
                M["aluminum"],
                32,
                rotation=(0, math.pi / 2, 0),
                semantic="vehicle_wheel_rim",
                bevel=0.008,
            )
            cylinder(
                vctx,
                name + f":brake_{axle}_{side}",
                (outside + side * 0.034, wy, wheel_radius),
                wheel_radius * 0.36,
                0.018,
                M["brake"],
                28,
                rotation=(0, math.pi / 2, 0),
                semantic="vehicle_brake_disc",
                bevel=0.002,
            )
            cylinder(
                vctx,
                name + f":hub_{axle}_{side}",
                (outside + side * 0.052, wy, wheel_radius),
                wheel_radius * 0.13,
                0.035,
                M["chrome"],
                24,
                rotation=(0, math.pi / 2, 0),
                semantic="vehicle_wheel_hub",
                bevel=0.004,
            )
            for spoke in range(7):
                a = spoke * math.tau / 7
                beam(
                    vctx,
                    name + f":spoke_{axle}_{side}_{spoke}",
                    (outside + side * 0.075, wy, wheel_radius),
                    (
                        outside + side * 0.075,
                        wy + math.cos(a) * wheel_radius * 0.45,
                        wheel_radius + math.sin(a) * wheel_radius * 0.45,
                    ),
                    0.018,
                    M["chrome"],
                    "vehicle_wheel_spoke",
                    10,
                )
    # Fascias, optics, grille, number plates and functional trim.
    nose = -length * 0.49
    tail = length * 0.49
    box(
        vctx,
        name + ":front_bumper",
        (0, nose - 0.035, 0.63),
        (half_w * 1.72, 0.18, 0.25),
        M["black"],
        0.08,
        semantic="vehicle_bumper",
    )
    box(
        vctx,
        name + ":rear_bumper",
        (0, tail + 0.035, 0.63),
        (half_w * 1.72, 0.18, 0.24),
        M["black"],
        0.08,
        semantic="vehicle_bumper",
    )
    for side in (-1, 1):
        box(
            vctx,
            name + f":headlamp_{side}",
            (side * half_w * 0.52, nose - 0.13, 0.83),
            (half_w * 0.55, 0.075, 0.22),
            M["lamp_clear"],
            0.065,
            semantic="vehicle_headlamp",
        )
        box(
            vctx,
            name + f":taillamp_{side}",
            (side * half_w * 0.57, tail + 0.13, 0.82),
            (half_w * 0.45, 0.075, 0.24),
            M["lamp_red"],
            0.060,
            semantic="vehicle_tail_lamp",
        )
    for slat in range(7):
        x = -half_w * 0.42 + slat * half_w * 0.14
        instance_box(
            vctx,
            name + f":grille_slat_{slat}",
            (x, nose - 0.145, 0.67),
            (0.045, 0.025, 0.20),
            M["chrome"],
            "vehicle_grille",
        )
    box(
        vctx,
        name + ":front_plate",
        (0, nose - 0.17, 0.55),
        (0.52, 0.035, 0.16),
        M["road_white"],
        0.018,
        semantic="vehicle_license_plate",
    )
    box(
        vctx,
        name + ":rear_plate",
        (0, tail + 0.17, 0.57),
        (0.52, 0.035, 0.16),
        M["road_white"],
        0.018,
        semantic="vehicle_license_plate",
    )
    for side in (-0.35, 0.35):
        beam(
            vctx,
            name + f":wiper_{side}",
            (side, -0.80, 1.02),
            (side * 0.42, -0.825, 1.35),
            0.012,
            M["black"],
            "vehicle_windshield_wiper",
            10,
        )
    tube(
        vctx,
        name + ":exhaust",
        [
            (half_w * 0.55, tail - 0.15, 0.42),
            (half_w * 0.67, tail + 0.08, 0.40),
            (half_w * 0.67, tail + 0.24, 0.40),
        ],
        0.035,
        M["steel"],
        "vehicle_exhaust",
    )
    if crossover:
        for side in (-1, 1):
            tube(
                vctx,
                name + f":roof_rail_{side}",
                [
                    (side * half_w * 0.55, -0.60, roof_z + 0.10),
                    (side * half_w * 0.60, 0.58, roof_z + 0.10),
                ],
                0.025,
                M["black"],
                "vehicle_roof_rail",
            )
    return root


def build_forecourt_vehicle(ctx, M):
    placements = {
        "nobile_wave": (
            "customer_silver_sedan",
            (11.35, -2.15),
            math.radians(3),
            "sedan",
            "car_silver",
        ),
        "blue_orange": (
            "customer_graphite_crossover",
            (-6.80, -2.00),
            math.radians(-2),
            "crossover",
            "car_graphite",
        ),
        "red_yellow": (
            "customer_teal_sedan",
            (3.65, -2.15),
            math.radians(2),
            "sedan",
            "car_teal",
        ),
    }
    name, location, yaw, kind, paint = placements[ctx.variant]
    return build_detailed_vehicle(ctx, "vehicle:" + name, location, yaw, M, kind, paint)


def build_forecourt(ctx, M):
    w = 35.0
    box(
        ctx,
        "site:compacted_subbase",
        (0, 0.8, -0.28),
        (w, 31.2, 0.65),
        M["concrete"],
        0.03,
        semantic="engineered_subbase",
    )
    surface = M["paver"] if ctx.variant == "red_yellow" else M["forecourt_asphalt"]
    box(
        ctx,
        "site:jointed_forecourt",
        (0, 0.8, 0.08),
        (w, 31.0, 0.28),
        surface,
        0.025,
        semantic="fuel_forecourt",
    )
    # The first two references use a continuous sealed asphalt apron; only the
    # third uses jointed concrete.  Avoiding an indiscriminate square grid is a
    # major scale cue and removes the old miniature-baseboard appearance.
    if ctx.variant == "red_yellow":
        for i, x in enumerate((-14, -10.5, -7, -3.5, 0, 3.5, 7, 10.5, 14)):
            instance_box(
                ctx,
                f"site:sawcut_x_{i}",
                (x, 0.8, 0.226),
                (0.012, 30.2, 0.006),
                M["joint"],
                "expansion_joint",
            )
        for i, y in enumerate((-9, -5, -1, 3, 7, 11, 15)):
            instance_box(
                ctx,
                f"site:sawcut_y_{i}",
                (0, y, 0.227),
                (34.2, 0.012, 0.006),
                M["joint"],
                "expansion_joint",
            )
    else:
        for i, y in enumerate((-7.4, 2.4, 12.0)):
            instance_box(
                ctx,
                f"site:asphalt_paving_seam_{i}",
                (0, y, 0.226),
                (34.2, 0.016, 0.006),
                M["joint"],
                "asphalt_paving_seam",
            )
    # Localized tire rubber and old fluid staining are thin irregular meshes,
    # never a uniform texture pasted over the full site.
    for i, x in enumerate(ctx.style.pump_x):
        irregular_stain(
            ctx,
            f"site:pump_weathering_{i}",
            (x + 0.42, -2.1),
            0.72,
            0.36,
            M,
            7100 + style_seed(ctx.variant) * 17 + i,
        )
        irregular_stain(
            ctx,
            f"site:drip_weathering_{i}",
            (x - 0.55, -3.35),
            0.28,
            0.18,
            M,
            7300 + style_seed(ctx.variant) * 19 + i,
        )
    for i, x in enumerate((-11.5, 10.8)):
        instance_box(
            ctx,
            f"site:tire_scuff_{i}",
            (x, -7.2, 0.239),
            (0.14, 5.6, 0.008),
            M["oil"],
            "forecourt_tire_scuff",
            rotation=(0, 0, math.radians(-3 if i else 4)),
        )
    build_trench_drain(ctx, "site:front_trench_drain", (7.2, -13.85), 17.0, "x", M, 32)
    build_trench_drain(ctx, "site:store_trench_drain", (0, 4.82), 24.0, "x", M, 44)
    # Underground fill points, inspection covers, and bonded spill aprons.
    for i, (x, y) in enumerate(((11.8, 2.9), (13.0, 2.9), (14.2, 2.9))):
        cylinder(
            ctx,
            f"site:fill_point_surround_{i}",
            (x, y, 0.235),
            0.33,
            0.035,
            M["black"],
            28,
            semantic="underground_fill_point",
        )
        cylinder(
            ctx,
            f"site:fill_point_cover_{i}",
            (x, y, 0.262),
            0.245,
            0.045,
            M["steel"],
            28,
            semantic="underground_fill_point",
        )
        for bolt in range(6):
            a = bolt * math.tau / 6
            instance_cylinder(
                ctx,
                f"site:fill_point_bolt_{i}_{bolt}",
                (x + 0.18 * math.cos(a), y + 0.18 * math.sin(a), 0.292),
                0.013,
                0.018,
                M["black"],
                "fastener",
                vertices=10,
            )
    cylinder(
        ctx,
        "site:separator_monitor_cover",
        (13.1, 4.0, 0.245),
        0.44,
        0.05,
        M["galvanized"],
        32,
        semantic="service_cover",
    )
    for bolt in range(10):
        a = bolt * math.tau / 10
        instance_cylinder(
            ctx,
            f"site:separator_cover_bolt_{bolt}",
            (13.1 + 0.34 * math.cos(a), 4.0 + 0.34 * math.sin(a), 0.278),
            0.014,
            0.015,
            M["black"],
            "fastener",
            vertices=10,
        )
    build_landscape_island(ctx, M)
    # Protective corner kerbs and edge marker studs.
    for side in (-1, 1):
        box(
            ctx,
            f"site:side_curb_{side}",
            (side * 17.25, 0.8, 0.25),
            (0.42, 31.0, 0.48),
            M["concrete_light"],
            0.06,
            semantic="site_curb",
        )
    for i, x in enumerate(range(-15, 16, 3)):
        cylinder(
            ctx,
            f"site:reflective_stud_{i}",
            (x, -14.05, 0.265),
            0.04,
            0.025,
            M["road_yellow"],
            12,
            semantic="reflective_road_stud",
        )
    # Painted circulation arrows are real thin meshes rather than texture decals.
    ground_polygon(
        ctx,
        "site:entry_arrow",
        [
            (10.2, -12.8),
            (10.75, -12.8),
            (10.75, -10.6),
            (11.55, -10.6),
            (10.48, -9.3),
            (9.4, -10.6),
            (10.2, -10.6),
        ],
        0.244,
        0.018,
        M["road_white"],
        "circulation_marking",
    )
    ground_polygon(
        ctx,
        "site:exit_arrow",
        [
            (13.1, -8.7),
            (13.65, -8.7),
            (13.65, -10.9),
            (14.45, -10.9),
            (13.38, -12.2),
            (12.3, -10.9),
            (13.1, -10.9),
        ],
        0.244,
        0.018,
        M["road_white"],
        "circulation_marking",
    )


def wave_canopy_shell(ctx, M):
    w = ctx.style.canopy_width
    d = ctx.style.canopy_depth
    nx = 64
    ny = 16
    top = []
    bottom = []

    def section(ix, iy):
        x = -w / 2 + w * ix / nx
        half = d / 2 * (0.80 + 0.20 * math.cos(math.pi * x / w))
        front = (
            -2.5
            - half
            - 0.34 * math.exp(-(((x + 3.0) / 5.8) ** 2))
            + 0.10 * math.sin(x * 0.31)
        )
        rear = -2.5 + half
        y = front + (rear - front) * iy / ny
        z = (
            6.61
            + 0.44 * math.exp(-(((x - 4.5) / 7.0) ** 2))
            + 0.16 * math.sin((x / w + 0.18) * math.pi * 1.55)
            + 0.015 * y
        )
        return x, y, z

    for ix in range(nx + 1):
        for iy in range(ny + 1):
            x, y, z = section(ix, iy)
            top.append((x, y, z + 0.25))
            bottom.append((x, y, z - 0.25))
    verts = top + bottom
    stride = ny + 1
    plane = (nx + 1) * (ny + 1)
    faces = []
    mats = []
    for ix in range(nx):
        for iy in range(ny):
            a = ix * stride + iy
            b = (ix + 1) * stride + iy
            faces.append((a, b, b + 1, a + 1))
            mats.append(0)
            faces.append((plane + a + 1, plane + b + 1, plane + b, plane + a))
            mats.append(1)
    perimeter = []
    perimeter += [ix * stride for ix in range(nx + 1)]
    perimeter += [nx * stride + iy for iy in range(1, ny + 1)]
    perimeter += [ix * stride + ny for ix in range(nx - 1, -1, -1)]
    perimeter += [iy for iy in range(ny - 1, 0, -1)]
    for i, a in enumerate(perimeter):
        b = perimeter[(i + 1) % len(perimeter)]
        faces.append((a, b, plane + b, plane + a))
        mats.append(2)
    mesh = bpy.data.meshes.new(PREFIX + ctx.variant + ":sculpted_canopy_mesh")
    mesh.from_pydata(verts, [], faces)
    for mat in (M["white"], M["galvanized"], M["white_warm"]):
        mesh.materials.append(mat)
    for poly, mi in zip(mesh.polygons, mats):
        poly.material_index = mi
    obj = bpy.data.objects.new(PREFIX + ctx.variant + ":sculpted_canopy_shell", mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    for poly in mesh.polygons:
        poly.use_smooth = True
    tag(obj, "canopy_shell", ctx, True)
    # Wavy ribbons follow the non-planar south edge from the same equations.
    for band, (offset, height, mat) in enumerate(
        ((0.01, 0.14, M["yellow"]), (0.15, 0.15, M["orange"]), (0.30, 0.46, M["red"]))
    ):
        points = []
        for ix in range(nx + 1):
            x, y, z = section(ix, 0)
            phase = ix / nx
            bottom_z = z - 0.25 + offset + 0.025 * math.sin(phase * math.pi * 2.0)
            points.append((x, y - 0.035, bottom_z, bottom_z + height))
        edge_ribbon(
            ctx, f"canopy:warm_wave_band_{band}", points, 0.075, mat, "canopy_fascia"
        )
    # Narrow dark shadow reveal beneath the colored ribbons adds the missing
    # separation visible in the reference photograph.
    reveal = []
    for ix in range(nx + 1):
        x, y, z = section(ix, 0)
        reveal.append((x, y - 0.015, z - 0.285, z - 0.235))
    edge_ribbon(
        ctx,
        "canopy:fascia_shadow_reveal",
        reveal,
        0.052,
        M["black"],
        "canopy_fascia_reveal",
    )
    return 6.35


def edge_ribbon(ctx, name, points, depth, material, semantic="canopy_fascia"):
    # points: x, y, lower_z, upper_z
    verts = []
    for x, y, z0, z1 in points:
        verts.extend(
            (
                (x, y - depth / 2, z0),
                (x, y - depth / 2, z1),
                (x, y + depth / 2, z0),
                (x, y + depth / 2, z1),
            )
        )
    faces = []
    for i in range(len(points) - 1):
        a = 4 * i
        b = 4 * (i + 1)
        faces.extend(
            (
                (a, b, b + 1, a + 1),
                (a + 2, a + 3, b + 3, b + 2),
                (a, a + 2, b + 2, b),
                (a + 1, b + 1, b + 3, a + 3),
            )
        )
    faces.extend(
        ((0, 1, 3, 2), (len(verts) - 4, len(verts) - 2, len(verts) - 1, len(verts) - 3))
    )
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, True)


def hip_roof(ctx, name, width, depth, z, height, material):
    lower = [
        (-width / 2, -depth / 2, z),
        (width / 2, -depth / 2, z),
        (width / 2, depth / 2, z),
        (-width / 2, depth / 2, z),
    ]
    upper = [
        (-width / 2 + 1.4, -depth / 2 + 1.2, z + height),
        (width / 2 - 1.4, -depth / 2 + 1.2, z + height),
        (width / 2 - 1.4, depth / 2 - 1.2, z + height),
        (-width / 2 + 1.4, depth / 2 - 1.2, z + height),
    ]
    verts = lower + upper
    faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, "canopy_roof_weathering", ctx, True)


def rectangular_canopy_shell(ctx, M):
    s = ctx.style
    w = s.canopy_width
    d = s.canopy_depth
    box(
        ctx,
        "canopy:structural_deck",
        (0, -2.5, 6.55),
        (w, d, 0.56),
        M["galvanized"],
        0.055,
        semantic="canopy_shell",
    )
    if s.canopy_kind == "layered_hip":
        hip_roof(
            ctx,
            "canopy:shallow_hip_weather_skin",
            w - 0.15,
            d - 0.15,
            6.83,
            0.48,
            M["white"],
        )
        bands = (
            (6.31, 0.25, M["blue"]),
            (6.56, 0.22, M["white"]),
            (6.78, 0.28, M["orange"]),
            (7.04, 0.24, M["blue"]),
            (7.25, 0.17, M["white"]),
        )
        # Standing-seam weather skin and ridge cap remain visible in aerial
        # inspection shots and stop the roof reading as one blank slab.
        box(
            ctx,
            "canopy:hip_ridge_cap",
            (0, -2.5, 7.34),
            (w - 2.7, 0.15, 0.10),
            M["aluminum"],
            0.035,
            semantic="canopy_roof_ridge",
        )
        for i, x in enumerate(
            [-(w - 3.2) / 2 + j * 1.45 for j in range(int((w - 3.2) / 1.45) + 1)]
        ):
            instance_box(
                ctx,
                f"canopy:standing_seam_{i}",
                (x, -2.5, 7.335),
                (0.028, d - 2.45, 0.035),
                M["galvanized"],
                "canopy_roof_seam",
            )
    else:
        box(
            ctx,
            "canopy:flat_weather_skin",
            (0, -2.5, 6.93),
            (w + 0.12, d + 0.12, 0.23),
            M["white"],
            0.035,
            semantic="canopy_roof_weathering",
        )
        bands = (
            (6.46, 0.34, M["red"]),
            (6.76, 0.22, M["yellow"]),
            (6.97, 0.18, M["red"]),
            (7.13, 0.10, M["white"]),
        )
        box(
            ctx,
            "canopy:flat_roof_coping",
            (0, -2.5, 7.10),
            (w + 0.34, d + 0.34, 0.09),
            M["galvanized"],
            0.025,
            semantic="canopy_roof_coping",
        )
    for bi, (z, h, mat) in enumerate(bands):
        box(
            ctx,
            f"canopy:front_band_{bi}",
            (0, -2.5 - d / 2 - 0.06, z),
            (w + 0.18, 0.13, h),
            mat,
            0.018,
            semantic="canopy_fascia",
        )
        box(
            ctx,
            f"canopy:rear_band_{bi}",
            (0, -2.5 + d / 2 + 0.06, z),
            (w + 0.18, 0.13, h),
            mat,
            0.018,
            semantic="canopy_fascia",
        )
        box(
            ctx,
            f"canopy:left_band_{bi}",
            (-w / 2 - 0.06, -2.5, z),
            (0.13, d, h),
            mat,
            0.018,
            semantic="canopy_fascia",
        )
        box(
            ctx,
            f"canopy:right_band_{bi}",
            (w / 2 + 0.06, -2.5, z),
            (0.13, d, h),
            mat,
            0.018,
            semantic="canopy_fascia",
        )
    for seam, x in enumerate(
        [-w / 2 + 2.0 + i * 2.25 for i in range(int((w - 4.0) / 2.25) + 1)]
    ):
        instance_box(
            ctx,
            f"canopy:front_fascia_joint_{seam}",
            (x, -2.5 - d / 2 - 0.137, 6.82),
            (0.016, 0.018, 1.00),
            M["aluminum"],
            "fascia_panel_joint",
        )
        instance_cylinder(
            ctx,
            f"canopy:front_fascia_fastener_{seam}",
            (x, -2.5 - d / 2 - 0.151, 6.36),
            0.012,
            0.012,
            M["black"],
            "fastener",
            rotation=(math.pi / 2, 0, 0),
            vertices=10,
        )
    box(
        ctx,
        "canopy:continuous_shadow_reveal",
        (0, -2.5 - d / 2 - 0.132, 6.255),
        (w + 0.10, 0.045, 0.065),
        M["black"],
        0.008,
        semantic="canopy_fascia_reveal",
    )
    return 6.26


def build_brand_emblem(ctx, M, front_y, z, center_x=None, scale=1.0):
    s = ctx.style
    if s.variant == "nobile_wave":
        # Three nested, physically extruded flame/teardrop fields.
        cx = -3.0 if center_x is None else center_x
        raw = [
            (-1.05, -0.12),
            (-0.82, 0.54),
            (-0.20, 1.15),
            (0.35, 0.62),
            (0.88, 0.25),
            (0.96, -0.22),
            (0.55, -0.70),
            (-0.20, -0.83),
            (-0.83, -0.55),
        ]
        base = [(cx + x * scale, z + zz * scale) for x, zz in raw]
        vertical_prism(
            ctx,
            "brand:nobile_outer_flame",
            base,
            front_y,
            0.09,
            M["blue"],
            "brand_logo",
        )
        vertical_prism(
            ctx,
            "brand:nobile_red_flame",
            [
                (cx + (x - cx) * 0.68 - 0.05 * scale, z + (pz - z) * 0.68)
                for x, pz in base
            ],
            front_y - 0.065,
            0.095,
            M["red"],
            "brand_logo",
        )
        vertical_prism(
            ctx,
            "brand:nobile_gold_flame",
            [
                (cx + (x - cx) * 0.37 + 0.02 * scale, z + (pz - z) * 0.37)
                for x, pz in base
            ],
            front_y - 0.13,
            0.10,
            M["yellow"],
            "brand_logo",
        )
    elif s.variant == "blue_orange":
        cx = -8.75 if center_x is None else center_x
        torus(
            ctx,
            "brand:orange_sun_ring",
            (cx, front_y, z),
            0.54 * scale,
            0.10 * scale,
            M["orange"],
            (math.pi / 2, 0, 0),
            "brand_logo",
            32,
            8,
        )
        for i in range(8):
            a = i * math.tau / 8
            x = cx + 0.80 * scale * math.cos(a)
            zz = z + 0.80 * scale * math.sin(a)
            instance_box(
                ctx,
                f"brand:sun_ray_{i}",
                (x, front_y, zz),
                (0.31 * scale, 0.10, 0.075 * scale),
                M["orange"],
                "brand_logo",
                (0, a, 0),
            )
    else:
        cx = -7.6 if center_x is None else center_x
        torus(
            ctx,
            "brand:nova_roundel",
            (cx, front_y, z),
            0.53 * scale,
            0.11 * scale,
            M["red"],
            (math.pi / 2, 0, 0),
            "brand_logo",
            36,
            9,
        )
        vertical_prism(
            ctx,
            "brand:nova_star",
            [
                (
                    cx + math.cos(math.pi / 2 + i * 4 * math.pi / 5) * 0.37 * scale,
                    z + math.sin(math.pi / 2 + i * 4 * math.pi / 5) * 0.37 * scale,
                )
                for i in range(5)
            ],
            front_y - 0.07,
            0.10,
            M["yellow"],
            "brand_logo",
        )


def build_canopy(ctx, M):
    underside = (
        wave_canopy_shell(ctx, M)
        if ctx.style.canopy_kind == "sculpted_wave"
        else rectangular_canopy_shell(ctx, M)
    )
    s = ctx.style
    w = s.canopy_width
    d = s.canopy_depth
    # Secondary steel frame, ribbed soffit, gutters and bolted columns.
    for iy, y in enumerate(
        [(-2.5 - d / 2) + 0.55 + i * 0.44 for i in range(int((d - 1.1) / 0.44) + 1)]
    ):
        instance_box(
            ctx,
            f"canopy:soffit_rib_{iy:02d}",
            (0, y, underside - 0.045),
            (w - 1.0, 0.038, 0.045),
            M["aluminum"],
            "soffit_rib",
        )
    for ix, x in enumerate(
        [-w / 2 + 1.15 + i * 3.1 for i in range(int((w - 2.3) / 3.1) + 1)]
    ):
        instance_box(
            ctx,
            f"canopy:primary_joist_{ix:02d}",
            (x, -2.5, underside + 0.045),
            (0.11, d - 1.0, 0.16),
            M["galvanized"],
            "canopy_primary_joist",
        )
    for x in (-w / 2 + 1.1, w / 2 - 1.1):
        box(
            ctx,
            f"canopy:gutter_{'l' if x<0 else 'r'}",
            (x, -2.5, underside + 0.03),
            (0.22, d - 0.8, 0.20),
            M["galvanized"],
            0.018,
            semantic="rain_gutter",
        )
    col_x = (-10.3, 0, 10.3) if s.variant == "blue_orange" else (-8.4, 8.4)
    col_y = (-5.0, 0.2) if s.variant != "blue_orange" else (-5.2, 0.3)
    for ix, x in enumerate(col_x):
        for iy, y in enumerate(col_y):
            name = f"canopy:column_{ix}_{iy}"
            box(
                ctx,
                name + ":footing",
                (x, y, 0.24),
                (1.18, 1.18, 0.28),
                M["concrete_light"],
                0.12,
                semantic="column_footing",
            )
            box(
                ctx,
                name + ":base_plate",
                (x, y, 0.42),
                (0.86, 0.86, 0.10),
                M["steel"],
                0.055,
                semantic="column_base_plate",
            )
            if s.variant == "nobile_wave":
                cylinder(
                    ctx,
                    name + ":shaft",
                    (x, y, 3.28),
                    0.31,
                    5.72,
                    M["white"],
                    32,
                    semantic="canopy_column",
                    bevel=0.025,
                )
                box(
                    ctx,
                    name + ":brand_cladding",
                    (x, y - 0.315, 3.35),
                    (0.24, 0.075, 4.30),
                    M["yellow"],
                    0.025,
                    semantic="column_brand_cladding",
                )
            else:
                box(
                    ctx,
                    name + ":shaft",
                    (x, y, 3.30),
                    (0.68, 0.68, 5.76),
                    M["white"],
                    0.055,
                    semantic="canopy_column",
                )
                if s.variant == "blue_orange":
                    box(
                        ctx,
                        name + ":brand_cladding",
                        (x, y - 0.37, 3.0),
                        (0.51, 0.09, 3.70),
                        M["blue"],
                        0.025,
                        semantic="column_brand_cladding",
                    )
                    box(
                        ctx,
                        name + ":accent_panel",
                        (x, y - 0.425, 3.05),
                        (0.27, 0.04, 1.25),
                        M["green"],
                        0.012,
                        semantic="column_wayfinding",
                    )
            box(
                ctx,
                name + ":capital",
                (x, y, 6.16),
                (1.05, 1.05, 0.24),
                M["steel"],
                0.055,
                semantic="column_capital",
            )
            box(
                ctx,
                name + ":neck_plate",
                (x, y, 5.90),
                (0.86, 0.86, 0.12),
                M["galvanized"],
                0.035,
                semantic="column_connection_plate",
            )
            for bolt in range(8):
                a = bolt * math.tau / 8
                instance_cylinder(
                    ctx,
                    f"{name}:anchor_bolt_{bolt}",
                    (x + 0.30 * math.cos(a), y + 0.30 * math.sin(a), 0.49),
                    0.023,
                    0.08,
                    M["black"],
                    "fastener",
                    vertices=10,
                )
            cylinder(
                ctx,
                name + ":downpipe",
                (x + 0.34, y, 3.28),
                0.045,
                5.35,
                M["galvanized"],
                14,
                semantic="rainwater_downpipe",
                bevel=0.003,
            )
            for zi in (1.2, 2.7, 4.2):
                instance_box(
                    ctx,
                    f"{name}:pipe_clip_{zi}",
                    (x + 0.34, y - 0.06, zi),
                    (0.20, 0.13, 0.035),
                    M["steel"],
                    "pipe_bracket",
                )
    # Recessed luminaire frames and real area lights.
    lx = (-8.5, -2.8, 2.8, 8.5) if s.variant == "blue_orange" else (-7.0, 0, 7.0)
    for ix, x in enumerate(lx):
        for iy, y in enumerate((-5.2, 0.2)):
            box(
                ctx,
                f"canopy:light_recess_{ix}_{iy}",
                (x, y, underside - 0.10),
                (2.15, 1.02, 0.10),
                M["black"],
                0.08,
                semantic="canopy_light_recess",
            )
            box(
                ctx,
                f"canopy:light_diffuser_{ix}_{iy}",
                (x, y, underside - 0.165),
                (1.90, 0.79, 0.035),
                M["warm_light"],
                0.04,
                semantic="canopy_light",
            )
            if iy == 0:
                area_light(
                    ctx,
                    f"canopy:area_light_{ix}",
                    (x, y, underside - 0.22),
                    180,
                    (2.0, 0.9),
                    (0.98, 0.92, 0.78),
                )
    # Real forecourt canopies expose layered safety and electrical services
    # beneath the deck.  These small but readable systems prevent the soffit
    # from appearing as a single unbuilt slab in close and oblique views.
    tube(
        ctx,
        "canopy:fire_suppression_main",
        [
            (-w / 2 + 1.3, -1.65, underside - 0.23),
            (w / 2 - 1.3, -1.65, underside - 0.23),
        ],
        0.032,
        M["safety_red"],
        "canopy_fire_main",
    )
    sprinkler_x = [
        -w / 2 + 2.2 + i * 3.2 for i in range(max(2, int((w - 4.4) / 3.2) + 1))
    ]
    for head_i, x in enumerate(sprinkler_x):
        cylinder(
            ctx,
            f"canopy:sprinkler_drop_{head_i}",
            (x, -1.65, underside - 0.39),
            0.017,
            0.30,
            M["steel"],
            12,
            semantic="canopy_sprinkler_drop",
            bevel=0.002,
        )
        cylinder(
            ctx,
            f"canopy:sprinkler_head_{head_i}",
            (x, -1.65, underside - 0.56),
            0.052,
            0.018,
            M["chrome"],
            18,
            semantic="canopy_sprinkler_head",
            bevel=0.003,
        )
        torus(
            ctx,
            f"canopy:sprinkler_guard_{head_i}",
            (x, -1.65, underside - 0.55),
            0.065,
            0.008,
            M["steel"],
            semantic="canopy_sprinkler_guard",
            major_segments=20,
            minor_segments=5,
        )
    tube(
        ctx,
        "canopy:electrical_conduit",
        [
            (-w / 2 + 1.1, -3.25, underside - 0.20),
            (w / 2 - 1.1, -3.25, underside - 0.20),
        ],
        0.021,
        M["galvanized"],
        "canopy_electrical_conduit",
    )
    for box_i, x in enumerate((-w * 0.28, 0, w * 0.28)):
        box(
            ctx,
            f"canopy:junction_box_{box_i}",
            (x, -3.25, underside - 0.26),
            (0.30, 0.22, 0.13),
            M["galvanized"],
            0.025,
            semantic="canopy_junction_box",
        )
        for clip in (-0.28, 0.28):
            instance_box(
                ctx,
                f"canopy:conduit_clip_{box_i}_{clip}",
                (x + clip, -3.25, underside - 0.215),
                (0.055, 0.09, 0.018),
                M["steel"],
                "canopy_conduit_clip",
            )
    cam_x = w / 2 - 1.65
    cam_y = -2.5 - d / 2 + 1.0
    beam(
        ctx,
        "canopy:cctv_bracket",
        (cam_x, cam_y, underside - 0.08),
        (cam_x, cam_y, underside - 0.52),
        0.025,
        M["steel"],
        "cctv_bracket",
        14,
    )
    rounded_vertical_prism(
        ctx,
        "canopy:cctv_housing",
        cam_x,
        underside - 0.61,
        0.38,
        0.22,
        0.08,
        cam_y - 0.04,
        0.24,
        M["white"],
        "cctv_camera",
        6,
    )
    cylinder(
        ctx,
        "canopy:cctv_lens",
        (cam_x, cam_y - 0.178, underside - 0.61),
        0.065,
        0.035,
        M["display_glass"],
        24,
        rotation=(math.pi / 2, 0, 0),
        semantic="cctv_lens",
        bevel=0.008,
    )
    # Reference 3 exposes a glazed triangular service-bay frame behind the
    # dispensers.  Model the actual steel triangulation instead of drawing it
    # onto the store facade.
    if s.variant == "red_yellow":
        truss_y = 4.45
        for bay in range(4):
            x0 = -7.2 + bay * 3.6
            x1 = x0 + 3.6
            xm = (x0 + x1) / 2
            beam(
                ctx,
                f"canopy:rear_truss_bottom_{bay}",
                (x0, truss_y, 5.48),
                (x1, truss_y, 5.48),
                0.045,
                M["steel"],
                "canopy_rear_truss",
                14,
            )
            beam(
                ctx,
                f"canopy:rear_truss_left_{bay}",
                (x0, truss_y, 5.48),
                (xm, truss_y, 6.25),
                0.045,
                M["steel"],
                "canopy_rear_truss",
                14,
            )
            beam(
                ctx,
                f"canopy:rear_truss_right_{bay}",
                (xm, truss_y, 6.25),
                (x1, truss_y, 5.48),
                0.045,
                M["steel"],
                "canopy_rear_truss",
                14,
            )
    front_y = -2.5 - d / 2 - 0.145
    build_brand_emblem(ctx, M, front_y, 7.02 if s.variant != "nobile_wave" else 7.10)
    # Large, individually extruded channel letters.  The fit helper records
    # and enforces the usable fascia bounds so letters are legible without
    # ever crossing the sign region.
    if s.variant == "nobile_wave":
        display_brand = "Nobile"
        label_x = 2.25
        panel_w = 5.2
        panel_h = 0.82
        sign_mat = M["black"]
        font = FONT_BOLD
        sign_z = 7.08
        sign_extrude = 0.045
    elif s.variant == "blue_orange":
        display_brand = "BLUEWAY ENERGY"
        label_x = 2.15
        panel_w = 9.4
        panel_h = 0.62
        sign_mat = M["white"]
        font = FONT_BOLD
        sign_z = 7.04
        sign_extrude = 0.036
    else:
        display_brand = "NOVA FUEL"
        label_x = 2.10
        panel_w = 6.6
        panel_h = 0.72
        sign_mat = M["white"]
        font = FONT_BOLD
        sign_z = 6.79
        sign_extrude = 0.045
    text_front_fitted(
        ctx,
        "brand:canopy_wordmark",
        display_brand,
        (label_x, front_y - 0.035, sign_z),
        panel_w,
        panel_h,
        sign_mat,
        sign_extrude,
        font_path=font,
        semantic="canopy_brand_wordmark",
        margin=0.08,
    )
    return underside


# ---------------------------------------------------------------------------
# Fuel dispensing, safety equipment and roadside identity


def style_materials(ctx, M):
    if ctx.variant == "nobile_wave":
        return M["red"], M["yellow"], M["orange"]
    if ctx.variant == "blue_orange":
        return M["blue"], M["orange"], M["blue_light"]
    return M["red"], M["yellow"], M["black"]


def build_bollard(ctx, name, x, y, M, color=None):
    sleeve = color or M["steel"]
    cylinder(
        ctx,
        name + ":footing",
        (x, y, 0.32),
        0.17,
        0.15,
        M["concrete_light"],
        28,
        semantic="bollard_footing",
        bevel=0.014,
    )
    cylinder(
        ctx,
        name + ":shaft",
        (x, y, 0.74),
        0.092,
        0.82,
        M["galvanized"],
        32,
        semantic="impact_bollard",
        bevel=0.014,
    )
    cylinder(
        ctx,
        name + ":protective_sleeve",
        (x, y, 0.61),
        0.099,
        0.43,
        sleeve,
        32,
        semantic="bollard_protective_sleeve",
        bevel=0.009,
    )
    cylinder(
        ctx,
        name + ":reflective_band",
        (x, y, 0.91),
        0.099,
        0.095,
        M["road_white"],
        32,
        semantic="reflective_band",
        bevel=0.003,
    )
    cylinder(
        ctx,
        name + ":cap",
        (x, y, 1.17),
        0.100,
        0.07,
        M["steel"],
        32,
        semantic="bollard_cap",
        bevel=0.014,
    )


def build_nozzle(ctx, base_name, loc, side_sign, front_sign, M):
    x, y, z = loc
    # A real pistol silhouette is extruded from one continuous profile; the
    # grip, trigger loop and bent stainless spout are not stacked primitives.
    box(
        ctx,
        base_name + ":holster",
        (x, y, z),
        (0.20, 0.13, 0.48),
        M["sealant"],
        0.035,
        semantic="nozzle_holster",
    )
    sx = lambda value: x + side_sign * value
    profile = [
        (sx(-0.075), z + 0.19),
        (sx(0.050), z + 0.20),
        (sx(0.120), z + 0.115),
        (sx(0.095), z + 0.015),
        (sx(0.055), z - 0.19),
        (sx(-0.035), z - 0.18),
        (sx(-0.020), z - 0.015),
        (sx(-0.110), z + 0.055),
    ]
    vertical_prism(
        ctx,
        base_name + ":pistol_body",
        profile,
        y - front_sign * 0.085,
        0.115,
        M["black_gloss"],
        "fuel_nozzle",
    )
    guard = [
        (sx(0.015), y - front_sign * 0.153, z + 0.055),
        (sx(0.125), y - front_sign * 0.153, z + 0.040),
        (sx(0.105), y - front_sign * 0.153, z - 0.095),
        (sx(0.018), y - front_sign * 0.153, z - 0.105),
    ]
    tube(
        ctx,
        base_name + ":trigger_guard",
        guard,
        0.012,
        M["steel"],
        "fuel_nozzle_guard",
        cyclic=True,
    )
    beam(
        ctx,
        base_name + ":trigger",
        (sx(0.050), y - front_sign * 0.165, z + 0.025),
        (sx(0.072), y - front_sign * 0.165, z - 0.068),
        0.012,
        M["safety_yellow"],
        "fuel_nozzle_trigger",
        10,
    )
    for ridge in range(4):
        beam(
            ctx,
            f"{base_name}:grip_ridge_{ridge}",
            (
                sx(0.052 + ridge * 0.008),
                y - front_sign * 0.150,
                z - 0.015 - ridge * 0.038,
            ),
            (
                sx(0.095 + ridge * 0.008),
                y - front_sign * 0.150,
                z - 0.025 - ridge * 0.038,
            ),
            0.006,
            M["rubber"],
            "nozzle_grip_rib",
            8,
        )
    cylinder(
        ctx,
        base_name + ":coupling",
        (x, y + front_sign * 0.105, z - 0.235),
        0.065,
        0.19,
        M["steel"],
        20,
        rotation=(math.pi / 2, 0, 0),
        semantic="hose_coupling",
        bevel=0.008,
    )
    for ring in (-0.045, 0, 0.045):
        torus(
            ctx,
            f"{base_name}:coupling_ring_{ring}",
            (x, y + front_sign * (0.105 + ring), z - 0.235),
            0.067,
            0.009,
            M["black"],
            (math.pi / 2, 0, 0),
            "hose_coupling_detail",
            24,
            6,
        )
    tube(
        ctx,
        base_name + ":spout",
        [
            (sx(-0.055), y - front_sign * 0.085, z + 0.155),
            (sx(0.055), y - front_sign * 0.20, z + 0.245),
            (sx(0.245), y - front_sign * 0.30, z + 0.31),
            (sx(0.38), y - front_sign * 0.31, z + 0.285),
        ],
        0.021,
        M["steel"],
        "fuel_nozzle_spout",
    )
    cylinder(
        ctx,
        base_name + ":spout_tip",
        (sx(0.40), y - front_sign * 0.31, z + 0.285),
        0.026,
        0.105,
        M["steel"],
        18,
        rotation=(0, math.pi / 2, 0),
        semantic="fuel_nozzle_spout_tip",
        bevel=0.004,
    )


def build_fuel_dispenser(ctx, index, x, y, M):
    primary, secondary, accent = style_materials(ctx, M)
    name = f"dispenser:{index:02d}"
    # Compact chamfered containment island at real service-station scale.
    box(
        ctx,
        name + ":island",
        (x, y, 0.30),
        (1.88, 3.30, 0.26),
        M["concrete_light"],
        0.16,
        semantic="pump_island",
    )
    for side in (-1, 1):
        for i in range(7):
            yy = y - 1.30 + (i + 0.5) * 2.60 / 7
            instance_box(
                ctx,
                f"{name}:hazard_{side}_{i}",
                (x + side * 0.945, yy, 0.445),
                (0.055, 0.31, 0.075),
                M["black" if i % 2 else "safety_yellow"],
                "island_hazard_marking",
            )
    for bx, by in (
        (x - 0.72, y - 1.26),
        (x + 0.72, y - 1.26),
        (x - 0.72, y + 1.26),
        (x + 0.72, y + 1.26),
    ):
        build_bollard(ctx, name + f":bollard_{bx:.2f}_{by:.2f}", bx, by, M, primary)
    # One radiused folded-metal cabinet with a separate stainless plinth and
    # integrated rectangular brand header.  Continuous surfaces replace the
    # conspicuous oval cap and stacked-block body of the previous revision.
    rounded_vertical_prism(
        ctx,
        name + ":base_plinth",
        x,
        0.59,
        1.13,
        0.24,
        0.07,
        y,
        0.76,
        M["steel"],
        "dispenser_plinth",
        7,
    )
    body_mat = (
        M["paint_gray"]
        if ctx.variant in {"blue_orange", "red_yellow"}
        else M["white_warm"]
    )
    cabinet = rounded_vertical_prism(
        ctx,
        name + ":formed_cabinet",
        x,
        1.48,
        1.10,
        1.76,
        0.11,
        y,
        0.66,
        body_mat,
        "fuel_dispenser",
        8,
    )
    cabinet["c2w_manufactured_form"] = "single_radiused_folded_sheet_cabinet"
    cabinet["c2w_dispenser_revision"] = MODEL_REVISION
    header = box(
        ctx,
        name + ":integrated_header",
        (x, y, 2.36),
        (1.16, 0.70, 0.28),
        primary,
        0.038,
        semantic="dispenser_brand_crown",
    )
    header["c2w_manufactured_form"] = "integrated_folded_rectangular_header"
    box(
        ctx,
        name + ":header_inset",
        (x, y - 0.366, 2.36),
        (0.91, 0.028, 0.125),
        secondary,
        0.016,
        semantic="dispenser_brand_accent",
    )
    for side in (-1, 1):
        box(
            ctx,
            name + f":rolled_edge_{side}",
            (x + side * 0.525, y, 1.50),
            (0.055, 0.71, 1.55),
            M["steel"],
            0.018,
            semantic="dispenser_rolled_edge",
        )
        box(
            ctx,
            name + f":side_brand_panel_{side}",
            (x + side * 0.558, y, 1.67),
            (0.035, 0.54, 0.86),
            primary,
            0.012,
            semantic="dispenser_brand_cladding",
        )
        box(
            ctx,
            name + f":side_service_reveal_{side}",
            (x + side * 0.579, y, 1.05),
            (0.012, 0.48, 0.38),
            M["sealant"],
            0.003,
            semantic="dispenser_side_panel",
        )
        for rivet, yy in enumerate((y - 0.23, y, y + 0.23)):
            cylinder(
                ctx,
                f"{name}:side_rivet_{side}_{rivet}",
                (x + side * 0.588, yy, 1.05),
                0.012,
                0.012,
                M["steel"],
                10,
                rotation=(0, math.pi / 2, 0),
                semantic="dispenser_panel_fastener",
                bevel=0.002,
            )
    pump_brand = (
        "Nobile"
        if ctx.variant == "nobile_wave"
        else ("ENERGY" if ctx.variant == "blue_orange" else "NOVA")
    )
    text_front_fitted(
        ctx,
        name + ":header_wordmark",
        pump_brand,
        (x, y - 0.405, 2.36),
        0.82,
        0.14,
        M["white_emit"],
        0.010,
        semantic="dispenser_brand_wordmark",
        margin=0.012,
    )
    # Both customer faces are manufactured as nested modules: anti-glare
    # meter glass, payment hardware, grade-selection strip and framed lower
    # service hatch.  The geometry is duplicated on the rear service face.
    for face, sgn in (("front", -1), ("rear", 1)):
        shell_y = y + sgn * 0.345
        detail_y = y + sgn * 0.382
        box(
            ctx,
            f"{name}:{face}:meter_module",
            (x, shell_y, 1.94),
            (0.91, 0.065, 0.55),
            M["black_gloss"],
            0.055,
            semantic="fuel_dispenser_meter_face",
        )
        box(
            ctx,
            f"{name}:{face}:display_bezel",
            (x, detail_y, 2.055),
            (0.76, 0.030, 0.275),
            M["black"],
            0.026,
            semantic="pump_display_bezel",
        )
        box(
            ctx,
            f"{name}:{face}:display_glass",
            (x, detail_y + sgn * 0.020, 2.065),
            (0.63, 0.018, 0.16),
            M["display_glass"],
            0.018,
            semantic="dispenser_display_window",
        )
        box(
            ctx,
            f"{name}:{face}:lcd",
            (x, detail_y + sgn * 0.031, 2.065),
            (0.54, 0.010, 0.105),
            M["lcd"],
            0.008,
            semantic="pump_display",
        )
        # Payment terminal: recessed surround, screen, card/receipt slots,
        # twelve individual keys and a speaker grille.
        box(
            ctx,
            f"{name}:{face}:payment_surround",
            (x - 0.23, detail_y, 1.715),
            (0.36, 0.030, 0.27),
            M["black"],
            0.030,
            semantic="dispenser_payment_module",
        )
        box(
            ctx,
            f"{name}:{face}:payment_screen",
            (x - 0.23, detail_y + sgn * 0.020, 1.775),
            (0.22, 0.014, 0.085),
            M["screen"],
            0.010,
            semantic="contactless_reader",
        )
        for row in range(4):
            for col in range(3):
                instance_box(
                    ctx,
                    f"{name}:{face}:key_{row}_{col}",
                    (
                        x - 0.305 + col * 0.075,
                        detail_y + sgn * 0.024,
                        1.69 - row * 0.043,
                    ),
                    (0.040, 0.014, 0.025),
                    M["steel"],
                    "pump_keypad",
                )
        box(
            ctx,
            f"{name}:{face}:card_slot",
            (x - 0.23, detail_y + sgn * 0.026, 1.555),
            (0.18, 0.014, 0.025),
            M["black"],
            0.004,
            semantic="payment_card_slot",
        )
        box(
            ctx,
            f"{name}:{face}:receipt_slot",
            (x + 0.25, detail_y + sgn * 0.026, 1.79),
            (0.22, 0.014, 0.030),
            M["black"],
            0.004,
            semantic="receipt_slot",
        )
        for hole in range(5):
            cylinder(
                ctx,
                f"{name}:{face}:speaker_{hole}",
                (x + 0.17 + hole * 0.038, detail_y + sgn * 0.030, 1.665),
                0.008,
                0.010,
                M["sealant"],
                8,
                rotation=(math.pi / 2, 0, 0),
                semantic="payment_speaker_grille",
                bevel=0.001,
            )
        box(
            ctx,
            f"{name}:{face}:grade_control_rail",
            (x, detail_y, 1.435),
            (0.76, 0.032, 0.20),
            M["black_gloss"],
            0.025,
            semantic="dispenser_grade_control_rail",
        )
        for grade in range(3):
            gx = x - 0.25 + grade * 0.25
            grade_mat = (M["green"], secondary, primary)[grade]
            rounded_vertical_prism(
                ctx,
                f"{name}:{face}:grade_button_{grade}",
                gx,
                1.455,
                0.18,
                0.085,
                0.022,
                detail_y + sgn * 0.022,
                0.026,
                grade_mat,
                "grade_selection_button",
                4,
            )
            box(
                ctx,
                f"{name}:{face}:grade_label_{grade}",
                (gx, detail_y + sgn * 0.030, 1.385),
                (0.16, 0.014, 0.026),
                grade_mat,
                0.004,
                semantic="fuel_grade_label",
            )
            if face == "front":
                text_front_fitted(
                    ctx,
                    f"{name}:{face}:grade_text_{grade}",
                    ("87", "89", "93")[grade],
                    (gx, detail_y - 0.052, 1.455),
                    0.13,
                    0.052,
                    M["white_emit"],
                    0.005,
                    semantic="dispenser_grade_text",
                    margin=0.008,
                )
        box(
            ctx,
            f"{name}:{face}:instruction_plate",
            (x, detail_y + sgn * 0.030, 1.265),
            (0.70, 0.016, 0.11),
            M["decal_white"],
            0.005,
            semantic="safety_instruction_plate",
        )
        box(
            ctx,
            f"{name}:{face}:warning_band",
            (x, detail_y + sgn * 0.040, 1.245),
            (0.66, 0.008, 0.025),
            M["warning"],
            0.002,
            semantic="dispenser_instruction_decal",
        )
        # A genuinely recessed lower hatch with perimeter seam, hinges, latch,
        # serial plate and ventilation slots.
        box(
            ctx,
            f"{name}:{face}:service_hatch",
            (x, shell_y, 0.92),
            (0.79, 0.050, 0.55),
            body_mat,
            0.035,
            semantic="dispenser_service_panel",
        )
        front_panel_frame(
            ctx,
            f"{name}:{face}:service_hatch_frame",
            (x, detail_y, 0.92),
            0.82,
            0.58,
            0.025,
            0.022,
            M["sealant"],
            "dispenser_service_hatch_seam",
        )
        for vent in range(7):
            instance_box(
                ctx,
                f"{name}:{face}:vent_{vent}",
                (x - 0.27 + vent * 0.09, detail_y + sgn * 0.030, 0.82),
                (0.050, 0.012, 0.015),
                M["sealant"],
                "dispenser_vent",
            )
        cylinder(
            ctx,
            f"{name}:{face}:service_lock",
            (x + 0.31, detail_y + sgn * 0.032, 1.02),
            0.026,
            0.014,
            M["chrome"],
            16,
            rotation=(math.pi / 2, 0, 0),
            semantic="dispenser_service_lock",
            bevel=0.003,
        )
        for hinge, zz in enumerate((0.77, 1.08)):
            cylinder(
                ctx,
                f"{name}:{face}:service_hinge_{hinge}",
                (x - 0.36, detail_y + sgn * 0.032, zz),
                0.018,
                0.065,
                M["steel"],
                12,
                rotation=(math.pi / 2, 0, 0),
                semantic="dispenser_service_hinge",
                bevel=0.003,
            )
        box(
            ctx,
            f"{name}:{face}:serial_plate",
            (x + 0.22, detail_y + sgn * 0.034, 0.70),
            (0.26, 0.010, 0.065),
            M["decal_white"],
            0.003,
            semantic="dispenser_serial_plate",
        )
        if face == "front":
            text_front_fitted(
                ctx,
                f"{name}:price_readout",
                "$ 0.00",
                (x, detail_y - 0.052, 2.065),
                0.48,
                0.075,
                M["white_emit"],
                0.006,
                semantic="pump_display_text",
                margin=0.006,
            )
            text_front_fitted(
                ctx,
                f"{name}:display_sale_label",
                "SALE $",
                (x - 0.18, detail_y - 0.052, 2.137),
                0.22,
                0.025,
                M["white_emit"],
                0.003,
                semantic="dispenser_display_label",
                margin=0.002,
            )
            text_front_fitted(
                ctx,
                f"{name}:display_volume_label",
                "LITRES",
                (x + 0.18, detail_y - 0.052, 2.137),
                0.22,
                0.025,
                M["white_emit"],
                0.003,
                semantic="dispenser_display_label",
                margin=0.002,
            )
            text_front_fitted(
                ctx,
                f"{name}:payment_label",
                "PAY HERE",
                (x - 0.23, detail_y - 0.052, 1.842),
                0.25,
                0.035,
                M["white_emit"],
                0.003,
                semantic="dispenser_payment_label",
                margin=0.003,
            )
            text_front_fitted(
                ctx,
                f"{name}:instruction_copy",
                "PAY  •  SELECT  •  FUEL",
                (x, detail_y - 0.052, 1.265),
                0.58,
                0.045,
                M["black"],
                0.004,
                semantic="dispenser_instruction_text",
                margin=0.003,
            )
    # Twin grade hoses per customer face: 4 complete hose/nozzle assemblies.
    for front_sign in (-1, 1):
        for side_sign in (-1, 1):
            sx = x + side_sign * 0.51
            sy = y + front_sign * 0.24
            cylinder(
                ctx,
                f"{name}:breakaway_{front_sign}_{side_sign}",
                (sx, sy, 2.29),
                0.047,
                0.16,
                M["steel"],
                18,
                rotation=(math.pi / 2, 0, 0),
                semantic="hose_breakaway_coupling",
                bevel=0.006,
            )
            box(
                ctx,
                f"{name}:hose_cradle_{front_sign}_{side_sign}",
                (x + side_sign * 0.56, y + front_sign * 0.30, 2.13),
                (0.10, 0.10, 0.18),
                M["black"],
                0.025,
                semantic="hose_support_bracket",
            )
            hose_points = [
                (sx, sy, 2.27),
                (x + side_sign * 0.72, y + front_sign * 0.32, 2.03),
                (x + side_sign * 0.78, y + front_sign * 0.40, 1.12),
                (x + side_sign * 0.70, y + front_sign * 0.41, 0.69),
                (x + side_sign * 0.58, y + front_sign * 0.40, 1.10),
            ]
            hname = f"{name}:hose_{'f' if front_sign<0 else 'r'}_{'l' if side_sign<0 else 'r'}"
            tube(ctx, hname, hose_points, 0.022, M["rubber"], "fuel_hose")
            build_nozzle(
                ctx,
                hname + ":nozzle",
                (x + side_sign * 0.58, y + front_sign * 0.405, 1.22),
                side_sign,
                front_sign,
                M,
            )
    # Flush emergency-stop enclosure, bonding point and anchored base hardware.
    box(
        ctx,
        name + ":emergency_stop_box",
        (x + 0.72, y - 0.58, 0.69),
        (0.18, 0.14, 0.24),
        M["warning"],
        0.025,
        semantic="emergency_stop_enclosure",
    )
    cylinder(
        ctx,
        name + ":emergency_stop_button",
        (x + 0.72, y - 0.66, 0.72),
        0.052,
        0.038,
        M["safety_red"],
        20,
        rotation=(math.pi / 2, 0, 0),
        semantic="emergency_stop_button",
        bevel=0.006,
    )
    cylinder(
        ctx,
        name + ":bonding_point",
        (x - 0.46, y - 0.355, 0.63),
        0.032,
        0.025,
        M["green"],
        14,
        rotation=(math.pi / 2, 0, 0),
        semantic="dispenser_bonding_point",
        bevel=0.003,
    )
    for bolt, (bx, by) in enumerate(
        (
            (x - 0.44, y - 0.26),
            (x + 0.44, y - 0.26),
            (x - 0.44, y + 0.26),
            (x + 0.44, y + 0.26),
        )
    ):
        cylinder(
            ctx,
            f"{name}:base_anchor_{bolt}",
            (bx, by, 0.48),
            0.026,
            0.045,
            M["steel"],
            12,
            semantic="dispenser_base_anchor",
            bevel=0.004,
        )
    text_front_fitted(
        ctx,
        name + ":island_number",
        str(index + 1),
        (x, y - 1.675, 0.53),
        0.24,
        0.18,
        M["white_emit"],
        0.010,
        semantic="island_identifier",
        margin=0.018,
    )
    return name


def build_squeegee_bin(ctx, name, x, y, M):
    cylinder(
        ctx,
        name + ":body",
        (x, y, 0.79),
        0.31,
        1.10,
        M["black"],
        28,
        semantic="forecourt_bin",
        bevel=0.035,
    )
    cylinder(
        ctx,
        name + ":rim",
        (x, y, 1.35),
        0.335,
        0.10,
        M["steel"],
        28,
        semantic="bin_rim",
        bevel=0.015,
    )
    box(
        ctx,
        name + ":waste_slot",
        (x, y - 0.305, 1.13),
        (0.34, 0.045, 0.16),
        M["rubber"],
        0.025,
        semantic="bin_waste_slot",
    )
    cylinder(
        ctx,
        name + ":bucket",
        (x + 0.42, y, 0.89),
        0.16,
        0.72,
        M["blue"],
        22,
        semantic="squeegee_bucket",
        bevel=0.018,
    )
    beam(
        ctx,
        name + ":squeegee_handle",
        (x + 0.42, y, 1.12),
        (x + 0.60, y, 2.0),
        0.022,
        M["steel"],
        "squeegee",
    )
    box(
        ctx,
        name + ":squeegee_head",
        (x + 0.63, y, 2.07),
        (0.45, 0.08, 0.055),
        M["rubber"],
        0.015,
        rotation=(0, 0.20, 0),
        semantic="squeegee",
    )


def build_fire_cabinet(ctx, M):
    x, y = 14.9, -7.0
    box(
        ctx,
        "safety:fire_cabinet_body",
        (x, y, 1.05),
        (0.72, 0.42, 1.52),
        M["safety_red"],
        0.06,
        semantic="fire_safety_cabinet",
    )
    box(
        ctx,
        "safety:fire_cabinet_glass",
        (x, y - 0.225, 1.12),
        (0.52, 0.025, 0.94),
        M["glass"],
        0.025,
        semantic="cabinet_glazing",
    )
    cylinder(
        ctx,
        "safety:extinguisher_body",
        (x, y - 0.02, 0.95),
        0.13,
        0.67,
        M["safety_red"],
        24,
        semantic="fire_extinguisher",
        bevel=0.018,
    )
    cylinder(
        ctx,
        "safety:extinguisher_valve",
        (x, y - 0.02, 1.34),
        0.055,
        0.12,
        M["steel"],
        16,
        semantic="extinguisher_valve",
        bevel=0.005,
    )
    tube(
        ctx,
        "safety:extinguisher_hose",
        [
            (x + 0.08, y - 0.04, 1.30),
            (x + 0.23, y - 0.08, 1.22),
            (x + 0.20, y - 0.10, 0.92),
        ],
        0.018,
        M["rubber"],
        "extinguisher_hose",
    )
    text_front(
        ctx,
        "safety:fire_label",
        "FIRE",
        (x, y - 0.255, 1.67),
        0.16,
        M["white_emit"],
        0.012,
        semantic="safety_signage",
    )
    for i in range(3):
        # Weighted rubber cone with reflective collar, not a single orange cone.
        cx = 13.65 + i * 0.58
        cylinder(
            ctx,
            f"safety:cone_{i}:base",
            (cx, -7.8, 0.31),
            0.25,
            0.10,
            M["rubber"],
            24,
            semantic="traffic_cone",
        )
        cylinder(
            ctx,
            f"safety:cone_{i}:body",
            (cx, -7.8, 0.69),
            0.17,
            0.72,
            M["orange"],
            24,
            semantic="traffic_cone",
            bevel=0.006,
            radius_top=0.035,
        )
        cylinder(
            ctx,
            f"safety:cone_{i}:band",
            (cx, -7.8, 0.72),
            0.115,
            0.14,
            M["road_white"],
            24,
            semantic="reflective_cone_band",
            bevel=0.003,
            radius_top=0.09,
        )


def build_air_water_service(ctx, M):
    """Modeled compressor cabinet, gauge, coin reader and coiled service hose."""
    primary, secondary, _ = style_materials(ctx, M)
    x, y = -14.65, 3.55
    box(
        ctx,
        "service:air_machine_plinth",
        (x, y, 0.32),
        (1.42, 1.05, 0.28),
        M["concrete_light"],
        0.10,
        semantic="air_service_plinth",
    )
    profile = [
        (x - 0.56, 0.48),
        (x - 0.62, 0.62),
        (x - 0.62, 1.92),
        (x - 0.49, 2.10),
        (x + 0.49, 2.10),
        (x + 0.62, 1.92),
        (x + 0.62, 0.62),
        (x + 0.56, 0.48),
    ]
    vertical_prism(
        ctx,
        "service:air_machine_case",
        profile,
        y,
        0.72,
        M["galvanized"],
        "air_service_machine",
    )
    box(
        ctx,
        "service:air_machine_brand",
        (x, y - 0.385, 1.86),
        (1.02, 0.045, 0.28),
        primary,
        0.035,
        semantic="air_service_brand_panel",
    )
    text_front(
        ctx,
        "service:air_word",
        "AIR / WATER",
        (x, y - 0.418, 1.87),
        0.15,
        M["white_emit"],
        0.012,
        semantic="air_service_label",
    )
    cylinder(
        ctx,
        "service:pressure_gauge",
        (x - 0.25, y - 0.415, 1.43),
        0.145,
        0.035,
        M["glass_dark"],
        28,
        rotation=(math.pi / 2, 0, 0),
        semantic="pressure_gauge",
        bevel=0.010,
    )
    for tick in range(9):
        a = math.radians(205 - tick * 23)
        box(
            ctx,
            f"service:gauge_tick_{tick}",
            (x - 0.25 + 0.105 * math.cos(a), y - 0.438, 1.43 + 0.105 * math.sin(a)),
            (0.014, 0.010, 0.035),
            M["white_emit"],
            0.004,
            rotation=(0, a, 0),
            semantic="gauge_marking",
        )
    box(
        ctx,
        "service:coin_reader",
        (x + 0.25, y - 0.420, 1.43),
        (0.25, 0.035, 0.34),
        M["black"],
        0.035,
        semantic="air_service_coin_reader",
    )
    box(
        ctx,
        "service:coin_slot",
        (x + 0.25, y - 0.445, 1.50),
        (0.12, 0.012, 0.025),
        M["chrome"],
        0.004,
        semantic="coin_slot",
    )
    torus(
        ctx,
        "service:coiled_hose",
        (x, y - 0.455, 0.92),
        0.32,
        0.025,
        M["rubber"],
        (math.pi / 2, 0, 0),
        "air_service_hose",
        36,
        8,
    )
    tube(
        ctx,
        "service:air_hose_tail",
        [
            (x + 0.31, y - 0.45, 0.92),
            (x + 0.60, y - 0.47, 0.72),
            (x + 0.70, y - 0.48, 0.48),
        ],
        0.025,
        M["rubber"],
        "air_service_hose",
    )
    cylinder(
        ctx,
        "service:air_chuck",
        (x + 0.70, y - 0.49, 0.43),
        0.035,
        0.18,
        M["chrome"],
        16,
        rotation=(math.pi / 2, 0, 0),
        semantic="air_service_chuck",
        bevel=0.004,
    )
    for vent in range(7):
        instance_box(
            ctx,
            f"service:compressor_vent_{vent}",
            (x - 0.36 + vent * 0.12, y + 0.372, 0.77),
            (0.055, 0.018, 0.32),
            M["black"],
            "air_service_vent",
        )


def build_tank_vent_stack(ctx, M):
    x, y = 15.4, 5.0
    box(
        ctx,
        "service:vent_stack_pad",
        (x, y, 0.27),
        (1.8, 1.1, 0.18),
        M["concrete_light"],
        0.08,
        semantic="tank_vent_pad",
    )
    for i, offset in enumerate((-0.48, 0, 0.48)):
        cylinder(
            ctx,
            f"service:tank_vent_{i}",
            (x + offset, y, 2.15),
            0.055,
            3.65,
            M["galvanized"],
            18,
            semantic="underground_tank_vent",
            bevel=0.004,
        )
        tube(
            ctx,
            f"service:tank_vent_gooseneck_{i}",
            [
                (x + offset, y, 3.96),
                (x + offset, y - 0.18, 4.18),
                (x + offset, y - 0.42, 4.18),
            ],
            0.055,
            M["galvanized"],
            "underground_tank_vent",
        )
        cylinder(
            ctx,
            f"service:tank_vent_cap_{i}",
            (x + offset, y - 0.46, 4.18),
            0.085,
            0.16,
            M["steel"],
            18,
            rotation=(math.pi / 2, 0, 0),
            semantic="tank_vent_cap",
            bevel=0.008,
        )


def build_price_pylon(ctx, M):
    s = ctx.style
    primary, secondary, accent = style_materials(ctx, M)
    x = -13.1
    y = -12.0
    # Reinforced base and twin galvanized legs match freestanding roadside signs.
    box(
        ctx,
        "pylon:foundation",
        (x, y, 0.16),
        (3.10, 1.35, 0.32),
        M["concrete_light"],
        0.14,
        semantic="sign_foundation",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"pylon:leg_{side}",
            (x + side * 0.78, y, 2.48),
            (0.24, 0.32, 4.50),
            M["steel"],
            0.045,
            semantic="sign_support",
        )
        box(
            ctx,
            f"pylon:base_plate_{side}",
            (x + side * 0.78, y, 0.38),
            (0.58, 0.60, 0.10),
            M["steel"],
            0.035,
            semantic="sign_base_plate",
        )
        for bi in range(4):
            bx = x + side * 0.78 + (-0.18 if bi % 2 == 0 else 0.18)
            by = y + (-0.18 if bi < 2 else 0.18)
            instance_cylinder(
                ctx,
                f"pylon:anchor_{side}_{bi}",
                (bx, by, 0.455),
                0.025,
                0.07,
                M["black"],
                "fastener",
                vertices=10,
            )
    panel_z = 4.35 if s.variant != "nobile_wave" else 4.65
    panel_h = 5.55 if s.variant != "nobile_wave" else 6.20
    if s.variant == "nobile_wave":
        bottom = panel_z - panel_h / 2
        top = panel_z + panel_h / 2
        vertical_prism(
            ctx,
            "pylon:formed_main_case",
            [
                (x - 1.28, bottom + 0.18),
                (x - 1.28, top - 0.34),
                (x - 0.98, top),
                (x + 0.98, top),
                (x + 1.28, top - 0.34),
                (x + 1.28, bottom + 0.18),
                (x + 1.08, bottom),
                (x - 1.08, bottom),
            ],
            y,
            0.52,
            M["white"],
            "price_pylon",
        )
    else:
        box(
            ctx,
            "pylon:main_case",
            (x, y, panel_z),
            (2.55, 0.52, panel_h),
            M["galvanized"],
            0.15,
            semantic="price_pylon",
        )
    # Rolled perimeter trims and rear access cabinet create readable thickness.
    for side in (-1, 1):
        box(
            ctx,
            f"pylon:side_trim_{side}",
            (x + side * 1.255, y - 0.285, panel_z),
            (0.055, 0.055, panel_h - 0.34),
            M["aluminum"],
            0.016,
            semantic="pylon_case_trim",
        )
    box(
        ctx,
        "pylon:rear_access_case",
        (x, y + 0.35, panel_z - 0.72),
        (1.75, 0.28, 2.20),
        M["galvanized"],
        0.08,
        semantic="pylon_electrical_access",
    )
    box(
        ctx,
        "pylon:rear_access_handle",
        (x + 0.55, y + 0.505, panel_z - 0.72),
        (0.25, 0.035, 0.055),
        M["black"],
        0.018,
        semantic="pylon_access_handle",
    )
    box(
        ctx,
        "pylon:brand_header",
        (x, y - 0.285, panel_z + panel_h * 0.31),
        (2.28, 0.055, 1.55),
        primary,
        0.10,
        semantic="pylon_brand_panel",
    )
    if s.variant == "blue_orange":
        box(
            ctx,
            "pylon:orange_header_rule",
            (x, y - 0.326, panel_z + panel_h * 0.205),
            (2.12, 0.025, 0.16),
            secondary,
            0.018,
            semantic="pylon_brand_panel",
        )
    elif s.variant == "red_yellow":
        box(
            ctx,
            "pylon:yellow_header_rule",
            (x, y - 0.326, panel_z + panel_h * 0.205),
            (2.12, 0.025, 0.18),
            secondary,
            0.018,
            semantic="pylon_brand_panel",
        )
    build_brand_emblem(
        ctx, M, y - 0.345, panel_z + panel_h * 0.35, center_x=x - 0.68, scale=0.40
    )
    font = FONT_BOLD
    short = (
        "Nobile"
        if s.variant == "nobile_wave"
        else ("BLUEWAY" if s.variant == "blue_orange" else "NOVA")
    )
    text_front_fitted(
        ctx,
        "pylon:brand_text",
        short,
        (x + 0.40, y - 0.35, panel_z + panel_h * 0.33),
        1.30,
        0.70,
        M["white_emit"],
        0.030,
        font_path=font,
        semantic="pylon_brand_text",
        margin=0.035,
    )
    # Three inset dark price rows with separated grade label and raised digits.
    for i, (grade, price) in enumerate(
        (("Regular", "3.39"), ("Plus", "3.51"), ("Premium", "3.60"))
    ):
        zz = panel_z + 0.40 - i * 0.72
        box(
            ctx,
            f"pylon:price_row_{i}",
            (x, y - 0.295, zz),
            (2.18, 0.07, 0.60),
            M["black"],
            0.035,
            semantic="price_display_panel",
        )
        box(
            ctx,
            f"pylon:price_row_bezel_{i}",
            (x, y - 0.338, zz),
            (2.25, 0.026, 0.66),
            M["aluminum"],
            0.018,
            semantic="price_display_bezel",
        )
        box(
            ctx,
            f"pylon:price_row_face_{i}",
            (x, y - 0.357, zz),
            (2.09, 0.018, 0.52),
            M["black"],
            0.012,
            semantic="price_display_panel",
        )
        text_front_fitted(
            ctx,
            f"pylon:grade_{i}",
            grade,
            (x - 0.52, y - 0.382, zz),
            0.92,
            0.40,
            M["white_emit"],
            0.014,
            semantic="fuel_grade_text",
            margin=0.025,
        )
        text_front_fitted(
            ctx,
            f"pylon:price_{i}",
            price,
            (x + 0.52, y - 0.383, zz),
            0.88,
            0.43,
            secondary,
            0.020,
            semantic="fuel_price_text",
            margin=0.020,
        )
    box(
        ctx,
        "pylon:footer",
        (x, y - 0.30, panel_z - panel_h * 0.36),
        (2.25, 0.06, 0.58),
        secondary,
        0.04,
        semantic="pylon_footer",
    )
    text_front_fitted(
        ctx,
        "pylon:open_text",
        "OPEN 24 H",
        (x, y - 0.35, panel_z - panel_h * 0.36),
        1.92,
        0.34,
        M["black"],
        0.014,
        semantic="hours_sign",
        margin=0.025,
    )
    # Thin reflective aluminum wayfinding sign on two galvanized posts.
    box(
        ctx,
        "wayfinding:direction_base",
        (12.7, -12.5, 0.18),
        (1.42, 0.72, 0.24),
        M["concrete_light"],
        0.10,
        semantic="direction_sign_base",
    )
    for side in (-1, 1):
        cylinder(
            ctx,
            f"wayfinding:post_{side}",
            (12.7 + side * 0.37, -12.5, 0.78),
            0.035,
            1.18,
            M["galvanized"],
            16,
            semantic="direction_sign_post",
            bevel=0.004,
        )
        box(
            ctx,
            f"wayfinding:post_plate_{side}",
            (12.7 + side * 0.37, -12.5, 0.34),
            (0.20, 0.20, 0.055),
            M["steel"],
            0.025,
            semantic="direction_sign_base_plate",
        )
    box(
        ctx,
        "wayfinding:direction_body",
        (12.7, -12.5, 1.16),
        (1.20, 0.085, 0.72),
        primary,
        0.055,
        semantic="direction_sign",
    )
    box(
        ctx,
        "wayfinding:reflective_border",
        (12.7, -12.552, 1.16),
        (1.08, 0.018, 0.60),
        M["white_emit"],
        0.025,
        semantic="direction_sign_border",
    )
    box(
        ctx,
        "wayfinding:inner_panel",
        (12.7, -12.566, 1.16),
        (0.98, 0.012, 0.50),
        primary,
        0.020,
        semantic="direction_sign_face",
    )
    vertical_prism(
        ctx,
        "wayfinding:arrow",
        [
            (12.34, 1.18),
            (12.66, 1.43),
            (12.66, 1.28),
            (13.02, 1.28),
            (13.02, 1.08),
            (12.66, 1.08),
            (12.66, 0.91),
        ],
        -12.578,
        0.018,
        M["white_emit"],
        "direction_arrow",
    )


def build_pump_field(ctx, M):
    for i, x in enumerate(ctx.style.pump_x):
        build_fuel_dispenser(ctx, i, x, -2.7, M)
        if i % 2 == 0:
            build_squeegee_bin(ctx, f"service:island_bin_{i}", x + 1.55, -1.85, M)
    build_fire_cabinet(ctx, M)
    build_air_water_service(ctx, M)
    build_tank_vent_stack(ctx, M)


# ---------------------------------------------------------------------------
# Convenience store shell, transparent facade and physically stocked interior


def build_store_product(
    ctx, name, x, y, base_z, kind, color_mat, M, support_obj, index
):
    if kind == "bottle":
        height = 0.27 + (index % 3) * 0.035
        radius = 0.065 + (index % 2) * 0.008
        body = instance_cylinder(
            ctx,
            name + ":body",
            (x, y, base_z + height / 2),
            radius,
            height,
            color_mat,
            "store_product",
            vertices=16,
        )
        instance_cylinder(
            ctx,
            name + ":cap",
            (x, y, base_z + height + 0.035),
            radius * 0.72,
            0.07,
            M["white"],
            "store_product_detail",
            vertices=16,
        )
        instance_box(
            ctx,
            name + ":label",
            (x, y - 0.068, base_z + height * 0.50),
            (radius * 1.45, 0.012, height * 0.42),
            M["road_white"],
            "store_product_label",
        )
    elif kind == "can":
        height = 0.25 + (index % 2) * 0.03
        radius = 0.062
        body = instance_cylinder(
            ctx,
            name + ":body",
            (x, y, base_z + height / 2),
            radius,
            height,
            color_mat,
            "store_product",
            vertices=18,
        )
        instance_cylinder(
            ctx,
            name + ":top",
            (x, y, base_z + height + 0.006),
            radius * 0.94,
            0.012,
            M["steel"],
            "store_product_detail",
            vertices=18,
        )
        instance_box(
            ctx,
            name + ":label",
            (x, y - 0.064, base_z + height * 0.5),
            (radius * 1.55, 0.010, height * 0.58),
            M["road_white"],
            "store_product_label",
        )
    else:
        width = 0.13 + (index % 3) * 0.018
        height = 0.25 + (index % 4) * 0.025
        depth = 0.105
        body = instance_box(
            ctx,
            name + ":body",
            (x, y, base_z + height / 2),
            (width, depth, height),
            color_mat,
            "store_product",
        )
        instance_box(
            ctx,
            name + ":front_print",
            (x, y - depth / 2 - 0.007, base_z + height * 0.54),
            (width * 0.78, 0.012, height * 0.52),
            M["road_white"],
            "store_product_label",
        )
        instance_box(
            ctx,
            name + ":top_flap",
            (x, y, base_z + height + 0.008),
            (width * 0.88, depth * 0.86, 0.016),
            M["cardboard"],
            "store_product_detail",
        )
    body["c2w_support_relation"] = "rests_on_modeled_shelf"
    body["c2w_support_name"] = support_obj.name
    body["c2w_support_top_z"] = base_z
    body["c2w_product_kind"] = kind
    return body


def build_shelf_unit(ctx, name, cx, cy, M, seed):
    rng = random.Random(seed)
    width = 3.35
    depth = 0.72
    height = 2.18
    box(
        ctx,
        name + ":back",
        (cx, cy + 0.32, 1.40),
        (width, 0.10, height),
        M["white_warm"],
        0.018,
        semantic="shelf_back",
    )
    for sx in (-width / 2, width / 2):
        box(
            ctx,
            name + f":upright_{sx}",
            (cx + sx, cy, 1.39),
            (0.065, depth, 2.30),
            M["steel"],
            0.012,
            semantic="shelf_upright",
        )
        for row in range(10):
            instance_box(
                ctx,
                name + f":upright_slot_{sx}_{row}",
                (cx + sx, cy - 0.365, 0.42 + row * 0.19),
                (0.028, 0.018, 0.075),
                M["black"],
                "shelf_adjustment_slot",
            )
    for level in range(5):
        deck_z = 0.36 + level * 0.43
        deck = box(
            ctx,
            name + f":deck_{level}",
            (cx, cy, deck_z),
            (width, 0.72, 0.065),
            M["steel"],
            0.012,
            semantic="shelf_deck",
        )
        box(
            ctx,
            name + f":price_rail_{level}",
            (cx, cy - 0.385, deck_z + 0.055),
            (width, 0.055, 0.12),
            M["blue_light" if ctx.variant == "blue_orange" else "red"],
            0.012,
            semantic="shelf_price_rail",
        )
        for bracket in range(6):
            bx = cx - width / 2 + 0.25 + bracket * (width - 0.5) / 5
            instance_box(
                ctx,
                name + f":bracket_{level}_{bracket}",
                (bx, cy + 0.17, deck_z - 0.07),
                (0.045, 0.26, 0.10),
                M["black"],
                "shelf_bracket",
            )
        support_top = deck_z + 0.0325
        for pi in range(10):
            px = cx - width / 2 + 0.22 + pi * (width - 0.44) / 9
            kind = ("carton", "bottle", "carton", "can")[(pi + level + seed) % 4]
            mat = M[f"product_{(pi+level*3+seed)%8}"]
            build_store_product(
                ctx,
                f"{name}:product_{level}_{pi}",
                px,
                cy - 0.16,
                support_top,
                kind,
                mat,
                M,
                deck,
                pi + level,
            )
    box(
        ctx,
        name + ":top_sign",
        (cx, cy + 0.01, 2.64),
        (width + 0.08, 0.18, 0.40),
        M["white"],
        0.035,
        semantic="aisle_header",
    )
    text_front(
        ctx,
        name + ":category",
        "TRAVEL  •  FOOD",
        (cx, cy - 0.105, 2.65),
        0.16,
        M["blue" if ctx.variant == "blue_orange" else "red"],
        0.012,
        semantic="aisle_sign",
    )


def build_cooler_wall(ctx, M, front_y, width):
    y = front_y + ctx.style.store_depth - 0.55
    case_w = min(width - 3.0, 20.0)
    box(
        ctx,
        "store:cooler_case",
        (0, y, 2.14),
        (case_w, 0.82, 3.62),
        M["black"],
        0.06,
        semantic="refrigerated_case",
    )
    doors = 6
    door_w = (case_w - 0.6) / doors
    for i in range(doors):
        x = -case_w / 2 + 0.30 + door_w * (i + 0.5)
        box(
            ctx,
            f"store:cooler_door_{i}",
            (x, y - 0.435, 2.18),
            (door_w - 0.09, 0.055, 3.30),
            M["glass"],
            0.025,
            semantic="cooler_glazing",
        )
        for side in (-1, 1):
            instance_box(
                ctx,
                f"store:cooler_frame_{i}_{side}",
                (x + side * (door_w - 0.09) / 2, y - 0.47, 2.18),
                (0.045, 0.06, 3.33),
                M["aluminum"],
                "cooler_frame",
            )
        instance_box(
            ctx,
            f"store:cooler_handle_{i}",
            (x + door_w * 0.28, y - 0.505, 2.18),
            (0.035, 0.045, 1.10),
            M["steel"],
            "cooler_handle",
        )
        for level in range(4):
            shelf_z = 0.72 + level * 0.72
            instance_box(
                ctx,
                f"store:cooler_shelf_{i}_{level}",
                (x, y - 0.15, shelf_z),
                (door_w - 0.15, 0.46, 0.035),
                M["steel"],
                "cooler_shelf",
            )
            for pi in range(6):
                px = x - door_w * 0.36 + pi * door_w * 0.145
                color = M[f"product_{(i+level+pi)%8}"]
                instance_cylinder(
                    ctx,
                    f"store:cooler_product_{i}_{level}_{pi}",
                    (px, y - 0.37, shelf_z + 0.18),
                    0.047,
                    0.34,
                    color,
                    "store_product",
                    vertices=14,
                )
                instance_cylinder(
                    ctx,
                    f"store:cooler_cap_{i}_{level}_{pi}",
                    (px, y - 0.37, shelf_z + 0.37),
                    0.034,
                    0.045,
                    M["white"],
                    "store_product_detail",
                    vertices=12,
                )
        box(
            ctx,
            f"store:cooler_light_{i}",
            (x, y - 0.49, 3.68),
            (door_w - 0.18, 0.035, 0.055),
            M["white_emit"],
            0.008,
            semantic="interior_light_fixture",
        )


def build_checkout(ctx, M, width, front_y):
    x = width / 2 - 3.65
    y = front_y + 1.80
    primary, secondary, _ = style_materials(ctx, M)
    box(
        ctx,
        "store:checkout_plinth",
        (x, y, 0.72),
        (5.3, 1.0, 1.00),
        M["wood"],
        0.08,
        semantic="checkout_counter",
    )
    box(
        ctx,
        "store:checkout_front",
        (x, y - 0.53, 0.78),
        (5.10, 0.08, 0.84),
        primary,
        0.025,
        semantic="checkout_counter_front",
    )
    for i in range(9):
        instance_box(
            ctx,
            f"store:checkout_reveal_{i}",
            (x - 2.2 + i * 0.55, y - 0.58, 0.78),
            (0.022, 0.035, 0.72),
            secondary,
            "counter_joinery",
        )
    box(
        ctx,
        "store:checkout_top",
        (x, y, 1.27),
        (5.55, 1.18, 0.12),
        M["black"],
        0.055,
        semantic="countertop",
    )
    # Point-of-sale monitor, card terminal, scanner glass, receipt printer and till.
    box(
        ctx,
        "store:pos_monitor",
        (x + 0.70, y - 0.05, 1.78),
        (0.78, 0.18, 0.56),
        M["black"],
        0.055,
        rotation=(math.radians(-7), 0, 0),
        semantic="point_of_sale",
    )
    box(
        ctx,
        "store:pos_screen",
        (x + 0.70, y - 0.155, 1.80),
        (0.61, 0.025, 0.40),
        M["screen"],
        0.018,
        rotation=(math.radians(-7), 0, 0),
        semantic="digital_screen",
    )
    box(
        ctx,
        "store:barcode_scanner",
        (x - 0.05, y - 0.28, 1.37),
        (0.55, 0.35, 0.055),
        M["glass_dark"],
        0.018,
        semantic="barcode_scanner",
    )
    box(
        ctx,
        "store:receipt_printer",
        (x + 1.45, y - 0.05, 1.44),
        (0.42, 0.38, 0.29),
        M["white"],
        0.045,
        semantic="receipt_printer",
    )
    box(
        ctx,
        "store:receipt_slot",
        (x + 1.45, y - 0.26, 1.49),
        (0.22, 0.025, 0.035),
        M["black"],
        0.006,
        semantic="receipt_slot",
    )
    box(
        ctx,
        "store:card_terminal",
        (x - 1.02, y - 0.30, 1.48),
        (0.30, 0.36, 0.18),
        M["black"],
        0.035,
        rotation=(math.radians(-16), 0, 0),
        semantic="card_terminal",
    )
    for row in range(3):
        for col in range(3):
            instance_box(
                ctx,
                f"store:terminal_key_{row}_{col}",
                (x - 1.11 + col * 0.09, y - 0.50, 1.51 - row * 0.045),
                (0.045, 0.016, 0.026),
                M["steel"],
                "card_terminal_key",
            )
    box(
        ctx,
        "store:cash_drawer",
        (x + 0.55, y + 0.20, 0.99),
        (1.05, 0.56, 0.18),
        M["steel"],
        0.022,
        semantic="cash_drawer",
    )
    # Under-counter cabinet doors, recessed pulls and impulse-product trays.
    for i in range(5):
        cx = x - 2.0 + i * 1.0
        box(
            ctx,
            f"store:counter_door_{i}",
            (cx, y - 0.565, 0.73),
            (0.88, 0.035, 0.69),
            M["white_warm"],
            0.018,
            semantic="cabinet_front",
        )
        instance_box(
            ctx,
            f"store:counter_pull_{i}",
            (cx, y - 0.595, 0.91),
            (0.28, 0.025, 0.035),
            M["steel"],
            "cabinet_handle",
        )
    box(
        ctx,
        "store:impulse_rack",
        (x - 2.95, y - 0.36, 0.89),
        (0.52, 0.48, 1.20),
        M["steel"],
        0.025,
        semantic="impulse_rack",
    )
    for level in range(4):
        instance_box(
            ctx,
            f"store:impulse_shelf_{level}",
            (x - 2.95, y - 0.48, 0.45 + level * 0.28),
            (0.46, 0.27, 0.035),
            M["steel"],
            "shelf_deck",
        )
        for pi in range(3):
            instance_box(
                ctx,
                f"store:impulse_product_{level}_{pi}",
                (x - 3.10 + pi * 0.15, y - 0.62, 0.55 + level * 0.28),
                (0.11, 0.08, 0.18),
                M[f"product_{(level+pi)%8}"],
                "store_product",
            )


def build_store_interior(ctx, M, width, front_y, depth):
    # Porcelain floor and modeled grout joints continue behind the glazing.
    interior_cy = front_y + depth / 2
    box(
        ctx,
        "store:interior_floor",
        (0, interior_cy, 0.30),
        (width - 1.0, depth - 1.1, 0.20),
        M["tile"],
        0.025,
        semantic="interior_floor",
    )
    for i, x in enumerate(
        [-(width - 1) / 2 + i * 1.0 for i in range(int(width - 1) + 1)]
    ):
        instance_box(
            ctx,
            f"store:floor_grout_x_{i}",
            (x, interior_cy, 0.405),
            (0.018, depth - 1.25, 0.008),
            M["grout"],
            "modeled_floor_grout",
        )
    floor_rows = max(6, int((depth - 1.1) / 0.85))
    for i, y in enumerate(
        [
            front_y + 0.62 + i * (depth - 1.24) / (floor_rows - 1)
            for i in range(floor_rows)
        ]
    ):
        instance_box(
            ctx,
            f"store:floor_grout_y_{i}",
            (0, y, 0.406),
            (width - 1.0, 0.018, 0.008),
            M["grout"],
            "modeled_floor_grout",
        )
    # Six full commercial gondolas, stocked from a deterministic but varied mix.
    positions = []
    shelf_spacing = min(4.1, (width - 4.0) / 2.0)
    for row, y in enumerate((front_y + 3.15, front_y + 5.50)):
        for col, x in enumerate((-shelf_spacing, 0.0, shelf_spacing)):
            positions.append((x, y, row * 3 + col))
    for x, y, idx in positions:
        build_shelf_unit(
            ctx, f"store:shelf_{idx}", x, y, M, style_seed(ctx.variant) * 100 + idx
        )
    build_cooler_wall(ctx, M, front_y, width)
    build_checkout(ctx, M, width, front_y)
    # Ceiling grid, recessed luminous panels, and real local fill lights.
    box(
        ctx,
        "store:suspended_ceiling",
        (0, interior_cy, 3.92),
        (width - 1.0, depth - 1.05, 0.12),
        M["white"],
        0.018,
        semantic="interior_ceiling",
    )
    for ix, x in enumerate((-8, -4, 0, 4, 8)):
        if abs(x) > width / 2 - 2:
            continue
        for iy, y in enumerate(
            (front_y + 1.7, front_y + depth * 0.53, front_y + depth - 1.45)
        ):
            box(
                ctx,
                f"store:ceiling_recess_{ix}_{iy}",
                (x, y, 3.84),
                (1.45, 0.72, 0.06),
                M["black"],
                0.035,
                semantic="interior_light_recess",
            )
            box(
                ctx,
                f"store:ceiling_panel_{ix}_{iy}",
                (x, y, 3.79),
                (1.27, 0.58, 0.035),
                M["warm_light"],
                0.025,
                semantic="interior_light_fixture",
            )
            if ix in (-4, 4) and iy == 1:
                area_light(
                    ctx,
                    f"store:area_light_{ix}_{iy}",
                    (x, y, 3.73),
                    115,
                    (1.4, 0.7),
                    (0.98, 0.91, 0.74),
                )


def build_rooftop_plant(ctx, M, width, roof_y):
    # Screened HVAC equipment is visible in elevated views and fully connected.
    for unit, x in enumerate((-width * 0.22, width * 0.20)):
        box(
            ctx,
            f"roof:hvac_{unit}:curb",
            (x, roof_y, 5.03),
            (4.1, 2.45, 0.24),
            M["galvanized"],
            0.045,
            semantic="roof_equipment_curb",
        )
        box(
            ctx,
            f"roof:hvac_{unit}:case",
            (x, roof_y, 5.65),
            (3.72, 2.12, 1.06),
            M["galvanized"],
            0.09,
            semantic="roof_hvac_unit",
        )
        for side in (-1, 1):
            for slat in range(8):
                instance_box(
                    ctx,
                    f"roof:hvac_{unit}:louver_{side}_{slat}",
                    (x + side * 1.88, roof_y - 0.72 + slat * 0.20, 5.62),
                    (0.035, 0.12, 0.72),
                    M["black"],
                    "mechanical_louver",
                )
        for fan in (-0.72, 0.72):
            torus(
                ctx,
                f"roof:hvac_{unit}:fan_ring_{fan}",
                (x + fan, roof_y, 6.21),
                0.42,
                0.045,
                M["black"],
                semantic="condenser_fan_guard",
                major_segments=28,
                minor_segments=7,
            )
            for blade in range(5):
                a = blade * math.tau / 5
                instance_box(
                    ctx,
                    f"roof:hvac_{unit}:fan_blade_{fan}_{blade}",
                    (x + fan + 0.18 * math.cos(a), roof_y + 0.18 * math.sin(a), 6.22),
                    (0.34, 0.10, 0.025),
                    M["black"],
                    "condenser_fan_blade",
                    (0, 0, a),
                )
    # Electrical conduit and rainwater outlets.
    tube(
        ctx,
        "roof:service_conduit",
        [
            (-2.0, roof_y + 0.9, 5.0),
            (-2.0, roof_y + 1.7, 5.15),
            (2.0, roof_y + 1.7, 5.15),
            (2.0, roof_y + 0.9, 5.0),
        ],
        0.055,
        M["galvanized"],
        "roof_service_conduit",
    )


def build_commercial_entry(ctx, M, x, front, bay_w, primary):
    """Build a complete thermally-broken, glazed aluminum double entrance.

    The door is assembled as real storefront construction: a recessed
    structural subframe, profiled threshold, independent leaf rails and
    stiles, safety glazing, pressure gaskets, continuous hinges, concealed
    closers, mortise locks, sweeps and offset tubular pulls.  Hardware is
    integrated into the framing rather than represented by floating cuboids on
    an opaque slab.
    """
    opening_w = bay_w - 0.10
    door_bottom = 0.57
    door_top = 3.54
    door_h = door_top - door_bottom
    door_z = (door_bottom + door_top) / 2
    outer_y = front - 0.305

    # Deep perimeter receptor and a separate snap cap show the actual layered
    # storefront extrusion in both head-on and oblique inspection views.
    for side in (-1, 1):
        jamb_x = x + side * (opening_w / 2 - 0.055)
        box(
            ctx,
            f"store:entry_jamb_receptor_{side}",
            (jamb_x, front - 0.235, door_z),
            (0.115, 0.165, door_h + 0.12),
            M["door_frame"],
            0.012,
            semantic="door_frame_receptor",
        )
        box(
            ctx,
            f"store:entry_jamb_snap_cap_{side}",
            (jamb_x, front - 0.347, door_z),
            (0.072, 0.035, door_h + 0.04),
            M["aluminum"],
            0.009,
            semantic="door_frame_snap_cap",
        )
        box(
            ctx,
            f"store:entry_jamb_thermal_break_{side}",
            (jamb_x - side * 0.022, front - 0.365, door_z),
            (0.018, 0.016, door_h - 0.08),
            M["sealant"],
            0.004,
            semantic="door_thermal_break",
        )
    box(
        ctx,
        "store:entry_head_receptor",
        (x, front - 0.235, door_top + 0.055),
        (opening_w, 0.165, 0.145),
        M["door_frame"],
        0.014,
        semantic="door_frame_receptor",
    )
    box(
        ctx,
        "store:entry_head_snap_cap",
        (x, front - 0.347, door_top + 0.055),
        (opening_w - 0.08, 0.035, 0.075),
        M["aluminum"],
        0.009,
        semantic="door_frame_snap_cap",
    )
    box(
        ctx,
        "store:entry_head_stop",
        (x, front - 0.368, door_top - 0.035),
        (opening_w - 0.18, 0.018, 0.028),
        M["sealant"],
        0.004,
        semantic="door_weatherseal",
    )

    # The saddle is an extruded sloped profile, not a rectangular step.
    extruded_yz(
        ctx,
        "store:entry_threshold_profile",
        [
            (front - 0.49, 0.475),
            (front - 0.14, 0.475),
            (front - 0.10, 0.515),
            (front - 0.17, 0.555),
            (front - 0.43, 0.555),
        ],
        x,
        opening_w - 0.04,
        M["steel"],
        "door_threshold_profile",
    )
    box(
        ctx,
        "store:entry_threshold_thermal_break",
        (x, front - 0.275, 0.562),
        (opening_w - 0.20, 0.025, 0.018),
        M["sealant"],
        0.004,
        semantic="door_thermal_break",
    )

    clear_w = opening_w - 0.18
    meeting_gap = 0.030
    leaf_w = (clear_w - meeting_gap) / 2
    for leaf in (-1, 1):
        lx = x + leaf * (meeting_gap / 2 + leaf_w / 2)
        frame_y = front - 0.315
        stile_w = 0.088
        top_rail = 0.105
        bottom_rail = 0.185
        glass_bottom = door_bottom + bottom_rail
        glass_top = door_top - top_rail
        glass_h = glass_top - glass_bottom
        glass_z = (glass_bottom + glass_top) / 2
        glass_w = leaf_w - 2 * stile_w

        # One continuous safety-glass lite per leaf, recessed behind the four
        # structural rails.  No dot manifestation or decorative block is put
        # on either the door glazing or the adjacent windows.
        pane = box(
            ctx,
            f"store:entry_safety_glass_{leaf}",
            (lx, front - 0.278, glass_z),
            (glass_w, 0.028, glass_h),
            M["entry_glass"],
            0.006,
            semantic="door_safety_glazing",
        )
        pane["c2w_door_glazing_type"] = "tempered_laminated_safety_glass"
        pane["c2w_glazing_dot_markers"] = 0
        for side in (-1, 1):
            sx = lx + side * (leaf_w / 2 - stile_w / 2)
            box(
                ctx,
                f"store:entry_leaf_stile_{leaf}_{side}",
                (sx, frame_y, door_z),
                (stile_w, 0.090, door_h),
                M["door_frame"],
                0.010,
                semantic="door_leaf_frame",
            )
        box(
            ctx,
            f"store:entry_leaf_top_rail_{leaf}",
            (lx, frame_y, door_top - top_rail / 2),
            (leaf_w, 0.090, top_rail),
            M["door_frame"],
            0.010,
            semantic="door_leaf_frame",
        )
        box(
            ctx,
            f"store:entry_leaf_bottom_rail_{leaf}",
            (lx, frame_y, door_bottom + bottom_rail / 2),
            (leaf_w, 0.090, bottom_rail),
            M["door_frame"],
            0.012,
            semantic="door_leaf_frame",
        )
        front_panel_frame(
            ctx,
            f"store:entry_glazing_gasket_{leaf}",
            (lx, front - 0.331, glass_z),
            glass_w + 0.030,
            glass_h + 0.030,
            0.014,
            0.016,
            M["sealant"],
            "door_glazing_gasket",
        )
        front_panel_frame(
            ctx,
            f"store:entry_leaf_thermal_break_{leaf}",
            (lx, front - 0.354, door_z),
            leaf_w - 0.018,
            door_h - 0.018,
            0.014,
            0.014,
            M["sealant"],
            "door_thermal_break",
        )

        # Full-height geared hinge, mortise lock and brush sweep are recessed
        # into the stiles/rail and read as connected manufactured hardware.
        hinge_x = lx + leaf * (leaf_w / 2 - 0.018)
        cylinder(
            ctx,
            f"store:entry_continuous_hinge_{leaf}",
            (hinge_x, front - 0.365, door_z),
            0.015,
            door_h - 0.22,
            M["steel"],
            18,
            semantic="door_continuous_hinge",
            bevel=0.003,
        )
        lock_x = lx - leaf * (leaf_w / 2 - stile_w / 2)
        cylinder(
            ctx,
            f"store:entry_mortise_lock_{leaf}",
            (lock_x, front - 0.370, 1.22),
            0.018,
            0.018,
            M["black"],
            18,
            rotation=(math.pi / 2, 0, 0),
            semantic="door_lock_cylinder",
            bevel=0.003,
        )
        box(
            ctx,
            f"store:entry_bottom_sweep_{leaf}",
            (lx, front - 0.362, door_bottom + 0.012),
            (leaf_w - 0.10, 0.030, 0.026),
            M["door_sweep"],
            0.006,
            semantic="door_bottom_sweep",
        )

        # Offset tubular pull: the short returns land on the meeting stile, so
        # no isolated white fasteners remain scattered across the glass.
        handle_x = lx - leaf * (leaf_w / 2 - 0.13)
        handle_points = [
            (handle_x, front - 0.365, 1.34),
            (handle_x, front - 0.455, 1.43),
            (handle_x, front - 0.455, 2.39),
            (handle_x, front - 0.365, 2.48),
        ]
        tube(
            ctx,
            f"store:entry_pull_handle_{leaf}",
            handle_points,
            0.020,
            M["steel"],
            "door_pull_handle",
        )
        for mount_z in (1.34, 2.48):
            beam(
                ctx,
                f"store:entry_pull_mount_{leaf}_{mount_z}",
                (handle_x, front - 0.342, mount_z),
                (handle_x, front - 0.405, mount_z),
                0.022,
                M["steel"],
                "door_handle_mount",
                16,
            )

        # A flush cover at the head identifies the concealed closer without
        # the oversized exposed box-and-arm assembly from the previous pass.
        closer_x = lx + leaf * leaf_w * 0.16
        rounded_vertical_prism(
            ctx,
            f"store:concealed_closer_cover_{leaf}",
            closer_x,
            door_top + 0.050,
            0.34,
            0.048,
            0.020,
            front - 0.370,
            0.018,
            M["aluminum"],
            "door_concealed_closer",
            6,
        )

    # Interlocking astragal and compressible meeting seal close the double
    # leaf pair while retaining a realistic narrow center joint.
    box(
        ctx,
        "store:entry_astragal",
        (x - meeting_gap * 0.18, front - 0.337, door_z),
        (0.032, 0.055, door_h - 0.13),
        M["door_frame"],
        0.008,
        semantic="door_astragal",
    )
    box(
        ctx,
        "store:entry_meeting_seal",
        (x + meeting_gap * 0.34, front - 0.368, door_z),
        (0.014, 0.018, door_h - 0.20),
        M["sealant"],
        0.004,
        semantic="door_weatherseal",
    )
    box(
        ctx,
        "store:entry_mat",
        (x, front + 0.38, 0.45),
        (opening_w * 0.94, 1.22, 0.035),
        M["rubber"],
        0.025,
        semantic="entrance_mat",
    )


def build_store(ctx, M):
    # The store has its own local root because the third reference places the
    # compact shop on the right of the canopy while the first two use broad,
    # nearly centered market buildings.  The offset remains part of the
    # reusable station asset and follows pipeline yaw/placement correctly.
    store_anchor = bpy.data.objects.new(PREFIX + ctx.variant + ":store_root", None)
    ctx.collection.objects.link(store_anchor)
    store_anchor.parent = ctx.anchor
    store_anchor.location = (ctx.style.store_offset_x, 0, 0)
    tag(store_anchor, "store_root", ctx, True)
    store_anchor["c2w_store_layout"] = "reference_specific_independent_shell"
    ctx = BuildContext(ctx.collection, store_anchor, ctx.style)
    width = ctx.style.store_width
    depth = ctx.style.store_depth
    front = 5.36
    cy = front + depth / 2
    rear = front + depth
    primary, secondary, accent = style_materials(ctx, M)
    # Full shell with deep returns; the front wall is a real post-and-beam frame.
    box(
        ctx,
        "store:foundation",
        (0, cy, 0.02),
        (width + 1.0, depth + 1.0, 0.55),
        M["concrete"],
        0.055,
        semantic="store_foundation",
    )
    box(
        ctx,
        "store:rear_wall",
        (0, rear, 2.47),
        (width, 0.38, 4.32),
        M["white_warm"],
        0.035,
        semantic="store_wall",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"store:side_wall_{side}",
            (side * width / 2, cy, 2.47),
            (0.38, depth, 4.32),
            M["white_warm"],
            0.035,
            semantic="store_wall",
        )
        for joint in range(8):
            yy = front + 0.55 + joint * (depth - 1.1) / 7
            instance_box(
                ctx,
                f"store:side_panel_joint_{side}_{joint}",
                (side * (width / 2 + 0.195), yy, 2.50),
                (0.018, 0.025, 3.90),
                M["grout"],
                "facade_panel_joint",
            )
    box(
        ctx,
        "store:front_head",
        (0, front, 4.05),
        (width, 0.46, 0.80),
        M["white"],
        0.04,
        semantic="storefront_head",
    )
    box(
        ctx,
        "store:front_sill",
        (0, front, 0.47),
        (width, 0.42, 0.25),
        M["concrete_light"],
        0.025,
        semantic="storefront_sill",
    )
    # A dark recessed reveal below the head gives the curtain wall real depth.
    box(
        ctx,
        "store:front_shadow_reveal",
        (0, front - 0.245, 3.58),
        (width - 0.30, 0.055, 0.11),
        M["black"],
        0.012,
        semantic="storefront_shadow_reveal",
    )
    box(
        ctx,
        "store:head_drip_flashing",
        (0, front - 0.315, 3.60),
        (width - 0.18, 0.18, 0.045),
        M["aluminum"],
        0.010,
        semantic="storefront_drip_flashing",
    )
    # Rainscreen panel joints and exposed folded corner closures keep the long
    # facade head from reading as one oversized cube.
    head_joint_count = max(8, int(width / 1.35))
    for joint in range(1, head_joint_count):
        jx = -width / 2 + joint * width / head_joint_count
        instance_box(
            ctx,
            f"store:front_head_joint_{joint}",
            (jx, front - 0.238, 4.07),
            (0.018, 0.020, 0.63),
            M["sealant"],
            "facade_panel_joint",
        )
        for zz in (3.82, 4.31):
            cylinder(
                ctx,
                f"store:front_head_fastener_{joint}_{zz}",
                (jx, front - 0.252, zz),
                0.010,
                0.009,
                M["steel"],
                10,
                rotation=(math.pi / 2, 0, 0),
                semantic="facade_fastener",
                bevel=0.001,
            )
    for side in (-1, 1):
        box(
            ctx,
            f"store:front_corner_closure_{side}",
            (side * (width / 2 - 0.08), front - 0.285, 2.51),
            (0.16, 0.16, 3.96),
            M["aluminum"],
            0.018,
            semantic="storefront_corner_flashing",
        )
    # Eight framed facade bays; bay 5 is a complete commercial aluminum-and-
    # glass double entrance.  Adjacent curtain-wall panes use pressure plates,
    # thermal gaskets and sloped sill flashings with no dot manifestation.
    clear_w = width - 2.0
    bays = 8
    bay_w = clear_w / bays
    for i in range(bays):
        x = -clear_w / 2 + bay_w * (i + 0.5)
        if i == 5:
            build_commercial_entry(ctx, M, x, front, bay_w, primary)
        else:
            pane = box(
                ctx,
                f"store:glazing_{i}",
                (x, front - 0.245, 2.12),
                (bay_w - 0.12, 0.032, 2.95),
                M["glass"],
                0.008,
                semantic="storefront_glazing",
            )
            pane[
                "c2w_glazing_system"
            ] = "thermally_broken_pressure_equalized_curtain_wall"
            pane["c2w_glazing_dot_markers"] = 0
            front_panel_frame(
                ctx,
                f"store:window_gasket_{i}",
                (x, front - 0.292, 2.12),
                bay_w - 0.12,
                2.95,
                0.016,
                0.016,
                M["sealant"],
                "storefront_glazing_gasket",
            )
            front_panel_frame(
                ctx,
                f"store:window_pressure_plate_{i}",
                (x, front - 0.320, 2.12),
                bay_w - 0.085,
                2.985,
                0.034,
                0.022,
                M["door_frame"],
                "storefront_pressure_plate",
            )
            # A folded, sloped subsill drains outward; unlike the old box
            # ledge it has a readable drip nose and back upstand.
            extruded_yz(
                ctx,
                f"store:window_sill_flashing_{i}",
                [
                    (front - 0.405, 0.585),
                    (front - 0.145, 0.585),
                    (front - 0.135, 0.625),
                    (front - 0.180, 0.660),
                    (front - 0.360, 0.630),
                ],
                x,
                bay_w - 0.13,
                M["aluminum"],
                "storefront_sill_flashing",
            )
            box(
                ctx,
                f"store:window_subsill_gasket_{i}",
                (x, front - 0.338, 0.648),
                (bay_w - 0.22, 0.018, 0.018),
                M["sealant"],
                0.003,
                semantic="storefront_glazing_gasket",
            )
            instance_box(
                ctx,
                f"store:transom_{i}",
                (x, front - 0.337, 3.05),
                (bay_w - 0.13, 0.040, 0.060),
                M["door_frame"],
                "storefront_transom",
            )
            instance_box(
                ctx,
                f"store:transom_gasket_{i}",
                (x, front - 0.362, 3.05),
                (bay_w - 0.20, 0.014, 0.020),
                M["sealant"],
                "storefront_glazing_gasket",
            )
        if i in (1, 3, 7):
            # Framed promotional panels are mounted behind the glazing; their
            # small typography-like bars avoid the flat colored rectangles of
            # the former interior backdrop.
            box(
                ctx,
                f"store:poster_frame_{i}",
                (x, front + 0.02, 2.20),
                (bay_w * 0.57, 0.045, 1.10),
                M["black"],
                0.025,
                semantic="storefront_poster_frame",
            )
            box(
                ctx,
                f"store:poster_face_{i}",
                (x, front - 0.008, 2.20),
                (bay_w * 0.50, 0.018, 1.00),
                M[f"product_{i%8}"],
                0.012,
                semantic="storefront_poster",
            )
            for line in range(5):
                instance_box(
                    ctx,
                    f"store:poster_copy_{i}_{line}",
                    (x, front - 0.022, 2.48 - line * 0.14),
                    (bay_w * (0.34 - 0.025 * (line % 2)), 0.010, 0.025),
                    M["white_emit"],
                    "storefront_poster_copy",
                )
    # One mullion per bay boundary avoids coincident duplicate geometry and
    # exposes the cap/gasket/receptor build-up of a real curtain wall.
    for boundary in range(bays + 1):
        mx = -clear_w / 2 + boundary * bay_w
        box(
            ctx,
            f"store:mullion_receptor_{boundary}",
            (mx, front - 0.258, 2.12),
            (0.092, 0.105, 3.10),
            M["door_frame"],
            0.010,
            semantic="storefront_mullion_receptor",
        )
        box(
            ctx,
            f"store:mullion_snap_cap_{boundary}",
            (mx, front - 0.342, 2.12),
            (0.050, 0.028, 3.02),
            M["aluminum"],
            0.007,
            semantic="storefront_mullion_cap",
        )
        for side in (-1, 1):
            instance_box(
                ctx,
                f"store:mullion_gasket_{boundary}_{side}",
                (mx + side * 0.035, front - 0.365, 2.12),
                (0.012, 0.014, 2.94),
                M["sealant"],
                "storefront_glazing_gasket",
            )
    # Reference-specific layered store cornice.
    if ctx.variant == "blue_orange":
        band_specs = (
            (4.33, 0.30, primary),
            (4.55, 0.16, secondary),
            (4.72, 0.12, M["white"]),
        )
    else:
        band_specs = (
            (4.29, 0.24, primary),
            (4.49, 0.17, secondary),
            (4.65, 0.13, primary),
            (4.79, 0.10, M["white"]),
        )
    for bi, (z, h, mat) in enumerate(band_specs):
        box(
            ctx,
            f"store:brand_band_{bi}",
            (0, front - 0.26, z),
            (width + 0.45, 0.16, h),
            mat,
            0.018,
            semantic="store_brand_fascia",
        )
    # High-contrast non-glowing channel letters remain crisp in daylight and
    # do not disappear into the red/orange fascia behind them.
    sign_mat = M["black"] if ctx.variant == "nobile_wave" else M["white"]
    font = FONT_BOLD
    primary_sign_width = (
        9.8
        if ctx.variant == "nobile_wave"
        else (10.4 if ctx.variant == "blue_orange" else 6.8)
    )
    primary_sign_height = (
        0.66
        if ctx.variant == "nobile_wave"
        else (0.70 if ctx.variant == "blue_orange" else 0.64)
    )
    text_front_fitted(
        ctx,
        "store:primary_sign",
        ctx.style.shop_name,
        (0, front - 0.37, 4.47),
        primary_sign_width,
        primary_sign_height,
        sign_mat,
        0.045,
        font_path=font,
        semantic="store_sign",
        margin=0.045,
    )
    text_front_fitted(
        ctx,
        "store:hours_sign",
        "OPEN 24 HOURS",
        (-width * 0.32, front - 0.32, 3.39),
        2.75,
        0.28,
        M["white_emit"],
        0.015,
        semantic="hours_sign",
        margin=0.025,
    )
    # Each facade includes the construction seen in its matching reference,
    # not merely a recolored common shop box.
    if ctx.variant == "nobile_wave":
        cafe_x = -width * 0.30
        box(
            ctx,
            "store:cafe_awning",
            (cafe_x, front - 0.78, 3.26),
            (5.4, 1.18, 0.16),
            M["red"],
            0.06,
            semantic="cafe_awning",
        )
        for side in (-1, 1):
            beam(
                ctx,
                f"store:cafe_awning_tie_{side}",
                (cafe_x + side * 2.30, front - 0.30, 3.18),
                (cafe_x + side * 2.30, front - 1.20, 3.42),
                0.030,
                M["steel"],
                "awning_tie",
                12,
            )
        text_front_fitted(
            ctx,
            "store:cafe_wordmark",
            "CAFÉ",
            (cafe_x, front - 0.88, 3.28),
            3.6,
            0.42,
            M["white_emit"],
            0.030,
            semantic="cafe_sign",
            margin=0.055,
        )
        for side in (-1, 1):
            box(
                ctx,
                f"store:nobile_stone_pier_{side}",
                (side * (width / 2 - 0.55), front - 0.28, 2.18),
                (0.72, 0.58, 3.38),
                M["concrete_light"],
                0.055,
                semantic="store_facade_pier",
            )
    elif ctx.variant == "blue_orange":
        # Blue vertical portal and an English secondary identity band retain
        # the broad energy-station composition without any CJK scene text.
        for side in (-1, 1):
            box(
                ctx,
                f"store:blue_portal_pier_{side}",
                (side * (width / 2 - 0.42), front - 0.34, 2.42),
                (0.62, 0.52, 4.05),
                M["blue"],
                0.045,
                semantic="store_facade_pier",
            )
        box(
            ctx,
            "store:orange_entry_canopy",
            (width * 0.21, front - 0.66, 3.64),
            (4.4, 0.92, 0.16),
            M["orange"],
            0.045,
            semantic="store_entry_canopy",
        )
        text_front_fitted(
            ctx,
            "store:secondary_market_sign",
            "FUEL  •  MARKET  •  COFFEE",
            (-width * 0.245, front - 0.39, 4.08),
            6.4,
            0.38,
            M["white_emit"],
            0.025,
            font_path=FONT_BOLD,
            semantic="store_sign",
            margin=0.040,
        )
    else:
        # The compact third shop has a pronounced red/yellow portal and a
        # lightweight glazed gable visible behind the flat canopy.
        portal_x = width * 0.22
        box(
            ctx,
            "store:red_entry_canopy",
            (portal_x, front - 0.78, 3.62),
            (4.15, 1.12, 0.18),
            M["red"],
            0.055,
            semantic="store_entry_canopy",
        )
        box(
            ctx,
            "store:yellow_entry_reveal",
            (portal_x, front - 1.36, 3.53),
            (3.72, 0.10, 0.09),
            M["yellow"],
            0.018,
            semantic="store_entry_canopy_trim",
        )
        beam(
            ctx,
            "store:gabled_portal_left",
            (portal_x - 2.05, front - 0.18, 4.22),
            (portal_x, front - 0.18, 5.12),
            0.055,
            M["steel"],
            "store_glazed_portal_frame",
            14,
        )
        beam(
            ctx,
            "store:gabled_portal_right",
            (portal_x, front - 0.18, 5.12),
            (portal_x + 2.05, front - 0.18, 4.22),
            0.055,
            M["steel"],
            "store_glazed_portal_frame",
            14,
        )
        for mullion in range(5):
            mx = portal_x - 1.64 + mullion * 0.82
            top = 5.12 - abs(mx - portal_x) * 0.44
            beam(
                ctx,
                f"store:gabled_portal_mullion_{mullion}",
                (mx, front - 0.16, 4.22),
                (mx, front - 0.16, top),
                0.026,
                M["aluminum"],
                "store_glazed_portal_frame",
                12,
            )
        for side in (-1, 1):
            box(
                ctx,
                f"store:red_panel_bay_{side}",
                (side * (width / 2 - 0.48), cy, 2.46),
                (0.70, depth - 0.65, 4.18),
                M["white"],
                0.045,
                semantic="store_vertical_cladding",
            )
            for seam in range(9):
                yy = front + 0.45 + seam * (depth - 1.0) / 8
                instance_box(
                    ctx,
                    f"store:red_panel_seam_{side}_{seam}",
                    (side * (width / 2 - 0.845), yy, 2.48),
                    (0.018, 0.028, 3.82),
                    M["joint"],
                    "facade_panel_joint",
                )
    # Parapet cap, coping joints, gutters and downpipes.
    box(
        ctx,
        "store:roof_slab",
        (0, cy, 4.69),
        (width + 0.35, depth + 0.35, 0.32),
        M["concrete_light"],
        0.045,
        semantic="store_roof",
    )
    box(
        ctx,
        "store:parapet_cap",
        (0, front + 0.02, 4.92),
        (width + 0.60, 0.58, 0.17),
        M["galvanized"],
        0.025,
        semantic="parapet_coping",
    )
    for i in range(12):
        x = -width / 2 + (i + 0.5) * width / 12
        instance_box(
            ctx,
            f"store:coping_joint_{i}",
            (x, front - 0.275, 4.93),
            (0.022, 0.04, 0.14),
            M["black"],
            "coping_joint",
        )
    for side in (-1, 1):
        cylinder(
            ctx,
            f"store:downpipe_{side}",
            (side * (width / 2 - 0.45), rear - 0.28, 2.54),
            0.052,
            4.45,
            M["galvanized"],
            16,
            semantic="rainwater_downpipe",
            bevel=0.004,
        )
        for zi in (1.0, 2.2, 3.4):
            instance_box(
                ctx,
                f"store:downpipe_clip_{side}_{zi}",
                (side * (width / 2 - 0.45), rear - 0.49, zi),
                (0.22, 0.14, 0.035),
                M["steel"],
                "pipe_bracket",
            )
    build_store_interior(ctx, M, width, front, depth)
    build_rooftop_plant(ctx, M, width, cy + 0.6)


# ---------------------------------------------------------------------------
# Reusable pipeline entrypoints and validation presentation context


def build_gas_station_asset(
    variant,
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    include_site=True,
    materials=None,
):
    """Build one independently placeable reference archetype from source."""
    if variant not in STYLES:
        raise ValueError(
            f"Unknown gas station variant {variant!r}; expected one of {sorted(STYLES)}"
        )
    M = materials or make_materials()
    style = STYLES[variant]
    host = parent or bpy.context.scene.collection
    ctx = new_station_context(style, host, origin, yaw)
    if include_site:
        build_forecourt(ctx, M)
    build_canopy(ctx, M)
    build_pump_field(ctx, M)
    build_price_pylon(ctx, M)
    build_store(ctx, M)
    ctx.collection["c2w_reference_index"] = style.reference_index
    ctx.collection["c2w_reference_url"] = REFERENCE_URLS[style.reference_index - 1]
    ctx.collection["c2w_archetype"] = style.canopy_kind
    ctx.collection["c2w_brand"] = style.brand
    ctx.collection["c2w_dispenser_count"] = len(style.pump_x)
    ctx.collection["c2w_layout_front_direction"] = "local_negative_y"
    ctx.collection["c2w_modeling_quality"] = "production_high_detail"
    ctx.collection["c2w_model_revision"] = MODEL_REVISION
    ctx.collection["c2w_external_blend_inputs"] = 0
    return ctx.collection


def build_gas_station_reference_row(parent=None, include_site=True):
    """Live Urban-v3 entrypoint: three distinct stations in one east-west row."""
    RNG.seed(20260831)
    SHARED_MESHES.clear()
    M = make_materials()
    host = parent or bpy.context.scene.collection
    root = collection("THREE_REFERENCE_GAS_STATION_ROW", host, "procedural_asset_group")
    root["c2w_asset_id"] = ASSET_ID
    root[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_gass.build_gas_station_reference_row"
    root["c2w_pipeline_adapter"] = "urban_assets.build_gas_station_reference_row"
    root[
        "c2w_single_asset_entrypoint"
    ] = "generate_urban_v3_gass.build_gas_station_asset"
    root["c2w_single_asset_adapter"] = "urban_assets.build_gas_station_asset"
    root["c2w_reference_urls"] = json.dumps(REFERENCE_URLS, ensure_ascii=False)
    root["c2w_reference_driven"] = True
    root["c2w_model_revision"] = MODEL_REVISION
    root["c2w_scene_asset_inputs"] = 0
    root[
        "c2w_layout_summary"
    ] = "three distinct gas stations aligned east-west in one row, all facing south"
    root[
        "c2w_quality_profile"
    ] = "reference_specific_architecture+integrated_radiused_four_hose_dispensers+detailed_glazed_commercial_entries+english_only_signage+physical_services+photographic_daylight"
    for style in STYLES.values():
        build_gas_station_asset(style.variant, root, style.origin, 0.0, include_site, M)
    return root, M


PRESENTATION_STYLE = StationStyle(
    "presentation_context",
    0,
    (0, 0, 0),
    "",
    "",
    "context",
    1,
    1,
    (),
    (0.2, 0.2, 0.2),
    (0.2, 0.2, 0.2),
    (0.2, 0.2, 0.2),
    1,
    0,
    1,
)


def build_mountain_backdrop(ctx, M):
    """Two smooth 2-D height fields provide real sloping terrain at horizon."""
    for layer, (y0, y1, amp, mat_key, phase) in enumerate(
        (
            (52.0, 94.0, 7.2, "mountain_far", 1.7),
            (31.0, 70.0, 10.0, "mountain_near", 0.2),
        )
    ):
        nx = 96
        ny = 18
        verts = []
        for iy in range(ny + 1):
            t = iy / ny
            ridge = max(0.0, math.sin(math.pi * t)) ** 0.72
            y = y0 + (y1 - y0) * t
            for ix in range(nx + 1):
                x = -78 + 156 * ix / nx
                broad = (
                    0.53
                    + 0.19 * math.sin(ix * 0.19 + phase)
                    + 0.105 * math.sin(ix * 0.43 + phase * 1.8)
                    + 0.050 * math.sin(ix * 0.91 + iy * 0.21 + phase)
                )
                erosion = 0.16 * math.sin(
                    ix * 0.27 - iy * 0.36 + phase
                ) + 0.07 * math.sin(ix * 0.77 + iy * 0.49)
                z = -0.34 + amp * ridge * max(
                    0.18, broad + erosion * (0.22 + 0.78 * ridge)
                )
                verts.append((x, y, z))
        faces = []
        stride = nx + 1
        for iy in range(ny):
            for ix in range(nx):
                a = iy * stride + ix
                b = a + stride
                faces.append((a, a + 1, b + 1, b))
        mesh = bpy.data.meshes.new(PREFIX + f"presentation:mountain_layer_{layer}:mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.materials.append(M[mat_key])
        for poly in mesh.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new(
            PREFIX + f"presentation:mountain_layer_{layer}", mesh
        )
        ctx.collection.objects.link(obj)
        obj.parent = ctx.anchor
        tag(obj, "distant_terrain", ctx, True)


def build_presentation_context(parent, M):
    coll = collection("DAYLIGHT_PRESENTATION_CONTEXT", parent, "presentation_context")
    anchor = bpy.data.objects.new(PREFIX + "presentation:root", None)
    coll.objects.link(anchor)
    ctx = BuildContext(coll, anchor, PRESENTATION_STYLE)
    tag(anchor, "presentation_root", ctx)
    anchor["c2w_role"] = "presentation_root"
    # A deep continuous terrain datum keeps every downward-looking camera from
    # exposing the empty world beyond the modeled road section.
    box(
        ctx,
        "presentation:world_ground",
        (0, -45.0, -0.72),
        (142, 220, 0.34),
        M["grass"],
        0.04,
        semantic="terrain_datum",
    )
    # The road is deliberately sparse of unrelated props, but is built to real
    # construction depth with gutter, lane markings and aggregate variation.
    box(
        ctx,
        "presentation:road_subbase",
        (0, -21.5, -0.35),
        (119, 13.0, 0.75),
        M["concrete"],
        0.025,
        semantic="road_subbase",
    )
    box(
        ctx,
        "presentation:asphalt_carriageway",
        (0, -21.5, 0.05),
        (119, 12.4, 0.28),
        M["asphalt"],
        0.035,
        semantic="public_road",
    )
    box(
        ctx,
        "presentation:gutter",
        (0, -15.35, 0.21),
        (119, 0.48, 0.20),
        M["concrete_light"],
        0.055,
        semantic="road_gutter",
    )
    for i, x in enumerate(range(-56, 57, 4)):
        instance_box(
            ctx,
            f"presentation:center_dash_{i}",
            (x, -22.1, 0.205),
            (2.25, 0.12, 0.018),
            M["road_yellow"],
            "lane_marking",
        )
    for y, label in ((-17.1, "north_edge"), (-26.0, "south_edge")):
        instance_box(
            ctx,
            f"presentation:{label}",
            (0, y, 0.205),
            (117, 0.11, 0.018),
            M["road_white"],
            "lane_marking",
        )
    # The pedestrian path crosses the carriageway along Y, so each painted
    # bar runs along X.  The previous pass accidentally used long Y bars (a
    # 90-degree error clearly visible in the front view).
    for i, y in enumerate((-23.30, -22.40, -21.50, -20.60, -19.70, -18.80, -17.90)):
        stripe = instance_box(
            ctx,
            f"presentation:zebra_stripe_{i}",
            (0, y, 0.214),
            (5.35, 0.46, 0.018),
            M["road_white"],
            "pedestrian_crossing",
        )
        stripe["c2w_crosswalk_bar_axis"] = "X"
        stripe["c2w_rotation_correction_degrees"] = 90
    for i, x in enumerate((-7.8, -4.8, 4.8, 7.8)):
        instance_box(
            ctx,
            f"presentation:road_patch_{i}",
            (x, -23.5 + (i % 2) * 3.2, 0.214),
            (3.8, 0.85, 0.014),
            M["oil"],
            "asphalt_repair_patch",
            rotation=(0, 0, math.radians((i - 1.5) * 0.45)),
        )
    tube(
        ctx,
        "presentation:asphalt_crack_0",
        [
            (-45, -18.2, 0.222),
            (-41, -19.0, 0.224),
            (-37, -18.6, 0.223),
            (-33, -20.1, 0.224),
        ],
        0.018,
        M["joint"],
        "asphalt_crack",
    )
    tube(
        ctx,
        "presentation:asphalt_crack_1",
        [
            (29, -24.8, 0.222),
            (33, -23.9, 0.224),
            (37, -24.4, 0.223),
            (41, -22.8, 0.224),
        ],
        0.015,
        M["joint"],
        "asphalt_crack",
    )
    for i, x in enumerate((-49, -38, -27, -11, 0, 11, 27, 38, 49)):
        instance_box(
            ctx,
            f"presentation:gutter_inlet_frame_{i}",
            (x, -15.30, 0.32),
            (2.2, 0.34, 0.07),
            M["black"],
            "stormwater_inlet",
        )
        for slot in range(10):
            instance_box(
                ctx,
                f"presentation:gutter_inlet_{i}_{slot}",
                (x - 0.96 + slot * 0.215, -15.31, 0.365),
                (0.055, 0.25, 0.025),
                M["galvanized"],
                "stormwater_grate",
            )
    # Broad terrain behind and beside the assets prevents black horizon gaps.
    box(
        ctx,
        "presentation:rear_terrain",
        (0, 37, -0.23),
        (122, 45, 0.62),
        M["grass"],
        0.05,
        semantic="terrain",
    )
    box(
        ctx,
        "presentation:far_sidewalk",
        (0, -28.2, 0.12),
        (120, 1.9, 0.24),
        M["concrete"],
        0.035,
        semantic="sidewalk",
    )
    # Concrete plot separators make the three independently generated sites
    # legible as a row without hiding their own edge kerbs.
    for i, x in enumerate((-19, 19)):
        box(
            ctx,
            f"presentation:plot_separator_{i}",
            (x, 0.8, 0.26),
            (2.1, 31.0, 0.18),
            M["concrete_light"],
            0.06,
            semantic="plot_separator",
        )
    build_mountain_backdrop(ctx, M)
    return coll


def archive_references():
    REFERENCES.mkdir(parents=True, exist_ok=True)
    records = []
    for src, name, url in zip(REFERENCE_CACHE, REFERENCE_FILES, REFERENCE_URLS):
        if not src.is_file() or src.stat().st_size < 10000:
            raise FileNotFoundError(
                f"Missing downloaded reference inside workspace: {src}"
            )
        dst = REFERENCES / name
        shutil.copy2(src, dst)
        records.append(
            {
                "file": name,
                "bytes": dst.stat().st_size,
                "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                "url": url,
            }
        )
    return records


def setup_daylight():
    world = bpy.data.worlds.new(PREFIX + "clear_day_world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky_grade = nodes.new("ShaderNodeHueSaturation")
    sky_grade.inputs["Saturation"].default_value = 1.12
    sky_grade.inputs["Value"].default_value = 1.02
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(56)
    sky.sun_rotation = math.radians(226)
    sky.altitude = 0.32
    sky.air_density = 0.92
    sky.dust_density = 0.025
    sky.ozone_density = 1.02
    bg.inputs["Strength"].default_value = 0.34
    sky_tint = nodes.new("ShaderNodeMixRGB")
    sky_tint.blend_type = "MIX"
    sky_tint.inputs["Fac"].default_value = 0.28
    sky_tint.inputs[2].default_value = (0.08, 0.30, 0.70, 1.0)
    links.new(sky.outputs["Color"], sky_grade.inputs["Color"])
    links.new(sky_grade.outputs["Color"], sky_tint.inputs[1])
    links.new(sky_tint.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])
    bpy.context.scene.world = world
    data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    data.energy = 2.65
    data.angle = math.radians(0.38)
    sun = bpy.data.objects.new(PREFIX + "day_sun", data)
    bpy.context.scene.collection.objects.link(sun)
    sun.location = (-65, -85, 110)
    sun.rotation_euler = (
        (Vector((0, 0, 4)) - sun.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(sun, "daylight")
    fill_data = bpy.data.lights.new(PREFIX + "day_fill", "AREA")
    fill_data.energy = 32
    fill_data.shape = "DISK"
    fill_data.size = 54
    fill = bpy.data.objects.new(PREFIX + "day_fill", fill_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.location = (45, -38, 48)
    fill.rotation_euler = (
        (Vector((0, 2, 3)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(fill, "daylight_fill")


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
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.08
    scene["c2w_preview_render"] = bool(preview)
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 8 if preview else 24
        if hasattr(scene.eevee, "taa_samples"):
            scene.eevee.taa_samples = 8 if preview else 24
    scene.camera = None


def camera(name, loc, target, lens, role):
    data = bpy.data.cameras.new(PREFIX + name)
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = False
    data.clip_start = 0.08
    data.clip_end = 650.0
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    obj["c2w_view_role"] = role
    return tag(obj, "validation_camera")


def camera_specs():
    return [
        (
            "01_three_station_row_front_far.png",
            (0, -121, 10.5),
            (0, 0.6, 4.05),
            36,
            "far",
        ),
        (
            "02_three_station_row_oblique_far.png",
            (-91, -78, 14.2),
            (0, 0.2, 4.05),
            45,
            "far",
        ),
        (
            "03_three_station_row_rear_aerial_far.png",
            (76, 55, 25.0),
            (0, 2.8, 3.45),
            52,
            "far",
        ),
        (
            "04_nobile_wave_reference_close.png",
            (-57, -31, 5.8),
            (-38, -1.8, 3.45),
            49,
            "near",
        ),
        (
            "05_nobile_dispenser_pylon_detail.png",
            (-34.6, -13.2, 2.62),
            (-38.0, -2.7, 1.48),
            60,
            "detail",
        ),
        (
            "06_blue_orange_reference_close.png",
            (-14, -32, 5.7),
            (-1, -1.7, 3.42),
            48,
            "near",
        ),
        (
            "07_blue_orange_dispenser_detail.png",
            (7.3, -12.9, 2.65),
            (3.4, -2.70, 1.48),
            62,
            "detail",
        ),
        (
            "08_red_yellow_reference_close.png",
            (54, -31, 5.8),
            (39, -1.6, 3.38),
            49,
            "near",
        ),
        (
            "09_red_yellow_pylon_pump_detail.png",
            (27, -17.5, 3.4),
            (34, -2.8, 2.05),
            57,
            "detail",
        ),
        (
            "10_blue_storefront_interior_close.png",
            (6.6, -1.8, 2.55),
            (2.15, 5.36, 2.05),
            58,
            "storefront",
        ),
        (
            "11_nobile_storefront_door_close.png",
            (-29.9, -1.9, 2.62),
            (-34.525, 5.34, 2.05),
            58,
            "storefront",
        ),
        (
            "12_red_yellow_storefront_door_close.png",
            (51.0, -1.9, 2.62),
            (46.588, 5.34, 2.05),
            58,
            "storefront",
        ),
    ]


def render_all(cameras):
    selected = {
        x.strip()
        for x in os.environ.get("C2W_GASS_VIEW_FILTER", "").split(",")
        if x.strip()
    }
    scene = bpy.context.scene
    for filename, cam, role in cameras:
        if selected and not any(filename.startswith(prefix) for prefix in selected):
            continue
        preview = bool(scene.get("c2w_preview_render", False))
        if role == "far":
            scene.render.resolution_x = 1400 if preview else 2200
            scene.render.resolution_y = 484 if preview else 760
        else:
            scene.render.resolution_x = 960 if preview else 1600
            scene.render.resolution_y = 600 if preview else 1000
        print(f"[gass] rendering {role}: {filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def semantic_counts(objects=None):
    counts = {}
    for obj in objects or bpy.context.scene.objects:
        sem = obj.get("c2w_semantic", "unclassified")
        counts[sem] = counts.get(sem, 0) + 1
    return dict(sorted(counts.items()))


def product_support_audit():
    support_names = {
        o.name
        for o in bpy.context.scene.objects
        if o.get("c2w_semantic") == "shelf_deck"
    }
    supported = [
        o
        for o in bpy.context.scene.objects
        if o.get("c2w_support_relation") == "rests_on_modeled_shelf"
    ]
    errors = []
    for obj in supported:
        support = obj.get("c2w_support_name", "")
        declared = float(obj.get("c2w_support_top_z", -999))
        if support not in support_names:
            errors.append({"object": obj.name, "reason": "missing_modeled_shelf"})
        if abs((obj.location.z - obj.scale.z * 0.5) - declared) > 0.0015:
            # Instance cylinders and cubes both use normalized unit-height meshes.
            errors.append(
                {
                    "object": obj.name,
                    "reason": "base_not_on_shelf",
                    "gap_m": round((obj.location.z - obj.scale.z * 0.5) - declared, 6),
                }
            )
    return {
        "modeled_shelf_decks": len(support_names),
        "supported_product_bodies": len(supported),
        "support_error_count": len(errors),
        "sample_errors": errors[:20],
        "passed": len(support_names) >= 90 and len(supported) >= 900 and not errors,
    }


def render_diagnostics():
    diagnostics = {}
    for filename, _, _, _, _ in camera_specs():
        path = RENDERS / filename
        item = {
            "path": str(path),
            "bytes": path.stat().st_size if path.is_file() else 0,
        }
        if not path.is_file() or path.stat().st_size < 45000:
            item.update({"passed": False, "reason": "missing_or_too_small"})
            diagnostics[filename] = item
            continue
        image = bpy.data.images.load(str(path), check_existing=False)
        width, height = image.size
        values = []
        for gy in range(9):
            py = min(height - 1, int((gy + 0.5) * height / 9))
            for gx in range(15):
                px = min(width - 1, int((gx + 0.5) * width / 15))
                idx = 4 * (py * width + px)
                values.append(
                    (image.pixels[idx] + image.pixels[idx + 1] + image.pixels[idx + 2])
                    / 3
                )
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        dark = sum(v < 0.012 for v in values) / len(values)
        bright = sum(v > 0.99 for v in values) / len(values)
        role = next((r for fn, _, _, _, r in camera_specs() if fn == filename), "near")
        resolution_ok = (
            (width >= 2200 and height >= 760)
            if role == "far"
            else (width >= 1600 and height >= 1000)
        )
        passed = resolution_ok and variance >= 0.002 and dark < 0.72 and bright < 0.72
        item.update(
            {
                "passed": passed,
                "resolution": [width, height],
                "sample_mean": round(mean, 6),
                "sample_variance": round(variance, 6),
                "dark_fraction": round(dark, 4),
                "bright_fraction": round(bright, 4),
            }
        )
        diagnostics[filename] = item
        bpy.data.images.remove(image)
    return diagnostics


def validate(root, cameras, reference_records, rendered=False):
    objects = list(bpy.context.scene.objects)
    renderables = [
        o for o in objects if o.type in {"MESH", "CURVE", "FONT"} and not o.hide_render
    ]
    stations = [c for c in root.children if c.get("c2w_role") == "gas_station_asset"]
    by_variant = {}
    expected_pumps = {v: len(s.pump_x) for v, s in STYLES.items()}
    for variant in STYLES:
        obs = [o for o in objects if o.get("c2w_station_variant") == variant]
        counts = semantic_counts(obs)
        by_variant[variant] = {
            "objects": len(obs),
            "renderables": sum(o.type in {"MESH", "CURVE", "FONT"} for o in obs),
            "semantic_counts": counts,
            "expected_dispensers": expected_pumps[variant],
        }
    support = product_support_audit()
    banned_tokens = (
        "placeholder",
        "proxy",
        "dummy",
        "toy",
        "lowpoly",
        "low_poly",
        "primitive_only",
    )
    banned = [
        o.name for o in renderables if any(t in o.name.lower() for t in banned_tokens)
    ]
    complex_materials = [
        m
        for m in bpy.data.materials
        if m.use_nodes and m.node_tree and len(m.node_tree.nodes) >= 7
    ]
    views = [
        {
            "file": fn,
            "role": role,
            "bytes": (RENDERS / fn).stat().st_size if (RENDERS / fn).is_file() else 0,
        }
        for fn, _, _, _, role in camera_specs()
    ]
    roots = [
        o
        for o in objects
        if o.get("c2w_role") == "procedural_asset_root"
        and o.get("c2w_station_variant") in STYLES
    ]
    roots_sorted = sorted(roots, key=lambda o: o.location.x)
    adapter_available = False
    try:
        ua = importlib.import_module("urban_assets")
        adapter_available = (
            callable(getattr(ua, "build_gas_station_reference_row", None))
            and callable(getattr(ua, "build_gas_station_asset", None))
            and tuple(getattr(ua, "GAS_STATION_VARIANTS", ())) == tuple(STYLES)
        )
    except Exception:
        adapter_available = False
    dense_checks = {
        v: (d["objects"] >= 1700 and d["renderables"] >= 1600)
        for v, d in by_variant.items()
    }
    dispenser_checks = {
        v: (
            d["semantic_counts"].get("dispenser_brand_crown", 0) == expected_pumps[v]
            and d["semantic_counts"].get("fuel_hose", 0) == expected_pumps[v] * 4
            and d["semantic_counts"].get("fuel_nozzle", 0) == expected_pumps[v] * 4
            and d["semantic_counts"].get("fuel_nozzle_spout", 0)
            == expected_pumps[v] * 4
        )
        for v, d in by_variant.items()
    }
    interior_checks = {
        v: (
            d["semantic_counts"].get("store_product", 0) >= 430
            and d["semantic_counts"].get("store_product_label", 0) >= 300
            and d["semantic_counts"].get("shelf_deck", 0) >= 30
            and d["semantic_counts"].get("cooler_glazing", 0) >= 6
            and d["semantic_counts"].get("roof_hvac_unit", 0) == 2
        )
        for v, d in by_variant.items()
    }
    structure_checks = {
        v: (
            d["semantic_counts"].get("canopy_light", 0) >= 6
            and d["semantic_counts"].get("canopy_column", 0) >= 4
            and d["semantic_counts"].get("fastener", 0) >= 34
            and d["semantic_counts"].get("rainwater_downpipe", 0) >= 6
            and d["semantic_counts"].get("shrub_leaf", 0) >= 430
        )
        for v, d in by_variant.items()
    }
    manufactured_form_checks = {
        v: (
            d["semantic_counts"].get("fuel_dispenser", 0) == expected_pumps[v]
            and d["semantic_counts"].get("dispenser_rolled_edge", 0)
            == expected_pumps[v] * 2
            and d["semantic_counts"].get("dispenser_vent", 0) == expected_pumps[v] * 14
            and d["semantic_counts"].get("air_service_machine", 0) == 1
            # Each of three vent stacks has a vertical riser plus a modeled
            # gooseneck, both intentionally carrying the service semantic.
            and d["semantic_counts"].get("underground_tank_vent", 0) == 6
        )
        for v, d in by_variant.items()
    }
    reference_specific_checks = {
        "nobile_wave": (
            by_variant["nobile_wave"]["semantic_counts"].get("cafe_awning", 0) == 1
            and by_variant["nobile_wave"]["semantic_counts"].get("cafe_sign", 0) == 1
            and by_variant["nobile_wave"]["semantic_counts"].get(
                "canopy_fascia_reveal", 0
            )
            >= 1
        ),
        "blue_orange": (
            by_variant["blue_orange"]["semantic_counts"].get("canopy_roof_seam", 0)
            >= 16
            and by_variant["blue_orange"]["semantic_counts"].get("store_facade_pier", 0)
            == 2
            and by_variant["blue_orange"]["semantic_counts"].get(
                "store_entry_canopy", 0
            )
            == 1
        ),
        "red_yellow": (
            by_variant["red_yellow"]["semantic_counts"].get("canopy_rear_truss", 0)
            == 12
            and by_variant["red_yellow"]["semantic_counts"].get(
                "store_glazed_portal_frame", 0
            )
            >= 7
            and by_variant["red_yellow"]["semantic_counts"].get(
                "store_vertical_cladding", 0
            )
            == 2
        ),
    }
    detailed_door_checks = {
        v: (
            by_variant[v]["semantic_counts"].get("door_safety_glazing", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_leaf_frame", 0) == 8
            and by_variant[v]["semantic_counts"].get("door_glazing_gasket", 0) == 8
            and by_variant[v]["semantic_counts"].get("door_continuous_hinge", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_lock_cylinder", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_pull_handle", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_handle_mount", 0) == 4
            and by_variant[v]["semantic_counts"].get("door_concealed_closer", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_threshold_profile", 0) == 1
            and by_variant[v]["semantic_counts"].get("door_bottom_sweep", 0) == 2
            and by_variant[v]["semantic_counts"].get("door_astragal", 0) == 1
            and all(
                o.get("c2w_door_glazing_type") == "tempered_laminated_safety_glass"
                and int(o.get("c2w_glazing_dot_markers", -1)) == 0
                for o in objects
                if o.get("c2w_station_variant") == v
                and o.get("c2w_semantic") == "door_safety_glazing"
            )
            and all(
                by_variant[v]["semantic_counts"].get(old, 0) == 0
                for old in (
                    "opaque_entrance_leaf",
                    "opaque_door_backing",
                    "door_kickplate",
                    "door_pushplate",
                    "door_brand_inlay",
                    "door_closer_arm",
                )
            )
        )
        for v in STYLES
    }
    equipment_detail_checks = {
        v: (
            by_variant[v]["semantic_counts"].get("dispenser_payment_module", 0)
            == expected_pumps[v] * 2
            and by_variant[v]["semantic_counts"].get("dispenser_service_hatch_seam", 0)
            == expected_pumps[v] * 8
            and by_variant[v]["semantic_counts"].get("dispenser_side_panel", 0)
            == expected_pumps[v] * 2
            and by_variant[v]["semantic_counts"].get("hose_breakaway_coupling", 0)
            == expected_pumps[v] * 4
            and by_variant[v]["semantic_counts"].get("pump_keypad", 0)
            == expected_pumps[v] * 24
            and by_variant[v]["semantic_counts"].get("dispenser_grade_text", 0)
            == expected_pumps[v] * 3
            and all(
                o.get("c2w_manufactured_form") == "single_radiused_folded_sheet_cabinet"
                for o in objects
                if o.get("c2w_station_variant") == v
                and o.get("c2w_semantic") == "fuel_dispenser"
            )
            and all(
                o.get("c2w_manufactured_form") == "integrated_folded_rectangular_header"
                for o in objects
                if o.get("c2w_station_variant") == v
                and o.get("c2w_semantic") == "dispenser_brand_crown"
            )
        )
        for v in STYLES
    }
    architectural_detail_checks = {
        v: (
            by_variant[v]["semantic_counts"].get("storefront_glazing", 0) == 7
            and by_variant[v]["semantic_counts"].get("storefront_glazing_gasket", 0)
            >= 56
            and by_variant[v]["semantic_counts"].get("storefront_pressure_plate", 0)
            == 28
            and by_variant[v]["semantic_counts"].get("storefront_mullion_receptor", 0)
            == 9
            and by_variant[v]["semantic_counts"].get("storefront_mullion_cap", 0) == 9
            and by_variant[v]["semantic_counts"].get("storefront_manifestation", 0) == 0
            and by_variant[v]["semantic_counts"].get("canopy_sprinkler_head", 0) >= 6
            and by_variant[v]["semantic_counts"].get("canopy_junction_box", 0) == 3
            and by_variant[v]["semantic_counts"].get("cctv_camera", 0) == 1
            and by_variant[v]["semantic_counts"].get("cctv_lens", 0) == 1
            and by_variant[v]["semantic_counts"].get("facade_fastener", 0) >= 18
            and by_variant[v]["semantic_counts"].get("storefront_corner_flashing", 0)
            == 2
        )
        for v in STYLES
    }
    fitted_signs = [o for o in objects if "c2w_sign_panel_width" in o]
    fitted_sign_check = len(fitted_signs) >= 60 and all(
        bool(o.get("c2w_sign_fit", False)) for o in fitted_signs
    )
    font_objects = [o for o in objects if o.type == "FONT"]
    scene_text_bodies = [str(o.data.body) for o in font_objects]
    cjk_text_objects = [o.name for o in font_objects if contains_cjk(str(o.data.body))]
    scene_text_audit = {
        "font_object_count": len(font_objects),
        "unique_visible_text": sorted(set(scene_text_bodies)),
        "cjk_text_object_count": len(cjk_text_objects),
        "cjk_text_objects": cjk_text_objects,
        "passed": not cjk_text_objects,
    }
    crossing = [o for o in objects if o.get("c2w_semantic") == "pedestrian_crossing"]
    crossing_orientation_ok = len(crossing) == 7 and all(
        o.get("c2w_crosswalk_bar_axis") == "X"
        and int(o.get("c2w_rotation_correction_degrees", 0)) == 90
        and abs(o.scale.x) > abs(o.scale.y) * 8
        for o in crossing
    )
    checks = {
        "exactly_three_reference_specific_station_assets": len(stations) == 3
        and sorted(c.get("c2w_reference_index") for c in stations) == [1, 2, 3],
        "three_geometrically_distinct_canopy_archetypes": {
            c.get("c2w_archetype") for c in stations
        }
        == {"sculpted_wave", "layered_hip", "flat_banded"},
        "east_west_single_row_with_independent_roots": len(roots_sorted) == 3
        and [round(o.location.x, 1) for o in roots_sorted] == [-38.0, 0.0, 38.0]
        and all(abs(o.location.y) < 0.001 for o in roots_sorted),
        "each_station_is_dense_production_geometry": all(dense_checks.values()),
        "all_dispensers_have_four_complete_hose_nozzle_assemblies": all(
            dispenser_checks.values()
        ),
        "each_store_retains_commercial_fitout_behind_reflective_facade": all(
            interior_checks.values()
        ),
        "modeled_shelf_support_is_physically_consistent": support["passed"],
        "modeled_canopy_structure_services_and_landscape": all(
            structure_checks.values()
        ),
        "formed_dispenser_and_service_equipment_geometry": all(
            manufactured_form_checks.values()
        ),
        "complex_integrated_dispenser_modules_replace_toy_assemblies": all(
            equipment_detail_checks.values()
        ),
        "all_store_entrances_are_detailed_commercial_glazed_assemblies": all(
            detailed_door_checks.values()
        ),
        "no_dot_markers_on_storefront_or_door_glazing": all(
            by_variant[v]["semantic_counts"].get("storefront_manifestation", 0) == 0
            and all(
                int(o.get("c2w_glazing_dot_markers", -1)) == 0
                for o in objects
                if o.get("c2w_station_variant") == v
                and o.get("c2w_semantic")
                in {"storefront_glazing", "door_safety_glazing"}
            )
            for v in STYLES
        ),
        "architectural_envelope_and_canopy_services_are_detailed": all(
            architectural_detail_checks.values()
        ),
        "all_visible_scene_text_is_cjk_free": scene_text_audit["passed"],
        "no_unrequested_vehicle_or_toy_context_models": semantic_counts(objects).get(
            "vehicle_root", 0
        )
        == 0,
        "all_primary_sign_text_is_large_and_panel_fitted": fitted_sign_check,
        "reference_specific_store_and_canopy_construction": all(
            reference_specific_checks.values()
        ),
        "reference_images_archived_inside_workspace": len(reference_records) == 3
        and min(r["bytes"] for r in reference_records) > 10000,
        "multi_scale_pbr_material_system": len(bpy.data.materials) >= 38
        and len(complex_materials) >= 12,
        "twelve_daylight_near_far_detail_views": len(cameras) == 12
        and {v["role"] for v in views} >= {"far", "near", "detail", "storefront"},
        "active_urban_pipeline_adapter_is_callable": adapter_available
        and root.get("c2w_pipeline_adapter")
        == "urban_assets.build_gas_station_reference_row",
        "source_generator_is_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_gass.build_gas_station_reference_row",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "all_renderable_geometry_is_source_tagged": all(
            o.get("c2w_generator") == Path(__file__).name
            and o.get("c2w_source_geometry") == "procedural"
            for o in renderables
        ),
        "no_placeholder_or_degraded_asset_names": not banned,
        "pedestrian_crossing_is_rotated_90_degrees_to_correct_axis": crossing_orientation_ok,
        "photographic_context_has_crossing_and_layered_terrain": semantic_counts(
            objects
        ).get("pedestrian_crossing", 0)
        == 7
        and semantic_counts(objects).get("distant_terrain", 0) == 2,
    }
    diagnostics = {}
    if rendered:
        diagnostics = render_diagnostics()
        checks["all_twelve_full_resolution_renders_are_nonblank"] = len(
            diagnostics
        ) == 12 and all(d["passed"] for d in diagnostics.values())
    data = {
        "schema": "agent.urban_asset_manifest.v6",
        "generator": str(Path(__file__).resolve()),
        "runner": str((ROOT / "scripts/run_urban_v3_gass.sh").resolve()),
        "output": str(OUT),
        "blend": str(BLEND),
        "pipeline_asset_id": ASSET_ID,
        "output_run_id": OUTPUT_RUN_ID,
        "model_revision": MODEL_REVISION,
        "pipeline_connected": True,
        "pipeline_entrypoint": "generate_urban_v3_gass.build_gas_station_reference_row",
        "pipeline_adapter": "urban_assets.build_gas_station_reference_row",
        "single_asset_entrypoint": "generate_urban_v3_gass.build_gas_station_asset",
        "single_asset_adapter": "urban_assets.build_gas_station_asset",
        "rebuild_command": "bash scripts/run_urban_v3_gass.sh",
        "reference_urls": REFERENCE_URLS,
        "reference_files": reference_records,
        "reference_observations": {
            "reference_01": "white sculpted wave canopy, red/orange/yellow flowing fascia, round flame emblem, warm-trimmed market and freestanding cafe/price pylon",
            "reference_02": "wide shallow-hip white canopy, layered blue-orange-blue fascia, blue clad wayfinding columns, four aligned dispenser islands and blue convenience-store bands",
            "reference_03": "flat white canopy with red/yellow double band, square white columns, neutral gray dispensers, matching glazed convenience store and tall three-grade price pylon",
        },
        "station_variants": list(STYLES),
        "station_count": len(stations),
        "variant_audit": by_variant,
        "object_count": len(objects),
        "renderable_count": len(renderables),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "semantic_counts": semantic_counts(objects),
        "product_support_audit": support,
        "dense_geometry_checks": dense_checks,
        "dispenser_assembly_checks": dispenser_checks,
        "interior_detail_checks": interior_checks,
        "structure_detail_checks": structure_checks,
        "manufactured_form_checks": manufactured_form_checks,
        "equipment_detail_checks": equipment_detail_checks,
        "detailed_door_checks": detailed_door_checks,
        "architectural_detail_checks": architectural_detail_checks,
        "scene_text_audit": scene_text_audit,
        "fitted_sign_count": len(fitted_signs),
        "crossing_orientation_check": crossing_orientation_ok,
        "reference_specific_geometry_checks": reference_specific_checks,
        "render_views": views,
        "render_diagnostics": diagnostics,
        "render_settings": {
            "engine": "BLENDER_EEVEE_NEXT",
            "near_resolution": [1600, 1000],
            "far_resolution": [2200, 760],
            "samples": 24,
            "color_management": "AgX - Medium High Contrast",
        },
        "daylight": True,
        "near_and_far_views": True,
        "external_blend_inputs": 0,
        "banned_geometry_names": banned,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not data["all_checks_passed"]:
        failed = [name for name, value in checks.items() if not value]
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps({"failed": failed, "audit": data}, indent=2, ensure_ascii=False),
            encoding="utf8",
        )
        raise RuntimeError("Gas-station production audit failed: " + ", ".join(failed))
    return data


def main():
    print("[gass] starting source-driven production generator", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    REFERENCES.mkdir(parents=True, exist_ok=True)
    reference_records = archive_references()
    for stale in (
        OUT / "SUCCESS",
        OUT / "manifest.json",
        OUT / "quality_report.json",
        OUT / "build_audit.json",
        OUT / "FAILED_AUDIT.json",
    ):
        stale.unlink(missing_ok=True)
    for filename, _, _, _, _ in camera_specs():
        (RENDERS / filename).unlink(missing_ok=True)
    preview = os.environ.get("C2W_GASS_PREVIEW", "0") == "1"
    build_only = os.environ.get("C2W_GASS_BUILD_ONLY", "0") == "1"
    partial_render = bool(os.environ.get("C2W_GASS_VIEW_FILTER", "").strip())
    reset_scene()
    sys.path.insert(0, str(ROOT / "scripts"))
    # Validation intentionally enters through the active pipeline adapter.
    UA = importlib.import_module("urban_assets")
    root = UA.build_gas_station_reference_row(prefix=PREFIX)
    M = make_materials()
    build_presentation_context(root, M)
    setup_daylight()
    configure_scene(preview)
    cameras = []
    for filename, loc, target, lens, role in camera_specs():
        cameras.append((filename, camera(filename[:-4], loc, target, lens, role), role))
    initial = validate(root, cameras, reference_records, rendered=False)
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_runner"] = str(
        (ROOT / "scripts/run_urban_v3_gass.sh").resolve()
    )
    scene["c2w_asset_id"] = ASSET_ID
    scene["c2w_domain"] = "urban_gas_station"
    scene["c2w_reference_driven"] = True
    scene["c2w_model_revision"] = MODEL_REVISION
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_gass.build_gas_station_reference_row"
    scene["c2w_pipeline_adapter"] = "urban_assets.build_gas_station_reference_row"
    scene[
        "c2w_quality_profile"
    ] = "reference_grade_complex_procedural_modeling_v6_detailed_storefronts_english_only_no_toy_forms"
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
                    "checks": initial["checks"],
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
    final = validate(root, cameras, reference_records, rendered=True)
    scene["c2w_manifest"] = json.dumps(final, ensure_ascii=False)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    (OUT / "manifest.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8"
    )
    quality = {
        "result": "PASS",
        "all_checks_passed": True,
        "checks": final["checks"],
        "variant_audit": final["variant_audit"],
        "product_support_audit": final["product_support_audit"],
        "dispenser_assembly_checks": final["dispenser_assembly_checks"],
        "interior_detail_checks": final["interior_detail_checks"],
        "structure_detail_checks": final["structure_detail_checks"],
        "manufactured_form_checks": final["manufactured_form_checks"],
        "equipment_detail_checks": final["equipment_detail_checks"],
        "detailed_door_checks": final["detailed_door_checks"],
        "architectural_detail_checks": final["architectural_detail_checks"],
        "scene_text_audit": final["scene_text_audit"],
        "crossing_orientation_check": final["crossing_orientation_check"],
        "fitted_sign_count": final["fitted_sign_count"],
        "reference_specific_geometry_checks": final[
            "reference_specific_geometry_checks"
        ],
        "render_diagnostics": final["render_diagnostics"],
        "note": "Quality gates require independent reference archetypes, integrated radiused dispenser cabinets with complete payment/hose hardware, detailed glazed commercial entry assemblies, dot-free curtain-wall glazing, English-only fitted signage, corrected crossing orientation, detailed architectural services, no unrequested context vehicles and nonblank full-resolution daylight renders; raw object count alone cannot pass.",
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf8"
    )
    (OUT / "SUCCESS").write_text(
        f"{OUTPUT_RUN_ID} production generation, pipeline-adapter validation and twelve daylight views complete\n",
        encoding="utf8",
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
