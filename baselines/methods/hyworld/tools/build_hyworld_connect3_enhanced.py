#!/usr/bin/env python3
"""Build a clearer, provenance-safe HY-World 2.0 paired 3DGS delivery.

This version deterministically enhances the existing native HY-World training
views before fitting fresh 3D Gaussian scenes.  It does not use neural image
generation or super-resolution, and it preserves HY-World's native limitation
that indoor and outdoor scenes do not share a coordinate frame.
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
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

import baselines.methods.hyworld.tools.build_hyworld_connect2_native as base


REPO_ROOT = base.REPO_ROOT
BASELINES = base.BASELINES
WORK_ROOT = BASELINES / "work/hyworld2_connect3_native"
CANDIDATE = WORK_ROOT / "candidate"
ENHANCED_DATA_ROOT = WORK_ROOT / "enhanced_gs_data"
PROBE_ROOT = BASELINES / "work/hyworld2_connect3_probe"
SCRIPT = Path(__file__).resolve()
SCHEMA = "hyworld2-connect3-enhanced-native-v1"

# Point the well-tested connect2 renderer and validators at an independent
# connect3 work tree.  No connect2 files are modified.
base.WORK_ROOT = WORK_ROOT
base.CANDIDATE = CANDIDATE

_ORIGINAL_PREPARE_TRAINING_COMMAND = base.prepare_training_command


def enhancement_record() -> dict[str, Any]:
    return {
        "kind": "deterministic_non_neural_training_view_enhancement",
        "neural_super_resolution": False,
        "generative_image_editing": False,
        "native_input_resolution": [832, 480],
        "local_contrast": "LAB CLAHE clipLimit=1.25 tileGrid=10x10",
        "multiscale_unsharp": {
            "sigma_small": 0.9,
            "weight_small": 0.55,
            "sigma_large": 2.5,
            "weight_large": 0.12,
        },
    }


def enhanced_data_dir(run: Path) -> Path:
    relative = run.relative_to(base.DATA_ROOT)
    return ENHANCED_DATA_ROOT / relative


def enhance_training_image(source: Path, target: Path) -> None:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read training image: {source}")
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    lightness = cv2.createCLAHE(clipLimit=1.25, tileGridSize=(10, 10)).apply(lightness)
    values = cv2.cvtColor(
        cv2.merge((lightness, channel_a, channel_b)), cv2.COLOR_LAB2BGR
    ).astype(np.float32)
    fine = cv2.GaussianBlur(values, (0, 0), 0.9)
    broad = cv2.GaussianBlur(values, (0, 0), 2.5)
    enhanced = np.clip(
        values + 0.55 * (values - fine) + 0.12 * (values - broad), 0, 255
    ).astype(np.uint8)
    if not cv2.imwrite(str(target), enhanced, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
        raise OSError(f"Cannot write enhanced training image: {target}")


def prepare_enhanced_data(run: Path) -> Path:
    source = run / "scene/native/gs_data"
    target = enhanced_data_dir(run)
    marker = target / "enhancement.json"
    source_images = sorted((source / "images").glob("*.png"))
    if marker.is_file() and len(list((target / "images").glob("*.png"))) == len(
        source_images
    ):
        return target
    if target.exists():
        shutil.rmtree(target)
    (target / "images").mkdir(parents=True)
    for child in source.iterdir():
        if child.name == "images":
            continue
        os.symlink(
            child.resolve(), target / child.name, target_is_directory=child.is_dir()
        )
    for source_image in source_images:
        enhance_training_image(source_image, target / "images" / source_image.name)
    payload = enhancement_record()
    payload.update(
        {
            "source_gs_data": str(source.relative_to(REPO_ROOT)),
            "image_count": len(source_images),
        }
    )
    marker.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def prepare_training_command(run: Path, model_dir: Path) -> list[str]:
    command = _ORIGINAL_PREPARE_TRAINING_COMMAND(run, model_dir)
    data_dir = prepare_enhanced_data(run)
    command[command.index("--data_dir") + 1] = str(data_dir)
    if "--sh_degree" in command:
        command[command.index("--sh_degree") + 1] = "0"
    else:
        command.extend(["--sh_degree", "0"])
    return command


def enhance_display(image: np.ndarray) -> np.ndarray:
    """Increase edge acuity without inventing semantic image content."""
    values = image.astype(np.float32)
    fine = cv2.GaussianBlur(values, (0, 0), 1.0)
    broad = cv2.GaussianBlur(values, (0, 0), 3.0)
    values = np.clip(values + 0.55 * (values - fine) + 0.12 * (values - broad), 0, 255)
    channel_mean = values.mean(axis=(0, 1), keepdims=True)
    values = np.clip((values - channel_mean) * 1.07 + channel_mean, 0, 255)
    return values.astype(np.uint8)


def save_enhanced_render(image: np.ndarray, output: Path) -> None:
    Image.fromarray(enhance_display(image)).save(output, compress_level=3)


def train_all(gpu: int) -> None:
    base.prepare_training_command = prepare_training_command
    try:
        base.train_all(gpu)
    finally:
        # Enhanced RGBs are reproducible and are not part of the delivery.
        # Remove them after each full training pass to conserve shared storage.
        if ENHANCED_DATA_ROOT.exists():
            shutil.rmtree(ENHANCED_DATA_ROOT)


def side_manifest_path(pair_name: str, side: str) -> Path:
    return CANDIDATE / pair_name / side / "manifest.json"


def patch_side_manifest(pair_name: str, side: str) -> None:
    path = side_manifest_path(pair_name, side)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = SCHEMA
    payload["training_input_preprocessing"] = enhancement_record()
    payload["spherical_harmonics_degree"] = 0
    payload["quality_tier"] = "enhanced-native-views-2000-step"
    rendering = payload["rendering"]
    rendering["display_sharpening"] = (
        "non-neural multiscale unsharp sigma=1.0/3.0 weights=0.55/0.12 "
        "plus 1.07 global contrast"
    )
    rendering["neural_super_resolution"] = False
    rendering["generative_postprocessing"] = False
    base.atomic_json(path, payload)


def render_side(pair_name: str, side: str, gpu: int) -> None:
    base.save_render = save_enhanced_render
    base.render_side(pair_name, side, gpu)
    patch_side_manifest(pair_name, side)


def render_complete(pair_name: str, side: str) -> bool:
    path = side_manifest_path(pair_name, side)
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    side_dir = path.parent
    return (
        payload.get("schema_version") == SCHEMA
        and payload.get("training_input_preprocessing", {}).get("kind")
        == "deterministic_non_neural_training_view_enhancement"
        and len(list((side_dir / "images").rglob("*.png"))) == 24
        and (side_dir / "video/walkthrough.mp4").is_file()
    )


def render_all(gpu: int) -> None:
    environment = base.runtime_environment(gpu)
    for index, (pair_name, side, _, _) in enumerate(base.selected_sides(), start=1):
        if render_complete(pair_name, side):
            print(f"RENDER_SKIP {index}/12 {pair_name}/{side}", flush=True)
            continue
        print(f"RENDER_START {index}/12 {pair_name}/{side}", flush=True)
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


def write_readme() -> None:
    readme = """# HY-World 2.0 Connect3 Clear Enhancements

