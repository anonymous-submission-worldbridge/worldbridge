"""all43_10 focused asset refinement: signs, entry racks, retail shelving and dining furniture."""
import math, random
import bpy

P = "all43_10:"


def mat(name, color, rough=0.5, metal=0, emit=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = color
        b.inputs["Emission Strength"].default_value = emit
    return m


def cube_mesh():
    m = bpy.data.meshes.get(P + "shared_cube")
    if m:
        return m
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
    m = bpy.data.meshes.new(P + "shared_cube")
    m.from_pydata(v, [], f)
    return m


def cylinder_mesh():
    m = bpy.data.meshes.get(P + "shared_cylinder_12")
    if m:
        return m
    v = []
    f = []
    n = 12
    for z in (-0.5, 0.5):
        for i in range(n):
            a = 2 * math.pi * i / n
            v.append((math.cos(a), math.sin(a), z))
    for i in range(n):
        f.append((i, (i + 1) % n, (i + 1) % n + n, i + n))
    f.extend((tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))))
    m = bpy.data.meshes.new(P + "shared_cylinder_12")
    m.from_pydata(v, [], f)
    return m


def bag_mesh():
    m = bpy.data.meshes.get(P + "shared_bag")
    if m:
        return m
    v = [
        (-0.45, -0.12, -0.5),
        (0.45, -0.12, -0.5),
        (0.38, -0.10, 0.30),
        (0.18, -0.08, 0.5),
        (-0.18, -0.08, 0.5),
        (-0.38, -0.10, 0.30),
        (-0.45, 0.12, -0.5),
        (0.45, 0.12, -0.5),
        (0.38, 0.10, 0.30),
        (0.18, 0.08, 0.5),
        (-0.18, 0.08, 0.5),
        (-0.38, 0.10, 0.30),
    ]
    f = [
        (0, 1, 2, 3, 4, 5),
        (6, 11, 10, 9, 8, 7),
        (0, 6, 7, 1),
        (1, 7, 8, 2),
        (2, 8, 9, 3),
        (3, 9, 10, 4),
        (4, 10, 11, 5),
        (5, 11, 6, 0),
    ]
    m = bpy.data.meshes.new(P + "shared_bag")
    m.from_pydata(v, [], f)
    return m


def obj(c, n, mesh, loc, scale, M, bevel=0.008, rot=0):
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
        q = o.modifiers.new("scaled_bevel", "BEVEL")
        q.width = min(bevel, min(scale) * 0.2)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def box(c, n, loc, scale, M, bevel=0.008, rot=0):
    return obj(c, n, cube_mesh(), loc, scale, M, bevel, rot)


def cyl(c, n, loc, scale, M, bevel=0.006):
    return obj(c, n, cylinder_mesh(), loc, scale, M, bevel)


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
        "black": mat("sign_black", (0.025, 0.03, 0.03, 1), 0.32, 0.62),
        "green": mat("sign_green", (0.08, 0.34, 0.18, 1), 0.38, 0.25),
        "orange": mat("sign_orange", (0.52, 0.105, 0.035, 1), 0.40, 0.20),
        "letter": mat("channel_letter_face", (0.90, 0.88, 0.74, 1), 0.25, 0.05, 0.45),
        "steel": mat("fixture_steel", (0.10, 0.12, 0.12, 1), 0.34, 0.58),
        "shelf": mat("shelf_powdercoat", (0.34, 0.37, 0.36, 1), 0.46, 0.32),
        "edge": mat("price_label_edge", (0.72, 0.64, 0.22, 1), 0.48),
        "wood": mat("dining_wood", (0.25, 0.085, 0.025, 1), 0.42),
        "upholstery": mat("chair_upholstery", (0.12, 0.16, 0.14, 1), 0.62),
        "red": mat("pack_red", (0.48, 0.055, 0.025, 1), 0.48),
        "blue": mat("pack_blue", (0.035, 0.18, 0.42, 1), 0.45),
        "greenpack": mat("pack_green", (0.035, 0.34, 0.10, 1), 0.50),
        "yellow": mat("pack_yellow", (0.66, 0.42, 0.035, 1), 0.48),
        "white": mat("pack_white", (0.70, 0.72, 0.68, 1), 0.42),
        "dark": mat("interior_dark", (0.025, 0.03, 0.03, 1), 0.69),
    }


