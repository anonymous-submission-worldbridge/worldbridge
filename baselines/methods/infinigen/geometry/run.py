#!/usr/bin/env python3
"""Execute the Infinigen-only Table 3 pilot or formal matrix."""

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
import threading
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPECS = BASELINES / "protocol/geometry/indoor_specs.jsonl"
ADAPTER = BASELINES / "methods/infinigen/geometry/adapters/infinigen.py"
PYTHON = BASELINES / "envs/hyworld2/bin/python"
PILOT_INDICES = {0, 5, 10, 15, 20}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, value: dict, lock: threading.Lock):
    line = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def execute(task, gpu, args, log_path, log_lock):
    spec_id, seed = task
    command = [
        str(PYTHON),
        str(ADAPTER),
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--gpu",
        str(gpu),
        "--data-root",
        str(args.data_root),
    ]
    if args.force:
        command.append("--force")
    attempts = []
    for attempt in range(1, args.max_retries_infra + 2):
        completed = subprocess.run(
            command,
            cwd=BASELINES.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        row = {
            "timestamp_utc": utc_now(),
            "phase": args.phase,
            "spec_id": spec_id,
            "seed": seed,
            "gpu": gpu,
            "attempt": attempt,
            "exit_code": completed.returncode,
            "output": completed.stdout.strip(),
        }
        attempts.append(row)
        append_jsonl(log_path, row, log_lock)
        print(
            f"MATRIX_ITEM {'OK' if completed.returncode == 0 else 'FAILED'} "
            f"spec={spec_id} seed={seed} gpu={gpu} attempt={attempt} "
            f"{completed.stdout.strip()}",
            flush=True,
        )
        if completed.returncode == 0:
            break
    return attempts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--gpus", type=int, nargs="+", default=[2, 3, 4])
    parser.add_argument("--data-root", type=Path, default=BASELINES / "data/table3")
    parser.add_argument("--max-retries-infra", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--seeds", type=int, nargs="+")
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in SPECS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.spec_ids:
        wanted = set(args.spec_ids)
        specs = [spec for spec in specs if spec["spec_id"] in wanted]
    elif args.phase == "pilot":
        specs = [spec for spec in specs if spec["spec_index"] in PILOT_INDICES]
    seeds = (
        args.seeds
        if args.seeds is not None
        else ([0, 1] if args.phase == "pilot" else [0, 1, 2, 3])
    )
    tasks = [(spec["spec_id"], seed) for spec in specs for seed in seeds]
    active_gpus = args.gpus[: min(args.workers, len(args.gpus))]
    if not active_gpus:
        parser.error(
            "At least one assigned GPU/index is required for scheduling provenance"
        )
    results_dir = BASELINES / "evaluation/geometry/results"
    results_dir.mkdir(parents=True, exist_ok=True)
    log_path = results_dir / f"matrix_{args.phase}.jsonl"
    log_lock = threading.Lock()
    queues = {gpu: [] for gpu in active_gpus}
    for index, task in enumerate(tasks):
        queues[active_gpus[index % len(active_gpus)]].append(task)
    print(
        f"MATRIX_START phase={args.phase} tasks={len(tasks)} workers={len(active_gpus)} gpus={active_gpus}",
        flush=True,
    )
    all_attempts = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(
                lambda assigned_gpu=gpu: [
                    row
                    for task in queues[assigned_gpu]
                    for row in execute(task, assigned_gpu, args, log_path, log_lock)
                ]
            )
            for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            all_attempts.extend(future.result())
    final = {}
    for row in all_attempts:
        final[(row["spec_id"], row["seed"])] = row
    failures = [row for row in final.values() if row["exit_code"] != 0]
    print(
        f"MATRIX_COMPLETE phase={args.phase} tasks={len(tasks)} failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
