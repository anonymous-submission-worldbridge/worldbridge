"""Photorealistic procedural BENCH + TRASH-BIN showcase v2
(urban_v3_longchair+trashbin2).

v1 modelled six pieces but they read as CG: mirror-clean metal, glossy plastic
paint, void-black liners, no weathering, a flat studio floor and flat lighting.
v2 attacks every one of those tells:

  MATERIALS  - a shared `_weather` node graph adds, to *every* surface:
                 * grime settling in crevices        (geometry Pointiness, concave)
                 * polished / chipped wear on edges   (geometry Pointiness, convex)
                 * dust on up-facing surfaces         (True-Normal.Z * noise)
                 * roughness mottling                 (noise -> MapRange)
               plus per-plank wood colour variation (Object-Info Random -> HSV),
               satin metals (not chrome), galvanised spangle, paint whose worn
               edges reveal bare metal, and a matte mid-grey liner (not a void).

  LIGHTING   - stronger Nishita sky for ambient + reflections, and a big soft
               area-light "soft-box" so metal / paint get real speculars and
               something to reflect (the single biggest realism lever for metal).

  GROUND     - textured concrete (cracks + stains + bump) and a varied lawn, so
               contact shadows land on a believable surface, not a clean slab.

  GEOMETRY   - the classic bench's cast-iron ends are now flat *castings* (with
               bolt fixings) instead of thin round tubes; the domed bin gets a
               flatter lid + finial + seam band; every piece gets a small random
               yaw so nothing is robotically aligned.

Rendered with Cycles + OptiX GPU, Nishita sky, AgX, depth-of-field.

Run:
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_bench_trashbin2.py
  (FURN_QUICK=1 -> fast smoke test; URBAN_FURN_OUT overrides out dir)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_longchair+trashbin2):
  furniture.blend, furniture.png (hero), _overview, _gallery,
  bench_01_classic.png ... bin_03_wooden.png (six close-ups), furniture_orbit.mp4
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
import subprocess
import sys
from pathlib import Path

REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUTPUT_DIR = Path(
    os.environ.get(
        "URBAN_FURN_OUT",
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_longchair+trashbin2",
    )
)
FRAMES_DIR = OUTPUT_DIR / "frames"
TMP_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
for d in (OUTPUT_DIR, FRAMES_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

SCENE_PATH = OUTPUT_DIR / "furniture.blend"
HERO_PNG = OUTPUT_DIR / "furniture.png"
OVERVIEW_PNG = OUTPUT_DIR / "furniture_overview.png"
GALLERY_PNG = OUTPUT_DIR / "furniture_gallery.png"
VIDEO_PATH = OUTPUT_DIR / "furniture_orbit.mp4"

TAU = math.tau


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


def _noise(nt, scale, detail=8.0, vec=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
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


def _weather(
    nt,
    b,
    base_socket,
    *,
    base_rough=0.5,
    edge_color=(0.06, 0.06, 0.065),
    edge_amt=0.0,
    edge_metallic=0.0,
    base_metallic=0.0,
    dirt=0.4,
    dirt_color=(0.014, 0.012, 0.010),
    dust=0.0,
    dust_color=(0.30, 0.28, 0.24),
    bump_strength=0.05,
    bump_scale=180.0,
    base_normal=None,
):
    """Layer grime (crevices), edge wear, top dust, roughness mottling and a
    micro-bump onto a base colour, then drive a Principled BSDF."""
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    # convex edges -> wear / chips
    chip = _math(
        nt,
        "MULTIPLY",
        a_sock=_maprange(nt, geo.outputs["Pointiness"], 0.54, 0.66, 0.0, 1.0),
        b=edge_amt,
    )
    # concave crevices -> dirt
    dirt_f = _math(
        nt,
        "MULTIPLY",
        a_sock=_maprange(nt, geo.outputs["Pointiness"], 0.47, 0.30, 0.0, 1.0),
        b=dirt,
    )
    # up-facing faces * noise -> settled dust
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["True Normal"], sep.inputs["Vector"])
    up = _maprange(nt, sep.outputs["Z"], 0.2, 0.7, 0.0, 1.0)
    dust_f = _math(
        nt,
        "MULTIPLY",
        a_sock=_math(nt, "MULTIPLY", a_sock=up, b_sock=_noise(nt, 24.0).outputs["Fac"]),
        b=dust,
    )
    # base colour chain
    c1 = _mix(nt, fac_sock=chip, c1_sock=base_socket, c2=edge_color)
    c2 = _mix(nt, fac_sock=dirt_f, c1_sock=c1, c2=dirt_color)
    c3 = _mix(nt, fac_sock=dust_f, c1_sock=c2, c2=dust_color)
    nt.links.new(c3, b.inputs["Base Color"])
    # metallic
    if edge_metallic > 0 or base_metallic > 0:
        met = _math(
            nt,
            "MINIMUM",
            a_sock=_math(
                nt,
                "ADD",
                a_sock=_math(nt, "MULTIPLY", a_sock=chip, b=edge_metallic),
                b=base_metallic,
            ),
            b=1.0,
        )
        nt.links.new(met, b.inputs["Metallic"])
    else:
        _set(b, "Metallic", 0.0)
    # roughness: noise mottle + rougher where dirty
    rr = _maprange(
        nt,
        _noise(nt, 42.0).outputs["Fac"],
        0.0,
        1.0,
        base_rough - 0.08,
        base_rough + 0.12,
    )
    rough = _math(
        nt,
        "MINIMUM",
        a_sock=_math(
            nt, "ADD", a_sock=rr, b_sock=_math(nt, "MULTIPLY", a_sock=dirt_f, b=0.22)
        ),
        b=0.96,
    )
    nt.links.new(rough, b.inputs["Roughness"])
    # micro bump (optionally chained on top of a base normal, e.g. wood grain)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    nt.links.new(
        _noise(nt, bump_scale, detail=8.0).outputs["Fac"], bump.inputs["Height"]
    )
    if base_normal is not None:
        nt.links.new(base_normal, bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])


# --------------------------------------------------------------------------- #
# Material builders
# --------------------------------------------------------------------------- #
def metal_material(
    name,
    color,
    roughness=0.42,
    base_metallic=1.0,
    edge_amt=0.18,
    edge_color=None,
    dust=0.15,
    bump_scale=130.0,
    bump_strength=0.04,
    spangle=False,
):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    src = _rgb(nt, color)
    if spangle:  # galvanised mottled crystal look
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 13.0
        light = tuple(min(1.0, c * 1.5) for c in color)
        dark = tuple(c * 0.6 for c in color)
        src = _mix(nt, fac_sock=vor.outputs["Distance"], c1=dark, c2=light)
    if edge_color is None:
        edge_color = tuple(min(1.0, c * 1.7 + 0.05) for c in color)
    _weather(
        nt,
        b,
        src,
        base_rough=roughness,
        edge_color=edge_color,
        edge_amt=edge_amt,
        edge_metallic=0.0,
        base_metallic=base_metallic,
        dirt=0.35,
        dirt_color=(0.02, 0.02, 0.02),
        dust=dust,
        dust_color=(0.33, 0.31, 0.27),
        bump_strength=bump_strength,
        bump_scale=bump_scale,
    )
    return m


def paint_material(
    name,
    paint,
    roughness=0.5,
    dust=0.4,
    chip=0.5,
    metal=(0.055, 0.055, 0.06),
    bump_scale=210.0,
):
    """Powder-coat / enamel paint whose worn edges chip to bare metal."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    src = _rgb(nt, paint)
    _weather(
        nt,
        b,
        src,
        base_rough=roughness,
        edge_color=metal,
        edge_amt=chip,
        edge_metallic=0.9,
        base_metallic=0.0,
        dirt=0.5,
        dirt_color=(0.012, 0.012, 0.010),
        dust=dust,
        dust_color=(0.30, 0.28, 0.23),
        bump_strength=0.035,
        bump_scale=bump_scale,
    )
    return m


