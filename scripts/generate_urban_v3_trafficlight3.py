"""Photoreal traffic lights v3 (urban_v3_trafficlight3).

Fixes vs v3_2:
  * HORIZONTAL type re-modelled correctly as a Chinese-style cantilever gantry:
    one long horizontal boom over the road carrying a ROW of horizontal
    3-aspect heads (R-Y-G side by side), plus a countdown timer, a diagonal
    tie-rod truss and a green blade sign.
  * Less "toy": flattened signal lenses (no marble bulge) with concentric
    fresnel rings + rubber gasket rings, near-black glossy OFF lenses,
    procedural grunge (noise bump + roughness variation) on housings / poles,
    desaturated retro-reflective borders, road markings for context.

Render recipe (unchanged, tuned): Cycles + OPTIX, Nishita sky split by Light
Path, fog-glow glare, AgX at -1.3 EV.

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_trafficlight3.py
  (V3_STILL_ONLY=1 -> skip video for fast iteration)

Outputs (.../infinigen/outputs/urban_v3_trafficlight3):
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

OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trafficlight3")
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


def add_grunge(
    mat, bump_scale=14.0, bump_strength=0.18, rough_var=0.0, rough_scale=5.0
):
    """Inject a noise bump (and optional roughness variation) so surfaces are
    not perfectly uniform -- the main thing that reads as 'CG toy'."""
    nt = mat.node_tree
    b = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = bump_scale
    noise.inputs["Detail"].default_value = 8.0
    if "Roughness" in noise.inputs:
        noise.inputs["Roughness"].default_value = 0.7
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if rough_var > 0:
        n2 = nt.nodes.new("ShaderNodeTexNoise")
        n2.inputs["Scale"].default_value = rough_scale
        base = b.inputs["Roughness"].default_value
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = max(0.02, base - rough_var)
        mr.inputs["To Max"].default_value = min(1.0, base + rough_var)
        nt.links.new(n2.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return mat


def make_lens_glass(name, tint, ring_scale=55.0):
    """Transmissive tinted lens with concentric fresnel rings (bump)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = pbr(name, tint, roughness=0.08, transmission=0.92, ior=1.49)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = ring_scale
    if "Distortion" in wave.inputs:
        wave.inputs["Distortion"].default_value = 1.5
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(tex.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


MATS = {}


def build_materials():
    MATS.update(
        {
            "galv": pbr(
                "v33_galv",
                (0.30, 0.31, 0.315),
                roughness=0.4,
                metallic=1.0,
                anisotropy=0.35,
            ),
            "pole_black": pbr(
                "v33_pole_black",
                (0.017, 0.018, 0.018),
                roughness=0.4,
                metallic=0.55,
                specular=0.3,
            ),
            "pole_dark": pbr(
                "v33_pole_dark",
                (0.022, 0.03, 0.028),
                roughness=0.42,
                metallic=0.6,
                specular=0.3,
            ),
            "housing": pbr(
                "v33_housing",
                (0.014, 0.015, 0.015),
                roughness=0.52,
                metallic=0.0,
                coat=0.0,
                specular=0.18,
            ),
            "dark_metal": pbr(
                "v33_dark_metal", (0.02, 0.021, 0.021), roughness=0.36, metallic=0.9
            ),
            "rubber": pbr(
                "v33_rubber", (0.008, 0.008, 0.008), roughness=0.68, specular=0.1
            ),
            "backplate": pbr(
                "v33_backplate", (0.006, 0.006, 0.006), roughness=0.72, specular=0.08
            ),
            "yellow_trim": pbr(
                "v33_yellow_trim", (0.62, 0.5, 0.03), roughness=0.5, coat=0.2
            ),
            "cabinet": pbr("v33_cabinet", (0.2, 0.27, 0.23), roughness=0.45, coat=0.25),
            "concrete": pbr("v33_concrete", (0.33, 0.32, 0.30), roughness=0.92),
            "asphalt": pbr("v33_asphalt", (0.026, 0.026, 0.027), roughness=0.88),
            "paint_white": pbr("v33_paint_white", (0.5, 0.5, 0.47), roughness=0.6),
            "paint_yellow": pbr("v33_paint_yellow", (0.42, 0.28, 0.02), roughness=0.55),
            "sign_green": pbr(
                "v33_sign_green", (0.015, 0.12, 0.045), roughness=0.42, specular=0.25
            ),
            "sign_white": pbr("v33_sign_white", (0.62, 0.63, 0.61), roughness=0.45),
            # lens glass with fresnel rings
            "glass_red": make_lens_glass("v33_glass_red", (0.55, 0.015, 0.008)),
            "glass_yellow": make_lens_glass("v33_glass_yellow", (0.6, 0.32, 0.008)),
            "glass_green": make_lens_glass("v33_glass_green", (0.01, 0.5, 0.13)),
            # emissive LED cores
            "led_red_on": pbr(
                "v33_led_red_on",
                (1.0, 0.03, 0.02),
                emission=(1.0, 0.06, 0.03),
                emission_strength=28.0,
                roughness=0.4,
            ),
            "led_yellow_on": pbr(
                "v33_led_yellow_on",
                (1.0, 0.55, 0.02),
                emission=(1.0, 0.52, 0.04),
                emission_strength=26.0,
                roughness=0.4,
            ),
            "led_green_on": pbr(
                "v33_led_green_on",
                (0.02, 1.0, 0.2),
                emission=(0.08, 1.0, 0.32),
                emission_strength=34.0,
                roughness=0.4,
            ),
            # OFF lenses: near-black, glossy (reflect environment like real dark lenses)
            "led_red_off": pbr(
                "v33_led_red_off", (0.05, 0.006, 0.005), roughness=0.16, specular=0.6
            ),
            "led_yellow_off": pbr(
                "v33_led_yellow_off", (0.06, 0.032, 0.005), roughness=0.16, specular=0.6
            ),
            "led_green_off": pbr(
                "v33_led_green_off", (0.006, 0.06, 0.018), roughness=0.16, specular=0.6
            ),
            # pedestrian glyphs
            "walk_on": pbr(
                "v33_walk_on",
                (0.9, 1.0, 0.85),
                emission=(0.85, 1.0, 0.8),
                emission_strength=11.0,
            ),
            "hand_off": pbr("v33_hand_off", (0.1, 0.025, 0.004), roughness=0.3),
            "count_on": pbr(
                "v33_count_on",
                (1.0, 0.35, 0.03),
                emission=(1.0, 0.3, 0.02),
                emission_strength=10.0,
            ),
            "count_green": pbr(
                "v33_count_green",
                (0.05, 1.0, 0.2),
                emission=(0.06, 1.0, 0.25),
                emission_strength=9.0,
            ),
            # dark glassy screen behind the countdown digits
            "screen_dark": pbr(
                "v33_screen_dark", (0.012, 0.014, 0.012), roughness=0.12, specular=0.55
            ),
        }
    )
    # grunge / surface detail
    add_grunge(MATS["housing"], bump_scale=22, bump_strength=0.14, rough_var=0.06)
    add_grunge(MATS["galv"], bump_scale=10, bump_strength=0.12, rough_var=0.1)
    add_grunge(MATS["pole_black"], bump_scale=12, bump_strength=0.1, rough_var=0.07)
    add_grunge(MATS["pole_dark"], bump_scale=12, bump_strength=0.1, rough_var=0.07)
    add_grunge(MATS["backplate"], bump_scale=30, bump_strength=0.1)
    add_grunge(MATS["concrete"], bump_scale=8, bump_strength=0.35, rough_var=0.05)
    add_grunge(MATS["asphalt"], bump_scale=40, bump_strength=0.25, rough_var=0.05)


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


def gasket(name, center, yaw, offset, major_r, minor_r, material, coll):
    _, front, _ = basis(yaw)
    loc = local(center, yaw, *offset)
    bpy.ops.mesh.primitive_torus_add(
        location=loc,
        major_radius=major_r,
        minor_radius=minor_r,
        major_segments=48,
        minor_segments=8,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = front.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, coll)


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
                0.02,
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
                0.022,
                MATS["galv"],
                coll,
                vertices=12,
            )


