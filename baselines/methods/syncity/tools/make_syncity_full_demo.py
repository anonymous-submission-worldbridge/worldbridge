#!/usr/bin/env python3
"""Render clean SynCity 3000 showcase images and videos from frozen PLY scenes.

The source Table-2 runs are read-only inputs.  This script writes only the
presentation package below ``baselines/annotations/syncity3k/full`` (or an
explicit output directory below ``baselines``).  Images are individual clean
renders: no montage, labels, borders, or embedded view numbers are added.
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
import gc
import hashlib
import json
import math
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from baselines.methods.syncity.tools.render_syncity_generation import BASELINES_ROOT
from baselines.methods.syncity.tools.render_syncity_generation import load_splat
from baselines.methods.syncity.tools.render_syncity_generation import look_at_camera
from baselines.methods.syncity.tools.render_syncity_generation import normalize_scene
from baselines.methods.syncity.tools.render_syncity_generation import render_one


DEFAULT_OUTPUT = BASELINES_ROOT / "annotations/syncity3k/full"
STILL_SIZE = (1280, 720)
VIDEO_SIZE = (960, 540)
VIDEO_FPS = 24
VIDEO_FRAMES = 72


TARGET_SCENES: tuple[dict[str, Any], ...] = (
    {
        "key": "target_U-00BABA3B05DA",
        "blind_id": "U-00BABA3B05DA",
        "domain": "urban",
        "spec_id": "urban_commercial_main_side_07",
        "logical_seed": 2,
        "run_dir": BASELINES_ROOT
        / "data/table2/urban/syncity3k/urban_commercial_main_side_07/seed_2",
        "source_video": BASELINES_ROOT
        / "annotations/syncity3k/urban/videos/U-00BABA3B05DA.mp4",
    },
    {
        "key": "target_U-EA4D282345FC",
        "blind_id": "U-EA4D282345FC",
        "domain": "urban",
        "spec_id": "urban_mixed_use_irregular_14",
        "logical_seed": 1,
        "run_dir": BASELINES_ROOT
        / "data/table2/urban/syncity3k/urban_mixed_use_irregular_14/seed_1",
        "source_video": BASELINES_ROOT
        / "annotations/syncity3k/urban/videos/U-EA4D282345FC.mp4",
    },
)


# Three indoor and three outdoor examples.  The choices are intentionally from
# different semantic categories and are independent of the two requested
# alternate-view scenes above.
DEMO_SCENES: tuple[dict[str, Any], ...] = (
    {
        "key": "indoor_kitchen",
        "blind_id": "I-6FEC2C865E6B",
        "domain": "indoor",
        "category": "kitchen",
        "spec_id": "indoor_kitchen_02",
        "logical_seed": 2,
        "run_dir": BASELINES_ROOT
        / "data/table2/indoor/syncity3k/indoor_kitchen_02/seed_2",
    },
    {
        "key": "indoor_living_room",
        "blind_id": "I-E26861C1BDA8",
        "domain": "indoor",
        "category": "living_room",
        "spec_id": "indoor_living_room_04",
        "logical_seed": 1,
        "run_dir": BASELINES_ROOT
        / "data/table2/indoor/syncity3k/indoor_living_room_04/seed_1",
    },
    {
        "key": "indoor_dining_room",
        "blind_id": "I-FC68E3228523",
        "domain": "indoor",
        "category": "dining_room",
        "spec_id": "indoor_dining_room_03",
        "logical_seed": 0,
        "run_dir": BASELINES_ROOT
        / "data/table2/indoor/syncity3k/indoor_dining_room_03/seed_0",
    },
    {
        "key": "urban_park",
        "blind_id": "U-6E17DCF59BB7",
        "domain": "urban",
        "category": "park_edge",
        "spec_id": "urban_park_edge_t_junction_16",
        "logical_seed": 2,
        "run_dir": BASELINES_ROOT
        / "data/table2/urban/syncity3k/urban_park_edge_t_junction_16/seed_2",
    },
    {
        "key": "urban_commercial",
        "blind_id": "U-46D413681E51",
        "domain": "urban",
        "category": "commercial",
        "spec_id": "urban_commercial_offset_08",
        "logical_seed": 2,
        "run_dir": BASELINES_ROOT
        / "data/table2/urban/syncity3k/urban_commercial_offset_08/seed_2",
    },
    {
        "key": "urban_residential",
        "blind_id": "U-B52D496BD1FE",
        "domain": "urban",
        "category": "residential",
        "spec_id": "urban_residential_t_junction_01",
        "logical_seed": 2,
        "run_dir": BASELINES_ROOT
        / "data/table2/urban/syncity3k/urban_residential_t_junction_01/seed_2",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def camera(
    angle_degrees: float,
    radius: float,
    height: float,
    target_height: float = 0.05,
) -> np.ndarray:
    angle = math.radians(angle_degrees)
    position = np.asarray(
        [radius * math.sin(angle), -height, radius * math.cos(angle)],
        dtype=np.float32,
    )
    target = np.asarray([0.0, target_height, 0.0], dtype=np.float32)
    return look_at_camera(position, target)


def target_views() -> dict[str, np.ndarray]:
    # The low cameras sit near the scene edge and look inward.  In SynCity's
    # file coordinates negative Y is up, so smaller absolute height values are
    # deliberately closer to a pedestrian/first-person viewpoint.
    return {
        "third_person_overview": camera(-32.0, 2.45, 1.68, 0.03),
        "first_person_far_left": camera(-58.0, 2.02, 0.46, 0.04),
        "first_person_left": camera(-30.0, 2.02, 0.46, 0.04),
        "first_person_right": camera(30.0, 2.02, 0.46, 0.04),
        "first_person_far_right": camera(58.0, 2.02, 0.46, 0.04),
    }


def demo_views() -> dict[str, np.ndarray]:
    return {
        "overview": camera(-38.0, 2.35, 1.52, 0.04),
        "front_left": camera(-56.0, 2.16, 1.16, 0.04),
        "front_right": camera(56.0, 2.16, 1.16, 0.04),
        "side_detail": camera(18.0, 1.88, 0.70, 0.04),
    }


def video_path() -> list[np.ndarray]:
    transforms: list[np.ndarray] = []
    for index in range(VIDEO_FRAMES):
        fraction = index / (VIDEO_FRAMES - 1)
        smooth = fraction * fraction * (3.0 - 2.0 * fraction)
        angle = -58.0 + 116.0 * smooth
        height = 1.22 + 0.10 * math.sin(math.pi * fraction)
        radius = 2.18 - 0.05 * math.sin(math.pi * fraction)
        transforms.append(camera(angle, radius, height, 0.04))
    return transforms


def load_scene(
    scene: dict[str, Any], device: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    import torch

    run_dir = Path(scene["run_dir"])
    ply_path = run_dir / "scene/scene_color_adjusted.ply"
    if not (run_dir / "SUCCESS").is_file():
        raise FileNotFoundError(f"Source run is not successful: {run_dir}")
    if not ply_path.is_file() or ply_path.stat().st_size == 0:
        raise FileNotFoundError(f"Missing source Gaussian PLY: {ply_path}")
    normalization = normalize_scene(load_splat(ply_path))
    numpy_arrays = normalization.pop("arrays")
    torch.cuda.set_device(device)
    arrays = {
        name: torch.from_numpy(value).to(device=f"cuda:{device}", dtype=torch.float32)
        for name, value in numpy_arrays.items()
    }
    metadata = {
        "source_run_dir": str(run_dir),
        "source_scene": str(ply_path),
        "source_scene_size_bytes": ply_path.stat().st_size,
        "normalization": normalization,
        "gaussian_count": int(len(numpy_arrays["means"])),
    }
    return arrays, metadata


def image_stats(pixels: np.ndarray) -> dict[str, float]:
    unit = pixels.astype(np.float32) / 255.0
    return {"mean": float(unit.mean()), "std": float(unit.std())}


def render_stills(
    arrays: dict[str, Any],
    views: dict[str, np.ndarray],
    output_dir: Path,
    force: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[list[float]]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    cameras: dict[str, list[list[float]]] = {}
    for name, transform in views.items():
        destination = output_dir / f"{name}.png"
        if force or not destination.is_file():
            pixels = render_one(arrays, transform, *STILL_SIZE)
            Image.fromarray(pixels, mode="RGB").save(destination, optimize=True)
        else:
            with Image.open(destination) as handle:
                pixels = np.asarray(handle.convert("RGB"))
        stats = image_stats(pixels)
        if stats["mean"] <= 0.005 or stats["std"] <= 0.01:
            raise RuntimeError(f"Degenerate render {destination}: {stats}")
        files.append(
            {
                "path": str(destination),
                "kind": "image",
                "width": STILL_SIZE[0],
                "height": STILL_SIZE[1],
                "sha256": sha256_file(destination),
                **stats,
            }
        )
        cameras[name] = transform.tolist()
        print(f"SYNCITY3K_FULL_IMAGE path={destination}", flush=True)
    return files, cameras


def render_video(
    arrays: dict[str, Any],
    transforms: list[np.ndarray],
    destination: Path,
    force: bool,
) -> dict[str, Any]:
    if destination.is_file() and not force:
        return {
            "path": str(destination),
            "kind": "video",
            "width": VIDEO_SIZE[0],
            "height": VIDEO_SIZE[1],
            "frames": VIDEO_FRAMES,
            "fps": VIDEO_FPS,
            "sha256": sha256_file(destination),
        }
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required to encode demo videos")
    temporary = destination.with_suffix(".tmp.mp4")
    temporary.unlink(missing_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{VIDEO_SIZE[0]}x{VIDEO_SIZE[1]}",
        "-r",
        str(VIDEO_FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index, transform in enumerate(transforms):
            pixels = render_one(arrays, transform, *VIDEO_SIZE)
            process.stdin.write(pixels.tobytes())
            if index % 12 == 0 or index + 1 == len(transforms):
                print(
                    f"SYNCITY3K_FULL_VIDEO_FRAME path={destination} "
                    f"frame={index + 1}/{len(transforms)}",
                    flush=True,
                )
        process.stdin.close()
        return_code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    if return_code != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}: {destination}")
    temporary.replace(destination)
    return {
        "path": str(destination),
        "kind": "video",
        "width": VIDEO_SIZE[0],
        "height": VIDEO_SIZE[1],
        "frames": VIDEO_FRAMES,
        "fps": VIDEO_FPS,
        "duration_seconds": VIDEO_FRAMES / VIDEO_FPS,
        "sha256": sha256_file(destination),
    }


def relative_files(rows: list[dict[str, Any]], output: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        copied["path"] = str(Path(copied["path"]).resolve().relative_to(output))
        normalized.append(copied)
    return normalized


def render_target(
    scene: dict[str, Any], output: Path, device: int, force: bool
) -> dict[str, Any]:
    import torch

    started = time.monotonic()
    arrays, source = load_scene(scene, device)
    try:
        destination = output / "alternate_views" / scene["blind_id"]
        files, cameras = render_stills(arrays, target_views(), destination, force)
        payload = {
            "purpose": "requested alternate viewpoints",
            "method": "syncity3k",
            "blind_id": scene["blind_id"],
            "domain": scene["domain"],
            "spec_id": scene["spec_id"],
            "logical_seed": scene["logical_seed"],
            "source_video": str(scene["source_video"]),
            **source,
            "render_resolution": list(STILL_SIZE),
            "coordinate_system": "OpenCV x-right, y-down, z-forward; source PLY negative-y-up",
            "camera_to_world": cameras,
            "files": relative_files(files, output),
            "wall_time_seconds": round(time.monotonic() - started, 3),
        }
        atomic_json(destination / "scene.json", payload)
        return payload
    finally:
        del arrays
        gc.collect()
        torch.cuda.empty_cache()


def render_demo(
    scene: dict[str, Any], output: Path, device: int, force: bool
) -> dict[str, Any]:
    import torch

    started = time.monotonic()
    arrays, source = load_scene(scene, device)
    try:
        destination = output / "demos" / scene["key"]
        files, cameras = render_stills(arrays, demo_views(), destination, force)
        trajectory = video_path()
        files.append(render_video(arrays, trajectory, destination / "video.mp4", force))
        payload = {
            "purpose": "indoor-outdoor showcase demo",
            "method": "syncity3k",
            "blind_id": scene["blind_id"],
            "domain": scene["domain"],
            "category": scene["category"],
            "spec_id": scene["spec_id"],
            "logical_seed": scene["logical_seed"],
            **source,
            "image_resolution": list(STILL_SIZE),
            "video_resolution": list(VIDEO_SIZE),
            "video_fps": VIDEO_FPS,
            "video_frames": VIDEO_FRAMES,
            "coordinate_system": "OpenCV x-right, y-down, z-forward; source PLY negative-y-up",
            "still_camera_to_world": cameras,
            "video_camera_to_world": [transform.tolist() for transform in trajectory],
            "files": relative_files(files, output),
            "wall_time_seconds": round(time.monotonic() - started, 3),
        }
        atomic_json(destination / "scene.json", payload)
        return payload
    finally:
        del arrays
        gc.collect()
        torch.cuda.empty_cache()


def write_readme(output: Path) -> None:
    text = """# SynCity 3000 full visualization package

