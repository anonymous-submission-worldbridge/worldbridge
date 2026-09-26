"""
Urban Street Scene — All v3 Outdoor Assets Combined
====================================================
80m stretch of mixed-use street assembling every urban_v3 asset:

  • Road: asphalt, centre-line dashes, crosswalk, stop line
  • Street lamps (modern LED overhang) — both sides
  • Traffic lights (vertical 3-aspect + pedestrian head) — intersection
  • Bus stop shelter (glass/alu, bench, ad lightbox, route totem)
  • Benches (slatted wood-on-metal) + Cylindrical trash bins
  • K6 Red telephone box (British GPO style)
  • Street kiosk — newsstand / press shop
  • Shared-bicycle docking station (3 bikes + info totem)
  • Trees (layered sphere canopy + tapered trunk) — both sides
  • Building facades with window arrays — both sides (background)

Layout (bird's eye, X = across street, Y = along road):
  Road:           X ∈ [−4,  4]
  Right sidewalk: X ∈ [ 4,  9]  ← all main assets here
  Left sidewalk:  X ∈ [−9, −4]
  Y: −40 → +40 (40 m visible each way)

Cameras:
  CAM_Overview    → overview.png       (28 mm elevated wide shot)
  CAM_StreetLevel → streetlevel.png    (50 mm pedestrian, faces north)
  CAM_BusStop     → busstop_detail.png (85 mm, close on shelter)
  CAM_Kiosk       → kiosk_detail.png   (85 mm, kiosk + phone booth)

Run:
  ${BLENDER_BIN} -b --python scripts/generate_urban_v3_all.py
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
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]

import math
import os
from pathlib import Path

import bpy
from mathutils import Vector

# ─── OUTPUT ────────────────────────────────────────────────────────────────
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all")
OUT.mkdir(parents=True, exist_ok=True)
SCENE_BLD = OUT / "street_scene.blend"
IMG_OV = OUT / "overview.png"
IMG_SL = OUT / "streetlevel.png"
IMG_BS = OUT / "busstop_detail.png"
IMG_KI = OUT / "kiosk_detail.png"

TMP = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/tmp_blender")
TMP.mkdir(parents=True, exist_ok=True)

# ─── SCENE GEOMETRY CONSTANTS ────────────────────────────────────────────────
ROAD_W = 8.0  # road width  (X: −4 → +4)
SW_W = 5.0  # sidewalk width each side
CURB_H = 0.14  # sidewalk raised above road
ROAD_LEN = 80.0  # total length  (Y: −40 → +40)

ROAD_EDGE = ROAD_W / 2  # 4.0
SW_Z = CURB_H  # surface Z of sidewalk = 0.14
RSW_CX = ROAD_EDGE + SW_W / 2  # right sidewalk centre X = 6.5

TAU = math.tau
M: dict = {}  # material registry


# ─── SCENE UTILITIES ────────────────────────────────────────────────────────
def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blk in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.images,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.node_groups,
    ):
        for item in list(blk):
            if item.users == 0:
                blk.remove(item)


def new_coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def to_coll(obj, c):
    c.objects.link(obj)
    for oc in list(obj.users_collection):
        if oc.name != c.name:
            try:
                oc.objects.unlink(obj)
            except Exception:
                pass
    return obj


def shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def add_bevel(obj, w=0.008, segs=2):
    mod = obj.modifiers.new("Bev", "BEVEL")
    mod.width = w
    mod.segments = segs
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)


# ─── MATERIAL BUILDERS ──────────────────────────────────────────────────────
def _pbr(name, rgb, rough=0.5, metal=0.0, emit=None, emit_str=1.0, trans=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for key in ("Transmission Weight", "Transmission"):
        if key in b.inputs:
            b.inputs[key].default_value = trans
            break
    if emit is not None:
        for key in ("Emission Color", "Emission"):
            if key in b.inputs:
                b.inputs[key].default_value = (*emit, 1.0)
                break
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = emit_str
    return mat


def _glass(name, rgb=(0.88, 0.92, 0.90), rough=0.015):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    for key in ("Transmission Weight", "Transmission"):
        if key in b.inputs:
            b.inputs[key].default_value = 0.95
            break
    b.inputs["IOR"].default_value = 1.517
    if "Alpha" in b.inputs:
        b.inputs["Alpha"].default_value = 0.10
    mat.show_transparent_back = False
    return mat


def build_materials():
    M["asphalt"] = _pbr("M_Asphalt", (0.028, 0.028, 0.030), rough=0.92)
    M["concrete"] = _pbr("M_Concrete", (0.50, 0.48, 0.46), rough=0.88)
    M["curb"] = _pbr("M_Curb", (0.62, 0.60, 0.57), rough=0.82)
    M["mdk"] = _pbr("M_MDk", (0.06, 0.06, 0.07), rough=0.45, metal=0.82)
    M["mal"] = _pbr("M_MAl", (0.75, 0.75, 0.76), rough=0.20, metal=0.92)
    M["mst"] = _pbr("M_MSt", (0.62, 0.62, 0.64), rough=0.18, metal=0.95)
    M["glass"] = _glass("M_Glass")
    M["glass_bl"] = _glass("M_GlBl", (0.78, 0.88, 0.94))
    M["red"] = _pbr("M_Red", (0.72, 0.04, 0.03), rough=0.32)
    M["yel_on"] = _pbr(
        "M_YelOn", (1.0, 0.80, 0.02), rough=0.06, emit=(1.0, 0.80, 0.02), emit_str=2.5
    )
    M["grn_on"] = _pbr(
        "M_GrnOn", (0.04, 0.82, 0.10), rough=0.06, emit=(0.04, 0.82, 0.10), emit_str=5.0
    )
    M["red_on"] = _pbr("M_RedOn", (0.95, 0.05, 0.03), rough=0.06)
    M["lens_off"] = _pbr("M_LensOff", (0.04, 0.04, 0.04), rough=0.08)
    M["wht"] = _pbr("M_White", (0.95, 0.95, 0.95), rough=0.65)
    M["yel_line"] = _pbr("M_YelLine", (0.95, 0.80, 0.05), rough=0.65)
    M["wood_dk"] = _pbr("M_WoodDk", (0.20, 0.12, 0.07), rough=0.68)
    M["wood_lt"] = _pbr("M_WoodLt", (0.58, 0.40, 0.20), rough=0.62)
    M["glow"] = _pbr(
        "M_Glow", (1.0, 0.97, 0.90), rough=0.05, emit=(1.0, 0.97, 0.90), emit_str=12.0
    )
    M["leaf"] = _pbr("M_Leaf", (0.07, 0.25, 0.05), rough=0.78)
    M["bark"] = _pbr("M_Bark", (0.30, 0.20, 0.11), rough=0.87)
    M["facade"] = _pbr("M_Facade", (0.52, 0.50, 0.48), rough=0.84)
    M["window"] = _glass("M_Win", (0.60, 0.78, 0.88))
    M["kiosk_w"] = _pbr("M_KioskW", (0.94, 0.90, 0.82), rough=0.52)
    M["kiosk_g"] = _pbr("M_KioskG", (0.04, 0.35, 0.12), rough=0.48)
    M["bike_tl"] = _pbr("M_BikeTl", (0.04, 0.50, 0.54), rough=0.40, metal=0.15)
    M["bike_bk"] = _pbr("M_BikeBk", (0.03, 0.03, 0.03), rough=0.78)
    M["rubber"] = _pbr("M_Rubber", (0.04, 0.04, 0.04), rough=0.90)
    M["bus_roof"] = _pbr("M_BusRf", (0.26, 0.26, 0.28), rough=0.52, metal=0.55)
    M["ad"] = _pbr("M_Ad", (0.96, 0.93, 0.88), rough=0.58)
    M["soil"] = _pbr("M_Soil", (0.25, 0.18, 0.11), rough=0.96)


# ─── GEOMETRY PRIMITIVES ────────────────────────────────────────────────────
def _b(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=0.0, rz=0.0):
    """Box centered at (cx,cy,cz) with full dims (dx,dy,dz)."""
    bpy.ops.mesh.primitive_cube_add(location=(cx, cy, cz))
    o = bpy.context.object
    o.name = name
    o.scale = (dx / 2, dy / 2, dz / 2)
    if rz:
        o.rotation_euler[2] = rz
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    if bev > 0:
        add_bevel(o, bev)
    if mat:
        o.data.materials.append(mat)
    to_coll(o, coll)
    return o


def _c(name, cx, cy, cz, r, h, mat, coll, verts=32, rx=0.0, rz=0.0):
    """Cylinder centered at (cx,cy,cz), radius r, height h along Z."""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=r, depth=h, vertices=verts, location=(cx, cy, cz)
    )
    o = bpy.context.object
    o.name = name
    if rx:
        o.rotation_euler[0] = rx
    if rz:
        o.rotation_euler[2] = rz
    bpy.ops.object.transform_apply(rotation=True)
    shade_smooth(o)
    if mat:
        o.data.materials.append(mat)
    to_coll(o, coll)
    return o


def _s(name, cx, cy, cz, r, mat, coll, segs=22, rings=14):
    """UV sphere."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=r, location=(cx, cy, cz), segments=segs, ring_count=rings
    )
    o = bpy.context.object
    o.name = name
    shade_smooth(o)
    if mat:
        o.data.materials.append(mat)
    to_coll(o, coll)
    return o


