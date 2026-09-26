#!/usr/bin/env python3
"""Validate and index the dense eight-scene GLM connect3 deliverable."""

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


import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.validate_glm_flash_connect as base


OUTPUT = base.BASELINES / "annotations/glm53_flash/connect3"
SCENES = (
    "rowhouse_living_dining",
    "apartment_kitchen_balcony",
    "suburban_family_room",
    "duplex_home_office_lounge",
    "neighborhood_pharmacy",
    "local_grocery_market",
    "casual_family_restaurant",
    "hardware_home_store",
)
IMAGE_ROLES = (
    "indoor_overview",
    "indoor_overview_rear",
    "indoor_detail_left",
    "indoor_detail_right",
    "inside_to_outside_rear_center",
    "inside_to_outside_rear_left",
    "inside_to_outside_rear_right",
    "inside_to_outside_mid_center",
    "inside_to_outside_mid_left",
    "inside_to_outside_mid_right",
    "inside_to_outside_high",
    "inside_to_outside_entry_oblique",
    "outdoor_overview_high",
    "outdoor_streetscape_left",
    "outdoor_streetscape_right",
    "outdoor_entry_context",
    "outside_to_inside_street_center",
    "outside_to_inside_street_left",
    "outside_to_inside_street_right",
    "outside_to_inside_context_high",
    "outside_to_inside_mid_center",
    "outside_to_inside_mid_left",
    "outside_to_inside_mid_right",
    "outside_to_inside_entry_oblique",
)


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
    if frames != 48 or not 1.95 <= duration <= 2.05:
        raise ValueError(
            f"wrong video length: {path}: frames={frames} duration={duration}"
        )
    return {
        "path": str(path.relative_to(OUTPUT)),
        "bytes": path.stat().st_size,
        "sha256": base.digest(path),
        **stream,
    }


def validate_scene(scene_id: str) -> dict[str, object]:
    root = OUTPUT / scene_id
    paths = {
        "manifest": root / "manifest.json",
        "generation": root / "generation_manifest.json",
        "source": root / "source/generated.py",
        "blend": root / "scene/scene.blend",
        "glb": root / "scene/scene.glb",
    }
    for path in paths.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    generation = json.loads(paths["generation"].read_text(encoding="utf-8"))
    refinement = manifest.get("refinement", {})
    connectivity = manifest.get("connectivity", {})
    if manifest.get("schema_version") != 2 or not manifest.get("render_success"):
        raise ValueError(f"render manifest failed: {scene_id}")
    if not manifest.get("true_shared_coordinate_3d_scene") or not manifest.get(
        "native_geometry"
    ):
        raise ValueError(f"native shared-coordinate 3D flags failed: {scene_id}")
    if (
        refinement.get("still_view_count") != 24
        or refinement.get("connection_view_count") != 16
    ):
        raise ValueError(f"view-count metadata failed: {scene_id}")
    if not refinement.get("dense_surrounding_buildings") or not refinement.get(
        "empty_exterior_horizon_avoided"
    ):
        raise ValueError(f"dense-context metadata failed: {scene_id}")
    if not connectivity.get(
        "indoor_views_include_interior_overview_and_exterior_depth"
    ):
        raise ValueError(f"indoor-to-outdoor coverage metadata failed: {scene_id}")
    if not connectivity.get(
        "outdoor_views_include_streetscape_context_and_interior_depth"
    ):
        raise ValueError(f"outdoor-to-indoor coverage metadata failed: {scene_id}")
    if manifest.get("video_frames") != 48:
        raise ValueError(f"non-final frame count: {scene_id}")

    if generation.get("model_requested") != "glm-5.3-flash" or not generation.get(
        "generation_success"
    ):
        raise ValueError(f"GLM generation identity failed: {scene_id}")
    source_hash = base.digest(paths["source"])
    if generation.get("generated_code_sha256") != source_hash:
        raise ValueError(f"generation/source hash mismatch: {scene_id}")
    if manifest.get("generation", {}).get("generated_code_sha256") != source_hash:
        raise ValueError(f"render/source hash mismatch: {scene_id}")
    if generation.get("secret_persisted") is not False:
        raise ValueError(f"secret-persistence assertion failed: {scene_id}")

    blend_magic = paths["blend"].read_bytes()[:7]
    if blend_magic != b"BLENDER" and blend_magic[:4] != b"\x28\xb5\x2f\xfd":
        raise ValueError(f"invalid Blender file: {paths['blend']}")
    if paths["glb"].read_bytes()[:4] != b"glTF":
        raise ValueError(f"invalid GLB file: {paths['glb']}")
    geometry = manifest.get("geometry", {})
    if (
        geometry.get("mesh_object_count", 0) < 1_000
        or geometry.get("vertex_count", 0) < 6_000
    ):
        raise ValueError(f"scene geometry too sparse: {scene_id}")

    image_paths = sorted((root / "images").glob("*.png"))
    video_paths = sorted((root / "videos").glob("*.mp4"))
    if {path.stem for path in image_paths} != set(IMAGE_ROLES):
        raise ValueError(f"wrong image roles: {scene_id}")
    if {path.stem for path in video_paths} != set(base.VIDEO_ROLES):
        raise ValueError(f"wrong video roles: {scene_id}")
    images = [
        base.image_record(root / "images" / f"{role}.png") for role in IMAGE_ROLES
    ]
    videos = [
        video_record(root / "videos" / f"{role}.mp4") for role in base.VIDEO_ROLES
    ]
    manifest_images = {
        item["role"]: item["sha256"] for item in manifest.get("images", [])
    }
    manifest_videos = {
        item["role"]: item["sha256"] for item in manifest.get("videos", [])
    }
    for role, record in zip(IMAGE_ROLES, images):
        if manifest_images.get(role) != record["sha256"]:
            raise ValueError(f"image hash mismatch: {scene_id}/{role}")
    for role, record in zip(base.VIDEO_ROLES, videos):
        if manifest_videos.get(role) != record["sha256"]:
            raise ValueError(f"video hash mismatch: {scene_id}/{role}")

    return {
        "scene_id": scene_id,
        "valid": True,
        "true_shared_coordinate_3d_scene": True,
        "mesh_object_count": geometry["mesh_object_count"],
        "vertex_count": geometry["vertex_count"],
        "material_count": geometry["material_count"],
        "blend": {
            "path": str(paths["blend"].relative_to(OUTPUT)),
            "bytes": paths["blend"].stat().st_size,
            "sha256": base.digest(paths["blend"]),
        },
        "glb": {
            "path": str(paths["glb"].relative_to(OUTPUT)),
            "bytes": paths["glb"].stat().st_size,
            "sha256": base.digest(paths["glb"]),
        },
        "images": images,
        "videos": videos,
        "manifest": str(paths["manifest"].relative_to(OUTPUT)),
        "generation_manifest": str(paths["generation"].relative_to(OUTPUT)),
    }


