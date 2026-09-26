#!/usr/bin/env python3
"""Run the MetaUrban-only Table 3 pilot or formal matrix on assigned GPUs."""

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
import sys
import threading
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import BASELINES
from baselines.methods.metaurban.geometry.common import ENV_PYTHON
from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import utc_now


PILOT_INDICES = {0, 6, 12, 18, 24}
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def append_jsonl(path: Path, row: dict, lock: threading.Lock) -> None:
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )


def environment(gpu: int) -> dict[str, str]:
    value = os.environ.copy()
    for name in PROXY_VARIABLES:
        value.pop(name, None)
    value.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "METAURBANHOME": str(BASELINES / "sources/metaurban"),
            "PYTHONPATH": str(BASELINES / "sources/metaurban") + os.pathsep + str(REPO),
            "XDG_CACHE_HOME": str(BASELINES / "cache/xdg/metaurban"),
            "MPLCONFIGDIR": str(BASELINES / "cache/matplotlib/metaurban"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return value


def run_one(
    spec_id: str, seeds: list[int], gpu: int, args, log_path: Path, lock: threading.Lock
):
    command = [
        str(ENV_PYTHON),
        str(PACKAGE / "evaluate_spec.py"),
        "--spec-id",
        spec_id,
        "--seeds",
        *[str(seed) for seed in seeds],
        "--gpu",
        str(gpu),
        "--data-root",
        str(args.data_root),
    ]
    if args.force:
        command.append("--force")
    attempts = []
    for attempt in range(1, args.max_retries_infra + 2):
        free_gib = shutil.disk_usage(BASELINES).free / 1024**3
        if free_gib < args.min_free_gib:
            row = {
                "timestamp_utc": utc_now(),
                "spec_id": spec_id,
                "seeds": seeds,
                "gpu": gpu,
                "attempt": attempt,
                "exit_code": 75,
                "output": f"low disk: {free_gib:.1f} GiB",
            }
        else:
            completed = subprocess.run(
                command,
                cwd=REPO,
                env=environment(gpu),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            row = {
                "timestamp_utc": utc_now(),
                "spec_id": spec_id,
                "seeds": seeds,
                "gpu": gpu,
                "attempt": attempt,
                "exit_code": completed.returncode,
                "output": completed.stdout.strip(),
            }
        attempts.append(row)
        append_jsonl(log_path, row, lock)
        print(
            f"MATRIX_ITEM {'OK' if row['exit_code'] == 0 else 'FAILED'} spec={spec_id} "
            f"seeds={seeds} gpu={gpu} attempt={attempt}\n{row['output']}",
            flush=True,
        )
        if row["exit_code"] == 0 or row["exit_code"] == 75:
            break
    return attempts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--data-root", type=Path, default=TABLE3)
    parser.add_argument("--max-retries-infra", type=int, default=2)
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    specs = load_jsonl(PROTOCOL / "urban_specs.jsonl")
    if args.spec_ids:
        wanted = set(args.spec_ids)
        specs = [spec for spec in specs if spec["spec_id"] in wanted]
    elif args.phase == "pilot":
        specs = [spec for spec in specs if int(spec["spec_index"]) in PILOT_INDICES]
    seeds = (
        args.seeds
        if args.seeds is not None
        else ([0, 1] if args.phase == "pilot" else [0, 1, 2, 3])
    )
    active_gpus = list(dict.fromkeys(args.gpus))[: args.workers]
    if not active_gpus:
        parser.error("at least one GPU is required")
    PACKAGE.joinpath("results").mkdir(parents=True, exist_ok=True)
    log_path = PACKAGE / f"results/matrix_{args.phase}.jsonl"
    lock = threading.Lock()
    queues = {gpu: [] for gpu in active_gpus}
    for index, spec in enumerate(specs):
        queues[active_gpus[index % len(active_gpus)]].append(spec["spec_id"])
    print(
        f"MATRIX_START phase={args.phase} specs={len(specs)} seeds={seeds} gpus={active_gpus}",
        flush=True,
    )
    attempts = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(active_gpus)
    ) as executor:
        futures = [
            executor.submit(
                lambda selected_gpu=gpu: [
                    row
                    for spec_id in queues[selected_gpu]
                    for row in run_one(
                        spec_id, seeds, selected_gpu, args, log_path, lock
                    )
                ]
            )
            for gpu in active_gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            attempts.extend(future.result())
    final = {}
    for row in attempts:
        final[row["spec_id"]] = row
    failures = [row for row in final.values() if row["exit_code"] != 0]
    print(
        f"MATRIX_COMPLETE phase={args.phase} specs={len(specs)} failures={len(failures)}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
