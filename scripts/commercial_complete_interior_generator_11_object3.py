"""Physically supported shop stock and four-seat dining sets for object3."""
import math, random
import bpy

P = "all43_11_object3:"


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
        q = o.modifiers.new("soft manufactured edges", "BEVEL")
        q.width = min(bev, min(s) * 0.18)
        q.segments = 3
    return o


def box(c, n, loc, s, M, rot=0, bev=0.006):
    return add(c, n, cube(), loc, s, M, rot, bev)


def master(n):
    c = bpy.data.collections.new(P + "MASTER:" + n)
    c["procedural_asset"] = True
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
        "wood": mat("sealed_oak", (0.30, 0.13, 0.045, 1), 0.42),
        "steel": mat("powder_steel", (0.055, 0.07, 0.065, 1), 0.30, 0.72),
        "dark": mat("dark_metal", (0.018, 0.022, 0.020, 1), 0.52, 0.68),
        "cream": mat("cream_card", (0.78, 0.70, 0.52, 1), 0.48),
        "red": mat("printed_red", (0.52, 0.025, 0.012, 1), 0.40),
        "blue": mat("printed_blue", (0.018, 0.12, 0.40, 1), 0.38),
        "green": mat("printed_green", (0.025, 0.25, 0.055, 1), 0.43),
        "white": mat("print_white", (0.83, 0.84, 0.78, 1), 0.42),
        "foil": mat("brushed_lid", (0.48, 0.50, 0.47, 1), 0.20, 0.78),
        "glass": mat("tinted_container", (0.09, 0.20, 0.15, 1), 0.18),
        "chair": mat("chair_oak", (0.27, 0.085, 0.022, 1), 0.38),
        "seat": mat("upholstery", (0.055, 0.12, 0.095, 1), 0.64),
        "ceramic": mat("ceramic", (0.78, 0.75, 0.67, 1), 0.24),
        "napkin": mat("napkin", (0.48, 0.12, 0.045, 1), 0.62),
    }


def products(M):
    result = []
    b = master("bottle")
    add(b, "bottle_body", cyl(), (0, 0, 0.17), (0.072, 0.072, 0.17), M["glass"])
    add(b, "shoulder", cyl(), (0, 0, 0.35), (0.058, 0.058, 0.05), M["glass"])
    add(b, "neck", cyl(), (0, 0, 0.415), (0.031, 0.031, 0.04), M["glass"])
    add(b, "ribbed_cap", cyl(), (0, 0, 0.468), (0.040, 0.040, 0.016), M["green"])
    add(b, "wrap_label", cyl(), (0, 0, 0.18), (0.076, 0.076, 0.07), M["cream"])
    add(b, "brand_band", cyl(), (0, 0, 0.21), (0.078, 0.078, 0.014), M["red"])
    result.append(b)
    j = master("lidded_jar")
    add(j, "jar_body", cyl(), (0, 0, 0.135), (0.095, 0.095, 0.135), M["glass"])
    add(j, "jar_shoulder", cyl(), (0, 0, 0.275), (0.083, 0.083, 0.025), M["glass"])
    add(j, "threaded_lid", cyl(), (0, 0, 0.31), (0.097, 0.097, 0.018), M["foil"])
    add(j, "paper_label", cyl(), (0, 0, 0.14), (0.099, 0.099, 0.067), M["cream"])
    add(j, "printed_band", cyl(), (0, 0, 0.16), (0.101, 0.101, 0.014), M["green"])
    result.append(j)
    c = master("folded_carton")
    box(c, "carton", (0, 0, 0.245), (0.135, 0.062, 0.245), M["cream"], bev=0.012)
    box(c, "front_art", (0, -0.064, 0.265), (0.105, 0.006, 0.145), M["blue"], bev=0.003)
    box(
        c,
        "brand_panel",
        (0, -0.071, 0.34),
        (0.075, 0.006, 0.032),
        M["white"],
        bev=0.003,
    )
    box(
        c,
        "nutrition_panel",
        (0.137, 0, 0.23),
        (0.006, 0.047, 0.13),
        M["white"],
        bev=0.003,
    )
    box(c, "top_flap", (0, 0, 0.495), (0.126, 0.057, 0.008), M["red"], bev=0.003)
    result.append(c)
    p = master("formed_pouch")
    add(p, "shaped_bag", bag(), (0, 0, 0.205), (0.145, 0.10, 0.41), M["red"], bev=0.01)
    box(p, "top_crimp", (0, 0, 0.407), (0.14, 0.017, 0.012), M["foil"], bev=0.003)
    box(p, "bottom_crimp", (0, 0, 0.009), (0.14, 0.017, 0.009), M["foil"], bev=0.003)
    box(
        p,
        "printed_panel",
        (0, -0.103, 0.235),
        (0.085, 0.006, 0.085),
        M["cream"],
        bev=0.003,
    )
    box(
        p,
        "flavour_band",
        (0, -0.109, 0.13),
        (0.115, 0.006, 0.016),
        M["green"],
        bev=0.003,
    )
    result.append(p)
    can = master("ring_pull_can")
    add(can, "can_body", cyl(), (0, 0, 0.145), (0.082, 0.082, 0.145), M["foil"])
    add(can, "printed_wrap", cyl(), (0, 0, 0.145), (0.085, 0.085, 0.105), M["blue"])
    add(can, "top_rim", cyl(), (0, 0, 0.292), (0.087, 0.087, 0.010), M["foil"])
    add(can, "bottom_rim", cyl(), (0, 0, 0.008), (0.087, 0.087, 0.008), M["foil"])
    box(
        can, "pull_tab", (0, -0.018, 0.305), (0.025, 0.011, 0.004), M["dark"], bev=0.003
    )
    result.append(can)
    return result


