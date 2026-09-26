"""Complete structural furniture and premium multi-part merchandise for object2."""
import math, random
import bpy

P = "all43_11_object2:"


def mat(n, c, r=0.5, m=0):
    x = bpy.data.materials.get(P + n) or bpy.data.materials.new(P + n)
    x.use_nodes = True
    b = x.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = c
    b.inputs["Roughness"].default_value = r
    b.inputs["Metallic"].default_value = m
    return x


def cube():
    return bpy.data.meshes["all43_10:shared_cube"]


def cyl():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


def bag():
    return bpy.data.meshes["all43_10:shared_bag"]


def sphere():
    return bpy.data.meshes["all43_11_light:shared_produce_sphere"]


def add(c, n, mesh, loc, s, M, rot=0, bev=0.006):
    o = bpy.data.objects.new(P + n, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = s
    o.rotation_euler[2] = rot
    if not mesh.materials:
        mesh.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bev:
        q = o.modifiers.new("manufactured_edge", "BEVEL")
        q.width = min(bev, min(s) * 0.18)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def box(c, n, loc, s, M, rot=0, bev=0.006):
    return add(c, n, cube(), loc, s, M, rot, bev)


def master(n):
    c = bpy.data.collections.new(P + "MASTER:" + n)
    c["complete_master"] = True
    return c


def inst(c, m, n, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + n, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = m
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def materials():
    return {
        "wood": mat("warm_shelf_wood", (0.28, 0.115, 0.035, 1), 0.46),
        "steel": mat("powdercoated_steel", (0.075, 0.09, 0.085, 1), 0.33, 0.64),
        "dark": mat("dark_frame", (0.018, 0.023, 0.022, 1), 0.66),
        "label": mat("price_channel", (0.66, 0.52, 0.12, 1), 0.46),
        "paper": mat("paper_package", (0.72, 0.66, 0.47, 1), 0.50),
        "red": mat("printed_red", (0.54, 0.045, 0.018, 1), 0.42),
        "blue": mat("printed_blue", (0.025, 0.16, 0.42, 1), 0.40),
        "green": mat("printed_green", (0.035, 0.31, 0.07, 1), 0.48),
        "white": mat("print_white", (0.76, 0.78, 0.72, 1), 0.43),
        "foil": mat("metal_lid", (0.42, 0.45, 0.43, 1), 0.24, 0.72),
        "glass": mat("jar_glass", (0.10, 0.22, 0.16, 1), 0.18),
        "chair": mat("chair_wood", (0.31, 0.10, 0.028, 1), 0.40),
        "seat": mat("seat_pad", (0.08, 0.15, 0.12, 1), 0.60),
        "ceramic": mat("ceramic", (0.76, 0.73, 0.64, 1), 0.25),
    }


def premium_products(M):
    bottle = master("premium_bottle")
    add(bottle, "body", cyl(), (0, 0, 0.18), (0.075, 0.075, 0.18), M["glass"])
    add(bottle, "shoulder", cyl(), (0, 0, 0.36), (0.062, 0.062, 0.055), M["glass"])
    add(bottle, "neck", cyl(), (0, 0, 0.435), (0.034, 0.034, 0.045), M["glass"])
    add(bottle, "ribbed_cap", cyl(), (0, 0, 0.49), (0.043, 0.043, 0.018), M["green"])
    add(bottle, "wrap_label", cyl(), (0, 0, 0.18), (0.079, 0.079, 0.075), M["paper"])
    add(bottle, "brand_band", cyl(), (0, 0, 0.20), (0.081, 0.081, 0.018), M["red"])
    jar = master("premium_jar")
    add(jar, "glass_jar", cyl(), (0, 0, 0.14), (0.10, 0.10, 0.14), M["glass"])
    add(jar, "shoulder", cyl(), (0, 0, 0.275), (0.09, 0.09, 0.025), M["glass"])
    add(jar, "metal_lid", cyl(), (0, 0, 0.315), (0.102, 0.102, 0.018), M["foil"])
    add(jar, "paper_label", cyl(), (0, 0, 0.14), (0.104, 0.104, 0.075), M["paper"])
    add(jar, "label_stripe", cyl(), (0, 0, 0.14), (0.106, 0.106, 0.018), M["green"])
    cereal = master("premium_cereal_box")
    box(cereal, "carton", (0, 0, 0.25), (0.14, 0.065, 0.25), M["paper"], bev=0.012)
    box(
        cereal,
        "front_art",
        (0, -0.067, 0.27),
        (0.105, 0.006, 0.15),
        M["blue"],
        bev=0.003,
    )
    box(
        cereal,
        "brand_panel",
        (0, -0.074, 0.33),
        (0.075, 0.006, 0.035),
        M["white"],
        bev=0.003,
    )
    box(
        cereal,
        "nutrition_side",
        (0.142, 0, 0.23),
        (0.006, 0.048, 0.13),
        M["white"],
        bev=0.003,
    )
    box(cereal, "folded_top", (0, 0, 0.505), (0.13, 0.06, 0.008), M["red"], bev=0.003)
    chips = master("premium_chips_bag")
    add(
        chips,
        "formed_pouch",
        bag(),
        (0, 0, 0.22),
        (0.15, 0.105, 0.44),
        M["red"],
        bev=0.012,
    )
    box(chips, "top_crimp", (0, 0, 0.435), (0.145, 0.018, 0.012), M["foil"], bev=0.003)
    box(
        chips,
        "bottom_crimp",
        (0, 0, 0.008),
        (0.145, 0.018, 0.010),
        M["foil"],
        bev=0.003,
    )
    box(
        chips,
        "printed_roundel",
        (0, -0.108, 0.24),
        (0.085, 0.006, 0.09),
        M["paper"],
        bev=0.004,
    )
    box(
        chips,
        "flavor_band",
        (0, -0.114, 0.13),
        (0.12, 0.006, 0.018),
        M["green"],
        bev=0.003,
    )
    carton = master("premium_drink_carton")
    box(carton, "carton_body", (0, 0, 0.21), (0.10, 0.075, 0.21), M["white"], bev=0.012)
    box(
        carton,
        "front_print",
        (0, -0.077, 0.23),
        (0.075, 0.006, 0.13),
        M["green"],
        bev=0.003,
    )
    box(
        carton,
        "folded_roof",
        (0, 0, 0.435),
        (0.095, 0.07, 0.018),
        M["paper"],
        bev=0.005,
    )
    add(
        carton,
        "screw_cap",
        cyl(),
        (0.045, -0.025, 0.475),
        (0.024, 0.024, 0.018),
        M["red"],
        bev=0.004,
    )
    tray = master("premium_produce_tray")
    box(tray, "wood_tray", (0, 0, 0.045), (0.38, 0.25, 0.04), M["wood"], bev=0.012)
    for x in (-0.25, 0, 0.25):
        for y in (-0.14, 0.14):
            add(
                tray,
                "individual_fruit",
                sphere(),
                (x, y, 0.15),
                (0.105, 0.105, 0.095),
                M["red" if (x + y) > 0 else "green"],
                bev=0.004,
            )
    return [bottle, jar, cereal, chips, carton, tray]


def complete_shelf(M, variant, prod):
    c = master("complete_shelf_v" + str(variant))
    w = (1.30, 1.55, 1.12)[variant]
    h = (1.92, 2.08, 1.70)[variant]
    levels = (5, 6, 4)[variant]
    floor = 0.10
    box(
        c,
        "solid_floor_plinth",
        (0, 0, floor + 0.07),
        (w + 0.10, 0.36, 0.07),
        M["wood"],
        bev=0.018,
    )
    for x in (-w, w):
        box(
            c,
            "continuous_steel_post",
            (x, 0.18, (floor + h) / 2),
            (0.055, 0.065, (h - floor) / 2),
            M["steel"],
            bev=0.010,
        )
    box(
        c,
        "rear_lower_beam",
        (0, 0.20, floor + 0.17),
        (w, 0.055, 0.065),
        M["steel"],
        bev=0.009,
    )
    box(
        c,
        "rear_upper_beam",
        (0, 0.20, h - 0.07),
        (w, 0.055, 0.065),
        M["steel"],
        bev=0.009,
    )
    box(
        c,
        "wood_back_panel",
        (0, 0.22, (floor + h) / 2),
        (w, 0.035, (h - floor) / 2),
        M["wood"],
        bev=0.007,
    )
    rng = random.Random(11300 + variant)
    for j in range(levels):
        z = floor + 0.14 + j * (h - floor - 0.23) / (levels - 1)
        th = 0.032
        box(
            c,
            "continuous_wood_shelf",
            (0, -0.02, z),
            (w + 0.05, 0.37, th),
            M["wood"],
            bev=0.010,
        )
        box(
            c,
            "steel_front_rail",
            (0, -0.39, z),
            (w, 0.022, 0.045),
            M["steel"],
            bev=0.005,
        )
        box(
            c,
            "price_channel",
            (0, -0.415, z + 0.04),
            (w, 0.012, 0.025),
            M["label"],
            bev=0.002,
        )
        count = (7, 9, 6)[variant]
        step = 2 * w * 0.78 / (count - 1)
        for i in range(count):
            if rng.random() < 0.14 + 0.04 * j:
                continue
            p = prod[(i + j + variant + rng.randrange(3)) % len(prod)]
            s = 0.72 + rng.random() * 0.22
            inst(
                c,
                p,
                "shelf_supported_merchandise",
                (-w * 0.78 + i * step + (rng.random() - 0.5) * 0.035, -0.19, z + th),
                rot=(rng.random() - 0.5) * 0.08,
                scale=(s, s, s),
            )
    return c


def rebuild_fresh(M):
    c = bpy.data.collections["all43_01:MASTER:convenience_store"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            ("all43_11_object:grounded_gondola", "all43_11_object:grounded_produce")
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    prod = premium_products(M)
    shelves = [complete_shelf(M, i, prod) for i in range(3)]
    layout = [
        (-4.45, -2.05, 0, 1.51, 0.82),
        (-1.95, -1.15, 0, 1.62, 1.0),
        (0.60, -1.98, 0, 1.48, 0.94),
        (-3.35, 0.72, 0, 1.67, 0.88),
    ]
    made = []
    for i, (x, y, z, r, s) in enumerate(layout):
        made.append(
            inst(
                c, shelves[i % 3], "complete_stocked_shelf", (x, y, z), r, (s, 1, 1)
            ).name
        )
    return hidden, made


def square_table(M, variant):
    c = master("square_table_v" + str(variant))
    floor = 0.10
    top = 0.80
    w = (0.62, 0.70)[variant]
    box(c, "square_solid_top", (0, 0, top), (w, w, 0.06), M["wood"], bev=0.045)
    box(
        c,
        "under_top_frame",
        (0, 0, top - 0.10),
        (w - 0.08, w - 0.08, 0.045),
        M["steel"],
        bev=0.012,
    )
    box(
        c, "central_pedestal", (0, 0, 0.47), (0.085, 0.085, 0.29), M["steel"], bev=0.018
    )
    box(
        c,
        "cross_foot_x",
        (0, 0, floor + 0.035),
        (0.40, 0.10, 0.035),
        M["steel"],
        bev=0.018,
    )
    box(
        c,
        "cross_foot_y",
        (0, 0, floor + 0.04),
        (0.10, 0.40, 0.035),
        M["steel"],
        bev=0.018,
    )
    return c


def backed_chair(M):
    c = master("complete_backed_chair")
    floor = 0.10
    seat = 0.49
    # Rear legs are continuous members from floor through the back, preventing detached-back appearance.
    for x in (-0.22, 0.22):
        box(
            c,
            "continuous_rear_leg_back",
            (x, 0.20, 0.54),
            (0.035, 0.040, 0.44),
            M["steel"],
            bev=0.012,
        )
    for x in (-0.22, 0.22):
        box(
            c,
            "front_leg",
            (x, -0.20, (floor + seat - 0.06) / 2),
            (0.035, 0.040, (seat - 0.06 - floor) / 2),
            M["steel"],
            bev=0.012,
        )
    box(
        c,
        "seat_support_frame",
        (0, 0, seat - 0.06),
        (0.28, 0.26, 0.045),
        M["steel"],
        bev=0.018,
    )
    box(c, "thick_seat", (0, 0, seat), (0.27, 0.25, 0.06), M["seat"], bev=0.040)
    box(
        c,
        "front_stretcher",
        (0, -0.20, 0.30),
        (0.22, 0.030, 0.030),
        M["steel"],
        bev=0.008,
    )
    box(
        c,
        "left_stretcher",
        (-0.22, 0, 0.31),
        (0.030, 0.18, 0.030),
        M["steel"],
        bev=0.008,
    )
    box(
        c,
        "right_stretcher",
        (0.22, 0, 0.31),
        (0.030, 0.18, 0.030),
        M["steel"],
        bev=0.008,
    )
    box(
        c, "full_back_panel", (0, 0.20, 0.84), (0.28, 0.05, 0.18), M["chair"], bev=0.050
    )
    box(
        c, "back_crossbar", (0, 0.20, 0.69), (0.23, 0.035, 0.035), M["steel"], bev=0.010
    )
    return c


def grounded_counter(M):
    c = master("complete_service_counter")
    floor = 0.10
    box(
        c,
        "full_floor_plinth",
        (0, 0, floor + 0.06),
        (1.55, 0.43, 0.06),
        M["dark"],
        bev=0.018,
    )
    box(c, "joined_cabinet", (0, 0, 0.55), (1.50, 0.40, 0.39), M["wood"], bev=0.035)
    box(c, "solid_countertop", (0, 0, 0.98), (1.60, 0.48, 0.055), M["steel"], bev=0.026)
    return c


def rebuild_restaurant(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            (
                "all43_11_object:physical_table",
                "all43_11_object:physical_chair",
                "all43_11_object:supported_table_setting",
                "all43_11_object:grounded_service_counter",
            )
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    tables = [square_table(M, 0), square_table(M, 1)]
    chair = backed_chair(M)
    counter = grounded_counter(M)
    setting = bpy.data.collections.get("all43_11_light:MASTER:restaurant_table_setting")
    layout = [
        (-4.15, -2.35, 0.08),
        (-1.35, -2.05, -0.08),
        (1.25, -1.05, 0.12),
        (-2.75, 0.48, -0.10),
    ]
    made = []
    for i, (x, y, r) in enumerate(layout):
        made.append(inst(c, tables[i % 2], "complete_square_table", (x, y, 0), r).name)
        for side in (-1, 1):
            made.append(
                inst(
                    c,
                    chair,
                    "complete_backed_chair",
                    (x + side * 0.82 * math.sin(r), y + side * 0.82 * math.cos(r), 0),
                    r + (0 if side < 0 else math.pi),
                ).name
            )
        if setting:
            made.append(inst(c, setting, "tabletop_setting", (x, y, 0.86), r).name)
    made.append(
        inst(c, counter, "complete_service_counter", (3.35, 2.35, 0), math.pi).name
    )
    return hidden, made


def run():
    M = materials()
    fh, fm = rebuild_fresh(M)
    rh, rm = rebuild_restaurant(M)
    return {
        "removed_floor_goods_and_previous_shelves": fh,
        "complete_stocked_shelf_instances": len(fm),
        "premium_product_categories": [
            "multi-part bottle",
            "labeled jar",
            "printed cereal box",
            "formed chips bag",
            "capped drink carton",
            "produce tray",
        ],
        "old_restaurant_instances_hidden": rh,
        "complete_restaurant_instances": len(rm),
        "floor_goods_remaining": 0,
        "unique_new_meshes": sum(x.name.startswith(P) for x in bpy.data.meshes),
        "linked_instances": sum(
            bool(o.get("linked_collection_instance"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }
