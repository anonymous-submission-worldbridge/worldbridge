#!/usr/bin/env python3
"""Render a third-person orbit MP4 for the currently opened Blender scene."""

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PREFERRED_NAME_PARTS = (
    "living-room",
    "dining-room",
    "bedroom",
    "bathroom",
    "kitchen",
    "room_",
    ".wall",
    ".floor",
    ".ceiling",
)
EXCLUDED_NAME_PARTS = ("cloud", "atmosphere", "sky", "sun", "camera", "light")


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render a full-scene third-person orbit video."
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", type=int, default=int(os.getenv("VIDEO_FRAMES", 240)))
    parser.add_argument("--fps", type=int, default=int(os.getenv("VIDEO_FPS", 24)))
    parser.add_argument("--samples", type=int, default=int(os.getenv("VIDEO_SAMPLES", 64)))
    parser.add_argument("--resolution-x", type=int, default=int(os.getenv("VIDEO_RES_X", 1920)))
    parser.add_argument("--resolution-y", type=int, default=int(os.getenv("VIDEO_RES_Y", 1080)))
    parser.add_argument("--engine", default=os.getenv("VIDEO_ENGINE", "CYCLES"))
    parser.add_argument(
        "--output-format",
        choices=["FFMPEG", "PNG"],
        default=os.getenv("VIDEO_OUTPUT_FORMAT", "FFMPEG"),
        help="Use PNG for a frame sequence; it is safer for crash-prone preview renders.",
    )
    parser.add_argument(
        "--hide-collections",
        nargs="*",
        default=os.getenv("VIDEO_HIDE_COLLECTIONS", "").split(),
        help="Hide collections whose name contains any of these tokens, e.g. vegetation.",
    )
    parser.add_argument(
        "--hide-object-name-parts",
        nargs="*",
        default=os.getenv("VIDEO_HIDE_OBJECT_NAME_PARTS", "").split(),
        help="Hide objects whose name contains any of these tokens.",
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        default=os.getenv("VIDEO_SIMPLIFY", "0") == "1",
        help="Enable Blender render simplification for faster preview renders.",
    )
    parser.add_argument("--center-x", type=float, default=None)
    parser.add_argument("--center-y", type=float, default=None)
    parser.add_argument("--target-z", type=float, default=None)
    parser.add_argument("--radius", type=float, default=None)
    parser.add_argument("--height", type=float, default=None)
    parser.add_argument("--lens", type=float, default=float(os.getenv("THIRD_PERSON_LENS", 24)))
    parser.add_argument("--name-prefix", default="GenericVideo")
    return parser.parse_args(blender_args())


def object_bounds(obj):
    if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
        return None
    if not obj.bound_box:
        return None
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    if (maxs - mins).length == 0:
        return None
    return mins, maxs


def scene_bounds():
    objects = [obj for obj in bpy.context.scene.objects if obj.visible_get()]

    def selected_bounds(preferred):
        bounds = []
        for obj in objects:
            name = obj.name.lower()
            if any(part in name for part in EXCLUDED_NAME_PARTS):
                continue
            if preferred and not any(part in name for part in PREFERRED_NAME_PARTS):
                continue
            bound = object_bounds(obj)
            if bound is not None:
                bounds.append(bound)
        return bounds

    bounds = selected_bounds(preferred=True) or selected_bounds(preferred=False)
    if not bounds:
        return Vector((0, 0, 0)), Vector((10, 10, 4))

    mins = Vector(
        (
            min(bound[0].x for bound in bounds),
            min(bound[0].y for bound in bounds),
            min(bound[0].z for bound in bounds),
        )
    )
    maxs = Vector(
        (
            max(bound[1].x for bound in bounds),
            max(bound[1].y for bound in bounds),
            max(bound[1].z for bound in bounds),
        )
    )
    return mins, maxs


