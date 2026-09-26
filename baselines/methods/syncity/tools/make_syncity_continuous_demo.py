#!/usr/bin/env python3
"""Build six continuous shared-coordinate SynCity 3000 visualization demos.

SynCity 3000 emits scale-free indoor and urban Gaussian scenes separately.
This renderer turns each selected pair into one reproducible 3D presentation
scene: it ground-aligns both clouds, opens the indoor boundary, clears the
matching exterior approach, and inserts a real 3D threshold, walkway, jambs,
and lintel.  Every still and every video frame is rasterized from the combined
Gaussian set in one pass.  There is no image-space portal compositing.

Each demo contains ten clean, individually saved near/far PNG views and two
MP4 walkthroughs whose cameras physically cross the same threshold in opposite
directions.  Source runs remain read-only and all outputs stay below baselines.
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


DEFAULT_OUTPUT = BASELINES_ROOT / "annotations/syncity3k/connect"
STILL_SIZE = (1280, 720)
VIDEO_SIZE = (960, 540)
VIDEO_FPS = 24
VIDEO_FRAMES = 96
MAX_SOURCE_STILL_SPLATS = 3_000_000
MAX_SOURCE_VIDEO_SPLATS = 1_150_000

# Shared-coordinate layout in method-normalized units.  Negative Y is up.
INDOOR_SCALE = 2.0
OUTDOOR_SCALE = 2.8
EXTERIOR_START_Z = 0.58
DOOR_HALF_WIDTH = 0.54
DOOR_HEIGHT = 0.70
INDOOR_CORRIDOR_START_Z = -2.85
WALKWAY_END_Z = 3.10
CAMERA_EYE_Y = -0.30


def run_dir(domain: str, spec_id: str, seed: int) -> Path:
    return BASELINES_ROOT / f"data/table2/{domain}/syncity3k/{spec_id}/seed_{seed}"


SCENES: tuple[dict[str, Any], ...] = (
    {
        "scene_id": "kitchen_commercial",
        "indoor": {
            "blind_id": "I-6FEC2C865E6B",
            "spec_id": "indoor_kitchen_02",
            "seed": 2,
            "run_dir": run_dir("indoor", "indoor_kitchen_02", 2),
        },
        "outdoor": {
            "blind_id": "U-46D413681E51",
            "spec_id": "urban_commercial_offset_08",
            "seed": 2,
            "run_dir": run_dir("urban", "urban_commercial_offset_08", 2),
        },
        "connector_color": (0.45, 0.31, 0.20),
    },
    {
        "scene_id": "living_residential",
        "indoor": {
            "blind_id": "I-E26861C1BDA8",
            "spec_id": "indoor_living_room_04",
            "seed": 1,
            "run_dir": run_dir("indoor", "indoor_living_room_04", 1),
        },
        "outdoor": {
            "blind_id": "U-B52D496BD1FE",
            "spec_id": "urban_residential_t_junction_01",
            "seed": 2,
            "run_dir": run_dir("urban", "urban_residential_t_junction_01", 2),
        },
        "connector_color": (0.36, 0.24, 0.16),
    },
    {
        "scene_id": "dining_park",
        "indoor": {
            "blind_id": "I-FC68E3228523",
            "spec_id": "indoor_dining_room_03",
            "seed": 0,
            "run_dir": run_dir("indoor", "indoor_dining_room_03", 0),
        },
        "outdoor": {
            "blind_id": "U-E18A2A9FD286",
            "spec_id": "urban_park_edge_irregular_19",
            "seed": 1,
            "run_dir": run_dir("urban", "urban_park_edge_irregular_19", 1),
        },
        "connector_color": (0.40, 0.29, 0.18),
    },
    {
        "scene_id": "bedroom_mixed_use",
        "indoor": {
            "blind_id": "I-E2649CFAB731",
            "spec_id": "indoor_bedroom_04",
            "seed": 2,
            "run_dir": run_dir("indoor", "indoor_bedroom_04", 2),
        },
        "outdoor": {
            "blind_id": "U-EA4D282345FC",
            "spec_id": "urban_mixed_use_irregular_14",
            "seed": 1,
            "run_dir": run_dir("urban", "urban_mixed_use_irregular_14", 1),
        },
        "connector_color": (0.31, 0.23, 0.18),
    },
    {
        "scene_id": "bathroom_civic",
        "indoor": {
            "blind_id": "I-C65DC87E2681",
            "spec_id": "indoor_bathroom_03",
            "seed": 2,
            "run_dir": run_dir("indoor", "indoor_bathroom_03", 2),
        },
        "outdoor": {
            "blind_id": "U-EEEC98F75823",
            "spec_id": "urban_leisure_civic_t_junction_21",
            "seed": 2,
            "run_dir": run_dir("urban", "urban_leisure_civic_t_junction_21", 2),
        },
        "connector_color": (0.46, 0.43, 0.38),
    },
    {
        "scene_id": "lounge_cultural",
        "indoor": {
            "blind_id": "I-C4C1D0DBAB7A",
            "spec_id": "indoor_living_room_01",
            "seed": 0,
            "run_dir": run_dir("indoor", "indoor_living_room_01", 0),
        },
        "outdoor": {
            "blind_id": "U-B7EA5C7A218A",
            "spec_id": "urban_leisure_civic_irregular_24",
            "seed": 2,
            "run_dir": run_dir("urban", "urban_leisure_civic_irregular_24", 2),
        },
        "connector_color": (0.38, 0.28, 0.20),
    },
)


STILL_VIEW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "role": "indoor_near",
        "position": (0.0, -0.34, -1.05),
        "target": (1.35, -0.22, -2.00),
        "region": "indoor",
        "distance": "near",
    },
    {
        "role": "indoor_far",
        "position": (-2.85, -1.45, -4.65),
        "target": (-0.10, -0.22, -1.15),
        "region": "indoor",
        "distance": "far",
    },
    {
        "role": "threshold_from_inside_near",
        "position": (-0.04, CAMERA_EYE_Y, -0.68),
        "target": (0.02, -0.24, 0.95),
        "region": "connection",
        "distance": "near",
    },
    {
        "role": "threshold_from_inside_far",
        "position": (0.28, -0.45, -2.65),
        "target": (0.0, -0.24, 0.35),
        "region": "connection",
        "distance": "far",
    },
    {
        "role": "threshold_from_outside_near",
        "position": (0.05, CAMERA_EYE_Y, 0.98),
        "target": (-0.04, -0.24, -0.95),
        "region": "connection",
        "distance": "near",
    },
    {
        "role": "threshold_from_outside_far",
        "position": (-0.38, -0.48, 2.95),
        "target": (0.0, -0.23, -0.30),
        "region": "connection",
        "distance": "far",
    },
    {
        "role": "outdoor_near",
        "position": (0.32, -0.34, 1.48),
        "target": (0.16, -0.22, 3.45),
        "region": "outdoor",
        "distance": "near",
    },
    {
        "role": "outdoor_far",
        "position": (3.80, -1.85, 7.10),
        "target": (0.20, -0.24, 3.05),
        "region": "outdoor",
        "distance": "far",
    },
    {
        "role": "shared_oblique",
        "position": (5.25, -2.55, -2.80),
        "target": (0.0, -0.22, 0.85),
        "region": "whole_scene",
        "distance": "far",
    },
    {
        "role": "shared_overview",
        "position": (-5.65, -3.40, 7.65),
        "target": (0.0, -0.16, 0.75),
        "region": "whole_scene",
        "distance": "far",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def relative_to_output(path: Path, output: Path) -> str:
    return str(path.resolve().relative_to(output.resolve()))


def relative_to_repo(path: Path) -> str:
    return str(path.resolve().relative_to(BASELINES_ROOT.parent.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def deterministic_indices(count: int, limit: int, seed: int) -> np.ndarray | None:
    if count <= limit:
        return None
    rng = np.random.default_rng(seed)
    indices = rng.choice(count, size=limit, replace=False)
    indices.sort()
    return indices


def transform_source_numpy(
    source: dict[str, Any], side: str, sample_seed: int
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    source_run = Path(source["run_dir"])
    ply_path = source_run / "scene/scene_color_adjusted.ply"
    if not (source_run / "SUCCESS").is_file():
        raise FileNotFoundError(f"Source run is not successful: {source_run}")
    if not ply_path.is_file() or ply_path.stat().st_size == 0:
        raise FileNotFoundError(f"Missing source Gaussian scene: {ply_path}")

    normalized = normalize_scene(load_splat(ply_path))
    arrays = normalized.pop("arrays")
    original_count = int(len(arrays["means"]))
    visible = arrays["opacities"] >= 0.05
    visible_means = arrays["means"][visible] if visible.any() else arrays["means"]
    floor_y = float(np.quantile(visible_means[:, 1], 0.99))

    means = arrays["means"].copy()
    if side == "indoor":
        boundary_z = float(np.quantile(visible_means[:, 2], 0.99))
        means[:, 0] *= INDOOR_SCALE
        means[:, 1] = (means[:, 1] - floor_y) * INDOOR_SCALE
        means[:, 2] = (means[:, 2] - boundary_z) * INDOOR_SCALE
        scale_factor = INDOOR_SCALE
        # Remove a person-width aisle through the room as well as the front
        # boundary itself.  Ground splats are preserved, so the camera has a
        # continuous floor rather than an image-space hole.
        cut = (
            (np.abs(means[:, 0]) < DOOR_HALF_WIDTH + 0.10)
            & (means[:, 2] > INDOOR_CORRIDOR_START_Z)
            & (means[:, 2] < 0.14)
            & (means[:, 1] < -0.045)
        )
        keep = ~cut
        anchor_name = "positive_z_99_percentile_to_threshold"
    elif side == "outdoor":
        boundary_z = float(np.quantile(visible_means[:, 2], 0.01))
        means[:, 0] *= OUTDOOR_SCALE
        means[:, 1] = (means[:, 1] - floor_y) * OUTDOOR_SCALE
        means[:, 2] = (means[:, 2] - boundary_z) * OUTDOOR_SCALE + EXTERIOR_START_Z
        scale_factor = OUTDOOR_SCALE
        clearance = (
            (np.abs(means[:, 0]) < DOOR_HALF_WIDTH + 0.10)
            & (means[:, 2] > EXTERIOR_START_Z - 0.12)
            & (means[:, 2] < WALKWAY_END_Z)
            & (means[:, 1] < -0.045)
        )
        keep = ~clearance
        anchor_name = "negative_z_01_percentile_to_exterior_approach"
    else:
        raise ValueError(side)

    source_indices = np.flatnonzero(keep)
    kept_after_opening = int(len(source_indices))
    selected = deterministic_indices(
        kept_after_opening, MAX_SOURCE_STILL_SPLATS, sample_seed
    )
    if selected is not None:
        source_indices = source_indices[selected]

    transformed: dict[str, np.ndarray] = {}
    for name, values in arrays.items():
        if name == "means":
            transformed[name] = means[source_indices]
        elif name == "scales":
            transformed[name] = values[source_indices] * scale_factor
        else:
            transformed[name] = values[source_indices]
    retained_count = int(len(source_indices))
    del arrays, means, visible_means, visible, source_indices
    gc.collect()
    return transformed, {
        "blind_id": source["blind_id"],
        "spec_id": source["spec_id"],
        "logical_seed": source["seed"],
        "source_run": relative_to_repo(source_run),
        "source_scene": relative_to_repo(ply_path),
        "source_scene_bytes": ply_path.stat().st_size,
        "source_gaussian_count": original_count,
        "gaussian_count_after_opening": kept_after_opening,
        "retained_still_gaussian_count": retained_count,
        "normalization": normalized,
        "shared_transform": {
            "uniform_scale": scale_factor,
            "ground_alignment_source_y_99_percentile": floor_y,
            "z_anchor_source": boundary_z,
            "z_anchor_rule": anchor_name,
        },
    }


def box_splats(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    spacing: float,
    color: tuple[float, float, float],
) -> dict[str, np.ndarray]:
    center_array = np.asarray(center, dtype=np.float32)
    size_array = np.asarray(size, dtype=np.float32)
    faces: list[np.ndarray] = []
    for fixed_axis in range(3):
        free_axes = [axis for axis in range(3) if axis != fixed_axis]
        first = np.linspace(
            -size_array[free_axes[0]] / 2.0,
            size_array[free_axes[0]] / 2.0,
            max(2, int(math.ceil(size_array[free_axes[0]] / spacing)) + 1),
            dtype=np.float32,
        )
        second = np.linspace(
            -size_array[free_axes[1]] / 2.0,
            size_array[free_axes[1]] / 2.0,
            max(2, int(math.ceil(size_array[free_axes[1]] / spacing)) + 1),
            dtype=np.float32,
        )
        grid_first, grid_second = np.meshgrid(first, second, indexing="ij")
        for sign in (-1.0, 1.0):
            points = np.zeros((grid_first.size, 3), dtype=np.float32)
            points[:, fixed_axis] = sign * size_array[fixed_axis] / 2.0
            points[:, free_axes[0]] = grid_first.ravel()
            points[:, free_axes[1]] = grid_second.ravel()
            faces.append(points + center_array[None])
    means = np.concatenate(faces, axis=0)
    count = int(len(means))
    return {
        "means": means,
        "colors": np.tile(np.asarray(color, dtype=np.float32), (count, 1)),
        "scales": np.full((count, 3), spacing * 0.72, dtype=np.float32),
        "quats": np.tile(
            np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float32), (count, 1)
        ),
        "opacities": np.full((count,), 0.96, dtype=np.float32),
    }


def concatenate_numpy(parts: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    return {
        name: np.concatenate([part[name] for part in parts], axis=0)
        for name in ("means", "colors", "scales", "quats", "opacities")
    }


def connector_numpy(frame_color: tuple[float, float, float]) -> dict[str, np.ndarray]:
    stone = (0.34, 0.35, 0.34)
    frame_color = tuple(0.58 * channel for channel in frame_color)
    walkway_start_z = -0.46
    walkway_size_z = WALKWAY_END_Z - walkway_start_z
    walkway_center_z = (WALKWAY_END_Z + walkway_start_z) / 2.0
    parts = [
        box_splats(
            (0.0, 0.012, walkway_center_z),
            (2.0 * DOOR_HALF_WIDTH + 0.12, 0.055, walkway_size_z),
            0.025,
            stone,
        ),
        box_splats(
            (-DOOR_HALF_WIDTH - 0.065, -DOOR_HEIGHT / 2.0, -0.045),
            (0.13, DOOR_HEIGHT, 0.20),
            0.022,
            frame_color,
        ),
        box_splats(
            (DOOR_HALF_WIDTH + 0.065, -DOOR_HEIGHT / 2.0, -0.045),
            (0.13, DOOR_HEIGHT, 0.20),
            0.022,
            frame_color,
        ),
        box_splats(
            (0.0, -DOOR_HEIGHT - 0.065, -0.045),
            (2.0 * DOOR_HALF_WIDTH + 0.26, 0.13, 0.20),
            0.022,
            frame_color,
        ),
    ]
    return concatenate_numpy(parts)


def to_device(arrays: dict[str, np.ndarray], device: int) -> dict[str, Any]:
    import torch

    torch.cuda.set_device(device)
    result = {
        name: torch.from_numpy(np.ascontiguousarray(values)).to(
            device=f"cuda:{device}", dtype=torch.float32, non_blocking=True
        )
        for name, values in arrays.items()
    }
    del arrays
    gc.collect()
    return result


def concatenate_torch(parts: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    return {
        name: torch.cat([part[name] for part in parts], dim=0)
        for name in ("means", "colors", "scales", "quats", "opacities")
    }


def build_shared_scene(
    scene: dict[str, Any], device: int
) -> tuple[dict[str, Any], dict[str, Any], int]:
    indoor_numpy, indoor_meta = transform_source_numpy(
        scene["indoor"], "indoor", 1000 + scene["indoor"]["seed"]
    )
    indoor = to_device(indoor_numpy, device)
    outdoor_numpy, outdoor_meta = transform_source_numpy(
        scene["outdoor"], "outdoor", 2000 + scene["outdoor"]["seed"]
    )
    outdoor = to_device(outdoor_numpy, device)
    connector = to_device(connector_numpy(scene["connector_color"]), device)
    connector_count = int(connector["means"].shape[0])
    combined = concatenate_torch([indoor, outdoor, connector])
    del indoor, outdoor, connector
    gc.collect()
    return (
        combined,
        {
            "indoor": indoor_meta,
            "outdoor": outdoor_meta,
            "assembly": {
                "coordinate_system": "x/z ground plane, negative y up",
                "shared_coordinate_frame": True,
                "image_space_compositing": False,
                "indoor_scale": INDOOR_SCALE,
                "outdoor_scale": OUTDOOR_SCALE,
                "door_center_xyz": [0.0, -DOOR_HEIGHT / 2.0, 0.0],
                "door_clear_width": 2.0 * DOOR_HALF_WIDTH,
                "door_clear_height": DOOR_HEIGHT,
                "flush_threshold": True,
                "exterior_source_start_z": EXTERIOR_START_Z,
                "cleared_walkway_end_z": WALKWAY_END_Z,
                "procedural_connector_gaussian_count": connector_count,
                "construction": (
                    "ground-aligned transformed source splats plus a 3D threshold, "
                    "walkway, two jambs, and lintel"
                ),
            },
        },
        connector_count,
    )


def video_arrays(
    arrays: dict[str, Any], connector_count: int, seed: int
) -> dict[str, Any]:
    import torch

    total = int(arrays["means"].shape[0])
    source_count = total - connector_count
    source_limit = 2 * MAX_SOURCE_VIDEO_SPLATS
    if source_count <= source_limit:
        return arrays
    generator = torch.Generator(device=arrays["means"].device)
    generator.manual_seed(seed)
    source_indices = torch.randperm(
        source_count, generator=generator, device=arrays["means"].device
    )[:source_limit]
    source_indices, _ = torch.sort(source_indices)
    connector_indices = torch.arange(source_count, total, device=arrays["means"].device)
    indices = torch.cat((source_indices, connector_indices))
    return {name: values.index_select(0, indices) for name, values in arrays.items()}


def image_stats(pixels: np.ndarray) -> dict[str, float]:
    unit = pixels.astype(np.float32) / 255.0
    return {"mean": float(unit.mean()), "std": float(unit.std())}


def save_png(path: Path, pixels: np.ndarray) -> dict[str, Any]:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels, mode="RGB").save(path, optimize=True, compress_level=7)
    stats = image_stats(pixels)
    if stats["mean"] <= 0.005 or stats["std"] <= 0.01:
        raise RuntimeError(f"Degenerate image {path}: {stats}")
    return {
        "path": str(path),
        "width": int(pixels.shape[1]),
        "height": int(pixels.shape[0]),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        **stats,
    }


def still_views() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for spec in STILL_VIEW_SPECS:
        position = np.asarray(spec["position"], dtype=np.float32)
        target = np.asarray(spec["target"], dtype=np.float32)
        result[spec["role"]] = {
            **spec,
            "camera_to_world": look_at_camera(position, target),
        }
    return result


def render_stills(
    arrays: dict[str, Any], scene_root: Path
) -> tuple[list[dict[str, Any]], dict[str, list[list[float]]]]:
    records: list[dict[str, Any]] = []
    cameras: dict[str, list[list[float]]] = {}
    for role, spec in still_views().items():
        transform = spec["camera_to_world"]
        pixels = render_one(arrays, transform, *STILL_SIZE)
        path = scene_root / "images" / f"{role}.png"
        record = save_png(path, pixels)
        record.update(
            {
                "role": role,
                "region": spec["region"],
                "distance": spec["distance"],
            }
        )
        records.append(record)
        cameras[role] = transform.tolist()
        print(
            f"SYNCITY3K_CONTINUOUS_IMAGE scene={scene_root.name} role={role}",
            flush=True,
        )
    return records, cameras


def traversal(direction: str, frames: int) -> list[np.ndarray]:
    if direction not in {"inside_to_outside", "outside_to_inside"}:
        raise ValueError(direction)
    start_z, end_z, look_sign = (
        (-2.65, 2.75, 1.0) if direction == "inside_to_outside" else (2.75, -2.65, -1.0)
    )
    transforms: list[np.ndarray] = []
    for index in range(frames):
        fraction = index / max(1, frames - 1)
        move_fraction = min(1.0, max(0.0, (fraction - 0.08) / 0.84))
        smooth = move_fraction * move_fraction * (3.0 - 2.0 * move_fraction)
        z = start_z + (end_z - start_z) * smooth
        x = 0.075 * math.sin(2.0 * math.pi * smooth)
        y = CAMERA_EYE_Y - 0.018 * math.sin(math.pi * smooth)
        position = np.asarray((x, y, z), dtype=np.float32)
        forward_direction = np.asarray((0.0, 0.0, look_sign), dtype=np.float32)
        if direction == "outside_to_inside" and fraction > 0.82:
            turn = (fraction - 0.82) / 0.18
            turn = turn * turn * (3.0 - 2.0 * turn)
            direction_vector = (1.0 - turn) * forward_direction + turn * np.asarray(
                (1.0, 0.0, 0.08), dtype=np.float32
            )
        else:
            direction_vector = forward_direction
        direction_vector /= np.linalg.norm(direction_vector)
        target = position + 1.25 * direction_vector
        target[1] = -0.24
        transforms.append(look_at_camera(position, target))
    return transforms


def open_video_encoder(destination: Path) -> subprocess.Popen[bytes]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required")
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
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def video_record(path: Path, role: str, frames: int) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    return {
        "path": str(path),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "expected_frames": frames,
        **stream,
    }


def render_video(
    arrays: dict[str, Any],
    scene_root: Path,
    direction: str,
    transforms: list[np.ndarray],
) -> dict[str, Any]:
    video_root = scene_root / "videos"
    video_root.mkdir(parents=True, exist_ok=True)
    destination = video_root / f"{direction}.mp4"
    process = open_video_encoder(destination)
    assert process.stdin is not None
    try:
        for index, transform in enumerate(transforms):
            pixels = render_one(arrays, transform, *VIDEO_SIZE)
            process.stdin.write(np.ascontiguousarray(pixels).tobytes())
            if index == 0 or (index + 1) % 12 == 0 or index + 1 == len(transforms):
                print(
                    f"SYNCITY3K_CONTINUOUS_VIDEO_FRAME scene={scene_root.name} "
                    f"direction={direction} frame={index + 1}/{len(transforms)}",
                    flush=True,
                )
        process.stdin.close()
        return_code = process.wait()
        temporary = destination.with_suffix(".tmp.mp4")
        if return_code != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Video encoding failed ({return_code}): {destination}")
        temporary.replace(destination)
    except Exception:
        process.kill()
        process.wait()
        destination.with_suffix(".tmp.mp4").unlink(missing_ok=True)
        raise
    return video_record(destination, direction, len(transforms))


def image_roles() -> list[str]:
    return [spec["role"] for spec in STILL_VIEW_SPECS]


def expected_paths(scene_root: Path) -> list[Path]:
    return [
        *[scene_root / "images" / f"{role}.png" for role in image_roles()],
        scene_root / "videos/inside_to_outside.mp4",
        scene_root / "videos/outside_to_inside.mp4",
        scene_root / "manifest.json",
    ]


def reusable(scene_root: Path, frames: int) -> bool:
    manifest_path = scene_root / "manifest.json"
    if not all(
        path.is_file() and path.stat().st_size > 0
        for path in expected_paths(scene_root)
    ):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if (
        manifest.get("schema_version") != 2
        or manifest.get("video_frames") != frames
        or not manifest.get("render_success")
        or not manifest.get("true_shared_coordinate_3d_scene")
        or manifest.get("image_space_compositing") is not False
    ):
        return False
    hashes = manifest.get("output_sha256", {})
    outputs = expected_paths(scene_root)[:-1]
    return all(
        hashes.get(str(path.relative_to(scene_root))) == sha256_file(path)
        for path in outputs
    )


def clean_obsolete_outputs(scene_root: Path) -> None:
    keep = {path.resolve() for path in expected_paths(scene_root)}
    for folder, pattern in (
        (scene_root / "images", "*.png"),
        (scene_root / "videos", "*.mp4"),
    ):
        if not folder.is_dir():
            continue
        for path in folder.glob(pattern):
            if path.resolve() not in keep:
                path.unlink()


def render_scene(
    scene: dict[str, Any], output: Path, device: int, frames: int, force: bool
) -> dict[str, Any]:
    import torch

    scene_root = output / scene["scene_id"]
    if not force and reusable(scene_root, frames):
        print(f"SYNCITY3K_CONTINUOUS_REUSE scene={scene['scene_id']}", flush=True)
        return json.loads((scene_root / "manifest.json").read_text(encoding="utf-8"))
    scene_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    arrays: dict[str, Any] | None = None
    video_scene: dict[str, Any] | None = None
    try:
        arrays, source_meta, connector_count = build_shared_scene(scene, device)
        combined_count = int(arrays["means"].shape[0])
        image_records, still_cameras = render_stills(arrays, scene_root)
        video_scene = video_arrays(
            arrays, connector_count, 3000 + scene["indoor"]["seed"]
        )
        if video_scene is not arrays:
            del arrays
            arrays = None
        gc.collect()
        torch.cuda.empty_cache()

        trajectories = {
            direction: traversal(direction, frames)
            for direction in ("inside_to_outside", "outside_to_inside")
        }
        videos = [
            render_video(video_scene, scene_root, direction, transforms)
            for direction, transforms in trajectories.items()
        ]
        video_gaussian_count = int(video_scene["means"].shape[0])
        del video_scene
        video_scene = None
        gc.collect()
        torch.cuda.empty_cache()

        for record in image_records:
            record["path"] = relative_to_output(Path(record["path"]), output)
        for record in videos:
            record["path"] = relative_to_output(Path(record["path"]), output)
        output_paths = expected_paths(scene_root)[:-1]
        manifest = {
            "schema_version": 2,
            "created_at_utc": utc_now(),
            "method": "syncity3k",
            "scene_id": scene["scene_id"],
            "render_success": True,
            "true_shared_coordinate_3d_scene": True,
            "image_space_compositing": False,
            "source_pair": source_meta,
            "generation": {
                "type": "shared_coordinate_3d_assembly_of_method_outputs",
                "native_joint_generation": False,
                "note": (
                    "SynCity 3000 generates the source indoor and urban splats separately. "
                    "This reproducible 3D assembly ground-aligns them, opens matching geometry, "
                    "and adds a real 3D threshold. All views render the combined splats in one pass."
                ),
            },
            "connectivity_validation": {
                "single_combined_gaussian_set_per_render": True,
                "doorway_opened_in_indoor_boundary": True,
                "exterior_approach_cleared": True,
                "flush_3d_threshold_present": True,
                "inside_to_outside_camera_crosses_threshold": True,
                "outside_to_inside_camera_crosses_same_threshold": True,
                "inside_path_z_range": [-2.65, 2.75],
                "outside_path_z_range": [2.75, -2.65],
                "threshold_plane_z": 0.0,
                "cleared_indoor_corridor_z_range": [INDOOR_CORRIDOR_START_Z, 0.14],
                "cleared_outdoor_corridor_z_range": [
                    EXTERIOR_START_Z - 0.12,
                    WALKWAY_END_Z,
                ],
            },
            "image_policy": "individual PNGs without montage, text, borders, or view numbers",
            "images": image_records,
            "videos": videos,
            "still_resolution": list(STILL_SIZE),
            "video_resolution": list(VIDEO_SIZE),
            "video_fps": VIDEO_FPS,
            "video_frames": frames,
            "video_duration_seconds": frames / VIDEO_FPS,
            "render_device": device,
            "combined_still_gaussian_count": combined_count,
            "combined_video_gaussian_count": video_gaussian_count,
            "still_camera_to_world": still_cameras,
            "video_camera_to_world": {
                direction: [transform.tolist() for transform in transforms]
                for direction, transforms in trajectories.items()
            },
            "wall_time_seconds": round(time.monotonic() - started, 3),
            "output_sha256": {
                str(path.relative_to(scene_root)): sha256_file(path)
                for path in output_paths
            },
        }
        atomic_json(scene_root / "manifest.json", manifest)
        clean_obsolete_outputs(scene_root)
        print(
            f"SYNCITY3K_CONTINUOUS_SCENE_COMPLETE scene={scene['scene_id']}", flush=True
        )
        return manifest
    finally:
        if arrays is not None:
            del arrays
        if video_scene is not None:
            del video_scene
        gc.collect()
        torch.cuda.empty_cache()


def write_readme(output: Path) -> None:
    text = """# SynCity 3000 continuous indoor/outdoor visualization demos

