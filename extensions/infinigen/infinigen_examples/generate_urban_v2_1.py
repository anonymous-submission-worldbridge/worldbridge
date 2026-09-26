#!/usr/bin/env python3
"""
Urban Vehicle Showcase Scene — v2.1
Builds a low-rise urban block focused on realistic procedural vehicles.

Saves:  ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1/scene.blend
Render: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1/render.mp4

Run:
  cd ${WORLDBRIDGE_ROOT}/infinigen
  blender -b --python infinigen_examples/generate_urban_v2_1.py
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths['WORLDBRIDGE_ROOT']
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths['WORLDBRIDGE_SITE_PACKAGES']


import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONDA = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA.exists():
    sys.path.insert(0, str(CONDA))

import bpy
import numpy as np
from mathutils import Vector

# Patch infinigen tagging to work without a full Infinigen TaskGraph init
import infinigen.core.tagging as _tag_mod
_tag_mod.tag_object = lambda obj, semantic, **kw: \
    obj.get("semantic") or obj.__setitem__("semantic", semantic)

from infinigen.assets.objects.vehicles.vehicle import VehicleFactory
from infinigen.assets.objects.traffic.traffic_light import TrafficLightFactory
from infinigen.assets.objects.street_furniture.street_assets import StreetFurnitureFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BLEND_PATH = str(OUTPUT_DIR / "scene.blend")
RENDER_PATH = str(OUTPUT_DIR / "render.mp4")
FRAMES_DIR = OUTPUT_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

NUM_FRAMES = 150
FPS = 25

# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

def _make_mat(name, color, roughness=0.55, metallic=0.0,
              emission_strength=0.0, noise_strength=0.0, bump_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if len(color) > 3 and color[3] < 1.0:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
        mat.blend_method = "BLEND"
    if emission_strength > 0:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if noise_strength > 0:
        noise = nodes.new(type="ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 22
        noise.inputs["Detail"].default_value = 9
        ramp = nodes.new(type="ShaderNodeValToRGB")
        lo = tuple(max(0.0, c * (1 - noise_strength)) for c in color[:3]) + (1.0,)
        hi = tuple(min(1.0, c * (1 + noise_strength)) for c in color[:3]) + (1.0,)
        ramp.color_ramp.elements[0].color = lo
        ramp.color_ramp.elements[1].color = hi
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if bump_strength > 0 and "Normal" in bsdf.inputs:
        noise = nodes.new(type="ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 48
        noise.inputs["Detail"].default_value = 12
        bump = nodes.new(type="ShaderNodeBump")
        bump.inputs["Strength"].default_value = bump_strength
        bump.inputs["Distance"].default_value = 0.04
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_car_paint(name, color, roughness=0.18, metallic=0.82):
    """PBR car paint with clearcoat layer (Blender 4.x Principled BSDF)."""
    mat = _make_mat(name, color, roughness=roughness, metallic=metallic)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # Clearcoat inputs in Blender 4.x
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 0.88
            bsdf.inputs["Coat Roughness"].default_value = 0.032
            if "Coat IOR" in bsdf.inputs:
                bsdf.inputs["Coat IOR"].default_value = 1.52
        elif "Clearcoat" in bsdf.inputs:
            bsdf.inputs["Clearcoat"].default_value = 0.88
            bsdf.inputs["Clearcoat Roughness"].default_value = 0.04
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.52
        # Specular (older API)
        if "Specular" in bsdf.inputs:
            bsdf.inputs["Specular"].default_value = 0.5
    return mat


def _make_glass(name, tint=(0.04, 0.07, 0.10), alpha=0.15):
    """Semi-transparent tinted car glass."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.02
        bsdf.inputs["Metallic"].default_value = 0.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.52
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.92
    return mat


