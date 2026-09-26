"""Photorealistic procedural ROAD showcase (urban_v3_road).

Why this exists
---------------
Infinigen ships excellent procedural GROUND materials (cobblestone with real
geometric displacement, concrete, dirt, mud, cracked ground, brick / paving
tiles) but it has **no dedicated asphalt material** and **no standalone road
factory** with lane markings — those only live, ad-hoc and gin-driven, inside
the big ``generate_urban.py``.  So this script builds a self-contained,
photo-real road showcase that COMBINES:

  * a custom procedural ASPHALT shader (fine aggregate speckle + micro bump),
  * infinigen's real procedural materials (CobbleStone / Concrete / Dirt / Mud /
    CrackedGround) applied to densely-subdivided panels so their displacement
    actually shows,
  * proper road MARKINGS built as slightly-raised worn-paint geometry:
    double-yellow centre lines, dashed white lane dividers, solid edge lines,
    zebra crosswalks, stop lines and directional arrows,
  * a hero 4-way intersection (the "money shot", matching the reference photos)
    plus a gallery strip of six labelled road types for side-by-side viewing.

Rendered with Cycles + OptiX GPU path tracing, a Nishita physical sky, AgX view
transform and depth-of-field.

Run (needs the infinigen conda env whose python bundles bpy 4.2 + infinigen deps):
  ${WORLDBRIDGE_PYTHON} \
      scripts/generate_urban_v3_road.py

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_road):
  road.blend
  road.png                (hero intersection)
  road_overview.png       (whole showcase, high angle)
  road_gallery.png        (all six material panels)
  road_type_0*_*.png      (six close-ups, one per surface type)
  road_orbit.mp4          (turntable around the intersection)
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
# Make the repo's infinigen source importable, and keep all scratch off "/".
# --------------------------------------------------------------------------- #
REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUTPUT_DIR = Path(
    os.environ.get(
        "URBAN_ROAD_OUT",
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_road",
    )
)
FRAMES_DIR = OUTPUT_DIR / "frames"
TMP_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
for d in (OUTPUT_DIR, FRAMES_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

# Optional: infinigen procedural materials. Import lazily / defensively so the
# script still produces the custom-asphalt content even if a mat fails to build.
_INF = {}
try:
    from infinigen.assets.materials.ceramic.concrete import Concrete
    from infinigen.assets.materials.ceramic.brick import Brick
    from infinigen.assets.materials.terrain.cobble_stone import CobbleStone
    from infinigen.assets.materials.terrain.dirt import Dirt
    from infinigen.assets.materials.terrain.mud import Mud
    from infinigen.assets.materials.terrain.cracked_ground import CrackedGround

    _INF = {
        "concrete": Concrete,
        "brick": Brick,
        "cobble": CobbleStone,
        "dirt": Dirt,
        "mud": Mud,
        "cracked": CrackedGround,
    }
    print("[road] infinigen procedural materials available:", list(_INF))
except Exception as exc:  # pragma: no cover
    print("[road] WARNING infinigen materials unavailable:", repr(exc))


SCENE_PATH = OUTPUT_DIR / "road.blend"
HERO_PNG = OUTPUT_DIR / "road.png"
OVERVIEW_PNG = OUTPUT_DIR / "road_overview.png"
GALLERY_PNG = OUTPUT_DIR / "road_gallery.png"
VIDEO_PATH = OUTPUT_DIR / "road_orbit.mp4"


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
# Simple PBR + custom procedural asphalt / paint shaders (pure bpy nodes)
# --------------------------------------------------------------------------- #
def _set(b, name, value):
    if name in b.inputs:
        b.inputs[name].default_value = value


def pbr(name, color, roughness=0.6, metallic=0.0, ior=1.45):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    _set(b, "IOR", ior)
    return m


def asphalt_material(name="road_asphalt", base=(0.020, 0.021, 0.023), weathered=False):
    """Procedural asphalt: dark bitumen + bright aggregate speckle + micro bump.

    `weathered` lightens/greys the surface and coarsens the bump for an older,
    sun-bleached road.
    """
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    # Object coordinates are in METRES here (scale is baked into the mesh), so
    # texture scales below are "features per metre".
    tex = nodes.new("ShaderNodeTexCoord")

    # large tonal blotches (patched / re-paved / oil-stained areas), ~3-4 m
    n_big = nodes.new("ShaderNodeTexNoise")
    n_big.inputs["Scale"].default_value = 0.28
    n_big.inputs["Detail"].default_value = 4.0
    links.new(tex.outputs["Object"], n_big.inputs["Vector"])

    # aggregate stones ~1.5 cm  (voronoi ~45 cells / m)
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 45.0
    links.new(tex.outputs["Object"], vor.inputs["Vector"])

    # tighter grain for micro roughness / bump
    n_fine = nodes.new("ShaderNodeTexNoise")
    n_fine.inputs["Scale"].default_value = 14.0
    n_fine.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], n_fine.inputs["Vector"])

    # base colour: genuinely dark bitumen, faintly mottled
    ramp = nodes.new("ShaderNodeValToRGB")
    lo = (base[0], base[1], base[2], 1.0)
    hi = (0.045, 0.046, 0.050, 1.0) if not weathered else (0.085, 0.085, 0.088, 1.0)
    ramp.color_ramp.elements[0].color = lo
    ramp.color_ramp.elements[1].color = hi
    links.new(n_big.outputs["Fac"], ramp.inputs["Fac"])

    # sparse light aggregate specks (only the brightest voronoi cells)
    spk = nodes.new("ShaderNodeValToRGB")
    spk.color_ramp.elements[0].position = 0.6
    spk.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    spk.color_ramp.elements[1].position = 0.95
    spk.color_ramp.elements[1].color = (0.11, 0.105, 0.10, 1.0)
    links.new(vor.outputs["Distance"], spk.inputs["Fac"])

    # ADD a faint speckle over the dark base (keeps it genuinely dark)
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "ADD"
    mix.inputs["Fac"].default_value = 0.22 if not weathered else 0.38
    links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    links.new(spk.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    _set(bsdf, "Roughness", 0.92 if not weathered else 0.97)

    # micro surface relief: combine aggregate + fine grain into a bump
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35 if not weathered else 0.5
    bump.inputs["Distance"].default_value = 0.004
    mixb = nodes.new("ShaderNodeMixRGB")
    mixb.inputs["Fac"].default_value = 0.5
    links.new(vor.outputs["Distance"], mixb.inputs["Color1"])
    links.new(n_fine.outputs["Fac"], mixb.inputs["Color2"])
    links.new(mixb.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def paint_material(name, color, wear=0.35):
    """Worn road paint: base colour dimmed unevenly by noise + slight bump."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 8.0
    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.5 - wear * 0.5
    ramp.color_ramp.elements[0].color = (
        color[0] * 0.35,
        color[1] * 0.35,
        color[2] * 0.35,
        1.0,
    )
    ramp.color_ramp.elements[1].position = 0.5 + wear * 0.5
    ramp.color_ramp.elements[1].color = (*color, 1.0)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.62)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


