#!/usr/bin/env python3
"""Batch text-to-panorama generation for frozen HY-World 2.0 runs.

The upstream high-level wrapper currently requires an image even though the
underlying official HunyuanImage-3 model supports text-only generation.  This
adapter calls that model API directly, preserving the published generation
configuration and loading the 80B checkpoint only once per workset.  The
The explicitly accelerated six-step direct-image sampler avoids both the
expensive 80B recaption pass and Taylor Cache's incompatibility with the
four-GPU checkpoint device map.  This is the frozen throughput-first setting
requested for the 200-scene evaluation.
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
import gc
import json
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE_ROOT = Path(
    os.environ.get("HYWORLD2_SOURCE_ROOT", BASELINES_ROOT / "sources/HY-World-2.0")
)
PANOGEN_ROOT = SOURCE_ROOT / "hyworld2/panogen"
EXPECTED_RESOLUTION = (1920, 960)


def four_gpu_device_map() -> dict[str, int]:
    """Keep the 32 decoder layers resident; place the large FP32 VAE on GPU 1.

    Auto dispatch reserves one entire decoder layer on GPU 0 for CPU swaps.
    On four 48-GiB cards that causes unnecessary offload of the final layers.
    This map uses about 39.7/41.9/37.2/38.2 GiB of checkpoint storage, leaving
    at least 6 GiB per idle card for activations. It does not change precision.
    """
    mapping = {f"model.layers.{index}": index // 8 for index in range(32)}
    mapping.update(
        {
            name: 0
            for name in (
                "vision_model",
                "vision_aligner",
                "timestep_emb",
                "patch_embed",
                "time_embed",
                "final_layer",
                "time_embed_2",
                "model.wte",
            )
        }
    )
    mapping.update({"vae": 1, "model.ln_f": 3, "lm_head": 3})
    return mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_below_baselines(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must stay below {BASELINES_ROOT}: {resolved}") from exc
    return resolved


def ensure_allowed_model_root(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    node_local_cache = Path(
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_models_uid2002/HY-World-2.0")
    ).resolve()
    if resolved == node_local_cache:
        return resolved
    return ensure_below_baselines(resolved)


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def update_manifest(run_dir: Path, stage_record: dict) -> None:
    path = run_dir / "run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    stage_record.setdefault("protocol_sha256", manifest.get("protocol_sha256"))
    attempts = manifest.setdefault("attempts", [])
    attempts.append(stage_record)
    manifest["last_stage"] = "panorama"
    manifest["last_updated_at_utc"] = utc_now()
    atomic_json(path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workset", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument(
        "--attn-implementation", default="sdpa", choices=("sdpa", "flash_attention_2")
    )
    parser.add_argument(
        "--moe-implementation", default="eager", choices=("eager", "flashinfer")
    )
    parser.add_argument(
        "--bot-task",
        default="image",
        choices=("image", "auto", "recaption", "think_recaption"),
        help="Direct image mode avoids the expensive 80B prompt-recaption pass.",
    )
    parser.add_argument("--diff-infer-steps", type=int, default=6)
    parser.add_argument(
        "--use-taylor-cache",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Taylor Cache is disabled by default because it is not device-map safe.",
    )
    parser.add_argument("--taylor-cache-interval", type=int, default=4)
    parser.add_argument("--taylor-cache-order", type=int, default=2)
    parser.add_argument(
        "--device-map", choices=("auto", "four_gpu_resident"), default="auto"
    )
    parser.add_argument(
        "--gpu-max-memory-gib",
        type=int,
        default=19,
        help="Maximum checkpoint weight memory per visible GPU; leaves room for diffusion activations.",
    )
    parser.add_argument(
        "--cpu-max-memory-gib",
        type=int,
        default=300,
        help="Maximum CPU checkpoint-offload memory available to Accelerate.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    workset = ensure_below_baselines(args.workset)
    model_root = ensure_allowed_model_root(args.model_root)
    model_dir = model_root / "HY-Pano-2.0"
    if not model_dir.is_dir() or not (model_dir / "config.json").exists():
        raise FileNotFoundError(f"Incomplete local HY-Pano checkpoint: {model_dir}")
    scenes = sorted(path for path in workset.iterdir() if path.is_symlink())
    if not scenes:
        raise RuntimeError(f"No scene symlinks in workset: {workset}")

    sys.path.insert(0, str(PANOGEN_ROOT))
    import numpy as np
    import torch
    from hunyuan_image_3 import HunyuanImage3ForCausalMM
    from pipeline import circular_blend_edges

    if args.gpu_max_memory_gib < 1 or args.cpu_max_memory_gib < 1:
        raise ValueError("Accelerate memory limits must be positive")
    if args.diff_infer_steps < 1:
        raise ValueError("diff-infer-steps must be positive")
    if args.taylor_cache_interval < 2 or args.taylor_cache_order < 1:
        raise ValueError("Taylor Cache requires interval >= 2 and order >= 1")
    visible_gpu_count = torch.cuda.device_count()
    if visible_gpu_count < 1:
        raise RuntimeError("HY-Pano requires at least one visible CUDA GPU")
    device_map = "auto"
    if args.device_map == "four_gpu_resident":
        if visible_gpu_count != 4:
            raise ValueError("four_gpu_resident requires exactly four visible GPUs")
        config = json.loads((model_dir / "config.json").read_text())
        if config.get("num_hidden_layers") != 32:
            raise ValueError(
                "four_gpu_resident is specific to the frozen 32-layer checkpoint"
            )
        free_gib = {i: torch.cuda.mem_get_info(i)[0] / 2**30 for i in range(4)}
        if any(free < 46 for free in free_gib.values()):
            raise RuntimeError(
                f"four_gpu_resident needs at least 46 GiB free/card: {free_gib}"
            )
        device_map = four_gpu_device_map()
    per_gpu_raw = os.environ.get("HYWORLD2_PANO_GPU_MEMORY_GIBS", "").strip()
    if per_gpu_raw:
        per_gpu_limits = [int(value) for value in per_gpu_raw.split(",")]
        if len(per_gpu_limits) != visible_gpu_count or any(
            value < 1 for value in per_gpu_limits
        ):
            raise ValueError(
                "HYWORLD2_PANO_GPU_MEMORY_GIBS must contain one positive integer "
                "for every visible GPU"
            )
    else:
        per_gpu_limits = [args.gpu_max_memory_gib] * visible_gpu_count
    max_memory = {
        **{index: f"{limit}GiB" for index, limit in enumerate(per_gpu_limits)},
        "cpu": f"{args.cpu_max_memory_gib}GiB",
    }

    print(
        f"Loading HY-Pano model once from {model_dir} with max_memory={max_memory}",
        flush=True,
    )
    model = HunyuanImage3ForCausalMM.from_pretrained(
        str(model_dir),
        attn_implementation=args.attn_implementation,
        trust_remote_code=True,
        torch_dtype="auto",
        device_map=device_map,
        max_memory=max_memory,
        moe_impl=args.moe_implementation,
        moe_drop_tokens=True,
    )
    model.load_tokenizer(str(model_dir))
    model.eval()
    if os.environ.get("HYWORLD2_VAE_SPATIAL_TILING") == "1":
        model.vae.enable_spatial_tiling()
    if os.environ.get("HYWORLD2_SYNC_LAYER_BOUNDARIES") == "1":
        model.model.hyworld2_sync_layer_boundaries = True
    # generate_image forwards arbitrary kwargs, but this checkpoint's generate()
    # reads the denoising count from generation_config rather than kwargs.
    model.generation_config.diff_infer_steps = args.diff_infer_steps
    print(f"HY-Pano device map: {model.hf_device_map}", flush=True)
    print("HY-Pano model ready", flush=True)

    failures = 0
    for scene_link in scenes:
        scene_dir = ensure_below_baselines(scene_link.resolve())
        run_dir = scene_dir.parents[1]
        native = json.loads(
            (run_dir / "input/native_input.json").read_text(encoding="utf-8")
        )
        output_path = scene_dir / "panorama.png"
        if output_path.exists() and not args.force:
            from PIL import Image

            with Image.open(output_path) as existing:
                if existing.size != EXPECTED_RESOLUTION:
                    raise RuntimeError(
                        f"Existing panorama has wrong size: {output_path} {existing.size}"
                    )
            print(
                f"PANORAMA_SKIP {native['spec_id']} seed={native['logical_seed']}",
                flush=True,
            )
            continue

        seed = int(native["method_seed"])
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True)
        started_at = utc_now()
        tic = time.perf_counter()
        stage_record = {
            "stage": "panorama",
            "started_at_utc": started_at,
            "seed": seed,
            "command_mode": "hunyuan_image_3_core_text_to_image",
            "physical_gpus": [
                int(value)
                for value in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
                if value.strip()
            ],
            "gpu_max_memory_gib": args.gpu_max_memory_gib,
            "gpu_max_memory_gib_per_visible_device": per_gpu_limits,
            "gpu_free_at_dispatch_mib_per_visible_device": [
                int(value)
                for value in os.environ.get(
                    "HYWORLD2_PANO_GPU_FREE_AT_DISPATCH_MIB", ""
                ).split(",")
                if value
            ],
            "cpu_max_memory_gib": args.cpu_max_memory_gib,
            "device_map_mode": args.device_map,
            "device_map": model.hf_device_map,
            "model_root": str(model_root),
            "sync_layer_boundaries": bool(
                getattr(model.model, "hyworld2_sync_layer_boundaries", False)
            ),
            "sync_kv_cache": os.environ.get("HYWORLD2_SYNC_KV_CACHE") == "1",
            "host_stage_boundaries": os.environ.get("HYWORLD2_HOST_STAGE_BOUNDARIES")
            == "1",
            "validate_latents": os.environ.get("HYWORLD2_VALIDATE_LATENTS") == "1",
            "validate_layer_outputs": os.environ.get("HYWORLD2_VALIDATE_LAYER_OUTPUTS")
            == "1",
            "cuda_device_max_connections": os.environ.get(
                "CUDA_DEVICE_MAX_CONNECTIONS"
            ),
            "pytorch_cuda_alloc_conf": os.environ.get("PYTORCH_CUDA_ALLOC_CONF"),
            "vae_spatial_tiling": bool(getattr(model.vae, "use_spatial_tiling", False)),
            "release_cache_before_vae": os.environ.get(
                "HYWORLD2_RELEASE_CACHE_BEFORE_VAE"
            )
            == "1",
            "diff_infer_steps": args.diff_infer_steps,
            "bot_task": args.bot_task,
            "use_taylor_cache": args.use_taylor_cache,
            "taylor_cache_interval": args.taylor_cache_interval,
            "taylor_cache_order": args.taylor_cache_order,
            "taylor_cache_low_freqs_order": 2,
            "taylor_cache_high_freqs_order": 2,
        }
        try:
            cot_text, samples = model.generate_image(
                prompt=native["panorama_prompt_en"],
                image=None,
                seed=seed,
                image_size=[960, 1952],
                use_system_prompt="en_unified",
                bot_task=args.bot_task,
                verbose=2,
                max_new_tokens=2048,
                infer_align_image_size=False,
                use_taylor_cache=args.use_taylor_cache,
                taylor_cache_interval=args.taylor_cache_interval,
                taylor_cache_order=args.taylor_cache_order,
                taylor_cache_enable_first_enhance=False,
                taylor_cache_first_enhance_steps=3,
                taylor_cache_enable_tailing_enhance=False,
                taylor_cache_tailing_enhance_steps=1,
                taylor_cache_low_freqs_order=2,
                taylor_cache_high_freqs_order=2,
            )
            panorama = circular_blend_edges(samples[0], blend_width=32)
            if panorama.size != EXPECTED_RESOLUTION:
                raise RuntimeError(
                    f"Unexpected panorama size {panorama.size}; expected {EXPECTED_RESOLUTION}"
                )
            pixels = np.asarray(panorama, dtype=np.float32)
            dynamic_range = float(pixels.max() - pixels.min())
            pixel_std = float(pixels.std())
            if dynamic_range < 8.0 or pixel_std < 1.0:
                raise RuntimeError(
                    f"Degenerate panorama rejected: dynamic_range={dynamic_range:.3f}, "
                    f"pixel_std={pixel_std:.3f}"
                )
            temporary = output_path.with_suffix(".png.tmp")
            panorama.save(temporary, format="PNG")
            temporary.replace(output_path)
            stage_record.update(
                {
                    "ended_at_utc": utc_now(),
                    "wall_time_s": time.perf_counter() - tic,
                    "exit_code": 0,
                    "success": True,
                    "output": "scene/native/panorama.png",
                    "reasoning_trace_present": bool(cot_text),
                    "panorama_dynamic_range": dynamic_range,
                    "panorama_pixel_std": pixel_std,
                }
            )
            update_manifest(run_dir, stage_record)
            print(
                f"PANORAMA_OK {native['spec_id']} seed={native['logical_seed']} "
                f"wall_time_s={stage_record['wall_time_s']:.1f}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            traceback.print_exc()
            stage_record.update(
                {
                    "ended_at_utc": utc_now(),
                    "wall_time_s": time.perf_counter() - tic,
                    "exit_code": 1,
                    "success": False,
                    "error": repr(exc),
                }
            )
            update_manifest(run_dir, stage_record)
            print(
                f"PANORAMA_FAILED {native['spec_id']} seed={native['logical_seed']} {exc!r}",
                flush=True,
            )
            # A large model is loaded once for the whole workset.  Most errors
            # at this boundary are systemic runtime/ABI failures; stop after
            # the first one so a retry does not duplicate the same failure on
            # every remaining scene.  Completed panoramas remain resumable.
            break
        finally:
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except RuntimeError:
                # A device-side assert poisons the context; preserve the
                # original traceback instead of replacing it during cleanup.
                traceback.print_exc()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
