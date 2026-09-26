#!/usr/bin/env python3
"""Fit Table-4 HY-World Gaussian scenes concurrently, one scene per GPU."""

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
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
TABLE4_ROOT = _BASELINE_PROJECT_ROOT / "baselines/methods/hyworld/unified/native"
sys.path.insert(0, str(BASELINES_ROOT))

import baselines.methods.hyworld.unified.native.run_hyworld_matrix as matrix  # noqa: E402


def load_adapter():
    path = TABLE4_ROOT / "adapters/hyworld.py"
    spec = importlib.util.spec_from_file_location("table4_gs_adapter", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()
matrix.HY = HY
LOG_ROOT = BASELINES_ROOT / "results/table4/hyworld2/logs/gs_parallel"
LOCAL_ROOT = Path(f"/tmp/hyworld2_table4_gs_uid{os.getuid()}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity(run_dir: Path) -> tuple[str, int, str]:
    payload = json.loads(
        (run_dir / "input/native_input.json").read_text(encoding="utf-8")
    )
    return str(payload["spec_id"]), int(payload["logical_seed"]), str(payload["side"])


def command_for(run_dir: Path, local_scene: Path) -> list[str]:
    command = HY.gs_train_command(run_dir)
    if "--disable-viewer" not in command:
        command.append("--disable-viewer")
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
        "--export_mesh",
    ):
        if flag in command:
            command.remove(flag)
    command.extend(["--lpips_lambda1", "0", "--lpips_lambda2", "0"])
    return command


def clean_exact_incomplete(native: Path) -> None:
    target = matrix.run_dir_from_native(native) / "scene/gs"
    # Formal heavy outputs may be explicitly staged under a uid-private /tmp
    # root.  Validate the link location itself; never accept an arbitrary
    # external path supplied as a run directory.
    HY.ensure_under_baselines(target.parent)
    if target.exists() and not matrix.valid_gs_training(native):
        if target.is_symlink():
            resolved = target.resolve()
            if resolved.exists():
                shutil.rmtree(resolved)
            resolved.mkdir(parents=True, exist_ok=True)
        else:
            shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--gpus", nargs="+", type=int, required=True)
    parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--min-free-mib", type=int, default=18000)
    parser.add_argument("--min-free-disk-gib", type=float, default=120.0)
    args = parser.parse_args()
    if len(args.gpus) != len(set(args.gpus)):
        raise ValueError("GPU ids must be unique")
    data_root = HY.PILOT_DATA_ROOT if args.phase == "pilot" else HY.DATA_ROOT
    runs = [
        run
        for domain in args.domains
        for run in HY.select_runs(
            domain, args.phase, data_root, args.spec_ids, args.seeds
        )
    ]
    natives = [run / "scene/native" for run in runs]
    pending = [native for native in natives if not matrix.valid_gs_training(native)]
    free_disk_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
    if free_disk_gib < args.min_free_disk_gib:
        print(f"HYWORLD2_TABLE4_GS_ABORT free_disk_gib={free_disk_gib:.1f}", flush=True)
        return 75
    print(
        f"HYWORLD2_TABLE4_GS_START phase={args.phase} selected={len(natives)} "
        f"pending={len(pending)} gpus={args.gpus}",
        flush=True,
    )
    tasks: queue.Queue[Path] = queue.Queue()
    for native in pending:
        tasks.put(native)
    stop = threading.Event()
    lock = threading.Lock()
    completed_count = len(natives) - len(pending)
    failures: list[dict[str, object]] = []
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

    def worker(gpu: int) -> None:
        nonlocal completed_count
        while not stop.is_set():
            try:
                native = tasks.get_nowait()
            except queue.Empty:
                return
            run_dir = matrix.run_dir_from_native(native)
            spec_id, seed, side = identity(run_dir)
            while not stop.is_set():
                free_mib = matrix.gpu_free_mib(gpu)
                free_disk_gib = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
                if (
                    free_mib >= args.min_free_mib
                    and free_disk_gib >= args.min_free_disk_gib
                ):
                    break
                print(
                    f"HYWORLD2_TABLE4_GS_WAIT gpu={gpu} free_mib={free_mib} "
                    f"free_disk_gib={free_disk_gib:.1f}",
                    flush=True,
                )
                time.sleep(15)
            if stop.is_set():
                tasks.task_done()
                return
            clean_exact_incomplete(native)
            local_scene = LOCAL_ROOT / f"gpu{gpu}" / f"{spec_id}_seed{seed}_{side}"
            if local_scene.exists():
                shutil.rmtree(local_scene)
            local_scene.mkdir(parents=True)
            shutil.copytree(native / "gs_data", local_scene / "gs_data")
            shutil.copy2(native / "meta_info.json", local_scene / "meta_info.json")
            command = command_for(run_dir, local_scene)
            log_path = LOG_ROOT / f"{spec_id}_seed{seed}_{side}_gpu{gpu}.log"
            local_log = local_scene / "train.log"
            environment = matrix.runtime_environment([gpu], "gs_training")
            local_cache = LOCAL_ROOT / "runtime/cache"
            local_tmp = LOCAL_ROOT / "runtime/tmp"
            local_cache.mkdir(parents=True, exist_ok=True)
            local_tmp.mkdir(parents=True, exist_ok=True)
            for key, relative in {
                "TORCH_HOME": "torch",
                "TORCH_EXTENSIONS_DIR": "torch_extensions",
                "TORCHINDUCTOR_CACHE_DIR": "torchinductor",
                "TRITON_CACHE_DIR": "triton",
                "CUDA_CACHE_PATH": "cuda",
                "XDG_CACHE_HOME": "xdg",
                "PYTHONPYCACHEPREFIX": "pycache",
                "MPLCONFIGDIR": "matplotlib",
            }.items():
                path = local_cache / relative
                path.mkdir(parents=True, exist_ok=True)
                environment[key] = str(path)
            staged_extensions = Path(
                f"/tmp/hyworld2_runtime_cache_uid{os.getuid()}/torch_extensions"
            )
            if (staged_extensions / "gsplat_cuda/gsplat_cuda.so").is_file():
                environment["TORCH_EXTENSIONS_DIR"] = str(staged_extensions)
            environment["TMPDIR"] = str(local_tmp)
            started_at = utc_now()
            started = time.monotonic()
            with local_log.open("a", encoding="utf-8") as log:
                log.write(f"\n[{started_at}] COMMAND {json.dumps(command)}\n")
                log.flush()
                result = subprocess.run(
                    command,
                    cwd=HY.SOURCE_ROOT / "hyworld2/worldgen",
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            shutil.copy2(local_log, log_path)
            if result.returncode == 0:
                canonical = run_dir / "scene/gs"
                if canonical.is_symlink():
                    resolved = canonical.resolve()
                    if resolved.exists():
                        shutil.rmtree(resolved)
                    shutil.copytree(local_scene / "gs", resolved)
                else:
                    if canonical.exists():
                        shutil.rmtree(canonical)
                    shutil.copytree(local_scene / "gs", canonical)
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
                    "table4_fast_50_step_profile": True,
                    "log": str(log_path.relative_to(BASELINES_ROOT)),
                },
            )
            with lock:
                if success:
                    matrix.mark_generation_complete(native)
                    completed_count += 1
                    print(
                        f"HYWORLD2_TABLE4_GS_DONE completed={completed_count}/{len(natives)} "
                        f"gpu={gpu} pair={spec_id}/seed_{seed}/{side} wall_s={elapsed:.1f}",
                        flush=True,
                    )
                    shutil.rmtree(local_scene)
                else:
                    failure = {
                        "gpu": gpu,
                        "spec_id": spec_id,
                        "seed": seed,
                        "side": side,
                        "exit_code": result.returncode,
                        "log": str(log_path),
                    }
                    failures.append(failure)
                    print(f"HYWORLD2_TABLE4_GS_ERROR {json.dumps(failure)}", flush=True)
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
        f"HYWORLD2_TABLE4_GS_END completed={len(natives) - remaining}/{len(natives)} "
        f"remaining={remaining} failures={len(failures)}",
        flush=True,
    )
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
