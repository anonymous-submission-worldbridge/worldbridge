#!/usr/bin/env python3
"""Pure helpers for the frozen GPT-6 Astra native-mesh navigation track."""

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


import json
from pathlib import Path
from typing import Iterable


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RULES_PATH = (
    BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json"
)


def load_rules(path: Path = RULES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_name(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").replace("-", " ").split())


def contains_any(name: str, patterns: Iterable[str]) -> bool:
    value = normalized_name(name)
    return any(normalized_name(pattern) in value for pattern in patterns)


def is_crosswalk(name: str) -> bool:
    return contains_any(name, ("crosswalk", "pedestrian crossing", "zebra crossing"))


def is_surface_detail(name: str, rules: dict) -> bool:
    return contains_any(name, rules["surface_detail_exclusions"])


def is_walkable_surface(name: str, rules: dict, domain: str) -> bool:
    value = normalized_name(name)
    if domain == "indoor":
        return "floor" in value and not contains_any(
            value, rules["thin_nav_exclusions"]
        )
    if is_crosswalk(value):
        return True
    return contains_any(
        value, rules["walkable_name_patterns"]
    ) and not is_surface_detail(value, rules)


def is_support_surface(name: str, rules: dict) -> bool:
    return contains_any(name, rules["support_surface_name_patterns"])


def exclude_from_nav_obstacles(name: str, rules: dict) -> bool:
    return (
        is_support_surface(name, rules)
        or is_surface_detail(name, rules)
        or contains_any(name, rules["thin_nav_exclusions"])
    )


def roi_for_spec(spec: dict, rules: dict) -> tuple[float, float, float, float]:
    if spec["domain"] == "urban":
        half = float(rules["urban_roi"]["half_extent_m"])
        return (-half, half, -half, half)
    width, depth = [float(value) for value in spec["extent_m"][:2]]
    return (-width / 2.0, width / 2.0, -depth / 2.0, depth / 2.0)


def aabb_intersects_roi(
    minimum: Iterable[float],
    maximum: Iterable[float],
    roi: tuple[float, float, float, float],
) -> bool:
    minimum = list(minimum)
    maximum = list(maximum)
    xmin, xmax, ymin, ymax = roi
    return not (
        maximum[0] < xmin or minimum[0] > xmax or maximum[1] < ymin or minimum[1] > ymax
    )
