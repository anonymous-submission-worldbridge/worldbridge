import json, sys
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT

registry = json.loads((OUT / "asset_registry.json").read_text())["assets"]
names = [r["source_object"] for r in registry if r.get("source_object")]
path = next(r["source"] for r in registry if r.get("source_object"))
with bpy.data.libraries.load(path, link=False) as (src, dst):
    dst.objects = list(src.objects)
for o in dst.objects:
    if o is not None:
        bpy.context.scene.collection.objects.link(o)
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
for name in names:
    o = bpy.data.objects[name]
    print(
        "SOURCE",
        name,
        [(s.link, s.material.name if s.material else None) for s in o.material_slots],
        flush=True,
    )
    ev = o.evaluated_get(deps)
    m = ev.to_mesh()
    print("EVALUATED", [(x.name if x else None) for x in m.materials], flush=True)
    ev.to_mesh_clear()
