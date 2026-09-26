"""
Create urban_v3_all24 from urban_v3_all18 with one continuous flower-grass park ground.

The park ground should not read as separate inner/outer zones, tree pits, bare
soil, or local flower patches.  This pass first lays down one complete
flower-grass ground plane across the full park boundary, hides older split
ground/soil/flowerbed surfaces, then keeps hardscape and park furniture above
that continuous base.
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
OUT = ROOT / "infinigen/outputs/urban_v3_all24"
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


def continuous_flowergrass_mat(name="a24_continuous_flowergrass_ground"):
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
    noise.inputs["Scale"].default_value = 24.0
    noise.inputs["Detail"].default_value = 15.0
    noise.inputs["Roughness"].default_value = 0.64
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.16
    ramp.color_ramp.elements[0].color = (0.105, 0.125, 0.040, 1.0)
    mid = ramp.color_ramp.elements.new(0.55)
    mid.color = (0.185, 0.260, 0.070, 1.0)
    ramp.color_ramp.elements[2].position = 1.0
    ramp.color_ramp.elements[2].color = (0.330, 0.305, 0.110, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.050
    bump.inputs["Distance"].default_value = 0.070

    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_input(bsdf, "Roughness", 0.94)
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


def world_bbox(obj):
    from mathutils import Vector

    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def overlaps_park(obj, margin=1.50):
    if obj.type != "MESH":
        return False
    x0, x1, y0, y1, _z0, _z1 = world_bbox(obj)
    return (
        x1 >= PARK_X0 - margin
        and x0 <= PARK_X1 + margin
        and y1 >= PARK_Y0 - margin
        and y0 <= PARK_Y1 + margin
    )


def hide_conflicting_park_ground():
    hidden = 0
    prefixes = (
        "park_lawn_grid",
        "a18_park_old_grass_full_quadrant",
        "a18_grass_flower",
        "a18_flower_proto",
        "a19_",
        "a20_",
        "a21_full_old_grass",
        "a22_park_flowerbed_full_quadrant",
        "a22_park_continuous_turf_full_quadrant",
        "a22_short_turf",
        "a23_park_flower_ground_full_quadrant",
        "a23_full_flower_ground_detail",
        "all8veg_scatter:FlowerPlantFactory",
        "all8veg_scatter:GrassTuftFactory",
        "FlowerPlantFactory",
        "GrassTuftFactory",
        "pfb",
        "pk_fl",
    )
    hardscape_terms = (
        "path",
        "plaza",
        "marble",
        "pergola",
        "pavilion",
        "pav_",
        "bench",
        "knot",
        "sculpt",
        "road",
        "sidewalk",
        "stone",
    )
    ground_terms = (
        "lawn",
        "grass",
        "soil",
        "mulch",
        "ground",
        "flowerbed",
        "flower",
        "blossom",
        "treepit",
        "tree_pit",
        "tree_pool",
        "tree_ring",
        "tr_pt",
    )

    for obj in bpy.data.objects:
        if obj.name.startswith("a24_"):
            continue
        lower = obj.name.lower()
        mats = " ".join(
            slot.material.name.lower()
            for slot in obj.material_slots
            if slot.material is not None
        )
        should_hide = obj.name.startswith(prefixes)
        if not should_hide and overlaps_park(obj):
            _x0, _x1, _y0, _y1, z0, z1 = world_bbox(obj)
            is_low_ground = z1 <= 0.36 and z0 <= 0.12
            looks_ground = any(term in lower or term in mats for term in ground_terms)
            is_hardscape = any(
                term in lower or term in mats for term in hardscape_terms
            )
            should_hide = is_low_ground and looks_ground and not is_hardscape
        if should_hide:
            obj.hide_render = True
            obj.hide_viewport = True
            obj.visible_camera = False
            hidden += 1
    return hidden


def source_flower_ground_material():
    return continuous_flowergrass_mat()


def clear_for_flower_detail(x, y):
    if not (
        PARK_X0 + 0.18 <= x <= PARK_X1 - 0.18 and PARK_Y0 + 0.18 <= y <= PARK_Y1 - 0.18
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
    old = bpy.data.objects.get("a24_continuous_flowergrass_detail")
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    mats = [
        flat_mat("a24_flowergrass_leaf_dark", (0.060, 0.185, 0.035), 0.84),
        flat_mat("a24_flowergrass_leaf_mid", (0.115, 0.285, 0.055), 0.84),
        flat_mat("a24_flowergrass_leaf_olive", (0.230, 0.260, 0.070), 0.86),
        flat_mat(
            "a24_flowergrass_yellow", (0.94, 0.78, 0.07), 0.58, (0.94, 0.78, 0.07), 0.05
        ),
        flat_mat("a24_flowergrass_white", (0.92, 0.90, 0.82), 0.58),
        flat_mat("a24_flowergrass_pink", (0.78, 0.28, 0.54), 0.58),
        flat_mat("a24_flowergrass_blue", (0.30, 0.42, 0.78), 0.60),
    ]
    rng = random.Random(2424)
    verts = []
    faces = []
    mat_indices = []

    x = PARK_X0 + 0.22
    while x <= PARK_X1 - 0.22:
        y = PARK_Y0 + 0.22
        while y <= PARK_Y1 - 0.22:
            gx = x + rng.uniform(-0.18, 0.18)
            gy = y + rng.uniform(-0.18, 0.18)
            if clear_for_flower_detail(gx, gy):
                for _ in range(4):
                    ang = rng.uniform(0.0, math.tau)
                    width = rng.uniform(0.040, 0.080)
                    height = rng.uniform(0.11, 0.24)
                    lean = rng.uniform(0.012, 0.052)
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
                    mat_indices.append(rng.randrange(3))

                if rng.random() < 0.58:
                    rad = rng.uniform(0.052, 0.095)
                    z = rng.uniform(0.135, 0.225)
                    flower_mat_index = 3 + rng.randrange(4)
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
            y += 0.46
        x += 0.46

    mesh = bpy.data.meshes.new("a24_continuous_flowergrass_detail_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("a24_continuous_flowergrass_detail", mesh)
    for mat in mats:
        obj.data.materials.append(mat)
    for poly, mat_index in zip(obj.data.polygons, mat_indices):
        poly.material_index = mat_index
    link_only_to_coll(obj, coll)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.visible_camera = True
    print(
        f"[all24] Added continuous flower-grass detail faces={len(faces)}", flush=True
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


print("[all24] Opening all18 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park = get_coll("Park")

mat = source_flower_ground_material()
hidden = hide_conflicting_park_ground()
surface = full_surface(
    "a24_park_continuous_flowergrass_ground",
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
    "[all24] Replaced park ground with one continuous flower-grass plane "
    f"bbox=({COVER_X0:.2f},{COVER_X1:.2f},{COVER_Y0:.2f},{COVER_Y1:.2f}); "
    f"hidden conflicting ground/tree-pit objects={hidden}; material={mat.name}",
    flush=True,
)

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all24.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all24] Blend saved: {out_blend}", flush=True)

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
        print(f"[all24] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all24] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all24] Done: {filename}", flush=True)

print("[all24] All complete.", flush=True)
