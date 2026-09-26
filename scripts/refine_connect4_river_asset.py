"""Retain the authored river/bridge and add existing botanical bank geometry."""
import bpy, sys, json, os
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import A
from prepare_connect4_assets import reset, load, root, save, inst

reset()
source = A / "river.blend"
c = load(source, "ASSET_river")
root(c)
grass = load(A / "botanical_island.blend", "ASSET_botanical_island", True)
bpy.context.view_layer.update()
s = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
places = []
for x in [-9, -5, 5, 9]:
    for y in [4, 10, 16, 27, 33, 39]:
        hit, p, n, f, ob, mat = s.ray_cast(
            dg, Vector((x, y, 8)), Vector((0, 0, -1)), distance=12
        )
        if hit and n.z > 0.65 and "water" not in ob.name:
            places.append((x, y, p.z + 0.004))
for i, p in enumerate(places):
    inst(c, grass, "existing_bank_groundcover", p, 0.55, (i % 5) * 0.7)
extension = bpy.data.collections.new("ASSET_river_extension")
for ob in c.objects:
    if not any(t in ob.name.lower() for t in ["bridge", "railing", "handrail"]):
        extension.objects.link(ob)
for lib in bpy.data.libraries:
    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
bpy.data.libraries.write(
    str(A / "river_extension.blend"),
    {extension},
    path_remap="RELATIVE_ALL",
    compress=True,
)
meta = json.loads((A / "river.json").read_text())
meta["bank_groundcover_instances"] = len(places)
meta["bank_revision"] = 1
bpy.data.libraries.write(
    str(A / "river.refined.blend"), {c}, path_remap="RELATIVE_ALL", compress=True
)
(A / "river.refined.blend").replace(A / "river.blend")
(A / "river.json").write_text(json.dumps(meta, indent=2))
print("REFINED_EXISTING_RIVER", len(places), flush=True)
