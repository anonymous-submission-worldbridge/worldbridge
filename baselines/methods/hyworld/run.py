#!/usr/bin/env python3
"""Resumable HY-World 2.0 Table-2 stage runner.

Every stage is filtered to incomplete scenes before the upstream batch command
is launched.  This is important because some official stages rewrite their
output directory when called, while loading their large models once per batch
is much faster than one process per scene.
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
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
RUNTIME_ROOT = BASELINES_ROOT / "hyworld2_runtime"
ADAPTER_PATH = BASELINES_ROOT / "methods/hyworld/adapter.py"
PYTHON = Path(
    os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
)
VLLM_PYTHON = Path(
    os.environ.get(
        "HYWORLD2_VLLM_PYTHON",
        BASELINES_ROOT / "envs/hyworld2-vllm-runtime/bin/python",
    )
)
VLLM_PACKAGE = (
    VLLM_PYTHON.parent.parent / "lib/python3.11/site-packages/vllm/__init__.py"
)
PANO_TRANSFORMERS_COMPAT = RUNTIME_ROOT / "pano_python_compat"
QWEN_ROOT = Path(
    os.environ.get(
        "HYWORLD2_QWEN_ROOT",
        RUNTIME_ROOT / "checkpoints/Qwen3-VL-8B-Instruct",
    )
)
STAGES = (
    "panorama",
    "trajectory_planning",
    "trajectory_rendering",
    "world_expansion",
    "gs_data",
    "gs_training",
)
GPU_COUNTS = {
    # The 80B panorama model is dispatched with Accelerate's device_map=auto.
    # Six 24-GiB GPUs plus CPU offload fit this host.  The panorama loader caps
    # checkpoint weights at 19 GiB/card so diffusion activations retain headroom.
    "panorama": 6,
    "trajectory_planning": 1,
    "trajectory_rendering": 3,
    "world_expansion": 4,
    "gs_data": 4,
    "gs_training": 4,
}
VLM_STAGES = {"trajectory_planning", "trajectory_rendering"}


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "hyworld2_adapter_runtime", ADAPTER_PATH
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_dir_from_native(native: Path) -> Path:
    return native.parents[1]


def valid_panorama(native: Path) -> bool:
    path = native / "panorama.png"
    if not path.is_file():
        return False
    try:
        with Image.open(path) as image:
            return image.size == (1920, 960) and image.mode in {"RGB", "RGBA"}
    except Exception:
        return False


def camera_paths(native: Path) -> list[Path]:
    root = native / "render_results"
    return (
        sorted(
            path
            for path in root.rglob("camera.json")
            if path.parent.name.startswith("traj")
        )
        if root.is_dir()
        else []
    )


def valid_planning(native: Path) -> bool:
    root = native / "render_results"
    navmesh = native / "navmesh"
    return (
        (root / "global_pcd.ply").is_file()
        and (root / "full_depth_prediction.pt").is_file()
        and bool(camera_paths(native))
        # A successful NavMesh pass always writes metadata and at least one
        # path family.  Reconstruction pairs are optional when the VLM finds
        # no suitable reconstruction target in a scene.
        and (navmesh / "metadata.json").is_file()
        and any(navmesh.glob("*/paths.json"))
    )


def valid_trajectory_rendering(native: Path) -> bool:
    selection = native / "render_results/selected_trajectories.json"
    if selection.is_file():
        try:
            selected = json.loads(selection.read_text(encoding="utf-8"))["selected"]
            roots = [native / "render_results" / relative for relative in selected]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return False
        return bool(roots) and all(
            (root / name).is_file()
            for root in roots
            for name in (
                "camera.json",
                "render.mp4",
                "render_mask.mp4",
                "traj_caption.json",
            )
        )
    # Formal accelerated runs always record their deterministic selection.
    # Legacy all-camera outputs without the manifest are normalized once by
    # rerunning the resumable trajectory renderer.
    return False


def valid_world_expansion(native: Path) -> bool:
    bank = native / "render_results/generation_bank_worldstereo-memory-dmd"
    return (bank / "global_pcd.ply").is_file() and (bank / "aligned_pcd.ply").is_file()


def valid_gs_data(native: Path) -> bool:
    root = native / "gs_data"
    if not all(
        (root / name).is_file()
        for name in ("points.ply", "cameras.json", "meta_info.json")
    ):
        return False
    return bool(list((root / "images").glob("*.png"))) and bool(
        list((root / "normals").glob("*.png"))
    )


def valid_gs_training(native: Path) -> bool:
    run_dir = run_dir_from_native(native)
    root = run_dir / "scene/gs"
    meta = root / "ply/position_meta_info.json"
    if not meta.is_file():
        return False
    candidates: list[tuple[int, Path]] = []
    for path in (root / "ply").glob("point_cloud_*.ply"):
        match = re.fullmatch(r"point_cloud_(\d+)\.ply", path.name)
        if match and path.is_file():
            candidates.append((int(match.group(1)), path))
    # Accelerated training ends at step 499.  Accept the newest internally
    # consistent PLY/checkpoint pair instead of hard-coding the official
    # 1999-step artifact and accidentally rerunning valid scenes.
    return any(
        list((root / "ckpts").glob(f"ckpt_{step}_rank*.pt"))
        for step, _ in sorted(candidates, reverse=True)
    )


VALIDATORS: dict[str, Callable[[Path], bool]] = {
    "panorama": valid_panorama,
    "trajectory_planning": valid_planning,
    "trajectory_rendering": valid_trajectory_rendering,
    "world_expansion": valid_world_expansion,
    "gs_data": valid_gs_data,
    "gs_training": valid_gs_training,
}


def stage_state(native: Path) -> dict[str, bool]:
    state: dict[str, bool] = {}
    prerequisite = True
    for stage in STAGES:
        current = prerequisite and VALIDATORS[stage](native)
        state[stage] = current
        prerequisite = current
    return state


def make_stage_workset(natives: list[Path], trial: str, stage: str) -> Path:
    # Selected native paths are already absolute; resolving 200 NFS paths here
    # serialized hundreds of unnecessary metadata RPCs on every restart.
    payload = "\n".join(str(path) for path in natives).encode()
    key = hashlib.sha256(payload).hexdigest()[:12]
    root = RUNTIME_ROOT / "worksets/stages" / f"{trial}_{stage}_{key}"
    manifest_path = root.with_suffix(".json")
    expected_scenes = [str(path) for path in natives]
    if root.is_dir() and manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                existing.get("trial") == trial
                and existing.get("stage") == stage
                and existing.get("scenes") == expected_scenes
                and len(list(root.iterdir())) == len(natives)
            ):
                return root
        except (OSError, TypeError, json.JSONDecodeError):
            pass
    root.mkdir(parents=True, exist_ok=True)
    for index, native in enumerate(natives):
        link = root / f"scene_{index:04d}"
        if link.is_symlink():
            if link.resolve() != native.resolve():
                raise RuntimeError(f"Mismatched workset link: {link}")
        elif link.exists():
            raise RuntimeError(f"Unexpected non-link workset entry: {link}")
        else:
            link.symlink_to(native.resolve(), target_is_directory=True)
    expected = {f"scene_{index:04d}" for index in range(len(natives))}
    actual = {path.name for path in root.iterdir()}
    if actual != expected:
        raise RuntimeError(
            f"Stage workset has unexpected entries: {sorted(actual - expected)}"
        )
    atomic_json(
        manifest_path, {"trial": trial, "stage": stage, "scenes": expected_scenes}
    )
    return root


def gpu_free_mib(gpu: int) -> int:
    result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(5):
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
        values: dict[int, int] = {}
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                fields = [field.strip() for field in line.split(",")]
                if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit():
                    values[int(fields[0])] = int(fields[1])
        if gpu in values:
            return values[gpu]
        if attempt < 4:
            time.sleep(1)
    assert result is not None
    print(
        f"HYWORLD2_WARN nvidia_smi_unavailable gpu={gpu} rc={result.returncode}; "
        "continuing because CUDA availability is validated by the stage process",
        flush=True,
    )
    return 1 << 30


def runtime_environment(gpus: list[int], stage: str | None = None) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(HY.runtime_environment())
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": ",".join(str(gpu) for gpu in gpus),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
            "PATH": f"{PYTHON.parent}:{environment.get('PATH', '')}",
        }
    )
    if stage == "panorama":
        # The repository intentionally pins transformers 5.2 for worldgen but
        # 4.57.1 for panogen.  Reuse the already installed 4.57.6 package-only
        # overlay so torch/torchvision continue to come from the HY environment.
        environment[
            "PYTHONPATH"
        ] = f"{PANO_TRANSFORMERS_COMPAT}:{environment.get('PYTHONPATH', '')}"
    return environment


def vllm_environment(gpu: int) -> dict[str, str]:
    """Build an isolated environment for the separately pinned vLLM venv."""
    environment = dict(os.environ)
    cache = RUNTIME_ROOT / "cache"
    private_cache = cache / f"uid_{os.getuid()}" / "vllm_runtime"
    # ZeroMQ IPC sockets have a 107-byte Unix-domain path limit.  Keep this
    # inside baselines, but deliberately short enough for vLLM's UUID suffix.
    private_tmp = BASELINES_ROOT / ".vtmp" / str(os.getuid())
    for path in (
        cache / "huggingface",
        cache / "huggingface/hub",
        cache / "torch",
        private_cache / "vllm",
        private_cache / "triton",
        private_cache / "torchinductor",
        private_cache / "cuda",
        private_cache / "xdg",
        private_tmp,
    ):
        path.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HOME": str(cache / "huggingface"),
            "HF_HUB_CACHE": str(cache / "huggingface/hub"),
            "HUGGINGFACE_HUB_CACHE": str(cache / "huggingface/hub"),
            "TORCH_HOME": str(cache / "torch"),
            "VLLM_CACHE_ROOT": str(private_cache / "vllm"),
            "TRITON_CACHE_DIR": str(private_cache / "triton"),
            "TORCHINDUCTOR_CACHE_DIR": str(private_cache / "torchinductor"),
            "CUDA_CACHE_PATH": str(private_cache / "cuda"),
            "XDG_CACHE_HOME": str(private_cache / "xdg"),
            "TMPDIR": str(private_tmp),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONUNBUFFERED": "1",
            "PATH": f"{VLLM_PYTHON.parent}:{environment.get('PATH', '')}",
        }
    )
    # Never leak the HY generation environment's site-package overlay into
    # vLLM: its compiled wheel has a separately pinned torch/transformers ABI.
    environment.pop("PYTHONPATH", None)
    return environment


def llm_health(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def start_vllm(
    gpu: int,
    port: int,
    max_model_len: int,
    timeout_s: int,
) -> tuple[subprocess.Popen[str], Path]:
    if not VLLM_PYTHON.is_file() or not VLLM_PACKAGE.is_file():
        raise RuntimeError(
            f"Incomplete isolated vLLM environment: {VLLM_PYTHON.parent.parent}"
        )
    if not (QWEN_ROOT / "config.json").is_file():
        raise RuntimeError(f"Missing local Qwen checkpoint: {QWEN_ROOT}")
    if not port_is_free(port):
        raise RuntimeError(
            f"LLM port {port} is already occupied; use --external-llm to reuse a server"
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Logs copied from another machine may be owned by a different uid.  Keep
    # new service logs in a uid-private sibling so resumptions never depend on
    # changing ownership or permissions of earlier experiment records.
    log_path = (
        RUNTIME_ROOT / "logs" / f"vllm_uid_{os.getuid()}" / f"qwen_gpu{gpu}_{stamp}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(VLLM_PYTHON),
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        str(QWEN_ROOT),
        "--served-model-name",
        "Qwen/Qwen3-VL-8B-Instruct",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--tensor-parallel-size",
        "1",
        "--pipeline-parallel-size",
        "1",
        "--max-model-len",
        str(max_model_len),
        "--gpu-memory-utilization",
        "0.90",
        "--trust-remote-code",
    ]
    log = log_path.open("a", encoding="utf-8")
    log.write(f"\n[{utc_now()}] COMMAND {json.dumps(command)}\n")
    log.flush()
    try:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=vllm_environment(gpu),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    finally:
        log.close()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"vLLM exited with code {exit_code}; see {log_path}")
        if llm_health(port):
            print(
                f"HYWORLD2_VLLM_READY gpu={gpu} port={port} log={log_path}",
                flush=True,
            )
            return process, log_path
        time.sleep(2)
    stop_process_group(process)
    raise RuntimeError(
        f"vLLM did not become healthy within {timeout_s}s; see {log_path}"
    )


def stop_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def append_attempt(native: Path, record: dict[str, Any]) -> None:
    path = run_dir_from_native(native) / "run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    record.setdefault("protocol_sha256", manifest.get("protocol_sha256"))
    manifest.setdefault("attempts", []).append(record)
    manifest["last_stage"] = record["stage"]
    manifest["last_updated_at_utc"] = utc_now()
    atomic_json(path, manifest)


def mark_generation_complete(native: Path) -> None:
    run_dir = run_dir_from_native(native)
    marker = run_dir / "GENERATION_SUCCESS"
    marker.write_text("hyworld2 six-stage output contract valid\n", encoding="utf-8")
    path = run_dir / "run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["generation_success"] = True
    manifest["failure_reason"] = None
    manifest["generation_completed_at_utc"] = utc_now()
    atomic_json(path, manifest)


def run_logged(
    command: list[str], log_path: Path, environment: dict[str, str]
) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{utc_now()}] COMMAND {json.dumps(command)}\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGINT)
            try:
                exit_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                exit_code = process.wait()
            raise
    return exit_code, time.monotonic() - started


def select_natives(args: argparse.Namespace) -> list[Path]:
    natives: list[Path] = []
    for domain in args.domains:
        runs = HY.select_runs(
            domain,
            args.trial,
            HY.DATA_ROOT,
            args.spec_ids,
            args.seeds,
        )
        natives.extend(run / "scene/native" for run in runs)
    return natives


def command_for_stage(
    stage: str, workset: Path, native: Path | None, llm_port: int
) -> list[str]:
    if stage == "gs_training":
        if native is None:
            raise ValueError("gs_training requires one native scene")
        return HY.gs_train_command(run_dir_from_native(native))
    return HY.stage_commands(workset, llm_port)[stage]


def audit(natives: list[Path]) -> int:
    rows = []
    for native in natives:
        run_dir = run_dir_from_native(native)
        manifest = json.loads(
            (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        rows.append(
            {
                "domain": manifest["domain"],
                "spec_id": manifest["spec_id"],
                "seed": manifest["logical_seed"],
                "stages": stage_state(native),
            }
        )
    summary = {stage: sum(row["stages"][stage] for row in rows) for stage in STAGES}
    print(json.dumps({"runs": len(rows), "summary": summary, "rows": rows}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(*STAGES, "audit"), required=True)
    parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--gpus", nargs="+", type=int, default=[])
    parser.add_argument("--panorama-min-gpus", type=int, default=6)
    parser.add_argument("--panorama-gpu-max-memory-gib", type=int, default=19)
    parser.add_argument(
        "--panorama-device-map", choices=("auto", "four_gpu_resident"), default="auto"
    )
    parser.add_argument("--llm-gpu", type=int)
    parser.add_argument("--llm-port", type=int, default=18080)
    parser.add_argument("--external-llm", action="store_true")
    parser.add_argument("--vllm-max-model-len", type=int, default=8192)
    parser.add_argument("--vllm-startup-timeout", type=int, default=900)
    parser.add_argument("--min-free-mib", type=int, default=20000)
    parser.add_argument("--llm-min-free-mib", type=int, default=22000)
    parser.add_argument("--min-free-disk-gib", type=float, default=300.0)
    args = parser.parse_args()

    if len(set(args.gpus)) != len(args.gpus) or any(
        gpu not in range(8) for gpu in args.gpus
    ):
        raise ValueError("GPU ids must be unique values in 0..7")
    if args.llm_gpu is not None and args.llm_gpu not in range(8):
        raise ValueError("LLM GPU id must be in 0..7")
    if args.seeds is not None:
        allowed = set(HY.PHASE_SEEDS[args.trial])
        if not set(args.seeds).issubset(allowed):
            raise ValueError(f"Seeds must be selected from {sorted(allowed)}")
    natives = select_natives(args)
    if args.stage == "audit":
        return audit(natives)
    required_gpus = GPU_COUNTS[args.stage]
    if args.stage == "panorama":
        required_gpus = args.panorama_min_gpus
        if not 1 <= required_gpus <= 8 or args.panorama_gpu_max_memory_gib < 1:
            raise ValueError("Invalid panorama runtime memory configuration")
        if not required_gpus <= len(args.gpus) <= 8:
            raise ValueError(
                f"panorama requires {required_gpus}..8 visible GPUs for automatic dispatch"
            )
    elif (
        args.stage == "trajectory_rendering"
        and not 1 <= len(args.gpus) <= required_gpus
    ):
        raise ValueError("trajectory_rendering requires 1..3 visible GPUs")
    elif args.stage == "world_expansion" and len(args.gpus) not in {2, 4}:
        # Sequence-parallel attention has 16 heads, so its world size must
        # divide 16.  Two A6000s retain enough FSDP activation headroom when a
        # stable fourth card is unavailable.
        raise ValueError("world_expansion requires 2 or 4 visible GPUs")
    elif (
        args.stage not in {"trajectory_rendering", "world_expansion"}
        and len(args.gpus) != required_gpus
    ):
        raise ValueError(f"{args.stage} requires exactly {required_gpus} visible GPUs")
    if args.stage in VLM_STAGES:
        if args.external_llm:
            if args.llm_gpu is not None:
                raise ValueError("--external-llm and --llm-gpu are mutually exclusive")
        elif args.llm_gpu is None:
            raise ValueError(f"{args.stage} requires --llm-gpu or --external-llm")
        elif args.llm_gpu in args.gpus:
            raise ValueError("The LLM GPU must be distinct from the generation GPUs")
    elif args.llm_gpu is not None or args.external_llm:
        raise ValueError("LLM options are only valid for planning/rendering stages")
    free_disk = shutil.disk_usage(BASELINES_ROOT).free / (1024**3)
    if free_disk < args.min_free_disk_gib:
        print(f"HYWORLD2_ABORT free_disk_gib={free_disk:.1f}", flush=True)
        return 75
    free = {gpu: gpu_free_mib(gpu) for gpu in args.gpus}
    low = {gpu: mib for gpu, mib in free.items() if mib < args.min_free_mib}
    if low:
        print(f"HYWORLD2_ABORT low_gpu_memory={low}", flush=True)
        return 75
    if args.llm_gpu is not None:
        llm_free = gpu_free_mib(args.llm_gpu)
        if llm_free < args.llm_min_free_mib:
            print(
                f"HYWORLD2_ABORT low_llm_gpu_memory={{'{args.llm_gpu}': {llm_free}}}",
                flush=True,
            )
            return 75

    # A stage's own final artifacts are sufficient for resumability.  Walking
    # every earlier stage (including image opens and recursive trajectory
    # globs) made each restart spend minutes on shared-filesystem metadata.
    pending = [native for native in natives if not VALIDATORS[args.stage](native)]
    print(
        f"HYWORLD2_STAGE_START stage={args.stage} selected={len(natives)} pending={len(pending)} "
        f"gpus={args.gpus} free_mib={free} free_disk_gib={free_disk:.1f}",
        flush=True,
    )
    if not pending:
        print(
            f"HYWORLD2_STAGE_COMPLETE stage={args.stage} pending=0 failures=0",
            flush=True,
        )
        return 0
    stage_index = STAGES.index(args.stage)
    if stage_index:
        prerequisite = STAGES[stage_index - 1]
        blocked = [native for native in pending if not VALIDATORS[prerequisite](native)]
        if blocked:
            print(
                f"HYWORLD2_ABORT prerequisite={prerequisite} incomplete={len(blocked)}",
                flush=True,
            )
            return 2
    workset = make_stage_workset(pending, args.trial, args.stage)
    environment = runtime_environment(args.gpus, args.stage)
    failures = 0
    batches = (
        [[native] for native in pending] if args.stage == "gs_training" else [pending]
    )
    llm_process: subprocess.Popen[str] | None = None
    try:
        if args.stage in VLM_STAGES:
            if args.external_llm:
                if not llm_health(args.llm_port):
                    raise RuntimeError(
                        f"External LLM is not healthy on port {args.llm_port}"
                    )
                print(f"HYWORLD2_VLLM_REUSE port={args.llm_port}", flush=True)
            else:
                assert args.llm_gpu is not None
                llm_process, _ = start_vllm(
                    args.llm_gpu,
                    args.llm_port,
                    args.vllm_max_model_len,
                    args.vllm_startup_timeout,
                )
        for batch_index, batch in enumerate(batches):
            native = batch[0] if args.stage == "gs_training" else None
            command = command_for_stage(args.stage, workset, native, args.llm_port)
            if args.stage in {"trajectory_rendering", "world_expansion"}:
                # Both distributed stages support arbitrary world sizes.  Match
                # torchrun to the currently available, explicitly selected cards.
                command[command.index("--nproc_per_node") + 1] = str(len(args.gpus))
            if args.stage == "panorama":
                command.extend(
                    [
                        "--gpu-max-memory-gib",
                        str(args.panorama_gpu_max_memory_gib),
                        "--device-map",
                        args.panorama_device_map,
                    ]
                )
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            log_path = (
                RUNTIME_ROOT
                / "logs"
                / f"{args.trial}_{args.stage}_{batch_index:04d}_{stamp}_pid{os.getpid()}.log"
            )
            started_at = utc_now()
            exit_code, wall_time = run_logged(command, log_path, environment)
            for item in batch:
                success = VALIDATORS[args.stage](item)
                # On a monolithic batch failure, do not issue hundreds of NFS
                # read/modify/write operations for scenes the child never
                # reached.  Successful artifacts are independently validated
                # and remain fully recorded/resumable.
                if args.stage != "panorama" and (exit_code == 0 or success):
                    append_attempt(
                        item,
                        {
                            "stage": args.stage,
                            "started_at_utc": started_at,
                            "ended_at_utc": utc_now(),
                            "wall_time_s": wall_time,
                            "exit_code": exit_code,
                            "success": success,
                            "physical_gpus": args.gpus,
                            "llm_gpu": args.llm_gpu,
                            "log": str(log_path.relative_to(BASELINES_ROOT)),
                        },
                    )
                if success and args.stage == "gs_training":
                    mark_generation_complete(item)
                if not success and exit_code == 0:
                    failures += 1
            print(
                f"HYWORLD2_BATCH_END stage={args.stage} batch={batch_index} exit={exit_code} "
                f"validated={sum(VALIDATORS[args.stage](item) for item in batch)}/{len(batch)} "
                f"wall_time_s={wall_time:.1f} log={log_path}",
                flush=True,
            )
            if exit_code != 0:
                break
    finally:
        if llm_process is not None:
            stop_process_group(llm_process)
            print("HYWORLD2_VLLM_STOPPED", flush=True)
    # The stage validator is sufficient here.  Re-walking all prerequisite
    # stages after a batch failure performs thousands of redundant NFS stats
    # and can leave the launcher blocked for minutes on a busy shared volume.
    remaining = sum(not VALIDATORS[args.stage](native) for native in natives)
    print(
        f"HYWORLD2_STAGE_COMPLETE stage={args.stage} remaining={remaining} failures={failures}",
        flush=True,
    )
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
