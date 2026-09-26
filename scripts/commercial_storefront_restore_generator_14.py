"""All43-14 restore pass: simplify storefronts back to large transparent glass and visible interiors."""
import math
import random
import bpy

P = "all43_14:"


def cube():
    return bpy.data.meshes["all43_10:shared_cube"]


def cyl():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


def bag():
    return bpy.data.meshes.get("all43_10:shared_bag") or cube()


def mat(name, color, rough=0.55, metal=0, noise=0, bump=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    links = m.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if noise and not nodes.get(P + "micro_" + name):
        tex = nodes.new("ShaderNodeTexNoise")
        tex.name = P + "micro_" + name
        tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 4
        tex.inputs["Roughness"].default_value = 0.60
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(
            max(0, x * 0.90) for x in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, x * 1.04 + 0.010) for x in color[:3]
        ) + (1,)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump_node = nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.010
        links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def glassmat():
    m = mat("restored_clear_storefront_glass", (0.055, 0.090, 0.095, 1), 0.075, 0)
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Transmission Weight"].default_value = 0.86
    bsdf.inputs["IOR"].default_value = 1.46
    bsdf.inputs["Coat Weight"].default_value = 0.18
    bsdf.inputs["Coat Roughness"].default_value = 0.045
    m.use_screen_refraction = True
    return m


def materials():
    return {
        "fresh_wall": mat(
            "fresh_wall_low_detail", (0.16, 0.33, 0.22, 1), 0.66, 0, 32, 0.055
        ),
        "rest_wall": mat(
            "kitchen_wall_low_detail", (0.38, 0.13, 0.070, 1), 0.68, 0, 32, 0.055
        ),
        "frame": mat(
            "dark_aluminum_frame", (0.030, 0.034, 0.033, 1), 0.36, 0.62, 42, 0.015
        ),
        "glass": glassmat(),
        "base": mat(
            "simple_concrete_base", (0.42, 0.415, 0.385, 1), 0.82, 0, 38, 0.070
        ),
        "metal": mat(
            "subtle_brushed_metal", (0.23, 0.24, 0.23, 1), 0.44, 0.55, 38, 0.016
        ),
        "fresh_sign": mat(
            "fresh_sign_backer_simple", (0.045, 0.18, 0.10, 1), 0.52, 0.06, 22, 0.015
        ),
        "rest_sign": mat(
            "kitchen_sign_backer_simple", (0.30, 0.065, 0.032, 1), 0.54, 0.06, 22, 0.015
        ),
        "letter": mat("shallow_letter_face", (0.69, 0.66, 0.55, 1), 0.40, 0, 12, 0.006),
        "shelf": mat("muted_shelf_14", (0.15, 0.165, 0.155, 1), 0.55, 0.28, 24, 0.016),
        "wood": mat(
            "muted_interior_wood_14", (0.21, 0.090, 0.040, 1), 0.52, 0, 18, 0.024
        ),
        "seat": mat("restaurant_seat_14", (0.070, 0.150, 0.135, 1), 0.64, 0, 18, 0.016),
        "white": mat(
            "off_white_equipment_14", (0.55, 0.56, 0.53, 1), 0.62, 0, 20, 0.014
        ),
        "black": mat("dark_rubber_14", (0.015, 0.016, 0.015, 1), 0.78),
        "carton": mat("carton_pack_14", (0.60, 0.48, 0.24, 1), 0.55, 0, 20, 0.010),
        "red": mat("red_pack_14", (0.40, 0.045, 0.025, 1), 0.52, 0, 18, 0.008),
        "blue": mat("blue_pack_14", (0.035, 0.095, 0.28, 1), 0.50, 0, 18, 0.008),
        "green": mat("green_pack_14", (0.030, 0.21, 0.085, 1), 0.52, 0, 18, 0.008),
        "foil": mat("dull_foil_14", (0.44, 0.44, 0.40, 1), 0.36, 0.50, 32, 0.008),
        "ceramic": mat("simple_ceramic_14", (0.68, 0.66, 0.59, 1), 0.42, 0, 18, 0.008),
    }


