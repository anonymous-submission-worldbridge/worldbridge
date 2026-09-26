#!/usr/bin/env python3
"""Write a view-only PNG preview of an authoritative full-12 EXR color part.

This utility never modifies the EXR.  It is used only for camera-framing
review under render_runtime/diagnostics; final PNG delivery remains the job of
the production z-depth compositor.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, None)
    return np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--part", default="CombinedColor")
    args = parser.parse_args()

    exr = OpenEXR.File(str(args.source))
    parts = {part.name(): part for part in exr.parts}
    if args.part not in parts:
        raise SystemExit(f"missing part {args.part!r}; available={sorted(parts)}")
    channel = parts[args.part].channels.get(args.part)
    if channel is None:
        raise SystemExit(
            f"missing packed channel {args.part!r}; "
            f"available={sorted(parts[args.part].channels)}"
        )
    pixels = np.asarray(channel.pixels, dtype=np.float32)
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise SystemExit(f"unexpected color array shape: {pixels.shape}")
    rgb = np.nan_to_num(pixels[..., :3], nan=0.0, posinf=0.0, neginf=0.0)
    alpha = (
        np.clip(np.nan_to_num(pixels[..., 3], nan=0.0), 0.0, 1.0)
        if pixels.shape[2] == 4
        else np.ones(pixels.shape[:2], dtype=np.float32)
    )

    # Workbench/Eevee EXRs are scene-linear.  A fixed photographic shoulder
    # keeps comparisons stable across views while retaining highlight detail.
    rgb = rgb / (1.0 + np.maximum(rgb, 0.0))
    rgb = srgb_encode(rgb)
    background = np.empty_like(rgb)
    background[..., 0] = 0.76
    background[..., 1] = 0.84
    background[..., 2] = 0.94
    rgb = rgb * alpha[..., None] + background * (1.0 - alpha[..., None])

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(
        np.rint(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8), "RGB"
    ).save(args.destination, compress_level=6)
    print(
        f"PASS source={args.source} part={args.part} "
        f"shape={pixels.shape} destination={args.destination}"
    )


if __name__ == "__main__":
    main()
