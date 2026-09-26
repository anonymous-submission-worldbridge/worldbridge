"""
generate_urban_v3_all2.py
=========================
Photo-realistic outdoor street scene using all pre-built urban_v3 assets.

Assets imported directly from their existing .blend files:
  traffic_lights3 | busstop | bench+bin | kiosk5 | sharedbicycle4 | phonebooth3 | streetlight

Procedural elements: road, sidewalk, green belt, trees, flower beds, cars (sedans), houses (flat buildings).

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all2/
        street_scene.blend + overview.png + streetlevel.png + intersection.png + sidewalk.png
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
from mathutils import Vector

import urban_assets as UA

# ─── OUTPUT ───────────────────────────────────────────────────────────────────
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all2")
OUT.mkdir(parents=True, exist_ok=True)

# ─── SCENE SETUP ──────────────────────────────────────────────────────────────
UA.reset_scene()
UA.build_all_materials()
M = UA.M


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
C_trees = C("Trees")
C_flow = C("FlowerBeds")
C_cars = C("Cars")
C_house = C("Houses")

# ─── SCENE GEOMETRY ───────────────────────────────────────────────────────────
print("[scene] Building road, sidewalks, green belts…")
UA.build_road(C_road)
UA.build_sidewalks(C_sw)
UA.build_green_belts(C_green)

# Ground setback planes (between green belt and houses)
for sign, sfx in [(1, "r"), (-1, "l")]:
    gx = (UA.ROAD_X2 if sign > 0 else UA.ROAD_X1) + sign * (UA.SIDEW_W + UA.GREEN_W)
    cx = gx + sign * 5.0
    UA._box(
        f"setback_{sfx}", cx, 0, -0.01, 10.0, UA.ROAD_LEN, 0.02, M["sidewalk"], C_sw
    )

# ─── TRAFFIC LIGHT ────────────────────────────────────────────────────────────
print("[scene] Placing traffic light…")
UA.place_trafficlight((0.0, -30.0), C_tl)

# ─── BUS STOP ─────────────────────────────────────────────────────────────────
print("[scene] Placing bus stop…")
UA.place_busstop((5.5, -18.0), C_bs, yaw=-math.pi / 2)

# ─── BENCH + BIN ──────────────────────────────────────────────────────────────
print("[scene] Placing bench and bin…")
UA.place_bench_classic((6.2, -9.0), C_furn, yaw=-math.pi / 2)
UA.place_bin_domed((6.2, -6.0), C_furn)

# ─── PHONE BOOTH ──────────────────────────────────────────────────────────────
print("[scene] Placing phone booth…")
UA.place_phonebooth((5.5, 2.0), C_phone, yaw=-math.pi / 2)

# ─── KIOSK ────────────────────────────────────────────────────────────────────
print("[scene] Placing kiosk…")
UA.place_kiosk5((6.5, 12.0), C_kiosk, yaw=-math.pi / 2)

# ─── BICYCLE STATION ──────────────────────────────────────────────────────────
print("[scene] Placing bicycle station…")
UA.place_bicycle_station((6.0, 24.0), C_bike, yaw=0.0)

# ─── STREET LAMPS ─────────────────────────────────────────────────────────────
print("[scene] Placing street lamps…")
lamp_ys_r = (-37, -25, -13, -1, 11, 23, 35)
lamp_ys_l = (-33, -21, -9, 3, 15, 27)

for y in lamp_ys_r:
    UA.place_streetlight((5.0, float(y)), C_lamp, yaw=+math.pi / 2)
for y in lamp_ys_l:
    UA.place_streetlight((-5.0, float(y)), C_lamp, yaw=-math.pi / 2)

# ─── TREES ────────────────────────────────────────────────────────────────────
print("[scene] Planting trees…")
tree_ys_r = (-38, -29, -21, -13, -5, 5, 15, 25, 36)
tree_ys_l = (-35, -27, -19, -11, -3, 7, 17, 27)

for i, y in enumerate(tree_ys_r):
    h = 2.6 + (i % 3) * 0.3
    r = 2.0 + (i % 2) * 0.4
    UA.build_tree(f"tr{i}", 8.3, float(y), C_trees, trunk_h=h, canopy_r=r)
for i, y in enumerate(tree_ys_l):
    h = 2.5 + (i % 3) * 0.35
    r = 1.9 + (i % 2) * 0.35
    UA.build_tree(f"tl{i}", -8.3, float(y), C_trees, trunk_h=h, canopy_r=r)

# ─── FLOWER BEDS ──────────────────────────────────────────────────────────────
print("[scene] Building flower beds…")
flower_ys_r = (-33, -25, -17, -8, 1, 9, 19, 29)
flower_ys_l = (-31, -23, -15, -7, 2, 12)

for i, y in enumerate(flower_ys_r):
    UA.build_flowerbed(f"fr{i}", 8.3, float(y), C_flow, w=1.6, d=0.70, seed=i * 7)
for i, y in enumerate(flower_ys_l):
    UA.build_flowerbed(f"fl{i}", -8.3, float(y), C_flow, w=1.6, d=0.70, seed=i * 13 + 5)

# ─── CARS ─────────────────────────────────────────────────────────────────────
print("[scene] Adding cars…")
# Right lane (heading +Y = default yaw=0)
UA.build_car("a", 2.0, -10.0, C_cars, yaw=0.0, mat_body=M["car_paint"])
UA.build_car(
    "c",
    2.0,
    18.0,
    C_cars,
    yaw=0.0,
    mat_body=UA._pbr("car_dark", (0.04, 0.04, 0.06), rough=0.18, metal=0.05),
)
# Left lane (heading -Y → yaw = π)
UA.build_car("b", -2.0, 4.0, C_cars, yaw=math.pi, mat_body=M["car_paint2"])

# ─── HOUSES (Hutongs) ────────────────────────────────────────────────────────────
print("[scene] Building houses…")
# Right bungalow: front faces -X (toward road), yaw=-π/2
UA.build_house(
    "right",
    18.0,
    8.0,
    C_house,
    w=15.0,
    d=8.0,
    wall_h=3.4,
    yaw=-math.pi / 2,
    mat_wall=M["wall"],
    mat_roof=M["roof_flat"],
    n_win_front=4,
)

# Left bungalow: front faces +X (toward road), yaw=+π/2
UA.build_house(
    "left",
    -17.0,
    -3.0,
    C_house,
    w=12.0,
    d=7.5,
    wall_h=3.2,
    yaw=+math.pi / 2,
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
    obj.location = loc
    obj.rotation_euler = (
        (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    return obj


CAMS = {
    # Wide elevated overview of the whole street
    "overview": make_cam(
        "CAM_Overview", loc=(-28, -46, 30), look_at=(2, -5, 1.5), lens=28
    ),
    # Pedestrian-level looking along the sidewalk
    "street": make_cam(
        "CAM_Street", loc=(0.5, -36, 1.72), look_at=(4.8, -5, 1.55), lens=50
    ),
    # Intersection — driver's view up the road at the gantry
    "cross": make_cam(
        "CAM_Intersection", loc=(0.5, -40, 2.8), look_at=(0, -28, 6.5), lens=50
    ),
    # Bus stop + sidewalk detail
    "busstop": make_cam(
        "CAM_BusStop", loc=(0.0, -26, 2.0), look_at=(5.5, -18, 2.6), lens=85, fstop=3.5
    ),
}

# ─── COMPOSITOR (fog glow) ────────────────────────────────────────────────────
bpy.context.scene.use_nodes = True
nt = bpy.context.scene.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
rl = nt.nodes.new("CompositorNodeRLayers")
gla = nt.nodes.new("CompositorNodeGlare")
out = nt.nodes.new("CompositorNodeComposite")
gla.glare_type = "FOG_GLOW"
gla.quality = "HIGH"
gla.threshold = 0.92
gla.mix = -0.65
gla.size = 7
nt.links.new(rl.outputs["Image"], gla.inputs["Image"])
nt.links.new(gla.outputs["Image"], out.inputs["Image"])

# ─── RENDER CONFIG ────────────────────────────────────────────────────────────
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.film_transparent = False

# GPU: OPTIX → CUDA → HIP → CPU fallback
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
try:
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
    print("[render] GPU OPTIX enabled")
except Exception as e:
    try:
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
        print("[render] GPU CUDA enabled")
    except Exception:
        sc.cycles.device = "CPU"
        print(f"[render] CPU fallback: {e}")

sc.cycles.samples = 512
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.denoising_use_gpu = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Base Contrast"
sc.view_settings.exposure = -0.6

# ─── SAVE BLEND ───────────────────────────────────────────────────────────────
blend_path = str(OUT / "street_scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[scene] Saved: {blend_path}")


# ─── RENDER STILLS ────────────────────────────────────────────────────────────
def render_cam(cam_obj, png_name, samples=512):
    sc.cycles.samples = samples
    sc.camera = cam_obj
    sc.render.filepath = str(OUT / png_name)
    bpy.ops.render.render(write_still=True)
    print(f"[render] → {sc.render.filepath}")


print("[render] Starting renders…")
render_cam(CAMS["overview"], "overview.png", samples=512)
render_cam(CAMS["street"], "streetlevel.png", samples=512)
render_cam(CAMS["cross"], "intersection.png", samples=512)
render_cam(CAMS["busstop"], "busstop_detail.png", samples=512)

print("[done] All renders complete →", OUT)
