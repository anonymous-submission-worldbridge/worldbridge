"""
Create urban_v3_all20 from urban_v3_all16 with strict park refinements.

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
OUT = ROOT / "infinigen/outputs/urban_v3_all20"
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
PERGOLA_XS = (25.5, 35.5, 45.5)
PERGOLA_Y = PARK_CY + 5.70
PERGOLA_KEEP_RADIUS = 4.35
BENCH_CLEARANCE = 1.75


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


def move_group_xy(objects, dx, dy):
    for obj in objects:
        obj.location.x += dx
        obj.location.y += dy
    bpy.context.view_layer.update()


def center_group_xy(objects, tx, ty):
    _mn, _mx, center = bbox_info(objects)
    move_group_xy(objects, tx - center.x, ty - center.y)


def clamp_group_inside_park(objects, margin=0.75):
    mn, mx, _center = bbox_info(objects)
    dx = 0.0
    dy = 0.0
    if mn.x < PARK_X0 + margin:
        dx = PARK_X0 + margin - mn.x
    elif mx.x > PARK_X1 - margin:
        dx = PARK_X1 - margin - mx.x
    if mn.y < PARK_Y0 + margin:
        dy = PARK_Y0 + margin - mn.y
    elif mx.y > PARK_Y1 - margin:
        dy = PARK_Y1 - margin - mx.y
    if dx or dy:
        move_group_xy(objects, dx, dy)


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
    )
    removed = 0
    for obj in list(park.all_objects):
        if obj.name.startswith(remove_prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(
        f"[all20] Removed old park focal/bench/scatter objects: {removed}", flush=True
    )


def resize_original_lawn_to_full_park(park):
    lawn = bpy.data.objects.get("park_lawn_grid")
    if lawn is None or lawn.type != "MESH":
        raise RuntimeError("park_lawn_grid mesh is required for all20 grass coverage")

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
    link_only_to_coll(lawn, park)

    mn, mx, _center, _radius = object_xy_bbox(lawn)
    print(
        "[all20] Resized park_lawn_grid to "
        f"x=[{mn.x:.2f},{mx.x:.2f}] y=[{mn.y:.2f},{mx.y:.2f}]",
        flush=True,
    )


def add_walk_paths_and_clean_marble_plaza(park):
    stone = bpy.data.materials.get("park_stone") or mat_principled(
        "park_stone", (0.64, 0.62, 0.56), 0.72
    )
    marble = mat_marble("a20_clean_white_marble")
    seam = mat_principled("a20_marble_seam", (0.63, 0.64, 0.63), 0.78)

    gap = MARBLE_RADIUS + 0.55
    box(
        "a20_path_ns_south",
        PARK_CX,
        (PARK_Y0 + PARK_CY - gap) / 2,
        0.040,
        2.15,
        PARK_CY - gap - PARK_Y0,
        0.022,
        stone,
        park,
    )
    box(
        "a20_path_ns_north",
        PARK_CX,
        (PARK_CY + gap + PARK_Y1) / 2,
        0.040,
        2.15,
        PARK_Y1 - (PARK_CY + gap),
        0.022,
        stone,
        park,
    )
    box(
        "a20_path_ew_west",
        (PARK_X0 + PARK_CX - gap) / 2,
        PARK_CY,
        0.041,
        PARK_CX - gap - PARK_X0,
        2.15,
        0.022,
        stone,
        park,
    )
    box(
        "a20_path_ew_east",
        (PARK_CX + gap + PARK_X1) / 2,
        PARK_CY,
        0.041,
        PARK_X1 - (PARK_CX + gap),
        2.15,
        0.022,
        stone,
        park,
    )
    box(
        "a20_path_pergola_row",
        PARK_CX,
        PERGOLA_Y,
        0.042,
        27.5,
        1.75,
        0.022,
        stone,
        park,
    )

    cyl(
        "a20_center_clean_marble_plaza",
        PARK_CX,
        PARK_CY,
        0.058,
        MARBLE_RADIUS,
        0.070,
        marble,
        park,
        verts=96,
    )
    for i in range(6):
        yaw = i * math.pi / 6
        obj = box(
            f"a20_center_marble_seam_{i}",
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
        "[all20] Added split walking paths and clean center white-marble sculpture pad",
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
        "a20_grass_flower_",
        "a20_grass_blossom_",
    )
    terms = ("flower", "blossom", "plant", "shrub", "tree", "trunk", "crown", "branch")
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
    print(f"[all20] Removed vegetation from clean marble zone: {removed}", flush=True)


def remove_vegetation_from_pergola_keepouts(park):
    keepouts = [(x, PERGOLA_Y, PERGOLA_KEEP_RADIUS) for x in PERGOLA_XS]
    removed = 0
    candidates = set(park.all_objects)
    candidates.update(
        obj
        for obj in bpy.data.objects
        if PARK_X0 - 2.0 <= obj.location.x <= PARK_X1 + 2.0
        and PARK_Y0 - 2.0 <= obj.location.y <= PARK_Y1 + 2.0
    )
    for obj in list(candidates):
        if not is_vegetation_object(obj):
            continue
        _mn, _mx, center, radius = object_xy_bbox(obj)
        if any(
            math.hypot(center.x - x, center.y - y) < r + radius for x, y, r in keepouts
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(
        f"[all20] Removed vegetation from pergola keepout zones: {removed}", flush=True
    )


def add_all16_style_flowerbeds(park):
    UA.build_all_materials()
    flowerbeds = [
        ("a20_fb_west", 18.5, 50.5, 4.0, 2.5, 20, 2001),
        ("a20_fb_south_east", 45.0, 16.0, 5.0, 3.0, 24, 2002),
        ("a20_fb_north_east", 52.5, 49.0, 3.8, 2.3, 18, 2003),
        ("a20_fb_south_west", 23.0, 18.0, 3.8, 2.4, 18, 2004),
    ]
    for tag, x, y, w, d, count, seed in flowerbeds:
        if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_CLEAN_RADIUS + 2.0:
            continue
        if any(
            math.hypot(x - px, y - PERGOLA_Y) < PERGOLA_KEEP_RADIUS + 2.8
            for px in PERGOLA_XS
        ):
            continue
        UA.build_flowerbed(tag, x, y, park, w=w, d=d, n_flowers=count, seed=seed)
    print("[all20] Added all16-style soil and flowerbed patches", flush=True)


def place_public_art(park):
    knot = append_prefix("knot:", park, "a20_center_mirror_knot")
    transform_group(knot, PARK_CX, PARK_CY, tz=0.135, yaw=math.radians(18), scale=1.42)

    pergola_row = [
        (PERGOLA_XS[0], PERGOLA_Y, 0.0, 1.12),
        (PERGOLA_XS[1], PERGOLA_Y, 0.0, 1.12),
        (PERGOLA_XS[2], PERGOLA_Y, 0.0, 1.12),
    ]
    for idx, (x, y, yaw, scale) in enumerate(pergola_row):
        perg = append_prefix("perg:", park, f"a20_pergola_row_{idx:02d}")
        transform_group(perg, x, y, tz=0.060, yaw=yaw, scale=scale)
    print(
        "[all20] Placed one center mirror-knot sculpture and three aligned near-center pergolas",
        flush=True,
    )


def rebuild_large_benches(park):
    bench_plan = [
        (20.5, 21.5, 0.0),
        (35.5, 21.5, 0.0),
        (50.5, 21.5, 0.0),
        (20.5, 29.5, math.pi),
        (50.5, 29.5, math.pi),
        (20.5, 48.5, 0.0),
        (35.5, 48.5, 0.0),
        (50.5, 48.5, 0.0),
        (16.8, 35.5, math.pi / 2),
        (54.2, 35.5, -math.pi / 2),
    ]
    for idx, (x, y, yaw) in enumerate(bench_plan):
        if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_CLEAN_RADIUS + 1.2:
            continue
        if any(
            math.hypot(x - px, y - PERGOLA_Y) < PERGOLA_KEEP_RADIUS + BENCH_CLEARANCE
            for px in PERGOLA_XS
        ):
            continue
        objs = UA.place_bench_classic((x, y), park, yaw=yaw)
        scale_group_about_center(objs, 1.48)
        center_group_xy(objs, x, y)
        clamp_group_inside_park(objs)
        for obj in objs:
            obj.name = f"a20_large_park_bench_{idx:02d}_{obj.name}"
    print(f"[all20] Placed larger park benches: {len(bench_plan)} planned", flush=True)


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


print("[all20] Opening all16 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park_coll = get_coll("Park")

remove_old_focal_and_benches(park_coll)
resize_original_lawn_to_full_park(park_coll)
add_walk_paths_and_clean_marble_plaza(park_coll)
remove_vegetation_from_marble(park_coll)
remove_vegetation_from_pergola_keepouts(park_coll)
add_all16_style_flowerbeds(park_coll)
remove_vegetation_from_marble(park_coll)
remove_vegetation_from_pergola_keepouts(park_coll)
place_public_art(park_coll)
rebuild_large_benches(park_coll)
ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all20.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all20] Blend saved: {out_blend}", flush=True)

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
        print(f"[all20] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all20] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all20] Done: {filename}", flush=True)

print("[all20] All complete.", flush=True)
