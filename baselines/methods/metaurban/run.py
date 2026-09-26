#!/usr/bin/env python3
"""Run one serial MetaUrban queue on each of the explicitly allowed GPUs."""

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
import os
import shutil
import subprocess
import time
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER = BASELINES_ROOT / "methods/metaurban/adapter.py"
PYTHON = BASELINES_ROOT / "envs/metaurban/bin/python"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"
PILOT_SPEC_INDICES = (0, 6, 12, 18, 24)
ALLOWED_GPUS = (0, 1)
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def run_environment(gpu: int) -> dict[str, str]:
    if gpu not in ALLOWED_GPUS:
        raise ValueError(f"Only physical GPUs {ALLOWED_GPUS} are permitted")
    environment = os.environ.copy()
    for variable in PROXY_VARIABLES:
        environment.pop(variable, None)
    environment["CUDA_VISIBLE_DEVICES"] = str(gpu)
    return environment


def load_specs() -> list[dict]:
    return [
        json.loads(line)
        for line in SPEC_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def tasks_for(
    trial_mode: str, spec_ids: list[str] | None, seeds: list[int] | None
) -> list[tuple[str, int]]:
    specs = load_specs()
    if spec_ids is not None:
        requested = set(spec_ids)
        unknown = requested - {spec["spec_id"] for spec in specs}
        if unknown:
            raise ValueError(f"Unknown spec IDs: {sorted(unknown)}")
        specs = [spec for spec in specs if spec["spec_id"] in requested]
    elif trial_mode == "pilot":
        specs = [
            spec for spec in specs if int(spec["spec_index"]) in PILOT_SPEC_INDICES
        ]
    logical_seeds = (
        seeds
        if seeds is not None
        else ([0, 1] if trial_mode == "pilot" else [0, 1, 2, 3])
    )
    if any(seed not in (0, 1, 2, 3) for seed in logical_seeds):
        raise ValueError("Seeds must be chosen from 0,1,2,3")
    return [(spec["spec_id"], seed) for spec in specs for seed in logical_seeds]


def run_queue(
    gpu: int,
    queue: list[tuple[str, int]],
    trial_mode: str,
    force: bool,
    min_free_gib: float,
) -> list[dict]:
    failures: list[dict] = []
    for index, (spec_id, seed) in enumerate(queue):
        free_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
        if free_gib < min_free_gib:
            failures.extend(
                {
                    "spec_id": pending_spec,
                    "seed": pending_seed,
                    "gpu": gpu,
                    "exit_code": 75,
                    "reason": "not_started_low_disk",
                }
                for pending_spec, pending_seed in queue[index:]
            )
            break
        command = [
            str(PYTHON),
            str(ADAPTER),
            "--spec-id",
            spec_id,
            "--seed",
            str(seed),
            "--gpu",
            str(gpu),
            "--trial-mode",
            trial_mode,
        ]
        if force:
            command.append("--force")
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=BASELINES_ROOT.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=run_environment(gpu),
        )
        result = {
            "spec_id": spec_id,
            "seed": seed,
            "gpu": gpu,
            "exit_code": completed.returncode,
            "wall_time_s": time.monotonic() - started,
            "output": completed.stdout.strip(),
        }
        print(
            f"MATRIX_ITEM {'OK' if completed.returncode == 0 else 'FAILED'} "
            f"mode={trial_mode} spec={spec_id} seed={seed} gpu={gpu} "
            f"wall={result['wall_time_s']:.1f}s {result['output']}",
            flush=True,
        )
        if completed.returncode != 0:
            failures.append(result)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-mode", choices=("pilot", "formal"), required=True)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=100.0)
    args = parser.parse_args()
    if not args.gpus or any(gpu not in ALLOWED_GPUS for gpu in args.gpus):
        raise ValueError(f"Only physical GPUs {ALLOWED_GPUS} are permitted")
    active_gpus = list(dict.fromkeys(args.gpus))
    tasks = tasks_for(args.trial_mode, args.spec_ids, args.seeds)
    queues = {gpu: [] for gpu in active_gpus}
    for index, task in enumerate(tasks):
        queues[active_gpus[index % len(active_gpus)]].append(task)
    print(
        f"MATRIX_START mode={args.trial_mode} tasks={len(tasks)} gpus={active_gpus}",
        flush=True,
    )
    failures: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(
                run_queue,
                gpu,
                queues[gpu],
                args.trial_mode,
                args.force,
                args.min_free_gib,
            )
            for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            failures.extend(future.result())
    print(f"MATRIX_COMPLETE total={len(tasks)} failures={len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
