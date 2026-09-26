"""
Create urban_v3_all18 from urban_v3_all16 with park-only refinements.

Park requirements:
  - Old grass ground style covers the full park quadrant, with flowers and paths.
  - Center mirror-knot sculpture sits on a marble plaza patch.
  - Three pergolas are placed in one regular row.
  - More benches are planned, and benches are larger than the previous pass.
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
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all16/urban_v3_all16.blend"
ART_BLEND = ROOT / "infinigen/outputs/urban_v3_sculpture2/public_art.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all18"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
import urban_assets as UA  # noqa: E402

S1 = 7.0
FW = 2.5
G1 = S1 + FW
ARM = 52.0
PARK_X0 = G1
PARK_X1 = G1 + ARM
PARK_Y0 = G1
PARK_Y1 = G1 + ARM
PARK_CX = (PARK_X0 + PARK_X1) / 2
PARK_CY = (PARK_Y0 + PARK_Y1) / 2


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


def bbox_info(objects):
    pts = []
    for obj in objects:
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0))
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx, (mn + mx) * 0.5


def transform_group(objects, tx, ty, tz=0.0, yaw=0.0, scale=1.0):
    mn, _mx, center = bbox_info(objects)
    rot = Matrix.Rotation(yaw, 4, "Z")
    src_xy = Vector((center.x, center.y, 0.0))
    for obj in objects:
        rel = Vector((obj.location.x, obj.location.y, 0.0)) - src_xy
        nrel = rot @ rel
        obj.location.x = tx + nrel.x * scale
        obj.location.y = ty + nrel.y * scale
        obj.location.z = tz + (obj.location.z - mn.z) * scale
        obj.rotation_euler.z += yaw
        obj.scale = (obj.scale.x * scale, obj.scale.y * scale, obj.scale.z * scale)


def scale_group_about_center(objects, factor):
    _mn, _mx, center = bbox_info(objects)
    for obj in objects:
        obj.location.x = center.x + (obj.location.x - center.x) * factor
        obj.location.y = center.y + (obj.location.y - center.y) * factor
        obj.location.z = center.z + (obj.location.z - center.z) * factor
        obj.scale = (obj.scale.x * factor, obj.scale.y * factor, obj.scale.z * factor)


def append_prefix(prefix, target_coll, name_prefix):
    with bpy.data.libraries.load(str(ART_BLEND), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name.startswith(prefix)]
    objects = []
    for obj in dst.objects:
        if obj is None:
            continue
        obj.name = f"{name_prefix}_{obj.name}"
        link_only_to_coll(obj, target_coll)
        obj.hide_render = False
        obj.hide_viewport = False
        obj.visible_camera = True
        objects.append(obj)
    if not objects:
        raise RuntimeError(f"No objects loaded for prefix {prefix} from {ART_BLEND}")
    return objects


def mat_principled(name, rgb, rough=0.75, emit=None, emit_strength=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        if emit is not None and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emit_strength
    return mat


def mat_marble(name):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise = nodes.new("ShaderNodeTexNoise")
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-650, 0)
    noise.location = (-450, 0)
    ramp.location = (-230, 0)
    bsdf.location = (0, 0)
    out.location = (260, 0)
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.56
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (0.80, 0.80, 0.78, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.97, 0.96, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.40
    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def box(name, cx, cy, cz, dx, dy, dz, mat, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz), scale=(dx, dy, dz))
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    link_only_to_coll(obj, coll)
    return obj


def cyl(name, cx, cy, cz, radius, depth, mat, coll, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts,
        radius=radius,
        depth=depth,
        location=(cx, cy, cz + depth / 2),
        end_fill_type="NGON",
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    link_only_to_coll(obj, coll)
    return obj


def sph(name, cx, cy, cz, radius, mat, coll):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=8, ring_count=5, radius=radius, location=(cx, cy, cz)
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    link_only_to_coll(obj, coll)
    return obj


def remove_old_focal_and_benches(park):
    remove_prefixes = (
        "pav:",
        "band:",
        "ct_ring",
        "fnt_",
        "clbench:",
        "bin_domed:",
        "pk_plaza",
    )
    removed = 0
    for obj in list(park.all_objects):
        if obj.name.startswith(remove_prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(f"[all18] Removed old park focal/bench objects: {removed}", flush=True)


def expand_old_grass_ground(park):
    lawn = bpy.data.objects.get("park_lawn_grid")
    mat = None
    if (
        lawn is not None
        and lawn.material_slots
        and lawn.material_slots[0].material is not None
    ):
        mat = lawn.material_slots[0].material
        lawn.hide_render = True
        lawn.hide_viewport = True
    if mat is None:
        mat = bpy.data.materials.get("grass_park") or mat_principled(
            "grass_park", (0.08, 0.28, 0.04), 0.85
        )
    full_lawn = box(
        "a18_park_old_grass_full_quadrant",
        PARK_CX,
        PARK_CY,
        0.006,
        PARK_X1 - PARK_X0 + 0.30,
        PARK_Y1 - PARK_Y0 + 0.30,
        0.012,
        mat,
        park,
    )
    full_lawn.hide_render = False
    full_lawn.hide_viewport = False
    print(
        "[all18] Added old-grass material ground across full park quadrant", flush=True
    )


def add_walk_paths_and_marble_plaza(park):
    stone = bpy.data.materials.get("park_stone") or mat_principled(
        "park_stone", (0.64, 0.62, 0.56), 0.72
    )
    marble = mat_marble("a18_center_white_marble")
    seam = mat_principled("a18_marble_seam", (0.55, 0.56, 0.56), 0.78)
    border = mat_principled("a18_marble_border", (0.44, 0.44, 0.42), 0.72)

    box(
        "a18_path_center_ns",
        PARK_CX,
        PARK_CY,
        0.036,
        2.4,
        PARK_Y1 - PARK_Y0,
        0.030,
        stone,
        park,
    )
    box(
        "a18_path_center_ew",
        PARK_CX,
        PARK_CY,
        0.037,
        PARK_X1 - PARK_X0,
        2.4,
        0.030,
        stone,
        park,
    )
    box("a18_path_pergola_row", PARK_CX, 47.5, 0.038, 35.0, 2.0, 0.030, stone, park)

    cyl(
        "a18_center_marble_plaza",
        PARK_CX,
        PARK_CY,
        0.050,
        5.8,
        0.080,
        marble,
        park,
        verts=80,
    )
    cyl(
        "a18_center_marble_border",
        PARK_CX,
        PARK_CY,
        0.096,
        5.95,
        0.035,
        border,
        park,
        verts=80,
    )
    for i in range(4):
        yaw = i * math.pi / 4
        obj = box(
            f"a18_center_marble_seam_{i}",
            PARK_CX,
            PARK_CY,
            0.101,
            11.0,
            0.030,
            0.012,
            seam,
            park,
        )
        obj.rotation_euler.z = yaw
    print("[all18] Added walking paths and center marble sculpture plaza", flush=True)


def add_flower_detail(park):
    mats = {
        "leaf": bpy.data.materials.get("flower_leaf")
        or mat_principled("flower_leaf", (0.10, 0.30, 0.05), 0.78),
        "red": bpy.data.materials.get("flower_r")
        or mat_principled(
            "flower_r", (0.88, 0.18, 0.12), 0.60, (0.88, 0.18, 0.12), 0.10
        ),
        "yellow": bpy.data.materials.get("flower_y")
        or mat_principled(
            "flower_y", (0.95, 0.80, 0.10), 0.58, (0.95, 0.80, 0.10), 0.08
        ),
        "purple": bpy.data.materials.get("flower_p")
        or mat_principled("flower_p", (0.65, 0.20, 0.78), 0.58),
        "white": bpy.data.materials.get("flower_w")
        or mat_principled("flower_w", (0.92, 0.92, 0.88), 0.55),
    }
    flower_mats = [mats["red"], mats["yellow"], mats["purple"], mats["white"]]
    stem_proto = cyl(
        "a18_flower_proto_stem",
        -1000,
        -1000,
        0.06,
        0.006,
        0.16,
        mats["leaf"],
        park,
        verts=5,
    )
    flower_protos = [
        sph(f"a18_flower_proto_{i}", -1000, -1000, 0.22, 0.048, mat, park)
        for i, mat in enumerate(flower_mats)
    ]
    avoid = [
        (PARK_CX, PARK_CY, 7.5),
        (25.5, 47.5, 4.8),
        (35.5, 47.5, 4.8),
        (45.5, 47.5, 4.8),
    ]
    rng = random.Random(18018)
    made = 0
    attempts = 0
    while made < 360 and attempts < 5000:
        attempts += 1
        x = rng.uniform(PARK_X0 + 1.0, PARK_X1 - 1.0)
        y = rng.uniform(PARK_Y0 + 1.0, PARK_Y1 - 1.0)
        if abs(x - PARK_CX) < 2.0 or abs(y - PARK_CY) < 2.0 or abs(y - 47.5) < 1.8:
            continue
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        scale = rng.uniform(0.80, 1.25)
        stem = stem_proto.copy()
        stem.data = stem_proto.data
        stem.name = f"a18_grass_flower_stem_{made:03d}"
        stem.location = (x, y, 0.075 + 0.08 * scale)
        stem.scale = (1.0, 1.0, scale)
        park.objects.link(stem)
        flower_proto = flower_protos[rng.randrange(len(flower_protos))]
        flower = flower_proto.copy()
        flower.data = flower_proto.data
        flower.name = f"a18_grass_flower_{made:03d}"
        flower.location = (x, y, 0.24 + 0.08 * (scale - 1.0))
        flower.scale = (scale, scale, scale)
        park.objects.link(flower)
        made += 1
    bpy.data.objects.remove(stem_proto, do_unlink=True)
    for proto in flower_protos:
        bpy.data.objects.remove(proto, do_unlink=True)
    print(f"[all18] Added flower detail plants: {made}", flush=True)


def place_public_art(park):
    knot = append_prefix("knot:", park, "a18_center_mirror_knot")
    transform_group(knot, PARK_CX, PARK_CY, tz=0.12, yaw=math.radians(18), scale=1.40)

    pergola_row = [
        (25.5, 47.5, 0.0, 1.12),
        (35.5, 47.5, 0.0, 1.12),
        (45.5, 47.5, 0.0, 1.12),
    ]
    for idx, (x, y, yaw, scale) in enumerate(pergola_row):
        perg = append_prefix("perg:", park, f"a18_pergola_row_{idx:02d}")
        transform_group(perg, x, y, tz=0.055, yaw=yaw, scale=scale)
    print(
        "[all18] Placed center mirror-knot sculpture and three aligned pergolas",
        flush=True,
    )


def rebuild_large_benches(park):
    bench_plan = [
        (27.0, 32.0, 0.0),
        (44.0, 32.0, math.pi),
        (31.0, 39.2, math.pi),
        (40.0, 39.2, math.pi),
        (24.0, 52.2, 0.0),
        (35.5, 52.2, 0.0),
        (47.0, 52.2, 0.0),
        (20.0, 45.2, -math.pi / 2),
        (51.0, 45.2, math.pi / 2),
        (18.0, 24.0, 0.0),
        (30.0, 18.0, 0.0),
        (42.0, 18.0, 0.0),
        (55.0, 24.0, math.pi),
        (15.0, 36.0, math.pi / 2),
        (56.5, 36.0, -math.pi / 2),
    ]
    for idx, (x, y, yaw) in enumerate(bench_plan):
        objs = UA.place_bench_classic((x, y), park, yaw=yaw)
        scale_group_about_center(objs, 1.45)
        for obj in objs:
            obj.name = f"a18_large_park_bench_{idx:02d}_{obj.name}"
    print(f"[all18] Placed larger park benches: {len(bench_plan)}", flush=True)


def ensure_cycles_color_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.image_settings.file_format = "PNG"
    scene.cycles.samples = 192
    scene.cycles.use_denoising = True
    try:
        scene.cycles.device = "GPU"
    except Exception:
        pass
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = -0.25
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


print("[all18] Opening all16 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park_coll = get_coll("Park")

remove_old_focal_and_benches(park_coll)
expand_old_grass_ground(park_coll)
add_walk_paths_and_marble_plaza(park_coll)
add_flower_detail(park_coll)
place_public_art(park_coll)
rebuild_large_benches(park_coll)
ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all18.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all18] Blend saved: {out_blend}", flush=True)

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
        print(f"[all18] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all18] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all18] Done: {filename}", flush=True)

print("[all18] All complete.", flush=True)
