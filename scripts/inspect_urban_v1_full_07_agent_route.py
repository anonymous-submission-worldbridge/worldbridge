"""Print scene landmarks relevant to the urban_v1_full_07 robot demo."""

from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import json
from pathlib import Path

import bpy


OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/"
    "urban_v1_full_07_agent/scene_landmarks.json"
)


def world_bbox(obj: bpy.types.Object):
    if not obj.bound_box:
        return None
    points = [
        obj.matrix_world @ __import__("mathutils").Vector(corner)
        for corner in obj.bound_box
    ]
    return {
        "min": [round(min(p[i] for p in points), 3) for i in range(3)],
        "max": [round(max(p[i] for p in points), 3) for i in range(3)],
    }


def record(obj: bpy.types.Object):
    return {
        "name": obj.name,
        "type": obj.type,
        "location": [round(v, 3) for v in obj.matrix_world.translation],
        "dimensions": [round(v, 3) for v in obj.dimensions],
        "bbox": world_bbox(obj),
        "instance_collection": obj.instance_collection.name
        if obj.instance_collection
        else None,
        "hide_render": obj.hide_render,
    }


tokens = (
    "convenience",
    "fresh",
    "storefront",
    "door",
    "residential",
    "apartment",
    "house",
    "crosswalk",
    "road_",
    "sidewalk",
)
matches = [
    record(obj)
    for obj in bpy.context.scene.objects
    if any(token in obj.name.lower() for token in tokens)
]

payload = {
    "scene": bpy.context.scene.name,
    "object_count": len(bpy.context.scene.objects),
    "collection_count": len(bpy.data.collections),
    "matches": matches,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"AGENT_ROUTE_INSPECT={OUT}")
print(f"AGENT_ROUTE_MATCHES={len(matches)}")
