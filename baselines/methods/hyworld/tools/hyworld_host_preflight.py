#!/usr/bin/env python3
"""Check the transferred HY runtime without downloading or generating a scene."""

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

from pathlib import Path
import argparse
import importlib
import json
import os
import subprocess
import sys
import faulthandler

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["panorama", "worldgen", "vllm", "vlm_inference"],
        default="panorama",
    )
    parser.add_argument("--gpus", nargs="+", type=int, default=[4, 5, 6, 0])
    parser.add_argument("--gpu-memory-gib", type=int, default=41)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    import baselines.methods.hyworld.run as matrix

    if args.stage == "vlm_inference":
        if len(args.gpus) != 1 or matrix.gpu_free_mib(args.gpus[0]) < 46000:
            raise RuntimeError("VLM inference smoke test requires one idle 48-GiB GPU")
        from baselines.methods.hyworld.tools.score_hyworld_ai_proxy import request_score
        from baselines.methods.hyworld.tools.score_hyworld_ai_proxy import MODEL

        process = None
        try:
            process, log = matrix.start_vllm(args.gpus[0], 18082, 16384, 900)
            response = request_score(
                18082,
                {
                    "model": MODEL,
                    "temperature": 0,
                    "max_tokens": 16,
                    "messages": [
                        {"role": "user", "content": "Reply with the single word ready."}
                    ],
                },
            )
            if not response.get("choices", [{}])[0].get("message", {}).get("content"):
                raise RuntimeError("VLM returned an empty response")
            report = {
                "stage": args.stage,
                "physical_gpu": args.gpus[0],
                "log": str(log),
                "local_model": str(matrix.QWEN_ROOT),
                "text_inference_response": response,
            }
            matrix.atomic_json(
                BASELINES / "results/hyworld2/host_preflight_vlm_inference.json", report
            )
            print("PREFLIGHT_VLM_INFERENCE_OK", flush=True)
        finally:
            if process is not None:
                matrix.stop_process_group(process)
        return 0
    if not args.worker:
        environment = (
            matrix.vllm_environment(args.gpus[0])
            if args.stage == "vllm"
            else matrix.runtime_environment(args.gpus, args.stage)
        )
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        python = matrix.VLLM_PYTHON if args.stage == "vllm" else matrix.PYTHON
        return subprocess.run(
            [str(python), str(Path(__file__).resolve()), *sys.argv[1:], "--worker"],
            env=environment,
            cwd=BASELINES,
        ).returncode
    faulthandler.dump_traceback_later(120, repeat=True)
    print(f"PREFLIGHT_IMPORT_TORCH stage={args.stage}", flush=True)
    import torch

    report = {
        "stage": args.stage,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "devices": [],
    }
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    for index in range(torch.cuda.device_count()):
        x = torch.ones((64, 64), device=f"cuda:{index}")
        assert (x @ x)[0, 0].item() == 64
        report["devices"].append(
            {
                "logical_gpu": index,
                "physical_gpu": args.gpus[index],
                "name": torch.cuda.get_device_name(index),
                "free_mib": torch.cuda.mem_get_info(index)[0] // 2**20,
            }
        )
        del x
        torch.cuda.empty_cache()
    if args.stage == "panorama":
        import transformers
        import huggingface_hub
        from accelerate import init_empty_weights, infer_auto_device_map

        sys.path.insert(0, str(matrix.HY.SOURCE_ROOT / "hyworld2/panogen"))
        from hunyuan_image_3 import HunyuanImage3ForCausalMM
        from hunyuan_image_3.configuration_hunyuan_image_3 import HunyuanImage3Config

        model_dir = matrix.HY.PANO_MODEL_ROOT / "HY-Pano-2.0"
        config = HunyuanImage3Config.from_pretrained(
            str(model_dir), local_files_only=True
        )
        config.moe_impl = "eager"
        config._attn_implementation = "sdpa"
        with init_empty_weights():
            model = HunyuanImage3ForCausalMM(config)
        memory = {
            i: f"{args.gpu_memory_gib}GiB" for i in range(torch.cuda.device_count())
        }
        memory["cpu"] = "300GiB"
        mapping = infer_auto_device_map(
            model,
            max_memory=memory,
            dtype=torch.bfloat16,
            no_split_module_classes=model._no_split_modules,
        )
        report.update(
            {
                "transformers": transformers.__version__,
                "huggingface_hub": huggingface_hub.__version__,
                "weight_budget_gib_per_gpu": args.gpu_memory_gib,
                "device_map": mapping,
                "cpu_offload_modules": [
                    name for name, device in mapping.items() if device == "cpu"
                ],
            }
        )
    else:
        names = (
            [
                "transformers",
                "diffusers",
                "pytorch3d._C",
                "fused_ssim_cuda",
                "recast",
                "gsplat",
            ]
            if args.stage == "worldgen"
            else ["vllm", "transformers"]
        )
        for name in names:
            print(f"PREFLIGHT_IMPORT {name}", flush=True)
            module = importlib.import_module(name)
            report[name] = {
                "version": getattr(module, "__version__", None),
                "file": module.__file__,
            }
        if args.stage == "worldgen":
            from pytorch3d.structures import Pointclouds
            from pytorch3d.renderer.points.rasterize_points import rasterize_points
            from fused_ssim import fused_ssim
            from gsplat import rasterization

            device = torch.device("cuda:0")
            points = torch.tensor([[[0.0, 0.0, 1.0]]], device=device)
            fragments = rasterize_points(Pointclouds(points), image_size=16, radius=0.2)
            assert (fragments[0] >= 0).any().item()
            frame = torch.rand(1, 3, 32, 32, device=device)
            assert abs(fused_ssim(frame, frame).item() - 1.0) < 1e-5
            render, alpha, meta = rasterization(
                means=torch.tensor([[0.0, 0.0, 2.0]], device=device),
                quats=torch.tensor([[1.0, 0.0, 0.0, 0.0]], device=device),
                scales=torch.full((1, 3), 0.1, device=device),
                opacities=torch.ones(1, device=device) * 0.8,
                colors=torch.tensor([[1.0, 0.0, 0.0]], device=device),
                viewmats=torch.eye(4, device=device).unsqueeze(0),
                Ks=torch.tensor(
                    [[[32.0, 0.0, 16.0], [0.0, 32.0, 16.0], [0.0, 0.0, 1.0]]],
                    device=device,
                ),
                width=32,
                height=32,
            )
            assert torch.isfinite(render).all().item() and alpha.max().item() > 0
            report["cuda_kernel_checks"] = [
                "pytorch3d_rasterize_points",
                "fused_ssim_identity",
                "gsplat_rasterization",
            ]
    out = BASELINES / "results/hyworld2" / f"host_preflight_{args.stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    faulthandler.cancel_dump_traceback_later()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
