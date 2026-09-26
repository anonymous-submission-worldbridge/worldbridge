"""Photorealistic procedural RESIDENTIAL COMPOUND WALL (urban_v3_fence2).

Improves on urban_v3_fence:
  1. Instead of three short straight segments, this builds ONE large *closed*
     rectangular perimeter that fully encloses a plot (NO house inside) - a
     brick boundary wall with regularly spaced brick piers, taller corner &
     gate piers, a concrete coping, and a double-leaf wrought-iron entrance
     gate on the street side.
  2. A far more detailed, image-level-real brick material:
       - per-brick two-tone brindling (Brick node Color1/Color2, random bias)
       - large-scale kiln "patch" tonal drift
       - rising-damp darkening near the ground (world-Z reference)
       - vertical water-runoff staining streaks
       - grime settled in the mortar joints (AO)
       - recessed mortar + per-brick face unevenness + fine grit in the normal
       - a projecting plinth course at the base and a dentil/soldier band under
         the coping for real shadow lines.

Realism levers unchanged from the v3 assets: weathered PBR, a split-sky city
HDRI (bright to camera, weak for lighting) so the sun throws crisp directional
shadows, AgX + glare, GPU/OPTIX.

Run:
  TMPDIR=${WORLDBRIDGE_EXTERNAL}/tmp ${BLENDER_BIN} -b \
      --python scripts/generate_urban_v3_fence2.py
Env:
  V3_SPP=N   sample override (default 448)
  F_ENV=city|courtyard|sunset|sunrise   HDRI (default city)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence2):
  fence.blend
  fence_overview.png   3/4 aerial of the whole enclosure + gate
  fence_gate.png       the wrought-iron entrance gate + gate piers
  fence_brick.png      close detail of a wall + pier (brick realism)
  fence_corner.png     a corner pier where two runs meet
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
from mathutils import Vector

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence2")
SCENE_PATH = OUTPUT_DIR / "fence.blend"
OVERVIEW_PATH = OUTPUT_DIR / "fence_overview.png"
GATE_PATH = OUTPUT_DIR / "fence_gate.png"
BRICK_PATH = OUTPUT_DIR / "fence_brick.png"
CORNER_PATH = OUTPUT_DIR / "fence_corner.png"

BLENDER_ROOT = Path(f"{_wb_BLENDER_RESOURCES}")
HDRI_DIR = BLENDER_ROOT / "datafiles/studiolights/world"

# --------------------------------------------------------------------------- #
# Compound footprint (a closed rectangle enclosing an empty plot).
# Street / camera side is -Y; the front wall (Y=0) carries the gate.
# --------------------------------------------------------------------------- #
HALF_X = 9.0  # plot half-width  -> 18 m wide
FRONT_Y = 0.0
BACK_Y = 13.0  # plot depth 13 m
WALL_H = 1.70
WALL_T = 0.24
FOOT_H = 0.14
PIER_W = 0.42
PIER_H = 1.92
CORNER_W = 0.52
CORNER_H = 2.04
GATE_CLEAR = 3.80  # clear opening between the two gate piers
GPIER_W = 0.54
GPIER_H = 2.18
GATE_PX = GATE_CLEAR / 2 + GPIER_W / 2  # gate-pier centre X


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
# Material node helpers
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
    """A weathered, textured PBR surface: workhorse for metal/paint/concrete."""
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


def mat_brick_real(
    name,
    *,
    c1=(0.235, 0.070, 0.048),
    c2=(0.135, 0.052, 0.042),
    c3=(0.335, 0.120, 0.072),
    c4=(0.085, 0.038, 0.034),
    mortar=(0.335, 0.315, 0.285),
    bw=0.235,
    rh=0.076,
    mortar_sz=0.009,
    rough=0.90,
):
    """Image-level brick masonry.

    Base pattern uses the Brick node in OBJECT space (rotated 90 deg about X so
    world-up maps to the node's row axis -> horizontal courses on every upright
    face regardless of how the wall object is oriented).  Realism layers:
      * the brick-grid coordinates are warped by a fine noise so joints wander
        and brick outlines read irregular instead of a perfect CG grid,
      * two randomly-biased brick tones + a per-brick tonal spread noise +
        occasional very-dark "burnt header" bricks + soft large kiln patches,
      * rising-damp darkening keyed to WORLD Z toward the ground plane,
      * blotchy weathering grime + grime settled in the mortar joints (AO),
      * a matte finish (high roughness, low specular).
    The normal combines a deep recessed-mortar bump, per-brick face unevenness
    and fine grit.
    """
    m, nt, b = _principled(name)

    # ---- pattern coordinates: object space, rotated so Z -> rows ----
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    # warp the grid so mortar joints wander and brick edges look hand-laid
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 12.0
    warp.inputs["Detail"].default_value = 2.0
    warp_s = nt.nodes.new("ShaderNodeVectorMath")
    warp_s.operation = "SCALE"
    nt.links.new(warp.outputs["Color"], warp_s.inputs[0])
    warp_s.inputs["Scale"].default_value = 0.010
    addv = nt.nodes.new("ShaderNodeVectorMath")
    addv.operation = "ADD"
    nt.links.new(mp.outputs["Vector"], addv.inputs[0])
    nt.links.new(warp_s.outputs["Vector"], addv.inputs[1])

    tb = nt.nodes.new("ShaderNodeTexBrick")
    nt.links.new(addv.outputs["Vector"], tb.inputs["Vector"])
    tb.offset = 0.5
    tb.offset_frequency = 2
    tb.squash = 1.0
    tb.squash_frequency = 2
    tb.inputs["Color1"].default_value = (c1[0], c1[1], c1[2], 1.0)
    tb.inputs["Color2"].default_value = (c2[0], c2[1], c2[2], 1.0)
    tb.inputs["Mortar"].default_value = (mortar[0], mortar[1], mortar[2], 1.0)
    tb.inputs["Scale"].default_value = 1.0
    tb.inputs["Mortar Size"].default_value = mortar_sz
    tb.inputs["Mortar Smooth"].default_value = 0.05
    tb.inputs["Bias"].default_value = 0.0
    tb.inputs["Brick Width"].default_value = bw
    tb.inputs["Row Height"].default_value = rh

    # ---- per-brick tonal spread (a noise sized ~one cell per brick) ----
    pb = nt.nodes.new("ShaderNodeTexNoise")
    pb.inputs["Scale"].default_value = 4.6
    pb.inputs["Detail"].default_value = 1.0
    pbr = _ramp(nt, [(0.0, (0.62, 0.62, 0.62)), (1.0, (1.18, 1.18, 1.18))])
    nt.links.new(pb.outputs["Fac"], pbr.inputs["Fac"])
    spread = nt.nodes.new("ShaderNodeMixRGB")
    spread.blend_type = "MULTIPLY"
    spread.inputs["Fac"].default_value = 1.0
    nt.links.new(tb.outputs["Color"], spread.inputs["Color1"])
    nt.links.new(pbr.outputs["Color"], spread.inputs["Color2"])
    cur = spread.outputs["Color"]

    # ---- occasional very-dark burnt-header bricks ----
    bh = nt.nodes.new("ShaderNodeTexNoise")
    bh.inputs["Scale"].default_value = 4.6
    bh.inputs["Detail"].default_value = 1.0
    bhr = _ramp(nt, [(0.0, (0, 0, 0)), (0.80, (0, 0, 0)), (0.88, (1, 1, 1))])
    nt.links.new(bh.outputs["Fac"], bhr.inputs["Fac"])
    bhmix = nt.nodes.new("ShaderNodeMixRGB")
    bhmix.blend_type = "MIX"
    nt.links.new(cur, bhmix.inputs["Color1"])
    bhmix.inputs["Color2"].default_value = (c4[0], c4[1], c4[2], 1.0)
    nt.links.new(bhr.outputs["Color"], bhmix.inputs["Fac"])
    cur = bhmix.outputs["Color"]

    # ---- soft large kiln patches (a third warm clay tone) ----
    patch = nt.nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = 1.5
    patch.inputs["Detail"].default_value = 2.0
    patch_r = _ramp(nt, [(0.40, (0, 0, 0)), (0.66, (1, 1, 1))])
    nt.links.new(patch.outputs["Fac"], patch_r.inputs["Fac"])
    mix3 = nt.nodes.new("ShaderNodeMixRGB")
    mix3.blend_type = "MIX"
    mix3.inputs["Fac"].default_value = 0.35
    nt.links.new(cur, mix3.inputs["Color1"])
    mix3.inputs["Color2"].default_value = (c3[0], c3[1], c3[2], 1.0)
    # only tint where the patch mask is high
    pmul = nt.nodes.new("ShaderNodeMath")
    pmul.operation = "MULTIPLY"
    pmul.inputs[1].default_value = 0.5
    nt.links.new(patch_r.outputs["Color"], pmul.inputs[0])
    nt.links.new(pmul.outputs["Value"], mix3.inputs["Fac"])
    cur = mix3.outputs["Color"]

    # ---- rising damp toward the ground (WORLD Z) ----
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    damp = nt.nodes.new("ShaderNodeMapRange")
    damp.inputs["From Min"].default_value = 0.10
    damp.inputs["From Max"].default_value = 0.68
    damp.inputs["To Min"].default_value = 1.0
    damp.inputs["To Max"].default_value = 0.0
    damp.clamp = True
    nt.links.new(sep.outputs["Z"], damp.inputs["Value"])
    dnoise = nt.nodes.new("ShaderNodeTexNoise")
    dnoise.inputs["Scale"].default_value = 5.0
    dmul = nt.nodes.new("ShaderNodeMath")
    dmul.operation = "MULTIPLY"
    nt.links.new(damp.outputs["Result"], dmul.inputs[0])
    nt.links.new(dnoise.outputs["Fac"], dmul.inputs[1])
    dmul2 = nt.nodes.new("ShaderNodeMath")
    dmul2.operation = "MULTIPLY"
    dmul2.inputs[1].default_value = 0.6
    nt.links.new(dmul.outputs["Value"], dmul2.inputs[0])
    dmix = nt.nodes.new("ShaderNodeMixRGB")
    dmix.blend_type = "MULTIPLY"
    nt.links.new(cur, dmix.inputs["Color1"])
    dmix.inputs["Color2"].default_value = (0.42, 0.40, 0.36, 1.0)
    nt.links.new(dmul2.outputs["Value"], dmix.inputs["Fac"])
    cur = dmix.outputs["Color"]

    # ---- blotchy weathering grime (isotropic, not streaky) ----
    blot = nt.nodes.new("ShaderNodeTexNoise")
    blot.inputs["Scale"].default_value = 3.2
    blot.inputs["Detail"].default_value = 4.0
    blotr = _ramp(nt, [(0.45, (0, 0, 0)), (0.72, (1, 1, 1))])
    nt.links.new(blot.outputs["Fac"], blotr.inputs["Fac"])
    blotmix = nt.nodes.new("ShaderNodeMixRGB")
    blotmix.blend_type = "MULTIPLY"
    blotmix.inputs["Color2"].default_value = (0.6, 0.58, 0.55, 1.0)
    bstr = nt.nodes.new("ShaderNodeMath")
    bstr.operation = "MULTIPLY"
    bstr.inputs[1].default_value = 0.30
    nt.links.new(blotr.outputs["Color"], bstr.inputs[0])
    nt.links.new(cur, blotmix.inputs["Color1"])
    nt.links.new(bstr.outputs["Value"], blotmix.inputs["Fac"])
    cur = blotmix.outputs["Color"]

    # ---- grime settled in the mortar joints ----
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.05
    md = nt.nodes.new("ShaderNodeMixRGB")
    md.blend_type = "MULTIPLY"
    md.inputs["Fac"].default_value = 0.28
    nt.links.new(cur, md.inputs["Color1"])
    nt.links.new(ao.outputs["Color"], md.inputs["Color2"])
    nt.links.new(md.outputs["Color"], b.inputs["Base Color"])

    # ---- matte finish: high roughness w/ noise variation, low specular ----
    _set(b, "Specular IOR Level", 0.22)
    rn = nt.nodes.new("ShaderNodeTexNoise")
    rn.inputs["Scale"].default_value = 9.0
    rr = _ramp(nt, [(0.0, (rough - 0.10,) * 3), (1.0, (min(1.0, rough + 0.05),) * 3)])
    nt.links.new(rn.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], b.inputs["Roughness"])

    # ---- normal: deep recessed mortar + per-brick unevenness + grit ----
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.75
    bmp.inputs["Distance"].default_value = 0.03
    nt.links.new(tb.outputs["Fac"], bmp.inputs["Height"])
    face = nt.nodes.new("ShaderNodeTexNoise")
    face.inputs["Scale"].default_value = 14.0
    face.inputs["Detail"].default_value = 2.0
    bmp2 = nt.nodes.new("ShaderNodeBump")
    bmp2.inputs["Strength"].default_value = 0.20
    bmp2.inputs["Distance"].default_value = 0.012
    nt.links.new(face.outputs["Fac"], bmp2.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bmp2.inputs["Normal"])
    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 120.0
    bmp3 = nt.nodes.new("ShaderNodeBump")
    bmp3.inputs["Strength"].default_value = 0.11
    nt.links.new(grit.outputs["Fac"], bmp3.inputs["Height"])
    nt.links.new(bmp2.outputs["Normal"], bmp3.inputs["Normal"])
    nt.links.new(bmp3.outputs["Normal"], b.inputs["Normal"])

    _set(b, "Roughness", rough)
    return m


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


def torus(name, loc, R, r, mat, coll, major=32, minor=12, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        location=loc,
        major_radius=R,
        minor_radius=r,
        major_segments=major,
        minor_segments=minor,
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    smooth(o)
    return link_to(o, coll)


def pyramid(
    name, loc, base, height, mat, coll, verts=4, rot=(0, 0, math.radians(45)), bevel=0.0
):
    bpy.ops.mesh.primitive_cone_add(
        vertices=verts, radius1=base, radius2=0.0, depth=height, location=loc
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    if mat:
        o.data.materials.append(mat)
    _bevel(o, bevel)
    return link_to(o, coll)


def ball(name, loc, r, mat, coll, squash=1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (1.0, 1.0, squash)
    if mat:
        o.data.materials.append(mat)
    smooth(o)
    return link_to(o, coll)


# --------------------------------------------------------------------------- #
# Materials registry
# --------------------------------------------------------------------------- #
M = {}


def build_materials():
    M["brick"] = mat_brick_real("f_brick")
    # cast concrete for copings / caps / curbs / string course / bands
    M["concrete"] = mat_surface(
        "f_concrete",
        (0.585, 0.575, 0.55),
        base_rough=0.82,
        rough_var=0.10,
        rough_scale=4.0,
        bump=0.15,
        bump_scale=24,
        dirt=0.36,
        ao_dist=0.45,
    )
    M["concrete_dk"] = mat_surface(
        "f_concrete_dk",
        (0.46, 0.455, 0.44),
        base_rough=0.86,
        rough_var=0.10,
        rough_scale=3.4,
        bump=0.18,
        bump_scale=18,
        dirt=0.5,
        ao_dist=0.6,
    )
    # satin-black wrought iron (painted metal) for the gate
    M["iron"] = mat_surface(
        "f_iron",
        (0.021, 0.021, 0.024),
        metallic=0.7,
        base_rough=0.36,
        rough_var=0.08,
        bump=0.05,
        bump_scale=150,
        wear=0.08,
        wear_color=(0.11, 0.11, 0.12),
        dirt=0.26,
        coat=0.07,
    )
    # ground
    M["grass"] = mat_surface(
        "f_grass",
        (0.052, 0.130, 0.033),
        base_rough=0.95,
        rough_var=0.20,
        rough_scale=14.0,
        bump=0.7,
        bump_scale=300,
        dirt=0.42,
        ao_dist=0.5,
    )
    M["hedge"] = mat_surface(
        "f_hedge",
        (0.050, 0.160, 0.036),
        base_rough=0.95,
        rough_var=0.14,
        rough_scale=9.0,
        bump=0.85,
        bump_scale=280,
        dirt=0.4,
        ao_dist=0.4,
    )
    M["pave"] = mat_surface(
        "f_pave",
        (0.235, 0.23, 0.222),
        base_rough=0.70,
        rough_var=0.20,
        rough_scale=3.2,
        bump=0.22,
        bump_scale=16,
        dirt=0.55,
        ao_dist=0.9,
        specular=0.28,
    )
    M["pave_seam"] = mat_surface(
        "f_paveseam", (0.07, 0.07, 0.072), base_rough=0.9, dirt=0.6
    )
    M["drive"] = mat_surface(
        "f_drive",
        (0.115, 0.112, 0.108),
        base_rough=0.72,
        rough_var=0.14,
        rough_scale=3.0,
        bump=0.16,
        bump_scale=14,
        dirt=0.45,
        ao_dist=0.7,
        specular=0.28,
    )
    print("[fence2] materials:", len(M))


# --------------------------------------------------------------------------- #
# Wall + pier builders (a wall run is modelled with local X = length so the
# brick material's object-space mapping stays consistent under Z rotation)
# --------------------------------------------------------------------------- #
def wall_run(name, coll, cx, cy, length, axis):
    """A brick wall run with foundation curb, projecting plinth course, a
    string-course band, a dentil/soldier band and a concrete coping cap.
    axis 'X' runs along world X, 'Y' runs along world Y."""
    rot = (0, 0, 0) if axis == "X" else (0, 0, math.radians(90))
    z0 = FOOT_H
    # foundation curb (slightly wider than the wall)
    cube(
        f"{name}:foot",
        (cx, cy, FOOT_H / 2),
        (length + 0.02, WALL_T + 0.12, FOOT_H),
        M["concrete_dk"],
        coll,
        rot=rot,
        bevel=0.01,
    )
    # projecting plinth course (bottom ~3 brick courses, a touch proud)
    plinth_h = 0.26
    cube(
        f"{name}:plinth",
        (cx, cy, z0 + plinth_h / 2),
        (length, WALL_T + 0.05, plinth_h),
        M["brick"],
        coll,
        rot=rot,
        bevel=0.006,
    )
    # main brick wall
    cube(
        f"{name}:wall",
        (cx, cy, z0 + WALL_H / 2),
        (length, WALL_T, WALL_H),
        M["brick"],
        coll,
        rot=rot,
        bevel=0.005,
    )
    # concrete string-course band ~ 62% up
    band_z = z0 + WALL_H * 0.60
    cube(
        f"{name}:band",
        (cx, cy, band_z),
        (length + 0.01, WALL_T + 0.055, 0.06),
        M["concrete"],
        coll,
        rot=rot,
        bevel=0.008,
    )
    # dentil / soldier band just under the coping (proud brick course)
    dz = z0 + WALL_H - 0.10
    cube(
        f"{name}:dentil",
        (cx, cy, dz),
        (length, WALL_T + 0.06, 0.12),
        M["brick"],
        coll,
        rot=rot,
        bevel=0.005,
    )
    # concrete coping cap
    cube(
        f"{name}:coping",
        (cx, cy, z0 + WALL_H + 0.05),
        (length + 0.02, WALL_T + 0.14, 0.10),
        M["concrete"],
        coll,
        rot=rot,
        bevel=0.014,
    )


def brick_pier(name, coll, px, py, w=PIER_W, h=PIER_H, ball_top=False):
    cube(
        f"{name}:col",
        (px, py, FOOT_H + h / 2),
        (w, w, h),
        M["brick"],
        coll,
        bevel=0.008,
    )
    # slim concrete banding near the base of the pier
    cube(
        f"{name}:base",
        (px, py, FOOT_H + 0.10),
        (w + 0.06, w + 0.06, 0.10),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    cube(
        f"{name}:cap",
        (px, py, FOOT_H + h + 0.045),
        (w + 0.16, w + 0.16, 0.09),
        M["concrete"],
        coll,
        bevel=0.014,
    )
    pyramid(
        f"{name}:pyr",
        (px, py, FOOT_H + h + 0.155),
        (w + 0.10) / 2,
        0.18,
        M["concrete"],
        coll,
        bevel=0.004,
    )
    if ball_top:
        ball(f"{name}:ball", (px, py, FOOT_H + h + 0.30), 0.075, M["concrete"], coll)


# --------------------------------------------------------------------------- #
# Wrought-iron double-leaf entrance gate (fills the clear opening at the front)
# --------------------------------------------------------------------------- #
def gate_panel(name, coll, gx0, gx1):
    """One gate leaf between gx0..gx1 at the front (Y=0): frame, vertical bars
    with spear finials, a mid rail and a ring-scroll row."""
    y = 0.0
    w = gx1 - gx0
    gcx = (gx0 + gx1) / 2
    z_bot = 0.12
    z_top = 1.60
    stile = 0.055
    # frame: two stiles + top & bottom rails
    cube(
        f"{name}:stileL",
        (gx0 + stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:stileR",
        (gx1 - stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:railB",
        (gcx, y, z_bot + 0.03),
        (w, 0.055, 0.07),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:railT",
        (gcx, y, z_top - 0.03),
        (w, 0.055, 0.07),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:railM",
        (gcx, y, z_bot + (z_top - z_bot) * 0.42),
        (w, 0.04, 0.045),
        M["iron"],
        coll,
        bevel=0.004,
    )
    # vertical bars with spear finials above the top rail
    bar_t = 0.022
    n = max(4, int(w / 0.12))
    step = w / n
    for j in range(n + 1):
        bx = gx0 + j * step
        if bx <= gx0 + stile or bx >= gx1 - stile:
            continue
        cube(
            f"{name}:bar:{j}",
            (bx, y, (z_bot + z_top) / 2 + 0.02),
            (bar_t, bar_t, z_top - z_bot + 0.24),
            M["iron"],
            coll,
            bevel=0.002,
        )
        pyramid(
            f"{name}:spear:{j}",
            (bx, y, z_top + 0.22),
            bar_t * 1.8,
            0.16,
            M["iron"],
            coll,
            verts=4,
            bevel=0.0,
        )
    # ring-scroll row centred in the lower third
    n_ring = max(2, int(w / 0.55))
    rstep = w / n_ring
    for j in range(n_ring):
        rx = gx0 + (j + 0.5) * rstep
        torus(
            f"{name}:ring:{j}",
            (rx, y, z_bot + (z_top - z_bot) * 0.30),
            0.085,
            0.015,
            M["iron"],
            coll,
            major=24,
            minor=8,
            rot=(math.radians(90), 0, 0),
        )


def build_gate(coll):
    # two leaves meeting at X=0 with a small central gap
    gap = 0.03
    gate_panel("G:L", coll, -GATE_CLEAR / 2, -gap)
    gate_panel("G:R", coll, gap, GATE_CLEAR / 2)
    # central meeting stiles
    for sx in (-0.05, 0.05):
        cube(
            f"G:centre:{sx:.2f}",
            (sx, 0.0, (0.12 + 1.60) / 2),
            (0.05, 0.06, 1.60 - 0.12),
            M["iron"],
            coll,
            bevel=0.004,
        )


# --------------------------------------------------------------------------- #
# Assemble the closed compound perimeter
# --------------------------------------------------------------------------- #
def build_compound(coll):
    # -------- corner + gate + intermediate pier positions --------
    corners = [
        (-HALF_X, FRONT_Y),
        (HALF_X, FRONT_Y),
        (-HALF_X, BACK_Y),
        (HALF_X, BACK_Y),
    ]
    for i, (px, py) in enumerate(corners):
        brick_pier(f"P:corner:{i}", coll, px, py, w=CORNER_W, h=CORNER_H, ball_top=True)
    # gate piers (front, flanking the opening) - taller, with ball finials
    brick_pier("P:gateL", coll, -GATE_PX, FRONT_Y, w=GPIER_W, h=GPIER_H, ball_top=True)
    brick_pier("P:gateR", coll, GATE_PX, FRONT_Y, w=GPIER_W, h=GPIER_H, ball_top=True)

    # -------- front runs (corner -> gate pier), left & right of the gate ----
    fl_cx = (-HALF_X + -GATE_PX) / 2
    fl_len = (-GATE_PX) - (-HALF_X)
    wall_run("W:frontL", coll, fl_cx, FRONT_Y, fl_len, "X")
    brick_pier("P:frontL", coll, fl_cx, FRONT_Y)  # one intermediate pier
    fr_cx = (HALF_X + GATE_PX) / 2
    fr_len = HALF_X - GATE_PX
    wall_run("W:frontR", coll, fr_cx, FRONT_Y, fr_len, "X")
    brick_pier("P:frontR", coll, fr_cx, FRONT_Y)

    # -------- back run (full width) --------
    wall_run("W:back", coll, 0.0, BACK_Y, 2 * HALF_X, "X")
    for bx in (-6.0, -3.0, 0.0, 3.0, 6.0):
        brick_pier(f"P:back:{bx:.0f}", coll, bx, BACK_Y)

    # -------- side runs (front -> back) --------
    side_len = BACK_Y - FRONT_Y
    side_cy = (FRONT_Y + BACK_Y) / 2
    for sx, tag in ((-HALF_X, "L"), (HALF_X, "R")):
        wall_run(f"W:side{tag}", coll, sx, side_cy, side_len, "Y")
        for sy in (3.25, 6.5, 9.75):
            brick_pier(f"P:side{tag}:{sy:.1f}", coll, sx, sy)

    # -------- entrance gate --------
    build_gate(coll)


# --------------------------------------------------------------------------- #
# Ground + garden context
# --------------------------------------------------------------------------- #
def build_ground(coll):
    # broad outer pavement (street / neighbourhood)
    cube("gnd:pave", (0.0, 4.0, -0.04), (60, 60, 0.06), M["pave"], coll, bevel=0)
    # paving seams on the street side only (in front of the compound)
    step = 1.5
    for i in range(-8, 9):
        cube(
            f"gnd:sx:{i}",
            (i * step, -4.0, -0.006),
            (0.05, 9.0, 0.010),
            M["pave_seam"],
            coll,
            bevel=0,
        )
    for j in range(0, 6):
        cube(
            f"gnd:sy:{j}",
            (0.0, -0.6 - j * 1.5, -0.006),
            (26, 0.05, 0.010),
            M["pave_seam"],
            coll,
            bevel=0,
        )
    # lawn inside the compound
    cube(
        "gnd:lawn",
        (0.0, (FRONT_Y + BACK_Y) / 2, -0.02),
        (2 * HALF_X - 0.10, (BACK_Y - FRONT_Y) - 0.10, 0.05),
        M["grass"],
        coll,
        bevel=0,
    )
    # driveway from the gate into the yard
    cube(
        "gnd:drive",
        (0.0, 4.0, -0.005),
        (GATE_CLEAR - 0.2, 9.0, 0.03),
        M["drive"],
        coll,
        bevel=0,
    )
    # low clipped hedge line just inside along the back wall
    cube(
        "gnd:hedge_back",
        (0.0, BACK_Y - 0.85, 0.55),
        (2 * HALF_X - 1.6, 0.55, 1.05),
        M["hedge"],
        coll,
        bevel=0.22,
    )
    # a couple of shrub balls inside near the gate
    for dx in (-3.0, 3.0):
        ball(f"gnd:bush:{dx:.0f}", (dx, 2.2, 0.62), 0.62, M["hedge"], coll, squash=0.85)


# --------------------------------------------------------------------------- #
# World (split-sky HDRI) + sun + cameras + render
# --------------------------------------------------------------------------- #
def build_world():
    env_name = os.environ.get("F_ENV", "city")
    path = HDRI_DIR / f"{env_name}.exr"
    if not path.exists():
        path = HDRI_DIR / "city.exr"
    world = bpy.data.worlds.new("f_world")
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
    bg_light.inputs["Strength"].default_value = 0.28
    nt.links.new(env.outputs["Color"], bg_cam.inputs["Color"])
    nt.links.new(env.outputs["Color"], bg_light.inputs["Color"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_light.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    print(f"[fence2] HDRI env: {path.name} (split-sky)")


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 8.5
    sun.data.angle = math.radians(1.2)
    sun.data.color = (1.0, 0.94, 0.84)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-54))


def _focus_empty(name, loc):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    return e


def make_camera(name, loc, target, lens=40, fstop=6.3):
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
    glare.threshold = 1.2
    glare.size = 7
    if hasattr(glare, "mix"):
        glare.mix = -0.75
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def configure_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    chosen = None
    for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
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
    print(f"[fence2] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 10
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


def render_still(scene, cam, path, samples=448, res=(1920, 1080)):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    print(f"[fence2] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ground_c = add_collection("f_ground")
    comp_c = add_collection("f_compound")

    build_ground(ground_c)
    build_compound(comp_c)

    build_world()
    add_sun()
    configure_cycles()
    setup_compositor()
    scene = bpy.context.scene

    # 3/4 aerial from outside the front-left corner: shows the gate, the left
    # run receding to the back wall, and the enclosed lawn.
    overview = make_camera(
        "cam_overview", (-15.0, -12.5, 8.2), (1.5, 5.5, 0.9), lens=26, fstop=None
    )
    # entrance gate, near head-on
    cam_gate = make_camera(
        "cam_gate", (0.0, -8.5, 1.95), (0.0, 0.15, 1.35), lens=42, fstop=8.0
    )
    # tight brick detail on the front-left wall + its pier
    fl_cx = (-HALF_X + -GATE_PX) / 2
    cam_brick = make_camera(
        "cam_brick",
        (fl_cx - 2.2, -2.9, 1.35),
        (fl_cx + 0.4, 0.12, 1.0),
        lens=55,
        fstop=5.0,
    )
    # front-left corner pier where the front and left runs meet
    cam_corner = make_camera(
        "cam_corner",
        (-HALF_X - 4.2, -4.0, 2.3),
        (-HALF_X + 0.4, 2.2, 1.0),
        lens=40,
        fstop=6.3,
    )

    scene.camera = overview
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    spp = int(os.environ.get("V3_SPP", 448))
    render_still(scene, overview, OVERVIEW_PATH, samples=max(360, spp - 80))
    render_still(scene, cam_gate, GATE_PATH, samples=spp)
    render_still(scene, cam_brick, BRICK_PATH, samples=spp)
    render_still(scene, cam_corner, CORNER_PATH, samples=spp)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[fence2] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
