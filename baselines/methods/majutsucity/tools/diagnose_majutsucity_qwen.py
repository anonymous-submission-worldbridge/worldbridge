#!/usr/bin/env python3
"""Run two non-eligible Qwen Edit probes and record latent finiteness."""

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
import gc
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from diffusers import QwenImageEditPlusPipeline
from PIL import Image, ImageStat


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--prompt-record", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument(
        "--stop-after",
        type=int,
        default=None,
        help="Interrupt after this many denoising steps while keeping the full schedule.",
    )
    parser.add_argument("--suite", choices=("negative", "cfg"), default="negative")
    parser.add_argument(
        "--placement",
        choices=("balanced", "model_cpu_offload"),
        default="balanced",
    )
    parser.add_argument(
        "--variant",
        default="all",
        help="Run only one named suite variant (default: all variants).",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    record = json.loads(args.prompt_record.read_text(encoding="utf-8"))
    load_kwargs = {
        "torch_dtype": torch.bfloat16,
        "local_files_only": True,
    }
    if args.placement == "balanced":
        load_kwargs["device_map"] = "balanced"
    pipe = QwenImageEditPlusPipeline.from_pretrained(str(args.model), **load_kwargs)
    if args.placement == "model_cpu_offload":
        pipe.enable_model_cpu_offload(gpu_id=0)
    device_map = getattr(pipe, "hf_device_map", None)
    print(f"QWEN_DIAGNOSTIC_DEVICE_MAP {device_map}", flush=True)
    image = Image.open(args.input).convert("RGB")
    variants = (
        {
            "official_blank_negative": {"negative_prompt": " ", "true_cfg_scale": 4.0},
            "majutsucity_constrained_negative": {
                "negative_prompt": record["negative_prompt"],
                "true_cfg_scale": 4.0,
            },
        }
        if args.suite == "negative"
        else {
            "no_true_cfg": {"negative_prompt": None, "true_cfg_scale": 1.0},
            "official_blank_cfg4": {"negative_prompt": " ", "true_cfg_scale": 4.0},
        }
    )
    if args.variant != "all":
        if args.variant not in variants:
            parser.error(
                f"--variant {args.variant!r} is not in the {args.suite!r} suite: "
                + ", ".join(variants)
            )
        variants = {args.variant: variants[args.variant]}
    report = {
        "table2_eligible": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": str(args.model.resolve()),
        "input": str(args.input.resolve()),
        "prompt_record": str(args.prompt_record.resolve()),
        "device_map": device_map,
        "placement": args.placement,
        "torch_dtype": "bfloat16",
        "steps": args.steps,
        "stop_after": args.stop_after,
        "true_cfg_scale": "per_variant",
        "variants": {},
    }
    for name, settings in variants.items():
        negative_prompt = settings["negative_prompt"]
        true_cfg_scale = settings["true_cfg_scale"]
        latent_records = []
        transformer_records = []

        original_forward = pipe.transformer.forward

        def diagnostic_forward(*forward_args, **forward_kwargs):
            output = original_forward(*forward_args, **forward_kwargs)
            tensor = output[0]
            finite = torch.isfinite(tensor)
            transformer_records.append(
                {
                    "call": len(transformer_records),
                    "all_finite": bool(finite.all().item()),
                    "nonfinite": int((~finite).sum().item()),
                    "minimum": float(torch.nan_to_num(tensor).min().item()),
                    "maximum": float(torch.nan_to_num(tensor).max().item()),
                }
            )
            return output

        pipe.transformer.forward = diagnostic_forward

        def callback(_pipe, step, timestep, callback_kwargs):
            latents = callback_kwargs["latents"]
            finite = torch.isfinite(latents)
            latent_records.append(
                {
                    "step": int(step),
                    "timestep": float(timestep),
                    "all_finite": bool(finite.all().item()),
                    "nonfinite": int((~finite).sum().item()),
                    "minimum": float(torch.nan_to_num(latents).min().item()),
                    "maximum": float(torch.nan_to_num(latents).max().item()),
                }
            )
            if args.stop_after is not None and step + 1 >= args.stop_after:
                _pipe._interrupt = True
            return callback_kwargs

        print(f"QWEN_DIAGNOSTIC_START {name}", flush=True)
        generator = torch.Generator(device="cuda").manual_seed(int(record["seed"]))
        with torch.inference_mode():
            result = pipe(
                image=image,
                prompt=record["edit_prompt"],
                negative_prompt=negative_prompt,
                generator=generator,
                num_inference_steps=args.steps,
                true_cfg_scale=true_cfg_scale,
                guidance_scale=1.0,
                num_images_per_prompt=1,
                callback_on_step_end=callback,
                callback_on_step_end_tensor_inputs=["latents"],
            )
        output = result.images[0]
        output_path = args.output_dir / f"{name}.png"
        output.save(output_path)
        array = np.asarray(output.convert("RGB"), dtype=np.uint8)
        stddev = ImageStat.Stat(output.convert("RGB")).stddev
        report["variants"][name] = {
            "negative_prompt": negative_prompt,
            "true_cfg_scale": true_cfg_scale,
            "output": str(output_path.resolve()),
            "size": list(output.size),
            "minimum": int(array.min()),
            "maximum": int(array.max()),
            "stddev": stddev,
            "valid_nonconstant": bool(max(stddev) > 1.0),
            "all_latent_steps_finite": all(row["all_finite"] for row in latent_records),
            "latents": latent_records,
            "transformer_outputs": transformer_records,
        }
        atomic_json(args.output_dir / "diagnostic.json", report)
        print(
            f"QWEN_DIAGNOSTIC_DONE {name} valid={max(stddev) > 1.0} "
            f"finite={report['variants'][name]['all_latent_steps_finite']}",
            flush=True,
        )
        gc.collect()
        torch.cuda.empty_cache()
        pipe.transformer.forward = original_forward
    return (
        0
        if any(
            item["valid_nonconstant"] and item["all_latent_steps_finite"]
            for item in report["variants"].values()
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
