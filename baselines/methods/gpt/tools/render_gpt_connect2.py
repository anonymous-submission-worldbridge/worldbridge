#!/usr/bin/env python3
"""Build and GPU-render one GPT-6 Astra high connect2 scene."""
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
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import bpy

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.render_glm_flash_connect as base
import baselines.methods.glm_flash.tools.render_glm_flash_connect2 as detail


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gpt6_astra/connect2"
SCENE_IDS = (
    "residential_neighborhood",
    "neighborhood_school",
    "public_library",
    "community_sports_hall",
    "retail_pharmacy",
    "police_station",
    "fire_station",
    "community_hospital",
    "light_factory",
    "delivery_service_hub",
    "community_bank_atm",
    "gas_station_store",
    "riverside_lake_park",
)
STILL_SIZE = (1280, 720)
VIDEO_SIZE = (1280, 720)
FPS = 24
VIDEO_FRAMES = 96
IMAGE_ROLES = (
    "indoor_overview",
    "indoor_left_detail",
    "indoor_right_detail",
    "outdoor_overview",
    "outdoor_left_detail",
    "outdoor_right_detail",
    "inside_to_outside_far_center",
    "inside_to_outside_far_left",
    "inside_to_outside_far_right",
    "inside_to_outside_mid_center",
    "inside_to_outside_mid_left",
    "inside_to_outside_mid_right",
    "inside_to_outside_near",
    "outside_to_inside_far_center",
    "outside_to_inside_far_left",
    "outside_to_inside_far_right",
    "outside_to_inside_mid_center",
    "outside_to_inside_mid_left",
    "outside_to_inside_mid_right",
    "outside_to_inside_near",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_blueprint(path: Path, scene_id: str):
    spec = importlib.util.spec_from_file_location(f"astra_connect2_{scene_id}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import blueprint {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "build_scene", None)):
        raise RuntimeError("blueprint lacks build_scene(api)")
    if getattr(module, "SCENE_SPEC", {}).get("scene_id") != scene_id:
        raise RuntimeError("blueprint scene id mismatch")
    return module


def configure_render(width: int, height: int, samples: int) -> None:
    base.configure_render(width, height, samples)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.compression = 68
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.view_settings.look = "AgX - Medium High Contrast"


def extended_connection_audit() -> dict[str, object]:
    # The model-authored blueprint must preserve the route itself.  This pass
    # is deliberately read-only so articulated furniture is never separated.
    blockers = []
    doorway_blockers = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name.startswith("Harness_"):
            continue
        low, high = base.world_bbox(obj)
        if (
            low.x < 0.70
            and high.x > -0.70
            and low.y < 12.0
            and high.y > -0.10
            and low.z < 2.35
            and high.z > 0.18
        ):
            blockers.append(obj.name)
        if (
            low.x < 1.08
            and high.x > -1.08
            and low.y < 0.22
            and high.y > -0.22
            and low.z < 2.70
            and high.z > 0.16
        ):
            doorway_blockers.append(obj.name)
    return {
        "extended_route_to_y_m": 12.0,
        "route_half_width_m": 0.70,
        "moved_extended_route_blockers": [],
        "remaining_route_blockers": blockers,
        "remaining_doorway_blockers": doorway_blockers,
        "passed": not blockers and not doorway_blockers,
    }


def still_views():
    return (
        (
            "indoor_overview",
            (0.0, -1.05, 2.25),
            (0.0, -6.15, 1.15),
            25,
            "indoor",
            "far",
        ),
        (
            "indoor_left_detail",
            (-1.20, -6.55, 1.78),
            (-3.9, -5.0, 1.10),
            31,
            "indoor",
            "mid",
        ),
        (
            "indoor_right_detail",
            (1.20, -6.55, 1.78),
            (3.9, -4.7, 1.10),
            31,
            "indoor",
            "mid",
        ),
        ("outdoor_overview", (8.0, 18.2, 6.6), (0.0, 7.2, 1.05), 28, "outdoor", "far"),
        (
            "outdoor_left_detail",
            (-7.0, 9.2, 2.35),
            (-1.2, 5.2, 1.05),
            35,
            "outdoor",
            "mid",
        ),
        (
            "outdoor_right_detail",
            (7.0, 10.8, 2.35),
            (1.2, 5.8, 1.05),
            35,
            "outdoor",
            "mid",
        ),
        (
            "inside_to_outside_far_center",
            (0.0, -8.10, 1.76),
            (0.0, 7.0, 1.22),
            27,
            "inside_to_outside",
            "far",
        ),
        (
            "inside_to_outside_far_left",
            (-1.22, -7.55, 2.05),
            (0.30, 7.0, 1.18),
            29,
            "inside_to_outside",
            "far",
        ),
        (
            "inside_to_outside_far_right",
            (1.22, -7.55, 2.05),
            (-0.30, 7.0, 1.18),
            29,
            "inside_to_outside",
            "far",
        ),
        (
            "inside_to_outside_mid_center",
            (0.0, -5.10, 1.64),
            (0.0, 8.2, 1.18),
            31,
            "inside_to_outside",
            "mid",
        ),
        (
            "inside_to_outside_mid_left",
            (-1.10, -4.20, 1.86),
            (0.35, 6.6, 1.20),
            30,
            "inside_to_outside",
            "mid",
        ),
        (
            "inside_to_outside_mid_right",
            (1.10, -4.20, 1.86),
            (-0.35, 6.6, 1.20),
            30,
            "inside_to_outside",
            "mid",
        ),
        (
            "inside_to_outside_near",
            (0.0, -1.55, 1.58),
            (0.0, 8.8, 1.18),
            33,
            "inside_to_outside",
            "near",
        ),
        (
            "outside_to_inside_far_center",
            (0.0, 17.0, 2.25),
            (0.0, -5.4, 1.20),
            28,
            "outside_to_inside",
            "far",
        ),
        (
            "outside_to_inside_far_left",
            (-2.9, 15.2, 3.05),
            (0.25, -4.5, 1.18),
            30,
            "outside_to_inside",
            "far",
        ),
        (
            "outside_to_inside_far_right",
            (2.9, 15.2, 3.05),
            (-0.25, -4.5, 1.18),
            30,
            "outside_to_inside",
            "far",
        ),
        (
            "outside_to_inside_mid_center",
            (0.0, 9.3, 1.72),
            (0.0, -5.0, 1.18),
            31,
            "outside_to_inside",
            "mid",
        ),
        (
            "outside_to_inside_mid_left",
            (-1.15, 8.3, 2.00),
            (0.30, -4.2, 1.16),
            31,
            "outside_to_inside",
            "mid",
        ),
        (
            "outside_to_inside_mid_right",
            (1.15, 8.3, 2.00),
            (-0.30, -4.2, 1.16),
            31,
            "outside_to_inside",
            "mid",
        ),
        (
            "outside_to_inside_near",
            (0.0, 3.65, 1.58),
            (0.0, -5.2, 1.16),
            34,
            "outside_to_inside",
            "near",
        ),
    )


def render_stills(
    root: Path, camera: bpy.types.Object, force: bool = False
) -> list[dict[str, object]]:
    image_root = root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    views = still_views()
    if tuple(row[0] for row in views) != IMAGE_ROLES:
        raise RuntimeError("still role ordering mismatch")
    configure_render(*STILL_SIZE, samples=64)
    records = []
    for index, (role, location, target, lens, direction, distance) in enumerate(
        views, start=1
    ):
        path = image_root / f"{role}.png"
        reused = not force and path.is_file() and path.stat().st_size > 20_000
        if not reused:
            base.look_at(camera, location, target, lens)
            bpy.context.scene.render.filepath = str(path)
            bpy.context.scene.frame_set(1)
            bpy.ops.render.render(write_still=True)
        if not path.is_file() or path.stat().st_size < 20_000:
            raise RuntimeError(f"invalid still render: {path}")
        records.append(
            {
                "role": role,
                "direction": direction,
                "distance_band": distance,
                "path": str(path.relative_to(root)),
                "width": STILL_SIZE[0],
                "height": STILL_SIZE[1],
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "camera_location": list(location),
                "camera_target": list(target),
                "lens_mm": lens,
            }
        )
        status = "REUSED" if reused else "COMPLETE"
        print(
            f"ASTRA_CONNECT2_IMAGE_{status} scene={root.name} {index}/{len(views)} role={role}",
            flush=True,
        )
    return records


def animate_camera(camera: bpy.types.Object, frames: int) -> None:
    camera.animation_data_clear()
    keyframes = (
        (1, (0.0, -7.75, 1.64), (0.0, -2.3, 1.30), 31),
        (round(frames * 0.25), (0.0, -3.65, 1.62), (0.0, 1.0, 1.28), 30),
        (round(frames * 0.50), (0.0, -0.60, 1.60), (0.0, 4.2, 1.23), 29),
        (round(frames * 0.75), (0.0, 3.30, 1.62), (0.0, 7.6, 1.20), 31),
        (frames, (0.0, 10.8, 1.72), (0.0, 14.2, 1.24), 34),
    )
    for frame, location, target, lens in keyframes:
        base.look_at(camera, location, target, lens)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera.data.keyframe_insert(data_path="lens", frame=frame)
    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"


def render_videos(
    root: Path, camera: bpy.types.Object, frames: int, force: bool = False
) -> list[dict[str, object]]:
    video_root = root / "videos"
    video_root.mkdir(parents=True, exist_ok=True)
    forward = video_root / "inside_to_outside.mp4"
    reverse = video_root / "outside_to_inside.mp4"
    if force or not (forward.is_file() and forward.stat().st_size > 50_000):
        forward.unlink(missing_ok=True)
        animate_camera(camera, frames)
        configure_render(*VIDEO_SIZE, samples=32)
        scene = bpy.context.scene
        scene.frame_start = 1
        scene.frame_end = frames
        scene.render.fps = FPS
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.ffmpeg.audio_codec = "NONE"
        scene.render.filepath = str(forward)
        print(
            f"ASTRA_CONNECT2_VIDEO_START scene={root.name} frames={frames}", flush=True
        )
        bpy.ops.render.render(animation=True)
        duplicate = forward.with_suffix(".mp4.mp4")
        if duplicate.is_file() and not forward.is_file():
            duplicate.replace(forward)
    if not forward.is_file() or forward.stat().st_size < 50_000:
        raise RuntimeError("forward traversal video was not created")
    if force or not (reverse.is_file() and reverse.stat().st_size > 50_000):
        reverse.unlink(missing_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(forward),
                "-vf",
                "reverse",
                "-an",
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
                str(reverse),
            ],
            check=True,
        )
    records = []
    for role, path in (("inside_to_outside", forward), ("outside_to_inside", reverse)):
        records.append(
            {
                "role": role,
                "path": str(path.relative_to(root)),
                "width": VIDEO_SIZE[0],
                "height": VIDEO_SIZE[1],
                "fps": FPS,
                "frames": frames,
                "duration_seconds": frames / FPS,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    print(f"ASTRA_CONNECT2_VIDEO_COMPLETE scene={root.name}", flush=True)
    return records


def save_scene(root: Path) -> dict[str, object]:
    destination = root / "scene/scene.blend"
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), compress=True)
    if destination.stat().st_size < 100_000:
        raise RuntimeError("compressed Blender scene is unexpectedly small")
    return {
        "path": str(destination.relative_to(root)),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
    }


def main() -> int:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", required=True, choices=SCENE_IDS)
    parser.add_argument("--video-frames", type=int, default=VIDEO_FRAMES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(arguments)
    if args.video_frames < 48:
        raise ValueError("video must contain at least 48 frames")
    root = OUTPUT / args.scene_id
    generated = root / "source/generated.py"
    generation_manifest = root / "generation_manifest.json"
    render_manifest = root / "manifest.json"
    expected = [
        root / "scene/scene.blend",
        *(root / "images" / f"{role}.png" for role in IMAGE_ROLES),
        root / "videos/inside_to_outside.mp4",
        root / "videos/outside_to_inside.mp4",
    ]
    if (
        not args.force
        and render_manifest.is_file()
        and all(path.is_file() and path.stat().st_size > 0 for path in expected)
    ):
        old = json.loads(render_manifest.read_text(encoding="utf-8"))
        if (
            old.get("render_success") is True
            and old.get("video_frames") == args.video_frames
        ):
            print(f"ASTRA_CONNECT2_RENDER_REUSED scene={args.scene_id}", flush=True)
            return 0
    if not generated.is_file() or not generation_manifest.is_file():
        raise FileNotFoundError(f"missing generated blueprint for {args.scene_id}")
    generation = json.loads(generation_manifest.read_text(encoding="utf-8"))
    started_at = utc()
    started = time.monotonic()
    print(f"ASTRA_CONNECT2_BUILD_START scene={args.scene_id}", flush=True)
    base.clear_scene()
    api = detail.DetailedSceneAPI()
    detail.ensure_core(api, args.scene_id)
    blueprint = load_blueprint(generated, args.scene_id)
    blueprint.build_scene(api)
    detail.add_refinement_pass(api, args.scene_id)
    base_connection = base.enforce_open_connection()
    extended_connection = extended_connection_audit()
    if not extended_connection["passed"]:
        raise RuntimeError(f"connection audit failed: {extended_connection}")
    camera = detail.add_camera_and_lighting(args.scene_id)
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in mesh_objects)
    polygons = sum(len(obj.data.polygons) for obj in mesh_objects)
    if len(mesh_objects) < 180 or vertices < 3000:
        raise RuntimeError(
            f"scene is too sparse: meshes={len(mesh_objects)} vertices={vertices}"
        )
    scene_asset = save_scene(root)
    images = render_stills(root, camera, args.force)
    videos = render_videos(root, camera, args.video_frames, args.force)
    manifest = {
        "schema_version": 1,
        "method": "gpt6_astra",
        "model_requested": "gpt-6-astra",
        "reasoning_effort_requested": "high",
        "provider": "openai_codex",
        "scene_id": args.scene_id,
        "title_zh": generation["title_zh"],
        "categories_zh": generation["categories_zh"],
        "created_at_utc": started_at,
        "completed_at_utc": utc(),
        "render_success": True,
        "true_shared_coordinate_3d_scene": True,
        "native_geometry": True,
        "external_assets": False,
        "image_policy": "20 separate unlabelled 1280x720 PNG files; no montage and no embedded numbering",
        "renderer": "BLENDER_EEVEE_NEXT",
        "gpu_lane": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "generation": {
            "generated_code": "source/generated.py",
            "generated_code_sha256": sha256(generated),
            "prompt_sha256": generation["prompt_sha256"],
            "model_requested": generation["model_requested"],
            "reasoning_effort_requested": generation["reasoning_effort_requested"],
            "high_level_api_calls": generation["high_level_api_calls"],
        },
        "geometry": {
            "mesh_object_count": len(mesh_objects),
            "vertex_count": vertices,
            "polygon_count": polygons,
            "material_count": len(bpy.data.materials),
            "interior_bounds_approx_m": [[-6, -9, 0], [6, 0, 3.65]],
            "exterior_bounds_approx_m": [[-15, 0, 0], [15, 20, 8]],
        },
        "connectivity": {
            "shared_coordinate_frame": True,
            "open_doorway_center_xyz": [0.0, 0.0, 1.4],
            "clear_width_m": 2.2,
            "flush_threshold": True,
            "inside_to_outside_camera_crosses_same_doorway": True,
            "outside_to_inside_is_reverse_of_same_path": True,
            "base_adjustments": base_connection,
            "extended_audit": extended_connection,
        },
        "scene_asset": scene_asset,
        "images": images,
        "videos": videos,
        "still_resolution": list(STILL_SIZE),
        "video_resolution": list(VIDEO_SIZE),
        "video_fps": FPS,
        "video_frames": args.video_frames,
        "wall_time_seconds": round(time.monotonic() - started, 3),
        "blender_version": bpy.app.version_string,
    }
    atomic_json(render_manifest, manifest)
    print(
        f"ASTRA_CONNECT2_SCENE_COMPLETE scene={args.scene_id} meshes={len(mesh_objects)} vertices={vertices}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
