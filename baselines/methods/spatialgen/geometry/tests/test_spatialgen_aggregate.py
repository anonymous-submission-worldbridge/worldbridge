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

from baselines.methods.spatialgen.geometry.metrics.aggregate_spatialgen import aggregate


def write_metric(root, spec_id, seed, nav, connected, success):
    run = root / spec_id / f"seed_{seed}"
    (run / "metrics").mkdir(parents=True)
    (run / "scene").mkdir()
    (run / "metrics/navigability.json").write_text(
        json.dumps(
            {
                "navigable_area_ratio": nav,
                "connected_area_ratio": connected,
                "navmesh_success": success,
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    (run / "scene/reconstruction.json").write_text(
        json.dumps({"calibration": {"position_rmse_m": 0.0}}), encoding="utf-8"
    )


def test_macro_aggregation_and_missing_run_itt_zero(tmp_path):
    write_metric(tmp_path, "a", 0, 100.0, 80.0, True)
    write_metric(tmp_path, "a", 1, 0.0, 20.0, False)
    write_metric(tmp_path, "b", 0, 50.0, 50.0, True)
    # b/seed_1 is deliberately absent and must contribute an ITT zero.
    specs = [{"spec_id": "a"}, {"spec_id": "b"}]
    protocol = {
        "seeds": [0, 1],
        "aggregation": {
            "order": "mean_over_spec(mean_over_seed(scene_metric))",
            "bootstrap_repeats": 100,
            "bootstrap_seed": 7,
        },
    }
    result = aggregate(tmp_path, specs, protocol)
    assert result["planned_runs"] == 4
    assert result["evaluated_runs"] == 3
    assert np.isclose(result["metrics"]["navigable_area_ratio"]["mean"], 37.5)
    assert np.isclose(result["metrics"]["connected_area_ratio"]["mean"], 37.5)
    assert np.isclose(result["metrics"]["navmesh_success_rate"]["mean"], 50.0)
    assert result["failure_breakdown"] == {"missing_metric": 1}
    assert result["geometry_coverage"] == 75.0
    assert result["scale_calibration_coverage"] == 75.0
