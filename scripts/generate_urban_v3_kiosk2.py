"""Photorealistic procedural street-kiosk scene v2 (urban_v3_kiosk2).

A ground-up realism rewrite of urban_v3_kiosk.  The v1 read as a low-poly
cartoon because materials were flat solid colours, lighting was flat, the
backdrop was cartoon blobs and geometry was toy-simple.  This version chases
photographic realism the way a lookdev artist would:

  * REAL environment lighting — a bundled Blender city/courtyard HDRI drives
    image-based lighting AND the reflections you see in glass & metal; plus a
    sun for a crisp key shadow.  The HDRI also fills the out-of-focus backdrop
    so there are no cartoon buildings.
  * TEXTURED PBR — every material is a node graph: noise-driven roughness
    breakup, fine bump, Pointiness edge-wear to bare metal, and AO cavity dirt.
    That micro-variation is what separates "render" from "CG plastic".
  * PRINTED CONTENT — magazine covers, newspapers, posters and the fascia sign
    are numpy-generated image textures, so the newsstand reads as real print.
  * DENSE GEOMETRY — tiered slanted magazine racks, a glass drinks fridge with
    bottles + interior light, hanging snack strips, standing-seam roof, awning
    with support arms, bolts, kickplates and price rails.
  * WET, REFLECTIVE PAVEMENT + cinematic 35mm DoF, AgX grade, subtle glare.

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_kiosk2.py
Env:
  V3_STILL_ONLY=1   still only (fast look-dev)
  K_ENV=city|courtyard|sunset|sunrise   pick the HDRI (default city)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk2):
  kiosk.blend  kiosk.png  kiosk.mp4
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

import bpy
import numpy as np
from mathutils import Vector

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk2")
SCENE_PATH = OUTPUT_DIR / "kiosk.blend"
STILL_PATH = OUTPUT_DIR / "kiosk.png"
VIDEO_PATH = OUTPUT_DIR / "kiosk.mp4"

BLENDER_ROOT = Path(f"{_wb_BLENDER_RESOURCES}")
HDRI_DIR = BLENDER_ROOT / "datafiles/studiolights/world"


# --------------------------------------------------------------------------- #
# Scene bookkeeping
# --------------------------------------------------------------------------- #
def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.images,
        bpy.data.lights,
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
# Node-graph material toolkit  (this is where the realism lives)
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

    # --- roughness breakup ------------------------------------------------ #
    nr = nt.nodes.new("ShaderNodeTexNoise")
    nr.inputs["Scale"].default_value = rough_scale
    nr.inputs["Detail"].default_value = 3.0
    lo, hi = max(0.0, base_rough - rough_var), min(1.0, base_rough + rough_var)
    cr = _ramp(nt, [(0.0, (lo, lo, lo)), (1.0, (hi, hi, hi))])
    nt.links.new(nr.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Roughness"])

    # --- fine surface bump ------------------------------------------------ #
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

    # --- base colour: subtle tonal noise -> edge wear -> cavity dirt ------ #
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


def mat_wood(name, color=(0.26, 0.15, 0.07), rough=0.42):
    m, nt, b = _principled(name)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.inputs["Scale"].default_value = 3.5
    w.inputs["Distortion"].default_value = 12.0
    w.inputs["Detail"].default_value = 2.0
    dark = (color[0] * 0.6, color[1] * 0.6, color[2] * 0.6)
    light = tuple(min(1.0, x * 1.35) for x in color)
    cc = _ramp(nt, [(0.0, dark), (1.0, light)])
    nt.links.new(w.outputs["Fac"], cc.inputs["Fac"])
    nt.links.new(cc.outputs["Color"], b.inputs["Base Color"])
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.25
    nt.links.new(w.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", rough)
    _set(b, ("Coat Weight", "Coat"), 0.15)
    return m


def mat_glass(name, tint=(0.85, 0.90, 0.90), rough=0.02):
    m, nt, b = _principled(name)
    _set(b, "Base Color", (tint[0], tint[1], tint[2], 1.0))
    _set(b, ("Transmission Weight", "Transmission"), 1.0)
    _set(b, "IOR", 1.5)
    _set(b, "Metallic", 0.0)
    # smudge roughness
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    cr = _ramp(
        nt,
        [
            (0.0, (rough, rough, rough)),
            (1.0, (rough + 0.05, rough + 0.05, rough + 0.05)),
        ],
    )
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


def mat_image(name, img, rough=0.32, emit=0.0):
    """Glossy printed material driven by a numpy image texture."""
    m, nt, b = _principled(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Cubic"
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", rough)
    _set(b, ("Coat Weight", "Coat"), 0.25)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.05
    nt.links.new(tex.outputs["Color"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    if emit > 0.0:
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        _set(b, "Emission Strength", emit)
    return m


# --------------------------------------------------------------------------- #
# numpy printed-content textures
# --------------------------------------------------------------------------- #
_IMG_SEED = np.random.RandomState(7)


def _new_image(name, arr):
    """arr: HxWx3 float 0..1 -> a Blender image (sRGB)."""
    h, w, _ = arr.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(arr, 0, 1)
    img = bpy.data.images.new(name, width=w, height=h)
    # Blender expects bottom-up row order
    img.pixels.foreach_set(rgba[::-1].reshape(-1))
    img.pack()
    return img


def _rand_color(rng, sat=0.8, val=0.95):
    import colorsys

    h = rng.rand()
    r, g, b = colorsys.hsv_to_rgb(
        h, sat * (0.6 + 0.4 * rng.rand()), val * (0.7 + 0.3 * rng.rand())
    )
    return np.array([r, g, b])


_SKIN = [
    np.array(c)
    for c in [
        (0.86, 0.66, 0.53),
        (0.72, 0.52, 0.40),
        (0.55, 0.38, 0.28),
        (0.92, 0.76, 0.66),
    ]
]


def make_cover(name, rng, w=96, h=136):
    """A magazine cover that reads as a photo: studio-lit portrait subject
    (head + shoulders) over a coloured seamless backdrop, masthead + coverlines."""
    yy, xx = np.ogrid[:h, :w]
    a = np.ones((h, w, 3), dtype=np.float32)
    # seamless studio backdrop: single hue, soft top-lit vertical falloff
    bg = _rand_color(rng, sat=0.55, val=0.85)
    for y in range(h):
        t = y / h
        a[y, :, :] = bg * (1.05 - 0.5 * t)
    # ---- portrait subject: shoulders (trapezoid) + head (ellipse) + hair ----
    skin = _SKIN[rng.randint(len(_SKIN))]
    cloth = _rand_color(rng, sat=0.6, val=0.55)
    cx = w // 2 + rng.randint(-6, 7)
    # shoulders / torso occupying lower half
    sh_top = int(h * 0.62)
    for y in range(sh_top, h):
        t = (y - sh_top) / max(1, h - sh_top)
        half = int((0.20 + 0.34 * t) * w)
        a[y, max(0, cx - half) : min(w, cx + half), :] = cloth * (0.85 + 0.3 * (1 - t))
    # neck
    a[int(h * 0.52) : sh_top + 2, cx - 6 : cx + 6, :] = skin * 0.9
    # head (ellipse)
    hcy, hrx, hry = int(h * 0.40), int(w * 0.15), int(h * 0.15)
    head = ((yy - hcy) / hry) ** 2 + ((xx - cx) / hrx) ** 2 < 1.0
    a[head] = skin
    # simple shading on the face (light from upper-left)
    shade = np.clip(
        1.05
        - 0.5 * ((xx - (cx - hrx)) / (2 * hrx))
        - 0.3 * ((yy - (hcy - hry)) / (2 * hry)),
        0.6,
        1.15,
    )
    a[head] = np.clip(a[head] * shade[head][:, None], 0, 1)
    # hair cap over the top third of the head
    hair = _rand_color(rng, sat=0.4, val=0.3)
    cap = (((yy - hcy) / hry) ** 2 + ((xx - cx) / hrx) ** 2 < 1.0) & (
        yy < hcy - hry // 4
    )
    a[cap] = hair
    # ---- masthead (top) ----
    mh = rng.randint(15, 22)
    title = (
        np.clip(bg * 0.15 + 0.9, 0, 1)
        if rng.rand() > 0.5
        else np.array([0.08, 0.08, 0.09])
    )
    a[3:mh, 5 : w - 5, :] = title
    # ---- coverlines down the right edge ----
    for i in range(rng.randint(4, 7)):
        yy0 = mh + 8 + i * int((h - mh - 16) / 7)
        ln = rng.randint(w // 4, w // 2)
        col = (
            0.06 + 0.05 * rng.rand(3)
            if rng.rand() > 0.4
            else _rand_color(rng, sat=0.9, val=0.95)
        )
        a[yy0 : yy0 + 3, w - 6 - ln : w - 6, :] = col
    return _new_image(name, np.clip(a, 0, 1))


def make_newspaper(name, rng, w=110, h=140):
    a = np.ones((h, w, 3), dtype=np.float32) * (0.86 + 0.05 * rng.rand())
    a[:, :, :] *= np.array([1.0, 0.99, 0.95])  # newsprint cream
    # masthead
    a[6:20, 6 : w - 6, :] = 0.12
    a[9:17, 10 : w - 10, :] = 0.9
    # a photo block
    py, px = rng.randint(26, 40), rng.randint(8, 20)
    ph, pw = rng.randint(28, 40), rng.randint(40, 60)
    a[py : py + ph, px : px + pw, :] = _rand_color(rng, sat=0.3, val=0.6)
    # columns of grey text lines
    for col_x in range(8, w - 8, 26):
        for ly in range(py + ph + 6, h - 6, 5):
            a[ly : ly + 2, col_x : col_x + 22, :] = 0.25 + 0.1 * rng.rand()
    return _new_image(name, a)


def make_poster(name, rng, w=128, h=160, hue=None):
    import colorsys

    a = np.ones((h, w, 3), dtype=np.float32)
    if hue is None:
        hue = rng.rand()
    c1 = np.array(colorsys.hsv_to_rgb(hue, 0.8, 0.95))
    c2 = np.array(colorsys.hsv_to_rgb((hue + 0.12) % 1, 0.9, 0.5))
    for y in range(h):
        t = y / h
        a[y, :, :] = c1 * (1 - t) + c2 * t
    # big circle
    cy, cx, rad = h // 2, w // 2, min(h, w) // 4
    yy, xx = np.ogrid[:h, :w]
    a[(yy - cy) ** 2 + (xx - cx) ** 2 < rad**2] = np.clip(c1 * 0.2 + 0.8, 0, 1)
    # headline + text bars
    a[10:26, 12 : w - 12, :] = 0.08
    for i in range(4):
        yy2 = h - 40 + i * 8
        a[yy2 : yy2 + 4, 16 : w - 16 - i * 6, :] = 0.95
    return _new_image(name, a)


def make_sign(name, text_rgb=(0.95, 0.9, 0.4), bg=(0.03, 0.14, 0.09), w=256, h=48):
    """Fascia signboard: coloured plate with lighter 'lettering' blocks."""
    a = np.ones((h, w, 3), dtype=np.float32) * np.array(bg)
    x = 14
    rng = _IMG_SEED
    for _ in range(3):  # three "words"
        wlen = rng.randint(40, 70)
        for _ in range(rng.randint(4, 7)):  # letters as blocks
            lw = rng.randint(5, 9)
            if x + lw > w - 14:
                break
            a[12 : h - 12, x : x + lw, :] = np.array(text_rgb)
            x += lw + 4
        x += 16
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


def plane_img(name, loc, size, mat, coll, rot=(0, 0, 0)):
    """A thin textured card (for covers/posters). size=(w,h)."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = (size[0], size[1], 0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    return link_to(o, coll)


