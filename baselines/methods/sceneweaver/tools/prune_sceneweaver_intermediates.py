#!/usr/bin/env python3
"""Prune bulky, reproducible SceneWeaver solver snapshots from terminal runs.

The final scene, evaluation renders, cameras, manifests, prompts, LLM responses,
and attempt logs are deliberately retained.  By default this command is a dry
run; pass ``--execute`` to remove only the two allowlisted snapshot directories.
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
import datetime as dt
import json
import os
import shutil
from pathlib import Path


ALLOWLIST = ("executor_work", "record_files")
TERMINAL_MARKERS = (
    "SUCCESS",
    "PLANNER_BUDGET_EXHAUSTED",
    "RENDER_VALIDATION_FAILED",
)


def tree_usage(path: Path) -> tuple[int, int, int]:
    """Return file count, apparent bytes, and allocated bytes without following links."""
    files = apparent = allocated = 0
    for root, dirs, names in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        for name in names:
            candidate = Path(root) / name
            try:
                stat = candidate.lstat()
            except FileNotFoundError:
                continue
            files += 1
            apparent += stat.st_size
            allocated += stat.st_blocks * 512
    return files, apparent, allocated


def terminal_status(run_dir: Path) -> str | None:
    present = [marker for marker in TERMINAL_MARKERS if (run_dir / marker).is_file()]
    return present[0] if len(present) == 1 else None


def eligible(run_dir: Path, status: str) -> tuple[bool, str | None]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return False, "missing run_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False, "invalid run_manifest.json"
    if manifest.get("method") != "sceneweaver":
        return False, "manifest method is not sceneweaver"
    if status == "SUCCESS":
        validation_path = run_dir / "renders/validation.json"
        if not (run_dir / "scene").is_dir() or not validation_path.is_file():
            return False, "SUCCESS is missing final scene or render validation"
        try:
            validation = json.loads(validation_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False, "invalid render validation"
        if validation.get("valid") is not True:
            return False, "SUCCESS render validation is not valid"
    return True, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    method_root = (args.data_root / "indoor" / "sceneweaver").resolve()
    records: list[dict] = []
    for run_dir in sorted(method_root.glob("*/seed_*")):
        status = terminal_status(run_dir)
        if status is None:
            continue
        ok, error = eligible(run_dir, status)
        record = {
            "run_dir": str(run_dir.relative_to(method_root)),
            "status": status,
            "eligible": ok,
            "error": error,
            "targets": [],
        }
        if ok:
            work_root = (run_dir / "sceneweaver").resolve()
            for name in ALLOWLIST:
                target = work_root / name
                if not target.is_dir() or target.is_symlink():
                    continue
                if target.parent != work_root or work_root.parent != run_dir.resolve():
                    raise RuntimeError(f"unsafe prune target: {target}")
                files, apparent, allocated = tree_usage(target)
                record["targets"].append(
                    {
                        "relative_path": str(target.relative_to(run_dir)),
                        "files": files,
                        "apparent_bytes": apparent,
                        "allocated_bytes": allocated,
                    }
                )
                if args.execute:
                    shutil.rmtree(target)
            if args.execute and record["targets"]:
                marker = run_dir / "PRUNED_INTERMEDIATES.json"
                marker.write_text(
                    json.dumps(
                        {
                            "policy": "terminal_sceneweaver_snapshot_allowlist_v1",
                            "removed": record["targets"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
        records.append(record)

    payload = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "dry_run",
        "method_root": str(method_root),
        "allowlist": list(ALLOWLIST),
        "terminal_markers": list(TERMINAL_MARKERS),
        "records": records,
        "target_count": sum(len(record["targets"]) for record in records),
        "allocated_bytes": sum(
            target["allocated_bytes"]
            for record in records
            for target in record["targets"]
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        f"SCENEWEAVER_PRUNE mode={payload['mode']} targets={payload['target_count']} "
        f"allocated_bytes={payload['allocated_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
