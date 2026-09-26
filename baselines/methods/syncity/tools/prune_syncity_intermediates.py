#!/usr/bin/env python3
"""Safely prune redundant raw SynCity PLY files from terminal formal runs."""

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
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
DEFAULT_REPORT = BASELINES_ROOT / "results/syncity3k/intermediate_prune.json"


def validated_raw_files(data_root: Path) -> list[tuple[Path, int]]:
    candidates: list[tuple[Path, int]] = []
    for run_dir in sorted(data_root.glob("*/syncity3k/*/seed_*")):
        if not (
            (run_dir / "SUCCESS").is_file() or (run_dir / "QUALITY_FAILURE").is_file()
        ):
            continue
        manifest_path = run_dir / "run_manifest.json"
        raw = run_dir / "scene/scene.ply"
        final = run_dir / "scene/scene_color_adjusted.ply"
        if not raw.is_file():
            continue
        if (
            not manifest_path.is_file()
            or not final.is_file()
            or final.stat().st_size == 0
        ):
            raise RuntimeError(f"Refusing to prune incomplete terminal run: {run_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "method": "syncity3k",
            "generation_success": True,
            "scene_file": "scene/scene_color_adjusted.ply",
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise RuntimeError(
                    f"Refusing to prune {run_dir}: {key}={manifest.get(key)!r}"
                )
        if manifest.get("scene_size_bytes") != final.stat().st_size:
            raise RuntimeError(f"Final-scene size mismatch: {run_dir}")
        if raw.samefile(final):
            raise RuntimeError(f"Raw and final scenes alias each other: {run_dir}")
        candidates.append((raw, raw.stat().st_size))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    report = args.report.resolve()
    data_root.relative_to(BASELINES_ROOT.resolve())
    report.relative_to(BASELINES_ROOT.resolve())
    files = validated_raw_files(data_root)
    total_bytes = sum(size for _, size in files)
    if args.execute:
        for path, _ in files:
            path.unlink()
        payload = {
            "method": "syncity3k",
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "policy": (
                "Removed only scene/scene.ply from terminal runs after validating "
                "the frozen scene/scene_color_adjusted.ply primary output and manifest."
            ),
            "removed_count": len(files),
            "removed_bytes": total_bytes,
            "removed_paths": [str(path) for path, _ in files],
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temporary.replace(report)
    print(
        json.dumps(
            {
                "execute": args.execute,
                "candidate_count": len(files),
                "candidate_bytes": total_bytes,
                "candidate_gib": round(total_bytes / (1024**3), 3),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
