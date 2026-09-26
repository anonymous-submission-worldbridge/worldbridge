"""Photorealistic procedural street-kiosk scene v3 (urban_v3_kiosk3).

kiosk2 still read as a game/animation prop: a stylised green newsstand made of
clean boxes with no branding.  The user's reference photos are compact, heavily
Branded commercial food/beverage kiosks:

  * REF A - "THE U COFFEE & TEA": a signature CURVED BARREL end (gold drum with a
    round face), a black sign-board header with the U logo + latin wordmark, a
    cream awning over an open serving counter with a glass pastry case + marble
    top + espresso machine, black side panels with white CJK/latin lettering.
  * REF B - a red McDONALD'S food kiosk: deep-red painted body, a yellow peaked
    fascia under the golden arches of McDonald's with an open glass serving window
    showing interior equipment, and a side glass panel of promo posters.

The realism levers over kiosk2:
  * REAL SIGNAGE - crisp lettering + logos via Blender FONT objects (latin AND
    CJK from Noto/Droid), not blocky numpy text.  Branding is what sells a kiosk.
  * DISTINCTIVE SILHOUETTES - a barrel-vault gold drum and a peaked golden-arch
    roof, not flat boxes.
  * OPEN, DRESSED INTERIORS - lit counters with an espresso machine, pastry case,
    cups, menu boards - so the booths read as working shops.
  * BOLD TWO-TONE PBR - glossy automotive paint, black satin panels, cream awning
    fabric, brushed alu framing, polished marble.
  * WET GRANITE PLAZA + split-sky city HDRI (bright to camera, weak for lighting
    so the sun casts a real shadow) + AgX + DoF + glare, as in kiosk2.

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_kiosk3.py
Env:
  V3_STILL_ONLY=1   hero still only (fast look-dev)
  K_ENV=city|courtyard|sunset|sunrise   pick the HDRI (default city)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk3):
  kiosk.blend  kiosk.png (hero, coffee)  kiosk_b.png (mcd)  kiosk_overview.png
  kiosk.mp4 (dolly)
"""

from __future__ import annotations

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
_wb_BLENDER_RESOURCES = _wb_paths["BLENDER_RESOURCES"]


import math
import os
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk3")
SCENE_PATH = OUTPUT_DIR / "kiosk.blend"
STILL_PATH = OUTPUT_DIR / "kiosk.png"
STILL_B_PATH = OUTPUT_DIR / "kiosk_b.png"
OVERVIEW_PATH = OUTPUT_DIR / "kiosk_overview.png"
VIDEO_PATH = OUTPUT_DIR / "kiosk.mp4"

BLENDER_ROOT = Path(f"{_wb_BLENDER_RESOURCES}")
HDRI_DIR = BLENDER_ROOT / "datafiles/studiolights/world"

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


# --------------------------------------------------------------------------- #
# Scene bookkeeping
# --------------------------------------------------------------------------- #
def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.images,
        bpy.data.lights,
        bpy.data.fonts,
    ):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def add_collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def link_to(obj, coll):
    coll.objects.link(obj)
    try:
        bpy.context.collection.objects.unlink(obj)
    except RuntimeError:
        pass
    return obj


def smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


# --------------------------------------------------------------------------- #
# Material toolkit (workhorse PBR from kiosk2)
# --------------------------------------------------------------------------- #
def _ramp(nt, positions_colors):
    r = nt.nodes.new("ShaderNodeValToRGB")
    ramp = r.color_ramp
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[-1])
    first = True
    for pos, col in positions_colors:
        el = ramp.elements[0] if first else ramp.elements.new(pos)
        el.position = pos
        el.color = (col[0], col[1], col[2], 1.0)
        first = False
    return r


def _principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    return m, nt, b


def _set(b, key, val):
    for k in [key] if isinstance(key, str) else key:
        if k in b.inputs:
            b.inputs[k].default_value = val
            return True
    return False


