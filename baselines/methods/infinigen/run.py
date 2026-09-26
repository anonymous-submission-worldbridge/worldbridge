#!/usr/bin/env python3
"""Run the frozen Infinigen Indoors Table-2 matrix with bounded concurrency."""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER = ROOT / "methods/infinigen/adapter.py"
PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
SPEC_FILE = ROOT / "protocol/generation/indoor_specs.jsonl"


def load_spec_ids() -> list[str]:
    with SPEC_FILE.open("r", encoding="utf-8") as handle:
        return [json.loads(line)["spec_id"] for line in handle if line.strip()]


def run_one(
    phase: str,
    spec_id: str,
    seed: int,
    gpu: int,
    force: bool,
) -> dict:
    command = [
        str(PYTHON),
        str(ADAPTER),
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--phase",
        phase,
        "--gpu",
        str(gpu),
    ]
    if force:
        command.append("--force")
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "phase": phase,
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "exit_code": completed.returncode,
        "wall_time_s": time.monotonic() - started,
        "output": completed.stdout.strip(),
    }


def run_gpu_queue(
    phase: str,
    gpu: int,
    tasks: list[tuple[str, int]],
    force: bool,
    min_free_gib: float,
) -> list[dict]:
    """Run one serial queue per GPU to prevent accidental GPU oversubscription."""
    failures = []
    for task_index, (spec_id, seed) in enumerate(tasks):
        free_gib = shutil.disk_usage(ROOT).free / (1024**3)
        if free_gib < min_free_gib:
            skipped = tasks[task_index:]
            print(
                f"MATRIX_ABORT_LOW_DISK phase={phase} gpu={gpu} "
                f"free_gib={free_gib:.2f} min_free_gib={min_free_gib:.2f} "
                f"skipped={len(skipped)}",
                flush=True,
            )
            failures.extend(
                {
                    "phase": phase,
                    "spec_id": skipped_spec_id,
                    "seed": skipped_seed,
                    "gpu": gpu,
                    "exit_code": 75,
                    "wall_time_s": 0.0,
                    "output": (
                        f"not_started_low_disk free_gib={free_gib:.2f} "
                        f"min_free_gib={min_free_gib:.2f}"
                    ),
                }
                for skipped_spec_id, skipped_seed in skipped
            )
            break
        result = run_one(phase, spec_id, seed, gpu, force)
        status = "OK" if result["exit_code"] == 0 else "FAILED"
        print(
            f"MATRIX_ITEM {status} phase={result['phase']} "
            f"spec={result['spec_id']} seed={result['seed']} gpu={result['gpu']} "
            f"wall={result['wall_time_s']:.1f}s {result['output']}",
            flush=True,
        )
        if result["exit_code"] != 0:
            failures.append(result)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("generate", "render", "all"), required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1, 2, 3, 4, 5])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--spec-ids", nargs="+", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--min-free-gib",
        type=float,
        default=50.0,
        help="Stop before starting another task if filesystem free space is lower.",
    )
    args = parser.parse_args()
    if args.min_free_gib < 0:
        raise ValueError("--min-free-gib must be non-negative")
    spec_ids = args.spec_ids or load_spec_ids()
    active_gpus = args.gpus[: min(args.workers, len(args.gpus))]
    if not active_gpus:
        raise ValueError("At least one GPU is required")
    pairs = [(spec_id, seed) for spec_id in spec_ids for seed in args.seeds]
    queues = {gpu: [] for gpu in active_gpus}
    for index, pair in enumerate(pairs):
        queues[active_gpus[index % len(active_gpus)]].append(pair)
    failures = []
    print(
        f"MATRIX_START phase={args.phase} tasks={len(pairs)} workers={len(active_gpus)} "
        f"gpus={active_gpus}",
        flush=True,
    )
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(
                run_gpu_queue,
                args.phase,
                gpu,
                queues[gpu],
                args.force,
                args.min_free_gib,
            )
            for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            failures.extend(future.result())
    print(
        f"MATRIX_COMPLETE phase={args.phase} total={len(pairs)} failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
