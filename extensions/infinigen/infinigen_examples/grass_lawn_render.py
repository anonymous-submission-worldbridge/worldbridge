#!/usr/bin/env python3
"""
grass_lawn_render.py — render an Infinigen procedural grass lawn (whole-area scatter).

Uses infinigen/assets/scatters/grass.py which distributes GrassTuftFactory instances
over a ground plane with geometry nodes (DistributePointsOnFaces + InstanceOnPoints).

Three outputs:
  1. grass_lawn_side.png   — low camera angle looking across the lawn
  2. grass_lawn_top.png    — overhead view showing coverage uniformity
  3. grass_lawn_orbit.mp4  — 150-frame orbit video
  4. grass_lawn.blend

GPU: OPTIX → CUDA → HIP → METAL  (CPU never used)

Run:
    cd ${WORLDBRIDGE_ROOT}/infinigen
    blender -b --python infinigen_examples/grass_lawn_render.py
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

# ── gin config ─────────────────────────────────────────────────────────────────
import infinigen
from infinigen.core import init

gin.clear_config()
init.apply_gin_configs(
    config_folders=[str(ROOT / "infinigen_examples/configs_nature")],
    configs=[],
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

# ── output ─────────────────────────────────────────────────────────────────────
OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_plants2')
OUT.mkdir(parents=True, exist_ok=True)

# ── imports ────────────────────────────────────────────────────────────────────
from infinigen.assets.scatters import grass as grass_scatter
from infinigen.core.util.math import FixedSeed

# ── helpers ────────────────────────────────────────────────────────────────────

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
                bpy.data.cameras, bpy.data.lights, bpy.data.curves,
                bpy.data.collections):
        for blk in list(col):
            try:
                col.remove(blk)
            except Exception:
                pass


def add_sky_world(sun_elev_deg=25, strength=1.0):
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
    sky.sky_type      = "NISHITA"
    sky.sun_elevation = math.radians(sun_elev_deg)
    sky.sun_rotation  = math.radians(135)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun(energy=600, elev_deg=30, azimuth_deg=135):
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.active_object
    sun.data.energy = energy
    sun.rotation_euler = (
        math.radians(90 - elev_deg),
        0,
        math.radians(azimuth_deg),
    )
    sun.data.angle = math.radians(2.0)
    return sun


def make_ground(size=10.0, subdivisions=8):
    """Create a subdivided ground plane with a soil material."""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "GrassGround"

    # Subdivide for slight undulation later
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=subdivisions)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Soil material (dark loamy earth)
    mat = bpy.data.materials.new("soil")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp  = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")

    # Soil color ramp: dark-brown → medium-brown
    ramp.color_ramp.elements[0].color = (0.038, 0.022, 0.010, 1.0)
    ramp.color_ramp.elements[1].color = (0.072, 0.042, 0.020, 1.0)
    ramp.color_ramp.elements[1].position = 0.6

    noise.inputs["Scale"].default_value  = 8.0
    noise.inputs["Detail"].default_value = 6.0

    mapping.inputs["Scale"].default_value = (3.0, 3.0, 1.0)

    bsdf.inputs["Roughness"].default_value  = 0.95
    bsdf.inputs["Specular IOR Level"].default_value = 0.02 if "Specular IOR Level" in bsdf.inputs else 0

    nt.links.new(coord.outputs["UV"],       mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],      ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],     bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],      out.inputs["Surface"])

    ground.data.materials.append(mat)
    return ground


def apply_grass_scatter(ground, seed=42):
    """Apply Infinigen's grass scatter system to the ground plane."""
    print("[lawn] Applying grass scatter …")
    with FixedSeed(seed):
        scatter_obj, grass_col = grass_scatter.apply(ground)
    print(f"[lawn] Scatter object: {scatter_obj.name}")
    return scatter_obj, grass_col


