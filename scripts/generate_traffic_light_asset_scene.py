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
from pathlib import Path

import bpy
from mathutils import Vector


OUTPUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_2")
SCENE_PATH = OUTPUT_DIR / "scene.blend"
VIDEO_PATH = OUTPUT_DIR / "traffic_light_asset_review.mp4"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.images,
    ):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def mat(
    name, color, roughness=0.6, metallic=0.0, alpha=1.0, emission=None, strength=0.0
):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = (color[0], color[1], color[2], alpha)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], alpha)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Alpha"].default_value = alpha
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (
                emission[0],
                emission[1],
                emission[2],
                1,
            )
            bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        material.blend_method = "BLEND"
        material.use_screen_refraction = True
    return material


MATS = {}


def build_materials():
    MATS.update(
        {
            "asphalt": mat(
                "tl_mat_weathered_asphalt", (0.075, 0.073, 0.067), roughness=0.95
            ),
            "asphalt_light": mat(
                "tl_mat_asphalt_aggregate", (0.14, 0.135, 0.12), roughness=0.98
            ),
            "sidewalk": mat(
                "tl_mat_concrete_sidewalk", (0.54, 0.52, 0.47), roughness=0.9
            ),
            "curb": mat("tl_mat_chipped_curb", (0.72, 0.69, 0.62), roughness=0.88),
            "paint": mat("tl_mat_road_paint", (0.92, 0.9, 0.82), roughness=0.66),
            "yellow_paint": mat(
                "tl_mat_reflective_yellow_paint", (0.95, 0.68, 0.13), roughness=0.5
            ),
            "housing": mat(
                "tl_mat_powder_coated_signal_black",
                (0.018, 0.02, 0.018),
                roughness=0.55,
                metallic=0.18,
            ),
            "backplate": mat(
                "tl_mat_matte_backplate", (0.006, 0.007, 0.006), roughness=0.72
            ),
            "yellow_trim": mat(
                "tl_mat_signal_yellow_trim", (0.94, 0.64, 0.05), roughness=0.5
            ),
            "metal": mat(
                "tl_mat_galvanized_metal",
                (0.47, 0.48, 0.45),
                roughness=0.42,
                metallic=0.55,
            ),
            "dark_metal": mat(
                "tl_mat_dark_bracket_metal",
                (0.045, 0.047, 0.044),
                roughness=0.44,
                metallic=0.5,
            ),
            "glass_red_on": mat(
                "tl_mat_convex_red_lens_on",
                (0.95, 0.02, 0.015),
                roughness=0.18,
                alpha=0.86,
                emission=(1.0, 0.04, 0.02),
                strength=2.4,
            ),
            "glass_yellow_on": mat(
                "tl_mat_convex_yellow_lens_on",
                (1.0, 0.68, 0.02),
                roughness=0.18,
                alpha=0.84,
                emission=(1.0, 0.56, 0.02),
                strength=1.8,
            ),
            "glass_green_on": mat(
                "tl_mat_convex_green_lens_on",
                (0.02, 0.85, 0.18),
                roughness=0.18,
                alpha=0.86,
                emission=(0.02, 0.95, 0.22),
                strength=2.0,
            ),
            "glass_red_dim": mat(
                "tl_mat_convex_red_lens_dim",
                (0.25, 0.015, 0.012),
                roughness=0.32,
                alpha=0.72,
                emission=(0.45, 0.02, 0.01),
                strength=0.12,
            ),
            "glass_yellow_dim": mat(
                "tl_mat_convex_yellow_lens_dim",
                (0.35, 0.22, 0.02),
                roughness=0.32,
                alpha=0.72,
                emission=(0.55, 0.34, 0.02),
                strength=0.1,
            ),
            "glass_green_dim": mat(
                "tl_mat_convex_green_lens_dim",
                (0.015, 0.24, 0.055),
                roughness=0.32,
                alpha=0.72,
                emission=(0.02, 0.4, 0.08),
                strength=0.1,
            ),
            "walk_on": mat(
                "tl_mat_walk_symbol_on",
                (0.9, 0.95, 0.86),
                roughness=0.16,
                emission=(0.9, 1.0, 0.82),
                strength=1.9,
            ),
            "dont_walk": mat(
                "tl_mat_hand_symbol_dim",
                (0.55, 0.22, 0.04),
                roughness=0.2,
                emission=(0.9, 0.25, 0.04),
                strength=0.35,
            ),
            "cabinet": mat(
                "tl_mat_control_cabinet_green_gray",
                (0.34, 0.43, 0.37),
                roughness=0.54,
                metallic=0.18,
            ),
            "grass": mat("tl_mat_urban_grass", (0.18, 0.36, 0.14), roughness=0.92),
            "leaf": mat("tl_mat_shrub_leaf_mix", (0.08, 0.28, 0.09), roughness=0.84),
            "brick": mat("tl_mat_lowrise_brick", (0.55, 0.23, 0.16), roughness=0.82),
            "glass": mat(
                "tl_mat_lowrise_window_glass",
                (0.16, 0.25, 0.32),
                roughness=0.22,
                metallic=0.05,
            ),
        }
    )


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
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    obj.select_set(False)
    return obj