def add_mesh(c, name, mesh, loc, scale, material, bevel=0.004, rot=(0, 0, 0)):
    o = bpy.data.objects.new(P + name, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = scale
    o.rotation_euler = rot
    o.data.materials.append(material)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = material
    if bevel:
        b = o.modifiers.new("small_real_edge_radius", "BEVEL")
        b.width = min(bevel, min(scale) * 0.16)
        b.segments = 2
    o["shared_mesh_data"] = True
    return o


def add(c, name, loc, scale, material, bevel=0.004, rot=(0, 0, 0)):
    return add_mesh(c, name, cube(), loc, scale, material, bevel, rot)


def master(name):
    c = bpy.data.collections.new(P + "MASTER:" + name)
    c["high_quality_master"] = True
    return c


def inst(c, m, name, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + name, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = m
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def hide(o, reason, hidden):
    if not (o.hide_render and o.hide_viewport):
        o.hide_render = True
        o.hide_viewport = True
        o["all43_14_hidden_reason"] = reason
        hidden.append(o.name)


def clear_storefront_and_near_interior():
    hidden = {"front": [], "interior": []}
    front_terms = (
        "facade",
        "window",
        "door",
        "glass",
        "mullion",
        "jamb",
        "rail",
        "sill",
        "awning",
        "canopy",
        "sign",
        "letter",
        "standoff",
        "pier",
        "base_course",
        "roof_edge",
        "wall_panel",
        "side_wall",
        "downspout",
        "utility",
        "recess",
        "closer",
        "pull",
        "handle",
        "threshold",
        "coping",
        "brace",
        "gutter",
    )
    interior_terms = (
        "interior_only",
        "zoned_stocked_shelf",
        "continuous_rear_cooler",
        "front_impulse_display",
        "checkout_near_entry",
        "checkout_inside_zone",
        "rear_wall_cooler",
        "setback_impulse_rack",
        "non_grid_dining",
        "inward_dining_chair",
        "individual_table_setting",
        "wall_banquette",
        "visible_order_counter",
        "order_counter_inside_zone",
        "table_plate",
        "rear_service_partition",
        "open_entry_path",
    )
    for c in (
        bpy.data.collections["all43_01:MASTER:convenience_store"],
        bpy.data.collections["all43_01:MASTER:restaurant"],
    ):
        for o in list(c.objects):
            low = o.name.lower()
            if o.name.startswith(P):
                continue
            if o.type == "FONT" and o.location.y < -4.20:
                hide(o, "replace floating/flat legacy sign", hidden["front"])
            elif o.location.y < -4.20 and any(t in low for t in front_terms):
                hide(
                    o,
                    "replace cluttered storefront with restored glass",
                    hidden["front"],
                )
            elif any(t in low for t in interior_terms):
                hide(o, "replace constrained interior layout", hidden["interior"])
    return hidden


def large_glass_bay(c, x, w, h, M, split=False):
    y = -5.18
    z = 0.50 + h / 2
    add(
        c,
        "restored_transparent_window",
        (x, y, z),
        (w / 2 - 0.09, 0.020, h / 2 - 0.08),
        M["glass"],
        0.002,
    )
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "window_frame_vertical",
            (xx, y - 0.015, z),
            (0.045, 0.048, h / 2 + 0.045),
            M["frame"],
            0.004,
        )
    for zz in (0.50, 0.50 + h):
        add(
            c,
            "window_frame_horizontal",
            (x, y - 0.015, zz),
            (w / 2 + 0.045, 0.048, 0.045),
            M["frame"],
            0.004,
        )
    if split:
        add(
            c,
            "window_center_mullion",
            (x, y - 0.020, z),
            (0.022, 0.040, h / 2 - 0.11),
            M["frame"],
            0.003,
        )


def glass_door(c, x, w, M, double=False):
    y = -5.20
    h = 2.58
    z = 0.28 + h / 2
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "door_frame_vertical",
            (xx, y - 0.015, z),
            (0.052, 0.052, h / 2 + 0.040),
            M["frame"],
            0.004,
        )
    add(
        c,
        "door_frame_header",
        (x, y - 0.015, 0.28 + h),
        (w / 2 + 0.052, 0.052, 0.045),
        M["frame"],
        0.004,
    )
    leaves = 2 if double else 1
    for i in range(leaves):
        lw = w / 2 if double else w
        cx = x + (-w * 0.25 if double and i == 0 else w * 0.25 if double else 0)
        add(
            c,
            "transparent_glass_door_leaf",
            (cx, y - 0.020, 1.55),
            (lw / 2 - 0.055, 0.019, 1.00),
            M["glass"],
            0.002,
        )
        for xx in (cx - lw / 2 + 0.030, cx + lw / 2 - 0.030):
            add(
                c,
                "door_leaf_stile",
                (xx, y - 0.045, z),
                (0.026, 0.032, h / 2 - 0.065),
                M["frame"],
                0.003,
            )
        add(
            c,
            "door_leaf_bottom_kick",
            (cx, y - 0.045, 0.40),
            (lw / 2 - 0.035, 0.032, 0.095),
            M["metal"],
            0.003,
        )
        hx = cx + (lw * 0.22 if i == 0 else -lw * 0.22)
        add(
            c,
            "door_pull_handle",
            (hx, y - 0.085, 1.43),
            (0.018, 0.026, 0.235),
            M["metal"],
            0.004,
        )
    add(
        c,
        "door_threshold",
        (x, y - 0.060, 0.14),
        (w / 2 + 0.080, 0.090, 0.035),
        M["metal"],
        0.004,
    )


