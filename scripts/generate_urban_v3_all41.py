"""
urban_v3_all41 - fresh procedural residential district expansion.

  1. Generate the base urban scene from code in this Blender process, then apply
     the all34 crossing/light/kiosk fixes in-scene.
  2. Import three freshly generated all41 indoor-pipeline house assets.
  3. Replace the residential quadrant ground with marble paving and physical
     dark seams.
  4. Rebuild house roofs with bases aligned to each house shell outline and
     grey-blue/qingwa material.
  5. Add a realistic wood door, wood window frames, glass panes, trim and
     hardware.
  6. Add two smaller all41 Infinigen houses plus one exterior-only apartment
     building in the residential quadrant for a stronger overview.
  7. Render exterior views plus two interior views from the large house, with
     the window view raised
     to a natural eye-level position.

This script does not open urban_v3_all40 or any previous urban blend.
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
import os
import runpy
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
CITY_SCRIPT = ROOT / "scripts/generate_urban_v3_all30.py"
HOUSE_BLENDS = {
    "large": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all41_house_large/scene.blend",
    "small_a": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all41_house_small_a/scene.blend",
    "small_b": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all41_house_small_b/scene.blend",
}
OUT = ROOT / "infinigen/outputs/urban_v3_all41"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import urban_assets as UA  # noqa: E402

TARGET_FRONT_X = -10.5
TARGET_CY = 31.0
NEW_SCALE = 0.826 * math.sqrt(2.0)  # large, complex house footprint
FULL_VARIANT = os.environ.get("C2W_URBAN_VARIANT", "baseline")
WANT = lambda c: (
    c == "unique_assets" or c == "skirting" or c.startswith("door_base_elements")
)

missing = [str(p) for p in HOUSE_BLENDS.values() if not p.exists()]
if missing:
    raise FileNotFoundError(
        "Fresh all41 house blend(s) missing:\n  "
        + "\n  ".join(missing)
        + "\nRun run_generate_indoors_all41.py for variants large, small_a, small_b first."
    )

print(f"[all41] Generating base urban scene from {CITY_SCRIPT}", flush=True)
os.environ["ALL41_SAFE_VEHICLES"] = "1"
runpy.run_path(str(CITY_SCRIPT), run_name="__main__")
print(
    f"[all41] Base urban scene generated in memory; objects={len(bpy.data.objects)}",
    flush=True,
)

bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all41] GPU OPTIX", flush=True)
except Exception as e:
    print("[all41] gpu", e, flush=True)


def apply_all34_base_fixes():
    print("[all41] Applying all34 base fixes in generated scene", flush=True)
    r = 4.5
    z_mark = 0.047
    dz_mark = 0.008
    old_x = [o for o in bpy.data.objects if o.name.startswith("xwk_")]
    for o in old_x:
        bpy.data.objects.remove(o, do_unlink=True)

    mat_x = bpy.data.materials.get("a8_xw") or bpy.data.materials.get("a33_mk_xwalk")
    coll_mk = bpy.data.collections.get("RoadMarkings")

    def mbox(name, cx, cy, dx, dy, mat, z=z_mark):
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(cx, cy, z), scale=(dx, dy, dz_mark)
        )
        o = bpy.context.active_object
        o.name = name
        if mat:
            o.data.materials.append(mat)
        if coll_mk:
            UA.to_coll(o, coll_mk)
        return o

    cw_w, cw_g = 0.50, 0.35
    length = 3.6
    half = r - 0.35
    pitch = cw_w + cw_g

    layout_mode = os.environ.get("C2W_URBAN_LAYOUT", "crossroads")

    def zebra_ns(tag, yc):
        x = -half
        k = 0
        while x <= half + 1e-6:
            mbox(f"xwk_ns_{tag}_{k}", x, yc, cw_w, length, mat_x)
            x += pitch
            k += 1

    def zebra_ew(tag, xc):
        y = -half
        k = 0
        while y <= half + 1e-6:
            mbox(f"xwk_ew_{tag}_{k}", xc, y, length, cw_w, mat_x)
            y += pitch
            k += 1

    crossing_offset = r + 0.4 + length / 2
    if layout_mode == "linear_street":
        # A single mid-block zebra; there is no intersection in this variant.
        zebra_ns("midblock", -9.5)
    elif layout_mode == "t_junction":
        zebra_ns("south", -crossing_offset)
        zebra_ew("east", crossing_offset)
        zebra_ew("west", -crossing_offset)
    else:
        zebra_ns("north", crossing_offset)
        zebra_ns("south", -crossing_offset)
        zebra_ew("east", crossing_offset)
        zebra_ew("west", -crossing_offset)

    def world_bbox(prefix):
        mnx = mny = 1e18
        mxx = mxy = -1e18
        for obj in bpy.data.objects:
            if not obj.name.startswith(prefix) or not hasattr(obj, "bound_box"):
                continue
            for c in obj.bound_box:
                w = obj.matrix_world @ Vector(c)
                mnx = min(mnx, w.x)
                mny = min(mny, w.y)
                mxx = max(mxx, w.x)
                mxy = max(mxy, w.y)
        if mnx > mxx:
            return None
        return [mnx, mny, mxx, mxy]

    def world_center_xy(obj):
        cs = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        return (sum(c.x for c in cs) / 8.0, sum(c.y for c in cs) / 8.0)

    zones = []
    for pfx in ("busN_", "busS_"):
        bb = world_bbox(pfx)
        if bb:
            zones.append([bb[0] - 1.5, bb[1] - 0.3, bb[2] + 1.5, bb[3] + 0.3])

    def in_zones(x, y):
        return any(z[0] <= x <= z[2] and z[1] <= y <= z[3] for z in zones)

    lights = [o for o in bpy.data.objects if o.name.startswith("SL_")]
    removed_lights = 0
    for o in list(lights):
        cx, cy = world_center_xy(o)
        if in_zones(cx, cy):
            bpy.data.objects.remove(o, do_unlink=True)
            removed_lights += 1

    kiosk = [o for o in bpy.data.objects if o.name.startswith("B:")]
    for o in kiosk:
        bpy.data.objects.remove(o, do_unlink=True)

    print(
        f"[all41] all34 fixes: {layout_mode} crossings rebuilt, removed {removed_lights} streetlights, "
        f"removed {len(kiosk)} kiosk objects",
        flush=True,
    )


apply_all34_base_fixes()


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
    m = _clear("a40_facade")
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
    m = _clear("a40_roof_qingwa_grayblue")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    brick = nd.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.18, 0.27, 0.32, 1.0)
    brick.inputs["Color2"].default_value = (0.30, 0.40, 0.46, 1.0)
    brick.inputs["Mortar"].default_value = (0.065, 0.09, 0.105, 1.0)
    brick.inputs["Scale"].default_value = 1.05
    brick.inputs["Mortar Size"].default_value = 0.034
    if "Brick Width" in brick.inputs:
        brick.inputs["Brick Width"].default_value = 0.52
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 0.30
    lk.new(tex.outputs["Object"], brick.inputs["Vector"])
    lk.new(brick.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.68)
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.62
    bm.inputs["Distance"].default_value = 0.024
    lk.new(brick.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def glass_mat():
    m = _clear("a40_clear_window_glass")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.84, 0.93, 0.98, 0.42)
    _set(b, "Alpha", 0.42)
    _set(b, "Roughness", 0.012)
    _set(b, "Transmission Weight", 0.82)
    _set(b, "IOR", 1.45)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    m.blend_method = "BLEND"
    m.use_screen_refraction = True
    return m


def frame_mat():
    m = _clear("a40_window_frame_wood")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    w = nd.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.inputs["Scale"].default_value = 8.0
    w.inputs["Distortion"].default_value = 9.0
    lk.new(tex.outputs["Object"], w.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.10, 0.055, 0.028, 1.0)
    r.color_ramp.elements[1].color = (0.30, 0.17, 0.075, 1.0)
    lk.new(w.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.11
    bm.inputs["Distance"].default_value = 0.006
    lk.new(w.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.46)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def wood_mat():
    m = _clear("a40_oiled_wood_door")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    w = nd.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.inputs["Scale"].default_value = 6.0
    w.inputs["Distortion"].default_value = 9.0
    lk.new(tex.outputs["Object"], w.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.18, 0.085, 0.035, 1.0)
    r.color_ramp.elements[1].color = (0.42, 0.22, 0.095, 1.0)
    lk.new(w.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.13
    bm.inputs["Distance"].default_value = 0.007
    lk.new(w.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.48)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_FACADE = facade_mat()
MAT_TILE = tile_roof_mat()
MAT_GLASS = glass_mat()
MAT_FRAME = frame_mat()
MAT_WOOD = wood_mat()


def principled_mat(name, color, roughness=0.6, metallic=0.0):
    m = _clear(name)
    nt = m.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = color
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def marble_mat():
    m = _clear("a40_marble_paving")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    noise = nd.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.58
    lk.new(tex.outputs["Object"], noise.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position = 0.16
    r.color_ramp.elements[0].color = (0.62, 0.64, 0.64, 1.0)
    vein = r.color_ramp.elements.new(0.47)
    vein.color = (0.36, 0.39, 0.40, 1.0)
    r.color_ramp.elements[1].color = (0.91, 0.92, 0.89, 1.0)
    lk.new(noise.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.055
    bm.inputs["Distance"].default_value = 0.012
    lk.new(noise.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.34)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_ROOF_FASCIA = principled_mat(
    "a40_roof_fascia_bluegray", (0.105, 0.155, 0.18, 1.0), roughness=0.72
)
MAT_DARK = principled_mat(
    "a40_dark_hardware", (0.035, 0.032, 0.028, 1.0), roughness=0.42, metallic=0.30
)
MAT_MARBLE = marble_mat()
MAT_SEAM = principled_mat(
    "a40_dark_marble_seam", (0.075, 0.080, 0.078, 1.0), roughness=0.78
)
MAT_STONE = principled_mat(
    "a40_fence_cut_stone", (0.48, 0.47, 0.43, 1.0), roughness=0.86
)
MAT_CONCRETE = principled_mat(
    "a40_fence_concrete_cap", (0.58, 0.57, 0.53, 1.0), roughness=0.82
)
MAT_IRON = principled_mat(
    "a40_black_wrought_iron", (0.018, 0.019, 0.021, 1.0), roughness=0.38, metallic=0.72
)


def bevel(obj, width=0.006, segments=1):
    if width <= 0:
        return obj
    mod = obj.modifiers.new("a40_bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("a40_weighted_normal", "WEIGHTED_NORMAL")
    return obj


def box(name, cx, cy, cz, dx, dy, dz, mat, coll, bevel_width=0.006):
    hx, hy, hz = dx / 2, dy / 2, dz / 2
    verts = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    if mat:
        o.data.materials.append(mat)
    bevel(o, bevel_width)
    coll.objects.link(o)
    return o


def cylinder(
    name, loc, radius, depth, mat, coll, vertices=24, rot=(0, 0, 0), bevel_width=0
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot
    )
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    bevel(o, bevel_width)
    coll.objects.link(o)
    for c in list(o.users_collection):
        if c is not coll:
            c.objects.unlink(o)
    return o


def pyramid(name, loc, base, height, mat, coll, rot=(0, 0, math.radians(45))):
    z0 = loc[2] - height / 2
    z1 = loc[2] + height / 2
    pts = [
        Vector((base, 0, z0)),
        Vector((0, base, z0)),
        Vector((-base, 0, z0)),
        Vector((0, -base, z0)),
    ]
    rz = rot[2]
    cr, sr = math.cos(rz), math.sin(rz)
    verts = []
    for p in pts:
        x = loc[0] + p.x * cr - p.y * sr
        y = loc[1] + p.x * sr + p.y * cr
        verts.append((x, y, p.z))
    verts.append((loc[0], loc[1], z1))
    faces = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    if mat:
        o.data.materials.append(mat)
    coll.objects.link(o)
    return o


def torus(name, loc, major, minor, mat, coll, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=24,
        minor_segments=8,
        location=loc,
        rotation=rot,
    )
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    coll.objects.link(o)
    for c in list(o.users_collection):
        if c is not coll:
            c.objects.unlink(o)
    return o


def pt(axis, t, fixed):
    return (t, fixed) if axis == "X" else (fixed, t)


def dims(axis, length, thick, height):
    return (length, thick, height) if axis == "X" else (thick, length, height)


def add_seamed_slab_grid(prefix, coll, x0, x1, y0, y1, z=0.082, tile=1.35):
    if x1 <= x0 or y1 <= y0:
        return
    box(
        f"{prefix}_slab",
        (x0 + x1) / 2,
        (y0 + y1) / 2,
        z,
        x1 - x0,
        y1 - y0,
        0.06,
        MAT_MARBLE,
        coll,
        bevel_width=0.004,
    )
    sx = math.ceil(x0 / tile) * tile
    i = 0
    while sx < x1:
        box(
            f"{prefix}_seam_x_{i}",
            sx,
            (y0 + y1) / 2,
            z + 0.034,
            0.026,
            y1 - y0,
            0.014,
            MAT_SEAM,
            coll,
            bevel_width=0,
        )
        sx += tile
        i += 1
    sy = math.ceil(y0 / tile) * tile
    j = 0
    while sy < y1:
        box(
            f"{prefix}_seam_y_{j}",
            (x0 + x1) / 2,
            sy,
            z + 0.035,
            x1 - x0,
            0.026,
            0.014,
            MAT_SEAM,
            coll,
            bevel_width=0,
        )
        sy += tile
        j += 1


def add_residential_quadrant_marble():
    coll = bpy.data.collections.new("Residential_marble_quadrant")
    bpy.context.scene.collection.children.link(coll)
    # North-west residential land: outside the road/sidewalk line and within the
    # original north-arm extent.
    add_seamed_slab_grid("a40_res_quad_marble", coll, -54.2, -10.5, 10.5, 54.5)
    print(
        "[all41] residential quadrant marble paving X[-54.2,-10.5] Y[10.5,54.5]",
        flush=True,
    )


add_residential_quadrant_marble()


# ─── import house ─────────────────────────────────────────────────────────────
with bpy.data.libraries.load(str(HOUSE_BLENDS["large"]), link=False) as (s, d):
    d.collections = [c for c in s.collections if WANT(c)]
house_objs = set()
for c in [c for c in d.collections if c]:
    for o in c.all_objects:
        house_objs.add(o)
print(f"[all41] imported {len(house_objs)} large house objects", flush=True)
House = bpy.data.collections.new("House_large_indoor")
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
    f"[all41] large house X[{mn3[0]:.1f},{mx3[0]:.1f}] Y[{mn3[1]:.1f},{mx3[1]:.1f}] Z[{mn3[2]:.1f},{mx3[2]:.1f}]",
    flush=True,
)

# room_exterior bbox = wall shell for roof + facade features
ext = [o for o in house_objs if o.type == "MESH" and in_coll(o, "room_exterior")]
emn, emx = hbbox(ext) if ext else (mn3, mx3)


# ─── LOW HIP / PYRAMID TILE ROOF over the shell ───────────────────────────────
def build_hip_roof(
    emn, emx, mat, fascia_mat, coll, overhang=0.0, pitch_frac=0.13, prefix="a41"
):
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
    me = bpy.data.meshes.new(f"{prefix}_house_roof")
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(f"{prefix}_house_roof", me)
    o.data.materials.append(mat)
    coll.objects.link(o)
    bevel(o, 0.01)
    edge_z = zt - 0.055
    box(
        f"{prefix}_roof_fascia_front",
        (x0 + x1) / 2,
        y0,
        edge_z,
        W,
        0.09,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        f"{prefix}_roof_fascia_back",
        (x0 + x1) / 2,
        y1,
        edge_z,
        W,
        0.09,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        f"{prefix}_roof_fascia_left",
        x0,
        (y0 + y1) / 2,
        edge_z,
        0.09,
        D,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        f"{prefix}_roof_fascia_right",
        x1,
        (y0 + y1) / 2,
        edge_z,
        0.09,
        D,
        0.11,
        fascia_mat,
        coll,
    )
    return o, zr


roof, apex_z = build_hip_roof(
    emn, emx, MAT_TILE, MAT_ROOF_FASCIA, House, overhang=0.0, prefix="a41_large"
)
print(f"[all41] outline-aligned qingwa roof apex z={apex_z:.2f}", flush=True)


# ─── FRONT DOOR + WINDOWS on the road-facing (+X) facade ──────────────────────
fx = emx[0]  # facade plane (road side)
fcy = (emn[1] + emx[1]) / 2.0  # facade centre y
# door surround + leaf + upper glass + hardware (protruding slightly toward road)
door_h = 2.45
door_w = 1.32
box(
    "fd_frame",
    fx + 0.025,
    fcy,
    door_h / 2,
    0.10,
    door_w + 0.34,
    door_h + 0.24,
    MAT_FRAME,
    House,
    bevel_width=0.012,
)
box(
    "fd_leaf",
    fx + 0.080,
    fcy,
    door_h / 2,
    0.075,
    door_w,
    door_h,
    MAT_WOOD,
    House,
    bevel_width=0.012,
)
for zc in (0.82, 1.43):
    box(
        f"fd_panel_{zc:.1f}",
        fx + 0.120,
        fcy,
        zc,
        0.030,
        door_w - 0.32,
        0.46,
        MAT_DARK,
        House,
        bevel_width=0.006,
    )
box(
    "fd_glass",
    fx + 0.128,
    fcy,
    1.96,
    0.028,
    door_w - 0.36,
    0.66,
    MAT_GLASS,
    House,
    bevel_width=0.004,
)
cylinder(
    "fd_handle",
    (fx + 0.165, fcy - door_w * 0.33, 1.13),
    0.045,
    0.23,
    MAT_DARK,
    House,
    vertices=16,
    rot=(math.radians(90), 0, 0),
)
box(
    "fd_threshold",
    fx + 0.080,
    fcy,
    0.06,
    0.28,
    door_w + 0.50,
    0.12,
    MAT_DARK,
    House,
    bevel_width=0.010,
)

front_windows = [
    (fcy - 4.15, 1.58, 1.65, 1.56),
    (fcy + 4.15, 1.58, 1.65, 1.56),
    (fcy - 4.15, 3.55, 1.35, 1.05),
    (fcy + 4.15, 3.55, 1.35, 1.05),
]
kept_front_windows = []
for k, (wy, wz, ww, wh) in enumerate(front_windows):
    if wy - ww / 2 < emn[1] + 0.45 or wy + ww / 2 > emx[1] - 0.45:
        continue
    kept_front_windows.append((wy, wz, ww, wh))
    box(
        f"fw{k}_outer_frame",
        fx + 0.018,
        wy,
        wz,
        0.105,
        ww + 0.28,
        wh + 0.28,
        MAT_FRAME,
        House,
        bevel_width=0.010,
    )
    box(
        f"fw{k}_glass",
        fx + 0.086,
        wy,
        wz,
        0.030,
        ww,
        wh,
        MAT_GLASS,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_mullv",
        fx + 0.114,
        wy,
        wz,
        0.036,
        0.070,
        wh,
        MAT_FRAME,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_mullh",
        fx + 0.114,
        wy,
        wz,
        0.036,
        ww,
        0.070,
        MAT_FRAME,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_sill",
        fx + 0.105,
        wy,
        wz - wh / 2 - 0.14,
        0.18,
        ww + 0.46,
        0.09,
        MAT_DARK,
        House,
        bevel_width=0.006,
    )
print(
    f"[all41] large house added front wood door + {len(kept_front_windows)} glass windows",
    flush=True,
)


# ─── MARBLE PAVING + WROUGHT-IRON FENCE ──────────────────────────────────────
def box_dims(name, loc, dim, mat, coll, bevel_width=0.006):
    return box(
        name,
        loc[0],
        loc[1],
        loc[2],
        dim[0],
        dim[1],
        dim[2],
        mat,
        coll,
        bevel_width=bevel_width,
    )


def add_marble_paving(coll, mat, seam_mat, emn, emx, hmn, hmx):
    house_depth = max(1.0, emx[0] - emn[0])
    house_width = max(1.0, hmx[1] - hmn[1])
    plot = {
        "front_x": -8.70,
        "back_x": max(-52.0, emn[0] - house_depth * 0.90),
        "y0": max(10.80, hmn[1] - house_width * 0.55),
        "y1": min(54.10, hmx[1] + house_width * 0.55),
    }
    z = 0.055
    slabs = [
        ("front", emx[0] + 0.04, plot["front_x"], plot["y0"], plot["y1"]),
        ("back", plot["back_x"], emn[0] - 0.04, plot["y0"], plot["y1"]),
        ("south", emn[0] - 0.04, emx[0] + 0.04, plot["y0"], emn[1] - 0.04),
        ("north", emn[0] - 0.04, emx[0] + 0.04, emx[1] + 0.04, plot["y1"]),
    ]
    for name, x0, x1, y0, y1 in slabs:
        if x1 <= x0 or y1 <= y0:
            continue
        box(
            f"a40_marble_paving_{name}",
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            z,
            x1 - x0,
            y1 - y0,
            0.055,
            mat,
            coll,
            bevel_width=0.004,
        )
        tile = 1.15
        sx = math.ceil(x0 / tile) * tile
        i = 0
        while sx < x1:
            box(
                f"a40_marble_seam_x_{name}_{i}",
                sx,
                (y0 + y1) / 2,
                z + 0.032,
                0.022,
                y1 - y0,
                0.012,
                seam_mat,
                coll,
                bevel_width=0,
            )
            sx += tile
            i += 1
        sy = math.ceil(y0 / tile) * tile
        j = 0
        while sy < y1:
            box(
                f"a40_marble_seam_y_{name}_{j}",
                (x0 + x1) / 2,
                sy,
                z + 0.033,
                x1 - x0,
                0.022,
                0.012,
                seam_mat,
                coll,
                bevel_width=0,
            )
            sy += tile
            j += 1
    return plot


def stone_pier(name, coll, x, y, h=1.72, w=0.34):
    box(f"{name}:col", x, y, h / 2, w, w, h, MAT_STONE, coll, bevel_width=0.012)
    box(
        f"{name}:cap",
        x,
        y,
        h + 0.035,
        w + 0.14,
        w + 0.14,
        0.07,
        MAT_CONCRETE,
        coll,
        bevel_width=0.012,
    )
    pyramid(f"{name}:pyr", (x, y, h + 0.135), (w + 0.10) / 2, 0.16, MAT_CONCRETE, coll)
    cylinder(
        f"{name}:finial", (x, y, h + 0.28), 0.045, 0.14, MAT_IRON, coll, vertices=16
    )


def posts_between(a, b, spacing=2.8):
    if b < a:
        a, b = b, a
    pts = [a]
    n = max(1, int((b - a) / spacing))
    for i in range(1, n):
        pts.append(a + (b - a) * i / n)
    pts.append(b)
    return pts


def iron_run(name, coll, axis, t0, t1, fixed, posts):
    if t1 <= t0:
        return
    length = t1 - t0
    tc = (t0 + t1) / 2
    plinth_h = 0.43
    box_dims(
        f"{name}:plinth",
        (*pt(axis, tc, fixed), plinth_h / 2),
        dims(axis, length, 0.20, plinth_h),
        MAT_STONE,
        coll,
    )
    box_dims(
        f"{name}:plinthcap",
        (*pt(axis, tc, fixed), plinth_h + 0.025),
        dims(axis, length, 0.24, 0.05),
        MAT_CONCRETE,
        coll,
    )
    rail_bot = plinth_h + 0.08
    rail_top = 1.45
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    for idx in range(len(posts) - 1):
        a = posts[idx] + 0.18
        b = posts[idx + 1] - 0.18
        if b <= a:
            continue
        bc = (a + b) / 2
        bl = b - a
        box_dims(
            f"{name}:rail_bot:{idx}",
            (*pt(axis, bc, fixed), rail_bot),
            dims(axis, bl, 0.052, 0.052),
            MAT_IRON,
            coll,
        )
        box_dims(
            f"{name}:rail_mid:{idx}",
            (*pt(axis, bc, fixed), rail_top - 0.30),
            dims(axis, bl, 0.036, 0.036),
            MAT_IRON,
            coll,
        )
        box_dims(
            f"{name}:rail_top:{idx}",
            (*pt(axis, bc, fixed), rail_top),
            dims(axis, bl, 0.055, 0.060),
            MAT_IRON,
            coll,
        )
        n_bar = max(4, int(bl / 0.16))
        step = bl / n_bar
        for j in range(n_bar + 1):
            t = a + j * step
            box(
                f"{name}:bar:{idx}:{j}",
                *pt(axis, t, fixed),
                (rail_bot + rail_top) / 2 + 0.04,
                0.024,
                0.024,
                rail_top - rail_bot + 0.32,
                MAT_IRON,
                coll,
                bevel_width=0.002,
            )
            pyramid(
                f"{name}:spear:{idx}:{j}",
                (*pt(axis, t, fixed), rail_top + 0.24),
                0.044,
                0.16,
                MAT_IRON,
                coll,
            )
        n_ring = max(1, int(bl / 0.62))
        for j in range(n_ring):
            t = a + (j + 0.5) * (bl / n_ring)
            torus(
                f"{name}:ring:{idx}:{j}",
                (*pt(axis, t, fixed), rail_bot + 0.46),
                0.078,
                0.014,
                MAT_IRON,
                coll,
                rot=ring_rot,
            )


def gate_leaf(name, coll, axis, t0, t1, fixed):
    w = t1 - t0
    tc = (t0 + t1) / 2
    z_bot, z_top = 0.16, 1.58
    stile = 0.052
    box_dims(
        f"{name}:stile_a",
        (*pt(axis, t0 + stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:stile_b",
        (*pt(axis, t1 - stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_bottom",
        (*pt(axis, tc, fixed), z_bot + 0.03),
        dims(axis, w, 0.055, 0.065),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_top",
        (*pt(axis, tc, fixed), z_top - 0.03),
        dims(axis, w, 0.055, 0.065),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_mid",
        (*pt(axis, tc, fixed), z_bot + (z_top - z_bot) * 0.42),
        dims(axis, w, 0.040, 0.044),
        MAT_IRON,
        coll,
    )
    n = max(4, int(w / 0.16))
    for j in range(1, n):
        t = t0 + j * (w / n)
        box(
            f"{name}:bar:{j}",
            *pt(axis, t, fixed),
            (z_bot + z_top) / 2 + 0.03,
            0.022,
            0.022,
            z_top - z_bot + 0.24,
            MAT_IRON,
            coll,
            bevel_width=0.002,
        )
        pyramid(
            f"{name}:spear:{j}",
            (*pt(axis, t, fixed), z_top + 0.21),
            0.040,
            0.15,
            MAT_IRON,
            coll,
        )
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    n_ring = max(2, int(w / 0.56))
    for j in range(n_ring):
        t = t0 + (j + 0.5) * (w / n_ring)
        torus(
            f"{name}:ring:{j}",
            (*pt(axis, t, fixed), z_bot + 0.44),
            0.078,
            0.014,
            MAT_IRON,
            coll,
            rot=ring_rot,
        )


def add_fence(coll, plot, door_y):
    front_x = plot["front_x"] + 0.10
    back_x = plot["back_x"] + 0.08
    y0 = plot["y0"] + 0.15
    y1 = plot["y1"] - 0.15
    gate_w = 3.60
    gy0 = max(y0 + 1.0, door_y - gate_w / 2)
    gy1 = min(y1 - 1.0, door_y + gate_w / 2)
    gate_c = (gy0 + gy1) / 2
    pier_points = [
        (front_x, y0),
        (front_x, gy0),
        (front_x, gy1),
        (front_x, y1),
        (back_x, y0),
        (back_x, y1),
    ]
    for x, y in pier_points:
        stone_pier(f"a40_fence_pier_{x:.1f}_{y:.1f}", coll, x, y)
    iron_run("a40_fence_front_low", coll, "Y", y0, gy0, front_x, posts_between(y0, gy0))
    iron_run(
        "a40_fence_front_high", coll, "Y", gy1, y1, front_x, posts_between(gy1, y1)
    )
    iron_run("a40_fence_back", coll, "Y", y0, y1, back_x, posts_between(y0, y1))
    iron_run(
        "a40_fence_south",
        coll,
        "X",
        back_x,
        front_x,
        y0,
        posts_between(back_x, front_x),
    )
    iron_run(
        "a40_fence_north",
        coll,
        "X",
        back_x,
        front_x,
        y1,
        posts_between(back_x, front_x),
    )
    gate_leaf(
        "a40_fence_gate_left", coll, "Y", gy0 + 0.08, gate_c - 0.03, front_x + 0.018
    )
    gate_leaf(
        "a40_fence_gate_right", coll, "Y", gate_c + 0.03, gy1 - 0.08, front_x + 0.018
    )
    cylinder(
        "a40_fence_gate_handle_l",
        (front_x + 0.07, gate_c - 0.08, 0.92),
        0.035,
        0.12,
        MAT_IRON,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    cylinder(
        "a40_fence_gate_handle_r",
        (front_x + 0.07, gate_c + 0.08, 0.92),
        0.035,
        0.12,
        MAT_IRON,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    print(
        f"[all41] fence X[{back_x:.2f},{front_x:.2f}] Y[{y0:.2f},{y1:.2f}] gate Y[{gy0:.2f},{gy1:.2f}]",
        flush=True,
    )


plot = add_marble_paving(House, MAT_MARBLE, MAT_SEAM, emn, emx, mn3, mx3)
print("[all41] large house marble paving with physical seams added", flush=True)
add_fence(House, plot, fcy)


# ─── TWO SMALLER FRESH INFINIGEN HOUSES ──────────────────────────────────────
def import_infinigen_house(
    label, blend_path, target_front_x, target_cy, scale, simple=True
):
    with bpy.data.libraries.load(str(blend_path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if WANT(c)]
    objs = set()
    for c in [c for c in dst.collections if c]:
        for o in c.all_objects:
            objs.add(o)
    coll = bpy.data.collections.new(f"House_{label}_indoor")
    bpy.context.scene.collection.children.link(coll)
    for o in objs:
        try:
            coll.objects.link(o)
        except RuntimeError:
            pass
    for o in objs:
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

    root = bpy.data.objects.new(f"House_{label}_root", None)
    bpy.context.scene.collection.objects.link(root)
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.parent = root
            o.matrix_parent_inverse = root.matrix_world.inverted()
    bpy.context.view_layer.update()

    mn0, mx0 = hbbox(objs)
    hcx0, hcy0 = (mn0[0] + mx0[0]) / 2, (mn0[1] + mx0[1]) / 2
    win_objs = [o for o in objs if o.type == "MESH" and in_coll(o, "windows")]
    fv2 = Vector((0.0, 0.0))
    for wobj in win_objs:
        cc = cxyz(wobj)
        fv2 += Vector((cc.x - hcx0, cc.y - hcy0))
    root.rotation_euler.z = (
        round((-math.atan2(fv2.y, fv2.x)) / (math.pi / 2)) * (math.pi / 2)
        if (win_objs and fv2.length > 0.3)
        else (0.0 if (mx0[0] - mn0[0]) >= (mx0[1] - mn0[1]) else math.pi / 2)
    )
    root.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    mn1, mx1 = hbbox(objs)
    root.location.x += target_front_x - mx1[0]
    root.location.y += target_cy - (mn1[1] + mx1[1]) / 2
    root.location.z += 0.0 - mn1[2]
    bpy.context.view_layer.update()

    hmn, hmx = hbbox(objs)
    ext_objs = [o for o in objs if o.type == "MESH" and in_coll(o, "room_exterior")]
    smn, smx = hbbox(ext_objs) if ext_objs else (hmn, hmx)
    sfx = smx[0]
    sfcy = (smn[1] + smx[1]) / 2.0
    _, rz = build_hip_roof(
        smn,
        smx,
        MAT_TILE,
        MAT_ROOF_FASCIA,
        coll,
        overhang=0.0,
        pitch_frac=0.12,
        prefix=f"a41_{label}",
    )

    door_h = 2.08
    door_w = 1.05
    box(
        f"{label}_fd_frame",
        sfx + 0.020,
        sfcy,
        door_h / 2,
        0.090,
        door_w + 0.24,
        door_h + 0.18,
        MAT_FRAME,
        coll,
        bevel_width=0.010,
    )
    box(
        f"{label}_fd_leaf",
        sfx + 0.072,
        sfcy,
        door_h / 2,
        0.065,
        door_w,
        door_h,
        MAT_WOOD,
        coll,
        bevel_width=0.010,
    )
    box(
        f"{label}_fd_glass",
        sfx + 0.112,
        sfcy,
        1.62,
        0.026,
        door_w - 0.32,
        0.54,
        MAT_GLASS,
        coll,
        bevel_width=0.004,
    )
    cylinder(
        f"{label}_fd_handle",
        (sfx + 0.150, sfcy - door_w * 0.32, 1.05),
        0.038,
        0.18,
        MAT_DARK,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )

    win_count = 0
    for k, wy in enumerate((sfcy - 2.65, sfcy + 2.65)):
        if wy < smn[1] + 0.45 or wy > smx[1] - 0.45:
            continue
        win_count += 1
        box(
            f"{label}_fw{k}_outer_frame",
            sfx + 0.017,
            wy,
            1.52,
            0.095,
            1.22,
            1.28,
            MAT_FRAME,
            coll,
            bevel_width=0.009,
        )
        box(
            f"{label}_fw{k}_glass",
            sfx + 0.082,
            wy,
            1.52,
            0.028,
            1.00,
            1.05,
            MAT_GLASS,
            coll,
            bevel_width=0.004,
        )
        box(
            f"{label}_fw{k}_mullv",
            sfx + 0.106,
            wy,
            1.52,
            0.032,
            0.055,
            1.05,
            MAT_FRAME,
            coll,
            bevel_width=0.004,
        )
        box(
            f"{label}_fw{k}_sill",
            sfx + 0.098,
            wy,
            0.83,
            0.15,
            1.34,
            0.08,
            MAT_DARK,
            coll,
            bevel_width=0.005,
        )

    pad_margin_x = 1.25
    pad_margin_y = 1.15
    px0, px1 = smn[0] - pad_margin_x, min(-10.9, smx[0] + 1.25)
    py0, py1 = max(10.8, hmn[1] - pad_margin_y), min(54.1, hmx[1] + pad_margin_y)
    if px1 > px0 and py1 > py0:
        box(
            f"{label}_marble_pad",
            (px0 + px1) / 2,
            (py0 + py1) / 2,
            0.052,
            px1 - px0,
            py1 - py0,
            0.050,
            MAT_MARBLE,
            coll,
            bevel_width=0.004,
        )
        sy = math.ceil(py0 / 1.15) * 1.15
        j = 0
        while sy < py1:
            box(
                f"{label}_pad_seam_y_{j}",
                (px0 + px1) / 2,
                sy,
                0.083,
                px1 - px0,
                0.020,
                0.010,
                MAT_SEAM,
                coll,
                bevel_width=0,
            )
            sy += 1.15
            j += 1
    print(
        f"[all41] {label} house imported {len(objs)} objects; "
        f"X[{hmn[0]:.1f},{hmx[0]:.1f}] Y[{hmn[1]:.1f},{hmx[1]:.1f}] roof_z={rz:.2f} windows={win_count}",
        flush=True,
    )
    return objs, coll, (hmn, hmx)


_res_cfg = (
    {
        "small_a_y": 18.8,
        "small_b_y": 45.8,
        "small_a_scale": 0.61,
        "small_b_scale": 0.73,
        "apt_floors": 8,
        "apt_y": 31.5,
        "apt_depth": 19.0,
    }
    if FULL_VARIANT == "demo2"
    else {
        "small_a_y": 17.9,
        "small_b_y": 47.2,
        "small_a_scale": 0.68,
        "small_b_scale": 0.66,
        "apt_floors": 5,
        "apt_y": 31.0,
        "apt_depth": 20.4,
    }
)
small_a_objs, SmallA, small_a_bbox = import_infinigen_house(
    "small_a",
    HOUSE_BLENDS["small_a"],
    target_front_x=-16.2,
    target_cy=_res_cfg["small_a_y"],
    scale=_res_cfg["small_a_scale"],
)
small_b_objs, SmallB, small_b_bbox = import_infinigen_house(
    "small_b",
    HOUSE_BLENDS["small_b"],
    target_front_x=-16.2,
    target_cy=_res_cfg["small_b_y"],
    scale=_res_cfg["small_b_scale"],
)


# ─── EXTERIOR-ONLY PROCEDURAL APARTMENT BUILDING ─────────────────────────────
MAT_APT_BODY = principled_mat(
    "a41_apartment_warm_stone", (0.58, 0.56, 0.50, 1.0), roughness=0.82
)
MAT_APT_ACCENT = principled_mat(
    "a41_apartment_vertical_accent", (0.30, 0.34, 0.36, 1.0), roughness=0.68
)
MAT_APT_BALC = principled_mat(
    "a41_apartment_balcony_black",
    (0.05, 0.055, 0.06, 1.0),
    roughness=0.42,
    metallic=0.55,
)


def add_apartment_building():
    coll = bpy.data.collections.new("Residential_apartment_exterior")
    bpy.context.scene.collection.children.link(coll)
    cx, cy = -47.0, _res_cfg["apt_y"]
    w, d = 9.2, _res_cfg["apt_depth"]
    floors = _res_cfg["apt_floors"]
    floor_h = 2.75
    h = floors * floor_h
    box("a41_apt_body", cx, cy, h / 2, w, d, h, MAT_APT_BODY, coll, bevel_width=0.025)
    box(
        "a41_apt_plinth",
        cx,
        cy,
        0.35,
        w + 0.45,
        d + 0.40,
        0.70,
        MAT_DARK,
        coll,
        bevel_width=0.018,
    )
    box(
        "a41_apt_roof_cap",
        cx,
        cy,
        h + 0.18,
        w + 0.35,
        d + 0.35,
        0.36,
        MAT_ROOF_FASCIA,
        coll,
        bevel_width=0.015,
    )
    box(
        "a41_apt_parapet_front",
        cx + w / 2 + 0.08,
        cy,
        h + 0.70,
        0.16,
        d + 0.42,
        0.88,
        MAT_ROOF_FASCIA,
        coll,
        bevel_width=0.010,
    )
    box(
        "a41_apt_parapet_back",
        cx - w / 2 - 0.08,
        cy,
        h + 0.70,
        0.16,
        d + 0.42,
        0.88,
        MAT_ROOF_FASCIA,
        coll,
        bevel_width=0.010,
    )
    box(
        "a41_apt_corner_accent_s",
        cx + w / 2 + 0.03,
        cy - d / 2 + 1.05,
        h / 2 + 0.25,
        0.20,
        1.15,
        h - 0.5,
        MAT_APT_ACCENT,
        coll,
        bevel_width=0.008,
    )
    box(
        "a41_apt_corner_accent_n",
        cx + w / 2 + 0.03,
        cy + d / 2 - 1.05,
        h / 2 + 0.25,
        0.20,
        1.15,
        h - 0.5,
        MAT_APT_ACCENT,
        coll,
        bevel_width=0.008,
    )

    front_x = cx + w / 2 + 0.06
    for floor in range(floors):
        z = 1.55 + floor * floor_h
        for j, yy in enumerate([cy - 7.0, cy - 3.5, cy, cy + 3.5, cy + 7.0]):
            box(
                f"a41_apt_front_win_{floor}_{j}_frame",
                front_x,
                yy,
                z,
                0.10,
                1.22,
                1.32,
                MAT_FRAME,
                coll,
                bevel_width=0.006,
            )
            box(
                f"a41_apt_front_win_{floor}_{j}_glass",
                front_x + 0.055,
                yy,
                z,
                0.026,
                0.96,
                1.06,
                MAT_GLASS,
                coll,
                bevel_width=0.003,
            )
            if floor > 0 and j in (1, 3):
                box(
                    f"a41_apt_balcony_slab_{floor}_{j}",
                    front_x + 0.42,
                    yy,
                    z - 0.82,
                    0.78,
                    1.65,
                    0.10,
                    MAT_CONCRETE,
                    coll,
                    bevel_width=0.006,
                )
                box(
                    f"a41_apt_balcony_rail_{floor}_{j}",
                    front_x + 0.82,
                    yy,
                    z - 0.45,
                    0.055,
                    1.52,
                    0.55,
                    MAT_APT_BALC,
                    coll,
                    bevel_width=0.004,
                )
                box(
                    f"a41_apt_balcony_top_{floor}_{j}",
                    front_x + 0.83,
                    yy,
                    z - 0.16,
                    0.070,
                    1.64,
                    0.060,
                    MAT_APT_BALC,
                    coll,
                    bevel_width=0.004,
                )

    side_y0 = cy - d / 2 - 0.055
    side_y1 = cy + d / 2 + 0.055
    for floor in range(floors):
        z = 1.55 + floor * floor_h
        for i, xx in enumerate([cx - 2.7, cx, cx + 2.7]):
            box(
                f"a41_apt_south_win_{floor}_{i}",
                xx,
                side_y0,
                z,
                1.05,
                0.10,
                1.16,
                MAT_GLASS,
                coll,
                bevel_width=0.004,
            )
            box(
                f"a41_apt_north_win_{floor}_{i}",
                xx,
                side_y1,
                z,
                1.05,
                0.10,
                1.16,
                MAT_GLASS,
                coll,
                bevel_width=0.004,
            )

    box(
        "a41_apt_entry_frame",
        front_x + 0.02,
        cy,
        1.35,
        0.12,
        2.00,
        2.35,
        MAT_FRAME,
        coll,
        bevel_width=0.010,
    )
    box(
        "a41_apt_entry_glass_l",
        front_x + 0.09,
        cy - 0.48,
        1.20,
        0.035,
        0.72,
        1.90,
        MAT_GLASS,
        coll,
        bevel_width=0.004,
    )
    box(
        "a41_apt_entry_glass_r",
        front_x + 0.09,
        cy + 0.48,
        1.20,
        0.035,
        0.72,
        1.90,
        MAT_GLASS,
        coll,
        bevel_width=0.004,
    )
    box(
        "a41_apt_entry_canopy",
        front_x + 0.65,
        cy,
        2.58,
        1.20,
        2.70,
        0.16,
        MAT_ROOF_FASCIA,
        coll,
        bevel_width=0.010,
    )
    for i, yy in enumerate((cy - 3.2, cy, cy + 3.2)):
        box(
            f"a41_apt_roof_unit_{i}",
            cx - 1.7 + i * 1.65,
            yy,
            h + 0.55,
            1.10,
            1.15,
            0.55,
            MAT_APT_ACCENT,
            coll,
            bevel_width=0.010,
        )
    box(
        "a41_apt_marble_front_pad",
        -40.8,
        cy,
        0.055,
        3.2,
        d + 1.6,
        0.055,
        MAT_MARBLE,
        coll,
        bevel_width=0.004,
    )
    print(
        f"[all41] apartment exterior X[{cx - w/2:.1f},{cx + w/2:.1f}] Y[{cy - d/2:.1f},{cy + d/2:.1f}] floors={floors}",
        flush=True,
    )
    return coll


Apartment = add_apartment_building()


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


furniture_keys = (
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
furn = [
    o
    for o in house_objs
    if o.type == "MESH" and any(key in o.name for key in furniture_keys)
]
fmn, fmx = hbbox([o for o in furn if o.dimensions.length > 0.5] or furn or house_objs)
fc = ((fmn[0] + fmx[0]) / 2, (fmn[1] + fmx[1]) / 2, (fmn[2] + fmx[2]) / 2)
cam_furn = make_cam(
    "cam_int_furniture",
    (fmx[0] + 4.6, fc[1] - 3.4, max(1.45, fmn[2] + 1.55)),
    (fc[0] - 0.4, fc[1] + 0.2, max(0.70, fmn[2] + 0.85)),
    64,
)

if kept_front_windows:
    window_y, window_z, window_w, window_h = kept_front_windows[0]
else:
    window_y, window_z = fcy - 3.4, 1.58
cam_win = make_cam(
    "cam_int_window",
    (emx[0] - 4.2, window_y - 0.55, max(1.82, window_z + 0.34)),
    (plot["front_x"] + 15.5, window_y + 0.15, max(1.72, window_z + 0.16)),
    52,
)
print(
    f"[all41] raised window camera y={window_y:.2f} z={max(1.82, window_z + 0.34):.2f}",
    flush=True,
)


def aim_existing_camera(name, loc, tgt, fov):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = make_cam(name, loc, tgt, fov)
    else:
        cam.location = loc
        cam.data.lens_unit = "FOV"
        cam.data.angle = math.radians(fov)
        cam.rotation_euler = (
            (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        )
    return cam


aim_existing_camera("cam_residential", (-4.5, 6.5, 27.5), (-33.5, 31.5, 4.8), 62)
print("[all41] residential camera widened for three houses plus apartment", flush=True)


# ─── SAVE + RENDER ────────────────────────────────────────────────────────────
out_blend = OUT / "urban_v3_all41.blend"
if os.environ.get("C2W_SKIP_INTERMEDIATE_SAVES") != "1":
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
else:
    print("[full02] Intermediate all41 save skipped; scene remains in memory.")
print("[all41] saved blend", flush=True)
sc = bpy.context.scene

EXT = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cn, fn in [] if os.environ.get("C2W_SKIP_LEGACY_RENDERS") == "1" else EXT:
    cam = bpy.data.objects.get(cn)
    if not cam:
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fn)
    print(f"[all41] render {fn}", flush=True)
    bpy.ops.render.render(write_still=True)


def reset_house_visibility():
    for o in house_objs:
        if o.type == "MESH":
            o.hide_render = False


if os.environ.get("C2W_SKIP_LEGACY_RENDERS") != "1":
    reset_house_visibility()
    for o in house_objs:
        if o.type == "MESH" and (
            in_coll(o, "room_wall")
            or in_coll(o, "room_exterior")
            or in_coll(o, "room_ceiling")
        ):
            o.hide_render = True
    sc.camera = cam_furn
    sc.render.filepath = str(OUT / "interior_furniture.png")
    print("[all41] render interior_furniture.png", flush=True)
    bpy.ops.render.render(write_still=True)

    reset_house_visibility()
    for o in house_objs:
        if o.type == "MESH" and (
            in_coll(o, "room_wall") or in_coll(o, "room_exterior")
        ):
            o.hide_render = True
    sc.camera = cam_win
    sc.render.filepath = str(OUT / "interior_window.png")
    print("[all41] render interior_window.png", flush=True)
    bpy.ops.render.render(write_still=True)

print("[all41] ALL DONE.", flush=True)
