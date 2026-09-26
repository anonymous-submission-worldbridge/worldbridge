#!/usr/bin/env python
"""Create a dense procedural flower bed using Infinigen's native flower assets.

Builds a soil ground patch, scatters Infinigen `FlowerPlantFactory` plants (complex
procedural flowers: phyllotaxis petals, seeded centers, stems, branches, leaves) plus
grass tufts over it, lights it with a Nishita sky, and renders:
    - urban_v3_flower.blend  (editable scene)
    - urban_v3_flower.png    (high-quality still)
    - urban_v3_flower.mp4    (turntable animation)

Run from the infinigen repo root inside the `infinigen` conda env:
    python ../tools/render_flower_bed.py
"""

import math
import time
from pathlib import Path

import bpy
import gin
import numpy as np
from mathutils import Euler, Vector

from infinigen.assets.lighting import sky_lighting
from infinigen.assets.materials.terrain.mud import Mud
from infinigen.assets.scatters import flowerplant, grass
from infinigen.core import init
from infinigen.core.placement import density
from infinigen.core.util import blender as butil

# ------------------------------------------------------------------ config
SEED = 42
BED_SIZE = 10.0  # metres (square ground patch)
SUBDIV = 200  # ground subdivisions per axis (for scatter density)
OUT_DIR = Path("outputs/urban_v3_flower")
NAME = "urban_v3_flower"

STILL_RES = (1920, 1080)
STILL_SAMPLES = 256
VIDEO_RES = (1280, 720)
VIDEO_SAMPLES = 48
VIDEO_FRAMES = 96  # 96 frames @ 24fps = 4s turntable
FPS = 24

FLOWER_DENSITY = 1.0  # gets divided by avg plant volume + clamped to <=200/m^2
GRASS_DENSITY = 12.0


def make_colorful():
    """Widen Infinigen's petal palette so the bed reads as a multi-colour flower bed
    (like a tulip garden) instead of the default red/pink-only range."""
    from infinigen.assets import colors

    def petal_hsv():
        return (
            float(np.random.uniform(0.0, 1.0)),  # full hue wheel
            float(np.random.uniform(0.65, 0.95)),  # vivid saturation
            float(np.random.uniform(0.5, 0.85)),  # bright value
        )

    colors.petal_hsv = petal_hsv


def clean_scene():
    butil.clear_scene()


def build_ground():
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=SUBDIV,
        y_subdivisions=SUBDIV,
        size=BED_SIZE,
        location=(0, 0, 0),
    )
    ground = bpy.context.active_object
    ground.name = "flower_bed_ground"
    Mud().apply(ground)
    return ground


def scatter_plants(ground):
    all_objs = [ground]

    # Grass understory across the whole patch.
    grass_sel = density.placement_mask(
        normal_dir=(0, 0, 1), scale=3, return_scalar=True, select_thresh=0.0
    )
    gobj, _ = grass.apply(ground, selection=grass_sel, density=GRASS_DENSITY)
    all_objs.append(gobj)

    # Dense flower bed on top.
    fobj, _ = flowerplant.apply(ground, selection=None, density=FLOWER_DENSITY)
    all_objs.append(fobj)

    return all_objs


def setup_camera():
    cam_data = bpy.data.cameras.new("FlowerCam")
    cam_data.lens = 35
    cam = bpy.data.objects.new("FlowerCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)

    # Low, angled view so we look across the sea of flowers with sky above.
    cam.location = Vector((0.0, -6.5, 2.2))
    target = Vector((0.0, 0.5, 0.35))
    direction = (target - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bpy.context.scene.camera = cam
    return cam


def setup_turntable(cam, frames):
    """Parent the camera to a pivot empty and spin it a full turn."""
    pivot = bpy.data.objects.new("Turntable", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = Vector((0.0, 0.0, 0.4))

    cam_world = cam.matrix_world.copy()
    cam.parent = pivot
    cam.matrix_world = cam_world

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    # keyframes: start at 0, end at 2pi -> one full revolution
    pivot.rotation_euler = Euler((0, 0, 0), "XYZ")
    pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = Euler((0, 0, 2 * math.pi), "XYZ")
    pivot.keyframe_insert("rotation_euler", frame=frames)
    for fc in pivot.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    return pivot


def configure_render(res, samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    init.configure_cycles_devices(use_gpu=True)  # OPTIX -> CUDA -> ... preference


def render_still(path):
    configure_render(STILL_RES, STILL_SAMPLES)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_video(path, frames):
    configure_render(VIDEO_RES, VIDEO_SAMPLES)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.filepath = str(path)
    bpy.ops.render.render(animation=True)


def main():
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # gin defaults for @gin.configurable helpers (placement_mask, nishita_lighting).
    gin.clear_config()
    gin.enter_interactive_mode()

    np.random.seed(SEED)
    make_colorful()

    clean_scene()
    ground = build_ground()
    print(f"[flower] ground built @ {time.time()-t0:.1f}s")
    scatter_plants(ground)
    print(f"[flower] scattered flowers+grass @ {time.time()-t0:.1f}s")

    sky_lighting.add_lighting()
    cam = setup_camera()

    # Save the editable .blend before rendering.
    blend_path = OUT_DIR / f"{NAME}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path.resolve()))
    print(f"[flower] saved {blend_path} @ {time.time()-t0:.1f}s")

    # Still image.
    png_path = OUT_DIR / f"{NAME}.png"
    render_still(png_path)
    print(f"[flower] rendered {png_path} @ {time.time()-t0:.1f}s")

    # Turntable video.
    setup_turntable(cam, VIDEO_FRAMES)
    mp4_path = OUT_DIR / f"{NAME}.mp4"
    render_video(mp4_path, VIDEO_FRAMES)
    print(f"[flower] rendered {mp4_path} @ {time.time()-t0:.1f}s")

    print(f"[flower] DONE in {time.time()-t0:.1f}s -> {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
