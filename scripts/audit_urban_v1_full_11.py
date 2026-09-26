#!/usr/bin/env python3
"""Strict read-only production audit for ``urban_v1_full_11``.

The established full-10 inspector performs the expensive reachable-geometry,
source-lineage, scale, collision, indoor, count, road-content, and spatial
relationship checks.  This active full-11 audit then adds lake3/fire7,
coverage, street-continuity, connected-road-graph, infill, and complete
all-regions-visible daytime-render checks.  The Blend is never saved.

Use ``-- structure-only`` while iterating before renders exist.  That mode
writes ``structure_completion_audit.json`` and deliberately removes SUCCESS.
The default mode creates SUCCESS only if every structural and render check
passes.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import bpy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_urban_v1_full_10 as base


REVISION = "urban_v1_full_11"
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
LAYOUT = OUT / "layout_plan.json"
RENDERS = OUT / "renders"
RENDER_MANIFEST = RENDERS / "render_manifest.json"

base.REVISION = REVISION
base.FALLBACK_OUT = OUT
base.EXPECTED_EXACT_COUNTS = dict(base.EXPECTED_EXACT_COUNTS)
base.EXPECTED_EXACT_COUNTS["artificial_lake"] = 1
base.SOURCE_TOKENS = dict(base.SOURCE_TOKENS)
base.SOURCE_TOKENS["fire_station"] = ("urban_v3_fire7",)
base.SOURCE_TOKENS["artificial_lake"] = ("urban_v3_lake3",)


EXPECTED_CITY_VIEWS = {
    "city_southwest",
    "city_southeast",
    "city_northwest",
    "city_northeast",
    "city_high_aerial",
    "city_top_down",
}
EXPECTED_ZONES = {
    "residential",
    "commercial",
    "park",
    "leisure",
    "education",
    "civic",
    "health",
    "industrial",
    "roads",
}
EXPECTED_FEATURES = {
    "school",
    "library",
    "bank",
    "hospital",
    "gas_station",
    "factory",
    "fire_police",
    "artificial_lake",
}


def script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def render_checks() -> tuple[dict[str, bool], dict[str, Any]]:
    if not RENDER_MANIFEST.is_file():
        return {
            "render_manifest_present": False,
            "render_catalogue_complete": False,
            "all_render_views_keep_every_region_visible": False,
            "six_city_panorama_views_present": False,
            "every_region_has_near_and_far_views": False,
            "every_required_feature_has_near_and_far_views": False,
            "all_png_outputs_are_nonempty_and_valid": False,
            "top_down_visible_asset_coverage_meets_target": False,
            "renderer_left_blend_unchanged": False,
        }, {"manifest": str(RENDER_MANIFEST), "error": "missing"}

    manifest = json.loads(RENDER_MANIFEST.read_text(encoding="utf8"))
    views = {
        str(record.get("name")): record
        for record in manifest.get("views", [])
        if record.get("name")
    }
    catalogue = {
        str(record.get("name")): record
        for record in manifest.get("catalogue", [])
        if record.get("name")
    }
    expected_names = set(catalogue)
    file_records = []
    files_valid = True
    for name in sorted(expected_names):
        record = views.get(name, catalogue[name])
        path = RENDERS / str(record.get("filename", ""))
        dimensions = png_dimensions(path)
        valid = bool(
            path.is_file()
            and path.stat().st_size >= 20_000
            and dimensions is not None
            and dimensions[0] >= 720
            and dimensions[1] >= 400
        )
        files_valid = files_valid and valid
        file_records.append(
            {
                "name": name,
                "path": str(path),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "dimensions": list(dimensions) if dimensions else None,
                "valid": valid,
            }
        )

    visibility = manifest.get("visibility_scope", {})
    visual_coverage = manifest.get("visual_coverage_audit", {})
    hidden_zones = visibility.get("temporarily_hidden_zones", [])
    hidden_placements = visibility.get("temporarily_hidden_placements", [])
    kept = set(visibility.get("kept_zones", []))
    completed = {
        name
        for name, record in views.items()
        if record.get("status") in {"rendered", "existing"}
        and (RENDERS / str(record.get("filename", ""))).is_file()
    }
    zone_pairs = {
        zone: {f"{zone}_near", f"{zone}_far"}.issubset(completed)
        for zone in EXPECTED_ZONES
    }
    feature_pairs = {
        feature: {f"{feature}_near", f"{feature}_far"}.issubset(completed)
        for feature in EXPECTED_FEATURES
    }
    checks = {
        "render_manifest_present": manifest.get("schema")
        == "agent.full11.daytime_render_manifest.v1",
        "render_catalogue_complete": bool(
            len(expected_names) >= 40
            and expected_names == completed
            and not manifest.get("errors")
            and manifest.get("complete") is True
        ),
        "all_render_views_keep_every_region_visible": bool(
            visibility.get("all_regions_visible") is True
            and not visibility.get("active", True)
            and not hidden_zones
            and not hidden_placements
            and EXPECTED_ZONES.issubset(kept)
        ),
        "six_city_panorama_views_present": EXPECTED_CITY_VIEWS.issubset(completed),
        "every_region_has_near_and_far_views": all(zone_pairs.values()),
        "every_required_feature_has_near_and_far_views": all(feature_pairs.values()),
        "all_png_outputs_are_nonempty_and_valid": bool(files_valid and file_records),
        "top_down_visible_asset_coverage_meets_target": bool(
            visual_coverage.get("top_down_non_base_pixel_coverage_ratio", 0)
            >= visual_coverage.get("required_top_down_non_base_pixel_coverage_ratio", 1)
        ),
        "renderer_left_blend_unchanged": manifest.get("blend_file_unchanged") is True,
    }
    return checks, {
        "manifest": str(RENDER_MANIFEST),
        "expected_count": len(expected_names),
        "completed_count": len(completed),
        "city_views": sorted(EXPECTED_CITY_VIEWS),
        "zone_pairs": zone_pairs,
        "feature_pairs": feature_pairs,
        "visual_coverage_audit": visual_coverage,
        "visibility_scope": visibility,
        "files": file_records,
    }


def full11_checks(
    layout: dict[str, Any], structure_only: bool
) -> tuple[dict[str, bool], dict[str, Any]]:
    placements = layout.get("placements", [])
    categories = Counter(str(record.get("category")) for record in placements)
    lake = [
        record for record in placements if record.get("category") == "artificial_lake"
    ]
    fire = [record for record in placements if record.get("category") == "fire_station"]
    infill = [
        record for record in placements if record.get("category") == "urban_infill"
    ]
    north_connector = [
        record
        for record in placements
        if str(record.get("placement_id", "")).startswith("road_north_connector_")
    ]
    coverage = layout.get("coverage_audit", {})
    frontage = layout.get("street_frontage_audit", {})
    road_graph = layout.get("road_connectivity_audit", {})
    generation = layout.get("generation_checks", {})
    source_files = layout.get("source_files", {})
    declared_infill = int(layout.get("infill", {}).get("total", 0))

    checks = {
        "full11_active_generator_is_pipeline_entry": (
            Path(str(layout.get("active_generator", ""))).name
            == "generate_urban_v1_full_11.py"
        ),
        "all_full11_generation_checks_pass": bool(
            generation
            and generation.get("asset_aabb_overlap_pairs") == []
            and generation.get("asset_road_intrusions") == []
            and all(
                value is True
                for key, value in generation.items()
                if key not in {"asset_aabb_overlap_pairs", "asset_road_intrusions"}
            )
        ),
        "exact_lake3_region_present_near_library": bool(
            len(lake) == 1
            and "urban_v3_lake3" in str(lake[0].get("source_path", ""))
            and lake[0].get("near_library") is True
            and lake[0].get("pavilion_count") == 1
            and lake[0].get("tree_instance_count", 0) >= 20
            and lake[0].get("bench_instance_count", 0) >= 8
        ),
        "fire7_four_engines_no_ambulance": bool(
            len(fire) == 1
            and "urban_v3_fire7" in str(fire[0].get("source_path", ""))
            and fire[0].get("fire_engine_count") == 4
            and fire[0].get("ambulance_count") == 0
            and "AMBULANCE" not in str(fire[0].get("source_collection", "")).upper()
        ),
        "core_counts_not_inflated_by_infill": bool(
            categories["commercial_district"] == 1
            and categories["residential_area"] == 3
            and categories["urban_infill"] == declared_infill
            and declared_infill >= 190
        ),
        "infill_reuses_exact_detailed_sources_at_scale_one": bool(
            len(infill) == declared_infill
            and declared_infill >= 190
            and all(record.get("scale") == [1.0, 1.0, 1.0] for record in infill)
            and all(
                any(
                    token in str(record.get("source_path", ""))
                    for token in ("urban_v3_all45_09", "urban_v3_all43_25")
                )
                for record in infill
            )
        ),
        "occupied_asset_coverage_meets_target": bool(
            coverage.get("occupied_asset_footprint_ratio", 0)
            >= coverage.get("required_asset_footprint_ratio", 1)
        ),
        "developed_city_coverage_meets_target": bool(
            coverage.get("developed_city_coverage_ratio", 0)
            >= coverage.get("required_developed_city_coverage_ratio", 1)
        ),
        "street_frontage_continuity_meets_target": bool(
            frontage.get("mean_continuity_ratio", 0)
            >= frontage.get("required_mean_ratio", 1)
            and frontage.get("minimum_corridor_ratio", 0)
            >= frontage.get("required_minimum_corridor_ratio", 1)
        ),
        "connected_road_graph_with_internal_spines": bool(
            road_graph.get("connected") is True
            and road_graph.get("node_count", 0) >= 18
            and road_graph.get("edge_count", 0) >= 27
            and len(road_graph.get("internal_spine_x", [])) >= 2
        ),
        "exact_north_connector_road_modules_3": bool(
            len(north_connector) == 3
            and sum(
                record.get("category") == "road_intersection"
                for record in north_connector
            )
            == 1
            and sum(
                record.get("category") == "road_segment_ns"
                for record in north_connector
            )
            == 2
            and all(record.get("source_key") == "river5" for record in north_connector)
            and all(
                record.get("scale") == [1.0, 1.0, 1.0] for record in north_connector
            )
        ),
        "fire7_and_lake3_source_files_are_real": bool(
            "fire7" in source_files
            and "lake3" in source_files
            and Path(source_files["fire7"]).is_file()
            and Path(source_files["lake3"]).is_file()
        ),
        "park_and_leisure_parcels_are_irregular": bool(
            len(layout.get("zones", {}).get("park_irregular_polygon", [])) >= 6
            and len(layout.get("zones", {}).get("leisure_south_polygon", [])) >= 5
        ),
        "all_declared_production_placements_manifested": bool(
            declared_infill >= 190
            and len(north_connector) == 3
            and len(placements) == 99 + len(north_connector) + declared_infill
        ),
    }
    detail: dict[str, Any] = {
        "category_counts": dict(sorted(categories.items())),
        "coverage": coverage,
        "street_frontage": frontage,
        "road_connectivity": road_graph,
        "generation_checks": generation,
        "lake_records": lake,
        "fire_records": fire,
        "infill_count": len(infill),
        "north_connector_records": north_connector,
    }
    if not structure_only:
        image_checks, image_detail = render_checks()
        checks.update(image_checks)
        detail["render_delivery"] = image_detail
    return checks, detail


def main() -> None:
    structure_only = any(
        arg.strip().lower() in {"structure-only", "--structure-only"}
        for arg in script_args()
    )
    if not LAYOUT.is_file():
        raise FileNotFoundError(LAYOUT)

    # This writes the base report and SUCCESS only after every established
    # expensive source/geometry/spatial check passes.
    base.main()
    report_path = OUT / "strict_completion_audit.json"
    success_path = OUT / "SUCCESS"
    report = json.loads(report_path.read_text(encoding="utf8"))
    layout = json.loads(LAYOUT.read_text(encoding="utf8"))
    checks, detail = full11_checks(layout, structure_only)
    report["full11_checks"] = checks
    report["full11_detail"] = detail
    report["checks"].update(checks)
    report["failed_checks"] = sorted(
        name for name, valid in report["checks"].items() if valid is not True
    )
    report["valid"] = not report["failed_checks"]
    report["audit_mode"] = (
        "strict read-only full11 structure audit; renders intentionally deferred"
        if structure_only
        else "strict read-only full11 structure, coverage, continuity, and render audit"
    )

    if structure_only:
        target = OUT / "structure_completion_audit.json"
        target.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
        )
        report_path.unlink(missing_ok=True)
        success_path.unlink(missing_ok=True)
    else:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
        )

    if report["failed_checks"]:
        success_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{REVISION} audit failed: " + ", ".join(report["failed_checks"])
        )
    if structure_only:
        print(f"{REVISION} structure-only audit: PASS (SUCCESS intentionally deferred)")
    else:
        success_path.write_text("SUCCESS\n", encoding="utf8")
        print(f"{REVISION} strict completion audit: SUCCESS")


if __name__ == "__main__":
    main()
