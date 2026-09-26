#!/usr/bin/env python3
"""Blender-local clipping and crosswalk-envelope fixtures."""

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


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))
from baselines.methods.gpt.tools.export_gpt_geometry import clip_triangle
from baselines.methods.gpt.tools.export_gpt_geometry import crosswalk_envelopes
from baselines.methods.gpt.tools.export_gpt_geometry import merge_parts  # noqa: E402
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import (
    load_rules,
)  # noqa: E402


rules = load_rules()
clipped = clip_triangle([(-2, 0, 0), (2, 0, 0), (0, 2, 0)], (-1, 1, -1, 1))
assert len(clipped) >= 3
assert all(-1 <= point[0] <= 1 and -1 <= point[1] <= 1 for point in clipped)
records = [
    {
        "name": "Crosswalk stripe 1",
        "minimum": [-1.0, -0.2, 0.0],
        "maximum": [-0.5, 0.2, 0.01],
    },
    {
        "name": "Crosswalk stripe 2",
        "minimum": [0.0, -0.2, 0.0],
        "maximum": [0.5, 0.2, 0.01],
    },
]
parts, metadata = crosswalk_envelopes(records, (-2, 2, -2, 2), rules)
vertices, faces = merge_parts(parts)
assert len(metadata) == 1 and len(vertices) == 4 and len(faces) == 2
assert metadata[0]["source_nodes"] == ["Crosswalk stripe 1", "Crosswalk stripe 2"]
print("GPT-6 Astra Table-3 Blender fixtures: PASS")
