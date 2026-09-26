"""Photorealistic procedural SHARED-BICYCLE + DOCKING-STATION showcase - v2
(urban_v3_sharedbicycle2).

Reworked from a study of real share-bikes (HelloRide blue/white; a yellow
ofo/Meituan-style bike) to shed the "toy" look and add the details those photos
show:

  * REAR SOLID-DISC WHEEL (branded) + spoked front wheel, COLOURED RIMS, thinner
    tyres  - the signature share-bike cue.
  * fat front DRUM-BRAKE hub; brake/gear CABLES routed along the frame; BRAKE
    LEVERS + BELL on the bar.
  * REFLECTORS (red rear, white front, amber pedal); MUDGUARD STAYS; a DOUBLE
    CENTRE KICKSTAND.
  * a WHITE gradient panel + brand wordmark on the down tube (two-tone livery);
    the front BASKET dropped low over the front wheel on a head-tube bracket.
  * an ergonomic contoured SADDLE (not a round dome).

Fleet is shown in the four requested white-based liveries - blue / orange /
yellow / pink - one per docked bike, so a single scheme can be chosen later.
The kiosk's floating roof solar panel is removed (replaced by a flush cap).

Rendered with Cycles + OptiX GPU, Nishita sky, AgX, depth-of-field.

Run:
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_sharedbicycle2.py
  (BIKE_QUICK=1 -> fast smoke test; URBAN_BIKE_OUT overrides out dir)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sharedbicycle2):
  bike_station.blend, bicycle.png (hero), _overview, _gallery,
  detail_*.png close-ups, bicycle_orbit.mp4
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
        "URBAN_BIKE_OUT",
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sharedbicycle2",
    )
)
FRAMES_DIR = OUTPUT_DIR / "frames"
TMP_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
for d in (OUTPUT_DIR, FRAMES_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

SCENE_PATH = OUTPUT_DIR / "bike_station.blend"
HERO_PNG = OUTPUT_DIR / "bicycle.png"
OVERVIEW_PNG = OUTPUT_DIR / "bicycle_overview.png"
GALLERY_PNG = OUTPUT_DIR / "bicycle_gallery.png"
VIDEO_PATH = OUTPUT_DIR / "bicycle_orbit.mp4"

TAU = math.tau
BRAND = "VELO"


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
# Node-graph helpers (shared with the bench/bin v2 realism pass)
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
    chip = _math(
        nt,
        "MULTIPLY",
        a_sock=_maprange(nt, geo.outputs["Pointiness"], 0.54, 0.66, 0.0, 1.0),
        b=edge_amt,
    )
    dirt_f = _math(
        nt,
        "MULTIPLY",
        a_sock=_maprange(nt, geo.outputs["Pointiness"], 0.47, 0.30, 0.0, 1.0),
        b=dirt,
    )
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["True Normal"], sep.inputs["Vector"])
    up = _maprange(nt, sep.outputs["Z"], 0.2, 0.7, 0.0, 1.0)
    dust_f = _math(
        nt,
        "MULTIPLY",
        a_sock=_math(nt, "MULTIPLY", a_sock=up, b_sock=_noise(nt, 24.0).outputs["Fac"]),
        b=dust,
    )
    c1 = _mix(nt, fac_sock=chip, c1_sock=base_socket, c2=edge_color)
    c2 = _mix(nt, fac_sock=dirt_f, c1_sock=c1, c2=dirt_color)
    c3 = _mix(nt, fac_sock=dust_f, c1_sock=c2, c2=dust_color)
    nt.links.new(c3, b.inputs["Base Color"])
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
    if spangle:
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
    coat=0.0,
):
    """Powder-coat / enamel paint whose worn edges chip to bare metal."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    if coat > 0:
        _set(b, "Coat Weight", coat)
        _set(b, "Coat Roughness", 0.12)
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
        bump_strength=0.03,
        bump_scale=bump_scale,
    )
    return m


def rubber_material(name="tyre", color=(0.011, 0.011, 0.013)):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    src = _rgb(nt, color)
    _weather(
        nt,
        b,
        src,
        base_rough=0.72,
        edge_color=(0.05, 0.05, 0.05),
        edge_amt=0.06,
        edge_metallic=0.0,
        base_metallic=0.0,
        dirt=0.4,
        dirt_color=(0.03, 0.028, 0.022),
        dust=0.45,
        dust_color=(0.24, 0.22, 0.18),
        bump_strength=0.10,
        bump_scale=55.0,
    )
    return m


