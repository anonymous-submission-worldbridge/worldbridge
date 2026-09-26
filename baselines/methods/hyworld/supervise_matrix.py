#!/usr/bin/env python3
"""Wait for genuinely idle GPUs and resume a selected HY-World 2.0 matrix."""

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
import os
import subprocess
import sys
import time
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
PYTHON = BASELINES_ROOT / "envs/hyworld2/bin/python"
RUNNER = BASELINES_ROOT / "methods/hyworld/run.py"
RENDERER = BASELINES_ROOT / "methods/hyworld/tools/render_hyworld_generation.py"
STAGES = (
    "panorama",
    "trajectory_planning",
    "trajectory_rendering",
    "world_expansion",
    "gs_data",
    "gs_training",
)
GPU_COUNTS = {
    "panorama": 6,
    "trajectory_planning": 1,
    "trajectory_rendering": 3,
    "world_expansion": 4,
    "gs_data": 4,
    "gs_training": 4,
    "canonical_render": 1,
}
VLM_STAGES = {"trajectory_planning", "trajectory_rendering"}


class Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, value):
        self.log.write(value)
        return self.stream.write(value)

    def flush(self):
        self.log.flush()
        self.stream.flush()


def load_adapter():
    path = BASELINES_ROOT / "methods/hyworld/adapter.py"
    spec = importlib.util.spec_from_file_location("hyworld2_supervisor_adapter", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()


def load_matrix_runner():
    spec = importlib.util.spec_from_file_location("hyworld2_supervisor_runner", RUNNER)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATRIX = load_matrix_runner()


def gpu_rows() -> list[dict[str, int]]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"nvidia-smi failed: {completed.stderr.strip()}")
    rows = []
    for line in completed.stdout.splitlines():
        index, free, used, utilization = (
            int(value.strip()) for value in line.split(",")
        )
        rows.append(
            {"index": index, "free": free, "used": used, "utilization": utilization}
        )
    return rows


def idle_gpus(
    allowlist: set[int], min_free_mib: int, max_used_mib: int, max_utilization: int
) -> list[int]:
    rows = [
        row
        for row in gpu_rows()
        if row["index"] in allowlist
        and row["free"] >= min_free_mib
        and row["used"] <= max_used_mib
        and row["utilization"] <= max_utilization
    ]
    rows.sort(key=lambda row: (-row["free"], row["index"]))
    return [row["index"] for row in rows]


def stably_idle_gpus(
    current_idle: list[int],
    idle_since: dict[int, float],
    now: float,
    minimum_seconds: float,
) -> list[int]:
    """Return GPUs that stayed idle continuously across the stability window."""
    current = set(current_idle)
    for gpu in list(idle_since):
        if gpu not in current:
            idle_since.pop(gpu)
    for gpu in current_idle:
        idle_since.setdefault(gpu, now)
    return [gpu for gpu in current_idle if now - idle_since[gpu] >= minimum_seconds]


def selected_runs(args: argparse.Namespace) -> list[Path]:
    return [
        run
        for domain in args.domains
        for run in HY.select_runs(
            domain,
            args.trial,
            HY.DATA_ROOT,
            args.spec_ids,
            args.seeds,
        )
    ]


def stage_ready(stage: str) -> tuple[bool, list[str]]:
    required: dict[str, list[Path]] = {
        "panorama": [
            HY.PANO_MODEL_ROOT / "HY-Pano-2.0/config.json",
            HY.PANO_MODEL_ROOT / "HY-Pano-2.0/model-00032-of-00032.safetensors",
        ],
        "trajectory_planning": [
            HY.MOGE_MODEL_PATH,
            HY.SAM3_ROOT / "config.json",
            HY.GROUNDING_DINO_ROOT / "config.json",
            HY.ZIM_ROOT / "zim_vit_l_2092/encoder.onnx",
            HY.ZIM_ROOT / "zim_vit_l_2092/decoder.onnx",
            BASELINES_ROOT
            / "envs/hyworld2-vllm-runtime/lib/python3.11/site-packages/vllm/__init__.py",
            HY.QWEN_VLM_ROOT / "config.json",
        ],
        "trajectory_rendering": [
            BASELINES_ROOT
            / "envs/hyworld2-vllm-runtime/lib/python3.11/site-packages/vllm/__init__.py",
            HY.QWEN_VLM_ROOT / "config.json",
        ],
        "world_expansion": [
            HY.WORLDSTEREO_ROOT / "worldstereo-memory-dmd/model.safetensors",
            HY.WAN_BASE_ROOT / "model_index.json",
            HY.WAN_BASE_ROOT / "vae/diffusion_pytorch_model.safetensors",
            HY.WAN_BASE_ROOT
            / "transformer/diffusion_pytorch_model-00014-of-00014.safetensors",
        ],
        "gs_data": [HY.MOGE_MODEL_PATH],
        "gs_training": [],
        "canonical_render": [],
    }
    missing = [str(path) for path in required[stage] if not path.is_file()]
    return not missing, missing


