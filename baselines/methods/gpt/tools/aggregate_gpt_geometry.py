#!/usr/bin/env python3
"""Aggregate GPT-6 Astra Table-3 navigation scores with spec-cluster bootstrap."""

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


import csv
import json
import sys
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA = BASELINES / "data/table3_gpt6_astra"
RESULTS = BASELINES / "results/gpt6_astra/table3"
METRICS = ("navigable_area_ratio", "connected_area_ratio", "navmesh_success_rate")


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_specs(domain: str) -> list[dict]:
    path = BASELINES / f"protocol/generation/{domain}_specs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def collect(domain: str) -> list[dict]:
    records = []
    for spec in read_specs(domain):
        for seed in range(4):
            path = (
                DATA
                / domain
                / spec["spec_id"]
                / f"seed_{seed}/metrics/navigability.json"
            )
            if not path.is_file():
                raise RuntimeError(f"Missing planned navigation metric: {path}")
            record = json.loads(path.read_text(encoding="utf-8"))
            if (
                record.get("domain") != domain
                or record.get("spec_id") != spec["spec_id"]
                or int(record.get("logical_seed", -1)) != seed
            ):
                raise RuntimeError(f"Foreign or mis-keyed metric: {path}")
            record["navmesh_success_rate"] = 100.0 if record["navmesh_success"] else 0.0
            records.append(record)
    return records


def summarize(domain: str, records: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["spec_id"], []).append(record)
    if len(grouped) != 25 or any(len(values) != 4 for values in grouped.values()):
        raise RuntimeError(
            f"{domain}: aggregation requires exactly 25 clusters of four"
        )
    spec_ids = sorted(grouped)
    per_spec = {
        spec_id: {
            metric: float(np.mean([row[metric] for row in grouped[spec_id]]))
            for metric in METRICS
        }
        for spec_id in spec_ids
    }
    values = np.asarray(
        [[per_spec[spec_id][metric] for metric in METRICS] for spec_id in spec_ids],
        dtype=float,
    )
    means = values.mean(axis=0)
    rng = np.random.default_rng(20260909)
    indexes = rng.integers(0, len(spec_ids), size=(10000, len(spec_ids)))
    bootstrap = values[indexes].mean(axis=1)
    lower = np.percentile(bootstrap, 2.5, axis=0)
    upper = np.percentile(bootstrap, 97.5, axis=0)
    summaries = {
        metric: {
            "mean": float(means[index]),
            "ci95": [float(lower[index]), float(upper[index])],
        }
        for index, metric in enumerate(METRICS)
    }
    return {
        "domain": domain,
        "method": "gpt6_astra",
        "track": "native_mesh_instance_incomplete",
        "planned_runs": 100,
        "evaluated_geometry_runs": sum(
            bool(record.get("success")) for record in records
        ),
        "itt_failure_runs": sum(
            record.get("failure_policy") == "itt_worst_case" for record in records
        ),
        "geometry_coverage_percent": 100.0
        * sum(bool(record.get("success")) for record in records)
        / 100.0,
        "native_instance_coverage_percent": 0.0,
        "aggregation": "mean_over_spec(mean_over_four_seeds)",
        "bootstrap": {"unit": "spec", "repeats": 10000, "seed": 20260909},
        "metrics": summaries,
        "structural_metrics": {
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "valid_scene_rate": "N/A-I",
        },
        "per_spec": per_spec,
        "per_run": records,
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    summaries = [summarize(domain, collect(domain)) for domain in ("indoor", "urban")]
    atomic_json(
        RESULTS / "table3_full.json",
        {
            "protocol_id": "worldbridge-table3-gpt6-astra-native-mesh-nav-v1",
            "domains": summaries,
        },
    )
    columns = [
        "method",
        "domain",
        "track",
        "collision_rate",
        "floating_rate",
        "oob_rate",
        "support_validity",
        "navigable_area_ratio",
        "connected_area_ratio",
        "navmesh_success_rate",
        "valid_scene_rate",
        "planned_runs",
        "evaluated_geometry_runs",
        "geometry_coverage_percent",
        "native_instance_coverage_percent",
    ]
    temporary = RESULTS / "table3.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "method": "gpt6_astra",
                    "domain": summary["domain"],
                    "track": summary["track"],
                    "collision_rate": "N/A-I",
                    "floating_rate": "N/A-I",
                    "oob_rate": "N/A-I",
                    "support_validity": "N/A-I",
                    "navigable_area_ratio": f'{summary["metrics"]["navigable_area_ratio"]["mean"]:.9f}',
                    "connected_area_ratio": f'{summary["metrics"]["connected_area_ratio"]["mean"]:.9f}',
                    "navmesh_success_rate": f'{summary["metrics"]["navmesh_success_rate"]["mean"]:.9f}',
                    "valid_scene_rate": "N/A-I",
                    "planned_runs": 100,
                    "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
                    "geometry_coverage_percent": f'{summary["geometry_coverage_percent"]:.1f}',
                    "native_instance_coverage_percent": "0.0",
                }
            )
    temporary.replace(RESULTS / "table3.csv")
    for summary in summaries:
        print(
            json.dumps(
                {
                    "domain": summary["domain"],
                    "metrics": summary["metrics"],
                    "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
