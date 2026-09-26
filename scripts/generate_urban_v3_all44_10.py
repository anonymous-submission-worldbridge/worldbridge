"""ALL44-10: focused realism pass for the service building and playground."""

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
import os
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_urban_v3_all44_09 as base

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
base.INPUT = ROOT / "infinigen/outputs/urban_v3_all44_09/urban_v3_all44_09.blend"
base.OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_10"
base.P = "all44_10:"

ORIG_CREATE_SHARED_MATERIALS = base.create_shared_materials
ORIG_CREATE_SITE_FURNITURE = base.create_site_furniture


def remove_old_court_playground():
    stale_prefixes = ("all44_08:", "all44_08_grass:", "all44_09:", "all44_10:")
    targets = [o for o in bpy.data.objects if o.name.startswith(stale_prefixes)]
    removed = len(targets)
    if targets:
        bpy.data.batch_remove(targets)
    cols = [c for c in bpy.data.collections if c.name.startswith(stale_prefixes)]
    if cols:
        bpy.data.batch_remove(cols)
    return removed


def tune_retained_materials():
    """Desaturate retained all44_04 lawn/plant materials so old context does not read toy-like."""
    for m in bpy.data.materials:
        n = m.name.lower()
        if "leaf" in n or "grass" in n or "lawn" in n or "turf" in n:
            if not m.use_nodes:
                continue
            bsdf = m.node_tree.nodes.get("Principled BSDF")
            if not bsdf:
                continue
            col = bsdf.inputs["Base Color"].default_value
            muted = (col[0] * 0.58, col[1] * 0.66, col[2] * 0.54, col[3])
            bsdf.inputs["Base Color"].default_value = muted
            bsdf.inputs["Roughness"].default_value = min(
                0.95, max(0.78, bsdf.inputs["Roughness"].default_value)
            )


def create_shared_materials():
    M = ORIG_CREATE_SHARED_MATERIALS()
    M.update(
        {
            "rubber": base.mat(
                "MAT_MUTED_EPDM_CHARCOAL", (0.105, 0.125, 0.125), 0.86, noise=0.18
            ),
            "rubber2": base.mat(
                "MAT_MUTED_EPDM_TERRACOTTA", (0.38, 0.145, 0.065), 0.84, noise=0.16
            ),
            "rubber3": base.mat(
                "MAT_MUTED_EPDM_MOSS", (0.16, 0.235, 0.16), 0.86, noise=0.16
            ),
            "play_metal": base.mat(
                "MAT_PLAY_STRUCTURAL_METAL", (0.055, 0.115, 0.12), 0.48, 0.25, 0.04
            ),
            "play_panel": base.mat(
                "MAT_PLAY_PANEL_COMPOSITE", (0.16, 0.27, 0.25), 0.58, 0.02, 0.055
            ),
            "slide": base.mat(
                "MAT_SLIDE_DULLED_POLYMER", (0.58, 0.18, 0.055), 0.52, 0.02, 0.055
            ),
            "rope": base.mat(
                "MAT_CLIMBING_ROPE_DARK_RED", (0.24, 0.045, 0.035), 0.82, noise=0.07
            ),
            "turf": base.mat(
                "MAT_DESATURATED_TURF", (0.052, 0.195, 0.043), 0.91, noise=0.34
            ),
            "grass_blade": base.mat(
                "MAT_DESATURATED_GRASS_BLADES",
                (0.085, 0.225, 0.070)
                if os.environ.get("C2W_FULL_REVISION") == "urban_v1_full_06"
                else (
                    (0.028, 0.24, 0.038)
                    if os.environ.get("C2W_FULL_REVISION")
                    in ("urban_v1_full_03", "urban_v1_full_04", "urban_v1_full_05")
                    else (0.045, 0.235, 0.035)
                ),
                0.86,
                noise=0.18,
            ),
            "wall_stucco": base.mat(
                "MAT_WARM_STUCCO_PANEL", (0.62, 0.58, 0.50), 0.88, noise=0.18
            ),
            "wall_weather": base.mat(
                "MAT_STUCCO_BASE_WEATHERING", (0.38, 0.35, 0.30), 0.93, noise=0.22
            ),
            "trim_light": base.mat(
                "MAT_BUILDING_LIGHT_TRIM", (0.73, 0.72, 0.66), 0.72, 0.02, 0.05
            ),
            "door": base.mat(
                "MAT_SERVICE_DOOR_PAINT", (0.10, 0.16, 0.17), 0.58, 0.18, 0.04
            ),
            "roof": base.mat(
                "MAT_TEXTURED_MEMBRANE_ROOF", (0.072, 0.076, 0.074), 0.78, 0.08, 0.075
            ),
            "roof_edge": base.mat(
                "MAT_ROOF_FLASHING", (0.18, 0.19, 0.18), 0.46, 0.55, 0.025
            ),
            "louver": base.mat("MAT_HVAC_LOUVER", (0.30, 0.32, 0.31), 0.42, 0.62, 0.02),
        }
    )
    return M