def mat_surface(
    name,
    color,
    *,
    metallic=0.0,
    base_rough=0.45,
    rough_var=0.12,
    rough_scale=7.0,
    bump=0.12,
    bump_scale=90.0,
    wear=0.0,
    wear_color=(0.34, 0.35, 0.37),
    dirt=0.28,
    ao_dist=0.18,
    coat=0.0,
    specular=0.5,
    anisotropy=0.0,
    wave_scratch=False,
):
    """A weathered, textured PBR surface: the workhorse for metal/paint/plastic."""
    m, nt, b = _principled(name)
    _set(b, "Metallic", metallic)
    _set(b, "IOR", 1.45)
    _set(b, "Specular IOR Level", specular)
    _set(b, ("Coat Weight", "Coat"), coat)
    _set(b, "Anisotropic", anisotropy)

    nr = nt.nodes.new("ShaderNodeTexNoise")
    nr.inputs["Scale"].default_value = rough_scale
    nr.inputs["Detail"].default_value = 3.0
    lo, hi = max(0.0, base_rough - rough_var), min(1.0, base_rough + rough_var)
    cr = _ramp(nt, [(0.0, (lo, lo, lo)), (1.0, (hi, hi, hi))])
    nt.links.new(nr.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Roughness"])

    if wave_scratch:
        nb = nt.nodes.new("ShaderNodeTexWave")
        nb.wave_type = "BANDS"
        nb.inputs["Scale"].default_value = bump_scale
        nb.inputs["Distortion"].default_value = 6.0
        bump_out = nb.outputs["Fac"]
    else:
        nb = nt.nodes.new("ShaderNodeTexNoise")
        nb.inputs["Scale"].default_value = bump_scale
        nb.inputs["Detail"].default_value = 4.0
        bump_out = nb.outputs["Fac"]
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.004
    nt.links.new(bump_out, bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])

    ntc = nt.nodes.new("ShaderNodeTexNoise")
    ntc.inputs["Scale"].default_value = rough_scale * 0.5
    ntc.inputs["Detail"].default_value = 2.0
    c0 = (color[0], color[1], color[2])
    c1 = tuple(min(1.0, x * 1.14 + 0.01) for x in c0)
    cc = _ramp(nt, [(0.0, c0), (1.0, c1)])
    nt.links.new(ntc.outputs["Fac"], cc.inputs["Fac"])
    cur = cc.outputs["Color"]

    if wear > 0.0:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        pr = _ramp(nt, [(0.46, (0, 0, 0)), (0.62, (1, 1, 1))])
        nt.links.new(geo.outputs["Pointiness"], pr.inputs["Fac"])
        mw = nt.nodes.new("ShaderNodeMixRGB")
        mw.inputs["Fac"].default_value = wear
        nt.links.new(pr.outputs["Color"], mw.inputs["Fac"])
        nt.links.new(cur, mw.inputs["Color1"])
        mw.inputs["Color2"].default_value = (
            wear_color[0],
            wear_color[1],
            wear_color[2],
            1.0,
        )
        cur = mw.outputs["Color"]

    if dirt > 0.0:
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = ao_dist
        md = nt.nodes.new("ShaderNodeMixRGB")
        md.blend_type = "MULTIPLY"
        md.inputs["Fac"].default_value = dirt
        nt.links.new(cur, md.inputs["Color1"])
        nt.links.new(ao.outputs["Color"], md.inputs["Color2"])
        cur = md.outputs["Color"]

    nt.links.new(cur, b.inputs["Base Color"])
    return m


def mat_marble(name, base=(0.78, 0.77, 0.73)):
    """Polished marble: veined by a distorted wave, low roughness, clear coat."""
    m, nt, b = _principled(name)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = "DIAGONAL"
    w.inputs["Scale"].default_value = 2.4
    w.inputs["Distortion"].default_value = 9.0
    w.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], w.inputs["Vector"])
    dark = tuple(x * 0.6 for x in base)
    vein = _ramp(
        nt, [(0.0, base), (0.45, base), (0.5, dark), (0.55, base), (1.0, base)]
    )
    nt.links.new(w.outputs["Fac"], vein.inputs["Fac"])
    nt.links.new(vein.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.14)
    _set(b, ("Coat Weight", "Coat"), 0.4)
    _set(b, "Coat Roughness", 0.08)
    return m


