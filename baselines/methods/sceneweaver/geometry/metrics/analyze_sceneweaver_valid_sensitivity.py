#!/usr/bin/env python3
"""Supplementary SceneWeaver Operational Valid and connected-threshold sensitivity."""

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
from collections import defaultdict
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_CONFIG = (
    BASELINES
    / "methods/sceneweaver/protocol/geometry/sceneweaver_operational_valid.json"
)
DEFAULT_INPUT = BASELINES / "evaluation/geometry/results/sceneweaver_table3_full.json"
DEFAULT_JSON = (
    BASELINES / "evaluation/geometry/results/sceneweaver_valid_sensitivity.json"
)
DEFAULT_CSV = (
    BASELINES / "evaluation/geometry/results/sceneweaver_valid_sensitivity.csv"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fixed_conditions_pass(record: dict, config: dict) -> bool:
    fixed = config["fixed_conditions"]
    return bool(
        record.get("output_contract_passed") is fixed["output_contract_passed"]
        and float(record["collision_rate"]) <= fixed["collision_rate_max_percent"]
        and float(record["floating_rate"]) <= fixed["floating_rate_max_percent"]
        and float(record["oob_rate"]) <= fixed["oob_rate_max_percent"]
        and float(record["support_validity"]) >= fixed["support_validity_min_percent"]
        and (float(record["navmesh_success_rate"]) == 100.0)
        is fixed["navmesh_success_required"]
        and float(record["navigable_area_ratio"])
        >= fixed["navigable_area_ratio_min_percent"]
    )


def scene_pass(record: dict, config: dict, connected_threshold: float) -> bool:
    return fixed_conditions_pass(record, config) and (
        float(record["connected_area_ratio"]) >= connected_threshold
    )


def clustered_summary(
    records: list[dict],
    config: dict,
    connected_threshold: float,
    repeats: int,
    seed: int,
) -> dict:
    per_spec: dict[str, list[float]] = defaultdict(list)
    for record in records:
        per_spec[record["spec_id"]].append(
            100.0 if scene_pass(record, config, connected_threshold) else 0.0
        )
    spec_ids = sorted(per_spec)
    if (
        len(records) != 100
        or len(spec_ids) != 25
        or any(len(per_spec[key]) != 4 for key in spec_ids)
    ):
        raise RuntimeError(
            "Expected the complete 25-spec x 4-seed SceneWeaver ITT matrix"
        )
    spec_values = np.asarray([np.mean(per_spec[key]) for key in spec_ids], dtype=float)
    rng = np.random.default_rng(seed)
    samples = np.empty(repeats, dtype=float)
    for index in range(repeats):
        samples[index] = float(
            np.mean(spec_values[rng.integers(0, len(spec_values), len(spec_values))])
        )
    passed = [
        record for record in records if scene_pass(record, config, connected_threshold)
    ]
    evaluated = [record for record in records if record.get("geometry_available")]
    evaluated_passed = [
        record
        for record in evaluated
        if scene_pass(record, config, connected_threshold)
    ]
    return {
        "connected_area_threshold_percent": connected_threshold,
        "planned_runs": len(records),
        "pass_count_itt": len(passed),
        "rate_percent_itt": float(spec_values.mean()),
        "ci95_cluster_bootstrap": [
            float(np.percentile(samples, 2.5)),
            float(np.percentile(samples, 97.5)),
        ],
        "evaluated_runs": len(evaluated),
        "pass_count_evaluated": len(evaluated_passed),
        "rate_percent_evaluated_only": 100.0 * len(evaluated_passed) / len(evaluated),
        "passing_runs": [
            {"spec_id": record["spec_id"], "logical_seed": int(record["seed"])}
            for record in passed
        ],
        "per_spec_percent": {key: float(np.mean(per_spec[key])) for key in spec_ids},
    }


def analyze(records: list[dict], config: dict, repeats: int, seed: int) -> dict:
    rows = [
        clustered_summary(records, config, float(threshold), repeats, seed)
        for threshold in config["connected_sensitivity_thresholds_percent"]
    ]
    operational_threshold = float(
        config["operational_connected_area_ratio_min_percent"]
    )
    operational = next(
        row
        for row in rows
        if row["connected_area_threshold_percent"] == operational_threshold
    )
    evaluated = [record for record in records if record.get("geometry_available")]
    return {
        "protocol_id": config["protocol_id"],
        "status": config["status"],
        "method": config["method"],
        "domain": config["domain"],
        "primary_valid_scene_unchanged": bool(
            config["frozen_primary_valid_scene_unchanged"]
        ),
        "primary_valid_scene_rate_percent": float(
            np.mean([record["valid_scene_rate"] for record in records])
        ),
        "operational_definition": {
            "fixed_conditions": config["fixed_conditions"],
            "connected_area_ratio_min_percent": operational_threshold,
            "rationale": config["operational_rationale"],
        },
        "operational_valid": operational,
        "sensitivity": rows,
        "gate_breakdown_evaluated": {
            "evaluated_runs": len(evaluated),
            "fixed_conditions_except_connected_pass": sum(
                fixed_conditions_pass(record, config) for record in evaluated
            ),
            "primary_connected_threshold_pass": sum(
                float(record["connected_area_ratio"])
                >= float(config["primary_connected_area_ratio_min_percent"])
                for record in evaluated
            ),
        },
        "aggregation": config["aggregation"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if sha256(args.input) != config["base_result_sha256"]:
        raise RuntimeError("Frozen SceneWeaver primary result SHA-256 mismatch")
    primary = json.loads(args.input.read_text(encoding="utf-8"))
    records = primary["per_scene"]
    payload = analyze(
        records,
        config,
        int(config["aggregation"]["cluster_bootstrap_repeats"]),
        int(config["aggregation"]["cluster_bootstrap_seed"]),
    )
    payload["provenance"] = {
        "primary_result": str(args.input),
        "primary_result_sha256": sha256(args.input),
        "config": str(args.config),
        "config_sha256": sha256(args.config),
        "implementation_sha256": sha256(Path(__file__)),
    }
    atomic_json(args.output_json, payload)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_csv.with_suffix(args.output_csv.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "connected_area_threshold_percent",
                "rate_percent_itt",
                "ci95_low",
                "ci95_high",
                "pass_count_itt",
                "planned_runs",
                "rate_percent_evaluated_only",
                "pass_count_evaluated",
                "evaluated_runs",
            ],
        )
        writer.writeheader()
        for row in payload["sensitivity"]:
            writer.writerow(
                {
                    "connected_area_threshold_percent": row[
                        "connected_area_threshold_percent"
                    ],
                    "rate_percent_itt": row["rate_percent_itt"],
                    "ci95_low": row["ci95_cluster_bootstrap"][0],
                    "ci95_high": row["ci95_cluster_bootstrap"][1],
                    "pass_count_itt": row["pass_count_itt"],
                    "planned_runs": row["planned_runs"],
                    "rate_percent_evaluated_only": row["rate_percent_evaluated_only"],
                    "pass_count_evaluated": row["pass_count_evaluated"],
                    "evaluated_runs": row["evaluated_runs"],
                }
            )
    temporary.replace(args.output_csv)
    print(
        json.dumps(
            {
                "primary_valid_scene_rate_percent": payload[
                    "primary_valid_scene_rate_percent"
                ],
                "operational_valid_rate_percent_itt": operational["rate_percent_itt"]
                if (operational := payload["operational_valid"])
                else None,
                "operational_valid_ci95": operational["ci95_cluster_bootstrap"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
