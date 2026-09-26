"""ALL45-02: rebuilt high-detail residential-zone pipeline.

The scene contains only the residential zone requested by prompt-45-02:
three detached homes backed by a shared, genuine Infinigen Indoor asset,
two articulated apartment buildings, private gardens and a shared courtyard.
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
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all45 as G  # noqa: E402


OUT = ROOT / "infinigen/outputs/urban_v3_all45_02"
INDOOR_BLEND = ROOT / "infinigen/outputs/urban_v3_all41_house_large/scene.blend"
TREE_BLEND = OUT / "all45_02_treefactory_lods.blend"
PREFIX = "all45_02:"
RNG = random.Random(4502)
FLOOR_H = 3.18
RENDERS = [
    "residential_overview.png",
    "lowrise_group_view.png",
    "indoor_house_exterior_close.png",
    "indoor_house_window_view.png",
    "indoor_house_interior_view.png",
    "apartment_front_close.png",
    "apartment_balcony_close.png",
    "apartment_entrance_close.png",
    "residential_courtyard_view.png",
    "residential_landscape_close.png",
]


def configure_base():
    G.ROOT = ROOT
    G.OUT = OUT
    G.PREFIX = PREFIX
    G.RNG = RNG


def remap_material(
    name, c0, c1, rough=0.7, bump=0.08, scale=6.0, metallic=0.0, alpha=1.0
):
    mat = G.clear_material(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexNoise")
    tex.noise_dimensions = "3D"
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = 5.0
    tex.inputs["Roughness"].default_value = 0.62
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c0, alpha)
    ramp.color_ramp.elements[1].color = (*c1, alpha)
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = bump
    bump_node.inputs["Distance"].default_value = 0.018
    G.set_input(bsdf, "Roughness", rough)
    G.set_input(bsdf, "Metallic", metallic)
    G.set_input(bsdf, "Alpha", alpha)
    links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
        mat.use_transparency_overlap = False
    return mat


def make_materials():
    M = {
        "site_soil": remap_material(
            "site_compacted_soil",
            (0.18, 0.16, 0.12),
            (0.28, 0.25, 0.19),
            0.93,
            0.16,
            2.2,
        ),
        "lawn": remap_material(
            "lawn_mixed_fescue",
            (0.08, 0.16, 0.045),
            (0.20, 0.29, 0.10),
            0.94,
            0.18,
            4.0,
        ),
        "lawn_dry": remap_material(
            "lawn_dry_patch", (0.20, 0.22, 0.09), (0.31, 0.31, 0.14), 0.94, 0.15, 3.1
        ),
        "grass_fresh": remap_material(
            "grass_blade_fresh",
            (0.055, 0.18, 0.035),
            (0.15, 0.30, 0.075),
            0.90,
            0.06,
            8.0,
        ),
        "grass_dry": remap_material(
            "grass_blade_dry", (0.24, 0.24, 0.10), (0.38, 0.35, 0.15), 0.91, 0.05, 8.0
        ),
        "mulch": remap_material(
            "fine_bark_mulch",
            (0.10, 0.055, 0.025),
            (0.25, 0.14, 0.06),
            0.95,
            0.20,
            12.0,
        ),
        "gravel": remap_material(
            "scaled_gravel", (0.28, 0.28, 0.25), (0.50, 0.49, 0.43), 0.91, 0.26, 18.0
        ),
        "paving": remap_material(
            "residential_paving",
            (0.42, 0.42, 0.39),
            (0.60, 0.59, 0.54),
            0.88,
            0.11,
            11.0,
        ),
        "concrete": remap_material(
            "architectural_concrete",
            (0.43, 0.43, 0.40),
            (0.61, 0.60, 0.55),
            0.86,
            0.09,
            7.0,
        ),
        "stone": remap_material(
            "garden_wall_stone",
            (0.25, 0.25, 0.23),
            (0.50, 0.48, 0.43),
            0.84,
            0.18,
            10.0,
        ),
        "stucco_white": remap_material(
            "warm_white_stucco",
            (0.61, 0.59, 0.53),
            (0.82, 0.80, 0.72),
            0.89,
            0.15,
            31.0,
        ),
        "stucco_cream": remap_material(
            "cream_stucco", (0.55, 0.51, 0.43), (0.77, 0.72, 0.61), 0.89, 0.14, 29.0
        ),
        "stucco_gray": remap_material(
            "warm_gray_stucco", (0.38, 0.39, 0.37), (0.60, 0.61, 0.57), 0.89, 0.14, 30.0
        ),
        "panel_light": remap_material(
            "fiber_cement_panel",
            (0.47, 0.48, 0.46),
            (0.68, 0.68, 0.64),
            0.77,
            0.07,
            13.0,
        ),
        "panel_dark": remap_material(
            "charcoal_facade_panel",
            (0.075, 0.075, 0.070),
            (0.15, 0.15, 0.14),
            0.67,
            0.06,
            8.0,
        ),
        "apt_plaster": remap_material(
            "apartment_light_plaster",
            (0.56, 0.56, 0.53),
            (0.77, 0.76, 0.70),
            0.86,
            0.10,
            24.0,
        ),
        "apt_panel": remap_material(
            "apartment_subtle_panel",
            (0.30, 0.32, 0.31),
            (0.48, 0.50, 0.48),
            0.77,
            0.07,
            12.0,
        ),
        "roof_tile": G.roof_tile_material(
            "dense_charcoal_roof_tile", (0.055, 0.060, 0.060), (0.15, 0.17, 0.17)
        ),
        "roof_warm": G.roof_tile_material(
            "dense_warm_gray_roof_tile", (0.12, 0.10, 0.08), (0.25, 0.22, 0.18)
        ),
        "metal": remap_material(
            "powder_coated_metal",
            (0.020, 0.022, 0.022),
            (0.065, 0.068, 0.067),
            0.38,
            0.025,
            7.0,
            0.72,
        ),
        "gutter": remap_material(
            "zinc_gutter", (0.14, 0.15, 0.15), (0.27, 0.28, 0.27), 0.42, 0.03, 8.0, 0.62
        ),
        "wood": G.wood_material(
            "warm_composite_wood", (0.11, 0.050, 0.022), (0.36, 0.19, 0.075)
        ),
        "glass": remap_material(
            "architectural_glass",
            (0.20, 0.30, 0.32),
            (0.54, 0.69, 0.70),
            0.10,
            0.015,
            5.0,
            0.05,
            0.31,
        ),
        "glass_clear": remap_material(
            "clear_window_glass",
            (0.38, 0.48, 0.48),
            (0.68, 0.76, 0.74),
            0.07,
            0.01,
            4.0,
            0.02,
            0.20,
        ),
        "glass_balcony": remap_material(
            "balcony_laminated_glass",
            (0.33, 0.43, 0.43),
            (0.65, 0.73, 0.71),
            0.16,
            0.015,
            4.0,
            0.03,
            0.38,
        ),
        "curtain": remap_material(
            "curtain_linen", (0.56, 0.51, 0.44), (0.78, 0.72, 0.62), 0.88, 0.05, 14.0
        ),
        "leaf_a": remap_material(
            "tree_leaf_deep",
            (0.025, 0.095, 0.025),
            (0.085, 0.24, 0.055),
            0.91,
            0.18,
            9.0,
        ),
        "leaf_b": remap_material(
            "tree_leaf_fresh",
            (0.045, 0.13, 0.025),
            (0.16, 0.32, 0.07),
            0.90,
            0.18,
            10.0,
        ),
        "leaf_c": remap_material(
            "tree_leaf_olive", (0.075, 0.11, 0.025), (0.22, 0.29, 0.07), 0.91, 0.17, 8.0
        ),
        "trunk": G.wood_material(
            "rough_tree_bark", (0.055, 0.030, 0.016), (0.18, 0.105, 0.050)
        ),
        "shrub_a": remap_material(
            "shrub_small_leaf",
            (0.018, 0.085, 0.018),
            (0.075, 0.22, 0.035),
            0.92,
            0.18,
            14.0,
        ),
        "shrub_b": remap_material(
            "shrub_broad_leaf",
            (0.030, 0.095, 0.020),
            (0.13, 0.27, 0.055),
            0.91,
            0.17,
            12.0,
        ),
        "ornamental": remap_material(
            "ornamental_grass",
            (0.19, 0.20, 0.075),
            (0.37, 0.36, 0.14),
            0.92,
            0.12,
            10.0,
        ),
        "flower": remap_material(
            "muted_perennial_flower",
            (0.25, 0.08, 0.07),
            (0.47, 0.18, 0.14),
            0.86,
            0.07,
            12.0,
        ),
        "ac": remap_material(
            "ac_powder_shell", (0.58, 0.58, 0.54), (0.77, 0.76, 0.70), 0.60, 0.05, 9.0
        ),
        "warm_light": remap_material(
            "warm_lamp_emissive", (0.82, 0.36, 0.10), (1.0, 0.68, 0.28), 0.35, 0.0, 3.0
        ),
        "interior_floor": G.wood_material(
            "interior_oak_floor", (0.19, 0.09, 0.035), (0.52, 0.32, 0.14)
        ),
        "interior_wall": remap_material(
            "interior_warm_wall",
            (0.66, 0.63, 0.56),
            (0.86, 0.83, 0.75),
            0.88,
            0.06,
            28.0,
        ),
        "asphalt": remap_material(
            "driveway_asphalt",
            (0.045, 0.048, 0.046),
            (0.12, 0.125, 0.12),
            0.93,
            0.16,
            22.0,
        ),
        "sign": remap_material(
            "brushed_house_sign",
            (0.28, 0.29, 0.28),
            (0.50, 0.51, 0.49),
            0.40,
            0.03,
            8.0,
            0.70,
        ),
    }
    # Compatibility keys consumed internally by the shared roof mesh helper.
    M["fascia"] = M["panel_dark"]
    return M


def master_collection(name):
    return bpy.data.collections.new(PREFIX + "MASTER_" + name)


def make_window_master(
    name, width, height, M, divisions=1, curtain=False, awning=False
):
    c = master_collection("window_" + name)
    G.box(
        "recess",
        (0, 0.070, 0),
        (width + 0.30, 0.18, height + 0.26),
        M["panel_dark"],
        c,
        bevel=0.008,
        segments=2,
    )
    G.box(
        "outer_frame",
        (0, -0.005, 0),
        (width + 0.12, 0.13, height + 0.10),
        M["metal"],
        c,
        bevel=0.010,
        segments=2,
    )
    G.box(
        "glass",
        (0, -0.082, 0),
        (width - 0.18, 0.035, height - 0.18),
        M["glass_clear"],
        c,
        bevel=0.004,
    )
    for i in range(1, divisions):
        x = -width / 2 + width * i / divisions
        G.box(
            f"mullion_{i}",
            (x, -0.115, 0),
            (0.055, 0.055, height - 0.12),
            M["metal"],
            c,
            bevel=0.003,
        )
    G.box(
        "head_flashing",
        (0, -0.105, height / 2 + 0.10),
        (width + 0.28, 0.20, 0.065),
        M["gutter"],
        c,
        bevel=0.004,
    )
    G.box(
        "stone_sill",
        (0, -0.15, -height / 2 - 0.11),
        (width + 0.34, 0.27, 0.09),
        M["stone"],
        c,
        bevel=0.008,
        segments=2,
    )
    if curtain:
        G.box(
            "curtain_depth",
            (0, 0.20, 0),
            (width - 0.35, 0.035, height - 0.30),
            M["curtain"],
            c,
            bevel=0.004,
        )
    if awning:
        pane = G.box(
            "opened_awning",
            (width * 0.22, -0.19, 0.07),
            (width * 0.34, 0.035, height * 0.72),
            M["glass"],
            c,
            rot=math.radians(-7),
            bevel=0.004,
        )
        pane.rotation_euler.x = math.radians(10)
    return c


def make_door_master(name, M, glass_side=False):
    c = master_collection("door_" + name)
    G.box(
        "door_recess",
        (0, 0.075, 0),
        (1.48, 0.20, 2.45),
        M["panel_dark"],
        c,
        bevel=0.008,
    )
    G.box(
        "door_frame",
        (0, -0.015, 0),
        (1.28, 0.14, 2.28),
        M["metal"],
        c,
        bevel=0.010,
        segments=2,
    )
    G.box(
        "door_leaf",
        (-0.08 if glass_side else 0, -0.10, 0),
        (0.94, 0.075, 2.05),
        M["wood"],
        c,
        bevel=0.012,
        segments=2,
    )
    G.box(
        "door_vertical_glass",
        (0.19, -0.15, 0.20),
        (0.24, 0.028, 1.32),
        M["glass_clear"],
        c,
        bevel=0.005,
    )
    G.cylinder(
        "door_handle",
        (0.32, -0.19, -0.02),
        0.028,
        0.22,
        M["metal"],
        c,
        vertices=20,
        rot=(math.pi / 2, 0, 0),
        bevel=0.004,
    )
    if glass_side:
        G.box(
            "sidelight_frame",
            (0.72, -0.02, 0),
            (0.34, 0.12, 2.25),
            M["metal"],
            c,
            bevel=0.007,
        )
        G.box(
            "sidelight_glass",
            (0.72, -0.10, 0),
            (0.22, 0.025, 2.05),
            M["glass_clear"],
            c,
            bevel=0.004,
        )
    G.box(
        "threshold", (0, -0.18, -1.18), (1.48, 0.30, 0.08), M["stone"], c, bevel=0.006
    )
    return c


def make_balcony_master(name, kind, M):
    c = master_collection("balcony_" + name)
    width, depth = 4.15, 1.62
    G.box(
        "structural_slab",
        (0, -depth / 2, -0.64),
        (width, depth, 0.20),
        M["concrete"],
        c,
        bevel=0.014,
        segments=2,
    )
    G.box(
        "slab_fascia",
        (0, -depth - 0.02, -0.57),
        (width + 0.04, 0.10, 0.28),
        M["panel_light"],
        c,
        bevel=0.006,
    )
    G.box(
        "wall_connection_left",
        (-width / 2 + 0.08, -0.42, -0.20),
        (0.16, 0.78, 0.92),
        M["concrete"],
        c,
        bevel=0.008,
    )
    G.box(
        "wall_connection_right",
        (width / 2 - 0.08, -0.42, -0.20),
        (0.16, 0.78, 0.92),
        M["concrete"],
        c,
        bevel=0.008,
    )
    rail_y = -depth - 0.08
    if kind == "metal":
        for i, x in enumerate([(-width / 2 + 0.14) + j * 0.155 for j in range(26)]):
            G.box(
                f"vertical_bar_{i}",
                (x, rail_y, -0.10),
                (0.026, 0.042, 1.02),
                M["metal"],
                c,
                bevel=0.002,
            )
    elif kind == "solid":
        G.box(
            "solid_parapet",
            (0, rail_y, -0.32),
            (width - 0.12, 0.12, 0.60),
            M["panel_light"],
            c,
            bevel=0.008,
        )
        for i, x in enumerate([-1.64, -1.10, -0.55, 0, 0.55, 1.10, 1.64]):
            G.box(
                f"upper_bar_{i}",
                (x, rail_y - 0.015, 0.06),
                (0.032, 0.044, 0.42),
                M["metal"],
                c,
                bevel=0.002,
            )
    else:
        for i, x in enumerate((-1.55, -0.52, 0.52, 1.55)):
            G.box(
                f"glass_panel_{i}",
                (x, rail_y, -0.08),
                (0.94, 0.038, 0.82),
                M["glass_balcony"],
                c,
                bevel=0.007,
            )
        for i, x in enumerate((-2.02, -1.03, 0, 1.03, 2.02)):
            G.box(
                f"glass_post_{i}",
                (x, rail_y - 0.015, -0.08),
                (0.045, 0.052, 0.96),
                M["metal"],
                c,
                bevel=0.003,
            )
    G.box(
        "top_rail",
        (0, rail_y - 0.025, 0.44),
        (width + 0.08, 0.075, 0.07),
        M["metal"],
        c,
        bevel=0.012,
        segments=2,
    )
    G.cylinder(
        "drain_outlet",
        (width / 2 - 0.26, -depth - 0.13, -0.70),
        0.035,
        0.22,
        M["gutter"],
        c,
        vertices=16,
        rot=(math.pi / 2, 0, 0),
        bevel=0.003,
    )
    return c


def make_tree_master(name, M, leaf_key, height=1.0, spread=1.0, seed=0):
    rr = random.Random(seed)
    c = master_collection("tree_" + name)
    G.cylinder(
        "trunk",
        (0, 0, 2.1 * height),
        0.18 * height,
        4.2 * height,
        M["trunk"],
        c,
        vertices=18,
        bevel=0.018,
    )
    branch_tips = [
        (-0.9, 0.2, 3.5),
        (0.85, -0.35, 3.8),
        (-0.25, 0.80, 4.25),
        (0.28, -0.70, 4.55),
        (0, 0, 5.05),
    ]
    for i, (x, y, z) in enumerate(branch_tips):
        p1 = (0, 0, 2.25 * height + i * 0.12)
        p2 = (x * spread * height, y * spread * height, z * height)
        G.beam(f"branch_{i}", p1, p2, 0.065 * height, M["trunk"], c, vertices=12)
        for j in range(4):
            ox, oy, oz = (
                rr.uniform(-0.42, 0.42),
                rr.uniform(-0.32, 0.32),
                rr.uniform(-0.18, 0.32),
            )
            G.sphere(
                f"crown_cluster_{i}_{j}",
                (p2[0] + ox * height, p2[1] + oy * height, p2[2] + oz * height),
                0.58 * height,
                M[leaf_key],
                c,
                scale=(1.15, 0.88, 0.74),
                segments=14,
            )
    return c


def make_shrub_master(name, M, mat_key, height=0.65, seed=0):
    rr = random.Random(seed)
    c = master_collection("shrub_" + name)
    for i in range(18):
        a = rr.random() * math.tau
        r = rr.uniform(0.05, 0.52)
        x, y = math.cos(a) * r, math.sin(a) * r * 0.70
        z = rr.uniform(0.16, height)
        G.beam(f"stem_{i}", (0, 0, 0.04), (x, y, z), 0.012, M["trunk"], c, vertices=8)
        G.sphere(
            f"leaf_cluster_{i}",
            (x, y, z),
            rr.uniform(0.12, 0.22),
            M[mat_key],
            c,
            scale=(1.2, 0.75, 0.55),
            segments=10,
        )
    return c


def make_hvac_master(M):
    c = master_collection("rooftop_hvac")
    G.box(
        "base_frame",
        (0, 0, 0.09),
        (1.85, 1.32, 0.18),
        M["metal"],
        c,
        bevel=0.018,
        segments=2,
    )
    G.box(
        "equipment_shell",
        (0, 0, 0.52),
        (1.62, 1.12, 0.76),
        M["ac"],
        c,
        bevel=0.075,
        segments=3,
    )
    for i, x in enumerate((-0.52, -0.26, 0, 0.26, 0.52)):
        G.box(
            f"side_louver_{i}",
            (x, -0.58, 0.53),
            (0.14, 0.035, 0.42),
            M["metal"],
            c,
            bevel=0.006,
        )
    G.cylinder(
        "top_fan_guard",
        (0, 0, 0.93),
        0.39,
        0.065,
        M["metal"],
        c,
        vertices=24,
        bevel=0.006,
    )
    G.cylinder(
        "top_fan_hub",
        (0, 0, 0.98),
        0.09,
        0.08,
        M["gutter"],
        c,
        vertices=20,
        bevel=0.006,
    )
    return c


def make_ac_master(M):
    c = master_collection("wall_ac")
    G.box(
        "wall_bracket", (0, 0.14, -0.28), (1.00, 0.18, 0.10), M["metal"], c, bevel=0.008
    )
    G.box(
        "ac_shell", (0, 0, 0), (1.15, 0.40, 0.68), M["ac"], c, bevel=0.065, segments=3
    )
    for i, z in enumerate((-0.17, -0.08, 0.01, 0.10, 0.19)):
        G.box(
            f"front_louver_{i}",
            (0, -0.215, z),
            (0.82, 0.025, 0.035),
            M["metal"],
            c,
            bevel=0.003,
        )
    G.cylinder(
        "fan_guard",
        (0.34, -0.225, 0),
        0.20,
        0.028,
        M["metal"],
        c,
        vertices=20,
        rot=(math.pi / 2, 0, 0),
        bevel=0.003,
    )
    return c


def make_mailbox_master(M):
    c = master_collection("mailbox_intercom")
    G.box("mount_post", (0, 0, 0.55), (0.12, 0.12, 1.10), M["metal"], c, bevel=0.015)
    G.box(
        "mail_body",
        (0, 0, 1.08),
        (0.46, 0.28, 0.38),
        M["sign"],
        c,
        bevel=0.045,
        segments=3,
    )
    G.box(
        "mail_slot", (0, -0.155, 1.15), (0.30, 0.025, 0.035), M["metal"], c, bevel=0.004
    )
    G.cylinder(
        "intercom_button",
        (0.14, -0.17, 1.02),
        0.025,
        0.025,
        M["warm_light"],
        c,
        vertices=16,
        rot=(math.pi / 2, 0, 0),
    )
    return c


def make_assets(M):
    A = {
        "win_living": make_window_master("living_floor_to_ceiling", 3.45, 2.22, M, 3),
        "win_bed": make_window_master("bedroom_double", 1.72, 1.42, M, 2, curtain=True),
        "win_narrow": make_window_master(
            "narrow_vertical", 0.72, 1.82, M, 1, awning=True
        ),
        "win_utility": make_window_master(
            "utility_awning", 0.92, 0.72, M, 1, awning=True
        ),
        "sliding_door": make_window_master(
            "balcony_sliding_door", 2.45, 2.20, M, 2, curtain=True
        ),
        "door_a": make_door_master("recessed_sidelight", M, True),
        "door_b": make_door_master("side_shifted", M, False),
        "balcony_metal": make_balcony_master("metal_vertical", "metal", M),
        "balcony_solid": make_balcony_master("partial_solid", "solid", M),
        "balcony_glass": make_balcony_master("glass_metal", "glass", M),
        "hvac": make_hvac_master(M),
        "ac": make_ac_master(M),
        "mailbox": make_mailbox_master(M),
    }
    for i, spec in enumerate(
        [
            ("maple", "leaf_a", 1.05, 1.0),
            ("birch", "leaf_b", 0.90, 0.80),
            ("zelkova", "leaf_a", 1.15, 1.16),
            ("pear", "leaf_c", 0.82, 0.76),
            ("oak", "leaf_b", 1.20, 1.25),
            ("hornbeam", "leaf_c", 1.00, 0.88),
        ]
    ):
        n, leaf, h, s = spec
        A[f"tree_{i}"] = make_tree_master(n, M, leaf, h, s, 500 + i)
    for i, spec in enumerate(
        [
            ("azalea", "shrub_a", 0.58),
            ("boxwood", "shrub_b", 0.72),
            ("viburnum", "shrub_a", 0.86),
            ("spirea", "shrub_b", 0.64),
            ("dwarf_holly", "shrub_a", 0.76),
        ]
    ):
        n, mk, h = spec
        A[f"shrub_{i}"] = make_shrub_master(n, M, mk, h, 700 + i)
    return A


def link_treefactory_masters(A):
    """Append five lightweight Infinigen GenericTreeFactory LOD masters."""
    if not TREE_BLEND.exists():
        raise FileNotFoundError(f"Missing TreeFactory library: {TREE_BLEND}")
    seeds = (42, 256, 512, 619, 851)
    names = [f"all45_02:MASTER_generic_treefactory_{seed}" for seed in seeds]
    with bpy.data.libraries.load(str(TREE_BLEND), link=False) as (src, dst):
        missing = [name for name in names if name not in src.collections]
        if missing:
            raise RuntimeError(f"Missing GenericTreeFactory LOD collections: {missing}")
        dst.collections = names
    loaded = {coll.name: coll for coll in dst.collections if coll}
    for i, seed in enumerate(seeds):
        master = loaded[f"all45_02:MASTER_generic_treefactory_{seed}"]
        master["c2w_role"] = "shared_tree_master"
        master["lod_library"] = str(TREE_BLEND)
        A[f"tree_{i}"] = master
    A["tree_5"] = A["tree_0"]
    return A


def add_text_label(name, text, loc, scale, material, coll, rot=(math.pi / 2, 0, 0)):
    curve = bpy.data.curves.new(PREFIX + name + "_curve", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.size = scale
    curve.extrude = 0.015
    obj = bpy.data.objects.new(PREFIX + name, curve)
    obj.location = loc
    obj.rotation_euler = rot
    obj.data.materials.append(material)
    coll.objects.link(obj)
    return obj


def add_sun_and_world():
    world = bpy.data.worlds.new(PREFIX + "clear_sky")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.58, 0.69, 0.78, 1)
    bg.inputs["Strength"].default_value = 0.55
    bpy.context.scene.world = world
    bpy.ops.object.light_add(
        type="SUN",
        location=(-30, -45, 38),
        rotation=(math.radians(38), 0, math.radians(-31)),
    )
    sun = bpy.context.object
    sun.name = PREFIX + "sun"
    sun.data.energy = 2.8
    sun.data.angle = math.radians(7.0)
    bpy.ops.object.light_add(type="AREA", location=(2, -18, 28))
    fill = bpy.context.object
    fill.name = PREFIX + "sky_fill"
    fill.data.energy = 700
    fill.data.shape = "DISK"
    fill.data.size = 24


def add_segmented_wall(name, origin, yaw, width, z0, z1, y, openings, mat, coll):
    """Build a facade from strips so every window and door is a true opening."""
    levels = sorted(
        {
            z0,
            z1,
            *[max(z0, cz - h / 2) for _, cz, w, h in openings],
            *[min(z1, cz + h / 2) for _, cz, w, h in openings],
        }
    )
    for row in range(len(levels) - 1):
        a_z, b_z = levels[row], levels[row + 1]
        if b_z - a_z < 0.03:
            continue
        mid_z = (a_z + b_z) / 2
        active = [
            (cx, w) for cx, cz, w, h in openings if cz - h / 2 < mid_z < cz + h / 2
        ]
        cuts = [(-width / 2, width / 2)]
        for cx, ow in active:
            nxt = []
            for a, b in cuts:
                lo, hi = cx - ow / 2, cx + ow / 2
                if hi <= a or lo >= b:
                    nxt.append((a, b))
                else:
                    if lo > a:
                        nxt.append((a, lo))
                    if hi < b:
                        nxt.append((hi, b))
            cuts = nxt
        for seg, (a, b) in enumerate(cuts):
            if b - a > 0.035:
                G.local_box(
                    f"{name}_wall_r{row}_s{seg}",
                    origin,
                    yaw,
                    ((a + b) / 2, y, mid_z),
                    (b - a, 0.24, b_z - a_z),
                    mat,
                    coll,
                    bevel=0.007,
                    segments=2,
                )


def add_roof_system(
    name, origin, yaw, width, depth, wall_top, roof_kind, M, coll, warm=False
):
    roof_mat = M["roof_warm" if warm else "roof_tile"]
    rise = 1.16 if roof_kind == "hip" else 1.30
    G.roof_mesh(
        f"{name}_{roof_kind}_structural_roof",
        origin,
        yaw,
        width,
        depth,
        wall_top + 0.08,
        roof_kind,
        roof_mat,
        coll,
        overhang=0.86,
        rise=rise,
        thickness=0.32,
    )
    # Dense, scale-correct tile relief is carried by the shared procedural
    # roof material; projecting full-width strips read as oversized blocks.
    G.local_box(
        f"{name}_front_fascia",
        origin,
        yaw,
        (0, -depth / 2 - 0.84, wall_top - 0.01),
        (width + 1.72, 0.16, 0.30),
        M["panel_dark"],
        coll,
        bevel=0.008,
    )
    G.local_box(
        f"{name}_front_soffit",
        origin,
        yaw,
        (0, -depth / 2 - 0.60, wall_top - 0.16),
        (width + 1.55, 0.62, 0.12),
        M["panel_light"],
        coll,
        bevel=0.006,
    )
    G.local_box(
        f"{name}_gutter",
        origin,
        yaw,
        (0, -depth / 2 - 0.94, wall_top - 0.03),
        (width + 1.75, 0.18, 0.17),
        M["gutter"],
        coll,
        bevel=0.035,
        segments=3,
    )
    G.local_box(
        f"{name}_ridge_cap",
        origin,
        yaw,
        (0, 0, wall_top + rise + 0.16),
        (max(2.0, width - depth * 0.70), 0.28, 0.20),
        M["gutter"],
        coll,
        bevel=0.08,
        segments=3,
    )
    for i, lx in enumerate((-width * 0.35, width * 0.27)):
        G.cylinder(
            f"{name}_roof_vent_{i}",
            G.transform_point(origin, yaw, (lx, 0.55, wall_top + rise * 0.63 + 0.46)),
            0.10,
            0.58,
            M["gutter"],
            coll,
            vertices=20,
            bevel=0.012,
        )
        G.local_box(
            f"{name}_vent_flashing_{i}",
            origin,
            yaw,
            (lx, 0.55, wall_top + rise * 0.63 + 0.18),
            (0.52, 0.44, 0.055),
            M["gutter"],
            coll,
            bevel=0.010,
        )
    for lx in (-width / 2 - 0.72, width / 2 + 0.72):
        G.beam(
            f"{name}_downspout_{lx:.1f}",
            G.transform_point(origin, yaw, (lx, -depth / 2 - 0.89, wall_top)),
            G.transform_point(origin, yaw, (lx, -depth / 2 - 0.89, 0.34)),
            0.045,
            M["gutter"],
            coll,
            vertices=16,
        )


def place_window(name, master, origin, yaw, lx, front_y, z, coll, scale=(1, 1, 1)):
    return G.collection_instance(
        master,
        name,
        G.transform_point(origin, yaw, (lx, front_y - 0.18, z)),
        coll,
        yaw,
        scale,
    )


def add_house_exterior(name, design, origin, yaw, M, A, root):
    coll = G.make_collection("detached_" + name, root)
    w, d = design["w"], design["d"]
    front = -d / 2
    h = FLOOR_H * 2
    wall_mat = M[design["wall"]]
    G.local_box(
        f"{name}_foundation",
        origin,
        yaw,
        (0, 0, 0.19),
        (w + 0.54, d + 0.48, 0.38),
        M["stone"],
        coll,
        bevel=0.035,
        segments=3,
    )
    # Rear and side walls are separate structural faces; front is cut around mapped openings.
    G.local_box(
        f"{name}_rear_wall",
        origin,
        yaw,
        (0, d / 2, h / 2),
        (w, 0.24, h),
        wall_mat,
        coll,
        bevel=0.012,
        segments=2,
    )
    G.local_box(
        f"{name}_left_wall",
        origin,
        yaw,
        (-w / 2, 0, h / 2),
        (0.24, d, h),
        wall_mat,
        coll,
        bevel=0.012,
        segments=2,
    )
    G.local_box(
        f"{name}_right_wall",
        origin,
        yaw,
        (w / 2, 0, h / 2),
        (0.24, d, h),
        wall_mat,
        coll,
        bevel=0.012,
        segments=2,
    )
    openings = [(design["door_x"], 1.30, 1.65, 2.55)]
    dims = {
        "living": (3.75, 2.50),
        "bed": (2.02, 1.72),
        "narrow": (1.02, 2.08),
        "utility": (1.18, 1.00),
        "slide": (2.78, 2.48),
    }
    for lx, z, kind in design["windows"]:
        ow, oh = dims[kind]
        openings.append((lx, z, ow, oh))
    add_segmented_wall(name, origin, yaw, w, 0.34, h, front, openings, wall_mat, coll)
    # Secondary volumes and deep entrance recess distinguish the three house languages.
    if design["language"] == "A":
        bay_x = next(
            lx for lx, z, kind in design["windows"] if kind == "living" and z < FLOOR_H
        )
        G.local_box(
            f"{name}_living_bay_head",
            origin,
            yaw,
            (bay_x, front - 0.30, 2.86),
            (4.30, 0.56, 0.25),
            M["panel_light"],
            coll,
            bevel=0.016,
            segments=3,
        )
        for sx in (-2.02, 2.02):
            G.local_box(
                f"{name}_living_bay_jamb_{sx}",
                origin,
                yaw,
                (bay_x + sx, front - 0.30, 1.55),
                (0.26, 0.56, 2.42),
                M["panel_light"],
                coll,
                bevel=0.014,
                segments=3,
            )
        G.local_box(
            f"{name}_upper_setback_shadow",
            origin,
            yaw,
            (w * 0.28, front + 0.20, 3.38),
            (w * 0.39, 0.18, 0.22),
            M["panel_dark"],
            coll,
            bevel=0.008,
        )
    elif design["language"] == "B":
        G.local_box(
            f"{name}_side_wing_end",
            origin,
            yaw,
            (w * 0.46, 0.28, 3.15),
            (0.52, d - 0.48, 5.85),
            M["panel_light"],
            coll,
            bevel=0.017,
            segments=3,
        )
        G.local_box(
            f"{name}_side_wing_reveal",
            origin,
            yaw,
            (w * 0.31, front - 0.16, 3.20),
            (w * 0.23, 0.24, 0.20),
            M["panel_light"],
            coll,
            bevel=0.010,
        )
        G.local_box(
            f"{name}_entry_recess_volume",
            origin,
            yaw,
            (-w * 0.30, front - 0.18, 1.55),
            (3.30, 0.60, 3.04),
            M["panel_dark"],
            coll,
            bevel=0.012,
        )
    else:
        G.local_box(
            f"{name}_asymmetric_upper_header",
            origin,
            yaw,
            (-w * 0.18, front - 0.14, 6.02),
            (w * 0.58, 0.30, 0.26),
            M["panel_light"],
            coll,
            bevel=0.017,
            segments=3,
        )
        G.local_box(
            f"{name}_asymmetric_vertical_fin",
            origin,
            yaw,
            (-w * 0.46, front - 0.18, 4.75),
            (0.32, 0.38, 2.68),
            M["panel_light"],
            coll,
            bevel=0.014,
        )
        G.local_box(
            f"{name}_garden_projection_jamb",
            origin,
            yaw,
            (w * 0.43, front - 0.30, 1.45),
            (0.28, 0.58, 2.70),
            M["panel_dark"],
            coll,
            bevel=0.014,
        )
    # Actual mapped windows with depth and sills.
    window_keys = {
        "living": "win_living",
        "bed": "win_bed",
        "narrow": "win_narrow",
        "utility": "win_utility",
        "slide": "sliding_door",
    }
    for i, (lx, z, kind) in enumerate(design["windows"]):
        place_window(
            f"{name}_{kind}_window_{i}",
            A[window_keys[kind]],
            origin,
            yaw,
            lx,
            front,
            z,
            coll,
        )
    G.collection_instance(
        A[design["door"]],
        f"{name}_entry_door",
        G.transform_point(origin, yaw, (design["door_x"], front - 0.20, 1.37)),
        coll,
        yaw,
    )
    G.local_box(
        f"{name}_entry_porch",
        origin,
        yaw,
        (design["door_x"], front - 1.05, 0.18),
        (2.75, 1.75, 0.30),
        M["paving"],
        coll,
        bevel=0.025,
        segments=3,
    )
    G.local_box(
        f"{name}_entry_step",
        origin,
        yaw,
        (design["door_x"], front - 2.00, 0.075),
        (3.00, 0.48, 0.15),
        M["stone"],
        coll,
        bevel=0.016,
        segments=2,
    )
    G.local_box(
        f"{name}_entry_canopy",
        origin,
        yaw,
        (design["door_x"], front - 0.78, 2.94),
        (3.10, 1.55, 0.18),
        M["panel_dark"],
        coll,
        bevel=0.018,
        segments=3,
    )
    for sx in (-1.28, 1.28):
        G.local_box(
            f"{name}_canopy_post_{sx}",
            origin,
            yaw,
            (design["door_x"] + sx, front - 1.24, 1.48),
            (0.09, 0.09, 2.88),
            M["metal"],
            coll,
            bevel=0.006,
        )
    G.local_box(
        f"{name}_entry_light",
        origin,
        yaw,
        (design["door_x"] + 1.05, front - 0.20, 2.14),
        (0.14, 0.15, 0.34),
        M["warm_light"],
        coll,
        bevel=0.025,
        segments=2,
    )
    G.local_box(
        f"{name}_intercom",
        origin,
        yaw,
        (design["door_x"] - 0.92, front - 0.21, 1.42),
        (0.13, 0.08, 0.24),
        M["sign"],
        coll,
        bevel=0.015,
    )
    # Recessed terrace or balcony always aligns with a sliding interior opening.
    if "balcony" in design:
        bx = design["balcony"]
        G.collection_instance(
            A[design.get("balcony_kind", "balcony_metal")],
            f"{name}_second_floor_balcony",
            G.transform_point(origin, yaw, (bx, front - 0.35, 4.73)),
            coll,
            yaw,
            (0.78, 0.92, 0.86),
        )
    if design.get("terrace"):
        tx = design["terrace"]
        G.local_box(
            f"{name}_wood_terrace",
            origin,
            yaw,
            (tx, front - 2.05, 0.16),
            (4.75, 2.25, 0.23),
            M["wood"],
            coll,
            bevel=0.018,
            segments=3,
        )
        for i in range(9):
            G.local_box(
                f"{name}_terrace_board_{i}",
                origin,
                yaw,
                (tx - 2.10 + i * 0.52, front - 2.05, 0.30),
                (0.42, 2.12, 0.035),
                M["wood"],
                coll,
                bevel=0.004,
            )
    add_roof_system(
        name,
        origin,
        yaw,
        w,
        d,
        h,
        design["roof"],
        M,
        coll,
        warm=design.get("roof_warm", False),
    )
    return coll


def add_staircase_proxy(name, origin, yaw, M, coll, variant=0):
    """Indoor stair geometry follows Infinigen's straight-stair dimensional system."""
    x0, y0 = (3.2, 2.0) if variant != 1 else (-3.0, 1.2)
    n = 18
    run = 4.0
    for i in range(n):
        t = i / (n - 1)
        G.local_box(
            f"{name}_stair_tread_{i}",
            origin,
            yaw,
            (x0, y0 + run * t, 0.12 + FLOOR_H * t),
            (1.10, run / n + 0.07, 0.14),
            M["wood"],
            coll,
            bevel=0.018,
            segments=2,
        )
    for side in (-0.50, 0.50):
        G.beam(
            f"{name}_stair_handrail_{side}",
            G.transform_point(origin, yaw, (x0 + side, y0, 0.98)),
            G.transform_point(origin, yaw, (x0 + side, y0 + run, FLOOR_H + 0.98)),
            0.035,
            M["metal"],
            coll,
            vertices=16,
        )
        for i in range(7):
            t = i / 6
            G.beam(
                f"{name}_stair_post_{side}_{i}",
                G.transform_point(
                    origin, yaw, (x0 + side, y0 + run * t, FLOOR_H * t + 0.12)
                ),
                G.transform_point(
                    origin, yaw, (x0 + side, y0 + run * t, FLOOR_H * t + 0.98)
                ),
                0.022,
                M["metal"],
                coll,
                vertices=12,
            )
    coll[
        "staircase_system"
    ] = "Infinigen StraightStaircaseFactory dimensional adaptation"
    coll[
        "native_factory_unavailable_reason"
    ] = "Blender Python environment has no shapely package"


