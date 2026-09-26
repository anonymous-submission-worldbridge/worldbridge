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

from baselines.methods.hyworld.geometry.hyworld_geometry import depth_grid_mesh
from baselines.methods.hyworld.geometry.hyworld_geometry import expected_tasks
from baselines.methods.hyworld.geometry.hyworld_geometry import failed_navigation
from baselines.methods.hyworld.geometry.hyworld_geometry import load_protocol
from baselines.methods.hyworld.geometry.hyworld_geometry import load_specs
from baselines.methods.hyworld.geometry.hyworld_geometry import points_in_polygons
from baselines.methods.hyworld.geometry.hyworld_geometry import reference_definition


def test_matrix_cardinality_and_pilot_coverage() -> None:
    protocol = load_protocol()
    assert len(expected_tasks("formal", ["indoor", "urban"], protocol)) == 200
    assert len(expected_tasks("pilot", ["indoor", "urban"], protocol)) == 40


def test_indoor_reference_is_centered_spec_rectangle() -> None:
    protocol = load_protocol()
    spec = load_specs("indoor", protocol)[0]
    boundary = reference_definition(spec, protocol)
    polygon = np.asarray(boundary["walkable_polygons_xy_m"][0])
    assert np.allclose(polygon.mean(axis=0), [0.0, 0.0])
    assert points_in_polygons(np.asarray([[0.0, 0.0]]), [polygon.tolist()])[0]


def test_depth_mesh_respects_registered_region() -> None:
    protocol = load_protocol()
    protocol["surface_extraction"]["grid_stride"] = 1
    yy, xx = np.indices((4, 4), dtype=np.float32)
    points = np.stack((xx * 0.05, yy * 0.05, np.zeros_like(xx)), axis=-1)
    valid = np.ones((4, 4), dtype=bool)
    boundary = {"walkable_polygons_xy_m": [[[-1, -1], [1, -1], [1, 1], [-1, 1]]]}
    vertices, faces, stats = depth_grid_mesh(points, valid, boundary, protocol)
    assert len(vertices) == 16
    assert len(faces) == 18
    assert stats["retained_faces"] == 18


def test_itt_failure_preserves_stage_success_flags() -> None:
    spec = load_specs("urban")[0]
    metric = failed_navigation(
        spec,
        0,
        {"type": "empty_surface", "message": "test"},
        {"generation_success": True, "render_success": False},
        mesh_extraction_success=False,
        scale_calibration_success=True,
    )
    assert metric["navigable_area_ratio"] == 0.0
    assert metric["connected_area_ratio"] == 0.0
    assert metric["navmesh_success"] is False
    assert metric["scale_calibration_success"] is True
    assert metric["table2_generation_success"] is True
    assert metric["table2_render_success"] is False
