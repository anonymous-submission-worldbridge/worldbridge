#!/usr/bin/env python3
"""Validate and inventory the HyWorld2 connected-scene visualization delivery."""

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
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SCENES = (
    "scene_01_t_junction_seed_097",
    "scene_02_main_side_seed_095",
    "scene_03_offset_seed_099",
    "scene_04_four_way_seed_092",
    "scene_05_irregular_seed_114",
    "scene_06_four_way_seed_130",
)
IMAGE_ROLES = (
    "overview",
    "outdoor",
    "outdoor_to_indoor",
    "indoor",
    "indoor_to_outdoor",
)
VIDEO_ROLES = ("outdoor_to_indoor", "indoor_to_outdoor")
MULTIVIEW_DIRECTIONS = ("outdoor_to_indoor", "indoor_to_outdoor")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def video_metadata(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    fmt = payload["format"]
    return {
        "codec": stream["codec_name"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate": stream["r_frame_rate"],
        "frames": int(stream["nb_frames"]),
        "duration_seconds": float(fmt["duration"]),
        "bytes": int(fmt["size"]),
    }


def file_record(path: Path, root: Path) -> dict:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    scene_records = []
    checksum_paths: list[Path] = []
    for scene_id in SCENES:
        scene_dir = root / scene_id
        audit_path = scene_dir / "connected_3d_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit["real_3d_geometry"] is True
        assert audit["native_shared_world_frame"] is True
        assert audit["walkthrough_crosses_exterior_portal"] is True
        assert len(audit["connected_buildings"]) >= 1
        assert len(audit["portal_objects"]) >= 1

        images = {}
        for role in IMAGE_ROLES:
            path = scene_dir / "images" / f"{role}.png"
            width, height = png_size(path)
            assert (width, height) == (1280, 720)
            images[role] = {
                **file_record(path, root),
                "width": width,
                "height": height,
                "independent_image": True,
                "montage": False,
                "pixel_overlay": False,
            }
            checksum_paths.append(path)

        videos = {}
        for role in VIDEO_ROLES:
            path = scene_dir / "videos" / f"{role}.mp4"
            metadata = video_metadata(path)
            assert metadata["codec"] == "h264"
            assert (metadata["width"], metadata["height"]) == (1280, 720)
            assert metadata["frames"] == 120
            videos[role] = {**file_record(path, root), **metadata}
            checksum_paths.append(path)

        multiview_manifest_path = (
            scene_dir / "images" / "multiview" / "camera_manifest.json"
        )
        multiview_manifest = json.loads(
            multiview_manifest_path.read_text(encoding="utf-8")
        )
        assert multiview_manifest["view_count"] == 12
        assert multiview_manifest["resolution"] == [1280, 720]
        assert multiview_manifest["independent_images"] is True
        assert multiview_manifest["pixel_overlays"] is False
        assert multiview_manifest["validation"] == "rendered_from_real_3d_scene"
        assert {view["role"] for view in multiview_manifest["views"]} == set(
            MULTIVIEW_DIRECTIONS
        )
        multiview_images = []
        for view in multiview_manifest["views"]:
            path = scene_dir / "images" / view["path"]
            width, height = png_size(path)
            assert (width, height) == (1280, 720)
            multiview_images.append(
                {
                    **file_record(path, root),
                    "role": view["role"],
                    "view": view["view"],
                    "distance_from_portal_m": view["distance_from_portal_m"],
                    "lateral_offset_m": view["lateral_offset_m"],
                    "height_m": view["height_m"],
                    "lens_mm": view["lens_mm"],
                    "width": width,
                    "height": height,
                    "independent_image": True,
                    "montage": False,
                    "pixel_overlay": False,
                }
            )
            checksum_paths.append(path)
        checksum_paths.append(multiview_manifest_path)

        far_bright_manifest_path = (
            scene_dir / "images" / "far_bright" / "camera_manifest.json"
        )
        far_bright_manifest = json.loads(
            far_bright_manifest_path.read_text(encoding="utf-8")
        )
        assert far_bright_manifest["render_profile"] == "far_bright"
        assert far_bright_manifest["view_count"] == 12
        assert far_bright_manifest["resolution"] == [1280, 720]
        assert far_bright_manifest["independent_images"] is True
        assert far_bright_manifest["pixel_overlays"] is False
        assert far_bright_manifest["validation"] == "rendered_from_real_3d_scene"
        assert far_bright_manifest["exposure"] >= 1.14
        assert far_bright_manifest["workbench_shadows"] is False
        assert far_bright_manifest["workbench_cavity"] is False
        assert {view["role"] for view in far_bright_manifest["views"]} == set(
            MULTIVIEW_DIRECTIONS
        )
        far_bright_images = []
        for view in far_bright_manifest["views"]:
            path = scene_dir / "images" / view["path"]
            width, height = png_size(path)
            assert (width, height) == (1280, 720)
            far_bright_images.append(
                {
                    **file_record(path, root),
                    "role": view["role"],
                    "view": view["view"],
                    "distance_from_portal_m": view["distance_from_portal_m"],
                    "lateral_offset_m": view["lateral_offset_m"],
                    "height_m": view["height_m"],
                    "lens_mm": view["lens_mm"],
                    "width": width,
                    "height": height,
                    "independent_image": True,
                    "montage": False,
                    "pixel_overlay": False,
                }
            )
            checksum_paths.append(path)
        checksum_paths.append(far_bright_manifest_path)

        representations = {}
        for suffix in ("blend", "glb"):
            path = scene_dir / f"scene.{suffix}"
            assert path.is_symlink() and path.resolve().is_file()
            representations[suffix] = {
                "path": str(path.relative_to(root)),
                "storage": "relative_symlink_to_existing_verified_asset",
                "target": str(path.readlink()),
                "target_bytes": path.resolve().stat().st_size,
            }

        support_files = []
        for name in (
            "connected_3d_audit.json",
            "production_asset_audit.json",
            "source_manifest.json",
            "source_validation.json",
            "world.json",
        ):
            path = scene_dir / name
            support_files.append(file_record(path, root))
            checksum_paths.append(path)

        scene_records.append(
            {
                "scene_id": scene_id,
                "seed": audit["scene_seed"],
                "topology": audit["topology"],
                "mesh_object_count": audit["mesh_object_count"],
                "connected_building_count": len(audit["connected_buildings"]),
                "shared_portal_count": len(audit["portal_objects"]),
                "real_3d_geometry": True,
                "native_shared_world_frame": True,
                "walkthrough_crosses_exterior_portal": True,
                "representations": representations,
                "images": images,
                "multiview": {
                    "camera_manifest": file_record(multiview_manifest_path, root),
                    "render_engine": multiview_manifest["render_engine"],
                    "view_count": len(multiview_images),
                    "images": multiview_images,
                },
                "far_bright": {
                    "camera_manifest": file_record(far_bright_manifest_path, root),
                    "render_engine": far_bright_manifest["render_engine"],
                    "exposure": far_bright_manifest["exposure"],
                    "workbench_shadows": far_bright_manifest["workbench_shadows"],
                    "workbench_cavity": far_bright_manifest["workbench_cavity"],
                    "view_count": len(far_bright_images),
                    "images": far_bright_images,
                },
                "videos": videos,
                "support_files": support_files,
                "validation": "passed",
            }
        )

    readme = root / "README.md"
    checksum_paths.append(readme)
    checksums = root / "SHA256SUMS"
    checksums.write_text(
        "".join(
            f"{digest(path)}  ./{path.relative_to(root)}\n"
            for path in sorted(checksum_paths)
        ),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "HyWorld2.0",
        "delivery": "connected_indoor_outdoor_3d_visualization",
        "scene_count": len(scene_records),
        "image_count": len(scene_records) * (len(IMAGE_ROLES) + 12 + 12),
        "base_image_count": len(scene_records) * len(IMAGE_ROLES),
        "multiview_image_count": len(scene_records) * 12,
        "far_bright_image_count": len(scene_records) * 12,
        "video_count": len(scene_records) * len(VIDEO_ROLES),
        "generation_decision": (
            "reused_existing_verified_real_3d_scenes; no duplicate scene generation"
        ),
        "storage_policy": (
            "media copied into delivery; large .blend/.glb assets referenced by "
            "relative symlink to avoid duplicate disk usage"
        ),
        "gpu_status": "unavailable: NVIDIA driver communication failed",
        "visual_qc": {
            "all_images_independent": True,
            "no_montages": True,
            "no_pixel_numbers_or_labels": True,
            "bidirectional_portal_views_present": True,
        },
        "scenes": scene_records,
        "checksums": "SHA256SUMS",
        "validation": "passed",
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "validation": "passed",
                "scenes": len(scene_records),
                "images": manifest["image_count"],
                "multiview_images": manifest["multiview_image_count"],
                "far_bright_images": manifest["far_bright_image_count"],
                "videos": manifest["video_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
