"""Print a compact audit of a SceneWeaver Blender scene.

This is a diagnostic helper executed by Blender, not an evaluator.  It keeps
the first-pass export rule evidence in the repository instead of relying on
interactive inspection.
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


import json
import sys
from pathlib import Path

import bpy


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit(
            "usage: blender scene.blend --python inspect_sceneweaver_blend.py -- OUTPUT.json"
        )
    output = Path(argv[0])
    records = []
    for obj in bpy.data.objects:
        collections = sorted(collection.name for collection in obj.users_collection)
        record = {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "collections": collections,
            "hide_render": bool(obj.hide_render),
            "hide_viewport": bool(obj.hide_viewport),
            "location": [float(value) for value in obj.location],
            "dimensions": [float(value) for value in obj.dimensions],
            "custom_properties": {
                key: repr(obj[key])[:500]
                for key in sorted(obj.keys())
                if key != "_RNA_UI"
            },
        }
        if obj.type == "MESH":
            record.update(
                {
                    "vertices": len(obj.data.vertices),
                    "polygons": len(obj.data.polygons),
                    "bound_box_world": [
                        list(obj.matrix_world @ __import__("mathutils").Vector(corner))
                        for corner in obj.bound_box
                    ],
                }
            )
        records.append(record)
    payload = {
        "blender_version": bpy.app.version_string,
        "collections": [
            {
                "name": collection.name,
                "parent_names": sorted(
                    possible.name
                    for possible in bpy.data.collections
                    if collection.name in {child.name for child in possible.children}
                ),
                "objects": sorted(obj.name for obj in collection.objects),
                "children": sorted(child.name for child in collection.children),
                "hide_render": bool(collection.hide_render),
                "hide_viewport": bool(collection.hide_viewport),
            }
            for collection in sorted(bpy.data.collections, key=lambda value: value.name)
        ],
        "objects": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"SCENEWEAVER_BLEND_AUDIT objects={len(records)} output={output}")


if __name__ == "__main__":
    main()
