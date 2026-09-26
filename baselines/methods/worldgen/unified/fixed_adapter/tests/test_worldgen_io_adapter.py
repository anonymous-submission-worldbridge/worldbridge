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


import copy
import json
from pathlib import Path

import numpy as np

from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    PROTOCOL_PATH,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    canonical_geometry,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    capsule_collides,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    entrance_alignment,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    portal_record,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    rectangle_iou,
)
from baselines.methods.worldgen.unified.fixed_adapter.worldgen_io_adapter import (
    transition_collision,
)


def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def test_protocol_is_separate_system_and_forbids_posthoc_alignment():
    value = protocol()
    assert value["track"] == "fixed_io_adapter_system"
    forbidden = " ".join(value["adapter"]["forbidden_operations"]).lower()
    assert "icp" in forbidden
    assert "iou" in forbidden
    assert value["adapter"]["portal"]["state"] == "open"


def test_perfect_shared_portal_alignment_passes():
    value = protocol()
    result = entrance_alignment(
        portal_record(value, "exterior"), portal_record(value, "interior"), value
    )
    assert result["passed"]
    assert result["aperture_iou"] == 1.0


def test_tangent_offset_fixture_fails_alignment():
    value = protocol()
    outside = portal_record(value, "exterior")
    inside = portal_record(value, "interior")
    inside["center_xyz_m"][0] += 0.25
    result = entrance_alignment(outside, inside, value)
    assert not result["passed"]
    assert not result["checks"]["tangent_offset"]


def test_normal_angle_fixture_fails_alignment():
    value = protocol()
    outside = portal_record(value, "exterior")
    inside = portal_record(value, "interior")
    radians = np.deg2rad(20.0)
    inside["outward_normal_xyz"] = [
        float(np.sin(radians)),
        float(-np.cos(radians)),
        0.0,
    ]
    result = entrance_alignment(outside, inside, value)
    assert not result["passed"]
    assert not result["checks"]["normal_angle"]


def test_shape_iou_eighty_percent_linear_scale_is_point_sixty_four():
    outer = [[-5, -5], [5, -5], [5, 5], [-5, 5]]
    inner = [[-4, -4], [4, -4], [4, 4], [-4, 4]]
    assert rectangle_iou(outer, inner) == 0.64


def test_fixed_portal_centerline_has_zero_transition_collision():
    value = protocol()
    _, _, walls = canonical_geometry(value)
    result = transition_collision(walls, value)
    assert result["sample_count"] == 61
    assert result["blocked_count"] == 0
    assert result["collision_percent"] == 0.0


def test_closed_wall_fixture_blocks_capsule():
    value = protocol()
    wall = [{"name": "closed", "bounds": [-0.6, 0.6, -5.0, -4.7, 0.0, 3.0]}]
    assert capsule_collides((0.0, -4.85), wall, value)


def test_canonical_geometry_is_nonempty_and_shared_envelope_is_exact():
    value = protocol()
    vertices, faces, walls = canonical_geometry(value)
    assert vertices.shape[1] == 3 and len(vertices) > 0
    assert faces.shape[1] == 3 and len(faces) > 0
    assert {row["name"] for row in walls} >= {
        "wall_front_left",
        "wall_front_right",
        "door_lintel",
    }


def test_failure_values_cover_all_nine_metrics():
    value = protocol()
    assert set(value["failure_values"]) == {
        "functional_aqs",
        "visual_aqs",
        "spatial_aqs",
        "shape_iou",
        "entrance_alignment",
        "entrance_passability",
        "transition_collision",
        "io_connectivity_rate",
        "cross_boundary_reachability",
    }
    assert value["failure_values"]["transition_collision"] == 100.0
