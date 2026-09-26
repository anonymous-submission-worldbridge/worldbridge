#!/usr/bin/env python3
"""GPU expected-depth surface extraction for a final SynCity 3000 Gaussian.

This stage runs in SynCity's existing Python 3.10 environment.  It deliberately
does not import Recast (the frozen binding is Python 3.11); the companion driver
performs the common navigation evaluation after this process exits.
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
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from plyfile import PlyData


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
PROTOCOL_PATH = BASELINES / "methods/syncity/geometry/protocol.yaml"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_ply(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    vertices = np.ascontiguousarray(vertices, dtype="<f4")
    faces = np.ascontiguousarray(faces, dtype="<i4")
    face_records = np.empty(
        len(faces), dtype=np.dtype([("count", "u1"), ("indices", "<i4", (3,))])
    )
    face_records["count"] = 3
    face_records["indices"] = faces
    with temporary.open("wb") as handle:
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(vertices)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            f"element face {len(faces)}\n"
            "property list uchar int vertex_indices\nend_header\n"
        )
        handle.write(header.encode("ascii"))
        vertices.tofile(handle)
        face_records.tofile(handle)
    temporary.replace(path)


def load_protocol() -> dict[str, Any]:
    return yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))


def points_in_polygons(
    points: np.ndarray, polygons: list[list[list[float]]]
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    answer = np.zeros(len(points), dtype=bool)
    x, y = points[:, 0], points[:, 1]
    for polygon in polygons:
        poly = np.asarray(polygon, dtype=float)
        inside = np.zeros(len(points), dtype=bool)
        previous = len(poly) - 1
        for current in range(len(poly)):
            xi, yi = poly[current]
            xj, yj = poly[previous]
            crosses = (yi > y) != (yj > y)
            intersection = (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
            inside ^= crosses & (x <= intersection)
            previous = current
        answer |= inside
    return answer


def load_splat(path: Path) -> dict[str, Any]:
    vertex = PlyData.read(str(path), mmap=True)["vertex"]
    names = {item.name for item in vertex.properties}
    required = {
        "x",
        "y",
        "z",
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    }
    if not required.issubset(names):
        raise RuntimeError(
            f"Final Gaussian is missing fields: {sorted(required - names)}"
        )
    means = np.column_stack([vertex[name] for name in ("x", "y", "z")]).astype(
        np.float32
    )
    quats = np.column_stack([vertex[f"rot_{index}"] for index in range(4)]).astype(
        np.float32
    )
    quats /= np.clip(np.linalg.norm(quats, axis=1, keepdims=True), 1e-8, None)
    scales = np.exp(
        np.clip(
            np.column_stack([vertex[f"scale_{index}"] for index in range(3)]).astype(
                np.float32
            ),
            -30.0,
            30.0,
        )
    )
    opacity_raw = np.asarray(vertex["opacity"], dtype=np.float32)
    if np.any((opacity_raw < 0.0) | (opacity_raw > 1.0)):
        opacities = 1.0 / (1.0 + np.exp(-np.clip(opacity_raw, -50.0, 50.0)))
    else:
        opacities = opacity_raw
    if not all(np.isfinite(value).all() for value in (means, quats, scales, opacities)):
        raise RuntimeError("Final Gaussian contains non-finite activated fields")
    return {
        "means": means,
        "quats": quats,
        "scales": np.clip(scales, 1e-6, None),
        "opacities": opacities,
        "gaussian_count": int(len(means)),
    }


def calibrate_scale(
    spec: dict[str, Any],
    means: np.ndarray,
    opacities: np.ndarray,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    config = protocol["scale_calibration"]
    visible = opacities >= float(config["visible_opacity_threshold"])
    points = means[visible] if visible.any() else means
    quantiles = [float(value) for value in config["robust_horizontal_quantiles"]]
    x_bounds = np.quantile(points[:, 0], quantiles)
    z_bounds = np.quantile(points[:, 2], quantiles)
    spans = np.asarray([x_bounds[1] - x_bounds[0], z_bounds[1] - z_bounds[0]])
    minimum = float(config["minimum_native_horizontal_span"])
    maximum = float(config["maximum_native_horizontal_span"])
    if not np.all((spans >= minimum) & (spans <= maximum)):
        raise RuntimeError(
            f"Native horizontal spans outside frozen range: {spans.tolist()}"
        )
    grid_units = float(config["native_scene_grid_units"])
    meters_per_native = (
        min(float(spec["extent_m"][0]), float(spec["extent_m"][1])) / grid_units
    )
    floor_y = float(np.quantile(points[:, 1], float(config["floor_source_y_quantile"])))
    return {
        "method": "frozen adapter grid-to-spec similarity plus robust floor alignment",
        "native_scene_grid_units": grid_units,
        "meters_per_native_unit": meters_per_native,
        "native_horizontal_bounds": {"x": x_bounds.tolist(), "z": z_bounds.tolist()},
        "native_horizontal_spans": spans.tolist(),
        "native_center_xz": [float(x_bounds.mean()), float(z_bounds.mean())],
        "native_floor_y": floor_y,
        "visible_gaussian_count": int(visible.sum()),
        "scale_uses_output_bounds": False,
        "translation_uses_output_bounds": True,
    }


def normalize_splat(splat: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    config = protocol["surface_extraction"]
    visible = splat["opacities"] >= float(
        protocol["scale_calibration"]["visible_opacity_threshold"]
    )
    points = splat["means"][visible] if visible.any() else splat["means"]
    low_q, high_q = [float(value) for value in config["normalization_quantiles"]]
    low = np.quantile(points, low_q, axis=0).astype(np.float32)
    high = np.quantile(points, high_q, axis=0).astype(np.float32)
    center = 0.5 * (low + high)
    half_extent = float(max(float((high - low).max()) / 2.0, 1e-4))
    return {
        "center_native": center,
        "half_extent_native": half_extent,
        "robust_low_native": low,
        "robust_high_native": high,
        "means": (splat["means"] - center[None]) / half_extent,
        "scales": splat["scales"] / half_extent,
    }


def look_at(position: np.ndarray, target: np.ndarray) -> np.ndarray:
    forward = target - position
    forward /= np.linalg.norm(forward)
    world_up = np.asarray([0.0, -1.0, 0.0], dtype=np.float32)
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    down /= np.linalg.norm(down)
    transform = np.eye(4, dtype=np.float32)
    transform[:3, 0] = right
    transform[:3, 1] = down
    transform[:3, 2] = forward
    transform[:3, 3] = position
    return transform


def camera_rows(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    config = protocol["surface_extraction"]
    target = np.zeros(3, dtype=np.float32)
    rows = []
    for index in range(int(config["orbit_views"])):
        angle = 2.0 * math.pi * index / int(config["orbit_views"])
        position = np.asarray(
            [
                float(config["normalized_orbit_radius"]) * math.sin(angle),
                float(config["normalized_orbit_height"]),
                float(config["normalized_orbit_radius"]) * math.cos(angle),
            ],
            dtype=np.float32,
        )
        rows.append({"name": f"orbit_{index:02d}", "c2w": look_at(position, target)})
    for index in range(int(config["polar_views"])):
        angle = 2.0 * math.pi * (index + 0.5) / int(config["polar_views"])
        position = np.asarray(
            [
                float(config["normalized_polar_radius"]) * math.sin(angle),
                float(config["normalized_polar_height"]),
                float(config["normalized_polar_radius"]) * math.cos(angle),
            ],
            dtype=np.float32,
        )
        rows.append({"name": f"polar_{index:02d}", "c2w": look_at(position, target)})
    return rows


def intrinsic(protocol: dict[str, Any]) -> np.ndarray:
    config = protocol["surface_extraction"]
    width, height = int(config["render_width"]), int(config["render_height"])
    focal = width / (
        2.0 * math.tan(math.radians(float(config["horizontal_fov_degrees"])) / 2.0)
    )
    return np.asarray(
        [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def depth_grid_mesh(
    depth: np.ndarray,
    alpha: np.ndarray,
    camera: np.ndarray,
    intrinsic_matrix: np.ndarray,
    normalization: dict[str, Any],
    calibration: dict[str, Any],
    boundary: dict[str, Any],
    protocol: dict[str, Any],
    domain: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    config = protocol["surface_extraction"]
    stride = int(config["grid_stride"])
    rows = np.arange(0, depth.shape[0], stride, dtype=np.int64)
    columns = np.arange(0, depth.shape[1], stride, dtype=np.int64)
    sampled_depth = depth[np.ix_(rows, columns)]
    sampled_alpha = alpha[np.ix_(rows, columns)]
    yy, xx = np.meshgrid(
        rows.astype(np.float32), columns.astype(np.float32), indexing="ij"
    )
    valid = (
        np.isfinite(sampled_depth)
        & np.isfinite(sampled_alpha)
        & (sampled_alpha >= float(config["opacity_threshold"]))
        & (sampled_depth >= float(config["near_plane_normalized"]))
        & (sampled_depth <= float(config["far_plane_normalized"]))
    )
    z = sampled_depth.astype(np.float64)
    camera_points = np.stack(
        (
            (xx - float(intrinsic_matrix[0, 2])) / float(intrinsic_matrix[0, 0]) * z,
            (yy - float(intrinsic_matrix[1, 2])) / float(intrinsic_matrix[1, 1]) * z,
            z,
        ),
        axis=-1,
    )
    normalized_world = camera_points @ camera[:3, :3].T + camera[:3, 3]
    native = normalized_world * float(normalization["half_extent_native"]) + np.asarray(
        normalization["center_native"], dtype=np.float64
    )
    scale = float(calibration["meters_per_native_unit"])
    center_x, center_z = calibration["native_center_xz"]
    vertices_grid = np.stack(
        (
            (native[..., 0] - float(center_x)) * scale,
            (native[..., 2] - float(center_z)) * scale,
            (float(calibration["native_floor_y"]) - native[..., 1]) * scale,
        ),
        axis=-1,
    ).astype(np.float32)
    height, width = vertices_grid.shape[:2]
    grid = np.arange(height * width, dtype=np.int32).reshape(height, width)
    a, b, c, d = grid[:-1, :-1], grid[:-1, 1:], grid[1:, :-1], grid[1:, 1:]
    faces = np.concatenate(
        (
            np.stack((a, b, c), axis=-1).reshape(-1, 3),
            np.stack((b, d, c), axis=-1).reshape(-1, 3),
        ),
        axis=0,
    )
    vertices = vertices_grid.reshape(-1, 3)
    vertex_valid = valid.reshape(-1)
    triangles = vertices[faces]
    edges = np.stack(
        (
            np.linalg.norm(triangles[:, 1] - triangles[:, 0], axis=1),
            np.linalg.norm(triangles[:, 2] - triangles[:, 1], axis=1),
            np.linalg.norm(triangles[:, 0] - triangles[:, 2], axis=1),
        ),
        axis=1,
    )
    areas = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    centers = triangles.mean(axis=1)
    in_region = points_in_polygons(centers[:, :2], boundary["walkable_polygons_xy_m"])
    lower = -float(config["lower_height_margin_m"])
    upper = float(protocol["agent"]["height_m"]) + float(
        config["upper_height_margin_above_agent_m"]
    )
    in_height = (triangles[:, :, 2].max(axis=1) >= lower) & (
        triangles[:, :, 2].min(axis=1) <= upper
    )
    maximum_edge = float(config["maximum_triangle_edge_m"][domain])
    keep = (
        vertex_valid[faces].all(axis=1)
        & np.isfinite(edges).all(axis=1)
        & (edges.max(axis=1) <= maximum_edge)
        & np.isfinite(areas)
        & (areas > 1e-10)
        & in_region
        & in_height
    )
    faces = faces[keep]
    if not len(faces):
        return (
            np.empty((0, 3), np.float32),
            np.empty((0, 3), np.int32),
            {
                "sampled_pixels": int(len(vertices)),
                "alpha_valid_pixels": int(valid.sum()),
                "retained_faces": 0,
            },
        )
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return (
        vertices[used],
        remap[faces],
        {
            "sampled_pixels": int(len(vertices)),
            "alpha_valid_pixels": int(valid.sum()),
            "retained_vertices": int(len(used)),
            "retained_faces": int(len(faces)),
            "maximum_triangle_edge_m": maximum_edge,
        },
    )


def extract(
    raw: Path,
    spec_path: Path,
    boundary_path: Path,
    output_dir: Path,
    source_sha256: str | None,
) -> dict[str, Any]:
    import torch
    from gsplat.rendering import rasterization

    raw = require_below_baselines(raw)
    output_dir = require_below_baselines(output_dir)
    protocol = load_protocol()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    domain = str(spec["domain"])
    splat = load_splat(raw)
    calibration = calibrate_scale(spec, splat["means"], splat["opacities"], protocol)
    normalization = normalize_splat(splat, protocol)
    device = {
        "means": torch.from_numpy(normalization["means"]).to(
            "cuda", dtype=torch.float32
        ),
        "scales": torch.from_numpy(normalization["scales"]).to(
            "cuda", dtype=torch.float32
        ),
        "quats": torch.from_numpy(splat["quats"]).to("cuda", dtype=torch.float32),
        "opacities": torch.from_numpy(splat["opacities"]).to(
            "cuda", dtype=torch.float32
        ),
    }
    colors = torch.zeros(
        (splat["gaussian_count"], 1), device="cuda", dtype=torch.float32
    )
    matrix = intrinsic(protocol)
    matrix_tensor = torch.from_numpy(matrix).to("cuda")
    config = protocol["surface_extraction"]
    all_vertices, all_faces, evidence = [], [], []
    offset = 0
    for index, row in enumerate(camera_rows(protocol)):
        camera = row["c2w"]
        camera_tensor = torch.from_numpy(camera).to("cuda")
        with torch.inference_mode():
            rendered, alpha, _ = rasterization(
                means=device["means"],
                quats=device["quats"],
                scales=device["scales"],
                opacities=device["opacities"],
                colors=colors,
                viewmats=torch.linalg.inv(camera_tensor)[None],
                Ks=matrix_tensor[None],
                width=int(config["render_width"]),
                height=int(config["render_height"]),
                render_mode="ED",
                near_plane=float(config["near_plane_normalized"]),
                far_plane=float(config["far_plane_normalized"]),
                radius_clip=0.0,
                packed=True,
            )
        depth = rendered[0, ..., 0].float().cpu().numpy()
        alpha_np = alpha[0, ..., 0].float().cpu().numpy()
        vertices, faces, stats = depth_grid_mesh(
            depth,
            alpha_np,
            camera,
            matrix,
            normalization,
            calibration,
            boundary,
            protocol,
            domain,
        )
        if len(faces):
            all_vertices.append(vertices)
            all_faces.append(faces + offset)
            offset += len(vertices)
        evidence.append(
            {
                "index": index,
                "camera": row["name"],
                "normalized_position": camera[:3, 3].tolist(),
                "alpha_mean": float(alpha_np.mean()),
                **stats,
            }
        )
        del rendered, alpha, depth, alpha_np, vertices, faces
    del device, colors
    torch.cuda.empty_cache()
    if not all_faces:
        raise RuntimeError("SynCity expected-depth reconstruction is empty")
    vertices = np.concatenate(all_vertices, axis=0)
    faces = np.concatenate(all_faces, axis=0)
    collision = output_dir / "collision.ply"
    write_ply(collision, vertices, faces)
    transform = {
        "source_coordinate_system": "right-handed x/z ground plane, negative-y up",
        "target_coordinate_system": "right-handed z-up meter",
        "mapping": "((source_x-center_x)*scale, (source_z-center_z)*scale, (floor_y-source_y)*scale)",
        "render_normalization": {
            "center_native": normalization["center_native"].tolist(),
            "half_extent_native": normalization["half_extent_native"],
            "robust_low_native": normalization["robust_low_native"].tolist(),
            "robust_high_native": normalization["robust_high_native"].tolist(),
        },
        "scale_calibration": calibration,
    }
    atomic_json(output_dir / "transform.json", transform)
    result = {
        "created_at_utc": utc_now(),
        "method": "syncity3k",
        "domain": domain,
        "spec_id": spec["spec_id"],
        "algorithm": "24-view gsplat expected-depth grid triangulation",
        "parameters": config,
        "gaussian_count": splat["gaussian_count"],
        "selected_cameras": [row["camera"] for row in evidence],
        "mesh_vertices": int(len(vertices)),
        "mesh_faces": int(len(faces)),
        "per_view": evidence,
        "scale_calibration": calibration,
        "source_gaussian_sha256": source_sha256 or sha256_file(raw),
        "collision_sha256": sha256_file(collision),
        "native_navmesh_used": False,
        "hole_filling_used": False,
        "components_connected": False,
        "largest_component_only": False,
    }
    atomic_json(output_dir / "extraction.json", result)
    atomic_json(
        output_dir / "instances.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "representation": "surface_only",
            "native_instance_coverage": 0.0,
            "instances": [],
            "na_reason": "N/A-I",
            "floor_z_m": 0.0,
        },
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-sha256")
    args = parser.parse_args()
    result = extract(
        args.raw, args.spec, args.boundaries, args.output_dir, args.source_sha256
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "method",
                    "domain",
                    "spec_id",
                    "mesh_vertices",
                    "mesh_faces",
                )
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