This package contains six continuous, shared-coordinate 3D presentation
scenes. Each one ground-aligns a frozen SynCity 3000 indoor result and a frozen
urban result, opens the matching boundary geometry, clears the exterior
approach, and inserts a real 3D threshold, walkway, jambs, and lintel.

Every image and every video frame is rasterized from the combined Gaussian set
in one pass. No image-space portal, cross-fade, or two-scene compositing is
used. The two videos move a physical camera through the same threshold in
opposite directions. Ten separate unlabelled PNG files provide indoor,
outdoor, threshold, near, far, oblique, and overview views.

SynCity 3000 itself does not natively co-generate indoor and outdoor scenes in
one coordinate system. These are therefore documented, reproducible 3D
assemblies of frozen method outputs rather than a claim of native joint model
generation. Exact source runs, transforms, cameras, and hashes are recorded in
each scene manifest.
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument("--video-frames", type=int, default=VIDEO_FRAMES)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    if args.video_frames < 2:
        parser.error("--video-frames must be at least 2")
    output = require_below_baselines(args.output)
    output.mkdir(parents=True, exist_ok=True)
    selected = set(args.only)
    known = {scene["scene_id"] for scene in SCENES}
    unknown = selected - known
    if unknown:
        parser.error(f"unknown --only scene(s): {sorted(unknown)}")

    manifests = []
    started_at = utc_now()
    for scene in SCENES:
        if selected and scene["scene_id"] not in selected:
            continue
        print(f"SYNCITY3K_CONTINUOUS_START scene={scene['scene_id']}", flush=True)
        manifests.append(
            render_scene(scene, output, args.device, args.video_frames, args.force)
        )
    write_readme(output)
    root_manifest = {
        "schema_version": 2,
        "method": "syncity3k",
        "created_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "scene_count": len(manifests),
        "expected_full_scene_count": len(SCENES),
        "true_shared_coordinate_3d_scenes": True,
        "image_space_compositing": False,
        "all_images_individual_and_unlabelled": True,
        "views_per_scene": len(STILL_VIEW_SPECS),
        "videos_per_scene": 2,
        "scenes": [
            {
                "scene_id": manifest["scene_id"],
                "manifest": f"{manifest['scene_id']}/manifest.json",
                "render_success": manifest["render_success"],
                "true_shared_coordinate_3d_scene": manifest[
                    "true_shared_coordinate_3d_scene"
                ],
            }
            for manifest in manifests
        ],
    }
    atomic_json(output / "MANIFEST.json", root_manifest)
    print(
        f"SYNCITY3K_CONTINUOUS_COMPLETE output={output} scenes={len(manifests)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
