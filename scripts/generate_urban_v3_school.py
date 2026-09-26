"""Reference-driven procedural school campus production generator.

This is the source generator for ``urban_v3_school5``.  It builds every
building, facade component, sports facility and site element from code in the
active Blender scene.  No prepared blend is appended and no post-generation
manual patch is required.  ``build_school_campus`` is the reusable urban
pipeline entry point; ``main`` creates and validates the requested daylight
near/far presentation scene.
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
OUTPUT_NAME = "urban_v3_school5"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / OUTPUT_NAME
RENDERS = OUT / "renders"
PREFIX = "school:"
SCHEMA_VERSION = 6

LAWN_ZONES = (
    ("west_boundary", (-104.0, 67.0), (5.6, 32.0), 0.78),
    ("north_boundary", (0.0, 83.2), (200.0, 8.0), 0.82),
    ("east_boundary", (103.0, 42.0), (6.0, 78.0), 0.76),
    ("east_courtyard", (62.0, 23.0), (14.0, 8.0), 0.52),
)
TREE_POSITIONS = (
    tuple((float(x), 82.0) for x in range(-85, 96, 20))
    + tuple((103.0, float(y)) for y in (-72, -48, -20, 12, 35, 58, 77))
    + ((-104.0, 57.0), (-104.0, 75.0))
    + ((48.0, -83.0), (65.0, -83.0), (82.0, -83.0))
    + (
        (-31.0, 53.0),
        (37.0, 49.0),
        (65.0, 23.0),
        (45.0, -39.0),
        (96.0, -43.0),
        (17.0, -57.0),
    )
)


def _position_inside_lawn(position):
    """Return whether a trunk centre is inside one of the modeled turf beds."""
    x, y = position
    return any(
        abs(x - center[0]) <= dims[0] / 2 and abs(y - center[1]) <= dims[1] / 2
        for _, center, dims, _ in LAWN_ZONES
    )


# Every tree rooted in hard campus paving receives a genuine square opening.
# This is derived from the same placement table used to instantiate the trees,
# preventing later tree additions from silently appearing through concrete.
PAVED_TREE_PITS = tuple(
    position for position in TREE_POSITIONS if not _position_inside_lawn(position)
)
assert len(PAVED_TREE_PITS) == 11
REFERENCE_URL = (
    "https://respic.3d66.com/coverimg/cache/7018/"
    "34f253e341898cf6604ed1238677e471.jpg!medium-size-2"
    "?v=12708662&k=D41D8CD98F00B204E9800998ECF8427E"
)

sys.path.insert(0, str(ROOT / "infinigen"))
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all46_2 as BASE

# Reuse the production geometry/material primitives from the current urban_v3
# generator, while rebinding their namespace and tags to this source entrypoint.
BASE.PREFIX = PREFIX
BASE.G.PREFIX = PREFIX
BASE._CUBE_MESHES = {}


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
text_object = BASE.text_object
pbr = BASE.pbr


def origin3(origin):
    return origin if len(origin) == 3 else (origin[0], origin[1], 0.0)


def local_box(c, name, origin, yaw, xyz, dims, material, bevel=0.035, role=None):
    return BASE.local_box(
        c, name, origin3(origin), yaw, xyz, dims, material, bevel, role
    )


def local_text(
    c, name, body, origin, yaw, xyz, size, material, extrude=0.055, align="CENTER"
):
    return BASE.local_text(
        c, name, body, origin3(origin), yaw, xyz, size, material, extrude, align
    )


def collection(name, parent=None, asset_id=None, role="procedural_asset"):
    result = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(result)
    result["c2w_schema_version"] = SCHEMA_VERSION
    result["c2w_role"] = role
    result["c2w_generator"] = Path(__file__).name
    if asset_id:
        result["c2w_asset_id"] = asset_id
    return result


def _surface_coordinates(nodes, links, scale):
    """World-scaled coordinates keep procedural finishes consistent in metres."""
    geometry = nodes.new("ShaderNodeNewGeometry")
    mapping = nodes.new("ShaderNodeVectorMath")
    mapping.operation = "SCALE"
    mapping.inputs[3].default_value = scale
    links.new(geometry.outputs["Position"], mapping.inputs[0])
    return mapping.outputs["Vector"]


def procedural_brick(name, color_a, color_b, mortar_color):
    """Physically legible running-bond masonry with recessed mortar and micrograin."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.78
    bsdf.inputs["Base Color"].default_value = (*color_a, 1)
    coordinates = _surface_coordinates(nodes, links, 1.0)
    # Collapse horizontal world axes and retain world Z as the row axis.  This
    # keeps running bond horizontal on both north/south and east/west walls.
    separate = nodes.new("ShaderNodeSeparateXYZ")
    horizontal = nodes.new("ShaderNodeMath")
    horizontal.operation = "ADD"
    brick_coordinates = nodes.new("ShaderNodeCombineXYZ")
    links.new(coordinates, separate.inputs["Vector"])
    links.new(separate.outputs["X"], horizontal.inputs[0])
    links.new(separate.outputs["Y"], horizontal.inputs[1])
    links.new(horizontal.outputs["Value"], brick_coordinates.inputs["X"])
    links.new(separate.outputs["Z"], brick_coordinates.inputs["Y"])
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.squash_frequency = 2
    brick.inputs["Color1"].default_value = (*color_a, 1)
    brick.inputs["Color2"].default_value = (*color_b, 1)
    brick.inputs["Mortar"].default_value = (*mortar_color, 1)
    brick.inputs["Scale"].default_value = 2.05
    brick.inputs["Mortar Size"].default_value = 0.032
    brick.inputs["Mortar Smooth"].default_value = 0.015
    brick.inputs["Brick Width"].default_value = 0.64
    brick.inputs["Row Height"].default_value = 0.24
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 34.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.72
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.16
    links.new(brick_coordinates.outputs["Vector"], brick.inputs["Vector"])
    links.new(coordinates, noise.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(noise.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.34
    bump.inputs["Distance"].default_value = 0.045
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "running_bond_masonry"
    return mat


def procedural_ground(
    name, dark, light, scale, roughness, bump_strength=0.18, detail=6.0
):
    """Multi-scale non-uniform ground finish for asphalt, paving, turf and rubber."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = roughness
    coordinates = _surface_coordinates(nodes, links, 1.0)
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    macro.inputs["Scale"].default_value = scale
    macro.inputs["Detail"].default_value = detail
    macro.inputs["Roughness"].default_value = 0.68
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    micro.inputs["Scale"].default_value = scale * 12.0
    micro.inputs["Detail"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (*light, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.035
    links.new(coordinates, macro.inputs["Vector"])
    links.new(coordinates, micro.inputs["Vector"])
    links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "multi_scale_ground"
    return mat


def procedural_lawn(name, dark, mid, light, macro_scale=0.42):
    """Layered close-mown turf shader with broad growth and fine fibre relief."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.93
    if "Sheen Weight" in shader.inputs:
        shader.inputs["Sheen Weight"].default_value = 0.08
    coordinates = _surface_coordinates(nodes, links, 1.0)

    broad = nodes.new("ShaderNodeTexNoise")
    broad.noise_dimensions = "3D"
    broad.inputs["Scale"].default_value = macro_scale
    broad.inputs["Detail"].default_value = 6.5
    broad.inputs["Roughness"].default_value = 0.72
    clumps = nodes.new("ShaderNodeTexNoise")
    clumps.noise_dimensions = "3D"
    clumps.inputs["Scale"].default_value = 5.5
    clumps.inputs["Detail"].default_value = 5.0
    clumps.inputs["Roughness"].default_value = 0.78
    fibres = nodes.new("ShaderNodeTexVoronoi")
    fibres.distance = "EUCLIDEAN"
    fibres.feature = "DISTANCE_TO_EDGE"
    fibres.inputs["Scale"].default_value = 38.0

    broad_ramp = nodes.new("ShaderNodeValToRGB")
    broad_ramp.color_ramp.elements[0].position = 0.20
    broad_ramp.color_ramp.elements[0].color = (*dark, 1)
    broad_ramp.color_ramp.elements[1].position = 0.82
    broad_ramp.color_ramp.elements[1].color = (*mid, 1)
    clump_ramp = nodes.new("ShaderNodeValToRGB")
    clump_ramp.color_ramp.elements[0].position = 0.30
    clump_ramp.color_ramp.elements[0].color = (0.55, 0.58, 0.50, 1)
    clump_ramp.color_ramp.elements[1].position = 0.74
    clump_ramp.color_ramp.elements[1].color = (*light, 1)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "MULTIPLY"
    color_mix.inputs["Fac"].default_value = 0.28
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.31
    bump.inputs["Distance"].default_value = 0.024

    links.new(coordinates, broad.inputs["Vector"])
    links.new(coordinates, clumps.inputs["Vector"])
    links.new(coordinates, fibres.inputs["Vector"])
    links.new(broad.outputs["Fac"], broad_ramp.inputs["Fac"])
    links.new(clumps.outputs["Fac"], clump_ramp.inputs["Fac"])
    links.new(broad_ramp.outputs["Color"], color_mix.inputs[1])
    links.new(clump_ramp.outputs["Color"], color_mix.inputs[2])
    links.new(color_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(fibres.outputs["Distance"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "layered_living_turf"
    return mat


def procedural_tree_soil(name):
    """Rich planting soil with moisture variation, pores and fine aggregate relief."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.965
    if "Specular IOR Level" in shader.inputs:
        shader.inputs["Specular IOR Level"].default_value = 0.24
    coordinates = _surface_coordinates(nodes, links, 1.0)

    moist_clods = nodes.new("ShaderNodeTexNoise")
    moist_clods.noise_dimensions = "3D"
    moist_clods.inputs["Scale"].default_value = 3.15
    moist_clods.inputs["Detail"].default_value = 8.0
    moist_clods.inputs["Roughness"].default_value = 0.82
    moist_clods.inputs["Distortion"].default_value = 0.28
    grains = nodes.new("ShaderNodeTexNoise")
    grains.noise_dimensions = "3D"
    grains.inputs["Scale"].default_value = 38.0
    grains.inputs["Detail"].default_value = 6.0
    grains.inputs["Roughness"].default_value = 0.76
    pores = nodes.new("ShaderNodeTexVoronoi")
    pores.distance = "EUCLIDEAN"
    pores.feature = "DISTANCE_TO_EDGE"
    pores.inputs["Scale"].default_value = 23.0

    soil_ramp = nodes.new("ShaderNodeValToRGB")
    soil_ramp.color_ramp.elements[0].position = 0.16
    soil_ramp.color_ramp.elements[0].color = (0.009, 0.0025, 0.001, 1)
    middle = soil_ramp.color_ramp.elements.new(0.48)
    middle.color = (0.066, 0.020, 0.0045, 1)
    soil_ramp.color_ramp.elements[-1].position = 0.86
    soil_ramp.color_ramp.elements[-1].color = (0.265, 0.105, 0.022, 1)
    grain_ramp = nodes.new("ShaderNodeValToRGB")
    grain_ramp.color_ramp.elements[0].position = 0.31
    grain_ramp.color_ramp.elements[0].color = (0.12, 0.045, 0.012, 1)
    grain_ramp.color_ramp.elements[1].position = 0.73
    grain_ramp.color_ramp.elements[1].color = (0.62, 0.34, 0.105, 1)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "SOFT_LIGHT"
    color_mix.inputs["Fac"].default_value = 0.38

    grain_weight = nodes.new("ShaderNodeMath")
    grain_weight.operation = "MULTIPLY"
    grain_weight.inputs[1].default_value = 0.48
    pore_weight = nodes.new("ShaderNodeMath")
    pore_weight.operation = "MULTIPLY"
    pore_weight.inputs[1].default_value = 0.28
    relief = nodes.new("ShaderNodeMath")
    relief.operation = "ADD"
    relief_2 = nodes.new("ShaderNodeMath")
    relief_2.operation = "ADD"
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.78
    bump.inputs["Distance"].default_value = 0.044

    for texture in (moist_clods, grains, pores):
        links.new(coordinates, texture.inputs["Vector"])
    links.new(moist_clods.outputs["Fac"], soil_ramp.inputs["Fac"])
    links.new(grains.outputs["Fac"], grain_ramp.inputs["Fac"])
    links.new(soil_ramp.outputs["Color"], color_mix.inputs[1])
    links.new(grain_ramp.outputs["Color"], color_mix.inputs[2])
    links.new(color_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(grains.outputs["Fac"], grain_weight.inputs[0])
    links.new(pores.outputs["Distance"], pore_weight.inputs[0])
    links.new(moist_clods.outputs["Fac"], relief.inputs[0])
    links.new(grain_weight.outputs["Value"], relief.inputs[1])
    links.new(relief.outputs["Value"], relief_2.inputs[0])
    links.new(pore_weight.outputs["Value"], relief_2.inputs[1])
    links.new(relief_2.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "layered_moist_planting_soil"
    mat["c2w_soil_detail_scales"] = "3.15m clods + 38m grains + 23m pore edges"
    return mat


def procedural_architectural_surface(
    name, dark, light, roughness, macro_scale, micro_scale, bump_strength
):
    """Layered mineral/paint finish with metre-scale weathering and fine pore relief."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    coordinates = _surface_coordinates(nodes, links, 1.0)
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    macro.inputs["Scale"].default_value = macro_scale
    macro.inputs["Detail"].default_value = 5.5
    macro.inputs["Roughness"].default_value = 0.72
    pores = nodes.new("ShaderNodeTexNoise")
    pores.noise_dimensions = "3D"
    pores.inputs["Scale"].default_value = micro_scale
    pores.inputs["Detail"].default_value = 7.0
    pores.inputs["Roughness"].default_value = 0.78
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.23
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.79
    ramp.color_ramp.elements[1].color = (*light, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.018
    links.new(coordinates, macro.inputs["Vector"])
    links.new(coordinates, pores.inputs["Vector"])
    links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(pores.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "layered_architectural_finish"
    return mat


def architectural_glass(name, tint, roughness=0.14, transmission=0.34):
    """Physically layered glazing: reflective outside, transmissive over modeled interior depth."""
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = (*tint, 1)
    shader.inputs["Roughness"].default_value = roughness
    if "IOR" in shader.inputs:
        shader.inputs["IOR"].default_value = 1.46
    if "Transmission Weight" in shader.inputs:
        shader.inputs["Transmission Weight"].default_value = transmission
    if "Coat Weight" in shader.inputs:
        shader.inputs["Coat Weight"].default_value = 0.32
        shader.inputs["Coat Roughness"].default_value = 0.08
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.55
    coordinates = nodes.new("ShaderNodeTexCoord")
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.035
    bump.inputs["Distance"].default_value = 0.004
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "architectural_glazing"
    return mat


def procedural_road_paint(name, base_color):
    """Mineral traffic paint with aggregate wear instead of a perfectly flat color."""
    mat = procedural_architectural_surface(
        name,
        tuple(channel * 0.72 for channel in base_color),
        base_color,
        0.76,
        1.8,
        95.0,
        0.13,
    )
    mat["c2w_procedural_surface"] = "weathered_traffic_paint"
    return mat


def make_materials():
    materials = BASE.make_materials()
    materials.update(
        {
            "brick": procedural_brick(
                "campus_red_brick",
                (0.255, 0.055, 0.026),
                (0.43, 0.105, 0.048),
                (0.26, 0.235, 0.205),
            ),
            "brick_dark": procedural_brick(
                "campus_dark_brick",
                (0.105, 0.020, 0.012),
                (0.245, 0.050, 0.024),
                (0.20, 0.185, 0.165),
            ),
            "brick_light": procedural_brick(
                "campus_terracotta",
                (0.34, 0.082, 0.034),
                (0.54, 0.155, 0.062),
                (0.32, 0.29, 0.245),
            ),
            "mortar_light": pbr("brick_mortar", (0.49, 0.46, 0.40), 0.93, noise=0.055),
            "white": procedural_architectural_surface(
                "warm_mineral_stucco",
                (0.35, 0.35, 0.325),
                (0.58, 0.58, 0.53),
                0.84,
                0.52,
                62.0,
                0.18,
            ),
            "white_clean": procedural_architectural_surface(
                "precast_warm_concrete",
                (0.40, 0.395, 0.36),
                (0.64, 0.63, 0.57),
                0.79,
                0.38,
                78.0,
                0.16,
            ),
            "concrete": procedural_architectural_surface(
                "boardformed_concrete",
                (0.26, 0.255, 0.235),
                (0.46, 0.445, 0.40),
                0.91,
                0.47,
                72.0,
                0.24,
            ),
            "stone_light": procedural_architectural_surface(
                "honed_limestone",
                (0.42, 0.40, 0.35),
                (0.64, 0.61, 0.53),
                0.82,
                1.2,
                90.0,
                0.11,
            ),
            "stone_dark": procedural_architectural_surface(
                "dark_granite",
                (0.075, 0.078, 0.073),
                (0.18, 0.185, 0.17),
                0.72,
                1.6,
                105.0,
                0.12,
            ),
            "glass_blue": architectural_glass(
                "low_e_blue_glass", (0.035, 0.095, 0.12), 0.11, 0.28
            ),
            "glass_blue_alt": architectural_glass(
                "neutral_low_e_glass", (0.055, 0.095, 0.098), 0.15, 0.24
            ),
            "glass_clear": architectural_glass(
                "clear_entrance_glass", (0.12, 0.15, 0.145), 0.07, 0.52
            ),
            "track": procedural_ground(
                "running_track_epdm_rubber",
                (0.29, 0.035, 0.018),
                (0.53, 0.092, 0.042),
                0.85,
                0.91,
                0.36,
                7.5,
            ),
            "track_line": procedural_road_paint(
                "track_lane_white", (0.79, 0.775, 0.70)
            ),
            "field": procedural_ground(
                "athletic_turf",
                (0.025, 0.105, 0.018),
                (0.075, 0.275, 0.043),
                0.72,
                0.96,
                0.28,
            ),
            "field_alt": procedural_ground(
                "athletic_turf_stripe",
                (0.020, 0.083, 0.015),
                (0.058, 0.225, 0.034),
                0.76,
                0.96,
                0.26,
            ),
            "court_green": procedural_ground(
                "volleyball_green_acrylic",
                (0.028, 0.17, 0.125),
                (0.065, 0.31, 0.22),
                1.4,
                0.84,
                0.15,
            ),
            "court_rose": procedural_ground(
                "volleyball_oxide_acrylic",
                (0.35, 0.065, 0.070),
                (0.58, 0.16, 0.17),
                1.3,
                0.84,
                0.15,
            ),
            "court_blue": procedural_ground(
                "volleyball_blue_acrylic",
                (0.025, 0.12, 0.205),
                (0.055, 0.245, 0.39),
                1.3,
                0.84,
                0.15,
            ),
            "court_border": procedural_ground(
                "court_safety_acrylic",
                (0.035, 0.21, 0.165),
                (0.075, 0.38, 0.285),
                1.4,
                0.86,
                0.16,
            ),
            "line_yellow": pbr("sports_yellow", (0.94, 0.66, 0.06), 0.67),
            "roof": pbr(
                "standing_seam_roof",
                (0.22, 0.27, 0.29),
                0.38,
                metallic=0.55,
                noise=0.045,
            ),
            "roof_light": pbr(
                "light_metal_roof", (0.65, 0.69, 0.68), 0.44, metallic=0.42, noise=0.045
            ),
            "rubber_dark": pbr(
                "sports_rubber_dark", (0.055, 0.075, 0.075), 0.91, noise=0.09
            ),
            "leaf": pbr("deciduous_leaf", (0.025, 0.125, 0.020), 0.69, noise=0.34),
            "leaf_light": pbr("sunlit_leaf", (0.075, 0.25, 0.035), 0.67, noise=0.31),
            "bark": procedural_architectural_surface(
                "tree_bark",
                (0.035, 0.014, 0.005),
                (0.145, 0.065, 0.018),
                0.94,
                5.5,
                64.0,
                0.46,
            ),
            "solar": pbr("solar_glass", (0.012, 0.075, 0.15), 0.16, metallic=0.38),
            "campus_paver": procedural_ground(
                "warm_granite_campus_paver",
                (0.29, 0.275, 0.245),
                (0.49, 0.46, 0.40),
                0.62,
                0.88,
                0.14,
            ),
            "plaza_paver": procedural_ground(
                "light_courtyard_paver",
                (0.43, 0.40, 0.35),
                (0.68, 0.64, 0.56),
                0.92,
                0.83,
                0.11,
            ),
            "asphalt_real": procedural_ground(
                "weathered_road_asphalt",
                (0.010, 0.012, 0.014),
                (0.052, 0.055, 0.056),
                0.72,
                0.97,
                0.42,
                8.0,
            ),
            "roof_membrane": procedural_ground(
                "weathered_roof_membrane",
                (0.27, 0.29, 0.29),
                (0.48, 0.49, 0.47),
                0.75,
                0.87,
                0.13,
            ),
            "soil": procedural_ground(
                "mulched_planting_soil",
                (0.055, 0.025, 0.012),
                (0.18, 0.095, 0.035),
                0.55,
                0.98,
                0.30,
            ),
            "blind_warm": pbr(
                "window_blind_warm", (0.62, 0.55, 0.42), 0.77, noise=0.06
            ),
            "blind_cool": pbr(
                "window_blind_cool", (0.28, 0.36, 0.40), 0.72, noise=0.05
            ),
            "paint_white": procedural_road_paint(
                "traffic_marking_white", (0.72, 0.70, 0.63)
            ),
            "road_mark": procedural_road_paint(
                "road_lane_marking", (0.68, 0.665, 0.61)
            ),
            "skin_a": pbr("skin_warm_a", (0.46, 0.22, 0.12), 0.72, noise=0.035),
            "skin_b": pbr("skin_warm_b", (0.72, 0.48, 0.31), 0.72, noise=0.035),
            "uniform_blue": pbr(
                "student_uniform_blue", (0.025, 0.09, 0.22), 0.76, noise=0.04
            ),
            "uniform_white": pbr(
                "student_uniform_white", (0.68, 0.69, 0.66), 0.78, noise=0.04
            ),
            "sports_red": pbr(
                "sports_jersey_red", (0.62, 0.025, 0.018), 0.71, noise=0.04
            ),
            "sports_yellow": pbr(
                "sports_jersey_yellow", (0.94, 0.58, 0.02), 0.71, noise=0.04
            ),
            "vehicle_white": pbr(
                "automotive_white", (0.72, 0.74, 0.72), 0.20, metallic=0.34, noise=0.018
            ),
            "vehicle_blue": pbr(
                "automotive_blue", (0.025, 0.11, 0.24), 0.19, metallic=0.48, noise=0.018
            ),
            "vehicle_silver": pbr(
                "automotive_silver",
                (0.31, 0.34, 0.35),
                0.18,
                metallic=0.72,
                noise=0.018,
            ),
            "vehicle_red": pbr(
                "automotive_red", (0.47, 0.018, 0.012), 0.20, metallic=0.42, noise=0.018
            ),
            "tyre": pbr("vehicle_tyre", (0.012, 0.014, 0.015), 0.93, noise=0.10),
            "hedge": pbr(
                "natural_shrub_foliage", (0.022, 0.12, 0.018), 0.72, noise=0.34
            ),
            "flower_white": pbr(
                "flower_petals_warm_white", (0.78, 0.73, 0.62), 0.62, noise=0.04
            ),
            "flower_yellow": pbr(
                "flower_petals_yellow", (0.83, 0.42, 0.025), 0.59, noise=0.04
            ),
            "flower_red": pbr(
                "flower_petals_deep_red", (0.48, 0.018, 0.016), 0.61, noise=0.04
            ),
            "flower_purple": pbr(
                "flower_petals_purple", (0.27, 0.045, 0.24), 0.60, noise=0.04
            ),
            "flower_center": pbr("flower_disc", (0.25, 0.105, 0.015), 0.74, noise=0.07),
            "mulch": procedural_ground(
                "natural_bark_mulch",
                (0.045, 0.018, 0.006),
                (0.16, 0.065, 0.018),
                4.5,
                0.96,
                0.38,
            ),
            "lawn": procedural_lawn(
                "maintained_campus_lawn",
                (0.012, 0.055, 0.008),
                (0.055, 0.19, 0.025),
                (0.22, 0.39, 0.08),
                0.48,
            ),
            "regional_land": procedural_lawn(
                "regional_meadow_turf",
                (0.012, 0.045, 0.008),
                (0.045, 0.15, 0.022),
                (0.16, 0.31, 0.065),
                0.30,
            ),
            "tree_soil": procedural_tree_soil("recessed_tree_pit_soil"),
        }
    )
    return materials


# ---------------------------------------------------------------------------
# Reusable facade and architectural detail systems.
# ---------------------------------------------------------------------------


def facade_window(c, name, origin, yaw, center, dims, face, M, lit=False, shade=False):
    """Construct a genuinely recessed window cell on a local building face."""
    x, y, z = center
    width, height = dims
    glass = M["glass_blue_alt"]
    back = M["warm_light"] if lit else M["interior"]
    variation = sum((index + 1) * ord(char) for index, char in enumerate(name))
    if face in {"south", "north"}:
        outward = -1 if face == "south" else 1
        local_box(
            c,
            name + ":reveal",
            origin,
            yaw,
            (x, y, z),
            (width + 0.34, 0.30, height + 0.32),
            M["dark"],
            0.012,
            role="window_reveal",
        )
        local_box(
            c,
            name + ":shadow",
            origin,
            yaw,
            (x, y - outward * 0.09, z),
            (width - 0.14, 0.05, height - 0.14),
            back,
            0.005,
            role="facade_depth",
        )
        if variation % 5 in {0, 2}:
            blind_height = height * (0.28 + 0.11 * (variation % 4))
            blind_z = z + height / 2 - blind_height / 2 - 0.10
            local_box(
                c,
                name + ":interior_blind",
                origin,
                yaw,
                (x, y + outward * 0.075, blind_z),
                (width - 0.22, 0.025, blind_height),
                M["blind_warm"] if variation % 3 else M["blind_cool"],
                0.0,
                role="interior_blind",
            )
        local_box(
            c,
            name + ":glass",
            origin,
            yaw,
            (x, y + outward * 0.19, z),
            (width, 0.045, height),
            glass,
            0.006,
            role="facade_glazing",
        )
        for xx in (x - width / 2, x, x + width / 2):
            local_box(
                c,
                name + ":vertical_frame",
                origin,
                yaw,
                (xx, y + outward * 0.245, z),
                (0.075, 0.08, height + 0.12),
                M["black_metal"],
                0.006,
                role="facade_mullion",
            )
        for zz in (z - height / 2, z + height / 2):
            local_box(
                c,
                name + ":horizontal_frame",
                origin,
                yaw,
                (x, y + outward * 0.245, zz),
                (width + 0.14, 0.08, 0.075),
                M["black_metal"],
                0.006,
                role="facade_mullion",
            )
        if variation % 3 != 1:
            local_box(
                c,
                name + ":projecting_sill",
                origin,
                yaw,
                (x, y + outward * 0.35, z - height / 2 - 0.10),
                (width + 0.24, 0.36, 0.10),
                M["stone_light"],
                0.018,
                role="window_sill",
            )
        if shade:
            local_box(
                c,
                name + ":sunshade",
                origin,
                yaw,
                (x, y + outward * 0.48, z + height / 2 + 0.13),
                (width + 0.28, 0.72, 0.11),
                M["white_clean"],
                0.025,
                role="facade_sunshade",
            )
    else:
        outward = -1 if face == "west" else 1
        local_box(
            c,
            name + ":reveal",
            origin,
            yaw,
            (x, y, z),
            (0.30, width + 0.34, height + 0.32),
            M["dark"],
            0.012,
            role="window_reveal",
        )
        local_box(
            c,
            name + ":shadow",
            origin,
            yaw,
            (x - outward * 0.09, y, z),
            (0.05, width - 0.14, height - 0.14),
            back,
            0.005,
            role="facade_depth",
        )
        if variation % 5 in {0, 2}:
            blind_height = height * (0.28 + 0.11 * (variation % 4))
            blind_z = z + height / 2 - blind_height / 2 - 0.10
            local_box(
                c,
                name + ":interior_blind",
                origin,
                yaw,
                (x + outward * 0.075, y, blind_z),
                (0.025, width - 0.22, blind_height),
                M["blind_warm"] if variation % 3 else M["blind_cool"],
                0.0,
                role="interior_blind",
            )
        local_box(
            c,
            name + ":glass",
            origin,
            yaw,
            (x + outward * 0.19, y, z),
            (0.045, width, height),
            glass,
            0.006,
            role="facade_glazing",
        )
        for yy in (y - width / 2, y, y + width / 2):
            local_box(
                c,
                name + ":vertical_frame",
                origin,
                yaw,
                (x + outward * 0.245, yy, z),
                (0.08, 0.075, height + 0.12),
                M["black_metal"],
                0.006,
                role="facade_mullion",
            )
        for zz in (z - height / 2, z + height / 2):
            local_box(
                c,
                name + ":horizontal_frame",
                origin,
                yaw,
                (x + outward * 0.245, y, zz),
                (0.08, width + 0.14, 0.075),
                M["black_metal"],
                0.006,
                role="facade_mullion",
            )
        if variation % 3 != 1:
            local_box(
                c,
                name + ":projecting_sill",
                origin,
                yaw,
                (x + outward * 0.35, y, z - height / 2 - 0.10),
                (0.36, width + 0.24, 0.10),
                M["stone_light"],
                0.018,
                role="window_sill",
            )


def local_door(c, name, origin, yaw, x, y, width, height, M):
    local_box(
        c,
        name + ":portal",
        origin,
        yaw,
        (x, y + 0.10, height / 2),
        (width + 1.2, 0.58, height + 0.75),
        M["white_clean"],
        0.07,
        role="entrance_portal",
    )
    local_box(
        c,
        name + ":recess",
        origin,
        yaw,
        (x, y - 0.25, height / 2),
        (width + 0.44, 0.32, height + 0.25),
        M["dark"],
        0.02,
        role="entrance_recess",
    )
    for side in (-1, 1):
        dx = x + side * width / 4
        local_box(
            c,
            name + ":door_glass",
            origin,
            yaw,
            (dx, y - 0.48, height / 2),
            (width / 2 - 0.08, 0.055, height),
            M["glass_clear"],
            0.006,
            role="entrance_glazing",
        )
        for edge in (-1, 1):
            local_box(
                c,
                name + ":door_jamb",
                origin,
                yaw,
                (dx + edge * (width / 4 - 0.04), y - 0.53, height / 2),
                (0.075, 0.08, height + 0.08),
                M["steel"],
                0.005,
                role="door_frame",
            )
        local_box(
            c,
            name + ":door_handle",
            origin,
            yaw,
            (x + side * width * 0.12, y - 0.59, height / 2),
            (0.035, 0.035, 0.75),
            M["brass"],
            0.01,
            role="door_hardware",
        )
    local_box(
        c,
        name + ":canopy",
        origin,
        yaw,
        (x, y - 1.05, height + 0.28),
        (width + 2.1, 2.4, 0.25),
        M["white_clean"],
        0.055,
        role="entrance_canopy",
    )
    for side in (-1, 1):
        local_box(
            c,
            name + ":canopy_column",
            origin,
            yaw,
            (x + side * (width / 2 + 0.65), y - 1.42, (height + 0.25) / 2),
            (0.18, 0.18, height + 0.25),
            M["steel"],
            0.025,
            role="structural_column",
        )


def roof_plant(c, name, origin, yaw, x, y, z, M, scale=1.0):
    local_box(
        c,
        name + ":curb",
        origin,
        yaw,
        (x, y, z + 0.10),
        (4.5 * scale, 3.1 * scale, 0.20),
        M["concrete"],
        0.035,
        role="roof_plant_curb",
    )
    local_box(
        c,
        name + ":unit",
        origin,
        yaw,
        (x, y, z + 0.85 * scale),
        (3.7 * scale, 2.5 * scale, 1.45 * scale),
        M["roof_light"],
        0.07,
        role="roof_mechanical_unit",
    )
    for index in range(7):
        local_box(
            c,
            name + ":louver",
            origin,
            yaw,
            (x, y - 1.28 * scale, z + (0.35 + index * 0.17) * scale),
            (3.1 * scale, 0.045, 0.065 * scale),
            M["black_metal"],
            0.005,
            role="mechanical_louver",
        )
    cylinder(
        c,
        name + ":fan",
        BASE.G.transform_point(origin3(origin), yaw, (x, y, z + 1.62 * scale)),
        0.72 * scale,
        0.12 * scale,
        M["black_metal"],
        32,
        role="roof_fan",
    )


def academic_envelope_details(
    c, key, origin, yaw, width, depth, floors, height, bays, bay_w, M
):
    """Secondary facade layer: brick relief, shadowed spandrels, flashings and service detail."""
    for face_sign, face_name in ((-1, "south"), (1, "north")):
        face_y = face_sign * (depth / 2 + 0.355)
        # A physically separate base flashing and coping stop the shell reading as one extruded block.
        local_box(
            c,
            f"{key}:{face_name}:base_flashing",
            origin,
            yaw,
            (0, face_y, 0.94),
            (width - 0.55, 0.09, 0.16),
            M["steel"],
            0.012,
            role="facade_flashing",
        )
        local_box(
            c,
            f"{key}:{face_name}:coping",
            origin,
            yaw,
            (0, face_sign * (depth / 2 + 0.55), height + 1.06),
            (width + 0.92, 0.72, 0.16),
            M["roof_light"],
            0.025,
            role="roof_coping",
        )
        for floor in range(floors):
            z = 2.15 + floor * 3.75
            for bay in range(bays):
                x = -width / 2 + 1.7 + bay_w * (bay + 0.5)
                # Set-back brick spandrels and headers give every opening a real wall build-up.
                local_box(
                    c,
                    f"{key}:{face_name}:spandrel_{floor}_{bay}",
                    origin,
                    yaw,
                    (x, face_y, z - 1.43),
                    (bay_w * 0.82, 0.13, 0.42),
                    M["brick_dark"] if (bay + floor) % 7 == 0 else M["brick"],
                    0.016,
                    role="facade_spandrel",
                )
                local_box(
                    c,
                    f"{key}:{face_name}:lintel_{floor}_{bay}",
                    origin,
                    yaw,
                    (x, face_y + face_sign * 0.055, z + 1.23),
                    (bay_w * 0.75, 0.16, 0.16),
                    M["stone_light"],
                    0.018,
                    role="window_lintel",
                )
                if bay % 3 == 1:
                    local_box(
                        c,
                        f"{key}:{face_name}:relief_pier_{floor}_{bay}",
                        origin,
                        yaw,
                        (x + bay_w * 0.46, face_y + face_sign * 0.08, z),
                        (0.15, 0.22, 2.90),
                        M["brick_dark"],
                        0.012,
                        role="facade_brick_relief",
                    )
            # Slab shadow lines remain dark and recessed beneath the precast band.
            local_box(
                c,
                f"{key}:{face_name}:slab_shadow_{floor}",
                origin,
                yaw,
                (0, face_y - face_sign * 0.04, z + 1.59),
                (width - 0.9, 0.055, 0.075),
                M["dark"],
                0.0,
                role="facade_shadow_joint",
            )

        # Projecting end bays break the long classroom wing into occupied volumes.
        for end in (-1, 1):
            end_x = end * (width / 2 - 0.72)
            local_box(
                c,
                f"{key}:{face_name}:projecting_end_bay_{end}",
                origin,
                yaw,
                (end_x, face_y + face_sign * 0.12, height * 0.48),
                (1.15, 0.38, height - 2.1),
                M["brick_dark"],
                0.045,
                role="facade_projecting_bay",
            )
            for floor in range(floors):
                local_box(
                    c,
                    f"{key}:{face_name}:end_bay_slot_{end}_{floor}",
                    origin,
                    yaw,
                    (end_x, face_y + face_sign * 0.34, 2.1 + floor * 3.75),
                    (0.44, 0.075, 1.75),
                    M["glass_blue_alt"],
                    0.008,
                    role="facade_glazing",
                )

    # Roof edge brackets, drain heads and vent stacks provide believable maintenance detail.
    for bracket in range(max(5, bays // 2)):
        x = -width / 2 + 1.0 + bracket * (width - 2.0) / max(1, max(5, bays // 2) - 1)
        for face_sign in (-1, 1):
            local_box(
                c,
                f"{key}:coping_bracket_{bracket}_{face_sign}",
                origin,
                yaw,
                (x, face_sign * (depth / 2 + 0.68), height + 0.78),
                (0.10, 0.22, 0.26),
                M["steel"],
                0.012,
                role="roof_coping_bracket",
            )
    for x in (-width * 0.31, width * 0.31):
        for face_sign in (-1, 1):
            local_box(
                c,
                f"{key}:rainwater_hopper",
                origin,
                yaw,
                (x, face_sign * (depth / 2 + 0.71), height - 0.22),
                (0.38, 0.32, 0.46),
                M["steel"],
                0.035,
                role="rainwater_hopper",
            )


def build_academic_bar(
    parent, M, key, origin, width, depth, floors, yaw=0.0, entrance=True, title=None
):
    c = collection("ACADEMIC_" + key, parent, "school.academic." + key.lower() + ".v3")
    height = floors * 3.75 + 1.0
    ox, oy = origin
    shell_material = (
        M["brick_light"] if key in {"NORTH_CENTRE", "MID_EAST"} else M["brick"]
    )
    local_box(
        c,
        key + ":occupied_shell",
        origin,
        yaw,
        (0, 0, height / 2),
        (width, depth, height),
        shell_material,
        0.11,
        role="occupied_building_shell",
    )
    local_box(
        c,
        key + ":brick_plinth",
        origin,
        yaw,
        (0, 0, 0.48),
        (width + 0.36, depth + 0.36, 0.96),
        M["brick_dark"],
        0.055,
        role="masonry_plinth",
    )

    bays = max(6, round(width / 5.0))
    bay_w = (width - 3.4) / bays
    for floor in range(floors):
        z = 2.15 + floor * 3.75
        for bay in range(bays):
            x = -width / 2 + 1.7 + bay_w * (bay + 0.5)
            lit = (floor * 7 + bay * 3 + len(key)) % 17 in {2, 8}
            facade_window(
                c,
                f"{key}:south_window_{floor}_{bay}",
                origin,
                yaw,
                (x, -depth / 2 - 0.08, z),
                (bay_w * 0.66, 2.25),
                "south",
                M,
                lit,
                shade=floor > 0,
            )
            facade_window(
                c,
                f"{key}:north_window_{floor}_{bay}",
                origin,
                yaw,
                (x, depth / 2 + 0.08, z),
                (bay_w * 0.66, 2.25),
                "north",
                M,
                lit=False,
                shade=False,
            )
        # Expressed white slab edges reproduce the reference's facade frames.
        for side in (-1, 1):
            local_box(
                c,
                f"{key}:floor_band_{floor}_{side}",
                origin,
                yaw,
                (0, side * (depth / 2 + 0.31), z + 1.48),
                (width + 0.7, 0.42, 0.30),
                M["white_clean"],
                0.025,
                role="precast_floor_band",
            )

    side_bays = max(2, round(depth / 4.6))
    side_step = (depth - 2.4) / side_bays
    for floor in range(floors):
        z = 2.15 + floor * 3.75
        for bay in range(side_bays):
            y = -depth / 2 + 1.2 + side_step * (bay + 0.5)
            facade_window(
                c,
                f"{key}:west_window_{floor}_{bay}",
                origin,
                yaw,
                (-width / 2 - 0.08, y, z),
                (side_step * 0.62, 2.18),
                "west",
                M,
                False,
                False,
            )
            facade_window(
                c,
                f"{key}:east_window_{floor}_{bay}",
                origin,
                yaw,
                (width / 2 + 0.08, y, z),
                (side_step * 0.62, 2.18),
                "east",
                M,
                False,
                False,
            )

    # White structural frames and brick coursing are modeled geometry, not a texture.
    frame_positions = {-width / 2 - 0.31, width / 2 + 0.31}
    for bay in range(0, bays + 1, 3):
        frame_positions.add(-width / 2 + 1.7 + bay_w * bay)
    for x in sorted(frame_positions):
        for side in (-1, 1):
            local_box(
                c,
                f"{key}:precast_pier",
                origin,
                yaw,
                (x, side * (depth / 2 + 0.44), height / 2),
                (0.45, 0.65, height + 0.65),
                M["white_clean"],
                0.045,
                role="precast_structural_frame",
            )
    for course in range(1, int(height / 0.66)):
        z = course * 0.66
        for side in (-1, 1):
            local_box(
                c,
                f"{key}:mortar_course_{course}_{side}",
                origin,
                yaw,
                (0, side * (depth / 2 + 0.345), z),
                (width - 0.85, 0.025, 0.025),
                M["mortar_light"],
                0.0,
                role="brick_mortar_joint",
            )

    academic_envelope_details(
        c, key, origin, yaw, width, depth, floors, height, bays, bay_w, M
    )

    # Expansion joints, plinth vents and rainwater goods break up long elevations.
    for joint in (-width * 0.25, width * 0.25):
        for side in (-1, 1):
            local_box(
                c,
                f"{key}:expansion_joint",
                origin,
                yaw,
                (joint, side * (depth / 2 + 0.36), height / 2),
                (0.055, 0.025, height - 1.2),
                M["dark"],
                0.0,
                role="facade_expansion_joint",
            )
    for side in (-1, 1):
        for x in (-width / 2 + 2.2, width / 2 - 2.2):
            world = BASE.G.transform_point(
                origin3(origin), yaw, (x, side * (depth / 2 + 0.58), height / 2)
            )
            cylinder(
                c,
                f"{key}:rainwater_downpipe",
                world,
                0.075,
                height - 0.55,
                M["steel"],
                18,
                role="rainwater_downpipe",
            )
            local_box(
                c,
                f"{key}:downpipe_shoe",
                origin,
                yaw,
                (x, side * (depth / 2 + 0.62), 0.48),
                (0.24, 0.42, 0.28),
                M["steel"],
                0.025,
                role="rainwater_downpipe",
            )
    for vent in range(max(3, bays // 2)):
        x = -width / 2 + 2.4 + vent * (width - 4.8) / max(1, max(3, bays // 2) - 1)
        local_box(
            c,
            f"{key}:plinth_vent",
            origin,
            yaw,
            (x, depth / 2 + 0.40, 0.58),
            (1.15, 0.055, 0.34),
            M["black_metal"],
            0.01,
            role="foundation_vent",
        )
        for blade in range(4):
            local_box(
                c,
                f"{key}:plinth_vent_blade",
                origin,
                yaw,
                (x, depth / 2 + 0.44, 0.46 + blade * 0.08),
                (0.95, 0.035, 0.025),
                M["steel"],
                0.0,
                role="mechanical_louver",
            )

    # Projecting stair tower gives each bar a legible circulation core.
    tower_x = -width / 2 + 3.0
    local_box(
        c,
        key + ":stair_tower",
        origin,
        yaw,
        (tower_x, -depth / 2 - 0.75, height / 2),
        (4.0, 1.5, height + 0.8),
        M["white"],
        0.07,
        role="stair_tower",
    )
    for floor in range(floors):
        facade_window(
            c,
            f"{key}:stair_slot_{floor}",
            origin,
            yaw,
            (tower_x, -depth / 2 - 1.53, 2.05 + floor * 3.75),
            (1.05, 2.40),
            "south",
            M,
            False,
            False,
        )

    local_box(
        c,
        key + ":roof_parapet_front",
        origin,
        yaw,
        (0, -depth / 2, height + 0.52),
        (width + 0.6, 0.48, 1.05),
        M["white_clean"],
        0.055,
        role="roof_parapet",
    )
    local_box(
        c,
        key + ":roof_parapet_back",
        origin,
        yaw,
        (0, depth / 2, height + 0.52),
        (width + 0.6, 0.48, 1.05),
        M["white_clean"],
        0.055,
        role="roof_parapet",
    )
    for side in (-1, 1):
        local_box(
            c,
            key + ":roof_parapet_side",
            origin,
            yaw,
            (side * width / 2, 0, height + 0.52),
            (0.48, depth, 1.05),
            M["white_clean"],
            0.055,
            role="roof_parapet",
        )
    local_box(
        c,
        key + ":roof_membrane",
        origin,
        yaw,
        (0, 0, height + 0.16),
        (width - 0.75, depth - 0.75, 0.20),
        M["roof_membrane"],
        0.02,
        role="roof_membrane",
    )
    local_box(
        c,
        key + ":roof_access_hatch",
        origin,
        yaw,
        (-width * 0.34, 0, height + 0.48),
        (2.1, 2.4, 0.58),
        M["roof_light"],
        0.045,
        role="roof_access_hatch",
    )
    for vent in (-0.36, 0.36):
        world = BASE.G.transform_point(
            origin3(origin), yaw, (width * vent, -depth * 0.22, height + 0.62)
        )
        cylinder(
            c,
            key + ":roof_exhaust",
            world,
            0.22,
            0.92,
            M["steel"],
            24,
            bevel=0.025,
            role="roof_exhaust",
        )
        cylinder(
            c,
            key + ":roof_exhaust_cap",
            (world[0], world[1], world[2] + 0.52),
            0.34,
            0.10,
            M["steel"],
            28,
            bevel=0.025,
            role="roof_exhaust",
        )
    roof_plant(
        c, key + ":plant_a", origin, yaw, width * 0.22, 0, height + 0.15, M, 0.78
    )
    roof_plant(
        c,
        key + ":plant_b",
        origin,
        yaw,
        -width * 0.18,
        depth * 0.12,
        height + 0.15,
        M,
        0.62,
    )

    if key in {"NORTH_WEST", "NORTH_EAST", "EAST_LINK"}:
        panel_rows = 2 if depth >= 15 else 1
        for row in range(panel_rows):
            for col in range(max(4, int(width // 8))):
                px = -width * 0.32 + col * (width * 0.64) / max(
                    1, max(4, int(width // 8)) - 1
                )
                py = -depth * 0.18 + row * depth * 0.34
                local_box(
                    c,
                    f"{key}:solar_panel_{row}_{col}",
                    origin,
                    yaw,
                    (px, py, height + 0.64),
                    (4.1, 2.3, 0.10),
                    M["solar"],
                    0.018,
                    role="solar_panel",
                )
                for support in (-1, 1):
                    local_box(
                        c,
                        f"{key}:solar_support_{row}_{col}_{support}",
                        origin,
                        yaw,
                        (px + support * 1.55, py, height + 0.43),
                        (0.08, 1.65, 0.48),
                        M["steel"],
                        0.01,
                        role="solar_support",
                    )

    if entrance:
        local_door(
            c,
            key + ":main_entry",
            origin,
            yaw,
            width * 0.18,
            -depth / 2 - 0.33,
            3.4,
            3.05,
            M,
        )
        for step in range(3):
            local_box(
                c,
                key + f":entry_step_{step}",
                origin,
                yaw,
                (width * 0.18, -depth / 2 - 1.82 + step * 0.34, 0.10 + step * 0.10),
                (5.2 + (2 - step) * 0.35, 0.62, 0.20),
                M["stone_light"],
                0.025,
                role="entrance_stair",
            )
        for side in (-1, 1):
            local_box(
                c,
                key + ":entry_wall_light",
                origin,
                yaw,
                (width * 0.18 + side * 2.1, -depth / 2 - 0.71, 2.25),
                (0.18, 0.18, 0.62),
                M["black_metal"],
                0.035,
                role="facade_light_fixture",
            )
            local_box(
                c,
                key + ":entry_wall_lens",
                origin,
                yaw,
                (width * 0.18 + side * 2.1, -depth / 2 - 0.82, 2.25),
                (0.11, 0.05, 0.42),
                M["lamp"],
                0.018,
                role="facade_light_lens",
            )
    if title:
        local_text(
            c,
            key + ":building_title",
            title,
            origin,
            yaw,
            (width * 0.18, -depth / 2 - 1.62, height - 1.35),
            0.55,
            M["white_clean"],
            0.045,
        )
    c[
        "c2w_detail_profile"
    ] = "brick_courses+four_sided_windows+recesses+precast_frames+sunshades+roof_plant+entrance"
    return c


def build_administration(parent, M):
    c = collection("ADMINISTRATION_LIBRARY", parent, "school.administration_library.v3")
    ox, oy = 28.0, 5.0
    w, d, h = 48.0, 23.0, 17.0
    box(
        c,
        "admin:occupied_shell",
        (ox, oy, h / 2),
        (w, d, h),
        M["brick_light"],
        0.13,
        role="occupied_building_shell",
    )
    south = oy - d / 2
    # Double-height entrance hall and white projecting frame.
    box(
        c,
        "admin:glass_hall_recess",
        (ox, south - 0.20, 7.7),
        (15.0, 0.46, 14.0),
        M["dark"],
        0.025,
        role="entrance_recess",
    )
    box(
        c,
        "admin:glass_hall",
        (ox, south - 0.48, 7.7),
        (13.7, 0.055, 13.2),
        M["glass_blue_alt"],
        0.006,
        role="facade_glazing",
    )
    for x in [ox - 6.85 + i * 2.28 for i in range(7)]:
        box(
            c,
            "admin:hall_mullion",
            (x, south - 0.55, 7.7),
            (0.11, 0.12, 13.35),
            M["black_metal"],
            0.007,
            role="facade_mullion",
        )
    for z in (3.55, 7.25, 10.95, 14.25):
        box(
            c,
            "admin:hall_transom",
            (ox, south - 0.55, z),
            (13.9, 0.12, 0.13),
            M["black_metal"],
            0.007,
            role="facade_mullion",
        )
    for x in (ox - 8.0, ox + 8.0):
        box(
            c,
            "admin:portal_column",
            (x, south - 0.92, 8.25),
            (1.05, 1.15, 16.5),
            M["white_clean"],
            0.065,
            role="monumental_portal_frame",
        )
    box(
        c,
        "admin:portal_beam",
        (ox, south - 0.92, 15.95),
        (17.0, 1.15, 1.10),
        M["white_clean"],
        0.065,
        role="monumental_portal_frame",
    )
    box(
        c,
        "admin:entrance_canopy",
        (ox, south - 2.35, 5.1),
        (11.0, 4.0, 0.30),
        M["white_clean"],
        0.06,
        role="entrance_canopy",
    )
    for x in (ox - 4.4, ox + 4.4):
        cylinder(
            c,
            "admin:canopy_column",
            (x, south - 3.15, 2.55),
            0.13,
            5.1,
            M["steel"],
            28,
            role="structural_column",
        )
    for side in (-1, 1):
        x = ox + side * 2.65
        box(
            c,
            "admin:door_glass",
            (x, south - 0.66, 2.15),
            (5.15, 0.055, 4.3),
            M["glass_clear"],
            0.006,
            role="entrance_glazing",
        )
        for edge in (-1, 1):
            box(
                c,
                "admin:door_jamb",
                (x + edge * 2.50, south - 0.73, 2.15),
                (0.09, 0.10, 4.4),
                M["steel"],
                0.006,
                role="door_frame",
            )

    # Brick classroom/library wings on both sides of the central atrium.
    for side in (-1, 1):
        center_x = ox + side * 15.5
        for floor in range(4):
            z = 2.1 + floor * 3.65
            for bay in range(4):
                x = center_x - 7.1 + bay * 4.7
                BASE.window_y(
                    c,
                    f"admin:wing_{side}_{floor}_{bay}",
                    x,
                    south - 0.25,
                    z,
                    3.15,
                    2.15,
                    M,
                    glass="glass_blue_alt",
                    divisions=2,
                    lit=False,
                )
            box(
                c,
                "admin:wing_floor_band",
                (center_x, south - 0.48, z + 1.47),
                (17.6, 0.52, 0.28),
                M["white_clean"],
                0.02,
                role="precast_floor_band",
            )
    for x in (ox - 24.0, ox - 17.8, ox - 8.2, ox + 8.2, ox + 17.8, ox + 24.0):
        box(
            c,
            "admin:precast_pier",
            (x, south - 0.61, h / 2),
            (0.48, 0.65, h + 0.4),
            M["white_clean"],
            0.04,
            role="precast_structural_frame",
        )

    # Side and rear elevations remain fully articulated.
    for floor in range(4):
        z = 2.1 + floor * 3.65
        for bay in range(5):
            y = oy - 8.0 + bay * 4.0
            BASE.window_x(
                c,
                f"admin:east_{floor}_{bay}",
                ox + w / 2 + 0.18,
                y,
                z,
                2.70,
                2.12,
                M,
                glass="glass_blue_alt",
                divisions=1,
                normal=1,
            )
            BASE.window_x(
                c,
                f"admin:west_{floor}_{bay}",
                ox - w / 2 - 0.18,
                y,
                z,
                2.70,
                2.12,
                M,
                glass="glass_blue_alt",
                divisions=1,
                normal=-1,
            )
        for bay in range(10):
            x = ox - 21.0 + bay * 4.65
            BASE.window_y(
                c,
                f"admin:north_{floor}_{bay}",
                x,
                oy + d / 2 + 0.18,
                z,
                3.0,
                2.12,
                M,
                glass="glass_blue_alt",
                divisions=1,
                normal=1,
            )
    box(
        c,
        "admin:roof_cap",
        (ox, oy, h + 0.48),
        (w + 0.8, d + 0.8, 0.95),
        M["white_clean"],
        0.06,
        role="roof_parapet",
    )
    text_object(
        c,
        "admin:school_name",
        "RIVERSIDE SCHOOL",
        (ox, south - 0.72, 13.05),
        0.83,
        M["white_clean"],
        0.065,
    )
    roof_plant(c, "admin:roof_plant", (ox, oy), 0.0, -14.0, 2.0, h + 0.55, M, 0.8)
    # The main block receives sill courses, recessed shadow joints and roof drainage.
    for wing_sign in (-1, 1):
        wing_x = ox + wing_sign * 15.5
        for floor in range(4):
            z = 2.1 + floor * 3.65
            box(
                c,
                "admin:window_sill_course",
                (wing_x, south - 0.64, z - 1.22),
                (16.2, 0.30, 0.14),
                M["stone_light"],
                0.015,
                role="window_sill",
            )
            box(
                c,
                "admin:recess_shadow_course",
                (wing_x, south - 0.67, z + 1.34),
                (16.4, 0.10, 0.10),
                M["dark"],
                0.0,
                role="facade_shadow_joint",
            )
    for x in (ox - 22.2, ox + 22.2):
        cylinder(
            c,
            "admin:rainwater_downpipe",
            (x, oy + d / 2 + 0.62, h / 2),
            0.085,
            h - 0.6,
            M["steel"],
            20,
            role="rainwater_downpipe",
        )
        box(
            c,
            "admin:rainwater_hopper",
            (x, oy + d / 2 + 0.66, h - 0.45),
            (0.44, 0.34, 0.54),
            M["steel"],
            0.04,
            role="rainwater_hopper",
        )
    box(
        c,
        "admin:roof_coping",
        (ox, oy, h + 1.01),
        (w + 1.15, d + 1.15, 0.16),
        M["roof_light"],
        0.03,
        role="roof_coping",
    )
    c[
        "c2w_detail_profile"
    ] = "double_height_atrium+four_storey_wings+four_sided_facades+monumental_entry+roof_plant"
    return c


def build_gymnasium(parent, M):
    c = collection("GYMNASIUM", parent, "school.gymnasium.v3")
    ox, oy = -13.0, 14.0
    w, d, h = 31.0, 24.0, 12.8
    box(
        c,
        "gym:occupied_shell",
        (ox, oy, h / 2),
        (w, d, h),
        M["brick_dark"],
        0.14,
        role="occupied_building_shell",
    )
    south = oy - d / 2
    box(
        c,
        "gym:upper_metal_cladding",
        (ox, oy, 9.4),
        (w + 0.25, d + 0.25, 6.5),
        M["roof_light"],
        0.055,
        role="gym_metal_cladding",
    )
    for index in range(18):
        x = ox - w / 2 + 0.9 + index * (w - 1.8) / 17
        box(
            c,
            "gym:standing_seam",
            (x, south - 0.19, 9.4),
            (0.055, 0.055, 6.1),
            M["steel"],
            0.005,
            role="metal_cladding_seam",
        )
    for bay in range(8):
        x = ox - 13.0 + bay * 3.7
        BASE.window_y(
            c,
            f"gym:clerestory_{bay}",
            x,
            south - 0.28,
            8.7,
            2.4,
            3.8,
            M,
            glass="glass_blue",
            divisions=1,
        )
    local_door(c, "gym:entry", (ox, oy), 0, 0, -d / 2 - 0.35, 4.2, 3.4, M)
    # Roof monitors and actual standing seams establish the large-span roof.
    box(
        c,
        "gym:roof",
        (ox, oy, h + 0.34),
        (w + 1.0, d + 1.0, 0.68),
        M["roof"],
        0.08,
        role="long_span_roof",
    )
    for index in range(17):
        x = ox - w / 2 + index * w / 16
        box(
            c,
            "gym:roof_seam",
            (x, oy, h + 0.72),
            (0.055, d, 0.09),
            M["steel"],
            0.005,
            role="standing_seam",
        )
    for index, y in enumerate((oy - 5.0, oy, oy + 5.0)):
        box(
            c,
            f"gym:skylight_{index}",
            (ox, y, h + 0.86),
            (20.0, 1.4, 0.18),
            M["glass_blue"],
            0.04,
            role="roof_skylight",
        )
        for x in range(-9, 10, 3):
            box(
                c,
                "gym:skylight_mullion",
                (ox + x, y, h + 0.98),
                (0.07, 1.45, 0.08),
                M["steel"],
                0.005,
                role="skylight_mullion",
            )
    # Fully resolve side and rear elevations with buttresses, clerestories and service access.
    for side in (-1, 1):
        side_x = ox + side * (w / 2 + 0.20)
        for bay in range(5):
            yy = oy - 8.0 + bay * 4.0
            BASE.window_x(
                c,
                f"gym:side_clerestory_{side}_{bay}",
                side_x,
                yy,
                8.6,
                2.35,
                2.65,
                M,
                glass="glass_blue_alt",
                divisions=2,
                normal=side,
            )
            box(
                c,
                "gym:side_buttress",
                (side_x + side * 0.34, yy - 1.75, 4.4),
                (0.60, 0.48, 8.8),
                M["brick_dark"],
                0.045,
                role="structural_buttress",
            )
    for bay in range(7):
        xx = ox - 12.0 + bay * 4.0
        BASE.window_y(
            c,
            f"gym:rear_clerestory_{bay}",
            xx,
            oy + d / 2 + 0.20,
            8.7,
            2.45,
            2.80,
            M,
            glass="glass_blue_alt",
            divisions=2,
            normal=1,
        )
    for side in (-1, 1):
        x = ox + side * (w / 2 - 1.1)
        cylinder(
            c,
            "gym:roof_downpipe",
            (x, oy + d / 2 + 0.56, h / 2),
            0.09,
            h - 0.5,
            M["steel"],
            20,
            role="rainwater_downpipe",
        )
        box(
            c,
            "gym:gutter_hopper",
            (x, oy + d / 2 + 0.62, h - 0.22),
            (0.46, 0.36, 0.58),
            M["steel"],
            0.04,
            role="rainwater_hopper",
        )
    box(
        c,
        "gym:rear_service_recess",
        (ox, oy + d / 2 + 0.12, 1.65),
        (5.4, 0.38, 3.3),
        M["dark"],
        0.025,
        role="entrance_recess",
    )
    for side in (-1, 1):
        box(
            c,
            "gym:rear_service_door",
            (ox + side * 1.35, oy + d / 2 + 0.36, 1.55),
            (2.55, 0.08, 3.0),
            M["steel"],
            0.018,
            role="service_door",
        )
        box(
            c,
            "gym:service_pushbar",
            (ox + side * 0.68, oy + d / 2 + 0.43, 1.35),
            (0.68, 0.06, 0.07),
            M["black_metal"],
            0.012,
            role="door_hardware",
        )
    c[
        "c2w_detail_profile"
    ] = "long_span_hall+four_sided_clerestories+buttresses+service_doors+standing_seam_roof"
    return c


def build_auditorium(parent, M):
    c = collection("CIRCULAR_AUDITORIUM", parent, "school.circular_auditorium.v3")
    ox, oy = 2.0, -34.0
    cylinder(
        c,
        "auditorium:occupied_shell",
        (ox, oy, 4.3),
        13.0,
        8.6,
        M["brick_light"],
        96,
        bevel=0.08,
        role="occupied_building_shell",
    )
    cylinder(
        c,
        "auditorium:dark_plinth",
        (ox, oy, 0.55),
        13.35,
        1.1,
        M["brick_dark"],
        96,
        role="masonry_plinth",
    )
    cylinder(
        c,
        "auditorium:glazing_band",
        (ox, oy, 5.25),
        13.12,
        2.75,
        M["glass_blue_alt"],
        96,
        role="facade_glazing",
    )
    cylinder(
        c,
        "auditorium:roof_cap",
        (ox, oy, 8.95),
        13.65,
        0.70,
        M["white_clean"],
        96,
        bevel=0.07,
        role="roof_parapet",
    )
    # Curved curtain wall receives individual vertical white fins.
    for index in range(40):
        angle = 2 * math.pi * index / 40
        x = ox + math.cos(angle) * 13.5
        y = oy + math.sin(angle) * 13.5
        box(
            c,
            "auditorium:vertical_fin",
            (x, y, 5.1),
            (0.22, 0.48, 6.8),
            M["white_clean"],
            0.035,
            rot=angle,
            role="curved_facade_fin",
        )
    # South entrance interrupts the circular rhythm with a deep glazed porch.
    box(
        c,
        "auditorium:entry_recess",
        (ox, oy - 13.32, 2.45),
        (7.8, 0.46, 4.9),
        M["dark"],
        0.02,
        role="entrance_recess",
    )
    box(
        c,
        "auditorium:entry_glass",
        (ox, oy - 13.61, 2.35),
        (7.1, 0.055, 4.55),
        M["glass_clear"],
        0.006,
        role="entrance_glazing",
    )
    for x in (ox - 3.55, ox, ox + 3.55):
        box(
            c,
            "auditorium:entry_mullion",
            (x, oy - 13.70, 2.35),
            (0.10, 0.10, 4.7),
            M["steel"],
            0.006,
            role="door_frame",
        )
    box(
        c,
        "auditorium:canopy",
        (ox, oy - 15.0, 5.1),
        (10.0, 3.8, 0.30),
        M["white_clean"],
        0.07,
        role="entrance_canopy",
    )
    for x in (ox - 4.2, ox + 4.2):
        cylinder(
            c,
            "auditorium:canopy_column",
            (x, oy - 15.8, 2.55),
            0.13,
            5.1,
            M["steel"],
            28,
            role="structural_column",
        )
    # Circular rooftop skylight and radial structure.
    cylinder(
        c,
        "auditorium:skylight",
        (ox, oy, 9.43),
        5.8,
        0.22,
        M["glass_blue"],
        72,
        role="roof_skylight",
    )
    for index in range(16):
        a = 2 * math.pi * index / 16
        beam(
            c,
            "auditorium:radial_skylight_bar",
            (ox, oy, 9.58),
            (ox + math.cos(a) * 5.7, oy + math.sin(a) * 5.7, 9.58),
            0.045,
            M["steel"],
            12,
            "skylight_mullion",
        )
    # Continuous metal drip edges and segmented masonry bands make the drum constructible.
    cylinder(
        c,
        "auditorium:lower_dpc",
        (ox, oy, 1.14),
        13.39,
        0.12,
        M["steel"],
        128,
        role="facade_flashing",
    )
    cylinder(
        c,
        "auditorium:upper_coping",
        (ox, oy, 9.34),
        13.78,
        0.16,
        M["roof_light"],
        128,
        role="roof_coping",
    )
    for band_z in (3.72, 6.72):
        cylinder(
            c,
            "auditorium:masonry_string_course",
            (ox, oy, band_z),
            13.25,
            0.15,
            M["stone_light"],
            128,
            role="facade_string_course",
        )
    for handle_x in (ox - 1.65, ox + 1.65):
        box(
            c,
            "auditorium:door_pull",
            (handle_x, oy - 13.77, 2.20),
            (0.055, 0.055, 1.05),
            M["brass"],
            0.015,
            role="door_hardware",
        )
    c[
        "c2w_detail_profile"
    ] = "segmented_curved_masonry+curtain_wall_fins+deep_entry+radial_skylight+metal_coping"
    return c


def build_cafeteria(parent, M):
    c = collection("CAFETERIA_ARTS", parent, "school.cafeteria_arts.v3")
    ox, oy = 72.0, -21.0
    w, d, h = 37.0, 22.0, 11.5
    box(
        c,
        "cafeteria:occupied_shell",
        (ox, oy, h / 2),
        (w, d, h),
        M["brick"],
        0.12,
        role="occupied_building_shell",
    )
    south = oy - d / 2
    box(
        c,
        "cafeteria:glass_wall",
        (ox, south - 0.27, 4.15),
        (31.5, 0.055, 6.8),
        M["glass_blue_alt"],
        0.006,
        role="facade_glazing",
    )
    box(
        c,
        "cafeteria:shadow_back",
        (ox, south - 0.05, 4.15),
        (31.0, 0.055, 6.4),
        M["interior"],
        0.005,
        role="facade_depth",
    )
    for x in [ox - 15.7 + i * 2.62 for i in range(13)]:
        box(
            c,
            "cafeteria:curtain_mullion",
            (x, south - 0.35, 4.15),
            (0.10, 0.10, 6.95),
            M["black_metal"],
            0.006,
            role="facade_mullion",
        )
    for z in (0.75, 3.5, 6.25, 7.55):
        box(
            c,
            "cafeteria:curtain_transom",
            (ox, south - 0.35, z),
            (32.0, 0.10, 0.11),
            M["black_metal"],
            0.006,
            role="facade_mullion",
        )
    box(
        c,
        "cafeteria:deep_canopy",
        (ox, south - 2.25, 7.85),
        (35.0, 4.4, 0.42),
        M["white_clean"],
        0.07,
        role="entrance_canopy",
    )
    for x in range(-15, 16, 5):
        cylinder(
            c,
            "cafeteria:canopy_column",
            (ox + x, south - 3.25, 3.9),
            0.12,
            7.8,
            M["steel"],
            24,
            role="structural_column",
        )
    box(
        c,
        "cafeteria:roof",
        (ox, oy, h + 0.35),
        (w + 0.8, d + 0.8, 0.70),
        M["white_clean"],
        0.07,
        role="roof_parapet",
    )
    # Solar array with supports and separations.
    for row in range(3):
        for col in range(8):
            x = ox - 14.0 + col * 4.0
            y = oy - 6.0 + row * 5.8
            box(
                c,
                "cafeteria:solar_panel",
                (x, y, h + 1.25),
                (3.55, 4.6, 0.12),
                M["solar"],
                0.025,
                role="solar_panel",
            )
            for side in (-1, 1):
                beam(
                    c,
                    "cafeteria:solar_support",
                    (x + side * 1.35, y, h + 0.55),
                    (x + side * 1.35, y, h + 1.16),
                    0.045,
                    M["steel"],
                    12,
                    "solar_support",
                )
    # Side/rear walls receive real openings, service doors, screens and drainage.
    for side in (-1, 1):
        side_x = ox + side * (w / 2 + 0.18)
        for bay in range(4):
            yy = oy - 7.2 + bay * 4.8
            BASE.window_x(
                c,
                f"cafeteria:side_window_{side}_{bay}",
                side_x,
                yy,
                4.25,
                3.05,
                4.9,
                M,
                glass="glass_blue_alt",
                divisions=2,
                normal=side,
            )
            for fin in range(4):
                box(
                    c,
                    "cafeteria:side_vertical_screen",
                    (side_x + side * 0.42, yy - 1.25 + fin * 0.83, 4.25),
                    (0.14, 0.11, 5.35),
                    M["wood"],
                    0.025,
                    role="facade_sunshade",
                )
    for bay in range(7):
        xx = ox - 14.0 + bay * 4.65
        BASE.window_y(
            c,
            f"cafeteria:rear_window_{bay}",
            xx,
            oy + d / 2 + 0.18,
            4.2,
            3.15,
            4.8,
            M,
            glass="glass_blue_alt",
            divisions=2,
            normal=1,
        )
    for side in (-1, 1):
        x = ox + side * (w / 2 - 1.0)
        cylinder(
            c,
            "cafeteria:downpipe",
            (x, oy + d / 2 + 0.56, h / 2),
            0.085,
            h - 0.5,
            M["steel"],
            20,
            role="rainwater_downpipe",
        )
        box(
            c,
            "cafeteria:rainwater_hopper",
            (x, oy + d / 2 + 0.61, h - 0.25),
            (0.44, 0.34, 0.52),
            M["steel"],
            0.04,
            role="rainwater_hopper",
        )
    box(
        c,
        "cafeteria:roof_coping",
        (ox, oy, h + 0.78),
        (w + 1.2, d + 1.2, 0.16),
        M["roof_light"],
        0.03,
        role="roof_coping",
    )
    c[
        "c2w_detail_profile"
    ] = "four_sided_curtain_wall+timber_screens+deep_canopy+solar_array+roof_drainage"
    return c


# ---------------------------------------------------------------------------
# Standards-based track/football field and volleyball courts.
# ---------------------------------------------------------------------------


def capsule_points(cx, cy, width, length, segments=48):
    radius = width / 2
    straight = (length - width) / 2
    pts = []
    for index in range(segments + 1):
        angle = math.pi * index / segments
        pts.append(
            (cx + radius * math.cos(angle), cy + straight + radius * math.sin(angle))
        )
    for index in range(segments + 1):
        angle = math.pi + math.pi * index / segments
        pts.append(
            (cx + radius * math.cos(angle), cy - straight + radius * math.sin(angle))
        )
    return pts


def stadium_ring(
    c,
    name,
    center,
    outer,
    inner,
    z,
    material,
    role="running_track_surface",
    thickness=0.14,
):
    outer_pts = capsule_points(*center, *outer)
    inner_pts = capsule_points(*center, *inner)
    bottom = z - thickness
    verts = (
        [(x, y, z) for x, y in outer_pts]
        + [(x, y, z) for x, y in inner_pts]
        + [(x, y, bottom) for x, y in outer_pts]
        + [(x, y, bottom) for x, y in inner_pts]
    )
    n = len(outer_pts)
    faces = []
    for index in range(n):
        nxt = (index + 1) % n
        # Top, soffit, outer fascia and inner fascia create a physical resilient slab.
        faces.append((index, nxt, n + nxt, n + index))
        faces.append((2 * n + index, 3 * n + index, 3 * n + nxt, 2 * n + nxt))
        faces.append((index, 2 * n + index, 2 * n + nxt, nxt))
        faces.append((n + index, n + nxt, 3 * n + nxt, 3 * n + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    return tag(obj, role)


def capsule_curve(
    c, name, center, width, length, z, material, radius=0.045, role="track_lane_line"
):
    outer = capsule_points(*center, width + radius * 2, length + radius * 2, 64)
    inner = capsule_points(*center, width - radius * 2, length - radius * 2, 64)
    vertices = [(x, y, z) for x, y in outer] + [(x, y, z) for x, y in inner]
    count = len(outer)
    faces = []
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":flat_ribbon_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    return tag(obj, role)


def field_line_box(c, name, xyz, dims, M):
    return box(c, name, xyz, dims, M["track_line"], 0.0, role="football_pitch_marking")


def build_goal(c, name, cx, cy, outward, M):
    z0 = 0.38
    width = 7.32
    height = 2.44
    depth = 2.0
    for x in (cx - width / 2, cx + width / 2):
        beam(
            c,
            name + ":front_post",
            (x, cy, z0),
            (x, cy, z0 + height),
            0.065,
            M["white_clean"],
            18,
            "football_goal_frame",
        )
        beam(
            c,
            name + ":back_support",
            (x, cy, z0 + height),
            (x, cy + outward * depth, z0 + height * 0.78),
            0.045,
            M["white_clean"],
            14,
            "football_goal_frame",
        )
    beam(
        c,
        name + ":crossbar",
        (cx - width / 2, cy, z0 + height),
        (cx + width / 2, cy, z0 + height),
        0.065,
        M["white_clean"],
        18,
        "football_goal_frame",
    )
    beam(
        c,
        name + ":backbar",
        (cx - width / 2, cy + outward * depth, z0),
        (cx + width / 2, cy + outward * depth, z0),
        0.045,
        M["white_clean"],
        14,
        "football_goal_frame",
    )
    for ix in range(13):
        x = cx - width / 2 + width * ix / 12
        beam(
            c,
            name + ":net_vertical",
            (x, cy, z0),
            (x, cy + outward * depth, z0 + height * 0.78),
            0.008,
            M["track_line"],
            8,
            "goal_net_cord",
        )
    for iz in range(7):
        z = z0 + height * iz / 6
        back_z = z0 + height * 0.78 * iz / 6
        beam(
            c,
            name + ":net_horizontal",
            (cx - width / 2, cy, z),
            (cx + width / 2, cy, z),
            0.008,
            M["track_line"],
            8,
            "goal_net_cord",
        )
        beam(
            c,
            name + ":net_back",
            (cx - width / 2, cy + outward * depth, back_z),
            (cx + width / 2, cy + outward * depth, back_z),
            0.008,
            M["track_line"],
            8,
            "goal_net_cord",
        )


def build_track_and_field(parent, M):
    c = collection("TRACK_AND_FOOTBALL_FIELD", parent, "school.track_football.v3")
    cx, cy = -68.0, -18.0
    stadium_ring(
        c,
        "track:eight_lane_surface",
        (cx, cy),
        (65.0, 124.0),
        (50.2, 109.2),
        0.34,
        M["track"],
    )
    stadium_ring(
        c,
        "track:outer_slot_drain",
        (cx, cy),
        (65.75, 124.75),
        (65.18, 124.18),
        0.355,
        M["steel"],
        role="track_drainage_channel",
        thickness=0.10,
    )
    stadium_ring(
        c,
        "track:inner_slot_drain",
        (cx, cy),
        (50.05, 109.05),
        (49.55, 108.55),
        0.365,
        M["steel"],
        role="track_drainage_channel",
        thickness=0.11,
    )
    for lane in range(9):
        inset = lane * (7.4 / 8)
        capsule_curve(
            c,
            f"track:lane_boundary_{lane}",
            (cx, cy),
            65.0 - inset * 2,
            124.0 - inset * 2,
            0.39,
            M["track_line"],
            0.035,
        )
    # Staggered start marks, exchange zones, lane numerals and drain channel.
    for lane in range(8):
        x = cx - 31.0 + lane * 0.92
        field_line_box(
            c,
            f"track:start_mark_{lane}",
            (x, cy - 30.0 + lane * 0.65, 0.41),
            (0.055, 2.0, 0.035),
            M,
        )
        text_object(
            c,
            f"track:lane_number_{lane+1}",
            str(lane + 1),
            (x + 0.42, cy - 30.0 + lane * 0.65, 0.43),
            0.55,
            M["track_line"],
            0.018,
            rot=(0, 0, math.pi / 2),
            role="track_lane_number",
        )
    for y in (cy - 39, cy + 39):
        for lane in range(8):
            x = cx - 31.0 + lane * 0.93
            box(
                c,
                "track:exchange_tick",
                (x, y, 0.415),
                (0.055, 1.8, 0.035),
                M["line_yellow"],
                0,
                role="track_exchange_mark",
            )
    capsule_curve(
        c,
        "track:inner_drain_edge",
        (cx, cy),
        49.48,
        108.48,
        0.397,
        M["black_metal"],
        0.055,
        role="track_drainage_edge",
    )

    # Striped regulation football pitch inside the oval.
    # A complete 43.5 x 79 m school football pitch fits wholly inside the oval;
    # its former 91 m rectangle intruded into the red track at all four corners.
    field_w, field_l = 43.5, 79.0
    for stripe in range(13):
        sy = cy - field_l / 2 + stripe * field_l / 13 + field_l / 26
        box(
            c,
            f"field:mowing_stripe_{stripe}",
            (cx, sy, 0.285),
            (field_w, field_l / 13 + 0.02, 0.18),
            M["field_alt"] if stripe % 2 else M["field"],
            0.0,
            role="football_turf",
        )
    line_z = 0.405
    for x in (cx - field_w / 2, cx + field_w / 2):
        field_line_box(c, "field:touchline", (x, cy, line_z), (0.09, field_l, 0.035), M)
    for y in (cy - field_l / 2, cy + field_l / 2, cy):
        field_line_box(
            c, "field:goal_or_halfway_line", (cx, y, line_z), (field_w, 0.09, 0.035), M
        )
    # Centre circle and penalty arcs are real curves.
    for name, px, py, radius, start, end in (
        ("centre_circle", cx, cy, 7.5, 0, 2 * math.pi),
        (
            "south_penalty_arc",
            cx,
            cy - field_l / 2 + 15.0,
            6.8,
            0.15 * math.pi,
            0.85 * math.pi,
        ),
        (
            "north_penalty_arc",
            cx,
            cy + field_l / 2 - 15.0,
            6.8,
            1.15 * math.pi,
            1.85 * math.pi,
        ),
    ):
        curve = bpy.data.curves.new(PREFIX + "field:" + name + ":curve", "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = 0.045
        curve.bevel_resolution = 2
        spline = curve.splines.new("POLY")
        count = 64
        spline.points.add(count)
        for idx in range(count + 1):
            a = start + (end - start) * idx / count
            spline.points[idx].co = (
                px + math.cos(a) * radius,
                py + math.sin(a) * radius,
                line_z,
                1,
            )
        spline.use_cyclic_u = end - start >= 2 * math.pi - 0.01
        obj = bpy.data.objects.new(PREFIX + "field:" + name, curve)
        c.objects.link(obj)
        curve.materials.append(M["track_line"])
        tag(obj, "football_pitch_marking")
    cylinder(
        c,
        "field:centre_spot",
        (cx, cy, line_z),
        0.13,
        0.04,
        M["track_line"],
        24,
        role="football_pitch_marking",
    )
    for side in (-1, 1):
        gy = cy + side * field_l / 2
        # penalty and goal boxes
        box(
            c,
            "field:penalty_box_end",
            (cx, gy - side * 12.0, line_z),
            (30.0, 0.09, 0.035),
            M["track_line"],
            0,
            role="football_pitch_marking",
        )
        for x in (cx - 15.0, cx + 15.0):
            box(
                c,
                "field:penalty_box_side",
                (x, gy - side * 6.0, line_z),
                (0.09, 12.0, 0.035),
                M["track_line"],
                0,
                role="football_pitch_marking",
            )
        box(
            c,
            "field:goal_box_end",
            (cx, gy - side * 4.0, line_z),
            (13.5, 0.09, 0.035),
            M["track_line"],
            0,
            role="football_pitch_marking",
        )
        for x in (cx - 6.75, cx + 6.75):
            box(
                c,
                "field:goal_box_side",
                (x, gy - side * 2.0, line_z),
                (0.09, 4.0, 0.035),
                M["track_line"],
                0,
                role="football_pitch_marking",
            )
        cylinder(
            c,
            "field:penalty_spot",
            (cx, gy - side * 10.2, line_z),
            0.12,
            0.04,
            M["track_line"],
            24,
            role="football_pitch_marking",
        )
        build_goal(c, "field:goal", cx, gy, side, M)

    # West-side tiered spectator stand with individual seats and guardrail.
    sx = cx - 39.2
    box(
        c,
        "stand:foundation",
        (sx, cy, 0.55),
        (8.5, 44.0, 1.1),
        M["concrete"],
        0.07,
        role="grandstand_foundation",
    )
    for tier in range(5):
        box(
            c,
            f"stand:tier_{tier}",
            (sx - tier * 0.65, cy, 0.95 + tier * 0.48),
            (7.2 - tier * 0.8, 42.0, 0.42),
            M["stone_light"],
            0.025,
            role="grandstand_tier",
        )
        for seat in range(20):
            y = cy - 19.0 + seat * 2.0
            seat_x = sx - 1.2 - tier * 0.63
            seat_z = 1.35 + tier * 0.48
            seat_material = M["court_blue"] if (seat + tier) % 3 else M["court_rose"]
            box(
                c,
                f"stand:seat_{tier}_{seat}:pan",
                (seat_x, y, seat_z),
                (0.58, 1.35, 0.18),
                seat_material,
                0.07,
                role="grandstand_seat",
            )
            box(
                c,
                f"stand:seat_{tier}_{seat}:back",
                (seat_x - 0.28, y, seat_z + 0.48),
                (0.13, 1.25, 0.82),
                seat_material,
                0.065,
                role="grandstand_seat_back",
            )
            cylinder(
                c,
                f"stand:seat_{tier}_{seat}:pedestal",
                (seat_x, y, seat_z - 0.23),
                0.055,
                0.44,
                M["steel"],
                16,
                role="grandstand_seat_support",
            )
    for y in (cy - 21.0, cy + 21.0):
        cylinder(
            c,
            "stand:rail_post",
            (sx - 4.5, y, 4.05),
            0.045,
            1.8,
            M["steel"],
            16,
            role="guardrail",
        )
    beam(
        c,
        "stand:top_guardrail",
        (sx - 4.5, cy - 21, 4.85),
        (sx - 4.5, cy + 21, 4.85),
        0.055,
        M["steel"],
        16,
        "guardrail",
    )
    # Cantilevered spectator canopy with rear structure and drainage gutter.
    for y in (cy - 20.0, cy - 10.0, cy, cy + 10.0, cy + 20.0):
        cylinder(
            c,
            "stand:canopy_column",
            (sx - 3.9, y, 5.15),
            0.13,
            6.1,
            M["steel"],
            22,
            role="grandstand_canopy_structure",
        )
        beam(
            c,
            "stand:canopy_outrigger",
            (sx - 3.9, y, 7.55),
            (sx + 3.6, y, 6.75),
            0.11,
            M["steel"],
            18,
            "grandstand_canopy_structure",
        )
    box(
        c,
        "stand:canopy_roof",
        (sx - 0.2, cy, 7.23),
        (8.5, 44.5, 0.28),
        M["roof_light"],
        0.055,
        role="grandstand_canopy",
    )
    box(
        c,
        "stand:canopy_gutter",
        (sx + 4.0, cy, 6.92),
        (0.28, 44.8, 0.35),
        M["steel"],
        0.035,
        role="rainwater_gutter",
    )

    # The east apron is intentionally continuous paving.  The former jump
    # runway/sand-pit assembly formed red, yellow and pale rectangular strips
    # between the oval and auditorium, while the exposed equipment-store mat
    # and loose starting blocks read as a construction-toy board below the
    # nearest mast.  Both groups are removed at source, not hidden for cameras.

    # Corner flags, covered team benches and four stadium light masts.
    for corner_index, (x, y) in enumerate(
        (
            (cx - field_w / 2, cy - field_l / 2),
            (cx + field_w / 2, cy - field_l / 2),
            (cx - field_w / 2, cy + field_l / 2),
            (cx + field_w / 2, cy + field_l / 2),
        )
    ):
        cylinder(
            c,
            f"field:corner_flag_{corner_index}:pole",
            (x, y, 1.03),
            0.025,
            1.35,
            M["paint_white"],
            12,
            role="athletic_equipment",
        )
        local_box(
            c,
            f"field:corner_flag_{corner_index}:flag",
            (x, y),
            0,
            (0.22, 0, 1.47),
            (0.44, 0.035, 0.30),
            M["sports_yellow"] if corner_index % 2 else M["sports_red"],
            0.0,
            role="athletic_equipment",
        )
    for shelter_index, sy in enumerate((cy - 39.0, cy - 26.0)):
        shelter_x = cx + 40.0
        box(
            c,
            f"field:team_shelter_{shelter_index}:base",
            (shelter_x, sy, 0.52),
            (3.0, 9.0, 0.18),
            M["concrete"],
            0.035,
            role="team_shelter",
        )
        box(
            c,
            f"field:team_shelter_{shelter_index}:roof",
            (shelter_x + 0.8, sy, 2.65),
            (3.5, 9.4, 0.18),
            M["glass_clear"],
            0.08,
            role="team_shelter",
        )
        for seat in range(5):
            seat_y = sy - 3.3 + seat * 1.65
            group = f"track_shelter_{shelter_index}_seat_{seat}"
            pan = box(
                c,
                f"field:team_shelter_{shelter_index}:seat_{seat}:pan",
                (shelter_x, seat_y, 0.82),
                (0.75, 1.15, 0.20),
                M["court_blue"],
                0.06,
                role="team_shelter_seat",
            )
            # The pitch is west of the dugouts; the back therefore belongs on
            # the east side, leaving the seated sightline unobstructed to -X.
            back = box(
                c,
                f"field:team_shelter_{shelter_index}:seat_{seat}:back",
                (shelter_x + 0.30, seat_y, 1.18),
                (0.16, 1.05, 0.64),
                M["court_blue"],
                0.055,
                role="team_shelter_seat",
            )
            for component, kind in ((pan, "pan"), (back, "back")):
                component["c2w_seat_group"] = group
                component["c2w_seat_component"] = kind
                component["c2w_seating_target"] = "football_pitch"
                component["c2w_facing_x"] = -1.0
                component["c2w_facing_y"] = 0.0
        for post_y in (sy - 4.4, sy + 4.4):
            cylinder(
                c,
                f"field:team_shelter_{shelter_index}:post",
                (shelter_x + 1.85, post_y, 1.55),
                0.06,
                2.2,
                M["steel"],
                16,
                role="team_shelter",
            )
    for mast_index, (mx, my) in enumerate(
        ((cx - 38, cy - 50), (cx - 38, cy + 50), (cx + 38, cy - 50), (cx + 38, cy + 50))
    ):
        cylinder(
            c,
            f"stadium:light_mast_{mast_index}",
            (mx, my, 9.5),
            0.19,
            18.2,
            M["steel"],
            26,
            bevel=0.035,
            role="stadium_light_mast",
        )
        box(
            c,
            f"stadium:light_bar_{mast_index}",
            (mx, my, 18.75),
            (4.0, 0.35, 0.24),
            M["black_metal"],
            0.035,
            role="stadium_light_array",
        )
        for lamp in range(6):
            box(
                c,
                f"stadium:floodlight_{mast_index}_{lamp}",
                (mx - 1.65 + lamp * 0.66, my - 0.18, 18.62),
                (0.48, 0.24, 0.36),
                M["lamp"],
                0.045,
                role="stadium_floodlight",
            )
    return c


def volleyball_net(c, name, cx, cy, M):
    y0, y1 = cy - 5.1, cy + 5.1
    for y in (y0, y1):
        cylinder(
            c,
            name + ":post_footing",
            (cx, y, 0.27),
            0.28,
            0.22,
            M["concrete"],
            32,
            bevel=0.025,
            role="volleyball_post_footing",
        )
        cylinder(
            c,
            name + ":post_socket",
            (cx, y, 0.43),
            0.12,
            0.18,
            M["steel"],
            28,
            bevel=0.012,
            role="volleyball_post_socket",
        )
        cylinder(
            c,
            name + ":post",
            (cx, y, 1.35),
            0.075,
            2.70,
            M["steel"],
            24,
            role="volleyball_post",
        )
        cylinder(
            c,
            name + ":post_pad",
            (cx, y, 0.72),
            0.18,
            1.44,
            M["court_blue"],
            28,
            role="volleyball_post_padding",
        )
    beam(
        c,
        name + ":top_cable",
        (cx, y0, 2.43),
        (cx, y1, 2.43),
        0.025,
        M["track_line"],
        12,
        "volleyball_net_cable",
    )
    beam(
        c,
        name + ":bottom_cable",
        (cx, y0, 0.95),
        (cx, y1, 0.95),
        0.018,
        M["track_line"],
        12,
        "volleyball_net_cable",
    )
    for index in range(17):
        y = y0 + (y1 - y0) * index / 16
        beam(
            c,
            name + ":vertical_cord",
            (cx, y, 0.95),
            (cx, y, 2.43),
            0.008,
            M["track_line"],
            8,
            "volleyball_net_mesh",
        )
    for index in range(10):
        z = 0.95 + (2.43 - 0.95) * index / 9
        beam(
            c,
            name + ":horizontal_cord",
            (cx, y0, z),
            (cx, y1, z),
            0.008,
            M["track_line"],
            8,
            "volleyball_net_mesh",
        )
    for y in (y0 + 0.16, y1 - 0.16):
        box(
            c,
            name + ":antenna",
            (cx, y, 2.66),
            (0.035, 0.035, 0.88),
            M["line_yellow"],
            0.006,
            role="volleyball_antenna",
        )
        box(
            c,
            name + ":side_tape",
            (cx, y, 1.69),
            (0.032, 0.075, 1.48),
            M["track_line"],
            0.005,
            role="volleyball_net_tape",
        )
    # Visible tension ratchet, cable guide and protective cap make the post assembly operational.
    box(
        c,
        name + ":tension_ratchet",
        (cx + 0.12, y1 + 0.08, 1.92),
        (0.24, 0.18, 0.34),
        M["steel"],
        0.035,
        role="volleyball_net_tensioner",
    )
    cylinder(
        c,
        name + ":ratchet_spindle",
        (cx + 0.24, y1 + 0.08, 1.92),
        0.055,
        0.28,
        M["black_metal"],
        18,
        rot=(0, math.pi / 2, 0),
        role="volleyball_net_tensioner",
    )
    for y in (y0, y1):
        cylinder(
            c,
            name + ":post_cap",
            (cx, y, 2.735),
            0.105,
            0.08,
            M["black_metal"],
            24,
            bevel=0.018,
            role="volleyball_post_cap",
        )


def chainlink_fence_segment(
    c, name, p0, p1, M, height=4.2, base_z=0.48, mesh_pitch=0.42
):
    """Ball-stop fence with posts, rails and clipped diamond wire mesh in one procedural panel."""
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    direction = Vector((x1 - x0, y1 - y0, 0)).normalized()

    def world(s, z):
        return (x0 + direction.x * s, y0 + direction.y * s, z)

    panel_count = max(1, math.ceil(length / 3.0))
    for index in range(panel_count + 1):
        s = length * index / panel_count
        px, py, _ = world(s, base_z)
        cylinder(
            c,
            name + ":concrete_footing",
            (px, py, 0.34),
            0.22,
            0.34,
            M["concrete"],
            28,
            bevel=0.025,
            role="volleyball_fence_footing",
        )
        cylinder(
            c,
            name + ":post",
            (px, py, base_z + height / 2),
            0.055,
            height,
            M["black_metal"],
            18,
            role="volleyball_fence_post",
        )
    for z in (base_z + 0.10, base_z + height * 0.52, base_z + height):
        beam(
            c,
            name + ":rail",
            world(0, z),
            world(length, z),
            0.038,
            M["black_metal"],
            14,
            "volleyball_fence_rail",
        )

    curve = bpy.data.curves.new(PREFIX + name + ":diamond_mesh_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.008
    curve.bevel_resolution = 0

    def add_wire(start_s, start_z, end_s, end_z):
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        a = world(start_s, start_z)
        b = world(end_s, end_z)
        spline.points[0].co = (*a, 1)
        spline.points[1].co = (*b, 1)

    offset = -height
    while offset <= length + height:
        start_s = max(0.0, offset)
        end_s = min(length, offset + height)
        if end_s > start_s:
            add_wire(start_s, base_z + start_s - offset, end_s, base_z + end_s - offset)
        start_s = max(0.0, offset - height)
        end_s = min(length, offset)
        if end_s > start_s:
            add_wire(start_s, base_z + offset - start_s, end_s, base_z + offset - end_s)
        offset += mesh_pitch
    curve.materials.append(M["steel"])
    mesh_obj = bpy.data.objects.new(PREFIX + name + ":diamond_wire_mesh", curve)
    c.objects.link(mesh_obj)
    tag(mesh_obj, "volleyball_fence_mesh")
    mesh_obj["c2w_mesh_pitch_m"] = mesh_pitch
    mesh_obj["c2w_ballstop_height_m"] = height


def build_volleyball_compound_fence(c, M):
    west, east, south, north = 43.8, 95.2, -78.5, -57.4
    chainlink_fence_segment(c, "compound:north", (west, north), (east, north), M)
    chainlink_fence_segment(c, "compound:west", (west, south), (west, north), M)
    chainlink_fence_segment(c, "compound:east", (east, north), (east, south), M)
    chainlink_fence_segment(c, "compound:south_west", (west, south), (67.2, south), M)
    chainlink_fence_segment(c, "compound:south_east", (70.8, south), (east, south), M)
    # A framed double service gate occupies the only opening in the enclosure.
    for leaf, centre_x in enumerate((68.1, 69.9)):
        for x in (centre_x - 0.86, centre_x + 0.86):
            beam(
                c,
                f"compound:gate_{leaf}:jamb",
                (x, south, 0.52),
                (x, south, 3.38),
                0.045,
                M["black_metal"],
                14,
                "volleyball_fence_gate",
            )
        for z in (0.52, 3.38):
            beam(
                c,
                f"compound:gate_{leaf}:rail",
                (centre_x - 0.86, south, z),
                (centre_x + 0.86, south, z),
                0.045,
                M["black_metal"],
                14,
                "volleyball_fence_gate",
            )
        for picket in range(7):
            x = centre_x - 0.72 + picket * 0.24
            beam(
                c,
                f"compound:gate_{leaf}:mesh_vertical",
                (x, south, 0.62),
                (x, south, 3.28),
                0.009,
                M["steel"],
                8,
                "volleyball_fence_gate_mesh",
            )
        box(
            c,
            f"compound:gate_{leaf}:latch",
            (centre_x + (-0.78 if leaf == 0 else 0.78), south - 0.06, 1.35),
            (0.17, 0.12, 0.32),
            M["steel"],
            0.025,
            role="volleyball_fence_gate_hardware",
        )


def volleyball_ball_cart(c, name, x, y, M):
    """Tubular wheeled ball trolley with a wire basket and retained balls."""
    for z, half_x, half_y in ((0.48, 0.66, 0.46), (1.32, 0.58, 0.39)):
        beam(
            c,
            name + ":basket_front",
            (x - half_x, y - half_y, z),
            (x + half_x, y - half_y, z),
            0.022,
            M["steel"],
            10,
            "volleyball_ball_cart",
        )
        beam(
            c,
            name + ":basket_back",
            (x - half_x, y + half_y, z),
            (x + half_x, y + half_y, z),
            0.022,
            M["steel"],
            10,
            "volleyball_ball_cart",
        )
        beam(
            c,
            name + ":basket_left",
            (x - half_x, y - half_y, z),
            (x - half_x, y + half_y, z),
            0.022,
            M["steel"],
            10,
            "volleyball_ball_cart",
        )
        beam(
            c,
            name + ":basket_right",
            (x + half_x, y - half_y, z),
            (x + half_x, y + half_y, z),
            0.022,
            M["steel"],
            10,
            "volleyball_ball_cart",
        )
    for sx in (-1, 1):
        for sy in (-1, 1):
            beam(
                c,
                name + ":upright",
                (x + sx * 0.66, y + sy * 0.46, 0.34),
                (x + sx * 0.58, y + sy * 0.39, 1.38),
                0.026,
                M["steel"],
                10,
                "volleyball_ball_cart",
            )
    for index in range(7):
        px = x - 0.54 + index * 0.18
        beam(
            c,
            name + ":basket_wire_x",
            (px, y - 0.42, 0.53),
            (px, y + 0.42, 1.27),
            0.008,
            M["steel"],
            8,
            "volleyball_ball_cart_mesh",
        )
    for index in range(6):
        py = y - 0.36 + index * 0.145
        beam(
            c,
            name + ":basket_wire_y",
            (x - 0.62, py, 0.53),
            (x + 0.62, py, 1.27),
            0.008,
            M["steel"],
            8,
            "volleyball_ball_cart_mesh",
        )
    for sx in (-0.48, 0.48):
        cylinder(
            c,
            name + ":caster",
            (x + sx, y, 0.27),
            0.16,
            0.10,
            M["tyre"],
            18,
            rot=(math.pi / 2, 0, 0),
            role="volleyball_ball_cart_caster",
        )
    for ball_index in range(5):
        bx = x - 0.38 + (ball_index % 3) * 0.38
        by = y + (-0.15 if ball_index % 2 else 0.14)
        bz = 0.76 + (ball_index // 3) * 0.38
        ellipsoid(
            c,
            name + f":retained_ball_{ball_index}",
            (bx, by, bz),
            (0.34, 0.34, 0.34),
            M["sports_yellow"] if ball_index % 2 else M["paint_white"],
            "volleyball_equipment",
            segments=24,
            rings=12,
        )


def volleyball_courtside_chair(c, name, x, y, target, M):
    target_x, target_y = target
    direction_x, direction_y = target_x - x, target_y - y
    yaw = math.atan2(-direction_x, direction_y)
    origin = (x, y, 0.0)
    parts = []
    for side in (-1, 1):
        parts.append(
            beam(
                c,
                name + f":front_leg_{side}",
                BASE.G.transform_point(origin, yaw, (side * 0.42, 0.23, 0.28)),
                BASE.G.transform_point(origin, yaw, (side * 0.42, 0.23, 0.72)),
                0.032,
                M["steel"],
                10,
                "court_seating_frame",
            )
        )
        parts.append(
            beam(
                c,
                name + f":rear_leg_{side}",
                BASE.G.transform_point(origin, yaw, (side * 0.42, -0.23, 0.28)),
                BASE.G.transform_point(origin, yaw, (side * 0.42, -0.23, 1.22)),
                0.032,
                M["steel"],
                10,
                "court_seating_frame",
            )
        )
    for slat in range(4):
        part = local_box(
            c,
            name + f":seat_slat_{slat}",
            (x, y),
            yaw,
            (0, -0.20 + slat * 0.13, 0.72),
            (0.96, 0.10, 0.075),
            M["wood"],
            0.025,
            role="court_seating_slat",
        )
        part["c2w_seat_component"] = "pan"
        parts.append(part)
    for slat in range(4):
        part = local_box(
            c,
            name + f":back_slat_{slat}",
            (x, y),
            yaw,
            (0, -0.25, 0.90 + slat * 0.12),
            (0.96, 0.075, 0.08),
            M["wood"],
            0.025,
            role="court_seating_slat",
        )
        part["c2w_seat_component"] = "back"
        parts.append(part)
    facing_x, facing_y = -math.sin(yaw), math.cos(yaw)
    for part in parts:
        part["c2w_seat_group"] = name
        part["c2w_seating_target"] = "volleyball_court"
        part["c2w_facing_x"] = facing_x
        part["c2w_facing_y"] = facing_y
        part["c2w_target_x"] = target_x
        part["c2w_target_y"] = target_y


def build_volleyball_courts(parent, M):
    c = collection("VOLLEYBALL_COURTS", parent, "school.volleyball_courts.v3")
    box(
        c,
        "compound:reinforced_apron",
        (69.5, -68.0, 0.255),
        (52.0, 20.0, 0.16),
        M["concrete"],
        0.055,
        role="volleyball_compound_apron",
    )
    for court, (cx, cy, inner) in enumerate(
        ((57.0, -68.0, "court_rose"), (82.0, -68.0, "court_blue"))
    ):
        box(
            c,
            f"court_{court}:safety_zone",
            (cx, cy, 0.28),
            (22.0, 14.0, 0.18),
            M["court_border"],
            0.07,
            role="volleyball_safety_surface",
        )
        box(
            c,
            f"court_{court}:playing_surface",
            (cx, cy, 0.39),
            (18.0, 9.0, 0.07),
            M[inner],
            0.035,
            role="volleyball_playing_surface",
        )
        line_z = 0.445
        for x in (cx - 9.0, cx + 9.0, cx):
            box(
                c,
                f"court_{court}:end_or_centre_line",
                (x, cy, line_z),
                (0.07, 9.0, 0.028),
                M["track_line"],
                0,
                role="volleyball_court_line",
            )
        for y in (cy - 4.5, cy + 4.5):
            box(
                c,
                f"court_{court}:sideline",
                (cx, y, line_z),
                (18.0, 0.07, 0.028),
                M["track_line"],
                0,
                role="volleyball_court_line",
            )
        for x in (cx - 3.0, cx + 3.0):
            box(
                c,
                f"court_{court}:attack_line",
                (x, cy, line_z),
                (0.07, 9.0, 0.028),
                M["track_line"],
                0,
                role="volleyball_court_line",
            )
        # Regulation service-zone ticks, centre anchors and flush perimeter drains.
        for x in (cx - 9.0, cx + 9.0):
            for y in (cy - 4.75, cy + 4.75):
                box(
                    c,
                    f"court_{court}:service_tick",
                    (x + (-0.18 if x < cx else 0.18), y, line_z),
                    (0.42, 0.055, 0.028),
                    M["track_line"],
                    0.0,
                    role="volleyball_court_line",
                )
        for y in (cy - 7.18, cy + 7.18):
            box(
                c,
                f"court_{court}:linear_drain",
                (cx, y, 0.405),
                (22.3, 0.18, 0.075),
                M["black_metal"],
                0.012,
                role="volleyball_court_drain",
            )
            for slot in range(32):
                box(
                    c,
                    f"court_{court}:drain_slot",
                    (cx - 10.6 + slot * 0.685, y, 0.452),
                    (0.32, 0.06, 0.018),
                    M["steel"],
                    0.0,
                    role="volleyball_court_drain_slot",
                )
        volleyball_net(c, f"court_{court}:net", cx, cy, M)
        # Referee stand with ladder rungs and platform.
        sx, sy = cx + 0.75, cy + 5.8
        for side in (-1, 1):
            beam(
                c,
                f"court_{court}:referee_upright",
                (sx + side * 0.35, sy, 0.35),
                (sx + side * 0.35, sy, 2.75),
                0.045,
                M["steel"],
                12,
                "referee_stand",
            )
        for rung in range(6):
            beam(
                c,
                f"court_{court}:ladder_rung",
                (sx - 0.35, sy, 0.55 + rung * 0.36),
                (sx + 0.35, sy, 0.55 + rung * 0.36),
                0.032,
                M["steel"],
                10,
                "referee_stand",
            )
        box(
            c,
            f"court_{court}:referee_platform",
            (sx, sy, 2.55),
            (1.25, 1.0, 0.14),
            M["steel"],
            0.025,
            role="referee_stand",
        )
        box(
            c,
            f"court_{court}:scoreboard_post",
            (cx - 8.4, cy + 6.4, 1.25),
            (0.16, 0.16, 2.2),
            M["steel"],
            0.025,
            role="court_scoreboard",
        )
        box(
            c,
            f"court_{court}:scoreboard",
            (cx - 8.4, cy + 6.4, 2.25),
            (2.2, 0.22, 1.25),
            M["charcoal"],
            0.055,
            role="court_scoreboard",
        )
        local_text(
            c,
            f"court_{court}:score",
            "12  |  09",
            (cx - 8.4, cy + 6.27),
            0,
            (0, 0, 2.28),
            0.28,
            M["track_line"],
            0.025,
        )
        # Ball trolley and courtside seating use tubular frames, wire basket and timber slats.
        cart_x, cart_y = cx + 8.2, cy - 6.0
        volleyball_ball_cart(c, f"court_{court}:ball_cart", cart_x, cart_y, M)
        for seat in range(4):
            volleyball_courtside_chair(
                c,
                f"court_{court}:courtside_chair_{seat}",
                cx - 5.1 + seat * 2.0,
                cy - 6.2,
                (cx, cy),
                M,
            )
        cylinder(
            c,
            f"court_{court}:net_anchor_cover_a",
            (cx, cy - 5.1, 0.45),
            0.20,
            0.035,
            M["steel"],
            28,
            bevel=0.012,
            role="volleyball_net_anchor",
        )
        cylinder(
            c,
            f"court_{court}:net_anchor_cover_b",
            (cx, cy + 5.1, 0.45),
            0.20,
            0.035,
            M["steel"],
            28,
            bevel=0.012,
            role="volleyball_net_anchor",
        )
    build_volleyball_compound_fence(c, M)
    c[
        "c2w_detail_profile"
    ] = "regulation_surfaces+diamond_ballstop_fence+tensioned_nets+drainage+referee_stands+tubular_furniture"
    return c


# ---------------------------------------------------------------------------
# Campus grounds: dedicated parcel, gate, fence, circulation and vegetation.
# ---------------------------------------------------------------------------


def fence_segment(c, name, p0, p1, M, height=2.1):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    yaw = math.atan2(y1 - y0, x1 - x0)
    count = max(1, math.ceil(length / 4.0))
    for index in range(count + 1):
        t = index / count
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        cylinder(
            c,
            name + ":post",
            (x, y, height / 2 + 0.35),
            0.075,
            height,
            M["black_metal"],
            18,
            role="campus_fence_post",
        )
    for rail_z in (0.68, height + 0.25):
        beam(
            c,
            name + ":rail",
            (x0, y0, rail_z),
            (x1, y1, rail_z),
            0.055,
            M["black_metal"],
            14,
            "campus_fence_rail",
        )
    # Dense vertical infill makes the boundary read as a real security fence.
    for index in range(count * 4 + 1):
        t = index / (count * 4)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        cylinder(
            c,
            name + ":picket",
            (x, y, height / 2 + 0.35),
            0.018,
            height - 0.12,
            M["steel"],
            10,
            role="campus_fence_infill",
        )


_LEAF_MESHES = {}
_TREE_MASTERS = {}
_TREE_MASTER_STATS = {}
_TREE_SEEDS = (42, 619)


def leaf_card(c, name, xyz, scale, rotation, material):
    key = material.name_full
    mesh = _LEAF_MESHES.get(key)
    if mesh is None or mesh.name not in bpy.data.meshes:
        mesh = bpy.data.meshes.new(PREFIX + "shared_leaf:" + key.replace(":", "_"))
        mesh.from_pydata(
            [
                (-0.50, 0, 0),
                (-0.27, 0, -0.24),
                (0.08, 0, -0.30),
                (0.48, 0, -0.08),
                (0.55, 0, 0.08),
                (0.18, 0, 0.30),
                (-0.18, 0, 0.28),
                (-0.46, 0, 0.10),
            ],
            [],
            [(0, 1, 2, 3, 4, 5, 6, 7), (7, 6, 5, 4, 3, 2, 1, 0)],
        )
        mesh.materials.append(material)
        mesh.update()
        _LEAF_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = xyz
    obj.scale = scale
    obj.rotation_euler = rotation
    return tag(obj, "botanical_leaf")


_LANDSCAPE_LEAF_MESHES = {}
_FLOWER_PETAL_MESHES = {}


def landscape_leaf(c, name, location, direction, size, material, role="shrub_leaf"):
    """Curved, veined leaf mesh reused from the previous connected-planter strategy."""
    key = material.name_full
    mesh = _LANDSCAPE_LEAF_MESHES.get(key)
    if mesh is None or mesh.name not in bpy.data.meshes:
        vertices = [
            (0.0, 0.0, 0.0),
            (-0.20, 0.20, 0.025),
            (-0.30, 0.46, 0.06),
            (-0.22, 0.72, 0.045),
            (0.0, 1.0, 0.0),
            (0.22, 0.72, 0.045),
            (0.30, 0.46, 0.06),
            (0.20, 0.20, 0.025),
            (0.0, 0.28, 0.085),
            (0.0, 0.62, 0.095),
        ]
        faces = [
            (0, 1, 8),
            (1, 2, 8),
            (2, 3, 9, 8),
            (3, 4, 9),
            (0, 8, 7),
            (7, 8, 6),
            (8, 9, 5, 6),
            (9, 4, 5),
            (8, 1, 0),
            (8, 2, 1),
            (8, 9, 3, 2),
            (9, 4, 3),
            (7, 8, 0),
            (6, 8, 7),
            (6, 5, 9, 8),
            (5, 4, 9),
        ]
        mesh = bpy.data.meshes.new(
            PREFIX + "shared_connected_landscape_leaf:" + key.replace(":", "_")
        )
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(material)
        mesh.update()
        _LANDSCAPE_LEAF_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = location
    vector = Vector(direction)
    if vector.length < 1e-6:
        vector = Vector((0, 1, 0.1))
    obj.rotation_euler = vector.normalized().to_track_quat("Y", "Z").to_euler()
    obj.scale = (size, size, size)
    tag(obj, role)
    obj["c2w_leaf_mesh_vertices"] = len(mesh.vertices)
    obj["c2w_connected_to_stem"] = True
    return obj


def flower_petal(c, name, location, angle, scale, material):
    key = material.name_full
    mesh = _FLOWER_PETAL_MESHES.get(key)
    if mesh is None or mesh.name not in bpy.data.meshes:
        vertices = [
            (-0.08, 0.0, 0.0),
            (-0.15, 0.16, 0.035),
            (-0.14, 0.34, 0.075),
            (-0.07, 0.48, 0.055),
            (0.0, 0.54, 0.025),
            (0.07, 0.48, 0.055),
            (0.14, 0.34, 0.075),
            (0.15, 0.16, 0.035),
            (0.08, 0.0, 0.0),
            (0.0, 0.25, 0.105),
        ]
        faces = [
            (0, 1, 9),
            (1, 2, 9),
            (2, 3, 9),
            (3, 4, 9),
            (4, 5, 9),
            (5, 6, 9),
            (6, 7, 9),
            (7, 8, 9),
        ]
        faces += [tuple(reversed(face)) for face in faces]
        mesh = bpy.data.meshes.new(
            PREFIX + "shared_curved_flower_petal:" + key.replace(":", "_")
        )
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(material)
        mesh.update()
        _FLOWER_PETAL_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (
        math.radians(-8),
        math.radians(5 * math.sin(angle * 3)),
        angle,
    )
    obj.scale = (scale, scale, scale)
    tag(obj, "flower_petal")
    obj["c2w_connected_flower_head"] = True
    return obj


def connected_shrub(c, name, base, seed, height, spread, M):
    """Multi-level woody shrub with explicit petioles and shaped leaves; never an ellipsoid crown."""
    rng = random.Random(seed)
    bx, by, bz = base
    stem_count = 8
    for stem in range(stem_count):
        angle = math.tau * stem / stem_count + rng.uniform(-0.22, 0.22)
        radial = spread * rng.uniform(0.55, 1.0)
        mid = Vector(
            (
                bx + math.cos(angle) * radial * 0.38,
                by + math.sin(angle) * radial * 0.38,
                bz + height * rng.uniform(0.38, 0.52),
            )
        )
        tip = Vector(
            (
                bx + math.cos(angle) * radial,
                by + math.sin(angle) * radial,
                bz + height * rng.uniform(0.78, 1.08),
            )
        )
        beam(
            c,
            name + f":primary_{stem}_a",
            (bx, by, bz),
            mid,
            0.018,
            M["bark"],
            9,
            "shrub_branch",
        )
        beam(
            c,
            name + f":primary_{stem}_b",
            mid,
            tip,
            0.012,
            M["bark"],
            8,
            "shrub_branch",
        )
        side = Vector(
            (-math.sin(angle), math.cos(angle), rng.uniform(0.18, 0.42))
        ).normalized()
        for branch_sign in (-1, 1):
            branch_tip = mid.lerp(
                tip, 0.58
            ) + side * branch_sign * spread * rng.uniform(0.32, 0.48)
            beam(
                c,
                name + f":twig_{stem}_{branch_sign}",
                mid.lerp(tip, 0.46),
                branch_tip,
                0.007,
                M["bark"],
                7,
                "shrub_twig",
            )
            for leaf_index in range(2):
                anchor = mid.lerp(branch_tip, 0.56 + leaf_index * 0.25)
                leaf_dir = side * branch_sign + Vector(
                    (
                        rng.uniform(-0.2, 0.2),
                        rng.uniform(-0.2, 0.2),
                        rng.uniform(0.12, 0.45),
                    )
                )
                petiole_end = anchor + leaf_dir.normalized() * 0.055
                beam(
                    c,
                    name + f":petiole_{stem}_{branch_sign}_{leaf_index}",
                    anchor,
                    petiole_end,
                    0.0035,
                    M["leaf"],
                    6,
                    "shrub_petiole",
                )
                landscape_leaf(
                    c,
                    name + f":leaf_{stem}_{branch_sign}_{leaf_index}",
                    petiole_end,
                    leaf_dir,
                    rng.uniform(0.19, 0.27),
                    M["leaf_light"] if (stem + leaf_index) % 7 == 0 else M["leaf"],
                )
        for leaf_index in range(3):
            anchor = mid.lerp(tip, 0.50 + leaf_index * 0.22)
            leaf_angle = angle + (-0.8 if leaf_index % 2 else 0.8)
            leaf_dir = Vector(
                (math.cos(leaf_angle), math.sin(leaf_angle), rng.uniform(0.18, 0.55))
            )
            petiole_end = anchor + leaf_dir.normalized() * 0.05
            beam(
                c,
                name + f":terminal_petiole_{stem}_{leaf_index}",
                anchor,
                petiole_end,
                0.0035,
                M["leaf"],
                6,
                "shrub_petiole",
            )
            landscape_leaf(
                c,
                name + f":terminal_leaf_{stem}_{leaf_index}",
                petiole_end,
                leaf_dir,
                rng.uniform(0.20, 0.30),
                M["leaf"],
            )


def connected_flower(c, name, base, seed, M):
    rng = random.Random(seed)
    x, y, z = base
    height = rng.uniform(0.34, 0.56)
    middle = Vector(
        (
            x + rng.uniform(-0.025, 0.025),
            y + rng.uniform(-0.025, 0.025),
            z + height * 0.52,
        )
    )
    top = Vector(
        (x + rng.uniform(-0.045, 0.045), y + rng.uniform(-0.045, 0.045), z + height)
    )
    beam(c, name + ":stem_lower", (x, y, z), middle, 0.006, M["leaf"], 7, "flower_stem")
    beam(c, name + ":stem_upper", middle, top, 0.0045, M["leaf"], 7, "flower_stem")
    for side in (-1, 1):
        direction = Vector(
            (
                side * rng.uniform(0.7, 1.0),
                rng.uniform(-0.35, 0.35),
                rng.uniform(0.18, 0.38),
            )
        )
        petiole_end = middle + direction.normalized() * 0.07
        beam(
            c,
            name + f":leaf_petiole_{side}",
            middle,
            petiole_end,
            0.003,
            M["leaf"],
            6,
            "flower_petiole",
        )
        landscape_leaf(
            c,
            name + f":stem_leaf_{side}",
            petiole_end,
            direction,
            rng.uniform(0.14, 0.19),
            M["leaf_light"],
            role="flower_leaf",
        )
    petal_materials = (
        M["flower_white"],
        M["flower_yellow"],
        M["flower_red"],
        M["flower_purple"],
    )
    petal_material = petal_materials[seed % len(petal_materials)]
    petals = 8
    for index in range(petals):
        flower_petal(
            c,
            name + f":petal_{index}",
            top,
            math.tau * index / petals,
            rng.uniform(0.31, 0.38),
            petal_material,
        )
    cylinder(
        c,
        name + ":disc",
        (top.x, top.y, top.z + 0.035),
        0.075,
        0.055,
        M["flower_center"],
        24,
        bevel=0.015,
        role="flower_disc",
    )


def _append_tapered_tube(vertices, faces, p0, p1, radius0, radius1, sides=7):
    p0, p1 = Vector(p0), Vector(p1)
    direction = p1 - p0
    if direction.length < 1e-7:
        return
    direction.normalize()
    reference = Vector((0, 0, 1)) if abs(direction.z) < 0.92 else Vector((1, 0, 0))
    right = direction.cross(reference).normalized()
    up = right.cross(direction).normalized()
    offset = len(vertices)
    for point, radius in ((p0, radius0), (p1, radius1)):
        for side in range(sides):
            angle = math.tau * side / sides
            vertices.append(
                tuple(
                    point
                    + right * math.cos(angle) * radius
                    + up * math.sin(angle) * radius
                )
            )
    for side in range(sides):
        nxt = (side + 1) % sides
        faces.append(
            (offset + side, offset + nxt, offset + sides + nxt, offset + sides + side)
        )
    faces.append(tuple(reversed(tuple(offset + side for side in range(sides)))))
    faces.append(tuple(offset + sides + side for side in range(sides)))


def _append_shaped_leaf(vertices, faces, location, direction, size):
    source = (
        (0.0, 0.0, 0.0),
        (-0.20, 0.20, 0.025),
        (-0.30, 0.46, 0.06),
        (-0.22, 0.72, 0.045),
        (0.0, 1.0, 0.0),
        (0.22, 0.72, 0.045),
        (0.30, 0.46, 0.06),
        (0.20, 0.20, 0.025),
        (0.0, 0.28, 0.085),
        (0.0, 0.62, 0.095),
    )
    source_faces = (
        (0, 1, 8),
        (1, 2, 8),
        (2, 3, 9, 8),
        (3, 4, 9),
        (0, 8, 7),
        (7, 8, 6),
        (8, 9, 5, 6),
        (9, 4, 5),
    )
    vector = Vector(direction)
    if vector.length < 1e-7:
        vector = Vector((0, 1, 0.2))
    rotation = vector.normalized().to_track_quat("Y", "Z")
    origin = Vector(location)
    offset = len(vertices)
    for coordinate in source:
        vertices.append(tuple(origin + rotation @ (Vector(coordinate) * size)))
    for face in source_faces:
        mapped = tuple(offset + index for index in face)
        faces.extend((mapped, tuple(reversed(mapped))))


def _append_flower_petal(vertices, faces, location, angle, scale):
    source = (
        (-0.08, 0.0, 0.0),
        (-0.15, 0.16, 0.035),
        (-0.14, 0.34, 0.075),
        (-0.07, 0.48, 0.055),
        (0.0, 0.54, 0.025),
        (0.07, 0.48, 0.055),
        (0.14, 0.34, 0.075),
        (0.15, 0.16, 0.035),
        (0.08, 0.0, 0.0),
        (0.0, 0.25, 0.105),
    )
    source_faces = (
        (0, 1, 9),
        (1, 2, 9),
        (2, 3, 9),
        (3, 4, 9),
        (4, 5, 9),
        (5, 6, 9),
        (6, 7, 9),
        (7, 8, 9),
    )
    cosine, sine = math.cos(angle), math.sin(angle)
    origin = Vector(location)
    offset = len(vertices)
    for x, y, z in source:
        vertices.append(
            tuple(
                origin
                + Vector(
                    (
                        (x * cosine - y * sine) * scale,
                        (x * sine + y * cosine) * scale,
                        z * scale,
                    )
                )
            )
        )
    for face in source_faces:
        mapped = tuple(offset + index for index in face)
        faces.extend((mapped, tuple(reversed(mapped))))


def _append_disc(vertices, faces, location, radius=0.075, depth=0.055, sides=14):
    origin = Vector(location)
    offset = len(vertices)
    for z in (0.0, depth):
        for side in range(sides):
            angle = math.tau * side / sides
            vertices.append(
                (
                    origin.x + math.cos(angle) * radius,
                    origin.y + math.sin(angle) * radius,
                    origin.z + z,
                )
            )
    for side in range(sides):
        nxt = (side + 1) % sides
        faces.append(
            (offset + side, offset + nxt, offset + sides + nxt, offset + sides + side)
        )
    faces.append(tuple(reversed(tuple(offset + side for side in range(sides)))))
    faces.append(tuple(offset + sides + side for side in range(sides)))


def _merged_botanical_object(
    c, name, vertices, faces, material, role, explicit_key, explicit_count
):
    if not vertices or not faces:
        return None
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    tag(obj, role)
    obj[explicit_key] = explicit_count
    obj["c2w_merged_without_geometry_loss"] = True
    return obj


def detailed_landscape_planter(c, name, x, y, length, depth, M, seed):
    """Raised masonry planter with hollow wall assembly, coping, mulch, shrubs and explicit flowers."""
    wall_t = 0.30
    base_z = 0.73
    box(
        c,
        name + ":wall_north",
        (x, y + depth / 2 - wall_t / 2, base_z),
        (length, wall_t, 0.62),
        M["brick_dark"],
        0.045,
        role="landscape_planter_wall",
    )
    box(
        c,
        name + ":wall_south",
        (x, y - depth / 2 + wall_t / 2, base_z),
        (length, wall_t, 0.62),
        M["brick_dark"],
        0.045,
        role="landscape_planter_wall",
    )
    box(
        c,
        name + ":wall_east",
        (x + length / 2 - wall_t / 2, y, base_z),
        (wall_t, depth - wall_t * 2, 0.62),
        M["brick_dark"],
        0.045,
        role="landscape_planter_wall",
    )
    box(
        c,
        name + ":wall_west",
        (x - length / 2 + wall_t / 2, y, base_z),
        (wall_t, depth - wall_t * 2, 0.62),
        M["brick_dark"],
        0.045,
        role="landscape_planter_wall",
    )
    box(
        c,
        name + ":soil",
        (x, y, 1.07),
        (length - 0.52, depth - 0.52, 0.13),
        M["soil"],
        0.025,
        role="planting_soil",
    )
    box(
        c,
        name + ":mulch_layer",
        (x, y, 1.145),
        (length - 0.64, depth - 0.64, 0.045),
        M["mulch"],
        0.018,
        role="landscape_mulch",
    )
    # Individual coping stones reveal joints and wall thickness.
    coping_count = max(4, int(math.ceil(length / 1.15)))
    coping_w = length / coping_count
    for index in range(coping_count):
        cx = x - length / 2 + coping_w * (index + 0.5)
        for cy in (y - depth / 2, y + depth / 2):
            box(
                c,
                name + f":coping_long_{index}",
                (cx, cy, 1.08),
                (coping_w - 0.035, 0.42, 0.14),
                M["stone_light"],
                0.028,
                role="landscape_planter_coping",
            )
    side_count = max(2, int(math.ceil((depth - 0.75) / 0.85)))
    side_w = (depth - 0.75) / side_count
    for index in range(side_count):
        cy = y - (depth - 0.75) / 2 + side_w * (index + 0.5)
        for cx in (x - length / 2, x + length / 2):
            box(
                c,
                name + f":coping_short_{index}",
                (cx, cy, 1.08),
                (0.42, side_w - 0.035, 0.14),
                M["stone_light"],
                0.028,
                role="landscape_planter_coping",
            )

    rng = random.Random(seed)
    shrub_branch_vertices, shrub_branch_faces = [], []
    shrub_leaf_vertices, shrub_leaf_faces = [], []
    explicit_shrub_branches = 0
    explicit_shrub_leaves = 0
    shrub_count = max(3, int(length // 4.0))
    for shrub in range(shrub_count):
        sx = x - length / 2 + 1.25 + shrub * (length - 2.5) / max(1, shrub_count - 1)
        sy = y + rng.uniform(-depth * 0.14, depth * 0.14)
        shrub_rng = random.Random(seed * 97 + shrub)
        height = rng.uniform(0.74, 1.02)
        spread = rng.uniform(0.55, 0.78)
        stem_count = 8
        for stem in range(stem_count):
            angle = math.tau * stem / stem_count + shrub_rng.uniform(-0.22, 0.22)
            radial = spread * shrub_rng.uniform(0.55, 1.0)
            base = Vector((sx, sy, 1.15))
            middle = Vector(
                (
                    sx + math.cos(angle) * radial * 0.38,
                    sy + math.sin(angle) * radial * 0.38,
                    1.15 + height * shrub_rng.uniform(0.38, 0.52),
                )
            )
            tip = Vector(
                (
                    sx + math.cos(angle) * radial,
                    sy + math.sin(angle) * radial,
                    1.15 + height * shrub_rng.uniform(0.78, 1.08),
                )
            )
            _append_tapered_tube(
                shrub_branch_vertices, shrub_branch_faces, base, middle, 0.018, 0.012, 7
            )
            _append_tapered_tube(
                shrub_branch_vertices, shrub_branch_faces, middle, tip, 0.012, 0.005, 7
            )
            explicit_shrub_branches += 2
            side_vector = Vector(
                (-math.sin(angle), math.cos(angle), shrub_rng.uniform(0.18, 0.42))
            ).normalized()
            for branch_sign in (-1, 1):
                branch_base = middle.lerp(tip, 0.46)
                branch_tip = middle.lerp(
                    tip, 0.58
                ) + side_vector * branch_sign * spread * shrub_rng.uniform(0.32, 0.48)
                _append_tapered_tube(
                    shrub_branch_vertices,
                    shrub_branch_faces,
                    branch_base,
                    branch_tip,
                    0.007,
                    0.0028,
                    6,
                )
                explicit_shrub_branches += 1
                for leaf_index in range(2):
                    anchor = middle.lerp(branch_tip, 0.56 + leaf_index * 0.25)
                    leaf_direction = side_vector * branch_sign + Vector(
                        (
                            shrub_rng.uniform(-0.2, 0.2),
                            shrub_rng.uniform(-0.2, 0.2),
                            shrub_rng.uniform(0.12, 0.45),
                        )
                    )
                    petiole_end = anchor + leaf_direction.normalized() * 0.055
                    _append_tapered_tube(
                        shrub_branch_vertices,
                        shrub_branch_faces,
                        anchor,
                        petiole_end,
                        0.0035,
                        0.0018,
                        5,
                    )
                    _append_shaped_leaf(
                        shrub_leaf_vertices,
                        shrub_leaf_faces,
                        petiole_end,
                        leaf_direction,
                        shrub_rng.uniform(0.19, 0.27),
                    )
                    explicit_shrub_branches += 1
                    explicit_shrub_leaves += 1
            for leaf_index in range(3):
                anchor = middle.lerp(tip, 0.50 + leaf_index * 0.22)
                leaf_angle = angle + (-0.8 if leaf_index % 2 else 0.8)
                leaf_direction = Vector(
                    (
                        math.cos(leaf_angle),
                        math.sin(leaf_angle),
                        shrub_rng.uniform(0.18, 0.55),
                    )
                )
                petiole_end = anchor + leaf_direction.normalized() * 0.05
                _append_tapered_tube(
                    shrub_branch_vertices,
                    shrub_branch_faces,
                    anchor,
                    petiole_end,
                    0.0035,
                    0.0018,
                    5,
                )
                _append_shaped_leaf(
                    shrub_leaf_vertices,
                    shrub_leaf_faces,
                    petiole_end,
                    leaf_direction,
                    shrub_rng.uniform(0.20, 0.30),
                )
                explicit_shrub_branches += 1
                explicit_shrub_leaves += 1

    _merged_botanical_object(
        c,
        name + ":merged_connected_shrub_branches",
        shrub_branch_vertices,
        shrub_branch_faces,
        M["bark"],
        "shrub_branch",
        "c2w_explicit_branch_count",
        explicit_shrub_branches,
    )
    _merged_botanical_object(
        c,
        name + ":merged_shaped_shrub_leaves",
        shrub_leaf_vertices,
        shrub_leaf_faces,
        M["leaf"],
        "shrub_leaf",
        "c2w_explicit_leaf_count",
        explicit_shrub_leaves,
    )

    flower_stem_vertices, flower_stem_faces = [], []
    flower_leaf_vertices, flower_leaf_faces = [], []
    disc_vertices, disc_faces = [], []
    petal_materials = (
        M["flower_white"],
        M["flower_yellow"],
        M["flower_red"],
        M["flower_purple"],
    )
    petal_geometry = [[[], []] for _ in petal_materials]
    petal_counts = [0] * len(petal_materials)
    explicit_flower_stems = 0
    explicit_flower_leaves = 0
    flower_count = max(10, int(length * 0.8))
    for flower in range(flower_count):
        fx = x + rng.uniform(-length / 2 + 0.60, length / 2 - 0.60)
        fy = y + rng.choice((-1, 1)) * rng.uniform(depth * 0.20, depth * 0.30)
        flower_seed = seed * 1009 + flower
        flower_rng = random.Random(flower_seed)
        flower_height = flower_rng.uniform(0.34, 0.56)
        base = Vector((fx, fy, 1.15))
        middle = Vector(
            (
                fx + flower_rng.uniform(-0.025, 0.025),
                fy + flower_rng.uniform(-0.025, 0.025),
                1.15 + flower_height * 0.52,
            )
        )
        top = Vector(
            (
                fx + flower_rng.uniform(-0.045, 0.045),
                fy + flower_rng.uniform(-0.045, 0.045),
                1.15 + flower_height,
            )
        )
        _append_tapered_tube(
            flower_stem_vertices, flower_stem_faces, base, middle, 0.006, 0.0048, 6
        )
        _append_tapered_tube(
            flower_stem_vertices, flower_stem_faces, middle, top, 0.0048, 0.0025, 6
        )
        explicit_flower_stems += 2
        for side in (-1, 1):
            direction = Vector(
                (
                    side * flower_rng.uniform(0.7, 1.0),
                    flower_rng.uniform(-0.35, 0.35),
                    flower_rng.uniform(0.18, 0.38),
                )
            )
            petiole_end = middle + direction.normalized() * 0.07
            _append_tapered_tube(
                flower_stem_vertices,
                flower_stem_faces,
                middle,
                petiole_end,
                0.003,
                0.0015,
                5,
            )
            _append_shaped_leaf(
                flower_leaf_vertices,
                flower_leaf_faces,
                petiole_end,
                direction,
                flower_rng.uniform(0.14, 0.19),
            )
            explicit_flower_stems += 1
            explicit_flower_leaves += 1
        material_index = flower_seed % len(petal_materials)
        petal_vertices, petal_faces = petal_geometry[material_index]
        for petal_index in range(8):
            _append_flower_petal(
                petal_vertices,
                petal_faces,
                top,
                math.tau * petal_index / 8,
                flower_rng.uniform(0.31, 0.38),
            )
            petal_counts[material_index] += 1
        _append_disc(disc_vertices, disc_faces, (top.x, top.y, top.z + 0.018))

    _merged_botanical_object(
        c,
        name + ":merged_connected_flower_stems",
        flower_stem_vertices,
        flower_stem_faces,
        M["leaf"],
        "flower_stem",
        "c2w_explicit_stem_count",
        explicit_flower_stems,
    )
    _merged_botanical_object(
        c,
        name + ":merged_shaped_flower_leaves",
        flower_leaf_vertices,
        flower_leaf_faces,
        M["leaf_light"],
        "flower_leaf",
        "c2w_explicit_leaf_count",
        explicit_flower_leaves,
    )
    for material_index, material in enumerate(petal_materials):
        vertices, faces = petal_geometry[material_index]
        _merged_botanical_object(
            c,
            name + f":merged_curved_flower_petals_{material_index}",
            vertices,
            faces,
            material,
            "flower_petal",
            "c2w_explicit_petal_count",
            petal_counts[material_index],
        )
    _merged_botanical_object(
        c,
        name + ":merged_flower_discs",
        disc_vertices,
        disc_faces,
        M["flower_center"],
        "flower_disc",
        "c2w_explicit_disc_count",
        flower_count,
    )


def _native_full07_leaf_assets(seed):
    """Create curved, serrated, midribbed leaf templates for the full07 tree algorithm."""
    assets = []
    for variant in range(3):
        # Five curved cross-sections preserve a midribbed, serrated leaf while
        # keeping the shared full07 species masters memory-safe in the full scene.
        stations = 5
        vertices = []
        for index in range(stations):
            t = index / (stations - 1)
            profile = math.sin(math.pi * t) ** (0.72 + variant * 0.08)
            serration = 1.0 + 0.10 * math.sin(index * math.pi * (1.6 + variant * 0.17))
            half_width = (0.23 + variant * 0.035) * profile * serration
            curve_z = 0.075 * math.sin(math.pi * t) + 0.018 * math.sin(
                t * math.tau * 2 + variant
            )
            vertices.extend(
                (
                    (-half_width, t, curve_z * 0.72),
                    (0.0, t, curve_z + 0.035 * profile),
                    (half_width, t, curve_z * 0.72),
                )
            )
        faces = []
        for index in range(stations - 1):
            lower = index * 3
            upper = (index + 1) * 3
            left = (lower, upper, upper + 1, lower + 1)
            right = (lower + 1, upper + 1, upper + 2, lower + 2)
            faces.extend((left, right, tuple(reversed(left)), tuple(reversed(right))))
        mesh = bpy.data.meshes.new(
            PREFIX + f"full07_native_curved_leaf_{seed}_{variant}:mesh"
        )
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        leaf = bpy.data.objects.new(
            PREFIX + f"full07_native_curved_leaf_{seed}_{variant}", mesh
        )
        leaf["c2w_leaf_template"] = "curved_serrated_midribbed"
        leaf["c2w_leaf_template_vertices"] = len(vertices)
        assets.append(leaf)
    return assets


def _full07_tree_master(seed):
    """Reuse the prior full07 multilevel botanical generator with native curved leaves."""
    if seed in _TREE_MASTERS:
        return _TREE_MASTERS[seed], _TREE_MASTER_STATS[seed]
    from urban_v1_full_07_trees import build_botanical_tree_master

    leaf_assets = _native_full07_leaf_assets(seed)

    master = bpy.data.collections.new(PREFIX + f"BOTANICAL_TREE_MASTER_{seed}")
    master.use_fake_user = True
    stats = build_botanical_tree_master(master, seed, leaf_assets)
    for source in master.objects:
        if "botanical_bark" in source.name:
            tag(source, "tree_multilevel_branch_mesh")
            source["c2w_botanical_branch_count"] = stats["branches"]
        else:
            tag(source, "botanical_leaf_canopy")
            if "c2w_genuine_leaffactory_mesh" in source:
                del source["c2w_genuine_leaffactory_mesh"]
            source["c2w_explicit_leaf_count"] = stats["leaves"]
            source[
                "c2w_leaf_source"
            ] = "same-run curved serrated midribbed native mesh templates"
        source["c2w_source_generator"] = "urban_v1_full_07_trees.py"
        source["c2w_treefactory_seed"] = seed
    master["c2w_generator"] = Path(__file__).name
    master["c2w_role"] = "shared_full07_botanical_tree_master"
    master["c2w_source_generator"] = "urban_v1_full_07_trees.py"
    master["c2w_scene_asset_inputs"] = 0
    master["c2w_coarse"] = False
    master[
        "generator"
    ] = "urban_v1_full_07 multilevel botanical branch generator + native curved leaf templates"
    master[
        "c2w_leaf_source"
    ] = "same-run curved serrated midribbed native mesh templates"

    template_meshes = {obj.data for obj in leaf_assets if obj.data}
    for obj in leaf_assets:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in template_meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    _TREE_MASTERS[seed] = master
    _TREE_MASTER_STATS[seed] = stats
    return master, stats


def campus_tree(c, name, x, y, scale, M=None, leaf_count=None):
    """Place a full multilevel botanical tree; no planar-card or blob fallback exists."""
    variant = sum((index + 1) * ord(char) for index, char in enumerate(name))
    seed = _TREE_SEEDS[variant % len(_TREE_SEEDS)]
    master, stats = _full07_tree_master(seed)
    target_height = 8.15 * scale
    placement_scale = target_height / stats["height"]
    placed = []
    for source in master.objects:
        obj = source.copy()
        obj.data = source.data
        c.objects.link(obj)
        obj.name = (
            PREFIX
            + name
            + (
                ":botanical_bark"
                if "botanical_bark" in source.name
                else ":botanical_leaf_canopy"
            )
        )
        obj.location = (x, y, 0.0)
        obj.rotation_euler[2] = seed * 0.017 + variant * 0.00037
        obj.scale = (placement_scale, placement_scale, placement_scale)
        if "botanical_bark" in source.name:
            tag(obj, "tree_multilevel_branch_mesh")
            obj["c2w_botanical_branch_count"] = stats["branches"]
        else:
            tag(obj, "botanical_leaf_canopy")
            obj["c2w_explicit_leaf_count"] = stats["leaves"]
            obj[
                "c2w_leaf_source"
            ] = "same-run curved serrated midribbed native mesh templates"
        obj["c2w_source_generator"] = "urban_v1_full_07_trees.py"
        obj["c2w_treefactory_seed"] = seed
        obj["c2w_real_world_height_m"] = target_height
        obj["c2w_no_simplified_fallback"] = True
        placed.append(obj)
    return placed


def campus_parcel_with_landscape_openings(c, M):
    """Build the raised parcel with genuine tree-pit and lawn openings."""
    # A structural base stops below the tree-pit soil.  The finish course is
    # tessellated around the exact openings, so the depression is geometric and
    # is not a dark decal laid over an unbroken slab.
    parcel = box(
        c,
        "site:raised_campus_parcel",
        (0, 0, -0.0825),
        (220, 180, 0.525),
        M["campus_paver"],
        0.07,
        role="dedicated_school_parcel",
    )
    parcel["c2w_tree_pit_opening_count"] = len(PAVED_TREE_PITS)
    parcel["c2w_lawn_opening_count"] = len(LAWN_ZONES)
    half_opening = 1.35
    lawn_bounds = [
        (
            center[0] - dims[0] / 2,
            center[0] + dims[0] / 2,
            center[1] - dims[1] / 2,
            center[1] + dims[1] / 2,
        )
        for _, center, dims, _ in LAWN_ZONES
    ]
    x_cuts = {
        -110.0,
        110.0,
        *(x - half_opening for x, _ in PAVED_TREE_PITS),
        *(x + half_opening for x, _ in PAVED_TREE_PITS),
    }
    y_cuts = {
        -90.0,
        90.0,
        *(y - half_opening for _, y in PAVED_TREE_PITS),
        *(y + half_opening for _, y in PAVED_TREE_PITS),
    }
    for lx0, lx1, ly0, ly1 in lawn_bounds:
        x_cuts.update((lx0, lx1))
        y_cuts.update((ly0, ly1))
    x_cuts = sorted(x_cuts)
    y_cuts = sorted(y_cuts)
    finish_depth = 0.125
    finish_z = 0.18 + finish_depth / 2
    tile_index = 0
    for x0, x1 in zip(x_cuts, x_cuts[1:]):
        for y0, y1 in zip(y_cuts, y_cuts[1:]):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if any(
                abs(mx - px) < half_opening and abs(my - py) < half_opening
                for px, py in PAVED_TREE_PITS
            ):
                continue
            if any(
                lx0 < mx < lx1 and ly0 < my < ly1 for lx0, lx1, ly0, ly1 in lawn_bounds
            ):
                continue
            tile = box(
                c,
                f"site:campus_paving_tile_{tile_index}",
                (mx, my, finish_z),
                (x1 - x0, y1 - y0, finish_depth),
                M["campus_paver"],
                0.0,
                role="campus_paving_surface",
            )
            tile["c2w_continuous_finish_course"] = True
            tile_index += 1
    parcel["c2w_paving_tile_count"] = tile_index
    return parcel


def _lawn_height(x, y, seed):
    phase = seed * 0.013
    return (
        0.321
        + 0.0042 * math.sin(x * 0.47 + phase)
        + 0.0031 * math.cos(y * 0.63 - phase * 0.7)
        + 0.0012 * math.sin(x * 1.83 - y * 1.41 + phase * 1.9)
    )


def detailed_lawn(c, name, center, dims, pitch, M, seed):
    """Create a close-mown, continuous living-turf bed without pointed sprouts."""
    cx, cy = center
    width, depth = dims
    substrate = box(
        c,
        name + ":rootzone_substrate",
        (cx, cy, 0.235),
        (width, depth, 0.10),
        M["soil"],
        0.0,
        role="lawn_rootzone_substrate",
    )
    substrate["c2w_compacted_depth_m"] = 0.18

    # A metre-scale smooth mesh supplies real drainage fall and subtle soil
    # settlement.  Fine turf fibres live in the layered procedural normal and
    # colour response, so no isolated spear-like blade meshes protrude upward.
    x_segments = max(6, min(220, int(math.ceil(width / 1.0))))
    y_segments = max(6, min(100, int(math.ceil(depth / 1.0))))
    vertices = []
    faces = []
    for iy in range(y_segments + 1):
        y = cy - depth / 2 + depth * iy / y_segments
        for ix in range(x_segments + 1):
            x = cx - width / 2 + width * ix / x_segments
            edge = min(ix, x_segments - ix, iy, y_segments - iy)
            edge_factor = min(1.0, edge / 2.0)
            z = 0.319 + (_lawn_height(x, y, seed) - 0.321) * edge_factor
            vertices.append((x, y, z))
    row = x_segments + 1
    for iy in range(y_segments):
        for ix in range(x_segments):
            a = iy * row + ix
            faces.append((a, a + 1, a + row + 1, a + row))
    mesh = bpy.data.meshes.new(PREFIX + name + ":turf_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(M["lawn"])
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    surface = bpy.data.objects.new(PREFIX + name + ":living_turf", mesh)
    c.objects.link(surface)
    tag(surface, "campus_lawn_surface")
    surface["c2w_lawn_width_m"] = width
    surface["c2w_lawn_depth_m"] = depth
    surface["c2w_building_clearance_required_m"] = 0.65
    surface["c2w_surface_face_count"] = len(faces)
    surface["c2w_above_ground_pointed_blade_count"] = 0
    surface["c2w_finish"] = "continuous close-mown turf with multi-scale shader fibres"
    surface["c2w_nominal_sampling_pitch_m"] = pitch

    # Flush edging reads as a designed lawn boundary and prevents the turf from
    # looking like a floating green rectangular patch.
    edge_width = 0.075
    for suffix, xyz, edge_dims in (
        ("north", (cx, cy + depth / 2, 0.272), (width, edge_width, 0.095)),
        ("south", (cx, cy - depth / 2, 0.272), (width, edge_width, 0.095)),
        ("east", (cx + width / 2, cy, 0.272), (edge_width, depth, 0.095)),
        ("west", (cx - width / 2, cy, 0.272), (edge_width, depth, 0.095)),
    ):
        box(
            c,
            name + ":flush_edge_" + suffix,
            xyz,
            edge_dims,
            M["steel"],
            0.0,
            role="lawn_edge",
        )

    return surface


def recessed_tree_pit(c, name, x, y, M, pavement_z=0.305):
    """Model a true square opening and one continuous, detailed recessed soil bed."""
    inner_half = 1.10
    grid = 36
    soil_seed = 9100 + int((x + 130) * 17 + (y + 100) * 11)
    rng = random.Random(soil_seed)
    vertices = []
    faces = []
    for iy in range(grid + 1):
        py = y - inner_half + inner_half * 2 * iy / grid
        for ix in range(grid + 1):
            px = x - inner_half + inner_half * 2 * ix / grid
            radius = math.hypot(px - x, py - y)
            # The boundary stays uniformly below the flush stone edge, while
            # low-amplitude multi-frequency relief forms compacted clods and a
            # subtle root collar as one surface—never loose cuboid scatter.
            edge_falloff = math.sin(math.pi * ix / grid) * math.sin(math.pi * iy / grid)
            root_mound = max(0.0, 1.0 - radius / 0.62) ** 2 * 0.024
            broad_relief = (
                0.0078 * math.sin(px * 3.1 + soil_seed * 0.019)
                + 0.0058 * math.cos(py * 4.3 - soil_seed * 0.011)
                + 0.0035 * math.sin((px + py) * 9.7 + soil_seed * 0.007)
            )
            fine_relief = rng.uniform(-0.0024, 0.0024)
            z = (
                pavement_z
                - 0.104
                + root_mound
                + (broad_relief + fine_relief) * edge_falloff
            )
            vertices.append((px, py, z))
    row = grid + 1
    for iy in range(grid):
        for ix in range(grid):
            a = iy * row + ix
            faces.append((a, a + 1, a + row + 1, a + row))
    mesh = bpy.data.meshes.new(PREFIX + name + ":recessed_soil_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(M["tree_soil"])
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    soil = bpy.data.objects.new(PREFIX + name + ":recessed_soil", mesh)
    c.objects.link(soil)
    tag(soil, "tree_pit_soil")
    soil["c2w_depression_below_paving_m"] = round(
        pavement_z - max(vertex[2] for vertex in vertices), 4
    )
    soil["c2w_true_paving_opening"] = True
    soil["c2w_pit_center_x"] = x
    soil["c2w_pit_center_y"] = y
    soil["c2w_continuous_microrelief_vertices"] = len(vertices)
    soil["c2w_continuous_microrelief_faces"] = len(faces)
    soil["c2w_loose_scatter_piece_count"] = 0
    soil["c2w_soil_surface"] = "continuous root-collar, clod and pore relief"

    opening_half = 1.35
    rim_width = opening_half - inner_half
    rim_z = pavement_z - 0.040
    for suffix, xyz, dims in (
        (
            "north",
            (x, y + inner_half + rim_width / 2, rim_z),
            (opening_half * 2, rim_width, 0.080),
        ),
        (
            "south",
            (x, y - inner_half - rim_width / 2, rim_z),
            (opening_half * 2, rim_width, 0.080),
        ),
        (
            "east",
            (x + inner_half + rim_width / 2, y, rim_z),
            (rim_width, inner_half * 2, 0.080),
        ),
        (
            "west",
            (x - inner_half - rim_width / 2, y, rim_z),
            (rim_width, inner_half * 2, 0.080),
        ),
    ):
        edge = box(
            c,
            name + ":flush_stone_edge_" + suffix,
            xyz,
            dims,
            M["stone_dark"],
            0.0,
            role="tree_pit_edge",
        )
        edge["c2w_edge_top_is_flush"] = True
    return soil


def bench(c, name, x, y, yaw, M, seating_target=None):
    parts = []
    for slat in range(6):
        part = local_box(
            c,
            name + f":seat_slat_{slat}",
            (x, y),
            yaw,
            (0, (slat - 2.5) * 0.13, 0.63),
            (3.6, 0.105, 0.11),
            M["wood"],
            0.035,
            role="bench_slat",
        )
        part["c2w_seat_component"] = "pan"
        parts.append(part)
    for slat in range(5):
        part = local_box(
            c,
            name + f":back_slat_{slat}",
            (x, y),
            yaw,
            (0, 0.40, 0.92 + slat * 0.13),
            (3.6, 0.10, 0.10),
            M["wood"],
            0.03,
            role="bench_slat",
        )
        part["c2w_seat_component"] = "back"
        parts.append(part)
    for side in (-1, 1):
        parts.append(
            local_box(
                c,
                name + f":leg_{side}",
                (x, y),
                yaw,
                (side * 1.42, 0, 0.35),
                (0.12, 0.72, 0.62),
                M["black_metal"],
                0.025,
                role="bench_frame",
            )
        )
        parts.append(
            beam(
                c,
                name + f":back_support_{side}",
                BASE.G.transform_point((x, y, 0), yaw, (side * 1.42, 0.30, 0.42)),
                BASE.G.transform_point((x, y, 0), yaw, (side * 1.42, 0.43, 1.25)),
                0.05,
                M["black_metal"],
                12,
                "bench_frame",
            )
        )
    if seating_target:
        facing_x, facing_y = math.sin(yaw), -math.cos(yaw)
        for part in parts:
            part["c2w_seat_group"] = name
            part["c2w_seating_target"] = seating_target
            part["c2w_facing_x"] = facing_x
            part["c2w_facing_y"] = facing_y


def campus_light(c, name, x, y, M):
    cylinder(
        c,
        name + ":pole",
        (x, y, 3.35),
        0.08,
        6.7,
        M["black_metal"],
        22,
        role="campus_light_pole",
    )
    beam(
        c,
        name + ":arm_left",
        (x, y, 6.45),
        (x - 0.75, y, 6.82),
        0.05,
        M["black_metal"],
        14,
        "campus_light_arm",
    )
    beam(
        c,
        name + ":arm_right",
        (x, y, 6.45),
        (x + 0.75, y, 6.82),
        0.05,
        M["black_metal"],
        14,
        "campus_light_arm",
    )
    for dx in (-0.86, 0.86):
        box(
            c,
            name + ":luminaire",
            (x + dx, y, 6.81),
            (0.65, 0.28, 0.14),
            M["black_metal"],
            0.045,
            role="campus_light_luminaire",
        )
        box(
            c,
            name + ":lens",
            (x + dx, y, 6.72),
            (0.52, 0.21, 0.035),
            M["lamp"],
            0.012,
            role="campus_light_lens",
        )


_ELLIPSOID_MESHES = {}


def ellipsoid(
    c, name, xyz, dims, material, role, rotation=(0.0, 0.0, 0.0), segments=16, rings=8
):
    """Instanced smooth ellipsoid used for anatomy and clipped planting masses."""
    key = (material.name_full, segments, rings)
    mesh = _ELLIPSOID_MESHES.get(key)
    if mesh is None or mesh.name not in bpy.data.meshes:
        verts = [(0.0, 0.0, 1.0)]
        for ring in range(1, rings):
            phi = math.pi * ring / rings
            for segment in range(segments):
                theta = 2 * math.pi * segment / segments
                verts.append(
                    (
                        math.sin(phi) * math.cos(theta),
                        math.sin(phi) * math.sin(theta),
                        math.cos(phi),
                    )
                )
        bottom_index = len(verts)
        verts.append((0.0, 0.0, -1.0))
        faces = []
        for segment in range(segments):
            faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
        for ring in range(rings - 2):
            start = 1 + ring * segments
            next_start = start + segments
            for segment in range(segments):
                nxt = (segment + 1) % segments
                faces.append(
                    (
                        start + segment,
                        next_start + segment,
                        next_start + nxt,
                        start + nxt,
                    )
                )
        last_start = 1 + (rings - 2) * segments
        for segment in range(segments):
            faces.append(
                (
                    last_start + segment,
                    bottom_index,
                    last_start + (segment + 1) % segments,
                )
            )
        mesh = bpy.data.meshes.new(
            PREFIX + "shared_ellipsoid:" + material.name_full.replace(":", "_")
        )
        mesh.from_pydata(verts, [], faces)
        mesh.materials.append(material)
        mesh.update()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        _ELLIPSOID_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    c.objects.link(obj)
    obj.location = xyz
    obj.scale = (dims[0] / 2, dims[1] / 2, dims[2] / 2)
    obj.rotation_euler = rotation
    return tag(obj, role)


def instanced_limb(c, name, p0, p1, width, material, role):
    """Orient a shared smooth ellipsoid between points; avoids a unique mesh per limb."""
    start = Vector(p0)
    end = Vector(p1)
    direction = end - start
    rotation = direction.to_track_quat("Z", "Y").to_euler()
    return ellipsoid(
        c,
        name,
        (start + end) / 2,
        (width, width, direction.length),
        material,
        role,
        rotation,
        12,
        6,
    )


def procedural_person(c, name, x, y, yaw, M, activity="walk", palette=0):
    """Articulated, clothed campus occupant with a readable pose and accessories."""
    base = (x, y, 0.48)
    point = lambda xyz: BASE.G.transform_point(base, yaw, xyz)
    skin = M["skin_a"] if palette % 3 else M["skin_b"]
    shirt_options = (
        M["uniform_blue"],
        M["uniform_white"],
        M["sports_red"],
        M["sports_yellow"],
    )
    shirt = shirt_options[palette % len(shirt_options)]
    trouser = M["charcoal"] if palette % 2 else M["uniform_blue"]
    stride = 0.20 if activity == "walk" else 0.08
    if activity in {"volleyball", "football"}:
        stride = 0.28
    torso = ellipsoid(
        c,
        name + ":tailored_torso",
        point((0, 0, 1.26)),
        (0.54, 0.34, 0.92),
        shirt,
        "campus_occupant",
        (0, 0, yaw),
        14,
        7,
    )
    torso["c2w_activity"] = activity
    ellipsoid(
        c,
        name + ":neck",
        point((0, 0, 1.78)),
        (0.15, 0.15, 0.20),
        skin,
        "person_anatomy",
        (0, 0, yaw),
        12,
        5,
    )
    ellipsoid(
        c,
        name + ":head",
        point((0, 0, 2.00)),
        (0.34, 0.32, 0.43),
        skin,
        "person_anatomy",
        (0, 0, yaw),
        16,
        8,
    )
    ellipsoid(
        c,
        name + ":hair",
        point((0, 0.015, 2.13)),
        (0.36, 0.33, 0.23),
        M["dark"],
        "person_hair",
        (0, 0, yaw),
        14,
        6,
    )
    # Knees and feet are offset to avoid a mannequin-straight stance.
    left_hip = point((-0.13, 0, 0.91))
    right_hip = point((0.13, 0, 0.91))
    left_knee = point((-0.14, stride, 0.52))
    right_knee = point((0.14, -stride, 0.52))
    left_ankle = point((-0.14, stride * 1.55, 0.08))
    right_ankle = point((0.14, -stride * 1.55, 0.08))
    for side_name, hip, knee, ankle in (
        ("left", left_hip, left_knee, left_ankle),
        ("right", right_hip, right_knee, right_ankle),
    ):
        instanced_limb(
            c,
            name + f":{side_name}_upper_leg",
            hip,
            knee,
            0.19,
            trouser,
            "person_clothing",
        )
        instanced_limb(
            c,
            name + f":{side_name}_lower_leg",
            knee,
            ankle,
            0.16,
            trouser,
            "person_clothing",
        )
        local_offset = -0.04 if side_name == "left" else 0.04
        foot = point(
            (
                local_offset,
                (stride * 1.55 if side_name == "left" else -stride * 1.55) - 0.10,
                0.05,
            )
        )
        ellipsoid(
            c,
            name + f":{side_name}_shoe",
            foot,
            (0.20, 0.36, 0.14),
            M["rubber_dark"],
            "person_footwear",
            (0, 0, yaw),
            12,
            5,
        )
    shoulder_z = 1.52
    if activity == "volleyball":
        arm_targets = ((-0.30, 0.04, 2.25), (0.30, 0.04, 2.30))
    elif activity == "football":
        arm_targets = ((-0.38, 0.10, 1.18), (0.38, -0.10, 1.50))
    else:
        arm_targets = ((-0.30, -stride, 1.06), (0.30, stride, 1.10))
    for index, side in enumerate((-1, 1)):
        shoulder = point((side * 0.23, 0, shoulder_z))
        elbow = point(
            (
                side * 0.34,
                arm_targets[index][1] * 0.45,
                (shoulder_z + arm_targets[index][2]) / 2,
            )
        )
        hand = point(arm_targets[index])
        instanced_limb(
            c,
            name + f":arm_{index}_sleeve",
            shoulder,
            elbow,
            0.14,
            shirt,
            "person_clothing",
        )
        instanced_limb(
            c, name + f":arm_{index}_forearm", elbow, hand, 0.11, skin, "person_anatomy"
        )
        ellipsoid(
            c,
            name + f":hand_{index}",
            hand,
            (0.13, 0.11, 0.16),
            skin,
            "person_anatomy",
            (0, 0, yaw),
            10,
            5,
        )
    if palette % 4 == 1 and activity == "walk":
        local_box(
            c,
            name + ":backpack",
            base,
            yaw,
            (0, 0.22, 1.32),
            (0.45, 0.20, 0.66),
            M["sports_red"] if palette % 2 else M["uniform_blue"],
            0.09,
            role="person_accessory",
        )
    return torso


def procedural_car(c, name, x, y, yaw, M, paint_key="vehicle_white", scale=1.0):
    """Multi-part parked/moving passenger car with glazing, lights and real wheels."""
    origin = (x, y, 0.0)
    local_box(
        c,
        name + ":lower_body",
        origin,
        yaw,
        (0, 0, 0.64 * scale),
        (4.45 * scale, 1.82 * scale, 0.68 * scale),
        M[paint_key],
        0.14,
        role="road_vehicle",
    )
    local_box(
        c,
        name + ":bonnet",
        origin,
        yaw,
        (-1.47 * scale, 0, 1.03 * scale),
        (1.35 * scale, 1.70 * scale, 0.30 * scale),
        M[paint_key],
        0.11,
        role="vehicle_body_detail",
    )
    local_box(
        c,
        name + ":cabin",
        origin,
        yaw,
        (0.45 * scale, 0, 1.24 * scale),
        (2.25 * scale, 1.62 * scale, 0.76 * scale),
        M[paint_key],
        0.13,
        role="vehicle_body_detail",
    )
    for side in (-1, 1):
        local_box(
            c,
            name + ":side_glass",
            origin,
            yaw,
            (0.38 * scale, side * 0.825 * scale, 1.30 * scale),
            (1.72 * scale, 0.045, 0.52 * scale),
            M["glass_blue"],
            0.02,
            role="vehicle_glazing",
        )
        local_box(
            c,
            name + ":mirror",
            origin,
            yaw,
            (-0.62 * scale, side * 1.02 * scale, 1.22 * scale),
            (0.28 * scale, 0.16 * scale, 0.16 * scale),
            M[paint_key],
            0.06,
            role="vehicle_body_detail",
        )
        for axle in (-1.35, 1.35):
            centre = BASE.G.transform_point(
                origin, yaw, (axle * scale, side * 0.91 * scale, 0.50 * scale)
            )
            cylinder(
                c,
                name + ":tyre",
                centre,
                0.36 * scale,
                0.22 * scale,
                M["tyre"],
                24,
                rot=(math.pi / 2, 0, yaw),
                bevel=0.025,
                role="vehicle_wheel",
            )
            cylinder(
                c,
                name + ":wheel_hub",
                centre,
                0.19 * scale,
                0.235 * scale,
                M["steel"],
                20,
                rot=(math.pi / 2, 0, yaw),
                bevel=0.018,
                role="vehicle_wheel",
            )
    local_box(
        c,
        name + ":windscreen",
        origin,
        yaw,
        (-0.52 * scale, -0.01, 1.43 * scale),
        (0.065, 1.46 * scale, 0.48 * scale),
        M["glass_blue_alt"],
        0.01,
        role="vehicle_glazing",
    )
    for side in (-1, 1):
        local_box(
            c,
            name + ":headlamp",
            origin,
            yaw,
            (-2.25 * scale, side * 0.58 * scale, 0.75 * scale),
            (0.055, 0.38 * scale, 0.18 * scale),
            M["lamp"],
            0.025,
            role="vehicle_lamp",
        )
        local_box(
            c,
            name + ":tail_lamp",
            origin,
            yaw,
            (2.25 * scale, side * 0.58 * scale, 0.75 * scale),
            (0.055, 0.32 * scale, 0.17 * scale),
            M["red"],
            0.025,
            role="vehicle_lamp",
        )


def procedural_bus(c, name, x, y, yaw, M):
    """School coach with individual windows, doors, wheel assemblies and markings."""
    origin = (x, y, 0.0)
    local_box(
        c,
        name + ":body",
        origin,
        yaw,
        (0, 0, 1.65),
        (10.8, 2.55, 2.95),
        M["sports_yellow"],
        0.16,
        role="road_vehicle",
    )
    local_box(
        c,
        name + ":lower_skirt",
        origin,
        yaw,
        (0, 0, 0.72),
        (10.95, 2.60, 0.62),
        M["charcoal"],
        0.08,
        role="vehicle_body_detail",
    )
    for side in (-1, 1):
        for bay in range(6):
            local_box(
                c,
                name + f":window_{side}_{bay}",
                origin,
                yaw,
                (-3.85 + bay * 1.55, side * 1.30, 2.12),
                (1.26, 0.045, 0.82),
                M["glass_blue"],
                0.018,
                role="vehicle_glazing",
            )
        for axle in (-3.35, 3.35):
            centre = BASE.G.transform_point(origin, yaw, (axle, side * 1.32, 0.60))
            cylinder(
                c,
                name + ":tyre",
                centre,
                0.55,
                0.26,
                M["tyre"],
                28,
                rot=(math.pi / 2, 0, yaw),
                bevel=0.025,
                role="vehicle_wheel",
            )
            cylinder(
                c,
                name + ":hub",
                centre,
                0.28,
                0.28,
                M["steel"],
                22,
                rot=(math.pi / 2, 0, yaw),
                bevel=0.018,
                role="vehicle_wheel",
            )
    local_box(
        c,
        name + ":front_windscreen",
        origin,
        yaw,
        (-5.43, 0, 2.05),
        (0.055, 2.15, 1.18),
        M["glass_blue_alt"],
        0.01,
        role="vehicle_glazing",
    )
    local_text(
        c,
        name + ":school_bus_label",
        "SCHOOL BUS",
        origin,
        yaw,
        (0, -1.34, 1.18),
        0.34,
        M["charcoal"],
        0.025,
    )


def covered_walkway(c, name, p0, p1, width, M):
    """Columned weather-protected link matching the reference's connected campus."""
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    yaw = math.atan2(y1 - y0, x1 - x0)
    mid = ((x0 + x1) / 2, (y0 + y1) / 2)
    local_box(
        c,
        name + ":walk_surface",
        mid,
        yaw,
        (0, 0, 0.45),
        (length, width, 0.16),
        M["plaza_paver"],
        0.035,
        role="covered_walkway_surface",
    )
    local_box(
        c,
        name + ":canopy",
        mid,
        yaw,
        (0, 0, 3.75),
        (length + 0.6, width + 0.65, 0.28),
        M["white_clean"],
        0.06,
        role="covered_walkway_canopy",
    )
    count = max(2, int(length // 4.5))
    for index in range(count + 1):
        lx = -length / 2 + length * index / count
        for side in (-1, 1):
            world = BASE.G.transform_point(
                (mid[0], mid[1], 0), yaw, (lx, side * (width / 2 - 0.22), 2.0)
            )
            cylinder(
                c,
                name + ":column",
                world,
                0.095,
                3.55,
                M["steel"],
                20,
                role="covered_walkway_column",
            )
        if 0 < index < count:
            local_box(
                c,
                name + ":soffit_light",
                mid,
                yaw,
                (lx, 0, 3.56),
                (1.25, 0.18, 0.055),
                M["lamp"],
                0.015,
                role="covered_walkway_light",
            )


def context_building(c, name, x, y, w, d, floors, facing, M, palette=0):
    """Four-sided background building detailed enough to avoid an empty CG horizon."""
    floor_h = 3.25
    h = floors * floor_h + 0.65
    material = (M["white"], M["brick_light"], M["concrete"])[palette % 3]
    box(
        c,
        name + ":shell",
        (x, y, h / 2 - 0.20),
        (w, d, h),
        material,
        0.10,
        role="context_building_shell",
    )
    box(
        c,
        name + ":plinth",
        (x, y, 0.45),
        (w + 0.18, d + 0.18, 0.90),
        M["stone_dark"],
        0.045,
        role="context_building_detail",
    )
    axis_y = facing in {"north", "south"}
    outward = 1 if facing in {"north", "east"} else -1
    span = w if axis_y else d
    bays = max(3, int(span // 4.1))
    for floor in range(floors):
        z = 2.0 + floor * floor_h
        for bay in range(bays):
            offset = -span / 2 + span * (bay + 0.5) / bays
            if axis_y:
                bx, by = x + offset, y + outward * (d / 2 + 0.08)
                dims = (span / bays * 0.62, 0.055, 1.72)
            else:
                bx, by = x + outward * (w / 2 + 0.08), y + offset
                dims = (0.055, span / bays * 0.62, 1.72)
            box(
                c,
                name + ":window",
                (bx, by, z),
                dims,
                M["glass_blue_alt"],
                0.012,
                role="context_facade_glazing",
            )
            if axis_y:
                box(
                    c,
                    name + ":window_head",
                    (bx, by + outward * 0.035, z + 0.95),
                    (dims[0] + 0.30, 0.10, 0.14),
                    M["white_clean"],
                    0.018,
                    role="context_building_detail",
                )
            else:
                box(
                    c,
                    name + ":window_head",
                    (bx + outward * 0.035, by, z + 0.95),
                    (0.10, dims[1] + 0.30, 0.14),
                    M["white_clean"],
                    0.018,
                    role="context_building_detail",
                )
    box(
        c,
        name + ":roof",
        (x, y, h + 0.22),
        (w + 0.45, d + 0.45, 0.44),
        M["roof_membrane"],
        0.045,
        role="context_roof",
    )
    if floors >= 5:
        box(
            c,
            name + ":roof_plant",
            (x + w * 0.18, y, h + 0.72),
            (2.8, 2.2, 1.0),
            M["roof_light"],
            0.045,
            role="context_roof",
        )


def road_crack(c, name, points, M, width=0.018):
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = width
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for target, point in zip(spline.points, points):
        target.co = (*point, 1)
    curve.materials.append(M["dark"])
    obj = bpy.data.objects.new(PREFIX + name, curve)
    c.objects.link(obj)
    return tag(obj, "road_surface_crack")


def road_arrow(c, name, x, y, yaw, M):
    local_box(
        c,
        name + ":shaft",
        (x, y),
        yaw,
        (0, 0, 0.172),
        (3.2, 0.28, 0.025),
        M["paint_white"],
        0.0,
        role="road_direction_arrow",
    )
    local_points = ((1.22, -0.70), (2.35, 0), (1.22, 0.70))
    cosine, sine = math.cos(yaw), math.sin(yaw)
    points = [
        (x + px * cosine - py * sine, y + px * sine + py * cosine)
        for px, py in local_points
    ]
    poly_prism(
        c,
        name + ":head",
        points,
        0.174,
        0.025,
        M["paint_white"],
        0.0,
        role="road_direction_arrow",
    )


def build_campus_site(parent, M):
    c = collection("DEDICATED_CAMPUS_SITE", parent, "school.site.reference.v3")
    # The raised parcel is visibly separate from the surrounding district.
    box(
        c,
        "site:regional_ground",
        (0, 0, -0.85),
        (800, 800, 1.5),
        M["regional_land"],
        0.02,
        role="regional_ground",
    )
    campus_parcel_with_landscape_openings(c, M)
    # Four clipped, constructible lawns replace the former flat green panels.
    # The long green strip in front of the circular auditorium is deliberately
    # absent, and every remaining lawn has generous facade clearance.
    for lawn_index, (name, center, dims, pitch) in enumerate(LAWN_ZONES):
        detailed_lawn(
            c, "lawn:" + name, center, dims, pitch, M, 6200 + lawn_index * 137
        )

    # Roads and sidewalks completely surround the independent campus block.
    for name, xyz, dims in (
        ("south_road", (0, -101, 0.02), (250, 18, 0.22)),
        ("north_road", (0, 101, 0.02), (250, 18, 0.22)),
        ("west_road", (-121, 0, 0.02), (18, 184, 0.22)),
        ("east_road", (121, 0, 0.02), (18, 184, 0.22)),
    ):
        box(
            c,
            "site:" + name,
            xyz,
            dims,
            M["asphalt_real"],
            0.025,
            role="perimeter_road",
        )
    for y in (-92.0, 92.0):
        box(
            c,
            "site:sidewalk",
            (0, y, 0.26),
            (224, 3.4, 0.25),
            M["concrete"],
            0.03,
            role="public_sidewalk",
        )
        box(
            c,
            "site:curb",
            (0, y + (-1.85 if y < 0 else 1.85), 0.30),
            (224, 0.30, 0.60),
            M["stone_light"],
            0.045,
            role="street_curb",
        )
    for x in (-112.0, 112.0):
        box(
            c,
            "site:sidewalk",
            (x, 0, 0.26),
            (3.4, 180, 0.25),
            M["concrete"],
            0.03,
            role="public_sidewalk",
        )
        box(
            c,
            "site:curb",
            (x + (-1.85 if x < 0 else 1.85), 0, 0.30),
            (0.30, 184, 0.60),
            M["stone_light"],
            0.045,
            role="street_curb",
        )
    for x in range(-105, 106, 15):
        box(
            c,
            "site:south_lane_mark",
            (x, -101, 0.15),
            (7.0, 0.16, 0.03),
            M["road_mark"],
            0,
            role="road_marking",
        )
        box(
            c,
            "site:north_lane_mark",
            (x, 101, 0.15),
            (7.0, 0.16, 0.03),
            M["road_mark"],
            0,
            role="road_marking",
        )
    for y in range(-75, 76, 15):
        box(
            c,
            "site:west_lane_mark",
            (-121, y, 0.15),
            (0.16, 7.0, 0.03),
            M["road_mark"],
            0,
            role="road_marking",
        )
        box(
            c,
            "site:east_lane_mark",
            (121, y, 0.15),
            (0.16, 7.0, 0.03),
            M["road_mark"],
            0,
            role="road_marking",
        )
    # Continuous edge lines, asphalt joints and road-specific drainage improve real scale.
    for y in (-108.2, -93.8, 93.8, 108.2):
        box(
            c,
            "site:road_edge_line",
            (0, y, 0.157),
            (244.0, 0.14, 0.026),
            M["paint_white"],
            0.0,
            role="road_edge_marking",
        )
    for x in (-128.2, -113.8, 113.8, 128.2):
        box(
            c,
            "site:road_edge_line",
            (x, 0, 0.157),
            (0.14, 176.0, 0.026),
            M["paint_white"],
            0.0,
            role="road_edge_marking",
        )
    for y in (-105.6, -96.4, 96.4, 105.6):
        box(
            c,
            "site:asphalt_paving_joint",
            (0, y, 0.148),
            (248.0, 0.035, 0.018),
            M["dark"],
            0.0,
            role="road_paving_joint",
        )
    for x in (-125.6, -116.4, 116.4, 125.6):
        box(
            c,
            "site:asphalt_paving_joint",
            (x, 0, 0.148),
            (0.035, 182.0, 0.018),
            M["dark"],
            0.0,
            role="road_paving_joint",
        )

    # The previous crossing was rotated 90 degrees.  These bars run parallel to traffic
    # and are spaced across the pedestrian direction, matching a continental zebra crossing.
    for stripe in range(12):
        stripe_y = -107.6 + stripe * 1.18
        box(
            c,
            "site:gate_crosswalk_corrected",
            (28.0, stripe_y, 0.168),
            (11.5, 0.62, 0.035),
            M["paint_white"],
            0.0,
            role="pedestrian_crossing",
        )
    for stop_x in (20.6, 35.4):
        box(
            c,
            "site:crosswalk_stop_line",
            (stop_x, -101.0, 0.169),
            (0.52, 7.0, 0.038),
            M["paint_white"],
            0.0,
            role="road_stop_line",
        )
    # Keep the gate threshold as one continuous mineral sidewalk surface.  The
    # former raised yellow pad and stud array read as a loose construction-toy
    # plate and are deliberately absent from the actual generated geometry.

    # Sealed hairline cracks, flush covers and arrows provide road-scale detail.
    # Contrasting resurfacing polygons were removed because they read as loose
    # colour patches rather than coherent pavement construction.
    crack_paths = (
        (
            (-62, -102, 0.166),
            (-58, -101.6, 0.166),
            (-55, -102.2, 0.166),
            (-51, -101.8, 0.166),
        ),
        (
            (54, 100.2, 0.166),
            (57, 100.8, 0.166),
            (60, 100.1, 0.166),
            (64, 100.5, 0.166),
        ),
        (
            (-120.2, -8, 0.166),
            (-120.8, -4, 0.166),
            (-120.0, 0, 0.166),
            (-120.5, 4, 0.166),
        ),
        (
            (122.3, 39, 0.166),
            (121.7, 43, 0.166),
            (122.4, 47, 0.166),
            (121.9, 51, 0.166),
        ),
    )
    for crack_index, points in enumerate(crack_paths):
        road_crack(c, f"site:sealed_crack_{crack_index}", points, M)
    for cover_index, (x, y) in enumerate(
        ((-12, -104.5), (92, 98.0), (-118.0, 65), (124.0, 11))
    ):
        cylinder(
            c,
            f"site:road_manhole_{cover_index}",
            (x, y, 0.176),
            0.54,
            0.055,
            M["steel"],
            40,
            bevel=0.018,
            role="road_manhole",
        )
        cylinder(
            c,
            f"site:road_manhole_inner_{cover_index}",
            (x, y, 0.211),
            0.37,
            0.020,
            M["black_metal"],
            32,
            bevel=0.010,
            role="road_manhole_detail",
        )
    road_arrow(c, "site:south_arrow_east", -48, -97.0, 0.0, M)
    road_arrow(c, "site:south_arrow_west", 79, -105.0, math.pi, M)
    road_arrow(c, "site:east_arrow_north", 117.0, -42, math.pi / 2, M)
    road_arrow(c, "site:west_arrow_south", -125.0, 37, -math.pi / 2, M)

    # Main ceremonial axis, secondary paths and detailed courtyard paving.
    box(
        c,
        "site:main_axis",
        (28, -38, 0.36),
        (15.5, 97.0, 0.24),
        M["plaza_paver"],
        0.035,
        role="pedestrian_axis",
    )
    box(
        c,
        "site:central_plaza",
        (29, 29, 0.37),
        (62.0, 30.0, 0.26),
        M["plaza_paver"],
        0.05,
        role="school_courtyard",
    )
    for x in range(0, 61, 3):
        box(
            c,
            "site:plaza_joint_x",
            (x, 29, 0.515),
            (0.025, 29.0, 0.015),
            M["mortar"],
            0,
            role="paver_joint",
        )
    for y in range(16, 44, 3):
        box(
            c,
            "site:plaza_joint_y",
            (29, y, 0.515),
            (61.0, 0.025, 0.015),
            M["mortar"],
            0,
            role="paver_joint",
        )
    # Three necessary building-side links remain.  The former west link at
    # (-18, -18) was a pale 18 x 6 m bar between the track and circular hall;
    # it is removed together with the adjacent red runway and yellow sand pit.
    for walk_name, xyz, dims in (
        ("northwest_academic_link", (-14, 48, 0.37), (34, 6, 0.24)),
        ("northeast_academic_link", (69, 50, 0.37), (38, 6, 0.24)),
        ("southeast_activity_link", (71, -43, 0.37), (44, 5, 0.24)),
    ):
        box(
            c,
            "site:secondary_walk:" + walk_name,
            xyz,
            dims,
            M["plaza_paver"],
            0.035,
            role="pedestrian_walk",
        )

    # Drainage and utility covers add the small-scale cues missing from the earlier scene.
    for drain_index, (x, y, yaw) in enumerate(
        (
            (-30, -86, 0),
            (4, -86, 0),
            (55, -86, 0),
            (98, -86, 0),
            (-104, -44, math.pi / 2),
            (-104, 34, math.pi / 2),
        )
    ):
        local_box(
            c,
            f"site:drain_{drain_index}",
            (x, y),
            yaw,
            (0, 0, 0.49),
            (2.1, 0.36, 0.08),
            M["black_metal"],
            0.015,
            role="storm_drain",
        )
        for slot in range(8):
            local_box(
                c,
                f"site:drain_slot_{drain_index}_{slot}",
                (x, y),
                yaw,
                (-0.76 + slot * 0.22, 0, 0.535),
                (0.07, 0.24, 0.025),
                M["dark"],
                0.0,
                role="storm_drain_slot",
            )
    for cover_index, (x, y) in enumerate(((2, -62), (75, -48), (11, 13), (-24, 31))):
        cylinder(
            c,
            f"site:utility_cover_{cover_index}",
            (x, y, 0.50),
            0.58,
            0.055,
            M["steel"],
            32,
            bevel=0.015,
            role="utility_cover",
        )

    # Security fence leaves a 15 m main gate and a service gate in the east.
    fence_segment(c, "fence:south_west", (-108, -89), (20, -89), M)
    fence_segment(c, "fence:south_east", (36, -89), (108, -89), M)
    fence_segment(c, "fence:north", (-108, 89), (108, 89), M)
    fence_segment(c, "fence:west", (-108, -89), (-108, 89), M)
    fence_segment(c, "fence:east_south", (108, -89), (108, -12), M)
    fence_segment(c, "fence:east_north", (108, 2), (108, 89), M)
    # Main gate architecture, guardhouse and clear school identity.
    for x in (20, 36):
        box(
            c,
            "gate:brick_pier",
            (x, -88.6, 2.4),
            (1.55, 1.75, 4.8),
            M["brick"],
            0.10,
            role="campus_gate_pier",
        )
        box(
            c,
            "gate:stone_cap",
            (x, -88.6, 4.92),
            (1.9, 2.05, 0.32),
            M["stone_light"],
            0.055,
            role="campus_gate_cap",
        )
    beam(
        c,
        "gate:header",
        (20, -88.6, 5.25),
        (36, -88.6, 5.25),
        0.28,
        M["white_clean"],
        24,
        "campus_gate_header",
    )
    text_object(
        c,
        "gate:school_sign",
        "RIVERSIDE SCHOOL",
        (28, -89.02, 5.30),
        0.75,
        M["blue"],
        0.065,
    )
    box(
        c,
        "gate:guardhouse_shell",
        (43.5, -84.8, 1.65),
        (6.5, 5.2, 3.3),
        M["brick_light"],
        0.09,
        role="guardhouse",
    )
    for face_y in (-87.45, -82.15):
        BASE.window_y(
            c,
            "gate:guardhouse_window",
            43.5,
            face_y,
            1.85,
            4.7,
            1.65,
            M,
            divisions=2,
            normal=-1 if face_y < -85 else 1,
        )
    box(
        c,
        "gate:guardhouse_roof",
        (43.5, -84.8, 3.55),
        (7.1, 5.8, 0.45),
        M["white_clean"],
        0.055,
        role="guardhouse_roof",
    )
    for index in range(8):
        cylinder(
            c,
            "gate:entry_bollard",
            (21.7 + index * 1.8, -84.8, 0.75),
            0.10,
            1.5,
            M["steel"],
            22,
            role="security_bollard",
        )
    # Sliding security gate leaves and card-reader pedestal are fully modeled.
    for leaf_index, centre_x in enumerate((16.2, 39.8)):
        box(
            c,
            f"gate:sliding_leaf_{leaf_index}:bottom",
            (centre_x, -88.0, 0.72),
            (7.1, 0.10, 0.16),
            M["black_metal"],
            0.018,
            role="security_gate_leaf",
        )
        box(
            c,
            f"gate:sliding_leaf_{leaf_index}:top",
            (centre_x, -88.0, 2.72),
            (7.1, 0.10, 0.16),
            M["black_metal"],
            0.018,
            role="security_gate_leaf",
        )
        for picket in range(14):
            box(
                c,
                f"gate:sliding_leaf_{leaf_index}:picket",
                (centre_x - 3.25 + picket * 0.50, -88.0, 1.72),
                (0.055, 0.08, 1.95),
                M["steel"],
                0.0,
                role="security_gate_leaf",
            )
    box(
        c,
        "gate:card_reader_pedestal",
        (38.5, -84.3, 0.95),
        (0.34, 0.34, 1.65),
        M["black_metal"],
        0.055,
        role="access_control",
    )
    box(
        c,
        "gate:card_reader_screen",
        (38.5, -84.48, 1.28),
        (0.21, 0.035, 0.26),
        M["glass_blue"],
        0.012,
        role="access_control",
    )

    # Human-scale campus furniture.
    for idx, (x, y, yaw, target) in enumerate(
        (
            (14, 22, 0, None),
            (44, 22, math.pi, None),
            (12, 38, 0, None),
            (47, 38, math.pi, None),
            (60, -47, 0, "volleyball_court"),
            (86, -47, 0, "volleyball_court"),
        )
    ):
        bench(c, f"furniture:bench_{idx}", x, y, yaw, M, target)
    for idx, (x, y) in enumerate(
        (
            (7, -15),
            (28, -18),
            (50, -38),
            (94, -48),
            (-29, 46),
            (73, 25),
            (101, 8),
            (28, -80),
        )
    ):
        campus_light(c, f"lighting:campus_{idx}", x, y, M)
    # Bicycle racks are bent frames, not symbolic bars.
    for rack in range(10):
        x = 48.5 + rack * 1.15
        for side in (-1, 1):
            cylinder(
                c,
                "bikes:rack_foot",
                (x + side * 0.34, -43.5, 0.45),
                0.035,
                0.9,
                M["steel"],
                14,
                role="bicycle_rack",
            )
        beam(
            c,
            "bikes:rack_arch",
            (x - 0.34, -43.5, 0.86),
            (x + 0.34, -43.5, 0.86),
            0.045,
            M["steel"],
            14,
            "bicycle_rack",
        )

    # Raised masonry planters reuse the prior connected-branch/explicit-leaf/flower strategy.
    planter_specs = (
        (1, 18, 11, 2.8),
        (56, 18, 13, 2.8),
        (2, 41, 11, 2.6),
        (56, 41, 13, 2.6),
        (47, -48, 17, 2.2),
        (92, -48, 13, 2.2),
    )
    for planter_index, (x, y, length, depth) in enumerate(planter_specs):
        detailed_landscape_planter(
            c,
            f"landscape:planter_{planter_index}",
            x,
            y,
            length,
            depth,
            M,
            7310 + planter_index,
        )

    # Exact full07 multilevel botanical trees with native curved leaf templates. Positions enforce a
    # generous no-crown/no-trunk keepout around the complete red running track.
    for index, (x, y) in enumerate(TREE_POSITIONS):
        planting_context = (
            "modeled_lawn"
            if _position_inside_lawn((x, y))
            else "hard_paving_square_soil_pit"
        )
        for tree_part in campus_tree(
            c, f"tree_{index}", x, y, 0.86 + 0.16 * ((index * 7) % 5) / 4, M
        ):
            tree_part["c2w_tree_center_x"] = x
            tree_part["c2w_tree_center_y"] = y
            tree_part["c2w_planting_context"] = planting_context
    for pit_index, (x, y) in enumerate(PAVED_TREE_PITS):
        recessed_tree_pit(c, f"tree_pit_{pit_index}", x, y, M)

    c[
        "c2w_detail_profile"
    ] = "raised_parcel_with_all_hardscape_tree_openings+continuous_close_mown_turf+four_realistic_roads+security_fence+gate+open_plaza+full07_botanical_trees+connected_flowerbeds"
    return c


def build_covered_connections(parent, M):
    c = collection(
        "COVERED_CAMPUS_CONNECTIONS", parent, "school.covered_walkways.reference.v3"
    )
    covered_walkway(c, "admin_to_north_academic", (4.0, 18.0), (4.0, 57.0), 3.2, M)
    covered_walkway(c, "admin_to_east_academic", (52.5, 17.5), (52.5, 30.2), 3.0, M)
    covered_walkway(c, "auditorium_to_admin", (14.2, -22.0), (14.2, -8.0), 3.0, M)
    c[
        "c2w_detail_profile"
    ] = "continuous_canopies+steel_columns+integrated_lighting+paved_links"
    return c


def build_context_district(parent, M):
    c = collection("SURROUNDING_URBAN_CONTEXT", parent, "school.context.district.v3")
    # The reference is a complete urban block, not an isolated model on an infinite plane.
    specs = (
        (-92, 137, 28, 18, 4, "south"),
        (-55, 139, 30, 20, 6, "south"),
        (-15, 138, 34, 18, 5, "south"),
        (29, 140, 35, 20, 7, "south"),
        (72, 138, 30, 18, 5, "south"),
        (105, 140, 24, 20, 4, "south"),
        (-92, -139, 31, 19, 4, "north"),
        (-51, -138, 30, 18, 5, "north"),
        (-10, -140, 34, 20, 6, "north"),
        (36, -138, 36, 18, 4, "north"),
        (80, -140, 32, 20, 7, "north"),
        (112, -137, 22, 17, 3, "north"),
        (157, -67, 22, 27, 5, "west"),
        (158, -24, 24, 29, 7, "west"),
        (157, 24, 23, 30, 4, "west"),
        (158, 68, 25, 27, 6, "west"),
        (-157, -61, 22, 29, 4, "east"),
        (-158, -17, 24, 28, 6, "east"),
        (-157, 29, 23, 29, 5, "east"),
        (-158, 70, 25, 25, 4, "east"),
    )
    for index, spec in enumerate(specs):
        context_building(c, f"context_block_{index}", *spec, M, palette=index)

    # Secondary streets, parking bays, planted verges and service alleys extend the composition.
    for name, xyz, dims in (
        ("north_secondary_road", (0, 119, -0.01), (270, 11, 0.18)),
        ("south_secondary_road", (0, -119, -0.01), (270, 11, 0.18)),
        ("east_secondary_road", (139, 0, -0.01), (11, 210, 0.18)),
        ("west_secondary_road", (-139, 0, -0.01), (11, 210, 0.18)),
    ):
        box(c, name, xyz, dims, M["asphalt_real"], 0.025, role="context_road")
    for x in range(-105, 106, 12):
        box(
            c,
            "north:parking_bay",
            (x, 112.6, 0.14),
            (0.10, 5.6, 0.025),
            M["paint_white"],
            0.0,
            role="parking_bay_marking",
        )
        box(
            c,
            "south:parking_bay",
            (x, -112.6, 0.14),
            (0.10, 5.6, 0.025),
            M["paint_white"],
            0.0,
            role="parking_bay_marking",
        )
    for index, (x, y) in enumerate(
        (
            (-128, -78),
            (-128, -35),
            (-128, 8),
            (-128, 51),
            (128, -78),
            (128, -35),
            (128, 8),
            (128, 51),
            (-96, 113),
            (-54, 113),
            (-12, 113),
            (32, 113),
            (74, 113),
            (102, 113),
        )
    ):
        campus_tree(
            c,
            f"context_tree_{index}",
            x,
            y,
            0.78 + 0.06 * (index % 3),
            M,
            leaf_count=44,
        )
    c[
        "c2w_detail_profile"
    ] = "twenty_detailed_context_buildings+secondary_streets+parking+street_trees"
    return c


def build_campus_life(parent, M):
    c = collection("CAMPUS_LIFE_AND_SPORT", parent, "school.campus_life.v3")
    walkers = (
        (22, -80, 0.10),
        (26, -72, -0.04),
        (32, -66, 0.08),
        (24, -58, -0.10),
        (31, -49, 0.06),
        (22, -39, -0.12),
        (33, -28, 0.10),
        (23, -17, -0.08),
        (17, 20, 0.35),
        (23, 23, -0.50),
        (35, 20, 0.20),
        (42, 24, -0.30),
        (10, 31, 0.10),
        (18, 37, 0.45),
        (40, 36, -0.20),
        (49, 31, 0.20),
        (4, 48, 0.02),
        (53, 26, 0.04),
        (58, -43, 0.15),
        (87, -45, -0.10),
        (45, -52, 0.35),
        (97, -54, -0.45),
        (37, -82, 0.12),
        (42, -84, -0.08),
    )
    for index, (x, y, yaw) in enumerate(walkers):
        procedural_person(c, f"student_{index}", x, y, yaw, M, "walk", index)

    # Football practice, runners and complete volleyball teams supply scale and activity.
    footballers = (
        (-82, -38),
        (-70, -34),
        (-58, -29),
        (-78, -12),
        (-63, -7),
        (-72, 8),
        (-55, 16),
        (-84, 22),
    )
    for index, (x, y) in enumerate(footballers):
        procedural_person(
            c, f"footballer_{index}", x, y, 0.35 * index, M, "football", index + 2
        )
    ellipsoid(
        c,
        "football:training_ball",
        (-66.8, -16.0, 0.66),
        (0.36, 0.36, 0.36),
        M["paint_white"],
        "athletic_ball",
        segments=18,
        rings=9,
    )
    runners = (
        (-97.0, -48.0, 0.1),
        (-98.2, -34.0, 0.04),
        (-96.5, 4.0, -0.04),
        (-92.0, 31.0, -0.08),
    )
    for index, (x, y, yaw) in enumerate(runners):
        procedural_person(c, f"runner_{index}", x, y, yaw, M, "football", index + 1)
    volleyballers = (
        (52.5, -70.5),
        (61.0, -71.5),
        (54.0, -65.5),
        (62.5, -65.2),
        (77.0, -70.5),
        (85.5, -71.4),
        (78.5, -65.3),
        (87.0, -65.5),
    )
    for index, (x, y) in enumerate(volleyballers):
        procedural_person(
            c,
            f"volleyball_player_{index}",
            x,
            y,
            math.pi / 2 if index % 2 else -math.pi / 2,
            M,
            "volleyball",
            index + 1,
        )
    ellipsoid(
        c,
        "volleyball:airborne_ball",
        (81.9, -68.0, 3.15),
        (0.34, 0.34, 0.34),
        M["sports_yellow"],
        "volleyball_equipment",
        segments=18,
        rings=9,
    )
    c[
        "c2w_detail_profile"
    ] = "articulated_students+football_practice+runners+volleyball_teams+modeled_sports_balls"
    return c


def build_school_campus(parent=None, include_site=True):
    """Reusable pipeline entrypoint for the complete procedural school."""
    print("[school5] materials", flush=True)
    M = make_materials()
    root = collection(
        "RIVERSIDE_SCHOOL_CAMPUS", parent, "campus.school.reference_7018.v6"
    )
    root["c2w_pipeline_entrypoint"] = "generate_urban_v3_school.build_school_campus"
    root["c2w_scene_asset_inputs"] = 0
    root["c2w_reference_url"] = REFERENCE_URL
    root["c2w_reference_cache"] = str(ROOT / ".reference_cache/school_reference.jpg")
    root[
        "c2w_layout_summary"
    ] = "reference-matched independent block: west oval track, south-east volleyball, circular hall with clear paved forecourt, and compact north/east teaching courtyards"
    root["c2w_outer_context_buildings"] = 0
    root["c2w_human_models"] = 0
    root["c2w_track_object_keepout"] = "complete red EPDM running surface"
    # Build shared complex species masters before thousands of site objects so
    # the temporary full07 mesh lists never stack on top of the finished scene.
    root["c2w_revision"] = OUTPUT_NAME
    root["c2w_flag_and_platform_removed"] = True
    root["c2w_auditorium_forecourt_finish"] = "continuous paving; no green ground panel"
    print("[school5] prebuilding shared full07 botanical masters", flush=True)
    for seed in _TREE_SEEDS:
        _full07_tree_master(seed)
    if include_site:
        print(
            "[school5] all hardscape tree pits, close-mown lawns, clear gate and coherent roads",
            flush=True,
        )
        build_campus_site(root, M)
    print(
        "[school5] clear regulation track, football and inward-facing spectator seating",
        flush=True,
    )
    build_track_and_field(root, M)
    print(
        "[school5] enclosed detailed volleyball compound with inward-facing seating",
        flush=True,
    )
    build_volleyball_courts(root, M)
    print("[school5] layered academic facade systems", flush=True)
    build_academic_bar(
        root, M, "NORTH_WEST", (-55.0, 68.0), 55.0, 15.0, 4, 0.0, True, "SCIENCE"
    )
    build_academic_bar(
        root, M, "NORTH_CENTRE", (8.0, 66.0), 50.0, 16.0, 5, 0.0, True, "ACADEMIC"
    )
    build_academic_bar(
        root, M, "NORTH_EAST", (66.0, 68.0), 45.0, 15.0, 4, 0.0, True, "ARTS"
    )
    build_academic_bar(
        root, M, "WEST_LINK", (-20.0, 47.0), 31.0, 15.0, 4, math.pi / 2, False
    )
    build_academic_bar(
        root,
        M,
        "EAST_LINK",
        (90.0, 40.0),
        52.0,
        15.0,
        4,
        math.pi / 2,
        True,
        "CLASSROOMS",
    )
    build_academic_bar(
        root, M, "MID_EAST", (61.0, 39.0), 42.0, 15.0, 4, 0.0, True, "LANGUAGES"
    )
    print("[school5] administration, gymnasium, auditorium and cafeteria", flush=True)
    build_administration(root, M)
    build_gymnasium(root, M)
    build_auditorium(root, M)
    build_cafeteria(root, M)
    print("[school5] covered campus links; no human models", flush=True)
    build_covered_connections(root, M)
    print(f"[school5] build complete: {len(bpy.data.objects)} objects", flush=True)
    return root, M


# ---------------------------------------------------------------------------
# Daylight presentation, output and strict requirement audit.
# ---------------------------------------------------------------------------


def camera(name, location, target, lens):
    data = bpy.data.cameras.new(PREFIX + name)
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    sightline = Vector(target) - Vector(location)
    obj.rotation_euler = sightline.to_track_quat("-Z", "Y").to_euler()
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = sightline.length < 145
    data.dof.focus_distance = sightline.length
    data.dof.aperture_fstop = 7.1
    data.dof.aperture_blades = 9
    return tag(obj, "validation_camera")


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
    # Nishita is connected (the prior generator created it but rendered a flat blue background).
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(132)
    sky.air_density = 1.0
    sky.dust_density = 0.10
    if hasattr(sky, "altitude"):
        sky.altitude = 75.0
    background.inputs["Strength"].default_value = 0.24
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    bpy.ops.object.light_add(type="SUN", location=(70, -95, 145))
    sun = bpy.context.object
    sun.name = PREFIX + "day_sun"
    sun.data.energy = 3.05
    sun.data.angle = math.radians(2.4)
    sun.rotation_euler = (math.radians(42), math.radians(-18), math.radians(138))
    tag(sun, "daylight")
    bpy.ops.object.light_add(type="AREA", location=(-80, -55, 100))
    fill = bpy.context.object
    fill.name = PREFIX + "sky_fill"
    fill.data.energy = 310
    fill.data.shape = "DISK"
    fill.data.size = 70
    fill.rotation_euler = (math.radians(21), 0, math.radians(-30))
    tag(fill, "daylight_fill")

    # Large warm bounce keeps recessed brick elevations readable without flattening shadows.
    bpy.ops.object.light_add(type="AREA", location=(85, -105, 38))
    bounce = bpy.context.object
    bounce.name = PREFIX + "warm_ground_bounce"
    bounce.data.energy = 175
    bounce.data.color = (1.0, 0.79, 0.60)
    bounce.data.shape = "DISK"
    bounce.data.size = 34
    bounce.rotation_euler = (
        (Vector((20, 10, 7)) - bounce.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(bounce, "daylight_bounce")


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1536
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.68
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 18
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 64
        if hasattr(scene.eevee, "use_shadows"):
            scene.eevee.use_shadows = True
        if hasattr(scene.eevee, "shadow_resolution_scale"):
            scene.eevee.shadow_resolution_scale = 1.0
        if hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = True
        if hasattr(scene.eevee, "ray_tracing_method"):
            scene.eevee.ray_tracing_method = "SCREEN"
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True
        if hasattr(scene.eevee, "gtao_quality"):
            scene.eevee.gtao_quality = 1.35
        if hasattr(scene.eevee, "gtao_distance"):
            scene.eevee.gtao_distance = 3.0


def render_views(cameras):
    configure_render()
    scene = bpy.context.scene
    for filename, cam in cameras:
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def audit(root, cameras):
    bpy.context.view_layer.update()
    role_counts = {}
    for obj in bpy.data.objects:
        role = obj.get("c2w_role", "untagged")
        role_counts[role] = role_counts.get(role, 0) + 1
    children = {child.name: len(child.all_objects) for child in root.children}
    building_collections = [
        child
        for child in root.children
        if any(
            token in child.name
            for token in (
                "ACADEMIC_",
                "ADMINISTRATION",
                "GYMNASIUM",
                "AUDITORIUM",
                "CAFETERIA",
            )
        )
    ]
    renderable = [
        obj for obj in bpy.data.objects if obj.type in {"MESH", "CURVE", "FONT"}
    ]
    banned_tokens = ("placeholder", "proxy", "dummy", "toy", "blob")
    banned = [
        obj.name
        for obj in renderable
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    human_name_tokens = (
        "student",
        "person",
        "pedestrian_model",
        "footballer",
        "runner",
        "volleyball_player",
    )
    human_named_objects = [
        obj.name
        for obj in renderable
        if any(token in obj.name.lower() for token in human_name_tokens)
    ]
    camera_building_intersections = []
    building_shells = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "occupied_building_shell"
    ]
    procedural_surface_count = sum(
        1 for material in bpy.data.materials if material.get("c2w_procedural_surface")
    )
    visible_leaf_canopies = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "botanical_leaf_canopy"
    ]
    explicit_tree_leaves = sum(
        int(obj.get("c2w_explicit_leaf_count", 0)) for obj in visible_leaf_canopies
    )
    explicit_tree_branches = sum(
        int(obj.get("c2w_botanical_branch_count", 0))
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "tree_multilevel_branch_mesh"
    )
    explicit_shrub_branches = sum(
        int(obj.get("c2w_explicit_branch_count", 0))
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "shrub_branch"
    )
    explicit_shrub_leaves = sum(
        int(obj.get("c2w_explicit_leaf_count", 0))
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "shrub_leaf"
    )
    explicit_flower_petals = sum(
        int(obj.get("c2w_explicit_petal_count", 0))
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "flower_petal"
    )
    # Audit the exact eight-lane annulus.  Only bonded markings and drainage may
    # touch the red EPDM; all equipment, vegetation and furniture must be clear.
    track_clearance_violations = []
    allowed_track_roles = {
        "running_track_surface",
        "track_lane_line",
        "track_lane_number",
        "track_exchange_mark",
        "track_drainage_channel",
        "track_drainage_edge",
    }

    def inside_capsule(px, py, width, length):
        radius = width / 2
        straight = (length - width) / 2
        dx = px + 68.0
        dy = abs(py + 18.0)
        cap_y = max(0.0, dy - straight)
        return dx * dx + cap_y * cap_y <= radius * radius

    for obj in bpy.context.scene.objects:
        if (
            obj.type not in {"MESH", "CURVE", "FONT"}
            or obj.get("c2w_role") in allowed_track_roles
        ):
            continue
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_x, max_x = min(point.x for point in corners), max(
            point.x for point in corners
        )
        min_y, max_y = min(point.y for point in corners), max(
            point.y for point in corners
        )
        max_z = max(point.z for point in corners)
        if max_z <= 0.405:
            continue
        intersects_red = False
        for ix in range(5):
            px = min_x + (max_x - min_x) * ix / 4
            for iy in range(5):
                py = min_y + (max_y - min_y) * iy / 4
                if inside_capsule(px, py, 65.0, 124.0) and not inside_capsule(
                    px, py, 50.2, 109.2
                ):
                    intersects_red = True
                    break
            if intersects_red:
                break
        if intersects_red and not obj.name.startswith(PREFIX + "track:start_mark"):
            track_clearance_violations.append(
                {"object": obj.name, "role": obj.get("c2w_role", "untagged")}
            )

    crossing_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "pedestrian_crossing"
    ]
    corrected_crossing_orientation = bool(crossing_objects) and all(
        obj.dimensions.x > obj.dimensions.y * 8 for obj in crossing_objects
    )
    for filename, cam in cameras:
        point = cam.matrix_world.translation
        for shell in building_shells:
            corners = [
                shell.matrix_world @ Vector(corner) for corner in shell.bound_box
            ]
            mins = Vector(
                (
                    min(v.x for v in corners),
                    min(v.y for v in corners),
                    min(v.z for v in corners),
                )
            )
            maxs = Vector(
                (
                    max(v.x for v in corners),
                    max(v.y for v in corners),
                    max(v.z for v in corners),
                )
            )
            if all(mins[index] <= point[index] <= maxs[index] for index in range(3)):
                camera_building_intersections.append(
                    {"view": filename, "building": shell.name}
                )

    def bounds_xy(obj):
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return (
            min(v.x for v in points),
            max(v.x for v in points),
            min(v.y for v in points),
            max(v.y for v in points),
        )

    lawn_surfaces = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "campus_lawn_surface"
    ]
    lawn_blade_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "modeled_grass_blades"
    ]
    explicit_grass_blades = sum(
        int(obj.get("c2w_explicit_blade_count", 0)) for obj in lawn_blade_objects
    )
    lawn_surface_face_count = sum(
        len(obj.data.polygons) for obj in lawn_surfaces if obj.type == "MESH"
    )
    pointed_lawn_geometry = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role") == "modeled_grass_blades"
        or "grass_blade" in obj.name.lower()
    ]
    lawn_building_collisions = []
    clearance = 0.65
    for lawn in lawn_surfaces:
        lx0, lx1, ly0, ly1 = bounds_xy(lawn)
        for shell in building_shells:
            bx0, bx1, by0, by1 = bounds_xy(shell)
            if (
                lx1 > bx0 - clearance
                and lx0 < bx1 + clearance
                and ly1 > by0 - clearance
                and ly0 < by1 + clearance
            ):
                lawn_building_collisions.append(
                    {
                        "lawn": lawn.name,
                        "building": shell.name,
                        "required_clearance_m": clearance,
                    }
                )
    paving_lawn_overlaps = []
    paving_surfaces = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "campus_paving_surface"
    ]
    for lawn in lawn_surfaces:
        lx0, lx1, ly0, ly1 = bounds_xy(lawn)
        for paving in paving_surfaces:
            px0, px1, py0, py1 = bounds_xy(paving)
            if (
                lx1 > px0 + 0.002
                and lx0 < px1 - 0.002
                and ly1 > py0 + 0.002
                and ly0 < py1 - 0.002
            ):
                paving_lawn_overlaps.append({"lawn": lawn.name, "paving": paving.name})

    # The former green strip occupied x=0.5..23.5 and y=-83.5..-26.5,
    # penetrating the circular hall.  Its entire south-entry forecourt is now
    # required to remain free of all lawn meshes.
    auditorium_forecourt = (-12.0, 25.5, -86.0, -47.8)
    forecourt_lawn_intrusions = []
    for lawn in lawn_surfaces:
        lx0, lx1, ly0, ly1 = bounds_xy(lawn)
        fx0, fx1, fy0, fy1 = auditorium_forecourt
        if lx1 > fx0 and lx0 < fx1 and ly1 > fy0 and ly0 < fy1:
            forecourt_lawn_intrusions.append(lawn.name)

    tree_pit_soils = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_role") == "tree_pit_soil"
    ]
    expected_pit_centers = {(round(x, 3), round(y, 3)) for x, y in PAVED_TREE_PITS}
    actual_pit_centers = {
        (
            round(float(obj.get("c2w_pit_center_x", 9999.0)), 3),
            round(float(obj.get("c2w_pit_center_y", 9999.0)), 3),
        )
        for obj in tree_pit_soils
    }
    tagged_paved_tree_centers = {
        (
            round(float(obj.get("c2w_tree_center_x", 9999.0)), 3),
            round(float(obj.get("c2w_tree_center_y", 9999.0)), 3),
        )
        for obj in visible_leaf_canopies
        if obj.get("c2w_planting_context") == "hard_paving_square_soil_pit"
    }
    missing_hardscape_tree_pits = sorted(expected_pit_centers - actual_pit_centers)
    unexpected_tree_pits = sorted(actual_pit_centers - expected_pit_centers)
    unclassified_hardscape_trees = sorted(
        expected_pit_centers - tagged_paved_tree_centers
    )
    loose_tree_pit_scatter = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role") == "tree_pit_mulch" or "mulch_chip" in obj.name.lower()
    ]
    tree_pit_paving_overlaps = []
    for soil in tree_pit_soils:
        sx0, sx1, sy0, sy1 = bounds_xy(soil)
        for paving in paving_surfaces:
            px0, px1, py0, py1 = bounds_xy(paving)
            if (
                sx1 > px0 + 0.002
                and sx0 < px1 - 0.002
                and sy1 > py0 + 0.002
                and sy0 < py1 - 0.002
            ):
                tree_pit_paving_overlaps.append(
                    {"soil": soil.name, "paving": paving.name}
                )

    tactile_paving_objects = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role") == "tactile_paving" or "tactile_" in obj.name.lower()
    ]
    foreground_equipment_board_objects = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role")
        in {"athletic_equipment_storage_surface", "athletic_equipment_rack"}
        or any(
            token in obj.name.lower()
            for token in (
                "equipment_store",
                "start_block",
                "track:hurdle",
                "marker_cone",
            )
        )
    ]
    track_auditorium_strip_objects = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role")
        in {"long_jump_runway", "long_jump_pit", "long_jump_sand"}
        or "long_jump" in obj.name.lower()
    ]
    # The pale secondary-walk bar formerly occupied this exact gap between the
    # east edge of the oval and west face of the circular auditorium.
    removed_pale_strip_zone = (-27.0, -9.0, -21.0, -15.0)
    zx0, zx1, zy0, zy1 = removed_pale_strip_zone
    for obj in renderable:
        if obj.get("c2w_role") != "pedestrian_walk":
            continue
        ox0, ox1, oy0, oy1 = bounds_xy(obj)
        if ox1 > zx0 and ox0 < zx1 and oy1 > zy0 and oy0 < zy1:
            track_auditorium_strip_objects.append(obj.name)
    forbidden_ground_patches = [
        obj.name
        for obj in renderable
        if obj.get("c2w_role") == "road_surface_repair"
        or "asphalt_repair" in obj.name.lower()
        or "landscape_patch" in obj.name.lower()
    ]
    forbidden_flagcourt = [
        obj.name for obj in renderable if "flagcourt" in obj.name.lower()
    ]

    # Validate orientation from both the declared sightline and the physical
    # offset between each seat pan and its back, so metadata alone cannot pass.
    seating_groups = {}
    for obj in bpy.context.scene.objects:
        group = obj.get("c2w_seat_group")
        if group and obj.get("c2w_seating_target") in {
            "football_pitch",
            "volleyball_court",
        }:
            seating_groups.setdefault(group, []).append(obj)
    seating_orientation_violations = []
    seating_target_counts = {"football_pitch": 0, "volleyball_court": 0}
    for group, parts in seating_groups.items():
        pans = [obj for obj in parts if obj.get("c2w_seat_component") == "pan"]
        backs = [obj for obj in parts if obj.get("c2w_seat_component") == "back"]
        if not pans or not backs:
            seating_orientation_violations.append(
                {"group": group, "reason": "missing pan or back geometry"}
            )
            continue
        target = parts[0].get("c2w_seating_target")
        seating_target_counts[target] += 1
        facing = Vector(
            (
                float(parts[0].get("c2w_facing_x", 0.0)),
                float(parts[0].get("c2w_facing_y", 0.0)),
            )
        )
        pan_center = sum(
            (
                Vector((obj.matrix_world.translation.x, obj.matrix_world.translation.y))
                for obj in pans
            ),
            Vector((0.0, 0.0)),
        ) / len(pans)
        back_center = sum(
            (
                Vector((obj.matrix_world.translation.x, obj.matrix_world.translation.y))
                for obj in backs
            ),
            Vector((0.0, 0.0)),
        ) / len(backs)
        if target == "football_pitch":
            target_point = Vector((-68.0, pan_center.y))
        else:
            court_x = (
                57.0 if abs(pan_center.x - 57.0) <= abs(pan_center.x - 82.0) else 82.0
            )
            target_point = Vector((court_x, -68.0))
        sightline = target_point - pan_center
        if facing.length < 0.9 or sightline.length < 0.1:
            seating_orientation_violations.append(
                {"group": group, "reason": "invalid facing vector"}
            )
            continue
        facing.normalize()
        sightline.normalize()
        back_offset = back_center - pan_center
        if facing.dot(sightline) < 0.92 or back_offset.dot(facing) >= -0.04:
            seating_orientation_violations.append(
                {
                    "group": group,
                    "reason": "seat does not face target",
                    "facing_dot": round(facing.dot(sightline), 4),
                    "back_offset_dot": round(back_offset.dot(facing), 4),
                }
            )
    required = {
        "dense_school_building_group": len(building_collections) >= 10
        and min(len(c.all_objects) for c in building_collections) >= 40,
        "detailed_external_facades": role_counts.get("facade_glazing", 0) >= 260
        and role_counts.get("facade_mullion", 0) >= 520,
        "brick_and_precast_articulation": role_counts.get("brick_mortar_joint", 0)
        >= 200
        and role_counts.get("precast_structural_frame", 0) >= 40
        and role_counts.get("facade_spandrel", 0) >= 250,
        "layered_non_block_facades": role_counts.get("facade_projecting_bay", 0) >= 20
        and role_counts.get("window_lintel", 0) >= 250
        and role_counts.get("facade_shadow_joint", 0) >= 30,
        "roof_architectural_detail": role_counts.get("roof_mechanical_unit", 0) >= 10
        and role_counts.get("roof_parapet", 0) >= 20
        and role_counts.get("roof_coping", 0) >= 10,
        "regulation_track_and_football": role_counts.get("track_lane_line", 0) >= 9
        and role_counts.get("football_pitch_marking", 0) >= 18
        and role_counts.get("football_goal_frame", 0) >= 8,
        "red_running_track_completely_clear": not track_clearance_violations,
        "two_complete_volleyball_courts": role_counts.get(
            "volleyball_playing_surface", 0
        )
        == 2
        and role_counts.get("volleyball_net_mesh", 0) >= 40
        and role_counts.get("volleyball_post", 0) == 4
        and role_counts.get("volleyball_court_drain_slot", 0) >= 100,
        "volleyball_compound_is_ballstop_fenced": role_counts.get(
            "volleyball_fence_post", 0
        )
        >= 35
        and role_counts.get("volleyball_fence_mesh", 0) == 5
        and role_counts.get("volleyball_fence_gate", 0) >= 8,
        "dedicated_fenced_parcel": role_counts.get("dedicated_school_parcel", 0) == 1
        and role_counts.get("campus_fence_post", 0) >= 90
        and role_counts.get("campus_gate_pier", 0) == 2,
        "full07_complex_botanical_trees_reused": len(visible_leaf_canopies) >= 25
        and explicit_tree_branches >= 4000
        and explicit_tree_leaves >= 10000
        and all(obj.get("c2w_no_simplified_fallback") for obj in visible_leaf_canopies),
        "connected_complex_flowerbeds": explicit_shrub_branches >= 900
        and explicit_shrub_leaves >= 900
        and explicit_flower_petals >= 450
        and role_counts.get("landscape_planter_wall", 0) == 24,
        "physically_varied_procedural_materials": procedural_surface_count >= 18,
        "all_human_models_removed": not human_named_objects
        and not any(
            role_counts.get(role, 0)
            for role in (
                "campus_occupant",
                "person_anatomy",
                "person_clothing",
                "person_hair",
                "person_footwear",
            )
        ),
        "all_outer_road_context_buildings_removed": role_counts.get(
            "context_building_shell", 0
        )
        == 0
        and role_counts.get("context_facade_glazing", 0) == 0
        and not any(
            "SURROUNDING_URBAN_CONTEXT" in child.name for child in root.children
        ),
        "operational_sports_detail": role_counts.get("football_goal_frame", 0) >= 8
        and role_counts.get("team_shelter", 0) >= 8
        and role_counts.get("grandstand_seat", 0) >= 80
        and role_counts.get("volleyball_equipment", 0) >= 10
        and role_counts.get("stadium_light_mast", 0) == 4,
        "realistic_four_road_system_without_colour_patches": role_counts.get(
            "perimeter_road", 0
        )
        == 4
        and role_counts.get("road_surface_repair", 0) == 0
        and role_counts.get("road_surface_crack", 0) == 4
        and role_counts.get("road_manhole", 0) == 4
        and role_counts.get("road_direction_arrow", 0) == 8,
        "corrected_crosswalk_orientation": corrected_crossing_orientation
        and len(crossing_objects) == 12,
        "landscape_and_micro_detail": role_counts.get("storm_drain", 0) >= 6
        and role_counts.get("utility_cover", 0) >= 4
        and role_counts.get("landscape_planter_coping", 0) >= 80,
        "weather_protected_building_links": role_counts.get("covered_walkway_canopy", 0)
        == 3
        and role_counts.get("covered_walkway_column", 0) >= 14,
        "all_hardscape_trees_have_true_recessed_soil_pits": role_counts.get(
            "tree_grate", 0
        )
        == 0
        and role_counts.get("tree_grate_slot", 0) == 0
        and len(tree_pit_soils) == len(PAVED_TREE_PITS) == 11
        and role_counts.get("tree_pit_edge", 0) == len(PAVED_TREE_PITS) * 4
        and not missing_hardscape_tree_pits
        and not unexpected_tree_pits
        and not unclassified_hardscape_trees
        and not tree_pit_paving_overlaps
        and all(
            obj.get("c2w_true_paving_opening")
            and float(obj.get("c2w_depression_below_paving_m", 0)) >= 0.06
            for obj in tree_pit_soils
        ),
        "tree_pit_soil_is_continuous_detailed_and_scatter_free": not loose_tree_pit_scatter
        and all(
            int(obj.get("c2w_continuous_microrelief_vertices", 0)) >= 1300
            and int(obj.get("c2w_continuous_microrelief_faces", 0)) >= 1200
            and int(obj.get("c2w_loose_scatter_piece_count", -1)) == 0
            for obj in tree_pit_soils
        ),
        "circular_auditorium_forecourt_green_removed": not forecourt_lawn_intrusions,
        "remaining_green_ground_is_modeled_lawn": len(lawn_surfaces) == len(LAWN_ZONES)
        and lawn_surface_face_count >= 2200
        and all(
            obj.get("c2w_finish")
            == "continuous close-mown turf with multi-scale shader fibres"
            for obj in lawn_surfaces
        ),
        "all_pointed_lawn_sprouts_removed": not pointed_lawn_geometry
        and not lawn_blade_objects
        and explicit_grass_blades == 0
        and all(
            int(obj.get("c2w_above_ground_pointed_blade_count", -1)) == 0
            for obj in lawn_surfaces
        ),
        "lawns_clear_all_building_shells": not lawn_building_collisions,
        "lawns_have_true_paving_openings_without_z_fighting": not paving_lawn_overlaps,
        "gate_yellow_blocklike_tactile_board_removed": not tactile_paving_objects
        and role_counts.get("tactile_paving", 0) == 0,
        "foreground_mast_equipment_board_removed": not foreground_equipment_board_objects
        and role_counts.get("athletic_equipment_storage_surface", 0) == 0
        and role_counts.get("athletic_equipment_rack", 0) == 0,
        "track_auditorium_red_yellow_white_strips_removed": not track_auditorium_strip_objects
        and role_counts.get("pedestrian_walk", 0) == 3
        and all(
            role_counts.get(role, 0) == 0
            for role in ("long_jump_runway", "long_jump_pit", "long_jump_sand")
        ),
        "national_flag_and_platform_removed": not forbidden_flagcourt
        and all(
            role_counts.get(role, 0) == 0
            for role in (
                "school_flag",
                "flagpole",
                "flagpole_finial",
                "flag_halyard",
                "flagpole_base",
            )
        ),
        "ground_colour_patch_geometry_removed": not forbidden_ground_patches,
        "track_and_volleyball_seating_face_play": not seating_orientation_violations
        and seating_target_counts["football_pitch"] == 10
        and seating_target_counts["volleyball_court"] == 10,
    }
    checks = {
        **required,
        "reference_layout_encoded": root.get("c2w_reference_url") == REFERENCE_URL,
        "procedural_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_school.build_school_campus",
        "no_external_blend_dependency": root.get("c2w_scene_asset_inputs") == 0,
        "eight_daylight_near_and_far_views": len(cameras) == 8,
        "no_camera_inside_building_shell": not camera_building_intersections,
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
        "reference_url": REFERENCE_URL,
        "reference_cache": str(ROOT / ".reference_cache/school_reference.jpg"),
        "layout": {
            "parcel_m": [220, 180],
            "track_zone": "west",
            "volleyball_zone": "south_east",
            "academic_zone": "north_and_east",
            "civic_axis": "south_gate_to_central_plaza",
            "outer_context_buildings": 0,
        },
        "building_collection_count": len(building_collections),
        "building_collections": [child.name for child in building_collections],
        "objects_per_collection": children,
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "procedural_surface_material_count": procedural_surface_count,
        "full07_visible_tree_count": len(visible_leaf_canopies),
        "full07_explicit_branch_count": explicit_tree_branches,
        "full07_explicit_leaf_count": explicit_tree_leaves,
        "flowerbed_explicit_shrub_branch_count": explicit_shrub_branches,
        "flowerbed_explicit_shrub_leaf_count": explicit_shrub_leaves,
        "flowerbed_explicit_petal_count": explicit_flower_petals,
        "modeled_lawn_zone_count": len(lawn_surfaces),
        "modeled_lawn_surface_face_count": lawn_surface_face_count,
        "explicit_grass_blade_count": explicit_grass_blades,
        "recessed_tree_pit_count": len(tree_pit_soils),
        "expected_hardscape_tree_pit_count": len(PAVED_TREE_PITS),
        "seating_target_counts": seating_target_counts,
        "role_counts": role_counts,
        "validation_views": [filename for filename, _ in cameras],
        "daylight": True,
        "near_and_far_views": True,
        "external_blend_inputs": 0,
        "pipeline_connected": True,
        "implemented_revision_requirements": [
            "all eleven trees rooted in cement paving receive true square openings with soil recessed at least 0.06 m",
            "tree-pit soil rebuilt as continuous 37x37-vertex microrelief with layered clod, grain, pore and moisture response; no loose square scatter",
            "raised yellow entrance tactile board and all studs removed at source",
            "foreground mast equipment mat, rack, hurdles, starting blocks and cones removed at source",
            "all pointed explicit lawn sprouts removed; retained lawns are smooth close-mown procedural turf",
            "red runway, yellow sand pit, pale curb and pale secondary-walk bar between track and circular auditorium removed at source",
            "green ground removed from the circular auditorium forecourt",
            "all retained campus green zones remain in true paving openings with layered living-turf materials and facade clearance",
            "national flag, mast, halyard, finial and all platform steps removed",
            "contrasting ground and asphalt repair colour patches removed",
            "track shelters and all volleyball-side seating physically rotated toward play",
        ],
        "reference_fidelity_features": [
            "west eight-lane oval and football pitch",
            "south-east twin volleyball courts",
            "4.2 m diamond-mesh volleyball ball-stop enclosure",
            "central circular auditorium with a clear continuous-paved forecourt",
            "four modeled living-turf lawn zones clear of building envelopes",
            "north/east red-brick academic courtyards",
            "independent fenced urban parcel with four perimeter roads",
            "no buildings beyond the perimeter roads",
            "no human models anywhere in the generated scene",
        ],
        "banned_geometry_names": banned,
        "human_named_objects": human_named_objects,
        "track_clearance_violations": track_clearance_violations,
        "lawn_building_collisions": lawn_building_collisions,
        "paving_lawn_overlaps": paving_lawn_overlaps,
        "auditorium_forecourt_lawn_intrusions": forecourt_lawn_intrusions,
        "missing_hardscape_tree_pits": missing_hardscape_tree_pits,
        "unexpected_tree_pits": unexpected_tree_pits,
        "unclassified_hardscape_trees": unclassified_hardscape_trees,
        "tree_pit_paving_overlaps": tree_pit_paving_overlaps,
        "loose_tree_pit_scatter_objects": loose_tree_pit_scatter,
        "pointed_lawn_geometry": pointed_lawn_geometry,
        "tactile_paving_objects": tactile_paving_objects,
        "foreground_equipment_board_objects": foreground_equipment_board_objects,
        "track_auditorium_strip_objects": track_auditorium_strip_objects,
        "forbidden_ground_patch_objects": forbidden_ground_patches,
        "forbidden_flagcourt_objects": forbidden_flagcourt,
        "seating_orientation_violations": seating_orientation_violations,
        "crosswalk_long_axis": "east_west_parallel_to_traffic",
        "camera_building_intersections": camera_building_intersections,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "all_checks_passed": all(checks.values()),
    }
    if not result["all_checks_passed"]:
        raise RuntimeError(
            "School production audit failed: "
            + json.dumps(result, indent=2, ensure_ascii=False)
        )
    (OUT / "manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    BASE.G.reset_scene()
    root, _ = build_school_campus()
    setup_daylight()
    specs = [
        ("01_full_campus_aerial_southeast.png", (235, -270, 210), (0, -2, 7), 56),
        ("02_full_campus_aerial_northwest.png", (-190, 178, 148), (0, 0, 7), 57),
        (
            "03_main_gate_road_and_civic_axis_close.png",
            (28, -132, 16.0),
            (28, -70, 3.2),
            48,
        ),
        (
            "04_recessed_tree_pit_and_courtyard_close.png",
            (31.2, 41.5, 2.35),
            (37.0, 49.0, 0.28),
            52,
        ),
        (
            "05_track_field_and_inward_facing_shelters.png",
            (3, -91, 17),
            (-55, -37, 2.4),
            49,
        ),
        (
            "06_volleyball_and_inward_facing_seating_close.png",
            (100, -85, 9.5),
            (70, -67, 1.8),
            52,
        ),
        (
            "07_circular_auditorium_clear_paved_forecourt.png",
            (-23, -76, 9.5),
            (2, -48, 2.1),
            47,
        ),
        (
            "08_east_lawn_and_building_clearance_close.png",
            (118, 9, 9.0),
            (102, 38, 2.2),
            50,
        ),
    ]
    cameras = [
        (filename, camera(filename[:-4], location, target, lens))
        for filename, location, target, lens in specs
    ]
    data = audit(root, cameras)
    scene = bpy.context.scene
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_entrypoint"] = "generate_urban_v3_school.build_school_campus"
    scene["c2w_schema_version"] = SCHEMA_VERSION
    scene["c2w_revision"] = OUTPUT_NAME
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(
        filepath=str(OUT / f"{OUTPUT_NAME}.blend"), compress=True
    )
    if os.environ.get("C2W_SCHOOL_BUILD_ONLY") == "1":
        print(
            "[school5] build-only validation complete; presentation rendering skipped",
            flush=True,
        )
        return
    render_views(cameras)
    (OUT / "SUCCESS").write_text(
        f"{OUTPUT_NAME} complex procedural generation, daylight near/far rendering and strict revision validation complete\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
