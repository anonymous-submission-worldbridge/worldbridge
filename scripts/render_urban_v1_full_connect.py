"""Cycles/OptiX stills and real camera animation for the six connected scenes."""
from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"


def pose(scene, position, target, lens):
    camera = scene.camera
    camera.location = position
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    scene.view_layers.update()


def configure(scene, width, samples):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    selected = []
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            selected.append(device.name)
    if not selected:
        raise RuntimeError("GPU required; no OptiX device exposed")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoising_use_gpu = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    scene.render.use_persistent_data = True
    scene.render.resolution_x = width
    scene.render.resolution_y = width * 9 // 16
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 30
    scene.render.use_file_extension = True
    return selected


def animation_pose(m, name, t):
    """Smooth physical camera moves, including both directions through the door."""
    shot = m["shots"][name]
    p = Vector(shot["position"])
    target = Vector(shot["target"])
    u = t * t * (3 - 2 * t)
    x = m["door_x"]
    y = m["front_y"]
    if name == "outside_to_inside":
        p = Vector((x, y - 2.1 + 3.4 * u, 1.8))
        # Look along the unobstructed portal while traversing, then into the room.
        target = Vector((x + (shot["target"][0] - x) * 0.38 * u, y + 4, 1.65))
        lens = 23
    elif name == "inside_to_outside":
        p = Vector((x, y + 1.35 - 3.5 * u, 1.8))
        target = Vector((x, y - 8, 1.4))
        lens = 23
    elif name == "exterior":
        p.x += 1.2 * (u - 0.5)
        lens = shot["lens"]
    else:
        # A small nodal pan preserves a verified camera position in dense interiors.
        target.x += 1.2 * (u - 0.5)
        lens = shot["lens"]
    return p, target, lens


def main(args):
    dest = OUT / args.scene
    manifest = json.loads((dest / "scene_manifest.json").read_text())
    bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
    scene = bpy.context.scene
    devices = configure(scene, args.width, args.samples)
    shots = manifest["shots"]
    selected = args.shots.split(",") if args.shots else list(shots)
    image_dir = dest / ("previews" if args.mode == "preview" else "images")
    image_dir.mkdir(exist_ok=True)
    report = {
        "scene": args.scene,
        "mode": args.mode,
        "devices": devices,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "width": args.width,
        "samples": args.samples,
        "renders": [],
    }
    if args.mode != "video":
        for name in selected:
            target = image_dir / (name + ".png")
            if target.exists() and not args.overwrite:
                continue
            pose(scene, **shots[name])
            scene.render.filepath = str(target)
            start = time.monotonic()
            bpy.ops.render.render(write_still=True)
            report["renders"].append(
                {"file": str(target), "seconds": round(time.monotonic() - start, 2)}
            )
            (dest / (args.mode + "_render_manifest.json")).write_text(
                json.dumps(report, indent=2)
            )
            print("CONNECT_STILL " + str(target), flush=True)
    else:
        video_dir = dest / "videos"
        video_dir.mkdir(exist_ok=True)
        frame_dir = dest / ".video_frames"
        frame_dir.mkdir(exist_ok=True)
        selected = (
            args.shots.split(",")
            if args.shots
            else ["interior", "exterior", "inside_to_outside", "outside_to_inside"]
        )
        scene.render.fps = 24
        for name in selected:
            target = video_dir / (name + ".mp4")
            if target.exists() and not args.overwrite:
                continue
            count = args.frames
            for i in range(count):
                frame = frame_dir / (name + f"_{i:04d}.png")
                if frame.exists() and not args.overwrite:
                    continue
                p, look, lens = animation_pose(manifest, name, i / (count - 1))
                pose(scene, p, look, lens)
                scene.render.filepath = str(frame)
                bpy.ops.render.render(write_still=True)
                print(f"CONNECT_FRAME {name} {i+1}/{count}", flush=True)
            temp = video_dir / (name + ".partial.mp4")
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-framerate",
                    "24",
                    "-i",
                    str(frame_dir / (name + "_%04d.png")),
                    "-frames:v",
                    str(count),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(temp),
                ],
                check=True,
            )
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(temp), "-f", "null", "-"],
                check=True,
            )
            temp.replace(target)
            # Remove only frames produced here, after complete video decode succeeds.
            for frame in frame_dir.glob(name + "_*.png"):
                frame.unlink()
            report["renders"].append(
                {
                    "file": str(target),
                    "frames": count,
                    "fps": 24,
                    "duration_seconds": count / 24,
                }
            )
            (dest / "video_render_manifest.json").write_text(
                json.dumps(report, indent=2)
            )
            print("CONNECT_VIDEO " + str(target), flush=True)
        if not any(frame_dir.iterdir()):
            frame_dir.rmdir()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scene", required=True)
    p.add_argument("--mode", choices=["preview", "final", "video"], default="preview")
    p.add_argument("--width", type=int, default=768)
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--shots", default="")
    p.add_argument("--frames", type=int, default=72)
    p.add_argument("--overwrite", action="store_true")
    main(p.parse_args(sys.argv[sys.argv.index("--") + 1 :]))
