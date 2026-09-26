"""Photorealistic procedural traffic-light scene (urban_v3_trafficlight).

Upgrades over urban_v2_2:
  * Cycles + OPTIX GPU path tracing (was EEVEE) with OptiX denoising.
  * Nishita physical-sky world -> real image-based lighting & reflections
    on the metal housings and glass lenses (the single biggest realism win).
  * PBR materials: powder-coated aluminium housing with a coat layer,
    galvanised mast, retro-reflective backplate, and transmissive convex
    glass lens covers over emissive LED cores.
  * Camera with depth-of-field, AgX view transform, 1080p hero still +
    720p orbit turntable video.

Run:
  ${BLENDER_BIN} -b --python \
    scripts/generate_urban_v3_trafficlight.py

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trafficlight):
  traffic_light.blend  traffic_light.png  traffic_light.mp4
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trafficlight")
SCENE_PATH = OUTPUT_DIR / "traffic_light.blend"
STILL_PATH = OUTPUT_DIR / "traffic_light.png"
VIDEO_PATH = OUTPUT_DIR / "traffic_light.mp4"


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
    # Blender <4.1 exposed mesh.use_auto_smooth; 4.x drops it (smooth-by-angle
    # is a modifier now). Guard so the script runs on both.
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
    # Specular IOR Level (0.5 == IOR 1.5). Lower it to kill the bright dielectric
    # sky sheen on large flat matte panels (backplate / housing).
    _set(b, "Specular IOR Level", specular)
    # transmission / coat input names differ slightly across versions
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
            # --- roadway --------------------------------------------------- #
            "asphalt": pbr("v3_asphalt", (0.021, 0.021, 0.022), roughness=0.9),
            "sidewalk": pbr("v3_sidewalk", (0.28, 0.275, 0.26), roughness=0.85),
            "curb": pbr("v3_curb", (0.36, 0.35, 0.33), roughness=0.8),
            "paint_white": pbr("v3_paint_white", (0.62, 0.6, 0.55), roughness=0.55),
            "paint_yellow": pbr("v3_paint_yellow", (0.55, 0.36, 0.03), roughness=0.5),
            # --- structural metals ---------------------------------------- #
            # galvanised / painted mast + pole: bright brushed steel
            "mast": pbr(
                "v3_mast_galvanised",
                (0.32, 0.325, 0.33),
                roughness=0.46,
                metallic=1.0,
                anisotropy=0.3,
            ),
            # powder-coated dark aluminium signal housing: flat matte black so
            # it does not pick up a bright Fresnel sheen from the sky.
            "housing": pbr(
                "v3_housing_black",
                (0.014, 0.015, 0.015),
                roughness=0.55,
                metallic=0.0,
                coat=0.0,
                specular=0.18,
            ),
            "dark_metal": pbr(
                "v3_dark_metal",
                (0.02, 0.021, 0.021),
                roughness=0.38,
                metallic=0.9,
            ),
            # matte retro-reflective backplate + fluorescent yellow border
            "backplate": pbr(
                "v3_backplate", (0.006, 0.006, 0.006), roughness=0.7, specular=0.08
            ),
            "yellow_trim": pbr(
                "v3_yellow_trim", (0.85, 0.62, 0.02), roughness=0.35, coat=0.4
            ),
            "cabinet": pbr("v3_cabinet", (0.22, 0.30, 0.25), roughness=0.45, coat=0.3),
            # --- lens glass (convex transmissive covers) ------------------- #
            "glass_red": pbr(
                "v3_glass_red",
                (0.55, 0.015, 0.008),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            "glass_yellow": pbr(
                "v3_glass_yellow",
                (0.6, 0.32, 0.008),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            "glass_green": pbr(
                "v3_glass_green",
                (0.01, 0.5, 0.13),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            # --- emissive LED cores --------------------------------------- #
            "led_red_on": pbr(
                "v3_led_red_on",
                (1.0, 0.03, 0.02),
                emission=(1.0, 0.06, 0.03),
                emission_strength=13.0,
                roughness=0.4,
            ),
            "led_yellow_on": pbr(
                "v3_led_yellow_on",
                (1.0, 0.55, 0.02),
                emission=(1.0, 0.52, 0.04),
                emission_strength=13.0,
                roughness=0.4,
            ),
            "led_green_on": pbr(
                "v3_led_green_on",
                (0.02, 1.0, 0.2),
                emission=(0.08, 1.0, 0.32),
                emission_strength=16.0,
                roughness=0.4,
            ),
            # dim (off) LED core: near-black tinted glossy
            "led_red_off": pbr("v3_led_red_off", (0.06, 0.008, 0.006), roughness=0.3),
            "led_yellow_off": pbr(
                "v3_led_yellow_off", (0.07, 0.04, 0.006), roughness=0.3
            ),
            "led_green_off": pbr(
                "v3_led_green_off", (0.008, 0.07, 0.02), roughness=0.3
            ),
            # --- pedestrian signal glyphs --------------------------------- #
            "walk_on": pbr(
                "v3_walk_on",
                (0.9, 1.0, 0.85),
                emission=(0.85, 1.0, 0.8),
                emission_strength=13.0,
            ),
            "hand_off": pbr("v3_hand_off", (0.12, 0.03, 0.005), roughness=0.3),
            "count_on": pbr(
                "v3_count_on",
                (1.0, 0.35, 0.03),
                emission=(1.0, 0.3, 0.02),
                emission_strength=12.0,
            ),
            # --- context -------------------------------------------------- #
            "brick": pbr("v3_brick", (0.19, 0.16, 0.14), roughness=0.82),
            "window": pbr(
                "v3_window",
                (0.03, 0.05, 0.07),
                roughness=0.06,
                metallic=0.0,
                coat=0.6,
            ),
            "grass": pbr("v3_grass", (0.06, 0.16, 0.05), roughness=0.9),
            "leaf": pbr("v3_leaf", (0.03, 0.12, 0.04), roughness=0.8),
        }
    )


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _bevel(obj, width=0.015, segments=2):
    if width <= 0:
        return
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("wn", "WEIGHTED_NORMAL")


def cube(name, loc, dims, material, coll, yaw=0.0, bevel_width=0.015):
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


def sphere(name, loc, scale, material, coll, segments=48):
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


def cyl_between(name, start, end, radius, material, coll, vertices=48):
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


def basis(yaw):
    right = Vector((math.cos(yaw), math.sin(yaw), 0))
    front = Vector((-math.sin(yaw), math.cos(yaw), 0))
    up = Vector((0, 0, 1))
    return right, front, up


def local(center, yaw, x=0, y=0, z=0):
    right, front, up = basis(yaw)
    return Vector(center) + right * x + front * y + up * z


def local_box(name, center, yaw, offset, dims, material, coll, bevel_width=0.015):
    return cube(
        name,
        local(center, yaw, *offset),
        dims,
        material,
        coll,
        yaw=yaw,
        bevel_width=bevel_width,
    )


def disc(name, center, yaw, offset, radius, depth, material, coll, vertices=48):
    _, front, _ = basis(yaw)
    c = local(center, yaw, *offset)
    return cyl_between(
        name,
        c - front * (depth * 0.5),
        c + front * (depth * 0.5),
        radius,
        material,
        coll,
        vertices=vertices,
    )


def convex(name, center, yaw, offset, radius, bulge, material, coll):
    """A flattened UV-sphere used as a convex lens cover / LED core."""
    _, front, _ = basis(yaw)
    loc = local(center, yaw, *offset)
    obj = sphere(name, loc, (radius, radius, bulge), material, coll, segments=56)
    obj.rotation_euler = front.to_track_quat("Z", "Y").to_euler()
    return obj


def arc_visor(name, center, yaw, offset, radius, length, thickness, material, coll):
    """Tunnel-style deep-cutaway hood over a lens (half cylinder shell)."""
    right, front, up = basis(yaw)
    c = local(center, yaw, *offset)
    verts, faces = [], []
    steps = 22
    for d in (0.0, length):
        for r in (radius, radius + thickness):
            for i in range(steps + 1):
                theta = math.pi * i / steps
                pos = (
                    c
                    + front * d
                    + right * (math.cos(theta) * r)
                    + up * (math.sin(theta) * r)
                )
                verts.append(tuple(pos))
    ring = steps + 1
    for i in range(steps):
        a, bb = i, i + 1
        c1, dd = ring + i + 1, ring + i
        faces.append((a, bb, c1, dd))
        off = 2 * ring
        faces.append((off + a, off + dd, off + c1, off + bb))
        faces.append((a, off + a, off + bb, bb))
        faces.append((dd, c1, off + c1, off + dd))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    coll.objects.link(obj)
    obj.modifiers.new("wn", "WEIGHTED_NORMAL")
    smooth(obj)
    return obj


def add_bolts(prefix, center, yaw, width, height, depth, coll):
    for i, x in enumerate((-width / 2 + 0.09, width / 2 - 0.09)):
        for j, z in enumerate((-height / 2 + 0.09, height / 2 - 0.09)):
            disc(
                f"{prefix}:bolt:{i}:{j}",
                center,
                yaw,
                (x, depth / 2 + 0.012, z),
                0.022,
                0.016,
                MATS["dark_metal"],
                coll,
                vertices=12,
            )


# --------------------------------------------------------------------------- #
# Signal heads
# --------------------------------------------------------------------------- #
LENS_MATS = {
    "red": ("glass_red", "led_red_on", "led_red_off"),
    "yellow": ("glass_yellow", "led_yellow_on", "led_yellow_off"),
    "green": ("glass_green", "led_green_on", "led_green_off"),
}


def signal_head(
    prefix, center, yaw, layout, coll, orientation="vertical", active="red"
):
    count = len(layout)
    spacing = 0.60
    lens_r = 0.20
    depth = 0.36
    if orientation == "vertical":
        width = 0.80
        height = 0.36 + spacing * (count - 1) + 0.46
        positions = [
            (0.0, 0.0, (count - 1) * spacing / 2 - i * spacing) for i in range(count)
        ]
    else:
        width = 0.36 + spacing * (count - 1) + 0.62
        height = 0.80
        positions = [
            (-(count - 1) * spacing / 2 + i * spacing, 0.0, 0.0) for i in range(count)
        ]

    # retro-reflective backplate with fluorescent-yellow border
    local_box(
        f"{prefix}:backplate",
        center,
        yaw,
        (0, -0.04, 0),
        (width + 0.30, 0.05, height + 0.30),
        MATS["yellow_trim"],
        coll,
        bevel_width=0.02,
    )
    local_box(
        f"{prefix}:backplate_face",
        center,
        yaw,
        (0, -0.02, 0),
        (width + 0.12, 0.05, height + 0.12),
        MATS["backplate"],
        coll,
        bevel_width=0.01,
    )
    # weatherproof housing body
    local_box(
        f"{prefix}:housing",
        center,
        yaw,
        (0, 0, 0),
        (width, depth, height),
        MATS["housing"],
        coll,
        bevel_width=0.05,
    )
    add_bolts(prefix, center, yaw, width + 0.14, height + 0.14, depth, coll)

    for idx, item in enumerate(layout):
        kind = item
        x, y, z = positions[idx]
        is_on = kind == active
        glass, on_mat, off_mat = LENS_MATS[kind]
        # recessed dark reflector bucket
        disc(
            f"{prefix}:bucket:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 - 0.02, z),
            lens_r * 1.05,
            0.10,
            MATS["dark_metal"],
            coll,
            vertices=56,
        )
        # emissive LED core (bright if active, near-black if off)
        convex(
            f"{prefix}:led:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.02, z),
            lens_r * 0.92,
            0.045,
            MATS[on_mat if is_on else off_mat],
            coll,
        )
        # convex transmissive glass cover
        convex(
            f"{prefix}:glass:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.06, z),
            lens_r,
            0.06,
            MATS[glass],
            coll,
        )
        # deep tunnel visor
        arc_visor(
            f"{prefix}:visor:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.05, z),
            lens_r * 1.12,
            0.30,
            0.03,
            MATS["housing"],
            coll,
        )

    # rear terminal / wiring box
    local_box(
        f"{prefix}:terminal",
        center,
        yaw,
        (0, -depth / 2 - 0.06, -height / 2 + 0.12),
        (0.40, 0.14, 0.20),
        MATS["dark_metal"],
        coll,
        bevel_width=0.015,
    )
    return width, height


def pedestrian_head(prefix, center, yaw, coll):
    local_box(
        f"{prefix}:backplate",
        center,
        yaw,
        (0, -0.02, 0),
        (0.82, 0.05, 0.92),
        MATS["backplate"],
        coll,
        bevel_width=0.02,
    )
    local_box(
        f"{prefix}:case",
        center,
        yaw,
        (0, 0, 0),
        (0.66, 0.26, 0.78),
        MATS["housing"],
        coll,
        bevel_width=0.035,
    )
    # upper "walk" window (dim) + hand (off) — here show orange hand steady
    local_box(
        f"{prefix}:hand_window",
        center,
        yaw,
        (0, 0.14, 0.16),
        (0.5, 0.02, 0.3),
        MATS["hand_off"],
        coll,
        bevel_width=0.008,
    )
    local_box(
        f"{prefix}:count_window",
        center,
        yaw,
        (0, 0.14, -0.2),
        (0.44, 0.02, 0.22),
        MATS["count_on"],
        coll,
        bevel_width=0.008,
    )
    arc_visor(
        f"{prefix}:visor",
        center,
        yaw,
        (0, 0.13, 0.02),
        0.34,
        0.18,
        0.028,
        MATS["housing"],
        coll,
    )
    add_bolts(prefix, center, yaw, 0.76, 0.86, 0.26, coll)


# --------------------------------------------------------------------------- #
# Poles / structures
# --------------------------------------------------------------------------- #
_MAST_HEADS = {}


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


def mast_arm(prefix, pole_xy, yaw, coll, active="green"):
    x, y = pole_xy
    # tapered fluted base pole
    cyl_between(
        f"{prefix}:pole",
        (x, y, 0.05),
        (x, y, 5.0),
        0.12,
        MATS["mast"],
        coll,
        vertices=48,
    )
    cyl_between(
        f"{prefix}:pole_cap",
        (x, y, 5.0),
        (x, y, 5.12),
        0.13,
        MATS["mast"],
        coll,
        vertices=48,
    )
    # long horizontal mast arm
    arm_end = tuple(local((x, y, 4.85), yaw, 0, 5.0, 0))
    cyl_between(
        f"{prefix}:arm", (x, y, 4.85), arm_end, 0.08, MATS["mast"], coll, vertices=40
    )
    # diagonal support truss
    cyl_between(
        f"{prefix}:truss",
        (x, y, 5.05),
        tuple(local((x, y, 4.85), yaw, 0, 3.6, 0)),
        0.02,
        MATS["dark_metal"],
        coll,
        vertices=16,
    )
    # base plate + anchor bolts
    cube(
        f"{prefix}:base_plate",
        (x, y, 0.06),
        (0.6, 0.6, 0.09),
        MATS["dark_metal"],
        coll,
        bevel_width=0.02,
    )
    for i, dx in enumerate((-0.2, 0.2)):
        for j, dy in enumerate((-0.2, 0.2)):
            cyl_between(
                f"{prefix}:anchor:{i}:{j}",
                (x + dx, y + dy, 0.09),
                (x + dx, y + dy, 0.18),
                0.028,
                MATS["mast"],
                coll,
                vertices=12,
            )
    # main overhead 3-section head hanging from the arm
    head_center = tuple(local((x, y, 4.35), yaw, 0, 4.55, 0))
    signal_head(
        f"{prefix}:main_head",
        head_center,
        yaw,
        ["red", "yellow", "green"],
        coll,
        orientation="vertical",
        active=active,
    )
    _MAST_HEADS[prefix] = (Vector(head_center), yaw)
    cyl_between(
        f"{prefix}:hanger",
        tuple(local((x, y, 4.85), yaw, 0, 4.55, 0)),
        tuple(local(head_center, yaw, 0, -0.20, 0.66)),
        0.028,
        MATS["dark_metal"],
        coll,
        vertices=16,
    )
    # side-mounted head + pedestrian signal on the pole itself
    signal_head(
        f"{prefix}:side_head",
        tuple(local((x, y, 3.05), yaw, 0, 0.30, 0)),
        yaw,
        ["red", "yellow", "green"],
        coll,
        orientation="vertical",
        active=active,
    )
    pedestrian_head(
        f"{prefix}:ped", tuple(local((x, y, 2.15), yaw, 0, -0.33, 0)), yaw, coll
    )
    # push-button
    local_box(
        f"{prefix}:btn_box",
        (x, y, 1.15),
        yaw,
        (0.2, 0.12, 0),
        (0.2, 0.13, 0.32),
        MATS["cabinet"],
        coll,
        bevel_width=0.02,
    )
    disc(
        f"{prefix}:btn",
        (x, y, 1.15),
        yaw,
        (0.2, 0.19, 0.02),
        0.045,
        0.02,
        MATS["yellow_trim"],
        coll,
        vertices=24,
    )


def corner_pedestal(prefix, pole_xy, yaw, coll, active="red"):
    x, y = pole_xy
    cyl_between(
        f"{prefix}:pole",
        (x, y, 0.05),
        (x, y, 3.55),
        0.09,
        MATS["mast"],
        coll,
        vertices=40,
    )
    cube(
        f"{prefix}:base_plate",
        (x, y, 0.06),
        (0.45, 0.45, 0.08),
        MATS["dark_metal"],
        coll,
        bevel_width=0.02,
    )
    signal_head(
        f"{prefix}:head",
        tuple(local((x, y, 2.8), yaw, 0, 0.28, 0)),
        yaw,
        ["red", "yellow", "green"],
        coll,
        orientation="vertical",
        active=active,
    )
    pedestrian_head(
        f"{prefix}:ped", tuple(local((x, y, 1.95), yaw, 0, -0.31, 0)), yaw, coll
    )
    local_box(
        f"{prefix}:btn_box",
        (x, y, 1.12),
        yaw,
        (0.18, 0.11, 0),
        (0.2, 0.12, 0.32),
        MATS["cabinet"],
        coll,
        bevel_width=0.018,
    )
    disc(
        f"{prefix}:btn",
        (x, y, 1.12),
        yaw,
        (0.18, 0.18, 0.01),
        0.045,
        0.02,
        MATS["yellow_trim"],
        coll,
        vertices=20,
    )


def control_cabinet(coll):
    base = (6.2, -6.8, 0.6)
    cube(
        "controller:body",
        base,
        (0.8, 0.5, 1.1),
        MATS["cabinet"],
        coll,
        yaw=math.radians(14),
        bevel_width=0.025,
    )
    cube(
        "controller:door",
        (6.2, -7.05, 0.62),
        (0.56, 0.02, 0.86),
        MATS["dark_metal"],
        coll,
        yaw=math.radians(14),
        bevel_width=0.004,
    )
    cube(
        "controller:label",
        (6.05, -7.06, 0.95),
        (0.24, 0.012, 0.12),
        MATS["yellow_trim"],
        coll,
        yaw=math.radians(14),
        bevel_width=0.003,
    )


# --------------------------------------------------------------------------- #
# Road + context
# --------------------------------------------------------------------------- #
def road_scene(coll):
    cube(
        "road:ew", (0, 0, -0.02), (34, 7.4, 0.04), MATS["asphalt"], coll, bevel_width=0
    )
    cube(
        "road:ns", (0, 0, -0.018), (7.4, 34, 0.04), MATS["asphalt"], coll, bevel_width=0
    )
    for side, y in enumerate((-5.3, 5.3)):
        cube(
            f"sidewalk:ew:{side}",
            (0, y, 0.04),
            (34, 3.0, 0.1),
            MATS["sidewalk"],
            coll,
            bevel_width=0.02,
        )
    for side, x in enumerate((-5.3, 5.3)):
        cube(
            f"sidewalk:ns:{side}",
            (x, 0, 0.043),
            (3.0, 34, 0.1),
            MATS["sidewalk"],
            coll,
            bevel_width=0.02,
        )
    for i, y in enumerate((-3.8, 3.8)):
        cube(
            f"curb:ew:{i}",
            (0, y, 0.12),
            (34, 0.26, 0.15),
            MATS["curb"],
            coll,
            bevel_width=0.015,
        )
    for i, x in enumerate((-3.8, 3.8)):
        cube(
            f"curb:ns:{i}",
            (x, 0, 0.12),
            (0.26, 34, 0.15),
            MATS["curb"],
            coll,
            bevel_width=0.015,
        )
    # crosswalk zebra bars
    for i, x in enumerate([n * 0.8 for n in range(-4, 5)]):
        cube(
            f"cw:n:{i}",
            (x, 4.2, 0.02),
            (0.44, 2.2, 0.012),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )
        cube(
            f"cw:s:{i}",
            (x, -4.2, 0.02),
            (0.44, 2.2, 0.012),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )
    for i, y in enumerate([n * 0.8 for n in range(-4, 5)]):
        cube(
            f"cw:e:{i}",
            (4.2, y, 0.02),
            (2.2, 0.44, 0.012),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )
        cube(
            f"cw:w:{i}",
            (-4.2, y, 0.02),
            (2.2, 0.44, 0.012),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )
    # centre lane dashes
    for i, x in enumerate(range(-14, 15, 3)):
        if abs(x) < 4:
            continue
        cube(
            f"lane:ew:{i}",
            (x, 0, 0.021),
            (1.4, 0.1, 0.01),
            MATS["paint_yellow"],
            coll,
            bevel_width=0,
        )
        cube(
            f"lane:ns:{i}",
            (0, x, 0.022),
            (0.1, 1.4, 0.01),
            MATS["paint_yellow"],
            coll,
            bevel_width=0,
        )


def context(coll):
    buildings = [
        ("nw", -12.5, 11.0, 6.0, 5.5, 8.0),
        ("ne", 12.0, 11.0, 6.5, 5.5, 11.0),
        ("sw", -12.5, -11.0, 6.0, 5.0, 6.5),
        ("se", 12.5, -11.0, 5.5, 5.5, 9.0),
    ]
    for name, x, y, sx, sy, h in buildings:
        cube(
            f"bld:{name}",
            (x, y, h / 2),
            (sx, sy, h),
            MATS["brick"],
            coll,
            bevel_width=0.04,
        )
        face_y = y - math.copysign(sy / 2 + 0.02, y)
        for floor in range(2, int(h), 2):
            for k in (-2, -1, 1, 2):
                cube(
                    f"bld:{name}:win:{floor}:{k}",
                    (x + k * sx * 0.16, face_y, floor + 0.25),
                    (0.7, 0.03, 0.9),
                    MATS["window"],
                    coll,
                    bevel_width=0.008,
                )
    for i, (x, y) in enumerate([(-8.0, 7.5), (-7.5, -7.5), (8.0, -7.5), (7.5, 7.5)]):
        cube(
            f"grass:{i}",
            (x, y, 0.06),
            (2.0, 1.4, 0.05),
            MATS["grass"],
            coll,
            yaw=0.1 * i,
            bevel_width=0.04,
        )
        for j in range(9):
            a = j * math.tau / 9
            sphere(
                f"shrub:{i}:{j}",
                (x + math.cos(a) * 0.6, y + math.sin(a) * 0.4, 0.35),
                (0.2, 0.17, 0.19),
                MATS["leaf"],
                coll,
                segments=18,
            )


# --------------------------------------------------------------------------- #
# World (Nishita physical sky) + camera + render
# --------------------------------------------------------------------------- #
def build_world():
    """Nishita physical sky, but split via Light Path so the camera sees a
    bright blue sky while diffuse/glossy rays get a much dimmer version. The
    full-brightness sky would otherwise reflect off the large matte-black
    housing and read as pale beige, and bloom in the glare pass.
    """
    world = bpy.data.worlds.new("v3_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(28)  # warm low-ish afternoon sun
    sky.sun_rotation = math.radians(-40)
    sky.sun_intensity = 1.0
    sky.altitude = 300
    sky.air_density = 1.1
    sky.dust_density = 0.6  # light, clean city haze

    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")  # what the camera sees
    bg_light = nt.nodes.new("ShaderNodeBackground")  # what surfaces receive
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light.inputs["Strength"].default_value = 0.16
    if os.environ.get("V3_DIAG"):
        bg_cam.inputs["Strength"].default_value = 0.05
        bg_light.inputs["Strength"].default_value = 0.05
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
    sun.data.energy = 3.2
    sun.data.angle = math.radians(1.5)  # soft shadow edges
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-40))


def _focus_empty(name, loc):
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = loc
    return empty


def add_cameras(hero_head, hero_yaw):
    """Return (still_cam, orbit_cam). Both look at the hero overhead head.

    `front` is the direction the signal lenses face, so a camera placed on the
    +front side sees the lit lens faces.
    """
    _, front, up = basis(hero_yaw)
    focus = _focus_empty("cam_focus", hero_head)

    # ---- hero still camera: low 3/4 angle looking up at the lit face ----
    still = bpy.data.cameras.new("cam_still")
    still_obj = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(still_obj)
    still.lens = 50
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 2.5
    still.dof.focus_object = focus
    cam_pos = hero_head + rot_z(front, math.radians(24)) * 5.6 - up * 1.9
    still_obj.location = cam_pos
    still_obj.rotation_euler = (hero_head - cam_pos).to_track_quat("-Z", "Y").to_euler()

    # ---- orbit camera: sweep across the +front hemisphere (video) ----
    orbit = bpy.data.cameras.new("cam_orbit")
    orbit_obj = bpy.data.objects.new("cam_orbit", orbit)
    bpy.context.scene.collection.objects.link(orbit_obj)
    orbit.lens = 42
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 3.5
    orbit.dof.focus_object = focus
    radius = 6.6
    for frame, deg in ((1, -52), (48, 4), (96, 50)):
        d = rot_z(front, math.radians(deg))
        loc = hero_head + d * radius - up * 1.5
        orbit_obj.location = loc
        orbit_obj.rotation_euler = (hero_head - loc).to_track_quat("-Z", "Y").to_euler()
        orbit_obj.keyframe_insert(data_path="location", frame=frame)
        orbit_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    for fc in orbit_obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return still_obj, orbit_obj


def setup_compositor():
    """Fog-glow glare so the lit lenses bloom like real signals."""
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
    glare.threshold = 1.15  # only the truly bright lit lens blooms
    glare.size = 6
    if hasattr(glare, "mix"):
        glare.mix = -0.55  # subtle glow, keep the base image dominant
    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def configure_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    # enable OptiX on all available RTX cards
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
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 12
    scene.cycles.caustics_reflective = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    # AgX view transform (Blender 4.x) for filmic, photographic response
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = -1.3  # tame the bright Nishita sky


def render_still(scene, cam):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = 400
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(STILL_PATH)
    print("[v3] rendering hero still ...")
    bpy.ops.render.render(write_still=True)


def render_video(scene, cam):
    scene.camera = cam
    scene.cycles.samples = 160
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
    sig = add_collection("v3_traffic_signals")
    road_scene(ctx)
    context(ctx)

    # signals: NW mast arm is the hero (green), others complement the intersection
    mast_arm("tl:nw_mast", (-5.9, -6.1), math.radians(45), sig, active="green")
    mast_arm("tl:se_mast", (5.9, 6.1), math.radians(-135), sig, active="green")
    corner_pedestal("tl:ne", (5.9, -5.9), math.radians(135), sig, active="red")
    corner_pedestal("tl:sw", (-5.9, 5.9), math.radians(-45), sig, active="red")
    control_cabinet(sig)

    build_world()
    add_sun()
    hero_head, hero_yaw = _MAST_HEADS["tl:nw_mast"]
    still_cam, orbit_cam = add_cameras(hero_head, hero_yaw)
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
    # re-save with render settings intact
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v3] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
