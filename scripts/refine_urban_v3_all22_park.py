"""
Create urban_v3_all22 from urban_v3_all18 with a strict continuous-turf park fix.

The park ground must read as one uninterrupted green lawn base.  This pass hides
the previous flower/soil and outer-green ground treatments, adds a full-quadrant
short-turf surface, and scatters only low grass-blade detail outside paths,
plazas, pergolas, sculpture pads, and bench keepout areas.
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


from pathlib import Path
import math
import random

import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all18/urban_v3_all18.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all22"
OUT.mkdir(parents=True, exist_ok=True)

S1 = 7.0
FW = 2.5
G1 = S1 + FW
ARM = 52.0
PARK_X0 = G1 - 0.15
PARK_X1 = G1 + ARM + 0.15
PARK_Y0 = G1 - 0.15
PARK_Y1 = G1 + ARM + 0.15
PARK_CX = (PARK_X0 + PARK_X1) / 2.0
PARK_CY = (PARK_Y0 + PARK_Y1) / 2.0
MARBLE_RADIUS = 5.65
PERGOLA_Y = PARK_CY + 12.0
PERGOLA_X0 = 18.0
PERGOLA_X1 = 53.0
BENCH_POINTS = (
    (27.0, 32.0),
    (44.0, 32.0),
    (31.0, 39.2),
    (40.0, 39.2),
    (24.0, 52.2),
    (35.5, 52.2),
    (47.0, 52.2),
    (20.0, 45.2),
    (51.0, 45.2),
    (18.0, 24.0),
    (30.0, 18.0),
    (42.0, 18.0),
    (55.0, 24.0),
    (15.0, 36.0),
    (56.5, 36.0),
)


def get_coll(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_only_to_coll(obj, coll):
    for old in list(obj.users_collection):
        try:
            old.objects.unlink(obj)
        except RuntimeError:
            pass
    try:
        coll.objects.link(obj)
    except RuntimeError:
        pass
    return obj


def set_input(node, name, value):
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def continuous_turf_mat(name="a22_continuous_short_turf"):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 28.0
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.58
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.045, 0.175, 0.035, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.120, 0.355, 0.070, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.075

    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_input(bsdf, "Roughness", 0.96)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def flat_mat(name, color, roughness=0.92):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(bsdf, "Base Color", (*color, 1.0))
    set_input(bsdf, "Roughness", roughness)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def full_surface(name, x0, x1, y0, y1, z, mat, coll, step=1.85):
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    nx = max(1, math.ceil((x1 - x0) / step))
    ny = max(1, math.ceil((y1 - y0) / step))
    verts = []
    for ix in range(nx + 1):
        x = x0 + (x1 - x0) * ix / nx
        for iy in range(ny + 1):
            y = y0 + (y1 - y0) * iy / ny
            verts.append((x, y, z))

    faces = []
    for ix in range(nx):
        for iy in range(ny):
            a = ix * (ny + 1) + iy
            faces.append((a, a + 1, a + ny + 2, a + ny + 1))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    if mat is not None:
        obj.data.materials.append(mat)

    uv_layer = obj.data.uv_layers.new(name="UVMap")
    for poly in obj.data.polygons:
        for loop_index in poly.loop_indices:
            vx, vy, _vz = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
            uv_layer.data[loop_index].uv = ((vx - x0) / 8.0, (vy - y0) / 8.0)

    link_only_to_coll(obj, coll)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.visible_camera = True
    return obj


def is_clear_for_short_grass(x, y):
    if not (
        PARK_X0 + 0.45 <= x <= PARK_X1 - 0.45 and PARK_Y0 + 0.45 <= y <= PARK_Y1 - 0.45
    ):
        return False
    if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_RADIUS + 0.85:
        return False
    if abs(x - PARK_CX) < 1.55 and PARK_Y0 <= y <= PARK_Y1:
        return False
    if abs(y - PARK_CY) < 1.55 and PARK_X0 <= x <= PARK_X1:
        return False
    if PERGOLA_X0 - 0.75 <= x <= PERGOLA_X1 + 0.75 and abs(y - PERGOLA_Y) < 1.35:
        return False
    for bx, by in BENCH_POINTS:
        if math.hypot(x - bx, y - by) < 1.45:
            return False
    return True


def add_short_grass_detail(coll):
    old = bpy.data.objects.get("a22_short_turf_blade_detail")
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    mats = [
        flat_mat("a22_short_turf_blade_dark", (0.038, 0.165, 0.032)),
        flat_mat("a22_short_turf_blade_mid", (0.075, 0.260, 0.048)),
        flat_mat("a22_short_turf_blade_light", (0.115, 0.340, 0.070)),
    ]
    verts = []
    faces = []
    mat_indices = []
    rng = random.Random(2227)

    x = PARK_X0 + 0.55
    while x <= PARK_X1 - 0.55:
        y = PARK_Y0 + 0.55
        while y <= PARK_Y1 - 0.55:
            gx = x + rng.uniform(-0.22, 0.22)
            gy = y + rng.uniform(-0.22, 0.22)
            if is_clear_for_short_grass(gx, gy):
                for _ in range(3):
                    ang = rng.uniform(0.0, math.tau)
                    width = rng.uniform(0.030, 0.055)
                    height = rng.uniform(0.075, 0.155)
                    lean = rng.uniform(0.010, 0.045)
                    dx = math.cos(ang) * width
                    dy = math.sin(ang) * width
                    lx = math.cos(ang + math.pi / 2) * lean
                    ly = math.sin(ang + math.pi / 2) * lean
                    base = len(verts)
                    verts.extend(
                        [
                            (gx - dx, gy - dy, 0.026),
                            (gx + dx, gy + dy, 0.026),
                            (gx + lx, gy + ly, 0.026 + height),
                        ]
                    )
                    faces.append((base, base + 1, base + 2))
                    mat_indices.append(rng.randrange(len(mats)))
            y += 0.55
        x += 0.55

    mesh = bpy.data.meshes.new("a22_short_turf_blade_detail_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("a22_short_turf_blade_detail", mesh)
    for mat in mats:
        obj.data.materials.append(mat)
    for poly, idx in zip(obj.data.polygons, mat_indices):
        poly.material_index = idx
    link_only_to_coll(obj, coll)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.visible_camera = True
    print(f"[all22] Added continuous short-grass detail faces={len(faces)}", flush=True)
    return obj


def hide_previous_park_ground_and_flowers(park):
    hidden = 0
    prefixes = (
        "park_lawn_grid",
        "a18_park_old_grass_full_quadrant",
        "a22_park_flowerbed_full_quadrant",
        "a22_park_continuous_turf_full_quadrant",
        "a18_grass_flower",
        "a18_flower_proto",
        "pfb",
        "pk_fl",
    )
    terms = ("flowerplant", "blossom")
    candidates = set(obj for obj in bpy.data.objects if obj.name.startswith(prefixes))
    candidates.update(park.all_objects)
    candidates.update(
        obj
        for obj in bpy.data.objects
        if PARK_X0 - 2.0 <= obj.location.x <= PARK_X1 + 2.0
        and PARK_Y0 - 2.0 <= obj.location.y <= PARK_Y1 + 2.0
    )
    for obj in candidates:
        lower = obj.name.lower()
        if obj.name.startswith(prefixes) or any(term in lower for term in terms):
            obj.hide_render = True
            obj.hide_viewport = True
            obj.visible_camera = False
            hidden += 1
    print(
        f"[all22] Hidden previous split/flower groundcover objects={hidden}", flush=True
    )
    return hidden


def ensure_cycles_color_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 192
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.film_transparent = False
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


print("[all22] Opening all18 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park = get_coll("Park")

hidden = hide_previous_park_ground_and_flowers(park)
turf_mat = continuous_turf_mat()

surface = full_surface(
    "a22_park_continuous_turf_full_quadrant",
    PARK_X0,
    PARK_X1,
    PARK_Y0,
    PARK_Y1,
    0.018,
    turf_mat,
    park,
    step=1.35,
)
add_short_grass_detail(park)
print(
    "[all22] Replaced split park ground with continuous short turf "
    f"bbox=({PARK_X0:.2f},{PARK_X1:.2f},{PARK_Y0:.2f},{PARK_Y1:.2f}); "
    f"hidden previous groundcover objects={hidden}; material={turf_mat.name}",
    flush=True,
)

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all22.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all22] Blend saved: {out_blend}", flush=True)

cameras = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]

scene = bpy.context.scene
for cam_name, filename in cameras:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all22] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all22] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all22] Done: {filename}", flush=True)

print("[all22] All complete.", flush=True)
