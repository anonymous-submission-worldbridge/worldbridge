"""Synthetic Recast regression test for the SceneWeaver Table-3 path."""

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
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh

REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.evaluation.geometry.metrics.build_navmesh import build
from baselines.evaluation.geometry.metrics.build_navmesh import connected_components
from baselines.evaluation.geometry.metrics.build_navmesh import spawn_projection
from baselines.evaluation.geometry.metrics.build_navmesh import triangle_areas
from baselines.evaluation.geometry.metrics.geometry import box_mesh


BASELINES = REPO / "baselines"


def merged(parts):
    vertices = []
    faces = []
    for part_vertices, part_faces in parts:
        offset = len(vertices)
        vertices.extend(np.asarray(part_vertices).tolist())
        faces.extend((np.asarray(part_faces) + offset).tolist())
    return np.asarray(vertices), np.asarray(faces)


def main() -> None:
    floor_vertices = np.asarray(
        [[0, 0, 0], [6, 0, 0], [6, 5, 0], [0, 5, 0]], dtype=float
    )
    floor_faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=int)
    box = box_mesh([3, 2.5, 0.5], np.eye(3), [0.6, 0.6, 0.5])
    final_vertices, final_faces = merged([(floor_vertices, floor_faces), box])
    config = json.loads(((BASELINES / "protocol/geometry/agent.yaml")).read_text())
    with tempfile.TemporaryDirectory(prefix="sceneweaver-nav-") as directory:
        directory = Path(directory)
        reference_path = directory / "reference.ply"
        final_path = directory / "final.ply"
        trimesh.Trimesh(floor_vertices, floor_faces, process=False).export(
            reference_path
        )
        trimesh.Trimesh(final_vertices, final_faces, process=False).export(final_path)
        reference_nav = build(reference_path, config, 0.0)
        final_nav = build(final_path, config, 0.0)
    ref_vertices, ref_faces, _ = reference_nav
    nav_vertices, nav_faces, _ = final_nav
    ref_area = float(triangle_areas(ref_vertices, ref_faces).sum())
    final_area = float(triangle_areas(nav_vertices, nav_faces).sum())
    assert ref_area > 20.0
    assert 0.0 < final_area < ref_area
    components, component_areas = connected_components(nav_vertices, nav_faces)
    assert components and abs(sum(component_areas) - final_area) < 1e-4
    projection = spawn_projection((0.7, 0.7, 0.0), nav_vertices, nav_faces)
    assert projection["projected"]
    print("SCENEWEAVER_TABLE3_NAV_FIXTURES_OK", ref_area, final_area)


if __name__ == "__main__":
    main()
