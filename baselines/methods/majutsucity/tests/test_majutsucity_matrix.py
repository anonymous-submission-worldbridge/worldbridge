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

import pytest


MODULE_PATH = _BASELINE_PROJECT_ROOT / "baselines/methods/majutsucity/run.py"
SPEC = importlib.util.spec_from_file_location("majutsucity_matrix", MODULE_PATH)
assert SPEC and SPEC.loader
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)


def test_gpu_gate_requires_continuous_idle_window(monkeypatch) -> None:
    readings = iter(
        [
            {3: 41000, 4: 42000},
            {3: 39000, 4: 42000},
            {3: 41000, 4: 42000},
            {3: 41000, 4: 42000},
            {3: 41000, 4: 42000},
        ]
    )
    times = iter([0.0, 10.0, 20.0, 30.0, 40.0])
    monkeypatch.setattr(matrix, "free_memory", lambda: next(readings))
    monkeypatch.setattr(matrix.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(matrix.time, "sleep", lambda _seconds: None)

    matrix.wait_for_gpus([3, 4], 40000, stable_seconds=20.0, poll_seconds=10.0)


@pytest.mark.parametrize(
    ("stable_seconds", "poll_seconds"),
    [(-1.0, 10.0), (10.0, 0.0)],
)
def test_gpu_gate_rejects_invalid_timing(
    stable_seconds: float, poll_seconds: float
) -> None:
    with pytest.raises(ValueError):
        matrix.wait_for_gpus(
            [3, 4],
            40000,
            stable_seconds=stable_seconds,
            poll_seconds=poll_seconds,
        )