def bevel(obj, width=0.02, segments=1):
    if width <= 0:
        return obj
    mod = obj.modifiers.new("softened_edges", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.affect = "EDGES"
    obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    return obj


def cube(name, loc, dims, material, collection, yaw=0.0, bevel_width=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[2] = yaw
    if material:
        obj.data.materials.append(material)
    bevel(obj, bevel_width)
    return link_to(obj, collection)


def sphere(name, loc, scale, material, collection, segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=max(8, segments // 2), radius=1, location=loc
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, collection)


def cyl_between(name, start, end, radius, material, collection, vertices=32):
    start_v = Vector(start)
    end_v = Vector(end)
    mid = (start_v + end_v) * 0.5
    direction = end_v - start_v
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=direction.length, location=mid
    )
    obj = bpy.context.object
    obj.name = name
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, collection)


def cone_between(name, start, end, radius1, radius2, material, collection, vertices=32):
    start_v = Vector(start)
    end_v = Vector(end)
    mid = (start_v + end_v) * 0.5
    direction = end_v - start_v
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=direction.length,
        location=mid,
    )
    obj = bpy.context.object
    obj.name = name
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    if material:
        obj.data.materials.append(material)
    smooth(obj)
    return link_to(obj, collection)


def basis(yaw):
    right = Vector((math.cos(yaw), math.sin(yaw), 0))
    front = Vector((-math.sin(yaw), math.cos(yaw), 0))
    up = Vector((0, 0, 1))
    return right, front, up


def local(center, yaw, x=0, y=0, z=0):
    right, front, up = basis(yaw)
    return Vector(center) + right * x + front * y + up * z


def local_box(name, center, yaw, offset, dims, material, collection, bevel_width=0.015):
    return cube(
        name,
        local(center, yaw, *offset),
        dims,
        material,
        collection,
        yaw=yaw,
        bevel_width=bevel_width,
    )


def disc(name, center, yaw, offset, radius, depth, material, collection, vertices=48):
    _, front, _ = basis(yaw)
    c = local(center, yaw, *offset)
    return cyl_between(
        name,
        c - front * (depth * 0.5),
        c + front * (depth * 0.5),
        radius,
        material,
        collection,
        vertices=vertices,
    )


def lens(name, center, yaw, offset, radius, material, collection):
    right, front, _ = basis(yaw)
    loc = local(center, yaw, *offset)
    scale = (radius, radius, 0.055)
    obj = sphere(name, loc, scale, material, collection, segments=40)
    # Align the shallow lens bulge toward the viewer.
    obj.rotation_euler = front.to_track_quat("Z", "Y").to_euler()
    return obj


