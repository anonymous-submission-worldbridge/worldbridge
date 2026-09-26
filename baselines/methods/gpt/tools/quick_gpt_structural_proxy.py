#!/usr/bin/env python3
"""Fast structural proxy for GPT-6, Gemini, and GLM native-mesh scenes.

This intentionally operates on the retained ``geometry.json`` node AABBs.  It
is a table-completion proxy, not the native-instance/BVH evaluator used for
Infinigen, SceneWeaver, or MetaUrban.  The output keeps all 100 planned slots
per domain and applies the frozen ITT worst case when geometry is absent.
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
import json
import math
import re
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA = BASELINES / "data" / "table2"

METHODS = {
    "gpt6_astra_low": "gpt6_astra_low",
    "gpt6_astra_medium": "gpt6_astra_medium",
    "gpt6_astra_high": "gpt6_astra",
    "glm_5_3_low": "glm_5_3",
    "glm_5_3_flash": "glm53_flash",
    "gemini_3_1_pro": "gemini_3_1_pro",
}

PATTERNS = [
    (
        "vehicle",
        re.compile(
            r"\b(car|cars|vehicle|vehicles|truck|bus|van|taxi|sedan|suv|pickup|bicycle|bike|motorcycle)\b"
        ),
    ),
    ("tree", re.compile(r"\b(tree|trees|trunk|canopy|foliage)\b")),
    (
        "streetlight",
        re.compile(
            r"\b(streetlight|street light|lamp post|lamppost|light pole|street lamp)\b"
        ),
    ),
    (
        "street_furniture",
        re.compile(
            r"\b(bench|hydrant|bollard|mailbox|kiosk|bus stop|trash bin|waste bin|planter|traffic sign|street sign)\b"
        ),
    ),
    (
        "bed",
        re.compile(
            r"\b(bed|mattress|headboard|footboard|pillow|duvet|comforter|blanket)\b"
        ),
    ),
    (
        "table",
        re.compile(r"\b(table|desk|nightstand|bedside|island|counter|countertop)\b"),
    ),
    ("seating", re.compile(r"\b(chair|stool|sofa|couch|armchair|ottoman)\b")),
    (
        "storage",
        re.compile(
            r"\b(wardrobe|cabinet|dresser|bookcase|bookshelf|shelf|shelving|closet|drawer|cupboard|chest)\b"
        ),
    ),
    (
        "appliance",
        re.compile(
            r"\b(refrigerator|fridge|oven|microwave|dishwasher|washer|dryer|cooktop|stove|range hood|range)\b"
        ),
    ),
    ("bath_fixture", re.compile(r"\b(toilet|bathtub|bath tub|shower|sink|basin)\b")),
]

STRUCTURAL = re.compile(
    r"\b(floor|plank|wall|ceiling|roof|road|sidewalk|pavement|curb|crosswalk|lane|building|house|shop|facade|awning|window|door|fence|stair|terrain|ground|grass|foundation|column|beam)\b"
)
EXCLUDED_VISUAL_OR_THIN = re.compile(
    r"\b(rug|carpet|lamp|light|shade|bulb|mirror|picture|painting|art|curtain|towel|blanket|pillow|plant|vase|clock|screen|television|tv)\b"
)

OFFICIAL_RESULTS = {
    "gpt6_astra": BASELINES / "results/gpt6_astra/table3/table3_full.json",
    "gpt6_astra_medium": BASELINES
    / "results/gpt6_astra_medium/table3/table3_full.json",
    "gpt6_astra_low": BASELINES / "results/gpt6_astra_low/table3/table3_full.json",
    "glm_5_3": BASELINES / "results/glm_5_3/table3/table3_full.json",
    "glm53_flash": BASELINES / "results/glm53_flash/table3/table3_full.json",
    "gemini_3_1_pro": BASELINES / "results/gemini_3_1_pro/table3/table3_full.json",
}


def classify(name: str) -> str | None:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    text = re.sub(r"\.\d+$", "", text.lower().replace("_", " ").replace("-", " "))
    is_streetlight = re.search(
        r"\b(streetlight|street light|lamp post|lamppost|light pole|street lamp)\b",
        text,
    )
    if EXCLUDED_VISUAL_OR_THIN.search(text) and not is_streetlight:
        return None
    for category, pattern in PATTERNS:
        if pattern.search(text):
            return category
    if STRUCTURAL.search(text):
        return None
    return None


def box_distance(left: dict, right: dict) -> float:
    squared = 0.0
    for axis in range(3):
        gap = max(
            left["min"][axis] - right["max"][axis],
            right["min"][axis] - left["max"][axis],
            0.0,
        )
        squared += gap * gap
    return math.sqrt(squared)


def overlap_2d(left: dict, right: dict) -> tuple[float, float]:
    dx = max(
        0.0, min(left["max"][0], right["max"][0]) - max(left["min"][0], right["min"][0])
    )
    dy = max(
        0.0, min(left["max"][1], right["max"][1]) - max(left["min"][1], right["min"][1])
    )
    area = dx * dy
    left_area = max(
        1e-9, (left["max"][0] - left["min"][0]) * (left["max"][1] - left["min"][1])
    )
    right_area = max(
        1e-9, (right["max"][0] - right["min"][0]) * (right["max"][1] - right["min"][1])
    )
    return area, area / min(left_area, right_area)


def aabb_union(nodes: list[dict]) -> dict:
    return {
        "min": [min(node["min"][axis] for node in nodes) for axis in range(3)],
        "max": [max(node["max"][axis] for node in nodes) for axis in range(3)],
    }


def cluster_nodes(nodes: list[dict], tolerance: float = 0.08) -> list[dict]:
    by_category: dict[str, list[dict]] = {}
    for node in nodes:
        category = classify(str(node.get("name", "")))
        if category is not None:
            node = {
                "name": str(node["name"]),
                "min": list(map(float, node["min"])),
                "max": list(map(float, node["max"])),
            }
            by_category.setdefault(category, []).append(node)

    groups: list[dict] = []
    for category, records in by_category.items():
        parent = list(range(len(records)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        ordered = sorted(
            range(len(records)), key=lambda index: records[index]["min"][0]
        )
        for position, left_index in enumerate(ordered):
            left = records[left_index]
            limit = left["max"][0] + tolerance
            for right_index in ordered[position + 1 :]:
                right = records[right_index]
                if right["min"][0] > limit:
                    break
                if box_distance(left, right) <= tolerance:
                    union(left_index, right_index)

        components: dict[int, list[dict]] = {}
        for index, record in enumerate(records):
            components.setdefault(find(index), []).append(record)
        for component_nodes in components.values():
            bounds = aabb_union(component_nodes)
            groups.append({"category": category, "nodes": component_nodes, **bounds})
    return groups


def significant_overlap(left: dict, right: dict) -> bool:
    overlap = [
        min(left["max"][axis], right["max"][axis])
        - max(left["min"][axis], right["min"][axis])
        for axis in range(3)
    ]
    if min(overlap) <= 0.0:
        return False
    volume = overlap[0] * overlap[1] * overlap[2]
    left_volume = math.prod(
        max(1e-9, left["max"][axis] - left["min"][axis]) for axis in range(3)
    )
    right_volume = math.prod(
        max(1e-9, right["max"][axis] - right["min"][axis]) for axis in range(3)
    )
    return min(overlap) > 0.01 or (
        volume > 1e-5 and volume / min(left_volume, right_volume) > 0.005
    )


def groups_collide(left: dict, right: dict) -> bool:
    # Common built-in/fixture compositions are treated as one functional asset.
    pair = {left["category"], right["category"]}
    if pair == {"bath_fixture", "storage"}:
        return False
    for left_node in left["nodes"]:
        for right_node in right["nodes"]:
            if significant_overlap(left_node, right_node):
                # Touching a support surface by <=1 cm is allowed.
                vertical = min(
                    abs(left_node["min"][2] - right_node["max"][2]),
                    abs(right_node["min"][2] - left_node["max"][2]),
                )
                if vertical <= 0.01:
                    continue
                return True
    return False


def supported(group: dict, groups: list[dict]) -> bool:
    bottom = group["min"][2]
    # Generated scenes often put the finished floor/sidewalk top at 0.1-0.2 m.
    if -0.10 <= bottom <= 0.30:
        return True
    for parent in groups:
        if parent is group:
            continue
        gap = bottom - parent["max"][2]
        _, ratio = overlap_2d(group, parent)
        if -0.01 <= gap <= 0.05 and ratio >= 0.05:
            return True
    return False


def inside_center(group: dict, roi: tuple[float, float, float, float]) -> bool:
    center_x = 0.5 * (group["min"][0] + group["max"][0])
    center_y = 0.5 * (group["min"][1] + group["max"][1])
    return roi[0] <= center_x <= roi[1] and roi[2] <= center_y <= roi[3]


def oob(group: dict, roi: tuple[float, float, float, float]) -> bool:
    min_x, max_x, min_y, max_y = roi
    width = max(1e-9, group["max"][0] - group["min"][0])
    depth = max(1e-9, group["max"][1] - group["min"][1])
    inside_width = max(0.0, min(group["max"][0], max_x) - max(group["min"][0], min_x))
    inside_depth = max(0.0, min(group["max"][1], max_y) - max(group["min"][1], min_y))
    return 1.0 - (inside_width * inside_depth) / (width * depth) > 0.01


def scene_metrics(path: Path, roi: tuple[float, float, float, float]) -> dict:
    groups = [
        group
        for group in cluster_nodes(json.loads(path.read_text()))
        if inside_center(group, roi)
    ]
    if not groups:
        raise ValueError("no eligible proxy instances")

    collision_ids: set[int] = {
        index for index, group in enumerate(groups) if group["min"][2] < -0.10
    }
    for left_index, left in enumerate(groups):
        for right_index in range(left_index + 1, len(groups)):
            if groups_collide(left, groups[right_index]):
                collision_ids.update((left_index, right_index))
    floating_ids = {
        index for index, group in enumerate(groups) if not supported(group, groups)
    }
    oob_ids = {index for index, group in enumerate(groups) if oob(group, roi)}
    denominator = len(groups)
    return {
        "eligible_objects": denominator,
        "collision_rate": 100.0 * len(collision_ids) / denominator,
        "floating_rate": 100.0 * len(floating_ids) / denominator,
        "oob_rate": 100.0 * len(oob_ids) / denominator,
        "support_validity": 100.0 * (denominator - len(floating_ids)) / denominator,
    }


def specs(domain: str) -> dict[str, dict]:
    path = (BASELINES / "protocol/generation") / (
        "table3/indoor_specs.jsonl" if domain == "indoor" else "urban_specs.jsonl"
    )
    return {
        record["spec_id"]: record
        for record in (
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        )
    }


def roi_for(domain: str, spec: dict) -> tuple[float, float, float, float]:
    if domain == "urban":
        return (-30.0, 30.0, -30.0, 30.0)
    width, depth = map(float, spec["extent_m"][:2])
    return (-width / 2.0, width / 2.0, -depth / 2.0, depth / 2.0)


def official_success_slots(method_dir: str, domain: str) -> set[tuple[str, int]]:
    payload = json.loads(OFFICIAL_RESULTS[method_dir].read_text())
    domain_record = next(
        record for record in payload["domains"] if record["domain"] == domain
    )
    return {
        (str(record["spec_id"]), int(record["logical_seed"]))
        for record in domain_record["per_run"]
        if bool(record.get("success"))
    }


def aggregate(method_dir: str, domain: str) -> dict:
    spec_map = specs(domain)
    allowed_slots = official_success_slots(method_dir, domain)
    metric_names = ("collision_rate", "floating_rate", "oob_rate", "support_validity")
    per_spec: dict[str, list[dict]] = {}
    evaluated = 0
    eligible_total = 0
    for spec_id, spec in spec_map.items():
        records = []
        for seed in range(4):
            path = (
                DATA
                / domain
                / method_dir
                / spec_id
                / f"seed_{seed}"
                / "scene"
                / "geometry.json"
            )
            try:
                if (spec_id, seed) not in allowed_slots:
                    raise OSError("frozen ITT failure")
                result = scene_metrics(path, roi_for(domain, spec))
                evaluated += 1
                eligible_total += result["eligible_objects"]
            except (OSError, ValueError, json.JSONDecodeError):
                result = {
                    "collision_rate": 100.0,
                    "floating_rate": 100.0,
                    "oob_rate": 100.0,
                    "support_validity": 0.0,
                    "eligible_objects": 0,
                }
            records.append(result)
        per_spec[spec_id] = records
    means = {
        metric: sum(
            sum(record[metric] for record in records) / 4.0
            for records in per_spec.values()
        )
        / len(per_spec)
        for metric in metric_names
    }
    return {
        "planned_runs": len(spec_map) * 4,
        "evaluated_runs": evaluated,
        "eligible_proxy_instances": eligible_total,
        **means,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    output = {
        method: {
            domain: aggregate(method_dir, domain) for domain in ("indoor", "urban")
        }
        for method, method_dir in METHODS.items()
    }
    print(json.dumps(output, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
