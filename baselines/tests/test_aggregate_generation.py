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


import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = (
    _BASELINE_PROJECT_ROOT / "baselines/evaluation/visual/aggregate_generation.py"
)
SPEC = importlib.util.spec_from_file_location("aggregate_table2", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
aggregate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate)


def test_scene_metric_is_macro_averaged_by_spec() -> None:
    records = []
    for seed, value in enumerate([1.0, 2.0, 3.0, 4.0]):
        records.append({"spec_id": "a", "logical_seed": seed, "score": value})
    for seed, value in enumerate([10.0, 10.0, 10.0, 10.0]):
        records.append({"spec_id": "b", "logical_seed": seed, "score": value})
    grouped = aggregate.group_scene_metric(records, "score", ["a", "b"])
    assert grouped == {"a": 2.5, "b": 10.0}
    summary = aggregate.bootstrap_summary(
        grouped, ["a", "b"], np.random.default_rng(123)
    )
    assert summary["status"] == "complete"
    assert summary["mean"] == 6.25


def test_incomplete_seed_set_cannot_enter_main_table() -> None:
    records = [
        {"spec_id": "a", "logical_seed": seed, "score": float(seed)}
        for seed in range(3)
    ]
    grouped = aggregate.group_scene_metric(records, "score", ["a"])
    assert grouped == {}
    summary = aggregate.bootstrap_summary(grouped, ["a"], np.random.default_rng(1))
    assert summary["status"] == "pending"
    assert summary["mean"] is None
    assert summary["missing_spec_ids"] == ["a"]


def test_duplicate_seed_cannot_masquerade_as_complete_set() -> None:
    records = [
        {"spec_id": "a", "logical_seed": seed, "score": float(seed)}
        for seed in [0, 1, 2, 2]
    ]
    assert aggregate.group_scene_metric(records, "score", ["a"]) == {}


def test_duplicate_per_spec_metric_is_rejected() -> None:
    records = [
        {"spec_id": "a", "score": 0.1},
        {"spec_id": "a", "score": 0.2},
    ]
    assert aggregate.group_spec_metric(records, "score", ["a"]) == {}


def test_itt_failure_values_are_included_not_dropped() -> None:
    records = [
        {"spec_id": "a", "logical_seed": 0, "score": 4.0, "success": True},
        {"spec_id": "a", "logical_seed": 1, "score": 4.0, "success": True},
        {"spec_id": "a", "logical_seed": 2, "score": 1.0, "success": False},
        {"spec_id": "a", "logical_seed": 3, "score": 1.0, "success": False},
    ]
    grouped = aggregate.group_scene_metric(records, "score", ["a"])
    assert grouped["a"] == 2.5


def test_records_from_other_methods_and_domains_are_excluded() -> None:
    records = [
        {"method": "infinigen_indoors", "domain": "indoor", "score": 1.0},
        {"method": "spatialgen", "domain": "indoor", "score": 99.0},
        {"method": "infinigen_indoors", "domain": "urban", "score": 88.0},
    ]
    selected = aggregate.select_method_records(records, "infinigen_indoors", "indoor")
    assert [row["score"] for row in selected] == [1.0]


def test_bootstrap_ci_is_independent_of_an_earlier_pending_metric() -> None:
    spec_ids = ["a", "b", "c"]
    grouped = {
        metric: {spec_id: float(index + 1) for index, spec_id in enumerate(spec_ids)}
        for metric in aggregate.METRIC_COLUMNS
    }
    complete = aggregate.bootstrap_metrics(grouped, spec_ids, 123)
    grouped["qalign"] = {}
    qalign_pending = aggregate.bootstrap_metrics(grouped, spec_ids, 123)
    assert qalign_pending["qalign"]["status"] == "pending"
    assert qalign_pending["clipiqa_plus"] == complete["clipiqa_plus"]
