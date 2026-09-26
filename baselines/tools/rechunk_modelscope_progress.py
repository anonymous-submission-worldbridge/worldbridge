#!/usr/bin/env python3
"""Safely migrate ModelScope resume metadata to a smaller chunk size.

Only ranges already marked complete are mapped to the new grid. Unfinished
ranges remain pending and are overwritten by the downloader on resume.
"""

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
from pathlib import Path


BASELINES_ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_below_baselines(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def migrate(progress_path: Path, new_chunk_size: int) -> tuple[int, int]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    old_chunk_size = int(progress["chunk_size"])
    file_size = int(progress["size"])
    old_completed = {int(index) for index in progress.get("completed_chunks", [])}
    if old_chunk_size == new_chunk_size:
        return len(old_completed), len(old_completed)
    if new_chunk_size >= old_chunk_size or old_chunk_size % new_chunk_size:
        raise ValueError(
            "new chunk size must be a proper divisor of the old size: "
            f"old={old_chunk_size}, new={new_chunk_size}"
        )

    completed: set[int] = set()
    for old_index in old_completed:
        old_start = old_index * old_chunk_size
        if old_start >= file_size:
            raise ValueError(
                f"completed chunk {old_index} starts beyond file size {file_size}: "
                f"{progress_path}"
            )
        old_end = min(old_start + old_chunk_size, file_size)
        for start in range(old_start, old_end, new_chunk_size):
            completed.add(start // new_chunk_size)

    progress["chunk_size"] = new_chunk_size
    progress["completed_chunks"] = sorted(completed)
    atomic_json(progress_path, progress)
    return len(old_completed), len(completed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--chunk-size-mib", type=int, required=True)
    args = parser.parse_args()
    root = ensure_below_baselines(args.root)
    chunk_size = args.chunk_size_mib * 1024 * 1024
    paths = sorted(root.rglob("*.partial.json"))
    if not paths:
        raise RuntimeError(f"No resume metadata found below {root}")
    for path in paths:
        old_count, new_count = migrate(path, chunk_size)
        print(
            f"RECHUNKED {path.relative_to(BASELINES_ROOT)} "
            f"completed={old_count}->{new_count}",
            flush=True,
        )
    print(f"RECHUNK_COMPLETE files={len(paths)} chunk_size={chunk_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