def build_materials():
    M = {}
    # --- Car paints ---
    M["car_red"]    = _make_car_paint("car_red",    (0.58, 0.04, 0.03, 1.0))
    M["car_blue"]   = _make_car_paint("car_blue",   (0.03, 0.12, 0.52, 1.0))
    M["car_white"]  = _make_car_paint("car_white",  (0.82, 0.84, 0.80, 1.0), metallic=0.60)
    M["car_black"]  = _make_car_paint("car_black",  (0.04, 0.04, 0.042, 1.0))
    M["car_silver"] = _make_car_paint("car_silver", (0.55, 0.57, 0.60, 1.0), metallic=0.88)
    M["car_green"]  = _make_car_paint("car_green",  (0.04, 0.28, 0.10, 1.0))
    M["bus_yellow"] = _make_car_paint("bus_yellow", (0.92, 0.66, 0.08, 1.0), metallic=0.50)
    # --- Vehicle parts ---
    M["car_glass"]       = _make_glass("car_glass",       tint=(0.04, 0.07, 0.10), alpha=0.14)
    M["tire"]            = _make_mat("tire",            (0.022, 0.020, 0.018, 1.0), roughness=0.90, bump_strength=0.12)
    M["rim_metal"]       = _make_mat("rim_metal",       (0.80, 0.80, 0.84, 1.0), metallic=0.96, roughness=0.10)
    M["chrome"]          = _make_mat("chrome",          (0.88, 0.88, 0.90, 1.0), metallic=1.0, roughness=0.03)
    M["metal"]           = _make_mat("metal",           (0.18, 0.18, 0.18, 1.0), roughness=0.62, metallic=0.22)
    M["brake_disc"]      = _make_mat("brake_disc",      (0.30, 0.28, 0.26, 1.0), metallic=0.55, roughness=0.52)
    M["headlight"]       = _make_mat("headlight",       (1.0, 0.92, 0.70, 1.0), emission_strength=2.5)
    M["headlight_led"]   = _make_mat("headlight_led",   (0.94, 0.96, 1.0, 1.0), emission_strength=5.0)
    M["tail_light"]      = _make_mat("tail_light",      (0.90, 0.02, 0.01, 1.0), emission_strength=2.0)
    M["tail_indicator"]  = _make_mat("tail_indicator",  (0.90, 0.42, 0.02, 1.0), emission_strength=1.2)
    M["tail_reverse"]    = _make_mat("tail_reverse",    (0.95, 0.95, 0.95, 1.0), emission_strength=0.9)
    M["license_plate"]   = _make_mat("license_plate",   (0.92, 0.90, 0.78, 1.0), roughness=0.42)
    M["signal_box"]      = _make_mat("signal_box",      (0.030, 0.032, 0.030, 1.0), roughness=0.72)
    M["car_interior"]    = _make_mat("car_interior",    (0.04, 0.04, 0.05, 1.0), roughness=0.86)
    # --- Road surface ---
    M["asphalt"]         = _make_mat("asphalt",         (0.032, 0.034, 0.036, 1.0), roughness=0.92, bump_strength=0.06)
    M["asphalt_patch"]   = _make_mat("asphalt_patch",   (0.045, 0.046, 0.048, 1.0), roughness=0.88)
    M["paint"]           = _make_mat("paint",           (0.82, 0.82, 0.78, 1.0), roughness=0.55)
    # --- Sidewalk / curb ---
    M["concrete"]        = _make_mat("concrete",        (0.56, 0.54, 0.50, 1.0), roughness=0.82, noise_strength=0.04, bump_strength=0.05)
    M["concrete_seam"]   = _make_mat("concrete_seam",   (0.36, 0.34, 0.30, 1.0), roughness=0.88)
    M["curb"]            = _make_mat("curb",            (0.60, 0.58, 0.54, 1.0), roughness=0.80)
    M["curb_ramp"]       = _make_mat("curb_ramp",       (0.62, 0.60, 0.56, 1.0), roughness=0.80)
    M["tactile_paving"]  = _make_mat("tactile_paving",  (0.85, 0.70, 0.18, 1.0), roughness=0.75)
    M["manhole"]         = _make_mat("manhole",         (0.25, 0.24, 0.22, 1.0), roughness=0.70, metallic=0.15)
    M["bollard"]         = _make_mat("bollard",         (0.88, 0.55, 0.04, 1.0), roughness=0.60)
    M["drain"]           = _make_mat("drain",           (0.22, 0.21, 0.20, 1.0), roughness=0.72, metallic=0.12)
    # --- Green ---
    M["grass"]           = _make_mat("grass",           (0.05, 0.22, 0.06, 1.0), roughness=0.96)
    # --- Buildings ---
    M["brick"]           = _make_mat("brick",           (0.38, 0.18, 0.12, 1.0), roughness=0.86, noise_strength=0.06, bump_strength=0.12)
    M["facade"]          = _make_mat("facade",          (0.58, 0.55, 0.48, 1.0), roughness=0.76, noise_strength=0.04)
    M["glass_facade"]    = _make_glass("glass_facade",  tint=(0.20, 0.36, 0.44), alpha=0.45)
    M["building_top"]    = _make_mat("building_top",    (0.30, 0.28, 0.26, 1.0), roughness=0.80)
    # --- Trees ---
    M["trunk"]           = _make_mat("trunk",           (0.20, 0.12, 0.05, 1.0), roughness=0.88)
    M["bark_dark"]       = _make_mat("bark_dark",       (0.10, 0.055, 0.025, 1.0), roughness=0.88)
    M["leaf"]            = _make_mat("leaf",            (0.06, 0.28, 0.10, 1.0), roughness=0.90)
    M["leaf_dark"]       = _make_mat("leaf_dark",       (0.030, 0.17, 0.06, 1.0), roughness=0.90)
    M["leaf_litter"]     = _make_mat("leaf_litter",     (0.34, 0.18, 0.06, 1.0), roughness=0.94)
    # --- Traffic light ---
    M["red_signal"]      = _make_mat("red_signal",      (1.0, 0.05, 0.03, 1.0), emission_strength=1.4)
    M["yellow_signal"]   = _make_mat("yellow_signal",   (1.0, 0.75, 0.08, 1.0), emission_strength=0.6)
    M["green_signal"]    = _make_mat("green_signal",    (0.05, 0.90, 0.18, 1.0), emission_strength=1.2)
    # --- Street lamp ---
    M["lamp"]            = _make_mat("lamp",            (1.0, 0.86, 0.48, 1.0), emission_strength=1.5)
    M["aged_metal"]      = _make_mat("aged_metal",      (0.22, 0.20, 0.18, 1.0), roughness=0.72, metallic=0.12)
    # --- Road detail ---
    M["road_stain"]      = _make_mat("road_stain",      (0.025, 0.026, 0.028, 1.0), roughness=0.88)
    M["road_crack"]      = _make_mat("road_crack",      (0.018, 0.018, 0.020, 1.0), roughness=0.92)
    M["asphalt_aggregate"] = _make_mat("asphalt_aggregate", (0.048, 0.044, 0.040, 1.0), roughness=0.90)
    M["paint_wear"]      = _make_mat("paint_wear",      (0.62, 0.60, 0.56, 1.0), roughness=0.70)
    M["curb_grime"]      = _make_mat("curb_grime",      (0.14, 0.13, 0.11, 1.0), roughness=0.92)
    M["paper_litter"]    = _make_mat("paper_litter",    (0.78, 0.74, 0.68, 1.0), roughness=0.82)
    M["gum"]             = _make_mat("gum",             (0.45, 0.42, 0.40, 1.0), roughness=0.88)
    M["leaf_litter"]     = M["leaf_litter"]
    M["sidewalk_stain"]  = _make_mat("sidewalk_stain",  (0.40, 0.38, 0.35, 1.0), roughness=0.86)
    M["oil_sheen"]       = _make_mat("oil_sheen",       (0.04, 0.06, 0.08, 0.60), roughness=0.10)
    M["grass_tuft"]      = _make_mat("grass_tuft",      (0.05, 0.24, 0.07, 1.0), roughness=0.95)
    # Aliases for misc factory lookups
    M["anchor_facade"]   = M["facade"]
    M["bench"]           = _make_mat("bench",           (0.32, 0.19, 0.10, 1.0), roughness=0.82)
    M["stone"]           = _make_mat("stone",           (0.56, 0.54, 0.50, 1.0), roughness=0.82)
    M["water"]           = _make_glass("water",         tint=(0.12, 0.38, 0.62), alpha=0.75)
    M["bronze"]          = _make_mat("bronze",          (0.55, 0.32, 0.13, 1.0), metallic=0.45)
    M["planter"]         = _make_mat("planter",         (0.42, 0.25, 0.14, 1.0), roughness=0.80)
    M["hydrant"]         = _make_mat("hydrant",         (0.78, 0.05, 0.03, 1.0), roughness=0.35)
    M["bus_stop_glass"]  = _make_glass("bus_stop_glass", tint=(0.22, 0.38, 0.45), alpha=0.55)
    M["bus_stop_sign"]   = _make_mat("bus_stop_sign",   (0.05, 0.22, 0.72, 1.0))
    M["sign"]            = _make_mat("sign",            (0.04, 0.20, 0.70, 1.0))
    M["trash"]           = _make_mat("trash",           (0.08, 0.22, 0.10, 1.0), roughness=0.80)
    M["soil"]            = _make_mat("soil",            (0.13, 0.075, 0.035, 1.0), roughness=0.96)
    M["shrub"]           = _make_mat("shrub",           (0.05, 0.24, 0.08, 1.0), roughness=0.90)
    M["leaf"]            = M["leaf"]
    M["flower_yellow"]   = _make_mat("flower_yellow",   (0.95, 0.78, 0.10, 1.0), roughness=0.80)
    M["person_skin"]     = _make_mat("person_skin",     (0.68, 0.48, 0.34, 1.0))
    M["person_pants"]    = _make_mat("person_pants",    (0.05, 0.06, 0.09, 1.0))
    M["person_hair"]     = _make_mat("person_hair",     (0.06, 0.035, 0.018, 1.0))
    M["person_shoe"]     = _make_mat("person_shoe",     (0.025, 0.022, 0.020, 1.0))
    M["person_shirt_red"]   = _make_mat("shirt_red",   (0.70, 0.08, 0.08, 1.0))
    M["person_shirt_blue"]  = _make_mat("shirt_blue",  (0.07, 0.18, 0.55, 1.0))
    M["person_shirt_green"] = _make_mat("shirt_green", (0.08, 0.42, 0.20, 1.0))
    return M

