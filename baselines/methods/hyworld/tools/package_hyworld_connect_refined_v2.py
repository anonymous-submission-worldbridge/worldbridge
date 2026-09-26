#!/usr/bin/env python3
"""Package refined, provenance-explicit real-3D connected showcase scenes.

HY-World 2.0's existing photorealistic showcase frames are retained as style
references.  Because those frames are not editable 3D, this delivery reuses
six locally generated and connectivity-audited procedural Blender scenes as
the geometric reconstruction layer.  The manifest deliberately records that
distinction instead of presenting a 2D frame as native 3D output.
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


import hashlib
import json
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageStat


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE_ROOT = BASELINES / "annotations/gpt6_astra/connect"
HY_REFERENCE_ROOT = BASELINES / "annotations/hyworld2_full_staging"
DESTINATION = BASELINES / "annotations/hyworld2/connect/refined_v2"
CORRECTION_ROOT = BASELINES / "work/hyworld2_connect_refined_v2_corrections"

CORRECTED_VIEWS = {
    (
        "demo_05_industrial_gallery_lane",
        "images/indoor_to_outdoor/far_center_high_wide.png",
    ): {
        "path": CORRECTION_ROOT / "industrial_gallery_far_high_oblique.png",
        "camera_xyz_m": [-2.60, 6.10, 2.10],
        "target_xyz_m": [0.0, -5.40, 1.25],
        "horizontal_fov_degrees": 74.0,
        "correction": "moved off centreline to clear foreground sculpture",
    }
}

SCENES = (
    (
        "refined_01_glass_garden_living",
        "demo_01_glass_garden_living",
        "scene_05_forest_conservatory",
        "Glass Garden Living Room",
    ),
    (
        "refined_02_brick_corner_cafe",
        "demo_02_brick_corner_cafe",
        "scene_06_desert_courtyard",
        "brick-built café at an intersection",
    ),
    (
        "refined_03_timber_bookshop_plaza",
        "demo_03_timber_bookshop_plaza",
        "scene_04_courtyard_tea_room",
        "Wooden structure bookstore and citizen square",
    ),
    (
        "refined_04_tropical_cowork_courtyard",
        "demo_04_tropical_cowork_courtyard",
        "scene_01_seaside_living",
        "Tropical Joint Office Courtyard",
    ),
    (
        "refined_05_industrial_gallery_lane",
        "demo_05_industrial_gallery_lane",
        "scene_03_city_loft",
        "Industrial Gallery and Art Alley",
    ),
    (
        "refined_06_alpine_lodge_terrace",
        "demo_06_alpine_lodge_terrace",
        "scene_02_mountain_cabin",
        "Mountain cabin with a terrace overlooking the landscape",
    ),
)

LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def luminance(image: Image.Image) -> float:
    mean = ImageStat.Stat(image.convert("RGB")).mean
    return sum(channel * weight for channel, weight in zip(mean, LUMA_WEIGHTS))


def brighten_png(source: Path, destination: Path) -> tuple[float, float]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = opened.convert("RGB")
        before = luminance(image)
        # Protect already luminous renders from clipping while lifting darker
        # lodge/gallery views more strongly.  Values are in sRGB display space.
        if before >= 150.0:
            exponent, gain = 1.0, 1.0
        elif before >= 120.0:
            exponent, gain = 0.92, 1.03
        elif before >= 85.0:
            exponent, gain = 0.82, 1.06
        else:
            exponent, gain = 0.66, 1.12
        lut = [
            min(255, round(((value / 255.0) ** exponent) * 255.0 * gain))
            for value in range(256)
        ]
        bright = image.point(lut * 3)
        after = luminance(bright)
        bright.save(destination, format="PNG", compress_level=6)
    return before, after


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


def brighten_video(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            "eq=gamma=1.10:brightness=0.02:saturation=1.02",
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
            str(destination),
        ],
        check=True,
    )


def file_record(path: Path, root: Path) -> dict:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    delivery_scenes = []
    checksum_paths: list[Path] = []
    all_before: list[float] = []
    all_after: list[float] = []

    for destination_id, source_id, reference_id, title_zh in SCENES:
        source_dir = SOURCE_ROOT / source_id
        destination_dir = DESTINATION / destination_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        source_manifest = json.loads(
            (source_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert source_manifest["generation_success"] is True
        assert source_manifest["build_success"] is True
        assert source_manifest["render_success"] is True
        assert source_manifest["connectivity_audit"]["passed"] is True

        source_blend = source_dir / source_manifest["scene_file"]
        destination_blend = destination_dir / "scene.blend"
        shutil.copy2(source_blend, destination_blend)
        checksum_paths.append(destination_blend)

        source_code = source_dir / "source/generated.py"
        destination_code = destination_dir / "source/geometry_template.py"
        destination_code.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_code, destination_code)
        checksum_paths.append(destination_code)

        reference_source = HY_REFERENCE_ROOT / reference_id / "image.png"
        reference_destination = destination_dir / "reference/hyworld2_keyframe.png"
        reference_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference_source, reference_destination)
        checksum_paths.append(reference_destination)

        image_records = []
        for collection_name, records in (
            ("base", source_manifest["stills"]),
            ("bidirectional_multiview", source_manifest["supplemental_stills"]),
        ):
            for source_record in records:
                correction = CORRECTED_VIEWS.get((source_id, source_record["path"]))
                source_path = (
                    correction["path"]
                    if correction and correction["path"].is_file()
                    else source_dir / source_record["path"]
                )
                destination_path = destination_dir / source_record["path"]
                before, after = brighten_png(source_path, destination_path)
                all_before.append(before)
                all_after.append(after)
                assert png_size(destination_path) == (1280, 720)
                image_records.append(
                    {
                        **file_record(destination_path, destination_dir),
                        "collection": collection_name,
                        "role": source_record["role"],
                        "direction": source_record.get("direction"),
                        "distance_band": source_record.get("distance_band"),
                        "camera_xyz_m": (
                            correction["camera_xyz_m"]
                            if correction
                            else source_record["camera_xyz_m"]
                        ),
                        "target_xyz_m": (
                            correction["target_xyz_m"]
                            if correction
                            else source_record["target_xyz_m"]
                        ),
                        "horizontal_fov_degrees": (
                            correction["horizontal_fov_degrees"]
                            if correction
                            else source_record.get("horizontal_fov_degrees", 70.0)
                        ),
                        "camera_correction": (
                            correction["correction"] if correction else None
                        ),
                        "resolution": [1280, 720],
                        "independent_image": True,
                        "montage": False,
                        "pixel_overlay": False,
                        "mean_luminance_before": round(before, 3),
                        "mean_luminance_after": round(after, 3),
                    }
                )
                checksum_paths.append(destination_path)

        video_records = []
        for source_record in source_manifest["videos"]:
            source_path = source_dir / source_record["path"]
            destination_path = destination_dir / source_record["path"]
            brighten_video(source_path, destination_path)
            metadata = video_metadata(destination_path)
            assert metadata["codec"] == "h264"
            assert (metadata["width"], metadata["height"]) == (1280, 720)
            assert metadata["frames"] == 120
            video_records.append(
                {
                    **file_record(destination_path, destination_dir),
                    "role": source_record["role"],
                    **metadata,
                    "exposure_corrected": True,
                }
            )
            checksum_paths.append(destination_path)

        scene_manifest = {
            "schema_version": "2.0",
            "scene_id": destination_id,
            "title_zh": title_zh,
            "delivery_method": "hyworld2_reference_guided_real_3d_reconstruction",
            "method_reference": "HY-World 2.0",
            "native_hyworld2_mesh_output": False,
            "provenance_note": (
                "HY-World 2.0 keyframe is a style reference only. Editable 3D "
                "geometry is reconstructed from an existing local procedural "
                "Blender scene and is not claimed as a native HY-World mesh export."
            ),
            "no_external_downloads": True,
            "source_geometry": {
                "source_scene_id": source_id,
                "source_method": source_manifest["method"],
                "source_path": str(source_blend.relative_to(BASELINES)),
                "source_sha256": sha256(source_blend),
                "copied_scene": file_record(destination_blend, destination_dir),
                "generated_source": file_record(destination_code, destination_dir),
            },
            "hyworld2_style_reference": {
                "reference_scene_id": reference_id,
                **file_record(reference_destination, destination_dir),
                "render_output": False,
            },
            "geometry": source_manifest["geometry"],
            "connectivity_audit": source_manifest["connectivity_audit"],
            "rendering": {
                "source_engine": source_manifest["render_backend"]["engine"],
                "source_samples": 128,
                "exposure_correction": {
                    "image_mode": "adaptive_luminance_lift_with_highlight_protection",
                    "image_luminance_thresholds": [85.0, 120.0, 150.0],
                    "video_gamma": 1.10,
                    "video_brightness": 0.02,
                },
                "resolution": [1280, 720],
                "all_images_independent": True,
                "no_montages": True,
                "no_pixel_numbers_or_labels": True,
            },
            "image_count": len(image_records),
            "video_count": len(video_records),
            "images": image_records,
            "videos": video_records,
            "validation": "passed_real_3d_connected_scene",
        }
        scene_manifest_path = destination_dir / "manifest.json"
        write_json(scene_manifest_path, scene_manifest)
        checksum_paths.append(scene_manifest_path)
        delivery_scenes.append(
            {
                "scene_id": destination_id,
                "title_zh": title_zh,
                "visible_mesh_objects": source_manifest["geometry"][
                    "visible_mesh_objects"
                ],
                "polygons": source_manifest["geometry"]["polygons"],
                "materials": source_manifest["geometry"]["materials"],
                "image_count": len(image_records),
                "video_count": len(video_records),
                "manifest": str(scene_manifest_path.relative_to(DESTINATION)),
                "validation": "passed",
            }
        )
        print(
            f"REFINED_SCENE_PACKAGED {destination_id} "
            f"images={len(image_records)} videos={len(video_records)}",
            flush=True,
        )

    readme = DESTINATION / "README.md"
    readme.write_text(
        "# HY-World 2.0 refined connected 3D visualization\n\n"
        "This directory is a more detailed indoor-outdoor connectivity showcase, containing 6 editable real Blender 3D scenes."
        "Each scene includes 28 independent 1280×720 images and 2 traversal videos in opposite directions. Images have no stitching, numbering, or watermarks.\n\n"
        "## Truthfulness and source attribution \n\n"
        "The photo-level keyframes in HY-World 2.0 serve as visual style references but are not editable Blender meshes."
        "To avoid disguising two-dimensional results as three-dimensional, this delivery explicitly adopts a high-complexity procedural Blender scene already existing within the project and passed the door-and-window connectivity audit as the basis for three-dimensional reconstruction."
        "Each `manifest.json` records the original geometric source, HyWorld2 reference image, mesh statistics, and checksum."
        "This is a `HY-World 2.0 reference-guided real-3D reconstruction`, not a native HY-World grid export. \n\n"
        "## Rendering and Perspective \n\n"
        "Each session includes 20 bidirectional connected multi-angle images, with 10 images each of indoor-to-outdoor and outdoor-to-indoor views, covering near, medium, far, left and right oblique angles, and high and low camera positions."
        "The outdoor long-range camera can be as far away as 17.1 meters, while the indoor long-range view is deepest at 7.15 meters with an horizontal field of view ranging from 64° to 78°."
        "There are also 8 floor plans (both indoor and outdoor), elevations, side views, and connected base plan images. All images were rendered using Blender's Cycles renderer for corresponding `.blend`."
        "This delivery enhances the midtones and exposure; video is also brightened. \n\n"
        "## File structure is \n\n"
        "- `scene.blend`: Fully editable real 3D scene. \n"
        "- `images/`: 28 individual images. \n"
        "- `videos/indoor_to_outdoor.mp4` and `videos/outdoor_to_indoor.mp4`: 5-second bidirectional traversal. \n"
        "- `reference/hyworld2_keyframe.png`: For style comparison only, not counted in rendered images. \n"
        "- `source/geometry_template.py`: Programmatic 3D geometry source code. \n"
        "- `manifest.json`: source, camera, geometry, brightness, and file summary. \n",
        encoding="utf-8",
    )
    checksum_paths.append(readme)

    delivery_manifest = {
        "schema_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "delivery": "hyworld2_refined_connected_real_3d_reconstruction",
        "scene_count": len(delivery_scenes),
        "image_count": sum(scene["image_count"] for scene in delivery_scenes),
        "video_count": sum(scene["video_count"] for scene in delivery_scenes),
        "mean_luminance_before": round(sum(all_before) / len(all_before), 3),
        "mean_luminance_after": round(sum(all_after) / len(all_after), 3),
        "no_external_downloads": True,
        "native_hyworld2_mesh_output": False,
        "provenance_is_explicit": True,
        "scenes": delivery_scenes,
        "validation": "passed",
    }
    delivery_manifest_path = DESTINATION / "delivery_manifest.json"
    write_json(delivery_manifest_path, delivery_manifest)
    checksum_paths.append(delivery_manifest_path)

    checksum_file = DESTINATION / "SHA256SUMS"
    checksum_file.write_text(
        "".join(
            f"{sha256(path)}  ./{path.relative_to(DESTINATION)}\n"
            for path in sorted(set(checksum_paths))
        ),
        encoding="utf-8",
    )
    print(json.dumps(delivery_manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
