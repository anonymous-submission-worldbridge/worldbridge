#!/usr/bin/env python3
"""Supplementary MetaUrban Operational Valid and connected-threshold sensitivity."""

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
from collections import defaultdict
from pathlib import Path

import numpy as np


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import sha256


PACKAGE = _BASELINE_PROJECT_ROOT / "baselines/methods/metaurban/geometry"
DEFAULT_CONFIG = PROTOCOL / "metaurban_operational_valid.json"
DEFAULT_INPUT = PACKAGE / "results/table3_full.json"
DEFAULT_JSON = PACKAGE / "results/metaurban_valid_sensitivity.json"
DEFAULT_CSV = PACKAGE / "results/metaurban_valid_sensitivity.csv"


def individual_gate_passes(record: dict, config: dict) -> dict[str, bool]:
    """Return each frozen Valid gate except the scanned Connected gate."""
    fixed = config["fixed_conditions"]
    return {
        "output_contract": record.get("output_contract_passed")
        is fixed["output_contract_passed"],
        "collision_zero": float(record["collision_rate"])
        <= fixed["collision_rate_max_percent"],
        "floating_zero": float(record["floating_rate"])
        <= fixed["floating_rate_max_percent"],
        "oob_zero": float(record["oob_rate"]) <= fixed["oob_rate_max_percent"],
        "support_perfect": float(record["support_validity"])
        >= fixed["support_validity_min_percent"],
        "navmesh_success": (float(record["navmesh_success_rate"]) == 100.0)
        == bool(fixed["navmesh_success_required"]),
        "navigable_primary": float(record["navigable_area_ratio"])
        >= fixed["navigable_area_ratio_min_percent"],
    }


def fixed_conditions_pass(record: dict, config: dict) -> bool:
    return all(individual_gate_passes(record, config).values())


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
            "Expected the complete 25-spec x 4-seed MetaUrban ITT matrix"
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
    gate_counts = {
        gate: sum(individual_gate_passes(record, config)[gate] for record in evaluated)
        for gate in individual_gate_passes(evaluated[0], config)
    }
    gate_counts.update(
        {
            "evaluated_runs": len(evaluated),
            "fixed_conditions_except_connected_pass": sum(
                fixed_conditions_pass(record, config) for record in evaluated
            ),
            "primary_connected_threshold_pass": sum(
                float(record["connected_area_ratio"])
                >= float(config["primary_connected_area_ratio_min_percent"])
                for record in evaluated
            ),
            "operational_connected_threshold_pass": sum(
                float(record["connected_area_ratio"]) >= operational_threshold
                for record in evaluated
            ),
        }
    )
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
        "gate_breakdown_evaluated": gate_counts,
        "aggregation": config["aggregation"],
    }


def write_csv(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
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
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if sha256(args.input) != config["base_result_sha256"]:
        raise RuntimeError("Frozen MetaUrban primary result SHA-256 mismatch")
    primary = json.loads(args.input.read_text(encoding="utf-8"))
    payload = analyze(
        primary["per_scene"],
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
    write_csv(args.output_csv, payload)
    operational = payload["operational_valid"]
    print(
        json.dumps(
            {
                "primary_valid_scene_rate_percent": payload[
                    "primary_valid_scene_rate_percent"
                ],
                "operational_valid_rate_percent_itt": operational["rate_percent_itt"],
                "operational_valid_ci95": operational["ci95_cluster_bootstrap"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
