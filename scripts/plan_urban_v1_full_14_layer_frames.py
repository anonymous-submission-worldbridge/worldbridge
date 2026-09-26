#!/usr/bin/env python3
"""Plan or certify resumable full-13 layer frames.

The long-running shell pipeline launches one Blender/Vulkan process per view.
This helper makes that restart boundary cheap and strict: a frame is reusable
only when its rolling-manifest provenance, settings, byte count, SHA-256, and
authoritative EXR validation all match the current render-pack dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
LAYER_ROOT = CITY / "renders/zdepth_layers"
CAMERAS = CITY / "camera_preflight.json"
LINEAGE = CITY / "render_dependency_packs/render_pack_lineage.json"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frame_valid(
    layer: str,
    dependency_hash: str,
    camera: dict[str, Any],
    record: dict[str, Any] | None,
) -> bool:
    if not isinstance(record, dict):
        return False
    expected = (
        LAYER_ROOT / layer / Path(str(camera["filename"])).with_suffix(".exr").name
    ).resolve()
    try:
        actual = Path(record["outputs"]["bundle"]).resolve()
        settings = record["render_settings"]
        validation = record["authoritative_exr_validation"]
        byte_count = int(record["bytes"]["bundle"])
        expected_sha = str(record["sha256"]["bundle"])
    except (KeyError, TypeError, ValueError):
        return False
    if (
        actual != expected
        or not actual.is_file()
        or actual.stat().st_size != byte_count
    ):
        return False
    if record.get("name") != camera.get("name"):
        return False
    if record.get("filename") != camera.get("filename"):
        return False
    if record.get("kind") != camera.get("kind"):
        return False
    if record.get("interior") is not camera.get("interior"):
        return False
    if record.get("placement_ids") != camera.get("placement_ids"):
        return False
    if record.get("camera_composition_revision") != camera.get(
        "camera_composition_revision"
    ):
        return False
    if record.get("shot_spec_sha256") != camera.get("shot_spec_sha256"):
        return False
    recorded_camera = record.get("camera", {})
    certified_camera = camera.get("camera", {})
    for key in ("mode", "projection", "location", "target", "lens_mm", "ortho_scale"):
        if recorded_camera.get(key) != certified_camera.get(key):
            return False
    if record.get("status") != "rendered" or record.get("layer_key") != layer:
        return False
    if record.get("render_dependency_hash") != dependency_hash:
        return False
    if settings.get("engine") not in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        return False
    if settings.get("resolution") != [1920, 1080] or settings.get("samples") != 64:
        return False
    if settings.get("final_pbr_required") is not True:
        return False
    if settings.get("workbench_final_allowed") is not False:
        return False
    if settings.get("mesh_simplification") is not False:
        return False
    if validation.get("status") != "PASS":
        return False
    if validation.get("resolution") != [1920, 1080]:
        return False
    if validation.get("pixel_content_nondegenerate") is not True:
        return False
    if validation.get("target_pixel_centers_sampled_exactly") is not True:
        return False
    if any(
        validation.get(key) is not False
        for key in ("resizing", "resampling", "interpolation")
    ):
        return False
    if record.get("camera", {}).get("matrix_validation", {}).get("pass") is not True:
        return False
    return len(expected_sha) == 64 and sha256(actual) == expected_sha


def state(layer: str) -> tuple[list[dict[str, Any]], dict[str, bool], dict[str, Any]]:
    run_id = os.environ.get("C2W_FULL14_RUN_ID", "").strip()
    cameras_payload = load_json(CAMERAS)
    lineage = load_json(LINEAGE)
    if (
        cameras_payload.get("status") != "PASS"
        or cameras_payload.get("camera_count_passed") != 80
    ):
        raise RuntimeError("The certified 80-camera preflight is absent or stale")
    if lineage.get("status") != "PASS" or lineage.get("pack_count") != 16:
        raise RuntimeError("The exact render-pack lineage is absent or stale")
    if run_id and (
        cameras_payload.get("run_id") != run_id or lineage.get("run_id") != run_id
    ):
        raise RuntimeError("Run ID mismatch while planning layer frames")
    pack = lineage.get("packs", {}).get(layer)
    if not isinstance(pack, dict):
        raise RuntimeError(f"Unknown full-13 render layer: {layer}")
    dependency_hash = str(pack.get("dependency_hash", ""))
    if len(dependency_hash) != 64:
        raise RuntimeError(f"Missing dependency hash for layer {layer}")
    cameras = cameras_payload.get("cameras", [])
    if len(cameras) != 80 or len({item.get("name") for item in cameras}) != 80:
        raise RuntimeError("Camera contract must contain 80 unique views")
    if any(len(str(item.get("shot_spec_sha256", ""))) != 64 for item in cameras):
        raise RuntimeError("Camera preflight lacks per-view shot-spec hashes")
    manifest_path = LAYER_ROOT / f"layer_manifest_{layer}.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError, TypeError):
            manifest = {}
    records = {
        item.get("name"): item
        for item in manifest.get("views", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    validity = {
        str(camera["name"]): frame_valid(
            layer, dependency_hash, camera, records.get(camera["name"])
        )
        for camera in cameras
    }
    return cameras, validity, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer")
    parser.add_argument("--assert-shot")
    parser.add_argument("--assert-complete", action="store_true")
    args = parser.parse_args()
    cameras, validity, manifest = state(args.layer)
    if args.assert_shot:
        if args.assert_shot not in validity or not validity[args.assert_shot]:
            raise SystemExit(
                f"Frame certification failed: {args.layer}:{args.assert_shot}"
            )
        print(f"FULL14_FRAME_CERTIFIED layer={args.layer} shot={args.assert_shot}")
        return
    missing = [
        str(camera["name"]) for camera in cameras if not validity[str(camera["name"])]
    ]
    if args.assert_complete:
        if missing:
            raise SystemExit(
                f"Layer incomplete after frame jobs: {args.layer}; missing={missing}"
            )
        if not (
            manifest.get("run_id") == os.environ.get("C2W_FULL14_RUN_ID")
            and manifest.get("status") == "PASS"
            and manifest.get("complete") is True
            and manifest.get("completed_count") == 80
            and manifest.get("expected_count") == 80
            and manifest.get("workbench_final_frames") == 0
            and manifest.get("all_frames_pbr_eevee") is True
        ):
            raise SystemExit(f"Final layer manifest contract failed: {args.layer}")
        print(f"FULL14_LAYER_CERTIFIED layer={args.layer} completed=80/80")
        return
    for name in missing:
        print(name)


if __name__ == "__main__":
    main()
