#!/usr/bin/env python3
"""Strictly audit the frozen 10-run Infinigen Table 3 pilot."""

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
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "data/table3/indoor/infinigen_indoors"
OUTPUT = BASELINES / "evaluation/geometry/results/pilot_audit.json"
PILOT = [
    "indoor_bedroom_00",
    "indoor_living_room_00",
    "indoor_kitchen_00",
    "indoor_bathroom_00",
    "indoor_dining_room_00",
]
METRICS = ["collision_rate", "floating_rate", "oob_rate", "support_validity"]
NAV = ["navigable_area_ratio", "connected_area_ratio"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    rows = []
    errors = []
    review_cases = []
    current_hashes = None
    for spec_id in PILOT:
        for seed in (0, 1):
            run_id = f"{spec_id}/seed_{seed}"
            run_dir = ROOT / spec_id / f"seed_{seed}"
            required = [
                run_dir / "metrics/structural.json",
                run_dir / "metrics/navigability.json",
                run_dir / "run_manifest.json",
                run_dir / "EVALUATION_SUCCESS",
            ]
            missing = [
                str(path.relative_to(run_dir)) for path in required if not path.exists()
            ]
            if missing:
                errors.append({"run_id": run_id, "missing": missing})
                continue
            structural = read(required[0])
            nav = read(required[1])
            manifest = read(required[2])
            if current_hashes is None:
                current_hashes = manifest["implementation_hashes"]
            if manifest["implementation_hashes"] != current_hashes:
                errors.append(
                    {"run_id": run_id, "error": "implementation_hash_mismatch"}
                )
            for key in METRICS:
                if (
                    not math.isfinite(float(structural[key]))
                    or not 0 <= float(structural[key]) <= 100
                ):
                    errors.append(
                        {"run_id": run_id, "metric": key, "value": structural[key]}
                    )
            for key in NAV:
                if (
                    not math.isfinite(float(nav[key]))
                    or not 0 <= float(nav[key]) <= 100 + 1e-6
                ):
                    errors.append({"run_id": run_id, "metric": key, "value": nav[key]})
            formal = manifest["source_table2_status"] == "formal_success"
            if formal:
                formal_required = [
                    run_dir / "scene/canonical/collision.glb",
                    run_dir / "scene/canonical/collision_geometry.npz",
                    run_dir / "scene/canonical/instances.json",
                    run_dir / "scene/raw/REFERENCE.json",
                    run_dir / "metrics/debug_structural_topdown.png",
                ]
                if nav["navmesh_success"]:
                    formal_required.append(run_dir / "navigation/debug_topdown.png")
                absent = [
                    str(path.relative_to(run_dir))
                    for path in formal_required
                    if not path.is_file() or path.stat().st_size == 0
                ]
                if absent:
                    errors.append(
                        {"run_id": run_id, "missing_formal_artifacts": absent}
                    )
                instances = read(run_dir / "scene/canonical/instances.json")[
                    "instances"
                ]
                helpers = [
                    name
                    for item in instances
                    for name in item["mesh_nodes"]
                    if "spawn_placeholder" in name or ".cutter" in name
                ]
                if helpers:
                    errors.append(
                        {"run_id": run_id, "helper_meshes_in_instances": helpers}
                    )
                for pair in structural.get("pairs", []):
                    if pair.get("significant"):
                        review_cases.append(
                            {"run_id": run_id, "kind": "collision", "detail": pair}
                        )
                for edge in structural.get("support_edges", []):
                    if not edge.get("valid"):
                        review_cases.append(
                            {"run_id": run_id, "kind": "support", "detail": edge}
                        )
            rows.append(
                {
                    "run_id": run_id,
                    "source_status": manifest["source_table2_status"],
                    "eligible_objects": structural["eligible_objects"],
                    **{key: structural[key] for key in METRICS},
                    **{key: nav[key] for key in NAV},
                    "navmesh_success": nav["navmesh_success"],
                    "valid": nav.get("valid", False),
                }
            )
    result = {
        "method": "infinigen_indoors",
        "phase": "pilot",
        "planned_runs": 10,
        "audited_runs": len(rows),
        "formal_success_sources": sum(
            row["source_status"] == "formal_success" for row in rows
        ),
        "itt_sources": sum(row["source_status"] != "formal_success" for row in rows),
        "review_case_count": len(review_cases),
        "review_cases_first_20": review_cases[:20],
        "implementation_hashes": current_hashes,
        "errors": errors,
        "passed": len(rows) == 10 and not errors and len(review_cases) >= 10,
        "runs": rows,
    }
    (_BASELINE_PROJECT_ROOT / "baselines/evaluation/geometry/results").mkdir(
        parents=True, exist_ok=True
    )
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "audited_runs",
                    "formal_success_sources",
                    "itt_sources",
                    "review_case_count",
                    "passed",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
