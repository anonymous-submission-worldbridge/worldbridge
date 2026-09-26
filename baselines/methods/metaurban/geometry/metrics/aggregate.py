#!/usr/bin/env python3
"""Aggregate 100 MetaUrban Table 3 runs with spec-cluster bootstrap CIs."""

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
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import read_json


METRICS = (
    "collision_rate",
    "floating_rate",
    "oob_rate",
    "support_validity",
    "navigable_area_ratio",
    "connected_area_ratio",
    "navmesh_success_rate",
    "valid_scene_rate",
)


def aggregate(records: list[dict], repeats: int, seed: int) -> dict:
    per_spec = defaultdict(list)
    for record in records:
        per_spec[record["spec_id"]].append(record)
    spec_ids = sorted(per_spec)
    per_spec_values = {
        spec_id: {
            metric: float(np.mean([record[metric] for record in per_spec[spec_id]]))
            for metric in METRICS
        }
        for spec_id in spec_ids
    }
    metrics = {}
    for metric_index, metric in enumerate(METRICS):
        values = np.asarray(
            [per_spec_values[spec_id][metric] for spec_id in spec_ids], dtype=float
        )
        rng = np.random.default_rng(seed + metric_index)
        samples = np.asarray(
            [
                float(np.mean(values[rng.integers(0, len(values), len(values))]))
                for _ in range(repeats)
            ]
        )
        metrics[metric] = {
            "mean": float(values.mean()),
            "ci95": [
                float(np.percentile(samples, 2.5)),
                float(np.percentile(samples, 97.5)),
            ],
            "per_spec": {
                spec_id: per_spec_values[spec_id][metric] for spec_id in spec_ids
            },
        }
    return {"metrics": metrics, "spec_count": len(spec_ids), "run_count": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=TABLE3)
    parser.add_argument("--bootstrap-repeats", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260909)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--output-csv", type=Path, default=PACKAGE / "results/table3.csv"
    )
    parser.add_argument(
        "--output-json", type=Path, default=PACKAGE / "results/table3_full.json"
    )
    args = parser.parse_args()
    records = []
    incomplete = []
    failures = Counter()
    for spec in load_jsonl(PROTOCOL / "urban_specs.jsonl"):
        for seed in range(4):
            run_dir = args.data_root / spec["spec_id"] / f"seed_{seed}"
            paths = [
                run_dir / "metrics/structural.json",
                run_dir / "metrics/navigability.json",
                run_dir / "run_manifest.json",
            ]
            if not all(path.is_file() for path in paths):
                incomplete.append(f"{spec['spec_id']}/seed_{seed}")
                continue
            structural, navigation, manifest = (read_json(path) for path in paths)
            if manifest.get("evaluation_status") != "success":
                failures[str(manifest.get("evaluation_status"))] += 1
            records.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "collision_rate": float(structural["collision_rate"]),
                    "floating_rate": float(structural["floating_rate"]),
                    "oob_rate": float(structural["oob_rate"]),
                    "support_validity": float(structural["support_validity"]),
                    "navigable_area_ratio": float(navigation["navigable_area_ratio"]),
                    "connected_area_ratio": float(navigation["connected_area_ratio"]),
                    "navmesh_success_rate": 100.0
                    if navigation["navmesh_success"]
                    else 0.0,
                    "valid_scene_rate": 100.0
                    if navigation.get("valid", False)
                    else 0.0,
                    "eligible_objects": int(structural["eligible_objects"]),
                    "output_contract_passed": bool(
                        structural["output_contract_passed"]
                    ),
                    "geometry_available": manifest.get("canonical_status") == "success",
                    "instances_available": int(structural["eligible_objects"]) > 0,
                }
            )
    if incomplete and not args.allow_incomplete:
        print(
            f"Incomplete MetaUrban matrix: {len(incomplete)}; first={incomplete[:10]}"
        )
        return 2
    if not records:
        print("No MetaUrban records")
        return 3
    result = aggregate(records, args.bootstrap_repeats, args.bootstrap_seed)
    means = {metric: result["metrics"][metric]["mean"] for metric in METRICS}
    planned = 100
    row = {
        "method": "MetaUrban",
        "domain": "urban",
        "track": "structured_physics_ready",
        **means,
        "planned_runs": planned,
        "evaluated_runs": len(records),
        "instance_coverage": 100.0
        * sum(record["instances_available"] for record in records)
        / planned,
        "geometry_coverage": 100.0
        * sum(record["geometry_available"] for record in records)
        / planned,
        "output_contract_coverage": 100.0
        * sum(record["output_contract_passed"] for record in records)
        / planned,
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    full = {
        "method": "metaurban",
        "display_name": "MetaUrban",
        "domain": "urban",
        "track": "structured_physics_ready",
        "failure_policy": "itt",
        "bootstrap_repeats": args.bootstrap_repeats,
        "bootstrap_seed": args.bootstrap_seed,
        "planned_runs": planned,
        "evaluated_runs": len(records),
        "incomplete_runs": incomplete,
        "coverage": {
            "instance_percent": row["instance_coverage"],
            "geometry_percent": row["geometry_coverage"],
            "output_contract_percent": row["output_contract_coverage"],
        },
        "failure_breakdown": dict(failures),
        "aggregate": result,
        "display_row_one_decimal": {
            metric: round(value, 1) for metric, value in means.items()
        },
        "per_scene": records,
    }
    atomic_json(args.output_json, full)
    print(json.dumps(full["display_row_one_decimal"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
