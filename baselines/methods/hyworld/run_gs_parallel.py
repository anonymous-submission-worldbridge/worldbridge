#!/usr/bin/env python3
"""Train independent HY-World Gaussian scenes concurrently, one per GPU."""

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
import json
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import baselines.methods.hyworld.run as matrix


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
LOG_ROOT = ROOT / "hyworld2_runtime/logs/gs_parallel"
LOCAL_ROOT = Path(_wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_gs_uid2002"))
DEMO_KEYS = {
    ("indoor_bedroom_00", 1),
    ("indoor_living_room_00", 0),
    ("urban_residential_four_way_00", 0),
    ("urban_leisure_civic_irregular_24", 0),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scene_identity(run_dir: Path) -> tuple[str, int]:
    payload = json.loads(
        (run_dir / "input/native_input.json").read_text(encoding="utf-8")
    )
    return str(payload["spec_id"]), int(payload["logical_seed"])


def command_for(run_dir: Path, local_scene: Path, demo: bool) -> list[str]:
    command = matrix.HY.gs_train_command(run_dir)
    if "--disable-viewer" not in command:
        command.append("--disable-viewer")
    # Fifty scene-local fitting steps are the accelerated inference profile.
    # Keep depth/normal supervision and the final Gaussian PLY, while removing
    # training-only evaluation, LPIPS/VGG, and redundant SPZ conversion.
    replacements = {
        "--max_steps": "50",
        "--save_steps": "50",
        "--ply_steps": "50",
        "--strategy.refine-start-iter": "5",
        "--strategy.refine-stop-iter": "25",
        "--strategy.refine-every": "3",
        "--strategy.refine-scale2d-stop-iter": "25",
    }
    for flag, value in replacements.items():
        command[command.index(flag) + 1] = value
    command[command.index("--data_dir") + 1] = str(local_scene / "gs_data")
    command[command.index("--result_dir") + 1] = str(local_scene / "gs")
    for flag in ("--eval_steps", "--convert_to_spz"):
        if flag in command:
            index = command.index(flag)
            del command[index : index + (2 if flag == "--eval_steps" else 1)]
    for flag in (
        "--use_mask_gaussian",
        "--mask_export_stochastic",
        "--no-mask-export-anchor-protection",
    ):
        if flag in command:
            command.remove(flag)
    command.extend(["--lpips_lambda1", "0", "--lpips_lambda2", "0"])
    if not demo and "--export_mesh" in command:
        command.remove("--export_mesh")
    return command


def clean_incomplete(native: Path) -> None:
    target = matrix.run_dir_from_native(native) / "scene/gs"
    if target.exists() and not matrix.valid_gs_training(native):
        shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpus", nargs="+", type=int, required=True)
    parser.add_argument(
        "--domains",
        nargs="+",
        choices=("indoor", "urban"),
        default=["indoor", "urban"],
    )
    parser.add_argument("--min-free-mib", type=int, default=18000)
    args = parser.parse_args()
    if len(args.gpus) != len(set(args.gpus)):
        raise ValueError("GPU ids must be unique")

    class SelectArgs:
        domains = args.domains
        trial = "formal"
        spec_ids = None
        seeds = None

    natives = matrix.select_natives(SelectArgs())
    pending = [native for native in natives if not matrix.valid_gs_training(native)]
    print(
        f"HYWORLD2_GS_PARALLEL_START selected={len(natives)} "
        f"pending={len(pending)} gpus={args.gpus}",
        flush=True,
    )
    tasks: queue.Queue[Path] = queue.Queue()
    for native in pending:
        tasks.put(native)
    stop = threading.Event()
    lock = threading.Lock()
    counts = {"completed": len(natives) - len(pending)}
    failures: list[dict] = []
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

    def worker(gpu: int) -> None:
        while not stop.is_set():
            try:
                native = tasks.get_nowait()
            except queue.Empty:
                return
            run_dir = matrix.run_dir_from_native(native)
            spec_id, seed = scene_identity(run_dir)
            demo = (spec_id, seed) in DEMO_KEYS
            while not stop.is_set():
                free_mib = matrix.gpu_free_mib(gpu)
                if free_mib >= args.min_free_mib:
                    break
                print(f"HYWORLD2_GS_WAIT gpu={gpu} free_mib={free_mib}", flush=True)
                time.sleep(15)
            if stop.is_set():
                tasks.task_done()
                return
            clean_incomplete(native)
            local_scene = LOCAL_ROOT / f"gpu{gpu}" / f"{spec_id}_seed{seed}"
            if local_scene.exists():
                shutil.rmtree(local_scene)
            local_scene.mkdir(parents=True)
            shutil.copytree(native / "gs_data", local_scene / "gs_data")
            shutil.copy2(native / "meta_info.json", local_scene / "meta_info.json")
            command = command_for(run_dir, local_scene, demo)
            log_path = LOG_ROOT / f"{spec_id}_seed{seed}_gpu{gpu}_50step.log"
            local_log_path = local_scene / "train.log"
            environment = matrix.runtime_environment([gpu], "gs_training")
            # The runtime overlay's gsplat/csrc.py loads the already compiled
            # extension from this node-local cache.  Pointing torch's extension
            # cache there also prevents accidental JIT rebuilds on NFS.
            local_extension_cache = (
                Path(
                    environment.get(
                        "HYWORLD2_RUNTIME_PYTHON_ROOT",
                        _wb_expand_paths(
                            "${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime"
                        ),
                    )
                )
                / "cache/torch_extensions"
            )
            environment["TORCH_EXTENSIONS_DIR"] = str(local_extension_cache)
            local_cache = Path(
                _wb_expand_paths(
                    "${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/cache"
                )
            )
            local_tmp = Path(
                _wb_expand_paths(
                    "${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/tmp"
                )
            )
            local_cache.mkdir(parents=True, exist_ok=True)
            local_tmp.mkdir(parents=True, exist_ok=True)
            for key, relative in {
                "TORCH_HOME": "torch",
                "TORCHINDUCTOR_CACHE_DIR": "torchinductor",
                "TRITON_CACHE_DIR": "triton",
                "CUDA_CACHE_PATH": "cuda",
                "XDG_CACHE_HOME": "xdg",
                "PYTHONPYCACHEPREFIX": "pycache",
                "MPLCONFIGDIR": "matplotlib",
            }.items():
                cache_path = local_cache / relative
                cache_path.mkdir(parents=True, exist_ok=True)
                environment[key] = str(cache_path)
            environment["TMPDIR"] = str(local_tmp)
            local_python_lib = _wb_expand_paths(
                "${WORLDBRIDGE_CACHE}/hyworld2_python_uid2002/lib"
            )
            inherited_ld_library_path = environment.get("LD_LIBRARY_PATH", "")
            environment["LD_LIBRARY_PATH"] = (
                f"{local_python_lib}:{inherited_ld_library_path}"
                if inherited_ld_library_path
                else local_python_lib
            )
            started_at = utc_now()
            started = time.monotonic()
            with local_log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[{started_at}] COMMAND {json.dumps(command)}\n")
                log.flush()
                result = subprocess.run(
                    command,
                    cwd=matrix.HY.SOURCE_ROOT / "hyworld2/worldgen",
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_log_path, log_path)
            if result.returncode == 0:
                canonical_result = run_dir / "scene/gs"
                if canonical_result.exists():
                    shutil.rmtree(canonical_result)
                shutil.copytree(local_scene / "gs", canonical_result)
            elapsed = time.monotonic() - started
            success = result.returncode == 0 and matrix.valid_gs_training(native)
            matrix.append_attempt(
                native,
                {
                    "stage": "gs_training",
                    "started_at_utc": started_at,
                    "ended_at_utc": utc_now(),
                    "wall_time_s": elapsed,
                    "exit_code": result.returncode,
                    "success": success,
                    "physical_gpus": [gpu],
                    "parallel_scene_training": True,
                    "visualization_demo": demo,
                    "log": str(log_path.relative_to(ROOT)),
                },
            )
            with lock:
                if success:
                    matrix.mark_generation_complete(native)
                    counts["completed"] += 1
                    print(
                        f"HYWORLD2_GS_DONE completed={counts['completed']}/{len(natives)} "
                        f"gpu={gpu} scene={spec_id}/seed_{seed} "
                        f"wall_s={elapsed:.1f} demo={demo}",
                        flush=True,
                    )
                    shutil.rmtree(local_scene)
                else:
                    failure = {
                        "gpu": gpu,
                        "scene": spec_id,
                        "seed": seed,
                        "exit_code": result.returncode,
                        "log": str(log_path),
                    }
                    failures.append(failure)
                    print(f"HYWORLD2_GS_ERROR {json.dumps(failure)}", flush=True)
                    stop.set()
            tasks.task_done()

    threads = [
        threading.Thread(target=worker, args=(gpu,), daemon=False) for gpu in args.gpus
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    remaining = sum(not matrix.valid_gs_training(native) for native in natives)
    print(
        f"HYWORLD2_GS_PARALLEL_END completed={len(natives) - remaining}/{len(natives)} "
        f"remaining={remaining} failures={len(failures)}",
        flush=True,
    )
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