def arc_visor(
    name, center, yaw, offset, radius, length, thickness, material, collection
):
    right, front, up = basis(yaw)
    c = local(center, yaw, *offset)
    verts = []
    faces = []
    steps = 18
    for depth_i, d in enumerate((0, length)):
        for layer, r in enumerate((radius, radius + thickness)):
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
        a = i
        b = i + 1
        c1 = ring + i + 1
        d = ring + i
        faces.append((a, b, c1, d))
        off = 2 * ring
        faces.append((off + a, off + d, off + c1, off + b))
        faces.append((a, off + a, off + b, b))
        faces.append((d, c1, off + c1, off + d))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    collection.objects.link(obj)
    obj.modifiers.new("visor_weighted_normals", "WEIGHTED_NORMAL")
    return obj


def led_dot_grid(
    name, center, yaw, lens_offset, radius, material, collection, active=True
):
    dot_radius = 0.012 if active else 0.009
    spacing = 0.067
    idx = 0
    for ix in range(-3, 4):
        for iz in range(-3, 4):
            if ix * ix + iz * iz > 10:
                continue
            if not active and (ix + iz) % 3:
                continue
            pos = (
                lens_offset[0] + ix * spacing,
                lens_offset[1] + 0.055,
                lens_offset[2] + iz * spacing,
            )
            disc(
                f"{name}:led:{idx:02d}",
                center,
                yaw,
                pos,
                dot_radius,
                0.01,
                material,
                collection,
                vertices=12,
            )
            idx += 1


def arrow_glyph(name, center, yaw, lens_offset, material, collection, direction="left"):
    p = Vector(lens_offset)
    zoff = 0.075
    y = p.y + 0.075
    if direction == "left":
        points = [
            ((p.x + 0.105, y, p.z), (p.x - 0.11, y, p.z)),
            ((p.x - 0.11, y, p.z), (p.x - 0.01, y, p.z + zoff)),
            ((p.x - 0.11, y, p.z), (p.x - 0.01, y, p.z - zoff)),
        ]
    elif direction == "right":
        points = [
            ((p.x - 0.105, y, p.z), (p.x + 0.11, y, p.z)),
            ((p.x + 0.11, y, p.z), (p.x + 0.01, y, p.z + zoff)),
            ((p.x + 0.11, y, p.z), (p.x + 0.01, y, p.z - zoff)),
        ]
    else:
        points = [
            ((p.x, y, p.z - 0.105), (p.x, y, p.z + 0.11)),
            ((p.x, y, p.z + 0.11), (p.x - 0.075, y, p.z + 0.005)),
            ((p.x, y, p.z + 0.11), (p.x + 0.075, y, p.z + 0.005)),
        ]
    for i, (a, b) in enumerate(points):
        a_world = local(center, yaw, *a)
        b_world = local(center, yaw, *b)
        cyl_between(
            f"{name}:arrow:{i}",
            a_world,
            b_world,
            0.016,
            material,
            collection,
            vertices=10,
        )


def add_bolts(prefix, center, yaw, width, height, depth, collection):
    for i, x in enumerate((-width / 2 + 0.09, width / 2 - 0.09)):
        for j, z in enumerate((-height / 2 + 0.09, height / 2 - 0.09)):
            disc(
                f"{prefix}:bolt:{i}:{j}",
                center,
                yaw,
                (x, depth / 2 + 0.015, z),
                0.025,
                0.018,
                MATS["metal"],
                collection,
                vertices=14,
            )


