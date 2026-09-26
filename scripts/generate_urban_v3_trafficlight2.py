"""Two photorealistic procedural traffic lights (urban_v3_trafficlight2).

Deliverables show the FULL body of two distinct signal types, side by side on
an asphalt pad, with a camera that orbits to reveal each one completely:

  * UPRIGHT   - a straight pedestal pole with a side-bracket vertical 3-section
                head + pedestrian head + push button (red showing).
  * MAST-ARM  - a tall pole with a long tapered horizontal arm, two hanging
                vertical heads, a pole-mounted head, a green street-name blade
                sign, and a diagonal support truss (green showing).

Rendering reuses the tuned v3 recipe: Cycles + OPTIX GPU, Nishita sky split via
a Light Path node (camera vs. lighting) so the matte-black housings stay dark,
fog-glow glare on the lit lens, AgX at -1.3 EV.

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_trafficlight2.py
  (V3_STILL_ONLY=1 -> skip the video for fast iteration)

Outputs (${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trafficlight2):
  traffic_lights.blend  traffic_lights.png  traffic_lights.mp4
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trafficlight2")
SCENE_PATH = OUTPUT_DIR / "traffic_lights.blend"
STILL_PATH = OUTPUT_DIR / "traffic_lights.png"
VIDEO_PATH = OUTPUT_DIR / "traffic_lights.mp4"


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
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_to(obj, coll):
    coll.objects.link(obj)
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
# Materials
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
            # structure
            "galv": pbr(
                "v32_galv",
                (0.32, 0.325, 0.33),
                roughness=0.46,
                metallic=1.0,
                anisotropy=0.3,
            ),
            "pole_black": pbr(
                "v32_pole_black",
                (0.016, 0.017, 0.017),
                roughness=0.4,
                metallic=0.6,
                specular=0.3,
            ),
            "pole_green": pbr(
                "v32_pole_green",
                (0.02, 0.055, 0.035),
                roughness=0.42,
                metallic=0.5,
                specular=0.3,
            ),
            "housing": pbr(
                "v32_housing",
                (0.014, 0.015, 0.015),
                roughness=0.55,
                metallic=0.0,
                coat=0.0,
                specular=0.18,
            ),
            "dark_metal": pbr(
                "v32_dark_metal", (0.02, 0.021, 0.021), roughness=0.38, metallic=0.9
            ),
            "backplate": pbr(
                "v32_backplate", (0.006, 0.006, 0.006), roughness=0.7, specular=0.08
            ),
            "yellow_trim": pbr(
                "v32_yellow_trim", (0.85, 0.62, 0.02), roughness=0.35, coat=0.4
            ),
            "cabinet": pbr("v32_cabinet", (0.22, 0.30, 0.25), roughness=0.45, coat=0.3),
            "concrete": pbr("v32_concrete", (0.34, 0.33, 0.31), roughness=0.9),
            "asphalt": pbr("v32_asphalt", (0.021, 0.021, 0.022), roughness=0.9),
            "sign_green": pbr(
                "v32_sign_green", (0.02, 0.14, 0.05), roughness=0.4, specular=0.25
            ),
            "sign_white": pbr("v32_sign_white", (0.75, 0.76, 0.74), roughness=0.4),
            # lens glass
            "glass_red": pbr(
                "v32_glass_red",
                (0.55, 0.015, 0.008),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            "glass_yellow": pbr(
                "v32_glass_yellow",
                (0.6, 0.32, 0.008),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            "glass_green": pbr(
                "v32_glass_green",
                (0.01, 0.5, 0.13),
                roughness=0.11,
                transmission=0.9,
                ior=1.49,
            ),
            # LED cores
            "led_red_on": pbr(
                "v32_led_red_on",
                (1.0, 0.03, 0.02),
                emission=(1.0, 0.06, 0.03),
                emission_strength=13.0,
                roughness=0.4,
            ),
            "led_yellow_on": pbr(
                "v32_led_yellow_on",
                (1.0, 0.55, 0.02),
                emission=(1.0, 0.52, 0.04),
                emission_strength=13.0,
                roughness=0.4,
            ),
            "led_green_on": pbr(
                "v32_led_green_on",
                (0.02, 1.0, 0.2),
                emission=(0.08, 1.0, 0.32),
                emission_strength=16.0,
                roughness=0.4,
            ),
            "led_red_off": pbr("v32_led_red_off", (0.06, 0.008, 0.006), roughness=0.3),
            "led_yellow_off": pbr(
                "v32_led_yellow_off", (0.07, 0.04, 0.006), roughness=0.3
            ),
            "led_green_off": pbr(
                "v32_led_green_off", (0.008, 0.07, 0.02), roughness=0.3
            ),
            # pedestrian glyphs
            "walk_on": pbr(
                "v32_walk_on",
                (0.9, 1.0, 0.85),
                emission=(0.85, 1.0, 0.8),
                emission_strength=13.0,
            ),
            "hand_off": pbr("v32_hand_off", (0.12, 0.03, 0.005), roughness=0.3),
            "count_on": pbr(
                "v32_count_on",
                (1.0, 0.35, 0.03),
                emission=(1.0, 0.3, 0.02),
                emission_strength=12.0,
            ),
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


def cyl_vert(name, xy, z0, z1, radius, material, coll, vertices=48):
    x, y = xy
    return cyl_between(
        name, (x, y, z0), (x, y, z1), radius, material, coll, vertices=vertices
    )


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
    _, front, _ = basis(yaw)
    loc = local(center, yaw, *offset)
    obj = sphere(name, loc, (radius, radius, bulge), material, coll, segments=56)
    obj.rotation_euler = front.to_track_quat("Z", "Y").to_euler()
    return obj


def arc_visor(name, center, yaw, offset, radius, length, thickness, material, coll):
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


def anchor_base(prefix, xy, yaw, coll, pad_r=0.55, flange=0.34):
    x, y = xy
    cyl_vert(
        f"{prefix}:concrete_pad",
        xy,
        0.0,
        0.14,
        pad_r,
        MATS["concrete"],
        coll,
        vertices=48,
    )
    cube(
        f"{prefix}:base_flange",
        (x, y, 0.17),
        (flange, flange, 0.06),
        MATS["dark_metal"],
        coll,
        yaw=yaw,
        bevel_width=0.02,
    )
    for i, dx in enumerate((-flange / 2 + 0.06, flange / 2 - 0.06)):
        for j, dy in enumerate((-flange / 2 + 0.06, flange / 2 - 0.06)):
            cyl_vert(
                f"{prefix}:anchor:{i}:{j}",
                (x + dx, y + dy),
                0.2,
                0.28,
                0.024,
                MATS["galv"],
                coll,
                vertices=12,
            )


# --------------------------------------------------------------------------- #
# Signal / pedestrian heads
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

    for idx, kind in enumerate(layout):
        x, y, z = positions[idx]
        is_on = kind == active
        glass, on_mat, off_mat = LENS_MATS[kind]
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
# The two traffic-light types
# --------------------------------------------------------------------------- #
def build_upright(prefix, base_xy, yaw, coll, active="red", pole_mat="pole_green"):
    """Straight pedestal pole, side-bracket vertical head, pedestrian head."""
    x, y = base_xy
    mat = MATS[pole_mat]
    anchor_base(prefix, base_xy, yaw, coll, pad_r=0.5, flange=0.3)
    # decorative bell base cover
    cyl_vert(f"{prefix}:base_cover", base_xy, 0.14, 0.62, 0.19, mat, coll, vertices=40)
    cyl_between(
        f"{prefix}:base_taper", (x, y, 0.62), (x, y, 0.78), 0.19, mat, coll, vertices=40
    )
    # main pole
    cyl_vert(f"{prefix}:pole", base_xy, 0.62, 4.5, 0.078, mat, coll, vertices=40)
    # finial cap
    cyl_vert(f"{prefix}:cap", base_xy, 4.5, 4.6, 0.095, mat, coll, vertices=40)
    sphere(
        f"{prefix}:finial", (x, y, 4.66), (0.075, 0.075, 0.09), mat, coll, segments=24
    )
    # side bracket + vertical head near the top
    head_center = tuple(local((x, y, 3.55), yaw, 0, 0.62, 0))
    cyl_between(
        f"{prefix}:bracket",
        (x, y, 3.85),
        tuple(local((x, y, 3.85), yaw, 0, 0.55, 0)),
        0.05,
        mat,
        coll,
        vertices=24,
    )
    cyl_between(
        f"{prefix}:bracket_down",
        tuple(local((x, y, 3.85), yaw, 0, 0.55, 0)),
        tuple(local(head_center, yaw, 0, 0.0, 0.62)),
        0.045,
        mat,
        coll,
        vertices=24,
    )
    signal_head(
        f"{prefix}:head",
        head_center,
        yaw,
        ["red", "yellow", "green"],
        coll,
        orientation="vertical",
        active=active,
    )
    # pedestrian head + push button lower on the pole
    pedestrian_head(
        f"{prefix}:ped", tuple(local((x, y, 2.35), yaw, 0, 0.28, 0)), yaw, coll
    )
    local_box(
        f"{prefix}:btn_box",
        (x, y, 1.25),
        yaw,
        (0.0, 0.2, 0),
        (0.2, 0.13, 0.32),
        MATS["cabinet"],
        coll,
        bevel_width=0.02,
    )
    disc(
        f"{prefix}:btn",
        (x, y, 1.25),
        yaw,
        (0.0, 0.27, 0.02),
        0.045,
        0.02,
        MATS["yellow_trim"],
        coll,
        vertices=24,
    )


def build_mast_arm(
    prefix, base_xy, arm_yaw, coll, active="green", head_yaw=None, pole_mat="galv"
):
    """Tall pole + long tapered horizontal arm, hanging heads + blade sign."""
    x, y = base_xy
    mat = MATS[pole_mat]
    if head_yaw is None:
        head_yaw = arm_yaw + math.pi / 2  # heads face across the arm

    arm_r, arm_f, _ = basis(arm_yaw)  # arm_f points along the arm
    anchor_base(prefix, base_xy, arm_yaw, coll, pad_r=0.7, flange=0.5)
    # hand-hole cover on the pole shaft
    cyl_vert(f"{prefix}:pole", base_xy, 0.2, 6.5, 0.13, mat, coll, vertices=48)
    cyl_vert(
        f"{prefix}:pole_shoulder", base_xy, 0.2, 0.55, 0.16, mat, coll, vertices=48
    )
    cyl_vert(f"{prefix}:cap", base_xy, 6.5, 6.62, 0.15, mat, coll, vertices=48)
    local_box(
        f"{prefix}:handhole",
        (x, y, 1.1),
        arm_yaw,
        (0.14, 0, 0),
        (0.03, 0.16, 0.34),
        MATS["dark_metal"],
        coll,
        bevel_width=0.01,
    )

    arm_len = 5.9
    arm_z = 6.15
    arm_base = Vector((x, y, arm_z))
    arm_tip = arm_base + arm_f * arm_len
    # tapered arm in two segments
    arm_mid = arm_base + arm_f * (arm_len * 0.5)
    cyl_between(f"{prefix}:arm_inner", arm_base, arm_mid, 0.10, mat, coll, vertices=40)
    cyl_between(f"{prefix}:arm_outer", arm_mid, arm_tip, 0.075, mat, coll, vertices=40)
    cyl_between(
        f"{prefix}:arm_flange",
        (x, y, arm_z - 0.02),
        arm_base + arm_f * 0.35,
        0.13,
        mat,
        coll,
        vertices=40,
    )
    # diagonal support truss from high on the pole to the arm
    cyl_between(
        f"{prefix}:truss",
        (x, y, 6.55),
        arm_base + arm_f * (arm_len * 0.55),
        0.03,
        MATS["dark_metal"],
        coll,
        vertices=20,
    )

    # hanging vertical heads
    for i, d in enumerate((2.7, 4.9)):
        ap = arm_base + arm_f * d
        head_center = tuple(ap - Vector((0, 0, 0.95)))
        cyl_between(
            f"{prefix}:hanger:{i}",
            tuple(ap),
            tuple(ap - Vector((0, 0, 0.30))),
            0.03,
            MATS["dark_metal"],
            coll,
            vertices=16,
        )
        signal_head(
            f"{prefix}:hang_head:{i}",
            head_center,
            head_yaw,
            ["red", "yellow", "green"],
            coll,
            orientation="vertical",
            active=active,
        )

    # pole-mounted head for the near side + pedestrian head
    pole_head_center = tuple(local((x, y, 3.4), head_yaw, 0, 0.34, 0))
    cyl_between(
        f"{prefix}:pole_bracket",
        (x, y, 3.4),
        tuple(local((x, y, 3.4), head_yaw, 0, 0.3, 0)),
        0.04,
        mat,
        coll,
        vertices=20,
    )
    signal_head(
        f"{prefix}:pole_head",
        pole_head_center,
        head_yaw,
        ["red", "yellow", "green"],
        coll,
        orientation="vertical",
        active=active,
    )
    pedestrian_head(
        f"{prefix}:ped", tuple(local((x, y, 2.3), head_yaw, 0, 0.3, 0)), head_yaw, coll
    )

    # green street-name blade sign hanging near the arm end
    sp = arm_base + arm_f * (arm_len * 0.72) - Vector((0, 0, 0.42))
    cyl_between(
        f"{prefix}:sign_hanger:a",
        tuple(arm_base + arm_f * (arm_len * 0.72 - 0.55)),
        tuple(sp + arm_f * -0.55 + Vector((0, 0, 0.22))),
        0.018,
        MATS["dark_metal"],
        coll,
        vertices=12,
    )
    cyl_between(
        f"{prefix}:sign_hanger:b",
        tuple(arm_base + arm_f * (arm_len * 0.72 + 0.55)),
        tuple(sp + arm_f * 0.55 + Vector((0, 0, 0.22))),
        0.018,
        MATS["dark_metal"],
        coll,
        vertices=12,
    )
    # blade faces the camera side (broad face along -y), long axis along the arm
    cube(
        f"{prefix}:blade_border",
        tuple(sp),
        (1.54, 0.05, 0.46),
        MATS["sign_white"],
        coll,
        yaw=arm_yaw,
        bevel_width=0.01,
    )
    cube(
        f"{prefix}:blade_sign",
        tuple(sp + Vector((0, 0, 0))),
        (1.46, 0.07, 0.38),
        MATS["sign_green"],
        coll,
        yaw=arm_yaw,
        bevel_width=0.01,
    )


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


# --------------------------------------------------------------------------- #
# Ground, world, camera, render (reused v3 recipe)
# --------------------------------------------------------------------------- #
def ground(coll):
    cube(
        "ground:asphalt",
        (2.0, 0, -0.02),
        (40, 40, 0.04),
        MATS["asphalt"],
        coll,
        bevel_width=0,
    )


def build_world():
    world = bpy.data.worlds.new("v32_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(-45)
    sky.sun_intensity = 1.0
    sky.altitude = 300
    sky.air_density = 1.0
    sky.dust_density = 0.35
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light.inputs["Strength"].default_value = 0.16
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
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-45))


def setup_compositor():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 1.15
    glare.size = 6
    if hasattr(glare, "mix"):
        glare.mix = -0.55
    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def add_cameras(center, radius=16.5, height=4.6):
    focus = bpy.data.objects.new("cam_focus", None)
    bpy.context.scene.collection.objects.link(focus)
    focus.location = center

    still = bpy.data.cameras.new("cam_still")
    still_obj = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(still_obj)
    still.lens = 38
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 6.0
    still.dof.focus_object = focus
    ang = math.radians(-118)
    cam_pos = center + Vector((math.cos(ang) * radius, math.sin(ang) * radius, height))
    still_obj.location = cam_pos
    still_obj.rotation_euler = (center - cam_pos).to_track_quat("-Z", "Y").to_euler()

    orbit = bpy.data.cameras.new("cam_orbit")
    orbit_obj = bpy.data.objects.new("cam_orbit", orbit)
    bpy.context.scene.collection.objects.link(orbit_obj)
    orbit.lens = 36
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 7.0
    orbit.dof.focus_object = focus
    for frame, deg in ((1, -155), (48, -90), (96, -25)):
        loc = center + Vector(
            (
                math.cos(math.radians(deg)) * radius,
                math.sin(math.radians(deg)) * radius,
                height + 0.6 * math.sin(math.radians(deg * 2)),
            )
        )
        orbit_obj.location = loc
        orbit_obj.rotation_euler = (center - loc).to_track_quat("-Z", "Y").to_euler()
        orbit_obj.keyframe_insert(data_path="location", frame=frame)
        orbit_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    for fc in orbit_obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return still_obj, orbit_obj


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
    print(f"[v32] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 12
    scene.cycles.caustics_reflective = False
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    scene.view_settings.exposure = -1.3


def render_still(scene, cam):
    scene.camera = cam
    scene.frame_set(1)
    scene.cycles.samples = 400
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(STILL_PATH)
    print("[v32] rendering hero still ...")
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
    print("[v32] rendering orbit video ...")
    bpy.ops.render.render(animation=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()
    coll = add_collection("v32_traffic_lights")
    ground(coll)

    # Both heads face -y (south) so the lens faces stay toward the camera arc,
    # which sweeps the southern hemisphere.
    # UPRIGHT type on the left
    build_upright(
        "upright",
        (-3.2, 0.0),
        math.radians(180),
        coll,
        active="red",
        pole_mat="pole_green",
    )
    # MAST-ARM type on the right, arm reaching further right (+x)
    build_mast_arm(
        "mast",
        (3.4, 0.0),
        math.radians(0),
        coll,
        active="green",
        head_yaw=math.radians(180),
        pole_mat="galv",
    )

    build_world()
    add_sun()
    still_cam, orbit_cam = add_cameras(Vector((2.0, 0.0, 3.1)))
    configure_cycles()
    setup_compositor()

    scene = bpy.context.scene
    scene.camera = still_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    render_still(scene, still_cam)
    if os.environ.get("V3_STILL_ONLY"):
        print("[v32] still-only mode; skipping video")
        return
    render_video(scene, orbit_cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v32] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
