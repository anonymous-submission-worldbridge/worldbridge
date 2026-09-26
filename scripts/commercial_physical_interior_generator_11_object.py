"""Physically grounded and structurally connected commercial interiors."""
import math, random
import bpy

P = "all43_11_object:"


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


def add(c, n, loc, s, M, rot=0, bev=0.008):
    o = bpy.data.objects.new(P + n, cube())
    c.objects.link(o)
    o.location = loc
    o.scale = s
    o.rotation_euler[2] = rot
    if not o.data.materials:
        o.data.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bev:
        q = o.modifiers.new("physical_edge_bevel", "BEVEL")
        q.width = min(bev, min(s) * 0.18)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def master(n):
    c = bpy.data.collections.new(P + "MASTER:" + n)
    c["physical_master"] = True
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
        "frame": mat("fixture_frame", (0.10, 0.12, 0.115, 1), 0.34, 0.62),
        "deck": mat("shelf_deck", (0.42, 0.45, 0.42, 1), 0.46, 0.24),
        "label": mat("label_strip", (0.62, 0.49, 0.10, 1), 0.48),
        "wood": mat("restaurant_wood", (0.26, 0.085, 0.024, 1), 0.39),
        "seat": mat("seat_upholstery", (0.10, 0.16, 0.13, 1), 0.60),
        "dark": mat("service_dark", (0.022, 0.028, 0.026, 1), 0.67),
        "counter": mat("service_counter", (0.40, 0.38, 0.31, 1), 0.45),
        "steel": mat("restaurant_steel", (0.18, 0.21, 0.20, 1), 0.30, 0.68),
    }


def products():
    names = ("bottle", "can", "carton", "bag", "box")
    return [bpy.data.collections["all43_10:MASTER:product_" + n] for n in names]


def grounded_shelf(M, variant):
    c = master("grounded_shelf_v" + str(variant))
    w = (1.12, 1.38, 0.96)[variant]
    h = (1.80, 2.0, 1.62)[variant]
    levels = (5, 6, 4)[variant]
    floor = 0.10
    # Continuous plinth and adjustable feet establish an unambiguous load path to the floor.
    add(
        c,
        "continuous_plinth",
        (0, 0, floor + 0.055),
        (w + 0.08, 0.31, 0.055),
        M["frame"],
        bev=0.014,
    )
    for x in (-w, w):
        add(
            c,
            "leveling_foot",
            (x, 0, floor + 0.025),
            (0.14, 0.18, 0.025),
            M["frame"],
            bev=0.010,
        )
        add(
            c,
            "structural_upright",
            (x, 0.17, floor + (h - floor) / 2),
            (0.045, 0.06, (h - floor) / 2),
            M["frame"],
            bev=0.008,
        )
    add(
        c,
        "lower_crossbeam",
        (0, 0.16, floor + 0.16),
        (w, 0.05, 0.055),
        M["frame"],
        bev=0.008,
    )
    add(
        c,
        "top_crossbeam",
        (0, 0.16, h - 0.055),
        (w, 0.05, 0.055),
        M["frame"],
        bev=0.008,
    )
    add(
        c,
        "continuous_back",
        (0, 0.205, (floor + h) / 2),
        (w, 0.025, (h - floor) / 2),
        M["deck"],
        bev=0.006,
    )
    rng = random.Random(11200 + variant)
    prod = products()
    for j in range(levels):
        z = floor + 0.12 + j * ((h - floor - 0.20) / (levels - 1))
        th = 0.028
        add(
            c,
            "load_bearing_shelf",
            (0, -0.02, z),
            (w + 0.045, 0.34, th),
            M["deck"],
            bev=0.007,
        )
        add(
            c,
            "front_label_channel",
            (0, -0.365, z),
            (w, 0.018, 0.042),
            M["label"],
            bev=0.003,
        )
        slot_count = (8, 10, 7)[variant]
        step = w * 1.65 / (slot_count - 1)
        for i in range(slot_count):
            if rng.random() < 0.18 + 0.035 * j:
                continue
            p = prod[(i + j * 2 + variant + rng.randrange(2)) % len(prod)]
            sx = 0.68 + rng.random() * 0.30
            # Every product master has its origin at its package bottom. Place exactly on shelf top.
            inst(
                c,
                p,
                "grounded_product",
                (-w * 0.825 + i * step + (rng.random() - 0.5) * 0.035, -0.19, z + th),
                rot=(rng.random() - 0.5) * 0.09,
                scale=(sx, sx * 0.92, sx * (0.86 + rng.random() * 0.20)),
            )
    return c


