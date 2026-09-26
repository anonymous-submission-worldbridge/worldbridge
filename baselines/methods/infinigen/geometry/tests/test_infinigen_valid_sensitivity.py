#!/usr/bin/env python3
"""Synthetic checks for the supplementary Infinigen validity sensitivity."""

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

from baselines.methods.infinigen.geometry.metrics.analyze_infinigen_valid_sensitivity import (
    analyze,
)
from baselines.methods.infinigen.geometry.metrics.analyze_infinigen_valid_sensitivity import (
    fixed_conditions_pass,
)
from baselines.methods.infinigen.geometry.metrics.analyze_infinigen_valid_sensitivity import (
    scene_pass,
)


REPO = _BASELINE_PROJECT_ROOT
CONFIG = json.loads(
    (
        (
            REPO
            / "baselines/methods/infinigen/protocol/geometry/infinigen_operational_valid.json"
        )
    ).read_text()
)


def valid_record(**overrides) -> dict:
    record = {
        "spec_id": "indoor_fixture_00",
        "seed": 0,
        "output_contract_passed": True,
        "collision_rate": 0.0,
        "floating_rate": 0.0,
        "oob_rate": 0.0,
        "support_validity": 100.0,
        "navmesh_success_rate": 100.0,
        "navigable_area_ratio": 80.0,
        "connected_area_ratio": 82.0,
        "valid_scene_rate": 0.0,
        "geometry_available": True,
    }
    record.update(overrides)
    return record


def test_operational_changes_only_connected_threshold():
    record = valid_record()
    assert fixed_conditions_pass(record, CONFIG)
    assert scene_pass(record, CONFIG, 80.0)
    assert not scene_pass(record, CONFIG, 85.0)
    for key, bad_value in (
        ("output_contract_passed", False),
        ("collision_rate", 1.0),
        ("floating_rate", 1.0),
        ("oob_rate", 1.0),
        ("support_validity", 99.0),
        ("navmesh_success_rate", 0.0),
        ("navigable_area_ratio", 70.0),
    ):
        invalid = copy.deepcopy(record)
        invalid[key] = bad_value
        assert not fixed_conditions_pass(invalid, CONFIG), key
        assert not scene_pass(invalid, CONFIG, 80.0), key


def test_complete_matrix_sensitivity_and_primary_reproduction():
    records = []
    for spec_index in range(25):
        for seed in range(4):
            record = valid_record(spec_id=f"fixture_{spec_index:02d}", seed=seed)
            if spec_index == 0 and seed == 0:
                record["connected_area_ratio"] = 100.0
                record["valid_scene_rate"] = 100.0
            elif spec_index == 0 and seed == 1:
                record["connected_area_ratio"] = 82.0
            else:
                record["collision_rate"] = 1.0
            records.append(record)
    payload = analyze(records, CONFIG, repeats=100, seed=20260909)
    rows = {
        row["connected_area_threshold_percent"]: row for row in payload["sensitivity"]
    }
    primary = rows[float(CONFIG["primary_connected_area_ratio_min_percent"])]
    operational = rows[80.0]
    assert payload["primary_predicate_reproduced"] is True
    assert primary["pass_count_itt"] == 1
    assert primary["rate_percent_itt"] == 1.0
    assert operational["pass_count_itt"] == 2
    assert operational["rate_percent_itt"] == 2.0
