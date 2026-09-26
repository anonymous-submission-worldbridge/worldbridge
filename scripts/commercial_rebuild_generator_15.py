"""All43-15: rebuild both community storefronts as coherent commercial systems.

The source scene contains many generations of mutually overlapping storefront
experiments.  This pass deliberately hides every legacy object in the two shop
master collections and builds a new shell, facade, interior, and frontage from
named, instanced assets.
"""
import math
import random

import bpy
from mathutils import Vector


P = "all43_15:"
FRESH_COLLECTION = "all43_01:MASTER:convenience_store"
RESTAURANT_COLLECTION = "all43_01:MASTER:restaurant"


def cube_mesh():
    return bpy.data.meshes["all43_10:shared_cube"]


def cylinder_mesh():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


def sphere_mesh():
    return bpy.data.meshes["all43_11_light:shared_produce_sphere"]


def bag_mesh():
    return bpy.data.meshes.get("all43_10:shared_bag") or cube_mesh()


def material(name, color, roughness=0.55, metallic=0.0, noise_scale=0.0, bump=0.0):
    mat = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if noise_scale and not nodes.get(P + "micro_" + name):
        tex = nodes.new("ShaderNodeTexNoise")
        tex.name = P + "micro_" + name
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 4.0
        tex.inputs["Roughness"].default_value = 0.62
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.name = P + "variation_" + name
        dark = tuple(max(0.0, v * 0.91) for v in color[:3]) + (1.0,)
        light = tuple(min(1.0, v * 1.06 + 0.008) for v in color[:3]) + (1.0,)
        ramp.color_ramp.elements[0].color = dark
        ramp.color_ramp.elements[1].color = light
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump_node = nodes.new("ShaderNodeBump")
        bump_node.name = P + "bump_" + name
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.012
        links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def glass_material():
    mat = material("storefront_laminated_glass", (0.035, 0.075, 0.078, 1), 0.14)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Transmission Weight"].default_value = 0.76
    bsdf.inputs["IOR"].default_value = 1.46
    bsdf.inputs["Coat Weight"].default_value = 0.24
    bsdf.inputs["Coat Roughness"].default_value = 0.075
    return mat


def materials():
    return {
        "fresh_stucco": material(
            "fresh_warm_stucco", (0.43, 0.47, 0.41, 1), 0.72, 0, 30, 0.065
        ),
        "restaurant_stucco": material(
            "restaurant_warm_stucco", (0.52, 0.45, 0.37, 1), 0.73, 0, 30, 0.065
        ),
        "side_panel": material(
            "fiber_cement_side_panel", (0.28, 0.31, 0.30, 1), 0.65, 0.03, 34, 0.035
        ),
        "frame": material(
            "anodized_storefront_aluminum",
            (0.035, 0.042, 0.041, 1),
            0.30,
            0.72,
            46,
            0.018,
        ),
        "gasket": material("black_glazing_gasket", (0.008, 0.010, 0.010, 1), 0.80),
        "glass": glass_material(),
        "concrete": material(
            "architectural_concrete", (0.44, 0.43, 0.39, 1), 0.86, 0, 48, 0.085
        ),
        "sidewalk": material(
            "broom_finished_sidewalk", (0.48, 0.47, 0.43, 1), 0.89, 0, 55, 0.095
        ),
        "entry_paver": material(
            "charcoal_entry_paver", (0.15, 0.16, 0.15, 1), 0.78, 0, 42, 0.055
        ),
        "dark_metal": material(
            "powdercoated_dark_metal", (0.025, 0.030, 0.029, 1), 0.42, 0.56, 45, 0.02
        ),
        "brushed_metal": material(
            "brushed_stainless", (0.35, 0.37, 0.36, 1), 0.36, 0.67, 52, 0.018
        ),
        "fresh_sign": material(
            "fresh_sign_enamel", (0.055, 0.20, 0.12, 1), 0.46, 0.10, 24, 0.016
        ),
        "restaurant_sign": material(
            "restaurant_sign_enamel", (0.34, 0.075, 0.040, 1), 0.48, 0.10, 24, 0.016
        ),
        "letter_face": material(
            "warm_channel_letter_face", (0.82, 0.75, 0.55, 1), 0.33, 0.18, 20, 0.008
        ),
        "canopy": material(
            "canopy_zinc_finish", (0.16, 0.19, 0.18, 1), 0.46, 0.42, 38, 0.018
        ),
        "interior_wall": material(
            "commercial_interior_wall", (0.72, 0.70, 0.64, 1), 0.77, 0, 28, 0.035
        ),
        "grocery_floor": material(
            "grocery_vinyl_tile", (0.40, 0.43, 0.40, 1), 0.61, 0, 58, 0.032
        ),
        "restaurant_floor": material(
            "restaurant_terrazzo_floor", (0.36, 0.34, 0.30, 1), 0.57, 0, 72, 0.035
        ),
        "ceiling": material(
            "acoustic_ceiling", (0.77, 0.76, 0.70, 1), 0.86, 0, 35, 0.025
        ),
        "light_lens": material("light_diffuser", (0.82, 0.82, 0.73, 1), 0.35),
        "shelf": material(
            "shelf_powdercoat", (0.23, 0.25, 0.23, 1), 0.54, 0.34, 35, 0.018
        ),
        "shelf_edge": material(
            "shelf_label_edge", (0.66, 0.64, 0.55, 1), 0.48, 0.08, 28, 0.010
        ),
        "cooler": material(
            "cooler_off_white", (0.64, 0.66, 0.63, 1), 0.51, 0.14, 28, 0.018
        ),
        "wood": material("sealed_ash_wood", (0.43, 0.22, 0.095, 1), 0.48, 0, 22, 0.035),
        "dark_wood": material(
            "counter_walnut", (0.22, 0.085, 0.035, 1), 0.46, 0, 20, 0.035
        ),
        "seat": material(
            "restaurant_seat_vinyl", (0.075, 0.20, 0.16, 1), 0.59, 0, 26, 0.025
        ),
        "black": material("equipment_black", (0.012, 0.014, 0.013, 1), 0.66),
        "carton": material("kraft_carton", (0.58, 0.42, 0.20, 1), 0.60, 0, 24, 0.018),
        "red_pack": material(
            "muted_red_package", (0.42, 0.055, 0.028, 1), 0.52, 0, 24, 0.012
        ),
        "blue_pack": material(
            "muted_blue_package", (0.045, 0.13, 0.28, 1), 0.50, 0, 24, 0.012
        ),
        "green_pack": material(
            "muted_green_package", (0.045, 0.25, 0.095, 1), 0.52, 0, 24, 0.012
        ),
        "cream_pack": material(
            "cream_package", (0.68, 0.61, 0.43, 1), 0.54, 0, 22, 0.012
        ),
        "foil": material("dull_can_foil", (0.43, 0.44, 0.41, 1), 0.35, 0.62, 40, 0.010),
        "ceramic": material(
            "restaurant_ceramic", (0.73, 0.70, 0.61, 1), 0.40, 0, 22, 0.010
        ),
        "plant": material("frontage_plant", (0.11, 0.26, 0.095, 1), 0.70, 0, 24, 0.030),
        "soil": material("planter_soil", (0.10, 0.065, 0.035, 1), 0.92, 0, 30, 0.045),
    }


