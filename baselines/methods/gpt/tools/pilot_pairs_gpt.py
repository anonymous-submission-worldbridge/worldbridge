"""Validate real two-seed diversity without inventing missing formal runs."""

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
import json
import os
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
os.environ.setdefault("TORCH_HOME", str(ROOT / "cache/torch"))
os.environ.setdefault("HF_HOME", str(ROOT / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "cache/xdg_metrics"))
sys.path.insert(0, str((ROOT / "evaluation/visual")))
from baselines.evaluation.visual.eval_diversity import semantic_distance
from baselines.evaluation.visual.eval_diversity import scalar
from baselines.evaluation.visual.eval_diversity import INDOOR_CLASS_IDS
from baselines.evaluation.visual.eval_diversity import URBAN_CLASS_IDS
import pyiqa
import torch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--domain", choices=["indoor", "urban"], required=True)
    p.add_argument("--spec-id", required=True)
    args = p.parse_args()
    base = ROOT / "data/gpt6_astra_pilot" / args.domain / "gpt6_astra" / args.spec_id
    runs = [base / f"seed_{s}" for s in [0, 1]]
    if any(not (r / "SUCCESS").exists() for r in runs):
        raise RuntimeError("Both fixed pilot seeds must be valid before pair sanity")
    metric = pyiqa.create_metric("lpips", device="cuda", as_loss=False)
    ids = INDOOR_CLASS_IDS if args.domain == "indoor" else URBAN_CLASS_IDS
    views = []
    with torch.inference_mode():
        for i in range(8):
            images = [r / f"renders/anchors/rgb_{i:03d}.png" for r in runs]
            semantics = [
                r / f"renders/semantic_pred/semantic_{i:03d}.png" for r in runs
            ]
            views.append(
                {
                    "index": i,
                    "lpips": scalar(metric(*map(str, images))),
                    "semantic_1miou": semantic_distance(*semantics, ids),
                    "inputs_sha256": {
                        str(q.relative_to(ROOT)): hashlib.sha256(
                            q.read_bytes()
                        ).hexdigest()
                        for q in images + semantics
                    },
                }
            )
    report = {
        "formal": False,
        "method": "gpt6_astra",
        "domain": args.domain,
        "spec_id": args.spec_id,
        "logical_seeds": [0, 1],
        "views": views,
        "appearance_valid_pair": sum(v["lpips"] for v in views) / 8,
        "layout_valid_pair": sum(v["semantic_1miou"] for v in views) / 8,
        "note": "Pilot valid pair only; no invented seeds 2/3 and no formal ITT estimate",
    }
    target = ROOT / f"results/gpt6_astra/smoke/{args.domain}/{args.spec_id}_pair.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "views"}), flush=True)


if __name__ == "__main__":
    main()