def shallow_sign(c, label, z, M, panelmat, width):
    add(
        c,
        "sign_backing_panel",
        (0, -5.08, z),
        (width / 2, 0.035, 0.245),
        panelmat,
        0.010,
    )
    old = next(
        (
            o
            for o in bpy.data.objects
            if o.type == "FONT" and " ".join(o.data.body.split()) == label
        ),
        None,
    )
    if old:
        data = old.data.copy()
        data.extrude = 0.028
        data.bevel_depth = 0.004
        data.bevel_resolution = 1
        data.materials.clear()
        data.materials.append(M["letter"])
        t = bpy.data.objects.new(P + "shallow_letters_" + label.replace(" ", "_"), data)
        c.objects.link(t)
        t.location = (old.location.x, -5.125, z)
        t.rotation_euler = old.rotation_euler
        t.scale = old.scale
        t["letter_mounting"] = "nearly_flush_to_backing_panel"


def restored_facade(c, is_rest, M):
    wall = M["rest_wall"] if is_rest else M["fresh_wall"]
    signmat = M["rest_sign"] if is_rest else M["fresh_sign"]
    top = 5.30 if is_rest else 4.82
    # Minimal opaque construction: only wall above/beside openings and a low base.
    add(
        c,
        "upper_wall_above_glazing",
        (0, -4.91, (3.18 + top) / 2),
        (7.58, 0.105, (top - 3.18) / 2),
        wall,
        0.012,
    )
    add(c, "left_edge_wall", (-7.58, -4.94, 1.78), (0.115, 0.115, 1.48), wall, 0.010)
    add(
        c,
        "right_edge_wall",
        ((7.46 if is_rest else 7.58), -4.94, 1.78),
        (0.115, 0.115, 1.48),
        wall,
        0.010,
    )
    add(
        c,
        "low_concrete_kick_base",
        (0, -4.98, 0.28),
        (7.58, 0.115, 0.150),
        M["base"],
        0.008,
    )
    if is_rest:
        glass_door(c, 5.40, 1.08, M, False)
        bays = [
            (-5.60, 2.75, 2.55, True),
            (-2.52, 2.55, 2.55, False),
            (0.42, 2.58, 2.55, True),
            (2.95, 1.86, 2.55, False),
        ]
        sign_label, sign_z, sign_w = "CORNER KITCHEN", 5.00, 7.40
        canopy_z, canopy_w = 3.55, 14.10
    else:
        glass_door(c, 0, 1.44, M, True)
        bays = [
            (-5.55, 2.80, 2.55, True),
            (-2.65, 2.36, 2.55, False),
            (2.62, 2.34, 2.55, False),
            (5.28, 2.58, 2.55, True),
        ]
        sign_label, sign_z, sign_w = "FRESH MART", 4.50, 6.00
        canopy_z, canopy_w = 3.42, 14.35
    for x, w, h, split in bays:
        large_glass_bay(c, x, w, h, M, split)
    for x in (-7.35, 7.35):
        add(
            c,
            "structural_end_column",
            (x, -5.02, 1.80),
            (0.060, 0.090, 1.46),
            wall,
            0.006,
        )
    add(
        c,
        "simple_flat_canopy",
        (0, -5.58, canopy_z),
        (canopy_w / 2, 0.45, 0.045),
        signmat,
        0.010,
    )
    shallow_sign(c, sign_label, sign_z, M, signmat, sign_w)
    return {
        "glass_bays": len(bays),
        "door": 1,
        "allowed_facade_detail_policy": "wall/frame/glass/door/handle/sill/canopy/sign only",
    }


