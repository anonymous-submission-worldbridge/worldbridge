#!/usr/bin/env python3
"""Resource-gated supervisor for the HY-World 2.0 Table-4 matrix."""

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


import importlib.util
import os
import subprocess
import sys
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
TABLE4_ROOT = _BASELINE_PROJECT_ROOT / "baselines/methods/hyworld/unified/native"
CONFIG_MIN_FREE_DISK_GIB = 120.0
sys.path.insert(0, str(BASELINES_ROOT))

import baselines.methods.hyworld.supervise_matrix as supervisor  # noqa: E402


supervisor.PYTHON = Path(
    os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
)


def load_adapter():
    path = TABLE4_ROOT / "adapters/hyworld.py"
    spec = importlib.util.spec_from_file_location("table4_supervisor_adapter", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()
supervisor.HY = HY
supervisor.MATRIX.HY = HY
supervisor.RUNNER = TABLE4_ROOT / "run_hyworld_matrix.py"
# The user explicitly authorized capacity-based GPU sharing on 2026-09-10.
# Capacity-qualified A6000s are sorted by free memory. The runner gives the
# first visible card extra VAE-decode headroom and derives every checkpoint
# placement cap from the free memory measured immediately before dispatch.
# Generated samples, seeds, model and inference steps do not change; only
# Accelerate's device placement changes.
supervisor.GPU_COUNTS["panorama"] = 2
supervisor.GPU_COUNTS["trajectory_rendering"] = 1
supervisor.GPU_COUNTS["world_expansion"] = 2
supervisor.GPU_COUNTS["gs_data"] = 2
supervisor.GPU_COUNTS["gs_training"] = 1


def capacity_gpus(
    allowlist: set[int], min_free_mib: int, max_used_mib: int, max_utilization: int
) -> list[int]:
    """Select by remaining memory only, as explicitly requested by the user."""
    del max_used_mib, max_utilization
    rows = [
        row
        for row in supervisor.gpu_rows()
        if row["index"] in allowlist and row["free"] >= min_free_mib
    ]
    rows.sort(key=lambda row: (-row["free"], row["index"]))
    return [row["index"] for row in rows]


supervisor.idle_gpus = capacity_gpus


_shared_run_stage = supervisor.run_stage


def run_stage(args, stage: str, gpus: list[int], llm_gpu: int | None) -> int:
    if stage != "gs_training":
        return _shared_run_stage(args, stage, gpus, llm_gpu)
    command = [
        str(supervisor.PYTHON),
        str((TABLE4_ROOT / "run_hyworld_gs_parallel.py")),
        "--phase",
        args.trial,
        "--domains",
        *args.domains,
        "--gpus",
        *(str(gpu) for gpu in gpus),
        "--min-free-mib",
        str(args.min_free_mib),
        "--min-free-disk-gib",
        str(CONFIG_MIN_FREE_DISK_GIB),
    ]
    if args.spec_ids:
        command.extend(["--spec-ids", *args.spec_ids])
    if args.seeds:
        command.extend(["--seeds", *(str(seed) for seed in args.seeds)])
    print(f"HYWORLD2_TABLE4_GS_LAUNCH gpus={gpus}", flush=True)
    return subprocess.run(command, cwd=supervisor.REPO_ROOT, check=False).returncode


supervisor.run_stage = run_stage


_shared_stage_command = supervisor.stage_command


def stage_command(args, stage: str, gpus: list[int], llm_gpu: int | None) -> list[str]:
    """Propagate the Table-4 disk gate and optionally reuse a local VLM."""
    command = _shared_stage_command(args, stage, gpus, llm_gpu)
    command.extend(["--min-free-disk-gib", str(args.min_free_disk_gib)])
    if stage in supervisor.VLM_STAGES and args.external_llm:
        command.extend(["--external-llm", "--llm-port", str(args.llm_port)])
    return command


supervisor.stage_command = stage_command


_shared_main = supervisor.main


def main() -> int:
    global CONFIG_MIN_FREE_DISK_GIB
    # The shared supervisor's parser is intentionally kept unchanged for the
    # Table-2 run.  Table 4 accepts these two operational flags through a small
    # argv translation and exposes them to the patched scheduling functions.
    external_llm = "--external-llm" in sys.argv
    llm_port = 18080
    min_free_disk_gib = 120.0
    translated = list(sys.argv)
    if external_llm:
        translated.remove("--external-llm")
    for option, cast, default in (
        ("--llm-port", int, llm_port),
        ("--min-free-disk-gib", float, min_free_disk_gib),
    ):
        if option in translated:
            position = translated.index(option)
            value = cast(translated[position + 1])
            del translated[position : position + 2]
        else:
            value = default
        if option == "--llm-port":
            llm_port = value
        else:
            min_free_disk_gib = value
    CONFIG_MIN_FREE_DISK_GIB = min_free_disk_gib

    original_argv = sys.argv
    original_vlm_stages = supervisor.VLM_STAGES
    original_stage_command = supervisor.stage_command
    try:
        sys.argv = translated
        # An already healthy local service consumes no additional scheduling
        # GPU.  The runner performs the health check before each VLM stage.
        if external_llm:
            supervisor.VLM_STAGES = set()

        def configured_stage_command(args, stage, gpus, llm_gpu):
            args.external_llm = external_llm
            args.llm_port = llm_port
            args.min_free_disk_gib = min_free_disk_gib
            command = original_stage_command(args, stage, gpus, llm_gpu)
            if external_llm and stage in original_vlm_stages:
                command.extend(["--external-llm", "--llm-port", str(llm_port)])
            return command

        supervisor.stage_command = configured_stage_command
        return _shared_main()
    finally:
        supervisor.stage_command = original_stage_command
        supervisor.VLM_STAGES = original_vlm_stages
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
