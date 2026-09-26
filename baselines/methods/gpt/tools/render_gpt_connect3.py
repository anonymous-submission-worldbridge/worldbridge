#!/usr/bin/env python3
"""Render independent high-quality stills and traversal videos for connect3."""
from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gpt6_astra/connect3"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def point_camera(camera, location, target, lens):
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens


# The entrance is centered on x=0, with indoor space at positive y and outdoor
# space at negative y.  Every bidirectional view follows the audited clear lane.
VIEWS = {
    "indoor_wide_center": ((0.0, 0.95, 2.05), (0.0, 6.0, 1.25), 25),
    "indoor_left_detail": ((0.75, 2.0, 1.70), (-4.8, 5.4, 1.25), 34),
    "indoor_right_detail": ((-0.75, 2.0, 1.70), (4.8, 5.4, 1.25), 34),
    "indoor_rear_oblique": ((0.0, 8.65, 1.82), (-4.3, 5.2, 1.15), 31),
    "indoor_entry_oblique": ((-1.05, 0.85, 1.72), (4.7, 6.8, 1.18), 29),
    "outdoor_wide_context": ((0.0, -22.0, 7.8), (0.0, -5.0, 1.25), 31),
    "outdoor_facade_left": ((-6.5, -15.0, 3.2), (-1.3, -0.2, 1.55), 34),
    "outdoor_facade_right": ((6.5, -15.0, 3.2), (1.3, -0.2, 1.55), 34),
    "outdoor_left_detail": ((-2.2, -13.8, 2.05), (-4.4, -6.2, 1.10), 39),
    "outdoor_right_detail": ((2.2, -13.8, 2.05), (4.4, -6.2, 1.10), 39),
    "inside_to_outside_far_center": ((0.0, 8.45, 1.74), (3.0, -9.0, 1.05), 31),
    "inside_to_outside_far_left": ((-0.68, 8.20, 1.72), (-3.0, -9.0, 1.15), 31),
    "inside_to_outside_far_right": ((0.68, 8.20, 1.72), (3.0, -9.0, 1.15), 31),
    "inside_to_outside_mid_center": ((0.0, 5.65, 1.70), (-3.0, -8.5, 1.05), 29),
    "inside_to_outside_mid_left": ((-0.70, 5.20, 1.68), (-3.2, -8.0, 1.10), 29),
    "inside_to_outside_mid_right": ((0.70, 5.20, 1.68), (3.2, -8.0, 1.10), 29),
    "inside_to_outside_near_center": ((0.0, 2.35, 1.66), (3.8, -9.0, 1.02), 27),
    "outside_to_inside_far_center": ((0.0, -15.0, 1.72), (0.0, 5.4, 1.18), 31),
    "outside_to_inside_far_left": ((-2.30, -14.0, 1.78), (1.25, 5.6, 1.20), 31),
    "outside_to_inside_far_right": ((2.30, -14.0, 1.78), (-1.25, 5.6, 1.20), 31),
    "outside_to_inside_mid_center": ((0.0, -10.0, 1.69), (0.0, 5.7, 1.18), 29),
    "outside_to_inside_mid_left": ((-1.15, -9.3, 1.69), (1.45, 5.3, 1.16), 29),
    "outside_to_inside_mid_right": ((1.15, -9.3, 1.69), (-1.45, 5.3, 1.16), 29),
    "outside_to_inside_near_center": ((0.0, -4.35, 1.65), (0.0, 6.0, 1.16), 27),
}


def configure_common(scene):
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.dither_intensity = 1.0
    scene.render.image_settings.color_management = "FOLLOW_SCENE"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.20
    scene.view_settings.gamma = 1.0
    scene.render.use_compositing = True
    scene.render.use_sequencer = False


