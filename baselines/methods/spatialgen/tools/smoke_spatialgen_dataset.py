#!/usr/bin/env python3
"""Load one compiled run through SpatialGen's unmodified ExampleDataset."""

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


import argparse
import json
import sys
from pathlib import Path

import torch


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPATIALGEN_ROOT = BASELINES_ROOT / "vendor/SpatialGen"
sys.path.insert(0, str(SPATIALGEN_ROOT))

from src.data.example_loader import ExampleDataset  # noqa: E402


def assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Run directory must be inside baselines/: {resolved}"
        ) from exc
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = assert_baselines_path(args.run_dir)
    spec = json.loads((run_dir / "input/spec.json").read_text(encoding="utf-8"))
    dataset_root = run_dir / "input/dataset"
    dataset = ExampleDataset(
        data_dir=str(dataset_root),
        dataset_name="spatialgen",
        split_filepath=str(dataset_root / "test_split.txt"),
        image_height=512,
        image_width=512,
        T_in=1,
        total_view=16,
        validation=True,
        use_normal=False,
        use_semantic=True,
        use_metric_depth=False,
        use_scene_coord_map=True,
        use_layout_prior=True,
        use_layout_prior_from_p3d=True,
        return_metric_data=True,
    )
    if len(dataset) != 1:
        raise RuntimeError(f"Expected one compiled room, got {len(dataset)}")
    item = dataset[0]
    expected_shapes = {
        "image_input": (1, 3, 512, 512),
        "image_target": (15, 3, 512, 512),
        "semantic_layout_input": (1, 3, 512, 512),
        "semantic_layout_target": (15, 3, 512, 512),
        "depth_layout_input": (1, 3, 512, 512),
        "depth_layout_target": (15, 3, 512, 512),
        "pose_in": (1, 4, 4),
        "pose_out": (15, 4, 4),
        "pose_metric_input": (1, 4, 4),
        "pose_metric_target": (15, 4, 4),
    }
    for key, expected in expected_shapes.items():
        value = item.get(key)
        if not torch.is_tensor(value) or tuple(value.shape) != expected:
            raise RuntimeError(
                f"Unexpected {key}: type={type(value).__name__} "
                f"shape={getattr(value, 'shape', None)} expected={expected}"
            )
        if not torch.isfinite(value).all():
            raise RuntimeError(f"{key} contains non-finite values")
    room_uid = item["room_uid"]
    if room_uid != spec["spec_id"]:
        raise RuntimeError(f"Unexpected room_uid={room_uid!r}")
    print(
        "SPATIALGEN_DATASET_SMOKE_OK "
        f"spec={room_uid} keys={len(item)} scene_scale={float(item['scene_scale']):.8f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
