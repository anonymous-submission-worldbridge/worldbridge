#!/usr/bin/env python3
"""Run SpatialGen Table-2 tasks as one serial queue per selected GPU."""

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
import shutil
import subprocess
import sys
import time
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
ADAPTER = BASELINES_ROOT / "methods/spatialgen/adapter.py"
PYTHON = BASELINES_ROOT / "envs/spatialgen/bin/python"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"


def load_specs() -> list[dict]:
    with SPEC_FILE.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def gpu_free_mib(gpu: int) -> int | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu}",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return int(completed.stdout.strip()) if completed.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def run_one(args: argparse.Namespace, spec_id: str, seed: int, gpu: int) -> dict:
    command = [
        str(PYTHON),
        str(ADAPTER),
        "run",
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--data-root",
        str(args.data_root),
        "--phase",
        args.phase,
        "--gpu",
        str(gpu),
        "--prepare-device",
        args.prepare_device,
        "--flux-offload",
        args.flux_offload,
        "--prepare-timeout-s",
        str(args.prepare_timeout_s),
        "--reference-timeout-s",
        str(args.reference_timeout_s),
        "--generation-timeout-s",
        str(args.generation_timeout_s),
        "--render-timeout-s",
        str(args.render_timeout_s),
    ]
    if args.force:
        command.append("--force")
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "phase": args.phase,
        "exit_code": completed.returncode,
        "wall_time_s": time.monotonic() - started,
        "output": completed.stdout.strip(),
    }


def run_queue(
    args: argparse.Namespace, gpu: int, tasks: list[tuple[str, int]]
) -> list[dict]:
    failures: list[dict] = []
    for index, (spec_id, seed) in enumerate(tasks):
        free_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
        if free_gib < args.min_free_gib:
            print(
                f"SPATIALGEN_QUEUE_ABORT disk_free_gib={free_gib:.2f} "
                f"minimum={args.min_free_gib:.2f} gpu={gpu}",
                flush=True,
            )
            failures.extend(
                {
                    "spec_id": pending_spec,
                    "seed": pending_seed,
                    "gpu": gpu,
                    "phase": args.phase,
                    "exit_code": 75,
                    "wall_time_s": 0.0,
                    "output": "not_started_low_disk",
                }
                for pending_spec, pending_seed in tasks[index:]
            )
            break
        if args.phase in {"reference", "generate", "render", "all"}:
            free_mib = gpu_free_mib(gpu)
            wait_deadline = time.monotonic() + args.wait_for_gpu_s
            while (
                free_mib is not None
                and free_mib < args.min_free_gpu_mib
                and time.monotonic() < wait_deadline
            ):
                remaining_s = max(0, int(wait_deadline - time.monotonic()))
                print(
                    f"SPATIALGEN_QUEUE_WAIT gpu={gpu} free_mib={free_mib} "
                    f"minimum={args.min_free_gpu_mib} remaining_s={remaining_s}",
                    flush=True,
                )
                time.sleep(min(args.gpu_poll_interval_s, max(1, remaining_s)))
                free_mib = gpu_free_mib(gpu)
            if free_mib is not None and free_mib < args.min_free_gpu_mib:
                print(
                    f"SPATIALGEN_QUEUE_ABORT gpu={gpu} free_mib={free_mib} "
                    f"minimum={args.min_free_gpu_mib}",
                    flush=True,
                )
                failures.extend(
                    {
                        "spec_id": pending_spec,
                        "seed": pending_seed,
                        "gpu": gpu,
                        "phase": args.phase,
                        "exit_code": 75,
                        "wall_time_s": 0.0,
                        "output": "not_started_low_gpu_memory",
                    }
                    for pending_spec, pending_seed in tasks[index:]
                )
                break
        result = run_one(args, spec_id, seed, gpu)
        status = "OK" if result["exit_code"] == 0 else "FAILED"
        print(
            f"SPATIALGEN_ITEM {status} phase={args.phase} spec={spec_id} "
            f"seed={seed} gpu={gpu} wall={result['wall_time_s']:.1f}s "
            f"{result['output']}",
            flush=True,
        )
        if result["exit_code"] != 0:
            failures.append(result)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("compile", "prepare", "reference", "generate", "render", "all"),
        required=True,
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--spec-ids", nargs="+", default=None)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=BASELINES_ROOT / "data/table2",
        help="Output root; must remain below baselines/.",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Use the first frozen specification in each of the five room categories.",
    )
    parser.add_argument("--prepare-device", choices=("cpu", "cuda:0"), default="cuda:0")
    parser.add_argument(
        "--flux-offload", choices=("model", "sequential", "none"), default="sequential"
    )
    parser.add_argument("--prepare-timeout-s", type=int, default=1800)
    parser.add_argument("--reference-timeout-s", type=int, default=7200)
    parser.add_argument("--generation-timeout-s", type=int, default=14400)
    parser.add_argument("--render-timeout-s", type=int, default=3600)
    parser.add_argument("--min-free-gib", type=float, default=100.0)
    parser.add_argument("--min-free-gpu-mib", type=int, default=20000)
    parser.add_argument(
        "--wait-for-gpu-s",
        type=int,
        default=0,
        help="Wait this long for each queue GPU to meet the free-memory guard.",
    )
    parser.add_argument("--gpu-poll-interval-s", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.data_root = args.data_root.resolve()
    try:
        args.data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc
    if args.workers < 1 or not args.gpus:
        raise ValueError("At least one worker and one GPU are required")
    if args.wait_for_gpu_s < 0 or args.gpu_poll_interval_s < 1:
        raise ValueError("GPU wait must be non-negative and poll interval positive")
    if any(seed not in (0, 1, 2, 3) for seed in args.seeds):
        raise ValueError("Seeds must be selected from the frozen set 0,1,2,3")

    specs = load_specs()
    if args.spec_ids:
        requested = set(args.spec_ids)
        unknown = requested - {spec["spec_id"] for spec in specs}
        if unknown:
            raise ValueError(f"Unknown spec ids: {sorted(unknown)}")
        specs = [spec for spec in specs if spec["spec_id"] in requested]
    elif args.pilot:
        first_by_category: dict[str, dict] = {}
        for spec in specs:
            first_by_category.setdefault(spec["category"], spec)
        specs = list(first_by_category.values())
        if args.seeds == [0, 1, 2, 3]:
            args.seeds = [0, 1]

    tasks = [(spec["spec_id"], seed) for spec in specs for seed in args.seeds]
    active_gpus = args.gpus[: min(args.workers, len(args.gpus))]
    queues: dict[int, list[tuple[str, int]]] = {gpu: [] for gpu in active_gpus}
    for index, task in enumerate(tasks):
        queues[active_gpus[index % len(active_gpus)]].append(task)
    print(
        f"SPATIALGEN_MATRIX_START phase={args.phase} tasks={len(tasks)} "
        f"workers={len(active_gpus)} gpus={active_gpus}",
        flush=True,
    )
    failures: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(run_queue, args, gpu, queues[gpu]) for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            failures.extend(future.result())
    print(
        f"SPATIALGEN_MATRIX_COMPLETE phase={args.phase} total={len(tasks)} "
        f"failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
