"""ALL45-01: refined residential-zone generator.

This is the prompt-45-01 continuation of scripts/generate_urban_v3_all45.py.
It keeps the same lightweight procedural base, but upgrades scale, facade
detail, apartment balconies, courtyard density, lawn variation, and integrates
one real Infinigen Indoor house as the near-camera key residence.
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


OUT = ROOT / "infinigen/outputs/urban_v3_all45_01"
INDOOR_BLEND = ROOT / "infinigen/outputs/urban_v3_all41_house_large/scene.blend"
PREFIX = "all45_01:"
RNG = random.Random(4501)
WANT_INDOOR_COLLECTION = lambda c: (
    c == "unique_assets" or c == "skirting" or c.startswith("door_base_elements")
)


def configure_base_module():
    G.ROOT = ROOT
    G.OUT = OUT
    G.PREFIX = PREFIX
    G.RNG = RNG


def add_extra_materials(M):
    M.update(
        {
            "stucco_light": G.material(
                "stucco_light_micrograin", (0.62, 0.60, 0.53), rough=0.88, noise=0.12
            ),
            "stucco_gray": G.material(
                "stucco_gray_micrograin", (0.45, 0.47, 0.45), rough=0.88, noise=0.11
            ),
            "tile_warm": G.brick_material(
                "warm_small_tile_facade",
                (0.53, 0.45, 0.35),
                (0.66, 0.59, 0.48),
                (0.27, 0.25, 0.22),
                scale=13.0,
            ),
            "deep_recess": G.material(
                "deep_window_recess_shadow",
                (0.050, 0.053, 0.052),
                rough=0.80,
                noise=0.02,
            ),
            "curtain_warm": G.material(
                "warm_curtain_proxy",
                (0.70, 0.62, 0.48),
                rough=0.78,
                noise=0.04,
                alpha=0.72,
            ),
            "curtain_cool": G.material(
                "cool_curtain_proxy",
                (0.50, 0.56, 0.58),
                rough=0.78,
                noise=0.04,
                alpha=0.70,
            ),
            "solid_balcony": G.material(
                "painted_balcony_panel", (0.40, 0.41, 0.39), rough=0.72, noise=0.04
            ),
            "glass_balcony": G.material(
                "balcony_frosted_glass", (0.58, 0.70, 0.72), rough=0.18, alpha=0.42
            ),
            "flower": G.material(
                "muted_flower_bed", (0.46, 0.12, 0.11), rough=0.82, noise=0.12
            ),
            "soil": G.material(
                "exposed_garden_soil", (0.20, 0.15, 0.10), rough=0.92, noise=0.18
            ),
        }
    )


def make_extra_masters(M, A):
    def new_coll(name):
        return bpy.data.collections.new(PREFIX + name)

    # Window variants: all reuse a few shared collection masters.
    wide = new_coll("MASTER_wide_house_window")
    G.box(
        "master_wide_recess",
        (0, 0.045, 0),
        (1.86, 0.12, 1.42),
        M["deep_recess"],
        wide,
        bevel=0.005,
    )
    G.box(
        "master_wide_frame",
        (0, -0.015, 0),
        (1.62, 0.10, 1.18),
        M["white_frame"],
        wide,
        bevel=0.006,
    )
    G.box(
        "master_wide_glass_l",
        (-0.39, -0.075, 0),
        (0.68, 0.030, 0.92),
        M["glass"],
        wide,
        bevel=0.003,
    )
    G.box(
        "master_wide_glass_r",
        (0.39, -0.075, 0),
        (0.68, 0.030, 0.92),
        M["glass"],
        wide,
        bevel=0.003,
    )
    G.box(
        "master_wide_mullion",
        (0, -0.105, 0),
        (0.055, 0.055, 1.00),
        M["white_frame"],
        wide,
        bevel=0.002,
    )
    G.box(
        "master_wide_sill",
        (0, -0.135, -0.73),
        (1.92, 0.20, 0.085),
        M["stone"],
        wide,
        bevel=0.005,
    )
    G.box(
        "master_wide_curtain",
        (-0.36, -0.12, 0.03),
        (0.45, 0.025, 0.88),
        M["curtain_warm"],
        wide,
        bevel=0.002,
    )
    A["window_wide"] = wide

    slit = new_coll("MASTER_apartment_slit_window")
    G.box(
        "master_slit_recess",
        (0, 0.035, 0),
        (0.70, 0.10, 1.72),
        M["deep_recess"],
        slit,
        bevel=0.004,
    )
    G.box(
        "master_slit_frame",
        (0, -0.012, 0),
        (0.54, 0.075, 1.48),
        M["frame"],
        slit,
        bevel=0.004,
    )
    G.box(
        "master_slit_glass",
        (0, -0.066, 0.06),
        (0.38, 0.026, 1.16),
        M["glass"],
        slit,
        bevel=0.003,
    )
    G.box(
        "master_slit_sill",
        (0, -0.118, -0.90),
        (0.74, 0.16, 0.065),
        M["stone"],
        slit,
        bevel=0.004,
    )
    A["window_slit"] = slit

    # Balcony modules avoid the previous black-box look.
    metal = new_coll("MASTER_balcony_metal_rail")
    G.box(
        "metal_balcony_slab",
        (0, -0.56, -0.72),
        (2.25, 1.12, 0.13),
        M["concrete"],
        metal,
        bevel=0.006,
    )
    G.box(
        "metal_balcony_edge_trim",
        (0, -1.12, -0.62),
        (2.30, 0.075, 0.18),
        M["gutter"],
        metal,
        bevel=0.004,
    )
    for x in (-0.98, -0.66, -0.33, 0.0, 0.33, 0.66, 0.98):
        G.box(
            f"metal_balcony_bar_{x:.2f}",
            (x, -1.13, -0.18),
            (0.030, 0.050, 0.72),
            M["metal"],
            metal,
            bevel=0.002,
        )
    G.box(
        "metal_balcony_toprail",
        (0, -1.14, 0.22),
        (2.32, 0.070, 0.060),
        M["metal"],
        metal,
        bevel=0.004,
    )
    G.box(
        "metal_balcony_drain",
        (0.86, -1.17, -0.74),
        (0.22, 0.065, 0.035),
        M["gutter"],
        metal,
        bevel=0.002,
    )
    A["balcony_metal"] = metal

    glass = new_coll("MASTER_balcony_glass_mixed")
    G.box(
        "glass_balcony_slab",
        (0, -0.56, -0.72),
        (2.20, 1.08, 0.13),
        M["concrete"],
        glass,
        bevel=0.006,
    )
    G.box(
        "glass_balcony_panel_l",
        (-0.53, -1.12, -0.17),
        (0.86, 0.040, 0.64),
        M["glass_balcony"],
        glass,
        bevel=0.004,
    )
    G.box(
        "glass_balcony_panel_r",
        (0.53, -1.12, -0.17),
        (0.86, 0.040, 0.64),
        M["glass_balcony"],
        glass,
        bevel=0.004,
    )
    G.box(
        "glass_balcony_toprail",
        (0, -1.15, 0.20),
        (2.18, 0.060, 0.055),
        M["metal"],
        glass,
        bevel=0.004,
    )
    for x in (-1.05, 0, 1.05):
        G.box(
            f"glass_balcony_post_{x:.1f}",
            (x, -1.15, -0.18),
            (0.045, 0.055, 0.76),
            M["metal"],
            glass,
            bevel=0.002,
        )
    A["balcony_glass"] = glass

    solid = new_coll("MASTER_balcony_partial_panel")
    G.box(
        "solid_balcony_slab",
        (0, -0.54, -0.72),
        (2.18, 1.02, 0.13),
        M["concrete"],
        solid,
        bevel=0.006,
    )
    G.box(
        "solid_balcony_low_panel",
        (0, -1.05, -0.34),
        (2.12, 0.075, 0.45),
        M["solid_balcony"],
        solid,
        bevel=0.005,
    )
    G.box(
        "solid_balcony_open_rail",
        (0, -1.08, 0.05),
        (2.14, 0.055, 0.32),
        M["metal"],
        solid,
        bevel=0.004,
    )
    for x in (-0.82, -0.41, 0, 0.41, 0.82):
        G.box(
            f"solid_balcony_short_bar_{x:.2f}",
            (x, -1.10, 0.04),
            (0.030, 0.045, 0.36),
            M["metal"],
            solid,
            bevel=0.002,
        )
    A["balcony_solid"] = solid

    planter = new_coll("MASTER_small_balcony_planter")
    G.box(
        "planter_box", (0, 0, 0.11), (0.55, 0.18, 0.18), M["soil"], planter, bevel=0.012
    )
    for i in range(5):
        G.sphere(
            f"planter_leaf_{i}",
            (RNG.uniform(-0.22, 0.22), RNG.uniform(-0.06, 0.06), 0.27),
            0.08,
            M["hedge"],
            planter,
            scale=(1.1, 0.8, 0.6),
            segments=12,
        )
    A["planter"] = planter
    return A


def make_render_collection_root():
    root = G.make_collection("residential_zone_all45_01")
    return root


def bbox_world(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for obj in objs:
        if obj.type != "MESH" or not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            mn.x = min(mn.x, p.x)
            mn.y = min(mn.y, p.y)
            mn.z = min(mn.z, p.z)
            mx.x = max(mx.x, p.x)
            mx.y = max(mx.y, p.y)
            mx.z = max(mx.z, p.z)
    return mn, mx


def imported_in_collection(obj, token):
    return any(token in c.name for c in obj.users_collection)


def add_segmented_front_wall(name, origin, yaw, w, h, y, M, coll, openings, wall_mat):
    """Wall panels around openings; front windows are actual voids, not decals."""
    zbase = 0.35
    # Split facade into floor-height rows so large overlapping panels do not close holes.
    rows = [
        (0.35, 3.10, [op for op in openings if op[1] < 3.2]),
        (3.10, h, [op for op in openings if op[1] >= 3.2]),
    ]
    for ri, (z0, z1, ops) in enumerate(rows):
        intervals = [(-w / 2, w / 2)]
        for cx, cz, ow, oh in ops:
            new_intervals = []
            ox0, ox1 = cx - ow / 2, cx + ow / 2
            for a, b in intervals:
                if ox1 <= a or ox0 >= b:
                    new_intervals.append((a, b))
                else:
                    if ox0 > a:
                        new_intervals.append((a, ox0))
                    if ox1 < b:
                        new_intervals.append((ox1, b))
            intervals = new_intervals
        for ii, (a, b) in enumerate(intervals):
            if b - a > 0.08:
                G.local_box(
                    f"{name}_front_wall_row{ri}_strip{ii}",
                    origin,
                    yaw,
                    ((a + b) / 2, y, (z0 + z1) / 2),
                    (b - a, 0.22, z1 - z0),
                    wall_mat,
                    coll,
                    bevel=0.006,
                )
        for oi, (cx, cz, ow, oh) in enumerate(ops):
            below = max(0.0, cz - oh / 2 - z0)
            above = max(0.0, z1 - (cz + oh / 2))
            if below > 0.08:
                G.local_box(
                    f"{name}_front_below_opening_{ri}_{oi}",
                    origin,
                    yaw,
                    (cx, y, z0 + below / 2),
                    (ow, 0.22, below),
                    wall_mat,
                    coll,
                    bevel=0.006,
                )
            if above > 0.08:
                G.local_box(
                    f"{name}_front_above_opening_{ri}_{oi}",
                    origin,
                    yaw,
                    (cx, y, z1 - above / 2),
                    (ow, 0.22, above),
                    wall_mat,
                    coll,
                    bevel=0.006,
                )


def add_roof_flash_and_vents(name, origin, yaw, w, d, z, M, coll, vent_count=1):
    for i in range(vent_count):
        lx = RNG.uniform(-w * 0.28, w * 0.28)
        ly = RNG.choice((-0.18, 0.22)) * d
        G.cylinder(
            f"{name}_roof_vent_{i}",
            G.transform_point(origin, yaw, (lx, ly, z + 0.36)),
            0.12,
            0.44,
            M["gutter"],
            coll,
            vertices=16,
            bevel=0.004,
        )
        G.local_box(
            f"{name}_roof_vent_flashing_{i}",
            origin,
            yaw,
            (lx, ly, z + 0.13),
            (0.42, 0.36, 0.055),
            M["gutter"],
            coll,
            bevel=0.004,
        )


def add_house_shell(name, origin, yaw, p, M, A, root, indoor=False, imported_bbox=None):
    coll = G.make_collection("house_" + name, root)
    w, d, floors = p["w"], p["d"], p["floors"]
    h = 3.35 * floors
    wall_mat = M[p["wall"]]
    front_y = -d / 2
    back_y = d / 2

    G.local_box(
        f"{name}_foundation_plinth",
        origin,
        yaw,
        (0, 0, 0.22),
        (w + 0.65, d + 0.56, 0.44),
        M["stone"],
        coll,
        bevel=0.014,
    )
    G.local_box(
        f"{name}_back_wall",
        origin,
        yaw,
        (0, back_y, h / 2),
        (w, 0.24, h),
        wall_mat,
        coll,
        bevel=0.010,
    )
    G.local_box(
        f"{name}_left_wall",
        origin,
        yaw,
        (-w / 2, 0, h / 2),
        (0.24, d, h),
        wall_mat,
        coll,
        bevel=0.010,
    )
    G.local_box(
        f"{name}_right_wall",
        origin,
        yaw,
        (w / 2, 0, h / 2),
        (0.24, d, h),
        wall_mat,
        coll,
        bevel=0.010,
    )
    G.local_box(
        f"{name}_floor_band",
        origin,
        yaw,
        (0, front_y - 0.03, 3.27),
        (w + 0.18, 0.14, 0.12),
        M["stone"],
        coll,
        bevel=0.004,
    )
    G.local_box(
        f"{name}_corner_trim_left",
        origin,
        yaw,
        (-w / 2 - 0.04, front_y - 0.02, h / 2),
        (0.18, 0.18, h),
        M["stone"],
        coll,
        bevel=0.004,
    )
    G.local_box(
        f"{name}_corner_trim_right",
        origin,
        yaw,
        (w / 2 + 0.04, front_y - 0.02, h / 2),
        (0.18, 0.18, h),
        M["stone"],
        coll,
        bevel=0.004,
    )

    openings = [(p["door_x"], 1.42, 1.38, 2.35)]
    for wx, wz, scale_key in p["front_windows"]:
        ww = 1.95 if scale_key == "wide" else 1.45
        wh = 1.38 if wz < 3.2 else 1.22
        openings.append((wx, wz, ww, wh))
    add_segmented_front_wall(
        name, origin, yaw, w, h, front_y - 0.02, M, coll, openings, wall_mat
    )

    # Entry composition.
    G.collection_instance(
        A["door"],
        f"{name}_entry_door",
        G.transform_point(origin, yaw, (p["door_x"], front_y - 0.16, 1.42)),
        coll,
        yaw,
    )
    G.local_box(
        f"{name}_porch_platform",
        origin,
        yaw,
        (p["door_x"], front_y - 0.90, 0.18),
        (2.20, 1.36, 0.30),
        M["concrete"],
        coll,
        bevel=0.016,
    )
    G.local_box(
        f"{name}_porch_step",
        origin,
        yaw,
        (p["door_x"], front_y - 1.68, 0.085),
        (2.42, 0.44, 0.17),
        M["stone"],
        coll,
        bevel=0.010,
    )
    G.local_box(
        f"{name}_porch_canopy",
        origin,
        yaw,
        (p["door_x"], front_y - 0.62, 2.80),
        (2.35, 1.42, 0.16),
        M[p.get("canopy_mat", "roof_metal")],
        coll,
        bevel=0.010,
    )
    for sx in (-0.92, 0.92):
        G.beam(
            f"{name}_porch_brace_{sx}",
            G.transform_point(origin, yaw, (p["door_x"] + sx, front_y - 0.25, 2.68)),
            G.transform_point(
                origin, yaw, (p["door_x"] + sx * 0.58, front_y - 1.05, 2.18)
            ),
            0.030,
            M["metal"],
            coll,
        )

    # Windows and lightweight interior proxies for exterior-only houses.
    for i, (wx, wz, scale_key) in enumerate(p["front_windows"]):
        master = A["window_wide"] if scale_key == "wide" else A["window"]
        G.collection_instance(
            master,
            f"{name}_front_window_{i}",
            G.transform_point(origin, yaw, (wx, front_y - 0.17, wz)),
            coll,
            yaw,
            (1, 1, 1),
        )
        if not indoor:
            G.local_box(
                f"{name}_interior_proxy_wall_{i}",
                origin,
                yaw,
                (wx, front_y + 0.42, wz),
                (1.35, 0.05, 1.06),
                M["curtain_warm" if i % 2 == 0 else "curtain_cool"],
                coll,
                bevel=0.002,
            )
            if i % 3 == 0:
                G.local_box(
                    f"{name}_furniture_silhouette_{i}",
                    origin,
                    yaw,
                    (wx - 0.25, front_y + 0.62, wz - 0.46),
                    (0.82, 0.26, 0.30),
                    M["wood"],
                    coll,
                    bevel=0.008,
                )

    side_windows = p.get("side_windows", [])
    for i, (side, ly, z, sc) in enumerate(side_windows):
        lx = -w / 2 - 0.15 if side == "left" else w / 2 + 0.15
        rot = yaw + math.pi / 2 if side == "left" else yaw - math.pi / 2
        G.collection_instance(
            A["window"],
            f"{name}_side_window_{i}",
            G.transform_point(origin, yaw, (lx, ly, z)),
            coll,
            rot,
            sc,
        )

    if p.get("small_balcony"):
        bx, bz = p["small_balcony"]
        G.local_box(
            f"{name}_small_balcony_door_recess",
            origin,
            yaw,
            (bx, front_y - 0.03, bz),
            (1.05, 0.14, 1.80),
            M["deep_recess"],
            coll,
            bevel=0.004,
        )
        G.collection_instance(
            A["window_tall"],
            f"{name}_small_balcony_door",
            G.transform_point(origin, yaw, (bx, front_y - 0.16, bz)),
            coll,
            yaw,
            (0.82, 0.82, 0.92),
        )
        G.collection_instance(
            A["balcony_metal"],
            f"{name}_small_balcony",
            G.transform_point(origin, yaw, (bx, front_y - 0.44, bz - 0.05)),
            coll,
            yaw,
            (0.70, 0.74, 0.72),
        )

    G.roof_mesh(
        f"{name}_{p['roof']}_roof",
        origin,
        yaw,
        w,
        d,
        h + 0.04,
        p["roof"],
        M[p["roof_mat"]],
        coll,
        overhang=0.66,
        rise=p["rise"],
        thickness=0.28,
    )
    add_roof_flash_and_vents(
        name,
        origin,
        yaw,
        w,
        d,
        h + p["rise"] * 0.68,
        M,
        coll,
        vent_count=p.get("roof_vents", 1),
    )
    G.local_box(
        f"{name}_soffit_front",
        origin,
        yaw,
        (0, front_y - 0.56, h - 0.02),
        (w + 1.15, 0.22, 0.12),
        M["fascia"],
        coll,
        bevel=0.004,
    )
    G.local_box(
        f"{name}_soffit_back",
        origin,
        yaw,
        (0, back_y + 0.56, h - 0.02),
        (w + 1.15, 0.22, 0.12),
        M["fascia"],
        coll,
        bevel=0.004,
    )

    # Services attached to functional facades.
    G.collection_instance(
        A["ac"],
        f"{name}_ac_unit_ground",
        G.transform_point(origin, yaw, (w / 2 + 0.32, -0.8, 1.35)),
        coll,
        yaw + math.pi / 2,
        (1.05, 1.05, 1.05),
    )
    if floors == 2:
        G.collection_instance(
            A["ac"],
            f"{name}_ac_unit_upper",
            G.transform_point(origin, yaw, (-w / 2 - 0.32, 1.0, 4.40)),
            coll,
            yaw - math.pi / 2,
            (0.86, 0.86, 0.86),
        )
    G.collection_instance(
        A["utility"],
        f"{name}_utility_meter",
        G.transform_point(origin, yaw, (w / 2 + 0.35, d * 0.22, 0)),
        coll,
        yaw + math.pi / 2,
    )
    G.collection_instance(
        A["mailbox"],
        f"{name}_mailbox",
        G.transform_point(origin, yaw, (p["door_x"] - 1.36, front_y - 2.05, 0)),
        coll,
        yaw,
    )

    # Yard: larger and directly tied to entrance.
    yx0, yx1, yy0, yy1 = p["yard"]
    pts = [
        G.transform_point(origin, yaw, (yx0, yy0, 0))[:2],
        G.transform_point(origin, yaw, (yx1, yy0, 0))[:2],
        G.transform_point(origin, yaw, (yx1, yy1, 0))[:2],
        G.transform_point(origin, yaw, (yx0, yy1, 0))[:2],
    ]
    G.poly_prism(
        f"{name}_patchy_private_lawn_base",
        pts,
        0.015,
        0.035,
        M["lawn"],
        coll,
        bevel=0.012,
    )
    for pi in range(5):
        px = RNG.uniform(yx0 + 0.7, yx1 - 0.7)
        py = RNG.uniform(yy0 + 0.7, yy1 - 0.7)
        G.local_box(
            f"{name}_lawn_color_patch_{pi}",
            origin,
            yaw,
            (px, py, 0.045),
            (RNG.uniform(1.4, 2.8), RNG.uniform(0.7, 1.5), 0.014),
            M["hedge"] if pi % 2 else M["soil"],
            coll,
            rot=RNG.uniform(-0.5, 0.5),
            bevel=0.12,
            segments=4,
        )
    for seg, p0, p1 in (
        ("back", (yx0, yy1), (yx1, yy1)),
        ("left", (yx0, yy0), (yx0, yy1)),
        ("right", (yx1, yy0), (yx1, yy1)),
    ):
        wp0 = G.transform_point(origin, yaw, (p0[0], p0[1], 0.62))
        wp1 = G.transform_point(origin, yaw, (p1[0], p1[1], 0.62))
        G.beam(
            f"{name}_yard_fence_{seg}",
            wp0,
            wp1,
            0.055,
            M["metal"] if p.get("fence") == "metal" else M["stone"],
            coll,
        )
    for i, (sx, sy, sc) in enumerate(p["shrubs"]):
        G.collection_instance(
            A["shrub"],
            f"{name}_yard_shrub_{i}",
            G.transform_point(origin, yaw, (sx, sy, 0.04)),
            coll,
            yaw + RNG.uniform(-0.4, 0.4),
            (sc, sc, sc),
        )

    if p.get("carport"):
        cx, cy = p.get("carport_xy", (-w / 2 - 1.9, 0.7))
        G.local_box(
            f"{name}_carport_paving",
            origin,
            yaw,
            (cx, cy, 0.04),
            (3.15, 5.05, 0.08),
            M["asphalt"],
            coll,
            bevel=0.010,
        )
        G.local_box(
            f"{name}_carport_roof",
            origin,
            yaw,
            (cx, cy, 2.55),
            (3.15, 5.05, 0.16),
            M["roof_metal"],
            coll,
            bevel=0.008,
        )
        for sx in (-1.36, 1.36):
            for sy in (-2.18, 2.18):
                G.local_box(
                    f"{name}_carport_post_{sx}_{sy}",
                    origin,
                    yaw,
                    (cx + sx, cy + sy, 1.28),
                    (0.10, 0.10, 2.52),
                    M["metal"],
                    coll,
                    bevel=0.004,
                )

    G.local_box(
        f"{name}_entrance_yard_light",
        origin,
        yaw,
        (p["door_x"] + 1.25, front_y - 1.28, 1.15),
        (0.14, 0.12, 0.42),
        M["light"],
        coll,
        bevel=0.008,
    )
    print(
        f"[all45_01] house {name}: floors={floors} w={w:.1f} d={d:.1f} roof={p['roof']} indoor={indoor} objects={len(coll.all_objects)}",
        flush=True,
    )
    return coll


def import_infinigen_indoor_house(origin, yaw, M, A, root):
    if not INDOOR_BLEND.exists():
        raise FileNotFoundError(
            f"Required Infinigen Indoor blend is missing: {INDOOR_BLEND}"
        )

    with bpy.data.libraries.load(str(INDOOR_BLEND), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if WANT_INDOOR_COLLECTION(c)]

    objs = set()
    imported_collections = [c for c in dst.collections if c]
    for coll in imported_collections:
        for obj in coll.all_objects:
            objs.add(obj)

    indoor_coll = G.make_collection("indoor_key_house_true_infinigen", root)
    for obj in objs:
        try:
            indoor_coll.objects.link(obj)
        except RuntimeError:
            pass

    root_empty = bpy.data.objects.new(PREFIX + "key_indoor_house_root", None)
    bpy.context.scene.collection.objects.link(root_empty)
    for obj in objs:
        if obj.parent is None or obj.parent not in objs:
            obj.parent = root_empty
            obj.matrix_parent_inverse = root_empty.matrix_world.inverted()

    bpy.context.view_layer.update()
    mn, mx = bbox_world(objs)
    raw_w = max(0.1, mx.x - mn.x)
    raw_d = max(0.1, mx.y - mn.y)
    target_w, target_d = 10.9, 8.4
    scale = min(target_w / raw_w, target_d / raw_d) * 0.92
    root_empty.rotation_euler.z = yaw
    root_empty.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    mn2, mx2 = bbox_world(objs)
    center = (mn2 + mx2) / 2
    target_center = Vector((origin[0], origin[1], 0))
    root_empty.location += Vector(
        (target_center.x - center.x, target_center.y - center.y, -mn2.z)
    )
    bpy.context.view_layer.update()

    # Imported Infinigen exterior walls can occlude the newly generated facade.
    # Hide only those exterior shell meshes; keep furniture, interior walls and household assets.
    hidden_shells = 0
    for obj in objs:
        if obj.type == "MESH" and imported_in_collection(obj, "room_exterior"):
            obj.hide_viewport = True
            obj.hide_render = True
            hidden_shells += 1
    mn3, mx3 = bbox_world([o for o in objs if o.type == "MESH" and not o.hide_render])

    shell_params = {
        "w": 11.4,
        "d": 8.8,
        "floors": 2,
        "wall": "stucco_light",
        "roof": "mixed",
        "roof_mat": "roof_blue",
        "rise": 1.45,
        "door_x": -2.7,
        "front_windows": [
            (-4.4, 1.62, "wide"),
            (0.25, 1.62, "wide"),
            (3.8, 1.62, "standard"),
            (-3.6, 4.72, "standard"),
            (0.6, 4.72, "wide"),
            (4.1, 4.72, "standard"),
        ],
        "side_windows": [
            ("left", -1.4, 1.65, (0.82, 0.82, 0.86)),
            ("right", 1.9, 4.72, (0.74, 0.74, 0.82)),
        ],
        "small_balcony": (3.6, 4.75),
        "yard": (-6.8, 6.2, -6.7, 5.8),
        "shrubs": [
            (-5.8, -5.7, 0.86),
            (5.3, -5.9, 0.74),
            (5.6, 4.6, 0.70),
            (-5.4, 4.8, 0.68),
        ],
        "fence": "metal",
        "carport": True,
        "carport_xy": (-6.35, 0.9),
        "roof_vents": 2,
    }
    shell = add_house_shell(
        "key_indoor",
        origin,
        yaw,
        shell_params,
        M,
        A,
        root,
        indoor=True,
        imported_bbox=(mn3, mx3),
    )
    print(
        f"[all45_01] imported true Infinigen Indoor key house objects={len(objs)} hidden_exterior_shells={hidden_shells}",
        flush=True,
    )
    return indoor_coll, shell


def add_exterior_only_houses(M, A, root):
    templates = [
        dict(
            w=10.2,
            d=8.0,
            floors=2,
            wall="tile_warm",
            roof="hip",
            roof_mat="roof_brown",
            rise=1.35,
            door_x=1.9,
            front_windows=[
                (-3.5, 1.62, "wide"),
                (0.2, 1.62, "standard"),
                (3.8, 1.62, "standard"),
                (-2.8, 4.70, "standard"),
                (1.5, 4.70, "wide"),
            ],
            side_windows=[("right", 1.0, 1.62, (0.78, 0.78, 0.82))],
            yard=(-5.9, 5.8, -5.7, 5.2),
            shrubs=[(-5.0, -4.7, 0.74), (4.8, -4.8, 0.66), (4.9, 4.1, 0.66)],
            fence="stone",
            carport=True,
            carport_xy=(-5.7, 0.2),
            roof_vents=1,
        ),
        dict(
            w=9.4,
            d=7.4,
            floors=2,
            wall="stucco_gray",
            roof="gable",
            roof_mat="roof_blue",
            rise=1.42,
            door_x=-1.4,
            front_windows=[
                (-3.4, 1.62, "standard"),
                (2.2, 1.62, "wide"),
                (-2.9, 4.65, "standard"),
                (2.6, 4.65, "standard"),
            ],
            side_windows=[
                ("left", -0.8, 1.62, (0.72, 0.72, 0.80)),
                ("right", 1.8, 4.65, (0.72, 0.72, 0.80)),
            ],
            small_balcony=(2.4, 4.65),
            yard=(-5.5, 5.3, -5.6, 5.0),
            shrubs=[(-4.7, -4.8, 0.70), (4.2, -4.5, 0.66), (-4.2, 4.2, 0.60)],
            fence="metal",
            carport=False,
            roof_vents=2,
        ),
        dict(
            w=8.8,
            d=7.0,
            floors=2,
            wall="cream",
            roof="mixed",
            roof_mat="roof_blue",
            rise=1.34,
            door_x=0.2,
            front_windows=[
                (-3.0, 1.58, "wide"),
                (3.0, 1.58, "standard"),
                (-2.7, 4.55, "standard"),
                (2.7, 4.55, "wide"),
            ],
            side_windows=[("left", 1.6, 1.60, (0.76, 0.76, 0.82))],
            yard=(-5.2, 5.0, -5.4, 4.8),
            shrubs=[(-4.4, -4.5, 0.68), (4.1, -4.2, 0.64), (4.2, 3.8, 0.62)],
            fence="metal",
            carport=True,
            carport_xy=(-5.2, 0.8),
            roof_vents=1,
        ),
        dict(
            w=9.8,
            d=6.9,
            floors=1,
            wall="pale_green",
            roof="hip",
            roof_mat="roof_metal",
            rise=1.05,
            door_x=-2.2,
            front_windows=[
                (-4.0, 1.52, "standard"),
                (0.8, 1.52, "wide"),
                (3.9, 1.52, "standard"),
            ],
            side_windows=[("right", 1.4, 1.50, (0.72, 0.72, 0.78))],
            yard=(-5.8, 5.6, -5.2, 4.7),
            shrubs=[(-4.8, -4.2, 0.66), (4.7, -4.0, 0.60), (4.8, 3.7, 0.58)],
            fence="stone",
            carport=False,
            roof_vents=1,
        ),
    ]
    placements = [
        ("large_south", (11.5, -18.2, 0), math.radians(-8), 0),
        ("medium_east", (26.0, -4.8, 0), math.radians(16), 1),
        ("medium_north", (14.8, 15.4, 0), math.radians(-20), 2),
        ("compact_north", (-2.6, 18.7, 0), math.radians(10), 3),
        ("medium_west", (-19.5, 13.6, 0), math.radians(-14), 1),
        ("small_west", (-28.0, -2.8, 0), math.radians(8), 3),
    ]
    out = []
    for label, origin, yaw, ti in placements:
        p = dict(templates[ti])
        p["w"] *= 1 + RNG.uniform(-0.035, 0.04)
        p["d"] *= 1 + RNG.uniform(-0.035, 0.035)
        p["rise"] *= 1 + RNG.uniform(-0.04, 0.04)
        out.append(add_house_shell(label, origin, yaw, p, M, A, root, indoor=False))
    return out


def add_refined_site(M, A, root):
    site = G.make_collection("site_courtyards_and_landscape", root)
    outline = [
        (-38, -25),
        (-4, -28),
        (26, -20),
        (35, 1),
        (26, 24),
        (-8, 29),
        (-34, 18),
        (-41, -6),
    ]
    G.poly_prism(
        "larger_irregular_residential_ground",
        outline,
        -0.08,
        0.10,
        M["ground"],
        site,
        bevel=0.04,
    )

    # Patchy courtyard: lawn is not a single saturated plane.
    lawn_outline = [
        (-13, -8),
        (-2, -13),
        (12, -9),
        (20, 1),
        (14, 12),
        (2, 15),
        (-11, 9),
        (-18, 0),
    ]
    G.poly_prism(
        "shared_courtyard_patchy_lawn",
        lawn_outline,
        0.014,
        0.035,
        M["lawn"],
        site,
        bevel=0.02,
    )
    for i in range(15):
        G.box(
            f"courtyard_lawn_density_patch_{i}",
            (RNG.uniform(-14, 15), RNG.uniform(-9, 12), 0.048),
            (RNG.uniform(1.2, 3.5), RNG.uniform(0.5, 1.7), 0.012),
            M["hedge"] if i % 3 else M["soil"],
            site,
            rot=RNG.uniform(-0.8, 0.8),
            bevel=0.16,
            segments=4,
        )

    # Internal pedestrian routes connect homes, apartment entrance, bike parking and trash point.
    paths = [
        ((-18, -13), (-6, -8), 1.55),
        ((-6, -8), (4, -6), 1.45),
        ((4, -6), (17, -12), 1.30),
        ((3, -6), (17, 8), 1.45),
        ((0, -6), (-6, 13), 1.25),
        ((-8, -7), (-25, 5), 1.20),
        ((-21, -10), (-28, -6), 1.10),
    ]
    for i, (p0, p1, width) in enumerate(paths):
        a, b = Vector((p0[0], p0[1], 0.045)), Vector((p1[0], p1[1], 0.045))
        mid = (a + b) / 2
        G.box(
            f"connected_walkway_{i}",
            mid,
            ((b - a).length, width, 0.070),
            M["path"],
            site,
            rot=math.atan2(b.y - a.y, b.x - a.x),
            bevel=0.020,
        )

    # Small seating node and flower beds create residential-use scale.
    G.box(
        "courtyard_seating_paving",
        (2.0, 4.2, 0.060),
        (5.0, 3.1, 0.075),
        M["path"],
        site,
        rot=0.16,
        bevel=0.018,
    )
    for i, x in enumerate((-1.0, 1.1, 3.2)):
        G.box(
            f"courtyard_bench_seat_{i}",
            (x, 4.2 + (i % 2) * 0.78, 0.48),
            (1.25, 0.32, 0.16),
            M["wood"],
            site,
            rot=0.16,
            bevel=0.020,
        )
        G.box(
            f"courtyard_bench_leg_l_{i}",
            (x - 0.45, 4.2 + (i % 2) * 0.78, 0.25),
            (0.10, 0.24, 0.34),
            M["metal"],
            site,
            rot=0.16,
            bevel=0.005,
        )
        G.box(
            f"courtyard_bench_leg_r_{i}",
            (x + 0.45, 4.2 + (i % 2) * 0.78, 0.25),
            (0.10, 0.24, 0.34),
            M["metal"],
            site,
            rot=0.16,
            bevel=0.005,
        )
    for i, (x, y) in enumerate(
        [(-6.5, -2.4), (-5.2, -1.2), (7.8, 7.0), (9.2, 6.0), (0.2, 10.4)]
    ):
        G.box(
            f"flower_bed_{i}",
            (x, y, 0.075),
            (1.8, 0.65, 0.10),
            M["soil"],
            site,
            rot=RNG.uniform(-0.7, 0.7),
            bevel=0.12,
            segments=4,
        )
        for j in range(5):
            G.sphere(
                f"flower_cluster_{i}_{j}",
                (x + RNG.uniform(-0.65, 0.65), y + RNG.uniform(-0.20, 0.20), 0.20),
                0.075,
                M["flower"],
                site,
                scale=(1.0, 0.7, 0.45),
                segments=10,
            )

    # Parking and service areas.
    for i, (cx, cy, w, d, rot) in enumerate(
        [
            (-20.5, -19.0, 11.4, 5.3, -0.15),
            (22.0, -15.0, 9.0, 4.8, 0.20),
            (24.0, 15.2, 7.4, 4.2, -0.42),
        ]
    ):
        G.box(
            f"parking_pad_refined_{i}",
            (cx, cy, 0.030),
            (w, d, 0.060),
            M["asphalt"],
            site,
            rot=rot,
            bevel=0.012,
        )
        for j in range(1, 4):
            off = -w / 2 + j * w / 4
            c, s = math.cos(rot), math.sin(rot)
            G.box(
                f"parking_mark_refined_{i}_{j}",
                (cx + c * off, cy + s * off, 0.070),
                (0.055, d - 0.55, 0.012),
                M["parking_line"],
                site,
                rot=rot + math.pi / 2,
                bevel=0,
            )
    for i, (cx, cy, rot, mat_key) in enumerate(
        [
            (-22.8, -19.2, -0.15, "car_dark"),
            (20.8, -15.4, 0.20, "car_blue"),
            (24.5, 15.5, -0.42, "car_dark"),
        ]
    ):
        G.box(
            f"parked_compact_car_body_{i}",
            (cx, cy, 0.50),
            (2.10, 3.72, 0.82),
            M[mat_key],
            site,
            rot=rot + math.pi / 2,
            bevel=0.12,
            segments=4,
        )
        G.box(
            f"parked_compact_car_cabin_{i}",
            (cx, cy + 0.10, 1.08),
            (1.58, 1.62, 0.58),
            M["glass"],
            site,
            rot=rot + math.pi / 2,
            bevel=0.08,
            segments=3,
        )

    G.box(
        "trash_collection_enclosure_pad",
        (-33.0, -10.8, 0.05),
        (3.2, 1.75, 0.09),
        M["concrete"],
        site,
        rot=-0.22,
        bevel=0.010,
    )
    for i in range(4):
        G.box(
            f"trash_bin_refined_{i}",
            (-34.0 + i * 0.62, -10.75 + RNG.uniform(-0.08, 0.08), 0.48),
            (0.46, 0.54, 0.82),
            M["trash"],
            site,
            rot=RNG.uniform(-0.12, 0.12),
            bevel=0.035,
            segments=2,
        )
    G.collection_instance(
        A["bike_rack"],
        "shared_bicycle_parking_near_apartment",
        (-19.2, -10.2, 0),
        site,
        -0.22,
        (1.20, 1.20, 1.20),
    )

    # Instanced trees/shrubs with constrained placement.
    for i, (x, y, sc) in enumerate(
        [
            (-35, 5, 1.05),
            (-30, 18, 0.95),
            (-12, 24, 1.05),
            (7, 23, 0.95),
            (27, 8, 0.98),
            (25, -16, 0.90),
            (-7, -23, 0.96),
            (13, -23, 0.86),
            (-38, -10, 0.92),
        ]
    ):
        G.collection_instance(
            A["tree_a"] if i % 2 else A["tree_b"],
            f"site_tree_refined_{i}",
            (x, y, 0),
            site,
            RNG.uniform(-math.pi, math.pi),
            (sc, sc, sc),
        )
    for i in range(22):
        x, y = RNG.choice(
            [(-10, 9), (-3, 12), (5, 12), (14, 5), (11, -7), (-10, -5), (-17, 2)]
        )
        G.collection_instance(
            A["shrub"],
            f"courtyard_shrub_refined_{i}",
            (x + RNG.uniform(-1.8, 1.8), y + RNG.uniform(-1.3, 1.3), 0.04),
            site,
            RNG.uniform(-0.5, 0.5),
            (RNG.uniform(0.62, 0.92),) * 3,
        )
    for i, (x, y, sx, sy, rot) in enumerate(
        [
            (-24, 23, 9.0, 0.45, 0.18),
            (-38, -1, 0.45, 10.5, -0.10),
            (29, -5, 0.45, 11.5, 0.18),
            (7, 26, 10.5, 0.45, -0.08),
        ]
    ):
        G.box(
            f"trimmed_boundary_hedge_{i}",
            (x, y, 0.50),
            (sx, sy, 0.84),
            M["hedge"],
            site,
            rot=rot,
            bevel=0.16,
            segments=4,
        )
    return site


def add_refined_apartment(origin, yaw, M, A, root):
    coll = G.make_collection("apartment_refined_facade", root)
    w, d, floors, floor_h = 24.0, 12.8, 6, 2.90
    h = floors * floor_h
    G.local_box(
        "apt01_main_mass",
        origin,
        yaw,
        (0, 0, h / 2),
        (w, d, h),
        M["apt_wall"],
        coll,
        bevel=0.022,
        segments=2,
    )
    G.local_box(
        "apt01_dark_plinth",
        origin,
        yaw,
        (0, 0, 0.42),
        (w + 0.70, d + 0.55, 0.84),
        M["apt_plinth"],
        coll,
        bevel=0.012,
    )

    # Bay segmentation and floor divisions.
    front_y = -d / 2 - 0.08
    back_y = d / 2 + 0.08
    for floor in range(floors + 1):
        z = floor * floor_h + 0.05
        G.local_box(
            f"apt01_floor_band_front_{floor}",
            origin,
            yaw,
            (0, front_y - 0.02, z),
            (w + 0.30, 0.13, 0.085),
            M["stone"],
            coll,
            bevel=0.003,
        )
    for x in (-9.7, -5.4, -1.0, 3.4, 7.8, 10.8):
        G.local_box(
            f"apt01_vertical_bay_trim_{x}",
            origin,
            yaw,
            (x, front_y - 0.03, h / 2),
            (0.16, 0.16, h - 0.8),
            M["apt_accent"],
            coll,
            bevel=0.004,
        )
    G.local_box(
        "apt01_stair_core_back",
        origin,
        yaw,
        (-w / 2 + 2.1, back_y + 0.04, h / 2),
        (3.2, 0.40, h - 0.8),
        M["apt_accent"],
        coll,
        bevel=0.008,
    )

    x_cols = [-9.3, -6.0, -2.3, 1.3, 5.0, 8.4, 10.5]
    balcony_modules = ["balcony_metal", "balcony_glass", "balcony_solid"]
    for floor in range(floors):
        z = 1.45 + floor * floor_h
        for j, lx in enumerate(x_cols):
            if floor == 0 and lx in (-2.3, 1.3):
                continue
            unit_has_balcony = floor > 0 and j in (1, 3, 5)
            if unit_has_balcony:
                G.local_box(
                    f"apt01_balcony_door_recess_{floor}_{j}",
                    origin,
                    yaw,
                    (lx, front_y + 0.01, z + 0.05),
                    (1.20, 0.16, 1.90),
                    M["deep_recess"],
                    coll,
                    bevel=0.004,
                )
                G.collection_instance(
                    A["window_tall"],
                    f"apt01_balcony_door_{floor}_{j}",
                    G.transform_point(origin, yaw, (lx, front_y - 0.10, z + 0.10)),
                    coll,
                    yaw,
                    (0.95, 0.95, 1.04),
                )
                mod = balcony_modules[(floor + j) % len(balcony_modules)]
                G.collection_instance(
                    A[mod],
                    f"apt01_balcony_{floor}_{j}",
                    G.transform_point(origin, yaw, (lx, front_y - 0.44, z + 0.02)),
                    coll,
                    yaw,
                    (1, 1, 1),
                )
                if (floor + j) % 3 == 0:
                    G.collection_instance(
                        A["planter"],
                        f"apt01_balcony_planter_{floor}_{j}",
                        G.transform_point(
                            origin, yaw, (lx - 0.55, front_y - 1.10, z + 0.12)
                        ),
                        coll,
                        yaw,
                        (0.9, 0.9, 0.9),
                    )
                if (floor + j) % 2 == 0:
                    G.collection_instance(
                        A["ac"],
                        f"apt01_balcony_ac_{floor}_{j}",
                        G.transform_point(
                            origin, yaw, (lx + 0.93, front_y - 0.80, z - 0.55)
                        ),
                        coll,
                        yaw,
                        (0.62, 0.62, 0.62),
                    )
            else:
                if (floor + j) % 4 == 0:
                    master, scale = A["window_slit"], (0.95, 0.95, 0.95)
                elif (floor + j) % 3 == 0:
                    master, scale = A["window_wide"], (0.78, 0.82, 0.86)
                else:
                    master, scale = A["window"], (0.80, 0.82, 0.86)
                G.collection_instance(
                    master,
                    f"apt01_front_window_{floor}_{j}",
                    G.transform_point(origin, yaw, (lx, front_y - 0.10, z)),
                    coll,
                    yaw,
                    scale,
                )
                if floor in (2, 4) and j in (0, 6):
                    G.collection_instance(
                        A["ac"],
                        f"apt01_wall_ac_{floor}_{j}",
                        G.transform_point(
                            origin, yaw, (lx + 0.78, front_y - 0.18, z - 0.52)
                        ),
                        coll,
                        yaw,
                        (0.56, 0.56, 0.56),
                    )

        for j, lx in enumerate((-9.2, -6.0, -2.8, 0.3, 3.4, 6.8, 9.6)):
            master = A["window_slit"] if j in (0, 6) else A["window"]
            G.collection_instance(
                master,
                f"apt01_back_window_{floor}_{j}",
                G.transform_point(origin, yaw, (lx, back_y + 0.10, z)),
                coll,
                yaw + math.pi,
                (0.68, 0.70, 0.80),
            )

    # Entrance and roof.
    G.local_box(
        "apt01_entry_recess",
        origin,
        yaw,
        (-0.5, front_y + 0.02, 1.34),
        (3.55, 0.20, 2.48),
        M["deep_recess"],
        coll,
        bevel=0.006,
    )
    G.local_box(
        "apt01_entry_glass_left",
        origin,
        yaw,
        (-1.08, front_y - 0.10, 1.20),
        (0.94, 0.055, 1.90),
        M["glass"],
        coll,
        bevel=0.004,
    )
    G.local_box(
        "apt01_entry_glass_right",
        origin,
        yaw,
        (0.16, front_y - 0.10, 1.20),
        (0.94, 0.055, 1.90),
        M["glass"],
        coll,
        bevel=0.004,
    )
    G.local_box(
        "apt01_entry_side_panel",
        origin,
        yaw,
        (1.18, front_y - 0.10, 1.20),
        (0.54, 0.055, 1.90),
        M["wood"],
        coll,
        bevel=0.006,
    )
    G.local_box(
        "apt01_entry_canopy",
        origin,
        yaw,
        (-0.25, front_y - 0.74, 2.72),
        (4.30, 1.55, 0.17),
        M["roof_metal"],
        coll,
        bevel=0.010,
    )
    G.local_box(
        "apt01_entry_paving",
        origin,
        yaw,
        (-0.2, front_y - 2.28, 0.055),
        (9.6, 3.4, 0.09),
        M["path"],
        coll,
        bevel=0.010,
    )
    G.collection_instance(
        A["bike_rack"],
        "apt01_bike_rack",
        G.transform_point(origin, yaw, (4.6, front_y - 1.55, 0)),
        coll,
        yaw,
        (1.15, 1.15, 1.15),
    )

    G.local_box(
        "apt01_roof_membrane",
        origin,
        yaw,
        (0, 0, h + 0.12),
        (w + 0.20, d + 0.14, 0.18),
        M["roof_metal"],
        coll,
        bevel=0.006,
    )
    for tag, lx, ly, sx, sy in [
        ("front", 0, -d / 2 - 0.02, w + 0.50, 0.26),
        ("back", 0, d / 2 + 0.02, w + 0.50, 0.26),
        ("left", -w / 2 - 0.02, 0, 0.26, d + 0.50),
        ("right", w / 2 + 0.02, 0, 0.26, d + 0.50),
    ]:
        G.local_box(
            f"apt01_parapet_{tag}",
            origin,
            yaw,
            (lx, ly, h + 0.64),
            (sx, sy, 0.98),
            M["fascia"],
            coll,
            bevel=0.008,
        )
    for i, (lx, ly, sx, sy) in enumerate(
        [
            (-6.4, -1.5, 1.6, 1.1),
            (-2.2, 2.6, 1.2, 1.0),
            (2.6, -1.0, 1.4, 1.25),
            (6.8, 2.4, 1.2, 0.9),
        ]
    ):
        G.local_box(
            f"apt01_roof_hvac_{i}",
            origin,
            yaw,
            (lx, ly, h + 0.82),
            (sx, sy, 0.64),
            M["apt_accent"],
            coll,
            bevel=0.012,
        )
        G.cylinder(
            f"apt01_roof_vent_{i}",
            G.transform_point(origin, yaw, (lx + sx * 0.32, ly, h + 1.25)),
            0.16,
            0.55,
            M["gutter"],
            coll,
            vertices=18,
            bevel=0.004,
        )
    for lx in (-w / 2 - 0.18, w / 2 + 0.18):
        for ly in (-d / 2 + 1.1, d / 2 - 1.1):
            G.beam(
                f"apt01_downspout_{lx:.1f}_{ly:.1f}",
                G.transform_point(origin, yaw, (lx, ly, h + 0.20)),
                G.transform_point(origin, yaw, (lx, ly, 0.44)),
                0.030,
                M["gutter"],
                coll,
            )
    print(
        f"[all45_01] apartment refined floors={floors} objects={len(coll.all_objects)}",
        flush=True,
    )
    return coll


def add_lighting_and_cameras():
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    try:
        bpy.context.scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new(
        PREFIX + "world"
    )
    bpy.context.scene.world.color = (0.78, 0.82, 0.86)
    bpy.ops.object.light_add(
        type="SUN",
        location=(-22, -18, 28),
        rotation=(math.radians(48), 0, math.radians(-34)),
    )
    sun = bpy.context.object
    sun.name = PREFIX + "daylight_sun"
    sun.data.energy = 2.0
    bpy.ops.object.light_add(type="AREA", location=(-5, -18, 17))
    area = bpy.context.object
    area.name = PREFIX + "soft_sky_fill"
    area.data.energy = 420
    area.data.size = 30

    def cam(name, loc, target, fov):
        bpy.ops.object.camera_add(location=loc)
        obj = bpy.context.object
        obj.name = PREFIX + "cam_" + name
        obj.data.lens_unit = "FOV"
        obj.data.angle = math.radians(fov)
        obj.data.clip_start = 0.03
        obj.rotation_euler = (
            (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        )
        return obj

    return [
        (
            cam("residential_overview", (5, -48, 36), (-4, 0, 4.2), 55),
            "residential_overview.png",
        ),
        (
            cam("apartment_close", (-30, -27, 11.0), (-18, -5, 6.2), 50),
            "apartment_close.png",
        ),
        (
            cam("apartment_balcony_close", (-21.8, -22.0, 7.2), (-17.6, -9.3, 5.4), 42),
            "apartment_balcony_close.png",
        ),
        (
            cam(
                "indoor_house_exterior_close", (-10, -30, 8.0), (-11.5, -15.0, 3.2), 48
            ),
            "indoor_house_exterior_close.png",
        ),
        (
            cam(
                "indoor_house_window_view", (-10.5, -23.7, 3.0), (-12.5, -15.7, 2.2), 35
            ),
            "indoor_house_window_view.png",
        ),
        (
            cam("exterior_only_house_close", (7.0, -31.0, 7.2), (12.2, -18.5, 3.1), 48),
            "exterior_only_house_close.png",
        ),
        (
            cam("courtyard_view", (-16.0, -18.0, 5.7), (3.0, 3.0, 1.8), 57),
            "courtyard_view.png",
        ),
        (
            cam("residential_side_view", (39, -18, 14), (8, 6, 4), 56),
            "residential_side_view.png",
        ),
    ]


def render(cameras):
    import render_urban_v3_all45_01_remaining as render_helper

    bpy.context.scene.render.use_simplify = True
    bpy.context.scene.render.simplify_subdivision_render = 0
    bpy.context.scene.render.simplify_child_particles_render = 0
    bpy.context.scene.render.resolution_x = 1000
    bpy.context.scene.render.resolution_y = 625
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    render_helper.ensure_lightweight_window_room()
    for cam, filename in cameras:
        render_helper.set_indoor_visibility(False)
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(OUT / filename)
        bpy.ops.render.render(write_still=True)
        print(f"[all45_01] rendered {filename}", flush=True)


def save_audit(start, indoor_imported=True):
    stats = {
        "prompt": "prompt-45-01 residential refinement",
        "output": str(OUT),
        "source_generator": str(ROOT / "scripts/generate_urban_v3_all45_01.py"),
        "base_generator_reused": str(ROOT / "scripts/generate_urban_v3_all45.py"),
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "collection_instances": sum(
            1 for o in bpy.data.objects if o.instance_type == "COLLECTION"
        ),
        "lowrise_houses": 7,
        "indoor_pipeline_houses": 1 if indoor_imported else 0,
        "indoor_source_blend": str(INDOOR_BLEND),
        "apartment_floors": 6,
        "renders": [
            "residential_overview.png",
            "apartment_close.png",
            "apartment_balcony_close.png",
            "indoor_house_exterior_close.png",
            "indoor_house_window_view.png",
            "exterior_only_house_close.png",
            "courtyard_view.png",
            "residential_side_view.png",
        ],
        "elapsed_seconds": round(time.time() - start, 2),
    }
    with (OUT / "all45_01_residential_audit.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"[all45_01] audit {stats}", flush=True)


def main():
    start = time.time()
    configure_base_module()
    OUT.mkdir(parents=True, exist_ok=True)
    G.reset_scene()
    root = make_render_collection_root()
    M = G.make_mats()
    add_extra_materials(M)
    G.MATS = M
    A = G.make_asset_masters(M)
    make_extra_masters(M, A)
    add_refined_site(M, A, root)
    add_refined_apartment((-19.5, -5.2, 0), math.radians(5), M, A, root)
    import_infinigen_indoor_house((-11.5, -16.0, 0), math.radians(5), M, A, root)
    add_exterior_only_houses(M, A, root)
    cameras = add_lighting_and_cameras()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45_01.blend"))
    save_audit(start, indoor_imported=True)
    render(cameras)


if __name__ == "__main__":
    main()