def signal_head(
    prefix, center, yaw, layout, collection, orientation="vertical", active_name="red"
):
    count = len(layout)
    spacing = 0.58
    lens_r = 0.195
    depth = 0.34
    if orientation == "vertical":
        width = 0.78
        height = 0.34 + spacing * (count - 1) + 0.45
        positions = [
            (0.0, 0.0, (count - 1) * spacing / 2 - i * spacing) for i in range(count)
        ]
    else:
        width = 0.34 + spacing * (count - 1) + 0.62
        height = 0.78
        positions = [
            (-(count - 1) * spacing / 2 + i * spacing, 0.0, 0.0) for i in range(count)
        ]

    local_box(
        f"{prefix}:retroreflective_backplate",
        center,
        yaw,
        (0, -0.03, 0),
        (width + 0.28, 0.055, height + 0.28),
        MATS["backplate"],
        collection,
        bevel_width=0.055,
    )
    local_box(
        f"{prefix}:yellow_border_top",
        center,
        yaw,
        (0, -0.061, height / 2 + 0.12),
        (width + 0.35, 0.022, 0.045),
        MATS["yellow_trim"],
        collection,
        bevel_width=0.008,
    )
    local_box(
        f"{prefix}:yellow_border_bottom",
        center,
        yaw,
        (0, -0.061, -height / 2 - 0.12),
        (width + 0.35, 0.022, 0.045),
        MATS["yellow_trim"],
        collection,
        bevel_width=0.008,
    )
    local_box(
        f"{prefix}:weatherproof_housing",
        center,
        yaw,
        (0, 0, 0),
        (width, depth, height),
        MATS["housing"],
        collection,
        bevel_width=0.045,
    )
    add_bolts(prefix, center, yaw, width + 0.18, height + 0.18, depth, collection)

    for idx, (kind, arrow_dir) in enumerate(layout):
        x, y, z = positions[idx]
        is_active = kind == active_name
        if kind == "red":
            lens_mat = MATS["glass_red_on"] if is_active else MATS["glass_red_dim"]
        elif kind == "yellow":
            lens_mat = (
                MATS["glass_yellow_on"] if is_active else MATS["glass_yellow_dim"]
            )
        else:
            lens_mat = MATS["glass_green_on"] if is_active else MATS["glass_green_dim"]
        disc(
            f"{prefix}:recessed_reflector_bucket:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.01, z),
            lens_r * 1.08,
            0.045,
            MATS["dark_metal"],
            collection,
            vertices=48,
        )
        lens(
            f"{prefix}:convex_{kind}_lens:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.055, z),
            lens_r,
            lens_mat,
            collection,
        )
        led_dot_grid(
            f"{prefix}:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.091, z),
            lens_r,
            lens_mat,
            collection,
            active=is_active,
        )
        arc_visor(
            f"{prefix}:deep_cutaway_visor:{kind}:{idx}",
            center,
            yaw,
            (x, depth / 2 + 0.07, z),
            lens_r * 1.13,
            0.31,
            0.035,
            MATS["housing"],
            collection,
        )
        if arrow_dir:
            arrow_glyph(
                f"{prefix}:{kind}:{idx}",
                center,
                yaw,
                (x, depth / 2 + 0.112, z),
                lens_mat,
                collection,
                direction=arrow_dir,
            )

    local_box(
        f"{prefix}:terminal_box",
        center,
        yaw,
        (0, -depth / 2 - 0.065, -height / 2 + 0.14),
        (0.42, 0.16, 0.22),
        MATS["dark_metal"],
        collection,
        bevel_width=0.018,
    )
    return width, height