def setup_render(filepath, samples=96, res_x=1920, res_y=1080, fmt="PNG"):
    sc = bpy.context.scene
    sc.render.engine          = "CYCLES"
    sc.cycles.samples         = samples
    sc.cycles.use_denoising   = True
    enable_optix_denoiser()
    sc.render.resolution_x    = res_x
    sc.render.resolution_y    = res_y
    sc.render.image_settings.file_format = fmt
    sc.render.filepath        = str(filepath)


def setup_video(filepath, n_frames=150, fps=25, samples=64, res_x=1920, res_y=1080):
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end   = n_frames
    sc.render.fps  = fps
    setup_render(filepath, samples, res_x, res_y, "FFMPEG")
    sc.render.ffmpeg.format               = "MPEG4"
    sc.render.ffmpeg.codec                = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"


def add_camera(location, look_at, name="Camera"):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.active_object
    cam.name = name
    bpy.context.scene.camera = cam

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt = bpy.context.active_object
    tgt.name = name + "_target"

    tc = cam.constraints.new("TRACK_TO")
    tc.target     = tgt
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis    = "UP_Y"
    return cam, tgt


def animate_orbit(cam, look_at_loc, radius=8.0, height=3.0, n_frames=150):
    """Keyframe orbit animation for the camera."""
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("LawnOrbit")
    cx, cy, _ = look_at_loc
    for f in range(1, n_frames + 1):
        ang = (f - 1) / n_frames * math.tau
        cam.location = (
            cx + radius * math.cos(ang),
            cy + radius * math.sin(ang),
            height,
        )
        cam.keyframe_insert("location", frame=f)


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()

    LAWN_SIZE = 10.0  # metres

    add_sky_world(sun_elev_deg=28, strength=1.1)
    add_sun(energy=700, elev_deg=28, azimuth_deg=145)

    ground = make_ground(size=LAWN_SIZE, subdivisions=10)
    scatter_obj, grass_col = apply_grass_scatter(ground, seed=7)

    bpy.context.view_layer.update()

    # ── 1. Side view (low angle, looking across the lawn) ──────────────────────
    print("\n[render] Side view PNG …")
    cam_side, tgt_side = add_camera(
        location=(7.0, -1.5, 0.55),
        look_at=(0.0, 0.0, 0.18),
        name="CamSide",
    )
    cam_side.data.lens = 70   # slight telephoto compresses the blades nicely

    setup_render(OUT / "grass_lawn_side.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'grass_lawn_side.png'}")

    # Delete side camera
    bpy.data.objects.remove(cam_side, do_unlink=True)
    bpy.data.objects.remove(tgt_side, do_unlink=True)

    # ── 2. Top-down / overhead view ────────────────────────────────────────────
    print("\n[render] Top-down PNG …")
    cam_top, tgt_top = add_camera(
        location=(0.0, 0.0, 9.5),
        look_at=(0.0, 0.0, 0.0),
        name="CamTop",
    )
    cam_top.data.lens = 28   # wider to show the whole patch

    setup_render(OUT / "grass_lawn_top.png", samples=96)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'grass_lawn_top.png'}")

    bpy.data.objects.remove(cam_top, do_unlink=True)
    bpy.data.objects.remove(tgt_top, do_unlink=True)

    # ── 3. Orbit video ─────────────────────────────────────────────────────────
    print("\n[render] Orbit video …")
    N = 150
    cam_orb, tgt_orb = add_camera(
        location=(8.0, 0.0, 2.8),
        look_at=(0.0, 0.0, 0.3),
        name="CamOrbit",
    )
    cam_orb.data.lens = 50
    animate_orbit(cam_orb, look_at_loc=(0.0, 0.0, 0.3), radius=8.0, height=2.8, n_frames=N)

    setup_video(OUT / "grass_lawn_orbit", n_frames=N, samples=48)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'grass_lawn_orbit0001-0150.mp4'}")

    # ── 4. Save .blend ─────────────────────────────────────────────────────────
    blend_path = str(OUT / "grass_lawn.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"\n[blend] {blend_path}")
    print(f"\n[done] All outputs in {OUT}")


if __name__ == "__main__":
    main()
