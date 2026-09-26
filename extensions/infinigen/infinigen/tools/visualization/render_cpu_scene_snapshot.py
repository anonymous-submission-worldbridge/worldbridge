#!/usr/bin/env python3
"""Render a stable CPU Cycles snapshot for crash-prone preview scenes."""

import argparse
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args():
    parser = argparse.ArgumentParser(description="Render a CPU Cycles scene snapshot.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolution-x", type=int, default=640)
    parser.add_argument("--resolution-y", type=int, default=360)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--no-denoise", action="store_true")
    parser.add_argument("--lens", type=float, default=24)
    parser.add_argument("--name-prefix", default="CyclesSnapshot")
    return parser.parse_args(blender_args())


def load_orbit_module():
    script = Path(__file__).with_name("render_third_person_orbit.py")
    spec = importlib.util.spec_from_file_location("render_third_person_orbit", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_cycles(scene, args):
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    scene.frame_start = 1
    scene.frame_end = 1
    scene.frame_set(1)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.preview_samples = args.samples
    scene.cycles.use_denoising = not args.no_denoise
    scene.cycles.device = "CPU"
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "None"
    except TypeError:
        pass
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    if scene.world is None:
        scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.color = (0.58, 0.64, 0.72)


def setup_preview_lights(scene):
    for obj in list(scene.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)

    sun_data = bpy.data.lights.new("PreviewSun", "SUN")
    sun = bpy.data.objects.new("PreviewSun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (0.85, 0.0, -0.75)
    sun_data.energy = 2.2

    area_data = bpy.data.lights.new("PreviewArea", "AREA")
    area = bpy.data.objects.new("PreviewArea", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (0, -25, 45)
    area_data.energy = 550
    area_data.size = 45


def main():
    args = parse_args()
    scene = bpy.context.scene
    orbit = load_orbit_module()

    setup_cycles(scene, args)
    setup_preview_lights(scene)
    orbit.make_orbit_camera(
        SimpleNamespace(
            name_prefix=args.name_prefix,
            center_x=None,
            center_y=None,
            target_z=None,
            radius=None,
            height=None,
            lens=args.lens,
            frames=1,
        )
    )

    print(f"[snapshot] output: {args.output}")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
