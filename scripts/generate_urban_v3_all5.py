"""
generate_urban_v3_all5.py
=========================
Comprehensive outdoor scene with 4 distinct functional zones around a 4-way crossroads.

Zones:
  North arm (+Y): Residential — houses, iron fences with gates, paved paths,
                                bus stop, bike station
  East arm  (+X): Park        — Chinese pavilion, Victorian bandstand, water feature,
                                benches, trees, lawn, park entrance
  South arm (-Y): Commercial  — 3 kiosk shops, simple storefronts, awnings,
                                street furniture
  West arm  (-X): Street continuation — trees, lamps

Rules:
  1. Wide crossroads with lane markings, stop lines, turn arrows, crosswalks
  2. Residential: houses set back, fences+gates, paved paths connecting to sidewalk
  3. Park: pavilion, sculptures, benches, trees, lawn, park entrance facing sidewalk
  4. Commercial: shops along street, entrances facing sidewalk, awnings
  5. Road area: vehicles + traffic markings ONLY
  6. Continuous curb flower beds (grass + flowers), openings at entries, crosswalks
  7. Bus stop: north arm east sidewalk — NOT on road
  8. Bike station: parallel to road, near bus stop, on sidewalk edge
  9. Continuous stone sidewalks connecting all zones
  10. Street furniture on sidewalk edges
  11. Clear road / pedestrian / green / building zone boundaries

All writes to ${WORLDBRIDGE_EXTERNAL}/
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

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all5")
OUT.mkdir(parents=True, exist_ok=True)

SC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sculpture/public_art.blend"
)

UA.reset_scene()
UA.build_all_materials()
M = UA.M

# ─── EXTRA MATERIALS ──────────────────────────────────────────────────────────
M["wall_tan"] = UA._noise_mat(
    "wall_tan", (0.82, 0.74, 0.58), (0.72, 0.64, 0.50), rough=0.68, scale=7
)
M["wall_cream"] = UA._noise_mat(
    "wall_cream", (0.88, 0.85, 0.76), (0.78, 0.76, 0.68), rough=0.68, scale=8
)
M["wall_blue"] = UA._noise_mat(
    "wall_blue", (0.52, 0.62, 0.78), (0.42, 0.52, 0.68), rough=0.68, scale=8
)
M["grass_lush"] = UA._noise_mat(
    "grass_lush", (0.10, 0.32, 0.06), (0.15, 0.40, 0.10), rough=0.85, scale=22
)
M["stone_path"] = UA._noise_mat(
    "stone_path", (0.65, 0.62, 0.56), (0.56, 0.52, 0.47), rough=0.80, scale=12
)
M["fence_iron"] = UA._pbr("fence_iron", (0.10, 0.10, 0.12), rough=0.35, metal=0.85)
M["gate_post"] = UA._pbr("gate_post", (0.14, 0.14, 0.16), rough=0.30, metal=0.90)
M["awning_r"] = UA._pbr("awning_r", (0.72, 0.18, 0.10), rough=0.76)
M["awning_g"] = UA._pbr("awning_g", (0.18, 0.52, 0.22), rough=0.76)
M["awning_b"] = UA._pbr("awning_b", (0.18, 0.30, 0.72), rough=0.76)
M["shop_beige"] = UA._noise_mat(
    "shop_beige", (0.82, 0.78, 0.68), (0.74, 0.70, 0.60), rough=0.70, scale=8
)
M["shop_red"] = UA._noise_mat(
    "shop_red", (0.70, 0.24, 0.14), (0.60, 0.20, 0.10), rough=0.66, scale=8
)
M["water_blue"] = UA._pbr("water_blue", (0.10, 0.36, 0.70), rough=0.04)
M["park_stone"] = UA._noise_mat(
    "park_stone", (0.72, 0.70, 0.65), (0.62, 0.60, 0.56), rough=0.68, scale=10
)
M["sign_bg"] = UA._pbr("sign_bg", (0.08, 0.22, 0.55), rough=0.72)

# ─── GEOMETRY CONSTANTS ───────────────────────────────────────────────────────
RW = 4.0  # road half-width  (total road = 8 m)
SW = 3.0  # sidewalk width
FW = 2.5  # curb flower-bed width
ARM = 44.0  # arm length beyond intersection edge

R = RW  # 4.0
S1 = R + SW  # 7.0  — outer sidewalk / inner flower-bed edge
G1 = S1 + FW  # 9.5  — outer flower-bed / zone start

# ─── COLLECTIONS ──────────────────────────────────────────────────────────────
C_road = UA.new_coll("Road")
C_sw = UA.new_coll("Sidewalks")
C_fb = UA.new_coll("FlowerBeds")
C_tl = UA.new_coll("TrafficLights")
C_n = UA.new_coll("Residential")
C_e = UA.new_coll("Park")
C_s = UA.new_coll("Commercial")
C_w = UA.new_coll("WestArm")
C_furn = UA.new_coll("Furniture")
C_lamp = UA.new_coll("Lamps")
C_cars = UA.new_coll("Vehicles")
C_tree = UA.new_coll("Trees")

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────


def _scatter_fb(tag, cx, cy, dx, dy, C, seed=0):
    """Scatter grass flowers on a flower-bed surface (z ~ 0.08)."""
    _rng.seed(seed % 99991)
    fmats = [M["flower_r"], M["flower_y"], M["flower_p"], M["flower_w"]]
    n = max(4, int(dx * dy * 1.6))
    for k in range(n):
        fx = cx + _rng.uniform(-dx / 2 + 0.2, dx / 2 - 0.2)
        fy = cy + _rng.uniform(-dy / 2 + 0.2, dy / 2 - 0.2)
        fh = _rng.uniform(0.10, 0.28)
        UA._cyl(f"{tag}_st{k}", fx, fy, 0.08, 0.007, fh, M["flower_leaf"], C, verts=5)
        UA._sph(
            f"{tag}_bl{k}",
            fx,
            fy,
            0.08 + fh,
            _rng.uniform(0.032, 0.07),
            _rng.choice(fmats),
            C,
            segs=6,
            rings=4,
        )


def _fb_ns(tag, x_inner, side, y0, y1, C):
    """N-S flower-bed segment from y0 to y1. side='e': grows east, 'w': grows west."""
    if y1 <= y0:
        return
    fw2 = FW / 2.0
    cx = x_inner + (fw2 if side == "e" else -fw2)
    cy = (y0 + y1) / 2.0
    dy = y1 - y0
    UA._box(f"{tag}_g", cx, cy, 0.04, FW, dy, 0.08, M["grass_lush"], C)
    _scatter_fb(tag, cx, cy, FW, dy, C, seed=abs(hash(tag)) % 99991)


def _fb_ew(tag, y_inner, side, x0, x1, C):
    """E-W flower-bed segment from x0 to x1. side='n': grows north, 's': grows south."""
    if x1 <= x0:
        return
    fw2 = FW / 2.0
    cy = y_inner + (fw2 if side == "n" else -fw2)
    cx = (x0 + x1) / 2.0
    dx = x1 - x0
    UA._box(f"{tag}_g", cx, cy, 0.04, dx, FW, 0.08, M["grass_lush"], C)
    _scatter_fb(tag, cx, cy, dx, FW, C, seed=abs(hash(tag)) % 99991)


def _build_fence(tag, cx, cy, fw, fd, gate_side="w", gate_w=2.0, C=None, h=1.4):
    """Rectangular iron fence (fw × fd) centred at (cx,cy). Gate on gate_side face."""
    mat, post = M["fence_iron"], M["gate_post"]
    hw, hd = fw / 2.0, fd / 2.0
    ghalf = gate_w / 2.0
    # 4 corner posts
    for k, (px, py) in enumerate(
        [(cx + hw, cy + hd), (cx - hw, cy + hd), (cx + hw, cy - hd), (cx - hw, cy - hd)]
    ):
        UA._cyl(f"{tag}_cp{k}", px, py, 0, 0.09, h + 0.4, post, C, verts=8)
    # North face (full, runs in X)
    UA._box(f"{tag}_fn", cx, cy + hd, h / 2, fw, 0.10, h, mat, C)
    # South face (full, runs in X)
    UA._box(f"{tag}_fs", cx, cy - hd, h / 2, fw, 0.10, h, mat, C)
    # East face
    if gate_side == "e":
        seg = hd - ghalf
        if seg > 0.05:
            UA._box(
                f"{tag}_fe_lo",
                cx + hw,
                cy - (hd + ghalf) / 2,
                h / 2,
                0.10,
                seg,
                h,
                mat,
                C,
            )
            UA._box(
                f"{tag}_fe_hi",
                cx + hw,
                cy + (hd + ghalf) / 2,
                h / 2,
                0.10,
                seg,
                h,
                mat,
                C,
            )
        UA._cyl(f"{tag}_egp1", cx + hw, cy - ghalf, 0, 0.11, h + 0.6, post, C, verts=8)
        UA._cyl(f"{tag}_egp2", cx + hw, cy + ghalf, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        UA._box(f"{tag}_fe", cx + hw, cy, h / 2, 0.10, fd, h, mat, C)
    # West face
    if gate_side == "w":
        seg = hd - ghalf
        if seg > 0.05:
            UA._box(
                f"{tag}_fw_lo",
                cx - hw,
                cy - (hd + ghalf) / 2,
                h / 2,
                0.10,
                seg,
                h,
                mat,
                C,
            )
            UA._box(
                f"{tag}_fw_hi",
                cx - hw,
                cy + (hd + ghalf) / 2,
                h / 2,
                0.10,
                seg,
                h,
                mat,
                C,
            )
        UA._cyl(f"{tag}_wgp1", cx - hw, cy - ghalf, 0, 0.11, h + 0.6, post, C, verts=8)
        UA._cyl(f"{tag}_wgp2", cx - hw, cy + ghalf, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        UA._box(f"{tag}_fw", cx - hw, cy, h / 2, 0.10, fd, h, mat, C)


def _turn_arrow(tag, cx, cy, yaw, C):
    """Road turn arrow at (cx,cy) pointing in yaw direction (0=north, −π/2=east)."""
    mat = M["stripe_w"]
    dir_x = -math.sin(yaw)
    dir_y = math.cos(yaw)
    # Shaft
    sh = UA._box(f"a_{tag}_sh", cx, cy, 0.026, 0.22, 1.5, 0.004, mat, C)
    sh.rotation_euler.z = yaw
    # Arrowhead wings
    tip_x = cx + dir_x * 0.75
    tip_y = cy + dir_y * 0.75
    for s in [1, -1]:
        w_yaw = yaw + s * math.radians(32)
        wd_x = -math.sin(w_yaw)
        wd_y = math.cos(w_yaw)
        wc_x = tip_x - wd_x * 0.27
        wc_y = tip_y - wd_y * 0.27
        wing = UA._box(f"a_{tag}_w{s}", wc_x, wc_y, 0.026, 0.22, 0.55, 0.004, mat, C)
        wing.rotation_euler.z = w_yaw


def _crosswalk_ns(tag, arm_sign, C):
    """Zebra crosswalk across a N-S arm (stripes run in X). arm_sign: +1=north, -1=south."""
    CW_W, CW_G = 0.55, 0.28
    y_base = arm_sign * (R + 0.5)
    for k in range(4):
        y = y_base + arm_sign * k * (CW_W + CW_G)
        UA._box(f"xwk_{tag}{k}", 0, y, 0.026, 2 * R - 0.2, CW_W, 0.004, M["xwalk"], C)


def _crosswalk_ew(tag, arm_sign, C):
    """Zebra crosswalk across an E-W arm (stripes run in Y). arm_sign: +1=east, -1=west."""
    CW_W, CW_G = 0.55, 0.28
    x_base = arm_sign * (R + 0.5)
    for k in range(4):
        x = x_base + arm_sign * k * (CW_W + CW_G)
        UA._box(f"xwk_{tag}{k}", x, 0, 0.026, CW_W, 2 * R - 0.2, 0.004, M["xwalk"], C)


def _shop_facade(tag, cx, cy, C, w=4.0, d=3.0, h=3.6, mat=None, aw_mat=None):
    """Simple shop building facing west (front at X = cx−d/2). w=Y-width, d=X-depth."""
    mat = mat or M["shop_beige"]
    aw = aw_mat or M["awning_g"]
    # Body
    UA._box(f"{tag}_body", cx, cy, h / 2, d, w, h, mat, C)
    # West-face glass
    UA._box(
        f"{tag}_gl",
        cx - d / 2 + 0.06,
        cy,
        h * 0.38,
        0.10,
        w * 0.68,
        h * 0.52,
        M["window"],
        C,
    )
    # Awning (project 1.0m from front face)
    UA._box(f"{tag}_aw", cx - d / 2 - 0.7, cy, h * 0.68, 1.4, w * 0.82, 0.10, aw, C)
    # Sign
    UA._box(
        f"{tag}_sg",
        cx - d / 2 + 0.06,
        cy,
        h * 0.85,
        0.14,
        w * 0.72,
        0.44,
        M["sign_bg"],
        C,
    )


# ─── GROUND PLANE ─────────────────────────────────────────────────────────────
_gm = UA._noise_mat("gnd", (0.34, 0.28, 0.20), (0.24, 0.20, 0.14), rough=0.92)
UA._box("gnd", 0, 0, -0.08, 300, 300, 0.16, _gm, C_sw)

# ─── CROSSROADS GEOMETRY ──────────────────────────────────────────────────────
# Intersection box
UA._box("isect", 0, 0, 0.02, 2 * R, 2 * R, 0.04, M["road"], C_road)

# N and S road arms + their sidewalks
for ys, t in [(+1, "n"), (-1, "s")]:
    yc = ys * (R + ARM / 2)
    UA._box(f"road_{t}", 0, yc, 0.02, 2 * R, ARM, 0.04, M["road"], C_road)
    UA._box(f"sw_{t}_e", S1 - SW / 2, yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
    UA._box(f"sw_{t}_w", -(S1 - SW / 2), yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)

# E and W road arms + their sidewalks
for xs, t in [(+1, "e"), (-1, "w")]:
    xc = xs * (R + ARM / 2)
    UA._box(f"road_{t}", xc, 0, 0.02, ARM, 2 * R, 0.04, M["road"], C_road)
    UA._box(f"sw_{t}_n", xc, S1 - SW / 2, 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
    UA._box(f"sw_{t}_s", xc, -(S1 - SW / 2), 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)

# Corner sidewalk tiles (4 intersection corners)
for xs, ys in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
    UA._box(
        f"corner_{xs}{ys}",
        xs * (R + SW / 2),
        ys * (R + SW / 2),
        0.03,
        SW,
        SW,
        0.04,
        M["sidewalk"],
        C_sw,
    )

# ─── LANE MARKINGS ────────────────────────────────────────────────────────────
# Yellow centre lines
UA._box("cl_ns", 0, 0, 0.025, 0.12, 2 * (R + ARM), 0.004, M["stripe_y"], C_road)
UA._box("cl_ew", 0, 0, 0.025, 2 * (R + ARM), 0.12, 0.004, M["stripe_y"], C_road)

# White dashed lane markings — N/S arms
DL, DG = 1.5, 1.5  # dash length, gap
for sgn in [+1, -1]:
    for lx in [2.0, -2.0]:
        y, k = sgn * (R + 1.0), 0
        while abs(y) < R + ARM - 1.0:
            UA._box(
                f"dash_ns_{sgn}_{lx}_{k}",
                lx,
                y + sgn * DL / 2,
                0.025,
                0.10,
                DL,
                0.004,
                M["stripe_w"],
                C_road,
            )
            y += sgn * (DL + DG)
            k += 1

# White dashed markings — E/W arms
for sgn in [+1, -1]:
    for ly in [2.0, -2.0]:
        x, k = sgn * (R + 1.0), 0
        while abs(x) < R + ARM - 1.0:
            UA._box(
                f"dash_ew_{sgn}_{ly}_{k}",
                x + sgn * DL / 2,
                ly,
                0.025,
                DL,
                0.10,
                0.004,
                M["stripe_w"],
                C_road,
            )
            x += sgn * (DL + DG)
            k += 1

# Stop lines at intersection edges
UA._box("stop_n", 0, (R + 0.3), 0.025, 2 * R, 0.22, 0.004, M["stripe_w"], C_road)
UA._box("stop_s", 0, -(R + 0.3), 0.025, 2 * R, 0.22, 0.004, M["stripe_w"], C_road)
UA._box("stop_e", (R + 0.3), 0, 0.025, 0.22, 2 * R, 0.004, M["stripe_w"], C_road)
UA._box("stop_w", -(R + 0.3), 0, 0.025, 0.22, 2 * R, 0.004, M["stripe_w"], C_road)

# Crosswalk zebra stripes
_crosswalk_ns("n", +1, C_road)
_crosswalk_ns("s", -1, C_road)
_crosswalk_ew("e", +1, C_road)
_crosswalk_ew("w", -1, C_road)

# ─── TURN ARROWS ──────────────────────────────────────────────────────────────
# Right-hand traffic (China): right lane is to the right of travel direction
# N arm northbound, right lane X=2: pointing north (yaw=0)
_turn_arrow("n1", 2.0, 11.0, 0.0, C_road)
_turn_arrow("n2", 2.0, 17.0, 0.0, C_road)
# S arm southbound, right lane X=-2: pointing south (yaw=π)
_turn_arrow("s1", -2.0, -11.0, math.pi, C_road)
_turn_arrow("s2", -2.0, -17.0, math.pi, C_road)
# E arm eastbound, right lane Y=-2: pointing east (yaw=-π/2)
_turn_arrow("e1", 11.0, -2.0, -math.pi / 2, C_road)
_turn_arrow("e2", 17.0, -2.0, -math.pi / 2, C_road)
# W arm westbound, right lane Y=2: pointing west (yaw=+π/2)
_turn_arrow("w1", -11.0, 2.0, math.pi / 2, C_road)
_turn_arrow("w2", -17.0, 2.0, math.pi / 2, C_road)

# ─── TRAFFIC LIGHTS (corrected yaw from v4) ───────────────────────────────────
UA.place_trafficlight((0.0, -(R + 2.5)), C_tl, yaw=0)  # S gantry → northbound
UA.place_trafficlight((0.0, (R + 2.5)), C_tl, yaw=math.pi)  # N gantry → southbound
UA.place_trafficlight((-(R + 2.5), 0.0), C_tl, yaw=-math.pi / 2)  # W gantry → eastbound
UA.place_trafficlight(((R + 2.5), 0.0), C_tl, yaw=math.pi / 2)  # E gantry → westbound

# ─── CURB FLOWER BEDS — segmented with openings at key access points ──────────
# N arm east side  (X=[7,9.5], Y=[4,48])
# Gaps: Y=[13,17] bike station | Y=[26,30] house-A gate | Y=[42,46] house-B gate
_fb_ns("fb_ne1", S1, "e", R, 13, C_fb)
_fb_ns("fb_ne2", S1, "e", 17, 26, C_fb)
_fb_ns("fb_ne3", S1, "e", 30, 42, C_fb)
_fb_ns("fb_ne4", S1, "e", 46, R + ARM, C_fb)

# N arm west side  (X=[-9.5,-7])
# Gap: Y=[30,34] house-C gate
_fb_ns("fb_nw1", -S1, "w", R, 30, C_fb)
_fb_ns("fb_nw2", -S1, "w", 34, R + ARM, C_fb)

# S arm east side  (X=[7,9.5], Y=[-48,-4])
# Gaps for 3 shop entrances at Y=[-16,-12], [-26,-22], [-36,-32]
_fb_ns("fb_se1", S1, "e", -(R + ARM), -36, C_fb)
_fb_ns("fb_se2", S1, "e", -32, -26, C_fb)
_fb_ns("fb_se3", S1, "e", -22, -16, C_fb)
_fb_ns("fb_se4", S1, "e", -12, -R, C_fb)

# S arm west side  (continuous)
_fb_ns("fb_sw", -S1, "w", -(R + ARM), -R, C_fb)

# E arm north side  (Y=[7,9.5], X=[4,48])
# Gap: X=[11,15] park entrance
_fb_ew("fb_en1", S1, "n", R, 11, C_fb)
_fb_ew("fb_en2", S1, "n", 15, R + ARM, C_fb)

# E arm south side  (continuous)
_fb_ew("fb_es", -S1, "s", R, R + ARM, C_fb)

# W arm both sides  (continuous)
_fb_ew("fb_wn", S1, "n", -(R + ARM), -R, C_fb)
_fb_ew("fb_ws", -S1, "s", -(R + ARM), -R, C_fb)

# ═══════════════════════════════════════════════════════════════════════════════
# NORTH ARM — RESIDENTIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════

# Bus stop — N arm east sidewalk at (5.5, 20), opens toward road (west = −X)
UA.place_busstop((5.5, 20.0), C_n, yaw=-math.pi / 2, scale=1.5)

# Bike station — parallel to N-S road (yaw=0 = bikes run in Y = parallel to road)
# Placed just outside flower bed at X=10.8, with small paved pad
UA._box("bike_pad", 11.0, 14.0, 0.03, 3.5, 8.5, 0.06, M["stone_path"], C_sw)
UA.place_bicycle_station((11.0, 14.0), C_n, yaw=0)

# ── House A — east side, faces road (west = −X), at (18, 28) ─────────────────
A_CX, A_CY = 18.0, 28.0
UA.build_house(
    "hA",
    A_CX,
    A_CY,
    C_n,
    w=12,
    d=8,
    wall_h=3.2,
    yaw=-math.pi / 2,
    mat_wall=M["wall_tan"],
    mat_roof=M["roof_tile"],
    n_win_front=2,
)
_build_fence("fA", A_CX, A_CY, fw=16, fd=14, gate_side="w", gate_w=2.2, C=C_n)
# Driveway from flower-bed edge (X=9.5) through gap to fence gate (X=A_CX−8=10)
UA._box("drv_a_out", (S1 + G1) / 2, A_CY, 0.03, FW, 2.4, 0.06, M["stone_path"], C_sw)
UA._box("drv_a_in", G1 + 1.5, A_CY, 0.03, 3.0, 2.4, 0.06, M["stone_path"], C_sw)

# ── House B — east side, faces road, at (18, 44) ─────────────────────────────
B_CX, B_CY = 18.0, 44.0
UA.build_house(
    "hB",
    B_CX,
    B_CY,
    C_n,
    w=12,
    d=8,
    wall_h=3.2,
    yaw=-math.pi / 2,
    mat_wall=M["wall_cream"],
    mat_roof=M["roof_flat"],
    n_win_front=3,
)
_build_fence("fB", B_CX, B_CY, fw=16, fd=14, gate_side="w", gate_w=2.2, C=C_n)
UA._box("drv_b_out", (S1 + G1) / 2, B_CY, 0.03, FW, 2.4, 0.06, M["stone_path"], C_sw)
UA._box("drv_b_in", G1 + 1.5, B_CY, 0.03, 3.0, 2.4, 0.06, M["stone_path"], C_sw)

# ── House C — west side, faces road (east = +X), at (−19, 32) ───────────────
C_CX, C_CY = -19.0, 32.0
UA.build_house(
    "hC",
    C_CX,
    C_CY,
    C_n,
    w=12,
    d=8,
    wall_h=3.2,
    yaw=math.pi / 2,
    mat_wall=M["wall_blue"],
    mat_roof=M["roof_tile"],
    n_win_front=2,
)
_build_fence("fC", C_CX, C_CY, fw=16, fd=14, gate_side="e", gate_w=2.2, C=C_n)
UA._box("drv_c_out", -(S1 + G1) / 2, C_CY, 0.03, FW, 2.4, 0.06, M["stone_path"], C_sw)
UA._box("drv_c_in", -(G1 + 1.5), C_CY, 0.03, 3.0, 2.4, 0.06, M["stone_path"], C_sw)

# Yard shrubs (inside fence, scale=1.6 for hedges and small trees)
for i, (sx, sy, si) in enumerate([(13, 22, 0), (22, 22, 2), (22, 34, 1), (13, 34, 3)]):
    UA.place_shrub_belt2(f"ysh_a{i}", (sx, sy), C_tree, scale=1.6, shrub_idx=si)
for i, (sx, sy, si) in enumerate([(13, 38, 4), (22, 38, 2), (22, 50, 0), (13, 50, 3)]):
    UA.place_shrub_belt2(f"ysh_b{i}", (sx, sy), C_tree, scale=1.6, shrub_idx=si)
for i, (sx, sy, si) in enumerate(
    [(-14, 26, 1), (-24, 26, 3), (-14, 38, 0), (-24, 38, 2)]
):
    UA.place_shrub_belt2(f"ysh_c{i}", (sx, sy), C_tree, scale=1.6, shrub_idx=si)

# Street trees — N arm, beyond zone (large belt2 at scale=3.5)
for i, (tx, ty, si) in enumerate(
    [
        (8.25, 10, 0),
        (8.25, 16, 2),
        (8.25, 22, 4),
        (8.25, 36, 1),
        (-8.25, 10, 3),
        (-8.25, 16, 1),
        (-8.25, 22, 0),
        (-8.25, 36, 2),
    ]
):
    UA.place_shrub_belt2(f"nt_tr{i}", (tx, ty), C_tree, scale=3.5, shrub_idx=si)

# N arm street lamps (east side yaw=+π/2, west side yaw=−π/2)
for y in [8, 14, 20, 26, 32, 38, 44]:
    UA.place_streetlight((R + SW / 2 - 0.2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-(R + SW / 2 - 0.2), y), C_lamp, yaw=-math.pi / 2, day=True)

# N arm sidewalk furniture
for y in [10, 24, 38]:
    UA.place_bench_classic((S1 - SW / 2 + 0.3, y), C_furn, yaw=math.pi / 2)
for y in [18, 30]:
    UA.place_bin_domed((S1 - SW / 2 + 0.3, y), C_furn)

# ═══════════════════════════════════════════════════════════════════════════════
# EAST ARM — PARK ZONE
# ═══════════════════════════════════════════════════════════════════════════════

# Park lawn base (Y=[9.5,42], X=[10,46])
UA._box("park_lawn", 28, 26, 0.02, 36, 32, 0.04, M["grass_lush"], C_e)

# Park entrance: gate posts at Y=9 on E arm N flower-bed edge (X=[11,15])
UA._cyl("park_gp1", 11, G1 + 0.2, 0, 0.14, 2.2, M["gate_post"], C_e, verts=8)
UA._cyl("park_gp2", 15, G1 + 0.2, 0, 0.14, 2.2, M["gate_post"], C_e, verts=8)
UA._box("park_ep", 13, (S1 + G1) / 2, 0.03, 2.0, FW, 0.06, M["stone_path"], C_sw)

# Park internal path network (stone paths)
UA._box("ppth_ns", 13, 21, 0.04, 2.2, 24, 0.08, M["stone_path"], C_e)  # N-S main path
UA._box("ppth_ew", 24, 22, 0.04, 22, 2.2, 0.08, M["stone_path"], C_e)  # E-W to pavilion
UA._box("ppth_circ", 30, 22, 0.04, 8, 2.2, 0.08, M["stone_path"], C_e)  # circle area
# Circular plaza around pavilion
bpy.ops.mesh.primitive_cylinder_add(
    vertices=24, radius=5.5, depth=0.10, location=(30, 22, 0.06)
)
_plaza = bpy.context.active_object
_plaza.name = "park_plaza"
_plaza.data.materials.append(M["park_stone"])
UA.to_coll(_plaza, C_e)

# ── Import Chinese Pavilion from sculpture blend ──────────────────────────────
pav_objs = UA._import_prefix(SC_BLEND, "pav:", C_e)
if pav_objs:
    UA._place(pav_objs, 30.0, 22.0)
    print(f"[v5] Chinese pavilion imported ({len(pav_objs)} objects)")
else:
    # Procedural fallback: simple hexagonal gazebo
    mat_gs = M["park_stone"]
    UA._cyl("pav_base", 30, 22, 0.0, 4.0, 0.35, mat_gs, C_e, verts=6)
    for i in range(6):
        a = i * math.pi / 3
        px, py = 30 + 2.5 * math.cos(a), 22 + 2.5 * math.sin(a)
        UA._cyl(f"pav_col{i}", px, py, 0.35, 0.18, 3.2, mat_gs, C_e, verts=12)
    UA._cyl("pav_roof", 30, 22, 3.55, 3.8, 0.18, M["roof_tile"], C_e, verts=6)
    bpy.ops.mesh.primitive_cone_add(
        radius1=3.6, radius2=0.25, depth=1.5, location=(30, 22, 4.6)
    )
    _cone = bpy.context.active_object
    _cone.name = "pav_roof_cone"
    _cone.data.materials.append(M["roof_tile"])
    UA.to_coll(_cone, C_e)

# ── Import Victorian Bandstand ────────────────────────────────────────────────
band_objs = UA._import_prefix(SC_BLEND, "band:", C_e)
if band_objs:
    UA._place(band_objs, 18.0, 30.0)
    print(f"[v5] Bandstand imported ({len(band_objs)} objects)")

# ── Water feature at (20, 15) ─────────────────────────────────────────────────
UA._cyl("wf_rim", 20, 15, 0.04, 2.4, 0.32, M["park_stone"], C_e, verts=24)
UA._cyl("wf_water", 20, 15, 0.04, 1.9, 0.24, M["water_blue"], C_e, verts=24)
UA._cyl("wf_spout", 20, 15, 0.28, 0.06, 1.0, M["park_stone"], C_e, verts=12)
UA._cyl("wf_basin", 20, 15, 1.30, 0.35, 0.08, M["park_stone"], C_e, verts=16)

# Park benches and bins
for px, py, pw in [(13.5, 14, math.pi / 2), (13.5, 26, math.pi / 2), (24, 34, 0)]:
    UA.place_bench_classic((px, py), C_e, yaw=pw)
for px, py in [(17, 12), (27, 32)]:
    UA.place_bin_domed((px, py), C_e)

# Phone booth on E arm north sidewalk
UA.place_phonebooth((22, S1 - SW / 2), C_furn, yaw=math.pi)  # facing south toward road

# E arm lamps (N side yaw=π, S side yaw=0)
for x in [8, 14, 20, 26, 32, 38, 44]:
    UA.place_streetlight((x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -(R + SW / 2 - 0.2)), C_lamp, yaw=0, day=True)

# Park trees — large belt2 shrubs throughout park
for i, (tx, ty, sc, si) in enumerate(
    [
        (11.5, 12, 3.0, 0),
        (11.5, 20, 3.5, 2),
        (11.5, 32, 3.5, 4),
        (24, 12, 3.0, 1),
        (36, 12, 3.5, 3),
        (40, 20, 4.0, 0),
        (40, 32, 3.5, 2),
        (36, 38, 3.0, 1),
        (24, 38, 3.5, 3),
    ]
):
    UA.place_shrub_belt2(f"pk_tr{i}", (tx, ty), C_tree, scale=sc, shrub_idx=si)

# ═══════════════════════════════════════════════════════════════════════════════
# SOUTH ARM — COMMERCIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════

# 3 kiosk5 shops on east side of S arm, facing road (west, yaw=−π/2)
for i, cy_shop in enumerate([-14.0, -24.0, -34.0]):
    UA.place_kiosk5((12.0, cy_shop), C_s, yaw=-math.pi / 2, scale=1.5)
    # Path from sidewalk (X=7) through flower bed gap to shop entrance
    UA._box(
        f"shop_path{i}",
        (S1 + G1) / 2,
        cy_shop,
        0.03,
        FW,
        2.2,
        0.06,
        M["stone_path"],
        C_sw,
    )
    UA._box(
        f"shop_pad{i}", G1 + 1.5, cy_shop, 0.03, 3.0, 2.2, 0.06, M["stone_path"], C_sw
    )

# Simple storefronts between kiosks (facing west)
_shop_facade(
    "sf1",
    11.5,
    -19.0,
    C_s,
    w=4.0,
    d=3.0,
    h=3.6,
    mat=M["shop_beige"],
    aw_mat=M["awning_r"],
)
_shop_facade(
    "sf2",
    11.5,
    -29.0,
    C_s,
    w=4.0,
    d=3.0,
    h=3.6,
    mat=M["shop_red"],
    aw_mat=M["awning_b"],
)

# S arm street lamps (east/west sidewalks)
for y in [-8, -14, -20, -26, -32, -38]:
    UA.place_streetlight((R + SW / 2 - 0.2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-(R + SW / 2 - 0.2), y), C_lamp, yaw=-math.pi / 2, day=True)

# S arm sidewalk furniture
for y in [-16, -28]:
    UA.place_bench_classic((S1 - SW / 2 + 0.3, y), C_furn, yaw=math.pi / 2)
for y in [-20, -30, -40]:
    UA.place_bin_domed((S1 - SW / 2 + 0.3, y), C_furn)
UA.place_phonebooth((5.5, -42.0), C_furn, yaw=0)  # faces north (toward intersection)

# Street trees behind commercial zone
for i, (tx, ty, si) in enumerate(
    [
        (8.25, -8, 0),
        (8.25, -18, 3),
        (8.25, -28, 1),
        (8.25, -38, 4),
        (-8.25, -8, 2),
        (-8.25, -18, 0),
        (-8.25, -28, 3),
        (-8.25, -38, 1),
    ]
):
    UA.place_shrub_belt2(f"st_tr{i}", (tx, ty), C_tree, scale=3.5, shrub_idx=si)

# ═══════════════════════════════════════════════════════════════════════════════
# WEST ARM — BASIC STREET CONTINUATION
# ═══════════════════════════════════════════════════════════════════════════════

# W arm street lamps
for x in [-8, -14, -20, -26, -32, -38]:
    UA.place_streetlight((x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -(R + SW / 2 - 0.2)), C_lamp, yaw=0, day=True)

# Belt2 shrubs in W arm zone areas (beyond flower beds)
for i, (tx, ty, si) in enumerate(
    [
        (-12, 8.25, 0),
        (-20, 8.25, 2),
        (-28, 8.25, 4),
        (-36, 8.25, 1),
        (-12, -8.25, 3),
        (-20, -8.25, 0),
        (-28, -8.25, 2),
        (-36, -8.25, 4),
    ]
):
    UA.place_shrub_belt2(f"wt_tr{i}", (tx, ty), C_w, scale=3.0, shrub_idx=si)

# ─── VEHICLES ─────────────────────────────────────────────────────────────────
# Right-hand traffic: northbound in right lane (X>0), southbound (X<0)
UA.place_vehicle("v_n", (2.5, 22.0), C_cars, yaw=math.pi / 2)  # northbound Ducato
UA.place_vehicle("v_w", (-30.0, 2.5), C_cars, yaw=math.pi)  # westbound Ducato

# Infinigen cars if available
_CARS = {
    "car_eastbound": (22.0, -2.5, 0.0),
    "car_southbound": (-2.5, -20.0, -math.pi / 2),
}
for vkey, (vx, vy, vyaw) in _CARS.items():
    try:
        UA.place_infinigen_car(f"inf_{vkey}", vkey, (vx, vy), C_cars, yaw_extra=vyaw)
    except Exception:
        pass  # skip if vehicles_inf blend missing

# ─── WORLD LIGHTING ───────────────────────────────────────────────────────────
UA.build_world_lighting()

# ─── GPU SETUP ────────────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 128
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = False

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dtype in ("CUDA", "OPTIX", "HIP", "METAL"):
        try:
            prefs.compute_device_type = dtype
            prefs.get_devices()
            if any(d.type != "CPU" for d in prefs.devices):
                for d in prefs.devices:
                    d.use = True
                break
        except Exception:
            continue
    scene.cycles.device = "GPU"
except Exception:
    pass

# AgX colour management
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass
scene.view_settings.exposure = -0.5


# ─── CAMERAS ──────────────────────────────────────────────────────────────────
def _make_camera(name, loc, target, focal=50):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.lens = focal
    direction = Vector(target) - Vector(loc)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


cameras = [
    ("overview", (-52, -68, 58), (2, 2, 2), 24),
    ("residential", (-9, 16, 2.8), (14, 28, 2), 50),
    ("park", (5, -7, 3.0), (24, 20, 2), 50),
    ("commercial", (-9, -22, 2.8), (12, -16, 3), 50),
    ("intersection", (0.5, -13, 2.8), (0, 2, 5.5), 50),
]
cam_objects = {}
for cname, loc, tgt, fl in cameras:
    cam_objects[cname] = _make_camera(cname, loc, tgt, fl)

# ─── SAVE .BLEND ──────────────────────────────────────────────────────────────
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all5.blend"))
print("[v5] .blend saved")

# ─── RENDER ALL CAMERAS ───────────────────────────────────────────────────────
for cname, cam in cam_objects.items():
    scene.camera = cam
    out_png = str(OUT / f"{cname}.png")
    scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    print(f"[v5] rendered {cname} → {out_png}")

print("[v5] All done. Files in", OUT)
