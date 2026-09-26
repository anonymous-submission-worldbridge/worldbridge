#!/usr/bin/env python3
"""Small geometry primitives shared by the Table 3 exporters and tests."""

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
from collections.abc import Iterable, Sequence

import numpy as np


EPS = 1e-9


def box_corners(
    center: Sequence[float], axes, half_sizes: Sequence[float]
) -> np.ndarray:
    center = np.asarray(center, dtype=float)
    axes = np.asarray(axes, dtype=float)
    half_sizes = np.asarray(half_sizes, dtype=float)
    return np.asarray(
        [
            center
            + sx * half_sizes[0] * axes[:, 0]
            + sy * half_sizes[1] * axes[:, 1]
            + sz * half_sizes[2] * axes[:, 2]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ]
    )


def box_mesh(center: Sequence[float], axes, half_sizes: Sequence[float]):
    """Return consistently wound vertices and triangular faces for an OBB."""
    corners = box_corners(center, axes, half_sizes)
    # box_corners ordering is binary (x, y, z), z changes fastest.
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
        dtype=np.int64,
    )
    return corners, faces


def sat_obb_overlap(a: dict, b: dict, epsilon: float = 1e-8) -> dict:
    """Separating-axis test for two OBBs, including minimum proxy penetration."""
    ca = np.asarray(a["center"], dtype=float)
    cb = np.asarray(b["center"], dtype=float)
    aa = np.asarray(a["axes"], dtype=float)
    ab = np.asarray(b["axes"], dtype=float)
    ea = np.asarray(a["half_sizes"], dtype=float)
    eb = np.asarray(b["half_sizes"], dtype=float)
    candidates = [aa[:, index] for index in range(3)]
    candidates.extend(ab[:, index] for index in range(3))
    for ia in range(3):
        for ib in range(3):
            axis = np.cross(aa[:, ia], ab[:, ib])
            length = float(np.linalg.norm(axis))
            if length > epsilon:
                candidates.append(axis / length)

    center_delta = cb - ca
    minimum = math.inf
    for axis in candidates:
        axis = np.asarray(axis, dtype=float)
        axis /= max(float(np.linalg.norm(axis)), EPS)
        radius_a = float(sum(ea[i] * abs(np.dot(axis, aa[:, i])) for i in range(3)))
        radius_b = float(sum(eb[i] * abs(np.dot(axis, ab[:, i])) for i in range(3)))
        overlap = radius_a + radius_b - abs(float(np.dot(center_delta, axis)))
        if overlap < -epsilon:
            return {"overlap": False, "penetration_depth_m": 0.0}
        minimum = min(minimum, max(0.0, overlap))
    return {"overlap": True, "penetration_depth_m": float(minimum)}


def aabb_overlap_volume(a_min, a_max, b_min, b_max) -> float:
    lengths = np.minimum(a_max, b_max) - np.maximum(a_min, b_min)
    if np.any(lengths <= 0.0):
        return 0.0
    return float(np.prod(lengths))


def convex_hull_2d(points: Iterable[Sequence[float]]) -> list[list[float]]:
    points = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(points) <= 1:
        return [list(point) for point in points]

    def cross(origin, a, b):
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (
            b[0] - origin[0]
        )

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= EPS:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= EPS:
            upper.pop()
        upper.append(point)
    return [list(point) for point in lower[:-1] + upper[:-1]]


def polygon_area(polygon: Sequence[Sequence[float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    return 0.5 * abs(
        sum(
            polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
            - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
            for index in range(len(polygon))
        )
    )


def _signed_area(polygon: Sequence[Sequence[float]]) -> float:
    return 0.5 * sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )


def clip_convex_polygon(subject, clip) -> list[list[float]]:
    """Clip a polygon by a convex polygon using Sutherland-Hodgman."""
    output = [np.asarray(point, dtype=float) for point in subject]
    clip = [np.asarray(point, dtype=float) for point in clip]
    if _signed_area(clip) < 0.0:
        clip.reverse()

    def inside(point, start, end):
        return float(np.cross(end - start, point - start)) >= -EPS

    def intersection(p1, p2, q1, q2):
        direction_p = p2 - p1
        direction_q = q2 - q1
        denominator = float(np.cross(direction_p, direction_q))
        if abs(denominator) <= EPS:
            return p2
        distance = float(np.cross(q1 - p1, direction_q)) / denominator
        return p1 + distance * direction_p

    for index, clip_start in enumerate(clip):
        clip_end = clip[(index + 1) % len(clip)]
        incoming = output
        output = []
        if not incoming:
            break
        previous = incoming[-1]
        for current in incoming:
            current_inside = inside(current, clip_start, clip_end)
            previous_inside = inside(previous, clip_start, clip_end)
            if current_inside:
                if not previous_inside:
                    output.append(intersection(previous, current, clip_start, clip_end))
                output.append(current)
            elif previous_inside:
                output.append(intersection(previous, current, clip_start, clip_end))
            previous = current
    return [[float(value) for value in point] for point in output]


def polygon_area_inside_triangles(polygon, triangles) -> float:
    """Area of a convex polygon inside a non-overlapping triangle mesh."""
    return float(
        sum(
            polygon_area(clip_convex_polygon(polygon, triangle))
            for triangle in triangles
        )
    )


def triangle_area_3d(a, b, c) -> float:
    return 0.5 * float(
        np.linalg.norm(
            np.cross(np.asarray(b) - np.asarray(a), np.asarray(c) - np.asarray(a))
        )
    )


def support_gap_valid(
    gap_m: float | None, mount_type: str, support_gap_m: float = 0.02
) -> bool:
    if gap_m is None or not math.isfinite(gap_m):
        return False
    lower = -0.01
    upper = support_gap_m
    return lower - EPS <= gap_m <= upper + EPS and mount_type in {
        "gravity",
        "wall",
        "ceiling",
    }
