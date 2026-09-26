#!/usr/bin/env python3
"""CPU fixtures for GPT-6 Astra Table-3 rules and NavMesh masking."""

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


import sys
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))

from baselines.methods.gpt.tools.evaluate_gpt_geometry_nav import mask_to_reference
from baselines.methods.gpt.tools.evaluate_gpt_geometry_nav import (
    point_in_triangle,
)  # noqa: E402
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import (
    exclude_from_nav_obstacles,
)
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import is_walkable_surface
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import load_rules
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import roi_for_spec


def main() -> None:
    rules = load_rules()
    assert roi_for_spec({"domain": "indoor", "extent_m": [6, 5, 3]}, rules) == (
        -3,
        3,
        -2.5,
        2.5,
    )
    assert roi_for_spec({"domain": "urban", "extent_m": [112, 112, 40]}, rules) == (
        -30,
        30,
        -30,
        30,
    )
    assert is_walkable_surface("Oak_Floor", rules, "indoor")
    assert not is_walkable_surface("Bed blanket", rules, "indoor")
    assert is_walkable_surface("North Sidewalk", rules, "urban")
    assert is_walkable_surface("Zebra Crosswalk 03", rules, "urban")
    assert exclude_from_nav_obstacles("Road asphalt", rules)
    assert not exclude_from_nav_obstacles("Parked car body", rules)
    triangle = np.asarray([[0, 0], [2, 0], [0, 2]], dtype=float)
    assert point_in_triangle(np.asarray([0.5, 0.5]), triangle)
    assert not point_in_triangle(np.asarray([2.0, 2.0]), triangle)
    reference_vertices = np.asarray([[0, 0, 0], [2, 0, 0], [0, 2, 0]], dtype=np.float32)
    reference_faces = np.asarray([[0, 1, 2]], dtype=np.int32)
    final_vertices = np.asarray(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [3, 3, 0], [4, 3, 0], [3, 4, 0]],
        dtype=np.float32,
    )
    final_faces = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    masked_vertices, masked_faces, meta = mask_to_reference(
        final_vertices, final_faces, reference_vertices, reference_faces, 0.5, 0.3
    )
    assert masked_vertices.shape == (3, 3)
    assert masked_faces.shape == (1, 3)
    assert meta["retained_faces"] == 1
    print("GPT-6 Astra Table-3 CPU fixtures: PASS")


if __name__ == "__main__":
    main()
