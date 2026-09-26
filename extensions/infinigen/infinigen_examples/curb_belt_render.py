#!/usr/bin/env python3
"""
curb_belt_render.py — procedural urban roadside green belt (roadside green belt).

Assembles a 15 m × 1.2 m curb planting strip from Infinigen building blocks:
  • Grass scatter  (Grass.apply  → GrassTuftFactory instances via geometry nodes)
  • Shrubs         (UrbanGroundcoverFactory.create_shrub  → BushFactory or fallback mesh)
  • Flower plants  (UrbanGroundcoverFactory.create_flowerplant → FlowerPlantFactory)
  • Concrete curb edge + asphalt road
  • Nishita sky, sun lamp, subtle HDRI ambient

Outputs (→ ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt/):
  belt_side.png      — street-level side view looking across the belt
  belt_end.png       — end-perspective looking down the strip
  belt_top.png       — overhead plan view
  belt_orbit0001-0150.mp4
  belt.blend

GPU: OPTIX → CUDA → HIP → METAL (never CPU)

Run:
    cd ${WORLDBRIDGE_ROOT}/infinigen
    blender -b --python infinigen_examples/curb_belt_render.py
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

# ── gin ────────────────────────────────────────────────────────────────────────
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
OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt')
OUT.mkdir(parents=True, exist_ok=True)

# ── imports ────────────────────────────────────────────────────────────────────
from infinigen.assets.objects.grassland.urban_groundcover import UrbanGroundcoverFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest
from infinigen.assets.scatters.grass import Grass
from infinigen.core.util.math import FixedSeed

# ── belt geometry constants ────────────────────────────────────────────────────
BELT_LEN   = 15.0   # metres, along X
BELT_WIDTH = 1.2    # metres, along Y  (road side = y=0, sidewalk side = y=1.2)
CURB_H     = 0.14   # concrete curb height above road
CURB_W     = 0.15   # curb width
ROAD_W     = 8.0    # asphalt slab to the side

# ── helpers ────────────────────────────────────────────────────────────────────

def enable_optix_denoiser():
    for d in ("OPTIX", "OPENIMAGEDENOISE"):
        try:
            bpy.context.scene.cycles.denoiser = d
            return
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


def make_mat(name, color, roughness=0.9, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value   = roughness
        bsdf.inputs["Metallic"].default_value    = metallic
    return mat


def make_noisy_mat(name, color_a, color_b, roughness=0.9, scale=6.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp  = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mp    = nt.nodes.new("ShaderNodeMapping")
    noise.inputs["Scale"].default_value  = scale
    noise.inputs["Detail"].default_value = 6.0
    mp.inputs["Scale"].default_value = (2.0, 2.0, 1.0)
    ramp.color_ramp.elements[0].color = color_a
    ramp.color_ramp.elements[1].color = color_b
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(coord.outputs["UV"],    mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"],   noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],   ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],  bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],   out.inputs["Surface"])
    return mat


def add_sky_world(sun_elev_deg=30, sun_rot_deg=155, strength=1.05):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type      = "NISHITA"
    sky.sun_elevation = math.radians(sun_elev_deg)
    sky.sun_rotation  = math.radians(sun_rot_deg)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun(energy=550, elev_deg=35, azimuth_deg=155):
    bpy.ops.object.light_add(type="SUN", location=(5, -5, 15))
    sun = bpy.context.active_object
    sun.data.energy    = energy
    sun.data.angle     = math.radians(1.8)
    sun.rotation_euler = (math.radians(90 - elev_deg), 0, math.radians(azimuth_deg))
    return sun


def add_camera(loc, look_at, name="Camera", lens=50):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.lens = lens
    bpy.context.scene.camera = cam
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt = bpy.context.active_object; tgt.name = name + "_tgt"
    tc = cam.constraints.new("TRACK_TO")
    tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
    return cam, tgt


def setup_render_png(fp, samples=128, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.cycles.samples         = samples
    sc.cycles.use_denoising   = True
    enable_optix_denoiser()
    sc.render.resolution_x    = rx
    sc.render.resolution_y    = ry
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath        = str(fp)


def setup_render_video(fp, n=150, fps=25, samples=48, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.frame_start = 1; sc.frame_end = n; sc.render.fps = fps
    setup_render_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format  = "FFMPEG"
    sc.render.ffmpeg.format               = "MPEG4"
    sc.render.ffmpeg.codec                = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"


def animate_orbit(cam, cx, cy, cz_look, radius, height, n=150):
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("BeltOrbit")
    for f in range(1, n + 1):
        ang = (f - 1) / n * math.tau
        cam.location = (cx + radius * math.cos(ang),
                        cy + radius * math.sin(ang),
                        height)
        cam.keyframe_insert("location", frame=f)


# ── geometry builders ──────────────────────────────────────────────────────────

def build_belt_ground(soil_mat):
    """15 m × 1.2 m soil strip, subdivided for grass scatter."""
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(BELT_LEN / 2, BELT_WIDTH / 2, 0))
    g = bpy.context.active_object; g.name = "BeltGround"
    g.scale = (BELT_LEN, BELT_WIDTH, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    # Subdivide to give geometry nodes density something to work with
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=8)
    bpy.ops.object.mode_set(mode="OBJECT")
    g.data.materials.append(soil_mat)
    return g


def build_curb(curb_mat):
    """Raised concrete kerb strip along road side (y=0 edge)."""
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(BELT_LEN / 2, -CURB_W / 2, CURB_H / 2 - 0.04)
    )
    c = bpy.context.active_object; c.name = "Curb"
    c.scale = (BELT_LEN, CURB_W, CURB_H)
    bpy.ops.object.transform_apply(scale=True)
    c.data.materials.append(curb_mat)
    return c


def build_road(asphalt_mat):
    """Asphalt slab on the road side of the curb."""
    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(BELT_LEN / 2, -(CURB_W + ROAD_W / 2), -0.04)
    )
    r = bpy.context.active_object; r.name = "Road"
    r.scale = (BELT_LEN + 4, ROAD_W, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    r.data.materials.append(asphalt_mat)
    return r


def build_sidewalk(pavement_mat):
    """Pavement slab on the far side of the belt."""
    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(BELT_LEN / 2, BELT_WIDTH + ROAD_W / 2, -0.01)
    )
    s = bpy.context.active_object; s.name = "Sidewalk"
    s.scale = (BELT_LEN + 4, ROAD_W, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    s.data.materials.append(pavement_mat)
    return s


# ── plant placement ────────────────────────────────────────────────────────────

def make_urban_mats():
    """Minimal material dict for UrbanGroundcoverFactory fallback meshes."""
    return {
        "trunk":        make_mat("trunk",       (0.12, 0.08, 0.04, 1.0), roughness=0.88),
        "shrub":        make_mat("shrub",       (0.04, 0.14, 0.03, 1.0), roughness=0.92),
        "leaf_dark":    make_mat("leaf_dark",   (0.02, 0.09, 0.02, 1.0), roughness=0.90),
        "grass_tuft":   make_mat("grass_tuft",  (0.07, 0.20, 0.04, 1.0), roughness=0.95),
        "flower_yellow":make_mat("flower_yellow",(0.82, 0.72, 0.08, 1.0), roughness=0.75),
        "lamp":         make_mat("lamp",        (0.90, 0.88, 0.80, 1.0), roughness=0.5),
        "leaf_litter":  make_mat("leaf_litter", (0.18, 0.12, 0.04, 1.0), roughness=0.95),
    }


def place_shrubs(factory: UrbanGroundcoverFactory):
    """Place 5 shrubs evenly along the belt centre line."""
    print("[belt] Placing shrubs …")
    positions = np.linspace(1.5, BELT_LEN - 1.5, 5)
    all_objs = []
    for i, x in enumerate(positions):
        y = BELT_WIDTH * (0.35 + 0.3 * (i % 2))   # alternate front/back
        req = UrbanAssetRequest(
            asset_type="shrub",
            location=(x, y, 0.0),
            semantic="shrub",
            yaw=i * 1.15,
            params={
                "id": str(i),
                "scale": 0.55 + 0.08 * (i % 3),
                "n_leaf": 3,
                "n_twig": 2,
                "use_nature_factory": True,
                "max_faces": 25000,
            },
        )
        try:
            objs, meta = factory.create_shrub(req)
            all_objs.extend(objs)
            print(f"  shrub {i}: {meta.get('type')} at ({x:.1f}, {y:.2f})")
        except Exception as e:
            print(f"  shrub {i} FAILED: {e}")
    return all_objs


def place_flowerplants(factory: UrbanGroundcoverFactory):
    """Place 6 flower plants between shrubs."""
    print("[belt] Placing flower plants …")
    positions = np.linspace(0.8, BELT_LEN - 0.8, 6)
    all_objs = []
    for i, x in enumerate(positions):
        y = BELT_WIDTH * (0.6 + 0.25 * math.sin(i * 1.9))
        req = UrbanAssetRequest(
            asset_type="flowerplant",
            location=(x, y, 0.0),
            semantic="flowerplant",
            yaw=i * 0.85,
            params={
                "id": str(20 + i),
                "scale": 0.75 + 0.15 * (i % 3),
                "max_faces": 10000,
            },
        )
        try:
            objs, meta = factory.create_flowerplant(req)
            all_objs.extend(objs)
            print(f"  flower {i}: {meta.get('type')} at ({x:.1f}, {y:.2f})")
        except Exception as e:
            print(f"  flower {i} FAILED: {e}")
    return all_objs


def place_grass_scatter(belt_ground):
    """Dense grass scatter over the soil strip."""
    print("[belt] Applying grass scatter …")
    with FixedSeed(42):
        scatter_obj, grass_col = Grass().apply(belt_ground)
    print(f"  scatter object: {scatter_obj.name}")
    return scatter_obj, grass_col


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()

    print("[belt] Building materials …")
    soil_mat     = make_noisy_mat("soil",     (0.032,0.018,0.008,1.0), (0.065,0.038,0.016,1.0), scale=8.0)
    curb_mat     = make_noisy_mat("concrete", (0.55,0.54,0.52,1.0),   (0.48,0.47,0.45,1.0), roughness=0.85, scale=12.0)
    asphalt_mat  = make_noisy_mat("asphalt",  (0.028,0.028,0.030,1.0),(0.040,0.040,0.042,1.0), roughness=0.92, scale=5.0)
    pavement_mat = make_noisy_mat("pavement", (0.50,0.49,0.47,1.0),   (0.42,0.41,0.40,1.0), roughness=0.86, scale=10.0)
    urban_mats   = make_urban_mats()

    print("[belt] Building geometry …")
    belt_ground = build_belt_ground(soil_mat)
    build_curb(curb_mat)
    build_road(asphalt_mat)
    build_sidewalk(pavement_mat)

    add_sky_world(sun_elev_deg=32, sun_rot_deg=150, strength=1.1)
    add_sun(energy=580, elev_deg=32, azimuth_deg=150)

    # ── plants ─────────────────────────────────────────────────────────────────
    factory = UrbanGroundcoverFactory(urban_mats)

    scatter_obj, grass_col = place_grass_scatter(belt_ground)
    shrub_objs    = place_shrubs(factory)
    flower_objs   = place_flowerplants(factory)

    bpy.context.view_layer.update()

    # belt centre for camera targeting
    cx = BELT_LEN / 2          # 7.5
    cy = BELT_WIDTH / 2        # 0.6
    cz = 0.5                   # roughly mid-plant height

    # ── 1. Side view: from road, looking across belt ────────────────────────────
    print("\n[render] Side view …")
    cam, tgt = add_camera(
        loc=(cx, -5.5, 1.4),
        look_at=(cx, cy, cz * 0.7),
        name="CamSide",
        lens=65,
    )
    setup_render_png(OUT / "belt_side.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt_side.png'}")
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

    # ── 2. End perspective: looking down the length of the strip ───────────────
    print("\n[render] End perspective …")
    cam, tgt = add_camera(
        loc=(-3.5, cy, 1.6),
        look_at=(cx, cy, cz * 0.5),
        name="CamEnd",
        lens=50,
    )
    setup_render_png(OUT / "belt_end.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt_end.png'}")
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

    # ── 3. Top-down plan view ──────────────────────────────────────────────────
    print("\n[render] Top-down view …")
    cam, tgt = add_camera(
        loc=(cx, cy, 10.0),
        look_at=(cx, cy, 0.0),
        name="CamTop",
        lens=35,
    )
    setup_render_png(OUT / "belt_top.png", samples=96)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt_top.png'}")
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

    # ── 4. Orbit video ─────────────────────────────────────────────────────────
    print("\n[render] Orbit video …")
    N = 150
    cam, tgt = add_camera(
        loc=(cx + 10.0, cy, 3.5),
        look_at=(cx, cy, cz * 0.6),
        name="CamOrbit",
        lens=55,
    )
    animate_orbit(cam, cx, cy, cz * 0.6, radius=10.0, height=3.5, n=N)
    setup_render_video(OUT / "belt_orbit", n=N, samples=48)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'belt_orbit0001-0150.mp4'}")
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

    # ── 5. Save .blend ─────────────────────────────────────────────────────────
    blend_path = str(OUT / "belt.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"\n[blend] {blend_path}")
    print(f"[done] All outputs in {OUT}")


if __name__ == "__main__":
    main()
