#!/usr/bin/env python3
"""Run the frozen SceneWeaver Table-2 indoor matrix.

Each selected physical GPU owns one serial queue.  This keeps SceneWeaver's
Blender/Infinigen subprocesses from oversubscribing a GPU while still allowing
independent specification/seed pairs to run concurrently.
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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
ADAPTER = BASELINES_ROOT / "methods/sceneweaver/adapter.py"
PLANNER_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
DEFAULT_JOURNAL = BASELINES_ROOT / "results/sceneweaver_matrix.jsonl"
FROZEN_SEEDS = (0, 1, 2, 3)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_below_baselines(path: Path) -> None:
    try:
        path.resolve().relative_to(BASELINES_ROOT.resolve())
    except ValueError as error:
        raise ValueError(
            f"SceneWeaver output must stay below {BASELINES_ROOT}: {path}"
        ) from error


def load_specs() -> list[dict]:
    with SPEC_FILE.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select_specs(
    specs: list[dict], spec_ids: list[str] | None, pilot: bool
) -> list[dict]:
    if spec_ids:
        requested = set(spec_ids)
        unknown = requested - {spec["spec_id"] for spec in specs}
        if unknown:
            raise ValueError(f"Unknown spec ids: {sorted(unknown)}")
        return [spec for spec in specs if spec["spec_id"] in requested]
    if not pilot:
        return specs
    first_by_category: dict[str, dict] = {}
    for spec in specs:
        first_by_category.setdefault(spec["category"], spec)
    return list(first_by_category.values())


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


def append_journal(path: Path, record: dict, lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def run_one(args: argparse.Namespace, spec_id: str, seed: int, gpu: int) -> dict:
    command = [
        str(PLANNER_PYTHON),
        str(ADAPTER),
        "--spec-file",
        str(SPEC_FILE),
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
        "--generation-timeout-s",
        str(args.generation_timeout_s),
        "--render-timeout-s",
        str(args.render_timeout_s),
    ]
    if args.force:
        command.append("--force")
    started_at = utc_now()
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
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "phase": args.phase,
        "spec_id": spec_id,
        "seed": seed,
        "gpu": gpu,
        "exit_code": completed.returncode,
        "wall_time_s": time.monotonic() - started,
        "output": completed.stdout.strip(),
    }


def run_queue(
    args: argparse.Namespace,
    gpu: int,
    tasks: list[tuple[str, int]],
    journal_lock: threading.Lock,
) -> list[dict]:
    failures: list[dict] = []
    for task_index, (spec_id, seed) in enumerate(tasks):
        free_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
        if free_gib < args.min_free_gib:
            reason = (
                f"not_started_low_disk free_gib={free_gib:.2f} "
                f"minimum={args.min_free_gib:.2f}"
            )
        else:
            free_mib = gpu_free_mib(gpu)
            reason = (
                f"not_started_low_gpu_memory free_mib={free_mib} "
                f"minimum={args.min_free_gpu_mib}"
                if free_mib is not None and free_mib < args.min_free_gpu_mib
                else ""
            )
        if reason:
            print(
                f"SCENEWEAVER_QUEUE_ABORT gpu={gpu} task_index={task_index} {reason}",
                flush=True,
            )
            for pending_spec, pending_seed in tasks[task_index:]:
                record = {
                    "started_at_utc": utc_now(),
                    "ended_at_utc": utc_now(),
                    "phase": args.phase,
                    "spec_id": pending_spec,
                    "seed": pending_seed,
                    "gpu": gpu,
                    "exit_code": 75,
                    "wall_time_s": 0.0,
                    "output": reason,
                }
                append_journal(args.journal, record, journal_lock)
                failures.append(record)
            break

        result = run_one(args, spec_id, seed, gpu)
        append_journal(args.journal, result, journal_lock)
        status = "OK" if result["exit_code"] == 0 else "FAILED"
        print(
            f"SCENEWEAVER_ITEM {status} phase={args.phase} spec={spec_id} "
            f"seed={seed} gpu={gpu} wall={result['wall_time_s']:.1f}s "
            f"{result['output']}",
            flush=True,
        )
        if result["exit_code"] != 0:
            failures.append(result)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("generate", "render", "all"), default="all")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(FROZEN_SEEDS))
    parser.add_argument("--spec-ids", nargs="+", default=None)
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Use the first frozen specification from each of the five room categories.",
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--generation-timeout-s", type=int, default=21600)
    parser.add_argument("--render-timeout-s", type=int, default=10800)
    parser.add_argument("--min-free-gib", type=float, default=100.0)
    parser.add_argument("--min-free-gpu-mib", type=int, default=6000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.data_root = args.data_root.expanduser().resolve()
    args.journal = args.journal.expanduser().resolve()
    assert_below_baselines(args.data_root)
    assert_below_baselines(args.journal)
    if args.workers < 1 or not args.gpus:
        raise ValueError("At least one worker and one GPU are required")
    if len(set(args.gpus)) != len(args.gpus):
        raise ValueError("--gpus must not contain duplicates")
    if any(seed not in FROZEN_SEEDS for seed in args.seeds):
        raise ValueError(f"Seeds must be selected from the frozen set {FROZEN_SEEDS}")
    if args.min_free_gib < 0 or args.min_free_gpu_mib < 0:
        raise ValueError("Resource protection thresholds must be non-negative")

    specs = select_specs(load_specs(), args.spec_ids, args.pilot)
    if args.pilot and args.seeds == list(FROZEN_SEEDS):
        args.seeds = [0, 1]
    tasks = [(spec["spec_id"], seed) for spec in specs for seed in args.seeds]
    active_gpus = args.gpus[: min(args.workers, len(args.gpus))]
    queues: dict[int, list[tuple[str, int]]] = {gpu: [] for gpu in active_gpus}
    for index, task in enumerate(tasks):
        queues[active_gpus[index % len(active_gpus)]].append(task)

    print(
        f"SCENEWEAVER_MATRIX_START phase={args.phase} tasks={len(tasks)} "
        f"workers={len(active_gpus)} gpus={active_gpus} data_root={args.data_root}",
        flush=True,
    )
    journal_lock = threading.Lock()
    failures: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(run_queue, args, gpu, queues[gpu], journal_lock)
            for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            failures.extend(future.result())
    print(
        f"SCENEWEAVER_MATRIX_COMPLETE phase={args.phase} total={len(tasks)} "
        f"failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