def _cone(name, cx, cy, cz, r1, r2, h, mat, coll, verts=20):
    bpy.ops.mesh.primitive_cone_add(
        radius1=r1, radius2=r2, depth=h, vertices=verts, location=(cx, cy, cz)
    )
    o = bpy.context.object
    o.name = name
    shade_smooth(o)
    if mat:
        o.data.materials.append(mat)
    to_coll(o, coll)
    return o


# ─── ROAD + SIDEWALK + MARKINGS ─────────────────────────────────────────────
def build_road(C):
    sw_cx = ROAD_EDGE + SW_W / 2  # = 6.5

    # Asphalt road slab
    _b("road", 0, 0, -0.06, ROAD_W, ROAD_LEN, 0.12, M["asphalt"], C)
    # Right sidewalk
    _b("sw_r", sw_cx, 0, CURB_H / 2, SW_W, ROAD_LEN, CURB_H, M["concrete"], C)
    # Left sidewalk
    _b("sw_l", -sw_cx, 0, CURB_H / 2, SW_W, ROAD_LEN, CURB_H, M["concrete"], C)
    # Curb strips
    _b("curb_r", ROAD_EDGE + 0.13, 0, CURB_H / 2, 0.26, ROAD_LEN, CURB_H, M["curb"], C)
    _b("curb_l", -ROAD_EDGE - 0.13, 0, CURB_H / 2, 0.26, ROAD_LEN, CURB_H, M["curb"], C)
    # Extended ground (buildings sit on this)
    _b("gnd_r", ROAD_EDGE + SW_W + 12, 0, -0.06, 26, ROAD_LEN, 0.12, M["soil"], C)
    _b("gnd_l", -ROAD_EDGE - SW_W - 12, 0, -0.06, 26, ROAD_LEN, 0.12, M["soil"], C)

    # Centre-lane dashes (yellow)
    for i in range(-6, 7):
        _b(f"ld{i}", 0, i * 6.2, 0.002, 0.13, 3.2, 0.004, M["yel_line"], C)

    # Crosswalk (9 white stripes at Y=−34)
    for j in range(9):
        xc = -3.60 + j * 0.88
        _b(f"xw{j}", xc, -34.0, 0.003, 0.65, 2.80, 0.006, M["wht"], C)

    # Stop line
    _b("stopln", 0, -35.7, 0.003, ROAD_W, 0.36, 0.006, M["wht"], C)


