#!/usr/bin/env python3
"""Print a read-only live progress snapshot for the GLM-5.3 Flash matrix."""
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


from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "glm53_flash"


def classify(run: Path, manifest: dict | None) -> str:
    if manifest is None:
        return "unstarted"
    if (run / "SUCCESS").exists() and manifest.get("render_success"):
        return "valid"
    if manifest.get("failure_class") == "quality":
        return "quality"
    attempts = manifest.get("attempts", [])
    if attempts and not attempts[-1].get("ended_at_utc"):
        return "generating"
    render_attempts = manifest.get("render_attempts", [])
    if render_attempts and not render_attempts[-1].get("ended_at_utc"):
        return "rendering"
    build_attempts = manifest.get("build_attempts", [])
    if build_attempts and not build_attempts[-1].get("ended_at_utc"):
        return "building"
    if manifest.get("failure_class") in {"infrastructure", "access_blocked"}:
        return manifest["failure_class"]
    if manifest.get("build_success"):
        return "waiting_render"
    if manifest.get("generation_success"):
        return "waiting_build"
    return "queued_generation"


def snapshot() -> dict:
    totals = Counter()
    domains = {}
    records = []
    for domain in ("indoor", "urban"):
        counts = Counter()
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if line
        ]
        for spec in specs:
            for seed in range(4):
                run = (
                    ROOT
                    / "data/table2"
                    / domain
                    / METHOD
                    / spec["spec_id"]
                    / f"seed_{seed}"
                )
                manifest_path = run / "run_manifest.json"
                manifest = (
                    json.loads(manifest_path.read_text())
                    if manifest_path.exists()
                    else None
                )
                status = classify(run, manifest)
                counts[status] += 1
                totals[status] += 1
                records.append((manifest, status))
        domains[domain] = dict(sorted(counts.items()))
    terminal = totals["valid"] + totals["quality"]
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected": 200,
        "started": 200 - totals["unstarted"],
        "terminal_for_itt": terminal,
        "terminal_percent": round(terminal / 2, 1),
        "generated": sum(
            bool(manifest and manifest.get("generation_success"))
            for manifest, _ in records
        ),
        "built": sum(
            bool(manifest and manifest.get("build_success")) for manifest, _ in records
        ),
        "rendered": totals["valid"],
        "counts": dict(sorted(totals.items())),
        "domains": domains,
        "free_gib": round(shutil.disk_usage(ROOT).free / 1024**3, 1),
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True), flush=True)