MATS = {}


def build_materials():
    MATS["asphalt"] = asphalt_material("road_asphalt")
    MATS["asphalt_worn"] = asphalt_material("road_asphalt_worn", weathered=True)
    MATS["paint_white"] = paint_material("road_paint_white", (0.72, 0.71, 0.67))
    MATS["paint_yellow"] = paint_material("road_paint_yellow", (0.66, 0.46, 0.03))
    MATS["curb"] = pbr("road_curb", (0.42, 0.41, 0.39), roughness=0.72)
    MATS["grass"] = grass_material("road_grass")


def grass_material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 12.0
    noise.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.075, 0.020, 1.0)
    ramp.color_ramp.elements[1].color = (0.075, 0.14, 0.045, 1.0)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.95)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def _grey_concrete():
    """infinigen Concrete but forced to a neutral grey (default is random-tinted)."""
    from infinigen.core import surface
    from infinigen.assets.materials.ceramic.concrete import shader_concrete

    return surface.shaderfunc_to_material(
        shader_concrete, base_color_hsv=(0.07, 0.03, 0.48), name="road_concrete"
    )


def _desaturate(obj, name_substr, saturation, value):
    """Some infinigen terrain shaders (dirt, cracked ground) draw an overly
    saturated / pinkish random base colour.  Pull the applied material back
    toward a neutral earthy tone by inserting a Hue/Sat/Value node in front of
    the Principled BSDF's Base Color link."""
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes or name_substr not in mat.name.lower():
            continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue
        bc = bsdf.inputs["Base Color"]
        if not bc.is_linked:
            continue
        src = bc.links[0].from_socket
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value = saturation
        hsv.inputs["Value"].default_value = value
        nt.links.new(src, hsv.inputs["Color"])
        nt.links.new(hsv.outputs["Color"], bc)


