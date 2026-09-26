"""
generate_urban_v3_all4.py
=========================
Photo-realistic 4-way crossroads — Version 4.

Fixes from v3:
 1. Vehicle variety: Ducato + infinigen cars/bus
 2. Phone booth on sidewalk (south arm east side)
 3. Bus stop larger (scale=1.5)
 4. Bicycle station: east arm north sidewalk, yaw=0 (bikes perpendicular to road)
 5. Green belt flowers scattered on grass surface (no toy planters)
 6. Real trees: infinigen TreeFactory OR belt2 at scale=3.5 (fallback)
 7. Street lamps OFF during daytime (day=True)
 8. Houses moved further back; textured walls reduce "white wall" effect
 9. Traffic lights correct yaw (N:0, S:π, W:−π/2, E:+π/2)
10. Toy flower beds removed
11. Kiosk enlarged (scale=1.5) and placed near House A

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all4/
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


import sys, math, random as _rng

sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
from pathlib import Path
from mathutils import Vector, Matrix

import urban_assets as UA

# ─── OUTPUT ───────────────────────────────────────────────────────────────────
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all4")
OUT.mkdir(parents=True, exist_ok=True)

# ─── SCENE SETUP ──────────────────────────────────────────────────────────────
UA.reset_scene()
UA.build_all_materials()
M = UA.M

# Extra textured wall materials so houses are not plain white
M["wall_tan"] = UA._noise_mat(
    "wall_tan", (0.82, 0.74, 0.58), (0.72, 0.64, 0.50), rough=0.68, scale=7
)
M["wall_cream"] = UA._noise_mat(
    "wall_cream", (0.86, 0.80, 0.70), (0.78, 0.72, 0.62), rough=0.65, scale=9
)

# ─── GEOMETRY CONSTANTS ───────────────────────────────────────────────────────
RW = 4.0  # road half-width  → road spans ±RW
SW = 3.0  # sidewalk width each side
GW = 2.5  # green-belt width each side
ARM = 40.0  # arm length beyond RW

R = RW  # 4.0  inner sidewalk edge
S1 = RW + SW  # 7.0  outer sidewalk / inner green edge
G1 = S1 + GW  # 9.5  outer green edge


# ─── COLLECTIONS ──────────────────────────────────────────────────────────────
def _c(name):
    return UA.new_coll(name)


C_road = _c("Road")
C_sw = _c("Sidewalk")
C_green = _c("Green")
C_tl = _c("TrafficLight")
C_bs = _c("BusStop")
C_furn = _c("Furniture")
C_kiosk = _c("Kiosk")
C_bike = _c("BicycleStation")
C_phone = _c("PhoneBooth")
C_lamp = _c("StreetLamps")
C_shrub = _c("Shrubs")
C_trees = _c("Trees")
C_cars = _c("Vehicles")
C_house = _c("Houses")
C_flow = _c("Flowers")

# ─── GROUND PLANE ─────────────────────────────────────────────────────────────
gnd_mat = UA._noise_mat(
    "ground_dirt", (0.36, 0.30, 0.22), (0.26, 0.22, 0.16), rough=0.92
)
UA._box("ground_plane", 0, 0, -0.06, 200, 200, 0.12, gnd_mat, C_sw)

# ─── CROSSROADS GEOMETRY ──────────────────────────────────────────────────────
print("[v4] Building crossroads geometry…")


def _road(n, cx, cy, dx, dy):
    UA._box(n, cx, cy, -0.02, dx, dy, 0.04, M["road"], C_road)


def _sw(n, cx, cy, dx, dy):
    UA._box(n, cx, cy, 0.06, dx, dy, 0.12, M["sidewalk"], C_sw)


def _gn(n, cx, cy, dx, dy):
    UA._box(n, cx, cy, 0.00, dx, dy, 0.04, M["greenstrip"], C_green)


# Asphalt deck
_road("isect", 0, 0, 2 * RW, 2 * RW)
_road("road_n", 0, RW + ARM / 2, 2 * RW, ARM)
_road("road_s", 0, -(RW + ARM / 2), 2 * RW, ARM)
_road("road_e", RW + ARM / 2, 0, ARM, 2 * RW)
_road("road_w", -(RW + ARM / 2), 0, ARM, 2 * RW)

# Corner sidewalk tiles
for sx, sy, sfx in [(1, 1, "ne"), (-1, 1, "nw"), (1, -1, "se"), (-1, -1, "sw")]:
    _sw(f"sw_cor_{sfx}", sx * (R + SW / 2), sy * (R + SW / 2), SW, SW)

# N-S arm sidewalks (4 strips: N-east, N-west, S-east, S-west)
arm_sw_len = ARM - SW  # 37 m
arm_sw_cy = R + SW + arm_sw_len / 2
for sx, sfx in [(1, "e"), (-1, "w")]:
    _sw(f"sw_n_{sfx}", sx * (R + SW / 2), arm_sw_cy, SW, arm_sw_len)
    _sw(f"sw_s_{sfx}", sx * (R + SW / 2), -arm_sw_cy, SW, arm_sw_len)

# E-W arm sidewalks
arm_sw_cx = arm_sw_cy
for sy, sfx in [(1, "n"), (-1, "s")]:
    _sw(f"sw_e_{sfx}", arm_sw_cx, sy * (R + SW / 2), arm_sw_len, SW)
    _sw(f"sw_w_{sfx}", -arm_sw_cx, sy * (R + SW / 2), arm_sw_len, SW)

# Green belt corner tiles
arm_gn_len = ARM - SW - GW  # 34.5 m
arm_gn_off = R + SW + GW + arm_gn_len / 2
for sx, sy, sfx in [(1, 1, "ne"), (-1, 1, "nw"), (1, -1, "se"), (-1, -1, "sw")]:
    _gn(f"gn_cor_{sfx}", sx * (S1 + GW / 2), sy * (S1 + GW / 2), GW, GW)
for sx, sfx in [(1, "e"), (-1, "w")]:
    _gn(f"gn_n_{sfx}", sx * (S1 + GW / 2), arm_gn_off, GW, arm_gn_len)
    _gn(f"gn_s_{sfx}", sx * (S1 + GW / 2), -arm_gn_off, GW, arm_gn_len)
for sy, sfx in [(1, "n"), (-1, "s")]:
    _gn(f"gn_e_{sfx}", arm_gn_off, sy * (S1 + GW / 2), arm_gn_len, GW)
    _gn(f"gn_w_{sfx}", -arm_gn_off, sy * (S1 + GW / 2), arm_gn_len, GW)

# Kerb strips along road edge
KM = M["curb"]
for arm_y in [RW + ARM / 2, -(RW + ARM / 2)]:
    for kx in [RW + 0.08, -(RW + 0.08)]:
        UA._box(
            f"kerb_ns_{arm_y:.0f}_{kx:.0f}", kx, arm_y, 0.10, 0.16, ARM, 0.20, KM, C_sw
        )
for arm_x in [RW + ARM / 2, -(RW + ARM / 2)]:
    for ky in [RW + 0.08, -(RW + 0.08)]:
        UA._box(
            f"kerb_ew_{arm_x:.0f}_{ky:.0f}", arm_x, ky, 0.10, ARM, 0.16, 0.20, KM, C_sw
        )

# Yellow centre lines
for dx in (-0.08, 0.08):
    UA._box(
        f"cl_ns_{dx:.2f}",
        dx,
        0,
        0.003,
        0.06,
        2 * (RW + ARM),
        0.004,
        M["stripe_y"],
        C_road,
    )
    UA._box(
        f"cl_ew_{dx:.2f}",
        0,
        dx,
        0.003,
        2 * (RW + ARM),
        0.06,
        0.004,
        M["stripe_y"],
        C_road,
    )

# White lane dashes (N-S and E-W arms)
for yi in range(2, 9):
    y0 = R + yi * (ARM / 9)
    for side in [2.0, -2.0]:
        UA._box(
            f"dash_n{yi}_{side:.0f}",
            side,
            y0,
            0.003,
            0.12,
            1.8,
            0.004,
            M["stripe_w"],
            C_road,
        )
        UA._box(
            f"dash_s{yi}_{side:.0f}",
            side,
            -y0,
            0.003,
            0.12,
            1.8,
            0.004,
            M["stripe_w"],
            C_road,
        )
for xi in range(2, 9):
    x0 = R + xi * (ARM / 9)
    for side in [2.0, -2.0]:
        UA._box(
            f"dash_e{xi}_{side:.0f}",
            x0,
            side,
            0.003,
            1.8,
            0.12,
            0.004,
            M["stripe_w"],
            C_road,
        )
        UA._box(
            f"dash_w{xi}_{side:.0f}",
            -x0,
            side,
            0.003,
            1.8,
            0.12,
            0.004,
            M["stripe_w"],
            C_road,
        )

# Crosswalks at all 4 arm entrances
for stripe in range(8):
    xf = -RW + 0.5 + stripe * (2 * RW - 1.0) / 8
    UA._box(
        f"xwk_s{stripe}", xf, -(RW + 0.6), 0.004, 0.78, 2.2, 0.005, M["xwalk"], C_road
    )
    UA._box(
        f"xwk_n{stripe}", xf, (RW + 0.6), 0.004, 0.78, 2.2, 0.005, M["xwalk"], C_road
    )
for stripe in range(8):
    yf = -RW + 0.5 + stripe * (2 * RW - 1.0) / 8
    UA._box(
        f"xwk_e{stripe}", (RW + 0.6), yf, 0.004, 2.2, 0.78, 0.005, M["xwalk"], C_road
    )
    UA._box(
        f"xwk_w{stripe}", -(RW + 0.6), yf, 0.004, 2.2, 0.78, 0.005, M["xwalk"], C_road
    )

# Stop lines
for sign, sfx in [(1, "n"), (-1, "s")]:
    UA._box(
        f"stop_{sfx}",
        0,
        sign * (RW + 2.0),
        0.004,
        2 * RW,
        0.4,
        0.005,
        M["stripe_w"],
        C_road,
    )
for sign, sfx in [(1, "e"), (-1, "w")]:
    UA._box(
        f"stop_{sfx}",
        sign * (RW + 2.0),
        0,
        0.004,
        0.4,
        2 * RW,
        0.005,
        M["stripe_w"],
        C_road,
    )

# ─── TRAFFIC LIGHTS (CORRECTED YAW) ──────────────────────────────────────────
# Source: gantry spans X, signals face −Y (toward approaching northbound traffic).
# Yaw: 0=south gantry(northbound), π=north gantry(southbound),
#      −π/2=west gantry(eastbound signals face −X), +π/2=east gantry(westbound signals face +X)
print("[v4] Placing traffic lights (4 gantries, corrected yaw)…")
UA.place_trafficlight((0.0, -(RW + 2.5)), C_tl, yaw=0)  # S gantry: northbound
UA.place_trafficlight((0.0, (RW + 2.5)), C_tl, yaw=math.pi)  # N gantry: southbound
UA.place_trafficlight((-(RW + 2.5), 0.0), C_tl, yaw=-math.pi / 2)  # W gantry: eastbound
UA.place_trafficlight(((RW + 2.5), 0.0), C_tl, yaw=math.pi / 2)  # E gantry: westbound

# ─── BUS STOP (larger, scale=1.5) ─────────────────────────────────────────────
print("[v4] Placing bus stop (north arm east sidewalk, scale=1.5)…")
UA.place_busstop((R + SW / 2, 16.0), C_bs, yaw=-math.pi / 2, scale=1.5)

# ─── KIOSK (near House A, scale=1.5) ─────────────────────────────────────────
print("[v4] Placing kiosk (near House A, scale=1.5)…")
UA.place_kiosk5((14.5, 27.0), C_kiosk, yaw=-math.pi / 2, scale=1.5)

# ─── PHONE BOOTH (on sidewalk, south arm east side) ──────────────────────────
print("[v4] Placing phone booth (south arm east sidewalk)…")
UA.place_phonebooth((R + SW / 2 + 0.2, -22.0), C_phone, yaw=-math.pi / 2)

# ─── BENCHES + BINS ───────────────────────────────────────────────────────────
print("[v4] Placing benches and bins…")
UA.place_bench_classic((R + SW / 2 - 0.3, 23.5), C_furn, yaw=-math.pi / 2)
UA.place_bin_domed((R + SW / 2 - 0.3, 26.0), C_furn)
UA.place_bench_classic((-(R + SW / 2 - 0.3), 13.0), C_furn, yaw=math.pi / 2)
UA.place_bin_domed((-(R + SW / 2 - 0.3), 10.5), C_furn)

# ─── BICYCLE STATION (east arm north sidewalk, bikes ⊥ to road) ──────────────
# yaw=0: fleet runs along Y (perpendicular to E-W road) = standard dock orientation
print("[v4] Placing bicycle station (east arm north sidewalk, yaw=0)…")
UA.place_bicycle_station((26.0, R + SW / 2), C_bike, yaw=0)

# ─── STREET LAMPS (daytime: emission off) ─────────────────────────────────────
print("[v4] Placing street lamps (daytime)…")
ns_lamp_ys = [8.0, 15.5, 23.0, 30.5, 38.0]
for y in ns_lamp_ys:
    UA.place_streetlight((R + SW / 2 - 0.2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight(
        (-(R + SW / 2 - 0.2), y + 3.5), C_lamp, yaw=-math.pi / 2, day=True
    )
for y in ns_lamp_ys:
    UA.place_streetlight((R + SW / 2 - 0.2, -y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight(
        (-(R + SW / 2 - 0.2), -(y + 3.5)), C_lamp, yaw=-math.pi / 2, day=True
    )
ew_lamp_xs = [8.0, 15.5, 23.0, 30.5, 38.0]
for x in ew_lamp_xs:
    UA.place_streetlight((x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x + 3.5, -(R + SW / 2 - 0.2)), C_lamp, yaw=0.0, day=True)
for x in ew_lamp_xs:
    UA.place_streetlight((-x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((-(x + 3.5), -(R + SW / 2 - 0.2)), C_lamp, yaw=0.0, day=True)

# ─── BELT2 SHRUBS (real infinigen assets, green belts) ───────────────────────
print("[v4] Planting belt2 shrubs in green belts…")
ns_shrub_ys = [9.5, 15.0, 20.5, 26.0, 31.5, 37.0, 42.5]
for i, y in enumerate(ns_shrub_ys):
    si = i % 5
    UA.place_shrub_belt2(
        f"shr_ne{i}", (S1 + GW / 2, y), C_shrub, scale=2.2, shrub_idx=si
    )
    UA.place_shrub_belt2(
        f"shr_nw{i}",
        (-(S1 + GW / 2), y + 2.5),
        C_shrub,
        scale=2.0,
        shrub_idx=(si + 2) % 5,
    )
    UA.place_shrub_belt2(
        f"shr_se{i}", (S1 + GW / 2, -y), C_shrub, scale=2.2, shrub_idx=(si + 1) % 5
    )
    UA.place_shrub_belt2(
        f"shr_sw{i}",
        (-(S1 + GW / 2), -(y + 2.5)),
        C_shrub,
        scale=2.0,
        shrub_idx=(si + 3) % 5,
    )
ew_shrub_xs = [9.5, 15.0, 20.5, 26.0, 31.5, 37.0, 42.5]
for i, x in enumerate(ew_shrub_xs):
    si = (i + 1) % 5
    UA.place_shrub_belt2(
        f"shr_en{i}", (x, S1 + GW / 2), C_shrub, scale=2.0, shrub_idx=si
    )
    UA.place_shrub_belt2(
        f"shr_es{i}",
        (x + 2.5, -(S1 + GW / 2)),
        C_shrub,
        scale=2.2,
        shrub_idx=(si + 2) % 5,
    )
    UA.place_shrub_belt2(
        f"shr_wn{i}", (-x, S1 + GW / 2), C_shrub, scale=2.0, shrub_idx=(si + 1) % 5
    )
    UA.place_shrub_belt2(
        f"shr_ws{i}",
        (-(x + 2.5), -(S1 + GW / 2)),
        C_shrub,
        scale=2.2,
        shrub_idx=(si + 3) % 5,
    )
for cx, cy, sfx, si in [
    (S1 + GW / 2, S1 + GW / 2, "ne", 0),
    (-(S1 + GW / 2), S1 + GW / 2, "nw", 2),
    (S1 + GW / 2, -(S1 + GW / 2), "se", 1),
    (-(S1 + GW / 2), -(S1 + GW / 2), "sw", 3),
]:
    UA.place_shrub_belt2(f"shr_cor_{sfx}", (cx, cy), C_shrub, scale=2.0, shrub_idx=si)

# ─── REAL STREET TREES ────────────────────────────────────────────────────────
# Use belt2 shrubs at scale=3.5 as street trees (real infinigen assets, GPU-friendly).
# The TreeFactory trees from trees.blend are too geometry-heavy for GPU VRAM.
print("[v4] Placing street trees (belt2 at scale=3.5)…")
_TREE_SPOTS = [
    # (x,   y,   shrub_idx)  — tall feature trees in setback zone
    (G1 + 2.2, 10.5, 0),
    (G1 + 2.2, 20.0, 1),
    (G1 + 2.2, 30.0, 2),
    (G1 + 2.2, 40.0, 3),
    (-(G1 + 2.2), 13.0, 2),
    (-(G1 + 2.2), 24.0, 4),
    (G1 + 2.2, -12.0, 1),
    (G1 + 2.2, -26.0, 3),
    (-(G1 + 2.2), -15.0, 0),
    (-(G1 + 2.2), -28.0, 4),
    (14.0, G1 + 2.2, 3),
    (26.0, G1 + 2.2, 0),
    (37.0, G1 + 2.2, 2),
    (18.0, -(G1 + 2.2), 1),
    (30.0, -(G1 + 2.2), 4),
]
for i, (tx, ty, si) in enumerate(_TREE_SPOTS):
    UA.place_shrub_belt2(f"ftree{i}", (tx, ty), C_trees, scale=3.5, shrub_idx=si % 5)

# ─── GREEN BELT FLOWERS (no raised planters, scattered on grass) ──────────────
# Small stems + blooms directly on the greenstrip surface.
print("[v4] Scattering flowers in green belts…")
_flower_colors = [M["flower_r"], M["flower_y"], M["flower_p"], M["flower_w"]]


def _scatter_flowers(tag, gx, gy, length, n, seed, C):
    """Scatter n flowers along a green belt centered at (gx, gy), running length in Y."""
    _rng.seed(seed)
    half = length / 2.0
    gw = GW / 2.0 - 0.15
    for k in range(n):
        fx = gx + _rng.uniform(-gw, gw)
        fy = gy + _rng.uniform(-half, half)
        fh = _rng.uniform(0.08, 0.20)
        UA._cyl(
            f"fs_st_{tag}_{k}",
            fx,
            fy,
            0.04,
            0.005,
            fh,
            M["flower_leaf"],
            C_flow,
            verts=5,
        )
        UA._sph(
            f"fs_bl_{tag}_{k}",
            fx,
            fy,
            0.04 + fh,
            _rng.uniform(0.03, 0.055),
            _rng.choice(_flower_colors),
            C_flow,
            segs=7,
            rings=5,
        )


def _scatter_flowers_x(tag, gx, gy, length, n, seed, C):
    """Scatter flowers running along X."""
    _rng.seed(seed)
    half = length / 2.0
    gw = GW / 2.0 - 0.15
    for k in range(n):
        fx = gx + _rng.uniform(-half, half)
        fy = gy + _rng.uniform(-gw, gw)
        fh = _rng.uniform(0.08, 0.20)
        UA._cyl(
            f"fs_st_{tag}_{k}",
            fx,
            fy,
            0.04,
            0.005,
            fh,
            M["flower_leaf"],
            C_flow,
            verts=5,
        )
        UA._sph(
            f"fs_bl_{tag}_{k}",
            fx,
            fy,
            0.04 + fh,
            _rng.uniform(0.03, 0.055),
            _rng.choice(_flower_colors),
            C_flow,
            segs=7,
            rings=5,
        )


# N-S arm green belts: flower clusters between shrubs
for yi, y_mid in [(0, 12.2), (2, 23.2), (4, 34.2)]:
    _scatter_flowers(f"fn_e{yi}", S1 + GW / 2, y_mid, 4.0, 14, yi * 7, C_flow)
    _scatter_flowers(
        f"fn_w{yi}", -(S1 + GW / 2), y_mid + 3, 4.0, 14, yi * 7 + 3, C_flow
    )
    _scatter_flowers(f"fs_e{yi}", S1 + GW / 2, -y_mid, 4.0, 14, yi * 7 + 5, C_flow)
    _scatter_flowers(
        f"fs_w{yi}", -(S1 + GW / 2), -(y_mid + 3), 4.0, 14, yi * 7 + 9, C_flow
    )

# E-W arm green belts
for xi, x_mid in [(0, 12.2), (2, 23.2), (4, 34.2)]:
    _scatter_flowers_x(f"fe_n{xi}", x_mid, S1 + GW / 2, 4.0, 12, xi * 11, C_flow)
    _scatter_flowers_x(
        f"fe_s{xi}", x_mid + 3, -(S1 + GW / 2), 4.0, 12, xi * 11 + 4, C_flow
    )
    _scatter_flowers_x(f"fw_n{xi}", -x_mid, S1 + GW / 2, 4.0, 12, xi * 11 + 7, C_flow)
    _scatter_flowers_x(
        f"fw_s{xi}", -(x_mid + 3), -(S1 + GW / 2), 4.0, 12, xi * 11 + 2, C_flow
    )

# ─── VEHICLES (mixed types) ───────────────────────────────────────────────────
# Van front faces +X: +π/2=north, −π/2=south, 0=east, π=west
print("[v4] Placing vehicles (mixed types)…")

# Ducato delivery vans (always available)
UA.place_vehicle("v_duc1", (2.8, 22.0), C_cars, yaw=math.pi / 2)  # northbound
UA.place_vehicle("v_duc2", (-30.0, 2.8), C_cars, yaw=math.pi)  # westbound

# Infinigen sedans/bus (from urban_block vehicles.blend)
# Each vehicle_key encodes travel direction, source already oriented:
#   car_eastbound→+X, car_westbound→−X, car_southbound→−Y, bus_northbound→+Y
UA.place_infinigen_car("v_car1", "car_eastbound", (22.0, -2.8), C_cars)
UA.place_infinigen_car("v_car2", "car_southbound", (-2.8, -20.0), C_cars)
UA.place_infinigen_car("v_bus1", "bus_northbound", (2.8, 36.5), C_cars)

# ─── HOUSES (moved further back, textured walls) ──────────────────────────────
# House A: NE quadrant, ~24m from green belt edge. Front faces −X (toward road).
# House B: SW quadrant, similarly set back. Front faces +X.
print("[v4] Building houses…")
UA.build_house(
    "A",
    28.0,
    34.0,
    C_house,
    w=14.0,
    d=9.0,
    wall_h=3.4,
    yaw=-math.pi / 2,
    mat_wall=M["wall_tan"],
    mat_roof=M["roof_tile"],
    n_win_front=4,
)
UA.build_house(
    "B",
    -26.0,
    -30.0,
    C_house,
    w=12.0,
    d=8.0,
    wall_h=3.2,
    yaw=math.pi / 2,
    mat_wall=M["wall_cream"],
    mat_roof=M["roof_flat"],
    n_win_front=3,
)

# Extra shrubs near houses to soften building edges
for i, (hx, hy, yoff, si) in enumerate(
    [
        (G1 + 1.5, 34.0, 0, 0),
        (G1 + 1.5, 36.5, 0, 2),
        (G1 + 1.5, 38.5, 0, 4),
        (-(G1 + 1.5), -30.0, 0, 1),
        (-(G1 + 1.5), -27.5, 0, 3),
        (-(G1 + 1.5), -32.5, 0, 0),
    ]
):
    UA.place_shrub_belt2(
        f"shr_houseA{i}" if i < 3 else f"shr_houseB{i-3}",
        (hx, hy),
        C_shrub,
        scale=2.5,
        shrub_idx=si,
    )

# ─── LIGHTING ─────────────────────────────────────────────────────────────────
print("[v4] Setting up world lighting…")
UA.build_world_lighting()


# ─── CAMERAS ──────────────────────────────────────────────────────────────────
def make_cam(name, loc, look_at, lens=50, fstop=None):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    if fstop:
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
        focus = Vector(look_at)
        cam.dof.focus_distance = (Vector(loc) - focus).length
    obj = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = Vector(loc)
    direction = Vector(look_at) - Vector(loc)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


CAMS = {
    # Elevated overview of full crossroads
    "overview": make_cam(
        "CAM_Overview", loc=(-42, -60, 45), look_at=(2, 2, 1.5), lens=28
    ),
    # Driver's-eye from north arm looking south (shows bus stop, kiosk, intersection)
    "northarm": make_cam(
        "CAM_NorthArm", loc=(-7.0, 40.0, 2.2), look_at=(5.5, 14.0, 2.2), lens=50
    ),
    # Driver's-eye from east end looking west (shows bicycle station, traffic lights)
    "eastarm": make_cam(
        "CAM_EastArm", loc=(44.0, -3.0, 2.4), look_at=(10.0, 0.0, 4.0), lens=50
    ),
    # Street-level at intersection, looking north (shows gantries over intersection)
    "intersection": make_cam(
        "CAM_Intersection", loc=(0.5, -12.0, 2.8), look_at=(0, 2, 5.5), lens=50
    ),
}

# ─── RENDER SETUP ─────────────────────────────────────────────────────────────
scn = bpy.context.scene
scn.render.engine = "CYCLES"
scn.render.resolution_x = 1920
scn.render.resolution_y = 1080
scn.cycles.samples = 512
scn.cycles.device = "GPU"
scn.cycles.use_denoising = True

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    # Use CUDA so all 8×4090s pool their VRAM for large scenes
    for dtype in ("CUDA", "OPTIX", "HIP", "METAL"):
        try:
            prefs.compute_device_type = dtype
            prefs.get_devices()
            if any(d.type != "CPU" for d in prefs.devices):
                break
        except Exception:
            continue
    for d in prefs.devices:
        d.use = True
    print(f"[v4] GPU rendering: {prefs.compute_device_type}")
except Exception as e:
    print(f"[v4] GPU setup: {e}")

# AgX with slight underexposure for outdoor realism
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = "AgX - Medium High Contrast"
scn.view_settings.exposure = -0.5

# ─── SAVE BLEND ───────────────────────────────────────────────────────────────
blend_path = str(OUT / "crossroads4.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[v4] Blend saved → {blend_path}")

# ─── RENDER ALL CAMERAS ───────────────────────────────────────────────────────
for cam_name, cam_obj in CAMS.items():
    scn.camera = cam_obj
    out_png = str(OUT / f"{cam_name}.png")
    scn.render.filepath = out_png
    print(f"[v4] Rendering {cam_name} → {out_png}")
    bpy.ops.render.render(write_still=True)
    print(f"[v4]   done.")

print(f"[v4] All renders complete → {OUT}")
