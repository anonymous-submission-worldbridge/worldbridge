"""
Create urban_v3_all19 from urban_v3_all16 with strict park refinements.

Park requirements:
  - Resize the original procedural lawn mesh so grass covers the full park area.
  - Put one mirror-knot sculpture at the park center on a clean white marble pad.
  - Keep flowers and walking paths out of the marble pad.
  - Place three pergolas in a regular row near the sculpture, away from the edge.
  - Rebuild larger benches with a planned layout.
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
OUT = ROOT / "infinigen/outputs/urban_v3_all19"
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

GRASS_MARGIN = 0.30
MARBLE_RADIUS = 5.65
MARBLE_CLEAN_RADIUS = 7.15
PERGOLA_Y = PARK_CY + 7.35


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


def object_xy_bbox(obj):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mn + mx) * 0.5
    radius = math.hypot((mx.x - mn.x) * 0.5, (mx.y - mn.y) * 0.5)
    return mn, mx, center, radius


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
    bpy.context.view_layer.update()

    mn, _mx, center = bbox_info(objects)
    dx = tx - center.x
    dy = ty - center.y
    dz = tz - mn.z
    for obj in objects:
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
    bpy.context.view_layer.update()


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


def mat_old_grass(name):
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
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-650, 0)
    noise.location = (-440, 0)
    ramp.location = (-220, 0)
    bsdf.location = (0, 0)
    out.location = (250, 0)
    noise.inputs["Scale"].default_value = 28.0
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.62
    ramp.color_ramp.elements[0].position = 0.24
    ramp.color_ramp.elements[0].color = (0.075, 0.205, 0.035, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.22, 0.36, 0.10, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.88
    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
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
    ramp.color_ramp.elements[0].color = (0.84, 0.84, 0.82, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.98, 0.97, 0.94, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
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


def cyl(name, cx, cy, base_z, radius, depth, mat, coll, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts,
        radius=radius,
        depth=depth,
        location=(cx, cy, base_z + depth / 2),
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


def torus(name, cx, cy, cz, major_radius, minor_radius, mat, coll):
    bpy.ops.mesh.primitive_torus_add(
        major_segments=96,
        minor_segments=10,
        major_radius=major_radius,
        minor_radius=minor_radius,
        location=(cx, cy, cz),
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
        "all8veg_scatter:",
    )
    removed = 0
    for obj in list(park.all_objects):
        if obj.name.startswith(remove_prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(
        f"[all19] Removed old park focal/bench/scatter objects: {removed}", flush=True
    )


def resize_original_lawn_to_full_park(park):
    lawn = bpy.data.objects.get("park_lawn_grid")
    if lawn is None or lawn.type != "MESH":
        raise RuntimeError("park_lawn_grid mesh is required for all19 grass coverage")

    target_x0 = PARK_X0 - GRASS_MARGIN
    target_x1 = PARK_X1 + GRASS_MARGIN
    target_y0 = PARK_Y0 - GRASS_MARGIN
    target_y1 = PARK_Y1 + GRASS_MARGIN

    pts = [lawn.matrix_world @ Vector(corner) for corner in lawn.bound_box]
    src_x0 = min(p.x for p in pts)
    src_x1 = max(p.x for p in pts)
    src_y0 = min(p.y for p in pts)
    src_y1 = max(p.y for p in pts)
    if abs(src_x1 - src_x0) < 1e-5 or abs(src_y1 - src_y0) < 1e-5:
        raise RuntimeError("park_lawn_grid has invalid XY bounds")

    scale_x = (target_x1 - target_x0) / (src_x1 - src_x0)
    scale_y = (target_y1 - target_y0) / (src_y1 - src_y0)
    lawn.scale.x *= scale_x
    lawn.scale.y *= scale_y
    bpy.context.view_layer.update()

    mn, mx, center, _radius = object_xy_bbox(lawn)
    lawn.location.x += PARK_CX - center.x
    lawn.location.y += PARK_CY - center.y
    bpy.context.view_layer.update()

    lawn.hide_render = False
    lawn.hide_viewport = False
    lawn.visible_camera = True
    lawn.data.materials.clear()
    lawn.data.materials.append(mat_old_grass("a19_old_grass_full_park"))
    link_only_to_coll(lawn, park)

    mn, mx, _center, _radius = object_xy_bbox(lawn)
    print(
        "[all19] Resized park_lawn_grid to "
        f"x=[{mn.x:.2f},{mx.x:.2f}] y=[{mn.y:.2f},{mx.y:.2f}]",
        flush=True,
    )


def add_walk_paths_and_clean_marble_plaza(park):
    stone = bpy.data.materials.get("park_stone") or mat_principled(
        "park_stone", (0.64, 0.62, 0.56), 0.72
    )
    marble = mat_marble("a19_clean_white_marble")
    seam = mat_principled("a19_marble_seam", (0.63, 0.64, 0.63), 0.78)
    edge = mat_principled("a19_marble_edge", (0.70, 0.70, 0.68), 0.62)

    box(
        "a19_path_center_ns",
        PARK_CX,
        PARK_CY,
        0.034,
        2.15,
        PARK_Y1 - PARK_Y0,
        0.028,
        stone,
        park,
    )
    box(
        "a19_path_center_ew",
        PARK_CX,
        PARK_CY,
        0.035,
        PARK_X1 - PARK_X0,
        2.15,
        0.028,
        stone,
        park,
    )
    box(
        "a19_path_pergola_row",
        PARK_CX,
        PERGOLA_Y,
        0.037,
        31.0,
        1.80,
        0.028,
        stone,
        park,
    )

    cyl(
        "a19_center_clean_marble_plaza",
        PARK_CX,
        PARK_CY,
        0.054,
        MARBLE_RADIUS,
        0.072,
        marble,
        park,
        verts=96,
    )
    torus(
        "a19_center_marble_low_edge_ring",
        PARK_CX,
        PARK_CY,
        0.128,
        MARBLE_RADIUS,
        0.055,
        edge,
        park,
    )
    for i in range(6):
        yaw = i * math.pi / 6
        obj = box(
            f"a19_center_marble_seam_{i}",
            PARK_CX,
            PARK_CY,
            0.132,
            MARBLE_RADIUS * 1.78,
            0.026,
            0.010,
            seam,
            park,
        )
        obj.rotation_euler.z = yaw
    print(
        "[all19] Added walking paths and clean center white-marble sculpture pad",
        flush=True,
    )


def is_vegetation_object(obj):
    name = obj.name
    if name == "park_lawn_grid":
        return False
    prefixes = (
        "pfb",
        "pk_fl",
        "all8veg_scatter:",
        "a19_grass_flower_",
        "a19_grass_blossom_",
    )
    terms = ("flower", "blossom", "plant", "shrub")
    return name.startswith(prefixes) or any(term in name.lower() for term in terms)


def remove_vegetation_from_marble(park):
    removed = 0
    for obj in list(park.all_objects):
        if not is_vegetation_object(obj):
            continue
        _mn, _mx, center, radius = object_xy_bbox(obj)
        if (
            math.hypot(center.x - PARK_CX, center.y - PARK_CY)
            < MARBLE_CLEAN_RADIUS + radius
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(f"[all19] Removed vegetation from clean marble zone: {removed}", flush=True)


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
        "a19_flower_proto_stem",
        -1000,
        -1000,
        0.06,
        0.007,
        0.17,
        mats["leaf"],
        park,
        verts=5,
    )
    flower_protos = [
        sph(f"a19_flower_proto_{i}", -1000, -1000, 0.24, 0.055, mat, park)
        for i, mat in enumerate(flower_mats)
    ]
    avoid = [
        (PARK_CX, PARK_CY, MARBLE_CLEAN_RADIUS),
        (25.5, PERGOLA_Y, 4.9),
        (35.5, PERGOLA_Y, 4.9),
        (45.5, PERGOLA_Y, 4.9),
    ]
    rng = random.Random(19019)
    made = 0
    attempts = 0
    while made < 430 and attempts < 8000:
        attempts += 1
        x = rng.uniform(PARK_X0 + 1.0, PARK_X1 - 1.0)
        y = rng.uniform(PARK_Y0 + 1.0, PARK_Y1 - 1.0)
        if (
            abs(x - PARK_CX) < 1.7
            or abs(y - PARK_CY) < 1.7
            or abs(y - PERGOLA_Y) < 1.55
        ):
            continue
        if any(math.hypot(x - ax, y - ay) < ar for ax, ay, ar in avoid):
            continue
        scale = rng.uniform(0.95, 1.42)
        stem = stem_proto.copy()
        stem.data = stem_proto.data
        stem.name = f"a19_grass_flower_stem_{made:03d}"
        stem.location = (x, y, 0.076 + 0.085 * scale)
        stem.scale = (1.0, 1.0, scale)
        park.objects.link(stem)
        flower_proto = flower_protos[rng.randrange(len(flower_protos))]
        flower = flower_proto.copy()
        flower.data = flower_proto.data
        flower.name = f"a19_grass_blossom_{made:03d}"
        flower.location = (x, y, 0.25 + 0.085 * (scale - 1.0))
        flower.scale = (scale, scale, scale)
        park.objects.link(flower)
        made += 1
    bpy.data.objects.remove(stem_proto, do_unlink=True)
    for proto in flower_protos:
        bpy.data.objects.remove(proto, do_unlink=True)
    print(
        f"[all19] Added grass flower detail outside marble/pergola zones: {made}",
        flush=True,
    )


def place_public_art(park):
    knot = append_prefix("knot:", park, "a19_center_mirror_knot")
    transform_group(knot, PARK_CX, PARK_CY, tz=0.135, yaw=math.radians(18), scale=1.42)

    pergola_row = [
        (25.5, PERGOLA_Y, 0.0, 1.14),
        (35.5, PERGOLA_Y, 0.0, 1.14),
        (45.5, PERGOLA_Y, 0.0, 1.14),
    ]
    for idx, (x, y, yaw, scale) in enumerate(pergola_row):
        perg = append_prefix("perg:", park, f"a19_pergola_row_{idx:02d}")
        transform_group(perg, x, y, tz=0.060, yaw=yaw, scale=scale)
    print(
        "[all19] Placed one center mirror-knot sculpture and three aligned near-center pergolas",
        flush=True,
    )


def rebuild_large_benches(park):
    bench_plan = [
        (26.0, 30.2, 0.0),
        (45.0, 30.2, math.pi),
        (25.8, 39.9, math.pi),
        (45.2, 39.9, math.pi),
        (22.0, 46.0, -math.pi / 2),
        (49.0, 46.0, math.pi / 2),
        (19.2, 31.0, math.pi / 2),
        (51.8, 31.0, -math.pi / 2),
        (18.5, 22.5, 0.0),
        (29.5, 18.2, 0.0),
        (41.5, 18.2, 0.0),
        (52.5, 22.5, math.pi),
        (20.5, 54.2, 0.0),
        (35.5, 54.2, 0.0),
        (50.5, 54.2, 0.0),
        (15.6, 38.5, math.pi / 2),
        (55.4, 38.5, -math.pi / 2),
    ]
    for idx, (x, y, yaw) in enumerate(bench_plan):
        if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_CLEAN_RADIUS + 1.2:
            continue
        objs = UA.place_bench_classic((x, y), park, yaw=yaw)
        scale_group_about_center(objs, 1.62)
        for obj in objs:
            obj.name = f"a19_large_park_bench_{idx:02d}_{obj.name}"
    print(f"[all19] Placed larger park benches: {len(bench_plan)} planned", flush=True)


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


print("[all19] Opening all16 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park_coll = get_coll("Park")

remove_old_focal_and_benches(park_coll)
resize_original_lawn_to_full_park(park_coll)
add_walk_paths_and_clean_marble_plaza(park_coll)
remove_vegetation_from_marble(park_coll)
add_flower_detail(park_coll)
remove_vegetation_from_marble(park_coll)
place_public_art(park_coll)
rebuild_large_benches(park_coll)
ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all19.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all19] Blend saved: {out_blend}", flush=True)

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
        print(f"[all19] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all19] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all19] Done: {filename}", flush=True)

print("[all19] All complete.", flush=True)
