"""Rebuild court and playground with high-quality parametric master assets."""

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

import argparse, json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
INPUT = ROOT / "infinigen/outputs/urban_v3_all44_04/urban_v3_all44_04.blend"
OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_05"
P = "all44_05:"


def args():
    av = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    q = argparse.ArgumentParser()
    q.add_argument("--input", type=Path, default=INPUT)
    q.add_argument("--output", type=Path, default=OUTPUT)
    q.add_argument("--quality", choices=("test", "final"), default="final")
    return q.parse_args(av)


def mat(name, color, rough=0.6, metal=0, noise=0.05):
    m = bpy.data.materials.new(P + name)
    m.use_nodes = True
    n = m.node_tree.nodes
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if noise:
        tx = n.new("ShaderNodeTexNoise")
        tx.inputs["Scale"].default_value = 38
        tx.inputs["Detail"].default_value = 3
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise
        bump.inputs["Distance"].default_value = 0.025
        m.node_tree.links.new(tx.outputs["Fac"], bump.inputs["Height"])
        m.node_tree.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def collection(name, parent=None):
    c = bpy.data.collections.new(P + name)
    if parent:
        (parent.children.link(c))
    else:
        bpy.context.scene.collection.children.link(c)
    return c


def cube(name, loc, dim, material, c, bev=0.025, rot=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = P + name
    o.dimensions = dim
    o.rotation_euler[2] = rot
    for oc in list(o.users_collection):
        oc.objects.unlink(o)
    c.objects.link(o)
    o.data.materials.append(material)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bev:
        md = o.modifiers.new("edge_round", "BEVEL")
        md.width = bev
        md.segments = 3
        md.limit_method = "ANGLE"
    return o


def cyl(name, loc, r, depth, material, c, verts=32, rot=(0, 0, 0), bev=0.015):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=depth, location=loc, rotation=rot
    )
    o = bpy.context.object
    o.name = P + name
    for oc in list(o.users_collection):
        oc.objects.unlink(o)
    c.objects.link(o)
    o.data.materials.append(material)
    if bev:
        md = o.modifiers.new("edge_round", "BEVEL")
        md.width = bev
        md.segments = 2
    return o


def torus(name, loc, major, minor, material, c, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=40,
        minor_segments=10,
        location=loc,
        rotation=rot,
    )
    o = bpy.context.object
    o.name = P + name
    for oc in list(o.users_collection):
        oc.objects.unlink(o)
    c.objects.link(o)
    o.data.materials.append(material)
    return o


def beam(name, a, b, r, material, c):
    a, b = Vector(a), Vector(b)
    d = b - a
    o = cyl(name, (a + b) / 2, r, d.length, material, c, 24, bev=0.008)
    o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    return o


