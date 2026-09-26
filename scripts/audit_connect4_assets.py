"""Measure actual entry clearance in each prepared building before assembly."""
import bpy, json, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import A, O, ENTERABLE

keys = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sorted(ENTERABLE)
report = (
    json.loads((O / "planning/asset_entry_audit.json").read_text())
    if (O / "planning/asset_entry_audit.json").exists()
    else {}
)
for key in keys:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(str(A / (key + ".blend")), link=False) as (src, dst):
        dst.collections = ["ASSET_" + key]
    bpy.context.scene.collection.children.link(dst.collections[0])
    bpy.context.view_layer.update()
    m = json.loads((A / (key + ".json")).read_text())
    s = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    hits = []
    for x in [-0.35, 0, 0.35]:
        for dz in [0.35, 0.65, 1.0, 1.4, 1.7, 1.95]:
            hit, pos, n, face, ob, mat = s.ray_cast(
                dg,
                Vector((x, -6.5, m["floor_z"] + dz)),
                Vector((0, 1, 0)),
                distance=6.5 + m["inside_y"],
            )
            if hit:
                hits.append(dict(x=x, z=dz, object=ob.name, point=list(pos)))
    ground = []
    for y in [-2, -0.5, 0.5, 1.2, m["inside_y"]]:
        hit, p, n, f, ob, ma = s.ray_cast(
            dg, Vector((0, y, m["floor_z"] + 2)), Vector((0, 0, -1)), distance=4
        )
        ground.append(
            dict(y=y, hit=hit, z=p.z if hit else None, object=ob.name if hit else None)
        )
    report[key] = dict(clear=not hits, hits=hits, floor_checks=ground)
    (O / "planning/asset_entry_audit.json").write_text(json.dumps(report, indent=2))
    print(key, "CLEAR" if not hits else json.dumps(hits), flush=True)
