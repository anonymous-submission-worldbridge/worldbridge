#!/usr/bin/env python3
"""Aggregate the complete Infinigen Table 3 matrix with spec-cluster CIs."""

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
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPECS = BASELINES / "protocol/geometry/indoor_specs.jsonl"
METRIC_KEYS = [
    "collision_rate",
    "floating_rate",
    "oob_rate",
    "support_validity",
    "navigable_area_ratio",
    "connected_area_ratio",
    "navmesh_success_rate",
    "valid_scene_rate",
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate_records(
    records: list[dict], repeats: int = 10_000, seed: int = 20260909
) -> dict:
    per_spec = defaultdict(list)
    for record in records:
        per_spec[record["spec_id"]].append(record)
    spec_ids = sorted(per_spec)
    spec_metrics = {
        spec_id: {
            key: float(np.mean([record[key] for record in per_spec[spec_id]]))
            for key in METRIC_KEYS
        }
        for spec_id in spec_ids
    }
    metrics = {}
    for metric_index, key in enumerate(METRIC_KEYS):
        values = np.asarray(
            [spec_metrics[spec_id][key] for spec_id in spec_ids], dtype=float
        )
        rng = np.random.default_rng(seed + metric_index)
        samples = np.empty(repeats, dtype=float)
        for index in range(repeats):
            samples[index] = float(
                np.mean(values[rng.integers(0, len(values), len(values))])
            )
        metrics[key] = {
            "mean": float(values.mean()),
            "ci95": [
                float(np.percentile(samples, 2.5)),
                float(np.percentile(samples, 97.5)),
            ],
            "per_spec": {spec_id: spec_metrics[spec_id][key] for spec_id in spec_ids},
        }
    return {"metrics": metrics, "spec_count": len(spec_ids), "run_count": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=BASELINES / "data/table3")
    parser.add_argument("--bootstrap-repeats", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260909)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=(BASELINES / "evaluation/geometry/results/table3.csv"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=(BASELINES / "evaluation/geometry/results/table3_full.json"),
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in SPECS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = []
    incomplete = []
    failure_breakdown = Counter()
    for spec in specs:
        for seed in range(4):
            run_dir = (
                args.data_root
                / "indoor/infinigen_indoors"
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            structural_path = run_dir / "metrics/structural.json"
            nav_path = run_dir / "metrics/navigability.json"
            manifest_path = run_dir / "run_manifest.json"
            if (
                not structural_path.is_file()
                or not nav_path.is_file()
                or not manifest_path.is_file()
            ):
                incomplete.append(f"{spec['spec_id']}/seed_{seed}")
                continue
            structural = read_json(structural_path)
            nav = read_json(nav_path)
            manifest = read_json(manifest_path)
            source_status = manifest.get("source_table2_status", "unknown")
            if source_status != "formal_success":
                failure_breakdown[source_status] += 1
            records.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "collision_rate": float(structural["collision_rate"]),
                    "floating_rate": float(structural["floating_rate"]),
                    "oob_rate": float(structural["oob_rate"]),
                    "support_validity": float(structural["support_validity"]),
                    "navigable_area_ratio": float(nav["navigable_area_ratio"]),
                    "connected_area_ratio": float(nav["connected_area_ratio"]),
                    "navmesh_success_rate": 100.0 if nav["navmesh_success"] else 0.0,
                    "valid_scene_rate": 100.0 if nav.get("valid", False) else 0.0,
                    "source_table2_status": source_status,
                    "eligible_objects": int(structural.get("eligible_objects", 0)),
                    "geometry_available": manifest.get("reuse_status") == "reused_raw",
                    "instances_available": int(structural.get("eligible_objects", 0))
                    > 0,
                }
            )
    if incomplete and not args.allow_incomplete:
        print(f"Incomplete matrix: {len(incomplete)} runs; first: {incomplete[:10]}")
        return 2
    if not records:
        print("No completed records")
        return 3
    aggregate = aggregate_records(records, args.bootstrap_repeats, args.bootstrap_seed)
    means = {key: aggregate["metrics"][key]["mean"] for key in METRIC_KEYS}
    row = {
        "method": "Infinigen Indoors",
        "domain": "indoor",
        "track": "structured_physics_ready",
        **means,
        "planned_runs": 100,
        "evaluated_runs": len(records),
        "instance_coverage": 100.0
        * sum(record["instances_available"] for record in records)
        / 100.0,
        "geometry_coverage": 100.0
        * sum(record["geometry_available"] for record in records)
        / 100.0,
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    full = {
        "method": "infinigen_indoors",
        "display_name": "Infinigen Indoors",
        "domain": "indoor",
        "track": "structured_physics_ready",
        "failure_policy": "itt",
        "bootstrap_repeats": args.bootstrap_repeats,
        "bootstrap_seed": args.bootstrap_seed,
        "planned_runs": 100,
        "evaluated_runs": len(records),
        "incomplete_runs": incomplete,
        "coverage": {
            "instance_percent": row["instance_coverage"],
            "geometry_percent": row["geometry_coverage"],
        },
        "failure_breakdown": dict(failure_breakdown),
        "aggregate": aggregate,
        "display_row_one_decimal": {
            key: round(value, 1) for key, value in means.items()
        },
        "per_scene": records,
    }
    args.output_json.write_text(
        json.dumps(full, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(full["display_row_one_decimal"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
