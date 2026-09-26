#!/usr/bin/env python3
"""Expose selected GLM-5.3 Flash anchors as standalone showcase images.

The annotation montages add a title and per-tile view numbers.  Their clean
source anchors are retained under ``baselines/data/table2``.  This utility
hard-links those PNGs into the requested annotation ``images`` directories,
so no image data is recompressed or duplicated on disk.
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


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
ANNOTATIONS = BASELINES / "annotations/glm53_flash"


@dataclass(frozen=True)
class Scene:
    domain: str
    blind_id: str
    anchors: Path


SCENES = (
    Scene(
        "indoor",
        "I-8BCA5E498F66",
        BASELINES
        / "data/table2/indoor/glm53_flash/indoor_bedroom_02/seed_3/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-370663C1B700",
        BASELINES
        / "data/table2/indoor/glm53_flash/indoor_living_room_04/seed_3/renders/anchors",
    ),
    Scene(
        "indoor",
        "I-D68F32D51FAB",
        BASELINES
        / "data/table2/indoor/glm53_flash/indoor_bedroom_04/seed_3/renders/anchors",
    ),
    Scene(
        "urban",
        "U-7C09F602ACCB",
        BASELINES
        / "data/table2/urban/glm53_flash/urban_commercial_main_side_07/seed_1/renders/anchors",
    ),
    Scene(
        "urban",
        "U-11B4169BA59F",
        BASELINES
        / "data/table2/urban/glm53_flash/urban_commercial_main_side_07/seed_0/renders/anchors",
    ),
    Scene(
        "urban",
        "U-EF8F42A71726",
        BASELINES
        / "data/table2/urban/glm53_flash/urban_mixed_use_t_junction_11/seed_2/renders/anchors",
    ),
)


def source_images(scene: Scene) -> list[Path]:
    sources = sorted(scene.anchors.glob("rgb_*.png"))
    expected = [f"rgb_{index:03d}.png" for index in range(8)]
    if [source.name for source in sources] != expected:
        raise RuntimeError(f"Expected {expected} in {scene.anchors}")
    return sources


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
    for scene in SCENES:
        output_dir = ANNOTATIONS / scene.domain / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(source_images(scene), start=1):
            destination = output_dir / f"{scene.blind_id}_view_{index:02d}.png"
            counts[expose(source, destination)] += 1
    print(
        f"Standalone images ready: {counts['created']} created, "
        f"{counts['reused']} reused"
    )


if __name__ == "__main__":
    main()
