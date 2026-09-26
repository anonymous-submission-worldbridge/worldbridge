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


import numpy as np

from baselines.evaluation.geometry.metrics.geometry import polygon_area_inside_triangles
from baselines.evaluation.geometry.metrics.geometry import sat_obb_overlap
from baselines.evaluation.geometry.metrics.geometry import support_gap_valid


def obb(x):
    return {
        "center": [x, 0, 0],
        "axes": np.eye(3).tolist(),
        "half_sizes": [0.5, 0.5, 0.5],
    }


def test_collision_separated_touching_and_threshold_depths():
    assert not sat_obb_overlap(obb(0), obb(1.1))["overlap"]
    assert sat_obb_overlap(obb(0), obb(1.0))["penetration_depth_m"] == 0
    assert np.isclose(sat_obb_overlap(obb(0), obb(0.995))["penetration_depth_m"], 0.005)
    assert np.isclose(sat_obb_overlap(obb(0), obb(0.98))["penetration_depth_m"], 0.02)


def test_oob_half_and_two_percent_exact_clipping():
    room = [[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1], [0, 1]]]
    half_percent = [[0.005, 0.2], [1.005, 0.2], [1.005, 0.8], [0.005, 0.8]]
    two_percent = [[0.02, 0.2], [1.02, 0.2], [1.02, 0.8], [0.02, 0.8]]
    ratio_half = 1 - polygon_area_inside_triangles(half_percent, room) / 0.6
    ratio_two = 1 - polygon_area_inside_triangles(two_percent, room) / 0.6
    assert np.isclose(ratio_half, 0.005)
    assert np.isclose(ratio_two, 0.02)


def test_support_gap_and_embedding_thresholds():
    assert support_gap_valid(0.0, "gravity")
    assert support_gap_valid(0.01, "gravity")
    assert not support_gap_valid(0.03, "gravity")
    assert support_gap_valid(-0.005, "gravity")
    assert not support_gap_valid(-0.02, "gravity")
