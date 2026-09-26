#!/usr/bin/env python3
"""Verify a local model snapshot against a frozen JSON file manifest."""

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
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ignore", nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ignored = set(args.ignore)
    records = []
    failures = []
    for expected in manifest["files"]:
        relative = expected["path"]
        if relative in ignored:
            records.append({"path": relative, "status": "ignored_metadata_difference"})
            continue
        path = args.root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            records.append({"path": relative, "status": "missing"})
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        valid = size == int(expected["size"]) and digest == expected["sha256"]
        records.append(
            {
                "path": relative,
                "status": "verified" if valid else "mismatch",
                "size": size,
                "sha256": digest,
                "expected_size": int(expected["size"]),
                "expected_sha256": expected["sha256"],
            }
        )
        if not valid:
            failures.append(f"mismatch:{relative}")
        print(f"WEIGHT_{'OK' if valid else 'FAIL'} {relative} bytes={size}", flush=True)
    payload = {
        "manifest": str(args.manifest.resolve()),
        "root": str(args.root.resolve()),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "ignored": sorted(ignored),
        "failures": failures,
        "verified_files": sum(row["status"] == "verified" for row in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        f"WEIGHT_AUDIT_COMPLETE verified={payload['verified_files']} failures={len(failures)}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
