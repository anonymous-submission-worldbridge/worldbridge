"""Aggregation and ITT regression checks for SceneWeaver Table 3."""

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


import sys
from pathlib import Path

REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.sceneweaver.geometry.metrics.aggregate_sceneweaver import (
    aggregate_sceneweaver_records,
)


def main() -> None:
    records = []
    for spec_index in range(25):
        for seed in range(4):
            failed = spec_index < 10
            records.append(
                {
                    "spec_id": f"spec_{spec_index:02d}",
                    "logical_seed": seed,
                    "collision_rate": 100.0 if failed else 0.0,
                    "floating_rate": 100.0 if failed else 0.0,
                    "oob_rate": 100.0 if failed else 0.0,
                    "support_validity": 0.0 if failed else 100.0,
                    "navigable_area_ratio": 0.0 if failed else 80.0,
                    "connected_area_ratio": 0.0 if failed else 100.0,
                    "navmesh_success_rate": 0.0 if failed else 100.0,
                    "valid_scene_rate": 0.0 if failed else 100.0,
                    "geometry_available": not failed,
                    "instances_available": not failed,
                    "output_contract_passed": not failed,
                    "failure_reason": "synthetic_failure" if failed else None,
                    "eligible_objects": 5 if not failed else 0,
                    "support_edges": 5 if not failed else 0,
                }
            )
    payload = aggregate_sceneweaver_records(records, 1000, 20260909)
    assert payload["planned_runs"] == 100
    assert payload["evaluated_runs"] == 60
    assert payload["aggregate"]["metrics"]["collision_rate"]["mean"] == 40.0
    assert payload["aggregate"]["metrics"]["navigable_area_ratio"]["mean"] == 48.0
    assert payload["aggregate"]["metrics"]["valid_scene_rate"]["mean"] == 60.0
    print("SCENEWEAVER_TABLE3_AGGREGATE_FIXTURES_OK")


if __name__ == "__main__":
    main()
