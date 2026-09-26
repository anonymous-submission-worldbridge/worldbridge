"""Photorealistic procedural street-kiosk scene v3 (urban_v3_kiosk4).

kiosk3 still read as a toy: flat automotive paint, a cartoon gold barrel drum
next to the coffee booth, a letter-"M" standing in for the McDonald's logo and a
clip-art ice-cream cone panel.  kiosk4 pushes toward PHOTO realism and follows
the user's corrections:

  * COFFEE / MILK-TEA booth ("THE U COFFEE & TEA"):  DROP the yellow barrel
    building on the left entirely.  A clean, self-contained black-framed booth:
    cream scalloped awning over an open marble counter, glass pastry case,
    espresso machine, warm lit interior, crisp branded header.  Real materials,
    edge wear, grime, brushed metal - no flat plastic.
  * McDONALD'S booth:  the whole FRONT is a big mullioned GLASS storefront window
    showing a dressed interior (counter, menu boards, equipment).  The clip-art
    ICE-CREAM cone side panel is REMOVED.  The logo is the real GOLDEN ARCHES -
    a solid double-arch "M" built as extruded geometry, not a font glyph.

The realism levers:
  * REAL GOLDEN ARCHES - procedural double-hoop mesh (bevelled, glossy #FFC72C).
  * FULL GLASS STOREFRONT with aluminium mullions + a visible interior.
  * TEXTURED PBR - weathered paint, satin black, cream canvas, brushed alu,
    polished marble, laminated glass; realistic light-grey stone plaza (matte,
    not a mirror) so the scene stops reading as a render turntable.
  * split-sky city HDRI (bright to camera, weak for lighting so the sun casts a
    real shadow) + AgX + DoF + glare.

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_kiosk4.py
Env:
  V3_SPP=N          sample override (default 300 fast / 560 final)
  K_ENV=city|courtyard|sunset|sunrise   pick the HDRI (default city)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk4):
  kiosk.blend  kiosk.png (hero, coffee)  kiosk_b.png (mcd)  kiosk_overview.png
  (stills only - no video)
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk6")
SCENE_PATH = OUTPUT_DIR / "kiosk.blend"
STILL_PATH = OUTPUT_DIR / "kiosk.png"
STILL_B_PATH = OUTPUT_DIR / "kiosk_b.png"
OVERVIEW_PATH = OUTPUT_DIR / "kiosk_overview.png"

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


def _rrect(a, x0, y0, x1, y1, col):
    a[y0:y1, x0:x1, :] = np.array(col)


def make_milktea_poster(
    name, w=300, h=440, accent=(0.86, 0.24, 0.34), tea=(0.80, 0.62, 0.42)
):
    """A photo-styled bubble-tea promo: soft-lit background, a CYLINDRICALLY
    shaded cup (cream foam cap, milk-tea body, shaded tapioca bed), a glossy
    domed lid with specular, a straw, a soft contact shadow, a brand band and a
    price badge.  The shading is what lifts it out of the flat clip-art look."""
    a = np.ones((h, w, 3), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    acc = np.array(accent, dtype=np.float32)
    tea_c = np.array(tea, dtype=np.float32)
    cx = w * 0.5
    # background: white -> pale accent wash, with a soft radial vignette
    base_bg = acc * 0.14 + 0.86
    for y in range(h):
        t = y / h
        a[y, :, :] = np.array([1.0, 1.0, 1.0]) * (1 - t) + base_bg * t
    r = np.sqrt((xx - cx) ** 2 + (yy - h * 0.46) ** 2) / (w * 0.8)
    a *= np.clip(1.0 - 0.32 * r**2, 0.62, 1.0)[..., None]
    # brand band
    a[: int(h * 0.13), :, :] = acc
    a[int(h * 0.115) : int(h * 0.13), :, :] = acc * 0.7
    # cup geometry (trapezoid, wider at the top)
    cup_top, cup_bot = int(h * 0.26), int(h * 0.80)
    topw, botw = w * 0.24, w * 0.155
    ch = float(cup_bot - cup_top)
    trow = np.clip((yy - cup_top) / ch, 0.0, 1.0)
    hw = topw * (1 - trow) + botw * trow
    u = (xx - cx) / np.maximum(hw, 1e-3)
    cup_mask = (yy >= cup_top) & (yy < cup_bot) & (np.abs(u) <= 1.0)
    # cylinder shading: bright band a little left of centre, dark at the rims
    cyl = 0.60 + 0.45 * np.sqrt(np.clip(1 - u**2, 0, 1))
    hi = 0.42 * np.exp(-(((u + 0.35) / 0.22) ** 2))
    shade = np.clip(cyl + hi, 0.25, 1.35)
    foam_c = np.clip(tea_c * 0.55 + 0.52, 0, 1)
    bed_c = tea_c * 0.70
    col = np.clip(tea_c[None, None, :] * (1 - (trow[..., None] - 0.16) * 0.30), 0, 1)
    col[trow < 0.16] = foam_c
    col[trow > 0.68] = bed_c
    shaded = np.clip(col * shade[..., None], 0, 1)
    a[cup_mask] = shaded[cup_mask]
    # tapioca pearls in the bed, each with radial shading + a specular dot
    prng = np.random.RandomState(11)
    for _ in range(36):
        pr = prng.uniform(0.70, 0.965)
        py = cup_top + pr * ch
        hwp = topw * (1 - pr) + botw * pr
        px = cx + prng.uniform(-0.82, 0.82) * hwp
        rad = float(prng.randint(5, 9))
        dd = (xx - px) ** 2 + (yy - py) ** 2
        pm = dd < rad**2
        psh = 0.42 + 0.75 * np.clip(1 - dd / (rad**2), 0, 1)
        pearl = np.clip(np.array([0.14, 0.10, 0.08]) * psh[..., None], 0, 1)
        a[pm] = pearl[pm]
        sp = ((xx - (px - rad * 0.35)) ** 2 + (yy - (py - rad * 0.35)) ** 2) < (
            rad * 0.32
        ) ** 2
        a[sp & pm] = np.array([0.48, 0.40, 0.34])
    # glossy domed lid + specular + rim
    lid_h = ch * 0.16
    lidr = topw + w * 0.02
    ld = ((xx - cx) / lidr) ** 2 + ((yy - cup_top) / (lid_h * 1.6)) ** 2
    lid = (ld < 1.0) & (yy <= cup_top)
    lshade = 0.80 + 0.25 * np.sqrt(np.clip(1 - ((xx - cx) / lidr) ** 2, 0, 1))
    a[lid] = np.clip(np.array([0.86, 0.88, 0.90]) * lshade[..., None], 0, 1)[lid]
    ls = ((xx - (cx - lidr * 0.3)) ** 2 + (yy - (cup_top - lid_h * 0.6)) ** 2) < (
        lidr * 0.16
    ) ** 2
    a[ls & lid] = np.array([0.98, 0.99, 1.0])
    rim = (np.abs(yy - cup_top) < h * 0.012) & (np.abs(xx - cx) < topw + w * 0.02)
    a[rim] = np.array([0.72, 0.73, 0.76])
    # straw poking out of the lid
    for y in range(int(h * 0.11), cup_top + int(ch * 0.12)):
        sxx = int(cx + topw * 0.42 + (cup_top - y) * 0.16)
        a[y, sxx : sxx + max(6, int(w * 0.028)), :] = acc
    # soft contact shadow under the cup
    sd = ((xx - cx) / (botw * 1.5)) ** 2 + (
        (yy - (cup_bot + h * 0.015)) / (h * 0.028)
    ) ** 2
    a[(sd < 1.0) & (yy > cup_bot)] *= 0.55
    # stylised wordmark bars + a price badge
    a[int(h * 0.845) : int(h * 0.875), int(w * 0.16) : int(w * 0.84), :] = np.array(
        [0.16, 0.14, 0.13]
    )
    a[int(h * 0.885) : int(h * 0.905), int(w * 0.24) : int(w * 0.66), :] = np.array(
        [0.42, 0.39, 0.37]
    )
    bd = (xx - w * 0.80) ** 2 + (yy - h * 0.925) ** 2
    a[bd < (w * 0.12) ** 2] = acc
    a[bd < (w * 0.09) ** 2] = np.clip(acc * 0.55 + 0.4, 0, 1)
    return _new_image(name, a)


def make_mcd_menu(name, w=360, h=210):
    """A backlit McDonald's menu board: red header + a 2x3 grid of combo tiles."""
    a = np.ones((h, w, 3), dtype=np.float32)
    a[:, :, :] = np.array([0.98, 0.96, 0.90])
    a[: int(h * 0.20), :, :] = np.array([0.80, 0.06, 0.06])  # red header
    a[int(h * 0.05) : int(h * 0.15), int(w * 0.05) : int(w * 0.17), :] = np.array(
        [1.0, 0.78, 0.09]
    )
    a[int(h * 0.07) : int(h * 0.13), int(w * 0.20) : int(w * 0.55), :] = np.array(
        [0.98, 0.98, 0.96]
    )
    cols, rows = 3, 2
    for r in range(rows):
        for c in range(cols):
            x0 = int(w * (0.04 + c * 0.32))
            y0 = int(h * (0.26 + r * 0.36))
            tw = int(w * 0.28)
            th = int(h * 0.30)
            a[y0 : y0 + th, x0 : x0 + tw, :] = np.array([1.0, 1.0, 0.98])
            kind = (r * cols + c) % 3
            px0, py0 = x0 + 4, y0 + 4
            pw = int(tw * 0.5)
            ph = th - 8
            if kind == 0:  # burger
                a[py0 : py0 + ph, px0 : px0 + pw, :] = np.array([0.80, 0.55, 0.28])
                a[py0 + ph // 2 - 3 : py0 + ph // 2 + 3, px0 : px0 + pw, :] = np.array(
                    [0.45, 0.63, 0.28]
                )
            elif kind == 1:  # fries
                a[py0 : py0 + ph, px0 : px0 + pw, :] = np.array([0.85, 0.10, 0.10])
                for k in range(5):
                    xk = px0 + 3 + k * (pw // 5)
                    a[py0 - 6 : py0 + ph // 2, xk : xk + 3, :] = np.array(
                        [0.98, 0.80, 0.20]
                    )
            else:  # drink
                a[py0 : py0 + ph, px0 + pw // 5 : px0 + pw * 4 // 5, :] = np.array(
                    [0.88, 0.14, 0.14]
                )
            for tln in range(2):
                ty = y0 + 6 + tln * int(th * 0.30)
                a[ty : ty + 3, x0 + pw + 6 : x0 + tw - 4, :] = np.array(
                    [0.15, 0.13, 0.11]
                )
            a[y0 + th - 10 : y0 + th - 2, x0 + pw + 6 : x0 + tw - 4, :] = np.array(
                [0.80, 0.06, 0.06]
            )
    return _new_image(name, a)


def make_mcd_poster(name, kind="burger", w=220, h=300):
    """A product hero poster (red field) for the interior back wall."""
    a = np.ones((h, w, 3), dtype=np.float32)
    for y in range(h):
        t = y / h
        a[y, :, :] = (
            np.array([0.86, 0.09, 0.09]) * (1 - t) + np.array([0.5, 0.03, 0.03]) * t
        )
    yy, xx = np.ogrid[:h, :w]
    cx = w // 2
    cy = int(h * 0.46)
    if kind == "burger":
        m = (
            (xx - cx) ** 2 / (w * 0.34) ** 2 + (yy - (cy - 30)) ** 2 / (h * 0.12) ** 2
        ) < 1
        a[m] = np.array([0.82, 0.58, 0.30])  # top bun
        a[cy - 6 : cy + 6, cx - int(w * 0.32) : cx + int(w * 0.32), :] = np.array(
            [0.45, 0.63, 0.28]
        )
        a[cy + 6 : cy + 22, cx - int(w * 0.33) : cx + int(w * 0.33), :] = np.array(
            [0.42, 0.20, 0.12]
        )
        a[cy + 22 : cy + 34, cx - int(w * 0.31) : cx + int(w * 0.31), :] = np.array(
            [0.95, 0.78, 0.20]
        )
        m2 = (
            ((xx - cx) ** 2 / (w * 0.33) ** 2 + (yy - (cy + 48)) ** 2 / (h * 0.07) ** 2)
            < 1
        ) & (yy > cy + 30)
        a[m2] = np.array([0.80, 0.55, 0.28])  # bottom bun
    else:  # fries
        a[int(h * 0.40) : int(h * 0.85), int(w * 0.30) : int(w * 0.70), :] = np.array(
            [0.85, 0.08, 0.08]
        )
        for k in range(7):
            xk = int(w * 0.30) + 4 + k * int(w * 0.058)
            a[int(h * 0.22) : int(h * 0.5), xk : xk + int(w * 0.04), :] = np.array(
                [0.98, 0.80, 0.20]
            )
    a[int(h * 0.06) : int(h * 0.14), int(w * 0.1) : int(w * 0.9), :] = np.array(
        [0.98, 0.98, 0.96]
    )
    m = ((xx - int(w * 0.78)) ** 2 + (yy - int(h * 0.86)) ** 2) < (w * 0.16) ** 2
    a[m] = np.array([1.0, 0.78, 0.09])
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


def _arch_hoop_loop(cx, leg_bottom, cy, Ro, Ri, segs):
    """Closed 2D outline (x,z) of one croquet-hoop (∩ with legs): outer path up
    the left leg, over the top at radius Ro, down the right leg, then the inner
    path back at radius Ri.  Two of these overlapping = the golden arches M."""
    outer = [(cx - Ro, leg_bottom), (cx - Ro, cy)]
    for i in range(segs + 1):
        a = math.pi * (1 - i / segs)  # pi -> 0 (over the top)
        outer.append((cx + Ro * math.cos(a), cy + Ro * math.sin(a)))
    outer += [(cx + Ro, cy), (cx + Ro, leg_bottom)]
    inner = [(cx + Ri, leg_bottom), (cx + Ri, cy)]
    for i in range(segs + 1):
        a = math.pi * (i / segs)  # 0 -> pi (back under)
        inner.append((cx + Ri * math.cos(a), cy + Ri * math.sin(a)))
    inner += [(cx - Ri, cy), (cx - Ri, leg_bottom)]
    return outer + inner


def golden_arches(name, loc, W, Hm, depth, mat, coll, segs=56, bevel=0.01):
    """The McDonald's golden arches: two overlapping hoops sharing a centre leg,
    filled and extruded ``depth`` along +Y.  ``loc`` is the front-face centre of
    the bottom edge; the M faces -Y.  W = overall width, Hm = overall height."""
    Ro = W / 4.0
    t = 0.26 * Ro  # stroke thickness
    Ri = Ro - t
    cy = max(Hm - Ro, 0.05 * Ro)  # top of straight legs
    # centres chosen so the two hoops ABUT at x=2Ro (no overlap -> no z-fighting);
    # the shared centre leg is then a clean 2t-wide column.
    cxL, cxR = Ro, 3 * Ro
    bm = bmesh.new()
    for cx in (cxL, cxR):
        loop = _arch_hoop_loop(cx, 0.0, cy, Ro, Ri, segs)
        vs = [bm.verts.new((x, 0.0, z)) for (x, z) in loop]
        bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    res = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    ext_v = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, depth, 0.0), verts=ext_v)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    total_w = 4 * Ro
    o.location = (loc[0] - total_w / 2.0, loc[1], loc[2])  # centre horizontally
    if mat:
        o.data.materials.append(mat)
    _bevel(o, bevel, segments=3)
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
        (0.92, 0.66, 0.03),
        base_rough=0.28,
        rough_var=0.07,
        wear=0.05,
        dirt=0.16,
        coat=0.35,
        bump=0.05,
        bump_scale=200,
    )
    # McDonald's golden arches: bright #FFC72C, glossy clear-coat.  A gentle
    # self-emission guarantees EVERY face reads golden - no AO/shadow ever turns
    # the top of the arch black (the kiosk4 complaint).
    _ma, _nta, _ba = _principled("k5_archgold")
    _set(_ba, "Base Color", (1.0, 0.78, 0.09, 1.0))
    _set(_ba, "Metallic", 0.35)
    _set(_ba, "Roughness", 0.22)
    _set(_ba, ("Coat Weight", "Coat"), 0.5)
    _set(_ba, "Coat Roughness", 0.08)
    _set(_ba, "Specular IOR Level", 0.7)
    _set(_ba, "Emission Color", (1.0, 0.78, 0.09, 1.0))
    _set(_ba, "Emission Strength", 0.42)
    M["arch_gold"] = _ma
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
    # satin (not mirror) black -> reads as painted metal, kills the toy plastic look
    M["black_panel"] = mat_surface(
        "k3_black",
        (0.020, 0.020, 0.023),
        base_rough=0.48,
        rough_var=0.10,
        wear=0.06,
        wear_color=(0.11, 0.11, 0.12),
        dirt=0.34,
        coat=0.10,
        bump=0.07,
        bump_scale=150,
    )
    # matte sign panel (coat=0) so raised letters don't mirror a ghost copy
    M["sign_black"] = mat_surface(
        "k3_signblack",
        (0.016, 0.016, 0.018),
        base_rough=0.55,
        rough_var=0.08,
        dirt=0.16,
        coat=0.0,
    )
    # flat clean red for the sign backing behind the arches (no AO -> never goes black)
    _mr, _ntr, _br = _principled("k4_redflat")
    _set(_br, "Base Color", (0.60, 0.03, 0.03, 1.0))
    _set(_br, "Roughness", 0.44)  # more matte -> no mirrored wordmark ghost
    _set(_br, ("Coat Weight", "Coat"), 0.06)
    M["red_flat"] = _mr
    # lit red backing plate directly behind the arches: faint self-glow so the
    # arch openings read as bright red, never a shadowed black hole.
    _mrs, _ntrs, _brs = _principled("k5_redsign")
    _set(_brs, "Base Color", (0.66, 0.03, 0.03, 1.0))
    _set(_brs, "Roughness", 0.34)
    _set(_brs, ("Coat Weight", "Coat"), 0.25)
    _set(_brs, "Emission Color", (0.62, 0.03, 0.03, 1.0))
    _set(_brs, "Emission Strength", 0.5)
    M["red_sign"] = _mrs
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
    # realistic light-grey stone plaza: matte, faintly reflective, mottled - NOT a
    # black mirror.  This is the biggest "it's a render" tell in kiosk3.
    M["pave"] = mat_surface(
        "k4_pave",
        (0.205, 0.20, 0.195),
        base_rough=0.68,
        rough_var=0.20,
        rough_scale=3.2,
        bump=0.22,
        bump_scale=18,
        dirt=0.62,
        ao_dist=0.9,
        specular=0.28,
        coat=0.0,
    )
    M["pave_seam"] = mat_surface(
        "k4_paveseam", (0.06, 0.06, 0.065), base_rough=0.9, dirt=0.6
    )
    # emitters
    M["interior"] = mat_emit("k3_interior", (1.0, 0.96, 0.88), 4.5)
    M["strip"] = mat_emit("k3_strip", (1.0, 0.98, 0.92), 9.0)
    M["light_warm"] = mat_emit("k3_warm", (1.0, 0.9, 0.75), 3.0)
    # dark props / rubber
    M["dark"] = mat_surface("k3_dark", (0.03, 0.03, 0.035), base_rough=0.5, dirt=0.3)
    print("[v3k3] materials:", len(M))


