"""Render one generated Infinigen scene to the frozen Table-2 contract.

This file is executed by Blender, not by the host Python interpreter.
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


ANCHOR_FRAMES = [1, 8, 15, 22, 29, 36, 43, 50]
HORIZONTAL_FOV_DEGREES = 70.0
CAMERA_HEIGHT_METERS = 1.55


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, required=True)
    return parser.parse_args(argv)


def select_camera() -> bpy.types.Object:
    camera = bpy.context.scene.camera
    if camera is not None and camera.type == "CAMERA":
        return camera
    cameras = sorted(
        (obj for obj in bpy.data.objects if obj.type == "CAMERA"),
        key=lambda obj: obj.name,
    )
    if not cameras:
        raise RuntimeError("No camera object found in scene")
    bpy.context.scene.camera = cameras[0]
    return cameras[0]


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
        gpu_devices = [
            device for device in preferences.devices if device.type == backend
        ]
        if gpu_devices:
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
        except TypeError:
            continue
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    return selected


def matrix_rows(matrix) -> list[list[float]]:
    return [[float(matrix[row][col]) for col in range(4)] for row in range(4)]


def normalize_camera_pose(camera: bpy.types.Object, frame: int):
    """Apply the method-independent indoor camera pose contract.

    Infinigen's RRT provides a collision-checked XY path and view direction,
    but also samples camera altitude and all three rotation axes.  Table 2
    freezes eye height and disallows arbitrary camera roll.  Preserve the
    generated XY path and full forward vector, set world Z to 1.55 m, and
    rebuild the orientation against global +Z so only roll is removed.
    """
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    source_camera_to_world = camera.matrix_world.copy()
    forward = -source_camera_to_world.to_3x3().col[2]
    if forward.length < 1e-8:
        raise RuntimeError(f"Degenerate camera forward vector at frame {frame}")
    forward.normalize()
    if abs(float(forward.dot(Vector((0.0, 0.0, 1.0))))) > 0.999:
        raise RuntimeError(
            f"Camera forward vector is parallel to global up at frame {frame}"
        )
    normalized_camera_to_world = forward.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    normalized_camera_to_world.translation = source_camera_to_world.translation
    normalized_camera_to_world.translation.z = CAMERA_HEIGHT_METERS
    camera.matrix_world = normalized_camera_to_world
    bpy.context.view_layer.update()
    return source_camera_to_world


def camera_record(
    camera: bpy.types.Object,
    frame: int,
    width: int,
    height: int,
    source_camera_to_world,
) -> dict:
    fov_x = float(camera.data.angle_x)
    focal = (width / 2.0) / math.tan(fov_x / 2.0)
    camera_to_world = camera.matrix_world.copy()
    world_to_camera = camera_to_world.inverted()
    return {
        "frame": frame,
        "output_index": frame - 1,
        "width": width,
        "height": height,
        "horizontal_fov_degrees": math.degrees(fov_x),
        "K": [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]],
        "camera_to_world_blender": matrix_rows(camera_to_world),
        "world_to_camera_blender": matrix_rows(world_to_camera),
        "source_camera_to_world_blender": matrix_rows(source_camera_to_world),
        "coordinate_convention": "Blender camera looks along local -Z with local +Y up",
        "pose_normalization": {
            "camera_height_m": CAMERA_HEIGHT_METERS,
            "preserve_source_xy": True,
            "preserve_source_forward": True,
            "remove_roll_with_global_up": True,
        },
    }


def render_frame(
    camera: bpy.types.Object,
    frame: int,
    output_path: Path,
    width: int,
    height: int,
    samples: int,
):
    scene = bpy.context.scene
    source_camera_to_world = normalize_camera_pose(camera, frame)
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.01
    scene.render.filepath = str(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return source_camera_to_world


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    backend = configure_cycles()
    camera = select_camera()
    camera.data.type = "PERSP"
    camera.data.angle = math.radians(HORIZONTAL_FOV_DEGREES)
    camera.data.lens_unit = "FOV"
    camera.data.dof.use_dof = False
    camera.data.clip_start = 0.05
    camera.data.clip_end = 500.0
    sequence_records = []
    for frame in range(1, 51):
        output = run_dir / "renders/sequence" / f"rgb_{frame - 1:03d}.png"
        source_pose = render_frame(camera, frame, output, 512, 512, 64)
        sequence_records.append(camera_record(camera, frame, 512, 512, source_pose))
    anchor_records = []
    for index, frame in enumerate(ANCHOR_FRAMES):
        output = run_dir / "renders/anchors" / f"rgb_{index:03d}.png"
        source_pose = render_frame(camera, frame, output, 1280, 720, 256)
        record = camera_record(camera, frame, 1280, 720, source_pose)
        record["anchor_index"] = index
        anchor_records.append(record)
    cameras_path = run_dir / "renders/sequence/cameras.json"
    cameras_path.write_text(
        json.dumps(
            {
                "renderer": "Blender Cycles",
                "cycles_backend": backend,
                "camera_pose_contract": {
                    "camera_height_m": CAMERA_HEIGHT_METERS,
                    "preserve_source_xy": True,
                    "preserve_source_forward": True,
                    "remove_roll_with_global_up": True,
                },
                "sequence": sequence_records,
                "anchors": anchor_records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "TABLE2_RENDER_COMPLETE "
        f"backend={backend} sequence={len(sequence_records)} anchors={len(anchor_records)}"
    )


if __name__ == "__main__":
    main()
