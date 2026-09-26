#!/usr/bin/env python3
"""Run frozen HY-World 2.0 WorldScore jobs on a resumable multi-GPU queue."""

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
import importlib.util
import json
import os
import subprocess
import threading
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "hyworld2_runtime/data/table2"
METRIC_SCRIPT = BASELINES_ROOT / "evaluation/visual/eval_worldscore.py"
PYTHON = BASELINES_ROOT / "envs/worldscore/bin/python"
ABI_ROOT = BASELINES_ROOT / "work/metaurban/worldscore_abi"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}


def load_metric_module():
    spec = importlib.util.spec_from_file_location(
        "hyworld2_worldscore_metric", METRIC_SCRIPT
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {METRIC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WS = load_metric_module()


def load_specs(domain: str) -> list[dict]:
    return [
        json.loads(line)
        for line in SPEC_FILES[domain].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def output_path(data_root: Path, domain: str, spec_id: str, seed: int) -> Path:
    return (
        data_root
        / domain
        / "hyworld2"
        / spec_id
        / f"seed_{seed}"
        / "metrics/consistency_3d.json"
    )


def valid_existing(path: Path, domain: str, spec_id: str, seed: int) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        record.get("method") == "hyworld2"
        and record.get("domain") == domain
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("metric") == "worldscore_static_3d_consistency"
        and record.get("checkpoint_sha256") == WS.CHECKPOINT_SHA256
        and isinstance(record.get("success"), bool)
        and (
            record.get("success") is True
            or record.get("failure_reason") == "missing_or_invalid_render"
        )
    )


def worker_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/xdg_metrics"),
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(
                part for part in (str(ABI_ROOT), existing_pythonpath) if part
            ),
        }
    )
    return environment


def run_one(task: tuple[str, str, int], gpu: int, data_root: Path) -> tuple[bool, str]:
    domain, spec_id, seed = task
    destination = output_path(data_root, domain, spec_id, seed)
    command = [
        str(PYTHON),
        str(METRIC_SCRIPT),
        "--worker",
        "--data-root",
        str(data_root),
        "--method",
        "hyworld2",
        "--domain",
        domain,
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--gpu",
        str(gpu),
    ]
    completed = subprocess.run(
        command,
        cwd=BASELINES_ROOT.parent,
        env=worker_environment(gpu),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode == 0 and valid_existing(destination, domain, spec_id, seed):
        record = json.loads(destination.read_text(encoding="utf-8"))
        return bool(record["success"]), ""
    return False, completed.stdout[-4000:]


def write_failure(data_root: Path, domain: str, spec_id: str, seed: int) -> None:
    run_dir = data_root / domain / "hyworld2" / spec_id / f"seed_{seed}"
    destination = output_path(data_root, domain, spec_id, seed)
    record = WS.failure_record(
        spec_id,
        seed,
        "missing_or_invalid_render",
        method="hyworld2",
        domain=domain,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_domain_outputs(domain: str, data_root: Path) -> None:
    records = []
    for spec in load_specs(domain):
        for seed in range(4):
            path = output_path(data_root, domain, spec["spec_id"], seed)
            if not valid_existing(path, domain, spec["spec_id"], seed):
                raise RuntimeError(f"Missing final WorldScore result: {path}")
            records.append(json.loads(path.read_text(encoding="utf-8")))
    destination = (
        BASELINES_ROOT / "results/hyworld2" / domain / "consistency_per_scene.jsonl"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domains", choices=tuple(SPEC_FILES), nargs="+", default=list(SPEC_FILES)
    )
    parser.add_argument("--gpus", type=int, nargs="+", required=True)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args()
    if not args.gpus or len(args.gpus) != len(set(args.gpus)):
        raise ValueError("Provide unique GPU ids")
    data_root = args.data_root.resolve()
    data_root.relative_to(BASELINES_ROOT.resolve())

    tasks: list[tuple[str, str, int]] = []
    skipped = 0
    render_failures = 0
    for domain in args.domains:
        for spec in load_specs(domain):
            spec_id = spec["spec_id"]
            for seed in range(4):
                run_dir = data_root / domain / "hyworld2" / spec_id / f"seed_{seed}"
                destination = output_path(data_root, domain, spec_id, seed)
                if valid_existing(destination, domain, spec_id, seed):
                    skipped += 1
                elif not (run_dir / "SUCCESS").is_file():
                    write_failure(data_root, domain, spec_id, seed)
                    render_failures += 1
                else:
                    tasks.append((domain, spec_id, seed))

    print(
        f"HYWORLD2_WORLDSCORE_QUEUE pending={len(tasks)} skipped={skipped} "
        f"render_failures={render_failures} gpus={args.gpus}",
        flush=True,
    )
    lock = threading.Lock()
    task_lock = threading.Lock()
    task_iterator = iter(tasks)
    state = {"completed": skipped + render_failures, "metric_ok": 0, "metric_failed": 0}

    def gpu_loop(gpu: int) -> None:
        while True:
            with task_lock:
                try:
                    domain, spec_id, seed = next(task_iterator)
                except StopIteration:
                    return
            success, detail = run_one((domain, spec_id, seed), gpu, data_root)
            with lock:
                state["completed"] += 1
                state["metric_ok" if success else "metric_failed"] += 1
                print(
                    f"HYWORLD2_WORLDSCORE_PROGRESS completed={state['completed']}/200 "
                    f"metric_ok={state['metric_ok']} metric_failed={state['metric_failed']} "
                    f"gpu={gpu} run={domain}/{spec_id}/seed_{seed}",
                    flush=True,
                )
            if detail:
                raise RuntimeError(
                    f"WorldScore worker infrastructure failure for {domain}/{spec_id}/seed_{seed}:\n{detail}"
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = [executor.submit(gpu_loop, gpu) for gpu in args.gpus]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    for domain in args.domains:
        write_domain_outputs(domain, data_root)
    print(
        f"HYWORLD2_WORLDSCORE_COMPLETE completed={state['completed']}/200 "
        f"metric_ok={state['metric_ok']} metric_failed={state['metric_failed']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