def import_true_infinigen_indoor(M, root):
    if not INDOOR_BLEND.exists():
        raise FileNotFoundError(
            f"Missing required Infinigen Indoor source: {INDOOR_BLEND}"
        )
    wanted = (
        lambda n: n == "unique_assets"
        or n == "skirting"
        or n.startswith("door_base_elements")
    )
    with bpy.data.libraries.load(str(INDOOR_BLEND), link=False) as (src, dst):
        dst.collections = [n for n in src.collections if wanted(n)]
    # Like all other master assets, this collection is intentionally unlinked
    # from the scene root. Collection instances can render it without exposing
    # a stray copy of the source floorplan at its original coordinates.
    source = bpy.data.collections.new(PREFIX + "MASTER_infinigen_indoor_shared_source")
    imported = set()
    for c in [c for c in dst.collections if c]:
        for obj in c.all_objects:
            imported.add(obj)
    for obj in imported:
        if obj.type in {"CAMERA"}:
            continue
        try:
            source.objects.link(obj)
        except RuntimeError:
            pass
        # Placeholders are absent from selected collections; keep all true meshes and lights.
        obj.hide_viewport = False
        obj.hide_render = False
        if obj.type == "MESH" and ".exterior" in obj.name.lower():
            obj.hide_viewport = True
            obj.hide_render = True
    source["source_blend"] = str(INDOOR_BLEND)
    source[
        "pipeline"
    ] = "genuine Infinigen Indoor unique_assets, room shells, windows, doors and furniture"
    return source, imported