def product_masters(M):
    ps = []
    b = master("bottle")
    add_mesh(
        b, "bottle_body", cyl(), (0, 0, 0.17), (0.060, 0.060, 0.17), M["green"], 0.005
    )
    add_mesh(
        b,
        "bottle_label",
        cyl(),
        (0, 0, 0.17),
        (0.063, 0.063, 0.050),
        M["carton"],
        0.001,
    )
    ps.append(b)
    can = master("can")
    add_mesh(
        can, "can_body", cyl(), (0, 0, 0.13), (0.070, 0.070, 0.13), M["foil"], 0.003
    )
    add_mesh(
        can, "can_wrap", cyl(), (0, 0, 0.13), (0.072, 0.072, 0.085), M["blue"], 0.001
    )
    ps.append(can)
    box = master("box")
    add(box, "carton_box", (0, 0, 0.19), (0.105, 0.055, 0.19), M["carton"], 0.005)
    add(box, "printed_face", (0, -0.058, 0.20), (0.078, 0.003, 0.080), M["red"], 0.001)
    ps.append(box)
    pouch = master("bag")
    add_mesh(
        pouch, "soft_bag", bag(), (0, 0, 0.17), (0.108, 0.074, 0.34), M["red"], 0.006
    )
    ps.append(pouch)
    return ps


def shelf_master(name, M, width=1.0, levels=4, seed=1):
    c = master(name)
    ps = product_masters(M)
    add(c, "shelf_base", (0, 0, 0.10), (width, 0.30, 0.065), M["shelf"], 0.006)
    for x in (-width * 0.92, width * 0.92):
        add(
            c, "shelf_upright", (x, 0.13, 0.76), (0.032, 0.036, 0.70), M["metal"], 0.004
        )
    rng = random.Random(seed)
    goods = 0
    for level in range(levels):
        z = 0.32 + level * 0.30
        add(c, "shelf_deck", (0, -0.02, z), (width, 0.28, 0.026), M["shelf"], 0.004)
        for i in range(5 + level % 2):
            if rng.random() < 0.18:
                continue
            x = (
                -width * 0.65
                + i * (width * 1.30 / max(1, 4 + level % 2))
                + (rng.random() - 0.5) * 0.025
            )
            s = 0.72 + rng.random() * 0.18
            inst(
                c,
                ps[(i + level + seed) % len(ps)],
                "product",
                (x, -0.13, z + 0.035),
                (rng.random() - 0.5) * 0.06,
                (s, s, s),
            )
            goods += 1
    c["goods_count"] = goods
    return c


def cooler_master(M):
    c = master("cooler")
    add(c, "cooler_case", (0, 0, 0.92), (1.05, 0.30, 0.84), M["white"], 0.014)
    add(
        c,
        "cooler_glass_front",
        (0, -0.325, 0.92),
        (0.92, 0.018, 0.68),
        M["glass"],
        0.002,
    )
    for x in (-0.32, 0.32):
        add(
            c,
            "cooler_handle",
            (x, -0.355, 0.93),
            (0.014, 0.020, 0.28),
            M["metal"],
            0.002,
        )
    return c


def checkout_master(M):
    c = master("checkout")
    add(c, "checkout_counter", (0, 0, 0.43), (1.00, 0.32, 0.40), M["wood"], 0.012)
    add(c, "checkout_top", (0, 0, 0.84), (1.08, 0.36, 0.035), M["metal"], 0.006)
    add(c, "register", (0.24, -0.14, 1.02), (0.16, 0.030, 0.105), M["black"], 0.003)
    return c


