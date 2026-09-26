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
import math
from pathlib import Path
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "astra_camera", (ROOT / "methods/gpt/tools/gpt_camera.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_resampling_preserves_narrow_corridor_corners():
    path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (3, 2)]
    result = MODULE.corner_preserving_resample(path)
    assert len(result) == 50
    assert result[0] == (0, 0) and result[-1] == (3, 2)
    assert (2, 0) in result and (2, 2) in result
    for a, b in zip(result, result[1:]):
        assert a[0] == b[0] or a[1] == b[1]
    assert sum(math.dist(a, b) for a, b in zip(result, result[1:])) == pytest.approx(5)


def test_resampling_is_deterministic():
    path = [(0, 0), (1, 0), (1, 3), (2, 3)]
    assert MODULE.corner_preserving_resample(path) == MODULE.corner_preserving_resample(
        path
    )


def test_too_many_corners_rejected():
    with pytest.raises(ValueError):
        MODULE.corner_preserving_resample([(0, 0), (1, 0), (1, 1), (2, 1)], count=3)
