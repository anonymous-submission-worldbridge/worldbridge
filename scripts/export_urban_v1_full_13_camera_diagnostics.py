#!/usr/bin/env python3
"""Export isolated camera-gate EXRs to viewable PNGs; never used for delivery."""

from pathlib import Path

import numpy as np
import OpenEXR
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13/renders/camera_diagnostics_r2"
)


def srgb(value: np.ndarray) -> np.ndarray:
    return np.where(
        value <= 0.0031308,
        value * 12.92,
        1.055 * np.power(value, 1.0 / 2.4) - 0.055,
    )


def main() -> None:
    outputs = []
    for path in sorted(SOURCE.glob("*/*.exr")):
        pixels = OpenEXR.File(str(path)).channels()["CombinedColor"].pixels
        rgb = np.maximum(pixels[..., :3].astype(np.float32), 0.0)
        alpha = np.clip(pixels[..., 3:4].astype(np.float32), 0.0, 1.0)
        sky = np.array([0.28, 0.48, 0.68], dtype=np.float32)
        rgb = rgb + sky * (1.0 - alpha)
        # Diagnostic-only display curve. The authoritative delivery conversion
        # remains Blender AgX in the Z compositor.
        rgb = rgb * (2.51 * rgb + 0.03) / (rgb * (2.43 * rgb + 0.59) + 0.14)
        rgb = srgb(np.clip(rgb, 0.0, 1.0))
        output = path.with_suffix(".diagnostic.png")
        Image.fromarray(np.round(rgb * 255.0).astype(np.uint8), "RGB").save(output)
        outputs.append(output)
    print(f"FULL13_CAMERA_DIAGNOSTIC_EXPORT_PASS count={len(outputs)}")


if __name__ == "__main__":
    main()
