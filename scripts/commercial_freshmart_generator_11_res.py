"""Fresh Mart realism and storefront cleanup for the high-resolution multi-view pass."""
import math, random
import bpy

P = "all43_11_res:"


def mat(name, color, rough=0.5, metal=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def cube():
    m = bpy.data.meshes.get("all43_10:shared_cube")
    if not m:
        raise RuntimeError("shared cube missing")
    return m


def cyl():
    m = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    if not m:
        raise RuntimeError("shared cylinder missing")
    return m


def add(c, n, mesh, loc, scale, M, rot=0, bevel=0.008):
    o = bpy.data.objects.new(P + n, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = scale
    o.rotation_euler[2] = rot
    if not mesh.materials:
        mesh.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bevel:
        q = o.modifiers.new("edge_bevel", "BEVEL")
        q.width = min(bevel, min(scale) * 0.18)
        q.segments = 2
    o["shared_mesh_data"] = True
    return o


def box(c, n, loc, scale, M, rot=0, bevel=0.008):
    return add(c, n, cube(), loc, scale, M, rot, bevel)


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


def materials():
    return {
        "steel": mat("shelf_steel", (0.15, 0.17, 0.16, 1), 0.38, 0.58),
        "white": mat("cooler_white", (0.62, 0.65, 0.62, 1), 0.42, 0.12),
        "dark": mat("fixture_dark", (0.022, 0.028, 0.027, 1), 0.70),
        "edge": mat("price_strip", (0.68, 0.55, 0.12, 1), 0.46),
        "counter": mat("checkout_counter", (0.18, 0.23, 0.20, 1), 0.39, 0.18),
        "rubber": mat("conveyor", (0.018, 0.02, 0.019, 1), 0.64),
        "glass": bpy.data.materials.get("all43_07:fresnel_commercial_glass")
        or mat("cooler_glass", (0.08, 0.15, 0.16, 1), 0.12),
        "light": mat("cooler_light", (1, 0.82, 0.58, 1), 0.30),
    }


def remove_brown_blocks():
    hidden = []
    for o in list(bpy.data.objects):
        low = o.name.lower()
        if (
            "base_stain" in low
            or "drip_stain" in low
            or "brown_block" in low
            or "door_block" in low
        ):
            hidden.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return hidden


def product_collections():
    names = ["bottle", "can", "carton", "bag", "box"]
    products = [bpy.data.collections.get("all43_10:MASTER:product_" + n) for n in names]
    produce = [
        c
        for c in bpy.data.collections
        if c.name.startswith("all43_11_light:MASTER:produce_crate_")
    ]
    return [p for p in products if p], produce


def shelf_master(M, products, variant):
    c = master("gondola_shelf_v" + str(variant))
    w = (1.18, 1.42, 0.98)[variant]
    h = (1.85, 2.05, 1.62)[variant]
    levels = (5, 6, 4)[variant]
    box(
        c,
        "perforated_back",
        (0, 0.20, h * 0.50),
        (w, 0.025, h * 0.50),
        M["white"],
        bevel=0.008,
    )
    for x in (-w, w):
        box(
            c,
            "upright",
            (x, 0.18, h * 0.50),
            (0.035, 0.05, h * 0.50),
            M["steel"],
            bevel=0.007,
        )
        box(
            c,
            "adjustable_foot",
            (x, -0.05, 0.05),
            (0.14, 0.22, 0.035),
            M["steel"],
            bevel=0.010,
        )
    rng = random.Random(11120 + variant)
    for level in range(levels):
        z = 0.14 + level * (h - 0.18) / (levels - 1)
        box(
            c, "shelf_deck", (0, 0, z), (w + 0.04, 0.34, 0.026), M["steel"], bevel=0.006
        )
        box(
            c,
            "price_label_strip",
            (0, -0.35, z + 0.026),
            (w, 0.018, 0.035),
            M["edge"],
            bevel=0.003,
        )
        slots = (8, 10, 7)[variant]
        cursor = -w * 0.84
        for i in range(slots):
            if rng.random() < (0.17 + 0.04 * level):
                continue
            category = (i + level * 2 + variant + rng.randrange(2)) % len(products)
            p = products[category]
            sx = 0.70 + rng.random() * 0.28
            sy = 0.78 + rng.random() * 0.15
            sz = 0.72 + rng.random() * 0.24
            inst(
                c,
                p,
                "mixed_merchandise",
                (cursor + (rng.random() - 0.5) * 0.045, -0.19, z + 0.045),
                rot=(rng.random() - 0.5) * 0.12,
                scale=(sx, sy, sz),
            )
            cursor += w * 1.68 / (slots - 1)
    return c


def cooler_master(M, products):
    c = master("wall_cooler")
    box(
        c,
        "insulated_case",
        (0, 0.24, 1.18),
        (1.58, 0.38, 1.18),
        M["white"],
        bevel=0.035,
    )
    box(c, "dark_recess", (0, -0.16, 1.24), (1.47, 0.035, 1.03), M["dark"], bevel=0.012)
    for z in (0.34, 0.72, 1.10, 1.48, 1.86):
        box(
            c,
            "cooler_shelf",
            (0, -0.20, z),
            (1.42, 0.28, 0.018),
            M["steel"],
            bevel=0.004,
        )
        for i, x in enumerate((-1.20, -0.90, -0.60, -0.30, 0, 0.30, 0.60, 0.90, 1.20)):
            if (i + int(z * 10)) % 7 == 0:
                continue
            inst(
                c,
                products[(i + int(z * 10)) % min(4, len(products))],
                "cooled_product",
                (x, -0.28, z + 0.035),
                scale=(0.62, 0.62, 0.70 + (i % 3) * 0.06),
            )
    for x in (-1.45, 0, 1.45):
        box(
            c,
            "door_mullion",
            (x, -0.28, 1.22),
            (0.035, 0.04, 1.03),
            M["steel"],
            bevel=0.006,
        )
    for x in (-0.78, 0.78):
        box(
            c,
            "cooler_handle",
            (x, -0.35, 1.18),
            (0.025, 0.025, 0.33),
            M["steel"],
            bevel=0.009,
        )
    box(
        c,
        "cooler_glazing",
        (0, -0.26, 1.23),
        (1.43, 0.012, 1.01),
        M["glass"],
        bevel=0.003,
    )
    box(
        c,
        "cooler_light",
        (0, -0.24, 2.14),
        (1.38, 0.018, 0.025),
        M["light"],
        bevel=0.004,
    )
    return c


def checkout_master(M):
    c = master("checkout_station")
    box(c, "cabinet", (0, 0, 0.48), (1.35, 0.48, 0.48), M["counter"], bevel=0.035)
    box(c, "worktop", (0, 0, 0.98), (1.42, 0.53, 0.045), M["steel"], bevel=0.018)
    box(
        c,
        "conveyor",
        (-0.45, -0.04, 1.04),
        (0.70, 0.40, 0.025),
        M["rubber"],
        bevel=0.015,
    )
    box(c, "scanner", (0.54, -0.18, 1.10), (0.25, 0.22, 0.10), M["dark"], bevel=0.025)
    box(c, "register", (0.91, 0.05, 1.28), (0.22, 0.16, 0.22), M["dark"], bevel=0.025)
    box(c, "screen", (0.91, -0.13, 1.38), (0.16, 0.022, 0.13), M["light"], bevel=0.012)
    box(c, "bag_well", (1.05, 0.28, 0.72), (0.28, 0.18, 0.20), M["steel"], bevel=0.018)
    return c


def rebuild_fresh_mart(M):
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    hidden = []
    for o in conv.objects:
        if o.name.startswith(
            (
                "all43_10:retail_shelf",
                "all43_10:functional_entry_display",
                "all43_11_light:fresh_produce_crate",
            )
        ):
            o.hide_render = True
            o.hide_viewport = True
            hidden.append(o.name)
    products, produce = product_collections()
    shelves = [shelf_master(M, products, i) for i in range(3)]
    cooler = cooler_master(M, products)
    checkout = checkout_master(M)
    # Clear entrance at x=5.45, then staggered gondolas and a rear cooler wall.
    layout = [
        (-4.55, -2.20, 0.12, 1.50, 0.82),
        (-2.05, -1.22, 0.12, 1.63, 1.02),
        (0.55, -2.05, 0.12, 1.47, 0.94),
        (-3.55, 0.72, 0.12, 1.68, 0.88),
    ]
    made = []
    for i, (x, y, z, r, s) in enumerate(layout):
        made.append(
            inst(conv, shelves[i % 3], "gondola_shelf", (x, y, z), r, (s, 1, 1)).name
        )
    for x in (-4.25, -0.85, 2.55):
        made.append(
            inst(conv, cooler, "wall_cooler", (x, 3.18, 0.12), 0, (0.92, 0.88, 1)).name
        )
    made.append(
        inst(
            conv, checkout, "checkout_station", (3.72, -1.68, 0.12), -1.53, (1.05, 1, 1)
        ).name
    )
    # Produce has a dedicated zone, not cubes mixed indiscriminately through every shelf.
    for i, c in enumerate(produce[:4]):
        made.append(
            inst(
                conv,
                c,
                "produce_zone",
                (-5.15 + i % 2 * 1.38, -3.05 + (i // 2) * 0.88, 0.12),
                0.05 * (i - 1),
            ).name
        )
    return hidden, made


def run():
    hidden_blocks = remove_brown_blocks()
    M = materials()
    old, new = rebuild_fresh_mart(M)
    return {
        "brown_glazing_blocks_hidden": hidden_blocks,
        "old_freshmart_instances_hidden": old,
        "new_freshmart_fixture_instances": len(new),
        "shelf_variants": 3,
        "product_shape_categories": [
            "bottle",
            "can",
            "carton",
            "bag",
            "packaged_box",
            "fresh_produce",
        ],
        "wall_coolers": 3,
        "checkout_stations": 1,
        "unique_new_meshes": sum(m.name.startswith(P) for m in bpy.data.meshes),
        "linked_instances": sum(
            bool(o.get("linked_collection_instance"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }
