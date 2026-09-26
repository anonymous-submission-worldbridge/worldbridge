#!/usr/bin/env python3
"""Run ZiYang-xie/WorldGen Table-2 tasks on persistent GPU 0/1 workers."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
PYTHON = BASELINES_ROOT / "environments/worldgen/bin/python"
ADAPTER = BASELINES_ROOT / "methods/worldgen/adapter.py"
RENDERER = BASELINES_ROOT / "methods/worldgen/tools/render_worldgen_generation.py"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
ALLOWED_GPUS = {0, 1}


def load_specs(domain: str) -> list[dict[str, Any]]:
    with SPEC_FILES[domain].open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select_specs(
    domain: str, pilot: bool, requested: set[str] | None
) -> list[dict[str, Any]]:
    specs = load_specs(domain)
    if requested is not None:
        selected = [spec for spec in specs if spec["spec_id"] in requested]
        unknown = requested - {spec["spec_id"] for spec in specs}
        if unknown:
            raise ValueError(f"Unknown {domain} spec ids: {sorted(unknown)}")
        return selected
    if not pilot:
        return specs
    first_by_category: dict[str, dict[str, Any]] = {}
    for spec in specs:
        first_by_category.setdefault(spec["category"], spec)
    return list(first_by_category.values())


def task_run_dir(data_root: Path, task: dict[str, Any]) -> Path:
    return (
        data_root
        / task["domain"]
        / "worldgen"
        / task["spec_id"]
        / f"seed_{task['seed']}"
    )


def gpu_free_mib(gpu: int) -> int | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu}",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
        return int(completed.stdout.strip()) if completed.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def worker_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    cuda_home = "/usr/local/cuda-12.8"
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HOME": str(BASELINES_ROOT / "checkpoints/WorldGen/huggingface"),
            "HF_HUB_CACHE": str(
                BASELINES_ROOT / "checkpoints/WorldGen/huggingface/hub"
            ),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TORCH_HOME": str(BASELINES_ROOT / "checkpoints/WorldGen/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/worldgen"),
            "TORCH_EXTENSIONS_DIR": str(
                BASELINES_ROOT / "cache/worldgen/torch_extensions"
            ),
            "CUDA_HOME": cuda_home,
            "PATH": f"{PYTHON.parent}:{cuda_home}/bin:{environment.get('PATH', '')}",
            "TORCH_CUDA_ARCH_LIST": "8.9",
            "MAX_JOBS": "8",
            "TMPDIR": str(BASELINES_ROOT / "tmp/worldgen"),
            "PYTHONUNBUFFERED": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return environment


def write_task_lists(
    phase: str, tasks: list[dict[str, Any]], gpus: list[int]
) -> dict[int, Path]:
    task_root = BASELINES_ROOT / "work/worldgen/tasklists"
    task_root.mkdir(parents=True, exist_ok=True)
    queues = {gpu: [] for gpu in gpus}
    for index, task in enumerate(tasks):
        queues[gpus[index % len(gpus)]].append(task)
    paths = {}
    for gpu, queue in queues.items():
        path = task_root / f"{phase}_gpu{gpu}.json"
        path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        paths[gpu] = path
    return paths


def run_model_worker(
    phase: str,
    gpu: int,
    task_list: Path,
    data_root: Path,
    force: bool,
) -> dict[str, Any]:
    free_mib = gpu_free_mib(gpu)
    if free_mib is not None and free_mib < 40000:
        return {
            "gpu": gpu,
            "phase": phase,
            "exit_code": 75,
            "output": f"GPU {gpu} has only {free_mib} MiB free; require 40000 MiB",
        }
    command = [
        str(PYTHON),
        str(ADAPTER),
        "worker",
        "--phase",
        phase,
        "--task-list",
        str(task_list),
        "--data-root",
        str(data_root),
    ]
    if force:
        command.append("--force")
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=worker_environment(gpu),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "gpu": gpu,
        "phase": phase,
        "exit_code": completed.returncode,
        "output": completed.stdout,
    }


def run_parallel_model_phase(
    phase: str,
    tasks: list[dict[str, Any]],
    gpus: list[int],
    data_root: Path,
    force: bool,
) -> int:
    paths = write_task_lists(phase, tasks, gpus)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as executor:
        futures = [
            executor.submit(run_model_worker, phase, gpu, paths[gpu], data_root, force)
            for gpu in gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                result["output"],
                end="" if result["output"].endswith("\n") else "\n",
                flush=True,
            )
    failures = sum(result["exit_code"] != 0 for result in results)
    print(
        f"WORLDGEN_PHASE_COMPLETE phase={phase} workers={len(results)} failures={failures}"
    )
    return failures


def run_render_queue(
    gpu: int,
    tasks: list[dict[str, Any]],
    data_root: Path,
    force: bool,
    min_free_gib: float,
) -> list[dict[str, Any]]:
    failures = []
    environment = worker_environment(gpu)
    for task in tasks:
        free_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
        if free_gib < min_free_gib:
            failures.append({**task, "reason": "low_disk", "free_gib": free_gib})
            break
        run_dir = task_run_dir(data_root, task)
        command = [str(PYTHON), str(RENDERER), "--run-dir", str(run_dir)]
        if force:
            command.append("--force")
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        print(
            completed.stdout,
            end="" if completed.stdout.endswith("\n") else "\n",
            flush=True,
        )
        if completed.returncode != 0:
            failures.append(
                {**task, "reason": "render_failed", "detail": completed.stdout[-4000:]}
            )
    return failures


def run_render_phase(
    tasks: list[dict[str, Any]],
    gpus: list[int],
    data_root: Path,
    force: bool,
    min_free_gib: float,
) -> int:
    queues = {gpu: [] for gpu in gpus}
    for index, task in enumerate(tasks):
        queues[gpus[index % len(gpus)]].append(task)
    failures: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as executor:
        futures = [
            executor.submit(
                run_render_queue, gpu, queues[gpu], data_root, force, min_free_gib
            )
            for gpu in gpus
        ]
        for future in concurrent.futures.as_completed(futures):
            failures.extend(future.result())
    if failures:
        failure_path = BASELINES_ROOT / "results/worldgen_render_failures.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(
        f"WORLDGEN_PHASE_COMPLETE phase=render tasks={len(tasks)} failures={len(failures)}"
    )
    return len(failures)


def run_compile_phase(tasks: list[dict[str, Any]], data_root: Path) -> int:
    path = write_task_lists("compile", tasks, [0])[0]
    command = [
        str(PYTHON),
        str(ADAPTER),
        "worker",
        "--phase",
        "compile",
        "--task-list",
        str(path),
        "--data-root",
        str(data_root),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    return int(completed.returncode != 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("compile", "panorama", "reconstruct", "render", "all"),
        required=True,
    )
    parser.add_argument(
        "--domains", choices=tuple(SPEC_FILES), nargs="+", default=list(SPEC_FILES)
    )
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--spec-ids", nargs="+", default=None)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=100.0)
    args = parser.parse_args()

    if args.workers < 1 or args.workers > len(args.gpus):
        raise ValueError("workers must be between 1 and the number of GPUs")
    if not set(args.gpus).issubset(ALLOWED_GPUS):
        raise ValueError(
            f"This experiment is restricted to physical GPUs {sorted(ALLOWED_GPUS)}"
        )
    if any(seed not in (0, 1, 2, 3) for seed in args.seeds):
        raise ValueError("Seeds must be selected from 0,1,2,3")
    if args.pilot and args.seeds == [0, 1, 2, 3]:
        args.seeds = [0, 1]
    data_root = args.data_root.resolve()
    try:
        data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc

    requested = set(args.spec_ids) if args.spec_ids else None
    tasks = [
        {"domain": domain, "spec_id": spec["spec_id"], "seed": seed}
        for domain in args.domains
        for spec in select_specs(domain, args.pilot, requested)
        for seed in args.seeds
    ]
    gpus = args.gpus[: args.workers]
    (BASELINES_ROOT / "tmp/worldgen").mkdir(parents=True, exist_ok=True)
    print(
        f"WORLDGEN_MATRIX_START phase={args.phase} tasks={len(tasks)} "
        f"domains={args.domains} gpus={gpus} data_root={data_root}",
        flush=True,
    )

    if shutil.disk_usage(BASELINES_ROOT).free / (1024**3) < args.min_free_gib:
        print("WORLDGEN_MATRIX_ABORT low disk", flush=True)
        return 75
    phases = (
        [args.phase]
        if args.phase != "all"
        else ["compile", "panorama", "reconstruct", "render"]
    )
    for phase in phases:
        if phase == "compile":
            failures = run_compile_phase(tasks, data_root)
        elif phase in {"panorama", "reconstruct"}:
            failures = run_parallel_model_phase(
                phase, tasks, gpus, data_root, args.force
            )
        else:
            failures = run_render_phase(
                tasks, gpus, data_root, args.force, args.min_free_gib
            )
        if failures:
            print(
                f"WORLDGEN_MATRIX_FAILED phase={phase} failures={failures}", flush=True
            )
            return 1
    print(f"WORLDGEN_MATRIX_COMPLETE tasks={len(tasks)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
