"""
Build urban_v3_all34 by refining the existing urban_v3_all33 blend in place.

Three targeted edits requested (continuing from all33):

  1. The zebra crossings were oriented 90 deg wrong (stripes ran perpendicular
     to vehicle travel). Rebuild them so the stripes run PARALLEL to traffic
     (long axis along the road, arranged across the walking direction) — the
     correct zebra look.
  2. The (enlarged) bus stops clip the streetlights. Remove the streetlights
     whose footprint overlaps either bus-stop bounding box.
  3. Remove the shops / McDonald's kiosk. The shop buildings were already gone
     (removed back in all28); the remaining item is the McDonald's kiosk — all
     its "B:*" objects in the Commercial collection.

Everything else (deep asphalt, dashes + centre line, park, sculpture,
vehicles, the two bus stops, cameras, world/sky, render) is inherited unchanged.
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
import sys

import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all33/urban_v3_all33.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all34"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
import urban_assets as UA  # noqa: E402

R = 4.5
Z_MARK = 0.045
DZ_MARK = 0.008

# ─────────────────────────────────────────────────────────────────────────────
print(f"[all34] Opening base blend: {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print(f"[all34] Opened. objects={len(bpy.data.objects)}", flush=True)

bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all34] GPU: OPTIX", flush=True)
except Exception as _e:
    print(f"[all34] OPTIX: {_e}", flush=True)
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print("[all34] GPU: CUDA", flush=True)
    except Exception as _e2:
        print(f"[all34] CUDA: {_e2}", flush=True)
print(f"[all34] cycles.device = {bpy.context.scene.cycles.device}", flush=True)


def world_bbox(prefix):
    mnx = mny = 1e18
    mxx = mxy = -1e18
    for o in bpy.data.objects:
        if o.name.startswith(prefix):
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                mnx = min(mnx, w.x)
                mny = min(mny, w.y)
                mxx = max(mxx, w.x)
                mxy = max(mxy, w.y)
    if mnx > mxx:
        return None
    return [mnx, mny, mxx, mxy]


def world_center_xy(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (sum(c.x for c in cs) / 8.0, sum(c.y for c in cs) / 8.0)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 1 — REBUILD ZEBRA CROSSINGS WITH CORRECT ORIENTATION
# ═════════════════════════════════════════════════════════════════════════════
print("[all34] TASK 1: fixing zebra-crossing orientation ...", flush=True)
old_x = [o for o in bpy.data.objects if o.name.startswith("xwk_")]
for o in old_x:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[all34]   removed {len(old_x)} mis-oriented crossing bars", flush=True)

MK_X = bpy.data.materials.get("a33_mk_xwalk")
C_mk = bpy.data.collections.get("RoadMarkings")


def mbox(name, cx, cy, dx, dy, mat, z=Z_MARK + 0.002):
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(cx, cy, z), scale=(dx, dy, DZ_MARK)
    )
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    UA.to_coll(o, C_mk)
    return o


CW_W, CW_G = 0.50, 0.35  # stripe width, gap
LEN = 3.6  # crossing depth (stripe long-axis length)
half = R - 0.35  # stripes span the road width
pitch = CW_W + CW_G

# NS-road crossings (north/south arms): traffic runs along Y, so stripes are
# LONG IN Y and arranged across X.
for arm_sign in (+1, -1):
    yc = arm_sign * (R + 0.4 + LEN / 2)
    x = -half
    k = 0
    while x <= half + 1e-6:
        mbox(f"xwk_ns_{arm_sign:+d}_{k}", x, yc, CW_W, LEN, MK_X)
        x += pitch
        k += 1

# EW-road crossings (east/west arms): traffic runs along X, so stripes are
# LONG IN X and arranged across Y.
for arm_sign in (+1, -1):
    xc = arm_sign * (R + 0.4 + LEN / 2)
    y = -half
    k = 0
    while y <= half + 1e-6:
        mbox(f"xwk_ew_{arm_sign:+d}_{k}", xc, y, LEN, CW_W, MK_X)
        y += pitch
        k += 1

n_x = len([o for o in bpy.data.objects if o.name.startswith("xwk_")])
print(f"[all34]   rebuilt {n_x} correctly-oriented crossing bars", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 2 — REMOVE STREETLIGHTS THAT CLIP THE BUS STOPS
# ═════════════════════════════════════════════════════════════════════════════
print("[all34] TASK 2: removing streetlights clipping the bus stops ...", flush=True)
zones = []
for pfx in ("busN_", "busS_"):
    bb = world_bbox(pfx)
    if bb:
        # expand: generous in X (catch the lamp arm reaching over the road),
        # tight in Y so neighbouring lamps are not swept up
        zones.append([bb[0] - 1.5, bb[1] - 0.3, bb[2] + 1.5, bb[3] + 0.3])
        print(f"[all34]   {pfx} bbox {[round(v,2) for v in bb]}", flush=True)


def in_zones(x, y):
    for z in zones:
        if z[0] <= x <= z[2] and z[1] <= y <= z[3]:
            return True
    return False


sl = [o for o in bpy.data.objects if o.name.startswith("SL_")]
to_rm = []
for o in sl:
    cx, cy = world_center_xy(o)
    if in_zones(cx, cy):
        to_rm.append(o)
for o in to_rm:
    bpy.data.objects.remove(o, do_unlink=True)
print(
    f"[all34]   removed {len(to_rm)} streetlight objects overlapping bus stops "
    f"(of {len(sl)} total)",
    flush=True,
)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 3 — REMOVE THE McDONALD'S KIOSK (shops already gone since all28)
# ═════════════════════════════════════════════════════════════════════════════
print("[all34] TASK 3: removing McDonald's kiosk ...", flush=True)
kiosk = [o for o in bpy.data.objects if o.name.startswith("B:")]
for o in kiosk:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[all34]   removed {len(kiosk)} McDonald's-kiosk objects", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# SAVE + RENDER
# ═════════════════════════════════════════════════════════════════════════════
out_blend = OUT / "urban_v3_all34.blend"
print(f"[all34] Saving blend -> {out_blend}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all34] Blend saved.", flush=True)

sc = bpy.context.scene
RENDERS = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cam_name, fname in RENDERS:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all34] MISSING camera {cam_name}, skipping {fname}", flush=True)
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all34] Rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all34] Done: {fname}", flush=True)

print("[all34] ALL DONE.", flush=True)
