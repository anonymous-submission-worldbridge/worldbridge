#!/usr/bin/env python3
"""Seal final Extra High Table-3 aggregate and audit artifacts."""

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
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RESULTS = BASELINES / "results/gpt6_astra_xhigh_table3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    audit = json.loads((RESULTS / "audit.json").read_text(encoding="utf-8"))
    if audit.get("passed") is not True:
        raise RuntimeError("Refusing to seal a failing Extra High audit")
    files = (
        "table3.csv",
        "table3_full.json",
        "audit.json",
        "method.lock.json",
        "metrics.lock.json",
        "source_recovery.json",
    )
    missing = [name for name in files if not (RESULTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing final results: {missing}")
    payload = {
        "method": "gpt6_astra_xhigh",
        "reasoning_effort": "xhigh",
        "source_recovery": True,
        "exact_table2_byte_reuse": False,
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {name: sha256(RESULTS / name) for name in files},
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
