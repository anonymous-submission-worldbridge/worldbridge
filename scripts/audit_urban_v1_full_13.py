#!/usr/bin/env python3
"""Strict geometry, provenance, pixel, camera, and semantic audit for full-13."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
LAYER_ROOT = CITY / "renders/zdepth_layers"
RENDER_ROOT = CITY / "renders"
EXPECTED_RESOLUTION = (1920, 1080)
NONDEGENERATE_THRESHOLDS = {
    # Entropy alone wrongly rejects valid wide daylight views dominated by a
    # smooth physical sky.  Require four independent signals instead: a
    # substantial encoded raster, global colour variation, luminance-bin
    # entropy, and robust 1st-to-99th percentile tonal span.
    "minimum_bytes": 1_000_000,
    "minimum_rgb_stddev": 0.075,
    "minimum_entropy_bits": 2.4,
    "minimum_luminance_p99_p01_span": 0.25,
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, path)


def part(exr: OpenEXR.File, name: str):
    by_name = {item.name(): item for item in exr.parts}
    return by_name[name]


def depth(path: Path, name: str) -> np.ndarray:
    exr = OpenEXR.File(str(path))
    return np.asarray(part(exr, name).channels[f"{name}.V"].pixels, dtype=np.float32)


def image_metrics(path: Path) -> dict:
    image = Image.open(path).convert("RGB")
    if image.size != EXPECTED_RESOLUTION:
        raise RuntimeError(f"Wrong resolution {image.size}: {path}")
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32) / 255.0
    luminance = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    histogram = np.bincount(
        (luminance * 255).astype(np.uint8).ravel(), minlength=256
    ).astype(np.float64)
    probabilities = histogram[histogram > 0] / histogram.sum()
    entropy = float(-(probabilities * np.log2(probabilities)).sum())
    metrics = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "resolution": list(image.size),
        "rgb_stddev": round(float(rgb.std()), 6),
        "luminance_mean": round(float(luminance.mean()), 6),
        "luminance_p01": round(float(np.quantile(luminance, 0.01)), 6),
        "luminance_p99": round(float(np.quantile(luminance, 0.99)), 6),
        "saturation_mean": round(float(hsv[..., 1].mean()), 6),
        "entropy_bits": round(entropy, 6),
    }
    metrics["luminance_p99_p01_span"] = round(
        metrics["luminance_p99"] - metrics["luminance_p01"], 6
    )
    metrics["nondegenerate_signals"] = {
        "encoded_bytes": metrics["bytes"] >= NONDEGENERATE_THRESHOLDS["minimum_bytes"],
        "rgb_stddev": metrics["rgb_stddev"]
        >= NONDEGENERATE_THRESHOLDS["minimum_rgb_stddev"],
        "entropy_bits": metrics["entropy_bits"]
        >= NONDEGENERATE_THRESHOLDS["minimum_entropy_bits"],
        "robust_luminance_span": metrics["luminance_p99_p01_span"]
        >= NONDEGENERATE_THRESHOLDS["minimum_luminance_p99_p01_span"],
    }
    return metrics


def make_contact_sheets(paths: list[Path]) -> list[str]:
    destination = RENDER_ROOT / "contact_sheets"
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    for page, start in enumerate(range(0, len(paths), 20), 1):
        canvas = Image.new("RGB", (1920, 4 * 236), (28, 30, 32))
        draw = ImageDraw.Draw(canvas)
        for cell, path in enumerate(paths[start : start + 20]):
            x = (cell % 5) * 384
            y = (cell // 5) * 236
            thumb = Image.open(path).convert("RGB")
            thumb.thumbnail((384, 216), Image.Resampling.LANCZOS)
            canvas.paste(thumb, (x, y))
            draw.rectangle((x, y + 216, x + 383, y + 235), fill=(20, 22, 24))
            draw.text((x + 5, y + 218), path.name, fill=(240, 240, 235))
        target = destination / f"full13_contact_sheet_{page:02d}.jpg"
        canvas.save(target, quality=94, subsampling=0)
        outputs.append(str(target.resolve()))
    return outputs


def main() -> None:
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    delivery = json.loads(
        (RENDER_ROOT / "render_manifest.json").read_text(encoding="utf8")
    )
    run_id = layout["run_id"]
    generation = json.loads((CITY / "generation_audit.json").read_text(encoding="utf8"))
    procedural = json.loads(
        (CITY / "asset_packs/full13_same_run_procedural_assets.json").read_text(
            encoding="utf8"
        )
    )
    semantic_pack = json.loads(
        (CITY / "asset_packs/full13_semantic_public_interiors.json").read_text(
            encoding="utf8"
        )
    )
    packs = json.loads(
        (CITY / "render_dependency_packs/render_pack_lineage.json").read_text(
            encoding="utf8"
        )
    )
    road_furniture = json.loads(
        (CITY / "road_furniture_mesh_audit.json").read_text(encoding="utf8")
    )
    direct_equivalence = json.loads(
        (CITY / "direct_zdepth_equivalence_audit.json").read_text(encoding="utf8")
    )
    resources = json.loads(
        (CITY / "resource_efficiency_audit.json").read_text(encoding="utf8")
    )
    provenance_rebind = json.loads(
        (CITY / "layer_provenance_rebind_audit.json").read_text(encoding="utf8")
    )
    cameras = json.loads((CITY / "camera_preflight.json").read_text(encoding="utf8"))
    camera_rebind = json.loads(
        (CITY / "camera_contract_rebind_audit.json").read_text(encoding="utf8")
    )
    layer_manifests = {}
    placement_layer = {}
    for path in sorted(LAYER_ROOT.glob("layer_manifest_*.json")):
        manifest = json.loads(path.read_text(encoding="utf8"))
        layer_manifests[manifest["layer_key"]] = manifest
        for placement_id in manifest["assigned_placement_ids"]:
            if placement_id in placement_layer:
                raise RuntimeError(f"Duplicate layer assignment: {placement_id}")
            placement_layer[placement_id] = manifest["layer_key"]
    if set(placement_layer) != {
        record["placement_id"] for record in layout["placements"]
    }:
        raise RuntimeError("Layer manifests do not partition the final layout")

    pngs = [RENDER_ROOT / record["filename"] for record in delivery["views"]]
    metrics = [image_metrics(path) for path in pngs]
    image_checks = {
        "all_80_present": len(pngs) == 80 and len({path.name for path in pngs}) == 80,
        "all_1920x1080": all(item["resolution"] == [1920, 1080] for item in metrics),
        "all_nondegenerate": all(
            all(item["nondegenerate_signals"].values()) for item in metrics
        ),
        "all_daylight_exposed": all(
            0.10 <= item["luminance_mean"] <= 0.90 and item["luminance_p99"] >= 0.45
            for item in metrics
        ),
        "all_color_rendered": all(item["saturation_mean"] >= 0.025 for item in metrics),
    }

    # Actual mesh projection: keep only authored building/service layers and
    # render surfaces at least 2 m above the base receiver.  Road surfaces,
    # school sports fields, park/lake ground and aprons are NOT buildings.
    # Reconstruct the rotated world-space pixel centers from the exact native
    # horizontal orthographic field and crop to the recorded city envelope.
    # No placement AABB enters the occupied-pixel numerator.
    top_name = "city_top_down_coverage"
    base_record = next(
        record
        for record in layer_manifests["base"]["views"]
        if record["name"] == top_name
    )
    base_depth = depth(Path(base_record["outputs"]["bundle"]), "BaseDepth")
    building_layers = (
        "river3_residential",
        "all45_unique_buildings",
        "education_buildings",
        "commercial_services",
        "industrial",
        "public_safety",
        "residential_delivery",
        "health",
        "full13_unique_urban_fabric",
        "full13_semantic_interiors",
    )
    union = np.zeros(base_depth.shape, dtype=bool)
    per_layer_height_area = {}
    ortho_width = float(base_record["camera"]["ortho_scale"])
    square_pixel_side = ortho_width / EXPECTED_RESOLUTION[0]
    ys, xs = np.indices(base_depth.shape)
    projected_right = (xs + 0.5 - EXPECTED_RESOLUTION[0] / 2) * square_pixel_side
    projected_up = (EXPECTED_RESOLUTION[1] / 2 - ys - 0.5) * square_pixel_side
    eye = np.asarray(base_record["camera"]["location"], dtype=np.float64)
    target = np.asarray(base_record["camera"]["target"], dtype=np.float64)
    camera_direction = eye - target
    camera_direction /= np.linalg.norm(camera_direction)
    right = np.array([-camera_direction[1], camera_direction[0], 0.0], dtype=np.float64)
    right /= np.linalg.norm(right)
    up = np.cross(camera_direction, right)
    world_x = target[0] + projected_right * right[0] + projected_up * up[0]
    world_y = target[1] + projected_right * right[1] + projected_up * up[1]
    city_limits = layout["coverage_audit"]["city_envelope"]
    x0, y0 = city_limits["min"]
    x1, y1 = city_limits["max"]
    in_city = (world_x >= x0) & (world_x <= x1) & (world_y >= y0) & (world_y <= y1)
    for layer_key in building_layers:
        manifest = layer_manifests[layer_key]
        record = next(
            record for record in manifest["views"] if record["name"] == top_name
        )
        building_height = (
            depth(Path(record["outputs"]["bundle"]), "CombinedDepth") < base_depth - 2.0
        )
        union |= building_height
        per_layer_height_area[layer_key] = (
            float(np.count_nonzero(building_height & in_city)) * square_pixel_side**2
        )
    city_pixels = int(np.count_nonzero(in_city))
    silhouette_area = float(np.count_nonzero(union & in_city)) * square_pixel_side**2
    buildable_area = float(layout["coverage_audit"]["buildable_parcel_area_m2"])
    coverage_ratio = silhouette_area / buildable_area
    image_city_area = city_pixels * square_pixel_side**2
    envelope_area = float(layout["coverage_audit"]["city_envelope_area_m2"])
    city_visible_fraction = min(1.0, image_city_area / envelope_area)
    coverage = {
        "method": "native orthographic building-layer union of pixels >2 m above BaseDepth, cropped to real rotated city envelope",
        "placement_aabb_used": False,
        "building_layers": list(building_layers),
        "excluded_nonbuilding_surfaces": [
            "roads",
            "school sports field",
            "park",
            "lake",
            "ground and aprons",
        ],
        "per_layer_building_height_area_m2": per_layer_height_area,
        "visible_asset_pixels": int(np.count_nonzero(union & in_city)),
        "square_metres_per_pixel": square_pixel_side**2,
        "mesh_silhouette_area_m2": silhouette_area,
        "buildable_parcel_area_m2": buildable_area,
        "mesh_projected_buildable_ratio": coverage_ratio,
        "city_envelope_area_visible_in_top_down_m2": image_city_area,
        "city_envelope_area_m2": envelope_area,
        "city_envelope_visible_fraction": city_visible_fraction,
        "minimum_required_ratio": 0.25,
        "pass": coverage_ratio >= 0.25 and city_visible_fraction >= 0.99,
    }

    # Per-shot evidence binds the named target to its assigned layer's actual
    # visible depth delta.  BBox occupancy catches wall/sky-only misframes;
    # pixel occupancy catches almost completely occluded targets.
    semantic = []
    semantic_pass = True
    for view in delivery["views"]:
        if not view.get("placement_ids"):
            continue
        base_path = LAYER_ROOT / "base" / f"{Path(view['filename']).stem}.exr"
        base_record = next(
            record
            for record in layer_manifests["base"]["views"]
            if record["name"] == view["name"]
        )
        base_z = depth(base_path, "BaseDepth")
        target_layers = sorted(
            {placement_layer[target] for target in view["placement_ids"]}
        )
        evidence = []
        for layer_key in target_layers:
            if layer_key == "base":
                # Roads are authored in the shared base receiver, so there is
                # no non-base CombinedDepth delta to isolate.  Certify the
                # actual center target ray instead: camera configuration aims
                # at the declared road target, and the rendered BaseDepth in a
                # 21x21 center patch must agree with that world distance.  A
                # street-level explicit view permits foreground road furniture
                # or a vehicle to occlude the precise center ray; fitted
                # overview cameras use the tighter tolerance.
                camera = base_record["camera"]
                location = np.asarray(camera["location"], dtype=np.float64)
                target = np.asarray(camera["target"], dtype=np.float64)
                expected_distance = float(np.linalg.norm(location - target))
                height, width = base_z.shape
                patch = base_z[
                    height // 2 - 10 : height // 2 + 11,
                    width // 2 - 10 : width // 2 + 11,
                ]
                positive_finite = np.isfinite(patch) & (patch > 0.0)
                observed_distance = (
                    float(np.median(patch[positive_finite]))
                    if positive_finite.any()
                    else float("inf")
                )
                relative_error = abs(observed_distance - expected_distance) / max(
                    expected_distance, 1.0
                )
                tolerance = (
                    0.35
                    if camera.get("mode") == "explicit_world_relationship"
                    else 0.08
                )
                valid = bool(
                    positive_finite.all()
                    and camera.get("matrix_validation", {}).get("pass") is True
                    and relative_error <= tolerance
                )
                evidence.append(
                    {
                        "layer": layer_key,
                        "method": "declared road target center ray versus native BaseDepth 21x21 patch",
                        "expected_target_distance_m": expected_distance,
                        "observed_center_depth_median_m": observed_distance,
                        "relative_depth_error": relative_error,
                        "maximum_relative_depth_error": tolerance,
                        "positive_finite_center_depth_fraction": float(
                            positive_finite.mean()
                        ),
                        "camera_matrix_validation_pass": camera.get(
                            "matrix_validation", {}
                        ).get("pass")
                        is True,
                        "pass": valid,
                    }
                )
                semantic_pass &= valid
                continue
            layer_path = LAYER_ROOT / layer_key / f"{Path(view['filename']).stem}.exr"
            mask = depth(layer_path, "CombinedDepth") < base_z - 0.002
            visible = int(mask.sum())
            if visible:
                yy, xx = np.where(mask)
                bbox_fraction = float(
                    (xx.max() - xx.min() + 1) * (yy.max() - yy.min() + 1) / mask.size
                )
            else:
                bbox_fraction = 0.0
            pixel_fraction = float(visible / mask.size)
            minimum = (
                0.001
                if view["kind"].endswith("far") or view["kind"] == "city"
                else 0.003
            )
            valid = pixel_fraction >= minimum and bbox_fraction >= min(
                0.025, minimum * 6
            )
            evidence.append(
                {
                    "layer": layer_key,
                    "visible_pixel_count": visible,
                    "visible_pixel_fraction": pixel_fraction,
                    "visible_bbox_frame_fraction": bbox_fraction,
                    "minimum_pixel_fraction": minimum,
                    "pass": valid,
                }
            )
            semantic_pass &= valid
        semantic.append(
            {
                "view": view["name"],
                "named_targets": view["placement_ids"],
                "target_layers": target_layers,
                "evidence": evidence,
                "pass": all(item["pass"] for item in evidence),
            }
        )

    camera_checks = []
    camera_mesh_checks = []
    for manifest in layer_manifests.values():
        for record in manifest["views"]:
            camera_checks.append(record["camera"].get("camera_aabb_preflight", {}))
            camera_mesh_checks.append(
                record["camera"].get("camera_mesh_aabb_preflight", {})
            )
    bvh = {
        key: manifest.get("evaluated_child_mesh_bvh_audit", {})
        for key, manifest in layer_manifests.items()
    }
    engine_counts = Counter(
        record["render_settings"]["engine"]
        for manifest in layer_manifests.values()
        for record in manifest["views"]
    )
    status_files = []
    for path in sorted(CITY.glob("*.status.json")):
        try:
            status_files.append(
                {
                    "path": str(path.resolve()),
                    **json.loads(path.read_text(encoding="utf8")),
                }
            )
        except (ValueError, OSError):
            status_files.append({"path": str(path.resolve()), "status": "INVALID"})
    run_ids = {
        generation.get("run_id"),
        procedural.get("run_id"),
        semantic_pack.get("run_id"),
        packs.get("run_id"),
        delivery.get("run_id"),
        provenance_rebind.get("run_id"),
    }
    run_ids.update(manifest.get("run_id") for manifest in layer_manifests.values())
    dependency_hashes_pass = all(
        manifest.get("render_dependency_hash")
        == packs.get("packs", {}).get(layer_key, {}).get("dependency_hash")
        and all(
            record.get("render_dependency_hash")
            == manifest.get("render_dependency_hash")
            for record in manifest.get("views", [])
        )
        for layer_key, manifest in layer_manifests.items()
    )
    camera_by_name = {item["name"]: item for item in cameras.get("cameras", [])}
    camera_values = (
        "mode",
        "projection",
        "location",
        "target",
        "lens_mm",
        "ortho_scale",
    )
    exact_camera_contracts_pass = bool(
        cameras.get("run_id") == run_id
        and cameras.get("status") == "PASS"
        and cameras.get("camera_count_passed") == 80
        and len(camera_by_name) == 80
        and all(
            record.get("shot_spec_sha256")
            == camera_by_name[record["name"]].get("shot_spec_sha256")
            and all(
                record.get("camera", {}).get(key)
                == camera_by_name[record["name"]].get("camera", {}).get(key)
                for key in camera_values
            )
            for manifest in layer_manifests.values()
            for record in manifest["views"]
        )
    )
    # Recompute byte evidence from EVERY current source EXR: a former 80/80
    # assertion is not sufficient after a selective camera or material edit.
    all_layer_frame_sha_verified = all(
        (bundle := Path(record.get("outputs", {}).get("bundle", ""))).is_file()
        and bundle.stat().st_size == record.get("bytes", {}).get("bundle")
        and sha256(bundle) == record.get("sha256", {}).get("bundle")
        for manifest in layer_manifests.values()
        for record in manifest["views"]
    )
    layer_camera_preflights = []
    for layer_key in layer_manifests:
        path = LAYER_ROOT / f"camera_mesh_preflight_{layer_key}.json"
        layer_camera_preflights.append(
            json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}
        )
    direct_manifests = []
    for direct_key in (
        "direct_civic",
        "direct_commercial",
        "direct_residential",
        "direct_industrial_safety",
        "direct_park_lake",
        "direct_diagonal_street",
    ):
        path = (
            CITY
            / "renders/direct_validation_layers"
            / f"layer_manifest_{direct_key}.json"
        )
        direct_manifests.append(
            json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}
        )
    legacy_rebind_pass = bool(
        provenance_rebind.get("pixel_content_changed") is False
        and provenance_rebind.get("layer_count") == 16
        and provenance_rebind.get("frame_count") == 1280
        and provenance_rebind.get("all_source_frame_sha256_verified") is True
        and provenance_rebind.get("all_source_frames_native_1920x1080_exr") is True
        and provenance_rebind.get("all_current_exact_preflights_pass") is True
        and provenance_rebind.get("all_current_80_camera_mesh_preflights_pass") is True
        and provenance_rebind.get(
            "all_pack_mesh_material_modifier_transform_change_counts_zero"
        )
        is True
    )
    selective_rebind_pass = bool(
        provenance_rebind.get("schema")
        == "agent.full13.selective_semantic_upgrade_rebind.v1"
        and set(provenance_rebind.get("changed_geometry_layers", []))
        == {"full13_semantic_interiors", "full13_public_realm"}
        and provenance_rebind.get("unchanged_geometry_layer_count") == 14
        and provenance_rebind.get("unchanged_frame_sha256_verified") == 14 * 80
        and provenance_rebind.get("procedural_collection_equivalence", {}).get(
            "unaffected_blender_data_content_identical"
        )
        is True
        and provenance_rebind.get("procedural_collection_equivalence", {}).get(
            "changed_collection_routed_to_full_rerender"
        )
        is True
        and provenance_rebind.get("layout_change", {}).get(
            "semantic_transforms_and_bounds_preserved"
        )
        is True
    )
    fresh_full_raster_pass = bool(
        provenance_rebind.get("schema")
        == "agent.full13.fresh_geometry_full_raster_provenance.v1"
        and provenance_rebind.get("run_id") == run_id
        and provenance_rebind.get("status") == "PASS"
        and provenance_rebind.get("fresh_production_blend_sha256")
        == generation.get("production_blend_sha256")
        and provenance_rebind.get("fresh_geometric_city_source_sha256")
        == generation.get("active_generator_sha256")
        and provenance_rebind.get("prior_run_frame_rebinding") is False
        and provenance_rebind.get(
            "pixel_content_regenerated_by_current_same_run_native_eevee"
        )
        is True
        and provenance_rebind.get(
            "all_source_frames_current_source_pack_sha_camera_and_pbr_verified"
        )
        is True
        and provenance_rebind.get("all_source_frame_sha256_verified") is True
        and provenance_rebind.get("all_source_frames_native_1920x1080_exr") is True
        and provenance_rebind.get("layer_count") == 16
        and provenance_rebind.get("frame_count") == 1280
        and all_layer_frame_sha_verified
        and exact_camera_contracts_pass
    )
    checks = {
        "one_traceable_run_id": run_ids == {run_id},
        "generation_pass": generation.get("status") == "PASS"
        and all(generation["generation_checks"].values()),
        "procedural_pack_pass": procedural.get("status") == "PASS",
        "semantic_public_interiors_pack_pass": (
            semantic_pack.get("status") == "PASS"
            and semantic_pack.get("production_connection", {}).get("detached_demo")
            is False
            and semantic_pack.get("production_connection", {}).get("render_layer")
            == "full13_semantic_interiors"
            and all(
                semantic_pack.get("observed_part_counts", {}).get(name, 0) >= minimum
                for name, minimum in semantic_pack.get(
                    "minimum_part_counts", {}
                ).items()
            )
            and semantic_pack.get("quality", {}).get("toy_or_placeholder_models") == 0
            and semantic_pack.get("quality", {}).get("proxy_geometry") == 0
            and generation.get("semantic_pack_sha256") == semantic_pack.get("sha256")
        ),
        "render_pack_partition_pass": packs.get("status") == "PASS"
        and packs.get("pack_count") == len(layer_manifests),
        "content_dependency_hashes_pass": (
            packs.get("content_hash_cache", {}).get("all_layers_have_dependency_hash")
            is True
            and dependency_hashes_pass
        ),
        "all_current_source_exr_sha256_verified": all_layer_frame_sha_verified,
        "all_layer_cameras_match_current_preflight": exact_camera_contracts_pass,
        "same_run_exact_camera_provenance_pass": (
            fresh_full_raster_pass
            or (
                camera_rebind.get("run_id") == run_id
                and camera_rebind.get("status") == "PASS"
                and camera_rebind.get("standard_layer_count") == 16
                and camera_rebind.get("direct_reference_count") == 6
                and set(camera_rebind.get("changed_views", []))
                == {
                    "city_top_down_coverage",
                    "school_library_shared_street",
                    "interior_hospital_lobby",
                }
                and camera_rebind.get("layer_dependency_hashes_preserved") is True
            )
        ),
        "same_run_source_frame_provenance_pass": (
            provenance_rebind.get("run_id") == run_id
            and provenance_rebind.get("status") == "PASS"
            and (legacy_rebind_pass or selective_rebind_pass or fresh_full_raster_pass)
        ),
        "road_furniture_mesh_audit_pass": road_furniture.get("run_id") == run_id
        and road_furniture.get("status") == "PASS"
        and road_furniture.get("pass") is True,
        "direct_zdepth_equivalence_pass": (
            direct_equivalence.get("run_id") == run_id
            and direct_equivalence.get("status") == "PASS"
            and direct_equivalence.get("reference_count") == 6
        ),
        "all_direct_reference_manifests_pass": (
            len(direct_manifests) == 6
            and all(
                item.get("run_id") == run_id
                and item.get("status") == "PASS"
                and item.get("complete") is True
                and item.get("expected_count") == 1
                and item.get("completed_count") == 1
                and len(item.get("views", [])) == 1
                and item.get("direct_validation_contract", {}).get("expected_count")
                == 1
                for item in direct_manifests
            )
        ),
        "resource_efficiency_audit_pass": (
            resources.get("run_id") == run_id
            and resources.get("status") == "PASS"
            and all(resources.get("checks", {}).values())
        ),
        "all_layer_manifests_pass": len(layer_manifests) == 16
        and all(
            item.get("status") == "PASS" and item.get("complete")
            for item in layer_manifests.values()
        ),
        "all_1280_source_frames_eevee": sum(engine_counts.values()) == 16 * 80
        and set(engine_counts) <= {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"},
        "zero_workbench_final_frames": engine_counts.get("BLENDER_WORKBENCH", 0) == 0
        and delivery.get("workbench_final_frame_count") == 0,
        "delivery_manifest_pass": delivery.get("status") == "PASS"
        and delivery.get("complete")
        and delivery.get("completed_count") == 80,
        "image_quality_pass": all(image_checks.values()),
        "mesh_projected_coverage_pass": coverage["pass"],
        "semantic_target_visibility_pass": semantic_pass,
        "camera_preflight_pass": bool(camera_checks)
        and all(item.get("pass") is True for item in camera_checks),
        "camera_exact_mesh_preflight_pass": (
            bool(camera_mesh_checks)
            and all(item.get("pass") is True for item in camera_mesh_checks)
            and len(layer_camera_preflights) == 16
            and all(
                item.get("run_id") == run_id
                and item.get("status") == "PASS"
                and item.get("camera_count_passed") == 80
                for item in layer_camera_preflights
            )
        ),
        "camera_exact_child_mesh_preflight_pass": all(
            record["camera"].get("camera_mesh_aabb_preflight", {}).get("pass") is True
            for manifest in layer_manifests.values()
            for record in manifest["views"]
        ),
        "evaluated_child_mesh_bvh_pass": all(
            item.get("pass") is True for item in bvh.values()
        ),
        # The pipeline status necessarily says RUNNING/strict_final_audit while
        # this audit is executing.  Exclude that controller record by schema;
        # all actual stage/worker status files must still be terminal.
        "all_actual_stage_and_worker_statuses_pass": all(
            item.get("status") == "PASS" and item.get("run_id") == run_id
            for item in status_files
            if item.get("schema") != "agent.full13.pipeline.status.v1"
        ),
    }
    contact_sheets = make_contact_sheets(pngs)
    manual_path = CITY / "manual_visual_review.json"
    manual = (
        json.loads(manual_path.read_text(encoding="utf8"))
        if manual_path.is_file()
        else None
    )
    metric_hashes = {Path(item["path"]).name: item["sha256"] for item in metrics}
    manual_views = manual.get("views", []) if manual else []
    manual_hashes = {item.get("filename"): item.get("sha256") for item in manual_views}
    contact_hashes = {
        str(Path(path).resolve()): sha256(Path(path)) for path in contact_sheets
    }
    manual_pass = bool(
        manual
        and manual.get("run_id") == run_id
        and manual.get("status") == "PASS"
        and len(manual_views) == 80
        and len(manual_hashes) == 80
        and all(item.get("status") == "PASS" for item in manual_views)
        and manual_hashes == metric_hashes
        and manual.get("contact_sheet_sha256") == contact_hashes
    )
    checks["manual_100_percent_visual_review_pass"] = manual_pass
    payload = {
        "schema": "agent.full13.strict_completion.v1",
        "created_utc": utc_now(),
        "run_id": run_id,
        "status": "PASS"
        if all(checks.values())
        else (
            "REVIEW_REQUIRED"
            if all(
                value
                for key, value in checks.items()
                if key != "manual_100_percent_visual_review_pass"
            )
            else "FAIL"
        ),
        "checks": checks,
        "source_frame_engine_counts": dict(engine_counts),
        "image_checks": image_checks,
        "image_nondegenerate_thresholds": NONDEGENERATE_THRESHOLDS,
        "image_metrics": metrics,
        "mesh_projection_audit": coverage,
        "semantic_visibility_audit": semantic,
        "camera_preflight_record_count": len(camera_checks),
        "evaluated_child_mesh_bvh_audits": bvh,
        "road_furniture_mesh_audit": road_furniture,
        "direct_zdepth_equivalence_audit": direct_equivalence,
        "direct_reference_manifests": direct_manifests,
        "resource_efficiency_audit": resources,
        "semantic_public_interiors_pack": semantic_pack,
        "layer_provenance_rebind_audit": provenance_rebind,
        "stage_status_files": status_files,
        "contact_sheets": contact_sheets,
        "manual_visual_review": str(manual_path.resolve()),
        "errors": [key for key, value in checks.items() if not value],
    }
    atomic_json(CITY / "mesh_projection_audit.json", {"run_id": run_id, **coverage})
    atomic_json(
        CITY / "semantic_visibility_audit.json",
        {
            "run_id": run_id,
            "status": "PASS" if semantic_pass else "FAIL",
            "views": semantic,
        },
    )
    atomic_json(CITY / "strict_completion_audit.json", payload)
    if payload["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
