#!/usr/bin/env python3
"""Read-only audit of all 100 retained SceneWeaver Table-2 terminals."""

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
from collections import Counter
from pathlib import Path
import sys


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.evaluation.geometry.common import BASELINES
from baselines.evaluation.geometry.common import SPEC_FILE
from baselines.evaluation.geometry.common import TABLE2_ROOT
from baselines.evaluation.geometry.common import atomic_json
from baselines.evaluation.geometry.common import classify_table2_run
from baselines.evaluation.geometry.common import load_specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=TABLE2_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES / "table3/results/sceneweaver_reuse_inventory.json",
    )
    args = parser.parse_args()
    records = []
    for spec in load_specs(args.spec_file):
        for seed in range(4):
            run_dir = args.source_root / spec["spec_id"] / f"seed_{seed}"
            records.append(
                {
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "source_run": str(run_dir),
                    **classify_table2_run(run_dir),
                }
            )
    counts = Counter(record["classification"] for record in records)
    payload = {
        "method": "sceneweaver",
        "domain": "indoor",
        "planned_runs": len(records),
        "classification_counts": dict(sorted(counts.items())),
        "reusable_raw": sum(record["reusable_raw"] for record in records),
        "regeneration_authorized": False,
        "records": records,
    }
    atomic_json(args.output, payload)
    print(
        f"SCENEWEAVER_REUSE_AUDIT planned={len(records)} reusable={payload['reusable_raw']} "
        f"counts={payload['classification_counts']}"
    )
    return 0 if len(records) == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