def configure_cycles(scene):
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 32
    scene.eevee.shadow_pool_size = "1024"
    scene.eevee.use_gtao = True
    scene.eevee.gtao_quality = 1.5
    scene.eevee.gtao_distance = 3.0
    scene.eevee.use_fast_gi = True
    backend = "BLENDER_EEVEE_NEXT_GPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        enabled = []
        for device in prefs.devices:
            use = device.type in {"OPTIX", "CUDA"}
            device.use = use
            if use:
                enabled.append(device.name)
        if enabled:
            scene.render.engine = "CYCLES"
            scene.cycles.device = "GPU"
            scene.cycles.samples = 32
            scene.cycles.use_denoising = True
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.04
            scene.cycles.max_bounces = 7
            scene.cycles.diffuse_bounces = 3
            scene.cycles.glossy_bounces = 3
            scene.cycles.transmission_bounces = 5
            scene.cycles.transparent_max_bounces = 5
            scene.cycles.use_light_tree = True
            backend = "CYCLES_OPTIX:" + ",".join(enabled)
    except Exception as error:
        print(f"ASTRA_CONNECT3_GPU_FALLBACK reason={error}", flush=True)
    return backend


def render_stills(scene, camera, image_dir: Path, force: bool, view_names=None):
    records = []
    view_names = view_names or list(VIEWS)
    for name in view_names:
        location, target, lens = VIEWS[name]
        destination = image_dir / f"{name}.png"
        point_camera(camera, location, target, lens)
        if force or not destination.is_file() or destination.stat().st_size < 50_000:
            scene.render.filepath = str(destination)
            print(f"ASTRA_CONNECT3_STILL_START view={name}", flush=True)
            bpy.ops.render.render(write_still=True)
        records.append(
            {
                "file": f"images/{destination.name}",
                "role": name,
                "camera_location_m": list(location),
                "target_m": list(target),
                "lens_mm": lens,
                "sha256": sha256(destination),
                "bytes": destination.stat().st_size,
            }
        )
        print(
            f"ASTRA_CONNECT3_STILL_COMPLETE view={name} bytes={destination.stat().st_size}",
            flush=True,
        )
    return records


def keyframe_camera(camera, frames, locations, targets, lenses):
    camera.animation_data_clear()
    for frame, location, target, lens in zip(frames, locations, targets, lenses):
        point_camera(camera, location, target, lens)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera.data.lens = lens
        camera.data.keyframe_insert(data_path="lens", frame=frame)
    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"


