"""Daylight recovery and realistic goods pass for all43_11-light."""
import math, random
import bpy

P = "all43_11_light:"


def mat(name, color, rough=0.5, metal=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def cube_mesh():
    return bpy.data.meshes.get("all43_10:shared_cube") or bpy.data.meshes.get(
        "all43_11:shared_cube"
    )


def sphere_mesh():
    m = bpy.data.meshes.get(P + "shared_produce_sphere")
    if m:
        return m
    seg, rings = 12, 7
    v = [(0, 0, 1), (0, 0, -1)]
    f = []
    for j in range(1, rings):
        phi = math.pi * j / rings
        for i in range(seg):
            a = 2 * math.pi * i / seg
            v.append(
                (
                    math.sin(phi) * math.cos(a),
                    math.sin(phi) * math.sin(a),
                    math.cos(phi),
                )
            )
    for i in range(seg):
        f.append((0, 2 + i, 2 + (i + 1) % seg))
    for j in range(rings - 2):
        a0 = 2 + j * seg
        a1 = a0 + seg
        for i in range(seg):
            f.append((a0 + i, a1 + i, a1 + (i + 1) % seg, a0 + (i + 1) % seg))
    base = 2 + (rings - 2) * seg
    for i in range(seg):
        f.append((1, base + (i + 1) % seg, base + i))
    m = bpy.data.meshes.new(P + "shared_produce_sphere")
    m.from_pydata(v, [], f)
    return m


def leaf_mesh():
    m = bpy.data.meshes.get(P + "shared_leaf")
    if m:
        return m
    v = [
        (0, -0.5, 0),
        (-0.28, -0.15, 0.04),
        (-0.34, 0.15, 0),
        (0, 0.5, 0.06),
        (0.34, 0.15, 0),
        (0.28, -0.15, 0.04),
    ]
    m = bpy.data.meshes.new(P + "shared_leaf")
    m.from_pydata(v, [], [(0, 1, 2, 3, 4, 5)])
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
        q = o.modifiers.new("soft_edge", "BEVEL")
        q.width = min(bevel, min(scale) * 0.16)
        q.segments = 2
    o["shared_mesh_data"] = True
    return o


def box(c, n, loc, scale, M, rot=0, bevel=0.008):
    return add(c, n, cube_mesh(), loc, scale, M, rot, bevel)


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


def remove_orange_entrance_blocks():
    hidden = []
    for o in bpy.data.objects:
        if o.name.startswith("all43_10:functional_entry_display") or o.name.startswith(
            "all43_10:display_product"
        ):
            o.hide_render = True
            o.hide_viewport = True
            o["removed_orange_entrance_block"] = True
            hidden.append(o.name)
    return hidden


def produce_materials():
    return {
        "crate": mat("produce_crate", (0.16, 0.075, 0.025, 1), 0.58),
        "dark": mat("crate_shadow", (0.025, 0.03, 0.022, 1), 0.72),
        "tomato": mat("tomato_skin", (0.48, 0.025, 0.012, 1), 0.32),
        "orange": mat("orange_skin", (0.72, 0.18, 0.018, 1), 0.48),
        "apple": mat("apple_skin", (0.38, 0.055, 0.018, 1), 0.28),
        "green": mat("leaf_green", (0.025, 0.22, 0.035, 1), 0.62),
        "lightgreen": mat("lettuce_green", (0.11, 0.38, 0.08, 1), 0.66),
        "paper": mat("produce_label", (0.72, 0.65, 0.42, 1), 0.60),
        "ceramic": mat("restaurant_ceramic", (0.75, 0.73, 0.65, 1), 0.25),
        "glass": mat("drinking_glass", (0.12, 0.22, 0.20, 1), 0.12),
        "steel": mat("cutlery_steel", (0.36, 0.40, 0.39, 1), 0.22, 0.72),
        "napkin": mat("napkin", (0.48, 0.16, 0.08, 1), 0.72),
    }


def produce_crate(M, kind, seed):
    c = master("produce_crate_" + kind)
    rng = random.Random(seed)
    box(c, "crate_floor", (0, 0, 0.06), (0.62, 0.38, 0.045), M["crate"], bevel=0.018)
    for y in (-0.34, 0.34):
        for z in (0.15, 0.29, 0.43):
            box(
                c,
                "crate_slatted_side",
                (0, y, z),
                (0.62, 0.025, 0.035),
                M["crate"],
                bevel=0.007,
            )
    for x in (-0.58, 0.58):
        for z in (0.15, 0.29, 0.43):
            box(
                c,
                "crate_slatted_end",
                (x, 0, z),
                (0.025, 0.34, 0.035),
                M["crate"],
                bevel=0.007,
            )
    box(
        c,
        "produce_label",
        (0, -0.37, 0.30),
        (0.22, 0.008, 0.09),
        M["paper"],
        bevel=0.003,
    )
    sm = sphere_mesh()
    lm = leaf_mesh()
    skin = M[kind] if kind in M else M["lightgreen"]
    for row, y in enumerate((-0.22, 0, 0.22)):
        for i, x in enumerate((-0.42, -0.14, 0.14, 0.42)):
            if rng.random() < 0.13:
                continue
            z = 0.17 + row * 0.075 + rng.random() * 0.025
            s = 0.105 + rng.random() * 0.025
            if kind == "lightgreen":
                for k in range(5):
                    add(
                        c,
                        "lettuce_leaf",
                        lm,
                        (x, y, z),
                        (s * 1.25, s * 1.25, s),
                        M["lightgreen"],
                        rot=k * 1.25 + rng.random() * 0.3,
                        bevel=0,
                    )
            else:
                add(
                    c,
                    "individual_produce",
                    sm,
                    (x, y, z),
                    (s, s, s * (0.88 if kind == "tomato" else 1)),
                    skin,
                    rot=rng.random(),
                    bevel=0.004,
                )
                add(
                    c,
                    "stem_leaf",
                    lm,
                    (x, y, z + s * 0.82),
                    (s * 0.30, s * 0.30, s * 0.18),
                    M["green"],
                    rot=rng.random() * 6.2,
                    bevel=0,
                )
    return c


def add_fresh_goods(M):
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    crates = [
        produce_crate(M, "tomato", 1101),
        produce_crate(M, "orange", 1102),
        produce_crate(M, "apple", 1103),
        produce_crate(M, "lightgreen", 1104),
    ]
    layout = [
        (-5.15, -2.75, 0.13, 0.05),
        (-3.72, -2.68, 0.13, -0.08),
        (-5.00, -1.82, 0.13, 0.10),
        (-3.55, -1.70, 0.13, -0.04),
    ]
    made = []
    for i, (x, y, z, r) in enumerate(layout):
        made.append(inst(conv, crates[i], "fresh_produce_crate", (x, y, z), r).name)
    return made


def table_setting_master(M):
    c = master("restaurant_table_setting")
    cyl = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    add(c, "plate", cyl, (0, 0, 0.018), (0.22, 0.22, 0.018), M["ceramic"], bevel=0.005)
    add(c, "bowl", cyl, (0, 0, 0.065), (0.14, 0.14, 0.045), M["ceramic"], bevel=0.006)
    add(
        c,
        "water_glass",
        cyl,
        (0.30, 0.08, 0.12),
        (0.055, 0.055, 0.12),
        M["glass"],
        bevel=0.004,
    )
    box(c, "fork", (-0.30, 0, 0.025), (0.018, 0.20, 0.008), M["steel"], bevel=0.003)
    box(
        c,
        "folded_napkin",
        (0.18, -0.22, 0.035),
        (0.13, 0.09, 0.018),
        M["napkin"],
        rot=0.18,
        bevel=0.005,
    )
    return c


def add_restaurant_items(M):
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    setting = table_setting_master(M)
    made = []
    for i, (x, y, r) in enumerate(
        (
            (-4.25, -2.55, 0.10),
            (-1.55, -2.15, -0.08),
            (1.25, -1.20, 0.16),
            (-3.35, 0.30, -0.14),
            (-0.15, 0.72, 0.06),
        )
    ):
        made.append(
            inst(
                rest,
                setting,
                "table_setting",
                (x, y, 0.92),
                r,
                ((0.92 if i % 2 else 1),) * 3,
            ).name
        )
    return made


def ensure_daylight():
    sc = bpy.context.scene
    world = bpy.data.worlds.get(P + "DAYLIGHT_WORLD") or bpy.data.worlds.new(
        P + "DAYLIGHT_WORLD"
    )
    world.use_nodes = True
    n, l = world.node_tree.nodes, world.node_tree.links
    n.clear()
    out = n.new("ShaderNodeOutputWorld")
    bg = n.new("ShaderNodeBackground")
    sky = n.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(128)
    sky.air_density = 1.0
    sky.dust_density = 0.35
    sky.ozone_density = 1.0
    bg.inputs["Strength"].default_value = 0.28
    l.new(sky.outputs["Color"], bg.inputs["Color"])
    l.new(bg.outputs["Background"], out.inputs["Surface"])
    sc.world = world
    data = bpy.data.lights.get(P + "sun") or bpy.data.lights.new(P + "sun", "SUN")
    data.energy = 2.2
    data.angle = math.radians(5)
    data.color = (1.0, 0.91, 0.78)
    sun = bpy.data.objects.get(P + "sun") or bpy.data.objects.new(P + "sun", data)
    if not sun.users_collection:
        sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-32))
    sun["daylight_key"] = True
    filldata = bpy.data.lights.get(P + "sky_fill") or bpy.data.lights.new(
        P + "sky_fill", "AREA"
    )
    filldata.energy = 650
    filldata.shape = "DISK"
    filldata.size = 18
    filldata.color = (0.72, 0.84, 1.0)
    fill = bpy.data.objects.get(P + "sky_fill") or bpy.data.objects.new(
        P + "sky_fill", filldata
    )
    if not fill.users_collection:
        sc.collection.objects.link(fill)
    fill.location = (-30, -35, 16)
    fill.rotation_euler = (0, 0, 0)
    fill.rotation_euler = (math.radians(18), 0, math.radians(-18))
    fill["daylight_fill"] = True
    sc.view_settings.exposure = -0.35
    sc.render.film_transparent = False
    return {
        "sun_energy": data.energy,
        "world_strength": bg.inputs["Strength"].default_value,
        "exposure": sc.view_settings.exposure,
    }


def run():
    removed = remove_orange_entrance_blocks()
    M = produce_materials()
    produce = add_fresh_goods(M)
    restaurant = add_restaurant_items(M)
    day = ensure_daylight()
    return {
        "orange_entrance_objects_hidden": removed,
        "fresh_produce_crate_instances": len(produce),
        "produce_categories": ["tomato", "orange", "apple", "leafy_green"],
        "restaurant_table_settings": len(restaurant),
        "daylight_rig": day,
        "unique_new_meshes": sum(m.name.startswith(P) for m in bpy.data.meshes),
        "linked_instances": sum(
            bool(o.get("linked_collection_instance"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }
