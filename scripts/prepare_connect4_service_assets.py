"""Reuse the detailed existing fire engine and espresso assembly."""
import bpy, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import A, O
import prepare_connect3_assets as old
from prepare_connect4_assets import reset, load, root, save

old.O = O
old.A = A
old.external(
    "fire_engine", "urban_v3_fire7", ["fire_region_v7:TRUCK_MODERN_LADDER_ENGINE"]
)
reset()
source = A / "cafe.blend"
src = load(source, "ASSET_cafe")
root(src)
c = bpy.data.collections.new("ASSET_espresso_assembly")
root(c)
for ob in src.objects:
    if "espresso" in ob.name.lower():
        c.objects.link(ob.copy())
bpy.context.scene.collection.children.unlink(src)
assert len(c.objects) > 20, "Detailed existing espresso assembly required"
bpy.context.view_layer.update()
info = old.metadata(c)
lo, hi = map(Vector, info["bounds"])
offset = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
for ob in c.objects:
    ob.location += offset
save("espresso_assembly", c, source)
