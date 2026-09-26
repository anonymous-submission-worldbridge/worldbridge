"""Keep reused native furniture inside the measured asymmetric residential walls."""
import bpy, sys, json, os
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from prepare_connect3_assets import metadata

A = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/shared_assets"
p = A / "townhouse.blend"
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(p), link=False) as (a, b):
    b.collections = ["ASSET_townhouse"]
c = b.collections[0]
bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.update()
rejected = []
for ob in list(c.objects):
    if not ob.get("interior_placement_verified"):
        continue
    pts = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    lo = [min(v[k] for v in pts) for k in range(3)]
    hi = [max(v[k] for v in pts) for k in range(3)]
    if lo[0] < -10.4 or hi[0] > 10.4 or lo[1] < 3.85 or hi[1] > 17.2:
        rejected.append({"object": ob.name, "bounds": [lo, hi]})
        c.objects.unlink(ob)
m = json.loads((A / "townhouse.json").read_text())
m.update(metadata(c))
m["placement_audit"] = "townhouse_interior_placement_audit.json"
(A / "townhouse.json").write_text(json.dumps(m, indent=2))
a = json.loads((A / "townhouse_interior_placement_audit.json").read_text())
a["measured_wall_envelope"] = [[-10.4, 3.85], [10.4, 17.2]]
a["additional_rejected"] = rejected
a["retained_final"] = sum(bool(o.get("interior_placement_verified")) for o in c.objects)
(A / "townhouse_interior_placement_audit.json").write_text(json.dumps(a, indent=2))
for lib in bpy.data.libraries:
    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
tmp = A / "townhouse.refined.blend"
bpy.data.libraries.write(str(tmp), {c}, path_remap="RELATIVE_ALL", compress=True)
tmp.replace(p)
print("MEASURED_ENVELOPE_REPAIR", len(rejected), m, flush=True)
