#!/usr/bin/env python3
"""Build compact contact sheets from an anonymous Table-2 rating package."""

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
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--items-per-sheet", type=int, default=10)
    args = parser.parse_args()

    with (args.package / "items.csv").open(newline="", encoding="utf-8") as handle:
        items = list(csv.DictReader(handle))
    args.output.mkdir(parents=True, exist_ok=True)
    tile_width, tile_height = 960, 292
    columns = 2
    rows = math.ceil(args.items_per_sheet / columns)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    except OSError:
        font = ImageFont.load_default()

    for page_start in range(0, len(items), args.items_per_sheet):
        page_items = items[page_start : page_start + args.items_per_sheet]
        canvas = Image.new(
            "RGB", (columns * tile_width, rows * (tile_height + 24)), "white"
        )
        draw = ImageDraw.Draw(canvas)
        for offset, item in enumerate(page_items):
            path = args.package / item["montage"]
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            x = (offset % columns) * tile_width
            y = (offset // columns) * (tile_height + 24)
            canvas.paste(image, (x, y))
            draw.text(
                (x + 8, y + tile_height + 2),
                f"item {page_start + offset + 1}: {item['blind_id']}",
                fill="black",
                font=font,
            )
        page_number = page_start // args.items_per_sheet + 1
        canvas.save(args.output / f"review_{page_number:02d}.jpg", quality=92)
    print(
        f"REVIEW_SHEETS_COMPLETE items={len(items)} pages={math.ceil(len(items) / args.items_per_sheet)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