def reflector_material(name, color, emit=0.7):
    """Small self-lit reflector (red/amber/white)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = _principled(m)
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", 0.28)
    _set(b, "Emission Color", (*color, 1.0))
    _set(b, "Emission Strength", emit)
    _set(b, "Coat Weight", 0.5)
    return m


def solar_material(name="solar"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    checker = nt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 26.0
    checker.inputs["Color1"].default_value = (0.010, 0.020, 0.055, 1.0)
    checker.inputs["Color2"].default_value = (0.016, 0.032, 0.085, 1.0)
    nt.links.new(coord.outputs["Object"], checker.inputs["Vector"])
    grid = nt.nodes.new("ShaderNodeTexChecker")
    grid.inputs["Scale"].default_value = 52.0
    grid.inputs["Color1"].default_value = (1.0, 1.0, 1.0, 1.0)
    grid.inputs["Color2"].default_value = (0.2, 0.2, 0.2, 1.0)
    nt.links.new(coord.outputs["Object"], grid.inputs["Vector"])
    cells = _mix(
        nt,
        fac_sock=grid.outputs["Color"],
        c1=(0.004, 0.006, 0.014),
        c2_sock=checker.outputs["Color"],
    )
    nt.links.new(cells, b.inputs["Base Color"])
    _set(b, "Metallic", 0.35)
    _set(b, "Roughness", 0.16)
    _set(b, "Coat Weight", 0.7)
    _set(b, "Coat Roughness", 0.08)
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
    base = _mix(
        nt,
        fac_sock=_noise(nt, 3.5, vec=coord.outputs["Object"]).outputs["Fac"],
        c1=(0.11, 0.11, 0.115),
        c2=(0.20, 0.195, 0.19),
    )
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

# four white-based liveries (main linear colour, logo-contrast: 'w' or 'd')
SCHEME_LIST = [
    ("blue", (0.015, 0.075, 0.42), "w"),
    ("orange", (0.62, 0.135, 0.012), "w"),
    ("yellow", (0.70, 0.47, 0.015), "d"),
    ("pink", (0.62, 0.085, 0.26), "w"),
]
SCHEMES = {s: (c, lg) for s, c, lg in SCHEME_LIST}
_SCHEME_CACHE = {}


def get_scheme(name):
    if name in _SCHEME_CACHE:
        return _SCHEME_CACHE[name]
    color, lg = SCHEMES[name]
    d = {
        "main": paint_material(
            f"main_{name}", color, roughness=0.30, chip=0.16, dust=0.24, coat=0.55
        ),
        "rim": paint_material(
            f"rim_{name}", color, roughness=0.34, chip=0.20, dust=0.22
        ),
        "disc": paint_material(
            f"disc_{name}", color, roughness=0.34, chip=0.12, dust=0.22, coat=0.4
        ),
        "logo": MATS["logo_w"] if lg == "w" else MATS["logo_d"],
    }
    _SCHEME_CACHE[name] = d
    return d


def build_materials():
    # shared parts
    MATS["white"] = paint_material(
        "bike_white", (0.62, 0.62, 0.60), roughness=0.34, chip=0.08, dust=0.20, coat=0.5
    )
    MATS["alu"] = metal_material(
        "bike_alu",
        (0.60, 0.62, 0.64),
        roughness=0.32,
        edge_amt=0.22,
        dust=0.2,
        bump_scale=150.0,
    )
    MATS["alu_dark"] = metal_material(
        "bike_alu_dark",
        (0.17, 0.18, 0.20),
        roughness=0.44,
        edge_amt=0.2,
        dust=0.25,
        bump_scale=140.0,
    )
    MATS["tyre"] = rubber_material("bike_tyre")
    MATS["saddle"] = paint_material(
        "bike_saddle",
        (0.010, 0.010, 0.012),
        roughness=0.90,
        chip=0.015,
        dust=0.04,
        metal=(0.0, 0.0, 0.0),
        coat=0.0,
    )
    # a saddle is a large top-facing surface: drop the specular so it doesn't
    # mirror the bright sky dome into a grey wash (tyres stay black by facing sideways)
    _set(_principled(MATS["saddle"]), "Specular IOR Level", 0.18)
    MATS["grip"] = paint_material(
        "bike_grip",
        (0.022, 0.020, 0.020),
        roughness=0.62,
        chip=0.05,
        dust=0.2,
        metal=(0.03, 0.03, 0.03),
    )
    MATS["cable"] = paint_material(
        "bike_cable", (0.020, 0.020, 0.023), roughness=0.5, chip=0.05, dust=0.15
    )
    MATS["basket"] = paint_material(
        "bike_basket", (0.030, 0.031, 0.034), roughness=0.5, chip=0.12, dust=0.3
    )
    MATS["lock"] = paint_material(
        "bike_lock", (0.024, 0.025, 0.028), roughness=0.5, chip=0.15, dust=0.3
    )
    MATS["solar"] = solar_material("bike_solar")
    MATS["logo_w"] = paint_material(
        "logo_white", (0.75, 0.74, 0.71), roughness=0.34, chip=0.04, dust=0.10, coat=0.4
    )
    MATS["logo_d"] = paint_material(
        "logo_dark", (0.020, 0.020, 0.022), roughness=0.4, chip=0.04, dust=0.10
    )
    MATS["refl_red"] = reflector_material("refl_red", (0.55, 0.02, 0.02))
    MATS["refl_amber"] = reflector_material("refl_amber", (0.60, 0.28, 0.01))
    MATS["refl_white"] = reflector_material("refl_white", (0.60, 0.60, 0.58), emit=0.4)
    # station
    MATS["steel_dark"] = metal_material(
        "dock_steel",
        (0.055, 0.057, 0.060),
        roughness=0.5,
        edge_amt=0.18,
        dust=0.3,
        bump_scale=110.0,
    )
    MATS["kiosk"] = paint_material(
        "dock_kiosk", (0.021, 0.022, 0.026), roughness=0.5, chip=0.2, dust=0.35
    )
    MATS["screen"] = paint_material(
        "dock_screen",
        (0.004, 0.005, 0.007),
        roughness=0.12,
        chip=0.02,
        dust=0.1,
        coat=0.8,
    )
    MATS["concrete"] = concrete_material()
    MATS["grass"] = grass_material()
    for name, *_ in SCHEME_LIST:
        get_scheme(name)
    print("[bike] materials:", list(MATS), "+ schemes", list(_SCHEME_CACHE))


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


def box(name, loc, dims, mat, coll, bevel=0.004, rot=(0, 0, 0)):
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


def torus(
    name,
    loc,
    major,
    minor,
    mat,
    coll,
    rot=(0, 0, 0),
    verts=56,
    minor_verts=16,
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
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=loc)
    o = bpy.context.object
    o.name = name
    if scale is not None:
        o.scale = scale
    return _finish(o, mat, coll, shade_smooth=True)


def bezier_tube(name, knots, radius, mat, coll, res=12, scale_y=1.0):
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
    if scale_y != 1.0:
        o.scale = (1.0, scale_y, 1.0)
    return link_to(o, coll)


def decal(name, text, loc, normal, up, size, mat, coll, extrude=0.003, align="CENTER"):
    """A 3-D text logo oriented by a built rotation matrix (local +Z->normal,
    +Y->up, +X->reading dir) so it faces the right way and reads un-mirrored."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = extrude
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    n = Vector(normal).normalized()
    up_v = Vector(up)
    yc = (up_v - up_v.dot(n) * n).normalized()
    xc = yc.cross(n).normalized()
    rot = Matrix((xc, yc, n)).transposed().to_4x4()
    o.matrix_world = Matrix.Translation(Vector(loc)) @ rot
    return link_to(o, coll)


