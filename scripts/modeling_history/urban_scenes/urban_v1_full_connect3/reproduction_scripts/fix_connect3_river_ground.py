"""Use an existing closed paving solid to form the river terrain opening."""
import bpy, sys, json
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect3 as B

k = "waterside_dining"
d = B.O / k
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
c = bpy.data.collections["Connected_streets_and_landscape"]
old = next(o for o in c.objects if "continuous_ground" in o.name)
mat = old.material_slots[0].material
for ob in list(c.objects):
    if "continuous_ground" in ob.name and ob != old:
        bpy.data.objects.remove(ob, do_unlink=True)
with bpy.data.libraries.load(str(B.A / "site_components.blend"), link=True) as (a, b):
    b.collections = ["ASSET_asphalt"]
src = list(b.collections[0].objects)[0]
bpy.data.objects.remove(old, do_unlink=True)
g = B.copy_part(c, src, "continuous_ground", (0, 0, -0.12), (1800, 2000, 0.2))
g.data = g.data.copy()
g.material_slots[0].link = "OBJECT"
g.material_slots[0].material = mat
g.modifiers.clear()
water = next(
    o
    for o in c.objects
    if o.instance_collection and o.instance_collection.name == "ASSET_river"
)
channel = next(
    o for o in water.instance_collection.objects if "incised_alluvial_channel" in o.name
)
bpy.context.view_layer.update()
ps = [water.matrix_world @ channel.matrix_world @ Vector(v) for v in channel.bound_box]
lo = [min(v[i] for v in ps) for i in range(3)]
hi = [max(v[i] for v in ps) for i in range(3)]
# Four complete copies of the existing paving solid surround the source channel.
# This avoids coplanar boolean faces filling the below-grade water surface.
bpy.data.objects.remove(g, do_unlink=True)
x0, x1 = lo[0] + 0.02, hi[0] - 0.02
y0, y1 = lo[1] + 0.02, hi[1] - 0.02
for name, xa, xb, ya, yb in [
    ("west", -900, x0, -1000, 1000),
    ("east", x1, 900, -1000, 1000),
    ("south", x0, x1, -1000, y0),
    ("north", x0, x1, y1, 1000),
]:
    g = B.copy_part(
        c,
        src,
        "continuous_ground_" + name,
        ((xa + xb) / 2, (ya + yb) / 2, -0.12),
        (xb - xa, yb - ya, 0.2),
    )
    g.data = g.data.copy()
    g.material_slots[0].link = "OBJECT"
    g.material_slots[0].material = mat
    g.modifiers.clear()
bpy.context.view_layer.update()
m[
    "water_ground_connected"
] = "Four existing paving solids surround measured full channel envelope"
m["river_ground_revision"] = 3
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
print("RIVER_GROUND_FIXED", len(g.data.vertices), lo, hi, flush=True)
