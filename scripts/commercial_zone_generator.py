"""Reusable, lightweight procedural commercial-zone generator for all43_04.

Architecture: shared materials + shared primitive meshes -> high quality master
collections -> constrained parameter generation -> collection instances.
"""
from dataclasses import dataclass, field
import math, random, time
import bpy
from mathutils import Vector

P = "all43_04:"


def _mat(name, color, rough=0.6, metal=0, trans=0, normal=0.12, dirt=0.08):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    m.diffuse_color = color
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if trans:
        b.inputs["Transmission Weight"].default_value = trans
        b.inputs["Alpha"].default_value = color[3]
        m.surface_render_method = "DITHERED"
    tex = n.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 24
    tex.inputs["Detail"].default_value = 6
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = normal
    bump.inputs["Distance"].default_value = 0.025
    l.new(tex.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    m["dirt_amount"] = dirt
    return m


def create_storefront_glass_material(
    roughness, tint, transmission, reflection_strength
):
    return _mat("MAT_GLASS", (*tint, 0.32), roughness, 0, transmission, 0.035, 0)


def create_shared_materials():
    return {
        "wall": _mat("MAT_WALL", (0.43, 0.37, 0.28, 1), 0.78, normal=0.18, dirt=0.14),
        "wall_red": _mat(
            "MAT_WALL_RED", (0.31, 0.065, 0.028, 1), 0.8, normal=0.24, dirt=0.18
        ),
        "metal": _mat(
            "MAT_METAL", (0.055, 0.065, 0.07, 1), 0.28, 0.72, 0.0, 0.05, 0.06
        ),
        "glass": create_storefront_glass_material(
            0.08, (0.035, 0.11, 0.14), 0.72, 0.35
        ),
        "asphalt": _mat(
            "MAT_ASPHALT", (0.038, 0.042, 0.044, 1), 0.93, normal=0.32, dirt=0.22
        ),
        "concrete": _mat(
            "MAT_CONCRETE", (0.37, 0.36, 0.33, 1), 0.86, normal=0.20, dirt=0.12
        ),
        "plastic": _mat(
            "MAT_PLASTIC", (0.035, 0.14, 0.075, 1), 0.45, normal=0.06, dirt=0.08
        ),
        "wood": _mat("MAT_WOOD", (0.23, 0.075, 0.025, 1), 0.65, normal=0.16, dirt=0.10),
        "black": _mat(
            "MAT_BLACK", (0.006, 0.008, 0.009, 1), 0.88, normal=0.04, dirt=0.05
        ),
        "paint": _mat("MAT_PAINT", (0.9, 0.88, 0.77, 1), 0.58, normal=0.04, dirt=0.05),
        "warm": _mat("MAT_WARM", (1, 0.56, 0.18, 1), 0.42, normal=0.03, dirt=0),
        "soil": _mat("MAT_SOIL", (0.09, 0.04, 0.015, 1), 0.95, normal=0.3, dirt=0.2),
    }


def _unit_cube():
    me = bpy.data.meshes.get(P + "MESH_UNIT_CUBE")
    if me:
        return me
    v = [
        (-0.5, -0.5, -0.5),
        (0.5, -0.5, -0.5),
        (0.5, 0.5, -0.5),
        (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),
        (0.5, -0.5, 0.5),
        (0.5, 0.5, 0.5),
        (-0.5, 0.5, 0.5),
    ]
    f = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    me = bpy.data.meshes.new(P + "MESH_UNIT_CUBE")
    me.from_pydata(v, [], f)
    return me


def _unit_cylinder(seg=24):
    key = P + f"MESH_UNIT_CYL_{seg}"
    me = bpy.data.meshes.get(key)
    if me:
        return me
    v = []
    for z in (-0.5, 0.5):
        v += [
            (math.cos(math.tau * i / seg) * 0.5, math.sin(math.tau * i / seg) * 0.5, z)
            for i in range(seg)
        ]
    f = [tuple(range(seg - 1, -1, -1)), tuple(range(seg, 2 * seg))] + [
        (i, (i + 1) % seg, (i + 1) % seg + seg, i + seg) for i in range(seg)
    ]
    me = bpy.data.meshes.new(key)
    me.from_pydata(v, [], f)
    return me


def _obj(c, name, mesh, loc, dims, mat, bevel=None, rot=0):
    o = bpy.data.objects.new(P + name, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = dims
    o.rotation_euler[2] = rot
    if not o.data.materials:
        o.data.materials.append(mat)
    if o.material_slots:
        o.material_slots[0].link = "OBJECT"
        o.material_slots[0].material = mat
    size = min(abs(x) for x in dims)
    bw = bevel if bevel is not None else max(0.002, min(0.04, size * 0.035))
    if bw:
        q = o.modifiers.new("adaptive_bevel", "BEVEL")
        q.width = bw
        q.segments = 2
    o["shared_mesh"] = mesh.name
    return o


def box(c, n, loc, dims, mat, bevel=None, rot=0):
    return _obj(c, n, _unit_cube(), loc, dims, mat, bevel, rot)


def cyl(c, n, loc, dims, mat, bevel=None, rot=0):
    return _obj(c, n, _unit_cylinder(), loc, dims, mat, bevel, rot)


def collection(name, parent=None, link=True):
    c = bpy.data.collections.new(P + name)
    if link:
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def instance(c, master, name, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + name, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = master
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["c2w_role"] = "instance"
    return o


@dataclass
class Library:
    mats: dict
    masters: dict = field(default_factory=dict)
    instances: list = field(default_factory=list)
    seed: int = 4304


def create_shelf_template(lib):
    c = collection("MASTER_SHELF", link=False)
    box(c, "shelf_body", (0, 0, 0.9), (1.0, 0.30, 0.9), lib.mats["metal"])
    for z in (0.18, 0.55, 0.92, 1.29, 1.65):
        box(
            c,
            "shelf_board",
            (0, -0.02, z),
            (1.05, 0.36, 0.025),
            lib.mats["metal"],
            0.004,
        )
    lib.masters["shelf"] = c


def create_table_template(lib):
    c = collection("MASTER_TABLE", link=False)
    cyl(c, "table_top", (0, 0, 0.72), (0.62, 0.62, 0.045), lib.mats["wood"])
    cyl(c, "table_post", (0, 0, 0.38), (0.08, 0.08, 0.34), lib.mats["metal"])
    cyl(c, "table_foot", (0, 0, 0.05), (0.34, 0.34, 0.04), lib.mats["metal"])
    lib.masters["table"] = c


def create_chair_template(lib):
    c = collection("MASTER_CHAIR", link=False)
    box(c, "chair_seat", (0, 0, 0.46), (0.24, 0.24, 0.05), lib.mats["wood"])
    box(c, "chair_back", (0, 0.22, 0.76), (0.24, 0.035, 0.32), lib.mats["wood"])
    for x in (-0.19, 0.19):
        for y in (-0.19, 0.19):
            cyl(c, "chair_leg", (x, y, 0.23), (0.025, 0.025, 0.23), lib.mats["metal"])
    lib.masters["chair"] = c


def create_trash_bin(lib, variant="A"):
    c = collection("MASTER_TRASH_" + variant, link=False)
    cyl(c, "bin_body", (0, 0, 0.52), (0.34, 0.34, 0.46), lib.mats["plastic"])
    cyl(c, "bin_rim", (0, 0, 0.98), (0.38, 0.38, 0.05), lib.mats["metal"])
    cyl(c, "bin_lid", (0, 0, 1.08), (0.32, 0.32, 0.08), lib.mats["black"])
    box(c, "bin_opening", (0, -0.32, 0.74), (0.22, 0.025, 0.11), lib.mats["black"])
    cyl(c, "bin_base", (0, 0, 0.05), (0.38, 0.38, 0.05), lib.mats["metal"])
    lib.masters["trash_" + variant] = c


def create_bike_rack(lib):
    c = collection("MASTER_BIKE_RACK", link=False)
    for x in (-0.48, 0, 0.48):
        cyl(c, "rack_upright", (x, 0, 0.42), (0.035, 0.035, 0.42), lib.mats["metal"])
        cyl(
            c,
            "rack_top",
            (x, 0, 0.84),
            (0.20, 0.20, 0.035),
            lib.mats["metal"],
            rot=math.pi / 2,
        )
        box(c, "rack_fix", (x, 0, 0.025), (0.12, 0.15, 0.025), lib.mats["metal"], 0.008)
    lib.masters["bike_rack"] = c


def create_planter(lib):
    c = collection("MASTER_PLANTER", link=False)
    box(c, "planter_shell", (0, 0, 0.36), (0.65, 0.65, 0.36), lib.mats["concrete"])
    box(c, "planter_soil", (0, 0, 0.73), (0.57, 0.57, 0.03), lib.mats["soil"])
    lib.masters["planter"] = c


def create_sign_board(lib):
    c = collection("MASTER_SIGN", link=False)
    box(c, "sign_panel", (0, 0, 1.15), (0.62, 0.08, 0.72), lib.mats["plastic"])
    cyl(c, "sign_post", (0, 0, 0.38), (0.04, 0.04, 0.38), lib.mats["metal"])
    box(c, "sign_foot", (0, 0, 0.04), (0.42, 0.30, 0.04), lib.mats["metal"])
    lib.masters["sign"] = c


def create_ac_unit(lib):
    c = collection("MASTER_AC", link=False)
    box(c, "ac_body", (0, 0, 0.48), (0.65, 0.25, 0.48), lib.mats["concrete"])
    cyl(
        c,
        "ac_fan",
        (0, -0.27, 0.49),
        (0.28, 0.035, 0.28),
        lib.mats["black"],
        rot=math.pi / 2,
    )
    for x in (-0.48, 0.48):
        box(c, "ac_bracket", (x, 0, 0.08), (0.06, 0.35, 0.06), lib.mats["metal"])
        cyl(
            c,
            "ac_connector",
            (0.58, 0.1, 0.28),
            (0.035, 0.035, 0.18),
            lib.mats["metal"],
        )
        lib.masters["ac"] = c


def create_drain_pipe(lib):
    c = collection("MASTER_DRAINPIPE", link=False)
    cyl(c, "pipe", (0, 0, 1.4), (0.06, 0.06, 1.4), lib.mats["metal"])
    box(c, "pipe_shoe", (0, -0.12, 0.08), (0.12, 0.20, 0.08), lib.mats["metal"])
    lib.masters["drainpipe"] = c


def create_electrical_box(lib):
    c = collection("MASTER_ELECTRICAL", link=False)
    box(c, "ebox", (0, 0, 0.62), (0.42, 0.16, 0.62), lib.mats["concrete"])
    box(c, "ebox_door", (0, -0.17, 0.62), (0.36, 0.025, 0.52), lib.mats["metal"])
    cyl(c, "ebox_lock", (0.22, -0.20, 0.62), (0.025, 0.025, 0.025), lib.mats["black"])
    lib.masters["electrical"] = c


def create_bollard(lib):
    c = collection("MASTER_BOLLARD", link=False)
    cyl(c, "bollard", (0, 0, 0.45), (0.075, 0.075, 0.45), lib.mats["metal"])
    cyl(c, "bollard_cap", (0, 0, 0.92), (0.085, 0.085, 0.035), lib.mats["paint"])
    lib.masters["bollard"] = c


def create_wheel_stop(lib):
    c = collection("MASTER_WHEEL_STOP", link=False)
    box(
        c,
        "wheel_stop_body",
        (0, 0, 0.10),
        (1.65, 0.18, 0.10),
        lib.mats["concrete"],
        0.025,
    )
    for x in (-0.52, 0.52):
        cyl(c, "wheel_stop_pin", (x, 0, 0.22), (0.025, 0.025, 0.12), lib.mats["metal"])
    lib.masters["wheel_stop"] = c


def prepare_commercial_asset_library(seed=4304):
    lib = Library(create_shared_materials(), seed=seed)
    create_shelf_template(lib)
    create_table_template(lib)
    create_chair_template(lib)
    create_trash_bin(lib, "A")
    create_trash_bin(lib, "B")
    create_bike_rack(lib)
    create_planter(lib)
    create_sign_board(lib)
    create_ac_unit(lib)
    create_drain_pipe(lib)
    create_electrical_box(lib)
    create_bollard(lib)
    create_wheel_stop(lib)
    return lib


def generate_storefront(params, lib, parent, seed):
    rng = random.Random(seed)
    c = collection("storefront_" + params["name"], parent)
    w = params["storefront_width"]
    h = params["storefront_height"]
    n = params["number_of_bays"]
    inset = params["facade_inset"]
    base = params["baseboard_height"]
    bay = w / n
    box(
        c,
        "facade_back",
        (0, 0, h / 2),
        (w, 0.18, h),
        lib.mats[params.get("wall_mat", "wall")],
    )
    box(c, "baseboard", (0, -0.13, base / 2), (w, 0.14, base), lib.mats["concrete"])
    for i in range(n):
        bw = bay * rng.uniform(0.95, 1.05)
        x = -w / 2 + bay * (i + 0.5)
        isdoor = i == params.get("door_bay", n - 1)
        ww = (params["door_width"] if isdoor else params["window_width"]) * rng.uniform(
            0.95, 1.05
        )
        hh = params["door_height"] if isdoor else params["window_height"]
        box(
            c,
            "opening_shadow",
            (x, -inset, base + hh / 2),
            (ww, 0.16, hh),
            lib.mats["black"],
            0.008,
        )
        box(
            c,
            "glass",
            (x, -inset - 0.10, base + hh / 2),
            (ww - 0.10, 0.025, hh - 0.10),
            lib.mats["glass"],
            0.003,
        )
        for xx in (x - ww / 2, x + ww / 2):
            box(
                c,
                "jamb",
                (xx, -inset - 0.14, base + hh / 2),
                (params["mullion_width"], params["mullion_depth"], hh + 0.15),
                lib.mats["metal"],
                0.005,
            )
        for zz in (base, base + hh):
            box(
                c,
                "rail",
                (x, -inset - 0.14, zz),
                (ww + 0.12, params["mullion_depth"], params["mullion_width"]),
                lib.mats["metal"],
                0.005,
            )
        if not isdoor:
            box(
                c,
                "mullion",
                (x, -inset - 0.15, base + hh / 2),
                (params["mullion_width"], params["mullion_depth"], hh - 0.1),
                lib.mats["metal"],
                0.004,
            )
        else:
            cyl(
                c,
                "door_pull",
                (x + ww * 0.22, -inset - 0.22, base + hh * 0.52),
                (0.025, 0.025, 0.30),
                lib.mats["metal"],
            )
    for i in range(n + 1):
        box(
            c,
            "column",
            (-w / 2 + i * bay, -0.03, h / 2),
            (params["column_width"], 0.26, h),
            lib.mats[params.get("wall_mat", "wall")],
        )
    cd = params["canopy_depth"] * rng.uniform(0.9, 1.1)
    box(
        c,
        "canopy",
        (0, -cd / 2 - 0.20, h - 0.78),
        (w * 0.96, cd, params["canopy_thickness"]),
        lib.mats["metal"],
    )
    sh = params["sign_height"] * rng.uniform(0.9, 1.1)
    box(
        c,
        "sign_band",
        (0, -0.18, h - sh / 2),
        (w * 0.92, params["sign_depth"], sh),
        lib.mats["plastic"],
    )
    for x in (-w / 2 + 0.18, w / 2 - 0.18):
        instance(c, lib.masters["drainpipe"], "drainpipe", (x, -0.25, 0), 0)
    return c


def generate_store_interior_proxy(kind, params, lib, parent, seed):
    c = collection("interior_" + kind, parent)
    d = params["interior_depth"]
    box(c, "back_wall", (0, d, 1.55), (params["width"], 0.10, 3.1), lib.mats["wall"])
    box(
        c,
        "interior_floor",
        (0, d / 2, 0.03),
        (params["width"], d, 0.03),
        lib.mats["concrete"],
    )
    if kind == "convenience":
        for i in range(params["shelf_rows"]):
            instance(
                c,
                lib.masters["shelf"],
                f"shelf_{i}",
                (-params["width"] * 0.32 + i * params["shelf_spacing"], d * 0.45, 0),
                math.pi / 2,
            )
        box(
            c,
            "counter",
            (params["width"] * 0.25, 0.65, 0.55),
            (params["counter_length"], 0.45, 0.55),
            lib.mats["wood"],
        )
        box(
            c,
            "freezer",
            (-params["width"] * 0.25, 0.55, 0.55),
            (1.5, 0.55, 0.55),
            lib.mats["metal"],
        )
    else:
        for i in range(params["table_count"]):
            x = -params["width"] * 0.3 + (i % 3) * params["table_spacing"]
            y = 0.75 + (i // 3) * 1.8
            instance(c, lib.masters["table"], f"table_{i}", (x, y, 0))
            for j, a in enumerate((0, math.pi)):
                instance(
                    c,
                    lib.masters["chair"],
                    f"chair_{i}_{j}",
                    (x + math.sin(a) * 0.85, y + math.cos(a) * 0.85, 0),
                    a,
                )
        box(
            c,
            "restaurant_counter",
            (params["width"] * 0.25, d - 0.65, 0.58),
            (params["counter_length"], 0.55, 0.58),
            lib.mats["wood"],
        )
        box(
            c,
            "kitchen_screen",
            (0, d - 0.15, 1.2),
            (params["width"] * 0.55, 0.10, 2.4),
            lib.mats["metal"],
        )
    for x in [
        (-params["width"] / 2) + 0.8 + i * params.get("light_spacing", 1.8)
        for i in range(max(1, int(params["width"] / params.get("light_spacing", 1.8))))
    ]:
        box(c, "light_strip", (x, d * 0.4, 2.85), (0.55, 0.08, 0.035), lib.mats["warm"])
    return c


def generate_commercial_frontage(params, lib, parent):
    c = collection("commercial_frontage", parent)
    w = params["frontage_width"]
    sw = params["sidewalk_width"]
    ch = params["curb_height"]
    box(c, "entrance_apron", (0, -1.0, 0.10), (w, 2.0, 0.10), lib.mats["concrete"])
    box(c, "sidewalk", (0, -2.0 - sw / 2, 0.12), (w, sw, 0.12), lib.mats["concrete"])
    box(c, "curb", (0, -2.0 - sw - 0.12, ch / 2), (w, 0.24, ch), lib.mats["concrete"])
    box(
        c,
        "accessible_ramp",
        (w * 0.25, -2.0 - sw - 0.20, ch * 0.35),
        (params["ramp_width"], 0.9, ch * 0.35),
        lib.mats["concrete"],
    )
    box(
        c,
        "drain_channel",
        (0, -2.0 - sw - 0.42, 0.07),
        (w, 0.22, 0.07),
        lib.mats["metal"],
    )
    for i in range(int(w / params["drain_interval"])):
        box(
            c,
            "drain_grate",
            (-w / 2 + (i + 0.5) * params["drain_interval"], -2.0 - sw - 0.54, 0.15),
            (params["drain_interval"] - 0.08, 0.04, 0.012),
            lib.mats["black"],
            0,
        )
    return c


def generate_parking_lot(params, lib, parent, seed):
    rng = random.Random(seed)
    c = collection("parking_lot", parent)
    L, W = params["parking_length"], params["parking_width"]
    box(c, "asphalt", (0, 0, 0.04), (W, L, 0.04), lib.mats["asphalt"])
    count = params["parking_count"]
    pw = params["parking_space_width"]
    pl = params["parking_space_length"]
    start = -W / 2 + pw / 2
    for i in range(count):
        x = start + i * pw
        for dx in (-pw / 2, pw / 2):
            box(
                c,
                "parking_line",
                (x + dx, 0, 0.095),
                (0.045, pl / 2, 0.012),
                lib.mats["paint"],
                0,
            )
        instance(
            c,
            lib.masters["wheel_stop"],
            f"wheel_stop_{i}",
            (x, L / 2 - pl * 0.30, 0.10),
            rng.uniform(-0.012, 0.012),
        )
    box(
        c,
        "rear_curb",
        (0, L / 2 - 0.12, params["curb_height"] / 2),
        (W, 0.24, params["curb_height"]),
        lib.mats["concrete"],
    )
    box(
        c,
        "parking_sidewalk",
        (0, L / 2 + params["sidewalk_width"] / 2, params["curb_height"]),
        (W, params["sidewalk_width"], 0.10),
        lib.mats["concrete"],
    )
    box(
        c,
        "entrance",
        (W / 2 - 0.9, -L / 2, 0.03),
        (1.8, 1.2, 0.03),
        lib.mats["asphalt"],
    )
    box(c, "drainage", (0, -L / 2 + 0.25, 0.07), (W, 0.22, 0.07), lib.mats["metal"])
    c["parking_count"] = count
    c["parking_angle"] = params["parking_angle"]
    return c


def populate_commercial_details(lib, parent, seed):
    rng = random.Random(seed)
    placements = []
    specs = [
        ("trash_A", (-7, -1, 0)),
        ("trash_B", (7, -1, 0)),
        ("bike_rack", (-5, -2, 0)),
        ("planter", (-8, -2, 0)),
        ("planter", (8, -2, 0)),
        ("sign", (5, -1, 0)),
        ("electrical", (-8, 0.2, 0)),
        ("ac", (7, 0.2, 0.2)),
    ]
    for i, (key, loc) in enumerate(specs):
        placements.append(
            instance(
                parent,
                lib.masters[key],
                f"{key}_{i}",
                loc,
                rng.uniform(-0.04, 0.04),
                (rng.uniform(0.96, 1.04),) * 3,
            )
        )
    for i, x in enumerate((-3, 0, 3)):
        placements.append(
            instance(parent, lib.masters["table"], f"outdoor_table_{i}", (x, -1.4, 0))
        )
        placements.append(
            instance(
                parent,
                lib.masters["chair"],
                f"outdoor_chair_{i}",
                (x, -2.2, 0),
                math.pi,
            )
        )
    return placements


def generate_commercial_zone(root, seed=4304):
    started = time.perf_counter()
    lib = prepare_commercial_asset_library(seed)
    zone = collection("generated_commercial_zone", root)
    rng = random.Random(seed)
    convenience = {
        "name": "convenience",
        "storefront_width": 15.5,
        "storefront_height": 5.1,
        "number_of_bays": 6,
        "door_width": 1.35,
        "door_height": 2.55,
        "window_width": 2.1,
        "window_height": 2.65,
        "mullion_width": 0.07,
        "mullion_depth": 0.10,
        "column_width": 0.18,
        "canopy_depth": 1.3,
        "canopy_thickness": 0.14,
        "sign_height": 0.72,
        "sign_depth": 0.18,
        "facade_inset": 0.24,
        "baseboard_height": 0.42,
        "door_bay": 5,
        "wall_mat": "wall",
    }
    restaurant = {
        **convenience,
        "name": "restaurant",
        "storefront_width": 15,
        "storefront_height": 5.6,
        "number_of_bays": 5,
        "door_width": 1.5,
        "window_width": 2.35,
        "canopy_depth": 1.65,
        "sign_height": 0.82,
        "wall_mat": "wall_red",
        "door_bay": 4,
    }
    sf1 = generate_storefront(convenience, lib, zone, seed + 1)
    sf2 = generate_storefront(restaurant, lib, zone, seed + 2)
    instance(zone, sf1, "convenience_front", (-39, -25.65, 0.2))
    instance(zone, sf2, "restaurant_front", (-23.5, -25.65, 0.2))
    ip1 = generate_store_interior_proxy(
        "convenience",
        {
            "width": 14,
            "interior_depth": 4,
            "shelf_rows": 5,
            "shelf_spacing": 2.1,
            "shelf_height": 1.8,
            "counter_length": 2.8,
            "light_spacing": 1.8,
        },
        lib,
        zone,
        seed + 3,
    )
    ip2 = generate_store_interior_proxy(
        "restaurant",
        {
            "width": 13.5,
            "interior_depth": 4,
            "table_count": 5,
            "table_spacing": 2.3,
            "chair_count": 2,
            "counter_length": 3.2,
            "light_spacing": 1.7,
        },
        lib,
        zone,
        seed + 4,
    )
    instance(zone, ip1, "convenience_interior", (-39, -20.8, 0.2), math.pi)
    instance(zone, ip2, "restaurant_interior", (-23.5, -20.8, 0.2), math.pi)
    frontage = generate_commercial_frontage(
        {
            "frontage_width": 31,
            "sidewalk_width": 2.4,
            "curb_height": 0.15,
            "ramp_width": 1.4,
            "drain_interval": 1.8,
        },
        lib,
        zone,
    )
    instance(zone, frontage, "frontage", (-31, -27.0, 0.05))
    parking = generate_parking_lot(
        {
            "parking_length": 15,
            "parking_width": 22,
            "parking_space_width": 2.65,
            "parking_space_length": 5.1,
            "parking_count": 8,
            "aisle_width": 6,
            "curb_height": 0.15,
            "sidewalk_width": 2.2,
            "parking_angle": 0,
        },
        lib,
        zone,
        seed + 5,
    )
    instance(zone, parking, "parking", (-22, -38, 0.05))
    details = populate_commercial_details(lib, zone, seed + 6)
    return (
        zone,
        lib,
        {
            "generation_seconds": time.perf_counter() - started,
            "detail_instances": len(details),
        },
    )
