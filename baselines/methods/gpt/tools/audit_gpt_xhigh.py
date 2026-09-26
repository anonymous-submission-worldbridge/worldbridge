#!/usr/bin/env python3
"""Read-only audit of GPT-6 Astra Extra High pilot or formal matrices."""
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
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gpt6_astra_xhigh"


def audit(data_root: Path, pilot: bool) -> dict:
    records = []
    for domain in ("indoor", "urban"):
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if line
        ]
        if pilot:
            specs = [spec for spec in specs if spec["spec_index"] % 5 == 0]
        for spec in specs:
            for seed in [0, 1] if pilot else range(4):
                run = data_root / domain / METHOD / spec["spec_id"] / f"seed_{seed}"
                row = {
                    "domain": domain,
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "status": "not_started",
                }
                manifest_path = run / "run_manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text())
                    except json.JSONDecodeError as exc:
                        row.update(status="invalid_manifest", failure_reason=str(exc))
                        records.append(row)
                        continue
                    row.update(
                        code_generated=bool(manifest.get("generation_success")),
                        scene_built=bool(manifest.get("build_success")),
                        render_success=bool(manifest.get("render_success")),
                        failure_reason=manifest.get("failure_reason"),
                        generation_attempts=len(manifest.get("attempts", [])),
                        build_attempts=len(manifest.get("build_attempts", [])),
                        render_attempts=len(manifest.get("render_attempts", [])),
                        reasoning_effort=manifest.get("reasoning_effort_requested"),
                    )
                    if (
                        manifest.get("method") != METHOD
                        or manifest.get("reasoning_effort_requested") != "xhigh"
                    ):
                        row["status"] = "identity_mismatch"
                    elif (run / "SUCCESS").exists() and manifest.get("render_success"):
                        row["status"] = "valid"
                    else:
                        stage = (
                            "render"
                            if manifest.get("build_success")
                            else "build"
                            if manifest.get("generation_success")
                            else "generation"
                        )
                        attempts = manifest.get(
                            "attempts"
                            if stage == "generation"
                            else stage + "_attempts",
                            [],
                        )
                        if attempts and not attempts[-1].get("ended_at_utc"):
                            row["status"] = {
                                "generation": "generating",
                                "build": "building",
                                "render": "rendering",
                            }[stage]
                        elif manifest.get("failure_class"):
                            row["status"] = manifest["failure_class"]
                        else:
                            row["status"] = "queued_" + stage
                records.append(row)
    counts = dict(Counter(row["status"] for row in records))
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": METHOD,
        "reasoning_effort": "xhigh",
        "data_root": str(data_root),
        "pilot": pilot,
        "expected": len(records),
        "counts": counts,
        "built": sum(row.get("scene_built", False) for row in records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    root = args.data_root or ROOT / (
        "data/gpt6_astra_xhigh_pilot" if args.pilot else "data/table2"
    )
    report = audit(root, args.pilot)
    output = (
        ROOT
        / "results/gpt6_astra_xhigh"
        / ("pilot_audit.json" if args.pilot else "formal_audit.json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "records"}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
