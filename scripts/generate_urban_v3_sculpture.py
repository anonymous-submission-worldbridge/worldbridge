#!/usr/bin/env python
"""
Photo-real procedural OUTDOOR PUBLIC-ART & PAVILION assets for WorldBridge.

Infinigen ships no real sculpture / gazebo assets (only a crude primitive
`PublicSpaceFactory` -> a cube plinth + a few bronze rings, toy-level), so this
builds a gallery of six varied, image-quality pieces from scratch:

  SCULPTURES
    1. mirror stainless-steel trefoil-knot          (modern polished art)
    2. patinated-bronze reclining figure (metaballs) (Henry-Moore-esque)
    3. red enamelled-steel stabile                   (Calder-esque)
  GAZEBOS / PAVILIONS
    4. Victorian octagonal bandstand                 (white timber + zinc dome)
    5. Chinese pavilion                              (red lacquer + green glaze)
    6. modern timber + corten-steel pergola

Rendered with Cycles + OptiX GPU, Nishita sky + soft-box, AgX, DoF.  Reuses the
proven material / lighting scaffold from generate_urban_v3_sharedbicycle*.py.

Run:
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_sculpture.py
  (SCULPT_QUICK=1 -> fast smoke test; URBAN_SCULPT_OUT overrides out dir)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sculpture):
  public_art.blend, overview.png, sculptures.png, pavilions.png,
  hero_*.png close-ups (one per asset)
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
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]


import math
import os
import sys
from pathlib import Path

REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUTPUT_DIR = Path(
    os.environ.get(
        "URBAN_SCULPT_OUT",
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sculpture",
    )
)
TMP_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
for d in (OUTPUT_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

SCENE_PATH = OUTPUT_DIR / "public_art.blend"
TAU = math.tau
QUICK = bool(os.environ.get("SCULPT_QUICK"))


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
        bpy.data.metaballs,
        bpy.data.images,
        bpy.data.lights,
        bpy.data.objects,
        bpy.data.cameras,
    ):
        for item in list(block):
            if getattr(item, "users", 0) == 0:
                try:
                    block.remove(item)
                except Exception:
                    pass


def add_collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def link_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def smooth(obj):
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


# --------------------------------------------------------------------------- #
# Node-graph helpers
# --------------------------------------------------------------------------- #
def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def _principled(mat):
    return mat.node_tree.nodes.get("Principled BSDF")


def _rgb(nt, color):
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs["Color"].default_value = (*color, 1.0)
    return n.outputs["Color"]


def _coord(nt):
    return nt.nodes.new("ShaderNodeTexCoord")


def _noise(nt, scale, detail=8.0, vec=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    if vec is not None:
        nt.links.new(vec, n.inputs["Vector"])
    return n


def _voronoi(nt, scale, vec=None, feature="F1"):
    n = nt.nodes.new("ShaderNodeTexVoronoi")
    n.feature = feature
    n.inputs["Scale"].default_value = scale
    if vec is not None:
        nt.links.new(vec, n.inputs["Vector"])
    return n


def _wave(nt, scale, distortion=0.0, detail=2.0, vec=None):
    n = nt.nodes.new("ShaderNodeTexWave")
    n.inputs["Scale"].default_value = scale
    n.inputs["Distortion"].default_value = distortion
    n.inputs["Detail"].default_value = detail
    if vec is not None:
        nt.links.new(vec, n.inputs["Vector"])
    return n


def _maprange(nt, val_socket, fmin, fmax, tmin, tmax, clamp=True):
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = clamp
    mr.inputs["From Min"].default_value = fmin
    mr.inputs["From Max"].default_value = fmax
    mr.inputs["To Min"].default_value = tmin
    mr.inputs["To Max"].default_value = tmax
    nt.links.new(val_socket, mr.inputs["Value"])
    return mr.outputs["Result"]


def _math(nt, op, a_sock=None, b_sock=None, a=0.0, b=0.0):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    if a_sock is not None:
        nt.links.new(a_sock, n.inputs[0])
    else:
        n.inputs[0].default_value = a
    if b_sock is not None:
        nt.links.new(b_sock, n.inputs[1])
    else:
        n.inputs[1].default_value = b
    return n.outputs["Value"]


def _mix(
    nt,
    fac_sock=None,
    fac=0.5,
    c1_sock=None,
    c1=None,
    c2_sock=None,
    c2=None,
    blend="MIX",
):
    n = nt.nodes.new("ShaderNodeMixRGB")
    n.blend_type = blend
    if fac_sock is not None:
        nt.links.new(fac_sock, n.inputs["Fac"])
    else:
        n.inputs["Fac"].default_value = fac
    if c1_sock is not None:
        nt.links.new(c1_sock, n.inputs["Color1"])
    elif c1 is not None:
        n.inputs["Color1"].default_value = (*c1, 1.0)
    if c2_sock is not None:
        nt.links.new(c2_sock, n.inputs["Color2"])
    elif c2 is not None:
        n.inputs["Color2"].default_value = (*c2, 1.0)
    return n.outputs["Color"]


def _bump(nt, b, scale, strength, vec=None):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(_noise(nt, scale, vec=vec).outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])


def _new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, None
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree


# --------------------------------------------------------------------------- #
# Material builders
# --------------------------------------------------------------------------- #
def chrome_material(name, color=(0.83, 0.84, 0.86), rough=0.045, coat=0.25):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Metallic", 1.0)
    _set(b, "Roughness", rough)
    _set(b, "Coat Weight", coat)
    _set(b, "Coat Roughness", 0.04)
    _set(b, "Anisotropic", 0.25)
    _bump(nt, b, 320.0, 0.006)  # micro imperfections keep it from CG-perfect
    return m


def metal_material(
    name, color, roughness=0.4, edge_amt=0.16, dust=0.15, bump_scale=130.0
):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    edge = tuple(min(1.0, c * 1.6 + 0.03) for c in color)
    base = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 26.0, vec=coord).outputs["Fac"], 0.4, 0.7, 0.0, edge_amt
        ),
        c1=color,
        c2=edge,
    )
    dirt = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 5.0, vec=coord).outputs["Fac"], 0.4, 0.7, 0.0, dust
        ),
        c1_sock=base,
        c2=(0.14, 0.13, 0.11),
    )
    nt.links.new(dirt, b.inputs["Base Color"])
    _set(b, "Metallic", 1.0)
    nt.links.new(
        _maprange(
            nt,
            _noise(nt, 40.0, vec=coord).outputs["Fac"],
            0.0,
            1.0,
            roughness - 0.06,
            roughness + 0.12,
        ),
        b.inputs["Roughness"],
    )
    _bump(nt, b, bump_scale, 0.04, vec=coord)
    return m


def bronze_material(
    name="bronze", base=(0.32, 0.165, 0.066), patina=(0.13, 0.32, 0.27)
):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    # Generated coords are robust on metaballs (Object coords can degenerate)
    coord = _coord(nt).outputs["Generated"]
    # verdigris collects only in scattered recesses -> keep bronze dominant
    fine = _noise(nt, 12.0, detail=10.0, vec=coord).outputs["Fac"]
    broad = _noise(nt, 3.0, detail=6.0, vec=coord).outputs["Fac"]
    mask = _math(
        nt,
        "MULTIPLY",
        a_sock=_maprange(
            nt, _math(nt, "MULTIPLY", a_sock=fine, b_sock=broad), 0.22, 0.5, 0.0, 1.0
        ),
        b=0.65,
    )
    col = _mix(nt, fac_sock=mask, c1=base, c2=patina)
    # streaky darker weathered runs
    col = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 4.0, vec=coord).outputs["Fac"], 0.6, 0.82, 0.0, 0.4
        ),
        c1_sock=col,
        c2=(0.10, 0.06, 0.03),
    )
    nt.links.new(col, b.inputs["Base Color"])
    # bronze is metallic; patina is a dull oxide -> drop metallic where patina sits
    nt.links.new(
        _math(nt, "SUBTRACT", a=1.0, b_sock=_math(nt, "MULTIPLY", a_sock=mask, b=0.95)),
        b.inputs["Metallic"],
    )
    nt.links.new(_maprange(nt, mask, 0.0, 1.0, 0.46, 0.85), b.inputs["Roughness"])
    _bump(nt, b, 45.0, 0.05, vec=coord)
    return m


def stone_material(
    name, color=(0.30, 0.29, 0.27), rough=0.85, speckle=0.35, grain=140.0
):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    lo = tuple(c * 0.78 for c in color)
    hi = tuple(min(1.0, c * 1.22) for c in color)
    base = _mix(nt, fac_sock=_noise(nt, 7.0, vec=coord).outputs["Fac"], c1=lo, c2=hi)
    # Monochrome mineral flecks: sharpen the Voronoi cell distance into isolated
    # points and mix between a dark and a light tint of the SAME stone hue. The
    # Voronoi *Color* output was giving per-cell random RGB (rainbow confetti).
    vor = _voronoi(nt, 90.0, vec=coord)
    fleck = _maprange(nt, vor.outputs["Distance"], 0.0, 0.14, 1.0, 0.0)
    dark = tuple(c * 0.55 for c in color)
    lite = tuple(min(1.0, c * 1.45) for c in color)
    speck_col = _mix(
        nt,
        fac_sock=fleck,
        c1_sock=base,
        c2_sock=_mix(
            nt, fac_sock=_noise(nt, 90.0, vec=coord).outputs["Fac"], c1=dark, c2=lite
        ),
    )
    speck = _mix(nt, fac=speckle, c1_sock=base, c2_sock=speck_col)
    nt.links.new(speck, b.inputs["Base Color"])
    _set(b, "Metallic", 0.0)
    _set(b, "Roughness", rough)
    _bump(nt, b, grain, 0.16, vec=coord)
    return m


def marble_material(name="marble", base=(0.80, 0.79, 0.76), vein=(0.34, 0.34, 0.37)):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    wv = _wave(nt, 2.4, distortion=9.0, detail=3.0, vec=coord)
    vmask = _maprange(nt, wv.outputs["Fac"], 0.35, 0.55, 0.0, 1.0)
    col = _mix(nt, fac_sock=vmask, c1=base, c2=vein)
    nt.links.new(col, b.inputs["Base Color"])
    _set(b, "Metallic", 0.0)
    _set(b, "Roughness", 0.24)
    _set(b, "Coat Weight", 0.3)
    _set(b, "Coat Roughness", 0.1)
    _bump(nt, b, 120.0, 0.03, vec=coord)
    return m


def wood_material(name, base=(0.22, 0.12, 0.05), rough=0.42, coat=0.0, grain_scale=3.5):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    dark = tuple(c * 0.7 for c in base)
    light = tuple(min(1.0, c * 1.8) for c in base)
    grain = _wave(nt, grain_scale, distortion=2.2, detail=3.0, vec=coord)
    col = _mix(nt, fac_sock=grain.outputs["Fac"], c1=dark, c2=light)
    col = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 14.0, vec=coord).outputs["Fac"], 0.45, 0.7, 0.0, 0.4
        ),
        c1_sock=col,
        c2=dark,
    )
    nt.links.new(col, b.inputs["Base Color"])
    _set(b, "Metallic", 0.0)
    _set(b, "Roughness", rough)
    _set(b, "Specular IOR Level", 0.5)
    if coat > 0:  # varnished / lacquered sheen
        _set(b, "Coat Weight", coat)
        _set(b, "Coat Roughness", 0.14)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(
        _wave(nt, grain_scale, distortion=2.2, vec=coord).outputs["Fac"],
        bump.inputs["Height"],
    )
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def roof_tile_material(name="roof_tile"):
    """Dark glazed clay barrel tiles - deep slate blue-grey with a wet sheen."""
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    base = _mix(
        nt,
        fac_sock=_noise(nt, 8.0, detail=8.0, vec=coord).outputs["Fac"],
        c1=(0.018, 0.015, 0.012),
        c2=(0.052, 0.043, 0.034),
    )
    # occasional weathered / mossy tiles
    base = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 3.0, vec=coord).outputs["Fac"], 0.55, 0.78, 0.0, 0.5
        ),
        c1_sock=base,
        c2=(0.040, 0.046, 0.034),
    )
    nt.links.new(base, b.inputs["Base Color"])
    _set(b, "Metallic", 0.0)
    # A large, smooth, sky-facing surface mirrors the bright uniform Nishita dome
    # if it has ANY gloss/coat -> reads as silver-beige regardless of base colour.
    # Kill the coat, keep roughness high, drop specular, and break the surface up
    # with a strong bump so no clean sky reflection can form. Dark matte slate.
    # roughness varies per-tile so it never reads as one uniform sheet
    rgh = _maprange(
        nt, _noise(nt, 26.0, detail=4.0, vec=coord).outputs["Fac"], 0.0, 1.0, 0.68, 0.86
    )
    nt.links.new(rgh, b.inputs["Roughness"])
    _set(b, "Specular IOR Level", 0.14)
    _set(b, "Coat Weight", 0.0)
    # keep bump SUBTLE - a strong noise bump turns the roof into lumpy stucco and
    # buries the crisp geometric tile ribs. The tile-row structure comes from the
    # batten geometry, not from this material.
    _bump(nt, b, 55.0, 0.06, vec=coord)
    return m


def glaze_material(name, color, rough=0.13):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    col = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 18.0, vec=coord).outputs["Fac"], 0.4, 0.65, 0.0, 0.25
        ),
        c1=color,
        c2=tuple(min(1.0, c * 1.5 + 0.02) for c in color),
    )
    nt.links.new(col, b.inputs["Base Color"])
    _set(b, "Metallic", 0.0)
    _set(b, "Roughness", rough)
    _set(b, "Coat Weight", 1.0)
    _set(b, "Coat Roughness", 0.06)
    _bump(nt, b, 130.0, 0.03, vec=coord)
    return m


def corten_material(name="corten"):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    coord = _coord(nt).outputs["Object"]
    rust = _mix(
        nt,
        fac_sock=_noise(nt, 10.0, detail=10.0, vec=coord).outputs["Fac"],
        c1=(0.20, 0.085, 0.035),
        c2=(0.40, 0.19, 0.08),
    )
    rust = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 3.0, vec=coord).outputs["Fac"], 0.45, 0.72, 0.0, 0.7
        ),
        c1_sock=rust,
        c2=(0.14, 0.06, 0.028),
    )
    nt.links.new(rust, b.inputs["Base Color"])
    _set(b, "Metallic", 0.12)
    _set(b, "Roughness", 0.72)
    _bump(nt, b, 90.0, 0.12, vec=coord)
    return m


def concrete_material(name="plaza_concrete"):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    _set(b, "Metallic", 0.0)
    coord = _coord(nt).outputs["Object"]
    base = _mix(
        nt,
        fac_sock=_noise(nt, 3.5, vec=coord).outputs["Fac"],
        c1=(0.30, 0.30, 0.31),
        c2=(0.42, 0.415, 0.40),
    )
    stained = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 1.6, vec=coord).outputs["Fac"], 0.35, 0.62, 0.0, 0.5
        ),
        c1_sock=base,
        c2=(0.20, 0.19, 0.18),
    )
    vor = _voronoi(nt, 4.0, vec=coord, feature="DISTANCE_TO_EDGE")
    crack = _maprange(nt, vor.outputs["Distance"], 0.0, 0.02, 0.0, 1.0)
    cracked = _mix(
        nt,
        fac_sock=_math(nt, "SUBTRACT", a=1.0, b_sock=crack),
        c1_sock=stained,
        c2=(0.12, 0.12, 0.12),
    )
    nt.links.new(cracked, b.inputs["Base Color"])
    _set(b, "Roughness", 0.9)
    _bump(nt, b, 180.0, 0.14, vec=coord)
    return m


def grass_material(name="lawn"):
    m, nt = _new_mat(name)
    if nt is None:
        return m
    b = _principled(m)
    _set(b, "Roughness", 0.92)
    coord = _coord(nt).outputs["Object"]
    fine = _mix(
        nt,
        fac_sock=_noise(nt, 110.0, vec=coord).outputs["Fac"],
        c1=(0.045, 0.075, 0.020),
        c2=(0.090, 0.130, 0.038),
    )
    patch = _mix(
        nt,
        fac_sock=_maprange(
            nt, _noise(nt, 4.0, vec=coord).outputs["Fac"], 0.4, 0.65, 0.0, 0.6
        ),
        c1_sock=fine,
        c2=(0.11, 0.10, 0.05),
    )
    nt.links.new(patch, b.inputs["Base Color"])
    _bump(nt, b, 240.0, 0.3, vec=coord)
    return m


MATS = {}


def build_materials():
    MATS["chrome"] = chrome_material("sc_chrome")
    MATS["steel"] = metal_material(
        "sc_steel",
        (0.52, 0.53, 0.55),
        roughness=0.34,
        edge_amt=0.14,
        dust=0.14,
        bump_scale=150.0,
    )
    MATS["zinc"] = metal_material(
        "sc_zinc",
        (0.44, 0.46, 0.48),
        roughness=0.44,
        edge_amt=0.1,
        dust=0.28,
        bump_scale=90.0,
    )
    MATS["brass"] = metal_material(
        "sc_brass",
        (0.63, 0.45, 0.15),
        roughness=0.26,
        edge_amt=0.2,
        dust=0.08,
        bump_scale=140.0,
    )
    MATS["gold"] = metal_material(
        "sc_gold",
        (0.74, 0.54, 0.14),
        roughness=0.22,
        edge_amt=0.15,
        dust=0.05,
        bump_scale=160.0,
    )
    MATS["bronze"] = bronze_material("sc_bronze")
    MATS["stone"] = stone_material("sc_stone", (0.30, 0.29, 0.27))
    MATS["stone_warm"] = stone_material(
        "sc_stone_warm", (0.46, 0.42, 0.35), speckle=0.25
    )
    MATS["marble"] = marble_material("sc_marble")
    MATS["red"] = glaze_material("sc_red", (0.40, 0.025, 0.02), rough=0.24)
    MATS["white"] = glaze_material("sc_white", (0.80, 0.78, 0.73), rough=0.32)
    MATS["lacquer_red"] = glaze_material(
        "sc_lacquer_red", (0.34, 0.02, 0.02), rough=0.12
    )
    MATS["glaze_green"] = glaze_material(
        "sc_glaze_green", (0.030, 0.14, 0.085), rough=0.11
    )
    MATS["wood"] = wood_material("sc_wood", (0.20, 0.11, 0.05))
    MATS["wood_light"] = wood_material("sc_wood_light", (0.34, 0.20, 0.09))
    # dark stained/varnished timber for the Chinese pavilion frame
    MATS["wood_dark"] = wood_material(
        "sc_wood_dark", (0.115, 0.050, 0.028), rough=0.30, coat=0.55, grain_scale=5.0
    )
    MATS["roof_tile"] = roof_tile_material("sc_roof_tile")
    MATS["corten"] = corten_material("sc_corten")
    MATS["concrete"] = concrete_material()
    MATS["grass"] = grass_material()
    print("[sculpt] materials:", list(MATS))


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #
def _finish(obj, mat, coll, shade_smooth=False, bevel=0.0, bevel_seg=2):
    obj.data.materials.append(mat)
    if bevel > 0:
        mod = obj.modifiers.new("bev", "BEVEL")
        mod.width = bevel
        mod.segments = bevel_seg
        mod.harden_normals = True
    if shade_smooth:
        smooth(obj)
    return link_to(obj, coll)


def box(name, loc, dims, mat, coll, bevel=0.006, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (dims[0], dims[1], dims[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler = rot
    return _finish(o, mat, coll, bevel=bevel)


def cyl(name, loc, radius, depth, mat, coll, verts=48, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=depth, location=loc
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    _finish(o, mat, coll)
    if verts > 8:
        for poly in o.data.polygons:
            if abs(poly.normal.z) < 0.7:
                poly.use_smooth = True
    return o


def cone(
    name, loc, r1, r2, depth, mat, coll, verts=48, rot=(0, 0, 0), smooth_side=True
):
    bpy.ops.mesh.primitive_cone_add(
        vertices=verts, radius1=r1, radius2=r2, depth=depth, location=loc
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    _finish(o, mat, coll)
    if smooth_side and verts > 8:
        for poly in o.data.polygons:
            if abs(poly.normal.z) < 0.95:
                poly.use_smooth = True
    return o


def torus(
    name,
    loc,
    major,
    minor,
    mat,
    coll,
    rot=(0, 0, 0),
    verts=56,
    minor_verts=18,
    scale=None,
):
    bpy.ops.mesh.primitive_torus_add(
        location=loc,
        major_radius=major,
        minor_radius=minor,
        major_segments=verts,
        minor_segments=minor_verts,
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    if scale is not None:
        o.scale = scale
    return _finish(o, mat, coll, shade_smooth=True)


def uvsphere(name, loc, radius, mat, coll, scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, location=loc, segments=40, ring_count=24
    )
    o = bpy.context.object
    o.name = name
    if scale is not None:
        o.scale = scale
    return _finish(o, mat, coll, shade_smooth=True)


def loop_tube(name, pts, radius, mat, coll, res=24, bevel_res=8):
    """A smooth CLOSED tube following a list of points (cyclic bezier)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.resolution_u = res
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    sp.use_cyclic_u = True
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    return link_to(o, coll)


