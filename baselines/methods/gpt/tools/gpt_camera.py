"""Geometry-only camera helpers, independent of Blender and model output quality."""

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


def corner_preserving_resample(raw, count=50):
    if len(raw) < 2 or count < 2:
        raise ValueError("At least two path points and samples are required")
    points = [tuple(raw[0])]
    for i in range(1, len(raw) - 1):
        a, b, c = raw[i - 1 : i + 2]
        first = (b[0] - a[0], b[1] - a[1])
        second = (c[0] - b[0], c[1] - b[1])
        cross = first[0] * second[1] - first[1] * second[0]
        dot = first[0] * second[0] + first[1] * second[1]
        if abs(cross) > 1e-8 or dot <= 0:
            points.append(tuple(b))
    points.append(tuple(raw[-1]))
    if len(points) > count:
        raise ValueError("Path has more essential corners than camera frames")
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if min(lengths) <= 0 or total <= 0:
        raise ValueError("Path contains zero-length segments")
    ideal = [(count - 1) * length / total for length in lengths]
    allocation = [1] * len(lengths)
    for _ in range(count - 1 - len(lengths)):
        index = max(range(len(lengths)), key=lambda i: (ideal[i] - allocation[i], -i))
        allocation[index] += 1
    result = [points[0]]
    for a, b, n in zip(points, points[1:], allocation):
        for i in range(1, n + 1):
            t = i / n
            result.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return result