def apply_infinigen(obj, key):
    """Apply an infinigen procedural material (with geo displacement if any)."""
    cls = _INF.get(key)
    if cls is None:
        obj.data.materials.append(MATS["asphalt_worn"])
        return False
    # deterministic look across runs
    import random as _r
    import numpy as _np

    _r.seed(hash(key) & 0xFFFF)
    _np.random.seed(hash(key) & 0xFFFF)
    try:
        if key == "concrete":
            obj.data.materials.append(_grey_concrete())
            return True
        inst = cls()
        if hasattr(inst, "apply"):
            inst.apply(obj)
        else:
            obj.data.materials.append(inst.generate())
        if key == "dirt":
            _desaturate(obj, "dirt", saturation=0.45, value=0.9)
        elif key == "cracked":
            _desaturate(obj, "cracked", saturation=0.4, value=0.72)
        return True
    except Exception as exc:
        print(f"[road] infinigen '{key}' failed: {exc!r}; falling back")
        obj.data.materials.append(MATS["asphalt_worn"])
        return False


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def slab(name, loc, dims, material, coll, yaw=0.0):
    """A flat box (road surface / marking / curb)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[2] = yaw
    if material:
        obj.data.materials.append(material)
    return link_to(obj, coll)


def grid_panel(name, loc, dims, coll, cuts_x=160, cuts_y=420):
    """A densely subdivided plane so infinigen SDF-perturb mats can displace."""
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=cuts_x, y_subdivisions=cuts_y, size=1, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (dims[0], dims[1], 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return link_to(obj, coll)


# paint sits flush with the asphalt — a single flat plane a few mm above the
# surface, just enough to avoid z-fighting.  Real road paint is not a raised kerb.
MARK_Z = 0.004


def flat_decal(name, loc, dims, material, coll, yaw=0.0):
    """A painted road marking: a flat plane flush with the road (NOT a raised
    box).  `dims` is (size_x, size_y, _ignored_thickness)."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=(loc[0], loc[1], MARK_Z))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (dims[0], dims[1], 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[2] = yaw
    if material:
        obj.data.materials.append(material)
    return link_to(obj, coll)