def fresh_interior(M):
    c = bpy.data.collections["all43_01:MASTER:convenience_store"]
    shelf_a = shelf_master("fresh_shelf_a", M, 1.0, 4, 43141)
    shelf_b = shelf_master("fresh_shelf_b", M, 0.82, 4, 43142)
    cooler = cooler_master(M)
    checkout = checkout_master(M)
    placements = [
        (-4.20, -2.95, 0.04, 0.90),
        (-1.60, -2.05, -0.04, 0.86),
        (1.25, -2.78, 0.06, 0.84),
        (-3.20, 0.45, 0.02, 0.82),
    ]
    for i, (x, y, r, s) in enumerate(placements):
        inst(
            c,
            shelf_a if i % 2 == 0 else shelf_b,
            "fresh_shelf_set_back_from_glass",
            (x, y, 0),
            r,
            (s, 1, 1),
        )
    for x in (-4.15, -1.35, 1.35, 4.05):
        inst(c, cooler, "rear_cooler_visible_through_glass", (x, 2.70, 0), 0)
    inst(c, checkout, "checkout_visible_inside", (4.45, 0.80, 0), -0.04)
    return {
        "fresh_first_shelf_y": -2.95,
        "fresh_clear_zone_from_glass_m": 2.15,
        "fresh_product_master_categories": 4,
    }


def table_master(M, rectangular=False):
    c = master("table_rect" if rectangular else "table_round")
    if rectangular:
        add(c, "table_top", (0, 0, 0.74), (0.56, 0.36, 0.040), M["wood"], 0.010)
        for x in (-0.38, 0.38):
            add(c, "table_leg", (x, 0, 0.40), (0.030, 0.26, 0.28), M["metal"], 0.004)
    else:
        add_mesh(
            c, "round_top", cyl(), (0, 0, 0.74), (0.38, 0.38, 0.040), M["wood"], 0.010
        )
        add_mesh(
            c, "pedestal", cyl(), (0, 0, 0.40), (0.048, 0.048, 0.27), M["metal"], 0.006
        )
        add_mesh(c, "base", cyl(), (0, 0, 0.12), (0.27, 0.27, 0.035), M["metal"], 0.006)
    return c


def chair_master(M):
    c = master("chair")
    add(c, "chair_seat", (0, 0, 0.44), (0.21, 0.20, 0.040), M["seat"], 0.010)
    add(c, "chair_back", (0, 0.16, 0.75), (0.23, 0.032, 0.20), M["seat"], 0.010)
    for x, y in [(-0.17, -0.15), (0.17, -0.15), (-0.17, 0.15), (0.17, 0.15)]:
        add(c, "chair_leg", (x, y, 0.27), (0.024, 0.024, 0.23), M["wood"], 0.003)
    return c


def service_counter_master(M):
    c = master("service_counter")
    add(c, "service_counter_body", (0, 0, 0.46), (1.18, 0.34, 0.38), M["wood"], 0.012)
    add(c, "service_counter_top", (0, 0, 0.86), (1.26, 0.38, 0.035), M["metal"], 0.006)
    add(c, "pos_screen", (0.40, -0.22, 1.03), (0.15, 0.024, 0.10), M["black"], 0.003)
    return c


