#!/usr/bin/env python3
"""Compare bounded single-scene Eevee references to identical Z layers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image

from urban_v1_full_14_direct_specs import DIRECT_VALIDATIONS


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
STANDARD = CITY / "renders/zdepth_layers"
DIRECT = CITY / "renders/direct_validation_layers"
OUTPUT_ROOT = CITY / "renders/direct_validation"
AUDIT = CITY / "direct_zdepth_equivalence_audit.json"
REFERENCE_RECEIPTS = OUTPUT_ROOT / "reference_receipts"
RENDERER = ROOT / "scripts/render_urban_v1_full_14_daytime.py"
SKY = np.asarray((0.19, 0.48, 0.82), dtype=np.float32)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exr_parts(path: Path) -> dict[str, np.ndarray]:
    file = OpenEXR.File(str(path))
    result = {}
    for item in file.parts:
        name = item.name()
        channel_name = name if name in item.channels else f"{name}.V"
        if channel_name not in item.channels:
            raise RuntimeError(
                f"Part {name!r} in {path} has no authoritative channel; "
                f"got {sorted(item.channels)}"
            )
        result[name] = np.asarray(item.channels[channel_name].pixels, dtype=np.float32)
    return result


def filled(color: np.ndarray, background: np.ndarray) -> np.ndarray:
    rgb = color[..., :3]
    if color.shape[-1] < 4:
        return rgb
    alpha = np.clip(color[..., 3:4], 0.0, 1.0)
    return rgb * alpha + background * (1.0 - alpha)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb, 0.0, None)
    return np.where(
        rgb <= 0.0031308,
        12.92 * rgb,
        1.055 * np.power(rgb, 1.0 / 2.4) - 0.055,
    )


def gradient(luminance: np.ndarray) -> np.ndarray:
    dx = np.abs(np.diff(luminance, axis=1, append=luminance[:, -1:]))
    dy = np.abs(np.diff(luminance, axis=0, append=luminance[-1:, :]))
    return np.hypot(dx, dy)


def atomic_json(payload: dict) -> None:
    temporary = AUDIT.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, AUDIT)


def atomic_reference_json(key: str, payload: dict) -> None:
    REFERENCE_RECEIPTS.mkdir(parents=True, exist_ok=True)
    destination = REFERENCE_RECEIPTS / f"{key}.json"
    temporary = destination.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, destination)


def merge_reference_receipts() -> None:
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    camera_preflight = json.loads(
        (CITY / "camera_preflight.json").read_text(encoding="utf8")
    )
    run_id = layout["run_id"]
    renderer_hash = sha256(RENDERER)
    if not (
        camera_preflight.get("run_id") == run_id
        and camera_preflight.get("status") == "PASS"
        and camera_preflight.get("renderer_sha256") == renderer_hash
    ):
        raise RuntimeError(
            "Direct comparison requires current certified 80-camera renderer"
        )
    results = []
    for key, spec in DIRECT_VALIDATIONS.items():
        receipt = json.loads(
            (REFERENCE_RECEIPTS / f"{key}.json").read_text(encoding="utf8")
        )
        result = receipt["result"]
        shot = spec["shot"]
        direct_manifest = json.loads(
            (DIRECT / f"layer_manifest_{key}.json").read_text(encoding="utf8")
        )
        direct_record = next(
            item for item in direct_manifest["views"] if item["name"] == shot
        )
        source_records = {}
        for source_key in ("base", *spec["layers"]):
            manifest = json.loads(
                (STANDARD / f"layer_manifest_{source_key}.json").read_text(
                    encoding="utf8"
                )
            )
            source_records[source_key] = next(
                item for item in manifest["views"] if item["name"] == shot
            )
        direct_path = Path(direct_record["outputs"]["bundle"])
        comparison_image = Path(result["comparison_image"])
        checks = {
            "run_and_camera_current": (
                receipt.get("run_id") == run_id
                and receipt.get("renderer_sha256") == renderer_hash
                and direct_record.get("shot_spec_sha256")
                == source_records[spec["layers"][0]].get("shot_spec_sha256")
            ),
            "one_contracted_reference": (
                receipt.get("status") == "PASS"
                and result.get("key") == key
                and result.get("shot") == shot
                and result.get("pass") is True
                and result.get("source_layers") == list(spec["layers"])
            ),
            "direct_native_bundle_byte_evidence": (
                direct_path.is_file()
                and result.get("direct_bundle_sha256")
                == direct_record.get("sha256", {}).get("bundle")
                and sha256(direct_path) == result.get("direct_bundle_sha256")
            ),
            "all_current_source_layer_byte_evidence": all(
                (source := Path(record["outputs"]["bundle"])).is_file()
                and result.get("source_bundle_sha256", {}).get(layer_key)
                == record.get("sha256", {}).get("bundle")
                and sha256(source) == result["source_bundle_sha256"][layer_key]
                for layer_key, record in source_records.items()
            ),
            "comparison_image_byte_evidence": (
                comparison_image.is_file()
                and sha256(comparison_image) == result.get("comparison_image_sha256")
            ),
        }
        if not all(checks.values()):
            raise RuntimeError(
                f"Stale or unverifiable direct comparison {key}: {checks}"
            )
        results.append(result)
    payload = {
        "schema": "agent.full14.direct_zdepth_equivalence.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "status": "PASS" if all(record["pass"] for record in results) else "FAIL",
        "method": "six bounded multi-layer single-scene Eevee references versus identical-layer camera-Z composites, isolated per-reference Python process",
        "full_scene_oom_avoidance": "Each of six native 1920x1080 direct comparisons runs in a separate process with current camera, direct source SHA, every exact standard source SHA and difference image SHA certified at the merge gate.",
        "reference_count": len(results),
        "results": results,
    }
    atomic_json(payload)
    if payload["status"] != "PASS":
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one-reference", choices=tuple(DIRECT_VALIDATIONS))
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()
    if args.one_reference is not None and args.merge_only:
        raise RuntimeError("--one-reference and --merge-only are mutually exclusive")
    if args.merge_only:
        merge_reference_receipts()
        return
    if args.one_reference is None:
        # Real process boundaries prevent OpenEXR/numpy temporaries from six
        # heavyweight native direct+layer bundles accumulating in one service
        # and triggering systemd-oomd.  No quality, thresholds or references
        # are dropped; all current bytes are SHA-verified again during merge.
        for key in DIRECT_VALIDATIONS:
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--one-reference", key],
                check=True,
            )
        merge_reference_receipts()
        return
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for key, spec in DIRECT_VALIDATIONS.items():
        if key != args.one_reference:
            continue
        shot = spec["shot"]
        direct_manifest = json.loads(
            (DIRECT / f"layer_manifest_{key}.json").read_text(encoding="utf8")
        )
        direct_record = next(
            record for record in direct_manifest["views"] if record["name"] == shot
        )
        direct_path = Path(direct_record["outputs"]["bundle"])
        direct_parts = exr_parts(direct_path)
        direct_rgb = filled(direct_parts["CombinedColor"], SKY)
        direct_depth = direct_parts["CombinedDepth"]

        base_manifest = json.loads(
            (STANDARD / "layer_manifest_base.json").read_text(encoding="utf8")
        )
        base_record = next(
            record for record in base_manifest["views"] if record["name"] == shot
        )
        base_parts = exr_parts(Path(base_record["outputs"]["bundle"]))
        base_rgb = filled(base_parts["BaseColor"], SKY)
        base_depth = base_parts["BaseDepth"]
        shadowed = base_rgb.copy()
        strongest_receiver_delta = np.zeros(base_depth.shape, dtype=np.float32)
        asset_passes = []
        source_hashes = {"base": base_record["sha256"]["bundle"]}
        for source_layer in spec["layers"]:
            manifest = json.loads(
                (STANDARD / f"layer_manifest_{source_layer}.json").read_text(
                    encoding="utf8"
                )
            )
            record = next(item for item in manifest["views"] if item["name"] == shot)
            path = Path(record["outputs"]["bundle"])
            parts = exr_parts(path)
            color = parts["CombinedColor"]
            depth = parts["CombinedDepth"]
            mask = depth < base_depth - 0.002
            receiver = filled(color, base_rgb)
            clean_receiver = np.where(mask[..., None], base_rgb, receiver)
            receiver_delta = np.linalg.norm(clean_receiver - base_rgb, axis=2)
            take_receiver = receiver_delta > strongest_receiver_delta
            shadowed = np.where(take_receiver[..., None], clean_receiver, shadowed)
            strongest_receiver_delta = np.maximum(
                strongest_receiver_delta, receiver_delta
            )
            asset_passes.append((mask, color[..., :3], depth))
            source_hashes[source_layer] = record["sha256"]["bundle"]

        composite = shadowed
        composite_depth = base_depth.copy()
        for mask, color, depth in asset_passes:
            front = mask & (depth < composite_depth)
            composite = np.where(front[..., None], color, composite)
            composite_depth = np.minimum(composite_depth, depth)

        color_error = np.abs(composite - direct_rgb)
        rgb_mae = float(color_error.mean())
        rgb_p95 = float(np.quantile(color_error, 0.95))
        rgb_p99 = float(np.quantile(color_error, 0.99))
        direct_luma = direct_rgb @ np.asarray(
            (0.2126, 0.7152, 0.0722), dtype=np.float32
        )
        composite_luma = composite @ np.asarray(
            (0.2126, 0.7152, 0.0722), dtype=np.float32
        )
        edge_mae = float(
            np.abs(gradient(direct_luma) - gradient(composite_luma)).mean()
        )
        finite = np.isfinite(direct_depth) & np.isfinite(composite_depth)
        depth_tolerance = np.maximum(0.01, np.abs(direct_depth) * 1.0e-5)
        depth_match = float(
            (
                np.abs(direct_depth - composite_depth)[finite]
                <= depth_tolerance[finite]
            ).mean()
        )
        passed = (
            rgb_mae <= 0.04
            and rgb_p95 <= 0.12
            and edge_mae <= 0.025
            and depth_match >= 0.985
        )

        difference = np.clip(color_error * 4.0, 0.0, 1.0)
        comparison = np.concatenate(
            (linear_to_srgb(direct_rgb), linear_to_srgb(composite), difference), axis=1
        )
        image_path = OUTPUT_ROOT / f"{key}_{shot}_direct_composite_difference.png"
        Image.fromarray(np.uint8(np.clip(comparison, 0.0, 1.0) * 255.0), "RGB").save(
            image_path
        )
        results.append(
            {
                "key": key,
                "shot": shot,
                "source_layers": list(spec["layers"]),
                "status": "PASS" if passed else "FAIL",
                "pass": passed,
                "direct_bundle": str(direct_path.resolve()),
                "direct_bundle_sha256": sha256(direct_path),
                "source_bundle_sha256": source_hashes,
                "comparison_image": str(image_path.resolve()),
                "comparison_image_sha256": sha256(image_path),
                "metrics": {
                    "linear_rgb_mae": rgb_mae,
                    "linear_rgb_p95": rgb_p95,
                    "linear_rgb_p99": rgb_p99,
                    "luminance_edge_mae": edge_mae,
                    "depth_match_fraction": depth_match,
                },
                "thresholds": {
                    "maximum_linear_rgb_mae": 0.04,
                    "maximum_linear_rgb_p95": 0.12,
                    "maximum_luminance_edge_mae": 0.025,
                    "minimum_depth_match_fraction": 0.985,
                },
            }
        )
        print(
            f"FULL14_DIRECT_COMPARE {key} pass={passed} mae={rgb_mae:.6f} p95={rgb_p95:.6f} edge={edge_mae:.6f} depth={depth_match:.6f}",
            flush=True,
        )
    camera_preflight = json.loads(
        (CITY / "camera_preflight.json").read_text(encoding="utf8")
    )
    if not (
        len(results) == 1
        and results[0]["key"] == args.one_reference
        and camera_preflight.get("status") == "PASS"
        and camera_preflight.get("renderer_sha256") == sha256(RENDERER)
    ):
        raise RuntimeError("One-reference result is not bound to current renderer")
    atomic_reference_json(
        args.one_reference,
        {
            "schema": "agent.full14.isolated_direct_reference_comparison.v1",
            "created_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "run_id": layout["run_id"],
            "status": results[0]["status"],
            "renderer_sha256": sha256(RENDERER),
            "result": results[0],
        },
    )
    if results[0]["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
