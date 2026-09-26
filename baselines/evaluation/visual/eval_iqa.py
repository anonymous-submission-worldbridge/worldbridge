#!/usr/bin/env python3
"""Evaluate Q-Align and CLIP-IQA+ on frozen anchor renders."""

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
import json
import os
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
os.environ.setdefault("TORCH_HOME", str(BASELINES_ROOT / "cache/torch"))
os.environ.setdefault("HF_HOME", str(BASELINES_ROOT / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES_ROOT / "cache/xdg_metrics"))

import pyiqa  # noqa: E402
import torch  # noqa: E402


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_specs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def per_scene_artifact(
    run_dir: Path, data_root: Path, artifact_root: Path | None, relative: str
) -> Path:
    base = (
        artifact_root / run_dir.relative_to(data_root)
        if artifact_root is not None
        else run_dir
    )
    return base / relative


def scalar(value) -> float:
    if isinstance(value, (list, tuple)):
        value = value[0]
    if torch.is_tensor(value):
        value = value.detach().float().mean().cpu().item()
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root", type=Path, default=BASELINES_ROOT / "data/table2"
    )
    parser.add_argument(
        "--spec-file",
        type=Path,
        default=(BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    )
    parser.add_argument(
        "--output", type=Path, default=BASELINES_ROOT / "results/iqa_per_scene.jsonl"
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--domain", choices=("indoor", "urban"), default="indoor")
    parser.add_argument("--spec-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help=(
            "Optional writable mirror root for per-scene metric artifacts. "
            "The aggregate --output remains unchanged."
        ),
    )
    args = parser.parse_args()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    qalign = pyiqa.create_metric("qalign", device=args.device)
    clipiqa = pyiqa.create_metric("clipiqa+", device=args.device)
    records = []
    specs = [
        spec
        for spec in load_specs(args.spec_file)
        if args.spec_id in (None, spec["spec_id"])
    ]
    if args.spec_id is not None and not specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    seeds = range(4) if args.seed is None else [args.seed]
    if args.seed is not None and args.seed not in range(4):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    for spec in specs:
        for logical_seed in seeds:
            run_dir = (
                args.data_root
                / args.domain
                / args.method
                / spec["spec_id"]
                / f"seed_{logical_seed}"
            )
            success = (run_dir / "SUCCESS").exists()
            images = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
            if not success or len(images) != 8:
                record = {
                    "method": args.method,
                    "domain": args.domain,
                    "spec_id": spec["spec_id"],
                    "logical_seed": logical_seed,
                    "success": False,
                    "qalign": 1.0,
                    "clipiqa_plus": 0.0,
                    "failure_policy": "itt_lower_bound",
                    "views": [],
                }
                atomic_json(
                    per_scene_artifact(
                        run_dir, args.data_root, args.artifact_root, "metrics/iqa.json"
                    ),
                    record,
                )
                records.append(record)
                continue
            views = []
            with torch.inference_mode():
                for view_index, image in enumerate(images):
                    q_value = scalar(qalign(str(image), task_="quality"))
                    c_value = scalar(clipiqa(str(image)))
                    views.append(
                        {
                            "view_index": view_index,
                            "image": str(image.relative_to(run_dir)),
                            "qalign": q_value,
                            "clipiqa_plus": c_value,
                        }
                    )
            record = {
                "method": args.method,
                "domain": args.domain,
                "spec_id": spec["spec_id"],
                "logical_seed": logical_seed,
                "success": True,
                "qalign": sum(view["qalign"] for view in views) / len(views),
                "clipiqa_plus": sum(view["clipiqa_plus"] for view in views)
                / len(views),
                "failure_policy": "none",
                "views": views,
            }
            atomic_json(
                per_scene_artifact(
                    run_dir, args.data_root, args.artifact_root, "metrics/iqa.json"
                ),
                record,
            )
            records.append(record)
            print(
                f"IQA_OK {spec['spec_id']} seed={logical_seed} "
                f"qalign={record['qalign']:.6f} clipiqa+={record['clipiqa_plus']:.6f}",
                flush=True,
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in records))
    temporary.replace(args.output)
    print(f"IQA_COMPLETE records={len(records)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
