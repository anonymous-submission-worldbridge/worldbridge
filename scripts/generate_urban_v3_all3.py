"""
generate_urban_v3_all3.py
=========================
Photo-realistic 4-way crossroads street scene.

Uses real infinigen assets throughout:
  - Fiat Ducato van    ← openx_preview.blend (Grp_Root hierarchy)
  - Belt2 shrubs       ← belt2.blend (Shrub_N_bark + Shrub_N_leaf pairs)
  - All pre-built urban_v3 assets (traffic lights, bus stop, kiosk, etc.)

No toy UV-sphere trees or box-car models.

Layout: intersection at (0,0), arms extend 40 m in each cardinal direction.
Road: 8 m wide (2 lanes × 4 m). Sidewalk: 3 m. Green belt: 2.5 m.

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all3/
        crossroads.blend + overview.png + intersection.png + northarm.png + eastarm.png
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


import sys, math

sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
from pathlib import Path
from mathutils import Vector, Matrix

import urban_assets as UA

# ─── OUTPUT ───────────────────────────────────────────────────────────────────
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all3")
OUT.mkdir(parents=True, exist_ok=True)

# ─── SCENE SETUP ──────────────────────────────────────────────────────────────
UA.reset_scene()
UA.build_all_materials()
M = UA.M

# Geometry constants
RW = 4.0  # road half-width  → road spans X or Y ∈ [−RW, +RW]
SW = 3.0  # sidewalk width
GW = 2.5  # green-belt width
ARM = 40.0  # arm length beyond RW  → each arm ends at ±(RW+ARM)

R = RW  # 4.0  — inner sidewalk edge
S1 = RW + SW  # 7.0  — outer sidewalk / inner green edge
G1 = S1 + GW  # 9.5  — outer green edge


def C(name):
    return UA.new_coll(name)


C_road = C("Road")
C_sw = C("Sidewalk")
C_green = C("Green")
C_tl = C("TrafficLight")
C_bs = C("BusStop")
C_furn = C("Furniture")
C_kiosk = C("Kiosk")
C_bike = C("BicycleStation")
C_phone = C("PhoneBooth")
C_lamp = C("StreetLamps")
C_shrub = C("Shrubs")
C_cars = C("Vehicles")
C_flow = C("FlowerBeds")
C_house = C("Houses")

# ─── GROUND PLANE ─────────────────────────────────────────────────────────────
gnd_mat = UA._noise_mat(
    "ground_dirt", (0.38, 0.32, 0.24), (0.28, 0.24, 0.18), rough=0.92
)
UA._box("ground_plane", 0, 0, -0.05, 160, 160, 0.1, gnd_mat, C_sw)

# ─── CROSSROADS GEOMETRY ──────────────────────────────────────────────────────
print("[scene] Building crossroads geometry…")


def _road_box(name, cx, cy, dx, dy):
    UA._box(name, cx, cy, -0.02, dx, dy, 0.04, M["road"], C_road)


def _sw_box(name, cx, cy, dx, dy):
    UA._box(name, cx, cy, 0.06, dx, dy, 0.12, M["sidewalk"], C_sw)


def _gn_box(name, cx, cy, dx, dy):
    UA._box(name, cx, cy, 0.00, dx, dy, 0.04, M["greenstrip"], C_green)


# Asphalt
_road_box("isect_center", 0, 0, 2 * RW, 2 * RW)  # intersection
_road_box("road_n", 0, RW + ARM / 2, 2 * RW, ARM)  # north arm
_road_box("road_s", 0, -(RW + ARM / 2), 2 * RW, ARM)  # south arm
_road_box("road_e", RW + ARM / 2, 0, ARM, 2 * RW)  # east arm
_road_box("road_w", -(RW + ARM / 2), 0, ARM, 2 * RW)  # west arm

# Corner sidewalk tiles (3×3 m at each intersection corner)
for sx, sy, sfx in [(1, 1, "ne"), (-1, 1, "nw"), (1, -1, "se"), (-1, -1, "sw")]:
    _sw_box(f"sw_corner_{sfx}", sx * (R + SW / 2), sy * (R + SW / 2), SW, SW)

# N-S arm sidewalks (east and west, excluding corners already placed)
arm_sw_len = ARM - SW  # 37 m
arm_sw_cy = R + SW + arm_sw_len / 2  # center Y of sidewalk strip
for sx, sfx in [(1, "e"), (-1, "w")]:
    _sw_box(f"sw_n_{sfx}", sx * (R + SW / 2), arm_sw_cy, SW, arm_sw_len)
    _sw_box(f"sw_s_{sfx}", sx * (R + SW / 2), -arm_sw_cy, SW, arm_sw_len)
# E-W arm sidewalks (north and south)
arm_sw_cx = R + SW + arm_sw_len / 2
for sy, sfx in [(1, "n"), (-1, "s")]:
    _sw_box(f"sw_e_{sfx}", arm_sw_cx, sy * (R + SW / 2), arm_sw_len, SW)
    _sw_box(f"sw_w_{sfx}", -arm_sw_cx, sy * (R + SW / 2), arm_sw_len, SW)

# Corner green tiles
arm_gn_len = ARM - SW - GW  # 34.5 m
arm_gn_off = R + SW + GW + arm_gn_len / 2
for sx, sy, sfx in [(1, 1, "ne"), (-1, 1, "nw"), (1, -1, "se"), (-1, -1, "sw")]:
    _gn_box(f"gn_corner_{sfx}", sx * (S1 + GW / 2), sy * (S1 + GW / 2), GW, GW)
# N-S arm green belts
for sx, sfx in [(1, "e"), (-1, "w")]:
    _gn_box(f"gn_n_{sfx}", sx * (S1 + GW / 2), arm_gn_off, GW, arm_gn_len)
    _gn_box(f"gn_s_{sfx}", sx * (S1 + GW / 2), -arm_gn_off, GW, arm_gn_len)
# E-W arm green belts
for sy, sfx in [(1, "n"), (-1, "s")]:
    _gn_box(f"gn_e_{sfx}", arm_gn_off, sy * (S1 + GW / 2), arm_gn_len, GW)
    _gn_box(f"gn_w_{sfx}", -arm_gn_off, sy * (S1 + GW / 2), arm_gn_len, GW)

# Kerb strips along road edges
KERB_MAT = M["curb"]
for arm_y in [RW + ARM / 2, -(RW + ARM / 2)]:
    for kx in [RW + 0.08, -(RW + 0.08)]:
        UA._box(
            f"kerb_ns_{arm_y:.0f}_{kx:.0f}",
            kx,
            arm_y,
            0.10,
            0.16,
            ARM,
            0.20,
            KERB_MAT,
            C_sw,
        )
for arm_x in [RW + ARM / 2, -(RW + ARM / 2)]:
    for ky in [RW + 0.08, -(RW + 0.08)]:
        UA._box(
            f"kerb_ew_{arm_x:.0f}_{ky:.0f}",
            arm_x,
            ky,
            0.10,
            ARM,
            0.16,
            0.20,
            KERB_MAT,
            C_sw,
        )

# Yellow center lines (N-S and E-W)
for dx in (-0.08, 0.08):
    UA._box(
        f"cl_ns_{dx:.0f}",
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
        f"cl_ew_{dx:.0f}",
        0,
        dx,
        0.003,
        2 * (RW + ARM),
        0.06,
        0.004,
        M["stripe_y"],
        C_road,
    )

# White lane dashes
for arm, arm_range, is_ns in [
    ("n_r", range(1, 9), True),
    ("n_l", range(1, 9), True),
    ("s_r", range(1, 9), True),
    ("s_l", range(1, 9), True),
]:
    pass
# Keep it simple: 4 sets of dashes for each arm
for yi in range(2, 9):
    y0 = R + yi * (ARM / 9)
    for side in [2.0, -2.0]:
        UA._box(
            f"dash_n_{yi}_{side:.0f}",
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
            f"dash_s_{yi}_{side:.0f}",
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
            f"dash_e_{xi}_{side:.0f}",
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
            f"dash_w_{xi}_{side:.0f}",
            -x0,
            side,
            0.003,
            1.8,
            0.12,
            0.004,
            M["stripe_w"],
            C_road,
        )

# Crosswalks at each arm entrance
for stripe in range(8):
    xf = -RW + 0.5 + stripe * (2 * RW - 1.0) / 8
    UA._box(
        f"xwalk_s_{stripe}",
        xf,
        -(RW + 0.6),
        0.004,
        0.78,
        2.2,
        0.005,
        M["xwalk"],
        C_road,
    )
    UA._box(
        f"xwalk_n_{stripe}", xf, (RW + 0.6), 0.004, 0.78, 2.2, 0.005, M["xwalk"], C_road
    )
for stripe in range(8):
    yf = -RW + 0.5 + stripe * (2 * RW - 1.0) / 8
    UA._box(
        f"xwalk_e_{stripe}", (RW + 0.6), yf, 0.004, 2.2, 0.78, 0.005, M["xwalk"], C_road
    )
    UA._box(
        f"xwalk_w_{stripe}",
        -(RW + 0.6),
        yf,
        0.004,
        2.2,
        0.78,
        0.005,
        M["xwalk"],
        C_road,
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

# ─── TRAFFIC LIGHTS ───────────────────────────────────────────────────────────
# One gantry per approach arm (signals visible to approaching traffic).
# Source gantry: road runs Y, signals face −Y.
# Yaw rotations: 0→signals−Y, π→+Y, +π/2→+X, −π/2→−X
print("[scene] Placing traffic lights (4 gantries)…")
UA.place_trafficlight((0.0, -(RW + 2.5)), C_tl)  # south: northbound signal
UA.place_trafficlight(
    (0.0, (RW + 2.5)), C_tl
)  # north: southbound (yaw via _place below)
UA.place_trafficlight((-(RW + 2.5), 0.0), C_tl)  # west: eastbound
UA.place_trafficlight(((RW + 2.5), 0.0), C_tl)  # east: westbound

# ─── BUS STOP ─────────────────────────────────────────────────────────────────
print("[scene] Placing bus stop (north arm east sidewalk)…")
UA.place_busstop((R + SW / 2, 18.0), C_bs, yaw=-math.pi / 2)

# ─── KIOSK (McDonald's style) ─────────────────────────────────────────────────
print("[scene] Placing kiosk (north arm east sidewalk)…")
UA.place_kiosk5((R + SW / 2, 33.0), C_kiosk, yaw=-math.pi / 2)

# ─── PHONE BOOTH ──────────────────────────────────────────────────────────────
print("[scene] Placing phone booth (south arm east sidewalk)…")
UA.place_phonebooth((R + SW / 2, -16.0), C_phone, yaw=-math.pi / 2)

# ─── BENCH + BIN SETS ─────────────────────────────────────────────────────────
print("[scene] Placing benches and bins…")
UA.place_bench_classic((R + SW / 2 - 0.4, 24.5), C_furn, yaw=-math.pi / 2)
UA.place_bin_domed((R + SW / 2 - 0.4, 27.0), C_furn)
# Second set on west side of north arm
UA.place_bench_classic((-(R + SW / 2 - 0.4), 14.0), C_furn, yaw=math.pi / 2)
UA.place_bin_domed((-(R + SW / 2 - 0.4), 11.5), C_furn)

# ─── BICYCLE STATION (east arm, north sidewalk) ───────────────────────────────
print("[scene] Placing bicycle station (east arm north sidewalk)…")
UA.place_bicycle_station((26.0, R + SW / 2), C_bike, yaw=-math.pi / 2)

# ─── STREET LAMPS ─────────────────────────────────────────────────────────────
# North-South arm lamps
print("[scene] Placing street lamps…")
ns_lamp_ys = [8.0, 15.5, 23.0, 30.5, 38.0]
for y in ns_lamp_ys:
    UA.place_streetlight(
        (R + SW / 2 - 0.2, y), C_lamp, yaw=math.pi / 2
    )  # east side, arm over road
    UA.place_streetlight(
        (-(R + SW / 2 - 0.2), y + 3.5), C_lamp, yaw=-math.pi / 2
    )  # west side
for y in ns_lamp_ys:
    UA.place_streetlight((R + SW / 2 - 0.2, -y), C_lamp, yaw=math.pi / 2)
    UA.place_streetlight((-(R + SW / 2 - 0.2), -(y + 3.5)), C_lamp, yaw=-math.pi / 2)

# East-West arm lamps
ew_lamp_xs = [8.0, 15.5, 23.0, 30.5, 38.0]
for x in ew_lamp_xs:
    UA.place_streetlight(
        (x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi
    )  # north side, arm over road
    UA.place_streetlight((x + 3.5, -(R + SW / 2 - 0.2)), C_lamp, yaw=0.0)  # south side
for x in ew_lamp_xs:
    UA.place_streetlight((-x, R + SW / 2 - 0.2), C_lamp, yaw=math.pi)
    UA.place_streetlight((-(x + 3.5), -(R + SW / 2 - 0.2)), C_lamp, yaw=0.0)

# ─── BELT2 SHRUBS (real infinigen assets) ─────────────────────────────────────
# Replace toy UV-sphere trees with photorealistic infinigen shrubs from belt2.blend.
# Scale 2.5 → ~3 m tall street shrubs/trees; 1.6 → ~2 m gap-fill shrubs.
print("[scene] Planting belt2 shrubs (real infinigen assets)…")

# N and S arm green belts (green at X=[7,9.5] and X=[-9.5,-7])
ns_shrub_ys = [9.0, 14.5, 20.0, 25.5, 31.0, 36.5, 42.0]
for i, y in enumerate(ns_shrub_ys):
    si = i % 5
    UA.place_shrub_belt2(
        f"shr_ne_{i}", (S1 + GW / 2, y), C_shrub, scale=2.2, shrub_idx=si
    )
    UA.place_shrub_belt2(
        f"shr_nw_{i}",
        (-(S1 + GW / 2), y + 2.5),
        C_shrub,
        scale=2.0,
        shrub_idx=(si + 2) % 5,
    )
    UA.place_shrub_belt2(
        f"shr_se_{i}", (S1 + GW / 2, -y), C_shrub, scale=2.2, shrub_idx=(si + 1) % 5
    )
    UA.place_shrub_belt2(
        f"shr_sw_{i}",
        (-(S1 + GW / 2), -(y + 2.5)),
        C_shrub,
        scale=2.0,
        shrub_idx=(si + 3) % 5,
    )

# E and W arm green belts (green at Y=[7,9.5] and Y=[-9.5,-7])
ew_shrub_xs = [9.0, 14.5, 20.0, 25.5, 31.0, 36.5, 42.0]
for i, x in enumerate(ew_shrub_xs):
    si = (i + 1) % 5
    UA.place_shrub_belt2(
        f"shr_en_{i}", (x, S1 + GW / 2), C_shrub, scale=2.0, shrub_idx=si
    )
    UA.place_shrub_belt2(
        f"shr_es_{i}",
        (x + 2.5, -(S1 + GW / 2)),
        C_shrub,
        scale=2.2,
        shrub_idx=(si + 2) % 5,
    )
    UA.place_shrub_belt2(
        f"shr_wn_{i}", (-x, S1 + GW / 2), C_shrub, scale=2.0, shrub_idx=(si + 1) % 5
    )
    UA.place_shrub_belt2(
        f"shr_ws_{i}",
        (-(x + 2.5), -(S1 + GW / 2)),
        C_shrub,
        scale=2.2,
        shrub_idx=(si + 3) % 5,
    )

# Corner shrubs (4 corners)
for cx, cy, sfx, si in [
    (S1 + GW / 2, S1 + GW / 2, "ne", 0),
    (-(S1 + GW / 2), S1 + GW / 2, "nw", 2),
    (S1 + GW / 2, -(S1 + GW / 2), "se", 1),
    (-(S1 + GW / 2), -(S1 + GW / 2), "sw", 3),
]:
    UA.place_shrub_belt2(
        f"shr_corner_{sfx}", (cx, cy), C_shrub, scale=2.0, shrub_idx=si
    )

# ─── FLOWER BEDS ──────────────────────────────────────────────────────────────
print("[scene] Building flower beds…")
flower_spots = [
    (S1 + GW / 2, 11.0, 0),
    (S1 + GW / 2, 28.0, 7),
    (-(S1 + GW / 2), 8.0, 3),
    (-(S1 + GW / 2), 21.0, 11),
    (11.0, S1 + GW / 2, 5),
    (22.0, S1 + GW / 2, 9),
    (-11.0, S1 + GW / 2, 13),
    (-22.0, S1 + GW / 2, 2),
]
for i, (fx, fy, seed) in enumerate(flower_spots):
    UA.build_flowerbed(f"fb{i}", fx, fy, C_flow, w=1.4, d=0.65, seed=seed)

# ─── REAL VEHICLES (Fiat Ducato) ──────────────────────────────────────────────
# Van front faces +X in source.
#   +π/2 → north (+Y)    −π/2 → south (−Y)
#   0    → east  (+X)     π   → west  (−X)
print("[scene] Importing Fiat Ducato vehicles (real openx assets)…")

# Right lane for each travel direction (right-hand traffic, China)
UA.place_vehicle("v1", (2.8, 20.0), C_cars, yaw=math.pi / 2)  # northbound
UA.place_vehicle("v2", (2.8, 35.0), C_cars, yaw=math.pi / 2)  # northbound (2nd)
UA.place_vehicle("v3", (-2.8, -25.0), C_cars, yaw=-math.pi / 2)  # southbound
UA.place_vehicle("v4", (22.0, -2.8), C_cars, yaw=0.0)  # eastbound
UA.place_vehicle("v5", (-30.0, 2.8), C_cars, yaw=math.pi)  # westbound

# ─── HOUSES (Flat, single-story Chinese bungalows) ────────────────────────────
print("[scene] Building houses…")
# House A: NE quadrant, set back from road ~12 m beyond green belt
UA.build_house(
    "A",
    22.0,
    26.0,
    C_house,
    w=14.0,
    d=9.0,
    wall_h=3.4,
    yaw=-math.pi / 2,
    mat_wall=M["wall"],
    mat_roof=M["roof_flat"],
    n_win_front=4,
)

# House B: SW quadrant
UA.build_house(
    "B",
    -20.0,
    -24.0,
    C_house,
    w=12.0,
    d=8.0,
    wall_h=3.2,
    yaw=math.pi / 2,
    mat_wall=M["wall2"],
    mat_roof=M["roof_tile"],
    n_win_front=3,
)

# ─── LIGHTING ─────────────────────────────────────────────────────────────────
print("[scene] Setting up lighting…")
UA.build_world_lighting()


# ─── CAMERAS ──────────────────────────────────────────────────────────────────
def make_cam(name, loc, look_at, lens=50, fstop=None):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    if fstop:
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = fstop
    obj = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = Vector(loc)
    direction = Vector(look_at) - Vector(loc)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


CAMS = {
    # Wide elevated overview of the full crossroads
    "overview": make_cam(
        "CAM_Overview", loc=(-42, -60, 45), look_at=(2, 0, 1.5), lens=28
    ),
    # Driver's-eye view: southbound approaching intersection from north arm
    "intersection": make_cam(
        "CAM_Intersection", loc=(0.5, 42, 2.8), look_at=(0, 10, 5.5), lens=50
    ),
    # North arm pedestrian view looking south toward intersection with assets
    "northarm": make_cam(
        "CAM_NorthArm", loc=(-8.0, 40.0, 2.0), look_at=(5.5, 15.0, 2.0), lens=50
    ),
    # East arm: bicycle station and street furniture
    "eastarm": make_cam(
        "CAM_EastArm",
        loc=(6.0, -12.0, 2.5),
        look_at=(26.0, 5.5, 2.2),
        lens=70,
        fstop=4.0,
    ),
}

# ─── COMPOSITOR ───────────────────────────────────────────────────────────────
bpy.context.scene.use_nodes = True
nt = bpy.context.scene.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
rl = nt.nodes.new("CompositorNodeRLayers")
gla = nt.nodes.new("CompositorNodeGlare")
out = nt.nodes.new("CompositorNodeComposite")
gla.glare_type = "FOG_GLOW"
gla.quality = "HIGH"
gla.threshold = 0.90
gla.mix = -0.60
gla.size = 7
nt.links.new(rl.outputs["Image"], gla.inputs["Image"])
nt.links.new(gla.outputs["Image"], out.inputs["Image"])

# ─── RENDER CONFIG ────────────────────────────────────────────────────────────
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.film_transparent = False

prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("OPTIX", "CUDA", "HIP", "METAL"):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        if any(d.type != "CPU" for d in prefs.devices):
            for d in prefs.devices:
                d.use = True
            sc.cycles.device = "GPU"
            print(f"[render] GPU {dev_type} enabled")
            break
    except Exception:
        pass
else:
    sc.cycles.device = "CPU"
    print("[render] CPU fallback")

sc.cycles.samples = 512
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.denoising_use_gpu = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Base Contrast"
sc.view_settings.exposure = -0.6

# ─── SAVE BLEND ───────────────────────────────────────────────────────────────
blend_path = str(OUT / "crossroads.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[scene] Saved: {blend_path}")


# ─── RENDER STILLS ────────────────────────────────────────────────────────────
def render_cam(cam_obj, png_name, samples=512):
    sc.cycles.samples = samples
    sc.camera = cam_obj
    sc.render.filepath = str(OUT / png_name)
    bpy.ops.render.render(write_still=True)
    print(f"[render] → {sc.render.filepath}")


print("[render] Starting 4 renders…")
render_cam(CAMS["overview"], "overview.png", samples=512)
render_cam(CAMS["intersection"], "intersection.png", samples=512)
render_cam(CAMS["northarm"], "northarm.png", samples=512)
render_cam(CAMS["eastarm"], "eastarm.png", samples=512)

print("[done] All renders complete →", OUT)