def render_video(scene, camera, video_dir: Path, name: str, forward: bool, force: bool):
    destination = video_dir / f"{name}.mp4"
    if not force and destination.is_file() and destination.stat().st_size > 200_000:
        return {
            "file": f"videos/{destination.name}",
            "role": name,
            "sha256": sha256(destination),
            "bytes": destination.stat().st_size,
            "frames": 48,
            "fps": 12,
            "resolution": [960, 540],
        }
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 4
    scene.eevee.use_fast_gi = False
    scene.eevee.use_gtao = False
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(destination)
    scene.render.fps = 12
    scene.frame_start = 1
    scene.frame_end = 48
    scene.render.image_settings.color_mode = "RGB"
    inside_locations = [
        (0.0, 8.45, 1.72),
        (-0.28, 5.2, 1.68),
        (0.22, 1.8, 1.64),
        (0.0, -4.7, 1.62),
        (0.35, -12.0, 1.70),
    ]
    inside_targets = [
        (0.0, -3.0, 1.10),
        (0.0, -4.2, 1.08),
        (0.0, -6.0, 1.08),
        (0.0, -9.0, 1.10),
        (0.0, -15.0, 1.15),
    ]
    if forward:
        locations, targets = inside_locations, inside_targets
    else:
        locations, targets = list(reversed(inside_locations)), [
            (0.0, -1.8, 1.18),
            (0.0, 1.3, 1.18),
            (0.0, 4.4, 1.18),
            (0.0, 7.2, 1.18),
            (0.0, 9.0, 1.18),
        ]
    keyframe_camera(
        camera, [1, 13, 25, 37, 48], locations, targets, [30, 29, 27, 29, 31]
    )
    print(f"ASTRA_CONNECT3_VIDEO_START video={name}", flush=True)
    bpy.ops.render.render(animation=True)
    if not destination.is_file():
        alternatives = sorted(video_dir.glob(name + "*.mp4"))
        if not alternatives:
            raise RuntimeError(f"video output missing: {destination}")
        alternatives[-1].replace(destination)
    print(
        f"ASTRA_CONNECT3_VIDEO_COMPLETE video={name} bytes={destination.stat().st_size}",
        flush=True,
    )
    return {
        "file": f"videos/{destination.name}",
        "role": name,
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
        "frames": 48,
        "fps": 12,
        "resolution": [960, 540],
    }


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-videos", action="store_true")
    parser.add_argument("--stills-only", action="store_true")
    parser.add_argument(
        "--views", help="comma-separated review subset; does not update manifest"
    )
    parser.add_argument("--update-manifest", action="store_true")
    args = parser.parse_args(arguments)
    root = OUTPUT / args.scene_id
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_path = root / manifest["scene_file"]
    if manifest.get("scene_sha256") != sha256(scene_path):
        raise RuntimeError("scene hash differs from build manifest")
    image_dir, video_dir = root / "images", root / "videos"
    image_dir.mkdir(exist_ok=True)
    video_dir.mkdir(exist_ok=True)
    scene = bpy.context.scene
    camera = scene.camera
    configure_common(scene)
    still_backend = configure_cycles(scene)
    started = utc()
    view_names = args.views.split(",") if args.views else None
    if view_names:
        unknown = sorted(set(view_names) - set(VIEWS))
        if unknown:
            raise ValueError(f"unknown views: {unknown}")
    images = render_stills(scene, camera, image_dir, args.force, view_names)
    if view_names:
        if args.update_manifest:
            merged = {record["role"]: record for record in manifest.get("images", [])}
            merged.update({record["role"]: record for record in images})
            manifest["images"] = [merged[name] for name in VIEWS if name in merged]
            manifest["render_completed_at_utc"] = utc()
            manifest["render_success"] = (
                len(manifest["images"]) == len(VIEWS)
                and len(manifest.get("videos", [])) == 2
            )
            atomic_json(manifest_path, manifest)
        print(
            f"ASTRA_CONNECT3_REVIEW_COMPLETE scene={args.scene_id} images={len(images)}",
            flush=True,
        )
        return
    videos = []
    if not args.stills_only:
        videos.append(
            render_video(
                scene,
                camera,
                video_dir,
                "inside_to_outside",
                True,
                args.force or args.force_videos,
            )
        )
        videos.append(
            render_video(
                scene,
                camera,
                video_dir,
                "outside_to_inside",
                False,
                args.force or args.force_videos,
            )
        )
    elif manifest.get("videos"):
        videos = manifest["videos"]
    manifest.update(
        {
            "render_started_at_utc": started,
            "render_completed_at_utc": utc(),
            "render_success": len(images) == len(VIEWS)
            and (args.stills_only or len(videos) == 2),
            "images": images,
            "videos": videos,
            "render": {
                "resolution": [1280, 720],
                "still_backend": still_backend,
                "still_samples": 32,
                "still_denoising": still_backend.startswith("CYCLES"),
                "video_backend": "BLENDER_EEVEE_NEXT",
                "video_samples": 4,
                "video_resolution": [960, 540],
                "video_frames": 48,
                "video_fps": 12,
                "independent_images": True,
                "montage": False,
                "image_overlays": False,
                "view_count": len(VIEWS),
            },
        }
    )
    atomic_json(manifest_path, manifest)
    print(
        f"ASTRA_CONNECT3_RENDER_COMPLETE scene={args.scene_id} images={len(images)} videos={len(videos)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