# --------------------------------------------------------------------------- #
# BICYCLE  (built about local origin, front wheel toward +X)
# --------------------------------------------------------------------------- #
WHEEL_R = 0.350
TYRE_X = 0.036  # slimmer tyre (was 0.046 -> looked toy-ish)
RIM_MAJ = 0.258
AXLE_Z = WHEEL_R
FX = 0.545
RX = -0.520
BBX, BBZ = -0.05, 0.285
SPOKES = 20


def wheel_spoked(prefix, cx, cz, coll, rim_mat, drum=False):
    """Front wheel: slim tyre, coloured rim, thin steel spokes, fat drum hub."""
    objs = []
    axis_y = (math.pi / 2, 0, 0)
    objs.append(
        torus(
            f"{prefix}:tyre",
            (cx, 0, cz),
            WHEEL_R - TYRE_X,
            TYRE_X,
            MATS["tyre"],
            coll,
            rot=axis_y,
            verts=64,
            minor_verts=18,
        )
    )
    objs.append(
        torus(
            f"{prefix}:rim",
            (cx, 0, cz),
            RIM_MAJ,
            0.020,
            rim_mat,
            coll,
            rot=axis_y,
            verts=64,
            minor_verts=12,
        )
    )
    hub_r = 0.058 if drum else 0.032
    objs.append(
        cyl(
            f"{prefix}:hub",
            (cx, 0, cz),
            hub_r,
            0.11 if drum else 0.09,
            MATS["alu_dark"] if drum else MATS["alu"],
            coll,
            verts=24,
            rot=axis_y,
        )
    )
    if drum:  # drum-brake reaction arm
        objs.append(
            box(
                f"{prefix}:drumarm",
                (cx - 0.02, 0.06, cz - 0.075),
                (0.03, 0.02, 0.10),
                MATS["alu_dark"],
                coll,
                bevel=0.004,
            )
        )
    rim_r = RIM_MAJ - 0.020
    rmid = (hub_r + rim_r) / 2
    slen = rim_r - hub_r
    for i in range(SPOKES):
        a = i / SPOKES * TAU
        yoff = 0.026 if i % 2 else -0.026
        objs.append(
            cyl(
                f"{prefix}:spoke:{i}",
                (cx + math.cos(a) * rmid, yoff, cz + math.sin(a) * rmid),
                0.0024,
                slen,
                MATS["alu"],
                coll,
                verts=6,
                rot=(0, math.pi / 2 - a, 0),
            )
        )
    # valve stem
    objs.append(
        cyl(
            f"{prefix}:valve",
            (cx + rim_r - 0.01, 0.0, cz + 0.0),
            0.005,
            0.03,
            MATS["alu_dark"],
            coll,
            verts=8,
            rot=(0, math.pi / 2 - math.radians(90), 0),
        )
    )
    return objs


def wheel_disc(prefix, cx, cz, coll, disc_mat, logo_mat):
    """Rear solid-disc wheel (share-bike signature), branded on the face."""
    objs = []
    axis_y = (math.pi / 2, 0, 0)
    objs.append(
        torus(
            f"{prefix}:tyre",
            (cx, 0, cz),
            WHEEL_R - TYRE_X,
            TYRE_X,
            MATS["tyre"],
            coll,
            rot=axis_y,
            verts=64,
            minor_verts=18,
        )
    )
    for sy in (0.018, -0.018):  # two solid disc faces + a dished look
        objs.append(
            cyl(
                f"{prefix}:disc:{sy:+.2f}",
                (cx, sy, cz),
                RIM_MAJ + 0.006,
                0.010,
                disc_mat,
                coll,
                verts=64,
                rot=axis_y,
            )
        )
    objs.append(
        cyl(
            f"{prefix}:discweb",
            (cx, 0.0, cz),
            RIM_MAJ + 0.006,
            0.030,
            disc_mat,
            coll,
            verts=64,
            rot=axis_y,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:hub",
            (cx, 0, cz),
            0.05,
            0.05,
            MATS["alu_dark"],
            coll,
            verts=24,
            rot=axis_y,
        )
    )
    objs.append(
        torus(
            f"{prefix}:discring",
            (cx, 0, cz),
            RIM_MAJ - 0.05,
            0.006,
            MATS["alu_dark"],
            coll,
            rot=axis_y,
            verts=56,
        )
    )
    objs.append(
        decal(
            f"{prefix}:disc_logo",
            BRAND,
            (cx, RIM_MAJ * 0.0 + 0.026, cz),
            normal=(0, 1, 0),
            up=(0, 0, 1),
            size=0.070,
            mat=logo_mat,
            coll=coll,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:valve",
            (cx + RIM_MAJ - 0.02, 0.0, cz),
            0.005,
            0.03,
            MATS["alu_dark"],
            coll,
            verts=8,
            rot=(0, 0.0, 0),
        )
    )
    return objs


