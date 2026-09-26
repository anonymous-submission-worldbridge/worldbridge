"""Extract authored, fully generated Infinigen objects, never placeholders."""
import bpy, json
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/shared_assets"
S = R / "infinigen/outputs/indoor_outdoor_villa_demo2/coarse/scene.blend"
bpy.ops.wm.read_factory_settings(use_empty=True)
factories = {
    "CupFactory": 3,
    "BottleFactory": 3,
    "JarFactory": 2,
    "FoodBoxFactory": 2,
    "FoodBagFactory": 2,
    "WineglassFactory": 2,
    "PotFactory": 2,
    "PanFactory": 2,
    "SpoonFactory": 1,
    "ChopsticksFactory": 1,
    "OvenFactory": 1,
    "KitchenCabinetFactory": 1,
    "PlantContainerFactory": 2,
    "DeskLampFactory": 2,
    "BookStackFactory": 3,
    "BookColumnFactory": 2,
    "SimpleBookcaseFactory": 2,
    "SimpleDeskFactory": 1,
    "SofaFactory": 1,
    "MonitorFactory": 1,
    "PillowFactory": 2,
    "BlanketFactory": 1,
}
with bpy.data.libraries.load(str(S), link=False) as (a, b):
    b.objects = [
        n
        for f, count in factories.items()
        for n in sorted(
            n for n in a.objects if n.startswith(f + "(") and ".spawn_asset(" in n
        )[:count]
    ]
cols = []
report = []
counter = {}
for obj in b.objects:
    f = obj.name.split("(")[0]
    i = counter.get(f, 0)
    counter[f] = i + 1
    c = bpy.data.collections.new(f"NATIVE_{f}_{i}")
    bpy.context.scene.collection.children.link(c)
    c.objects.link(obj)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.hide_render = False
    obj.hide_viewport = False
    bpy.context.view_layer.update()
    pts = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    mn = Vector([min(p[k] for p in pts) for k in range(3)])
    mx = Vector([max(p[k] for p in pts) for k in range(3)])
    obj.location = (-0.5 * (mn.x + mx.x), -0.5 * (mn.y + mx.y), -mn.z)
    obj["asset_source_blend"] = str(S)
    obj["asset_factory"] = f
    obj["asset_quality"] = "full_generated_mesh"
    report.append(
        {
            "collection": c.name,
            "source_object": obj.name,
            "dimensions": list(mx - mn),
            "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
        }
    )
    cols.append(c)
bpy.data.libraries.write(str(O / "native_extended.blend"), set(cols), compress=True)
(O / "native_extended.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
