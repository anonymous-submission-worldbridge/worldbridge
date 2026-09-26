#!/usr/bin/env python3
"""Create deterministic four-item contact sheets for GLM-5.3 montage review."""
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
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    args = parser.parse_args()
    package = ROOT / "annotations/glm_5_3" / args.domain
    output = ROOT / "work/glm_5_3/synthetic_review" / args.domain
    output.mkdir(parents=True, exist_ok=True)
    with (package / "items.csv").open(newline="", encoding="utf-8") as handle:
        items = list(csv.DictReader(handle))
    if not items:
        raise RuntimeError("Annotation package contains no successful items")
    font = ImageFont.load_default(size=18)
    for offset in range(0, len(items), 4):
        rows = items[offset : offset + 4]
        sheet = Image.new("RGB", (1920, 632), "white")
        draw = ImageDraw.Draw(sheet)
        for local_index, item in enumerate(rows):
            with Image.open(package / item["montage"]) as opened:
                montage = opened.convert("RGB").resize(
                    (960, 292), Image.Resampling.LANCZOS
                )
            column, row = local_index % 2, local_index // 2
            x, y = column * 960, row * 316
            sheet.paste(montage, (x, y))
            draw.text(
                (x + 7, y + 294),
                f"item {offset + local_index + 1}: {item['blind_id']}",
                fill="black",
                font=font,
            )
        sheet.save(
            output / f"review_{offset // 4 + 1:02d}.jpg", quality=90, optimize=True
        )
    print(f"wrote {(len(items) + 3) // 4} sheets for {len(items)} {args.domain} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
