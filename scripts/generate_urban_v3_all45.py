"""Generate urban_v3_all45: a standalone realistic residential zone.

The scene intentionally contains only the residential district requested by
prompt-45: one mid-rise apartment, seven low-rise homes, yards, parking,
greenery, utilities and five validation renders.
"""

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


import json
import math
import random
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/urban_v3_all45"
PREFIX = "all45:"
RNG = random.Random(45)


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for datablock in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.collections,
        bpy.data.curves,
    ):
        for item in list(datablock):
            if item.users == 0:
                datablock.remove(item)


def make_collection(name, parent=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def clear_material(name):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    for node in list(mat.node_tree.nodes):
        mat.node_tree.nodes.remove(node)
    return mat


def set_input(node, key, value):
    if key in node.inputs:
        node.inputs[key].default_value = value


def material(name, color, rough=0.68, metallic=0.0, noise=0.0, alpha=1.0):
    mat = clear_material(name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color[:3], alpha)
    set_input(bsdf, "Alpha", alpha)
    set_input(bsdf, "Roughness", rough)
    set_input(bsdf, "Metallic", metallic)
    if noise:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 28.0
        tex.inputs["Detail"].default_value = 9.0
        tex.inputs["Roughness"].default_value = 0.58
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (
            *[max(0, c * (1 - noise)) for c in color[:3]],
            alpha,
        )
        ramp.color_ramp.elements[1].color = (
            *[min(1, c * (1 + noise) + 0.015) for c in color[:3]],
            alpha,
        )
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = min(0.26, noise * 0.85)
        bump.inputs["Distance"].default_value = 0.028
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if alpha < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
        mat.show_transparent_back = True
    return mat


def brick_material(name, color1, color2, mortar, rough=0.8, scale=8.0):
    mat = clear_material(name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (*color1, 1)
    brick.inputs["Color2"].default_value = (*color2, 1)
    brick.inputs["Mortar"].default_value = (*mortar, 1)
    brick.inputs["Scale"].default_value = scale
    brick.inputs["Mortar Size"].default_value = 0.028
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.13
    bump.inputs["Distance"].default_value = 0.018
    set_input(bsdf, "Roughness", rough)
    links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def roof_tile_material(name, c1, c2):
    mat = clear_material(name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (*c1, 1)
    brick.inputs["Color2"].default_value = (*c2, 1)
    brick.inputs["Mortar"].default_value = (0.045, 0.048, 0.048, 1)
    brick.inputs["Scale"].default_value = 4.4
    brick.inputs["Mortar Size"].default_value = 0.025
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 0.18
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.03
    set_input(bsdf, "Roughness", 0.74)
    links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def wood_material(name, c1=(0.17, 0.08, 0.035), c2=(0.39, 0.20, 0.08)):
    mat = clear_material(name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Distortion"].default_value = 8.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.006
    set_input(bsdf, "Roughness", 0.48)
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(wave.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def add_bevel(obj, width=0.01, segments=1):
    if width <= 0:
        return obj
    bevel = obj.modifiers.new(PREFIX + "edge_bevel", "BEVEL")
    bevel.width = width
    bevel.segments = segments
    bevel.harden_normals = True
    obj.modifiers.new(PREFIX + "weighted_normals", "WEIGHTED_NORMAL")
    return obj


def link_to(obj, coll):
    coll.objects.link(obj)
    for existing in list(obj.users_collection):
        if existing is not coll:
            existing.objects.unlink(obj)
    return obj


def box(name, loc, dim, mat, coll, rot=0.0, bevel=0.01, segments=1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=(0, 0, rot))
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dim
    if mat:
        obj.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    add_bevel(obj, bevel, segments)
    return link_to(obj, coll)


def cylinder(
    name, loc, radius, depth, mat, coll, vertices=24, rot=(0, 0, 0), bevel=0.0
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot
    )
    obj = bpy.context.object
    obj.name = PREFIX + name
    if mat:
        obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    add_bevel(obj, bevel, 1)
    return link_to(obj, coll)


def sphere(name, loc, radius, mat, coll, scale=(1, 1, 1), segments=24):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=12, radius=radius, location=loc
    )
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.scale = scale
    if mat:
        obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return link_to(obj, coll)


def beam(name, p1, p2, radius, mat, coll, vertices=18):
    a, b = Vector(p1), Vector(p2)
    mid = (a + b) / 2
    obj = cylinder(
        name, mid, radius, (b - a).length, mat, coll, vertices=vertices, bevel=0.003
    )
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return obj


def poly_prism(name, pts, z, depth, mat, coll, bevel=0.0):
    verts = [(x, y, z) for x, y in pts] + [(x, y, z + depth) for x, y in pts]
    n = len(pts)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    if mat:
        obj.data.materials.append(mat)
    coll.objects.link(obj)
    add_bevel(obj, bevel, 1)
    return obj


def transform_point(origin, yaw, local):
    x, y, z = local
    c, s = math.cos(yaw), math.sin(yaw)
    return (origin[0] + c * x - s * y, origin[1] + s * x + c * y, origin[2] + z)


def local_box(
    name, origin, yaw, local, dim, mat, coll, rot=0.0, bevel=0.01, segments=1
):
    return box(
        name,
        transform_point(origin, yaw, local),
        dim,
        mat,
        coll,
        yaw + rot,
        bevel,
        segments,
    )


def collection_instance(coll_src, name, loc, parent, rot=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(PREFIX + name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = coll_src
    obj.location = loc
    obj.rotation_euler[2] = rot
    obj.scale = scale
    obj["c2w_linked_asset"] = coll_src.name
    parent.objects.link(obj)
    return obj


def make_mats():
    return {
        "ground": material(
            "compact_residential_soil", (0.34, 0.33, 0.29), rough=0.86, noise=0.12
        ),
        "path": material(
            "warm_concrete_paths", (0.55, 0.54, 0.49), rough=0.82, noise=0.08
        ),
        "asphalt": material(
            "fine_grain_asphalt", (0.09, 0.095, 0.095), rough=0.88, noise=0.11
        ),
        "parking_line": material(
            "slightly_worn_parking_line", (0.86, 0.84, 0.72), rough=0.74, noise=0.03
        ),
        "lawn": material(
            "muted_residential_lawn", (0.11, 0.25, 0.09), rough=0.9, noise=0.12
        ),
        "hedge": material("hedge_leaves", (0.04, 0.20, 0.055), rough=0.88, noise=0.15),
        "leaf_a": material("tree_leaf_a", (0.055, 0.24, 0.07), rough=0.86, noise=0.14),
        "leaf_b": material("tree_leaf_b", (0.075, 0.29, 0.09), rough=0.86, noise=0.12),
        "trunk": wood_material("rough_bark", (0.12, 0.07, 0.04), (0.24, 0.15, 0.08)),
        "cream": material(
            "painted_cream_wall", (0.66, 0.63, 0.55), rough=0.83, noise=0.08
        ),
        "warm_gray": material(
            "painted_warm_gray_wall", (0.48, 0.50, 0.48), rough=0.84, noise=0.08
        ),
        "tile_wall": brick_material(
            "small_exterior_tile_wall",
            (0.49, 0.43, 0.36),
            (0.64, 0.58, 0.48),
            (0.27, 0.25, 0.22),
            scale=11.0,
        ),
        "pale_green": material(
            "subtle_pale_green_wall", (0.47, 0.56, 0.48), rough=0.84, noise=0.06
        ),
        "apt_wall": material(
            "apartment_warm_concrete", (0.58, 0.57, 0.51), rough=0.86, noise=0.07
        ),
        "apt_accent": material(
            "apartment_gray_tile_accent", (0.30, 0.33, 0.34), rough=0.74, noise=0.07
        ),
        "apt_plinth": material(
            "apartment_dark_plinth", (0.12, 0.13, 0.13), rough=0.78, noise=0.06
        ),
        "glass": material(
            "slightly_tinted_glass",
            (0.55, 0.72, 0.78),
            rough=0.08,
            metallic=0.0,
            alpha=0.44,
        ),
        "frame": material(
            "dark_bronze_window_frame", (0.05, 0.048, 0.043), rough=0.42, metallic=0.35
        ),
        "white_frame": material(
            "off_white_window_frame",
            (0.78, 0.76, 0.69),
            rough=0.56,
            metallic=0.0,
            noise=0.02,
        ),
        "wood": wood_material("wooden_door_and_trim"),
        "roof_blue": roof_tile_material(
            "blue_gray_roof_tile", (0.14, 0.20, 0.23), (0.29, 0.36, 0.39)
        ),
        "roof_brown": roof_tile_material(
            "brown_ceramic_roof_tile", (0.26, 0.12, 0.06), (0.43, 0.23, 0.12)
        ),
        "roof_metal": material(
            "standing_seam_metal_roof",
            (0.22, 0.27, 0.28),
            rough=0.56,
            metallic=0.28,
            noise=0.04,
        ),
        "fascia": material(
            "painted_roof_fascia", (0.08, 0.10, 0.11), rough=0.62, metallic=0.05
        ),
        "gutter": material(
            "galvanized_gutter", (0.18, 0.19, 0.18), rough=0.42, metallic=0.55
        ),
        "concrete": material(
            "poured_concrete", (0.48, 0.47, 0.43), rough=0.86, noise=0.08
        ),
        "stone": material("low_wall_stone", (0.43, 0.41, 0.36), rough=0.84, noise=0.10),
        "metal": material(
            "dark_powder_coated_metal", (0.025, 0.027, 0.027), rough=0.38, metallic=0.62
        ),
        "ac": material(
            "off_white_ac_unit",
            (0.78, 0.76, 0.70),
            rough=0.58,
            metallic=0.05,
            noise=0.03,
        ),
        "utility": material(
            "utility_box_plastic", (0.50, 0.54, 0.50), rough=0.62, noise=0.03
        ),
        "mail": material(
            "mailbox_red_brown",
            (0.38, 0.08, 0.04),
            rough=0.52,
            metallic=0.10,
            noise=0.02,
        ),
        "trash": material(
            "trash_bin_blue_gray", (0.11, 0.18, 0.22), rough=0.64, metallic=0.05
        ),
        "car_dark": material(
            "compact_car_dark_gray", (0.08, 0.09, 0.10), rough=0.40, metallic=0.25
        ),
        "car_blue": material(
            "compact_car_desaturated_blue",
            (0.10, 0.18, 0.25),
            rough=0.42,
            metallic=0.22,
        ),
        "light": material("warm_window_light", (1.0, 0.63, 0.29), rough=0.35),
    }


def make_asset_masters(M):
    masters = {}

    win = bpy.data.collections.new(PREFIX + "MASTER_window_recessed_bronze")
    box(
        "master_window_recess_shadow",
        (0, 0.035, 0),
        (1.38, 0.08, 1.38),
        M["apt_plinth"],
        win,
        bevel=0.004,
    )
    box(
        "master_window_frame",
        (0, -0.005, 0),
        (1.22, 0.10, 1.18),
        M["frame"],
        win,
        bevel=0.006,
    )
    box(
        "master_window_glass",
        (0, -0.065, 0),
        (0.92, 0.03, 0.88),
        M["glass"],
        win,
        bevel=0.003,
    )
    box(
        "master_window_mullion_v",
        (0, -0.095, 0),
        (0.055, 0.045, 0.92),
        M["frame"],
        win,
        bevel=0.002,
    )
    box(
        "master_window_mullion_h",
        (0, -0.097, 0),
        (0.96, 0.045, 0.050),
        M["frame"],
        win,
        bevel=0.002,
    )
    box(
        "master_window_sill",
        (0, -0.12, -0.72),
        (1.40, 0.20, 0.08),
        M["stone"],
        win,
        bevel=0.006,
    )
    masters["window"] = win

    win2 = bpy.data.collections.new(PREFIX + "MASTER_window_white_tall")
    box(
        "master_tall_shadow",
        (0, 0.035, 0),
        (1.10, 0.08, 1.72),
        M["apt_plinth"],
        win2,
        bevel=0.004,
    )
    box(
        "master_tall_frame",
        (0, -0.010, 0),
        (0.96, 0.10, 1.54),
        M["white_frame"],
        win2,
        bevel=0.006,
    )
    box(
        "master_tall_glass",
        (0, -0.065, 0),
        (0.72, 0.03, 1.25),
        M["glass"],
        win2,
        bevel=0.003,
    )
    box(
        "master_tall_sill",
        (0, -0.12, -0.88),
        (1.14, 0.18, 0.07),
        M["stone"],
        win2,
        bevel=0.005,
    )
    masters["window_tall"] = win2

    door = bpy.data.collections.new(PREFIX + "MASTER_lowrise_entry_door")
    box(
        "master_door_recess",
        (0, 0.05, 0.02),
        (1.36, 0.12, 2.34),
        M["apt_plinth"],
        door,
        bevel=0.006,
    )
    box(
        "master_door_leaf",
        (0, -0.03, 0.00),
        (1.03, 0.07, 2.05),
        M["wood"],
        door,
        bevel=0.008,
    )
    box(
        "master_door_panel_low",
        (0, -0.075, -0.42),
        (0.74, 0.025, 0.48),
        M["frame"],
        door,
        bevel=0.003,
    )
    box(
        "master_door_panel_high",
        (0, -0.075, 0.36),
        (0.74, 0.025, 0.48),
        M["frame"],
        door,
        bevel=0.003,
    )
    box(
        "master_door_glass",
        (0, -0.087, 0.78),
        (0.62, 0.022, 0.48),
        M["glass"],
        door,
        bevel=0.003,
    )
    cylinder(
        "master_door_handle",
        (0.34, -0.13, 0.03),
        0.035,
        0.16,
        M["metal"],
        door,
        vertices=16,
        rot=(math.pi / 2, 0, 0),
    )
    masters["door"] = door

    balcony = bpy.data.collections.new(PREFIX + "MASTER_apartment_balcony")
    box(
        "master_balcony_slab",
        (0, -0.44, -0.70),
        (1.95, 1.00, 0.12),
        M["concrete"],
        balcony,
        bevel=0.006,
    )
    box(
        "master_balcony_front_rail",
        (0, -0.93, -0.18),
        (1.96, 0.055, 0.76),
        M["metal"],
        balcony,
        bevel=0.004,
    )
    for x in (-0.82, -0.41, 0, 0.41, 0.82):
        box(
            f"master_balcony_picket_{x:.2f}",
            (x, -0.93, -0.22),
            (0.035, 0.060, 0.68),
            M["metal"],
            balcony,
            bevel=0.002,
        )
    box(
        "master_balcony_top_rail",
        (0, -0.94, 0.20),
        (2.06, 0.075, 0.060),
        M["metal"],
        balcony,
        bevel=0.004,
    )
    box(
        "master_balcony_side_l",
        (-0.97, -0.48, -0.18),
        (0.055, 0.86, 0.70),
        M["metal"],
        balcony,
        bevel=0.003,
    )
    box(
        "master_balcony_side_r",
        (0.97, -0.48, -0.18),
        (0.055, 0.86, 0.70),
        M["metal"],
        balcony,
        bevel=0.003,
    )
    masters["balcony"] = balcony

    ac = bpy.data.collections.new(PREFIX + "MASTER_ac_outdoor_unit")
    box("master_ac_body", (0, 0, 0), (0.82, 0.30, 0.48), M["ac"], ac, bevel=0.018)
    for i, z in enumerate((-0.12, 0.0, 0.12)):
        box(
            f"master_ac_louver_{i}",
            (0, -0.17, z),
            (0.72, 0.025, 0.030),
            M["metal"],
            ac,
            bevel=0.001,
        )
    cylinder(
        "master_ac_fan",
        (0.22, -0.19, 0.02),
        0.15,
        0.026,
        M["metal"],
        ac,
        vertices=24,
        rot=(math.pi / 2, 0, 0),
    )
    masters["ac"] = ac

    utility = bpy.data.collections.new(PREFIX + "MASTER_utility_cluster")
    box(
        "master_utility_meter",
        (0, 0, 0.58),
        (0.45, 0.16, 0.55),
        M["utility"],
        utility,
        bevel=0.010,
    )
    box(
        "master_utility_panel",
        (0.38, 0, 0.46),
        (0.30, 0.13, 0.38),
        M["ac"],
        utility,
        bevel=0.008,
    )
    cylinder(
        "master_utility_pipe",
        (-0.35, 0, 0.75),
        0.025,
        1.30,
        M["gutter"],
        utility,
        vertices=12,
    )
    masters["utility"] = utility

    mailbox = bpy.data.collections.new(PREFIX + "MASTER_mailbox")
    cylinder(
        "master_mailbox_post",
        (0, 0, 0.45),
        0.035,
        0.90,
        M["metal"],
        mailbox,
        vertices=12,
    )
    box(
        "master_mailbox_box",
        (0, 0, 1.02),
        (0.58, 0.22, 0.30),
        M["mail"],
        mailbox,
        bevel=0.035,
        segments=3,
    )
    box(
        "master_mailbox_slot",
        (0, -0.12, 1.05),
        (0.42, 0.012, 0.035),
        M["metal"],
        mailbox,
        bevel=0.001,
    )
    masters["mailbox"] = mailbox

    bike = bpy.data.collections.new(PREFIX + "MASTER_bicycle_rack")
    for i, x in enumerate((-0.55, 0.0, 0.55)):
        beam(
            f"master_bike_u_left_{i}",
            (x - 0.18, 0, 0.08),
            (x - 0.18, 0, 0.65),
            0.025,
            M["metal"],
            bike,
        )
        beam(
            f"master_bike_u_right_{i}",
            (x + 0.18, 0, 0.08),
            (x + 0.18, 0, 0.65),
            0.025,
            M["metal"],
            bike,
        )
        beam(
            f"master_bike_top_{i}",
            (x - 0.18, 0, 0.65),
            (x + 0.18, 0, 0.65),
            0.025,
            M["metal"],
            bike,
        )
    masters["bike_rack"] = bike

    shrub = bpy.data.collections.new(PREFIX + "MASTER_shrub_irregular")
    for i in range(6):
        sphere(
            f"master_shrub_lobe_{i}",
            (
                RNG.uniform(-0.25, 0.25),
                RNG.uniform(-0.18, 0.18),
                0.26 + RNG.uniform(-0.05, 0.06),
            ),
            RNG.uniform(0.22, 0.36),
            M["hedge"],
            shrub,
            scale=(1.35, 0.85, 0.72),
            segments=16,
        )
    masters["shrub"] = shrub

    for key, leaf_mat, scale in (
        ("tree_a", M["leaf_a"], 1.0),
        ("tree_b", M["leaf_b"], 0.85),
    ):
        tree = bpy.data.collections.new(PREFIX + "MASTER_" + key)
        cylinder(
            "master_tree_trunk",
            (0, 0, 1.25 * scale),
            0.12 * scale,
            2.5 * scale,
            M["trunk"],
            tree,
            vertices=14,
            bevel=0.01,
        )
        for i, (x, y, z, r) in enumerate(
            [
                (-0.35, 0.08, 2.55, 0.80),
                (0.33, -0.10, 2.70, 0.78),
                (0, 0.25, 3.05, 0.72),
                (0.06, -0.28, 3.20, 0.62),
            ]
        ):
            sphere(
                f"master_tree_canopy_{i}",
                (x * scale, y * scale, z * scale),
                r * scale,
                leaf_mat,
                tree,
                scale=(1.15, 0.95, 0.82),
                segments=20,
            )
        masters[key] = tree

    return masters


def roof_mesh(
    name,
    origin,
    yaw,
    w,
    d,
    z,
    roof_type,
    mat,
    coll,
    overhang=0.42,
    rise=1.15,
    thickness=0.18,
):
    x0, x1 = -w / 2 - overhang, w / 2 + overhang
    y0, y1 = -d / 2 - overhang, d / 2 + overhang
    verts = []
    faces = []

    def add_local(local_verts, local_faces):
        start = len(verts)
        for v in local_verts:
            verts.append(transform_point(origin, yaw, v))
        for face in local_faces:
            faces.append(tuple(start + i for i in face))

    if roof_type == "gable":
        ridge_y = 0
        top = [
            (x0, y0, z),
            (x1, y0, z),
            (x1, ridge_y, z + rise),
            (x0, ridge_y, z + rise),
            (x0, ridge_y, z + rise),
            (x1, ridge_y, z + rise),
            (x1, y1, z),
            (x0, y1, z),
        ]
        bot = [(x, y, zz - thickness) for x, y, zz in top]
        add_local(
            top + bot,
            [
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (8, 11, 10, 9),
                (12, 15, 14, 13),
                (0, 8, 9, 1),
                (1, 9, 10, 2),
                (6, 14, 15, 7),
                (7, 15, 12, 4),
                (0, 3, 11, 8),
                (5, 6, 14, 13),
            ],
        )
        ridge_a = transform_point(origin, yaw, (x0 + 0.18, 0, z + rise + 0.04))
        ridge_b = transform_point(origin, yaw, (x1 - 0.18, 0, z + rise + 0.04))
    elif roof_type == "hip":
        ridge_len = max(0.8, w - d)
        top = [
            (x0, y0, z),
            (x1, y0, z),
            (x1, y1, z),
            (x0, y1, z),
            (-ridge_len / 2, 0, z + rise),
            (ridge_len / 2, 0, z + rise),
        ]
        bot = [(x, y, zz - thickness) for x, y, zz in top]
        add_local(
            top + bot,
            [
                (0, 1, 5, 4),
                (2, 3, 4, 5),
                (3, 0, 4),
                (1, 2, 5),
                (6, 10, 11, 7),
                (8, 11, 10, 9),
                (9, 10, 6),
                (7, 11, 8),
                (0, 6, 7, 1),
                (2, 8, 9, 3),
                (0, 3, 9, 6),
                (1, 7, 8, 2),
            ],
        )
        ridge_a = transform_point(origin, yaw, (-ridge_len / 2, 0, z + rise + 0.04))
        ridge_b = transform_point(origin, yaw, (ridge_len / 2, 0, z + rise + 0.04))
    else:
        # Main hip roof with a cross gable over the entrance side.
        ridge_len = max(1.0, w - d * 0.6)
        top = [
            (x0, y0, z),
            (x1, y0, z),
            (x1, y1, z),
            (x0, y1, z),
            (-ridge_len / 2, 0, z + rise),
            (ridge_len / 2, 0, z + rise),
        ]
        bot = [(x, y, zz - thickness) for x, y, zz in top]
        add_local(
            top + bot,
            [
                (0, 1, 5, 4),
                (2, 3, 4, 5),
                (3, 0, 4),
                (1, 2, 5),
                (6, 10, 11, 7),
                (8, 11, 10, 9),
                (9, 10, 6),
                (7, 11, 8),
            ],
        )
        gx0, gx1 = -1.55, 1.55
        gy0, gy1 = y0 - 0.16, 0.55
        gz = z + 0.06
        cross = [
            (gx0, gy0, gz),
            (gx1, gy0, gz),
            (0, gy0, gz + 0.78),
            (gx0, gy1, gz),
            (gx1, gy1, gz),
            (0, gy1, gz + 0.78),
        ]
        cross_bot = [(x, y, zz - thickness * 0.65) for x, y, zz in cross]
        add_local(
            cross + cross_bot,
            [
                (0, 1, 2),
                (3, 5, 4),
                (0, 3, 4, 1),
                (0, 2, 5, 3),
                (1, 4, 5, 2),
                (6, 8, 7),
                (9, 10, 11),
            ],
        )
        ridge_a = transform_point(origin, yaw, (-ridge_len / 2, 0, z + rise + 0.04))
        ridge_b = transform_point(origin, yaw, (ridge_len / 2, 0, z + rise + 0.04))

    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    add_bevel(obj, 0.006, 1)

    beam(name + "_ridge_cap", ridge_a, ridge_b, 0.055, MATS["fascia"], coll)
    for ly in (y0 + 0.05, y1 - 0.05):
        p0 = transform_point(origin, yaw, (x0 + 0.12, ly, z - 0.04))
        p1 = transform_point(origin, yaw, (x1 - 0.12, ly, z - 0.04))
        beam(name + f"_gutter_{ly:.1f}", p0, p1, 0.042, MATS["gutter"], coll)
        for lx in (x0 + 0.38, x1 - 0.38):
            a = transform_point(origin, yaw, (lx, ly, z - 0.05))
            b = transform_point(origin, yaw, (lx, ly, 0.62))
            beam(
                name + f"_downspout_{lx:.1f}_{ly:.1f}",
                a,
                b,
                0.025,
                MATS["gutter"],
                coll,
            )

    rows = 7 if roof_type != "gable" else 8
    for i in range(rows):
        t = (i + 1) / (rows + 1)
        for side, sy0, sy1 in (("front", y0, 0), ("back", y1, 0)):
            yy = sy0 + (sy1 - sy0) * t
            zz = z + rise * (1 - abs(yy) / max(abs(y0), abs(y1))) * 0.88 + 0.025
            local_box(
                name + f"_tile_row_{side}_{i}",
                origin,
                yaw,
                (0, yy, zz),
                (w + overhang * 1.1, 0.035, 0.030),
                MATS["fascia"],
                coll,
                bevel=0.002,
            )
    return obj


def place_wall_instance(
    master, name, origin, yaw, lx, ly, lz, coll, face="front", scale=(1, 1, 1)
):
    extra = 0.0 if face in ("front", "back") else math.pi / 2
    return collection_instance(
        master,
        name,
        transform_point(origin, yaw, (lx, ly, lz)),
        coll,
        yaw + extra,
        scale,
    )


def add_lowrise_house(name, origin, yaw, params, M, A, root):
    coll = make_collection("house_" + name, root)
    w, d = params["w"], params["d"]
    floors = params["floors"]
    h = 2.9 * floors
    wall = M[params["wall"]]
    roof_mat = M[params["roof_mat"]]

    local_box(
        name + "_body_main",
        origin,
        yaw,
        (0, 0, h / 2),
        (w, d, h),
        wall,
        coll,
        bevel=0.020,
        segments=2,
    )
    if params.get("side_wing"):
        local_box(
            name + "_body_side_wing",
            origin,
            yaw,
            (w * 0.18, d * 0.48, 1.45),
            (w * 0.52, d * 0.45, 2.90),
            wall,
            coll,
            bevel=0.018,
            segments=2,
        )
    local_box(
        name + "_foundation",
        origin,
        yaw,
        (0, 0, 0.18),
        (w + 0.35, d + 0.35, 0.36),
        M["stone"],
        coll,
        bevel=0.012,
    )

    roof_mesh(
        name + "_" + params["roof"],
        origin,
        yaw,
        w,
        d,
        h + 0.02,
        params["roof"],
        roof_mat,
        coll,
        overhang=0.48,
        rise=params["rise"],
    )

    front_y = -d / 2 - 0.02
    back_y = d / 2 + 0.02
    door_x = params["door_x"]
    place_wall_instance(
        A["door"],
        name + "_entry_door",
        origin,
        yaw,
        door_x,
        front_y - 0.06,
        1.15,
        coll,
        "front",
    )
    local_box(
        name + "_entry_platform",
        origin,
        yaw,
        (door_x, front_y - 0.75, 0.14),
        (1.72, 1.05, 0.26),
        M["concrete"],
        coll,
        bevel=0.014,
    )
    local_box(
        name + "_entry_step",
        origin,
        yaw,
        (door_x, front_y - 1.36, 0.08),
        (1.92, 0.36, 0.16),
        M["stone"],
        coll,
        bevel=0.010,
    )
    local_box(
        name + "_entry_canopy_slab",
        origin,
        yaw,
        (door_x, front_y - 0.36, 2.44),
        (1.72, 1.10, 0.13),
        M["roof_metal"],
        coll,
        bevel=0.010,
    )
    for sx in (-0.68, 0.68):
        beam(
            name + f"_canopy_brace_{sx}",
            transform_point(origin, yaw, (door_x + sx, front_y - 0.18, 2.35)),
            transform_point(origin, yaw, (door_x + sx * 0.65, front_y - 0.88, 2.05)),
            0.026,
            M["metal"],
            coll,
        )

    win_positions = params["windows"]
    for i, (lx, face, z, scale) in enumerate(win_positions):
        if face == "front":
            ly = front_y - 0.055
        elif face == "back":
            ly = back_y + 0.055
        elif face == "left":
            ly = -w / 2 - 0.055
        else:
            ly = w / 2 + 0.055
        if face in ("left", "right"):
            place_wall_instance(
                A["window"],
                name + f"_window_{i}",
                origin,
                yaw,
                ly,
                lx,
                z,
                coll,
                "side",
                scale,
            )
        else:
            master = A["window_tall"] if scale[2] > 1.05 else A["window"]
            place_wall_instance(
                master, name + f"_window_{i}", origin, yaw, lx, ly, z, coll, face, scale
            )

    # Exterior services and AC units are tied to functional wall locations.
    collection_instance(
        A["ac"],
        name + "_ac_living",
        transform_point(origin, yaw, (w / 2 + 0.24, -0.8, 1.38)),
        coll,
        yaw + math.pi / 2,
        (0.9, 0.9, 0.9),
    )
    if floors == 2:
        collection_instance(
            A["ac"],
            name + "_ac_second_floor",
            transform_point(origin, yaw, (-w / 2 - 0.24, 0.9, 4.15)),
            coll,
            yaw + math.pi / 2,
            (0.82, 0.82, 0.82),
        )
    collection_instance(
        A["utility"],
        name + "_utility_cluster",
        transform_point(origin, yaw, (w / 2 + 0.26, d * 0.22, 0)),
        coll,
        yaw + math.pi / 2,
    )

    # Private yard and enclosure.
    yard = params["yard"]
    yx0, yx1, yy0, yy1 = yard
    pts = [
        transform_point(origin, yaw, (yx0, yy0, 0.025))[:2],
        transform_point(origin, yaw, (yx1, yy0, 0.025))[:2],
        transform_point(origin, yaw, (yx1, yy1, 0.025))[:2],
        transform_point(origin, yaw, (yx0, yy1, 0.025))[:2],
    ]
    poly_prism(name + "_private_lawn", pts, 0.025, 0.035, M["lawn"], coll, bevel=0.012)
    fence_z = 0.55
    for seg, p0, p1 in (
        ("front", (yx0, yy0), (yx1, yy0)),
        ("back", (yx0, yy1), (yx1, yy1)),
        ("left", (yx0, yy0), (yx0, yy1)),
        ("right", (yx1, yy0), (yx1, yy1)),
    ):
        if seg == "front" and abs(door_x) < max(abs(yx0), abs(yx1)):
            continue
        wp0 = transform_point(origin, yaw, (p0[0], p0[1], fence_z))
        wp1 = transform_point(origin, yaw, (p1[0], p1[1], fence_z))
        beam(
            name + "_low_fence_" + seg,
            wp0,
            wp1,
            0.045,
            M["metal"] if params["fence"] == "metal" else M["stone"],
            coll,
            vertices=12,
        )
        for t in [0.2, 0.4, 0.6, 0.8]:
            lx = p0[0] + (p1[0] - p0[0]) * t
            ly = p0[1] + (p1[1] - p0[1]) * t
            local_box(
                name + f"_fence_post_{seg}_{t}",
                origin,
                yaw,
                (lx, ly, fence_z - 0.18),
                (0.10, 0.10, 0.72),
                M["metal"],
                coll,
                bevel=0.004,
            )

    collection_instance(
        A["mailbox"],
        name + "_mailbox",
        transform_point(origin, yaw, (door_x - 1.05, front_y - 1.85, 0)),
        coll,
        yaw,
    )
    for i, (sx, sy, sc) in enumerate(params["shrubs"]):
        collection_instance(
            A["shrub"],
            name + f"_shrub_{i}",
            transform_point(origin, yaw, (sx, sy, 0.04)),
            coll,
            yaw + RNG.uniform(-0.4, 0.4),
            (sc, sc, sc),
        )

    if params.get("carport"):
        cx = -w / 2 - 1.55
        cy = 0.8
        local_box(
            name + "_carport_slab",
            origin,
            yaw,
            (cx, cy, 2.22),
            (2.35, 4.05, 0.13),
            M["roof_metal"],
            coll,
            bevel=0.008,
        )
        for sx in (-1.02, 1.02):
            for sy in (-1.74, 1.74):
                local_box(
                    name + f"_carport_post_{sx}_{sy}",
                    origin,
                    yaw,
                    (cx + sx, cy + sy, 1.08),
                    (0.09, 0.09, 2.16),
                    M["metal"],
                    coll,
                    bevel=0.004,
                )
        local_box(
            name + "_parking_pad",
            origin,
            yaw,
            (cx, cy, 0.035),
            (2.70, 4.35, 0.07),
            M["asphalt"],
            coll,
            bevel=0.006,
        )

    obj_count = len(coll.all_objects)
    print(
        f"[all45] lowrise {name}: floors={floors} roof={params['roof']} objects={obj_count}",
        flush=True,
    )
    return coll


def add_apartment(origin, yaw, M, A, root):
    coll = make_collection("midrise_apartment", root)
    w, d, floors, floor_h = 21.5, 11.6, 6, 2.85
    h = floors * floor_h
    local_box(
        "apartment_main_mass",
        origin,
        yaw,
        (0, 0, h / 2),
        (w, d, h),
        M["apt_wall"],
        coll,
        bevel=0.025,
        segments=2,
    )
    local_box(
        "apartment_plinth",
        origin,
        yaw,
        (0, 0, 0.38),
        (w + 0.50, d + 0.42, 0.76),
        M["apt_plinth"],
        coll,
        bevel=0.014,
    )
    local_box(
        "apartment_stair_core",
        origin,
        yaw,
        (-w / 2 + 2.2, d / 2 + 0.16, h / 2),
        (3.5, 0.42, h - 0.8),
        M["apt_accent"],
        coll,
        bevel=0.010,
    )
    local_box(
        "apartment_side_recess",
        origin,
        yaw,
        (w / 2 - 1.4, -d / 2 - 0.10, h / 2 + 0.25),
        (2.2, 0.36, h - 1.0),
        M["apt_accent"],
        coll,
        bevel=0.010,
    )

    for floor in range(floors + 1):
        z = floor * floor_h + 0.05
        local_box(
            f"apartment_floor_band_{floor}",
            origin,
            yaw,
            (0, -d / 2 - 0.065, z),
            (w + 0.12, 0.13, 0.085),
            M["stone"],
            coll,
            bevel=0.003,
        )

    front_y = -d / 2 - 0.08
    back_y = d / 2 + 0.08
    x_cols = [-7.6, -4.2, -0.8, 2.6, 6.2, 8.8]
    for floor in range(floors):
        z = 1.42 + floor * floor_h
        for j, lx in enumerate(x_cols):
            if floor == 0 and lx in (-0.8, 2.6):
                continue
            if j in (1, 3, 4) and floor > 0:
                # Balcony door: wall -> recess -> door frame/glass -> physical slab/rail.
                local_box(
                    f"apt_balcony_door_recess_{floor}_{j}",
                    origin,
                    yaw,
                    (lx, front_y + 0.01, z),
                    (1.24, 0.12, 1.90),
                    M["apt_plinth"],
                    coll,
                    bevel=0.004,
                )
                collection_instance(
                    A["window_tall"],
                    f"apt_balcony_door_{floor}_{j}",
                    transform_point(origin, yaw, (lx, front_y - 0.06, z + 0.12)),
                    coll,
                    yaw,
                )
                collection_instance(
                    A["balcony"],
                    f"apt_balcony_{floor}_{j}",
                    transform_point(origin, yaw, (lx, front_y - 0.28, z)),
                    coll,
                    yaw,
                )
                if (floor + j) % 2 == 0:
                    collection_instance(
                        A["ac"],
                        f"apt_balcony_ac_{floor}_{j}",
                        transform_point(
                            origin, yaw, (lx + 0.80, front_y - 0.72, z - 0.55)
                        ),
                        coll,
                        yaw,
                        (0.68, 0.68, 0.68),
                    )
            else:
                collection_instance(
                    A["window"],
                    f"apt_front_window_{floor}_{j}",
                    transform_point(origin, yaw, (lx, front_y - 0.04, z)),
                    coll,
                    yaw,
                    (0.84, 0.88, 0.88),
                )
                if floor in (1, 4) and j in (0, 5):
                    collection_instance(
                        A["ac"],
                        f"apt_wall_ac_{floor}_{j}",
                        transform_point(
                            origin, yaw, (lx + 0.88, front_y - 0.13, z - 0.50)
                        ),
                        coll,
                        yaw,
                        (0.58, 0.58, 0.58),
                    )

        # Back facade has smaller corridor windows.
        for j, lx in enumerate((-7.4, -4.8, -1.1, 1.9, 5.1, 8.0)):
            collection_instance(
                A["window"],
                f"apt_back_corridor_window_{floor}_{j}",
                transform_point(origin, yaw, (lx, back_y + 0.04, z)),
                coll,
                yaw + math.pi,
                (0.62, 0.72, 0.78),
            )

    # Side staircase slot windows.
    for floor in range(floors):
        z = 1.45 + floor * floor_h
        collection_instance(
            A["window_tall"],
            f"apt_side_stair_window_{floor}",
            transform_point(origin, yaw, (-w / 2 - 0.06, d * 0.21, z)),
            coll,
            yaw + math.pi / 2,
            (0.72, 0.72, 0.92),
        )

    # Entrance composition.
    local_box(
        "apt_entry_recess",
        origin,
        yaw,
        (0.8, front_y + 0.02, 1.24),
        (3.15, 0.18, 2.28),
        M["apt_plinth"],
        coll,
        bevel=0.006,
    )
    local_box(
        "apt_entry_left_glass",
        origin,
        yaw,
        (0.22, front_y - 0.08, 1.17),
        (0.92, 0.055, 1.82),
        M["glass"],
        coll,
        bevel=0.004,
    )
    local_box(
        "apt_entry_right_glass",
        origin,
        yaw,
        (1.35, front_y - 0.08, 1.17),
        (0.92, 0.055, 1.82),
        M["glass"],
        coll,
        bevel=0.004,
    )
    local_box(
        "apt_entry_canopy",
        origin,
        yaw,
        (0.78, front_y - 0.62, 2.56),
        (3.80, 1.28, 0.16),
        M["roof_metal"],
        coll,
        bevel=0.010,
    )
    for sx in (-1.05, 2.60):
        local_box(
            f"apt_canopy_post_{sx}",
            origin,
            yaw,
            (sx, front_y - 1.12, 1.28),
            (0.09, 0.09, 2.45),
            M["metal"],
            coll,
            bevel=0.004,
        )

    # Roof parapet, trim, HVAC, vents and drainage.
    local_box(
        "apt_roof_membrane",
        origin,
        yaw,
        (0, 0, h + 0.12),
        (w + 0.16, d + 0.12, 0.18),
        M["roof_metal"],
        coll,
        bevel=0.006,
    )
    local_box(
        "apt_parapet_front",
        origin,
        yaw,
        (0, -d / 2 - 0.02, h + 0.62),
        (w + 0.42, 0.26, 0.96),
        M["fascia"],
        coll,
        bevel=0.008,
    )
    local_box(
        "apt_parapet_back",
        origin,
        yaw,
        (0, d / 2 + 0.02, h + 0.62),
        (w + 0.42, 0.26, 0.96),
        M["fascia"],
        coll,
        bevel=0.008,
    )
    local_box(
        "apt_parapet_left",
        origin,
        yaw,
        (-w / 2 - 0.02, 0, h + 0.62),
        (0.26, d + 0.42, 0.96),
        M["fascia"],
        coll,
        bevel=0.008,
    )
    local_box(
        "apt_parapet_right",
        origin,
        yaw,
        (w / 2 + 0.02, 0, h + 0.62),
        (0.26, d + 0.42, 0.96),
        M["fascia"],
        coll,
        bevel=0.008,
    )
    for i, (lx, ly, sx, sy) in enumerate(
        [
            (-5.2, -1.8, 1.6, 1.1),
            (-1.3, 2.2, 1.2, 1.0),
            (3.4, -0.9, 1.4, 1.25),
            (6.2, 2.8, 1.0, 0.9),
        ]
    ):
        local_box(
            f"apt_roof_hvac_{i}",
            origin,
            yaw,
            (lx, ly, h + 0.78),
            (sx, sy, 0.62),
            M["apt_accent"],
            coll,
            bevel=0.012,
        )
        cylinder(
            f"apt_roof_vent_{i}",
            transform_point(origin, yaw, (lx + sx * 0.34, ly, h + 1.22)),
            0.16,
            0.55,
            M["gutter"],
            coll,
            vertices=18,
            bevel=0.004,
        )
    for lx in (-w / 2 - 0.17, w / 2 + 0.17):
        for ly in (-d / 2 + 1.0, d / 2 - 1.0):
            beam(
                f"apt_vertical_drain_{lx:.1f}_{ly:.1f}",
                transform_point(origin, yaw, (lx, ly, h + 0.16)),
                transform_point(origin, yaw, (lx, ly, 0.42)),
                0.030,
                M["gutter"],
                coll,
            )

    # Shared entry court, mailboxes and bicycle parking.
    local_box(
        "apt_entry_paving",
        origin,
        yaw,
        (0.9, front_y - 2.20, 0.045),
        (8.8, 3.2, 0.09),
        M["path"],
        coll,
        bevel=0.008,
    )
    local_box(
        "apt_mailbox_bank",
        origin,
        yaw,
        (-2.45, front_y - 1.08, 0.86),
        (1.55, 0.22, 1.14),
        M["mail"],
        coll,
        bevel=0.010,
    )
    collection_instance(
        A["bike_rack"],
        "apt_bicycle_rack",
        transform_point(origin, yaw, (4.35, front_y - 1.42, 0)),
        coll,
        yaw,
        (1.2, 1.2, 1.2),
    )
    print(
        f"[all45] apartment: floors={floors} objects={len(coll.all_objects)}",
        flush=True,
    )
    return coll


def add_site_environment(M, A, root):
    site = make_collection("residential_site", root)
    outline = [
        (-32, -23),
        (-4, -25),
        (25, -17),
        (32, 6),
        (21, 25),
        (-10, 27),
        (-33, 16),
        (-38, -8),
    ]
    poly_prism(
        "irregular_residential_ground",
        outline,
        -0.08,
        0.10,
        M["ground"],
        site,
        bevel=0.04,
    )
    poly_prism(
        "shared_courtyard_lawn",
        [(-5, -8), (8, -10), (15, 0), (12, 9), (-2, 12), (-11, 3)],
        0.012,
        0.035,
        M["lawn"],
        site,
        bevel=0.02,
    )
    # Internal paths connect entrances, rather than forming a grid.
    paths = [
        ((-17, -7), (-4, -3), 2.1),
        ((-4, -3), (10, 2), 1.6),
        ((10, 2), (22, 8), 1.45),
        ((-5, -3), (-13, 13), 1.35),
        ((4, -4), (10, -17), 1.20),
        ((-14, -7), (-25, -15), 1.20),
    ]
    for i, (p0, p1, width) in enumerate(paths):
        a, b = Vector((p0[0], p0[1], 0.035)), Vector((p1[0], p1[1], 0.035))
        mid = (a + b) / 2
        length = (b - a).length
        box(
            f"internal_path_{i}",
            mid,
            (length, width, 0.06),
            M["path"],
            site,
            rot=math.atan2(b.y - a.y, b.x - a.x),
            bevel=0.020,
        )

    # Parking courts are close to buildings but leave entries clear.
    parking = [
        (-24, -19, 10.0, 4.8, -0.16),
        (18, -12, 8.3, 4.5, 0.22),
        (21, 14, 7.2, 4.2, -0.45),
    ]
    for i, (cx, cy, w, d, rot) in enumerate(parking):
        box(
            f"parking_pad_{i}",
            (cx, cy, 0.025),
            (w, d, 0.05),
            M["asphalt"],
            site,
            rot=rot,
            bevel=0.012,
        )
        for j in range(3):
            xoff = -w / 2 + (j + 1) * w / 3
            c, s = math.cos(rot), math.sin(rot)
            loc = (cx + c * xoff, cy + s * xoff, 0.065)
            box(
                f"parking_space_line_{i}_{j}",
                loc,
                (0.055, d - 0.55, 0.012),
                M["parking_line"],
                site,
                rot=rot + math.pi / 2,
                bevel=0.0,
            )

    # Simple compact cars on selected spaces.
    for i, (cx, cy, rot, mat_key) in enumerate(
        [
            (-26.5, -19.2, -0.16, "car_dark"),
            (19.0, -12.8, 0.22, "car_blue"),
            (21.7, 14.4, -0.45, "car_dark"),
        ]
    ):
        box(
            f"compact_car_body_{i}",
            (cx, cy, 0.48),
            (2.05, 3.55, 0.78),
            M[mat_key],
            site,
            rot=rot + math.pi / 2,
            bevel=0.12,
            segments=4,
        )
        box(
            f"compact_car_cabin_{i}",
            (cx, cy + 0.08, 1.05),
            (1.58, 1.60, 0.58),
            M["glass"],
            site,
            rot=rot + math.pi / 2,
            bevel=0.08,
            segments=3,
        )

    # Trash and utility area belongs near apartment/service edge, not scattered.
    box(
        "trash_collection_pad",
        (-28.4, -10.5, 0.04),
        (2.6, 1.4, 0.08),
        M["concrete"],
        site,
        rot=-0.16,
        bevel=0.008,
    )
    for i in range(3):
        box(
            f"trash_bin_{i}",
            (-29.1 + i * 0.65, -10.45 + RNG.uniform(-0.08, 0.08), 0.48),
            (0.46, 0.54, 0.82),
            M["trash"],
            site,
            rot=RNG.uniform(-0.15, 0.15),
            bevel=0.035,
            segments=2,
        )
    collection_instance(
        A["bike_rack"],
        "shared_bicycle_parking",
        (-3.8, -8.9, 0),
        site,
        -0.35,
        (1.05, 1.05, 1.05),
    )

    # Trees, hedges and shrubs are instances from a small master library.
    tree_points = [
        (-33, 4, 1.08),
        (-29, 17, 0.95),
        (-14, 23, 1.05),
        (5, 22, 0.92),
        (25, 7, 0.98),
        (22, -15, 0.88),
        (-8, -21, 0.95),
        (13, -19, 0.86),
    ]
    for i, (x, y, sc) in enumerate(tree_points):
        collection_instance(
            A["tree_a"] if i % 2 else A["tree_b"],
            f"site_tree_{i}",
            (x, y, 0),
            site,
            RNG.uniform(-math.pi, math.pi),
            (sc, sc, sc),
        )
    for i, (x, y) in enumerate(
        [
            (-8, 10),
            (-4, 11),
            (1, 11.3),
            (6, 10.2),
            (11, 8.1),
            (14, 3.8),
            (13, -1.4),
            (9, -6.1),
            (3, -8.8),
            (-4, -8.4),
            (-10, -3.8),
        ]
    ):
        collection_instance(
            A["shrub"],
            f"courtyard_shrub_{i}",
            (x, y, 0.04),
            site,
            RNG.uniform(-0.4, 0.4),
            (0.82, 0.82, 0.70),
        )
    for i, (x, y, sx, sy, rot) in enumerate(
        [
            (-19, 23, 7.0, 0.45, 0.18),
            (-34, -1, 0.45, 8.5, -0.10),
            (26, -4, 0.45, 9.0, 0.18),
            (9, 24, 8.5, 0.45, -0.08),
        ]
    ):
        box(
            f"trimmed_hedge_{i}",
            (x, y, 0.48),
            (sx, sy, 0.80),
            M["hedge"],
            site,
            rot=rot,
            bevel=0.14,
            segments=4,
        )
    return site


def add_lowrise_group(M, A, root):
    templates = [
        dict(
            w=7.2,
            d=6.3,
            floors=2,
            wall="cream",
            roof="hip",
            roof_mat="roof_blue",
            rise=1.10,
            door_x=-1.7,
            fence="metal",
            carport=True,
            windows=[
                (-2.8, "front", 1.55, (0.92, 0.92, 0.92)),
                (2.2, "front", 1.55, (0.94, 0.94, 0.94)),
                (-2.4, "front", 4.35, (0.78, 0.80, 0.88)),
                (2.0, "front", 4.35, (0.78, 0.80, 0.88)),
                (0.8, "back", 1.55, (0.8, 0.8, 0.85)),
            ],
            yard=(-4.8, 4.8, -4.7, 5.2),
            shrubs=[(-3.8, -4.2, 0.72), (3.8, -4.0, 0.66), (4.1, 3.8, 0.60)],
        ),
        dict(
            w=6.4,
            d=5.4,
            floors=1,
            wall="tile_wall",
            roof="gable",
            roof_mat="roof_brown",
            rise=1.00,
            door_x=1.15,
            fence="stone",
            carport=False,
            windows=[
                (-1.9, "front", 1.42, (0.9, 0.9, 0.88)),
                (2.7, "front", 1.42, (0.75, 0.8, 0.82)),
                (-1.6, "back", 1.42, (0.80, 0.80, 0.80)),
                (0.8, "left", 1.42, (0.72, 0.72, 0.78)),
            ],
            yard=(-4.3, 4.0, -4.3, 4.2),
            shrubs=[(-3.2, -3.8, 0.62), (-2.7, 3.5, 0.55), (3.2, 3.2, 0.60)],
        ),
        dict(
            w=7.6,
            d=5.8,
            floors=2,
            wall="warm_gray",
            roof="mixed",
            roof_mat="roof_blue",
            rise=1.22,
            door_x=0.1,
            fence="metal",
            carport=True,
            side_wing=True,
            windows=[
                (-2.7, "front", 1.55, (0.92, 0.92, 0.90)),
                (2.9, "front", 1.55, (0.88, 0.88, 0.88)),
                (-2.6, "front", 4.32, (0.76, 0.78, 0.86)),
                (2.6, "front", 4.32, (0.76, 0.78, 0.86)),
                (-2.0, "back", 1.55, (0.82, 0.82, 0.84)),
            ],
            yard=(-5.0, 5.1, -4.9, 5.5),
            shrubs=[(-4.0, -4.3, 0.70), (4.3, -4.2, 0.64), (4.3, 4.1, 0.60)],
        ),
        dict(
            w=6.9,
            d=6.0,
            floors=1,
            wall="pale_green",
            roof="hip",
            roof_mat="roof_metal",
            rise=0.88,
            door_x=-0.8,
            fence="stone",
            carport=False,
            windows=[
                (-2.6, "front", 1.45, (0.88, 0.88, 0.84)),
                (2.0, "front", 1.45, (0.92, 0.92, 0.84)),
                (1.2, "right", 1.45, (0.72, 0.72, 0.78)),
                (-1.6, "back", 1.45, (0.76, 0.76, 0.82)),
            ],
            yard=(-4.7, 4.5, -4.4, 4.8),
            shrubs=[(-3.7, -3.7, 0.64), (3.6, -3.5, 0.56), (3.6, 3.6, 0.62)],
        ),
    ]
    placements = [
        ("A", (-2.8, -16.8, 0), math.radians(7), 0),
        ("B", (11.6, -16.0, 0), math.radians(-10), 1),
        ("C", (23.2, -2.8, 0), math.radians(18), 2),
        ("D", (18.0, 12.8, 0), math.radians(-22), 3),
        ("E", (2.8, 17.2, 0), math.radians(13), 0),
        ("F", (-12.5, 14.5, 0), math.radians(-16), 2),
        ("G", (-24.6, -3.0, 0), math.radians(10), 1),
    ]
    cols = []
    for label, origin, yaw, template_index in placements:
        params = dict(templates[template_index])
        # Constrained variation: dimensions and details move slightly within each master family.
        params["w"] *= 1 + RNG.uniform(-0.05, 0.06)
        params["d"] *= 1 + RNG.uniform(-0.05, 0.05)
        params["rise"] *= 1 + RNG.uniform(-0.05, 0.05)
        cols.append(add_lowrise_house(label, origin, yaw, params, M, A, root))
    return cols


def add_lighting_and_cameras():
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    try:
        bpy.context.scene.eevee.taa_render_samples = 24
    except Exception:
        pass
    bpy.context.scene.world = (
        bpy.data.worlds.new(PREFIX + "world")
        if bpy.context.scene.world is None
        else bpy.context.scene.world
    )
    bpy.context.scene.world.color = (0.78, 0.82, 0.86)

    bpy.ops.object.light_add(
        type="SUN",
        location=(-18, -10, 26),
        rotation=(math.radians(47), 0, math.radians(-32)),
    )
    sun = bpy.context.object
    sun.name = PREFIX + "soft_morning_sun"
    sun.data.energy = 2.0
    bpy.ops.object.light_add(type="AREA", location=(-8, -14, 18))
    area = bpy.context.object
    area.name = PREFIX + "large_sky_fill"
    area.data.energy = 320
    area.data.size = 28

    def cam(name, loc, target, fov):
        bpy.ops.object.camera_add(location=loc)
        obj = bpy.context.object
        obj.name = PREFIX + name
        obj.data.name = PREFIX + name
        obj.data.lens_unit = "FOV"
        obj.data.angle = math.radians(fov)
        obj.rotation_euler = (
            (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        )
        return obj

    return [
        (
            cam("cam_residential_zone_overview", (4, -43, 35), (-4, 0, 3.5), 55),
            "residential_zone_overview.png",
        ),
        (
            cam("cam_apartment_close_view", (-24, -26, 10.5), (-17, -3, 6.2), 52),
            "apartment_close_view.png",
        ),
        (
            cam("cam_lowrise_house_close_view", (8, -28, 7.0), (0, -16, 2.6), 50),
            "lowrise_house_close_view.png",
        ),
        (
            cam("cam_lowrise_group_view", (32, -30, 13), (13, 4, 3.2), 55),
            "lowrise_group_view.png",
        ),
        (
            cam("cam_residential_internal_view", (-21, -18, 5.6), (1, 1, 1.8), 58),
            "residential_internal_view.png",
        ),
    ]


def render_outputs(cameras):
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 800
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    for cam, filename in cameras:
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(OUT / filename)
        bpy.ops.render.render(write_still=True)
        print(f"[all45] rendered {filename}", flush=True)


def save_audit(start_time, root):
    object_count = len(bpy.data.objects)
    mesh_count = len(bpy.data.meshes)
    instanced = sum(1 for o in bpy.data.objects if o.instance_type == "COLLECTION")
    stats = {
        "prompt": "prompt-45 residential zone",
        "output": str(OUT),
        "object_count": object_count,
        "mesh_count": mesh_count,
        "collection_instances": instanced,
        "lowrise_houses": 7,
        "apartment_floors": 6,
        "render_names": [
            "residential_zone_overview.png",
            "apartment_close_view.png",
            "lowrise_house_close_view.png",
            "lowrise_group_view.png",
            "residential_internal_view.png",
        ],
        "elapsed_seconds": round(time.time() - start_time, 2),
    }
    with (OUT / "all45_residential_audit.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"[all45] audit {stats}", flush=True)


def main():
    start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    reset_scene()
    root = make_collection("residential_zone_all45")
    global MATS
    MATS = make_mats()
    assets = make_asset_masters(MATS)
    add_site_environment(MATS, assets, root)
    add_apartment((-18.0, -5.8, 0), math.radians(6), MATS, assets, root)
    add_lowrise_group(MATS, assets, root)
    cameras = add_lighting_and_cameras()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45.blend"))
    render_outputs(cameras)
    save_audit(start, root)


if __name__ == "__main__":
    main()