# ─── STREET LAMP ────────────────────────────────────────────────────────────
def build_lamp(tag, x, y, C):
    z0 = SW_Z
    ph = 8.8  # pole height
    arm = 2.8  # arm reach toward road centre
    side = -1 if x > 0 else 1  # arm extends toward road (negative X for right-side)
    arm_end = x + side * arm
    arm_mid = (x + arm_end) / 2
    arm_z = z0 + ph - 0.26

    _c(f"lp_pole_{tag}", x, y, z0 + ph / 2, 0.055, ph, M["mal"], C)
    # Elbow cap at top
    _c(f"lp_elb_{tag}", x, y, z0 + ph - 0.10, 0.082, 0.20, M["mal"], C)
    # Horizontal arm
    _b(f"lp_arm_{tag}", arm_mid, y, arm_z, abs(x - arm_end), 0.055, 0.055, M["mal"], C)
    # Head housing
    _b(
        f"lp_hd_{tag}",
        arm_end,
        y,
        arm_z - 0.22,
        0.65,
        0.21,
        0.12,
        M["mdk"],
        C,
        bev=0.006,
    )
    # Emissive LED panel
    _b(f"lp_ln_{tag}", arm_end, y, arm_z - 0.275, 0.56, 0.18, 0.008, M["glow"], C)


# ─── TRAFFIC LIGHT ──────────────────────────────────────────────────────────
def build_trafficlight(tag, x, y, face_y, C):
    """face_y: +1 → lenses face +Y; −1 → lenses face −Y."""
    z0 = SW_Z
    ph = 7.2

    _c(f"tl_pole_{tag}", x, y, z0 + ph / 2, 0.055, ph, M["mdk"], C)

    hz = z0 + ph - 0.55
    _b(f"tl_hous_{tag}", x, y, hz, 0.28, 0.22, 1.10, M["mdk"], C, bev=0.008)

    ly = y + face_y * 0.12
    for i, (mk, dz) in enumerate(
        [("red_on", 0.36), ("yel_on", 0.0), ("grn_on", -0.36)]
    ):
        _c(f"tl_ln{i}_{tag}", x, ly, hz + dz, 0.088, 0.026, M[mk], C, verts=32)
        # visor hood
        _b(
            f"tl_v{i}_{tag}",
            x,
            ly + face_y * 0.045,
            hz + dz + 0.065,
            0.20,
            0.07,
            0.038,
            M["mdk"],
            C,
        )

    # Short arm back to pole
    arm_x = x - (0.40 if x > 0 else -0.40)
    _b(
        f"tl_arm_{tag}",
        (x + arm_x) / 2,
        y,
        z0 + ph + 0.06,
        abs(x - arm_x) + 0.06,
        0.06,
        0.06,
        M["mdk"],
        C,
    )


