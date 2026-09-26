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


from baselines.evaluation.geometry.metrics.aggregate_geometry import METRIC_KEYS
from baselines.evaluation.geometry.metrics.aggregate_geometry import aggregate_records


def row(spec_id, value):
    return {"spec_id": spec_id, **{key: value for key in METRIC_KEYS}}


def test_scene_then_spec_macro_average_and_itt():
    records = [row("a", 100.0), row("a", 0.0), row("b", 100.0), row("b", 100.0)]
    result = aggregate_records(records, repeats=100, seed=1)
    assert result["metrics"]["collision_rate"]["mean"] == 75.0
    assert result["metrics"]["support_validity"]["mean"] == 75.0


def test_binary_rate_uses_all_planned_rows():
    records = [row(f"spec_{index}", 100.0 if index < 7 else 0.0) for index in range(10)]
    result = aggregate_records(records, repeats=100, seed=1)
    assert result["metrics"]["navmesh_success_rate"]["mean"] == 70.0