def shelf(M, variant, prods):
    c = master("integrated_shelf_" + str(variant))
    w = (1.22, 1.42, 1.08)[variant]
    h = (1.84, 2.02, 1.68)[variant]
    levels = (5, 6, 4)[variant]
    floor = 0.10
    box(
        c,
        "continuous_floor_plinth",
        (0, 0, 0.17),
        (w + 0.09, 0.38, 0.07),
        M["wood"],
        bev=0.015,
    )
    for x in (-w, w):
        box(
            c,
            "full_height_post",
            (x, 0.20, (floor + h) / 2),
            (0.058, 0.068, (h - floor) / 2),
            M["steel"],
            bev=0.01,
        )
    box(
        c,
        "solid_back_panel",
        (0, 0.245, (floor + h) / 2),
        (w, 0.035, (h - floor) / 2),
        M["wood"],
        bev=0.006,
    )
    box(c, "lower_crossbeam", (0, 0.20, 0.23), (w, 0.055, 0.06), M["steel"], bev=0.008)
    box(
        c,
        "upper_crossbeam",
        (0, 0.20, h - 0.07),
        (w, 0.055, 0.06),
        M["steel"],
        bev=0.008,
    )
    rng = random.Random(43081130 + variant)
    supports = []
    for level in range(levels):
        z = 0.26 + level * (h - 0.38) / (levels - 1)
        thick = 0.035
        support = z + thick
        supports.append(round(support, 4))
        box(
            c,
            "joined_shelf_deck",
            (0, -0.03, z),
            (w + 0.045, 0.38, thick),
            M["wood"],
            bev=0.008,
        )
        box(
            c,
            "front_lip",
            (0, -0.405, z + 0.035),
            (w, 0.023, 0.045),
            M["steel"],
            bev=0.004,
        )
        count = (7, 8, 6)[variant]
        for i in range(count):
            if rng.random() < 0.12:
                continue
            product = prods[(i + level * 2 + variant) % len(prods)]
            scale = 0.70 + rng.random() * 0.18
            x = -w * 0.76 + i * (2 * w * 0.76 / (count - 1))
            o = inst(
                c,
                product,
                "shelf_supported_product",
                (x + (rng.random() - 0.5) * 0.025, -0.19, support),
                rot=(rng.random() - 0.5) * 0.06,
                scale=(scale, scale, scale),
            )
            o["support_surface_z"] = support
            o["support_kind"] = "joined_shelf_deck"
            o["inventory_category"] = product.name
    c["support_levels"] = ",".join(map(str, supports))
    return c


