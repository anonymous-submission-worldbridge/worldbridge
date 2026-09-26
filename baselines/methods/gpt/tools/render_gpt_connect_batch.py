#!/usr/bin/env python3
"""Render pending GPT-6 Astra high connected demos on explicit GPU lanes."""
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
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_BLENDER_BIN = _wb_paths["BLENDER_BIN"]


import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import queue
import subprocess


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = (BASELINES / "annotations/gpt6_astra/connect").resolve()
BLENDER = Path(f"{_wb_BLENDER_BIN}")
RENDERER = BASELINES / "methods/gpt/tools/render_gpt_connect_demo.py"


def render_one(run: Path, gpu_queue: queue.Queue[str]) -> tuple[str, str, int]:
    gpu = gpu_queue.get()
    try:
        command = [
            str(BLENDER),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "11",
            "--python",
            str(RENDERER),
            "--",
            "--run-dir",
            str(run),
        ]
        environment = dict(os.environ)
        environment["CUDA_VISIBLE_DEVICES"] = gpu
        log = run / "render.log"
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                command,
                cwd=BASELINES.parent,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        return run.name, gpu, int(result.returncode)
    finally:
        gpu_queue.put(gpu)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpus", nargs="+", required=True)
    parser.add_argument("--scene", action="append", default=[])
    args = parser.parse_args()
    runs = sorted(
        path for path in OUTPUT.glob("demo_*") if (path / "manifest.json").is_file()
    )
    if args.scene:
        wanted = set(args.scene)
        runs = [path for path in runs if path.name in wanted]
        missing = wanted - {path.name for path in runs}
        if missing:
            raise ValueError(f"Unknown demo ids: {sorted(missing)}")
    pending = []
    for run in runs:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("render_success"):
            print(f"CONNECT_BATCH_REUSED {run.name}", flush=True)
        else:
            pending.append(run)
    if not pending:
        return 0
    gpu_queue: queue.Queue[str] = queue.Queue()
    for gpu in args.gpus:
        gpu_queue.put(gpu)
    failures = []
    with ThreadPoolExecutor(max_workers=len(args.gpus)) as executor:
        futures = {
            executor.submit(render_one, run, gpu_queue): run.name for run in pending
        }
        for future in as_completed(futures):
            name, gpu, code = future.result()
            if code:
                failures.append((name, gpu, code))
                print(f"CONNECT_BATCH_FAILED {name} gpu={gpu} exit={code}", flush=True)
            else:
                print(f"CONNECT_BATCH_COMPLETE {name} gpu={gpu}", flush=True)
    if failures:
        print(json.dumps({"failures": failures}, ensure_ascii=False), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
