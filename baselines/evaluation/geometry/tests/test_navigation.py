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


import json

import numpy as np

from baselines.evaluation.geometry.metrics.eval_navigability import build_recast
from baselines.evaluation.geometry.metrics.eval_navigability import components
from baselines.evaluation.geometry.metrics.eval_navigability import mesh_area
from baselines.evaluation.geometry.metrics.eval_navigability import project_to_navmesh


def save_geometry(path, vertices, faces):
    np.savez_compressed(
        path,
        vertices=np.asarray(vertices, dtype=np.float32),
        faces=np.asarray(faces, dtype=np.int32),
    )


def config():
    return {
        "agent": {
            "height_m": 1.7,
            "radius_m": 0.3,
            "max_climb_m": 0.2,
            "max_slope_deg": 45.0,
        },
        "recast": {"cell_size_m": 0.05, "cell_height_m": 0.05},
    }


def test_empty_rectangle_recast_and_spawn(tmp_path):
    path = tmp_path / "room.npz"
    save_geometry(
        path, [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]], [[0, 1, 2], [0, 2, 3]]
    )
    vertices, faces = build_recast(path, config(), 0.0)
    assert mesh_area(vertices, faces) > 8.0
    assert len(components(vertices, faces)) == 1
    projection = project_to_navmesh([2, 1.5, 0], vertices, faces)
    assert projection is not None
    assert projection["horizontal_distance_m"] < 0.05


def test_two_known_islands_remain_disconnected(tmp_path):
    path = tmp_path / "islands.npz"
    vertices = [
        [0, 0, 0],
        [2, 0, 0],
        [2, 2, 0],
        [0, 2, 0],
        [4, 0, 0],
        [6, 0, 0],
        [6, 2, 0],
        [4, 2, 0],
    ]
    faces = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    save_geometry(path, vertices, faces)
    nav_vertices, nav_faces = build_recast(path, config(), 0.0)
    rows = components(nav_vertices, nav_faces)
    assert len(rows) == 2
    assert np.isclose(rows[0]["area_m2"], rows[1]["area_m2"], rtol=0.05)
