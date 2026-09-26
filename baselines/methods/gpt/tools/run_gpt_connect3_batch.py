#!/usr/bin/env python3
"""Build and render the high-detail connect3 suite with resumable GPU lanes."""
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
OUTPUT = BASELINES / "annotations/gpt6_astra/connect3"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
BUILDER = BASELINES / "methods/gpt/tools/build_gpt_connect3.py"
RENDERER = BASELINES / "methods/gpt/tools/render_gpt_connect3.py"
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


def run_logged(command, log: Path, environment=None):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(
            command,
            cwd=BASELINES.parent,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return completed.returncode


def build_one(scene_id: str, force: bool):
    command = [
        str(BLENDER),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "11",
        "--python",
        str(BUILDER),
        "--",
        "--scene-id",
        scene_id,
    ]
    if force:
        command.append("--force")
    code = run_logged(command, OUTPUT / scene_id / "build.log")
    return scene_id, code


def render_one(scene_id: str, force: bool, lanes: queue.Queue[str], views: str | None):
    gpu = lanes.get()
    try:
        manifest_path = OUTPUT / scene_id / "manifest.json"
        if not manifest_path.is_file():
            return scene_id, gpu, 90
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scene_path = OUTPUT / scene_id / manifest["scene_file"]
        command = [
            str(BLENDER),
            "--background",
            str(scene_path),
            "--python-exit-code",
            "11",
            "--python",
            str(RENDERER),
            "--",
            "--scene-id",
            scene_id,
        ]
        if force:
            command.append("--force")
        if views:
            command.extend(["--views", views, "--update-manifest", "--stills-only"])
        environment = dict(os.environ)
        environment["CUDA_VISIBLE_DEVICES"] = gpu
        code = run_logged(command, OUTPUT / scene_id / "render.log", environment)
        return scene_id, gpu, code
    finally:
        lanes.put(gpu)


def selected_scenes(requested):
    if not requested:
        return list(SCENE_IDS)
    wanted = set(requested)
    selected = [scene for scene in SCENE_IDS if scene in wanted]
    unknown = sorted(wanted - set(selected))
    if unknown:
        raise ValueError(f"unknown scene ids: {unknown}")
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("build", "render", "all"), default="all")
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--gpus", nargs="+", default=["0", "2", "3"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--views", help="comma-separated partial still rerender")
    args = parser.parse_args()
    scenes = selected_scenes(args.scene)
    failures = []
    if args.stage in {"build", "all"}:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            futures = {
                executor.submit(build_one, scene, args.force): scene for scene in scenes
            }
            for future in as_completed(futures):
                scene, code = future.result()
                print(
                    f"ASTRA_CONNECT3_BATCH_BUILD scene={scene} exit={code}", flush=True
                )
                if code:
                    failures.append({"stage": "build", "scene": scene, "exit": code})
    if failures:
        print(
            json.dumps({"failures": failures}, ensure_ascii=False, indent=2), flush=True
        )
        return 2
    if args.stage in {"render", "all"}:
        lanes: queue.Queue[str] = queue.Queue()
        for gpu in args.gpus:
            lanes.put(gpu)
        with ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
            futures = {
                executor.submit(render_one, scene, args.force, lanes, args.views): scene
                for scene in scenes
            }
            for future in as_completed(futures):
                scene, gpu, code = future.result()
                print(
                    f"ASTRA_CONNECT3_BATCH_RENDER scene={scene} gpu={gpu} exit={code}",
                    flush=True,
                )
                if code:
                    failures.append(
                        {"stage": "render", "scene": scene, "gpu": gpu, "exit": code}
                    )
    if failures:
        print(
            json.dumps({"failures": failures}, ensure_ascii=False, indent=2), flush=True
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
