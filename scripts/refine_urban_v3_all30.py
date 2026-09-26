"""
Build urban_v3_all30 by refining the existing urban_v3_all29 blend in place.

Three targeted edits requested (discarding the earlier broken all30 attempt):

  1. Move the park chrome-trefoil sculpture to the exact centre of the marble
     floor disk (marble centre = 34, 30).
  2. Give the roads the dark-asphalt look of urban_v3_all18 (near-black asphalt)
     while keeping the white dashed lane lines + yellow centre line + zebra
     crossings + sidewalks. The old directional turn-arrows are REMOVED because
     the requested lane markings are short dashes, not arrows.
  3. Replace the crude procedural "infinigen_car" vehicles with ~10 diverse
     imported OpenX car assets (BMW X1, Audi Q7, Volvo V60/EX30, Mini, Hyundai,
     Dacia, GMC Hummer, Tesla Cybertruck, Mercedes SL65).

Everything else (buildings-removed layout, fences-removed, park vegetation,
marble plaza, cameras, world/sky, render settings) is inherited unchanged from
the all29 blend.
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
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]


from pathlib import Path
import math
import sys

import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all29/urban_v3_all29.blend"
OX_BASE = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")
OUT = ROOT / "infinigen/outputs/urban_v3_all30"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))

# Scene geometry constants (same as all29)
R = 4.5  # half road width
LC = R / 2  # 2.25 lane centre offset
PLZ_CX, PLZ_CY = 34.0, 30.0  # marble plaza centre

# ─────────────────────────────────────────────────────────────────────────────
# OPEN THE all29 BLEND
# ─────────────────────────────────────────────────────────────────────────────
print(f"[all30] Opening base blend: {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print(f"[all30] Opened. objects={len(bpy.data.objects)}", flush=True)

# ─── GPU ──────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all30] GPU: OPTIX", flush=True)
except Exception as _e:
    print(f"[all30] OPTIX: {_e}", flush=True)
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print("[all30] GPU: CUDA", flush=True)
    except Exception as _e2:
        print(f"[all30] CUDA: {_e2}", flush=True)
print(f"[all30] cycles.device = {bpy.context.scene.cycles.device}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 1 — CENTRE THE CHROME-TREFOIL SCULPTURE ON THE MARBLE DISK
# ═════════════════════════════════════════════════════════════════════════════
print("[all30] TASK 1: centring park sculpture on marble ...", flush=True)
knot = [o for o in bpy.data.objects if o.name.startswith("knot:")]
if not knot:
    # fall back to a possible fallback torus
    knot = [o for o in bpy.data.objects if o.name.startswith("plz_knot")]
if knot:
    # combined world-space bounding box over the sculpture geometry
    mins = [1e18, 1e18]
    maxs = [-1e18, -1e18]
    for o in knot:
        if o.type != "MESH":
            continue
        mw = o.matrix_world
        for corner in o.bound_box:
            w = mw @ Vector(corner)
            mins[0] = min(mins[0], w.x)
            mins[1] = min(mins[1], w.y)
            maxs[0] = max(maxs[0], w.x)
            maxs[1] = max(maxs[1], w.y)
    cx = (mins[0] + maxs[0]) / 2.0
    cy = (mins[1] + maxs[1]) / 2.0
    dx = PLZ_CX - cx
    dy = PLZ_CY - cy
    print(
        f"[all30]   sculpture geom centre was ({cx:.3f},{cy:.3f}) -> shifting by ({dx:.3f},{dy:.3f})",
        flush=True,
    )
    kset = set(knot)
    moved = 0
    for o in knot:
        # only move roots; parented children follow their parent
        if o.parent is None or o.parent not in kset:
            o.location.x += dx
            o.location.y += dy
            moved += 1
    print(
        f"[all30]   moved {moved} sculpture root object(s); now centred at ({PLZ_CX},{PLZ_CY})",
        flush=True,
    )
else:
    print("[all30]   WARN: no knot:* sculpture objects found — skipping", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 2 — DARK ASPHALT ROADS  (+ remove directional turn-arrows)
# ═════════════════════════════════════════════════════════════════════════════
print("[all30] TASK 2: dark asphalt + marking cleanup ...", flush=True)

# (a) darken the shared road material 'a8_concrete_road'
road_mat = bpy.data.materials.get("a8_concrete_road")
if road_mat and road_mat.use_nodes:
    nt = road_mat.node_tree
    for n in nt.nodes:
        if n.type == "VALTORGB":
            e0 = n.color_ramp.elements[0]
            e1 = n.color_ramp.elements[1]
            # the light concrete base ramp has element0 ~ (0.46,0.45,0.43)
            if sum(e0.color[:3]) > 0.9:
                e0.color = (0.028, 0.028, 0.030, 1.0)  # dark asphalt (shaded)
                e1.color = (0.055, 0.054, 0.056, 1.0)  # dark asphalt (lit)
                print("[all30]   darkened road base color ramp -> asphalt", flush=True)
        if n.type == "BSDF_PRINCIPLED":
            try:
                n.inputs["Roughness"].default_value = 0.86
            except Exception:
                pass
    print("[all30]   road material 'a8_concrete_road' -> dark asphalt", flush=True)
else:
    print("[all30]   WARN: a8_concrete_road material not found", flush=True)

# (b) brighten white lane paint so dashes read crisply on dark asphalt
sw_mat = bpy.data.materials.get("a8_sw")
if sw_mat and sw_mat.use_nodes:
    for n in sw_mat.node_tree.nodes:
        if n.type == "VALTORGB":
            n.color_ramp.elements[0].color = (0.42, 0.41, 0.39, 1.0)
            n.color_ramp.elements[1].color = (0.93, 0.92, 0.89, 1.0)
    print("[all30]   brightened white lane paint 'a8_sw'", flush=True)

# (c) remove the directional turn-arrows (lane lines should be short dashes)
arrows = [o for o in bpy.data.objects if o.name.startswith("arr_")]
for o in arrows:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[all30]   removed {len(arrows)} turn-arrow objects (dashes kept)", flush=True)

# NB: white dashed lane lines (dash_*), yellow centre line (cl_*), stop bars
# (stop_*), zebra crossings (xwk_*) and the sidewalks + kerbs are inherited
# unchanged and now stand out against the dark asphalt.


# ═════════════════════════════════════════════════════════════════════════════
# TASK 3 — REPLACE CRUDE VEHICLES WITH IMPORTED OpenX CARS
# ═════════════════════════════════════════════════════════════════════════════
print("[all30] TASK 3: swapping vehicles for OpenX imports ...", flush=True)

# (a) delete the old procedural infinigen_car parts (vn* / vs* / ve* / vw*)
veh_coll = bpy.data.collections.get("Vehicles")
old = set()
if veh_coll:
    old.update(veh_coll.objects)
for o in bpy.data.objects:
    if o.name.split("_")[0][:2] in ("vn", "vs", "ve", "vw") and "vehicle" in o.name:
        old.add(o)
for o in list(old):
    try:
        bpy.data.objects.remove(o, do_unlink=True)
    except Exception:
        pass
print(f"[all30]   removed {len(old)} old procedural vehicle objects", flush=True)

if veh_coll is None:
    veh_coll = bpy.data.collections.new("Vehicles")
    bpy.context.scene.collection.children.link(veh_coll)

# (b) OpenX importer (all share a 'Grp_Root' empty)
_VEH_EXCL = frozenset(
    {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}
)


def place_car(tag, blend_path, at, C, yaw=0.0, z=0.02):
    bp = Path(blend_path)
    if not bp.exists():
        print(f"[all30]   [car] MISSING: {bp}", flush=True)
        return []
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n not in _VEH_EXCL]
    root = None
    objs = []
    for o in dst.objects:
        if o is None:
            continue
        try:
            C.objects.link(o)
        except RuntimeError:
            pass
        objs.append(o)
        if o.name == "Grp_Root" and o.parent is None:
            root = o
    for o in objs:
        o.name = f"{tag}_{o.name}"
    if root is None:
        for o in objs:
            if o.parent is None and o.type == "EMPTY":
                root = o
                break
    if root:
        root.location.x = at[0]
        root.location.y = at[1]
        root.location.z = z
        root.rotation_euler.z = yaw
        print(
            f"[all30]   placed {tag} ({bp.parent.name}) at {at} yaw={yaw:.2f}",
            flush=True,
        )
    else:
        print(f"[all30]   [car] WARNING: no Grp_Root in {bp.name}", flush=True)
    return objs


CARS = {
    "bmw": OX_BASE / "m1_bmw_x1_2016/m1_bmw_x1_2016.blend",
    "audi": OX_BASE / "m1_audi_q7_2015/m1_audi_q7_2015.blend",
    "volvo": OX_BASE / "m1_volvo_v60_polestar_2013/m1_volvo_v60_polestar_2013.blend",
    "volvo_ex": OX_BASE / "m1_volvo_ex30_2024/m1_volvo_ex30_2024.blend",
    "mini": OX_BASE / "m1_mini_countryman_2016/m1_mini_countryman_2016.blend",
    "hyundai": OX_BASE / "m1_hyundai_tucson_2015/m1_hyundai_tucson_2015.blend",
    "dacia": OX_BASE / "m1_dacia_duster_2010/m1_dacia_duster_2010.blend",
    "gmc": OX_BASE / "n2_gmc_hummer_2021_pickup/n2_gmc_hummer_2021_pickup.blend",
    "cyber": OX_BASE / "n2_tesla_cybertruck_2024/n2_tesla_cybertruck_2024.blend",
    "merc": OX_BASE / "m1_mercedes_sl65amg_2008/m1_mercedes_sl65amg_2008.blend",
}

# Right-hand traffic. OpenX cars face +X at yaw=0.
#   yaw=+pi/2 -> north (+Y), yaw=-pi/2 -> south (-Y), yaw=pi -> west (-X).
# NS road runs along Y at x=+/-LC; EW road runs along X at y=+/-LC.
PLAN = [
    # North arm (y>0)
    ("v1", "bmw", (LC, 16.0), math.pi / 2),  # northbound, right lane
    ("v2", "audi", (LC, 34.0), math.pi / 2),  # northbound
    ("v3", "volvo", (-LC, 24.0), -math.pi / 2),  # southbound, left lane
    ("v4", "mini", (-LC, 42.0), -math.pi / 2),  # southbound
    # South arm (y<0)
    ("v5", "hyundai", (LC, -18.0), math.pi / 2),  # northbound
    ("v6", "dacia", (-LC, -32.0), -math.pi / 2),  # southbound
    # East arm (x>0)
    ("v7", "merc", (18.0, -LC), 0.0),  # eastbound, right lane
    ("v8", "cyber", (38.0, LC), math.pi),  # westbound, left lane
    # West arm (x<0)
    ("v9", "gmc", (-20.0, -LC), 0.0),  # eastbound
    ("v10", "volvo_ex", (-40.0, LC), math.pi),  # westbound
]

placed = 0
for tag, key, at, yaw in PLAN:
    objs = place_car(tag, CARS[key], at, veh_coll, yaw=yaw)
    if objs:
        placed += 1
print(f"[all30]   placed {placed}/{len(PLAN)} OpenX cars", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# SAVE + RENDER
# ═════════════════════════════════════════════════════════════════════════════
out_blend = OUT / "urban_v3_all30.blend"
print(f"[all30] Saving blend -> {out_blend}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all30] Blend saved.", flush=True)

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
        print(f"[all30] MISSING camera {cam_name}, skipping {fname}", flush=True)
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all30] Rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all30] Done: {fname}", flush=True)

print("[all30] ALL DONE.", flush=True)
