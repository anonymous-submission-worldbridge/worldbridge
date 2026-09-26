#!/usr/bin/env python3
"""Aggregate the complete SpatialGen Table-3 indoor surface-only matrix."""

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
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def summarize(values_by_spec: np.ndarray, repeats: int, seed: int) -> dict[str, Any]:
    spec_means = np.asarray(values_by_spec, dtype=np.float64).mean(axis=1)
    mean = float(spec_means.mean())
    generator = np.random.default_rng(seed)
    draws = generator.integers(0, len(spec_means), size=(repeats, len(spec_means)))
    boot = spec_means[draws].mean(axis=1)
    low, high = np.quantile(boot, [0.025, 0.975])
    return {
        "mean": mean,
        "ci95": [float(low), float(high)],
        "spec_means": spec_means.tolist(),
    }


def aggregate(
    data_root: Path, specs: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, Any]:
    seeds = [int(value) for value in protocol["seeds"]]
    rows = []
    failures: dict[str, int] = {}
    matrices = {
        "navigable_area_ratio": np.zeros((len(specs), len(seeds)), dtype=np.float64),
        "connected_area_ratio": np.zeros((len(specs), len(seeds)), dtype=np.float64),
        "navmesh_success_rate": np.zeros((len(specs), len(seeds)), dtype=np.float64),
    }
    evaluated = geometry_coverage = scale_coverage = 0
    for spec_index, spec in enumerate(specs):
        for seed_index, seed in enumerate(seeds):
            run_dir = data_root / spec["spec_id"] / f"seed_{seed}"
            metric_path = run_dir / "metrics/navigability.json"
            reconstruction_path = run_dir / "scene/reconstruction.json"
            if metric_path.is_file():
                metric = read_json(metric_path)
                evaluated += 1
                if reconstruction_path.is_file():
                    geometry_coverage += 1
                    reconstruction = read_json(reconstruction_path)
                    if (
                        reconstruction.get("calibration", {}).get("position_rmse_m")
                        is not None
                    ):
                        scale_coverage += 1
                nav = float(metric.get("navigable_area_ratio", 0.0))
                connected = float(metric.get("connected_area_ratio", 0.0))
                success = 100.0 if metric.get("navmesh_success") else 0.0
                for failure in metric.get("failures", []):
                    name = failure.get("type", "unknown")
                    failures[name] = failures.get(name, 0) + 1
            else:
                nav = connected = success = 0.0
                failures["missing_metric"] = failures.get("missing_metric", 0) + 1
            matrices["navigable_area_ratio"][spec_index, seed_index] = nav
            matrices["connected_area_ratio"][spec_index, seed_index] = connected
            matrices["navmesh_success_rate"][spec_index, seed_index] = success
            rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "navigable_area_ratio": nav,
                    "connected_area_ratio": connected,
                    "navmesh_success": bool(success),
                    "metric_path": str(metric_path),
                }
            )
    aggregation = protocol["aggregation"]
    metrics = {
        name: summarize(
            values,
            int(aggregation["bootstrap_repeats"]),
            int(aggregation["bootstrap_seed"]),
        )
        for name, values in matrices.items()
    }
    planned = len(specs) * len(seeds)
    return {
        "method": "spatialgen",
        "domain": "indoor",
        "track": "surface_only",
        "na": {
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "valid_scene_rate": "N/A-I",
        },
        "metrics": metrics,
        "planned_runs": planned,
        "evaluated_runs": evaluated,
        "geometry_coverage": 100.0 * geometry_coverage / planned,
        "scale_calibration_coverage": 100.0 * scale_coverage / planned,
        "native_instance_coverage": 0.0,
        "failure_breakdown": failures,
        "per_scene": rows,
        "failure_policy": "missing/reconstruction/NavMesh failure contributes 0 to all three metrics",
        "aggregation_order": aggregation["order"],
    }


def write_csv(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fields = [
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
        "evaluated_runs",
        "instance_coverage",
        "geometry_coverage",
        "scale_calibration_coverage",
    ]
    metrics = result["metrics"]
    row = {
        "method": "SpatialGen",
        "domain": "indoor",
        "track": "surface-only",
        "collision_rate": "N/A-I",
        "floating_rate": "N/A-I",
        "oob_rate": "N/A-I",
        "support_validity": "N/A-I",
        "navigable_area_ratio": f'{metrics["navigable_area_ratio"]["mean"]:.1f}',
        "connected_area_ratio": f'{metrics["connected_area_ratio"]["mean"]:.1f}',
        "navmesh_success_rate": f'{metrics["navmesh_success_rate"]["mean"]:.1f}',
        "valid_scene_rate": "N/A-I",
        "planned_runs": result["planned_runs"],
        "evaluated_runs": result["evaluated_runs"],
        "instance_coverage": "0.0",
        "geometry_coverage": f'{result["geometry_coverage"]:.1f}',
        "scale_calibration_coverage": f'{result["scale_calibration_coverage"]:.1f}',
    }
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=BASELINES_ROOT / "data/table3/indoor/spatialgen",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=(
            BASELINES_ROOT
            / "methods/spatialgen/protocol/geometry/spatialgen_protocol.json"
        ),
    )
    parser.add_argument(
        "--specs",
        type=Path,
        default=(BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(BASELINES_ROOT / "evaluation/geometry/results/spatialgen"),
    )
    args = parser.parse_args()
    protocol = read_json(args.protocol)
    specs = [
        json.loads(line)
        for line in args.specs.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = aggregate(args.data_root, specs, protocol)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = (
        args.output_dir / "table3_full.json",
        args.output_dir / "table3.csv",
    )
    atomic_json(json_path, result)
    write_csv(csv_path, result)
    atomic_json(
        args.output_dir / "completion.json",
        {
            "planned_runs": result["planned_runs"],
            "evaluated_runs": result["evaluated_runs"],
            "complete": result["evaluated_runs"] == result["planned_runs"],
            "table3_full_sha256": sha256(json_path),
            "table3_csv_sha256": sha256(csv_path),
            "protocol_sha256": sha256(args.protocol),
            "aggregator_sha256": sha256(Path(__file__)),
        },
    )
    print(
        json.dumps({name: value["mean"] for name, value in result["metrics"].items()})
    )
    return 0 if result["evaluated_runs"] == result["planned_runs"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