def mat_glass(name, tint=(0.86, 0.90, 0.90), rough=0.02):
    m, nt, b = _principled(name)
    _set(b, "Base Color", (tint[0], tint[1], tint[2], 1.0))
    _set(b, ("Transmission Weight", "Transmission"), 1.0)
    _set(b, "IOR", 1.5)
    _set(b, "Metallic", 0.0)
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    cr = _ramp(nt, [(0.0, (rough, rough, rough)), (1.0, (rough + 0.05,) * 3)])
    nt.links.new(n.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Roughness"])
    m.use_screen_refraction = True
    return m


def mat_emit(name, color, strength):
    m, nt, b = _principled(name)
    _set(b, "Base Color", (color[0], color[1], color[2], 1.0))
    _set(b, "Emission Color", (color[0], color[1], color[2], 1.0))
    _set(b, "Emission Strength", strength)
    _set(b, "Roughness", 0.4)
    return m


def mat_image(name, img, rough=0.34, emit=0.0, coat=0.15):
    m, nt, b = _principled(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Cubic"
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", rough)
    _set(b, ("Coat Weight", "Coat"), coat)
    if emit > 0.0:
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        _set(b, "Emission Strength", emit)
    return m


# --------------------------------------------------------------------------- #
# numpy content textures (posters / menu boards)
# --------------------------------------------------------------------------- #
def _new_image(name, arr):
    h, w, _ = arr.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(arr, 0, 1)
    img = bpy.data.images.new(name, width=w, height=h)
    img.pixels.foreach_set(rgba[::-1].reshape(-1))
    img.pack()
    return img


def make_icecream_poster(name, w=180, h=300):
    """A glossy promo poster: coloured field, a soft ice-cream cone, price block."""
    a = np.ones((h, w, 3), dtype=np.float32)
    yy, xx = np.ogrid[:h, :w]
    # cool gradient field (blue -> white), like a fridge/dessert ad
    for y in range(h):
        t = y / h
        a[y, :, :] = (
            np.array([0.15, 0.45, 0.72]) * (1 - t) + np.array([0.86, 0.93, 0.98]) * t
        )
    # top brand band
    a[: int(h * 0.13), :, :] = np.array([0.80, 0.05, 0.10])
    # a soft swirl "ice cream" blob mid-frame
    cx, cy = int(w * 0.5), int(h * 0.52)
    for k, (rr, col) in enumerate(
        [(52, (0.98, 0.94, 0.86)), (40, (0.96, 0.85, 0.72)), (28, (0.95, 0.78, 0.62))]
    ):
        m = ((xx - cx) ** 2 + (yy - (cy - k * 22)) ** 2) < rr**2
        a[m] = np.array(col)
    # cone (triangle) below
    for y in range(cy + 26, cy + 110):
        halfw = int((1 - (y - (cy + 26)) / 84) * 34)
        a[y, cx - halfw : cx + halfw, :] = np.array([0.80, 0.60, 0.32])
    # price plate bottom
    a[int(h * 0.80) : int(h * 0.96), int(w * 0.12) : int(w * 0.88), :] = np.array(
        [0.98, 0.85, 0.05]
    )
    a[int(h * 0.83) : int(h * 0.93), int(w * 0.18) : int(w * 0.82), :] = np.array(
        [0.80, 0.05, 0.10]
    )
    return _new_image(name, a)


def make_menu_board(name, w=320, h=180):
    """Backlit menu board: warm cream field, header bar, three price rows w/ photos."""
    a = np.ones((h, w, 3), dtype=np.float32)
    a[:, :, :] = np.array([0.96, 0.92, 0.84])
    a[: int(h * 0.22), :, :] = np.array([0.55, 0.09, 0.09])  # header
    rng = np.random.RandomState(3)
    for i in range(3):
        y0 = int(h * (0.30 + i * 0.22))
        # product thumbnail
        col = [(0.72, 0.45, 0.22), (0.85, 0.70, 0.35), (0.55, 0.30, 0.18)][i]
        a[
            y0 : y0 + int(h * 0.16), int(w * 0.06) : int(w * 0.06) + int(h * 0.16), :
        ] = np.array(col)
        # text lines
        for r in range(2):
            yy = y0 + 6 + r * int(h * 0.07)
            ln = rng.randint(int(w * 0.35), int(w * 0.5))
            a[yy : yy + 4, int(w * 0.30) : int(w * 0.30) + ln, :] = np.array(
                [0.15, 0.12, 0.10]
            )
        # price
        a[y0 + 4 : y0 + int(h * 0.12), int(w * 0.80) : int(w * 0.92), :] = np.array(
            [0.55, 0.09, 0.09]
        )
    return _new_image(name, a)


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _bevel(obj, width=0.008, segments=2):
    if width <= 0:
        return
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("wn", "WEIGHTED_NORMAL")


def cube(name, loc, dims, mat, coll, rot=(0, 0, 0), bevel=0.008):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    _bevel(o, bevel)
    return link_to(o, coll)


def wedge(name, loc, dims, mat, coll, rot=(0, 0, 0), bevel=0.0):
    """A right-triangular prism (ramp): full at -X, zero height toward +X."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    # slope the top: lift only the -X top edge
    me = o.data
    for v in me.vertices:
        if v.co.z > 0 and v.co.x > 0:
            v.co.z = -0.5  # collapse +X top down to bottom
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.location = loc
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    _bevel(o, bevel)
    return link_to(o, coll)


def plane_img(name, loc, size, mat, coll, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = (size[0], size[1], 0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    return link_to(o, coll)


def cyl(name, loc, r, depth, mat, coll, verts=48, axis="Z", rot=None):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=depth, location=loc
    )
    o = bpy.context.object
    o.name = name
    if rot is not None:
        o.rotation_euler = rot
    elif axis == "X":
        o.rotation_euler = (0, math.radians(90), 0)
    elif axis == "Y":
        o.rotation_euler = (math.radians(90), 0, 0)
    if mat:
        o.data.materials.append(mat)
    smooth(o)
    return link_to(o, coll)


def cyl_between(name, a, b, r, mat, coll, verts=20):
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=max(d.length, 1e-4), location=(a + b) * 0.5
    )
    o = bpy.context.object
    o.name = name
    if d.length > 1e-6:
        o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    if mat:
        o.data.materials.append(mat)
    smooth(o)
    return link_to(o, coll)


def barrel_vault(name, cx, y0, y1, R, straight_h, mat, coll, segs=48, cap=True):
    """Tombstone/arch tunnel: vertical sides of height ``straight_h`` topped by a
    semicircle of radius ``R``, extruded along Y from y0 to y1.  Flat bottom at
    z=0, apex at z=straight_h+R, spans x in [cx-R, cx+R].  A real arch silhouette
    (not a bulging half-sphere)."""
    outline = [(cx - R, 0.0), (cx - R, straight_h)]
    for i in range(1, segs):
        a = math.pi * i / segs
        outline.append((cx - R * math.cos(a), straight_h + R * math.sin(a)))
    outline.append((cx + R, straight_h))
    outline.append((cx + R, 0.0))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    r0 = [bm.verts.new((x, y0, z)) for (x, z) in outline]
    r1 = [bm.verts.new((x, y1, z)) for (x, z) in outline]
    n = len(outline)
    for i in range(n - 1):
        bm.faces.new((r0[i], r0[i + 1], r1[i + 1], r1[i]))
    bm.faces.new((r0[n - 1], r0[0], r1[0], r1[n - 1]))  # flat bottom
    if cap:
        bm.faces.new(list(reversed(r0)))
        bm.faces.new(r1)
    bmesh.ops.recalculate_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    if mat:
        o.data.materials.append(mat)
    smooth(o)
    return link_to(o, coll)


# ---- real text via Blender FONT objects (the branding) -------------------- #
_FONT = None


def _get_font():
    global _FONT
    if _FONT is not None:
        return _FONT
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                _FONT = bpy.data.fonts.load(p)
                print(f"[v3k3] font: {Path(p).name}")
                return _FONT
            except Exception as exc:
                print(f"[v3k3] font load failed {p}: {exc!r}")
    print("[v3k3] WARNING: no font loaded, using Blender default")
    return None


def text3d(
    name,
    body,
    loc,
    size,
    mat,
    coll,
    *,
    rot=(math.radians(90), 0, 0),
    align_x="CENTER",
    align_y="CENTER",
    extrude=0.006,
    spacing=1.0,
    char_spacing=1.0,
):
    """Extruded text object.  Default rot stands it up facing -Y (front)."""
    cu = bpy.data.curves.new(name, "FONT")
    try:
        cu.body = body
    except Exception:
        cu.body = "".join(ch if ord(ch) < 128 else "?" for ch in body)
    f = _get_font()
    if f:
        cu.font = f
    cu.size = size
    cu.align_x = align_x
    cu.align_y = align_y
    cu.extrude = extrude
    cu.space_line = spacing
    cu.space_character = char_spacing
    o = bpy.data.objects.new(name, cu)
    o.location = loc
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    return link_to(o, coll)


# --------------------------------------------------------------------------- #
# Materials registry
# --------------------------------------------------------------------------- #
M = {}


def build_materials():
    # paints (glossy automotive, clear-coat)
    M["red"] = mat_surface(
        "k3_red",
        (0.44, 0.028, 0.028),
        base_rough=0.33,
        rough_var=0.08,
        wear=0.09,
        wear_color=(0.18, 0.02, 0.02),
        dirt=0.26,
        coat=0.25,
        bump=0.06,
        bump_scale=180,
    )
    M["gold"] = mat_surface(
        "k3_gold",
        (0.72, 0.52, 0.10),
        base_rough=0.34,
        rough_var=0.09,
        wear=0.08,
        wear_color=(0.46, 0.34, 0.08),
        dirt=0.24,
        coat=0.28,
        bump=0.06,
        bump_scale=180,
    )
    M["mcd_yellow"] = mat_surface(
        "k3_mcdyellow",
        (0.88, 0.62, 0.03),
        base_rough=0.30,
        rough_var=0.08,
        wear=0.06,
        dirt=0.20,
        coat=0.3,
        bump=0.05,
        bump_scale=200,
    )
    M["cream"] = mat_surface(
        "k3_cream",
        (0.80, 0.75, 0.64),
        base_rough=0.62,
        rough_var=0.12,
        wear=0.08,
        wear_color=(0.55, 0.5, 0.42),
        dirt=0.3,
        coat=0.0,
        bump=0.28,
        bump_scale=55,
    )  # awning canvas
    M["black_panel"] = mat_surface(
        "k3_black",
        (0.018, 0.018, 0.021),
        base_rough=0.34,
        rough_var=0.08,
        wear=0.05,
        wear_color=(0.1, 0.1, 0.11),
        dirt=0.25,
        coat=0.3,
        bump=0.06,
        bump_scale=160,
    )
    M["sign_black"] = mat_surface(
        "k3_signblack",
        (0.012, 0.012, 0.014),
        base_rough=0.22,
        rough_var=0.05,
        dirt=0.12,
        coat=0.45,
    )
    M["white"] = mat_surface(
        "k3_white",
        (0.86, 0.86, 0.85),
        base_rough=0.4,
        rough_var=0.08,
        dirt=0.12,
        coat=0.1,
    )
    M["text_white"] = mat_surface(
        "k3_textwhite", (0.92, 0.92, 0.9), base_rough=0.35, dirt=0.0, coat=0.1
    )
    M["text_gold"] = mat_surface(
        "k3_textgold",
        (0.95, 0.72, 0.08),
        metallic=0.7,
        base_rough=0.28,
        dirt=0.0,
        coat=0.2,
    )
    M["text_red"] = mat_surface(
        "k3_textred", (0.7, 0.04, 0.04), base_rough=0.35, dirt=0.0, coat=0.2
    )
    # metals / stone
    M["alu"] = mat_surface(
        "k3_alu",
        (0.62, 0.63, 0.65),
        metallic=1.0,
        base_rough=0.3,
        rough_var=0.1,
        bump=0.08,
        bump_scale=150,
        wear=0.2,
        wear_color=(0.7, 0.71, 0.72),
        dirt=0.22,
        anisotropy=0.4,
        wave_scratch=True,
    )
    M["steel"] = mat_surface(
        "k3_steel",
        (0.5, 0.51, 0.53),
        metallic=1.0,
        base_rough=0.22,
        rough_var=0.08,
        bump=0.06,
        bump_scale=180,
        wear=0.25,
        wear_color=(0.72, 0.73, 0.75),
        dirt=0.18,
        anisotropy=0.5,
        wave_scratch=True,
    )
    M["marble"] = mat_marble("k3_marble")
    M["glass"] = mat_glass("k3_glass")
    M["granite"] = mat_surface(
        "k3_granite",
        (0.055, 0.055, 0.06),
        base_rough=0.34,
        rough_var=0.12,
        rough_scale=5.0,
        bump=0.10,
        bump_scale=45,
        dirt=0.42,
        ao_dist=0.5,
        specular=0.45,
        coat=0.0,
    )
    M["grout"] = mat_surface("k3_grout", (0.02, 0.02, 0.022), base_rough=0.7, dirt=0.4)
    # emitters
    M["interior"] = mat_emit("k3_interior", (1.0, 0.96, 0.88), 4.5)
    M["strip"] = mat_emit("k3_strip", (1.0, 0.98, 0.92), 9.0)
    M["light_warm"] = mat_emit("k3_warm", (1.0, 0.9, 0.75), 3.0)
    # dark props / rubber
    M["dark"] = mat_surface("k3_dark", (0.03, 0.03, 0.035), base_rough=0.5, dirt=0.3)
    print("[v3k3] materials:", len(M))


# --------------------------------------------------------------------------- #
# KIOSK A - "THE U COFFEE & TEA"  (curved barrel drum + open counter)
# Built facing -Y (front toward camera).  cx shifts the whole kiosk in X.
# --------------------------------------------------------------------------- #
def build_kiosk_coffee(coll, cx=0.0):
    FRONT = -0.95  # counter opening plane
    BACK = 1.15
    DEPTH = BACK - FRONT
    CY = (FRONT + BACK) / 2
    body_x0, body_x1 = cx - 0.15, cx + 1.65  # flat-roof serving body
    bw = body_x1 - body_x0
    bcx = (body_x0 + body_x1) / 2
    H = 2.15

    # plinth
    cube(
        "A:plinth",
        (cx + 0.4, CY, 0.06),
        (bw + 2.9, DEPTH + 0.25, 0.12),
        M["granite"],
        coll,
        bevel=0.01,
    )

    # ---- signature gold ARCH end on the LEFT (barrel-vault tombstone) ------ #
    arch_R = 0.82
    arch_straight = 1.05
    arch_top = arch_straight + arch_R  # apex ~1.87
    arch_cx = body_x0 - arch_R  # right edge meets the body
    # gold barrel shell
    barrel_vault("A:arch", arch_cx, FRONT, BACK, arch_R, arch_straight, M["gold"], coll)
    # recessed cream tombstone face proud of the front (gold reveal shows around)
    barrel_vault(
        "A:arch_face",
        arch_cx,
        FRONT - 0.03,
        FRONT - 0.006,
        arch_R * 0.85,
        arch_straight,
        M["cream"],
        coll,
    )
    # flush service door low-left on the cream face
    cube(
        "A:arch_door",
        (arch_cx - 0.30, FRONT - 0.05, 0.60),
        (0.52, 0.04, 1.12),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    cyl(
        "A:arch_handle",
        (arch_cx - 0.08, FRONT - 0.09, 0.60),
        0.016,
        0.28,
        M["steel"],
        coll,
        verts=16,
        axis="Z",
    )
    # vertical "COFFEE" down the right edge of the arch (as in the reference)
    text3d(
        "A:arch_coffee",
        "C\nO\nF\nF\nE\nE",
        (arch_cx + arch_R * 0.60, FRONT - 0.055, arch_top - 0.18),
        0.10,
        M["text_gold"],
        coll,
        align_y="TOP",
        spacing=1.0,
    )
    # black pilaster between the arch and the counter, carrying vertical CJK
    pil_x = cx - 0.12
    cube(
        "A:pilaster",
        (pil_x, FRONT - 0.01, 1.0),
        (0.3, 0.05, 2.0),
        M["sign_black"],
        coll,
        bevel=0.008,
    )
    text3d(
        "A:pil_cjk",
        "Tea making with fresh ingredients",
        (pil_x, FRONT - 0.05, 1.0),
        0.24,
        M["text_white"],
        coll,
        spacing=1.05,
    )

    # ---- serving body ----------------------------------------------------- #
    # back + right walls (black satin)
    cube(
        "A:back",
        (bcx, BACK - 0.02, H / 2),
        (bw, 0.06, H),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:right",
        (body_x1 - 0.02, CY, H / 2),
        (0.06, DEPTH, H),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    # roof slab
    cube(
        "A:roof",
        (bcx, CY, H + 0.03),
        (bw + 0.14, DEPTH + 0.12, 0.10),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    # brushed-alu corner posts
    for px in (body_x0 + 0.03, body_x1 - 0.03):
        cube(
            f"A:post:{px:.2f}",
            (px, FRONT + 0.02, H / 2),
            (0.09, 0.09, H),
            M["alu"],
            coll,
            bevel=0.012,
        )
    cube(
        "A:post_back",
        (body_x1 - 0.03, BACK - 0.03, H / 2),
        (0.09, 0.09, H),
        M["alu"],
        coll,
        bevel=0.012,
    )

    # ---- signboard header + branding ------------------------------------- #
    sb_x0, sb_x1 = cx - 0.35, body_x1 + 0.05
    sbw = sb_x1 - sb_x0
    sbcx = (sb_x0 + sb_x1) / 2
    cube(
        "A:signboard",
        (sbcx, FRONT - 0.03, 1.92),
        (sbw, 0.08, 0.42),
        M["sign_black"],
        coll,
        bevel=0.012,
    )
    # one clean line:  THE  [U]  COFFEE & TEA
    text3d(
        "A:the",
        "THE",
        (sb_x0 + 0.08, FRONT - 0.11, 1.92),
        0.12,
        M["text_white"],
        coll,
        align_x="LEFT",
    )
    cube(
        "A:ulogo",
        (sb_x0 + 0.46, FRONT - 0.08, 1.92),
        (0.32, 0.03, 0.32),
        M["text_red"],
        coll,
        bevel=0.02,
    )
    text3d("A:u", "U", (sb_x0 + 0.46, FRONT - 0.11, 1.90), 0.28, M["text_white"], coll)
    text3d(
        "A:word",
        "COFFEE & TEA",
        (sb_x0 + 0.68, FRONT - 0.11, 1.92),
        0.16,
        M["text_gold"],
        coll,
        align_x="LEFT",
    )

    # ---- cream awning over the counter ----------------------------------- #
    aw_y = FRONT - 0.02
    awning = cube(
        "A:awning",
        (sbcx, aw_y - 0.28, 1.6),
        (sbw + 0.05, 0.72, 0.05),
        M["cream"],
        coll,
        bevel=0.006,
        rot=(math.radians(20), 0, 0),
    )
    # scalloped valance (small half-round scallops along the front edge)
    n = max(10, int(sbw / 0.18))
    for i in range(n):
        vx = sb_x0 + (i + 0.5) * sbw / n
        cyl(
            f"A:valance:{i}",
            (vx, aw_y - 0.62, 1.45),
            0.06,
            0.02,
            M["cream"],
            coll,
            verts=18,
            axis="Y",
        )
    # front alu bar the awning hangs from
    cyl(
        "A:awn_bar",
        (sbcx, aw_y - 0.02, 1.72),
        0.03,
        sbw + 0.05,
        M["alu"],
        coll,
        verts=20,
        axis="X",
    )

    # ---- counter + interior ---------------------------------------------- #
    ct_y = FRONT + 0.28
    # marble counter top + black base
    cube(
        "A:counter_base",
        (bcx, ct_y, 0.5),
        (bw - 0.1, 0.5, 1.0),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:counter_top",
        (bcx, ct_y, 1.02),
        (bw - 0.02, 0.56, 0.05),
        M["marble"],
        coll,
        bevel=0.012,
    )
    # glass pastry display case on the counter
    disp_x = bcx - 0.35
    cube(
        "A:disp_base",
        (disp_x, ct_y, 1.09),
        (0.7, 0.5, 0.06),
        M["steel"],
        coll,
        bevel=0.006,
    )
    cube(
        "A:disp_glass",
        (disp_x, ct_y, 1.34),
        (0.68, 0.48, 0.44),
        M["glass"],
        coll,
        bevel=0.004,
    )
    for k, cc in enumerate([(0.75, 0.5, 0.28), (0.85, 0.7, 0.4), (0.6, 0.3, 0.2)]):
        cube(
            f"A:cake:{k}",
            (disp_x - 0.22 + k * 0.22, ct_y, 1.18),
            (0.14, 0.34, 0.08),
            mat_surface(f"k3_cake{k}", cc, base_rough=0.4, coat=0.3),
            coll,
            bevel=0.02,
        )
    # espresso machine (stainless) behind counter, right
    em_x = bcx + 0.5
    cube(
        "A:machine",
        (em_x, ct_y + 0.06, 1.28),
        (0.5, 0.4, 0.4),
        M["steel"],
        coll,
        bevel=0.02,
    )
    cube(
        "A:machine_top",
        (em_x, ct_y + 0.06, 1.5),
        (0.44, 0.36, 0.06),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    for gx in (em_x - 0.12, em_x + 0.12):
        cyl(
            f"A:grouphead:{gx:.2f}",
            (gx, ct_y - 0.18, 1.2),
            0.03,
            0.1,
            M["steel"],
            coll,
            verts=16,
            axis="Z",
        )
    # cups stacked on a shelf
    cube(
        "A:shelf",
        (bcx + 0.3, BACK - 0.12, 1.55),
        (bw - 0.5, 0.16, 0.03),
        M["alu"],
        coll,
        bevel=0.004,
    )
    for c in range(6):
        cx2 = bcx - 0.3 + c * 0.13
        cyl(
            f"A:cup:{c}",
            (cx2, BACK - 0.12, 1.62),
            0.028,
            0.07,
            M["white"],
            coll,
            verts=14,
            axis="Z",
        )
    # backlit menu board on the back wall
    mb = make_menu_board("k3_menu")
    plane_img(
        "A:menu",
        (bcx - 0.2, BACK - 0.06, 1.62),
        (0.9, 0.44),
        mat_image("k3_menumat", mb, rough=0.3, emit=1.6),
        coll,
        rot=(math.radians(90), 0, 0),
    )
    # interior ceiling light + fill glow
    cube(
        "A:ceil_light",
        (bcx, CY + 0.1, H - 0.08),
        (bw - 0.3, DEPTH - 0.5, 0.04),
        M["interior"],
        coll,
        bevel=0,
    )
    cube(
        "A:kickplate",
        (bcx, FRONT + 0.02, 0.14),
        (bw, 0.04, 0.28),
        M["steel"],
        coll,
        bevel=0.006,
    )

    return Vector((cx + 0.25, CY, 1.3))


# --------------------------------------------------------------------------- #
# KIOSK B - red McDONALD'S food kiosk (peaked yellow roof + arches)
# --------------------------------------------------------------------------- #
def build_kiosk_mcd(coll, cx=4.9):
    FRONT = -0.9
    BACK = 1.15
    DEPTH = BACK - FRONT
    CY = (FRONT + BACK) / 2
    x0, x1 = cx - 1.35, cx + 1.35
    bw = x1 - x0
    H = 2.05

    cube(
        "B:plinth",
        (cx, CY, 0.06),
        (bw + 0.4, DEPTH + 0.25, 0.12),
        M["granite"],
        coll,
        bevel=0.01,
    )
    # red body: back + right + left walls
    cube("B:back", (cx, BACK - 0.02, H / 2), (bw, 0.06, H), M["red"], coll, bevel=0.01)
    cube("B:left", (x0 + 0.02, CY, H / 2), (0.06, DEPTH, H), M["red"], coll, bevel=0.01)
    cube(
        "B:right", (x1 - 0.02, CY, H / 2), (0.06, DEPTH, H), M["red"], coll, bevel=0.01
    )
    # red counter/apron under the serving window (front, left half)
    win_x0, win_x1 = x0 + 0.05, cx + 0.15
    cube(
        "B:apron",
        ((win_x0 + win_x1) / 2, FRONT + 0.02, 0.55),
        (win_x1 - win_x0, 0.16, 1.1),
        M["red"],
        coll,
        bevel=0.01,
    )
    cube(
        "B:apron_top",
        ((win_x0 + win_x1) / 2, FRONT + 0.06, 1.12),
        (win_x1 - win_x0, 0.4, 0.06),
        M["steel"],
        coll,
        bevel=0.008,
    )

    # ---- red roof + yellow fascia + golden-arches sign pylon (ref1) -------- #
    roof_z = H + 0.14
    cube(
        "B:roof",
        (cx, CY + 0.04, roof_z),
        (bw + 0.38, DEPTH + 0.28, 0.12),
        M["red"],
        coll,
        bevel=0.02,
        rot=(math.radians(-6), 0, 0),
    )
    # bright yellow fascia band along the front eave
    cube(
        "B:fascia",
        (cx, FRONT - 0.17, roof_z - 0.02),
        (bw + 0.38, 0.10, 0.30),
        M["mcd_yellow"],
        coll,
        bevel=0.02,
    )
    # thin red drip edge below the fascia
    cube(
        "B:eave",
        (cx, FRONT - 0.15, roof_z - 0.20),
        (bw + 0.30, 0.06, 0.05),
        M["red"],
        coll,
        bevel=0.008,
    )
    # sign pylon rising from the roof front, carrying the golden arches + brand
    pyl_x, pyl_y = cx - 0.35, FRONT + 0.02
    cube(
        "B:pylon",
        (pyl_x, pyl_y + 0.06, roof_z + 0.46),
        (1.25, 0.10, 0.84),
        M["red"],
        coll,
        bevel=0.02,
    )
    text3d(
        "B:arch",
        "M",
        (pyl_x, pyl_y - 0.03, roof_z + 0.58),
        0.50,
        M["text_gold"],
        coll,
        char_spacing=0.85,
    )
    text3d(
        "B:brand",
        "McDonald's",
        (pyl_x, pyl_y - 0.03, roof_z + 0.20),
        0.15,
        M["text_gold"],
        coll,
    )

    # ---- serving window (glass) + interior ------------------------------- #
    cube(
        "B:win_glass",
        ((win_x0 + win_x1) / 2, FRONT - 0.0, 1.55),
        (win_x1 - win_x0 - 0.08, 0.03, 0.7),
        M["glass"],
        coll,
        bevel=0.004,
    )
    # interior: dark cavity + stainless counter + coffee machine + menu glow
    cube(
        "B:in_back",
        (cx - 0.5, BACK - 0.05, 1.4),
        (1.3, 0.04, 1.4),
        M["dark"],
        coll,
        bevel=0,
    )
    cube(
        "B:in_counter",
        ((win_x0 + win_x1) / 2, FRONT + 0.34, 1.2),
        (win_x1 - win_x0 - 0.1, 0.4, 0.06),
        M["steel"],
        coll,
        bevel=0.006,
    )
    cube(
        "B:in_machine",
        (cx - 0.4, FRONT + 0.44, 1.42),
        (0.4, 0.34, 0.34),
        M["steel"],
        coll,
        bevel=0.02,
    )
    cube(
        "B:in_light",
        (cx - 0.5, CY, H - 0.1),
        (1.2, DEPTH - 0.5, 0.04),
        M["interior"],
        coll,
        bevel=0,
    )
    mb = make_menu_board("k3_menu_b")
    plane_img(
        "B:menu",
        (cx - 0.5, BACK - 0.09, 1.55),
        (1.0, 0.4),
        mat_image("k3_menumat_b", mb, rough=0.3, emit=1.6),
        coll,
        rot=(math.radians(90), 0, 0),
    )

    # ---- right promo glass panel with posters ---------------------------- #
    pnl_x0, pnl_x1 = cx + 0.18, x1 - 0.05
    pcx = (pnl_x0 + pnl_x1) / 2
    cube(
        "B:panel_frame",
        (pcx, FRONT - 0.02, 1.2),
        (pnl_x1 - pnl_x0, 0.05, 1.9),
        M["red"],
        coll,
        bevel=0.01,
    )
    for k, dx in enumerate((-0.22, 0.22)):
        ic = make_icecream_poster(f"k3_promo_{k}")
        plane_img(
            f"B:poster:{k}",
            (pcx + dx, FRONT - 0.07, 1.25),
            (0.42, 1.5),
            mat_image(f"k3_promomat_{k}", ic, rough=0.28, coat=0.3),
            coll,
            rot=(math.radians(90), 0, 0),
        )
    cube(
        "B:panel_glass",
        (pcx, FRONT - 0.12, 1.25),
        (pnl_x1 - pnl_x0 - 0.05, 0.02, 1.55),
        M["glass"],
        coll,
        bevel=0.004,
    )
    return Vector((cx - 0.2, CY, 1.3))


# --------------------------------------------------------------------------- #
# Plaza ground
# --------------------------------------------------------------------------- #
def build_ground(coll):
    cube("gnd:slab", (2.0, 2.0, -0.02), (60, 40, 0.04), M["granite"], coll, bevel=0)
    # granite tile seams (large 1.0 m slabs)
    for i in range(-20, 26):
        cube(
            f"gnd:sx:{i}",
            (i * 1.0, 2.0, 0.001),
            (0.02, 40, 0.006),
            M["grout"],
            coll,
            bevel=0,
        )
    for j in range(-16, 20):
        cube(
            f"gnd:sy:{j}",
            (2.0, j * 1.0, 0.001),
            (60, 0.02, 0.006),
            M["grout"],
            coll,
            bevel=0,
        )


# --------------------------------------------------------------------------- #
# World (split-sky HDRI) + sun + cameras + render
# --------------------------------------------------------------------------- #
def build_world():
    env_name = os.environ.get("K_ENV", "city")
    path = HDRI_DIR / f"{env_name}.exr"
    if not path.exists():
        path = HDRI_DIR / "city.exr"
    world = bpy.data.worlds.new("k3_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for nname in list(nt.nodes):
        nt.nodes.remove(nname)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(path))
    mapping = nt.nodes.new("ShaderNodeMapping")
    texco = nt.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value = (0, 0, math.radians(70))
    nt.links.new(texco.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    bg_cam.inputs["Strength"].default_value = 1.1
    bg_light.inputs["Strength"].default_value = 0.32
    nt.links.new(env.outputs["Color"], bg_cam.inputs["Color"])
    nt.links.new(env.outputs["Color"], bg_light.inputs["Color"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_light.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    print(f"[v3k3] HDRI env: {path.name} (split-sky)")


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 6.0
    sun.data.angle = math.radians(1.6)
    sun.data.color = (1.0, 0.94, 0.84)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-58))


def _focus_empty(name, loc):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    return e


def make_camera(name, loc, target, lens=38, fstop=5.0):
    cam = bpy.data.cameras.new(name)
    o = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(o)
    cam.lens = lens
    cam.sensor_width = 36
    if fstop:
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
        cam.dof.focus_object = _focus_empty(f"{name}_focus", target)
    loc = Vector(loc)
    o.location = loc
    o.rotation_euler = (Vector(target) - loc).to_track_quat("-Z", "Y").to_euler()
    return o


def build_dolly(target_a, target_b):
    cam = bpy.data.cameras.new("cam_dolly")
    o = bpy.data.objects.new("cam_dolly", cam)
    bpy.context.scene.collection.objects.link(o)
    cam.lens = 34
    cam.sensor_width = 36
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = 4.0
    cam.dof.focus_object = _focus_empty("dolly_focus", target_a)
    keys = [
        (1, Vector((target_a.x - 4.6, -6.2, 2.0)), target_a),
        (48, Vector((2.4, -6.8, 2.1)), Vector((2.4, 0.2, 1.3))),
        (96, Vector((target_b.x + 3.6, -6.0, 1.9)), target_b),
    ]
    for f, loc, look in keys:
        o.location = loc
        o.rotation_euler = (Vector(look) - loc).to_track_quat("-Z", "Y").to_euler()
        o.keyframe_insert("location", frame=f)
        o.keyframe_insert("rotation_euler", frame=f)
    for fc in o.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return o


def setup_compositor():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    for nname in list(tree.nodes):
        tree.nodes.remove(nname)
    rl = tree.nodes.new("CompositorNodeRLayers")
    comp = tree.nodes.new("CompositorNodeComposite")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.1
    glare.size = 7
    if hasattr(glare, "mix"):
        glare.mix = -0.7
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def configure_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    chosen = None
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            devs = prefs.get_devices_for_type(backend)
            if devs:
                for dv in devs:
                    dv.use = True
                chosen = backend
                break
        except Exception:
            continue
    print(f"[v3k3] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 20
    scene.cycles.caustics_reflective = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = 0.15


def render_still(scene, cam, path, samples=560, res=(1920, 1080)):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    print(f"[v3k3] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


def render_video(scene, cam):
    scene.camera = cam
    scene.cycles.samples = 200
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.frame_start = 1
    scene.frame_end = 96
    scene.render.fps = 24
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.filepath = str(VIDEO_PATH)
    print("[v3k3] rendering dolly video ...")
    bpy.ops.render.render(animation=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ground_c = add_collection("k3_ground")
    a_c = add_collection("k3_coffee")
    b_c = add_collection("k3_mcd")

    build_ground(ground_c)
    target_a = build_kiosk_coffee(a_c, cx=0.0)
    target_b = build_kiosk_mcd(b_c, cx=4.9)

    build_world()
    add_sun()
    configure_cycles()
    setup_compositor()
    scene = bpy.context.scene

    hero = make_camera(
        "cam_hero",
        (target_a.x - 4.3, -5.6, 1.95),
        (target_a.x - 0.4, 0.1, 1.25),
        lens=35,
        fstop=5.0,
    )
    cam_b = make_camera(
        "cam_b",
        (target_b.x - 3.4, -5.4, 1.85),
        (target_b.x + 0.1, 0.1, 1.2),
        lens=38,
        fstop=5.0,
    )
    overview = make_camera(
        "cam_overview", (2.2, -8.2, 2.9), (2.4, 0.3, 1.2), lens=28, fstop=None
    )

    scene.camera = hero
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    if os.environ.get("V3_STILL_ONLY"):
        spp = int(os.environ.get("V3_SPP", 300))
        render_still(scene, hero, STILL_PATH, samples=spp)
        if os.environ.get("V3_ALL"):
            render_still(scene, cam_b, STILL_B_PATH, samples=spp)
            render_still(scene, overview, OVERVIEW_PATH, samples=spp)
        print("[v3k3] still-only; skip video")
        return

    render_still(scene, hero, STILL_PATH, samples=560)
    render_still(scene, cam_b, STILL_B_PATH, samples=480)
    render_still(scene, overview, OVERVIEW_PATH, samples=420)
    dolly = build_dolly(target_a, target_b)
    render_video(scene, dolly)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3k3] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
