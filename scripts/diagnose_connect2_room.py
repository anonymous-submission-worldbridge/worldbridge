import bpy, sys, json
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

key = sys.argv[-1]
dest = B.OUT / key
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
s = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
report = {"rays": [], "objects": []}
for p in [(0, -2, 2), (0, 2.3, 2), (0, 5, 2), (0, 8, 2), (-4, 6, 2), (4, 6, 2)]:
    for d in [(0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)]:
        hit, loc, n, i, o, m = s.ray_cast(dg, Vector(p), Vector(d), distance=25)
        if hit:
            report["rays"].append(
                {
                    "p": p,
                    "d": d,
                    "object": o.name,
                    "role": o.get("c2w_role"),
                    "at": list(loc),
                    "distance": (loc - Vector(p)).length,
                }
            )
for o in bpy.data.collections["Architecture_and_furnished_interior"].objects:
    if o.type != "MESH":
        continue
    a, b = B.bounds(o)
    if (
        all(b[k] > [-8, 0, 0.3][k] and a[k] < [8, 12, 4.4][k] for k in range(3))
        and max(o.dimensions) > 2
    ):
        report["objects"].append(
            {
                "name": o.name,
                "role": o.get("c2w_role"),
                "bbox": [list(a), list(b)],
                "modifiers": [(m.name, m.type) for m in o.modifiers],
            }
        )
(dest / "room_diagnostic.json").write_text(json.dumps(report, indent=1))
print("ROOM_DIAGNOSED", key)
