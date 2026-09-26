"""Photorealistic procedural bus-shelter scene (urban_v3_busstop).

A modern "JCDecaux / Adshel" street bus stop: an aluminium-framed glass
shelter with a cantilever roof, a perforated-steel slat bench, a backlit
advertising light-box at one end, an illuminated route totem, a wall
timetable and a litter bin — sitting on a kerbed sidewalk beside a bus
lane.  Built with the same realism stack as urban_v3_trafficlight:

  * Cycles + OPTIX GPU path tracing with OptiX denoising.
  * Nishita physical-sky world (split via Light Path) -> real image-based
    lighting + reflections in the glass and brushed metal.
  * PBR materials: tinted architectural glass, brushed anodised aluminium,
    powder-coated steel, an emissive backlit poster + route sign.
  * DoF camera, AgX view transform, 1080p hero still + 720p orbit video.

Run:
  ${BLENDER_BIN} -b --python \
    scripts/generate_urban_v3_busstop.py

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_busstop):
  bus_stop.blend  bus_stop.png  bus_stop.mp4
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_busstop")
SCENE_PATH = OUTPUT_DIR / "bus_stop.blend"
STILL_PATH = OUTPUT_DIR / "bus_stop.png"
VIDEO_PATH = OUTPUT_DIR / "bus_stop.mp4"


# --------------------------------------------------------------------------- #
# Scene bookkeeping
# --------------------------------------------------------------------------- #
def reset_scene() -> None:
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
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def link_to(obj, collection):
    collection.objects.link(obj)
    try:
        bpy.context.collection.objects.unlink(obj)
    except RuntimeError:
        pass
    return obj


def smooth(obj):
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
    return obj


# --------------------------------------------------------------------------- #
# Materials (node-based PBR)
# --------------------------------------------------------------------------- #
def _set(bsdf, name, value):
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value


def pbr(
    name,
    color,
    roughness=0.5,
    metallic=0.0,
    ior=1.45,
    transmission=0.0,
    coat=0.0,
    coat_rough=0.05,
    emission=None,
    emission_strength=0.0,
    anisotropy=0.0,
    alpha=1.0,
    specular=0.5,
):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    _set(b, "Base Color", (color[0], color[1], color[2], 1.0))
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    _set(b, "IOR", ior)
    _set(b, "Alpha", alpha)
    _set(b, "Specular IOR Level", specular)
    for key in ("Transmission Weight", "Transmission"):
        if key in b.inputs:
            b.inputs[key].default_value = transmission
            break
    for key in ("Coat Weight", "Coat"):
        if key in b.inputs:
            b.inputs[key].default_value = coat
            break
    _set(b, "Coat Roughness", coat_rough)
    _set(b, "Anisotropic", anisotropy)
    if emission is not None:
        _set(b, "Emission Color", (emission[0], emission[1], emission[2], 1.0))
        _set(b, "Emission Strength", emission_strength)
    if transmission > 0.5 or alpha < 1.0:
        m.use_screen_refraction = True
    return m


MATS = {}


def build_materials():
    MATS.update(
        {
            # --- ground ---------------------------------------------------- #
            "asphalt": pbr("bs_asphalt", (0.022, 0.022, 0.024), roughness=0.9),
            "sidewalk": pbr("bs_sidewalk", (0.30, 0.295, 0.28), roughness=0.86),
            "paver": pbr("bs_paver", (0.34, 0.335, 0.32), roughness=0.8),
            "curb": pbr("bs_curb", (0.40, 0.39, 0.37), roughness=0.78),
            "tactile": pbr("bs_tactile", (0.72, 0.62, 0.10), roughness=0.6),
            "paint_white": pbr("bs_paint_white", (0.66, 0.64, 0.60), roughness=0.55),
            "paint_red": pbr("bs_paint_red", (0.32, 0.03, 0.02), roughness=0.6),
            # --- structural metal ------------------------------------------ #
            # brushed anodised aluminium frame + posts
            "alu": pbr(
                "bs_alu",
                (0.55, 0.56, 0.58),
                roughness=0.34,
                metallic=1.0,
                anisotropy=0.35,
            ),
            "alu_dark": pbr(
                "bs_alu_dark",
                (0.10, 0.105, 0.11),
                roughness=0.42,
                metallic=1.0,
                anisotropy=0.2,
            ),
            # powder-coated steel roof (satin light grey)
            "roof": pbr("bs_roof", (0.40, 0.41, 0.42), roughness=0.45, coat=0.3),
            "roof_under": pbr("bs_roof_under", (0.62, 0.62, 0.63), roughness=0.5),
            "dark_metal": pbr(
                "bs_dark_metal", (0.03, 0.031, 0.032), roughness=0.4, metallic=0.85
            ),
            # --- glass ----------------------------------------------------- #
            # tinted architectural safety glass
            "glass": pbr(
                "bs_glass",
                (0.62, 0.72, 0.72),
                roughness=0.04,
                transmission=0.96,
                ior=1.5,
                alpha=0.28,
            ),
            "glass_ad": pbr(
                "bs_glass_ad",
                (0.85, 0.88, 0.9),
                roughness=0.05,
                transmission=0.9,
                ior=1.5,
                alpha=0.2,
            ),
            # --- emissive advertising / signage ---------------------------- #
            "lightbox": pbr(
                "bs_lightbox",
                (1.0, 0.98, 0.94),
                emission=(1.0, 0.97, 0.92),
                emission_strength=7.0,
            ),
            "poster_bg": pbr(
                "bs_poster_bg",
                (0.03, 0.32, 0.42),
                emission=(0.04, 0.42, 0.55),
                emission_strength=4.2,
            ),
            "poster_accent": pbr(
                "bs_poster_accent",
                (0.95, 0.28, 0.12),
                emission=(1.0, 0.30, 0.12),
                emission_strength=4.6,
            ),
            "poster_light": pbr(
                "bs_poster_light",
                (0.96, 0.96, 0.94),
                emission=(0.98, 0.98, 0.95),
                emission_strength=4.8,
            ),
            "sign_blue": pbr(
                "bs_sign_blue",
                (0.02, 0.12, 0.55),
                emission=(0.03, 0.18, 0.72),
                emission_strength=6.0,
            ),
            "sign_white": pbr(
                "bs_sign_white",
                (0.95, 0.96, 0.98),
                emission=(0.95, 0.96, 0.98),
                emission_strength=6.5,
            ),
            "timetable": pbr(
                "bs_timetable",
                (0.9, 0.91, 0.92),
                emission=(0.85, 0.87, 0.9),
                emission_strength=2.2,
            ),
            "timetable_line": pbr("bs_tt_line", (0.05, 0.06, 0.09), roughness=0.5),
            "downlight": pbr(
                "bs_downlight",
                (1.0, 0.95, 0.85),
                emission=(1.0, 0.95, 0.85),
                emission_strength=9.0,
            ),
            # --- bench / bin ----------------------------------------------- #
            "bench": pbr("bs_bench", (0.09, 0.10, 0.12), roughness=0.5, metallic=0.7),
            "bin_body": pbr("bs_bin", (0.13, 0.14, 0.15), roughness=0.45, metallic=0.7),
            # --- context --------------------------------------------------- #
            "brick": pbr("bs_brick", (0.30, 0.24, 0.20), roughness=0.82),
            "window": pbr("bs_window", (0.05, 0.07, 0.09), roughness=0.06, coat=0.6),
            "pole": pbr("bs_pole", (0.30, 0.31, 0.32), roughness=0.4, metallic=1.0),
            "lamp_glow": pbr(
                "bs_lamp_glow",
                (1.0, 0.9, 0.7),
                emission=(1.0, 0.9, 0.7),
                emission_strength=5.0,
            ),
            "grass": pbr("bs_grass", (0.06, 0.16, 0.05), roughness=0.9),
            "leaf": pbr("bs_leaf", (0.03, 0.13, 0.04), roughness=0.8),
            "trunk": pbr("bs_trunk", (0.10, 0.07, 0.05), roughness=0.85),
        }
    )


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _bevel(obj, width=0.012, segments=2):
    if width <= 0:
        return
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("wn", "WEIGHTED_NORMAL")


def cube(name, loc, dims, material, coll, yaw=0.0, bevel_width=0.012):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[2] = yaw
    if material:
        obj.data.materials.append(material)
    _bevel(obj, bevel_width)
    return link_to(obj, coll)


def sphere(name, loc, scale, material, coll, segments=40):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=max(10, segments // 2), radius=1, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, coll)


def cyl_between(name, start, end, radius, material, coll, vertices=40):
    a, b = Vector(start), Vector(end)
    mid = (a + b) * 0.5
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=d.length, location=mid
    )
    obj = bpy.context.object
    obj.name = name
    if d.length > 1e-6:
        obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, coll)


def cyl(name, loc, radius, depth, material, coll, vertices=40, axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    if axis == "X":
        obj.rotation_euler = (0, math.radians(90), 0)
    elif axis == "Y":
        obj.rotation_euler = (math.radians(90), 0, 0)
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, coll)


# --------------------------------------------------------------------------- #
# Bus shelter
# --------------------------------------------------------------------------- #
# The shelter stands on the sidewalk (+Y side) and opens toward the road (-Y).
# Width runs along X, depth along Y.
W = 4.6  # overall width (X)
D = 1.55  # overall depth (Y)
H = 2.42  # eave height (Z)
Y_BACK = D / 2  # rear glass wall plane (+Y)
Y_FRONT = -D / 2  # front eave plane (-Y)
X_L = -W / 2  # left end (totem side)
X_R = W / 2  # right end (ad light-box side)


def glass_panel(name, loc, dims, coll, mat="glass"):
    """A framed glass pane: alu frame border + thin transmissive glass."""
    cube(name + ":glass", loc, dims, MATS[mat], coll, bevel_width=0.004)
    # slim frame around the pane (four edges), thickness set by the two
    # near-zero dims of the pane.
    sx, sy, sz = dims
    fr = 0.05
    if sx < sy and sx < sz:  # pane faces X (end wall)
        for dz in (-sz / 2, sz / 2):
            cube(
                f"{name}:fr_h{dz:.2f}",
                (loc[0], loc[1], loc[2] + dz),
                (sx * 2.2, sy, fr),
                MATS["alu"],
                coll,
                bevel_width=0.006,
            )
        for dy in (-sy / 2, sy / 2):
            cube(
                f"{name}:fr_v{dy:.2f}",
                (loc[0], loc[1] + dy, loc[2]),
                (sx * 2.2, fr, sz),
                MATS["alu"],
                coll,
                bevel_width=0.006,
            )
    else:  # pane faces Y (rear/front wall)
        for dz in (-sz / 2, sz / 2):
            cube(
                f"{name}:fr_h{dz:.2f}",
                (loc[0], loc[1], loc[2] + dz),
                (sx, sy * 2.2, fr),
                MATS["alu"],
                coll,
                bevel_width=0.006,
            )
        for dx in (-sx / 2, sx / 2):
            cube(
                f"{name}:fr_v{dx:.2f}",
                (loc[0] + dx, loc[1], loc[2]),
                (fr, sy * 2.2, sz),
                MATS["alu"],
                coll,
                bevel_width=0.006,
            )


def build_shelter(coll):
    # ---- 4 corner posts (brushed aluminium, slightly inset) ------------- #
    px, py = W / 2 - 0.10, D / 2 - 0.10
    post_xy = [(-px, -py), (px, -py), (-px, py), (px, py)]
    for i, (x, y) in enumerate(post_xy):
        cube(
            f"shelter:post:{i}",
            (x, y, H / 2),
            (0.11, 0.11, H),
            MATS["alu"],
            coll,
            bevel_width=0.02,
        )
        # cast base foot
        cube(
            f"shelter:foot:{i}",
            (x, y, 0.05),
            (0.20, 0.20, 0.10),
            MATS["dark_metal"],
            coll,
            bevel_width=0.015,
        )

    # ---- roof: slightly forward-cantilevered slab ----------------------- #
    roof_z = H + 0.11
    cube(
        "shelter:roof",
        (0, -0.12, roof_z),
        (W + 0.34, D + 0.55, 0.14),
        MATS["roof"],
        coll,
        bevel_width=0.05,
    )
    # bright underside so the interior does not read as a dark cave
    cube(
        "shelter:roof_under",
        (0, -0.12, roof_z - 0.085),
        (W + 0.20, D + 0.42, 0.02),
        MATS["roof_under"],
        coll,
        bevel_width=0.02,
    )
    # front fascia lip
    cube(
        "shelter:fascia",
        (0, Y_FRONT - 0.42, roof_z - 0.02),
        (W + 0.34, 0.06, 0.20),
        MATS["roof"],
        coll,
        bevel_width=0.02,
    )
    # recessed downlights under the roof
    for i, x in enumerate((-1.4, 0.0, 1.4)):
        cyl(
            f"shelter:downlight:{i}",
            (x, -0.1, roof_z - 0.11),
            0.09,
            0.02,
            MATS["downlight"],
            coll,
            vertices=24,
        )

    # ---- rear glass wall: 3 panes split by mullions --------------------- #
    pane_w = (W - 0.3) / 3
    for i in range(3):
        x = -W / 2 + 0.15 + pane_w * (i + 0.5)
        glass_panel(
            f"shelter:rear:{i}", (x, Y_BACK, 1.15), (pane_w - 0.06, 0.028, 1.86), coll
        )

    # ---- left end glass ------------------------------------------------- #
    glass_panel(
        "shelter:end_l", (X_L + 0.02, 0.06, 1.15), (0.028, D - 0.28, 1.86), coll
    )

    # ---- right end: backlit advertising light-box ----------------------- #
    build_ad_lightbox(coll)

    # ---- interior slat bench against the rear wall ---------------------- #
    build_bench(coll)

    # ---- wall-mounted timetable panel on the rear glass ----------------- #
    build_timetable(coll)

    # ---- litter bin ----------------------------------------------------- #
    build_bin(coll, (X_L + 0.55, Y_FRONT + 0.30))

    # ---- illuminated route totem at the boarding (right/front) corner --- #
    build_totem(coll, (X_R + 0.45, Y_FRONT + 0.10))


def build_ad_lightbox(coll):
    x = X_R - 0.02
    cz = 1.2
    # aluminium enclosure
    cube(
        "ad:enclosure",
        (x, 0.06, cz),
        (0.16, D - 0.18, 1.94),
        MATS["alu"],
        coll,
        bevel_width=0.02,
    )
    # emissive backlight core (both faces glow through the poster)
    cube(
        "ad:backlight",
        (x, 0.06, cz),
        (0.05, D - 0.42, 1.70),
        MATS["lightbox"],
        coll,
        bevel_width=0.004,
    )
    # poster graphic on each face (a simple route/ad composition)
    for sign, face in ((1, "out"), (-1, "in")):
        fx = x + sign * 0.085
        # teal background
        cube(
            f"ad:poster_bg:{face}",
            (fx, 0.06, cz),
            (0.006, D - 0.44, 1.72),
            MATS["poster_bg"],
            coll,
            bevel_width=0,
        )
        # top accent band
        cube(
            f"ad:poster_top:{face}",
            (fx + sign * 0.002, 0.06, cz + 0.72),
            (0.004, D - 0.44, 0.26),
            MATS["poster_accent"],
            coll,
            bevel_width=0,
        )
        # central light roundel
        cyl(
            f"ad:poster_roundel:{face}",
            (fx + sign * 0.003, 0.06, cz + 0.05),
            0.32,
            0.004,
            MATS["poster_light"],
            coll,
            vertices=40,
            axis="X",
        )
        # lower text bars
        for k, dz in enumerate((-0.55, -0.68, -0.81)):
            cube(
                f"ad:poster_bar:{face}:{k}",
                (fx + sign * 0.002, 0.06, cz + dz),
                (0.004, (D - 0.6) * (0.8 - 0.12 * k), 0.045),
                MATS["poster_light"],
                coll,
                bevel_width=0,
            )
    # glass cover over the poster
    cube(
        "ad:cover",
        (x + 0.11, 0.06, cz),
        (0.02, D - 0.30, 1.80),
        MATS["glass_ad"],
        coll,
        bevel_width=0.004,
    )
    cube(
        "ad:cover2",
        (x - 0.11, 0.06, cz),
        (0.02, D - 0.30, 1.80),
        MATS["glass_ad"],
        coll,
        bevel_width=0.004,
    )


def build_bench(coll):
    seat_z = 0.46
    y0 = Y_BACK - 0.30
    # support brackets off the rear posts
    for i, x in enumerate((-1.55, 0.0, 1.55)):
        cube(
            f"bench:bracket:{i}",
            (x, y0 + 0.12, seat_z - 0.14),
            (0.06, 0.44, 0.30),
            MATS["alu_dark"],
            coll,
            bevel_width=0.01,
        )
    # seat slats (perforated-steel look via thin dark slats)
    for k in range(6):
        y = y0 - 0.24 + k * 0.075
        cube(
            f"bench:seat:{k}",
            (0, y, seat_z),
            (3.35, 0.055, 0.035),
            MATS["bench"],
            coll,
            bevel_width=0.006,
        )
    # backrest slats leaning on the rear glass
    for k in range(4):
        z = seat_z + 0.20 + k * 0.11
        cube(
            f"bench:back:{k}",
            (0, y0 + 0.26, z),
            (3.35, 0.05, 0.045),
            MATS["bench"],
            coll,
            bevel_width=0.006,
        )
    # armrest dividers
    for x in (-1.68, 0.0, 1.68):
        cube(
            f"bench:div:{x:.1f}",
            (x, y0 - 0.02, seat_z + 0.02),
            (0.05, 0.5, 0.10),
            MATS["alu_dark"],
            coll,
            bevel_width=0.01,
        )


def build_timetable(coll):
    x = 1.35
    cz = 1.35
    cube(
        "tt:frame",
        (x, Y_BACK - 0.05, cz),
        (0.62, 0.03, 0.92),
        MATS["alu"],
        coll,
        bevel_width=0.008,
    )
    cube(
        "tt:face",
        (x, Y_BACK - 0.065, cz),
        (0.54, 0.01, 0.82),
        MATS["timetable"],
        coll,
        bevel_width=0.003,
    )
    # header + schedule lines
    cube(
        "tt:header",
        (x, Y_BACK - 0.072, cz + 0.34),
        (0.5, 0.006, 0.10),
        MATS["poster_bg"],
        coll,
        bevel_width=0,
    )
    for k in range(7):
        z = cz + 0.20 - k * 0.075
        cube(
            f"tt:line:{k}",
            (x, Y_BACK - 0.072, z),
            (0.44, 0.006, 0.018),
            MATS["timetable_line"],
            coll,
            bevel_width=0,
        )


def build_bin(coll, xy):
    x, y = xy
    cyl("bin:body", (x, y, 0.52), 0.20, 0.72, MATS["bin_body"], coll, vertices=28)
    cyl("bin:rim", (x, y, 0.90), 0.215, 0.06, MATS["alu"], coll, vertices=28)
    cyl("bin:lid", (x, y, 0.96), 0.18, 0.05, MATS["alu_dark"], coll, vertices=28)
    cyl("bin:post", (x, y, 0.25), 0.03, 0.5, MATS["alu"], coll, vertices=16)


def build_totem(coll, xy):
    x, y = xy
    # slim mast
    cube(
        "totem:mast",
        (x, y, 1.55),
        (0.14, 0.14, 3.1),
        MATS["alu"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "totem:foot",
        (x, y, 0.06),
        (0.24, 0.24, 0.12),
        MATS["dark_metal"],
        coll,
        bevel_width=0.015,
    )
    # top illuminated bus-sign box
    bz = 3.0
    cube(
        "totem:box",
        (x, y, bz),
        (0.55, 0.16, 0.55),
        MATS["sign_blue"],
        coll,
        bevel_width=0.02,
    )
    # white bus glyph: body + windows + wheels (simple readable icon)
    fy = y - 0.09
    cube(
        "totem:bus_body",
        (x, fy, bz + 0.02),
        (0.36, 0.006, 0.20),
        MATS["sign_white"],
        coll,
        bevel_width=0.01,
    )
    for k, dx in enumerate((-0.11, 0.0, 0.11)):
        cube(
            f"totem:bus_win:{k}",
            (x + dx, fy - 0.004, bz + 0.07),
            (0.07, 0.006, 0.07),
            MATS["sign_blue"],
            coll,
            bevel_width=0,
        )
    for dx in (-0.11, 0.11):
        cyl(
            f"totem:bus_wheel:{dx:.2f}",
            (x + dx, fy - 0.006, bz - 0.11),
            0.045,
            0.006,
            MATS["sign_blue"],
            coll,
            vertices=20,
            axis="Y",
        )
    # small route panel below the box
    cube(
        "totem:route",
        (x, y - 0.085, bz - 0.55),
        (0.5, 0.02, 0.42),
        MATS["sign_white"],
        coll,
        bevel_width=0.01,
    )
    for k in range(3):
        cube(
            f"totem:route_line:{k}",
            (x, y - 0.10, bz - 0.42 - k * 0.11),
            (0.4, 0.006, 0.03),
            MATS["timetable_line"],
            coll,
            bevel_width=0,
        )


# --------------------------------------------------------------------------- #
# Ground + context
# --------------------------------------------------------------------------- #
def ground(coll):
    # sidewalk the shelter sits on
    cube(
        "gnd:sidewalk",
        (0, 3.4, 0.02),
        (26, 7.2, 0.06),
        MATS["sidewalk"],
        coll,
        bevel_width=0,
    )
    # paver grid seams under the shelter
    for i in range(-6, 7):
        cube(
            f"gnd:seam_x:{i}",
            (i * 1.2, 2.0, 0.051),
            (0.02, 5.4, 0.006),
            MATS["paver"],
            coll,
            bevel_width=0,
        )
    # kerb
    cube(
        "gnd:curb",
        (0, -0.2, 0.12),
        (26, 0.28, 0.16),
        MATS["curb"],
        coll,
        bevel_width=0.015,
    )
    # tactile warning strip at the boarding edge
    for i in range(-9, 10):
        for j in range(3):
            cyl(
                f"gnd:tactile:{i}:{j}",
                (i * 0.28, -0.55 + j * 0.16, 0.055),
                0.028,
                0.02,
                MATS["tactile"],
                coll,
                vertices=10,
            )
    # road / bus lane
    cube(
        "gnd:road",
        (0, -4.6, -0.01),
        (26, 9.0, 0.05),
        MATS["asphalt"],
        coll,
        bevel_width=0,
    )
    # bus-lane box + "BUS" lettering blocks on the tarmac
    cube(
        "gnd:lane_edge",
        (0, -1.15, 0.008),
        (26, 0.16, 0.01),
        MATS["paint_white"],
        coll,
        bevel_width=0,
    )
    cube(
        "gnd:lane_box",
        (0, -2.6, 0.008),
        (7.5, 0.14, 0.01),
        MATS["paint_white"],
        coll,
        bevel_width=0,
    )
    cube(
        "gnd:lane_box2",
        (3.75, -3.6, 0.008),
        (0.14, 2.0, 0.01),
        MATS["paint_white"],
        coll,
        bevel_width=0,
    )
    cube(
        "gnd:lane_box3",
        (-3.75, -3.6, 0.008),
        (0.14, 2.0, 0.01),
        MATS["paint_white"],
        coll,
        bevel_width=0,
    )
    bus_word_marking(coll, cx=0.0, cy=-4.4)


def bus_word_marking(coll, cx, cy):
    """Chunky white 'BUS' painted on the tarmac (block glyphs)."""
    s = 0.9
    z = 0.009
    th = 0.14 * s

    def bar(nm, lx, ly, w, h):
        cube(
            nm,
            (cx + lx, cy + ly, z),
            (w, h, 0.01),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )

    # B
    bx = -1.7 * s
    bar("bus:B:v", bx, 0, th, 1.4 * s)
    for dy in (0.63 * s, 0.0, -0.63 * s):
        bar(f"bus:B:h{dy:.2f}", bx + 0.28 * s, dy, 0.5 * s, th)
    bar("bus:B:r1", bx + 0.5 * s, 0.32 * s, th, 0.55 * s)
    bar("bus:B:r2", bx + 0.5 * s, -0.32 * s, th, 0.55 * s)
    # U
    ux = 0.0
    bar("bus:U:l", ux - 0.3 * s, 0.1 * s, th, 1.2 * s)
    bar("bus:U:r", ux + 0.3 * s, 0.1 * s, th, 1.2 * s)
    bar("bus:U:b", ux, -0.63 * s, 0.6 * s + th, th)
    # S
    sx = 1.7 * s
    for dy in (0.63 * s, 0.0, -0.63 * s):
        bar(f"bus:S:h{dy:.2f}", sx, dy, 0.5 * s, th)
    bar("bus:S:t", sx - 0.28 * s, 0.32 * s, th, 0.55 * s)
    bar("bus:S:b", sx + 0.28 * s, -0.32 * s, th, 0.55 * s)


def context(coll):
    # building backdrop behind the sidewalk
    buildings = [
        ("a", -8.0, 8.4, 7.0, 5.0, 9.0, "brick"),
        ("b", -0.5, 8.8, 8.0, 5.5, 12.0, "brick"),
        ("c", 8.0, 8.4, 7.0, 5.0, 8.0, "brick"),
    ]
    for name, x, y, sx, sy, h, mat in buildings:
        cube(
            f"bld:{name}", (x, y, h / 2), (sx, sy, h), MATS[mat], coll, bevel_width=0.04
        )
        face_y = y - sy / 2 - 0.02
        for floor in range(2, int(h), 2):
            for k in (-2, -1, 1, 2):
                cube(
                    f"bld:{name}:win:{floor}:{k}",
                    (x + k * sx * 0.17, face_y, floor + 0.25),
                    (0.8, 0.03, 1.0),
                    MATS["window"],
                    coll,
                    bevel_width=0.008,
                )
    # a street lamp further along the kerb
    lx, ly = 6.6, 0.2
    cyl_between(
        "ctx:lamp_pole",
        (lx, ly, 0.0),
        (lx, ly, 4.6),
        0.06,
        MATS["pole"],
        coll,
        vertices=24,
    )
    cyl_between(
        "ctx:lamp_arm",
        (lx, ly, 4.5),
        (lx, ly - 1.1, 4.7),
        0.045,
        MATS["pole"],
        coll,
        vertices=16,
    )
    sphere(
        "ctx:lamp_glow",
        (lx, ly - 1.05, 4.66),
        (0.16, 0.16, 0.1),
        MATS["lamp_glow"],
        coll,
        segments=20,
    )
    # a couple of street trees for framing
    for i, (x, y) in enumerate([(-7.5, 1.4), (5.2, 5.5)]):
        cyl_between(
            f"tree:trunk:{i}",
            (x, y, 0.0),
            (x, y, 2.2),
            0.12,
            MATS["trunk"],
            coll,
            vertices=16,
        )
        for j in range(3):
            sphere(
                f"tree:crown:{i}:{j}",
                (x + (j - 1) * 0.5, y + 0.1 * j, 2.7 + 0.2 * j),
                (1.3, 1.3, 1.1),
                MATS["leaf"],
                coll,
                segments=20,
            )


# --------------------------------------------------------------------------- #
# World (Nishita physical sky) + camera + render
# --------------------------------------------------------------------------- #
def build_world():
    world = bpy.data.worlds.new("bs_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(34)  # bright mid-morning sun
    sky.sun_rotation = math.radians(-55)
    sky.sun_intensity = 1.0
    sky.altitude = 250
    sky.air_density = 1.05
    sky.dust_density = 0.5

    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_cam.inputs["Strength"].default_value = 1.0
    # keep a fairly bright environment: glass + brushed alu want strong IBL
    bg_light.inputs["Strength"].default_value = 0.45
    if os.environ.get("V3_DIAG"):
        bg_cam.inputs["Strength"].default_value = 0.1
        bg_light.inputs["Strength"].default_value = 0.1
    nt.links.new(sky.outputs["Color"], bg_cam.inputs["Color"])
    nt.links.new(sky.outputs["Color"], bg_light.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_light.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def add_sun():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "key_sun"
    sun.data.energy = 3.6
    sun.data.angle = math.radians(1.2)
    sun.data.color = (1.0, 0.95, 0.86)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-55))


def _focus_empty(name, loc):
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = loc
    return empty


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


def add_cameras():
    """Hero 3/4 still + orbit turntable, both aimed at the shelter interior."""
    target = Vector((0.2, 0.0, 1.25))
    focus = _focus_empty("cam_focus", target)

    # ---- hero still: low 3/4 from the road side looking into the shelter -
    still = bpy.data.cameras.new("cam_still")
    still_obj = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(still_obj)
    still.lens = 35
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 3.5
    still.dof.focus_object = focus
    cam_pos = Vector((-3.4, -5.2, 1.55))
    still_obj.location = cam_pos
    still_obj.rotation_euler = (target - cam_pos).to_track_quat("-Z", "Y").to_euler()

    # ---- orbit camera: sweep the road-side hemisphere -------------------- #
    orbit = bpy.data.cameras.new("cam_orbit")
    orbit_obj = bpy.data.objects.new("cam_orbit", orbit)
    bpy.context.scene.collection.objects.link(orbit_obj)
    orbit.lens = 32
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 4.0
    orbit.dof.focus_object = focus
    radius = 6.6
    height = 1.7
    for frame, deg in ((1, -62), (48, 0), (96, 62)):
        d = rot_z(Vector((0, -1, 0)), math.radians(deg))
        loc = target + d * radius + Vector((0, 0, height - target.z))
        orbit_obj.location = loc
        orbit_obj.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        orbit_obj.keyframe_insert(data_path="location", frame=frame)
        orbit_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    for fc in orbit_obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return still_obj, orbit_obj


def setup_compositor():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new("CompositorNodeRLayers")
    if os.environ.get("V3_DIAG"):
        comp = tree.nodes.new("CompositorNodeComposite")
        tree.links.new(rl.outputs["Image"], comp.inputs["Image"])
        return
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.0  # let the backlit ad + totem bloom gently
    glare.size = 6
    if hasattr(glare, "mix"):
        glare.mix = -0.6
    comp = tree.nodes.new("CompositorNodeComposite")
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
                for d in devs:
                    d.use = True
                chosen = backend
                break
        except Exception:
            continue
    print(f"[v3] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 16  # lots of glass
    scene.cycles.caustics_reflective = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = -0.7


def render_still(scene, cam):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = 420
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(STILL_PATH)
    print("[v3] rendering hero still ...")
    bpy.ops.render.render(write_still=True)


def render_video(scene, cam):
    scene.camera = cam
    scene.cycles.samples = 170
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
    print("[v3] rendering orbit video ...")
    bpy.ops.render.render(animation=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ctx = add_collection("v3_context")
    shelter = add_collection("v3_bus_shelter")
    ground(ctx)
    context(ctx)
    build_shelter(shelter)

    build_world()
    add_sun()
    still_cam, orbit_cam = add_cameras()
    configure_cycles()
    setup_compositor()

    scene = bpy.context.scene
    scene.camera = still_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    render_still(scene, still_cam)
    if os.environ.get("V3_STILL_ONLY"):
        print("[v3] still-only mode; skipping video")
        return
    render_video(scene, orbit_cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
