#!/usr/bin/env python3
"""
openx_vehicle_preview.py — single-vehicle orbit render using OpenXVehicleFactory.

If OPENX_ASSETS_ROOT points to a directory with .blend/.xoma vehicle assets,
the factory loads one of them, normalises scale, randomises materials, adds
a license plate and optional dirt overlay, then renders a 150-frame orbit video.

When no OpenX assets are found the procedural VehicleFactory fallback is used
automatically — so the script always produces a result.

Output:
    outputs/urban_v3_vehicle/openx_preview0001-0150.mp4
    outputs/urban_v3_vehicle/openx_metadata.json

Run:
    cd ${WORLDBRIDGE_ROOT}/infinigen
    blender -b --python infinigen_examples/openx_vehicle_preview.py
    # or with assets:
    OPENX_ASSETS_ROOT=/path/to/openx blender -b --python ...
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


import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONDA = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA.exists():
    sys.path.insert(0, str(CONDA))

import bpy
from mathutils import Vector

# patch tagging so it works without a full Infinigen TaskGraph init
import infinigen.core.tagging as _tag_mod
_tag_mod.tag_object = lambda obj, semantic, **kw: \
    obj.get("semantic") or obj.__setitem__("semantic", semantic)

from infinigen.assets.objects.vehicles.openx_vehicle import OpenXVehicleFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

# ─── Paths ────────────────────────────────────────────────────────────────────

OUTPUT_DIR  = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_vehicle')
BLEND_PATH  = str(OUTPUT_DIR / "openx_preview.blend")
RENDER_PATH = str(OUTPUT_DIR / "openx_preview")
META_PATH   = str(OUTPUT_DIR / "openx_metadata.json")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NUM_FRAMES = 150
FPS        = 25

# ─── GPU ──────────────────────────────────────────────────────────────────────

def enable_gpu():
    prefs = bpy.context.preferences
    cycles_prefs = prefs.addons.get("cycles")
    if not cycles_prefs:
        return
    cp = cycles_prefs.preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            cp.compute_device_type = backend
            cp.refresh_devices()
            devs = cp.get_devices_for_type(backend)
            if devs:
                for d in devs:
                    d.use = (d.type != "CPU")
                active = [d.name for d in devs if d.use]
                print(f"[GPU] {backend}: {active}")
                break
        except Exception:
            continue
    bpy.context.scene.cycles.device = "GPU"

# ─── Materials ────────────────────────────────────────────────────────────────

def _make_mat(name, color, roughness=0.55, metallic=0.0,
              emission_strength=0.0, bump_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf  = nodes.get("Principled BSDF")
    if not bsdf:
        return mat
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["Metallic"].default_value   = metallic
    if len(color) > 3 and color[3] < 1.0:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
        mat.blend_method = "BLEND"
    if emission_strength > 0:
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = color; break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if bump_strength > 0 and "Normal" in bsdf.inputs:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value  = 48
        noise.inputs["Detail"].default_value = 12
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value  = bump_strength
        bump.inputs["Distance"].default_value  = 0.04
        links.new(noise.outputs["Fac"],   bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_glass(name, tint=(0.04, 0.07, 0.10), alpha=0.14):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
        bsdf.inputs["Roughness"].default_value  = 0.020
        for k in ("Transmission Weight", "Transmission"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = 0.92; break
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
    return mat


def _make_car_paint(name, color):
    mat = _make_mat(name, color, roughness=0.18, metallic=0.82)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        for k in ("Coat Weight", "Clearcoat"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = 0.88; break
        for k in ("Coat Roughness", "Clearcoat Roughness"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = 0.032; break
    return mat


def build_materials():
    M = {}
    # car paints
    M["car_red"]    = _make_car_paint("car_red",    (0.58, 0.040, 0.030, 1.0))
    M["car_blue"]   = _make_car_paint("car_blue",   (0.030, 0.12, 0.52, 1.0))
    M["car_white"]  = _make_car_paint("car_white",  (0.82, 0.84, 0.80, 1.0))
    M["car_black"]  = _make_car_paint("car_black",  (0.040, 0.040, 0.042, 1.0))
    M["car_silver"] = _make_car_paint("car_silver", (0.55, 0.57, 0.60, 1.0))
    # shared parts
    M["car_glass"]      = _make_glass("car_glass")
    M["tire"]           = _make_mat("tire",        (0.022, 0.020, 0.018, 1.0), roughness=0.90, bump_strength=0.12)
    M["rim_metal"]      = _make_mat("rim_metal",   (0.80, 0.80, 0.84, 1.0), metallic=0.96, roughness=0.10)
    M["chrome"]         = _make_mat("chrome",      (0.88, 0.88, 0.90, 1.0), metallic=1.0,  roughness=0.03)
    M["metal"]          = _make_mat("metal",       (0.18, 0.18, 0.18, 1.0), roughness=0.62, metallic=0.22)
    M["brake_disc"]     = _make_mat("brake_disc",  (0.30, 0.28, 0.26, 1.0), metallic=0.55, roughness=0.52)
    M["headlight"]      = _make_mat("headlight",   (1.00, 0.92, 0.70, 1.0), emission_strength=2.5)
    M["headlight_led"]  = _make_mat("headlight_led", (0.94, 0.96, 1.00, 1.0), emission_strength=5.0)
    M["tail_light"]     = _make_mat("tail_light",  (0.90, 0.020, 0.010, 1.0), emission_strength=2.0)
    M["tail_indicator"] = _make_mat("tail_indicator", (0.90, 0.42, 0.020, 1.0), emission_strength=1.2)
    M["tail_reverse"]   = _make_mat("tail_reverse", (0.95, 0.95, 0.95, 1.0), emission_strength=0.9)
    M["license_plate"]  = _make_mat("license_plate", (0.92, 0.90, 0.78, 1.0), roughness=0.42)
    M["signal_box"]     = _make_mat("signal_box",  (0.030, 0.032, 0.030, 1.0), roughness=0.72)
    M["car_interior"]   = _make_mat("car_interior", (0.040, 0.040, 0.050, 1.0), roughness=0.86)
    M["bus_yellow"]     = _make_car_paint("bus_yellow", (0.92, 0.66, 0.080, 1.0))
    return M

# ─── Scene setup ──────────────────────────────────────────────────────────────

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials,
                bpy.data.cameras, bpy.data.lights):
        for blk in list(col):
            col.remove(blk)


def add_ground_plane(mat_asphalt):
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0, 0, 0))
    gp = bpy.context.active_object
    gp.name = "ground_plane"
    gp.data.materials.append(mat_asphalt)
    return gp


def add_world_sky(strength=1.0):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg   = nt.nodes.new("ShaderNodeBackground")
    sky  = nt.nodes.new("ShaderNodeTexSky")
    out  = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(32)
    sky.sun_rotation   = math.radians(45)
    sky.altitude = 0.0
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_camera_orbit(radius=7.5, height=2.6, target_z=0.72):
    """Add a camera that orbits the vehicle over NUM_FRAMES."""
    bpy.ops.object.camera_add(location=(radius, 0, height))
    cam = bpy.context.active_object
    cam.name = "OrbitCamera"

    # point at vehicle centre
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, target_z))
    target = bpy.context.active_object
    target.name = "CameraTarget"

    track = cam.constraints.new("TRACK_TO")
    track.target    = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis   = "UP_Y"

    # animate camera on a circle
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("CameraOrbit")
    for frame in range(1, NUM_FRAMES + 1):
        angle = (frame - 1) / NUM_FRAMES * math.tau
        cam.location = (radius * math.cos(angle),
                        radius * math.sin(angle),
                        height)
        cam.keyframe_insert("location", frame=frame)

    bpy.context.scene.camera = cam
    return cam, target


def add_key_light(energy=800.0):
    bpy.ops.object.light_add(type="SUN", location=(4, -6, 12))
    sun = bpy.context.active_object
    sun.name = "KeyLight"
    sun.data.energy        = energy
    sun.data.angle         = math.radians(2)
    sun.rotation_euler     = (math.radians(40), math.radians(20), math.radians(60))
    return sun


# ─── Render ───────────────────────────────────────────────────────────────────

def configure_render():
    sc  = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end   = NUM_FRAMES
    sc.render.fps  = FPS
    sc.render.engine          = "CYCLES"
    sc.cycles.samples         = 96
    sc.cycles.use_denoising   = True
    try:
        sc.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    sc.render.resolution_x         = 1920
    sc.render.resolution_y         = 1080
    sc.render.image_settings.file_format  = "FFMPEG"
    sc.render.ffmpeg.format              = "MPEG4"
    sc.render.ffmpeg.codec               = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"
    sc.render.filepath = RENDER_PATH
    print(f"[render] Cycles OPTIX GPU …")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    enable_gpu()
    clear_scene()
    bpy.context.scene.unit_settings.system       = "METRIC"
    bpy.context.scene.unit_settings.length_unit  = "METERS"

    mats = build_materials()
    mat_asphalt = _make_mat("asphalt", (0.032, 0.034, 0.036, 1.0),
                            roughness=0.92, bump_strength=0.06)

    # ── build factory (OpenX if OPENX_ASSETS_ROOT is set, else procedural) ──
    factory = OpenXVehicleFactory(mats, fallback=True)

    request = UrbanAssetRequest(
        asset_type = "vehicle",
        location   = (0.0, 0.0, 0.0),
        semantic   = "vehicle",
        yaw        = 0.0,
        params     = {"id": "0", "axis": "x", "variant": "sedan",
                      "color": "car_blue"},
    )

    print("[OpenX] Creating vehicle …")
    objects, meta = factory.create(request)
    print(f"[OpenX] Created {len(objects)} objects  source={meta.get('source','?')}")

    # ── scene ──
    add_ground_plane(mat_asphalt)
    add_world_sky(strength=1.2)
    add_key_light()
    add_camera_orbit(radius=7.5, height=2.6)

    # ── save blend ──
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[save] {BLEND_PATH}")

    # ── render ──
    configure_render()
    bpy.ops.render.render(animation=True)
    print(f"[render] Done → {RENDER_PATH}")

    # ── metadata JSON ──
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[meta]   {META_PATH}")


if __name__ == "__main__":
    main()
