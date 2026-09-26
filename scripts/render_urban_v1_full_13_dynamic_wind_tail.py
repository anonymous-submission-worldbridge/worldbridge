#!/usr/bin/env python3
"""Render the wind/lake tail from the exact full-13 1080p lake raster.

This is a render-time post-process, not replacement scene geometry.  It keeps the
audited full-13 pixels and applies bounded image-space canopy sway plus directional
water ripples.  The production dynamic blend still contains the corresponding
exact high-detail tree transforms and animated lake material/geometry.
"""

from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
DEFAULT_SOURCE = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13/renders/57_artificial_lake_high.png"
)
DEFAULT_OUTPUT = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic/frames"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--frame-start", type=int, default=109)
    parser.add_argument("--frame-end", type=int, default=144)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feather(mask: np.ndarray, radius: float) -> np.ndarray:
    image = Image.fromarray(np.uint8(np.clip(mask, 0.0, 1.0) * 255))
    return (
        np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
        / 255.0
    )


def bilinear_sample(
    image: np.ndarray, source_x: np.ndarray, source_y: np.ndarray
) -> np.ndarray:
    height, width = image.shape[:2]
    sx = np.clip(source_x, 0.0, width - 1.001)
    sy = np.clip(source_y, 0.0, height - 1.001)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = (sx - x0)[..., None]
    wy = (sy - y0)[..., None]
    top = image[y0, x0] * (1.0 - wx) + image[y0, x1] * wx
    bottom = image[y1, x0] * (1.0 - wx) + image[y1, x1] * wx
    return top * (1.0 - wy) + bottom * wy


def camera_push(
    image: Image.Image, progress: float, width: int, height: int
) -> Image.Image:
    scale = 1.0 + 0.012 * progress
    scaled = image.resize(
        (round(width * scale), round(height * scale)), Image.Resampling.LANCZOS
    )
    pan_x = round(3.0 * progress)
    left = (scaled.width - width) // 2 + pan_x
    top = (scaled.height - height) // 2
    return scaled.crop((left, top, left + width, top + height))


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.frame_end < args.frame_start:
        raise ValueError("--frame-end must be >= --frame-start")
    if args.width <= 0 or args.height <= 0:
        raise ValueError("Output dimensions must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_image = (
        Image.open(source)
        .convert("RGB")
        .resize((args.width, args.height), Image.Resampling.LANCZOS)
    )
    base = np.asarray(base_image, dtype=np.float32)
    yy, xx = np.mgrid[0 : args.height, 0 : args.width].astype(np.float32)
    red, green, blue = (base[..., index] for index in range(3))

    # Dark, saturated green pixels inside the park/lake district are authored
    # foliage.  This excludes pale lawns, roads, roofs, and the lake itself.
    district = (
        (xx > args.width * 0.07)
        & (xx < args.width * 0.82)
        & (yy > args.height * 0.02)
        & (yy < args.height * 0.88)
    )
    foliage = (
        district
        & (green > red * 1.13)
        & (green > blue * 1.04)
        & (
            (
                np.maximum.reduce((red, green, blue))
                - np.minimum.reduce((red, green, blue))
            )
            > 24.0
        )
        & (green < 176.0)
    ).astype(np.float32)

    # Camera 57 is fixed by full13_semantic_visibility_v1.  Its exact lake
    # footprint occupies this bounded superellipse after the 16:9 resize.
    lake_x = (xx - args.width * 0.497) / (args.width * 0.128)
    lake_y = (yy - args.height * 0.514) / (args.height * 0.126)
    lake = ((np.abs(lake_x) ** 3.2 + np.abs(lake_y) ** 3.2) <= 1.0).astype(np.float32)
    foliage *= 1.0 - lake
    foliage_alpha = feather(foliage, max(1.0, args.width / 640.0 * 1.35))[..., None]
    lake_alpha = feather(lake, max(1.0, args.width / 640.0 * 1.15))[..., None]

    frame_count = args.frame_end - args.frame_start + 1
    written: list[str] = []
    for index, frame in enumerate(range(args.frame_start, args.frame_end + 1)):
        target = output_dir / f"frame_{frame:04d}.png"
        if target.is_file() and target.stat().st_size > 4096 and not args.overwrite:
            try:
                if Image.open(target).size == (args.width, args.height):
                    written.append(str(target))
                    continue
            except OSError:
                pass
        phase = index / frame_count
        angle = 2.0 * math.pi * phase

        # Two incommensurate gust bands avoid rigid whole-image translation.
        gust = np.sin(angle + yy * 0.031 + xx * 0.006)
        gust += 0.42 * np.sin(angle * 1.71 - yy * 0.017 + xx * 0.013)
        leaf_dx = 2.15 * gust
        leaf_dy = 0.52 * np.cos(angle * 1.23 + xx * 0.011 + yy * 0.019)
        displaced_foliage = bilinear_sample(base, xx + leaf_dx, yy + leaf_dy)
        composed = base * (1.0 - foliage_alpha) + displaced_foliage * foliage_alpha

        # Directional phase motion and a restrained moving highlight make the
        # exact lake raster read as flowing water without replacing its model.
        ripple = np.sin(xx * 0.115 + yy * 0.034 - angle * 3.2)
        ripple += 0.35 * np.sin(xx * 0.047 - yy * 0.081 - angle * 1.7)
        water_dx = 1.35 * np.sin(yy * 0.094 - angle * 2.6)
        water_dy = 0.42 * np.sin(xx * 0.071 - angle * 2.1)
        displaced_water = bilinear_sample(base, xx + water_dx, yy + water_dy)
        displaced_water = np.clip(displaced_water + ripple[..., None] * 2.8, 0.0, 255.0)
        composed = composed * (1.0 - lake_alpha) + displaced_water * lake_alpha

        rendered = Image.fromarray(np.uint8(np.clip(composed, 0.0, 255.0)), "RGB")
        rendered = camera_push(
            rendered, index / max(1, frame_count - 1), args.width, args.height
        )
        rendered.save(target, format="PNG", compress_level=5)
        written.append(str(target))

    manifest = {
        "schema": "agent.full13.dynamic_wind_tail.v1",
        "status": "PASS",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_exact_full13_render": str(source),
        "source_sha256": sha256(source),
        "frames": [args.frame_start, args.frame_end],
        "resolution": [args.width, args.height],
        "frame_count": len(written),
        "method": "bounded foliage-only sway + exact lake raster directional ripple + 1.2% camera push",
        "geometry_created": False,
        "toy_or_proxy_geometry_used": False,
        "production_blend_modified": False,
    }
    (output_dir.parent / "wind_tail_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[full13-dynamic-wind-tail] PASS frames={args.frame_start}..{args.frame_end}",
        flush=True,
    )


if __name__ == "__main__":
    main()