# --------------------------------------------------------------------------- #
# Heads
# --------------------------------------------------------------------------- #
LENS_MATS = {
    "red": ("glass_red", "led_red_on", "led_red_off"),
    "yellow": ("glass_yellow", "led_yellow_on", "led_yellow_off"),
    "green": ("glass_green", "led_green_on", "led_green_off"),
}


def signal_head(
    prefix,
    center,
    yaw,
    layout,
    coll,
    orientation="vertical",
    active="red",
    lens_r=0.19,
    spacing=0.56,
):
    count = len(layout)
    depth = 0.34
    margin = 0.20
    if orientation == "vertical":
        width = 2 * lens_r + margin
        height = 2 * lens_r + spacing * (count - 1) + margin
        positions = [
            (0.0, 0.0, (count - 1) * spacing / 2 - i * spacing) for i in range(count)
        ]
    else:
        width = 2 * lens_r + spacing * (count - 1) + margin
        height = 2 * lens_r + margin
        positions = [
            (-(count - 1) * spacing / 2 + i * spacing, 0.0, 0.0) for i in range(count)
        ]

    local_box(
        f"{prefix}:backplate",
        center,
        yaw,
        (0, -0.04, 0),
        (width + 0.26, 0.05, height + 0.26),
        MATS["yellow_trim"],
        coll,
        bevel_width=0.02,
    )
    local_box(
        f"{prefix}:backplate_face",
        center,
        yaw,
        (0, -0.02, 0),
        (width + 0.10, 0.05, height + 0.10),
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
        bevel_width=0.045,
    )
    add_bolts(prefix, center, yaw, width + 0.12, height + 0.12, depth, coll)

    for idx, kind in enumerate(layout):
        x, y, z = positions[idx]
        is_on = kind == active
        glass, on_mat, off_mat = LENS_MATS[kind]
        # shallow dark reflector bucket (not too deep or it buries the LED)
        disc(
            f"{prefix}:bucket:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 - 0.01, z),
            lens_r * 1.02,
            0.06,
            MATS["dark_metal"],
            coll,
            vertices=56,
        )
        # LED core: bright flat-ish disc filling the lens when on, dark glossy when off
        convex(
            f"{prefix}:led:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.028, z),
            lens_r * 0.93,
            0.03,
            MATS[on_mat if is_on else off_mat],
            coll,
        )
        # shallow convex fresnel glass cover (no marble bulge)
        convex(
            f"{prefix}:glass:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.05, z),
            lens_r,
            0.026,
            MATS[glass],
            coll,
        )
        # rubber gasket ring at the rim
        gasket(
            f"{prefix}:gasket:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.05, z),
            lens_r * 1.0,
            0.016,
            MATS["rubber"],
            coll,
        )
        # deep tunnel visor
        arc_visor(
            f"{prefix}:visor:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.04, z),
            lens_r * 1.12,
            0.24,
            0.028,
            MATS["housing"],
            coll,
        )

    local_box(
        f"{prefix}:terminal",
        center,
        yaw,
        (0, -depth / 2 - 0.05, -height / 2 + 0.1),
        (min(0.4, width * 0.5), 0.13, 0.18),
        MATS["dark_metal"],
        coll,
        bevel_width=0.012,
    )
    return width, height


