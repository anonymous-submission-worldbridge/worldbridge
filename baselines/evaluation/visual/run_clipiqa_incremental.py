#!/usr/bin/env python3
"""Incrementally evaluate frozen CLIP-IQA+ without loading Q-Align.

The frozen combined evaluator creates both models up front.  On a shared GPU,
that unnecessarily blocks CLIP-IQA+ when the much larger Q-Align model cannot
fit.  This staging runner uses the identical pyiqa metric name, images, scalar
conversion, and weights, while keeping its partial records separate until the
combined IQA result can be finalized.
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
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
METRICS_LOCK = BASELINES / "protocol/generation/metrics.lock.json"
FROZEN_EVALUATOR = BASELINES / "evaluation/visual/eval_iqa.py"
DEFAULT_OUTPUT = BASELINES / "results/clipiqa_plus_per_scene.checkpoint.jsonl"

os.environ.setdefault("TORCH_HOME", str(BASELINES / "cache/torch"))
os.environ.setdefault("HF_HOME", str(BASELINES / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES / "cache/xdg_metrics"))

import pyiqa  # noqa: E402
import torch  # noqa: E402


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


def scalar(value: Any) -> float:
    if isinstance(value, (list, tuple)):
        value = value[0]
    if torch.is_tensor(value):
        value = value.detach().float().mean().cpu().item()
    return float(value)


def provenance() -> dict[str, Any]:
    lock = json.loads(METRICS_LOCK.read_text(encoding="utf-8"))["clipiqa_plus"]
    return {
        "implementation": lock["implementation"],
        "backbone": lock["backbone"],
        "backbone_weights_sha256": lock["backbone_weights_sha256"],
        "learned_prompts_weights_sha256": lock["learned_prompts_weights_sha256"],
        "frozen_combined_evaluator_sha256": sha256(FROZEN_EVALUATOR),
        "metrics_lock_sha256": sha256(METRICS_LOCK),
        "pyiqa_version": getattr(pyiqa, "__version__", "unknown"),
        "torch_version": torch.__version__,
    }


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
    valid = (
        record.get("method") == method
        and record.get("domain") == "indoor"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("success") is True
        and isinstance(record.get("clipiqa_plus"), (int, float))
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
        "clipiqa_plus": 0.0,
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
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--spec-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if args.seed is not None and args.seed not in range(4):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")

    specs = [
        row
        for row in load_specs(args.spec_file)
        if args.spec_id in (None, row["spec_id"])
    ]
    if not specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    seeds = range(4) if args.seed is None else [args.seed]
    prov = provenance()
    metric = pyiqa.create_metric("clipiqa+", device=args.device)
    records: list[dict[str, Any]] = []
    measured = 0
    skipped = 0
    for spec in specs:
        spec_id = spec["spec_id"]
        for seed in seeds:
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
            partial_path = run_dir / "metrics/clipiqa_plus.json"
            record = valid_existing(partial_path, args.method, spec_id, seed, prov)
            if record is not None:
                skipped += 1
                records.append(record)
                print(
                    f"CLIPIQA_SKIP {spec_id} seed={seed} score={record['clipiqa_plus']:.6f}",
                    flush=True,
                )
                continue
            views = []
            with torch.inference_mode():
                for view_index, image in enumerate(images):
                    value = scalar(metric(str(image)))
                    views.append(
                        {
                            "view_index": view_index,
                            "image": str(image.relative_to(run_dir)),
                            "clipiqa_plus": value,
                        }
                    )
            record = {
                "method": args.method,
                "domain": "indoor",
                "spec_id": spec_id,
                "logical_seed": seed,
                "success": True,
                "clipiqa_plus": sum(row["clipiqa_plus"] for row in views) / len(views),
                "failure_policy": "none",
                "views": views,
                "provenance": prov,
            }
            atomic_json(partial_path, record)
            measured += 1
            records.append(record)
            print(
                f"CLIPIQA_OK {spec_id} seed={seed} score={record['clipiqa_plus']:.6f}",
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
        f"CLIPIQA_COMPLETE records={len(records)} measured={measured} skipped={skipped} "
        f"output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
