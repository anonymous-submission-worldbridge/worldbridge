#!/usr/bin/env python3
"""Wait for a safe shared-GPU window, then incrementally evaluate Q-Align."""

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
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
METRICS_LOCK = BASELINES / "protocol/generation/metrics.lock.json"
FROZEN_EVALUATOR = BASELINES / "evaluation/visual/eval_iqa.py"
DEFAULT_OUTPUT = BASELINES / "results/qalign_per_scene.checkpoint.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_specs(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def gpu_status(gpu: int) -> tuple[int, int]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
            "-i",
            str(gpu),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"nvidia-smi failed for GPU {gpu}: {completed.stdout.strip()}"
        )
    values = completed.stdout.strip().splitlines()[0].split(",")
    return int(values[0].strip()), int(values[1].strip())


def memory_available_mib() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise RuntimeError("MemAvailable is missing from /proc/meminfo")


def wait_for_resources(
    gpus: list[int],
    min_free_mib: int,
    max_utilization_percent: int,
    min_mem_available_mib: int,
    poll_seconds: int,
) -> int:
    while True:
        status = {gpu: gpu_status(gpu) for gpu in gpus}
        free = {gpu: values[0] for gpu, values in status.items()}
        utilization = {gpu: values[1] for gpu, values in status.items()}
        available = memory_available_mib()
        eligible = [
            gpu
            for gpu in gpus
            if free[gpu] >= min_free_mib and utilization[gpu] <= max_utilization_percent
        ]
        if eligible and available >= min_mem_available_mib:
            selected = max(eligible, key=free.get)
            print(
                f"QALIGN_RESOURCE_READY gpu={selected} free_mib={free[selected]} "
                f"mem_available_mib={available}",
                flush=True,
            )
            return selected
        detail = " ".join(
            f"gpu{gpu}_free_mib={free[gpu]}_util={utilization[gpu]}" for gpu in gpus
        )
        print(
            f"QALIGN_WAIT_RESOURCE {detail} mem_available_mib={available} "
            f"required_gpu_mib={min_free_mib} max_util={max_utilization_percent} "
            f"required_mem_mib={min_mem_available_mib}",
            flush=True,
        )
        time.sleep(poll_seconds)


def provenance(pyiqa: Any, torch: Any) -> dict[str, Any]:
    lock = json.loads(METRICS_LOCK.read_text(encoding="utf-8"))["qalign"]
    return {
        "implementation": lock["implementation"],
        "model_id": lock["model_id"],
        "revision": lock["revision"],
        "weight_sha256": [row["sha256"] for row in lock["weights"]],
        "frozen_combined_evaluator_sha256": sha256(FROZEN_EVALUATOR),
        "metrics_lock_sha256": sha256(METRICS_LOCK),
        "pyiqa_version": getattr(pyiqa, "__version__", "unknown"),
        "torch_version": torch.__version__,
    }


def scalar(value: Any, torch: Any) -> float:
    if isinstance(value, (list, tuple)):
        value = value[0]
    if torch.is_tensor(value):
        value = value.detach().float().mean().cpu().item()
    return float(value)


def valid_existing(
    path: Path,
    method: str,
    spec_id: str,
    seed: int,
    expected_provenance: dict[str, Any],
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    score = record.get("qalign")
    valid = (
        record.get("method") == method
        and record.get("domain") == "indoor"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("success") is True
        and isinstance(score, (int, float))
        and math.isfinite(float(score))
        and record.get("provenance") == expected_provenance
        and len(record.get("views", [])) == 8
    )
    return record if valid else None


def failure_record(method: str, spec_id: str, seed: int, reason: str) -> dict[str, Any]:
    return {
        "method": method,
        "domain": "indoor",
        "spec_id": spec_id,
        "logical_seed": seed,
        "success": False,
        "qalign": 1.0,
        "failure_policy": "itt_lower_bound_checkpoint",
        "failure_reason": reason,
        "views": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gpus", type=int, nargs="+", default=[2, 5])
    parser.add_argument("--min-free-mib", type=int, default=16500)
    parser.add_argument("--max-utilization-percent", type=int, default=10)
    parser.add_argument("--min-mem-available-mib", type=int, default=24576)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()
    if not args.gpus:
        parser.error("at least one physical GPU is required")
    if not 0 <= args.max_utilization_percent <= 100:
        parser.error("--max-utilization-percent must be between 0 and 100")
    if args.poll_seconds < 10 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 10 and 60")

    selected_gpu = wait_for_resources(
        args.gpus,
        args.min_free_mib,
        args.max_utilization_percent,
        args.min_mem_available_mib,
        args.poll_seconds,
    )
    os.environ["CUDA_VISIBLE_DEVICES"] = str(selected_gpu)
    os.environ.setdefault("TORCH_HOME", str(BASELINES / "cache/torch"))
    os.environ.setdefault("HF_HOME", str(BASELINES / "cache/huggingface"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES / "cache/xdg_metrics"))

    import pyiqa
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            f"CUDA is unavailable after selecting physical GPU {selected_gpu}"
        )
    prov = provenance(pyiqa, torch)
    print(f"QALIGN_LOAD_START physical_gpu={selected_gpu}", flush=True)
    metric = pyiqa.create_metric("qalign", device="cuda")
    print(f"QALIGN_LOAD_COMPLETE physical_gpu={selected_gpu}", flush=True)

    records: list[dict[str, Any]] = []
    measured = 0
    skipped = 0
    for spec in load_specs(args.spec_file):
        spec_id = spec["spec_id"]
        for seed in range(4):
            run_dir = args.data_root / spec_id / f"seed_{seed}"
            images = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
            if not (run_dir / "SUCCESS").exists() or len(images) != 8:
                records.append(
                    failure_record(
                        args.method,
                        spec_id,
                        seed,
                        f"success_marker={(run_dir / 'SUCCESS').exists()} images={len(images)}",
                    )
                )
                continue
            partial_path = run_dir / "metrics/qalign.json"
            record = valid_existing(partial_path, args.method, spec_id, seed, prov)
            if record is not None:
                skipped += 1
                records.append(record)
                print(
                    f"QALIGN_SKIP {spec_id} seed={seed} score={record['qalign']:.6f}",
                    flush=True,
                )
                continue
            views = []
            with torch.inference_mode():
                for view_index, image in enumerate(images):
                    value = scalar(metric(str(image), task_="quality"), torch)
                    views.append(
                        {
                            "view_index": view_index,
                            "image": str(image.relative_to(run_dir)),
                            "qalign": value,
                        }
                    )
            record = {
                "method": args.method,
                "domain": "indoor",
                "spec_id": spec_id,
                "logical_seed": seed,
                "success": True,
                "qalign": sum(row["qalign"] for row in views) / len(views),
                "failure_policy": "none",
                "views": views,
                "provenance": prov,
            }
            atomic_json(partial_path, record)
            measured += 1
            records.append(record)
            print(
                f"QALIGN_OK {spec_id} seed={seed} score={record['qalign']:.6f}",
                flush=True,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in records
        ),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        f"QALIGN_COMPLETE records={len(records)} measured={measured} skipped={skipped} "
        f"physical_gpu={selected_gpu} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
