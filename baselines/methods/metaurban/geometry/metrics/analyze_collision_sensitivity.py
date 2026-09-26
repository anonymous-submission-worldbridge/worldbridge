#!/usr/bin/env python3
"""Post-hoc MetaUrban collision sensitivity for visually operational interpretations."""

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
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import sha256


DEFAULT_CONFIG = PROTOCOL / "metaurban_collision_sensitivity.json"
DEFAULT_INPUT = PACKAGE / "results/table3_full.json"
DEFAULT_JSON = PACKAGE / "results/metaurban_collision_sensitivity.json"
DEFAULT_CSV = PACKAGE / "results/metaurban_collision_sensitivity.csv"


def endpoint_semantic(endpoint: str, instances_by_id: dict[str, dict]) -> str:
    instance = instances_by_id.get(endpoint)
    return str(instance["semantic"]) if instance is not None else endpoint


def collision_sets(
    structural: dict, instances: list[dict], config: dict
) -> dict[str, set[str]]:
    """Return implicated eligible IDs under four cumulative interpretation tiers."""
    instances_by_id = {row["instance_id"]: row for row in instances}
    eligible = {
        row["instance_id"]
        for row in instances
        if row["role"] == "placed_object" and row["include_collision"]
    }
    sets = {tier["id"]: set() for tier in config["tiers"]}
    ground_endpoint = config["ground_embedding_pair_endpoint"]
    tree_tree = tuple(config["tree_tree_semantics"])
    vegetation_like = set(config["vegetation_like_semantics"])
    for pair in structural["pairs"]:
        if not pair["significant"]:
            continue
        left, right = pair["a"], pair["b"]
        implicated = {endpoint for endpoint in (left, right) if endpoint in eligible}
        sets["all_collision_primary"].update(implicated)
        if right == ground_endpoint or left == ground_endpoint:
            continue
        sets["exclude_ground_embedding"].update(implicated)
        semantics = (
            endpoint_semantic(left, instances_by_id),
            endpoint_semantic(right, instances_by_id),
        )
        if semantics != tree_tree and semantics[::-1] != tree_tree:
            sets["exclude_ground_and_tree_tree"].update(implicated)
        if not vegetation_like.intersection(semantics):
            sets["hard_object_collision"].update(implicated)
    return sets


def source_manifest_digest(entries: list[dict]) -> str:
    canonical = json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_records(
    primary: dict, data_root: Path, config: dict
) -> tuple[list[dict], list[dict]]:
    records = []
    source_entries = []
    for primary_record in primary["per_scene"]:
        spec_id = primary_record["spec_id"]
        seed = int(primary_record["seed"])
        run_dir = data_root / spec_id / f"seed_{seed}"
        structural_path = run_dir / "metrics/structural.json"
        instances_path = run_dir / "scene/canonical/instances.json"
        if not structural_path.is_file() or not instances_path.is_file():
            raise RuntimeError(f"Missing collision source for {spec_id}/seed_{seed}")
        structural = json.loads(structural_path.read_text(encoding="utf-8"))
        instances = json.loads(instances_path.read_text(encoding="utf-8"))["instances"]
        eligible = [
            row
            for row in instances
            if row["role"] == "placed_object" and row["include_collision"]
        ]
        if len(eligible) != int(structural["eligible_objects"]):
            raise RuntimeError(f"Eligible-object mismatch for {spec_id}/seed_{seed}")
        sets = collision_sets(structural, instances, config)
        if len(sets["all_collision_primary"]) != int(structural["collision_objects"]):
            raise RuntimeError(
                f"Primary collision-object mismatch for {spec_id}/seed_{seed}"
            )
        reconstructed = 100.0 * len(sets["all_collision_primary"]) / len(eligible)
        if not math.isclose(
            reconstructed, float(primary_record["collision_rate"]), abs_tol=1e-12
        ):
            raise RuntimeError(
                f"Frozen primary collision-rate mismatch for {spec_id}/seed_{seed}"
            )
        rates = {tier: 100.0 * len(ids) / len(eligible) for tier, ids in sets.items()}
        counts = {tier: len(ids) for tier, ids in sets.items()}
        records.append(
            {
                "spec_id": spec_id,
                "logical_seed": seed,
                "eligible_objects": len(eligible),
                "collision_object_counts": counts,
                "collision_rates_percent": rates,
            }
        )
        source_entries.extend(
            [
                {
                    "path": str(structural_path.relative_to(REPO)),
                    "sha256": sha256(structural_path),
                },
                {
                    "path": str(instances_path.relative_to(REPO)),
                    "sha256": sha256(instances_path),
                },
            ]
        )
    return records, source_entries