# ---------------------------------------------------------------------------
# Primitive helpers (bypassing infinigen tagging)
# ---------------------------------------------------------------------------

def _cube(name, loc, dims, mat, bevel=0.015):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel > 0:
        m = obj.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
        m.affect = "EDGES"
        obj.modifiers.new("wn", "WEIGHTED_NORMAL")
    return obj


def _cyl(name, loc, radius, depth, mat, vertices=48):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    return obj


def _sphere(name, loc, radius, mat):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16,
                                          radius=radius, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    return obj


def _mesh(name, verts, faces, mat, smooth=False):
    bpy.ops.object.select_all(action="DESELECT")
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return obj


# ---------------------------------------------------------------------------
# Road & sidewalk
# ---------------------------------------------------------------------------

def build_road(M, block=64.0, road_w=7.0, walk_w=3.2, curb_h=0.16):
    half = block / 2
    hr   = road_w          # half-road (one direction)
    wi   = hr + walk_w     # inner sidewalk boundary

    # Ground plane (concrete base)
    _cube("road:base", (0, 0, curb_h / 2 - 0.01),
          (block, block, curb_h), M["concrete"], bevel=0.0)

    # Lawn strips
    for lid, cx, cy, sx, sy in [
        ("nw", -22,  22, 12, 10),
        ("ne",  22,  22, 11,  9),
        ("sw", -22, -22, 10,  8),
        ("plaza", 24, -25, 7, 2.5),
    ]:
        _cube(f"road:lawn:{lid}", (cx, cy, curb_h + 0.012), (sx, sy, 0.032), M["grass"], bevel=0.02)

    # Asphalt roads
    _cube("road:main_x", (0, 0, 0.025), (block, road_w * 2, 0.06), M["asphalt"], bevel=0.0)
    _cube("road:cross_y", (0, 0, 0.028), (road_w * 2, block, 0.065), M["asphalt"], bevel=0.0)

    # Curbs (8 segments)
    for cid, cx, cy, sx, sy in [
        ("nm_w", -half / 2 - hr, hr + 0.08, half - road_w * 2, 0.16),
        ("nm_e",  half / 2 + hr, hr + 0.08, half - road_w * 2, 0.16),
        ("sm_w", -half / 2 - hr, -hr - 0.08, half - road_w * 2, 0.16),
        ("sm_e",  half / 2 + hr, -hr - 0.08, half - road_w * 2, 0.16),
        ("wc_s", -hr - 0.08, -half / 2 - hr, 0.16, half - road_w * 2),
        ("wc_n", -hr - 0.08,  half / 2 + hr, 0.16, half - road_w * 2),
        ("ec_s",  hr + 0.08, -half / 2 - hr, 0.16, half - road_w * 2),
        ("ec_n",  hr + 0.08,  half / 2 + hr, 0.16, half - road_w * 2),
    ]:
        _cube(f"road:curb:{cid}", (cx, cy, curb_h + 0.035), (sx, sy, 0.07), M["curb"], bevel=0.02)

    # Sidewalk expansion joints
    seam_z = curb_h + 0.010
    for qid, xr, yr in [
        ("nw", (-half, -wi), (wi, half)),
        ("ne", (wi, half),   (wi, half)),
        ("sw", (-half, -wi), (-half, -wi)),
        ("se", (wi, half),   (-half, -wi)),
    ]:
        for idx, x in enumerate(np.arange(xr[0] + 2.0, xr[1], 2.0)):
            _cube(f"road:sjoint:{qid}:x:{idx}",
                  (x, (yr[0]+yr[1])/2, seam_z),
                  (0.024, abs(yr[1]-yr[0]), 0.008), M["concrete_seam"], bevel=0.0)
        for idx, y in enumerate(np.arange(yr[0] + 2.0, yr[1], 2.0)):
            _cube(f"road:sjoint:{qid}:y:{idx}",
                  ((xr[0]+xr[1])/2, y, seam_z),
                  (abs(xr[1]-xr[0]), 0.024, 0.008), M["concrete_seam"], bevel=0.0)

    # Lane markings (centre dashes)
    for i, x in enumerate(np.linspace(-half + 6, half - 6, 9)):
        _cube(f"road:lane_x:{i}", (x, 0, 0.032), (2.1, 0.10, 0.014), M["paint"], bevel=0.0)
    for i, y in enumerate(np.linspace(-half + 6, half - 6, 9)):
        _cube(f"road:lane_y:{i}", (0, y, 0.032), (0.10, 2.1, 0.014), M["paint"], bevel=0.0)

    # Crosswalk stripes (4 sides)
    for name, cx, cy, axis_cw in [
        ("north", 0,  hr + walk_w * 0.35, "x"),
        ("south", 0, -hr - walk_w * 0.35, "x"),
        ("east",  hr + walk_w * 0.35, 0,  "y"),
        ("west", -hr - walk_w * 0.35, 0,  "y"),
    ]:
        for k, off in enumerate(np.linspace(-2.8, 2.8, 7)):
            if axis_cw == "x":
                loc  = (cx + off, cy, 0.082)
                dims = (0.40, road_w * 1.75, 0.016)
            else:
                loc  = (cx, cy + off, 0.082)
                dims = (road_w * 1.75, 0.40, 0.016)
            _cube(f"road:xwalk:{name}:{k}", loc, dims, M["paint"], bevel=0.0)

    # Stop lines
    for sid, cx, cy, dims in [
        ("n",  0,  hr + walk_w * 0.75, (road_w * 1.8, 0.18, 0.016)),
        ("s",  0, -hr - walk_w * 0.75, (road_w * 1.8, 0.18, 0.016)),
        ("e",  hr + walk_w * 0.75, 0,  (0.18, road_w * 1.8, 0.016)),
        ("w", -hr - walk_w * 0.75, 0,  (0.18, road_w * 1.8, 0.016)),
    ]:
        _cube(f"road:stop:{sid}", (cx, cy, 0.084), dims, M["paint"], bevel=0.0)

    # Asphalt patches (wear detail)
    for i, (x, y, sx, sy) in enumerate([
        (-20, -1.5, 5.2, 1.3), (18, 1.6, 4.0, 1.2),
        (1.5, -20, 1.2, 4.8), (-1.6, 14, 1.1, 4.0),
    ]):
        _cube(f"road:patch:{i}", (x, y, 0.090), (sx, sy, 0.009), M["asphalt_patch"], bevel=0.01)

    # Manholes
    for i, (x, y) in enumerate([(-12, 2.5), (14, -2.4), (2.4, -14)]):
        obj = _cyl(f"road:manhole:{i}", (x, y, 0.100), 0.42, 0.016, M["manhole"], vertices=32)

    # Curb ramps + tactile paving
    for rid, x, y in [("nw", -5.4, 5.4), ("ne", 5.4, 5.4), ("se", 5.4, -5.4), ("sw", -5.4, -5.4)]:
        _cube(f"road:ramp:{rid}", (x, y, curb_h + 0.020), (1.4, 1.4, 0.050), M["curb_ramp"], bevel=0.04)
        _cube(f"road:tactile:{rid}", (x, y, curb_h + 0.055), (0.95, 0.95, 0.022), M["tactile_paving"], bevel=0.01)

    # Bollards around intersection
    for i, (bx, by) in enumerate([
        (-7.2,  7.2), (-5.5,  7.2), ( 7.2,  7.2), ( 7.2,  5.5),
        ( 7.2, -7.2), ( 5.5, -7.2), (-7.2, -7.2), (-7.2, -5.5),
    ]):
        _cyl(f"road:bollard:{i}", (bx, by, 0.55), 0.08, 0.90, M["bollard"], vertices=16)


