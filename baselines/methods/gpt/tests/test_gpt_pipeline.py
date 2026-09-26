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
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "astra_matrix", (ROOT / "methods/gpt/run.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pipeline_accounts_for_every_task(monkeypatch):
    def fake(spec, seed, root, gpu, phase):
        return {
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "generation_success": True,
            "build_success": phase in {"build", "render"},
            "render_success": phase == "render",
            "failure_class": None,
        }

    monkeypatch.setattr(MODULE, "task", fake)
    tasks = [({"spec_id": str(i)}, 0) for i in range(12)]
    result = MODULE.pipeline(tasks, ROOT / "tmp", [0, 2, 3], 4)
    assert len(result) == 12
    assert {r["spec_id"] for r in result} == {str(i) for i in range(12)}
    assert all(r["render_success"] for r in result)


def test_pipeline_stops_on_access_failure(monkeypatch):
    def fail(*args):
        raise RuntimeError("Access denied")

    monkeypatch.setattr(MODULE, "task", fail)
    with pytest.raises(RuntimeError, match="Pipeline paused"):
        MODULE.pipeline([({"spec_id": "x"}, 0)], ROOT / "tmp", [0], 1)


def test_cpu_builds_do_not_reserve_gpu_lanes(monkeypatch):
    import threading

    barrier = threading.Barrier(3, timeout=5)
    calls = []

    def fake(spec, seed, root, gpu, phase):
        calls.append((spec["spec_id"], phase, gpu))
        if phase == "build":
            assert gpu is None
            barrier.wait()
        return {
            "spec_id": spec["spec_id"],
            "generation_success": True,
            "build_success": phase in {"build", "render"},
            "render_success": phase == "render",
            "failure_class": None,
        }

    monkeypatch.setattr(MODULE, "task", fake)
    results = MODULE.pipeline(
        [({"spec_id": str(i)}, 0) for i in range(3)], ROOT / "tmp", [2], 1, builders=3
    )
    assert len(results) == 3
    assert all(gpu == 2 for _, phase, gpu in calls if phase == "render")
    for i in range(3):
        assert [phase for name, phase, _ in calls if name == str(i)] == [
            "generate",
            "build",
            "render",
        ]


def test_build_quality_failure_is_terminal_and_not_rendered(monkeypatch):
    calls = []

    def fake(spec, seed, root, gpu, phase):
        calls.append(phase)
        return {
            "generation_success": True,
            "failure_class": "quality" if phase == "build" else None,
        }

    monkeypatch.setattr(MODULE, "task", fake)
    results = MODULE.pipeline([({"spec_id": "x"}, 0)], ROOT / "tmp", [0], 1, builders=1)
    assert len(results) == 1 and results[0]["failure_class"] == "quality"
    assert calls == ["generate", "build"]
