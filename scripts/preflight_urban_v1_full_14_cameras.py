#!/usr/bin/env python3
"""Validate all full-13 delivery cameras without rasterizing the city."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
LAYOUT = CITY / "layout_plan.json"
RENDERER_PATH = ROOT / "scripts/render_urban_v1_full_14_daytime.py"
OUTPUT = CITY / "camera_preflight.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_atomic(payload: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, OUTPUT)


def main() -> None:
    layout = json.loads(LAYOUT.read_text(encoding="utf8"))
    if layout.get("scene_revision") != "urban_v1_full_14":
        raise RuntimeError("Full-13 layout revision mismatch")
    requested_run = os.environ.get("C2W_FULL14_RUN_ID", layout.get("run_id", ""))
    if requested_run != layout.get("run_id"):
        raise RuntimeError(
            f"Camera preflight run mismatch: requested={requested_run} layout={layout.get('run_id')}"
        )

    spec = importlib.util.spec_from_file_location(
        "full14_camera_preflight_renderer", RENDERER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {RENDERER_PATH}")
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)
    if len(renderer.SHOTS) != 80:
        raise RuntimeError(f"Expected 80 camera contracts, got {len(renderer.SHOTS)}")

    by_id = {record["placement_id"]: record for record in layout["placements"]}
    camera_data = bpy.data.cameras.new("full14:camera_preflight:data")
    camera = bpy.data.objects.new("full14:camera_preflight", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    records = []
    failures = []
    for shot in renderer.SHOTS:
        try:
            bounds = renderer.resolve_bounds(shot, layout, by_id)
            camera_record = renderer.configure_camera(camera, shot, bounds, by_id)
            pose = renderer.validate_camera_pose(camera, camera_record)
            location = Vector(camera_record["location"])
            target = Vector(camera_record["target"])
            sightline_m = float((target - location).length)
            if not math.isfinite(sightline_m) or sightline_m < 0.25:
                raise RuntimeError(f"Degenerate sightline length: {sightline_m}")
            if not shot.interior and location.z < 0.35:
                raise RuntimeError(
                    f"Exterior camera below safe eye height: z={location.z}"
                )
            records.append(
                {
                    "name": shot.name,
                    "filename": shot.filename,
                    "kind": shot.kind,
                    "interior": shot.interior,
                    "placement_ids": list(shot.placement_ids),
                    "camera_composition_revision": renderer.CAMERA_COMPOSITION_REVISION,
                    "shot_spec_sha256": renderer.shot_spec_sha256(shot),
                    "camera": camera_record,
                    "pose_validation": pose,
                    "sightline_m": round(sightline_m, 4),
                    "status": "PASS",
                }
            )
        except Exception as exc:
            diagnostic = {"name": shot.name, "error": f"{type(exc).__name__}: {exc}"}
            try:
                raw = renderer._base_configure_camera(camera, shot, bounds, by_id)
                diagnostic["computed_camera"] = raw
            except Exception as raw_exc:
                diagnostic[
                    "computed_camera_error"
                ] = f"{type(raw_exc).__name__}: {raw_exc}"
            failures.append(diagnostic)

    payload = {
        "schema": "agent.full14.camera_preflight.v1",
        "created_utc": utc_now(),
        "run_id": layout["run_id"],
        "scene_revision": layout["scene_revision"],
        "status": "PASS" if not failures and len(records) == 80 else "FAIL",
        "method": "all contracted camera matrices, target sightlines and solid non-target placement bounds; each render layer adds exact expanded child-mesh bounds",
        "camera_count_expected": 80,
        "camera_count_passed": len(records),
        "camera_count_failed": len(failures),
        "production_blend_sha256": sha256(CITY / "urban_v1_full_14.blend"),
        "renderer_sha256": sha256(RENDERER_PATH),
        "failures": failures,
        "cameras": records,
    }
    write_atomic(payload)
    print(
        "FULL14_CAMERA_PREFLIGHT",
        json.dumps(
            {
                "status": payload["status"],
                "passed": len(records),
                "failed": len(failures),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if payload["status"] != "PASS":
        raise RuntimeError(f"Full-13 camera preflight failed: {failures}")


if __name__ == "__main__":
    main()