def setup_render(args):
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = args.frames
    scene.render.fps = args.fps
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output_path)
    if args.output_format.upper() == "PNG":
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.compression = 20
    else:
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.use_motion_blur = False

    if args.simplify:
        scene.render.use_simplify = True
        simplify_settings = {
            "simplify_subdivision": 0,
            "simplify_child_particles": 0.35,
            "simplify_volumes": 0.25,
            "simplify_texture_limit": "1024",
        }
        for key, value in simplify_settings.items():
            if hasattr(scene.render, key):
                setattr(scene.render, key, value)

    engine = args.engine.upper()
    is_workbench = False
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.preview_samples = min(args.samples, 32)
        scene.cycles.use_denoising = True
        scene.cycles.device = "GPU"
        enable_cycles_gpu()
    elif engine in {"BLENDER_WORKBENCH", "WORKBENCH"}:
        scene.render.engine = "BLENDER_WORKBENCH"
        is_workbench = True
        configure_workbench_preview(scene)
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            if hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = args.samples
            if hasattr(eevee, "taa_samples"):
                eevee.taa_samples = args.samples

    if is_workbench:
        scene.view_settings.view_transform = "Standard"
        try:
            scene.view_settings.look = "None"
        except TypeError:
            scene.view_settings.look = "Medium High Contrast"
    else:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def configure_workbench_preview(scene):
    scene.render.film_transparent = False
    shading = scene.display.shading
    for attr, value in (
        ("light", "STUDIO"),
        ("color_type", "OBJECT"),
        ("background_type", "VIEWPORT"),
    ):
        try:
            setattr(shading, attr, value)
        except TypeError:
            pass
    if hasattr(shading, "background_color"):
        shading.background_color = (0.05, 0.055, 0.06)
    if hasattr(shading, "show_cavity"):
        shading.show_cavity = True

    palette = (
        (0.52, 0.56, 0.60, 1.0),
        (0.42, 0.58, 0.46, 1.0),
        (0.62, 0.54, 0.42, 1.0),
        (0.48, 0.52, 0.66, 1.0),
        (0.66, 0.50, 0.46, 1.0),
    )
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if max(obj.color[:3]) <= 0.01:
            idx = sum(ord(char) for char in obj.name) % len(palette)
            obj.color = palette[idx]


def apply_scene_filters(args):
    hidden_collections = []
    hide_tokens = [token.lower() for token in args.hide_collections if token]
    if hide_tokens:
        for collection in bpy.data.collections:
            name = collection.name.lower()
            if any(token in name for token in hide_tokens):
                collection.hide_viewport = True
                collection.hide_render = True
                hidden_collections.append(collection.name)
    if hidden_collections:
        print("[render] hidden collections: " + ", ".join(sorted(hidden_collections)))

    object_tokens = [token.lower() for token in args.hide_object_name_parts if token]
    if object_tokens:
        hidden_objects = []
        for obj in bpy.context.scene.objects:
            name = obj.name.lower()
            if any(token in name for token in object_tokens):
                obj.hide_viewport = True
                obj.hide_render = True
                hidden_objects.append(obj.name)
        print(f"[render] hidden objects by name: {len(hidden_objects)}")


def enable_cycles_gpu():
    prefs = bpy.context.preferences.addons.get("cycles")
    if not prefs:
        return
    cprefs = prefs.preferences
    for device_type in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            cprefs.compute_device_type = device_type
            cprefs.refresh_devices()
            devices = list(cprefs.devices)
            gpu_devices = [device for device in devices if device.type != "CPU"]
            if gpu_devices:
                for device in devices:
                    device.use = device.type != "CPU"
                print(f"[render] Cycles GPU backend: {device_type}")
                for device in gpu_devices:
                    print(f"[render] enabled device: {device.name}")
                return
        except Exception as exc:
            print(f"[render] GPU backend {device_type} unavailable: {exc}")
    print("[render] No Cycles GPU device found; Blender will fall back to CPU.")


def remove_generated_objects(prefix):
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith(prefix):
            bpy.data.objects.remove(obj, do_unlink=True)


def make_orbit_camera(args):
    remove_generated_objects(args.name_prefix)
    mins, maxs = scene_bounds()
    center = (mins + maxs) * 0.5
    dims = maxs - mins

    target = bpy.data.objects.new(f"{args.name_prefix}_OrbitTarget", None)
    target.location = (
        args.center_x if args.center_x is not None else center.x,
        args.center_y if args.center_y is not None else center.y,
        args.target_z if args.target_z is not None else mins.z + max(dims.z * 0.45, 1.5),
    )
    bpy.context.collection.objects.link(target)

    radius = args.radius if args.radius is not None else max(dims.x, dims.y, 8.0) * 1.45
    height = args.height if args.height is not None else maxs.z + max(dims.z * 0.25, 3.0)

    camera_data = bpy.data.cameras.new(f"{args.name_prefix}_OrbitCamera")
    camera = bpy.data.objects.new(f"{args.name_prefix}_OrbitCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera_data.lens = args.lens
    camera_data.clip_end = 10000
    camera_data.dof.use_dof = False

    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    constraint.target = target

    cx, cy = target.location.x, target.location.y
    for frame in range(1, args.frames + 1):
        t = (frame - 1) / max(args.frames - 1, 1)
        angle = math.radians(360.0 * t - 35.0)
        z = height + math.sin(2.0 * math.pi * t) * max(dims.z * 0.06, 0.6)
        camera.location = (
            cx + math.cos(angle) * radius,
            cy + math.sin(angle) * radius,
            z,
        )
        camera.keyframe_insert(data_path="location", frame=frame)

    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"

    print(
        "[render] orbit fit "
        f"center=({target.location.x:.2f}, {target.location.y:.2f}, {target.location.z:.2f}) "
        f"radius={radius:.2f} height={height:.2f}"
    )


def main():
    args = parse_args()
    apply_scene_filters(args)
    setup_render(args)
    make_orbit_camera(args)
    print(f"[render] third-person orbit output: {args.output}")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
