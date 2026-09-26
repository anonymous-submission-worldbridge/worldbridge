#!/usr/bin/env python3
"""Validate three-rater blind annotations and compute ITT human metrics."""

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
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE_ROOT = BASELINES_ROOT / "annotations/table2_v1"
OUTPUT = BASELINES_ROOT / "results/human_per_scene.jsonl"
LAYOUT_FIELDS = [
    "boundary_collision",
    "support_pose",
    "scale_density",
    "function_circulation",
]
VALID_RESPONSES = {"yes", "no", "not-visible"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=PACKAGE_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--rating-source",
        default="human",
        help="Provenance label written to every output record.",
    )
    args = parser.parse_args()
    mapping = json.loads(
        (args.package / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    items = {row["blind_id"]: row for row in read_csv(args.package / "items.csv")}
    layout_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(args.package / "layout_ratings.csv"):
        layout_rows[row["blind_id"]].append(row)
    prompt_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(args.package / "prompt_ratings.csv"):
        prompt_rows[row["blind_id"]].append(row)

    errors = []
    records: list[dict[str, Any]] = []
    for private in mapping:
        base = {
            "method": private["method"],
            "domain": private["domain"],
            "spec_id": private["spec_id"],
            "logical_seed": private["logical_seed"],
            "blind_id": private["blind_id"],
            "rating_source": args.rating_source,
        }
        if not private["success"]:
            records.append(
                {
                    **base,
                    "success": False,
                    "layout_plausibility": 0.0,
                    "prompt_alignment": 0.0,
                    "rater_count": 0,
                    "failure_policy": "itt_zero",
                }
            )
            continue
        item_id = private["blind_id"]
        if item_id not in items:
            errors.append(f"{item_id}: missing public item")
            continue
        item = items[item_id]
        layout_by_rater: dict[str, list[float]] = {}
        for row in layout_rows[item_id]:
            rater = row["rater_id"].strip()
            try:
                values = [float(row[field]) for field in LAYOUT_FIELDS]
            except ValueError:
                errors.append(f"{item_id}/{rater}: incomplete layout rating")
                continue
            if not all(value.is_integer() and 1 <= value <= 5 for value in values):
                errors.append(
                    f"{item_id}/{rater}: layout ratings must be integers 1..5"
                )
                continue
            if rater in layout_by_rater:
                errors.append(f"{item_id}/{rater}: duplicate layout row")
                continue
            layout_by_rater[rater] = values

        fact_count = int(item["fact_count"])
        prompt_by_rater: dict[str, dict[int, str]] = defaultdict(dict)
        for row in prompt_rows[item_id]:
            rater = row["rater_id"].strip()
            response = row["response"].strip().lower()
            try:
                fact_index = int(row["fact_index"])
            except ValueError:
                errors.append(f"{item_id}/{rater}: invalid fact index")
                continue
            if response not in VALID_RESPONSES:
                errors.append(f"{item_id}/{rater}/fact_{fact_index}: invalid response")
                continue
            if fact_index in prompt_by_rater[rater]:
                errors.append(
                    f"{item_id}/{rater}/fact_{fact_index}: duplicate response"
                )
                continue
            prompt_by_rater[rater][fact_index] = response
        layout_raters = set(layout_by_rater)
        prompt_raters = {
            rater
            for rater, responses in prompt_by_rater.items()
            if set(responses) == set(range(fact_count))
        }
        if len(layout_raters) != 3 or layout_raters != prompt_raters:
            errors.append(
                f"{item_id}: need the same 3 complete raters; "
                f"layout={sorted(layout_raters)} prompt={sorted(prompt_raters)}"
            )
            continue
        layout_per_rater = [
            25.0 * (float(np.mean(layout_by_rater[rater])) - 1.0)
            for rater in sorted(layout_raters)
        ]
        prompt_per_rater = [
            100.0
            * sum(response == "yes" for response in prompt_by_rater[rater].values())
            / fact_count
            for rater in sorted(prompt_raters)
        ]
        records.append(
            {
                **base,
                "success": True,
                "layout_plausibility": float(np.mean(layout_per_rater)),
                "prompt_alignment": float(np.mean(prompt_per_rater)),
                "rater_count": 3,
                "layout_per_rater": layout_per_rater,
                "prompt_per_rater": prompt_per_rater,
                "failure_policy": "none",
            }
        )
    if errors:
        print("HUMAN_RATINGS_INVALID")
        for error in errors[:100]:
            print(f"- {error}")
        print(f"error_count={len(errors)}; no output was written")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(f"HUMAN_RATINGS_COMPLETE records={len(records)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
