"""Photorealistic procedural residential BOUNDARY FENCES / WALLS (urban_v3_fence).

Infinigen ships NO fence / boundary-wall asset (checked: nothing under
infinigen/assets for fence|railing|balustrade|palisade|wall|brick|masonry), so
this builds three distinct, image-level-real garden/house perimeter enclosures
procedurally.  ONLY the outer fence / wall is modelled - no house.

  A. WROUGHT-IRON VILLA RAILING  - cut-stone plinth + stone pier columns with
     pyramidal caps, satin-black iron infill (square balusters, top & bottom
     rails, ring/scroll motif) topped with spear-point finials.
  B. BRICK PRIVACY WALL          - coursed red brick (procedural brick texture,
     recessed mortar), projecting brick piers, a cast concrete coping cap along
     the top + pyramidal pier caps, a concrete string course band.
  C. MODERN TIMBER-SLAT FENCE    - charcoal (RAL7016) square steel posts with
     caps on a low concrete curb, warm horizontal timber slats with shadow gaps.

Realism levers (same as the v3 kiosks): weathered PBR (noise roughness + AO
grime + edge wear + bump), procedural brick/wood/stone/concrete, a split-sky
city HDRI (bright to camera, weak for lighting) so the sun throws crisp
directional shadows, AgX + glare, GPU/OPTIX.

Run:
  TMPDIR=${WORLDBRIDGE_EXTERNAL}/tmp ${BLENDER_BIN} -b \
      --python scripts/generate_urban_v3_fence.py
Env:
  V3_SPP=N   sample override (default 480)
  F_ENV=city|courtyard|sunset|sunrise   HDRI (default city)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence):
  fence.blend
  fence_overview.png   all three side by side
  fence_iron.png       A - wrought-iron villa railing
  fence_brick.png      B - brick privacy wall
  fence_slat.png       C - modern timber-slat fence
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
from mathutils import Vector

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_fence")
SCENE_PATH = OUTPUT_DIR / "fence.blend"
OVERVIEW_PATH = OUTPUT_DIR / "fence_overview.png"
IRON_PATH = OUTPUT_DIR / "fence_iron.png"
BRICK_PATH = OUTPUT_DIR / "fence_brick.png"
SLAT_PATH = OUTPUT_DIR / "fence_slat.png"

BLENDER_ROOT = Path(f"{_wb_BLENDER_RESOURCES}")
HDRI_DIR = BLENDER_ROOT / "datafiles/studiolights/world"

# fence centres along X and their span (boundary line at Y=0, front = -Y)
IRON_CX, BRICK_CX, SLAT_CX = -7.0, 0.0, 7.0
FENCE_LEN = 5.4


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
# Material toolkit (weathered PBR workhorse, from the v3 kiosks)
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


def mat_brick(
    name,
    c1,
    c2,
    mortar,
    *,
    bw=0.235,
    rh=0.078,
    mortar_sz=0.012,
    rough=0.74,
    bump=0.42,
    coat=0.0,
):
    """Coursed masonry via the Brick texture in OBJECT space (world-consistent
    brick size regardless of the object's dimensions).  The brick Fac drives a
    bump so the mortar joints read recessed and the bricks proud.

    NOTE: the Brick node stacks its ROWS along the input vector's Y axis, but a
    wall stands up in Z (front face = X-Z plane at ~constant Y), so raw object
    coords would collapse the courses into vertical stripes.  Rotating the input
    90 deg about X routes world-Z into the node's row axis -> real horizontal
    courses on every upright face."""
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
    # per-brick tonal variation so it never looks like a flat tiled texture
    var = nt.nodes.new("ShaderNodeTexNoise")
    var.inputs["Scale"].default_value = 5.0
    var.inputs["Detail"].default_value = 2.0
    mixv = nt.nodes.new("ShaderNodeMixRGB")
    mixv.blend_type = "MULTIPLY"
    mixv.inputs["Fac"].default_value = 0.35
    nt.links.new(tb.outputs["Color"], mixv.inputs["Color1"])
    nt.links.new(var.outputs["Color"], mixv.inputs["Color2"])
    nt.links.new(mixv.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", rough)
    _set(b, ("Coat Weight", "Coat"), coat)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.02
    nt.links.new(tb.outputs["Fac"], bmp.inputs["Height"])
    # fine grit on the faces
    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 120.0
    bmp2 = nt.nodes.new("ShaderNodeBump")
    bmp2.inputs["Strength"].default_value = 0.10
    nt.links.new(grit.outputs["Fac"], bmp2.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bmp2.inputs["Normal"])
    nt.links.new(bmp2.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_wood(name, base=(0.40, 0.235, 0.115), dark=(0.22, 0.12, 0.055)):
    """Warm timber slat: wavy grain bands stretched along the slat, satin coat."""
    m, nt, b = _principled(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    # stretch along X (slat length) so the grain runs lengthwise
    mp.inputs["Scale"].default_value = (0.45, 7.5, 7.5)
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
    """A cone with `verts` sides -> a pyramid/spike.  `loc` is the CENTRE; base
    sits at loc.z-height/2, apex at loc.z+height/2."""
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


# --------------------------------------------------------------------------- #
# Materials registry
# --------------------------------------------------------------------------- #
M = {}


def build_materials():
    # coursed cut-stone (ashlar) for the villa plinth + piers
    M["stone"] = mat_brick(
        "f_stone",
        (0.50, 0.465, 0.40),
        (0.44, 0.41, 0.35),
        (0.34, 0.32, 0.29),
        bw=0.52,
        rh=0.24,
        mortar_sz=0.020,
        rough=0.84,
        bump=0.40,
    )
    # red facing brick for the privacy wall (deep clay red - AgX lifts it)
    M["brick"] = mat_brick(
        "f_brick",
        (0.30, 0.075, 0.052),
        (0.235, 0.072, 0.056),
        (0.70, 0.66, 0.60),
        bw=0.235,
        rh=0.076,
        mortar_sz=0.016,
        rough=0.78,
        bump=0.52,
    )
    # cast concrete for copings / caps / curbs / string course
    M["concrete"] = mat_surface(
        "f_concrete",
        (0.60, 0.59, 0.565),
        base_rough=0.80,
        rough_var=0.10,
        rough_scale=4.0,
        bump=0.14,
        bump_scale=26,
        dirt=0.34,
        ao_dist=0.4,
        coat=0.0,
    )
    # satin-black wrought iron (painted metal)
    M["iron"] = mat_surface(
        "f_iron",
        (0.021, 0.021, 0.024),
        metallic=0.7,
        base_rough=0.38,
        rough_var=0.08,
        bump=0.05,
        bump_scale=150,
        wear=0.07,
        wear_color=(0.11, 0.11, 0.12),
        dirt=0.26,
        coat=0.06,
    )
    # charcoal / RAL7016 anthracite steel for the modern posts
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
    # warm timber slats
    M["wood"] = mat_wood("f_wood")
    # ground: lawn (garden side) + paved sidewalk (street side)
    M["grass"] = mat_surface(
        "f_grass",
        (0.055, 0.135, 0.035),
        base_rough=0.95,
        rough_var=0.20,
        rough_scale=14.0,
        bump=0.7,
        bump_scale=300,
        dirt=0.42,
        ao_dist=0.5,
        coat=0.0,
    )
    M["hedge"] = mat_surface(
        "f_hedge",
        (0.055, 0.165, 0.038),
        base_rough=0.95,
        rough_var=0.14,
        rough_scale=9.0,
        bump=0.85,
        bump_scale=280,
        dirt=0.4,
        ao_dist=0.4,
        coat=0.0,
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
        coat=0.0,
    )
    M["pave_seam"] = mat_surface(
        "f_paveseam", (0.07, 0.07, 0.072), base_rough=0.9, dirt=0.6
    )
    print("[fence] materials:", len(M))


# --------------------------------------------------------------------------- #
# A - WROUGHT-IRON VILLA RAILING  (stone plinth + piers + black iron infill)
# --------------------------------------------------------------------------- #
def build_iron_fence(coll, cx=IRON_CX):
    x0, x1 = cx - FENCE_LEN / 2, cx + FENCE_LEN / 2
    y = 0.0
    plinth_h = 0.46  # low stone base wall
    plinth_t = 0.20
    pier_w = 0.34
    pier_h = 1.72
    rail_bot = plinth_h + 0.06
    rail_top = 1.46  # top rail height
    bar_t = 0.024  # baluster cross-section

    # continuous stone plinth
    cube(
        "A:plinth",
        (cx, y, plinth_h / 2),
        (FENCE_LEN, plinth_t, plinth_h),
        M["stone"],
        coll,
        bevel=0.012,
    )
    # a slim concrete cap along the plinth top (the rail sits on this)
    cube(
        "A:plinth_cap",
        (cx, y, plinth_h + 0.02),
        (FENCE_LEN, plinth_t + 0.04, 0.05),
        M["concrete"],
        coll,
        bevel=0.01,
    )

    # pier columns (4 -> 3 bays), stone with a concrete + pyramid cap
    n_pier = 4
    pier_xs = [x0 + i * (FENCE_LEN / (n_pier - 1)) for i in range(n_pier)]
    for i, px in enumerate(pier_xs):
        cube(
            f"A:pier:{i}",
            (px, y, pier_h / 2),
            (pier_w, pier_w + 0.04, pier_h),
            M["stone"],
            coll,
            bevel=0.014,
        )
        cube(
            f"A:piercap:{i}",
            (px, y, pier_h + 0.03),
            (pier_w + 0.12, pier_w + 0.14, 0.07),
            M["concrete"],
            coll,
            bevel=0.012,
        )
        pyramid(
            f"A:pierpyr:{i}",
            (px, y, pier_h + 0.135),
            (pier_w + 0.08) / 2,
            0.16,
            M["concrete"],
            coll,
            bevel=0.004,
        )
    # small stone ball finial on top of each pyramid cap
    for i, px in enumerate(pier_xs):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.055, location=(px, y, pier_h + 0.24)
        )
        o = bpy.context.object
        o.name = f"A:ball:{i}"
        o.data.materials.append(M["concrete"])
        smooth(o)
        link_to(o, coll)

    # iron infill panels between consecutive piers
    for i in range(n_pier - 1):
        bx0 = pier_xs[i] + pier_w / 2 + 0.01
        bx1 = pier_xs[i + 1] - pier_w / 2 - 0.01
        bw = bx1 - bx0
        bcx = (bx0 + bx1) / 2
        # top & bottom horizontal rails (flat bar stock)
        cube(
            f"A:rail_b:{i}",
            (bcx, y, rail_bot),
            (bw, 0.05, 0.05),
            M["iron"],
            coll,
            bevel=0.006,
        )
        cube(
            f"A:rail_t:{i}",
            (bcx, y, rail_top),
            (bw, 0.05, 0.06),
            M["iron"],
            coll,
            bevel=0.006,
        )
        # a second thin ornamental rail just under the top rail
        cube(
            f"A:rail_m:{i}",
            (bcx, y, rail_top - 0.30),
            (bw, 0.035, 0.035),
            M["iron"],
            coll,
            bevel=0.005,
        )
        # vertical balusters with spear finials
        n_bar = max(3, int(bw / 0.12))
        step = bw / n_bar
        for j in range(n_bar + 1):
            bxp = bx0 + j * step
            cube(
                f"A:bar:{i}:{j}",
                (bxp, y, (rail_bot + rail_top) / 2 + 0.03),
                (bar_t, bar_t, rail_top - rail_bot + 0.30),
                M["iron"],
                coll,
                bevel=0.003,
            )
            # spear point above the top rail
            pyramid(
                f"A:spear:{i}:{j}",
                (bxp, y, rail_top + 0.24),
                bar_t * 1.7,
                0.15,
                M["iron"],
                coll,
                verts=4,
                bevel=0.0,
            )
        # decorative ring motif row centred in the panel
        n_ring = max(2, int(bw / 0.52))
        rstep = bw / n_ring
        for j in range(n_ring):
            rx = bx0 + (j + 0.5) * rstep
            torus(
                f"A:ring:{i}:{j}",
                (rx, y, (rail_bot + rail_top) / 2 + 0.02),
                0.085,
                0.016,
                M["iron"],
                coll,
                major=24,
                minor=8,
                rot=(math.radians(90), 0, 0),
            )

    return Vector((cx, 0.0, 1.05))


# --------------------------------------------------------------------------- #
# B - BRICK PRIVACY WALL  (coursed brick + piers + concrete coping/caps)
# --------------------------------------------------------------------------- #
def build_brick_wall(coll, cx=BRICK_CX):
    x0, x1 = cx - FENCE_LEN / 2, cx + FENCE_LEN / 2
    y = 0.0
    wall_h = 1.66
    wall_t = 0.24
    pier_w = 0.42
    pier_h = 1.92

    # foundation curb
    cube(
        "B:foot",
        (cx, y, 0.06),
        (FENCE_LEN + 0.05, wall_t + 0.10, 0.12),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    # main brick wall
    cube(
        "B:wall",
        (cx, y, 0.12 + wall_h / 2),
        (FENCE_LEN, wall_t, wall_h),
        M["brick"],
        coll,
        bevel=0.006,
    )
    # concrete string-course band about 2/3 up (a shallow projecting ledge)
    band_z = 0.12 + wall_h * 0.66
    cube(
        "B:band",
        (cx, y, band_z),
        (FENCE_LEN + 0.02, wall_t + 0.06, 0.07),
        M["concrete"],
        coll,
        bevel=0.01,
    )
    # concrete coping cap running along the whole top
    cube(
        "B:coping",
        (cx, y, 0.12 + wall_h + 0.045),
        (FENCE_LEN + 0.04, wall_t + 0.12, 0.09),
        M["concrete"],
        coll,
        bevel=0.012,
    )

    # projecting brick piers
    n_pier = 4
    pier_xs = [x0 + i * (FENCE_LEN / (n_pier - 1)) for i in range(n_pier)]
    for i, px in enumerate(pier_xs):
        cube(
            f"B:pier:{i}",
            (px, y, 0.12 + pier_h / 2),
            (pier_w, pier_w + wall_t, pier_h),
            M["brick"],
            coll,
            bevel=0.008,
        )
        cube(
            f"B:piercap:{i}",
            (px, y, 0.12 + pier_h + 0.04),
            (pier_w + 0.14, pier_w + wall_t + 0.14, 0.08),
            M["concrete"],
            coll,
            bevel=0.012,
        )
        pyramid(
            f"B:pierpyr:{i}",
            (px, y, 0.12 + pier_h + 0.155),
            (pier_w + 0.10) / 2,
            0.18,
            M["concrete"],
            coll,
            bevel=0.004,
        )

    return Vector((cx, 0.0, 1.05))


# --------------------------------------------------------------------------- #
# C - MODERN TIMBER-SLAT FENCE  (charcoal steel posts + horizontal wood slats)
# --------------------------------------------------------------------------- #
def build_slat_fence(coll, cx=SLAT_CX):
    x0, x1 = cx - FENCE_LEN / 2, cx + FENCE_LEN / 2
    y = 0.0
    curb_h = 0.16
    post_w = 0.10
    post_h = 1.82
    slat_h = 0.145  # slat face height
    slat_t = 0.032  # slat thickness
    gap = 0.035  # shadow gap between slats

    # low concrete curb
    cube(
        "C:curb",
        (cx, y, curb_h / 2),
        (FENCE_LEN + 0.04, 0.16, curb_h),
        M["concrete"],
        coll,
        bevel=0.01,
    )

    # charcoal steel posts (4 -> 3 bays) with flat caps
    n_post = 4
    post_xs = [x0 + i * (FENCE_LEN / (n_post - 1)) for i in range(n_post)]
    for i, px in enumerate(post_xs):
        cube(
            f"C:post:{i}",
            (px, y, curb_h + post_h / 2),
            (post_w, post_w, post_h),
            M["anthracite"],
            coll,
            bevel=0.006,
        )
        cube(
            f"C:postcap:{i}",
            (px, y, curb_h + post_h + 0.012),
            (post_w + 0.02, post_w + 0.02, 0.024),
            M["anthracite"],
            coll,
            bevel=0.004,
        )

    # horizontal timber slats spanning each bay, stacked with shadow gaps
    z = curb_h + 0.06
    top = curb_h + post_h - 0.05
    k = 0
    while z + slat_h / 2 <= top:
        for i in range(n_post - 1):
            bx0 = post_xs[i] + post_w / 2
            bx1 = post_xs[i + 1] - post_w / 2
            bw = bx1 - bx0
            bcx = (bx0 + bx1) / 2
            cube(
                f"C:slat:{k}:{i}",
                (bcx, y, z + slat_h / 2),
                (bw + 0.006, slat_t, slat_h),
                M["wood"],
                coll,
                bevel=0.006,
            )
        z += slat_h + gap
        k += 1

    return Vector((cx, 0.0, 1.0))


# --------------------------------------------------------------------------- #
# Ground + garden context (lawn behind, sidewalk in front, low hedges)
# --------------------------------------------------------------------------- #
def build_ground(coll):
    # paved sidewalk on the street (camera / -Y) side
    cube("gnd:pave", (0.0, -5.0, -0.03), (44, 10.0, 0.06), M["pave"], coll, bevel=0)
    step = 1.5
    for i in range(-14, 15):
        cube(
            f"gnd:sx:{i}",
            (i * step, -5.0, 0.005),
            (0.05, 10.0, 0.010),
            M["pave_seam"],
            coll,
            bevel=0,
        )
    for j in range(0, 7):
        cube(
            f"gnd:sy:{j}",
            (0.0, -0.2 - j * 1.5, 0.005),
            (44, 0.05, 0.010),
            M["pave_seam"],
            coll,
            bevel=0,
        )
    # lawn on the garden (+Y) side, just behind the boundary line
    cube("gnd:lawn", (0.0, 6.0, -0.04), (44, 12.0, 0.06), M["grass"], coll, bevel=0)

    # low clipped hedges behind the iron & slat fences for a real-yard context
    for cx in (IRON_CX, SLAT_CX):
        cube(
            f"gnd:hedge:{cx:.0f}",
            (cx, 0.95, 0.55),
            (FENCE_LEN - 0.2, 0.55, 1.10),
            M["hedge"],
            coll,
            bevel=0.22,
        )
    # a couple of hedge balls behind the brick wall (peeking spheres)
    for dx in (-1.4, 1.4):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.62, location=(BRICK_CX + dx, 1.1, 0.9)
        )
        o = bpy.context.object
        o.name = f"gnd:bush:{dx:.0f}"
        o.scale = (1.0, 1.0, 0.85)
        o.data.materials.append(M["hedge"])
        smooth(o)
        link_to(o, coll)


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
    mapping.inputs["Rotation"].default_value = (0, 0, math.radians(60))
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
    print(f"[fence] HDRI env: {path.name} (split-sky)")


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 8.5
    sun.data.angle = math.radians(1.2)
    sun.data.color = (1.0, 0.94, 0.84)
    sun.rotation_euler = (math.radians(46), 0, math.radians(-58))


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
    print(f"[fence] Cycles backend: {chosen}")
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


def render_still(scene, cam, path, samples=480, res=(1920, 1080)):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    print(f"[fence] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ground_c = add_collection("f_ground")
    iron_c = add_collection("f_iron")
    brick_c = add_collection("f_brick")
    slat_c = add_collection("f_slat")

    build_ground(ground_c)
    t_iron = build_iron_fence(iron_c, cx=IRON_CX)
    t_brick = build_brick_wall(brick_c, cx=BRICK_CX)
    t_slat = build_slat_fence(slat_c, cx=SLAT_CX)

    build_world()
    add_sun()
    configure_cycles()
    setup_compositor()
    scene = bpy.context.scene

    overview = make_camera(
        "cam_overview", (-1.0, -12.5, 3.3), (0.4, 0.3, 1.0), lens=28, fstop=None
    )
    cam_iron = make_camera(
        "cam_iron",
        (t_iron.x - 3.1, -4.8, 1.6),
        (t_iron.x + 0.5, 0.15, 0.95),
        lens=42,
        fstop=6.3,
    )
    cam_brick = make_camera(
        "cam_brick",
        (t_brick.x - 3.1, -4.8, 1.65),
        (t_brick.x + 0.5, 0.15, 1.05),
        lens=42,
        fstop=6.3,
    )
    cam_slat = make_camera(
        "cam_slat",
        (t_slat.x - 3.1, -4.8, 1.6),
        (t_slat.x + 0.5, 0.15, 0.95),
        lens=42,
        fstop=6.3,
    )

    scene.camera = overview
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    spp = int(os.environ.get("V3_SPP", 480))
    render_still(scene, overview, OVERVIEW_PATH, samples=max(360, spp - 100))
    render_still(scene, cam_iron, IRON_PATH, samples=spp)
    render_still(scene, cam_brick, BRICK_PATH, samples=spp)
    render_still(scene, cam_slat, SLAT_PATH, samples=spp)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[fence] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