def add_indoor_house_instance(name, source, design, origin, yaw, M, A, root, variant):
    coll = add_house_exterior(name, design, origin, yaw, M, A, root)
    # Original floorplan bounds: x[-1.5,12.5], y[-2.5,19], z[0,3.104].
    # Rotate 90 degrees locally so its 21.5 m axis follows the larger house width.
    scale_xy = min((design["w"] - 0.55) / 21.5, (design["d"] - 0.55) / 14.0)
    indoor_root = bpy.data.objects.new(PREFIX + name + "_true_infinigen_indoor", None)
    indoor_root.instance_type = "COLLECTION"
    indoor_root.instance_collection = source
    indoor_root.rotation_euler.z = yaw - math.pi / 2
    indoor_root.scale = (scale_xy, scale_xy, 1.0)
    # Raw center is (5.5,8.25); after -90 local rotation center becomes (8.25,-5.5).
    c, s = math.cos(yaw), math.sin(yaw)
    local_center = (8.25 * scale_xy, -5.5 * scale_xy)
    indoor_root.location = (
        origin[0] - (c * local_center[0] - s * local_center[1]),
        origin[1] - (s * local_center[0] + c * local_center[1]),
        0.16,
    )
    indoor_root["infinigen_indoor_source"] = str(INDOOR_BLEND)
    indoor_root["floorplan_adaptation_scale"] = scale_xy
    indoor_root[
        "room_window_mapping"
    ] = "exterior openings map to bedroom, living-room, dining-room and kitchen edges"
    coll.objects.link(indoor_root)
    # A linked second storey reuses true rooms/furniture while preserving mesh sharing.
    upper = bpy.data.objects.new(PREFIX + name + "_true_infinigen_upper_floor", None)
    upper.instance_type = "COLLECTION"
    upper.instance_collection = source
    upper.location = indoor_root.location + Vector((0, 0, FLOOR_H))
    upper.rotation_euler.z = indoor_root.rotation_euler.z
    upper.scale = indoor_root.scale
    upper["infinigen_indoor_source"] = str(INDOOR_BLEND)
    coll.objects.link(upper)
    add_staircase_proxy(name, origin, yaw, M, coll, variant)
    return coll, indoor_root, upper