def fender(prefix, cx, cz, coll, a0, a1, mat):
    r = WHEEL_R + 0.026
    knots = []
    for t in (0.0, 0.34, 0.66, 1.0):
        a = math.radians(a0 + (a1 - a0) * t)
        knots.append((cx + math.cos(a) * r, 0.0, cz + math.sin(a) * r))
    objs = [bezier_tube(f"{prefix}:fender", knots, 0.024, mat, coll, scale_y=1.7)]
    # mudguard stays: thin rods from the two fender ends down to the axle
    for end_a in (a0, a1):
        ar = math.radians(end_a)
        for sy in (0.05, -0.05):
            objs.append(
                bezier_tube(
                    f"{prefix}:stay:{end_a:.0f}:{sy:+.2f}",
                    [
                        (
                            cx + math.cos(ar) * (r - 0.01),
                            sy,
                            cz + math.sin(ar) * (r - 0.01),
                        ),
                        (cx, sy, cz),
                    ],
                    0.0035,
                    MATS["alu"],
                    coll,
                )
            )
    return objs


def build_bicycle(coll, prefix, scheme):
    objs = []
    sc = get_scheme(scheme)
    main, rim, disc, logo = sc["main"], sc["rim"], sc["disc"], sc["logo"]
    white, alu, aldk = MATS["white"], MATS["alu"], MATS["alu_dark"]

    # ---- wheels (spoked front + drum hub, solid-disc rear) + fenders ----- #
    objs += wheel_spoked(f"{prefix}:fw", FX, AXLE_Z, coll, rim, drum=True)
    objs += wheel_disc(f"{prefix}:rw", RX, AXLE_Z, coll, disc, logo)
    objs += fender(f"{prefix}:ff", FX, AXLE_Z, coll, 38, 150, main)
    objs += fender(f"{prefix}:rf", RX, AXLE_Z, coll, 30, 152, main)

    # ---- frame tubes ------------------------------------------------------ #
    head_bot = (FX - 0.07, 0.0, 0.70)
    head_top = (FX - 0.11, 0.0, 1.02)
    seat_cluster = (-0.22, 0.0, 1.00)
    objs.append(
        bezier_tube(f"{prefix}:headtube", [head_bot, head_top], 0.025, main, coll)
    )
    objs.append(
        bezier_tube(
            f"{prefix}:downtube",
            [head_bot, (0.24, 0.0, 0.40), (BBX + 0.02, 0.0, BBZ)],
            0.026,
            main,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:topbar",
            [
                (head_top[0] - 0.02, 0.0, 0.95),
                (0.12, 0.0, 0.60),
                (-0.14, 0.0, 0.56),
                seat_cluster,
            ],
            0.024,
            main,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:seattube", [(BBX, 0.0, BBZ), seat_cluster], 0.024, main, coll
        )
    )
    for sy in (0.058, -0.058):
        objs.append(
            bezier_tube(
                f"{prefix}:chainstay:{sy:+.2f}",
                [(BBX, sy * 0.6, BBZ), (RX, sy, AXLE_Z)],
                0.013,
                main,
                coll,
            )
        )
        objs.append(
            bezier_tube(
                f"{prefix}:seatstay:{sy:+.2f}",
                [(seat_cluster[0], sy * 0.4, 0.97), (RX, sy, AXLE_Z)],
                0.012,
                main,
                coll,
            )
        )

    # ---- white two-tone panel + wordmark on the down tube ---------------- #
    panel_dir = Vector((0.06 - 0.34, 0.0, 0.34 - 0.52)).normalized()
    objs.append(
        bezier_tube(
            f"{prefix}:panel",
            [(0.34, 0.0, 0.52), (0.20, 0.0, 0.42), (0.06, 0.0, 0.34)],
            0.028,
            white,
            coll,
        )
    )
    for sgn in (1, -1):
        objs.append(
            decal(
                f"{prefix}:panel_txt:{sgn}",
                BRAND,
                (0.20, 0.030 * sgn, 0.435),
                normal=(0, sgn, 0),
                up=tuple(panel_dir),
                size=0.052,
                mat=main,
                coll=coll,
            )
        )

    # ---- fork ------------------------------------------------------------- #
    objs.append(
        bezier_tube(
            f"{prefix}:steerer", [head_bot, (FX - 0.05, 0.0, 0.64)], 0.021, aldk, coll
        )
    )
    for sy in (0.055, -0.055):
        objs.append(
            bezier_tube(
                f"{prefix}:fork:{sy:+.2f}",
                [
                    (FX - 0.05, sy * 0.4, 0.64),
                    (FX, sy, AXLE_Z + 0.10),
                    (FX, sy, AXLE_Z),
                ],
                0.015,
                aldk,
                coll,
            )
        )

    # ---- swept-back handlebar + grips + levers + bell -------------------- #
    stem_end = (FX - 0.21, 0.0, 1.11)
    objs.append(bezier_tube(f"{prefix}:stem", [head_top, stem_end], 0.018, aldk, coll))
    barL = (FX - 0.335, 0.250, 1.155)
    barR = (FX - 0.335, -0.250, 1.155)
    bar_knots = [
        barL,
        (FX - 0.255, 0.115, 1.118),
        stem_end,
        (FX - 0.255, -0.115, 1.118),
        barR,
    ]
    objs.append(bezier_tube(f"{prefix}:bar", bar_knots, 0.016, aldk, coll))
    objs.append(
        bezier_tube(
            f"{prefix}:gripL",
            [(FX - 0.298, 0.170, 1.137), barL],
            0.021,
            MATS["grip"],
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:gripR",
            [(FX - 0.298, -0.170, 1.137), barR],
            0.021,
            MATS["grip"],
            coll,
        )
    )
    for sy in (0.135, -0.135):  # brake levers
        objs.append(
            box(
                f"{prefix}:lever:{sy:+.2f}",
                (FX - 0.30, sy, 1.10),
                (0.075, 0.014, 0.02),
                aldk,
                coll,
                bevel=0.004,
                rot=(0, math.radians(18), 0),
            )
        )
    objs.append(
        cyl(
            f"{prefix}:bell",
            (FX - 0.255, 0.145, 1.135),
            0.017,
            0.02,
            aldk,
            coll,
            verts=18,
            rot=(0, 0, 0),
        )
    )
    objs.append(
        box(
            f"{prefix}:console",
            (stem_end[0] + 0.03, 0.0, stem_end[2] + 0.03),
            (0.05, 0.10, 0.03),
            MATS["lock"],
            coll,
            bevel=0.006,
        )
    )

    # ---- cables routed from the bar along the frame --------------------- #
    objs.append(
        bezier_tube(
            f"{prefix}:cable_f",
            [
                (FX - 0.28, 0.03, 1.12),
                (FX - 0.09, 0.03, 0.92),
                (FX - 0.055, 0.035, 0.70),
                (FX, 0.05, AXLE_Z + 0.07),
            ],
            0.0045,
            MATS["cable"],
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:cable_r",
            [
                (FX - 0.28, -0.03, 1.12),
                (FX - 0.10, -0.03, 0.88),
                (0.0, -0.03, 0.40),
                (RX + 0.06, 0.05, AXLE_Z + 0.12),
            ],
            0.0045,
            MATS["cable"],
            coll,
        )
    )

    # ---- ergonomic saddle ------------------------------------------------ #
    post_top = (-0.24, 0.0, 1.19)
    objs.append(
        bezier_tube(f"{prefix}:seatpost", [seat_cluster, post_top], 0.017, aldk, coll)
    )
    objs.append(
        cyl(
            f"{prefix}:seatclamp",
            (seat_cluster[0], 0.0, 1.01),
            0.026,
            0.03,
            aldk,
            coll,
            verts=16,
        )
    )
    sad = uvsphere(
        f"{prefix}:saddle",
        (post_top[0] + 0.03, 0.0, post_top[2] + 0.03),
        0.12,
        MATS["saddle"],
        coll,
        scale=(2.00, 0.68, 0.44),
    )
    for v in sad.data.vertices:
        # flatten the underside into a pan so the top reads as a padded cushion
        if v.co.z < -0.010:
            v.co.z = -0.010 + (v.co.z + 0.010) * 0.20
        if v.co.x > 0.03:  # taper the nose in width
            v.co.y *= 0.34
        if v.co.x < -0.05:  # broaden the tail (sit-bone area)
            v.co.y *= 1.08
    objs.append(sad)

    # ---- drivetrain + full chain-guard ----------------------------------- #
    axis_y = (math.pi / 2, 0, 0)
    objs.append(
        cyl(
            f"{prefix}:chainring",
            (BBX, 0.066, BBZ),
            0.085,
            0.006,
            aldk,
            coll,
            verts=40,
            rot=axis_y,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:chainguard",
            (BBX, 0.080, BBZ),
            0.125,
            0.012,
            main,
            coll,
            verts=48,
            rot=axis_y,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:bb",
            (BBX, 0.0, BBZ),
            0.027,
            0.14,
            aldk,
            coll,
            verts=18,
            rot=axis_y,
        )
    )
    for sy, cz in ((0.078, BBZ - 0.09), (-0.078, BBZ + 0.09)):
        objs.append(
            box(
                f"{prefix}:crank:{sy:+.2f}",
                (BBX, sy, cz),
                (0.030, 0.030, 0.18),
                aldk,
                coll,
                bevel=0.006,
            )
        )
        py = 0.140 if sy > 0 else -0.140
        pz = BBZ - 0.16 if sy > 0 else BBZ + 0.16
        objs.append(
            box(
                f"{prefix}:pedal:{sy:+.2f}",
                (BBX, py, pz),
                (0.10, 0.065, 0.022),
                MATS["lock"],
                coll,
                bevel=0.005,
            )
        )
        objs.append(
            box(
                f"{prefix}:pedalrefl:{sy:+.2f}",
                (BBX + 0.03, py, pz + 0.013),
                (0.025, 0.05, 0.006),
                MATS["refl_amber"],
                coll,
                bevel=0.002,
            )
        )

    # ---- low front basket over the wheel, on a head-tube bracket --------- #
    bx, bz = FX + 0.04, 0.72
    bw, bd, bh = 0.28, 0.26, 0.20
    objs.append(
        box(
            f"{prefix}:basket:floor",
            (bx, 0.0, bz - bh / 2),
            (bw, bd, 0.014),
            MATS["basket"],
            coll,
            bevel=0.006,
        )
    )
    edges = [
        ((bx - bw / 2, -bd / 2), (bx - bw / 2, bd / 2)),
        ((bx + bw / 2, -bd / 2), (bx + bw / 2, bd / 2)),
        ((bx - bw / 2, -bd / 2), (bx + bw / 2, -bd / 2)),
        ((bx - bw / 2, bd / 2), (bx + bw / 2, bd / 2)),
    ]
    for k, (p, q) in enumerate(edges):
        objs.append(
            bezier_tube(
                f"{prefix}:basket:rim{k}",
                [(p[0], p[1], bz + bh / 2), (q[0], q[1], bz + bh / 2)],
                0.008,
                MATS["basket"],
                coll,
            )
        )
    nx = 5
    for i in range(nx):
        xx = bx - bw / 2 + bw * i / (nx - 1)
        for yy in (-bd / 2, bd / 2):
            objs.append(
                cyl(
                    f"{prefix}:basket:vx:{i}:{yy:+.2f}",
                    (xx, yy, bz),
                    0.0038,
                    bh,
                    MATS["basket"],
                    coll,
                    verts=6,
                )
            )
    for j in range(4):
        yy = -bd / 2 + bd * j / 3
        for xx in (bx - bw / 2, bx + bw / 2):
            objs.append(
                cyl(
                    f"{prefix}:basket:vy:{j}:{xx:+.2f}",
                    (xx, yy, bz),
                    0.0038,
                    bh,
                    MATS["basket"],
                    coll,
                    verts=6,
                )
            )
    objs.append(
        bezier_tube(
            f"{prefix}:basket:bracket",
            [(bx - bw / 2, 0.0, bz), (FX - 0.09, 0.0, 0.80)],
            0.011,
            aldk,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:basket:legstay",
            [(bx, 0.0, bz - bh / 2), (FX, 0.0, AXLE_Z + 0.12)],
            0.008,
            aldk,
            coll,
        )
    )
    # front white reflector + headlight
    objs.append(
        box(
            f"{prefix}:refl_front",
            (bx + bw / 2 + 0.01, 0.0, bz - 0.04),
            (0.012, 0.07, 0.04),
            MATS["refl_white"],
            coll,
            bevel=0.003,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:headlight",
            (bx + bw / 2 + 0.01, 0.0, bz + 0.03),
            0.026,
            0.03,
            aldk,
            coll,
            verts=18,
            rot=(0, math.pi / 2, 0),
        )
    )

    # ---- rear rack + smart lock + solar + red reflector ----------------- #
    rk_z = AXLE_Z + 0.20
    objs.append(
        box(
            f"{prefix}:rack",
            (RX + 0.02, 0.0, rk_z),
            (0.30, 0.20, 0.016),
            aldk,
            coll,
            bevel=0.006,
        )
    )
    for sy in (0.075, -0.075):
        objs.append(
            bezier_tube(
                f"{prefix}:rackstrut:{sy:+.2f}",
                [(RX + 0.02, sy, rk_z), (RX, sy, AXLE_Z + 0.02)],
                0.008,
                aldk,
                coll,
            )
        )
    objs.append(
        box(
            f"{prefix}:lockbox",
            (RX + 0.04, 0.0, rk_z + 0.09),
            (0.20, 0.14, 0.12),
            MATS["lock"],
            coll,
            bevel=0.010,
        )
    )
    objs.append(
        box(
            f"{prefix}:solar",
            (RX + 0.04, 0.0, rk_z + 0.17),
            (0.19, 0.13, 0.010),
            MATS["solar"],
            coll,
            bevel=0.003,
            rot=(math.radians(-10), 0, 0),
        )
    )
    objs.append(
        box(
            f"{prefix}:refl_rear",
            (RX - 0.02, 0.0, rk_z - 0.02),
            (0.02, 0.10, 0.05),
            MATS["refl_red"],
            coll,
            bevel=0.004,
        )
    )
    # QR / info plate on the seat tube
    objs.append(
        box(
            f"{prefix}:qr",
            (-0.10, 0.03, 0.62),
            (0.07, 0.008, 0.09),
            MATS["logo_w"],
            coll,
            bevel=0.003,
        )
    )

    # ---- double centre kickstand ----------------------------------------- #
    for sy in (0.05, -0.05):
        objs.append(
            bezier_tube(
                f"{prefix}:kickstand:{sy:+.2f}",
                [(BBX - 0.02, sy, BBZ - 0.05), (BBX - 0.10, sy * 3.2, 0.0)],
                0.012,
                aldk,
                coll,
            )
        )

    # ---- head-tube round badge ------------------------------------------- #
    badge_n = Vector((0.94, 0.0, 0.34)).normalized()
    badge_c = (FX - 0.065 + badge_n.x * 0.024, 0.0, 0.90 + badge_n.z * 0.024)
    objs.append(
        uvsphere(f"{prefix}:badge", badge_c, 0.030, white, coll, scale=(1.0, 1.0, 0.25))
    )
    objs.append(
        decal(
            f"{prefix}:badge_txt",
            BRAND[0],
            (badge_c[0] + badge_n.x * 0.010, 0.0, badge_c[2] + badge_n.z * 0.010),
            normal=tuple(badge_n),
            up=(0, 0, 1),
            size=0.032,
            mat=main,
            coll=coll,
        )
    )
    return objs


