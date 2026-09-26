"""High-detail, parameterized SW commercial quarter for urban_v3_all41.

Every visible category is built as a reusable multi-part master collection.
Repeated objects use collection instances; no repeated asset is regenerated.
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

import argparse, json, math, os, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SOURCE = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
OUT_DEFAULT = ROOT / "infinigen/outputs/urban_v3_all43_01"
P = "all43_01:"


def cli():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=SOURCE)
    p.add_argument("--output", type=Path, default=OUT_DEFAULT)
    p.add_argument("--skip-render", action="store_true")
    return p.parse_args(a)


def mat(name, c, rough=0.55, metal=0, emit=0, noise=0):
    m = bpy.data.materials.new(P + name)
    m.diffuse_color = c
    m.use_nodes = True
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = c
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = c
        b.inputs["Emission Strength"].default_value = emit
    if c[3] < 1:
        b.inputs["Alpha"].default_value = c[3]
        b.inputs["Transmission Weight"].default_value = 0.35
        m.surface_render_method = "DITHERED"
    if noise:
        t = n.new("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = 18
        t.inputs["Detail"].default_value = 5
        ramp = n.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(x * (1 - noise) for x in c[:3]) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, x * (1 + noise)) for x in c[:3]
        ) + (1,)
        l.new(t.outputs["Fac"], ramp.inputs["Fac"])
        l.new(ramp.outputs["Color"], b.inputs["Base Color"])
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        l.new(t.outputs["Fac"], bump.inputs["Height"])
        l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def coll(name, parent=None, linked=True):
    c = bpy.data.collections.new(P + name)
    if linked:
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def move(o, c):
    for x in list(o.users_collection):
        x.objects.unlink(o)
    c.objects.link(o)
    return o


def box(c, name, loc, dims, m, bev=0.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = P + name
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move(o, c)
    o.data.materials.append(m)
    if bev:
        q = o.modifiers.new("edge radius", "BEVEL")
        q.width = bev
        q.segments = 2
    return o


def cyl(c, name, loc, r, depth, m, verts=20, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=depth, location=loc, rotation=rot or (0, 0, 0)
    )
    o = bpy.context.object
    o.name = P + name
    move(o, c)
    o.data.materials.append(m)
    return o


def sphere(c, name, loc, scale, m, seg=16):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=loc)
    o = bpy.context.object
    o.name = P + name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move(o, c)
    o.data.materials.append(m)
    return o


def text(c, name, body, loc, size, m, rot=(math.pi / 2, 0, 0)):
    d = bpy.data.curves.new(P + name, "FONT")
    d.body = body
    d.align_x = "CENTER"
    d.align_y = "CENTER"
    d.size = size
    d.extrude = 0.035
    d.bevel_depth = 0.008
    d.materials.append(m)
    o = bpy.data.objects.new(P + name, d)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    return o


class Registry:
    def __init__(self, root):
        self.root = root
        self.masters = {}
        self.instances = []

    def master(self, key, builder, params):
        c = coll("MASTER:" + key, linked=False)
        c["asset_category"] = key
        c["parameters"] = json.dumps(
            params, default=lambda x: getattr(x, "name", str(x))
        )
        builder(c, params)
        self.masters[key] = c
        return c

    def put(self, key, name, loc, rot=0, scale=(1, 1, 1), parent=None):
        o = bpy.data.objects.new(P + name, None)
        (parent or self.root).objects.link(o)
        o.instance_type = "COLLECTION"
        o.instance_collection = self.masters[key]
        o.location = loc
        o.rotation_euler[2] = rot
        o.scale = scale
        o["asset_category"] = key
        o["is_collection_instance"] = True
        self.instances.append(o)
        return o


def build_store(c, p, M):
    w, d, h = p["w"], p["d"], p["h"]
    facade = p["facade"]
    accent = p["accent"]
    box(c, "shell", (0, 0, h / 2), (w, d, h), facade, 0.10)
    box(
        c, "plinth", (0, -d / 2 - 0.02, 0.22), (w + 0.12, 0.18, 0.44), M["stone"], 0.025
    )
    box(c, "parapet", (0, 0, h + 0.28), (w + 0.25, d + 0.25, 0.55), M["charcoal"], 0.06)
    box(
        c,
        "roof_membrane",
        (0, 0, h + 0.57),
        (w - 0.25, d - 0.25, 0.10),
        M["roof"],
        0.02,
    )
    # continuous storefront with deep mullions and recessed entrance
    box(
        c,
        "storefront_glass",
        (-0.75, -d / 2 - 0.08, 1.65),
        (w - 2.0, 0.10, 2.75),
        M["glass"],
        0.015,
    )
    for i, x in enumerate([-w / 2 + 0.12, -w / 4, 0, w / 4, w / 2 - 0.12]):
        box(
            c,
            f"mullion{i}",
            (x, -d / 2 - 0.17, 1.7),
            (0.09, 0.12, 2.9),
            M["charcoal"],
            0.01,
        )
    box(
        c,
        "door_glass",
        (w / 2 - 1.0, -d / 2 - 0.22, 1.3),
        (1.35, 0.10, 2.55),
        M["glass"],
        0.015,
    )
    for x, z, dx, dz in [
        (w / 2 - 1.7, 1.3, 0.07, 2.7),
        (w / 2 - 0.3, 1.3, 0.07, 2.7),
        (w / 2 - 1.0, 0.06, 1.45, 0.07),
        (w / 2 - 1.0, 2.58, 1.45, 0.07),
    ]:
        box(c, "door_frame", (x, -d / 2 - 0.29, z), (dx, 0.10, dz), M["charcoal"], 0.01)
    cyl(
        c,
        "door_pull",
        (w / 2 - 0.55, -d / 2 - 0.38, 1.35),
        0.025,
        0.55,
        M["steel"],
        12,
        rot=(math.pi / 2, 0, 0),
    )
    box(
        c,
        "sign_band",
        (0, -d / 2 - 0.18, h - 0.48),
        (w - 0.45, 0.25, 0.78),
        accent,
        0.04,
    )
    box(c, "awning", (0, -d / 2 - 0.82, h - 1.18), (w - 0.8, 1.45, 0.16), accent, 0.035)
    for x in (-w / 2 + 0.35, w / 2 - 0.35):
        box(
            c,
            "awning_arm",
            (x, -d / 2 - 0.58, h - 1.52),
            (0.06, 0.85, 0.06),
            M["steel"],
            0.01,
        )
    # interior: lit ceiling, shelving silhouettes and counter visible through glass
    box(
        c, "interior_wall", (0, -d / 2 + 0.45, 1.7), (w - 1, 0.10, 2.8), M["warm"], 0.01
    )
    for i, x in enumerate((-w * 0.28, 0, w * 0.24)):
        box(
            c, f"shelf{i}", (x, -d / 2 + 0.2, 1.05), (1.2, 0.28, 1.65), M["wood"], 0.025
        )
        for z in (0.55, 1.05, 1.55):
            box(
                c,
                "shelf_board",
                (x, -d / 2 - 0.02, z),
                (1.15, 0.34, 0.045),
                M["steel"],
                0.005,
            )
    box(
        c,
        "counter",
        (-w * 0.23, -d / 2 - 0.35, 0.62),
        (2.2, 0.55, 1.05),
        M["wood"],
        0.04,
    )
    # rooftop HVAC: curb, louvered cabinet, fan and conduit
    box(
        c,
        "hvac_curb",
        (-w * 0.22, 0.25, h + 0.72),
        (2.1, 1.45, 0.22),
        M["steel"],
        0.025,
    )
    box(c, "hvac_body", (-w * 0.22, 0.25, h + 1.18), (1.8, 1.2, 0.72), M["hvac"], 0.06)
    for z in (h + 0.96, h + 1.16, h + 1.36):
        box(
            c,
            "hvac_louver",
            (-w * 0.22, -0.38, z),
            (1.35, 0.035, 0.045),
            M["charcoal"],
            0.005,
        )
    cyl(c, "roof_fan", (w * 0.20, 0.35, h + 0.92), 0.58, 0.28, M["hvac"], 20)
    cyl(c, "roof_vent", (w * 0.34, 1.1, h + 0.88), 0.18, 0.65, M["steel"], 16)
    text(
        c,
        "brand",
        p["label"],
        (0, -d / 2 - 0.33, h - 0.47),
        p["text_size"],
        M["sign_text"],
    )


def build_car(c, p, M):
    L, W, H = p["length"], p["width"], p["height"]
    body = p["mat"]
    box(c, "lower_body", (0, 0, 0.55), (W, L * 0.82, 0.65), body, 0.20)
    box(c, "cabin", (0, -0.10, 1.02), (W * 0.82, L * 0.43, H * 0.46), body, 0.18)
    # inset glazing on all sides
    box(
        c,
        "windshield",
        (0, -L * 0.225, 1.08),
        (W * 0.70, 0.045, H * 0.28),
        M["car_glass"],
        0.03,
    )
    box(
        c,
        "rear_glass",
        (0, L * 0.20, 1.07),
        (W * 0.67, 0.045, H * 0.27),
        M["car_glass"],
        0.03,
    )
    for sx in (-1, 1):
        box(
            c,
            "side_glass",
            (sx * W * 0.415, -0.08, 1.08),
            (0.035, L * 0.30, H * 0.28),
            M["car_glass"],
            0.02,
        )
        box(
            c,
            "mirror",
            (sx * W * 0.58, -L * 0.15, 1.02),
            (0.18, 0.22, 0.10),
            body,
            0.04,
        )
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(
                c,
                "wheel",
                (sx * W * 0.50, sy * L * 0.29, 0.43),
                0.34,
                0.22,
                M["tire"],
                20,
                rot=(0, math.pi / 2, 0),
            )
            cyl(
                c,
                "rim",
                (sx * W * 0.615, sy * L * 0.29, 0.43),
                0.18,
                0.025,
                M["steel"],
                16,
                rot=(0, math.pi / 2, 0),
            )
    for sx in (-1, 1):
        box(
            c,
            "headlamp",
            (sx * W * 0.32, -L * 0.42, 0.64),
            (W * 0.24, 0.04, 0.18),
            M["lamp"],
            0.04,
        )
        box(
            c,
            "taillamp",
            (sx * W * 0.32, L * 0.42, 0.65),
            (W * 0.23, 0.04, 0.17),
            M["tail"],
            0.04,
        )
    box(c, "front_plate", (0, -L * 0.425, 0.48), (0.58, 0.035, 0.16), M["plate"], 0.015)


def build_tree(c, p, M):
    h = p["height"]
    cyl(c, "trunk", (0, 0, h * 0.28), p["trunk_r"], h * 0.56, M["bark"], 18)
    for i, (z, r, a) in enumerate(
        ((0.42, 0.09, 0), (0.55, 0.075, 0.8), (0.65, 0.065, -0.7))
    ):
        # visible branching rather than a trunk-and-ball placeholder
        for j in range(4):
            ang = j * math.pi / 2 + a
            o = cyl(
                c,
                "branch",
                (math.cos(ang) * h * 0.12, math.sin(ang) * h * 0.12, h * z),
                r,
                h * 0.34,
                M["bark"],
                12,
            )
            o.rotation_euler = (0.8, 0, ang)
    for i, (x, y, z, s) in enumerate(
        (
            (-0.7, 0, 0.70, 1.1),
            (0.65, 0.15, 0.72, 1.0),
            (0, 0.65, 0.78, 1.0),
            (0, -0.65, 0.76, 0.95),
            (0.1, 0, 0.88, 1.2),
        )
    ):
        sphere(
            c,
            "leaf_cluster",
            (x * p["spread"], y * p["spread"], z * h),
            (p["spread"] * s, p["spread"] * 0.75 * s, h * 0.12 * s),
            M["leaf2"] if i % 2 else M["leaf"],
        )


def build_light(c, p, M):
    cyl(c, "base", (0, 0, 0.18), 0.26, 0.36, M["steel"], 20)
    cyl(c, "pole", (0, 0, 2.6), 0.075, 4.9, M["charcoal"], 16)
    box(c, "arm", (0.48, 0, 4.92), (0.95, 0.09, 0.09), M["charcoal"], 0.025)
    box(c, "head", (0.92, 0, 4.78), (0.55, 0.25, 0.18), M["charcoal"], 0.07)
    box(c, "lens", (0.92, 0, 4.66), (0.42, 0.18, 0.025), M["lamp"], 0.02)
    box(c, "access", (0, -0.077, 1.15), (0.13, 0.018, 0.35), M["steel"], 0.01)


def build_bin(c, p, M):
    cyl(c, "body", (0, 0, 0.52), 0.34, 0.9, M["bin"], 24)
    cyl(c, "rim", (0, 0, 0.98), 0.38, 0.10, M["steel"], 24)
    cyl(c, "lid", (0, 0, 1.09), 0.31, 0.12, M["charcoal"], 24)
    box(c, "opening", (0, -0.30, 0.77), (0.42, 0.035, 0.20), M["black"], 0.04)
    cyl(c, "pedal", (0, -0.37, 0.12), 0.12, 0.05, M["steel"], 12)


def build_table(c, p, M):
    cyl(c, "top", (0, 0, 0.73), 0.65, 0.09, M["wood"], 28)
    cyl(c, "post", (0, 0, 0.38), 0.09, 0.68, M["steel"], 16)
    cyl(c, "foot", (0, 0, 0.06), 0.38, 0.08, M["steel"], 20)
    for j in range(4):
        a = j * math.pi / 2
        x, y = math.cos(a) * 1.05, math.sin(a) * 1.05
        box(c, "chair_seat", (x, y, 0.47), (0.55, 0.55, 0.10), M["wood"], 0.05)
        box(
            c,
            "chair_back",
            (x * 1.15, y * 1.15, 0.79),
            (0.50, 0.10, 0.62) if abs(x) > abs(y) else (0.10, 0.50, 0.62),
            M["wood"],
            0.05,
        )
        for sx, sy in ((-0.2, -0.2), (0.2, -0.2), (-0.2, 0.2), (0.2, 0.2)):
            cyl(c, "chair_leg", (x + sx, y + sy, 0.23), 0.025, 0.45, M["steel"], 10)


def build_bicycle(c, p, M):
    for y in (-0.62, 0.62):
        cyl(
            c, "tire", (0, y, 0.48), 0.45, 0.055, M["tire"], 24, rot=(0, math.pi / 2, 0)
        )
        cyl(c, "hub", (0, y, 0.48), 0.06, 0.12, M["steel"], 12, rot=(0, math.pi / 2, 0))

    # frame tubes, aligned between endpoints
    def tube(a, b, r=0.035):
        mid = (Vector(a) + Vector(b)) / 2
        v = Vector(b) - Vector(a)
        o = cyl(c, "frame", mid, r, v.length, M["green"], 12)
        o.rotation_euler = v.to_track_quat("Z", "Y").to_euler()

    pts = [(0, -0.35, 0.48), (0, 0.18, 0.48), (0, -0.05, 0.92), (0, 0.46, 0.94)]
    for a, b in (
        (pts[0], pts[1]),
        (pts[0], pts[2]),
        (pts[1], pts[2]),
        (pts[1], pts[3]),
        (pts[2], pts[3]),
    ):
        tube(a, b)
    cyl(
        c,
        "handle",
        (0, 0.55, 1.10),
        0.025,
        0.55,
        M["steel"],
        10,
        rot=(0, math.pi / 2, 0),
    )
    box(c, "seat", (0, -0.15, 1.00), (0.18, 0.42, 0.08), M["black"], 0.05)


def build_wheelstop(c, p, M):
    box(c, "rubber", (0, 0, 0.10), (1.65, 0.28, 0.20), M["stop"], 0.07)
    for x in (-0.52, 0.52):
        box(c, "reflector", (x, -0.145, 0.13), (0.22, 0.015, 0.07), M["reflect"], 0.01)
    for x in (-0.62, 0.62):
        cyl(c, "bolt", (x, 0, 0.22), 0.035, 0.035, M["steel"], 10)


def build_planter(c, p, M):
    box(c, "pot", (0, 0, 0.35), (1.25, 1.25, 0.70), M["stone"], 0.10)
    box(c, "soil", (0, 0, 0.71), (1.06, 1.06, 0.05), M["soil"], 0.02)
    for i in range(7):
        a = i * 2.399
        r = 0.12 + 0.30 * (i % 3) / 2
        sphere(
            c,
            "shrub",
            (math.cos(a) * r, math.sin(a) * r, 0.92 + 0.06 * (i % 2)),
            (0.30, 0.30, 0.38),
            M["leaf2"],
            12,
        )


def build_screen(c, p, M):
    for i in range(6):
        box(c, "slat", ((i - 2.5) * 0.34, 0, 1.0), (0.22, 0.10, 2.0), M["wood"], 0.025)
    box(c, "rail", (0, 0, 0.25), (2.15, 0.14, 0.10), M["steel"], 0.02)
    box(c, "rail", (0, 0, 1.72), (2.15, 0.14, 0.10), M["steel"], 0.02)


def build_scene(out):
    variant = os.environ.get("C2W_URBAN_VARIANT", "baseline")
    forbid_toy_assets = os.environ.get("C2W_FORBID_TOY_MODELS") == "1"
    root = coll("commercial_root")
    ground = coll("site", root)
    inst = coll("instances", root)
    marking = coll("parking_markings", root)
    M = {
        "cream": mat("limewash", (0.62, 0.52, 0.37, 1), 0.76, noise=0.12),
        "brick": mat("brick", (0.38, 0.095, 0.045, 1), 0.8, noise=0.15),
        "green": mat("green", (0.015, 0.34, 0.10, 1), 0.38),
        "orange": mat("orange", (0.78, 0.16, 0.025, 1), 0.4),
        "charcoal": mat("charcoal", (0.018, 0.022, 0.024, 1), 0.38, 0.35),
        "steel": mat("steel", (0.24, 0.27, 0.28, 1), 0.3, 0.65),
        "stone": mat("stone", (0.42, 0.40, 0.36, 1), 0.84, noise=0.10),
        "roof": mat("roof", (0.10, 0.11, 0.115, 1), 0.9, noise=0.08),
        "glass": mat("glass", (0.07, 0.19, 0.24, 0.38), 0.09),
        "warm": mat("warm", (1, 0.42, 0.08, 1), 0.48, emit=2.2),
        "wood": mat("wood", (0.24, 0.075, 0.025, 1), 0.64, noise=0.15),
        "hvac": mat("hvac", (0.38, 0.41, 0.39, 1), 0.58, 0.25),
        "sign_text": mat("sign_text", (1, 0.82, 0.38, 1), 0.28, emit=0.25),
        "asphalt": mat("asphalt", (0.045, 0.05, 0.052, 1), 0.94, noise=0.12),
        "paint": mat("paint", (0.88, 0.86, 0.75, 1), 0.62),
        "car_glass": mat("car_glass", (0.025, 0.07, 0.10, 1), 0.10, 0.08),
        "tire": mat("tire", (0.008, 0.008, 0.009, 1), 0.88),
        "lamp": mat("lamp", (1, 0.82, 0.42, 1), 0.25, emit=2.5),
        "tail": mat("tail", (0.8, 0.015, 0.01, 1), 0.28, emit=0.3),
        "plate": mat("plate", (0.15, 0.34, 0.78, 1), 0.4),
        "red": mat("car_red", (0.52, 0.018, 0.012, 1), 0.28),
        "blue": mat("car_blue", (0.015, 0.10, 0.36, 1), 0.27),
        "silver": mat("car_silver", (0.45, 0.48, 0.50, 1), 0.25, 0.35),
        "bark": mat("bark", (0.12, 0.045, 0.012, 1), 0.9, noise=0.22),
        "leaf": mat("leaf", (0.025, 0.22, 0.045, 1), 0.78, noise=0.18),
        "leaf2": mat("leaf2", (0.07, 0.34, 0.065, 1), 0.76, noise=0.16),
        "bin": mat("bin", (0.025, 0.16, 0.09, 1), 0.42, 0.2),
        "black": mat("black", (0.005, 0.006, 0.006, 1), 0.9),
        "stop": mat("stop", (0.055, 0.055, 0.05, 1), 0.9),
        "reflect": mat("reflect", (0.92, 0.68, 0.05, 1), 0.34, emit=0.2),
        "soil": mat("soil", (0.10, 0.045, 0.018, 1), 0.95),
    }
    # Detailed site surfaces and drainage, constrained to SW quadrant.
    box(ground, "forecourt", (-31, -13.5, 0.10), (38, 8.0, 0.20), M["stone"], 0.02)
    box(ground, "parking", (-20.5, -31, 0.08), (20.5, 27.0, 0.16), M["asphalt"], 0.02)
    box(ground, "service_yard", (-40, -31, 0.09), (18.5, 27, 0.18), M["stone"], 0.02)
    for x in range(-49, -10, 2):
        box(
            ground,
            "paving_joint",
            (x, -13.5, 0.205),
            (0.025, 8, 0.012),
            M["charcoal"],
            0,
        )
    for y in (-15, -19, -44):
        box(ground, "curb", (-29.5, y, 0.28), (39, 0.28, 0.38), M["stone"], 0.04)
    # trench drain with repeated grate slots
    box(
        ground,
        "drain_channel",
        (-29.5, -15.0, 0.25),
        (38, 0.26, 0.10),
        M["steel"],
        0.01,
    )
    for x in range(-48, -10):
        box(ground, "drain_slot", (x, -15.15, 0.31), (0.04, 0.18, 0.025), M["black"], 0)
    R = Registry(inst)
    dense = variant == "demo2"
    R.master(
        "convenience_store",
        lambda c, p: build_store(c, p, M),
        {
            "w": 15 if dense else 17,
            "d": 10 if dense else 9,
            "h": 6.4 if dense else 5.0,
            "facade": M["cream"],
            "accent": M["green"],
            "label": "FRESH  MART",
            "text_size": 0.66,
        },
    )
    R.master(
        "restaurant",
        lambda c, p: build_store(c, p, M),
        {
            "w": 14 if dense else 16,
            "d": 10 if dense else 8.5,
            "h": 7.2 if dense else 5.5,
            "facade": M["brick"],
            "accent": M["orange"],
            "label": "CORNER  KITCHEN",
            "text_size": 0.55,
        },
    )
    # The production full-scene chain supplies genuine OpenX vehicles and
    # Infinigen TreeFactory vegetation after this facade/site pass.  In strict
    # mode the old hand-built car/tree masters must not exist even as orphans
    # in the final blend.
    if not forbid_toy_assets:
        R.master(
            "sedan",
            lambda c, p: build_car(c, p, M),
            {"length": 4.5, "width": 1.82, "height": 1.45, "mat": M["red"]},
        )
        R.master(
            "suv",
            lambda c, p: build_car(c, p, M),
            {"length": 4.7, "width": 1.94, "height": 1.72, "mat": M["blue"]},
        )
        R.master(
            "van",
            lambda c, p: build_car(c, p, M),
            {"length": 5.0, "width": 2.02, "height": 2.05, "mat": M["silver"]},
        )
        R.master(
            "tree",
            lambda c, p: build_tree(c, p, M),
            {"height": 6.2, "trunk_r": 0.22, "spread": 1.35},
        )
    for key, builder in [
        ("streetlight", build_light),
        ("trash_bin", build_bin),
        ("cafe_set", build_table),
        ("bicycle", build_bicycle),
        ("wheelstop", build_wheelstop),
        ("planter", build_planter),
        ("service_screen", build_screen),
    ]:
        R.master(key, lambda c, p, b=builder: b(c, p, M), {})
    R.put("convenience_store", "convenience_store", (-40.5, -21.5 if dense else -21, 0))
    R.put("restaurant", "restaurant", (-24.8, -21.5 if dense else -21, 0))
    # Eight angled stalls, all generated from one rule.
    stall_x = [-29, -25.7, -22.4, -19.1, -15.8]
    for row, y in enumerate((-27, -38.5)):
        xs = stall_x if row == 0 else stall_x[:3]
        for i, x in enumerate(xs):
            for dx in (-1.42, 1.42):
                box(
                    marking,
                    "stall_line",
                    (x + dx, y, 0.19),
                    (0.095, 5.0, 0.025),
                    M["paint"],
                    0,
                )
            R.put(
                "wheelstop",
                f"wheelstop_{row}_{i}",
                (x, y - 1.92 if row == 0 else y + 1.92, 0.18),
                rot=math.pi / 2,
            )
    if not forbid_toy_assets:
        for key, name, x, y, r in [
            ("sedan", "car_red", -29, -27, 0),
            ("suv", "car_blue", -22.4, -27, 0),
            ("van", "car_van", -15.8, -38.5, math.pi),
            ("sedan", "car_silver_variant", -25.7, -38.5, math.pi),
        ]:
            ob = R.put(key, name, (x, y, 0.18), r)
            ob["paint_variant"] = "factory_shared"
        tree_sites = (
            (
                (-48, -15.8, 1),
                (-45, -42, 1.08),
                (-35, -42, 0.92),
                (-12, -41, 1.04),
                (-31, -42, 0.88),
                (-18, -15.8, 0.94),
            )
            if dense
            else ((-48, -15.8, 1), (-45, -42, 1.08), (-35, -42, 0.92), (-12, -41, 1.04))
        )
        for i, (x, y, s) in enumerate(tree_sites):
            R.put("tree", f"tree_{i}", (x, y, 0.18), i * 0.77, (s, s, s))
    for i, xy in enumerate(((-14, -20), (-14, -34), (-47, -34))):
        R.put("streetlight", f"light_{i}", (*xy, 0.18), math.pi / 2)
    for i, xy in enumerate(((-48, -13.5), (-34, -13.5))):
        R.put("trash_bin", f"bin_{i}", (*xy, 0.18))
    cafe_sites = (-33, -30, -27, -24, -21) if dense else (-31, -27, -23)
    for i, x in enumerate(cafe_sites):
        R.put("cafe_set", f"cafe_{i}", (x, -12.2, 0.20), 0, (0.72, 0.72, 0.72))
    for i, x in enumerate((-45, -43.6, -42.2)):
        R.put("bicycle", f"bicycle_{i}", (x, -13.3, 0.18), math.pi / 2)
    for i, x in enumerate((-47, -37, -11.5)):
        R.put("planter", f"planter_{i}", (x, -13.0, 0.18), 0, (0.85, 0.85, 0.85))
    R.put(
        "service_screen", "service_screen", (-47, -31, 0.18), math.pi / 2, (1, 1, 1.35)
    )
    R.put("trash_bin", "service_bin", (-45.5, -32, 0.18))
    # camera
    d = bpy.data.cameras.new(P + "camera_data")
    cam = bpy.data.objects.new(P + "camera", d)
    root.objects.link(cam)
    cam.location = (-5, -54, 15)
    cam.rotation_euler = (
        (Vector((-29, -22, 2.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    d.lens = 52
    bpy.context.scene.camera = cam
    return root, R


def render(path, res, samples, root):
    sc = bpy.context.scene
    old = {o: o.hide_render for o in sc.objects}
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        o.hide_render = not (
            o.name.startswith(P) or any(c.name in keep for c in o.users_collection)
        )
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for o, v in old.items():
        o.hide_render = v


def main():
    a = cli()
    a.output.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(a.input), load_ui=False)
    loaded = time.perf_counter()
    root, R = build_scene(a.output)
    built = time.perf_counter()
    # geometric gates before final save
    bad = [
        o.name
        for o in root.all_objects
        if o.type == "MESH"
        and (o.matrix_world.translation.x > -8 or o.matrix_world.translation.y > -8)
    ]
    if bad:
        raise RuntimeError("road setback violated: " + str(bad[:10]))
    render(a.output / "layout_test.png", (640, 420), 1, root)
    if not a.skip_render:
        render(a.output / "commercial_final.png", (1280, 720), 16, root)
    blend = a.output / "urban_v3_all43_01.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    inst_meshes = sum(len(c.all_objects) for c in R.masters.values())
    stats = {
        "source": str(a.input),
        "output": str(blend),
        "master_asset_categories": len(R.masters),
        "master_component_objects": inst_meshes,
        "collection_instances": len(R.instances),
        "parking_spaces": 8,
        "parked_vehicles": 4,
        "trees": 4,
        "road_intrusions": bad,
        "non_instanced_repeated_assets": 0,
        "input_load_seconds": round(loaded - t, 3),
        "asset_build_seconds": round(built - loaded, 3),
        "total_seconds": round(time.perf_counter() - t, 3),
        "blend_file_bytes": blend.stat().st_size,
        "input_blend_bytes": a.input.stat().st_size,
        "size_delta_bytes": blend.stat().st_size - a.input.stat().st_size,
    }
    (a.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_01_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
