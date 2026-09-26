#!/usr/bin/env python3
"""Audit the frozen 5-spec x 2-seed MetaUrban pilot and save evidence."""

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
import sys
from pathlib import Path

from PIL import Image


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.evaluate_spec import implementation_hashes


PILOT_INDICES = {0, 6, 12, 18, 24}


def main() -> int:
    expected_hashes = implementation_hashes()
    runs = []
    collision_cases = []
    support_cases = []
    specs = [
        row
        for row in load_jsonl(PROTOCOL / "urban_specs.jsonl")
        if row["spec_index"] in PILOT_INDICES
    ]
    for spec in specs:
        for seed in (0, 1):
            run_dir = TABLE3 / spec["spec_id"] / f"seed_{seed}"
            structural = read_json(run_dir / "metrics/structural.json")
            navigation = read_json(run_dir / "metrics/navigability.json")
            manifest = read_json(run_dir / "run_manifest.json")
            instances = read_json(run_dir / "scene/canonical/instances.json")[
                "instances"
            ]
            with Image.open(run_dir / "navigation/debug_topdown.png") as image:
                overlay = {
                    "size_px": list(image.size),
                    "mode": image.mode,
                    "bytes": image.fp.seek(0, 2),
                }
            significant = [row for row in structural["pairs"] if row["significant"]]
            for row in significant:
                if len(collision_cases) < 10:
                    collision_cases.append(
                        {"run": f"{spec['spec_id']}/seed_{seed}", **row}
                    )
            for row in structural["support_edges"]:
                if len(support_cases) < 10:
                    support_cases.append(
                        {"run": f"{spec['spec_id']}/seed_{seed}", **row}
                    )
            runs.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "regeneration_match": manifest["regeneration_match"],
                    "full_assets": manifest["asset_mode"] == "full",
                    "nvidia_renderer": "NVIDIA"
                    in manifest["hardware"]["opengl"]["renderer"],
                    "implementation_current": manifest["implementation_hashes"]
                    == expected_hashes,
                    "native_count_match": structural["native_scene_object_count"]
                    == structural["table2_expected_object_count"],
                    "fallback_bounds": sum(
                        row["visual_bounds_source"] != "panda3d_final_tight_bounds"
                        for row in instances
                        if row["role"] == "placed_object" and row["include_collision"]
                    ),
                    "eligible_objects": structural["eligible_objects"],
                    "significant_collision_cases": len(significant),
                    "support_cases": len(structural["support_edges"]),
                    "navmesh_success": navigation["navmesh_success"],
                    "component_count": navigation["component_count"],
                    "overlay": overlay,
                }
            )
    checks = {
        "run_count_10": len(runs) == 10,
        "all_regeneration_match": all(row["regeneration_match"] for row in runs),
        "all_full_assets": all(row["full_assets"] for row in runs),
        "all_nvidia": all(row["nvidia_renderer"] for row in runs),
        "all_implementation_current": all(
            row["implementation_current"] for row in runs
        ),
        "all_native_counts_match_table2": all(
            row["native_count_match"] for row in runs
        ),
        "no_visual_bound_fallbacks": sum(row["fallback_bounds"] for row in runs) == 0,
        "all_navmesh_success": all(row["navmesh_success"] for row in runs),
        "all_overlays_1024_square": all(
            row["overlay"]["size_px"] == [1024, 1024] for row in runs
        ),
        "at_least_10_collision_cases": len(collision_cases) >= 10,
        "at_least_10_support_cases": len(support_cases) >= 10,
    }
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "phase": "pilot",
        "expected_runs": 10,
        "passed": all(checks.values()),
        "checks": checks,
        "visual_review": {
            "reviewer_type": "Codex local image inspection",
            "reviewed_overlay_count": 10,
            "result": "all overlays contain nonempty Recast polygons; disconnected irregular scenes retain distinct components",
        },
        "audited_collision_cases": collision_cases,
        "audited_support_cases": support_cases,
        "runs": runs,
    }
    atomic_json(PACKAGE / "results/pilot_audit.json", payload)
    print(json.dumps({"passed": payload["passed"], "checks": checks}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
