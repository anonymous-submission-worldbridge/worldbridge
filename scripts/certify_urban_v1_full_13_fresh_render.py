#!/usr/bin/env python3
"""Certify all 1,280 genuinely rerasterized production PBR layer frames.

This pipeline stage is used when the actual city geometry/camera changed.
Historical non-raster frame rebinding is explicitly forbidden.  Each source
EXR and its camera, current source-pack and rendering settings must identify
the *new* run; it is not sufficient to rename an old manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import OpenEXR


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
LAYER_ROOT = CITY / "renders/zdepth_layers"
LAYERS = (
    "river5_nature",
    "river3_residential",
    "artificial_lake",
    "all45_unique_buildings",
    "education_buildings",
    "commercial_services",
    "industrial",
    "public_safety",
    "residential_delivery",
    "all44_leisure",
    "park_leisure_support",
    "health",
    "full13_unique_urban_fabric",
    "full13_semantic_interiors",
    "full13_public_realm",
    "base",
)
OUTPUT = CITY / "layer_provenance_rebind_audit.json"


def load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(result, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    run_id = os.environ.get("C2W_FULL13_RUN_ID", "")
    if not run_id or os.environ.get("C2W_FULL13_FORCE_FRESH_RENDER") != "1":
        raise RuntimeError(
            "A named fresh-geometry production rendering run is required"
        )
    generation = load(CITY / "generation_audit.json")
    lineage = load(CITY / "render_dependency_packs/render_pack_lineage.json")
    camera_preflight = load(CITY / "camera_preflight.json")
    if not (
        generation.get("run_id")
        == lineage.get("run_id")
        == camera_preflight.get("run_id")
        == run_id
        and generation.get("status")
        == lineage.get("status")
        == camera_preflight.get("status")
        == "PASS"
        and lineage.get("pack_count") == 16
        and camera_preflight.get("camera_count_passed") == 80
    ):
        raise RuntimeError(
            "Current production city, packs or 80-camera contract not certified"
        )
    generation_completed_ns = int(
        datetime.fromisoformat(
            generation["completed_utc"].replace("Z", "+00:00")
        ).timestamp()
        * 1_000_000_000
    )
    expected_cameras = {item["name"]: item for item in camera_preflight["cameras"]}
    if len(expected_cameras) != 80:
        raise RuntimeError("Camera names contain a duplicate or are incomplete")
    expected_camera_fields = (
        "mode",
        "projection",
        "location",
        "target",
        "lens_mm",
        "ortho_scale",
    )
    actual_frames = 0
    total_bytes = 0
    verified_shas = hashlib.sha256()
    layers = []
    for layer in LAYERS:
        pack = lineage["packs"][layer]
        manifest = load(LAYER_ROOT / f"layer_manifest_{layer}.json")
        worker = load(CITY / f"render_{layer}.status.json")
        layer_preflight = load(LAYER_ROOT / f"camera_mesh_preflight_{layer}.json")
        if not (
            worker.get("run_id") == run_id
            and worker.get("status") == "PASS"
            and manifest.get("run_id") == run_id
            and manifest.get("status") == "PASS"
            and manifest.get("complete") is True
            and manifest.get("expected_count") == manifest.get("completed_count") == 80
            and manifest.get("render_dependency_hash") == pack.get("dependency_hash")
            and manifest.get("production_blend_before", {}).get("sha256")
            == manifest.get("production_blend_after", {}).get("sha256")
            == generation.get("production_blend_sha256")
            and layer_preflight.get("run_id") == run_id
            and layer_preflight.get("status") == "PASS"
            and layer_preflight.get("camera_count_passed") == 80
            and layer_preflight.get("evaluated_child_mesh_bvh_audit", {}).get("pass")
            is True
        ):
            raise RuntimeError(
                f"Current layer/worker/mesh lineage is incomplete: {layer}"
            )
        names = [record.get("name") for record in manifest["views"]]
        if len(names) != 80 or set(names) != set(expected_cameras):
            raise RuntimeError(f"Missing or duplicated current source views: {layer}")
        layer_bytes = 0
        for record in manifest["views"]:
            expected = expected_cameras[record["name"]]
            bundle = Path(record.get("outputs", {}).get("bundle", ""))
            validation = record.get("authoritative_exr_validation", {})
            settings = record.get("render_settings", {})
            if not (
                record.get("status") == "rendered"
                and record.get("producer_run_id") == run_id
                and record.get("render_dependency_hash") == pack["dependency_hash"]
                and record.get("shot_spec_sha256") == expected["shot_spec_sha256"]
                and record.get("camera_composition_revision")
                == expected["camera_composition_revision"]
                and all(
                    record.get("camera", {}).get(field) == expected["camera"].get(field)
                    for field in expected_camera_fields
                )
                and record.get("camera", {}).get("matrix_validation", {}).get("pass")
                is True
                and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
                and settings.get("resolution") == [1920, 1080]
                and settings.get("samples") == 64
                and settings.get("final_pbr_required") is True
                and settings.get("mesh_simplification") is False
                and validation.get("status") == "PASS"
                and validation.get("resolution") == [1920, 1080]
                and validation.get("native_resolution") == [1920, 1080]
                and validation.get("target_pixel_centers_sampled_exactly") is True
                and validation.get("resizing") is False
                and validation.get("resampling") is False
                and validation.get("interpolation") is False
                and bundle.is_file()
                and bundle.stat().st_mtime_ns >= generation_completed_ns
                and bundle.stat().st_size == record.get("bytes", {}).get("bundle")
                and len(record.get("sha256", {}).get("bundle", "")) == 64
                and sha256(bundle) == record["sha256"]["bundle"]
            ):
                raise RuntimeError(
                    f"Stale, simulated, or non-PBR frame: {layer}:{record.get('name')}"
                )
            exr = OpenEXR.InputFile(str(bundle))
            box = exr.header()["dataWindow"]
            size = (int(box.max.x - box.min.x + 1), int(box.max.y - box.min.y + 1))
            exr.close()
            if size != (1920, 1080):
                raise RuntimeError(f"Native source EXR is not 1920x1080: {bundle}")
            actual_frames += 1
            layer_bytes += bundle.stat().st_size
            verified_shas.update(
                f"{layer}:{record['name']}:{record['sha256']['bundle']}\n".encode(
                    "utf8"
                )
            )
        total_bytes += layer_bytes
        layers.append(
            {
                "name": layer,
                "same_run_real_raster_frames": 80,
                "new_native_exr_bytes": layer_bytes,
                "render_dependency_hash": pack["dependency_hash"],
            }
        )
    if actual_frames != 1280:
        raise RuntimeError(
            f"Expected 1280 independently certified EEVEE frames, got {actual_frames}"
        )
    receipt = {
        "schema": "agent.full13.fresh_geometry_full_raster_provenance.v1",
        "created_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "run_id": run_id,
        "status": "PASS",
        "fresh_geometric_city_source_sha256": generation["active_generator_sha256"],
        "fresh_production_blend_sha256": generation["production_blend_sha256"],
        "prior_run_frame_rebinding": False,
        "camera_only_rebinding": False,
        "pixel_content_regenerated_by_current_same_run_native_eevee": True,
        "all_source_frames_current_source_pack_sha_camera_and_pbr_verified": True,
        "all_current_exact_preflights_pass": True,
        "all_current_80_camera_mesh_preflights_pass": True,
        "all_source_frame_sha256_verified": True,
        "all_source_frames_native_1920x1080_exr": True,
        "layer_count": 16,
        "frame_count": actual_frames,
        "native_exr_total_bytes": total_bytes,
        "native_exr_provenance_digest": verified_shas.hexdigest(),
        "layers": layers,
    }
    temporary = OUTPUT.with_suffix(".fresh_writing.json")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, OUTPUT)
    print(
        "FULL13_FRESH_RASTER_CERTIFIED",
        json.dumps(
            {
                "run_id": run_id,
                "frame_count": actual_frames,
                "native_exr_total_bytes": total_bytes,
                "status": "PASS",
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