def cyl(name, loc, r, depth, mat, coll, verts=32, axis="Z", rot=None):
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


def cyl_between(name, a, b, r, mat, coll, verts=24):
    a, b = Vector(a), Vector(b)
    d = b - a
    o = None
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


# --------------------------------------------------------------------------- #
# Materials registry
# --------------------------------------------------------------------------- #
M = {}


def build_materials():
    M["kiosk_green"] = mat_surface(
        "k2_green",
        (0.012, 0.07, 0.04),
        base_rough=0.4,
        rough_var=0.12,
        bump=0.16,
        wear=0.09,
        wear_color=(0.04, 0.1, 0.07),
        dirt=0.22,
        coat=0.16,
    )
    M["kiosk_green_dark"] = mat_surface(
        "k2_green_dark",
        (0.008, 0.03, 0.02),
        base_rough=0.45,
        wear=0.1,
        wear_color=(0.03, 0.06, 0.04),
        dirt=0.3,
    )
    M["kiosk_cream"] = mat_surface(
        "k2_cream",
        (0.5, 0.47, 0.4),
        base_rough=0.5,
        rough_var=0.1,
        wear=0.14,
        wear_color=(0.3, 0.29, 0.27),
        dirt=0.3,
        coat=0.1,
    )
    M["kiosk_red"] = mat_surface(
        "k2_red", (0.28, 0.02, 0.02), base_rough=0.44, wear=0.16, dirt=0.3, coat=0.12
    )
    M["steel"] = mat_surface(
        "k2_steel",
        (0.28, 0.29, 0.31),
        metallic=1.0,
        base_rough=0.34,
        rough_var=0.12,
        bump=0.1,
        bump_scale=140,
        wear=0.25,
        wear_color=(0.55, 0.56, 0.58),
        dirt=0.3,
        anisotropy=0.4,
        wave_scratch=True,
    )
    M["steel_dark"] = mat_surface(
        "k2_steel_dark",
        (0.05, 0.052, 0.055),
        metallic=1.0,
        base_rough=0.4,
        bump=0.12,
        wear=0.2,
        wear_color=(0.3, 0.3, 0.32),
        dirt=0.35,
    )
    M["stainless"] = mat_surface(
        "k2_stainless",
        (0.55, 0.56, 0.58),
        metallic=1.0,
        base_rough=0.24,
        rough_var=0.08,
        bump=0.06,
        bump_scale=200,
        anisotropy=0.5,
        wave_scratch=True,
        wear=0.1,
        dirt=0.15,
    )
    M["brass"] = mat_surface(
        "k2_brass",
        (0.62, 0.45, 0.14),
        metallic=1.0,
        base_rough=0.32,
        wear=0.15,
        dirt=0.25,
    )
    M["wood"] = mat_wood("k2_wood", (0.24, 0.14, 0.07))
    M["wood_light"] = mat_wood("k2_wood_light", (0.42, 0.27, 0.13), rough=0.4)
    M["counter_stone"] = mat_surface(
        "k2_stone",
        (0.14, 0.14, 0.15),
        base_rough=0.28,
        rough_var=0.1,
        bump=0.08,
        bump_scale=40,
        dirt=0.2,
        coat=0.2,
        specular=0.6,
    )
    M["glass"] = mat_glass("k2_glass")
    M["glass_fridge"] = mat_glass(
        "k2_glass_fridge", tint=(0.9, 0.95, 0.95), rough=0.015
    )
    M["awning_green"] = mat_surface(
        "k2_awn_green",
        (0.02, 0.09, 0.055),
        base_rough=0.62,
        rough_var=0.08,
        bump=0.35,
        bump_scale=220,
        dirt=0.3,
    )
    M["awning_cream"] = mat_surface(
        "k2_awn_cream",
        (0.62, 0.58, 0.5),
        base_rough=0.62,
        bump=0.35,
        bump_scale=220,
        dirt=0.28,
    )
    M["awning_red"] = mat_surface(
        "k2_awn_red",
        (0.3, 0.03, 0.03),
        base_rough=0.62,
        bump=0.35,
        bump_scale=220,
        dirt=0.3,
    )
    M["roof_metal"] = mat_surface(
        "k2_roof",
        (0.1, 0.11, 0.12),
        metallic=1.0,
        base_rough=0.42,
        rough_var=0.14,
        bump=0.18,
        bump_scale=60,
        wear=0.2,
        dirt=0.4,
    )
    M["concrete"] = mat_surface(
        "k2_concrete",
        (0.135, 0.132, 0.125),
        base_rough=0.68,
        rough_var=0.24,
        rough_scale=3.2,
        bump=0.28,
        bump_scale=18,
        dirt=0.5,
        ao_dist=0.5,
    )
    M["grout"] = mat_surface(
        "k2_grout",
        (0.045, 0.045, 0.042),
        base_rough=0.85,
        dirt=0.4,
        bump=0.1,
        bump_scale=30,
    )
    M["asphalt"] = mat_surface(
        "k2_asphalt",
        (0.028, 0.028, 0.03),
        base_rough=0.32,
        rough_var=0.22,
        rough_scale=4.0,
        bump=0.15,
        bump_scale=25,
        dirt=0.25,
        specular=0.55,
    )
    M["curb"] = mat_surface(
        "k2_curb",
        (0.22, 0.213, 0.2),
        base_rough=0.6,
        dirt=0.45,
        bump=0.14,
        bump_scale=40,
    )
    M["rubber"] = mat_surface(
        "k2_rubber", (0.03, 0.03, 0.035), base_rough=0.6, dirt=0.2
    )
    M["plastic_crate"] = mat_surface(
        "k2_crate", (0.55, 0.12, 0.08), base_rough=0.45, dirt=0.2
    )
    M["leaf"] = mat_surface(
        "k2_leaf", (0.05, 0.16, 0.05), base_rough=0.7, bump=0.3, bump_scale=50
    )

    # emissive
    M["fridge_light"] = mat_emit("k2_fridge_light", (1.0, 0.98, 0.92), 11.0)
    M["interior_light"] = mat_emit("k2_interior_light", (1.0, 0.95, 0.85), 5.0)
    M["sign_neon"] = mat_emit("k2_neon", (1.0, 0.35, 0.12), 6.0)

    # printed content
    rng = _IMG_SEED
    M["covers"] = [
        mat_image(f"k2_cover_{i}", make_cover(f"cover_{i}", rng), rough=0.28)
        for i in range(14)
    ]
    M["papers"] = [
        mat_image(f"k2_paper_{i}", make_newspaper(f"paper_{i}", rng), rough=0.5)
        for i in range(5)
    ]
    M["posters"] = [
        mat_image(f"k2_poster_{i}", make_poster(f"poster_{i}", rng), rough=0.3)
        for i in range(5)
    ]
    M["snacks"] = [
        mat_image(
            f"k2_snack_{i}", make_poster(f"snack_{i}", rng, w=64, h=90), rough=0.2
        )
        for i in range(6)
    ]
    M["sign_press"] = mat_image(
        "k2_sign_press",
        make_sign("sign_press", (0.95, 0.9, 0.4), (0.02, 0.12, 0.08)),
        rough=0.35,
        emit=2.2,
    )
    M["sign_cafe"] = mat_image(
        "k2_sign_cafe",
        make_sign("sign_cafe", (0.98, 0.95, 0.9), (0.3, 0.03, 0.03)),
        rough=0.35,
        emit=2.4,
    )
    M["menu"] = mat_image(
        "k2_menu",
        make_poster("menu_img", rng, w=140, h=90, hue=0.08),
        rough=0.4,
        emit=1.6,
    )


