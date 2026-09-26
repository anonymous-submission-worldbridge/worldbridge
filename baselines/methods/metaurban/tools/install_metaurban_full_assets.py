#!/usr/bin/env python3
"""Safely install MetaUrban's registered full static asset archive.

The password is read without echo and is never written to argv, logs, or disk.
Extraction and validation finish in ``baselines/tmp`` before the working tiny
pack is moved to a recoverable backup.
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
import getpass
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE_PACKAGE = BASELINES_ROOT / "sources/metaurban/metaurban"
DESTINATION = SOURCE_PACKAGE / "assets"
DEFAULT_ARCHIVE = BASELINES_ROOT / "checkpoints/metaurban/assets-full.zip"
MANIFEST = BASELINES_ROOT / "methods/metaurban/environment/metaurban_full_assets.json"
_WORKER_ARCHIVE: zipfile.ZipFile | None = None
_WORKER_DESTINATION: Path | None = None
_WORKER_PASSWORD: bytes | None = None
KNOWN_OFFICIAL_MISSING_MODELS = {
    "Tents-506852e74b4e418eb5cd2fb2d996c282.glb",
    "Tents-70a8f7db5f724989a035166b79ace87b.glb",
    "Tents-fa46028e8d3849399ba5271df07ed99c.glb",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as error:
        raise ValueError(f"Path must remain below {BASELINES_ROOT}: {path}") from error
    return resolved


def find_assets_root(extracted: Path) -> Path:
    candidates = [
        path.parent
        for path in extracted.rglob("version.txt")
        if (path.parent / "models/test").is_dir()
        and (path.parent / "adj_parameter_folder").is_dir()
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one full assets root, found {len(candidates)}")
    return candidates[0]


def inventory(root: Path) -> dict[str, Any]:
    glbs = sorted((root / "models/test").glob("*.glb"))
    metadata = sorted((root / "adj_parameter_folder").glob("*.json"))
    buildings = [path for path in glbs if "building" in path.name.lower()]
    missing_models = []
    for metadata_path in metadata:
        row = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = row.get("filename")
        if filename and not (root / "models/test" / filename).exists():
            missing_models.append(filename)
    return {
        "version": (root / "version.txt").read_text(encoding="utf-8").strip(),
        "version_sha256": sha256_file(root / "version.txt"),
        "static_glb_count": len(glbs),
        "metadata_json_count": len(metadata),
        "building_glb_count": len(buildings),
        "missing_metadata_models": sorted(set(missing_models)),
    }


def validate_full_assets(root: Path) -> dict[str, Any]:
    result = inventory(root)
    # The public tiny pack contains exactly 50 GLBs/metadata entries and no
    # buildings in the current official release.  Full must strictly exceed it.
    if result["static_glb_count"] <= 50 or result["metadata_json_count"] <= 50:
        raise RuntimeError(
            f"Extracted archive still looks like the tiny pack: {result}"
        )
    if result["building_glb_count"] == 0:
        raise RuntimeError("Full asset validation found no building models")
    unexpected_missing = set(result["missing_metadata_models"]) - (
        KNOWN_OFFICIAL_MISSING_MODELS
    )
    if unexpected_missing:
        raise RuntimeError(
            "Asset metadata references unexpected missing models: "
            f"{sorted(unexpected_missing)}"
        )
    return result


def init_extract_worker(archive: str, destination: str, password: bytes) -> None:
    global _WORKER_ARCHIVE, _WORKER_DESTINATION, _WORKER_PASSWORD
    _WORKER_ARCHIVE = zipfile.ZipFile(archive)
    _WORKER_DESTINATION = Path(destination)
    _WORKER_PASSWORD = password


def extract_member(name: str) -> int:
    if (
        _WORKER_ARCHIVE is None
        or _WORKER_DESTINATION is None
        or _WORKER_PASSWORD is None
    ):
        raise RuntimeError("Parallel extraction worker was not initialized")
    info = _WORKER_ARCHIVE.getinfo(name)
    _WORKER_ARCHIVE.extract(info, path=_WORKER_DESTINATION, pwd=_WORKER_PASSWORD)
    return info.file_size


def parallel_extract(
    archive: Path, destination: Path, password: bytes, workers: int
) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        infos = handle.infolist()
        for info in infos:
            target = (destination / info.filename).resolve()
            try:
                target.relative_to(destination_resolved)
            except ValueError as error:
                raise RuntimeError(
                    f"Unsafe archive member path: {info.filename}"
                ) from error
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
        files = sorted(
            (info for info in infos if not info.is_dir()),
            key=lambda info: info.compress_size,
            reverse=True,
        )
    completed_bytes = 0
    context = multiprocessing.get_context("fork")
    with context.Pool(
        processes=workers,
        initializer=init_extract_worker,
        initargs=(str(archive), str(destination), password),
    ) as pool:
        for completed, size in enumerate(
            pool.imap_unordered(
                extract_member, (info.filename for info in files), chunksize=1
            ),
            start=1,
        ):
            completed_bytes += size
            if completed % 100 == 0 or completed == len(files):
                print(
                    f"EXTRACT_PROGRESS files={completed}/{len(files)} "
                    f"bytes={completed_bytes}",
                    flush=True,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--native-unzip",
        action="store_true",
        help="Use system unzip, which reads the code directly from the TTY",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel Python extraction workers (password stays out of argv)",
    )
    args = parser.parse_args()
    if not 1 <= args.workers <= 32:
        raise ValueError("workers must be between 1 and 32")
    archive = below_baselines(args.archive)
    if not archive.is_file():
        raise FileNotFoundError(archive)
    password: bytes | None = None
    if not args.native_unzip:
        password = getpass.getpass(
            "MetaUrban registration code (not stored): "
        ).encode()
        if not password:
            raise ValueError("An extraction code is required")

    tmp_parent = BASELINES_ROOT / "tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="metaurban-full-assets-", dir=tmp_parent
    ) as name:
        extracted = Path(name)
        if args.native_unzip:
            unzip = shutil.which("unzip")
            if unzip is None:
                raise RuntimeError("System unzip is unavailable")
            completed = subprocess.run(
                [unzip, "-q", str(archive), "-d", str(extracted)],
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "Archive extraction failed; check the registration code"
                )
        elif args.workers > 1:
            assert password is not None
            try:
                parallel_extract(archive, extracted, password, args.workers)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise RuntimeError(
                    "Archive extraction failed; check the registration code"
                ) from error
        else:
            try:
                with zipfile.ZipFile(archive) as handle:
                    handle.extractall(extracted, pwd=password)
            except RuntimeError as error:
                raise RuntimeError(
                    "Archive extraction failed; check the registration code"
                ) from error
        candidate = find_assets_root(extracted)
        full_inventory = validate_full_assets(candidate)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = below_baselines(tmp_parent / f"metaurban-assets-tiny-backup-{stamp}")
        if backup.exists():
            raise FileExistsError(backup)
        if not DESTINATION.is_dir():
            raise FileNotFoundError(
                f"Working asset directory is missing: {DESTINATION}"
            )
        shutil.move(str(DESTINATION), str(backup))
        try:
            shutil.move(str(candidate), str(DESTINATION))
        except Exception:
            if not DESTINATION.exists() and backup.exists():
                shutil.move(str(backup), str(DESTINATION))
            raise

    installed_inventory = validate_full_assets(DESTINATION)
    if installed_inventory != full_inventory:
        raise RuntimeError("Installed asset inventory changed during activation")
    manifest = {
        "status": "installed",
        "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_archive": str(archive),
        "source_archive_size_bytes": archive.stat().st_size,
        "source_archive_sha256": sha256_file(archive),
        "tiny_backup": str(backup),
        **installed_inventory,
    }
    atomic_json(MANIFEST, manifest)
    print(
        "METAURBAN_FULL_ASSETS_INSTALLED "
        f"glbs={manifest['static_glb_count']} metadata={manifest['metadata_json_count']} "
        f"backup={backup} manifest={MANIFEST}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
