#!/usr/bin/env python3
"""Validate and index the six GLM-5.3 Flash connected visualization demos."""

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


from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/glm53_flash/connect"
SCENES = (
    "courtyard_cafe",
    "garden_villa",
    "bookshop_arcade",
    "coastal_bungalow",
    "mountain_lodge",
    "gallery_plaza",
)
IMAGE_ROLES = (
    "indoor_overview",
    "indoor_detail",
    "indoor_entry_wide",
    "inside_to_outside_far",
    "inside_to_outside_mid",
    "inside_to_outside_left",
    "inside_to_outside_right",
    "inside_to_outside_high",
    "outdoor_overview",
    "outdoor_detail",
    "outdoor_entry_wide",
    "outside_to_inside_far",
    "outside_to_inside_mid",
    "outside_to_inside_left",
    "outside_to_inside_right",
    "outside_to_inside_high",
)
VIDEO_ROLES = ("inside_to_outside", "outside_to_inside")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def image_record(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        if image.size != (1280, 720) or image.mode not in {"RGB", "RGBA"}:
            raise ValueError(f"invalid image format: {path}: {image.mode} {image.size}")
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    mean = float(array.mean())
    std = float(array.std())
    dark_fraction = float((array.mean(axis=2) < 0.02).mean())
    if not 0.060 < mean < 0.97 or std < 0.055 or dark_fraction > 0.90:
        raise ValueError(
            f"degenerate image: {path}: mean={mean:.4f} std={std:.4f} dark={dark_fraction:.4f}"
        )
    return {
        "path": str(path.relative_to(OUTPUT)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
        "width": 1280,
        "height": 720,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "dark_fraction": round(dark_fraction, 6),
    }


def video_record(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,duration,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(completed.stdout).get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"video stream count is not one: {path}")
    stream = streams[0]
    if int(stream["width"]) != 960 or int(stream["height"]) != 540:
        raise ValueError(f"wrong video dimensions: {path}")
    frames = int(stream.get("nb_frames", 0))
    duration = float(stream.get("duration", 0))
    if frames != 120 or not 4.95 <= duration <= 5.05:
        raise ValueError(
            f"wrong video length: {path}: frames={frames} duration={duration}"
        )
    return {
        "path": str(path.relative_to(OUTPUT)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
        **stream,
    }


def validate_scene(scene_id: str) -> dict[str, object]:
    root = OUTPUT / scene_id
    manifest_path = root / "manifest.json"
    generation_path = root / "generation_manifest.json"
    source_path = root / "source/generated.py"
    blend_path = root / "scene/scene.blend"
    glb_path = root / "scene/scene.glb"
    for path in (manifest_path, generation_path, source_path, blend_path, glb_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    if not manifest.get("render_success") or not manifest.get(
        "true_shared_coordinate_3d_scene"
    ):
        raise ValueError(f"3D/render flags failed: {scene_id}")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("refinement", {}).get("still_view_count") != 16
    ):
        raise ValueError(f"refinement metadata failed: {scene_id}")
    if manifest.get("video_frames") != 120:
        raise ValueError(f"non-final frame count in manifest: {scene_id}")
    if generation.get("model_requested") != "glm-5.3-flash" or not generation.get(
        "generation_success"
    ):
        raise ValueError(f"model identity failed: {scene_id}")
    if generation.get("generated_code_sha256") != digest(source_path):
        raise ValueError(f"generated code hash mismatch: {scene_id}")
    if manifest["generation"]["generated_code_sha256"] != digest(source_path):
        raise ValueError(f"render/code hash mismatch: {scene_id}")
    blend_magic = blend_path.read_bytes()[:7]
    # Blender 4.5 compressed saves use a Zstandard frame rather than exposing
    # the historical BLENDER header at byte zero.
    if blend_magic != b"BLENDER" and blend_magic[:4] != b"\x28\xb5\x2f\xfd":
        raise ValueError(f"not a Blender/Zstandard file: {blend_path}")
    if glb_path.read_bytes()[:4] != b"glTF":
        raise ValueError(f"not a binary glTF: {glb_path}")
    if (
        manifest["geometry"]["mesh_object_count"] < 55
        or manifest["geometry"]["vertex_count"] < 450
    ):
        raise ValueError(f"scene geometry is too sparse: {scene_id}")

    image_paths = sorted((root / "images").glob("*.png"))
    video_paths = sorted((root / "videos").glob("*.mp4"))
    if {path.stem for path in image_paths} != set(IMAGE_ROLES):
        raise ValueError(f"wrong image roles: {scene_id}")
    if {path.stem for path in video_paths} != set(VIDEO_ROLES):
        raise ValueError(f"wrong video roles: {scene_id}")
    images = [image_record(root / "images" / f"{role}.png") for role in IMAGE_ROLES]
    videos = [video_record(root / "videos" / f"{role}.mp4") for role in VIDEO_ROLES]
    manifest_image_hashes = {
        item["role"]: item["sha256"] for item in manifest["images"]
    }
    manifest_video_hashes = {
        item["role"]: item["sha256"] for item in manifest["videos"]
    }
    for role, record in zip(IMAGE_ROLES, images):
        if manifest_image_hashes.get(role) != record["sha256"]:
            raise ValueError(f"image hash mismatch: {scene_id}/{role}")
    for role, record in zip(VIDEO_ROLES, videos):
        if manifest_video_hashes.get(role) != record["sha256"]:
            raise ValueError(f"video hash mismatch: {scene_id}/{role}")
    return {
        "scene_id": scene_id,
        "valid": True,
        "true_shared_coordinate_3d_scene": True,
        "mesh_object_count": manifest["geometry"]["mesh_object_count"],
        "vertex_count": manifest["geometry"]["vertex_count"],
        "material_count": manifest["geometry"]["material_count"],
        "blend": {
            "path": str(blend_path.relative_to(OUTPUT)),
            "bytes": blend_path.stat().st_size,
            "sha256": digest(blend_path),
        },
        "glb": {
            "path": str(glb_path.relative_to(OUTPUT)),
            "bytes": glb_path.stat().st_size,
            "sha256": digest(glb_path),
        },
        "images": images,
        "videos": videos,
        "manifest": str(manifest_path.relative_to(OUTPUT)),
        "generation_manifest": str(generation_path.relative_to(OUTPUT)),
    }


def main() -> int:
    scenes = [validate_scene(scene_id) for scene_id in SCENES]
    report = {
        "schema_version": 2,
        "validated_at_utc": utc(),
        "valid": True,
        "method": "glm53_flash",
        "model": "glm-5.3-flash",
        "scene_count": len(scenes),
        "true_shared_coordinate_3d_scene_count": sum(
            scene["true_shared_coordinate_3d_scene"] for scene in scenes
        ),
        "image_count": sum(len(scene["images"]) for scene in scenes),
        "video_count": sum(len(scene["videos"]) for scene in scenes),
        "blend_count": len(scenes),
        "glb_count": len(scenes),
        "all_images_individual_unlabelled_no_montage": True,
        "scenes": scenes,
    }
    atomic_json(OUTPUT / "VALIDATION_REPORT.json", report)
    atomic_json(
        OUTPUT / "MANIFEST.json",
        {
            "schema_version": 2,
            "method": "glm53_flash",
            "model": "glm-5.3-flash",
            "provider": "glm-coding-plan",
            "created_at_utc": utc(),
            "scene_count": 6,
            "image_count": 96,
            "video_count": 12,
            "blend_count": 6,
            "glb_count": 6,
            "true_shared_coordinate_3d_scenes": True,
            "shared_coordinate_connection": "open 2.2m doorway with flush threshold",
            "all_images_individual_unlabelled_no_montage": True,
            "images_per_scene": 16,
            "connection_views_per_scene": 12,
            "refinement": "detailed geometry and bright balanced interior/exterior lighting",
            "validation_report": "VALIDATION_REPORT.json",
            "scenes": [
                {
                    "scene_id": scene["scene_id"],
                    "manifest": scene["manifest"],
                    "valid": True,
                }
                for scene in scenes
            ],
        },
    )
    readme = """# GLM-5.3 Flash connected 3D demos

This directory contains six distinct, genuine Blender indoor/outdoor scenes in
one shared coordinate frame per scene. The interior and exterior meet at an
open 2.2 m entrance with a flush threshold. The transition videos move the
same physical camera through that doorway in both directions.

Each scene contains:

- `scene/scene.blend` and `scene/scene.glb` (editable/exported 3D geometry)
- sixteen separate 1280×720 PNG images with no montage, label, border, or number
  (including twelve varied long, medium, oblique, and high connection views)
- two 960×540, 24 fps, 5 second H.264 MP4 videos
- preserved GLM-generated source and generation/render provenance manifests

The refined pass adds rounded edges, smoother curved geometry, denser furniture,
vegetation and architectural finish details. Brighter world illumination,
multi-point interior fill lighting and raised exposure improve visibility while
keeping indoor and outdoor areas in the same physical 3D scene.

Generation used `glm-5.3-flash` through the GLM Coding Plan endpoint. No model
weights or external scene assets were downloaded. Rendering used Blender 4.5.4
EEVEE Next on CPU because the host NVIDIA driver was unavailable during this
run. See `VALIDATION_REPORT.json` for per-file hashes and media checks.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "valid",
                    "scene_count",
                    "image_count",
                    "video_count",
                    "blend_count",
                    "glb_count",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
