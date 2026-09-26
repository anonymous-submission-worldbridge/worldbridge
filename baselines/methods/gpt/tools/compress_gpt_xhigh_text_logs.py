#!/usr/bin/env python3
"""Losslessly compress only GPT-6 Astra Extra High text logs."""
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


import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SEARCH_ROOTS = [
    ROOT / "data/table2/indoor/gpt6_astra_xhigh",
    ROOT / "data/table2/urban/gpt6_astra_xhigh",
    ROOT / "data/gpt6_astra_xhigh_pilot",
]


def file_digest(path: Path, compressed: bool = False) -> str:
    result = hashlib.sha256()
    opener = gzip.open if compressed else open
    with opener(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main() -> int:
    records = []
    for search_root in SEARCH_ROOTS:
        if not search_root.exists():
            continue
        for source in sorted(search_root.rglob("*.log")):
            if not source.is_file() or source.is_symlink():
                raise RuntimeError("Unexpected log type: " + str(source))
            target = source.with_suffix(source.suffix + ".gz")
            temporary = target.with_suffix(target.suffix + ".tmp")
            if target.exists() or temporary.exists():
                raise RuntimeError(
                    "Refusing to overwrite compressed log: " + str(target)
                )
            before = source.stat().st_size
            before_hash = file_digest(source)
            with source.open("rb") as incoming, temporary.open("wb") as raw_out:
                with gzip.GzipFile(
                    filename="", mode="wb", fileobj=raw_out, compresslevel=9, mtime=0
                ) as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            if file_digest(temporary, compressed=True) != before_hash:
                temporary.unlink()
                raise RuntimeError("Compressed verification failed: " + str(source))
            os.replace(temporary, target)
            source.unlink()
            records.append(
                {
                    "source": str(source.relative_to(ROOT)),
                    "archive": str(target.relative_to(ROOT)),
                    "uncompressed_sha256": before_hash,
                    "uncompressed_bytes": before,
                    "compressed_bytes": target.stat().st_size,
                }
            )
    report = {
        "method": "gpt6_astra_xhigh",
        "compression": "gzip level 9, mtime 0, byte-for-byte decompression verified before source removal",
        "files": len(records),
        "uncompressed_bytes": sum(row["uncompressed_bytes"] for row in records),
        "compressed_bytes": sum(row["compressed_bytes"] for row in records),
        "records": records,
    }
    output = ROOT / "results/gpt6_astra_xhigh/text_log_compression.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(temporary, output)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "records"}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
