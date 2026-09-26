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

import pytest

from baselines.evaluation.visual.eval_worldscore import atomic_json
from baselines.evaluation.visual.eval_worldscore import base_record
from baselines.evaluation.visual.eval_worldscore import failure_record
from baselines.evaluation.visual.eval_worldscore import load_sequence_calib
from baselines.evaluation.visual.eval_worldscore import reusable_record


def write_cameras(run_dir: Path, records: list[dict]) -> None:
    path = run_dir / "renders/sequence/cameras.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"sequence": records}), encoding="utf-8")


def camera_record(focal: float = 365.630834) -> dict:
    return {
        "K": [
            [focal, 0.0, 256.0],
            [0.0, focal, 256.0],
            [0.0, 0.0, 1.0],
        ]
    }


def test_load_sequence_calib_uses_exported_intrinsics(tmp_path: Path) -> None:
    write_cameras(tmp_path, [camera_record() for _ in range(50)])
    assert load_sequence_calib(tmp_path) == [365.630834, 365.630834, 256.0, 256.0]


def test_load_sequence_calib_rejects_frame_varying_intrinsics(tmp_path: Path) -> None:
    records = [camera_record() for _ in range(50)]
    records[17] = camera_record(500.0)
    write_cameras(tmp_path, records)
    with pytest.raises(ValueError, match="change at frame 17"):
        load_sequence_calib(tmp_path)


def test_records_preserve_requested_method() -> None:
    assert base_record("indoor_bedroom_00", 0, "spatialgen")["method"] == "spatialgen"
    assert (
        failure_record("indoor_bedroom_00", 0, "test_failure", method="spatialgen")[
            "method"
        ]
        == "spatialgen"
    )


def test_reusable_record_requires_a_complete_matching_success(tmp_path: Path) -> None:
    output = tmp_path / "metrics/consistency_3d.json"
    record = base_record("indoor_bedroom_00", 0, "syncity3k", "indoor")
    record.update(
        success=True,
        raw_reprojection_error=0.25,
        valid_reprojection_samples=42,
        consistency_3d=76.7,
    )
    atomic_json(output, record)
    assert (
        reusable_record(output, "indoor_bedroom_00", 0, "syncity3k", "indoor", True)
        == record
    )

    record["success"] = False
    atomic_json(output, record)
    assert (
        reusable_record(output, "indoor_bedroom_00", 0, "syncity3k", "indoor", True)
        is None
    )


def test_reusable_record_accepts_only_expected_missing_render_failure(
    tmp_path: Path,
) -> None:
    output = tmp_path / "metrics/consistency_3d.json"
    record = failure_record(
        "urban_residential_four_way_00",
        3,
        "missing_or_invalid_render",
        method="syncity3k",
        domain="urban",
    )
    atomic_json(output, record)
    assert (
        reusable_record(
            output,
            "urban_residential_four_way_00",
            3,
            "syncity3k",
            "urban",
            False,
        )
        == record
    )
