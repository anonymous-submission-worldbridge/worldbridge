#!/usr/bin/env python3
"""Prune regular HY-World scenes to the single trajectory used by fast expansion."""

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
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    scenes = changed = removed = reclaimed = 0
    for manifest_path in sorted(args.root.rglob("selected_trajectories.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("full_visualization_demo"):
            continue
        selected = list(manifest.get("selected") or [])
        if not selected:
            continue
        scenes += 1
        keep = selected[:1]
        render_root = manifest_path.parent
        for relative in selected[1:]:
            for name in ("render.mp4", "render_mask.mp4", "traj_caption.json"):
                artifact = render_root / relative / name
                if artifact.is_file():
                    reclaimed += artifact.stat().st_size
                    artifact.unlink()
                    removed += 1
        if selected != keep:
            manifest["selected"] = keep
            temporary = manifest_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(manifest_path)
            changed += 1
    print(
        f"HYWORLD2_PRUNE scenes={scenes} manifests_changed={changed} "
        f"files_removed={removed} reclaimed_bytes={reclaimed}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
