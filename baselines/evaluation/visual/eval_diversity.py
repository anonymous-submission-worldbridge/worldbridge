#!/usr/bin/env python3
"""Compute ITT appearance and layout diversity for one method and domain."""

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
import itertools
import json
import os
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
os.environ.setdefault("TORCH_HOME", str(BASELINES_ROOT / "cache/torch"))
os.environ.setdefault("HF_HOME", str(BASELINES_ROOT / "cache/huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES_ROOT / "cache/xdg_metrics"))

import numpy as np  # noqa: E402
import pyiqa  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402


# ADE20K labels relevant to shared indoor scene structure and furniture.
INDOOR_CLASS_IDS = {
    0,  # wall
    3,  # floor
    5,  # ceiling
    7,  # bed
    8,  # windowpane
    10,  # cabinet
    14,  # door
    15,  # table
    17,  # plant
    18,  # curtain
    19,  # chair
    22,  # painting
    23,  # sofa
    24,  # shelf
    27,  # mirror
    28,  # rug
    30,  # armchair
    31,  # seat
    33,  # desk
    35,  # wardrobe
    36,  # lamp
    37,  # bathtub
    39,  # cushion
    42,  # column
    44,  # chest of drawers
    45,  # counter
    47,  # sink
    49,  # fireplace
    50,  # refrigerator
    53,  # stairs
    55,  # display case
    57,  # pillow
    58,  # screen door
    59,  # stairway
    62,  # bookcase
    63,  # blind
    64,  # coffee table
    65,  # toilet
    66,  # flower
    67,  # book
    69,  # bench
    70,  # countertop
    71,  # stove
    73,  # kitchen island
    74,  # computer
    75,  # swivel chair
    81,  # towel
    82,  # light
    85,  # chandelier
    89,  # television receiver
    93,  # pole/column
    95,  # bannister
    97,  # ottoman
    98,  # bottle
    99,  # buffet
    100,  # poster
    107,  # washer
    108,  # plaything
    110,  # stool
    112,  # basket
    115,  # bag
    117,  # cradle
    118,  # oven
    121,  # step
    124,  # microwave
    125,  # pot
    129,  # dishwasher
    130,  # screen
    131,  # blanket
    133,  # hood
    134,  # sconce
    135,  # vase
    137,  # tray
    138,  # ashcan
    139,  # fan
    141,  # CRT screen
    142,  # plate
    143,  # monitor
    144,  # bulletin board
    145,  # shower
    146,  # radiator
    147,  # glass
    148,  # clock
    149,  # flag/cloth
}

# ADE20K labels relevant to common urban structure, transport, vegetation and
# street furniture.  The same fixed predictor and class subset are used for
# every method evaluated in the urban domain.
URBAN_CLASS_IDS = {
    1,  # building
    4,  # tree
    6,  # road
    11,  # sidewalk
    12,  # person
    13,  # earth/ground
    20,  # car
    25,  # house
    32,  # fence
    42,  # column
    43,  # signboard
    52,  # path
    69,  # bench
    80,  # bus
    83,  # truck
    93,  # pole
    101,  # van
    127,  # bicycle
    136,  # traffic light
    138,  # trash can
    149,  # flag
}


def load_specs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def scalar(value) -> float:
    if torch.is_tensor(value):
        value = value.detach().float().mean().cpu().item()
    return float(value)


def semantic_distance(
    path_a: Path, path_b: Path, class_ids: set[int] = INDOOR_CLASS_IDS
) -> float:
    array_a = np.asarray(Image.open(path_a), dtype=np.uint8)
    array_b = np.asarray(Image.open(path_b), dtype=np.uint8)
    if array_a.shape != array_b.shape:
        raise ValueError(f"Semantic shape mismatch: {array_a.shape} != {array_b.shape}")
    present = [
        label
        for label in class_ids
        if np.any(array_a == label) or np.any(array_b == label)
    ]
    if not present:
        return 0.0
    ious = []
    for label in present:
        mask_a = array_a == label
        mask_b = array_b == label
        union = np.logical_or(mask_a, mask_b).sum()
        intersection = np.logical_and(mask_a, mask_b).sum()
        ious.append(float(intersection / union) if union else 1.0)
    return 1.0 - float(np.mean(ious))


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
    parser.add_argument(
        "--semantic-root",
        type=Path,
        default=None,
        help="Optional semantic-map mirror root produced by generate_semantics.py.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES_ROOT / "results/diversity_per_spec.jsonl",
    )
    args = parser.parse_args()
    lpips = pyiqa.create_metric("lpips", device=args.device, as_loss=False)
    class_ids = INDOOR_CLASS_IDS if args.domain == "indoor" else URBAN_CLASS_IDS
    records = []
    for spec in load_specs(args.spec_file):
        seed_dirs = {
            seed: (
                args.data_root
                / args.domain
                / args.method
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            for seed in range(4)
        }
        valid_seeds = [
            seed for seed, path in seed_dirs.items() if (path / "SUCCESS").exists()
        ]
        pairs = list(itertools.combinations(valid_seeds, 2))
        appearance_values = []
        layout_values = []
        pair_records = []
        with torch.inference_mode():
            for seed_a, seed_b in pairs:
                run_a, run_b = seed_dirs[seed_a], seed_dirs[seed_b]
                semantic_a = (
                    args.semantic_root
                    / run_a.relative_to(args.data_root)
                    / "renders/semantic_pred"
                    if args.semantic_root is not None
                    else run_a / "renders/semantic_pred"
                )
                semantic_b = (
                    args.semantic_root
                    / run_b.relative_to(args.data_root)
                    / "renders/semantic_pred"
                    if args.semantic_root is not None
                    else run_b / "renders/semantic_pred"
                )
                view_app = []
                view_layout = []
                for view in range(8):
                    rgb_a = run_a / "renders/anchors" / f"rgb_{view:03d}.png"
                    rgb_b = run_b / "renders/anchors" / f"rgb_{view:03d}.png"
                    sem_a = semantic_a / f"semantic_{view:03d}.png"
                    sem_b = semantic_b / f"semantic_{view:03d}.png"
                    if not (
                        rgb_a.exists()
                        and rgb_b.exists()
                        and sem_a.exists()
                        and sem_b.exists()
                    ):
                        raise FileNotFoundError(
                            f"Missing diversity input for {spec['spec_id']} seeds {seed_a},{seed_b} view {view}"
                        )
                    view_app.append(scalar(lpips(str(rgb_a), str(rgb_b))))
                    view_layout.append(semantic_distance(sem_a, sem_b, class_ids))
                appearance = float(np.mean(view_app))
                layout = float(np.mean(view_layout))
                appearance_values.append(appearance)
                layout_values.append(layout)
                pair_records.append(
                    {
                        "seeds": [seed_a, seed_b],
                        "appearance": appearance,
                        "layout": layout,
                    }
                )
        success_rate = len(valid_seeds) / 4.0
        penalty = success_rate**2
        valid_appearance = (
            float(np.mean(appearance_values)) if appearance_values else 0.0
        )
        valid_layout = float(np.mean(layout_values)) if layout_values else 0.0
        record = {
            "method": args.method,
            "domain": args.domain,
            "spec_id": spec["spec_id"],
            "valid_seeds": valid_seeds,
            "success_rate": success_rate,
            "valid_pair_count": len(pairs),
            "appearance_diversity_valid": valid_appearance,
            "layout_diversity_valid": valid_layout,
            "itt_penalty": penalty,
            "appearance_diversity_itt": valid_appearance * penalty,
            "layout_diversity_itt": valid_layout * penalty,
            "pairs": pair_records,
        }
        records.append(record)
        print(
            f"DIVERSITY_OK {spec['spec_id']} pairs={len(pairs)} "
            f"appearance_itt={record['appearance_diversity_itt']:.6f} "
            f"layout_itt={record['layout_diversity_itt']:.6f}",
            flush=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in records))
    temporary.replace(args.output)
    print(f"DIVERSITY_COMPLETE records={len(records)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
