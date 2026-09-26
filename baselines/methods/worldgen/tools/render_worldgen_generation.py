#!/usr/bin/env python3
"""Render a ZiYang-xie/WorldGen Gaussian scene under frozen Table-2 cameras."""

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
import json
import math
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from plyfile import PlyData


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
SEQUENCE_SIZE = (512, 512)
ANCHOR_SIZE = (1280, 720)
HORIZONTAL_FOV_DEGREES = 70.0


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


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_splat(path: Path) -> dict[str, np.ndarray]:
    vertex = PlyData.read(str(path))["vertex"].data
    names = set(vertex.dtype.names or ())
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
    means = np.column_stack([vertex[name] for name in ("x", "y", "z")]).astype(
        np.float32
    )
    dc = np.column_stack([vertex[f"f_dc_{index}"] for index in range(3)]).astype(
        np.float32
    )
    colors = np.clip(dc * 0.28209479177387814 + 0.5, 0.0, 1.0)
    scales = np.exp(
        np.column_stack([vertex[f"scale_{index}"] for index in range(3)]).astype(
            np.float32
        )
    )
    scales = np.clip(scales, 1e-5, None)
    quats = np.column_stack([vertex[f"rot_{index}"] for index in range(4)]).astype(
        np.float32
    )
    quat_norm = np.linalg.norm(quats, axis=1, keepdims=True)
    quats = quats / np.clip(quat_norm, 1e-8, None)
    opacities = np.asarray(vertex["opacity"], dtype=np.float32)
    if np.any((opacities < 0.0) | (opacities > 1.0)):
        opacities = 1.0 / (1.0 + np.exp(-opacities))
    if not all(
        np.isfinite(array).all() for array in (means, colors, scales, quats, opacities)
    ):
        raise ValueError("Splat PLY contains non-finite values")
    return {
        "means": means,
        "colors": colors,
        "scales": scales,
        "quats": quats,
        "opacities": opacities,
    }


def camera_to_world(position: np.ndarray, yaw_degrees: float) -> np.ndarray:
    yaw = math.radians(yaw_degrees)
    forward = np.asarray([math.sin(yaw), 0.0, math.cos(yaw)], dtype=np.float32)
    right = np.asarray([math.cos(yaw), 0.0, -math.sin(yaw)], dtype=np.float32)
    # WorldGen's pano_unit_rays maps the image top to negative Y and its demo
    # declares ``-y`` as up.  The native scene therefore already follows the
    # right-handed OpenCV x-right, y-down, z-forward camera convention.
    down = np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    transform = np.eye(4, dtype=np.float32)
    transform[:3, 0] = right
    transform[:3, 1] = down
    transform[:3, 2] = forward
    transform[:3, 3] = position
    return transform


def camera_path(domain: str, frames: int = 50) -> list[np.ndarray]:
    if domain == "indoor":
        start = np.asarray([-0.60, 0.0, -0.30], dtype=np.float32)
        end = np.asarray([0.60, 0.0, 0.30], dtype=np.float32)
    elif domain == "urban":
        # DA-2 scales every panorama to a maximum radial depth of 20 rather than
        # metric scene units.  The pilot showed that crossing the single-pano
        # capture center exposes the back of the one-layer outdoor splat.  Use
        # the longest uniformly valid tested path into (not through) the capture
        # center and declare its native normalization instead of calling it meters.
        start = np.asarray([-0.60, 0.0, -0.30], dtype=np.float32)
        end = np.asarray([0.0, 0.0, 0.0], dtype=np.float32)
    else:
        raise ValueError(f"Unsupported domain: {domain}")
    transforms = []
    for index in range(frames):
        fraction = index / (frames - 1)
        smooth = fraction * fraction * (3.0 - 2.0 * fraction)
        position = start * (1.0 - smooth) + end * smooth
        yaw = -35.0 + 70.0 * smooth
        transforms.append(camera_to_world(position, yaw))
    return transforms


