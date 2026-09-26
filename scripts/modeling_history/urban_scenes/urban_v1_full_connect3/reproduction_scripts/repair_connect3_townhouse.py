"""Reject native furnishings extending through the existing residential facade."""
import bpy, sys, json, os
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
A = O / "shared_assets"
p = A / "townhouse.blend"
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(p), link=False) as (a, b):
    b.collections = ["ASSET_townhouse"]
c = b.collections[0]
bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.update()
roots = [
    ob for ob in c.objects if ob.instance_collection and "native_indoor" in ob.name
]
report = {"roots": [ob.name for ob in roots], "retained": 0, "rejected": []}
if not roots and (A / "townhouse_interior_placement_audit.json").exists():
    print("TOWNHOUSE_ALREADY_REPAIRED")
    sys.exit(0)
assert roots, "Native interior roots missing"


def visit(collection, transform):
    tr = transform @ Matrix.Translation(-collection.instance_offset)
    for src in collection.all_objects:
        mw = tr @ src.matrix_world
        if src.instance_collection:
            visit(src.instance_collection, mw)
            continue
        if src.type not in {"MESH", "CURVE", "FONT", "LIGHT"} or src.hide_render:
            continue
        pts = [mw @ Vector(v) for v in src.bound_box]
        lo = Vector([min(v[k] for v in pts) for k in range(3)])
        hi = Vector([max(v[k] for v in pts) for k in range(3)])
        if lo.x < -11.9 or hi.x > 11.9 or lo.y < 1.0 or hi.y > 18.5:
            report["rejected"].append(
                {"object": src.name, "bounds": [list(lo), list(hi)]}
            )
            continue
        ob = src.copy()
        ob.parent = None
        ob.constraints.clear()
        ob.animation_data_clear()
        c.objects.link(ob)
        ob.matrix_world = mw
        ob["source_object"] = src.name
        ob["interior_placement_verified"] = True
        report["retained"] += 1


for root in roots:
    visit(root.instance_collection, root.matrix_world.copy())
    c.objects.unlink(root)
for lib in bpy.data.libraries:
    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
sys.path.insert(0, str(R / "scripts"))
from prepare_connect3_assets import metadata

meta = json.loads((A / "townhouse.json").read_text())
meta.update(metadata(c))
meta["placement_audit"] = "townhouse_interior_placement_audit.json"
(A / "townhouse.json").write_text(json.dumps(meta, indent=2))
tmp = A / "townhouse.repaired.blend"
bpy.data.libraries.write(str(tmp), {c}, path_remap="RELATIVE_ALL", compress=True)
tmp.replace(p)
(A / "townhouse_interior_placement_audit.json").write_text(json.dumps(report, indent=2))
print(
    "TOWNHOUSE_INTERIOR_REPAIRED",
    report["retained"],
    "rejected",
    len(report["rejected"]),
    flush=True,
)
