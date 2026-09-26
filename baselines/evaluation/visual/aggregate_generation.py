#!/usr/bin/env python3
"""Aggregate traceable Table-2 results with spec-clustered bootstrap CIs."""

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
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
RESULTS_ROOT = BASELINES_ROOT / "results"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DATA_ROOT = BASELINES_ROOT / "data/table2"
METRIC_COLUMNS = [
    "qalign",
    "clipiqa_plus",
    "layout_plausibility",
    "prompt_alignment",
    "consistency_3d",
    "appearance_diversity_itt",
    "layout_diversity_itt",
]
DISPLAY_PRECISION = {
    "qalign": 2,
    "clipiqa_plus": 3,
    "layout_plausibility": 1,
    "prompt_alignment": 1,
    "consistency_3d": 1,
    "appearance_diversity_itt": 3,
    "layout_diversity_itt": 3,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_spec_ids(path: Path) -> list[str]:
    return [row["spec_id"] for row in read_jsonl(path)]


def select_method_records(
    rows: list[dict[str, Any]], method: str, domain: str
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("method") == method and row.get("domain") == domain
    ]


def group_scene_metric(
    records: list[dict[str, Any]], metric: str, spec_ids: list[str]
) -> dict[str, float]:
    grouped: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in records:
        value = row.get(metric)
        seed = row.get("logical_seed")
        if value is not None and seed is not None:
            grouped[row["spec_id"]].append((int(seed), float(value)))
    result = {}
    for spec_id in spec_ids:
        entries = grouped.get(spec_id, [])
        if len(entries) == 4 and sorted(seed for seed, _ in entries) == [0, 1, 2, 3]:
            result[spec_id] = float(np.mean([value for _, value in entries]))
    return result


def group_spec_metric(
    records: list[dict[str, Any]], metric: str, spec_ids: list[str]
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in records:
        if row.get(metric) is not None:
            grouped[row["spec_id"]].append(float(row[metric]))
    return {
        spec_id: grouped[spec_id][0]
        for spec_id in spec_ids
        if len(grouped.get(spec_id, [])) == 1
    }


def bootstrap_summary(
    by_spec: dict[str, float], spec_ids: list[str], rng: np.random.Generator
) -> dict[str, Any]:
    present = [spec_id for spec_id in spec_ids if spec_id in by_spec]
    if len(present) != len(spec_ids):
        return {
            "status": "pending",
            "mean": None,
            "ci95": None,
            "spec_count": len(present),
            "expected_spec_count": len(spec_ids),
            "missing_spec_ids": [
                spec_id for spec_id in spec_ids if spec_id not in by_spec
            ],
        }
    values = np.asarray([by_spec[spec_id] for spec_id in spec_ids], dtype=np.float64)
    indices = rng.integers(0, len(values), size=(10000, len(values)))
    boot_means = values[indices].mean(axis=1)
    return {
        "status": "complete",
        "mean": float(values.mean()),
        "ci95": [
            float(np.quantile(boot_means, 0.025)),
            float(np.quantile(boot_means, 0.975)),
        ],
        "spec_count": len(values),
        "expected_spec_count": len(spec_ids),
        "missing_spec_ids": [],
    }


def bootstrap_metrics(
    grouped: dict[str, dict[str, float]], spec_ids: list[str], seed: int
) -> dict[str, dict[str, Any]]:
    """Use the same deterministic cluster resamples for every metric.

    Reinitializing the generator also makes each metric's confidence interval
    independent of whether an earlier metric is pending or complete.
    """
    return {
        metric: bootstrap_summary(
            grouped[metric], spec_ids, np.random.default_rng(seed)
        )
        for metric in METRIC_COLUMNS
    }


def audit_runs(
    data_root: Path,
    spec_ids: list[str],
    method: str,
    domain: str = "indoor",
) -> dict[str, Any]:
    manifests = []
    generation_success = 0
    render_success = 0
    failure_reasons: dict[str, int] = defaultdict(int)
    for spec_id in spec_ids:
        for seed in range(4):
            run_dir = data_root / domain / method / spec_id / f"seed_{seed}"
            manifest_path = run_dir / "run_manifest.json"
            if not manifest_path.exists():
                failure_reasons["missing_manifest"] += 1
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(str(manifest_path.relative_to(BASELINES_ROOT.parent)))
            generation_success += int(bool(manifest.get("generation_success")))
            render_success += int(bool(manifest.get("render_success")))
            if manifest.get("failure_reason"):
                failure_reasons[str(manifest["failure_reason"])] += 1
    expected = len(spec_ids) * 4
    return {
        "expected_runs": expected,
        "manifest_count": len(manifests),
        "generation_success_count": generation_success,
        "generation_success_rate": generation_success / expected,
        "render_success_count": render_success,
        "render_success_rate": render_success / expected,
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "manifests": manifests,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=(BASELINES_ROOT / "protocol/generation/protocol.yaml"),
    )
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--domain", choices=("indoor", "urban"), default="indoor")
    parser.add_argument("--bootstrap-seed", type=int, default=20260827)
    args = parser.parse_args()
    spec_ids = load_spec_ids(args.spec_file)

    selected = lambda rows: select_method_records(rows, args.method, args.domain)
    iqa = selected(read_jsonl(args.results_root / "iqa_per_scene.jsonl"))
    consistency = selected(
        read_jsonl(args.results_root / "consistency_per_scene.jsonl")
    )
    human = selected(read_jsonl(args.results_root / "human_per_scene.jsonl"))
    diversity = selected(read_jsonl(args.results_root / "diversity_per_spec.jsonl"))
    grouped = {
        "qalign": group_scene_metric(iqa, "qalign", spec_ids),
        "clipiqa_plus": group_scene_metric(iqa, "clipiqa_plus", spec_ids),
        "layout_plausibility": group_scene_metric(
            human, "layout_plausibility", spec_ids
        ),
        "prompt_alignment": group_scene_metric(human, "prompt_alignment", spec_ids),
        "consistency_3d": group_scene_metric(consistency, "consistency_3d", spec_ids),
        "appearance_diversity_itt": group_spec_metric(
            diversity, "appearance_diversity_itt", spec_ids
        ),
        "layout_diversity_itt": group_spec_metric(
            diversity, "layout_diversity_itt", spec_ids
        ),
    }
    metrics = bootstrap_metrics(grouped, spec_ids, args.bootstrap_seed)
    audit = audit_runs(args.data_root, spec_ids, args.method, args.domain)
    full = {
        "protocol": str(args.protocol),
        "method": args.method,
        "domain": args.domain,
        "bootstrap": {
            "unit": "spec_id",
            "replicates": 10000,
            "seed": args.bootstrap_seed,
        },
        "metrics": metrics,
        "run_audit": audit,
        "source_files": {
            "iqa": str(args.results_root / "iqa_per_scene.jsonl"),
            "human": str(args.results_root / "human_per_scene.jsonl"),
            "consistency": str(args.results_root / "consistency_per_scene.jsonl"),
            "diversity": str(args.results_root / "diversity_per_spec.jsonl"),
        },
    }
    args.results_root.mkdir(parents=True, exist_ok=True)
    full_path = args.results_root / "table2_full.json"
    temporary = full_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(full_path)

    csv_path = args.results_root / "table2.csv"
    csv_tmp = csv_path.with_suffix(".csv.tmp")
    with csv_tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["method", "domain", *METRIC_COLUMNS, "render_success_rate"],
        )
        writer.writeheader()
        row: dict[str, Any] = {"method": args.method, "domain": args.domain}
        for metric in METRIC_COLUMNS:
            mean = metrics[metric]["mean"]
            row[metric] = (
                "" if mean is None else f"{mean:.{DISPLAY_PRECISION[metric]}f}"
            )
        row["render_success_rate"] = f"{audit['render_success_rate']:.4f}"
        writer.writerow(row)
    csv_tmp.replace(csv_path)
    complete_count = sum(value["status"] == "complete" for value in metrics.values())
    print(
        f"AGGREGATE_COMPLETE metrics={complete_count}/{len(METRIC_COLUMNS)} "
        f"csv={csv_path} full={full_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