# --------------------------------------------------------------------------- #
# DOCKING STATION
# --------------------------------------------------------------------------- #
def build_dock_slot(x, rail_y, coll, prefix):
    objs = []
    steel = MATS["steel_dark"]
    for sy in (0.055, -0.055):
        objs.append(
            box(
                f"{prefix}:guide:{sy:+.2f}",
                (x, rail_y + sy, 0.14),
                (0.30, 0.02, 0.24),
                steel,
                coll,
                bevel=0.005,
            )
        )
    objs.append(
        box(
            f"{prefix}:post",
            (x, rail_y - 0.16, 0.30),
            (0.10, 0.10, 0.56),
            MATS["kiosk"],
            coll,
            bevel=0.008,
        )
    )
    objs.append(
        box(
            f"{prefix}:reader",
            (x, rail_y - 0.22, 0.42),
            (0.07, 0.03, 0.10),
            MATS["screen"],
            coll,
            bevel=0.006,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:light",
            (x, rail_y - 0.215, 0.52),
            0.012,
            0.02,
            MATS["refl_red"],
            coll,
            verts=12,
            rot=(math.pi / 2, 0, 0),
        )
    )
    return objs


def build_kiosk(x, y, coll):
    """Info / payment totem - flush roof cap (no floating solar board)."""
    objs = []
    objs.append(
        box(
            "kiosk:base",
            (x, y, 0.05),
            (0.44, 0.34, 0.10),
            MATS["steel_dark"],
            coll,
            bevel=0.008,
        )
    )
    objs.append(
        box(
            "kiosk:column",
            (x, y, 0.95),
            (0.30, 0.20, 1.70),
            MATS["kiosk"],
            coll,
            bevel=0.012,
        )
    )
    objs.append(
        box(
            "kiosk:screen",
            (x, y - 0.11, 1.20),
            (0.24, 0.02, 0.40),
            MATS["screen"],
            coll,
            bevel=0.006,
        )
    )
    objs.append(
        box(
            "kiosk:header",
            (x, y - 0.10, 1.62),
            (0.26, 0.03, 0.16),
            get_scheme("blue")["main"],
            coll,
            bevel=0.006,
        )
    )
    decal(
        "kiosk:logo",
        BRAND,
        (x, y - 0.115, 1.62),
        normal=(0, -1, 0),
        up=(0, 0, 1),
        size=0.075,
        mat=MATS["logo_w"],
        coll=coll,
    )
    # flush roof cap sitting ON the column top (was a floating solar panel)
    objs.append(
        box(
            "kiosk:cap",
            (x, y, 1.82),
            (0.34, 0.24, 0.05),
            MATS["kiosk"],
            coll,
            bevel=0.010,
        )
    )
    return objs


