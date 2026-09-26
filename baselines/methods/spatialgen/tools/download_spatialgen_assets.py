#!/usr/bin/env python3
"""Resume the three large SpatialGen assets with verified HTTP ranges.

The ordinary Hub downloader uses one long transfer per file on this server.
The proxy frequently stalls those transfers.  This helper preserves each
existing contiguous prefix, downloads only missing byte ranges in parallel,
and publishes a file only after its official SHA-256 matches.
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
from huggingface_hub import get_token, hf_hub_url
from huggingface_hub.utils import build_hf_headers


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ASSET_ROOT = BASELINES_ROOT / "spatialgen_assets"

FILES = {
    "lora": {
        "repo_id": "manycore-research/FLUX.1-Wireframe-dev-lora",
        "revision": "c10a28639d1bb554966bde3e8e9706f544bec558",
        "filename": "lora.safetensors",
        "size": 1_047_692_320,
        "sha256": "46a2884893fd7661c29bab06b68eb21f87eb240dc7145b314e9fa73c54a933c7",
        "local_root": ASSET_ROOT / "flux_wireframe_lora",
        "incomplete": ASSET_ROOT / "flux_wireframe_lora/.cache/huggingface/download/"
        "Sty1dvVrrZUCiecbhe23HDkh6nU=.46a2884893fd7661c29bab06b68eb21f87eb240dc7145b314e9fa73c54a933c7.incomplete",
    },
    "spatialgen_text_encoder": {
        "repo_id": "manycore-research/SpatialGen-1.0",
        "revision": "6c8c2d1c72ad6bf3c5a3440697c9767f4dceaec0",
        "filename": "text_encoder/model.safetensors",
        "size": 680_820_392,
        "sha256": "bc1827c465450322616f06dea41596eac7d493f4e95904dcb51f0fc745c4e13f",
        "local_root": ASSET_ROOT / "spatialgen_ckpts",
        "incomplete": ASSET_ROOT
        / "spatialgen_ckpts/.cache/huggingface/download/text_encoder/"
        "xGOKKLRSlIhH692hSVvI1-gpoa8=.bc1827c465450322616f06dea41596eac7d493f4e95904dcb51f0fc745c4e13f.incomplete",
    },
    "spatialgen_unet": {
        "repo_id": "manycore-research/SpatialGen-1.0",
        "revision": "6c8c2d1c72ad6bf3c5a3440697c9767f4dceaec0",
        "filename": "unet/diffusion_pytorch_model.safetensors",
        "size": 1_834_542_936,
        "sha256": "3ba49c80ed2b92db8afddaa4528da0df3eec6c6535e7be0f053b896fd308de8e",
        "local_root": ASSET_ROOT / "spatialgen_ckpts",
        "incomplete": ASSET_ROOT / "spatialgen_ckpts/.cache/huggingface/download/unet/"
        "4SfAgk9U607e8pVunEB9nSiU10k=.3ba49c80ed2b92db8afddaa4528da0df3eec6c6535e7be0f053b896fd308de8e.incomplete",
    },
}


def assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
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
                url, headers=headers, allow_redirects=True, timeout=(20, 180)
            ) as response:
                response.raise_for_status()
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                if response.status_code != 206 or match is None:
                    raise RuntimeError(
                        f"range not honored: status={response.status_code} "
                        f"content_range={content_range!r}"
                    )
                actual = tuple(map(int, match.groups()))
                if actual != (start, end, expected_size):
                    raise RuntimeError(f"unexpected range response: {actual}")
                data = response.content
            if len(data) != expected_length:
                raise RuntimeError(f"range length {len(data)} != {expected_length}")
            return data
        except Exception as exc:
            print(
                f"SPATIALGEN_ASSET_RANGE_RETRY range={start}-{end} "
                f"attempt={attempt}/{max_attempts} error={type(exc).__name__}: "
                f"{str(exc).splitlines()[-1][:240]}",
                flush=True,
            )
            if attempt == max_attempts:
                raise
            time.sleep(min(2 * attempt, 20))
    raise AssertionError("unreachable")


def write_local_metadata(entry: dict[str, object]) -> None:
    local_root = Path(entry["local_root"])
    filename = str(entry["filename"])
    metadata = local_root / ".cache/huggingface/download" / f"{filename}.metadata"
    assert_baselines_path(metadata)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    temporary = metadata.with_suffix(metadata.suffix + ".tmp")
    temporary.write_text(
        f"{entry['revision']}\n{entry['sha256']}\n{time.time()}\n",
        encoding="utf-8",
    )
    temporary.replace(metadata)


def resume_asset(
    key: str,
    entry: dict[str, object],
    workers: int,
    chunk_mib: int,
    max_attempts: int,
) -> None:
    local_root = Path(entry["local_root"])
    filename = str(entry["filename"])
    expected_size = int(entry["size"])
    expected_hash = str(entry["sha256"])
    incomplete = Path(entry["incomplete"])
    target = local_root / filename
    for path in (local_root, incomplete, target):
        assert_baselines_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    incomplete.parent.mkdir(parents=True, exist_ok=True)

    if target.is_file() and target.stat().st_size == expected_size:
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            raise RuntimeError(f"existing {key} hash mismatch: {actual_hash}")
        write_local_metadata(entry)
        print(f"SPATIALGEN_ASSET_SKIP key={key} sha256={actual_hash}", flush=True)
        return

    prefix_size = incomplete.stat().st_size if incomplete.exists() else 0
    if prefix_size > expected_size:
        raise RuntimeError(f"{key} prefix exceeds official size")
    chunk_bytes = chunk_mib * 1024 * 1024
    state_path = incomplete.with_suffix(incomplete.suffix + ".ranges.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if any(
            (
                state.get("key") != key,
                state.get("expected_size") != expected_size,
                state.get("sha256") != expected_hash,
                incomplete.stat().st_size != expected_size,
            )
        ):
            raise RuntimeError(f"stale range state: {state_path}")
        prefix_size = int(state["prefix_size"])
        stored_chunk_bytes = int(state["chunk_bytes"])
        stored_completed_ranges = set(state.get("completed_ranges", []))
    else:
        with incomplete.open("ab") as handle:
            handle.truncate(expected_size)
        completed_ranges: set[str] = set()
        state = {
            "key": key,
            "expected_size": expected_size,
            "sha256": expected_hash,
            "prefix_size": prefix_size,
            "chunk_bytes": chunk_bytes,
            "completed_ranges": [],
        }
        atomic_json(state_path, state)
        stored_chunk_bytes = chunk_bytes
        stored_completed_ranges = set()

    ranges = [
        (start, min(start + chunk_bytes, expected_size) - 1)
        for start in range(prefix_size, expected_size, chunk_bytes)
    ]
    if stored_chunk_bytes == chunk_bytes:
        completed_ranges = stored_completed_ranges
    else:
        completed_intervals = [
            tuple(map(int, item.split("-", 1))) for item in stored_completed_ranges
        ]
        completed_ranges = {
            f"{start}-{end}"
            for start, end in ranges
            if any(
                stored_start <= start and end <= stored_end
                for stored_start, stored_end in completed_intervals
            )
        }
        state["chunk_bytes"] = chunk_bytes
        state["completed_ranges"] = sorted(completed_ranges)
        atomic_json(state_path, state)
        print(
            f"SPATIALGEN_ASSET_RECHUNK key={key} "
            f"old_chunk={stored_chunk_bytes} new_chunk={chunk_bytes} "
            f"preserved_ranges={len(completed_ranges)}",
            flush=True,
        )
    pending = [
        item for item in ranges if f"{item[0]}-{item[1]}" not in completed_ranges
    ]
    completed_bytes = prefix_size + sum(
        end - start + 1 for start, end in ranges if f"{start}-{end}" in completed_ranges
    )
    print(
        f"SPATIALGEN_ASSET_START key={key} workers={workers} "
        f"prefix={prefix_size} completed={completed_bytes}/{expected_size} "
        f"pending_ranges={len(pending)}",
        flush=True,
    )
    url = hf_hub_url(str(entry["repo_id"]), filename, revision=str(entry["revision"]))
    headers = build_hf_headers(token=get_token())
    descriptor = os.open(incomplete, os.O_RDWR)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    fetch_range,
                    url,
                    headers,
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
                    raise RuntimeError(f"short pwrite for {start}-{end}")
                completed_ranges.add(f"{start}-{end}")
                state["completed_ranges"] = sorted(completed_ranges)
                atomic_json(state_path, state)
                completed_bytes += len(data)
                print(
                    f"SPATIALGEN_ASSET_PROGRESS key={key} "
                    f"bytes={completed_bytes}/{expected_size} "
                    f"percent={100.0 * completed_bytes / expected_size:.2f}",
                    flush=True,
                )
    finally:
        os.close(descriptor)

    if len(completed_ranges) != len(ranges):
        raise RuntimeError(f"incomplete range set for {key}")
    print(f"SPATIALGEN_ASSET_HASHING key={key}", flush=True)
    actual_hash = sha256_file(incomplete)
    if actual_hash != expected_hash:
        raise RuntimeError(f"assembled {key} hash mismatch: {actual_hash}")
    incomplete.replace(target)
    state_path.unlink()
    write_local_metadata(entry)
    print(
        f"SPATIALGEN_ASSET_COMPLETE key={key} bytes={expected_size} "
        f"sha256={actual_hash}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets", nargs="+", choices=tuple(FILES), default=list(FILES)
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-mib", type=int, default=16)
    parser.add_argument("--max-attempts", type=int, default=200)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must be in [1, 16]")
    for key in args.assets:
        resume_asset(key, FILES[key], args.workers, args.chunk_mib, args.max_attempts)
    print(f"SPATIALGEN_ASSETS_READY count={len(args.assets)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