def tier_summary(records: list[dict], tier_id: str, repeats: int, seed: int) -> dict:
    per_spec: dict[str, list[float]] = defaultdict(list)
    run_values = []
    for record in records:
        value = float(record["collision_rates_percent"][tier_id])
        per_spec[record["spec_id"]].append(value)
        run_values.append(value)
    spec_ids = sorted(per_spec)
    if (
        len(records) != 100
        or len(spec_ids) != 25
        or any(len(per_spec[spec_id]) != 4 for spec_id in spec_ids)
    ):
        raise RuntimeError("Expected the complete 25-spec x 4-seed MetaUrban matrix")
    spec_values = np.asarray(
        [np.mean(per_spec[spec_id]) for spec_id in spec_ids], dtype=float
    )
    rng = np.random.default_rng(seed)
    samples = np.asarray(
        [
            float(
                np.mean(
                    spec_values[rng.integers(0, len(spec_values), len(spec_values))]
                )
            )
            for _ in range(repeats)
        ]
    )
    implicated = sum(record["collision_object_counts"][tier_id] for record in records)
    eligible = sum(record["eligible_objects"] for record in records)
    return {
        "tier_id": tier_id,
        "collision_rate_percent": float(spec_values.mean()),
        "ci95_spec_cluster_bootstrap": [
            float(np.percentile(samples, 2.5)),
            float(np.percentile(samples, 97.5)),
        ],
        "implicated_object_run_records": implicated,
        "eligible_object_run_records": eligible,
        "pooled_object_rate_percent_descriptive_only": 100.0 * implicated / eligible,
        "zero_collision_runs": sum(value == 0.0 for value in run_values),
        "run_rate_range_percent": [float(min(run_values)), float(max(run_values))],
        "per_spec_percent": {
            spec_id: float(np.mean(per_spec[spec_id])) for spec_id in spec_ids
        },
    }


def analyze(records: list[dict], config: dict, repeats: int, seed: int) -> dict:
    summaries = [
        tier_summary(records, tier["id"], repeats, seed) for tier in config["tiers"]
    ]
    labels = {tier["id"]: tier for tier in config["tiers"]}
    for row in summaries:
        row.update(
            {
                "label_zh": labels[row["tier_id"]]["label_zh"],
                "definition": labels[row["tier_id"]]["definition"],
            }
        )
    return {
        "protocol_id": config["protocol_id"],
        "status": config["status"],
        "method": config["method"],
        "domain": config["domain"],
        "primary_collision_unchanged": bool(
            config["frozen_primary_collision_unchanged"]
        ),
        "aggregation": config["aggregation"],
        "sensitivity": summaries,
        "per_run": records,
    }


def write_csv(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "method",
            "tier_id",
            "label_zh",
            "collision_rate_percent",
            "ci95_low",
            "ci95_high",
            "implicated_object_run_records",
            "eligible_object_run_records",
            "pooled_object_rate_percent_descriptive_only",
            "zero_collision_runs",
            "run_rate_min_percent",
            "run_rate_max_percent",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload["sensitivity"]:
            writer.writerow(
                {
                    "method": payload["method"],
                    "tier_id": row["tier_id"],
                    "label_zh": row["label_zh"],
                    "collision_rate_percent": row["collision_rate_percent"],
                    "ci95_low": row["ci95_spec_cluster_bootstrap"][0],
                    "ci95_high": row["ci95_spec_cluster_bootstrap"][1],
                    "implicated_object_run_records": row[
                        "implicated_object_run_records"
                    ],
                    "eligible_object_run_records": row["eligible_object_run_records"],
                    "pooled_object_rate_percent_descriptive_only": row[
                        "pooled_object_rate_percent_descriptive_only"
                    ],
                    "zero_collision_runs": row["zero_collision_runs"],
                    "run_rate_min_percent": row["run_rate_range_percent"][0],
                    "run_rate_max_percent": row["run_rate_range_percent"][1],
                }
            )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--data-root", type=Path, default=TABLE3)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if sha256(args.input) != config["base_result_sha256"]:
        raise RuntimeError("Frozen MetaUrban primary result SHA-256 mismatch")
    primary = json.loads(args.input.read_text(encoding="utf-8"))
    records, source_entries = load_records(primary, args.data_root, config)
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
        "detailed_source_file_count": len(source_entries),
        "detailed_source_manifest_sha256": source_manifest_digest(source_entries),
    }
    atomic_json(args.output_json, payload)
    write_csv(args.output_csv, payload)
    print(
        json.dumps(
            {
                row["tier_id"]: {
                    "rate": row["collision_rate_percent"],
                    "ci95": row["ci95_spec_cluster_bootstrap"],
                }
                for row in payload["sensitivity"]
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
