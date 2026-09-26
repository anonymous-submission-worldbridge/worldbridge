#!/usr/bin/env python3
"""Render GPT-6 Astra connect2 scenes concurrently on explicit GPU lanes."""
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


import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import queue
import subprocess

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gpt6_astra/connect2"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
SCRIPT = BASELINES / "methods/gpt/tools/render_gpt_connect2.py"
SCENE_IDS = (
    "residential_neighborhood",
    "neighborhood_school",
    "public_library",
    "community_sports_hall",
    "retail_pharmacy",
    "police_station",
    "fire_station",
    "community_hospital",
    "light_factory",
    "delivery_service_hub",
    "community_bank_atm",
    "gas_station_store",
    "riverside_lake_park",
)
DEFAULT_VIDEO_FRAMES = 96


def render_one(scene_id: str, frames: int, force: bool, lanes: queue.Queue[str]):
    gpu = lanes.get()
    try:
        root = OUTPUT / scene_id
        log = root / "render.log"
        command = [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "11",
            "--python",
            str(SCRIPT),
            "--",
            "--scene-id",
            scene_id,
            "--video-frames",
            str(frames),
        ]
        if force:
            command.append("--force")
        environment = dict(os.environ)
        environment["CUDA_VISIBLE_DEVICES"] = gpu
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                command,
                cwd=BASELINES.parent,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
            )
        return scene_id, gpu, completed.returncode
    finally:
        lanes.put(gpu)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpus", nargs="+", required=True)
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--video-frames", type=int, default=DEFAULT_VIDEO_FRAMES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected = list(SCENE_IDS)
    if args.scene:
        wanted = set(args.scene)
        selected = [scene_id for scene_id in selected if scene_id in wanted]
        missing = wanted - set(selected)
        if missing:
            raise ValueError(f"unknown scene ids: {sorted(missing)}")
    lanes: queue.Queue[str] = queue.Queue()
    for gpu in args.gpus:
        lanes.put(gpu)
    failures = []
    with ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = {
            executor.submit(
                render_one, scene_id, args.video_frames, args.force, lanes
            ): scene_id
            for scene_id in selected
        }
        for future in as_completed(futures):
            scene_id, gpu, code = future.result()
            if code:
                failures.append({"scene_id": scene_id, "gpu": gpu, "exit_code": code})
                print(
                    f"ASTRA_CONNECT2_BATCH_FAILED scene={scene_id} gpu={gpu} exit={code}",
                    flush=True,
                )
            else:
                print(
                    f"ASTRA_CONNECT2_BATCH_COMPLETE scene={scene_id} gpu={gpu}",
                    flush=True,
                )
    if failures:
        print(
            json.dumps({"failures": failures}, ensure_ascii=False, indent=2), flush=True
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