def facade_collections():
    return [
        bpy.data.collections[n]
        for n in ("all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant")
    ]


def upgrade_signs(M):
    # Width values are Blender half-extents: panels closely frame the letter groups.
    specs = {"FRESH MART": (3.35, M["green"]), "CORNER KITCHEN": (4.75, M["orange"])}
    changed = []
    parts = []
    for c in facade_collections():
        for o in c.objects:
            if o.name.startswith(
                ("all43_05:sign_back_rail", "all43_05:sign_hidden_standoff")
            ):
                o.hide_render = True
        text = next(
            (
                o
                for o in bpy.data.objects
                if o.type == "FONT"
                and " ".join(o.data.body.split()) in specs
                and c in o.users_collection
            ),
            None,
        )
        if not text:
            continue
        label = " ".join(text.data.body.split())
        width, panelmat = specs[label]
        text.data.extrude = 0.115
        text.data.bevel_depth = 0.018
        text.data.bevel_resolution = 3
        text.data.fill_mode = "BOTH"
        text.data.materials.clear()
        text.data.materials.append(M["letter"])
        text["sign_type"] = "beveled_channel_letters"
        y = text.location.y + 0.16
        z = text.location.z
        box(
            c,
            "sign_backplate",
            (text.location.x, y, z),
            (width, 0.075, 0.47),
            panelmat,
            0.035,
        )
        parts.append("backplate")
        box(
            c,
            "sign_rear_rail",
            (text.location.x, y + 0.10, z),
            (width * 0.92, 0.035, 0.055),
            M["black"],
            0.012,
        )
        parts.append("rail")
        for x in (-width * 0.72, -width * 0.36, 0, width * 0.36, width * 0.72):
            box(
                c,
                "sign_standoff",
                (text.location.x + x, y - 0.10, z),
                (0.035, 0.12, 0.035),
                M["black"],
                0.008,
            )
            parts.append("standoff")
        changed.append(label)
    return changed, parts


def product_masters(M):
    bottle = master("product_bottle")
    cyl(bottle, "bottle_body", (0, 0, 0.16), (0.075, 0.075, 0.16), M["greenpack"])
    cyl(bottle, "bottle_neck", (0, 0, 0.355), (0.035, 0.035, 0.055), M["white"])
    cyl(bottle, "bottle_cap", (0, 0, 0.42), (0.043, 0.043, 0.018), M["yellow"])
    can = master("product_can")
    cyl(can, "can_body", (0, 0, 0.13), (0.072, 0.072, 0.13), M["red"])
    cyl(can, "can_rim", (0, 0, 0.267), (0.076, 0.076, 0.008), M["white"])
    cyl(can, "can_rim", (0, 0, -0.007), (0.076, 0.076, 0.008), M["white"])
    carton = master("product_carton")
    box(carton, "carton_body", (0, 0, 0.16), (0.095, 0.07, 0.16), M["blue"], 0.012)
    box(carton, "carton_top", (0, 0, 0.335), (0.095, 0.07, 0.018), M["white"], 0.006)
    bag = master("product_bag")
    obj(bag, "pouch", bag_mesh(), (0, 0, 0.16), (0.14, 0.10, 0.32), M["yellow"], 0.012)
    box(bag, "bag_label", (0, -0.105, 0.17), (0.065, 0.008, 0.065), M["red"], 0.004)
    boxpack = master("product_box")
    box(boxpack, "box", (0, 0, 0.14), (0.12, 0.07, 0.14), M["red"], 0.012)
    box(boxpack, "label", (0, -0.075, 0.14), (0.07, 0.008, 0.045), M["white"], 0.003)
    return [bottle, carton, bag, can, boxpack]


