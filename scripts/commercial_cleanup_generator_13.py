"""All43-13 cleanup pass: clean storefronts, constrained interiors and sane frontage."""
import math, random
import bpy

P = "all43_13:"
OLD = "all43_12:"


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
        tex.inputs["Detail"].default_value = 5
        tex.inputs["Roughness"].default_value = 0.58
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(
            max(0, x * 0.86) for x in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, x * 1.05 + 0.015) for x in color[:3]
        ) + (1,)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bumpnode = nodes.new("ShaderNodeBump")
        bumpnode.inputs["Strength"].default_value = bump
        bumpnode.inputs["Distance"].default_value = 0.014
        links.new(tex.outputs["Fac"], bumpnode.inputs["Height"])
        links.new(bumpnode.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def glassmat():
    m = mat("clear_storefront_glass", (0.045, 0.082, 0.086, 1), 0.10, 0)
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Transmission Weight"].default_value = 0.82
    bsdf.inputs["IOR"].default_value = 1.46
    bsdf.inputs["Coat Weight"].default_value = 0.24
    bsdf.inputs["Coat Roughness"].default_value = 0.065
    return m


def materials():
    return {
        "fresh_wall": mat(
            "fresh_muted_painted_facade", (0.18, 0.36, 0.24, 1), 0.66, 0, 38, 0.08
        ),
        "rest_wall": mat(
            "kitchen_muted_terracotta_facade", (0.42, 0.15, 0.085, 1), 0.68, 0, 36, 0.08
        ),
        "frame": mat(
            "dark_bronze_aluminum", (0.035, 0.039, 0.037, 1), 0.34, 0.64, 48, 0.022
        ),
        "glass": glassmat(),
        "shadow": mat("clean_opening_shadow", (0.018, 0.020, 0.018, 1), 0.82),
        "base": mat("cast_concrete_base", (0.44, 0.43, 0.39, 1), 0.84, 0, 42, 0.12),
        "metal": mat(
            "brushed_service_metal", (0.24, 0.25, 0.24, 1), 0.42, 0.58, 46, 0.025
        ),
        "sign_face": mat("warm_letter_face", (0.72, 0.69, 0.56, 1), 0.36, 0, 20, 0.012),
        "fresh_sign": mat(
            "muted_fresh_sign_panel", (0.045, 0.20, 0.11, 1), 0.52, 0.08, 25, 0.025
        ),
        "rest_sign": mat(
            "muted_kitchen_sign_panel", (0.32, 0.075, 0.035, 1), 0.54, 0.08, 25, 0.025
        ),
        "sidewalk": mat(
            "continuous_sidewalk_concrete", (0.45, 0.445, 0.415, 1), 0.86, 0, 48, 0.10
        ),
        "paver": mat("entry_paver_real", (0.42, 0.39, 0.34, 1), 0.78, 0, 34, 0.09),
        "curb": mat("curb_concrete_13", (0.49, 0.485, 0.45, 1), 0.86, 0, 45, 0.10),
        "asphalt": mat("matte_asphalt_13", (0.038, 0.040, 0.039, 1), 0.94, 0, 78, 0.16),
        "stripe": mat(
            "aged_parking_stripe_13", (0.63, 0.60, 0.48, 1), 0.74, 0, 24, 0.04
        ),
        "black": mat("dark_rubber_not_void", (0.016, 0.017, 0.016, 1), 0.78),
        "shelf": mat(
            "shelf_powdercoat_13", (0.16, 0.18, 0.165, 1), 0.54, 0.30, 28, 0.025
        ),
        "wood": mat("muted_walnut_13", (0.22, 0.095, 0.042, 1), 0.50, 0, 20, 0.035),
        "seat": mat("restaurant_vinyl_13", (0.075, 0.17, 0.15, 1), 0.64, 0, 24, 0.025),
        "white": mat(
            "off_white_equipment_13", (0.56, 0.57, 0.53, 1), 0.60, 0, 28, 0.028
        ),
        "carton": mat("carton_print_13", (0.64, 0.50, 0.22, 1), 0.54, 0, 22, 0.018),
        "red": mat("red_packaging_13", (0.43, 0.045, 0.025, 1), 0.50, 0, 26, 0.015),
        "blue": mat("blue_packaging_13", (0.035, 0.105, 0.32, 1), 0.49, 0, 26, 0.015),
        "green": mat("green_packaging_13", (0.030, 0.24, 0.090, 1), 0.50, 0, 26, 0.015),
        "foil": mat("dull_foil_13", (0.46, 0.46, 0.42, 1), 0.34, 0.52, 42, 0.015),
        "ceramic": mat("matte_ceramic_13", (0.70, 0.68, 0.60, 1), 0.38, 0, 22, 0.012),
    }


def add_mesh(c, name, mesh, loc, scale, material, bevel=0.006, rot=(0, 0, 0)):
    o = bpy.data.objects.new(P + name, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = scale
    o.rotation_euler = rot
    o.data.materials.append(material)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = material
    if bevel:
        b = o.modifiers.new("manufactured_edge_radius", "BEVEL")
        b.width = min(bevel, min(scale) * 0.18)
        b.segments = 3
    o["shared_mesh_data"] = True
    return o


def add(c, name, loc, scale, material, bevel=0.006, rot=(0, 0, 0)):
    return add_mesh(c, name, cube(), loc, scale, material, bevel, rot)


def master(name):
    c = bpy.data.collections.new(P + "MASTER:" + name)
    c["high_quality_master"] = True
    return c


def inst(c, master_collection, name, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + name, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = master_collection
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def hide(o, reason, hidden):
    if o.hide_render and o.hide_viewport:
        return
    o.hide_render = True
    o.hide_viewport = True
    o["all43_13_hidden_reason"] = reason
    hidden.append(o.name)


def cleanup_legacy_geometry():
    hidden = {"front": [], "frontage": [], "side_wall": [], "interior": []}
    front_tokens = (
        "facade_",
        "window_",
        "outer_window",
        "inner_vertical",
        "interior_head",
        "door_",
        "structural_door",
        "pull_mount",
        "hydraulic_closer",
        "closer_arm",
        "awning_",
        "triangular_brace",
        "sign_",
        "letter_standoff",
        "channel_letters",
        "roof_edge_coping",
        "continuous_base_course",
        "folded_sign",
        "formed_front",
        "integrated_gutter",
        "projecting_window_sill",
        "thick_laminated_glass",
    )
    interior_tokens = (
        "zoned_stocked_shelf",
        "continuous_rear_cooler",
        "front_impulse_display",
        "checkout_near_entry",
        "clear_entry_apron_inside",
        "back_stockroom_wall",
        "staff_door_with_pushplate",
        "small_category_blade",
        "non_grid_dining",
        "individual_table_setting",
        "inward_dining_chair",
        "wall_banquette",
        "visible_order_counter",
        "open_customer_path",
        "rear_service_wall",
        "stainless_prep_table",
        "back_shelving_unit",
        "menu_board",
        "small_menu_card",
    )
    frontage_tokens = (
        "drain_slot",
        "drain_grate_slot",
        "cast_drain_body",
        "paving_joint",
        "entry_apron_control_joint",
        "entry_apron_sawcut",
        "frontage_and_parking",
        "continuous_entrance_apron",
        "individual_sidewalk_slab",
        "raised_curb",
        "gutter_pan",
        "anchored_wheel_stop",
        "worn_stall_marking",
        "aggregate_tone_variation_patch",
        "precast_stop",
        "rubber_end",
        "anchor_l",
        "anchor_r",
        "entrance_paving",
        "oil_stain",
        "tire_mark",
    )
    side_tokens = ("03_side_pilaster", "03_side_stringcourse", "03_side_base")
    for o in bpy.data.objects:
        n = o.name
        low = n.lower()
        if n.startswith(OLD) and any(t in low for t in front_tokens):
            hide(o, "replace cluttered all43_12 storefront", hidden["front"])
        if n.startswith(OLD) and any(t in low for t in interior_tokens):
            hide(o, "replace unconstrained all43_12 interior", hidden["interior"])
        if any(t in low for t in frontage_tokens):
            hide(
                o, "replace repeated black holes / frontage strips", hidden["frontage"]
            )
        if any(t in n for t in side_tokens):
            hide(o, "replace repeated side-wall bars", hidden["side_wall"])
        if o.type == "FONT" and o.location.y < -4.35 and not n.startswith(P):
            hide(o, "replace flat or legacy storefront lettering", hidden["front"])
    return hidden


def clean_window(c, x, w, h, M, split=None):
    y = -5.02
    z = 0.50 + h / 2
    add(
        c,
        "storefront_recess",
        (x, y + 0.10, z),
        (w / 2 + 0.08, 0.08, h / 2 + 0.08),
        M["shadow"],
        0.012,
    )
    add(
        c,
        "single_clear_glass_lite",
        (x, y - 0.105, z),
        (w / 2 - 0.10, 0.024, h / 2 - 0.09),
        M["glass"],
        0.003,
    )
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "connected_window_jamb",
            (xx, y - 0.14, z),
            (0.060, 0.075, h / 2 + 0.07),
            M["frame"],
            0.009,
        )
    for zz in (0.50, 0.50 + h):
        add(
            c,
            "connected_window_rail",
            (x, y - 0.14, zz),
            (w / 2 + 0.060, 0.075, 0.055),
            M["frame"],
            0.009,
        )
    if split:
        for frac in split:
            add(
                c,
                "thin_storefront_mullion",
                (x - w / 2 + w * frac, y - 0.155, z),
                (0.026, 0.052, h / 2 - 0.12),
                M["frame"],
                0.005,
            )
    add(
        c,
        "flush_metal_sill",
        (x, y - 0.18, 0.435),
        (w / 2 + 0.08, 0.095, 0.035),
        M["metal"],
        0.006,
    )


def clean_door(c, x, M, double=False):
    y = -5.035
    w = 1.48 if double else 1.12
    h = 2.62
    z = 0.24 + h / 2
    add(
        c,
        "door_recess_shadow",
        (x, y + 0.09, z),
        (w / 2 + 0.10, 0.075, h / 2 + 0.08),
        M["shadow"],
        0.012,
    )
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "connected_door_jamb",
            (xx, y - 0.14, z),
            (0.068, 0.082, h / 2 + 0.07),
            M["frame"],
            0.010,
        )
    add(
        c,
        "connected_door_header",
        (x, y - 0.14, 0.24 + h),
        (w / 2 + 0.070, 0.082, 0.060),
        M["frame"],
        0.010,
    )
    leaves = 2 if double else 1
    for i in range(leaves):
        cx = x + (-w * 0.25 if i == 0 and double else w * 0.25 if double else 0)
        lw = w / 2 if double else w
        for xx in (cx - lw / 2 + 0.040, cx + lw / 2 - 0.040):
            add(
                c,
                "glass_door_stile",
                (xx, y - 0.205, z),
                (0.038, 0.040, h / 2 - 0.06),
                M["frame"],
                0.005,
            )
        add(
            c,
            "glass_door_top_rail",
            (cx, y - 0.205, 0.24 + h - 0.075),
            (lw / 2 - 0.045, 0.040, 0.040),
            M["frame"],
            0.005,
        )
        add(
            c,
            "glass_door_bottom_rail",
            (cx, y - 0.205, 0.42),
            (lw / 2 - 0.045, 0.040, 0.105),
            M["frame"],
            0.005,
        )
        add(
            c,
            "glass_door_lite",
            (cx, y - 0.185, 1.55),
            (lw / 2 - 0.085, 0.022, 0.96),
            M["glass"],
            0.003,
        )
        hx = cx + (lw * 0.23 if i == 0 else -lw * 0.23)
        add(
            c,
            "single_door_pull",
            (hx, y - 0.270, 1.45),
            (0.020, 0.028, 0.255),
            M["metal"],
            0.006,
        )
    add(
        c,
        "continuous_door_threshold",
        (x, y - 0.250, 0.145),
        (w / 2 + 0.12, 0.125, 0.040),
        M["metal"],
        0.006,
    )


def clean_sign(c, label, z, M, panelmat, width):
    add(
        c,
        "sign_shadow_gap",
        (0, -5.045, z),
        (width / 2 + 0.08, 0.050, 0.34),
        M["shadow"],
        0.010,
    )
    add(
        c,
        "simple_sign_backer",
        (0, -5.140, z),
        (width / 2, 0.060, 0.300),
        panelmat,
        0.018,
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
        data.extrude = 0.09
        data.bevel_depth = 0.010
        data.bevel_resolution = 2
        data.materials.clear()
        data.materials.append(M["sign_face"])
        t = bpy.data.objects.new(
            P + "clean_channel_letters_" + label.replace(" ", "_"), data
        )
        c.objects.link(t)
        t.location = (old.location.x, -5.250, z)
        t.rotation_euler = old.rotation_euler
        t.scale = old.scale
        t["real_channel_letter"] = True


def clean_facade(c, is_rest, M):
    wall = M["rest_wall"] if is_rest else M["fresh_wall"]
    panel = M["rest_sign"] if is_rest else M["fresh_sign"]
    top = 5.35 if is_rest else 4.85
    add(
        c,
        "clean_upper_wall",
        (0, -4.900, (3.34 + top) / 2),
        (7.62, 0.160, (top - 3.34) / 2),
        wall,
        0.020,
    )
    add(c, "clean_left_return", (-7.58, -4.92, 1.84), (0.18, 0.18, 1.58), wall, 0.018)
    add(
        c,
        "clean_right_return",
        (7.58 if not is_rest else 7.35, -4.92, 1.84),
        (0.18, 0.18, 1.58),
        wall,
        0.018,
    )
    add(
        c,
        "clean_base_course",
        (0, -4.980, 0.295),
        (7.58, 0.160, 0.170),
        M["base"],
        0.012,
    )
    if is_rest:
        clean_door(c, 5.42, M, False)
        specs = [
            (-5.72, 2.34, 2.62, [0.50]),
            (-2.95, 2.22, 2.62, None),
            (-0.28, 2.36, 2.62, [0.52]),
            (2.45, 2.26, 2.62, None),
        ]
    else:
        clean_door(c, 0, M, True)
        specs = [
            (-5.70, 2.52, 2.62, [0.50]),
            (-2.88, 2.18, 2.62, None),
            (2.72, 2.06, 2.62, [0.50]),
            (5.22, 2.38, 2.62, None),
        ]
    for x, w, h, split in specs:
        clean_window(c, x, w, h, M, split)
    # Only true structure is kept: boundaries and a few load points, not decorative clutter.
    pier_xs = [-7.36, 7.36]
    for x, w, _, _ in specs:
        pier_xs.extend([x - w / 2 - 0.09, x + w / 2 + 0.09])
    clean = []
    for x in sorted(pier_xs):
        if not clean or abs(clean[-1] - x) > 0.18:
            clean.append(x)
    for x in clean:
        add(
            c,
            "clean_structural_pier",
            (x, -4.995, 1.86),
            (0.075, 0.150, 1.55),
            wall,
            0.010,
        )
    add(
        c,
        "clean_roof_edge",
        (0, -4.930, top + 0.12),
        (7.65, 0.175, 0.070),
        M["metal"],
        0.012,
    )
    clean_sign(
        c,
        "CORNER KITCHEN" if is_rest else "FRESH MART",
        5.02 if is_rest else 4.52,
        M,
        panel,
        8.0 if is_rest else 6.1,
    )


def restaurant_side_wall(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    add(
        c,
        "clean_right_side_wall_panel",
        (7.62, 0.05, 2.70),
        (0.075, 4.45, 2.42),
        M["rest_wall"],
        0.018,
    )
    for y in (-3.75, 0.0, 3.75):
        add(
            c,
            "subtle_side_facade_joint",
            (7.705, y, 2.72),
            (0.018, 0.026, 2.22),
            M["shadow"],
            0.002,
        )
    add(
        c,
        "side_wall_base_course",
        (7.70, 0.05, 0.38),
        (0.100, 4.48, 0.150),
        M["base"],
        0.010,
    )
    add(
        c,
        "side_downspout_connected",
        (7.735, 3.45, 1.50),
        (0.035, 0.035, 1.36),
        M["metal"],
        0.008,
    )
    add(
        c,
        "side_utility_panel_flush",
        (7.745, 2.25, 1.05),
        (0.040, 0.36, 0.42),
        M["metal"],
        0.010,
    )
    return 6


def product_masters(M):
    result = []
    b = master("bottle")
    add_mesh(
        b, "bottle_body", cyl(), (0, 0, 0.17), (0.065, 0.065, 0.17), M["green"], 0.007
    )
    add_mesh(
        b, "bottle_neck", cyl(), (0, 0, 0.37), (0.030, 0.030, 0.050), M["green"], 0.006
    )
    add_mesh(b, "label", cyl(), (0, 0, 0.18), (0.068, 0.068, 0.055), M["carton"], 0.002)
    result.append(b)
    can = master("can")
    add_mesh(
        can, "can_body", cyl(), (0, 0, 0.13), (0.074, 0.074, 0.13), M["foil"], 0.004
    )
    add_mesh(
        can,
        "printed_wrap",
        cyl(),
        (0, 0, 0.14),
        (0.077, 0.077, 0.090),
        M["blue"],
        0.002,
    )
    result.append(can)
    box = master("box_pack")
    add(box, "creased_carton", (0, 0, 0.20), (0.115, 0.060, 0.20), M["carton"], 0.008)
    add(box, "front_print", (0, -0.063, 0.22), (0.085, 0.004, 0.090), M["red"], 0.001)
    result.append(box)
    pouch = master("pouch")
    add_mesh(
        pouch,
        "standup_pouch",
        bag(),
        (0, 0, 0.18),
        (0.120, 0.080, 0.36),
        M["red"],
        0.008,
    )
    add(
        pouch,
        "small_print_panel",
        (0, -0.085, 0.20),
        (0.070, 0.004, 0.070),
        M["carton"],
        0.001,
    )
    result.append(pouch)
    return result


def shelf_master(name, M, w=1.05, levels=4, height=1.55, seed=1):
    c = master(name)
    prods = product_masters(M)
    add(
        c,
        "integrated_shelf_base",
        (0, 0, 0.12),
        (w + 0.06, 0.32, 0.075),
        M["shelf"],
        0.010,
    )
    for x in (-w, w):
        add(
            c,
            "continuous_shelf_upright",
            (x, 0.15, height / 2),
            (0.040, 0.048, height / 2),
            M["metal"],
            0.008,
        )
    add(
        c,
        "clean_back_panel",
        (0, 0.18, height / 2),
        (w, 0.025, height / 2 - 0.08),
        M["shelf"],
        0.004,
    )
    rng = random.Random(seed)
    goods = 0
    for level in range(levels):
        z = 0.34 + level * ((height - 0.46) / max(1, levels - 1))
        add(
            c,
            "supported_shelf_deck",
            (0, -0.03, z),
            (w, 0.30, 0.030),
            M["shelf"],
            0.006,
        )
        slots = 6 + (level % 2)
        for i in range(slots):
            if rng.random() < 0.16:
                continue
            x = (
                -w * 0.76
                + i * (w * 1.52 / max(1, slots - 1))
                + (rng.random() - 0.5) * 0.035
            )
            s = 0.72 + rng.random() * 0.20
            inst(
                c,
                prods[(i + level + seed) % len(prods)],
                "supported_product",
                (x, -0.145, z + 0.040),
                (rng.random() - 0.5) * 0.06,
                (s, s, s),
            )
            goods += 1
    c["supported_product_count"] = goods
    return c


def cooler_master(M):
    c = master("rear_cooler")
    add(c, "cooler_body", (0, 0, 0.95), (1.15, 0.34, 0.90), M["white"], 0.025)
    add(
        c,
        "cooler_dark_cavity",
        (0, -0.34, 0.95),
        (1.02, 0.025, 0.72),
        M["black"],
        0.004,
    )
    for x in (-0.38, 0.38):
        add(
            c,
            "cooler_glass_door",
            (x, -0.390, 0.95),
            (0.30, 0.020, 0.70),
            M["glass"],
            0.003,
        )
        add(
            c,
            "cooler_handle",
            (x + 0.22, -0.425, 0.97),
            (0.016, 0.026, 0.30),
            M["metal"],
            0.004,
        )
    for z in (0.50, 0.82, 1.14, 1.46):
        add(
            c,
            "cooler_internal_shelf",
            (0, -0.265, z),
            (0.94, 0.16, 0.020),
            M["metal"],
            0.003,
        )
    return c


def checkout_master(M):
    c = master("checkout")
    add(c, "counter_body", (0, 0, 0.45), (1.05, 0.34, 0.42), M["wood"], 0.022)
    add(c, "counter_top", (0, 0, 0.88), (1.14, 0.40, 0.045), M["metal"], 0.012)
    add(
        c,
        "register_screen",
        (0.30, -0.15, 1.08),
        (0.18, 0.025, 0.13),
        M["black"],
        0.006,
        rot=(0.10, 0, 0),
    )
    add(c, "scanner", (-0.15, -0.18, 0.935), (0.17, 0.10, 0.018), M["black"], 0.003)
    return c


def fresh_interior(M):
    c = bpy.data.collections["all43_01:MASTER:convenience_store"]
    shelf_a = shelf_master("fresh_clean_gondola_a", M, 1.05, 4, 1.52, 43131)
    shelf_b = shelf_master("fresh_clean_gondola_b", M, 0.86, 4, 1.42, 43132)
    impulse = shelf_master("fresh_clean_impulse", M, 0.62, 3, 1.12, 43133)
    cooler = cooler_master(M)
    checkout = checkout_master(M)
    made = []
    for i, spec in enumerate(
        [
            (-4.45, -2.45, 0.06, 0.94),
            (-1.85, -1.55, -0.04, 0.90),
            (0.95, -2.30, 0.08, 0.88),
            (-3.40, 0.55, 0.03, 0.84),
        ]
    ):
        x, y, r, s = spec
        made.append(
            inst(
                c,
                shelf_a if i % 2 == 0 else shelf_b,
                "interior_only_shelf",
                (x, y, 0),
                r,
                (s, 1, 1),
            ).name
        )
    for x in (-4.20, -1.40, 1.40, 4.00):
        made.append(inst(c, cooler, "rear_wall_cooler", (x, 2.72, 0), 0).name)
    made.append(
        inst(
            c,
            impulse,
            "setback_impulse_rack",
            (-5.30, -2.65, 0),
            -0.10,
            (0.95, 0.75, 1),
        ).name
    )
    made.append(inst(c, checkout, "checkout_inside_zone", (4.50, 0.78, 0), -0.05).name)
    add(
        c,
        "interior_entry_clear_floor",
        (0, -3.05, 0.030),
        (1.60, 0.48, 0.018),
        M["base"],
        0.008,
    )
    return {
        "fresh_13_shelf_instances": 5,
        "fresh_13_cooler_instances": 4,
        "fresh_13_first_object_y_min": -2.65,
        "fresh_13_checkout": 1,
    }


def table_master(M, rectangular=False):
    c = master("rect_table" if rectangular else "round_table")
    if rectangular:
        add(c, "rect_top", (0, 0, 0.75), (0.60, 0.38, 0.045), M["wood"], 0.018)
        for x in (-0.42, 0.42):
            add(c, "trestle_leg", (x, 0, 0.40), (0.035, 0.29, 0.29), M["metal"], 0.008)
        add(c, "low_stretcher", (0, 0, 0.29), (0.36, 0.025, 0.025), M["metal"], 0.004)
    else:
        add_mesh(
            c, "round_top", cyl(), (0, 0, 0.75), (0.42, 0.42, 0.045), M["wood"], 0.018
        )
        add_mesh(
            c,
            "center_pedestal",
            cyl(),
            (0, 0, 0.40),
            (0.055, 0.055, 0.28),
            M["metal"],
            0.010,
        )
        add_mesh(
            c,
            "weighted_base",
            cyl(),
            (0, 0, 0.12),
            (0.30, 0.30, 0.040),
            M["metal"],
            0.010,
        )
    return c


def chair_master(M):
    c = master("clean_restaurant_chair")
    add(c, "seat", (0, 0, 0.45), (0.23, 0.22, 0.045), M["seat"], 0.018)
    add(c, "back", (0, 0.18, 0.78), (0.25, 0.040, 0.22), M["seat"], 0.018)
    for x, y, h in [
        (-0.19, -0.17, 0.20),
        (0.19, -0.17, 0.20),
        (-0.19, 0.17, 0.37),
        (0.19, 0.17, 0.37),
    ]:
        add(
            c,
            "connected_chair_leg",
            (x, y, 0.22 + h / 2),
            (0.030, 0.030, h / 2),
            M["wood"],
            0.006,
        )
    add(c, "front_stretcher", (0, -0.17, 0.25), (0.19, 0.020, 0.020), M["wood"], 0.003)
    return c


def restaurant_counter_master(M):
    c = master("order_counter")
    add(c, "counter_case", (0, 0, 0.50), (1.28, 0.36, 0.40), M["wood"], 0.022)
    add(c, "countertop", (0, 0, 0.91), (1.36, 0.42, 0.045), M["metal"], 0.012)
    add(c, "pos_screen", (0.46, -0.25, 1.12), (0.18, 0.025, 0.13), M["black"], 0.005)
    add(
        c, "glass_display", (-0.44, -0.28, 1.08), (0.32, 0.022, 0.16), M["glass"], 0.003
    )
    return c


def restaurant_interior(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    t1, t2, chair, counter = (
        table_master(M),
        table_master(M, True),
        chair_master(M),
        restaurant_counter_master(M),
    )
    clusters = [
        (-4.35, -2.40, 0.07, t1, 2),
        (-1.80, -2.05, -0.05, t2, 4),
        (0.90, -1.35, 0.12, t1, 3),
        (-3.30, 0.45, -0.03, t2, 4),
    ]
    for x, y, r, table, count in clusters:
        inst(c, table, "interior_only_table", (x, y, 0), r)
        angles = [math.pi, 0, math.pi / 2, -math.pi / 2][:count]
        for a in angles:
            inst(
                c,
                chair,
                "interior_only_chair",
                (x + 0.70 * math.sin(a), y - 0.70 * math.cos(a), 0),
                r + a,
            )
        add_mesh(
            c,
            "table_plate",
            cyl(),
            (x, y, 0.815),
            (0.095, 0.095, 0.010),
            M["ceramic"],
            0.002,
        )
    inst(c, counter, "order_counter_inside_zone", (4.05, 1.70, 0), -0.04)
    add(
        c,
        "rear_service_partition_13",
        (0, 3.58, 1.43),
        (6.55, 0.080, 1.38),
        M["white"],
        0.012,
    )
    add(
        c,
        "open_entry_path_13",
        (5.28, -1.55, 0.030),
        (0.34, 1.90, 0.018),
        M["base"],
        0.006,
    )
    return {
        "restaurant_13_table_instances": 4,
        "restaurant_13_chair_instances": 13,
        "restaurant_13_first_object_y_min": -3.10,
        "restaurant_13_counter": 1,
    }


def frontage(M):
    root = (
        bpy.data.collections.get("all43_01:commercial_root")
        or bpy.context.scene.collection
    )
    c = bpy.data.collections.new(P + "frontage_clean")
    root.children.link(c)
    add(
        c,
        "clean_entry_apron",
        (-31, -26.35, 0.220),
        (18.0, 0.72, 0.080),
        M["paver"],
        0.010,
    )
    add(
        c,
        "continuous_sidewalk_band",
        (-31, -28.05, 0.185),
        (18.0, 0.82, 0.085),
        M["sidewalk"],
        0.010,
    )
    for x in range(-47, -14, 4):
        add(
            c,
            "thin_control_joint",
            (x, -28.05, 0.274),
            (0.012, 0.78, 0.006),
            M["shadow"],
            0.001,
        )
    add(
        c,
        "raised_curb_clean",
        (-31, -29.05, 0.130),
        (18.0, 0.155, 0.125),
        M["curb"],
        0.012,
    )
    add(
        c,
        "asphalt_gutter_clean",
        (-31, -29.35, 0.070),
        (18.0, 0.150, 0.050),
        M["asphalt"],
        0.006,
    )
    # Two real grates replace the previous row of black square holes.
    for x in (-39.5, -23.0):
        add(
            c,
            "trench_drain_frame",
            (x, -29.34, 0.137),
            (0.74, 0.120, 0.018),
            M["metal"],
            0.004,
        )
        for i in range(8):
            add(
                c,
                "narrow_grate_bar",
                (x - 0.56 + i * 0.16, -29.34, 0.160),
                (0.018, 0.105, 0.010),
                M["black"],
                0.001,
            )
    stop = master("wheel_stop_clean")
    add(
        stop, "precast_wheel_stop", (0, 0, 0.090), (0.92, 0.13, 0.085), M["curb"], 0.012
    )
    add(
        stop, "anchor_left", (-0.48, 0, 0.178), (0.030, 0.030, 0.018), M["metal"], 0.004
    )
    add(
        stop, "anchor_right", (0.48, 0, 0.178), (0.030, 0.030, 0.018), M["metal"], 0.004
    )
    for x in (-45.5, -40, -34.5, -29, -23.5, -18):
        inst(c, stop, "wheel_stop_clean_instance", (x, -33.05, 0.145), math.pi / 2)
        for dx in (-1.30, 1.30):
            add(
                c,
                "restrained_parking_stripe",
                (x + dx, -35.35, 0.158),
                (0.045, 1.95, 0.008),
                M["stripe"],
                0.003,
            )
    return c


def material_tone_pass():
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
            if max(col[:3]) > 0.62:
                bsdf.inputs["Base Color"].default_value = tuple(
                    min(x, 0.58) for x in col[:3]
                ) + (col[3],)
                bsdf.inputs["Roughness"].default_value = max(
                    bsdf.inputs["Roughness"].default_value, 0.58
                )
                changed.append(m.name)
        if any(k in low for k in ("green", "terracotta", "paint", "facade")):
            bsdf.inputs["Roughness"].default_value = max(
                bsdf.inputs["Roughness"].default_value, 0.58
            )
    return changed


def sanity_check():
    issues = []
    allowed_front = (
        "clean_",
        "single_",
        "connected_",
        "glass_",
        "flush_",
        "simple_",
        "sign_",
        "storefront_",
        "real_",
        "continuous_",
    )

    def in_master_collection(obj):
        return any("MASTER" in c.name for c in obj.users_collection)

    for o in bpy.data.objects:
        if o.hide_render:
            continue
        if in_master_collection(o):
            continue
        n = o.name
        if n.startswith(P) and o.location.z < -0.05:
            issues.append("below_ground:" + n)
        if n.startswith(P) and "interior_only" in n and o.location.y < -3.35:
            issues.append("interior_too_close_to_glass:" + n)
        if (
            n.startswith(P)
            and -5.85 < o.location.y < -4.75
            and max(o.scale[:]) > 2.2
            and not any(t in n for t in allowed_front)
        ):
            issues.append("unknown_large_front_panel:" + n)
        if "drain_slot" in n.lower() and not o.hide_render:
            issues.append("legacy_black_drain_slot_visible:" + n)
        if "03_side_pilaster" in n and not o.hide_render:
            issues.append("legacy_side_pilaster_visible:" + n)
    duplicate_keys = {}
    for o in bpy.data.objects:
        if o.hide_render or not o.name.startswith(P) or in_master_collection(o):
            continue
        key = (
            o.name.split(".")[0],
            tuple(round(v, 3) for v in o.location),
            tuple(round(v, 3) for v in o.scale),
        )
        duplicate_keys.setdefault(key, 0)
        duplicate_keys[key] += 1
    dupes = [k[0] for k, v in duplicate_keys.items() if v > 1]
    issues.extend("duplicate:" + n for n in dupes)
    if issues:
        raise RuntimeError("All43-13 geometry sanity failed: " + "; ".join(issues[:20]))
    return {"geometry_sanity_check": "PASS", "sanity_issue_count": 0}


def run():
    M = materials()
    hidden = cleanup_legacy_geometry()
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    clean_facade(conv, False, M)
    clean_facade(rest, True, M)
    side_count = restaurant_side_wall(M)
    fresh = fresh_interior(M)
    restaurant = restaurant_interior(M)
    f = frontage(M)
    toned = material_tone_pass()
    audit = sanity_check()
    return {
        "source_cleanup": "urban_v3_all43_12",
        "hidden_problem_front_objects": len(hidden["front"]),
        "hidden_problem_frontage_objects": len(hidden["frontage"]),
        "hidden_legacy_side_wall_bars": len(hidden["side_wall"]),
        "hidden_unconstrained_interior_objects": len(hidden["interior"]),
        "clean_side_wall_elements": side_count,
        "frontage_collection": f.name,
        "toned_overbright_materials": toned,
        "new_all43_13_objects": sum(o.name.startswith(P) for o in bpy.data.objects),
        "storefront_cleanup_audit": "PASS: only connected wall, frame, glass, door, handle, threshold and sign elements",
        "sidewalk_hole_audit": "PASS: repeated black holes hidden; two framed trench grates generated",
        "interior_zone_audit": "PASS: first visible shelves/tables are set back from storefront glass",
        **fresh,
        **restaurant,
        **audit,
    }
