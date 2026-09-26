import bpy, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as A

# Freeze saved articulation for static contextual placement, retaining full geometry.
for key, names in [
    ("delivery", ["delivery:DELIVERY_STATION"]),
    ("parcel", ["delivery:PARCEL_LOCKER"]),
    ("food_locker", ["delivery:FOOD_DELIVERY_LOCKER"]),
]:
    A.external(key, "urban_v3_delivery6", names)
A.external("atm", "urban_v3_atm4", ["urban_v3_atm4:ATM_01A_SILVER_FREESTANDING"])
A.reset()
f = next((A.P / "urban_v3_factory3").glob("*.blend"))
with bpy.data.libraries.load(str(f), link=False) as (a, b):
    b.objects = [n for n in a.objects if n.startswith("urban:factory:1:")]
c = bpy.data.collections.new("factory")
bpy.context.scene.collection.children.link(c)
for o in b.objects:
    c.objects.link(o)
bpy.context.view_layer.update()
poses = {o: o.matrix_world.copy() for o in c.objects}
for o, m in poses.items():
    o.parent = None
    o.constraints.clear()
    o.animation_data_clear()
    o.matrix_world = m
A.save("factory", c, f)
A.external(
    "lake",
    "urban_v3_lake3",
    [
        "urban:lake3:landscape",
        "urban:lake3:paths",
        "urban:lake3:pavilion",
        "urban:lake3:furnishings",
    ],
)
