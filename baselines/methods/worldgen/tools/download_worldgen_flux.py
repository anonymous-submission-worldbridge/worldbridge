#!/usr/bin/env python3
"""Reliably resume the two large FLUX.1-dev files missing for WorldGen.

The server's HTTP proxy occasionally closes long Hugging Face transfers.  The
Hub client keeps a valid ``.incomplete`` prefix, so this helper retries only
the affected file and verifies its official SHA-256 after completion.
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
import re
import time
from pathlib import Path

import requests

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

from huggingface_hub import get_token, hf_hub_url  # noqa: E402
from huggingface_hub.utils import build_hf_headers  # noqa: E402


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_CACHE = BASELINES_ROOT / "checkpoints/WorldGen/huggingface/hub"
REPO_ID = "black-forest-labs/FLUX.1-dev"
REVISION = "3de623fc3c33e44ffbe2bad470d0f45bccf2eb21"
FILES = {
    "text_encoder_2/model-00001-of-00002.safetensors": {
        "size": 4_994_582_224,
        "sha256": "ec87bffd1923e8b2774a6d240c922a41f6143081d52cf83b8fe39e9d838c893e",
    },
    "transformer/diffusion_pytorch_model-00002-of-00003.safetensors": {
        "size": 9_949_328_904,
        "sha256": "5e830704a83aa938dfaf23da308100a1c44b83fa084283abf1d163ea727e5f7a",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def blob_paths(cache_dir: Path, digest: str) -> tuple[Path, Path]:
    root = cache_dir / "models--black-forest-labs--FLUX.1-dev" / "blobs"
    return root / digest, root / f"{digest}.incomplete"


def ensure_cache_pointer(cache_dir: Path, filename: str, complete: Path) -> None:
    storage = cache_dir / "models--black-forest-labs--FLUX.1-dev"
    reference = storage / "refs/main"
    reference.parent.mkdir(parents=True, exist_ok=True)
    if reference.exists() and reference.read_text(encoding="utf-8").strip() != REVISION:
        raise RuntimeError(f"Unexpected cached main revision in {reference}")
    if not reference.exists():
        reference.write_text(REVISION, encoding="utf-8")

    pointer = storage / "snapshots" / REVISION / filename
    pointer.parent.mkdir(parents=True, exist_ok=True)
    if pointer.is_symlink():
        if pointer.resolve() != complete.resolve():
            raise RuntimeError(
                f"Unexpected snapshot pointer: {pointer} -> {pointer.resolve()}"
            )
        return
    if pointer.exists():
        raise RuntimeError(f"Snapshot path is not a symlink: {pointer}")
    pointer.symlink_to(os.path.relpath(complete, pointer.parent))


def verify_complete(
    filename: str,
    complete: Path,
    expected_size: int,
    expected_hash: str,
    cache_dir: Path,
) -> Path:
    if complete.stat().st_size != expected_size:
        raise RuntimeError(
            f"Completed blob has wrong size: {complete.stat().st_size} != {expected_size}"
        )
    print(f"WORLDGEN_FLUX_HASHING file={filename} bytes={expected_size}", flush=True)
    actual_hash = sha256_file(complete)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Completed blob hash mismatch: {actual_hash} != {expected_hash}"
        )
    ensure_cache_pointer(cache_dir, filename, complete)
    print(f"WORLDGEN_FLUX_VERIFIED file={filename} sha256={actual_hash}", flush=True)
    return complete


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fetch_range(
    url: str,
    base_headers: dict[str, str],
    start: int,
    end: int,
    expected_size: int,
    max_attempts: int,
) -> bytes:
    expected_length = end - start + 1
    for attempt in range(1, max_attempts + 1):
        headers = dict(base_headers)
        headers.update({"Accept-Encoding": "identity", "Range": f"bytes={start}-{end}"})
        try:
            with requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=(20, 120),
            ) as response:
                response.raise_for_status()
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                if response.status_code != 206 or match is None:
                    raise RuntimeError(
                        f"Server did not honor byte range: status={response.status_code} "
                        f"content_range={content_range!r}"
                    )
                actual = tuple(map(int, match.groups()))
                if actual != (start, end, expected_size):
                    raise RuntimeError(f"Unexpected byte range response: {actual}")
                data = response.content
            if len(data) != expected_length:
                raise RuntimeError(
                    f"Range length mismatch: {len(data)} != {expected_length}"
                )
            return data
        except Exception as exc:
            print(
                f"WORLDGEN_FLUX_RANGE_RETRY range={start}-{end} "
                f"attempt={attempt}/{max_attempts} error={type(exc).__name__}: "
                f"{str(exc).splitlines()[-1][:300]}",
                flush=True,
            )
            if attempt == max_attempts:
                raise
            time.sleep(min(2 * attempt, 10))
    raise AssertionError("unreachable")


def resume_file(
    filename: str,
    metadata: dict[str, int | str],
    cache_dir: Path,
    max_attempts: int,
    chunk_mib: int,
    workers: int,
) -> Path:
    expected_size = int(metadata["size"])
    expected_hash = str(metadata["sha256"])
    complete, incomplete = blob_paths(cache_dir, expected_hash)
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    if complete.exists():
        return verify_complete(
            filename, complete, expected_size, expected_hash, cache_dir
        )

    token = get_token()
    if not token:
        raise RuntimeError("No Hugging Face token found below HF_HOME")
    url = hf_hub_url(REPO_ID, filename, revision=REVISION)
    base_headers = build_hf_headers(token=token)
    chunk_bytes = chunk_mib * 1024 * 1024
    state_path = incomplete.with_suffix(incomplete.suffix + ".ranges.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (
            state.get("filename") != filename
            or state.get("expected_size") != expected_size
            or state.get("sha256") != expected_hash
            or state.get("chunk_bytes") != chunk_bytes
        ):
            raise RuntimeError(
                f"Range state does not match current request: {state_path}"
            )
        prefix_size = int(state["prefix_size"])
        completed_ranges = set(state.get("completed_ranges", []))
        if incomplete.stat().st_size != expected_size:
            raise RuntimeError(
                f"Preallocated range target has wrong size: {incomplete}"
            )
    else:
        prefix_size = incomplete.stat().st_size if incomplete.exists() else 0
        if prefix_size > expected_size:
            raise RuntimeError(
                f"Incomplete blob exceeds expected size: {prefix_size} > {expected_size}"
            )
        with incomplete.open("ab") as handle:
            handle.truncate(expected_size)
        completed_ranges: set[str] = set()
        state = {
            "filename": filename,
            "expected_size": expected_size,
            "sha256": expected_hash,
            "prefix_size": prefix_size,
            "chunk_bytes": chunk_bytes,
            "completed_ranges": [],
        }
        atomic_json(state_path, state)

    all_ranges = [
        (start, min(start + chunk_bytes, expected_size) - 1)
        for start in range(prefix_size, expected_size, chunk_bytes)
    ]
    pending = [
        (start, end)
        for start, end in all_ranges
        if f"{start}-{end}" not in completed_ranges
    ]
    completed_bytes = prefix_size + sum(
        end - start + 1
        for start, end in all_ranges
        if f"{start}-{end}" in completed_ranges
    )
    print(
        f"WORLDGEN_FLUX_PARALLEL file={filename} workers={workers} "
        f"prefix_bytes={prefix_size} completed_bytes={completed_bytes}/{expected_size} "
        f"pending_ranges={len(pending)}",
        flush=True,
    )

    descriptor = os.open(incomplete, os.O_RDWR)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    fetch_range,
                    url,
                    base_headers,
                    start,
                    end,
                    expected_size,
                    max_attempts,
                ): (start, end)
                for start, end in pending
            }
            for future in concurrent.futures.as_completed(futures):
                start, end = futures[future]
                data = future.result()
                written = os.pwrite(descriptor, data, start)
                if written != len(data):
                    raise RuntimeError(
                        f"Short pwrite for range {start}-{end}: {written}"
                    )
                key = f"{start}-{end}"
                completed_ranges.add(key)
                state["completed_ranges"] = sorted(completed_ranges)
                atomic_json(state_path, state)
                completed_bytes += len(data)
                print(
                    f"WORLDGEN_FLUX_RANGE_COMPLETE file={filename} range={key} "
                    f"bytes={completed_bytes}/{expected_size} "
                    f"percent={100.0 * completed_bytes / expected_size:.2f}",
                    flush=True,
                )
    finally:
        os.close(descriptor)

    if len(completed_ranges) != len(all_ranges):
        raise RuntimeError(
            f"Range count mismatch: {len(completed_ranges)} != {len(all_ranges)}"
        )
    print(f"WORLDGEN_FLUX_HASHING file={filename} bytes={expected_size}", flush=True)
    actual_hash = sha256_file(incomplete)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Assembled blob hash mismatch: {actual_hash} != {expected_hash}"
        )
    incomplete.replace(complete)
    ensure_cache_pointer(cache_dir, filename, complete)
    state_path.unlink()
    print(f"WORLDGEN_FLUX_VERIFIED file={filename} sha256={actual_hash}", flush=True)
    return complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--max-attempts", type=int, default=200)
    parser.add_argument("--chunk-mib", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    cache_dir = args.cache_dir.resolve()
    cache_dir.relative_to(BASELINES_ROOT.resolve())
    if args.workers < 1 or args.workers > 16:
        raise ValueError("workers must be in [1, 16]")
    for filename, metadata in FILES.items():
        resume_file(
            filename,
            metadata,
            cache_dir,
            args.max_attempts,
            args.chunk_mib,
            args.workers,
        )
    print("WORLDGEN_FLUX_DOWNLOAD_COMPLETE files=2", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
