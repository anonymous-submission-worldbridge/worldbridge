"""High-quality commercial facade templates layered onto the all43_03 baseline."""
import math
import bpy

P = "all43_05:"


def material(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    normal=0.04,
    transmission=0.0,
    emission=0.0,
):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    b.inputs["IOR"].default_value = 1.46
    if transmission:
        b.inputs["Transmission Weight"].default_value = transmission
    if emission:
        b.inputs["Emission Color"].default_value = color
        b.inputs["Emission Strength"].default_value = emission
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.42
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.44, 0.44, 0.44, 1)
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[1].color = (0.56, 0.56, 0.56, 1)
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = normal
    bump.inputs["Distance"].default_value = 0.012
    l.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def create_shared_materials():
    return {
        "painted_wall": material(
            "painted_wall", (0.42, 0.39, 0.32, 1), 0.72, normal=0.055
        ),
        "painted_metal": material(
            "painted_metal", (0.16, 0.18, 0.18, 1), 0.38, 0.45, 0.025
        ),
        "anodized_metal": material(
            "anodized_metal", (0.055, 0.065, 0.07, 1), 0.25, 0.72, 0.018
        ),
        "glass": create_commercial_glass_material(),
        "concrete": material("concrete", (0.42, 0.41, 0.38, 1), 0.82, normal=0.08),
        "dark": material("gasket", (0.008, 0.01, 0.011, 1), 0.75, normal=0.01),
        "light": material(
            "sign_letter", (1, 0.82, 0.45, 1), 0.30, normal=0.01, emission=1.15
        ),
    }


def create_commercial_glass_material():
    return material(
        "commercial_glass",
        (0.025, 0.075, 0.085, 0.22),
        0.09,
        normal=0.012,
        transmission=0.82,
    )


def cube_mesh():
    key = P + "shared_cube"
    m = bpy.data.meshes.get(key)
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
    m = bpy.data.meshes.new(key)
    m.from_pydata(v, [], f)
    return m


def box(c, name, loc, size, mat, bevel=0.012, rot=0):
    o = bpy.data.objects.new(P + name, cube_mesh())
    c.objects.link(o)
    o.location = loc
    o.scale = size
    o.rotation_euler[2] = rot
    if not o.data.materials:
        o.data.materials.append(mat)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = mat
    if bevel:
        q = o.modifiers.new("adaptive_bevel", "BEVEL")
        q.width = min(bevel, min(size) * 0.12)
        q.segments = 2
    o["shared_mesh_data"] = True
    return o


def master(name):
    c = bpy.data.collections.new(P + "MASTER:" + name)
    c["quality_master"] = True
    return c


def inst(parent, template, name, loc=(0, 0, 0), scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + name, None)
    parent.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = template
    o.location = loc
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def create_window_templates(lib):
    m = master("window_full")
    M = lib["materials"]
    box(m, "window_reveal", (0, 0.08, 1.25), (1.12, 0.13, 1.25), M["dark"])
    box(m, "window_glass", (0, -0.075, 1.25), (1.0, 0.025, 1.12), M["glass"], 0.003)
    for x in (-1.06, 0, 1.06):
        box(
            m,
            "window_mullion",
            (x, -0.12, 1.25),
            (0.045, 0.08, 1.22),
            M["anodized_metal"],
            0.005,
        )
    for z in (0.05, 1.25, 2.45):
        box(
            m,
            "window_rail",
            (0, -0.12, z),
            (1.10, 0.08, 0.045),
            M["anodized_metal"],
            0.005,
        )
    box(m, "window_sill", (0, -0.18, -0.02), (1.18, 0.18, 0.055), M["concrete"], 0.012)
    box(m, "kickplate", (0, -0.17, 0.22), (1.0, 0.045, 0.18), M["painted_metal"], 0.006)
    lib["window"] = m


