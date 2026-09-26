#!/usr/bin/env python3
"""Audit the frozen Table 2 Infinigen matrix for Table 3 reuse."""

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
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = _BASELINE_PROJECT_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.methods.infinigen.tools.audit_infinigen_matrix import DATA_ROOT
from baselines.methods.infinigen.tools.audit_infinigen_matrix import classify


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPECS = BASELINES / "protocol/geometry/indoor_specs.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(BASELINES / "evaluation/geometry/results/reuse_inventory.json"),
    )
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in SPECS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    for spec in specs:
        for seed in range(4):
            source = DATA_ROOT / spec["spec_id"] / f"seed_{seed}"
            status = classify(source)
            scene = source / "scene/scene.blend"
            reuse = (
                "reusable_raw"
                if status == "formal_success" and scene.is_file()
                else "table2_failure"
            )
            rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "table2_status": status,
                    "reuse_status": reuse,
                    "source_run_dir": str(source),
                    "scene_exists": scene.is_file(),
                    "scene_size_bytes": scene.stat().st_size if scene.is_file() else 0,
                }
            )
    result = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "planned_runs": len(rows),
        "counts": dict(Counter(row["reuse_status"] for row in rows)),
        "table2_counts": dict(Counter(row["table2_status"] for row in rows)),
        "regeneration_authorized": False,
        "runs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