# --------------------------------------------------------------------------- #
# Reusable sub-assemblies
# --------------------------------------------------------------------------- #
def bolt(name, loc, coll, r=0.012, d=0.01, axis="Y"):
    return cyl(name, loc, r, d, M["steel_dark"], coll, verts=8, axis=axis)


def magazine_rack(prefix, cx, front_y, base_z, width, coll, rows=4, cols=6, mats=None):
    """Tiered shelves of individually slanted, printed magazines facing -Y."""
    mats = mats or M["covers"]
    cw = width / cols
    slant = math.radians(-58)  # near-vertical, tipped back
    for r in range(rows):
        z = base_z + r * 0.34
        y = front_y + 0.02 + r * 0.05  # upper rows recede slightly
        # shelf ledge
        cube(
            f"{prefix}:ledge:{r}",
            (cx, y + 0.09, z - 0.16),
            (width + 0.05, 0.18, 0.02),
            M["steel_dark"],
            coll,
            bevel=0.004,
        )
        cube(
            f"{prefix}:lip:{r}",
            (cx, y - 0.06, z - 0.10),
            (width + 0.05, 0.02, 0.05),
            M["steel"],
            coll,
            bevel=0.003,
        )
        for c in range(cols):
            x = cx - width / 2 + cw * (c + 0.5)
            mat = mats[(r * cols + c) % len(mats)]
            plane_img(
                f"{prefix}:mag:{r}:{c}",
                (x, y, z),
                (cw - 0.015, 0.30),
                mat,
                coll,
                rot=(slant, 0, 0),
            )
        # price rail
        cube(
            f"{prefix}:price:{r}",
            (cx, y - 0.09, z - 0.13),
            (width + 0.05, 0.006, 0.02),
            M["stainless"],
            coll,
            bevel=0,
        )