# 7-segment segment presence for each digit (a b c d e f g)
_SEG = {
    0: "abcdef",
    1: "bc",
    2: "abged",
    3: "abgcd",
    4: "fgbc",
    5: "afgcd",
    6: "afgecd",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}


def seven_seg_digit(prefix, center, yaw, cx, cz, digit, mat, coll):
    """Emissive 7-segment digit in the head's local frame (x=horiz, z=vert, y=fwd)."""
    dw, dh, t, fy = 0.05, 0.115, 0.022, 0.145
    segs = {
        "a": ((cx, fy, cz + dh), (2 * dw, 0.03, t)),
        "g": ((cx, fy, cz), (2 * dw, 0.03, t)),
        "d": ((cx, fy, cz - dh), (2 * dw, 0.03, t)),
        "f": ((cx - dw, fy, cz + dh / 2), (t, 0.03, dh)),
        "b": ((cx + dw, fy, cz + dh / 2), (t, 0.03, dh)),
        "e": ((cx - dw, fy, cz - dh / 2), (t, 0.03, dh)),
        "c": ((cx + dw, fy, cz - dh / 2), (t, 0.03, dh)),
    }
    for key in _SEG[digit]:
        off, dims = segs[key]
        local_box(
            f"{prefix}:seg:{key}", center, yaw, off, dims, mat, coll, bevel_width=0.004
        )


