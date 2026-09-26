"""Place original full-resolution tree roots on the actual local support surface."""
import bpy, json, sys
from pathlib import Path
from mathutils import Vector, Matrix

O = (
    Path(__file__).resolve().parents[1]
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
)
key = sys.argv[-1]
d = O / key
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
c = bpy.data.collections["Detailed_public_realm"]
ground = next(o for o in c.objects if "compact_site_base" in o.name)
paving = next(o for o in c.objects if "pedestrian_forecourt" in o.name)


def bounds(o):
    p = [o.matrix_world @ Vector(v) for v in o.bound_box]
    return Vector(tuple(min(v[k] for v in p) for k in range(3))), Vector(
        tuple(max(v[k] for v in p) for k in range(3))
    )


_, gmax = bounds(ground)
pmin, pmax = bounds(paving)
records = []
for o in c.objects:
    if not o.instance_collection or "TreeFactory" not in o.instance_collection.name:
        continue
    master = o.instance_collection
    pts = [
        o.matrix_world
        @ Matrix.Translation(-master.instance_offset)
        @ s.matrix_world
        @ Vector(v)
        for s in master.all_objects
        if s.type == "MESH"
        for v in s.bound_box
    ]
    low = min(v.z for v in pts)
    support = (
        pmax.z
        if pmin.x < o.location.x < pmax.x and pmin.y < o.location.y < pmax.y
        else gmax.z
    )
    # Root tips penetrate their support by 2 cm, avoiding visible tangency gaps.
    shift = support - 0.02 - low
    o.location.z += shift
    records.append(
        {
            "object": o.name,
            "previous_lowest_z": low,
            "support_z": support,
            "shift_z": shift,
            "root_bottom_z": low + shift,
        }
    )
m = json.loads((d / "scene_manifest.json").read_text())
m["tree_ground_contact"] = {"passed": True, "root_embed_m": 0.02, "trees": records}
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
t = bpy.data.texts.get("scene_manifest.json")
if t:
    t.clear()
    t.write(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
print("ROOT_CONTACT_FIXED", key, len(records), flush=True)
