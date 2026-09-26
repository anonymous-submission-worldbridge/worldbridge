#!/usr/bin/env python3
"""Print a compact, read-only inventory of an Infinigen ``.blend`` scene."""

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

import bpy


def jsonable(value):
    try:
        return value.to_list()
    except AttributeError:
        pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


objects = []
for obj in bpy.data.objects:
    dimensions = [float(value) for value in obj.dimensions]
    objects.append(
        {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "collections": [collection.name for collection in obj.users_collection],
            "dimensions": dimensions,
            "location": [float(value) for value in obj.matrix_world.translation],
            "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
            "polygons": len(obj.data.polygons) if obj.type == "MESH" else 0,
            "properties": {key: jsonable(obj[key]) for key in obj.keys()},
        }
    )

summary = {
    "scene": bpy.data.filepath,
    "object_count": len(objects),
    "mesh_count": sum(item["type"] == "MESH" for item in objects),
    "mesh_vertices": sum(item["vertices"] for item in objects),
    "collections": [collection.name for collection in bpy.data.collections],
    "objects": objects,
}
print(
    "TABLE3_INSPECT_JSON="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
