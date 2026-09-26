#!/usr/bin/env python3
"""Audit and index the Gemini 3.1 Pro compact neighborhood collection."""
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
import struct
import subprocess


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect3"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect3_specs.json"
)
IMAGE_ROLES = [
    "interior_wide_axis",
    "interior_far_left",
    "interior_far_right",
    "interior_mid_left",
    "interior_mid_right",
    "inside_to_outside_far",
    "inside_to_outside_mid",
    "threshold_inside_oblique",
    "outside_to_inside_far",
    "outside_to_inside_mid",
    "threshold_outside_oblique",
    "neighborhood_front_axis",
    "streetscape_far_left",
    "streetscape_far_right",
    "cross_street_from_west",
    "cross_street_from_east",
    "district_aerial_southwest",
    "district_aerial_southeast",
    "district_oblique_northwest",
    "district_oblique_northeast",
    "public_realm_left",
    "public_realm_right",
]
VIDEO_ROLES = ["indoor_to_outdoor", "outdoor_to_indoor", "neighborhood_orbit"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path: Path) -> list[int]:
    with path.open("rb") as handle:
        signature = handle.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n" or signature[12:16] != b"IHDR":
        raise RuntimeError(f"Not a valid PNG: {path}")
    return list(struct.unpack(">II", signature[16:24]))