# ─── BUS STOP SHELTER ───────────────────────────────────────────────────────
def build_busstop(tag, cx, cy, C):
    """Shelter centre at (cx, cy). Opens toward −X (road side)."""
    z0 = SW_Z
    W = 3.4  # width along road (Y)
    D = 1.65  # depth into sidewalk (X)
    H = 2.65

    # Roof
    _b(
        f"bs_rf_{tag}",
        cx,
        cy,
        z0 + H + 0.07,
        D + 0.30,
        W + 0.35,
        0.12,
        M["bus_roof"],
        C,
        bev=0.006,
    )

    # 4 corner posts
    for ox, oy, pfx in [
        (-D / 2 + 0.04, -W / 2 + 0.04, "LL"),
        (-D / 2 + 0.04, W / 2 - 0.04, "LR"),
        (D / 2 - 0.04, -W / 2 + 0.04, "RL"),
        (D / 2 - 0.04, W / 2 - 0.04, "RR"),
    ]:
        _b(
            f"bs_pt_{tag}_{pfx}",
            cx + ox,
            cy + oy,
            z0 + H / 2,
            0.055,
            0.055,
            H,
            M["mal"],
            C,
            bev=0.004,
        )

    # Back wall (facing away from road, at +X side of shelter)
    _b(
        f"bs_bk_{tag}",
        cx + D / 2 - 0.02,
        cy,
        z0 + H / 2,
        0.034,
        W - 0.12,
        H - 0.12,
        M["glass_bl"],
        C,
    )

    # Side glass panels
    for sign, sfx in [(-1, "a"), (1, "b")]:
        _b(
            f"bs_sd{sfx}_{tag}",
            cx,
            cy + sign * (W / 2 - 0.018),
            z0 + H / 2,
            D - 0.12,
            0.034,
            H - 0.18,
            M["glass_bl"],
            C,
        )

    # Internal bench seat
    bx = cx + D / 2 - 0.52
    _b(
        f"bs_seat_{tag}",
        bx,
        cy,
        z0 + 0.52,
        0.38,
        W - 0.52,
        0.06,
        M["wood_dk"],
        C,
        bev=0.004,
    )
    for sign in [-1, 1]:
        _b(
            f"bs_bl{sign}_{tag}",
            bx,
            cy + sign * (W / 2 - 0.54),
            z0 + 0.27,
            0.04,
            0.04,
            0.52,
            M["mal"],
            C,
        )

    # Ad lightbox (on −Y face, open side toward road)
    _b(
        f"bs_ad_{tag}",
        cx - D / 2 + 0.07,
        cy - W / 2 + 0.65,
        z0 + 1.32,
        0.12,
        1.02,
        1.44,
        M["ad"],
        C,
        bev=0.005,
    )

    # Route-info totem pole (just outside +Y end)
    ty = cy + W / 2 + 0.45
    _c(f"bs_tp_{tag}", cx - D / 2 + 0.04, ty, z0 + 1.95, 0.038, 3.90, M["mal"], C)
    _b(
        f"bs_ts_{tag}",
        cx - D / 2 + 0.04,
        ty,
        z0 + 3.42,
        0.10,
        0.54,
        0.80,
        M["kiosk_g"],
        C,
        bev=0.005,
    )


# ─── BENCH ──────────────────────────────────────────────────────────────────
def build_bench(tag, cx, cy, C):
    z0 = SW_Z
    BL = 1.85
    for i, ox in enumerate([-0.072, 0.0, 0.072]):
        _b(
            f"bc_sl{i}_{tag}",
            cx + ox,
            cy,
            z0 + 0.47,
            0.038,
            BL,
            0.032,
            M["wood_dk"],
            C,
            bev=0.003,
        )
    for i, dz in enumerate([0.0, 0.085]):
        _b(
            f"bc_bk{i}_{tag}",
            cx + 0.03,
            cy,
            z0 + 0.70 + dz,
            0.032,
            BL,
            0.032,
            M["wood_dk"],
            C,
            bev=0.003,
        )
    for sign, sfx in [(-1, "a"), (1, "b")]:
        ey = cy + sign * (BL / 2 - 0.10)
        _b(f"bc_lg_{tag}_{sfx}", cx, ey, z0 + 0.24, 0.040, 0.040, 0.48, M["mal"], C)
        _b(
            f"bc_ar_{tag}_{sfx}",
            cx + 0.02,
            ey,
            z0 + 0.63,
            0.052,
            0.040,
            0.04,
            M["wood_lt"],
            C,
            bev=0.003,
        )


