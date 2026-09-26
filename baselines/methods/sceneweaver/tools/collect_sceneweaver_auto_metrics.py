#!/usr/bin/env python3
"""Strictly collect SceneWeaver automatic metrics into 100-slot ITT files."""

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
import math
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
METHOD_ROOT = BASELINES / "data/table2/indoor/sceneweaver"
RESULTS_ROOT = BASELINES / "results/sceneweaver/indoor"
FAILURE_MARKERS = ("PLANNER_BUDGET_EXHAUSTED", "RENDER_VALIDATION_FAILED")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_spec_ids(path: Path) -> list[str]:
    return [
        json.loads(line)["spec_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def require_number(record: dict[str, Any], key: str, path: Path) -> float:
    value = record.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RuntimeError(f"Invalid {key} in {path}")
    return float(value)


def require_identity(
    record: dict[str, Any], spec_id: str, seed: int, path: Path
) -> None:
    expected = {
        "method": "sceneweaver",
        "domain": "indoor",
        "spec_id": spec_id,
        "logical_seed": seed,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise RuntimeError(
                f"Wrong {key} in {path}: {record.get(key)!r} != {value!r}"
            )


def atomic_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=METHOD_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    args = parser.parse_args()

    iqa_records: list[dict[str, Any]] = []
    consistency_records: list[dict[str, Any]] = []
    measured = 0
    for spec_id in load_spec_ids(args.spec_file):
        for seed in range(4):
            run_dir = args.data_root / spec_id / f"seed_{seed}"
            success = (run_dir / "SUCCESS").is_file()
            failures = [name for name in FAILURE_MARKERS if (run_dir / name).is_file()]
            if int(success) + len(failures) != 1:
                raise RuntimeError(f"Run is not uniquely terminal: {run_dir}")
            if not success:
                reason = failures[0].lower()
                iqa_records.append(
                    {
                        "method": "sceneweaver",
                        "domain": "indoor",
                        "spec_id": spec_id,
                        "logical_seed": seed,
                        "success": False,
                        "qalign": 1.0,
                        "clipiqa_plus": 0.0,
                        "failure_policy": "itt_lower_bound",
                        "failure_reason": reason,
                        "views": [],
                    }
                )
                consistency_records.append(
                    {
                        "method": "sceneweaver",
                        "domain": "indoor",
                        "spec_id": spec_id,
                        "logical_seed": seed,
                        "success": False,
                        "consistency_3d": 0.0,
                        "failure_policy": "itt_zero",
                        "failure_reason": reason,
                    }
                )
                continue

            q_path = run_dir / "metrics/qalign.json"
            c_path = run_dir / "metrics/clipiqa_plus.json"
            w_path = run_dir / "metrics/consistency_3d.json"
            qalign = load_json(q_path)
            clipiqa = load_json(c_path)
            worldscore = load_json(w_path)
            for record, path in (
                (qalign, q_path),
                (clipiqa, c_path),
                (worldscore, w_path),
            ):
                require_identity(record, spec_id, seed, path)
                if record.get("success") is not True:
                    raise RuntimeError(
                        f"Successful run has failed metric record: {path}"
                    )
            if len(qalign.get("views", [])) != 8 or len(clipiqa.get("views", [])) != 8:
                raise RuntimeError(f"Successful run lacks eight IQA views: {run_dir}")
            q_value = require_number(qalign, "qalign", q_path)
            c_value = require_number(clipiqa, "clipiqa_plus", c_path)
            w_value = require_number(worldscore, "consistency_3d", w_path)
            if not 0.0 <= w_value <= 100.0:
                raise RuntimeError(f"WorldScore out of range in {w_path}")
            q_views = {int(row["view_index"]): row for row in qalign["views"]}
            c_views = {int(row["view_index"]): row for row in clipiqa["views"]}
            if sorted(q_views) != list(range(8)) or sorted(c_views) != list(range(8)):
                raise RuntimeError(f"Invalid IQA view indices: {run_dir}")
            iqa_records.append(
                {
                    "method": "sceneweaver",
                    "domain": "indoor",
                    "spec_id": spec_id,
                    "logical_seed": seed,
                    "success": True,
                    "qalign": q_value,
                    "clipiqa_plus": c_value,
                    "failure_policy": "none",
                    "views": [
                        {
                            "view_index": index,
                            "image": c_views[index]["image"],
                            "qalign": float(q_views[index]["qalign"]),
                            "clipiqa_plus": float(c_views[index]["clipiqa_plus"]),
                        }
                        for index in range(8)
                    ],
                    "source_provenance": {
                        "qalign": qalign.get("provenance"),
                        "clipiqa_plus": clipiqa.get("provenance"),
                    },
                }
            )
            consistency_records.append(worldscore)
            measured += 1

    if len(iqa_records) != 100 or len(consistency_records) != 100:
        raise RuntimeError("Expected exactly 100 ITT records per scene metric")
    atomic_jsonl(args.results_root / "iqa_per_scene.jsonl", iqa_records)
    atomic_jsonl(args.results_root / "consistency_per_scene.jsonl", consistency_records)
    print(
        f"SCENEWEAVER_METRICS_COLLECTED records=100 measured={measured} "
        f"itt_failures={100 - measured} results_root={args.results_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
