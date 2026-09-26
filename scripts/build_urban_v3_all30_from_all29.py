"""
build_urban_v3_all30_from_all29.py
==================================
Produces urban_v3_all30 by EDITING the already-built urban_v3_all29.blend,
instead of rebuilding from scratch (a fresh rebuild crashes deterministically
inside TreeFactory's 9th park tree on the current NVIDIA driver 580.173.02 —
all27/28/29 built fine on 580.159). Editing the saved blend reuses the
successfully-generated park verbatim and applies only the 3 requested changes:

  1. Chrome trefoil sculpture re-centred on the marble disk.
  2. Road surface -> dark ASPHALT (rewrite the shared 'a8_concrete_road'
     material in place; existing lane lines + sidewalks are kept).
  3. Vehicles -> 18 diverse REAL imported openx models (delete the old
     procedural car meshes first).

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all30/
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

import bpy, sys, math
from pathlib import Path
from mathutils import Vector

SRC = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all29/urban_v3_all29.blend"
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all30")
OX_BASE = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")
OUT.mkdir(parents=True, exist_ok=True)

print(f"[a30] opening {SRC} ...")
bpy.ops.wm.open_mainfile(filepath=SRC)
print("[a30] blend loaded")

# ─── GPU ────────────────────────────────────────────────────────────────────
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type != "CPU"
    bpy.context.scene.cycles.device = "GPU"
    print("[a30] GPU = OPTIX")
except Exception as e:
    print(f"[a30] OPTIX note: {e}")
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != "CPU"
        bpy.context.scene.cycles.device = "GPU"
        print("[a30] GPU = CUDA")
    except Exception as e2:
        print(f"[a30] CUDA note: {e2}")


def _set(b, n, v):
    if n in b.inputs:
        b.inputs[n].default_value = v


# ═══ TASK 2: dark ASPHALT (rewrite shared road material in place) ════════════
m = bpy.data.materials.get("a8_concrete_road")
if m:
    m.use_nodes = True
    nt = m.node_tree
    nds, lks = nt.nodes, nt.links
    for n in list(nds):
        nds.remove(n)
    out = nds.new("ShaderNodeOutputMaterial")
    bsdf = nds.new("ShaderNodeBsdfPrincipled")
    tex = nds.new("ShaderNodeTexCoord")
    nz = nds.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nz.inputs["Detail"].default_value = 10.0
    lks.new(tex.outputs["Object"], nz.inputs["Vector"])
    ramp = nds.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.020, 0.020, 0.022, 1.0)  # near-black
    ramp.color_ramp.elements[1].color = (0.055, 0.055, 0.058, 1.0)  # worn patches
    lks.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    lks.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.80)
    fine = nds.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 45.0
    fine.inputs["Detail"].default_value = 10.0
    lks.new(tex.outputs["Object"], fine.inputs["Vector"])
    bump = nds.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    lks.new(fine.outputs["Fac"], bump.inputs["Height"])
    lks.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    lks.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    print("[a30] road material -> dark asphalt")
else:
    print("[a30] WARN: a8_concrete_road material not found")

# ═══ TASK 1: centre chrome trefoil sculpture on the marble ═══════════════════
plz = bpy.data.objects.get("plz_marble")
knot = [
    bpy.data.objects.get(n)
    for n in ("knot:plinth", "knot:ribbon", "knot:stem", "knot:step")
]
knot = [o for o in knot if o]
if plz and knot:
    bpy.context.view_layer.update()
    cx, cy = plz.location.x, plz.location.y
    ribbon = next((o for o in knot if o.name == "knot:ribbon"), knot[0])
    cs = [ribbon.matrix_world @ Vector(c) for c in ribbon.bound_box]
    rcx = (min(v.x for v in cs) + max(v.x for v in cs)) / 2
    rcy = (min(v.y for v in cs) + max(v.y for v in cs)) / 2
    dx, dy = cx - rcx, cy - rcy
    for o in knot:
        o.location.x += dx
        o.location.y += dy
    print(
        f"[a30] sculpture recentred on marble ({cx:.1f},{cy:.1f}), shift=({dx:.2f},{dy:.2f})"
    )
else:
    print(f"[a30] WARN: marble/knot not found (plz={bool(plz)}, knot={len(knot)})")

# ═══ TASK 3: replace procedural cars with 18 diverse real openx models ═══════
vc = bpy.data.collections.get("Vehicles")
if vc is None:
    vc = bpy.data.collections.new("Vehicles")
    bpy.context.scene.collection.children.link(vc)
old = list(vc.objects)
for o in old:
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[a30] removed {len(old)} old procedural vehicle objects")

_VEH_EXCL = frozenset(
    {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}
)


def place_car(tag, blend_path, at, yaw=0.0):
    bp = Path(blend_path)
    if not bp.exists():
        print(f"[car] MISSING: {bp}")
        return
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n not in _VEH_EXCL]
    root = None
    objs = []
    for o in dst.objects:
        if o is None:
            continue
        try:
            vc.objects.link(o)
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
        root.location.z = 0.0
        root.rotation_euler.z = yaw
    else:
        print(f"[car] WARNING: no Grp_Root in {bp.name}")


LC = 4.5 / 2
CARS = {
    "fiat": OX_BASE / "n1_fiat_ducato_2014/n1_fiat_ducato_2014.blend",
    "bmw": OX_BASE / "m1_bmw_x1_2016/m1_bmw_x1_2016.blend",
    "audi": OX_BASE / "m1_audi_q7_2015/m1_audi_q7_2015.blend",
    "volvo": OX_BASE / "m1_volvo_v60_polestar_2013/m1_volvo_v60_polestar_2013.blend",
    "mini": OX_BASE / "m1_mini_countryman_2016/m1_mini_countryman_2016.blend",
    "hyundai": OX_BASE / "m1_hyundai_tucson_2015/m1_hyundai_tucson_2015.blend",
    "dacia": OX_BASE / "m1_dacia_duster_2010/m1_dacia_duster_2010.blend",
    "gmc": OX_BASE / "n2_gmc_hummer_2021_pickup/n2_gmc_hummer_2021_pickup.blend",
    "tesla": OX_BASE / "n2_tesla_cybertruck_2024/n2_tesla_cybertruck_2024.blend",
    "merc": OX_BASE / "m1_mercedes_sl65amg_2008/m1_mercedes_sl65amg_2008.blend",
    "audi_tt": OX_BASE / "m1_audi_tt_2014_roadster/m1_audi_tt_2014_roadster.blend",
    "ex30": OX_BASE / "m1_volvo_ex30_2024/m1_volvo_ex30_2024.blend",
}
# N arm (x=+LC -> +pi/2, x=-LC -> -pi/2)
place_car("vn1", CARS["bmw"], (LC, 20.0), math.pi / 2)
place_car("vn2", CARS["volvo"], (LC, 34.0), math.pi / 2)
place_car("vn3", CARS["audi"], (-LC, 27.0), -math.pi / 2)
place_car("vn4", CARS["tesla"], (-LC, 42.0), -math.pi / 2)
place_car("vn5", CARS["merc"], (LC, 47.0), math.pi / 2)
# S arm (x=+LC -> -pi/2, x=-LC -> +pi/2)
place_car("vs1", CARS["mini"], (LC, -18.0), -math.pi / 2)
place_car("vs2", CARS["hyundai"], (-LC, -14.0), math.pi / 2)
place_car("vs3", CARS["tesla"], (LC, -34.0), -math.pi / 2)
place_car("vs4", CARS["audi_tt"], (-LC, -40.0), math.pi / 2)
# E arm (y=-LC -> 0, y=+LC -> pi)
place_car("ve1", CARS["fiat"], (22.0, -LC), 0)
place_car("ve2", CARS["dacia"], (38.0, -LC), 0)
place_car("ve3", CARS["gmc"], (20.0, LC), math.pi)
place_car("ve4", CARS["ex30"], (44.0, LC), math.pi)
place_car("ve5", CARS["hyundai"], (50.0, -LC), 0)
# W arm (y=+LC -> pi, y=-LC -> 0)
place_car("vw1", CARS["bmw"], (-26.0, LC), math.pi)
place_car("vw2", CARS["volvo"], (-40.0, -LC), 0)
place_car("vw3", CARS["dacia"], (-14.0, -LC), 0)
place_car("vw4", CARS["mini"], (-48.0, LC), math.pi)
print("[a30] 18 real vehicles placed")

# ═══ RENDER + SAVE ═══════════════════════════════════════════════════════════
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "GPU"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.cycles.samples = 256
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPTIX"
except Exception:
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass

blend_path = str(OUT / "urban_v3_all30.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[a30] blend saved: {blend_path}")

for camname, fn in [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]:
    cam = bpy.data.objects.get(camname)
    if cam is None:
        print(f"[a30] WARN: camera {camname} missing")
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fn)
    print(f"[a30] Rendering {fn} ...")
    bpy.ops.render.render(write_still=True)
    print(f"[a30] Done: {fn}")

print("[a30] ALL DONE.")