# ─── TRASH BIN ──────────────────────────────────────────────────────────────
def build_bin(tag, cx, cy, C):
    z0 = SW_Z
    _c(f"bn_post_{tag}", cx, cy, z0 + 0.40, 0.030, 0.80, M["mal"], C)
    _c(f"bn_body_{tag}", cx, cy, z0 + 1.02, 0.190, 0.62, M["mdk"], C, verts=24)
    _cone(f"bn_lid_{tag}", cx, cy, z0 + 1.38, 0.196, 0.176, 0.12, M["mal"], C, verts=24)


# ─── K6 RED PHONE BOOTH ────────────────────────────────────────────────────
def build_phonebooth(tag, cx, cy, C):
    z0 = SW_Z
    BW, BD, BH = 1.02, 1.02, 2.65
    wall_t = 0.075

    # Plinth
    _b(
        f"ph_base_{tag}",
        cx,
        cy,
        z0 + 0.09,
        BW + 0.07,
        BD + 0.07,
        0.18,
        M["mal"],
        C,
        bev=0.007,
    )

    # Four red walls
    for side, (ox, oy, wx, wy) in enumerate(
        [
            (0, BD / 2, BW, wall_t),
            (0, -BD / 2, BW, wall_t),
            (BW / 2, 0, wall_t, BD),
            (-BW / 2, 0, wall_t, BD),
        ]
    ):
        _b(
            f"ph_w{side}_{tag}",
            cx + ox,
            cy + oy,
            z0 + 0.18 + BH / 2,
            wx,
            wy,
            BH,
            M["red"],
            C,
            bev=0.005,
        )

    # Glass inserts (2 panes per face)
    gh = 1.40
    gz = z0 + 0.18 + 0.90
    eps = 0.006
    # Front (+Y) and back (−Y) faces: 2 panes side-by-side along X
    for face_oy, label in [(BD / 2, "f"), (-BD / 2, "b")]:
        for gx, gi in [(-BW / 4 + 0.02, "0"), (BW / 4 - 0.02, "1")]:
            _b(
                f"ph_g{label}{gi}_{tag}",
                cx + gx,
                cy + face_oy + (-eps if face_oy > 0 else eps),
                gz,
                BW / 2 - 0.10,
                0.024,
                gh,
                M["glass"],
                C,
            )
    # Right (+X) and left (−X) faces: 2 panes along Y
    for face_ox, label in [(BW / 2, "r"), (-BW / 2, "l")]:
        for gy, gi in [(-BD / 4 + 0.02, "0"), (BD / 4 - 0.02, "1")]:
            _b(
                f"ph_g{label}{gi}_{tag}",
                cx + face_ox + (-eps if face_ox > 0 else eps),
                cy + gy,
                gz,
                0.024,
                BD / 2 - 0.10,
                gh,
                M["glass"],
                C,
            )

    # Crown band
    _b(
        f"ph_cr_{tag}",
        cx,
        cy,
        z0 + 0.18 + BH + 0.09,
        BW + 0.05,
        BD + 0.05,
        0.18,
        M["red"],
        C,
        bev=0.006,
    )

    # Dome (squashed UV sphere)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.65,
        location=(cx, cy, z0 + 0.18 + BH + 0.50),
        segments=32,
        ring_count=20,
    )
    dome = bpy.context.object
    dome.name = f"ph_dome_{tag}"
    dome.scale.z = 0.50
    bpy.ops.object.transform_apply(scale=True)
    shade_smooth(dome)
    dome.data.materials.append(M["red"])
    to_coll(dome, C)


# ─── STREET KIOSK (NEWSSTAND) ───────────────────────────────────────────────
def build_kiosk(tag, cx, cy, C):
    """kiosk back at +X, service window faces −X (road)."""
    z0 = SW_Z
    KW, KD, KH = 2.4, 1.60, 2.50

    # Main body (back two-thirds)
    bx = cx + KD / 6
    _b(
        f"ki_bd_{tag}",
        bx,
        cy,
        z0 + KH / 2,
        KD * 2 / 3,
        KW,
        KH,
        M["kiosk_w"],
        C,
        bev=0.008,
    )

    # Front fascia: top beam, bottom sill, side pillars (green)
    fx = cx - KD / 3
    _b(f"ki_ft_{tag}", fx, cy, z0 + KH / 2, KD / 3, KW, KH, M["kiosk_g"], C, bev=0.006)
    # Window opening: cut via slightly inset glass
    _b(
        f"ki_gl_{tag}",
        cx - KD / 2 + 0.025,
        cy,
        z0 + 1.26,
        0.025,
        KW - 0.54,
        0.84,
        M["glass"],
        C,
    )

    # Roof awning
    _b(
        f"ki_rf_{tag}",
        cx,
        cy,
        z0 + KH + 0.11,
        KD + 0.45,
        KW + 0.58,
        0.18,
        M["kiosk_g"],
        C,
        bev=0.008,
    )

    # Magazine slat display on front face
    for i in range(3):
        _b(
            f"ki_mg{i}_{tag}",
            cx - KD / 2 - 0.025,
            cy - 0.72 + i * 0.74,
            z0 + 0.96 + i * 0.14,
            0.04,
            0.56,
            0.22,
            M["ad"],
            C,
            bev=0.003,
        )