def build_rail(x0, x1, y, coll):
    cx = (x0 + x1) / 2
    return [
        box(
            "dock:rail",
            (cx, y, 0.05),
            (abs(x1 - x0) + 0.4, 0.22, 0.10),
            MATS["steel_dark"],
            coll,
            bevel=0.010,
        )
    ]


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
BIKE_X = [0.0, 0.95, 1.90, 2.85]
BIKE_SCHEMES = ["blue", "orange", "yellow", "pink"]
EMPTY_SLOT_X = 3.80
RAIL_Y = -0.14
BIKE_CENTER_Y = 0.40
YAWS = [-90 - 3, -90 + 2, -90 - 2, -90 + 3]
KIOSK_X = -1.05
ROW_CX = (BIKE_X[0] + BIKE_X[-1]) / 2


def place(objs, loc, yaw_deg):
    e = bpy.data.objects.new(f"bike_root_{loc[0]:.2f}", None)
    bpy.context.scene.collection.objects.link(e)
    e.location = (loc[0], loc[1], 0.0)
    e.rotation_euler[2] = math.radians(yaw_deg)
    for o in objs:
        o.parent = e
    return e


def build_scene_bikes(coll):
    for i, x in enumerate(BIKE_X):
        objs = build_bicycle(coll, f"bike{i}", BIKE_SCHEMES[i])
        place(objs, (x, BIKE_CENTER_Y), YAWS[i])


