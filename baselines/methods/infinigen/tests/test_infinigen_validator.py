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

from PIL import Image

from baselines.methods.infinigen.adapter import inspect_images


def write_camera_records(run_dir: Path, step_m: float) -> None:
    records = []
    for frame in range(50):
        matrix = [
            [1.0, 0.0, 0.0, frame * step_m],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 1.55],
            [0.0, 0.0, 0.0, 1.0],
        ]
        records.append(
            {
                "camera_to_world_blender": matrix,
                "source_camera_to_world_blender": matrix,
            }
        )
    path = run_dir / "renders/sequence/cameras.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "camera_pose_contract": {
                    "camera_height_m": 1.55,
                    "preserve_source_xy": True,
                    "preserve_source_forward": True,
                    "remove_roll_with_global_up": True,
                },
                "sequence": records,
            }
        ),
        encoding="utf-8",
    )


def write_tiny_render_set(run_dir: Path) -> None:
    anchors = run_dir / "renders/anchors"
    sequence = run_dir / "renders/sequence"
    anchors.mkdir(parents=True)
    sequence.mkdir(parents=True)
    image = Image.new("RGB", (2, 2), color=(64, 128, 192))
    for index in range(8):
        image.save(anchors / f"rgb_{index:03d}.png")
    for index in range(50):
        image.save(sequence / f"rgb_{index:03d}.png")


def test_validator_rejects_wrong_resolution_and_accepts_moving_trajectory(
    tmp_path: Path,
) -> None:
    write_tiny_render_set(tmp_path)
    write_camera_records(tmp_path, step_m=0.03)
    result = inspect_images(tmp_path)
    assert not result["valid"]
    assert result["trajectory"]["valid"]
    assert result["trajectory"]["pose_contract_valid"]
    assert result["trajectory"]["path_length_m"] > 1.0


def test_validator_rejects_nearly_static_trajectory(tmp_path: Path) -> None:
    write_tiny_render_set(tmp_path)
    write_camera_records(tmp_path, step_m=0.001)
    result = inspect_images(tmp_path)
    assert not result["trajectory"]["valid"]
