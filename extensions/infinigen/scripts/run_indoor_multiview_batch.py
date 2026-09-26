#!/usr/bin/env python3
"""Generate and render native Infinigen homes in a bounded parallel queue."""

from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_PYTHON = _wb_paths['WORLDBRIDGE_PYTHON']


import argparse
import concurrent.futures
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(f'{_wb_WORLDBRIDGE_PYTHON}')
PRIMARY_TYPES = ("bedroom", "living-room", "kitchen", "bathroom")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=3)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--gpus", default="1,2,3,4,6,7")
    parser.add_argument("--views-per-room", type=int, default=3)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument(
        "--render-stage-dir",
        type=Path,
        default=Path("/tmp/worldbridge_infinigen_render_stage"),
        help="Local scratch directory used to avoid random I/O on the shared data mount",
    )
    return parser.parse_args()


def atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def furniture_inventory(state_path: Path) -> dict:
    data = json.loads(state_path.read_text())
    objects = data.get("objs", {})
    rooms = {
        name
        for name, record in objects.items()
        if "Semantics(room)" in record.get("tags", []) and record.get("active", True)
    }
    counts = {room: 0 for room in rooms}
    for name, record in objects.items():
        if name in rooms or not record.get("active", True):
            continue
        targets = {
            relation.get("target_name") for relation in record.get("relations", [])
        }
        for room in rooms.intersection(targets):
            counts[room] += 1
    by_type = {}
    for room in sorted(rooms):
        match = re.match(r"^([a-z-]+)_\d+/\d+$", room)
        if match:
            by_type.setdefault(match.group(1), {})[room] = counts[room]
    return {"rooms": by_type, "direct_furnishing_counts": counts}


def validate_scene(scene_dir: Path) -> dict:
    blend = scene_dir / "coarse" / "scene.blend"
    state = scene_dir / "coarse" / "solve_state.json"
    if not blend.is_file() or blend.stat().st_size < 1_000_000:
        raise RuntimeError(f"Missing or invalid scene.blend: {blend}")
    if not state.is_file():
        raise RuntimeError(f"Missing solve_state.json: {state}")
    inventory = furniture_inventory(state)
    missing = [kind for kind in PRIMARY_TYPES if kind not in inventory["rooms"]]
    empty = [
        kind
        for kind in PRIMARY_TYPES
        if kind in inventory["rooms"]
        and max(inventory["rooms"][kind].values(), default=0) == 0
    ]
    if missing or empty:
        raise RuntimeError(f"Scene validation failed: missing={missing}, unfurnished={empty}")
    inventory["blend_bytes"] = blend.stat().st_size
    return inventory


def run_logged(command: list[str], log_path: Path, env: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", buffering=1) as log:
        log.write("\n$ " + " ".join(command) + "\n")
        log.flush()
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}; see {log_path}"
        )