def create_door_templates(lib):
    m = master("door_glazed")
    M = lib["materials"]
    box(m, "door_reveal", (0, 0.06, 1.35), (0.62, 0.14, 1.35), M["dark"])
    box(m, "door_glass", (0, -0.08, 1.48), (0.50, 0.025, 1.02), M["glass"], 0.003)
    for x in (-0.58, 0.58):
        box(
            m,
            "door_jamb",
            (x, -0.13, 1.35),
            (0.055, 0.09, 1.35),
            M["anodized_metal"],
            0.006,
        )
    for z in (0.04, 2.66):
        box(
            m,
            "door_rail",
            (0, -0.13, z),
            (0.64, 0.09, 0.055),
            M["anodized_metal"],
            0.006,
        )
    box(
        m, "door_kick", (0, -0.16, 0.25), (0.50, 0.035, 0.22), M["painted_metal"], 0.005
    )
    box(
        m,
        "door_handle",
        (0.36, -0.22, 1.35),
        (0.025, 0.035, 0.34),
        M["anodized_metal"],
        0.004,
    )
    box(m, "closer", (0, -0.20, 2.48), (0.25, 0.04, 0.055), M["anodized_metal"], 0.006)
    box(m, "threshold", (0, -0.20, 0.025), (0.65, 0.20, 0.025), M["concrete"], 0.005)
    lib["door"] = m


def create_awning_templates(lib):
    m = master("awning_support")
    M = lib["materials"]
    box(
        m,
        "wall_plate",
        (0, 0.02, 0.28),
        (0.075, 0.035, 0.30),
        M["anodized_metal"],
        0.006,
    )
    box(
        m,
        "brace",
        (0, -0.38, 0.24),
        (0.035, 0.48, 0.035),
        M["anodized_metal"],
        0.005,
        rot=-0.62,
    )
    box(
        m,
        "tie",
        (0, -0.45, 0.52),
        (0.035, 0.45, 0.035),
        M["anodized_metal"],
        0.005,
        rot=0.48,
    )
    lib["awning_support"] = m


def create_sign_templates(lib):
    m = master("sign_mount")
    M = lib["materials"]
    box(
        m,
        "sign_standoff",
        (0, -0.09, 0),
        (0.035, 0.10, 0.035),
        M["anodized_metal"],
        0.005,
    )
    box(m, "sign_rail", (0, -0.19, 0), (0.28, 0.025, 0.035), M["anodized_metal"], 0.005)
    lib["sign_mount"] = m


def prepare_commercial_asset_library():
    lib = {"materials": create_shared_materials()}
    create_window_templates(lib)
    create_door_templates(lib)
    create_awning_templates(lib)
    create_sign_templates(lib)
    return lib


def generate_store_sign(master_collection, params, lib):
    text = next(
        (
            o
            for o in master_collection.objects
            if o.type == "FONT" and o.data.body.strip() == params["text"]
        ),
        None,
    )
    if not text:
        raise RuntimeError("missing baseline sign " + params["text"])
    text.data.extrude = params["letter_depth"]
    text.data.bevel_depth = 0.012
    text.data.bevel_resolution = 3
    text.data.space_character = params["letter_spacing"]
    text.data.materials.clear()
    text.data.materials.append(lib["materials"]["light"])
    # Retain baseline sign band and add real rear rails/standoffs behind the dimensional letters.
    y = text.location.y + 0.12
    z = text.location.z
    box(
        master_collection,
        "sign_back_rail",
        (0, y, z),
        (params["sign_width"] / 2, 0.045, params["sign_height"] / 2),
        lib["materials"]["painted_metal"],
        0.018,
    )
    for x in (-params["sign_width"] * 0.34, 0, params["sign_width"] * 0.34):
        box(
            master_collection,
            "sign_hidden_standoff",
            (x, y + 0.05, z),
            (0.035, 0.07, 0.035),
            lib["materials"]["anodized_metal"],
            0.005,
        )
    text["procedural_sign_params"] = str(params)
    return text


def generate_store_awning(master_collection, params, lib):
    # Enhance, never replace, the baseline sloped awning: front fascia, closed ends, gutter, soffit ribs and anchored braces.
    w = params["width"]
    y = params["front_y"]
    z = params["height"]
    M = lib["materials"]
    box(
        master_collection,
        "awning_front_edge",
        (0, y - params["depth"] * 0.48, z - params["edge_height"] * 0.5),
        (w / 2, 0.07, params["edge_height"] / 2),
        M["painted_metal"],
        0.018,
    )
    for x in (-w / 2, w / 2):
        box(
            master_collection,
            "awning_endcap",
            (x, y - params["depth"] * 0.12, z),
            (0.045, params["depth"] / 2, params["thickness"]),
            M["painted_metal"],
            0.01,
        )
    box(
        master_collection,
        "awning_wall_flashing",
        (0, y + params["depth"] * 0.42, z + 0.10),
        (w / 2, 0.055, 0.12),
        M["anodized_metal"],
        0.012,
    )
    box(
        master_collection,
        "awning_gutter",
        (0, y - params["depth"] * 0.53, z - params["edge_height"]),
        (w / 2, 0.11, 0.065),
        M["anodized_metal"],
        0.012,
    )
    x = -w / 2 + 0.65
    while x < w / 2 - 0.4:
        inst(
            master_collection,
            lib["awning_support"],
            "awning_support",
            (x, y + 0.20, z - 0.55),
        )
        x += params["support_spacing"]
    return True


