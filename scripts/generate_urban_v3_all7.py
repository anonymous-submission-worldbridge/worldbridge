"""
generate_urban_v3_all7.py
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

All writes to urban_v3_all7 only; does not touch urban_v3_all6.
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
sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
import bpy
from pathlib import Path
from mathutils import Vector, Matrix
import urban_assets as UA
import generate_urban_v3_busstop as BUS
import generate_urban_v3_sharedbicycle4 as BIKE
import generate_urban_v3_kiosk5 as KIOSK
import generate_urban_v3_bench_trashbin2 as FURN
import generate_urban_v3_trafficlight3 as TL3
import generate_urban_v3_sculpture as ART

_USE_TREEFACTORY = "--real-treefactory" in sys.argv
try:
    if _USE_TREEFACTORY:
        import gin

        gin.clear_config()
        from infinigen.assets.objects.trees.generate import TreeFactory

        _TREE_IMPORT_ERROR = None
    else:
        TreeFactory = None
        _TREE_IMPORT_ERROR = "TreeFactory disabled for fast all7 generation; pass --real-treefactory to enable"
except Exception as exc:
    TreeFactory = None
    _TREE_IMPORT_ERROR = repr(exc)

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all7")
OUT.mkdir(parents=True, exist_ok=True)

VEHICLE_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_vehicle/openx_preview.blend"
)

UA.reset_scene()
UA.build_all_materials()
BUS.build_materials()
BIKE.build_materials()
KIOSK.build_materials()
FURN.build_materials()
TL3.build_materials()
ART.build_materials()
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


def _log(msg):
    print(f"[v7] {msg}", flush=True)


_log("materials and collections ready")
# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────


def _bbox_world(objs):
    xs, ys, zs = [], [], []
    for obj in objs:
        if not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            v = obj.matrix_world @ Vector(corner)
            xs.append(v.x)
            ys.append(v.y)
            zs.append(v.z)
    if not xs:
        return (0, 0, 0, 0, 0, 0)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _generated_at(
    tag, target_coll, builder, tx, ty, tz=0.0, yaw=0.0, sx=1.0, sy=1.0, sz=1.0
):
    """Run a procedural asset builder, then fit the generated objects into this scene."""
    before = {obj.name for obj in bpy.data.objects}
    builder()
    new_objs = [obj for obj in bpy.data.objects if obj.name not in before]
    if not new_objs:
        return []
    x0, x1, y0, y1, z0, _ = _bbox_world(new_objs)
    center = Vector(((x0 + x1) / 2.0, (y0 + y1) / 2.0, z0))
    mat = (
        Matrix.Translation(Vector((tx, ty, tz)))
        @ Matrix.Rotation(yaw, 4, "Z")
        @ Matrix.Diagonal((sx, sy, sz, 1.0))
        @ Matrix.Translation(-center)
    )
    new_set = set(new_objs)
    for obj in new_objs:
        obj.name = f"{tag}:{obj.name}"
        if target_coll and obj.name not in target_coll.objects.keys():
            try:
                target_coll.objects.link(obj)
            except RuntimeError:
                pass
        if obj.parent not in new_set:
            obj.matrix_world = mat @ obj.matrix_world
    return new_objs


def _gen_bus_stop(tag, at, C, yaw=-math.pi / 2, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: (BUS.build_shelter(C),),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _build_light_shared_bike(prefix, x, y, C, yaw_deg=-90):
    mats = getattr(BIKE, "MATS", {})
    frame = mats.get("frame") or M["awning_g"]
    dark = mats.get("steel_dark") or M["car_tire"]
    alu = mats.get("alu") or M["car_chrome"]
    lock = mats.get("lock") or M["fence_iron"]
    tyre = mats.get("tyre") or M["car_tire"]

    root = bpy.data.objects.new(f"{prefix}:root", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = (x, y, 0.0)
    root.rotation_euler.z = math.radians(yaw_deg)
    made = [root]

    def parent(obj):
        obj.parent = root
        made.append(obj)
        return obj

    def tube(name, a, b, r, mat, verts=12):
        return parent(_cyl_between(f"{prefix}:{name}", a, b, r, mat, C, verts=verts))

    rear = (-0.58, 0.0, 0.38)
    front = (0.58, 0.0, 0.38)
    for label, center in (("rear", rear), ("front", front)):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.32,
            minor_radius=0.025,
            major_segments=42,
            minor_segments=8,
            location=center,
            rotation=(math.pi / 2, 0, 0),
        )
        wh = bpy.context.active_object
        wh.name = f"{prefix}:{label}_tyre"
        wh.data.materials.append(tyre)
        UA.to_coll(wh, C)
        parent(wh)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.25,
            minor_radius=0.007,
            major_segments=36,
            minor_segments=6,
            location=center,
            rotation=(math.pi / 2, 0, 0),
        )
        rim = bpy.context.active_object
        rim.name = f"{prefix}:{label}_rim"
        rim.data.materials.append(alu)
        UA.to_coll(rim, C)
        parent(rim)
        for s in range(8):
            a = math.tau * s / 8.0
            rim_pt = (
                center[0] + math.cos(a) * 0.25,
                center[1],
                center[2] + math.sin(a) * 0.25,
            )
            tube(f"{label}_spoke{s}", center, rim_pt, 0.004, alu, verts=5)

    bb = (-0.05, 0.0, 0.46)
    seat = (-0.25, 0.0, 1.03)
    head = (0.42, 0.0, 0.98)
    tube("down_tube", head, bb, 0.026, frame)
    tube("seat_tube", bb, seat, 0.024, frame)
    tube("top_tube", seat, head, 0.022, frame)
    tube("chain_stay", bb, rear, 0.018, frame)
    tube("seat_stay", seat, rear, 0.016, frame)
    tube("fork_l", head, front, 0.016, dark)
    tube("fork_r", (head[0], -0.08, head[2]), (front[0], -0.08, front[2]), 0.014, dark)
    tube("handle_stem", head, (0.30, 0.0, 1.22), 0.018, dark)
    tube("handlebar", (0.30, -0.28, 1.22), (0.30, 0.28, 1.22), 0.014, dark)
    tube("seatpost", seat, (-0.28, 0.0, 1.18), 0.016, dark)

    saddle = UA._box(
        f"{prefix}:saddle", -0.32, 0.0, 1.20, 0.30, 0.20, 0.055, lock, C, bev=0.025
    )
    parent(saddle)
    basket = UA._box(
        f"{prefix}:basket", 0.70, 0.0, 0.88, 0.34, 0.30, 0.20, frame, C, bev=0.012
    )
    parent(basket)
    panel = UA._box(
        f"{prefix}:solar_lock", -0.52, 0.0, 0.76, 0.26, 0.16, 0.10, lock, C, bev=0.012
    )
    parent(panel)
    guard = UA._box(
        f"{prefix}:chainguard",
        -0.16,
        0.08,
        0.46,
        0.42,
        0.035,
        0.20,
        frame,
        C,
        bev=0.018,
    )
    parent(guard)
    return made


def _gen_bike_station(tag, at, C, yaw=0.0, scale=1.0):
    def build():
        BIKE.build_station(C)
        for i, x in enumerate(BIKE.BIKE_X[:3]):
            _build_light_shared_bike(f"bike{i}", x, BIKE.BIKE_CENTER_Y, C, BIKE.YAWS[i])

    return _generated_at(tag, C, build, at[0], at[1], 0.0, yaw, scale, scale, scale)


def _gen_kiosk_pair(tag, at, C, yaw=-math.pi / 2, scale=1.0):
    def build():
        KIOSK.build_kiosk_mcd(C, cx=0.0)

    return _generated_at(tag, C, build, at[0], at[1], 0.0, yaw, scale, scale, scale)


def _gen_bench(tag, at, C, yaw=0.0, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: FURN.bench_classic(0.0, 0.0, C),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _gen_bin(tag, at, C, yaw=0.0, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: FURN.bin_domed(0.0, 0.0, C),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _gen_traffic(tag, at, C, yaw=0.0, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: TL3.build_horizontal_gantry(tag, (0.0, 0.0), C),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _gen_pavilion(tag, at, C, yaw=0.0, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: ART.build_chinese_pavilion(0.0, 0.0, C),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _gen_bandstand(tag, at, C, yaw=0.0, scale=1.0):
    return _generated_at(
        tag,
        C,
        lambda: ART.build_bandstand(0.0, 0.0, C),
        at[0],
        at[1],
        0.0,
        yaw,
        scale,
        scale,
        scale,
    )


def _build_phonebooth(tag, cx, cy, C, yaw=0.0, scale=1.0):
    red = UA._pbr(f"{tag}:k6_red", (0.62, 0.02, 0.018), rough=0.38, metal=0.0)
    dark = UA._pbr(f"{tag}:dark_metal", (0.035, 0.03, 0.028), rough=0.45, metal=0.6)
    sign = UA._pbr(
        f"{tag}:sign_lit",
        (0.95, 0.88, 0.72),
        rough=0.35,
        emit=(1.0, 0.86, 0.55),
        emit_str=1.2,
    )
    glass = M["window"]
    parts = []

    def bx(name, lx, ly, lz, dx, dy, dz, mat, bev=0.01):
        o = UA._box(
            f"{tag}:{name}",
            lx,
            ly,
            lz,
            dx * scale,
            dy * scale,
            dz * scale,
            mat,
            C,
            bev=bev * scale,
        )
        parts.append(o)
        return o

    # Built around origin, front faces -Y, then transformed to scene.
    bx("base", 0, 0, 0.08 * scale, 1.12, 1.12, 0.16, dark, 0.025)
    bx("floor", 0, 0, 0.18 * scale, 0.96, 0.96, 0.08, red, 0.015)
    for x in (-0.48, 0.48):
        for y in (-0.48, 0.48):
            bx(
                f"post_{x}_{y}",
                x * scale,
                y * scale,
                1.18 * scale,
                0.10,
                0.10,
                2.0,
                red,
                0.018,
            )
    for z in (0.70, 1.20, 1.70):
        bx(f"rail_front_{z}", 0, -0.50 * scale, z * scale, 0.96, 0.08, 0.07, red, 0.012)
        bx(f"rail_back_{z}", 0, 0.50 * scale, z * scale, 0.96, 0.08, 0.07, red, 0.012)
        bx(f"rail_left_{z}", -0.50 * scale, 0, z * scale, 0.08, 0.96, 0.07, red, 0.012)
        bx(f"rail_right_{z}", 0.50 * scale, 0, z * scale, 0.08, 0.96, 0.07, red, 0.012)
    for x in (-0.24, 0.24):
        bx(
            f"glass_front_{x}",
            x * scale,
            -0.515 * scale,
            1.25 * scale,
            0.30,
            0.025,
            0.86,
            glass,
            0.004,
        )
        bx(
            f"glass_back_{x}",
            x * scale,
            0.515 * scale,
            1.25 * scale,
            0.30,
            0.025,
            0.86,
            glass,
            0.004,
        )
    for y in (-0.24, 0.24):
        bx(
            f"glass_left_{y}",
            -0.515 * scale,
            y * scale,
            1.25 * scale,
            0.025,
            0.30,
            0.86,
            glass,
            0.004,
        )
        bx(
            f"glass_right_{y}",
            0.515 * scale,
            y * scale,
            1.25 * scale,
            0.025,
            0.30,
            0.86,
            glass,
            0.004,
        )
    bx("sign_front", 0, -0.535 * scale, 2.16 * scale, 0.78, 0.035, 0.20, sign, 0.006)
    bx("sign_back", 0, 0.535 * scale, 2.16 * scale, 0.78, 0.035, 0.20, sign, 0.006)
    bx("roof", 0, 0, 2.35 * scale, 1.08, 1.08, 0.18, red, 0.035)
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=12, radius=0.58 * scale, location=(0, 0, 2.42 * scale)
    )
    dome = bpy.context.active_object
    dome.name = f"{tag}:dome"
    dome.scale.z = 0.22
    dome.data.materials.append(red)
    UA.to_coll(dome, C)
    parts.append(dome)
    bx("phone_box", 0.0, 0.34 * scale, 1.10 * scale, 0.36, 0.08, 0.42, dark, 0.01)
    bx(
        "handset",
        -0.14 * scale,
        0.285 * scale,
        1.10 * scale,
        0.07,
        0.045,
        0.32,
        dark,
        0.02,
    )

    mat = Matrix.Translation(Vector((cx, cy, 0))) @ Matrix.Rotation(yaw, 4, "Z")
    for obj in parts:
        obj.matrix_world = mat @ obj.matrix_world
    return parts


def _proc_shrub_belt2(tag, at, C, scale=1.0, shrub_idx=0, yaw=0.0):
    """Low planting used inside curb flower beds and yards."""
    x, y = at
    trunk_h = 0.55 * scale
    crown_r = 0.38 * scale
    UA._cyl(
        f"{tag}:stem", x, y, 0.02, 0.035 * scale, trunk_h, M["tree_trunk"], C, verts=8
    )
    palette_offsets = [
        (0.0, 0.0, 0.00, 1.00),
        (0.25, 0.08, 0.07, 0.72),
        (-0.22, 0.05, 0.05, 0.68),
        (0.02, -0.24, 0.04, 0.70),
    ]
    for i, (ox, oy, oz, sr) in enumerate(palette_offsets):
        o = UA._sph(
            f"{tag}:leaf{i}",
            x + ox * scale,
            y + oy * scale,
            0.34 * scale + trunk_h + oz * scale,
            crown_r * sr,
            M["tree_leaf"],
            C,
            segs=14,
            rings=8,
        )
        o.rotation_euler.z = yaw
    return []


_TREE_PROTOS = {}
_TREE_PROTO_COLL = None


def _tree_children(root):
    out = [root]
    for child in root.children:
        out.extend(_tree_children(child))
    return out


def _hide_tree_recursive(obj, hidden=True):
    obj.hide_viewport = hidden
    obj.hide_render = hidden
    for child in obj.children:
        _hide_tree_recursive(child, hidden)


def _tree_proto_coll():
    global _TREE_PROTO_COLL
    if _TREE_PROTO_COLL is None:
        _TREE_PROTO_COLL = UA.new_coll("TreePrototypes_Procedural")
    return _TREE_PROTO_COLL


def _make_tree_proto(variant, seed):
    if TreeFactory is None:
        raise RuntimeError(_TREE_IMPORT_ERROR or "TreeFactory unavailable")
    old_leaf, old_twig = TreeFactory.n_leaf, TreeFactory.n_twig
    TreeFactory.n_leaf = 4
    TreeFactory.n_twig = 1
    try:
        root = TreeFactory(
            seed=seed, season="summer", coarse=False, fruit_chance=0.0
        ).spawn_asset(
            int(seed % 100000),
            loc=(-760.0 - variant * 24.0, -760.0, 0.0),
            rot=(0.0, 0.0, 0.0),
            distance=32,
            vis_distance=32,
        )
    finally:
        TreeFactory.n_leaf, TreeFactory.n_twig = old_leaf, old_twig
    root.name = f"v7_tree_proto_{variant}:{root.name}"
    proto_coll = _tree_proto_coll()
    for obj in _tree_children(root):
        if obj.name not in proto_coll.objects.keys():
            try:
                proto_coll.objects.link(obj)
            except RuntimeError:
                pass
    _hide_tree_recursive(root, True)
    return root


def _clone_tree_recursive(src, parent, tag, C):
    clone = src.copy()
    if src.data:
        clone.data = src.data
    clone.name = f"{tag}:{src.name}"
    C.objects.link(clone)
    clone.parent = parent
    clone.matrix_local = src.matrix_local.copy()
    clone.hide_viewport = False
    clone.hide_render = False
    for child in src.children:
        _clone_tree_recursive(child, clone, tag, C)
    return clone


def _cyl_between(name, a, b, radius, mat, C, verts=12):
    a = Vector(a)
    b = Vector(b)
    mid = (a + b) * 0.5
    length = (b - a).length
    if length <= 0:
        return None
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=length, location=mid
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    if mat:
        obj.data.materials.append(mat)
    UA.to_coll(obj, C)
    return obj


def _fallback_broadleaf_tree(tag, at, C, scale=1.0, tree_idx=0, yaw=0.0):
    """Procedural fallback if Infinigen TreeFactory is unavailable."""
    x, y = at
    rnd = _rng.Random(9301 + tree_idx * 41)
    trunk_h = 3.8 * scale * rnd.uniform(0.92, 1.10)
    trunk_r = 0.18 * scale
    UA._cyl(f"{tag}:trunk", x, y, 0.0, trunk_r, trunk_h, M["tree_trunk"], C, verts=18)
    for i in range(7):
        ang = yaw + i * (math.tau / 7.0) + rnd.uniform(-0.18, 0.18)
        z0 = trunk_h * rnd.uniform(0.45, 0.78)
        length = scale * rnd.uniform(1.0, 1.9)
        end = (
            x + math.cos(ang) * length,
            y + math.sin(ang) * length,
            z0 + scale * rnd.uniform(0.35, 0.95),
        )
        _cyl_between(
            f"{tag}:branch{i}",
            (x, y, z0),
            end,
            trunk_r * rnd.uniform(0.25, 0.42),
            M["tree_trunk"],
            C,
            verts=10,
        )
    for i in range(10):
        ang = yaw + rnd.uniform(0, math.tau)
        rad = scale * rnd.uniform(0.0, 1.45)
        z = trunk_h + scale * rnd.uniform(0.3, 2.0)
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=24,
            ring_count=14,
            radius=scale * rnd.uniform(0.9, 1.45),
            location=(x + math.cos(ang) * rad, y + math.sin(ang) * rad, z),
        )
        leaf = bpy.context.active_object
        leaf.name = f"{tag}:leaf{i}"
        leaf.scale.x *= rnd.uniform(1.0, 1.55)
        leaf.scale.y *= rnd.uniform(0.8, 1.25)
        leaf.scale.z *= rnd.uniform(0.55, 0.9)
        leaf.rotation_euler.z = rnd.uniform(0, math.tau)
        leaf.data.materials.append(M["tree_leaf"])
        UA.to_coll(leaf, C)
    return []


def _place_real_tree(tag, at, C, scale=1.0, tree_idx=0, yaw=0.0):
    if not _USE_TREEFACTORY:
        return _fallback_broadleaf_tree(
            tag, at, C, scale=scale, tree_idx=tree_idx, yaw=yaw
        )
    seed = [42, 137, 256, 381, 512][tree_idx % 5]
    try:
        proto = _TREE_PROTOS.get(tree_idx % 5)
        if proto is None:
            proto = _make_tree_proto(tree_idx % 5, seed)
            _TREE_PROTOS[tree_idx % 5] = proto
        root = _clone_tree_recursive(proto, None, tag, C)
        root.location = (at[0], at[1], 0.0)
        root.rotation_euler.z = yaw
        root.scale = (scale, scale, scale)
        return [root]
    except Exception as exc:
        print(
            f"[v7] TreeFactory tree failed for {tag}: {exc!r}; using procedural fallback"
        )
        return _fallback_broadleaf_tree(
            tag, at, C, scale=scale, tree_idx=tree_idx, yaw=yaw
        )


def _place_plant(tag, at, C, scale=1.0, shrub_idx=0, yaw=0.0):
    if scale >= 2.5:
        return _place_real_tree(
            tag, at, C, scale=0.62 + (scale - 2.5) * 0.12, tree_idx=shrub_idx, yaw=yaw
        )
    return _proc_shrub_belt2(tag, at, C, scale=scale, shrub_idx=shrub_idx, yaw=yaw)


# Keep old call sites readable, but route them to in-scene procedural generation.
UA.place_shrub_belt2 = _place_plant


def _proc_streetlight(at, C, yaw=math.pi / 2, day=True):
    x, y = at
    pole = UA._pbr("v7_lamp_galv", (0.38, 0.39, 0.40), rough=0.32, metal=0.9)
    head = UA._pbr("v7_lamp_head", (0.08, 0.08, 0.085), rough=0.38, metal=0.8)
    glow = UA._pbr(
        "v7_lamp_glow",
        (0.95, 0.88, 0.68),
        rough=0.22,
        emit=(0.95, 0.82, 0.55),
        emit_str=0.0 if day else 4.0,
    )
    arm_len = 1.35
    h = 4.2
    UA._cyl("streetlight:pole", x, y, 0.0, 0.055, h, pole, C, verts=18)
    dx = -math.sin(yaw) * arm_len
    dy = math.cos(yaw) * arm_len
    start = Vector((x, y, h))
    end = Vector((x + dx, y + dy, h + 0.18))
    mid = (start + end) * 0.5
    length = (end - start).length
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=14, radius=0.035, depth=length, location=mid
    )
    arm = bpy.context.active_object
    arm.name = "streetlight:arm"
    arm.rotation_euler = (end - start).to_track_quat("Z", "Y").to_euler()
    arm.data.materials.append(pole)
    UA.to_coll(arm, C)
    lamp = UA._box(
        "streetlight:head",
        end.x,
        end.y,
        end.z - 0.08,
        0.52,
        0.22,
        0.13,
        head,
        C,
        bev=0.035,
        rz=yaw,
    )
    lens = UA._box(
        "streetlight:lens",
        end.x,
        end.y,
        end.z - 0.16,
        0.42,
        0.16,
        0.035,
        glow,
        C,
        bev=0.02,
        rz=yaw,
    )
    return [lamp, lens]


UA.place_streetlight = _proc_streetlight


def _asset_belt_ns(tag, x_inner, side, y0, y1, C):
    if y1 <= y0:
        return
    cx = x_inner + (FW / 2.0 if side == "e" else -FW / 2.0)
    cy = (y0 + y1) / 2.0
    dy = y1 - y0
    UA._box(f"{tag}:soil", cx, cy, 0.04, FW, dy, 0.08, M["soil"], C, bev=0.02)
    UA._box(
        f"{tag}:grass", cx, cy, 0.09, FW - 0.22, dy - 0.22, 0.035, M["grass_lush"], C
    )
    UA._box(
        f"{tag}:curb_w", cx - FW / 2, cy, 0.12, 0.16, dy, 0.18, M["curb"], C, bev=0.015
    )
    UA._box(
        f"{tag}:curb_e", cx + FW / 2, cy, 0.12, 0.16, dy, 0.18, M["curb"], C, bev=0.015
    )
    count = max(1, int(dy / 6.0))
    for k in range(count):
        yy = y0 + (k + 0.5) * dy / count
        UA.place_shrub_belt2(
            f"{tag}:shrub{k}",
            (cx + (0.35 if k % 2 else -0.35), yy),
            C_tree,
            scale=1.1,
            shrub_idx=k,
        )
        if k % 2 == 0:
            UA.build_flowerbed(
                f"{tag}:flower{k}",
                cx + 0.45,
                yy,
                C,
                w=0.75,
                d=0.46,
                n_flowers=4,
                seed=k,
            )


def _asset_belt_ew(tag, y_inner, side, x0, x1, C):
    if x1 <= x0:
        return
    cx = (x0 + x1) / 2.0
    cy = y_inner + (FW / 2.0 if side == "n" else -FW / 2.0)
    dx = x1 - x0
    UA._box(f"{tag}:soil", cx, cy, 0.04, dx, FW, 0.08, M["soil"], C, bev=0.02)
    UA._box(
        f"{tag}:grass", cx, cy, 0.09, dx - 0.22, FW - 0.22, 0.035, M["grass_lush"], C
    )
    UA._box(
        f"{tag}:curb_s", cx, cy - FW / 2, 0.12, dx, 0.16, 0.18, M["curb"], C, bev=0.015
    )
    UA._box(
        f"{tag}:curb_n", cx, cy + FW / 2, 0.12, dx, 0.16, 0.18, M["curb"], C, bev=0.015
    )
    count = max(1, int(dx / 6.0))
    for k in range(count):
        xx = x0 + (k + 0.5) * dx / count
        UA.place_shrub_belt2(
            f"{tag}:shrub{k}",
            (xx, cy + (0.35 if k % 2 else -0.35)),
            C_tree,
            scale=1.1,
            shrub_idx=k,
        )
        if k % 2 == 0:
            UA.build_flowerbed(
                f"{tag}:flower{k}",
                xx,
                cy + 0.45,
                C,
                w=0.75,
                d=0.46,
                n_flowers=4,
                seed=k,
            )


def _place_lawn_patch(tag, cx, cy, dx, dy, C, yaw=0.0):
    base = UA._box(f"{tag}:base", cx, cy, 0.025, dx, dy, 0.05, M["grass_lush"], C)
    base.rotation_euler.z = yaw
    ps = base.modifiers.new(f"{tag}:grass_hair", "PARTICLE_SYSTEM")
    settings = ps.particle_system.settings
    settings.type = "HAIR"
    settings.count = min(1000, max(250, int(dx * dy * 1.1)))
    settings.hair_length = 0.18
    settings.use_advanced_hair = True
    settings.render_type = "PATH"
    settings.use_modifier_stack = True
    settings.display_percentage = 45
    settings.roughness_1_size = 0.025
    settings.roughness_1 = 0.006
    settings.roughness_2 = 0.004
    settings.child_type = "INTERPOLATED"
    settings.rendered_child_count = 2
    settings.child_percent = 18
    n = max(8, int(dx * dy * 0.025))
    _rng.seed(int(cx * 101 + cy * 131 + dx * 17 + dy * 19))
    for i in range(n):
        lx = _rng.uniform(-dx / 2 + 0.35, dx / 2 - 0.35)
        ly = _rng.uniform(-dy / 2 + 0.35, dy / 2 - 0.35)
        x = cx + math.cos(yaw) * lx - math.sin(yaw) * ly
        y = cy + math.sin(yaw) * lx + math.cos(yaw) * ly
        UA._cyl(
            f"{tag}:grass_clump{i}",
            x,
            y,
            0.065,
            _rng.uniform(0.035, 0.075),
            _rng.uniform(0.12, 0.28),
            M["flower_leaf"],
            C,
            verts=5,
        )
    return [base]


def _place_clean_vehicle(tag, at, C, yaw=0.0):
    with bpy.data.libraries.load(str(VEHICLE_BLEND), link=False) as (src, dst):
        dst.objects = [
            n
            for n in src.objects
            if n not in {"CameraTarget", "KeyLight", "OrbitCamera", "ground_plane"}
        ]
    objs, root = [], None
    for obj in dst.objects:
        if obj is None:
            continue
        try:
            C.objects.link(obj)
        except RuntimeError:
            pass
        objs.append(obj)
        if obj.name == "Grp_Root" and obj.parent is None:
            root = obj
    for obj in objs:
        obj.name = f"{tag}:{obj.name}"
    if root is None:
        root = next(
            (obj for obj in objs if obj.parent is None and obj.type == "EMPTY"), None
        )
    if root:
        root.location.x = at[0]
        root.location.y = at[1]
        root.location.z = 0.0
        root.rotation_euler.z = yaw
    return objs


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
    _asset_belt_ns(tag, x_inner, side, y0, y1, C)


def _fb_ew(tag, y_inner, side, x0, x1, C):
    """E-W flower-bed segment from x0 to x1. side='n': grows north, 's': grows south."""
    _asset_belt_ew(tag, y_inner, side, x0, x1, C)


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
_log("building ground and roads")
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
_log("building traffic lights")
_gen_traffic("tl_s", (0.0, -(R + 2.5)), C_tl, yaw=0, scale=1.0)  # S gantry
_gen_traffic("tl_n", (0.0, (R + 2.5)), C_tl, yaw=math.pi, scale=1.0)  # N gantry
_gen_traffic("tl_w", (-(R + 2.5), 0.0), C_tl, yaw=-math.pi / 2, scale=1.0)  # W gantry
_gen_traffic("tl_e", ((R + 2.5), 0.0), C_tl, yaw=math.pi / 2, scale=1.0)  # E gantry

# ─── CURB FLOWER BEDS — segmented with openings at key access points ──────────
_log("building curb flower beds")
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
_log("building residential zone")

# Bus stop — N arm east sidewalk at (5.5, 20), opens toward road (west = -X)
_log("residential: bus stop")
_gen_bus_stop("busstop_main", (5.5, 20.0), C_n, yaw=-math.pi / 2, scale=1.25)

# Bike station — parallel to N-S road (yaw=0 = bikes run in Y = parallel to road)
# Placed just outside flower bed at X=10.8, with small paved pad
_log("residential: bike station")
UA._box("bike_pad", 11.0, 14.0, 0.03, 3.5, 8.5, 0.06, M["stone_path"], C_sw)
_gen_bike_station("bike_station_main", (11.0, 14.0), C_n, yaw=0, scale=0.95)

# ── House A — east side, faces road (west = −X), at (18, 28) ─────────────────
_log("residential: houses and yards")
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
_place_lawn_patch("yard_lawn_a", A_CX, A_CY, 14.8, 12.6, C_n)
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
_place_lawn_patch("yard_lawn_b", B_CX, B_CY, 14.8, 12.6, C_n)
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
_place_lawn_patch("yard_lawn_c", C_CX, C_CY, 14.8, 12.6, C_n)
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
_log("residential: trees and furniture")
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
for i, y in enumerate([10, 24, 38]):
    _gen_bench(
        f"bench_n{i}", (S1 - SW / 2 + 0.3, y), C_furn, yaw=math.pi / 2, scale=0.9
    )
for i, y in enumerate([18, 30]):
    _gen_bin(f"bin_n{i}", (S1 - SW / 2 + 0.3, y), C_furn, scale=0.9)

# ═══════════════════════════════════════════════════════════════════════════════
# EAST ARM — PARK ZONE
# ═══════════════════════════════════════════════════════════════════════════════
_log("building park zone")

# Park lawn base (Y=[9.5,42], X=[10,46]) with procedural hair grass.
_log("park: lawn")
_place_lawn_patch("park_lawn_asset", 28, 26, 36, 32, C_e)

# Park entrance: gate posts at Y=9 on E arm N flower-bed edge (X=[11,15])
_log("park: entrance and paths")
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

# ── Procedurally regenerate pavilion and bandstand in-place ───────────────────
_log("park: pavilion and bandstand")
_gen_pavilion("park_pavilion", (30.0, 22.0), C_e, scale=1.0)
_gen_bandstand("park_bandstand", (18.0, 30.0), C_e, scale=0.9)

# ── Water feature at (20, 15) ─────────────────────────────────────────────────
_log("park: water and furniture")
UA._cyl("wf_rim", 20, 15, 0.04, 2.4, 0.32, M["park_stone"], C_e, verts=24)
UA._cyl("wf_water", 20, 15, 0.04, 1.9, 0.24, M["water_blue"], C_e, verts=24)
UA._cyl("wf_spout", 20, 15, 0.28, 0.06, 1.0, M["park_stone"], C_e, verts=12)
UA._cyl("wf_basin", 20, 15, 1.30, 0.35, 0.08, M["park_stone"], C_e, verts=16)

# Park benches and bins
for px, py, pw in [(13.5, 14, math.pi / 2), (13.5, 26, math.pi / 2), (24, 34, 0)]:
    _gen_bench(f"bench_park_{px}_{py}", (px, py), C_e, yaw=pw, scale=0.9)
for px, py in [(17, 12), (27, 32)]:
    _gen_bin(f"bin_park_{px}_{py}", (px, py), C_e, scale=0.9)

# Phone booth on E arm north sidewalk, using the generated K6 asset at real scale.
_build_phonebooth("phone_e", 22, S1 - SW / 2, C_furn, yaw=math.pi, scale=1.15)

# E arm lamps (N side yaw=π, S side yaw=0)
for x in [8, 14, 20, 26, 32, 38, 44]:
    UA.place_streetlight((x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -(R + SW / 2 - 0.2)), C_lamp, yaw=0, day=True)

# Park trees — large belt2 shrubs throughout park
_log("park: trees")
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
_log("building commercial zone")

# 3 kiosk5 shops on east side of S arm, facing road (west, yaw=−π/2)
for i, cy_shop in enumerate([-14.0, -24.0, -34.0]):
    if i == 0:
        _gen_kiosk_pair(
            f"kiosk_shop{i}", (12.0, cy_shop), C_s, yaw=-math.pi / 2, scale=0.95
        )
    else:
        _shop_facade(
            f"kiosk_light{i}",
            11.5,
            cy_shop,
            C_s,
            w=4.0,
            d=3.0,
            h=3.6,
            mat=M["shop_beige"] if i == 1 else M["shop_red"],
            aw_mat=M["awning_g"] if i == 1 else M["awning_b"],
        )
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
    _gen_bench(
        f"bench_s{y}", (S1 - SW / 2 + 0.3, y), C_furn, yaw=math.pi / 2, scale=0.9
    )
for y in [-20, -30, -40]:
    _gen_bin(f"bin_s{y}", (S1 - SW / 2 + 0.3, y), C_furn, scale=0.9)
_build_phonebooth("phone_s", 5.5, -42.0, C_furn, yaw=0, scale=1.15)  # faces north

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
_log("building west arm")

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
_log("placing vehicles")
# Right-hand traffic: only imported/procedural-asset vehicles on road lanes, no preview ground planes.
_place_clean_vehicle("ducato_north", (2.5, 22.0), C_cars, yaw=math.pi / 2)
_place_clean_vehicle("ducato_west", (-30.0, 2.5), C_cars, yaw=math.pi)
_place_clean_vehicle("ducato_east", (22.0, -2.5), C_cars, yaw=0.0)

# Infinigen linked vehicles if available
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
_log("saving blend")
_builtin_font = bpy.data.fonts.get("Bfont") or bpy.data.fonts.get("Bfont Regular")
if _builtin_font is None:
    _builtin_font = next((f for f in bpy.data.fonts if f.filepath == "<builtin>"), None)
if _builtin_font:
    for _obj in bpy.data.objects:
        if _obj.type == "FONT":
            _obj.data.font = _builtin_font
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all7.blend"))
print("[v7] .blend saved")

if "--no-render" in sys.argv:
    print("[v7] no-render requested; saved blend only")
    raise SystemExit(0)

# ─── RENDER ALL CAMERAS ───────────────────────────────────────────────────────
for cname, cam in cam_objects.items():
    scene.camera = cam
    out_png = str(OUT / f"{cname}.png")
    scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    print(f"[v7] rendered {cname} -> {out_png}")

print("[v7] All done. Files in", OUT)
