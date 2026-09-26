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

from baselines.methods.worldgen.geometry.worldgen_geometry import calibrate_scale
from baselines.methods.worldgen.geometry.worldgen_geometry import load_protocol
from baselines.methods.worldgen.geometry.worldgen_geometry import load_specs
from baselines.methods.worldgen.geometry.worldgen_geometry import points_in_polygons
from baselines.methods.worldgen.geometry.worldgen_geometry import reference_definition
from baselines.methods.worldgen.geometry.worldgen_geometry import reference_mesh


def test_scale_calibration_uses_frozen_camera_height_and_bottom_cap():
    protocol = load_protocol()
    points = np.zeros((100, 200, 3), dtype=np.float32)
    points[-5:, :, 1] = 5.0
    result = calibrate_scale(points, "indoor", protocol)
    assert result["native_floor_y"] == 5.0
    assert np.isclose(result["meters_per_native_unit"], 1.55 / 5.0)


def test_observable_nadir_scale_is_not_rejected_by_an_arbitrary_upper_bound():
    protocol = load_protocol()
    points = np.zeros((100, 200, 3), dtype=np.float32)
    points[-5:, :, 1] = 0.01
    result = calibrate_scale(points, "urban", protocol)
    assert np.isclose(result["meters_per_native_unit"], 165.0)


def test_every_reference_spawn_is_inside_its_frozen_walkable_mask():
    protocol = load_protocol()
    for domain in protocol["domains"]:
        for spec in load_specs(domain, protocol):
            boundary = reference_definition(spec, protocol)
            point = np.asarray([boundary["structural_spawn_candidate_m"][:2]])
            assert points_in_polygons(point, boundary["walkable_polygons_xy_m"])[0]
            vertices, faces = reference_mesh(boundary)
            assert len(vertices) >= 4
            assert len(faces) >= 2


def test_reference_definitions_are_deterministic():
    protocol = load_protocol()
    for domain in protocol["domains"]:
        for spec in load_specs(domain, protocol):
            assert reference_definition(spec, protocol) == reference_definition(
                spec, protocol
            )
