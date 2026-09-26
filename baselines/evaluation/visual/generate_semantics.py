#!/usr/bin/env python3
"""Generate method-independent ADE20K semantic maps for anchor renders."""

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
import json
import os
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
os.environ.setdefault("HF_HOME", str(BASELINES_ROOT / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TORCH_HOME", str(BASELINES_ROOT / "cache/torch"))
os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES_ROOT / "cache/xdg_metrics"))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn.functional as functional  # noqa: E402
from PIL import Image  # noqa: E402
from transformers import (
    AutoImageProcessor,
    SegformerForSemanticSegmentation,
)  # noqa: E402


MODEL_ID = "nvidia/segformer-b2-finetuned-ade-512-512"
MODEL_REVISION = "de01bae28967510f9ddd496c60a969357195400c"
MODEL_WEIGHTS_SHA256 = (
    "187ca07bea003a5717c63d04ea90b07f33cd033c0ebf44b4b89fce5070d6c8f3"
)


def load_specs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root", type=Path, default=BASELINES_ROOT / "data/table2"
    )
    parser.add_argument(
        "--spec-file",
        type=Path,
        default=(BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    )
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--domain", choices=("indoor", "urban"), default="indoor")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--spec-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--semantic-root",
        type=Path,
        default=None,
        help=(
            "Optional writable mirror root. Semantic maps retain their path "
            "relative to data-root below this directory."
        ),
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=BASELINES_ROOT / "results/semantic_model.json",
    )
    args = parser.parse_args()
    processor = AutoImageProcessor.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, local_files_only=True
    )
    model = SegformerForSemanticSegmentation.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, local_files_only=True
    )
    model.to(args.device).eval()
    pending = []
    specs = [
        spec
        for spec in load_specs(args.spec_file)
        if args.spec_id in (None, spec["spec_id"])
    ]
    if args.spec_id is not None and not specs:
        raise KeyError(f"Unknown spec_id={args.spec_id!r}")
    seeds = range(4) if args.seed is None else [args.seed]
    if args.seed is not None and args.seed not in range(4):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    for spec in specs:
        for seed in seeds:
            run_dir = (
                args.data_root
                / args.domain
                / args.method
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            if not (run_dir / "SUCCESS").exists():
                continue
            for image_path in sorted((run_dir / "renders/anchors").glob("rgb_*.png")):
                semantic_dir = (
                    args.semantic_root
                    / run_dir.relative_to(args.data_root)
                    / "renders/semantic_pred"
                    if args.semantic_root is not None
                    else run_dir / "renders/semantic_pred"
                )
                output_path = semantic_dir / image_path.name.replace(
                    "rgb_", "semantic_"
                )
                if not output_path.exists():
                    pending.append((image_path, output_path))
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        images = [Image.open(source).convert("RGB") for source, _ in batch]
        inputs = processor(images=images, return_tensors="pt").to(args.device)
        with torch.inference_mode():
            logits = model(**inputs).logits
        for index, ((_, output_path), image) in enumerate(zip(batch, images)):
            resized = functional.interpolate(
                logits[index : index + 1],
                size=(image.height, image.width),
                mode="bilinear",
                align_corners=False,
            )
            labels = resized.argmax(dim=1)[0].to(torch.uint8).cpu().numpy()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.asarray(labels, dtype=np.uint8), mode="L").save(
                output_path
            )
        print(
            f"SEMANTICS_PROGRESS {min(start + len(batch), len(pending))}/{len(pending)}"
        )
    metadata = {
        "domain": args.domain,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_weights_sha256": MODEL_WEIGHTS_SHA256,
        "num_classes": len(model.config.id2label),
        "id2label": model.config.id2label,
        "generated": len(pending),
    }
    metadata_path = args.metadata_output
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"SEMANTICS_COMPLETE generated={len(pending)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