def pedestrian_head(prefix, center, yaw, collection, countdown="12"):
    local_box(
        f"{prefix}:pedestrian_signal_backplate",
        center,
        yaw,
        (0, -0.02, 0),
        (0.95, 0.05, 1.08),
        MATS["backplate"],
        collection,
        bevel_width=0.04,
    )
    local_box(
        f"{prefix}:pedestrian_signal_case",
        center,
        yaw,
        (0, 0, 0),
        (0.74, 0.24, 0.86),
        MATS["housing"],
        collection,
        bevel_width=0.035,
    )
    local_box(
        f"{prefix}:upper_icon_window",
        center,
        yaw,
        (-0.16, 0.145, 0.18),
        (0.24, 0.025, 0.22),
        MATS["walk_on"],
        collection,
        bevel_width=0.01,
    )
    local_box(
        f"{prefix}:dont_walk_window",
        center,
        yaw,
        (0.17, 0.145, 0.18),
        (0.24, 0.025, 0.22),
        MATS["dont_walk"],
        collection,
        bevel_width=0.01,
    )
    local_box(
        f"{prefix}:countdown_lcd",
        center,
        yaw,
        (0.0, 0.145, -0.22),
        (0.48, 0.026, 0.22),
        MATS["dark_metal"],
        collection,
        bevel_width=0.012,
    )
    add_text(
        f"{prefix}:countdown_digits",
        countdown,
        local(center, yaw, 0, 0.164, -0.29),
        0.22,
        MATS["walk_on"],
        collection,
        yaw=yaw,
        align="CENTER",
    )
    arc_visor(
        f"{prefix}:pedestrian_top_visor",
        center,
        yaw,
        (0, 0.145, 0.18),
        0.39,
        0.2,
        0.03,
        MATS["housing"],
        collection,
    )
    add_bolts(prefix, center, yaw, 0.9, 1.0, 0.24, collection)


def add_text(name, text, loc, size, material, collection, yaw=0.0, align="LEFT"):
    bpy.ops.object.text_add(location=loc, rotation=(math.radians(90), 0, yaw))
    obj = bpy.context.object
    obj.name = name
    obj.data.body = text
    obj.data.align_x = align
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.006
    obj.data.resolution_u = 8
    if material:
        obj.data.materials.append(material)
    return link_to(obj, collection)


def mast_arm_signal(prefix, pole_xy, yaw, collection, variant="standard"):
    x, y = pole_xy
    cyl_between(
        f"{prefix}:fluted_base_pole",
        (x, y, 0.05),
        (x, y, 4.75),
        0.115,
        MATS["metal"],
        collection,
        vertices=36,
    )
    cyl_between(
        f"{prefix}:mast_arm",
        (x, y, 4.55),
        tuple(local((x, y, 4.55), yaw, 0, 4.25, 0)),
        0.072,
        MATS["metal"],
        collection,
        vertices=32,
    )
    cyl_between(
        f"{prefix}:diagonal_support_cable",
        (x, y, 4.78),
        tuple(local((x, y, 4.55), yaw, 0, 3.2, 0)),
        0.018,
        MATS["dark_metal"],
        collection,
        vertices=12,
    )
    cube(
        f"{prefix}:mounting_base_plate",
        (x, y, 0.06),
        (0.55, 0.55, 0.08),
        MATS["dark_metal"],
        collection,
        bevel_width=0.02,
    )
    for i, dx in enumerate((-0.19, 0.19)):
        for j, dy in enumerate((-0.19, 0.19)):
            cyl_between(
                f"{prefix}:anchor_bolt:{i}:{j}",
                (x + dx, y + dy, 0.08),
                (x + dx, y + dy, 0.16),
                0.026,
                MATS["metal"],
                collection,
                vertices=12,
            )
    head_center = tuple(local((x, y, 4.05), yaw, 0, 3.82, 0))
    if variant == "five":
        signal_head(
            f"{prefix}:five_section_left_turn",
            head_center,
            yaw,
            [
                ("red", None),
                ("yellow", None),
                ("green", "left"),
                ("yellow", "left"),
                ("green", None),
            ],
            collection,
            orientation="vertical",
            active_name="green",
        )
    elif variant == "horizontal":
        signal_head(
            f"{prefix}:horizontal_head",
            head_center,
            yaw,
            [("red", None), ("yellow", None), ("green", None)],
            collection,
            orientation="horizontal",
            active_name="yellow",
        )
    else:
        signal_head(
            f"{prefix}:vertical_head",
            head_center,
            yaw,
            [("red", None), ("yellow", None), ("green", None)],
            collection,
            orientation="vertical",
            active_name="red",
        )
    cyl_between(
        f"{prefix}:signal_hanger",
        tuple(local((x, y, 4.55), yaw, 0, 3.82, 0)),
        tuple(local(head_center, yaw, 0, -0.18, 0.68)),
        0.025,
        MATS["dark_metal"],
        collection,
        vertices=16,
    )


