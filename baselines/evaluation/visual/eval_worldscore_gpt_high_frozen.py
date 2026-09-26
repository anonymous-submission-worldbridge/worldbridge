#!/usr/bin/env python3
"""Evaluate static 3D consistency with WorldScore's DROID-SLAM metric.

The public WorldScore metric is imported from the vendored, commit-pinned source.
Each scene is evaluated in a fresh process so that DROID-SLAM GPU/shared-memory
state cannot leak into the next scene.  The Table-2 score is WorldScore's
official empirical normalization of reprojection error, multiplied by 100.
"""

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
import os
import random
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Iterator


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
WORLD_SCORE_ROOT = BASELINES_ROOT / "vendor/WorldScore"
DROID_PYTHON_ROOT = (
    WORLD_SCORE_ROOT / "worldscore/benchmark/metrics/third_party/droid_slam"
)
CHECKPOINT = WORLD_SCORE_ROOT / "worldscore/benchmark/metrics/checkpoints/droid.pth"
WORLD_SCORE_COMMIT = "096c75fc4ada9c7d92e03140c3c1f0c8f383b61f"
DROID_SLAM_COMMIT = "8016d2b9b72b101a3e9ac804ebf20b4c654dc291"
CHECKPOINT_SHA256 = "46476ef64cde45a97504910d6f3de2eef7b398ec1c6e4e668815c29076024526"
EMPIRICAL_MIN = 0.0
EMPIRICAL_MAX = 1.0719
EVALUATION_SEED = 0


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_specs(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def base_record(
    spec_id: str,
    logical_seed: int,
    method: str = "infinigen_indoors",
    domain: str = "indoor",
) -> dict[str, Any]:
    return {
        "method": method,
        "domain": domain,
        "spec_id": spec_id,
        "logical_seed": logical_seed,
        "metric": "worldscore_static_3d_consistency",
        "frames_expected": 50,
        "worldscore_commit": WORLD_SCORE_COMMIT,
        "droid_slam_commit": DROID_SLAM_COMMIT,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "empirical_min": EMPIRICAL_MIN,
        "empirical_max": EMPIRICAL_MAX,
        "evaluation_seed": EVALUATION_SEED,
        "higher_is_better": True,
    }


def failure_record(
    spec_id: str,
    logical_seed: int,
    reason: str,
    detail: str = "",
    method: str = "infinigen_indoors",
    domain: str = "indoor",
) -> dict[str, Any]:
    record = base_record(spec_id, logical_seed, method, domain)
    record.update(
        {
            "success": False,
            "raw_reprojection_error": None,
            "valid_reprojection_samples": 0,
            "consistency_3d": 0.0,
            "failure_policy": "itt_zero",
            "failure_reason": reason,
            "failure_detail": detail,
        }
    )
    return record


def normalized_consistency(raw_error: float) -> float:
    clipped = min(EMPIRICAL_MAX, max(EMPIRICAL_MIN, raw_error))
    normalized = 1.0 - (clipped - EMPIRICAL_MIN) / (EMPIRICAL_MAX - EMPIRICAL_MIN)
    return 100.0 * normalized


def load_sequence_calib(run_dir: Path, expected_frames: int = 50) -> list[float]:
    """Load the rendered sequence intrinsics instead of using DROID's demo default."""
    cameras_path = run_dir / "renders/sequence/cameras.json"
    payload = json.loads(cameras_path.read_text(encoding="utf-8"))
    sequence = payload.get("sequence", [])
    if len(sequence) != expected_frames:
        raise ValueError(
            f"Expected {expected_frames} camera records, found {len(sequence)}"
        )
    calibrations = []
    for index, record in enumerate(sequence):
        matrix = record.get("K")
        if (
            not isinstance(matrix, list)
            or len(matrix) != 3
            or any(not isinstance(row, list) or len(row) != 3 for row in matrix)
        ):
            raise ValueError(f"Invalid K matrix in camera record {index}")
        calibrations.append(
            [
                float(matrix[0][0]),
                float(matrix[1][1]),
                float(matrix[0][2]),
                float(matrix[1][2]),
            ]
        )
    reference = calibrations[0]
    for index, calibration in enumerate(calibrations[1:], 1):
        if any(
            abs(value - expected) > 1e-4
            for value, expected in zip(calibration, reference)
        ):
            raise ValueError(
                f"Sequence intrinsics change at frame {index}: {calibration} != {reference}"
            )
    return reference


def image_stream(
    image_list: list[str], stride: int, calib: list[float]
) -> Iterator[tuple[int, Any, Any]]:
    # This mirrors WorldScore's public reprojection_error_metrics.py exactly.
    import cv2
    import numpy as np
    import torch

    fx, fy, cx, cy = calib
    for timestamp, image_path in enumerate(image_list[::stride]):
        image = cv2.imread(image_path)
        if image is None:
            raise RuntimeError(f"cv2 could not read {image_path}")
        height_0, width_0, _ = image.shape
        height_1 = int(height_0 * np.sqrt((512 * 512) / (height_0 * width_0)))
        width_1 = int(width_0 * np.sqrt((512 * 512) / (height_0 * width_0)))
        image = cv2.resize(image, (width_1, height_1))
        image = image[: height_1 - height_1 % 8, : width_1 - width_1 % 8]
        image_tensor = torch.as_tensor(image).permute(2, 0, 1)
        intrinsics = torch.as_tensor([fx, fy, cx, cy])
        intrinsics[0::2] *= width_1 / width_0
        intrinsics[1::2] *= height_1 / height_0
        yield timestamp, image_tensor[None], intrinsics


def evaluate_worker(
    run_dir: Path,
    spec_id: str,
    logical_seed: int,
    method: str,
    domain: str = "indoor",
) -> int:
    os.environ.setdefault("TORCH_HOME", str(BASELINES_ROOT / "cache/torch"))
    os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES_ROOT / "cache/xdg_metrics"))
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    sys.path.insert(0, str(DROID_PYTHON_ROOT))

    import numpy as np
    import torch
    from droid import Droid

    random.seed(EVALUATION_SEED)
    np.random.seed(EVALUATION_SEED)
    torch.manual_seed(EVALUATION_SEED)
    torch.cuda.manual_seed_all(EVALUATION_SEED)
    torch.backends.cudnn.benchmark = False

    output_path = run_dir / "metrics/consistency_3d.json"
    log_path = run_dir / "logs/worldscore.log"
    images = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    if not (run_dir / "SUCCESS").exists() or len(images) != 50:
        atomic_json(
            output_path,
            failure_record(
                spec_id,
                logical_seed,
                "missing_or_invalid_render",
                f"success_marker={(run_dir / 'SUCCESS').exists()} frames={len(images)}",
                method,
                domain,
            ),
        )
        return 0
    if not CHECKPOINT.exists():
        atomic_json(
            output_path,
            failure_record(
                spec_id,
                logical_seed,
                "missing_droid_checkpoint",
                method=method,
                domain=domain,
            ),
        )
        return 0

    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sequence_calib = load_sequence_calib(run_dir)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            with redirect_stdout(log), redirect_stderr(log):
                metric_args = argparse.Namespace(
                    t0=0,
                    stride=1,
                    weights=str(CHECKPOINT),
                    buffer=512,
                    beta=0.3,
                    filter_thresh=0.01,
                    warmup=8,
                    keyframe_thresh=4.0,
                    frontend_thresh=16.0,
                    frontend_window=25,
                    frontend_radius=2,
                    frontend_nms=1,
                    backend_thresh=22.0,
                    backend_radius=2,
                    backend_nms=3,
                    upsample=True,
                    stereo=False,
                    calib=sequence_calib,
                )
                image_paths = [str(path) for path in images]
                droid = None
                for timestamp, image, intrinsics in image_stream(
                    image_paths, metric_args.stride, metric_args.calib
                ):
                    if timestamp < metric_args.t0:
                        continue
                    if droid is None:
                        metric_args.image_size = [image.shape[2], image.shape[3]]
                        droid = Droid(metric_args)
                    droid.track(timestamp, image, intrinsics=intrinsics)
                if droid is None:
                    raise RuntimeError("DROID-SLAM received no frames")
                _, valid_errors = droid.terminate(
                    image_stream(image_paths, metric_args.stride, metric_args.calib)
                )
                if valid_errors is None or valid_errors.numel() == 0:
                    raise RuntimeError(
                        "DROID-SLAM returned no valid reprojection errors"
                    )
                raw_error = float(valid_errors.float().mean().item())
                valid_count = int(valid_errors.numel())
                del droid
                torch.cuda.empty_cache()
        record = base_record(spec_id, logical_seed, method, domain)
        record.update(
            {
                "success": True,
                "raw_reprojection_error": raw_error,
                "valid_reprojection_samples": valid_count,
                "consistency_3d": normalized_consistency(raw_error),
                "sequence_calibration_fx_fy_cx_cy": sequence_calib,
                "failure_policy": "none",
                "failure_reason": None,
                "failure_detail": "",
                "log": str(log_path.relative_to(run_dir)),
            }
        )
        atomic_json(output_path, record)
        return 0
    except Exception as exc:
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write("\nWORLD_SCORE_EXCEPTION\n")
            traceback.print_exc(file=log)
        atomic_json(
            output_path,
            failure_record(
                spec_id,
                logical_seed,
                "droid_slam_failed",
                repr(exc),
                method,
                domain,
            ),
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--domain", choices=("indoor", "urban"), default="indoor")
    parser.add_argument(
        "--metric", choices=("3d_consistency",), default="3d_consistency"
    )
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES_ROOT / "results/consistency_per_scene.jsonl",
    )
    parser.add_argument("--spec-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.frames != 50:
        raise ValueError("The frozen Table-2 protocol requires exactly 50 frames")
    if args.worker:
        if args.spec_id is None or args.seed is None:
            raise ValueError("Internal worker requires --spec-id and --seed")
        run_dir = (
            args.data_root
            / args.domain
            / args.method
            / args.spec_id
            / f"seed_{args.seed}"
        )
        return evaluate_worker(
            run_dir, args.spec_id, args.seed, args.method, args.domain
        )

    specs = load_specs(args.spec_file)
    selected_specs = [spec for spec in specs if args.spec_id in (None, spec["spec_id"])]
    selected_seeds = range(4) if args.seed is None else [args.seed]
    records = []
    for spec in selected_specs:
        for logical_seed in selected_seeds:
            run_dir = (
                args.data_root
                / args.domain
                / args.method
                / spec["spec_id"]
                / f"seed_{logical_seed}"
            )
            output_path = run_dir / "metrics/consistency_3d.json"
            if not (run_dir / "SUCCESS").exists():
                record = failure_record(
                    spec["spec_id"],
                    logical_seed,
                    "missing_or_invalid_render",
                    method=args.method,
                    domain=args.domain,
                )
                atomic_json(output_path, record)
            else:
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--data-root",
                    str(args.data_root),
                    "--method",
                    args.method,
                    "--domain",
                    args.domain,
                    "--spec-id",
                    spec["spec_id"],
                    "--seed",
                    str(logical_seed),
                    "--gpu",
                    str(args.gpu),
                ]
                environment = os.environ.copy()
                environment["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
                completed = subprocess.run(
                    command,
                    cwd=BASELINES_ROOT.parent,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if not output_path.exists():
                    record = failure_record(
                        spec["spec_id"],
                        logical_seed,
                        "worldscore_worker_crashed",
                        completed.stdout[-4000:],
                        args.method,
                        args.domain,
                    )
                    atomic_json(output_path, record)
                else:
                    record = json.loads(output_path.read_text(encoding="utf-8"))
            records.append(record)
            print(
                f"WORLDSCORE_{'OK' if record['success'] else 'FAILED'} "
                f"{spec['spec_id']} seed={logical_seed} "
                f"score={record['consistency_3d']:.6f}",
                flush=True,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(f"WORLDSCORE_COMPLETE records={len(records)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
