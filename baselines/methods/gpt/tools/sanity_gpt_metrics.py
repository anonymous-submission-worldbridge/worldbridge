"""Numerical sanity tests on fixed Astra pilot images; never a Table-2 row."""

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

import json
import hashlib
import os
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
os.environ.setdefault("TORCH_HOME", str(ROOT / "cache/torch"))
os.environ.setdefault("HF_HOME", str(ROOT / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "cache/xdg_metrics"))
import torch
import pyiqa
from PIL import Image
from torchvision.transforms.functional import to_tensor


def main():
    data = ROOT / "data/gpt6_astra_pilot"
    runs = [
        data / "indoor/gpt6_astra/indoor_bedroom_00/seed_0",
        data / "urban/gpt6_astra/urban_residential_four_way_00/seed_0",
    ]
    images = [
        run / f"renders/anchors/rgb_{i:03d}.png" for run in runs for i in range(5)
    ]
    if any(not (r / "SUCCESS").exists() for r in runs):
        raise RuntimeError("Both fixed pilot reference scenes must be valid")
    report = {
        "images": [str(p.relative_to(ROOT)) for p in images],
        "images_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in images
        },
        "formal": False,
        "device": torch.cuda.get_device_name(0),
        "checks": {},
    }
    for name in ["qalign", "clipiqa+"]:
        model = pyiqa.create_metric(name, device="cuda")
        kwargs = {"task_": "quality"} if name == "qalign" else {}
        with torch.inference_mode():
            first = [float(model(str(p), **kwargs).float().mean()) for p in images]
            second = [float(model(str(p), **kwargs).float().mean()) for p in images]
        delta = max(abs(a - b) for a, b in zip(first, second))
        report["checks"][name] = {
            "repeat_max_abs_delta": delta,
            "repeat_pass": delta <= 1e-4,
        }
        if name == "qalign":
            report["checks"][name][
                "batch8"
            ] = "not_supported_by_frozen_pyiqa_implementation_assert_batch_size_1"
            report["checks"][name][
                "cpu"
            ] = "not_run: fp16 LLM pipeline; GPU-only experiment"
        else:
            tensors = torch.stack(
                [to_tensor(Image.open(p).convert("RGB")) for p in images]
            ).cuda()
            with torch.inference_mode():
                batched = (
                    torch.cat([model(tensors[:8]), model(tensors[8:])])
                    .flatten()
                    .tolist()
                )
            batch_delta = max(abs(a - b) for a, b in zip(first, batched))
            report["checks"][name].update(
                batch8_max_abs_delta=batch_delta,
                batch8_tolerance_pass=batch_delta <= 1e-4,
            )
        del model
        torch.cuda.empty_cache()
    lpips = pyiqa.create_metric("lpips", device="cuda", as_loss=False)
    with torch.inference_mode():
        same = float(lpips(str(images[0]), str(images[0])).float().mean())
        different = float(lpips(str(images[0]), str(images[5])).float().mean())
    report["checks"]["lpips"] = {
        "self_distance": same,
        "different_scene_distance": different,
        "pass": abs(same) <= 1e-6 and different > same,
    }
    sys.path.insert(0, str((ROOT / "evaluation/visual")))
    from baselines.evaluation.visual.eval_diversity import semantic_distance
    from baselines.evaluation.visual.eval_diversity import INDOOR_CLASS_IDS

    sem = runs[0] / "renders/semantic_pred/semantic_000.png"
    semantic_self = semantic_distance(sem, sem, INDOOR_CLASS_IDS)
    report["checks"]["semantic_1miou"] = {
        "self_distance": semantic_self,
        "pass": abs(semantic_self) <= 1e-6,
    }
    # eval_iqa.py evaluates one file at a time for BOTH metrics. Batch 8 is
    # diagnostic only and must not silently become the production setting.
    report["production_iqa_batch_size"] = 1
    report["all_diagnostics_passed"] = all(
        v
        for check in report["checks"].values()
        for k, v in check.items()
        if k == "pass" or k.endswith("_pass")
    )
    report["passed"] = all(
        v
        for check in report["checks"].values()
        for k, v in check.items()
        if k in {"pass", "repeat_pass"}
    )
    report["batch8_approved_for_production"] = False
    report[
        "note"
    ] = "Production batch-1 stability only; preserve the batch-8 tolerance result separately. No tolerance relaxation and no batch-8 IQA in formal evaluation."
    output = ROOT / "results/gpt6_astra/smoke/numerical_sanity.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
