"""
Fix-ups for all37 (re-render only overview, residential, interior_furniture):
  - make the roof clay-TILE texture actually visible (coarser tiles, contrast,
    stronger bump)
  - aim the furniture interior camera AT the furniture cluster so the dressed
    room is shown
interior_window.png / park / commercial / intersection are already good and are
left untouched.
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
BLEND = ROOT / "infinigen/outputs/urban_v3_all37/urban_v3_all37.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all37"

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

# ── 1. visible clay tiles on the roof ─────────────────────────────────────────
m = bpy.data.materials.get("a37_roof_tile")
if m and m.use_nodes:
    for n in m.node_tree.nodes:
        if n.type == "TEX_BRICK":
            n.inputs["Scale"].default_value = 1.0  # Object coords are metres
            n.inputs["Color1"].default_value = (0.40, 0.13, 0.06, 1.0)
            n.inputs["Color2"].default_value = (0.56, 0.22, 0.11, 1.0)
            n.inputs["Mortar"].default_value = (0.14, 0.06, 0.03, 1.0)
            n.inputs["Mortar Size"].default_value = 0.035
            if "Brick Width" in n.inputs:
                n.inputs["Brick Width"].default_value = 0.55
            if "Row Height" in n.inputs:
                n.inputs["Row Height"].default_value = 0.32
        if n.type == "BUMP":
            n.inputs["Strength"].default_value = 0.7
    print("[fix37] roof tile texture coarsened", flush=True)

# ── 2. furniture camera aimed at the furniture cluster ────────────────────────
House = bpy.data.collections.get("House_indoor")
house_objs = [o for o in House.all_objects] if House else []


def in_coll(o, sub):
    return any(sub in c.name for c in o.users_collection)


# cutaway: hide ALL walls (interior partitions + exterior shell) so the
# furniture is never occluded; keep floor + ceiling for a room feel
for o in house_objs:
    if o.type == "MESH" and (
        in_coll(o, "room_wall")
        or in_coll(o, "room_exterior")
        or in_coll(o, "room_ceiling")
    ):
        o.hide_render = True

FURN = (
    "Shelf",
    "Cabinet",
    "Bookcase",
    "Table",
    "Chair",
    "Plant",
    "Lamp",
    "BookStack",
    "BookColumn",
    "Cell",
    "Plate",
    "Cup",
    "Bowl",
    "Pot",
    "Wineglass",
)


def cxyz(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector(
        (sum(c.x for c in cs) / 8, sum(c.y for c in cs) / 8, sum(c.z for c in cs) / 8)
    )


furn = [o for o in house_objs if o.type == "MESH" and any(k in o.name for k in FURN)]
# furniture bounding box (the big items dominate)
big = [o for o in furn if o.dimensions.length > 0.5] or furn
fmn = [1e18] * 3
fmx = [-1e18] * 3
for o in big:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            fmn[i] = min(fmn[i], w[i])
            fmx[i] = max(fmx[i], w[i])
fcx, fcy, fcz = (fmn[0] + fmx[0]) / 2, (fmn[1] + fmx[1]) / 2, (fmn[2] + fmx[2]) / 2
print(
    f"[fix37] {len(furn)} furniture ({len(big)} big) bbox X[{fmn[0]:.1f},{fmx[0]:.1f}] "
    f"Y[{fmn[1]:.1f},{fmx[1]:.1f}] Z[{fmn[2]:.1f},{fmx[2]:.1f}]",
    flush=True,
)

# camera just east of the furniture (past any occluding wall), looking west at it
cam = bpy.data.objects.get("cam_int_furniture")
if cam is None:
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.name = "cam_int_furniture"
cam_loc = Vector((fmx[0] + 4.5, fcy - 3.4, fmn[2] + 1.5))
cam_tgt = Vector((fcx - 0.3, fcy + 0.2, fmn[2] + 0.8))
cam.location = cam_loc
cam.data.lens_unit = "FOV"
cam.data.angle = math.radians(64)
cam.data.clip_start = 0.02
cam.rotation_euler = (cam_tgt - cam_loc).to_track_quat("-Z", "Y").to_euler()

# ── 3. re-render only the furniture interior view ─────────────────────────────
sc = bpy.context.scene
for cn, fn in [("cam_int_furniture", "interior_furniture.png")]:
    c = bpy.data.objects.get(cn)
    if not c:
        continue
    sc.camera = c
    sc.render.filepath = str(OUT / fn)
    print(f"[fix37] render {fn}", flush=True)
    bpy.ops.render.render(write_still=True)
print("[fix37] done", flush=True)
