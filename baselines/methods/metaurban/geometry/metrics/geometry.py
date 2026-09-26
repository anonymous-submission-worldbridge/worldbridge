"""Geometry primitives for MetaUrban canonical proxies and metrics."""

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


import math
from collections.abc import Iterable

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import triangulate, unary_union


EPS = 1e-8


def obb(center_xy, size_xyz, heading: float, z_min: float = 0.0) -> dict:
    length, width, height = (float(value) for value in size_xyz)
    cosine, sine = math.cos(heading), math.sin(heading)
    axes = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    center = np.asarray(
        [float(center_xy[0]), float(center_xy[1]), z_min + height / 2.0]
    )
    half = np.asarray([length / 2.0, width / 2.0, height / 2.0])
    corners = np.asarray(
        [
            center
            + sx * half[0] * axes[:, 0]
            + sy * half[1] * axes[:, 1]
            + sz * half[2] * axes[:, 2]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ]
    )
    return {
        "center": center.tolist(),
        "axes": axes.tolist(),
        "half_sizes": half.tolist(),
        "corners": corners.tolist(),
        "volume_m3": float(length * width * height),
    }


def footprint(proxy: dict) -> Polygon:
    center = np.asarray(proxy["center"], dtype=float)
    axes = np.asarray(proxy["axes"], dtype=float)
    half = np.asarray(proxy["half_sizes"], dtype=float)
    points = [
        center[:2] + sx * half[0] * axes[:2, 0] + sy * half[1] * axes[:2, 1]
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
    return Polygon(points)


def sat_overlap(left: dict, right: dict) -> tuple[bool, float]:
    a_center = np.asarray(left["center"], dtype=float)
    b_center = np.asarray(right["center"], dtype=float)
    a_axes = np.asarray(left["axes"], dtype=float)
    b_axes = np.asarray(right["axes"], dtype=float)
    a_half = np.asarray(left["half_sizes"], dtype=float)
    b_half = np.asarray(right["half_sizes"], dtype=float)
    axes = [a_axes[:, index] for index in range(3)] + [
        b_axes[:, index] for index in range(3)
    ]
    axes.extend(
        cross / np.linalg.norm(cross)
        for ia in range(3)
        for ib in range(3)
        if np.linalg.norm(cross := np.cross(a_axes[:, ia], b_axes[:, ib])) > EPS
    )
    minimum = math.inf
    delta = b_center - a_center
    for axis in axes:
        axis = np.asarray(axis, dtype=float)
        radius_a = sum(
            a_half[index] * abs(float(np.dot(axis, a_axes[:, index])))
            for index in range(3)
        )
        radius_b = sum(
            b_half[index] * abs(float(np.dot(axis, b_axes[:, index])))
            for index in range(3)
        )
        overlap = float(radius_a + radius_b - abs(np.dot(delta, axis)))
        if overlap < -EPS:
            return False, 0.0
        minimum = min(minimum, max(0.0, overlap))
    return True, float(minimum)


def overlap_volume(left: dict, right: dict) -> float:
    a_center = np.asarray(left["center"], dtype=float)
    b_center = np.asarray(right["center"], dtype=float)
    a_half = np.asarray(left["half_sizes"], dtype=float)
    b_half = np.asarray(right["half_sizes"], dtype=float)
    z_overlap = min(a_center[2] + a_half[2], b_center[2] + b_half[2]) - max(
        a_center[2] - a_half[2], b_center[2] - b_half[2]
    )
    if z_overlap <= 0.0:
        return 0.0
    return float(footprint(left).intersection(footprint(right)).area * z_overlap)


def polygon_parts(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    answer: list[Polygon] = []
    for child in getattr(geometry, "geoms", []):
        answer.extend(polygon_parts(child))
    return answer


def clean_union(polygons: Iterable[Polygon]):
    valid = [
        polygon.buffer(0)
        for polygon in polygons
        if not polygon.is_empty and polygon.area > EPS
    ]
    return unary_union(valid).buffer(0) if valid else Polygon()


def _triangles_for_polygon(polygon: Polygon) -> list[list[list[float]]]:
    result: list[list[list[float]]] = []
    for candidate in triangulate(polygon):
        clipped = candidate.intersection(polygon)
        for part in polygon_parts(clipped):
            coords = list(part.exterior.coords)[:-1]
            if len(coords) == 3 and not part.interiors:
                result.append([[float(x), float(y)] for x, y in coords])
                continue
            # Intersections with a Delaunay triangle are normally convex.  A fan
            # is exact for that case; the containment guard prevents hole fill.
            if len(coords) >= 3 and not part.interiors:
                origin = coords[0]
                for index in range(1, len(coords) - 1):
                    triangle = Polygon([origin, coords[index], coords[index + 1]])
                    if triangle.area > EPS and part.buffer(EPS).covers(triangle):
                        result.append(
                            [
                                [float(x), float(y)]
                                for x, y in (origin, coords[index], coords[index + 1])
                            ]
                        )
    return result


def surface_mesh(geometry, z: float = 0.0) -> tuple[np.ndarray, np.ndarray, list]:
    triangles = [
        triangle
        for part in polygon_parts(geometry)
        for triangle in _triangles_for_polygon(part)
    ]
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for triangle in triangles:
        offset = len(vertices)
        vertices.extend([[point[0], point[1], float(z)] for point in triangle])
        face = [offset, offset + 1, offset + 2]
        left, middle, right = vertices[offset : offset + 3]
        signed_twice_area = (middle[0] - left[0]) * (right[1] - left[1]) - (
            middle[1] - left[1]
        ) * (right[0] - left[0])
        # Recast consumes one-sided triangles.  Keep every horizontal surface
        # consistently upward-facing in the source Z-up frame.
        faces.append(
            face if signed_twice_area > 0.0 else [offset, offset + 2, offset + 1]
        )
    return (
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
        triangles,
    )


def box_mesh(proxy: dict) -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(proxy["corners"], dtype=np.float32)
    faces = np.asarray(
        [
            (0, 2, 3),
            (0, 3, 1),
            (4, 5, 7),
            (4, 7, 6),
            (0, 1, 5),
            (0, 5, 4),
            (2, 6, 7),
            (2, 7, 3),
            (0, 4, 6),
            (0, 6, 2),
            (1, 3, 7),
            (1, 7, 5),
        ],
        dtype=np.int32,
    )
    # The corner enumeration above makes this table inward-facing.  Flip it so
    # the closed collision proxy has conventional outward normals.
    return vertices, faces[:, [0, 2, 1]]


def merge_meshes(
    parts: Iterable[tuple[np.ndarray, np.ndarray]]
) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    for part_vertices, part_faces in parts:
        if len(part_vertices) == 0 or len(part_faces) == 0:
            continue
        vertices.append(np.asarray(part_vertices, dtype=np.float32))
        faces.append(np.asarray(part_faces, dtype=np.int32) + offset)
        offset += len(part_vertices)
    if not vertices:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.int32)
    return np.concatenate(vertices), np.concatenate(faces)


def write_ply(path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as handle:
        handle.write("ply\nformat ascii 1.0\n")
        handle.write(f"element vertex {len(vertices)}\n")
        handle.write("property float x\nproperty float y\nproperty float z\n")
        handle.write(f"element face {len(faces)}\n")
        handle.write("property list uchar int vertex_indices\nend_header\n")
        for vertex in vertices:
            handle.write(f"{vertex[0]:.7g} {vertex[1]:.7g} {vertex[2]:.7g}\n")
        for face in faces:
            handle.write(f"3 {int(face[0])} {int(face[1])} {int(face[2])}\n")
