#!/usr/bin/env python3
"""Resume Extra-High WorldScore with one frozen isolated worker per GPU.

This is an execution-only scheduler.  Every scene is still evaluated by the
locked WorldScore entry point in a fresh process with its frozen arguments.
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
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
WORKSPACE = ROOT.parent
LOCK_PATH = ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.lock.json"
PROTOCOL_PATH = ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.json"
SPEC_PATH = ROOT / "protocol/generation/urban_specs.jsonl"
FROZEN = ROOT / "evaluation/visual/eval_worldscore_gpt_high_frozen.py"
PYTHON = ROOT / "envs/worldscore/bin/python"
OUTPUT = ROOT / "results/gpt6_astra_xhigh/formal/urban/consistency_per_scene.jsonl"
REPORT = ROOT / "results/gpt6_astra_xhigh/worldscore_parallel_execution_20260914.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    changed = [
        relative
        for relative, expected in lock["files_sha256"].items()
        if digest(ROOT / relative) != expected
    ]
    if changed:
        raise RuntimeError(f"Frozen Extra-High sources changed: {changed}")
    return lock


def specs() -> list[dict]:
    return [json.loads(line) for line in SPEC_PATH.read_text().splitlines() if line]


def run_dir(data_root: Path, spec_id: str, seed: int) -> Path:
    return data_root / "urban/gpt6_astra_xhigh" / spec_id / f"seed_{seed}"


def metric_path(data_root: Path, spec_id: str, seed: int) -> Path:
    return run_dir(data_root, spec_id, seed) / "metrics/consistency_3d.json"


def valid_record(record: dict, spec_id: str, seed: int) -> bool:
    detail = str(record.get("failure_detail", "")).lower()
    infrastructure_signals = (
        "out of memory",
        "cuda error",
        "cuda device",
        "torch.cuda.is_available() is false",
        "device-side",
        "cublas",
        "cudnn",
        "driver shutting down",
    )
    return (
        record.get("method") == "gpt6_astra_xhigh"
        and record.get("domain") == "urban"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("metric") == "worldscore_static_3d_consistency"
        and record.get("frames_expected") == 50
        and record.get("worldscore_commit")
        == "096c75fc4ada9c7d92e03140c3c1f0c8f383b61f"
        and record.get("droid_slam_commit")
        == "8016d2b9b72b101a3e9ac804ebf20b4c654dc291"
        and record.get("checkpoint_sha256")
        == "46476ef64cde45a97504910d6f3de2eef7b398ec1c6e4e668815c29076024526"
        and isinstance(record.get("success"), bool)
        and isinstance(record.get("consistency_3d"), (int, float))
        and not any(signal in detail for signal in infrastructure_signals)
    )


def load_valid(path: Path, spec_id: str, seed: int) -> dict | None:
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if valid_record(record, spec_id, seed) else None


def gpu_state(gpu: int) -> tuple[int, int]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "-i",
            str(gpu),
            "--query-gpu=memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    free_text, utilization_text = completed.stdout.strip().split(",", 1)
    return int(free_text.strip()), int(utilization_text.strip())


def wait_for_gpu(gpu: int, min_free_mib: int, max_utilization: int) -> None:
    while True:
        free, utilization = gpu_state(gpu)
        if free >= min_free_mib and utilization <= max_utilization:
            return
        print(
            f"XHIGH_WORLDSCORE_WAIT gpu={gpu} free_mib={free} "
            f"required_mib={min_free_mib} utilization={utilization} "
            f"max_utilization={max_utilization}",
            flush=True,
        )
        time.sleep(30)


def evaluate(
    data_root: Path,
    spec_id: str,
    seed: int,
    gpu: int,
    min_free_mib: int,
    max_utilization: int,
) -> dict:
    per_run = metric_path(data_root, spec_id, seed)
    existing = load_valid(per_run, spec_id, seed)
    if existing is not None:
        return {"record": existing, "gpu": gpu, "resumed": True, "stdout": ""}
    partial = OUTPUT.parent / "worldscore_parts" / f"{spec_id}__seed_{seed}.jsonl"
    partial.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(PYTHON),
        str(FROZEN),
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_PATH),
        "--method",
        "gpt6_astra_xhigh",
        "--domain",
        "urban",
        "--gpu",
        str(gpu),
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
        "--output",
        str(partial),
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    for infrastructure_attempt in range(3):
        wait_for_gpu(gpu, min_free_mib, max_utilization)
        completed = subprocess.run(
            command,
            cwd=WORKSPACE,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        record = load_valid(per_run, spec_id, seed)
        if not completed.returncode and record is not None:
            return {
                "record": record,
                "gpu": gpu,
                "resumed": False,
                "stdout": completed.stdout[-1000:],
                "infrastructure_attempt": infrastructure_attempt + 1,
            }
        print(
            f"XHIGH_WORLDSCORE_INFRA_RETRY {spec_id} seed={seed} gpu={gpu} "
            f"attempt={infrastructure_attempt + 1} rc={completed.returncode}",
            flush=True,
        )
        time.sleep(5)
    raise RuntimeError(
        f"Frozen WorldScore failed for {spec_id} seed={seed} gpu={gpu}: "
        f"rc={completed.returncode}\n{completed.stdout[-4000:]}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/table2")
    parser.add_argument("--gpus", type=int, nargs="+", default=[4, 5])
    parser.add_argument("--min-free-mib", type=int, default=30000)
    parser.add_argument("--max-utilization", type=int, default=10)
    args = parser.parse_args()
    lock = verify_lock()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    data_root = args.data_root.resolve()
    expected_root = (ROOT / "data/table2").resolve()
    if data_root != expected_root:
        raise RuntimeError(
            f"Expected formal data root {expected_root}, got {data_root}"
        )
    if (
        protocol["method"] != "gpt6_astra_xhigh"
        or protocol["reasoning_effort"] != "xhigh"
    ):
        raise RuntimeError("Unexpected formal protocol")
    if not args.gpus or len(set(args.gpus)) != len(args.gpus):
        raise ValueError("GPU list must be nonempty and unique")

    ordered = [(spec["spec_id"], seed) for spec in specs() for seed in range(4)]
    tasks: queue.Queue[tuple[str, int]] = queue.Queue()
    for task in ordered:
        tasks.put(task)
    results: dict[tuple[str, int], dict] = {}
    failures: list[str] = []
    mutex = threading.Lock()
    started = datetime.now(timezone.utc)

    def worker(gpu: int) -> None:
        while True:
            try:
                spec_id, seed = tasks.get_nowait()
            except queue.Empty:
                return
            try:
                payload = evaluate(
                    data_root,
                    spec_id,
                    seed,
                    gpu,
                    args.min_free_mib,
                    args.max_utilization,
                )
                with mutex:
                    results[(spec_id, seed)] = payload
                    done = len(results)
                    record = payload["record"]
                    print(
                        f"XHIGH_WORLDSCORE {done}/100 gpu={gpu} {spec_id} seed={seed} "
                        f"resumed={payload['resumed']} success={record['success']} "
                        f"score={record['consistency_3d']:.6f}",
                        flush=True,
                    )
            except Exception as exc:
                with mutex:
                    failures.append(f"{spec_id} seed={seed} gpu={gpu}: {exc!r}")
            finally:
                tasks.task_done()

    threads = [
        threading.Thread(target=worker, args=(gpu,), daemon=False) for gpu in args.gpus
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures or len(results) != 100:
        raise RuntimeError(
            json.dumps({"failures": failures, "records": len(results)}, indent=2)
        )

    records = [results[key]["record"] for key in ordered]
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    report = {
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "execution_only_worldscore_parallelism",
        "scientific_change": False,
        "method": "gpt6_astra_xhigh",
        "reasoning_effort": "xhigh",
        "domain": "urban",
        "gpus": args.gpus,
        "min_free_mib": args.min_free_mib,
        "max_utilization": args.max_utilization,
        "records": len(records),
        "resumed_records": sum(payload["resumed"] for payload in results.values()),
        "new_records": sum(not payload["resumed"] for payload in results.values()),
        "frozen_entrypoint": str(FROZEN.relative_to(ROOT)),
        "frozen_entrypoint_sha256": digest(FROZEN),
        "formal_lock_sha256": digest(LOCK_PATH),
        "formal_lock_files_verified": len(lock["files_sha256"]),
        "output": str(OUTPUT.relative_to(ROOT)),
        "output_sha256": digest(OUTPUT),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
