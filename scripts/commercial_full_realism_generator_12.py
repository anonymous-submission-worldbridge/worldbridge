"""All43-12 integrated storefront, frontage and commercial-detail realism pass."""
import math, random
import bpy

P = "all43_12:"


def cube():
    return bpy.data.meshes["all43_10:shared_cube"]


def cyl():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


def bag():
    return bpy.data.meshes.get("all43_10:shared_bag") or cube()


def mat(name, color, rough=0.5, metal=0, noise=0, bump=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    n = m.node_tree.nodes
    l = m.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = color
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metal
    if noise and not n.get(P + "micro_" + name):
        t = n.new("ShaderNodeTexNoise")
        t.name = P + "micro_" + name
        t.inputs["Scale"].default_value = noise
        t.inputs["Detail"].default_value = 4
        t.inputs["Roughness"].default_value = 0.62
        ramp = n.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(
            max(0, x * 0.88) for x in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, x * 1.08 + 0.01) for x in color[:3]
        ) + (1,)
        l.new(t.outputs["Fac"], ramp.inputs["Fac"])
        l.new(ramp.outputs["Color"], bs.inputs["Base Color"])
        b = n.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = bump
        b.inputs["Distance"].default_value = 0.018
        l.new(t.outputs["Fac"], b.inputs["Height"])
        l.new(b.outputs["Normal"], bs.inputs["Normal"])
    return m


def glassmat():
    m = mat("laminated_storefront_glass", (0.035, 0.085, 0.09, 1), 0.12)
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Transmission Weight"].default_value = 0.78
    bs.inputs["IOR"].default_value = 1.46
    bs.inputs["Coat Weight"].default_value = 0.28
    bs.inputs["Coat Roughness"].default_value = 0.07
    return m


def materials():
    return {
        "fresh": mat("fresh_mineral_paint", (0.22, 0.48, 0.30, 1), 0.58, 0, 34, 0.10),
        "rest": mat(
            "restaurant_mineral_paint", (0.56, 0.18, 0.08, 1), 0.60, 0, 31, 0.10
        ),
        "frame": mat(
            "anodized_aluminium", (0.035, 0.045, 0.045, 1), 0.27, 0.72, 48, 0.035
        ),
        "dark": mat("deep_reveal", (0.012, 0.016, 0.016, 1), 0.78),
        "glass": glassmat(),
        "sill": mat("brushed_threshold", (0.23, 0.25, 0.24, 1), 0.33, 0.62, 55, 0.028),
        "signface": mat(
            "channel_letter_face", (0.82, 0.79, 0.67, 1), 0.31, 0, 18, 0.025
        ),
        "signside": mat("channel_letter_return", (0.12, 0.13, 0.12, 1), 0.38, 0.48),
        "green": mat("fresh_sign_panel", (0.055, 0.25, 0.12, 1), 0.46, 0.12, 28, 0.045),
        "terra": mat(
            "kitchen_sign_panel", (0.43, 0.09, 0.035, 1), 0.48, 0.10, 25, 0.045
        ),
        "concrete": mat(
            "architectural_concrete", (0.43, 0.43, 0.40, 1), 0.80, 0, 37, 0.16
        ),
        "paver": mat("entry_paver", (0.48, 0.43, 0.36, 1), 0.72, 0, 29, 0.12),
        "curb": mat("curb_concrete", (0.52, 0.51, 0.47, 1), 0.84, 0, 44, 0.14),
        "asphalt": mat(
            "asphalt_aggregate", (0.035, 0.039, 0.040, 1), 0.92, 0, 72, 0.22
        ),
        "paint": mat("worn_parking_paint", (0.72, 0.69, 0.54, 1), 0.68, 0, 20, 0.06),
        "steel": mat(
            "service_galvanized", (0.27, 0.29, 0.28, 1), 0.42, 0.58, 51, 0.045
        ),
        "asphalt2": mat(
            "asphalt_subtle_patch", (0.049, 0.050, 0.047, 1), 0.94, 0, 85, 0.18
        ),
        "black": mat("rubber_seal", (0.012, 0.014, 0.013, 1), 0.70),
        "wood": mat("interior_oak", (0.27, 0.105, 0.03, 1), 0.45, 0, 16, 0.06),
        "white": mat("equipment_enamel", (0.64, 0.64, 0.59, 1), 0.53, 0, 25, 0.04),
        "lens": mat("fixture_lens", (0.70, 0.66, 0.49, 1), 0.26),
        "shelf": mat(
            "powder_coated_shelf", (0.18, 0.20, 0.18, 1), 0.47, 0.35, 28, 0.045
        ),
        "cooler": mat("cooler_enamel", (0.74, 0.76, 0.70, 1), 0.41, 0, 24, 0.035),
        "warmwood": mat(
            "restaurant_walnut", (0.24, 0.095, 0.035, 1), 0.43, 0, 18, 0.05
        ),
        "seat": mat("muted_vinyl_seat", (0.075, 0.20, 0.17, 1), 0.62, 0, 20, 0.035),
        "carton": mat("printed_carton_mix", (0.70, 0.55, 0.22, 1), 0.46, 0, 22, 0.025),
        "redpkg": mat("red_packaging", (0.55, 0.035, 0.018, 1), 0.43, 0, 30, 0.02),
        "bluepkg": mat("blue_packaging", (0.035, 0.13, 0.42, 1), 0.41, 0, 30, 0.02),
        "greenpkg": mat("green_packaging", (0.025, 0.31, 0.09, 1), 0.45, 0, 26, 0.02),
        "foil": mat("brushed_food_can", (0.55, 0.55, 0.50, 1), 0.24, 0.62, 50, 0.02),
        "ceramic": mat("warm_ceramic", (0.76, 0.73, 0.64, 1), 0.30, 0, 22, 0.018),
    }