def snack_strip(prefix, cx, y, top_z, width, coll, n=7):
    cyl_between(
        f"{prefix}:wire",
        (cx - width / 2, y, top_z),
        (cx + width / 2, y, top_z),
        0.005,
        M["stainless"],
        coll,
        verts=8,
    )
    cw = width / n
    for i in range(n):
        x = cx - width / 2 + cw * (i + 0.5)
        mat = M["snacks"][i % len(M["snacks"])]
        plane_img(
            f"{prefix}:snack:{i}",
            (x, y, top_z - 0.16),
            (cw - 0.02, 0.22),
            mat,
            coll,
            rot=(math.radians(-90), 0, 0),
        )


def steel_frame(prefix, cx, cy, w, d, h, coll, t=0.04):
    """Visible angle-steel skeleton around a box footprint."""
    z0, z1 = 0.02, h
    xs = (cx - w / 2, cx + w / 2)
    ys = (cy - d / 2, cy + d / 2)
    for x in xs:
        for y in ys:
            cyl_between(
                f"{prefix}:col:{x:.2f}:{y:.2f}",
                (x, y, z0),
                (x, y, z1),
                t,
                M["steel_dark"],
                coll,
                verts=10,
            )
    for x in xs:
        for y in ys:
            pass
    # top rails
    for y in ys:
        cyl_between(
            f"{prefix}:rt_x:{y:.2f}",
            (xs[0], y, z1),
            (xs[1], y, z1),
            t,
            M["steel_dark"],
            coll,
            verts=10,
        )
    for x in xs:
        cyl_between(
            f"{prefix}:rt_y:{x:.2f}",
            (x, ys[0], z1),
            (x, ys[1], z1),
            t,
            M["steel_dark"],
            coll,
            verts=10,
        )


