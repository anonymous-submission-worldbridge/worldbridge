#!/usr/bin/env python3
"""Build and render one Gemini 3.1 Pro connected indoor/outdoor demo."""
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
import random
import shutil
import subprocess
import sys

import bpy
from mathutils import Vector
import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = (BASELINES / "annotations/gemini_3_1_pro/connect").resolve()
LOWER_LIMITS = (-15.0, -19.0, -1.6)
UPPER_LIMITS = (15.0, 10.0, 9.0)
VIDEO_FRAME_COUNT = 96
VIDEO_DIRECTIONS = ["indoor_to_outdoor", "outdoor_to_indoor"]
sys.path.insert(0, str((BASELINES / "methods")))
from baselines.methods.gemini.adapter_connect import check_code  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def build_scene(run: Path, manifest: dict) -> dict:
    generated = run / "source/generated.py"
    if not generated.is_file() or sha256(generated) != manifest.get(
        "generated_code_sha256"
    ):
        raise RuntimeError("Generated source is missing or changed")
    clear_scene()
    seed = int(manifest["logical_seed"])
    random.seed(seed)
    np.random.seed(seed)
    source = generated.read_text(encoding="utf-8")
    check_code(source)
    namespace = {"__name__": "gemini_connect_scene"}
    exec(compile(source, str(generated), "exec"), namespace)
    namespace["build_scene"](seed)
    bpy.context.view_layer.update()
    meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
    ]
    forbidden = [
        obj.name
        for obj in bpy.context.scene.objects
        if obj.type in {"LIGHT", "CAMERA", "FONT"}
    ]
    if forbidden:
        raise RuntimeError(f"Generated code created forbidden objects: {forbidden}")
    if len(meshes) < 40:
        raise RuntimeError(f"Scene is too sparse: only {len(meshes)} visible meshes")
    vertices = sum(len(obj.data.vertices) for obj in meshes)
    polygons = sum(len(obj.data.polygons) for obj in meshes)
    if vertices < 5000 or polygons < 5000:
        raise RuntimeError(
            f"Scene geometry is too sparse: {vertices} vertices, {polygons} polygons"
        )
    bounds_min = [
        min(
            (obj.matrix_world @ Vector(point))[axis]
            for obj in meshes
            for point in obj.bound_box
        )
        for axis in range(3)
    ]
    bounds_max = [
        max(
            (obj.matrix_world @ Vector(point))[axis]
            for obj in meshes
            for point in obj.bound_box
        )
        for axis in range(3)
    ]
    if any(bounds_min[axis] < LOWER_LIMITS[axis] for axis in range(3)):
        raise RuntimeError(f"Generated geometry exceeds lower bounds: {bounds_min}")
    if any(bounds_max[axis] > UPPER_LIMITS[axis] for axis in range(3)):
        raise RuntimeError(f"Generated geometry exceeds upper bounds: {bounds_max}")
    return {
        "visible_mesh_objects": len(meshes),
        "vertices": vertices,
        "polygons": polygons,
        "bounds_min_xyz_m": bounds_min,
        "bounds_max_xyz_m": bounds_max,
        "is_native_3d_scene": True,
    }


