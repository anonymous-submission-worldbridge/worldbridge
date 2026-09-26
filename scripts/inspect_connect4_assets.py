"""Read existing authored assemblies, retaining measured inventories for planning."""
import bpy, json, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect4"
A = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/shared_assets"
O.mkdir(exist_ok=True)
(O / "planning").mkdir(exist_ok=True)
for key in [
    "bar",
    "corner_store",
    "police",
    "fire",
    "delivery",
    "gas",
    "bank",
    "school",
    "gym",
]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(str(A / (key + ".blend")), link=False) as (src, dst):
        dst.collections = ["ASSET_" + key]
    c = dst.collections[0]
    bpy.context.scene.collection.children.link(c)
    bpy.context.view_layer.update()
    items = []
    for ob in c.all_objects:
        pts = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
        items.append(
            dict(
                name=ob.name,
                type=ob.type,
                loc=list(ob.matrix_world.translation),
                bounds=[
                    [min(p[k] for p in pts) for k in range(3)],
                    [max(p[k] for p in pts) for k in range(3)],
                ],
                collection=ob.instance_collection.name
                if ob.instance_collection
                else None,
                semantic=ob.get("c2w_semantic", ob.get("semantic", "")),
            )
        )
    (O / "planning" / (key + "_inventory.json")).write_text(json.dumps(items, indent=1))
    names = [o["name"] for o in items]
    print(
        key,
        len(items),
        "furniture",
        sum(
            any(
                t in n.lower()
                for t in [
                    "chair",
                    "desk",
                    "shelf",
                    "counter",
                    "bench",
                    "table",
                    "bed",
                    "rack",
                ]
            )
            for n in names
        ),
        flush=True,
    )
for folder in ["urban_v3_fountain3", "urban_v3_all43_25", "urban_v3_all45_09"]:
    p = R / "infinigen/outputs/outdoor_part_demo" / folder / (folder + ".blend")
    with bpy.data.libraries.load(str(p), link=True) as (src, dst):
        (O / "planning" / (folder + "_collections.json")).write_text(
            json.dumps(src.collections, indent=1)
        )