def striped_awning(prefix, cx, front_y, top_z, width, coll, mats, depth=1.0, drop=0.28):
    """Sloped striped awning with a sagging valance + steel support arms."""
    pitch = math.radians(24)
    n = max(14, int(round(width / 0.22)))
    sw = width / n
    cy = front_y - depth / 2
    for i in range(n):
        x = cx - width / 2 + sw * (i + 0.5)
        mat = M[mats[i % len(mats)]]
        cube(
            f"{prefix}:awn:{i}",
            (x, cy, top_z - 0.05),
            (sw + 0.004, depth, 0.04),
            mat,
            coll,
            rot=(pitch, 0, 0),
            bevel=0,
        )
    fy = front_y - depth + 0.03
    fz = top_z - depth * math.sin(pitch) - 0.02
    for i in range(n):
        x = cx - width / 2 + sw * (i + 0.5)
        mat = M[mats[i % len(mats)]]
        # scalloped valance: alternate slightly longer drops
        dd = drop + (0.05 if i % 2 == 0 else 0.0)
        cube(
            f"{prefix}:val:{i}",
            (x, fy, fz - dd / 2),
            (sw + 0.004, 0.015, dd),
            mat,
            coll,
            bevel=0,
        )
    cyl_between(
        f"{prefix}:bar",
        (cx - width / 2, fy, fz),
        (cx + width / 2, fy, fz),
        0.018,
        M["steel_dark"],
        coll,
        verts=12,
    )
    for s in (-1, 1):
        ax = cx + s * (width / 2 - 0.1)
        cyl_between(
            f"{prefix}:arm:{s}",
            (ax, front_y - 0.02, top_z - 0.02),
            (ax, fy, fz),
            0.016,
            M["steel_dark"],
            coll,
            verts=10,
        )


# --------------------------------------------------------------------------- #
# Kiosk A — HERO detailed newsstand (classic green)
# --------------------------------------------------------------------------- #
def front_mag_rack(prefix, cx, front_y, base_z, width, coll, rows=3, cols=8, mats=None):
    """A near-upright magazine bank facing the street (-Y), tiered slightly."""
    mats = mats or M["covers"]
    cw = width / cols
    tilt = math.radians(-72)  # nearly vertical, top tipped back
    for r in range(rows):
        z = base_z + r * 0.34
        y = front_y + r * 0.06  # upper rows lean back
        cube(
            f"{prefix}:shelf:{r}",
            (cx, y + 0.11, z - 0.17),
            (width + 0.06, 0.2, 0.02),
            M["steel_dark"],
            coll,
            bevel=0.004,
        )
        cube(
            f"{prefix}:lip:{r}",
            (cx, y - 0.05, z - 0.12),
            (width + 0.06, 0.02, 0.04),
            M["stainless"],
            coll,
            bevel=0.003,
        )
        for c in range(cols):
            x = cx - width / 2 + cw * (c + 0.5)
            mat = mats[(r * cols + c + r) % len(mats)]
            plane_img(
                f"{prefix}:mag:{r}:{c}",
                (x, y, z),
                (cw - 0.012, 0.31),
                mat,
                coll,
                rot=(tilt, 0, 0),
            )