# --------------------------------------------------------------------------- #
# KIOSK A - "THE U COFFEE & TEA"  (self-contained black-framed booth)
# The yellow barrel drum of kiosk3 is GONE.  Built facing -Y (front to camera).
# --------------------------------------------------------------------------- #
def build_kiosk_coffee(coll, cx=0.0):
    FRONT = -0.95  # counter opening plane
    BACK = 1.15
    DEPTH = BACK - FRONT
    CY = (FRONT + BACK) / 2
    body_x0, body_x1 = cx - 1.2, cx + 1.2  # compact self-contained booth
    bw = body_x1 - body_x0
    bcx = (body_x0 + body_x1) / 2
    H = 2.45  # taller shell -> a big sign

    # low granite plinth, tight to the booth footprint
    cube(
        "A:plinth",
        (bcx, CY, 0.06),
        (bw + 0.24, DEPTH + 0.22, 0.12),
        M["granite"],
        coll,
        bevel=0.01,
    )

    # ---- satin-black shell: back + both side walls + roof ----------------- #
    cube(
        "A:back",
        (bcx, BACK - 0.02, H / 2),
        (bw, 0.06, H),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:left",
        (body_x0 + 0.02, CY, H / 2),
        (0.06, DEPTH, H),
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
    cube(
        "A:roof",
        (bcx, CY, H + 0.03),
        (bw + 0.14, DEPTH + 0.12, 0.10),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    # brushed-alu corner posts (all four)
    for px in (body_x0 + 0.04, body_x1 - 0.04):
        for py in (FRONT + 0.03, BACK - 0.03):
            cube(
                f"A:post:{px:.2f}:{py:.2f}",
                (px, py, H / 2),
                (0.08, 0.08, H),
                M["alu"],
                coll,
                bevel=0.012,
            )
    # thin brushed kickplate along the base
    cube(
        "A:kickplate",
        (bcx, FRONT + 0.02, 0.14),
        (bw, 0.04, 0.28),
        M["steel"],
        coll,
        bevel=0.006,
    )

    # ---- signboard header + branding ------------------------------------- #
    sb_x0, sb_x1 = body_x0 + 0.02, body_x1 - 0.02
    sbw = sb_x1 - sb_x0
    sbcx = (sb_x0 + sb_x1) / 2
    # signboard overhangs the booth a little so the ONE-LINE brand can be large
    sign_w = bw + 0.28
    cube(
        "A:signboard",
        (sbcx, FRONT - 0.03, 2.05),
        (sign_w, 0.08, 0.74),
        M["sign_black"],
        coll,
        bevel=0.012,
    )
    # signboard front face sits at FRONT-0.07; seat the raised letters so their
    # BACK face (extrude half-depth 0.006) touches it -> no sun-cast drop-shadow
    # "ghost" of the floating text on the panel behind it.
    ty = FRONT - 0.076
    # compact red [U] logo badge, centred ABOVE the wordmark (brand mark only)
    cube(
        "A:ulogo",
        (sbcx, FRONT - 0.08, 2.28),
        (0.32, 0.03, 0.28),
        M["text_red"],
        coll,
        bevel=0.03,
    )
    text3d("A:u", "U", (sbcx, ty - 0.02, 2.268), 0.24, M["text_white"], coll)
    # ONE big centred line: THE COFFEE & TEA (gold) - the hero sign, single row
    text3d(
        "A:word",
        "THE COFFEE & TEA",
        (sbcx, ty, 1.90),
        0.315,
        M["text_gold"],
        coll,
        align_x="CENTER",
        char_spacing=1.0,
    )
    # small vertical CJK plate on the left front edge (rich-tea craft)
    cube(
        "A:pilaster",
        (body_x0 + 0.13, FRONT - 0.01, 1.15),
        (0.26, 0.05, 1.4),
        M["sign_black"],
        coll,
        bevel=0.008,
    )
    text3d(
        "A:pil_cjk",
        "Tea making with fresh ingredients",
        (body_x0 + 0.13, FRONT - 0.041, 1.15),
        0.20,
        M["text_white"],
        coll,
        spacing=1.05,
    )

    # NOTE: the cream scalloped awning of kiosk4 is REMOVED - the user asked to
    # drop the white obstruction blocking the counter, so
    # the sign + open counter now read cleanly.  A thin alu header bar remains.
    cyl(
        "A:awn_bar",
        (sbcx, FRONT - 0.04, 1.64),
        0.025,
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
        (bw - 0.16, 0.5, 1.0),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    cube(
        "A:counter_top",
        (bcx, ct_y, 1.02),
        (bw - 0.08, 0.56, 0.05),
        M["marble"],
        coll,
        bevel=0.012,
    )
    # --- # Promotional ads across the counter front include more images. --- #
    # each a shaded product photo of a real drink (pearl / brown-sugar / matcha)
    ad_specs = [
        ((0.86, 0.22, 0.32), (0.80, 0.62, 0.42)),  # pearl milk tea
        ((0.52, 0.32, 0.17), (0.64, 0.44, 0.27)),  # brown sugar boba
        ((0.30, 0.54, 0.31), (0.64, 0.74, 0.48)),  # matcha latte
    ]
    ad_y = ct_y - 0.27  # just proud of the counter base
    for k, ax in enumerate((bcx - 0.72, bcx, bcx + 0.72)):
        acc, teacol = ad_specs[k]
        img = make_milktea_poster(f"k5_ad{k}", accent=acc, tea=teacol)
        plane_img(
            f"A:ad:{k}",
            (ax, ad_y, 0.58),
            (0.50, 0.70),
            mat_image(f"k5_admat{k}", img, rough=0.18, coat=0.28),
            coll,
            rot=(math.radians(90), 0, 0),
        )
    # glass pastry display case on the counter
    disp_x = bcx - 0.45
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
    em_x = bcx + 0.52
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
        (bw - 0.6, 0.16, 0.03),
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

    return Vector((cx, CY, 1.3))


# --------------------------------------------------------------------------- #
# KIOSK B - red McDONALD'S food kiosk
# FULL glass storefront front + real GOLDEN ARCHES logo.  No ice-cream panel.
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
        (bw + 0.28, DEPTH + 0.22, 0.12),
        M["granite"],
        coll,
        bevel=0.01,
    )
    # red body: back + both side walls (the whole FRONT is glass)
    cube("B:back", (cx, BACK - 0.02, H / 2), (bw, 0.06, H), M["red"], coll, bevel=0.01)
    cube("B:left", (x0 + 0.02, CY, H / 2), (0.06, DEPTH, H), M["red"], coll, bevel=0.01)
    cube(
        "B:right", (x1 - 0.02, CY, H / 2), (0.06, DEPTH, H), M["red"], coll, bevel=0.01
    )
    # brushed-alu corner posts
    for px in (x0 + 0.04, x1 - 0.04):
        for py in (FRONT + 0.04, BACK - 0.04):
            cube(
                f"B:post:{px:.2f}:{py:.2f}",
                (px, py, H / 2),
                (0.08, 0.08, H),
                M["steel"],
                coll,
                bevel=0.01,
            )

    # ---- big glass storefront across the whole front --------------------- #
    win_x0, win_x1 = x0 + 0.10, x1 - 0.10
    win_w = win_x1 - win_x0
    wcx = (win_x0 + win_x1) / 2
    sill_z, head_z = 0.90, 1.90  # window from 0.90 to 1.90
    wcz, wh = (sill_z + head_z) / 2, head_z - sill_z
    # red bulkhead under the glass (the base panel)
    cube(
        "B:bulkhead",
        (wcx, FRONT + 0.02, sill_z / 2),
        (win_w + 0.06, 0.16, sill_z),
        M["red"],
        coll,
        bevel=0.01,
    )
    # stainless serving ledge protruding at the sill
    cube(
        "B:ledge",
        (wcx, FRONT - 0.06, sill_z + 0.02),
        (win_w - 0.02, 0.34, 0.06),
        M["steel"],
        coll,
        bevel=0.008,
    )
    # the single big glass pane
    cube(
        "B:glass",
        (wcx, FRONT + 0.0, wcz),
        (win_w - 0.06, 0.02, wh - 0.04),
        M["glass"],
        coll,
        bevel=0.003,
    )
    # aluminium storefront frame: head, sill, jambs, mullions, transom
    fr = 0.045
    cube(
        "B:fr_head",
        (wcx, FRONT - 0.01, head_z),
        (win_w + 0.02, 0.10, fr * 2),
        M["alu"],
        coll,
        bevel=0.006,
    )
    cube(
        "B:fr_sill",
        (wcx, FRONT - 0.01, sill_z),
        (win_w + 0.02, 0.10, fr * 2),
        M["alu"],
        coll,
        bevel=0.006,
    )
    for jx in (win_x0, win_x1):
        cube(
            f"B:fr_jamb:{jx:.2f}",
            (jx, FRONT - 0.01, wcz),
            (fr * 2, 0.10, wh),
            M["alu"],
            coll,
            bevel=0.006,
        )
    for f in (1 / 3, 2 / 3):  # vertical mullions -> 3 lights
        mx = win_x0 + f * win_w
        cube(
            f"B:mull:{f:.2f}",
            (mx, FRONT - 0.01, wcz),
            (fr, 0.09, wh),
            M["alu"],
            coll,
            bevel=0.005,
        )
    cube(
        "B:transom",
        (wcx, FRONT - 0.01, sill_z + wh * 0.62),
        (win_w, 0.09, fr),
        M["alu"],
        coll,
        bevel=0.005,
    )

    # ---- fully dressed, photoreal interior visible through the glass ------ #
    # (kiosk4 showed two bare white blocks - this is a real crew line: soda
    #  fountain, McCafé machine, fry station, packaged food, POS, order kiosk.)
    cube(
        "B:in_floor",
        (cx, CY + 0.1, 0.63),
        (bw - 0.2, DEPTH - 0.4, 0.02),
        M["steel"],
        coll,
        bevel=0,
    )
    cube(
        "B:in_back",
        (cx, BACK - 0.06, 1.35),
        (bw - 0.2, 0.04, 1.5),
        M["dark"],
        coll,
        bevel=0,
    )
    # long stainless service counter just inside the glass
    ic_y = FRONT + 0.46
    cube(
        "B:in_counter_base",
        (cx, ic_y, 0.72),
        (win_w - 0.18, 0.42, 0.92),
        M["steel"],
        coll,
        bevel=0.01,
    )
    cube(
        "B:in_counter_top",
        (cx, ic_y, 1.20),
        (win_w - 0.14, 0.46, 0.05),
        M["black_panel"],
        coll,
        bevel=0.01,
    )

    # soda fountain (dark tower, red graphic panel, drip tray, nozzles, cups) - left
    sf_x = cx - 0.95
    cube(
        "B:sf_body",
        (sf_x, ic_y + 0.02, 1.56),
        (0.44, 0.34, 0.62),
        M["dark"],
        coll,
        bevel=0.015,
    )
    cube(
        "B:sf_panel",
        (sf_x, ic_y - 0.16, 1.60),
        (0.40, 0.03, 0.50),
        mat_emit("k5_sfscreen", (0.9, 0.10, 0.10), 2.0),
        coll,
        bevel=0.004,
    )
    cube(
        "B:sf_tray",
        (sf_x, ic_y - 0.14, 1.28),
        (0.40, 0.16, 0.03),
        M["steel"],
        coll,
        bevel=0.004,
    )
    for nx in (sf_x - 0.10, sf_x, sf_x + 0.10):
        cube(
            f"B:sf_noz:{nx:.2f}",
            (nx, ic_y - 0.12, 1.40),
            (0.04, 0.04, 0.12),
            M["dark"],
            coll,
            bevel=0.006,
        )
    for ck in (sf_x - 0.12, sf_x + 0.12):
        cyl(
            f"B:sf_cup:{ck:.2f}",
            (ck, ic_y - 0.12, 1.31),
            0.035,
            0.09,
            M["white"],
            coll,
            verts=16,
            axis="Z",
        )

    # McCafé / espresso machine - centre (steel body + black top + group heads)
    mc_x = cx - 0.12
    cube(
        "B:mc_body",
        (mc_x, ic_y + 0.02, 1.44),
        (0.44, 0.34, 0.36),
        M["steel"],
        coll,
        bevel=0.02,
    )
    cube(
        "B:mc_top",
        (mc_x, ic_y + 0.02, 1.64),
        (0.40, 0.30, 0.06),
        M["black_panel"],
        coll,
        bevel=0.01,
    )
    for gx in (mc_x - 0.10, mc_x + 0.10):
        cyl(
            f"B:mc_grp:{gx:.2f}",
            (gx, ic_y - 0.16, 1.34),
            0.03,
            0.10,
            M["steel"],
            coll,
            verts=14,
            axis="Z",
        )

    # fry station + red fry cartons with golden fries - right
    fr_x = cx + 0.80
    fry_red = mat_surface("k5_fryred", (0.72, 0.06, 0.06), base_rough=0.40, coat=0.2)
    fry_yellow = mat_surface("k5_fryyellow", (0.95, 0.74, 0.16), base_rough=0.45)
    cube(
        "B:fry_body",
        (fr_x, ic_y + 0.04, 1.42),
        (0.50, 0.32, 0.30),
        M["steel"],
        coll,
        bevel=0.015,
    )
    for k, fx in enumerate((fr_x - 0.15, fr_x + 0.01, fr_x + 0.16)):
        cube(
            f"B:carton:{k}",
            (fx, ic_y - 0.14, 1.30),
            (0.09, 0.09, 0.12),
            fry_red,
            coll,
            bevel=0.006,
        )
        for j in range(3):
            cube(
                f"B:fry:{k}:{j}",
                (fx - 0.02 + j * 0.02, ic_y - 0.16, 1.40),
                (0.012, 0.012, 0.10),
                fry_yellow,
                coll,
                bevel=0,
            )

    # packaged burgers (yellow/red boxes) on the counter
    box_yellow = mat_surface("k5_boxy", (0.96, 0.76, 0.12), base_rough=0.5)
    for k, bxx in enumerate((cx + 0.14, cx + 0.30, cx + 0.22)):
        cube(
            f"B:box:{k}",
            (bxx, ic_y - 0.10, 1.28 + k * 0.05),
            (0.12, 0.10, 0.07),
            box_yellow,
            coll,
            bevel=0.008,
        )

    # two POS registers with glowing screens at the counter edge
    for k, rx in enumerate((cx - 0.60, cx + 0.48)):
        cube(
            f"B:pos:{k}",
            (rx, ic_y - 0.18, 1.30),
            (0.20, 0.16, 0.16),
            M["dark"],
            coll,
            bevel=0.012,
        )
        cube(
            f"B:pos_scr:{k}",
            (rx, ic_y - 0.27, 1.34),
            (0.16, 0.02, 0.11),
            mat_emit(f"k5_posscr{k}", (0.20, 0.5, 0.9), 1.8),
            coll,
            bevel=0.004,
            rot=(math.radians(-12), 0, 0),
        )

    # self-order kiosk screen near the left glass (tall, bright menu)
    cube(
        "B:kiosk_pole",
        (x0 + 0.35, FRONT + 0.30, 0.85),
        (0.08, 0.08, 1.1),
        M["dark"],
        coll,
        bevel=0.01,
    )
    sok = make_mcd_menu("k5_sok")
    plane_img(
        "B:kiosk_scr",
        (x0 + 0.35, FRONT + 0.24, 1.36),
        (0.42, 0.60),
        mat_image("k5_sokmat", sok, rough=0.15, emit=2.0),
        coll,
        rot=(math.radians(90), 0, 0),
    )

    # three backlit boards on the back wall: menu | burger hero | menu
    for k, (bkind, mx) in enumerate(
        (("menu", cx - 0.80), ("hero", cx), ("menu", cx + 0.80))
    ):
        img = (
            make_mcd_poster(f"k5_hero{k}", kind="burger")
            if bkind == "hero"
            else make_mcd_menu(f"k5_menu{k}")
        )
        plane_img(
            f"B:board:{k}",
            (mx, BACK - 0.10, 1.66),
            (0.80, 0.50),
            mat_image(f"k5_boardmat{k}", img, rough=0.25, emit=2.0),
            coll,
            rot=(math.radians(90), 0, 0),
        )

    # a stack of red trays on the counter
    tray_mat = mat_surface("k5_tray", (0.55, 0.08, 0.08), base_rough=0.40)
    for t in range(4):
        cube(
            f"B:tray:{t}",
            (cx + 0.02, ic_y + 0.12, 1.24 + t * 0.012),
            (0.34, 0.26, 0.01),
            tray_mat,
            coll,
            bevel=0.004,
        )

    # warm interior ceiling light strips
    cube(
        "B:in_light",
        (cx, CY + 0.05, H - 0.1),
        (bw - 0.4, DEPTH - 0.5, 0.04),
        M["interior"],
        coll,
        bevel=0,
    )
    cube(
        "B:in_light2",
        (cx, FRONT + 0.35, H - 0.14),
        (bw - 0.6, 0.14, 0.03),
        M["strip"],
        coll,
        bevel=0,
    )

    # ---- red roof + yellow fascia --------------------------------------- #
    roof_z = H + 0.13
    cube(
        "B:roof",
        (cx, CY + 0.04, roof_z),
        (bw + 0.36, DEPTH + 0.26, 0.12),
        M["red"],
        coll,
        bevel=0.02,
    )
    # red fascia band carrying the BIG white "McDonald's" wordmark
    # (Add larger white McDonald's sign above the shop)
    cube(
        "B:fascia",
        (cx, FRONT - 0.16, roof_z - 0.14),
        (bw + 0.36, 0.10, 0.42),
        M["red_flat"],
        coll,
        bevel=0.02,
    )
    # fascia front face at FRONT-0.21; seat the wordmark flush (back face touches
    # it) so the sun no longer casts a reddish drop-shadow "ghost" copy below it.
    # BIGGER wordmark (0.28 -> 0.36) on a taller band.
    text3d(
        "B:wordmark",
        "McDonald's",
        (cx, FRONT - 0.216, roof_z - 0.13),
        0.36,
        M["text_white"],
        coll,
        char_spacing=0.95,
    )
    # thin yellow accent stripe under the wordmark
    cube(
        "B:eave",
        (cx, FRONT - 0.15, roof_z - 0.37),
        (bw + 0.30, 0.06, 0.05),
        M["mcd_yellow"],
        coll,
        bevel=0.008,
    )

    # ---- sign pylon + REAL golden arches -------------------------------- #
    sgn_y = FRONT + 0.02
    # logo pylon + plate + arches - all a touch SMALLER than the first pass
    cube(
        "B:pylon",
        (cx, sgn_y + 0.08, roof_z + 0.50),
        (1.18, 0.12, 0.74),
        M["red"],
        coll,
        bevel=0.02,
    )
    # lit red backing plate covering the WHOLE logo so the arch openings and the
    # centre notch read as bright red, never a shadowed black hole
    cube(
        "B:sign_back",
        (cx, sgn_y - 0.005, roof_z + 0.54),
        (0.86, 0.02, 0.67),
        M["red_sign"],
        coll,
        bevel=0,
    )
    # the golden arches: procedural double-hoop mesh, glossy #FFC72C, sitting
    # FLUSH against the plate (back face touches it) so no dark gap shows through
    # the openings; the material self-emits so every face stays uniformly golden.
    # The size is slightly smaller this time (M tag + back panel slightly smaller).
    golden_arches(
        "B:arches",
        (cx, sgn_y - 0.075, roof_z + 0.32),
        0.63,
        0.47,
        0.05,
        M["arch_gold"],
        coll,
    )
    text3d(
        "B:brand", "McDonald's", (cx, sgn_y - 0.10, roof_z + 0.245), 0.10, M["text_gold"], coll
    )

    return Vector((cx, CY, 1.3))


# --------------------------------------------------------------------------- #
# Plaza ground
# --------------------------------------------------------------------------- #
def build_ground(coll):
    cube("gnd:slab", (2.0, 2.0, -0.02), (60, 40, 0.04), M["pave"], coll, bevel=0)
    # stone paver seams (large 1.5 m slabs, recessed dark grout)
    step = 1.5
    for i in range(-14, 18):
        cube(
            f"gnd:sx:{i}",
            (i * step, 2.0, 0.001),
            (0.04, 40, 0.010),
            M["pave_seam"],
            coll,
            bevel=0,
        )
    for j in range(-11, 14):
        cube(
            f"gnd:sy:{j}",
            (2.0, j * step, 0.001),
            (60, 0.04, 0.010),
            M["pave_seam"],
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
    bg_cam.inputs["Strength"].default_value = 1.05
    bg_light.inputs["Strength"].default_value = 0.22  # weaker fill -> punchier sun
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
    sun.data.energy = 9.0
    sun.data.angle = math.radians(1.2)  # crisp contact shadows
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_euler = (math.radians(42), 0, math.radians(-54))


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
    scene.view_settings.exposure = 0.0


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
        (target_a.x - 3.2, -5.4, 2.0),
        (target_a.x + 0.05, 0.0, 1.3),
        lens=36,
        fstop=5.6,
    )
    cam_b = make_camera(
        "cam_b",
        (target_b.x - 2.9, -6.6, 2.35),
        (target_b.x + 0.1, 0.0, 1.7),
        lens=34,
        fstop=6.3,
    )
    overview = make_camera(
        "cam_overview", (2.3, -8.6, 3.05), (2.4, 0.3, 1.35), lens=28, fstop=None
    )

    scene.camera = hero
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    # stills only (no video) - default 560 spp, override with V3_SPP for look-dev
    spp = int(os.environ.get("V3_SPP", 560))
    render_still(scene, hero, STILL_PATH, samples=spp)
    render_still(scene, cam_b, STILL_B_PATH, samples=spp)
    render_still(scene, overview, OVERVIEW_PATH, samples=max(360, spp - 140))
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3k4] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
