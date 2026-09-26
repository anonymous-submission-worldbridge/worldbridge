#!/usr/bin/env python3
"""Aggregate the complete SceneWeaver Table-3 matrix with spec-cluster CIs."""

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


import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))
from baselines.evaluation.geometry.common import BASELINES
from baselines.evaluation.geometry.common import SPEC_FILE
from baselines.evaluation.geometry.common import TABLE3_ROOT
from baselines.evaluation.geometry.common import atomic_json
from baselines.evaluation.geometry.common import load_specs  # noqa: E402
from baselines.evaluation.geometry.metrics.aggregate_geometry import METRIC_KEYS
from baselines.evaluation.geometry.metrics.aggregate_geometry import (
    aggregate_records,
)  # noqa: E402


def number(payload: dict, key: str, path: Path) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RuntimeError(f"Invalid {key} in {path}: {value!r}")
    return float(value)


def load_sceneweaver_records(data_root: Path, spec_file: Path) -> list[dict]:
    records = []
    for spec in load_specs(spec_file):
        for seed in range(4):
            run_dir = data_root / spec["spec_id"] / f"seed_{seed}"
            structural_path = run_dir / "metrics/structural.json"
            nav_path = run_dir / "metrics/navigability.json"
            manifest_path = run_dir / "run_manifest.json"
            if (
                not structural_path.is_file()
                or not nav_path.is_file()
                or not manifest_path.is_file()
            ):
                raise RuntimeError(f"Missing terminal run: {run_dir}")
            structural = json.loads(structural_path.read_text())
            nav = json.loads(nav_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            expected = {
                "method": "sceneweaver",
                "domain": "indoor",
                "spec_id": spec["spec_id"],
            }
            for payload, path in ((structural, structural_path), (nav, nav_path)):
                for key, value in expected.items():
                    if payload.get(key) != value:
                        raise RuntimeError(f"Identity mismatch {key} in {path}")
                if int(payload.get("logical_seed", seed)) != seed:
                    raise RuntimeError(f"Seed mismatch in {path}")
            record = {
                "spec_id": spec["spec_id"],
                "seed": seed,
                "collision_rate": number(structural, "collision_rate", structural_path),
                "floating_rate": number(structural, "floating_rate", structural_path),
                "oob_rate": number(structural, "oob_rate", structural_path),
                "support_validity": number(
                    structural, "support_validity", structural_path
                ),
                "navigable_area_ratio": number(nav, "navigable_area_ratio", nav_path),
                "connected_area_ratio": number(nav, "connected_area_ratio", nav_path),
                "navmesh_success_rate": 100.0 if nav.get("navmesh_success") else 0.0,
                "valid_scene_rate": 100.0
                if nav.get("valid_scene", nav.get("valid", False))
                else 0.0,
                "source_table2_status": manifest["source_classification"][
                    "classification"
                ],
                "eligible_objects": int(structural.get("eligible_objects", 0)),
                "support_edges": int(structural.get("required_support_edges", 0)),
                "geometry_available": bool(structural.get("success"))
                and bool(nav.get("success")),
                "instances_available": bool(structural.get("success"))
                and not structural.get("failures"),
                "output_contract_passed": bool(
                    structural.get("output_contract_passed")
                ),
                "failure_reason": structural.get("failure_reason")
                or nav.get("failure_reason"),
                "run_dir": str(run_dir),
            }
            for key in METRIC_KEYS:
                if not 0.0 <= record[key] <= 100.0 + 1e-8:
                    raise RuntimeError(
                        f"Out-of-range {key} at {run_dir}: {record[key]}"
                    )
            records.append(record)
    if len(records) != 100:
        raise RuntimeError(f"Expected 100 records, got {len(records)}")
    return records


def aggregate_sceneweaver_records(records: list[dict], repeats: int, seed: int) -> dict:
    aggregate = aggregate_records(records, repeats, seed)
    means = {key: aggregate["metrics"][key]["mean"] for key in METRIC_KEYS}
    evaluated = sum(record["geometry_available"] for record in records)
    mapped = sum(record["instances_available"] for record in records)
    contracts = sum(record["output_contract_passed"] for record in records)
    failures = Counter(
        str(record["failure_reason"] or record["source_table2_status"])
        for record in records
        if not record["geometry_available"]
    )
    return {
        "method": "sceneweaver",
        "display_name": "SceneWeaver (Indoor; mixed MiniMax/Codex planner)",
        "domain": "indoor",
        "track": "structured_physics_ready",
        "failure_policy": "itt",
        "planned_runs": 100,
        "evaluated_runs": evaluated,
        "coverage": {
            "geometry_percent": 100.0 * evaluated / 100.0,
            "instance_percent": 100.0 * mapped / 100.0,
            "output_contract_percent": 100.0 * contracts / 100.0,
        },
        "failure_breakdown": dict(sorted(failures.items())),
        "eligible_objects_total": sum(record["eligible_objects"] for record in records),
        "support_edges_total": sum(record["support_edges"] for record in records),
        "bootstrap_repeats": repeats,
        "bootstrap_seed": seed,
        "aggregate": aggregate,
        "display_row_one_decimal": {
            key: round(value, 1) for key, value in means.items()
        },
        "per_scene": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=TABLE3_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--bootstrap-repeats", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260909)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=BASELINES / "table3/results/sceneweaver_table3.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=BASELINES / "table3/results/sceneweaver_table3_full.json",
    )
    args = parser.parse_args()
    records = load_sceneweaver_records(args.data_root, args.spec_file)
    payload = aggregate_sceneweaver_records(
        records, args.bootstrap_repeats, args.bootstrap_seed
    )
    means = {key: payload["aggregate"]["metrics"][key]["mean"] for key in METRIC_KEYS}
    row = {
        "method": payload["display_name"],
        "domain": "indoor",
        "track": "structured_physics_ready",
        **means,
        "planned_runs": 100,
        "evaluated_runs": payload["evaluated_runs"],
        "instance_coverage": payload["coverage"]["instance_percent"],
        "geometry_coverage": payload["coverage"]["geometry_percent"],
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_csv.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    temporary.replace(args.output_csv)
    atomic_json(args.output_json, payload)
    print(json.dumps(payload["display_row_one_decimal"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