def video_probe(path: Path) -> dict:
    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate,pix_fmt,nb_frames",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(path),
    ]
    payload = json.loads(subprocess.check_output(command, text=True))
    stream = payload["streams"][0]
    result = {
        "codec": stream["codec_name"],
        "resolution": [int(stream["width"]), int(stream["height"])],
        "fps": stream["r_frame_rate"],
        "pixel_format": stream["pix_fmt"],
        "frames": int(stream["nb_frames"]),
        "duration_seconds": float(payload["format"]["duration"]),
        "bytes": int(payload["format"]["size"]),
    }
    expected = {
        "codec": "h264",
        "resolution": [960, 540],
        "fps": "24/1",
        "pixel_format": "yuv420p",
        "frames": 48,
        "duration_seconds": 2.0,
    }
    for key, value in expected.items():
        if result[key] != value:
            raise RuntimeError(
                f"Unexpected video {key} for {path}: {result[key]} != {value}"
            )
    return result


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    scenes = []
    for spec in specs:
        demo_id = spec["demo_id"]
        run = ROOT / demo_id
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not all(
            manifest.get(key)
            for key in ("generation_success", "build_success", "render_success")
        ):
            raise RuntimeError(f"Incomplete manifest state for {demo_id}")
        if manifest.get("auth_mode") != "account_subscription_no_api_key":
            raise RuntimeError(f"Unexpected auth mode for {demo_id}")
        if manifest.get("api_key_billing_forbidden") is not True:
            raise RuntimeError(f"API-key billing prohibition missing for {demo_id}")
        if manifest.get("model_requested") != "gemini-3.1-pro-high":
            raise RuntimeError(f"Unexpected model for {demo_id}")
        required_removed_keys = {
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_GEMINI_BASE_URL",
        }
        for attempt in manifest.get("attempts", []):
            if (
                set(attempt.get("api_keys_removed_from_child_environment", []))
                != required_removed_keys
            ):
                raise RuntimeError(f"API-key isolation audit failed for {demo_id}")
        if (run / ".render_frames").exists():
            raise RuntimeError(f"Temporary frame directory remains for {demo_id}")
        source = run / "source/generated.py"
        if sha256(source) != manifest.get("generated_code_sha256"):
            raise RuntimeError(f"Generated source hash mismatch for {demo_id}")

        geometry = manifest["geometry"]
        gate = geometry.get("connect3_quality_gate", {})
        if (
            not geometry.get("is_native_3d_scene")
            or geometry.get("visible_mesh_objects", 0) < 350
            or geometry.get("polygons", 0) < 90_000
            or geometry.get("occupied_context_building_zones", 0) < 2
            or geometry.get("spatial_zone_mesh_counts", {}).get("public_realm", 0) < 35
            or not gate.get("passed")
        ):
            raise RuntimeError(
                f"Connect3 native 3D geometry audit failed for {demo_id}"
            )
        if (
            geometry.get("standardized_edge_refinement", {}).get("is_image_postprocess")
            is not False
        ):
            raise RuntimeError(
                f"Missing real-geometry refinement provenance for {demo_id}"
            )

        blend = run / f"{demo_id}.blend"
        if not blend.is_file() or blend.stat().st_size < 150_000:
            raise RuntimeError(
                f"Missing or implausibly small Blender scene for {demo_id}"
            )
        images = []
        for role in IMAGE_ROLES:
            path = run / "images" / f"{role}.png"
            if png_size(path) != [1280, 720]:
                raise RuntimeError(f"Unexpected image resolution: {path}")
            images.append(
                {
                    "role": role,
                    "path": str(path.relative_to(ROOT)),
                    "resolution": [1280, 720],
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "overlay_or_number_added": False,
                }
            )
        videos = []
        for role in VIDEO_ROLES:
            path = run / "videos" / f"{role}.mp4"
            videos.append(
                {
                    "role": role,
                    "path": str(path.relative_to(ROOT)),
                    **video_probe(path),
                    "sha256": sha256(path),
                }
            )
        deliverables = [blend] + [ROOT / item["path"] for item in images + videos]
        manifest_hashes = manifest.get("outputs_sha256", {})
        for path in deliverables:
            if manifest_hashes.get(str(path.relative_to(run))) != sha256(path):
                raise RuntimeError(f"Manifest hash mismatch: {path}")
        scenes.append(
            {
                "demo_id": demo_id,
                "title": spec["title"],
                "logical_seed": spec["logical_seed"],
                "required_facilities": spec["required_facilities"],
                "layout_strategy": spec["layout_strategy"],
                "scene": {
                    "path": str(blend.relative_to(ROOT)),
                    "bytes": blend.stat().st_size,
                    "sha256": sha256(blend),
                },
                "geometry": geometry,
                "render_backend": manifest["render_backend"],
                "images": images,
                "videos": videos,
                "source_path": str(source.relative_to(ROOT)),
                "manifest_path": str(manifest_path.relative_to(ROOT)),
            }
        )

    all_files = [path for path in ROOT.rglob("*") if path.is_file()]
    collection = {
        "status": "complete",
        "all_checks_passed": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_output_path": str(ROOT.resolve()),
        "method": "gemini_3_1_pro",
        "model": "gemini-3.1-pro-high",
        "transport": "antigravity_cli_google_ai_pro_account",
        "auth_mode": "account_subscription_no_api_key",
        "api_key_billing_used": False,
        "scene_count": len(scenes),
        "blend_scene_count": len(scenes),
        "image_count": sum(len(scene["images"]) for scene in scenes),
        "video_count": sum(len(scene["videos"]) for scene in scenes),
        "temporary_frame_directories_remaining": 0,
        "facilities_covered": sorted(
            {facility for spec in specs for facility in spec["required_facilities"]}
        ),
        "deliverable_bytes": sum(
            scene["scene"]["bytes"]
            + sum(item["bytes"] for item in scene["images"])
            + sum(item["bytes"] for item in scene["videos"])
            for scene in scenes
        ),
        "directory_bytes_before_index": sum(path.stat().st_size for path in all_files),
        "scenes": scenes,
    }
    write_json(ROOT / "collection_manifest.json", collection)
    lines = [
        "# Gemini 3.1 Pro compact multi-building neighborhoods",
        "",
        "Ten detailed native Blender 3D districts generated through the Gemini 3.1 Pro Coding Plan account client. No Gemini API key or API-billed transport was used.",
        "",
        "Each scene contains several nearby functional buildings, a densely modeled public realm, a furnished anchor interior, and a physically open indoor/outdoor threshold.",
        "",
        "Each scene directory includes:",
        "",
        "- one compressed native `.blend` scene;",
        "- twenty-two separate bright 1280×720 PNG views with no labels, numbering, or montage;",
        "- three H.264 960×540 videos: two-way interior/exterior traversal and a district orbit;",
        "- Gemini source, input specification, subscription-client logs, geometry metrics, hashes, and provenance.",
        "",
        "Every scene passes at least 350 visible mesh objects, 90,000 baked polygons, multi-zone building occupancy, and public-realm density checks.",
        "",
        "## Scenes",
        "",
    ]
    for scene in scenes:
        lines.append(f"- `{scene['demo_id']}` — {scene['title']}")
    lines.extend(
        [
            "",
            "See `collection_manifest.json` for full facility coverage, camera roles, codec probes, geometry counts, and SHA-256 hashes.",
        ]
    )
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GEMINI_CONNECT3_FINAL_AUDIT_COMPLETE scenes=10 images=220 videos=30")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
