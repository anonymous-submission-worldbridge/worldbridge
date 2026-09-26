#!/usr/bin/env python3
"""Use the audited Table-2 HY runtime with Table-4 pair inputs."""

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


import hashlib
import importlib.util
import os
import sys
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES_ROOT))

import baselines.methods.hyworld.run as matrix  # noqa: E402


_local_pano_compat = os.environ.get("HYWORLD2_PANO_TRANSFORMERS_COMPAT")
if _local_pano_compat:
    matrix.PANO_TRANSFORMERS_COMPAT = Path(_local_pano_compat)


def load_table4_adapter():
    path = (
        _BASELINE_PROJECT_ROOT
        / "baselines/methods/hyworld/unified/native/adapters/hyworld.py"
    )
    spec = importlib.util.spec_from_file_location(
        "hyworld2_table4_runtime_adapter", path
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matrix.HY = load_table4_adapter()
# The Table-4 capacity-sharing amendment permits two-rank gs-data export.
# gen_gs_data partitions independent scenes by rank and has no four-rank-only
# collective; the shared runner's command is adjusted below to the selected
# world size, exactly as for its other distributed stages.
matrix.GPU_COUNTS["gs_data"] = 2


_shared_make_stage_workset = matrix.make_stage_workset


def make_stage_workset(natives, trial, stage):
    base = _shared_make_stage_workset(natives, trial, stage)
    warmup_value = os.environ.get("HYWORLD2_WORLD_EXPANSION_WARMUP_NATIVE")
    if stage != "world_expansion" or not warmup_value:
        return base
    warmup = Path(warmup_value).resolve(strict=True)
    if (
        not (warmup / "meta_info.json").is_file()
        or not (warmup / "render_results/selected_trajectories.json").is_file()
    ):
        raise RuntimeError(f"Invalid WorldStereo warm-up scene: {warmup}")
    key = hashlib.sha256(
        (str(warmup) + "\0" + str(base.resolve())).encode("utf-8")
    ).hexdigest()[:12]
    root = base.parent / f"{trial}_{stage}_warmup_{key}"
    root.mkdir(parents=True, exist_ok=True)
    targets = [warmup, *natives]
    expected = set()
    for index, target in enumerate(targets):
        link = root / f"scene_{index:04d}"
        expected.add(link.name)
        if link.is_symlink():
            if link.resolve() != target.resolve():
                link.unlink()
                link.symlink_to(target, target_is_directory=True)
        elif link.exists():
            raise RuntimeError(f"Unexpected non-link warm-up workset entry: {link}")
        else:
            link.symlink_to(target, target_is_directory=True)
    actual = {entry.name for entry in root.iterdir()}
    if actual != expected:
        raise RuntimeError(
            f"Warm-up workset entries differ: {sorted(actual ^ expected)}"
        )
    matrix.atomic_json(
        root.with_suffix(".json"),
        {
            "trial": trial,
            "stage": stage,
            "scratch_warmup_native": str(warmup),
            "scratch_warmup_reported": False,
            "reported_scene_count": len(natives),
            "reported_scenes": [str(native) for native in natives],
        },
    )
    return root


matrix.make_stage_workset = make_stage_workset


_shared_command_for_stage = matrix.command_for_stage


def command_for_stage(stage, workset, native, llm_port):
    command = _shared_command_for_stage(stage, workset, native, llm_port)
    if stage == "gs_data":
        command[command.index("--nproc_per_node") + 1] = "2"
    return command


matrix.command_for_stage = command_for_stage


_shared_runtime_environment = matrix.runtime_environment


def runtime_environment(gpus, stage):
    environment = _shared_runtime_environment(gpus, stage)
    if stage == "gs_data":
        local_cache = Path(f"/tmp/hyworld2_runtime_cache_uid{os.getuid()}/gs_data")
        local_paths = {
            "HF_HOME": local_cache / "huggingface",
            "HUGGINGFACE_HUB_CACHE": local_cache / "huggingface/hub",
            "TORCH_HOME": local_cache / "torch",
            "TORCH_EXTENSIONS_DIR": local_cache / "torch_extensions",
            "TORCHINDUCTOR_CACHE_DIR": local_cache / "torchinductor",
            "TRITON_CACHE_DIR": local_cache / "triton",
            "CUDA_CACHE_PATH": local_cache / "cuda",
            "XDG_CACHE_HOME": local_cache / "xdg",
            "PYTHONPYCACHEPREFIX": local_cache / "pycache",
            "MPLCONFIGDIR": local_cache / "matplotlib",
            "TMPDIR": local_cache / "tmp",
        }
        for key, path in local_paths.items():
            path.mkdir(parents=True, exist_ok=True)
            environment[key] = str(path)
    if stage == "world_expansion":
        # WorldStereo keeps hundreds of MiB of TorchInductor/Triton state.  A
        # busy shared filesystem can otherwise leave torchrun itself blocked
        # in rpc_wait before CUDA initialization, or stall cache coordination
        # during the first forward.  The cache is an audited, uid-private
        # staging copy; model weights, prompts, seeds, and outputs are
        # unchanged.
        local_cache = Path(
            os.environ.get(
                "HYWORLD2_WORLD_EXPANSION_CACHE_ROOT",
                f"/tmp/hyworld2_runtime_cache_uid{os.getuid()}",
            )
        )
        local_private = local_cache / f"uid_{os.getuid()}"
        local_paths = {
            "HF_HOME": local_cache / "huggingface",
            "HUGGINGFACE_HUB_CACHE": local_cache / "huggingface/hub",
            "HYWORLD2_HF_HUB_CACHE": local_cache / "huggingface/hub",
            "TORCH_HOME": local_cache / "torch",
            "TORCH_EXTENSIONS_DIR": local_cache / "torch_extensions",
            "TORCHINDUCTOR_CACHE_DIR": local_private / "torchinductor",
            "TRITON_CACHE_DIR": local_private / "triton",
            "CUDA_CACHE_PATH": local_private / "cuda",
            "XDG_CACHE_HOME": local_private / "xdg_hyworld2",
            "PYTHONPYCACHEPREFIX": local_private / "pycache/hyworld2",
            "MPLCONFIGDIR": local_cache / "matplotlib",
            "TMPDIR": local_cache / "tmp",
        }
        for key, path in local_paths.items():
            path.mkdir(parents=True, exist_ok=True)
            environment[key] = str(path)
        local_models = Path(f"/tmp/hyworld2_models_uid{os.getuid()}")
        staged_models = {
            "HYWORLD2_WORLDSTEREO_PATH": local_models / "WorldStereo",
            "HYWORLD2_WAN_BASE_PATH": local_models / "Wan2.1-I2V-14B-480P-Diffusers",
            "HYWORLD2_SAM3_PATH": local_models / "sam3",
            "HYWORLD2_MOGE_PATH": local_models / "moge-2-vitl-normal/model.pt",
            "HYWORLD2_GROUNDING_DINO_PATH": local_models / "grounding-dino-tiny",
            "HYWORLD2_ZIM_PATH": local_models / "zim-anything-vitl",
        }
        for key, path in staged_models.items():
            if path.exists():
                environment[key] = str(path)
        # The first compiled WorldStereo forward is a single long CUDA call.
        # On A6000 the default 600 s watchdog can report a stuck monitoring
        # thread before any NCCL collective has even been enqueued.  Keep
        # monitoring enabled, but allow the validated long-kernel envelope.
        environment["TORCH_NCCL_HEARTBEAT_TIMEOUT_SEC"] = "3600"
    if stage == "panorama":
        # CUDA_VISIBLE_DEVICES preserves this physical-GPU order. Re-read free
        # memory immediately before dispatch because other users may start jobs
        # after the supervisor selected a capacity-qualified card. Each card
        # keeps at least 4 GiB for KV/MoE/VAE activations. These are checkpoint-
        # placement budgets, not allocations; per-card ceilings retain room for
        # existing jobs, and the dead denoising cache is released before decode.
        free_mib = [matrix.gpu_free_mib(gpu) for gpu in gpus]
        cap_ceiling = 40
        caps = []
        for position, (gpu, free) in enumerate(zip(gpus, free_mib)):
            # Visible device 0 owns the VAE and needs a 3.6-GiB temporary
            # activation during full-resolution decode in addition to the
            # denoising footprint. Other visible devices do not decode.
            # Jobs from other experiments may begin after dispatch.  The
            # visible first card also owns the full-resolution VAE decode,
            # whose measured peak includes a 3.57-GiB temporary allocation.
            # Retain enough unassigned memory for that activation plus one
            # small co-tenant instead of budgeting against a momentary idle
            # snapshot alone.
            reserve_gib = 14 if position == 0 else 8
            caps.append(max(4, min(cap_ceiling, int(free / 1024) - reserve_gib)))
        environment["HYWORLD2_PANO_GPU_MEMORY_GIBS"] = ",".join(map(str, caps))
        environment["HYWORLD2_PANO_GPU_FREE_AT_DISPATCH_MIB"] = ",".join(
            map(str, free_mib)
        )
        environment["HYWORLD2_SYNC_KV_CACHE"] = "1"
        environment["HYWORLD2_HOST_STAGE_BOUNDARIES"] = "1"
        environment["HYWORLD2_VALIDATE_LATENTS"] = "1"
        environment["CUDA_DEVICE_MAX_CONNECTIONS"] = "1"
        environment["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        environment["HYWORLD2_RELEASE_CACHE_BEFORE_VAE"] = "1"
    return environment


matrix.runtime_environment = runtime_environment


if __name__ == "__main__":
    raise SystemExit(matrix.main())