def corner_pedestal(prefix, pole_xy, yaw, collection, active="green"):
    x, y = pole_xy
    cyl_between(
        f"{prefix}:short_corner_pole",
        (x, y, 0.05),
        (x, y, 3.45),
        0.09,
        MATS["metal"],
        collection,
        vertices=32,
    )
    signal_head(
        f"{prefix}:side_mounted_three_light",
        tuple(local((x, y, 2.72), yaw, 0, 0.28, 0)),
        yaw,
        [("red", None), ("yellow", None), ("green", None)],
        collection,
        orientation="vertical",
        active_name=active,
    )
    pedestrian_head(
        f"{prefix}:pedestrian_box",
        tuple(local((x, y, 1.95), yaw, 0, -0.31, 0)),
        yaw,
        collection,
        countdown="12",
    )
    local_box(
        f"{prefix}:push_button_box",
        (x, y, 1.12),
        yaw,
        (0.18, 0.11, 0),
        (0.2, 0.12, 0.32),
        MATS["cabinet"],
        collection,
        bevel_width=0.018,
    )
    disc(
        f"{prefix}:push_button",
        (x, y, 1.12),
        yaw,
        (0.18, 0.18, 0.01),
        0.045,
        0.02,
        MATS["yellow_trim"],
        collection,
        vertices=20,
    )
    local_box(
        f"{prefix}:small_access_panel",
        (x, y, 0.62),
        yaw,
        (-0.01, 0.092, 0),
        (0.16, 0.02, 0.28),
        MATS["dark_metal"],
        collection,
        bevel_width=0.006,
    )


def add_control_cabinet(collection):
    base = (5.8, -6.4, 0.55)
    cube(
        "traffic_signal_controller:cabinet_body",
        base,
        (0.78, 0.48, 1.05),
        MATS["cabinet"],
        collection,
        yaw=math.radians(12),
        bevel_width=0.025,
    )
    cube(
        "traffic_signal_controller:door_seam",
        (5.8, -6.64, 0.6),
        (0.55, 0.018, 0.83),
        MATS["dark_metal"],
        collection,
        yaw=math.radians(12),
        bevel_width=0.004,
    )
    cube(
        "traffic_signal_controller:service_sticker",
        (5.67, -6.66, 0.92),
        (0.26, 0.012, 0.13),
        MATS["yellow_trim"],
        collection,
        yaw=math.radians(12),
        bevel_width=0.003,
    )
    cyl_between(
        "traffic_signal_controller:underground_conduit",
        (5.8, -6.42, 0.08),
        (4.9, -5.6, 0.08),
        0.035,
        MATS["dark_metal"],
        collection,
        vertices=16,
    )


