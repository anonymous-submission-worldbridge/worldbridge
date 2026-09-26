"""Render a native MajutsuCity blend to the frozen Table-2 camera contract.

The road-constrained 42 m camera path is prepared outside Blender by the
MajutsuCity adapter.  This script only applies those frozen poses and preserves
the lighting, sky and materials assembled by the upstream release.
"""

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
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ANCHOR_FRAMES = (1, 8, 15, 22, 29, 36, 43, 50)
HORIZONTAL_FOV_DEGREES = 70.0


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, required=True)
    return parser.parse_args(argv)


def configure_cycles() -> str:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    selected = "CPU"
    for backend in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
        except Exception:
            continue
        devices = [device for device in preferences.devices if device.type == backend]
        if devices:
            for device in preferences.devices:
                device.use = device.type == backend
            selected = backend
            break
    if selected == "CPU":
        raise RuntimeError("No CUDA/OPTIX Cycles device is available")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.fps = 10
    scene.view_settings.view_transform = "Standard"
    for look in ("Medium High Contrast", "AgX - Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    return selected


def make_camera() -> bpy.types.Object:
    for obj in list(bpy.data.objects):
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)
    data = bpy.data.cameras.new("Table2MajutsuCameraData")
    data.sensor_fit = "HORIZONTAL"
    data.angle = math.radians(HORIZONTAL_FOV_DEGREES)
    data.clip_start = 0.05
    data.clip_end = 1500.0
    camera = bpy.data.objects.new("Table2MajutsuCamera", data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def matrix_rows(matrix) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def intrinsic_matrix(width: int, height: int) -> list[list[float]]:
    focal = 0.5 * width / math.tan(0.5 * math.radians(HORIZONTAL_FOV_DEGREES))
    return [
        [focal, 0.0, width / 2.0],
        [0.0, focal, height / 2.0],
        [0.0, 0.0, 1.0],
    ]


def apply_pose(camera: bpy.types.Object, record: dict) -> None:
    camera.location = tuple(float(value) for value in record["position_m"])
    heading = math.radians(float(record["view_heading_degrees"]))
    direction = Vector((math.cos(heading), math.sin(heading), 0.0))
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()


def render_image(path: Path, width: int, height: int, samples: int) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    plan = json.loads((run_dir / "input/camera_plan.json").read_text(encoding="utf-8"))
    poses = plan["sequence"]
    if len(poses) != 50:
        raise ValueError(f"Expected 50 camera poses, got {len(poses)}")

    anchors_dir = run_dir / "renders/anchors"
    sequence_dir = run_dir / "renders/sequence"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    sequence_dir.mkdir(parents=True, exist_ok=True)
    for render_dir in (anchors_dir, sequence_dir):
        for stale_image in render_dir.glob("rgb_*.png"):
            stale_image.unlink()

    backend = configure_cycles()
    camera = make_camera()
    scene = bpy.context.scene
    camera_records = []
    for index, pose in enumerate(poses):
        frame = index + 1
        scene.frame_set(frame)
        apply_pose(camera, pose)
        render_image(sequence_dir / f"rgb_{frame:03d}.png", 512, 512, 64)
        camera_records.append(
            {
                **pose,
                "frame": frame,
                "camera_to_world_blender": matrix_rows(camera.matrix_world),
                "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
                "resolution": [512, 512],
                "K": intrinsic_matrix(512, 512),
            }
        )

    anchor_records = []
    for anchor_index, frame in enumerate(ANCHOR_FRAMES):
        scene.frame_set(frame)
        apply_pose(camera, poses[frame - 1])
        output = anchors_dir / f"rgb_{anchor_index:03d}.png"
        render_image(output, 1280, 720, 256)
        anchor_records.append(
            {
                **poses[frame - 1],
                "frame": frame,
                "path": str(output.relative_to(run_dir)),
                "camera_to_world_blender": matrix_rows(camera.matrix_world),
                "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
                "resolution": [1280, 720],
                "K": intrinsic_matrix(1280, 720),
            }
        )

    payload = {
        "coordinate_convention": "Blender world; camera local -Z forward, local +Y up",
        "physical_gpu_requested": args.gpu,
        "camera_pose_contract": plan["camera_pose_contract"],
        "path_planner": plan["path_planner"],
        "render": {
            "engine": "cycles",
            "device": backend.lower(),
            "sequence_samples": 64,
            "anchor_samples": 256,
            "denoise": True,
        },
        "sequence": camera_records,
        "anchors": anchor_records,
    }
    (sequence_dir / "cameras.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"MAJUTSUCITY_RENDER_COMPLETE backend={backend} "
        f"path_length_m={plan['path_planner']['path_length_m']:.3f}"
    )


if __name__ == "__main__":
    main()