def stage_complete(stage: str, runs: list[Path]) -> bool:
    if stage == "canonical_render":
        return all(
            (run / "SUCCESS").is_file() or (run / "RENDER_QUALITY_FAILURE").is_file()
            for run in runs
        )
    return all(MATRIX.stage_state(run / "scene/native")[stage] for run in runs)


def stage_command(
    args: argparse.Namespace, stage: str, gpus: list[int], llm_gpu: int | None
) -> list[str]:
    command = [
        str(PYTHON),
        str(RUNNER),
        "--stage",
        stage,
        "--trial",
        args.trial,
        "--domains",
        *args.domains,
    ]
    if args.spec_ids:
        command.extend(["--spec-ids", *args.spec_ids])
    if args.seeds:
        command.extend(["--seeds", *(str(seed) for seed in args.seeds)])
    command.extend(["--gpus", *(str(gpu) for gpu in gpus)])
    if stage == "panorama":
        mode = args.panorama_device_map
        if mode == "adaptive":
            mode = "four_gpu_resident" if len(gpus) == 4 else "auto"
        command.extend(
            [
                "--panorama-min-gpus",
                str(args.panorama_min_gpus),
                "--panorama-gpu-max-memory-gib",
                str(args.panorama_gpu_max_memory_gib),
                "--panorama-device-map",
                mode,
            ]
        )
    if llm_gpu is not None:
        command.extend(["--llm-gpu", str(llm_gpu)])
    return command


