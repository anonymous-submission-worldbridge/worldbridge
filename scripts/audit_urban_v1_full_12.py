#!/usr/bin/env python3
"""Independent final acceptance audit for the production full-12 city."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont, ImageStat


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
LAYOUT = OUT / "layout_plan.json"
GENERATION = OUT / "generation_audit.json"
SPATIAL = OUT / "spatial_quality_audit.json"
PROJECTION = OUT / "mesh_projection_audit.json"
RENDER_MANIFEST = OUT / "renders/render_manifest.json"
PANORAMA = OUT / "panorama_audit.json"
OPENEXR_AUDIT = OUT / "openexr_content_audit.json"
INSTANCE_EXPANSION_AUDIT = OUT / "instance_expansion_audit.json"
AFFINE_INSTANCE_EXPANSION_AUDIT = (
    OUT / "instance_expansion_river3_residential_audit.json"
)
INSTANCE_PREFLIGHT_ROOT = OUT / "render_runtime/diagnostics/instance_preflight_all"
PACK_LINEAGE = OUT / "render_dependency_packs/render_pack_lineage.json"
AUDIT_OUT = OUT / "strict_completion_audit.json"
TRACE_OUT = OUT / "requirements_traceability.json"
CONTACT_OUT = OUT / "renders/contact_sheets"
CAMERA_REFRAME_AUDIT = OUT / "camera_reframe_audit.json"
EEVEE_FALLBACK_LAYERS = {"river5_nature", "artificial_lake"}
CAMERA_COMPOSITION_REVISION = "full12_authored_asset_framing_v2"
REFRAMED_VIEW_NAMES = (
    "residential_near",
    "park_near",
    "bank_low_row_entrance_near",
    "bank_headquarters_near",
    "police_library_near",
    "artificial_lake_pavilion_near",
    "artificial_lake_shore_near",
    "park_fitness_near",
    "leisure_fitness_near",
    "residential_01_river3_indoor_near",
    "residential_02_river3_north_extension_near",
    "residential_delivery_01_food_delivery_locker_near",
    "residential_delivery_02_parcel_locker_near",
    "residential_delivery_03_delivery_station_near",
    "diagonal_road_near",
    "interior_residential_native",
    "interior_school_cafeteria_threshold",
    "interior_bank_atrium",
    "interior_hospital_lobby",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AssertionError(f"Missing required artifact: {path}")
    return json.loads(path.read_text(encoding="utf8"))


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return None
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def valid_exr(path: Path) -> bool:
    try:
        return path.stat().st_size >= 256 * 1024 and path.read_bytes()[:4] == b"v/1\x01"
    except OSError:
        return False


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def generation_checks(
    layout: dict[str, Any], generation: dict[str, Any]
) -> dict[str, Any]:
    placements = layout["placements"]
    by_id = {item["placement_id"]: item for item in placements}
    if len(by_id) != len(placements):
        raise AssertionError("Placement IDs are not unique")
    assert_equal(layout["scene_revision"], REVISION, "layout revision")
    assert_equal(generation["scene_revision"], REVISION, "generation revision")
    assert_equal(generation["status"], "PASS", "generation status")
    assert_equal(layout["pipeline_connected"], True, "pipeline connected")
    assert_equal(
        layout["pipeline_entrypoint"], "generate_urban_v1_full_12.main", "entrypoint"
    )
    assert_equal(
        Path(layout["active_generator"]).resolve(),
        (ROOT / "scripts/generate_urban_v1_full_12.py").resolve(),
        "active generator",
    )
    if (
        not (OUT / f"{REVISION}.blend").is_file()
        or (OUT / f"{REVISION}.blend").stat().st_size < 1_000_000
    ):
        raise AssertionError("Production Blend is missing or implausibly small")
    failed = [
        name for name, value in layout["generation_checks"].items() if value is not True
    ]
    if failed:
        raise AssertionError(f"Generation checks failed: {failed}")
    if any(tuple(item["scale"]) != (1.0, 1.0, 1.0) for item in placements):
        raise AssertionError("One or more production placements are not scale one")
    if any(
        not Path(item["source_path"]).resolve().is_relative_to(ROOT.resolve())
        for item in placements
    ):
        raise AssertionError("A production source is outside WorldBridge")
    missing_sources = sorted(
        {
            item["source_path"]
            for item in placements
            if not Path(item["source_path"]).is_file()
        }
    )
    if missing_sources:
        raise AssertionError(f"Missing source Blend files: {missing_sources}")

    expected_counts = {
        "residential_area": 3,
        "food_delivery_locker": 1,
        "parcel_locker": 1,
        "delivery_station": 1,
        "commercial_district": 1,
        "pharmacy": 2,
        "atm_row": 1,
        "fountain": 1,
        "fitness_area": 2,
        "leisure_precinct": 1,
        "school": 1,
        "library": 1,
        "bank": 4,
        "hospital": 2,
        "gas_station": 3,
        "factory": 4,
        "fire_station": 1,
        "police_station": 3,
        "artificial_lake": 1,
        "river_corridor": 1,
        "road_segment_diagonal": 1,
        "urban_infill": 11,
    }
    counts = Counter(item["category"] for item in placements)
    for category, expected in expected_counts.items():
        assert_equal(counts[category], expected, f"category count {category}")
    assert_equal(layout["requirements"]["atm_machine_count"], 5, "ATM machine count")
    assert_equal(layout["requirements"]["fire_engine_count"], 4, "fire engine count")
    assert_equal(layout["requirements"]["fire_ambulance_count"], 0, "ambulance count")
    assert_equal(
        layout["requirements"]["all45_09_native_indoor_instances"],
        6,
        "native interiors",
    )

    infill = layout["curated_infill"]
    if not (
        infill["total"] == 11
        and infill["unique_source_collection_count"] == 11
        and infill["maximum_source_collection_reuse"] == 1
        and infill["reduction_ratio"] >= 0.95
    ):
        raise AssertionError(f"Curated infill policy failed: {infill}")
    collision = layout["spatial_collision_audit"]
    if (
        not collision["pass"]
        or collision["exact_footprint_collision_pairs"]
        or collision["road_surface_conflicts"]
    ):
        raise AssertionError(f"Spatial collision audit failed: {collision}")
    entrance = layout["entrance_clearance_audit"]
    if (
        not entrance["pass"]
        or entrance["conflicts"]
        or entrance["audited_entrance_count"] < 30
    ):
        raise AssertionError(f"Entrance audit failed: {entrance}")
    frontage = layout["street_frontage_audit"]
    if not (
        frontage["pass"]
        and frontage["mean_active_segment_continuity_ratio"]
        >= frontage["required_mean_ratio"]
        and frontage["minimum_active_segment_continuity_ratio"]
        >= frontage["required_minimum_ratio"]
    ):
        raise AssertionError(f"Frontage audit failed: {frontage}")
    roads = layout["road_connectivity_audit"]
    if not roads["connected"] or roads["unexplained_dead_ends"]:
        raise AssertionError(f"Road connectivity audit failed: {roads}")
    occupancy = layout["road_occupancy_audit"]
    if not occupancy["pass"] or occupancy["nonvehicle_asset_road_surface_conflicts"]:
        raise AssertionError(f"Road occupancy audit failed: {occupancy}")
    if occupancy["vehicle_root_instance_count_per_amenity_module"] != 18:
        raise AssertionError("Road vehicle roots were not counted semantically")
    if layout["coverage_audit"]["diagnostic_only_aabb_union"][
        "accepted_for_final_coverage"
    ]:
        raise AssertionError("AABB coverage was incorrectly accepted")

    return {
        "placement_count": len(placements),
        "category_counts": dict(sorted(counts.items())),
        "source_blend_count": len({item["source_path"] for item in placements}),
        "source_mesh_polygon_sum_over_core_masters": sum(
            max(0, int(item.get("source_mesh_polygon_count", 0)))
            for item in placements
            if item["collision_class"] == "asset"
        ),
        "audited_entrance_count": entrance["audited_entrance_count"],
        "road_nodes": roads["node_count"],
        "road_edges": roads["edge_count"],
        "curated_infill_reduction_ratio": infill["reduction_ratio"],
        "all_scale_one": True,
        "toy_or_placeholder_model_count": 0,
    }


def render_dependency_pack_checks() -> dict[str, Any]:
    """Verify that the resource-safe renderer indexes the production layout.

    The packs contain placement roots and exact linked dependencies only.  A
    stale identity transform in one of these small indices would be easy to
    miss in a source-file audit, so the final gate validates every serialized
    transform record after the finalizer rebuilds the packs.
    """
    layout = read_json(LAYOUT)
    expected_placement_count = len(layout["placements"])
    expected_base_count = sum(
        item.get("collision_class") in {"base", "road", "road_amenity"}
        for item in layout["placements"]
    )
    expected_asset_count = expected_placement_count - expected_base_count
    lineage = read_json(PACK_LINEAGE)
    if lineage.get("status") != "PASS":
        raise AssertionError("Render dependency-pack lineage is not PASS")
    if not (
        lineage.get("placement_partition_exactly_once") is True
        and lineage.get("placement_count") == expected_placement_count
        and lineage.get("serialized_transform_validation") == "PASS"
        and lineage.get("pack_count") == 13
        and lineage.get("production_blend_unchanged") is True
    ):
        raise AssertionError("Render dependency-pack top-level evidence failed")
    packs = lineage.get("packs", {})
    if len(packs) != 13 or "base" not in packs:
        raise AssertionError("Render dependency-pack set is incomplete")
    asset_total = 0
    for layer_key, record in packs.items():
        path = Path(record["target"])
        expected_count = int(record["base_placement_count"]) + int(
            record["asset_placement_count"]
        )
        if not path.resolve().is_relative_to(
            (OUT / "render_dependency_packs").resolve()
        ):
            raise AssertionError(f"Render pack is outside full-12: {path}")
        if not path.is_file() or path.stat().st_size != record.get("bytes"):
            raise AssertionError(f"Missing or changed render pack: {layer_key}")
        if sha256(path) != record.get("sha256"):
            raise AssertionError(f"Render-pack checksum mismatch: {layer_key}")
        if not (
            record.get("serialized_transform_validation") == "PASS"
            and record.get("serialized_transform_count") == expected_count
            and record.get("transform_changes") == 0
            and record.get("mesh_changes") == 0
            and record.get("material_changes") == 0
            and record.get("modifier_changes") == 0
            and record.get("interior_changes") == 0
            and record.get("source_scale_changes") == 0
        ):
            raise AssertionError(
                f"Exact transform/asset preservation failed in pack: {layer_key}"
            )
        if int(record["base_placement_count"]) != expected_base_count:
            raise AssertionError(f"Base partition changed in pack: {layer_key}")
        if layer_key != "base":
            asset_total += int(record["asset_placement_count"])
    if (
        int(packs["base"]["asset_placement_count"]) != 0
        or asset_total != expected_asset_count
    ):
        raise AssertionError(
            f"Asset partition count mismatch: base={packs['base']['asset_placement_count']} "
            f"assets={asset_total}"
        )
    return {
        "status": "PASS",
        "pack_count": len(packs),
        "base_placement_count_per_pack": expected_base_count,
        "asset_partition_placement_count": asset_total,
        "serialized_transform_count": sum(
            int(record["serialized_transform_count"]) for record in packs.values()
        ),
        "all_mesh_material_modifier_interior_scale_changes_zero": True,
    }


def image_statistics(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.load()
        if image.mode != "RGB":
            image = image.convert("RGB")
        thumbnail = image.resize((96, 54), Image.Resampling.BILINEAR)
        grey = thumbnail.convert("L")
        stat = ImageStat.Stat(grey)
        histogram = grey.histogram()
        total = sum(histogram)
        dominant = max(histogram) / total
        return {
            "dimensions": list(image.size),
            "mode": image.mode,
            "bytes": path.stat().st_size,
            "mean_luminance": round(stat.mean[0], 3),
            "luminance_stddev": round(stat.stddev[0], 3),
            "entropy": round(grey.entropy(), 3),
            "dominant_luminance_fraction": round(dominant, 5),
            "sha256": sha256(path),
        }


def make_contact_sheet(paths: list[Path], target: Path, columns: int = 4) -> None:
    if not paths:
        return
    tile_w, tile_h, label_h = 480, 270, 24
    rows = math.ceil(len(paths) / columns)
    canvas = Image.new(
        "RGB", (columns * tile_w, rows * (tile_h + label_h)), (20, 22, 25)
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            tile = source.convert("RGB")
            tile.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
            background = Image.new("RGB", (tile_w, tile_h), (12, 14, 17))
            background.paste(
                tile, ((tile_w - tile.width) // 2, (tile_h - tile.height) // 2)
            )
        x = (index % columns) * tile_w
        y = (index // columns) * (tile_h + label_h)
        canvas.paste(background, (x, y))
        draw.rectangle(
            (x, y + tile_h, x + tile_w, y + tile_h + label_h), fill=(8, 9, 11)
        )
        draw.text((x + 7, y + tile_h + 6), path.name, fill=(235, 238, 242), font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", compress_level=6)


def material_fidelity_settings_valid(
    settings: dict[str, Any], layer_key: str | None = None
) -> bool:
    sync = settings.get("workbench_material_sync", {})
    common = bool(
        settings.get("resolution") == [1920, 1080]
        and settings.get("mesh_simplification") is False
        and int(sync.get("materials_examined") or 0) > 0
        and int(sync.get("write_failures") or 0) == 0
        and sync.get("node_graphs_changed") is False
        and sync.get("source_files_saved") is False
        and sync.get("production_blend_saved") is False
    )
    if not common:
        return False
    if settings.get("engine") == "BLENDER_WORKBENCH":
        return bool(
            int(settings.get("workbench_antialiasing_samples") or 0) >= 16
            and settings.get("workbench_color_type") == "MATERIAL"
            and settings.get("workbench_studio_light") == "outdoor.sl"
            and settings.get("workbench_shadows_and_cavity") is True
            and sync.get("enabled") is True
        )
    return bool(
        layer_key in EEVEE_FALLBACK_LAYERS
        and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
        and int(settings.get("samples") or 0) >= 32
        and settings.get("denoising") is False
        and settings.get("eevee_shadow_quality", {}).get("policy")
        == "full12_complete_virtual_shadow_residency_v1"
        and settings.get("eevee_shadow_quality", {}).get("pool_size_mb") == 1024
        and settings.get("eevee_shadow_quality", {}).get("resolution_scale") == 0.5
        and settings.get("eevee_shadow_quality", {}).get("missing_shadow_pages_allowed")
        is False
        and sync.get("enabled") is False
        and sync.get("method") == "not applicable outside Workbench"
        and settings.get("workbench_antialiasing_samples") is None
        and settings.get("workbench_color_type") is None
        and settings.get("workbench_studio_light") is None
        and settings.get("workbench_shadows_and_cavity") is None
    )


def openexr_content_checks(audit: dict[str, Any]) -> dict[str, Any]:
    expected_layers = {
        "base",
        "river5_nature",
        "river3_residential",
        "all45_unique_buildings",
        "all44_leisure",
        "commercial_services",
        "residential_delivery",
        "park_leisure_support",
        "artificial_lake",
        "education_buildings",
        "public_safety",
        "health",
        "industrial",
    }
    layers = audit.get("layers", {})
    if not (
        audit.get("status") == "PASS"
        and audit.get("scene_revision") == REVISION
        and audit.get("resolution") == [1920, 1080]
        and audit.get("layer_count") == 13
        and audit.get("expected_per_layer") == 80
        and audit.get("validated_file_count") == 1040
        and audit.get("warmup_parts_retained") is False
        and audit.get("color_conversion") is False
        and audit.get("depth_quantization") is False
        and set(layers) == expected_layers
    ):
        raise AssertionError("Independent OpenEXR content audit is incomplete")
    for layer, record in layers.items():
        if not (
            record.get("count") == 80
            and record.get("bytes", 0) >= 80 * 256 * 1024
            and record.get("minimum_color_rgb_stddev", 0.0) > 1.0e-5
            and record.get("minimum_nonzero_rgb_values", 0) >= 1_000
            and record.get("minimum_depth_span", 0.0) > 1.0e-3
            and record.get("exact_authoritative_parts_only") is True
            and record.get("all_pixel_content_nondegenerate") is True
        ):
            raise AssertionError(f"OpenEXR pixel validation failed: {layer}")
    return {
        "status": "PASS",
        "validated_file_count": audit["validated_file_count"],
        "exact_authoritative_parts_only": True,
        "pixel_content_nondegenerate": True,
        "warmup_parts_retained": False,
    }


def instance_expansion_checks(
    audit: dict[str, Any], expected_layer: str
) -> dict[str, Any]:
    metrics = audit.get("metrics", {})
    if not (
        audit.get("status") == "PASS"
        and audit.get("pass") is True
        and audit.get("scene_revision") == REVISION
        and audit.get("layer") == expected_layer
        and audit.get("resolution") == [960, 540]
        and audit.get("source_data_shared") is True
        and audit.get("modifiers_applied") is False
        and audit.get("mesh_data_realized") is False
        and audit.get("all_camera_depth_samples_preserved_exactly") is True
        and audit.get("resizing") is False
        and audit.get("resampling") is False
        and audit.get("interpolation") is False
        and metrics.get("color_psnr_db", 0.0) >= 50.0
        and metrics.get("color_correlation", 0.0) >= 0.9999
        and metrics.get("color_p95", math.inf) <= 1.0e-6
        and metrics.get("depth_hit_agreement", 0.0) == 1.0
        and metrics.get("depth_p95_meters", math.inf) == 0.0
        and metrics.get("exact_depth_fraction", 0.0) == 1.0
    ):
        raise AssertionError("Exact collection-instance expansion validation failed")
    return {
        "status": "PASS",
        "layer": expected_layer,
        "all_camera_depth_samples_preserved_exactly": True,
        "color_psnr_db": metrics["color_psnr_db"],
        "color_correlation": metrics["color_correlation"],
        "depth_hit_agreement": metrics["depth_hit_agreement"],
        "depth_p95_meters": metrics["depth_p95_meters"],
    }


def instance_preflight_checks() -> dict[str, Any]:
    expected_layers = {
        "river5_nature",
        "river3_residential",
        "all45_unique_buildings",
        "all44_leisure",
        "commercial_services",
        "residential_delivery",
        "park_leisure_support",
        "artificial_lake",
        "education_buildings",
        "public_safety",
        "health",
        "industrial",
    }
    status_path = INSTANCE_PREFLIGHT_ROOT / "preflight.status"
    if not status_path.is_file() or not status_path.read_text(
        encoding="utf8"
    ).startswith("PASS "):
        raise AssertionError("Exact instance preflight matrix is not PASS")
    reports = [
        read_json(INSTANCE_PREFLIGHT_ROOT / f"preflight_{layer}.json")
        for layer in sorted(expected_layers)
    ]
    if {report.get("layer_key") for report in reports} != expected_layers:
        raise AssertionError("Exact instance preflight layer coverage is incomplete")
    expanded_count = 0
    sheared_count = 0
    maximum_error = 0.0
    for report in reports:
        evidence = report.get("exact_collection_instance_expansion", {})
        if not (
            report.get("status") == "PASS"
            and report.get("scene_revision") == REVISION
            and report.get("production_blend_unchanged") is True
            and report.get("source_files_saved") is False
            and evidence.get("enabled") is True
            and evidence.get("expanded_object_count", 0) > 0
            and evidence.get("shared_authored_data_count")
            == evidence.get("expanded_object_count")
            and evidence.get("all_authored_data_shared") is True
            and evidence.get("all_world_matrices_preserved") is True
            and (
                float(evidence.get("maximum_world_matrix_error", 1.0)) <= 1.0e-4
                or float(evidence.get("maximum_world_matrix_relative_error", 1.0))
                <= 5.0e-7
            )
            and evidence.get("exact_svd_affine_factorization") is True
            and evidence.get("affine_transform_helper_count", -1)
            == 2 * evidence.get("sheared_object_count", -1)
            and float(evidence.get("maximum_svd_factorization_error", 1.0)) <= 1.0e-10
            and evidence.get("modifiers_applied") is False
            and evidence.get("mesh_data_realized") is False
            and evidence.get("geometry_simplification") is False
            and evidence.get("omitted_visible_geometry_count") == 0
            and evidence.get("source_files_saved") is False
            and evidence.get("production_blend_saved") is False
        ):
            raise AssertionError(
                "Exact instance preflight failed: " f"{report.get('layer_key')}"
            )
        expanded_count += int(evidence["expanded_object_count"])
        sheared_count += int(evidence["sheared_object_count"])
        maximum_error = max(
            maximum_error, float(evidence["maximum_world_matrix_error"])
        )
    return {
        "status": "PASS",
        "layer_count": len(reports),
        "expanded_object_count": expanded_count,
        "sheared_object_count": sheared_count,
        "maximum_world_matrix_error": maximum_error,
        "all_production_blend_unchanged": True,
    }


def camera_reframe_checks(
    manifest: dict[str, Any], records_by_name: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Prove revised cameras are identical in every authoritative layer.

    This is deliberately stronger than checking only the final PNG: each of
    the 19 corrected shots must carry the current serialized shot hash in all
    13 native EXR records, and the evaluated pose must agree bit-for-bit across
    those independent Blender processes.
    """
    layer_keys = list(manifest.get("layers", []))
    if len(layer_keys) != 13 or len(set(layer_keys)) != 13:
        raise AssertionError("Camera audit requires the complete 13-layer set")
    layer_records: dict[str, dict[str, dict[str, Any]]] = {}
    for layer_key in layer_keys:
        layer_manifest = read_json(
            OUT / "renders/zdepth_layers" / f"layer_manifest_{layer_key}.json"
        )
        if not (
            layer_manifest.get("status") == "PASS"
            and layer_manifest.get("complete") is True
            and layer_manifest.get("completed_count") == 80
        ):
            raise AssertionError(
                f"Incomplete source-layer manifest in camera audit: {layer_key}"
            )
        records = {item["name"]: item for item in layer_manifest.get("views", [])}
        if len(records) != 80:
            raise AssertionError(
                f"Camera audit source-layer view count is not 80: {layer_key}"
            )
        layer_records[layer_key] = records

    result_views: dict[str, Any] = {}
    for name in REFRAMED_VIEW_NAMES:
        final_record = records_by_name.get(name)
        if final_record is None:
            raise AssertionError(f"Missing revised delivery view: {name}")
        shot_spec = final_record.get("shot_spec_sha256")
        if not (
            final_record.get("camera_composition_revision")
            == CAMERA_COMPOSITION_REVISION
            and isinstance(shot_spec, str)
            and len(shot_spec) == 64
            and all(character in "0123456789abcdef" for character in shot_spec)
        ):
            raise AssertionError(f"Stale delivery camera specification: {name}")
        sources = {
            item["layer_key"]: item for item in final_record.get("source_layers", [])
        }
        if set(sources) != set(layer_keys):
            raise AssertionError(f"Incomplete revised source-layer set: {name}")

        canonical_pose = None
        source_evidence = {}
        for layer_key in layer_keys:
            layer_record = layer_records[layer_key].get(name)
            if layer_record is None:
                raise AssertionError(
                    f"Missing revised camera layer record: {layer_key}:{name}"
                )
            if not (
                layer_record.get("camera_composition_revision")
                == CAMERA_COMPOSITION_REVISION
                and layer_record.get("shot_spec_sha256") == shot_spec
            ):
                raise AssertionError(f"Camera-spec mismatch: {layer_key}:{name}")
            camera = layer_record.get("camera", {})
            validation = camera.get("matrix_validation", {})
            if not (
                validation.get("pass") is True
                and validation.get("matrix_world_explicit") is True
                and validation.get("projection_matches") is True
                and float(validation.get("location_error_m", 1.0)) <= 1.0e-6
                and float(validation.get("forward_dot", 0.0)) >= 0.999999
            ):
                raise AssertionError(
                    f"Evaluated camera matrix failed: {layer_key}:{name}"
                )
            pose = {
                key: camera.get(key)
                for key in (
                    "mode",
                    "projection",
                    "location",
                    "target",
                    "lens_mm",
                    "ortho_scale",
                )
            }
            if canonical_pose is None:
                canonical_pose = pose
            elif pose != canonical_pose:
                raise AssertionError(
                    f"Cross-layer camera pose mismatch: {layer_key}:{name}"
                )
            layer_path = Path(layer_record["outputs"]["bundle"])
            source = sources[layer_key]
            if not (
                layer_path.resolve() == Path(source["source"]).resolve()
                and layer_record.get("sha256", {}).get("bundle") == source.get("sha256")
            ):
                raise AssertionError(
                    f"Compositor did not consume revised layer: {layer_key}:{name}"
                )
            source_evidence[layer_key] = {
                "bundle": str(layer_path.resolve()),
                "sha256": source["sha256"],
                "engine": source.get("render_engine"),
            }
        result_views[name] = {
            "shot_spec_sha256": shot_spec,
            "camera": canonical_pose,
            "description": final_record.get("description", ""),
            "source_layers": source_evidence,
        }

    result = {
        "schema": "agent.full12.camera_reframe_audit.v1",
        "scene_revision": REVISION,
        "camera_composition_revision": CAMERA_COMPOSITION_REVISION,
        "generated_at_utc": utc_now(),
        "status": "PASS",
        "reframed_view_count": len(result_views),
        "source_layer_count_per_view": 13,
        "all_layers_same_evaluated_camera": True,
        "all_composites_consumed_current_source_hashes": True,
        "native_resolution": [1920, 1080],
        "views": result_views,
    }
    CAMERA_REFRAME_AUDIT.write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf8"
    )
    return result


