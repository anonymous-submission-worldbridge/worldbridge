"""
urban_v3_all37 — from the all34 urban scene + the infinigen house, upgraded:

  1. Replace the flat roof slab with a LOW HIP / PYRAMID roof carrying a
     terracotta clay-tile texture (like a real tiled hip roof).
  2. Add an explicit realistic FRONT DOOR + glazed WINDOWS on the road-facing
     facade (the infinigen facade read as blank from the street).
  3. Keep the infinigen interior furniture (unique_assets) so rooms are dressed.
  4. Two interior renders: interior_furniture.png (shows the furnished room) and
     interior_window.png (looking out a window to the street).

Base = all34 (urban scene, no house); the house is re-imported and improved.
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
import bmesh
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all34/urban_v3_all34.blend"
HOUSE_BLEND = ROOT / "infinigen/outputs/indoor2/coarse/scene.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all37"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))

TARGET_FRONT_X = -10.5
TARGET_CY = 31.0
NEW_SCALE = 0.826 * math.sqrt(2.0)  # doubled footprint (as in all36)
WANT = lambda c: (
    c == "unique_assets" or c == "skirting" or c.startswith("door_base_elements")
)

print(f"[all37] Opening {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all37] GPU OPTIX", flush=True)
except Exception as e:
    print("[all37] gpu", e, flush=True)


# ─── materials ────────────────────────────────────────────────────────────────
def _clear(n):
    m = bpy.data.materials.new(n)
    m.use_nodes = True
    for x in list(m.node_tree.nodes):
        m.node_tree.nodes.remove(x)
    return m


def _set(b, k, v):
    if k in b.inputs:
        b.inputs[k].default_value = v


def facade_mat():
    m = _clear("a37_facade")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    big = nd.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 1.4
    lk.new(tex.outputs["Object"], big.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.52, 0.47, 0.40, 1.0)
    r.color_ramp.elements[1].color = (0.66, 0.61, 0.52, 1.0)
    lk.new(big.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.85)
    fn = nd.new("ShaderNodeTexNoise")
    fn.inputs["Scale"].default_value = 42.0
    fn.inputs["Detail"].default_value = 12.0
    lk.new(tex.outputs["Object"], fn.inputs["Vector"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.2
    lk.new(fn.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def tile_roof_mat():
    m = _clear("a37_roof_tile")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    brick = nd.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.42, 0.14, 0.07, 1.0)  # terracotta
    brick.inputs["Color2"].default_value = (0.52, 0.20, 0.10, 1.0)
    brick.inputs["Mortar"].default_value = (0.20, 0.09, 0.05, 1.0)
    brick.inputs["Scale"].default_value = 9.0
    brick.inputs["Mortar Size"].default_value = 0.02
    if "Brick Width" in brick.inputs:
        brick.inputs["Brick Width"].default_value = 0.5
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 0.28
    lk.new(tex.outputs["Object"], brick.inputs["Vector"])
    lk.new(brick.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.62)
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.45
    bm.inputs["Distance"].default_value = 0.02
    lk.new(brick.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def glass_mat():
    m = _clear("a37_glass")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.90, 0.95, 0.97, 1.0)
    _set(b, "Roughness", 0.02)
    _set(b, "Transmission Weight", 1.0)
    _set(b, "IOR", 1.45)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def frame_mat():
    m = _clear("a37_frame")
    nt = m.node_tree
    nd = nt.nodes
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1.0)
    _set(b, "Roughness", 0.35)
    _set(b, "Metallic", 0.9)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def wood_mat():
    m = _clear("a37_door_wood")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    w = nd.new("ShaderNodeTexWave")
    w.inputs["Scale"].default_value = 3.0
    w.inputs["Distortion"].default_value = 6.0
    lk.new(tex.outputs["Object"], w.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.22, 0.11, 0.05, 1.0)
    r.color_ramp.elements[1].color = (0.36, 0.19, 0.09, 1.0)
    lk.new(w.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.45)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_FACADE = facade_mat()
MAT_TILE = tile_roof_mat()
MAT_GLASS = glass_mat()
MAT_FRAME = frame_mat()
MAT_WOOD = wood_mat()


def box(name, cx, cy, cz, dx, dy, dz, mat, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (dx, dy, dz)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(mat)
    coll.objects.link(o)
    for c in list(o.users_collection):
        if c is not coll:
            c.objects.unlink(o)
    return o


# ─── import house ─────────────────────────────────────────────────────────────
with bpy.data.libraries.load(str(HOUSE_BLEND), link=False) as (s, d):
    d.collections = [c for c in s.collections if WANT(c)]
house_objs = set()
for c in [c for c in d.collections if c]:
    for o in c.all_objects:
        house_objs.add(o)
print(f"[all37] imported {len(house_objs)} house objects", flush=True)
House = bpy.data.collections.new("House_indoor")
bpy.context.scene.collection.children.link(House)
for o in house_objs:
    try:
        House.objects.link(o)
    except RuntimeError:
        pass


def in_coll(o, sub):
    return any(sub in c.name for c in o.users_collection)


# facade + glass materials on the imported shell
for o in house_objs:
    if o.type != "MESH":
        continue
    if in_coll(o, "room_exterior"):
        if o.data.materials:
            for i in range(len(o.data.materials)):
                o.data.materials[i] = MAT_FACADE
        else:
            o.data.materials.append(MAT_FACADE)
    elif in_coll(o, "windows") or in_coll(o, "doors") or in_coll(o, "door_base"):
        for i, sl in enumerate(o.material_slots):
            nm = (sl.material.name if sl.material else "").lower()
            if "glass" in nm:
                o.data.materials[i] = MAT_GLASS
            elif any(k in nm for k in ("metal", "plastic", "galv", "brush")):
                o.data.materials[i] = MAT_FRAME


# ─── group + orient + scale + anchor ──────────────────────────────────────────
def cxyz(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector(
        (sum(c.x for c in cs) / 8, sum(c.y for c in cs) / 8, sum(c.z for c in cs) / 8)
    )


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


empty = bpy.data.objects.new("House_root", None)
bpy.context.scene.collection.objects.link(empty)
for o in house_objs:
    if o.parent is None or o.parent not in house_objs:
        o.parent = empty
        o.matrix_parent_inverse = empty.matrix_world.inverted()
bpy.context.view_layer.update()

mnA, mxA = hbbox(house_objs)
hcx, hcy = (mnA[0] + mxA[0]) / 2, (mnA[1] + mxA[1]) / 2
wins0 = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
fv = Vector((0.0, 0.0))
for w in wins0:
    c = cxyz(w)
    fv += Vector((c.x - hcx, c.y - hcy))
rot_z = (
    round((-math.atan2(fv.y, fv.x)) / (math.pi / 2)) * (math.pi / 2)
    if (wins0 and fv.length > 0.3)
    else (0.0 if (mxA[0] - mnA[0]) >= (mxA[1] - mnA[1]) else math.pi / 2)
)
empty.rotation_euler.z = rot_z
empty.scale = (NEW_SCALE, NEW_SCALE, NEW_SCALE)
bpy.context.view_layer.update()
mn2, mx2 = hbbox(house_objs)
empty.location.x += TARGET_FRONT_X - mx2[0]
empty.location.y += TARGET_CY - (mn2[1] + mx2[1]) / 2
empty.location.z += 0.0 - mn2[2]
bpy.context.view_layer.update()
mn3, mx3 = hbbox(house_objs)
print(
    f"[all37] house X[{mn3[0]:.1f},{mx3[0]:.1f}] Y[{mn3[1]:.1f},{mx3[1]:.1f}] Z[{mn3[2]:.1f},{mx3[2]:.1f}]",
    flush=True,
)

# room_exterior bbox = wall shell for roof + facade features
ext = [o for o in house_objs if o.type == "MESH" and in_coll(o, "room_exterior")]
emn, emx = hbbox(ext) if ext else (mn3, mx3)


# ─── LOW HIP / PYRAMID TILE ROOF over the shell ───────────────────────────────
def build_hip_roof(emn, emx, mat, coll, overhang=0.7, pitch_frac=0.16):
    x0, y0, x1, y1 = (
        emn[0] - overhang,
        emn[1] - overhang,
        emx[0] + overhang,
        emx[1] + overhang,
    )
    zt = emx[2] - 0.02
    W, D = x1 - x0, y1 - y0
    rise = pitch_frac * min(W, D)
    zr = zt + rise
    if W >= D:
        ins = D / 2.0
        yc = (y0 + y1) / 2.0
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (x0 + ins, yc, zr),
            (x1 - ins, yc, zr),
        ]
        faces = [(0, 1, 5, 4), (2, 3, 4, 5), (3, 0, 4), (1, 2, 5)]
    else:
        ins = W / 2.0
        xc = (x0 + x1) / 2.0
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (xc, y0 + ins, zr),
            (xc, y1 - ins, zr),
        ]
        faces = [(1, 2, 5, 4), (3, 0, 4, 5), (0, 1, 4), (2, 3, 5)]
    me = bpy.data.meshes.new("house_roof")
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("house_roof", me)
    o.data.materials.append(mat)
    coll.objects.link(o)
    return o, zr


roof, apex_z = build_hip_roof(emn, emx, MAT_TILE, House)
print(f"[all37] hip roof apex z={apex_z:.2f}", flush=True)


# ─── FRONT DOOR + WINDOWS on the road-facing (+X) facade ──────────────────────
fx = emx[0]  # facade plane (road side)
fcy = (emn[1] + emx[1]) / 2.0  # facade centre y
# door surround + leaf + upper glass + handle (protruding slightly toward road)
box("fd_frame", fx + 0.03, fcy, 1.28, 0.20, 1.55, 2.55, MAT_FRAME, House)
box("fd_leaf", fx + 0.12, fcy, 1.20, 0.08, 1.25, 2.35, MAT_WOOD, House)
box("fd_glass", fx + 0.15, fcy, 1.95, 0.03, 0.80, 0.70, MAT_GLASS, House)
box("fd_glass2", fx + 0.15, fcy, 0.95, 0.03, 0.80, 0.55, MAT_GLASS, House)
bpy.ops.mesh.primitive_cylinder_add(
    vertices=12, radius=0.05, depth=0.28, location=(fx + 0.20, fcy - 0.45, 1.15)
)
hd = bpy.context.active_object
hd.name = "fd_handle"
hd.rotation_euler.x = math.pi / 2
hd.data.materials.append(MAT_FRAME)
House.objects.link(hd)
for c in list(hd.users_collection):
    if c is not House:
        c.objects.unlink(hd)
# two windows flanking the door
for k, wy in enumerate((fcy - 3.4, fcy + 3.4)):
    box(f"fw{k}_frame", fx + 0.03, wy, 1.65, 0.16, 1.75, 1.55, MAT_FRAME, House)
    box(f"fw{k}_glass", fx + 0.09, wy, 1.65, 0.04, 1.55, 1.35, MAT_GLASS, House)
    box(f"fw{k}_mullv", fx + 0.11, wy, 1.65, 0.02, 0.06, 1.35, MAT_FRAME, House)
    box(f"fw{k}_mullh", fx + 0.11, wy, 1.65, 0.02, 1.55, 0.06, MAT_FRAME, House)
print("[all37] added front door + 2 windows", flush=True)


# ─── interior fill lights ─────────────────────────────────────────────────────
for i, (fxx, fyy) in enumerate(
    [(0.3, 0.3), (0.3, 0.7), (0.7, 0.3), (0.7, 0.7), (0.5, 0.5)]
):
    lx = mn3[0] + fxx * (mx3[0] - mn3[0])
    ly = mn3[1] + fyy * (mx3[1] - mn3[1])
    lt = bpy.data.lights.new(f"int_fill_{i}", "AREA")
    lt.energy = 800.0
    lt.size = 3.0
    lo = bpy.data.objects.new(f"int_fill_{i}", lt)
    lo.location = (lx, ly, mx3[2] - 0.25)
    bpy.context.scene.collection.objects.link(lo)


# ─── interior cameras ─────────────────────────────────────────────────────────
def make_cam(name, loc, tgt, fov):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = name
    c.data.name = name
    c.data.lens_unit = "FOV"
    c.data.angle = math.radians(fov)
    c.data.clip_start = 0.02
    c.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return c


# furniture cam: high corner looking diagonally across the (soon open-plan) room
cx0, cy0 = mn3[0] + 1.2, mn3[1] + 1.2
cam_furn = make_cam(
    "cam_int_furniture",
    (cx0, cy0, mx3[2] - 0.5),
    ((mn3[0] + mx3[0]) / 2 + 3, (mn3[1] + mx3[1]) / 2 + 3, 0.4),
    78,
)

# window cam: chosen at render time (needs walls hidden); pre-create a placeholder
wins = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
dg = bpy.context.evaluated_depsgraph_get()


def clearance(o):
    c = cxyz(o)
    dv = Vector((c.x - (mn3[0] + mx3[0]) / 2, c.y - (mn3[1] + mx3[1]) / 2, 0.0))
    if dv.length < 0.05:
        return 0.0
    dv.normalize()
    org = c + dv * 0.45
    org.z = c.z
    hit, loc, n, i, ob, mw = bpy.context.scene.ray_cast(dg, org, dv)
    return 999.0 if not hit else (loc - org).length


def has_clear(o):
    return any(
        sl.material and "a37_glass" in sl.material.name for sl in o.material_slots
    )


cw = (
    [o for o in wins if has_clear(o) and clearance(o) > 4.0]
    or [o for o in wins if clearance(o) > 4.0]
    or wins
)
Cw = sum((cxyz(o) for o in cw), Vector((0, 0, 0))) / len(cw)
ds = Vector((0, 0, 0))
for o in cw:
    c = cxyz(o)
    dv = Vector((c.x - (mn3[0] + mx3[0]) / 2, c.y - (mn3[1] + mx3[1]) / 2, 0.0))
    if dv.length > 0.05:
        ds += dv.normalized()
dv = ds.normalized() if ds.length > 0.1 else Vector((1, 0, 0))
wl = Vector((Cw.x - dv.x * 7.5, Cw.y - dv.y * 7.5, 1.75))
wl.x = min(max(wl.x, mn3[0] + 0.6), mx3[0] - 0.6)
wl.y = min(max(wl.y, mn3[1] + 0.6), mx3[1] - 0.6)
cam_win = make_cam(
    "cam_int_window", tuple(wl), (Cw.x + dv.x * 14, Cw.y + dv.y * 14, 1.1), 72
)
print(f"[all37] window cam looks toward ({Cw.x:.1f},{Cw.y:.1f})", flush=True)


# ─── SAVE + RENDER ────────────────────────────────────────────────────────────
out_blend = OUT / "urban_v3_all37.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all37] saved blend", flush=True)
sc = bpy.context.scene

EXT = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cn, fn in EXT:
    cam = bpy.data.objects.get(cn)
    if not cam:
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fn)
    print(f"[all37] render {fn}", flush=True)
    bpy.ops.render.render(write_still=True)

# hide interior partition walls -> open-plan for the two interior views
for o in house_objs:
    if o.type == "MESH" and in_coll(o, "room_wall"):
        o.hide_render = True
for cam, fn in [(cam_furn, "interior_furniture.png"), (cam_win, "interior_window.png")]:
    sc.camera = cam
    sc.render.filepath = str(OUT / fn)
    print(f"[all37] render {fn}", flush=True)
    bpy.ops.render.render(write_still=True)

print("[all37] ALL DONE.", flush=True)
