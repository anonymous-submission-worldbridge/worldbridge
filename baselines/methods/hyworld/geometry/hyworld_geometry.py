#!/usr/bin/env python3
"""Auditable HY-World 2.0 Table-3 surface-only evaluator.

The complete Table-2 matrix is reused read-only. Expected depth is rendered
from each final trained Gaussian representation, converted to a canonical
meter-scale surface, and passed to the common Recast evaluator. HY-World's
planning NavMesh and planning point cloud are deliberately never scored.
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
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from PIL import Image, ImageDraw
from plyfile import PlyData


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
PACKAGE_ROOT = BASELINES / "methods/hyworld/geometry"
PROTOCOL_PATH = PACKAGE_ROOT / "protocol.yaml"
METHOD_LOCK_PATH = PACKAGE_ROOT / "method.lock.json"
METRICS_LOCK_PATH = PACKAGE_ROOT / "metrics.lock.json"
TABLE2_ROOT = BASELINES / "hyworld2_runtime/data/table2"
DATA_ROOT = BASELINES / "data/table3_hyworld2"
RESULTS_ROOT = PACKAGE_ROOT / "results"
REFERENCE_ROOT = PACKAGE_ROOT / "cache/reference"
RECAST_RUNTIME = BASELINES / "methods/worldgen/geometry/runtime/recast_glibc231_clean2"
GSPLAT_ROOT = (
    BASELINES / "sources/HY-World-2.0/hyworld2/worldgen/third_party/gsplat_maskgaussian"
)
HY_SOURCE_ROOT = BASELINES / "sources/HY-World-2.0"
HY_WORLDGEN_ROOT = HY_SOURCE_ROOT / "hyworld2/worldgen"
HY_RUNTIME_PYTHON = BASELINES / "hyworld2_runtime/python"
HY_RUNTIME_SM86 = BASELINES / "hyworld2_runtime/python_sm86"
COMMON_NAVMESH = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"

RUNTIME_IMPORT_ORDER = (
    REPO_ROOT,
    RECAST_RUNTIME,
    HY_RUNTIME_SM86,
    # This overlay contains csrc.py, which loads the already compiled,
    # ABI-matched gsplat CUDA extension instead of rebuilding it.
    HY_RUNTIME_PYTHON,
    HY_SOURCE_ROOT,
    HY_WORLDGEN_ROOT,
    GSPLAT_ROOT,
)
for path in RUNTIME_IMPORT_ORDER:
    while str(path) in sys.path:
        sys.path.remove(str(path))
sys.path[:0] = [str(path) for path in RUNTIME_IMPORT_ORDER]

from baselines.evaluation.geometry.metrics.build_navmesh import build
from baselines.evaluation.geometry.metrics.build_navmesh import connected_components
from baselines.evaluation.geometry.metrics.build_navmesh import spawn_projection
from baselines.evaluation.geometry.metrics.build_navmesh import triangle_areas
from baselines.evaluation.geometry.metrics.build_navmesh import write_ply


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = Path(path).resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_text(path: Path, value: str) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def save_npz(path: Path, **arrays: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    temporary.replace(path)


def load_protocol() -> dict[str, Any]:
    return yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))


def load_specs(
    domain: str, protocol: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    protocol = protocol or load_protocol()
    path = REPO_ROOT / protocol["specs"][domain]
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 25 or [row["spec_index"] for row in rows] != list(range(25)):
        raise RuntimeError(f"Expected 25 ordered specs in {path}")
    if any(row["domain"] != domain for row in rows):
        raise RuntimeError(f"Domain mismatch in {path}")
    return rows


def rectangle(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def segment_rectangle(
    start: tuple[float, float], end: tuple[float, float], width: float
) -> list[list[float]]:
    left = np.asarray(start, dtype=float)
    right = np.asarray(end, dtype=float)
    delta = right - left
    length = float(np.linalg.norm(delta))
    if length <= 1e-8:
        raise ValueError("Reference segment has zero length")
    tangent = delta / length
    normal = np.asarray([-tangent[1], tangent[0]])
    half = 0.5 * width
    left = left - tangent * half
    right = right + tangent * half
    return [
        (left + normal * half).tolist(),
        (right + normal * half).tolist(),
        (right - normal * half).tolist(),
        (left - normal * half).tolist(),
    ]


def axis_sidewalks(
    axis: str,
    center: float,
    lower: float,
    upper: float,
    road_width: float,
    sidewalk_width: float,
) -> list[list[list[float]]]:
    offset = 0.5 * road_width + 0.5 * sidewalk_width
    if axis == "horizontal":
        return [
            segment_rectangle(
                (lower, center - offset), (upper, center - offset), sidewalk_width
            ),
            segment_rectangle(
                (lower, center + offset), (upper, center + offset), sidewalk_width
            ),
        ]
    return [
        segment_rectangle(
            (center - offset, lower), (center - offset, upper), sidewalk_width
        ),
        segment_rectangle(
            (center + offset, lower), (center + offset, upper), sidewalk_width
        ),
    ]


def reference_definition(
    spec: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    width, depth = float(spec["extent_m"][0]), float(spec["extent_m"][1])
    half_x, half_y = width / 2.0, depth / 2.0
    if spec["domain"] == "indoor":
        polygons = [rectangle(-half_x, -half_y, half_x, half_y)]
        spawn = [0.0, 0.0, 0.0]
        label = "centered_spec_extent_rectangle"
    else:
        config = protocol["reference"]["urban"]
        sidewalk = float(config["sidewalk_width_m"])
        road = float(config["road_width_m"])
        topology = spec["topology"]
        polygons: list[list[list[float]]] = []
        if topology == "four_way":
            polygons += axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, road, sidewalk
            )
            polygons += axis_sidewalks("vertical", 0.0, -half_y, half_y, road, sidewalk)
            spawn = [0.0, 0.5 * road + 0.5 * sidewalk, 0.0]
        elif topology == "t_junction":
            polygons += axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, road, sidewalk
            )
            polygons += axis_sidewalks("vertical", 0.0, 0.0, half_y, road, sidewalk)
            spawn = [0.0, 0.5 * road + 0.5 * sidewalk, 0.0]
        elif topology == "main_road_side_road":
            main = float(config["main_road_width_m"])
            side = float(config["side_road_width_m"])
            polygons += axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, main, sidewalk
            )
            polygons += axis_sidewalks("vertical", 0.0, 0.0, half_y, side, sidewalk)
            spawn = [0.0, 0.5 * main + 0.5 * sidewalk, 0.0]
        elif topology == "offset_intersection":
            offset = 12.0
            polygons += axis_sidewalks(
                "horizontal", -offset, -half_x, half_x, road, sidewalk
            )
            polygons += axis_sidewalks(
                "horizontal", offset, -half_x, half_x, road, sidewalk
            )
            polygons += axis_sidewalks(
                "vertical", -offset, -half_y, 0.0, road, sidewalk
            )
            polygons += axis_sidewalks("vertical", offset, 0.0, half_y, road, sidewalk)
            polygons.insert(0, segment_rectangle((-5.0, -5.0), (5.0, 5.0), sidewalk))
            spawn = [0.0, 0.0, 0.0]
        elif topology == "irregular_intersection":
            network = [
                ((-half_x, -18.0), (-15.0, -6.0)),
                ((-15.0, -6.0), (12.0, 7.0)),
                ((12.0, 7.0), (half_x, 20.0)),
                ((-5.0, -1.0), (-20.0, half_y)),
                ((5.0, 3.0), (22.0, -half_y)),
            ]
            polygons = [
                segment_rectangle(start, end, sidewalk) for start, end in network
            ]
            polygons.append(segment_rectangle((-7.0, -3.0), (7.0, 4.0), sidewalk))
            spawn = [0.0, 0.5, 0.0]
        else:
            raise ValueError(f"Unsupported urban topology: {topology}")
        label = f"pedestrian_corridors:{topology}"
    return {
        "type": label,
        "roi_xy_m": [
            [-half_x, -half_y],
            [half_x, -half_y],
            [half_x, half_y],
            [-half_x, half_y],
        ],
        "walkable_polygons_xy_m": polygons,
        "structural_spawn_candidate_m": spawn,
        "floor_z_m": 0.0,
    }


def points_in_polygons(
    points: np.ndarray, polygons: Iterable[list[list[float]]]
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


def reference_mesh(boundary: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for polygon in boundary["walkable_polygons_xy_m"]:
        offset = len(vertices)
        vertices.extend([[float(x), float(y), 0.0] for x, y in polygon])
        for index in range(1, len(polygon) - 1):
            faces.append([offset, offset + index, offset + index + 1])
    return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def recast_config(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        key: protocol[key]
        for key in ("agent", "recast", "postprocess", "spawn", "success")
    }


def reference_key(boundary: dict[str, Any], protocol: dict[str, Any]) -> str:
    return stable_hash(
        {
            "boundary": boundary,
            "recast": recast_config(protocol),
            "common_navmesh_sha256": sha256_file(COMMON_NAVMESH),
        }
    )


def ensure_reference(
    boundary: dict[str, Any], protocol: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    key = reference_key(boundary, protocol)
    directory = REFERENCE_ROOT / key
    metadata_path = directory / "metadata.json"
    if metadata_path.is_file() and (directory / "reference.navmesh").is_file():
        return directory, json.loads(metadata_path.read_text(encoding="utf-8"))
    directory.mkdir(parents=True, exist_ok=True)
    vertices, faces = reference_mesh(boundary)
    mesh_path = directory / "reference.ply"
    write_ply(mesh_path, vertices, faces)
    nav_vertices, nav_faces, metadata = build(
        mesh_path, recast_config(protocol), float(boundary["floor_z_m"])
    )
    if not len(nav_faces):
        raise RuntimeError(f"Reference Recast returned an empty mesh for {key}")
    area = float(triangle_areas(nav_vertices, nav_faces).sum())
    registered = spawn_projection(
        tuple(boundary["structural_spawn_candidate_m"]), nav_vertices, nav_faces
    )
    if not registered.get("projected"):
        raise RuntimeError(f"Reference spawn failed for {key}: {registered}")
    save_npz(
        directory / "reference.navmesh",
        vertices=nav_vertices.astype(np.float32),
        faces=nav_faces.astype(np.int32),
    )
    payload = {
        "key": key,
        "reference_area_m2": area,
        "registered_spawn": registered,
        "recast": metadata,
        "boundary": boundary,
    }
    atomic_json(metadata_path, payload)
    atomic_text(directory / "COMPLETE", "reference ready\n")
    return directory, payload


def latest_gaussian(run_dir: Path) -> Path:
    candidates: list[tuple[int, Path]] = []
    for path in (run_dir / "scene/gs/ply").glob("point_cloud_*.ply"):
        match = re.fullmatch(r"point_cloud_(\d+)\.ply", path.name)
        if match and path.is_file():
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise FileNotFoundError(f"No final Gaussian PLY under {run_dir}")
    return max(candidates)[1]


def source_artifacts(
    domain: str, spec_id: str, seed: int
) -> tuple[Path, dict[str, Path], dict[str, Any]]:
    run_dir = TABLE2_ROOT / domain / "hyworld2" / spec_id / f"seed_{seed}"
    paths = {
        "manifest": run_dir / "run_manifest.json",
        "spec": run_dir / "input/spec.json",
        "native_input": run_dir / "input/native_input.json",
        "position_meta": run_dir / "scene/gs/ply/position_meta_info.json",
        "cameras": run_dir / "scene/native/gs_data/cameras.json",
        "calibration_pcd": run_dir / "scene/native/render_results/global_pcd.ply",
    }
    paths["gaussian"] = latest_gaussian(run_dir)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing source artifacts in {run_dir}: {missing}")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    if not manifest.get("generation_success"):
        raise RuntimeError(f"Table-2 generation was not successful: {run_dir}")
    identity = (
        manifest.get("domain"),
        manifest.get("spec_id"),
        int(manifest.get("logical_seed", -1)),
    )
    if identity != (domain, spec_id, seed):
        raise RuntimeError(f"Source identity mismatch in {paths['manifest']}")
    return run_dir, paths, manifest


def load_xyz(path: Path) -> np.ndarray:
    vertex = PlyData.read(str(path))["vertex"]
    names = {property_.name for property_ in vertex.properties}
    if not {"x", "y", "z"}.issubset(names):
        raise RuntimeError(f"PLY has no xyz fields: {path}")
    points = np.column_stack([vertex[name] for name in ("x", "y", "z")]).astype(
        np.float32
    )
    if not np.isfinite(points).all() or not len(points):
        raise RuntimeError(f"PLY has empty or non-finite xyz: {path}")
    return points


def calibrate_scale(
    calibration_pcd: Path, domain: str, protocol: dict[str, Any]
) -> dict[str, Any]:
    config = protocol["scale_calibration"]
    points = load_xyz(calibration_pcd)
    negative = points[:, 2]
    negative = negative[
        np.isfinite(negative)
        & (negative < float(config["negative_height_cutoff_native"]))
    ]
    if len(negative) < int(config["minimum_mode_samples"]):
        raise RuntimeError(
            "Too few points below the generated camera to calibrate scale"
        )
    cutoff = float(np.quantile(negative, float(config["lower_histogram_fraction"])))
    lower = negative[negative <= cutoff]
    width = float(config["histogram_bin_width_native"])
    start = math.floor(float(lower.min()) / width) * width
    stop = math.ceil(float(lower.max()) / width) * width + width
    edges = np.arange(start, stop + 0.5 * width, width, dtype=np.float64)
    counts, edges = np.histogram(lower, bins=edges)
    mode_index = int(np.argmax(counts))
    mode_values = lower[(lower >= edges[mode_index]) & (lower < edges[mode_index + 1])]
    if len(mode_values) < int(config["minimum_mode_samples"]):
        raise RuntimeError(
            f"Floor mode has only {len(mode_values)} samples; "
            f"requires {config['minimum_mode_samples']}"
        )
    floor_z = float(np.median(mode_values))
    mad = float(np.median(np.abs(mode_values - floor_z)))
    if mad > float(config["maximum_mode_mad_native"]):
        raise RuntimeError(f"Floor-mode MAD {mad} exceeds the frozen limit")
    camera_height = float(config["nominal_camera_height_m"][domain])
    meters_per_native = camera_height / -floor_z
    if not (
        float(config["minimum_meters_per_native_unit"])
        <= meters_per_native
        <= float(config["maximum_meters_per_native_unit"])
    ):
        raise RuntimeError(f"Recovered scale is out of range: {meters_per_native}")
    return {
        "floor_z_native": floor_z,
        "floor_mode_mad_native": mad,
        "floor_mode_samples": int(len(mode_values)),
        "negative_samples": int(len(negative)),
        "lower_histogram_cutoff_native": cutoff,
        "histogram_bin_native": [
            float(edges[mode_index]),
            float(edges[mode_index + 1]),
        ],
        "nominal_camera_height_m": camera_height,
        "meters_per_native_unit": meters_per_native,
        "method": "lower-quarter z histogram mode anchored to nominal camera height",
    }


def transform_from_position_meta(meta: dict[str, Any]) -> np.ndarray:
    up = np.asarray(meta["up_direction"], dtype=np.float64)
    facing = np.asarray(meta["facing_direction"], dtype=np.float64)
    center = np.asarray(meta["center_point"], dtype=np.float64)
    up /= np.linalg.norm(up)
    facing /= np.linalg.norm(facing)
    column_x = -facing
    column_z = up
    column_y = np.cross(column_z, column_x)
    column_y /= np.linalg.norm(column_y)
    column_x = np.cross(column_y, column_z)
    column_x /= np.linalg.norm(column_x)
    rotation = np.column_stack((column_x, column_y, column_z))
    if np.linalg.det(rotation) < 0.999 or abs(float(np.dot(up, facing))) > 1e-5:
        raise RuntimeError("Invalid orientation basis in position_meta_info.json")
    scale = float(meta["scale"])
    if not math.isfinite(scale) or scale <= 0:
        raise RuntimeError(f"Invalid GS normalization scale: {scale}")
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = scale * rotation
    transform[:3, 3] = center
    return transform


def camera_rows(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    width, height = int(payload["width"]), int(payload["height"])
    rows = []
    for name, record in payload.items():
        if name in {"width", "height"} or not isinstance(record, dict):
            continue
        extrinsic = np.asarray(record.get("extrinsic"), dtype=np.float64)
        intrinsic = np.asarray(record.get("intrinsic"), dtype=np.float64)
        if extrinsic.shape != (4, 4) or intrinsic.shape != (3, 3):
            continue
        if not np.isfinite(extrinsic).all() or not np.isfinite(intrinsic).all():
            continue
        native_c2w = np.linalg.inv(extrinsic)
        rows.append(
            {
                "name": name,
                "native_c2w": native_c2w,
                "intrinsic": intrinsic,
            }
        )
    if not rows:
        raise RuntimeError(f"No valid final training cameras in {path}")
    return rows, width, height


def evenly_spaced(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda row: row["name"])
    if count <= 0:
        return []
    if len(rows) <= count:
        return rows
    indices = np.linspace(0, len(rows) - 1, count)
    return [rows[int(round(index))] for index in indices]


def farthest_camera_subset(
    rows: list[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda row: row["name"])
    if len(rows) <= count:
        return rows
    positions = np.asarray([row["native_c2w"][:3, 3] for row in rows])
    selected = [0]
    distances = np.linalg.norm(positions - positions[0], axis=1)
    while len(selected) < count:
        candidate = int(np.argmax(distances))
        if candidate in selected:
            candidate = next(
                index for index in range(len(rows)) if index not in selected
            )
        selected.append(candidate)
        new = np.linalg.norm(positions - positions[candidate], axis=1)
        distances = np.minimum(distances, new)
        distances[selected] = -1.0
    return [rows[index] for index in selected]


def select_cameras(
    rows: list[dict[str, Any]], protocol: dict[str, Any]
) -> list[dict[str, Any]]:
    config = protocol["surface_extraction"]
    panoramas = [row for row in rows if row["name"].startswith("panorama_")]
    polars = [row for row in rows if row["name"].startswith("polar_")]
    trajectories = [
        row for row in rows if not row["name"].startswith(("panorama_", "polar_"))
    ]
    selected = evenly_spaced(panoramas, int(config["panorama_views"]))
    selected += evenly_spaced(polars, int(config["polar_views"]))
    remaining = int(config["maximum_views"]) - len(selected)
    selected += farthest_camera_subset(trajectories, max(0, remaining))
    if len(selected) < int(config["maximum_views"]):
        used = {row["name"] for row in selected}
        extras = [row for row in rows if row["name"] not in used]
        selected += evenly_spaced(extras, int(config["maximum_views"]) - len(selected))
    return selected[: int(config["maximum_views"])]


def load_depth_splat(path: Path) -> dict[str, Any]:
    vertex = PlyData.read(str(path))["vertex"]
    names = {property_.name for property_ in vertex.properties}
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
        np.column_stack([vertex[f"scale_{index}"] for index in range(3)]).astype(
            np.float32
        )
    )
    opacities = np.asarray(vertex["opacity"], dtype=np.float32)
    opacities = 1.0 / (1.0 + np.exp(-opacities))
    arrays = (means, quats, scales, opacities)
    if not all(np.isfinite(array).all() for array in arrays):
        raise RuntimeError("Final Gaussian contains non-finite fields")
    return {
        "means": means,
        "quats": quats,
        "scales": np.clip(scales, 1e-6, None),
        "opacities": opacities,
        "gaussian_count": int(len(means)),
    }


def normalized_camera(native_c2w: np.ndarray, transform: np.ndarray) -> np.ndarray:
    camera = transform @ native_c2w
    scale = float(np.linalg.norm(camera[0, :3]))
    if not math.isfinite(scale) or scale <= 0:
        raise RuntimeError("Degenerate transformed camera")
    camera[:3, :3] /= scale
    camera[3] = [0.0, 0.0, 0.0, 1.0]
    return camera


def backproject_expected_depth(
    depth: np.ndarray,
    alpha: np.ndarray,
    intrinsic: np.ndarray,
    normalized_c2w: np.ndarray,
    inverse_transform: np.ndarray,
    calibration: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    config = protocol["surface_extraction"]
    height, width = depth.shape
    yy, xx = np.indices((height, width), dtype=np.float32)
    valid = (
        np.isfinite(depth)
        & np.isfinite(alpha)
        & (alpha >= float(config["alpha_threshold"]))
        & (depth >= float(config["near_plane_native"]))
        & (depth <= float(config["far_plane_native"]))
    )
    z = depth.astype(np.float64)
    camera_points = np.stack(
        (
            (xx - float(intrinsic[0, 2])) / float(intrinsic[0, 0]) * z,
            (yy - float(intrinsic[1, 2])) / float(intrinsic[1, 1]) * z,
            z,
        ),
        axis=-1,
    )
    normalized_world = camera_points @ normalized_c2w[:3, :3].T + normalized_c2w[:3, 3]
    native_world = (
        normalized_world @ inverse_transform[:3, :3].T + inverse_transform[:3, 3]
    )
    meters = native_world * float(calibration["meters_per_native_unit"])
    meters[..., 2] -= float(calibration["floor_z_native"]) * float(
        calibration["meters_per_native_unit"]
    )
    return meters.astype(np.float32), valid


def depth_grid_mesh(
    points: np.ndarray,
    valid: np.ndarray,
    boundary: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    config = protocol["surface_extraction"]
    stride = int(config["grid_stride"])
    row_indices = np.arange(0, points.shape[0], stride, dtype=np.int64)
    column_indices = np.arange(0, points.shape[1], stride, dtype=np.int64)
    if row_indices[-1] != points.shape[0] - 1:
        row_indices = np.append(row_indices, points.shape[0] - 1)
    if column_indices[-1] != points.shape[1] - 1:
        column_indices = np.append(column_indices, points.shape[1] - 1)
    sampled = points[np.ix_(row_indices, column_indices)]
    sampled_valid = valid[np.ix_(row_indices, column_indices)]
    height, width = sampled.shape[:2]
    grid = np.arange(height * width, dtype=np.int32).reshape(height, width)
    top_left, top_right = grid[:-1, :-1], grid[:-1, 1:]
    bottom_left, bottom_right = grid[1:, :-1], grid[1:, 1:]
    faces = np.concatenate(
        (
            np.stack((top_left, top_right, bottom_left), axis=-1).reshape(-1, 3),
            np.stack((top_right, bottom_right, bottom_left), axis=-1).reshape(-1, 3),
        ),
        axis=0,
    )
    vertices = sampled.reshape(-1, 3)
    vertex_valid = sampled_valid.reshape(-1)
    triangles = vertices[faces]
    face_valid = vertex_valid[faces].all(axis=1)
    edges = np.stack(
        (
            np.linalg.norm(triangles[:, 1] - triangles[:, 0], axis=1),
            np.linalg.norm(triangles[:, 2] - triangles[:, 1], axis=1),
            np.linalg.norm(triangles[:, 0] - triangles[:, 2], axis=1),
        ),
        axis=1,
    )
    areas = 0.5 * np.linalg.norm(
        np.cross(
            triangles[:, 1] - triangles[:, 0],
            triangles[:, 2] - triangles[:, 0],
        ),
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
    keep = (
        face_valid
        & np.isfinite(edges).all(axis=1)
        & (edges.max(axis=1) <= float(config["maximum_triangle_edge_m"]))
        & np.isfinite(areas)
        & (areas > 1e-10)
        & in_region
        & in_height
    )
    faces = faces[keep]
    if not len(faces):
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 3), dtype=np.int32),
            {
                "sampled_pixels": int(len(vertices)),
                "alpha_valid_pixels": int(sampled_valid.sum()),
                "retained_faces": 0,
            },
        )
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    compact_faces = remap[faces]
    compact_vertices = vertices[used].astype(np.float32)
    return (
        compact_vertices,
        compact_faces.astype(np.int32),
        {
            "sampled_pixels": int(len(vertices)),
            "alpha_valid_pixels": int(sampled_valid.sum()),
            "retained_vertices": int(len(compact_vertices)),
            "retained_faces": int(len(compact_faces)),
        },
    )


def render_final_surface(
    paths: dict[str, Path],
    boundary: dict[str, Any],
    calibration: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], dict[str, Any]]:
    import torch
    from gsplat.rendering import rasterization

    config = protocol["surface_extraction"]
    meta = json.loads(paths["position_meta"].read_text(encoding="utf-8"))
    transform = transform_from_position_meta(meta)
    inverse_transform = np.linalg.inv(transform)
    rows, source_width, source_height = camera_rows(paths["cameras"])
    selected = select_cameras(rows, protocol)
    splat = load_depth_splat(paths["gaussian"])
    device_arrays = {
        name: torch.from_numpy(splat[name]).to("cuda", dtype=torch.float32)
        for name in ("means", "quats", "scales", "opacities")
    }
    colors = torch.zeros(
        (splat["gaussian_count"], 1), device="cuda", dtype=torch.float32
    )
    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    evidence = []
    vertex_offset = 0
    target_width = int(config["render_width"])
    target_height = int(config["render_height"])
    for index, row in enumerate(selected):
        native_c2w = row["native_c2w"]
        camera = normalized_camera(native_c2w, transform)
        intrinsic = row["intrinsic"].copy()
        intrinsic[0] *= target_width / source_width
        intrinsic[1] *= target_height / source_height
        c2w_tensor = torch.from_numpy(camera).to("cuda", dtype=torch.float32)
        intrinsic_tensor = torch.from_numpy(intrinsic).to("cuda", dtype=torch.float32)
        with torch.inference_mode():
            rendered, alpha, _ = rasterization(
                means=device_arrays["means"],
                quats=device_arrays["quats"],
                scales=device_arrays["scales"],
                opacities=device_arrays["opacities"],
                colors=colors,
                viewmats=torch.linalg.inv(c2w_tensor)[None],
                Ks=intrinsic_tensor[None],
                width=target_width,
                height=target_height,
                render_mode="ED",
                near_plane=float(config["near_plane_native"]),
                far_plane=float(config["far_plane_native"]),
                radius_clip=0.0,
                packed=True,
            )
        depth = rendered[0, ..., 0].float().cpu().numpy()
        alpha_numpy = alpha[0, ..., 0].float().cpu().numpy()
        points, valid = backproject_expected_depth(
            depth,
            alpha_numpy,
            intrinsic,
            camera,
            inverse_transform,
            calibration,
            protocol,
        )
        vertices, faces, stats = depth_grid_mesh(points, valid, boundary, protocol)
        if len(faces):
            all_vertices.append(vertices)
            all_faces.append(faces + vertex_offset)
            vertex_offset += len(vertices)
        evidence.append(
            {
                "index": index,
                "camera": row["name"],
                "native_position": native_c2w[:3, 3].tolist(),
                "alpha_mean": float(alpha_numpy.mean()),
                "alpha_pass_pixels": int(valid.sum()),
                **stats,
            }
        )
        del rendered, alpha, depth, alpha_numpy, points, valid, vertices, faces
    del device_arrays, colors
    torch.cuda.empty_cache()
    if not all_faces:
        raise RuntimeError("Final Gaussian expected-depth reconstruction is empty")
    vertices = np.concatenate(all_vertices, axis=0)
    faces = np.concatenate(all_faces, axis=0)
    extraction = {
        "algorithm": "final Gaussian expected-depth grid triangulation",
        "parameters": config,
        "gaussian_count": splat["gaussian_count"],
        "available_cameras": len(rows),
        "selected_cameras": [row["name"] for row in selected],
        "mesh_vertices": int(len(vertices)),
        "mesh_faces": int(len(faces)),
        "per_view": evidence,
        "native_navmesh_used": False,
        "planning_point_cloud_used_as_scored_surface": False,
    }
    transform_record = {
        "gs_normalization_transform": transform.tolist(),
        "gs_to_native_transform": inverse_transform.tolist(),
        "native_to_meter": {
            "scale": calibration["meters_per_native_unit"],
            "floor_z_native": calibration["floor_z_native"],
            "translation_z_m": -calibration["floor_z_native"]
            * calibration["meters_per_native_unit"],
        },
        "coordinate_system": "right-handed Z-up",
        "unit": "meter",
    }
    return vertices, faces, extraction, transform_record


def load_navmesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path) as archive:
        return (
            np.asarray(archive["vertices"], dtype=np.float32),
            np.asarray(archive["faces"], dtype=np.int32),
        )


def draw_debug(
    path: Path,
    boundary: dict[str, Any],
    reference_vertices: np.ndarray,
    reference_faces: np.ndarray,
    final_vertices: np.ndarray,
    final_faces: np.ndarray,
    components: list[list[int]],
) -> None:
    roi = np.asarray(boundary["roi_xy_m"], dtype=float)
    lower, upper = roi.min(axis=0), roi.max(axis=0)
    span = np.maximum(upper - lower, 1e-6)
    size, margin = 1024, 32

    def pixel(point: Iterable[float]) -> tuple[int, int]:
        point = list(point)
        x = margin + (float(point[0]) - lower[0]) / span[0] * (size - 2 * margin)
        y = size - margin - (float(point[1]) - lower[1]) / span[1] * (size - 2 * margin)
        return round(x), round(y)

    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    for face in reference_faces:
        draw.polygon(
            [pixel(reference_vertices[index]) for index in face],
            fill=(203, 213, 225, 90),
        )
    palette = [
        (37, 99, 235, 190),
        (239, 68, 68, 190),
        (16, 185, 129, 190),
        (168, 85, 247, 190),
        (245, 158, 11, 190),
    ]
    face_component: dict[int, int] = {}
    for component_index, component in enumerate(components):
        for face_index in component:
            face_component[face_index] = component_index
    for face_index, face in enumerate(final_faces):
        color = palette[face_component.get(face_index, 0) % len(palette)]
        draw.polygon([pixel(final_vertices[index]) for index in face], fill=color)
    for polygon in boundary["walkable_polygons_xy_m"]:
        points = [pixel(point) for point in polygon]
        draw.line(points + points[:1], fill=(30, 41, 59, 180), width=1)
    sx, sy = pixel(boundary["structural_spawn_candidate_m"])
    draw.ellipse((sx - 6, sy - 6, sx + 6, sy + 6), fill=(0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def structural_na(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "method": "hyworld2",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "collision_rate": None,
        "floating_rate": None,
        "oob_rate": None,
        "support_validity": None,
        "valid_scene": None,
        "reason": "N/A-I",
        "detail": (
            "HY-World 2.0's final trained Gaussian has no recoverable native "
            "object instances or support graph."
        ),
    }


def failed_navigation(
    spec: dict[str, Any],
    seed: int,
    failure: dict[str, Any],
    source_manifest: dict[str, Any] | None = None,
    mesh_extraction_success: bool = False,
    scale_calibration_success: bool = False,
) -> dict[str, Any]:
    source_manifest = source_manifest or {}
    return {
        "method": "hyworld2",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "empty_reference_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "largest_component_area_m2": 0.0,
        "diagnostic_navigable_area_ratio_before_itt": 0.0,
        "diagnostic_connected_area_ratio_before_itt": 0.0,
        "navigable_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "navmesh_success": False,
        "mesh_extraction_success": mesh_extraction_success,
        "scale_calibration_success": scale_calibration_success,
        "spawn_check_passed": False,
        "component_count": 0,
        "native_navmesh_used": False,
        "failure_policy": "ITT zero for all three navigation metrics",
        "failures": [failure],
        "table2_generation_success": bool(source_manifest.get("generation_success")),
        "table2_render_success": bool(source_manifest.get("render_success")),
    }


def output_run(domain: str, spec_id: str, seed: int) -> Path:
    return DATA_ROOT / domain / "hyworld2" / spec_id / f"seed_{seed}"


def is_current(run_dir: Path) -> bool:
    manifest_path = run_dir / "run_manifest.json"
    metric_path = run_dir / "metrics/navigability.json"
    marker = run_dir / "EVALUATION_SUCCESS"
    if not all(path.is_file() for path in (manifest_path, metric_path, marker)):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "evaluator_sha256": sha256_file(Path(__file__)),
            "common_navmesh_sha256": sha256_file(COMMON_NAVMESH),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        if manifest.get("metric_sha256") != sha256_file(metric_path):
            return False
        collision = run_dir / "scene/canonical/collision.ply"
        if manifest.get("geometry_extracted"):
            return collision.is_file() and manifest.get(
                "collision_sha256"
            ) == sha256_file(collision)
        return True
    except Exception:
        return False


def relative_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source.resolve():
            return
        destination.unlink()
    elif destination.exists():
        return
    destination.symlink_to(os.path.relpath(source, destination.parent))


def run_one(domain: str, spec: dict[str, Any], seed: int) -> dict[str, Any]:
    run_dir = output_run(domain, spec["spec_id"], seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    if is_current(run_dir):
        metric = json.loads(
            (run_dir / "metrics/navigability.json").read_text(encoding="utf-8")
        )
        return {
            "domain": domain,
            "spec_id": spec["spec_id"],
            "seed": seed,
            "status": "resumed_current",
            "navmesh_success": bool(metric["navmesh_success"]),
            "navigable_area_ratio": float(metric["navigable_area_ratio"]),
            "connected_area_ratio": float(metric["connected_area_ratio"]),
        }
    started = time.monotonic()
    started_at = utc_now()
    source_run: Path | None = None
    paths: dict[str, Path] = {}
    source_manifest: dict[str, Any] = {}
    geometry_extracted = False
    scale_calibrated = False
    manifest: dict[str, Any] = {
        "protocol_id": load_protocol()["protocol_id"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "evaluator_sha256": sha256_file(Path(__file__)),
        "common_navmesh_sha256": sha256_file(COMMON_NAVMESH),
        "method_lock_sha256": sha256_file(METHOD_LOCK_PATH),
        "method": "hyworld2",
        "domain": domain,
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "started_at_utc": started_at,
        "native_navmesh_used": False,
    }
    atomic_json(run_dir / "input/spec.json", spec)
    atomic_json(run_dir / "metrics/structural.json", structural_na(spec, seed))
    try:
        protocol = load_protocol()
        source_run, paths, source_manifest = source_artifacts(
            domain, spec["spec_id"], seed
        )
        manifest.update(
            {
                "source_run": str(source_run),
                "source_final_gaussian": str(paths["gaussian"]),
                "source_final_gaussian_sha256": sha256_file(paths["gaussian"]),
                "source_calibration_pcd": str(paths["calibration_pcd"]),
                "source_calibration_pcd_sha256": sha256_file(paths["calibration_pcd"]),
                "source_table2_manifest_sha256": sha256_file(paths["manifest"]),
                "table2_generation_success": True,
                "table2_render_success": bool(source_manifest.get("render_success")),
            }
        )
        boundary = reference_definition(spec, protocol)
        atomic_json(run_dir / "input/boundaries.json", boundary)
        relative_link(paths["gaussian"], run_dir / "scene/raw/final_gaussian.ply")
        relative_link(
            paths["calibration_pcd"],
            run_dir / "scene/raw/calibration_global_pcd.ply",
        )
        calibration = calibrate_scale(paths["calibration_pcd"], domain, protocol)
        scale_calibrated = True
        vertices, faces, extraction, transform_record = render_final_surface(
            paths, boundary, calibration, protocol
        )
        canonical = run_dir / "scene/canonical"
        canonical.mkdir(parents=True, exist_ok=True)
        collision_path = canonical / "collision.ply"
        write_ply(collision_path, vertices, faces)
        atomic_json(canonical / "transform.json", transform_record)
        atomic_json(
            canonical / "instances.json",
            {
                "coordinate_system": "right-handed Z-up",
                "unit": "meter",
                "instances": [],
                "reason": "N/A-I",
            },
        )
        geometry_extracted = True
        reference_dir, reference_meta = ensure_reference(boundary, protocol)
        relative_link(
            reference_dir / "reference.ply",
            canonical / "empty_reference.ply",
        )
        reference_vertices, reference_faces = load_navmesh(
            reference_dir / "reference.navmesh"
        )
        final_vertices, final_faces, final_recast = build(
            collision_path, recast_config(protocol), 0.0
        )
        reference_area = float(reference_meta["reference_area_m2"])
        final_area = float(triangle_areas(final_vertices, final_faces).sum())
        components, component_areas = connected_components(final_vertices, final_faces)
        largest = component_areas[0] if component_areas else 0.0
        registered = reference_meta["registered_spawn"]
        final_spawn = (
            spawn_projection(tuple(registered["point_m"]), final_vertices, final_faces)
            if registered.get("projected")
            else {"projected": False, "horizontal_distance_m": None}
        )
        spawn_ok = bool(final_spawn.get("projected"))
        minimum_fraction = float(protocol["success"]["minimum_reference_area_fraction"])
        builder_ok = bool(final_recast.get("builder_returned"))
        navmesh_success = bool(
            builder_ok
            and reference_area > 0.0
            and np.isfinite(final_area)
            and final_area >= minimum_fraction * reference_area
            and spawn_ok
        )
        raw_navigable = (
            100.0 * min(1.0, max(0.0, final_area / reference_area))
            if reference_area > 0.0
            else 0.0
        )
        raw_connected = 100.0 * largest / final_area if final_area > 0.0 else 0.0
        navigable = raw_navigable if navmesh_success else 0.0
        connected = raw_connected if navmesh_success else 0.0
        navigation_dir = run_dir / "navigation"
        navigation_dir.mkdir(parents=True, exist_ok=True)
        save_npz(
            navigation_dir / "empty_reference.navmesh",
            vertices=reference_vertices,
            faces=reference_faces,
        )
        save_npz(
            navigation_dir / "final.navmesh",
            vertices=final_vertices,
            faces=final_faces,
        )
        write_ply(navigation_dir / "final.navmesh.ply", final_vertices, final_faces)
        atomic_json(
            navigation_dir / "components.json",
            {
                "component_count": len(components),
                "component_areas_m2": component_areas,
                "components": components,
            },
        )
        draw_debug(
            navigation_dir / "debug_topdown.png",
            boundary,
            reference_vertices,
            reference_faces,
            final_vertices,
            final_faces,
            components,
        )
        metric = {
            "method": "hyworld2",
            "domain": domain,
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "track": "surface_only",
            "empty_reference_area_m2": reference_area,
            "final_navmesh_area_m2": final_area,
            "largest_component_area_m2": largest,
            "diagnostic_navigable_area_ratio_before_itt": raw_navigable,
            "diagnostic_connected_area_ratio_before_itt": raw_connected,
            "navigable_area_ratio": navigable,
            "connected_area_ratio": connected,
            "navmesh_success": navmesh_success,
            "mesh_extraction_success": True,
            "scale_calibration_success": True,
            "spawn_check_passed": spawn_ok,
            "component_count": len(components),
            "registered_spawn": registered,
            "final_spawn_projection": final_spawn,
            "scale_calibration": calibration,
            "surface_extraction": extraction,
            "reference_key": reference_meta["key"],
            "reference_recast": reference_meta["recast"],
            "final_recast": final_recast,
            "native_navmesh_used": False,
            "failure_policy": "ITT zero for all three metrics when success is false",
            "failures": (
                []
                if navmesh_success
                else [
                    {
                        "type": "navmesh_success_predicate_failed",
                        "message": (
                            "build, area, or spawn predicate failed; all three "
                            "surface-only metrics use ITT zero"
                        ),
                    }
                ]
            ),
            "table2_generation_success": bool(
                source_manifest.get("generation_success")
            ),
            "table2_render_success": bool(source_manifest.get("render_success")),
        }
        manifest.update(
            {
                "source_run": str(source_run),
                "source_final_gaussian": str(paths["gaussian"]),
                "source_final_gaussian_sha256": sha256_file(paths["gaussian"]),
                "source_calibration_pcd": str(paths["calibration_pcd"]),
                "source_calibration_pcd_sha256": sha256_file(paths["calibration_pcd"]),
                "source_table2_manifest_sha256": sha256_file(paths["manifest"]),
                "table2_generation_success": True,
                "table2_render_success": bool(source_manifest.get("render_success")),
                "scale_calibration": calibration,
                "surface_extraction": {
                    key: extraction[key]
                    for key in (
                        "algorithm",
                        "gaussian_count",
                        "available_cameras",
                        "selected_cameras",
                        "mesh_vertices",
                        "mesh_faces",
                        "native_navmesh_used",
                    )
                },
                "reference_key": reference_meta["key"],
            }
        )
    except Exception as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        atomic_text(run_dir / "logs/evaluation_error.log", failure["traceback"])
        metric = failed_navigation(
            spec,
            seed,
            failure,
            source_manifest,
            mesh_extraction_success=geometry_extracted,
            scale_calibration_success=scale_calibrated,
        )
    metric_path = run_dir / "metrics/navigability.json"
    atomic_json(metric_path, metric)
    atomic_text(
        run_dir / "EVALUATION_SUCCESS",
        "HY-World 2.0 Table-3 measurement completed under ITT\n",
    )
    manifest.update(
        {
            "geometry_extracted": geometry_extracted,
            "scale_calibrated": scale_calibrated,
            "navmesh_success": bool(metric["navmesh_success"]),
            "evaluation_completed": True,
            "failure_count": len(metric["failures"]),
            "metric_sha256": sha256_file(metric_path),
            "collision_sha256": (
                sha256_file(run_dir / "scene/canonical/collision.ply")
                if geometry_extracted
                else None
            ),
            "ended_at_utc": utc_now(),
            "wall_time_s": time.monotonic() - started,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        }
    )
    atomic_json(run_dir / "run_manifest.json", manifest)
    return {
        "domain": domain,
        "spec_id": spec["spec_id"],
        "seed": seed,
        "status": "complete",
        "geometry_extracted": geometry_extracted,
        "scale_calibrated": scale_calibrated,
        "navmesh_success": bool(metric["navmesh_success"]),
        "navigable_area_ratio": float(metric["navigable_area_ratio"]),
        "connected_area_ratio": float(metric["connected_area_ratio"]),
        "failure_count": len(metric["failures"]),
        "failure_type": metric["failures"][0]["type"] if metric["failures"] else None,
        "wall_time_s": manifest["wall_time_s"],
    }


def expected_tasks(
    phase: str, domains: list[str], protocol: dict[str, Any]
) -> list[tuple[str, dict[str, Any], int]]:
    tasks: list[tuple[str, dict[str, Any], int]] = []
    pilot = set(int(index) for index in protocol["pilot_spec_indices"])
    for domain in domains:
        for spec in load_specs(domain, protocol):
            if phase == "pilot" and int(spec["spec_index"]) not in pilot:
                continue
            for seed in protocol["seeds"]:
                tasks.append((domain, spec, int(seed)))
    return tasks


def configure_worker(gpu: int, worker_index: int) -> None:
    work = (PACKAGE_ROOT / "work") / f"gpu_{gpu}_worker_{worker_index}"
    for directory in (
        work,
        work / "tmp",
        work / "cache",
        work / "torch",
        work / "xdg",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["CUDA_HOME"] = "/usr/local/cuda-12.4"
    os.environ["PATH"] = "/usr/local/cuda-12.4/bin:" + os.environ.get("PATH", "")
    os.environ["TORCH_CUDA_ARCH_LIST"] = "8.9"
    os.environ["CPATH"] = str((PACKAGE_ROOT / "vendor/glm")) + (
        ":" + os.environ["CPATH"] if os.environ.get("CPATH") else ""
    )
    os.environ["TORCH_EXTENSIONS_DIR"] = str(
        (PACKAGE_ROOT / "cache/torch_extensions_glibc231")
    )
    os.environ["MAX_JOBS"] = "10"
    os.environ["TMPDIR"] = str(work / "tmp")
    os.environ["XDG_CACHE_HOME"] = str(work / "xdg")
    os.environ["TORCH_HOME"] = str(work / "torch")
    os.environ["PYTHONUNBUFFERED"] = "1"


def matrix_worker(
    gpu: int,
    worker_index: int,
    tasks: list[tuple[str, dict[str, Any], int]],
    phase: str,
) -> None:
    configure_worker(gpu, worker_index)
    log_path = (PACKAGE_ROOT / "logs") / f"{phase}_gpu_{gpu}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        for task_index, (domain, spec, seed) in enumerate(tasks, start=1):
            result = run_one(domain, spec, seed)
            result.update(
                {
                    "logged_at_utc": utc_now(),
                    "gpu": gpu,
                    "worker_index": worker_index,
                    "worker_task_index": task_index,
                    "worker_task_count": len(tasks),
                }
            )
            line = json.dumps(result, ensure_ascii=False, sort_keys=True)
            log.write(line + "\n")
            log.flush()
            print(line, flush=True)


def run_matrix(phase: str, domains: list[str], gpus: list[int]) -> None:
    protocol = load_protocol()
    invalid_domains = set(domains) - set(protocol["domains"])
    if invalid_domains:
        raise ValueError(f"Unknown domains: {sorted(invalid_domains)}")
    if not gpus:
        raise ValueError("At least one GPU is required")
    tasks = expected_tasks(phase, domains, protocol)
    pending = [
        task
        for task in tasks
        if not is_current(output_run(task[0], task[1]["spec_id"], task[2]))
    ]
    print(
        json.dumps(
            {
                "phase": phase,
                "domains": domains,
                "expected": len(tasks),
                "already_current": len(tasks) - len(pending),
                "pending": len(pending),
                "gpus": gpus,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if not pending:
        return
    assignments = [pending[index :: len(gpus)] for index in range(len(gpus))]
    context = mp.get_context("spawn")
    processes = []
    for worker_index, (gpu, assignment) in enumerate(zip(gpus, assignments)):
        if not assignment:
            continue
        process = context.Process(
            target=matrix_worker,
            args=(gpu, worker_index, assignment, phase),
            name=f"hyworld2-table3-gpu-{gpu}",
        )
        process.start()
        processes.append(process)
    failures = []
    for process in processes:
        process.join()
        if process.exitcode != 0:
            failures.append((process.name, process.exitcode))
    if failures:
        raise RuntimeError(f"Matrix workers failed: {failures}")


def create_inventory() -> dict[str, Any]:
    protocol = load_protocol()
    payload: dict[str, Any] = {
        "created_at_utc": utc_now(),
        "source_root": str(TABLE2_ROOT),
        "regeneration_performed": False,
        "downloads_performed": False,
        "domains": {},
    }
    for domain in protocol["domains"]:
        counters: Counter[str] = Counter()
        gaussian_bytes = 0
        calibration_bytes = 0
        problems = []
        for domain_name, spec, seed in expected_tasks("formal", [domain], protocol):
            counters["expected"] += 1
            try:
                _, paths, manifest = source_artifacts(
                    domain_name, spec["spec_id"], seed
                )
                counters["source_complete"] += 1
                counters["generation_success"] += int(
                    bool(manifest.get("generation_success"))
                )
                counters["table2_render_success"] += int(
                    bool(manifest.get("render_success"))
                )
                counters["table2_render_failure"] += int(
                    not bool(manifest.get("render_success"))
                )
                gaussian_bytes += paths["gaussian"].stat().st_size
                calibration_bytes += paths["calibration_pcd"].stat().st_size
            except Exception as error:
                counters["source_incomplete"] += 1
                problems.append(
                    {
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "error": str(error),
                    }
                )
        payload["domains"][domain] = {
            **dict(counters),
            "final_gaussian_bytes": gaussian_bytes,
            "calibration_pcd_bytes": calibration_bytes,
            "problems": problems,
        }
    payload["complete"] = all(
        row.get("source_complete") == row.get("expected")
        for row in payload["domains"].values()
    )
    atomic_json((RESULTS_ROOT / "reuse_inventory.json"), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if not payload["complete"]:
        raise RuntimeError("The reusable Table-2 source matrix is incomplete")
    return payload


def create_metrics_lock() -> dict[str, Any]:
    import gsplat
    import recast

    recast_path = Path(recast.__file__).resolve()
    gsplat_path = Path(gsplat.__file__).resolve()
    local_gsplat_extension = (
        PACKAGE_ROOT / "cache/torch_extensions_glibc231/gsplat_cuda/gsplat_cuda.so"
    )
    if not local_gsplat_extension.is_file():
        raise RuntimeError(
            f"Local ABI-compatible gsplat extension is missing: {local_gsplat_extension}"
        )
    payload = {
        "created_at_utc": utc_now(),
        "protocol_id": load_protocol()["protocol_id"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "method_lock_sha256": sha256_file(METHOD_LOCK_PATH),
        "evaluator": str(Path(__file__).resolve()),
        "evaluator_sha256": sha256_file(Path(__file__)),
        "common_navmesh": str(COMMON_NAVMESH.resolve()),
        "common_navmesh_sha256": sha256_file(COMMON_NAVMESH),
        "recast_binary": str(recast_path),
        "recast_binary_sha256": sha256_file(recast_path),
        "gsplat_module": str(gsplat_path),
        "gsplat_module_sha256": sha256_file(gsplat_path),
        "gsplat_cuda_extension": str(local_gsplat_extension.resolve()),
        "gsplat_cuda_extension_sha256": sha256_file(local_gsplat_extension),
        "cuda_toolkit": "/usr/local/cuda-12.4",
        "cuda_arch": "8.9",
        "native_navmesh_scored": False,
    }
    atomic_json(METRICS_LOCK_PATH, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def bootstrap_interval(spec_values: np.ndarray, repeats: int, seed: int) -> list[float]:
    if len(spec_values) == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(spec_values), size=(repeats, len(spec_values)))
    estimates = spec_values[samples].mean(axis=1)
    return [float(value) for value in np.quantile(estimates, [0.025, 0.975])]


def aggregate_domain(
    domain: str, rows: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, Any]:
    metrics = (
        "navigable_area_ratio",
        "connected_area_ratio",
        "navmesh_success_percent",
    )
    by_spec: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(row)
    spec_rows = []
    for spec_id in sorted(by_spec):
        group = by_spec[spec_id]
        spec_rows.append(
            {
                "spec_id": spec_id,
                "n": len(group),
                "navigable_area_ratio": float(
                    np.mean([row["navigable_area_ratio"] for row in group])
                ),
                "connected_area_ratio": float(
                    np.mean([row["connected_area_ratio"] for row in group])
                ),
                "navmesh_success_percent": float(
                    100.0 * np.mean([row["navmesh_success"] for row in group])
                ),
            }
        )
    aggregate: dict[str, Any] = {
        "domain": domain,
        "run_count": len(rows),
        "spec_count": len(spec_rows),
        "order": protocol["aggregation"]["order"],
        "failure_policy": protocol["aggregation"]["failure_policy"],
        "structured_metrics": {
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "valid_scene": "N/A-I",
        },
        "per_spec": spec_rows,
        "failure_types": dict(
            Counter(
                failure["type"] for row in rows for failure in row.get("failures", [])
            )
        ),
        "mesh_extraction_success_count": sum(
            bool(row["mesh_extraction_success"]) for row in rows
        ),
        "scale_calibration_success_count": sum(
            bool(row["scale_calibration_success"]) for row in rows
        ),
        "navmesh_success_count": sum(bool(row["navmesh_success"]) for row in rows),
    }
    repeats = int(protocol["aggregation"]["bootstrap_repeats"])
    bootstrap_seed = int(protocol["aggregation"]["bootstrap_seed"])
    for offset, name in enumerate(metrics):
        values = np.asarray([row[name] for row in spec_rows], dtype=float)
        aggregate[name] = float(values.mean())
        aggregate[f"{name}_95ci"] = bootstrap_interval(
            values, repeats, bootstrap_seed + offset
        )
    return aggregate


def aggregate_results() -> dict[str, Any]:
    protocol = load_protocol()
    expected = expected_tasks("formal", list(protocol["domains"]), protocol)
    rows: list[dict[str, Any]] = []
    missing = []
    for domain, spec, seed in expected:
        metric_path = (
            output_run(domain, spec["spec_id"], seed) / "metrics/navigability.json"
        )
        if not metric_path.is_file():
            missing.append(str(metric_path))
            continue
        rows.append(json.loads(metric_path.read_text(encoding="utf-8")))
    if missing:
        raise RuntimeError(f"Cannot aggregate: {len(missing)} metrics are missing")
    payload = {
        "created_at_utc": utc_now(),
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "evaluator_sha256": sha256_file(Path(__file__)),
        "metrics_lock_sha256": (
            sha256_file(METRICS_LOCK_PATH) if METRICS_LOCK_PATH.is_file() else None
        ),
        "method": "hyworld2",
        "display_name": "HY-World 2.0",
        "track": "surface_only",
        "total_run_count": len(rows),
        "domains": {
            domain: aggregate_domain(
                domain,
                [row for row in rows if row["domain"] == domain],
                protocol,
            )
            for domain in protocol["domains"]
        },
    }
    atomic_json((RESULTS_ROOT / "table3_full.json"), payload)
    header = [
        "domain",
        "spec_id",
        "logical_seed",
        "navigable_area_ratio",
        "connected_area_ratio",
        "navmesh_success",
        "mesh_extraction_success",
        "scale_calibration_success",
        "failure_type",
    ]
    lines = [",".join(header)]
    for row in sorted(
        rows, key=lambda item: (item["domain"], item["spec_id"], item["logical_seed"])
    ):
        lines.append(
            ",".join(
                [
                    str(row["domain"]),
                    str(row["spec_id"]),
                    str(row["logical_seed"]),
                    f"{float(row['navigable_area_ratio']):.9f}",
                    f"{float(row['connected_area_ratio']):.9f}",
                    str(int(bool(row["navmesh_success"]))),
                    str(int(bool(row["mesh_extraction_success"]))),
                    str(int(bool(row["scale_calibration_success"]))),
                    (row.get("failures") or [{}])[0].get("type", ""),
                ]
            )
        )
    atomic_text((RESULTS_ROOT / "per_run.csv"), "\n".join(lines) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


def create_montage(tasks: list[tuple[str, dict[str, Any], int]], output: Path) -> None:
    tile_width, tile_height = 240, 268
    tiles = []
    for domain, spec, seed in tasks:
        source = (
            output_run(domain, spec["spec_id"], seed) / "navigation/debug_topdown.png"
        )
        tile = Image.new("RGB", (tile_width, tile_height), "white")
        draw = ImageDraw.Draw(tile)
        if source.is_file():
            image = Image.open(source).convert("RGB")
            image.thumbnail((tile_width, tile_width))
            tile.paste(image, ((tile_width - image.width) // 2, 0))
        else:
            draw.rectangle((8, 8, tile_width - 8, tile_width - 8), outline="red")
            draw.text((15, 105), "NO NAVMESH DEBUG", fill="red")
        draw.text(
            (5, 244),
            f"{domain} {spec['spec_id']} s{seed}",
            fill="black",
        )
        tiles.append(tile)
    columns = 4
    rows = math.ceil(len(tiles) / columns)
    montage = Image.new("RGB", (columns * tile_width, rows * tile_height), "white")
    for index, tile in enumerate(tiles):
        montage.paste(
            tile, ((index % columns) * tile_width, (index // columns) * tile_height)
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    montage.save(output)


def audit_results(phase: str) -> dict[str, Any]:
    protocol = load_protocol()
    tasks = expected_tasks(phase, list(protocol["domains"]), protocol)
    problems = []
    completed = 0
    geometry = 0
    success = 0
    for domain, spec, seed in tasks:
        run_dir = output_run(domain, spec["spec_id"], seed)
        metric_path = run_dir / "metrics/navigability.json"
        manifest_path = run_dir / "run_manifest.json"
        if not metric_path.is_file() or not manifest_path.is_file():
            problems.append(f"missing result: {domain}/{spec['spec_id']}/seed_{seed}")
            continue
        try:
            metric = json.loads(metric_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            completed += 1
            geometry += int(bool(metric["mesh_extraction_success"]))
            success += int(bool(metric["navmesh_success"]))
            for name in ("navigable_area_ratio", "connected_area_ratio"):
                value = float(metric[name])
                if not math.isfinite(value) or value < 0.0 or value > 100.0:
                    problems.append(f"invalid {name}: {run_dir}")
            if not metric["navmesh_success"] and any(
                float(metric[name]) != 0.0
                for name in ("navigable_area_ratio", "connected_area_ratio")
            ):
                problems.append(f"ITT zero violated: {run_dir}")
            if metric.get("native_navmesh_used") is not False:
                problems.append(f"native navmesh flag violated: {run_dir}")
            if manifest.get("native_navmesh_used") is not False:
                problems.append(f"manifest native navmesh flag violated: {run_dir}")
            final_source = str(manifest.get("source_final_gaussian", ""))
            if "scene/gs/ply/point_cloud_" not in final_source:
                problems.append(f"wrong scored representation: {run_dir}")
            if manifest.get("metric_sha256") != sha256_file(metric_path):
                problems.append(f"metric hash mismatch: {run_dir}")
        except Exception as error:
            problems.append(f"audit exception {run_dir}: {error}")
    if phase == "pilot":
        create_montage(tasks, (RESULTS_ROOT / "pilot_montage.png"))
    payload = {
        "created_at_utc": utc_now(),
        "phase": phase,
        "expected": len(tasks),
        "completed": completed,
        "geometry_extraction_success": geometry,
        "navmesh_success": success,
        "problem_count": len(problems),
        "problems": problems,
        "native_navmesh_used": False,
    }
    atomic_json(RESULTS_ROOT / f"audit_{phase}.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if problems:
        raise RuntimeError(f"Audit found {len(problems)} problems")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    subparsers.add_parser("lock")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    run_parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    run_parser.add_argument("--gpus", nargs="+", type=int, required=True)
    subparsers.add_parser("aggregate")
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--phase", choices=("pilot", "formal"), default="formal")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "inventory":
        create_inventory()
    elif args.command == "lock":
        create_metrics_lock()
    elif args.command == "run":
        run_matrix(args.phase, args.domains, args.gpus)
    elif args.command == "aggregate":
        aggregate_results()
    elif args.command == "audit":
        audit_results(args.phase)


if __name__ == "__main__":
    main()
