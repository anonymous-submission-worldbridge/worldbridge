#!/usr/bin/env python3
"""Audit MetaUrban Table 3 completeness and provenance without changing runs."""

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


import json
import math
import sys
from collections import Counter
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256
from baselines.methods.metaurban.geometry.evaluate_spec import implementation_hashes


def main() -> int:
    rows = []
    expected_hashes = implementation_hashes()
    issue_count = 0
    required = (
        "GENERATION_SUCCESS",
        "CANONICAL_SUCCESS",
        "EVALUATION_SUCCESS",
        "input/spec.json",
        "input/native_input.json",
        "input/boundaries.json",
        "scene/raw/source.json",
        "scene/canonical/instances.json",
        "scene/canonical/geometry_manifest.json",
        "scene/canonical/empty_reference_geometry.npz",
        "scene/canonical/collision_geometry.npz",
        "navigation/empty_reference.navmesh",
        "navigation/final.navmesh",
        "navigation/components.json",
        "navigation/debug_topdown.png",
        "metrics/structural.json",
        "metrics/navigability.json",
        "run_manifest.json",
    )
    for spec in load_jsonl(PROTOCOL / "urban_specs.jsonl"):
        for seed in range(4):
            run_dir = TABLE3 / spec["spec_id"] / f"seed_{seed}"
            missing = [name for name in required if not (run_dir / name).is_file()]
            status = "complete" if not missing else "incomplete"
            detail = []
            if not missing:
                manifest = read_json(run_dir / "run_manifest.json")
                structural = read_json(run_dir / "metrics/structural.json")
                navigation = read_json(run_dir / "metrics/navigability.json")
                instances = read_json(run_dir / "scene/canonical/instances.json")[
                    "instances"
                ]
                geometry_manifest = read_json(
                    run_dir / "scene/canonical/geometry_manifest.json"
                )
                source = read_json(run_dir / "scene/raw/source.json")
                if not manifest.get("regeneration_match"):
                    detail.append("regeneration_mismatch")
                if manifest.get("asset_mode") != "full":
                    detail.append("not_full_assets")
                if "NVIDIA" not in manifest.get("hardware", {}).get("opengl", {}).get(
                    "renderer", ""
                ):
                    detail.append("non_nvidia_renderer")
                if manifest.get("implementation_hashes") != expected_hashes:
                    detail.append("implementation_hash_mismatch")
                if (
                    manifest.get("spec_id") != spec["spec_id"]
                    or manifest.get("logical_seed") != seed
                ):
                    detail.append("identity_mismatch")
                if (
                    structural["native_scene_object_count"]
                    != structural["table2_expected_object_count"]
                ):
                    detail.append("table2_object_count_mismatch")
                if any(
                    row["visual_bounds_source"] != "panda3d_final_tight_bounds"
                    for row in instances
                    if row["role"] == "placed_object" and row["include_collision"]
                ):
                    detail.append("visual_bounds_fallback")
                for filename, digest in geometry_manifest["files"].items():
                    if sha256(run_dir / "scene/canonical" / filename) != digest:
                        detail.append(f"canonical_hash:{filename}")
                source_run = Path(source["table2_run"])
                if (
                    sha256(source_run / "run_manifest.json")
                    != source["table2_manifest_sha256"]
                ):
                    detail.append("table2_manifest_hash")
                if (
                    sha256(source_run / "scene/scene.json")
                    != source["table2_scene_descriptor_sha256"]
                ):
                    detail.append("table2_scene_hash")
                if sha256(source_run / "input/native_input.json") != sha256(
                    run_dir / "input/native_input.json"
                ):
                    detail.append("native_input_copy_hash")
                if navigation["provenance"]["canonical_manifest_sha256"] != sha256(
                    run_dir / "scene/canonical/geometry_manifest.json"
                ):
                    detail.append("navigation_canonical_hash")
                eligible = structural["eligible_objects"]
                arithmetic = {
                    "collision": 100.0 * structural["collision_objects"] / eligible,
                    "floating": 100.0 * structural["floating_objects"] / eligible,
                    "oob": 100.0 * structural["oob_objects"] / eligible,
                    "support": 100.0
                    * structural["valid_support_edges"]
                    / structural["required_support_edges"],
                    "navigable": 100.0
                    * min(
                        1.0,
                        navigation["final_navmesh_area_m2"]
                        / navigation["empty_reference_area_m2"],
                    ),
                    "connected": 100.0
                    * navigation["largest_component_area_m2"]
                    / navigation["final_navmesh_area_m2"],
                }
                recorded = {
                    "collision": structural["collision_rate"],
                    "floating": structural["floating_rate"],
                    "oob": structural["oob_rate"],
                    "support": structural["support_validity"],
                    "navigable": navigation["navigable_area_ratio"],
                    "connected": navigation["connected_area_ratio"],
                }
                if any(
                    not math.isclose(
                        arithmetic[key], recorded[key], rel_tol=1e-10, abs_tol=1e-8
                    )
                    for key in arithmetic
                ):
                    detail.append("metric_arithmetic")
                thresholds = navigation["valid_scene_thresholds"]
                expected_valid = bool(
                    structural["output_contract_passed"]
                    and structural["collision_rate"] == 0.0
                    and structural["floating_rate"] == 0.0
                    and structural["oob_rate"] == 0.0
                    and structural["support_validity"] == 100.0
                    and navigation["navmesh_success"]
                    and navigation["navigable_area_ratio"]
                    >= thresholds["navigable_area_ratio"]
                    and navigation["connected_area_ratio"]
                    >= thresholds["connected_area_ratio"]
                )
                if navigation.get("valid") != expected_valid:
                    detail.append("valid_predicate")
                provenance_issues = [
                    item
                    for item in detail
                    if item not in ("output_contract_failed", "navmesh_failed")
                ]
                issue_count += len(provenance_issues)
                if not structural.get("output_contract_passed"):
                    detail.append("output_contract_failed")
                if not navigation.get("navmesh_success"):
                    detail.append("navmesh_failed")
                if detail:
                    status = "complete_metric_failure"
            rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "status": status,
                    "missing": missing,
                    "detail": detail,
                }
            )
    counts = Counter(row["status"] for row in rows)
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "expected": 100,
        "counts": dict(sorted(counts.items())),
        "all_terminal": not any(row["status"] == "incomplete" for row in rows),
        "provenance_and_arithmetic_issues": issue_count,
        "passed": not any(row["status"] == "incomplete" for row in rows)
        and issue_count == 0,
        "protocol_hashes": {
            path.name: sha256(path)
            for path in sorted(PROTOCOL.iterdir())
            if path.is_file()
        },
        "runs": rows,
    }
    atomic_json(PACKAGE / "results/audit.json", payload)
    print(
        json.dumps(
            {
                "expected": 100,
                "counts": payload["counts"],
                "all_terminal": payload["all_terminal"],
                "provenance_and_arithmetic_issues": issue_count,
                "passed": payload["passed"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