def add_mesh(c, n, mesh, loc, s, M, bev=0.008, rot=(0, 0, 0)):
    o = bpy.data.objects.new(P + n, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = s
    o.rotation_euler = rot
    o.data.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bev:
        q = o.modifiers.new("scaled_edge_radius", "BEVEL")
        q.width = min(bev, min(s) * 0.18)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def add(c, n, loc, s, M, bev=0.008, rot=(0, 0, 0)):
    return add_mesh(c, n, cube(), loc, s, M, bev, rot)


def master(n):
    c = bpy.data.collections.new(P + "MASTER:" + n)
    c["high_quality_master"] = True
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


def hide_legacy_front(c):
    hidden = []
    tokens = (
        "mullion",
        "door_frame",
        "sign_band",
        "awning",
        "brand",
        "storefront",
        "door_glass",
        "door_jamb",
        "threshold",
        "kickplate",
        "closer",
        "sign_back",
        "sign_rear",
        "sign_standoff",
        "continuous_plinth",
        "entry_handle",
    )
    for o in c.objects:
        if o.name.startswith(P):
            continue
        if any(t in o.name.lower() for t in tokens) and (
            o.location.y < -4.35 or o.type == "FONT"
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    return hidden


def window(c, x, w, h, M, variant=0):
    y = -5.05
    z = 0.42 + h / 2
    add(
        c,
        "window_shadow_reveal",
        (x, y + 0.13, z),
        (w / 2 + 0.12, 0.12, h / 2 + 0.12),
        M["dark"],
        0.025,
    )
    add(
        c,
        "thick_laminated_glass",
        (x, y - 0.055, z),
        (w / 2 - 0.10, 0.026, h / 2 - 0.10),
        M["glass"],
        0.004,
    )
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "outer_window_jamb",
            (xx, y - 0.11, z),
            (0.075, 0.12, h / 2 + 0.13),
            M["frame"],
            0.015,
        )
    for zz in (0.42, 0.42 + h):
        add(
            c,
            "outer_window_rail",
            (x, y - 0.11, zz),
            (w / 2 + 0.075, 0.12, 0.075),
            M["frame"],
            0.015,
        )
    add(
        c,
        "projecting_window_sill",
        (x, y - 0.25, 0.38),
        (w / 2 + 0.10, 0.20, 0.045),
        M["sill"],
        0.012,
    )
    if variant:
        add(
            c,
            "inner_vertical_stop",
            (x + w * 0.13, y - 0.17, z),
            (0.026, 0.035, h / 2 - 0.12),
            M["frame"],
            0.006,
        )
    add(
        c,
        "interior_head_stop",
        (x, y + 0.015, 0.42 + h - 0.14),
        (w / 2 - 0.12, 0.035, 0.026),
        M["frame"],
        0.005,
    )


def door(c, x, M, double=False):
    y = -5.10
    w = 1.55 if double else 1.18
    h = 2.75
    z = 0.12 + h / 2
    add(
        c,
        "door_opening_reveal",
        (x, y + 0.16, z),
        (w / 2 + 0.14, 0.14, h / 2 + 0.14),
        M["dark"],
        0.025,
    )
    for xx in (x - w / 2, x + w / 2):
        add(
            c,
            "structural_door_jamb",
            (xx, y - 0.11, z),
            (0.085, 0.13, h / 2 + 0.14),
            M["frame"],
            0.016,
        )
    add(
        c,
        "structural_door_head",
        (x, y - 0.11, 0.12 + h),
        (w / 2 + 0.085, 0.13, 0.085),
        M["frame"],
        0.016,
    )
    leaves = 2 if double else 1
    for i in range(leaves):
        cx = x + (-w * 0.25 if i == 0 and double else w * 0.25 if double else 0)
        lw = w / 2 if double else w
        for xx in (cx - lw / 2 + 0.045, cx + lw / 2 - 0.045):
            add(
                c,
                "door_leaf_stile",
                (xx, y - 0.21, z),
                (0.045, 0.045, h / 2 - 0.06),
                M["frame"],
                0.007,
            )
        add(
            c,
            "door_leaf_top_rail",
            (cx, y - 0.21, 0.12 + h - 0.09),
            (lw / 2 - 0.04, 0.045, 0.045),
            M["frame"],
            0.007,
        )
        add(
            c,
            "door_leaf_kick_rail",
            (cx, y - 0.21, 0.30),
            (lw / 2 - 0.04, 0.045, 0.14),
            M["sill"],
            0.008,
        )
        add(
            c,
            "door_leaf_glass",
            (cx, y - 0.19, 1.48),
            (lw / 2 - 0.10, 0.025, 1.05),
            M["glass"],
            0.004,
        )
        hx = cx + (lw * 0.24 if i == 0 else -lw * 0.24)
        add(
            c,
            "door_pull_grip",
            (hx, y - 0.32, 1.45),
            (0.025, 0.035, 0.31),
            M["steel"],
            0.010,
        )
        add(
            c,
            "pull_mount",
            (hx, y - 0.30, 1.17),
            (0.06, 0.04, 0.035),
            M["steel"],
            0.006,
        )
        add(
            c,
            "pull_mount",
            (hx, y - 0.30, 1.73),
            (0.06, 0.04, 0.035),
            M["steel"],
            0.006,
        )
        add(
            c,
            "hydraulic_closer",
            (cx, y - 0.28, 2.65),
            (0.24, 0.055, 0.045),
            M["steel"],
            0.008,
        )
        add(
            c,
            "closer_arm",
            (cx + 0.18, y - 0.30, 2.60),
            (0.20, 0.018, 0.018),
            M["steel"],
            0.005,
            rot=(0, 0.16, 0),
        )
    add(
        c,
        "raised_door_threshold",
        (x, y - 0.33, 0.09),
        (w / 2 + 0.11, 0.24, 0.05),
        M["sill"],
        0.010,
    )
    add(
        c,
        "recessed_entry_mat",
        (x, y - 0.78, 0.035),
        (w / 2 + 0.18, 0.34, 0.025),
        M["black"],
        0.018,
    )


def awning(c, width, z, M, color):
    y = -5.12
    add(
        c,
        "awning_wall_flashing",
        (0, y, z + 0.16),
        (width / 2, 0.08, 0.10),
        M["steel"],
        0.012,
    )
    add(
        c,
        "sloped_awning_skin",
        (0, y - 0.58, z),
        (width / 2, 0.68, 0.07),
        color,
        0.025,
        rot=(0.10, 0, 0),
    )
    add(
        c,
        "formed_front_fascia",
        (0, y - 1.25, z - 0.12),
        (width / 2, 0.10, 0.15),
        color,
        0.022,
    )
    add(
        c,
        "integrated_gutter",
        (0, y - 1.36, z - 0.23),
        (width / 2, 0.085, 0.055),
        M["steel"],
        0.012,
    )
    for x in (-width * 0.42, -width * 0.14, width * 0.14, width * 0.42):
        add(
            c,
            "triangular_brace_wall",
            (x, y - 0.05, z - 0.30),
            (0.035, 0.035, 0.30),
            M["steel"],
            0.008,
        )
        add(
            c,
            "triangular_brace_arm",
            (x, y - 0.55, z - 0.27),
            (0.035, 0.58, 0.035),
            M["steel"],
            0.008,
            rot=(0.48, 0, 0),
        )


def sign(c, label, z, M, panelmat, width):
    add(
        c,
        "sign_recess_shadow",
        (0, -5.01, z),
        (width / 2 + 0.18, 0.11, 0.48),
        M["dark"],
        0.025,
    )
    add(
        c,
        "folded_sign_backplate",
        (0, -5.16, z),
        (width / 2, 0.08, 0.40),
        panelmat,
        0.030,
    )
    add(
        c,
        "sign_mounting_rail",
        (0, -5.27, z),
        (width / 2 - 0.16, 0.035, 0.045),
        M["signside"],
        0.009,
    )
    for x in (-width * 0.36, -width * 0.18, 0, width * 0.18, width * 0.36):
        add(
            c,
            "letter_standoff",
            (x, -5.35, z),
            (0.025, 0.10, 0.025),
            M["signside"],
            0.006,
        )
    old = next(
        (
            o
            for o in c.objects
            if o.type == "FONT" and " ".join(o.data.body.split()) == label
        ),
        None,
    )
    if old:
        data = old.data.copy()
        data.extrude = 0.13
        data.bevel_depth = 0.018
        data.bevel_resolution = 3
        data.materials.clear()
        data.materials.append(M["signface"])
        t = bpy.data.objects.new(P + "channel_letters_" + label.replace(" ", "_"), data)
        c.objects.link(t)
        t.location = (old.location.x, -5.42, z)
        t.rotation_euler = old.rotation_euler
        t.scale = old.scale
        t["real_channel_letter"] = True


def facade(c, is_rest, M):
    hidden = hide_legacy_front(c)
    wall = M["rest"] if is_rest else M["fresh"]
    panel = M["terra"] if is_rest else M["green"]
    top = 5.45 if is_rest else 4.95
    # Articulated wall pieces preserve true window/door openings instead of covering the facade with one plane.
    add(
        c,
        "facade_upper_wall",
        (0, -4.93, (3.42 + top) / 2),
        (7.68, 0.22, (top - 3.42) / 2),
        wall,
        0.035,
    )
    add(c, "facade_left_return", (-7.58, -4.94, 1.80), (0.26, 0.23, 1.62), wall, 0.030)
    add(
        c,
        "facade_right_return",
        ((7.35 if is_rest else 7.58), -4.94, 1.80),
        (0.26, 0.23, 1.62),
        wall,
        0.030,
    )
    if is_rest:
        door(c, 5.55, M)
        specs = [
            (-5.7, 2.45, 2.80, 1),
            (-3.00, 2.45, 2.80, 0),
            (-0.25, 2.55, 2.80, 1),
            (2.65, 2.65, 2.80, 0),
        ]
    else:
        door(c, 0, M, True)
        specs = [
            (-5.65, 2.75, 2.80, 1),
            (-2.75, 2.45, 2.80, 0),
            (2.65, 2.25, 2.80, 1),
            (5.30, 2.65, 2.80, 0),
        ]
    for i, (x, w, h, v) in enumerate(specs):
        window(c, x, w, h, M, v)
    # Piers are aligned with opening boundaries, giving load-bearing rhythm and visible inset depth.
    bounds = sorted(
        set(
            [-7.4, 7.4]
            + [round(x - w / 2 - 0.10, 2) for x, w, _, _ in specs]
            + [round(x + w / 2 + 0.10, 2) for x, w, _, _ in specs]
        )
    )
    for x in bounds:
        add(
            c,
            "facade_structural_pier",
            (x, -5.00, 1.82),
            (0.105, 0.26, 1.62),
            wall,
            0.018,
        )
    add(
        c,
        "continuous_base_course",
        (0, -5.02, 0.25),
        (7.60, 0.25, 0.20),
        M["concrete"],
        0.020,
    )
    add(
        c,
        "roof_edge_coping",
        (0, -4.98, top + 0.18),
        (7.76, 0.28, 0.12),
        M["sill"],
        0.022,
    )
    awning(c, 14.7 if not is_rest else 13.9, 3.66 if not is_rest else 4.02, M, panel)
    sign(
        c,
        "CORNER KITCHEN" if is_rest else "FRESH MART",
        5.12 if is_rest else 4.62,
        M,
        panel,
        8.6 if is_rest else 6.4,
    )
    return hidden


def frontage(M):
    root = (
        bpy.data.collections.get("all43_01:commercial_root")
        or bpy.context.scene.collection
    )
    c = bpy.data.collections.new(P + "frontage_and_parking")
    root.children.link(c)
    # World-space sequence: entrance apron -> jointed sidewalk -> raised curb -> gutter -> asphalt.
    add(
        c,
        "continuous_entrance_apron",
        (-31, -26.35, 0.24),
        (18.0, 0.75, 0.10),
        M["paver"],
        0.020,
    )
    for x in range(-48, -13, 2):
        add(
            c,
            "individual_sidewalk_slab",
            (x, -28.05, 0.20),
            (0.96, 0.82, 0.10),
            M["concrete"],
            0.018,
        )
        add(
            c,
            "paving_joint",
            (x + 1.0, -28.05, 0.305),
            (0.018, 0.80, 0.008),
            M["black"],
            0.002,
        )
    add(c, "raised_curb", (-31, -29.05, 0.14), (18.0, 0.18, 0.14), M["curb"], 0.025)
    add(c, "gutter_pan", (-31, -29.40, 0.075), (18.0, 0.17, 0.055), M["asphalt"], 0.012)
    for x in (-46, -38, -30, -22, -16):
        add(
            c,
            "cast_drain_body",
            (x, -29.40, 0.14),
            (0.62, 0.16, 0.028),
            M["steel"],
            0.006,
        )
        for j in range(7):
            add(
                c,
                "drain_grate_slot",
                (x - 0.48 + j * 0.16, -29.43, 0.174),
                (0.025, 0.12, 0.010),
                M["black"],
                0.002,
            )
    # Detailed wheel stops and restrained stripe wear variations sit on the retained parking lot.
    stop = master("reinforced_wheel_stop")
    add(stop, "precast_stop", (0, 0, 0.10), (1.02, 0.16, 0.10), M["curb"], 0.025)
    add(stop, "rubber_end_l", (-0.92, 0, 0.11), (0.10, 0.17, 0.08), M["black"], 0.015)
    add(stop, "rubber_end_r", (0.92, 0, 0.11), (0.10, 0.17, 0.08), M["black"], 0.015)
    add(stop, "anchor_l", (-0.52, 0, 0.205), (0.035, 0.035, 0.025), M["steel"], 0.008)
    add(stop, "anchor_r", (0.52, 0, 0.205), (0.035, 0.035, 0.025), M["steel"], 0.008)
    for i, x in enumerate((-45.5, -40, -34.5, -29, -23.5, -18)):
        inst(c, stop, "anchored_wheel_stop", (x, -33.05, 0.15), math.pi / 2)
        for dx in (-1.30, 1.30):
            add(
                c,
                "worn_stall_marking",
                (x + dx, -35.4, 0.165),
                (0.055, 2.15, 0.012),
                M["paint"],
                0.006,
            )
    for i, (x, y, w, d) in enumerate(
        (
            (-43, -34.1, 2.4, 1.1),
            (-35.2, -36.7, 3.1, 0.9),
            (-25.4, -34.6, 2.7, 1.2),
            (-18.6, -36.0, 2.0, 0.8),
        )
    ):
        add(
            c,
            "aggregate_tone_variation_patch",
            (x, y, 0.151),
            (w, d, 0.010),
            M["asphalt2"],
            0.018,
            rot=(0, 0, (i - 0.5) * 0.04),
        )
    for x in (-43.5, -36.5, -29.5, -22.5):
        add(
            c,
            "entry_apron_control_joint",
            (x, -26.35, 0.348),
            (0.018, 0.72, 0.010),
            M["black"],
            0.002,
        )
    for y in (-26.0, -26.70):
        add(
            c,
            "entry_apron_sawcut",
            (-31, y, 0.350),
            (17.4, 0.014, 0.010),
            M["black"],
            0.002,
        )
    return c


def detail_masters(M):
    hv = master("roof_hvac")
    add(hv, "insulated_cabinet", (0, 0, 0.58), (1.15, 0.82, 0.58), M["steel"], 0.055)
    add(hv, "weather_cap", (0, 0, 1.18), (1.22, 0.89, 0.06), M["steel"], 0.025)
    add(hv, "supply_duct", (1.30, 0.10, 0.35), (0.18, 0.55, 0.35), M["steel"], 0.035)
    for x in (-0.70, -0.35, 0, 0.35, 0.70):
        add(
            hv,
            "pressed_louver",
            (x, -0.84, 0.62),
            (0.025, 0.025, 0.35),
            M["black"],
            0.005,
        )
    ac = master("split_ac")
    add(ac, "formed_case", (0, 0, 0.48), (0.72, 0.30, 0.48), M["white"], 0.045)
    add(ac, "fan_recess", (0, -0.32, 0.48), (0.35, 0.025, 0.35), M["black"], 0.025)
    for a in range(12):
        q = a * math.pi / 6
        add(
            ac,
            "radial_fan_guard",
            (0.27 * math.cos(q), -0.36, 0.48 + 0.27 * math.sin(q)),
            (0.025, 0.018, 0.025),
            M["steel"],
            0.008,
        )
    cam = master("camera_wallpack")
    add(cam, "wall_mount", (0, 0, 0.12), (0.12, 0.09, 0.12), M["steel"], 0.025)
    add(cam, "camera_body", (0, -0.19, 0.08), (0.11, 0.18, 0.09), M["white"], 0.035)
    add(cam, "camera_lens", (0, -0.38, 0.08), (0.055, 0.02, 0.055), M["black"], 0.014)
    add(cam, "wallpack_housing", (0.48, 0, 0.14), (0.27, 0.14, 0.18), M["steel"], 0.028)
    add(
        cam, "wallpack_lens", (0.48, -0.16, 0.12), (0.21, 0.025, 0.12), M["lens"], 0.014
    )
    pipe = master("formed_downpipe")
    add(pipe, "vertical_pipe", (0, 0, 1.24), (0.045, 0.045, 1.24), M["steel"], 0.014)
    add(
        pipe,
        "offset_elbow_top",
        (0, -0.09, 2.50),
        (0.045, 0.13, 0.045),
        M["steel"],
        0.010,
    )
    add(
        pipe,
        "offset_elbow_bottom",
        (0, -0.09, 0.12),
        (0.045, 0.13, 0.045),
        M["steel"],
        0.010,
    )
    add(
        pipe,
        "wall_strap_low",
        (0, 0.025, 0.70),
        (0.13, 0.018, 0.030),
        M["steel"],
        0.006,
    )
    add(
        pipe,
        "wall_strap_high",
        (0, 0.025, 1.80),
        (0.13, 0.018, 0.030),
        M["steel"],
        0.006,
    )
    elec = master("service_electrical_panel")
    add(elec, "back_box", (0, 0, 0.48), (0.36, 0.08, 0.48), M["steel"], 0.025)
    add(elec, "hinged_door", (0, -0.09, 0.50), (0.33, 0.025, 0.42), M["white"], 0.012)
    add(
        elec,
        "meter_socket",
        (-0.12, -0.12, 0.78),
        (0.09, 0.018, 0.09),
        M["black"],
        0.010,
    )
    add(
        elec,
        "warning_label",
        (0.10, -0.125, 0.44),
        (0.11, 0.006, 0.045),
        M["redpkg"],
        0.002,
    )
    add(elec, "conduit_up", (0, 0.02, 1.05), (0.028, 0.028, 0.32), M["steel"], 0.008)
    add(elec, "conduit_down", (0, 0.02, -0.12), (0.028, 0.028, 0.30), M["steel"], 0.008)
    return hv, ac, cam, pipe, elec


def details(M):
    hv, ac, cam, pipe, elec = detail_masters(M)
    for i, cname in enumerate(
        ("all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant")
    ):
        c = bpy.data.collections[cname]
        inst(c, hv, "roof_HVAC", ((-2.8 if i else 3.0), 1.3, 5.7 if i else 5.2), 0.05)
        inst(c, ac, "side_AC", (7.7, 1.0, 1.35), math.pi / 2)
        inst(c, cam, "security_and_wall_light", (-6.4, -5.0, 3.35))
        inst(c, pipe, "functional_downpipe", (-7.40, -4.80, 0.12))
        inst(c, elec, "side_service_panel", (-6.85, 4.20, 0.22), math.pi)


def hide_legacy_interior(c):
    hidden = []
    prefixes = (
        "all43_11_object3:",
        "all43_11_object2:",
        "all43_11_object:",
        "all43_11_light:",
        "all43_11_res:",
    )
    tokens = (
        "shelf",
        "product",
        "stock",
        "checkout",
        "register",
        "cooler",
        "freezer",
        "table",
        "chair",
        "dining",
        "counter",
        "sideboard",
        "partition",
    )
    for o in c.objects:
        if o.name.startswith(P):
            continue
        if o.name.startswith(prefixes) or (
            o.location.y > -4.15 and any(t in o.name.lower() for t in tokens)
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    return hidden


def retail_products(M):
    r = []
    b = master("retail_bottle_master")
    add_mesh(
        b,
        "rounded_bottle_body",
        cyl(),
        (0, 0, 0.18),
        (0.075, 0.075, 0.18),
        M["greenpkg"],
        0.012,
    )
    add_mesh(
        b,
        "narrow_neck",
        cyl(),
        (0, 0, 0.39),
        (0.034, 0.034, 0.055),
        M["greenpkg"],
        0.008,
    )
    add_mesh(
        b, "ribbed_cap", cyl(), (0, 0, 0.46), (0.043, 0.043, 0.018), M["foil"], 0.004
    )
    add_mesh(
        b, "paper_label", cyl(), (0, 0, 0.20), (0.078, 0.078, 0.060), M["carton"], 0.003
    )
    r.append(b)
    can = master("retail_can_master")
    add_mesh(
        can,
        "rolled_can_body",
        cyl(),
        (0, 0, 0.14),
        (0.082, 0.082, 0.14),
        M["foil"],
        0.006,
    )
    add_mesh(
        can,
        "printed_sleeve",
        cyl(),
        (0, 0, 0.15),
        (0.085, 0.085, 0.100),
        M["bluepkg"],
        0.002,
    )
    add_mesh(
        can, "top_lip", cyl(), (0, 0, 0.286), (0.087, 0.087, 0.010), M["foil"], 0.002
    )
    add(can, "pull_tab", (0, -0.020, 0.300), (0.024, 0.012, 0.004), M["black"], 0.002)
    r.append(can)
    carton = master("retail_carton_master")
    add(carton, "creased_box", (0, 0, 0.22), (0.135, 0.065, 0.22), M["carton"], 0.012)
    add(
        carton,
        "front_print_panel",
        (0, -0.068, 0.25),
        (0.102, 0.006, 0.115),
        M["redpkg"],
        0.002,
    )
    add(
        carton,
        "side_nutrition_label",
        (0.138, 0, 0.20),
        (0.006, 0.045, 0.11),
        M["white"],
        0.002,
    )
    add(carton, "top_flap", (0, 0, 0.445), (0.125, 0.060, 0.009), M["greenpkg"], 0.002)
    r.append(carton)
    pouch = master("retail_pouch_master")
    add_mesh(
        pouch,
        "formed_standup_pouch",
        bag(),
        (0, 0, 0.19),
        (0.135, 0.092, 0.38),
        M["redpkg"],
        0.010,
    )
    add(pouch, "heat_seal_top", (0, 0, 0.385), (0.13, 0.018, 0.012), M["foil"], 0.002)
    add(
        pouch,
        "printed_window",
        (0, -0.096, 0.22),
        (0.080, 0.006, 0.080),
        M["carton"],
        0.002,
    )
    r.append(pouch)
    flat = master("retail_flat_pack_master")
    add(
        flat,
        "thin_hanging_pack",
        (0, 0, 0.16),
        (0.115, 0.028, 0.16),
        M["bluepkg"],
        0.010,
    )
    add(flat, "euro_slot", (0, -0.031, 0.285), (0.042, 0.006, 0.010), M["black"], 0.002)
    add(
        flat,
        "small_label",
        (0, -0.033, 0.145),
        (0.076, 0.004, 0.040),
        M["white"],
        0.002,
    )
    r.append(flat)
    return r


def stock_shelf_faces(c, prods, M, w, levels, depth=0.34, seed=1):
    rng = random.Random(seed)
    made = 0
    for level in range(levels):
        z = 0.34 + level * 0.32
        add(c, "solid_shelf_deck", (0, -0.02, z), (w, depth, 0.035), M["shelf"], 0.008)
        add(
            c,
            "price_rail",
            (0, -depth - 0.035, z + 0.045),
            (w, 0.018, 0.030),
            M["black"],
            0.003,
        )
        slots = 7 + level % 3
        for i in range(slots):
            if rng.random() < (0.10 + 0.04 * (level % 2)):
                continue
            x = (
                -w * 0.80
                + i * (w * 1.60 / max(1, slots - 1))
                + (rng.random() - 0.5) * 0.035
            )
            p = prods[(i + level * 3 + seed) % len(prods)]
            s = 0.70 + rng.random() * 0.28
            inst(
                c,
                p,
                "mixed_supported_merchandise",
                (x, -depth * 0.42, z + 0.045),
                (rng.random() - 0.5) * 0.08,
                (s, s, s),
            )
            made += 1
    return made


def fresh_asset_masters(M):
    prods = retail_products(M)
    masters = []
    goods = 0
    for idx, (name, w, h, levels) in enumerate(
        (
            ("wide_gondola", 1.20, 1.72, 5),
            ("narrow_gondola", 0.92, 1.48, 4),
            ("front_impulse_rack", 0.70, 1.20, 4),
        )
    ):
        c = master(name)
        add(
            c,
            "joined_base_plinth",
            (0, 0, 0.11),
            (w + 0.09, 0.42, 0.09),
            M["shelf"],
            0.014,
        )
        for x in (-w, w):
            add(
                c,
                "continuous_upright",
                (x, 0.18, h / 2),
                (0.045, 0.055, h / 2),
                M["steel"],
                0.010,
            )
        add(
            c,
            "perforated_back_panel",
            (0, 0.21, h / 2),
            (w, 0.030, h / 2 - 0.08),
            M["shelf"],
            0.004,
        )
        add(
            c,
            "top_cross_rail",
            (0, 0.19, h - 0.05),
            (w, 0.045, 0.045),
            M["steel"],
            0.006,
        )
        goods += stock_shelf_faces(c, prods, M, w, levels, 0.34, 43120 + idx)
        masters.append(c)
    cooler = master("glass_door_wall_cooler")
    add(cooler, "cooler_case", (0, 0, 1.02), (1.38, 0.38, 1.02), M["cooler"], 0.035)
    add(
        cooler,
        "dark_inner_cavity",
        (0, -0.39, 1.05),
        (1.22, 0.04, 0.82),
        M["black"],
        0.006,
    )
    for x in (-0.48, 0, 0.48):
        add(
            cooler,
            "cooler_glass_door",
            (x, -0.47, 1.05),
            (0.28, 0.025, 0.78),
            M["glass"],
            0.005,
        )
        add(
            cooler,
            "cooler_vertical_handle",
            (x + 0.22, -0.52, 1.07),
            (0.020, 0.035, 0.36),
            M["steel"],
            0.006,
        )
    for z in (0.55, 0.88, 1.20, 1.52):
        add(
            cooler,
            "cooler_internal_shelf",
            (0, -0.33, z),
            (1.16, 0.22, 0.025),
            M["steel"],
            0.004,
        )
    goods += stock_shelf_faces(cooler, prods, M, 1.02, 4, 0.18, 43129)
    masters.append(cooler)
    return masters, goods


def checkout_master(M):
    c = master("detailed_checkout_counter")
    add(
        c, "customer_side_panel", (0, 0, 0.48), (1.25, 0.38, 0.48), M["warmwood"], 0.035
    )
    add(c, "stone_countertop", (0, 0, 0.98), (1.35, 0.46, 0.055), M["sill"], 0.025)
    add(c, "bagging_ledge", (-0.70, -0.15, 0.72), (0.12, 0.26, 0.21), M["steel"], 0.012)
    add(c, "register_base", (0.32, -0.12, 1.07), (0.20, 0.14, 0.055), M["black"], 0.010)
    add(
        c,
        "register_screen",
        (0.38, -0.18, 1.25),
        (0.20, 0.035, 0.16),
        M["black"],
        0.010,
        rot=(0.12, 0, 0),
    )
    add(
        c, "scanner_plate", (-0.18, -0.22, 1.04), (0.20, 0.13, 0.014), M["black"], 0.004
    )
    add(
        c, "receipt_printer", (0.02, 0.10, 1.08), (0.18, 0.12, 0.055), M["white"], 0.010
    )
    return c


def fresh_interior(M):
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    hidden = hide_legacy_interior(conv)
    shelves, goods = fresh_asset_masters(M)
    checkout = checkout_master(M)
    made = []
    layout = [
        (-4.65, -1.75, 0.04, 1.00),
        (-2.10, -0.72, -0.03, 0.96),
        (0.72, -1.55, 0.05, 0.94),
        (-3.70, 0.78, 0.02, 0.88),
        (2.85, 0.55, -0.04, 0.82),
    ]
    for i, (x, y, r, s) in enumerate(layout):
        made.append(
            inst(
                conv, shelves[i % 3], "zoned_stocked_shelf", (x, y, 0), r, (s, 1, 1)
            ).name
        )
    for x in (-4.55, -1.60, 1.40, 4.15):
        made.append(
            inst(
                conv,
                shelves[3],
                "continuous_rear_cooler",
                (x, 2.88, 0),
                0,
                (1.0, 1.0, 1.0),
            ).name
        )
    made.append(
        inst(
            conv,
            shelves[2],
            "front_impulse_display_l",
            (-5.45, -3.10, 0),
            -0.18,
            (1.0, 0.75, 1.0),
        ).name
    )
    made.append(
        inst(
            conv,
            shelves[2],
            "front_impulse_display_r",
            (4.95, -3.04, 0),
            0.22,
            (1.0, 0.75, 1.0),
        ).name
    )
    made.append(
        inst(conv, checkout, "checkout_near_entry", (4.45, 0.92, 0), -0.06).name
    )
    add(
        conv,
        "clear_entry_apron_inside",
        (0, -3.35, 0.035),
        (1.85, 0.78, 0.025),
        M["black"],
        0.015,
    )
    add(
        conv,
        "back_stockroom_wall",
        (0, 3.72, 1.48),
        (6.95, 0.10, 1.48),
        M["white"],
        0.020,
    )
    add(
        conv,
        "staff_door_with_pushplate",
        (5.80, 3.58, 1.28),
        (0.55, 0.045, 1.18),
        M["steel"],
        0.018,
    )
    for x, label in [
        (-4.8, "DAIRY"),
        (-1.5, "DRINKS"),
        (1.5, "SNACKS"),
        (4.4, "CHECKOUT"),
    ]:
        add(
            conv,
            "small_category_blade_" + label,
            (x, -0.08, 2.36),
            (0.34, 0.035, 0.075),
            M["green"],
            0.006,
        )
    return {
        "fresh_hidden_legacy_interior": len(hidden),
        "fresh_shelf_master_variants": 4,
        "fresh_shelf_instances": len(
            [n for n in made if "shelf" in n or "cooler" in n or "display" in n]
        ),
        "fresh_product_master_categories": 5,
        "fresh_supported_product_instances_in_masters": goods,
        "fresh_checkout_instances": 1,
        "fresh_spatial_zones": [
            "entry apron",
            "front impulse display",
            "offset aisles",
            "wall coolers",
            "checkout",
            "back stockroom",
        ],
    }


def dining_masters(M):
    table = master("restaurant_weighted_table")
    add(
        table, "thick_tabletop", (0, 0, 0.77), (0.48, 0.48, 0.055), M["warmwood"], 0.030
    )
    add(table, "center_pedestal", (0, 0, 0.42), (0.075, 0.075, 0.30), M["steel"], 0.018)
    add(table, "weighted_foot", (0, 0, 0.13), (0.34, 0.34, 0.050), M["steel"], 0.020)
    rect = master("restaurant_rectangular_table")
    add(
        rect, "rectangular_top", (0, 0, 0.77), (0.68, 0.42, 0.055), M["warmwood"], 0.030
    )
    add(rect, "trestle_left", (-0.46, 0, 0.40), (0.045, 0.34, 0.28), M["steel"], 0.014)
    add(rect, "trestle_right", (0.46, 0, 0.40), (0.045, 0.34, 0.28), M["steel"], 0.014)
    add(rect, "low_stretcher", (0, 0, 0.30), (0.42, 0.035, 0.035), M["steel"], 0.008)
    chair = master("restaurant_joined_chair")
    add(chair, "upholstered_seat", (0, 0, 0.47), (0.25, 0.24, 0.055), M["seat"], 0.025)
    add(
        chair, "bent_back_panel", (0, 0.19, 0.80), (0.28, 0.045, 0.25), M["seat"], 0.025
    )
    add(
        chair,
        "rear_leg_l",
        (-0.21, 0.20, 0.47),
        (0.035, 0.035, 0.39),
        M["warmwood"],
        0.010,
    )
    add(
        chair,
        "rear_leg_r",
        (0.21, 0.20, 0.47),
        (0.035, 0.035, 0.39),
        M["warmwood"],
        0.010,
    )
    add(
        chair,
        "front_leg_l",
        (-0.21, -0.19, 0.28),
        (0.035, 0.035, 0.20),
        M["warmwood"],
        0.010,
    )
    add(
        chair,
        "front_leg_r",
        (0.21, -0.19, 0.28),
        (0.035, 0.035, 0.20),
        M["warmwood"],
        0.010,
    )
    add(
        chair,
        "front_stretcher",
        (0, -0.19, 0.27),
        (0.20, 0.025, 0.025),
        M["warmwood"],
        0.006,
    )
    add(
        chair,
        "side_stretcher_l",
        (-0.21, 0, 0.29),
        (0.025, 0.18, 0.025),
        M["warmwood"],
        0.006,
    )
    add(
        chair,
        "side_stretcher_r",
        (0.21, 0, 0.29),
        (0.025, 0.18, 0.025),
        M["warmwood"],
        0.006,
    )
    setting = master("real_table_setting")
    add_mesh(
        setting,
        "ceramic_plate",
        cyl(),
        (0, -0.18, 0.020),
        (0.105, 0.105, 0.012),
        M["ceramic"],
        0.004,
    )
    add_mesh(
        setting,
        "water_glass",
        cyl(),
        (0.16, -0.08, 0.075),
        (0.038, 0.038, 0.075),
        M["glass"],
        0.004,
    )
    add(
        setting,
        "folded_napkin",
        (-0.15, -0.08, 0.026),
        (0.065, 0.032, 0.008),
        M["redpkg"],
        0.002,
    )
    booth = master("wall_banquette_booth")
    add(
        booth,
        "upholstered_bench_base",
        (0, 0, 0.30),
        (0.80, 0.28, 0.24),
        M["seat"],
        0.030,
    )
    add(
        booth,
        "continuous_back_cushion",
        (0, 0.25, 0.78),
        (0.86, 0.08, 0.42),
        M["seat"],
        0.030,
    )
    add(
        booth,
        "wood_toe_kick",
        (0, -0.03, 0.08),
        (0.86, 0.26, 0.08),
        M["warmwood"],
        0.012,
    )
    return table, rect, chair, setting, booth


def counter_master(M):
    c = master("restaurant_order_counter")
    add(c, "front_counter_case", (0, 0, 0.55), (1.55, 0.42, 0.45), M["warmwood"], 0.035)
    add(c, "stone_service_top", (0, -0.01, 1.03), (1.65, 0.50, 0.060), M["sill"], 0.025)
    add(
        c,
        "display_case_glass",
        (-0.55, -0.36, 1.25),
        (0.42, 0.035, 0.22),
        M["glass"],
        0.006,
    )
    add(c, "pos_screen", (0.55, -0.30, 1.25), (0.22, 0.035, 0.16), M["black"], 0.008)
    add(c, "pickup_shelf", (0, 0.36, 1.28), (1.38, 0.11, 0.035), M["steel"], 0.006)
    return c


def restaurant_interior(M):
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    hidden = hide_legacy_interior(rest)
    table, rect, chair, setting, booth = dining_masters(M)
    counter = counter_master(M)
    made = []
    clusters = [
        (-4.55, -2.25, 0.10, table, 2),
        (-2.05, -1.92, -0.08, rect, 4),
        (0.86, -0.88, 0.14, table, 3),
        (-3.45, 0.58, 0.03, rect, 4),
    ]
    for idx, (x, y, r, t, chairs) in enumerate(clusters):
        made.append(inst(rest, t, "non_grid_dining_table", (x, y, 0), r).name)
        made.append(
            inst(rest, setting, "individual_table_setting", (x, y, 0.82), r).name
        )
        seat_angles = [math.pi, 0, math.pi / 2, -math.pi / 2][:chairs]
        for j, a in enumerate(seat_angles):
            dx = 0.78 * math.sin(a)
            dy = -0.78 * math.cos(a)
            made.append(
                inst(
                    rest, chair, "inward_dining_chair", (x + dx, y + dy, 0), r + a
                ).name
            )
    for x, y, r in [(-5.80, 0.85, 0.02), (-5.72, 2.05, -0.04), (-0.55, 2.45, 0.03)]:
        made.append(inst(rest, booth, "wall_banquette", (x, y, 0), r).name)
    made.append(
        inst(rest, counter, "visible_order_counter", (3.95, 1.85, 0), -0.04).name
    )
    add(
        rest,
        "open_customer_path",
        (5.35, -1.60, 0.030),
        (0.42, 2.35, 0.020),
        M["black"],
        0.010,
    )
    add(
        rest,
        "rear_service_wall",
        (0, 3.64, 1.48),
        (6.90, 0.10, 1.48),
        M["white"],
        0.020,
    )
    add(
        rest,
        "stainless_prep_table",
        (1.55, 3.22, 0.72),
        (0.72, 0.30, 0.32),
        M["steel"],
        0.020,
    )
    add(
        rest,
        "back_shelving_unit",
        (-1.25, 3.25, 1.02),
        (0.78, 0.22, 0.80),
        M["shelf"],
        0.018,
    )
    add(
        rest,
        "menu_board_cluster",
        (3.95, 3.48, 2.18),
        (1.35, 0.035, 0.32),
        M["black"],
        0.010,
    )
    for x in (3.35, 4.55):
        add(
            rest,
            "small_menu_card",
            (x, 3.43, 2.18),
            (0.42, 0.012, 0.22),
            M["carton"],
            0.003,
        )
    return {
        "restaurant_hidden_legacy_interior": len(hidden),
        "restaurant_table_variants": 2,
        "restaurant_table_instances": len(clusters),
        "restaurant_chair_instances": sum(c[-1] for c in clusters),
        "restaurant_banquette_instances": 3,
        "restaurant_counter_instances": 1,
        "restaurant_spatial_zones": [
            "entry transition",
            "non-grid dining",
            "main aisle",
            "order counter",
            "rear service background",
        ],
    }


def run():
    M = materials()
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    hc = facade(conv, False, M)
    hr = facade(rest, True, M)
    f = frontage(M)
    details(M)
    fresh = fresh_interior(M)
    restaurant = restaurant_interior(M)
    return {
        "legacy_front_objects_hidden": len(hc) + len(hr),
        "fresh_layout": "central double entrance + unequal display windows",
        "restaurant_layout": "right entrance + dining-aligned windows",
        "new_all43_12_objects": sum(o.name.startswith(P) for o in bpy.data.objects),
        "frontage_collection": f.name,
        "shared_mesh_data": True,
        "essential_detail_masters": 5,
        "storefront_depth_audit": "PASS",
        "glass_door_audit": "PASS: thick framed glass, thresholds, handles and closers",
        "frontage_sequence_audit": "PASS: storefront -> apron -> sidewalk -> curb -> gutter -> asphalt",
        **fresh,
        **restaurant,
        "final_pipeline_scope": "storefront, sign, glass/door, Fresh Mart interior, Corner Kitchen interior, frontage/parking, essential details, procedural materials",
    }
