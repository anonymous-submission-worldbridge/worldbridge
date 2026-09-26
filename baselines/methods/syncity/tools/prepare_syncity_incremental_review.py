#!/usr/bin/env python3
"""Prepare stable, incremental SynCity montage sheets while the matrix runs.

This utility is review-only.  It never marks a run terminal and never creates
ratings.  Rows are keyed by the final annotation package's deterministic blind
ID, so later successes cannot invalidate decisions already bound to a montage
hash.
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
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from baselines.tools.make_annotation_package import blind_id
from baselines.tools.make_annotation_package import load_specs
from baselines.tools.make_annotation_package import make_montage


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(domain: str, output: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec_index, spec in enumerate(load_specs(SPEC_FILES[domain])):
        for seed in range(4):
            slot = spec_index * 4 + seed + 1
            run_dir = (
                DATA_ROOT / domain / "syncity3k" / spec["spec_id"] / f"seed_{seed}"
            )
            if not (run_dir / "SUCCESS").is_file():
                continue
            anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
            if len(anchors) != 8:
                raise RuntimeError(
                    f"Terminal run has {len(anchors)} anchors: {run_dir}"
                )
            item_id = blind_id("syncity3k", spec["spec_id"], seed, domain)
            montage = output / "montages" / f"{item_id}.jpg"
            # A SUCCESS run is immutable.  Reuse a prior montage only when all
            # inputs predate it; this also repairs interrupted snapshot writes.
            if not montage.is_file() or any(
                anchor.stat().st_mtime_ns > montage.stat().st_mtime_ns
                for anchor in anchors
            ):
                make_montage(anchors, montage, item_id, domain)
            rows.append(
                {
                    "slot": slot,
                    "blind_id": item_id,
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "prompt_en": spec["prompt_en"],
                    "required_facts": spec["required_facts"],
                    "montage": str(montage.relative_to(output)),
                    "montage_sha256": digest(montage),
                }
            )
    return rows


def make_sheets(rows: list[dict[str, Any]], output: Path, per_sheet: int) -> None:
    if per_sheet < 1 or per_sheet > 6:
        raise ValueError("items-per-sheet must be between 1 and 6")
    columns = 2
    tile_width, tile_height, label_height = 960, 292, 58
    sheet_rows = (per_sheet + columns - 1) // columns
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    sheet_root = output / "sheets"
    sheet_root.mkdir(parents=True, exist_ok=True)
    for page_start in range(0, len(rows), per_sheet):
        page_rows = rows[page_start : page_start + per_sheet]
        canvas = Image.new(
            "RGB",
            (columns * tile_width, sheet_rows * (tile_height + label_height)),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for offset, row in enumerate(page_rows):
            with Image.open(output / row["montage"]) as source:
                image = source.convert("RGB")
                image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            x = (offset % columns) * tile_width
            y = (offset // columns) * (tile_height + label_height)
            canvas.paste(image, (x, y))
            label = (
                f"slot {row['slot']:03d} | {row['blind_id']} | "
                f"{row['spec_id']} seed={row['logical_seed']}"
            )
            draw.text((x + 8, y + tile_height + 2), label, fill="black", font=font)
            draw.text(
                (x + 8, y + tile_height + 23),
                row["prompt_en"][:112],
                fill="black",
                font=font,
            )
        page = page_start // per_sheet + 1
        canvas.save(sheet_root / f"review_{page:03d}.jpg", quality=92)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=tuple(SPEC_FILES), required=True)
    parser.add_argument("--items-per-sheet", type=int, default=4)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BASELINES_ROOT / "work/syncity3k/synthetic_review",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    output_root.relative_to(BASELINES_ROOT.resolve())
    output = output_root / args.domain
    rows = collect(args.domain, output)
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "current_items.json.tmp"
    temporary.write_text(
        json.dumps(
            {
                "method": "syncity3k",
                "domain": args.domain,
                "completed_successes": len(rows),
                "expected_slots": 100,
                "items": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output / "current_items.json")
    make_sheets(rows, output, args.items_per_sheet)
    print(
        f"SYNCITY3K_INCREMENTAL_REVIEW domain={args.domain} "
        f"successes={len(rows)} sheets={(len(rows) + args.items_per_sheet - 1) // args.items_per_sheet}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
