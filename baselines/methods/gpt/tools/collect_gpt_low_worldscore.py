#!/usr/bin/env python3
"""Collect complete per-run Astra Low WorldScore records after recovery."""
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
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str((ROOT / "methods"))]
from baselines.methods.gpt.adapter_low import digest
from baselines.methods.gpt.adapter_low import utc
from baselines.methods.gpt.adapter_low import write_json
from baselines.methods.gpt.run_low_metrics import verify_evaluation_lock

METHOD = "gpt6_astra_low"


def exhausted_infrastructure(manifest: dict) -> bool:
    if manifest.get("failure_class") != "infrastructure":
        return False
    stage = (
        "render"
        if manifest.get("build_success")
        else "build"
        if manifest.get("generation_success")
        else "generation"
    )
    attempts = manifest.get(
        "attempts" if stage == "generation" else f"{stage}_attempts", []
    )
    return len(attempts) >= 3 and all(
        attempt.get("ended_at_utc") for attempt in attempts
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    args = parser.parse_args()
    verify_evaluation_lock()
    specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    rows = []
    counts = {"metric_success": 0, "droid_slam_itt_zero": 0, "failed_run_itt_zero": 0}
    for spec in specs:
        for seed in range(4):
            run = (
                ROOT
                / "data/table2"
                / args.domain
                / METHOD
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            manifest = json.loads((run / "run_manifest.json").read_text())
            render_success = (run / "SUCCESS").exists()
            if render_success != bool(manifest.get("render_success")):
                raise RuntimeError("SUCCESS/manifest mismatch: " + str(run))
            terminal_failure = manifest.get(
                "failure_class"
            ) == "quality" or exhausted_infrastructure(manifest)
            if not render_success and not terminal_failure:
                raise RuntimeError("Nonterminal matrix run: " + str(run))
            metric_path = run / "metrics/consistency_3d.json"
            row = json.loads(metric_path.read_text())
            if (
                row.get("method"),
                row.get("domain"),
                row.get("spec_id"),
                row.get("logical_seed"),
            ) != (METHOD, args.domain, spec["spec_id"], seed):
                raise RuntimeError("Foreign WorldScore record: " + str(metric_path))
            score = float(row.get("consistency_3d", float("nan")))
            if not math.isfinite(score):
                raise RuntimeError("Non-finite WorldScore: " + str(metric_path))
            if render_success:
                if row.get("success"):
                    counts["metric_success"] += 1
                elif row.get(
                    "failure_reason"
                ) == "droid_slam_failed" and "returned no valid reprojection errors" in row.get(
                    "failure_detail", ""
                ):
                    if score != 0:
                        raise RuntimeError(
                            "DROID failure must use ITT zero: " + str(metric_path)
                        )
                    counts["droid_slam_itt_zero"] += 1
                else:
                    raise RuntimeError(
                        "Successful render has unresolved WorldScore failure: "
                        + str(metric_path)
                    )
            else:
                if (
                    row.get("success")
                    or row.get("failure_reason") != "missing_or_invalid_render"
                    or score != 0
                ):
                    raise RuntimeError(
                        "Failed run lacks WorldScore ITT zero: " + str(metric_path)
                    )
                counts["failed_run_itt_zero"] += 1
            rows.append(row)
    if len(rows) != 100:
        raise RuntimeError("Expected 100 WorldScore records")
    output = (
        ROOT
        / "results/gpt6_astra_low/formal"
        / args.domain
        / "consistency_per_scene.jsonl"
    )
    temporary = output.with_suffix(output.suffix + ".tmp")
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    output_sha256 = hashlib.sha256(payload.encode()).hexdigest()
    temporary.write_text(payload)
    temporary.replace(output)
    report = {
        "status": "complete",
        "collected_at_utc": utc(),
        "method": METHOD,
        "domain": args.domain,
        "records": len(rows),
        **counts,
        # Hash the exact payload rather than reopening a just-renamed NFS inode.
        "output": str(output.relative_to(ROOT)),
        "output_sha256": output_sha256,
    }
    write_json(
        ROOT / "results/gpt6_astra_low" / f"worldscore_collection_{args.domain}.json",
        report,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
