"""Anchor the complete authored townhouse to its structural foundation."""
import bpy, json, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as assets

A = assets.A
p = A / "townhouse.blend"
m = json.loads((A / "townhouse.json").read_text())
if m.get("foundation_grounded"):
    raise SystemExit(0)
assets.reset()
with bpy.data.libraries.load(str(p), link=False) as (a, b):
    b.collections = ["ASSET_townhouse"]
c = b.collections[0]
bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.update()
f = next(o for o in c.objects if "townhouse_01_foundation" in o.name)
lo = min((f.matrix_world @ Vector(v)).z for v in f.bound_box)
for ob in c.objects:
    ob.location.z -= lo
bpy.context.view_layer.update()
assert abs(min((f.matrix_world @ Vector(v)).z for v in f.bound_box)) < 0.001
m.update(assets.metadata(c))
m["foundation_grounded"] = True
m["ground_shift"] = -lo
tmp = A / "townhouse.grounded.blend"
bpy.data.libraries.write(str(tmp), {c}, path_remap="RELATIVE_ALL", compress=True)
tmp.replace(p)
(A / "townhouse.json").write_text(json.dumps(m, indent=2))
print("TOWNHOUSE_FOUNDATION_GROUNDED", lo, flush=True)