# ---------------------------------------------------------------------------
# Buildings (low-rise: max 9 m)
# ---------------------------------------------------------------------------

def build_buildings(M, rng):
    specs = [
        # id, cx, cy, width, depth, height, wall_mat
        ("nw_a",  -22,  22, 16, 10, rng.uniform(5.5, 8.5), "brick"),
        ("nw_b",  -34,  26, 10,  8, rng.uniform(4.5, 7.0), "facade"),
        ("ne_a",   22,  22, 14, 10, rng.uniform(5.0, 9.0), "facade"),
        ("ne_b",   34,  26, 10,  7, rng.uniform(4.5, 7.5), "brick"),
        ("sw_a",  -22, -22, 16, 10, rng.uniform(5.0, 8.0), "brick"),
        ("sw_b",  -35, -27, 10,  7, rng.uniform(4.0, 7.0), "facade"),
        ("se_a",   22, -22, 14, 10, rng.uniform(5.5, 8.5), "facade"),
        ("se_b",   35, -27, 10,  7, rng.uniform(4.0, 6.5), "brick"),
    ]
    for bid, cx, cy, bw, bd, bh, wall_key in specs:
        wall_mat = M[wall_key]
        # Main shell
        _cube(f"bldg:{bid}:shell", (cx, cy, bh / 2), (bw, bd, bh), wall_mat)
        # Roof cap
        _cube(f"bldg:{bid}:roof", (cx, cy, bh + 0.17), (bw + 0.25, bd + 0.25, 0.34),
              M["building_top"], bevel=0.02)
        # Cornice (ledge just below roof)
        _cube(f"bldg:{bid}:cornice", (cx, cy, bh - 0.28), (bw + 0.18, bd + 0.18, 0.14),
              M["building_top"], bevel=0.01)
        # Window grid on each main facade
        _add_building_windows(M, bid, cx, cy, bw, bd, bh)


