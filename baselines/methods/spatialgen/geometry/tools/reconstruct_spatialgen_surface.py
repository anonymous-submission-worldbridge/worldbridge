#!/usr/bin/env python3
"""Reconstruct a collision surface from a final SpatialGen Gaussian.

The input layout is never used as scored geometry.  The only geometric samples
come from the final iteration-7000 Gaussian rasterizer's median-coordinate
and alpha outputs.  Frozen input camera poses are used solely to recover meter
scale and the common evaluation coordinate frame.
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
import math
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
STAGING_ROOT = Path("/tmp/worldbridge_spatialgen_table3_cache")
RADEGS_ROOT = BASELINES_ROOT / "vendor/SpatialGen/src/recons/Sparse-RaDeGS"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.methods.spatialgen.geometry.adapters.spatialgen import locate_artifacts
from baselines.methods.spatialgen.geometry.adapters.spatialgen import read_json


def assert_baselines_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    resolved.relative_to(BASELINES_ROOT.resolve())
    return resolved


def assert_source_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    for allowed in (BASELINES_ROOT.resolve(), STAGING_ROOT.resolve()):
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue
    raise ValueError(
        f"SpatialGen source must be under baselines/ or the dedicated staging root: {resolved}"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_npz(path: Path, **arrays: Any) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    temporary.replace(path)


def calibrate_similarity(
    normalized_cameras: list[dict[str, Any]],
    compiled_camera_map: dict[str, Any],
    maximum_rotation_error: float = 1e-4,
    maximum_position_rmse_m: float = 1e-4,
) -> dict[str, Any]:
    """Match rotations, then solve q = scale * A @ p + translation."""

    metric_poses = [
        np.asarray(compiled_camera_map[key], dtype=np.float64).reshape(4, 4)
        for key in sorted(compiled_camera_map, key=lambda value: int(value))
    ]
    if len(normalized_cameras) != len(metric_poses) or len(metric_poses) < 3:
        raise RuntimeError(
            f"Camera-count mismatch: normalized={len(normalized_cameras)}, metric={len(metric_poses)}"
        )
    normal_rotations = [
        np.asarray(camera["rotation"], dtype=np.float64)
        for camera in normalized_cameras
    ]
    normal_positions = np.asarray(
        [camera["position"] for camera in normalized_cameras], dtype=np.float64
    )
    best = None
    for reference_index, metric_pose in enumerate(metric_poses):
        align = metric_pose[:3, :3] @ normal_rotations[0].T
        costs = np.asarray(
            [
                [
                    np.linalg.norm(align @ normal_rotation - candidate[:3, :3])
                    for candidate in metric_poses
                ]
                for normal_rotation in normal_rotations
            ]
        )
        match = costs.argmin(axis=1)
        if len(set(int(value) for value in match)) != len(metric_poses):
            continue
        rotation_error = float(costs[np.arange(len(match)), match].max())
        score = float(costs[np.arange(len(match)), match].sum())
        candidate = (score, reference_index, align, match, rotation_error)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise RuntimeError(
            "Could not find a one-to-one rotation match for SpatialGen cameras"
        )
    _, reference_index, align, match, rotation_error = best
    if rotation_error > maximum_rotation_error:
        raise RuntimeError(
            f"Rotation match error {rotation_error} exceeds {maximum_rotation_error}"
        )
    metric_positions = np.asarray([metric_poses[int(index)][:3, 3] for index in match])
    normal_center = normal_positions.mean(axis=0)
    metric_center = metric_positions.mean(axis=0)
    aligned = (normal_positions - normal_center) @ align.T
    centered_metric = metric_positions - metric_center
    denominator = float(np.sum(aligned * aligned))
    if denominator <= 1e-12:
        raise RuntimeError("Degenerate normalized camera trajectory")
    scale = float(np.sum(aligned * centered_metric) / denominator)
    if not math.isfinite(scale) or scale <= 0:
        raise RuntimeError(f"Invalid recovered scale: {scale}")
    translation = metric_center - scale * (align @ normal_center)
    predicted = scale * (normal_positions @ align.T) + translation
    rmse = float(np.sqrt(np.mean((predicted - metric_positions) ** 2)))
    maximum_error = float(np.max(np.abs(predicted - metric_positions)))
    if rmse > maximum_position_rmse_m:
        raise RuntimeError(
            f"Camera calibration RMSE {rmse} exceeds {maximum_position_rmse_m}"
        )
    return {
        "rotation": align,
        "scale": scale,
        "translation": translation,
        "native_to_compiled_indices": [int(value) for value in match],
        "reference_compiled_index": int(reference_index),
        "rotation_match_max_frobenius": rotation_error,
        "position_rmse_m": rmse,
        "position_max_abs_error_m": maximum_error,
    }


def transform_points(points: np.ndarray, calibration: dict[str, Any]) -> np.ndarray:
    rotation = np.asarray(calibration["rotation"], dtype=np.float64)
    translation = np.asarray(calibration["translation"], dtype=np.float64)
    return (
        float(calibration["scale"])
        * (np.asarray(points, dtype=np.float64) @ rotation.T)
        + translation
    )


def voxelize_view_points(
    per_view_points: list[np.ndarray],
    lower: np.ndarray,
    upper: np.ndarray,
    voxel_size: float,
    minimum_views: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    lower = np.asarray(lower, dtype=np.float64)
    upper = np.asarray(upper, dtype=np.float64)
    shape = np.maximum(1, np.ceil((upper - lower) / voxel_size).astype(np.int64))
    if int(np.prod(shape)) > 50_000_000:
        raise RuntimeError(f"Refusing excessive voxel grid {shape.tolist()}")
    hits = np.zeros(tuple(int(value) for value in shape), dtype=np.uint16)
    accepted_points = 0
    for points in per_view_points:
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        finite = np.isfinite(points).all(axis=1)
        points = points[finite]
        inside = np.all((points >= lower) & (points < upper), axis=1)
        points = points[inside]
        accepted_points += int(len(points))
        if not len(points):
            continue
        indices = np.floor((points - lower) / voxel_size).astype(np.int64)
        linear = np.ravel_multi_index(indices.T, hits.shape)
        unique = np.unique(linear)
        flat = hits.reshape(-1)
        flat[unique] = np.minimum(np.iinfo(np.uint16).max, flat[unique] + 1)
    occupied = hits >= int(minimum_views)
    return occupied, {
        "grid_lower_m": lower.tolist(),
        "grid_upper_m": upper.tolist(),
        "grid_shape": [int(value) for value in shape],
        "accepted_surface_samples": accepted_points,
        "observed_voxels": int(np.count_nonzero(hits)),
        "occupied_voxels": int(np.count_nonzero(occupied)),
        "maximum_distinct_view_hits": int(hits.max(initial=0)),
    }


_FACE_DEFINITIONS = (
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((0, 1, 0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))),
    ((0, 0, -1), ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
)


def occupied_voxels_to_mesh(
    occupied: np.ndarray, lower: np.ndarray, voxel_size: float
) -> tuple[np.ndarray, np.ndarray]:
    occupied = np.asarray(occupied, dtype=bool)
    lower = np.asarray(lower, dtype=np.float64)
    vertex_ids: dict[tuple[int, int, int], int] = {}
    vertices: list[np.ndarray] = []
    faces: list[tuple[int, int, int]] = []

    def vertex_id(corner: tuple[int, int, int]) -> int:
        value = vertex_ids.get(corner)
        if value is None:
            value = len(vertices)
            vertex_ids[corner] = value
            vertices.append(lower + voxel_size * np.asarray(corner, dtype=np.float64))
        return value

    shape = occupied.shape
    for cell_array in np.argwhere(occupied):
        cell = tuple(int(value) for value in cell_array)
        for offset, corners in _FACE_DEFINITIONS:
            neighbor = tuple(cell[axis] + offset[axis] for axis in range(3))
            exposed = any(
                neighbor[axis] < 0 or neighbor[axis] >= shape[axis] for axis in range(3)
            )
            if not exposed:
                exposed = not occupied[neighbor]
            if not exposed:
                continue
            ids = [
                vertex_id(tuple(cell[axis] + corner[axis] for axis in range(3)))
                for corner in corners
            ]
            faces.append((ids[0], ids[1], ids[2]))
            faces.append((ids[0], ids[2], ids[3]))
    return np.asarray(vertices, dtype=np.float32).reshape(-1, 3), np.asarray(
        faces, dtype=np.int32
    ).reshape(-1, 3)


def empty_reference(extent: list[float]) -> tuple[np.ndarray, np.ndarray]:
    width, depth = float(extent[0]), float(extent[1])
    vertices = np.asarray(
        [
            [-width / 2, -depth / 2, 0],
            [width / 2, -depth / 2, 0],
            [width / 2, depth / 2, 0],
            [-width / 2, depth / 2, 0],
        ],
        dtype=np.float32,
    )
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    return vertices, faces


def spawn_from_native_input(
    native_input: dict[str, Any], extent: list[float], inset_m: float
) -> tuple[list[float], str]:
    candidates = [
        item
        for item in native_input.get("layout_objects", [])
        if item.get("role") == "entrance_door"
    ]
    if not candidates:
        return [0.0, 0.0, 0.0], "roi_center_fallback"
    center = np.asarray(candidates[0]["center_m"][:2], dtype=np.float64)
    toward_center = -center
    length = float(np.linalg.norm(toward_center))
    if length <= 1e-9:
        return [0.0, 0.0, 0.0], "roi_center_fallback"
    point = center + float(inset_m) * toward_center / length
    half = np.asarray(extent[:2], dtype=np.float64) / 2.0 - 0.05
    point = np.maximum(-half, np.minimum(half, point))
    return [float(point[0]), float(point[1]), 0.0], "entrance_door_inset"


def write_ply(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="ascii") as handle:
        handle.write("ply\nformat ascii 1.0\n")
        handle.write(f"element vertex {len(vertices)}\n")
        handle.write("property float x\nproperty float y\nproperty float z\n")
        handle.write(f"element face {len(faces)}\n")
        handle.write("property list uchar int vertex_indices\nend_header\n")
        for vertex in vertices:
            handle.write(f"{vertex[0]:.7g} {vertex[1]:.7g} {vertex[2]:.7g}\n")
        for face in faces:
            handle.write(f"3 {int(face[0])} {int(face[1])} {int(face[2])}\n")
    temporary.replace(path)


def render_surface(
    source_run: Path,
    output_run: Path,
    protocol_path: Path,
    provenance_source_run: Path | None = None,
) -> dict[str, Any]:
    source_run = assert_source_path(source_run)
    output_run = assert_baselines_path(output_run)
    protocol = read_json(protocol_path)
    config = protocol["surface_reconstruction"]
    paths = locate_artifacts(source_run)
    spec = read_json(paths["spec"])
    native_input = read_json(paths["native_input"])
    table2_manifest = read_json(paths["manifest"])
    normalized_cameras = read_json(paths["normalized_cameras"])
    compiled_cameras = read_json(paths["compiled_cameras"])["cameras"]
    calibration = calibrate_similarity(
        normalized_cameras,
        compiled_cameras,
        float(config["maximum_rotation_match_error"]),
        float(config["maximum_camera_position_rmse_m"]),
    )

    sys.path.insert(0, str(RADEGS_ROOT))
    import torch
    import diff_gaussian_rasterization
    from gaussian_renderer import render
    from scene.cameras import Camera
    from scene.gaussian_model import GaussianModel

    width = int(config["render_width"])
    height = int(config["render_height"])
    gaussian = GaussianModel(3)
    gaussian.load_ply(str(paths["gaussian"]))
    with torch.no_grad():
        effective_opacity = gaussian.get_opacity_with_3D_filter.squeeze(-1)
        gaussian_keep = torch.isfinite(effective_opacity) & (
            effective_opacity
            >= float(config["gaussian_effective_opacity_prune_threshold"])
        )
        original_gaussians = int(len(gaussian_keep))
        retained_gaussians = int(gaussian_keep.sum().item())
        if retained_gaussians == 0:
            raise RuntimeError("Effective-opacity pruning removed every final Gaussian")
        for attribute in (
            "_xyz",
            "_features_dc",
            "_features_rest",
            "_opacity",
            "_scaling",
            "_rotation",
            "filter_3D",
            "_semantic_feature",
        ):
            value = getattr(gaussian, attribute)
            filtered = value.detach()[gaussian_keep].contiguous()
            if isinstance(value, torch.nn.Parameter):
                filtered = torch.nn.Parameter(filtered, requires_grad=False)
            setattr(gaussian, attribute, filtered)
    pipe = SimpleNamespace(
        debug=False, convert_SHs_python=False, compute_cov3D_python=False
    )
    background = torch.zeros(3, dtype=torch.float32, device="cuda")
    per_view_points: list[np.ndarray] = []
    evidence = []
    with torch.no_grad():
        for view_index, record in enumerate(normalized_cameras):
            c2w = np.eye(4, dtype=np.float64)
            c2w[:3, :3] = np.asarray(record["rotation"], dtype=np.float64)
            c2w[:3, 3] = np.asarray(record["position"], dtype=np.float64)
            w2c = np.linalg.inv(c2w)
            fov_x = 2.0 * math.atan(width / (2.0 * float(record["fx"])))
            fov_y = 2.0 * math.atan(height / (2.0 * float(record["fy"])))
            camera = Camera(
                colmap_id=view_index,
                R=c2w[:3, :3],
                T=w2c[:3, 3],
                FoVx=fov_x,
                FoVy=fov_y,
                image=torch.zeros((3, height, width), dtype=torch.float32),
                depth=torch.zeros((height, width), dtype=torch.float32),
                gt_alpha_mask=None,
                image_name=str(view_index),
                uid=view_index,
                warp_mask=None,
                K=None,
                src_R=None,
                src_T=None,
                src_uid=view_index,
                semantic_feature=torch.zeros((3, height, width), dtype=torch.float32),
            )
            output = render(camera, gaussian, pipe, background)
            alpha = output["mask"].detach().float().squeeze().cpu().numpy()
            coordinates = (
                output["median_coord"].detach().float().permute(1, 2, 0).cpu().numpy()
            )
            keep = (alpha >= float(config["alpha_threshold"])) & np.isfinite(
                coordinates
            ).all(axis=2)
            metric_points = transform_points(coordinates[keep], calibration)
            per_view_points.append(metric_points)
            evidence.append(
                {
                    "view_index": view_index,
                    "alpha_pass_pixels": int(np.count_nonzero(keep)),
                    "alpha_mean": float(alpha.mean()),
                    "alpha_max": float(alpha.max(initial=0.0)),
                }
            )
            del output, camera, alpha, coordinates, keep, metric_points

    extent = [float(value) for value in spec["extent_m"]]
    margin = float(config["roi_margin_m"])
    lower = np.asarray([-extent[0] / 2 - margin, -extent[1] / 2 - margin, -margin])
    upper = np.asarray(
        [extent[0] / 2 + margin, extent[1] / 2 + margin, extent[2] + margin]
    )
    occupied, voxel_stats = voxelize_view_points(
        per_view_points,
        lower,
        upper,
        float(config["voxel_size_m"]),
        int(config["minimum_distinct_view_observations"]),
    )
    vertices, faces = occupied_voxels_to_mesh(
        occupied, lower, float(config["voxel_size_m"])
    )
    if not len(vertices) or not len(faces):
        raise RuntimeError("SpatialGen surface reconstruction produced an empty mesh")
    reference_vertices, reference_faces = empty_reference(extent)

    canonical = output_run / "scene/canonical"
    atomic_npz(canonical / "collision_geometry.npz", vertices=vertices, faces=faces)
    atomic_npz(
        canonical / "empty_reference_geometry.npz",
        vertices=reference_vertices,
        faces=reference_faces,
    )
    atomic_npz(
        canonical / "surface_evidence.npz",
        occupied=occupied.astype(np.uint8),
        lower=lower,
        upper=upper,
    )
    write_ply(canonical / "collision.ply", vertices, faces)
    atomic_json(
        canonical / "instances.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "instances": [],
            "reason": "N/A-I",
        },
    )
    calibration_json = {
        key: value.tolist() if isinstance(value, np.ndarray) else value
        for key, value in calibration.items()
    }
    atomic_json(
        canonical / "transform.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "normalized_to_meter_similarity": calibration_json,
        },
    )
    spawn, spawn_source = spawn_from_native_input(
        native_input, extent, float(protocol["navigation"]["spawn_inset_m"])
    )
    floor = [
        [-extent[0] / 2, -extent[1] / 2],
        [extent[0] / 2, -extent[1] / 2],
        [extent[0] / 2, extent[1] / 2],
        [-extent[0] / 2, extent[1] / 2],
    ]
    atomic_json(
        output_run / "input/boundaries.json",
        {
            "evaluation_roi": {"type": "polygon", "xy_m": floor},
            "floor_triangles_xy_m": [
                [floor[0], floor[1], floor[2]],
                [floor[0], floor[2], floor[3]],
            ],
            "floor_z_m": 0.0,
            "structural_spawn_candidate_m": spawn,
            "spawn_source": spawn_source,
            "input_layout_usage": "spawn registration and metric camera calibration only; never scored as geometry",
        },
    )
    (output_run / "input").mkdir(parents=True, exist_ok=True)
    for name, payload in (("spec.json", spec), ("native_input.json", native_input)):
        atomic_json(output_run / "input" / name, payload)
    source_hashes = {
        "gaussian_sha256": sha256(paths["gaussian"]),
        "normalized_cameras_sha256": sha256(paths["normalized_cameras"]),
        "compiled_cameras_sha256": sha256(paths["compiled_cameras"]),
        "table2_manifest_sha256": sha256(paths["manifest"]),
        "rasterizer_binary_sha256": sha256(
            Path(diff_gaussian_rasterization._C.__file__)
        ),
    }
    reconstruction = {
        "algorithm": config["algorithm"],
        "parameters": config,
        "calibration": calibration_json,
        "per_view_evidence": evidence,
        "gaussian_pruning": {
            "original_gaussians": original_gaussians,
            "retained_gaussians": retained_gaussians,
            "retained_fraction": retained_gaussians / original_gaussians,
        },
        "voxel_stats": voxel_stats,
        "mesh_vertices": int(len(vertices)),
        "mesh_faces": int(len(faces)),
        "source_hashes": source_hashes,
    }
    atomic_json(output_run / "scene/reconstruction.json", reconstruction)
    manifest = {
        "method": "spatialgen",
        "domain": "indoor",
        "track": "surface_only",
        "spec_id": spec["spec_id"],
        "logical_seed": int(table2_manifest["logical_seed"]),
        "source_run": str(
            provenance_source_run.resolve() if provenance_source_run else source_run
        ),
        "staged_source_run": str(source_run) if provenance_source_run else None,
        "source_table2_generation_success": bool(table2_manifest["generation_success"]),
        "source_table2_render_success": bool(table2_manifest["render_success"]),
        "method_commit": table2_manifest.get("method_commit"),
        "sparseradegs_commit": table2_manifest.get("sparseradegs_commit"),
        "protocol_sha256": sha256(protocol_path),
        "reconstructor_sha256": sha256(Path(__file__)),
        "source_hashes": source_hashes,
        "canonical_hashes": {
            "collision_geometry_sha256": sha256(canonical / "collision_geometry.npz"),
            "empty_reference_geometry_sha256": sha256(
                canonical / "empty_reference_geometry.npz"
            ),
            "surface_evidence_sha256": sha256(canonical / "surface_evidence.npz"),
            "transform_sha256": sha256(canonical / "transform.json"),
        },
        "hardware": {
            "hostname": platform.node(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "generation_status": "reused_table2_success",
        "export_status": "success",
        "evaluation_status": "pending",
    }
    atomic_json(output_run / "run_manifest.json", manifest)
    (output_run / "GENERATION_SUCCESS").write_text(
        "reused Table-2 final Gaussian\n", encoding="utf-8"
    )
    return reconstruction


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-run", type=Path, required=True)
    parser.add_argument("--provenance-source-run", type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=(
            BASELINES_ROOT
            / "methods/spatialgen/protocol/geometry/spatialgen_protocol.json"
        ),
    )
    args = parser.parse_args()
    result = render_surface(
        args.source_run, args.output_run, args.protocol, args.provenance_source_run
    )
    print(
        json.dumps(
            {
                "status": "success",
                "mesh_faces": result["mesh_faces"],
                "voxel_stats": result["voxel_stats"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
