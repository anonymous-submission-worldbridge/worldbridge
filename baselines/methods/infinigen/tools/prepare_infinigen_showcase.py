#!/usr/bin/env python3
"""Prepare single-image Infinigen Indoor visualization assets.

The script only reads existing renders/videos and writes a compact, reproducible
showcase under ``baselines/``.  It deliberately avoids generative image editing:
geometry, materials, and scene content remain pixel-identical apart from the two
explicit scene-level tone curves below.
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


@dataclass(frozen=True)
class AnchorScene:
    blind_id: str
    source_dir: Path
    tone_profile: str


ANCHOR_SCENES = (
    AnchorScene(
        "I-E6BCF0F9ADEC",
        BASELINES
        / "data/table2/indoor/infinigen_indoors/indoor_dining_room_04/seed_1/renders/anchors",
        "identity-normal",
    ),
    AnchorScene(
        "I-879E14CE98E2",
        BASELINES
        / "data/table2/indoor/infinigen_indoors/indoor_bedroom_03/seed_2/renders/anchors",
        "identity-normal",
    ),
    AnchorScene(
        "I-13DFDB7A9401",
        BASELINES
        / "data/table2/indoor/infinigen_indoors/indoor_dining_room_01/seed_2/renders/anchors",
        "lift-shadows-compress-highlights",
    ),
    AnchorScene(
        "I-5D2AC184053B",
        BASELINES
        / "data/table2/indoor/infinigen_indoors/indoor_living_room_02/seed_0/renders/anchors",
        "reduce-exposure-compress-highlights",
    ),
)


# Shared RGB-channel curves keep all views in a scene photometrically consistent.
# The dark scene is lifted in the lower midtones while its windows are compressed;
# the bright scene is pulled down mainly in its lamp/highlight range.
TONE_CURVES = {
    "lift-shadows-compress-highlights": (
        (0.00, 0.05, 0.15, 0.30, 0.55, 0.80, 1.00),
        (0.00, 0.075, 0.22, 0.40, 0.62, 0.82, 0.95),
    ),
    "reduce-exposure-compress-highlights": (
        (0.00, 0.10, 0.30, 0.50, 0.70, 0.90, 1.00),
        (0.00, 0.08, 0.24, 0.43, 0.60, 0.78, 0.91),
    ),
}


EXTRA_7D_SEQUENCE = (
    BASELINES
    / "data/table2/indoor/infinigen_indoors/indoor_dining_room_01/seed_1/renders/sequence"
)
EXTRA_68_SEQUENCE = (
    BASELINES
    / "data/table2/indoor/infinigen_indoors/indoor_dining_room_03"
    / "seed_3_pre_qalign_20260904/renders/sequence"
)
EXTRA_FRAME_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)


def tone_lut(profile: str) -> list[int] | None:
    if profile == "identity-normal":
        return None
    x, y = TONE_CURVES[profile]
    values = np.interp(np.arange(256, dtype=np.float32) / 255.0, x, y)
    return np.rint(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8).tolist()


def apply_tone(image: Image.Image, profile: str) -> Image.Image:
    image = image.convert("RGB")
    lut = tone_lut(profile)
    return image if lut is None else image.point(lut * 3)


def luminance_stats(image: Image.Image) -> dict[str, float]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    p01, p50, p99 = np.percentile(lum, (1, 50, 99))
    return {
        "p01": float(p01),
        "p50": float(p50),
        "p99": float(p99),
        "shadow_clip_pct": float((lum < 0.02).mean() * 100.0),
        "highlight_clip_pct": float((lum > 0.98).mean() * 100.0),
    }


def save_jpeg(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        destination,
        format="JPEG",
        quality=95,
        subsampling=0,
        optimize=True,
        progressive=True,
    )


def manifest_row(
    blind_id: str,
    view_kind: str,
    output: Path,
    source: str,
    source_index: int,
    profile: str,
    before: dict[str, float],
    after: dict[str, float],
) -> dict[str, str | int | float]:
    return {
        "blind_id": blind_id,
        "view_kind": view_kind,
        "output": str(output),
        "source": source,
        "source_index_zero_based": source_index,
        "tone_profile": profile,
        "before_p01": round(before["p01"], 6),
        "before_p50": round(before["p50"], 6),
        "before_p99": round(before["p99"], 6),
        "before_shadow_clip_pct": round(before["shadow_clip_pct"], 6),
        "before_highlight_clip_pct": round(before["highlight_clip_pct"], 6),
        "after_p01": round(after["p01"], 6),
        "after_p50": round(after["p50"], 6),
        "after_p99": round(after["p99"], 6),
        "after_shadow_clip_pct": round(after["shadow_clip_pct"], 6),
        "after_highlight_clip_pct": round(after["highlight_clip_pct"], 6),
    }


def prepare_anchor_scenes(output_root: Path) -> list[dict[str, str | int | float]]:
    rows: list[dict[str, str | int | float]] = []
    for scene in ANCHOR_SCENES:
        sources = sorted(scene.source_dir.glob("rgb_*.png"))
        if len(sources) != 8:
            raise RuntimeError(
                f"Expected 8 anchor views in {scene.source_dir}, found {len(sources)}"
            )
        for display_index, source in enumerate(sources, start=1):
            original = Image.open(source).convert("RGB")
            corrected = apply_tone(original, scene.tone_profile)
            destination = output_root / scene.blind_id / f"view_{display_index:02d}.jpg"
            save_jpeg(corrected, destination)
            rows.append(
                manifest_row(
                    scene.blind_id,
                    "anchor",
                    destination.relative_to(output_root),
                    str(source.relative_to(REPO_ROOT)),
                    display_index - 1,
                    scene.tone_profile,
                    luminance_stats(original),
                    luminance_stats(corrected),
                )
            )
    return rows


def prepare_7d_extra_views(output_root: Path) -> list[dict[str, str | int | float]]:
    rows: list[dict[str, str | int | float]] = []
    blind_id = "I-7D9960542583"
    for display_index, source_index in enumerate(EXTRA_FRAME_INDICES, start=1):
        source = EXTRA_7D_SEQUENCE / f"rgb_{source_index:03d}.png"
        original = Image.open(source).convert("RGB")
        destination = (
            output_root
            / blind_id
            / "additional_views"
            / f"view_{display_index:02d}.jpg"
        )
        save_jpeg(original, destination)
        stats = luminance_stats(original)
        rows.append(
            manifest_row(
                blind_id,
                "existing-sequence-render",
                destination.relative_to(output_root),
                str(source.relative_to(REPO_ROOT)),
                source_index,
                "identity-normal",
                stats,
                stats,
            )
        )
    return rows


def prepare_68_extra_views(output_root: Path) -> list[dict[str, str | int | float]]:
    rows: list[dict[str, str | int | float]] = []
    blind_id = "I-68FB5C6F4E1B"
    profile = "reduce-exposure-compress-highlights"
    for display_index, source_index in enumerate(EXTRA_FRAME_INDICES, start=1):
        source = EXTRA_68_SEQUENCE / f"rgb_{source_index:03d}.png"
        original = Image.open(source).convert("RGB")
        corrected = apply_tone(original, profile)
        destination = (
            output_root
            / blind_id
            / "additional_views"
            / f"view_{display_index:02d}.jpg"
        )
        save_jpeg(corrected, destination)
        rows.append(
            manifest_row(
                blind_id,
                "existing-sequence-render",
                destination.relative_to(output_root),
                str(source.relative_to(REPO_ROOT)),
                source_index,
                profile,
                luminance_stats(original),
                luminance_stats(corrected),
            )
        )
    return rows


def write_manifest(output_root: Path, rows: list[dict[str, str | int | float]]) -> None:
    manifest = output_root / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_readme(output_root: Path) -> None:
    (output_root / "README.md").write_text(
        """# Infinigen Indoor showcase

