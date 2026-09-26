#!/usr/bin/env python3
"""Evaluate successful Table-2 runs with WorldScore on parallel GPU queues.

The frozen evaluator remains the sole metric implementation.  This file only
selects successful runs, skips already valid per-scene records, and invokes one
fresh evaluator process per scene.
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
import concurrent.futures
import json
import subprocess
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
EVALUATOR = BASELINES / "evaluation/visual/eval_worldscore.py"
PYTHON = BASELINES / "envs/worldscore/bin/python"
RESULTS = BASELINES / "results/worldscore_incremental"
WORLD_SCORE_COMMIT = "096c75fc4ada9c7d92e03140c3c1f0c8f383b61f"
DROID_SLAM_COMMIT = "8016d2b9b72b101a3e9ac804ebf20b4c654dc291"
CHECKPOINT_SHA256 = "46476ef64cde45a97504910d6f3de2eef7b398ec1c6e4e668815c29076024526"


def load_spec_ids() -> list[str]:
    return [
        json.loads(line)["spec_id"]
        for line in SPEC_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def valid_existing(path: Path, spec_id: str, seed: int) -> bool:
    if not path.exists():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    provenance_valid = (
        record.get("method") == "infinigen_indoors"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("worldscore_commit") == WORLD_SCORE_COMMIT
        and record.get("droid_slam_commit") == DROID_SLAM_COMMIT
        and record.get("checkpoint_sha256") == CHECKPOINT_SHA256
        and isinstance(record.get("consistency_3d"), (int, float))
    )
    if not provenance_valid:
        return False
    if record.get("success") is True:
        return True
    if record.get("failure_reason") != "droid_slam_failed":
        return False
    detail = str(record.get("failure_detail", "")).lower()
    infrastructure_markers = (
        "out of memory",
        "cuda error",
        "cublas",
        "cudnn",
        "device-side",
        "driver",
        "no cuda",
    )
    return not any(marker in detail for marker in infrastructure_markers)


def gpu_free_mib(gpu: int) -> int:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.free",
            "--format=csv,noheader,nounits",
            "-i",
            str(gpu),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"nvidia-smi failed for GPU {gpu}: {completed.stdout.strip()}"
        )
    return int(completed.stdout.strip().splitlines()[0])


def wait_for_gpu(gpu: int, min_free_mib: int, poll_seconds: int) -> None:
    while True:
        free_mib = gpu_free_mib(gpu)
        if free_mib >= min_free_mib:
            return
        print(
            f"WORLDSCORE_WAIT_GPU gpu={gpu} free_mib={free_mib} "
            f"required_mib={min_free_mib}",
            flush=True,
        )
        time.sleep(poll_seconds)


def run_one(spec_id: str, seed: int, gpu: int) -> dict:
    run_dir = DATA_ROOT / spec_id / f"seed_{seed}"
    metric_path = run_dir / "metrics/consistency_3d.json"
    if valid_existing(metric_path, spec_id, seed):
        record = json.loads(metric_path.read_text(encoding="utf-8"))
        return {
            "spec_id": spec_id,
            "seed": seed,
            "gpu": gpu,
            "skipped": True,
            "success": bool(record.get("success")),
            "score": float(record["consistency_3d"]),
            "output": "valid_existing",
        }

    output = RESULTS / f"{spec_id}_seed_{seed}.jsonl"
    command = [
        str(PYTHON),
        str(EVALUATOR),
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--gpu",
        str(gpu),
        "--output",
        str(output),
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=BASELINES.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if not metric_path.exists():
        return {
            "spec_id": spec_id,
            "seed": seed,
            "gpu": gpu,
            "skipped": False,
            "success": False,
            "score": None,
            "wall_time_s": time.monotonic() - started,
            "output": completed.stdout[-4000:],
        }
    record = json.loads(metric_path.read_text(encoding="utf-8"))
    return {
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "skipped": False,
        "success": bool(record.get("success")),
        "score": float(record["consistency_3d"]),
        "wall_time_s": time.monotonic() - started,
        "output": completed.stdout[-4000:],
    }


def run_queue(
    gpu: int,
    tasks: list[tuple[str, int]],
    min_free_mib: int,
    poll_seconds: int,
) -> list[dict]:
    results = []
    for index, (spec_id, seed) in enumerate(tasks, 1):
        wait_for_gpu(gpu, min_free_mib, poll_seconds)
        result = run_one(spec_id, seed, gpu)
        results.append(result)
        print(
            f"WORLDSCORE_INCREMENTAL {'OK' if result['success'] else 'ZERO'} "
            f"gpu={gpu} item={index}/{len(tasks)} spec={spec_id} seed={seed} "
            f"score={result['score']} skipped={result['skipped']}",
            flush=True,
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpus", type=int, nargs="+", default=[2, 5])
    parser.add_argument("--min-free-mib", type=int, default=10000)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    if not args.gpus:
        parser.error("at least one GPU is required")
    if args.min_free_mib < 0:
        parser.error("--min-free-mib must be non-negative")
    if args.poll_seconds < 5 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 5 and 60")

    tasks = []
    for spec_id in load_spec_ids():
        for seed in range(4):
            run_dir = DATA_ROOT / spec_id / f"seed_{seed}"
            if (run_dir / "SUCCESS").exists():
                tasks.append((spec_id, seed))
    queues = {gpu: [] for gpu in args.gpus}
    for index, task in enumerate(tasks):
        queues[args.gpus[index % len(args.gpus)]].append(task)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(
        f"WORLDSCORE_INCREMENTAL_START tasks={len(tasks)} gpus={args.gpus}",
        flush=True,
    )
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = [
            executor.submit(
                run_queue,
                gpu,
                queues[gpu],
                args.min_free_mib,
                args.poll_seconds,
            )
            for gpu in args.gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())
    failures = [result for result in all_results if result["score"] is None]
    print(
        f"WORLDSCORE_INCREMENTAL_COMPLETE records={len(all_results)} "
        f"missing={len(failures)}",
        flush=True,
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
