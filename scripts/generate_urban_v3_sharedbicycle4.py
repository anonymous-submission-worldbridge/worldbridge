"""Photorealistic procedural SHARED-BICYCLE + DOCKING-STATION showcase
(urban_v3_sharedbicycle).

Infinigen ships no bicycle at all - its only "bike rack" (street_assets.py) is a
bare torus on two stubs, and its vehicles module models cars only. So this builds
a full dockless/docked bike-share fleet from scratch:

  BIKE       - step-through (Dutch/mixte) frame, chunky puncture-proof tyres with
               spoked alloy wheels, full chain-guard disc, front wire basket,
               swept handlebar + grips, saddle on a seatpost, front + rear
               mudguards, a rear smart-lock box carrying a solar panel, kickstand.
  STATION    - a low steel dock rail with per-slot wheel-guide channels + locking
               posts (one slot left empty, as in life), and an info/payment totem
               with a screen and a roof solar panel.

Realism is carried by the shared `_weather` node graph (grime in crevices, worn
edges that chip paint to bare metal, up-facing dust, roughness mottle, micro-bump)
re-used from the bench/bin v2 pass, satin metals (not chrome), a big soft-box for
real speculars, a textured cracked-concrete plaza, and a small per-bike yaw so the
fleet is not robotically aligned.

Rendered with Cycles + OptiX GPU, Nishita sky, AgX, depth-of-field.

Run:
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_sharedbicycle.py
  (BIKE_QUICK=1 -> fast smoke test; URBAN_BIKE_OUT overrides out dir)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sharedbicycle):
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
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sharedbicycle4",
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


def rubber_material(name="tyre", color=(0.010, 0.010, 0.012)):
    """Matte, slightly dusty tyre rubber with a fine tread bump."""
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
        dust=0.5,
        dust_color=(0.24, 0.22, 0.18),
        bump_strength=0.09,
        bump_scale=60.0,
    )
    return m


def solar_material(name="solar"):
    """Dark-blue PV panel: cell grid, glassy coat, faint metallic."""
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
    # thin dark grid lines between cells
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

# a single-brand fleet livery: teal frame, silver alloy, black rubber
TEAL = (0.010, 0.090, 0.098)


def build_materials():
    MATS["frame"] = paint_material(
        "bike_frame", TEAL, roughness=0.34, chip=0.22, dust=0.28, coat=0.5
    )
    MATS["frame_dark"] = paint_material(
        "bike_frame_dark", (0.010, 0.045, 0.050), roughness=0.4, chip=0.25, dust=0.3
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
        (0.20, 0.21, 0.23),
        roughness=0.42,
        edge_amt=0.2,
        dust=0.25,
        bump_scale=140.0,
    )
    MATS["tyre"] = rubber_material("bike_tyre")
    # warm tanned-leather saddle: brown hide, matte with a faint sheen, no metal
    # chipping; drop the specular so the top face doesn't mirror the sky to grey
    MATS["saddle"] = paint_material(
        "bike_saddle",
        (0.098, 0.038, 0.018),
        roughness=0.60,
        chip=0.0,
        dust=0.05,
        metal=(0.098, 0.038, 0.018),
        coat=0.04,
        bump_scale=320.0,
    )
    _set(_principled(MATS["saddle"]), "Specular IOR Level", 0.26)
    _set(_principled(MATS["saddle"]), "Sheen Weight", 0.12)
    MATS["grip"] = paint_material(
        "bike_grip",
        (0.020, 0.020, 0.022),
        roughness=0.6,
        chip=0.05,
        dust=0.2,
        metal=(0.03, 0.03, 0.03),
    )
    MATS["lock"] = paint_material(
        "bike_lock", (0.024, 0.025, 0.028), roughness=0.5, chip=0.15, dust=0.3
    )
    MATS["solar"] = solar_material("bike_solar")
    MATS["steel_dark"] = metal_material(
        "dock_steel",
        (0.055, 0.057, 0.060),
        roughness=0.5,
        edge_amt=0.18,
        dust=0.3,
        bump_scale=110.0,
    )
    MATS["galv"] = metal_material(
        "dock_galv",
        (0.30, 0.31, 0.33),
        roughness=0.44,
        edge_amt=0.2,
        dust=0.35,
        spangle=True,
        bump_scale=90.0,
        bump_strength=0.05,
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
    print("[bike] materials:", list(MATS))


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


# --------------------------------------------------------------------------- #
# BICYCLE  (built about local origin, front wheel toward +X)
# --------------------------------------------------------------------------- #
WHEEL_R = 0.345  # tyre outer radius
TYRE_X = 0.046  # tyre cross-section
RIM_MAJ = 0.250
AXLE_Z = WHEEL_R
FX = 0.535  # front axle x
RX = -0.520  # rear axle x
BBX, BBZ = -0.05, 0.285  # bottom bracket (crank centre)
SPOKES = 16


def wheel(prefix, cx, cz, coll):
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
            0.022,
            MATS["alu"],
            coll,
            rot=axis_y,
            verts=64,
            minor_verts=12,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:hub",
            (cx, 0, cz),
            0.030,
            0.10,
            MATS["alu"],
            coll,
            verts=20,
            rot=axis_y,
        )
    )
    hub_r, rim_r = 0.030, 0.235
    rmid = (hub_r + rim_r) / 2
    slen = rim_r - hub_r
    for i in range(SPOKES):
        a = i / SPOKES * TAU
        yoff = 0.028 if i % 2 else -0.028
        objs.append(
            cyl(
                f"{prefix}:spoke:{i}",
                (cx + math.cos(a) * rmid, yoff, cz + math.sin(a) * rmid),
                0.0028,
                slen,
                MATS["alu"],
                coll,
                verts=6,
                rot=(0, math.pi / 2 - a, 0),
            )
        )
    return objs


def fender(prefix, cx, cz, coll, a0, a1, hw=0.060, gap=0.022, drop=0.032):
    """A sheet-metal mudguard: a curved PLATE that follows the wheel arc and
    also curves down over the tyre shoulders in cross-section (a shallow
    channel), so it reads as a real fender board rather than a round tube."""
    r = WHEEL_R + gap
    na, nc = 24, 7
    verts, faces = [], []
    for i in range(na):
        t = i / (na - 1)
        a = math.radians(a0 + (a1 - a0) * t)
        radx, radz = math.cos(a), math.sin(a)
        for j in range(nc):
            s = -1.0 + 2.0 * j / (nc - 1)
            rr = r - drop * (s * s)  # edges dip to hug the tyre sides
            verts.append((cx + radx * rr, hw * s, cz + radz * rr))
    for i in range(na - 1):
        for j in range(nc - 1):
            a_ = i * nc + j
            faces.append((a_, a_ + 1, a_ + nc + 1, a_ + nc))
    me = bpy.data.meshes.new(f"{prefix}:fender")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(f"{prefix}:fender", me)
    sol = o.modifiers.new("sol", "SOLIDIFY")  # give the plate real thickness
    sol.thickness = 0.008
    sol.offset = 0.0
    return [_finish(o, MATS["frame"], coll, shade_smooth=True)]


def build_bicycle(coll, prefix):
    objs = []
    fr, alu, aldk = MATS["frame"], MATS["alu"], MATS["alu_dark"]

    # ---- wheels + fenders ------------------------------------------------- #
    objs += wheel(f"{prefix}:fw", FX, AXLE_Z, coll)
    objs += wheel(f"{prefix}:rw", RX, AXLE_Z, coll)
    objs += fender(f"{prefix}:ff", FX, AXLE_Z, coll, 40, 150)
    objs += fender(f"{prefix}:rf", RX, AXLE_Z, coll, 30, 150)

    # ---- frame tubes ------------------------------------------------------ #
    head_bot = (FX - 0.06, 0.0, 0.70)
    head_top = (FX - 0.10, 0.0, 1.02)
    seat_cluster = (-0.22, 0.0, 1.00)
    objs.append(
        bezier_tube(f"{prefix}:headtube", [head_bot, head_top], 0.023, fr, coll)
    )
    # low step-through down tube: head -> bottom bracket
    objs.append(
        bezier_tube(
            f"{prefix}:downtube",
            [head_bot, (0.24, 0.0, 0.40), (BBX + 0.02, 0.0, BBZ)],
            0.024,
            fr,
            coll,
        )
    )
    # characteristic low curved top bar: head -> seat cluster
    objs.append(
        bezier_tube(
            f"{prefix}:topbar",
            [
                (head_top[0] - 0.02, 0.0, 0.95),
                (0.12, 0.0, 0.60),
                (-0.14, 0.0, 0.56),
                seat_cluster,
            ],
            0.022,
            fr,
            coll,
        )
    )
    # seat tube: BB -> seat cluster
    objs.append(
        bezier_tube(
            f"{prefix}:seattube", [(BBX, 0.0, BBZ), seat_cluster], 0.023, fr, coll
        )
    )
    # chain + seat stays (both sides)
    for sy in (0.058, -0.058):
        objs.append(
            bezier_tube(
                f"{prefix}:chainstay:{sy:+.2f}",
                [(BBX, sy * 0.6, BBZ), (RX, sy, AXLE_Z)],
                0.012,
                fr,
                coll,
            )
        )
        objs.append(
            bezier_tube(
                f"{prefix}:seatstay:{sy:+.2f}",
                [(seat_cluster[0], sy * 0.4, 0.97), (RX, sy, AXLE_Z)],
                0.011,
                fr,
                coll,
            )
        )

    # ---- fork ------------------------------------------------------------- #
    objs.append(
        bezier_tube(
            f"{prefix}:steerer", [head_bot, (FX - 0.04, 0.0, 0.64)], 0.020, aldk, coll
        )
    )
    for sy in (0.055, -0.055):
        objs.append(
            bezier_tube(
                f"{prefix}:fork:{sy:+.2f}",
                [
                    (FX - 0.04, sy * 0.4, 0.64),
                    (FX, sy, AXLE_Z + 0.10),
                    (FX, sy, AXLE_Z),
                ],
                0.014,
                aldk,
                coll,
            )
        )

    # ---- handlebar + grips ------------------------------------------------ #
    stem_end = (FX - 0.20, 0.0, 1.13)
    objs.append(bezier_tube(f"{prefix}:stem", [head_top, stem_end], 0.017, aldk, coll))
    hw = 0.26  # half bar width
    sweep = 0.085  # how far the grips pull back toward the rider
    rise = 0.028
    bar_knots = [
        (stem_end[0] - sweep, +hw, stem_end[2] + rise),
        (stem_end[0] - 0.020, +hw * 0.55, stem_end[2] + rise * 0.35),
        (stem_end[0] + 0.012, 0.0, stem_end[2]),
        (stem_end[0] - 0.020, -hw * 0.55, stem_end[2] + rise * 0.35),
        (stem_end[0] - sweep, -hw, stem_end[2] + rise),
    ]
    objs.append(bezier_tube(f"{prefix}:bar", bar_knots, 0.014, aldk, coll))
    for sgn in (+1, -1):
        objs.append(
            cyl(
                f"{prefix}:grip:{sgn:+d}",
                (stem_end[0] - sweep, sgn * (hw - 0.006), stem_end[2] + rise),
                0.020,
                0.10,
                MATS["grip"],
                coll,
                verts=16,
                rot=(math.pi / 2, 0, 0),
            )
        )
    # small console + brake levers hint
    objs.append(
        box(
            f"{prefix}:console",
            (stem_end[0] + 0.02, 0.0, stem_end[2] + 0.03),
            (0.05, 0.10, 0.03),
            MATS["lock"],
            coll,
            bevel=0.006,
        )
    )

    # ---- saddle + seatpost ------------------------------------------------ #
    post_top = (-0.24, 0.0, 1.20)
    objs.append(
        bezier_tube(f"{prefix}:seatpost", [seat_cluster, post_top], 0.016, aldk, coll)
    )
    # broad cushioned leather saddle: wider + thicker for a comfortable look,
    # dropped down so its pan swallows the seatpost top (no floating gap).
    sad_cx = post_top[0] + 0.02
    sad_cz = post_top[2] - 0.035  # drop the saddle onto the post
    sad = uvsphere(
        f"{prefix}:saddle",
        (sad_cx, 0.0, sad_cz),
        0.12,
        MATS["saddle"],
        coll,
        scale=(1.66, 0.92, 0.54),
    )
    me = sad.data
    for v in me.vertices:
        xr = v.co.x / 0.12  # normalised -1 (tail) .. +1 (nose)
        if xr > 0.0:  # gradual taper into the nose (no hard crease)
            v.co.y *= 1.0 - 0.58 * xr
        if v.co.z < -0.010:  # flatten the underside into a rounded pan
            v.co.z = -0.010 + (v.co.z + 0.010) * 0.34
    objs.append(sad)
    # two brass rivets on the rear skirt, a classic leather-saddle tell
    for ry in (0.058, -0.058):
        objs.append(
            uvsphere(
                f"{prefix}:rivet:{ry:+.2f}",
                (sad_cx - 0.085, ry, sad_cz + 0.024),
                0.008,
                MATS["alu"],
                coll,
            )
        )

    # ---- drivetrain ------------------------------------------------------- #
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
    # full chain-guard disc (very shared-bike)
    objs.append(
        cyl(
            f"{prefix}:chainguard",
            (BBX, 0.078, BBZ),
            0.120,
            0.010,
            fr,
            coll,
            verts=48,
            rot=axis_y,
        )
    )
    objs.append(
        cyl(
            f"{prefix}:bb",
            (BBX, 0.0, BBZ),
            0.026,
            0.14,
            aldk,
            coll,
            verts=18,
            rot=axis_y,
        )
    )
    for sy, cz in ((0.075, BBZ - 0.09), (-0.075, BBZ + 0.09)):
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
        py = 0.135 if sy > 0 else -0.135
        pz = BBZ - 0.16 if sy > 0 else BBZ + 0.16
        objs.append(
            box(
                f"{prefix}:pedal:{sy:+.2f}",
                (BBX, py, pz),
                (0.10, 0.06, 0.022),
                MATS["lock"],
                coll,
                bevel=0.005,
            )
        )

    # ---- front basket ----------------------------------------------------- #
    bx, bz = FX - 0.02, 0.86
    bw, bd, bh = 0.30, 0.28, 0.20
    objs.append(
        box(
            f"{prefix}:basket:floor",
            (bx, 0.0, bz - bh / 2),
            (bw, bd, 0.014),
            fr,
            coll,
            bevel=0.006,
        )
    )
    # top rim frame (4 bars)
    objs.append(
        bezier_tube(
            f"{prefix}:basket:rimF",
            [(bx - bw / 2, -bd / 2, bz + bh / 2), (bx - bw / 2, bd / 2, bz + bh / 2)],
            0.008,
            fr,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:basket:rimB",
            [(bx + bw / 2, -bd / 2, bz + bh / 2), (bx + bw / 2, bd / 2, bz + bh / 2)],
            0.008,
            fr,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:basket:rimL",
            [(bx - bw / 2, -bd / 2, bz + bh / 2), (bx + bw / 2, -bd / 2, bz + bh / 2)],
            0.008,
            fr,
            coll,
        )
    )
    objs.append(
        bezier_tube(
            f"{prefix}:basket:rimR",
            [(bx - bw / 2, bd / 2, bz + bh / 2), (bx + bw / 2, bd / 2, bz + bh / 2)],
            0.008,
            fr,
            coll,
        )
    )
    # vertical wire bars
    nx = 5
    for i in range(nx):
        xx = bx - bw / 2 + bw * i / (nx - 1)
        for yy in (-bd / 2, bd / 2):
            objs.append(
                cyl(
                    f"{prefix}:basket:vx:{i}:{yy:+.2f}",
                    (xx, yy, bz),
                    0.004,
                    bh,
                    fr,
                    coll,
                    verts=6,
                )
            )
    ny = 4
    for j in range(ny):
        yy = -bd / 2 + bd * j / (ny - 1)
        for xx in (bx - bw / 2, bx + bw / 2):
            objs.append(
                cyl(
                    f"{prefix}:basket:vy:{j}:{xx:+.2f}",
                    (xx, yy, bz),
                    0.004,
                    bh,
                    fr,
                    coll,
                    verts=6,
                )
            )
    # basket mounting strut to head tube
    objs.append(
        bezier_tube(
            f"{prefix}:basket:strut",
            [(bx, 0.0, bz - bh / 2), (FX - 0.08, 0.0, 0.74)],
            0.010,
            aldk,
            coll,
        )
    )
    # small headlight on basket front
    objs.append(
        cyl(
            f"{prefix}:headlight",
            (bx + bw / 2 + 0.01, 0.0, bz),
            0.028,
            0.03,
            aldk,
            coll,
            verts=18,
            rot=(0, math.pi / 2, 0),
        )
    )

    # ---- rear rack + smart lock + solar panel ----------------------------- #
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
    # smart-lock control box astride the rear wheel
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
    # rear-wheel lock horseshoe (partial ring around the tyre)
    objs.append(
        torus(
            f"{prefix}:lockring",
            (RX, 0.0, AXLE_Z),
            WHEEL_R + 0.02,
            0.012,
            MATS["lock"],
            coll,
            rot=(math.pi / 2, 0, 0),
            verts=40,
        )
    )
    # roof solar panel, tilted up toward the sun
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

    # ---- kickstand -------------------------------------------------------- #
    objs.append(
        bezier_tube(
            f"{prefix}:kickstand",
            [(BBX - 0.06, 0.09, BBZ - 0.05), (BBX - 0.16, 0.20, 0.0)],
            0.011,
            aldk,
            coll,
        )
    )
    return objs


# --------------------------------------------------------------------------- #
# DOCKING STATION
# --------------------------------------------------------------------------- #
def build_dock_slot(x, rail_y, coll, prefix):
    """A wheel-guide channel + locking post at one dock position."""
    objs = []
    steel = MATS["steel_dark"]
    # two guide plates forming a slot for the front wheel
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
    # locking post with reader
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
    # a green/teal status light
    objs.append(
        cyl(
            f"{prefix}:light",
            (x, rail_y - 0.215, 0.52),
            0.012,
            0.02,
            MATS["frame"],
            coll,
            verts=12,
            rot=(math.pi / 2, 0, 0),
        )
    )
    return objs


def build_kiosk(x, y, coll):
    """Info / payment totem: column + screen + roof solar panel."""
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
            MATS["frame"],
            coll,
            bevel=0.006,
        )
    )
    # flush roof cap flush with the column top (1.80) -- no floating board
    objs.append(
        box(
            "kiosk:cap",
            (x, y, 1.83),
            (0.34, 0.24, 0.05),
            MATS["steel_dark"],
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
BIKE_X = [0.0, 0.95, 1.90, 2.85]  # docked-bike centres along the rail
EMPTY_SLOT_X = 3.80  # one empty dock, as in life
RAIL_Y = -0.14
BIKE_CENTER_Y = 0.40  # so the front wheel lands at the rail
YAWS = [-90 - 3, -90 + 2, -90 - 2, -90 + 3]  # face the rail, slight scatter
KIOSK_X = -1.05
ROW_CX = (BIKE_X[0] + BIKE_X[-1]) / 2


def place(objs, loc, yaw_deg):
    e = bpy.data.objects.new(f"bike_root_{loc[0]:.2f}", None)
    bpy.context.scene.collection.objects.link(e)
    e.location = (loc[0], loc[1], 0.0)
    e.rotation_euler[2] = math.radians(yaw_deg)
    for o in objs:
        o.parent = e  # objs built at origin; identity parent-inverse
    return e


def build_scene_bikes(coll):
    for i, x in enumerate(BIKE_X):
        objs = build_bicycle(coll, f"bike{i}")
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

    # feature bike = index 1 (has room on both sides)
    fx, fy = BIKE_X[1], BIKE_CENTER_Y

    hero_cam = make_camera(
        "hero_cam", (fx - 1.7, -2.4, 1.15), (fx, fy - 0.05, 0.62), lens=48, fstop=4.0
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
            "q_sad", (fx - 1.1, -0.7, 1.40), (fx, 0.60, 1.18), lens=70, fstop=3.2
        )
        render_still(
            sad_cam, OUTPUT_DIR / "quick_saddle.png", samples=56, res=(1280, 720)
        )
        fen_cam = make_camera(
            "q_fen", (fx - 1.3, -1.7, 0.72), (fx, -0.14, 0.52), lens=62, fstop=3.5
        )
        render_still(
            fen_cam, OUTPUT_DIR / "quick_fender.png", samples=56, res=(1280, 720)
        )
        print("[bike] QUICK done ->", OUTPUT_DIR)
        return

    render_still(hero_cam, HERO_PNG, samples=340)
    render_still(overview_cam, OVERVIEW_PNG, samples=260)
    render_still(gallery_cam, GALLERY_PNG, samples=260)

    # detail close-ups
    details = [
        ("detail_side", (fx + 2.4, fy, 0.72), (fx, fy, 0.62), 50, 4.0),
        ("detail_basket_lock", (fx - 1.2, -1.3, 1.25), (fx, fy - 0.1, 0.95), 55, 3.0),
        ("detail_drivetrain", (fx - 1.0, -0.9, 0.5), (fx - 0.05, fy, 0.30), 60, 2.8),
        ("detail_solar_rack", (fx + 1.6, 1.4, 1.05), (fx, fy + 0.55, 0.75), 55, 3.0),
        ("detail_dock", (BIKE_X[2], -1.8, 0.75), (BIKE_X[2], RAIL_Y, 0.35), 55, 3.5),
        ("detail_kiosk", (KIOSK_X - 1.3, -2.2, 1.4), (KIOSK_X, RAIL_Y, 1.15), 45, 4.0),
    ]
    for name, loc, look, lens, fstop in details:
        cam = make_camera(f"cam_{name}", loc, look, lens=lens, fstop=fstop)
        render_still(cam, OUTPUT_DIR / f"{name}.png", samples=240)

    # video skipped for this pass (images only)
    # render_orbit_video((ROW_CX, 0.4, 0.6), radius=4.6, height=1.8,
    #                    path=VIDEO_PATH, samples=150, frames=72)

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[bike] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
