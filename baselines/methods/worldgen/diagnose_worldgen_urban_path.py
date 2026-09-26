#!/usr/bin/env python3
"""Render existing WorldGen urban pilot splats at one uniform path scale."""

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
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "work/worldgen/pilot_generated/table2"
DEFAULT_OUTPUT_ROOT = BASELINES_ROOT / "work/worldgen/path_diagnostics"


def load_renderer() -> Any:
    path = BASELINES_ROOT / "methods/worldgen/tools/render_worldgen_generation.py"
    spec = importlib.util.spec_from_file_location("worldgen_renderer_diagnostic", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load renderer: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path must remain below {BASELINES_ROOT}: {resolved}"
        ) from exc
    return resolved


def scaled_transforms(renderer: Any, scale: float) -> list[np.ndarray]:
    return coefficient_transforms(renderer, -scale, scale)


def coefficient_transforms(
    renderer: Any, start_coefficient: float, end_coefficient: float
) -> list[np.ndarray]:
    transforms = []
    direction = np.asarray([2.0, 0.0, 1.0], dtype=np.float32)
    originals = renderer.camera_path("urban")
    for index, original in enumerate(originals):
        fraction = index / (len(originals) - 1)
        smooth = fraction * fraction * (3.0 - 2.0 * fraction)
        coefficient = start_coefficient * (1.0 - smooth) + end_coefficient * smooth
        transform = original.copy()
        transform[:3, 3] = direction * coefficient
        transforms.append(transform)
    return transforms


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=float)
    parser.add_argument("--start-coefficient", type=float)
    parser.add_argument("--end-coefficient", type=float)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    coefficient_mode = (
        args.start_coefficient is not None or args.end_coefficient is not None
    )
    if args.scale is not None and coefficient_mode:
        raise ValueError("use either --scale or explicit coefficients, not both")
    if args.scale is None and not coefficient_mode:
        raise ValueError("provide --scale or both explicit coefficients")
    if coefficient_mode and (
        args.start_coefficient is None or args.end_coefficient is None
    ):
        raise ValueError("both explicit coefficients are required")
    if args.scale is not None:
        if not (0.0 < args.scale <= 1.0):
            raise ValueError("scale must be in (0, 1]")
        start_coefficient, end_coefficient = -args.scale, args.scale
        output_tag = f"scale_{args.scale:.3f}"
    else:
        start_coefficient = args.start_coefficient
        end_coefficient = args.end_coefficient
        output_tag = f"range_{start_coefficient:.3f}_{end_coefficient:.3f}"
    data_root = require_below_baselines(args.data_root)
    output_root = require_below_baselines(args.output_root) / "urban" / output_tag
    renderer = load_renderer()
    transforms = coefficient_transforms(renderer, start_coefficient, end_coefficient)

    import torch

    records = []
    run_dirs = sorted((data_root / "urban/worldgen").glob("*/seed_*"))
    if len(run_dirs) != 10:
        raise RuntimeError(f"Expected 10 urban pilot runs, found {len(run_dirs)}")
    for run_dir in run_dirs:
        spec_id = run_dir.parent.name
        seed_name = run_dir.name
        scene = run_dir / "scene/splat.ply"
        if not scene.exists():
            raise FileNotFoundError(scene)
        destination = output_root / spec_id / seed_name
        sequence_dir = destination / "renders/sequence"
        anchor_dir = destination / "renders/anchors"
        sequence_dir.mkdir(parents=True, exist_ok=True)
        anchor_dir.mkdir(parents=True, exist_ok=True)
        splat_np = renderer.load_splat(scene)
        arrays = {
            name: torch.from_numpy(value).to(device="cuda", dtype=torch.float32)
            for name, value in splat_np.items()
        }
        stats = []
        for index, transform in enumerate(transforms):
            output = sequence_dir / f"rgb_{index:03d}.png"
            image = renderer.render_one(arrays, transform, *renderer.SEQUENCE_SIZE)
            Image.fromarray(image).save(output)
            pixels = image.astype(np.float32) / 255.0
            stats.append(
                {
                    "path": str(output.relative_to(destination)),
                    "mean": float(pixels.mean()),
                    "std": float(pixels.std()),
                }
            )
        for anchor_index, frame_index in enumerate(renderer.ANCHOR_INDICES):
            output = anchor_dir / f"rgb_{anchor_index:03d}.png"
            image = renderer.render_one(
                arrays, transforms[frame_index], *renderer.ANCHOR_SIZE
            )
            Image.fromarray(image).save(output)
            pixels = image.astype(np.float32) / 255.0
            stats.append(
                {
                    "path": str(output.relative_to(destination)),
                    "mean": float(pixels.mean()),
                    "std": float(pixels.std()),
                }
            )
        sequence_k = renderer.intrinsic(*renderer.SEQUENCE_SIZE)
        atomic_json(
            sequence_dir / "cameras.json",
            {
                "coordinate_system": "WorldGen/OpenCV x-right, y-down, z-forward",
                "trajectory_units": "native_normalized_not_metric",
                "horizontal_fov_degrees": renderer.HORIZONTAL_FOV_DEGREES,
                "sequence_resolution": list(renderer.SEQUENCE_SIZE),
                "anchor_resolution": list(renderer.ANCHOR_SIZE),
                "anchor_frame_indices": list(renderer.ANCHOR_INDICES),
                "trajectory_path_length_native_units": renderer.path_length(transforms),
                "sequence": [
                    {
                        "index": index,
                        "K": sequence_k.tolist(),
                        "camera_to_world": transform.tolist(),
                        "world_to_camera": np.linalg.inv(transform).tolist(),
                    }
                    for index, transform in enumerate(transforms)
                ],
            },
        )
        errors = []
        for stat in stats:
            if not (0.01 <= stat["mean"] <= 0.99):
                errors.append(f"{stat['path']}: mean={stat['mean']:.6f}")
            if stat["std"] < 0.01:
                errors.append(f"{stat['path']}: std={stat['std']:.6f}")
        record = {
            "spec_id": spec_id,
            "seed": int(seed_name.removeprefix("seed_")),
            "start_coefficient": start_coefficient,
            "end_coefficient": end_coefficient,
            "trajectory_path_length_native_units": renderer.path_length(transforms),
            "valid_image_contract": not errors,
            "errors": errors,
            "image_stats": stats,
        }
        atomic_json(destination / "renders/validation.json", record)
        success_marker = destination / "SUCCESS"
        if errors:
            success_marker.unlink(missing_ok=True)
        else:
            success_marker.write_text("worldgen path diagnostic valid\n")
        records.append(record)
        print(
            f"WORLDGEN_PATH_DIAGNOSTIC range={start_coefficient:.3f}:"
            f"{end_coefficient:.3f} spec={spec_id} "
            f"seed={record['seed']} valid={not errors} errors={len(errors)}",
            flush=True,
        )
        del arrays
        torch.cuda.empty_cache()
    summary = {
        "start_coefficient": start_coefficient,
        "end_coefficient": end_coefficient,
        "trajectory_path_length_native_units": renderer.path_length(transforms),
        "runs": len(records),
        "valid_runs": sum(record["valid_image_contract"] for record in records),
        "records": records,
    }
    atomic_json(output_root / "summary.json", summary)
    print(
        f"WORLDGEN_PATH_DIAGNOSTIC_COMPLETE range={start_coefficient:.3f}:"
        f"{end_coefficient:.3f} "
        f"valid={summary['valid_runs']}/{summary['runs']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
