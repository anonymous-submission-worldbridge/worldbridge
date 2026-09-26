#!/usr/bin/env python3
"""Create and evaluate the independent 50-scene indoor threshold suite."""

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


import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = _BASELINE_PROJECT_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.evaluation.geometry.metrics.eval_navigability import build_recast
from baselines.evaluation.geometry.metrics.eval_navigability import components
from baselines.evaluation.geometry.metrics.eval_navigability import mesh_area
from baselines.evaluation.geometry.metrics.geometry import box_mesh


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFINITIONS = BASELINES / "protocol/geometry/reference_indoor.jsonl"
RESULT = BASELINES / "evaluation/geometry/results/reference_indoor_calibration.json"
THRESHOLDS = BASELINES / "protocol/geometry/reference_thresholds.json"
AGENT = BASELINES / "protocol/geometry/agent.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def room_layout(category: str, variant: int) -> dict:
    width = (
        5.4
        + 0.25 * (variant % 5)
        + (0.4 if category in {"living_room", "dining_room"} else 0.0)
    )
    depth = (
        4.6 + 0.22 * ((variant * 3) % 5) + (0.35 if category == "living_room" else 0.0)
    )
    jitter = 0.04 * ((variant % 3) - 1)
    if category == "bedroom":
        boxes = [
            [1.35, depth - 1.15, 2.0, 1.6, 0.65],
            [width - 0.45, depth - 1.05, 0.6, 1.55, 2.0],
            [2.6, depth - 0.55, 0.45, 0.45, 0.55],
        ]
    elif category == "living_room":
        boxes = [
            [1.35, depth - 0.55, 2.2, 0.8, 0.9],
            [width - 0.55, depth / 2, 0.65, 1.8, 0.75],
            [width / 2 + jitter, depth / 2 + 0.25, 1.15, 0.7, 0.5],
        ]
    elif category == "kitchen":
        boxes = [
            [width / 2, depth - 0.38, width - 1.0, 0.65, 0.92],
            [width - 0.38, depth / 2, 0.65, depth - 1.0, 0.92],
            [width / 2 - 0.3 + jitter, depth / 2 - 0.2, 1.4, 0.7, 0.92],
        ]
    elif category == "bathroom":
        boxes = [
            [width - 0.45, depth - 0.75, 0.65, 1.3, 0.6],
            [width - 0.45, 0.75, 0.65, 0.65, 0.85],
            [1.0, depth - 0.45, 1.5, 0.7, 0.6],
        ]
    else:
        boxes = [
            [width / 2 + jitter, depth / 2, 1.9, 0.95, 0.76],
            [1.0, depth - 0.42, 1.4, 0.6, 1.0],
            [width - 0.45, depth - 0.75, 0.65, 1.3, 0.9],
        ]
    return {
        "reference_id": f"reference_{category}_{variant:02d}",
        "category": category,
        "variant": variant,
        "width_m": width,
        "depth_m": depth,
        "height_m": 2.8,
        "door_center_m": [0.0, depth / 2, 0.0],
        "spawn_m": [0.55, depth / 2, 0.0],
        "objects": [
            {"center_xy_m": [x, y], "size_xyz_m": [sx, sy, sz]}
            for x, y, sx, sy, sz in boxes
        ],
        "validation": "deterministic non-overlap, wall-contained, floor-supported box layout",
    }


def geometry(record: dict, include_objects: bool):
    width = record["width_m"]
    depth = record["depth_m"]
    vertices = np.asarray(
        [[0, 0, 0], [width, 0, 0], [width, depth, 0], [0, depth, 0]], dtype=np.float32
    )
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    parts = [(vertices, faces)]
    if include_objects:
        for item in record["objects"]:
            sx, sy, sz = item["size_xyz_m"]
            x, y = item["center_xy_m"]
            parts.append(box_mesh([x, y, sz / 2], np.eye(3), [sx / 2, sy / 2, sz / 2]))
    merged_vertices = []
    merged_faces = []
    offset = 0
    for part_vertices, part_faces in parts:
        merged_vertices.append(np.asarray(part_vertices, dtype=np.float32))
        merged_faces.append(np.asarray(part_faces, dtype=np.int32) + offset)
        offset += len(part_vertices)
    return np.concatenate(merged_vertices), np.concatenate(merged_faces)


def main() -> None:
    categories = ["bedroom", "living_room", "kitchen", "bathroom", "dining_room"]
    records = [
        room_layout(category, variant)
        for category in categories
        for variant in range(10)
    ]
    DEFINITIONS.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    config = json.loads(AGENT.read_text(encoding="utf-8"))
    rows = []
    temporary_root = BASELINES / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="table3-reference-", dir=temporary_root
    ) as directory:
        directory = Path(directory)
        for record in records:
            reference_vertices, reference_faces = geometry(record, False)
            final_vertices, final_faces = geometry(record, True)
            reference_path = directory / "reference.npz"
            final_path = directory / "final.npz"
            np.savez_compressed(
                reference_path, vertices=reference_vertices, faces=reference_faces
            )
            np.savez_compressed(final_path, vertices=final_vertices, faces=final_faces)
            ref_nav_vertices, ref_nav_faces = build_recast(reference_path, config, 0.0)
            final_nav_vertices, final_nav_faces = build_recast(final_path, config, 0.0)
            reference_area = mesh_area(ref_nav_vertices, ref_nav_faces)
            final_area = mesh_area(final_nav_vertices, final_nav_faces)
            component_rows = components(final_nav_vertices, final_nav_faces)
            largest = component_rows[0]["area_m2"] if component_rows else 0.0
            rows.append(
                {
                    "reference_id": record["reference_id"],
                    "navigable_area_ratio": 100.0
                    * min(1.0, final_area / reference_area),
                    "connected_area_ratio": 100.0 * largest / final_area,
                    "reference_area_m2": reference_area,
                    "final_area_m2": final_area,
                    "component_count": len(component_rows),
                }
            )
    navigable = np.asarray([row["navigable_area_ratio"] for row in rows])
    connected = np.asarray([row["connected_area_ratio"] for row in rows])
    thresholds = {
        "domain": "indoor",
        "reference_count": len(rows),
        "percentile": 5,
        "navigable_area_ratio": float(np.percentile(navigable, 5)),
        "connected_area_ratio": float(np.percentile(connected, 5)),
        "reference_definitions_sha256": sha256(DEFINITIONS),
        "agent_sha256": sha256(AGENT),
    }
    atomic_json(THRESHOLDS, thresholds)
    atomic_json(
        RESULT,
        {
            "suite": "independent deterministic valid indoor box-layout reference suite",
            "definition": str(DEFINITIONS),
            "thresholds": thresholds,
            "summary": {
                "navigable_min": float(navigable.min()),
                "navigable_median": float(np.median(navigable)),
                "navigable_max": float(navigable.max()),
                "connected_min": float(connected.min()),
                "connected_median": float(np.median(connected)),
                "connected_max": float(connected.max()),
            },
            "scenes": rows,
        },
    )
    print(json.dumps(thresholds, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