# ─── SHARED BICYCLE DOCKING STATION ────────────────────────────────────────
def build_bicycle_station(tag, cx, cy, C):
    z0 = SW_Z
    RL = 4.8  # rail length along Y

    # Low dock rail
    _b(f"bk_rl_{tag}", cx, cy, z0 + 0.08, 0.08, RL, 0.08, M["mal"], C, bev=0.005)
    # End uprights
    for sign, sfx in [(-1, "a"), (1, "b")]:
        _c(
            f"bk_up{sfx}_{tag}",
            cx,
            cy + sign * RL / 2,
            z0 + 0.38,
            0.038,
            0.76,
            M["mal"],
            C,
        )

    # 3 docked bikes (wheel-to-wheel axis along X = perpendicular to road)
    for i, by in enumerate([cy - 1.5, cy, cy + 1.5]):
        _build_bike(f"{tag}_{i}", cx + 0.65, by, z0, C)

    # Info / payment totem
    ty = cy + RL / 2 + 0.70
    _c(f"bk_tp_{tag}", cx, ty, z0 + 1.18, 0.036, 2.36, M["mal"], C)
    _b(f"bk_th_{tag}", cx, ty, z0 + 2.55, 0.12, 0.50, 0.76, M["kiosk_g"], C, bev=0.007)


def _build_bike(tag, cx, cy, z0, C):
    """Simplified parked bicycle. Wheel axle along Y, length along X."""
    rw = 0.30  # wheel radius
    # Wheels: cylinder with height along Y (rx=90°) → stands in XZ plane
    for pfx, wx in [("r", cx + 0.50), ("f", cx - 0.50)]:
        _c(
            f"bk_wh{pfx}_{tag}",
            wx,
            cy,
            z0 + rw,
            rw,
            0.05,
            M["bike_bk"],
            C,
            verts=28,
            rx=math.pi / 2,
        )
        _c(
            f"bk_rm{pfx}_{tag}",
            wx,
            cy,
            z0 + rw,
            rw * 0.74,
            0.04,
            M["mal"],
            C,
            verts=28,
            rx=math.pi / 2,
        )
    # Frame
    _b(
        f"bk_top_{tag}",
        cx,
        cy,
        z0 + 0.60,
        1.00,
        0.040,
        0.040,
        M["bike_tl"],
        C,
        bev=0.006,
    )
    _b(f"bk_st_{tag}", cx + 0.22, cy, z0 + 0.50, 0.040, 0.040, 0.40, M["bike_tl"], C)
    _b(
        f"bk_dt_{tag}",
        cx + 0.05,
        cy,
        z0 + 0.38,
        0.80,
        0.038,
        0.038,
        M["bike_tl"],
        C,
        rz=math.radians(12),
    )
    # Saddle
    _b(
        f"bk_sd_{tag}",
        cx + 0.32,
        cy,
        z0 + 0.79,
        0.30,
        0.14,
        0.040,
        M["rubber"],
        C,
        bev=0.005,
    )
    # Handlebar
    _b(
        f"bk_hb_{tag}",
        cx - 0.38,
        cy,
        z0 + 0.74,
        0.06,
        0.40,
        0.048,
        M["rubber"],
        C,
        bev=0.004,
    )


# ─── TREE ───────────────────────────────────────────────────────────────────
def build_tree(tag, cx, cy, C, th=2.8, cr=1.7):
    z0 = SW_Z
    _cone(f"tr_tr_{tag}", cx, cy, z0 + th / 2, 0.18, 0.08, th, M["bark"], C, verts=12)
    _s(f"tr_lo_{tag}", cx, cy, z0 + th + cr * 0.45, cr, M["leaf"], C, segs=20, rings=14)
    _s(
        f"tr_hi_{tag}",
        cx,
        cy,
        z0 + th + cr * 0.92,
        cr * 0.78,
        M["leaf"],
        C,
        segs=18,
        rings=12,
    )
    _b(f"tr_pt_{tag}", cx, cy, z0 - 0.005, 1.10, 1.10, 0.02, M["soil"], C)


# ─── BUILDING FACADE ────────────────────────────────────────────────────────
def build_facade(tag, cx, cy, w_y, d_x, h, C, floors=4, right_side=True):
    """Building box (width along Y, depth along X) with window array.
    right_side=True → front face at cx−d_x/2 (faces −X toward road).
    """
    _b(f"bld_{tag}", cx, cy, h / 2, d_x, w_y, h, M["facade"], C)
    # Front face X coordinate and direction
    if right_side:
        fx = cx - d_x / 2
        fdx = -0.018  # windows slightly proud of face
    else:
        fx = cx + d_x / 2
        fdx = 0.018
    fh = h / floors
    nw = max(2, int(w_y / 2.5))
    ww = (w_y / nw) * 0.52
    wh = fh * 0.46
    for fl in range(floors):
        wz = fl * fh + fh * 0.56
        for wi in range(nw):
            wy = cy - w_y / 2 + (wi + 0.5) * (w_y / nw)
            _b(
                f"win_{tag}_{fl}_{wi}",
                fx + fdx,
                wy,
                wz,
                0.034,
                ww,
                wh,
                M["window"],
                C,
                bev=0.002,
            )


