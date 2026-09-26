#!/usr/bin/env python3
"""Run an explicit, non-Cartesian list of frozen Infinigen matrix tasks."""

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

from baselines.methods.infinigen.run import load_spec_ids
from baselines.methods.infinigen.run import run_gpu_queue


def parse_task(value: str) -> tuple[str, int]:
    try:
        spec_id, seed_text = value.rsplit(":", 1)
        seed = int(seed_text)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            f"Task must have form SPEC_ID:SEED, got {value!r}"
        ) from error
    if seed not in (0, 1, 2, 3):
        raise argparse.ArgumentTypeError(f"Seed must be one of 0,1,2,3, got {seed}")
    return spec_id, seed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("generate", "render", "all"), default="all")
    parser.add_argument("--task", action="append", type=parse_task, required=True)
    parser.add_argument("--gpus", type=int, nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    args = parser.parse_args()

    known_specs = set(load_spec_ids())
    unknown = sorted({spec_id for spec_id, _ in args.task} - known_specs)
    if unknown:
        parser.error(f"Unknown spec ids: {unknown}")
    if len(set(args.task)) != len(args.task):
        parser.error("Duplicate tasks are not allowed")
    active_gpus = args.gpus[: min(args.workers, len(args.gpus))]
    if not active_gpus:
        parser.error("At least one GPU is required")

    queues = {gpu: [] for gpu in active_gpus}
    for index, task in enumerate(args.task):
        queues[active_gpus[index % len(active_gpus)]].append(task)
    print(
        f"TASKLIST_START phase={args.phase} tasks={len(args.task)} "
        f"workers={len(active_gpus)} gpus={active_gpus}",
        flush=True,
    )
    failures = []
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
        f"TASKLIST_COMPLETE total={len(args.task)} failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
