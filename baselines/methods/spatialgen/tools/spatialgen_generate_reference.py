#!/usr/bin/env python3
"""Generate SpatialGen's first-view RGB with official FLUX wireframe LoRA."""

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
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
from diffusers import FluxControlPipeline
from PIL import Image


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
DEFAULT_BASE_MODEL = BASELINES_ROOT / "spatialgen_assets/flux1_dev"
DEFAULT_LORA = BASELINES_ROOT / "spatialgen_assets/flux_wireframe_lora"


def assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside baselines/: {resolved}") from exc
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def generate_reference(
    run_dir: Path,
    base_model: Path,
    lora: Path,
    device_name: str,
    offload: str,
) -> dict[str, Any]:
    run_dir = assert_baselines_path(run_dir)
    base_model = base_model.resolve()
    lora = lora.resolve()
    if not base_model.is_dir():
        raise FileNotFoundError(f"FLUX base model is missing: {base_model}")
    if not lora.is_dir():
        raise FileNotFoundError(f"Wireframe LoRA is missing: {lora}")

    spec = json.loads((run_dir / "input/spec.json").read_text(encoding="utf-8"))
    native = json.loads(
        (run_dir / "input/native_input.json").read_text(encoding="utf-8")
    )
    scene_input = run_dir / "input/dataset" / spec["spec_id"]
    control_path = scene_input / "condition/frame_0.jpg"
    if not control_path.is_file():
        raise FileNotFoundError(f"Prepared wireframe is missing: {control_path}")

    device = torch.device(device_name)
    pipeline = FluxControlPipeline.from_pretrained(
        str(base_model),
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    )
    pipeline.load_lora_weights(
        str(lora), weight_name="lora.safetensors", local_files_only=True
    )
    if offload == "model":
        pipeline.enable_model_cpu_offload(gpu_id=device.index or 0)
        generator_device = "cpu"
    elif offload == "sequential":
        pipeline.enable_sequential_cpu_offload(gpu_id=device.index or 0)
        generator_device = "cpu"
    elif offload == "none":
        pipeline.to(device)
        generator_device = device.type
    else:
        raise ValueError(f"Unknown offload mode: {offload}")
    pipeline.set_progress_bar_config(disable=False)

    model_seed = int(native["method_seed"])
    generator = torch.Generator(device=generator_device).manual_seed(model_seed)
    control_image = Image.open(control_path).convert("RGB")
    image = pipeline(
        native["prompt_en"],
        num_inference_steps=20,
        generator=generator,
        control_image=control_image,
        guidance_scale=3.5,
        height=1024,
        width=1024,
        num_images_per_prompt=1,
    ).images[0]

    intermediate_dir = run_dir / "scene/intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    reference_1024 = intermediate_dir / "flux_reference_1024.png"
    image.save(reference_1024)
    reference_512 = intermediate_dir / "flux_reference_512.jpg"
    image.resize((512, 512), Image.Resampling.LANCZOS).save(reference_512)
    native_frame = scene_input / "rgb/frame_0.jpg"
    temporary_frame = native_frame.with_suffix(".jpg.tmp")
    Image.open(reference_512).convert("RGB").save(temporary_frame, format="JPEG")
    temporary_frame.replace(native_frame)

    generator_state_path = intermediate_dir / "flux_generator_state.pt"
    temporary_state = generator_state_path.with_suffix(".pt.tmp")
    torch.save(generator.get_state(), temporary_state)
    temporary_state.replace(generator_state_path)

    payload = {
        "stage": "official_flux_wireframe_reference",
        "spec_id": spec["spec_id"],
        "method_seed": model_seed,
        "prompt": native["prompt_en"],
        "base_model": str(base_model),
        "lora": str(lora),
        "device": str(device),
        "offload": offload,
        "generator_device": generator_device,
        "parameters": {
            "num_inference_steps": 20,
            "control_conditioning": (
                "native FluxControlPipeline latent concatenation; the frozen "
                "diffusers 0.32.0 API has no separate conditioning scale"
            ),
            "guidance_scale": 3.5,
            "height": 1024,
            "width": 1024,
            "resize": "PIL.Image.Resampling.LANCZOS to 512x512",
        },
        "control_image_sha256": sha256_file(control_path),
        "reference_1024_sha256": sha256_file(reference_1024),
        "reference_512_sha256": sha256_file(reference_512),
        "native_frame_sha256": sha256_file(native_frame),
        "generator_state_after_flux": str(generator_state_path.relative_to(run_dir)),
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(device)
        if device.type == "cuda"
        else None,
    }
    atomic_json(intermediate_dir / "flux_reference.json", payload)

    del pipeline
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--lora", type=Path, default=DEFAULT_LORA)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--offload", choices=("model", "sequential", "none"), default="model"
    )
    args = parser.parse_args()
    payload = generate_reference(
        args.run_dir, args.base_model, args.lora, args.device, args.offload
    )
    print(
        f"SPATIALGEN_REFERENCE_OK spec={payload['spec_id']} "
        f"seed={payload['method_seed']} sha256={payload['native_frame_sha256']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
