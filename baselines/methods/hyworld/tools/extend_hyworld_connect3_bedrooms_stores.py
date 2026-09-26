#!/usr/bin/env python3
"""Append two bedroom/storefront HY-World 2.0 pairs to connect3.

The store scenes are native outdoor commercial/storefront worlds because the
available HY-World 2.0 benchmark has no indoor retail category.  The manifests
record that scope explicitly.  All four scenes are freshly fitted enhanced-view
3D Gaussian models using the same policy as connect3.
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


import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import baselines.methods.hyworld.tools.build_hyworld_connect2_native as base
import baselines.methods.hyworld.tools.build_hyworld_connect3_enhanced as enhanced


REPO_ROOT = base.REPO_ROOT
BASELINES = base.BASELINES
SCRIPT = Path(__file__).resolve()
WORK_ROOT = BASELINES / "work/hyworld2_connect3_bedroom_store_extension"
CANDIDATE = WORK_ROOT / "candidate"
ENHANCED_DATA_ROOT = WORK_ROOT / "enhanced_gs_data"
FINAL_ROOT = BASELINES / "annotations/hyworld2/connect3"

EXTRA_PAIRS: tuple[dict[str, Any], ...] = (
    {
        "name": "scene_07_twin_bedroom_and_dense_retail_main_street",
        "indoor": ("indoor_bedroom_02", 3),
        "outdoor": ("urban_commercial_main_side_07", 2),
        "indoor_label": "twin bedroom",
        "outdoor_label": "dense retail main street storefronts",
    },
    {
        "name": "scene_08_traditional_bedroom_and_tree_lined_corner_shops",
        "indoor": ("indoor_bedroom_03", 3),
        "outdoor": ("urban_mixed_use_t_junction_11", 1),
        "indoor_label": "traditional wood-furnished bedroom",
        "outdoor_label": "tree-lined mixed-use corner shops",
    },
)

# Reuse the trained and validated connect3 pipeline in an isolated work tree.
base.PAIRS = EXTRA_PAIRS
base.WORK_ROOT = WORK_ROOT
base.CANDIDATE = CANDIDATE
enhanced.WORK_ROOT = WORK_ROOT
enhanced.CANDIDATE = CANDIDATE
enhanced.ENHANCED_DATA_ROOT = ENHANCED_DATA_ROOT
enhanced.SCRIPT = SCRIPT


def pair_by_name(name: str) -> dict[str, Any]:
    return next(pair for pair in EXTRA_PAIRS if pair["name"] == name)


def patch_category_manifest(pair_name: str, side: str) -> None:
    path = CANDIDATE / pair_name / side / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    pair = pair_by_name(pair_name)
    if side == "indoor":
        payload["requested_scene_category"] = "bedroom"
        payload["semantic_scope"] = "indoor bedroom"
        payload["scene_label"] = pair["indoor_label"]
    else:
        payload["requested_scene_category"] = "store"
        payload["semantic_scope"] = "outdoor commercial storefront street"
        payload["scene_label"] = pair["outdoor_label"]
        payload["store_scope_note_zh"] = (
            "The result is a native outdoor commercial street scene from HY-World 2.0; it uses an existing local model matrix."
            "There is no indoor retail store category, so it does not claim to be an indoor store."
        )
    base.atomic_json(path, payload)


def train(gpu: int) -> None:
    enhanced.train_all(gpu)


def render_one(pair_name: str, side: str, gpu: int) -> None:
    enhanced.render_side(pair_name, side, gpu)
    patch_category_manifest(pair_name, side)


def render(gpu: int) -> None:
    environment = base.runtime_environment(gpu)
    sides = base.selected_sides()
    for index, (pair_name, side, _, _) in enumerate(sides, start=1):
        if enhanced.render_complete(pair_name, side):
            patch_category_manifest(pair_name, side)
            print(f"RENDER_SKIP {index}/{len(sides)} {pair_name}/{side}", flush=True)
            continue
        print(f"RENDER_START {index}/{len(sides)} {pair_name}/{side}", flush=True)
        result = subprocess.run(
            [
                str(base.PYTHON),
                str(SCRIPT),
                "render-one",
                "--pair",
                pair_name,
                "--side",
                side,
                "--gpu",
                str(gpu),
            ],
            cwd=REPO_ROOT,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Render failed for {pair_name}/{side}")


def regenerate_checksums(root: Path) -> int:
    checksum_path = root / "SHA256SUMS"
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == checksum_path:
            continue
        rows.append(f"{base.sha256_file(path)}  {path.relative_to(root)}")
    checksum_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def package() -> None:
    base.package()
    for pair in EXTRA_PAIRS:
        for side in ("indoor", "outdoor"):
            patch_category_manifest(pair["name"], side)
        pair_path = CANDIDATE / pair["name"] / "manifest.json"
        payload = json.loads(pair_path.read_text(encoding="utf-8"))
        payload["schema_version"] = "hyworld2-connect3-category-extension-pair-v1"
        payload["requested_categories"] = {
            "indoor": "bedroom",
            "outdoor": "store",
        }
        payload["store_scope"] = "outdoor commercial storefront street"
        base.atomic_json(pair_path, payload)

    delivery_path = CANDIDATE / "delivery_manifest.json"
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["schema_version"] = "hyworld2-connect3-category-extension-v1"
    delivery["quality_tier"] = "enhanced-native-views-2000-step"
    delivery["training_view_enhancement"] = enhanced.enhancement_record()
    delivery["requested_addition"] = {
        "bedroom_scenes": 2,
        "store_scenes": 2,
        "store_scope": "outdoor commercial storefront streets",
    }
    base.atomic_json(delivery_path, delivery)
    (CANDIDATE / "README.md").write_text(
        "# HY-World 2.0 Connect3 bedroom and store expansion \n\n"
        "This extension includes two sets of paired scenes: one for a bedroom 3DGS scenario and another for an outdoor commercial storefront scene. "
        "3DGS scene. All four models were retrained for 2000 steps using the enhanced native view strategy of connect3. \n\n"
        "Please note: The local HY-World 2.0 baseline matrix does not include an indoor retail store category, so the shop results are based on general categories."
        "Clearly define the outdoor commercial street of the store, and do not claim it as an indoor shop. \n",
        encoding="utf-8",
    )
    files = regenerate_checksums(CANDIDATE)
    print(f"PACKAGE_DONE pairs={len(EXTRA_PAIRS)} files={files}", flush=True)


def final_readme() -> str:
    return """# HY-World 2.0 Connect3 Clear Enhancements