# ─── LIGHTING ───────────────────────────────────────────────────────────────
def build_world():
    world = bpy.data.worlds.new("street_sky")
    world.use_nodes = True
    bpy.context.scene.world = world
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(30)  # morning sun, low angle
    sky.sun_rotation = math.radians(-65)  # east-south-east
    sky.altitude = 200
    sky.air_density = 1.0
    sky.dust_density = 0.20

    # Light-path split: full sky for camera rays, dimmed for light bounces
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_c = nt.nodes.new("ShaderNodeBackground")
    bg_l = nt.nodes.new("ShaderNodeBackground")
    mix = nt.nodes.new("ShaderNodeMixShader")
    bg_c.inputs["Strength"].default_value = 1.0
    bg_l.inputs["Strength"].default_value = 0.30

    nt.links.new(sky.outputs["Color"], bg_c.inputs["Color"])
    nt.links.new(sky.outputs["Color"], bg_l.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_l.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_c.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

    # Key sun lamp
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.object
    sun.name = "Sun_Key"
    sun.data.energy = 3.2
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.95, 0.85)
    sun.rotation_euler = (math.radians(60), 0, math.radians(-65))

    # Soft fill (sky-blue area light, left side)
    bpy.ops.object.light_add(type="AREA", location=(-18, 0, 20))
    fill = bpy.context.object
    fill.name = "Fill_Sky"
    fill.data.shape = "RECTANGLE"
    fill.data.size = 16.0
    fill.data.size_y = 10.0
    fill.data.energy = 600.0
    fill.data.color = (0.68, 0.82, 1.0)
    fill.rotation_euler = (
        (Vector((0, 0, 0)) - Vector((-18, 0, 20))).to_track_quat("-Z", "Y").to_euler()
    )


