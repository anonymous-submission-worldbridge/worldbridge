#!/usr/bin/env python3
"""
grass_asset_render.py — render Infinigen's procedural grass/lawn assets.

Assets rendered:
  1. GrassTuftFactory     – Bézier-curve individual grass tuft (30-60 blades)
  2. GrassesMonocotFactory – Geometry-nodes grass plant (16-64 leaves)
  3. TussockMonocotFactory  – Dense tussock clump (512-1024 leaves)
  4. WheatMonocotFactory    – Wheat plant with ear
  5. ReedMonocotFactory     – Reed / bullrush (3-4 m tall)

For each asset: a PNG preview + a .blend file.
Plus one combined 6-view grid PNG and a 150-frame orbit video.

GPU: OPTIX → CUDA → HIP → METAL  (CPU never used)

Run:
    cd ${WORLDBRIDGE_ROOT}/infinigen
    blender -b --python infinigen_examples/grass_asset_render.py
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
import gin
import numpy as np
from mathutils import Vector

# ── gin: load base.gin so @gin.configurable functions have valid defaults ──────
import infinigen
from infinigen.core import init

gin.clear_config()
init.apply_gin_configs(
    config_folders=[str(ROOT / "infinigen_examples/configs_nature")],
    configs=[],         # base.gin is always prepended automatically
    overrides=[],
    skip_unknown=True,
    finalize_config=False,
    mandatory_folders=[],
)

# ── GPU ────────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
from infinigen.core.init import configure_cycles_devices
configure_cycles_devices()
print(f"[GPU] device = {bpy.context.scene.cycles.device}")

# ── output paths ───────────────────────────────────────────────────────────────
OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_plants')
OUT.mkdir(parents=True, exist_ok=True)

# ── import grass factories ─────────────────────────────────────────────────────
from infinigen.assets.objects.grassland.grass_tuft import GrassTuftFactory
from infinigen.assets.objects.monocot.grasses import (
    GrassesMonocotFactory,
    WheatMonocotFactory,
    MaizeMonocotFactory,
    ReedMonocotFactory,
)
from infinigen.assets.objects.monocot.tussock import TussockMonocotFactory
from infinigen.assets.lighting.three_point_lighting import add_lighting
from infinigen.core.util.math import FixedSeed

# ── render helpers ─────────────────────────────────────────────────────────────

def enable_optix_denoiser():
    try:
        bpy.context.scene.cycles.denoiser = "OPTIX"
    except Exception:
        try:
            bpy.context.scene.cycles.denoiser = "OPENIMAGEDENOISE"
        except Exception:
            pass


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials,
                bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for blk in list(col):
            col.remove(blk)


def add_sky_world(strength=1.0, sun_elev_deg=30):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type        = "NISHITA"
    sky.sun_elevation   = math.radians(sun_elev_deg)
    sky.sun_rotation    = math.radians(45)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_ground(size=4.0, color=(0.030, 0.060, 0.020, 1.0)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    gp = bpy.context.active_object
    gp.name = "ground"
    mat = bpy.data.materials.new("ground_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.95
    gp.data.materials.append(mat)
    return gp


def place_camera_for_asset(asset, distance_mult=3.5, height_angle_deg=22):
    """Point a new camera at asset from the side at a pleasing angle."""
    bpy.context.view_layer.update()
    dim  = asset.dimensions
    size = max(dim.x, dim.y, dim.z)
    dist = size * distance_mult

    angle_rad = math.radians(height_angle_deg)
    cam_x = dist * math.cos(angle_rad)
    cam_z = asset.location.z + dim.z / 2 + dist * math.sin(angle_rad)
    cam_y = 0.0

    bpy.ops.object.camera_add(location=(cam_x, cam_y, cam_z))
    cam = bpy.context.active_object
    cam.name = "RenderCam"
    bpy.context.scene.camera = cam

    # TRACK_TO constraint pointing at asset centre
    bpy.ops.object.empty_add(type="PLAIN_AXES",
                              location=(asset.location.x,
                                        asset.location.y,
                                        asset.location.z + dim.z / 2))
    tgt = bpy.context.active_object
    tgt.name = "CamTarget"
    tc = cam.constraints.new("TRACK_TO")
    tc.target    = tgt
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis   = "UP_Y"
    return cam


def setup_render_png(filepath, samples=128, res_x=1920, res_y=1080):
    sc = bpy.context.scene
    sc.cycles.samples       = samples
    sc.cycles.use_denoising = True
    enable_optix_denoiser()
    sc.render.resolution_x  = res_x
    sc.render.resolution_y  = res_y
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath      = str(filepath)


def setup_render_video(filepath, n_frames=150, fps=25, samples=96, res_x=1920, res_y=1080):
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end   = n_frames
    sc.render.fps  = fps
    sc.cycles.samples       = samples
    sc.cycles.use_denoising = True
    enable_optix_denoiser()
    sc.render.resolution_x  = res_x
    sc.render.resolution_y  = res_y
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format              = "MPEG4"
    sc.render.ffmpeg.codec               = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"
    sc.render.filepath      = str(filepath)


def orbit_camera(asset, n_frames=150, radius_mult=3.5, height_angle_deg=22):
    """Animate camera orbit around asset."""
    bpy.context.view_layer.update()
    dim  = asset.dimensions
    size = max(dim.x, dim.y, dim.z)
    dist = size * radius_mult
    angle_h = math.radians(height_angle_deg)
    cam_h   = asset.location.z + dim.z / 2 + dist * math.sin(angle_h)

    bpy.ops.object.camera_add(location=(dist, 0, cam_h))
    cam = bpy.context.active_object
    cam.name = "OrbitCam"
    bpy.context.scene.camera = cam

    bpy.ops.object.empty_add(type="PLAIN_AXES",
                              location=(asset.location.x, asset.location.y,
                                        asset.location.z + dim.z * 0.4))
    tgt = bpy.context.active_object; tgt.name = "OrbitTarget"
    tc = cam.constraints.new("TRACK_TO")
    tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"

    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("Orbit")
    for f in range(1, n_frames + 1):
        ang = (f - 1) / n_frames * math.tau
        cam.location = (dist * math.cos(ang), dist * math.sin(ang), cam_h)
        cam.keyframe_insert("location", frame=f)


# ── asset generation ───────────────────────────────────────────────────────────

ASSETS = [
    ("GrassTuft",    GrassTuftFactory,        0,  False),   # uses seed=, not factory_seed=
    ("GrassMonocot", GrassesMonocotFactory,    1,  True),
    ("Tussock",      TussockMonocotFactory,    2,  True),
    ("Wheat",        WheatMonocotFactory,      3,  True),
    ("Maize",        MaizeMonocotFactory,      4,  True),
]


def make_asset(name, FactoryClass, seed, use_factory_seed=True):
    print(f"\n[grass] Creating {name} (seed={seed}) …")
    with FixedSeed(seed):
        if use_factory_seed:
            factory = FactoryClass(factory_seed=seed)
        else:
            factory = FactoryClass(seed=seed)
        asset   = factory.create_asset()
        factory.finalize_assets([asset])
    asset.location = (0, 0, 0)
    asset.name = name
    bpy.context.view_layer.update()
    dim = asset.dimensions
    print(f"  dims: {dim.x:.3f} × {dim.y:.3f} × {dim.z:.3f} m")
    return asset


# ── render each asset independently ───────────────────────────────────────────

def render_single(name, FactoryClass, seed, use_factory_seed=True):
    print(f"\n{'='*60}")
    print(f"  Rendering {name}")
    print(f"{'='*60}")

    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()
    add_sky_world(strength=1.1, sun_elev_deg=35)
    add_ground(size=6.0)

    asset = make_asset(name, FactoryClass, seed, use_factory_seed)

    # three-point lighting auto-sized to asset
    add_lighting(asset)

    # camera
    place_camera_for_asset(asset, distance_mult=4.0)

    # PNG render
    png_path = OUT / f"{name}.png"
    setup_render_png(png_path, samples=128)
    bpy.ops.render.render(write_still=True)
    print(f"  [PNG] {png_path}")

    # save .blend
    blend_path = str(OUT / f"{name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"  [blend] {blend_path}")


# ── combined multi-asset scene + orbit video ───────────────────────────────────

def render_combined_video():
    print(f"\n{'='*60}")
    print(f"  Combined scene orbit video")
    print(f"{'='*60}")

    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()
    add_sky_world(strength=1.1, sun_elev_deg=35)
    add_ground(size=20.0)

    # Grid layout: place assets at evenly spaced X positions
    spacing = 3.0
    assets = []
    for i, (name, FactoryClass, seed, use_fs) in enumerate(ASSETS):
        asset = make_asset(name, FactoryClass, seed, use_fs)
        offset_x = (i - len(ASSETS) / 2 + 0.5) * spacing
        asset.location = (offset_x, 0, 0)
        assets.append(asset)

    bpy.context.view_layer.update()

    # Compute overall bbox centre to aim at
    all_locs = [a.location for a in assets]
    cx = sum(l.x for l in all_locs) / len(all_locs)
    cy = sum(l.y for l in all_locs) / len(all_locs)
    max_z = max(a.dimensions.z for a in assets)

    # Sun light
    bpy.ops.object.light_add(type="SUN", location=(5, -8, 12))
    sun = bpy.context.active_object
    sun.data.energy = 600
    sun.rotation_euler = (math.radians(38), math.radians(18), math.radians(55))

    # Orbit camera around the full group
    total_span = spacing * len(ASSETS)
    cam_dist   = total_span * 0.75
    cam_height = max_z * 1.6 + cam_dist * 0.35

    bpy.ops.object.camera_add(location=(cam_dist, 0, cam_height))
    cam = bpy.context.active_object; cam.name = "OrbitCam"
    bpy.context.scene.camera = cam

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(cx, cy, max_z * 0.4))
    tgt = bpy.context.active_object; tgt.name = "GroupTarget"
    tc  = cam.constraints.new("TRACK_TO")
    tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"

    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("GroupOrbit")
    N = 150
    for f in range(1, N + 1):
        ang = (f - 1) / N * math.tau
        cam.location = (cam_dist * math.cos(ang) + cx,
                        cam_dist * math.sin(ang) + cy,
                        cam_height)
        cam.keyframe_insert("location", frame=f)

    # combined PNG (frame 1)
    bpy.context.scene.frame_set(1)
    png_path = OUT / "grass_combined.png"
    setup_render_png(png_path, samples=96)
    bpy.ops.render.render(write_still=True)
    print(f"  [PNG] {png_path}")

    # orbit video
    video_path = OUT / "grass_orbit"
    setup_render_video(video_path, n_frames=N, samples=64)
    bpy.ops.render.render(animation=True)
    print(f"  [video] {video_path}0001-{N:04d}.mp4")

    # save .blend
    blend_path = str(OUT / "grass_combined.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"  [blend] {blend_path}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    # Render each grass type individually
    for name, FactoryClass, seed, use_fs in ASSETS:
        try:
            render_single(name, FactoryClass, seed, use_fs)
        except Exception as exc:
            import traceback
            print(f"\n[ERROR] {name} failed: {exc}")
            traceback.print_exc()

    # Combined scene + orbit video
    try:
        render_combined_video()
    except Exception as exc:
        import traceback
        print(f"\n[ERROR] combined scene failed: {exc}")
        traceback.print_exc()

    print(f"\n[done] All outputs in {OUT}")


if __name__ == "__main__":
    main()