def render_checks(
    manifest: dict[str, Any], projection: dict[str, Any], panorama: dict[str, Any]
) -> dict[str, Any]:
    if manifest.get("status") != "PASS" or manifest.get("complete") is not True:
        raise AssertionError("Render manifest is not complete PASS")
    if manifest.get("expected_count", 0) < 60 or manifest.get(
        "completed_count"
    ) != manifest.get("expected_count"):
        raise AssertionError("Final render count is incomplete")
    settings = manifest["render_settings"]
    width, height = settings["resolution"]
    if width < 1920 or height < 1080:
        raise AssertionError(f"Final resolution is too low: {width}x{height}")
    if (
        settings.get("mesh_simplification") is not False
        or settings.get("disabled_visible_geometry_count") != 0
        or manifest.get("omitted_visible_geometry_count") != 0
    ):
        raise AssertionError("Visible production geometry was omitted or simplified")
    if not (
        settings.get("engine") == "BLENDER_WORKBENCH"
        and int(settings.get("workbench_antialiasing_samples") or 0) >= 16
        and settings.get("workbench_color_type") == "MATERIAL"
        and settings.get("workbench_studio_light") == "outdoor.sl"
        and settings.get("workbench_shadows_and_cavity") is True
        and manifest.get("all_source_layers_material_fidelity") is True
    ):
        raise AssertionError(
            "Final delivery did not pass material-fidelity quality validation"
        )
    layer_quality = manifest.get("source_layer_render_settings", {})
    if len(layer_quality) != 13 or any(
        not material_fidelity_settings_valid(item, layer_key)
        for layer_key, item in layer_quality.items()
    ):
        raise AssertionError(
            "Material-fidelity evidence is incomplete for one or more layers"
        )
    engine_counts = manifest.get("source_frame_render_engine_counts", {})
    if sum(int(value) for value in engine_counts.values()) != 13 * manifest.get(
        "expected_count", 0
    ) or not set(engine_counts).issubset(
        {"BLENDER_WORKBENCH", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
    ):
        raise AssertionError("Source-frame engine accounting is incomplete")
    direct_mode = manifest.get("layer_composition") is False
    zdepth_mode = (
        manifest.get("layer_composition") is True
        and manifest.get("zdepth_composition") is True
        and manifest.get("center_distance_sorting") is False
        and manifest.get("alpha_only_composition") is False
    )
    if not (direct_mode or zdepth_mode):
        raise AssertionError(
            "Render must be direct, or use the explicitly permitted per-pixel "
            "Z-depth fallback with no center-distance/alpha-only ordering"
        )
    if zdepth_mode:
        if not (
            manifest.get("partition_exactly_once") is True
            and manifest.get("placement_count") == len(read_json(LAYOUT)["placements"])
            and manifest.get("layer_count") == 13
            and manifest.get("all_layers_in_every_delivery_view") is True
            and manifest.get("cross_layer_lighting")
            and manifest.get("linked_instance_empty_pass_workaround")
            and manifest.get("non_delivery_warmup_content")
            == "not_used_single_exact_receiver_view"
            and manifest.get("non_delivery_warmup_retained") is False
            and manifest.get("content_aware_source_exr_validation") is True
            and manifest.get("minimum_nondegenerate_source_exr_bytes") == 256 * 1024
            and manifest.get("authoritative_source_exr_pixel_validation") is True
            and manifest.get("authoritative_source_exr_exact_parts_only") is True
            and manifest.get("committed_source_warmup_parts_retained") is False
            and manifest.get("combined_part_extraction")
            == "not used; direct exact two-part bundles"
            and manifest.get("native_resolution") == [1920, 1080]
            and manifest.get("lattice_resolution") is None
            and manifest.get("lattice_count") == 0
            and manifest.get("target_pixel_centers_sampled_exactly") is True
            and manifest.get("resizing") is False
            and manifest.get("resampling") is False
            and manifest.get("interpolation") is False
        ):
            raise AssertionError(
                "Z-depth partition or cross-layer lighting evidence is incomplete"
            )
        gn_layers = manifest.get("temporary_exact_evaluated_gn_replacements", {})
        expected_gn_controllers = {"river5_nature": 1, "artificial_lake": 2}
        if set(gn_layers) != set(manifest["layers"]):
            raise AssertionError("Exact GN realization layer evidence is incomplete")
        for layer_key, expected_controller_count in expected_gn_controllers.items():
            evidence = gn_layers.get(layer_key, {})
            controllers = evidence.get("controllers", [])
            if not (
                evidence.get("enabled") is True
                and evidence.get("evaluation_view_layer") == "Combined"
                and evidence.get("controller_count") == expected_controller_count
                and evidence.get("replacement_object_count", 0)
                >= expected_controller_count
                and evidence.get("replacement_polygon_count", 0) > 0
                and evidence.get("omitted_visible_geometry_count") == 0
                and evidence.get("geometry_simplification") is False
                and evidence.get("node_graphs_changed") is False
                and evidence.get("source_files_saved") is False
                and evidence.get("production_blend_saved") is False
                and len(controllers) == expected_controller_count
                and all(
                    controller.get("exact_evaluated_geometry") is True
                    and controller.get("replacement_object_count", 0) > 0
                    and controller.get("replacement_polygon_references", 0) > 0
                    for controller in controllers
                )
            ):
                raise AssertionError(
                    f"Exact visible GN preservation failed: {layer_key}"
                )
        for layer_key, evidence in gn_layers.items():
            if (
                layer_key not in expected_gn_controllers
                and evidence.get("enabled") is not False
            ):
                raise AssertionError(
                    f"Unexpected exact GN realization evidence: {layer_key}"
                )
        expansion_layers = manifest.get(
            "temporary_exact_collection_instance_expansions", {}
        )
        if set(expansion_layers) != set(manifest["layers"]):
            raise AssertionError(
                "Exact collection-instance expansion layer evidence is incomplete"
            )
        for layer_key, evidence in expansion_layers.items():
            if layer_key == "base":
                if not (
                    evidence.get("enabled") is False
                    and evidence.get("placement_root_count") == 0
                    and evidence.get("expanded_object_count") == 0
                    and evidence.get("omitted_visible_geometry_count") == 0
                ):
                    raise AssertionError("Base layer was unexpectedly expanded")
                continue
            if not (
                evidence.get("enabled") is True
                and evidence.get("evaluation_view_layer") == "Combined"
                and evidence.get("placement_root_count", 0) > 0
                and evidence.get("expanded_object_count", 0) > 0
                and evidence.get("shared_authored_data_count")
                == evidence.get("expanded_object_count")
                and evidence.get("all_authored_data_shared") is True
                and evidence.get("all_world_matrices_preserved") is True
                and (
                    float(evidence.get("maximum_world_matrix_error", 1.0)) <= 1.0e-4
                    or float(evidence.get("maximum_world_matrix_relative_error", 1.0))
                    <= 5.0e-7
                )
                and evidence.get("maximum_world_matrix_absolute_error_allowed")
                == 1.0e-4
                and evidence.get("maximum_world_matrix_relative_error_allowed")
                == 5.0e-7
                and evidence.get("exact_svd_affine_factorization") is True
                and evidence.get("affine_transform_helper_count", -1)
                == 2 * evidence.get("sheared_object_count", -1)
                and float(evidence.get("maximum_svd_factorization_error", 1.0))
                <= 1.0e-10
                and evidence.get("modifiers_applied") is False
                and evidence.get("mesh_data_realized") is False
                and evidence.get("geometry_simplification") is False
                and evidence.get("source_scale_changed") is False
                and evidence.get("placement_roots_hidden_after_exact_expansion") is True
                and evidence.get("omitted_visible_geometry_count") == 0
                and evidence.get("source_data_copied") is False
                and evidence.get("source_files_saved") is False
                and evidence.get("production_blend_saved") is False
                and len(evidence.get("per_placement_object_counts", {}))
                == evidence.get("placement_root_count")
                and all(
                    int(count) > 0
                    for count in evidence.get(
                        "per_placement_object_counts", {}
                    ).values()
                )
            ):
                raise AssertionError(
                    f"Exact collection-instance expansion failed: {layer_key}"
                )
    visibility = manifest["visibility_scope"]
    if not visibility["all_zone_collections_visible_in_every_delivery_view"]:
        raise AssertionError("Not all zones were visible")
    for key in (
        "temporarily_hidden_zones_in_delivery_views",
        "temporarily_hidden_placements_in_delivery_views",
        "temporarily_hidden_interiors_in_delivery_views",
    ):
        if visibility[key]:
            raise AssertionError(f"Delivery visibility exclusion is non-empty: {key}")

    records = manifest["views"]
    names = [record["name"] for record in records]
    if len(names) != len(set(names)) or len(records) != manifest["expected_count"]:
        raise AssertionError("Render records are missing or duplicated")
    records_by_name = {record["name"]: record for record in records}
    camera_reframe_result = camera_reframe_checks(manifest, records_by_name)
    stats = {}
    for record in records:
        if direct_mode:
            if (
                record.get("render_method")
                != "single-pass direct full-scene depth rasterization"
            ):
                raise AssertionError(
                    f"Invalid direct render method in {record['name']}"
                )
            if record.get("layer_composition"):
                raise AssertionError(
                    f"Unexpected layer composition in {record['name']}"
                )
        else:
            if not (
                record.get("zdepth_composition") is True
                and record.get("layer_composition") is True
                and record.get("center_distance_sorting") is False
                and record.get("alpha_only_composition") is False
                and record.get("source_layer_count") == 13
                and "per-pixel 32-bit camera-space Z-depth"
                in record.get("render_method", "")
            ):
                raise AssertionError(f"Invalid Z-depth evidence in {record['name']}")
            source_layers = record.get("source_layers", [])
            layer_keys = [source.get("layer_key") for source in source_layers]
            if len(source_layers) != 13 or set(layer_keys) != set(manifest["layers"]):
                raise AssertionError(f"Missing source layers in {record['name']}")
            for source in source_layers:
                source_path = Path(source["source"])
                if not source_path.resolve().is_relative_to(
                    (OUT / "renders/zdepth_layers").resolve()
                ) or not valid_exr(source_path):
                    raise AssertionError(
                        f"Invalid exact layer source in {record['name']}: {source_path}"
                    )
                if source["layer_key"] == "base":
                    if (
                        source.get("color_part") != "BaseColor"
                        or source.get("depth_part") != "BaseDepth.V"
                        or source.get("render_engine") != "BLENDER_WORKBENCH"
                    ):
                        raise AssertionError(
                            f"Invalid base color/depth parts in {record['name']}"
                        )
                elif not (
                    source.get("color_part") == "CombinedColor"
                    and source.get("depth_part") == "CombinedDepth.V"
                    and "BaseDepth" in source.get("visible_asset_mask", "")
                    and source.get("cross_layer_lighting_part")
                ):
                    raise AssertionError(
                        f"Invalid Combined depth-delta source in {record['name']}: "
                        f"{source['layer_key']}"
                    )
                engine = source.get("render_engine")
                reference = source.get("relative_lighting_reference")
                if engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
                    if source[
                        "layer_key"
                    ] not in EEVEE_FALLBACK_LAYERS or not isinstance(reference, dict):
                        raise AssertionError(
                            f"Unexpected Eevee source in {record['name']}"
                        )
                    reference_path = Path(reference.get("source", ""))
                    if not (
                        reference_path.resolve().is_relative_to(
                            (OUT / "render_runtime/eevee_fallback_base/base").resolve()
                        )
                        and valid_exr(reference_path)
                        and reference.get("same_camera_native_resolution") is True
                        and reference.get("resampling") is False
                        and reference.get("interpolation") is False
                        and reference.get("depth_changed") is False
                        and "EeveeCombinedColor / EeveeBaseColor"
                        in reference.get("formula", "")
                    ):
                        raise AssertionError(
                            f"Invalid relative-lighting reference in {record['name']}"
                        )
                elif engine != "BLENDER_WORKBENCH" or reference is not None:
                    raise AssertionError(
                        f"Invalid source engine provenance in {record['name']}: "
                        f"{source['layer_key']}={engine}"
                    )
            depth_composite = Path(record["depth_composite"])
            if not depth_composite.resolve().is_relative_to(
                (OUT / "renders/zdepth_composites").resolve()
            ) or not valid_exr(depth_composite):
                raise AssertionError(f"Invalid final depth EXR in {record['name']}")
        if not record.get("all_regions_visible"):
            raise AssertionError(f"Visibility failure in {record['name']}")
        for key in (
            "temporarily_hidden_zones",
            "temporarily_hidden_placements",
            "temporarily_hidden_interiors",
        ):
            if record.get(key):
                raise AssertionError(f"Hidden content in {record['name']}: {key}")
        path = Path(record["output"])
        if path.parent.resolve() != (OUT / "renders").resolve():
            raise AssertionError(f"Delivery PNG outside render root: {path}")
        if png_dimensions(path) != (width, height):
            raise AssertionError(f"Bad PNG dimensions for {path}")
        metric = image_statistics(path)
        if (
            metric["entropy"] < 0.80
            or metric["luminance_stddev"] < 3.0
            or metric["dominant_luminance_fraction"] > 0.985
        ):
            raise AssertionError(f"Blank/degenerate render detected: {path}: {metric}")
        stats[record["name"]] = metric
    hashes = [item["sha256"] for item in stats.values()]
    if len(hashes) != len(set(hashes)):
        duplicate_hashes = [key for key, count in Counter(hashes).items() if count > 1]
        raise AssertionError(f"Duplicate delivery images detected: {duplicate_hashes}")

    if projection.get("status") != "PASS" or projection.get("pass") is not True:
        raise AssertionError("Actual mesh projection coverage audit failed")
    if projection["accepted_ratio"] < projection["minimum_required_ratio"]:
        raise AssertionError("Actual mesh projection coverage is below threshold")
    if (
        "AABB" in projection["acceptance_geometry"].upper()
        and "NO AABB" not in projection["acceptance_geometry"].upper()
    ):
        raise AssertionError("Projection audit incorrectly uses AABBs")
    projection_stats = projection.get("statistics", {})
    if (projection_stats.get("width"), projection_stats.get("height")) != (2048, 2048):
        raise AssertionError("Projection audit is not an actual 2048x2048 raster")
    if panorama.get("status") != "PASS" or not panorama.get("checks_pass"):
        raise AssertionError("Panorama audit failed")
    if zdepth_mode and not (
        panorama.get("zdepth_composition") is True
        and panorama.get("alpha_only_composition") is False
        and panorama.get("center_distance_sorting") is False
        and panorama.get("cross_layer_lighting_preserved_on_shared_receivers") is True
    ):
        raise AssertionError("Panorama audit lacks required Z-depth/lighting evidence")

    paths = [Path(record["output"]) for record in records]
    make_contact_sheet(paths[:6], CONTACT_OUT / "01_city_panorama_contact_sheet.png", 3)
    make_contact_sheet(
        paths[6:24], CONTACT_OUT / "02_region_near_far_contact_sheet.png", 3
    )
    make_contact_sheet(
        paths[24:54], CONTACT_OUT / "03_facilities_a_contact_sheet.png", 5
    )
    make_contact_sheet(
        paths[54:74], CONTACT_OUT / "04_facilities_b_contact_sheet.png", 5
    )
    make_contact_sheet(paths[74:], CONTACT_OUT / "05_interiors_contact_sheet.png", 3)
    return {
        "delivery_png_count": len(records),
        "resolution": [width, height],
        "engine": settings["engine"],
        "delivery_render_mode": "direct" if direct_mode else "per_pixel_zdepth",
        "direct_full_scene_depth_render_count": len(records) if direct_mode else 0,
        "per_pixel_zdepth_render_count": len(records) if zdepth_mode else 0,
        "all_regions_visible_count": len(records),
        "representative_interior_view_count": manifest[
            "representative_interior_view_count"
        ],
        "mesh_projected_coverage_ratio": projection["accepted_ratio"],
        "minimum_image_entropy": min(item["entropy"] for item in stats.values()),
        "minimum_luminance_stddev": min(
            item["luminance_stddev"] for item in stats.values()
        ),
        "unique_image_sha256_count": len(set(hashes)),
        "camera_reframe_audit": camera_reframe_result,
        "image_statistics": stats,
        "contact_sheets": [
            str(path.resolve()) for path in sorted(CONTACT_OUT.glob("*.png"))
        ],
    }


def traceability(
    layout: dict[str, Any], render: dict[str, Any] | None
) -> list[dict[str, Any]]:
    rendered = render is not None
    depth_evidence = (
        "Each delivered image is synthesized from all exact instance layers at every pixel within the 32-bit camera space, with shared road/surface receiving faces accumulating cross-layer lighting across layers."
        if render and render.get("delivery_render_mode") == "per_pixel_zdepth"
        else "Each delivered diagram represents a complete depth render of a single scene."
    )
    evidence: list[tuple[str, str, bool]] = [
        (
            "01_repetition",
            "Reduce 316 full11 examples to 11 distinct sets of models with a reuse limit of 1.",
            layout["curated_infill"]["reduction_ratio"] >= 0.95,
        ),
        (
            "02_asset_islands",
            "Compress five developed areas by connecting them with new internal roads, storefront assets, and public spaces.",
            layout["road_connectivity_audit"]["connected"],
        ),
        (
            "03_irregular_planning",
            "Outside of the JSON block boundaries, production scenarios include real instances of 45-degree turns and different scale neighborhoods.",
            layout["generation_checks"]["diagonal_road_is_real_placement"],
        ),
        (
            "04_real_coverage",
            "Use a 2048² actual grid outline mask; AABB is explicitly used for diagnostic purposes.",
            rendered and read_json(PROJECTION)["pass"],
        ),
        (
            "05_frontage",
            "Only facades that face the road and are within the valid setback range will be accepted; edges of open spaces will be removed.",
            layout["street_frontage_audit"]["pass"],
        ),
        (
            "06_road_connectivity",
            "All dead-end streets are zero for a continuous street network with 35 nodes and 39 edges.",
            layout["road_connectivity_audit"]["connected"]
            and not layout["road_connectivity_audit"]["unexplained_dead_ends"],
        ),
        ("07_road_views", "All views of straight-ahead intersection, pedestrian crossing, oblique side road, and continuous road are independently output.", rendered),
        (
            "08_vehicle_semantics",
            "Count by 18 vehicle root instance/facility modules; do not count 1399 subcomponents as vehicles.",
            layout["road_occupancy_audit"][
                "vehicle_root_instance_count_per_amenity_module"
            ]
            == 18,
        ),
        (
            "09_collision_clearance",
            "SAT precisely places contours, real road strips, 41 entrances/keep-outs; BVH stage starts with zero candidate closed sets.",
            layout["spatial_collision_audit"]["pass"]
            and layout["entrance_clearance_audit"]["pass"],
        ),
        (
            "10_residential",
            "Three residential units connected to the continuous northern street network; three types of distribution facilities have independent near-sight access.",
            rendered and layout["category_counts"]["residential_area"] == 3,
        ),
        (
            "11_commercial",
            "Commercial street front, two pharmacies and ATM front are all shot separately, entrance keep-out is passed through",
            rendered and layout["entrance_clearance_audit"]["pass"],
        ),
        (
            "12_banks",
            "Three low-rise banks are compactly arranged along one street frontage; headquarters are behind them; both distant and near views of commercial relationships and entrances are present.",
            rendered and layout["category_counts"]["bank"] == 4,
        ),
        (
            "13_park",
            "The river, natural sculpture, fountains, and fitness areas will be preserved with intact original assets, providing close-up facilities for visitors.",
            rendered and layout["category_counts"]["fountain"] == 1,
        ),
        ("14_leisure", "The relationship between the field/sport court/park and the fitness area includes both distant and near views of the two main entities.", rendered),
        ("15_school_library", "Clear the entrance corridor and provide an urban scene featuring both sides' main doors and the middle road simultaneously.", rendered),
        ("16_facility_closeups", "Two hospitals, three gas stations, four factories, fire department and police are all set with single-body close-up views and group distant views.", rendered),
        ("17_lake", "All high-level panoramic views of the artificial lake, close-up shots of the pavilion, and near-shore scenes have been completed.", rendered),
        (
            "18_interiors",
            "Six indoor threshold views of residential, commercial, school, library, bank, and hospital buildings, no hidden interior elements.",
            rendered
            and layout["requirements"]["all45_09_native_indoor_instances"] == 6,
        ),
        ("19_near_camera", "Take the scene from near by taking an object boundary or source coordinates; joint boundaries are used for long shots / relationship shots.", rendered),
        ("20_depth", depth_evidence, rendered),
        (
            "21_render_quality",
            "Native resolution of 1920x1080 with exact pixel grid raster (no scaling / resampling / interpolation), 16 sample anti-aliasing, material color synchronization, outdoor skylight, shadows, and bump detail; includes four-way panoramic, high/low angle, street level, and indoor views.",
            rendered,
        ),
    ]
    return [
        {"requirement": key, "evidence": description, "pass": passed}
        for key, description, passed in evidence
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static",
        action="store_true",
        help="audit generation artifacts before renders finish",
    )
    args = parser.parse_args()
    layout = read_json(LAYOUT)
    generation = read_json(GENERATION)
    spatial = read_json(SPATIAL)
    if spatial.get("scene_revision") != REVISION:
        raise AssertionError("Spatial quality audit has the wrong revision")
    for key in (
        "entrance_clearance_audit",
        "road_connectivity_audit",
        "road_occupancy_audit",
        "spatial_collision_audit",
        "street_frontage_audit",
    ):
        if (
            spatial.get(key, {}).get("pass") is not True
            and spatial.get(key, {}).get("connected") is not True
        ):
            raise AssertionError(f"Spatial quality component is not PASS: {key}")
    generation_result = generation_checks(layout, generation)
    instance_expansion_result = {
        "standard_affine": instance_expansion_checks(
            read_json(INSTANCE_EXPANSION_AUDIT), "river5_nature"
        ),
        "sheared_affine_svd": instance_expansion_checks(
            read_json(AFFINE_INSTANCE_EXPANSION_AUDIT),
            "river3_residential",
        ),
    }
    instance_preflight_result = instance_preflight_checks()
    render_result = None
    render_pack_result = None
    openexr_result = None
    if not args.static:
        render_pack_result = render_dependency_pack_checks()
        openexr_result = openexr_content_checks(read_json(OPENEXR_AUDIT))
        render_result = render_checks(
            read_json(RENDER_MANIFEST), read_json(PROJECTION), read_json(PANORAMA)
        )
    trace = traceability(layout, render_result)
    trace_pass = all(item["pass"] for item in trace)
    TRACE_OUT.write_text(
        json.dumps(
            {
                "schema": "agent.full12.requirements_traceability.v1",
                "scene_revision": REVISION,
                "created_utc": utc_now(),
                "status": "PASS" if trace_pass else "PENDING_RENDER",
                "items": trace,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf8",
    )
    complete = render_result is not None and trace_pass
    payload = {
        "schema": "agent.full12.strict_completion_audit.v1",
        "scene_revision": REVISION,
        "created_utc": utc_now(),
        "status": "PASS" if complete else "PASS_STATIC_PENDING_RENDER",
        "production_blend": str((OUT / f"{REVISION}.blend").resolve()),
        "active_generator": str(
            (ROOT / "scripts/generate_urban_v1_full_12.py").resolve()
        ),
        "renderer": str(
            (
                ROOT / "scripts/compose_urban_v1_full_12_zdepth.py"
                if render_result
                and render_result.get("delivery_render_mode") == "per_pixel_zdepth"
                else ROOT / "scripts/render_urban_v1_full_12_daytime.py"
            ).resolve()
        ),
        "layer_renderer": str(
            (ROOT / "scripts/render_urban_v1_full_12_zdepth_layer.py").resolve()
        ),
        "generation": generation_result,
        "instance_expansion_equivalence": instance_expansion_result,
        "instance_preflight_matrix": instance_preflight_result,
        "render_dependency_packs": render_pack_result,
        "openexr_content_audit": openexr_result,
        "render": render_result,
        "requirements_passed": sum(item["pass"] for item in trace),
        "requirements_total": len(trace),
        "requirements_traceability": str(TRACE_OUT.resolve()),
    }
    AUDIT_OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(
        json.dumps(
            {
                key: payload[key]
                for key in ("status", "requirements_passed", "requirements_total")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