# ─── CAMERAS ────────────────────────────────────────────────────────────────
def make_camera(name, loc, look_at, lens=50, fstop=None):
    cam = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(obj)
    cam.lens = lens
    cam.sensor_width = 36
    obj.location = loc
    obj.rotation_euler = (
        (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    if fstop is not None:
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
        focus = bpy.data.objects.new(f"{name}_foc", None)
        bpy.context.scene.collection.objects.link(focus)
        focus.location = look_at
        cam.dof.focus_object = focus
    return obj


def build_cameras():
    cams = {}
    # Elevated wide shot — whole scene visible
    cams["ov"] = make_camera(
        "CAM_Overview", loc=(30, -42, 28), look_at=(0, 8, 0.5), lens=28
    )
    # Pedestrian height, right sidewalk, looking north
    cams["sl"] = make_camera(
        "CAM_StreetLevel",
        loc=(7.5, -38, 1.68),
        look_at=(6.5, 15, 1.65),
        lens=50,
        fstop=3.5,
    )
    # Bus stop close-up: shoot from road side looking right
    cams["bs"] = make_camera(
        "CAM_BusStop", loc=(1.5, -24, 2.2), look_at=(7.0, -18, 1.9), lens=85, fstop=2.8
    )
    # Kiosk + phone booth: from road looking right (phone booth Y=4, kiosk Y=14)
    cams["ki"] = make_camera(
        "CAM_Kiosk", loc=(1.5, 8, 2.0), look_at=(7.5, 14, 1.8), lens=85, fstop=2.8
    )
    return cams


# ─── COMPOSITOR ─────────────────────────────────────────────────────────────
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
    glare.threshold = 1.10
    glare.size = 6
    if hasattr(glare, "mix"):
        glare.mix = -0.55

    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


# ─── CYCLES CONFIGURATION ───────────────────────────────────────────────────
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
                gpu_on = False
                for d in devs:
                    d.use = "CPU" not in d.name.upper()
                    gpu_on = gpu_on or d.use
                if gpu_on:
                    chosen = backend
                    break
        except Exception:
            continue
    print(f"[all] Cycles backend: {chosen}")
    scene.cycles.use_denoising = True
    scene.cycles.use_persistent_data = True
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 12
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        pass
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False
    bpy.context.preferences.filepaths.temporary_directory = str(TMP)
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        scene.view_settings.view_transform = "Filmic"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.view_settings.exposure = -0.8  # outdoor daylight


# ─── RENDER HELPERS ─────────────────────────────────────────────────────────
def render_still(cam_obj, path, samples=512):
    scene = bpy.context.scene
    scene.camera = cam_obj
    scene.cycles.samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"[render] {path}")


# ─── SCENE ASSEMBLY ─────────────────────────────────────────────────────────
def build_scene():
    C_rd = new_coll("Road")
    C_lp = new_coll("Lamps")
    C_tl = new_coll("TrafficLights")
    C_bs = new_coll("BusStop")
    C_bn = new_coll("Benches")
    C_ph = new_coll("PhoneBooth")
    C_ki = new_coll("Kiosk")
    C_bk = new_coll("Bicycles")
    C_tr = new_coll("Trees")
    C_bd = new_coll("Buildings")

    # ── Road ────────────────────────────────────────────────────────────────
    build_road(C_rd)

    # ── Street lamps — both sides, every ~15 m ──────────────────────────────
    lamp_ys = [-36, -22, -8, 6, 21, 35]
    for i, y in enumerate(lamp_ys):
        build_lamp(f"R{i}", 5.0, y, C_lp)  # right side (arm reaches toward X=2.2)
        build_lamp(f"L{i}", -5.0, y, C_lp)  # left side

    # ── Traffic lights — intersection at Y ≈ −32 ────────────────────────────
    # Right kerb (X=4.2), lenses face south (face_y=−1, toward approaching traffic)
    build_trafficlight("RS", 4.30, -31.0, face_y=-1, C=C_tl)
    # Left kerb (X=−4.2), lenses face north (face_y=+1)
    build_trafficlight("LS", -4.30, -31.0, face_y=+1, C=C_tl)

    # ── Bus stop shelter — right sidewalk, Y=−18 ────────────────────────────
    build_busstop("A", cx=7.0, cy=-18.0, C=C_bs)

    # ── Benches + trash bins — right sidewalk, Y=−7 to −4 ──────────────────
    build_bench("A", cx=6.8, cy=-7.5, C=C_bn)
    build_bench("B", cx=6.8, cy=-4.0, C=C_bn)
    build_bin("A", cx=8.1, cy=-6.0, C=C_bn)
    build_bin("B", cx=8.1, cy=-2.5, C=C_bn)

    # ── K6 Phone booth — right sidewalk, Y=+4 ───────────────────────────────
    build_phonebooth("A", cx=7.4, cy=4.0, C=C_ph)

    # ── Street kiosk — right sidewalk, Y=+14 ────────────────────────────────
    build_kiosk("A", cx=8.1, cy=14.0, C=C_ki)

    # ── Bicycle docking station — right sidewalk, Y=+24 ─────────────────────
    build_bicycle_station("A", cx=7.2, cy=24.0, C=C_bk)

    # ── Trees — both sides, staggered between lamps ──────────────────────────
    r_tree_ys = [-28, -14, -1, 12, 27, 38]
    for i, y in enumerate(r_tree_ys):
        build_tree(f"R{i}", cx=8.5, cy=y, C=C_tr)
    l_tree_ys = [-33, -19, -5, 8, 22, 36]
    for i, y in enumerate(l_tree_ys):
        build_tree(f"L{i}", cx=-8.5, cy=y, C=C_tr, th=2.6)

    # ── Background building facades ──────────────────────────────────────────
    # Right side — front face at X=12 (cx=14, dx=4)
    for tag, cy, wy, h, fl in [
        ("R1", -22, 7.0, 13, 4),
        ("R2", -8, 5.5, 9, 3),
        ("R3", 6, 6.5, 15, 5),
        ("R4", 22, 6.0, 10, 3),
    ]:
        build_facade(
            tag, cx=14, cy=cy, w_y=wy, d_x=4, h=h, C=C_bd, floors=fl, right_side=True
        )

    # Left side — front face at X=−12 (cx=−14, dx=4)
    for tag, cy, wy, h, fl in [
        ("L1", -24, 8.0, 17, 6),
        ("L2", -7, 6.0, 11, 4),
        ("L3", 10, 7.0, 14, 5),
        ("L4", 26, 5.5, 8, 3),
    ]:
        build_facade(
            tag, cx=-14, cy=cy, w_y=wy, d_x=4, h=h, C=C_bd, floors=fl, right_side=False
        )


# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    reset_scene()
    build_materials()
    build_scene()
    build_world()
    cams = build_cameras()
    setup_compositor()
    configure_cycles()

    # Save .blend
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_BLD))
    print(f"Scene saved → {SCENE_BLD}")

    # Overview (most samples — hero shot)
    render_still(cams["ov"], IMG_OV, samples=768)
    # Street-level (hero shot #2)
    render_still(cams["sl"], IMG_SL, samples=768)
    # Detail shots (fewer samples, faster)
    render_still(cams["bs"], IMG_BS, samples=512)
    render_still(cams["ki"], IMG_KI, samples=512)

    print(f"\nAll outputs → {OUT}/")
    for p in [SCENE_BLD, IMG_OV, IMG_SL, IMG_BS, IMG_KI]:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
