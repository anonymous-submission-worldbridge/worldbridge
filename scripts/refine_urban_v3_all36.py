"""
Build urban_v3_all36 from the all34 urban scene + an enlarged, more-realistic
infinigen indoor-pipeline house, plus an interior render looking out a window.

Continuing from all35 (which placed the infinigen coarse house):
  1. Double the house footprint  -> uniform scale x sqrt(2) vs all35 (0.826 ->
     ~1.168), keeping the road-facing facade anchored at the same front line.
  2. Add exterior realism:
       - exterior walls (room_exterior — had NO material) -> warm stucco PBR
       - roof (room_ceiling) -> dark standing-seam metal PBR
       - window / door glass slots -> clear transmissive glass (see-through)
       - window / door frames -> dark anodised metal
  3. Add an interior camera placed inside, just behind a road-facing window,
     looking OUT so the street scene is visible through the glass, plus a few
     soft interior area lights. Rendered as interior.png (6th image).

Base = all34 (urban scene without the house); the house is re-imported bigger.
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
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all34/urban_v3_all34.blend"
FRESH_HOUSE = ROOT / "infinigen/outputs/urban_v3_all35_house/coarse/scene.blend"
FALLBACK_HOUSE = ROOT / "infinigen/outputs/indoor2/coarse/scene.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all36"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))

TARGET_FRONT_X = -10.5  # east (road-facing) wall front line
TARGET_CY = 31.0
NEW_SCALE = 0.826 * math.sqrt(2.0)  # ~1.168 -> doubles the all35 footprint area
WANT = lambda c: (
    c == "unique_assets" or c == "skirting" or c.startswith("door_base_elements")
)

# ─────────────────────────────────────────────────────────────────────────────
print(f"[all36] Opening base blend: {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print(f"[all36] Opened. objects={len(bpy.data.objects)}", flush=True)

bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all36] GPU: OPTIX", flush=True)
except Exception as _e:
    print(f"[all36] OPTIX: {_e}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# MATERIALS (realistic exterior)
# ═════════════════════════════════════════════════════════════════════════════
def _clear(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    for n in list(m.node_tree.nodes):
        m.node_tree.nodes.remove(n)
    return m


def _set(b, k, v):
    if k in b.inputs:
        b.inputs[k].default_value = v


def facade_mat():
    m = _clear("a36_facade_stucco")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    big = nd.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 1.2
    big.inputs["Detail"].default_value = 3.0
    lk.new(tex.outputs["Object"], big.inputs["Vector"])
    ramp = nd.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.46, 0.40, 0.32, 1.0)  # warm taupe
    ramp.color_ramp.elements[1].color = (0.60, 0.54, 0.44, 1.0)  # beige stucco
    lk.new(big.outputs["Fac"], ramp.inputs["Fac"])
    lk.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.85)
    fine = nd.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 45.0
    fine.inputs["Detail"].default_value = 12.0
    lk.new(tex.outputs["Object"], fine.inputs["Vector"])
    bump = nd.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.004
    lk.new(fine.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def roof_mat():
    m = _clear("a36_roof_metal")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    # standing-seam stripes via wave texture
    wav = nd.new("ShaderNodeTexWave")
    wav.inputs["Scale"].default_value = 3.0
    wav.inputs["Distortion"].default_value = 0.0
    lk.new(tex.outputs["Object"], wav.inputs["Vector"])
    ramp = nd.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.055, 0.058, 0.065, 1.0)
    ramp.color_ramp.elements[1].color = (0.12, 0.12, 0.13, 1.0)
    lk.new(wav.outputs["Fac"], ramp.inputs["Fac"])
    lk.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.42)
    _set(bsdf, "Metallic", 0.75)
    bump = nd.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    lk.new(wav.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def glass_mat():
    m = _clear("a36_glass_clear")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.92, 0.96, 0.97, 1.0)
    _set(bsdf, "Roughness", 0.02)
    _set(bsdf, "Transmission Weight", 1.0)
    _set(bsdf, "IOR", 1.45)
    for k in ("Metallic",):
        _set(bsdf, k, 0.0)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def frame_mat():
    m = _clear("a36_frame_metal")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1.0)
    _set(bsdf, "Roughness", 0.35)
    _set(bsdf, "Metallic", 0.9)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_FACADE = facade_mat()
MAT_ROOF = roof_mat()
MAT_GLASS = glass_mat()
MAT_FRAME = frame_mat()


# ═════════════════════════════════════════════════════════════════════════════
# IMPORT + PLACE THE HOUSE (bigger)
# ═════════════════════════════════════════════════════════════════════════════
def import_house(src):
    with bpy.data.libraries.load(str(src), link=False) as (s, d):
        d.collections = [c for c in s.collections if WANT(c)]
    colls = [c for c in d.collections if c is not None]
    objs = set()
    for c in colls:
        for o in c.all_objects:
            objs.add(o)
    return objs


house_src = FRESH_HOUSE if FRESH_HOUSE.exists() else FALLBACK_HOUSE
print(f"[all36] Importing house from: {house_src}", flush=True)
house_objs = import_house(house_src)
if (
    len([o for o in house_objs if o.type == "MESH"]) < 20
    and house_src != FALLBACK_HOUSE
):
    house_objs = import_house(FALLBACK_HOUSE)
print(f"[all36]   imported {len(house_objs)} house objects", flush=True)

House = bpy.data.collections.new("House_indoor")
bpy.context.scene.collection.children.link(House)
for o in house_objs:
    try:
        House.objects.link(o)
    except RuntimeError:
        pass


# ── realistic material assignment (BEFORE transform; membership intact) ───────
def in_coll(o, sub):
    return any(sub in c.name for c in o.users_collection)


n_ext = n_roof = n_glass = 0
for o in house_objs:
    if o.type != "MESH":
        continue
    if in_coll(o, "room_exterior"):
        if o.data.materials:
            for i in range(len(o.data.materials)):
                o.data.materials[i] = MAT_FACADE
        else:
            o.data.materials.append(MAT_FACADE)
        n_ext += 1
    elif in_coll(o, "windows") or in_coll(o, "doors") or in_coll(o, "door_base"):
        for i, sl in enumerate(o.material_slots):
            nm = (sl.material.name if sl.material else "").lower()
            if "glass" in nm:
                o.data.materials[i] = MAT_GLASS
                n_glass += 1
            elif any(k in nm for k in ("metal", "plastic", "galv", "brush")):
                o.data.materials[i] = MAT_FRAME
print(
    f"[all36]   materials: exterior={n_ext} roof={n_roof} glass_slots={n_glass}",
    flush=True,
)


# ── group + transform ─────────────────────────────────────────────────────────
def hbbox(objs):
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    return mn, mx


def cxyz(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector(
        (sum(c.x for c in cs) / 8, sum(c.y for c in cs) / 8, sum(c.z for c in cs) / 8)
    )


empty = bpy.data.objects.new("House_root", None)
bpy.context.scene.collection.objects.link(empty)
for o in house_objs:
    if o.parent is None or o.parent not in house_objs:
        o.parent = empty
        o.matrix_parent_inverse = empty.matrix_world.inverted()
bpy.context.view_layer.update()

# rotate so the WINDOW-rich facade faces the road (+X). Average window offset
# from the house centre gives the facade normal direction.
mnA, mxA = hbbox(house_objs)
hcx = (mnA[0] + mxA[0]) / 2.0
hcy = (mnA[1] + mxA[1]) / 2.0
wins0 = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
fv = Vector((0.0, 0.0))
for w in wins0:
    c = cxyz(w)
    fv += Vector((c.x - hcx, c.y - hcy))
if wins0 and fv.length > 0.3:
    # spin the window-facade normal toward +X, SNAPPED to 90 deg so the house
    # stays axis-aligned to the street grid
    raw = -math.atan2(fv.y, fv.x)
    rot_z = round(raw / (math.pi / 2)) * (math.pi / 2)
else:
    rot_z = 0.0 if (mxA[0] - mnA[0]) >= (mxA[1] - mnA[1]) else math.pi / 2
print(
    f"[all36]   window-facade rot_z={rot_z:.2f} (fv={fv.x:.1f},{fv.y:.1f})", flush=True
)
empty.rotation_euler.z = rot_z
empty.scale = (NEW_SCALE, NEW_SCALE, NEW_SCALE)
bpy.context.view_layer.update()

mn2, mx2 = hbbox(house_objs)
anchor = (mx2[0], (mn2[1] + mx2[1]) / 2.0, mn2[2])
empty.location.x += TARGET_FRONT_X - anchor[0]
empty.location.y += TARGET_CY - anchor[1]
empty.location.z += 0.0 - anchor[2]
bpy.context.view_layer.update()
mn3, mx3 = hbbox(house_objs)
print(
    f"[all36]   placed house X[{mn3[0]:.1f},{mx3[0]:.1f}] Y[{mn3[1]:.1f},{mx3[1]:.1f}] Z[{mn3[2]:.1f},{mx3[2]:.1f}] "
    f"footprint {mx3[0]-mn3[0]:.1f}x{mx3[1]-mn3[1]:.1f}",
    flush=True,
)

# ── add a realistic dark flat roof slab over the plain shell top ───────────────
ext_objs = [o for o in house_objs if o.type == "MESH" and in_coll(o, "room_exterior")]
emn, emx = hbbox(ext_objs) if ext_objs else (mn3, mx3)
OV = 0.5
bpy.ops.mesh.primitive_cube_add(
    size=1, location=((emn[0] + emx[0]) / 2, (emn[1] + emx[1]) / 2, emx[2] + 0.16)
)
slab = bpy.context.active_object
slab.name = "house_roof_slab"
slab.scale = ((emx[0] - emn[0]) + 2 * OV, (emx[1] - emn[1]) + 2 * OV, 0.30)
bpy.ops.object.transform_apply(scale=True)
slab.data.materials.append(MAT_ROOF)
House.objects.link(slab)
print(f"[all36]   added dark roof slab at z={emx[2]:.2f}", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# INTERIOR CAMERA + LIGHTS (looking out a road-facing window)
# ═════════════════════════════════════════════════════════════════════════════
# road-facing window = window mesh with the largest world-X centre (the facade
# now faces +X toward the road), and place the camera INSIDE looking OUT.
wins = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
int_cam = None
if wins:
    hcx = (mn3[0] + mx3[0]) / 2.0
    hcy = (mn3[1] + mx3[1]) / 2.0

    def edge_dist(o):
        c = cxyz(o)
        return min(c.x - mn3[0], mx3[0] - c.x, c.y - mn3[1], mx3[1] - c.y)

    def warea(o):
        d = o.dimensions
        s = sorted([d.x, d.y, d.z])
        return s[1] * s[2]

    ext_w = [o for o in wins if edge_dist(o) < 1.8]  # exterior windows
    front_w = [o for o in ext_w if cxyz(o).x > mx3[0] - 2.8]  # road (+X) wall
    pool = front_w or ext_w or wins
    best = max(pool, key=warea)  # biggest pane
    wc = cxyz(best)
    inw = Vector((hcx - wc.x, hcy - wc.y))
    if inw.length < 0.1:
        inw = Vector((1.0, 0.0))
    inw.normalize()
    print(
        f"[all36]   interior view window at ({wc.x:.1f},{wc.y:.1f},{wc.z:.1f}) "
        f"area~{warea(best):.1f} front={len(front_w)} ext={len(ext_w)}",
        flush=True,
    )
    cam_loc = (wc.x + inw.x * 2.8, wc.y + inw.y * 2.8, wc.z + 0.2)  # inside room
    cam_tgt = (wc.x - inw.x * 4.0, wc.y - inw.y * 4.0, wc.z - 0.25)  # out the window
    bpy.ops.object.camera_add(location=cam_loc)
    int_cam = bpy.context.active_object
    int_cam.name = "cam_interior"
    int_cam.data.name = "cam_interior"
    int_cam.data.lens_unit = "FOV"
    int_cam.data.angle = math.radians(70)
    int_cam.data.clip_start = 0.05
    dvec = Vector(cam_tgt) - Vector(cam_loc)
    int_cam.rotation_euler = dvec.to_track_quat("-Z", "Y").to_euler()
    # bright soft interior fill lights near the ceiling, spread across footprint
    roof_z = mx3[2]
    for i, (fx, fy) in enumerate(
        [(0.30, 0.30), (0.30, 0.70), (0.70, 0.30), (0.70, 0.70), (0.5, 0.5)]
    ):
        lx = mn3[0] + fx * (mx3[0] - mn3[0])
        ly = mn3[1] + fy * (mx3[1] - mn3[1])
        light = bpy.data.lights.new(f"int_fill_{i}", "AREA")
        light.energy = 900.0
        light.size = 3.0
        lo = bpy.data.objects.new(f"int_fill_{i}", light)
        lo.location = (lx, ly, roof_z - 0.25)
        bpy.context.scene.collection.objects.link(lo)
    print("[all36]   interior camera + 5 fill lights added", flush=True)
else:
    print("[all36]   WARN: no window meshes found for interior camera", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# SAVE + RENDER
# ═════════════════════════════════════════════════════════════════════════════
out_blend = OUT / "urban_v3_all36.blend"
print(f"[all36] Saving blend -> {out_blend}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all36] Blend saved.", flush=True)

sc = bpy.context.scene
RENDERS = []
if int_cam is not None:
    RENDERS.append(("cam_interior", "interior.png"))  # render risky view first
RENDERS += [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cam_name, fname in RENDERS:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all36] MISSING camera {cam_name}, skipping {fname}", flush=True)
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all36] Rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all36] Done: {fname}", flush=True)

print("[all36] ALL DONE.", flush=True)