def build_station(coll):
    build_rail(BIKE_X[0], EMPTY_SLOT_X, RAIL_Y, coll)
    for i, x in enumerate(BIKE_X):
        build_dock_slot(x, RAIL_Y, coll, f"dock{i}")
    build_dock_slot(EMPTY_SLOT_X, RAIL_Y, coll, "dock_empty")
    build_kiosk(KIOSK_X, RAIL_Y - 0.05, coll)


def build_ground(coll):
    box(
        "plaza",
        (ROW_CX - 0.2, 0.6, -0.02),
        (8.5, 5.2, 0.04),
        MATS["concrete"],
        coll,
        bevel=0.0,
    )
    box(
        "lawn", (ROW_CX, 8.0, -0.06), (80.0, 80.0, 0.04), MATS["grass"], coll, bevel=0.0
    )


# --------------------------------------------------------------------------- #
# World / camera / render
# --------------------------------------------------------------------------- #
def build_world():
    world = bpy.data.worlds.new("bike_sky")
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
    bg.inputs["Strength"].default_value = 0.55
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_lights():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    sun = bpy.context.object
    sun.data.energy = 2.4
    sun.data.angle = math.radians(3.5)
    sun.data.color = (1.0, 0.96, 0.88)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-40))
    loc = Vector((ROW_CX + 3.5, -7.5, 6.5))
    bpy.ops.object.light_add(type="AREA", location=loc)
    sb = bpy.context.object
    sb.data.shape = "RECTANGLE"
    sb.data.size = 10.0
    sb.data.size_y = 4.5
    sb.data.energy = 950.0
    sb.data.color = (0.9, 0.94, 1.0)
    aim = Vector((ROW_CX, 0.3, 0.7))
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
    print(f"[bike] Cycles backend: {chosen}")
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
    scene.view_settings.exposure = -1.6
    print(
        f"[bike] view={scene.view_settings.view_transform} "
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
    print(f"[bike] render still -> {path.name}")
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
    print("[bike] render orbit frames ...")
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
            f"[bike] video muxed -> {path.name} " f"({path.stat().st_size // 1024} KiB)"
        )
    except Exception as exc:
        print(f"[bike] ffmpeg mux failed: {exc!r}")