def intrinsic(width: int, height: int) -> np.ndarray:
    focal = width / (2.0 * math.tan(math.radians(HORIZONTAL_FOV_DEGREES) / 2.0))
    return np.asarray(
        [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def path_length(transforms: list[np.ndarray]) -> float:
    positions = np.stack([transform[:3, 3] for transform in transforms])
    return float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())


def render_one(
    arrays: dict[str, Any], c2w: np.ndarray, width: int, height: int
) -> np.ndarray:
    import torch
    from gsplat.rendering import rasterization

    c2w_tensor = torch.from_numpy(c2w).to(device="cuda", dtype=torch.float32)
    k_tensor = torch.from_numpy(intrinsic(width, height)).to(
        device="cuda", dtype=torch.float32
    )
    with torch.inference_mode():
        rendered, _, _ = rasterization(
            means=arrays["means"],
            quats=arrays["quats"],
            scales=arrays["scales"],
            opacities=arrays["opacities"],
            colors=arrays["colors"],
            viewmats=torch.linalg.inv(c2w_tensor)[None],
            Ks=k_tensor[None],
            width=width,
            height=height,
            sh_degree=None,
            render_mode="RGB",
            near_plane=0.01,
            far_plane=100.0,
            radius_clip=0.0,
            backgrounds=torch.zeros((3,), device="cuda"),
        )
    image = rendered[0, ..., :3].clamp(0.0, 1.0).mul(255).byte().cpu().numpy()
    return image


def validate_outputs(
    run_dir: Path, domain: str, transforms: list[np.ndarray]
) -> dict[str, Any]:
    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    errors: list[str] = []
    if len(anchors) != 8:
        errors.append(f"anchor_count={len(anchors)} expected=8")
    if len(sequence) != 50:
        errors.append(f"sequence_count={len(sequence)} expected=50")
    stats = []
    for path in anchors + sequence:
        with Image.open(path) as handle:
            pixels = np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0
        mean = float(pixels.mean())
        std = float(pixels.std())
        stats.append({"path": str(path.relative_to(run_dir)), "mean": mean, "std": std})
        if not (0.01 <= mean <= 0.99):
            errors.append(f"{path.name}: mean={mean:.6f} outside [0.01,0.99]")
        if std < 0.01:
            errors.append(f"{path.name}: std={std:.6f} below 0.01")
    length = path_length(transforms)
    minimum = 1.0 if domain == "indoor" else 0.6
    if length < minimum:
        errors.append(f"trajectory_path_length={length:.6f} below {minimum}")
    result = {
        "valid": not errors,
        "errors": errors,
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "trajectory_path_length_native_units": length,
        "image_stats": stats,
    }
    _atomic_json(run_dir / "renders/validation.json", result)
    return result


def render_table2(run_dir: Path, force: bool = False) -> dict[str, Any]:
    import torch

    run_dir = require_below_baselines(run_dir)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    domain = manifest["domain"]
    scene = run_dir / "scene/splat.ply"
    if not scene.exists() or not (run_dir / "GENERATION_SUCCESS").exists():
        raise FileNotFoundError(f"WorldGen reconstruction is incomplete: {scene}")
    if (run_dir / "SUCCESS").exists() and not force:
        return {"valid": True, "skipped": True}

    started_at = utc_now()
    started = time.monotonic()
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    try:
        splat_np = load_splat(scene)
        arrays = {
            name: torch.from_numpy(value).to(device="cuda", dtype=torch.float32)
            for name, value in splat_np.items()
        }
        transforms = camera_path(domain)
        sequence_dir = run_dir / "renders/sequence"
        anchor_dir = run_dir / "renders/anchors"
        sequence_dir.mkdir(parents=True, exist_ok=True)
        anchor_dir.mkdir(parents=True, exist_ok=True)
        for index, transform in enumerate(transforms):
            output = sequence_dir / f"rgb_{index:03d}.png"
            if force or not output.exists():
                Image.fromarray(render_one(arrays, transform, *SEQUENCE_SIZE)).save(
                    output
                )
        for anchor_index, frame_index in enumerate(ANCHOR_INDICES):
            output = anchor_dir / f"rgb_{anchor_index:03d}.png"
            if force or not output.exists():
                Image.fromarray(
                    render_one(arrays, transforms[frame_index], *ANCHOR_SIZE)
                ).save(output)

        sequence_k = intrinsic(*SEQUENCE_SIZE)
        anchor_k = intrinsic(*ANCHOR_SIZE)
        cameras = {
            "coordinate_system": "WorldGen/OpenCV x-right, y-down, z-forward",
            "scale_mode": "DA-2 scale-invariant depth normalized to maximum radius 20",
            "trajectory_units": "native_normalized_not_metric",
            "nominal_camera_height_m": 1.55 if domain == "indoor" else 1.65,
            "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
            "sequence_resolution": list(SEQUENCE_SIZE),
            "anchor_resolution": list(ANCHOR_SIZE),
            "anchor_frame_indices": list(ANCHOR_INDICES),
            "trajectory_path_length_native_units": path_length(transforms),
            "sequence_intrinsic": sequence_k.tolist(),
            "anchor_intrinsic": anchor_k.tolist(),
            "sequence": [
                {
                    "index": index,
                    "K": sequence_k.tolist(),
                    "camera_to_world": transform.tolist(),
                    "world_to_camera": np.linalg.inv(transform).tolist(),
                }
                for index, transform in enumerate(transforms)
            ],
        }
        _atomic_json(sequence_dir / "cameras.json", cameras)
        validation = validate_outputs(run_dir, domain, transforms)
        success = bool(validation["valid"])
        if success:
            (run_dir / "SUCCESS").write_text(
                "worldgen output contract valid\n", encoding="utf-8"
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
        manifest["render_success"] = success
        manifest["failure_reason"] = None if success else "render_validator_failure"
        manifest["failure_detail"] = (
            "" if success else "; ".join(validation["errors"][:20])
        )
        manifest["renderer"] = {
            "implementation": "gsplat",
            "version": getattr(__import__("gsplat"), "__version__", "unknown"),
            "background": "black",
        }
        _atomic_json(manifest_path, manifest)
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
        _atomic_json(manifest_path, manifest)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    validation = render_table2(args.run_dir, args.force)
    print(
        f"WORLDGEN_RENDER_COMPLETE valid={validation['valid']} "
        f"run_dir={args.run_dir}",
        flush=True,
    )
    return 0 if validation["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
