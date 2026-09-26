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

from baselines.methods.gpt.unified.high.gpt_io_adapter import METRICS
from baselines.methods.gpt.unified.high.gpt_io_adapter import PROTOCOL_PATH
from baselines.methods.gpt.unified.high.gpt_io_adapter import category_variant
from baselines.methods.gpt.unified.high.gpt_io_adapter import parse_partial_score
from baselines.methods.gpt.unified.high.gpt_io_adapter import (
    recover_duplicate_key_evidence,
)
from baselines.methods.gpt.unified.high.gpt_io_adapter import source_pair
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


def test_protocol_is_separate_fixed_system_and_reuses_table2():
    value = protocol()
    assert value["track"] == "fixed_io_adapter_system"
    assert "reuse immutable" in value["source"]["generation_policy"]
    forbidden = " ".join(value["adapter"]["forbidden_operations"]).lower()
    assert "icp" in forbidden and "human" in forbidden


def test_mapping_is_semantic_and_stable_for_representative_pair():
    spec = {
        "spec_id": "food_service_brick_industrial_06",
        "spec_index": 6,
        "function": "food_service",
    }
    pair = source_pair(spec, 1)
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert pair["exterior"]["run"].name == "seed_1"


def test_category_variant_requires_five_members():
    rows = [{"category": "x", "spec_index": index} for index in range(5)]
    assert category_variant(rows, "x", 3)["spec_index"] == 3


def test_perfect_portal_and_shape_fixtures():
    value = protocol()
    result = entrance_alignment(
        portal_record(value, "exterior"), portal_record(value, "interior"), value
    )
    assert result["passed"] and result["aperture_iou"] == 1.0
    outer = [[-5, -5], [5, -5], [5, 5], [-5, 5]]
    inner = [[-4, -4], [4, -4], [4, 4], [-4, 4]]
    assert rectangle_iou(outer, inner) == 0.64


def test_alignment_failure_fixtures():
    value = protocol()
    outside = portal_record(value, "exterior")
    inside = portal_record(value, "interior")
    inside["center_xyz_m"][0] += 0.25
    assert not entrance_alignment(outside, inside, value)["passed"]
    inside = portal_record(value, "interior")
    radians = np.deg2rad(20.0)
    inside["outward_normal_xyz"] = [
        float(np.sin(radians)),
        float(-np.cos(radians)),
        0.0,
    ]
    assert not entrance_alignment(outside, inside, value)["passed"]


def test_open_portal_transition_and_closed_wall_fixture():
    value = protocol()
    _, _, walls = canonical_geometry(value)
    collision = transition_collision(walls, value)
    assert collision["sample_count"] == 61
    assert collision["blocked_count"] == 0
    closed = [{"name": "closed", "bounds": [-0.6, 0.6, -5.0, -4.7, 0.0, 3.0]}]
    assert capsule_collides((0.0, -4.85), closed, value)


def test_geometry_and_failure_values_cover_all_metrics():
    value = protocol()
    vertices, faces, walls = canonical_geometry(value)
    assert vertices.shape[1] == 3 and faces.shape[1] == 3
    assert {row["name"] for row in walls} >= {
        "wall_front_left",
        "wall_front_right",
        "door_lintel",
    }
    assert set(value["failure_values"]) == set(METRICS)
    assert value["failure_values"]["transition_collision"] == 100.0


def test_schema_repair_partial_parser_requires_all_three_integer_scores():
    raw = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"functional_aqs":4,"visual_aqs":5,"spatial_aqs":3,'
                        '"functional_evidence":"visible","visual_evidence":"also visible",'
                        '"spatial_aqs":"mislabeled evidence"}'
                    )
                }
            }
        ]
    }
    assert parse_partial_score(raw)["spatial_aqs"] == 3
    assert recover_duplicate_key_evidence(raw) == {
        "functional_aqs": 4,
        "visual_aqs": 5,
        "spatial_aqs": 3,
        "functional_evidence": "visible",
        "visual_evidence": "also visible",
        "spatial_evidence": "mislabeled evidence",
    }
