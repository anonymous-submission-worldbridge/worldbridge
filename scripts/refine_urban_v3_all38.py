"""
Build urban_v3_all38 from urban_v3_all37 with targeted residential updates:

  1. Replace the residential yard/entry ground with marble paving and real seam
     strips.
  2. Rebuild the house hip roof with a small eave and grey-blue/qingwa material.
  3. Strengthen the facade with visible wood doors, glass panes, and wood frames.
  4. Add a custom wrought-iron fence around the current house footprint.
  5. Render residential + two interior views; copy unchanged exterior views.
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
import shutil

import bpy
import bmesh
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all37/urban_v3_all37.blend"
SRC_OUT = ROOT / "infinigen/outputs/urban_v3_all37"
OUT = ROOT / "infinigen/outputs/urban_v3_all38"
OUT.mkdir(parents=True, exist_ok=True)


def enable_gpu():
    bpy.context.scene.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
        bpy.context.scene.cycles.device = "GPU"
        print("[all38] GPU OPTIX enabled", flush=True)
    except Exception as exc:
        print(f"[all38] GPU setup skipped: {exc}", flush=True)


def clear_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    for node in list(mat.node_tree.nodes):
        mat.node_tree.nodes.remove(node)
    return mat


def set_input(bsdf, key, value):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = value


def principled_mat(name, color, roughness=0.6, metallic=0.0):
    mat = clear_mat(name)
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Metallic", metallic)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def marble_mat():
    mat = clear_mat("a38_marble_paving")
    nt = mat.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")

    noise = nd.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.58
    lk.new(tex.outputs["Object"], noise.inputs["Vector"])

    ramp = nd.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (0.64, 0.66, 0.66, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.92, 0.93, 0.90, 1)
    vein = ramp.color_ramp.elements.new(0.48)
    vein.color = (0.36, 0.39, 0.40, 1)
    lk.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    lk.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nd.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.012
    lk.new(noise.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_input(bsdf, "Roughness", 0.34)
    set_input(bsdf, "Metallic", 0.0)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def roof_mat():
    mat = clear_mat("a38_roof_qingwa_grayblue")
    nt = mat.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    brick = nd.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.22, 0.31, 0.36, 1)
    brick.inputs["Color2"].default_value = (0.31, 0.42, 0.47, 1)
    brick.inputs["Mortar"].default_value = (0.075, 0.10, 0.115, 1)
    brick.inputs["Scale"].default_value = 1.15
    brick.inputs["Mortar Size"].default_value = 0.026
    if "Brick Width" in brick.inputs:
        brick.inputs["Brick Width"].default_value = 0.42
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 0.24
    lk.new(tex.outputs["Object"], brick.inputs["Vector"])
    lk.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nd.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.38
    bump.inputs["Distance"].default_value = 0.018
    lk.new(brick.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_input(bsdf, "Roughness", 0.68)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def glass_mat():
    mat = clear_mat("a38_clear_window_glass")
    nt = mat.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.84, 0.93, 0.98, 0.42)
    set_input(bsdf, "Alpha", 0.42)
    set_input(bsdf, "Roughness", 0.015)
    set_input(bsdf, "Transmission Weight", 0.78)
    set_input(bsdf, "IOR", 1.45)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.blend_method = "BLEND"
    mat.use_screen_refraction = True
    return mat


def wood_mat(name, base, dark):
    mat = clear_mat(name)
    nt = mat.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    bsdf = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    wave = nd.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 7.0
    wave.inputs["Distortion"].default_value = 11.0
    lk.new(tex.outputs["Object"], wave.inputs["Vector"])
    ramp = nd.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*base, 1)
    lk.new(wave.outputs["Color"], ramp.inputs["Fac"])
    lk.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nd.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.006
    lk.new(wave.outputs["Color"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_input(bsdf, "Roughness", 0.48)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def bbox(objs):
    mn = [1e18, 1e18, 1e18]
    mx = [-1e18, -1e18, -1e18]
    for obj in objs:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                mn[axis] = min(mn[axis], world[axis])
                mx[axis] = max(mx[axis], world[axis])
    return mn, mx


def center(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(pts, Vector((0, 0, 0))) / 8


def in_coll(obj, text):
    return any(text in coll.name for coll in obj.users_collection)


def link_to(obj, coll):
    coll.objects.link(obj)
    for user_coll in list(obj.users_collection):
        if user_coll is not coll:
            user_coll.objects.unlink(obj)
    return obj


def bevel(obj, width=0.008, segments=1):
    if width < 0.01:
        return obj
    mod = obj.modifiers.new("a38_bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("a38_weighted_normal", "WEIGHTED_NORMAL")
    return obj


def cube(name, loc, dims, mat, coll, rot=(0, 0, 0), bevel_width=0.006):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    verts = [
        (-0.5, -0.5, -0.5),
        (0.5, -0.5, -0.5),
        (0.5, 0.5, -0.5),
        (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),
        (0.5, -0.5, 0.5),
        (0.5, 0.5, 0.5),
        (-0.5, 0.5, 0.5),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.name = name
    obj.location = loc
    obj.rotation_euler = rot
    obj.scale = dims
    if mat:
        obj.data.materials.append(mat)
    bevel(obj, bevel_width)
    coll.objects.link(obj)
    return obj


def cylinder(
    name, loc, radius, depth, mat, coll, vertices=24, rot=(0, 0, 0), bevel_width=0
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot
    )
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    bevel(obj, bevel_width)
    return link_to(obj, coll)


def pyramid(name, loc, base, height, mat, coll, rot=(0, 0, math.radians(45))):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    z0 = -height / 2
    z1 = height / 2
    verts = [
        (-base, -base, z0),
        (base, -base, z0),
        (base, base, z0),
        (-base, base, z0),
        (0, 0, z1),
    ]
    faces = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = rot
    if mat:
        obj.data.materials.append(mat)
    coll.objects.link(obj)
    return obj


def torus(name, loc, major, minor, mat, coll, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=24,
        minor_segments=8,
        location=loc,
        rotation=rot,
    )
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return link_to(obj, coll)


def pt(axis, t, fixed):
    return (t, fixed) if axis == "X" else (fixed, t)


def dims(axis, length, thick, height):
    return (length, thick, height) if axis == "X" else (thick, length, height)


def build_hip_roof(emn, emx, mat, fascia_mat, coll, overhang=0.22, pitch_frac=0.13):
    x0, y0 = emn[0] - overhang, emn[1] - overhang
    x1, y1 = emx[0] + overhang, emx[1] + overhang
    zt = emx[2] - 0.015
    width, depth = x1 - x0, y1 - y0
    rise = pitch_frac * min(width, depth)
    zr = zt + rise
    if width >= depth:
        inset = depth / 2
        yc = (y0 + y1) / 2
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (x0 + inset, yc, zr),
            (x1 - inset, yc, zr),
        ]
        faces = [(0, 1, 5, 4), (2, 3, 4, 5), (3, 0, 4), (1, 2, 5)]
    else:
        inset = width / 2
        xc = (x0 + x1) / 2
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (xc, y0 + inset, zr),
            (xc, y1 - inset, zr),
        ]
        faces = [(1, 2, 5, 4), (3, 0, 4, 5), (0, 1, 4), (2, 3, 5)]
    mesh = bpy.data.meshes.new("a38_house_roof_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    roof = bpy.data.objects.new("house_roof", mesh)
    roof.data.materials.append(mat)
    coll.objects.link(roof)
    bevel(roof, 0.01)

    edge_z = zt - 0.055
    cube(
        "a38_roof_fascia_front",
        ((x1 + x0) / 2, y0, edge_z),
        (width, 0.09, 0.11),
        fascia_mat,
        coll,
    )
    cube(
        "a38_roof_fascia_back",
        ((x1 + x0) / 2, y1, edge_z),
        (width, 0.09, 0.11),
        fascia_mat,
        coll,
    )
    cube(
        "a38_roof_fascia_left",
        (x0, (y0 + y1) / 2, edge_z),
        (0.09, depth, 0.11),
        fascia_mat,
        coll,
    )
    cube(
        "a38_roof_fascia_right",
        (x1, (y0 + y1) / 2, edge_z),
        (0.09, depth, 0.11),
        fascia_mat,
        coll,
    )
    return roof


def add_marble_paving(coll, mat, seam_mat, emn, emx, hmn, hmx):
    plot = {
        "front_x": -8.85,
        "back_x": emn[0] - 1.20,
        "y0": hmn[1] - 0.95,
        "y1": hmx[1] + 0.95,
    }
    z = 0.055
    slabs = [
        ("front", emx[0] + 0.04, plot["front_x"], plot["y0"], plot["y1"]),
        ("back", plot["back_x"], emn[0] - 0.04, plot["y0"], plot["y1"]),
        ("south", emn[0] - 0.04, emx[0] + 0.04, plot["y0"], emn[1] - 0.04),
        ("north", emn[0] - 0.04, emx[0] + 0.04, emx[1] + 0.04, plot["y1"]),
    ]
    valid = []
    for name, x0, x1, y0, y1 in slabs:
        if x1 <= x0 or y1 <= y0:
            continue
        valid.append((x0, x1, y0, y1))
        cube(
            f"a38_marble_paving_{name}",
            ((x0 + x1) / 2, (y0 + y1) / 2, z),
            (x1 - x0, y1 - y0, 0.055),
            mat,
            coll,
            bevel_width=0.004,
        )
        tile = 1.15
        sx = math.ceil(x0 / tile) * tile
        i = 0
        while sx < x1:
            cube(
                f"a38_marble_seam_x_{name}_{i}",
                (sx, (y0 + y1) / 2, z + 0.032),
                (0.022, y1 - y0, 0.012),
                seam_mat,
                coll,
                bevel_width=0,
            )
            sx += tile
            i += 1
        sy = math.ceil(y0 / tile) * tile
        j = 0
        while sy < y1:
            cube(
                f"a38_marble_seam_y_{name}_{j}",
                ((x0 + x1) / 2, sy, z + 0.033),
                (x1 - x0, 0.022, 0.012),
                seam_mat,
                coll,
                bevel_width=0,
            )
            sy += tile
            j += 1
    return plot, valid


def stone_pier(name, coll, x, y, stone, concrete, iron, h=1.72, w=0.34):
    cube(f"{name}:col", (x, y, h / 2), (w, w, h), stone, coll, bevel_width=0.012)
    cube(
        f"{name}:cap",
        (x, y, h + 0.035),
        (w + 0.14, w + 0.14, 0.07),
        concrete,
        coll,
        bevel_width=0.012,
    )
    pyramid(f"{name}:pyr", (x, y, h + 0.135), (w + 0.10) / 2, 0.16, concrete, coll)
    cylinder(f"{name}:finial", (x, y, h + 0.28), 0.045, 0.14, iron, coll, vertices=16)


def iron_run(name, coll, axis, t0, t1, fixed, posts, stone, concrete, iron):
    if t1 <= t0:
        return
    length = t1 - t0
    tc = (t0 + t1) / 2
    plinth_h = 0.43
    cube(
        f"{name}:plinth",
        (*pt(axis, tc, fixed), plinth_h / 2),
        dims(axis, length, 0.20, plinth_h),
        stone,
        coll,
    )
    cube(
        f"{name}:plinthcap",
        (*pt(axis, tc, fixed), plinth_h + 0.025),
        dims(axis, length, 0.24, 0.05),
        concrete,
        coll,
    )
    rail_bot = plinth_h + 0.08
    rail_top = 1.45
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    for idx in range(len(posts) - 1):
        a = posts[idx] + 0.18
        b = posts[idx + 1] - 0.18
        if b <= a:
            continue
        bc = (a + b) / 2
        bl = b - a
        cube(
            f"{name}:rail_bot:{idx}",
            (*pt(axis, bc, fixed), rail_bot),
            dims(axis, bl, 0.052, 0.052),
            iron,
            coll,
        )
        cube(
            f"{name}:rail_mid:{idx}",
            (*pt(axis, bc, fixed), rail_top - 0.30),
            dims(axis, bl, 0.036, 0.036),
            iron,
            coll,
        )
        cube(
            f"{name}:rail_top:{idx}",
            (*pt(axis, bc, fixed), rail_top),
            dims(axis, bl, 0.055, 0.060),
            iron,
            coll,
        )
        n_bar = max(4, int(bl / 0.16))
        step = bl / n_bar
        for j in range(n_bar + 1):
            t = a + j * step
            cube(
                f"{name}:bar:{idx}:{j}",
                (*pt(axis, t, fixed), (rail_bot + rail_top) / 2 + 0.04),
                (0.024, 0.024, rail_top - rail_bot + 0.32),
                iron,
                coll,
                bevel_width=0.002,
            )
            pyramid(
                f"{name}:spear:{idx}:{j}",
                (*pt(axis, t, fixed), rail_top + 0.24),
                0.044,
                0.16,
                iron,
                coll,
            )
        n_ring = max(1, int(bl / 0.62))
        for j in range(n_ring):
            t = a + (j + 0.5) * (bl / n_ring)
            torus(
                f"{name}:ring:{idx}:{j}",
                (*pt(axis, t, fixed), rail_bot + 0.46),
                0.078,
                0.014,
                iron,
                coll,
                rot=ring_rot,
            )


def gate_leaf(name, coll, axis, t0, t1, fixed, iron):
    w = t1 - t0
    tc = (t0 + t1) / 2
    z_bot, z_top = 0.16, 1.58
    stile = 0.052
    cube(
        f"{name}:stile_a",
        (*pt(axis, t0 + stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        iron,
        coll,
    )
    cube(
        f"{name}:stile_b",
        (*pt(axis, t1 - stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        iron,
        coll,
    )
    cube(
        f"{name}:rail_bottom",
        (*pt(axis, tc, fixed), z_bot + 0.03),
        dims(axis, w, 0.055, 0.065),
        iron,
        coll,
    )
    cube(
        f"{name}:rail_top",
        (*pt(axis, tc, fixed), z_top - 0.03),
        dims(axis, w, 0.055, 0.065),
        iron,
        coll,
    )
    cube(
        f"{name}:rail_mid",
        (*pt(axis, tc, fixed), z_bot + (z_top - z_bot) * 0.42),
        dims(axis, w, 0.040, 0.044),
        iron,
        coll,
    )
    n = max(4, int(w / 0.16))
    for j in range(1, n):
        t = t0 + j * (w / n)
        cube(
            f"{name}:bar:{j}",
            (*pt(axis, t, fixed), (z_bot + z_top) / 2 + 0.03),
            (0.022, 0.022, z_top - z_bot + 0.24),
            iron,
            coll,
            bevel_width=0.002,
        )
        pyramid(
            f"{name}:spear:{j}",
            (*pt(axis, t, fixed), z_top + 0.21),
            0.040,
            0.15,
            iron,
            coll,
        )
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    for j in range(max(2, int(w / 0.56))):
        t = t0 + (j + 0.5) * (w / max(2, int(w / 0.56)))
        torus(
            f"{name}:ring:{j}",
            (*pt(axis, t, fixed), z_bot + 0.44),
            0.078,
            0.014,
            iron,
            coll,
            rot=ring_rot,
        )


def posts_between(a, b, spacing=2.8):
    if b < a:
        a, b = b, a
    pts = [a]
    n = max(1, int((b - a) / spacing))
    for i in range(1, n):
        pts.append(a + (b - a) * i / n)
    pts.append(b)
    return pts


def add_fence(coll, plot, door_y, stone, concrete, iron):
    front_x = plot["front_x"] + 0.10
    back_x = plot["back_x"] + 0.08
    y0 = plot["y0"] + 0.15
    y1 = plot["y1"] - 0.15
    gate_w = 3.60
    gy0 = max(y0 + 1.0, door_y - gate_w / 2)
    gy1 = min(y1 - 1.0, door_y + gate_w / 2)
    gate_c = (gy0 + gy1) / 2

    pier_points = [
        (front_x, y0),
        (front_x, gy0),
        (front_x, gy1),
        (front_x, y1),
        (back_x, y0),
        (back_x, y1),
    ]
    for x, y in pier_points:
        stone_pier(f"a38_fence_pier_{x:.1f}_{y:.1f}", coll, x, y, stone, concrete, iron)

    front_low = posts_between(y0, gy0)
    front_high = posts_between(gy1, y1)
    back = posts_between(y0, y1)
    side_x = posts_between(back_x, front_x)

    iron_run(
        "a38_fence_front_low",
        coll,
        "Y",
        y0,
        gy0,
        front_x,
        front_low,
        stone,
        concrete,
        iron,
    )
    iron_run(
        "a38_fence_front_high",
        coll,
        "Y",
        gy1,
        y1,
        front_x,
        front_high,
        stone,
        concrete,
        iron,
    )
    iron_run("a38_fence_back", coll, "Y", y0, y1, back_x, back, stone, concrete, iron)
    iron_run(
        "a38_fence_south", coll, "X", back_x, front_x, y0, side_x, stone, concrete, iron
    )
    iron_run(
        "a38_fence_north", coll, "X", back_x, front_x, y1, side_x, stone, concrete, iron
    )

    gate_leaf(
        "a38_fence_gate_left",
        coll,
        "Y",
        gy0 + 0.08,
        gate_c - 0.03,
        front_x + 0.018,
        iron,
    )
    gate_leaf(
        "a38_fence_gate_right",
        coll,
        "Y",
        gate_c + 0.03,
        gy1 - 0.08,
        front_x + 0.018,
        iron,
    )
    cylinder(
        "a38_fence_gate_handle_l",
        (front_x + 0.07, gate_c - 0.08, 0.92),
        0.035,
        0.12,
        iron,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    cylinder(
        "a38_fence_gate_handle_r",
        (front_x + 0.07, gate_c + 0.08, 0.92),
        0.035,
        0.12,
        iron,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    print(
        f"[all38] fence X[{back_x:.2f},{front_x:.2f}] Y[{y0:.2f},{y1:.2f}] gate Y[{gy0:.2f},{gy1:.2f}]",
        flush=True,
    )


def add_facade_details(coll, emn, emx, old_door_y, glass, frame_wood, door_wood, dark):
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("fd_", "fw0_", "fw1_", "a38_front_", "a38_upper_")):
            bpy.data.objects.remove(obj, do_unlink=True)

    fx = emx[0] + 0.035
    door_y = old_door_y
    door_h = 2.45
    door_w = 1.32
    cube(
        "a38_front_door_outer_frame",
        (fx + 0.018, door_y, door_h / 2),
        (0.10, door_w + 0.34, door_h + 0.24),
        frame_wood,
        coll,
        bevel_width=0.012,
    )
    cube(
        "a38_front_door_leaf",
        (fx + 0.075, door_y, door_h / 2),
        (0.075, door_w, door_h),
        door_wood,
        coll,
        bevel_width=0.012,
    )
    for zc in (0.82, 1.43):
        cube(
            f"a38_front_door_panel_{zc:.1f}",
            (fx + 0.118, door_y, zc),
            (0.030, door_w - 0.32, 0.46),
            dark,
            coll,
            bevel_width=0.006,
        )
    cube(
        "a38_front_door_glass_upper",
        (fx + 0.125, door_y, 1.96),
        (0.028, door_w - 0.36, 0.66),
        glass,
        coll,
        bevel_width=0.004,
    )
    cylinder(
        "a38_front_door_handle",
        (fx + 0.16, door_y - door_w * 0.33, 1.13),
        0.045,
        0.23,
        dark,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    cube(
        "a38_front_door_threshold",
        (fx + 0.08, door_y, 0.06),
        (0.28, door_w + 0.50, 0.12),
        dark,
        coll,
        bevel_width=0.01,
    )

    window_centers = [
        (door_y - 4.15, 1.58, 1.65, 1.56),
        (door_y + 4.15, 1.58, 1.65, 1.56),
        (door_y - 4.15, 3.55, 1.35, 1.05),
        (door_y + 4.15, 3.55, 1.35, 1.05),
    ]
    for idx, (wy, wz, ww, wh) in enumerate(window_centers):
        if wy - ww / 2 < emn[1] + 0.45 or wy + ww / 2 > emx[1] - 0.45:
            continue
        cube(
            f"a38_front_window_{idx}_outer_frame",
            (fx + 0.015, wy, wz),
            (0.105, ww + 0.28, wh + 0.28),
            frame_wood,
            coll,
            bevel_width=0.010,
        )
        cube(
            f"a38_front_window_{idx}_glass",
            (fx + 0.085, wy, wz),
            (0.030, ww, wh),
            glass,
            coll,
            bevel_width=0.004,
        )
        cube(
            f"a38_front_window_{idx}_mullion_v",
            (fx + 0.112, wy, wz),
            (0.036, 0.070, wh),
            frame_wood,
            coll,
            bevel_width=0.004,
        )
        cube(
            f"a38_front_window_{idx}_mullion_h",
            (fx + 0.112, wy, wz),
            (0.036, ww, 0.070),
            frame_wood,
            coll,
            bevel_width=0.004,
        )
        cube(
            f"a38_front_window_{idx}_sill",
            (fx + 0.105, wy, wz - wh / 2 - 0.14),
            (0.18, ww + 0.46, 0.09),
            dark,
            coll,
            bevel_width=0.006,
        )
    print(f"[all38] facade door_y={door_y:.2f} front_x={fx:.2f}", flush=True)
    return fx, door_y, window_centers


def make_cam(name, loc, target, fov):
    cam = bpy.data.objects.get(name)
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.object
        cam.name = name
        cam.data.name = name
    cam.location = Vector(loc)
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov)
    cam.data.clip_start = 0.02
    cam.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    return cam


def set_house_visibility(house_objs, mode, extra_hide=None):
    extra_hide = set(extra_hide or [])
    for obj in house_objs:
        if obj.type != "MESH":
            continue
        obj.hide_render = False
        if mode == "furniture" and (
            in_coll(obj, "room_wall")
            or in_coll(obj, "room_exterior")
            or in_coll(obj, "room_ceiling")
        ):
            obj.hide_render = True
        elif mode == "window" and (
            in_coll(obj, "room_wall") or in_coll(obj, "room_exterior")
        ):
            obj.hide_render = True
    for obj in extra_hide:
        obj.hide_render = True


print(f"[all38] opening {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
enable_gpu()

house = bpy.data.collections.get("House_indoor")
if not house:
    raise RuntimeError("House_indoor collection not found in all37 blend")
house_objs = list(house.all_objects)
hmn, hmx = bbox(house_objs)
ext_objs = [
    obj for obj in house_objs if obj.type == "MESH" and in_coll(obj, "room_exterior")
]
emn, emx = bbox(ext_objs) if ext_objs else (hmn, hmx)
old_door = bpy.data.objects.get("fd_leaf")
old_door_y = center(old_door).y if old_door else (emn[1] + emx[1]) / 2
print(
    f"[all38] house bbox X[{hmn[0]:.2f},{hmx[0]:.2f}] Y[{hmn[1]:.2f},{hmx[1]:.2f}]",
    flush=True,
)
print(
    f"[all38] exterior bbox X[{emn[0]:.2f},{emx[0]:.2f}] Y[{emn[1]:.2f},{emx[1]:.2f}]",
    flush=True,
)

all38 = bpy.data.collections.new("All38_residential_updates")
bpy.context.scene.collection.children.link(all38)

MAT_MARBLE = marble_mat()
MAT_SEAM = principled_mat(
    "a38_dark_marble_seam", (0.075, 0.080, 0.078, 1), roughness=0.78
)
MAT_ROOF = roof_mat()
MAT_FASCIA = principled_mat(
    "a38_roof_fascia_bluegray", (0.11, 0.16, 0.18, 1), roughness=0.72
)
MAT_GLASS = glass_mat()
MAT_DOOR_WOOD = wood_mat(
    "a38_oiled_wood_door", (0.42, 0.22, 0.095), (0.18, 0.085, 0.035)
)
MAT_FRAME_WOOD = wood_mat(
    "a38_window_frame_wood", (0.27, 0.16, 0.075), (0.09, 0.055, 0.030)
)
MAT_DARK = principled_mat(
    "a38_dark_hardware", (0.035, 0.032, 0.028, 1), roughness=0.42, metallic=0.30
)
MAT_STONE = principled_mat("a38_fence_cut_stone", (0.48, 0.47, 0.43, 1), roughness=0.86)
MAT_CONCRETE = principled_mat(
    "a38_fence_concrete_cap", (0.58, 0.57, 0.53, 1), roughness=0.82
)
MAT_IRON = principled_mat(
    "a38_black_wrought_iron", (0.018, 0.019, 0.021, 1), roughness=0.38, metallic=0.72
)

for obj in list(bpy.data.objects):
    if obj.name == "house_roof" or obj.name.startswith("a38_roof_fascia_"):
        bpy.data.objects.remove(obj, do_unlink=True)
build_hip_roof(emn, emx, MAT_ROOF, MAT_FASCIA, all38, overhang=0.22, pitch_frac=0.13)
print("[all38] roof rebuilt with small grey-blue eave", flush=True)
front_x, door_y, front_windows = add_facade_details(
    all38, emn, emx, old_door_y, MAT_GLASS, MAT_FRAME_WOOD, MAT_DOOR_WOOD, MAT_DARK
)
plot, _ = add_marble_paving(all38, MAT_MARBLE, MAT_SEAM, emn, emx, hmn, hmx)
print("[all38] marble paving with physical seams added", flush=True)
add_fence(all38, plot, door_y, MAT_STONE, MAT_CONCRETE, MAT_IRON)
house_objs = list(house.all_objects)

out_blend = OUT / "urban_v3_all38.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all38] saved {out_blend}", flush=True)

for name in ("commercial.png", "park.png", "intersection.png"):
    src = SRC_OUT / name
    if src.exists():
        shutil.copy2(src, OUT / name)

scene = bpy.context.scene
set_house_visibility(house_objs, "exterior")
for cam_name, filename in (
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
):
    cam = bpy.data.objects.get(cam_name)
    if cam:
        scene.camera = cam
        scene.render.filepath = str(OUT / filename)
        print(f"[all38] render {filename}", flush=True)
        bpy.ops.render.render(write_still=True)

# Furniture view: open up walls and aim at the furniture cluster.
furniture_keys = (
    "Shelf",
    "Cabinet",
    "Bookcase",
    "Table",
    "Chair",
    "Plant",
    "Lamp",
    "BookStack",
    "BookColumn",
    "Cell",
    "Plate",
    "Cup",
    "Bowl",
    "Pot",
    "Wineglass",
)
furn = [
    obj
    for obj in house_objs
    if obj.type == "MESH" and any(key in obj.name for key in furniture_keys)
]
fmn, fmx = bbox(
    [obj for obj in furn if obj.dimensions.length > 0.5] or furn or house_objs
)
fc = ((fmn[0] + fmx[0]) / 2, (fmn[1] + fmx[1]) / 2, (fmn[2] + fmx[2]) / 2)
make_cam(
    "cam_int_furniture",
    (fmx[0] + 4.6, fc[1] - 3.4, max(1.45, fmn[2] + 1.55)),
    (fc[0] - 0.4, fc[1] + 0.2, max(0.70, fmn[2] + 0.85)),
    64,
)
set_house_visibility(house_objs, "furniture")
scene.camera = bpy.data.objects["cam_int_furniture"]
scene.render.filepath = str(OUT / "interior_furniture.png")
print("[all38] render interior_furniture.png", flush=True)
bpy.ops.render.render(write_still=True)

# Window view: camera is square to the added front window and looks straight out.
set_house_visibility(house_objs, "window")
window_y, window_z, window_w, window_h = front_windows[0]
cam_x = emx[0] - 4.8
target_x = plot["front_x"] + 16.0
make_cam(
    "cam_int_window",
    (cam_x, window_y, window_z),
    (target_x, window_y, window_z - 0.05),
    58,
)
scene.camera = bpy.data.objects["cam_int_window"]
scene.render.filepath = str(OUT / "interior_window.png")
print("[all38] render interior_window.png", flush=True)
bpy.ops.render.render(write_still=True)

print("[all38] ALL DONE", flush=True)