- All deliverables are standalone JPEG images with no title, number, or other overlay.
- The four requested montage scenes use their original 1280x720 anchor renders.
- `I-13DFDB7A9401` received a fixed shadow-lift/highlight-compression curve.
- `I-5D2AC184053B` received a fixed exposure-reduction/highlight-compression curve.
- The other anchor images were already within a normal luminance range and were not tone-remapped.
- `I-7D9960542583/additional_views` samples eight existing 512x512 sequence renders; its Blender scene exists, so no redundant re-render was run.
- `I-68FB5C6F4E1B/additional_views` samples eight original 512x512 sequence renders from the archived `seed_3_pre_qalign_20260904` run; its Blender scene also exists there, so no redundant re-render was run. These bright frames received the same fixed exposure-reduction/highlight-compression curve.
- `manifest.csv` records every source frame and before/after luminance statistics.
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BASELINES / "visualizations/infinigen_indoor_showcase_20260917",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rebuild files in an existing output directory without deleting it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = args.output_root.resolve()
    if BASELINES.resolve() not in output_root.parents:
        raise ValueError(f"Output must stay under {BASELINES}")
    if output_root.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=args.overwrite)

    rows = prepare_anchor_scenes(output_root)
    rows.extend(prepare_7d_extra_views(output_root))
    rows.extend(prepare_68_extra_views(output_root))
    write_manifest(output_root, rows)
    write_readme(output_root)
    print(f"Wrote {len(rows)} standalone images to {output_root}")


if __name__ == "__main__":
    main()
