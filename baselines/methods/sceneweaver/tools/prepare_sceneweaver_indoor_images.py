#!/usr/bin/env python3
"""Export standalone, tone-balanced SceneWeaver indoor anchor images.

The source montages are blind-review derivatives.  Their unlabelled source
frames already exist as the original 1280x720 anchor renders, so this script
uses those frames directly instead of cropping or inpainting the montages.
Only a fixed, scene-level RGB tone curve is applied; scene content, geometry,
framing, and resolution are unchanged.
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
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
ANNOTATION_ROOT = BASELINES / "annotations/sceneweaver/indoor"


@dataclass(frozen=True)
class Scene:
    blind_id: str
    source_dir: Path
    tone_profile: str


SCENES = (
    Scene(
        "I-1A0606053537",
        BASELINES
        / "data/table2/indoor/sceneweaver/indoor_bedroom_03/seed_1/renders/anchors",
        "mild-highlight-compression",
    ),
    Scene(
        "I-1B9FE77D024C",
        BASELINES
        / "data/table2/indoor/sceneweaver/indoor_bedroom_02/seed_0/renders/anchors",
        "shadow-lift-highlight-compression",
    ),
    Scene(
        "I-9A1619718351",
        BASELINES
        / "data/table2/indoor/sceneweaver/indoor_kitchen_04/seed_2/renders/anchors",
        "overexposure-reduction",
    ),
)


# A single curve is shared by all eight views of each scene.  This avoids
# view-to-view exposure pumping while bringing shadows and clipped-looking
# highlights into a display-friendly range.
TONE_CURVES = {
    "mild-highlight-compression": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.06, 0.17, 0.32, 0.50, 0.67, 0.79, 0.92),
    ),
    "shadow-lift-highlight-compression": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.075, 0.21, 0.38, 0.56, 0.71, 0.82, 0.93),
    ),
    "overexposure-reduction": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.06, 0.17, 0.31, 0.46, 0.60, 0.72, 0.87),
    ),
}


def make_lut(profile: str) -> list[int]:
    x, y = TONE_CURVES[profile]
    values = np.interp(np.arange(256, dtype=np.float32) / 255.0, x, y)
    return np.rint(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8).tolist()


def luminance_stats(image: Image.Image) -> dict[str, float]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    p01, p50, p99 = np.percentile(luminance, (1, 50, 99))
    return {
        "p01": float(p01),
        "p50": float(p50),
        "p99": float(p99),
        "shadow_clip_pct": float((luminance < 0.02).mean() * 100.0),
        "highlight_clip_pct": float((luminance > 0.98).mean() * 100.0),
    }


def manifest_row(
    scene: Scene,
    source: Path,
    destination: Path,
    index: int,
    before: dict[str, float],
    after: dict[str, float],
) -> dict[str, str | int | float]:
    row: dict[str, str | int | float] = {
        "blind_id": scene.blind_id,
        "view_index_one_based": index + 1,
        "source_index_zero_based": index,
        "source": str(source.relative_to(REPO_ROOT)),
        "output": str(destination.relative_to(REPO_ROOT)),
        "tone_profile": scene.tone_profile,
    }
    for prefix, stats in (("before", before), ("after", after)):
        for key, value in stats.items():
            row[f"{prefix}_{key}"] = round(value, 6)
    return row


def export(output_dir: Path, overwrite: bool) -> list[dict[str, str | int | float]]:
    rows: list[dict[str, str | int | float]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for scene in SCENES:
        sources = sorted(scene.source_dir.glob("rgb_*.png"))
        if [path.name for path in sources] != [
            f"rgb_{index:03d}.png" for index in range(8)
        ]:
            raise RuntimeError(
                f"Expected rgb_000.png through rgb_007.png in {scene.source_dir}"
            )
        lut = make_lut(scene.tone_profile)
        for index, source in enumerate(sources):
            destination = output_dir / f"{scene.blind_id}_view_{index + 1:02d}.png"
            if destination.exists() and not overwrite:
                raise FileExistsError(
                    f"Refusing to overwrite {destination}; pass --overwrite"
                )
            with Image.open(source) as handle:
                original = handle.convert("RGB")
            if original.size != (1280, 720):
                raise RuntimeError(f"Unexpected source size {original.size}: {source}")
            corrected = original.point(lut * 3)
            corrected.save(destination, format="PNG", optimize=True, compress_level=9)
            rows.append(
                manifest_row(
                    scene,
                    source,
                    destination,
                    index,
                    luminance_stats(original),
                    luminance_stats(corrected),
                )
            )
    return rows


def write_manifest(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ANNOTATION_ROOT / "images",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ANNOTATION_ROOT / "images/images_manifest.csv",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    manifest = args.manifest.resolve()
    if BASELINES.resolve() not in output_dir.parents:
        raise ValueError(f"Output directory must stay under {BASELINES}")
    if BASELINES.resolve() not in manifest.parents:
        raise ValueError(f"Manifest must stay under {BASELINES}")
    if manifest.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite {manifest}; pass --overwrite")
    rows = export(output_dir, args.overwrite)
    write_manifest(manifest, rows)
    print(f"Wrote {len(rows)} standalone images to {output_dir}")
    print(f"Wrote luminance provenance to {manifest}")


if __name__ == "__main__":
    main()
