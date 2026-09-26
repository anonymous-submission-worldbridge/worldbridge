#!/usr/bin/env python3
"""Read-only exact dependency-graph placement bounds in production packs.

Report the actual evaluated child-object extents, not declared placement AABBs.
The output is diagnostic evidence and never replaces or edits any source mesh.
"""

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
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"


def main() -> None:
    layer = sys.argv[sys.argv.index("--") + 1]
    layout = json.loads((CITY / "layout_plan.json").read_text())
    source = bpy.context.scene
    roots = [
        obj
        for obj in source.objects
        if obj.get("placement_id") in {r["placement_id"] for r in layout["placements"]}
        and obj.instance_collection is not None
    ]
    print(f"FULL13_TRUE_BOUNDS_ROOTS layer={layer} count={len(roots)}", flush=True)
    if not roots:
        raise RuntimeError("No production placement roots in pack")

    # The same data-block instances and parent/child relationships as the
    # production renderer, but no geometry copies and no mesh mutations.
    graph = bpy.context.evaluated_depsgraph_get()
    graph.update()
    root_set = set(roots)
    groups = defaultdict(
        lambda: {
            "count": 0,
            "count_building_height": 0,
            "min": [float("inf")] * 3,
            "max": [-float("inf")] * 3,
            "building_min": [float("inf")] * 3,
            "building_max": [-float("inf")] * 3,
            "centers": [],
        }
    )
    for instance in graph.object_instances:
        if not instance.is_instance or instance.parent is None:
            continue
        parent = instance.parent.original
        if parent not in root_set or instance.object is None:
            continue
        obj = instance.object.original
        if obj.type not in {"MESH", "CURVE", "FONT"} or obj.hide_render:
            continue
        ident = str(parent.get("placement_id"))
        corners = [instance.matrix_world @ Vector(v) for v in obj.bound_box]
        if not corners:
            continue
        bmin = [min(v[i] for v in corners) for i in range(3)]
        bmax = [max(v[i] for v in corners) for i in range(3)]
        group = groups[ident]
        group["count"] += 1
        for i in range(3):
            group["min"][i] = min(group["min"][i], bmin[i])
            group["max"][i] = max(group["max"][i], bmax[i])
        if bmax[2] >= 3 and bmin[2] >= 0:
            group["count_building_height"] += 1
            for i in range(3):
                group["building_min"][i] = min(group["building_min"][i], bmin[i])
                group["building_max"][i] = max(group["building_max"][i], bmax[i])
            group["centers"].append([(bmin[i] + bmax[i]) * 0.5 for i in range(3)])
    records = {r["placement_id"]: r for r in layout["placements"]}
    result = {}
    for ident, group in sorted(groups.items()):
        if group["centers"]:
            centers = sorted(group["centers"])
            group["median_building_center"] = [
                sorted(row[i] for row in centers)[len(centers) // 2] for i in range(3)
            ]
        del group["centers"]
        group["declared_footprint"] = records[ident]["footprint"]
        group["declared_location"] = records[ident]["location"]
        group["source_center"] = records[ident]["source_center"]
        result[ident] = group
        print(
            "FULL13_TRUE_BOUNDS",
            ident,
            json.dumps(
                {
                    "children": group["count"],
                    "true_min": group["min"],
                    "true_max": group["max"],
                    "declared_location": group["declared_location"],
                    "declared_footprint": group["declared_footprint"],
                }
            ),
            flush=True,
        )
    out = CITY / "render_runtime" / "true_asset_bounds_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{layer}.json"
    target.write_text(
        json.dumps(
            {
                "schema": "agent.full13.true_evaluated_placement_bounds.v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": layout["run_id"],
                "source_pack": bpy.data.filepath,
                "layer": layer,
                "production_source_files_saved": False,
                "placements": result,
            },
            indent=2,
        )
    )
    print(
        f"FULL13_TRUE_BOUNDS_PASS layer={layer} source_roots={len(roots)} computed={len(groups)} file={target}",
        flush=True,
    )


if __name__ == "__main__":
    main()