def arrow_mesh(name, center, coll, material, yaw=0.0, length=3.4, width=0.9):
    """A straight-ahead lane arrow (shaft + head) as flat paint geometry."""
    hw = width / 2
    shaft_l = length * 0.55
    head_l = length * 0.45
    verts = [
        (-hw * 0.42, -length / 2, 0),
        (hw * 0.42, -length / 2, 0),
        (hw * 0.42, -length / 2 + shaft_l, 0),
        (-hw * 0.42, -length / 2 + shaft_l, 0),
        (-hw, -length / 2 + shaft_l, 0),
        (hw, -length / 2 + shaft_l, 0),
        (0.0, length / 2, 0),
    ]
    faces = [(0, 1, 2, 3), (4, 5, 6)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    obj.location = (center[0], center[1], MARK_Z)
    obj.rotation_euler = (0, 0, yaw)
    return link_to(obj, coll)


# --------------------------------------------------------------------------- #
# Hero 4-way intersection
# --------------------------------------------------------------------------- #
RW = 6.0  # road half-width  (=> 12 m carriageway, 2 lanes each way)
ARM = 20.0  # arm length from centre
LANE = RW / 2  # 3 m lane


def crosswalk(name, axis, sign, coll):
    """Zebra crossing at a road mouth. axis 'x' = crossing the E/W road."""
    bar_w, gap = 0.55, 0.55
    span = 2 * RW - 0.6
    n = int(span / (bar_w + gap))
    start = -span / 2 + bar_w / 2
    band_pos = sign * (RW + 2.0)  # just outside the junction box
    for i in range(n):
        off = start + i * (bar_w + gap)
        if axis == "x":  # crossing the E/W carriageway -> bars run along X
            flat_decal(
                f"{name}:{i}",
                (band_pos, off),
                (2.4, bar_w, 0.02),
                MATS["paint_white"],
                coll,
            )
        else:  # crossing N/S carriageway -> bars run along Y
            flat_decal(
                f"{name}:{i}",
                (off, band_pos),
                (bar_w, 2.4, 0.02),
                MATS["paint_white"],
                coll,
            )


def stop_line(name, axis, sign, coll):
    band_pos = sign * (RW + 3.6)
    if axis == "x":
        # only the approaching half of the carriageway
        flat_decal(
            name, (band_pos, sign * -RW / 2), (0.5, RW, 0.02), MATS["paint_white"], coll
        )
    else:
        flat_decal(
            name, (sign * RW / 2, band_pos), (RW, 0.5, 0.02), MATS["paint_white"], coll
        )


def build_intersection(coll):
    # carriageways (top surface at z=0)
    slab("hero:road_ew", (0, 0, -0.06), (2 * ARM, 2 * RW, 0.12), MATS["asphalt"], coll)
    slab("hero:road_ns", (0, 0, -0.058), (2 * RW, 2 * ARM, 0.12), MATS["asphalt"], coll)

    # ---- lane markings on the E/W arms (skip the junction box |x|<RW) ----
    for xseg in range(1):
        pass
    dash_len, dash_gap = 3.0, 3.0
    step = dash_len + dash_gap

    def ew_arm(sign):
        x = RW + 1.0
        while x < ARM - 1.0:
            # centre double-yellow (solid) — draw as short slabs to follow arm
            x += 0
            break
        # solid double yellow centre
        flat_decal(
            f"hero:cy1:{sign}",
            (sign * (RW + (ARM - RW) / 2), 0.18),
            ((ARM - RW), 0.16, 0.02),
            MATS["paint_yellow"],
            coll,
        )
        flat_decal(
            f"hero:cy2:{sign}",
            (sign * (RW + (ARM - RW) / 2), -0.18),
            ((ARM - RW), 0.16, 0.02),
            MATS["paint_yellow"],
            coll,
        )
        # solid white edge lines
        for ey in (-RW + 0.35, RW - 0.35):
            flat_decal(
                f"hero:edge:{sign}:{ey:.1f}",
                (sign * (RW + (ARM - RW) / 2), ey),
                ((ARM - RW), 0.14, 0.02),
                MATS["paint_white"],
                coll,
            )
        # dashed white lane dividers at ±LANE
        for ly in (-LANE, LANE):
            xx = RW + 1.5
            i = 0
            while xx < ARM - 1.0:
                flat_decal(
                    f"hero:dash:{sign}:{ly:.0f}:{i}",
                    (sign * xx, ly),
                    (dash_len, 0.13, 0.02),
                    MATS["paint_white"],
                    coll,
                )
                xx += step
                i += 1
        # a forward arrow in each approach lane
        arrow_mesh(
            f"hero:arrow:{sign}:a",
            (sign * (RW + 3.0), sign * -LANE),
            coll,
            MATS["paint_white"],
            yaw=(0 if sign > 0 else math.pi),
        )

    def ns_arm(sign):
        flat_decal(
            f"hero:cyn1:{sign}",
            (0.18, sign * (RW + (ARM - RW) / 2)),
            (0.16, (ARM - RW), 0.02),
            MATS["paint_yellow"],
            coll,
        )
        flat_decal(
            f"hero:cyn2:{sign}",
            (-0.18, sign * (RW + (ARM - RW) / 2)),
            (0.16, (ARM - RW), 0.02),
            MATS["paint_yellow"],
            coll,
        )
        for ex in (-RW + 0.35, RW - 0.35):
            flat_decal(
                f"hero:edgen:{sign}:{ex:.1f}",
                (ex, sign * (RW + (ARM - RW) / 2)),
                (0.14, (ARM - RW), 0.02),
                MATS["paint_white"],
                coll,
            )
        for lx in (-LANE, LANE):
            yy = RW + 1.5
            i = 0
            while yy < ARM - 1.0:
                flat_decal(
                    f"hero:dashn:{sign}:{lx:.0f}:{i}",
                    (lx, sign * yy),
                    (0.13, dash_len, 0.02),
                    MATS["paint_white"],
                    coll,
                )
                yy += step
                i += 1

    for s in (1, -1):
        ew_arm(s)
        ns_arm(s)
        crosswalk(f"hero:cw:x:{s}", "x", s, coll)
        crosswalk(f"hero:cw:y:{s}", "y", s, coll)
        stop_line(f"hero:stop:x:{s}", "x", s, coll)
        stop_line(f"hero:stop:y:{s}", "y", s, coll)

    # ---- curbs + concrete sidewalks in the four corners ----
    concrete_ok = "concrete" in _INF
    for sx in (1, -1):
        for sy in (1, -1):
            cx, cy = sx * (RW + 6.0), sy * (RW + 6.0)
            # sidewalk pad
            pad = grid_panel(
                f"hero:sidewalk:{sx}:{sy}",
                (cx, cy, 0.07),
                (12.0, 12.0),
                coll,
                cuts_x=60,
                cuts_y=60,
            )
            if concrete_ok:
                apply_infinigen(pad, "concrete")
            else:
                pad.data.materials.append(MATS["curb"])
            # curbs facing the road
            slab(
                f"hero:curb_x:{sx}:{sy}",
                (sx * (RW + 0.13), cy, 0.09),
                (0.26, 12.0, 0.22),
                MATS["curb"],
                coll,
            )
            slab(
                f"hero:curb_y:{sx}:{sy}",
                (cx, sy * (RW + 0.13), 0.09),
                (12.0, 0.26, 0.22),
                MATS["curb"],
                coll,
            )


# --------------------------------------------------------------------------- #
# Material gallery: six labelled road panels
# --------------------------------------------------------------------------- #
GALLERY_Y = 46.0
PANEL_W, PANEL_L = 6.0, 16.0
PANEL_SPACING = 7.4

GALLERY = [
    ("01_asphalt", "ASPHALT", "custom"),
    ("02_cobble", "COBBLESTONE", "cobble"),
    ("03_concrete", "CONCRETE", "concrete"),
    ("04_dirt", "DIRT ROAD", "dirt"),
    ("05_mud", "MUD TRACK", "mud"),
    ("06_cracked", "CRACKED GROUND", "cracked"),
]


def build_gallery(coll):
    n = len(GALLERY)
    x0 = -(n - 1) / 2 * PANEL_SPACING
    centers = {}
    for i, (key, label, kind) in enumerate(GALLERY):
        cx = x0 + i * PANEL_SPACING
        cy = GALLERY_Y
        centers[key] = (cx, cy)
        if kind == "custom":  # asphalt panel + markings
            slab(
                f"gal:{key}",
                (cx, cy, -0.05),
                (PANEL_W, PANEL_L, 0.1),
                MATS["asphalt"],
                coll,
            )
            # a dashed centre line so it reads as a road
            yy = cy - PANEL_L / 2 + 1.0
            j = 0
            while yy < cy + PANEL_L / 2 - 1.0:
                flat_decal(
                    f"gal:{key}:dash:{j}",
                    (cx, yy),
                    (0.14, 1.4, 0.02),
                    MATS["paint_white"],
                    coll,
                )
                yy += 2.6
                j += 1
        else:
            dense = kind in ("cobble", "dirt", "mud", "cracked")
            panel = grid_panel(
                f"gal:{key}",
                (cx, cy, 0.0),
                (PANEL_W, PANEL_L),
                coll,
                cuts_x=(180 if dense else 40),
                cuts_y=(480 if dense else 60),
            )
            apply_infinigen(panel, kind)
        make_label(f"gal:{key}:label", label, (cx, cy - PANEL_L / 2 - 1.4), coll)
    return centers


def make_label(name, text, loc, coll):
    """Small standing sign with the material name (best-effort)."""
    try:
        bpy.ops.object.text_add(location=(loc[0], loc[1], 0.02))
        txt = bpy.context.object
        txt.name = name
        txt.data.body = text
        txt.data.align_x = "CENTER"
        txt.data.extrude = 0.006
        txt.data.size = 0.62
        # stand upright, front face toward -Y (the gallery camera), reads +X
        txt.rotation_euler = (math.pi / 2, 0, 0)
        mat = pbr(f"{name}_mat", (0.9, 0.9, 0.88), roughness=0.4)
        txt.data.materials.append(mat)
        link_to(txt, coll)
    except Exception as exc:
        print(f"[road] label '{text}' skipped: {exc!r}")


# --------------------------------------------------------------------------- #
# Ground, world, sun, cameras, render config
# --------------------------------------------------------------------------- #
def build_ground(coll):
    slab("ground", (0, 22, -0.12), (160, 160, 0.2), MATS["grass"], coll)


def build_world():
    world = bpy.data.worlds.new("road_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(-35)
    sky.altitude = 250
    sky.air_density = 1.0
    sky.dust_density = 0.7
    # sky is ambient fill / reflections only; the sun lamp is the key light.
    bg.inputs["Strength"].default_value = 0.18
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    sun = bpy.context.object
    sun.data.energy = 2.6
    sun.data.angle = math.radians(3.5)  # softer disc -> less pinpoint glitter
    sun.data.color = (1.0, 0.95, 0.86)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-35))