def kiosk_newsstand(coll, cx):
    w, d, h = 2.9, 1.55, 2.35
    fy = -d / 2
    # plinth / kickbase
    cube(
        "A:plinth",
        (cx, 0.02, 0.07),
        (w + 0.12, d + 0.12, 0.14),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:kick",
        (cx, fy - 0.01, 0.17),
        (w + 0.02, 0.03, 0.14),
        M["steel_dark"],
        coll,
        bevel=0.004,
    )
    # cabinet: back + sides + open front bay
    cube(
        "A:back",
        (cx, d / 2 - 0.02, h / 2 + 0.14),
        (w, 0.06, h),
        M["kiosk_green"],
        coll,
        bevel=0.01,
    )
    for s in (-1, 1):
        cube(
            f"A:side:{s}",
            (cx + s * (w / 2 - 0.03), 0.05, h / 2 + 0.14),
            (0.06, d - 0.1, h),
            M["kiosk_green"],
            coll,
            bevel=0.01,
        )
    # lit interior shell behind the display
    cube(
        "A:interior",
        (cx, 0.22, 1.55),
        (w - 0.22, d - 0.3, 1.6),
        M["kiosk_green_dark"],
        coll,
        bevel=0,
    )
    cube(
        "A:ceil_glow",
        (cx, 0.3, 2.28),
        (w - 0.5, d - 0.55, 0.03),
        M["interior_light"],
        coll,
        bevel=0,
    )
    # front steel posts + head rail framing the bay
    for s in (-1, 1):
        x = cx + s * (w / 2 - 0.02)
        cyl_between(
            f"A:fcol:{s}",
            (x, fy, 0.02),
            (x, fy, h + 0.14),
            0.036,
            M["steel_dark"],
            coll,
            verts=12,
        )
    cyl_between(
        "A:ftop",
        (cx - w / 2, fy, h + 0.14),
        (cx + w / 2, fy, h + 0.14),
        0.036,
        M["steel_dark"],
        coll,
        verts=12,
    )
    # serving counter: stone top + green apron
    cube(
        "A:apron",
        (cx, fy + 0.02, 0.6),
        (w - 0.14, 0.42, 0.78),
        M["kiosk_green"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:counter",
        (cx, fy - 0.06, 1.02),
        (w - 0.04, 0.58, 0.06),
        M["counter_stone"],
        coll,
        bevel=0.006,
    )
    # HERO: magazine bank facing the street (left ~65% of the bay)
    front_mag_rack("A_front", cx - 0.55, fy + 0.12, 1.34, 1.75, coll, rows=3, cols=6)
    # upright newspaper rack standing on the counter, facing out
    for i, dx in enumerate(np.linspace(-1.4, -0.2, 5)):
        plane_img(
            f"A:paper:{i}",
            (cx + dx, fy - 0.12, 1.24),
            (0.24, 0.36),
            M["papers"][i % len(M["papers"])],
            coll,
            rot=(math.radians(-80), 0, math.radians((i - 2) * 3)),
        )
    # hanging snack strip along the head of the bay
    snack_strip("A_snacks", cx - 0.55, fy - 0.02, 2.16, 1.7, coll, n=7)
    # open lit drinks cooler on the front-right: colourful bottles on shelves
    frx = cx + w / 2 - 0.5
    drink_cols = [
        mat_surface(
            "k2_dr_red", (0.6, 0.04, 0.05), base_rough=0.28, dirt=0.05, coat=0.3
        ),
        mat_surface(
            "k2_dr_blue", (0.03, 0.16, 0.6), base_rough=0.28, dirt=0.05, coat=0.3
        ),
        mat_surface(
            "k2_dr_green", (0.05, 0.42, 0.12), base_rough=0.28, dirt=0.05, coat=0.3
        ),
        mat_surface(
            "k2_dr_orange", (0.75, 0.32, 0.02), base_rough=0.28, dirt=0.05, coat=0.3
        ),
        mat_surface(
            "k2_dr_white", (0.7, 0.72, 0.75), base_rough=0.28, dirt=0.05, coat=0.3
        ),
    ]
    # shallow recessed cabinet with a bright lit back panel
    cube(
        "A:cooler_box",
        (frx, 0.28, 0.9),
        (0.9, 0.5, 1.55),
        M["kiosk_green_dark"],
        coll,
        bevel=0.012,
    )
    cube(
        "A:cooler_back",
        (frx, 0.5, 0.9),
        (0.82, 0.02, 1.42),
        M["fridge_light"],
        coll,
        bevel=0,
    )
    for r in range(4):
        z = 0.36 + r * 0.34
        cube(
            f"A:cooler_shelf:{r}",
            (frx, 0.28, z - 0.17),
            (0.84, 0.44, 0.02),
            M["stainless"],
            coll,
            bevel=0.002,
        )
        for c in range(5):
            bx = frx - 0.32 + c * 0.16
            col = drink_cols[(r + c) % len(drink_cols)]
            cyl(
                f"A:bottle:{r}:{c}",
                (bx, fy + 0.34, z + 0.02),
                0.036,
                0.2,
                col,
                coll,
                verts=14,
            )
            cyl(
                f"A:bneck:{r}:{c}",
                (bx, fy + 0.34, z + 0.16),
                0.015,
                0.05,
                col,
                coll,
                verts=10,
            )
    cube(
        "A:cooler_header",
        (frx, fy + 0.06, 1.68),
        (0.9, 0.12, 0.2),
        M["kiosk_red"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:cooler_headlight",
        (frx, fy + 0.02, 1.55),
        (0.8, 0.04, 0.04),
        M["fridge_light"],
        coll,
        bevel=0,
    )
    # roof: standing-seam metal overhang + fascia signboard
    cube(
        "A:roof",
        (cx, 0.02, h + 0.24),
        (w + 0.34, d + 0.55, 0.1),
        M["roof_metal"],
        coll,
        bevel=0.02,
    )
    for i, sx in enumerate(np.linspace(-w / 2, w / 2, 8)):
        cube(
            f"A:seam:{i}",
            (cx + sx, 0.02, h + 0.30),
            (0.03, d + 0.55, 0.03),
            M["roof_metal"],
            coll,
            bevel=0.006,
        )
    cube(
        "A:fascia",
        (cx, fy - 0.28, h + 0.38),
        (w + 0.26, 0.09, 0.32),
        M["kiosk_green_dark"],
        coll,
        bevel=0.01,
    )
    plane_img(
        "A:sign",
        (cx, fy - 0.335, h + 0.38),
        (w + 0.02, 0.26),
        M["sign_press"],
        coll,
        rot=(math.radians(90), 0, 0),
    )
    for s in (-1, 1):
        cube(
            f"A:signcap:{s}",
            (cx + s * (w / 2 + 0.08), fy - 0.28, h + 0.38),
            (0.05, 0.1, 0.34),
            M["steel_dark"],
            coll,
            bevel=0.006,
        )
        bolt(f"A:bolt:{s}:0", (cx + s * (w / 2 - 0.04), fy - 0.235, h + 0.49), coll)
        bolt(f"A:bolt:{s}:1", (cx + s * (w / 2 - 0.04), fy - 0.235, h + 0.27), coll)
    # slim top-valance awning above the display (does not cover the goods)
    striped_awning(
        "A",
        cx,
        fy - 0.12,
        h + 0.16,
        w + 0.12,
        coll,
        ["awning_green", "awning_cream"],
        depth=0.6,
        drop=0.2,
    )
    # sidewalk A-board + a paper crate for foreground life
    cube(
        "A:crate",
        (cx - w / 2 - 0.5, fy - 0.45, 0.2),
        (0.44, 0.34, 0.3),
        M["plastic_crate"],
        coll,
        bevel=0.01,
    )
    for i in range(4):
        plane_img(
            f"A:crate_mag:{i}",
            (cx - w / 2 - 0.5, fy - 0.45 - i * 0.02, 0.37 + i * 0.005),
            (0.38, 0.28),
            M["covers"][(i + 6) % len(M["covers"])],
            coll,
            rot=(math.radians(12), 0, 0),
        )


# --------------------------------------------------------------------------- #
# Kiosk B — CAFE food kiosk (secondary, adds depth) — reuses toolkit
# --------------------------------------------------------------------------- #
def kiosk_cafe(coll, cx):
    w, d, h = 2.4, 1.7, 2.3
    fy = -d / 2
    cube(
        "B:plinth",
        (cx, 0.02, 0.07),
        (w + 0.12, d + 0.12, 0.14),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    cube(
        "B:body",
        (cx, 0.05, 1.1 + 0.14),
        (w, d - 0.1, 1.95),
        M["kiosk_cream"],
        coll,
        bevel=0.012,
    )
    cube(
        "B:band",
        (cx, 0.05, h + 0.02),
        (w + 0.03, d - 0.06, 0.42),
        M["kiosk_red"],
        coll,
        bevel=0.012,
    )
    # serving window recess + glow + rolled stainless shutter
    cube(
        "B:win_recess",
        (cx, 0.22, 1.72),
        (w - 0.36, 0.06, 0.86),
        M["kiosk_green_dark"],
        coll,
        bevel=0,
    )
    cube(
        "B:win_glow",
        (cx, 0.3, 2.0),
        (w - 0.6, 0.03, 0.1),
        M["interior_light"],
        coll,
        bevel=0,
    )
    cyl(
        f"B:shutter",
        (cx, fy + 0.12, 2.22),
        0.1,
        w - 0.2,
        M["stainless"],
        coll,
        verts=24,
        axis="X",
    )
    # wood serving counter + coffee rig + cups + pastry case
    cube(
        "B:counter",
        (cx, fy - 0.12, 1.06),
        (w - 0.06, 0.5, 0.1),
        M["wood_light"],
        coll,
        bevel=0.01,
    )
    cube(
        "B:counter_apron",
        (cx, fy - 0.34, 0.6),
        (w - 0.06, 0.05, 0.86),
        M["wood"],
        coll,
        bevel=0.008,
    )
    cube(
        "B:coffee",
        (cx - 0.62, 0.12, 1.34),
        (0.46, 0.4, 0.46),
        M["steel_dark"],
        coll,
        bevel=0.015,
    )
    cyl("B:grinder", (cx - 0.3, 0.12, 1.34), 0.08, 0.32, M["stainless"], coll, verts=20)
    for i, dx in enumerate((0.15, 0.26, 0.37)):
        cyl(
            f"B:cup:{i}",
            (cx + dx, fy + 0.0, 1.15),
            0.028,
            0.085,
            M["kiosk_cream"],
            coll,
            verts=14,
        )
    cube(
        "B:case",
        (cx + 0.72, fy - 0.05, 1.24),
        (0.66, 0.42, 0.26),
        M["glass"],
        coll,
        bevel=0.006,
    )
    for i in range(4):
        plane_img(
            f"B:pastry:{i}",
            (cx + 0.55 + i * 0.12, fy - 0.05, 1.13),
            (0.09, 0.3),
            M["snacks"][i % len(M["snacks"])],
            coll,
            rot=(math.radians(-90), 0, 0),
        )
    # roof + illuminated CAFE sign
    cube(
        "B:roof",
        (cx, 0.02, h + 0.3),
        (w + 0.28, d + 0.4, 0.1),
        M["roof_metal"],
        coll,
        bevel=0.02,
    )
    cube(
        "B:signbox",
        (cx, fy - 0.16, h + 0.26),
        (1.5, 0.1, 0.34),
        M["kiosk_red"],
        coll,
        bevel=0.01,
    )
    plane_img(
        "B:sign",
        (cx, fy - 0.215, h + 0.26),
        (1.4, 0.26),
        M["sign_cafe"],
        coll,
        rot=(math.radians(90), 0, 0),
    )
    plane_img(
        "B:menu",
        (cx, fy + 0.02, 2.02),
        (w - 0.6, 0.42),
        M["menu"],
        coll,
        rot=(math.radians(90), 0, 0),
    )
    striped_awning(
        "B",
        cx,
        fy - 0.02,
        h - 0.06,
        w + 0.08,
        coll,
        ["awning_red", "awning_cream"],
        depth=0.95,
    )


# --------------------------------------------------------------------------- #
# Kiosk C — flower/produce stall (distant, DoF-blurred variety)
# --------------------------------------------------------------------------- #
def kiosk_flower(coll, cx):
    w, d, h = 2.2, 1.6, 2.1
    fy = -d / 2
    cube(
        "C:plinth",
        (cx, 0.02, 0.07),
        (w + 0.1, d + 0.1, 0.14),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    cube(
        "C:body",
        (cx, 0.08, h / 2 + 0.14),
        (w, d - 0.14, h),
        M["kiosk_green_dark"],
        coll,
        bevel=0.012,
    )
    cube(
        "C:counter",
        (cx, fy - 0.1, 0.98),
        (w - 0.05, 0.5, 0.1),
        M["wood"],
        coll,
        bevel=0.01,
    )
    # tiered flower buckets (colourful blooms as emissive-ish clusters)
    palette = [
        (0.7, 0.05, 0.1),
        (0.9, 0.5, 0.05),
        (0.85, 0.8, 0.1),
        (0.6, 0.1, 0.5),
        (0.9, 0.9, 0.9),
    ]
    for row, (by, bz) in enumerate(
        [(fy - 0.2, 1.15), (fy + 0.05, 1.3), (fy + 0.3, 1.45)]
    ):
        for i, bx in enumerate(np.linspace(-w / 2 + 0.25, w / 2 - 0.25, 5)):
            cyl(
                f"C:bucket:{row}:{i}",
                (cx + bx, by, bz - 0.14),
                0.08,
                0.24,
                M["steel"],
                coll,
                verts=14,
            )
            col = palette[(row + i) % len(palette)]
            fm = mat_surface(
                f"k2_bloom_{row}_{i}",
                col,
                base_rough=0.6,
                bump=0.4,
                bump_scale=40,
                dirt=0.1,
            )
            for k in range(6):
                a = k * math.tau / 6
                cyl_between(
                    f"C:stem:{row}:{i}:{k}",
                    (cx + bx, by, bz),
                    (cx + bx + math.cos(a) * 0.08, by + math.sin(a) * 0.06, bz + 0.18),
                    0.006,
                    M["leaf"],
                    coll,
                    verts=6,
                )
            for k in range(7):
                a = k * math.tau / 7
                r = 0.09
                import bpy as _b

                _b.ops.mesh.primitive_uv_sphere_add(
                    segments=10,
                    ring_count=6,
                    radius=0.045,
                    location=(
                        cx + bx + math.cos(a) * r,
                        by + math.sin(a) * r * 0.7,
                        bz + 0.2,
                    ),
                )
                o = _b.context.object
                o.name = f"C:bloom:{row}:{i}:{k}"
                o.data.materials.append(fm)
                smooth(o)
                link_to(o, coll)
    cube(
        "C:roof",
        (cx, 0.05, h + 0.2),
        (w + 0.22, d + 0.3, 0.1),
        M["roof_metal"],
        coll,
        bevel=0.02,
    )
    striped_awning(
        "C",
        cx,
        fy - 0.02,
        h + 0.0,
        w + 0.06,
        coll,
        ["awning_green", "awning_cream"],
        depth=0.85,
    )


# --------------------------------------------------------------------------- #
# Ground
# --------------------------------------------------------------------------- #
def ground(coll):
    # wet-ish asphalt road catches reflections
    cube("gnd:road", (0, -6.5, -0.02), (60, 12, 0.04), M["asphalt"], coll, bevel=0)
    # paved sidewalk with slab seams
    cube("gnd:walk", (0, 2.6, 0.0), (60, 8.5, 0.04), M["concrete"], coll, bevel=0)
    for i in range(-24, 25):
        cube(
            f"gnd:seam_x:{i}",
            (i * 1.25, 2.6, 0.021),
            (0.035, 8.5, 0.006),
            M["grout"],
            coll,
            bevel=0,
        )
    for j in range(6):
        cube(
            f"gnd:seam_y:{j}",
            (0, -1.0 + j * 1.25, 0.021),
            (60, 0.035, 0.006),
            M["grout"],
            coll,
            bevel=0,
        )
    # kerb
    cube("gnd:curb", (0, -1.35, 0.09), (60, 0.3, 0.14), M["curb"], coll, bevel=0.012)
    cube("gnd:curb_face", (0, -1.52, 0.05), (60, 0.04, 0.1), M["curb"], coll, bevel=0)


# --------------------------------------------------------------------------- #
# World (HDRI) + sun + camera + render
# --------------------------------------------------------------------------- #
def build_world():
    env_name = os.environ.get("K_ENV", "city")
    path = HDRI_DIR / f"{env_name}.exr"
    if not path.exists():
        path = HDRI_DIR / "city.exr"
    world = bpy.data.worlds.new("k2_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(path))
    mapping = nt.nodes.new("ShaderNodeMapping")
    texco = nt.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value = (0, 0, math.radians(60))
    nt.links.new(texco.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    # split-sky: camera rays see a bright natural backdrop; lighting rays get a
    # much weaker fill so the SUN dominates and casts a real, crisp shadow.
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    bg_cam.inputs["Strength"].default_value = 1.15
    bg_light.inputs["Strength"].default_value = 0.32
    nt.links.new(env.outputs["Color"], bg_cam.inputs["Color"])
    nt.links.new(env.outputs["Color"], bg_light.inputs["Color"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_light.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    print(f"[v3k2] HDRI env: {path.name} (split-sky cam=1.15 light=0.32)")


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 6.5
    sun.data.angle = math.radians(1.4)
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_euler = (math.radians(46), 0, math.radians(-52))


def _focus_empty(name, loc):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    return e


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


def add_cameras(hero_cx):
    target = Vector((hero_cx + 0.1, 0.0, 1.45))
    focus = _focus_empty("cam_focus", target)

    still = bpy.data.cameras.new("cam_still")
    so = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(so)
    still.lens = 40
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 5.0
    still.dof.focus_object = focus
    cam_pos = Vector((hero_cx - 2.6, -6.4, 2.05))
    so.location = cam_pos
    so.rotation_euler = (target - cam_pos).to_track_quat("-Z", "Y").to_euler()

    orbit = bpy.data.cameras.new("cam_dolly")
    oo = bpy.data.objects.new("cam_dolly", orbit)
    bpy.context.scene.collection.objects.link(oo)
    orbit.lens = 40
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 3.5
    orbit.dof.focus_object = focus
    keys = [
        (1, Vector((hero_cx - 3.6, -4.2, 1.5)), Vector((hero_cx - 0.6, -0.1, 1.35))),
        (48, Vector((hero_cx + 0.2, -5.0, 1.75)), Vector((hero_cx + 0.2, -0.1, 1.45))),
        (96, Vector((hero_cx + 4.0, -4.6, 1.6)), Vector((hero_cx + 3.2, -0.1, 1.4))),
    ]
    for f, loc, look in keys:
        oo.location = loc
        oo.rotation_euler = (look - loc).to_track_quat("-Z", "Y").to_euler()
        oo.keyframe_insert("location", frame=f)
        oo.keyframe_insert("rotation_euler", frame=f)
    for fc in oo.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return so, oo


def setup_compositor():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new("CompositorNodeRLayers")
    comp = tree.nodes.new("CompositorNodeComposite")
    if os.environ.get("V3_DIAG"):
        tree.links.new(rl.outputs["Image"], comp.inputs["Image"])
        return
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.1
    glare.size = 7
    if hasattr(glare, "mix"):
        glare.mix = -0.7
    # gentle contrast + vignette-free filmic grade
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
    print(f"[v3k2] Cycles backend: {chosen}")
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
    scene.view_settings.exposure = 0.2


def render_still(scene, cam):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = 640
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(STILL_PATH)
    print("[v3k2] rendering hero still ...")
    bpy.ops.render.render(write_still=True)


def render_video(scene, cam):
    scene.camera = cam
    scene.cycles.samples = 220
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
    print("[v3k2] rendering dolly video ...")
    bpy.ops.render.render(animation=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ctx = add_collection("v3_context")
    kiosks = add_collection("v3_kiosks")
    ground(ctx)

    HERO = -0.2
    kiosk_newsstand(kiosks, HERO)
    kiosk_cafe(kiosks, HERO + 4.5)
    kiosk_flower(kiosks, HERO - 4.2)

    build_world()
    add_sun()
    still_cam, dolly_cam = add_cameras(HERO)
    configure_cycles()
    setup_compositor()

    scene = bpy.context.scene
    scene.camera = still_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    render_still(scene, still_cam)
    if os.environ.get("V3_STILL_ONLY"):
        print("[v3k2] still-only; skip video")
        return
    render_video(scene, dolly_cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3k2] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