def run_scene(index: int, gpu_queue: queue.Queue, args: argparse.Namespace) -> dict:
    gpu = gpu_queue.get()
    scene_name = f"indoor{index}"
    scene_dir = ROOT / "outputs" / scene_name
    tmp_dir = args.render_stage_dir / f"{scene_name}_worktmp"
    started = time.time()
    status_path = scene_dir / "status.json"
    try:
        scene_dir.mkdir(parents=True, exist_ok=True)
        (scene_dir / "logs").mkdir(exist_ok=True)
        args.render_stage_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "CUDA_VISIBLE_DEVICES": gpu,
                "TMPDIR": str(tmp_dir),
                "TMP": str(tmp_dir),
                "TEMP": str(tmp_dir),
                "OMP_NUM_THREADS": "8",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "PYTHONUNBUFFERED": "1",
            }
        )
        base_seed = f"worldbridge_{scene_name}_20260919"
        status = {
            "status": "starting",
            "scene": scene_name,
            "seed": base_seed,
            "gpu": gpu,
            "started_unix": started,
            "generation_config": "residential_batch_multiview.gin",
            "generation_attempts": [],
        }
        atomic_json(status_path, status)
        print(f"[start] {scene_name} gpu={gpu}", flush=True)

        try:
            inventory = validate_scene(scene_dir)
            print(f"[reuse] {scene_name} existing coarse scene passed validation", flush=True)
        except Exception as existing_error:
            inventory = None
            for attempt in range(1, 4):
                seed = base_seed if attempt == 1 else f"{base_seed}_retry{attempt}"
                status["status"] = "generating"
                status["seed"] = seed
                attempt_record = {
                    "attempt": attempt,
                    "seed": seed,
                    "status": "running",
                }
                status["generation_attempts"].append(attempt_record)
                atomic_json(status_path, status)
                coarse_dir = scene_dir / "coarse"
                if coarse_dir.exists():
                    shutil.rmtree(coarse_dir)
                command = [
                    str(PYTHON),
                    "-m",
                    "infinigen_examples.generate_indoors",
                    "--seed",
                    seed,
                    "--task",
                    "coarse",
                    "--output_folder",
                    str(coarse_dir),
                    "--configs",
                    "residential_batch_multiview.gin",
                ]
                try:
                    run_logged(command, scene_dir / "logs" / "generate.log", env)
                    inventory = validate_scene(scene_dir)
                    attempt_record["status"] = "complete"
                    atomic_json(status_path, status)
                    break
                except Exception as attempt_error:
                    attempt_record["status"] = "failed"
                    attempt_record["error"] = str(attempt_error)
                    atomic_json(status_path, status)
                    print(
                        f"[retry] {scene_name} attempt={attempt}/3 failed: {attempt_error}",
                        flush=True,
                    )
            if inventory is None:
                raise RuntimeError(
                    f"All generation attempts failed; initial state was: {existing_error}"
                )

        status["inventory"] = inventory
        status["status"] = "rendering"
        atomic_json(status_path, status)
        manifest = scene_dir / "render" / "manifest.json"
        render_complete = False
        if manifest.is_file():
            try:
                existing = json.loads(manifest.read_text())
                render_complete = existing.get("status") == "complete"
            except Exception:
                render_complete = False
        if not render_complete:
            args.render_stage_dir.mkdir(parents=True, exist_ok=True)
            staged_blend = args.render_stage_dir / f"{scene_name}.blend"
            staged_tmp = args.render_stage_dir / f"{scene_name}_tmp"
            staged_tmp.mkdir(exist_ok=True)
            source_blend = scene_dir / "coarse" / "scene.blend"
            print(f"[stage] {scene_name} {source_blend} -> {staged_blend}", flush=True)
            shutil.copy2(source_blend, staged_blend)
            render_env = env.copy()
            render_env.update(
                {"TMPDIR": str(staged_tmp), "TMP": str(staged_tmp), "TEMP": str(staged_tmp)}
            )
            command = [
                str(PYTHON),
                str(ROOT / "tools" / "render_indoor_multiview.py"),
                "--scene",
                str(staged_blend),
                "--source-label",
                str(source_blend),
                "--output",
                str(scene_dir / "render"),
                "--views-per-room",
                str(args.views_per_room),
                "--width",
                str(args.width),
                "--height",
                str(args.height),
                "--samples",
                str(args.samples),
            ]
            try:
                run_logged(command, scene_dir / "logs" / "render.log", render_env)
            finally:
                staged_blend.unlink(missing_ok=True)
                shutil.rmtree(staged_tmp, ignore_errors=True)
        else:
            print(f"[reuse] {scene_name} existing render passed manifest check", flush=True)

        render_data = json.loads(manifest.read_text())
        if render_data.get("status") != "complete":
            raise RuntimeError(f"Render manifest is incomplete: {manifest}")
        status.update(
            {
                "status": "complete",
                "room_count": render_data["room_count"],
                "image_count": render_data["total_images"],
                "elapsed_seconds": round(time.time() - started, 2),
            }
        )
        atomic_json(status_path, status)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(
            f"[complete] {scene_name} rooms={status['room_count']} "
            f"images={status['image_count']} seconds={status['elapsed_seconds']}",
            flush=True,
        )
        return status
    except Exception as error:
        failure = {
            "status": "failed",
            "scene": scene_name,
            "gpu": gpu,
            "elapsed_seconds": round(time.time() - started, 2),
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        scene_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(status_path, failure)
        print(f"[failed] {scene_name}: {error}", flush=True)
        return failure
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        gpu_queue.put(gpu)


def main() -> int:
    args = parse_args()
    gpus = [item.strip() for item in args.gpus.split(",") if item.strip()]
    if not PYTHON.is_file():
        raise FileNotFoundError(f"Existing Infinigen Python was not found: {PYTHON}")
    if args.count < 1 or args.workers < 1 or not gpus:
        raise ValueError("count, workers, and GPU list must be non-empty")
    workers = min(args.workers, len(gpus), args.count)
    gpu_queue: queue.Queue = queue.Queue()
    for gpu in gpus[:workers]:
        gpu_queue.put(gpu)

    batch_dir = ROOT / "outputs"
    summary_path = batch_dir / f"indoor{args.start}_indoor{args.start + args.count - 1}_batch.json"
    summary = {
        "status": "running",
        "start": args.start,
        "count": args.count,
        "workers": workers,
        "gpus": gpus[:workers],
        "views_per_room": args.views_per_room,
        "resolution": [args.width, args.height],
        "samples": args.samples,
        "started_unix": time.time(),
        "scenes": [],
    }
    atomic_json(summary_path, summary)
    print(
        f"[batch] scenes=indoor{args.start}..indoor{args.start + args.count - 1} "
        f"workers={workers} gpus={','.join(gpus[:workers])}",
        flush=True,
    )

    indices = range(args.start, args.start + args.count)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_scene, index, gpu_queue, args): index for index in indices}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            summary["scenes"].append(result)
            summary["scenes"].sort(key=lambda item: item["scene"])
            atomic_json(summary_path, summary)

    failures = [item for item in summary["scenes"] if item["status"] != "complete"]
    summary["status"] = "failed" if failures else "complete"
    summary["finished_unix"] = time.time()
    summary["elapsed_seconds"] = round(
        summary["finished_unix"] - summary["started_unix"], 2
    )
    summary["completed_scenes"] = len(summary["scenes"]) - len(failures)
    summary["failed_scenes"] = len(failures)
    summary["total_images"] = sum(
        item.get("image_count", 0) for item in summary["scenes"]
    )
    atomic_json(summary_path, summary)
    print(
        f"[batch-{summary['status']}] completed={summary['completed_scenes']} "
        f"failed={summary['failed_scenes']} images={summary['total_images']} "
        f"seconds={summary['elapsed_seconds']}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
