"""
Re-render only interior.png for all36 with a robust interior camera.

Picks a house window that genuinely faces the OUTSIDE by ray-casting outward
from each window: a window whose outward ray travels far without hitting house
geometry is an exterior window. Places the camera inside that room looking out
through it, so the street/lawn scenery is visible through the glass.
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]

from pathlib import Path
import math
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
BLEND = ROOT / "infinigen/outputs/urban_v3_all36/urban_v3_all36.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all36/interior.png"

print(f"[fix] opening {BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
except Exception as e:
    print("gpu", e, flush=True)

House = bpy.data.collections.get("House_indoor")
house_objs = [o for o in House.all_objects] if House else []


def cxyz(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector(
        (sum(c.x for c in cs) / 8, sum(c.y for c in cs) / 8, sum(c.z for c in cs) / 8)
    )


def in_coll(o, sub):
    return any(sub in c.name for c in o.users_collection)


wins = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
# house centre + bbox
mn = [1e18] * 3
mx = [-1e18] * 3
for o in house_objs:
    if o.type != "MESH":
        continue
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
hcx, hcy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2

dg = bpy.context.evaluated_depsgraph_get()


def outward(o):
    c = cxyz(o)
    d = Vector((c.x - hcx, c.y - hcy, 0.0))
    if d.length < 0.05:
        return Vector((1, 0, 0)), c
    d.normalize()
    return d, c


def clearance(o):
    d, c = outward(o)
    origin = c + d * 0.45
    origin.z = c.z
    hit, loc, nrm, idx, obj, m = bpy.context.scene.ray_cast(dg, origin, d)
    if not hit:
        return 999.0
    return (loc - origin).length


def has_clear_glass(o):
    return any(
        (sl.material and "a36_glass" in sl.material.name) for sl in o.material_slots
    )


# hide interior partition walls -> open-plan, guaranteeing a clear sightline
# from inside to the exterior windows
n_hidden = 0
for o in house_objs:
    if o.type == "MESH" and in_coll(o, "room_wall"):
        o.hide_render = True
        n_hidden += 1
print(
    f"[fix] hid {n_hidden} interior partition walls for the interior view", flush=True
)

# clear see-through windows that face open exterior
clear_wins = [o for o in wins if has_clear_glass(o) and clearance(o) > 4.0]
if not clear_wins:
    clear_wins = [o for o in wins if clearance(o) > 4.0] or wins
print(f"[fix] {len(clear_wins)} clear exterior windows of {len(wins)}", flush=True)

Cw = sum((cxyz(o) for o in clear_wins), Vector((0, 0, 0))) / len(clear_wins)
dsum = Vector((0, 0, 0))
for o in clear_wins:
    dd, _ = outward(o)
    dsum += Vector((dd.x, dd.y, 0.0))
d = dsum.normalized() if dsum.length > 0.1 else Vector((1, 0, 0))
print(
    f"[fix] window centroid ({Cw.x:.1f},{Cw.y:.1f},{Cw.z:.1f}) outward=({d.x:.2f},{d.y:.2f})",
    flush=True,
)

# camera set well back inside (opposite the windows), looking out toward them
cam_loc = Vector((Cw.x - d.x * 7.5, Cw.y - d.y * 7.5, 1.75))
cam_loc.x = min(max(cam_loc.x, mn[0] + 0.6), mx[0] - 0.6)
cam_loc.y = min(max(cam_loc.y, mn[1] + 0.6), mx[1] - 0.6)
cam_tgt = Vector((Cw.x + d.x * 14.0, Cw.y + d.y * 14.0, 1.1))

cam = bpy.data.objects.get("cam_interior")
if cam is None:
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.name = "cam_interior"
cam.location = cam_loc
cam.data.lens_unit = "FOV"
cam.data.angle = math.radians(72)
cam.data.clip_start = 0.02
cam.rotation_euler = (cam_tgt - cam_loc).to_track_quat("-Z", "Y").to_euler()

sc = bpy.context.scene
sc.camera = cam
sc.render.filepath = str(OUT)
print("[fix] rendering interior.png ...", flush=True)
bpy.ops.render.render(write_still=True)
print("[fix] done.", flush=True)
