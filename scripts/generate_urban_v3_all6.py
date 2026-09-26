"""
generate_urban_v3_all6.py
=========================
Complete redesign of outdoor scene — 4-zone crossroads.

Zones:
  North (+Y): Residential — houses, iron fences, gates, paved driveways, bus stop, bike station
  East  (+X): Park        — Chinese pavilion, bandstand, sculptures, lawn, infinigen trees
  South (-Y): Commercial  — shop facades, kiosk, phone booth, street furniture
  West  (-X): Green belt  — trees, lamps, benches

Rules enforced:
  1. Wide crossroads with lane markings, stop lines, turn arrows, crosswalks
  2. Residential: houses set back from road, outer fence+gate, paved path to sidewalk
  3. Park: pavilion, bandstand, sculpture, benches, infinigen trees, lawn, entrance
  4. Commercial: shops along street facing sidewalk, awnings, signs
  5. Road: vehicles + traffic markings ONLY
  6. Continuous curb flower beds, gaps at entries/crosswalks/stops
  7. Bus stop on sidewalk, not on road
  8. Bike station parallel to road, sidewalk edge, near bus stop
  9. Continuous stone sidewalks on both sides
  10. Street furniture on sidewalk edges
  11. Clear zone boundaries — no spatial overlap

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all6/
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

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all6")
OUT.mkdir(parents=True, exist_ok=True)

SC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sculpture/public_art.blend"
)

UA.reset_scene()
UA.build_all_materials()
M = UA.M

# ─── EXTRA MATERIALS ──────────────────────────────────────────────────────────
M["wall_beige"] = UA._noise_mat(
    "wall_beige", (0.85, 0.80, 0.68), (0.75, 0.70, 0.58), rough=0.68, scale=7
)
M["wall_white"] = UA._noise_mat(
    "wall_white", (0.90, 0.88, 0.82), (0.82, 0.80, 0.74), rough=0.65, scale=8
)
M["wall_blue"] = UA._noise_mat(
    "wall_blue", (0.52, 0.62, 0.78), (0.44, 0.54, 0.68), rough=0.68, scale=8
)
M["wall_cream"] = UA._noise_mat(
    "wall_cream", (0.88, 0.84, 0.72), (0.80, 0.76, 0.64), rough=0.68, scale=9
)
M["grass_park"] = UA._noise_mat(
    "grass_park", (0.08, 0.28, 0.04), (0.14, 0.38, 0.08), rough=0.82, scale=20
)
M["stone_path"] = UA._noise_mat(
    "stone_path", (0.70, 0.66, 0.58), (0.60, 0.56, 0.48), rough=0.78, scale=11
)
M["fence_iron"] = UA._pbr("fence_iron", (0.08, 0.08, 0.10), rough=0.32, metal=0.88)
M["gate_post"] = UA._pbr("gate_post", (0.12, 0.12, 0.14), rough=0.28, metal=0.92)
M["awning_r"] = UA._pbr("awning_r", (0.72, 0.18, 0.10), rough=0.76)
M["awning_g"] = UA._pbr("awning_g", (0.18, 0.50, 0.20), rough=0.76)
M["awning_b"] = UA._pbr("awning_b", (0.16, 0.28, 0.70), rough=0.76)
M["awning_y"] = UA._pbr("awning_y", (0.80, 0.64, 0.10), rough=0.76)
M["shop_beige"] = UA._noise_mat(
    "shop_beige", (0.82, 0.76, 0.64), (0.72, 0.66, 0.56), rough=0.70, scale=7
)
M["shop_red"] = UA._noise_mat(
    "shop_red", (0.68, 0.22, 0.12), (0.58, 0.18, 0.08), rough=0.66, scale=7
)
M["shop_blue"] = UA._noise_mat(
    "shop_blue", (0.30, 0.44, 0.70), (0.22, 0.36, 0.60), rough=0.66, scale=7
)
M["water_blue"] = UA._pbr("water_blue", (0.08, 0.32, 0.72), rough=0.03)
M["park_stone"] = UA._noise_mat(
    "park_stone", (0.70, 0.68, 0.62), (0.60, 0.58, 0.52), rough=0.68, scale=9
)
M["sign_bg"] = UA._pbr("sign_bg", (0.06, 0.18, 0.52), rough=0.72)
M["sign_comm"] = UA._pbr("sign_comm", (0.65, 0.08, 0.08), rough=0.72)
M["concrete"] = UA._noise_mat(
    "concrete", (0.62, 0.60, 0.56), (0.52, 0.50, 0.46), rough=0.82, scale=9
)
M["pool_rim"] = UA._pbr("pool_rim", (0.72, 0.70, 0.66), rough=0.55)

# ─── GEOMETRY CONSTANTS ───────────────────────────────────────────────────────
R = 4.5  # road half-width (9m total = 4 lanes)
SW = 3.5  # sidewalk width
FW = 2.5  # curb flower-bed width
S1 = R + SW  # 8.0   inner fb / outer sw edge
G1 = S1 + FW  # 10.5  outer fb / zone start
ARM = 50.0  # arm length from intersection edge

# lane centres
LC = R / 2  # 2.25 — centre of each half-road

# ─── COLLECTIONS ──────────────────────────────────────────────────────────────
C_road = UA.new_coll("Road")
C_sw = UA.new_coll("Sidewalks")
C_fb = UA.new_coll("FlowerBeds")
C_mk = UA.new_coll("RoadMarkings")
C_tl = UA.new_coll("TrafficLights")
C_n = UA.new_coll("Residential")
C_e = UA.new_coll("Park")
C_s = UA.new_coll("Commercial")
C_w = UA.new_coll("WestArm")
C_furn = UA.new_coll("Furniture")
C_lamp = UA.new_coll("Lamps")
C_cars = UA.new_coll("Vehicles")
C_tree = UA.new_coll("Trees")


# ─── SHORTHAND PRIMITIVES ─────────────────────────────────────────────────────
def _box(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=0.0, rz=0.0):
    return UA._box(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=bev, rz=rz)


def _cyl(name, cx, cy, cz, r, h, mat, coll, verts=24, rx=0.0, rz=0.0):
    return UA._cyl(name, cx, cy, cz, r, h, mat, coll, verts=verts, rx=rx, rz=rz)


def _sph(name, cx, cy, cz, r, mat, coll, segs=16, rings=12):
    return UA._sph(name, cx, cy, cz, r, mat, coll, segs=segs, rings=rings)


# ─── SCATTER FLOWERS ──────────────────────────────────────────────────────────
_fmats = None


def _scatter_fb(tag, cx, cy, dx, dy, C, n_override=None, seed=0):
    global _fmats
    if _fmats is None:
        _fmats = [M["flower_r"], M["flower_y"], M["flower_p"], M["flower_w"]]
    _rng.seed(seed % 99991)
    n = n_override or max(4, int(dx * dy * 1.8))
    for k in range(n):
        fx = cx + _rng.uniform(-dx / 2 + 0.15, dx / 2 - 0.15)
        fy = cy + _rng.uniform(-dy / 2 + 0.15, dy / 2 - 0.15)
        fh = _rng.uniform(0.12, 0.28)
        UA._cyl(f"{tag}_st{k}", fx, fy, 0.07, 0.007, fh, M["flower_leaf"], C, verts=5)
        UA._sph(
            f"{tag}_bl{k}",
            fx,
            fy,
            0.07 + fh,
            _rng.uniform(0.03, 0.065),
            _rng.choice(_fmats),
            C,
            segs=6,
            rings=4,
        )


# N-S flower-bed segment (x_inner = road-side edge; side='e' or 'w')
def _fb_ns(tag, x_inner, side, y0, y1, C):
    if y1 <= y0:
        return
    fw2 = FW / 2.0
    cx = x_inner + (fw2 if side == "e" else -fw2)
    cy = (y0 + y1) / 2.0
    dy = y1 - y0
    _box(f"{tag}_g", cx, cy, 0.04, FW, dy, 0.08, M["greenstrip"], C)
    _scatter_fb(tag, cx, cy, FW - 0.2, dy - 0.2, C, seed=abs(hash(tag)) % 99991)


# E-W flower-bed segment
def _fb_ew(tag, y_inner, side, x0, x1, C):
    if x1 <= x0:
        return
    fw2 = FW / 2.0
    cy = y_inner + (fw2 if side == "n" else -fw2)
    cx = (x0 + x1) / 2.0
    dx = x1 - x0
    _box(f"{tag}_g", cx, cy, 0.04, dx, FW, 0.08, M["greenstrip"], C)
    _scatter_fb(tag, cx, cy, dx - 0.2, FW - 0.2, C, seed=abs(hash(tag)) % 99991)


# ─── ROAD CROSSWALK + TURN ARROW HELPERS ──────────────────────────────────────
def _crosswalk_ns(tag, arm_sign, C):
    CW_W, CW_G = 0.50, 0.28
    y_base = arm_sign * (R + 0.55)
    for k in range(6):
        y = y_base + arm_sign * k * (CW_W + CW_G)
        _box(f"xwk_{tag}{k}", 0, y, 0.025, 2 * R - 0.3, CW_W, 0.004, M["xwalk"], C_mk)


def _crosswalk_ew(tag, arm_sign, C):
    CW_W, CW_G = 0.50, 0.28
    x_base = arm_sign * (R + 0.55)
    for k in range(6):
        x = x_base + arm_sign * k * (CW_W + CW_G)
        _box(f"xwk_{tag}{k}", x, 0, 0.025, CW_W, 2 * R - 0.3, 0.004, M["xwalk"], C_mk)


def _turn_arrow(tag, cx, cy, yaw, C):
    mat = M["stripe_w"]
    dx = -math.sin(yaw)
    dy = math.cos(yaw)
    sh = _box(f"arr_{tag}_sh", cx, cy, 0.026, 0.22, 1.5, 0.004, mat, C)
    sh.rotation_euler.z = yaw
    tip_x = cx + dx * 0.75
    tip_y = cy + dy * 0.75
    for s in [1, -1]:
        w_yaw = yaw + s * math.radians(32)
        wd_x = -math.sin(w_yaw)
        wd_y = math.cos(w_yaw)
        wc_x = tip_x - wd_x * 0.27
        wc_y = tip_y - wd_y * 0.27
        wing = _box(f"arr_{tag}_w{s}", wc_x, wc_y, 0.026, 0.22, 0.55, 0.004, mat, C)
        wing.rotation_euler.z = w_yaw


# ─── IRON FENCE PERIMETER ─────────────────────────────────────────────────────
def _build_fence(tag, cx, cy, fw, fd, gate_side="w", gate_w=2.4, C=None, h=1.4):
    mat, post = M["fence_iron"], M["gate_post"]
    hw, hd = fw / 2.0, fd / 2.0
    gh = gate_w / 2.0
    # Corner posts
    for k, (px, py) in enumerate(
        [(cx + hw, cy + hd), (cx - hw, cy + hd), (cx + hw, cy - hd), (cx - hw, cy - hd)]
    ):
        _cyl(f"{tag}_cp{k}", px, py, 0, 0.09, h + 0.4, post, C, verts=8)
    # North face (full)
    _box(f"{tag}_fn", cx, cy + hd, h / 2, fw, 0.10, h, mat, C)
    # South face (full)
    _box(f"{tag}_fs", cx, cy - hd, h / 2, fw, 0.10, h, mat, C)
    # East face (or gate)
    if gate_side == "e":
        for py0, py1, sfx in [(cy - hd, cy - gh, "lo"), (cy + gh, cy + hd, "hi")]:
            seg = abs(py1 - py0)
            if seg > 0.1:
                _box(
                    f"{tag}_fe_{sfx}",
                    cx + hw,
                    (py0 + py1) / 2,
                    h / 2,
                    0.10,
                    seg,
                    h,
                    mat,
                    C,
                )
        _cyl(f"{tag}_egp1", cx + hw, cy - gh, 0, 0.11, h + 0.6, post, C, verts=8)
        _cyl(f"{tag}_egp2", cx + hw, cy + gh, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        _box(f"{tag}_fe", cx + hw, cy, h / 2, 0.10, fd, h, mat, C)
    # West face (or gate)
    if gate_side == "w":
        for py0, py1, sfx in [(cy - hd, cy - gh, "lo"), (cy + gh, cy + hd, "hi")]:
            seg = abs(py1 - py0)
            if seg > 0.1:
                _box(
                    f"{tag}_fw_{sfx}",
                    cx - hw,
                    (py0 + py1) / 2,
                    h / 2,
                    0.10,
                    seg,
                    h,
                    mat,
                    C,
                )
        _cyl(f"{tag}_wgp1", cx - hw, cy - gh, 0, 0.11, h + 0.6, post, C, verts=8)
        _cyl(f"{tag}_wgp2", cx - hw, cy + gh, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        _box(f"{tag}_fw", cx - hw, cy, h / 2, 0.10, fd, h, mat, C)


# ─── SHOP FACADE (facing -X / west) ──────────────────────────────────────────
def _shop_w(tag, cx, cy, w, d, h, mat, aw_mat, C):
    """Shop body depth along X, front face at cx-d/2 (facing west)."""
    _box(f"{tag}_body", cx, cy, h / 2, d, w, h, mat, C, bev=0.02)
    _box(
        f"{tag}_gl",
        cx - d / 2 + 0.06,
        cy,
        h * 0.38,
        0.10,
        w * 0.70,
        h * 0.54,
        M["window"],
        C,
    )
    _box(
        f"{tag}_aw",
        cx - d / 2 - 0.72,
        cy,
        h * 0.70,
        1.44,
        w * 0.84,
        0.10,
        aw_mat,
        C,
        rz=math.radians(-4),
    )
    _box(
        f"{tag}_sg",
        cx - d / 2 + 0.06,
        cy,
        h * 0.86,
        0.14,
        w * 0.72,
        0.46,
        M["sign_comm"],
        C,
    )
    _box(f"{tag}_door", cx - d / 2 + 0.05, cy, 1.2, 0.12, 1.1, 2.4, M["door"], C)


# ─── SHOP FACADE (facing +X / east) ──────────────────────────────────────────
def _shop_e(tag, cx, cy, w, d, h, mat, aw_mat, C):
    """Shop body depth along X, front face at cx+d/2 (facing east)."""
    _box(f"{tag}_body", cx, cy, h / 2, d, w, h, mat, C, bev=0.02)
    _box(
        f"{tag}_gl",
        cx + d / 2 - 0.06,
        cy,
        h * 0.38,
        0.10,
        w * 0.70,
        h * 0.54,
        M["window"],
        C,
    )
    _box(
        f"{tag}_aw",
        cx + d / 2 + 0.72,
        cy,
        h * 0.70,
        1.44,
        w * 0.84,
        0.10,
        aw_mat,
        C,
        rz=math.radians(4),
    )
    _box(
        f"{tag}_sg",
        cx + d / 2 - 0.06,
        cy,
        h * 0.86,
        0.14,
        w * 0.72,
        0.46,
        M["sign_comm"],
        C,
    )
    _box(f"{tag}_door", cx + d / 2 - 0.05, cy, 1.2, 0.12, 1.1, 2.4, M["door"], C)


# ─── PROCEDURAL WATER FEATURE ────────────────────────────────────────────────
def _water_feature(tag, cx, cy, r, C):
    _cyl(f"{tag}_rim", cx, cy, 0.0, r + 0.18, 0.42, M["pool_rim"], C, verts=32)
    _cyl(f"{tag}_pool", cx, cy, 0.06, r, 0.28, M["water_blue"], C, verts=32)
    # Central spout column
    _cyl(f"{tag}_col", cx, cy, 0.34, 0.12, 1.20, M["pool_rim"], C, verts=12)
    _sph(f"{tag}_top", cx, cy, 1.54 + 0.24, 0.24, M["water_blue"], C, segs=12, rings=8)


# ─── PROCEDURAL SCULPTURE (abstract corten ring) ──────────────────────────────
def _corten_ring(tag, cx, cy, r, C):
    mat = UA._pbr(f"{tag}_corten", (0.48, 0.22, 0.06), rough=0.72)
    # 3 overlapping torus rings
    for i in range(3):
        ang = i * math.pi / 3
        ox, oy = cx + math.cos(ang) * r * 0.35, cy + math.sin(ang) * r * 0.35
        bpy.ops.mesh.primitive_torus_add(
            major_radius=r,
            minor_radius=r * 0.12,
            location=(ox, oy, r + 0.3),
            rotation=(math.radians(60 + i * 30), 0, ang),
        )
        o = bpy.context.active_object
        o.name = f"{tag}_ring{i}"
        o.data.materials.append(mat)
        UA.to_coll(o, C)


# ─── STONE PARK PLAZA (cylinder) ──────────────────────────────────────────────
def _plaza_circle(tag, cx, cy, r, C):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=r, depth=0.10, location=(cx, cy, 0.06)
    )
    o = bpy.context.active_object
    o.name = f"{tag}_plaza"
    o.data.materials.append(M["park_stone"])
    UA.to_coll(o, C)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUND PLANE
# ═══════════════════════════════════════════════════════════════════════════════
_gm = UA._noise_mat("gnd", (0.32, 0.26, 0.18), (0.22, 0.18, 0.12), rough=0.92)
_box("gnd", 0, 0, -0.10, 400, 400, 0.20, _gm, C_sw)

# ═══════════════════════════════════════════════════════════════════════════════
# CROSSROADS — ASPHALT + SIDEWALK CORNERS
# ═══════════════════════════════════════════════════════════════════════════════
# Intersection box
_box("isect", 0, 0, 0.02, 2 * R, 2 * R, 0.04, M["road"], C_road)

# N/S arm roads + sidewalks
for ys, t in [(+1, "n"), (-1, "s")]:
    yc = ys * (R + ARM / 2)
    _box(f"road_{t}", 0, yc, 0.02, 2 * R, ARM, 0.04, M["road"], C_road)
    _box(f"sw_{t}_e", S1 - SW / 2, yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
    _box(f"sw_{t}_w", -(S1 - SW / 2), yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
    # Kerbs
    _box(f"kerb_{t}_e", R + 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
    _box(f"kerb_{t}_w", -R - 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)

# E/W arm roads + sidewalks
for xs, t in [(+1, "e"), (-1, "w")]:
    xc = xs * (R + ARM / 2)
    _box(f"road_{t}", xc, 0, 0.02, ARM, 2 * R, 0.04, M["road"], C_road)
    _box(f"sw_{t}_n", xc, S1 - SW / 2, 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
    _box(f"sw_{t}_s", xc, -(S1 - SW / 2), 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
    # Kerbs
    _box(f"kerb_{t}_n", xc, R + 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
    _box(f"kerb_{t}_s", xc, -R - 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)

# Corner sidewalk patches at intersection
for xs, ys in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
    cx = xs * (R + SW / 2)
    cy = ys * (R + SW / 2)
    _box(f"sw_cor_{xs}{ys}", cx, cy, 0.03, SW, SW, 0.04, M["sidewalk"], C_sw)

# ═══════════════════════════════════════════════════════════════════════════════
# ROAD MARKINGS — LANE LINES + STOP LINES
# ═══════════════════════════════════════════════════════════════════════════════
FULL = R + ARM  # full half-length

# Double yellow centre lines (N-S)
for dx in (-0.10, 0.10):
    _box(f"cl_ns{dx:.0f}", dx, 0, 0.025, 0.08, 2 * FULL, 0.004, M["stripe_y"], C_mk)
# Double yellow centre lines (E-W)
for dy in (-0.10, 0.10):
    _box(f"cl_ew{dy:.0f}", 0, dy, 0.025, 2 * FULL, 0.08, 0.004, M["stripe_y"], C_mk)

# White dashed lane lines — N/S arms (at X=±LC)
DL, DG = 1.8, 1.8
for sgn in [+1, -1]:
    for lx in [LC, -LC]:
        y, k = sgn * (R + 1.0), 0
        while abs(y) < FULL - 1.0:
            _box(
                f"dash_ns_{sgn:.0f}_{lx:.1f}_{k}",
                lx,
                y + sgn * DL / 2,
                0.025,
                0.10,
                DL,
                0.004,
                M["stripe_w"],
                C_mk,
            )
            y += sgn * (DL + DG)
            k += 1

# White dashed lane lines — E/W arms (at Y=±LC)
for sgn in [+1, -1]:
    for ly in [LC, -LC]:
        x, k = sgn * (R + 1.0), 0
        while abs(x) < FULL - 1.0:
            _box(
                f"dash_ew_{sgn:.0f}_{ly:.1f}_{k}",
                x + sgn * DL / 2,
                ly,
                0.025,
                DL,
                0.10,
                0.004,
                M["stripe_w"],
                C_mk,
            )
            x += sgn * (DL + DG)
            k += 1

# Stop lines at intersection edges
for y in [(R + 0.32), -(R + 0.32)]:
    _box(f"stop_ns_{y:.1f}", 0, y, 0.025, 2 * R, 0.24, 0.004, M["stripe_w"], C_mk)
for x in [(R + 0.32), -(R + 0.32)]:
    _box(f"stop_ew_{x:.1f}", x, 0, 0.025, 0.24, 2 * R, 0.004, M["stripe_w"], C_mk)

# ═══════════════════════════════════════════════════════════════════════════════
# CROSSWALKS (all 4 arms)
# ═══════════════════════════════════════════════════════════════════════════════
_crosswalk_ns("n", +1, C_mk)
_crosswalk_ns("s", -1, C_mk)
_crosswalk_ew("e", +1, C_mk)
_crosswalk_ew("w", -1, C_mk)

# ═══════════════════════════════════════════════════════════════════════════════
# TURN ARROWS
# ═══════════════════════════════════════════════════════════════════════════════
# N arm: northbound (X=LC), southbound (-X side, X=-LC)
_turn_arrow("n_nb1", LC, 16.0, 0.0, C_mk)
_turn_arrow("n_nb2", LC, 26.0, 0.0, C_mk)
_turn_arrow("n_sb1", -LC, 16.0, math.pi, C_mk)
_turn_arrow("n_sb2", -LC, 26.0, math.pi, C_mk)
# S arm: southbound (X=LC going south, right lane X>0), northbound
_turn_arrow("s_sb1", LC, -16.0, 0.0, C_mk)
_turn_arrow("s_nb1", -LC, -16.0, math.pi, C_mk)
# E arm: eastbound (Y=-LC), westbound (Y=LC)
_turn_arrow("e_eb1", 16.0, -LC, -math.pi / 2, C_mk)
_turn_arrow("e_eb2", 26.0, -LC, -math.pi / 2, C_mk)
_turn_arrow("e_wb1", 16.0, LC, math.pi / 2, C_mk)
# W arm: westbound (Y=LC), eastbound (Y=-LC)
_turn_arrow("w_wb1", -16.0, LC, math.pi / 2, C_mk)
_turn_arrow("w_eb1", -16.0, -LC, -math.pi / 2, C_mk)

# ═══════════════════════════════════════════════════════════════════════════════
# TRAFFIC LIGHTS (4 gantries)
# ═══════════════════════════════════════════════════════════════════════════════
UA.place_trafficlight((0.0, -(R + 2.6)), C_tl, yaw=0)  # S gantry → northbound
UA.place_trafficlight((0.0, (R + 2.6)), C_tl, yaw=math.pi)  # N gantry → southbound
UA.place_trafficlight((-(R + 2.6), 0.0), C_tl, yaw=-math.pi / 2)  # W gantry → eastbound
UA.place_trafficlight(((R + 2.6), 0.0), C_tl, yaw=math.pi / 2)  # E gantry → westbound

# ═══════════════════════════════════════════════════════════════════════════════
# CURB FLOWER BEDS — Segmented with openings at all entry points
# ═══════════════════════════════════════════════════════════════════════════════
# N arm E flower bed (X inner edge = S1 = 8.0, grows east)
# Gaps: bus stop [12,16.5], bike station [19,23], house A gate [34,38], house B gate [48,52]
_fb_ns("fb_ne1", S1, "e", R, 12.0, C_fb)
_fb_ns("fb_ne2", S1, "e", 16.5, 19.0, C_fb)
_fb_ns("fb_ne3", S1, "e", 23.0, 34.0, C_fb)
_fb_ns("fb_ne4", S1, "e", 38.0, 48.0, C_fb)
_fb_ns("fb_ne5", S1, "e", 52.0, R + ARM, C_fb)

# N arm W flower bed (X inner edge = -S1, grows west)
# Gap: house C gate [36,40]
_fb_ns("fb_nw1", -S1, "w", R, 36.0, C_fb)
_fb_ns("fb_nw2", -S1, "w", 40.0, R + ARM, C_fb)

# S arm E flower bed
# Gaps for 3 shop entrances at Y=[-16,-18], [-28,-32], [-42,-46]
_fb_ns("fb_se1", S1, "e", -(R + ARM), -46.0, C_fb)
_fb_ns("fb_se2", S1, "e", -42.0, -32.0, C_fb)
_fb_ns("fb_se3", S1, "e", -28.0, -18.0, C_fb)
_fb_ns("fb_se4", S1, "e", -14.0, -R, C_fb)

# S arm W flower bed — gaps for west-side shop entrances
_fb_ns("fb_sw1", -S1, "w", -(R + ARM), -32.0, C_fb)
_fb_ns("fb_sw2", -S1, "w", -28.0, -18.0, C_fb)
_fb_ns("fb_sw3", -S1, "w", -14.0, -R, C_fb)

# E arm N flower bed — gap for park entrance [14,18]
_fb_ew("fb_en1", S1, "n", R, 14.0, C_fb)
_fb_ew("fb_en2", S1, "n", 18.0, R + ARM, C_fb)

# E arm S flower bed — continuous
_fb_ew("fb_es", -S1, "s", R, R + ARM, C_fb)

# W arm N flower bed — continuous
_fb_ew("fb_wn", S1, "n", -(R + ARM), -R, C_fb)
# W arm S flower bed — continuous
_fb_ew("fb_ws", -S1, "s", -(R + ARM), -R, C_fb)

# ═══════════════════════════════════════════════════════════════════════════════
# NORTH ARM — RESIDENTIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════

# ── Bus stop — E sidewalk, opens toward road (west, yaw=-π/2) ────────────────
UA.place_busstop((S1 - SW / 2, 14.0), C_n, yaw=-math.pi / 2, scale=1.5)

# ── Bike station — paved pad just east of E flower bed ───────────────────────
_box("bike_pad", 14.5, 21.0, 0.03, 8.0, 6.5, 0.06, M["stone_path"], C_sw)
UA.place_bicycle_station((14.5, 21.0), C_n, yaw=0)

# ── House A — east side (X>G1), faces road (west, yaw=-π/2) ──────────────────
HA_CX, HA_CY, HA_FW, HA_FD = 24.0, 36.0, 23.0, 14.0
UA.build_house(
    "hA",
    HA_CX,
    HA_CY,
    C_n,
    w=13,
    d=9,
    wall_h=3.4,
    yaw=-math.pi / 2,
    mat_wall=M["wall_beige"],
    mat_roof=M["roof_tile"],
    n_win_front=3,
)
_build_fence("fA", HA_CX, HA_CY, HA_FW, HA_FD, gate_side="w", gate_w=2.4, C=C_n)
# Driveway (flower bed gap + zone entry path)
_box("drv_a_fb", 9.25, HA_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_a_z", 11.5, HA_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

# ── House B — east side, further north ───────────────────────────────────────
HB_CX, HB_CY, HB_FW, HB_FD = 24.0, 50.0, 23.0, 14.0
UA.build_house(
    "hB",
    HB_CX,
    HB_CY,
    C_n,
    w=13,
    d=9,
    wall_h=3.4,
    yaw=-math.pi / 2,
    mat_wall=M["wall_cream"],
    mat_roof=M["roof_flat"],
    n_win_front=3,
)
_build_fence("fB", HB_CX, HB_CY, HB_FW, HB_FD, gate_side="w", gate_w=2.4, C=C_n)
_box("drv_b_fb", 9.25, HB_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_b_z", 11.5, HB_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

# ── House C — west side, faces road (east, yaw=+π/2) ─────────────────────────
HC_CX, HC_CY, HC_FW, HC_FD = -24.0, 38.0, 23.0, 14.0
UA.build_house(
    "hC",
    HC_CX,
    HC_CY,
    C_n,
    w=13,
    d=9,
    wall_h=3.4,
    yaw=math.pi / 2,
    mat_wall=M["wall_blue"],
    mat_roof=M["roof_tile"],
    n_win_front=3,
)
_build_fence("fC", HC_CX, HC_CY, HC_FW, HC_FD, gate_side="e", gate_w=2.4, C=C_n)
_box("drv_c_fb", -9.25, HC_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_c_z", -11.5, HC_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

# ── Yard shrubs inside residential fences ─────────────────────────────────────
for i, (sx, sy, si) in enumerate([(16, 30, 0), (18, 42, 2), (30, 30, 1), (30, 42, 3)]):
    UA.place_shrub_belt2(f"ysh_a{i}", (sx, sy), C_tree, scale=1.5, shrub_idx=si)
for i, (sx, sy, si) in enumerate([(16, 44, 4), (18, 56, 2), (30, 44, 0), (30, 56, 3)]):
    UA.place_shrub_belt2(f"ysh_b{i}", (sx, sy), C_tree, scale=1.5, shrub_idx=si)
for i, (sx, sy, si) in enumerate(
    [(-16, 32, 1), (-30, 32, 3), (-16, 44, 0), (-30, 44, 2)]
):
    UA.place_shrub_belt2(f"ysh_c{i}", (sx, sy), C_tree, scale=1.5, shrub_idx=si)

# ── Street trees (belt2 at scale=3.0) in N arm flower beds ───────────────────
for i, (ty, si) in enumerate([(8, 0), (18, 2), (28, 4), (40, 1), (50, 3)]):
    UA.place_shrub_belt2(f"nt_e{i}", (9.25, ty), C_tree, scale=3.0, shrub_idx=si)
    UA.place_shrub_belt2(
        f"nt_w{i}", (-9.25, ty), C_tree, scale=3.0, shrub_idx=si % 4 + 1
    )

# ── Street lamps on N arm sidewalks ──────────────────────────────────────────
for y in [7, 15, 22, 30, 38, 46, 52]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)

# ── Sidewalk furniture (benches/bins on E sidewalk, phone booth on W) ─────────
for y in [20, 42]:
    UA.place_bench_classic((S1 - SW * 0.8, y), C_furn, yaw=math.pi / 2)
    UA.place_bench_classic((-S1 + SW * 0.8, y), C_furn, yaw=-math.pi / 2)
for y in [28, 48]:
    UA.place_bin_domed((S1 - SW * 0.8, y), C_furn)
    UA.place_bin_domed((-S1 + SW * 0.8, y), C_furn)
# Phone booth on W sidewalk
UA.place_phonebooth((-S1 + SW * 0.6, 18.0), C_furn, yaw=math.pi / 2)

# ═══════════════════════════════════════════════════════════════════════════════
# EAST ARM — PARK ZONE
# ═══════════════════════════════════════════════════════════════════════════════
PARK_X0, PARK_X1 = G1, 54.0
PARK_Y0, PARK_Y1 = G1, 44.5
PARK_CX = (PARK_X0 + PARK_X1) / 2
PARK_CY = (PARK_Y0 + PARK_Y1) / 2

# Park lawn base
_box(
    "park_lawn",
    PARK_CX,
    PARK_CY,
    0.02,
    PARK_X1 - PARK_X0,
    PARK_Y1 - PARK_Y0,
    0.04,
    M["grass_park"],
    C_e,
)

# Also add south park strip (S side of E arm)
SPARKS_Y0, SPARKS_Y1 = -30.0, -G1
_box(
    "park_lawn_s",
    PARK_CX,
    (SPARKS_Y0 + SPARKS_Y1) / 2,
    0.02,
    PARK_X1 - PARK_X0,
    SPARKS_Y1 - SPARKS_Y0,
    0.04,
    M["grass_park"],
    C_e,
)

# ── Park entrance — gap in N flower bed (X=[14,18]) ───────────────────────────
# Gate posts at X=14 and X=18, Y=G1+0.3
_cyl("pk_gp1", 14.0, G1 + 0.3, 0, 0.14, 2.4, M["gate_post"], C_e, verts=8)
_cyl("pk_gp2", 18.0, G1 + 0.3, 0, 0.14, 2.4, M["gate_post"], C_e, verts=8)
# Entry path through flower-bed gap
_box("pk_ep", 16.0, (S1 + G1) / 2, 0.04, 4.2, FW, 0.08, M["stone_path"], C_e)

# ── Internal park path network ────────────────────────────────────────────────
# Main N-S spine (from entrance to north)
_box(
    "ppth_ns",
    16.0,
    (PARK_Y0 + PARK_Y1) / 2,
    0.05,
    2.5,
    PARK_Y1 - PARK_Y0,
    0.10,
    M["stone_path"],
    C_e,
)
# E-W cross-path at Y=28
_box(
    "ppth_ew",
    (PARK_X0 + PARK_X1) / 2,
    28.0,
    0.05,
    PARK_X1 - PARK_X0,
    2.5,
    0.10,
    M["stone_path"],
    C_e,
)
# Secondary E-W path at Y=20
_box("ppth_ew2", (G1 + 38) / 2, 20.0, 0.05, 38 - G1, 2.0, 0.10, M["stone_path"], C_e)

# ── Circular plaza around pavilion ───────────────────────────────────────────
_plaza_circle("pav_plz", 34.0, 30.0, 6.0, C_e)

# ── Import Chinese Pavilion from sculpture blend ──────────────────────────────
pav_objs = UA._import_prefix(SC_BLEND, "pav:", C_e)
if pav_objs:
    UA._place(pav_objs, 34.0, 30.0)
    print(f"[all6] Pavilion imported ({len(pav_objs)} objects)")
else:
    # Procedural fallback hexagonal gazebo
    _cyl("pav_base", 34, 30, 0.0, 4.2, 0.35, M["park_stone"], C_e, verts=6)
    for i in range(6):
        a = i * math.pi / 3
        px, py = 34 + 2.6 * math.cos(a), 30 + 2.6 * math.sin(a)
        _cyl(f"pav_col{i}", px, py, 0.35, 0.18, 3.4, M["park_stone"], C_e, verts=12)
    _cyl("pav_roof", 34, 30, 3.75, 4.0, 0.20, M["roof_tile"], C_e, verts=6)
    bpy.ops.mesh.primitive_cone_add(
        radius1=3.8, radius2=0.20, depth=1.6, location=(34, 30, 4.75)
    )
    _cone = bpy.context.active_object
    _cone.name = "pav_cone"
    _cone.data.materials.append(M["roof_tile"])
    UA.to_coll(_cone, C_e)

# ── Import Victorian Bandstand ────────────────────────────────────────────────
band_objs = UA._import_prefix(SC_BLEND, "band:", C_e)
if band_objs:
    UA._place(band_objs, 20.0, 20.0)
    print(f"[all6] Bandstand imported ({len(band_objs)} objects)")

# ── Corten sculpture at (44, 38) ─────────────────────────────────────────────
_corten_ring("sc1", 44.0, 38.0, 1.6, C_e)

# ── Water feature / fountain at (26, 22) ────────────────────────────────────
_water_feature("wf", 26.0, 22.0, 2.0, C_e)

# ── Park benches ─────────────────────────────────────────────────────────────
for bx, by, byw in [
    (18.5, 26.0, math.pi / 2),
    (26.0, 36.0, 0.0),
    (40.0, 22.0, math.pi / 2),
    (42.0, 38.0, 0.0),
]:
    UA.place_bench_classic((bx, by), C_e, yaw=byw)

# Park bins
for bx, by in [(22.0, 32.0), (38.0, 44.0)]:
    UA.place_bin_domed((bx, by), C_e)

# ── Infinigen trees in park ───────────────────────────────────────────────────
park_tree_positions = [
    (18, 16, 0),
    (26, 43, 1),
    (40, 14, 2),
    (48, 40, 3),
    (32, 44, 4),
    (15, 36, 0),
    (46, 24, 2),
    (50, 14, 1),
]
for i, (tx, ty, ti) in enumerate(park_tree_positions):
    UA.place_infinigen_tree(f"pk_inftr{i}", (tx, ty), C_e, tree_idx=ti, scale=1.0)

# ── Street trees in E arm flower beds ────────────────────────────────────────
for i, (tx, si) in enumerate([(8, 0), (18, 3), (28, 1), (38, 4), (48, 2)]):
    UA.place_shrub_belt2(f"et_n{i}", (tx, 9.25), C_tree, scale=3.0, shrub_idx=si)
    UA.place_shrub_belt2(
        f"et_s{i}", (tx, -9.25), C_tree, scale=3.0, shrub_idx=(si + 2) % 5
    )

# ── Street lamps on E arm sidewalks ──────────────────────────────────────────
# N sidewalk (Y>0): arm must point toward -Y (road) → yaw=π
# S sidewalk (Y<0): arm must point toward +Y (road) → yaw=0
for x in [7, 15, 22, 30, 38, 46, 52]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SOUTH ARM — COMMERCIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════
SHOP_D = 8.0  # shop depth (X direction)
SHOP_H = 4.2  # shop height
SHOP_W = 12.0  # shop width (Y direction)
# East-side shops: front at X = G1 = 10.5, center X = G1 + SHOP_D/2 = 14.5
SH_CX_E = G1 + SHOP_D / 2
SH_CX_W = -G1 - SHOP_D / 2

# Shop A east  (center Y=-16)
_shop_w(
    "shA_e", SH_CX_E, -16.0, SHOP_W, SHOP_D, SHOP_H, M["shop_beige"], M["awning_r"], C_s
)
# Shop B east
_shop_w(
    "shB_e", SH_CX_E, -30.0, SHOP_W, SHOP_D, SHOP_H, M["shop_red"], M["awning_g"], C_s
)
# Shop C east
_shop_w(
    "shC_e", SH_CX_E, -44.0, SHOP_W, SHOP_D, SHOP_H, M["shop_blue"], M["awning_b"], C_s
)

# Shop D west (facing east)
_shop_e(
    "shD_w", SH_CX_W, -16.0, SHOP_W, SHOP_D, SHOP_H, M["shop_beige"], M["awning_y"], C_s
)
# Shop E west
_shop_e(
    "shE_w", SH_CX_W, -30.0, SHOP_W, SHOP_D, SHOP_H, M["shop_red"], M["awning_r"], C_s
)

# ── Kiosk on E sidewalk ──────────────────────────────────────────────────────
UA.place_kiosk5((S1 - SW / 2, -24.0), C_s, yaw=-math.pi / 2, scale=0.9)

# ── Phone booth on E sidewalk ────────────────────────────────────────────────
UA.place_phonebooth((S1 - SW * 0.6, -38.0), C_s, yaw=-math.pi / 2)

# ── Street furniture on S arm sidewalks ──────────────────────────────────────
for y in [-20.0, -36.0, -50.0]:
    UA.place_bench_classic((S1 - SW * 0.8, y), C_furn, yaw=math.pi / 2)
for y in [-26.0, -44.0]:
    UA.place_bench_classic((-S1 + SW * 0.8, y), C_furn, yaw=-math.pi / 2)
for y in [-22.0, -42.0]:
    UA.place_bin_domed((S1 - SW * 0.8, y), C_furn)
UA.place_bin_domed((-S1 + SW * 0.8, -30.0), C_furn)

# ── Street trees in S arm flower beds ────────────────────────────────────────
for i, (ty, si) in enumerate([(-8, 1), (-20, 3), (-34, 0), (-46, 2), (-52, 4)]):
    UA.place_shrub_belt2(f"st_e{i}", (9.25, ty), C_tree, scale=3.0, shrub_idx=si)
    UA.place_shrub_belt2(
        f"st_w{i}", (-9.25, ty), C_tree, scale=3.0, shrub_idx=(si + 1) % 5
    )

# ── Street lamps on S arm sidewalks ──────────────────────────────────────────
for y in [-7, -15, -22, -30, -38, -46, -52]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)

# ═══════════════════════════════════════════════════════════════════════════════
# WEST ARM — GREEN BELT
# ═══════════════════════════════════════════════════════════════════════════════
# Belt lawn beyond flower beds (N and S of W arm road)
_WLCX = -(R + ARM / 2)  # -29.5, centre of west arm
_box("wst_lawn_n", _WLCX, 28.0, 0.02, ARM, 36.0, 0.04, M["grass_park"], C_w)
_box("wst_lawn_s", _WLCX, -28.0, 0.02, ARM, 36.0, 0.04, M["grass_park"], C_w)

# Street trees in W arm flower beds
for i, (tx, si) in enumerate([(-8, 2), (-18, 4), (-28, 1), (-38, 3), (-48, 0)]):
    UA.place_shrub_belt2(f"wt_n{i}", (tx, 9.25), C_tree, scale=3.0, shrub_idx=si)
    UA.place_shrub_belt2(
        f"wt_s{i}", (tx, -9.25), C_tree, scale=3.0, shrub_idx=(si + 2) % 5
    )

# A few benches and bins in W arm sidewalks
for y in [0.0]:
    UA.place_bench_classic((-15.0, S1 - SW * 0.8), C_furn, yaw=0)
    UA.place_bench_classic((-28.0, -S1 + SW * 0.8), C_furn, yaw=0)

# Street lamps on W arm (same yaw logic as E arm)
for x in [-7, -15, -22, -30, -38, -46, -52]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)

# ═══════════════════════════════════════════════════════════════════════════════
# VEHICLES (on road lanes only)
# ═══════════════════════════════════════════════════════════════════════════════
# N arm — northbound (X=+LC) and southbound (X=-LC)
UA.build_car("vn1", 2.25, 20.0, C_cars, yaw=0, mat_body=M["car_paint"])
UA.build_car("vn2", 2.25, 35.0, C_cars, yaw=0, mat_body=M["car_paint2"])
UA.build_car("vn3", -2.25, 28.0, C_cars, yaw=math.pi, mat_body=M["car_paint"])
# S arm — southbound (X=+LC) and northbound (X=-LC)
UA.build_car("vs1", 2.25, -22.0, C_cars, yaw=math.pi, mat_body=M["car_paint2"])
UA.build_car("vs2", -2.25, -18.0, C_cars, yaw=0, mat_body=M["car_paint"])
# E arm — eastbound (Y=-LC) and westbound (Y=+LC)
UA.build_car("ve1", 22.0, -2.25, C_cars, yaw=-math.pi / 2, mat_body=M["car_paint"])
UA.build_car("ve2", 36.0, -2.25, C_cars, yaw=-math.pi / 2, mat_body=M["car_paint2"])
UA.build_car("ve3", 18.0, 2.25, C_cars, yaw=math.pi / 2, mat_body=M["car_paint"])
# W arm — westbound (Y=+LC) and eastbound (Y=-LC)
UA.build_car("vw1", -24.0, 2.25, C_cars, yaw=math.pi / 2, mat_body=M["car_paint2"])
UA.build_car("vw2", -38.0, -2.25, C_cars, yaw=-math.pi / 2, mat_body=M["car_paint"])

# ═══════════════════════════════════════════════════════════════════════════════
# LIGHTING — Nishita sky + warm sun
# ═══════════════════════════════════════════════════════════════════════════════
bpy.context.scene.world = bpy.data.worlds.new("sky")
bpy.context.scene.world.use_nodes = True
wt = bpy.context.scene.world.node_tree
wt.nodes.clear()

bg = wt.nodes.new("ShaderNodeBackground")
sky = wt.nodes.new("ShaderNodeTexSky")
lp = wt.nodes.new("ShaderNodeLightPath")
mix = wt.nodes.new("ShaderNodeMixShader")
bg2 = wt.nodes.new("ShaderNodeBackground")
out = wt.nodes.new("ShaderNodeOutputWorld")

sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(42)
sky.sun_rotation = math.radians(215)
sky.altitude = 1000.0
sky.air_density = 1.0
sky.dust_density = 0.5

bg.inputs["Strength"].default_value = 1.0
bg2.inputs[
    "Strength"
].default_value = 0.0  # camera rays → black bg (shows sky in viewport only)

wt.links.new(sky.outputs["Color"], bg.inputs["Color"])
wt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wt.links.new(bg.outputs["Background"], mix.inputs[1])
wt.links.new(bg2.outputs["Background"], mix.inputs[2])
wt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

# Sun lamp
bpy.ops.object.light_add(type="SUN", location=(20, -40, 60))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 5.0
sun.data.angle = math.radians(0.5)
sun.rotation_euler[0] = math.radians(48)
sun.rotation_euler[2] = math.radians(215)

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.cycles.samples = 256
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPTIX"
sc.cycles.device = "GPU"

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
except Exception as e:
    print(f"[all6] GPU setup note: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# CAMERAS
# ═══════════════════════════════════════════════════════════════════════════════
def make_camera(name, loc, target, fov_deg=58):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.name = name
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov_deg)
    # Point camera at target (camera looks in -Z, up is +Y)
    dir_vec = Vector(target) - Vector(loc)
    if dir_vec.length > 0:
        rot_q = dir_vec.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_q.to_euler()
    return cam


# Camera 1 — Overview (near-BEV, high angle)
cam_ov = make_camera("cam_overview", loc=(0, -80, 110), target=(0, 12, 0), fov_deg=62)
# Camera 2 — Residential street view (N arm)
cam_rs = make_camera("cam_residential", loc=(-18, 8, 14), target=(2, 38, 0), fov_deg=60)
# Camera 3 — Park view (E arm)
cam_pk = make_camera("cam_park", loc=(-12, 36, 22), target=(34, 28, 2), fov_deg=62)
# Camera 4 — Commercial street view (S arm)
cam_cm = make_camera(
    "cam_commercial", loc=(-18, -8, 14), target=(2, -32, 0), fov_deg=60
)
# Camera 5 — Intersection close-up
cam_ix = make_camera(
    "cam_intersection", loc=(-22, -22, 20), target=(0, 0, 0), fov_deg=58
)

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE BLEND FILE
# ═══════════════════════════════════════════════════════════════════════════════
blend_path = str(OUT / "urban_v3_all6.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[all6] Blend saved: {blend_path}")

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER ALL 5 CAMERAS
# ═══════════════════════════════════════════════════════════════════════════════
cameras = [
    (cam_ov, "overview.png"),
    (cam_rs, "residential.png"),
    (cam_pk, "park.png"),
    (cam_cm, "commercial.png"),
    (cam_ix, "intersection.png"),
]

for cam, fname in cameras:
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all6] Rendering {fname} ...")
    bpy.ops.render.render(write_still=True)
    print(f"[all6] Done: {fname}")

print("[all6] All renders complete.")