# --------------------------------------------------------------------------- #
def main():
    reset_scene()
    build_materials()

    ground_c = add_collection("bike_ground")
    bikes_c = add_collection("bike_fleet")
    dock_c = add_collection("bike_dock")

    build_ground(ground_c)
    build_scene_bikes(bikes_c)
    build_station(dock_c)

    build_world()
    add_lights()
    configure_cycles()

    fx, fy = BIKE_X[1], BIKE_CENTER_Y  # feature bike (orange/white)

    hero_cam = make_camera(
        "hero_cam", (fx - 1.7, -2.4, 1.15), (fx, fy - 0.05, 0.60), lens=48, fstop=4.0
    )
    overview_cam = make_camera(
        "overview_cam", (ROW_CX, -7.2, 5.2), (ROW_CX, 0.4, 0.5), lens=30
    )
    gallery_cam = make_camera(
        "gallery_cam", (ROW_CX - 0.3, -5.8, 2.3), (ROW_CX, 0.3, 0.65), lens=26
    )

    bpy.context.scene.camera = hero_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    if os.environ.get("BIKE_QUICK"):
        render_still(
            gallery_cam, OUTPUT_DIR / "quick_gallery.png", samples=56, res=(1280, 720)
        )
        render_still(
            hero_cam, OUTPUT_DIR / "quick_hero.png", samples=56, res=(1280, 720)
        )
        sad_cam = make_camera(
            "q_sad", (fx - 1.1, -0.7, 1.38), (fx, 0.60, 1.18), lens=70, fstop=3.2
        )
        render_still(
            sad_cam, OUTPUT_DIR / "quick_saddle.png", samples=56, res=(1280, 720)
        )
        disc_cam = make_camera(
            "q_disc",
            (BIKE_X[0] - 1.9, 1.5, 0.62),
            (BIKE_X[0], 0.92, 0.36),
            lens=62,
            fstop=5.0,
        )
        render_still(
            disc_cam, OUTPUT_DIR / "quick_disc.png", samples=56, res=(1280, 720)
        )
        print("[bike] QUICK done ->", OUTPUT_DIR)
        return

    render_still(hero_cam, HERO_PNG, samples=340)
    render_still(overview_cam, OVERVIEW_PNG, samples=260)
    render_still(gallery_cam, GALLERY_PNG, samples=260)

    details = [
        ("detail_side", (fx + 2.4, fy, 0.72), (fx, fy, 0.60), 50, 4.0),
        ("detail_saddle_bar", (fx - 1.15, -0.7, 1.48), (fx, 0.60, 1.14), 65, 3.2),
        (
            "detail_disc_wheel",
            (BIKE_X[0] - 1.9, 1.5, 0.62),
            (BIKE_X[0], 0.92, 0.36),
            62,
            5.0,
        ),
        ("detail_basket_lock", (fx - 1.2, -1.3, 1.05), (fx, fy - 0.1, 0.75), 55, 3.0),
        ("detail_drivetrain", (fx - 1.0, -0.9, 0.5), (fx - 0.05, fy, 0.30), 60, 2.8),
        ("detail_dock", (BIKE_X[2], -1.8, 0.75), (BIKE_X[2], RAIL_Y, 0.35), 55, 3.5),
        ("detail_kiosk", (KIOSK_X - 1.3, -2.2, 1.4), (KIOSK_X, RAIL_Y, 1.15), 45, 4.0),
    ]
    for name, loc, look, lens, fstop in details:
        cam = make_camera(f"cam_{name}", loc, look, lens=lens, fstop=fstop)
        render_still(cam, OUTPUT_DIR / f"{name}.png", samples=240)

    render_orbit_video(
        (ROW_CX, 0.4, 0.6),
        radius=4.6,
        height=1.8,
        path=VIDEO_PATH,
        samples=150,
        frames=72,
    )

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[bike] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
