#!/usr/bin/env python3
"""Synthetic checks for the supplementary SceneWeaver validity sensitivity."""

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
import sys
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))
from baselines.methods.sceneweaver.geometry.metrics.analyze_sceneweaver_valid_sensitivity import (
    fixed_conditions_pass,
)
from baselines.methods.sceneweaver.geometry.metrics.analyze_sceneweaver_valid_sensitivity import (
    scene_pass,
)


def main() -> None:
    config = json.loads(
        (
            (
                REPO
                / "baselines/methods/sceneweaver/protocol/geometry/sceneweaver_operational_valid.json"
            )
        ).read_text()
    )
    valid = {
        "output_contract_passed": True,
        "collision_rate": 0.0,
        "floating_rate": 0.0,
        "oob_rate": 0.0,
        "support_validity": 100.0,
        "navmesh_success_rate": 100.0,
        "navigable_area_ratio": 80.0,
        "connected_area_ratio": 82.0,
    }
    assert fixed_conditions_pass(valid, config)
    assert scene_pass(valid, config, 80.0)
    assert not scene_pass(valid, config, 85.0)
    for key, bad_value in (
        ("output_contract_passed", False),
        ("collision_rate", 1.0),
        ("floating_rate", 1.0),
        ("oob_rate", 1.0),
        ("support_validity", 99.0),
        ("navmesh_success_rate", 0.0),
        ("navigable_area_ratio", 70.0),
    ):
        invalid = copy.deepcopy(valid)
        invalid[key] = bad_value
        assert not fixed_conditions_pass(invalid, config), key
        assert not scene_pass(invalid, config, 80.0), key
    print("SCENEWEAVER_OPERATIONAL_VALID_FIXTURES_OK")


if __name__ == "__main__":
    main()
