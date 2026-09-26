#!/usr/bin/env python3
"""Evaluate exact road children and reject duplicated seam furniture."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
LAYER_SCRIPT = ROOT / "scripts/render_urban_v1_full_13_zdepth_layer.py"
OUTPUT = CITY / "road_furniture_mesh_audit.json"


def atomic_json(payload: dict) -> None:
    temporary = OUTPUT.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, OUTPUT)


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "full13_road_furniture_zlayer", LAYER_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {LAYER_SCRIPT}")
    layer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = layer
    spec.loader.exec_module(layer)
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    renderer = layer.load_renderer()
    scene, state = layer.build_temporary_scene(layout, "base", renderer)
    evaluation_layer = scene.view_layers[0]
    evaluation_layer.name = "Combined"
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
        bpy.context.window.view_layer = evaluation_layer
    expansion = layer._base_expand(
        scene, state["base_collection"], state["base_copies"]
    )
    furniture = []
    keywords = ("lamp", "light", "traffic", "signal", "pole", "bollard", "sign")
    for obj in state["base_collection"].objects:
        placement_id = str(obj.get("source_placement_id", ""))
        if not placement_id.startswith("full13_road_") or obj.type not in {
            "MESH",
            "CURVE",
        }:
            continue
        lower_name = obj.name.lower()
        if not any(word in lower_name for word in keywords):
            continue
        if obj.type == "MESH" and obj.data is not None:
            points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            center = Vector(
                tuple(
                    (min(p[a] for p in points) + max(p[a] for p in points)) * 0.5
                    for a in range(3)
                )
            )
            extent = tuple(
                max(p[a] for p in points) - min(p[a] for p in points) for a in range(3)
            )
        else:
            center = obj.matrix_world.translation.copy()
            extent = (0.0, 0.0, 0.0)
        furniture.append(
            {
                "object": obj.name,
                "placement_id": placement_id,
                "center": [float(v) for v in center],
                "extent": [float(v) for v in extent],
            }
        )

    # Coincident seam children share nearly the same center and dimensions.
    # A 12 cm center tolerance is far below normal pole spacing while allowing
    # harmless floating-point differences from rotated exact instances.
    grid = {}
    for index, item in enumerate(furniture):
        x, y, z = item["center"]
        key = (round(x / 0.12), round(y / 0.12), round(z / 0.12))
        for gx in range(key[0] - 1, key[0] + 2):
            for gy in range(key[1] - 1, key[1] + 2):
                for gz in range(key[2] - 1, key[2] + 2):
                    grid.setdefault((gx, gy, gz), [])
        grid[key].append(index)
    candidates = set()
    for indices in grid.values():
        for a_pos, first in enumerate(indices):
            for second in indices[a_pos + 1 :]:
                if (
                    furniture[first]["placement_id"]
                    != furniture[second]["placement_id"]
                ):
                    candidates.add((min(first, second), max(first, second)))
    duplicates = []
    for first, second in sorted(candidates):
        a, b = furniture[first], furniture[second]
        distance = math.dist(a["center"], b["center"])
        extent_error = max(abs(x - y) for x, y in zip(a["extent"], b["extent"]))
        if distance <= 0.12 and extent_error <= 0.12:
            duplicates.append(
                {
                    "a": a["object"],
                    "a_placement": a["placement_id"],
                    "b": b["object"],
                    "b_placement": b["placement_id"],
                    "center_distance_m": distance,
                    "maximum_extent_difference_m": extent_error,
                }
            )
    payload = {
        "schema": "agent.full13.road_furniture_mesh_audit.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": layout["run_id"],
        "status": "PASS" if not duplicates else "FAIL",
        "method": "exact dependency-expanded road children; cross-module pole/light/signal center-and-extent coincidence",
        "exact_expansion": expansion,
        "furniture_child_count": len(furniture),
        "duplicate_pairs": duplicates,
        "pass": not duplicates,
    }
    atomic_json(payload)
    print(
        "FULL13_ROAD_FURNITURE_AUDIT",
        json.dumps(
            {
                "status": payload["status"],
                "children": len(furniture),
                "duplicates": len(duplicates),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if duplicates:
        raise RuntimeError(
            f"Duplicated road furniture at module seams: {duplicates[:12]}"
        )


if __name__ == "__main__":
    main()
