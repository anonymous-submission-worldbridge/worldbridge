#!/usr/bin/env python3
"""Generate offline WorldGen threshold-panorama candidates for weak demo scenes."""

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
import sys
import time
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
TOOLS = BASELINES / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from baselines.methods.worldgen.tools.worldgen_mesh_visualization import (
    configure_offline_environment,
)
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import (
    require_below_baselines,
)
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import seed_everything


TASKS_PATH = (
    BASELINES / "methods/worldgen/protocol/generation/worldgen_mesh_demo_scenes.json"
)
OUTPUT_ROOT = BASELINES / "tmp/worldgen_connect_candidates"
STRICT_THRESHOLD_SUFFIX = (
    " MANDATORY 360 COMPOSITION: the camera is exactly on the plane of one fully open "
    "entrance. The forward 180-degree half is clearly outdoors. The opposite rear "
    "180-degree half is a clearly enclosed and furnished interior room with visible "
    "ceiling, walls, furniture, and lighting. Turning around must reveal the interior, "
    "never another exterior facade, porch, arcade, or covered outdoor area. Door jambs "
    "at the left and right connect both halves into one continuous architectural space. "
    "One photograph, no split screen, no diptych, no collage."
)


def load_task(scene_id: str) -> dict[str, object]:
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    for task in tasks:
        if task["scene_id"] == scene_id:
            return task
    raise KeyError(f"Unknown scene id: {scene_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", required=True, action="append")
    parser.add_argument("--seed", required=True, type=int, action="append")
    parser.add_argument("--steps", type=int, default=50)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")

    if len(args.scene_id) != len(args.seed):
        parser.error("Repeat --scene-id and --seed the same number of times")
    requests = []
    for scene_id, seed in zip(args.scene_id, args.seed):
        task = load_task(scene_id)
        output = require_below_baselines(
            OUTPUT_ROOT / f"{scene_id}_seed_{seed}" / "panorama.png"
        )
        if output.is_file():
            print(
                f"CANDIDATE_SKIP_EXISTING path={output.relative_to(REPO)}", flush=True
            )
            continue
        requests.append((task, seed, output))
    if not requests:
        return 0

    configure_offline_environment()
    import torch
    from worldgen.pano_gen import build_pano_gen_model
    from worldgen.pano_gen import gen_pano_image

    request_names = ",".join(f"{task['scene_id']}:{seed}" for task, seed, _ in requests)
    print(f"MODEL_LOAD_START requests={request_names}", flush=True)
    model = build_pano_gen_model(device=torch.device("cuda"), low_vram=False)
    print(f"MODEL_LOAD_COMPLETE requests={request_names}", flush=True)
    for task, seed, output in requests:
        scene_id = str(task["scene_id"])
        prompt = str(task["prompt"]) + STRICT_THRESHOLD_SUFFIX
        metadata = output.with_name("candidate.json")
        seed_everything(seed)
        started = time.monotonic()
        image = gen_pano_image(
            model,
            prompt=prompt,
            seed=seed,
            guidance_scale=7.0,
            num_inference_steps=args.steps,
            height=800,
            width=1600,
            blend_extend=6,
            prefix="A high quality 360 panorama photo of",
            suffix="HDR, RAW, seamless 360 consistent, omnidirectional",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, compress_level=6)
        metadata.write_text(
            json.dumps(
                {
                    "method": "worldgen",
                    "scene_id": scene_id,
                    "seed": seed,
                    "steps": args.steps,
                    "prompt": prompt,
                    "resolution": [1600, 800],
                    "panorama": str(output.relative_to(REPO)),
                    "wall_time_seconds": round(time.monotonic() - started, 3),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"CANDIDATE_GENERATED scene={scene_id} seed={seed} "
            f"wall_time_s={time.monotonic()-started:.3f} path={output.relative_to(REPO)}",
            flush=True,
        )
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