This directory contains 6 sets of indoor/outdoor visual pairs, totaling 12 real HY-World 2.0 3D Gaussians.
Splatting scene. Each model is re-fitted to the original HY-World view using 2000 steps, not from scratch.
The GPT-Astra/Blender scene is not just a collection of two-dimensional images.

Compared to Connect2, this version first performs deterministic local contrast on the native 3DGS training view of 832x480.
And then retrain 3DGs with multi-scale sharpening; finally, both images and videos use the same non-neural multi-scale sharpening. No further training is done.
Download or use an ultra-resolution model without generating photorealistic edits or incorporating fictional textures into the results. Detailed parameters recorded.
On each side `manifest.json`.

Each side contains 24 independent 1600x900 PNGs, one 120-frame 960x540 H.264 video, and reality.
`model/scene.ply`, training checkpoint, original HY-World panorama and complete source hash. The image is not stitched.
No numbered watermark; field of view is 100° / 112° / 120°.

Important Boundary: HY-World 2.0 does not generate native indoor-outdoor joint world within shared coordinate system. This delivery is for indoor and
Outdoor dual 3D scene visual pairing, without claiming geometric doorways or native connectivity paths on both sides.
"""
    (CANDIDATE / "README.md").write_text(readme, encoding="utf-8")


def regenerate_checksums() -> int:
    checksum_path = CANDIDATE / "SHA256SUMS"
    rows = []
    for path in sorted(CANDIDATE.rglob("*")):
        if not path.is_file() or path == checksum_path:
            continue
        rows.append(f"{base.sha256_file(path)}  {path.relative_to(CANDIDATE)}")
    checksum_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def package() -> None:
    # The base packager performs PLY vertex, PNG, video and checksum validation.
    base.package()
    for pair in base.PAIRS:
        pair_path = CANDIDATE / pair["name"] / "manifest.json"
        payload = json.loads(pair_path.read_text(encoding="utf-8"))
        payload["schema_version"] = "hyworld2-connect3-enhanced-pair-v1"
        payload["quality_tier"] = "enhanced-native-views-2000-step"
        base.atomic_json(pair_path, payload)
    delivery_path = CANDIDATE / "delivery_manifest.json"
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["schema_version"] = "hyworld2-connect3-enhanced-delivery-v1"
    delivery["quality_tier"] = "enhanced-native-views-2000-step"
    delivery["training_view_enhancement"] = enhancement_record()
    delivery["comparison_to_connect2"] = (
        "Fresh 3DGS models trained on deterministically enhanced native views; "
        "stronger non-neural edge acuity with unchanged scene selection and cameras."
    )
    base.atomic_json(delivery_path, delivery)
    write_readme()
    file_count = regenerate_checksums()
    if PROBE_ROOT.exists():
        shutil.rmtree(PROBE_ROOT)
    print(
        f"PACKAGE_ENHANCED_DONE candidate={CANDIDATE} files={file_count}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("train", "render", "package", "all"):
        child = subparsers.add_parser(action)
        child.add_argument("--gpu", type=int, default=3)
    render_one_parser = subparsers.add_parser("render-one")
    render_one_parser.add_argument(
        "--pair", required=True, choices=[row["name"] for row in base.PAIRS]
    )
    render_one_parser.add_argument(
        "--side", required=True, choices=("indoor", "outdoor")
    )
    render_one_parser.add_argument("--gpu", type=int, default=3)
    args = parser.parse_args()

    if args.action == "train":
        train_all(args.gpu)
    elif args.action == "render":
        render_all(args.gpu)
    elif args.action == "render-one":
        render_side(args.pair, args.side, args.gpu)
    elif args.action == "package":
        package()
    elif args.action == "all":
        train_all(args.gpu)
        render_all(args.gpu)
        package()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
