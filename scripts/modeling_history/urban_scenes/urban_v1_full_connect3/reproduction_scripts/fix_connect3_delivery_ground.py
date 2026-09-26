"""Ground the existing station using its evaluated mesh envelope."""
import bpy, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as assets

A = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/shared_assets"
p = A / "delivery.blend"
m = json.loads((A / "delivery.json").read_text())
if m.get("grounded"):
    raise SystemExit(0)
assets.reset()
with bpy.data.libraries.load(str(p), link=False) as (a, b):
    b.collections = ["ASSET_delivery"]
c = b.collections[0]
bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.update()
lo = m["bounds"][0][2]
for ob in c.objects:
    ob.location.z -= lo
bpy.context.view_layer.update()
m.update(assets.metadata(c))
print("GROUND_BOUNDS", lo, m["bounds"], flush=True)
assert abs(m["bounds"][0][2]) < 0.001
m["grounded"] = True
m["ground_shift"] = -lo
tmp = A / "delivery.grounded.blend"
bpy.data.libraries.write(str(tmp), {c}, path_remap="RELATIVE_ALL", compress=True)
tmp.replace(p)
(A / "delivery.json").write_text(json.dumps(m, indent=2))
print("STATION_GROUNDED", lo, flush=True)
