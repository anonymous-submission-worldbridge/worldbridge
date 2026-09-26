"""ALL44-08-grass: dense reference-style lawn and horizontal basketball rims."""

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

import argparse, json, math, random, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
INPUT = ROOT / "infinigen/outputs/urban_v3_all44_08/urban_v3_all44_08.blend"
OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_08-grass"
P = "all44_08_grass:"


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
        tx.inputs["Detail"].default_value = 4
        tx.inputs["Roughness"].default_value = 0.62
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise
        bump.inputs["Distance"].default_value = 0.025
        m.node_tree.links.new(tx.outputs["Fac"], bump.inputs["Height"])
        m.node_tree.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        ramp = n.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*tuple(max(0, v * 0.88) for v in color), 1)
        ramp.color_ramp.elements[1].color = (
            *tuple(min(1, v * 1.08 + 0.015) for v in color),
            1,
        )
        m.node_tree.links.new(tx.outputs["Fac"], ramp.inputs["Fac"])
        m.node_tree.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        rn = n.new("ShaderNodeTexNoise")
        rn.inputs["Scale"].default_value = 7
        rn.inputs["Detail"].default_value = 2
        rr = n.new("ShaderNodeMapRange")
        rr.inputs["From Min"].default_value = 0
        rr.inputs["From Max"].default_value = 1
        rr.inputs["To Min"].default_value = max(0.08, rough - 0.09)
        rr.inputs["To Max"].default_value = min(1, rough + 0.09)
        m.node_tree.links.new(rn.outputs["Fac"], rr.inputs["Value"])
        m.node_tree.links.new(rr.outputs["Result"], b.inputs["Roughness"])
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


def line_ribbon(name, pts, width, z, material, c, cyclic=False):
    """A continuous flat paint stripe mesh; points are XY, never Curve fragments."""
    p = [Vector((x, y, z)) for x, y in pts]
    if cyclic:
        p.append(p[0])
    verts = []
    for i, v in enumerate(p):
        prev = p[i - 1] if i else (p[-2] if cyclic else p[0])
        nxt = p[i + 1] if i < len(p) - 1 else (p[1] if cyclic else p[-1])
        tangent = (nxt - prev).normalized()
        normal = Vector((-tangent.y, tangent.x, 0)) * width / 2
        verts.extend((tuple(v + normal), tuple(v - normal)))
    faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(p) - 1)]
    me = bpy.data.meshes.new(P + name + "_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(material)
    me.update()
    o = bpy.data.objects.new(P + name, me)
    c.objects.link(o)
    return o


def arc_points(cx, cy, r, a0, a1, n=64):
    return [
        (
            cx + r * math.cos(a0 + (a1 - a0) * i / n),
            cy + r * math.sin(a0 + (a1 - a0) * i / n),
        )
        for i in range(n + 1)
    ]


def uv_sphere(name, loc, r, material, c, segments=24):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=12, radius=r, location=loc
    )
    o = bpy.context.object
    o.name = P + name
    for oc in list(o.users_collection):
        oc.objects.unlink(o)
    c.objects.link(o)
    o.data.materials.append(material)
    for poly in o.data.polygons:
        poly.use_smooth = True
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
    targets = [o for o in bpy.data.objects if o.name.startswith("all44_08:")]
    removed = len(targets)
    if targets:
        bpy.data.batch_remove(targets)
    cols = [c for c in bpy.data.collections if c.name.startswith("all44_08:")]
    if cols:
        bpy.data.batch_remove(cols)
    return removed