def _add_building_windows(M, bid, cx, cy, bw, bd, bh):
    floor_h  = 2.8
    n_floors = max(1, int((bh - 1.2) / floor_h))
    win_w, win_h = 0.90, 1.10
    gap_x, gap_y = 0.65, 0.70
    mat = _make_glass("bldg_win", tint=(0.20, 0.34, 0.44), alpha=0.50)

    # North face (y = +bd/2)
    n_cols_x = max(2, int(bw / (win_w + gap_x)))
    for fl in range(n_floors):
        z = 1.0 + fl * floor_h + floor_h * 0.40
        for col in range(n_cols_x):
            x = cx - bw / 2 + (col + 0.5) * bw / n_cols_x
            _cube(f"bldg:{bid}:win:n:{fl}:{col}",
                  (x, cy + bd / 2 + 0.010, z),
                  (win_w, 0.08, win_h), mat, bevel=0.01)
    # South face
    for fl in range(n_floors):
        z = 1.0 + fl * floor_h + floor_h * 0.40
        for col in range(n_cols_x):
            x = cx - bw / 2 + (col + 0.5) * bw / n_cols_x
            _cube(f"bldg:{bid}:win:s:{fl}:{col}",
                  (x, cy - bd / 2 - 0.010, z),
                  (win_w, 0.08, win_h), mat, bevel=0.01)
    # East face
    n_cols_y = max(2, int(bd / (win_w + gap_y)))
    for fl in range(n_floors):
        z = 1.0 + fl * floor_h + floor_h * 0.40
        for col in range(n_cols_y):
            y = cy - bd / 2 + (col + 0.5) * bd / n_cols_y
            _cube(f"bldg:{bid}:win:e:{fl}:{col}",
                  (cx + bw / 2 + 0.010, y, z),
                  (0.08, win_w, win_h), mat, bevel=0.01)


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

VEHICLE_CONFIGS = [
    # (vid, x, y, axis, vehicle_type, variant, color)
    ("sed_r",   -11, -2.2, "x", "car", "sedan",    "car_red"),
    ("suv_w",     3, -2.2, "x", "car", "suv",      "car_white"),
    ("htch_b",   14,  2.0, "x", "car", "hatchback","car_blue"),
    ("pkup_k",   -4,  2.0, "x", "car", "pickup",   "car_black"),
    ("bus_y",   2.0,  14,  "y", "bus", "sedan",    "bus_yellow"),
]

