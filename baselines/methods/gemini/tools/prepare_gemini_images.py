#!/usr/bin/env python3
"""Expose selected Gemini 3.1 Pro anchors as standalone showcase images.

The annotation montages are downsampled blind-review derivatives with a title
and burned-in view numbers.  The original unlabelled 1280x720 PNG anchors are
retained under ``baselines/data/table2``.  This utility verifies that each
source matches its montage tile outside the label area, then hard-links the
source into the requested annotation ``images`` directory.  No pixels are
changed and no image data is duplicated on disk.
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


import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
ANNOTATIONS = BASELINES / "annotations/gemini_3_1_pro"
TILE_SIZE = (480, 270)
MONTAGE_SIZE = (1920, 584)
HEADER_HEIGHT = 44
SOURCE_SIZE = (1280, 720)


@dataclass(frozen=True)
class Scene:
    domain: str
    blind_id: str
    anchors: Path

    @property
    def montage(self) -> Path:
        return ANNOTATIONS / self.domain / "montages" / f"{self.blind_id}.jpg"


SCENES = (
    Scene(
        "indoor",
        "I-8A92EED35374",
        BASELINES
        / "data/table2/indoor/gemini_3_1_pro/indoor_living_room_03/seed_1/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-36DD97FD3038",
        BASELINES
        / "data/table2/indoor/gemini_3_1_pro/indoor_kitchen_04/seed_0/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-43FB2B945021",
        BASELINES
        / "data/table2/indoor/gemini_3_1_pro/indoor_bedroom_04/seed_2/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-65573B610E7D",
        BASELINES
        / "data/table2/indoor/gemini_3_1_pro/indoor_bedroom_00/seed_0/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-324701333E3D",
        BASELINES
        / "data/table2/indoor/gemini_3_1_pro/indoor_dining_room_00/seed_0/renders/anchors",
    ),
    Scene(
        "urban",
        "U-5DD012757C12",
        BASELINES
        / "data/table2/urban/gemini_3_1_pro/urban_residential_irregular_04/seed_2/renders/anchors",
    ),
    Scene(
        "urban",
        "U-6D1C9BD1A875",
        BASELINES
        / "data/table2/urban/gemini_3_1_pro/urban_mixed_use_four_way_10/seed_0/renders/anchors",
    ),
    Scene(
        "urban",
        "U-443ED98F1DCF",
        BASELINES
        / "data/table2/urban/gemini_3_1_pro/urban_mixed_use_irregular_14/seed_1/renders/anchors",
    ),
    Scene(
        "urban",
        "U-FE86F566B321",
        BASELINES
        / "data/table2/urban/gemini_3_1_pro/urban_mixed_use_irregular_14/seed_3/renders/anchors",
    ),
)


def source_images(scene: Scene) -> list[Path]:
    sources = sorted(scene.anchors.glob("rgb_*.png"))
    expected = [f"rgb_{index:03d}.png" for index in range(8)]
    if [source.name for source in sources] != expected:
        raise RuntimeError(f"Expected {expected} in {scene.anchors}")
    return sources


def verify_source_size(source: Path) -> None:
    with Image.open(source) as handle:
        if handle.size != SOURCE_SIZE or handle.mode != "RGB":
            raise RuntimeError(
                f"Expected {SOURCE_SIZE[0]}x{SOURCE_SIZE[1]} RGB source: {source}; "
                f"got {handle.size} {handle.mode}"
            )


def montage_mae(montage: Image.Image, source: Path, view_index: int) -> float:
    with Image.open(source) as handle:
        reference = handle.convert("RGB")
        reference.thumbnail(TILE_SIZE, Image.Resampling.LANCZOS)
    if reference.size != TILE_SIZE:
        raise RuntimeError(f"Unexpected downsampled size {reference.size}: {source}")

    col, row = view_index % 4, view_index // 4
    left = col * TILE_SIZE[0]
    top = HEADER_HEIGHT + row * TILE_SIZE[1]
    tile = montage.crop((left, top, left + TILE_SIZE[0], top + TILE_SIZE[1]))

    # Ignore the burned-in number and a small margin for JPEG ringing.
    tile.paste(reference.crop((0, 0, 56, 45)), (0, 0))
    difference = ImageChops.difference(tile, reference)
    channel_means = ImageStat.Stat(difference).mean
    return sum(channel_means) / len(channel_means)


def verify_scene(scene: Scene, sources: list[Path]) -> list[float]:
    if not scene.montage.is_file():
        raise FileNotFoundError(f"Missing montage: {scene.montage}")
    for source in sources:
        verify_source_size(source)
    with Image.open(scene.montage) as handle:
        montage = handle.convert("RGB")
    if montage.size != MONTAGE_SIZE:
        raise RuntimeError(f"Unexpected montage size {montage.size}: {scene.montage}")
    errors = [
        montage_mae(montage, source, view_index)
        for view_index, source in enumerate(sources)
    ]
    if max(errors) > 3.0:
        raise RuntimeError(
            f"Source/montage mismatch for {scene.blind_id}; maximum MAE={max(errors):.6f}"
        )
    return errors


def expose(source: Path, destination: Path) -> str:
    if destination.exists():
        source_stat = source.stat()
        destination_stat = destination.stat()
        if (
            source_stat.st_dev == destination_stat.st_dev
            and source_stat.st_ino == destination_stat.st_ino
        ):
            return "reused"
        raise FileExistsError(f"Refusing to replace unrelated file: {destination}")
    os.link(source, destination)
    return "created"


def main() -> None:
    counts = {"created": 0, "reused": 0}
    errors: list[float] = []
    for scene in SCENES:
        sources = source_images(scene)
        errors.extend(verify_scene(scene, sources))
        output_dir = ANNOTATIONS / scene.domain / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(sources, start=1):
            destination = output_dir / f"{scene.blind_id}_view_{index:02d}.png"
            counts[expose(source, destination)] += 1
    print(
        f"Standalone images ready: {counts['created']} created, "
        f"{counts['reused']} reused"
    )
    print(
        "Verified 72 source/montage pairs outside labels: "
        f"mean MAE={sum(errors) / len(errors):.6f}, max MAE={max(errors):.6f}"
    )


if __name__ == "__main__":
    main()
