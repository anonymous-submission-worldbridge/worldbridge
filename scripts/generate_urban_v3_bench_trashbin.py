"""Photorealistic procedural BENCH + TRASH-BIN showcase (urban_v3_longchair+trashbin).

Why this exists
---------------
Infinigen's only street bench / trash-bin geometry lives in
``infinigen/assets/objects/street_furniture/street_assets.py`` and is a bare
primitive assembly (a bench = a few plank cubes + cylinder legs; a bin = one
cylinder + a rim). ``sim_objects/trash.py`` is an *indoor* pedal kitchen bin,
not a street bin. None of them reach photo-realism and none offer the several
distinct styles the reference photos show (classic cast-iron + wood park bench,
modern slatted bench, wire-mesh street bin, domed covered bin ...).

So this script procedurally models, from scratch, a small furniture showroom:

  BENCHES
    * classic  - ornate cast-iron scroll ends + warm wooden slats (the iconic
                 Victorian park bench)
    * modern   - powder-coated steel sled frame + clean horizontal wood slats
    * wooden   - chunky all-timber A-frame garden bench

  TRASH BINS
    * mesh     - galvanised wire-mesh street bin (vertical bars + hoops) on feet
    * domed    - painted-metal covered street bin with a domed lid + push flap
    * wooden   - timber-slat park bin with steel bands and a steel liner

Every surface uses a hand-built photoreal PBR shader: a procedural wood-grain
node graph (wave + noise -> two-tone grain + micro bump), cast iron / powder
coat / galvanised steel with micro-scratch bump, on a subtle concrete plaza with
a grass surround.

Rendered with Cycles + OptiX GPU path tracing, a Nishita physical sky, AgX view
transform and depth-of-field.

Run (needs the infinigen conda env whose python bundles bpy 4.2):
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_bench_trashbin.py

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_longchair+trashbin):
  furniture.blend
  furniture.png              (hero: classic bench + mesh bin)
  furniture_overview.png     (whole showroom, high angle)
  furniture_gallery.png      (all six pieces in a row, labelled)
  bench_01_classic.png ... bin_03_wooden.png   (six close-ups)
  furniture_orbit.mp4        (turntable around the hero pairing)
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

# --------------------------------------------------------------------------- #
# Keep all scratch off "/"; write only under ${WORLDBRIDGE_EXTERNAL}/.
# --------------------------------------------------------------------------- #
REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUTPUT_DIR = Path(
    os.environ.get(
        "URBAN_FURN_OUT",
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_longchair+trashbin",
    )
)
FRAMES_DIR = OUTPUT_DIR / "frames"
TMP_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
for d in (OUTPUT_DIR, FRAMES_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

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
# Photoreal PBR shaders (pure bpy nodes)
# --------------------------------------------------------------------------- #
def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def _principled(mat):
    return mat.node_tree.nodes.get("Principled BSDF")


def metal_material(
    name, color, roughness=0.4, metallic=1.0, scratch=0.015, bump_scale=48.0
):
    """Metal with a faint procedural micro-scratch / cast-texture bump."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    # micro bump for realism (breaks the plastic-perfect look)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = bump_scale
    noise.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = scratch
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # a touch of roughness variation
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = max(0.02, roughness - 0.12)
    rr.inputs["To Max"].default_value = min(0.95, roughness + 0.12)
    nt.links.new(noise.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    return m


def wood_material(
    name,
    dark=(0.055, 0.022, 0.008),
    light=(0.16, 0.075, 0.028),
    roughness=0.42,
    grain_scale=(0.5, 14.0, 2.0),
    bump=0.20,
):
    """Procedural wood: stretched wave grain + fibre noise -> two-tone + bump.

    Colours are given in *linear* space (already fairly dark so AgX keeps them
    a natural warm timber rather than orange plastic)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "Metallic", 0.0)
    _set(b, "IOR", 1.5)

    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = grain_scale
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    # long grain lines
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 2.4
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 1.2
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])

    # fine fibre noise mixed in so the grain isn't too regular
    fibre = nt.nodes.new("ShaderNodeTexNoise")
    fibre.inputs["Scale"].default_value = 22.0
    fibre.inputs["Detail"].default_value = 8.0
    nt.links.new(mapping.outputs["Vector"], fibre.inputs["Vector"])

    mix_fac = nt.nodes.new("ShaderNodeMixRGB")
    mix_fac.blend_type = "MULTIPLY"
    mix_fac.inputs["Fac"].default_value = 0.35
    nt.links.new(wave.outputs["Color"], mix_fac.inputs["Color1"])
    nt.links.new(fibre.outputs["Color"], mix_fac.inputs["Color2"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(mix_fac.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])

    # roughness varies slightly with grain
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = roughness - 0.08
    rr.inputs["To Max"].default_value = roughness + 0.10
    nt.links.new(mix_fac.outputs["Color"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])

    # bump from the grain
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.004
    nt.links.new(mix_fac.outputs["Color"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    return m


def concrete_material(name="plaza_concrete"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _principled(m)
    _set(b, "Roughness", 0.85)
    _set(b, "Metallic", 0.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 5.0
    n1.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.16, 0.16, 0.17, 1.0)
    ramp.color_ramp.elements[1].color = (0.26, 0.255, 0.25, 1.0)
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 220.0
    n2.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.12
    nt.links.new(n2.outputs["Fac"], bmp.inputs["Height"])
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
    _set(b, "Roughness", 0.9)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 90.0
    n.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.045, 0.075, 0.020, 1.0)
    ramp.color_ramp.elements[1].color = (0.085, 0.13, 0.038, 1.0)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


MATS = {}


def build_materials():
    MATS["wood_teak"] = wood_material(
        "wood_teak", dark=(0.060, 0.026, 0.010), light=(0.17, 0.085, 0.032)
    )
    MATS["wood_oak"] = wood_material(
        "wood_oak",
        dark=(0.085, 0.045, 0.018),
        light=(0.22, 0.13, 0.060),
        grain_scale=(0.5, 10.0, 2.0),
    )
    MATS["wood_dark"] = wood_material(
        "wood_dark",
        dark=(0.030, 0.014, 0.006),
        light=(0.10, 0.050, 0.022),
        grain_scale=(0.5, 16.0, 2.0),
    )
    MATS["cast_iron_green"] = metal_material(
        "cast_iron_green",
        (0.010, 0.035, 0.022),
        roughness=0.46,
        metallic=0.85,
        scratch=0.03,
        bump_scale=30.0,
    )
    MATS["cast_iron_black"] = metal_material(
        "cast_iron_black",
        (0.010, 0.010, 0.011),
        roughness=0.44,
        metallic=0.85,
        scratch=0.03,
        bump_scale=30.0,
    )
    MATS["powder_graphite"] = metal_material(
        "powder_graphite",
        (0.020, 0.021, 0.024),
        roughness=0.55,
        metallic=0.35,
        scratch=0.012,
        bump_scale=60.0,
    )
    MATS["galv_steel"] = metal_material(
        "galv_steel",
        (0.34, 0.35, 0.37),
        roughness=0.34,
        metallic=1.0,
        scratch=0.02,
        bump_scale=70.0,
    )
    MATS["steel_dark"] = metal_material(
        "steel_dark",
        (0.045, 0.047, 0.050),
        roughness=0.40,
        metallic=1.0,
        scratch=0.02,
        bump_scale=55.0,
    )
    MATS["bin_green"] = metal_material(
        "bin_green",
        (0.012, 0.045, 0.028),
        roughness=0.50,
        metallic=0.4,
        scratch=0.015,
        bump_scale=50.0,
    )
    MATS["liner_black"] = metal_material(
        "liner_black",
        (0.006, 0.006, 0.006),
        roughness=0.7,
        metallic=0.2,
        scratch=0.0,
        bump_scale=10.0,
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
        # smooth the round wall but keep the caps flat
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


def torus(name, loc, major, minor, mat, coll, rot=(0, 0, 0), verts=48, minor_verts=14):
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
    _finish(o, mat, coll, shade_smooth=True)
    return o


def hemisphere(name, loc, radius, mat, coll, squash=0.55, segments=48):
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


def tube(name, pts, radius, mat, coll, res=6, smooth_side=True):
    """A round-profile tube following a poly-line (wrought-iron look)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = res
    cu.resolution_u = 8
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    return link_to(o, coll)


def bezier_tube(name, knots, radius, mat, coll, res=12):
    """Smooth bezier tube; knots = [(x,y,z), ...] with auto handles."""
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


# --------------------------------------------------------------------------- #
# BENCHES
# --------------------------------------------------------------------------- #
def bench_classic(ox, oy, coll, wood, iron):
    """Victorian park bench: ornate cast-iron scroll ends + wooden slats."""
    objs = []
    L = 0.86  # half length (X)
    seat_z = 0.44
    # ---- wooden seat slats (run along X) ----
    for i, sy in enumerate([-0.20, -0.10, 0.0, 0.10, 0.20]):
        objs.append(
            box(
                f"clbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.075, 0.028),
                wood,
                coll,
                bevel=0.010,
            )
        )
    # ---- backrest slats (tilted) ----
    tilt = math.radians(14)
    for i in range(4):
        z = 0.53 + i * 0.095
        yy = oy + 0.24 + i * 0.022
        objs.append(
            box(
                f"clbench:back:{i}",
                (ox, yy, z),
                (2 * L, 0.072, 0.024),
                wood,
                coll,
                bevel=0.009,
                rot=(tilt, 0, 0),
            )
        )
    # ---- cast-iron ornate ends at x = ox +/- L ----
    for sx in (-L - 0.02, L + 0.02):
        x = ox + sx
        # rear upright continues up as the backrest post (gentle S)
        objs.append(
            bezier_tube(
                f"clbench:rear:{sx:.2f}",
                [
                    (x, oy + 0.30, 0.02),
                    (x, oy + 0.27, 0.30),
                    (x, oy + 0.30, seat_z),
                    (x, oy + 0.40, 0.90),
                ],
                0.024,
                iron,
                coll,
            )
        )
        # front leg with an outward scroll foot
        objs.append(
            bezier_tube(
                f"clbench:front:{sx:.2f}",
                [
                    (x, oy - 0.30, 0.0),
                    (x, oy - 0.26, 0.16),
                    (x, oy - 0.24, seat_z + 0.02),
                ],
                0.024,
                iron,
                coll,
            )
        )
        # scroll foot (little curl at floor, front)
        objs.append(
            bezier_tube(
                f"clbench:foot:{sx:.2f}",
                [
                    (x, oy - 0.30, 0.02),
                    (x, oy - 0.42, 0.02),
                    (x, oy - 0.45, 0.11),
                    (x, oy - 0.37, 0.13),
                ],
                0.017,
                iron,
                coll,
            )
        )
        # armrest: from front leg top, up and back to the rear post, with a
        # forward curl at the front (the classic rolled arm)
        objs.append(
            bezier_tube(
                f"clbench:arm:{sx:.2f}",
                [
                    (x, oy - 0.46, 0.60),
                    (x, oy - 0.40, 0.68),
                    (x, oy - 0.22, 0.70),
                    (x, oy + 0.22, 0.66),
                    (x, oy + 0.34, 0.62),
                ],
                0.020,
                iron,
                coll,
            )
        )
        # arm support post (front)
        objs.append(
            tube(
                f"clbench:armpost:{sx:.2f}",
                [(x, oy - 0.30, seat_z), (x, oy - 0.34, 0.66)],
                0.018,
                iron,
                coll,
            )
        )
        # decorative scroll under the arm
        objs.append(
            bezier_tube(
                f"clbench:scroll:{sx:.2f}",
                [
                    (x, oy - 0.24, 0.50),
                    (x, oy - 0.12, 0.54),
                    (x, oy - 0.10, 0.64),
                    (x, oy - 0.20, 0.66),
                    (x, oy - 0.26, 0.60),
                ],
                0.011,
                iron,
                coll,
            )
        )
    # ---- iron cross rails tying the two ends (under seat + low stretcher) ----
    objs.append(
        cyl(
            "clbench:rail_seat",
            (ox, oy - 0.02, seat_z - 0.05),
            0.018,
            2 * L + 0.02,
            iron,
            coll,
            verts=16,
            rot=(0, math.radians(90), 0),
        )
    )
    objs.append(
        cyl(
            "clbench:rail_low",
            (ox, oy - 0.10, 0.11),
            0.016,
            2 * L - 0.06,
            iron,
            coll,
            verts=16,
            rot=(0, math.radians(90), 0),
        )
    )
    return objs


def bench_modern(ox, oy, coll, wood, metal):
    """Modern bench: powder-coated steel sled frame + horizontal wood slats."""
    objs = []
    L = 0.80
    seat_z = 0.43
    # ---- seat slats ----
    for i, sy in enumerate([-0.19, -0.095, 0.0, 0.095, 0.19]):
        objs.append(
            box(
                f"mbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.078, 0.030),
                wood,
                coll,
                bevel=0.012,
            )
        )
    # ---- back slats (near vertical, slight tilt) ----
    for i in range(3):
        z = 0.56 + i * 0.10
        objs.append(
            box(
                f"mbench:back:{i}",
                (ox, oy + 0.26, z),
                (2 * L, 0.078, 0.028),
                wood,
                coll,
                bevel=0.012,
                rot=(math.radians(6), 0, 0),
            )
        )
    # ---- two flat-bar sled legs (rectangular loops in Y-Z) ----
    for sx in (-L + 0.10, L - 0.10):
        x = ox + sx
        bar = 0.05
        # foot on the ground
        objs.append(
            box(
                f"mbench:foot:{sx:.2f}",
                (x, oy - 0.02, 0.02),
                (bar, 0.66, 0.045),
                metal,
                coll,
                bevel=0.008,
            )
        )
        # front + rear uprights
        objs.append(
            box(
                f"mbench:up_f:{sx:.2f}",
                (x, oy - 0.24, seat_z / 2 + 0.02),
                (bar, 0.05, seat_z),
                metal,
                coll,
                bevel=0.008,
            )
        )
        objs.append(
            box(
                f"mbench:up_r:{sx:.2f}",
                (x, oy + 0.24, 0.34),
                (bar, 0.05, 0.66),
                metal,
                coll,
                bevel=0.008,
            )
        )
        # seat crossbar
        objs.append(
            box(
                f"mbench:cross:{sx:.2f}",
                (x, oy, seat_z - 0.035),
                (bar, 0.60, 0.045),
                metal,
                coll,
                bevel=0.008,
            )
        )
        # back rake bar
        objs.append(
            box(
                f"mbench:rake:{sx:.2f}",
                (x, oy + 0.255, 0.64),
                (bar, 0.05, 0.34),
                metal,
                coll,
                bevel=0.008,
                rot=(math.radians(6), 0, 0),
            )
        )
    return objs


def bench_wooden(ox, oy, coll, wood, metal):
    """Chunky all-timber A-frame garden bench."""
    objs = []
    L = 0.82
    seat_z = 0.45
    # thick seat slats
    for i, sy in enumerate([-0.17, 0.0, 0.17]):
        objs.append(
            box(
                f"wbench:seat:{i}",
                (ox, oy + sy, seat_z),
                (2 * L, 0.16, 0.045),
                wood,
                coll,
                bevel=0.014,
            )
        )
    # back slats
    for i in range(2):
        z = 0.60 + i * 0.16
        objs.append(
            box(
                f"wbench:back:{i}",
                (ox, oy + 0.27, z),
                (2 * L, 0.16, 0.040),
                wood,
                coll,
                bevel=0.013,
                rot=(math.radians(10), 0, 0),
            )
        )
    # A-frame plank legs at each end
    for sx in (-L + 0.14, L - 0.14):
        x = ox + sx
        objs.append(
            box(
                f"wbench:leg_f:{sx:.2f}",
                (x, oy - 0.20, seat_z / 2),
                (0.09, 0.14, seat_z + 0.02),
                wood,
                coll,
                bevel=0.010,
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
                bevel=0.010,
                rot=(math.radians(8), 0, 0),
            )
        )
        # apron tying legs under the seat
        objs.append(
            box(
                f"wbench:apron:{sx:.2f}",
                (x, oy + 0.03, seat_z - 0.08),
                (0.06, 0.52, 0.10),
                wood,
                coll,
                bevel=0.008,
            )
        )
    # long stretcher between the A-frames
    objs.append(
        box(
            "wbench:stretch",
            (ox, oy + 0.02, 0.16),
            (2 * L - 0.30, 0.07, 0.09),
            wood,
            coll,
            bevel=0.008,
        )
    )
    # steel bolt caps for detail
    for sx in (-L + 0.14, L - 0.14):
        for sy in (-0.20, 0.28):
            objs.append(
                cyl(
                    f"wbench:bolt:{sx:.2f}:{sy:.2f}",
                    (ox + sx, oy + sy, seat_z - 0.02),
                    0.016,
                    0.10,
                    metal,
                    coll,
                    verts=12,
                    rot=(0, math.radians(90), 0),
                )
            )
    return objs


# --------------------------------------------------------------------------- #
# TRASH BINS
# --------------------------------------------------------------------------- #
def bin_mesh(ox, oy, coll, steel, liner):
    """Galvanised wire-mesh street bin: vertical bars + hoops on little feet."""
    objs = []
    R = 0.27
    z0, z1 = 0.16, 0.86
    h = z1 - z0
    cz = (z0 + z1) / 2
    n_bars = 44
    for i in range(n_bars):
        a = i / n_bars * TAU
        x = ox + math.cos(a) * R
        y = oy + math.sin(a) * R
        objs.append(cyl(f"binmesh:bar:{i}", (x, y, cz), 0.006, h, steel, coll, verts=8))
    # horizontal hoops
    for i, z in enumerate([z0 + 0.02, cz, z1 - 0.02, z1]):
        mnr = 0.012 if i == 3 else 0.008
        rr = R + (0.01 if i == 3 else 0.0)
        objs.append(torus(f"binmesh:hoop:{i}", (ox, oy, z), rr, mnr, steel, coll))
    # bottom plate + inner liner so it reads solid, not hollow
    objs.append(
        cyl(
            "binmesh:bottom", (ox, oy, z0 + 0.02), R - 0.01, 0.03, steel, coll, verts=40
        )
    )
    objs.append(
        cyl(
            "binmesh:liner",
            (ox, oy, (z0 + z1) / 2 + 0.02),
            R - 0.03,
            h - 0.06,
            liner,
            coll,
            verts=40,
        )
    )
    # little feet
    for i in range(3):
        a = i / 3 * TAU + 0.4
        x = ox + math.cos(a) * (R - 0.03)
        y = oy + math.sin(a) * (R - 0.03)
        objs.append(
            cyl(f"binmesh:foot:{i}", (x, y, z0 / 2), 0.014, z0, steel, coll, verts=10)
        )
    return objs


def bin_domed(ox, oy, coll, body_mat, lid_mat, liner):
    """Painted-metal covered street bin: tapered body, domed lid, push flap."""
    objs = []
    R = 0.30
    # tapered body
    objs.append(
        cone(
            "bindome:body", (ox, oy, 0.44), R, R - 0.035, 0.80, body_mat, coll, verts=48
        )
    )
    # base ring
    objs.append(torus("bindome:base", (ox, oy, 0.05), R + 0.005, 0.03, body_mat, coll))
    # top rim
    objs.append(torus("bindome:rim", (ox, oy, 0.84), R + 0.005, 0.022, body_mat, coll))
    # domed lid (sits neatly on the rim, not a big mushroom overhang)
    objs.append(
        hemisphere("bindome:lid", (ox, oy, 0.85), R - 0.008, lid_mat, coll, squash=0.48)
    )
    # small top knob / vent
    objs.append(
        cyl("bindome:knob", (ox, oy, 0.95), 0.025, 0.05, lid_mat, coll, verts=16)
    )
    # recessed push-flap opening on the front (-Y face)
    objs.append(
        box(
            "bindome:flap_frame",
            (ox, oy - R + 0.02, 0.55),
            (0.30, 0.05, 0.30),
            lid_mat,
            coll,
            bevel=0.012,
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
    # inner darkness
    objs.append(
        cyl("bindome:liner", (ox, oy, 0.50), R - 0.06, 0.66, liner, coll, verts=40)
    )
    return objs


def bin_wooden(ox, oy, coll, wood, steel, liner):
    """Timber-slat park bin: vertical wood slats + steel bands + liner."""
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
    # steel bands top / middle / bottom
    for z in (z0 + 0.04, cz, z1 - 0.02):
        objs.append(
            torus(f"binwood:band:{z:.2f}", (ox, oy, z), R + 0.012, 0.014, steel, coll)
        )
    # top rim + flared mouth
    objs.append(
        cone(
            "binwood:mouth",
            (ox, oy, z1 + 0.03),
            R + 0.02,
            R + 0.05,
            0.06,
            steel,
            coll,
            verts=40,
        )
    )
    # bottom + liner
    objs.append(
        cyl(
            "binwood:bottom", (ox, oy, z0 + 0.02), R - 0.01, 0.03, steel, coll, verts=36
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
            verts=36,
        )
    )
    return objs


# --------------------------------------------------------------------------- #
# Showroom layout
# --------------------------------------------------------------------------- #
# order alternates bench / bin so a bench+bin pair sits together for the hero
PIECES = [
    ("bench_01_classic", "CLASSIC PARK BENCH", "bench"),
    ("bin_01_mesh", "WIRE-MESH BIN", "bin"),
    ("bench_02_modern", "MODERN SLAT BENCH", "bench"),
    ("bin_02_domed", "DOMED COVER BIN", "bin"),
    ("bench_03_wooden", "TIMBER GARDEN BENCH", "bench"),
    ("bin_03_wooden", "TIMBER SLAT BIN", "bin"),
]
SPACING = 2.6
BASE_Y = 0.0


def piece_positions():
    n = len(PIECES)
    x0 = -(n - 1) / 2 * SPACING
    return {key: (x0 + i * SPACING, BASE_Y) for i, (key, _, _) in enumerate(PIECES)}


def build_pieces(coll):
    pos = piece_positions()
    builders = {
        "bench_01_classic": lambda x, y: bench_classic(
            x, y, coll, MATS["wood_teak"], MATS["cast_iron_green"]
        ),
        "bin_01_mesh": lambda x, y: bin_mesh(
            x, y, coll, MATS["galv_steel"], MATS["liner_black"]
        ),
        "bench_02_modern": lambda x, y: bench_modern(
            x, y, coll, MATS["wood_oak"], MATS["powder_graphite"]
        ),
        "bin_02_domed": lambda x, y: bin_domed(
            x, y, coll, MATS["bin_green"], MATS["steel_dark"], MATS["liner_black"]
        ),
        "bench_03_wooden": lambda x, y: bench_wooden(
            x, y, coll, MATS["wood_dark"], MATS["steel_dark"]
        ),
        "bin_03_wooden": lambda x, y: bin_wooden(
            x, y, coll, MATS["wood_teak"], MATS["steel_dark"], MATS["liner_black"]
        ),
    }
    for key, (x, y) in pos.items():
        builders[key](x, y)
    return pos


def make_label(name, text, loc, coll):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.align_x = "CENTER"
    cu.size = 0.16
    obj = bpy.data.objects.new(name, cu)
    obj.location = loc
    # lie flat-ish, front face toward -Y camera, reads +X
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(MATS["steel_dark"])
    return link_to(obj, coll)


def build_ground(coll):
    # concrete plaza the pieces sit on
    p = box(
        "plaza", (0, 0.0, -0.02), (18.0, 4.2, 0.04), MATS["concrete"], coll, bevel=0.0
    )
    # grass surround (large, sits just below plaza)
    g = box("lawn", (0, 4.0, -0.06), (60.0, 60.0, 0.04), MATS["grass"], coll, bevel=0.0)
    return p, g


# --------------------------------------------------------------------------- #
# World / camera / render  (same proven scaffold as the road showcase)
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
    sky.sun_elevation = math.radians(46)
    sky.sun_rotation = math.radians(-40)
    sky.altitude = 250
    sky.air_density = 1.0
    sky.dust_density = 0.6
    bg.inputs["Strength"].default_value = 0.28
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    sun = bpy.context.object
    sun.data.energy = 2.8
    sun.data.angle = math.radians(2.8)
    sun.data.color = (1.0, 0.96, 0.88)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-40))


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
    scene.cycles.max_bounces = 10
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


def render_orbit_video(center, radius, height, path, samples=130, frames=72):
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
    seq = FRAMES_DIR / "orbit_"
    scene.render.filepath = str(seq)
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
    for key, label, _ in PIECES:
        cx, cy = pos[key]
        make_label(f"label_{key}", label, (cx, cy - 0.62, 0.03), label_c)

    build_world()
    add_sun()
    configure_cycles()

    keys = [p[0] for p in PIECES]
    hero_key_a, hero_key_b = keys[0], keys[1]  # classic bench + mesh bin
    hx = (pos[hero_key_a][0] + pos[hero_key_b][0]) / 2

    # ---- cameras ----
    hero_cam = make_camera(
        "hero_cam", (hx + 1.6, -3.3, 1.55), (hx, 0.05, 0.5), lens=45, fstop=4.0
    )
    overview_cam = make_camera(
        "overview_cam", (0.0, -11.5, 7.4), (0.0, 0.3, 0.4), lens=28
    )
    gallery_cam = make_camera(
        "gallery_cam", (0.0, -11.8, 3.7), (0.0, 0.1, 0.55), lens=24
    )

    bpy.context.scene.camera = hero_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    # quick low-sample smoke test (catch geometry/material errors cheaply)
    if os.environ.get("FURN_QUICK"):
        render_still(
            gallery_cam, OUTPUT_DIR / "quick_gallery.png", samples=48, res=(1280, 720)
        )
        render_still(
            hero_cam, OUTPUT_DIR / "quick_hero.png", samples=48, res=(1280, 720)
        )
        print("[furn] QUICK done ->", OUTPUT_DIR)
        return

    # ---- stills ----
    render_still(hero_cam, HERO_PNG, samples=300)
    render_still(overview_cam, OVERVIEW_PNG, samples=240)
    render_still(gallery_cam, GALLERY_PNG, samples=240)

    # per-piece close-ups
    for key, label, kind in PIECES:
        cx, cy = pos[key]
        look_z = 0.55 if kind == "bench" else 0.5
        cam = make_camera(
            f"cam_{key}",
            (cx + 1.35, cy - 2.5, 1.35),
            (cx, cy, look_z),
            lens=50,
            fstop=3.5,
        )
        render_still(cam, OUTPUT_DIR / f"{key}.png", samples=220)

    # ---- orbit video around the hero bench+bin pairing ----
    render_orbit_video(
        (hx, 0.05, 0.55),
        radius=4.4,
        height=1.9,
        path=VIDEO_PATH,
        samples=140,
        frames=72,
    )

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[furn] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