def place_vehicles(M):
    vf = VehicleFactory(M)
    for vid, x, y, axis, vtype, variant, color in VEHICLE_CONFIGS:
        req = UrbanAssetRequest(
            asset_type="vehicle",
            location=(x, y, 0),
            semantic="vehicle",
            yaw=0.0,
            params={"id": vid, "axis": axis, "vehicle_type": vtype,
                    "variant": variant, "color": color},
        )
        objs, info = vf.create(req)
        print(f"  [{info['type']}] {vid} placed at ({x}, {y}): {len(objs)} parts")


# ---------------------------------------------------------------------------
# Traffic lights (4 corners)
# ---------------------------------------------------------------------------

def place_traffic_lights(M):
    tf = TrafficLightFactory(M)
    for corner, x, y, facing in [
        ("nw", -6.4,  6.4, "y"),
        ("ne",  6.4,  6.4, "x"),
        ("se",  6.4, -6.4, "y"),
        ("sw", -6.4, -6.4, "x"),
    ]:
        tf.create(UrbanAssetRequest(
            asset_type="traffic-light",
            location=(x, y, 0),
            semantic="traffic-light",
            yaw=0.0,
            params={"id": corner, "facing_axis": facing},
        ))


# ---------------------------------------------------------------------------
# Street furniture
# ---------------------------------------------------------------------------

def place_street_furniture(M):
    sf = StreetFurnitureFactory(M)

    # Street lamps along main road (N + S sides)
    lamp_x = list(np.linspace(-24, 24, 7))
    for i, lx in enumerate(lamp_x):
        for ly, sign in [(7.6, -1), (-7.6, 1)]:
            sf.create_street_lamp(UrbanAssetRequest(
                asset_type="street-lamp",
                location=(lx, ly, 0),
                semantic="street-lamp",
                yaw=0.0,
                params={"id": i * 2 + (0 if sign < 0 else 1), "head_sign": sign},
            ))

    # Bus stop (south sidewalk)
    sf.create_bus_stop(UrbanAssetRequest(
        asset_type="bus-stop",
        location=(-16, -8.8, 0),
        semantic="bus-stop",
        yaw=0.0,
        params={"id": 0},
    ))

    # Fire hydrant
    sf.create_fire_hydrant(UrbanAssetRequest(
        asset_type="fire-hydrant",
        location=(-9.0, -7.2, 0),
        semantic="fire-hydrant",
        yaw=0.0,
        params={"id": 0},
    ))

    # Benches
    for i, (bx, by, yaw) in enumerate([
        (16, -8.5, 0.0), (18, -8.5, 0.0), (-20, 8.2, math.pi),
    ]):
        sf.create_bench(UrbanAssetRequest(
            asset_type="bench",
            location=(bx, by, 0),
            semantic="bench",
            yaw=yaw,
            params={"id": i},
        ))

    # Planters
    for i, (px, py) in enumerate([
        (20, -8.8), (22, -8.8), (-18, 8.5), (14, 8.5),
    ]):
        sf.create_planter(UrbanAssetRequest(
            asset_type="planter",
            location=(px, py, 0),
            semantic="planter",
            yaw=0.0,
            params={"id": i},
        ))

    # Bike racks
    for i, bx in enumerate([8.5, 9.2, 9.9]):
        sf.create_bike_rack(UrbanAssetRequest(
            asset_type="bike-rack",
            location=(bx, -8.8, 0),
            semantic="bike-rack",
            yaw=0.0,
            params={"id": i},
        ))

    # Trash bins
    sf.create_trash_bin(UrbanAssetRequest(
        asset_type="trash-bin",
        location=(12.5, -8.2, 0),
        semantic="trash-bin",
        yaw=0.0,
        params={"id": 0},
    ))

    # Traffic signs
    sf.create_traffic_sign(UrbanAssetRequest(
        asset_type="traffic-sign",
        location=(6.8, -8.2, 0),
        semantic="traffic-sign",
        yaw=0.0,
        params={"id": 0},
    ))


# ---------------------------------------------------------------------------
# Lightweight procedural trees  (no heavy TreeFactory — keeps memory low)
# ---------------------------------------------------------------------------

