"""Read-only scene audit plus an Astra-only progress report."""

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
import os
from pathlib import Path

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def runtime():
    from baselines.methods.gpt.tools.migrate_gpt_scheduler import process

    rows = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        record = process(int(directory.name))
        if not record or record["uid"] != os.getuid():
            continue
        command = record["command"]
        if not any("gpt6_astra" in arg for arg in command) or any(
            arg in ["-c", "-lc"] for arg in command
        ):
            continue
        rows.append(record)
    return rows


def audit(data_root, pilot):
    records = []
    for domain in ["indoor", "urban"]:
        specs = [
            json.loads(l)
            for l in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if l
        ]
        if pilot:
            specs = [s for s in specs if s["spec_index"] % 5 == 0]
        for spec in specs:
            for seed in [0, 1] if pilot else range(4):
                run = (
                    data_root / domain / "gpt6_astra" / spec["spec_id"] / f"seed_{seed}"
                )
                row = {
                    "domain": domain,
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "status": "not_started",
                }
                path = run / "run_manifest.json"
                if path.exists():
                    m = json.loads(path.read_text())
                    row.update(
                        code_generated=bool(m.get("generation_success")),
                        scene_built=bool(m.get("build_success")),
                        render_success=bool(m.get("render_success")),
                        failure_reason=m.get("failure_reason"),
                        generation_attempts=len(m.get("attempts", [])),
                    )
                    if (run / "SUCCESS").exists() and m.get("render_success"):
                        row["status"] = "valid"
                    else:
                        stage = (
                            "render"
                            if m.get("build_success")
                            else "build"
                            if m.get("generation_success")
                            else "generation"
                        )
                        attempts = m.get(
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
                        elif m.get("failure_class"):
                            row["status"] = m["failure_class"]
                        else:
                            row["status"] = "queued_" + stage
                    row["usage"] = [
                        usage
                        for a in m.get("attempts", [])
                        for usage in a.get("usage", [])
                        if usage
                    ]
                records.append(row)
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "pilot": pilot,
        "expected": len(records),
        "counts": dict(Counter(r["status"] for r in records)),
        "built": sum(r.get("scene_built", False) for r in records),
        "records": records,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--runtime", action="store_true")
    args = p.parse_args()
    if args.runtime:
        print(json.dumps(runtime(), indent=2))
        return
    root = ROOT / ("data/gpt6_astra_pilot" if args.pilot else "data/table2")
    report = audit(root, args.pilot)
    output = (
        ROOT
        / "results/gpt6_astra"
        / ("pilot_audit.json" if args.pilot else "formal_audit.json")
    )
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}), flush=True)


if __name__ == "__main__":
    main()
