import bpy, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A

for folder in ["urban_v3_fountain3", "urban_v3_all43_25", "urban_v3_fire7"]:
    p = next((R / "infinigen/outputs/outdoor_part_demo" / folder).glob("*.blend"))
    with bpy.data.libraries.load(str(p), link=True) as (src, dst):
        (O / "planning" / (folder + "_collections.json")).write_text(
            json.dumps(src.collections, indent=1)
        )
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(A / "corner_store.blend"), link=False) as (src, dst):
    dst.collections = ["ASSET_corner_store"]
c = dst.collections[0]
bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.update()
ob = next(o for o in c.objects if "chamfered_corner_double_entry" in o.name)
print("CORNER_ENTRY", list(ob.location), list(ob.rotation_euler), flush=True)
for ob in ob.instance_collection.objects:
    print(ob.name, list(ob.location), list(ob.dimensions), flush=True)