def _make_tree(M, name, x, y, trunk_h, canopy_r, lean_x=0.0, lean_y=0.0):
    """Simple but visually convincing street tree: tapered trunk + layered canopy."""
    # Trunk (tapered: wider at base)
    trunk = _cyl(f"tree:{name}:trunk", (x, y, trunk_h / 2),
                 0.095, trunk_h, M["trunk"], vertices=10)
    trunk.scale.x = 1.2
    trunk.scale.y = 1.2
    bpy.ops.object.select_all(action="DESELECT")
    trunk.select_set(True)
    bpy.context.view_layer.objects.active = trunk

    # Root flare
    flare = _cyl(f"tree:{name}:flare", (x, y, 0.18),
                 0.22, 0.36, M["trunk"], vertices=10)

    # 3 canopy layers (ellipsoid spheres at different heights/offsets)
    canopy_specs = [
        (0.0,  0.0,  trunk_h + canopy_r * 0.55,  canopy_r,       canopy_r * 0.70),
        (0.18, 0.12, trunk_h + canopy_r * 0.15,  canopy_r * 0.85, canopy_r * 0.60),
        (-0.12, 0.08, trunk_h - canopy_r * 0.20, canopy_r * 0.72, canopy_r * 0.55),
    ]
    canopies = []
    for ci, (ox, oy, cz, cr, ch) in enumerate(canopy_specs):
        c = _sphere(f"tree:{name}:canopy:{ci}", (x + ox, y + oy, cz), 1.0,
                    M["leaf"] if ci % 2 == 0 else M["leaf_dark"])
        c.scale = (cr, cr, ch)
        bpy.ops.object.select_all(action="DESELECT")
        c.select_set(True)
        bpy.context.view_layer.objects.active = c
        bpy.ops.object.transform_apply(scale=True)
        canopies.append(c)

    # 5 main branches (cylinders from mid-trunk to canopy edge)
    for bi in range(5):
        angle = bi * math.tau / 5 + lean_x
        blen  = canopy_r * 0.65
        b_end_x = x + math.cos(angle) * blen
        b_end_y = y + math.sin(angle) * blen
        b_z0    = trunk_h * 0.55
        b_z1    = trunk_h + canopy_r * 0.25

        # branch as a thin cylinder_between via mesh
        dx = b_end_x - x; dy = b_end_y - y; dz = b_z1 - b_z0
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        cx = (x + b_end_x) / 2; cy_b = (y + b_end_y) / 2
        cz_b = (b_z0 + b_z1) / 2
        br = _cyl(f"tree:{name}:branch:{bi}", (cx, cy_b, cz_b),
                  0.028, length, M["bark_dark"], vertices=6)
        br.rotation_euler = (
            math.atan2(math.sqrt(dx*dx + dy*dy), dz),
            0,
            math.atan2(dy, dx),
        )

    # Tree pit stones (4 small blocks around base)
    for pi, ang in enumerate([0, math.pi/2, math.pi, 3*math.pi/2]):
        px = x + math.cos(ang) * 0.32
        py = y + math.sin(ang) * 0.32
        _cube(f"tree:{name}:pit:{pi}", (px, py, 0.055),
              (0.45, 0.10, 0.11) if pi % 2 == 0 else (0.10, 0.45, 0.11),
              M["curb"], bevel=0.008)


def place_trees(M):
    tree_positions = [
        # (name, x, y, trunk_h, canopy_r)
        ("n1", -26,  8.2, 4.8, 2.8),
        ("n2", -20,  8.2, 5.2, 3.0),
        ("n3", -14,  8.2, 4.6, 2.6),
        ("n4",  -8,  8.2, 5.0, 2.9),
        ("n5",  -2,  8.2, 4.4, 2.5),
        ("n6",   4,  8.2, 5.1, 2.8),
        ("n7",  10,  8.2, 4.7, 2.7),
        ("n8",  16,  8.2, 5.3, 3.1),
        ("n9",  22,  8.2, 4.5, 2.6),
        ("s1", -26, -8.5, 4.9, 2.8),
        ("s2", -18, -8.5, 5.0, 2.9),
        ("s3",  -8, -8.5, 4.7, 2.7),
        ("s4",   4, -8.5, 5.2, 3.0),
        ("s5",  14, -8.5, 4.6, 2.6),
        ("s6",  24, -8.5, 5.0, 2.8),
        ("e1",  8.2, 18,  4.8, 2.7),
        ("e2",  8.2, 26,  5.1, 2.9),
        ("w1", -8.5, 16,  4.9, 2.8),
        ("w2", -8.5, 24,  5.0, 2.7),
    ]
    for name, x, y, trunk_h, canopy_r in tree_positions:
        _make_tree(M, name, x, y, trunk_h, canopy_r)
    print(f"  Placed {len(tree_positions)} lightweight trees")


# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

def setup_lighting():
    # Primary sun (afternoon light from SW)
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.active_object
    sun.name = "light:sun"
    sun.data.energy = 4.5
    sun.data.angle = math.radians(2.5)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-42))

    # Large sky fill area light (north, cool)
    bpy.ops.object.light_add(type="AREA", location=(0, 30, 18))
    fill = bpy.context.active_object
    fill.name = "light:sky_fill"
    fill.data.energy = 120
    fill.data.size = 30
    fill.data.color = (0.70, 0.82, 1.00)
    fill.rotation_euler = (math.radians(65), 0, 0)

    # Bounce fill from ground (warm, low)
    bpy.ops.object.light_add(type="AREA", location=(0, 0, 0.2))
    bounce = bpy.context.active_object
    bounce.name = "light:bounce"
    bounce.data.energy = 25
    bounce.data.size = 40
    bounce.data.color = (1.00, 0.92, 0.80)
    bounce.rotation_euler = (math.radians(180), 0, 0)


def setup_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.48, 0.58, 0.75, 1.0)
        bg.inputs["Strength"].default_value = 0.35
    # Color management
    try:
        bpy.context.scene.view_settings.view_transform = "Filmic"
        bpy.context.scene.view_settings.look = "Medium High Contrast"
        bpy.context.scene.view_settings.exposure = 0.25
        bpy.context.scene.view_settings.gamma = 1.0
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Camera orbit animation
# ---------------------------------------------------------------------------

