"""Three CLOSED procedural boundary enclosures (urban_v3_fence3).

Combines the two earlier fence studies:
  * from urban_v3_fence   -> the three distinct fence STYLES
      A. WROUGHT-IRON villa railing  (cut-stone plinth + piers + black iron)
      B. RED-BRICK privacy wall      (photoreal coursed brick + coping)
      C. MODERN TIMBER-SLAT fence    (charcoal steel posts + wood slats)
  * from urban_v3_fence2  -> each is now a large *closed* rectangular perimeter
      (14 x 14 m) that fully encloses a house-sized plot, with corner piers,
      intermediate piers, a street-side entrance with gate piers and a
      double-leaf gate.  NOTHING is placed inside (empty plot, no house).

This variant is a clean ASSET SHOWCASE: no city HDRI backdrop, no ground grid,
no garden dressing - just the three enclosures on a neutral studio sweep, lit by
a sun for crisp directional shadows + a soft neutral sky for fill.

Run:
  TMPDIR=${WORLDBRIDGE_EXTERNAL}/tmp ${BLENDER_BIN} -b \
      --python scripts/generate_urban_v3_fence3.py
Env:
  V3_SPP=N   sample override (default 448)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence3):
  fence.blend
  fence_overview.png       all three closed enclosures together
  fence_brick.png          the brick enclosure (3/4)
  fence_iron.png           the iron enclosure (3/4)
  fence_slat.png           the slat enclosure (3/4)
  fence_brick_detail.png   close brick realism detail
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


import math
import os
from pathlib import Path

import bpy
from mathutils import Vector

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence3")
SCENE_PATH = OUTPUT_DIR / "fence.blend"
OVERVIEW_PATH = OUTPUT_DIR / "fence_overview.png"
BRICK_PATH = OUTPUT_DIR / "fence_brick.png"
IRON_PATH = OUTPUT_DIR / "fence_iron.png"
SLAT_PATH = OUTPUT_DIR / "fence_slat.png"
BRICK_DETAIL_PATH = OUTPUT_DIR / "fence_brick_detail.png"

# --------------------------------------------------------------------------- #
# Each enclosure is a closed square: front (street / camera) side is -Y = 0,
# back at +Y = BACK; half-width HALF in X.  A centred street entrance carries
# gate piers + a double-leaf gate.
# --------------------------------------------------------------------------- #
HALF = 7.0  # -> 14 m wide
BACK = 14.0  # -> 14 m deep
FOOT_H = 0.14  # brick foundation curb height
WALL_H = 1.70
WALL_T = 0.24
GATE_CLEAR = 3.60  # clear opening between the gate piers

# enclosure centres along X (spaced apart so all three read separately)
BRICK_OX = -26.0
IRON_OX = 0.0
SLAT_OX = 26.0


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


def mat_stone(
    name,
    c1=(0.50, 0.465, 0.40),
    c2=(0.44, 0.41, 0.35),
    mortar=(0.34, 0.32, 0.29),
    bw=0.52,
    rh=0.24,
    mortar_sz=0.020,
    rough=0.84,
    bump=0.40,
):
    """Coursed cut-stone (ashlar) via the Brick texture in OBJECT space, rotated
    90 deg about X so world-up maps to the node's row axis -> horizontal courses
    on every upright face (see the fence-v1 orientation note)."""
    m, nt, b = _principled(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    tb = nt.nodes.new("ShaderNodeTexBrick")
    nt.links.new(mp.outputs["Vector"], tb.inputs["Vector"])
    tb.offset = 0.5
    tb.offset_frequency = 2
    tb.inputs["Color1"].default_value = (c1[0], c1[1], c1[2], 1.0)
    tb.inputs["Color2"].default_value = (c2[0], c2[1], c2[2], 1.0)
    tb.inputs["Mortar"].default_value = (mortar[0], mortar[1], mortar[2], 1.0)
    tb.inputs["Scale"].default_value = 1.0
    tb.inputs["Mortar Size"].default_value = mortar_sz
    tb.inputs["Mortar Smooth"].default_value = 0.12
    tb.inputs["Bias"].default_value = 0.0
    tb.inputs["Brick Width"].default_value = bw
    tb.inputs["Row Height"].default_value = rh
    var = nt.nodes.new("ShaderNodeTexNoise")
    var.inputs["Scale"].default_value = 5.0
    var.inputs["Detail"].default_value = 2.0
    mixv = nt.nodes.new("ShaderNodeMixRGB")
    mixv.blend_type = "MULTIPLY"
    mixv.inputs["Fac"].default_value = 0.32
    nt.links.new(tb.outputs["Color"], mixv.inputs["Color1"])
    nt.links.new(var.outputs["Color"], mixv.inputs["Color2"])
    nt.links.new(mixv.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", rough)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.02
    nt.links.new(tb.outputs["Fac"], bmp.inputs["Height"])
    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 120.0
    bmp2 = nt.nodes.new("ShaderNodeBump")
    bmp2.inputs["Strength"].default_value = 0.10
    nt.links.new(grit.outputs["Fac"], bmp2.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bmp2.inputs["Normal"])
    nt.links.new(bmp2.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_wood(name, long_axis="X", base=(0.40, 0.235, 0.115), dark=(0.22, 0.12, 0.055)):
    """Warm timber slat: wavy grain bands stretched along the slat length."""
    m, nt, b = _principled(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    # compress the length axis so the grain bands run lengthwise
    mp.inputs["Scale"].default_value = (
        (0.45, 7.5, 7.5) if long_axis == "X" else (7.5, 0.45, 7.5)
    )
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = "Z"
    w.inputs["Scale"].default_value = 3.0
    w.inputs["Distortion"].default_value = 11.0
    w.inputs["Detail"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    hi = tuple(min(1.0, x * 1.16 + 0.01) for x in base)
    ramp = _ramp(nt, [(0.0, dark), (0.5, base), (1.0, hi)])
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.44)
    _set(b, ("Coat Weight", "Coat"), 0.10)
    _set(b, "Coat Roughness", 0.25)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.16
    bmp.inputs["Distance"].default_value = 0.006
    nt.links.new(w.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
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
    """Image-level brick masonry (from urban_v3_fence2).  Brick node in OBJECT
    space rotated 90 deg about X -> horizontal courses; the grid coords are
    warped for wandering joints; two brick tones + per-brick spread + dark burnt
    headers + kiln patches; rising-damp toward WORLD Z; blotchy grime + AO joint
    grime; matte finish; recessed-mortar + face + grit normal."""
    m, nt, b = _principled(name)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
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
    pmul = nt.nodes.new("ShaderNodeMath")
    pmul.operation = "MULTIPLY"
    pmul.inputs[1].default_value = 0.5
    nt.links.new(patch_r.outputs["Color"], pmul.inputs[0])
    nt.links.new(pmul.outputs["Value"], mix3.inputs["Fac"])
    cur = mix3.outputs["Color"]

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

    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.05
    md = nt.nodes.new("ShaderNodeMixRGB")
    md.blend_type = "MULTIPLY"
    md.inputs["Fac"].default_value = 0.28
    nt.links.new(cur, md.inputs["Color1"])
    nt.links.new(ao.outputs["Color"], md.inputs["Color2"])
    nt.links.new(md.outputs["Color"], b.inputs["Base Color"])

    _set(b, "Specular IOR Level", 0.22)
    rn = nt.nodes.new("ShaderNodeTexNoise")
    rn.inputs["Scale"].default_value = 9.0
    rr = _ramp(nt, [(0.0, (rough - 0.10,) * 3), (1.0, (min(1.0, rough + 0.05),) * 3)])
    nt.links.new(rn.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], b.inputs["Roughness"])

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


def _pt(axis, t, f):
    """World (x, y) for along-coordinate t on a side whose fixed perpendicular
    coordinate is f.  axis 'X' runs along world X (perp = Y=f); axis 'Y' runs
    along world Y (perp = X=f)."""
    return (t, f) if axis == "X" else (f, t)


def _dims(axis, length, thick, height):
    return (length, thick, height) if axis == "X" else (thick, length, height)


# --------------------------------------------------------------------------- #
# Materials registry
# --------------------------------------------------------------------------- #
M = {}


def build_materials():
    M["brick"] = mat_brick_real("f_brick")
    M["stone"] = mat_stone("f_stone")
    M["wood_x"] = mat_wood("f_wood_x", long_axis="X")
    M["wood_y"] = mat_wood("f_wood_y", long_axis="Y")
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
    M["anthracite"] = mat_surface(
        "f_anthra",
        (0.046, 0.048, 0.052),
        metallic=0.6,
        base_rough=0.44,
        rough_var=0.07,
        bump=0.04,
        bump_scale=170,
        dirt=0.16,
        coat=0.12,
    )
    # neutral studio ground sweep
    M["ground"] = mat_surface(
        "f_ground",
        (0.40, 0.40, 0.42),
        base_rough=0.92,
        rough_var=0.05,
        rough_scale=2.0,
        bump=0.03,
        bump_scale=8,
        dirt=0.10,
        ao_dist=0.6,
        specular=0.25,
    )
    print("[fence3] materials:", len(M))


# --------------------------------------------------------------------------- #
# Piers / posts (one per style)
# --------------------------------------------------------------------------- #
def brick_pier(name, coll, px, py, w, h, ball_top=False):
    cube(
        f"{name}:col",
        (px, py, FOOT_H + h / 2),
        (w, w, h),
        M["brick"],
        coll,
        bevel=0.008,
    )
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


def stone_pier(name, coll, px, py, w, h, ball_top=False):
    cube(
        f"{name}:col", (px, py, h / 2), (w, w + 0.04, h), M["stone"], coll, bevel=0.014
    )
    cube(
        f"{name}:cap",
        (px, py, h + 0.035),
        (w + 0.12, w + 0.14, 0.07),
        M["concrete"],
        coll,
        bevel=0.012,
    )
    pyramid(
        f"{name}:pyr",
        (px, py, h + 0.135),
        (w + 0.08) / 2,
        0.16,
        M["concrete"],
        coll,
        bevel=0.004,
    )
    if ball_top:
        ball(f"{name}:ball", (px, py, h + 0.275), 0.058, M["concrete"], coll)


def steel_post(name, coll, px, py, w, h, ball_top=False):
    curb_h = 0.16
    cube(
        f"{name}:post",
        (px, py, curb_h + h / 2),
        (w, w, h),
        M["anthracite"],
        coll,
        bevel=0.006,
    )
    cube(
        f"{name}:cap",
        (px, py, curb_h + h + 0.012),
        (w + 0.02, w + 0.02, 0.024),
        M["anthracite"],
        coll,
        bevel=0.004,
    )


def place_pier(style, name, coll, px, py, w, h, ball_top=False):
    if style == "brick":
        brick_pier(name, coll, px, py, w, h, ball_top)
    elif style == "iron":
        stone_pier(name, coll, px, py, w, h, ball_top)
    else:
        steel_post(name, coll, px, py, w, h, ball_top)


# --------------------------------------------------------------------------- #
# Side runs (one per style)
# --------------------------------------------------------------------------- #
def brick_run(name, coll, cx, cy, length, axis):
    """Brick wall run: foot curb + projecting plinth + main wall + string course
    + dentil band + concrete coping (piers are placed separately on top)."""
    rot = (0, 0, 0) if axis == "X" else (0, 0, math.radians(90))
    z0 = FOOT_H
    cube(
        f"{name}:foot",
        (cx, cy, FOOT_H / 2),
        (length + 0.02, WALL_T + 0.12, FOOT_H),
        M["concrete_dk"],
        coll,
        rot=rot,
        bevel=0.01,
    )
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
    cube(
        f"{name}:wall",
        (cx, cy, z0 + WALL_H / 2),
        (length, WALL_T, WALL_H),
        M["brick"],
        coll,
        rot=rot,
        bevel=0.005,
    )
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
    cube(
        f"{name}:coping",
        (cx, cy, z0 + WALL_H + 0.05),
        (length + 0.02, WALL_T + 0.14, 0.10),
        M["concrete"],
        coll,
        rot=rot,
        bevel=0.014,
    )


def iron_run(name, coll, axis, t0, t1, f, pos):
    """Iron villa railing run: a low continuous stone plinth + concrete cap,
    then satin-black iron infill (rails, balusters w/ spear finials, ring row)
    filling each bay between the posts listed in `pos`."""
    length = t1 - t0
    tc = (t0 + t1) / 2
    plinth_h = 0.46
    plinth_t = 0.20
    cube(
        f"{name}:plinth",
        (*_pt(axis, tc, f), plinth_h / 2),
        _dims(axis, length, plinth_t, plinth_h),
        M["stone"],
        coll,
        bevel=0.012,
    )
    cube(
        f"{name}:plinthcap",
        (*_pt(axis, tc, f), plinth_h + 0.02),
        _dims(axis, length, plinth_t + 0.04, 0.05),
        M["concrete"],
        coll,
        bevel=0.01,
    )

    rail_bot = plinth_h + 0.06
    rail_top = 1.46
    bar_t = 0.024
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    for k in range(len(pos) - 1):
        a = pos[k] + 0.12
        bcx = (pos[k] + pos[k + 1]) / 2
        blen = (pos[k + 1] - 0.12) - a
        if blen <= 0.05:
            continue
        cube(
            f"{name}:rb:{k}",
            (*_pt(axis, bcx, f), rail_bot),
            _dims(axis, blen, 0.05, 0.05),
            M["iron"],
            coll,
            bevel=0.006,
        )
        cube(
            f"{name}:rt:{k}",
            (*_pt(axis, bcx, f), rail_top),
            _dims(axis, blen, 0.05, 0.06),
            M["iron"],
            coll,
            bevel=0.006,
        )
        cube(
            f"{name}:rm:{k}",
            (*_pt(axis, bcx, f), rail_top - 0.30),
            _dims(axis, blen, 0.035, 0.035),
            M["iron"],
            coll,
            bevel=0.005,
        )
        n_bar = max(3, int(blen / 0.12))
        step = blen / n_bar
        for j in range(n_bar + 1):
            bp = a + j * step
            cube(
                f"{name}:bar:{k}:{j}",
                (*_pt(axis, bp, f), (rail_bot + rail_top) / 2 + 0.03),
                (bar_t, bar_t, rail_top - rail_bot + 0.30),
                M["iron"],
                coll,
                bevel=0.003,
            )
            pyramid(
                f"{name}:sp:{k}:{j}",
                (*_pt(axis, bp, f), rail_top + 0.24),
                bar_t * 1.7,
                0.15,
                M["iron"],
                coll,
                verts=4,
                bevel=0.0,
            )
        n_ring = max(1, int(blen / 0.52))
        rstep = blen / n_ring
        for j in range(n_ring):
            rp = a + (j + 0.5) * rstep
            torus(
                f"{name}:rg:{k}:{j}",
                (*_pt(axis, rp, f), (rail_bot + rail_top) / 2 + 0.02),
                0.085,
                0.016,
                M["iron"],
                coll,
                major=24,
                minor=8,
                rot=ring_rot,
            )


def slat_run(name, coll, axis, t0, t1, f, pos):
    """Modern timber-slat run: a low continuous concrete curb, then horizontal
    wood slats with shadow gaps filling each bay between the posts in `pos`."""
    length = t1 - t0
    tc = (t0 + t1) / 2
    curb_h = 0.16
    post_h = 1.82
    cube(
        f"{name}:curb",
        (*_pt(axis, tc, f), curb_h / 2),
        _dims(axis, length + 0.04, 0.16, curb_h),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    wood = M["wood_x"] if axis == "X" else M["wood_y"]
    slat_h = 0.145
    slat_t = 0.032
    gap = 0.035
    for k in range(len(pos) - 1):
        a = pos[k] + 0.06
        bcx = (pos[k] + pos[k + 1]) / 2
        blen = (pos[k + 1] - 0.06) - a
        if blen <= 0.05:
            continue
        z = curb_h + 0.06
        top = curb_h + post_h - 0.05
        s = 0
        while z + slat_h / 2 <= top:
            cube(
                f"{name}:sl:{k}:{s}",
                (*_pt(axis, bcx, f), z + slat_h / 2),
                _dims(axis, blen + 0.006, slat_t, slat_h),
                wood,
                coll,
                bevel=0.006,
            )
            z += slat_h + gap
            s += 1


# --------------------------------------------------------------------------- #
# Double-leaf entrance gate (one per style)
# --------------------------------------------------------------------------- #
def iron_gate_leaf(name, coll, gx0, gx1):
    y = 0.0
    w = gx1 - gx0
    gcx = (gx0 + gx1) / 2
    z_bot, z_top = 0.12, 1.60
    stile = 0.055
    cube(
        f"{name}:sL",
        (gx0 + stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:sR",
        (gx1 - stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:rB",
        (gcx, y, z_bot + 0.03),
        (w, 0.055, 0.07),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:rT",
        (gcx, y, z_top - 0.03),
        (w, 0.055, 0.07),
        M["iron"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:rM",
        (gcx, y, z_bot + (z_top - z_bot) * 0.42),
        (w, 0.04, 0.045),
        M["iron"],
        coll,
        bevel=0.004,
    )
    bar_t = 0.022
    n = max(4, int(w / 0.12))
    step = w / n
    for j in range(n + 1):
        bx = gx0 + j * step
        if bx <= gx0 + stile or bx >= gx1 - stile:
            continue
        cube(
            f"{name}:b:{j}",
            (bx, y, (z_bot + z_top) / 2 + 0.02),
            (bar_t, bar_t, z_top - z_bot + 0.24),
            M["iron"],
            coll,
            bevel=0.002,
        )
        pyramid(
            f"{name}:sp:{j}",
            (bx, y, z_top + 0.22),
            bar_t * 1.8,
            0.16,
            M["iron"],
            coll,
            verts=4,
            bevel=0.0,
        )
    n_ring = max(2, int(w / 0.55))
    rstep = w / n_ring
    for j in range(n_ring):
        rx = gx0 + (j + 0.5) * rstep
        torus(
            f"{name}:rg:{j}",
            (rx, y, z_bot + (z_top - z_bot) * 0.30),
            0.085,
            0.015,
            M["iron"],
            coll,
            major=24,
            minor=8,
            rot=(math.radians(90), 0, 0),
        )


def slat_gate_leaf(name, coll, gx0, gx1):
    y = 0.0
    w = gx1 - gx0
    gcx = (gx0 + gx1) / 2
    z_bot, z_top = 0.10, 1.62
    stile = 0.06
    cube(
        f"{name}:sL",
        (gx0 + stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["anthracite"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:sR",
        (gx1 - stile / 2, y, (z_bot + z_top) / 2),
        (stile, 0.05, z_top - z_bot),
        M["anthracite"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:rB",
        (gcx, y, z_bot + 0.03),
        (w, 0.05, 0.06),
        M["anthracite"],
        coll,
        bevel=0.005,
    )
    cube(
        f"{name}:rT",
        (gcx, y, z_top - 0.03),
        (w, 0.05, 0.06),
        M["anthracite"],
        coll,
        bevel=0.005,
    )
    slat_h = 0.145
    slat_t = 0.032
    gap = 0.035
    z = z_bot + 0.10
    s = 0
    inner = w - 2 * stile
    while z + slat_h / 2 <= z_top - 0.08:
        cube(
            f"{name}:sl:{s}",
            (gcx, y, z + slat_h / 2),
            (inner, slat_t, slat_h),
            M["wood_x"],
            coll,
            bevel=0.005,
        )
        z += slat_h + gap
        s += 1


def build_gate(coll, ox, style):
    gap = 0.03
    if style == "slat":
        slat_gate_leaf(f"{style}:gateL", coll, ox - GATE_CLEAR / 2, ox - gap)
        slat_gate_leaf(f"{style}:gateR", coll, ox + gap, ox + GATE_CLEAR / 2)
    else:
        iron_gate_leaf(f"{style}:gateL", coll, ox - GATE_CLEAR / 2, ox - gap)
        iron_gate_leaf(f"{style}:gateR", coll, ox + gap, ox + GATE_CLEAR / 2)
        for sx in (-0.05, 0.05):
            cube(
                f"{style}:gateC:{sx:.2f}",
                (ox + sx, 0.0, (0.12 + 1.60) / 2),
                (0.05, 0.06, 1.60 - 0.12),
                M["iron"],
                coll,
                bevel=0.004,
            )


# --------------------------------------------------------------------------- #
# Assemble one closed enclosure
# --------------------------------------------------------------------------- #
# per-style pier sizing: (intermediate w, h, corner w, h, gate w, h)
CFG = {
    "brick": (0.42, 1.92, 0.52, 2.04, 0.54, 2.18),
    "iron": (0.34, 1.72, 0.42, 1.94, 0.44, 2.00),
    "slat": (0.12, 1.82, 0.15, 1.86, 0.15, 1.90),
}


def enclosure(coll, ox, style):
    pw, ph, cw, ch, gw, gh = CFG[style]
    xL, xR = ox - HALF, ox + HALF
    yF, yB = 0.0, BACK
    gate_px = GATE_CLEAR / 2 + gw / 2

    # corner piers
    for tag, (px, py) in (
        ("cLF", (xL, yF)),
        ("cRF", (xR, yF)),
        ("cLB", (xL, yB)),
        ("cRB", (xR, yB)),
    ):
        place_pier(style, f"{style}:{tag}", coll, px, py, cw, ch, ball_top=True)
    # gate piers
    place_pier(style, f"{style}:gpL", coll, ox - gate_px, yF, gw, gh, ball_top=True)
    place_pier(style, f"{style}:gpR", coll, ox + gate_px, yF, gw, gh, ball_top=True)

    sides = [
        ("back", "X", xL, xR, yB),
        ("left", "Y", yF, yB, xL),
        ("right", "Y", yF, yB, xR),
        ("frontL", "X", xL, ox - gate_px, yF),
        ("frontR", "X", ox + gate_px, xR, yF),
    ]
    for sname, axis, t0, t1, f in sides:
        length = t1 - t0
        n = max(1, round(length / 2.9))
        pos = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        # intermediate piers (endpoints are corners / gate piers already placed)
        for i in range(1, len(pos) - 1):
            px, py = _pt(axis, pos[i], f)
            place_pier(style, f"{style}:{sname}:p{i}", coll, px, py, pw, ph)
        # run
        if style == "brick":
            cx, cy = _pt(axis, (t0 + t1) / 2, f)
            brick_run(f"{style}:{sname}", coll, cx, cy, length, axis)
            # decorative piers sit on the wall at every pier position
            # (already placed as intermediate; brick wall is continuous)
        elif style == "iron":
            iron_run(f"{style}:{sname}", coll, axis, t0, t1, f, pos)
        else:
            slat_run(f"{style}:{sname}", coll, axis, t0, t1, f, pos)

    build_gate(coll, ox, style)


# --------------------------------------------------------------------------- #
# Ground + world + sun + cameras + render
# --------------------------------------------------------------------------- #
def build_ground(coll):
    cube("gnd", (0.0, 6.0, -0.05), (200, 200, 0.10), M["ground"], coll, bevel=0)


def build_world():
    """Neutral studio sky: solid soft-grey background (bright to camera, weak
    for lighting) so the sun still throws crisp shadows on a clean backdrop."""
    world = bpy.data.worlds.new("f_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for nname in list(nt.nodes):
        nt.nodes.remove(nname)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    bg_cam.inputs["Color"].default_value = (0.74, 0.77, 0.82, 1.0)
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light.inputs["Color"].default_value = (0.62, 0.66, 0.72, 1.0)
    bg_light.inputs["Strength"].default_value = 0.85
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_light.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    print("[fence3] world: neutral studio sweep")


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 5.0
    sun.data.angle = math.radians(1.6)
    sun.data.color = (1.0, 0.96, 0.90)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-52))


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
        glare.mix = -0.78
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
    print(f"[fence3] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 8
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
    print(f"[fence3] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ground_c = add_collection("f_ground")
    brick_c = add_collection("f_brick")
    iron_c = add_collection("f_iron")
    slat_c = add_collection("f_slat")

    build_ground(ground_c)
    enclosure(brick_c, BRICK_OX, "brick")
    enclosure(iron_c, IRON_OX, "iron")
    enclosure(slat_c, SLAT_OX, "slat")

    build_world()
    add_sun()
    configure_cycles()
    setup_compositor()
    scene = bpy.context.scene

    # all three enclosures together, high 3/4 from the street side
    overview = make_camera(
        "cam_overview", (3.0, -46.0, 33.0), (0.0, 7.0, 0.6), lens=30, fstop=None
    )

    def type_cam(name, ox):
        return make_camera(
            name, (ox - 15.5, -15.5, 10.5), (ox + 1.2, 6.5, 0.9), lens=30, fstop=None
        )

    cam_brick = type_cam("cam_brick", BRICK_OX)
    cam_iron = type_cam("cam_iron", IRON_OX)
    cam_slat = type_cam("cam_slat", SLAT_OX)
    # tight brick realism detail on the brick enclosure's front-left wall
    bl_cx = BRICK_OX - (HALF + GATE_CLEAR / 2 + 0.27) / 2
    cam_brick_detail = make_camera(
        "cam_brick_detail",
        (bl_cx - 2.4, -3.0, 1.35),
        (bl_cx + 0.4, 0.12, 1.0),
        lens=55,
        fstop=5.0,
    )

    scene.camera = overview
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    spp = int(os.environ.get("V3_SPP", 448))
    render_still(scene, overview, OVERVIEW_PATH, samples=max(384, spp - 64))
    render_still(scene, cam_brick, BRICK_PATH, samples=spp)
    render_still(scene, cam_iron, IRON_PATH, samples=spp)
    render_still(scene, cam_slat, SLAT_PATH, samples=spp)
    render_still(scene, cam_brick_detail, BRICK_DETAIL_PATH, samples=spp)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[fence3] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