def add_lighting() -> None:
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("ConnectDemoWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.54, 0.67, 0.84, 1.0)
    background.inputs["Strength"].default_value = 0.32

    sun_data = bpy.data.lights.new("ConnectSunData", "SUN")
    sun_data.energy = 2.4
    sun_data.angle = math.radians(10.0)
    sun = bpy.data.objects.new("ConnectSun", sun_data)
    sun.rotation_euler = (math.radians(30.0), math.radians(-20.0), math.radians(-34.0))
    bpy.context.scene.collection.objects.link(sun)

    locations = ((-3.4, 4.4, 3.0), (3.4, 4.4, 3.0), (-3.4, 0.0, 3.0), (3.4, 0.0, 3.0))
    for index, location in enumerate(locations):
        data = bpy.data.lights.new(f"InteriorFillData{index}", "AREA")
        data.energy = 420.0
        data.shape = "DISK"
        data.size = 2.5
        data.color = (1.0, 0.86, 0.72)
        obj = bpy.data.objects.new(f"InteriorFill{index}", data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)


def configure_render(seed: int) -> dict:
    scene = bpy.context.scene
    selected_backend = None
    selected_devices: list[str] = []
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                preferences.compute_device_type = backend
                preferences.get_devices()
            except Exception:
                continue
            devices = [
                device for device in preferences.devices if device.type == backend
            ]
            if not devices:
                continue
            for device in preferences.devices:
                device.use = device.type == backend
            selected_backend = backend
            selected_devices = [device.name for device in devices]
            break
    except Exception:
        selected_backend = None

    if selected_backend:
        scene.render.engine = "CYCLES"
        scene.cycles.device = "GPU"
        scene.cycles.seed = seed
        scene.cycles.use_denoising = True
        try:
            scene.cycles.denoiser = "OPTIX"
        except Exception:
            scene.cycles.denoiser = "OPENIMAGEDENOISE"
        backend = {
            "engine": "CYCLES",
            "device": "GPU",
            "compute_backend": selected_backend,
            "devices": selected_devices,
        }
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        backend = {
            "engine": "BLENDER_EEVEE_NEXT",
            "device": "available Blender graphics device",
            "compute_backend": None,
            "devices": [],
            "fallback_reason": "No CUDA or OptiX Cycles device visible to Blender at render time",
        }
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 35
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    scene.render.fps = 24
    scene.render.use_persistent_data = True
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.25
    scene.view_settings.gamma = 1.0
    return backend


def set_quality(video: bool) -> None:
    scene = bpy.context.scene
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 24 if video else 72
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.10 if video else 0.04
    else:
        scene.eevee.taa_render_samples = 8 if video else 32
        scene.render.image_settings.compression = 45 if video else 35


def make_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("ConnectCameraData")
    data.sensor_width = 36.0
    data.lens = 36.0 / (2.0 * math.tan(math.radians(70.0) / 2.0))
    data.clip_start = 0.05
    data.clip_end = 200.0
    camera = bpy.data.objects.new("ConnectCamera", data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def point_camera(
    camera: bpy.types.Object,
    position: tuple[float, float, float],
    target: tuple[float, float, float],
) -> None:
    camera.location = position
    direction = Vector(target) - Vector(position)
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()


STILL_VIEWS = [
    ((0.0, 5.6, 1.72), (0.0, 0.4, 1.22), "interior_overview"),
    ((-4.7, 3.7, 1.82), (-1.0, 0.8, 1.18), "interior_detail"),
    ((0.0, 0.8, 1.66), (0.0, -8.0, 1.24), "inside_looking_out"),
    ((0.0, -3.15, 1.64), (0.0, -8.8, 1.24), "threshold_from_inside"),
    ((7.6, -12.0, 2.15), (0.0, -7.2, 1.25), "exterior_overview"),
    ((-7.3, -10.8, 1.95), (-2.3, -7.2, 1.12), "outdoor_detail"),
    ((0.0, -8.0, 1.67), (0.0, 1.8, 1.28), "outside_looking_in"),
    ((0.0, -5.85, 1.64), (0.0, 0.7, 1.28), "threshold_from_outside"),
]


def render_stills(run: Path, camera: bpy.types.Object) -> list[dict]:
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    set_quality(video=False)
    images = run / "images"
    images.mkdir(parents=True, exist_ok=True)
    records = []
    for position, target, role in STILL_VIEWS:
        point_camera(camera, position, target)
        path = images / f"{role}.png"
        if path.is_file():
            print(f"GEMINI_CONNECT_STILL_REUSED {run.name} {role}", flush=True)
        else:
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
        records.append(
            {
                "path": str(path.relative_to(run)),
                "role": role,
                "camera_xyz_m": list(position),
                "target_xyz_m": list(target),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "contains_overlay_or_number": False,
            }
        )
        print(f"GEMINI_CONNECT_STILL_COMPLETE {run.name} {role}", flush=True)
    return records


def render_video(run: Path, camera: bpy.types.Object, direction: str) -> dict:
    if direction not in {"indoor_to_outdoor", "outdoor_to_indoor"}:
        raise ValueError(direction)
    scene = bpy.context.scene
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    set_quality(video=True)
    frames_root = run / ".render_frames"
    frames = frames_root / direction
    if frames_root.exists():
        shutil.rmtree(frames_root)
    frames.mkdir(parents=True)
    frame_count = VIDEO_FRAME_COUNT
    try:
        for frame in range(1, frame_count + 1):
            progress = (frame - 1) / (frame_count - 1)
            eased = progress * progress * (3.0 - 2.0 * progress)
            if direction == "indoor_to_outdoor":
                y = 5.4 + (-14.2 - 5.4) * eased
                target_y = y - (3.4 + 0.6 * progress)
            else:
                y = -14.2 + (5.4 + 14.2) * eased
                target_y = y + (3.8 - 0.4 * progress)
            x = 0.14 * math.sin(math.pi * progress)
            z = 1.64 + 0.035 * math.sin(math.pi * progress)
            target_x = 0.24 * math.sin(math.pi * progress)
            point_camera(camera, (x, y, z), (target_x, target_y, 1.27))
            scene.frame_set(frame)
            path = frames / f"frame_{frame:04d}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if frame == 1 or frame % 24 == 0 or frame == frame_count:
                print(
                    f"GEMINI_CONNECT_VIDEO_FRAME {run.name} {direction} {frame}/{frame_count}",
                    flush=True,
                )
        videos = run / "videos"
        videos.mkdir(parents=True, exist_ok=True)
        video = videos / f"{direction}.mp4"
        command = [
            "/usr/bin/ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video),
        ]
        subprocess.run(command, check=True)
        return {
            "path": str(video.relative_to(run)),
            "role": direction,
            "sha256": sha256(video),
            "bytes": video.stat().st_size,
            "resolution": [960, 540],
            "fps": 24,
            "frames": frame_count,
            "duration_seconds": frame_count / 24.0,
            "camera_path": "continuous step-free traversal through the same open shared entrance",
        }
    finally:
        if frames_root.exists():
            shutil.rmtree(frames_root)


def expected_outputs(run: Path) -> list[Path]:
    paths = [run / "images" / f"{role}.png" for _position, _target, role in STILL_VIEWS]
    paths.extend(run / "videos" / f"{direction}.mp4" for direction in VIDEO_DIRECTIONS)
    paths.append(run / f"{run.name}.blend")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--stills-only", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(OUTPUT):
        raise ValueError("Run directory escapes the Gemini connect output root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("generation_success"):
        raise RuntimeError("Scene generation is incomplete")
    expected = expected_outputs(run)
    if manifest.get("render_success") and all(path.is_file() for path in expected):
        hashes = manifest.get("outputs_sha256", {})
        if hashes and all(
            hashes.get(str(path.relative_to(run))) == sha256(path) for path in expected
        ):
            print(f"GEMINI_CONNECT_RENDER_REUSED {run.name}", flush=True)
            return 0
        raise RuntimeError("Existing render output hash mismatch")
    try:
        geometry = build_scene(run, manifest)
        add_lighting()
        backend = configure_render(int(manifest["logical_seed"]))
        camera = make_camera()
        scene_file = run / f"{run.name}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(scene_file), compress=True)
        manifest.update(
            build_success=True,
            build_completed_at_utc=now(),
            scene_file=scene_file.name,
            scene_sha256=sha256(scene_file),
            geometry=geometry,
            render_backend=backend,
        )
        write_json(manifest_path, manifest)
        if args.build_only:
            print(
                f"GEMINI_CONNECT_BUILD_COMPLETE {run.name} backend={json.dumps(backend)}",
                flush=True,
            )
            return 0
        stills = render_stills(run, camera)
        if args.stills_only:
            manifest.update(
                stills_success=True,
                stills_completed_at_utc=now(),
                stills=stills,
            )
            write_json(manifest_path, manifest)
            print(f"GEMINI_CONNECT_STILLS_COMPLETE {run.name}", flush=True)
            return 0
        videos = [
            render_video(run, camera, direction) for direction in VIDEO_DIRECTIONS
        ]
        output_paths = [run / row["path"] for row in stills + videos] + [scene_file]
        manifest.update(
            render_success=True,
            render_completed_at_utc=now(),
            stills=stills,
            videos=videos,
            outputs_sha256={
                str(path.relative_to(run)): sha256(path) for path in output_paths
            },
        )
        manifest.pop("render_failure", None)
        write_json(manifest_path, manifest)
        print(
            f"GEMINI_CONNECT_RENDER_COMPLETE {run.name} backend={json.dumps(backend)}",
            flush=True,
        )
        return 0
    except Exception as error:
        manifest.update(
            render_success=False,
            render_failure=f"{type(error).__name__}: {error}",
            render_failed_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
