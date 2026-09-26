#!/usr/bin/env python3
"""Copy-verify-switch only the Extra High formal method trees to /tmp."""
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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
TMP_DATA = Path(
    _wb_expand_paths("${WORLDBRIDGE_CACHE}/worldbridge_gpt6_astra_xhigh_uid2002/table2")
)
METHOD = "gpt6_astra_xhigh"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def tree_digest(records: list[dict]) -> str:
    payload = "".join(
        f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n" for row in records
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def copy_tree(source: Path, target: Path) -> list[dict]:
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_symlink():
            raise RuntimeError(
                "Unexpected symlink inside formal method tree: " + str(item)
            )
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            raise RuntimeError("Unexpected formal artifact type: " + str(item))
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        temporary = destination.with_name(destination.name + ".migration-tmp")
        with item.open("rb") as incoming, temporary.open("wb") as outgoing:
            while block := incoming.read(4 * 1024 * 1024):
                outgoing.write(block)
                digest.update(block)
        shutil.copystat(item, temporary, follow_symlinks=False)
        os.replace(temporary, destination)
        records.append(
            {
                "path": str(relative),
                "bytes": item.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return records


def verify_target(target: Path, records: list[dict]) -> None:
    actual = sorted(
        str(path.relative_to(target))
        for path in target.rglob("*")
        if path.is_file() and path.name != ".migration_inventory.json"
    )
    expected = [row["path"] for row in records]
    if actual != expected:
        raise RuntimeError("Target file inventory mismatch")
    for row in records:
        path = target / row["path"]
        if path.stat().st_size != row["bytes"] or hash_file(path) != row["sha256"]:
            raise RuntimeError("Target checksum mismatch: " + str(path))


def main() -> int:
    processes = subprocess.check_output(["ps", "-eo", "cmd="], text=True)
    if (
        "run_gpt_xhigh_accelerated.py" in processes
        or "codex-gpt6-astra-xhigh-frozen exec" in processes
    ):
        raise RuntimeError("Refusing migration while an Extra High process is active")
    if shutil.disk_usage("/tmp").free < 20 * 1024**3:
        raise RuntimeError("Insufficient /tmp free space for verified migration")
    reports = []
    for domain in ("indoor", "urban"):
        source = ROOT / "data/table2" / domain / METHOD
        target = TMP_DATA / domain / METHOD
        if source.is_symlink():
            if source.resolve() != target.resolve():
                raise RuntimeError(
                    "Unexpected existing formal method symlink: " + str(source)
                )
            inventory = json.loads((target / ".migration_inventory.json").read_text())
            reports.append(inventory)
            continue
        if not source.is_dir():
            source.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError(
                "Refusing to merge into an existing migration target: " + str(target)
            )
        records = copy_tree(source, target)
        verify_target(target, records)
        inventory = {
            "domain": domain,
            "source": str(source),
            "target": str(target),
            "files": len(records),
            "bytes": sum(row["bytes"] for row in records),
            "tree_sha256": tree_digest(records),
            "verified_before_source_removal": True,
            "records": records,
        }
        (target / ".migration_inventory.json").write_text(
            json.dumps(inventory, indent=2) + "\n"
        )
        shutil.rmtree(source)
        source.symlink_to(target, target_is_directory=True)
        if source.resolve() != target.resolve():
            raise RuntimeError("Formal method link verification failed")
        reports.append(inventory)
    output = ROOT / "results/gpt6_astra_xhigh/formal_storage_migration.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "method": METHOD,
                "tmp_data_root": str(TMP_DATA),
                "domains": [
                    {key: value for key, value in row.items() if key != "records"}
                    for row in reports
                ],
            },
            indent=2,
        )
        + "\n"
    )
    os.replace(temporary, output)
    print(output.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
