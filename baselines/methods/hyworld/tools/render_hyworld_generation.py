#!/usr/bin/env python3
"""Render a HY-World 2.0 Gaussian scene for the frozen Table-2 protocol."""

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
import math
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
SEQUENCE_SIZE = (512, 512)
ANCHOR_SIZE = (1280, 720)
HORIZONTAL_FOV_DEGREES = 70.0
NEAR_PLANE = 0.01
NEAR_PLANE_DEPTH = 0.02


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path must remain below {BASELINES_ROOT}: {resolved}"
        ) from exc
    return resolved


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    # The shared filesystem occasionally delays visibility of a just-created
    # sibling temporary file, making an immediate os.replace spuriously fail.
    # Each run has a single writer, so a direct write is safe here and avoids
    # turning fully rendered scenes into infrastructure failures.
    path.write_text(serialized, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_splat(path: Path) -> dict[str, np.ndarray | int]:
    from plyfile import PlyData

    vertex = PlyData.read(str(path))["vertex"]
    names = {prop.name for prop in vertex.properties}
    required = {
        "x",
        "y",
        "z",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    }
    missing = required - names
    if missing:
        raise ValueError(f"Splat PLY is missing attributes: {sorted(missing)}")
    means = np.stack([vertex[name] for name in ("x", "y", "z")], axis=-1).astype(
        np.float32
    )
    quats = np.stack([vertex[f"rot_{index}"] for index in range(4)], axis=-1).astype(
        np.float32
    )
    quats /= np.clip(np.linalg.norm(quats, axis=1, keepdims=True), 1e-8, None)
    scales = np.exp(
        np.stack([vertex[f"scale_{index}"] for index in range(3)], axis=-1).astype(
            np.float32
        )
    )
    opacities = np.asarray(vertex["opacity"], dtype=np.float32)
    opacities = 1.0 / (1.0 + np.exp(-opacities))
    sh0 = np.stack([vertex[f"f_dc_{index}"] for index in range(3)], axis=-1).astype(
        np.float32
    )
    rest_names = sorted(
        (name for name in names if name.startswith("f_rest_")),
        key=lambda name: int(name.rsplit("_", 1)[1]),
    )
    if len(rest_names) % 3:
        raise ValueError(f"Invalid number of higher-order SH fields: {len(rest_names)}")
    if rest_names:
        shn = np.stack([vertex[name] for name in rest_names], axis=-1).astype(
            np.float32
        )
        shn = shn.reshape(len(means), len(rest_names) // 3, 3)
        colors = np.concatenate([sh0[:, None, :], shn], axis=1)
    else:
        colors = sh0[:, None, :]
    sh_degree = round(math.sqrt(colors.shape[1]) - 1)
    if (sh_degree + 1) ** 2 != colors.shape[1]:
        raise ValueError(f"Invalid SH coefficient count: {colors.shape[1]}")
    arrays = (means, quats, scales, opacities, colors)
    if not all(np.isfinite(array).all() for array in arrays):
        raise ValueError("Splat PLY contains non-finite values")
    return {
        "means": means,
        "quats": quats,
        "scales": np.clip(scales, 1e-6, None),
        "opacities": opacities,
        "colors": colors,
        "sh_degree": sh_degree,
    }


def is_aerial_camera(path: Path, payload: dict[str, Any]) -> bool:
    camera_type = str(payload.get("type", "")).lower()
    # Regular aerial proposals name their type explicitly. Navigation aerial
    # trajectories retain the semantic task type but uniquely record this
    # obstruction diagnostic.
    return "aerial" in camera_type or "max_xy_angle" in payload


def native_camera_candidates(native: Path) -> list[dict[str, Any]]:
    candidates = []
    for path in sorted((native / "render_results").rglob("camera.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if is_aerial_camera(path, payload):
            continue
        extrinsic = np.asarray(payload.get("extrinsic"), dtype=np.float64)
        intrinsic = np.asarray(payload.get("intrinsic"), dtype=np.float64)
        if extrinsic.ndim != 3 or extrinsic.shape[1:] != (4, 4) or len(extrinsic) < 2:
            continue
        if intrinsic.ndim != 3 or intrinsic.shape[0] != extrinsic.shape[0]:
            continue
        if not np.isfinite(extrinsic).all() or not np.isfinite(intrinsic).all():
            continue
        c2w = np.linalg.inv(extrinsic)
        length = float(np.linalg.norm(np.diff(c2w[:, :3, 3], axis=0), axis=1).sum())
        displacement = float(np.linalg.norm(c2w[-1, :3, 3] - c2w[0, :3, 3]))
        candidates.append(
            {
                "path": path,
                "camera_type": payload.get("type"),
                "c2w": c2w,
                "native_length": length,
                "native_displacement": displacement,
            }
        )
    return candidates


def choose_native_trajectory(native: Path) -> dict[str, Any]:
    candidates = native_camera_candidates(native)
    if not candidates:
        raise FileNotFoundError(f"No valid non-aerial camera trajectory below {native}")
    # Python's max keeps the first item on a tie; candidates are path-sorted,
    # making the selection stable across filesystems.
    return max(candidates, key=lambda row: row["native_length"])


def load_training_transform(run_dir: Path, step: int) -> tuple[np.ndarray, Path]:
    import torch

    checkpoints = sorted((run_dir / "scene/gs/ckpts").glob(f"ckpt_{step}_rank*.pt"))
    if not checkpoints:
        raise FileNotFoundError(
            "Missing GS training checkpoint needed for its similarity transform"
        )
    checkpoint = next(
        (path for path in checkpoints if path.name.endswith("rank0.pt")), checkpoints[0]
    )
    try:
        payload = torch.load(
            checkpoint, map_location="cpu", weights_only=False, mmap=True
        )
    except TypeError:
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    transform = payload.get("transform")
    if hasattr(transform, "detach"):
        transform = transform.detach().cpu().numpy()
    transform = np.asarray(transform, dtype=np.float64)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError(f"Invalid training similarity transform in {checkpoint}")
    return transform, checkpoint


def transform_cameras(transform: np.ndarray, cameras: np.ndarray) -> np.ndarray:
    result = np.einsum("nij,ki->nkj", cameras, transform)
    scaling = np.linalg.norm(result[:, 0, :3], axis=1)
    if np.any(scaling <= 0):
        raise ValueError("Degenerate transformed camera rotation")
    result[:, :3, :3] /= scaling[:, None, None]
    result[:, 3, :] = np.asarray([0.0, 0.0, 0.0, 1.0])
    return result


def rotation_to_quaternion(matrix: np.ndarray) -> np.ndarray:
    """Convert a 3x3 rotation to a normalized wxyz quaternion."""
    quaternion = np.empty(4, dtype=np.float64)
    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion[:] = [
            0.25 * scale,
            (matrix[2, 1] - matrix[1, 2]) / scale,
            (matrix[0, 2] - matrix[2, 0]) / scale,
            (matrix[1, 0] - matrix[0, 1]) / scale,
        ]
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            scale = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            quaternion[:] = [
                (matrix[2, 1] - matrix[1, 2]) / scale,
                0.25 * scale,
                (matrix[0, 1] + matrix[1, 0]) / scale,
                (matrix[0, 2] + matrix[2, 0]) / scale,
            ]
        elif index == 1:
            scale = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            quaternion[:] = [
                (matrix[0, 2] - matrix[2, 0]) / scale,
                (matrix[0, 1] + matrix[1, 0]) / scale,
                0.25 * scale,
                (matrix[1, 2] + matrix[2, 1]) / scale,
            ]
        else:
            scale = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            quaternion[:] = [
                (matrix[1, 0] - matrix[0, 1]) / scale,
                (matrix[0, 2] + matrix[2, 0]) / scale,
                (matrix[1, 2] + matrix[2, 1]) / scale,
                0.25 * scale,
            ]
    return quaternion / np.linalg.norm(quaternion)


def quaternion_to_rotation(quaternion: np.ndarray) -> np.ndarray:
    w, x, y, z = quaternion / np.linalg.norm(quaternion)
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def quaternion_slerp(
    first: np.ndarray, second: np.ndarray, fraction: float
) -> np.ndarray:
    dot = float(np.dot(first, second))
    if dot < 0.0:
        second = -second
        dot = -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        result = first + fraction * (second - first)
        return result / np.linalg.norm(result)
    angle = math.acos(dot)
    sin_angle = math.sin(angle)
    return (
        math.sin((1.0 - fraction) * angle) / sin_angle * first
        + math.sin(fraction * angle) / sin_angle * second
    )


def resample_cameras(cameras: np.ndarray, frames: int = 50) -> np.ndarray:
    if len(cameras) < 2:
        raise ValueError("At least two native poses are required")
    source_t = np.linspace(0.0, 1.0, len(cameras))
    target_t = np.linspace(0.0, 1.0, frames)
    result = np.tile(np.eye(4, dtype=np.float64), (frames, 1, 1))
    for axis in range(3):
        result[:, axis, 3] = np.interp(target_t, source_t, cameras[:, axis, 3])
    quaternions = [rotation_to_quaternion(matrix) for matrix in cameras[:, :3, :3]]
    for target_index, target in enumerate(target_t):
        source_position = target * (len(cameras) - 1)
        before = min(int(math.floor(source_position)), len(cameras) - 2)
        fraction = source_position - before
        quaternion = quaternion_slerp(
            quaternions[before], quaternions[before + 1], fraction
        )
        result[target_index, :3, :3] = quaternion_to_rotation(quaternion)
    return result.astype(np.float32)


def intrinsic(width: int, height: int) -> np.ndarray:
    focal = width / (2.0 * math.tan(math.radians(HORIZONTAL_FOV_DEGREES) / 2.0))
    return np.asarray(
        [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def path_statistics(cameras: np.ndarray) -> tuple[float, float]:
    positions = cameras[:, :3, 3]
    length = float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())
    displacement = float(np.linalg.norm(positions[-1] - positions[0]))
    return length, displacement


def render_one(
    arrays: dict[str, Any], c2w: np.ndarray, width: int, height: int
) -> tuple[np.ndarray, float]:
    import torch
    from gsplat.rendering import rasterization

    c2w_tensor = torch.from_numpy(c2w).to(device="cuda", dtype=torch.float32)
    k_tensor = torch.from_numpy(intrinsic(width, height)).to(
        device="cuda", dtype=torch.float32
    )
    with torch.inference_mode():
        rendered, alpha, _ = rasterization(
            means=arrays["means"],
            quats=arrays["quats"],
            scales=arrays["scales"],
            opacities=arrays["opacities"],
            colors=arrays["colors"],
            viewmats=torch.linalg.inv(c2w_tensor)[None],
            Ks=k_tensor[None],
            width=width,
            height=height,
            sh_degree=arrays["sh_degree"],
            render_mode="RGB+D",
            near_plane=NEAR_PLANE,
            far_plane=1000.0,
            radius_clip=0.0,
            backgrounds=None,
        )
    image = rendered[0, ..., :3].clamp(0.0, 1.0).mul(255).byte().cpu().numpy()
    depth = rendered[0, ..., 3]
    visible = alpha[0, ..., 0] > 1e-4
    near_fraction = float(
        ((depth < NEAR_PLANE_DEPTH) & visible).sum().item()
        / max(visible.sum().item(), 1)
    )
    return image, near_fraction


def valid_rgb_image(path: Path, expected_size: tuple[int, int]) -> bool:
    if not path.is_file():
        return False
    try:
        with Image.open(path) as handle:
            handle.load()
            return handle.size == expected_size and handle.mode in {"RGB", "RGBA"}
    except (OSError, ValueError):
        return False


def validate_outputs(
    run_dir: Path,
    cameras: np.ndarray,
    near_fractions: list[float],
) -> dict[str, Any]:
    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    errors: list[str] = []
    if len(anchors) != 8:
        errors.append(f"anchor_count={len(anchors)} expected=8")
    if len(sequence) != 50:
        errors.append(f"sequence_count={len(sequence)} expected=50")
    stats = []
    sequence_arrays = []
    for path in anchors + sequence:
        with Image.open(path) as handle:
            pixels = np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0
        mean = float(pixels.mean())
        std = float(pixels.std())
        stats.append({"path": str(path.relative_to(run_dir)), "mean": mean, "std": std})
        if not (0.01 <= mean <= 0.99):
            errors.append(f"{path.name}: mean={mean:.6f} outside [0.01,0.99]")
        if std < 0.02:
            errors.append(f"{path.name}: std={std:.6f} below 0.02")
        if path.parent.name == "sequence":
            sequence_arrays.append(pixels)
    length, displacement = path_statistics(cameras)
    if length < 1.0:
        errors.append(f"trajectory_path_length={length:.6f} below 1.0")
    if displacement < 0.5:
        errors.append(f"trajectory_max_displacement={displacement:.6f} below 0.5")
    adjacent = [
        float(np.abs(after - before).mean())
        for before, after in zip(sequence_arrays, sequence_arrays[1:])
    ]
    mean_adjacent = float(np.mean(adjacent)) if adjacent else 0.0
    if mean_adjacent < 0.005:
        errors.append(f"mean_adjacent_frame_difference={mean_adjacent:.6f} below 0.005")
    max_near_fraction = max(near_fractions, default=1.0)
    if max_near_fraction > 0.30:
        errors.append(f"maximum_near_plane_fraction={max_near_fraction:.6f} above 0.30")
    result = {
        "valid": not errors,
        "errors": errors,
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "trajectory_path_length_normalized": length,
        "trajectory_max_displacement_normalized": displacement,
        "mean_adjacent_frame_difference": mean_adjacent,
        "maximum_near_plane_fraction": max_near_fraction,
        "image_stats": stats,
    }
    atomic_json(run_dir / "renders/validation.json", result)
    return result


def render_table2(run_dir: Path, force: bool = False) -> dict[str, Any]:
    import torch

    run_dir = require_below_baselines(run_dir)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native = run_dir / "scene/native"
    position_meta = run_dir / "scene/gs/ply/position_meta_info.json"
    candidates = []
    for path in (run_dir / "scene/gs/ply").glob("point_cloud_*.ply"):
        match = re.fullmatch(r"point_cloud_(\d+)\.ply", path.name)
        if match and path.is_file():
            candidates.append((int(match.group(1)), path))
    candidates.sort(reverse=True)
    compatible = [
        (step, path)
        for step, path in candidates
        if list((run_dir / "scene/gs/ckpts").glob(f"ckpt_{step}_rank*.pt"))
    ]
    if not compatible or not position_meta.is_file():
        raise FileNotFoundError(f"HY-World GS training is incomplete below {run_dir}")
    gs_step, ply = compatible[0]
    if (run_dir / "SUCCESS").exists() and not force:
        validation = json.loads(
            (run_dir / "renders/validation.json").read_text(encoding="utf-8")
        )
        return {**validation, "skipped": True}

    started_at = utc_now()
    started = time.monotonic()
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    (run_dir / "RENDER_QUALITY_FAILURE").unlink(missing_ok=True)
    try:
        chosen = choose_native_trajectory(native)
        transform, transform_checkpoint = load_training_transform(run_dir, gs_step)
        transformed = transform_cameras(transform, chosen["c2w"])
        cameras = resample_cameras(transformed, 50)
        splat_np = load_splat(ply)
        arrays = {
            name: torch.from_numpy(value).to(device="cuda", dtype=torch.float32)
            for name, value in splat_np.items()
            if isinstance(value, np.ndarray)
        }
        arrays["sh_degree"] = splat_np["sh_degree"]
        sequence_dir = run_dir / "renders/sequence"
        anchor_dir = run_dir / "renders/anchors"
        sequence_dir.mkdir(parents=True, exist_ok=True)
        anchor_dir.mkdir(parents=True, exist_ok=True)
        near_fractions = []
        for index, camera in enumerate(cameras):
            output = sequence_dir / f"rgb_{index:03d}.png"
            if force or not valid_rgb_image(output, SEQUENCE_SIZE):
                image, near_fraction = render_one(arrays, camera, *SEQUENCE_SIZE)
                Image.fromarray(image).save(output)
            else:
                _, near_fraction = render_one(arrays, camera, 64, 64)
            near_fractions.append(near_fraction)
        for anchor_index, frame_index in enumerate(ANCHOR_INDICES):
            output = anchor_dir / f"rgb_{anchor_index:03d}.png"
            if force or not valid_rgb_image(output, ANCHOR_SIZE):
                image, _ = render_one(arrays, cameras[frame_index], *ANCHOR_SIZE)
                Image.fromarray(image).save(output)

        sequence_k = intrinsic(*SEQUENCE_SIZE)
        anchor_k = intrinsic(*ANCHOR_SIZE)
        length, displacement = path_statistics(cameras)
        camera_record = {
            "coordinate_system": "HY-World normalized OpenCV x-right, y-down, z-forward",
            "trajectory_source": str(chosen["path"].relative_to(native)),
            "trajectory_type": chosen["camera_type"],
            "selection": "longest_non_aerial_native_trajectory",
            "source_native_length": chosen["native_length"],
            "source_native_displacement": chosen["native_displacement"],
            "pose_normalization": "gs_training_similarity_transform",
            "transform_checkpoint": str(transform_checkpoint.relative_to(run_dir)),
            "transform_checkpoint_sha256": sha256_file(transform_checkpoint),
            "training_transform": transform.tolist(),
            "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
            "sequence_resolution": list(SEQUENCE_SIZE),
            "anchor_resolution": list(ANCHOR_SIZE),
            "anchor_frame_indices": list(ANCHOR_INDICES),
            "trajectory_path_length_normalized": length,
            "trajectory_max_displacement_normalized": displacement,
            "sequence_intrinsic": sequence_k.tolist(),
            "anchor_intrinsic": anchor_k.tolist(),
            "sequence": [
                {
                    "index": index,
                    "K": sequence_k.tolist(),
                    "camera_to_world": camera.tolist(),
                    "world_to_camera": np.linalg.inv(camera).tolist(),
                }
                for index, camera in enumerate(cameras)
            ],
        }
        atomic_json(sequence_dir / "cameras.json", camera_record)
        validation = validate_outputs(run_dir, cameras, near_fractions)
        success = bool(validation["valid"])
        if success:
            (run_dir / "GENERATION_SUCCESS").write_text(
                "hyworld2 six-stage output contract valid\n", encoding="utf-8"
            )
            (run_dir / "SUCCESS").write_text(
                "hyworld2 render contract valid\n", encoding="utf-8"
            )
        else:
            (run_dir / "RENDER_QUALITY_FAILURE").write_text(
                "; ".join(validation["errors"][:20]) + "\n", encoding="utf-8"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("attempts", []).append(
            {
                "attempt": 1
                + sum(
                    row.get("phase") == "render" for row in manifest.get("attempts", [])
                ),
                "phase": "render",
                "started_at_utc": started_at,
                "ended_at_utc": utc_now(),
                "wall_time_s": round(time.monotonic() - started, 6),
                "success": success,
                "detail": "" if success else "; ".join(validation["errors"][:20]),
            }
        )
        manifest["generation_success"] = True
        manifest["render_success"] = success
        manifest["failure_reason"] = None if success else "render_validator_failure"
        manifest["failure_detail"] = (
            "" if success else "; ".join(validation["errors"][:20])
        )
        manifest["renderer"] = {
            "implementation": "gsplat",
            "version": getattr(__import__("gsplat"), "__version__", "unknown"),
            "background": "black",
            "source_ply": str(ply.relative_to(run_dir)),
            "source_ply_sha256": sha256_file(ply),
        }
        atomic_json(manifest_path, manifest)
        return validation
    except Exception:
        detail = traceback.format_exc()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("attempts", []).append(
            {
                "attempt": 1
                + sum(
                    row.get("phase") == "render" for row in manifest.get("attempts", [])
                ),
                "phase": "render",
                "started_at_utc": started_at,
                "ended_at_utc": utc_now(),
                "wall_time_s": round(time.monotonic() - started, 6),
                "success": False,
                "detail": detail[-4000:],
            }
        )
        manifest["render_success"] = False
        manifest["failure_reason"] = "render_infrastructure_failure"
        manifest["failure_detail"] = detail[-4000:]
        atomic_json(manifest_path, manifest)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    validation = render_table2(args.run_dir, args.force)
    print(
        f"HYWORLD2_RENDER_COMPLETE valid={validation['valid']} run_dir={args.run_dir}",
        flush=True,
    )
    return 0 if validation["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
