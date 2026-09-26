#!/usr/bin/env python3
"""Download one hash-pinned Hugging Face file in resumable HTTP ranges."""

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
import concurrent.futures
import hashlib
import json
import os
import subprocess
import threading
import urllib.parse
from pathlib import Path


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-size-mib", type=int, default=256)
    parser.add_argument("--temp-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output.is_file():
        if (
            args.output.stat().st_size == args.size
            and sha256_file(args.output) == args.sha256
        ):
            print(f"ALREADY_VERIFIED {args.output}")
            return 0
        raise RuntimeError(f"Existing output has wrong size/hash: {args.output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.temp_root.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.name + ".range.partial")
    progress_path = args.output.with_name(args.output.name + ".range.partial.json")
    chunk_size = args.chunk_size_mib * 1024 * 1024
    chunk_count = (args.size + chunk_size - 1) // chunk_size
    expected = {
        "transport": "hf-mirror HTTP byte ranges without proxy",
        "repo": args.repo,
        "revision": args.revision,
        "path": args.path,
        "size": args.size,
        "sha256": args.sha256,
        "chunk_size": chunk_size,
    }
    completed_chunks: set[int] = set()
    if progress_path.exists():
        progress = json.loads(progress_path.read_text())
        for key, value in expected.items():
            if progress.get(key) != value:
                raise RuntimeError(f"Resume metadata mismatch: {key}")
        completed_chunks = {
            int(index) for index in progress.get("completed_chunks", [])
        }
    if partial.exists() and partial.stat().st_size != args.size:
        raise RuntimeError(f"Partial file has wrong size: {partial}")
    if not partial.exists():
        with partial.open("wb") as handle:
            handle.truncate(args.size)
        atomic_json(progress_path, {**expected, "completed_chunks": []})

    quoted_repo = "/".join(
        urllib.parse.quote(item, safe="") for item in args.repo.split("/")
    )
    quoted_path = urllib.parse.quote(args.path, safe="/")
    url = f"https://hf-mirror.com/{quoted_repo}/resolve/{urllib.parse.quote(args.revision, safe='')}/{quoted_path}"
    lock = threading.Lock()

    def download(index: int) -> tuple[int, int]:
        start = index * chunk_size
        end = min(args.size, start + chunk_size) - 1
        temporary = args.temp_root / f"{args.sha256}.{index:06d}.{start}-{end}.part"
        command = [
            "curl",
            "--noproxy",
            "*",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "12",
            "--retry-all-errors",
            "--connect-timeout",
            "30",
            "--max-time",
            "1800",
            "--range",
            f"{start}-{end}",
            "--output",
            str(temporary),
            "--write-out",
            "%{http_code}",
            url,
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError(f"curl chunk {index} failed: {result.stderr[-1000:]}")
        status = result.stdout.strip()[-3:]
        if status != "206":
            raise RuntimeError(f"Server ignored range for chunk {index}: HTTP {status}")
        expected_size = end - start + 1
        if temporary.stat().st_size != expected_size:
            raise RuntimeError(
                f"Wrong size for chunk {index}: {temporary.stat().st_size} != {expected_size}"
            )
        descriptor = os.open(partial, os.O_WRONLY)
        try:
            with temporary.open("rb") as source:
                offset = start
                while block := source.read(16 * 1024 * 1024):
                    written = os.pwrite(descriptor, block, offset)
                    if written != len(block):
                        raise OSError(f"Short pwrite for chunk {index}")
                    offset += written
        finally:
            os.close(descriptor)
        temporary.unlink()
        with lock:
            completed_chunks.add(index)
            atomic_json(
                progress_path,
                {**expected, "completed_chunks": sorted(completed_chunks)},
            )
        return index, expected_size

    pending = [index for index in range(chunk_count) if index not in completed_chunks]
    downloaded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(download, index) for index in pending]
        for future in concurrent.futures.as_completed(futures):
            index, size = future.result()
            downloaded += size
            print(
                f"CHUNK_OK {args.path} chunk={index} progress={downloaded}/"
                f"{sum(min(chunk_size, args.size - i * chunk_size) for i in pending)}",
                flush=True,
            )
    if completed_chunks != set(range(chunk_count)):
        raise RuntimeError("Not all chunks completed")
    actual_hash = sha256_file(partial)
    if actual_hash != args.sha256:
        raise RuntimeError(f"SHA-256 mismatch: {actual_hash} != {args.sha256}")
    partial.replace(args.output)
    progress_path.unlink()
    print(f"FILE_VERIFIED {args.path} bytes={args.size} sha256={actual_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
