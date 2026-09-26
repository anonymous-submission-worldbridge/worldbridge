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
SPEC = importlib.util.spec_from_file_location(
    "astra_metric_guard", (ROOT / "methods/gpt/evaluate.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "baselines"
    (root / "protocol/generation").mkdir(parents=True)
    (root / "methods/gpt/protocol/generation").mkdir(parents=True)
    (root / "protocol/generation/indoor_specs.jsonl").write_text(
        json.dumps({"spec_id": "indoor_test", "domain": "indoor"}) + "\n"
    )
    monkeypatch.setattr(MODULE, "ROOT", root)
    monkeypatch.setattr(MODULE, "confined", lambda p: Path(p))
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *a, **k: pytest.fail("Metric subprocess must not start"),
    )
    data = root / "data/pilot"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "metrics",
            "--domain",
            "indoor",
            "--data-root",
            str(data),
            "--smoke-spec-id",
            "indoor_test",
        ],
    )
    return root, data / "indoor/gpt6_astra/indoor_test/seed_0"


def test_unstarted_run_never_becomes_itt_failure(setup):
    root, _ = setup
    with pytest.raises(RuntimeError, match="unstarted run"):
        MODULE.main()
    assert not (root / "results").exists()


def test_infrastructure_failure_cannot_be_scored(setup):
    _, run = setup
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(
        json.dumps({"failure_class": "infrastructure"})
    )
    with pytest.raises(RuntimeError, match="not terminal"):
        MODULE.main()


def test_success_marker_must_match_manifest(setup):
    _, run = setup
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(json.dumps({"render_success": False}))
    (run / "SUCCESS").touch()
    with pytest.raises(RuntimeError, match="disagrees"):
        MODULE.main()


def test_formal_source_drift_blocks_evaluation(setup, monkeypatch):
    root, _ = setup
    source = root / "protocol/frozen.txt"
    source.write_text("changed")
    (root / "methods/gpt/protocol/generation/gpt6_astra.lock.json").write_text(
        json.dumps({"files_sha256": {"protocol/frozen.txt": "wrong"}})
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["metrics", "--domain", "indoor", "--data-root", str(root / "data/table2")],
    )
    with pytest.raises(RuntimeError, match="Frozen evaluation source changed"):
        MODULE.main()


@pytest.mark.parametrize(
    "reason,detail",
    [
        ("worldscore_worker_crashed", "ImportError"),
        ("missing_droid_checkpoint", ""),
        ("droid_slam_failed", "CUDA out of memory"),
    ],
)
def test_metric_infrastructure_is_not_an_itt_zero(setup, reason, detail):
    root, run = setup
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(json.dumps({"render_success": True}))
    row = {
        "spec_id": "indoor_test",
        "logical_seed": 0,
        "consistency_3d": 0,
        "success": False,
        "failure_reason": reason,
        "failure_detail": detail,
    }
    with pytest.raises(RuntimeError, match="triage"):
        MODULE.check_consistency_records([row], root / "data/pilot", "indoor")


def test_observed_slam_tracking_failure_uses_frozen_zero(setup):
    root, run = setup
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(json.dumps({"render_success": True}))
    row = {
        "spec_id": "indoor_test",
        "logical_seed": 0,
        "consistency_3d": 0,
        "success": False,
        "failure_reason": "droid_slam_failed",
        "failure_detail": "RuntimeError: DROID-SLAM returned no valid reprojection errors",
    }
    MODULE.check_consistency_records([row], root / "data/pilot", "indoor")