`alternate_views/` contains the requested new viewpoints for the two specified
urban scenes.  Each target has one third-person overview and four low side
views.

`demos/` contains six distinct examples: three indoor categories and three
urban categories.  Every scene has four independent PNG images and one MP4
camera-arc video.  The images are direct renders without montage composition,
labels, borders, or embedded numbering.

`MANIFEST.json` records source runs, camera transforms, render settings, output
hashes, and validation metadata.  The frozen source runs were not modified.
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Render only a named task key; may be supplied more than once.",
    )
    args = parser.parse_args()
    output = below_baselines(args.output)
    output.mkdir(parents=True, exist_ok=True)
    selected = set(args.only)
    known = {row["key"] for row in TARGET_SCENES + DEMO_SCENES}
    unknown = selected - known
    if unknown:
        raise ValueError(f"Unknown --only task(s): {sorted(unknown)}")

    started_at = utc_now()
    targets: list[dict[str, Any]] = []
    demos: list[dict[str, Any]] = []
    for scene in TARGET_SCENES:
        if selected and scene["key"] not in selected:
            continue
        print(f"SYNCITY3K_FULL_START task={scene['key']}", flush=True)
        targets.append(render_target(scene, output, args.device, args.force))
    for scene in DEMO_SCENES:
        if selected and scene["key"] not in selected:
            continue
        print(f"SYNCITY3K_FULL_START task={scene['key']}", flush=True)
        demos.append(render_demo(scene, output, args.device, args.force))

    write_readme(output)
    manifest = {
        "schema_version": 1,
        "method": "syncity3k",
        "created_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "source_policy": "frozen successful Table-2 PLY scenes; source runs unmodified",
        "image_policy": "individual clean renders; no montage, labels, borders, or embedded numbering",
        "renderer": "gsplat",
        "device": args.device,
        "target_scene_count": len(targets),
        "demo_scene_count": len(demos),
        "alternate_views": targets,
        "demos": demos,
    }
    atomic_json(output / "MANIFEST.json", manifest)
    print(
        f"SYNCITY3K_FULL_COMPLETE output={output} "
        f"targets={len(targets)} demos={len(demos)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
