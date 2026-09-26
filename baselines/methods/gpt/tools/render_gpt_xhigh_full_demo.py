"""Build and GPU-render one connected indoor/outdoor GPT-6 Astra xhigh demo."""
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
sys.path.insert(0, str((BASELINES / "methods")))
from baselines.methods.gpt.adapter import check_code  # noqa: E402


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
    namespace = {"__name__": "astra_full_demo_scene"}
    exec(compile(source, str(generated), "exec"), namespace)
    namespace["build_scene"](seed)
    bpy.context.view_layer.update()
    meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
    ]
    forbidden = [
        obj.name for obj in bpy.context.scene.objects if obj.type in {"LIGHT", "CAMERA"}
    ]
    if not meshes:
        raise RuntimeError("Generated scene has no visible mesh geometry")
    if forbidden:
        raise RuntimeError(
            f"Generated code created forbidden camera/light objects: {forbidden}"
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
    if any(bounds_min[axis] < limit for axis, limit in enumerate((-15.0, -19.0, -1.0))):
        raise RuntimeError(
            f"Generated geometry exceeds lower demo bounds: {bounds_min}"
        )
    if any(bounds_max[axis] > limit for axis, limit in enumerate((15.0, 10.0, 9.0))):
        raise RuntimeError(
            f"Generated geometry exceeds upper demo bounds: {bounds_max}"
        )
    return {
        "visible_mesh_objects": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "polygons": sum(len(obj.data.polygons) for obj in meshes),
        "bounds_min_xyz_m": bounds_min,
        "bounds_max_xyz_m": bounds_max,
    }


def add_lighting() -> None:
    world = bpy.data.worlds.new("FullDemoWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.58, 0.68, 0.82, 1.0)
    background.inputs["Strength"].default_value = 0.28

    sun_data = bpy.data.lights.new("FullDemoSunData", "SUN")
    sun_data.energy = 2.6
    sun_data.angle = math.radians(12.0)
    sun = bpy.data.objects.new("FullDemoSun", sun_data)
    sun.rotation_euler = (math.radians(28.0), math.radians(-18.0), math.radians(-32.0))
    bpy.context.scene.collection.objects.link(sun)

    for index, (x, y, energy, size) in enumerate(
        (
            (-3.0, 3.8, 520.0, 3.0),
            (3.0, 3.8, 520.0, 3.0),
            (-3.0, -0.2, 440.0, 2.5),
            (3.0, -0.2, 440.0, 2.5),
        )
    ):
        data = bpy.data.lights.new(f"InteriorFillData{index:02d}", "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = (1.0, 0.86, 0.70)
        obj = bpy.data.objects.new(f"InteriorFill{index:02d}", data)
        obj.location = (x, y, 3.05)
        bpy.context.scene.collection.objects.link(obj)


def configure_cycles(seed: int) -> str:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.seed = seed
    scene.cycles.use_denoising = True
    preferences = bpy.context.preferences.addons["cycles"].preferences
    selected = None
    selected_devices: list[str] = []
    for backend in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
        except Exception:
            continue
        devices = [device for device in preferences.devices if device.type == backend]
        if not devices:
            continue
        for device in preferences.devices:
            device.use = device.type == backend
        selected = backend
        selected_devices = [device.name for device in devices if device.use]
        break
    if selected is None:
        raise RuntimeError("No CUDA/OptiX Cycles device is available")
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    scene.render.fps = 24
    scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.35
    scene.view_settings.gamma = 1.0
    return f"{selected}: {', '.join(selected_devices)}"


def make_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("FullDemoCameraData")
    data.sensor_width = 36.0
    data.lens = 36.0 / (2.0 * math.tan(math.radians(70.0) / 2.0))
    data.clip_start = 0.05
    data.clip_end = 200.0
    camera = bpy.data.objects.new("FullDemoCamera", data)
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


def render_stills(run: Path, camera: bpy.types.Object) -> list[dict]:
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.cycles.samples = 96
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.04
    images = run / "images"
    images.mkdir(parents=True, exist_ok=True)
    demo_id = run.name
    views = [
        ((0.0, 5.6, 1.75), (0.0, 0.3, 1.25), "interior_axis"),
        ((-4.6, 3.6, 1.85), (-0.8, 0.7, 1.15), "interior_left"),
        ((4.6, 2.8, 1.85), (0.7, 0.0, 1.15), "interior_right"),
        ((0.0, 0.7, 1.65), (0.0, -7.5, 1.25), "inside_to_outside"),
        ((0.0, -5.7, 1.65), (0.0, 1.2, 1.30), "outside_to_inside"),
        ((-7.6, -10.2, 2.15), (0.0, -4.0, 1.35), "facade_left"),
        ((7.6, -11.3, 2.15), (0.0, -6.1, 1.25), "outdoor_context"),
        ((0.0, -14.8, 2.30), (0.0, -4.0, 1.55), "approach"),
    ]
    records = []
    for index, (position, target, role) in enumerate(views, start=1):
        point_camera(camera, position, target)
        path = images / f"{demo_id}_view_{index:02d}.png"
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
            }
        )
        print(f"FULL_DEMO_STILL_COMPLETE {demo_id} {index}/8", flush=True)
    return records


def render_video(run: Path, camera: bpy.types.Object) -> dict:
    scene = bpy.context.scene
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.cycles.samples = 32
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.08
    frames = run / ".render_frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    frame_count = 120
    for frame in range(1, frame_count + 1):
        progress = (frame - 1) / (frame_count - 1)
        eased = progress * progress * (3.0 - 2.0 * progress)
        x = 0.18 * math.sin(math.pi * progress)
        y = 5.3 + (-13.2 - 5.3) * eased
        z = 1.64 + 0.04 * math.sin(math.pi * progress)
        look_y = y - (3.0 + 0.7 * progress)
        look_x = 0.30 * math.sin(math.pi * min(1.0, progress * 1.2))
        point_camera(camera, (x, y, z), (look_x, look_y, 1.30))
        scene.frame_set(frame)
        path = frames / f"frame_{frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        if frame == 1 or frame % 20 == 0 or frame == frame_count:
            print(f"FULL_DEMO_VIDEO_FRAME {run.name} {frame}/{frame_count}", flush=True)
    video = run / f"{run.name}_indoor_to_outdoor.mp4"
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
    shutil.rmtree(frames)
    return {
        "path": video.name,
        "sha256": sha256(video),
        "bytes": video.stat().st_size,
        "resolution": [960, 540],
        "fps": 24,
        "frames": frame_count,
        "duration_seconds": frame_count / 24.0,
        "camera_path": "continuous step-free interior-to-exterior traversal through the shared entrance",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    allowed = (BASELINES / "annotations/gpt6_astra_xhigh/full").resolve()
    if not run.is_relative_to(allowed):
        raise ValueError("Run directory escapes the full-demo output root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("generation_success"):
        raise RuntimeError("Scene generation is incomplete")
    expected = [
        run / "images" / f"{run.name}_view_{index:02d}.png" for index in range(1, 9)
    ]
    expected.append(run / f"{run.name}_indoor_to_outdoor.mp4")
    if manifest.get("render_success") and all(path.is_file() for path in expected):
        hashes = manifest.get("outputs_sha256", {})
        if hashes and all(
            hashes.get(str(path.relative_to(run))) == sha256(path) for path in expected
        ):
            print(f"FULL_DEMO_RENDER_REUSED {run.name}", flush=True)
            return 0
        raise RuntimeError("Existing render output hash mismatch")
    try:
        geometry = build_scene(run, manifest)
        add_lighting()
        backend = configure_cycles(int(manifest["logical_seed"]))
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
        stills = render_stills(run, camera)
        video = render_video(run, camera)
        output_paths = [run / row["path"] for row in stills] + [run / video["path"]]
        manifest.update(
            render_success=True,
            render_completed_at_utc=now(),
            stills=stills,
            video=video,
            outputs_sha256={
                str(path.relative_to(run)): sha256(path) for path in output_paths
            },
        )
        write_json(manifest_path, manifest)
        print(f"FULL_DEMO_RENDER_COMPLETE {run.name} backend={backend}", flush=True)
        return 0
    except Exception as error:
        manifest.update(
            build_success=bool(manifest.get("build_success")),
            render_success=False,
            render_failure=f"{type(error).__name__}: {error}",
            render_failed_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
