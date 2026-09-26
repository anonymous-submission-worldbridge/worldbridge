"""Measure localized motion and static background stability from actual renders."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

REGIONS = {
    "sky": (150, 15, 1200, 105),
    "building": (1620, 128, 1800, 203),
    "foliage": (345, 607, 990, 1027),
    "river_water": (15, 908, 300, 1065),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--frames", default="1,48")
    args = p.parse_args()
    numbers = [int(n) for n in args.frames.split(",")]
    first = np.asarray(
        Image.open(args.folder / f"frame_{numbers[0]:04d}.png").convert("RGB"),
        dtype=np.float32,
    )
    if first.shape != (1080, 1920, 3):
        raise RuntimeError("Expected native 1080p images")
    pairs = []
    for frame in numbers[1:]:
        current = np.asarray(
            Image.open(args.folder / f"frame_{frame:04d}.png").convert("RGB"),
            dtype=np.float32,
        )
        diff = np.abs(current - first)
        metrics = {}
        for name, (x0, y0, x1, y1) in REGIONS.items():
            patch = diff[y0:y1, x0:x1]
            metrics[name] = {
                "mean_absolute_RGB_difference": float(patch.mean()),
                "fraction_above_3": float((patch.max(axis=2) > 3).mean()),
                "p99_absolute_RGB_difference": float(np.percentile(patch, 99)),
            }
        pairs.append({"frames": [numbers[0], frame], "regions": metrics})
    passed = all(
        item["regions"]["sky"]["mean_absolute_RGB_difference"] < 0.1
        and item["regions"]["building"]["mean_absolute_RGB_difference"] < 1.0
        and item["regions"]["foliage"]["fraction_above_3"] > 0.01
        and item["regions"]["river_water"]["fraction_above_3"] > 0.01
        for item in pairs
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "resolution": [1920, 1080],
        "fixed_regions_xyxy": REGIONS,
        "pairs": pairs,
        "scope": "Fixed river_detail camera only; complements native transform/world audit",
    }
    (args.folder / "localized_motion_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