def main() -> int:
    base.OUTPUT = OUTPUT
    scenes = [validate_scene(scene_id) for scene_id in SCENES]
    report = {
        "schema_version": 3,
        "validated_at_utc": base.utc(),
        "valid": True,
        "method": "glm53_flash",
        "model": "glm-5.3-flash",
        "scene_count": 8,
        "true_shared_coordinate_3d_scene_count": 8,
        "image_count": 192,
        "video_count": 16,
        "blend_count": 8,
        "glb_count": 8,
        "images_per_scene": 24,
        "connection_views_per_scene": 16,
        "all_images_individual_unlabelled_no_montage": True,
        "dense_surrounding_buildings": True,
        "scenes": scenes,
    }
    base.atomic_json(OUTPUT / "VALIDATION_REPORT.json", report)
    base.atomic_json(
        OUTPUT / "MANIFEST.json",
        {
            "schema_version": 3,
            "method": "glm53_flash",
            "model": "glm-5.3-flash",
            "provider": "glm-coding-plan",
            "created_at_utc": base.utc(),
            "scene_count": 8,
            "image_count": 192,
            "video_count": 16,
            "blend_count": 8,
            "glb_count": 8,
            "true_shared_coordinate_3d_scenes": True,
            "shared_coordinate_connection": "open 2.2m entrance in one indoor/outdoor coordinate frame",
            "all_images_individual_unlabelled_no_montage": True,
            "images_per_scene": 24,
            "connection_views_per_scene": 16,
            "context": "dense neighborhood with at least seven deterministic surrounding buildings plus GLM-planned context",
            "refinement": "high-density ordinary residential/retail geometry with bright balanced lighting",
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
    readme = """# GLM-5.3 Flash connect3: dense ordinary residential and retail scenes

This directory contains eight genuine Blender 3D indoor/outdoor environments,
each built in one shared coordinate frame with a physically open 2.2 m entrance.
The set contains four ordinary homes and four neighborhood shops/restaurants.

Each scene includes an editable compressed `scene/scene.blend`, an exported
`scene/scene.glb`, 24 separate unlabelled 1280x720 PNG images, and two 960x540
H.264 videos. Sixteen stills per scene cover the connection in both directions:
far, middle, lateral, oblique and elevated indoor-to-outdoor and
outdoor-to-indoor views. No montage, embedded label, border or number is used.

Interiors use multi-part furniture, built-ins, stocked shelving, lighting,
plants, trim and small accessories. Exterior views are enclosed by a two-storey
main facade, sidewalks, roads, trees, lamps, parked vehicles and multiple
detailed neighboring buildings; blank exterior horizons are intentionally
avoided.

Scene blueprints were produced by `glm-5.3-flash` through the GLM Coding Plan
endpoint. The API secret was process-only and is not stored. No model weights,
textures or external scene assets were downloaded. See `VALIDATION_REPORT.json`
for file hashes, media probes, image statistics and per-scene geometry counts.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    print(
        json.dumps(
            {
                "valid": True,
                "scene_count": 8,
                "image_count": 192,
                "video_count": 16,
                "blend_count": 8,
                "glb_count": 8,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
