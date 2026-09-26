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
import unittest

from baselines.methods.metaurban.geometry.metrics.analyze_valid_sensitivity import (
    analyze,
)
from baselines.methods.metaurban.geometry.metrics.analyze_valid_sensitivity import (
    fixed_conditions_pass,
)


CONFIG = {
    "protocol_id": "test",
    "status": "test",
    "method": "metaurban",
    "domain": "urban",
    "frozen_primary_valid_scene_unchanged": True,
    "fixed_conditions": {
        "output_contract_passed": True,
        "collision_rate_max_percent": 0.0,
        "floating_rate_max_percent": 0.0,
        "oob_rate_max_percent": 0.0,
        "support_validity_min_percent": 100.0,
        "navmesh_success_required": True,
        "navigable_area_ratio_min_percent": 90.0,
    },
    "primary_connected_area_ratio_min_percent": 100.0,
    "operational_connected_area_ratio_min_percent": 80.0,
    "operational_rationale": "test",
    "connected_sensitivity_thresholds_percent": [100.0, 80.0, 0.0],
    "aggregation": {"failure_policy": "itt"},
}


def make_record(spec: int, seed: int) -> dict:
    return {
        "spec_id": f"spec_{spec:02d}",
        "seed": seed,
        "output_contract_passed": True,
        "collision_rate": 0.0,
        "floating_rate": 0.0,
        "oob_rate": 0.0,
        "support_validity": 100.0,
        "navmesh_success_rate": 100.0,
        "navigable_area_ratio": 95.0,
        "connected_area_ratio": 85.0,
        "valid_scene_rate": 0.0,
        "geometry_available": True,
    }


class ValidSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            make_record(spec, seed) for spec in range(25) for seed in range(4)
        ]

    def test_operational_relaxes_only_connected_gate(self):
        payload = analyze(self.records, CONFIG, repeats=100, seed=7)
        self.assertEqual(payload["sensitivity"][0]["rate_percent_itt"], 0.0)
        self.assertEqual(payload["operational_valid"]["rate_percent_itt"], 100.0)
        self.assertEqual(
            payload["gate_breakdown_evaluated"][
                "fixed_conditions_except_connected_pass"
            ],
            100,
        )

    def test_structural_failure_still_fails_operational(self):
        record = copy.deepcopy(self.records[0])
        record["collision_rate"] = 0.01
        self.assertFalse(fixed_conditions_pass(record, CONFIG))

    def test_requires_complete_balanced_matrix(self):
        with self.assertRaisesRegex(RuntimeError, "25-spec x 4-seed"):
            analyze(self.records[:-1], CONFIG, repeats=10, seed=7)


if __name__ == "__main__":
    unittest.main()