def tube(name, pts, radius, mat, coll, res=16, bevel_res=6):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.resolution_u = res
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    return link_to(o, coll)


def poly_mesh(name, verts, faces, mat, coll, smooth=True, solidify=0.0):
    """Build an arbitrary mesh from vertex / face lists."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [list(f) for f in faces])
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    o.data.materials.append(mat)
    if solidify > 0:
        mod = o.modifiers.new("sol", "SOLIDIFY")
        mod.thickness = solidify
        mod.offset = 0.0
    link_to(o, coll)
    return o


def beam_between(
    name, p, q, width, height, mat, coll, z=None, bevel=0.01, extra_len=0.0
):
    """A box beam spanning horizontally from p to q (xy), centred at height z."""
    px, py = p[0], p[1]
    qx, qy = q[0], q[1]
    length = math.hypot(qx - px, qy - py) + extra_len
    yaw = math.atan2(qy - py, qx - px)
    zc = z if z is not None else (p[2] + q[2]) / 2
    return box(
        name,
        ((px + qx) / 2, (py + qy) / 2, zc),
        (length, width, height),
        mat,
        coll,
        bevel=bevel,
        rot=(0, 0, yaw),
    )


# --------------------------------------------------------------------------- #
# SCULPTURE 1 - mirror stainless-steel trefoil knot
# --------------------------------------------------------------------------- #
def build_mirror_knot(cx, cy, coll):
    # trefoil knot path (built first so the plinth can sit under its low point)
    s = 0.46
    cz = 2.15
    n = 24 if QUICK else 44
    pts = []
    for i in range(n):
        t = i / n * TAU
        x = math.sin(t) + 2 * math.sin(2 * t)
        y = math.cos(t) - 2 * math.cos(2 * t)
        z = -math.sin(3 * t)
        pts.append((cx + x * s, cy + y * s, cz + z * s))
    low = min(pts, key=lambda p: p[2])  # true lowest point of the loop
    # granite plinth centred under the knot's contact point
    box(
        "knot:plinth",
        (low[0], low[1], 0.55),
        (1.0, 1.0, 1.10),
        MATS["stone"],
        coll,
        bevel=0.04,
    )
    box(
        "knot:step",
        (low[0], low[1], 0.06),
        (1.45, 1.45, 0.12),
        MATS["stone"],
        coll,
        bevel=0.02,
    )
    loop_tube(
        "knot:ribbon",
        pts,
        0.13,
        MATS["chrome"],
        coll,
        res=(12 if QUICK else 26),
        bevel_res=(4 if QUICK else 10),
    )
    # polished stem from the plinth top up INTO the knot's lowest tube
    tube(
        "knot:stem",
        [(low[0], low[1], 1.05), (low[0], low[1], low[2] + 0.08)],
        0.11,
        MATS["chrome"],
        coll,
    )
    return {"center": (cx, cy, cz), "name": "hero_mirror_knot"}


# --------------------------------------------------------------------------- #
# SCULPTURE 2 - patinated-bronze reclining figure (metaballs)
# --------------------------------------------------------------------------- #
def build_bronze_figure(cx, cy, coll):
    # A Henry Moore-esque abstract RECLINING bronze: two raised masses
    # (head/shoulder + drawn-up knees) linked by a flowing lower body, pierced
    # by the sculptor's signature through-hole.  Reads as intentional museum art
    # rather than a failed literal human.  Long, low, resting on a wide plinth.
    box(
        "figure:plinth",
        (cx, cy, 0.30),
        (3.2, 1.8, 0.60),
        MATS["stone_warm"],
        coll,
        bevel=0.03,
    )
    box(
        "figure:step",
        (cx, cy, 0.05),
        (3.7, 2.3, 0.10),
        MATS["stone_warm"],
        coll,
        bevel=0.02,
    )

    mball = bpy.data.metaballs.new("figure_mb")
    mball.resolution = 0.10 if QUICK else 0.028
    mball.render_resolution = 0.08 if QUICK else 0.024
    mball.threshold = 0.6
    obj = bpy.data.objects.new("figure:body", mball)
    obj.data.materials.append(MATS["bronze"])
    link_to(obj, coll)

    top = 0.60  # plinth top; the body rests ON it
    # Elongated ELLIPSOID elements laid along +X.  (dx, dy, dz, r, (sx,sy,sz))
    # The reclining silhouette: shoulder hump -> waist dip -> hip -> raised knees.
    # Centres spaced ~0.45 apart with generous overlap so the field fuses into
    # ONE continuous reclining log (no severing).  Two humps, a low waist dip.
    masses = [
        (-1.10, 0.0, 0.58, 0.52, (0.95, 1.30, 1.35)),  # head + shoulder hump
        (-0.62, 0.0, 0.44, 0.54, (1.45, 1.25, 0.98)),  # upper back
        (-0.18, 0.0, 0.36, 0.54, (1.45, 1.20, 0.80)),  # waist (low dip)
        (0.24, 0.0, 0.36, 0.54, (1.35, 1.20, 0.80)),  # hip bridge (keeps it joined)
        (0.62, 0.0, 0.46, 0.52, (1.30, 1.28, 0.98)),  # pelvis
        (1.02, 0.0, 0.64, 0.52, (1.00, 1.25, 1.32)),  # drawn-up knees (2nd hump)
        (1.38, 0.05, 0.42, 0.44, (0.78, 0.98, 0.82)),  # calf / foot taper
    ]
    for i, (dx, dy, dz, r, sz) in enumerate(masses):
        el = mball.elements.new()
        el.type = "ELLIPSOID"
        el.co = (cx + dx, cy + dy, top + dz)
        el.radius = r
        el.size_x, el.size_y, el.size_z = sz
        el.stiffness = 2.2
    return {"center": (cx, cy, top + 0.7), "name": "hero_bronze_figure"}


# --------------------------------------------------------------------------- #
# SCULPTURE 3 - red enamelled-steel stabile (Calder-esque)
# --------------------------------------------------------------------------- #
def build_red_stabile(cx, cy, coll):
    box(
        f"stab:pad",
        (cx, cy, 0.05),
        (2.6, 2.6, 0.10),
        MATS["concrete"],
        coll,
        bevel=0.02,
    )
    red = MATS["red"]
    H = 2.55
    zc = 0.10 + H / 2  # bottom edge rests ON the pad top (z=0.10)
    # Three vertical plates rising from the pad, all passing through the central
    # axis -> they physically intersect into ONE grounded, connected form.  Only
    # rotated about Z so every foot stays on the ground (no floating).
    for i, adeg in enumerate((0.0, 58.0, 118.0)):
        a = math.radians(adeg)
        w = (1.95, 1.65, 1.80)[i]
        box(
            f"stab:plate:{i}",
            (cx, cy, zc),
            (w, 0.06, H),
            red,
            coll,
            bevel=0.025,
            rot=(0, 0, a),
        )
    # crowning swept blade + cantilevered fin, bridging the plate tops
    box(
        f"stab:blade",
        (cx - 0.05, cy, H + 0.24),
        (2.35, 0.06, 0.62),
        red,
        coll,
        bevel=0.025,
        rot=(0.0, math.radians(-15), math.radians(7)),
    )
    box(
        f"stab:fin",
        (cx + 0.85, cy + 0.15, H + 0.42),
        (0.9, 0.06, 0.5),
        red,
        coll,
        bevel=0.025,
        rot=(math.radians(18), math.radians(32), 0.0),
    )
    # bolt hardware ON the central spine where the plates cross (pierces them)
    for i, z in enumerate((0.55, 1.30, 2.05)):
        cyl(
            f"stab:bolt:{i}",
            (cx, cy, z),
            0.055,
            0.46,
            MATS["steel"],
            coll,
            verts=16,
            rot=(math.pi / 2, 0, 0),
        )
    return {"center": (cx, cy, 1.5), "name": "hero_red_stabile"}


# --------------------------------------------------------------------------- #
# GAZEBO 1 - Victorian octagonal bandstand
# --------------------------------------------------------------------------- #
def build_bandstand(cx, cy, coll):
    R = 2.15
    col_r = 1.85
    floor_z = 0.55
    col_h = 2.55
    cap_z = floor_z + col_h
    # stepped stone base (octagonal)
    cyl("band:step2", (cx, cy, 0.12), 2.65, 0.24, MATS["stone"], coll, verts=8)
    cyl("band:step1", (cx, cy, 0.34), 2.40, 0.24, MATS["stone"], coll, verts=8)
    cyl(
        "band:plinth",
        (cx, cy, floor_z - 0.06),
        2.25,
        0.12,
        MATS["stone"],
        coll,
        verts=8,
    )
    cyl(
        "band:floor",
        (cx, cy, floor_z + 0.03),
        2.12,
        0.06,
        MATS["wood_light"],
        coll,
        verts=8,
    )
    # 8 columns + railing + brackets
    entrance = 0  # leave this bay open as the entry
    for i in range(8):
        a = i * TAU / 8 + math.radians(22.5)
        px, py = cx + math.cos(a) * col_r, cy + math.sin(a) * col_r
        cyl(
            f"band:col:{i}",
            (px, py, floor_z + col_h / 2),
            0.075,
            col_h,
            MATS["white"],
            coll,
            verts=20,
        )
        cyl(
            f"band:base:{i}",
            (px, py, floor_z + 0.10),
            0.11,
            0.20,
            MATS["white"],
            coll,
            verts=20,
        )
        cyl(
            f"band:cap:{i}",
            (px, py, cap_z - 0.10),
            0.11,
            0.20,
            MATS["white"],
            coll,
            verts=20,
        )
        # railing to the next column (skip entrance bay)
        if i != entrance:
            a2 = (i + 1) * TAU / 8 + math.radians(22.5)
            qx, qy = cx + math.cos(a2) * col_r, cy + math.sin(a2) * col_r
            for hz, hr in ((floor_z + 0.12, 0.03), (floor_z + 0.85, 0.035)):
                tube(
                    f"band:rail:{i}:{hz:.2f}",
                    [(px, py, hz), (qx, qy, hz)],
                    hr,
                    MATS["white"],
                    coll,
                )
            nb = 3 if QUICK else 5
            for k in range(1, nb + 1):
                t = k / (nb + 1)
                bx, by = px + (qx - px) * t, py + (qy - py) * t
                cyl(
                    f"band:balus:{i}:{k}",
                    (bx, by, floor_z + 0.48),
                    0.022,
                    0.72,
                    MATS["white"],
                    coll,
                    verts=12,
                )
        # ornate bracket under the eave
        inx, iny = cx + math.cos(a) * (col_r - 0.28), cy + math.sin(a) * (col_r - 0.28)
        box(
            f"band:bracket:{i}",
            ((px + inx) / 2, (py + iny) / 2, cap_z + 0.02),
            (0.34, 0.05, 0.28),
            MATS["white"],
            coll,
            bevel=0.02,
            rot=(0, 0, a),
        )
    # eave fascia ring
    torus(
        "band:fascia",
        (cx, cy, cap_z + 0.06),
        col_r + 0.06,
        0.07,
        MATS["white"],
        coll,
        verts=48,
    )
    cyl(
        "band:eave",
        (cx, cy, cap_z + 0.16),
        col_r + 0.28,
        0.16,
        MATS["white"],
        coll,
        verts=8,
    )
    # zinc standing-seam octagonal roof
    roof = cone(
        "band:roof",
        (cx, cy, cap_z + 0.9),
        col_r + 0.42,
        0.14,
        1.55,
        MATS["zinc"],
        coll,
        verts=8,
        smooth_side=False,
    )
    # standing seams along the 8 hips
    rtop = cap_z + 0.9 + 1.55 / 2
    reave = cap_z + 0.9 - 1.55 / 2
    for i in range(8):
        a = i * TAU / 8
        ex, ey = cx + math.cos(a) * (col_r + 0.42), cy + math.sin(a) * (col_r + 0.42)
        tube(
            f"band:seam:{i}",
            [(ex, ey, reave + 0.05), (cx, cy, rtop - 0.05)],
            0.02,
            MATS["zinc"],
            coll,
        )
    # brass finial
    cyl(
        "band:finpost", (cx, cy, rtop + 0.12), 0.05, 0.34, MATS["brass"], coll, verts=16
    )
    uvsphere("band:finial", (cx, cy, rtop + 0.36), 0.13, MATS["brass"], coll)
    cone(
        "band:fintip",
        (cx, cy, rtop + 0.58),
        0.06,
        0.0,
        0.18,
        MATS["brass"],
        coll,
        verts=16,
    )
    return {"center": (cx, cy, cap_z), "name": "hero_bandstand"}


# --------------------------------------------------------------------------- #
# GAZEBO 2 - Chinese pavilion
# --------------------------------------------------------------------------- #
def build_chinese_pavilion(cx, cy, coll):
    # A large hexagonal structure with a dark-stained timber frame atop a raised stone base.
    # platform, deep curved tiled hip roof with battens / hip ridges / swept-up
    # corners, woman leaning on bench, lattice frieze, banner signboard, interior
    # stone table + stools.
    WD = MATS["wood_dark"]
    TILE = MATS["roof_tile"]
    STONE = MATS["stone"]
    GOLD = MATS["gold"]

    col_R = 2.35  # column-circle circumradius
    col_h = 3.35  # column height  (taller / bigger)
    floor_z = 0.66  # walking-surface top
    corner_a = [math.radians(90 + 60 * k) for k in range(6)]
    col_pos = [(cx + col_R * math.cos(a), cy + col_R * math.sin(a)) for a in corner_a]

    # ---- stepped hexagonal stone base --------------------------------------
    hexrot = (0, 0, math.radians(90))
    cyl("pav:step2", (cx, cy, 0.14), 4.05, 0.28, STONE, coll, verts=6, rot=hexrot)
    cyl("pav:step1", (cx, cy, 0.40), 3.62, 0.24, STONE, coll, verts=6, rot=hexrot)
    cyl(
        "pav:platform",
        (cx, cy, floor_z - 0.10),
        3.30,
        0.20,
        MATS["stone_warm"],
        coll,
        verts=6,
        rot=hexrot,
    )

    # ---- columns on carved stone drums -------------------------------------
    for i, (px, py) in enumerate(col_pos):
        cyl(
            f"pav:drum:{i}", (px, py, floor_z + 0.11), 0.33, 0.22, STONE, coll, verts=24
        )
        cyl(
            f"pav:col:{i}",
            (px, py, floor_z + col_h / 2),
            0.205,
            col_h,
            MATS["wood_dark"],
            coll,
            verts=24,
        )

    col_top = floor_z + col_h
    OPEN_BAY = 5  # leave this bay as the entrance

    def inward(px, py, d):
        vx, vy = cx - px, cy - py
        n = math.hypot(vx, vy) or 1.0
        return px + vx / n * d, py + vy / n * d

    # --- bay-specific: A woman's seat with apron, head beam, and lattice frieze ---
    for k in range(6):
        ax, ay = col_pos[k]
        bx, by = col_pos[(k + 1) % 6]
        # architrave main head beam + slim eave purlin above it
        beam_between(
            f"pav:arch:{k}",
            (ax, ay, 0),
            (bx, by, 0),
            0.16,
            0.36,
            WD,
            coll,
            z=col_top - 0.26,
            extra_len=0.30,
        )
        beam_between(
            f"pav:purlin:{k}",
            (ax, ay, 0),
            (bx, by, 0),
            0.12,
            0.14,
            WD,
            coll,
            z=col_top - 0.02,
            extra_len=0.34,
        )
        # Corbel brackets flank each column under the beam.
        for jx, jy in ((ax, ay), (bx, by)):
            mx, my = (jx + (bx if (jx, jy) == (ax, ay) else ax)) / 2, (
                jy + (by if (jx, jy) == (ax, ay) else ay)
            ) / 2
            qx, qy = jx + (mx - jx) * 0.28, jy + (my - jy) * 0.28
            beam_between(
                f"pav:corbel:{k}:{jx:.2f}",
                (jx, jy, 0),
                (qx, qy, 0),
                0.10,
                0.22,
                WD,
                coll,
                z=col_top - 0.52,
            )
        # lattice frieze hanging below the architrave
        yaw = math.atan2(by - ay, bx - ax)
        beam_between(
            f"pav:friezebar:{k}",
            (ax, ay, 0),
            (bx, by, 0),
            0.05,
            0.05,
            WD,
            coll,
            z=col_top - 0.86,
        )
        nfd = 4 if QUICK else 9
        for d in range(1, nfd):
            t = d / nfd
            fx, fy = ax + (bx - ax) * t, ay + (by - ay) * t
            box(
                f"pav:frieze:{k}:{d}",
                (fx, fy, col_top - 0.68),
                (0.035, 0.035, 0.34),
                WD,
                coll,
                bevel=0.005,
                rot=(0, 0, yaw),
            )
        if k == OPEN_BAY:
            continue
        # bench seat (pulled inward from the columns) + skirt apron
        s0 = inward(ax, ay, 0.16)
        s1 = inward(bx, by, 0.16)
        beam_between(
            f"pav:seat:{k}",
            s0,
            s1,
            0.44,
            0.07,
            WD,
            coll,
            z=floor_z + 0.46,
            extra_len=-0.10,
        )
        beam_between(
            f"pav:apron:{k}",
            (ax, ay, 0),
            (bx, by, 0),
            0.06,
            0.30,
            WD,
            coll,
            z=floor_z + 0.20,
            extra_len=-0.16,
        )
        # outward-leaning backrest: top hand-rail + balusters
        beam_between(
            f"pav:handrail:{k}",
            (ax, ay, 0),
            (bx, by, 0),
            0.07,
            0.08,
            WD,
            coll,
            z=floor_z + 0.92,
            extra_len=-0.10,
        )
        nb = 3 if QUICK else 6
        for d in range(1, nb):
            t = d / nb
            rx, ry = ax + (bx - ax) * t, ay + (by - ay) * t
            box(
                f"pav:balus:{k}:{d}",
                (rx, ry, floor_z + 0.69),
                (0.045, 0.045, 0.46),
                WD,
                coll,
                bevel=0.005,
                rot=(0, 0, yaw),
            )

    # Signboard on the front-facing bay (Bay 2 faces the camera).
    sb_k = 2
    ax, ay = col_pos[sb_k]
    bx, by = col_pos[(sb_k + 1) % 6]
    mx, my = (ax + bx) / 2, (ay + by) / 2
    ox, oy = mx + (mx - cx) * 0.04, my + (my - cy) * 0.04  # nudge outward
    yaw = math.atan2(by - ay, bx - ax)
    box(
        "pav:signframe",
        (ox, oy, col_top - 0.40),
        (1.7, 0.10, 0.62),
        GOLD,
        coll,
        bevel=0.02,
        rot=(0, 0, yaw),
    )
    box(
        "pav:signface",
        (ox + (mx - cx) * 0.012, oy + (my - cy) * 0.012, col_top - 0.40),
        (1.48, 0.12, 0.44),
        MATS["lacquer_red"],
        coll,
        bevel=0.01,
        rot=(0, 0, yaw),
    )
    for sx in (-0.5, 0.0, 0.5):  # three gold "character" cartouches
        gx = ox + math.cos(yaw) * sx
        gy = oy + math.sin(yaw) * sx
        box(
            f"pav:signch:{sx}",
            (gx + (mx - cx) * 0.02, gy + (my - cy) * 0.02, col_top - 0.40),
            (0.24, 0.10, 0.26),
            GOLD,
            coll,
            bevel=0.01,
            rot=(0, 0, yaw),
        )

    # ---- interior: round stone table + drum stools -------------------------
    cyl("pav:tbl_ped", (cx, cy, floor_z + 0.36), 0.20, 0.68, STONE, coll, verts=20)
    cyl(
        "pav:tbl_top",
        (cx, cy, floor_z + 0.74),
        0.62,
        0.10,
        MATS["marble"],
        coll,
        verts=40,
    )
    for si in range(4):
        sa = math.radians(45 + 90 * si)
        sx2, sy2 = cx + 0.98 * math.cos(sa), cy + 0.98 * math.sin(sa)
        cyl(
            f"pav:stool:{si}",
            (sx2, sy2, floor_z + 0.26),
            0.24,
            0.50,
            MATS["stone_warm"],
            coll,
            verts=24,
        )

    # ---- CURVED TILED HEXAGONAL HIP ROOF -----------------------------------
    eave_R = col_R + 1.55  # deep overhang
    eave_z = col_top + 0.14
    roof_H = 2.55  # lower / broader peak - less tent-like
    apex_z = eave_z + roof_H
    NR = 4 if QUICK else 6  # rings apex->eave
    seg = 2 if QUICK else 4  # samples per hex edge
    N = 6 * seg
    KICK_Z, KICK_R = 1.15, 0.17
    corner_xy = [(math.cos(a) * eave_R, math.sin(a) * eave_R) for a in corner_a]

    def perim(j):  # point on hexagon perimeter (straight edges)
        e = j // seg
        t = (j % seg) / seg
        c0, c1 = corner_xy[e], corner_xy[(e + 1) % 6]
        return (c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t)

    def cornerness(j):
        t = (j % seg) / seg
        return abs(math.cos(math.pi * t))

    def ring_pt(i, j):  # world xyz of roof vertex (ring i, sample j)
        rho = i / NR
        px, py = perim(j)
        w = cornerness(j)
        u = rho**3
        scl = rho * (1.0 + KICK_R * u * w)
        z = apex_z - (apex_z - eave_z) * (rho**0.74) + KICK_Z * u * w
        return (cx + px * scl, cy + py * scl, z)

    verts = [(cx, cy, apex_z)]
    for i in range(1, NR + 1):
        for j in range(N):
            verts.append(ring_pt(i, j))

    def vid(i, j):
        return 0 if i == 0 else 1 + (i - 1) * N + (j % N)

    faces = []
    for j in range(N):  # apex fan
        faces.append((vid(0, 0), vid(1, j), vid(1, j + 1)))
    for i in range(1, NR):  # quad strips
        for j in range(N):
            faces.append((vid(i, j), vid(i, j + 1), vid(i + 1, j + 1), vid(i + 1, j)))
    poly_mesh("pav:roof", verts, faces, TILE, coll, smooth=True, solidify=0.14)

    # tile battens: convex barrel-tile ribs running down every slope line
    # sitting proud of the surface. These ARE the tile texture - make them read.
    for j in range(N):
        pts = []
        for i in range(1, NR + 1):
            x, y, z = ring_pt(i, j)
            pts.append((cx + (x - cx) * 1.010, cy + (y - cy) * 1.010, z + 0.045))
        tube(
            f"pav:batten:{j}",
            pts,
            0.050,
            TILE,
            coll,
            res=(6 if QUICK else 14),
            bevel_res=(3 if QUICK else 6),
        )

    # fatter HIP ridges + swept-up corner tips + ornaments at the 6 corners
    for e in range(6):
        j = e * seg
        pts = []
        for i in range(1, NR + 1):
            x, y, z = ring_pt(i, j)
            pts.append((cx + (x - cx) * 1.02, cy + (y - cy) * 1.02, z + 0.09))
        tube(
            f"pav:hip:{e}",
            pts,
            0.065,
            TILE,
            coll,
            res=(6 if QUICK else 14),
            bevel_res=(3 if QUICK else 6),
        )
        tipx, tipy, tipz = pts[-1]
        uvsphere(f"pav:hiptip:{e}", (tipx, tipy, tipz + 0.05), 0.10, GOLD, coll)

    # continuous carved eave fascia board - hanging just under the eave lip
    # tracing the up-swept eave line (replaces the old floating rafter dentils).
    for j in range(N):
        p = ring_pt(NR, j)
        q = ring_pt(NR, (j + 1) % N)
        beam_between(
            f"pav:fascia:{j}",
            p,
            q,
            0.05,
            0.22,
            WD,
            coll,
            z=(p[2] + q[2]) / 2 - 0.13,
            bevel=0.008,
            extra_len=0.04,
        )
    # short rafter tails poking out just above the fascia, tucked to the underside
    for j in range(0, N, 2):
        x, y, z = ring_pt(NR, j)
        yaw = math.atan2(y - cy, x - cx)
        box(
            f"pav:rafter:{j}",
            (cx + (x - cx) * 0.965, cy + (y - cy) * 0.965, z - 0.05),
            (0.22, 0.07, 0.07),
            MATS["wood_dark"],
            coll,
            bevel=0.006,
            rot=(0, 0, yaw),
        )

    # central finial (baoding)
    cyl("pav:finbase", (cx, cy, apex_z + 0.10), 0.22, 0.30, TILE, coll, verts=24)
    uvsphere("pav:fingourd1", (cx, cy, apex_z + 0.48), 0.22, GOLD, coll)
    uvsphere("pav:fingourd2", (cx, cy, apex_z + 0.82), 0.15, GOLD, coll)
    cone("pav:fintip", (cx, cy, apex_z + 1.06), 0.10, 0.0, 0.24, GOLD, coll, verts=20)
    return {"center": (cx, cy, col_top), "name": "hero_chinese_pavilion"}


# --------------------------------------------------------------------------- #
# GAZEBO 3 - modern timber + corten pergola
# --------------------------------------------------------------------------- #
def build_pergola(cx, cy, coll):
    W, D = 3.6, 2.6  # footprint
    post_h = 2.5
    px = W / 2 - 0.2
    py = D / 2 - 0.2
    # concrete pad
    box(
        "perg:pad",
        (cx, cy, 0.05),
        (W + 0.8, D + 0.8, 0.10),
        MATS["concrete"],
        coll,
        bevel=0.02,
    )
    # 6 corten posts (2 rows x 3)
    posts = [(-px, -py), (0, -py), (px, -py), (-px, py), (0, py), (px, py)]
    for i, (dx, dy) in enumerate(posts):
        box(
            f"perg:post:{i}",
            (cx + dx, cy + dy, post_h / 2),
            (0.15, 0.15, post_h),
            MATS["corten"],
            coll,
            bevel=0.01,
        )
    # long beams (corten) along the two rows
    for i, dy in enumerate((-py, py)):
        box(
            f"perg:beam:{i}",
            (cx, cy + dy, post_h + 0.10),
            (W + 0.3, 0.10, 0.30),
            MATS["corten"],
            coll,
            bevel=0.01,
        )
    # cross beams
    for i, dx in enumerate((-px, 0, px)):
        box(
            f"perg:cross:{i}",
            (cx + dx, cy, post_h + 0.22),
            (0.10, D + 0.3, 0.20),
            MATS["corten"],
            coll,
            bevel=0.01,
        )
    # timber roof slats running across
    nslat = 7 if QUICK else 15
    for i in range(nslat):
        sx = cx - W / 2 + 0.15 + i * (W - 0.1) / (nslat - 1)
        box(
            f"perg:slat:{i}",
            (sx, cy, post_h + 0.40),
            (0.07, D + 0.5, 0.10),
            MATS["wood_light"],
            coll,
            bevel=0.01,
        )
    # timber slat bench underneath
    for i in range(4):
        box(
            f"perg:benchtop:{i}",
            (cx, cy - 0.1 + i * 0.13, 0.5),
            (W - 1.2, 0.10, 0.06),
            MATS["wood"],
            coll,
            bevel=0.01,
        )
    for i, dx in enumerate((-(W / 2 - 0.9), (W / 2 - 0.9))):
        box(
            f"perg:benchleg:{i}",
            (cx + dx, cy + 0.1, 0.25),
            (0.10, 0.5, 0.5),
            MATS["corten"],
            coll,
            bevel=0.01,
        )
    return {"center": (cx, cy, post_h * 0.6), "name": "hero_pergola"}


# --------------------------------------------------------------------------- #
# Ground
# --------------------------------------------------------------------------- #
def build_ground(coll):
    box(
        "plaza",
        (0.0, 5.0, -0.02),
        (34.0, 30.0, 0.04),
        MATS["concrete"],
        coll,
        bevel=0.0,
    )
    box("lawn", (0.0, 5.0, -0.06), (140.0, 140.0, 0.04), MATS["grass"], coll, bevel=0.0)


# --------------------------------------------------------------------------- #
# World / camera / render
# --------------------------------------------------------------------------- #
def build_world():
    world = bpy.data.worlds.new("sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(50)
    sky.sun_rotation = math.radians(-42)
    sky.altitude = 250
    sky.air_density = 1.0
    sky.dust_density = 0.55
    bg.inputs["Strength"].default_value = 0.6
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_lights():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 40))
    sun = bpy.context.object
    sun.data.energy = 2.6
    sun.data.angle = math.radians(3.2)
    sun.data.color = (1.0, 0.96, 0.88)
    sun.rotation_euler = (math.radians(54), 0, math.radians(-42))
    loc = Vector((6.0, -12.0, 9.0))
    bpy.ops.object.light_add(type="AREA", location=loc)
    sb = bpy.context.object
    sb.data.shape = "RECTANGLE"
    sb.data.size = 16.0
    sb.data.size_y = 8.0
    sb.data.energy = 2600.0
    sb.data.color = (0.9, 0.94, 1.0)
    aim = Vector((0.0, 5.0, 1.4))
    sb.rotation_euler = (aim - loc).to_track_quat("-Z", "Y").to_euler()


def make_camera(name, loc, look_at, lens=50, fstop=None):
    cam = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(obj)
    cam.lens = lens
    cam.sensor_width = 36
    obj.location = loc
    obj.rotation_euler = (
        (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    if fstop:
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
        focus = bpy.data.objects.new(f"{name}_focus", None)
        bpy.context.scene.collection.objects.link(focus)
        focus.location = look_at
        cam.dof.focus_object = focus
    return obj


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
                gpu_on = False
                for d in devs:
                    d.use = "CPU" not in d.name.upper()
                    gpu_on = gpu_on or d.use
                if gpu_on:
                    chosen = backend
                    break
        except Exception:
            continue
    print(f"[sculpt] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 16  # mirror knot wants plenty of bounces
    scene.cycles.glossy_bounces = 12
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    bpy.context.preferences.filepaths.temporary_directory = str(TMP_DIR)
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.view_settings.exposure = -1.4
    print(
        f"[sculpt] view={scene.view_settings.view_transform} "
        f"look={scene.view_settings.look} exposure={scene.view_settings.exposure}"
    )


def render_still(cam, path, samples=240, res=(1920, 1080)):
    scene = bpy.context.scene
    scene.camera = cam
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(1)
    scene.render.filepath = str(path)
    print(f"[sculpt] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
# sculpture row (y=0), pavilion row (y=10.5)
POS = {
    "mirror_knot": (-7.5, 0.0),
    "bronze_figure": (0.0, 0.0),
    "red_stabile": (7.5, 0.0),
    "bandstand": (-9.0, 10.5),
    "chinese_pavilion": (0.5, 10.5),
    "pergola": (9.0, 10.5),
}


def main():
    reset_scene()
    build_materials()

    ground_c = add_collection("sc_ground")
    art_c = add_collection("sc_art")

    build_ground(ground_c)
    info = {}
    info["mirror_knot"] = build_mirror_knot(*POS["mirror_knot"], art_c)
    info["bronze_figure"] = build_bronze_figure(*POS["bronze_figure"], art_c)
    info["red_stabile"] = build_red_stabile(*POS["red_stabile"], art_c)
    info["bandstand"] = build_bandstand(*POS["bandstand"], art_c)
    info["chinese_pavilion"] = build_chinese_pavilion(*POS["chinese_pavilion"], art_c)
    info["pergola"] = build_pergola(*POS["pergola"], art_c)

    build_world()
    add_lights()
    configure_cycles()

    # group / overview cameras
    overview = make_camera("overview", (0.0, -17.0, 12.5), (0.0, 5.5, 1.6), lens=30)
    sculpt_cam = make_camera(
        "sculptures", (0.0, -9.5, 3.4), (0.0, 0.2, 1.3), lens=30, fstop=8.0
    )
    pav_cam = make_camera(
        "pavilions", (0.0, 24.5, 6.6), (0.0, 10.5, 2.9), lens=28, fstop=9.0
    )

    bpy.context.scene.camera = overview
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    if QUICK:
        render_still(
            overview, OUTPUT_DIR / "quick_overview.png", samples=48, res=(1280, 720)
        )
        render_still(
            sculpt_cam, OUTPUT_DIR / "quick_sculptures.png", samples=48, res=(1280, 720)
        )
        render_still(
            pav_cam, OUTPUT_DIR / "quick_pavilions.png", samples=48, res=(1280, 720)
        )
        print("[sculpt] QUICK done ->", OUTPUT_DIR)
        return

    render_still(overview, OUTPUT_DIR / "overview.png", samples=300)
    render_still(sculpt_cam, OUTPUT_DIR / "sculptures.png", samples=280)
    render_still(pav_cam, OUTPUT_DIR / "pavilions.png", samples=280)

    # per-asset hero close-ups (offset, look, lens, fstop)
    heroes = {
        "mirror_knot": ((-11.0, -4.5, 2.6), (-7.5, 0.0, 1.7), 42, 5.0),
        "bronze_figure": ((-2.4, -5.6, 1.8), (0.0, 0.0, 1.05), 38, 5.6),
        "red_stabile": ((13.2, -6.4, 3.4), (7.5, 0.1, 1.5), 34, 6.0),
        "bandstand": ((-14.5, 3.5, 3.6), (-9.0, 10.5, 2.2), 34, 6.0),
        "chinese_pavilion": ((-2.5, -1.5, 5.2), (0.5, 10.5, 3.4), 24, 9.0),
        "pergola": ((14.0, 4.5, 3.0), (9.0, 10.5, 1.8), 38, 6.0),
    }
    for key, (loc, look, lens, fstop) in heroes.items():
        cam = make_camera(f"cam_{key}", loc, look, lens=lens, fstop=fstop)
        render_still(cam, OUTPUT_DIR / f"{info[key]['name']}.png", samples=260)

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[sculpt] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
