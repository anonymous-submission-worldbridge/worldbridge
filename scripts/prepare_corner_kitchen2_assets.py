"""Extract full native Infinigen factory results with traceable provenance."""
import bpy
import json
from pathlib import Path
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "infinigen/outputs/indoor_outdoor_villa_demo2/coarse/scene.blend"
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect/corner_kitchen2/assets"
)
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
factories = {
    "TableDiningFactory": 1,
    "ChairFactory": 1,
    "CupFactory": 6,
    "PlateFactory": 1,
    "PlantContainerFactory": 4,
    "LargePlantContainerFactory": 4,
}
with bpy.data.libraries.load(str(SOURCE), link=False) as (available, requested):
    requested.objects = [
        n
        for f, count in factories.items()
        for n in sorted(
            n
            for n in available.objects
            if n.startswith(f + "(") and ".spawn_asset(" in n
        )[:count]
    ]
collections, report, counts = [], [], {}
for obj in requested.objects:
    name = obj.name
    factory = name.split("(")[0]
    index = counts.get(factory, 0)
    counts[factory] = index + 1
    col = bpy.data.collections.new(f"CK2_NATIVE_{factory}_{index}")
    bpy.context.scene.collection.children.link(col)
    col.objects.link(obj)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.hide_render = obj.hide_viewport = False
    bpy.context.view_layer.update()
    points = [Vector(v) for v in obj.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    obj.location = (-0.5 * (lo.x + hi.x), -0.5 * (lo.y + hi.y), -lo.z)
    obj["asset_factory"] = factory
    obj["original_factory_object"] = name
    obj["asset_source_blend"] = str(SOURCE)
    collections.append(col)
    report.append(
        dict(
            collection=col.name,
            factory=factory,
            original_object=name,
            dimensions=list(hi - lo),
            vertices=len(obj.data.vertices),
            materials=[m.name for m in obj.data.materials if m],
            source_blend=str(SOURCE),
        )
    )
bpy.data.libraries.write(
    str(OUT / "native_outdoor.blend"), set(collections), compress=True
)
(OUT / "native_outdoor.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2), flush=True)