def wood_material(
    name,
    dark,
    light,
    edge=(0.24, 0.15, 0.075),
    grain_scale=(0.5, 13.0, 2.0),
    roughness=0.52,
):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "IOR", 1.5)

    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = grain_scale
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 2.3
    wave.inputs["Distortion"].default_value = 10.0
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 1.3
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    fibre = _noise(nt, 24.0, vec=mapping.outputs["Vector"])
    grain = _mix(
        nt,
        fac=0.35,
        c1_sock=wave.outputs["Color"],
        c2_sock=fibre.outputs["Color"],
        blend="MULTIPLY",
    )
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(grain, ramp.inputs["Fac"])
    # per-object (per-plank) colour variation
    obj = nt.nodes.new("ShaderNodeObjectInfo")
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    nt.links.new(ramp.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(
        _maprange(nt, obj.outputs["Random"], 0.0, 1.0, 0.47, 0.53), hsv.inputs["Hue"]
    )
    nt.links.new(
        _maprange(nt, obj.outputs["Random"], 0.0, 1.0, 0.78, 1.20), hsv.inputs["Value"]
    )
    # wood-grain bump chained under the weather micro-bump
    grain_bump = nt.nodes.new("ShaderNodeBump")
    grain_bump.inputs["Strength"].default_value = 0.18
    grain_bump.inputs["Distance"].default_value = 0.004
    nt.links.new(grain, grain_bump.inputs["Height"])
    _weather(
        nt,
        b,
        hsv.outputs["Color"],
        base_rough=roughness,
        edge_color=edge,
        edge_amt=0.3,
        edge_metallic=0.0,
        base_metallic=0.0,
        dirt=0.28,
        dirt_color=(0.02, 0.012, 0.006),
        dust=0.22,
        dust_color=(0.26, 0.24, 0.19),
        bump_strength=0.09,
        bump_scale=150.0,
        base_normal=grain_bump.outputs["Normal"],
    )
    return m


def concrete_material(name="plaza_concrete"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "Metallic", 0.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    # blotchy base tone
    base = _mix(
        nt,
        fac_sock=_noise(nt, 3.5, vec=coord.outputs["Object"]).outputs["Fac"],
        c1=(0.11, 0.11, 0.115),
        c2=(0.20, 0.195, 0.19),
    )
    # large dark stains
    stained = _mix(
        nt,
        fac_sock=_maprange(
            nt,
            _noise(nt, 1.6, vec=coord.outputs["Object"]).outputs["Fac"],
            0.35,
            0.62,
            0.0,
            0.7,
        ),
        c1_sock=base,
        c2=(0.055, 0.05, 0.045),
    )
    # crack lines from voronoi edges
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 5.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    crack = _maprange(nt, vor.outputs["Distance"], 0.0, 0.03, 0.0, 1.0)
    cracked = _mix(
        nt,
        fac_sock=_math(nt, "SUBTRACT", a=1.0, b_sock=crack),
        c1_sock=stained,
        c2=(0.03, 0.03, 0.03),
    )
    nt.links.new(cracked, b.inputs["Base Color"])
    _set(b, "Roughness", 0.9)
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.18
    nt.links.new(
        _noise(nt, 180.0, vec=coord.outputs["Object"]).outputs["Fac"],
        bmp.inputs["Height"],
    )
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    return m


def grass_material(name="lawn"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "Roughness", 0.92)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    fine = _mix(
        nt,
        fac_sock=_noise(nt, 110.0, vec=coord.outputs["Object"]).outputs["Fac"],
        c1=(0.035, 0.060, 0.016),
        c2=(0.075, 0.110, 0.030),
    )
    patch = _mix(
        nt,
        fac_sock=_maprange(
            nt,
            _noise(nt, 4.0, vec=coord.outputs["Object"]).outputs["Fac"],
            0.4,
            0.65,
            0.0,
            0.6,
        ),
        c1_sock=fine,
        c2=(0.10, 0.09, 0.045),
    )
    nt.links.new(patch, b.inputs["Base Color"])
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.3
    nt.links.new(
        _noise(nt, 240.0, vec=coord.outputs["Object"]).outputs["Fac"],
        bmp.inputs["Height"],
    )
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    return m


MATS = {}


def build_materials():
    MATS["wood_teak"] = wood_material(
        "wood_teak", (0.060, 0.026, 0.010), (0.17, 0.085, 0.032)
    )
    MATS["wood_oak"] = wood_material(
        "wood_oak",
        (0.085, 0.045, 0.018),
        (0.22, 0.13, 0.060),
        grain_scale=(0.5, 10.0, 2.0),
    )
    MATS["wood_dark"] = wood_material(
        "wood_dark",
        (0.030, 0.014, 0.006),
        (0.10, 0.050, 0.022),
        edge=(0.14, 0.08, 0.04),
        grain_scale=(0.5, 16.0, 2.0),
    )
    MATS["iron_green"] = paint_material(
        "iron_green", (0.012, 0.035, 0.024), roughness=0.48, chip=0.55, dust=0.45
    )
    MATS["iron_black"] = paint_material(
        "iron_black", (0.012, 0.012, 0.013), roughness=0.46, chip=0.5, dust=0.4
    )
    MATS["powder_graphite"] = paint_material(
        "powder_graphite", (0.021, 0.022, 0.026), roughness=0.55, chip=0.4, dust=0.4
    )
    MATS["bin_green"] = paint_material(
        "bin_green", (0.013, 0.045, 0.030), roughness=0.5, chip=0.5, dust=0.5
    )
    MATS["galv_steel"] = metal_material(
        "galv_steel",
        (0.30, 0.31, 0.33),
        roughness=0.44,
        edge_amt=0.2,
        dust=0.35,
        spangle=True,
        bump_scale=90.0,
        bump_strength=0.05,
    )
    MATS["steel_dark"] = metal_material(
        "steel_dark",
        (0.055, 0.057, 0.060),
        roughness=0.5,
        edge_amt=0.15,
        dust=0.3,
        bump_scale=110.0,
    )
    MATS["cast_lid"] = metal_material(
        "cast_lid",
        (0.028, 0.028, 0.030),
        roughness=0.55,
        edge_amt=0.22,
        dust=0.35,
        bump_scale=60.0,
        bump_strength=0.06,
    )
    MATS["bolt"] = metal_material(
        "bolt",
        (0.10, 0.10, 0.105),
        roughness=0.38,
        edge_amt=0.3,
        dust=0.1,
        bump_scale=200.0,
    )
    # matte mid-grey liner - reads as a real bin insert, not a black void
    MATS["liner"] = paint_material(
        "liner",
        (0.030, 0.030, 0.032),
        roughness=0.82,
        chip=0.15,
        dust=0.25,
        metal=(0.04, 0.04, 0.04),
    )
    MATS["concrete"] = concrete_material()
    MATS["grass"] = grass_material()
    print("[furn] materials:", list(MATS))


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


def cyl(name, loc, radius, depth, mat, coll, verts=32, rot=(0, 0, 0), smooth_side=True):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=depth, location=loc
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    _finish(o, mat, coll)
    if smooth_side:
        for poly in o.data.polygons:
            if abs(poly.normal.z) < 0.7:
                poly.use_smooth = True
    return o


def cone(name, loc, r1, r2, depth, mat, coll, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(
        vertices=verts, radius1=r1, radius2=r2, depth=depth, location=loc
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    _finish(o, mat, coll)
    for poly in o.data.polygons:
        if abs(poly.normal.z) < 0.9:
            poly.use_smooth = True
    return o


def torus(name, loc, major, minor, mat, coll, rot=(0, 0, 0), verts=56, minor_verts=16):
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
    return _finish(o, mat, coll, shade_smooth=True)


def hemisphere(name, loc, radius, mat, coll, squash=0.5, segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=segments // 2, radius=radius, location=(0, 0, 0)
    )
    o = bpy.context.object
    o.name = name
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    kill = [v for v in bm.verts if v.co.z < -1e-4]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    o.scale = (1.0, 1.0, squash)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.location = loc
    return _finish(o, mat, coll, shade_smooth=True)


def bezier_tube(name, knots, radius, mat, coll, res=12):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    cu.resolution_u = res
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(knots) - 1)
    for i, p in enumerate(knots):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    return link_to(o, coll)


def bolt(name, loc, mat, coll, r=0.013, depth=0.022, axis="y"):
    rot = {
        "x": (0, math.radians(90), 0),
        "y": (math.radians(90), 0, 0),
        "z": (0, 0, 0),
    }[axis]
    return cyl(name, loc, r, depth, mat, coll, verts=12, rot=rot)


# --------------------------------------------------------------------------- #
# BENCHES
# --------------------------------------------------------------------------- #
def bench_classic(ox, oy, coll):
    """Victorian park bench: flat cast-iron scroll ends + wooden slats + bolts."""
    wood, iron, blt = MATS["wood_teak"], MATS["iron_green"], MATS["bolt"]
    objs = []
    L = 0.86
    seat_z = 0.44
    for i, sy in enumerate([-0.21, -0.126, -0.042, 0.042, 0.126, 0.21]):
        objs.append(
            box(
                f"clbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.070, 0.030),
                wood,
                coll,
                bevel=0.011,
            )
        )
    tilt = math.radians(14)
    for i in range(4):
        z = 0.55 + i * 0.093
        yy = oy + 0.245 + i * 0.023
        objs.append(
            box(
                f"clbench:back:{i}",
                (ox, yy, z),
                (2 * L, 0.068, 0.026),
                wood,
                coll,
                bevel=0.010,
                rot=(tilt, 0, 0),
            )
        )
    # flat cast-iron end castings
    for sx in (-L - 0.02, L + 0.02):
        x = ox + sx
        objs.append(
            box(
                f"clbench:foot:{sx:.2f}",
                (x, oy - 0.02, 0.03),
                (0.05, 0.66, 0.055),
                iron,
                coll,
                bevel=0.012,
            )
        )
        objs.append(
            box(
                f"clbench:frontleg:{sx:.2f}",
                (x, oy - 0.26, 0.24),
                (0.045, 0.10, 0.46),
                iron,
                coll,
                bevel=0.012,
            )
        )
        objs.append(
            box(
                f"clbench:rearleg:{sx:.2f}",
                (x, oy + 0.30, 0.47),
                (0.045, 0.10, 0.92),
                iron,
                coll,
                bevel=0.012,
                rot=(math.radians(-4), 0, 0),
            )
        )
        objs.append(
            box(
                f"clbench:seatsup:{sx:.2f}",
                (x, oy + 0.02, seat_z - 0.035),
                (0.05, 0.56, 0.05),
                iron,
                coll,
                bevel=0.012,
            )
        )
        # rolled armrest (flat bar) + front scroll curl
        objs.append(
            box(
                f"clbench:arm:{sx:.2f}",
                (x, oy - 0.05, 0.70),
                (0.05, 0.58, 0.05),
                iron,
                coll,
                bevel=0.014,
                rot=(math.radians(-5), 0, 0),
            )
        )
        objs.append(
            box(
                f"clbench:armpost:{sx:.2f}",
                (x, oy - 0.30, 0.58),
                (0.045, 0.06, 0.26),
                iron,
                coll,
                bevel=0.010,
            )
        )
        objs.append(
            bezier_tube(
                f"clbench:armcurl:{sx:.2f}",
                [
                    (x, oy - 0.34, 0.68),
                    (x, oy - 0.40, 0.66),
                    (x, oy - 0.40, 0.58),
                    (x, oy - 0.33, 0.57),
                ],
                0.020,
                iron,
                coll,
            )
        )
        # decorative scroll under the arm
        objs.append(
            bezier_tube(
                f"clbench:scroll:{sx:.2f}",
                [
                    (x, oy - 0.22, 0.50),
                    (x, oy - 0.10, 0.54),
                    (x, oy - 0.09, 0.63),
                    (x, oy - 0.19, 0.64),
                    (x, oy - 0.24, 0.57),
                ],
                0.013,
                iron,
                coll,
            )
        )
        # bolt fixings where slats meet the frame
        bxo = 0.03 if sx > 0 else -0.03
        for by in (-0.18, 0.18):
            objs.append(
                bolt(
                    f"clbench:bolt_s:{sx:.2f}:{by:.2f}",
                    (x + bxo, oy + by, seat_z),
                    blt,
                    coll,
                    axis="x",
                )
            )
        for bz in (0.60, 0.80):
            objs.append(
                bolt(
                    f"clbench:bolt_b:{sx:.2f}:{bz:.2f}",
                    (x + bxo, oy + 0.30, bz),
                    blt,
                    coll,
                    axis="x",
                )
            )
    # cross members between the two ends
    objs.append(
        box(
            "clbench:rail_seat",
            (ox, oy + 0.02, seat_z - 0.06),
            (2 * L, 0.05, 0.05),
            iron,
            coll,
            bevel=0.010,
        )
    )
    objs.append(
        box(
            "clbench:rail_low",
            (ox, oy - 0.06, 0.12),
            (2 * L - 0.12, 0.045, 0.045),
            iron,
            coll,
            bevel=0.010,
        )
    )
    objs.append(
        box(
            "clbench:back_rail",
            (ox, oy + 0.34, 0.90),
            (2 * L, 0.05, 0.05),
            iron,
            coll,
            bevel=0.010,
        )
    )
    return objs


def bench_modern(ox, oy, coll):
    """Modern bench: powder-coated steel sled frame + wood slats + bolts."""
    wood, metal, blt = MATS["wood_oak"], MATS["powder_graphite"], MATS["bolt"]
    objs = []
    L = 0.80
    seat_z = 0.43
    for i, sy in enumerate([-0.19, -0.095, 0.0, 0.095, 0.19]):
        objs.append(
            box(
                f"mbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.078, 0.032),
                wood,
                coll,
                bevel=0.013,
            )
        )
    for i in range(3):
        z = 0.56 + i * 0.10
        objs.append(
            box(
                f"mbench:back:{i}",
                (ox, oy + 0.26, z),
                (2 * L, 0.078, 0.030),
                wood,
                coll,
                bevel=0.013,
                rot=(math.radians(6), 0, 0),
            )
        )
    for sx in (-L + 0.10, L - 0.10):
        x = ox + sx
        bar = 0.05
        objs.append(
            box(
                f"mbench:foot:{sx:.2f}",
                (x, oy - 0.02, 0.025),
                (bar, 0.66, 0.05),
                metal,
                coll,
                bevel=0.009,
            )
        )
        objs.append(
            box(
                f"mbench:up_f:{sx:.2f}",
                (x, oy - 0.24, seat_z / 2 + 0.02),
                (bar, 0.05, seat_z),
                metal,
                coll,
                bevel=0.009,
            )
        )
        objs.append(
            box(
                f"mbench:up_r:{sx:.2f}",
                (x, oy + 0.24, 0.34),
                (bar, 0.05, 0.66),
                metal,
                coll,
                bevel=0.009,
            )
        )
        objs.append(
            box(
                f"mbench:cross:{sx:.2f}",
                (x, oy, seat_z - 0.035),
                (bar, 0.60, 0.05),
                metal,
                coll,
                bevel=0.009,
            )
        )
        objs.append(
            box(
                f"mbench:rake:{sx:.2f}",
                (x, oy + 0.255, 0.64),
                (bar, 0.05, 0.34),
                metal,
                coll,
                bevel=0.009,
                rot=(math.radians(6), 0, 0),
            )
        )
        for by in (-0.15, 0.15):
            objs.append(
                bolt(
                    f"mbench:bolt:{sx:.2f}:{by:.2f}",
                    (x, oy + by, seat_z + 0.017),
                    blt,
                    coll,
                    r=0.010,
                    axis="z",
                )
            )
    return objs


def bench_wooden(ox, oy, coll):
    """Chunky all-timber A-frame garden bench with steel bolt caps."""
    wood, metal = MATS["wood_dark"], MATS["steel_dark"]
    objs = []
    L = 0.82
    seat_z = 0.45
    for i, sy in enumerate([-0.17, 0.0, 0.17]):
        objs.append(
            box(
                f"wbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.16, 0.045),
                wood,
                coll,
                bevel=0.015,
            )
        )
    for i in range(2):
        z = 0.60 + i * 0.16
        objs.append(
            box(
                f"wbench:back:{i}",
                (ox, oy + 0.27, z),
                (2 * L, 0.16, 0.040),
                wood,
                coll,
                bevel=0.014,
                rot=(math.radians(10), 0, 0),
            )
        )
    for sx in (-L + 0.14, L - 0.14):
        x = ox + sx
        objs.append(
            box(
                f"wbench:leg_f:{sx:.2f}",
                (x, oy - 0.20, seat_z / 2),
                (0.09, 0.14, seat_z + 0.02),
                wood,
                coll,
                bevel=0.011,
                rot=(math.radians(-9), 0, 0),
            )
        )
        objs.append(
            box(
                f"wbench:leg_r:{sx:.2f}",
                (x, oy + 0.28, 0.38),
                (0.09, 0.14, 0.80),
                wood,
                coll,
                bevel=0.011,
                rot=(math.radians(8), 0, 0),
            )
        )
        objs.append(
            box(
                f"wbench:apron:{sx:.2f}",
                (x, oy + 0.03, seat_z - 0.08),
                (0.06, 0.52, 0.10),
                wood,
                coll,
                bevel=0.009,
            )
        )
        for sy in (-0.20, 0.28):
            objs.append(
                bolt(
                    f"wbench:bolt:{sx:.2f}:{sy:.2f}",
                    (ox + sx, oy + sy, seat_z - 0.02),
                    metal,
                    coll,
                    r=0.017,
                    depth=0.11,
                    axis="x",
                )
            )
    objs.append(
        box(
            "wbench:stretch",
            (ox, oy + 0.02, 0.16),
            (2 * L - 0.30, 0.07, 0.09),
            wood,
            coll,
            bevel=0.009,
        )
    )
    return objs


# --------------------------------------------------------------------------- #
# TRASH BINS
# --------------------------------------------------------------------------- #
def bin_mesh(ox, oy, coll):
    """Galvanised wire-mesh street bin: bars + rolled rim + hoops on feet."""
    steel, liner = MATS["galv_steel"], MATS["liner"]
    objs = []
    R = 0.27
    z0, z1 = 0.16, 0.86
    h = z1 - z0
    cz = (z0 + z1) / 2
    n_bars = 48
    for i in range(n_bars):
        a = i / n_bars * TAU
        x = ox + math.cos(a) * R
        y = oy + math.sin(a) * R
        objs.append(
            cyl(f"binmesh:bar:{i}", (x, y, cz), 0.0075, h, steel, coll, verts=8)
        )
    for i, z in enumerate([z0 + 0.02, cz, z1 - 0.03]):
        objs.append(torus(f"binmesh:hoop:{i}", (ox, oy, z), R, 0.010, steel, coll))
    # thick rolled top rim
    objs.append(torus("binmesh:rim", (ox, oy, z1), R + 0.012, 0.018, steel, coll))
    # base plate + matte liner (not a void)
    objs.append(
        cyl(
            "binmesh:bottom", (ox, oy, z0 + 0.02), R - 0.01, 0.03, steel, coll, verts=44
        )
    )
    objs.append(
        cyl(
            "binmesh:liner",
            (ox, oy, cz + 0.02),
            R - 0.028,
            h - 0.05,
            liner,
            coll,
            verts=44,
        )
    )
    for i in range(3):
        a = i / 3 * TAU + 0.4
        x = ox + math.cos(a) * (R - 0.03)
        y = oy + math.sin(a) * (R - 0.03)
        objs.append(
            cyl(f"binmesh:foot:{i}", (x, y, z0 / 2), 0.015, z0, steel, coll, verts=10)
        )
    return objs


def bin_domed(ox, oy, coll):
    """Painted-metal covered street bin: tapered body, flat dome + finial, flap."""
    body, lid, liner = MATS["bin_green"], MATS["cast_lid"], MATS["liner"]
    objs = []
    R = 0.30
    objs.append(
        cone("bindome:body", (ox, oy, 0.44), R, R - 0.035, 0.80, body, coll, verts=56)
    )
    objs.append(torus("bindome:base", (ox, oy, 0.05), R + 0.006, 0.03, body, coll))
    # a mid-body seam band
    objs.append(torus("bindome:band", (ox, oy, 0.42), R - 0.012, 0.012, lid, coll))
    objs.append(torus("bindome:rim", (ox, oy, 0.84), R + 0.006, 0.022, body, coll))
    # flatter dome + finial ball
    objs.append(
        hemisphere("bindome:lid", (ox, oy, 0.85), R - 0.006, lid, coll, squash=0.40)
    )
    objs.append(cyl("bindome:neck", (ox, oy, 0.95), 0.02, 0.04, lid, coll, verts=14))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(ox, oy, 0.98))
    fin = bpy.context.object
    fin.name = "bindome:finial"
    _finish(fin, lid, coll, shade_smooth=True)
    objs.append(fin)
    # recessed push flap
    objs.append(
        box(
            "bindome:flap_frame",
            (ox, oy - R + 0.02, 0.55),
            (0.30, 0.05, 0.30),
            lid,
            coll,
            bevel=0.013,
        )
    )
    objs.append(
        box(
            "bindome:flap",
            (ox, oy - R - 0.005, 0.55),
            (0.24, 0.03, 0.24),
            liner,
            coll,
            bevel=0.010,
            rot=(math.radians(-12), 0, 0),
        )
    )
    objs.append(
        cyl("bindome:liner", (ox, oy, 0.50), R - 0.06, 0.66, liner, coll, verts=44)
    )
    return objs


def bin_wooden(ox, oy, coll):
    """Timber-slat park bin: wood slats + steel bands + flared steel mouth."""
    wood, steel, liner = MATS["wood_teak"], MATS["steel_dark"], MATS["liner"]
    objs = []
    R = 0.28
    z0, z1 = 0.06, 0.80
    h = z1 - z0
    cz = (z0 + z1) / 2
    n = 18
    for i in range(n):
        a = i / n * TAU
        x = ox + math.cos(a) * R
        y = oy + math.sin(a) * R
        objs.append(
            box(
                f"binwood:slat:{i}",
                (x, y, cz),
                (0.055, 0.022, h),
                wood,
                coll,
                bevel=0.004,
                rot=(0, 0, a),
            )
        )
    for z in (z0 + 0.04, cz, z1 - 0.02):
        objs.append(
            torus(f"binwood:band:{z:.2f}", (ox, oy, z), R + 0.012, 0.014, steel, coll)
        )
    objs.append(
        cone(
            "binwood:mouth",
            (ox, oy, z1 + 0.03),
            R + 0.02,
            R + 0.05,
            0.06,
            steel,
            coll,
            verts=44,
        )
    )
    objs.append(
        cyl(
            "binwood:bottom", (ox, oy, z0 + 0.02), R - 0.01, 0.03, steel, coll, verts=40
        )
    )
    objs.append(
        cyl(
            "binwood:liner",
            (ox, oy, cz + 0.02),
            R - 0.03,
            h - 0.04,
            liner,
            coll,
            verts=40,
        )
    )
    return objs


# --------------------------------------------------------------------------- #
# Showroom layout
# --------------------------------------------------------------------------- #
PIECES = [
    ("bench_01_classic", "CLASSIC PARK BENCH", "bench", bench_classic),
    ("bin_01_mesh", "WIRE-MESH BIN", "bin", bin_mesh),
    ("bench_02_modern", "MODERN SLAT BENCH", "bench", bench_modern),
    ("bin_02_domed", "DOMED COVER BIN", "bin", bin_domed),
    ("bench_03_wooden", "TIMBER GARDEN BENCH", "bench", bench_wooden),
    ("bin_03_wooden", "TIMBER SLAT BIN", "bin", bin_wooden),
]
SPACING = 2.6
BASE_Y = 0.0
YAWS = [-5.0, 4.0, -3.0, 6.0, -4.0, 3.0]  # small deterministic tilt per piece


def piece_positions():
    n = len(PIECES)
    x0 = -(n - 1) / 2 * SPACING
    return {key: (x0 + i * SPACING, BASE_Y) for i, (key, *_) in enumerate(PIECES)}


def apply_yaw(objs, center, deg):
    """Rotate a piece a few degrees about its own vertical axis (via a parent
    empty) so nothing is robotically aligned."""
    e = bpy.data.objects.new(f"yaw_{center[0]:.2f}", None)
    bpy.context.scene.collection.objects.link(e)
    e.location = (center[0], center[1], 0.0)
    inv = Matrix.Translation((-center[0], -center[1], 0.0))
    for o in objs:
        o.parent = e
        o.matrix_parent_inverse = inv
    e.rotation_euler[2] = math.radians(deg)
    return e


def build_pieces(coll):
    pos = piece_positions()
    for i, (key, _label, _kind, builder) in enumerate(PIECES):
        x, y = pos[key]
        objs = builder(x, y, coll)
        apply_yaw(objs, (x, y), YAWS[i])
    return pos


def make_label(name, text, loc, coll):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.align_x = "CENTER"
    cu.size = 0.16
    obj = bpy.data.objects.new(name, cu)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(MATS["steel_dark"])
    return link_to(obj, coll)


def build_ground(coll):
    box("plaza", (0, 0.0, -0.02), (19.0, 4.6, 0.04), MATS["concrete"], coll, bevel=0.0)
    box("lawn", (0, 6.0, -0.06), (70.0, 70.0, 0.04), MATS["grass"], coll, bevel=0.0)


# --------------------------------------------------------------------------- #
# World / camera / render
# --------------------------------------------------------------------------- #
def build_world():
    world = bpy.data.worlds.new("furn_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(48)
    sky.sun_rotation = math.radians(-40)
    sky.altitude = 250
    sky.air_density = 1.0
    sky.dust_density = 0.6
    bg.inputs["Strength"].default_value = 0.55  # stronger ambient + reflections
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_lights():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    sun = bpy.context.object
    sun.data.energy = 2.4
    sun.data.angle = math.radians(3.5)
    sun.data.color = (1.0, 0.96, 0.88)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-40))
    # big soft-box: gives metal / paint real speculars + something to reflect
    loc = Vector((3.5, -7.5, 6.5))
    bpy.ops.object.light_add(type="AREA", location=loc)
    sb = bpy.context.object
    sb.data.shape = "RECTANGLE"
    sb.data.size = 9.0
    sb.data.size_y = 4.0
    sb.data.energy = 900.0
    sb.data.color = (0.9, 0.94, 1.0)
    sb.rotation_euler = (
        (Vector((0, 0.3, 0.6)) - loc).to_track_quat("-Z", "Y").to_euler()
    )


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
    print(f"[furn] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 12
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
    scene.view_settings.exposure = -1.7
    print(
        f"[furn] view={scene.view_settings.view_transform} "
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
    print(f"[furn] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


def render_orbit_video(center, radius, height, path, samples=140, frames=72):
    scene = bpy.context.scene
    cam = make_camera(
        "orbit_cam",
        (center[0] + radius, center[1], height),
        center,
        lens=45,
        fstop=None,
    )
    focus = Vector((center[0], center[1], center[2]))
    for f in range(1, frames + 1):
        ang = (f - 1) / frames * TAU
        loc = Vector(
            (
                center[0] + math.cos(ang) * radius,
                center[1] + math.sin(ang) * radius,
                height,
            )
        )
        cam.location = loc
        cam.rotation_euler = (focus - loc).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    scene.camera = cam
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = (1280, 720)
    scene.frame_start, scene.frame_end = 1, frames
    scene.render.fps = 24
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(FRAMES_DIR / "orbit_")
    print("[furn] render orbit frames ...")
    bpy.ops.render.render(animation=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        "24",
        "-i",
        str(FRAMES_DIR / "orbit_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(
            f"[furn] video muxed -> {path.name} " f"({path.stat().st_size // 1024} KiB)"
        )
    except Exception as exc:
        print(f"[furn] ffmpeg mux failed: {exc!r}")


# --------------------------------------------------------------------------- #
def main():
    reset_scene()
    build_materials()

    ground_c = add_collection("furn_ground")
    pieces_c = add_collection("furn_pieces")
    label_c = add_collection("furn_labels")

    build_ground(ground_c)
    pos = build_pieces(pieces_c)
    for key, label, _kind, _b in PIECES:
        cx, cy = pos[key]
        make_label(f"label_{key}", label, (cx, cy - 0.62, 0.03), label_c)

    build_world()
    add_lights()
    configure_cycles()

    keys = [p[0] for p in PIECES]
    hx = (pos[keys[0]][0] + pos[keys[1]][0]) / 2

    hero_cam = make_camera(
        "hero_cam", (hx + 1.6, -3.3, 1.5), (hx, 0.05, 0.5), lens=45, fstop=4.0
    )
    overview_cam = make_camera(
        "overview_cam", (0.0, -11.5, 7.4), (0.0, 0.3, 0.4), lens=28
    )
    gallery_cam = make_camera(
        "gallery_cam", (0.0, -11.8, 3.7), (0.0, 0.1, 0.55), lens=24
    )

    bpy.context.scene.camera = hero_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    if os.environ.get("FURN_QUICK"):
        render_still(
            gallery_cam, OUTPUT_DIR / "quick_gallery.png", samples=56, res=(1280, 720)
        )
        render_still(
            hero_cam, OUTPUT_DIR / "quick_hero.png", samples=56, res=(1280, 720)
        )
        print("[furn] QUICK done ->", OUTPUT_DIR)
        return

    render_still(hero_cam, HERO_PNG, samples=340)
    render_still(overview_cam, OVERVIEW_PNG, samples=260)
    render_still(gallery_cam, GALLERY_PNG, samples=260)
    for key, label, kind, _b in PIECES:
        cx, cy = pos[key]
        look_z = 0.55 if kind == "bench" else 0.5
        cam = make_camera(
            f"cam_{key}",
            (cx + 1.35, cy - 2.5, 1.35),
            (cx, cy, look_z),
            lens=50,
            fstop=3.5,
        )
        render_still(cam, OUTPUT_DIR / f"{key}.png", samples=240)

    render_orbit_video(
        (hx, 0.05, 0.55),
        radius=4.4,
        height=1.9,
        path=VIDEO_PATH,
        samples=150,
        frames=72,
    )

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[furn] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
