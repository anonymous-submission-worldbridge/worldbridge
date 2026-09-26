#!/usr/bin/env python3
"""Build, audit, and GPU-render one GPT-6 Astra high connected demo."""
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
OUTPUT = (BASELINES / "annotations/gpt6_astra/connect").resolve()
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


def scene_ray(
    origin: tuple[float, float, float],
    direction: tuple[float, float, float],
    distance: float,
):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, normal, face_index, obj, matrix = bpy.context.scene.ray_cast(
        depsgraph, Vector(origin), Vector(direction), distance=distance
    )
    return hit, location, normal, face_index, obj, matrix


def connectivity_audit() -> dict:
    """Check the camera corridor and a continuous near-level walking surface."""
    eye_rays = []
    eye_clear = True
    for x in (-0.60, 0.0, 0.60):
        hit, location, _normal, _face, obj, _matrix = scene_ray(
            (x, -14.2, 1.20), (0.0, 1.0, 0.0), 20.2
        )
        hit_y = float(location.y) if hit else None
        row = {
            "x_m": x,
            "hit": bool(hit),
            "first_hit_y_m": hit_y,
            "object": obj.name if obj else None,
        }
        eye_rays.append(row)
        if hit and hit_y < 5.70:
            eye_clear = False

    surface_samples = []
    surface_continuous = True
    for y in np.linspace(-14.0, 5.5, 40):
        hit, location, _normal, _face, obj, _matrix = scene_ray(
            (0.0, float(y), 0.80), (0.0, 0.0, -1.0), 1.20
        )
        z = float(location.z) if hit else None
        valid = bool(hit and -0.25 <= z <= 0.25)
        surface_samples.append(
            {
                "y_m": round(float(y), 3),
                "hit_z_m": None if z is None else round(z, 4),
                "object": obj.name if obj else None,
                "valid": valid,
            }
        )
        surface_continuous = surface_continuous and valid
    return {
        "passed": eye_clear and surface_continuous,
        "eye_level_corridor_clear": eye_clear,
        "walking_surface_continuous": surface_continuous,
        "eye_level_rays": eye_rays,
        "walking_surface_samples": surface_samples,
        "contract": "X samples -0.60/0/0.60 m clear from Y=-14.2 to 5.7 at Z=1.2; center walking surface within Z +/-0.25 m",
    }


def build_scene(run: Path, manifest: dict) -> tuple[dict, dict]:
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
    namespace = {"__name__": "astra_connect_demo_scene"}
    exec(compile(source, str(generated), "exec"), namespace)
    # Some generated scripts use bpy.scene as a concise alias for the active
    # scene. Blender exposes the object at bpy.context.scene, so provide the
    # non-mutating compatibility alias without editing the preserved source.
    if not hasattr(bpy, "scene"):
        bpy.scene = bpy.context.scene
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
    geometry = {
        "visible_mesh_objects": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "edges": sum(len(obj.data.edges) for obj in meshes),
        "polygons": sum(len(obj.data.polygons) for obj in meshes),
        "materials": len(bpy.data.materials),
        "collections": len(bpy.data.collections),
        "bounds_min_xyz_m": bounds_min,
        "bounds_max_xyz_m": bounds_max,
    }
    connectivity = connectivity_audit()
    if not connectivity["passed"]:
        raise RuntimeError(
            "Generated scene failed the physical indoor/outdoor connectivity audit"
        )
    return geometry, connectivity


