#!/usr/bin/env python3
"""Render a first-person walkthrough MP4 for the currently opened Blender scene."""

import argparse
import json
import os
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector


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
        description="Render a first-person walkthrough video."
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", type=int, default=int(os.getenv("VIDEO_FRAMES", 288)))
    parser.add_argument("--fps", type=int, default=int(os.getenv("VIDEO_FPS", 24)))
    parser.add_argument("--samples", type=int, default=int(os.getenv("VIDEO_SAMPLES", 64)))
    parser.add_argument("--resolution-x", type=int, default=int(os.getenv("VIDEO_RES_X", 1920)))
    parser.add_argument("--resolution-y", type=int, default=int(os.getenv("VIDEO_RES_Y", 1080)))
    parser.add_argument("--engine", default=os.getenv("VIDEO_ENGINE", "CYCLES"))
    parser.add_argument("--eye-height", type=float, default=float(os.getenv("FIRST_PERSON_EYE_HEIGHT", 1.62)))
    parser.add_argument("--lens", type=float, default=float(os.getenv("FIRST_PERSON_LENS", 20)))
    parser.add_argument("--path-json", default=os.getenv("FIRST_PERSON_PATH_JSON"))
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
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.use_motion_blur = False

    if args.engine.upper() == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.preview_samples = min(args.samples, 32)
        scene.cycles.use_denoising = True
        scene.cycles.device = "GPU"
        enable_cycles_gpu()
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    horizontal = Vector((direction.x, direction.y, 0.0))
    if horizontal.length < 1e-6:
        return

    yaw = math.atan2(horizontal.x, -horizontal.y)
    distance = horizontal.length
    pitch = math.atan2(direction.z, distance)

    # First-person view: keep the camera upright and only pan/tilt gently.
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = Euler((math.radians(90.0) - pitch, 0.0, yaw), "XYZ")


def keyframe_pose(camera, frame, loc, target):
    camera.location = loc
    look_at(camera, target)
    camera.keyframe_insert(data_path="location", frame=frame)
    camera.keyframe_insert(data_path="rotation_euler", frame=frame)


def load_waypoints(path):
    data = json.loads(Path(path).read_text())
    waypoints = data["waypoints"] if isinstance(data, dict) else data
    parsed = []
    for item in waypoints:
        if isinstance(item, dict):
            loc = item["location"]
            target = item["target"]
            duration = float(item.get("duration", 1.0))
        else:
            loc, target = item
            duration = 1.0
        parsed.append((Vector(loc), Vector(target), max(duration, 0.05)))
    if len(parsed) < 2:
        raise ValueError("First-person path needs at least two waypoints.")
    return parsed


def auto_waypoints(eye_height):
    mins, maxs = scene_bounds()
    dims = maxs - mins
    z = mins.z + eye_height
    x0, x1 = mins.x, maxs.x
    y0, y1 = mins.y, maxs.y
    cx = (x0 + x1) * 0.5
    cy = (y0 + y1) * 0.5
    width = max(dims.x, 4.0)
    depth = max(dims.y, 4.0)
    outside = max(depth * 0.45, 5.0)
    look_z = z

    points = [
        ((cx, y0 - outside, z), (cx, cy, look_z + 0.4)),
        ((cx, y0 - outside * 0.25, z), (cx, cy, look_z)),
        ((x0 + width * 0.28, y0 + depth * 0.25, z), (x1 - width * 0.20, cy, look_z)),
        ((x1 - width * 0.25, y0 + depth * 0.25, z), (x1 - width * 0.25, y1 - depth * 0.25, look_z)),
        ((x1 - width * 0.25, y1 - depth * 0.30, z), (x0 + width * 0.25, y1 - depth * 0.25, look_z)),
        ((x0 + width * 0.25, y1 - depth * 0.25, z), (cx, cy, look_z)),
        ((cx, cy, z), (cx, y0 - outside, look_z)),
        ((cx, y0 - outside * 0.7, z), (cx, cy, look_z + 0.4)),
    ]
    print(
        "[render] walkthrough auto fit "
        f"bounds=({x0:.2f}, {y0:.2f})..({x1:.2f}, {y1:.2f}) eye_z={z:.2f}"
    )
    return [(Vector(loc), Vector(target), 1.0) for loc, target in points]


def make_walkthrough_camera(args):
    remove_generated_objects(args.name_prefix)
    camera_data = bpy.data.cameras.new(f"{args.name_prefix}_WalkthroughCamera")
    camera = bpy.data.objects.new(f"{args.name_prefix}_WalkthroughCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera_data.lens = args.lens
    camera_data.clip_start = 0.05
    camera_data.clip_end = 10000
    camera_data.dof.use_dof = False

    waypoints = load_waypoints(args.path_json) if args.path_json else auto_waypoints(args.eye_height)

    segment_weights = [duration for _, _, duration in waypoints[1:]]
    total_weight = sum(segment_weights) or 1.0
    cumulative = 0.0
    for idx, (loc, target, _duration) in enumerate(waypoints):
        if idx == 0:
            frame = 1
        else:
            cumulative += segment_weights[idx - 1]
            frame = 1 + round(cumulative * (args.frames - 1) / total_weight)
        keyframe_pose(camera, frame, loc, target)

    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"


def main():
    args = parse_args()
    setup_render(args)
    make_walkthrough_camera(args)
    print(f"[render] first-person walkthrough output: {args.output}")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