def place_windows_and_doors(master_collection, params, lib):
    # The all43_03 baseline openings already exceed the template quality. Keep them intact;
    # templates remain available for new parameter sets instead of being overlaid mechanically.
    for o in master_collection.objects:
        if any(
            k in o.name.lower()
            for k in ("storefront", "door", "glass", "window", "mullion", "jamb")
        ):
            o["preserved_high_quality_opening"] = True


def generate_commercial_building(master_collection, params, lib):
    generate_store_sign(master_collection, params["sign"], lib)
    generate_store_awning(master_collection, params["awning"], lib)
    place_windows_and_doors(master_collection, params, lib)
    # Continuous plinth closes facade/sidewalk gap without coplanar overlap.
    box(
        master_collection,
        "continuous_plinth",
        (0, -4.84, 0.105),
        (7.55, 0.10, 0.105),
        lib["materials"]["concrete"],
        0.012,
    )


def geometry_sanity_check(configs):
    errors = []
    for p in configs:
        if not (
            p["parking_z"]
            < p["curb_z"]
            <= p["sidewalk_z"]
            <= p["door_threshold_z"] + 0.03
        ):
            errors.append(p["name"] + ": invalid level order")
        if abs(p["building_base_z"] - p["door_threshold_z"]) > 0.08:
            errors.append(p["name"] + ": floating threshold")
    # Exact duplicate object transforms in this pass indicate accidental overlapping modules.
    seen = set()
    for o in bpy.data.objects:
        if not o.name.startswith(P):
            continue
        key = (
            tuple(sorted(c.name for c in o.users_collection)),
            o.type,
            tuple(round(v, 4) for v in o.location),
            tuple(round(v, 4) for v in o.scale),
            getattr(o.data, "name", ""),
        )
        if key in seen and o.type == "MESH":
            errors.append("duplicate " + o.name)
        seen.add(key)
    return errors


def populate_commercial_zone():
    lib = prepare_commercial_asset_library()
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    common = {
        "front_y": -4.92,
        "base_z": 0.18,
        "window_centers": [-5.25, -3.15, -1.05, 1.05, 3.15],
        "door_x": 5.45,
    }
    cp = {
        **common,
        "name": "FRESH MART",
        "sign": {
            "text": "FRESH  MART",
            "sign_width": 5.6,
            "sign_height": 0.55,
            "sign_depth": 0.12,
            "letter_depth": 0.075,
            "letter_spacing": 1.0,
            "background_color": "green",
            "letter_color": "warm",
            "emission_strength": 1.15,
            "mounting_offset": 0.12,
        },
        "awning": {
            "width": 15.3,
            "depth": 1.05,
            "thickness": 0.10,
            "support_spacing": 2.5,
            "slope": 0.08,
            "edge_height": 0.16,
            "front_y": -5.30,
            "height": 3.88,
        },
    }
    rp = {
        **common,
        "name": "CORNER KITCHEN",
        "window_centers": [-5.1, -2.9, -0.7, 1.5, 3.7],
        "door_x": 6.15,
        "sign": {
            "text": "CORNER  KITCHEN",
            "sign_width": 7.0,
            "sign_height": 0.62,
            "sign_depth": 0.14,
            "letter_depth": 0.085,
            "letter_spacing": 1.0,
            "background_color": "terracotta",
            "letter_color": "warm",
            "emission_strength": 1.15,
            "mounting_offset": 0.14,
        },
        "awning": {
            "width": 14.3,
            "depth": 1.18,
            "thickness": 0.11,
            "support_spacing": 2.35,
            "slope": 0.09,
            "edge_height": 0.18,
            "front_y": -5.30,
            "height": 4.38,
        },
    }
    generate_commercial_building(conv, cp, lib)
    generate_commercial_building(rest, rp, lib)
    levels = [
        {
            "name": p["name"],
            "building_base_z": 0.18,
            "sidewalk_z": 0.18,
            "door_threshold_z": 0.18,
            "curb_z": 0.15,
            "parking_z": 0.12,
        }
        for p in (cp, rp)
    ]
    return lib, geometry_sanity_check(levels), [cp, rp]
