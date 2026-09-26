#!/usr/bin/env python3
"""Render selected, reviewed camera frames as individual publication PNGs.

This script reconstructs the camera paths used by the existing Infinigen preview
videos, then renders only explicitly selected frames.  It is intended to run
inside Blender, for example::

    blender -b scene.blend --python scripts/render_paper_multiview.py -- \
        --mode first_auto --route-frames 288 \
        --shots bedroom_wide:73,bedroom_reverse:85 --output-dir render
"""

import argparse
import importlib.util
import json
import math
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy


ROOT = Path(__file__).resolve().parents[1]
VIS_DIR = ROOT / "infinigen/infinigen/tools/visualization"


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("first_auto", "villa_v5", "orbit"), required=True
    )
    parser.add_argument("--route-frames", type=int, required=True)
    parser.add_argument(
        "--shots", required=True, help="Comma-separated name:frame entries"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resolution-x", type=int, default=1920)
    parser.add_argument("--resolution-y", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument(
        "--engine",
        choices=("CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"),
        default="CYCLES",
    )
    parser.add_argument("--lens", type=float, default=None)
    parser.add_argument("--eye-height", type=float, default=1.62)
    return parser.parse_args(blender_args())


def load_module(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, VIS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_shots(value, route_frames):
    shots = []
    seen = set()
    for entry in value.split(","):
        name, separator, raw_frame = entry.strip().partition(":")
        if not separator or not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError(f"Invalid shot entry: {entry!r}")
        frame = int(raw_frame)
        if frame < 1 or frame > route_frames:
            raise ValueError(f"Frame {frame} outside 1..{route_frames}")
        if name in seen:
            raise ValueError(f"Duplicate shot name: {name}")
        seen.add(name)
        shots.append((name, frame))
    if not shots:
        raise ValueError("At least one shot is required")
    return shots


def configure_cycles_gpu():
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return []
    preferences = addon.preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            preferences.compute_device_type = backend
            preferences.refresh_devices()
            devices = list(preferences.devices)
            gpu_devices = [device for device in devices if device.type != "CPU"]
            if gpu_devices:
                for device in devices:
                    device.use = device.type != "CPU"
                names = [device.name for device in gpu_devices]
                print(
                    f"[paper-render] GPU backend={backend} devices={names}", flush=True
                )
                return names
        except Exception as exc:
            print(f"[paper-render] backend {backend} unavailable: {exc}", flush=True)
    print("[paper-render] no GPU device found; Blender will use CPU", flush=True)
    return []


def configure_render(args, output_dir):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = args.route_frames
    scene.render.fps = 24
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 15
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    scene.render.use_file_extension = True
    requested_engine = args.engine
    if requested_engine.startswith("BLENDER_EEVEE"):
        supported = {
            item.identifier
            for item in scene.render.bl_rna.properties["engine"].enum_items
        }
        requested_engine = (
            "BLENDER_EEVEE_NEXT"
            if "BLENDER_EEVEE_NEXT" in supported
            else "BLENDER_EEVEE"
        )
    scene.render.engine = requested_engine

    gpu_devices = []
    if requested_engine == "CYCLES":
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.device = "GPU"
        if hasattr(scene.render, "use_persistent_data"):
            scene.render.use_persistent_data = True
        gpu_devices = configure_cycles_gpu()

    try:
        scene.view_settings.view_transform = "Filmic"
        scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    output_dir.mkdir(parents=True, exist_ok=True)
    return scene, gpu_devices


def make_first_auto_camera(args):
    module = load_module("render_first_person_walkthrough.py", "paper_first_auto")
    camera_args = SimpleNamespace(
        frames=args.route_frames,
        eye_height=args.eye_height,
        lens=args.lens if args.lens is not None else 20.0,
        name_prefix="PaperAuto",
        path_json=None,
    )
    module.make_walkthrough_camera(camera_args)


def make_orbit_camera(args):
    module = load_module("render_third_person_orbit.py", "paper_orbit")
    camera_args = SimpleNamespace(
        frames=args.route_frames,
        lens=args.lens if args.lens is not None else 24.0,
        name_prefix="PaperOrbit",
        center_x=None,
        center_y=None,
        target_z=None,
        radius=None,
        height=None,
    )
    module.make_orbit_camera(camera_args)


def make_villa_v5_camera(args):
    module = load_module("render_villa_first_person_v5.py", "paper_villa_v5")
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.name.startswith("PaperVillaV5"):
            bpy.data.objects.remove(obj, do_unlink=True)

    camera_data = bpy.data.cameras.new("PaperVillaV5_Camera")
    camera = bpy.data.objects.new("PaperVillaV5_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera_data.lens = args.lens if args.lens is not None else 22.0
    camera_data.clip_start = 0.05
    camera_data.clip_end = 10000

    events = module.route()
    total_duration = sum(event[-1] for event in events)
    frame = 1
    current_yaw = module.yaw(events[0][1], events[0][2])
    for event in events:
        count = max(2, round(event[-1] / total_duration * (args.route_frames - 1)))
        if event[0] == "walk":
            _, point_a, point_b, _ = event
            target_yaw = module.yaw(point_a, point_b)
            yaw_delta = module.delta(current_yaw, target_yaw)
            for index in range(count):
                ratio = index / max(1, count - 1)
                xy = (
                    point_a[0] + (point_b[0] - point_a[0]) * ratio,
                    point_a[1] + (point_b[1] - point_a[1]) * ratio,
                )
                module.pose(
                    camera,
                    frame,
                    xy,
                    current_yaw + yaw_delta * min(1, ratio * 2),
                    args.eye_height,
                )
                frame += 1
            current_yaw = target_yaw
        else:
            _, location, yaw_start, yaw_end, _ = event
            start_delta = module.delta(current_yaw, yaw_start)
            pan_delta = module.delta(yaw_start, yaw_end)
            for index in range(count):
                ratio = index / max(1, count - 1)
                yaw_value = (
                    current_yaw + start_delta * (ratio / 0.2)
                    if ratio < 0.2
                    else yaw_start + pan_delta * ((ratio - 0.2) / 0.8)
                )
                module.pose(camera, frame, location, yaw_value, args.eye_height)
                frame += 1
            current_yaw = yaw_end

    while frame <= args.route_frames:
        module.pose(camera, frame, events[-1][1], current_yaw, args.eye_height)
        frame += 1
    for curve in camera.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"


def main():
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    shots = parse_shots(args.shots, args.route_frames)
    scene, gpu_devices = configure_render(args, output_dir)

    if args.mode == "first_auto":
        make_first_auto_camera(args)
    elif args.mode == "villa_v5":
        make_villa_v5_camera(args)
    else:
        make_orbit_camera(args)

    records = []
    started = time.time()
    for index, (name, frame) in enumerate(shots, start=1):
        output_path = output_dir / f"{name}.png"
        scene.frame_set(frame)
        scene.render.filepath = str(output_path)
        shot_started = time.time()
        print(
            f"[paper-render] shot {index}/{len(shots)} name={name} frame={frame} output={output_path}",
            flush=True,
        )
        bpy.ops.render.render(write_still=True)
        records.append(
            {
                "name": name,
                "frame": frame,
                "file": output_path.name,
                "seconds": round(time.time() - shot_started, 3),
                "bytes": output_path.stat().st_size,
            }
        )

    manifest = {
        "source_blend": bpy.data.filepath,
        "mode": args.mode,
        "route_frames": args.route_frames,
        "resolution": [args.resolution_x, args.resolution_y],
        "engine": scene.render.engine,
        "samples": args.samples,
        "gpu_devices": gpu_devices,
        "shots": records,
        "total_seconds": round(time.time() - started, 3),
    }
    manifest_path = output_dir / f"manifest_{args.mode}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[paper-render] complete manifest={manifest_path}", flush=True)


if __name__ == "__main__":
    main()
