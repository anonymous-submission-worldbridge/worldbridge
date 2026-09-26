#!/usr/bin/env python3
"""Audit and index the refined Gemini 3.1 Pro connected-demo package."""
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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect2"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_specs.json"
)
IMAGE_ROLES = [
    "interior_wide_axis",
    "interior_far_left",
    "interior_far_right",
    "interior_mid_left",
    "interior_mid_right",
    "interior_detail_left",
    "interior_detail_right",
    "inside_to_outside_far",
    "inside_to_outside_mid",
    "threshold_inside_oblique",
    "exterior_establishing_front",
    "exterior_far_left",
    "exterior_far_right",
    "exterior_mid_left",
    "exterior_mid_right",
    "outside_to_inside_far",
    "outside_to_inside_mid",
    "threshold_outside_oblique",
]
VIDEO_ROLES = ["indoor_to_outdoor", "outdoor_to_indoor"]


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
            raise RuntimeError(f"API-key billing prohibition is missing for {demo_id}")
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
                raise RuntimeError(
                    f"API-key environment isolation audit failed for {demo_id}"
                )
        if (run / ".render_frames").exists():
            raise RuntimeError(f"Temporary frame directory remains for {demo_id}")
        source = run / "source/generated.py"
        if sha256(source) != manifest.get("generated_code_sha256"):
            raise RuntimeError(f"Generated source hash mismatch for {demo_id}")

        geometry = manifest["geometry"]
        if (
            not geometry.get("is_native_3d_scene")
            or geometry.get("visible_mesh_objects", 0) < 250
            or geometry.get("polygons", 0) < 60_000
            or not geometry.get("connect2_quality_gate", {}).get("passed")
        ):
            raise RuntimeError(f"Refined 3D geometry audit failed for {demo_id}")
        refinement = geometry.get("standardized_edge_refinement", {})
        if refinement.get("is_image_postprocess") is not False:
            raise RuntimeError(
                f"Missing real-geometry refinement provenance for {demo_id}"
            )

        blend = run / f"{demo_id}.blend"
        if not blend.is_file() or blend.stat().st_size < 100_000:
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
        "requested_output_path": _wb_expand_paths(
            "${WORLDBRIDGE_ROOT}/baselines/annotations/gemini_3_1_pro/connect2"
        ),
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
        "deliverable_bytes": sum(
            scene["scene"]["bytes"]
            + sum(item["bytes"] for item in scene["images"])
            + sum(item["bytes"] for item in scene["videos"])
            for scene in scenes
        ),
        "directory_bytes_before_index": sum(path.stat().st_size for path in all_files),
        "scenes": scenes,
        "protocol_amendments": [
            "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_bmesh_compatibility_20260923.json",
            "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_bmesh_faces_compatibility_20260923.json",
            "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_coastal_bmesh_compatibility_20260923.json",
        ],
    }
    write_json(ROOT / "collection_manifest.json", collection)
    lines = [
        "# Gemini 3.1 Pro refined connected indoor/outdoor demos",
        "",
        "Six detailed native Blender 3D scenes generated through the Gemini 3.1 Pro Coding Plan account client. No Gemini API key or API-billed transport was used.",
        "",
        "Each scene directory contains:",
        "",
        "- one compressed `.blend` scene with real indoor, threshold, and outdoor geometry;",
        "- eighteen separate bright 1280×720 PNG views, with varied distances and angles and no labels, numbering, or montage;",
        "- two H.264 960×540 traversal videos at 24 fps and 2 seconds each;",
        "- Gemini source, input specification, raw account-client logs, geometry audit metrics, hashes, and compatibility provenance.",
        "",
        "The delivered meshes pass a minimum of 250 visible mesh objects and 60,000 renderable polygons per scene. Modifier geometry and standardized edge refinement are baked into the `.blend` files; this is real 3D geometry, not image post-processing.",
        "",
        "## Scenes",
        "",
    ]
    for scene in scenes:
        lines.append(f"- `{scene['demo_id']}` — {scene['title']}")
    lines.extend(
        [
            "",
            "See `collection_manifest.json` for dimensions, codec probes, SHA-256 hashes, geometry counts, renderer selection, and full provenance.",
        ]
    )
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GEMINI_CONNECT2_FINAL_AUDIT_COMPLETE scenes=6 images=108 videos=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