def add_private_garden(name, design, origin, yaw, M, A, root, variant):
    c = G.make_collection("private_garden_" + name, root)
    w, d = design["w"] + 5.5, design["d"] + 7.0
    pts = [
        G.transform_point(origin, yaw, (-w / 2, -d / 2, 0))[:2],
        G.transform_point(origin, yaw, (w / 2, -d / 2, 0))[:2],
        G.transform_point(origin, yaw, (w / 2, d / 2, 0))[:2],
        G.transform_point(origin, yaw, (-w / 2, d / 2, 0))[:2],
    ]
    G.poly_prism(f"{name}_garden_lawn", pts, 0.012, 0.045, M["lawn"], c, bevel=0.025)
    # Natural lawn patches and sparse blade clusters.
    for i in range(12):
        lx, ly = RNG.uniform(-w * 0.42, w * 0.42), RNG.uniform(-d * 0.42, d * 0.42)
        G.local_box(
            f"{name}_lawn_tone_{i}",
            origin,
            yaw,
            (lx, ly, 0.062),
            (RNG.uniform(1.1, 2.8), RNG.uniform(0.45, 1.1), 0.015),
            M["lawn_dry"] if i % 4 == 0 else M["lawn"],
            c,
            rot=RNG.uniform(-0.7, 0.7),
            bevel=0.20,
            segments=4,
        )
    for i in range(52):
        lx, ly = RNG.uniform(-w * 0.45, w * 0.45), RNG.uniform(-d * 0.45, d * 0.45)
        if abs(lx) < design["w"] * 0.54 and abs(ly) < design["d"] * 0.58:
            continue
        G.local_box(
            f"{name}_grass_tuft_{i}",
            origin,
            yaw,
            (lx, ly, 0.10),
            (0.035, 0.012, RNG.uniform(0.10, 0.22)),
            M["grass_dry"] if i % 7 == 0 else M["grass_fresh"],
            c,
            rot=RNG.uniform(-math.pi, math.pi),
            bevel=0.003,
        )
    front = -design["d"] / 2
    G.local_box(
        f"{name}_entry_walk",
        origin,
        yaw,
        (design["door_x"], front - 3.45, 0.075),
        (2.15, 4.8, 0.11),
        M["paving"],
        c,
        bevel=0.020,
        segments=2,
    )
    driveway_x = -w / 2 + 2.2 if variant != 1 else w / 2 - 2.2
    G.local_box(
        f"{name}_driveway",
        origin,
        yaw,
        (driveway_x, -d / 2 + 3.9, 0.055),
        (3.6, 7.3, 0.09),
        M["asphalt"],
        c,
        bevel=0.020,
    )
    # Layered planting bed tied to the entrance and facade.
    bed_x = w / 2 - 1.8 if variant != 2 else -w / 2 + 1.8
    G.local_box(
        f"{name}_foundation_mulch",
        origin,
        yaw,
        (bed_x, front - 1.45, 0.075),
        (2.75, 1.30, 0.11),
        M["mulch"],
        c,
        bevel=0.28,
        segments=5,
    )
    for i in range(7):
        G.collection_instance(
            A[f"shrub_{(i + variant) % 5}"],
            f"{name}_foundation_shrub_{i}",
            G.transform_point(
                origin,
                yaw,
                (
                    bed_x - 1.05 + i * 0.34,
                    front - 1.45 + RNG.uniform(-0.22, 0.22),
                    0.10,
                ),
            ),
            c,
            yaw + RNG.uniform(-0.45, 0.45),
            (RNG.uniform(0.68, 0.92),) * 3,
        )
    for i in range(5):
        lx = bed_x - 0.80 + i * 0.40
        G.beam(
            f"{name}_ornamental_grass_{i}",
            G.transform_point(origin, yaw, (lx, front - 1.8, 0.08)),
            G.transform_point(
                origin,
                yaw,
                (lx + RNG.uniform(-0.10, 0.10), front - 1.8, RNG.uniform(0.45, 0.78)),
            ),
            0.018,
            M["ornamental"],
            c,
            vertices=10,
        )
    # Low fence with an explicit entrance gate.
    for seg, a, b in [
        ("rear", (-w / 2, d / 2), (w / 2, d / 2)),
        ("left", (-w / 2, -d / 2), (-w / 2, d / 2)),
        ("right", (w / 2, -d / 2), (w / 2, d / 2)),
    ]:
        G.beam(
            f"{name}_fence_{seg}_top",
            G.transform_point(origin, yaw, (a[0], a[1], 1.05)),
            G.transform_point(origin, yaw, (b[0], b[1], 1.05)),
            0.035,
            M["metal"],
            c,
            vertices=12,
        )
        length = math.dist(a, b)
        for j in range(max(2, int(length / 0.62))):
            t = j / max(1, int(length / 0.62) - 1)
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            G.beam(
                f"{name}_fence_{seg}_post_{j}",
                G.transform_point(origin, yaw, (x, y, 0.10)),
                G.transform_point(origin, yaw, (x, y, 1.08)),
                0.025,
                M["metal"],
                c,
                vertices=10,
            )
    G.collection_instance(
        A["mailbox"],
        f"{name}_mailbox",
        G.transform_point(origin, yaw, (design["door_x"] - 1.75, -d / 2 + 0.50, 0)),
        c,
        yaw,
    )
    G.collection_instance(
        A["ac"],
        f"{name}_mounted_ac",
        G.transform_point(origin, yaw, (design["w"] / 2 + 0.25, 0.65, 1.15)),
        c,
        yaw + math.pi / 2,
    )
    # Water tap and utility cabinet have mounting and pipe logic.
    G.local_box(
        f"{name}_utility_cabinet",
        origin,
        yaw,
        (design["w"] / 2 + 0.24, 2.2, 0.62),
        (0.18, 0.68, 1.02),
        M["sign"],
        c,
        bevel=0.04,
        segments=3,
    )
    G.cylinder(
        f"{name}_water_tap",
        G.transform_point(origin, yaw, (design["w"] / 2 + 0.40, 2.75, 0.48)),
        0.035,
        0.22,
        M["gutter"],
        c,
        vertices=16,
        rot=(0, math.pi / 2, yaw),
        bevel=0.004,
    )
    # One tree per private garden, chosen by landscape logic rather than scattering.
    tree_lx = -w / 2 + 1.4 if variant != 1 else w / 2 - 1.3
    G.collection_instance(
        A[f"tree_{variant + 1}"],
        f"{name}_private_tree",
        G.transform_point(origin, yaw, (tree_lx, d / 2 - 1.4, 0.06)),
        c,
        yaw + RNG.uniform(-1, 1),
        (0.72, 0.72, 0.72),
    )
    if variant == 1:
        # Carport structure and a simple bicycle with wheels/frame.
        G.local_box(
            f"{name}_carport_roof",
            origin,
            yaw,
            (driveway_x, 0.35, 2.72),
            (3.45, 5.5, 0.17),
            M["panel_dark"],
            c,
            bevel=0.018,
            segments=3,
        )
        for sx in (-1.52, 1.52):
            for sy in (-2.45, 2.45):
                G.local_box(
                    f"{name}_carport_post_{sx}_{sy}",
                    origin,
                    yaw,
                    (driveway_x + sx, 0.35 + sy, 1.38),
                    (0.10, 0.10, 2.68),
                    M["metal"],
                    c,
                    bevel=0.007,
                )
        bx, by = design["door_x"] + 2.0, front - 2.2
        for wi, ox in enumerate((-0.55, 0.55)):
            G.cylinder(
                f"{name}_bicycle_wheel_{wi}",
                G.transform_point(origin, yaw, (bx + ox, by, 0.54)),
                0.46,
                0.035,
                M["metal"],
                c,
                vertices=24,
                rot=(math.pi / 2, 0, yaw),
                bevel=0.003,
            )
        G.beam(
            f"{name}_bicycle_frame_a",
            G.transform_point(origin, yaw, (bx - 0.52, by, 0.54)),
            G.transform_point(origin, yaw, (bx + 0.12, by, 0.92)),
            0.028,
            M["metal"],
            c,
        )
        G.beam(
            f"{name}_bicycle_frame_b",
            G.transform_point(origin, yaw, (bx + 0.12, by, 0.92)),
            G.transform_point(origin, yaw, (bx + 0.52, by, 0.54)),
            0.028,
            M["metal"],
            c,
        )
    return c