This directory contains 8 sets of indoor/outdoor visual pairs, totaling 16 real HY-World 2.0 3D Gaussians.
Splatting scenario. The first 6 groups are the original connect3 delivery; groups 7 and 8 add two bedroom scenarios and
Two commercial street scenes. All models were re-fitted to the original view from the native HY-World training dataset using 2000 steps.

Each side contains 24 independent 1600x900 PNGs, one 120-frame 960x540 H.264 video, and reality.
`model/scene.ply`, training checkpoint, original HY-World panorama and complete source hash. Image none
Stitching, unnumbered watermarks, field of view as 100° / 112° / 120°.

This version re-trains 3DGs after deterministic local contrast and multiscale sharpening of the original 832x480 training view.
There is no neuro-super-resolution, generative retouching, or GPT-Astra/BLENDER replacement for scenes.

Category boundaries: `indoor` for groups 7 and 8 is bedroom; `outdoor` is clearly a commercial space with a front street shop.
Street view. The existing local HY-World 2.0 matrix does not include an indoor retail store category, so they will not be described as stores.
In indoor environments. HY-World 2.0 does not generate native joint world within shared coordinate systems; each pair is visual.
Pair, without claiming for geometric doorways or native connected paths.
"""


def install() -> None:
    if not FINAL_ROOT.is_dir():
        raise FileNotFoundError(FINAL_ROOT)
    if not (CANDIDATE / "SHA256SUMS").is_file():
        raise FileNotFoundError("Package the extension before installing it")

    targets = [
        (CANDIDATE / pair["name"], FINAL_ROOT / pair["name"]) for pair in EXTRA_PAIRS
    ]
    conflicts = [str(target) for _, target in targets if target.exists()]
    if conflicts:
        raise FileExistsError(f"Refusing to overwrite existing additions: {conflicts}")
    missing = [str(source) for source, _ in targets if not source.is_dir()]
    if missing:
        raise FileNotFoundError(f"Missing packaged pair directories: {missing}")

    for source, target in targets:
        source.replace(target)

    pair_manifests = []
    for path in sorted(FINAL_ROOT.glob("scene_*/manifest.json")):
        pair_manifests.append(json.loads(path.read_text(encoding="utf-8")))
    if len(pair_manifests) != 8:
        raise ValueError(
            f"Expected 8 final pair manifests, found {len(pair_manifests)}"
        )

    delivery_path = FINAL_ROOT / "delivery_manifest.json"
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["schema_version"] = "hyworld2-connect3-enhanced-delivery-v2"
    delivery["scene_pair_count"] = 8
    delivery["total_native_3d_scenes"] = 16
    delivery["scenes"] = pair_manifests
    delivery["category_addition"] = {
        "bedroom_scenes": 2,
        "store_scenes": 2,
        "store_scope": "outdoor commercial storefront streets",
        "pair_names": [pair["name"] for pair in EXTRA_PAIRS],
    }
    base.atomic_json(delivery_path, delivery)
    (FINAL_ROOT / "README.md").write_text(final_readme(), encoding="utf-8")
    files = regenerate_checksums(FINAL_ROOT)

    # Only extension root metadata remains after the two pair directories move.
    if CANDIDATE.exists():
        shutil.rmtree(CANDIDATE)
    if ENHANCED_DATA_ROOT.exists():
        shutil.rmtree(ENHANCED_DATA_ROOT)
    print(f"INSTALL_DONE root={FINAL_ROOT} pairs=8 files={files}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("train", "render", "package", "install", "all"):
        child = subparsers.add_parser(action)
        child.add_argument("--gpu", type=int, default=4)
    render_one_parser = subparsers.add_parser("render-one")
    render_one_parser.add_argument(
        "--pair", required=True, choices=[pair["name"] for pair in EXTRA_PAIRS]
    )
    render_one_parser.add_argument(
        "--side", required=True, choices=("indoor", "outdoor")
    )
    render_one_parser.add_argument("--gpu", type=int, default=4)
    args = parser.parse_args()

    if args.action == "train":
        train(args.gpu)
    elif args.action == "render":
        render(args.gpu)
    elif args.action == "render-one":
        render_one(args.pair, args.side, args.gpu)
    elif args.action == "package":
        package()
    elif args.action == "install":
        install()
    elif args.action == "all":
        train(args.gpu)
        render(args.gpu)
        package()
        install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
