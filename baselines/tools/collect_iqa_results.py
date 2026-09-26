#!/usr/bin/env python3
"""Merge staged Q-Align and CLIP-IQA+ records without hiding missing metrics."""

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
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


BASELINES = Path(__file__).resolve().parents[1]
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
DEFAULT_OUTPUT = BASELINES / "results/iqa_per_scene.jsonl"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = load_module(
    "table2_audit_infinigen",
    (BASELINES / "methods/infinigen/tools/audit_infinigen_matrix.py"),
)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_spec_ids(path: Path) -> list[str]:
    return [
        json.loads(line)["spec_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def valid_partial(
    record: dict[str, Any] | None,
    metric: str,
    spec_id: str,
    seed: int,
) -> bool:
    if record is None:
        return False
    value = record.get(metric)
    return (
        record.get("method") == "infinigen_indoors"
        and record.get("domain") == "indoor"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == seed
        and record.get("success") is True
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and len(record.get("views", [])) == 8
        and isinstance(record.get("provenance"), dict)
    )


def formal_generate_attempts(run_dir: Path) -> list[dict[str, Any]]:
    manifest = load_json(run_dir / "run_manifest.json") or {}
    return [
        row for row in manifest.get("attempts", []) if AUDIT.is_formal_generate(row)
    ]


def terminal_failure(run_dir: Path, classification: str) -> bool:
    if classification == "quality_failure":
        return True
    attempts = formal_generate_attempts(run_dir)
    return (
        classification == "infrastructure_candidate"
        and len(attempts) >= 2
        and attempts[-1].get("success") is False
    )


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-qalign",
        action="store_true",
        help="Reject output unless all successful runs have Q-Align records.",
    )
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    qalign_measured = 0
    clip_measured = 0
    for spec_id in load_spec_ids(args.spec_file):
        for seed in range(4):
            run_dir = args.data_root / spec_id / f"seed_{seed}"
            classification = AUDIT.classify(run_dir)
            if (run_dir / "SUCCESS").exists():
                clip = load_json(run_dir / "metrics/clipiqa_plus.json")
                qalign = load_json(run_dir / "metrics/qalign.json")
                if not valid_partial(clip, "clipiqa_plus", spec_id, seed):
                    raise RuntimeError(
                        f"Successful run lacks valid CLIP-IQA+: {spec_id}/seed_{seed}"
                    )
                qalign_valid = valid_partial(qalign, "qalign", spec_id, seed)
                if args.require_qalign and not qalign_valid:
                    raise RuntimeError(
                        f"Successful run lacks valid Q-Align: {spec_id}/seed_{seed}"
                    )
                clip_measured += 1
                qalign_measured += int(qalign_valid)
                q_views = {
                    int(row["view_index"]): row
                    for row in (qalign or {}).get("views", [])
                }
                views = []
                for clip_view in clip["views"]:
                    index = int(clip_view["view_index"])
                    views.append(
                        {
                            "view_index": index,
                            "image": clip_view["image"],
                            "qalign": (
                                float(q_views[index]["qalign"])
                                if index in q_views
                                else None
                            ),
                            "clipiqa_plus": float(clip_view["clipiqa_plus"]),
                        }
                    )
                records.append(
                    {
                        "method": "infinigen_indoors",
                        "domain": "indoor",
                        "spec_id": spec_id,
                        "logical_seed": seed,
                        "success": True,
                        "qalign": float(qalign["qalign"]) if qalign_valid else None,
                        "clipiqa_plus": float(clip["clipiqa_plus"]),
                        "failure_policy": "none",
                        "metrics_complete": (
                            ["qalign", "clipiqa_plus"]
                            if qalign_valid
                            else ["clipiqa_plus"]
                        ),
                        "views": views,
                        "source_provenance": {
                            "qalign": qalign.get("provenance")
                            if qalign_valid
                            else None,
                            "clipiqa_plus": clip["provenance"],
                        },
                    }
                )
                continue
            if not terminal_failure(run_dir, classification):
                raise RuntimeError(
                    f"Nonterminal matrix slot rejected: {spec_id}/seed_{seed} "
                    f"classification={classification}"
                )
            records.append(
                {
                    "method": "infinigen_indoors",
                    "domain": "indoor",
                    "spec_id": spec_id,
                    "logical_seed": seed,
                    "success": False,
                    "qalign": 1.0,
                    "clipiqa_plus": 0.0,
                    "failure_policy": "itt_lower_bound",
                    "failure_reason": classification,
                    "metrics_complete": ["qalign", "clipiqa_plus"],
                    "views": [],
                }
            )

    if len(records) != 100:
        raise RuntimeError(f"Expected 100 records, found {len(records)}")
    atomic_text(
        args.output,
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in records
        ),
    )
    summary = {
        "status": "complete" if qalign_measured == clip_measured else "qalign_pending",
        "record_count": len(records),
        "successful_run_count": clip_measured,
        "terminal_failure_count": len(records) - clip_measured,
        "clipiqa_plus_measured_count": clip_measured,
        "qalign_measured_count": qalign_measured,
        "qalign_required": args.require_qalign,
    }
    atomic_text(
        args.output.with_suffix(".summary.json"),
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"IQA_COLLECT_COMPLETE records={len(records)} clip_measured={clip_measured} "
        f"qalign_measured={qalign_measured} status={summary['status']} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
