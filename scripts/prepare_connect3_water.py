"""Extract the actual modeled basin, water and shore, excluding large scenery."""
import bpy, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as A

A.reset()
f = A.P / "urban_v3_lake3/urban_v3_lake3.blend"
with bpy.data.libraries.load(str(f), link=False) as (a, b):
    b.objects = [n for n in a.objects if n.startswith("urban:lake:reference:")]
c = bpy.data.collections.new("water_and_shore")
bpy.context.scene.collection.children.link(c)
for ob in b.objects:
    c.objects.link(ob)
bpy.context.view_layer.update()
poses = {ob: ob.matrix_world.copy() for ob in c.objects}
for ob, m in poses.items():
    ob.parent = None
    ob.constraints.clear()
    ob.animation_data_clear()
    ob.matrix_world = m
A.save("lake", c, f)
