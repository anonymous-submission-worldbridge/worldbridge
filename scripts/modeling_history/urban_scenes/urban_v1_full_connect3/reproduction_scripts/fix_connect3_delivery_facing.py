"""Orient the existing delivery station's shopfront toward the approach."""
import bpy, json, os, sys
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
A = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/shared_assets"
p = A / "delivery.blend"
m = json.loads((A / "delivery.json").read_text())
if m.get("facing_revision") == 2:
    raise SystemExit(0)
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as assets

assets.external("delivery", "urban_v3_delivery6", ["delivery:DELIVERY_STATION"])
m = json.loads((A / "delivery.json").read_text())
c = bpy.data.collections["ASSET_delivery"]
bpy.context.view_layer.update()
center = (Vector(m["bounds"][0]) + Vector(m["bounds"][1])) / 2
tr = (
    Matrix.Translation(center)
    @ Matrix.Rotation(3.141592653589793, 4, "Z")
    @ Matrix.Translation(-center)
)
for ob in c.objects:
    ob.matrix_world = tr @ ob.matrix_world
bpy.context.view_layer.update()
actual = assets.metadata(c)
assert all(
    abs(actual["bounds"][j][k] - m["bounds"][j][k]) < 0.01
    for j in range(2)
    for k in range(3)
), (actual, m)
m.update(actual)
from fix_connect3_fonts import fix

fix()
for lib in bpy.data.libraries:
    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
tmp = A / "delivery.facing.blend"
bpy.data.libraries.write(str(tmp), {c}, path_remap="RELATIVE_ALL", compress=True)
tmp.replace(p)
m["front_facing_corrected"] = True
m["facing_revision"] = 2
(A / "delivery.json").write_text(json.dumps(m, indent=2))
print("DELIVERY_FACING_CORRECTED", flush=True)
