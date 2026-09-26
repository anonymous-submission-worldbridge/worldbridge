#!/usr/bin/env python3
"""Repair and incrementally finish SceneWeaver WorldScore records on many GPUs."""

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
import concurrent.futures
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES.parent
DATA_ROOT = BASELINES / "data/table2"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
EVALUATOR = BASELINES / "evaluation/visual/eval_worldscore.py"
PYTHON = BASELINES / "envs/worldscore/bin/python"
ABI_ROOT = BASELINES / "work/metaurban/worldscore_abi"
ABI_FILES = (
    ABI_ROOT / "droid_backends.cpython-39-x86_64-linux-gnu.so",
    ABI_ROOT / "lietorch_backends.cpython-39-x86_64-linux-gnu.so",
)
WORLD_SCORE_COMMIT = "096c75fc4ada9c7d92e03140c3c1f0c8f383b61f"
DROID_SLAM_COMMIT = "8016d2b9b72b101a3e9ac804ebf20b4c654dc291"
CHECKPOINT_SHA256 = "46476ef64cde45a97504910d6f3de2eef7b398ec1c6e4e668815c29076024526"
INFRASTRUCTURE_MARKERS = (
    "out of memory",
    "cuda error",
    "cublas",
    "cudnn",
    "device-side",
    "driver",
    "no cuda",
    "glibc_",
    "worldscore_worker_crashed",
)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def valid_record(path: Path, spec_id: str, seed: int) -> bool:
    record = load_json(path)
    if record is None:
        return False
    valid_identity = (
        record.get("method") == "sceneweaver"
        and record.get("domain") == "indoor"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("worldscore_commit") == WORLD_SCORE_COMMIT
        and record.get("droid_slam_commit") == DROID_SLAM_COMMIT
        and record.get("checkpoint_sha256") == CHECKPOINT_SHA256
        and isinstance(record.get("consistency_3d"), (int, float))
        and math.isfinite(float(record["consistency_3d"]))
    )
    if not valid_identity:
        return False
    if record.get("success") is True:
        return True
    if record.get("failure_reason") != "droid_slam_failed":
        return False
    detail = str(record.get("failure_detail", "")).lower()
    return not any(marker in detail for marker in INFRASTRUCTURE_MARKERS)


def environment(gpu: int) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TORCH_HOME": str(BASELINES / "cache/torch"),
            "XDG_CACHE_HOME": str(BASELINES / "cache/xdg_metrics"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(
                part for part in (str(ABI_ROOT), existing) if part
            ),
        }
    )
    return env


def run_one(task: tuple[str, int], gpu: int, data_root: Path) -> dict[str, Any]:
    spec_id, seed = task
    run_dir = data_root / "indoor/sceneweaver" / spec_id / f"seed_{seed}"
    metric_path = run_dir / "metrics/consistency_3d.json"
    if valid_record(metric_path, spec_id, seed):
        record = load_json(metric_path) or {}
        return {
            "spec_id": spec_id,
            "seed": seed,
            "gpu": gpu,
            "skipped": True,
            "valid": True,
            "score": record.get("consistency_3d"),
            "metric_success": record.get("success") is True,
        }
    command = [
        str(PYTHON),
        str(EVALUATOR),
        "--worker",
        "--data-root",
        str(data_root),
        "--method",
        "sceneweaver",
        "--domain",
        "indoor",
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--gpu",
        str(gpu),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment(gpu),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    record = load_json(metric_path) or {}
    return {
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "skipped": False,
        "valid": valid_record(metric_path, spec_id, seed),
        "score": record.get("consistency_3d"),
        "metric_success": record.get("success") is True,
        "returncode": completed.returncode,
        "output": completed.stdout[-3000:],
    }


def run_queue(
    gpu: int, tasks: list[tuple[str, int]], data_root: Path
) -> list[dict[str, Any]]:
    records = []
    for index, task in enumerate(tasks, 1):
        result = run_one(task, gpu, data_root)
        records.append(result)
        print(
            f"SCENEWEAVER_WORLDSCORE {'OK' if result['valid'] else 'RETRY_NEEDED'} "
            f"gpu={gpu} item={index}/{len(tasks)} spec={task[0]} seed={task[1]} "
            f"score={result['score']} skipped={result['skipped']}",
            flush=True,
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES / "results/sceneweaver/indoor/worldscore_incremental.json",
    )
    args = parser.parse_args()
    missing = [str(path) for path in ABI_FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing baselines-local WorldScore ABI files: {missing}"
        )
    if not args.gpus or len(set(args.gpus)) != len(args.gpus):
        parser.error("--gpus must contain unique physical GPU indices")

    spec_ids = [
        json.loads(line)["spec_id"]
        for line in args.spec_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tasks = [
        (spec_id, seed)
        for spec_id in spec_ids
        for seed in range(4)
        if (
            args.data_root / "indoor/sceneweaver" / spec_id / f"seed_{seed}" / "SUCCESS"
        ).is_file()
    ]
    queues = {gpu: [] for gpu in args.gpus}
    for index, task in enumerate(tasks):
        queues[args.gpus[index % len(args.gpus)]].append(task)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = [
            executor.submit(run_queue, gpu, queues[gpu], args.data_root)
            for gpu in args.gpus
        ]
        results = [record for future in futures for record in future.result()]
    invalid = [record for record in results if not record["valid"]]
    payload = {
        "method": "sceneweaver",
        "tasks": len(tasks),
        "valid": len(results) - len(invalid),
        "skipped": sum(bool(record["skipped"]) for record in results),
        "invalid": invalid,
        "worldscore_abi_root": str(ABI_ROOT),
        "records": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        f"SCENEWEAVER_WORLDSCORE_COMPLETE tasks={len(tasks)} valid={payload['valid']} "
        f"skipped={payload['skipped']} invalid={len(invalid)} output={args.output}",
        flush=True,
    )
    return int(bool(invalid))


if __name__ == "__main__":
    raise SystemExit(main())
