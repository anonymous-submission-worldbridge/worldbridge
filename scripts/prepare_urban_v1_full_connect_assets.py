import bpy, json
from pathlib import Path
from mathutils import Matrix, Vector

root = Path(__file__).resolve().parents[1]
source = root / "infinigen/outputs/indoor_outdoor_villa_demo2/coarse/scene.blend"
output = (
    root / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect/shared_assets"
)
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source), link=False) as (a, b):
    names = []
    for factory in ["ChairFactory", "PlateFactory", "BowlFactory", "VaseFactory"]:
        names.append(
            next(
                n
                for n in sorted(a.objects)
                if n.startswith(factory + "(") and ".spawn_asset(" in n
            )
        )
    b.objects = names
cols = []
report = []
for o in b.objects:
    factory = o.name.split("(")[0]
    c = bpy.data.collections.new("NATIVE_" + factory)
    bpy.context.scene.collection.children.link(c)
    c.objects.link(o)
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
    o.hide_render = False
    o.hide_viewport = False
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(p) for p in o.bound_box]
    mn = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    mx = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    o.location = (-0.5 * (mn.x + mx.x), -0.5 * (mn.y + mx.y), -mn.z)
    o["original_procedural_asset"] = o.name
    o["source_blend"] = str(source)
    report.append(
        {
            "name": o.name,
            "collection": c.name,
            "dimensions": list(mx - mn),
            "vertices": len(o.data.vertices) if o.type == "MESH" else None,
            "modifiers": [(m.name, m.type) for m in o.modifiers],
        }
    )
    cols.append(c)
bpy.data.libraries.write(
    str(output / "native_indoor_assets.blend"), set(cols), compress=True
)
(output / "native_indoor_assets.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
tree_file = output / "reference08_tree.blend"
if not tree_file.exists():
    reference = (
        root
        / "infinigen/outputs/outdoor_full_demo/urban_v1_full_08/urban_v1_full_08.blend"
    )
    with bpy.data.libraries.load(str(reference), link=False) as (available, requested):
        requested.collections = ["full02:MASTER:TreeFactory:42"]
    bpy.data.libraries.write(str(tree_file), set(requested.collections), compress=True)
