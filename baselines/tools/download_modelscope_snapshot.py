#!/usr/bin/env python3
"""Download a hash-pinned ModelScope snapshot with resumable byte ranges.

The downloader is intentionally dependency-free.  Large files are fetched in
parallel byte ranges, written with ``pwrite`` into a sparse temporary file, and
renamed only after their published SHA-256 has been verified.
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
import subprocess
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASELINES_ROOT = Path(__file__).resolve().parents[1]


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


def build_manifest(repo: str, revision: str, prefix: str) -> dict[str, Any]:
    encoded_repo = "/".join(
        urllib.parse.quote(part, safe="") for part in repo.split("/")
    )
    query = urllib.parse.urlencode({"Revision": revision, "Recursive": "true"})
    api_url = f"https://modelscope.cn/api/v1/models/{encoded_repo}/repo/files?{query}"
    payload = fetch_json(api_url)
    if payload.get("Code") != 200:
        raise RuntimeError(f"ModelScope API error: {payload.get('Message', payload)}")
    files = []
    for item in payload["Data"]["Files"]:
        if item.get("Type") != "blob" or not item["Path"].startswith(prefix):
            continue
        if not item.get("Sha256") or int(item.get("Size", 0)) < 0:
            raise RuntimeError(f"Missing size/hash for {item['Path']}")
        files.append(
            {
                "path": item["Path"],
                "size": int(item["Size"]),
                "sha256": item["Sha256"],
            }
        )
    files.sort(key=lambda row: row["path"])
    if not files:
        raise RuntimeError(f"No files matched prefix {prefix!r}")
    return {
        "transport": "ModelScope official mirror",
        "repo": repo,
        "revision": revision,
        "prefix": prefix,
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
        self.output_root = output_root
        self.temp_root = temp_root
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

    def initialize_file(self, record: dict[str, Any]) -> bool:
        relative_path = record["path"]
        output = self.output_path(relative_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            if (
                output.stat().st_size == record["size"]
                and sha256_file(output) == record["sha256"]
            ):
                self.completed[relative_path] = set(
                    range((record["size"] + self.chunk_size - 1) // self.chunk_size)
                )
                print(f"ALREADY_VERIFIED {relative_path}", flush=True)
                return True
            raise RuntimeError(f"Existing output has the wrong size/hash: {output}")

        partial = self.partial_path(relative_path)
        progress_path = self.progress_path(relative_path)
        expected = {
            "path": relative_path,
            "size": record["size"],
            "sha256": record["sha256"],
            "chunk_size": self.chunk_size,
        }
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


def download_chunk(
    chunk: Chunk,
    state: DownloadState,
    repo: str,
    revision: str,
) -> tuple[str, int, int]:
    quoted_repo = "/".join(
        urllib.parse.quote(part, safe="") for part in repo.split("/")
    )
    quoted_path = urllib.parse.quote(chunk.relative_path, safe="/")
    url = f"https://modelscope.cn/models/{quoted_repo}/resolve/{urllib.parse.quote(revision, safe='')}/{quoted_path}"
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
            "12",
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
    whole_file = chunk.start == 0 and chunk.size == chunk.file_size
    if status != "206" and not (status == "200" and whole_file):
        raise RuntimeError(
            f"Server ignored range for {chunk.relative_path} chunk {chunk.index}: HTTP {status}"
        )
    actual_size = temporary.stat().st_size
    if actual_size != chunk.size:
        raise RuntimeError(
            f"Wrong chunk size for {chunk.relative_path} chunk {chunk.index}: "
            f"{actual_size} != {chunk.size}"
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
    relative_path = record["path"]
    output = state.output_path(relative_path)
    if output.exists():
        return
    chunk_count = (record["size"] + state.chunk_size - 1) // state.chunk_size
    if state.completed.get(relative_path, set()) != set(range(chunk_count)):
        raise RuntimeError(f"Not every chunk completed for {relative_path}")
    partial = state.partial_path(relative_path)
    actual_hash = sha256_file(partial)
    if actual_hash != record["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {relative_path}: {actual_hash} != {record['sha256']}"
        )
    partial.replace(output)
    state.progress_path(relative_path).unlink(missing_ok=True)
    print(f"FILE_VERIFIED {relative_path} bytes={record['size']}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", default="master")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--temp-root", type=Path, default=BASELINES_ROOT / "tmp/modelscope_download"
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-size-mib", type=int, default=256)
    parser.add_argument("--expected-files", type=int)
    parser.add_argument("--expected-bytes", type=int)
    args = parser.parse_args()
    if args.workers < 1 or args.chunk_size_mib < 1:
        raise ValueError("workers and chunk-size-mib must be positive")

    if args.manifest.exists():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        for key, value in (
            ("repo", args.repo),
            ("revision", args.revision),
            ("prefix", args.prefix),
        ):
            if manifest.get(key) != value:
                raise RuntimeError(f"Frozen manifest mismatch for {key}")
    else:
        manifest = build_manifest(args.repo, args.revision, args.prefix)
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
    tasks: list[Chunk] = []
    verified = set()
    for record in manifest["files"]:
        if state.initialize_file(record):
            verified.add(record["path"])
            continue
        for index, start in enumerate(range(0, record["size"], chunk_size)):
            if index in state.completed[record["path"]]:
                continue
            tasks.append(
                Chunk(
                    relative_path=record["path"],
                    file_size=record["size"],
                    file_sha256=record["sha256"],
                    index=index,
                    start=start,
                    end=min(start + chunk_size, record["size"]) - 1,
                )
            )

    downloaded = 0
    total_pending = sum(chunk.size for chunk in tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(download_chunk, chunk, state, args.repo, args.revision)
            for chunk in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            relative_path, index, size = future.result()
            downloaded += size
            print(
                f"CHUNK_OK {relative_path} chunk={index} "
                f"progress={downloaded}/{total_pending}",
                flush=True,
            )

    for record in manifest["files"]:
        finalize_file(record, state)
    print(
        f"SNAPSHOT_VERIFIED files={manifest['file_count']} "
        f"bytes={manifest['total_bytes']} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