def add_road_scene(collection):
    cube(
        "urban_v2_2:road:east_west_asphalt",
        (0, 0, -0.015),
        (28, 7.2, 0.03),
        MATS["asphalt"],
        collection,
        bevel_width=0,
    )
    cube(
        "urban_v2_2:road:north_south_asphalt",
        (0, 0, -0.012),
        (7.2, 28, 0.03),
        MATS["asphalt"],
        collection,
        bevel_width=0,
    )
    for side, y in enumerate((-5.1, 5.1)):
        cube(
            f"urban_v2_2:sidewalk:ew:{side}",
            (0, y, 0.035),
            (28, 2.6, 0.09),
            MATS["sidewalk"],
            collection,
            bevel_width=0.018,
        )
    for side, x in enumerate((-5.1, 5.1)):
        cube(
            f"urban_v2_2:sidewalk:ns:{side}",
            (x, 0, 0.038),
            (2.6, 28, 0.09),
            MATS["sidewalk"],
            collection,
            bevel_width=0.018,
        )
    for i, y in enumerate((-3.72, 3.72)):
        cube(
            f"urban_v2_2:curb:ew:{i}",
            (0, y, 0.12),
            (28, 0.25, 0.14),
            MATS["curb"],
            collection,
            bevel_width=0.015,
        )
    for i, x in enumerate((-3.72, 3.72)):
        cube(
            f"urban_v2_2:curb:ns:{i}",
            (x, 0, 0.12),
            (0.25, 28, 0.14),
            MATS["curb"],
            collection,
            bevel_width=0.015,
        )
    for i, x in enumerate([n * 0.78 for n in range(-4, 5)]):
        cube(
            f"urban_v2_2:crosswalk:north:{i}",
            (x, 4.05, 0.155),
            (0.42, 2.1, 0.014),
            MATS["paint"],
            collection,
            bevel_width=0.003,
        )
        cube(
            f"urban_v2_2:crosswalk:south:{i}",
            (x, -4.05, 0.155),
            (0.42, 2.1, 0.014),
            MATS["paint"],
            collection,
            bevel_width=0.003,
        )
    for i, y in enumerate([n * 0.78 for n in range(-4, 5)]):
        cube(
            f"urban_v2_2:crosswalk:east:{i}",
            (4.05, y, 0.157),
            (2.1, 0.42, 0.014),
            MATS["paint"],
            collection,
            bevel_width=0.003,
        )
        cube(
            f"urban_v2_2:crosswalk:west:{i}",
            (-4.05, y, 0.157),
            (2.1, 0.42, 0.014),
            MATS["paint"],
            collection,
            bevel_width=0.003,
        )
    for i, x in enumerate(range(-12, 13, 4)):
        cube(
            f"urban_v2_2:lane_marker:ew:{i}",
            (x, 0, 0.158),
            (1.6, 0.09, 0.012),
            MATS["yellow_paint"],
            collection,
            bevel_width=0.003,
        )
        cube(
            f"urban_v2_2:lane_marker:ns:{i}",
            (0, x, 0.16),
            (0.09, 1.6, 0.012),
            MATS["yellow_paint"],
            collection,
            bevel_width=0.003,
        )
    for i in range(120):
        x = math.sin(i * 12.989) * 13.0
        y = math.sin(i * 78.233) * 13.0
        if abs(x) < 3.7 or abs(y) < 3.7:
            cube(
                f"urban_v2_2:asphalt_aggregate:{i:03d}",
                (x, y, 0.006),
                (0.045 + (i % 5) * 0.012, 0.025 + (i % 7) * 0.008, 0.008),
                MATS["asphalt_light"],
                collection,
                yaw=i * 0.37,
                bevel_width=0.002,
            )


def add_low_buildings_and_greenery(collection):
    buildings = [
        ("nw", -10.4, 9.2, 4.6, 4.2, 5.8),
        ("ne", 10.0, 9.0, 5.2, 4.4, 6.6),
        ("sw", -10.3, -9.5, 4.8, 4.0, 5.1),
        ("se", 10.7, -9.1, 4.4, 4.2, 6.2),
    ]
    for name, x, y, sx, sy, h in buildings:
        cube(
            f"urban_v2_2:low_building:{name}",
            (x, y, h / 2),
            (sx, sy, h),
            MATS["brick"],
            collection,
            bevel_width=0.035,
        )
        face_y = y - math.copysign(sy / 2 + 0.018, y)
        for floor in range(2, int(h), 2):
            for k in (-1, 1):
                cube(
                    f"urban_v2_2:low_building:{name}:window:{floor}:{k}",
                    (x + k * sx * 0.22, face_y, floor + 0.25),
                    (0.72, 0.024, 0.55),
                    MATS["glass"],
                    collection,
                    bevel_width=0.006,
                )
    for i, (x, y) in enumerate([(-7.5, 6.0), (-6.3, -6.6), (7.4, -6.2), (6.7, 6.3)]):
        cube(
            f"urban_v2_2:grass_patch:{i}",
            (x, y, 0.055),
            (1.8, 1.2, 0.05),
            MATS["grass"],
            collection,
            yaw=0.1 * i,
            bevel_width=0.04,
        )
        for j in range(7):
            angle = j * math.tau / 7
            sphere(
                f"urban_v2_2:shrub:{i}:{j}",
                (x + math.cos(angle) * 0.52, y + math.sin(angle) * 0.34, 0.34),
                (0.18, 0.15, 0.16),
                MATS["leaf"],
                collection,
                segments=16,
            )


