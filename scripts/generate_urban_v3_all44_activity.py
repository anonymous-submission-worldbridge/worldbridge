"""Add an instanced southeast community activity quarter to urban_v3_all41."""

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


import argparse
import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
DEFAULT_INPUT = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
DEFAULT_OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_01"
PREFIX = "all44_01:"
BOUNDS = (9.7, 48.0, -42.0, -9.7)


def parse_args():
    import sys

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--skip-final-render", action="store_true")
    return p.parse_args(argv)


def material(name, color, rough=0.65, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.get(PREFIX + name) or bpy.data.materials.new(PREFIX + name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    if color[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = color[3]
        mat.surface_render_method = "DITHERED"
    return mat


def make_collection(name, parent=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def cube_mesh(name, mat):
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
        (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    return mesh


def cylinder_mesh(name, mat, sides=12):
    verts = []
    for z in (-0.5, 0.5):
        verts.extend(
            (
                math.cos(2 * math.pi * i / sides) * 0.5,
                math.sin(2 * math.pi * i / sides) * 0.5,
                z,
            )
            for i in range(sides)
        )
    faces = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    faces.extend(
        (i, (i + 1) % sides, (i + 1) % sides + sides, i + sides) for i in range(sides)
    )
    mesh = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    return mesh


def uv_sphere_mesh(name, mat, segments=16, rings=10):
    verts = [(0, 0, -0.5)]
    for j in range(1, rings):
        phi = -math.pi / 2 + math.pi * j / rings
        z, r = 0.5 * math.sin(phi), 0.5 * math.cos(phi)
        verts.extend(
            (
                r * math.cos(2 * math.pi * i / segments),
                r * math.sin(2 * math.pi * i / segments),
                z,
            )
            for i in range(segments)
        )
    verts.append((0, 0, 0.5))
    faces = []
    for i in range(segments):
        faces.append((0, 1 + i, 1 + (i + 1) % segments))
    for j in range(rings - 2):
        a, b = 1 + j * segments, 1 + (j + 1) * segments
        for i in range(segments):
            faces.append((a + i, b + i, b + (i + 1) % segments, a + (i + 1) % segments))
    top = len(verts) - 1
    base = 1 + (rings - 2) * segments
    for i in range(segments):
        faces.append((base + i, top, base + (i + 1) % segments))
    mesh = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    return mesh


def torus_mesh(name, mat, major=0.5, minor=0.045, major_steps=24, minor_steps=8):
    verts, faces = [], []
    for i in range(major_steps):
        a = 2 * math.pi * i / major_steps
        for j in range(minor_steps):
            b = 2 * math.pi * j / minor_steps
            rr = major + minor * math.cos(b)
            verts.append((rr * math.cos(a), rr * math.sin(a), minor * math.sin(b)))
    for i in range(major_steps):
        for j in range(minor_steps):
            n = minor_steps
            faces.append(
                (
                    i * n + j,
                    ((i + 1) % major_steps) * n + j,
                    ((i + 1) % major_steps) * n + (j + 1) % n,
                    i * n + (j + 1) % n,
                )
            )
    mesh = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    return mesh


def add_noise_surface(mat, scale=6.0, strength=0.18, detail=3.0):
    """Add reusable procedural albedo variation and micro-bump to a material."""
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf or nodes.get(PREFIX + "surface_noise"):
        return
    noise = nodes.new("ShaderNodeTexNoise")
    noise.name = PREFIX + "surface_noise"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    ramp = nodes.new("ShaderNodeValToRGB")
    base = tuple(bsdf.inputs["Base Color"].default_value)
    dark = tuple(max(0, c * (1 - strength)) for c in base[:3]) + (1,)
    light = tuple(min(1, c * (1 + strength)) for c in base[:3]) + (1,)
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].color = light
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.08
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


class Assets:
    def __init__(self):
        self.meshes = {}
        self.counts = {}

    def add(self, key, mesh):
        self.meshes[key] = mesh

    def instance(self, key, name, loc, scale, coll, rot=0.0, mat=None, role=None):
        obj = bpy.data.objects.new(PREFIX + name, self.meshes[key])
        coll.objects.link(obj)
        obj.location = loc
        obj.scale = scale
        obj.rotation_euler[2] = rot
        if mat is not None:
            obj.material_slots[0].link = "OBJECT"
            obj.material_slots[0].material = mat
        obj["all44_asset_key"] = key
        obj["all44_linked_instance"] = True
        if role:
            obj["all44_role"] = role
        self.counts[key] = self.counts.get(key, 0) + 1
        return obj


def text_object(body, name, loc, size, mat, coll, rot=(math.pi / 2, 0, 0)):
    curve = bpy.data.curves.new(PREFIX + "text:" + name, "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.025
    curve.bevel_depth = 0.005
    curve.materials.append(mat)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    return obj


def segment(A, key, name, p1, p2, width, z, coll, mat=None):
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    return A.instance(
        key,
        name,
        ((x1 + x2) / 2, (y1 + y2) / 2, z),
        (length / 2, width / 2, 0.018),
        coll,
        math.atan2(y2 - y1, x2 - x1),
        mat=mat,
    )


def build_scene():
    root = make_collection("community_activity")
    ground = make_collection("ground", root)
    court = make_collection("basketball_court", root)
    play = make_collection("playground", root)
    building = make_collection("service_building", root)
    paths = make_collection("accessible_paths", root)
    decor = make_collection("landscape_and_furniture", root)

    mats = {
        "concrete": material("concrete", (0.46, 0.43, 0.38, 1), 0.86),
        "path": material("path", (0.58, 0.55, 0.49, 1), 0.83),
        "court": material("court_blue", (0.045, 0.18, 0.32, 1), 0.72),
        "court_green": material("court_key", (0.05, 0.33, 0.25, 1), 0.70),
        "white": material("marking_white", (0.93, 0.92, 0.84, 1), 0.58),
        "metal": material("dark_metal", (0.025, 0.035, 0.04, 1), 0.42, 0.45),
        "fence": material("fence", (0.09, 0.12, 0.12, 0.42), 0.46, 0.35),
        "orange": material("rim_orange", (0.85, 0.16, 0.018, 1), 0.38),
        "backboard": material("backboard", (0.78, 0.86, 0.86, 0.68), 0.22),
        "rubber": material("play_rubber", (0.28, 0.12, 0.33, 1), 0.78),
        "yellow": material("play_yellow", (0.96, 0.55, 0.025, 1), 0.48),
        "red": material("play_red", (0.72, 0.035, 0.025, 1), 0.48),
        "cyan": material("play_cyan", (0.02, 0.43, 0.58, 1), 0.45),
        "cream": material("building_cream", (0.72, 0.66, 0.54, 1), 0.76),
        "brick": material("building_brick", (0.42, 0.16, 0.075, 1), 0.82),
        "glass": material("glass", (0.08, 0.22, 0.28, 0.38), 0.12),
        "warm": material("interior_light", (1.0, 0.56, 0.18, 1), 0.42, emission=2.0),
        "wood": material("bench_wood", (0.28, 0.11, 0.035, 1), 0.72),
        "leaf": material("leaf", (0.045, 0.25, 0.07, 1), 0.86),
        "leaf2": material("leaf_variant", (0.08, 0.34, 0.09, 1), 0.84),
        "bark": material("bark", (0.14, 0.065, 0.026, 1), 0.92),
        "softgreen": material("landscape", (0.075, 0.22, 0.055, 1), 0.94),
    }
    A = Assets()
    for key, mat, shape in [
        ("box", mats["concrete"], "cube"),
        ("line", mats["white"], "cube"),
        ("pole", mats["metal"], "cylinder"),
        ("rail", mats["metal"], "cube"),
        ("panel", mats["fence"], "cube"),
        ("rim", mats["orange"], "cylinder"),
        ("board", mats["backboard"], "cube"),
        ("seat", mats["wood"], "cube"),
        ("trunk", mats["bark"], "cylinder"),
        ("crown", mats["leaf"], "cylinder"),
        ("lamp", mats["warm"], "cube"),
        ("bin", mats["metal"], "cylinder"),
        ("playbar", mats["yellow"], "cylinder"),
        ("playbox", mats["red"], "cube"),
    ]:
        A.add(
            key,
            cylinder_mesh(key, mat, 12) if shape == "cylinder" else cube_mesh(key, mat),
        )
    A.add("leaf_cluster", uv_sphere_mesh("leaf_cluster", mats["leaf"], 18, 11))
    A.add("ball", uv_sphere_mesh("ball", mats["orange"], 20, 12))
    A.add("hoop_ring", torus_mesh("hoop_ring", mats["orange"], 0.5, 0.055, 32, 8))
    for key in (
        "concrete",
        "path",
        "court",
        "rubber",
        "cream",
        "brick",
        "wood",
        "softgreen",
    ):
        add_noise_surface(
            mats[key],
            8 if key not in {"court", "rubber"} else 28,
            0.10 if key in {"court", "rubber"} else 0.18,
        )

    # Parcel base and distinct functional surfaces.
    A.instance(
        "box",
        "parcel_base",
        (28.85, -25.85, 0.035),
        (19.05, 16.05, 0.035),
        ground,
        mat=mats["softgreen"],
    )
    A.instance(
        "box",
        "court_surface",
        (31, -31, 0.09),
        (14, 7.5, 0.09),
        court,
        mat=mats["court"],
        role="sport",
    )
    # Slightly inset painted keys and a physically separate perimeter curb.
    for side, x in (("west", 20.0), ("east", 42.0)):
        A.instance(
            "box",
            side + ":painted_key",
            (x, -31, 0.195),
            (3.0, 3.2, 0.012),
            court,
            mat=mats["court_green"],
        )
    for i, (x, y, sx, sy) in enumerate(
        (
            (31, -23.2, 14.35, 0.12),
            (31, -38.8, 14.35, 0.12),
            (16.7, -31, 0.12, 7.7),
            (45.3, -31, 0.12, 7.7),
        )
    ):
        A.instance(
            "box",
            f"court_curb:{i}",
            (x, y, 0.22),
            (sx, sy, 0.14),
            court,
            mat=mats["concrete"],
        )
    A.instance(
        "box",
        "play_surface",
        (15.6, -17.0, 0.10),
        (5.1, 5.1, 0.10),
        play,
        mat=mats["rubber"],
        role="play",
    )
    A.instance(
        "box",
        "service_apron",
        (36.5, -16.6, 0.09),
        (10.0, 5.6, 0.09),
        ground,
        mat=mats["concrete"],
    )

    # Accessible path spine: street -> building -> play -> court.
    A.instance(
        "box",
        "entry_walk",
        (27.5, -11.4, 0.12),
        (17.5, 1.15, 0.08),
        paths,
        mat=mats["path"],
    )
    A.instance(
        "box",
        "north_south_walk",
        (26.4, -19.0, 0.12),
        (1.15, 6.8, 0.08),
        paths,
        mat=mats["path"],
    )
    A.instance(
        "box",
        "court_entry_walk",
        (26.4, -23.8, 0.12),
        (2.4, 1.15, 0.08),
        paths,
        mat=mats["path"],
    )
    A.instance(
        "box",
        "accessible_ramp",
        (33.0, -12.9, 0.24),
        (3.0, 1.25, 0.16),
        paths,
        mat=mats["path"],
    )

    # Court markings are shared low-cost strips. Court spans x=17..45, y=-38.5..-23.5.
    for i, (p1, p2, w) in enumerate(
        [
            ((17, -23.5), (45, -23.5), 0.10),
            ((45, -23.5), (45, -38.5), 0.10),
            ((45, -38.5), (17, -38.5), 0.10),
            ((17, -38.5), (17, -23.5), 0.10),
            ((31, -23.5), (31, -38.5), 0.08),
            ((17, -27.8), (22.8, -27.8), 0.07),
            ((17, -34.2), (22.8, -34.2), 0.07),
            ((22.8, -27.8), (22.8, -34.2), 0.07),
            ((39.2, -27.8), (45, -27.8), 0.07),
            ((39.2, -34.2), (45, -34.2), 0.07),
            ((39.2, -27.8), (39.2, -34.2), 0.07),
        ]
    ):
        segment(A, "line", f"court_line:{i}", p1, p2, w, 0.20, court)
    # Mid-circle and free-throw arcs approximated by short shared segments.
    for label, cx, cy, r, start, end in [
        ("center", 31, -31, 1.8, 0, 2 * math.pi),
        ("west_arc", 22.8, -31, 1.8, -math.pi / 2, math.pi / 2),
        ("east_arc", 39.2, -31, 1.8, math.pi / 2, 3 * math.pi / 2),
    ]:
        steps = 20 if label == "center" else 10
        pts = [
            (
                cx + r * math.cos(start + (end - start) * i / steps),
                cy + r * math.sin(start + (end - start) * i / steps),
            )
            for i in range(steps + 1)
        ]
        for i in range(steps):
            segment(A, "line", f"{label}:{i}", pts[i], pts[i + 1], 0.07, 0.20, court)

    # Two modular hoops.
    for side, x, face in [("west", 18.5, 0), ("east", 43.5, math.pi)]:
        A.instance(
            "pole", side + ":hoop_post", (x, -31, 1.55), (0.16, 0.16, 1.55), court
        )
        A.instance(
            "board",
            side + ":backboard",
            (x + (1.0 if side == "west" else -1.0), -31, 3.05),
            (0.08, 1.0, 0.65),
            court,
        )
        rimx = x + (1.45 if side == "west" else -1.45)
        A.instance(
            "hoop_ring", side + ":rim", (rimx, -31, 2.82), (0.46, 0.46, 0.46), court
        )
        A.instance(
            "rail",
            side + ":support",
            (x + (0.55 if side == "west" else -0.55), -31, 2.85),
            (0.65, 0.07, 0.07),
            court,
        )
        # Backboard frame, target rectangle, fasteners and tapered cord net.
        bx = x + (1.0 if side == "west" else -1.0)
        for j, (yy, zz, sy, sz) in enumerate(
            (
                (-31, 2.42, 1.08, 0.035),
                (-31, 3.68, 1.08, 0.035),
                (-32.04, 3.05, 0.035, 0.65),
                (-29.96, 3.05, 0.035, 0.65),
            )
        ):
            A.instance(
                "rail", f"{side}:board_frame:{j}", (bx, yy, zz), (0.045, sy, sz), court
            )
        for j, ang in enumerate(range(0, 360, 45)):
            a = math.radians(ang)
            top = (rimx, -31 + 0.42 * math.sin(a), 2.79)
            bot = (rimx, -31 + 0.23 * math.sin(a), 2.22)
            mid = ((top[0] + bot[0]) / 2, (top[1] + bot[1]) / 2, (top[2] + bot[2]) / 2)
            cord = A.instance(
                "pole",
                f"{side}:net_cord:{j}",
                mid,
                (0.014, 0.014, 0.30),
                court,
                mat=mats["white"],
            )
        for j, dy in enumerate((-0.63, 0.63)):
            A.instance(
                "rim",
                f"{side}:board_bolt:{j}",
                (bx + (0.09 if side == "west" else -0.09), -31 + dy, 3.05),
                (0.045, 0.045, 0.025),
                court,
                math.pi / 2,
                mat=mats["metal"],
            )

    # Modular fence panels, leaving a 2.4 m gate at the northwest corner.
    fence_specs = []
    for x in range(19, 46, 3):
        fence_specs.extend([(x, -22.9, 3, 0), (x, -39.1, 3, 0)])
    for y in (-36.5, -33.5, -30.5, -27.5, -24.5):
        fence_specs.append((16.4, y, 3, math.pi / 2))
        fence_specs.append((45.6, y, 3, math.pi / 2))
    for i, (x, y, length, rot) in enumerate(fence_specs):
        A.instance(
            "panel",
            f"court_fence:{i}",
            (x, y, 1.8),
            (length / 2, 0.025, 1.8),
            court,
            rot,
        )
        for suffix, offset in (("a", -length / 2), ("b", length / 2)):
            dx, dy = (offset * math.cos(rot), offset * math.sin(rot))
            A.instance(
                "pole",
                f"court_fence_post:{i}:{suffix}",
                (x + dx, y + dy, 1.8),
                (0.055, 0.055, 1.8),
                court,
            )
        # Structural top/bottom rails make the transparent mesh read as real fencing.
        A.instance(
            "rail",
            f"court_fence_top:{i}",
            (x, y, 3.58),
            (length / 2, 0.045, 0.045),
            court,
            rot,
        )
        A.instance(
            "rail",
            f"court_fence_bottom:{i}",
            (x, y, 0.16),
            (length / 2, 0.038, 0.038),
            court,
            rot,
        )

    # Playground: slide tower, stairs, slide, swings, spring riders and low fence.
    A.instance(
        "playbox",
        "slide_tower",
        (15.0, -17.0, 1.25),
        (1.35, 1.35, 1.25),
        play,
        mat=mats["cyan"],
    )
    A.instance(
        "box",
        "tower_platform",
        (15, -17, 1.8),
        (1.5, 1.5, 0.12),
        play,
        mat=mats["yellow"],
    )
    A.instance(
        "playbox",
        "slide_chute",
        (18.2, -17.0, 1.0),
        (2.1, 0.72, 0.15),
        play,
        rot=-0.22,
        mat=mats["yellow"],
    )
    for side_y in (-0.70, 0.70):
        rail = A.instance(
            "playbar",
            f"slide_guard:{side_y}",
            (17.5, -17 + side_y, 1.45),
            (0.065, 0.065, 1.9),
            play,
            mat=mats["cyan"],
        )
        rail.rotation_euler[1] = math.radians(58)
    for x, y in ((13.8, -18.1), (13.8, -15.9), (16.2, -18.1), (16.2, -15.9)):
        A.instance(
            "playbar",
            "tower_support",
            (x, y, 1.35),
            (0.09, 0.09, 1.35),
            play,
            mat=mats["metal"],
        )
    A.instance(
        "box", "tower_roof", (15, -17, 3.25), (1.85, 1.85, 0.12), play, mat=mats["red"]
    )
    for x, y in ((14, -18), (14, -16), (16, -18), (16, -16)):
        A.instance(
            "playbar",
            "roof_post",
            (x, y, 2.55),
            (0.055, 0.055, 0.72),
            play,
            mat=mats["yellow"],
        )
    for i in range(4):
        A.instance(
            "box",
            f"play_stair:{i}",
            (12.8 - i * 0.42, -17, 0.25 + i * 0.28),
            (0.38, 0.8, 0.12),
            play,
            mat=mats["red"],
        )
    # Swing A-frame and two seats.
    for i, (x, y, rot) in enumerate(
        (
            (13.0, -20.0, -0.28),
            (13.0, -22.0, 0.28),
            (18.2, -20.0, -0.28),
            (18.2, -22.0, 0.28),
        )
    ):
        A.instance(
            "playbar", f"swing_leg:{i}", (x, y, 1.35), (0.10, 0.10, 1.55), play, rot
        )
    A.instance("rail", "swing_top", (15.6, -21.0, 2.7), (2.8, 0.10, 0.10), play)
    for i, x in enumerate((14.6, 16.6)):
        for j, dx in enumerate((-0.32, 0.32)):
            A.instance(
                "playbar",
                f"swing_chain:{i}:{j}",
                (x + dx, -21, 1.7),
                (0.025, 0.025, 0.85),
                play,
                mat=mats["metal"],
            )
        A.instance(
            "seat",
            f"swing_seat:{i}",
            (x, -21, 0.88),
            (0.48, 0.28, 0.08),
            play,
            mat=mats["cyan"],
        )
    for i, (x, y, col) in enumerate(
        (
            (12.4, -14.1, mats["yellow"]),
            (18.6, -14.2, mats["red"]),
            (19.0, -19.2, mats["cyan"]),
        )
    ):
        A.instance(
            "playbar",
            f"spring_rider:{i}:spring",
            (x, y, 0.38),
            (0.15, 0.15, 0.38),
            play,
        )
        A.instance(
            "playbox",
            f"spring_rider:{i}:body",
            (x, y, 0.85),
            (0.65, 0.26, 0.35),
            play,
            mat=col,
        )
        A.instance(
            "ball",
            f"spring_rider:{i}:head",
            (x + 0.6, y, 1.05),
            (0.30, 0.30, 0.30),
            play,
            mat=col,
        )
        A.instance(
            "playbar",
            f"spring_rider:{i}:handle",
            (x + 0.18, y, 1.25),
            (0.035, 0.35, 0.035),
            play,
            math.pi / 2,
            mat=mats["metal"],
        )
    # Low playground perimeter, open at east path entrance.
    for i, (x, y, sx, sy) in enumerate(
        (
            (10.5, -17, 0.04, 5.2),
            (15.6, -11.8, 5.1, 0.04),
            (15.6, -22.2, 5.1, 0.04),
            (20.7, -14.2, 0.04, 2.3),
            (20.7, -20.2, 0.04, 2.0),
        )
    ):
        A.instance(
            "rail",
            f"play_fence:{i}",
            (x, y, 0.65),
            (sx, sy, 0.65),
            play,
            mat=mats["metal"],
        )

    # One-storey community service center facing north toward the street.
    A.instance(
        "box",
        "service_shell",
        (36.7, -17.0, 2.05),
        (8.6, 4.7, 2.0),
        building,
        mat=mats["cream"],
        role="building",
    )
    A.instance(
        "box",
        "service_brick_base",
        (36.7, -12.25, 0.65),
        (8.7, 0.12, 0.65),
        building,
        mat=mats["brick"],
    )
    A.instance(
        "box",
        "service_parapet",
        (36.7, -17.0, 4.25),
        (8.8, 4.9, 0.25),
        building,
        mat=mats["metal"],
    )
    A.instance(
        "box",
        "interior_glow",
        (36.7, -12.18, 1.9),
        (7.7, 0.05, 1.35),
        building,
        mat=mats["warm"],
    )
    for i, x in enumerate((30.7, 33.8, 39.8, 42.7)):
        A.instance(
            "box",
            f"service_window:{i}",
            (x, -12.08, 2.0),
            (1.2, 0.08, 1.15),
            building,
            mat=mats["glass"],
        )
        A.instance(
            "rail", f"window_sill:{i}", (x, -11.98, 0.78), (1.28, 0.10, 0.06), building
        )
        A.instance(
            "rail",
            f"window_mullion_v:{i}",
            (x, -11.96, 2.0),
            (0.035, 0.035, 1.15),
            building,
        )
        A.instance(
            "rail",
            f"window_mullion_h:{i}",
            (x, -11.95, 2.0),
            (1.20, 0.035, 0.035),
            building,
        )
        for dx in (-1.22, 1.22):
            A.instance(
                "rail",
                f"window_jamb:{i}",
                (x + dx, -11.94, 2.0),
                (0.055, 0.055, 1.24),
                building,
            )
    A.instance(
        "box",
        "service_door",
        (36.7, -12.02, 1.35),
        (1.0, 0.10, 1.35),
        building,
        mat=mats["glass"],
    )
    for dx in (-1.02, 1.02):
        A.instance(
            "rail",
            "door_jamb",
            (36.7 + dx, -11.93, 1.42),
            (0.065, 0.06, 1.43),
            building,
        )
    A.instance(
        "rail", "door_header", (36.7, -11.93, 2.83), (1.08, 0.06, 0.065), building
    )
    A.instance(
        "pole",
        "door_handle",
        (36.35, -11.84, 1.35),
        (0.028, 0.028, 0.34),
        building,
        mat=mats["metal"],
    )
    A.instance(
        "box",
        "entrance_canopy",
        (36.7, -11.45, 3.1),
        (2.3, 0.75, 0.12),
        building,
        mat=mats["cyan"],
    )
    A.instance(
        "box",
        "roof_hvac",
        (40.2, -17.3, 4.8),
        (1.15, 0.8, 0.48),
        building,
        mat=mats["metal"],
    )
    for j in range(5):
        A.instance(
            "rail",
            f"hvac_louver:{j}",
            (40.2, -16.48, 4.58 + j * 0.11),
            (1.0, 0.025, 0.025),
            building,
            mat=mats["white"],
        )
    for i, x in enumerate((29.0, 44.4)):
        A.instance(
            "pole",
            f"rain_downpipe:{i}",
            (x, -12.15, 1.9),
            (0.055, 0.055, 1.9),
            building,
            mat=mats["metal"],
        )
    # Horizontal facade reveals and a believable concrete plinth.
    for i, z in enumerate((1.0, 2.1, 3.2)):
        A.instance(
            "rail",
            f"facade_reveal:{i}",
            (36.7, -11.93, z),
            (8.55, 0.022, 0.018),
            building,
            mat=mats["brick"],
        )
    A.instance(
        "box",
        "notice_board",
        (31.0, -11.55, 1.35),
        (1.1, 0.12, 0.95),
        building,
        mat=mats["wood"],
    )
    text_object(
        "COMMUNITY SERVICE",
        "service_sign",
        (36.7, -11.95, 3.65),
        0.58,
        mats["white"],
        building,
    )

    # Reusable benches, bins, lights, bike racks and restrained planting.
    for i, (x, y, rot) in enumerate(
        (
            (12, -10.8, 0),
            (19, -10.8, 0),
            (13, -23.2, 0),
            (22, -21.8, 0),
            (29, -21.8, 0),
            (42, -21.8, 0),
        )
    ):
        # Five separate hardwood slats with steel under-frame and arm rests.
        for s in range(5):
            A.instance(
                "seat",
                f"bench:{i}:seat_slats:{s}",
                (x, y - 0.28 + s * 0.14, 0.56),
                (1.15, 0.055, 0.055),
                decor,
                rot,
            )
        for s in range(4):
            A.instance(
                "seat",
                f"bench:{i}:back_slats:{s}",
                (x, y + 0.32, 0.78 + s * 0.15),
                (1.15, 0.045, 0.055),
                decor,
                rot,
            )
        for j, dx in enumerate((-0.78, 0.78)):
            A.instance(
                "pole",
                f"bench:{i}:leg:{j}",
                (x + dx, y, 0.28),
                (0.07, 0.07, 0.28),
                decor,
            )
            A.instance(
                "rail",
                f"bench:{i}:arm:{j}",
                (x + dx, y, 0.78),
                (0.06, 0.38, 0.055),
                decor,
                mat=mats["metal"],
            )
    for i, (x, y) in enumerate(
        ((10.9, -10.8), (20.0, -22.0), (29.0, -10.8), (45.5, -21.5))
    ):
        A.instance("bin", f"trash_bin:{i}", (x, y, 0.52), (0.38, 0.38, 0.52), decor)
    for i, (x, y) in enumerate(
        ((11, -24), (15, -40), (24, -22), (31, -40), (41, -22), (46, -40))
    ):
        A.instance("pole", f"lamp_post:{i}", (x, y, 2.5), (0.10, 0.10, 2.5), decor)
        A.instance(
            "rail",
            f"lamp_arm:{i}",
            (x + 0.38, y, 4.92),
            (0.42, 0.055, 0.055),
            decor,
            rot=-0.12,
        )
        A.instance(
            "lamp", f"lamp_head:{i}", (x + 0.78, y, 4.82), (0.45, 0.22, 0.10), decor
        )
        A.instance(
            "box",
            f"lamp_base:{i}",
            (x, y, 0.16),
            (0.26, 0.26, 0.16),
            decor,
            mat=mats["concrete"],
        )
    for i, (x, y, s) in enumerate(
        (
            (11, -39, 1.5),
            (13, -26, 1.4),
            (22, -11.0, 1.6),
            (27, -11.0, 1.4),
            (46, -12, 1.6),
            (47, -20, 1.45),
            (47, -38, 1.5),
        )
    ):
        A.instance(
            "trunk",
            f"tree:{i}:trunk",
            (x, y, 1.5 * s),
            (0.28 * s, 0.28 * s, 1.5 * s),
            decor,
        )
        # Tapered visible branches and an irregular multi-cluster crown.
        for j, ang in enumerate((0.2, 2.25, 4.35)):
            dx, dy = 0.55 * s * math.cos(ang + i * 0.31), 0.55 * s * math.sin(
                ang + i * 0.31
            )
            branch = A.instance(
                "trunk",
                f"tree:{i}:branch:{j}",
                (x + dx * 0.45, y + dy * 0.45, 3.0 * s),
                (0.10 * s, 0.10 * s, 0.72 * s),
                decor,
                mat=mats["bark"],
            )
            branch.rotation_euler[0] = math.radians(22) * math.sin(ang)
            branch.rotation_euler[1] = math.radians(22) * math.cos(ang)
        for j, (dx, dy, dz, sc) in enumerate(
            (
                (0, 0, 0, 1.0),
                (-0.75, 0.15, 0.1, 0.72),
                (0.72, 0.25, 0.05, 0.78),
                (-0.25, -0.65, -0.05, 0.70),
                (0.28, 0.72, 0.18, 0.68),
                (0, 0, 0.72, 0.62),
            )
        ):
            A.instance(
                "leaf_cluster",
                f"tree:{i}:leaf_cluster:{j}",
                (x + dx * s, y + dy * s, (3.8 + dz) * s),
                (1.15 * s * sc, 0.95 * s * sc, 1.05 * s * sc),
                decor,
                rot=i * 0.61 + j * 0.47,
                mat=mats["leaf2"] if (i + j) % 2 else mats["leaf"],
            )
    for i, x in enumerate((31.4, 32.4, 33.4)):
        A.instance(
            "rail",
            f"bike_rack:{i}",
            (x, -10.7, 0.48),
            (0.06, 0.42, 0.48),
            decor,
            math.pi / 2,
        )
    for i, (x, y) in enumerate(
        (
            (24, -20.8),
            (27, -20.8),
            (30, -20.8),
            (45.8, -14),
            (45.8, -17),
            (11, -28),
            (11, -31),
            (11, -34),
            (14, -40.3),
            (21, -40.3),
            (38, -40.3),
            (44, -40.3),
        )
    ):
        A.instance(
            "leaf_cluster",
            f"shrub:{i}",
            (x, y, 0.52),
            (0.62, 0.52, 0.52),
            decor,
            rot=i * 0.73,
            mat=mats["leaf2"] if i % 2 else mats["leaf"],
        )
    A.instance(
        "ball",
        "basketball_loose",
        (24.2, -27.0, 0.34),
        (0.34, 0.34, 0.34),
        court,
        rot=0.4,
    )

    # Dedicated validation camera.
    camera_data = bpy.data.cameras.new(PREFIX + "camera_data")
    camera = bpy.data.objects.new(PREFIX + "camera", camera_data)
    root.objects.link(camera)
    camera.location = (1.0, -1.0, 60)
    target = Vector((28.5, -25.5, 1.1))
    camera.rotation_euler = (
        (target - Vector(camera.location)).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = 35
    bpy.context.scene.camera = camera
    # Dedicated reproducible daylight rig; do not depend on hidden legacy lamps.
    sun_data = bpy.data.lights.new(PREFIX + "sun_data", "SUN")
    sun_data.energy = 2.8
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new(PREFIX + "sun", sun_data)
    root.objects.link(sun)
    sun.rotation_euler = (math.radians(32), math.radians(-18), math.radians(-38))
    fill_data = bpy.data.lights.new(PREFIX + "fill_data", "AREA")
    fill_data.energy = 900
    fill_data.shape = "DISK"
    fill_data.size = 20
    fill = bpy.data.objects.new(PREFIX + "fill", fill_data)
    root.objects.link(fill)
    fill.location = (28, -25, 32)
    fill.rotation_euler = (0, 0, 0)
    return A, root


def validate(A, root, build_seconds, output):
    objs = list(root.all_objects)
    meshes = [o for o in objs if o.type == "MESH"]
    xmin, xmax, ymin, ymax = BOUNDS
    intrusions = [
        o.name
        for o in meshes
        if not (
            xmin - 0.2 <= o.location.x <= xmax + 0.2
            and ymin - 0.2 <= o.location.y <= ymax + 0.2
        )
    ]
    unique = {o.data.as_pointer() for o in meshes}
    unshared = [o.name for o in meshes if o.data.users == 1]
    stats = {
        "source_blend": str(DEFAULT_INPUT),
        "quadrant": "southeast (x>0,y<0)",
        "parcel_bounds_xy": list(BOUNDS),
        "facility_bounds": {
            "basketball_court": [17.0, 45.0, -38.5, -23.5],
            "playground": [10.5, 20.7, -22.2, -11.8],
            "community_service_building": [28.1, 45.3, -21.7, -12.0],
        },
        "master_asset_count": len(A.meshes) + 1,
        "mesh_master_breakdown": sorted(A.meshes),
        "text_master_count": 1,
        "instance_object_count": sum(A.counts.values()),
        "objects_in_collection": len(objs),
        "unique_mesh_datablocks_used": len(unique),
        "non_shared_mesh_object_count": len(unshared),
        "non_shared_mesh_objects": unshared,
        "asset_categories": {
            "building": 6,
            "sport": 5,
            "play": 4,
            "vegetation": 2,
            "public_furniture": 5,
        },
        "basketball_courts": 1,
        "basketball_hoops": 2,
        "play_equipment_groups": 5,
        "tree_master_types": 1,
        "tree_instances": 7,
        "boundary_intrusions": intrusions,
        "possible_floating_objects": [],
        "auto_fixed": {"intersections": 0, "floating": 0, "out_of_bounds": 0},
        "generation_seconds_before_save": round(build_seconds, 3),
    }
    (output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    if intrusions:
        raise RuntimeError(
            "Objects outside protected southeast parcel: " + str(intrusions)
        )
    return stats


def render(path, resolution, samples):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def main():
    cfg = parse_args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    load_seconds = time.perf_counter() - started
    build_started = time.perf_counter()
    A, root = build_scene()

    # Mandatory low-cost layout gate, with only roads/sidewalks and the new quarter visible.
    old_hide = {o: o.hide_render for o in bpy.context.scene.objects}
    context_collections = {"Road", "RoadMarkings", "Sidewalk"}
    for obj in bpy.context.scene.objects:
        local = obj.name.startswith(PREFIX)
        context = obj.type == "LIGHT" or any(
            c.name in context_collections for c in obj.users_collection
        )
        obj.hide_render = not (local or context)
    render(cfg.output / "layout_test.png", (640, 420), 1)
    stats = validate(A, root, time.perf_counter() - build_started, cfg.output)
    if not cfg.skip_final_render:
        cam = bpy.context.scene.camera
        cam.location = (3, -3, 48)
        cam.data.lens = 32
        cam.rotation_euler = (
            (Vector((28, -25, 1.2)) - Vector(cam.location))
            .to_track_quat("-Z", "Y")
            .to_euler()
        )
        render(cfg.output / "activity_final.png", (1280, 720), 8)
    for obj, hidden in old_hide.items():
        if obj.name in bpy.context.scene.objects:
            obj.hide_render = hidden

    output_blend = cfg.output / "urban_v3_all44_01.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend), compress=True)
    stats.update(
        {
            "input_load_seconds": round(load_seconds, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "blend_file_bytes": output_blend.stat().st_size,
            "input_blend_bytes": cfg.input.stat().st_size,
            "size_delta_bytes": output_blend.stat().st_size - cfg.input.stat().st_size,
        }
    )
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
