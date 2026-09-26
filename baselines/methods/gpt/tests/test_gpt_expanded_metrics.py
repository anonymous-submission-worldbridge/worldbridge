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
import json
from pathlib import Path
import sys
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "astra_expanded", (ROOT / "methods/gpt/tools/validate_gpt_pilot_metrics.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    result = tmp_path / "results/gpt6_astra/smoke/indoor/example_seed_0"
    result.mkdir(parents=True)
    run = tmp_path / "data/gpt6_astra_pilot/indoor/gpt6_astra/example/seed_0"
    semantics = run / "renders/semantic_pred"
    semantics.mkdir(parents=True)
    for i in range(8):
        (semantics / f"semantic_{i:03d}.png").touch()
    (run / "run_manifest.json").write_text(json.dumps({"render_success": True}))
    row = {
        "method": "gpt6_astra",
        "domain": "indoor",
        "spec_id": "example",
        "logical_seed": 0,
        "success": True,
    }
    iqa = {**row, "qalign": 3.1, "clipiqa_plus": 0.5, "views": [{} for _ in range(8)]}
    consistency = {**row, "consistency_3d": 50.0}
    (result / "iqa_per_scene.jsonl").write_text(json.dumps(iqa) + "\n")
    (result / "consistency_per_scene.jsonl").write_text(json.dumps(consistency) + "\n")
    return row, result, run, iqa, consistency


def test_valid_cached_metrics(metrics):
    MODULE.verify_metrics(metrics[0])


def test_foreign_cache_rejected(metrics):
    row, result, run, iqa, _ = metrics
    iqa["method"] = "another_method"
    (result / "iqa_per_scene.jsonl").write_text(json.dumps(iqa) + "\n")
    with pytest.raises(RuntimeError, match="foreign cached"):
        MODULE.verify_metrics(row)


def test_nonfinite_cache_rejected(metrics):
    row, result, run, iqa, _ = metrics
    iqa["qalign"] = float("nan")
    (result / "iqa_per_scene.jsonl").write_text(json.dumps(iqa) + "\n")
    with pytest.raises(RuntimeError, match="Invalid IQA"):
        MODULE.verify_metrics(row)


def test_missing_semantics_rejected(metrics):
    row, result, run, _, _ = metrics
    (run / "renders/semantic_pred/semantic_007.png").rename(
        run / "renders/semantic_pred/unused"
    )
    with pytest.raises(RuntimeError, match="semantic outputs"):
        MODULE.verify_metrics(row)


def test_cached_slam_infrastructure_error_is_not_success(metrics):
    row, result, run, _, consistency = metrics
    consistency.update(
        success=False,
        failure_reason="droid_slam_failed",
        failure_detail="CUDA out of memory",
    )
    (result / "consistency_per_scene.jsonl").write_text(json.dumps(consistency) + "\n")
    with pytest.raises(RuntimeError, match="triage"):
        MODULE.verify_metrics(row)