def assign_object_material(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat


def add_mesh(collection, name, mesh, loc, dims, mat, bevel=0.006, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = dims
    obj.rotation_euler = rot
    assign_object_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_bevel", "BEVEL")
        modifier.width = min(bevel, min(dims) * 0.20)
        modifier.segments = 2
    obj["shared_mesh_data"] = True
    return obj


def add_box(collection, name, loc, dims, mat, bevel=0.006, rot=(0, 0, 0)):
    return add_mesh(collection, name, cube_mesh(), loc, dims, mat, bevel, rot)


def add_cylinder(collection, name, loc, scale, mat, bevel=0.004, rot=(0, 0, 0)):
    return add_mesh(collection, name, cylinder_mesh(), loc, scale, mat, bevel, rot)


def add_beam_between(collection, name, start, end, thickness, mat):
    start = Vector(start)
    end = Vector(end)
    vec = end - start
    obj = add_box(
        collection,
        name,
        (start + end) / 2,
        (thickness, thickness, vec.length),
        mat,
        0.004,
    )
    obj.rotation_euler = vec.to_track_quat("Z", "Y").to_euler()
    return obj


def new_master(name):
    old = bpy.data.collections.get(name)
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new(name)
    collection.use_fake_user = True
    collection["all43_15_master_asset"] = True
    collection["instance_policy"] = "linked collection instance"
    return collection


def instance(collection, master_collection, name, loc, rot=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(P + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master_collection
    obj.location = loc
    obj.rotation_euler[2] = rot
    obj.scale = scale
    obj["linked_asset"] = master_collection.name
    return obj


def hide_legacy_shop_objects():
    hidden = {}
    for collection_name in (FRESH_COLLECTION, RESTAURANT_COLLECTION):
        collection = bpy.data.collections[collection_name]
        names = []
        for obj in collection.objects:
            if obj.name.startswith(P):
                continue
            obj.hide_render = True
            obj.hide_viewport = True
            obj["all43_15_hidden_reason"] = "complete commercial-system rebuild"
            names.append(obj.name)
        hidden[collection_name] = names
    return hidden


def add_area_light(collection, name, loc, energy=280, size=2.2):
    data = bpy.data.lights.new(P + name + "_data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = 0.40
    obj = bpy.data.objects.new(P + name, data)
    collection.objects.link(obj)
    obj.location = loc
    return obj


def create_exterior_masters(M):
    frame = new_master("STOREFRONT_FRAME_MASTER")
    add_box(
        frame,
        "frame_recess_shadow",
        (0, 0.09, 1.40),
        (2.46, 0.12, 2.82),
        M["gasket"],
        0.012,
    )
    for x in (-1.22, 1.22):
        add_box(
            frame,
            "frame_jamb",
            (x, -0.07, 1.40),
            (0.090, 0.15, 2.82),
            M["frame"],
            0.009,
        )
    for z in (0.07, 2.73):
        add_box(
            frame, "frame_rail", (0, -0.07, z), (2.46, 0.15, 0.105), M["frame"], 0.009
        )

    window = new_master("STOREFRONT_WINDOW_MASTER")
    instance(window, frame, "nested_structural_frame", (0, 0, 0))
    add_box(
        window,
        "laminated_display_glass",
        (0, -0.055, 1.39),
        (2.25, 0.030, 2.52),
        M["glass"],
        0.002,
    )
    add_box(
        window,
        "center_mullion",
        (0, -0.165, 1.39),
        (0.052, 0.075, 2.52),
        M["frame"],
        0.005,
    )
    add_box(
        window,
        "transom_rail",
        (0, -0.165, 2.19),
        (2.25, 0.075, 0.060),
        M["frame"],
        0.005,
    )
    add_box(
        window,
        "lower_kick_plate",
        (0, -0.17, 0.20),
        (2.25, 0.080, 0.24),
        M["dark_metal"],
        0.006,
    )
    add_box(
        window,
        "interior_glazing_stop",
        (0, 0.02, 2.60),
        (2.25, 0.035, 0.030),
        M["gasket"],
        0.002,
    )

    door = new_master("STOREFRONT_DOOR_MASTER")
    add_box(
        door, "door_reveal", (0, 0.10, 1.42), (1.20, 0.13, 2.86), M["gasket"], 0.012
    )
    for x in (-0.58, 0.58):
        add_box(
            door, "door_jamb", (x, -0.08, 1.42), (0.085, 0.16, 2.86), M["frame"], 0.009
        )
    add_box(
        door, "door_header", (0, -0.08, 2.78), (1.20, 0.16, 0.095), M["frame"], 0.009
    )
    add_box(
        door,
        "door_glass_leaf",
        (0, -0.19, 1.48),
        (1.01, 0.030, 2.35),
        M["glass"],
        0.002,
    )
    for x in (-0.48, 0.48):
        add_box(
            door,
            "door_leaf_stile",
            (x, -0.22, 1.45),
            (0.045, 0.060, 2.50),
            M["frame"],
            0.005,
        )
    add_box(
        door,
        "door_leaf_top_rail",
        (0, -0.22, 2.66),
        (1.01, 0.060, 0.060),
        M["frame"],
        0.005,
    )
    add_box(
        door,
        "door_leaf_kick_rail",
        (0, -0.22, 0.31),
        (1.01, 0.065, 0.25),
        M["brushed_metal"],
        0.006,
    )
    add_box(
        door,
        "door_pull",
        (0.30, -0.315, 1.48),
        (0.035, 0.045, 0.56),
        M["brushed_metal"],
        0.007,
    )
    for z in (1.23, 1.73):
        add_box(
            door,
            "door_pull_mount",
            (0.30, -0.285, z),
            (0.080, 0.045, 0.045),
            M["brushed_metal"],
            0.005,
        )
    add_box(
        door,
        "hydraulic_door_closer",
        (-0.20, -0.26, 2.57),
        (0.38, 0.075, 0.090),
        M["dark_metal"],
        0.008,
    )
    add_box(
        door,
        "accessible_threshold",
        (0, -0.16, 0.08),
        (1.28, 0.34, 0.065),
        M["brushed_metal"],
        0.005,
    )

    sign_band = new_master("SIGN_BAND_MASTER")
    add_box(
        sign_band,
        "folded_sign_backboard",
        (0, 0, 0),
        (1.0, 0.16, 0.78),
        M["dark_metal"],
        0.018,
    )
    add_box(
        sign_band,
        "sign_top_trim",
        (0, -0.02, 0.405),
        (1.04, 0.19, 0.050),
        M["dark_metal"],
        0.006,
    )
    add_box(
        sign_band,
        "sign_bottom_trim",
        (0, -0.02, -0.405),
        (1.04, 0.19, 0.050),
        M["dark_metal"],
        0.006,
    )

    channel = new_master("CHANNEL_LETTER_MASTER")
    text_data = bpy.data.curves.new(P + "channel_letter_reference_data", "FONT")
    text_data.body = "A"
    text_data.align_x = "CENTER"
    text_data.align_y = "CENTER"
    text_data.size = 0.52
    text_data.extrude = 0.10
    text_data.bevel_depth = 0.008
    text_data.bevel_resolution = 2
    text_data.materials.append(M["letter_face"])
    text = bpy.data.objects.new(P + "channel_letter_reference", text_data)
    channel.objects.link(text)
    text.rotation_euler[0] = math.pi / 2
    add_cylinder(
        channel,
        "letter_mounting_cup",
        (0, 0.055, 0),
        (0.035, 0.035, 0.055),
        M["dark_metal"],
        0.003,
        (math.pi / 2, 0, 0),
    )

    canopy = new_master("CANOPY_MASTER")
    slope = math.radians(4.5)
    add_box(
        canopy,
        "seamed_canopy_skin",
        (0, -0.62, 0),
        (0.98, 1.24, 0.095),
        M["canopy"],
        0.010,
        (slope, 0, 0),
    )
    add_box(
        canopy,
        "canopy_underside_frame",
        (0, -0.62, -0.09),
        (0.92, 1.12, 0.055),
        M["dark_metal"],
        0.006,
        (slope, 0, 0),
    )
    add_box(
        canopy,
        "formed_canopy_fascia",
        (0, -1.23, -0.14),
        (0.98, 0.095, 0.22),
        M["canopy"],
        0.008,
    )
    add_box(
        canopy,
        "canopy_wall_flashing",
        (0, -0.03, 0.08),
        (0.98, 0.075, 0.16),
        M["brushed_metal"],
        0.006,
    )
    return {
        "frame": frame,
        "window": window,
        "door": door,
        "sign_band": sign_band,
        "channel": channel,
        "canopy": canopy,
    }


def create_product_masters(M):
    bottle = new_master(P + "MASTER:PRODUCT_BOTTLE")
    add_cylinder(
        bottle,
        "bottle_body",
        (0, 0, 0.16),
        (0.055, 0.055, 0.16),
        M["green_pack"],
        0.004,
    )
    add_cylinder(
        bottle,
        "bottle_shoulder",
        (0, 0, 0.33),
        (0.040, 0.040, 0.055),
        M["green_pack"],
        0.003,
    )
    add_cylinder(
        bottle,
        "bottle_cap",
        (0, 0, 0.405),
        (0.026, 0.026, 0.025),
        M["cream_pack"],
        0.002,
    )
    add_cylinder(
        bottle,
        "bottle_label",
        (0, 0, 0.17),
        (0.058, 0.058, 0.045),
        M["cream_pack"],
        0.001,
    )

    can = new_master(P + "MASTER:PRODUCT_CAN")
    add_cylinder(can, "can_body", (0, 0, 0.13), (0.065, 0.065, 0.13), M["foil"], 0.003)
    add_cylinder(
        can,
        "can_printed_wrap",
        (0, 0, 0.135),
        (0.068, 0.068, 0.085),
        M["blue_pack"],
        0.001,
    )
    add_cylinder(
        can, "can_top", (0, 0, 0.265), (0.061, 0.061, 0.008), M["brushed_metal"], 0.001
    )

    box = new_master(P + "MASTER:PRODUCT_BOX")
    add_box(box, "folded_carton", (0, 0, 0.19), (0.20, 0.105, 0.38), M["carton"], 0.007)
    add_box(
        box,
        "carton_print_panel",
        (0, -0.056, 0.22),
        (0.145, 0.008, 0.18),
        M["red_pack"],
        0.001,
    )
    add_box(
        box,
        "carton_top_flap",
        (0, 0, 0.385),
        (0.17, 0.09, 0.018),
        M["cream_pack"],
        0.002,
    )

    bag = new_master(P + "MASTER:PRODUCT_BAG")
    add_mesh(
        bag,
        "stand_up_pouch",
        bag_mesh(),
        (0, 0, 0.17),
        (0.12, 0.075, 0.34),
        M["red_pack"],
        0.006,
    )
    add_box(
        bag,
        "pouch_label",
        (0, -0.079, 0.18),
        (0.075, 0.006, 0.10),
        M["cream_pack"],
        0.001,
    )

    carton = new_master(P + "MASTER:PRODUCT_CARTON")
    add_box(
        carton,
        "drink_carton_body",
        (0, 0, 0.20),
        (0.12, 0.09, 0.40),
        M["cream_pack"],
        0.006,
    )
    add_box(
        carton,
        "drink_carton_panel",
        (0, -0.048, 0.20),
        (0.085, 0.006, 0.20),
        M["green_pack"],
        0.001,
    )
    add_cylinder(
        carton,
        "carton_cap",
        (0.025, -0.01, 0.415),
        (0.020, 0.020, 0.020),
        M["red_pack"],
        0.002,
    )
    return [bottle, can, box, bag, carton]


def create_grocery_masters(M, products):
    shelf = new_master("GROCERY_SHELF_MASTER")
    add_box(
        shelf, "gondola_plinth", (0, 0, 0.11), (2.80, 0.88, 0.18), M["shelf"], 0.012
    )
    add_box(
        shelf,
        "gondola_back_panel",
        (0, 0, 0.93),
        (2.72, 0.075, 1.55),
        M["shelf"],
        0.008,
    )
    for x in (-1.34, 1.34):
        add_box(
            shelf,
            "gondola_upright",
            (x, 0, 0.92),
            (0.065, 0.085, 1.72),
            M["dark_metal"],
            0.007,
        )
    rng = random.Random(431501)
    goods = 0
    for side in (-1, 1):
        y = side * 0.37
        for level, z in enumerate((0.34, 0.68, 1.02, 1.36, 1.66)):
            add_box(
                shelf,
                "supported_shelf_deck",
                (0, y, z),
                (2.70, 0.34, 0.045),
                M["shelf"],
                0.005,
            )
            add_box(
                shelf,
                "shelf_price_edge",
                (0, y + side * 0.17, z + 0.02),
                (2.66, 0.025, 0.080),
                M["shelf_edge"],
                0.003,
            )
            slots = 11
            for slot in range(slots):
                if rng.random() < 0.20:
                    continue
                x = -1.17 + slot * 0.235 + (rng.random() - 0.5) * 0.035
                product = products[
                    (slot + level * 2 + (0 if side < 0 else 1)) % len(products)
                ]
                size = 0.68 + rng.random() * 0.16
                instance(
                    shelf,
                    product,
                    "faced_product",
                    (x, y + side * 0.04, z + 0.045),
                    (rng.random() - 0.5) * 0.07,
                    (size, size, size),
                )
                goods += 1
    shelf["semantic_asset"] = "double-sided stocked grocery gondola"
    shelf["product_instance_count"] = goods

    fridge = new_master("GROCERY_FRIDGE_MASTER")
    add_box(
        fridge,
        "refrigerator_case",
        (0, 0.04, 1.10),
        (2.48, 0.72, 2.20),
        M["cooler"],
        0.024,
    )
    add_box(
        fridge,
        "refrigerator_recess",
        (0, -0.345, 1.13),
        (2.25, 0.035, 1.83),
        M["black"],
        0.003,
    )
    for door_x in (-0.78, 0, 0.78):
        add_box(
            fridge,
            "cooler_glazed_door",
            (door_x, -0.39, 1.15),
            (0.68, 0.026, 1.72),
            M["glass"],
            0.002,
        )
        add_box(
            fridge,
            "cooler_door_handle",
            (door_x + 0.24, -0.445, 1.16),
            (0.025, 0.035, 0.66),
            M["brushed_metal"],
            0.005,
        )
    for z in (0.48, 0.82, 1.16, 1.50, 1.82):
        add_box(
            fridge,
            "cooler_internal_shelf",
            (0, -0.20, z),
            (2.18, 0.31, 0.025),
            M["brushed_metal"],
            0.003,
        )
        for x in (-0.91, -0.57, -0.22, 0.18, 0.56, 0.91):
            product = products[int((z * 10 + x * 7)) % len(products)]
            instance(
                fridge,
                product,
                "chilled_product",
                (x, -0.35, z + 0.035),
                0,
                (0.62, 0.62, 0.62),
            )
    add_box(
        fridge,
        "cooler_top_vent",
        (0, -0.36, 2.08),
        (2.20, 0.06, 0.10),
        M["dark_metal"],
        0.004,
    )

    checkout = new_master("CHECKOUT_MASTER")
    add_box(
        checkout,
        "checkout_cabinet",
        (0, 0, 0.45),
        (2.25, 0.72, 0.86),
        M["dark_wood"],
        0.022,
    )
    add_box(
        checkout,
        "checkout_toe_kick",
        (0, -0.30, 0.10),
        (2.05, 0.12, 0.16),
        M["black"],
        0.004,
    )
    add_box(
        checkout,
        "checkout_countertop",
        (0, 0, 0.91),
        (2.38, 0.82, 0.080),
        M["brushed_metal"],
        0.012,
    )
    add_box(
        checkout,
        "conveyor_belt",
        (-0.43, -0.08, 0.965),
        (1.18, 0.48, 0.035),
        M["black"],
        0.005,
    )
    add_box(
        checkout,
        "register_base",
        (0.70, 0.02, 1.04),
        (0.38, 0.30, 0.18),
        M["black"],
        0.008,
    )
    add_box(
        checkout,
        "register_screen",
        (0.70, -0.16, 1.27),
        (0.34, 0.055, 0.25),
        M["black"],
        0.006,
        (math.radians(-10), 0, 0),
    )
    add_box(
        checkout,
        "card_terminal",
        (0.18, -0.30, 1.05),
        (0.20, 0.14, 0.10),
        M["dark_metal"],
        0.006,
    )
    add_box(
        checkout,
        "bagging_shelf",
        (1.30, 0.12, 0.66),
        (0.48, 0.52, 0.055),
        M["brushed_metal"],
        0.006,
    )
    return {"shelf": shelf, "fridge": fridge, "checkout": checkout}


def create_restaurant_masters(M):
    table = new_master("DINING_TABLE_MASTER")
    add_box(
        table, "solid_tabletop", (0, 0, 0.76), (1.24, 0.76, 0.080), M["wood"], 0.020
    )
    add_box(
        table,
        "table_apron_long",
        (0, -0.31, 0.67),
        (1.10, 0.070, 0.16),
        M["dark_wood"],
        0.007,
    )
    add_box(
        table,
        "table_apron_long",
        (0, 0.31, 0.67),
        (1.10, 0.070, 0.16),
        M["dark_wood"],
        0.007,
    )
    for x in (-0.48, 0.48):
        for y in (-0.27, 0.27):
            add_box(
                table,
                "tapered_table_leg",
                (x, y, 0.37),
                (0.065, 0.065, 0.67),
                M["dark_metal"],
                0.007,
            )

    chair = new_master("DINING_CHAIR_MASTER")
    add_box(
        chair,
        "upholstered_chair_seat",
        (0, 0, 0.46),
        (0.47, 0.45, 0.09),
        M["seat"],
        0.020,
    )
    add_box(
        chair,
        "chair_back_frame",
        (0, 0.19, 0.79),
        (0.47, 0.065, 0.52),
        M["dark_wood"],
        0.014,
        (math.radians(-4), 0, 0),
    )
    add_box(
        chair,
        "chair_back_inset",
        (0, 0.155, 0.80),
        (0.35, 0.040, 0.34),
        M["seat"],
        0.014,
        (math.radians(-4), 0, 0),
    )
    for x in (-0.18, 0.18):
        for y in (-0.16, 0.16):
            add_box(
                chair,
                "chair_leg",
                (x, y, 0.24),
                (0.045, 0.045, 0.43),
                M["dark_metal"],
                0.006,
            )
    add_box(
        chair,
        "chair_front_stretcher",
        (0, -0.16, 0.22),
        (0.34, 0.035, 0.035),
        M["dark_metal"],
        0.004,
    )
    add_box(
        chair,
        "chair_side_stretcher",
        (-0.18, 0, 0.24),
        (0.035, 0.28, 0.035),
        M["dark_metal"],
        0.004,
    )
    add_box(
        chair,
        "chair_side_stretcher",
        (0.18, 0, 0.24),
        (0.035, 0.28, 0.035),
        M["dark_metal"],
        0.004,
    )

    counter = new_master("RESTAURANT_COUNTER_MASTER")
    add_box(
        counter,
        "service_counter_cabinet",
        (0, 0, 0.48),
        (3.60, 0.86, 0.92),
        M["dark_wood"],
        0.025,
    )
    add_box(
        counter,
        "service_counter_recess",
        (0, -0.44, 0.48),
        (3.26, 0.035, 0.68),
        M["black"],
        0.004,
    )
    for x in (-1.12, 0, 1.12):
        add_box(
            counter,
            "counter_front_slatted_panel",
            (x, -0.47, 0.49),
            (0.90, 0.030, 0.62),
            M["wood"],
            0.008,
        )
    add_box(
        counter,
        "service_countertop",
        (0, 0, 0.97),
        (3.78, 0.98, 0.090),
        M["brushed_metal"],
        0.013,
    )
    add_box(
        counter,
        "glass_display_base",
        (-1.00, -0.10, 1.10),
        (1.24, 0.56, 0.16),
        M["dark_metal"],
        0.007,
    )
    add_box(
        counter,
        "glass_display_case",
        (-1.00, -0.10, 1.38),
        (1.20, 0.48, 0.45),
        M["glass"],
        0.004,
    )
    add_box(
        counter, "pos_base", (1.12, -0.12, 1.09), (0.38, 0.28, 0.16), M["black"], 0.007
    )
    add_box(
        counter,
        "pos_screen",
        (1.12, -0.28, 1.32),
        (0.34, 0.050, 0.27),
        M["black"],
        0.006,
        (math.radians(-10), 0, 0),
    )
    add_box(
        counter,
        "pickup_shelf",
        (2.22, 0.05, 0.84),
        (0.70, 0.64, 0.080),
        M["wood"],
        0.010,
    )

    prep = new_master("KITCHEN_PREP_MASTER")
    add_box(
        prep,
        "undercounter_cabinet",
        (0, 0, 0.42),
        (2.25, 0.72, 0.82),
        M["cooler"],
        0.018,
    )
    add_box(
        prep,
        "stainless_prep_top",
        (0, 0, 0.87),
        (2.38, 0.82, 0.080),
        M["brushed_metal"],
        0.010,
    )
    for x in (-0.74, 0, 0.74):
        add_box(
            prep,
            "cabinet_door",
            (x, -0.375, 0.45),
            (0.62, 0.035, 0.64),
            M["brushed_metal"],
            0.006,
        )
        add_box(
            prep,
            "cabinet_pull",
            (x + 0.20, -0.410, 0.54),
            (0.025, 0.025, 0.16),
            M["dark_metal"],
            0.004,
        )
    add_box(
        prep,
        "prep_undershelf",
        (0, 0.02, 0.22),
        (2.02, 0.56, 0.050),
        M["brushed_metal"],
        0.005,
    )
    return {"table": table, "chair": chair, "counter": counter, "prep": prep}


def add_text(collection, name, body, loc, size, depth, mat):
    data = bpy.data.curves.new(P + name + "_data", "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.space_character = 1.15
    data.extrude = depth
    data.bevel_depth = 0.009
    data.bevel_resolution = 2
    data.fill_mode = "BOTH"
    data.materials.append(mat)
    obj = bpy.data.objects.new(P + name, data)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler[0] = math.pi / 2
    obj["asset_role"] = "raised channel letters with physical depth"
    obj["mounting_offset_m"] = 0.055
    return obj


def add_store_shell(collection, M, wall_mat, restaurant=False):
    top = 5.70 if restaurant else 5.42
    # Full building mass, with a readable interior shell and deep side returns.
    add_box(
        collection,
        "commercial_floor_slab",
        (0, -0.05, 0.10),
        (15.45, 8.72, 0.20),
        M["concrete"],
        0.010,
    )
    add_box(
        collection,
        "left_side_wall_mass",
        (-7.68, 0, top / 2),
        (0.28, 8.86, top),
        wall_mat,
        0.018,
    )
    add_box(
        collection,
        "right_side_wall_mass",
        (7.68, 0, top / 2),
        (0.28, 8.86, top),
        wall_mat,
        0.018,
    )
    add_box(
        collection,
        "rear_wall_mass",
        (0, 4.38, top / 2),
        (15.10, 0.28, top),
        wall_mat,
        0.018,
    )
    add_box(
        collection,
        "storefront_header_mass",
        (0, -4.40, 4.37),
        (15.10, 0.34, top - 3.18),
        wall_mat,
        0.022,
    )
    add_box(
        collection,
        "storefront_lower_base",
        (0, -4.63, 0.28),
        (15.10, 0.34, 0.42),
        M["concrete"],
        0.012,
    )
    add_box(
        collection,
        "interior_finished_floor",
        (0, -0.05, 0.225),
        (15.10, 8.36, 0.055),
        M["restaurant_floor" if restaurant else "grocery_floor"],
        0.004,
    )
    add_box(
        collection,
        "interior_ceiling",
        (0, -0.05, 4.02),
        (15.05, 8.30, 0.075),
        M["ceiling"],
        0.005,
    )
    add_box(
        collection,
        "rear_interior_finish",
        (0, 4.20, 2.08),
        (14.82, 0.060, 3.72),
        M["interior_wall"],
        0.004,
    )
    add_box(
        collection,
        "left_interior_finish",
        (-7.48, 0, 2.08),
        (0.060, 8.20, 3.72),
        M["interior_wall"],
        0.004,
    )
    add_box(
        collection,
        "right_interior_finish",
        (7.48, 0, 2.08),
        (0.060, 8.20, 3.72),
        M["interior_wall"],
        0.004,
    )
    # Parapet and coping are real perimeter pieces rather than a roof slab edge.
    add_box(
        collection,
        "front_parapet",
        (0, -4.33, top + 0.17),
        (15.50, 0.42, 0.34),
        wall_mat,
        0.014,
    )
    add_box(
        collection,
        "rear_parapet",
        (0, 4.28, top + 0.17),
        (15.50, 0.42, 0.34),
        wall_mat,
        0.014,
    )
    add_box(
        collection,
        "left_parapet",
        (-7.56, 0, top + 0.17),
        (0.42, 8.25, 0.34),
        wall_mat,
        0.014,
    )
    add_box(
        collection,
        "right_parapet",
        (7.56, 0, top + 0.17),
        (0.42, 8.25, 0.34),
        wall_mat,
        0.014,
    )
    add_box(
        collection,
        "front_coping",
        (0, -4.35, top + 0.37),
        (15.68, 0.52, 0.10),
        M["brushed_metal"],
        0.010,
    )
    add_box(
        collection,
        "rear_coping",
        (0, 4.30, top + 0.37),
        (15.68, 0.52, 0.10),
        M["brushed_metal"],
        0.010,
    )
    add_box(
        collection,
        "left_coping",
        (-7.60, 0, top + 0.37),
        (0.52, 8.20, 0.10),
        M["brushed_metal"],
        0.010,
    )
    add_box(
        collection,
        "right_coping",
        (7.60, 0, top + 0.37),
        (0.52, 8.20, 0.10),
        M["brushed_metal"],
        0.010,
    )
    # Side cladding has panel joints and a continuous base, not decorative rods.
    visible_x = 7.84 if restaurant else -7.84
    for y in (-3.28, -1.64, 0, 1.64, 3.28):
        add_box(
            collection,
            "side_cladding_panel",
            (visible_x, y, 2.75),
            (0.065, 1.54, 4.65),
            M["side_panel"],
            0.008,
        )
    for y in (-2.46, -0.82, 0.82, 2.46):
        add_box(
            collection,
            "side_cladding_reveal_joint",
            (visible_x + (0.04 if visible_x > 0 else -0.04), y, 2.75),
            (0.025, 0.030, 4.48),
            M["gasket"],
            0.002,
        )
    add_box(
        collection,
        "side_wall_base_course",
        (visible_x, 0, 0.38),
        (0.10, 8.35, 0.30),
        M["concrete"],
        0.009,
    )
    # Exterior service components have explicit mounting relationships.
    pipe_x = -7.84 if restaurant else 7.84
    add_cylinder(
        collection,
        "connected_downpipe",
        (pipe_x, 3.30, 2.55),
        (0.075, 0.075, 2.42),
        M["dark_metal"],
        0.005,
    )
    for z in (1.1, 2.7, 4.3):
        add_box(
            collection,
            "downpipe_wall_clip",
            (pipe_x, 3.30, z),
            (0.18, 0.12, 0.050),
            M["brushed_metal"],
            0.004,
        )
    add_beam_between(
        collection,
        "downpipe_discharge_shoe",
        (pipe_x, 3.30, 0.18),
        (pipe_x, 3.02, 0.12),
        0.10,
        M["dark_metal"],
    )
    add_box(
        collection,
        "exterior_utility_panel",
        (visible_x + (0.05 if visible_x > 0 else -0.05), 2.15, 1.25),
        (0.12, 0.66, 0.78),
        M["dark_metal"],
        0.014,
    )
    # Staff access is aligned to a real rear opening.
    add_box(
        collection,
        "rear_staff_door",
        (4.85, 4.02, 1.48),
        (1.25, 0.10, 2.62),
        M["dark_metal"],
        0.012,
    )
    add_box(
        collection,
        "rear_staff_door_frame",
        (4.85, 3.95, 2.78),
        (1.42, 0.16, 0.11),
        M["brushed_metal"],
        0.007,
    )
    for x in (4.18, 5.52):
        add_box(
            collection,
            "rear_staff_door_jamb",
            (x, 3.95, 1.48),
            (0.11, 0.16, 2.72),
            M["brushed_metal"],
            0.007,
        )
    return top


def add_window_and_door_system(collection, exterior, restaurant=False):
    window = exterior["window"]
    door = exterior["door"]
    wall_mat = bpy.data.materials[
        P + ("restaurant_warm_stucco" if restaurant else "fresh_warm_stucco")
    ]
    if restaurant:
        window_xs = (-6.03, -3.34, -0.65, 2.04)
        spans = []
        for i, x in enumerate(window_xs):
            scale_x = 1.02 if i in (0, 3) else 0.96
            instance(
                collection,
                window,
                "restaurant_display_window",
                (x, -4.82, 0.38),
                0,
                (scale_x, 1, 1),
            )
            half_width = 2.46 * scale_x / 2
            spans.append((x - half_width, x + half_width))
        instance(
            collection,
            window,
            "restaurant_entry_sidelight",
            (4.18, -4.82, 0.38),
            0,
            (0.58, 1, 1),
        )
        instance(collection, door, "restaurant_single_entry_door", (5.80, -4.82, 0.30))
        spans.extend(((4.18 - 2.46 * 0.58 / 2, 4.18 + 2.46 * 0.58 / 2), (5.20, 6.40)))
        door_centers = [5.80]
    else:
        spans = []
        for i, x in enumerate((-6.10, -3.40, 3.40, 6.10)):
            scale_x = 1.02 if i in (0, 3) else 0.96
            instance(
                collection,
                window,
                "fresh_mart_display_window",
                (x, -4.82, 0.38),
                0,
                (scale_x, 1, 1),
            )
            half_width = 2.46 * scale_x / 2
            spans.append((x - half_width, x + half_width))
        instance(collection, door, "fresh_mart_double_entry_left", (-0.62, -4.82, 0.30))
        right = instance(
            collection, door, "fresh_mart_double_entry_right", (0.62, -4.82, 0.30)
        )
        right.scale.x = -1
        spans.extend(((-1.22, -0.02), (0.02, 1.22)))
        door_centers = [-0.62, 0.62]
    # Every gap between modules is closed by a deep structural pier.  This
    # prevents an accidental open-front shell and gives jambs a real substrate.
    cursor = -7.50
    for left, right in sorted(spans):
        gap = left - cursor
        if gap > 0.12:
            add_box(
                collection,
                "storefront_structural_wall_pier",
                ((cursor + left) / 2, -4.65, 1.78),
                (gap - 0.035, 0.42, 2.96),
                wall_mat,
                0.014,
            )
        cursor = max(cursor, right)
    if 7.50 - cursor > 0.12:
        add_box(
            collection,
            "storefront_structural_wall_pier",
            ((cursor + 7.50) / 2, -4.65, 1.78),
            (7.50 - cursor - 0.035, 0.42, 2.96),
            wall_mat,
            0.014,
        )
    # Continuous head rail and end piers connect all modules.
    add_box(
        collection,
        "continuous_storefront_head",
        (0, -4.94, 3.23),
        (15.08, 0.24, 0.18),
        bpy.data.materials[P + "anodized_storefront_aluminum"],
        0.010,
    )
    for x in (-7.50, 7.50):
        add_box(
            collection,
            "storefront_end_pier",
            (x, -4.73, 1.75),
            (0.22, 0.42, 3.05),
            wall_mat,
            0.016,
        )
    return door_centers


def add_sign_and_canopy(collection, exterior, M, label, restaurant=False):
    sign_z = 4.98 if restaurant else 4.70
    sign_width = 9.25 if restaurant else 7.45
    panel_mat = M["restaurant_sign" if restaurant else "fresh_sign"]
    # Create a sign-specific band so the panel finish can differ while preserving
    # the required shared sign-band master as the dimensional template.
    instance(
        collection,
        exterior["sign_band"],
        "linked_sign_band_structure",
        (0, -4.78, sign_z),
        0,
        (sign_width, 1, 1),
    )
    add_box(
        collection,
        "sign_finish_face_panel",
        (0, -4.90, sign_z),
        (sign_width - 0.18, 0.055, 0.66),
        panel_mat,
        0.012,
    )
    add_box(
        collection,
        "sign_rear_shadow_gap",
        (0, -4.67, sign_z),
        (sign_width + 0.20, 0.055, 0.90),
        M["gasket"],
        0.010,
    )
    for z in (sign_z - 0.43, sign_z + 0.43):
        add_box(
            collection,
            "sign_folded_edge_trim",
            (0, -4.89, z),
            (sign_width + 0.12, 0.22, 0.055),
            M["dark_metal"],
            0.007,
        )
    for x in (-sign_width / 2 - 0.03, sign_width / 2 + 0.03):
        add_box(
            collection,
            "sign_side_return",
            (x, -4.89, sign_z),
            (0.060, 0.22, 0.80),
            M["dark_metal"],
            0.007,
        )
    for x in (-sign_width * 0.34, 0, sign_width * 0.34):
        add_cylinder(
            collection,
            "channel_letter_mounting_offset",
            (x, -4.93, sign_z),
            (0.035, 0.035, 0.070),
            M["dark_metal"],
            0.003,
            (math.pi / 2, 0, 0),
        )
    add_text(
        collection,
        "raised_channel_letters_" + label.replace(" ", "_"),
        label,
        (0, -4.985, sign_z),
        0.82 if restaurant else 0.86,
        0.115,
        M["letter_face"],
    )

    canopy_z = 3.70 if restaurant else 3.62
    bay_count = 14
    bay_width = 1.02
    first_x = -((bay_count - 1) * bay_width) / 2
    for i in range(bay_count):
        instance(
            collection,
            exterior["canopy"],
            "supported_canopy_bay",
            (first_x + i * bay_width, -4.79, canopy_z),
        )
    # Triangular steel brackets visibly connect the canopy to the facade.
    for x in (-5.8, -2.0, 2.0, 5.8):
        add_beam_between(
            collection,
            "canopy_wall_bracket",
            (x, -4.95, canopy_z - 0.10),
            (x, -4.95, canopy_z - 0.62),
            0.055,
            M["dark_metal"],
        )
        add_beam_between(
            collection,
            "canopy_diagonal_brace",
            (x, -4.95, canopy_z - 0.58),
            (x, -5.86, canopy_z - 0.16),
            0.055,
            M["dark_metal"],
        )
    add_box(
        collection,
        "canopy_end_cap_left",
        (-7.17, -5.42, canopy_z - 0.08),
        (0.075, 1.30, 0.24),
        M["canopy"],
        0.007,
    )
    add_box(
        collection,
        "canopy_end_cap_right",
        (7.17, -5.42, canopy_z - 0.08),
        (0.075, 1.30, 0.24),
        M["canopy"],
        0.007,
    )


def add_frontage(collection, M, door_centers, restaurant=False):
    add_box(
        collection,
        "continuous_pedestrian_frontage",
        (0, -5.92, 0.12),
        (15.60, 1.72, 0.18),
        M["sidewalk"],
        0.010,
    )
    add_box(
        collection,
        "integrated_front_curb",
        (0, -6.79, 0.10),
        (15.60, 0.18, 0.22),
        M["concrete"],
        0.010,
    )
    add_box(
        collection,
        "curb_gutter_transition",
        (0, -6.95, 0.045),
        (15.60, 0.34, 0.070),
        M["concrete"],
        0.008,
        (math.radians(3), 0, 0),
    )
    for x in (-5.20, -2.60, 2.60, 5.20):
        add_box(
            collection,
            "sidewalk_control_joint",
            (x, -5.92, 0.217),
            (0.024, 1.58, 0.008),
            M["gasket"],
            0.001,
        )
    for x in door_centers:
        add_box(
            collection,
            "flush_storefront_threshold",
            (x, -5.10, 0.225),
            (1.18, 0.50, 0.055),
            M["brushed_metal"],
            0.006,
        )
    entry_x = 5.80 if restaurant else 0
    add_box(
        collection,
        "recessed_entry_mat",
        (entry_x, -5.55, 0.225),
        (1.30 if restaurant else 2.25, 0.65, 0.030),
        M["entry_paver"],
        0.004,
    )
    # One planter and one bin provide useful frontage detail without blocking entry.
    planter_x = -6.25 if restaurant else -6.45
    add_box(
        collection,
        "anchored_frontage_planter",
        (planter_x, -5.82, 0.42),
        (0.80, 0.62, 0.62),
        M["dark_metal"],
        0.020,
    )
    add_box(
        collection,
        "planter_soil",
        (planter_x, -5.82, 0.75),
        (0.68, 0.50, 0.08),
        M["soil"],
        0.006,
    )
    for dx, dy, scale in (
        (-0.20, -0.10, 0.20),
        (0.12, 0.08, 0.24),
        (0.22, -0.12, 0.18),
        (-0.05, 0.12, 0.19),
    ):
        add_mesh(
            collection,
            "planter_foliage",
            sphere_mesh(),
            (planter_x + dx, -5.82 + dy, 0.91),
            (scale, scale, scale * 1.25),
            M["plant"],
            0.006,
        )
    bin_x = 6.75 if not restaurant else 7.00
    add_box(
        collection,
        "lidded_frontage_bin",
        (bin_x, -5.70, 0.44),
        (0.48, 0.42, 0.75),
        M["dark_metal"],
        0.016,
    )
    add_box(
        collection,
        "frontage_bin_lid",
        (bin_x, -5.70, 0.84),
        (0.54, 0.48, 0.10),
        M["canopy"],
        0.010,
    )
    # Compact wall lights are mounted to facade piers, clear of glazing.
    for x in (-7.25, 7.25):
        add_box(
            collection,
            "exterior_wall_light_backplate",
            (x, -4.98, 3.42),
            (0.20, 0.08, 0.26),
            M["dark_metal"],
            0.008,
        )
        add_box(
            collection,
            "exterior_wall_light_lens",
            (x, -5.04, 3.39),
            (0.14, 0.06, 0.14),
            M["light_lens"],
            0.006,
        )


def add_ceiling_grid_and_lights(collection, M, restaurant=False):
    xs = (-5.2, -2.6, 0, 2.6, 5.2)
    ys = (-2.0, 0.6, 2.8) if not restaurant else (-2.0, 0.5, 2.7)
    count = 0
    for row, y in enumerate(ys):
        for i, x in enumerate(xs):
            if restaurant and row == 2 and i in (0, 4):
                continue
            add_box(
                collection,
                "recessed_ceiling_light",
                (x, y, 3.94),
                (1.25, 0.34, 0.055),
                M["light_lens"],
                0.004,
            )
            if (i + row) % 2 == 0:
                add_area_light(
                    collection,
                    "interior_area_light",
                    (x, y, 3.88),
                    245 if restaurant else 285,
                    1.35,
                )
            count += 1
    return count


def add_floor_joints(collection, M, restaurant=False):
    mat = M["gasket"]
    for x in (-6, -4, -2, 0, 2, 4, 6):
        add_box(
            collection,
            "subtle_floor_joint",
            (x, -0.05, 0.257),
            (0.018, 8.10, 0.006),
            mat,
            0.001,
        )
    for y in (-3.0, -1.5, 0, 1.5, 3.0):
        add_box(
            collection,
            "subtle_floor_joint",
            (0, y, 0.257),
            (14.75, 0.018, 0.006),
            mat,
            0.001,
        )


def build_fresh_interior(collection, grocery, M):
    # Clear entry transition: x +/-1.05, y -4.3 to -2.2 remains empty.
    aisle_positions = [(-5.05, -0.45), (-2.55, -0.45), (2.05, -0.35)]
    for i, (x, y) in enumerate(aisle_positions):
        instance(
            collection,
            grocery["shelf"],
            "organized_grocery_aisle",
            (x, y, 0.26),
            math.pi / 2,
            (0.98, 0.98, 0.98),
        )
    # One short wall-side run has a different orientation and scale.
    instance(
        collection,
        grocery["shelf"],
        "left_wall_shelf_run",
        (-6.88, 2.15, 0.26),
        math.pi / 2,
        (0.72, 0.88, 0.98),
    )
    for x in (-5.15, -2.55, 0.05, 2.65, 5.25):
        instance(
            collection,
            grocery["fridge"],
            "continuous_refrigerator_section",
            (x, 3.72, 0.26),
            0,
            (0.94, 0.78, 0.94),
        )
    instance(
        collection,
        grocery["checkout"],
        "checkout_counter_near_entry",
        (4.70, -2.72, 0.26),
        0,
        (1.0, 1.0, 1.0),
    )
    add_box(
        collection,
        "checkout_queue_rail_base",
        (3.03, -3.58, 0.31),
        (0.10, 0.10, 0.10),
        M["dark_metal"],
        0.006,
    )
    add_cylinder(
        collection,
        "checkout_queue_post",
        (3.03, -3.58, 0.78),
        (0.045, 0.045, 0.43),
        M["brushed_metal"],
        0.004,
    )
    add_box(
        collection,
        "checkout_impulse_rack",
        (6.15, -2.60, 0.80),
        (0.72, 0.42, 1.05),
        M["shelf"],
        0.010,
    )
    for z in (0.52, 0.78, 1.04):
        add_box(
            collection,
            "impulse_rack_shelf",
            (6.15, -2.84, z),
            (0.64, 0.34, 0.035),
            M["shelf_edge"],
            0.004,
        )
    # Back-stock partition and visible staff access establish operational depth.
    add_box(
        collection,
        "back_stockroom_partition",
        (6.42, 2.55, 2.05),
        (1.75, 0.12, 3.55),
        M["interior_wall"],
        0.008,
    )
    add_box(
        collection,
        "back_stock_staff_door",
        (6.20, 2.45, 1.50),
        (1.05, 0.10, 2.52),
        M["dark_metal"],
        0.009,
    )
    return {
        "fresh_aisle_instances": len(aisle_positions) + 1,
        "fresh_fridge_instances": 5,
        "fresh_entry_clear_width_m": 2.10,
        "fresh_checkout_location": [4.70, -2.72],
    }


def place_table_set(collection, restaurant_assets, M, loc, seats=2, scale=(1, 1, 1)):
    x, y = loc
    instance(
        collection, restaurant_assets["table"], "dining_table", (x, y, 0.26), 0, scale
    )
    chair_positions = [(0, -0.78, 0), (0, 0.78, math.pi)]
    if seats == 4:
        chair_positions += [(-0.88, 0, -math.pi / 2), (0.88, 0, math.pi / 2)]
    for dx, dy, rot in chair_positions:
        instance(
            collection,
            restaurant_assets["chair"],
            "dining_chair_facing_table",
            (x + dx * scale[0], y + dy * scale[1], 0.26),
            rot,
        )
    # Table settings provide readable scale without turning into clutter.
    for dx in (-0.25, 0.25) if seats == 4 else (0,):
        add_cylinder(
            collection,
            "individual_table_plate",
            (x + dx, y, 1.065),
            (0.13, 0.13, 0.012),
            M["ceramic"],
            0.002,
        )
        add_cylinder(
            collection,
            "drinking_glass",
            (x + dx + 0.18, y + 0.08, 1.13),
            (0.035, 0.035, 0.085),
            M["glass"],
            0.001,
        )
    return len(chair_positions)


def build_restaurant_interior(collection, assets, M):
    chairs = 0
    tables = [
        ((-5.55, -2.55), 2, (0.72, 0.90, 1)),
        ((-3.25, -2.15), 4, (1, 1, 1)),
        ((-0.55, -2.25), 2, (0.72, 0.90, 1)),
        ((-5.10, 0.25), 4, (1, 1, 1)),
        ((-2.15, 0.55), 2, (0.72, 0.90, 1)),
    ]
    for loc, seats, scale in tables:
        chairs += place_table_set(collection, assets, M, loc, seats, scale)
    # Ordering counter faces the dining room; right-side entry route stays open.
    instance(
        collection,
        assets["counter"],
        "ordering_and_pickup_counter",
        (3.45, 1.20, 0.26),
        0,
    )
    add_box(
        collection,
        "counter_overhead_menu_rail",
        (3.10, 2.63, 2.73),
        (5.25, 0.12, 0.18),
        M["dark_metal"],
        0.008,
    )
    for i, x in enumerate((1.45, 2.55, 3.65, 4.75)):
        add_box(
            collection,
            "framed_menu_board",
            (x, 2.55, 2.75),
            (0.90, 0.075, 0.68),
            M["black"],
            0.010,
        )
        for row in range(4):
            add_box(
                collection,
                "menu_line",
                (x, 2.50, 2.95 - row * 0.14),
                (0.62 - row * 0.05, 0.012, 0.025),
                M["letter_face"],
                0.001,
            )
    # Back kitchen partition is assembled around a real pass-through opening.
    # The opening spans x=.90..5.60 and z=1.18..2.84 behind the service counter.
    add_box(
        collection,
        "back_kitchen_partition_left",
        (-3.20, 2.78, 1.55),
        (8.20, 0.14, 2.55),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "back_kitchen_partition_right",
        (6.45, 2.78, 1.55),
        (1.70, 0.14, 2.55),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "kitchen_pass_lower_wall",
        (3.25, 2.78, 0.72),
        (4.70, 0.14, 0.90),
        M["interior_wall"],
        0.008,
    )
    add_box(
        collection,
        "kitchen_pass_header",
        (3.25, 2.78, 3.42),
        (4.70, 0.14, 1.14),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "kitchen_pass_stainless_sill",
        (3.25, 2.67, 1.18),
        (4.82, 0.28, 0.065),
        M["brushed_metal"],
        0.006,
    )
    instance(
        collection, assets["prep"], "stainless_prep_station", (1.15, 3.45, 0.26), 0
    )
    instance(
        collection, assets["prep"], "stainless_prep_station", (-1.55, 3.45, 0.26), 0
    )
    # Cooking line: proportioned equipment, splashback, hood, sink, and shelving.
    for i, x in enumerate((-5.80, -4.45, -3.10)):
        add_box(
            collection,
            "kitchen_equipment_cabinet",
            (x, 3.63, 0.70),
            (1.12, 0.72, 0.86),
            M["brushed_metal"],
            0.015,
        )
        add_box(
            collection,
            "equipment_control_panel",
            (x, 3.23, 0.83),
            (1.00, 0.08, 0.22),
            M["black"],
            0.006,
        )
        for knob_x in (-0.30, 0, 0.30):
            add_cylinder(
                collection,
                "equipment_control_knob",
                (x + knob_x, 3.17, 0.84),
                (0.045, 0.045, 0.035),
                M["brushed_metal"],
                0.003,
                (math.pi / 2, 0, 0),
            )
    add_box(
        collection,
        "kitchen_stainless_splashback",
        (-4.45, 4.04, 1.65),
        (4.20, 0.055, 1.45),
        M["brushed_metal"],
        0.004,
    )
    add_box(
        collection,
        "kitchen_exhaust_hood",
        (-4.45, 3.76, 2.90),
        (4.45, 0.82, 0.48),
        M["brushed_metal"],
        0.016,
    )
    add_box(
        collection,
        "hood_exhaust_riser",
        (-4.45, 4.00, 3.45),
        (1.00, 0.45, 0.70),
        M["brushed_metal"],
        0.010,
    )
    add_box(
        collection,
        "utility_sink_cabinet",
        (5.85, 3.58, 0.66),
        (1.55, 0.70, 0.82),
        M["brushed_metal"],
        0.014,
    )
    add_box(
        collection,
        "utility_sink_basin",
        (5.85, 3.53, 1.05),
        (1.34, 0.55, 0.20),
        M["black"],
        0.010,
    )
    add_beam_between(
        collection,
        "sink_faucet_riser",
        (5.85, 3.58, 1.10),
        (5.85, 3.58, 1.48),
        0.035,
        M["brushed_metal"],
    )
    add_beam_between(
        collection,
        "sink_faucet_spout",
        (5.85, 3.58, 1.46),
        (5.85, 3.34, 1.46),
        0.035,
        M["brushed_metal"],
    )
    for z in (1.52, 2.02, 2.52):
        add_box(
            collection,
            "kitchen_wall_shelf",
            (5.72, 3.95, z),
            (1.70, 0.34, 0.055),
            M["brushed_metal"],
            0.006,
        )
    return {
        "restaurant_table_instances": len(tables),
        "restaurant_chair_instances": chairs,
        "restaurant_entry_path_width_m": 1.35,
        "restaurant_service_counter_location": [3.45, 1.20],
        "restaurant_back_kitchen_zone_y": [2.78, 4.15],
    }


def audit_scene(hidden, masters, fresh_stats, restaurant_stats):
    required = (
        "STOREFRONT_FRAME_MASTER",
        "STOREFRONT_DOOR_MASTER",
        "STOREFRONT_WINDOW_MASTER",
        "SIGN_BAND_MASTER",
        "CHANNEL_LETTER_MASTER",
        "CANOPY_MASTER",
        "GROCERY_SHELF_MASTER",
        "GROCERY_FRIDGE_MASTER",
        "CHECKOUT_MASTER",
        "DINING_TABLE_MASTER",
        "DINING_CHAIR_MASTER",
        "RESTAURANT_COUNTER_MASTER",
        "KITCHEN_PREP_MASTER",
    )
    missing = [name for name in required if bpy.data.collections.get(name) is None]
    new_objects = [obj for obj in bpy.data.objects if obj.name.startswith(P)]
    instances = [obj for obj in new_objects if obj.instance_type == "COLLECTION"]
    legacy_visible = []
    for collection_name in (FRESH_COLLECTION, RESTAURANT_COLLECTION):
        for obj in bpy.data.collections[collection_name].objects:
            if not obj.name.startswith(P) and not obj.hide_render:
                legacy_visible.append(obj.name)
    forbidden_names = [
        obj.name
        for obj in new_objects
        if any(
            t in obj.name.lower()
            for t in ("mystery", "floating", "placeholder", "random")
        )
    ]
    if missing or legacy_visible or forbidden_names:
        raise RuntimeError(
            {
                "missing_masters": missing,
                "visible_legacy": legacy_visible,
                "forbidden_names": forbidden_names,
            }
        )
    return {
        "pipeline_strategy": "complete rebuild; no legacy commercial mesh patched",
        "legacy_commercial_objects_hidden": sum(len(v) for v in hidden.values()),
        "visible_legacy_objects_in_shop_masters": len(legacy_visible),
        "new_all43_15_objects": len(new_objects),
        "linked_collection_instances": len(instances),
        "required_master_assets": list(required),
        "required_master_asset_count": len(required),
        "missing_master_assets": missing,
        "shared_mesh_policy": "all manufactured primitives share source cube/cylinder/sphere meshes; repeated assets are collection instances",
        "facade_depth_sequence_m": {
            "wall_plane_y": -4.40,
            "sign_front_y": -4.985,
            "glazing_frame_y": -4.89,
            "glass_y": -4.875,
            "canopy_front_y": -6.02,
        },
        "semantic_zones": {
            "fresh_mart": [
                "entry transition",
                "gondola aisles",
                "wall shelf",
                "rear refrigeration",
                "checkout",
                "staff access",
            ],
            "corner_kitchen": [
                "entry route",
                "two/four-seat dining",
                "ordering counter",
                "pickup",
                "back kitchen",
                "sink/utility",
            ],
        },
        "forbidden_unexplained_asset_name_count": len(forbidden_names),
        **fresh_stats,
        **restaurant_stats,
    }


def run():
    M = materials()
    hidden = hide_legacy_shop_objects()
    exterior = create_exterior_masters(M)
    products = create_product_masters(M)
    grocery = create_grocery_masters(M, products)
    restaurant_assets = create_restaurant_masters(M)

    fresh = bpy.data.collections[FRESH_COLLECTION]
    restaurant = bpy.data.collections[RESTAURANT_COLLECTION]
    add_store_shell(fresh, M, M["fresh_stucco"], restaurant=False)
    add_store_shell(restaurant, M, M["restaurant_stucco"], restaurant=True)
    fresh_doors = add_window_and_door_system(fresh, exterior, restaurant=False)
    restaurant_doors = add_window_and_door_system(restaurant, exterior, restaurant=True)
    add_sign_and_canopy(fresh, exterior, M, "FRESH MART", restaurant=False)
    add_sign_and_canopy(restaurant, exterior, M, "CORNER KITCHEN", restaurant=True)
    add_frontage(fresh, M, fresh_doors, restaurant=False)
    add_frontage(restaurant, M, restaurant_doors, restaurant=True)
    add_floor_joints(fresh, M)
    add_floor_joints(restaurant, M, restaurant=True)
    fresh_lights = add_ceiling_grid_and_lights(fresh, M)
    restaurant_lights = add_ceiling_grid_and_lights(restaurant, M, restaurant=True)
    fresh_stats = build_fresh_interior(fresh, grocery, M)
    restaurant_stats = build_restaurant_interior(restaurant, restaurant_assets, M)
    fresh_stats["fresh_ceiling_fixture_count"] = fresh_lights
    restaurant_stats["restaurant_ceiling_fixture_count"] = restaurant_lights
    stats = audit_scene(hidden, exterior, fresh_stats, restaurant_stats)
    stats["material_system_count"] = len(
        [m for m in bpy.data.materials if m.name.startswith(P)]
    )
    stats[
        "daylight_render_policy"
    ] = "existing daytime world retained; interiors receive neutral area fixtures"
    return stats