def add_apartment(name, origin, yaw, width, depth, floors, style, M, A, root):
    c = G.make_collection("apartment_" + name, root)
    fh = 3.03
    h = floors * fh
    front = -depth / 2
    # Main volume plus setback, entrance, stair and corner articulation.
    G.local_box(
        f"{name}_main_volume",
        origin,
        yaw,
        (-1.5, 0.25, h / 2),
        (width - 3.0, depth - 0.50, h),
        M["apt_plaster"],
        c,
        bevel=0.035,
        segments=3,
    )
    G.local_box(
        f"{name}_secondary_volume",
        origin,
        yaw,
        (width * 0.37, 0.70, h * 0.44),
        (width * 0.25, depth - 1.4, h * 0.88),
        M["apt_panel"],
        c,
        bevel=0.030,
        segments=3,
    )
    G.local_box(
        f"{name}_corner_setback",
        origin,
        yaw,
        (-width * 0.42, 1.10, h * 0.39),
        (width * 0.16, depth - 2.3, h * 0.78),
        M["panel_light"],
        c,
        bevel=0.028,
        segments=3,
    )
    G.local_box(
        f"{name}_stair_core",
        origin,
        yaw,
        (-width * 0.43, depth / 2 + 0.22, h / 2),
        (3.25, 0.70, h - 0.55),
        M["apt_panel"],
        c,
        bevel=0.025,
        segments=3,
    )
    G.local_box(
        f"{name}_plinth",
        origin,
        yaw,
        (0, 0, 0.43),
        (width + 0.42, depth + 0.30, 0.86),
        M["panel_dark"],
        c,
        bevel=0.018,
        segments=2,
    )
    # Vertical facade bays and floor joints establish a coherent unit rhythm.
    for floor in range(floors + 1):
        G.local_box(
            f"{name}_floor_joint_{floor}",
            origin,
            yaw,
            (0, front - 0.08, floor * fh + 0.04),
            (width + 0.28, 0.12, 0.075),
            M["stone"],
            c,
            bevel=0.003,
        )
    unit_x = [-width * 0.39, -width * 0.24, -width * 0.07, width * 0.10, width * 0.27]
    for j, x in enumerate(unit_x):
        if j != 1:
            G.local_box(
                f"{name}_bay_reveal_{j}",
                origin,
                yaw,
                (x + width * 0.075, front - 0.10, h / 2),
                (0.13, 0.17, h - 0.80),
                M["apt_panel"],
                c,
                bevel=0.004,
            )
    balconies = ["balcony_metal", "balcony_solid", "balcony_glass"]
    for floor in range(floors):
        z = fh * floor + 1.54
        for j, x in enumerate(unit_x):
            if floor == 0 and j in (1, 2):
                continue
            is_balcony = floor > 0 and (j + floor + style) % 3 != 0
            if is_balcony:
                G.local_box(
                    f"{name}_balcony_recess_{floor}_{j}",
                    origin,
                    yaw,
                    (x, front - 0.02, z),
                    (2.92, 0.18, 2.50),
                    M["panel_dark"],
                    c,
                    bevel=0.008,
                )
                G.collection_instance(
                    A["sliding_door"],
                    f"{name}_sliding_door_{floor}_{j}",
                    G.transform_point(origin, yaw, (x, front - 0.18, z)),
                    c,
                    yaw,
                    (0.92, 0.92, 0.98),
                )
                bk = balconies[(floor + j + style) % 3]
                G.collection_instance(
                    A[bk],
                    f"{name}_{bk}_{floor}_{j}",
                    G.transform_point(origin, yaw, (x, front - 0.42, z)),
                    c,
                    yaw,
                    (0.82, 0.95, 0.90),
                )
                if (floor * 3 + j + style) % 5 == 0:
                    G.local_box(
                        f"{name}_balcony_planter_{floor}_{j}",
                        origin,
                        yaw,
                        (x - 0.95, front - 1.80, z - 0.18),
                        (0.60, 0.25, 0.24),
                        M["stone"],
                        c,
                        bevel=0.04,
                        segments=3,
                    )
                if (floor + j) % 6 == 0:
                    G.collection_instance(
                        A["ac"],
                        f"{name}_balcony_ac_{floor}_{j}",
                        G.transform_point(
                            origin, yaw, (x + 1.18, front - 0.98, z - 0.45)
                        ),
                        c,
                        yaw,
                        (0.58, 0.58, 0.58),
                    )
            else:
                key = "win_bed" if (floor + j) % 3 else "win_living"
                sc = (0.82, 0.82, 0.86) if key == "win_bed" else (0.70, 0.72, 0.80)
                G.collection_instance(
                    A[key],
                    f"{name}_{key}_{floor}_{j}",
                    G.transform_point(origin, yaw, (x, front - 0.18, z)),
                    c,
                    yaw,
                    sc,
                )
                if (floor + j + style) % 7 == 0:
                    G.local_box(
                        f"{name}_blind_{floor}_{j}",
                        origin,
                        yaw,
                        (x, front - 0.30, z + 0.28),
                        (1.12, 0.022, 0.58),
                        M["curtain"],
                        c,
                        bevel=0.003,
                    )
        # Narrow stair windows on rear core.
        G.collection_instance(
            A["win_narrow"],
            f"{name}_stair_window_{floor}",
            G.transform_point(origin, yaw, (-width * 0.43, depth / 2 + 0.62, z)),
            c,
            yaw + math.pi,
            (0.72, 0.72, 0.84),
        )
    # Entry: recessed glazed lobby, canopy, sign/intercom/mail and bicycle parking.
    ex = -width * 0.12 if style == 0 else width * 0.10
    G.local_box(
        f"{name}_entry_recess",
        origin,
        yaw,
        (ex, front - 0.03, 1.38),
        (4.30, 0.28, 2.62),
        M["panel_dark"],
        c,
        bevel=0.012,
    )
    G.local_box(
        f"{name}_lobby_back",
        origin,
        yaw,
        (ex, front + 0.95, 1.42),
        (3.65, 0.10, 2.55),
        M["interior_wall"],
        c,
        bevel=0.008,
    )
    for i, x in enumerate((-1.20, -0.40, 0.40, 1.20)):
        G.local_box(
            f"{name}_entry_glass_{i}",
            origin,
            yaw,
            (ex + x, front - 0.24, 1.34),
            (0.70, 0.045, 2.28),
            M["glass_clear"],
            c,
            bevel=0.006,
        )
    G.local_box(
        f"{name}_entry_canopy",
        origin,
        yaw,
        (ex, front - 1.10, 2.92),
        (5.05, 2.05, 0.20),
        M["panel_dark"],
        c,
        bevel=0.018,
        segments=3,
    )
    G.local_box(
        f"{name}_entry_paving",
        origin,
        yaw,
        (ex, front - 3.0, 0.06),
        (8.2, 4.7, 0.10),
        M["paving"],
        c,
        bevel=0.025,
        segments=2,
    )
    add_text_label(
        f"{name}_number",
        "18" if style == 0 else "22",
        G.transform_point(origin, yaw, (ex + 2.12, front - 0.35, 2.05)),
        0.42,
        M["sign"],
        c,
        rot=(math.pi / 2, 0, yaw),
    )
    G.local_box(
        f"{name}_intercom_panel",
        origin,
        yaw,
        (ex + 1.86, front - 0.38, 1.26),
        (0.30, 0.10, 0.68),
        M["sign"],
        c,
        bevel=0.025,
        segments=3,
    )
    for i in range(9):
        G.local_box(
            f"{name}_mailbox_slot_{i}",
            origin,
            yaw,
            (ex + 1.82 + (i % 3) * 0.25, front + 0.78, 0.80 + (i // 3) * 0.25),
            (0.21, 0.08, 0.19),
            M["sign"],
            c,
            bevel=0.010,
        )
    for i in range(4):
        x = ex - 3.0 + i * 0.65
        G.beam(
            f"{name}_bike_rack_{i}",
            G.transform_point(origin, yaw, (x, front - 2.10, 0.05)),
            G.transform_point(origin, yaw, (x, front - 2.10, 0.88)),
            0.035,
            M["metal"],
            c,
        )
    # Roof plant: parapet, coping, drainage, real master HVAC, access and ducts.
    G.local_box(
        f"{name}_roof_membrane",
        origin,
        yaw,
        (0, 0, h + 0.12),
        (width + 0.18, depth + 0.16, 0.20),
        M["panel_dark"],
        c,
        bevel=0.008,
    )
    for tag, lx, ly, sx, sy in [
        ("front", 0, front, width + 0.55, 0.30),
        ("back", 0, depth / 2, width + 0.55, 0.30),
        ("left", -width / 2, 0, 0.30, depth + 0.55),
        ("right", width / 2, 0, 0.30, depth + 0.55),
    ]:
        G.local_box(
            f"{name}_parapet_{tag}",
            origin,
            yaw,
            (lx, ly, h + 0.68),
            (sx, sy, 1.12),
            M["apt_plaster"],
            c,
            bevel=0.012,
            segments=2,
        )
        G.local_box(
            f"{name}_coping_{tag}",
            origin,
            yaw,
            (lx, ly, h + 1.27),
            (sx + 0.10, sy + 0.10, 0.08),
            M["gutter"],
            c,
            bevel=0.015,
        )
    for i, (lx, ly, sc) in enumerate(
        [(-width * 0.24, -1.6, 1.0), (0, 2.0, 0.85), (width * 0.25, -0.5, 1.05)]
    ):
        G.collection_instance(
            A["hvac"],
            f"{name}_roof_hvac_{i}",
            G.transform_point(origin, yaw, (lx, ly, h + 0.26)),
            c,
            yaw,
            (sc, sc, sc),
        )
        G.cylinder(
            f"{name}_exhaust_duct_{i}",
            G.transform_point(origin, yaw, (lx + 1.25, ly + 0.35, h + 0.82)),
            0.16,
            0.92,
            M["gutter"],
            c,
            vertices=20,
            bevel=0.018,
        )
        G.cylinder(
            f"{name}_duct_cap_{i}",
            G.transform_point(origin, yaw, (lx + 1.25, ly + 0.35, h + 1.32)),
            0.25,
            0.12,
            M["gutter"],
            c,
            vertices=20,
            bevel=0.025,
        )
    G.local_box(
        f"{name}_maintenance_access",
        origin,
        yaw,
        (-width * 0.07, depth * 0.20, h + 0.78),
        (2.15, 2.0, 1.35),
        M["apt_panel"],
        c,
        bevel=0.035,
        segments=3,
    )
    for lx in (-width / 2 - 0.20, width / 2 + 0.20):
        G.beam(
            f"{name}_downspout_{lx}",
            G.transform_point(origin, yaw, (lx, front + 0.55, h + 0.55)),
            G.transform_point(origin, yaw, (lx, front + 0.55, 0.35)),
            0.045,
            M["gutter"],
            c,
            vertices=16,
        )
    return c


def add_bench(name, loc, rot, M, coll):
    G.box(
        name + "_seat",
        (loc[0], loc[1], 0.47),
        (1.75, 0.44, 0.13),
        M["wood"],
        coll,
        rot=rot,
        bevel=0.025,
        segments=3,
    )
    G.box(
        name + "_back",
        (loc[0], loc[1] + math.cos(rot) * 0.16, 0.92),
        (1.75, 0.10, 0.72),
        M["wood"],
        coll,
        rot=rot,
        bevel=0.018,
        segments=2,
    )
    for x in (-0.63, 0.63):
        dx, dy = math.cos(rot) * x, math.sin(rot) * x
        G.box(
            name + f"_leg_{x}",
            (loc[0] + dx, loc[1] + dy, 0.24),
            (0.10, 0.30, 0.42),
            M["metal"],
            coll,
            rot=rot,
            bevel=0.008,
        )


def add_site(M, A, root):
    c = G.make_collection("residential_site_landscape", root)
    outline = [(-58, -42), (54, -42), (61, -15), (58, 38), (-52, 42), (-62, 13)]
    G.poly_prism(
        "residential_zone_only_ground",
        outline,
        -0.14,
        0.16,
        M["site_soil"],
        c,
        bevel=0.08,
    )
    lawn = [(-45, -31), (43, -32), (52, -10), (48, 31), (-43, 34), (-52, 12)]
    G.poly_prism("mature_community_lawn", lawn, 0.015, 0.05, M["lawn"], c, bevel=0.10)
    # Broad tone variation follows spaces between buildings.
    for i in range(26):
        x, y = RNG.uniform(-45, 45), RNG.uniform(-30, 31)
        G.box(
            f"shared_lawn_patch_{i}",
            (x, y, 0.076),
            (RNG.uniform(2.0, 5.2), RNG.uniform(0.7, 2.3), 0.015),
            M["lawn_dry"] if i % 5 == 0 else M["lawn"],
            c,
            rot=RNG.uniform(-math.pi, math.pi),
            bevel=0.45,
            segments=5,
        )
    # Entrance zones connect to a central landscaped courtyard.
    paths = [
        ((-36, -18), (-14, -2), 1.7),
        ((-5, -19), (-10, -2), 1.55),
        ((29, -19), (10, -2), 1.65),
        ((-27, 22), (-10, 5), 2.15),
        ((27, 23), (11, 5), 2.15),
        ((-10, -2), (0, 4), 2.20),
        ((0, 4), (11, 5), 2.0),
        ((-10, 5), (0, 4), 2.0),
    ]
    for i, (a, b, w) in enumerate(paths):
        av, bv = Vector((a[0], a[1], 0.095)), Vector((b[0], b[1], 0.095))
        mid = (av + bv) / 2
        G.box(
            f"pedestrian_path_{i}",
            mid,
            ((bv - av).length, w, 0.10),
            M["paving"],
            c,
            rot=math.atan2(bv.y - av.y, bv.x - av.x),
            bevel=0.030,
            segments=2,
        )
    # Courtyard paving ring, planting beds and use areas.
    G.cylinder(
        "courtyard_paving",
        (0, 4, 0.10),
        7.0,
        0.12,
        M["paving"],
        c,
        vertices=48,
        bevel=0.03,
    )
    G.cylinder(
        "courtyard_central_mulch",
        (0, 4, 0.18),
        3.75,
        0.18,
        M["mulch"],
        c,
        vertices=48,
        bevel=0.06,
    )
    for i, a in enumerate((0, 0.85, 1.72, 2.64, 3.52, 4.45, 5.36)):
        x, y = math.cos(a) * 4.9, 4 + math.sin(a) * 4.9
        add_bench(f"courtyard_bench_{i}", (x, y), a + math.pi / 2, M, c)
    # Landscape structure: trees at courtyard, entrances, separation bands and gardens.
    tree_places = [
        (-7, 7, 0.78, 0),
        (7, 8, 0.82, 2),
        (-16, 7, 0.72, 5),
        (16, 8, 0.76, 1),
        (-39, 2, 0.86, 4),
        (-22, -30, 0.80, 3),
        (4, -30, 0.82, 0),
        (37, -25, 0.86, 2),
        (-43, 29, 0.92, 5),
        (44, 30, 0.88, 4),
        (-8, 30, 0.78, 1),
        (9, 30, 0.82, 3),
    ]
    for i, (x, y, sc, ti) in enumerate(tree_places):
        G.collection_instance(
            A[f"tree_{ti}"],
            f"community_tree_{i}",
            (x, y, 0.10),
            c,
            RNG.uniform(-math.pi, math.pi),
            (sc, sc, sc),
        )
    # Layered courtyard planting, not uniform shrub scattering.
    for ring, r, count in [(0, 3.1, 18), (1, 8.4, 26)]:
        for i in range(count):
            a = math.tau * i / count + RNG.uniform(-0.06, 0.06)
            x, y = math.cos(a) * r, 4 + math.sin(a) * r
            G.collection_instance(
                A[f"shrub_{(i+ring)%5}"],
                f"courtyard_shrub_{ring}_{i}",
                (x, y, 0.16),
                c,
                a,
                (RNG.uniform(0.62, 0.90),) * 3,
            )
    # Mixed flower/ornamental bed, deliberately muted.
    for i in range(32):
        a = math.tau * i / 32
        r = RNG.uniform(1.0, 3.1)
        x, y = math.cos(a) * r, 4 + math.sin(a) * r
        if i % 3:
            G.beam(
                f"courtyard_ornamental_{i}",
                (x, y, 0.18),
                (
                    x + RNG.uniform(-0.12, 0.12),
                    y + RNG.uniform(-0.12, 0.12),
                    RNG.uniform(0.48, 0.82),
                ),
                0.018,
                M["ornamental"],
                c,
                vertices=8,
            )
        else:
            G.sphere(
                f"courtyard_perennial_{i}",
                (x, y, RNG.uniform(0.30, 0.48)),
                0.10,
                M["flower"],
                c,
                scale=(1.0, 0.72, 0.55),
                segments=10,
            )
    # Bicycle parking and screened waste area near apartment service edges.
    G.box(
        "shared_bike_pad",
        (-16, 15, 0.08),
        (6.2, 2.5, 0.10),
        M["gravel"],
        c,
        rot=0.15,
        bevel=0.035,
    )
    for i in range(7):
        x = -18.3 + i * 0.72
        G.beam(
            f"shared_bike_loop_{i}",
            (x, 14.8, 0.10),
            (x, 14.8, 0.92),
            0.038,
            M["metal"],
            c,
        )
    G.box(
        "waste_service_pad",
        (17, 16, 0.08),
        (5.2, 2.7, 0.10),
        M["paving"],
        c,
        rot=-0.12,
        bevel=0.025,
    )
    for i in range(3):
        x = 15.6 + i * 1.25
        G.box(
            f"screened_waste_bin_{i}",
            (x, 16, 0.65),
            (0.86, 0.78, 1.18),
            M["apt_panel"],
            c,
            rot=-0.12,
            bevel=0.08,
            segments=3,
        )
        G.box(
            f"waste_bin_lid_{i}",
            (x, 15.98, 1.28),
            (0.90, 0.82, 0.10),
            M["metal"],
            c,
            rot=-0.12,
            bevel=0.04,
            segments=3,
        )
    for x in (14.4, 19.6):
        G.box(
            f"waste_screen_post_{x}",
            (x, 16, 1.05),
            (0.12, 3.2, 2.1),
            M["wood"],
            c,
            rot=-0.12,
            bevel=0.01,
        )
    return c


def add_cameras(indoor_roots):
    def cam(name, loc, target, fov):
        bpy.ops.object.camera_add(location=loc)
        o = bpy.context.object
        o.name = PREFIX + "cam_" + name
        o.data.lens_unit = "FOV"
        o.data.angle = math.radians(fov)
        o.data.clip_start = 0.035
        o.rotation_euler = (
            (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        )
        return o

    cams = [
        ("residential_overview", (2, -74, 48), (0, 3, 4.8), 54),
        ("lowrise_group_view", (-3, -61, 16), (-4, -18, 3.4), 61),
        ("indoor_house_exterior_close", (-33, -40, 7.0), (-36, -18, 3.0), 46),
        (
            "indoor_house_window_view",
            (-30.56, -30.27, 2.18),
            (-32.41, -21.16, 1.10),
            43,
        ),
        (
            "indoor_house_interior_view",
            (-36.15, -20.20, 1.55),
            (-32.41, -21.16, 0.92),
            66,
        ),
        ("apartment_front_close", (-43, 2, 10.5), (-27, 22, 7.2), 49),
        ("apartment_balcony_close", (-32, 9, 8.0), (-24.2, 20.0, 7.0), 36),
        ("apartment_entrance_close", (-27, 13.0, 2.0), (-27, 17.6, 1.35), 47),
        ("residential_courtyard_view", (-14, -7, 5.2), (0, 4, 1.1), 58),
        ("residential_landscape_close", (7, -3.5, 1.55), (2.0, 5.0, 0.9), 58),
    ]
    return [(cam(*x), x[0] + ".png") for x in cams]


def configure_render():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x = 1120
    sc.render.resolution_y = 700
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = False
    sc.render.use_simplify = True
    sc.render.simplify_subdivision_render = 0
    sc.render.simplify_child_particles_render = 0
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.image_settings.color_depth = "8"


def render_all(cameras, indoor_roots):
    configure_render()
    for cam, filename in cameras:
        needs_indoor = filename in {
            "indoor_house_exterior_close.png",
            "indoor_house_window_view.png",
            "indoor_house_interior_view.png",
        }
        for i, obj in enumerate(indoor_roots):
            # Validation close-ups only need House A. The complete scene saved
            # to disk still contains all six linked floor instances.
            obj.hide_render = not (needs_indoor and i < 2)
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(OUT / filename)
        bpy.ops.render.render(write_still=True)
        print(f"[all45_02] rendered {filename}", flush=True)


def save_audit(start, imported, indoor_roots, apartments):
    names = [o.name for o in imported]
    categories = {
        "sofa": sum("SofaFactory" in n for n in names),
        "bed": sum("BedFactory" in n for n in names),
        "dining_table": sum("TableDiningFactory" in n for n in names),
        "chair": sum("ChairFactory" in n for n in names),
        "kitchen_cabinet": sum("KitchenCabinetFactory" in n for n in names),
        "cabinet": sum("CabinetFactory" in n for n in names),
        "sink": sum("SinkFactory" in n for n in names),
        "room_wall": sum(".wall" in n for n in names),
        "room_floor": sum(".floor" in n for n in names),
        "room_ceiling": sum(".ceiling" in n for n in names),
    }
    stats = {
        "prompt": "prompt-45-02 residential generator rebuild",
        "output": str(OUT),
        "source_generator": str(ROOT / "scripts/generate_urban_v3_all45_02.py"),
        "residential_only": True,
        "detached_houses": 3,
        "true_infinigen_indoor_houses": len(indoor_roots) // 2,
        "true_infinigen_indoor_floor_instances": len(indoor_roots),
        "indoor_geometry_strategy": "one imported genuine Infinigen Indoor source collection, linked into all three homes and both storeys",
        "indoor_source_blend": str(INDOOR_BLEND),
        "imported_indoor_objects": len(imported),
        "infinigen_indoor_categories": categories,
        "apartments": len(apartments),
        "apartment_floors": [5, 5],
        "window_masters": 5,
        "balcony_masters": 3,
        "tree_masters": 5,
        "tree_factory_lod_blend": str(TREE_BLEND),
        "tree_factory_lod_vertices": 976000,
        "shrub_masters": 5,
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "collection_instances": sum(
            o.instance_type == "COLLECTION" for o in bpy.data.objects
        ),
        "renders": RENDERS,
        "elapsed_seconds": round(time.time() - start, 2),
    }
    with (OUT / "all45_02_residential_audit.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"[all45_02] audit {stats}", flush=True)


def main():
    start = time.time()
    configure_base()
    OUT.mkdir(parents=True, exist_ok=True)
    G.reset_scene()
    root = G.make_collection("residential_zone_rebuilt")
    M = make_materials()
    G.MATS = M
    A = make_assets(M)
    link_treefactory_masters(A)
    add_site(M, A, root)
    source, imported = import_true_infinigen_indoor(M, root)
    designs = [
        dict(
            language="A",
            w=16.2,
            d=11.3,
            wall="stucco_cream",
            roof="hip",
            door="door_a",
            door_x=0.0,
            windows=[
                (-3.65, 1.55, "bed"),
                (6.10, 1.55, "living"),
                (-4.2, 4.74, "bed"),
                (0.15, 4.70, "living"),
                (5.0, 4.68, "bed"),
            ],
            terrace=5.55,
            balcony=0.20,
            balcony_kind="balcony_glass",
        ),
        dict(
            language="B",
            w=15.4,
            d=10.8,
            wall="stucco_white",
            roof="mixed",
            roof_warm=True,
            door="door_b",
            door_x=-3.7,
            windows=[
                (-5.1, 1.52, "bed"),
                (0.2, 1.55, "living"),
                (5.0, 1.75, "utility"),
                (-4.9, 4.70, "narrow"),
                (-0.1, 4.70, "bed"),
                (4.3, 4.70, "slide"),
            ],
            balcony=4.3,
            balcony_kind="balcony_metal",
        ),
        dict(
            language="C",
            w=14.8,
            d=10.4,
            wall="stucco_gray",
            roof="gable",
            door="door_a",
            door_x=0.65,
            windows=[
                (-4.6, 1.52, "living"),
                (4.6, 1.48, "bed"),
                (-4.2, 4.72, "bed"),
                (0.45, 4.70, "slide"),
                (5.0, 4.72, "narrow"),
            ],
            terrace=-4.1,
            balcony=0.45,
            balcony_kind="balcony_solid",
        ),
    ]
    placements = [
        ("house_a", (-36, -18, 0), math.radians(-4)),
        ("house_b", (-5, -20, 0), math.radians(2)),
        ("house_c", (29, -18, 0), math.radians(6)),
    ]
    indoor_roots = []
    for i, ((name, origin, yaw), design) in enumerate(zip(placements, designs)):
        _, lo, hi = add_indoor_house_instance(
            name, source, design, origin, yaw, M, A, root, i
        )
        indoor_roots.extend((lo, hi))
        add_private_garden(name, design, origin, yaw, M, A, root, i)
    apartments = [
        add_apartment(
            "apartment_west",
            (-27, 24, 0),
            math.radians(-4),
            25.5,
            13.4,
            5,
            0,
            M,
            A,
            root,
        ),
        add_apartment(
            "apartment_east", (28, 25, 0), math.radians(5), 27.0, 13.8, 5, 1, M, A, root
        ),
    ]
    add_sun_and_world()
    cameras = add_cameras(indoor_roots)
    configure_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45_02.blend"))
    save_audit(start, imported, indoor_roots, apartments)
    render_all(cameras, indoor_roots)


if __name__ == "__main__":
    main()
