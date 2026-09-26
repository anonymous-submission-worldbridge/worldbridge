#!/usr/bin/env python3
"""Auditable surface-only Table 3 evaluator for ZiYang-xie/WorldGen.

The evaluator reuses the ordered Gaussian splats produced for Table 2.  WorldGen's
default splat has one Gaussian per panorama pixel, so its centers retain the
native RGB-D sampling grid.  We deterministically triangulate that grid, recover
metric scale from the frozen camera-height anchor and the nadir floor cap, crop
to the preregistered walkable reference, and rebuild Recast without connecting
or discarding components.
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
import concurrent.futures
import hashlib
import json
import math
import os
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
PACKAGE_ROOT = BASELINES / "methods/worldgen/geometry"
PROTOCOL_PATH = BASELINES / "methods/worldgen/protocol/geometry/geometry_worldgen.yaml"
METHOD_LOCK_PATH = (
    BASELINES / "methods/worldgen/protocol/geometry/geometry_worldgen_method.lock.json"
)
METRICS_LOCK_PATH = (
    BASELINES / "methods/worldgen/protocol/geometry/geometry_worldgen_metrics.lock.json"
)
TABLE2_ROOT = BASELINES / "data/table2"
DATA_ROOT = BASELINES / "data/table3_worldgen"
RESULTS_ROOT = BASELINES / "results/table3_worldgen"
REFERENCE_CACHE = PACKAGE_ROOT / "cache/reference"
RECAST_RUNTIME = PACKAGE_ROOT / "runtime/recast_glibc231_clean2"
PILOT_INDICES = {0, 5, 10, 15, 20}

if str(RECAST_RUNTIME) not in sys.path:
    sys.path.insert(0, str(RECAST_RUNTIME))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.evaluation.geometry.metrics.build_navmesh import build
from baselines.evaluation.geometry.metrics.build_navmesh import connected_components
from baselines.evaluation.geometry.metrics.build_navmesh import spawn_projection
from baselines.evaluation.geometry.metrics.build_navmesh import triangle_areas
from baselines.evaluation.geometry.metrics.build_navmesh import write_ply


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must remain below {BASELINES}: {resolved}") from exc
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_specs(domain: str, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    path = REPO_ROOT / protocol["specs"][domain]
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 25 or [row["spec_index"] for row in rows] != list(range(25)):
        raise RuntimeError(f"Expected 25 ordered {domain} specs in {path}")
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


def _axis_sidewalks(
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
    width, depth = (float(spec["extent_m"][0]), float(spec["extent_m"][1]))
    half_x, half_y = width / 2.0, depth / 2.0
    if spec["domain"] == "indoor":
        polygons = [rectangle(-half_x, -half_y, half_x, half_y)]
        spawn = [0.0, 0.0, 0.0]
        label = "centered_spec_extent_rectangle"
    else:
        cfg = protocol["reference"]["urban"]
        sidewalk = float(cfg["sidewalk_width_m"])
        road = float(cfg["road_width_m"])
        topology = spec["topology"]
        polygons: list[list[list[float]]] = []
        if topology == "four_way":
            polygons += _axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, road, sidewalk
            )
            polygons += _axis_sidewalks(
                "vertical", 0.0, -half_y, half_y, road, sidewalk
            )
            spawn = [0.0, 0.5 * road + 0.5 * sidewalk, 0.0]
        elif topology == "t_junction":
            polygons += _axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, road, sidewalk
            )
            polygons += _axis_sidewalks("vertical", 0.0, 0.0, half_y, road, sidewalk)
            spawn = [0.0, 0.5 * road + 0.5 * sidewalk, 0.0]
        elif topology == "main_road_side_road":
            main = float(cfg["main_road_width_m"])
            side = float(cfg["side_road_width_m"])
            polygons += _axis_sidewalks(
                "horizontal", 0.0, -half_x, half_x, main, sidewalk
            )
            polygons += _axis_sidewalks("vertical", 0.0, 0.0, half_y, side, sidewalk)
            spawn = [0.0, 0.5 * main + 0.5 * sidewalk, 0.0]
        elif topology == "offset_intersection":
            offset = 12.0
            polygons += _axis_sidewalks(
                "horizontal", -offset, -half_x, half_x, road, sidewalk
            )
            polygons += _axis_sidewalks(
                "horizontal", offset, -half_x, half_x, road, sidewalk
            )
            polygons += _axis_sidewalks(
                "vertical", -offset, -half_y, 0.0, road, sidewalk
            )
            polygons += _axis_sidewalks("vertical", offset, 0.0, half_y, road, sidewalk)
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
    x = points[:, 0]
    y = points[:, 1]
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


def sample_indices(size: int, stride: int) -> np.ndarray:
    result = np.arange(0, size, stride, dtype=np.int64)
    if result[-1] != size - 1:
        result = np.append(result, size - 1)
    return result


def calibrate_scale(
    points_native: np.ndarray, domain: str, protocol: dict[str, Any]
) -> dict[str, float]:
    cfg = protocol["scale_calibration"]
    fraction = float(cfg["floor_cap_bottom_fraction"])
    start = max(0, int(math.floor(points_native.shape[0] * (1.0 - fraction))))
    values = points_native[start:, :, 1].reshape(-1).astype(np.float64)
    values = values[np.isfinite(values)]
    floor_native = float(np.median(values))
    mad = float(np.median(np.abs(values - floor_native)))
    relative_mad = mad / max(abs(floor_native), 1e-12)
    minimum = float(cfg["minimum_native_floor_distance"])
    if floor_native <= minimum:
        raise RuntimeError(
            f"Nadir floor distance {floor_native:.8g} is not positive/observable"
        )
    if relative_mad > float(cfg["maximum_relative_mad"]):
        raise RuntimeError(
            f"Nadir floor relative MAD {relative_mad:.6f} exceeds frozen threshold"
        )
    camera_height = float(cfg["nominal_camera_height_m"][domain])
    scale = camera_height / floor_native
    if not math.isfinite(scale) or scale <= 0.0:
        raise RuntimeError(f"Recovered scale {scale:.8g} is not finite and positive")
    return {
        "native_floor_y": floor_native,
        "native_floor_mad": mad,
        "native_floor_relative_mad": relative_mad,
        "nominal_camera_height_m": camera_height,
        "meters_per_native_unit": scale,
        "floor_sample_row_start": start,
        "floor_sample_count": int(len(values)),
    }


def load_ordered_centers(
    splat_path: Path, protocol: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    vertex = PlyData.read(str(splat_path))["vertex"].data
    cfg = protocol["surface_extraction"]
    height = int(cfg["expected_panorama_height"])
    width = int(cfg["expected_panorama_width"])
    if len(vertex) != height * width:
        raise RuntimeError(
            f"Ordered-splat contract failed: {len(vertex)} vertices, expected {height * width}"
        )
    names = set(vertex.dtype.names or ())
    if not {"x", "y", "z"}.issubset(names):
        raise RuntimeError("Splat PLY does not contain xyz centers")
    points = np.column_stack([vertex[name] for name in ("x", "y", "z")]).astype(
        np.float32
    )
    if not np.isfinite(points).all():
        raise RuntimeError("Splat centers contain non-finite values")
    return points.reshape(height, width, 3), {
        "ordered_vertex_count": int(len(vertex)),
        "native_grid": [height, width],
    }


def extract_surface(
    points_native: np.ndarray,
    scale: dict[str, float],
    boundary: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cfg = protocol["surface_extraction"]
    stride = int(cfg["grid_stride"])
    rows = sample_indices(points_native.shape[0], stride)
    cols = sample_indices(points_native.shape[1], stride)
    sampled = points_native[np.ix_(rows, cols)]
    meters_per_native = float(scale["meters_per_native_unit"])
    camera_height = float(scale["nominal_camera_height_m"])
    # WorldGen/OpenCV xyz -> right-handed Z-up x,z,-y, then place the nadir floor at z=0.
    vertices = np.stack(
        [sampled[..., 0], sampled[..., 2], -sampled[..., 1]], axis=-1
    ).reshape(-1, 3)
    vertices *= meters_per_native
    vertices[:, 2] += camera_height

    h, w = sampled.shape[:2]
    grid = np.arange(h * w, dtype=np.int32).reshape(h, w)
    tl, tr = grid[:-1, :-1], grid[:-1, 1:]
    bl, br = grid[1:, :-1], grid[1:, 1:]
    faces = np.concatenate(
        [
            np.stack([tl, tr, bl], axis=-1).reshape(-1, 3),
            np.stack([tr, br, bl], axis=-1).reshape(-1, 3),
        ],
        axis=0,
    )
    triangles = vertices[faces]
    edges = np.stack(
        [
            np.linalg.norm(triangles[:, 1] - triangles[:, 0], axis=1),
            np.linalg.norm(triangles[:, 2] - triangles[:, 1], axis=1),
            np.linalg.norm(triangles[:, 0] - triangles[:, 2], axis=1),
        ],
        axis=1,
    )
    maximum_edge = edges.max(axis=1)
    areas = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    centers = triangles.mean(axis=1)
    region = points_in_polygons(centers[:, :2], boundary["walkable_polygons_xy_m"])
    lower = -float(cfg["lower_height_margin_m"])
    upper = float(protocol["agent"]["height_m"]) + float(
        cfg["upper_height_margin_above_agent_m"]
    )
    height_band = (triangles[:, :, 2].max(axis=1) >= lower) & (
        triangles[:, :, 2].min(axis=1) <= upper
    )
    keep = (
        np.isfinite(maximum_edge)
        & (maximum_edge <= float(cfg["maximum_triangle_edge_m"]))
        & (areas > 1e-9)
        & region
        & height_band
    )
    faces = faces[keep]
    if len(faces) == 0:
        raise RuntimeError("Surface extraction retained no triangles")
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    output_vertices = vertices[used].astype(np.float32)
    output_faces = remap[faces].astype(np.int32)
    return (
        output_vertices,
        output_faces,
        {
            "grid_stride": stride,
            "sampled_grid": [int(h), int(w)],
            "sampled_vertices": int(len(vertices)),
            "candidate_faces": int(len(keep)),
            "retained_vertices": int(len(output_vertices)),
            "retained_faces": int(len(output_faces)),
            "retained_face_fraction": float(keep.mean()),
            "maximum_triangle_edge_m": float(cfg["maximum_triangle_edge_m"]),
            "connect_equirectangular_seam": bool(cfg["connect_equirectangular_seam"]),
            "height_band_m": [lower, upper],
            "region_test": cfg["face_region_test"],
        },
    )


def save_navmesh(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.savez_compressed(
            handle,
            vertices=np.asarray(vertices, dtype=np.float32),
            faces=np.asarray(faces, dtype=np.int32),
        )


def reference_key(boundary: dict[str, Any], protocol: dict[str, Any]) -> str:
    return stable_hash(
        {
            "boundary": boundary,
            "agent": protocol["agent"],
            "recast": protocol["recast"],
            "postprocess": protocol["postprocess"],
        }
    )


def recast_config(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        key: protocol[key]
        for key in ("agent", "recast", "postprocess", "spawn", "success")
    }


def ensure_reference_cache(boundary: dict[str, Any], protocol: dict[str, Any]) -> Path:
    key = reference_key(boundary, protocol)
    directory = REFERENCE_CACHE / key
    complete = directory / "COMPLETE"
    if complete.exists():
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    vertices, faces = reference_mesh(boundary)
    mesh_path = directory / "reference.ply"
    write_ply(mesh_path, vertices, faces)
    nav_vertices, nav_faces, metadata = build(mesh_path, recast_config(protocol), 0.0)
    if len(nav_faces) == 0:
        raise RuntimeError(f"Reference Recast mesh is empty for {key}")
    save_navmesh(directory / "reference.navmesh", nav_vertices, nav_faces)
    area = float(triangle_areas(nav_vertices, nav_faces).sum())
    registered = spawn_projection(
        tuple(boundary["structural_spawn_candidate_m"]), nav_vertices, nav_faces
    )
    if not registered.get("projected"):
        raise RuntimeError(
            f"Frozen reference spawn does not project for {key}: {registered}"
        )
    atomic_json(
        directory / "metadata.json",
        {
            "key": key,
            "reference_area_m2": area,
            "reference_vertices": int(len(nav_vertices)),
            "reference_faces": int(len(nav_faces)),
            "registered_spawn": registered,
            "recast": metadata,
            "boundary": boundary,
        },
    )
    atomic_text(complete, "reference cache complete\n")
    return directory


def load_reference(directory: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(directory / "reference.navmesh") as archive:
        vertices = np.asarray(archive["vertices"], dtype=np.float32)
        faces = np.asarray(archive["faces"], dtype=np.int32)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    return vertices, faces, metadata


def relative_symlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source.resolve():
            return
        destination.unlink()
    elif destination.exists():
        raise RuntimeError(
            f"Refusing to replace non-symlink raw artifact: {destination}"
        )
    destination.symlink_to(os.path.relpath(source, destination.parent))


def draw_debug(
    path: Path,
    boundary: dict[str, Any],
    reference_vertices: np.ndarray,
    reference_faces: np.ndarray,
    final_vertices: np.ndarray,
    final_faces: np.ndarray,
    components: list[list[int]],
) -> None:
    size, margin = 768, 24
    roi = np.asarray(boundary["roi_xy_m"], dtype=float)
    lower, upper = roi.min(axis=0), roi.max(axis=0)
    span = np.maximum(upper - lower, 1e-6)

    def pixel(point: np.ndarray | list[float]) -> tuple[int, int]:
        point = np.asarray(point, dtype=float)
        x = margin + (point[0] - lower[0]) / span[0] * (size - 2 * margin)
        y = size - margin - (point[1] - lower[1]) / span[1] * (size - 2 * margin)
        return int(round(x)), int(round(y))

    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    for face in reference_faces:
        draw.polygon(
            [pixel(reference_vertices[index]) for index in face],
            fill=(203, 213, 225, 70),
        )
    palette = [
        (37, 99, 235, 180),
        (239, 68, 68, 180),
        (16, 185, 129, 180),
        (168, 85, 247, 180),
    ]
    face_component: dict[int, int] = {}
    for component_index, member_faces in enumerate(components):
        for face_index in member_faces:
            face_component[face_index] = component_index
    for face_index, face in enumerate(final_faces):
        draw.polygon(
            [pixel(final_vertices[index]) for index in face],
            fill=palette[face_component.get(face_index, 0) % len(palette)],
        )
    for polygon in boundary["walkable_polygons_xy_m"]:
        points = [pixel(point) for point in polygon]
        draw.line(points + points[:1], fill=(30, 41, 59, 150), width=1)
    sx, sy = pixel(boundary["structural_spawn_candidate_m"])
    draw.ellipse((sx - 5, sy - 5, sx + 5, sy + 5), fill=(0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def structural_na(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "worldgen",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "track": "surface_only",
        "collision_rate": None,
        "floating_rate": None,
        "oob_rate": None,
        "support_validity": None,
        "valid_scene": None,
        "reason": "N/A-I",
        "detail": "WorldGen's final Gaussian splat has no recoverable native object instances.",
    }


def failed_navigation(spec: dict[str, Any], failure: dict[str, str]) -> dict[str, Any]:
    return {
        "method": "worldgen",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "track": "surface_only",
        "empty_reference_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "navigable_area_ratio": 0.0,
        "largest_component_area_m2": 0.0,
        "connected_area_ratio": 0.0,
        "component_count": 0,
        "registered_spawn": None,
        "final_spawn_projection": None,
        "spawn_check_passed": False,
        "navmesh_success": False,
        "mesh_extraction_success": False,
        "scale_calibration_success": False,
        "failures": [failure],
    }


def run_one(domain: str, spec: dict[str, Any], seed: int) -> dict[str, Any]:
    protocol = load_protocol()
    started_utc = utc_now()
    started = time.monotonic()
    source = TABLE2_ROOT / domain / "worldgen" / spec["spec_id"] / f"seed_{seed}"
    run_dir = DATA_ROOT / domain / "worldgen" / spec["spec_id"] / f"seed_{seed}"
    require_below_baselines(source)
    require_below_baselines(run_dir)
    for child in (
        "input",
        "scene/raw",
        "scene/canonical",
        "navigation",
        "metrics",
        "logs",
    ):
        (run_dir / child).mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    boundary = reference_definition(spec, protocol)
    atomic_json(run_dir / "input/boundaries.json", boundary)
    atomic_json(run_dir / "metrics/structural.json", structural_na(spec))
    table2_manifest: dict[str, Any] = {}
    manifest: dict[str, Any] = {
        "method": "worldgen",
        "implementation": protocol["implementation"],
        "domain": domain,
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "started_at_utc": started_utc,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "method_lock_sha256": sha256_file(METHOD_LOCK_PATH),
        "source_run": str(source.relative_to(REPO_ROOT)),
        "reuse_table2": True,
        "regenerated": False,
    }
    navigation: dict[str, Any]
    geometry_success = False
    scale_success = False
    try:
        table2_manifest_path = source / "run_manifest.json"
        table2_manifest = json.loads(table2_manifest_path.read_text(encoding="utf-8"))
        if (
            not table2_manifest.get("generation_success")
            or not (source / "GENERATION_SUCCESS").exists()
        ):
            raise RuntimeError(
                "Table 2 WorldGen generation did not reach GENERATION_SUCCESS"
            )
        splat = source / "scene/splat.ply"
        if not splat.is_file():
            raise FileNotFoundError(splat)
        native_input = json.loads(
            (source / "input/native_input.json").read_text(encoding="utf-8")
        )
        cameras = json.loads(
            (source / "renders/sequence/cameras.json").read_text(encoding="utf-8")
        )
        expected_height = float(
            protocol["scale_calibration"]["nominal_camera_height_m"][domain]
        )
        if not math.isclose(
            float(cameras["nominal_camera_height_m"]), expected_height, abs_tol=1e-9
        ):
            raise RuntimeError(
                "Table 2 camera-height anchor differs from the frozen Table 3 protocol"
            )
        atomic_json(run_dir / "input/native_input.json", native_input)
        atomic_json(run_dir / "input/table2_cameras.json", cameras)
        relative_symlink(splat, run_dir / "scene/raw/splat.ply")
        panorama = source / "scene/panorama.png"
        if panorama.is_file():
            relative_symlink(panorama, run_dir / "scene/raw/panorama.png")
        raw_sha256 = sha256_file(splat)
        points, ordered_meta = load_ordered_centers(splat, protocol)
        scale = calibrate_scale(points, domain, protocol)
        scale_success = True
        vertices, faces, extraction = extract_surface(points, scale, boundary, protocol)
        canonical_path = run_dir / "scene/canonical/collision.ply"
        write_ply(canonical_path, vertices, faces)
        geometry_success = True
        atomic_json(
            run_dir / "scene/canonical/instances.json",
            {
                "coordinate_system": "right-handed-z-up",
                "unit": "meter",
                "representation": "surface_only",
                "native_instance_coverage": 0.0,
                "instances": [],
                "na_reason": "N/A-I",
                "floor_z_m": 0.0,
                "walkable_polygons_xy_m": boundary["walkable_polygons_xy_m"],
            },
        )
        atomic_json(
            run_dir / "scene/canonical/transform.json",
            {
                "source_coordinate_system": "WorldGen/OpenCV x-right, y-down, z-forward",
                "target_coordinate_system": "right-handed-z-up",
                "mapping": "target=(source_x,source_z,-source_y)*scale+(0,0,camera_height)",
                "scale_calibration": scale,
            },
        )

        reference_dir = ensure_reference_cache(boundary, protocol)
        ref_vertices, ref_faces, reference_meta = load_reference(reference_dir)
        relative_symlink(
            reference_dir / "reference.ply",
            run_dir / "scene/canonical/empty_reference.ply",
        )
        save_navmesh(
            run_dir / "navigation/empty_reference.navmesh", ref_vertices, ref_faces
        )
        final_vertices, final_faces, final_meta = build(
            canonical_path, recast_config(protocol), 0.0
        )
        save_navmesh(run_dir / "navigation/final.navmesh", final_vertices, final_faces)
        final_area = float(triangle_areas(final_vertices, final_faces).sum())
        reference_area = float(reference_meta["reference_area_m2"])
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
        builder_ok = bool(final_meta.get("builder_returned"))
        navmesh_success = bool(
            builder_ok
            and reference_area > 0.0
            and np.isfinite(final_area)
            and final_area >= minimum_fraction * reference_area
            and spawn_ok
        )
        navigable_ratio = (
            100.0 * min(1.0, max(0.0, final_area / reference_area))
            if reference_area > 0.0
            else 0.0
        )
        connected_ratio = 100.0 * largest / final_area if final_area > 0.0 else 0.0
        atomic_json(
            run_dir / "navigation/components.json",
            {
                "component_count": len(components),
                "component_areas_m2": component_areas,
                "components": components,
            },
        )
        draw_debug(
            run_dir / "navigation/debug_topdown.png",
            boundary,
            ref_vertices,
            ref_faces,
            final_vertices,
            final_faces,
            components,
        )
        navigation = {
            "method": "worldgen",
            "domain": domain,
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "track": "surface_only",
            "empty_reference_area_m2": reference_area,
            "final_navmesh_area_m2": final_area,
            "navigable_area_ratio": navigable_ratio,
            "largest_component_area_m2": largest,
            "connected_area_ratio": connected_ratio,
            "component_count": len(components),
            "registered_spawn": registered,
            "final_spawn_projection": final_spawn,
            "spawn_check_passed": spawn_ok,
            "navmesh_success": navmesh_success,
            "mesh_extraction_success": True,
            "scale_calibration_success": True,
            "scale_calibration": scale,
            "ordered_splat": ordered_meta,
            "surface_extraction": extraction,
            "reference_key": reference_meta["key"],
            "reference_recast": reference_meta["recast"],
            "final_recast": final_meta,
            "recast_config": recast_config(protocol),
            "failures": [],
        }
        manifest.update(
            {
                "raw_splat_sha256": raw_sha256,
                "canonical_collision_sha256": sha256_file(canonical_path),
                "scale_calibration": scale,
                "surface_extraction": extraction,
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
        navigation = failed_navigation(spec, failure)
        navigation["logical_seed"] = seed
    navigation["table2_generation_success"] = bool(
        table2_manifest.get("generation_success")
    )
    navigation["table2_render_success"] = bool(table2_manifest.get("render_success"))
    atomic_json(run_dir / "metrics/navigability.json", navigation)
    atomic_text(
        run_dir / "EVALUATION_SUCCESS",
        "WorldGen Table 3 evaluation completed under ITT\n",
    )
    manifest.update(
        {
            "table2_generation_success": bool(
                table2_manifest.get("generation_success")
            ),
            "table2_render_success": bool(table2_manifest.get("render_success")),
            "geometry_extracted": geometry_success,
            "scale_calibrated": scale_success,
            "navmesh_success": bool(navigation["navmesh_success"]),
            "evaluation_completed": True,
            "failure_count": len(navigation["failures"]),
            "ended_at_utc": utc_now(),
            "wall_time_s": time.monotonic() - started,
            "software": {
                "python": sys.version.split()[0],
                "numpy": np.__version__,
                "recast_module": str(
                    (RECAST_RUNTIME / "recast.cpython-311-x86_64-linux-gnu.so")
                ),
            },
        }
    )
    atomic_json(run_dir / "run_manifest.json", manifest)
    return {
        "domain": domain,
        "spec_id": spec["spec_id"],
        "seed": seed,
        "geometry_extracted": geometry_success,
        "navmesh_success": bool(navigation["navmesh_success"]),
        "navigable_area_ratio": float(navigation["navigable_area_ratio"]),
        "connected_area_ratio": float(navigation["connected_area_ratio"]),
        "failure_count": len(navigation["failures"]),
        "wall_time_s": manifest["wall_time_s"],
    }


def selected_tasks(
    phase: str, domains: list[str]
) -> list[tuple[str, dict[str, Any], int]]:
    protocol = load_protocol()
    tasks = []
    seeds = [0, 1] if phase == "pilot" else [int(value) for value in protocol["seeds"]]
    for domain in domains:
        specs = load_specs(domain, protocol)
        if phase == "pilot":
            specs = [spec for spec in specs if spec["spec_index"] in PILOT_INDICES]
        tasks.extend((domain, spec, seed) for spec in specs for seed in seeds)
    return tasks


def prepare_references(tasks: list[tuple[str, dict[str, Any], int]]) -> None:
    protocol = load_protocol()
    unique: dict[str, dict[str, Any]] = {}
    for _, spec, _ in tasks:
        boundary = reference_definition(spec, protocol)
        unique[reference_key(boundary, protocol)] = boundary
    for index, (key, boundary) in enumerate(sorted(unique.items()), 1):
        directory = ensure_reference_cache(boundary, protocol)
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        print(
            f"REFERENCE_READY {index}/{len(unique)} key={key[:12]} "
            f"area={metadata['reference_area_m2']:.4f}",
            flush=True,
        )


def run_matrix(phase: str, domains: list[str], workers: int) -> int:
    tasks = selected_tasks(phase, domains)
    prepare_references(tasks)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = RESULTS_ROOT / f"matrix_{phase}.jsonl"
    records = []
    print(
        f"WORLDGEN_TABLE3_START phase={phase} tasks={len(tasks)} workers={workers}",
        flush=True,
    )
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        future_tasks = {
            executor.submit(run_one, domain, spec, seed): (
                domain,
                spec["spec_id"],
                seed,
            )
            for domain, spec, seed in tasks
        }
        for completed, future in enumerate(
            concurrent.futures.as_completed(future_tasks), 1
        ):
            domain, spec_id, seed = future_tasks[future]
            try:
                record = future.result()
            except Exception as error:
                record = {
                    "domain": domain,
                    "spec_id": spec_id,
                    "seed": seed,
                    "infrastructure_error": f"{type(error).__name__}: {error}",
                }
            record["completed_index"] = completed
            records.append(record)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
            print(
                "WORLDGEN_TABLE3_ITEM " + json.dumps(record, sort_keys=True), flush=True
            )
    infra = [record for record in records if "infrastructure_error" in record]
    print(
        f"WORLDGEN_TABLE3_COMPLETE phase={phase} tasks={len(tasks)} infra_failures={len(infra)}",
        flush=True,
    )
    return 1 if infra else 0


def audit_existing() -> dict[str, Any]:
    protocol = load_protocol()
    rows = []
    for domain in protocol["domains"]:
        for spec in load_specs(domain, protocol):
            for seed in protocol["seeds"]:
                source = (
                    TABLE2_ROOT / domain / "worldgen" / spec["spec_id"] / f"seed_{seed}"
                )
                manifest_path = source / "run_manifest.json"
                manifest = (
                    json.loads(manifest_path.read_text())
                    if manifest_path.is_file()
                    else {}
                )
                splat = source / "scene/splat.ply"
                rows.append(
                    {
                        "domain": domain,
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "run_manifest": manifest_path.is_file(),
                        "generation_success": bool(manifest.get("generation_success")),
                        "render_success": bool(manifest.get("render_success")),
                        "raw_splat": splat.is_file(),
                        "raw_splat_bytes": splat.stat().st_size
                        if splat.is_file()
                        else 0,
                        "reusable_raw": bool(manifest.get("generation_success"))
                        and splat.is_file(),
                    }
                )
    result = {
        "protocol": protocol["protocol_id"],
        "audited_at_utc": utc_now(),
        "planned_runs": len(rows),
        "reusable_raw": sum(row["reusable_raw"] for row in rows),
        "generation_success": sum(row["generation_success"] for row in rows),
        "render_success": sum(row["render_success"] for row in rows),
        "total_raw_bytes": sum(row["raw_splat_bytes"] for row in rows),
        "rows": rows,
    }
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULTS_ROOT / "reuse_inventory.json", result)
    print(
        f"WORLDGEN_REUSE_INVENTORY reusable={result['reusable_raw']}/{result['planned_runs']} "
        f"render_success={result['render_success']}/{result['planned_runs']}",
        flush=True,
    )
    return result


def metric_lock() -> dict[str, Any]:
    files = {
        "protocol": PROTOCOL_PATH,
        "method_lock": METHOD_LOCK_PATH,
        "evaluator": Path(__file__),
        "common_navmesh": (BASELINES / "evaluation/geometry/metrics/build_navmesh.py"),
        "recast_binary": (RECAST_RUNTIME / "recast.cpython-311-x86_64-linux-gnu.so"),
    }
    lock = {
        "protocol_id": load_protocol()["protocol_id"],
        "created_at_utc": utc_now(),
        "files": {
            str(path.relative_to(REPO_ROOT)): sha256_file(path)
            for path in files.values()
        },
        "recast_source": "baselines/sources/HY-World-2.0/hyworld2/worldgen/third_party/{navmesh,recastnavigation}",
        "recast_build": {
            "compiler": "/usr/bin/g++ 9.4.0",
            "glibc_compatibility": "2.31",
            "components_connected": False,
            "largest_component_only": False,
        },
    }
    atomic_json(METRICS_LOCK_PATH, lock)
    print(f"WORLDGEN_METRICS_LOCK {sha256_file(METRICS_LOCK_PATH)}", flush=True)
    return lock


def bootstrap(values: np.ndarray, repeats: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(repeats, len(values)))
    draws = values[indices].mean(axis=1)
    return [float(value) for value in np.percentile(draws, [2.5, 97.5])]


def aggregate() -> dict[str, Any]:
    protocol = load_protocol()
    repeats = int(protocol["aggregation"]["bootstrap_repeats"])
    bootstrap_seed = int(protocol["aggregation"]["bootstrap_seed"])
    domain_results = []
    full_domains = {}
    for domain_index, domain in enumerate(protocol["domains"]):
        scene_rows = []
        failures: Counter[str] = Counter()
        specs = load_specs(domain, protocol)
        for spec in specs:
            for seed in protocol["seeds"]:
                path = (
                    DATA_ROOT
                    / domain
                    / "worldgen"
                    / spec["spec_id"]
                    / f"seed_{seed}"
                    / "metrics/navigability.json"
                )
                if path.is_file():
                    row = json.loads(path.read_text(encoding="utf-8"))
                    row["evaluated"] = True
                    for failure in row.get("failures", []):
                        failures[failure.get("type", "unknown")] += 1
                else:
                    row = failed_navigation(
                        spec, {"type": "missing_evaluation", "message": str(path)}
                    )
                    row["logical_seed"] = seed
                    row["evaluated"] = False
                    failures["missing_evaluation"] += 1
                row["spec_index"] = spec["spec_index"]
                scene_rows.append(row)
        spec_rows = []
        for spec in specs:
            members = [row for row in scene_rows if row["spec_id"] == spec["spec_id"]]
            spec_rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "spec_index": spec["spec_index"],
                    "navigable_area_ratio": float(
                        np.mean([row["navigable_area_ratio"] for row in members])
                    ),
                    "connected_area_ratio": float(
                        np.mean([row["connected_area_ratio"] for row in members])
                    ),
                    "navmesh_success_rate": 100.0
                    * float(np.mean([row["navmesh_success"] for row in members])),
                }
            )
        metrics = {}
        for offset, name in enumerate(
            ("navigable_area_ratio", "connected_area_ratio", "navmesh_success_rate")
        ):
            values = np.asarray([row[name] for row in spec_rows], dtype=float)
            metrics[name] = {
                "mean": float(values.mean()),
                "ci95": bootstrap(
                    values, repeats, bootstrap_seed + 100 * domain_index + offset
                ),
            }
        output = {
            "method": "worldgen",
            "domain": domain,
            "track": "surface_only",
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "navigable_area_ratio": metrics["navigable_area_ratio"]["mean"],
            "connected_area_ratio": metrics["connected_area_ratio"]["mean"],
            "navmesh_success_rate": metrics["navmesh_success_rate"]["mean"],
            "valid_scene_rate": "N/A-I",
            "planned_runs": len(scene_rows),
            "evaluated_runs": sum(row["evaluated"] for row in scene_rows),
            "raw_geometry_coverage": sum(
                row.get("table2_generation_success", False) for row in scene_rows
            )
            / len(scene_rows),
            "geometry_coverage": sum(
                row.get("mesh_extraction_success", False) for row in scene_rows
            )
            / len(scene_rows),
            "scale_calibration_coverage": sum(
                row.get("scale_calibration_success", False) for row in scene_rows
            )
            / len(scene_rows),
            "instance_coverage": 0.0,
        }
        domain_results.append(output)
        full_domains[domain] = {
            "summary": output,
            "metrics": metrics,
            "failure_breakdown": dict(failures),
            "spec_rows": spec_rows,
            "scene_rows": scene_rows,
        }
    result = {
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "method_lock_sha256": sha256_file(METHOD_LOCK_PATH),
        "metrics_lock_sha256": sha256_file(METRICS_LOCK_PATH)
        if METRICS_LOCK_PATH.is_file()
        else None,
        "aggregated_at_utc": utc_now(),
        "failure_policy": "itt",
        "aggregation_order": "mean_over_spec(mean_over_seed(scene_metric))",
        "bootstrap_repeats": repeats,
        "domains": full_domains,
    }
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULTS_ROOT / "table3_full.json", result)
    columns = list(domain_results[0])
    lines = [",".join(columns)]
    for row in domain_results:
        fields = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                fields.append(f"{value:.10g}")
            else:
                fields.append(str(value))
        lines.append(",".join(fields))
    atomic_text(RESULTS_ROOT / "table3.csv", "\n".join(lines) + "\n")
    for row in domain_results:
        print(
            "WORLDGEN_TABLE3_RESULT "
            + json.dumps(
                {
                    "domain": row["domain"],
                    "navigable_area_ratio": row["navigable_area_ratio"],
                    "connected_area_ratio": row["connected_area_ratio"],
                    "navmesh_success_rate": row["navmesh_success_rate"],
                    "geometry_coverage": row["geometry_coverage"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return result


def audit_results() -> dict[str, Any]:
    protocol = load_protocol()
    issues = []
    counts = Counter()
    for domain in protocol["domains"]:
        for spec in load_specs(domain, protocol):
            for seed in protocol["seeds"]:
                run_dir = (
                    DATA_ROOT / domain / "worldgen" / spec["spec_id"] / f"seed_{seed}"
                )
                counts["planned"] += 1
                metric_path = run_dir / "metrics/navigability.json"
                if not metric_path.is_file():
                    issues.append(f"missing metric: {metric_path}")
                    continue
                counts["evaluated"] += 1
                metric = json.loads(metric_path.read_text(encoding="utf-8"))
                for name in ("navigable_area_ratio", "connected_area_ratio"):
                    value = metric.get(name)
                    if (
                        not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or not 0 <= value <= 100
                    ):
                        issues.append(f"invalid {name}: {metric_path}: {value}")
                if metric.get("mesh_extraction_success"):
                    counts["geometry"] += 1
                    for relative in (
                        "scene/raw/splat.ply",
                        "scene/canonical/collision.ply",
                        "navigation/empty_reference.navmesh",
                        "navigation/final.navmesh",
                        "navigation/debug_topdown.png",
                    ):
                        if not (run_dir / relative).exists():
                            issues.append(
                                f"missing terminal artifact: {run_dir / relative}"
                            )
                if metric.get("scale_calibration_success"):
                    counts["scale"] += 1
                if metric.get("navmesh_success"):
                    counts["nav_success"] += 1
                if not (run_dir / "EVALUATION_SUCCESS").is_file():
                    issues.append(f"missing EVALUATION_SUCCESS: {run_dir}")
    result = {
        "audited_at_utc": utc_now(),
        "counts": dict(counts),
        "issues": issues,
        "passed": not issues
        and counts["planned"] == 200
        and counts["evaluated"] == 200,
    }
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULTS_ROOT / "audit.json", result)
    print(
        f"WORLDGEN_TABLE3_AUDIT passed={result['passed']} counts={dict(counts)} issues={len(issues)}",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    subparsers.add_parser("lock")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    run_parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    run_parser.add_argument("--workers", type=int, default=4)
    subparsers.add_parser("aggregate")
    subparsers.add_parser("audit")
    args = parser.parse_args()
    if args.command == "inventory":
        audit_existing()
        return 0
    if args.command == "lock":
        metric_lock()
        return 0
    if args.command == "run":
        return run_matrix(args.phase, args.domains, args.workers)
    if args.command == "aggregate":
        aggregate()
        return 0
    if args.command == "audit":
        return 0 if audit_results()["passed"] else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
