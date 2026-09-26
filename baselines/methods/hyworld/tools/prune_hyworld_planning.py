#!/usr/bin/env python3
"""Prune downstream-unused HY-World planning artifacts after each scene."""

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
import os
import re
import time
from pathlib import Path


DEMOS = {
    ("indoor_bedroom_00", "seed_1"),
    ("indoor_living_room_00", "seed_0"),
    ("urban_residential_four_way_00", "seed_0"),
    ("urban_leisure_civic_irregular_24", "seed_0"),
}
SCENE_RE = re.compile(
    r"Stage1: Start regular trajectory generation for scene: scene_(\d+)"
)


def planning_valid(native: Path) -> bool:
    render = native / "render_results"
    if not (
        (render / "global_pcd.ply").is_file()
        and (render / "full_depth_prediction.pt").is_file()
        and (native / "navmesh/reconstruct_pairs.json").is_file()
    ):
        return False
    return any(
        path.parent.name.startswith("traj") for path in render.rglob("camera.json")
    )


def prune(native_link: Path) -> None:
    native = native_link.resolve()
    spec_id = native.parents[2].name
    seed_id = native.parents[1].name
    if (spec_id, seed_id) in DEMOS:
        print(f"HYWORLD2_VIS_DEMO_KEEP spec={spec_id} seed={seed_id}", flush=True)
        return
    candidates = [
        *(
            native / "navmesh" / kind / "vis_mesh.ply"
            for kind in ("surround", "target", "exploration", "reconstruct")
        ),
        native / "render_results/global_mesh.ply",
        native / "render_results/global_normal.npy",
        native / "render_results/combined_with_markers.ply",
    ]
    removed_bytes = 0
    removed_files = 0
    for path in candidates:
        if path.is_file():
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
    print(
        f"HYWORLD2_PRUNE spec={spec_id} seed={seed_id} files={removed_files} "
        f"freed_mib={removed_bytes / (1024 ** 2):.1f}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workset", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    args = parser.parse_args()

    scenes = sorted(args.workset.glob("scene_*"))
    handled: set[int] = set()
    offset = 0
    current = -1
    while Path(f"/proc/{args.pid}").exists():
        if args.log.is_file():
            with args.log.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
            for match in SCENE_RE.finditer(chunk):
                current = max(current, int(match.group(1)))
            for index in range(current):
                if index not in handled and planning_valid(scenes[index]):
                    prune(scenes[index])
                    handled.add(index)
        time.sleep(args.poll_seconds)

    for index, native in enumerate(scenes):
        if index not in handled and planning_valid(native):
            prune(native)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