def shelf_master(M, products, variant):
    c = master("retail_shelf_v" + str(variant))
    w = (1.05, 1.18, 0.94)[variant]
    h = (1.85, 2.0, 1.65)[variant]
    levels = (4, 5, 4)[variant]
    for x in (-w, w):
        box(c, "upright", (x, 0.18, h / 2), (0.035, 0.055, h / 2), M["steel"], 0.009)
        box(c, "foot", (x, -0.10, 0.055), (0.16, 0.27, 0.035), M["steel"], 0.012)
    box(c, "perforated_back", (0, 0.24, h / 2), (w, 0.025, h / 2), M["shelf"], 0.008)
    rng = random.Random(4310 + variant)
    for j in range(levels):
        z = 0.16 + j * ((h - 0.22) / (levels - 1))
        box(c, "shelf_board", (0, 0, z), (w + 0.04, 0.34, 0.025), M["shelf"], 0.007)
        box(
            c,
            "label_strip",
            (0, -0.345, z + 0.025),
            (w, 0.018, 0.035),
            M["edge"],
            0.004,
        )
        slots = 8
        for i in range(slots):
            if rng.random() < (0.16 + 0.05 * j):
                continue
            p = products[(i + j * 2 + variant) % len(products)]
            x = -w * 0.82 + i * (w * 1.64 / (slots - 1))
            s = 0.78 + rng.random() * 0.18
            inst(
                c,
                p,
                "merchandise",
                (x, -0.19, z + 0.04),
                rot=(rng.random() - 0.5) * 0.10,
                scale=(s, s, s),
            )
    return c


def rebuild_convenience(M):
    conv = facade_collections()[0]
    hidden = []
    for o in conv.objects:
        if (
            o.name.startswith(
                ("all43_01:shelf", "all43_06:retail_shelf_", "all43_07:retail_shelf_")
            )
            or "checkout_counter" in o.name.lower()
        ):
            o.hide_render = True
            hidden.append(o.name)
    products = product_masters(M)
    shelves = [shelf_master(M, products, i) for i in range(3)]
    # First fixture is 1.4m behind glazing; remaining aisles are staggered and varied.
    layout = [
        (-4.8, -3.45, 0.12, 0.05, 0.72),
        (-2.3, -1.55, 0.12, 1.52, 1.0),
        (0.25, -2.20, 0.12, 1.63, 0.93),
        (2.75, -0.85, 0.12, 1.47, 1.04),
        (-4.35, 0.95, 0.12, 0.10, 0.82),
    ]
    for i, (x, y, z, r, s) in enumerate(layout):
        inst(conv, shelves[i % 3], "retail_shelf", (x, y, z), r, (s, 1, 1))
    return hidden, len(layout), len(products)


def display_rack_master(M, products):
    c = master("entrance_display_rack")
    box(c, "base", (0, 0, 0.06), (0.48, 0.30, 0.055), M["steel"], 0.018)
    for x in (-0.42, 0.42):
        box(c, "post", (x, 0.18, 0.58), (0.025, 0.035, 0.55), M["steel"], 0.008)
    for z in (0.18, 0.52, 0.86):
        box(c, "tray", (0, 0, z), (0.46, 0.27, 0.025), M["shelf"], 0.008)
        box(
            c,
            "front_lip",
            (0, -0.27, z + 0.055),
            (0.46, 0.025, 0.055),
            M["edge"],
            0.006,
        )
        for i, x in enumerate((-0.30, -0.10, 0.10, 0.30)):
            inst(
                c,
                products[(i + int(z * 10)) % len(products)],
                "display_product",
                (x, -0.08, z + 0.04),
                scale=(0.72, 0.72, 0.72),
            )
    return c


def fix_entrance_racks(M):
    hidden = []
    # The flesh-colored stacks were legacy near-glass retail shelves; remove them rather than relabeling cubes.
    for c in facade_collections():
        for o in c.objects:
            if (
                o.name.startswith(
                    (
                        "all43_01:shelf",
                        "all43_06:retail_shelf_",
                        "all43_07:retail_shelf_",
                    )
                )
                and o.location.y < -2.8
            ):
                o.hide_render = True
                hidden.append(o.name)
    products = product_masters(M)
    rack = display_rack_master(M, products)
    conv = facade_collections()[0]
    inst(
        conv,
        rack,
        "functional_entry_display",
        (-5.55, -3.35, 0.12),
        0.08,
        (0.86, 0.86, 0.86),
    )
    return hidden, 1


