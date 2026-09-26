"""Emit a compact structural and bounds report for a Blender asset scene.

Run with Blender after opening the blend to inspect::

    blender --background source.blend --python scripts/inspect_blend_asset.py -- report.json

The utility is intentionally read-only.  It is used by large-scene composers to
identify scene-root collections, directly linked objects, and world-space
footprints without guessing from object origins.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector


GEOMETRY_TYPES = {"MESH", "CURVE", "FONT", "SURFACE", "META"}


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _bounds(objects):
    points = []
    for obj in objects:
        if obj.type not in GEOMETRY_TYPES or obj.hide_render:
            continue
        try:
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
        except (AttributeError, ReferenceError, RuntimeError):
            continue
    if not points:
        return None
    values = {
        "min": [min(point[index] for point in points) for index in range(3)],
        "max": [max(point[index] for point in points) for index in range(3)],
    }
    if not all(_finite(value) for row in values.values() for value in row):
        return None
    values["size"] = [values["max"][index] - values["min"][index] for index in range(3)]
    values["center"] = [
        (values["max"][index] + values["min"][index]) / 2 for index in range(3)
    ]
    return values


def _object_bounds(obj):
    if obj.type not in GEOMETRY_TYPES:
        return None
    try:
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    except (AttributeError, ReferenceError, RuntimeError):
        return None
    minimum = [min(point[index] for point in points) for index in range(3)]
    maximum = [max(point[index] for point in points) for index in range(3)]
    size = [maximum[index] - minimum[index] for index in range(3)]
    return {"min": minimum, "max": maximum, "size": size}


def main(output_path: Path) -> None:
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    all_scene_objects = list(scene.objects)
    child_names = {
        child.name
        for collection in bpy.data.collections
        for child in collection.children
    }
    roots = list(scene.collection.children)
    direct = list(scene.collection.objects)
    object_bounds = [(obj, _object_bounds(obj)) for obj in all_scene_objects]
    object_bounds = [(obj, bounds) for obj, bounds in object_bounds if bounds]

    def collection_record(collection):
        return {
            "name": collection.name,
            "hide_render": bool(collection.hide_render),
            "object_count_recursive": len(collection.all_objects),
            "direct_object_count": len(collection.objects),
            "child_count": len(collection.children),
            "bounds": _bounds(collection.all_objects),
            "properties": {
                key: collection[key]
                for key in collection.keys()
                if isinstance(collection[key], (bool, int, float, str))
            },
        }

    report = {
        "blend": bpy.data.filepath,
        "scene": scene.name,
        "scene_root_collection": scene.collection.name,
        "scene_bounds": _bounds(all_scene_objects),
        "scene_object_count": len(all_scene_objects),
        "scene_type_counts": dict(
            sorted(Counter(obj.type for obj in all_scene_objects).items())
        ),
        "largest_geometry_objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "hide_render": bool(obj.hide_render),
                "bounds": bounds,
                "users_collection": [
                    collection.name for collection in obj.users_collection
                ],
            }
            for obj, bounds in sorted(
                object_bounds,
                key=lambda item: item[1]["size"][0] * item[1]["size"][1],
                reverse=True,
            )[:30]
        ],
        "direct_scene_objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "hide_render": bool(obj.hide_render),
                "location": list(obj.location),
            }
            for obj in direct
        ],
        "root_collections": [collection_record(collection) for collection in roots],
        "root_child_collections": [
            {
                "parent": root.name,
                **collection_record(collection),
            }
            for root in roots
            for collection in root.children
        ],
        "unparented_datablock_collections": sorted(
            collection.name
            for collection in bpy.data.collections
            if collection.name not in child_names and collection not in roots
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(f"C2W_ASSET_REPORT={output_path}", flush=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit("expected exactly one output JSON path after --")
    main(Path(argv[0]).resolve())