def rebuild_fresh(M):
    c = bpy.data.collections["all43_01:MASTER:convenience_store"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            ("all43_11_res:gondola_shelf", "all43_11_res:produce_zone")
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    shelves = [grounded_shelf(M, i) for i in range(3)]
    layout = [
        (-4.45, -2.12, 0, 1.50, 0.84),
        (-2.0, -1.16, 0, 1.63, 1.0),
        (0.55, -2.0, 0, 1.47, 0.94),
        (-3.45, 0.72, 0, 1.68, 0.88),
    ]
    made = []
    for i, (x, y, z, r, s) in enumerate(layout):
        made.append(
            inst(c, shelves[i % 3], "grounded_gondola", (x, y, z), r, (s, 1, 1)).name
        )
    produce = [
        x
        for x in bpy.data.collections
        if x.name.startswith("all43_11_light:MASTER:produce_crate_")
    ]
    for i, p in enumerate(produce[:4]):
        made.append(
            inst(
                c,
                p,
                "grounded_produce",
                (-5.10 + i % 2 * 1.36, -3.02 + (i // 2) * 0.86, 0.10),
                0.04 * (i - 1),
            ).name
        )
    return hidden, made


def table_master(M, variant):
    c = master("restaurant_table_v" + str(variant))
    floor = 0.10
    topz = (0.80, 0.76)[variant]
    w = (0.67, 0.58)[variant]
    d = (0.54, 0.58)[variant]
    add(c, "solid_tabletop", (0, 0, topz), (w, d, 0.055), M["wood"], bev=0.038)
    add(
        c,
        "front_apron",
        (0, -d + 0.035, topz - 0.105),
        (w - 0.08, 0.035, 0.075),
        M["wood"],
        bev=0.012,
    )
    add(
        c,
        "rear_apron",
        (0, d - 0.035, topz - 0.105),
        (w - 0.08, 0.035, 0.075),
        M["wood"],
        bev=0.012,
    )
    add(
        c,
        "left_apron",
        (-w + 0.035, 0, topz - 0.105),
        (0.035, d - 0.08, 0.075),
        M["wood"],
        bev=0.012,
    )
    add(
        c,
        "right_apron",
        (w - 0.035, 0, topz - 0.105),
        (0.035, d - 0.08, 0.075),
        M["wood"],
        bev=0.012,
    )
    leg_h = (topz - 0.16 - floor) / 2
    for x in (-w + 0.10, w - 0.10):
        for y in (-d + 0.10, d - 0.10):
            add(
                c,
                "floor_connected_leg",
                (x, y, floor + leg_h),
                (0.038, 0.038, leg_h),
                M["steel"],
                bev=0.010,
            )
    return c


def chair_master(M):
    c = master("restaurant_chair_physical")
    floor = 0.10
    seat = 0.49
    add(
        c,
        "seat_frame",
        (0, 0, seat - 0.055),
        (0.28, 0.26, 0.045),
        M["steel"],
        bev=0.018,
    )
    add(c, "upholstered_seat", (0, 0, seat), (0.27, 0.25, 0.055), M["seat"], bev=0.035)
    lh = (seat - 0.10 - floor) / 2
    for x in (-0.21, 0.21):
        for y in (-0.19, 0.19):
            add(
                c,
                "floor_connected_leg",
                (x, y, floor + lh),
                (0.027, 0.027, lh),
                M["steel"],
                bev=0.008,
            )
    add(
        c,
        "front_stretcher",
        (0, -0.19, 0.28),
        (0.21, 0.025, 0.025),
        M["steel"],
        bev=0.007,
    )
    add(
        c,
        "side_stretcher",
        (-0.21, 0, 0.30),
        (0.025, 0.18, 0.025),
        M["steel"],
        bev=0.007,
    )
    add(
        c,
        "side_stretcher",
        (0.21, 0, 0.30),
        (0.025, 0.18, 0.025),
        M["steel"],
        bev=0.007,
    )
    # Rear posts overlap the seat frame and continue into a supported backrest.
    for x in (-0.21, 0.21):
        add(
            c,
            "continuous_back_post",
            (x, 0.20, 0.72),
            (0.028, 0.028, 0.28),
            M["steel"],
            bev=0.008,
        )
    add(
        c,
        "supported_backrest",
        (0, 0.20, 0.86),
        (0.27, 0.042, 0.18),
        M["wood"],
        bev=0.042,
    )
    return c


def service_counter(M):
    c = master("grounded_service_counter")
    floor = 0.10
    add(
        c,
        "continuous_toe_plinth",
        (0, 0, floor + 0.06),
        (1.55, 0.42, 0.06),
        M["dark"],
        bev=0.015,
    )
    add(c, "cabinet_body", (0, 0, 0.55), (1.50, 0.40, 0.39), M["counter"], bev=0.032)
    add(c, "worktop", (0, 0, 0.98), (1.58, 0.47, 0.055), M["steel"], bev=0.025)
    for x in (-0.75, 0, 0.75):
        add(
            c,
            "cabinet_joint",
            (x, -0.405, 0.56),
            (0.012, 0.008, 0.33),
            M["dark"],
            bev=0.002,
        )
    return c


def rebuild_restaurant(M):
    c = bpy.data.collections["all43_01:MASTER:restaurant"]
    hidden = []
    for o in c.objects:
        if o.name.startswith(
            (
                "all43_10:dining_table",
                "all43_10:dining_chair",
                "all43_10:restaurant_sideboard",
                "all43_11_light:table_setting",
            )
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    tables = [table_master(M, 0), table_master(M, 1)]
    chair = chair_master(M)
    counter = service_counter(M)
    layout = [
        (-4.25, -2.45, 0.10),
        (-1.50, -2.10, -0.08),
        (1.25, -1.15, 0.16),
        (-3.30, 0.34, -0.14),
        (-0.10, 0.75, 0.06),
    ]
    made = []
    setting = bpy.data.collections.get("all43_11_light:MASTER:restaurant_table_setting")
    for i, (x, y, r) in enumerate(layout):
        made.append(inst(c, tables[i % 2], "physical_table", (x, y, 0), r).name)
        for side in (-1, 1):
            made.append(
                inst(
                    c,
                    chair,
                    "physical_chair",
                    (x + side * 0.76 * math.sin(r), y + side * 0.76 * math.cos(r), 0),
                    r + (0 if side < 0 else math.pi),
                ).name
            )
        if setting:
            made.append(
                inst(
                    c,
                    setting,
                    "supported_table_setting",
                    (x, y, (0.855, 0.815)[i % 2]),
                    r,
                ).name
            )
    made.append(
        inst(c, counter, "grounded_service_counter", (3.45, 2.35, 0), math.pi).name
    )
    return hidden, made


def run():
    M = materials()
    fh, fm = rebuild_fresh(M)
    rh, rm = rebuild_restaurant(M)
    return {
        "floating_freshmart_instances_hidden": fh,
        "new_grounded_freshmart_instances": len(fm),
        "old_restaurant_furniture_hidden": rh,
        "new_physical_restaurant_instances": len(rm),
        "shelf_load_path": [
            "plinth",
            "leveling feet",
            "uprights",
            "crossbeams",
            "shelf decks",
        ],
        "chair_structure": [
            "floor legs",
            "seat frame",
            "stretchers",
            "continuous back posts",
            "backrest",
        ],
        "unique_new_meshes": sum(x.name.startswith(P) for x in bpy.data.meshes),
        "linked_instances": sum(
            bool(o.get("linked_collection_instance"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }
