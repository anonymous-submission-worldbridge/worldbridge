"""
Create urban_v3_all21 from urban_v3_all16 with strict park refinements.

Park requirements:
  - Use one oversized continuous old-soil/flower ground treatment across the park quadrant.
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
OUT = ROOT / "infinigen/outputs/urban_v3_all21"
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

MARBLE_RADIUS = 5.65
MARBLE_CLEAN_RADIUS = 7.15
PERGOLA_XS = (25.5, 35.5, 45.5)
PERGOLA_Y = PARK_CY + 5.70
PERGOLA_KEEP_RADIUS = 4.35
BENCH_CLEARANCE = 1.75
QUADRANT_ROAD_EDGE = 4.55
# Deliberately oversized so the old-soil/flower treatment extends far past
# the pergola row and fills the whole visible park quadrant in the park camera.
OVERSIZED_PARK_END = 125.00
VISUAL_GRASS_X0 = QUADRANT_ROAD_EDGE
VISUAL_GRASS_X1 = OVERSIZED_PARK_END
VISUAL_GRASS_Y0 = QUADRANT_ROAD_EDGE
VISUAL_GRASS_Y1 = OVERSIZED_PARK_END


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


def mat_old_grass_soil(name):
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
    noise.location = (-430, 0)
    ramp.location = (-210, 0)
    bsdf.location = (0, 0)
    out.location = (260, 0)
    noise.inputs["Scale"].default_value = 36.0
    noise.inputs["Detail"].default_value = 12.0
    noise.inputs["Roughness"].default_value = 0.68
    ramp.color_ramp.elements[0].position = 0.16
    ramp.color_ramp.elements[0].color = (0.19, 0.125, 0.058, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.30, 0.205, 0.095, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.90
    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_flat(name, rgb, rough=0.82):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
    return mat


def box(name, cx, cy, cz, dx, dy, dz, mat, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz), scale=(dx, dy, dz))
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    link_only_to_coll(obj, coll)
    return obj


def lawn_surface(name, x0, x1, y0, y1, z, mat, coll, step=2.0):
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


def is_clear_for_grass_detail(x, y):
    if math.hypot(x - PARK_CX, y - PARK_CY) < MARBLE_CLEAN_RADIUS + 0.35:
        return False
    gap = MARBLE_RADIUS + 0.55
    if abs(x - PARK_CX) < 1.35 and (y < PARK_CY - gap or y > PARK_CY + gap):
        return False
    if abs(y - PARK_CY) < 1.35 and (x < PARK_CX - gap or x > PARK_CX + gap):
        return False
    if abs(y - PERGOLA_Y) < 1.10 and 21.0 <= x <= 50.0:
        return False
    if any(
        math.hypot(x - px, y - PERGOLA_Y) < PERGOLA_KEEP_RADIUS + 0.25
        for px in PERGOLA_XS
    ):
        return False
    return True


def add_full_visible_old_grassland(park):
    template_lawn = bpy.data.objects.get("park_lawn_grid.001") or bpy.data.objects.get(
        "park_lawn_grid"
    )
    template_mat = None
    if template_lawn is not None and template_lawn.material_slots:
        template_mat = template_lawn.material_slots[0].material
    grass_soil = (
        template_mat
        or bpy.data.materials.get("a8_grass_park")
        or bpy.data.materials.get("a13_gp")
        or mat_old_grass_soil("a21_old_grass_soil_full_park")
    )
    leaf_dark = mat_flat("a21_old_grass_blade_dark", (0.070, 0.230, 0.035))
    leaf_mid = mat_flat("a21_old_grass_blade_mid", (0.125, 0.335, 0.060))
    flower_y = mat_flat("a21_old_grass_flower_yellow", (0.95, 0.78, 0.08), 0.62)
    flower_w = mat_flat("a21_old_grass_flower_white", (0.92, 0.90, 0.82), 0.62)
    flower_p = mat_flat("a21_old_grass_flower_pink", (0.76, 0.28, 0.55), 0.62)
    flower_b = mat_flat("a21_old_grass_flower_blue", (0.30, 0.42, 0.78), 0.62)

    carpet = lawn_surface(
        "a21_full_old_grass_soil_carpet",
        VISUAL_GRASS_X0,
        VISUAL_GRASS_X1,
        VISUAL_GRASS_Y0,
        VISUAL_GRASS_Y1,
        0.034,
        grass_soil,
        park,
        step=1.85,
    )
    carpet.hide_render = False
    carpet.visible_camera = True

    rng = random.Random(2121)
    verts = []
    faces = []
    mat_indices = []
    leaf_mats = [leaf_dark, leaf_mid]
    flower_mats = [flower_y, flower_w, flower_p, flower_b]

    x = VISUAL_GRASS_X0 + 0.55
    while x <= VISUAL_GRASS_X1 - 0.55:
        y = VISUAL_GRASS_Y0 + 0.55
        while y <= VISUAL_GRASS_Y1 - 0.55:
            gx = x + rng.uniform(-0.24, 0.24)
            gy = y + rng.uniform(-0.24, 0.24)
            if is_clear_for_grass_detail(gx, gy):
                for _ in range(4):
                    ang = rng.uniform(0, math.tau)
                    width = rng.uniform(0.045, 0.080)
                    height = rng.uniform(0.18, 0.34)
                    lean = rng.uniform(0.020, 0.075)
                    dx = math.cos(ang) * width
                    dy = math.sin(ang) * width
                    lx = math.cos(ang + math.pi / 2) * lean
                    ly = math.sin(ang + math.pi / 2) * lean
                    base = len(verts)
                    verts.extend(
                        [
                            (gx - dx, gy - dy, 0.043),
                            (gx + dx, gy + dy, 0.043),
                            (gx + lx, gy + ly, 0.043 + height),
                        ]
                    )
                    faces.append((base, base + 1, base + 2))
                    mat_indices.append(rng.randrange(len(leaf_mats)))

                if rng.random() < 0.34:
                    rad = rng.uniform(0.060, 0.105)
                    z = rng.uniform(0.140, 0.205)
                    for petal in range(4):
                        ang = petal * math.pi / 2 + rng.uniform(-0.18, 0.18)
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
                        mat_indices.append(
                            len(leaf_mats) + rng.randrange(len(flower_mats))
                        )
            y += 0.62
        x += 0.62

    mesh = bpy.data.meshes.new("a21_full_old_grass_detail_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("a21_full_old_grass_detail", mesh)
    for mat in leaf_mats + flower_mats:
        obj.data.materials.append(mat)
    for poly, mat_index in zip(obj.data.polygons, mat_indices):
        poly.material_index = mat_index
    link_only_to_coll(obj, park)
    obj.hide_render = False
    obj.visible_camera = True
    print(
        f"[all21] Added full visible old grassland carpet and {len(faces)} detail faces",
        flush=True,
    )


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


def hide_original_lawn_ground(park):
    hidden = 0
    for lawn in [
        obj for obj in bpy.data.objects if obj.name.startswith("park_lawn_grid")
    ]:
        if lawn.type != "MESH":
            continue
        lawn.hide_render = True
        lawn.hide_viewport = True
        lawn.visible_camera = False
        link_only_to_coll(lawn, park)
        hidden += 1
    print(
        f"[all21] Hidden original park_lawn_grid variants to remove split ground: {hidden}",
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


print("[all21] Opening all16 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park_coll = get_coll("Park")

remove_old_focal_and_benches(park_coll)
hide_original_lawn_ground(park_coll)
add_walk_paths_and_clean_marble_plaza(park_coll)
remove_vegetation_from_marble(park_coll)
remove_vegetation_from_pergola_keepouts(park_coll)
add_full_visible_old_grassland(park_coll)
place_public_art(park_coll)
rebuild_large_benches(park_coll)
ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all21.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all21] Blend saved: {out_blend}", flush=True)

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
        print(f"[all21] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all21] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all21] Done: {filename}", flush=True)

print("[all21] All complete.", flush=True)
