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
from pathlib import Path

import numpy as np

from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import (
    PROTOCOL_PATH,
)
from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import (
    SOURCE_SUMMARY,
)
from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import all_specs
from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import (
    fixed_native_reference_scale,
)
from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import (
    source_pair_success,
)
from baselines.methods.hyworld.unified.fixed_adapter.hyworld_io_adapter import (
    specs_and_seeds,
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


def test_protocol_adds_separate_hyworld_system_row():
    value = protocol()
    assert value["method"] == "hyworld2_fixed_io_adapter"
    assert value["display_name"] == "HY-World 2.0 + fixed IO adapter"
    assert value["source_method"] == "hyworld2"
    assert value["track"] == "fixed_io_adapter_system"


def test_formal_and_pilot_matrices_are_frozen():
    formal_specs, formal_seeds = specs_and_seeds("formal")
    pilot_specs, pilot_seeds = specs_and_seeds("pilot")
    assert len(all_specs()) == 25
    assert len(formal_specs) * len(formal_seeds) == 100
    assert [row["spec_index"] for row in pilot_specs] == [0, 6, 12, 18, 24]
    assert pilot_seeds == [0, 1]


def test_source_summary_is_complete_and_reused():
    source = json.loads(SOURCE_SUMMARY.read_text(encoding="utf-8"))
    assert source["planned_pairs"] == 100
    assert source["successful_pairs"] == 70
    assert source["metrics"]["functional_aqs"]["display"] == "2.55"
    assert source["metrics"]["visual_aqs"]["display"] == "2.80"


def test_source_pair_success_requires_both_sides(tmp_path: Path):
    pair = tmp_path / "pair"
    (pair / "exterior").mkdir(parents=True)
    (pair / "interior").mkdir(parents=True)
    (pair / "exterior/SUCCESS").write_text("ok\n", encoding="utf-8")
    assert not source_pair_success(pair)
    (pair / "interior/SUCCESS").write_text("ok\n", encoding="utf-8")
    assert source_pair_success(pair)


def test_protocol_forbids_posthoc_alignment_and_native_overwrite():
    forbidden = " ".join(protocol()["adapter"]["forbidden_operations"]).lower()
    assert "icp" in forbidden
    assert "iou" in forbidden
    assert "overwrite" in forbidden


def test_shared_portal_alignment_and_collision_fixtures():
    value = protocol()
    alignment = entrance_alignment(
        portal_record(value, "exterior"), portal_record(value, "interior"), value
    )
    assert alignment["passed"]
    assert alignment["aperture_iou"] == 1.0
    _, _, walls = canonical_geometry(value)
    collision = transition_collision(walls, value)
    assert collision["sample_count"] == 61
    assert collision["blocked_count"] == 0
    assert collision["collision_percent"] == 0.0


def test_bad_portal_and_closed_wall_fixtures_fail():
    value = protocol()
    exterior = portal_record(value, "exterior")
    interior = portal_record(value, "interior")
    interior["center_xyz_m"][0] += 0.25
    assert not entrance_alignment(exterior, interior, value)["passed"]
    wall = [{"name": "closed", "bounds": [-0.6, 0.6, -5.0, -4.7, 0.0, 3.0]}]
    assert capsule_collides((0.0, -4.85), wall, value)


def test_shape_fixture_and_canonical_geometry():
    outer = [[-5, -5], [5, -5], [5, 5], [-5, 5]]
    inner = [[-4, -4], [4, -4], [4, 4], [-4, 4]]
    assert rectangle_iou(outer, inner) == 0.64
    vertices, faces, walls = canonical_geometry(protocol())
    assert vertices.shape[1] == 3 and faces.shape[1] == 3
    assert len(vertices) > 0 and len(faces) > 0 and len(walls) > 0


def test_native_reference_scale_is_fixed_and_metric_excluded(tmp_path: Path):
    cloud = tmp_path / "cloud.ply"
    cloud.write_bytes(b"immutable-test-cloud")
    value = fixed_native_reference_scale(cloud, 1.65)
    assert value["meters_per_native_unit"] == 1.0
    assert value["floor_sample_count"] == 0
    assert value["native_geometry_used_for_metrics"] is False


def test_failure_values_cover_all_nine_metrics():
    values = protocol()["failure_values"]
    assert len(values) == 9
    assert values["functional_aqs"] == 1.0
    assert values["spatial_aqs"] == 1.0
    assert values["transition_collision"] == 100.0
