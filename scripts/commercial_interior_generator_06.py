"""Clean commercial entrances, transparent glazing, and instanced visible interiors."""
import math
import bpy

P = "all43_06:"


def mat(name, color, rough=0.5, metal=0, trans=0, emit=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["IOR"].default_value = 1.46
    if trans:
        b.inputs["Transmission Weight"].default_value = trans
        b.inputs["Alpha"].default_value = color[3]
    if emit:
        b.inputs["Emission Color"].default_value = color
        b.inputs["Emission Strength"].default_value = emit
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 8
    noise.inputs["Detail"].default_value = 2
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.035
    bump.inputs["Distance"].default_value = 0.01
    l.new(noise.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def materials():
    glass = mat("clear_commercial_glass", (0.055, 0.075, 0.072, 0.06), 0.025, trans=1.0)
    n = glass.node_tree.nodes
    l = glass.node_tree.links
    b = n.get("Principled BSDF")
    out = n.get("Material Output")
    for link in list(out.inputs["Surface"].links):
        l.remove(link)
    transparent = n.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (0.92, 0.97, 0.96, 1)
    mix = n.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.16
    l.new(transparent.outputs[0], mix.inputs[1])
    l.new(b.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    glass.surface_render_method = "DITHERED"
    return {
        "glass": glass,
        "metal": mat("interior_metal", (0.10, 0.12, 0.12, 1), 0.30, 0.58),
        "shelf": mat("shelf_paint", (0.68, 0.69, 0.66, 1), 0.52),
        "wood": mat("warm_wood", (0.24, 0.075, 0.025, 1), 0.55),
        "counter": mat("countertop", (0.15, 0.17, 0.16, 1), 0.35, 0.12),
        "freezer": mat("freezer_white", (0.72, 0.74, 0.72, 1), 0.38, 0.08),
        "dark": mat("interior_back", (0.035, 0.04, 0.038, 1), 0.70),
        "warm": mat("interior_light", (1, 0.68, 0.30, 1), 0.28, emit=3.0),
        "product_a": mat("product_green", (0.08, 0.30, 0.12, 1), 0.55),
        "product_b": mat("product_red", (0.42, 0.08, 0.035, 1), 0.55),
    }


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


def box(c, name, loc, size, material, bevel=0.01):
    o = bpy.data.objects.new(P + name, cube_mesh())
    c.objects.link(o)
    o.location = loc
    o.scale = size
    if not o.data.materials:
        o.data.materials.append(material)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = material
    if bevel:
        q = o.modifiers.new("edge_bevel", "BEVEL")
        q.width = min(bevel, min(size) * 0.1)
        q.segments = 2
    o["shared_mesh_data"] = True
    return o


def master(name):
    c = bpy.data.collections.new(P + "MASTER:" + name)
    c["interior_master"] = True
    return c


def instance(parent, m, name, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + name, None)
    parent.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = m
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def create_shelf_master(M):
    c = master("retail_shelf")
    box(c, "shelf_back", (0, 0.16, 1.0), (0.75, 0.04, 1.0), M["shelf"])
    for z in (0.12, 0.48, 0.84, 1.20, 1.56, 1.92):
        box(c, "shelf_board", (0, 0, z), (0.78, 0.30, 0.025), M["metal"], 0.004)
    for row, z in enumerate((0.27, 0.63, 0.99, 1.35, 1.71)):
        for x in (-0.52, -0.17, 0.18, 0.53):
            box(
                c,
                "product",
                (x, -0.12, z),
                (0.12, 0.12, 0.12),
                M["product_a"] if (row + int(x * 10)) % 2 else M["product_b"],
                0.012,
            )
    return c


def create_checkout_master(M):
    c = master("checkout")
    box(c, "checkout_body", (0, 0, 0.48), (1.15, 0.42, 0.48), M["counter"], 0.035)
    box(c, "checkout_top", (0, -0.02, 0.99), (1.22, 0.46, 0.045), M["metal"], 0.015)
    box(c, "register", (0.48, -0.18, 1.12), (0.22, 0.18, 0.12), M["dark"], 0.025)
    box(c, "screen", (0.48, -0.27, 1.36), (0.16, 0.025, 0.18), M["dark"], 0.015)
    return c


def create_freezer_master(M):
    c = master("display_freezer")
    box(c, "freezer_body", (0, 0, 0.55), (1.0, 0.40, 0.55), M["freezer"], 0.035)
    box(c, "freezer_glass", (0, -0.42, 0.68), (0.90, 0.025, 0.38), M["glass"], 0.006)
    for x in (-0.45, 0, 0.45):
        box(
            c,
            "freezer_divider",
            (x, -0.46, 0.68),
            (0.018, 0.025, 0.38),
            M["metal"],
            0.003,
        )
    box(c, "freezer_vent", (0, -0.44, 0.15), (0.84, 0.025, 0.09), M["dark"], 0.004)
    return c


def create_table_master(M):
    c = master("restaurant_table")
    box(c, "table_top", (0, 0, 0.74), (0.55, 0.55, 0.045), M["wood"], 0.025)
    box(c, "table_post", (0, 0, 0.38), (0.055, 0.055, 0.34), M["metal"], 0.012)
    box(c, "table_foot", (0, 0, 0.04), (0.32, 0.32, 0.035), M["metal"], 0.012)
    return c


def create_chair_master(M):
    c = master("restaurant_chair")
    box(c, "chair_seat", (0, 0, 0.46), (0.24, 0.24, 0.045), M["wood"], 0.02)
    box(c, "chair_back", (0, 0.22, 0.78), (0.24, 0.035, 0.32), M["wood"], 0.018)
    for x in (-0.19, 0.19):
        for y in (-0.19, 0.19):
            box(c, "chair_leg", (x, y, 0.23), (0.025, 0.025, 0.23), M["metal"], 0.005)
    return c


def create_light_master(M):
    c = master("ceiling_light")
    box(c, "light_housing", (0, 0, 0), (0.58, 0.10, 0.035), M["metal"], 0.008)
    box(c, "light_diffuser", (0, -0.02, -0.045), (0.52, 0.08, 0.012), M["warm"], 0.004)
    return c


def prepare_interior_asset_library():
    M = materials()
    return {
        "materials": M,
        "shelf": create_shelf_master(M),
        "checkout": create_checkout_master(M),
        "freezer": create_freezer_master(M),
        "table": create_table_master(M),
        "chair": create_chair_master(M),
        "light": create_light_master(M),
    }


def remove_unexplained_front_objects(collection):
    removed = []
    bad = (
        "02_bollard",
        "door_pull",
        "02_pull",
        "02_meter_box",
        "02_meter",
        "02_conduit",
    )
    for o in list(collection.objects):
        # Baseline counter at y=-4.75 is outside the glazing and reads as an unexplained block.
        if any(k in o.name for k in bad) or (
            "counter" in o.name.lower() and o.location.y < -4.5
        ):
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return removed


def open_facade_shell(collection, M):
    removed = []
    shell = next(
        (
            o
            for o in collection.objects
            if o.name.split(".")[-1].endswith(":shell")
            or o.name == "all43_01:shell"
            or o.name == "all43_01:shell.001"
        ),
        None,
    )
    wallmat = (
        shell.material_slots[0].material
        if shell and shell.material_slots
        else M["shelf"]
    )
    for o in list(collection.objects):
        name = o.name
        occluder = (
            "interior_wall" in name
            or "02_storefront_recess" in name
            or "02_door_reveal" in name
            or (
                ("storefront_glass" in name or "door_glass" in name)
                and "02_" not in name
            )
            or name in ("all43_01:shell", "all43_01:shell.001")
        )
        if occluder:
            removed.append(name)
            bpy.data.objects.remove(o, do_unlink=True)
    # Replace the former solid box with a real shell around an open storefront.
    box(
        collection,
        "shell_left_wall",
        (-7.89, 0, 2.55),
        (0.22, 9.0, 5.1),
        wallmat,
        0.015,
    )
    box(
        collection,
        "shell_right_wall",
        (7.89, 0, 2.55),
        (0.22, 9.0, 5.1),
        wallmat,
        0.015,
    )
    box(
        collection,
        "shell_rear_wall",
        (0, 4.39, 2.55),
        (15.56, 0.22, 5.1),
        wallmat,
        0.015,
    )
    box(
        collection,
        "shell_front_header",
        (0, -4.39, 4.25),
        (15.56, 0.22, 1.7),
        wallmat,
        0.015,
    )
    return removed


def make_glazing_transparent(collection, glass):
    changed = []
    for o in collection.objects:
        if o.type != "MESH":
            continue
        semantic = "glass" in o.name.lower() or any(
            s.material and "glass" in s.material.name.lower() for s in o.material_slots
        )
        if semantic:
            if not o.data.materials:
                o.data.materials.append(glass)
            for s in o.material_slots:
                s.link = "OBJECT"
                s.material = glass
            o.visible_shadow = False
            o["commercial_transparent_glazing"] = True
            changed.append(o.name)
    return changed


def create_interior_shell(c, M, width):
    box(c, "interior_floor", (0, -0.4, 0.05), (width / 2, 4.1, 0.05), M["dark"], 0.006)
    box(
        c,
        "interior_back_wall",
        (0, 3.65, 1.55),
        (width / 2, 0.08, 1.55),
        M["dark"],
        0.01,
    )
    box(
        c,
        "interior_ceiling",
        (0, -0.3, 3.05),
        (width / 2, 4.0, 0.05),
        M["shelf"],
        0.008,
    )
    light = bpy.data.lights.get(P + "shared_interior_area") or bpy.data.lights.new(
        P + "shared_interior_area", "AREA"
    )
    light.energy = 850
    light.color = (1.0, 0.72, 0.48)
    light.shape = "RECTANGLE"
    light.size = 4.0
    light.size_y = 2.0
    for i, x in enumerate((-3.8, 0, 3.8)):
        o = bpy.data.objects.new(P + "interior_area_light_" + str(i), light)
        c.objects.link(o)
        o.location = (x, -0.2, 2.88)
        o["shared_light_data"] = True


def populate_convenience_interior(c, lib):
    create_interior_shell(c, lib["materials"], 14.3)
    for i, x in enumerate((-4.8, -2.6, -0.4, 1.8)):
        instance(
            c, lib["shelf"], "retail_shelf_" + str(i), (x, -0.7, 0.12), math.pi / 2
        )
    instance(c, lib["checkout"], "checkout_counter", (3.9, -2.65, 0.12))
    instance(c, lib["freezer"], "display_freezer", (-4.4, 2.6, 0.12))
    for i, x in enumerate((-5, -2.5, 0, 2.5, 5)):
        instance(c, lib["light"], "ceiling_light_" + str(i), (x, -0.4, 2.92))


def populate_restaurant_interior(c, lib):
    create_interior_shell(c, lib["materials"], 14.3)
    positions = (
        (-4.4, -2.3),
        (-2.0, -2.3),
        (0.4, -2.3),
        (-3.2, 0.2),
        (-0.8, 0.2),
        (1.6, 0.2),
    )
    for i, (x, y) in enumerate(positions):
        instance(c, lib["table"], "dining_table_" + str(i), (x, y, 0.12))
        instance(
            c, lib["chair"], "dining_chair_" + str(i) + "a", (x, y - 0.78, 0.12), 0
        )
        instance(
            c,
            lib["chair"],
            "dining_chair_" + str(i) + "b",
            (x, y + 0.78, 0.12),
            math.pi,
        )
    instance(c, lib["checkout"], "service_counter", (4.2, 1.6, 0.12), math.pi)
    for i, x in enumerate((-5, -2.5, 0, 2.5, 5)):
        instance(c, lib["light"], "ceiling_light_" + str(i), (x, -0.4, 2.92))


def run():
    lib = prepare_interior_asset_library()
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    removed = remove_unexplained_front_objects(conv) + remove_unexplained_front_objects(
        rest
    )
    removed += open_facade_shell(conv, lib["materials"]) + open_facade_shell(
        rest, lib["materials"]
    )
    changed = make_glazing_transparent(
        conv, lib["materials"]["glass"]
    ) + make_glazing_transparent(rest, lib["materials"]["glass"])
    populate_convenience_interior(conv, lib)
    populate_restaurant_interior(rest, lib)
    # Sanity: removed identifiers cannot remain in either facade master.
    forbidden = (
        "02_bollard",
        "door_pull",
        "02_pull",
        "02_meter_box",
        "02_meter",
        "02_conduit",
    )
    remaining = [
        o.name
        for c in (conv, rest)
        for o in c.objects
        if any(k in o.name for k in forbidden)
    ]
    if remaining:
        raise RuntimeError("front cleanup incomplete: " + str(remaining))
    return lib, removed, changed