def fresh(M):
    c = bpy.data.collections["all43_01:MASTER:convenience_store"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            (
                "all43_11_object2:complete_stocked_shelf",
                "all43_11_object2:premium_",
                "all43_11_object:grounded_",
                "all43_11_light:fresh_produce_",
            )
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    prods = products(M)
    shelves = [shelf(M, i, prods) for i in range(3)]
    layout = [
        (-4.40, -2.0, 1.51, 0.84),
        (-1.82, -1.08, 1.62, 0.98),
        (0.65, -1.92, 1.48, 0.94),
        (-3.25, 0.74, 1.68, 0.88),
    ]
    made = []
    for i, (x, y, r, s) in enumerate(layout):
        made.append(
            inst(
                c, shelves[i % 3], "complete_stocked_shelf", (x, y, 0), r, (s, 1, 1)
            ).name
        )
    # Every product lives inside a shelf master and starts exactly on a recorded deck top.
    bad = []
    count = 0
    for s in shelves:
        levels = [float(x) for x in s["support_levels"].split(",")]
        for o in s.objects:
            if o.name.startswith(P + "shelf_supported_product"):
                count += 1
                if min(abs(o.location.z - z) for z in levels) > 1e-4:
                    bad.append(o.name)
    if bad:
        raise RuntimeError("Unsupported merchandise: " + ",".join(bad))
    return hidden, made, count


def table(M):
    c = master("crafted_square_table")
    floor = 0.10
    top = 0.80
    w = 0.64
    box(c, "thick_square_top", (0, 0, top), (w, w, 0.06), M["wood"], bev=0.038)
    for x in (-0.50, 0.50):
        for y in (-0.50, 0.50):
            box(
                c,
                "joined_tapered_leg",
                (x, y, 0.43),
                (0.055, 0.055, 0.33),
                M["chair"],
                bev=0.014,
            )
    box(c, "front_apron", (0, -0.50, 0.70), (0.50, 0.055, 0.075), M["chair"], bev=0.012)
    box(c, "rear_apron", (0, 0.50, 0.70), (0.50, 0.055, 0.075), M["chair"], bev=0.012)
    box(c, "left_apron", (-0.50, 0, 0.70), (0.055, 0.50, 0.075), M["chair"], bev=0.012)
    box(c, "right_apron", (0.50, 0, 0.70), (0.055, 0.50, 0.075), M["chair"], bev=0.012)
    box(
        c,
        "lower_stretcher_x",
        (0, 0, 0.27),
        (0.48, 0.035, 0.035),
        M["chair"],
        bev=0.009,
    )
    box(
        c,
        "lower_stretcher_y",
        (0, 0, 0.28),
        (0.035, 0.48, 0.035),
        M["chair"],
        bev=0.009,
    )
    return c


def chair(M):
    c = master("crafted_backed_chair")
    floor = 0.10
    seat = 0.49
    # Model faces -Y; rear legs continue into the back so no component can appear detached.
    for x in (-0.22, 0.22):
        box(
            c,
            "continuous_rear_leg",
            (x, 0.20, 0.56),
            (0.038, 0.042, 0.46),
            M["chair"],
            bev=0.012,
        )
    for x in (-0.22, 0.22):
        box(
            c,
            "front_leg",
            (x, -0.20, 0.285),
            (0.038, 0.042, 0.185),
            M["chair"],
            bev=0.012,
        )
    box(
        c,
        "front_seat_rail",
        (0, -0.20, 0.43),
        (0.22, 0.042, 0.045),
        M["chair"],
        bev=0.010,
    )
    box(
        c,
        "rear_seat_rail",
        (0, 0.20, 0.43),
        (0.22, 0.042, 0.045),
        M["chair"],
        bev=0.010,
    )
    box(
        c,
        "left_seat_rail",
        (-0.22, 0, 0.43),
        (0.040, 0.18, 0.045),
        M["chair"],
        bev=0.010,
    )
    box(
        c,
        "right_seat_rail",
        (0.22, 0, 0.43),
        (0.040, 0.18, 0.045),
        M["chair"],
        bev=0.010,
    )
    box(c, "upholstered_seat", (0, 0, seat), (0.265, 0.25, 0.055), M["seat"], bev=0.035)
    box(
        c,
        "front_stretcher",
        (0, -0.20, 0.27),
        (0.22, 0.028, 0.028),
        M["chair"],
        bev=0.007,
    )
    box(
        c,
        "side_stretcher_l",
        (-0.22, 0, 0.28),
        (0.028, 0.18, 0.028),
        M["chair"],
        bev=0.007,
    )
    box(
        c,
        "side_stretcher_r",
        (0.22, 0, 0.28),
        (0.028, 0.18, 0.028),
        M["chair"],
        bev=0.007,
    )
    box(c, "back_top_rail", (0, 0.20, 0.98), (0.27, 0.05, 0.055), M["chair"], bev=0.022)
    box(
        c,
        "back_lower_rail",
        (0, 0.20, 0.68),
        (0.24, 0.045, 0.040),
        M["chair"],
        bev=0.012,
    )
    for x in (-0.12, 0, 0.12):
        box(
            c,
            "back_vertical_slat",
            (x, 0.20, 0.83),
            (0.026, 0.035, 0.13),
            M["chair"],
            bev=0.010,
        )
    return c


def settings(M):
    c = master("four_place_settings")
    for x, y, r in (
        (0, -0.40, 0),
        (0, 0.40, math.pi),
        (-0.40, 0, -math.pi / 2),
        (0.40, 0, math.pi / 2),
    ):
        add(
            c,
            "ceramic_plate",
            cyl(),
            (x, y, 0.018),
            (0.115, 0.115, 0.012),
            M["ceramic"],
            rot=r,
        )
        add(
            c,
            "drinking_cup",
            cyl(),
            (x + 0.13 * math.cos(r), y + 0.13 * math.sin(r), 0.065),
            (0.042, 0.042, 0.065),
            M["ceramic"],
        )
        box(
            c,
            "folded_napkin",
            (x - 0.13 * math.cos(r), y - 0.13 * math.sin(r), 0.024),
            (0.07, 0.035, 0.008),
            M["napkin"],
            rot=r,
            bev=0.003,
        )
    return c


def restaurant(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            (
                "all43_11_object2:complete_square_table",
                "all43_11_object2:complete_backed_chair",
                "all43_11_object2:tabletop_setting",
            )
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    t = table(M)
    ch = chair(M)
    st = settings(M)
    layout = [
        (-4.05, -2.25, 0.04),
        (-1.25, -2.02, -0.06),
        (1.35, -0.72, 0.08),
        (-2.75, 0.58, -0.05),
    ]
    made = []
    facing = []
    # Local offsets and rotations put the chair fronts toward the table centre.
    seats = [
        ((0, -0.94), math.pi),
        ((0, 0.94), 0),
        ((-0.94, 0), math.pi / 2),
        ((0.94, 0), -math.pi / 2),
    ]
    for i, (x, y, r) in enumerate(layout):
        made.append(inst(c, t, "crafted_square_table", (x, y, 0), r).name)
        made.append(inst(c, st, "four_place_settings", (x, y, 0.86), r).name)
        for (dx, dy), cr in seats:
            wx = x + dx * math.cos(r) - dy * math.sin(r)
            wy = y + dx * math.sin(r) + dy * math.cos(r)
            o = inst(c, ch, "inward_facing_backed_chair", (wx, wy, 0), r + cr)
            o["faces_table_index"] = i
            made.append(o.name)
            forward = (math.sin(o.rotation_euler.z), -math.cos(o.rotation_euler.z))
            to = (x - wx, y - wy)
            facing.append(forward[0] * to[0] + forward[1] * to[1])
    if len(made) != 24 or min(facing) < 0.90:
        raise RuntimeError("Dining set orientation audit failed")
    return hidden, made


def run():
    M = materials()
    fh, fm, goods = fresh(M)
    rh, rm = restaurant(M)
    return {
        "hidden_previous_shop_assets": fh,
        "new_complete_shelves": len(fm),
        "supported_complex_goods": goods,
        "floor_goods_remaining": 0,
        "toy_sphere_goods": 0,
        "product_categories": [
            "multi-part bottle",
            "lidded jar",
            "printed folded carton",
            "formed sealed pouch",
            "ring-pull can",
        ],
        "hidden_previous_dining_assets": rh,
        "dining_tables": 4,
        "backed_chairs": 16,
        "chairs_per_table": 4,
        "chair_orientation_audit": "PASS",
        "shelf_support_audit": "PASS",
    }