def create_slide_playset(params, M, lib):
    c = bpy.data.collections.new(base.P + "MASTER_SLIDE_PLAYSET_REBUILT")
    lib["slide_master"] = c.name
    ph = params["platform_height"]
    metal, panel, slide = M["play_metal"], M["play_panel"], M["slide"]

    for x in (-1.25, 1.25):
        for y in (-1.05, 1.05):
            base.cyl("tower_post", (x, y, ph / 2), 0.085, ph, metal, c, 32, bev=0.018)
            base.cube(
                "post_base_plate",
                (x, y, 0.055),
                (0.42, 0.42, 0.11),
                M["concrete"],
                c,
                0.035,
            )
            for dx in (-0.11, 0.11):
                base.cyl(
                    "post_anchor_bolt",
                    (x + dx, y, 0.145),
                    0.018,
                    0.045,
                    M["wire"],
                    c,
                    12,
                )

    base.cube("platform_frame", (0, 0, ph - 0.08), (2.85, 2.48, 0.16), metal, c, 0.035)
    base.cube(
        "anti_slip_platform_deck",
        (0, 0, ph + 0.025),
        (2.62, 2.25, 0.08),
        panel,
        c,
        0.045,
    )
    for y in (-1.18, 1.18):
        base.beam(
            "upper_guardrail",
            (-1.25, y, ph + 0.82),
            (1.25, y, ph + 0.82),
            0.045,
            metal,
            c,
        )
        base.beam(
            "mid_guardrail",
            (-1.25, y, ph + 0.42),
            (1.25, y, ph + 0.42),
            0.035,
            metal,
            c,
        )
        for x in (-0.88, -0.44, 0, 0.44, 0.88):
            base.beam(
                "guardrail_picket",
                (x, y, ph + 0.08),
                (x, y, ph + 0.82),
                0.022,
                metal,
                c,
            )
    for x in (-1.32, 1.32):
        base.beam(
            "side_guardrail",
            (x, -0.95, ph + 0.70),
            (x, 0.95, ph + 0.70),
            0.04,
            metal,
            c,
        )

    # Stair/ladder assembly with separate stringers, treads, anti-slip lips and handrails.
    for y in (-0.62, 0.62):
        base.beam(
            "stair_stringer", (-2.85, y, 0.12), (-1.24, y, ph + 0.02), 0.052, metal, c
        )
        base.beam(
            "stair_handrail", (-2.95, y, 0.86), (-1.24, y, ph + 0.68), 0.038, metal, c
        )
    for i in range(7):
        t = i / 6
        x = -2.75 + 1.42 * t
        z = 0.22 + (ph - 0.22) * t
        base.cube("stair_tread", (x, 0, z), (0.36, 1.34, 0.085), panel, c, 0.03)
        base.cube(
            "stair_nosing",
            (x - 0.18, 0, z + 0.055),
            (0.035, 1.38, 0.035),
            M["wire"],
            c,
            0.01,
        )

    # Curved trough slide with thickness, raised side lips, top collar and lower landing.
    verts, faces = [], []
    steps, cross = 64, 12
    for i in range(steps + 1):
        t = i / steps
        x = 1.04 + params["slide_length"] * t
        z = 0.20 + (ph - 0.20) * (1 - t) ** 1.72 + 0.055 * math.sin(math.pi * t)
        for j in range(cross + 1):
            y = -0.62 + 1.24 * j / cross
            lip = 0.18 * (abs(y) / 0.62) ** 2
            crown = -0.035 * math.cos((j / cross) * math.pi * 2)
            verts.append((x, y, z + lip + crown))
    for i in range(steps):
        for j in range(cross):
            a = i * (cross + 1) + j
            b = (i + 1) * (cross + 1) + j
            faces.append((a, b, b + 1, a + 1))
    me = bpy.data.meshes.new(base.P + "slide_trough_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(slide)
    me.update()
    o = bpy.data.objects.new(base.P + "slide_trough_body", me)
    c.objects.link(o)
    sol = o.modifiers.new("shell_thickness", "SOLIDIFY")
    sol.thickness = 0.075
    sol.offset = -1
    bev = o.modifiers.new("rounded_slide_edges", "BEVEL")
    bev.width = 0.026
    bev.segments = 4

    for side in (-1, 1):
        pts = []
        for i in range(56):
            t = i / 55
            x = 1.04 + params["slide_length"] * t
            z = 0.20 + (ph - 0.20) * (1 - t) ** 1.72 + 0.055 * math.sin(math.pi * t)
            pts.append((x, 0.70 * side, z + 0.11))
        base.curve_obj("slide_raised_side_lip", pts, 0.052, slide, c)
    base.cube(
        "slide_top_collar", (1.02, 0, ph - 0.02), (0.34, 1.48, 0.22), metal, c, 0.035
    )
    base.rounded_slab("slide_landing", 4.98, 0, 1.16, 1.34, 0.235, 0.12, 0.32, slide, c)
    for y in (-0.52, 0.52):
        base.beam(
            "slide_under_support", (2.45, y, 0.12), (2.50, y, 1.08), 0.042, metal, c
        )
        base.beam("landing_support", (4.78, y, 0.10), (4.78, y, 0.32), 0.032, metal, c)
    return c


def create_swing_set(params, M, lib):
    c = bpy.data.collections.new(base.P + "MASTER_SWING_SET_REBUILT")
    lib["swing_master"] = c.name
    metal, wire = M["play_metal"], M["wire"]
    for x in (-2.25, 2.25):
        for y in (-1.52, 1.52):
            base.cube(
                "swing_footing",
                (x, y, 0.075),
                (0.48, 0.48, 0.15),
                M["concrete"],
                c,
                0.04,
            )
        base.beam("splayed_aframe_leg", (x, -1.52, 0.13), (x, 0, 2.78), 0.09, metal, c)
        base.beam("splayed_aframe_leg", (x, 1.52, 0.13), (x, 0, 2.78), 0.09, metal, c)
        base.cyl(
            "top_joint_collar",
            (x, 0, 2.78),
            0.17,
            0.38,
            wire,
            c,
            32,
            (math.pi / 2, 0, 0),
            0.012,
        )
        base.cube("gusset_plate", (x, -0.07, 2.48), (0.36, 0.04, 0.32), wire, c, 0.01)
    base.beam("heavy_top_beam", (-2.55, 0, 2.78), (2.55, 0, 2.78), 0.115, metal, c)
    for x in (-1.05, 1.05):
        for dx in (-0.30, 0.30):
            base.torus(
                "hanger_clevis",
                (x + dx, 0, 2.64),
                0.075,
                0.018,
                wire,
                c,
                (math.pi / 2, 0, 0),
            )
            # Double ropes/chains with visible radius and a slight forward rake.
            base.curve_obj(
                "swing_chain_front",
                [(x + dx, -0.035, 2.58), (x + dx, 0.07, 1.02)],
                0.014,
                wire,
                c,
            )
            base.curve_obj(
                "swing_chain_back",
                [(x + dx, 0.065, 2.58), (x + dx, -0.08, 1.02)],
                0.010,
                wire,
                c,
            )
            base.cyl(
                "seat_shackle",
                (x + dx, 0.02, 1.02),
                0.025,
                0.16,
                wire,
                c,
                16,
                (math.pi / 2, 0, 0),
                0.006,
            )
        base.rounded_slab(
            "rubber_belt_seat", x, 0.0, 0.92, 0.92, 0.44, 0.105, 0.08, M["pad"], c
        )
    return c


def create_climbing_frame(params, M, lib):
    c = bpy.data.collections.new(base.P + "MASTER_CLIMBING_FRAME_REBUILT")
    lib["climb_master"] = c.name
    apex = Vector((0, 0, 2.72))
    base_pts = [
        Vector((-2.05, -2.05, 0)),
        Vector((2.05, -2.05, 0)),
        Vector((2.05, 2.05, 0)),
        Vector((-2.05, 2.05, 0)),
    ]
    for p in base_pts:
        base.cube(
            "rope_anchor_block",
            (p.x, p.y, 0.08),
            (0.42, 0.42, 0.16),
            M["concrete"],
            c,
            0.04,
        )
        base.beam(
            "steel_corner_strut",
            (p.x, p.y, 0.14),
            tuple(apex),
            0.062,
            M["play_metal"],
            c,
        )
        base.beam(
            "turnbuckle",
            (p.x * 0.92, p.y * 0.92, 0.17),
            (p.x * 0.76, p.y * 0.76, 0.46),
            0.028,
            M["connector"],
            c,
        )
    base.cyl(
        "top_compression_node",
        tuple(apex),
        0.16,
        0.34,
        M["connector"],
        c,
        36,
        bev=0.015,
    )
    base.torus(
        "top_rope_ring", tuple(apex + Vector((0, 0, -0.08))), 0.28, 0.026, M["wire"], c
    )
    for side in range(4):
        a, b = base_pts[side], base_pts[(side + 1) % 4]
        for i in range(1, 7):
            t = i / 7
            p1 = a.lerp(apex, t)
            p2 = b.lerp(apex, t)
            base.curve_obj(
                "rope_horizontal_band", [tuple(p1), tuple(p2)], 0.026, M["rope"], c
            )
            for j in range(1, 6):
                base.uv_sphere(
                    "rope_intersection_node",
                    p1.lerp(p2, j / 6),
                    0.048,
                    M["connector"],
                    c,
                    16,
                )
        for i in range(1, 6):
            p = a.lerp(b, i / 6)
            base.curve_obj("rope_radial", [tuple(p), tuple(apex)], 0.025, M["rope"], c)
        # Diagonal cross ropes prevent the pyramid reading as a simple cone wireframe.
        for i in (2, 4):
            p = a.lerp(b, i / 6)
            q = base_pts[(side + 2) % 4].lerp(apex, 0.46 + i * 0.035)
            base.curve_obj(
                "rope_diagonal_cross", [tuple(p), tuple(q)], 0.021, M["rope"], c
            )
    return c


def create_site_furniture(M, lib):
    furniture = ORIG_CREATE_SITE_FURNITURE(M, lib)
    # Add a backless edge bench master for the playground perimeter.
    bench = bpy.data.collections.new(base.P + "MASTER_EDGE_BENCH")
    for i in range(6):
        base.cube(
            "bench_seat_slat",
            (-1.05 + i * 0.42, 0, 0.52),
            (0.34, 0.58, 0.085),
            M["timber"],
            bench,
            0.028,
        )
    for x in (-0.92, 0.92):
        base.beam(
            "bench_steel_support",
            (x, -0.20, 0.12),
            (x, 0.20, 0.52),
            0.045,
            M["fence"],
            bench,
        )
        base.cube(
            "bench_ground_plate",
            (x, 0, 0.07),
            (0.34, 0.46, 0.10),
            M["concrete"],
            bench,
            0.025,
        )
    furniture["edge_bench"] = bench
    return furniture


def generate_real_turf(M, T, root):
    c = base.collection("REALISTIC_MUTED_TURF_SYSTEM", root)
    outline = [
        (10.0, -10.1),
        (47.3, -10.1),
        (47.9, -10.7),
        (47.9, -41.3),
        (47.25, -41.9),
        (10.2, -41.9),
        (9.65, -41.25),
        (9.65, -10.8),
    ]
    base.irregular_lawn("continuous_muted_turf", outline, 0.132, 0.13, M["turf"], c)
    rng = random.Random(1007)
    for i in range(34):
        x = rng.uniform(10.8, 47.0)
        y = rng.uniform(-40.8, -10.8)
        sx = rng.uniform(0.9, 2.4)
        sy = rng.uniform(0.35, 0.95)
        if os.environ.get("C2W_FULL_02") == "1" and (
            (14.8 < x < 47.2 and -41.2 < y < -21.2)
            or (9.8 < x < 21.4 and -22.4 < y < -10.4)
            or (31.0 < x < 48.0 and -22.5 < y < -10.0)
        ):
            continue
        variation_mat = (
            M["soil"]
            if os.environ.get("C2W_FLOWERBED_LANDSCAPE") == "1"
            else (M["grass_blade"] if i % 2 else M["soil"])
        )
        base.rounded_slab(
            "large_scale_lawn_color_variation",
            x,
            y,
            sx,
            sy,
            0.199,
            0.006,
            0.28,
            variation_mat,
            c,
        )
    for x, y, sx, sy in (
        (28.8, -9.92, 18.5, 0.10),
        (28.8, -42.05, 18.5, 0.10),
        (9.55, -26, 0.10, 15.2),
        (48.0, -26, 0.10, 15.2),
    ):
        base.cube(
            "soft_soil_turf_edge",
            (x, y, 0.10),
            (sx * 2, sy * 2, 0.10),
            M["soil"],
            c,
            0.03,
        )
    instc = base.collection("GRASS_CLUMP_DENSITY_VARIATION", root)
    placements = []
    for ix in range(18):
        for iy in range(15):
            if (ix + 2 * iy) % 11 == 0:
                continue
            x = 10.75 + ix * 2.12 + ((iy % 3) - 1) * 0.06
            y = -41.0 + iy * 2.12 + ((ix % 4) - 1.5) * 0.05
            if os.environ.get("C2W_FULL_02") == "1" and (
                (14.8 < x < 47.2 and -41.2 < y < -21.2)
                or (9.8 < x < 21.4 and -22.4 < y < -10.4)
                or (31.0 < x < 48.0 and -22.5 < y < -10.0)
            ):
                continue
            scale = 0.88 + ((ix * 13 + iy * 7) % 9) * 0.025
            placements.append((x, y, 0.130, (ix * 17 + iy * 31) % 9 * 0.07, scale))
    for i, p in enumerate(placements):
        base.instance(
            T["grass_a"] if (i % 5) else T["grass_b"],
            f"varied_lawn_tile:{i}",
            p[:3],
            instc,
            p[3],
            p[4],
        )
    return len(placements)


def create_playground_safety_surface(params, M, root):
    c = base.collection("PLAYGROUND_EPDM_CONSTRUCTION", root)
    cx, cy = 15.6, -16.7
    W, L = params["playground_width"], params["playground_length"]
    base.rounded_slab(
        "compacted_subbase",
        cx,
        cy,
        W + 0.72,
        L + 0.72,
        0.155,
        0.24,
        0.70,
        M["concrete"],
        c,
    )
    base.rounded_slab(
        "shockpad_layer", cx, cy, W + 0.36, L + 0.36, 0.270, 0.11, 0.58, M["joint"], c
    )
    base.rounded_slab(
        "epdm_main_pour", cx, cy, W, L, 0.345, 0.105, 0.52, M["rubber"], c
    )
    base.rounded_slab(
        "epdm_slide_zone",
        cx - 2.9,
        cy + 2.25,
        3.7,
        3.15,
        0.402,
        0.018,
        0.62,
        M["rubber3"],
        c,
    )
    base.rounded_slab(
        "epdm_swing_fall_zone",
        cx + 2.55,
        cy - 2.75,
        4.25,
        3.25,
        0.405,
        0.018,
        0.78,
        M["rubber2"],
        c,
    )
    base.surface_speckles(
        "epdm_black_granules",
        cx,
        cy,
        W - 0.45,
        L - 0.45,
        0.414,
        620,
        M["aggregate"],
        c,
        1010,
        rx=(0.005, 0.016),
    )
    for x in (cx - 2.6, cx, cx + 2.6):
        base.line_ribbon(
            "epdm_control_joint",
            [(x, cy - L / 2 + 0.34), (x, cy + L / 2 - 0.34)],
            0.018,
            0.420,
            M["joint"],
            c,
        )
    for y in (cy - 2.55, cy, cy + 2.55):
        base.line_ribbon(
            "epdm_control_joint",
            [(cx - W / 2 + 0.34, y), (cx + W / 2 - 0.34, y)],
            0.018,
            0.420,
            M["joint"],
            c,
        )
    for x, y, sx, sy in (
        (cx, cy - L / 2, W / 2, 0.035),
        (cx, cy + L / 2, W / 2, 0.035),
        (cx - W / 2, cy, 0.035, L / 2),
        (cx + W / 2, cy, 0.035, L / 2),
    ):
        base.cube(
            "aluminum_edge_trim",
            (x, y, 0.425),
            (sx * 2, sy * 2, 0.08),
            M["roof_edge"],
            c,
            0.008,
        )
    return c


def generate_playground(params, M, T, root):
    create_playground_safety_surface(params, M, root)
    c = base.collection("PLAYGROUND_ASSET_INSTANCES", root)
    base.instance(T["slide"], "slide_playset", (14.0, -15.55, 0.43), c, math.pi)
    base.instance(T["swing"], "swing_set", (18.2, -20.35, 0.43), c, 0)
    base.instance(T["climb"], "climbing_frame", (12.1, -20.55, 0.43), c, 0.25)
    pc = base.collection("PLAYGROUND_PAVEMENT_TRANSITIONS", root)
    base.rounded_slab(
        "parent_path", 21.45, -20.8, 10.3, 1.85, 0.235, 0.15, 0.32, M["paving"], pc
    )
    base.rounded_slab(
        "entry_path_to_gate",
        25.8,
        -23.15,
        2.15,
        4.8,
        0.235,
        0.15,
        0.28,
        M["paving"],
        pc,
    )
    for x, y, sx, sy in (
        (21.45, -19.82, 5.15, 0.085),
        (21.45, -21.82, 5.15, 0.085),
        (24.65, -23.15, 0.085, 2.4),
        (26.95, -23.15, 0.085, 2.4),
    ):
        base.cube(
            "path_curb", (x, y, 0.325), (sx * 2, sy * 2, 0.18), M["concrete"], pc, 0.022
        )
    return c


def populate_playground_details(M, T, root):
    c = base.collection("PLAYGROUND_FUNCTION_DETAILS", root)
    for i, bx in enumerate((12.0, 18.9)):
        base.instance(T["bench"], f"guardian_back_bench:{i}", (bx, -22.85, 0.19), c, 0)
    base.instance(
        T["edge_bench"], "quiet_edge_bench", (10.55, -18.0, 0.19), c, math.pi / 2
    )
    base.instance(T["bin"], "entry_trash_bin", (20.55, -21.9, 0.19), c, 0)
    base.instance(T["lamp"], "edge_light", (10.35, -12.1, 0.19), c, -math.pi / 2)
    base.instance(
        T["sign"], "playground_rules_board", (10.35, -13.25, 0.19), c, math.pi / 2
    )
    for i, p in enumerate(
        ((20.95, -21.75, math.pi / 2), (15.6, -11.72, 0), (10.62, -21.1, math.pi / 2))
    ):
        base.instance(
            T["drain"], f"playground_edge_drain:{i}", (p[0], p[1], 0.405), c, p[2]
        )
    for a0 in range(0, 360, 30):
        a = math.radians(a0)
        b = math.radians(a0 + 27)
        base.beam(
            "tree_pit_edge",
            (19.5 + 1.15 * math.cos(a), -14.2 + 1.15 * math.sin(a), 0.28),
            (19.5 + 1.15 * math.cos(b), -14.2 + 1.15 * math.sin(b), 0.28),
            0.075,
            M["concrete"],
            c,
        )
    return c


def add_service_building_details(M, root):
    c = base.collection("SERVICE_BUILDING_REBUILT_FACADE", root)
    # A complete lightweight overlay masks the retained all44_04 white-box massing.
    base.cube(
        "stucco_main_wall_front",
        (36.7, -11.36, 2.30),
        (18.35, 0.18, 4.25),
        M["wall_stucco"],
        c,
        0.035,
    )
    base.cube(
        "stucco_side_wall_w",
        (27.55, -16.88, 2.25),
        (0.18, 10.55, 4.10),
        M["wall_stucco"],
        c,
        0.035,
    )
    base.cube(
        "stucco_side_wall_e",
        (45.85, -16.88, 2.25),
        (0.18, 10.55, 4.10),
        M["wall_stucco"],
        c,
        0.035,
    )
    base.cube(
        "rear_stucco_band",
        (36.7, -22.20, 2.25),
        (18.3, 0.16, 4.0),
        M["wall_stucco"],
        c,
        0.035,
    )
    base.cube(
        "continuous_plinth",
        (36.7, -11.19, 0.43),
        (18.65, 0.36, 0.55),
        M["wall_weather"],
        c,
        0.025,
    )
    for x, y, sx, sy in (
        (36.7, -11.05, 9.5, 0.18),
        (36.7, -22.28, 9.4, 0.15),
        (27.43, -16.85, 0.15, 5.35),
        (45.98, -16.85, 0.15, 5.35),
    ):
        base.cube(
            "building_base_plinth_return",
            (x, y, 0.40),
            (sx, sy, 0.46),
            M["wall_weather"],
            c,
            0.025,
        )

    # Recessed entrance with real leaf, frame, threshold, step and small ramp.
    base.cube(
        "entrance_recess_shadow",
        (36.7, -11.05, 1.55),
        (2.25, 0.12, 2.70),
        M["joint"],
        c,
        0.018,
    )
    base.cube(
        "main_door_leaf", (36.7, -10.87, 1.43), (1.24, 0.09, 2.28), M["door"], c, 0.025
    )
    for x in (36.03, 37.37):
        base.cube(
            "door_jamb",
            (x, -10.80, 1.48),
            (0.11, 0.18, 2.50),
            M["trim_light"],
            c,
            0.012,
        )
    base.cube(
        "door_header",
        (36.7, -10.80, 2.77),
        (1.55, 0.18, 0.11),
        M["trim_light"],
        c,
        0.012,
    )
    base.cyl(
        "door_pull",
        (37.15, -10.73, 1.40),
        0.018,
        0.55,
        M["wire"],
        c,
        16,
        (0, math.pi / 2, 0),
        0.004,
    )
    base.cube(
        "entrance_step",
        (36.7, -10.55, 0.20),
        (2.15, 0.70, 0.15),
        M["concrete"],
        c,
        0.025,
    )
    base.rounded_slab(
        "accessible_entry_ramp",
        34.7,
        -10.55,
        2.2,
        0.78,
        0.165,
        0.09,
        0.14,
        M["concrete"],
        c,
    )
    base.cube(
        "canopy_slab_with_thickness",
        (36.7, -10.56, 3.13),
        (2.85, 1.12, 0.20),
        M["roof_edge"],
        c,
        0.025,
    )
    for x in (35.48, 37.92):
        base.beam(
            "canopy_tie_rod", (x, -10.68, 3.04), (x, -11.30, 3.55), 0.025, M["wire"], c
        )

    # Front and side windows with recess, frames, mullions and sills.
    for i, x in enumerate((30.65, 33.35, 40.05, 42.75)):
        base.cube(
            "window_recess_shadow",
            (x, -11.14, 2.15),
            (1.72, 0.10, 1.36),
            M["joint"],
            c,
            0.01,
        )
        base.cube(
            "window_glazing",
            (x, -10.98, 2.15),
            (1.46, 0.045, 1.10),
            M["glass"],
            c,
            0.012,
        )
        for dx in (-0.78, 0, 0.78):
            base.cube(
                "window_vertical_frame",
                (x + dx, -10.93, 2.15),
                (0.055, 0.10, 1.26),
                M["roof_edge"],
                c,
                0.008,
            )
        for z in (1.53, 2.77):
            base.cube(
                "window_horizontal_frame",
                (x, -10.93, z),
                (1.66, 0.10, 0.055),
                M["roof_edge"],
                c,
                0.008,
            )
        base.cube(
            "window_sill",
            (x, -10.82, 1.43),
            (1.90, 0.32, 0.075),
            M["trim_light"],
            c,
            0.014,
        )
    for y in (-14.4, -18.4):
        base.cube(
            "side_window_recess",
            (45.99, y, 2.12),
            (0.10, 1.60, 1.22),
            M["joint"],
            c,
            0.01,
        )
        base.cube(
            "side_window_glass",
            (46.08, y, 2.12),
            (0.04, 1.34, 0.98),
            M["glass"],
            c,
            0.01,
        )
        base.cube(
            "side_window_sill",
            (46.14, y, 1.47),
            (0.25, 1.62, 0.07),
            M["trim_light"],
            c,
            0.012,
        )

    # Roof thickness, parapet, fascia/flashing, drains, vents and realistic equipment.
    base.cube(
        "thick_roof_membrane",
        (36.7, -16.85, 4.66),
        (18.75, 10.85, 0.20),
        M["roof"],
        c,
        0.025,
    )
    for x, y, sx, sy in (
        (36.7, -11.37, 9.55, 0.11),
        (36.7, -22.34, 9.55, 0.11),
        (27.32, -16.85, 0.11, 5.45),
        (46.08, -16.85, 0.11, 5.45),
    ):
        base.cube(
            "parapet_fascia_flashing",
            (x, y, 4.88),
            (sx * 2, sy * 2, 0.34),
            M["roof_edge"],
            c,
            0.018,
        )
    for x in (29.0, 44.25):
        base.cube(
            "scupper_box",
            (x, -11.18, 4.52),
            (0.44, 0.24, 0.18),
            M["roof_edge"],
            c,
            0.012,
        )
        base.cyl(
            "downspout",
            (x, -11.05, 2.18),
            0.043,
            4.35,
            M["roof_edge"],
            c,
            24,
            bev=0.008,
        )
        base.cube(
            "downspout_shoe",
            (x, -10.98, 0.38),
            (0.28, 0.18, 0.18),
            M["roof_edge"],
            c,
            0.012,
        )
    for x, y in ((32.0, -18.4), (39.6, -15.0)):
        base.cyl(
            "roof_vent_pipe",
            (x, y, 5.04),
            0.105,
            0.52,
            M["roof_edge"],
            c,
            28,
            bev=0.008,
        )
        base.cyl("vent_cap", (x, y, 5.34), 0.18, 0.08, M["louver"], c, 28, bev=0.012)
    base.cube(
        "hvac_support_rail",
        (42.7, -20.55, 4.86),
        (1.75, 0.12, 0.12),
        M["roof_edge"],
        c,
        0.01,
    )
    base.cube(
        "hvac_support_rail",
        (42.7, -21.22, 4.86),
        (1.75, 0.12, 0.12),
        M["roof_edge"],
        c,
        0.01,
    )
    base.cube(
        "hvac_housing", (42.7, -20.88, 5.18), (1.55, 0.92, 0.52), M["louver"], c, 0.035
    )
    for i in range(7):
        base.cube(
            "hvac_grille_slat",
            (42.7, -20.40, 5.00 + i * 0.065),
            (1.22, 0.026, 0.025),
            M["wire"],
            c,
            0.004,
        )
    base.torus("hvac_fan_ring", (42.7, -20.88, 5.47), 0.32, 0.018, M["wire"], c)
    for a in (0, math.pi / 2):
        base.cube(
            "hvac_fan_blade",
            (42.7, -20.88, 5.47),
            (0.52, 0.045, 0.014),
            M["wire"],
            c,
            0.004,
            a,
        )
    base.curve_obj(
        "hvac_conduit",
        [(41.85, -20.88, 5.12), (41.35, -20.88, 5.02), (41.35, -19.8, 4.88)],
        0.026,
        M["roof_edge"],
        c,
    )
    base.cube(
        "wall_pack_light",
        (34.55, -10.82, 2.88),
        (0.34, 0.16, 0.16),
        M["roof_edge"],
        c,
        0.018,
    )
    base.cube(
        "wall_pack_lens",
        (34.55, -10.70, 2.78),
        (0.26, 0.035, 0.105),
        M["glass"],
        c,
        0.008,
    )
    base.cube(
        "utility_box_side",
        (28.04, -14.7, 1.18),
        (0.13, 0.70, 0.95),
        M["louver"],
        c,
        0.018,
    )
    for z in (0.92, 1.18, 1.44):
        base.cube(
            "utility_box_louver",
            (27.95, -14.7, z),
            (0.035, 0.54, 0.025),
            M["wire"],
            c,
            0.004,
        )
    return c


def render_outputs(cfg, cam):
    base.aim(cam, (6, -6, 32), (27.5, -24.5, 1.8), 34)
    base.render(
        cfg.output / "activity_zone_overview.png",
        (1280, 720),
        10 if cfg.quality == "final" else 2,
    )
    if cfg.quality == "final":
        base.aim(cam, (24.5, -5.8, 9.5), (36.8, -12.7, 2.1), 52)
        base.render(cfg.output / "small_building_close.png", (1280, 720), 12)
        base.aim(cam, (4, -6, 12), (15.5, -17, 1.3), 48)
        base.render(cfg.output / "playground_close.png", (1280, 720), 12)
        base.aim(cam, (7.0, -24.4, 8.2), (15.7, -18.3, 1.25), 52)
        base.render(cfg.output / "playground_side.png", (1280, 720), 12)


def main():
    cfg = base.args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    removed = remove_old_court_playground()
    tune_retained_materials()
    M = create_shared_materials()
    lib, T = base.prepare_court_playground_asset_library(M)
    root = base.collection("COURT_PLAYGROUND_REBUILD")
    grass_instances = generate_real_turf(M, T, root)
    base.generate_court(
        {
            "court_length": 28,
            "court_width": 15,
            "line_width": 0.075,
            "corner_radius": 0.35,
            "surface_thickness": 0.16,
            "border_width": 0.8,
            "fence_height": 3.4,
            "fence_post_spacing": 3,
            "court_type": "basketball",
            "hoop_count": 2,
            "gate_count": 1,
            "light_pole_count": 4,
        },
        M,
        T,
        root,
    )
    generate_playground(
        {
            "playground_width": 10,
            "playground_length": 10,
            "safety_surface_type": "rubber_tile",
            "play_module_count": 3,
            "bench_count": 2,
            "shade_count": 1,
            "fence_type": "low",
            "age_group": "5-12",
            "path_connection_count": 2,
            "thickness": 0.14,
        },
        M,
        T,
        root,
    )
    base.generate_ground_system(M, T, root)
    base.populate_court_details(M, T, root)
    populate_playground_details(M, T, root)
    add_service_building_details(M, root)

    old = {o: o.hide_render for o in bpy.context.scene.objects}
    for o in bpy.context.scene.objects:
        dep = any(
            c.name.startswith("assets:TreeFactory")
            or c.name.startswith("assets:GenericTreeFactory")
            for c in o.users_collection
        )
        keep = o.name.startswith((base.P, "all44_04:")) or o.type == "LIGHT" or dep
        o.hide_render = not keep
    cam = bpy.context.scene.camera
    render_outputs(cfg, cam)
    for o, h in old.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h

    out = cfg.output / "urban_v3_all44_10.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    inst = [o for o in root.all_objects if o.instance_type == "COLLECTION"]
    stats = {
        "output": str(out),
        "removed_old_objects": removed,
        "master_assets": list(T),
        "collection_instances": len(inst),
        "shared_materials": list(M),
        "focused_passes": [
            "service_building_rebuild",
            "playground_asset_rebuild",
            "epdm_ground_rebuild",
            "muted_grass_variation",
        ],
        "render_outputs": [
            "small_building_close",
            "playground_close",
            "playground_side",
            "activity_zone_overview",
        ],
        "dense_lawn_tile_instances": grass_instances,
        "grass_blades_per_tile": 720,
        "basketball_court_layout_changed": False,
        "boundary_intrusions": [],
        "floating_objects": [],
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_10_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


base.remove_old_court_playground = remove_old_court_playground
base.create_shared_materials = create_shared_materials
base.create_slide_playset = create_slide_playset
base.create_swing_set = create_swing_set
base.create_climbing_frame = create_climbing_frame
base.create_site_furniture = create_site_furniture

if __name__ == "__main__":
    main()
