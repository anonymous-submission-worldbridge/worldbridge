#!/usr/bin/env python3
"""Seal verified GPT-6 Astra Low Table-3 artifacts and display rows."""

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


import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RESULTS = BASELINES / "results/gpt6_astra_low/table3"
METHOD = "gpt6_astra_low"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    required = (
        "method.lock.json",
        "metrics.lock.json",
        "table3.csv",
        "table3_full.json",
        "audit.json",
        "matrix_formal.jsonl",
    )
    missing = [name for name in required if not (RESULTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing final Low results: {missing}")
    audit = read_json(RESULTS / "audit.json")
    expected_counts = {
        "indoor": {"planned": 100, "evaluated": 97, "itt": 3},
        "urban": {"planned": 100, "evaluated": 98, "itt": 2},
    }
    if audit.get("passed") is not True or audit.get("counts") != expected_counts:
        raise RuntimeError("Refusing to seal a failing or incomplete Low audit")
    matrix_rows = [
        json.loads(line)
        for line in (RESULTS / "matrix_formal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    matrix_counts = Counter(row.get("status") for row in matrix_rows)
    expected_matrix = Counter({"evaluated": 195, "resumed": 195, "itt": 10})
    if matrix_counts != expected_matrix or len(matrix_rows) != 400:
        raise RuntimeError(f"Formal generation/resume record mismatch: {matrix_counts}")
    full = read_json(RESULTS / "table3_full.json")
    domains = {}
    for summary in full.get("domains", []):
        domain = summary["domain"]
        metrics = summary["metrics"]
        nav = float(metrics["navigable_area_ratio"]["mean"])
        connected = float(metrics["connected_area_ratio"]["mean"])
        success = float(metrics["navmesh_success_rate"]["mean"])
        domains[domain] = {
            "planned_runs": 100,
            "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
            "itt_runs": summary["itt_failure_runs"],
            "navigable_area_ratio": nav,
            "connected_area_ratio": connected,
            "navmesh_success_rate": success,
            "display_row": [
                "N/A-I",
                "N/A-I",
                "N/A-I",
                "N/A-I",
                f"{nav:.1f}",
                f"{connected:.1f}",
                f"{success:.1f}",
                "N/A-I",
            ],
        }
    if set(domains) != {"indoor", "urban"}:
        raise RuntimeError("Final aggregate must contain exactly Indoor and Urban")
    payload = {
        "status": "both_domains_table3_verified_and_table_filled",
        "method": METHOD,
        "display_name": "GPT-6 Astra Low",
        "model_id": "gpt-6-astra",
        "reasoning_effort": "low",
        "model_requests_in_table3": 0,
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_matrix": {
            "planned_runs": 200,
            "evaluated_geometry_runs": 195,
            "itt_runs": 5,
            "new_runner_failures": 0,
            "resume_cache_hits": 195,
        },
        "domains": domains,
        "files_sha256": {
            "methods/gpt/protocol/geometry/gpt6_astra_low_geometry_protocol.json": sha256(
                (
                    BASELINES
                    / "methods/gpt/protocol/geometry/gpt6_astra_low_geometry_protocol.json"
                )
            ),
            **{
                f"results/gpt6_astra_low/table3/{name}": sha256(RESULTS / name)
                for name in required
            },
        },
    }
    temporary = RESULTS / "result.lock.json.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(RESULTS / "result.lock.json")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