def setup_camera(num_frames, fps):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam_obj = bpy.context.active_object
    cam_obj.name = "camera:orbit"
    cam = cam_obj.data
    cam.lens = 40
    cam.clip_start = 0.5
    cam.clip_end = 300
    bpy.context.scene.camera = cam_obj

    scene = bpy.context.scene
    scene.frame_start = 0
    scene.frame_end = num_frames - 1
    scene.render.fps = fps

    # Focus point: centre of vehicle cluster
    target = Vector((0.0, 0.0, 1.6))
    radius  = 26
    height_base = 7.5

    # Orbit: 270° arc from SW to NW (counter-clockwise viewed from top)
    start_a = math.radians(230)
    total_a = math.radians(270)

    for f in range(num_frames):
        t = f / max(num_frames - 1, 1)
        # Smooth-step easing
        ts = t * t * (3 - 2 * t)
        angle = start_a + ts * total_a

        # Gentle height variation: dip slightly at start/end, peak in middle
        h = height_base + math.sin(ts * math.pi) * 2.5

        pos = Vector((radius * math.cos(angle), radius * math.sin(angle), h))
        cam_obj.location = pos

        direction = target - pos
        cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

        cam_obj.keyframe_insert(data_path="location", frame=f)
        cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)

    # Set all keyframes to BEZIER for smooth motion
    if cam_obj.animation_data and cam_obj.animation_data.action:
        for fc in cam_obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"

    return cam_obj


# ---------------------------------------------------------------------------
# GPU setup
# ---------------------------------------------------------------------------

def enable_gpu():
    """Enable GPU rendering. Tries OPTIX → CUDA → HIP → METAL in order."""
    prefs = bpy.context.preferences
    cycles_addon = prefs.addons.get("cycles")
    if cycles_addon is None:
        print("[GPU] cycles addon not found; EEVEE_NEXT will use GPU by default")
        return False

    cp = cycles_addon.preferences
    for device_type in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            cp.compute_device_type = device_type
            # Refresh device list
            cp.get_devices()
            gpu_devs = [d for d in cp.devices if d.type != "CPU"]
            if gpu_devs:
                for d in cp.devices:
                    d.use = (d.type != "CPU")
                names = [d.name for d in gpu_devs]
                print(f"[GPU] Enabled {device_type}: {names}")
                return True
        except Exception as e:
            print(f"[GPU] {device_type} unavailable: {e}")

    print("[GPU] No discrete GPU found; falling back to CPU")
    return False


# ---------------------------------------------------------------------------
# Render settings
# ---------------------------------------------------------------------------

def setup_render(render_path, num_frames, fps, res_x=1920, res_y=1080):
    scene = bpy.context.scene
    rd = scene.render

    # EEVEE_NEXT is GPU-only (Blender 4.2+); also ensure GPU prefs are set
    rd.engine = "BLENDER_EEVEE_NEXT"
    rd.resolution_x = res_x
    rd.resolution_y = res_y
    rd.resolution_percentage = 100
    rd.fps = fps
    rd.use_motion_blur = False

    # EEVEE quality settings
    eevee = scene.eevee
    eevee.taa_render_samples = 64
    for attr, val in [
        ("use_gtao", True), ("gtao_distance", 0.35), ("gtao_factor", 0.85),
        ("use_bloom", True), ("bloom_threshold", 0.92), ("bloom_intensity", 0.04),
        ("use_ssr", True), ("use_ssr_refraction", True),
        ("shadow_cube_size", "2048"), ("shadow_cascade_size", "2048"),
    ]:
        try:
            setattr(eevee, attr, val)
        except AttributeError:
            pass

    # Output: MP4 via FFmpeg
    rd.image_settings.file_format = "FFMPEG"
    rd.ffmpeg.format = "MPEG4"
    rd.ffmpeg.codec = "H264"
    rd.ffmpeg.constant_rate_factor = "MEDIUM"
    rd.ffmpeg.ffmpeg_preset = "GOOD"
    rd.filepath = render_path

    scene.frame_start = 0
    scene.frame_end = num_frames - 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Urban Vehicle Scene v2.1")
    print("=" * 60)

    # Clear default objects
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)

    rng = np.random.default_rng(seed=42)

    print("[1/7] Building materials...")
    M = build_materials()

    print("[2/7] Building road & sidewalk...")
    build_road(M)

    print("[3/7] Building low-rise buildings...")
    build_buildings(M, rng)

    print("[4/7] Placing vehicles...")
    place_vehicles(M)

    print("[5/7] Placing traffic lights & street furniture...")
    place_traffic_lights(M)
    place_street_furniture(M)

    print("[6/7] Placing trees...")
    place_trees(M)

    print("[7/7] Setting up lighting, camera, render...")
    enable_gpu()
    setup_world()
    setup_lighting()
    setup_camera(NUM_FRAMES, FPS)
    setup_render(RENDER_PATH, NUM_FRAMES, FPS, res_x=1920, res_y=1080)

    # Save .blend
    print(f"\nSaving .blend → {BLEND_PATH}")
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print("Saved.")

    # Render animation → MP4
    print(f"\nRendering {NUM_FRAMES} frames → {RENDER_PATH}")
    print("(This may take several minutes with EEVEE...)")
    bpy.ops.render.render(animation=True)
    print("\nDone! Output:")
    print(f"  Scene : {BLEND_PATH}")
    print(f"  Video : {RENDER_PATH}")


if __name__ == "__main__":
    main()
