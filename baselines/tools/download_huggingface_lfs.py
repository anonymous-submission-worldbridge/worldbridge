#!/usr/bin/env python3
"""Download selected, hash-pinned Hugging Face LFS files with byte-range resume.

Unlike ``snapshot_download``, this helper can recover complete logical chunks
from an older sparse ``.incomplete`` file.  A recovered chunk is trusted only
as a download candidate; the published LFS SHA-256 is still checked across the
entire assembled file before the final atomic rename.
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
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASELINES_ROOT = Path(__file__).resolve().parents[1]


def below_baselines(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path, block_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def fetch_json(url: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "8",
            "--retry-all-errors",
            "--connect-timeout",
            "30",
            url,
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


def build_manifest(repo: str, revision: str, paths: list[str]) -> dict[str, Any]:
    encoded_repo = "/".join(
        urllib.parse.quote(part, safe="") for part in repo.split("/")
    )
    encoded_revision = urllib.parse.quote(revision, safe="")
    payload = fetch_json(
        f"https://huggingface.co/api/models/{encoded_repo}/revision/"
        f"{encoded_revision}?blobs=true"
    )
    if payload.get("sha") != revision:
        raise RuntimeError(
            f"Hugging Face revision mismatch: {payload.get('sha')} != {revision}"
        )
    by_path = {row["rfilename"]: row for row in payload.get("siblings", [])}
    files = []
    for path in paths:
        row = by_path.get(path)
        if row is None:
            raise RuntimeError(f"Path is absent from pinned revision: {path}")
        lfs = row.get("lfs") or {}
        sha256 = lfs.get("sha256")
        size = row.get("size")
        if not sha256 or size is None:
            raise RuntimeError(
                f"Selected path is not hash-addressed LFS content: {path}"
            )
        files.append({"path": path, "size": int(size), "sha256": sha256})
    return {
        "transport": "Hugging Face LFS byte ranges",
        "repo": repo,
        "revision": revision,
        "paths": paths,
        "file_count": len(files),
        "total_bytes": sum(row["size"] for row in files),
        "files": files,
    }


@dataclass(frozen=True)
class Chunk:
    relative_path: str
    file_size: int
    file_sha256: str
    index: int
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start + 1


class DownloadState:
    def __init__(self, output_root: Path, temp_root: Path, chunk_size: int) -> None:
        self.output_root = below_baselines(output_root)
        self.temp_root = below_baselines(temp_root)
        self.chunk_size = chunk_size
        self.lock = threading.Lock()
        self.completed: dict[str, set[int]] = {}

    def output_path(self, relative_path: str) -> Path:
        return self.output_root / relative_path

    def partial_path(self, relative_path: str) -> Path:
        output = self.output_path(relative_path)
        return output.with_name(output.name + ".partial")

    def progress_path(self, relative_path: str) -> Path:
        output = self.output_path(relative_path)
        return output.with_name(output.name + ".partial.json")

    def expected_progress(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": record["path"],
            "size": record["size"],
            "sha256": record["sha256"],
            "chunk_size": self.chunk_size,
        }

    def initialize_file(self, record: dict[str, Any]) -> bool:
        relative_path = record["path"]
        output = self.output_path(relative_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        chunk_count = (record["size"] + self.chunk_size - 1) // self.chunk_size
        if output.exists():
            if (
                output.stat().st_size == record["size"]
                and sha256_file(output) == record["sha256"]
            ):
                self.completed[relative_path] = set(range(chunk_count))
                print(f"ALREADY_VERIFIED {relative_path}", flush=True)
                return True
            raise RuntimeError(f"Existing output has the wrong size/hash: {output}")

        partial = self.partial_path(relative_path)
        progress_path = self.progress_path(relative_path)
        expected = self.expected_progress(record)
        completed: set[int] = set()
        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            for key, value in expected.items():
                if progress.get(key) != value:
                    raise RuntimeError(
                        f"Resume metadata mismatch for {relative_path}: {key}"
                    )
            completed = {int(index) for index in progress.get("completed_chunks", [])}
        if partial.exists() and partial.stat().st_size != record["size"]:
            raise RuntimeError(f"Partial file has the wrong size: {partial}")
        if not partial.exists():
            with partial.open("wb") as handle:
                handle.truncate(record["size"])
            atomic_json(progress_path, {**expected, "completed_chunks": []})
        self.completed[relative_path] = completed
        return False

    def mark_complete(self, chunk: Chunk) -> None:
        with self.lock:
            done = self.completed[chunk.relative_path]
            done.add(chunk.index)
            atomic_json(
                self.progress_path(chunk.relative_path),
                {
                    "path": chunk.relative_path,
                    "size": chunk.file_size,
                    "sha256": chunk.file_sha256,
                    "chunk_size": self.chunk_size,
                    "completed_chunks": sorted(done),
                },
            )


def fully_allocated_chunks(path: Path, size: int, chunk_size: int) -> set[int]:
    """Return chunks containing no filesystem holes in their logical range."""
    completed = set()
    descriptor = os.open(path, os.O_RDONLY)
    try:
        for index, start in enumerate(range(0, size, chunk_size)):
            end = min(start + chunk_size, size)
            try:
                data = os.lseek(descriptor, start, os.SEEK_DATA)
            except OSError:
                continue
            if data > start:
                continue
            try:
                hole = os.lseek(descriptor, start, os.SEEK_HOLE)
            except OSError:
                continue
            if hole >= end:
                completed.add(index)
    finally:
        os.close(descriptor)
    return completed


def seed_sparse_file(
    state: DownloadState, record: dict[str, Any], source: Path
) -> None:
    source = below_baselines(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    target = state.partial_path(record["path"])
    progress = state.progress_path(record["path"])
    if target.exists() or progress.exists():
        raise RuntimeError(f"Refusing to seed over existing resume state: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cp", "--reflink=auto", "--sparse=always", str(source), str(target)],
        check=True,
    )
    with target.open("r+b") as handle:
        handle.truncate(record["size"])
    completed = fully_allocated_chunks(target, record["size"], state.chunk_size)
    atomic_json(
        progress,
        {**state.expected_progress(record), "completed_chunks": sorted(completed)},
    )
    recovered = sum(
        min(state.chunk_size, record["size"] - index * state.chunk_size)
        for index in completed
    )
    print(
        f"SPARSE_SEED_RECOVERED {record['path']} chunks={len(completed)} bytes={recovered}",
        flush=True,
    )


def download_chunk(
    chunk: Chunk, state: DownloadState, repo: str, revision: str, endpoint: str
) -> tuple[str, int, int]:
    quoted_repo = "/".join(
        urllib.parse.quote(part, safe="") for part in repo.split("/")
    )
    quoted_path = urllib.parse.quote(chunk.relative_path, safe="/")
    url = (
        f"{endpoint.rstrip('/')}/{quoted_repo}/resolve/"
        f"{urllib.parse.quote(revision, safe='')}/{quoted_path}"
    )
    chunk_dir = state.temp_root / chunk.file_sha256
    chunk_dir.mkdir(parents=True, exist_ok=True)
    temporary = chunk_dir / f"{chunk.index:06d}.{chunk.start}-{chunk.end}.part"
    completed = subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "20",
            "--retry-all-errors",
            "--connect-timeout",
            "30",
            "--max-time",
            "1800",
            "--range",
            f"{chunk.start}-{chunk.end}",
            "--output",
            str(temporary),
            "--write-out",
            "%{http_code}",
            url,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"curl failed for {chunk.relative_path} chunk {chunk.index}: "
            f"{completed.stderr[-1000:]}"
        )
    status = completed.stdout.strip()[-3:]
    if status != "206":
        raise RuntimeError(
            f"Server ignored range for {chunk.relative_path} chunk {chunk.index}: HTTP {status}"
        )
    if temporary.stat().st_size != chunk.size:
        raise RuntimeError(
            f"Wrong chunk size for {chunk.relative_path} chunk {chunk.index}: "
            f"{temporary.stat().st_size} != {chunk.size}"
        )
    descriptor = os.open(state.partial_path(chunk.relative_path), os.O_WRONLY)
    try:
        with temporary.open("rb") as source:
            offset = chunk.start
            while block := source.read(16 * 1024 * 1024):
                written = os.pwrite(descriptor, block, offset)
                if written != len(block):
                    raise OSError(f"Short pwrite: {written} != {len(block)}")
                offset += written
    finally:
        os.close(descriptor)
    temporary.unlink()
    state.mark_complete(chunk)
    return chunk.relative_path, chunk.index, chunk.size


def finalize_file(record: dict[str, Any], state: DownloadState) -> None:
    output = state.output_path(record["path"])
    if output.exists():
        return
    count = (record["size"] + state.chunk_size - 1) // state.chunk_size
    if state.completed[record["path"]] != set(range(count)):
        raise RuntimeError(f"Not every chunk completed for {record['path']}")
    partial = state.partial_path(record["path"])
    actual = sha256_file(partial)
    if actual != record["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {record['path']}: {actual} != {record['sha256']}"
        )
    partial.replace(output)
    state.progress_path(record["path"]).unlink(missing_ok=True)
    print(f"FILE_VERIFIED {record['path']} bytes={record['size']}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--path", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--chunk-size-mib", type=int, default=16)
    parser.add_argument("--seed-sparse", type=Path)
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument("--expected-files", type=int)
    parser.add_argument("--expected-bytes", type=int)
    args = parser.parse_args()
    if args.workers < 1 or args.chunk_size_mib < 1:
        raise ValueError("workers and chunk-size-mib must be positive")
    below_baselines(args.output)
    below_baselines(args.manifest)
    below_baselines(args.temp_root)

    if args.manifest.exists():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        for key, value in (
            ("repo", args.repo),
            ("revision", args.revision),
            ("paths", args.path),
        ):
            if manifest.get(key) != value:
                raise RuntimeError(f"Frozen manifest mismatch for {key}")
    else:
        manifest = build_manifest(args.repo, args.revision, args.path)
        atomic_json(args.manifest, manifest)
    if (
        args.expected_files is not None
        and manifest["file_count"] != args.expected_files
    ):
        raise RuntimeError(
            f"Expected {args.expected_files} files, manifest has {manifest['file_count']}"
        )
    if (
        args.expected_bytes is not None
        and manifest["total_bytes"] != args.expected_bytes
    ):
        raise RuntimeError(
            f"Expected {args.expected_bytes} bytes, manifest has {manifest['total_bytes']}"
        )

    chunk_size = args.chunk_size_mib * 1024 * 1024
    state = DownloadState(args.output, args.temp_root, chunk_size)
    if args.seed_sparse:
        if len(manifest["files"]) != 1:
            raise ValueError("--seed-sparse requires exactly one selected file")
        seed_sparse_file(state, manifest["files"][0], args.seed_sparse)

    tasks = []
    verified = set()
    for record in manifest["files"]:
        if state.initialize_file(record):
            verified.add(record["path"])
            continue
        done = state.completed[record["path"]]
        for index, start in enumerate(range(0, record["size"], chunk_size)):
            if index not in done:
                tasks.append(
                    Chunk(
                        record["path"],
                        record["size"],
                        record["sha256"],
                        index,
                        start,
                        min(start + chunk_size, record["size"]) - 1,
                    )
                )
    total_pending = sum(chunk.size for chunk in tasks)
    downloaded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                download_chunk, chunk, state, args.repo, args.revision, args.endpoint
            )
            for chunk in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            relative_path, index, size = future.result()
            downloaded += size
            print(
                f"CHUNK_OK {relative_path} chunk={index} progress={downloaded}/{total_pending}",
                flush=True,
            )
    for record in manifest["files"]:
        finalize_file(record, state)
    print(
        f"SNAPSHOT_VERIFIED files={manifest['file_count']} bytes={manifest['total_bytes']} "
        f"output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