def add_lighting() -> None:
    world = bpy.data.worlds.new("ConnectDemoWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.52, 0.64, 0.80, 1.0)
    background.inputs["Strength"].default_value = 0.22

    sun_data = bpy.data.lights.new("ConnectDemoSunData", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(9.0)
    sun = bpy.data.objects.new("ConnectDemoSun", sun_data)
    sun.rotation_euler = (math.radians(28.0), math.radians(-18.0), math.radians(-32.0))
    bpy.context.scene.collection.objects.link(sun)

    for index, (x, y, energy, size) in enumerate(
        (
            (-3.0, 4.2, 420.0, 2.8),
            (3.0, 4.2, 420.0, 2.8),
            (-3.0, 0.0, 340.0, 2.4),
            (3.0, 0.0, 340.0, 2.4),
        )
    ):
        data = bpy.data.lights.new(f"InteriorFillData{index:02d}", "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = (1.0, 0.84, 0.68)
        obj = bpy.data.objects.new(f"InteriorFill{index:02d}", data)
        obj.location = (x, y, 3.05)
        bpy.context.scene.collection.objects.link(obj)


def configure_cycles(seed: int) -> dict:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.seed = seed
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 8
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
    scene.view_settings.exposure = 0.10
    scene.view_settings.gamma = 1.0
    return {"engine": "Cycles", "device_backend": selected, "devices": selected_devices}


def make_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("ConnectDemoCameraData")
    data.sensor_width = 36.0
    data.lens = 36.0 / (2.0 * math.tan(math.radians(70.0) / 2.0))
    data.clip_start = 0.05
    data.clip_end = 200.0
    camera = bpy.data.objects.new("ConnectDemoCamera", data)
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
    scene.cycles.samples = 128
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    images = run / "images"
    images.mkdir(parents=True, exist_ok=True)
    views = [
        ((0.0, 5.7, 1.72), (0.0, 0.4, 1.20), "interior_overview"),
        ((-4.7, 3.8, 1.82), (-0.8, 0.7, 1.12), "interior_left_detail"),
        ((4.7, 3.0, 1.82), (0.8, 0.0, 1.12), "interior_right_detail"),
        ((0.0, 0.8, 1.64), (0.0, -8.0, 1.20), "inside_to_outside_connection"),
        ((0.0, -6.4, 1.64), (0.0, 1.8, 1.25), "outside_to_inside_connection"),
        ((-7.7, -10.4, 2.10), (0.0, -4.1, 1.32), "exterior_facade"),
        ((7.7, -11.4, 2.12), (0.0, -6.0, 1.22), "exterior_context"),
        ((0.0, -14.8, 2.22), (0.0, -4.0, 1.48), "exterior_approach"),
    ]
    records = []
    for index, (position, target, role) in enumerate(views, start=1):
        point_camera(camera, position, target)
        path = images / f"{role}.png"
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
                "resolution": [1280, 720],
                "samples": 128,
            }
        )
        print(
            f"CONNECT_STILL_COMPLETE {run.name} {index}/{len(views)} role={role}",
            flush=True,
        )
    return records


def render_video(run: Path, camera: bpy.types.Object, direction: str) -> dict:
    if direction not in {"indoor_to_outdoor", "outdoor_to_indoor"}:
        raise ValueError(direction)
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.cycles.samples = 40
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.06
    frames = run / f".render_frames_{direction}"
    if frames.exists():
        if not frames.resolve().is_relative_to(run.resolve()):
            raise RuntimeError("Temporary frame directory escaped the run root")
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    frame_count = 120
    for frame in range(1, frame_count + 1):
        progress = (frame - 1) / (frame_count - 1)
        eased = progress * progress * (3.0 - 2.0 * progress)
        if direction == "indoor_to_outdoor":
            y = 5.35 + (-13.6 - 5.35) * eased
            heading = -1.0
            x = 0.16 * math.sin(math.pi * progress)
        else:
            y = -13.6 + (5.35 + 13.6) * eased
            heading = 1.0
            x = -0.16 * math.sin(math.pi * progress)
        z = 1.64 + 0.035 * math.sin(math.pi * progress)
        look_y = y + heading * (3.1 + 0.55 * progress)
        look_x = 0.22 * math.sin(math.pi * min(1.0, progress * 1.2)) * heading
        point_camera(camera, (x, y, z), (look_x, look_y, 1.28))
        scene.frame_set(frame)
        path = frames / f"frame_{frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        if frame == 1 or frame % 20 == 0 or frame == frame_count:
            print(
                f"CONNECT_VIDEO_FRAME {run.name} {direction} {frame}/{frame_count}",
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
    shutil.rmtree(frames)
    return {
        "path": str(video.relative_to(run)),
        "role": direction,
        "sha256": sha256(video),
        "bytes": video.stat().st_size,
        "resolution": [1280, 720],
        "fps": 24,
        "frames": frame_count,
        "duration_seconds": frame_count / 24.0,
        "camera_path": f"continuous step-free {direction.replace('_', '-')} traversal through the shared open entrance",
    }


def expected_outputs(run: Path) -> list[Path]:
    roles = (
        "interior_overview",
        "interior_left_detail",
        "interior_right_detail",
        "inside_to_outside_connection",
        "outside_to_inside_connection",
        "exterior_facade",
        "exterior_context",
        "exterior_approach",
    )
    return [run / "images" / f"{role}.png" for role in roles] + [
        run / "videos/indoor_to_outdoor.mp4",
        run / "videos/outdoor_to_indoor.mp4",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(OUTPUT):
        raise ValueError("Run directory escapes the connect-demo output root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("method") != "gpt6_astra"
        or manifest.get("reasoning_effort_requested") != "high"
    ):
        raise RuntimeError("Run is not a GPT-6 Astra high artifact")
    if not manifest.get("generation_success"):
        raise RuntimeError("Scene generation is incomplete")
    expected = expected_outputs(run)
    if manifest.get("render_success") and all(path.is_file() for path in expected):
        hashes = manifest.get("outputs_sha256", {})
        if hashes and all(
            hashes.get(str(path.relative_to(run))) == sha256(path) for path in expected
        ):
            print(f"CONNECT_RENDER_REUSED {run.name}", flush=True)
            return 0
        raise RuntimeError("Existing render output hash mismatch")
    try:
        geometry, connectivity = build_scene(run, manifest)
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
            connectivity_audit=connectivity,
            render_backend=backend,
        )
        write_json(manifest_path, manifest)
        stills = render_stills(run, camera)
        videos = [
            render_video(run, camera, "indoor_to_outdoor"),
            render_video(run, camera, "outdoor_to_indoor"),
        ]
        output_paths = [run / row["path"] for row in stills + videos]
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
        manifest.pop("render_failed_at_utc", None)
        write_json(manifest_path, manifest)
        print(f"CONNECT_RENDER_COMPLETE {run.name} backend={backend}", flush=True)
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