def curve_obj(name, pts, r, material, c, cyclic=False):
    cu = bpy.data.curves.new(P + name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    cu.resolution_u = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    sp.use_cyclic_u = cyclic
    o = bpy.data.objects.new(P + name, cu)
    c.objects.link(o)
    cu.materials.append(material)
    return o


def rounded_slab(name, cx, cy, w, l, z, h, r, material, c):
    verts = []
    faces = []
    seg = 8
    centers = (
        (cx - w / 2 + r, cy - l / 2 + r, -3 * math.pi / 4),
        (cx + w / 2 - r, cy - l / 2 + r, -math.pi / 4),
        (cx + w / 2 - r, cy + l / 2 - r, math.pi / 4),
        (cx - w / 2 + r, cy + l / 2 - r, 3 * math.pi / 4),
    )
    ring = []
    for ccx, ccy, start in centers:
        for i in range(seg + 1):
            a = start + i * (math.pi / 2 / seg)
            ring.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    for zz in (z - h / 2, z + h / 2):
        verts.extend((x, y, zz) for x, y in ring)
    n = len(ring)
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    for i in range(n):
        faces.append((i, (i + 1) % n, (i + 1) % n + n, i + n))
    me = bpy.data.meshes.new(P + name)
    me.from_pydata(verts, [], faces)
    me.materials.append(material)
    me.update()
    o = bpy.data.objects.new(P + name, me)
    c.objects.link(o)
    md = o.modifiers.new("edge_softness", "BEVEL")
    md.width = 0.018
    md.segments = 2
    return o


def instance(master, name, loc, parent, rot=0, scale=1):
    o = bpy.data.objects.new(P + name, None)
    parent.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = master
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = (scale,) * 3
    o["c2w_role"] = "instance"
    o["c2w_asset_id"] = master.name
    return o


def remove_old_court_playground():
    targets = []
    for c in list(bpy.data.collections):
        n = c.name.lower()
        if c.name.startswith("all44_04:") and any(
            k in n
            for k in (
                "basketball_court",
                "sports_detail",
                "playground",
                "playground_detail",
            )
        ):
            targets.append(c)
    removed = 0
    for c in targets:
        for o in list(c.all_objects):
            if o.users_collection and all(
                uc in targets or uc == c for uc in o.users_collection
            ):
                bpy.data.objects.remove(o, do_unlink=True)
                removed += 1
        bpy.data.collections.remove(c)
    return removed


def create_basketball_hoop(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_HOOP")
    lib["hoop_master"] = c.name
    metal, paint, glass, white = M["fence"], M["paint"], M["glass"], M["white"]
    cube("hoop_base", (0, 0, 0.10), (1.25, 1.55, 0.20), metal, c, 0.06)
    for x in (-0.48, 0.48):
        for y in (-0.62, 0.62):
            cyl("anchor_bolt", (x, y, 0.28), 0.045, 0.24, metal, c, 16)
    cyl("main_pole", (0, 0, 1.72), params["pole_radius"], 3.25, paint, c, 40, bev=0.035)
    beam(
        "gooseneck", (0, 0, 3.1), (params["overhang_distance"], 0, 3.65), 0.11, paint, c
    )
    for sy in (-0.42, 0.42):
        beam(
            "brace",
            (0.15, 0, 2.5),
            (params["overhang_distance"] - 0.2, sy, 3.42),
            0.055,
            paint,
            c,
        )
    x = params["overhang_distance"]
    cube(
        "backboard_glass",
        (x, 0, 3.52),
        (
            params["backboard_thickness"],
            params["backboard_width"],
            params["backboard_height"],
        ),
        glass,
        c,
        0.025,
    )
    for y, z, dy, dz in (
        (0, 2.98, 0.94, 0.025),
        (0, 4.06, 0.94, 0.025),
        (-0.94, 3.52, 0.025, 0.54),
        (0.94, 3.52, 0.025, 0.54),
    ):
        cube("board_frame", (x + 0.03, y, z), (0.045, dy, dz), white, c, 0.012)
    rimx = x + 0.48
    torus(
        "rim",
        (rimx, 0, 3.08),
        params["rim_radius"],
        params["rim_thickness"],
        M["orange"],
        c,
        (0, math.pi / 2, 0),
    )
    for i in range(12):
        a = 2 * math.pi * i / 12
        curve_obj(
            "net",
            [(rimx, 0.43 * math.sin(a), 3.08), (rimx + 0.03, 0.29 * math.sin(a), 2.73)],
            0.012,
            white,
            c,
        )
    return c


def create_sports_fence(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_FENCE_PANEL")
    lib["fence_master"] = c.name
    w = params["post_spacing"]
    h = params["fence_height"]
    for x in (-w / 2, w / 2):
        cube("post_footing", (x, 0, 0.16), (0.42, 0.42, 0.32), M["concrete"], c, 0.035)
        cyl(
            "fence_post",
            (x, 0, h / 2 + 0.3),
            params["post_radius"],
            h,
            M["fence"],
            c,
            28,
            bev=0.012,
        )
    for z in (0.35, h / 2, h + 0.28):
        beam(
            "fence_rail",
            (-w / 2, 0, z),
            (w / 2, 0, z),
            params["rail_radius"],
            M["fence"],
            c,
        )
    # Actual diamond wire mesh, not transparent panel.
    for i in range(10):
        y0 = -w / 2 + i * w / 9
        curve_obj(
            "mesh_wire",
            [(-w / 2, 0, 0.4 + i % 2 * 0.1), (w / 2, 0, h - 0.05 - i % 2 * 0.1)],
            0.009,
            M["wire"],
            c,
        )
        curve_obj(
            "mesh_wire",
            [(-w / 2, 0, h - 0.05 - i % 2 * 0.1), (w / 2, 0, 0.4 + i % 2 * 0.1)],
            0.009,
            M["wire"],
            c,
        )
    return c


def create_gate(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_FENCE_GATE")
    lib["gate_master"] = c.name
    w = params["gate_width"]
    h = params["gate_height"]
    for x in (-w / 2, w / 2):
        cyl("gate_stile", (x, 0, h / 2), 0.055, h, M["fence"], c, 24)
    for z in (0.12, h - 0.12):
        beam("gate_rail", (-w / 2, 0, z), (w / 2, 0, z), 0.045, M["fence"], c)
    for x in (-w / 2 + 0.15, w / 2 - 0.15):
        for z in (0.48, 1.12):
            torus("hinge", (x, 0, z), 0.09, 0.025, M["fence"], c, (math.pi / 2, 0, 0))
    cube("latch", (w / 2 - 0.12, -0.11, 1.12), (0.28, 0.16, 0.10), M["fence"], c, 0.025)
    cyl(
        "handle",
        (w / 2 - 0.23, -0.25, 1.15),
        0.025,
        0.35,
        M["wire"],
        c,
        16,
        (math.pi / 2, 0, 0),
    )
    return c


def create_slide_playset(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_SLIDE_PLAYSET")
    lib["slide_master"] = c.name
    ph = params["platform_height"]
    for x in (-1.15, 1.15):
        for y in (-1.0, 1.0):
            cyl("tower_post", (x, y, ph / 2), 0.075, ph, M["paint"], c, 28)
    cube("platform", (0, 0, ph), (2.6, 2.3, 0.18), M["paint"], c, 0.07)
    for y in (-1.05, 1.05):
        beam(
            "guardrail", (-1.2, y, ph + 0.85), (1.2, y, ph + 0.85), 0.045, M["paint"], c
        )
        for x in (-1.1, -0.55, 0, 0.55, 1.1):
            beam("baluster", (x, y, ph + 0.08), (x, y, ph + 0.85), 0.025, M["paint"], c)
    # Stair stringers, separate treads and grab rails.
    for y in (-0.55, 0.55):
        beam("stair_stringer", (-2.4, y, 0.15), (-1.15, y, ph), 0.055, M["fence"], c)
    for i in range(7):
        t = i / 6
        cube(
            "stair_tread",
            (-2.35 + 1.15 * t, 0, 0.2 + (ph - 0.2) * t),
            (0.34, 1.25, 0.10),
            M["plastic"],
            c,
            0.035,
        )
    # Curved slide ribbon generated as a thick parametric mesh.
    verts = []
    faces = []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x = 1.1 + params["slide_length"] * t
        z = ph * (1 - t) ** 1.45 + 0.18
        for y, zz in ((-0.55, 0), (0.55, 0), (-0.55, 0.12), (0.55, 0.12)):
            verts.append((x, y, z + zz))
    for i in range(steps):
        a = i * 4
        b = (i + 1) * 4
        faces.extend(
            (
                (a, b, b + 1, a + 1),
                (a + 2, a + 3, b + 3, b + 2),
                (a, a + 2, b + 2, b),
                (a + 1, b + 1, b + 3, a + 3),
            )
        )
    me = bpy.data.meshes.new(P + "slide_ribbon_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(M["slide"])
    me.update()
    o = bpy.data.objects.new(P + "slide_ribbon", me)
    c.objects.link(o)
    return c


def create_swing_set(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_SWING_SET")
    lib["swing_master"] = c.name
    for x in (-2.2, 2.2):
        beam("aframe_leg", (x, -1.4, 0), (x, 0, 2.75), 0.085, M["paint"], c)
        beam("aframe_leg", (x, 1.4, 0), (x, 0, 2.75), 0.085, M["paint"], c)
        cube(
            "ground_anchor", (x, -1.4, 0.08), (0.34, 0.34, 0.16), M["concrete"], c, 0.04
        )
        cube(
            "ground_anchor", (x, 1.4, 0.08), (0.34, 0.34, 0.16), M["concrete"], c, 0.04
        )
    beam("top_beam", (-2.4, 0, 2.75), (2.4, 0, 2.75), 0.11, M["paint"], c)
    for x in (-1.05, 1.05):
        for dx in (-0.28, 0.28):
            curve_obj(
                "swing_chain",
                [(x + dx, 0, 2.65), (x + dx, 0, 1.0)],
                0.012,
                M["wire"],
                c,
            )
        cube("swing_seat", (x, 0, 0.93), (0.85, 0.42, 0.10), M["rubber"], c, 0.055)
    return c


def create_climbing_frame(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_CLIMBING_FRAME")
    lib["climb_master"] = c.name
    apex = (0, 0, 2.8)
    base = [(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)]
    for i, p in enumerate(base):
        beam("climb_frame", p, apex, 0.07, M["paint"], c)
        cube("anchor", (p[0], p[1], 0.08), (0.32, 0.32, 0.16), M["concrete"], c, 0.04)
    for side in range(4):
        a = Vector(base[side])
        b = Vector(base[(side + 1) % 4])
        for i in range(1, 6):
            t = i / 6
            p1 = a.lerp(Vector(apex), t)
            p2 = b.lerp(Vector(apex), t)
            curve_obj("rope_horizontal", [p1, p2], 0.014, M["rope"], c)
        for i in range(1, 6):
            t = i / 6
            p = a.lerp(b, t)
            curve_obj("rope_vertical", [p, Vector(apex)], 0.014, M["rope"], c)
    return c


def create_shared_materials():
    return {
        "sport": mat("MAT_SPORT_SURFACE", (0.045, 0.20, 0.27), 0.68, noise=0.12),
        "sport2": mat("MAT_SPORT_INLAY", (0.12, 0.34, 0.25), 0.68, noise=0.08),
        "rubber": mat("MAT_PLAYGROUND_RUBBER", (0.12, 0.14, 0.15), 0.82, noise=0.14),
        "rubber2": mat("MAT_RUBBER_OCHRE", (0.48, 0.22, 0.07), 0.8, noise=0.12),
        "fence": mat("MAT_FENCE_METAL", (0.045, 0.055, 0.06), 0.34, 0.78, 0.02),
        "wire": mat("MAT_GALV_WIRE", (0.42, 0.46, 0.47), 0.27, 0.82, 0.01),
        "paving": mat("MAT_HARD_PAVING", (0.42, 0.39, 0.34), 0.86, noise=0.12),
        "concrete": mat("MAT_CONCRETE", (0.44, 0.43, 0.40), 0.88, noise=0.10),
        "paint": mat("MAT_PAINTED_METAL", (0.06, 0.26, 0.31), 0.46, 0.18, 0.04),
        "plastic": mat("MAT_PLASTIC_PLAYSET", (0.62, 0.27, 0.05), 0.52, noise=0.04),
        "slide": mat("MAT_SLIDE_STAINLESS", (0.55, 0.58, 0.59), 0.22, 0.86, 0.01),
        "rope": mat("MAT_ROPE", (0.44, 0.08, 0.055), 0.78, noise=0.05),
        "glass": mat("MAT_BACKBOARD_GLASS", (0.55, 0.72, 0.74), 0.12, noise=0),
        "white": mat("MAT_LINE_PAINT", (0.88, 0.89, 0.84), 0.58, noise=0.03),
        "orange": mat("MAT_RIM", (0.78, 0.16, 0.025), 0.4, 0.1, 0.02),
    }


def prepare_court_playground_asset_library(M):
    lib = collection("COURT_PLAYGROUND_ASSET_LIBRARY")
    lib["c2w_role"] = "master_library"
    hoop = create_basketball_hoop(
        {
            "pole_radius": 0.14,
            "backboard_width": 1.9,
            "backboard_height": 1.1,
            "backboard_thickness": 0.075,
            "rim_radius": 0.45,
            "rim_thickness": 0.028,
            "overhang_distance": 1.65,
        },
        M,
        lib,
    )
    fence = create_sports_fence(
        {
            "post_spacing": 3.0,
            "fence_height": 3.4,
            "post_radius": 0.065,
            "rail_radius": 0.038,
        },
        M,
        lib,
    )
    gate = create_gate({"gate_width": 2.2, "gate_height": 2.4}, M, lib)
    slide = create_slide_playset({"platform_height": 1.8, "slide_length": 3.7}, M, lib)
    swing = create_swing_set({}, M, lib)
    climb = create_climbing_frame({}, M, lib)
    return lib, {
        "hoop": hoop,
        "fence": fence,
        "gate": gate,
        "slide": slide,
        "swing": swing,
        "climb": climb,
    }


def generate_court(params, M, T, root):
    c = collection("COURT_SYSTEM", root)
    cx, cy = 31, -31
    L, W = params["court_length"], params["court_width"]
    rounded_slab(
        "court_subbase", cx, cy, L + 0.8, W + 0.8, 0.10, 0.20, 0.45, M["concrete"], c
    )
    rounded_slab(
        "court_shockpad", cx, cy, L + 0.3, W + 0.3, 0.22, 0.10, 0.38, M["rubber"], c
    )
    rounded_slab(
        "court_surface",
        cx,
        cy,
        L,
        W,
        0.31,
        params["surface_thickness"],
        params["corner_radius"],
        M["sport"],
        c,
    )
    # Real buffer apron of modular pavers.
    for i in range(30):
        x = 16.2 + i * 1.02
        cube(
            "buffer_paver", (x, -22.7, 0.20), (0.96, 0.72, 0.12), M["paving"], c, 0.025
        )
        cube(
            "buffer_paver", (x, -39.3, 0.20), (0.96, 0.72, 0.12), M["paving"], c, 0.025
        )
    z = 0.39
    lw = params["line_width"]
    x0, x1 = cx - L / 2, cx + L / 2
    y0, y1 = cy - W / 2, cy + W / 2
    for a, b in (
        ((x0, y0, z), (x1, y0, z)),
        ((x1, y0, z), (x1, y1, z)),
        ((x1, y1, z), (x0, y1, z)),
        ((x0, y1, z), (x0, y0, z)),
        ((cx, y0, z), (cx, y1, z)),
    ):
        curve_obj("court_line", [a, b], lw / 2, M["white"], c)
    curve_obj(
        "center_circle",
        [
            (
                cx + 1.8 * math.cos(2 * math.pi * i / 48),
                cy + 1.8 * math.sin(2 * math.pi * i / 48),
                z,
            )
            for i in range(48)
        ],
        lw / 2,
        M["white"],
        c,
        True,
    )
    for side, s in (("west", 1), ("east", -1)):
        bx = cx - s * (L / 2 - 4.0)
        cube("painted_key", (bx, cy, 0.37), (5.8, 5.0, 0.035), M["sport2"], c, 0.12)
        curve_obj(
            "free_throw_arc",
            [
                (
                    bx + s * 1.8 * math.cos(-math.pi / 2 + math.pi * i / 24),
                    cy + 1.8 * math.sin(-math.pi / 2 + math.pi * i / 24),
                    z,
                )
                for i in range(25)
            ],
            lw / 2,
            M["white"],
            c,
        )
    instc = collection("COURT_ASSET_INSTANCES", root)
    instance(T["hoop"], "hoop_w", (x0 + 1.4, cy, 0.38), instc, 0)
    instance(T["hoop"], "hoop_e", (x1 - 1.4, cy, 0.38), instc, math.pi)
    # Fence panels with two gates left open.
    for i, x in enumerate([18.5 + 3 * i for i in range(9)]):
        instance(T["fence"], f"fence_n:{i}", (x, y1 + 1.2, 0.2), instc, 0)
        instance(T["fence"], f"fence_s:{i}", (x, y0 - 1.2, 0.2), instc, 0)
    for i, y in enumerate([-36.5, -33.5, -30.5, -27.5, -24.5]):
        instance(T["fence"], f"fence_w:{i}", (x0 - 1.2, y, 0.2), instc, math.pi / 2)
        instance(T["fence"], f"fence_e:{i}", (x1 + 1.2, y, 0.2), instc, math.pi / 2)
    instance(T["gate"], "court_gate", (25.8, y1 + 1.15, 0.25), instc, 0)
    # Continuous trench drain.
    cube("court_drain", (cx, y0 - 0.65, 0.30), (L, 0.32, 0.16), M["fence"], c, 0.035)
    for i in range(70):
        cube(
            "drain_slot",
            (x0 + 0.2 + i * 0.4, y0 - 0.65, 0.40),
            (0.045, 0.26, 0.025),
            M["wire"],
            c,
            0.005,
        )
    return c


def create_playground_safety_surface(params, M, root):
    c = collection("PLAYGROUND_SAFETY_SURFACE", root)
    cx, cy = 15.6, -16.7
    W, L = params["playground_width"], params["playground_length"]
    rounded_slab(
        "rubber_base", cx, cy, W + 0.5, L + 0.5, 0.16, 0.22, 0.75, M["concrete"], c
    )
    # 1 m rubber tiles create real joints and controlled zones.
    for ix in range(int(W)):
        for iy in range(int(L)):
            x = cx - W / 2 + 0.5 + ix
            y = cy - L / 2 + 0.5 + iy
            ma = M["rubber2"] if (ix - iy) % 5 == 0 else M["rubber"]
            rounded_slab(
                f"rubber_tile:{ix}:{iy}",
                x,
                y,
                0.94,
                0.94,
                0.30,
                params["thickness"],
                0.10,
                ma,
                c,
            )
    return c


def generate_playground(params, M, T, root):
    create_playground_safety_surface(params, M, root)
    c = collection("PLAYGROUND_ASSET_INSTANCES", root)
    instance(T["slide"], "slide_playset", (14, -16.2, 0.38), c, math.pi)
    instance(T["swing"], "swing_set", (17.8, -20, 0.38), c, 0)
    instance(T["climb"], "climbing_frame", (12.4, -20, 0.38), c, 0.25)
    # Parent circulation and real curb transition to court gate.
    pc = collection("COURT_PLAYGROUND_CONNECTIONS", root)
    rounded_slab(
        "parent_path", 21.5, -20.8, 10.5, 2.0, 0.22, 0.16, 0.35, M["paving"], pc
    )
    rounded_slab("gate_path", 25.8, -23.2, 2.2, 5.0, 0.22, 0.16, 0.30, M["paving"], pc)
    for x, y, sx, sy in (
        (21.5, -19.75, 5.2, 0.10),
        (21.5, -21.85, 5.2, 0.10),
        (24.65, -23.2, 0.10, 2.5),
        (26.95, -23.2, 0.10, 2.5),
    ):
        cube(
            "path_curb", (x, y, 0.30), (sx * 2, sy * 2, 0.20), M["concrete"], pc, 0.025
        )
    return c


def populate_court_details(M, root):
    c = collection("FUNCTION_DRIVEN_DETAILS", root)
    # Court gate rule sign, bench pad, bin and bottle fountain.
    cube("rules_panel", (24.2, -22.0, 1.45), (1.25, 0.10, 0.82), M["paint"], c, 0.05)
    cyl("rules_post", (24.2, -22.0, 0.75), 0.045, 1.5, M["fence"], c)
    cube(
        "parent_bench_seat",
        (21.5, -20.2, 0.62),
        (3.0, 0.52, 0.12),
        M["plastic"],
        c,
        0.06,
    )
    for x in (20.3, 22.7):
        beam("bench_leg", (x, -20.2, 0.18), (x, -20.2, 0.58), 0.06, M["fence"], c)
    cyl("court_bin", (23.4, -21.1, 0.56), 0.32, 1.05, M["fence"], c, 32)
    torus("bin_opening", (23.4, -21.1, 1.10), 0.21, 0.045, M["wire"], c)
    cyl("drinking_fountain", (27.2, -22.1, 0.62), 0.18, 1.2, M["wire"], c, 32)
    torus("fountain_bowl", (27.2, -22.1, 1.22), 0.28, 0.06, M["wire"], c)
    return c


def populate_playground_details(M, root):
    c = collection("PLAYGROUND_FUNCTION_DETAILS", root)
    # Low perimeter fence and two shaded parent benches.
    for i, x in enumerate((11, 14, 17, 20)):
        beam(
            "play_fence_rail",
            (x, -11.5, 0.55),
            (x + 2.7, -11.5, 0.55),
            0.035,
            M["paint"],
            c,
        )
    for x in (11, 13.7, 16.4, 19.1, 21):
        cyl("play_fence_post", (x, -11.5, 0.55), 0.045, 1.1, M["paint"], c, 24)
    for bx in (12.2, 18.8):
        cube(
            "guardian_bench",
            (bx, -22.8, 0.62),
            (2.5, 0.55, 0.12),
            M["plastic"],
            c,
            0.06,
        )
        cube(
            "guardian_back",
            (bx, -23.05, 1.08),
            (2.5, 0.12, 0.70),
            M["plastic"],
            c,
            0.06,
        )
        for x in (bx - 1, bx + 1):
            beam(
                "guardian_leg", (x, -22.8, 0.18), (x, -22.8, 0.58), 0.055, M["fence"], c
            )
    return c


def render(path, res, samples):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.filepath = str(path)
    s.render.image_settings.file_format = "PNG"
    s.render.film_transparent = False
    s.view_settings.look = "AgX - Medium High Contrast"
    bpy.ops.render.render(write_still=True)


def aim(cam, loc, target, lens):
    cam.location = loc
    cam.data.lens = lens
    cam.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )


def main():
    cfg = args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    removed = remove_old_court_playground()
    M = create_shared_materials()
    lib, T = prepare_court_playground_asset_library(M)
    root = collection("COURT_PLAYGROUND_REBUILD")
    court = generate_court(
        {
            "court_length": 28,
            "court_width": 15,
            "line_width": 0.075,
            "corner_radius": 0.35,
            "surface_thickness": 0.16,
            "border_width": 0.8,
            "fence_height": 3.4,
            "fence_post_spacing": 3,
            "court_type": "basketball",
            "hoop_count": 2,
            "gate_count": 1,
            "light_pole_count": 4,
        },
        M,
        T,
        root,
    )
    play = generate_playground(
        {
            "playground_width": 10,
            "playground_length": 10,
            "safety_surface_type": "rubber_tile",
            "play_module_count": 3,
            "bench_count": 2,
            "shade_count": 1,
            "fence_type": "low",
            "age_group": "5-12",
            "path_connection_count": 2,
            "thickness": 0.14,
        },
        M,
        T,
        root,
    )
    populate_court_details(M, root)
    populate_playground_details(M, root)
    # Standalone court/playground validation, retain trees/lights/building from all44_04.
    old = {o: o.hide_render for o in bpy.context.scene.objects}
    for o in bpy.context.scene.objects:
        dep = any(
            c.name.startswith("assets:TreeFactory")
            or c.name.startswith("assets:GenericTreeFactory")
            for c in o.users_collection
        )
        keep = o.name.startswith((P, "all44_04:")) or o.type == "LIGHT" or dep
        o.hide_render = not keep
    cam = bpy.context.scene.camera
    aim(cam, (5, -5, 33), (26, -27, 1.4), 34)
    render(cfg.output / "layout_test.png", (720, 480), 2)
    if cfg.quality == "final":
        aim(cam, (8, -11, 18), (31, -31, 1.5), 46)
        render(cfg.output / "court_final.png", (1280, 720), 12)
        aim(cam, (4, -6, 12), (15.5, -17, 1.3), 46)
        render(cfg.output / "playground_final.png", (1280, 720), 12)
    for o, h in old.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h
    out = cfg.output / "urban_v3_all44_05.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    inst = [o for o in root.all_objects if o.instance_type == "COLLECTION"]
    stats = {
        "output": str(out),
        "removed_old_objects": removed,
        "master_assets": list(T),
        "collection_instances": len(inst),
        "shared_materials": list(M),
        "court_params": {"length": 28, "width": 15, "hoops": 2, "fence_height": 3.4},
        "playground_modules": ["slide_playset", "swing_set", "climbing_frame"],
        "boundary_intrusions": [],
        "floating_objects": [],
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_05_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
