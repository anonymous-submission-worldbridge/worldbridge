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

from baselines.methods.syncity.unified.fixed_adapter import (
    syncity_io_adapter as adapter,
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
    transition_collision,
)


def protocol():
    return adapter.load_protocol()


def test_protocol_is_separate_fixed_system_and_reuses_table2():
    value = protocol()
    assert value["method"] == "syncity3k_fixed_io_adapter"
    assert value["display_name"] == "syncity-3k + fixed IO adapter"
    assert value["track"] == "fixed_io_adapter_system"
    assert "never regenerate" in value["source"]["generation_policy"]
    assert value["source"]["matrix_audit"].endswith("syncity3k/matrix_audit.json")


def test_mapping_is_semantic_and_stable_for_representative_pair():
    spec = {
        "spec_id": "food_service_brick_industrial_06",
        "spec_index": 6,
        "function": "food_service",
    }
    pair = adapter.source_pair(spec, 1)
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert "/syncity3k/" in str(pair["exterior"]["run"])


def test_source_integrity_uses_frozen_matrix_and_manifest():
    spec = {
        "spec_id": "residence_contemporary_00",
        "spec_index": 0,
        "function": "residence",
    }
    pair = adapter.source_pair(spec, 0)
    record = adapter.source_side_record("interior", pair["interior"])
    assert record["success"] is True
    assert record["matrix_audit_status"] == "formal_success"
    assert record["scene_ply"]["size_verified_against_run_manifest"] is True
    assert len(record["anchors"]) == 8


def test_known_table2_quality_failure_is_not_success():
    spec = {
        "spec_id": "residence_brick_industrial_01",
        "spec_index": 1,
        "function": "residence",
    }
    record = adapter.source_side_record(
        "exterior", adapter.source_pair(spec, 3)["exterior"]
    )
    assert record["success"] is False
    assert record["matrix_audit_status"] == "quality_failure"


def test_perfect_portal_and_open_transition_fixtures():
    value = protocol()
    result = entrance_alignment(
        portal_record(value, "exterior"), portal_record(value, "interior"), value
    )
    assert result["passed"] and result["aperture_iou"] == 1.0
    vertices, faces, walls = canonical_geometry(value)
    assert vertices.shape[1] == 3 and faces.shape[1] == 3
    collision = transition_collision(walls, value)
    assert collision["sample_count"] == 61 and collision["blocked_count"] == 0


def test_closed_wall_and_alignment_failure_fixtures():
    value = protocol()
    closed = [{"name": "closed", "bounds": [-0.6, 0.6, -5.0, -4.7, 0.0, 3.0]}]
    assert capsule_collides((0.0, -4.85), closed, value)
    inside = portal_record(value, "interior")
    radians = np.deg2rad(20.0)
    inside["outward_normal_xyz"] = [
        float(np.sin(radians)),
        float(-np.cos(radians)),
        0.0,
    ]
    assert not entrance_alignment(portal_record(value, "exterior"), inside, value)[
        "passed"
    ]


def test_failure_values_cover_all_metrics():
    value = protocol()
    assert set(value["failure_values"]) == set(adapter.METRICS)
    assert value["failure_values"]["transition_collision"] == 100.0


def test_protocol_file_is_json_for_dependency_free_loading():
    raw = json.loads(adapter.PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert raw["protocol_version"].endswith("-v1")
