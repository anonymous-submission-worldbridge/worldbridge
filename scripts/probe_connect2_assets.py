import bpy, json, sys
from pathlib import Path
from collections import Counter
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
key = sys.argv[-1]
paths = {
    "pharmacy": "outdoor_part_demo/urban_v3_pharmacy5/urban_v3_pharmacy5.blend",
    "hospital": "outdoor_part_demo/urban_v3_hospital4/urban_v3_hospital4.blend",
    "library": "outdoor_part_demo/urban_v3_library4/urban_v3_library4.blend",
    "native": "indoor_outdoor_villa_demo2/coarse/scene.blend",
}
p = R / "infinigen/outputs" / paths[key]
if key == "native":
    with bpy.data.libraries.load(str(p)) as (a, b):
        names = [n for n in a.objects if ".spawn_asset(" in n]
    (O / "native_inventory.json").write_text(json.dumps(names, indent=2))
    print(Counter(n.split("(")[0] for n in names), flush=True)
else:
    bpy.ops.wm.open_mainfile(filepath=str(p), load_ui=False)
    cols = [
        {
            "name": c.name,
            "objects": len(c.objects),
            "all_objects": len(c.all_objects),
            "children": [a.name for a in c.children],
        }
        for c in bpy.data.collections
    ]
    objs = []
    for o in bpy.context.scene.objects:
        pts = (
            [o.matrix_world @ Vector(v) for v in o.bound_box]
            if o.type in ("MESH", "FONT", "CURVE")
            else [o.matrix_world.translation]
        )
        objs.append(
            {
                "name": o.name,
                "type": o.type,
                "loc": list(o.matrix_world.translation),
                "bbox": [
                    [min(v[i] for v in pts) for i in range(3)],
                    [max(v[i] for v in pts) for i in range(3)],
                ],
                "role": o.get("c2w_role"),
                "parent": o.parent.name if o.parent else None,
                "collections": [c.name for c in o.users_collection],
            }
        )
    (O / (key + "_inventory.json")).write_text(
        json.dumps({"collections": cols, "objects": objs}, indent=1)
    )
    print(json.dumps(cols), flush=True)