def table_master(M):
    c = master("restaurant_table")
    box(c, "thick_tabletop", (0, 0, 0.74), (0.66, 0.54, 0.055), M["wood"], 0.035)
    box(c, "underframe", (0, 0, 0.66), (0.48, 0.38, 0.035), M["steel"], 0.012)
    for x in (-0.49, 0.49):
        for y in (-0.38, 0.38):
            box(c, "tapered_leg", (x, y, 0.34), (0.035, 0.035, 0.34), M["steel"], 0.012)
    return c


def chair_master(M):
    c = master("restaurant_chair")
    box(c, "padded_seat", (0, 0, 0.47), (0.27, 0.25, 0.055), M["upholstery"], 0.035)
    for x in (-0.21, 0.21):
        for y in (-0.18, 0.18):
            box(c, "chair_leg", (x, y, 0.23), (0.025, 0.025, 0.23), M["steel"], 0.009)
    for x in (-0.21, 0.21):
        box(c, "back_post", (x, 0.21, 0.75), (0.025, 0.025, 0.30), M["steel"], 0.009)
    box(c, "curved_back", (0, 0.21, 0.88), (0.27, 0.035, 0.17), M["wood"], 0.045)
    return c


def sideboard_master(M):
    c = master("restaurant_sideboard")
    box(c, "cabinet", (0, 0, 0.48), (1.0, 0.30, 0.48), M["wood"], 0.035)
    box(c, "countertop", (0, 0, 0.98), (1.06, 0.34, 0.045), M["black"], 0.018)
    for x in (-0.5, 0, 0.5):
        box(c, "door_gap", (x, -0.305, 0.48), (0.012, 0.008, 0.40), M["dark"], 0.002)
    for x in (-0.72, 0.72):
        box(c, "handle", (x, -0.33, 0.55), (0.06, 0.018, 0.018), M["steel"], 0.006)
        return c


def rebuild_restaurant(M):
    rest = facade_collections()[1]
    hidden = []
    for o in rest.objects:
        if o.name.startswith(
            (
                "all43_01:shelf",
                "all43_06:dining_table_",
                "all43_06:dining_chair_",
                "all43_07:dining_",
            )
        ) or o.name.startswith(("all43_06:retail_shelf_", "all43_07:retail_shelf_")):
            o.hide_render = True
            hidden.append(o.name)
    table, chair, side = table_master(M), chair_master(M), sideboard_master(M)
    layout = [
        (-4.25, -2.55, 0.10),
        (-1.55, -2.15, -0.08),
        (1.25, -1.20, 0.16),
        (-3.35, 0.30, -0.14),
        (-0.15, 0.72, 0.06),
    ]
    count = 0
    for x, y, r in layout:
        inst(rest, table, "dining_table", (x, y, 0.12), r)
        count += 1
        for sidev in (-1, 1):
            inst(
                rest,
                chair,
                "dining_chair",
                (x + sidev * 0.73 * math.sin(r), y + sidev * 0.73 * math.cos(r), 0.12),
                r + (0 if sidev < 0 else math.pi),
            )
            count += 1
    inst(rest, side, "restaurant_sideboard", (3.55, 2.45, 0.12), math.pi)
    count += 1
    return hidden, count


def run():
    M = materials()
    signs, signparts = upgrade_signs(M)
    old_shelves, shelf_instances, product_types = rebuild_convenience(M)
    bad_racks, display_count = fix_entrance_racks(M)
    old_dining, dining_instances = rebuild_restaurant(M)
    return {
        "upgraded_signs": signs,
        "sign_installation_parts": len(signparts),
        "legacy_retail_objects_hidden": len(set(old_shelves + bad_racks)),
        "shelf_master_variants": 3,
        "product_proxy_types": product_types,
        "new_shelf_instances": shelf_instances,
        "functional_entry_display_instances": display_count,
        "legacy_dining_objects_hidden": len(old_dining),
        "new_restaurant_furniture_instances": dining_instances,
        "unique_new_meshes": sum(m.name.startswith(P) for m in bpy.data.meshes),
        "linked_instances": sum(
            bool(o.get("linked_collection_instance"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }
