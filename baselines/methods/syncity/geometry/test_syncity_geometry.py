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

import numpy as np

from baselines.methods.syncity.geometry.syncity_geometry import expected_tasks
from baselines.methods.syncity.geometry.syncity_geometry import load_protocol
from baselines.methods.syncity.geometry.syncity_geometry import load_specs


EXTRACTOR_PATH = Path(__file__).with_name("extract_surface.py")
SPEC = importlib.util.spec_from_file_location(
    "syncity3k_table3_extractor", EXTRACTOR_PATH
)
extractor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(extractor)


def test_matrix_cardinality_and_pilot_coverage() -> None:
    assert len(expected_tasks("formal", ["indoor", "urban"])) == 200
    assert len(expected_tasks("pilot", ["indoor", "urban"])) == 20


def test_scale_uses_frozen_grid_and_spec_extent_not_output_span() -> None:
    protocol = load_protocol()
    spec = load_specs("indoor", protocol)[0]
    means = np.asarray([[-1.5, 0.5, -1.5], [1.5, -0.5, 1.5]], dtype=np.float32)
    means = np.repeat(means, 100, axis=0)
    opacities = np.ones(len(means), dtype=np.float32)
    result = extractor.calibrate_scale(spec, means, opacities, protocol)
    assert np.isclose(result["meters_per_native_unit"], min(spec["extent_m"][:2]) / 3.0)
    assert result["scale_uses_output_bounds"] is False


def test_camera_count_and_coordinate_orientation() -> None:
    protocol = load_protocol()
    rows = extractor.camera_rows(protocol)
    assert len(rows) == 24
    for row in rows:
        rotation = row["c2w"][:3, :3]
        assert np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5)
        assert row["c2w"][1, 3] < 0.0


def test_every_reference_spawn_is_inside_registered_mask() -> None:
    from baselines.methods.worldgen.geometry.worldgen_geometry import points_in_polygons
    from baselines.methods.worldgen.geometry.worldgen_geometry import (
        reference_definition,
    )

    protocol = load_protocol()
    for domain in protocol["domains"]:
        for spec in load_specs(domain, protocol):
            boundary = reference_definition(spec, protocol)
            point = np.asarray([boundary["structural_spawn_candidate_m"][:2]])
            assert points_in_polygons(point, boundary["walkable_polygons_xy_m"])[0]
