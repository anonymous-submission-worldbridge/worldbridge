"""
Create urban_v3_all25 from urban_v3_all18 with the inner flower-ground expanded.

The all18 park shows two ground treatments: an inner flower-like groundcover
surface and an outer green strip.  This pass expands the inner flower-ground
treatment to the whole park quadrant and hides the old split ground surfaces so
the outer green strip cannot remain visible.
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
OUT = ROOT / "infinigen/outputs/urban_v3_all25"
OUT.mkdir(parents=True, exist_ok=True)

S1 = 7.0
FW = 2.5
G1 = S1 + FW
ARM = 52.0
PARK_X0 = G1 - 0.15
PARK_X1 = G1 + ARM + 0.15
PARK_Y0 = G1 - 0.15
PARK_Y1 = G1 + ARM + 0.15
# Slight visual overrun prevents any original pale-green ring from peeking out
# at the park camera edges while hardscape/road objects remain above it.
COVER_X0 = PARK_X0 - 0.85
COVER_X1 = PARK_X1 + 0.85
COVER_Y0 = PARK_Y0 - 0.85
COVER_Y1 = PARK_Y1 + 0.85
PARK_CX = (PARK_X0 + PARK_X1) / 2.0
PARK_CY = (PARK_Y0 + PARK_Y1) / 2.0

MARBLE_RADIUS = 5.65
PERGOLA_Y = 47.5
PERGOLA_XS = (25.5, 35.5, 45.5)
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


def flat_mat(name, color, roughness=0.78, emission=None, strength=0.0):
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
    if emission is not None:
        set_input(bsdf, "Emission Color", (*emission, 1.0))
        set_input(bsdf, "Emission Strength", strength)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def full_surface(name, x0, x1, y0, y1, z, mat, coll, step=1.35):
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
    obj.data.materials.append(mat)
    uv_layer = obj.data.uv_layers.new(name="UVMap")
    for poly in obj.data.polygons:
        for loop_index in poly.loop_indices:
            vx, vy, _vz = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
            uv_layer.data[loop_index].uv = ((vx - x0) / 7.5, (vy - y0) / 7.5)

    link_only_to_coll(obj, coll)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.visible_camera = True
    return obj


def hide_split_ground_surfaces():
    hidden = 0
    prefixes = (
        "park_lawn_grid",
        "a18_park_old_grass_full_quadrant",
        "a22_park_flowerbed_full_quadrant",
        "a22_park_continuous_turf_full_quadrant",
        "a22_short_turf",
        "a23_park_flower_ground_full_quadrant",
        "a23_full_flower_ground_detail",
        "a24_park_continuous_flowergrass_ground",
        "a24_continuous_flowergrass_detail",
        "a25_inner_flower_ground_full_park",
        "a25_inner_flower_ground_detail",
    )
    for obj in bpy.data.objects:
        if obj.name.startswith(prefixes):
            obj.hide_render = True
            obj.hide_viewport = True
            obj.visible_camera = False
            hidden += 1
    return hidden


def source_flower_ground_material():
    # In all18 the desired central flower-like ground is the imported all8 park
    # lawn material. Prefer the smaller inner grid object over the outer all13
    # pale-green strip, then fall back by material name.
    for obj_name in ("park_lawn_grid.001", "park_lawn_grid.002", "park_lawn_grid"):
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.name == "a8_grass_park":
                return mat
    mat = bpy.data.materials.get("a8_grass_park")
    if mat is not None:
        return mat
    inner = bpy.data.objects.get("park_lawn_grid.001")
    if (
        inner is not None
        and inner.material_slots
        and inner.material_slots[0].material is not None
    ):
        return inner.material_slots[0].material
    raise RuntimeError(
        "Could not find all18 inner flower-ground material a8_grass_park"
    )


def clear_for_flower_detail(x, y):
    if not (
        PARK_X0 + 0.45 <= x <= PARK_X1 - 0.45 and PARK_Y0 + 0.45 <= y <= PARK_Y1 - 0.45
    ):
        return False
    if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_RADIUS + 0.65:
        return False
    if abs(x - PARK_CX) < 1.35:
        return False
    if abs(y - PARK_CY) < 1.35:
        return False
    if 17.5 <= x <= 53.5 and abs(y - PERGOLA_Y) < 1.05:
        return False
    if any(math.hypot(x - px, y - PERGOLA_Y) < 2.15 for px in PERGOLA_XS):
        return False
    if any(math.hypot(x - bx, y - by) < 1.35 for bx, by in BENCH_POINTS):
        return False
    return True


def add_full_flower_ground_detail(coll):
    old = bpy.data.objects.get("a25_inner_flower_ground_detail")
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    mats = [
        flat_mat("a25_inner_flower_leaf_dark", (0.050, 0.200, 0.040), 0.82),
        flat_mat("a25_inner_flower_leaf_mid", (0.105, 0.320, 0.060), 0.82),
        flat_mat(
            "a25_inner_flower_yellow",
            (0.94, 0.78, 0.07),
            0.58,
            (0.94, 0.78, 0.07),
            0.05,
        ),
        flat_mat("a25_inner_flower_white", (0.92, 0.90, 0.82), 0.58),
        flat_mat("a25_inner_flower_pink", (0.78, 0.28, 0.54), 0.58),
        flat_mat("a25_inner_flower_blue", (0.30, 0.42, 0.78), 0.60),
    ]
    rng = random.Random(2525)
    verts = []
    faces = []
    mat_indices = []

    x = PARK_X0 + 0.50
    while x <= PARK_X1 - 0.50:
        y = PARK_Y0 + 0.50
        while y <= PARK_Y1 - 0.50:
            gx = x + rng.uniform(-0.23, 0.23)
            gy = y + rng.uniform(-0.23, 0.23)
            if clear_for_flower_detail(gx, gy):
                for _ in range(3):
                    ang = rng.uniform(0.0, math.tau)
                    width = rng.uniform(0.045, 0.085)
                    height = rng.uniform(0.13, 0.28)
                    lean = rng.uniform(0.015, 0.060)
                    dx = math.cos(ang) * width
                    dy = math.sin(ang) * width
                    lx = math.cos(ang + math.pi / 2) * lean
                    ly = math.sin(ang + math.pi / 2) * lean
                    base = len(verts)
                    verts.extend(
                        [
                            (gx - dx, gy - dy, 0.031),
                            (gx + dx, gy + dy, 0.031),
                            (gx + lx, gy + ly, 0.031 + height),
                        ]
                    )
                    faces.append((base, base + 1, base + 2))
                    mat_indices.append(rng.randrange(2))

                if rng.random() < 0.46:
                    rad = rng.uniform(0.052, 0.095)
                    z = rng.uniform(0.135, 0.225)
                    flower_mat_index = 2 + rng.randrange(4)
                    for petal in range(4):
                        ang = petal * math.pi / 2 + rng.uniform(-0.20, 0.20)
                        cx = gx + math.cos(ang) * rad * 0.45
                        cy = gy + math.sin(ang) * rad * 0.45
                        base = len(verts)
                        verts.extend(
                            [
                                (gx, gy, z),
                                (
                                    cx + math.cos(ang) * rad,
                                    cy + math.sin(ang) * rad,
                                    z + 0.004,
                                ),
                                (
                                    cx + math.cos(ang + 1.8) * rad * 0.45,
                                    cy + math.sin(ang + 1.8) * rad * 0.45,
                                    z,
                                ),
                            ]
                        )
                        faces.append((base, base + 1, base + 2))
                        mat_indices.append(flower_mat_index)
            y += 0.58
        x += 0.58

    mesh = bpy.data.meshes.new("a25_inner_flower_ground_detail_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("a25_inner_flower_ground_detail", mesh)
    for mat in mats:
        obj.data.materials.append(mat)
    for poly, mat_index in zip(obj.data.polygons, mat_indices):
        poly.material_index = mat_index
    link_only_to_coll(obj, coll)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.visible_camera = True
    print(
        f"[all25] Added full inner flower-ground detail faces={len(faces)}", flush=True
    )
    return obj


def ensure_cycles_color_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 192
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


print("[all25] Opening all18 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park = get_coll("Park")

mat = source_flower_ground_material()
hidden = hide_split_ground_surfaces()
surface = full_surface(
    "a25_inner_flower_ground_full_park",
    COVER_X0,
    COVER_X1,
    COVER_Y0,
    COVER_Y1,
    0.018,
    mat,
    park,
)
add_full_flower_ground_detail(park)
print(
    "[all25] Expanded all18 inner flower-ground treatment to full park "
    f"bbox=({COVER_X0:.2f},{COVER_X1:.2f},{COVER_Y0:.2f},{COVER_Y1:.2f}); "
    f"hidden split ground objects={hidden}; inner material={mat.name}",
    flush=True,
)

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all25.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all25] Blend saved: {out_blend}", flush=True)

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
        print(f"[all25] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all25] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all25] Done: {filename}", flush=True)

print("[all25] All complete.", flush=True)