def irregular_lawn(name, outline, z, depth, material, c):
    n = len(outline)
    verts = [(x, y, z) for x, y in outline] + [(x, y, z - depth) for x, y in outline]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        faces.append((i, (i + 1) % n, (i + 1) % n + n, i + n))
    me = bpy.data.meshes.new(P + name + "_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(material)
    me.update()
    o = bpy.data.objects.new(P + name, me)
    c.objects.link(o)
    be = o.modifiers.new("natural_edge_softness", "BEVEL")
    be.width = 0.035
    be.segments = 2
    return o


def grass_clump_master(name, M, seed, height=0.17, radius=1.10):
    """Dense 2.2 m lawn tile; hundreds of curved/crossed blades in one shared mesh."""
    rng = random.Random(seed)
    c = bpy.data.collections.new(P + "MASTER_" + name.upper())
    verts = []
    faces = []
    for i in range(720):
        x = rng.uniform(-radius, radius)
        y = rng.uniform(-radius, radius)
        h = height * rng.uniform(0.62, 1.25)
        w = rng.uniform(0.007, 0.014)
        a = rng.random() * math.pi
        dx, dy = math.cos(a), math.sin(a)
        lean = rng.uniform(-0.055, 0.055)
        # two-segment tapered blades produce the bent, tangled lawn silhouette in the reference.
        px, py = -dy * w, dx * w
        k = len(verts)
        verts.extend(
            (
                (x + px, y + py, 0),
                (x - px, y - py, 0),
                (x + lean * 0.45 + px * 0.55, y + lean * 0.25 + py * 0.55, h * 0.56),
                (x + lean, y + lean * 0.5, h),
                (x + w * dx, y + w * dy, 0),
                (x - w * dx, y - w * dy, 0),
                (
                    x + lean * 0.25 + w * 0.5 * dx,
                    y + lean * 0.45 + w * 0.5 * dy,
                    h * 0.52,
                ),
                (x + lean * 0.45, y + lean, h * 0.92),
            )
        )
        faces.extend(
            (
                (k, k + 1, k + 2),
                (k + 1, k + 3, k + 2),
                (k + 4, k + 5, k + 6),
                (k + 5, k + 7, k + 6),
            )
        )
    me = bpy.data.meshes.new(P + name + "_blade_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(M["grass_blade"])
    me.update()
    o = bpy.data.objects.new(P + name + "_blades", me)
    c.objects.link(o)
    return c


def generate_real_turf(M, T, root):
    c = collection("REALISTIC_TURF_SYSTEM", root)
    outline = [
        (10.0, -10.1),
        (47.3, -10.1),
        (47.9, -10.7),
        (47.9, -41.3),
        (47.25, -41.9),
        (10.2, -41.9),
        (9.65, -41.25),
        (9.65, -10.8),
    ]
    irregular_lawn("continuous_turf", outline, 0.135, 0.13, M["turf"], c)
    # Exposed soil/aggregate transition visible at the chamfered perimeter.
    for x, y, sx, sy in (
        (28.8, -9.92, 18.5, 0.10),
        (28.8, -42.05, 18.5, 0.10),
        (9.55, -26, 0.10, 15.2),
        (48.0, -26, 0.10, 15.2),
    ):
        cube("turf_edge", (x, y, 0.10), (sx * 2, sy * 2, 0.10), M["soil"], c, 0.03)
    instc = collection("GRASS_CLUMP_INSTANCES", root)
    placements = []
    # Seam-overlapped shared tiles cover the whole lawn continuously; hardscape above masks them.
    for ix in range(18):
        for iy in range(15):
            x = 10.75 + ix * 2.12
            y = -41.0 + iy * 2.12
            placements.append((x, y, 0.130, (ix * 17 + iy * 31) % 9 * 0.07))
    for i, p in enumerate(placements):
        instance(
            T["grass_a"] if (i % 5) else T["grass_b"],
            f"dense_lawn_tile:{i}",
            p[:3],
            instc,
            p[3],
            1.0,
        )
    return len(placements)


def create_basketball_hoop(params, M, lib):
    c = bpy.data.collections.new(P + "MASTER_HOOP")
    lib["hoop_master"] = c.name
    metal, paint, glass, white = M["fence"], M["paint"], M["glass"], M["white"]
    cube("hoop_base", (0, 0, 0.10), (1.25, 1.55, 0.20), metal, c, 0.06)
    cube("pole_pad", (0.16, 0, 1.0), (0.38, 0.56, 1.75), M["pad"], c, 0.07)
    for x in (-0.48, 0.48):
        for y in (-0.62, 0.62):
            cyl("anchor_bolt", (x, y, 0.28), 0.045, 0.24, metal, c, 16)
    cyl("main_pole", (0, 0, 1.72), params["pole_radius"], 3.25, paint, c, 40, bev=0.035)
    beam(
        "gooseneck", (0, 0, 3.1), (params["overhang_distance"], 0, 3.65), 0.11, paint, c
    )
    cyl("arm_pivot", (0.12, 0, 3.12), 0.17, 0.42, metal, c, 32, (math.pi / 2, 0, 0))
    cube(
        "board_mount",
        (params["overhang_distance"] - 0.10, 0, 3.50),
        (0.20, 0.48, 0.48),
        metal,
        c,
        0.035,
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
    # Torus is created in the XY plane, so no rotation: rim is parallel to court surface.
    rimx = x + 0.48
    torus(
        "rim",
        (rimx, 0, 3.05),
        params["rim_radius"],
        params["rim_thickness"],
        M["orange"],
        c,
        (0, 0, 0),
    )
    for sy in (-0.22, 0.22):
        beam(
            "rim_bracket",
            (x + 0.05, sy, 3.02),
            (rimx - 0.37, sy, 3.05),
            0.022,
            M["orange"],
            c,
        )
    for i in range(12):
        a = 2 * math.pi * i / 12
        curve_obj(
            "net",
            [
                (rimx + 0.43 * math.cos(a), 0.43 * math.sin(a), 3.05),
                (rimx + 0.26 * math.cos(a), 0.26 * math.sin(a), 2.63),
            ],
            0.009,
            white,
            c,
        )
    for j in range(3):
        z = 2.70 + j * 0.11
        r = 0.28 + j * 0.04
        curve_obj(
            "net_ring",
            [
                (
                    rimx + r * math.cos(2 * math.pi * i / 32),
                    r * math.sin(2 * math.pi * i / 32),
                    z,
                )
                for i in range(32)
            ],
            0.008,
            white,
            c,
            True,
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
    for z in (0.38, h + 0.26):
        beam(
            "fence_rail",
            (-w / 2, 0, z),
            (w / 2, 0, z),
            params["rail_radius"],
            M["fence"],
            c,
        )
    # Actual diamond wire mesh, not transparent panel.
    pitch = 0.24
    xl, xr = -w / 2, w / 2
    zb, zt = 0.38, h + 0.2
    # Clip both diagonal families exactly to the rectangular rail opening.
    for slope in (-1, 1):
        z0 = zb - w
        while z0 <= zt + w:
            hits = []
            for x in (xl, xr):
                z = z0 + slope * (x - xl)
                if zb - 1e-5 <= z <= zt + 1e-5:
                    hits.append((x, 0, z))
            for z in (zb, zt):
                x = xl + (z - z0) / slope
                if xl + 1e-5 < x < xr - 1e-5:
                    hits.append((x, 0, z))
            if len(hits) >= 2:
                curve_obj("mesh_wire", hits[:2], 0.0065, M["wire"], c)
            z0 += pitch
    cyl("post_cap", (-w / 2, 0, h + 0.30), 0.085, 0.06, M["fence"], c, 24)
    cyl("post_cap", (w / 2, 0, h + 0.30), 0.085, 0.06, M["fence"], c, 24)
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
    # Molded trough slide: curved longitudinal profile and concave cross-section.
    verts = []
    faces = []
    steps = 48
    cross = 8
    for i in range(steps + 1):
        t = i / steps
        x = 1.1 + params["slide_length"] * t
        z = 0.18 + (ph - 0.18) * (1 - t) ** 1.65 + 0.08 * math.sin(math.pi * t)
        for j in range(cross + 1):
            y = -0.58 + 1.16 * j / cross
            cup = 0.14 * (abs(y) / 0.58) ** 2
            verts.append((x, y, z + cup))
    for i in range(steps):
        for j in range(cross):
            a = i * (cross + 1) + j
            b = (i + 1) * (cross + 1) + j
            faces.append((a, b, b + 1, a + 1))
    me = bpy.data.meshes.new(P + "slide_ribbon_mesh")
    me.from_pydata(verts, [], faces)
    me.materials.append(M["slide"])
    me.update()
    o = bpy.data.objects.new(P + "slide_ribbon", me)
    c.objects.link(o)
    sol = o.modifiers.new("molded_shell_thickness", "SOLIDIFY")
    sol.thickness = 0.055
    sol.offset = -1
    bev = o.modifiers.new("molded_edge_round", "BEVEL")
    bev.width = 0.025
    bev.segments = 3
    railpts = []
    for side in (-1, 1):
        railpts = []
        for i in range(41):
            t = i / 40
            x = 1.1 + params["slide_length"] * t
            z = 0.18 + (ph - 0.18) * (1 - t) ** 1.65 + 0.08 * math.sin(math.pi * t)
            railpts.append((x, 0.58 * side, z + 0.16 * (1 - t) + 0.06))
        curve_obj("slide_side_rail", railpts, 0.045, M["plastic"], c)
    rounded_slab("slide_runout", 4.95, 0, 1.0, 1.12, 0.25, 0.10, 0.28, M["slide"], c)
    for y in (-0.55, 0.55):
        beam("slide_support", (2.5, y, 0.10), (2.5, y, 1.15), 0.045, M["fence"], c)
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
    for x in (-2.2, 2.2):
        cyl(
            "swing_joint",
            (x, 0, 2.75),
            0.16,
            0.34,
            M["fence"],
            c,
            32,
            (math.pi / 2, 0, 0),
        )
    for x in (-1.05, 1.05):
        for dx in (-0.28, 0.28):
            torus(
                "hanger",
                (x + dx, 0, 2.64),
                0.06,
                0.018,
                M["wire"],
                c,
                (math.pi / 2, 0, 0),
            )
            curve_obj(
                "swing_chain",
                [(x + dx, 0, 2.58), (x + dx, 0.05, 1.0)],
                0.010,
                M["wire"],
                c,
            )
        cube("swing_seat", (x, 0.05, 0.93), (0.85, 0.42, 0.10), M["pad"], c, 0.055)
        for dx in (-0.28, 0.28):
            cyl(
                "seat_shackle",
                (x + dx, 0.05, 1.0),
                0.025,
                0.12,
                M["wire"],
                c,
                16,
                (math.pi / 2, 0, 0),
            )
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
            curve_obj("rope_horizontal", [p1, p2], 0.022, M["rope"], c)
            for j in range(1, 6):
                uv_sphere("rope_node", p1.lerp(p2, j / 6), 0.045, M["connector"], c, 16)
        for i in range(1, 6):
            t = i / 6
            p = a.lerp(b, t)
            curve_obj("rope_vertical", [p, Vector(apex)], 0.022, M["rope"], c)
    cyl("mast_tensioner", (0, 0, 2.66), 0.13, 0.32, M["connector"], c, 32)
    return c


def create_site_furniture(M, lib):
    bench = bpy.data.collections.new(P + "MASTER_BENCH")
    for y, z in ((0, 0.62), (0.22, 1.05)):
        for i in range(7):
            cube(
                "timber_slat",
                (-1.15 + i * 0.38, y, z),
                (0.32, 0.10 if z > 1 else 0.55, 0.09),
                M["timber"],
                bench,
                0.035,
            )
    for x in (-0.9, 0.9):
        beam("bench_leg", (x, -0.18, 0.16), (x, 0, 0.60), 0.055, M["fence"], bench)
        beam("back_support", (x, 0.12, 0.55), (x, 0.22, 1.28), 0.045, M["fence"], bench)
        cube(
            "bench_foot",
            (x, -0.12, 0.08),
            (0.34, 0.30, 0.12),
            M["concrete"],
            bench,
            0.035,
        )
    binm = bpy.data.collections.new(P + "MASTER_BIN")
    cyl("bin_body", (0, 0, 0.52), 0.30, 1.02, M["fence"], binm, 40)
    torus("bin_rim", (0, 0, 1.04), 0.24, 0.035, M["wire"], binm)
    cube("bin_opening", (0, -0.27, 0.82), (0.34, 0.035, 0.22), M["joint"], binm, 0.025)
    cube("bin_base", (0, 0, 0.07), (0.48, 0.48, 0.14), M["concrete"], binm, 0.05)
    lamp = bpy.data.collections.new(P + "MASTER_PATH_LIGHT")
    cube("lamp_base", (0, 0, 0.10), (0.52, 0.52, 0.20), M["concrete"], lamp, 0.06)
    cyl("lamp_pole", (0, 0, 2.25), 0.065, 4.3, M["fence"], lamp, 32)
    beam("lamp_arm", (0, 0, 4.34), (0.55, 0, 4.34), 0.045, M["fence"], lamp)
    cube("lamp_head", (0.66, 0, 4.28), (0.46, 0.24, 0.15), M["paint"], lamp, 0.055)
    cube("lamp_lens", (0.66, 0, 4.19), (0.32, 0.18, 0.025), M["glass"], lamp, 0.015)
    return {"bench": bench, "bin": binm, "lamp": lamp}


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
        "pad": mat("MAT_IMPACT_PAD", (0.035, 0.055, 0.07), 0.72, noise=0.07),
        "connector": mat("MAT_ROPE_CONNECTOR", (0.16, 0.18, 0.18), 0.28, 0.72, 0.02),
        "joint": mat("MAT_EPDM_JOINT", (0.018, 0.022, 0.024), 0.9, noise=0.02),
        "timber": mat("MAT_SITE_TIMBER", (0.34, 0.16, 0.065), 0.68, noise=0.055),
        "wear": mat("MAT_COURT_WEAR", (0.13, 0.31, 0.36), 0.78, noise=0.09),
        "turf": mat("MAT_NATURAL_TURF", (0.075, 0.32, 0.045), 0.88, noise=0.24),
        "grass_blade": mat("MAT_GRASS_BLADES", (0.055, 0.38, 0.025), 0.80, noise=0.12),
        "soil": mat("MAT_TURF_SOIL_EDGE", (0.15, 0.095, 0.045), 0.94, noise=0.18),
        "slide": mat("MAT_SLIDE_MOLDED", (0.72, 0.25, 0.035), 0.42, 0.02, 0.035),
        "rope": mat("MAT_ROPE", (0.34, 0.045, 0.028), 0.78, noise=0.05),
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
    furniture = create_site_furniture(M, lib)
    grass_a = grass_clump_master("DENSE_LAWN_TILE_A", M, 817, 0.11, 1.10)
    grass_b = grass_clump_master("DENSE_LAWN_TILE_B", M, 1447, 0.095, 1.10)
    return lib, {
        "hoop": hoop,
        "fence": fence,
        "gate": gate,
        "slide": slide,
        "swing": swing,
        "climb": climb,
        "grass_a": grass_a,
        "grass_b": grass_b,
        **furniture,
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
    # Restrained abrasion where feet pivot most; thin irregular ribbons avoid decal-flat uniformity.
    for j, (wx, wy, ang, ln) in enumerate(
        (
            (24.8, -31, 0.18, 1.3),
            (37.2, -30.6, -0.22, 1.1),
            (30.4, -27.4, 0.08, 0.75),
            (31.8, -34.5, -0.12, 0.8),
        )
    ):
        pts = [
            (wx - ln / 2, wy),
            (wx, wy + 0.035 * math.sin(j + 1)),
            (wx + ln / 2, wy + 0.02),
        ]
        line_ribbon("court_wear", pts, 0.055, 0.407, M["wear"], c)
    # Real buffer apron of modular pavers.
    for i in range(30):
        x = 16.2 + i * 1.02
        cube(
            "buffer_paver", (x, -22.7, 0.20), (0.96, 0.72, 0.12), M["paving"], c, 0.025
        )
        cube(
            "buffer_paver", (x, -39.3, 0.20), (0.96, 0.72, 0.12), M["paving"], c, 0.025
        )
    z = 0.405
    lw = params["line_width"]
    x0, x1 = cx - L / 2, cx + L / 2
    y0, y1 = cy - W / 2, cy + W / 2
    # FIBA 28x15 m geometry: continuous mesh ribbons, regulation dimensions.
    line_ribbon(
        "boundary", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], lw, z, M["white"], c, True
    )
    line_ribbon("centre_line", [(cx, y0), (cx, y1)], lw, z, M["white"], c)
    line_ribbon(
        "centre_circle",
        arc_points(cx, cy, 1.80, 0, 2 * math.pi, 96),
        lw,
        z,
        M["white"],
        c,
        True,
    )
    for s in (-1, 1):
        baseline = x0 if s == 1 else x1
        hoopx = baseline + s * 1.575
        ftx = baseline + s * 5.80
        # Restricted lane 4.9 m wide and free throw semicircle radius 1.8 m.
        rounded_slab(
            "key_inlay",
            (baseline + ftx) / 2,
            cy,
            abs(ftx - baseline),
            4.9,
            0.386,
            0.028,
            0.03,
            M["sport2"],
            c,
        )
        line_ribbon(
            "key_top", [(ftx, cy - 2.45), (ftx, cy + 2.45)], lw, z, M["white"], c
        )
        line_ribbon(
            "key_side_a",
            [(baseline, cy - 2.45), (ftx, cy - 2.45)],
            lw,
            z,
            M["white"],
            c,
        )
        line_ribbon(
            "key_side_b",
            [(baseline, cy + 2.45), (ftx, cy + 2.45)],
            lw,
            z,
            M["white"],
            c,
        )
        a0 = -math.pi / 2 if s == 1 else math.pi / 2
        a1 = math.pi / 2 if s == 1 else 3 * math.pi / 2
        line_ribbon(
            "free_throw_arc",
            arc_points(ftx, cy, 1.80, a0, a1, 64),
            lw,
            z,
            M["white"],
            c,
        )
        # 6.75 m three-point arc joined to straight 0.90 m sideline offsets.
        dy = W / 2 - 0.90
        dx = math.sqrt(6.75**2 - dy**2)
        joinx = hoopx + s * dx
        ang = math.atan2(dy, dx)
        arc = (
            arc_points(hoopx, cy, 6.75, -ang, ang, 96)
            if s == 1
            else arc_points(hoopx, cy, 6.75, math.pi - ang, math.pi + ang, 96)
        )
        if s == -1:
            arc = list(reversed(arc))
        line_ribbon(
            "three_point",
            [(baseline, cy - dy), (joinx, cy - dy)]
            + arc[1:-1]
            + [(joinx, cy + dy), (baseline, cy + dy)],
            lw,
            z,
            M["white"],
            c,
        )
        line_ribbon(
            "no_charge",
            arc_points(hoopx, cy, 1.25, -math.pi / 2, math.pi / 2, 48)
            if s == 1
            else arc_points(hoopx, cy, 1.25, math.pi / 2, 3 * math.pi / 2, 48),
            lw,
            z,
            M["white"],
            c,
        )
    instc = collection("COURT_ASSET_INSTANCES", root)
    instance(T["hoop"], "hoop_w", (x0 - 0.55, cy, 0.38), instc, 0)
    instance(T["hoop"], "hoop_e", (x1 + 0.55, cy, 0.38), instc, math.pi)
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
    # Continuous poured EPDM, flush zones and hairline construction joints.
    rounded_slab(
        "epdm_main", cx, cy, W, L, 0.30, params["thickness"], 0.48, M["rubber"], c
    )
    rounded_slab(
        "epdm_warm_zone",
        cx - 2.7,
        cy + 2.4,
        3.8,
        3.2,
        0.374,
        0.010,
        0.7,
        M["rubber2"],
        c,
    )
    rounded_slab(
        "epdm_swing_zone",
        cx + 2.4,
        cy - 2.6,
        4.0,
        3.0,
        0.374,
        0.010,
        1.0,
        M["rubber2"],
        c,
    )
    for x in (cx - 2.5, cx, cx + 2.5):
        line_ribbon(
            "epdm_joint",
            [(x, cy - L / 2 + 0.3), (x, cy + L / 2 - 0.3)],
            0.016,
            0.381,
            M["joint"],
            c,
        )
    for y in (cy - 2.5, cy, cy + 2.5):
        line_ribbon(
            "epdm_joint",
            [(cx - W / 2 + 0.3, y), (cx + W / 2 - 0.3, y)],
            0.016,
            0.381,
            M["joint"],
            c,
        )
    # Thin metal edge restraint.
    for a, b in (
        ((cx - W / 2, cy - L / 2), (cx + W / 2, cy - L / 2)),
        ((cx + W / 2, cy - L / 2), (cx + W / 2, cy + L / 2)),
        ((cx + W / 2, cy + L / 2), (cx - W / 2, cy + L / 2)),
        ((cx - W / 2, cy + L / 2), (cx - W / 2, cy - L / 2)),
    ):
        line_ribbon("edge_restraint", [a, b], 0.055, 0.386, M["wire"], c)
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


def populate_court_details(M, T, root):
    c = collection("FUNCTION_DRIVEN_DETAILS", root)
    # Court gate rule sign, bench pad, bin and bottle fountain.
    cube("rules_panel", (24.2, -22.0, 1.45), (1.25, 0.10, 0.82), M["paint"], c, 0.05)
    cyl("rules_post", (24.2, -22.0, 0.75), 0.045, 1.5, M["fence"], c)
    instance(T["bench"], "court_bench", (21.5, -20.2, 0.18), c, 0)
    instance(T["bin"], "court_bin", (23.6, -21.0, 0.18), c, 0)
    instance(T["lamp"], "court_entry_light", (26.7, -22.0, 0.18), c, math.pi)
    cyl("drinking_fountain", (27.2, -22.1, 0.62), 0.18, 1.2, M["wire"], c, 32)
    torus("fountain_bowl", (27.2, -22.1, 1.22), 0.28, 0.06, M["wire"], c)
    return c


def populate_playground_details(M, T, root):
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
    for i, bx in enumerate((12.2, 18.8)):
        instance(T["bench"], f"guardian_bench:{i}", (bx, -22.8, 0.18), c, 0)
    instance(T["bin"], "playground_bin", (20.5, -22.0, 0.18), c, 0)
    instance(T["lamp"], "playground_edge_light", (10.5, -12.0, 0.18), c, -math.pi / 2)
    # Low tree-pit edge at the existing mature tree, separating roots from circulation.
    for a0 in range(0, 360, 30):
        a = math.radians(a0)
        b = math.radians(a0 + 27)
        beam(
            "tree_pit_edge",
            (19.5 + 1.15 * math.cos(a), -14.2 + 1.15 * math.sin(a), 0.28),
            (19.5 + 1.15 * math.cos(b), -14.2 + 1.15 * math.sin(b), 0.28),
            0.075,
            M["concrete"],
            c,
        )
    return c


def render(path, res, samples):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.use_persistent_data = True
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
    grass_instances = generate_real_turf(M, T, root)
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
    populate_court_details(M, T, root)
    populate_playground_details(M, T, root)
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
    render(cfg.output / "overall_activity_zone.png", (720, 480), 2)
    if cfg.quality == "final":
        aim(cam, (8, -11, 18), (31, -31, 1.5), 46)
        render(cfg.output / "court_final.png", (1280, 720), 12)
        aim(cam, (4, -6, 12), (15.5, -17, 1.3), 46)
        render(cfg.output / "playground_final.png", (1280, 720), 12)
        aim(cam, (28.8, -2.5, 10.5), (28.8, -26, 1.2), 48)
        render(cfg.output / "activity_zone_front.png", (1280, 720), 10)
        aim(cam, (28.8, -49.0, 10.5), (28.8, -26, 1.2), 48)
        render(cfg.output / "activity_zone_rear.png", (1280, 720), 10)
        aim(cam, (2.5, -26, 10.5), (28.8, -26, 1.2), 48)
        render(cfg.output / "activity_zone_left.png", (1280, 720), 10)
        aim(cam, (55.0, -26, 10.5), (28.8, -26, 1.2), 48)
        render(cfg.output / "activity_zone_right.png", (1280, 720), 10)
    for o, h in old.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h
    out = cfg.output / "urban_v3_all44_08-grass.blend"
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
        "dense_lawn_tile_instances": grass_instances,
        "grass_blades_per_tile": 720,
        "basketball_rims_horizontal": True,
        "removed_green_spheres_and_blocks": True,
        "boundary_intrusions": [],
        "floating_objects": [],
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_08_GRASS_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