def make_camera(name, loc, look_at, lens=42, fstop=None):
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
    print(f"[road] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 8
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
    scene.view_settings.exposure = -2.2
    print(
        f"[road] view_transform={scene.view_settings.view_transform} "
        f"look={scene.view_settings.look} exposure={scene.view_settings.exposure}"
    )


def render_still(cam, path, samples=256, res=(1920, 1080)):
    scene = bpy.context.scene
    scene.camera = cam
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(1)
    scene.render.filepath = str(path)
    print(f"[road] render still -> {path.name}")
    bpy.ops.render.render(write_still=True)


def render_orbit_video(center, radius, height, path, samples=140, frames=72):
    """Render a turntable PNG sequence then mux to mp4 with system ffmpeg."""
    scene = bpy.context.scene
    cam = make_camera(
        "orbit_cam",
        (center[0] + radius, center[1], height),
        center,
        lens=40,
        fstop=None,
    )
    focus = Vector((center[0], center[1], center[2]))
    for f in range(1, frames + 1):
        ang = (f - 1) / frames * math.tau
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
    print("[road] render orbit frames ...")
    bpy.ops.render.render(animation=True)
    # mux with system ffmpeg (reliable) -> mp4
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
            f"[road] video muxed -> {path.name} " f"({path.stat().st_size // 1024} KiB)"
        )
    except Exception as exc:
        print(f"[road] ffmpeg mux failed: {exc!r}")


