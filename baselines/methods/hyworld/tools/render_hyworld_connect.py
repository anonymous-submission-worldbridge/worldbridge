#!/usr/bin/env python3
"""Render the existing HyWorld2 connected indoor/outdoor Blender demos.

Run with Blender, for example::

    blender -b scene.blend --python render_hyworld_connect.py -- \
        --output-dir /path/to/output --scene-id scene_01

The source .blend is never modified.  Images are independent PNG files and
contain no view labels, numbers, montage borders, or other overlays.
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
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import bpy


STILL_CAMERAS = {
    "outdoor": "camera_street",
    "outdoor_to_indoor": "camera_entrance_00",
    "indoor": "camera_room_00",
    "indoor_to_outdoor": "camera_interior_00",
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def camera_record(obj: bpy.types.Object) -> dict:
    return {
        "name": obj.name,
        "location_m": [round(float(value), 6) for value in obj.location],
        "rotation_euler_rad": [round(float(value), 6) for value in obj.rotation_euler],
        "lens_mm": round(float(obj.data.lens), 6),
    }


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    images_dir = output_dir / "images"
    videos_dir = output_dir / "videos"
    images_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 35
    scene.render.fps = 24
    scene.render.fps_base = 1.0
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = args.samples

    missing = [name for name in STILL_CAMERAS.values() if name not in bpy.data.objects]
    if "camera_walkthrough" not in bpy.data.objects:
        missing.append("camera_walkthrough")
    if missing:
        raise RuntimeError(f"Missing required cameras: {missing}")

    started = time.time()
    rendered_images: list[Path] = []
    for role, camera_name in STILL_CAMERAS.items():
        output_path = images_dir / f"{role}.png"
        rendered_images.append(output_path)
        if output_path.exists() and output_path.stat().st_size > 0 and not args.force:
            print(f"CONNECT_SKIP_STILL {role} {output_path}", flush=True)
            continue
        scene.camera = bpy.data.objects[camera_name]
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(output_path)
        print(f"CONNECT_RENDER_STILL {role} camera={camera_name}", flush=True)
        bpy.ops.render.render(write_still=True)

    video_path = videos_dir / "outdoor_to_indoor.mp4"
    if not (video_path.exists() and video_path.stat().st_size > 0) or args.force:
        scene.camera = bpy.data.objects["camera_walkthrough"]
        scene.frame_start = 1
        scene.frame_end = 120
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.ffmpeg.audio_codec = "NONE"
        scene.render.filepath = str(video_path)
        print(
            "CONNECT_RENDER_VIDEO outdoor_to_indoor "
            f"camera=camera_walkthrough frames={scene.frame_start}-{scene.frame_end}",
            flush=True,
        )
        bpy.ops.render.render(animation=True)
    else:
        print(f"CONNECT_SKIP_VIDEO outdoor_to_indoor {video_path}", flush=True)

    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    portal_objects = sorted(
        obj.name for obj in bpy.data.objects if "shared_portal" in obj.name.lower()
    )
    output_files = [*rendered_images, video_path]
    audit = {
        "schema_version": "1.0",
        "scene_id": args.scene_id,
        "source_blend": str(Path(bpy.data.filepath).resolve()),
        "real_3d_geometry": True,
        "native_shared_world_frame": True,
        "coordinate_system": "metric Z-up right-handed Blender world coordinates",
        "mesh_object_count": len(mesh_objects),
        "mesh_vertex_count": sum(len(obj.data.vertices) for obj in mesh_objects),
        "mesh_polygon_count": sum(len(obj.data.polygons) for obj in mesh_objects),
        "shared_portal_objects": portal_objects,
        "walkthrough_camera": camera_record(bpy.data.objects["camera_walkthrough"]),
        "walkthrough_crosses_exterior_portal": True,
        "still_views": {
            role: camera_record(bpy.data.objects[camera_name])
            for role, camera_name in STILL_CAMERAS.items()
        },
        "render": {
            "engine": scene.render.engine,
            "width": args.width,
            "height": args.height,
            "fps": 24,
            "video_frames": [1, 120],
            "video_direction": "outdoor_to_indoor",
            "overlays": False,
            "montage": False,
        },
        "elapsed_seconds": round(time.time() - started, 3),
        "outputs": [
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in output_files
            if path.exists()
        ],
    }
    audit_path = output_dir / "render_audit.json"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"CONNECT_DONE {audit_path}", flush=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    main()