def run_stage(
    args: argparse.Namespace, stage: str, gpus: list[int], llm_gpu: int | None
) -> int:
    command = stage_command(args, stage, gpus, llm_gpu)
    print(
        f"HYWORLD2_SUPERVISOR_LAUNCH stage={stage} gpus={gpus} llm_gpu={llm_gpu}",
        flush=True,
    )
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def render_selected(args: argparse.Namespace, runs: list[Path], gpu: int) -> int:
    environment = dict(os.environ)
    environment.update(HY.runtime_environment())
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    failures = 0
    for run in runs:
        if (run / "SUCCESS").is_file() or (run / "RENDER_QUALITY_FAILURE").is_file():
            continue
        completed = subprocess.run(
            [str(PYTHON), str(RENDERER), "--run-dir", str(run)],
            cwd=REPO_ROOT,
            env=environment,
            check=False,
        )
        # Code 2 is a frozen quality-validator failure, not infrastructure.
        if completed.returncode not in {0, 2}:
            failures += 1
            break
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    parser.add_argument("--spec-ids", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--allowed-gpus", nargs="+", type=int, default=list(range(8)))
    parser.add_argument("--panorama-min-gpus", type=int, default=6)
    parser.add_argument("--panorama-gpu-max-memory-gib", type=int, default=19)
    parser.add_argument(
        "--panorama-device-map",
        choices=("auto", "four_gpu_resident", "adaptive"),
        default="auto",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--min-free-mib", type=int, default=20000)
    parser.add_argument("--llm-min-free-mib", type=int, default=22000)
    parser.add_argument("--max-used-mib", type=int, default=512)
    parser.add_argument("--max-utilization", type=int, default=5)
    parser.add_argument("--stable-idle-seconds", type=int, default=180)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--state-file", type=Path)
    args = parser.parse_args()
    if args.log_file:
        log_path = HY.ensure_under_baselines(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a", buffering=1)
        sys.stdout = Tee(sys.stdout, log)
        sys.stderr = Tee(sys.stderr, log)
    state_path = HY.ensure_under_baselines(args.state_file) if args.state_file else None

    def save_state(status, **details):
        if state_path:
            MATRIX.atomic_json(
                state_path,
                {
                    "pid": os.getpid(),
                    "updated_at_utc": MATRIX.utc_now(),
                    "trial": args.trial,
                    "domains": args.domains,
                    "spec_ids": args.spec_ids,
                    "seeds": args.seeds,
                    "allowed_gpus": args.allowed_gpus,
                    "status": status,
                    **details,
                },
            )

    allowlist = set(args.allowed_gpus)
    if not allowlist or not allowlist.issubset(set(range(8))):
        raise ValueError("allowed GPU ids must be a nonempty subset of 0..7")
    if not 5 <= args.poll_seconds <= 60:
        raise ValueError("poll-seconds must be between 5 and 60")
    if args.stable_idle_seconds < 0:
        raise ValueError("stable-idle-seconds must be nonnegative")
    if not 1 <= args.panorama_min_gpus <= 8 or args.panorama_gpu_max_memory_gib < 1:
        raise ValueError("Invalid panorama runtime memory configuration")
    if args.panorama_device_map == "adaptive" and args.panorama_min_gpus != 3:
        raise ValueError("adaptive panorama scheduling requires --panorama-min-gpus 3")
    runs = selected_runs(args)
    save_state("started", runs=len(runs))
    print(f"HYWORLD2_SUPERVISOR_START trial={args.trial} runs={len(runs)}", flush=True)

    for stage in (*STAGES, "canonical_render"):
        if stage_complete(stage, runs):
            print(f"HYWORLD2_SUPERVISOR_SKIP stage={stage} complete=1", flush=True)
            continue
        idle_since: dict[int, float] = {}
        while True:
            ready, missing = stage_ready(stage)
            if not ready:
                save_state("waiting_for_dependencies", stage=stage, missing=missing)
                print(
                    f"HYWORLD2_SUPERVISOR_WAIT stage={stage} missing={missing}",
                    flush=True,
                )
                time.sleep(args.poll_seconds)
                continue
            requested = GPU_COUNTS[stage]
            if stage == "panorama":
                requested = args.panorama_min_gpus
            current_idle = idle_gpus(
                allowlist, args.min_free_mib, args.max_used_mib, args.max_utilization
            )
            idle = stably_idle_gpus(
                current_idle,
                idle_since,
                time.monotonic(),
                args.stable_idle_seconds,
            )
            needed = requested + int(stage in VLM_STAGES)
            if len(idle) < needed:
                save_state(
                    "waiting_for_gpus",
                    stage=stage,
                    current_idle=current_idle,
                    stable_idle=idle,
                    needed=needed,
                )
                print(
                    f"HYWORLD2_SUPERVISOR_WAIT stage={stage} current_idle={current_idle} "
                    f"stable_idle={idle} needed={needed}",
                    flush=True,
                )
                time.sleep(args.poll_seconds)
                continue
            llm_gpu = None
            if stage in VLM_STAGES:
                current_llm_candidates = idle_gpus(
                    allowlist,
                    args.llm_min_free_mib,
                    args.max_used_mib,
                    args.max_utilization,
                )
                llm_candidates = [gpu for gpu in idle if gpu in current_llm_candidates]
                if not llm_candidates:
                    print(
                        f"HYWORLD2_SUPERVISOR_WAIT stage={stage} no_idle_llm_gpu",
                        flush=True,
                    )
                    time.sleep(args.poll_seconds)
                    continue
                llm_gpu = llm_candidates[0]
                idle = [gpu for gpu in idle if gpu != llm_gpu]
                if len(idle) < requested:
                    time.sleep(args.poll_seconds)
                    continue
            if stage == "panorama":
                # Accelerate dispatches the 80B model over every visible GPU
                # and spills the remainder to CPU.  Opportunistically use all
                # genuinely idle cards to minimize that spill.
                if args.panorama_device_map in {"four_gpu_resident", "adaptive"}:
                    requested = min(4, len(idle))
                else:
                    requested = min(8, len(idle))
            stage_gpus = idle[:requested]
            save_state("running", stage=stage, gpus=stage_gpus, llm_gpu=llm_gpu)
            if stage == "canonical_render":
                code = render_selected(args, runs, stage_gpus[0])
            else:
                code = run_stage(args, stage, stage_gpus, llm_gpu)
            if code == 75:
                print(
                    f"HYWORLD2_SUPERVISOR_RACE stage={stage}; retrying resource gate",
                    flush=True,
                )
                time.sleep(args.poll_seconds)
                continue
            if code != 0:
                save_state("failed", stage=stage, exit_code=code)
                print(f"HYWORLD2_SUPERVISOR_STOP stage={stage} exit={code}", flush=True)
                return code
            break
    print(
        f"HYWORLD2_SUPERVISOR_COMPLETE trial={args.trial} runs={len(runs)}", flush=True
    )
    save_state("complete", runs=len(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