# --------------------------------------------------------------------------- #
def main():
    reset_scene()
    build_materials()

    ground_c = add_collection("road_ground")
    hero_c = add_collection("road_hero")
    gallery_c = add_collection("road_gallery")

    build_ground(ground_c)
    build_intersection(hero_c)
    centers = build_gallery(gallery_c)

    build_world()
    add_sun()
    configure_cycles()

    # ---- cameras ----
    hero_cam = make_camera(
        "hero_cam", (16.5, -15.0, 6.2), (0, 2.5, 0), lens=35, fstop=6.0
    )
    overview_cam = make_camera("overview_cam", (34, -18, 34), (0, 24, 0), lens=30)
    gal_center = (0.0, GALLERY_Y, 0.3)
    gallery_cam = make_camera(
        "gallery_cam", (0.0, GALLERY_Y - 24.0, 21.0), gal_center, lens=34
    )

    bpy.context.scene.camera = hero_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))

    # ---- stills ----
    render_still(hero_cam, HERO_PNG, samples=300)
    render_still(overview_cam, OVERVIEW_PNG, samples=240)
    render_still(gallery_cam, GALLERY_PNG, samples=240)

    # per-panel close-ups
    for key, label, kind in GALLERY:
        cx, cy = centers[key]
        cam = make_camera(
            f"cam_{key}", (cx + 2.6, cy - 5.4, 3.0), (cx, cy, 0.05), lens=45, fstop=4.5
        )
        render_still(cam, OUTPUT_DIR / f"road_type_{key}.png", samples=220)

    # ---- orbit video around the intersection ----
    render_orbit_video(
        (0, 0, 0.4), radius=26.0, height=11.0, path=VIDEO_PATH, samples=140, frames=72
    )

    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[road] DONE ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
