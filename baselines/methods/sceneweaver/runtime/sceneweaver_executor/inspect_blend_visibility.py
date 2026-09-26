"""Print SceneWeaver room collections and visibility from an opened blend."""

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


import bpy


for collection in sorted(bpy.data.collections, key=lambda value: value.name):
    if True:
        print(
            "COLLECTION",
            repr(collection.name),
            f"hide_render={collection.hide_render}",
            f"hide_viewport={collection.hide_viewport}",
            f"objects={len(collection.objects)}",
        )

for obj in sorted(bpy.data.objects, key=lambda value: value.name):
    if (
        "room" in obj.name.lower()
        or "wall" in obj.name.lower()
        or "floor" in obj.name.lower()
    ):
        print(
            "OBJECT",
            repr(obj.name),
            f"type={obj.type}",
            f"hide_render={obj.hide_render}",
            f"hide_viewport={obj.hide_viewport}",
            "collections="
            + repr([collection.name for collection in obj.users_collection]),
            f"vertices={len(obj.data.vertices) if obj.type == 'MESH' else 0}",
            f"polygons={len(obj.data.polygons) if obj.type == 'MESH' else 0}",
            "dimensions="
            + repr(tuple(round(float(value), 4) for value in obj.dimensions)),
            "materials="
            + repr(
                [
                    slot.material.name if slot.material else None
                    for slot in obj.material_slots
                ]
            ),
        )
