#!/usr/bin/env python3
"""Export clean, tone-balanced SpatialGen indoor showcase frames.

The anonymous review montages contain burned-in labels and only 480x270 pixels
per view. Their retained 50-frame videos contain the same frozen camera path
without labels. This script extracts the exact eight anchor indices, crops the
square video frames to the montage's 16:9 field of view, applies one fixed RGB
tone curve per scene, and writes no persistent intermediate files.
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
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
SPATIALGEN_ROOT = BASELINES / "annotations/spatialgen"
INDOOR_ROOT = SPATIALGEN_ROOT / "indoor"
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
SOURCE_SIZE = (512, 512)
OUTPUT_SIZE = (512, 288)


@dataclass(frozen=True)
class Scene:
    blind_id: str
    tone_profile: str

    @property
    def video(self) -> Path:
        return INDOOR_ROOT / "videos" / f"{self.blind_id}.mp4"

    @property
    def montage(self) -> Path:
        return INDOOR_ROOT / "montages" / f"{self.blind_id}.jpg"


SCENES = (
    Scene("I-01E2A3A3CCA3", "mild-highlight-compression"),
    Scene("I-3DF1D13C0AD1", "mild-highlight-compression"),
    Scene("I-6CE28357AC79", "mild-highlight-compression"),
    Scene("I-7F23FC552EAB", "mild-highlight-compression"),
    Scene("I-8A8288ECD5C9", "mild-highlight-compression"),
    Scene("I-BB98E6039E21", "mild-highlight-compression"),
    Scene("I-B6C2A433788C", "mild-highlight-compression"),
)


TONE_CURVES = {
    "identity": ((0.0, 1.0), (0.0, 1.0)),
    "mild-highlight-compression": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.055, 0.16, 0.30, 0.47, 0.64, 0.78, 0.92),
    ),
    "moderate-highlight-compression": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.055, 0.16, 0.29, 0.45, 0.61, 0.74, 0.88),
    ),
    "shadow-lift-highlight-compression": (
        (0.00, 0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 1.00),
        (0.00, 0.075, 0.21, 0.37, 0.54, 0.69, 0.80, 0.92),
    ),
}


def assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must remain under baselines/: {resolved}") from exc
    return resolved


def make_lut(profile: str) -> list[int]:
    x, y = TONE_CURVES[profile]
    values = np.interp(np.arange(256, dtype=np.float32) / 255.0, x, y)
    return np.rint(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8).tolist()


def luminance_stats(image: Image.Image) -> dict[str, float]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    p01, p10, p50, p90, p99 = np.percentile(luminance, (1, 10, 50, 90, 99))
    return {
        "p01": float(p01),
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
        "p99": float(p99),
        "shadow_clip_pct": float((luminance < 0.02).mean() * 100.0),
        "highlight_clip_pct": float((luminance > 0.98).mean() * 100.0),
    }


def extract_anchor_frames(video: Path, temporary: Path) -> list[Path]:
    select = "+".join(f"eq(n\\,{index})" for index in ANCHOR_INDICES)
    # Both the square sequence and 16:9 anchors use a 70-degree horizontal FoV.
    # This centered crop therefore recovers the montage tile's view volume.
    crop_top = (SOURCE_SIZE[1] - OUTPUT_SIZE[1]) // 2
    vf = f"select='{select}',crop={OUTPUT_SIZE[0]}:{OUTPUT_SIZE[1]}:0:{crop_top}"
    pattern = temporary / "frame_%02d.png"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        vf,
        "-fps_mode",
        "vfr",
        "-frames:v",
        str(len(ANCHOR_INDICES)),
        str(pattern),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {video}: {completed.stderr[-2000:]}")
    frames = sorted(temporary.glob("frame_*.png"))
    if len(frames) != len(ANCHOR_INDICES):
        raise RuntimeError(
            f"Expected eight extracted frames from {video}, got {len(frames)}"
        )
    return frames


def montage_mae(scene: Scene, view_index: int, raw: Image.Image) -> float:
    with Image.open(scene.montage) as handle:
        montage = np.asarray(handle.convert("RGB"), dtype=np.float32)
    col, row = view_index % 4, view_index // 4
    tile = montage[
        44 + row * 270 : 44 + (row + 1) * 270,
        col * 480 : (col + 1) * 480,
    ]
    resized = np.asarray(
        raw.resize((480, 270), Image.Resampling.LANCZOS), dtype=np.float32
    )
    mask = np.ones((270, 480), dtype=bool)
    # Ignore the burned-in label plus a margin for JPEG ringing.
    mask[:45, :56] = False
    return float(np.abs(tile - resized)[mask].mean())


def export_scene(
    scene: Scene,
    output_dir: Path,
    overwrite: bool,
    selected_views: set[int],
    no_tone: bool,
    work_root: Path,
) -> list[dict[str, Any]]:
    if not scene.video.is_file() or not scene.montage.is_file():
        raise FileNotFoundError(f"Missing retained media for {scene.blind_id}")
    profile = "identity" if no_tone else scene.tone_profile
    lut = make_lut(profile)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix=f"{scene.blind_id}-", dir=work_root
    ) as temp:
        frames = extract_anchor_frames(scene.video, Path(temp))
        for view_index, (sequence_index, frame) in enumerate(
            zip(ANCHOR_INDICES, frames)
        ):
            if view_index not in selected_views:
                continue
            destination = output_dir / f"{scene.blind_id}_view_{view_index + 1:02d}.png"
            if destination.exists() and not overwrite:
                raise FileExistsError(
                    f"Refusing to overwrite {destination}; pass --overwrite"
                )
            with Image.open(frame) as handle:
                raw = handle.convert("RGB")
            if raw.size != OUTPUT_SIZE:
                raise RuntimeError(f"Unexpected extracted size {raw.size}: {frame}")
            corrected = raw.point(lut * 3)
            destination.parent.mkdir(parents=True, exist_ok=True)
            corrected.save(destination, format="PNG", optimize=True, compress_level=9)
            before = luminance_stats(raw)
            after = luminance_stats(corrected)
            row: dict[str, Any] = {
                "blind_id": scene.blind_id,
                "view_index_one_based": view_index + 1,
                "sequence_index_zero_based": sequence_index,
                "source_video": str(scene.video.relative_to(REPO_ROOT)),
                "source_montage": str(scene.montage.relative_to(REPO_ROOT)),
                "output": str(destination.relative_to(REPO_ROOT)),
                "output_width": OUTPUT_SIZE[0],
                "output_height": OUTPUT_SIZE[1],
                "tone_profile": profile,
                "montage_mae_excluding_label": round(
                    montage_mae(scene, view_index, raw), 6
                ),
            }
            for prefix, stats in (("before", before), ("after", after)):
                for key, value in stats.items():
                    row[f"{prefix}_{key}"] = round(value, 6)
            rows.append(row)
    return rows


def write_manifest(
    path: Path, rows: list[dict[str, Any]], append: bool = False
) -> None:
    if not rows:
        raise RuntimeError("No images were exported")
    if append and path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
        existing_outputs = {row["output"] for row in existing}
        duplicate_outputs = existing_outputs.intersection(row["output"] for row in rows)
        if duplicate_outputs:
            duplicates = ", ".join(sorted(duplicate_outputs))
            raise ValueError(f"Manifest already contains outputs: {duplicates}")
        rows = existing + rows
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SPATIALGEN_ROOT / "images")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SPATIALGEN_ROOT / "images/images_manifest.csv",
    )
    parser.add_argument(
        "--scene",
        action="append",
        choices=[scene.blind_id for scene in SCENES],
        help="Export only this scene; may be repeated",
    )
    parser.add_argument(
        "--view",
        action="append",
        type=int,
        choices=range(1, 9),
        help="Export only this one-based view; may be repeated",
    )
    parser.add_argument("--no-tone", action="store_true")
    parser.add_argument("--no-manifest", action="store_true")
    parser.add_argument(
        "--append-manifest",
        action="store_true",
        help="Preserve existing manifest rows and add only the new outputs",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = assert_baselines_path(args.output_dir)
    manifest = assert_baselines_path(args.manifest)
    work_root = assert_baselines_path(BASELINES / "work/spatialgen")
    work_root.mkdir(parents=True, exist_ok=True)
    if args.append_manifest and args.no_manifest:
        raise ValueError("--append-manifest and --no-manifest are mutually exclusive")
    if args.append_manifest and args.overwrite:
        raise ValueError("--append-manifest and --overwrite are mutually exclusive")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("The existing local ffmpeg executable is required")
    chosen_scene_ids = set(args.scene or [scene.blind_id for scene in SCENES])
    selected_views = {view - 1 for view in (args.view or range(1, 9))}
    chosen_scenes = [scene for scene in SCENES if scene.blind_id in chosen_scene_ids]
    if (
        manifest.exists()
        and not args.overwrite
        and not args.no_manifest
        and not args.append_manifest
    ):
        raise FileExistsError(f"Refusing to overwrite {manifest}; pass --overwrite")
    rows = []
    for scene in chosen_scenes:
        rows.extend(
            export_scene(
                scene,
                output_dir,
                args.overwrite,
                selected_views,
                args.no_tone,
                work_root,
            )
        )
    if not args.no_manifest:
        write_manifest(manifest, rows, append=args.append_manifest)
    print(f"Wrote {len(rows)} standalone images to {output_dir}")
    if not args.no_manifest:
        print(f"Wrote extraction/tone provenance to {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
