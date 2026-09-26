"""Photorealistic procedural street-kiosk scene (urban_v3_kiosk).

infinigen ships NO kiosk / newsstand / vending-booth asset, so this builds a
small variety of them from scratch, using the same realism stack as
urban_v3_trafficlight / urban_v3_busstop:

  * Cycles + OPTIX GPU path tracing with OptiX denoising.
  * Nishita physical-sky world (split via Light Path) -> real image-based
    lighting + reflections in metal, glass and the awnings.
  * PBR materials + emissive backlit signage / menu boards / product walls.
  * DoF camera, AgX view transform, 1080p hero still + 720p dolly video.

Three kiosk types stand in a row on a kerbed sidewalk:
  A. Classic green PRESS newsstand  (magazines, papers, snacks, striped awning)
  B. Red/cream CAFE food kiosk       (serving window, backlit menu, coffee rig)
  C. Blue-glass drinks vending booth (illuminated product grid, ATM-style face)

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_kiosk.py

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk):
  kiosk.blend  kiosk.png  kiosk.mp4
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_kiosk")
SCENE_PATH = OUTPUT_DIR / "kiosk.blend"
STILL_PATH = OUTPUT_DIR / "kiosk.png"
VIDEO_PATH = OUTPUT_DIR / "kiosk.mp4"


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
            "asphalt": pbr("k_asphalt", (0.022, 0.022, 0.024), roughness=0.9),
            "sidewalk": pbr("k_sidewalk", (0.31, 0.305, 0.29), roughness=0.86),
            "paver": pbr("k_paver", (0.35, 0.345, 0.33), roughness=0.8),
            "curb": pbr("k_curb", (0.41, 0.40, 0.38), roughness=0.78),
            "paint_white": pbr("k_paint_white", (0.66, 0.64, 0.60), roughness=0.55),
            # --- structural ------------------------------------------------ #
            "steel": pbr(
                "k_steel",
                (0.52, 0.53, 0.55),
                roughness=0.34,
                metallic=1.0,
                anisotropy=0.3,
            ),
            "steel_dark": pbr(
                "k_steel_dark", (0.09, 0.095, 0.10), roughness=0.42, metallic=1.0
            ),
            "stainless": pbr(
                "k_stainless",
                (0.62, 0.63, 0.65),
                roughness=0.22,
                metallic=1.0,
                anisotropy=0.4,
            ),
            "chrome": pbr("k_chrome", (0.78, 0.79, 0.8), roughness=0.08, metallic=1.0),
            # --- kiosk body paints ----------------------------------------- #
            "green": pbr("k_green", (0.02, 0.13, 0.075), roughness=0.52, coat=0.1),
            "green_trim": pbr(
                "k_green_trim", (0.03, 0.20, 0.11), roughness=0.48, coat=0.1
            ),
            "red": pbr("k_red", (0.40, 0.03, 0.03), roughness=0.52, coat=0.1),
            "cream": pbr("k_cream", (0.80, 0.76, 0.66), roughness=0.6, coat=0.06),
            "blue": pbr("k_blue", (0.02, 0.09, 0.32), roughness=0.52, coat=0.1),
            "wood": pbr("k_wood", (0.24, 0.14, 0.07), roughness=0.55),
            "wood_light": pbr("k_wood_light", (0.44, 0.30, 0.16), roughness=0.55),
            "roof_metal": pbr(
                "k_roof_metal", (0.16, 0.17, 0.18), roughness=0.45, coat=0.3
            ),
            # --- glazing --------------------------------------------------- #
            "glass": pbr(
                "k_glass",
                (0.6, 0.7, 0.72),
                roughness=0.04,
                transmission=0.96,
                ior=1.5,
                alpha=0.25,
            ),
            "counter": pbr(
                "k_counter", (0.14, 0.14, 0.15), roughness=0.3, metallic=0.6
            ),
            # --- awning stripes -------------------------------------------- #
            "awn_green": pbr("k_awn_green", (0.03, 0.24, 0.12), roughness=0.6),
            "awn_cream": pbr("k_awn_cream", (0.86, 0.82, 0.72), roughness=0.6),
            "awn_red": pbr("k_awn_red", (0.45, 0.04, 0.04), roughness=0.6),
            # --- emissive signage / menus / product walls ------------------ #
            "sign_press": pbr(
                "k_sign_press",
                (0.9, 0.85, 0.2),
                emission=(1.0, 0.9, 0.2),
                emission_strength=5.5,
            ),
            "sign_cafe": pbr(
                "k_sign_cafe",
                (0.95, 0.3, 0.15),
                emission=(1.0, 0.32, 0.15),
                emission_strength=5.5,
            ),
            "sign_white": pbr(
                "k_sign_white",
                (0.95, 0.96, 0.98),
                emission=(0.96, 0.97, 0.99),
                emission_strength=5.5,
            ),
            "menu_board": pbr(
                "k_menu",
                (0.05, 0.05, 0.06),
                emission=(0.10, 0.11, 0.12),
                emission_strength=1.6,
            ),
            "menu_text": pbr(
                "k_menu_text",
                (0.95, 0.9, 0.6),
                emission=(1.0, 0.92, 0.6),
                emission_strength=2.4,
            ),
            "vend_glow": pbr(
                "k_vend_glow",
                (0.9, 0.95, 1.0),
                emission=(0.9, 0.96, 1.0),
                emission_strength=1.7,
            ),
            "interior_glow": pbr(
                "k_interior",
                (1.0, 0.93, 0.8),
                emission=(1.0, 0.93, 0.8),
                emission_strength=3.0,
            ),
            # --- products -------------------------------------------------- #
            "mag_a": pbr("k_mag_a", (0.75, 0.10, 0.12), roughness=0.4),
            "mag_b": pbr("k_mag_b", (0.10, 0.35, 0.65), roughness=0.4),
            "mag_c": pbr("k_mag_c", (0.90, 0.62, 0.08), roughness=0.4),
            "mag_d": pbr("k_mag_d", (0.15, 0.55, 0.28), roughness=0.4),
            "mag_e": pbr("k_mag_e", (0.55, 0.15, 0.55), roughness=0.4),
            "mag_f": pbr("k_mag_f", (0.92, 0.92, 0.9), roughness=0.4),
            "bottle_green": pbr(
                "k_bottle_green",
                (0.05, 0.30, 0.10),
                roughness=0.12,
                transmission=0.85,
                ior=1.46,
                alpha=0.5,
            ),
            "bottle_amber": pbr(
                "k_bottle_amber",
                (0.45, 0.22, 0.03),
                roughness=0.12,
                transmission=0.85,
                ior=1.46,
                alpha=0.5,
            ),
            "can_red": pbr(
                "k_can_red", (0.6, 0.05, 0.05), roughness=0.25, metallic=0.8
            ),
            "can_blue": pbr(
                "k_can_blue", (0.05, 0.2, 0.6), roughness=0.25, metallic=0.8
            ),
            "cup": pbr("k_cup", (0.88, 0.85, 0.8), roughness=0.5),
            "coffee_machine": pbr(
                "k_coffee", (0.12, 0.12, 0.13), roughness=0.3, metallic=0.7
            ),
            # --- context --------------------------------------------------- #
            "brick": pbr("k_brick", (0.30, 0.24, 0.20), roughness=0.82),
            "window": pbr("k_window", (0.05, 0.07, 0.09), roughness=0.06, coat=0.6),
            "pole": pbr("k_pole", (0.30, 0.31, 0.32), roughness=0.4, metallic=1.0),
            "lamp_glow": pbr(
                "k_lamp_glow",
                (1.0, 0.9, 0.7),
                emission=(1.0, 0.9, 0.7),
                emission_strength=5.0,
            ),
            "leaf": pbr("k_leaf", (0.03, 0.13, 0.04), roughness=0.8),
            "trunk": pbr("k_trunk", (0.10, 0.07, 0.05), roughness=0.85),
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


def cube(name, loc, dims, material, coll, yaw=0.0, pitch=0.0, bevel_width=0.012):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler = (pitch, 0.0, yaw)
    if material:
        obj.data.materials.append(material)
    _bevel(obj, bevel_width)
    return link_to(obj, coll)


def sphere(name, loc, scale, material, coll, segments=32):
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


def cyl_between(name, start, end, radius, material, coll, vertices=32):
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


def cyl(name, loc, radius, depth, material, coll, vertices=32, axis="Z"):
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
# Shared kiosk sub-assemblies
# --------------------------------------------------------------------------- #
MAG_MATS = ["mag_a", "mag_b", "mag_c", "mag_d", "mag_e", "mag_f"]


def striped_awning(prefix, cx, front_y, top_z, width, depth, coll, mats, drop=0.34):
    """A sloped striped fabric awning projecting from the shopfront (-Y)."""
    pitch = math.radians(20)
    n = 10
    sw = width / n
    cz = top_z - 0.02
    cy = front_y - depth / 2
    for i in range(n):
        x = cx - width / 2 + sw * (i + 0.5)
        mat = MATS[mats[i % len(mats)]]
        cube(
            f"{prefix}:awn:{i}",
            (x, cy, cz - 0.06),
            (sw + 0.004, depth, 0.05),
            mat,
            coll,
            pitch=pitch,
            bevel_width=0,
        )
    # scalloped valance hanging off the front edge
    fy = front_y - depth + 0.02
    fz = top_z - depth * math.sin(pitch) - 0.02
    for i in range(n):
        x = cx - width / 2 + sw * (i + 0.5)
        mat = MATS[mats[i % len(mats)]]
        cube(
            f"{prefix}:val:{i}",
            (x, fy, fz - drop / 2),
            (sw + 0.004, 0.02, drop),
            mat,
            coll,
            bevel_width=0,
        )
    # front support bar
    cyl_between(
        f"{prefix}:awn_bar",
        (cx - width / 2, fy, fz),
        (cx + width / 2, fy, fz),
        0.02,
        MATS["steel_dark"],
        coll,
        vertices=12,
    )


def magazine_wall(prefix, cx, cy, base_z, width, coll, rows=3, cols=7, face="-Y"):
    """A grid of colourful magazine/newspaper covers on a slanted rack."""
    cw = width / cols
    for r in range(rows):
        z = base_z + r * 0.30
        for c in range(cols):
            x = cx - width / 2 + cw * (c + 0.5)
            mat = MATS[MAG_MATS[(r * cols + c) % len(MAG_MATS)]]
            if face == "-Y":
                cube(
                    f"{prefix}:mag:{r}:{c}",
                    (x, cy, z),
                    (cw - 0.02, 0.03, 0.27),
                    mat,
                    coll,
                    pitch=math.radians(-12),
                    bevel_width=0.004,
                )
            else:  # +X side rack
                cube(
                    f"{prefix}:mag:{r}:{c}",
                    (cy, x, z),
                    (0.03, cw - 0.02, 0.27),
                    mat,
                    coll,
                    bevel_width=0.004,
                )


def bottle_shelf(prefix, cx, cy, z, width, coll, n=8):
    cw = width / n
    kinds = ["bottle_green", "bottle_amber", "can_red", "can_blue"]
    for i in range(n):
        x = cx - width / 2 + cw * (i + 0.5)
        k = kinds[i % len(kinds)]
        if k.startswith("bottle"):
            cyl(
                f"{prefix}:btl:{i}",
                (x, cy, z + 0.12),
                0.032,
                0.24,
                MATS[k],
                coll,
                vertices=16,
            )
            cyl(
                f"{prefix}:btlneck:{i}",
                (x, cy, z + 0.27),
                0.014,
                0.06,
                MATS[k],
                coll,
                vertices=12,
            )
        else:
            cyl(
                f"{prefix}:can:{i}",
                (x, cy, z + 0.06),
                0.033,
                0.12,
                MATS[k],
                coll,
                vertices=16,
            )


# --------------------------------------------------------------------------- #
# Kiosk A — classic PRESS newsstand (green)
# --------------------------------------------------------------------------- #
def kiosk_newsstand(coll, cx):
    body = MATS["green"]
    w, d, h = 2.4, 1.7, 2.35
    fy = -d / 2
    # plinth + body cabinet
    cube(
        "A:plinth",
        (cx, 0, 0.09),
        (w + 0.1, d + 0.1, 0.18),
        MATS["steel_dark"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "A:body",
        (cx, 0.05, h / 2 + 0.15),
        (w, d - 0.1, h),
        body,
        coll,
        bevel_width=0.03,
    )
    # green trim frame around the front opening
    cube(
        "A:frame",
        (cx, fy + 0.06, 1.55),
        (w - 0.05, 0.08, 1.5),
        MATS["green_trim"],
        coll,
        bevel_width=0.02,
    )
    # dark recessed interior + emissive interior glow
    cube(
        "A:interior",
        (cx, 0.15, 1.5),
        (w - 0.4, d - 0.5, 1.35),
        MATS["steel_dark"],
        coll,
        bevel_width=0,
    )
    cube(
        "A:int_glow",
        (cx, 0.55, 2.15),
        (w - 0.6, 0.04, 0.12),
        MATS["interior_glow"],
        coll,
        bevel_width=0,
    )
    # service counter shelf across the open front
    cube(
        "A:counter",
        (cx, fy + 0.16, 1.02),
        (w - 0.1, 0.5, 0.08),
        MATS["wood"],
        coll,
        bevel_width=0.015,
    )
    # product walls: magazines across the back, papers stacked on counter
    magazine_wall("A", cx, 0.42, 1.28, w - 0.5, coll, rows=3, cols=7, face="-Y")
    for i, dx in enumerate((-0.7, -0.2, 0.3, 0.8)):
        stack_mat = MATS[MAG_MATS[i % len(MAG_MATS)]]
        cube(
            f"A:paper:{i}",
            (cx + dx, fy + 0.16, 1.10),
            (0.34, 0.42, 0.10),
            stack_mat,
            coll,
            bevel_width=0.004,
        )
    # snack clips hanging at the side + a drinks shelf
    bottle_shelf("A", cx, fy + 0.12, 0.62, w - 0.6, coll, n=8)
    # side magazine rack on +X face
    magazine_wall(
        "A_side",
        cx + w / 2 + 0.03,
        -0.15,
        1.15,
        d - 0.5,
        coll,
        rows=3,
        cols=4,
        face="+X",
    )
    # roof + top signage box "PRESS"
    cube(
        "A:roof",
        (cx, 0.05, h + 0.2),
        (w + 0.18, d + 0.05, 0.14),
        MATS["roof_metal"],
        coll,
        bevel_width=0.03,
    )
    cube(
        "A:signbox",
        (cx, fy + 0.02, h + 0.42),
        (w - 0.2, 0.12, 0.34),
        MATS["green_trim"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "A:sign",
        (cx, fy - 0.05, h + 0.42),
        (w - 0.5, 0.03, 0.22),
        MATS["sign_press"],
        coll,
        bevel_width=0.006,
    )
    # letter slots on the sign (dark bars reading as PRESS)
    for i in range(5):
        cube(
            f"A:letter:{i}",
            (cx - 0.7 + i * 0.35, fy - 0.07, h + 0.42),
            (0.12, 0.02, 0.14),
            MATS["steel_dark"],
            coll,
            bevel_width=0,
        )
    # striped awning
    striped_awning(
        "A", cx, fy, h + 0.05, w + 0.1, 0.95, coll, ["awn_green", "awn_cream"]
    )


# --------------------------------------------------------------------------- #
# Kiosk B — CAFE food kiosk (red/cream, serving window + backlit menu)
# --------------------------------------------------------------------------- #
def kiosk_cafe(coll, cx):
    w, d, h = 2.6, 1.8, 2.4
    fy = -d / 2
    cube(
        "B:plinth",
        (cx, 0, 0.09),
        (w + 0.1, d + 0.1, 0.18),
        MATS["steel_dark"],
        coll,
        bevel_width=0.02,
    )
    # cream lower body + red upper band
    cube(
        "B:body",
        (cx, 0.05, 1.15 + 0.18),
        (w, d - 0.1, 2.0),
        MATS["cream"],
        coll,
        bevel_width=0.03,
    )
    cube(
        "B:band",
        (cx, 0.05, h + 0.05),
        (w + 0.04, d - 0.06, 0.5),
        MATS["red"],
        coll,
        bevel_width=0.03,
    )
    # wood-clad serving counter jutting out the front
    cube(
        "B:counter",
        (cx, fy - 0.12, 1.05),
        (w - 0.1, 0.55, 0.12),
        MATS["wood_light"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "B:counter_front",
        (cx, fy - 0.36, 0.6),
        (w - 0.1, 0.06, 0.9),
        MATS["wood"],
        coll,
        bevel_width=0.015,
    )
    # large serving window opening (dark interior) + rolled-up shutter
    cube(
        "B:window_recess",
        (cx, 0.28, 1.75),
        (w - 0.4, 0.06, 0.9),
        MATS["steel_dark"],
        coll,
        bevel_width=0,
    )
    cube(
        "B:int_glow",
        (cx, 0.34, 2.05),
        (w - 0.6, 0.03, 0.10),
        MATS["interior_glow"],
        coll,
        bevel_width=0,
    )
    cube(
        "B:shutter_roll",
        (cx, fy + 0.16, 2.28),
        (w - 0.2, 0.18, 0.18),
        MATS["stainless"],
        coll,
        bevel_width=0.02,
    )
    # backlit menu board above the window
    cube(
        "B:menu",
        (cx, fy + 0.02, 2.02),
        (w - 0.5, 0.05, 0.44),
        MATS["menu_board"],
        coll,
        bevel_width=0.01,
    )
    for r in range(3):
        for c in range(2):
            cube(
                f"B:menu_line:{r}:{c}",
                (cx - 0.5 + c * 0.9, fy - 0.01, 2.14 - r * 0.11),
                (0.7, 0.01, 0.03),
                MATS["menu_text"],
                coll,
                bevel_width=0,
            )
    # coffee machine + cups + display case on the counter
    cube(
        "B:coffee",
        (cx - 0.7, 0.1, 1.35),
        (0.5, 0.42, 0.5),
        MATS["coffee_machine"],
        coll,
        bevel_width=0.02,
    )
    cyl(
        "B:grinder",
        (cx - 0.35, 0.1, 1.35),
        0.09,
        0.34,
        MATS["stainless"],
        coll,
        vertices=20,
    )
    for i, dx in enumerate((0.2, 0.32, 0.44)):
        cyl(
            f"B:cup:{i}",
            (cx + dx, fy + 0.02, 1.16),
            0.03,
            0.09,
            MATS["cup"],
            coll,
            vertices=14,
        )
    cube(
        "B:display",
        (cx + 0.75, fy - 0.02, 1.22),
        (0.7, 0.4, 0.24),
        MATS["glass"],
        coll,
        bevel_width=0.01,
    )
    for i in range(4):
        cube(
            f"B:pastry:{i}",
            (cx + 0.55 + i * 0.13, fy - 0.02, 1.12),
            (0.08, 0.24, 0.05),
            MATS["mag_c"],
            coll,
            bevel_width=0.01,
        )
    # roof + illuminated CAFE sign
    cube(
        "B:roof",
        (cx, 0.05, h + 0.35),
        (w + 0.2, d + 0.06, 0.14),
        MATS["roof_metal"],
        coll,
        bevel_width=0.03,
    )
    cube(
        "B:signbox",
        (cx, fy + 0.0, h + 0.28),
        (1.5, 0.14, 0.4),
        MATS["red"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "B:sign",
        (cx, fy - 0.09, h + 0.28),
        (1.2, 0.03, 0.26),
        MATS["sign_cafe"],
        coll,
        bevel_width=0.006,
    )
    # cup icon on the sign
    cyl(
        "B:cupicon",
        (cx, fy - 0.12, h + 0.28),
        0.10,
        0.02,
        MATS["sign_white"],
        coll,
        vertices=24,
        axis="Y",
    )
    # striped awning
    striped_awning("B", cx, fy, h - 0.05, w + 0.1, 1.0, coll, ["awn_red", "awn_cream"])


# --------------------------------------------------------------------------- #
# Kiosk C — blue-glass drinks vending / ticket booth
# --------------------------------------------------------------------------- #
def kiosk_vending(coll, cx):
    w, d, h = 2.0, 1.6, 2.3
    fy = -d / 2
    cube(
        "C:plinth",
        (cx, 0, 0.09),
        (w + 0.1, d + 0.1, 0.18),
        MATS["steel_dark"],
        coll,
        bevel_width=0.02,
    )
    cube(
        "C:body",
        (cx, 0.05, h / 2 + 0.15),
        (w, d - 0.1, h),
        MATS["blue"],
        coll,
        bevel_width=0.03,
    )
    # big illuminated glass product face on the front
    cube(
        "C:facelight",
        (cx, fy + 0.10, 1.45),
        (w - 0.35, 0.04, 1.7),
        MATS["vend_glow"],
        coll,
        bevel_width=0,
    )
    # product grid behind glass: rows of cans/bottles as bright chips
    cols, rows = 5, 4
    gw = w - 0.6
    cwd = gw / cols
    kinds = ["can_red", "can_blue", "bottle_green", "mag_c", "mag_b", "mag_a"]
    for r in range(rows):
        for c in range(cols):
            x = cx - gw / 2 + cwd * (c + 0.5)
            z = 0.85 + r * 0.34
            cube(
                f"C:prod:{r}:{c}",
                (x, fy + 0.14, z),
                (cwd - 0.05, 0.05, 0.24),
                MATS[kinds[(r * cols + c) % len(kinds)]],
                coll,
                bevel_width=0.006,
            )
    # glass front cover
    cube(
        "C:glass",
        (cx, fy + 0.02, 1.45),
        (w - 0.28, 0.03, 1.75),
        MATS["glass"],
        coll,
        bevel_width=0.006,
    )
    cube(
        "C:frame",
        (cx, fy + 0.04, 1.45),
        (w - 0.22, 0.06, 1.82),
        MATS["stainless"],
        coll,
        bevel_width=0.02,
    )
    # payment/selection panel on the right
    cube(
        "C:panel",
        (cx + w / 2 - 0.16, fy + 0.06, 1.1),
        (0.22, 0.06, 0.6),
        MATS["steel_dark"],
        coll,
        bevel_width=0.015,
    )
    for i in range(3):
        cube(
            f"C:button:{i}",
            (cx + w / 2 - 0.16, fy - 0.0, 1.25 - i * 0.14),
            (0.09, 0.02, 0.06),
            MATS["sign_white"],
            coll,
            bevel_width=0.004,
        )
    # dispensing tray
    cube(
        "C:tray",
        (cx, fy + 0.02, 0.5),
        (w - 0.5, 0.16, 0.16),
        MATS["steel_dark"],
        coll,
        bevel_width=0.02,
    )
    # roof + top light bar sign
    cube(
        "C:roof",
        (cx, 0.05, h + 0.2),
        (w + 0.16, d + 0.05, 0.14),
        MATS["roof_metal"],
        coll,
        bevel_width=0.03,
    )
    cube(
        "C:signbar",
        (cx, fy - 0.02, h + 0.34),
        (w - 0.15, 0.1, 0.26),
        MATS["sign_white"],
        coll,
        bevel_width=0.02,
    )


# --------------------------------------------------------------------------- #
# Ground + context
# --------------------------------------------------------------------------- #
def ground(coll):
    cube(
        "gnd:sidewalk",
        (0, 3.2, 0.02),
        (34, 7.6, 0.06),
        MATS["sidewalk"],
        coll,
        bevel_width=0,
    )
    for i in range(-14, 15):
        cube(
            f"gnd:seam_x:{i}",
            (i * 1.2, 2.0, 0.051),
            (0.02, 6.0, 0.006),
            MATS["paver"],
            coll,
            bevel_width=0,
        )
    for j in range(6):
        cube(
            f"gnd:seam_y:{j}",
            (0, -0.6 + j * 1.2, 0.051),
            (34, 0.02, 0.006),
            MATS["paver"],
            coll,
            bevel_width=0,
        )
    cube(
        "gnd:curb",
        (0, -1.05, 0.12),
        (34, 0.28, 0.16),
        MATS["curb"],
        coll,
        bevel_width=0.015,
    )
    cube(
        "gnd:road",
        (0, -5.6, -0.01),
        (34, 9.0, 0.05),
        MATS["asphalt"],
        coll,
        bevel_width=0,
    )
    for i in range(-16, 17, 4):
        cube(
            f"gnd:lane:{i}",
            (i, -3.0, 0.008),
            (1.6, 0.12, 0.01),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )


def context(coll):
    buildings = [
        ("a", -11.0, 8.8, 8.5, 5.5, 11.0),
        ("b", -1.0, 9.2, 9.0, 6.0, 14.0),
        ("c", 10.0, 8.8, 8.5, 5.5, 10.0),
    ]
    for name, x, y, sx, sy, ht in buildings:
        cube(
            f"bld:{name}",
            (x, y, ht / 2),
            (sx, sy, ht),
            MATS["brick"],
            coll,
            bevel_width=0.05,
        )
        face_y = y - sy / 2 - 0.02
        for floor in range(2, int(ht), 2):
            for k in (-2, -1, 1, 2):
                cube(
                    f"bld:{name}:win:{floor}:{k}",
                    (x + k * sx * 0.17, face_y, floor + 0.3),
                    (0.9, 0.03, 1.1),
                    MATS["window"],
                    coll,
                    bevel_width=0.008,
                )
    # street lamps flanking the row
    for i, (lx, ly) in enumerate([(-8.5, -0.4), (8.5, -0.4)]):
        cyl_between(
            f"ctx:lamp_pole:{i}",
            (lx, ly, 0.0),
            (lx, ly, 4.8),
            0.06,
            MATS["pole"],
            coll,
            vertices=20,
        )
        cyl_between(
            f"ctx:lamp_arm:{i}",
            (lx, ly, 4.7),
            (lx, ly - 1.1, 4.9),
            0.045,
            MATS["pole"],
            coll,
            vertices=14,
        )
        sphere(
            f"ctx:lamp_glow:{i}",
            (lx, ly - 1.05, 4.86),
            (0.16, 0.16, 0.1),
            MATS["lamp_glow"],
            coll,
            segments=18,
        )
    # framing trees
    for i, (x, y) in enumerate([(-6.2, 1.6), (6.4, 1.6)]):
        cyl_between(
            f"tree:trunk:{i}",
            (x, y, 0.0),
            (x, y, 2.4),
            0.13,
            MATS["trunk"],
            coll,
            vertices=14,
        )
        for j in range(3):
            sphere(
                f"tree:crown:{i}:{j}",
                (x + (j - 1) * 0.5, y + 0.1 * j, 3.0 + 0.2 * j),
                (1.4, 1.4, 1.2),
                MATS["leaf"],
                coll,
                segments=18,
            )


# --------------------------------------------------------------------------- #
# World + camera + render
# --------------------------------------------------------------------------- #
def build_world():
    world = bpy.data.worlds.new("k_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(36)
    sky.sun_rotation = math.radians(-58)
    sky.sun_intensity = 1.0
    sky.altitude = 250
    sky.air_density = 1.05
    sky.dust_density = 0.5

    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light.inputs["Strength"].default_value = 0.5
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
    sun.rotation_euler = (math.radians(50), 0, math.radians(-58))


def _focus_empty(name, loc):
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = loc
    return empty


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


def add_cameras():
    """Hero 3/4 of the row + a dolly that travels along the shopfronts."""
    target = Vector((-0.3, 0.0, 1.6))
    focus = _focus_empty("cam_focus", target)

    still = bpy.data.cameras.new("cam_still")
    still_obj = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(still_obj)
    still.lens = 36
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 4.5
    still.dof.focus_object = focus
    cam_pos = Vector((-9.8, -9.4, 2.5))
    still_obj.location = cam_pos
    still_obj.rotation_euler = (target - cam_pos).to_track_quat("-Z", "Y").to_euler()

    # dolly: slide across the front from left to right, gently arcing in
    orbit = bpy.data.cameras.new("cam_dolly")
    orbit_obj = bpy.data.objects.new("cam_dolly", orbit)
    bpy.context.scene.collection.objects.link(orbit_obj)
    orbit.lens = 30
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 5.0
    orbit.dof.focus_object = focus
    keys = [
        (1, Vector((-8.5, -6.2, 1.85)), Vector((-5.0, -0.2, 1.4))),
        (48, Vector((0.0, -7.0, 2.0)), Vector((0.0, -0.2, 1.5))),
        (96, Vector((8.5, -6.2, 1.85)), Vector((5.0, -0.2, 1.4))),
    ]
    for frame, loc, look in keys:
        orbit_obj.location = loc
        orbit_obj.rotation_euler = (look - loc).to_track_quat("-Z", "Y").to_euler()
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
    glare.threshold = 1.0
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
    scene.cycles.transmission_bounces = 16
    scene.cycles.caustics_reflective = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = -0.8


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
    print("[v3] rendering dolly video ...")
    bpy.ops.render.render(animation=True)


# --------------------------------------------------------------------------- #
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()

    ctx = add_collection("v3_context")
    kiosks = add_collection("v3_kiosks")
    ground(ctx)
    context(ctx)

    kiosk_newsstand(kiosks, -4.7)
    kiosk_cafe(kiosks, 0.0)
    kiosk_vending(kiosks, 4.6)

    build_world()
    add_sun()
    still_cam, dolly_cam = add_cameras()
    configure_cycles()
    setup_compositor()

    scene = bpy.context.scene
    scene.camera = still_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    render_still(scene, still_cam)
    if os.environ.get("V3_STILL_ONLY"):
        print("[v3] still-only mode; skipping video")
        return
    render_video(scene, dolly_cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