def add_signal_assets(collection):
    mast_arm_signal(
        "traffic_light:northwest_mast",
        (-5.7, -5.9),
        math.radians(42),
        collection,
        variant="five",
    )
    mast_arm_signal(
        "traffic_light:southeast_mast",
        (5.9, 5.7),
        math.radians(-138),
        collection,
        variant="horizontal",
    )
    mast_arm_signal(
        "traffic_light:northeast_mast",
        (5.8, -5.8),
        math.radians(132),
        collection,
        variant="standard",
    )
    corner_pedestal(
        "traffic_light:southwest_pedestal",
        (-5.75, 5.65),
        math.radians(-48),
        collection,
        active="green",
    )
    corner_pedestal(
        "traffic_light:northwest_pedestal",
        (-5.95, -5.6),
        math.radians(45),
        collection,
        active="red",
    )
    add_control_cabinet(collection)
    cyl_between(
        "traffic_light:overhead_span_wire",
        (-5.7, -5.9, 4.75),
        (5.9, 5.7, 4.72),
        0.012,
        MATS["dark_metal"],
        collection,
        vertices=10,
    )
    cyl_between(
        "traffic_light:signal_cable_loop",
        (-5.7, -5.9, 4.55),
        (-4.6, -4.5, 4.05),
        0.012,
        MATS["dark_metal"],
        collection,
        vertices=10,
    )


def add_lighting_and_camera():
    bpy.context.scene.world = (
        bpy.data.worlds.new("urban_v2_2_world")
        if not bpy.context.scene.world
        else bpy.context.scene.world
    )
    bpy.context.scene.world.color = (0.62, 0.68, 0.75)
    bpy.ops.object.light_add(
        type="SUN",
        location=(0, 0, 12),
        rotation=(math.radians(45), 0, math.radians(-35)),
    )
    sun = bpy.context.object
    sun.name = "urban_v2_2:late_afternoon_sun"
    sun.data.energy = 2.4
    bpy.ops.object.light_add(type="AREA", location=(-3.5, -6.2, 5.5))
    area = bpy.context.object
    area.name = "urban_v2_2:soft_signal_fill"
    area.data.energy = 230
    area.data.size = 5.0
    bpy.ops.object.camera_add(
        location=(-10.5, -10.0, 4.0), rotation=(math.radians(63), 0, math.radians(-43))
    )
    camera = bpy.context.object
    camera.name = "Camera_traffic_light_orbit"
    camera.data.lens = 28
    bpy.context.scene.camera = camera
    target = Vector((0.15, -0.1, 2.55))
    for frame, angle in ((1, -134), (48, -85), (96, -34)):
        radius = 13.5
        loc = Vector(
            (
                math.cos(math.radians(angle)) * radius,
                math.sin(math.radians(angle)) * radius,
                4.1 + 0.4 * math.sin(math.radians(angle * 2)),
            )
        )
        camera.location = loc
        direction = target - loc
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    for fcurve in camera.animation_data.action.fcurves:
        for key in fcurve.keyframe_points:
            key.interpolation = "BEZIER"


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 64
    scene.frame_start = 1
    scene.frame_end = 96
    scene.frame_set(1)
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.fps = 24
    scene.render.filepath = str(VIDEO_PATH)
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reset_scene()
    build_materials()
    scene_collection = add_collection("urban_v2_2_context_low_buildings")
    signal_collection = add_collection("procedural_traffic_light_assets")
    add_road_scene(scene_collection)
    add_low_buildings_and_greenery(scene_collection)
    add_signal_assets(signal_collection)
    add_lighting_and_camera()
    configure_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_PATH))
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