def countdown_unit(prefix, center, yaw, coll, color="count_green", number=26):
    local_box(
        f"{prefix}:back",
        center,
        yaw,
        (0, -0.03, 0),
        (0.62, 0.05, 0.7),
        MATS["backplate"],
        coll,
        bevel_width=0.02,
    )
    local_box(
        f"{prefix}:case",
        center,
        yaw,
        (0, 0, 0),
        (0.5, 0.24, 0.56),
        MATS["housing"],
        coll,
        bevel_width=0.03,
    )
    local_box(
        f"{prefix}:bezel",
        center,
        yaw,
        (0, 0.115, 0),
        (0.42, 0.02, 0.48),
        MATS["dark_metal"],
        coll,
        bevel_width=0.01,
    )
    local_box(
        f"{prefix}:screen",
        center,
        yaw,
        (0, 0.128, 0),
        (0.36, 0.02, 0.42),
        MATS["screen_dark"],
        coll,
        bevel_width=0.006,
    )
    tens, ones = (number // 10) % 10, number % 10
    seven_seg_digit(f"{prefix}:d0", center, yaw, -0.082, 0.0, tens, MATS[color], coll)
    seven_seg_digit(f"{prefix}:d1", center, yaw, 0.082, 0.0, ones, MATS[color], coll)
    add_bolts(prefix, center, yaw, 0.56, 0.64, 0.24, coll)


def pedestrian_head(prefix, center, yaw, coll):
    local_box(
        f"{prefix}:backplate",
        center,
        yaw,
        (0, -0.02, 0),
        (0.78, 0.05, 0.88),
        MATS["backplate"],
        coll,
        bevel_width=0.02,
    )
    local_box(
        f"{prefix}:case",
        center,
        yaw,
        (0, 0, 0),
        (0.62, 0.24, 0.74),
        MATS["housing"],
        coll,
        bevel_width=0.03,
    )
    local_box(
        f"{prefix}:hand_window",
        center,
        yaw,
        (0, 0.13, 0.16),
        (0.46, 0.02, 0.28),
        MATS["hand_off"],
        coll,
        bevel_width=0.008,
    )
    local_box(
        f"{prefix}:count_window",
        center,
        yaw,
        (0, 0.13, -0.19),
        (0.4, 0.02, 0.2),
        MATS["count_on"],
        coll,
        bevel_width=0.008,
    )
    arc_visor(
        f"{prefix}:visor",
        center,
        yaw,
        (0, 0.12, 0.02),
        0.32,
        0.16,
        0.026,
        MATS["housing"],
        coll,
    )
    add_bolts(prefix, center, yaw, 0.72, 0.82, 0.24, coll)


def rot_z(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return Vector((v.x * ca - v.y * sa, v.x * sa + v.y * ca, v.z))


# --------------------------------------------------------------------------- #
# Type A: horizontal cantilever gantry (long boom + a ROW of horizontal heads)
# --------------------------------------------------------------------------- #
def build_horizontal_gantry(prefix, base_xy, coll, head_yaw=math.radians(180)):
    x, y = base_xy
    mat = MATS["galv"]
    anchor_base(prefix, base_xy, 0.0, coll, pad_r=0.8, flange=0.56)
    # tall pole
    cyl_vert(f"{prefix}:pole", base_xy, 0.2, 7.0, 0.15, mat, coll, vertices=48)
    cyl_vert(
        f"{prefix}:pole_shoulder", base_xy, 0.2, 0.6, 0.185, mat, coll, vertices=48
    )
    cyl_vert(f"{prefix}:cap", base_xy, 7.0, 7.14, 0.17, mat, coll, vertices=48)
    local_box(
        f"{prefix}:handhole",
        (x, y, 1.2),
        0.0,
        (0.16, 0, 0),
        (0.03, 0.18, 0.36),
        MATS["dark_metal"],
        coll,
        bevel_width=0.01,
    )

    # long horizontal boom extending +x over the road
    boom_len = 8.6
    boom_z = 6.35
    boom_a = Vector((x, y, boom_z))
    boom_b = Vector((x + boom_len, y, boom_z))
    boom_mid = boom_a.lerp(boom_b, 0.5)
    cyl_between(f"{prefix}:boom_inner", boom_a, boom_mid, 0.12, mat, coll, vertices=44)
    cyl_between(f"{prefix}:boom_outer", boom_mid, boom_b, 0.088, mat, coll, vertices=44)
    cyl_between(
        f"{prefix}:boom_flange",
        (x, y, boom_z),
        (x + 0.5, y, boom_z),
        0.155,
        mat,
        coll,
        vertices=44,
    )
    sphere(
        f"{prefix}:boom_end", tuple(boom_b), (0.09, 0.09, 0.09), mat, coll, segments=24
    )
    # diagonal tie-rod truss supporting the long cantilever
    cyl_between(
        f"{prefix}:truss_hi",
        (x, y, 6.95),
        Vector((x + boom_len * 0.62, y, boom_z + 0.02)),
        0.028,
        MATS["dark_metal"],
        coll,
        vertices=18,
    )
    cyl_between(
        f"{prefix}:truss_strut", (x, y, 6.95), (x, y, 7.0), 0.04, mat, coll, vertices=18
    )

    # ROW of horizontal 3-aspect heads hanging just below the boom
    head_xs = [x + 1.9, x + 4.2, x + 6.5]
    actives = ["green", "green", "red"]
    head_top = boom_z - 0.12
    for i, (hx, act) in enumerate(zip(head_xs, actives)):
        ap = Vector((hx, y, boom_z))
        # clamp collar on the boom + short drop bracket
        cyl_between(
            f"{prefix}:collar:{i}",
            (hx, y, boom_z + 0.09),
            (hx, y, boom_z - 0.09),
            0.11,
            MATS["dark_metal"],
            coll,
            vertices=24,
        )
        cyl_between(
            f"{prefix}:drop:{i}",
            (hx, y, head_top),
            (hx, y, head_top - 0.34),
            0.032,
            MATS["dark_metal"],
            coll,
            vertices=16,
        )
        head_center = (hx, y, head_top - 0.34 - 0.24)
        signal_head(
            f"{prefix}:hhead:{i}",
            head_center,
            head_yaw,
            ["red", "yellow", "green"],
            coll,
            orientation="horizontal",
            active=act,
            lens_r=0.16,
            spacing=0.44,
        )

    # countdown timer + green blade sign near the boom
    countdown_unit(
        f"{prefix}:count",
        (x + 3.05, y, boom_z - 0.62),
        head_yaw,
        coll,
        color="count_green",
    )
    cyl_between(
        f"{prefix}:count_drop",
        (x + 3.05, y, boom_z - 0.09),
        (x + 3.05, y, boom_z - 0.28),
        0.028,
        MATS["dark_metal"],
        coll,
        vertices=14,
    )
    sp = Vector((x + 7.5, y, boom_z - 0.5))
    cube(
        f"{prefix}:blade_border",
        tuple(sp),
        (1.5, 0.05, 0.44),
        MATS["sign_white"],
        coll,
        bevel_width=0.01,
    )
    cube(
        f"{prefix}:blade_sign",
        tuple(sp),
        (1.42, 0.07, 0.36),
        MATS["sign_green"],
        coll,
        bevel_width=0.01,
    )
    for hx in (x + 7.5 - 0.6, x + 7.5 + 0.6):
        cyl_between(
            f"{prefix}:sign_hang:{hx:.1f}",
            (hx, y, boom_z - 0.09),
            (hx, y, boom_z - 0.28),
            0.016,
            MATS["dark_metal"],
            coll,
            vertices=12,
        )


# --------------------------------------------------------------------------- #
# Type B: upright pedestal pole
# --------------------------------------------------------------------------- #
def build_upright(prefix, base_xy, yaw, coll, active="red"):
    x, y = base_xy
    mat = MATS["pole_dark"]
    anchor_base(prefix, base_xy, yaw, coll, pad_r=0.5, flange=0.3)
    cyl_vert(f"{prefix}:base_cover", base_xy, 0.14, 0.62, 0.185, mat, coll, vertices=40)
    cyl_between(
        f"{prefix}:base_taper",
        (x, y, 0.62),
        (x, y, 0.78),
        0.185,
        mat,
        coll,
        vertices=40,
    )
    cyl_vert(f"{prefix}:pole", base_xy, 0.62, 4.6, 0.076, mat, coll, vertices=40)
    cyl_vert(f"{prefix}:cap", base_xy, 4.6, 4.7, 0.092, mat, coll, vertices=40)
    sphere(
        f"{prefix}:finial", (x, y, 4.76), (0.072, 0.072, 0.088), mat, coll, segments=24
    )
    head_center = tuple(local((x, y, 3.6), yaw, 0, 0.6, 0))
    cyl_between(
        f"{prefix}:bracket",
        (x, y, 3.9),
        tuple(local((x, y, 3.9), yaw, 0, 0.54, 0)),
        0.048,
        mat,
        coll,
        vertices=24,
    )
    cyl_between(
        f"{prefix}:bracket_down",
        tuple(local((x, y, 3.9), yaw, 0, 0.54, 0)),
        tuple(local(head_center, yaw, 0, 0.0, 0.62)),
        0.044,
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
    pedestrian_head(
        f"{prefix}:ped", tuple(local((x, y, 2.4), yaw, 0, 0.28, 0)), yaw, coll
    )
    local_box(
        f"{prefix}:btn_box",
        (x, y, 1.3),
        yaw,
        (0.0, 0.2, 0),
        (0.2, 0.13, 0.32),
        MATS["cabinet"],
        coll,
        bevel_width=0.02,
    )
    disc(
        f"{prefix}:btn",
        (x, y, 1.3),
        yaw,
        (0.0, 0.27, 0.02),
        0.045,
        0.02,
        MATS["yellow_trim"],
        coll,
        vertices=24,
    )


# --------------------------------------------------------------------------- #
# Ground + world + camera + render
# --------------------------------------------------------------------------- #
def ground(coll):
    cube(
        "ground:asphalt",
        (2.0, 1.0, -0.02),
        (44, 44, 0.04),
        MATS["asphalt"],
        coll,
        bevel_width=0,
    )
    # stop bar + lane dashes under the gantry to read as 'over the road'
    cube(
        "ground:stopbar",
        (2.0, -3.2, 0.005),
        (13, 0.5, 0.01),
        MATS["paint_white"],
        coll,
        bevel_width=0,
    )
    for i, lx in enumerate(range(-3, 9, 3)):
        cube(
            f"ground:laneline:{i}",
            (lx, 1.5, 0.005),
            (0.16, 3.2, 0.01),
            MATS["paint_white"],
            coll,
            bevel_width=0,
        )
    cube(
        "ground:center_yellow",
        (2.0, 4.6, 0.006),
        (13, 0.16, 0.01),
        MATS["paint_yellow"],
        coll,
        bevel_width=0,
    )


def build_world():
    world = bpy.data.worlds.new("v33_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(40)
    sky.sun_rotation = math.radians(-50)
    sky.sun_intensity = 1.0
    sky.altitude = 300
    sky.air_density = 1.0
    sky.dust_density = 0.3
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_light = nt.nodes.new("ShaderNodeBackground")
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light.inputs[
        "Strength"
    ].default_value = 0.22  # a bit brighter for metal reflections
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
    sun.data.energy = 3.0
    sun.data.angle = math.radians(1.8)
    sun.data.color = (1.0, 0.94, 0.84)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-50))


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
        glare.mix = -0.6
    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def add_cameras(hero, wide_center):
    focus = bpy.data.objects.new("cam_focus", None)
    bpy.context.scene.collection.objects.link(focus)
    focus.location = hero

    # hero still: 3/4 view showing the whole gantry (pole + long boom + row)
    still = bpy.data.cameras.new("cam_still")
    still_obj = bpy.data.objects.new("cam_still", still)
    bpy.context.scene.collection.objects.link(still_obj)
    still.lens = 35
    still.sensor_width = 36
    still.dof.use_dof = True
    still.dof.aperture_fstop = 7.0
    still.dof.focus_object = focus
    cam_pos = Vector((-6.0, -14.5, 2.4))
    still_obj.location = cam_pos
    still_obj.rotation_euler = (
        (Vector((0.5, 0.0, 4.3)) - cam_pos).to_track_quat("-Z", "Y").to_euler()
    )

    # orbit: wide, whole scene (full boom + upright)
    wfocus = bpy.data.objects.new("cam_wfocus", None)
    bpy.context.scene.collection.objects.link(wfocus)
    wfocus.location = wide_center
    orbit = bpy.data.cameras.new("cam_orbit")
    orbit_obj = bpy.data.objects.new("cam_orbit", orbit)
    bpy.context.scene.collection.objects.link(orbit_obj)
    orbit.lens = 30
    orbit.sensor_width = 36
    orbit.dof.use_dof = True
    orbit.dof.aperture_fstop = 9.0
    orbit.dof.focus_object = wfocus
    radius = 21.0
    height = 5.2
    for frame, deg in ((1, -150), (48, -90), (96, -30)):
        loc = wide_center + Vector(
            (
                math.cos(math.radians(deg)) * radius,
                math.sin(math.radians(deg)) * radius,
                height + 0.5 * math.sin(math.radians(deg * 2)),
            )
        )
        orbit_obj.location = loc
        orbit_obj.rotation_euler = (
            (wide_center - loc).to_track_quat("-Z", "Y").to_euler()
        )
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
    print(f"[v33] Cycles backend: {chosen}")
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
    scene.cycles.samples = 420
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(STILL_PATH)
    print("[v33] rendering hero still ...")
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
    print("[v33] rendering orbit video ...")
    bpy.ops.render.render(animation=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()
    coll = add_collection("v33_traffic_lights")
    ground(coll)

    # Horizontal cantilever gantry (hero, corrected): pole left, boom over road
    build_horizontal_gantry("gantry", (-4.4, 0.0), coll, head_yaw=math.radians(180))
    # Upright pedestal for comparison, to the right
    build_upright("upright", (7.6, -0.4), math.radians(180), coll, active="red")

    build_world()
    add_sun()
    still_cam, orbit_cam = add_cameras(
        Vector((-0.2, 0.0, 5.6)), Vector((1.5, 0.0, 3.4))
    )
    configure_cycles()
    setup_compositor()

    scene = bpy.context.scene
    scene.camera = still_cam
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    render_still(scene, still_cam)
    if os.environ.get("V3_STILL_ONLY"):
        print("[v33] still-only mode; skipping video")
        return
    render_video(scene, orbit_cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    print("[v33] done ->", OUTPUT_DIR)


if __name__ == "__main__":
    main()