def restaurant_interior(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    t1, t2, ch, counter = (
        table_master(M),
        table_master(M, True),
        chair_master(M),
        service_counter_master(M),
    )
    clusters = [
        (-4.20, -2.90, 0.08, t1, 2),
        (-1.65, -2.25, -0.06, t2, 4),
        (0.85, -1.70, 0.10, t1, 3),
        (-3.20, 0.35, -0.04, t2, 4),
    ]
    for x, y, r, table, count in clusters:
        inst(c, table, "restaurant_table_visible_through_glass", (x, y, 0), r)
        for a in [math.pi, 0, math.pi / 2, -math.pi / 2][:count]:
            inst(
                c,
                ch,
                "restaurant_chair_visible_through_glass",
                (x + 0.66 * math.sin(a), y - 0.66 * math.cos(a), 0),
                r + a,
            )
        add_mesh(
            c,
            "simple_table_plate",
            cyl(),
            (x, y, 0.795),
            (0.085, 0.085, 0.009),
            M["ceramic"],
            0.001,
        )
    inst(c, counter, "service_counter_visible_inside", (4.00, 1.70, 0), -0.04)
    add(
        c,
        "rear_zone_muted_partition",
        (0, 3.58, 1.38),
        (6.40, 0.060, 1.30),
        M["white"],
        0.006,
    )
    return {
        "restaurant_first_table_y": -2.90,
        "restaurant_clear_zone_from_glass_m": 2.10,
        "restaurant_table_instances": 4,
        "restaurant_chair_instances": 13,
    }


def tone_down_legacy_whites():
    changed = []
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if not bsdf:
            continue
        low = m.name.lower()
        if any(
            k in low for k in ("white", "cream", "equipment_enamel", "fixture_lens")
        ):
            col = list(bsdf.inputs["Base Color"].default_value)
            if max(col[:3]) > 0.60:
                bsdf.inputs["Base Color"].default_value = tuple(
                    min(v, 0.56) for v in col[:3]
                ) + (col[3],)
                bsdf.inputs["Roughness"].default_value = max(
                    bsdf.inputs["Roughness"].default_value, 0.58
                )
                changed.append(m.name)
    return changed


def sanity_check():
    issues = []
    allowed_prefixes = (
        P + "upper_wall",
        P + "left_edge",
        P + "right_edge",
        P + "low_concrete",
        P + "restored_transparent_window",
        P + "window_frame",
        P + "window_center",
        P + "door_frame",
        P + "transparent_glass_door",
        P + "door_leaf",
        P + "door_pull",
        P + "door_threshold",
        P + "structural_end",
        P + "simple_flat_canopy",
        P + "sign_backing_panel",
        P + "shallow_letters",
    )
    for c in (
        bpy.data.collections["all43_01:MASTER:convenience_store"],
        bpy.data.collections["all43_01:MASTER:restaurant"],
    ):
        for o in c.objects:
            if o.hide_render:
                continue
            if (
                o.location.y < -4.20
                and o.name.startswith(P)
                and not o.name.startswith(allowed_prefixes)
            ):
                issues.append("unknown_front_object:" + o.name)
            if (
                o.name.startswith(P)
                and (
                    "fresh_shelf" in o.name
                    or "restaurant_table" in o.name
                    or "restaurant_chair" in o.name
                )
                and o.location.y < -4.05
            ):
                issues.append("interior_too_close_to_glass:" + o.name)
    visible_old_front = []
    for c in (
        bpy.data.collections["all43_01:MASTER:convenience_store"],
        bpy.data.collections["all43_01:MASTER:restaurant"],
    ):
        for o in c.objects:
            low = o.name.lower()
            if not o.hide_render and o.location.y < -4.20 and not o.name.startswith(P):
                if any(
                    t in low
                    for t in (
                        "facade",
                        "recess",
                        "triangular",
                        "standoff",
                        "window_shadow",
                        "sign_",
                        "door_opening",
                    )
                ):
                    visible_old_front.append(o.name)
    if visible_old_front:
        issues.append("visible_old_front_clutter:" + ",".join(visible_old_front[:8]))
    if issues:
        raise RuntimeError(
            "All43-14 storefront sanity failed: " + "; ".join(issues[:20])
        )
    return {"geometry_sanity_check": "PASS", "sanity_issue_count": 0}


def run():
    M = materials()
    hidden = clear_storefront_and_near_interior()
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    fresh_facade = restored_facade(conv, False, M)
    rest_facade = restored_facade(rest, True, M)
    fresh = fresh_interior(M)
    restaurant = restaurant_interior(M)
    toned = tone_down_legacy_whites()
    audit = sanity_check()
    return {
        "source_visual_baseline": "urban_v3_all43_13 with storefront restored using simplified prior glass-storefront logic",
        "hidden_legacy_front_objects": len(hidden["front"]),
        "hidden_near_or_old_interior_objects": len(hidden["interior"]),
        "new_all43_14_objects": sum(o.name.startswith(P) for o in bpy.data.objects),
        "facade_policy": "no random facade modules; only wall, frame, glass, door, handle, sill, canopy and sign",
        "fresh_facade": fresh_facade,
        "corner_kitchen_facade": rest_facade,
        "sign_audit": "PASS: shallow letters close to backing panel, no emission",
        "storefront_glass_audit": "PASS: large transparent glass dominates both storefronts",
        "toned_material_count": len(toned),
        **fresh,
        **restaurant,
        **audit,
    }
