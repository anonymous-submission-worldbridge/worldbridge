"""
Build urban_v3_all33 by refining the existing urban_v3_all32 blend in place.

Three targeted edits requested (continuing from all32):

  1. Road markings were invisible because every marking box sat at centre
     z=0.025 (top 0.027) while the asphalt slab top is at z=0.040 — i.e. the
     white dashes / yellow centre line / zebra crossings were BURIED inside the
     road. Fix: delete the buried markings and rebuild them fresh ON TOP of the
     asphalt (centre z=0.045) with bright high-albedo paint. Short white dashed
     lane lines + double yellow centre line + zebra crossings + stop bars. NO
     arrows.
  2. Remove the roadside benches (the clbench:* objects in the Furniture
     collection). Park benches (in the Park collection) are kept.
  3. Two bus stops instead of one, flanking the crossroads on opposite sides a
     little way from the junction, and enlarged to ~2x the previous size (the
     old single shelter was scale 1.5; the new ones use a true uniform scale of
     3.0 about their ground pivot).

Everything else (deep asphalt, park + marble sculpture, vehicles, cameras,
world/sky, render settings) is inherited unchanged from the all32 blend.
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
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all32/urban_v3_all32.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all33"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
import urban_assets as UA  # noqa: E402

# ── scene geometry constants (same lineage as all29) ──
R = 4.5
SW = 3.5
FW = 2.5
S1 = R + SW  # 8.0
ARM = 50.0
LC = R / 2  # 2.25
FULL = R + ARM  # 54.5
Z_MARK = 0.045  # marking centre z — ON TOP of the 0.04 asphalt slab
DZ_MARK = 0.008

# ─────────────────────────────────────────────────────────────────────────────
# OPEN THE all32 BLEND
# ─────────────────────────────────────────────────────────────────────────────
print(f"[all33] Opening base blend: {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print(f"[all33] Opened. objects={len(bpy.data.objects)}", flush=True)

# ─── GPU ──────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all33] GPU: OPTIX", flush=True)
except Exception as _e:
    print(f"[all33] OPTIX: {_e}", flush=True)
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print("[all33] GPU: CUDA", flush=True)
    except Exception as _e2:
        print(f"[all33] CUDA: {_e2}", flush=True)
print(f"[all33] cycles.device = {bpy.context.scene.cycles.device}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 1 — REBUILD ROAD MARKINGS ON TOP OF THE ASPHALT
# ═════════════════════════════════════════════════════════════════════════════
print("[all33] TASK 1: rebuilding road markings above the asphalt ...", flush=True)

# delete the old buried markings
old_mk = [
    o
    for o in bpy.data.objects
    if o.name.startswith(("dash_", "cl_", "xwk_", "stop_", "arr_"))
]
for o in old_mk:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[all33]   removed {len(old_mk)} buried/old marking objects", flush=True)


# bright paint materials (high albedo so they read white/yellow through AgX)
def _set(b, k, v):
    if k in b.inputs:
        b.inputs[k].default_value = v


def paint(name, rgb, rough=0.55):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    _set(bsdf, "Roughness", rough)
    # faint self-emission guarantees the lines stay crisp under AgX at distance
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*rgb, 1.0)
        _set(bsdf, "Emission Strength", 0.12)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


MK_W = paint("a33_mk_white", (0.92, 0.92, 0.90))
MK_Y = paint("a33_mk_yellow", (0.90, 0.66, 0.06))
MK_X = paint("a33_mk_xwalk", (0.93, 0.93, 0.91))

C_mk = bpy.data.collections.get("RoadMarkings")
if C_mk is None:
    C_mk = bpy.data.collections.new("RoadMarkings")
    bpy.context.scene.collection.children.link(C_mk)


def mbox(name, cx, cy, dx, dy, mat, rz=0.0):
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(cx, cy, Z_MARK), scale=(dx, dy, DZ_MARK)
    )
    o = bpy.context.active_object
    o.name = name
    if rz:
        o.rotation_euler[2] = rz
    o.data.materials.append(mat)
    UA.to_coll(o, C_mk)
    return o


# double-yellow centre line (both roads, full length)
for dx in (-0.10, 0.10):
    mbox(f"cl_ns{dx:+.2f}", dx, 0.0, 0.10, 2 * FULL, MK_Y)
for dy in (-0.10, 0.10):
    mbox(f"cl_ew{dy:+.2f}", 0.0, dy, 2 * FULL, 0.10, MK_Y)

# white dashed lane lines (short dashes) at +/-LC on both roads
DL, DG = 1.8, 1.8
for sgn in (+1, -1):
    for lx in (LC, -LC):
        y, k = sgn * (R + 1.0), 0
        while abs(y) < FULL - 1.0:
            mbox(
                f"dash_ns_{sgn:+d}_{lx:+.1f}_{k}", lx, y + sgn * DL / 2, 0.12, DL, MK_W
            )
            y += sgn * (DL + DG)
            k += 1
for sgn in (+1, -1):
    for ly in (LC, -LC):
        x, k = sgn * (R + 1.0), 0
        while abs(x) < FULL - 1.0:
            mbox(
                f"dash_ew_{sgn:+d}_{ly:+.1f}_{k}", x + sgn * DL / 2, ly, DL, 0.12, MK_W
            )
            x += sgn * (DL + DG)
            k += 1

# stop bars just before each crossing
for y in ((R + 0.32), -(R + 0.32)):
    mbox(f"stop_ns_{y:+.1f}", 0.0, y, 2 * R, 0.26, MK_W)
for x in ((R + 0.32), -(R + 0.32)):
    mbox(f"stop_ew_{x:+.1f}", x, 0.0, 0.26, 2 * R, MK_W)

# zebra crossings on all four arms
CW_W, CW_G = 0.50, 0.28
for arm_sign in (+1, -1):
    yb = arm_sign * (R + 0.55)
    for k in range(6):
        y = yb + arm_sign * k * (CW_W + CW_G)
        mbox(f"xwk_ns_{arm_sign:+d}_{k}", 0.0, y, 2 * R - 0.3, CW_W, MK_X)
for arm_sign in (+1, -1):
    xb = arm_sign * (R + 0.55)
    for k in range(6):
        x = xb + arm_sign * k * (CW_W + CW_G)
        mbox(f"xwk_ew_{arm_sign:+d}_{k}", x, 0.0, CW_W, 2 * R - 0.3, MK_X)

n_new = len(
    [
        o
        for o in bpy.data.objects
        if o.name.startswith(("dash_", "cl_", "xwk_", "stop_"))
    ]
)
print(f"[all33]   rebuilt {n_new} marking objects at z={Z_MARK}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 2 — REMOVE ROADSIDE BENCHES (keep park benches)
# ═════════════════════════════════════════════════════════════════════════════
print("[all33] TASK 2: removing roadside benches ...", flush=True)
benches = [o for o in bpy.data.objects if o.name.startswith("clbench")]
removed = 0
for o in benches:
    colls = [c.name for c in o.users_collection]
    if "Park" in colls:
        continue  # keep the park benches
    bpy.data.objects.remove(o, do_unlink=True)
    removed += 1
print(
    f"[all33]   removed {removed} roadside bench objects (kept park benches)",
    flush=True,
)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 3 — TWO ENLARGED BUS STOPS FLANKING THE CROSSROADS
# ═════════════════════════════════════════════════════════════════════════════
print("[all33] TASK 3: placing two enlarged bus stops ...", flush=True)

# remove the previous single shelter
old_bus = [o for o in bpy.data.objects if o.name.startswith("shelter:")]
for o in old_bus:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[all33]   removed {len(old_bus)} old bus-shelter objects", flush=True)

C_bus = bpy.data.collections.get("Furniture") or bpy.context.scene.collection


def place_bus_big(tag, at, yaw, s, C):
    """Import a bus shelter, place+yaw it, then uniformly scale it by s about
    its ground pivot (px,py,0). Uniform scale about a point = scale geometry AND
    scale the position offset from the pivot."""
    objs = UA.place_busstop(at, C, yaw=yaw, scale=1.0)
    if not objs:
        print(f"[all33]   [bus] WARNING: import failed for {tag}", flush=True)
        return []
    px, py = at[0], at[1]
    for o in objs:
        o.name = f"{tag}_{o.name}"
        o.location.x = px + s * (o.location.x - px)
        o.location.y = py + s * (o.location.y - py)
        o.location.z = s * o.location.z  # ground pivot z=0
        o.scale = (o.scale[0] * s, o.scale[1] * s, o.scale[2] * s)
    print(
        f"[all33]   placed bus stop {tag} at {at} yaw={yaw:.2f} scale={s}", flush=True
    )
    return objs


BUS_S = 3.0  # ~2x the old scale-1.5 shelter
# North arm, east sidewalk (opens toward road −X)
place_bus_big("busN", (6.5, 24.0), yaw=-math.pi / 2, s=BUS_S, C=C_bus)
# South arm, west sidewalk (opens toward road +X)
place_bus_big("busS", (-6.5, -24.0), yaw=math.pi / 2, s=BUS_S, C=C_bus)


# ═════════════════════════════════════════════════════════════════════════════
# SAVE + RENDER
# ═════════════════════════════════════════════════════════════════════════════
out_blend = OUT / "urban_v3_all33.blend"
print(f"[all33] Saving blend -> {out_blend}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all33] Blend saved.", flush=True)

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
        print(f"[all33] MISSING camera {cam_name}, skipping {fname}", flush=True)
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all33] Rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all33] Done: {fname}", flush=True)

print("[all33] ALL DONE.", flush=True)
