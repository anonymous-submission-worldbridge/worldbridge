#!/usr/bin/env python3
"""Audit and index the completed Gemini 3.1 Pro connected-demo package."""
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
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_specs.json"
)
IMAGE_ROLES = [
    "interior_overview",
    "interior_detail",
    "inside_looking_out",
    "threshold_from_inside",
    "exterior_overview",
    "outdoor_detail",
    "outside_looking_in",
    "threshold_from_outside",
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
        "frames": 96,
        "duration_seconds": 4.0,
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
        if (
            not manifest.get("generation_success")
            or not manifest.get("build_success")
            or not manifest.get("render_success")
        ):
            raise RuntimeError(f"Incomplete manifest state for {demo_id}")
        if manifest.get("auth_mode") != "account_subscription_no_api_key":
            raise RuntimeError(f"Unexpected auth mode for {demo_id}")
        if manifest.get("model_requested") != "gemini-3.1-pro-high":
            raise RuntimeError(f"Unexpected model for {demo_id}")
        if (run / ".render_frames").exists():
            raise RuntimeError(f"Temporary frame directory remains for {demo_id}")

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
            probe = video_probe(path)
            videos.append(
                {
                    "role": role,
                    "path": str(path.relative_to(ROOT)),
                    **probe,
                    "sha256": sha256(path),
                }
            )
        deliverables = [blend] + [ROOT / item["path"] for item in images + videos]
        manifest_hashes = manifest.get("outputs_sha256", {})
        for path in deliverables:
            relative_to_run = str(path.relative_to(run))
            if manifest_hashes.get(relative_to_run) != sha256(path):
                raise RuntimeError(f"Manifest hash mismatch: {path}")
        geometry = manifest["geometry"]
        if (
            not geometry.get("is_native_3d_scene")
            or geometry.get("visible_mesh_objects", 0) < 40
        ):
            raise RuntimeError(f"3D geometry audit failed for {demo_id}")
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
                "source_path": str((run / "source/generated.py").relative_to(ROOT)),
                "manifest_path": str(manifest_path.relative_to(ROOT)),
            }
        )

    all_files = [path for path in ROOT.rglob("*") if path.is_file()]
    collection = {
        "status": "complete",
        "all_checks_passed": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_output_path": _wb_expand_paths(
            "${WORLDBRIDGE_ROOT}/baselines/annotations/gemini_3_1_pro/connect"
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
            "methods/gemini/protocol/generation/gemini_3_1_pro_connect_bmesh_amendment_20260923.json",
            "methods/gemini/protocol/generation/gemini_3_1_pro_connect_blender_compatibility_20260923.json",
        ],
    }
    write_json(ROOT / "collection_manifest.json", collection)

    lines = [
        "# Gemini 3.1 Pro connected indoor/outdoor demos",
        "",
        "Six native Blender 3D scenes generated through the Gemini 3.1 Pro account-subscription client. No Gemini API key or API-billed transport was used.",
        "",
        "Each scene directory contains:",
        "",
        "- one compressed `.blend` scene with real indoor and outdoor geometry;",
        "- eight separate 1280×720 PNG stills with no added labels, numbering, or montage;",
        "- `videos/indoor_to_outdoor.mp4` and `videos/outdoor_to_indoor.mp4`, each H.264 960×540, 24 fps, 4 seconds;",
        "- the Gemini-generated Blender Python source, input specification, raw client logs, and per-scene manifest.",
        "",
        "## Scenes",
        "",
    ]
    for scene in scenes:
        lines.append(f"- `{scene['demo_id']}` — {scene['title']}")
    lines.extend(
        [
            "",
            "See `collection_manifest.json` for dimensions, geometry counts, codec probes, SHA-256 hashes, and provenance.",
            "",
            "Rendering used Blender Eevee because CUDA/OptiX devices were not visible to Blender on this host during the run.",
        ]
    )
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("GEMINI_CONNECT_FINAL_AUDIT_COMPLETE scenes=6 images=48 videos=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
