#!/usr/bin/env python3
"""Finalize staged IQA and Table-2 aggregation after Q-Align completes."""

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
import subprocess
import sys
import time
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_QALIGN = BASELINES / "results/qalign_per_scene.checkpoint.jsonl"


def complete_qalign(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return False
    keys = {(row.get("spec_id"), row.get("logical_seed")) for row in rows}
    measured = [row for row in rows if row.get("success") is True]
    return (
        len(rows) == 100
        and len(keys) == 100
        and len(measured) == 89
        and all(isinstance(row.get("qalign"), (int, float)) for row in rows)
    )


def run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=BASELINES.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout, end="", flush=True)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed with exit={completed.returncode}: {' '.join(command)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qalign-output", type=Path, default=DEFAULT_QALIGN)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-wait-hours", type=float, default=168.0)
    args = parser.parse_args()
    if args.poll_seconds < 10 or args.poll_seconds > 300:
        parser.error("--poll-seconds must be between 10 and 300")

    deadline = time.monotonic() + args.max_wait_hours * 3600.0
    while not complete_qalign(args.qalign_output):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Q-Align did not complete within {args.max_wait_hours} hours"
            )
        partial_count = len(
            list(
                (BASELINES / "data/table2/indoor/infinigen_indoors").glob(
                    "*/seed_*/metrics/qalign.json"
                )
            )
        )
        print(
            f"QALIGN_FINALIZE_WAIT measured_partial_files={partial_count}/89",
            flush=True,
        )
        time.sleep(args.poll_seconds)

    print("QALIGN_FINALIZE_INPUT_COMPLETE records=100 measured=89", flush=True)
    run(
        [
            sys.executable,
            str(BASELINES / "tools/collect_iqa_results.py"),
            "--require-qalign",
            "--output",
            str(BASELINES / "results/iqa_per_scene.jsonl"),
        ]
    )
    run(
        [
            sys.executable,
            str((BASELINES / "evaluation/visual/aggregate_generation.py")),
            "--method",
            "infinigen_indoors",
            "--domain",
            "indoor",
        ]
    )
    print("QALIGN_FINALIZE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
