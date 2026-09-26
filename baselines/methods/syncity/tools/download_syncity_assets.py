#!/usr/bin/env python3
"""Stage the pinned Hugging Face assets required by SynCity 3000.

The script intentionally writes only below ``baselines/checkpoints/syncity3k``
and records resolved revisions and file metadata before downloading.
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
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
CHECKPOINT_ROOT = BASELINES_ROOT / "checkpoints/syncity3k"
HF_HOME = CHECKPOINT_ROOT / "huggingface"
MANIFEST = CHECKPOINT_ROOT / "huggingface_assets.json"
REPOSITORIES = (
    "alimama-creative/FLUX.1-dev-Controlnet-Inpainting-Beta",
    "microsoft/TRELLIS-image-large",
    "paulengstler/syncity-3k",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_safe_root() -> None:
    CHECKPOINT_ROOT.resolve().relative_to(BASELINES_ROOT.resolve())


def inspect_repositories() -> dict:
    api = HfApi()
    repositories = []
    for repo_id in REPOSITORIES:
        info = api.model_info(repo_id, files_metadata=True)
        files = []
        for sibling in info.siblings or ():
            files.append(
                {
                    "path": sibling.rfilename,
                    "size": sibling.size,
                    "blob_id": sibling.blob_id,
                    "lfs_sha256": (sibling.lfs.get("sha256") if sibling.lfs else None),
                }
            )
        repositories.append(
            {
                "repo_id": repo_id,
                "revision": info.sha,
                "total_bytes": sum(item["size"] or 0 for item in files),
                "files": files,
            }
        )
    return {
        "created_at_utc": utc_now(),
        "cache_root": str(HF_HOME / "hub"),
        "repositories": repositories,
    }


def atomic_write(payload: dict) -> None:
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(MANIFEST)


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    if algorithm == "sha1":
        digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified(path: Path, file_entry: dict) -> bool:
    if not path.is_file() or path.stat().st_size != file_entry["size"]:
        return False
    expected_sha256 = file_entry.get("lfs_sha256")
    if expected_sha256:
        return file_digest(path, "sha256") == expected_sha256
    expected_blob = file_entry.get("blob_id")
    return not expected_blob or file_digest(path, "sha1") == expected_blob


def aria2_download(entry: dict, file_entry: dict) -> str:
    repo_dir = "models--" + entry["repo_id"].replace("/", "--")
    repo_root = HF_HOME / "hub" / repo_dir
    snapshot_root = repo_root / "snapshots" / entry["revision"]
    target = snapshot_root / file_entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if not verified(target, file_entry):
        endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
        url = (
            f"{endpoint}/{entry['repo_id']}/resolve/{entry['revision']}/"
            f"{file_entry['path']}"
        )
        command = [
            "aria2c",
            "--continue=true",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--file-allocation=none",
            "--max-tries=30",
            "--retry-wait=5",
            "--connect-timeout=30",
            "--timeout=120",
            "--max-connection-per-server=4",
            "--split=4",
            "--min-split-size=32M",
            f"--dir={target.parent}",
            f"--out={target.name}",
            url,
        ]
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"aria2c exited {completed.returncode} for {entry['repo_id']}:"
                f"{file_entry['path']}"
            )
        if not verified(target, file_entry):
            raise RuntimeError(f"Checksum or size mismatch after download: {target}")
    refs = repo_root / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    # Hugging Face cache refs contain the raw 40-byte commit (no newline).
    (refs / "main").write_text(entry["revision"], encoding="utf-8")
    return str(snapshot_root.absolute())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument(
        "--from-manifest",
        action="store_true",
        help="Reuse the previously resolved official revisions instead of querying again.",
    )
    parser.add_argument(
        "--aria2",
        action="store_true",
        help="Download known files directly into a standard Hub snapshot.",
    )
    args = parser.parse_args()
    require_safe_root()
    if args.from_manifest:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        payload = inspect_repositories()
        atomic_write(payload)
    for entry in payload["repositories"]:
        print(
            f"SYNCITY3K_ASSET repo={entry['repo_id']} "
            f"revision={entry['revision']} bytes={entry['total_bytes']}",
            flush=True,
        )
    if args.inspect_only:
        return 0
    for entry in payload["repositories"]:
        path: str | None = None
        for file_index, file_entry in enumerate(entry["files"], 1):
            if args.aria2:
                path = aria2_download(entry, file_entry)
                print(
                    f"SYNCITY3K_FILE_READY repo={entry['repo_id']} "
                    f"file={file_index}/{len(entry['files'])} path={file_entry['path']}",
                    flush=True,
                )
                continue
            last_error: Exception | None = None
            for attempt in range(1, 8):
                try:
                    # A commit SHA plus a known filename avoids the mirror's
                    # flaky repository-listing API and still uses normal Hub
                    # blobs/snapshot links with resumable downloads.
                    path = hf_hub_download(
                        repo_id=entry["repo_id"],
                        filename=file_entry["path"],
                        revision=entry["revision"],
                        cache_dir=HF_HOME / "hub",
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"SYNCITY3K_ASSET_RETRY repo={entry['repo_id']} "
                        f"file={file_entry['path']} attempt={attempt} "
                        f"error={type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    if attempt < 7:
                        time.sleep(5 * attempt)
            else:
                assert last_error is not None
                raise last_error
            print(
                f"SYNCITY3K_FILE_READY repo={entry['repo_id']} "
                f"file={file_index}/{len(entry['files'])} path={file_entry['path']}",
                flush=True,
            )
        assert path is not None
        if args.aria2:
            entry["snapshot_path"] = path
        else:
            snapshot_path = Path(path).parents[len(Path(file_entry["path"]).parts) - 1]
            entry["snapshot_path"] = str(snapshot_path.absolute())
        entry["downloaded_at_utc"] = utc_now()
        atomic_write(payload)
        print(f"SYNCITY3K_ASSET_READY repo={entry['repo_id']} path={path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
