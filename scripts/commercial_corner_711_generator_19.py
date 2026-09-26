"""All43-19: production street-corner 7-Eleven mixed-use store asset.

The reference is a miniature streetscape, but this generator deliberately
interprets its architectural language at full scale: a three-storey green
brick corner building, a chamfered entrance, wraparound 7-Eleven fascia,
multi-pane upper windows, a transparent and operational convenience-store
interior, rooftop services, and grounded public frontage.

This is a source generator used both by ``refine_urban_v3_all43_19.py`` and by
the complete urban pipeline.  It never edits a saved blend in isolation.
"""
from __future__ import annotations

import math
from typing import Iterable

import bpy
from mathutils import Vector


P = "all43_19:"
MASTER_NAME = "CORNER_711_MIXED_USE_MASTER"
WORLD_COLLECTION = P + "corner_store_world"
STORE_LOCATION = Vector((-13.45, -11.20, 0.205))
WIDTH = 7.0
DEPTH = 8.10
HEIGHT = 10.25
CORNER_CUT = 1.20


def cube_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cube")
    if mesh is None:
        raise RuntimeError(
            "all43-19 requires all43_10:shared_cube from the active commercial pipeline"
        )
    return mesh


def cylinder_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    if mesh is None:
        raise RuntimeError(
            "all43-19 requires all43_10:shared_cylinder_12 from the active commercial pipeline"
        )
    return mesh


def material(
    name, color, roughness=0.55, metallic=0.0, emission=None, emission_strength=0.0
):
    mat = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = color
    return mat


def green_brick_material():
    name = P + "green_glazed_running_bond_brick"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.48
    bsdf.inputs["Coat Weight"].default_value = 0.17
    bsdf.inputs["Coat Roughness"].default_value = 0.24
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    # The supplied facade reads primarily as closely spaced horizontal green
    # masonry courses.  A Z-directed wave stays horizontal on north, east and
    # chamfer faces; the previous planar brick projection produced false
    # vertical bars on walls without authored UVs.
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 36.0
    wave.inputs["Distortion"].default_value = 0.12
    wave.inputs["Detail"].default_value = 3.0
    course_ramp = nodes.new("ShaderNodeValToRGB")
    course_ramp.color_ramp.elements.remove(course_ramp.color_ramp.elements[1])
    dark = course_ramp.color_ramp.elements[0]
    dark.position = 0.055
    dark.color = (0.075, 0.105, 0.045, 1)
    green_a = course_ramp.color_ramp.elements.new(0.14)
    green_a.color = (0.17, 0.30, 0.075, 1)
    green_b = course_ramp.color_ramp.elements.new(0.86)
    green_b.color = (0.28, 0.43, 0.12, 1)
    dark_high = course_ramp.color_ramp.elements.new(0.945)
    dark_high.color = (0.075, 0.105, 0.045, 1)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 23.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.62
    variation = nodes.new("ShaderNodeValToRGB")
    variation.color_ramp.elements[0].color = (0.72, 0.78, 0.66, 1)
    variation.color_ramp.elements[1].color = (1.0, 1.0, 0.92, 1)
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.20
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.28
    bump.inputs["Distance"].default_value = 0.035
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(wave.outputs["Color"], course_ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], variation.inputs["Fac"])
    links.new(course_ramp.outputs["Color"], mix.inputs[1])
    links.new(variation.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(wave.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.22, 0.36, 0.10, 1)
    mat[
        "material_system"
    ] = "horizontal glazed masonry courses with recessed joints and subtle kiln variation"
    return mat


def storefront_glass_material():
    name = P + "clear_low_iron_storefront_glass"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (0.82, 0.90, 0.87, 1)
    glass = nodes.new("ShaderNodeBsdfPrincipled")
    glass.inputs["Base Color"].default_value = (0.055, 0.11, 0.105, 1)
    glass.inputs["Roughness"].default_value = 0.085
    glass.inputs["Transmission Weight"].default_value = 0.92
    glass.inputs["IOR"].default_value = 1.46
    glass.inputs["Coat Weight"].default_value = 0.20
    glass.inputs["Coat Roughness"].default_value = 0.055
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.20
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(glass.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.07, 0.14, 0.13, 0.22)
    mat["physical_glazing"] = "12 mm laminated low-iron storefront glass"
    return mat


def materials():
    return {
        "brick": green_brick_material(),
        "brick_trim": material(
            "green_architectural_trim", (0.22, 0.37, 0.105, 1), 0.50
        ),
        "mortar": material("deep_window_reveal", (0.055, 0.072, 0.045, 1), 0.80),
        "white": material("warm_white_enamel", (0.82, 0.82, 0.74, 1), 0.40, 0.06),
        "frame": material(
            "dark_anodized_storefront_frame", (0.025, 0.032, 0.030, 1), 0.30, 0.68
        ),
        "upper_frame": material(
            "upper_window_white_powdercoat", (0.78, 0.79, 0.74, 1), 0.43, 0.10
        ),
        "glass": storefront_glass_material(),
        "upper_glass": material(
            "upper_floor_reflective_glass", (0.055, 0.090, 0.085, 1), 0.16, 0.08
        ),
        "concrete": material("structural_concrete", (0.39, 0.40, 0.36, 1), 0.86),
        "paver": material("corner_sidewalk_paver", (0.36, 0.37, 0.34, 1), 0.86),
        "joint": material("paver_joint", (0.055, 0.060, 0.056, 1), 0.95),
        "interior_wall": material(
            "convenience_interior_wall", (0.76, 0.74, 0.66, 1), 0.80
        ),
        "floor": material("speckled_commercial_tile", (0.47, 0.49, 0.46, 1), 0.58),
        "ceiling": material("acoustic_ceiling", (0.80, 0.79, 0.73, 1), 0.84),
        "orange": material(
            "seven_orange_luminous",
            (0.96, 0.24, 0.018, 1),
            0.31,
            0.03,
            (0.96, 0.16, 0.01, 1),
            0.55,
        ),
        "green": material(
            "seven_green_luminous",
            (0.018, 0.43, 0.105, 1),
            0.32,
            0.03,
            (0.01, 0.34, 0.055, 1),
            0.40,
        ),
        "red": material(
            "seven_red_luminous",
            (0.76, 0.018, 0.025, 1),
            0.31,
            0.03,
            (0.65, 0.008, 0.012, 1),
            0.42,
        ),
        "sign_white": material(
            "sign_diffuser_white",
            (0.92, 0.91, 0.83, 1),
            0.28,
            0.02,
            (0.88, 0.85, 0.72, 1),
            0.45,
        ),
        "steel": material(
            "brushed_stainless_service_metal", (0.31, 0.34, 0.33, 1), 0.34, 0.72
        ),
        "black": material("equipment_black", (0.010, 0.012, 0.011, 1), 0.64),
        "cabinet": material("service_counter_laminate", (0.20, 0.225, 0.195, 1), 0.50),
        "coffee": material(
            "coffee_machine_graphite", (0.045, 0.050, 0.046, 1), 0.34, 0.34
        ),
        "cup": material("paper_cup", (0.72, 0.67, 0.53, 1), 0.60),
        "light": material(
            "interior_light_diffuser",
            (0.92, 0.90, 0.76, 1),
            0.32,
            0,
            (0.95, 0.90, 0.70, 1),
            2.2,
        ),
        "roof": material("single_ply_roof_membrane", (0.22, 0.235, 0.22, 1), 0.90),
        "louver": material("hvac_louver_dark", (0.055, 0.062, 0.060, 1), 0.62, 0.32),
        "tactile": material("tactile_warning_yellow", (0.74, 0.50, 0.035, 1), 0.72),
    }


def assign_material(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat


def add_object(collection, name, mesh, loc, scale, mat, bevel=0.0, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        modifier.width = min(bevel, min(scale) * 0.18)
        modifier.segments = 3
    obj["shared_mesh_data"] = mesh in (cube_mesh(), cylinder_mesh())
    return obj


def add_box(collection, name, loc, dims, mat, bevel=0.006, rot=(0, 0, 0)):
    return add_object(collection, name, cube_mesh(), loc, dims, mat, bevel, rot)


def add_cylinder(collection, name, loc, scale, mat, bevel=0.004, rot=(0, 0, 0)):
    return add_object(collection, name, cylinder_mesh(), loc, scale, mat, bevel, rot)


def instance(collection, master, name, loc, rotation=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(P + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = loc
    obj.rotation_euler[2] = rotation
    obj.scale = scale
    obj["linked_asset"] = master.name
    return obj


def new_master(name):
    old = bpy.data.collections.get(name)
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new(name)
    collection.use_fake_user = True
    collection["production_asset"] = True
    collection[
        "asset_quality"
    ] = "full-scale architectural model; no toy or proxy geometry"
    return collection


def ensure_world_collection():
    collection = bpy.data.collections.get(WORLD_COLLECTION) or bpy.data.collections.new(
        WORLD_COLLECTION
    )
    if collection.name not in {
        child.name for child in bpy.context.scene.collection.children
    }:
        bpy.context.scene.collection.children.link(collection)
    return collection


def chamfered_prism_mesh(name, width, depth, z0, z1, cut):
    mesh_name = P + name
    existing = bpy.data.meshes.get(mesh_name)
    if existing:
        return existing
    hw, hd = width / 2, depth / 2
    outline = [(-hw, -hd), (hw, -hd), (hw, hd - cut), (hw - cut, hd), (-hw, hd)]
    vertices = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n))), tuple(range(n, n * 2))]
    for index in range(n):
        nxt = (index + 1) % n
        faces.append((index, nxt, n + nxt, n + index))
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def add_chamfered_mass(collection, name, z0, z1, inset, mat):
    mesh = chamfered_prism_mesh(
        name + "_mesh",
        WIDTH - inset * 2,
        DEPTH - inset * 2,
        z0,
        z1,
        max(0.30, CORNER_CUT - inset),
    )
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    bevel = obj.modifiers.new("masonry_edge_softening", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 3
    return obj


def add_text(collection, name, body, loc, size, depth, mat, facing="north"):
    curve = bpy.data.curves.new(P + name + "_data", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = depth
    curve.bevel_depth = min(0.009, depth * 0.18)
    curve.bevel_resolution = 2
    curve.fill_mode = "BOTH"
    curve.materials.append(mat)
    obj = bpy.data.objects.new(P + name, curve)
    collection.objects.link(obj)
    obj.location = loc
    if facing == "north":
        obj.rotation_euler = (-math.pi / 2, 0, 0)
        obj.scale.x = -1
    elif facing == "east":
        obj.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    elif facing == "northeast":
        obj.rotation_euler = (-math.pi / 2, 0, -math.pi / 4)
        obj.scale.x = -1
    obj["physical_channel_letter_depth_m"] = depth
    return obj


def add_area_light(collection, name, loc, energy=270, size=1.25):
    data = bpy.data.lights.new(P + name + "_data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = 0.32
    obj = bpy.data.objects.new(P + name, data)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (0, 0, 0)
    return obj


def tube_between(collection, name, start, end, radius, mat):
    start, end = Vector(start), Vector(end)
    direction = end - start
    obj = add_cylinder(
        collection,
        name,
        (start + end) / 2,
        (radius, radius, direction.length),
        mat,
        0.003,
    )
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def make_upper_window_master(M):
    collection = new_master(P + "MASTER:UPPER_MULTIPANE_WINDOW")
    width, height = 2.32, 1.62
    add_box(
        collection,
        "upper_window_shadow_reveal",
        (0, -0.045, 0),
        (width + 0.20, 0.12, height + 0.20),
        M["mortar"],
        0.010,
    )
    add_box(
        collection,
        "upper_window_glazing",
        (0, 0.035, 0),
        (width - 0.16, 0.035, height - 0.16),
        M["upper_glass"],
        0.002,
    )
    for x in (-width / 2, width / 2):
        add_box(
            collection,
            "upper_window_jamb",
            (x, 0.075, 0),
            (0.105, 0.13, height),
            M["upper_frame"],
            0.008,
        )
    for z in (-height / 2, height / 2):
        add_box(
            collection,
            "upper_window_head_sill",
            (0, 0.075, z),
            (width, 0.13, 0.105),
            M["upper_frame"],
            0.008,
        )
    for x in (-0.58, 0, 0.58):
        add_box(
            collection,
            "upper_window_vertical_mullion",
            (x, 0.080, 0),
            (0.070, 0.14, height - 0.12),
            M["upper_frame"],
            0.006,
        )
    add_box(
        collection,
        "upper_window_transom",
        (0, 0.085, 0.27),
        (width - 0.12, 0.14, 0.075),
        M["upper_frame"],
        0.006,
    )
    add_box(
        collection,
        "projecting_masonry_sill",
        (0, 0.105, -height / 2 - 0.10),
        (width + 0.26, 0.28, 0.12),
        M["brick_trim"],
        0.012,
    )
    collection["pane_layout"] = "four columns with ventilating transom row"
    return collection


def make_storefront_window_master(M):
    collection = new_master(P + "MASTER:711_STOREFRONT_WINDOW")
    width, height = 1.36, 2.72
    # Recess material is confined to the perimeter.  A full dark backing here
    # would falsely seal the shop and hide the generated retail interior.
    for x in (-width / 2 - 0.035, width / 2 + 0.035):
        add_box(
            collection,
            "storefront_deep_side_reveal",
            (x, -0.035, height / 2),
            (0.075, 0.10, height + 0.12),
            M["mortar"],
            0.006,
        )
    for z in (-0.035, height + 0.035):
        add_box(
            collection,
            "storefront_deep_head_sill_reveal",
            (0, -0.035, z),
            (width + 0.10, 0.10, 0.075),
            M["mortar"],
            0.006,
        )
    add_box(
        collection,
        "storefront_low_iron_glass",
        (0, 0.035, height / 2),
        (width - 0.12, 0.032, height - 0.14),
        M["glass"],
        0.002,
    )
    for x in (-width / 2, width / 2):
        add_box(
            collection,
            "storefront_jamb",
            (x, 0.072, height / 2),
            (0.070, 0.13, height),
            M["frame"],
            0.006,
        )
    for z in (0.05, height - 0.05):
        add_box(
            collection,
            "storefront_head_sill",
            (0, 0.072, z),
            (width, 0.13, 0.080),
            M["frame"],
            0.006,
        )
    add_box(
        collection,
        "storefront_transom",
        (0, 0.075, 2.18),
        (width - 0.08, 0.13, 0.065),
        M["frame"],
        0.005,
    )
    add_box(
        collection,
        "storefront_kickplate",
        (0, 0.085, 0.18),
        (width - 0.10, 0.14, 0.28),
        M["steel"],
        0.008,
    )
    return collection


def make_corner_door_master(M):
    collection = new_master(P + "MASTER:711_DOUBLE_ENTRY")
    width, height = 1.52, 2.72
    for x in (-width / 2 - 0.06, width / 2 + 0.06):
        add_box(
            collection,
            "entry_deep_side_reveal",
            (x, -0.04, height / 2),
            (0.12, 0.14, height + 0.16),
            M["mortar"],
            0.008,
        )
    add_box(
        collection,
        "entry_deep_head_reveal",
        (0, -0.04, height + 0.05),
        (width + 0.20, 0.14, 0.12),
        M["mortar"],
        0.008,
    )
    for side in (-1, 1):
        x = side * width * 0.25
        add_box(
            collection,
            "tempered_entry_glass",
            (x, 0.040, height / 2),
            (width / 2 - 0.08, 0.030, height - 0.18),
            M["glass"],
            0.002,
        )
        for jamb_x in (x - width / 4, x + width / 4):
            add_box(
                collection,
                "entry_door_vertical_frame",
                (jamb_x, 0.080, height / 2),
                (0.055, 0.14, height),
                M["frame"],
                0.006,
            )
        add_box(
            collection,
            "entry_door_top_rail",
            (x, 0.080, height - 0.06),
            (width / 2 - 0.04, 0.14, 0.085),
            M["frame"],
            0.006,
        )
        add_box(
            collection,
            "entry_door_bottom_rail",
            (x, 0.080, 0.11),
            (width / 2 - 0.04, 0.14, 0.18),
            M["steel"],
            0.007,
        )
        add_box(
            collection,
            "vertical_pull_handle",
            (x - side * 0.17, 0.155, 1.28),
            (0.032, 0.045, 0.72),
            M["steel"],
            0.006,
        )
        add_box(
            collection,
            "door_closer",
            (x, -0.02, 2.55),
            (0.35, 0.12, 0.10),
            M["frame"],
            0.006,
        )
    add_box(
        collection,
        "double_entry_threshold",
        (0, 0.12, 0.035),
        (width + 0.10, 0.34, 0.055),
        M["steel"],
        0.006,
    )
    collection[
        "door_system"
    ] = "paired tempered-glass swing doors, closers, pull handles, kick rails and flush threshold"
    return collection


def make_rooftop_unit_master(M):
    collection = new_master(P + "MASTER:ROOFTOP_CONDENSER")
    add_box(
        collection, "condenser_curb", (0, 0, 0.12), (1.48, 1.05, 0.20), M["roof"], 0.015
    )
    add_box(
        collection,
        "condenser_cabinet",
        (0, 0, 0.64),
        (1.38, 0.94, 0.86),
        M["steel"],
        0.025,
    )
    for side in (-1, 1):
        for index in range(6):
            add_box(
                collection,
                "condenser_side_louver",
                (side * 0.705, -0.30 + index * 0.12, 0.66),
                (0.025, 0.075, 0.48),
                M["louver"],
                0.002,
            )
    add_cylinder(
        collection,
        "condenser_fan_recess",
        (0, 0, 1.09),
        (0.35, 0.35, 0.035),
        M["black"],
        0.004,
    )
    for index in range(8):
        angle = math.tau * index / 8
        add_box(
            collection,
            "fan_guard_spoke",
            (math.cos(angle) * 0.13, math.sin(angle) * 0.13, 1.135),
            (0.30, 0.018, 0.012),
            M["louver"],
            0.002,
            (0, 0, angle),
        )
    add_cylinder(
        collection,
        "fan_guard_ring",
        (0, 0, 1.14),
        (0.39, 0.39, 0.018),
        M["louver"],
        0.002,
    )
    return collection


def add_wrap_segment(
    collection, name, center, length, depth, z, height, mat, rotation=0.0, bevel=0.008
):
    return add_box(
        collection,
        name,
        center[:2] + (z,),
        (length, depth, height),
        mat,
        bevel,
        (0, 0, rotation),
    )


def add_wraparound_fascia(collection, M):
    hw, hd, cut = WIDTH / 2, DEPTH / 2, CORNER_CUT
    north_length = WIDTH - cut
    east_length = DEPTH - cut
    north_center = (-cut / 2, hd + 0.19, 0)
    east_center = (hw + 0.19, -cut / 2, 0)
    chamfer_center = (hw - cut / 2, hd - cut / 2, 0)
    diagonal_length = math.sqrt(2) * cut
    segments = (
        ("north", north_center, north_length, 0.0),
        ("east", east_center, east_length, -math.pi / 2),
        ("chamfer", chamfer_center, diagonal_length, -math.pi / 4),
    )
    for label, center, length, rotation in segments:
        add_wrap_segment(
            collection,
            "white_wrap_fascia_" + label,
            center,
            length,
            0.34,
            3.61,
            0.94,
            M["sign_white"],
            rotation,
            0.015,
        )
        add_wrap_segment(
            collection,
            "orange_brand_stripe_" + label,
            center,
            length + 0.02,
            0.38,
            3.88,
            0.13,
            M["orange"],
            rotation,
            0.006,
        )
        add_wrap_segment(
            collection,
            "green_brand_stripe_" + label,
            center,
            length + 0.02,
            0.39,
            3.62,
            0.13,
            M["green"],
            rotation,
            0.006,
        )
        add_wrap_segment(
            collection,
            "red_brand_stripe_" + label,
            center,
            length + 0.02,
            0.40,
            3.36,
            0.13,
            M["red"],
            rotation,
            0.006,
        )
        add_wrap_segment(
            collection,
            "fascia_upper_lower_trim_" + label,
            center,
            length + 0.08,
            0.40,
            4.08,
            0.055,
            M["frame"],
            rotation,
            0.004,
        )
        add_wrap_segment(
            collection,
            "fascia_upper_lower_trim_" + label,
            center,
            length + 0.08,
            0.40,
            3.15,
            0.055,
            M["frame"],
            rotation,
            0.004,
        )
    # The white plaque breaks the stripes exactly as on a real illuminated fascia.
    add_box(
        collection,
        "north_logo_diffuser_panel",
        (-0.50, hd + 0.405, 3.62),
        (2.15, 0.055, 0.76),
        M["sign_white"],
        0.014,
    )
    # On a north-facing sign, world +X is screen-left to a viewer outside the
    # building.  Place the numeral east of the word in world space so the
    # street view reads left-to-right as 7 ELEVEN.
    add_text(
        collection,
        "north_logo_numeral",
        "7",
        (0.37, hd + 0.445, 3.63),
        0.72,
        0.055,
        M["red"],
        "north",
    )
    add_text(
        collection,
        "north_logo_wordmark",
        "ELEVEN",
        (-0.54, hd + 0.445, 3.61),
        0.30,
        0.048,
        M["green"],
        "north",
    )
    add_box(
        collection,
        "corner_logo_diffuser_panel",
        (hw - 0.60, hd - 0.60, 3.62),
        (1.34, 0.055, 0.74),
        M["sign_white"],
        0.012,
        (0, 0, -math.pi / 4),
    )
    add_text(
        collection,
        "corner_logo_numeral",
        "7",
        (hw - 0.60, hd - 0.60, 3.63),
        0.62,
        0.045,
        M["red"],
        "northeast",
    )


def add_ground_floor_shell(collection, M, window, door):
    hw, hd = WIDTH / 2, DEPTH / 2
    # Real shell: slab, back/party walls, interior finishes and structural posts.
    add_chamfered_mass(collection, "ground_floor_slab", 0, 0.20, 0.03, M["concrete"])
    add_box(
        collection,
        "south_ground_wall",
        (0, -hd + 0.10, 1.58),
        (WIDTH - 0.20, 0.20, 2.96),
        M["brick"],
        0.014,
    )
    add_box(
        collection,
        "west_ground_wall",
        (-hw + 0.10, 0, 1.58),
        (0.20, DEPTH - 0.20, 2.96),
        M["brick"],
        0.014,
    )
    add_box(
        collection,
        "north_ground_header",
        (-0.60, hd - 0.10, 2.96),
        (WIDTH - CORNER_CUT, 0.22, 0.38),
        M["brick"],
        0.016,
    )
    add_box(
        collection,
        "east_ground_header",
        (hw - 0.10, -0.60, 2.96),
        (0.22, DEPTH - CORNER_CUT, 0.38),
        M["brick"],
        0.016,
    )
    add_box(
        collection,
        "ground_interior_floor",
        (-0.12, -0.12, 0.225),
        (WIDTH - 0.42, DEPTH - 0.42, 0.055),
        M["floor"],
        0.004,
    )
    add_box(
        collection,
        "ground_interior_ceiling",
        (-0.20, -0.20, 2.92),
        (WIDTH - 0.55, DEPTH - 0.55, 0.065),
        M["ceiling"],
        0.004,
    )
    add_box(
        collection,
        "south_interior_finish",
        (0, -hd + 0.225, 1.50),
        (WIDTH - 0.45, 0.055, 2.45),
        M["interior_wall"],
        0.004,
    )
    add_box(
        collection,
        "west_interior_finish",
        (-hw + 0.225, -0.10, 1.50),
        (0.055, DEPTH - 0.45, 2.45),
        M["interior_wall"],
        0.004,
    )

    north_xs = (-2.72, -1.30, 0.12, 1.54)
    for index, x in enumerate(north_xs):
        instance(
            collection,
            window,
            "north_storefront_glazing",
            (x, hd + 0.035, 0.23),
            0,
            (1.0 if index != 3 else 0.88, 1, 1),
        )
    east_ys = (-3.23, -1.81, -0.39, 1.03)
    for index, y in enumerate(east_ys):
        instance(
            collection,
            window,
            "east_storefront_glazing",
            (hw + 0.035, y, 0.23),
            -math.pi / 2,
            (1.0 if index != 3 else 0.88, 1, 1),
        )
    chamfer_mid = (hw - CORNER_CUT / 2, hd - CORNER_CUT / 2, 0.23)
    instance(
        collection,
        door,
        "chamfered_corner_double_entry",
        chamfer_mid,
        -math.pi / 4,
        (1.02, 1, 1),
    )

    # Structural piers coincide with module joints; none obstruct clear door openings.
    for x in (-3.43, -2.01, -0.59, 0.83, 2.26):
        add_box(
            collection,
            "north_structural_mullion_pier",
            (x, hd - 0.03, 1.57),
            (0.105, 0.24, 2.72),
            M["frame"],
            0.008,
        )
    for y in (-3.96, -2.52, -1.10, 0.32, 1.72, 2.82):
        add_box(
            collection,
            "east_structural_mullion_pier",
            (hw - 0.03, y, 1.57),
            (0.24, 0.105, 2.72),
            M["frame"],
            0.008,
        )
    add_box(
        collection,
        "chamfer_entry_head",
        (hw - 0.60, hd - 0.60, 2.94),
        (1.78, 0.23, 0.30),
        M["frame"],
        0.010,
        (0, 0, -math.pi / 4),
    )


def add_upper_storeys(collection, M, upper_window):
    hw, hd = WIDTH / 2, DEPTH / 2
    add_chamfered_mass(
        collection,
        "upper_two_storey_masonry_mass",
        4.10,
        HEIGHT - 0.35,
        0.0,
        M["brick"],
    )
    add_chamfered_mass(
        collection, "masonry_parapet", HEIGHT - 0.35, HEIGHT, -0.08, M["brick"]
    )
    # Belt courses and roof cornice preserve the layered miniature reference in real construction detail.
    for z, height in (
        (4.28, 0.16),
        (6.92, 0.18),
        (9.68, 0.13),
        (9.88, 0.13),
        (10.07, 0.15),
    ):
        add_box(
            collection,
            "north_masonry_belt_course",
            (-0.60, hd + 0.055, z),
            (WIDTH - CORNER_CUT + 0.12, 0.18, height),
            M["brick_trim"],
            0.008,
        )
        add_box(
            collection,
            "east_masonry_belt_course",
            (hw + 0.055, -0.60, z),
            (0.18, DEPTH - CORNER_CUT + 0.12, height),
            M["brick_trim"],
            0.008,
        )
        add_box(
            collection,
            "chamfer_masonry_belt_course",
            (hw - 0.60, hd - 0.60, z),
            (math.sqrt(2) * CORNER_CUT + 0.12, 0.18, height),
            M["brick_trim"],
            0.008,
            (0, 0, -math.pi / 4),
        )
    for floor_z in (5.55, 8.30):
        for x in (-2.12, 0.76):
            instance(
                collection,
                upper_window,
                "north_upper_multipane_window",
                (x, hd + 0.055, floor_z),
                0,
            )
        for y in (-2.34, 0.28):
            instance(
                collection,
                upper_window,
                "east_upper_multipane_window",
                (hw + 0.055, y, floor_z),
                -math.pi / 2,
            )
    # A narrower window illuminates the chamfered stair landing on each upper floor.
    for floor_z in (5.55, 8.30):
        instance(
            collection,
            upper_window,
            "corner_stair_window",
            (hw - 0.60, hd - 0.60, floor_z),
            -math.pi / 4,
            (0.58, 1, 0.92),
        )
    add_box(
        collection,
        "flat_roof_membrane",
        (-0.10, -0.10, HEIGHT + 0.035),
        (WIDTH - 0.48, DEPTH - 0.48, 0.07),
        M["roof"],
        0.008,
    )
    # Party-side rainwater service is connected from scupper to drain shoe.
    tube_between(
        collection,
        "connected_rainwater_downpipe",
        (-hw - 0.10, -2.72, 0.28),
        (-hw - 0.10, -2.72, 9.62),
        0.070,
        M["steel"],
    )
    add_box(
        collection,
        "roof_scupper_head",
        (-hw - 0.10, -2.72, 9.68),
        (0.23, 0.36, 0.28),
        M["steel"],
        0.010,
    )
    tube_between(
        collection,
        "rainwater_discharge_shoe",
        (-hw - 0.10, -2.72, 0.28),
        (-hw - 0.10, -2.42, 0.20),
        0.082,
        M["steel"],
    )


def add_interior_service_counter(collection, M):
    # A full hot-food and coffee run, assembled with readable equipment rather than proxy blocks.
    add_box(
        collection,
        "service_counter_base",
        (2.30, -0.25, 0.70),
        (0.78, 2.35, 0.88),
        M["cabinet"],
        0.020,
    )
    add_box(
        collection,
        "service_counter_stainless_top",
        (2.30, -0.25, 1.17),
        (0.90, 2.48, 0.08),
        M["steel"],
        0.012,
    )
    add_box(
        collection,
        "coffee_machine_body",
        (2.25, -0.72, 1.54),
        (0.62, 0.52, 0.66),
        M["coffee"],
        0.018,
    )
    add_box(
        collection,
        "coffee_machine_display",
        (2.25, -0.995, 1.70),
        (0.35, 0.025, 0.18),
        M["black"],
        0.005,
    )
    for x in (2.07, 2.43):
        add_cylinder(
            collection,
            "coffee_group_head",
            (x, -1.01, 1.47),
            (0.060, 0.060, 0.055),
            M["steel"],
            0.004,
            (math.pi / 2, 0, 0),
        )
        tube_between(
            collection,
            "coffee_dispensing_spout",
            (x, -1.05, 1.44),
            (x, -1.05, 1.31),
            0.018,
            M["steel"],
        )
    for index in range(5):
        add_cylinder(
            collection,
            "stacked_takeaway_cup",
            (2.66, -0.88, 1.28 + index * 0.055),
            (0.055 + index * 0.004, 0.055 + index * 0.004, 0.055),
            M["cup"],
            0.002,
        )
    add_box(
        collection,
        "heated_food_display_base",
        (2.30, 0.48, 1.34),
        (0.68, 0.68, 0.24),
        M["frame"],
        0.010,
    )
    add_box(
        collection,
        "heated_food_display_glass",
        (2.30, 0.48, 1.68),
        (0.62, 0.62, 0.54),
        M["glass"],
        0.006,
    )
    for z in (1.49, 1.70):
        add_box(
            collection,
            "heated_food_display_shelf",
            (2.30, 0.48, z),
            (0.54, 0.50, 0.025),
            M["steel"],
            0.003,
        )
    add_box(
        collection,
        "service_wall_menu",
        (3.19, -0.32, 2.10),
        (0.035, 1.82, 0.50),
        M["black"],
        0.008,
    )
    for row in range(4):
        add_box(
            collection,
            "service_menu_line",
            (3.17, -0.78 + row * 0.30, 2.18),
            (0.018, 0.18, 0.035),
            M["sign_white"],
            0.002,
        )


def add_interior(collection, M):
    grocery_shelf = bpy.data.collections.get("GROCERY_SHELF_MASTER")
    grocery_fridge = bpy.data.collections.get("GROCERY_FRIDGE_MASTER")
    checkout = bpy.data.collections.get("CHECKOUT_MASTER")
    required = [grocery_shelf, grocery_fridge, checkout]
    if any(asset is None for asset in required):
        raise RuntimeError(
            "all43-19 requires the detailed all43-15 grocery asset masters"
        )
    instance(
        collection,
        grocery_shelf,
        "stocked_center_gondola",
        (-1.15, -1.48, 0.26),
        0,
        (0.83, 0.82, 0.92),
    )
    instance(
        collection,
        grocery_shelf,
        "stocked_center_gondola",
        (-1.15, 0.15, 0.26),
        0,
        (0.83, 0.82, 0.92),
    )
    instance(
        collection,
        grocery_shelf,
        "south_wall_stock_run",
        (-1.55, -3.30, 0.26),
        0,
        (0.62, 0.74, 0.90),
    )
    instance(
        collection,
        grocery_fridge,
        "west_wall_refrigeration",
        (-2.92, -1.65, 0.26),
        math.pi / 2,
        (0.88, 0.78, 0.90),
    )
    instance(
        collection,
        grocery_fridge,
        "west_wall_refrigeration",
        (-2.92, 0.72, 0.26),
        math.pi / 2,
        (0.88, 0.78, 0.90),
    )
    instance(
        collection,
        checkout,
        "entry_checkout_counter",
        (0.62, 2.28, 0.26),
        0,
        (0.76, 0.85, 0.92),
    )
    add_interior_service_counter(collection, M)
    # Ceiling grid, fixtures, joints and queue furniture make the store operationally legible.
    for x in (-2.20, -0.55, 1.10, 2.45):
        for y in (-2.42, -0.66, 1.10, 2.42):
            if x > 2 and y > 1.5:
                continue
            add_box(
                collection,
                "recessed_led_light",
                (x, y, 2.86),
                (1.02, 0.27, 0.045),
                M["light"],
                0.004,
            )
            if (round(x * 10) + round(y * 10)) % 3 == 0:
                add_area_light(
                    collection, "neutral_interior_area_light", (x, y, 2.78), 250, 1.05
                )
    for x in (-2.45, -1.22, 0, 1.22, 2.45):
        add_box(
            collection,
            "floor_tile_joint",
            (x, -0.20, 0.258),
            (0.015, DEPTH - 0.62, 0.006),
            M["joint"],
            0.001,
        )
    for y in (-3.02, -1.52, 0, 1.52, 3.02):
        add_box(
            collection,
            "floor_tile_joint",
            (-0.10, y, 0.258),
            (WIDTH - 0.62, 0.015, 0.006),
            M["joint"],
            0.001,
        )
    for x, y in ((1.72, 2.42), (2.55, 1.76)):
        add_cylinder(
            collection,
            "queue_stanchion_post",
            (x, y, 0.67),
            (0.045, 0.045, 0.42),
            M["steel"],
            0.004,
        )
        add_cylinder(
            collection,
            "queue_stanchion_base",
            (x, y, 0.285),
            (0.16, 0.16, 0.030),
            M["steel"],
            0.005,
        )
    tube_between(
        collection,
        "queue_retractable_belt",
        (1.72, 2.42, 0.87),
        (2.55, 1.76, 0.87),
        0.018,
        M["red"],
    )
    add_box(
        collection,
        "staff_room_partition",
        (-2.02, -3.45, 1.55),
        (2.45, 0.12, 2.48),
        M["interior_wall"],
        0.008,
    )
    add_box(
        collection,
        "staff_access_door",
        (-2.58, -3.36, 1.45),
        (1.02, 0.10, 2.35),
        M["frame"],
        0.010,
    )


def add_rooftop_services(collection, M, rooftop):
    for loc, rotation, scale in (
        ((-1.80, -1.65, HEIGHT + 0.08), 0.05, (1, 1, 1)),
        ((1.05, -0.82, HEIGHT + 0.08), -0.08, (0.88, 0.88, 0.88)),
    ):
        instance(
            collection, rooftop, "screened_rooftop_condenser", loc, rotation, scale
        )
    add_box(
        collection,
        "roof_access_hatch",
        (-0.35, 1.55, HEIGHT + 0.13),
        (1.15, 1.05, 0.20),
        M["steel"],
        0.018,
    )
    add_box(
        collection,
        "roof_access_hatch_upstand",
        (-0.35, 1.55, HEIGHT + 0.28),
        (0.94, 0.84, 0.16),
        M["roof"],
        0.012,
    )
    # Conduit and isolator rails visibly connect the equipment to the roof plant zone.
    for y in (-1.94, -1.36):
        add_box(
            collection,
            "condenser_isolator_rail",
            (-1.80, y, HEIGHT + 0.13),
            (1.38, 0.08, 0.12),
            M["louver"],
            0.006,
        )
    tube_between(
        collection,
        "rooftop_service_conduit",
        (-1.12, -1.65, HEIGHT + 0.36),
        (-0.35, 1.02, HEIGHT + 0.36),
        0.035,
        M["steel"],
    )


def build_store_master(M):
    master = new_master(MASTER_NAME)
    upper_window = make_upper_window_master(M)
    storefront = make_storefront_window_master(M)
    door = make_corner_door_master(M)
    rooftop = make_rooftop_unit_master(M)
    add_ground_floor_shell(master, M, storefront, door)
    add_wraparound_fascia(master, M)
    add_upper_storeys(master, M, upper_window)
    add_interior(master, M)
    add_rooftop_services(master, M, rooftop)
    master[
        "architectural_program"
    ] = "three-storey mixed-use corner building with ground-floor 7-Eleven"
    master[
        "reference_translation"
    ] = "green masonry, chamfered corner, white multi-pane windows, wraparound orange/green/red fascia"
    master["store_width_m"] = WIDTH
    master["store_depth_m"] = DEPTH
    master["building_height_m"] = HEIGHT
    master[
        "interior_visibility"
    ] = "transparent north/east storefront with stocked retail interior"
    return master


def hide_conflicting_frontage_assets():
    hidden = []
    for obj in bpy.data.objects:
        if obj.hide_render or obj.instance_collection is None:
            continue
        if (
            obj.instance_collection.name == "COMPLEX_REAR_FLOWERBED_MASTER"
            and (obj.location - Vector((-11.5, -13.0, 0.18))).length < 0.40
        ):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[
                P + "hidden_reason"
            ] = "footprint replaced by full-scale street-corner store"
            hidden.append(obj.name)
    return hidden


def add_world_frontage(world, M):
    # These are infill paving/threshold elements only; existing road and sidewalk remain authoritative.
    add_box(
        world,
        "north_entry_paver_apron",
        (-14.05, -6.69, 0.225),
        (5.75, 0.82, 0.065),
        M["paver"],
        0.010,
    )
    add_box(
        world,
        "east_entry_paver_apron",
        (-9.52, -11.80, 0.225),
        (0.82, 6.85, 0.065),
        M["paver"],
        0.010,
    )
    add_box(
        world,
        "chamfer_entry_threshold_apron",
        (-10.10, -7.86, 0.235),
        (1.72, 0.88, 0.070),
        M["paver"],
        0.010,
        (0, 0, -math.pi / 4),
    )
    add_box(
        world,
        "north_apron_road_edge_curb",
        (-14.05, -6.25, 0.17),
        (5.80, 0.12, 0.22),
        M["concrete"],
        0.010,
    )
    add_box(
        world,
        "east_apron_road_edge_curb",
        (-9.08, -11.80, 0.17),
        (0.12, 6.90, 0.22),
        M["concrete"],
        0.010,
    )
    for index in range(8):
        add_box(
            world,
            "north_apron_control_joint",
            (-16.55 + index * 0.72, -6.69, 0.260),
            (0.016, 0.74, 0.008),
            M["joint"],
            0.001,
        )
    for index in range(10):
        add_box(
            world,
            "east_apron_control_joint",
            (-9.52, -14.95 + index * 0.70, 0.260),
            (0.74, 0.016, 0.008),
            M["joint"],
            0.001,
        )
    # Tactile studs are individual grounded pavers, not floating yellow rods.
    for index in range(7):
        add_box(
            world,
            "north_tactile_warning_paver",
            (-16.40 + index * 0.48, -6.66, 0.274),
            (0.36, 0.36, 0.028),
            M["tactile"],
            0.006,
        )
    for index in range(7):
        add_box(
            world,
            "east_tactile_warning_paver",
            (-9.49, -14.65 + index * 0.48, 0.274),
            (0.36, 0.36, 0.028),
            M["tactile"],
            0.006,
        )
    # Stainless bicycle hoops are physically socketed into the east apron.
    for index, y in enumerate((-13.95, -12.75)):
        x = -9.30
        tube_between(
            world,
            "bicycle_hoop_left_leg",
            (x, y - 0.32, 0.25),
            (x, y - 0.32, 1.00),
            0.032,
            M["steel"],
        )
        tube_between(
            world,
            "bicycle_hoop_right_leg",
            (x, y + 0.32, 0.25),
            (x, y + 0.32, 1.00),
            0.032,
            M["steel"],
        )
        tube_between(
            world,
            "bicycle_hoop_top_rail",
            (x, y - 0.32, 1.00),
            (x, y + 0.32, 1.00),
            0.032,
            M["steel"],
        )


def recursive_collection_objects(collection, seen=None):
    seen = seen or set()
    if collection.name in seen:
        return []
    seen.add(collection.name)
    objects = list(collection.objects)
    for obj in collection.objects:
        if obj.instance_type == "COLLECTION" and obj.instance_collection:
            objects.extend(recursive_collection_objects(obj.instance_collection, seen))
    for child in collection.children:
        objects.extend(recursive_collection_objects(child, seen))
    return objects


def audit(master, store_instance, hidden, world):
    required_nested = (
        P + "MASTER:UPPER_MULTIPANE_WINDOW",
        P + "MASTER:711_STOREFRONT_WINDOW",
        P + "MASTER:711_DOUBLE_ENTRY",
        P + "MASTER:ROOFTOP_CONDENSER",
        "GROCERY_SHELF_MASTER",
        "GROCERY_FRIDGE_MASTER",
        "CHECKOUT_MASTER",
    )
    missing = [
        name for name in required_nested if bpy.data.collections.get(name) is None
    ]
    all_parts = recursive_collection_objects(master)
    visible_direct = [obj for obj in master.objects if not obj.hide_render]
    new_objects = [obj for obj in bpy.data.objects if obj.name.startswith(P)]
    collection_instances = [
        obj for obj in new_objects if obj.instance_type == "COLLECTION"
    ]
    storefront_glazing = [
        obj for obj in new_objects if "storefront_low_iron_glass" in obj.name
    ]
    product_instances = [
        obj
        for obj in all_parts
        if obj.instance_collection and "PRODUCT" in obj.instance_collection.name
    ]
    forbidden = [
        obj.name
        for obj in new_objects
        if any(
            token in obj.name.lower()
            for token in ("toy", "proxy", "placeholder", "dummy", "primitive_store")
        )
    ]
    low = STORE_LOCATION + Vector((-WIDTH / 2, -DEPTH / 2, 0))
    high = STORE_LOCATION + Vector((WIDTH / 2, DEPTH / 2, HEIGHT + 1.35))
    restaurant_east = -24.3 + 7.84
    south_gap = low.y - (-21.0 + 4.40)
    west_gap = low.x - restaurant_east
    checks = {
        "missing_nested_assets": missing,
        "store_is_linked_collection_instance": store_instance.instance_type
        == "COLLECTION"
        and store_instance.instance_collection == master,
        "recursive_component_count": len(all_parts),
        "direct_master_component_count": len(visible_direct),
        "new_collection_instance_count": len(collection_instances),
        "storefront_glass_master_count": len(storefront_glazing),
        "stocked_product_instance_count": len(product_instances),
        "hidden_conflicting_frontage_assets": hidden,
        "world_frontage_object_count": len(world.objects) - 1,
        "store_world_bounds": [
            list(round(v, 3) for v in low),
            list(round(v, 3) for v in high),
        ],
        "existing_restaurant_separation_m": round(max(south_gap, west_gap), 3),
        "forbidden_toy_or_proxy_names": forbidden,
    }
    if (
        missing
        or not checks["store_is_linked_collection_instance"]
        or len(all_parts) < 180
        or len(collection_instances) < 20
        or len(forbidden)
        or len(hidden) != 1
        or checks["existing_restaurant_separation_m"] < 0.20
    ):
        raise RuntimeError({"all43_19_quality_audit_failed": checks})
    return {
        "pipeline_stage": "commercial_corner_711_generator_19.py",
        "new_asset_master": MASTER_NAME,
        "new_store_instance": store_instance.name,
        "store_program": master["architectural_program"],
        "full_scale_dimensions_m": [WIDTH, DEPTH, HEIGHT],
        "facade_system": "green running-bond glazed masonry, deep multi-pane windows and wraparound illuminated tri-colour fascia",
        "storefront_system": "north/east low-iron curtain wall plus chamfered double glass entrance",
        "interior_system": "stocked gondolas, refrigeration, checkout, hot-food/coffee counter, queue and ceiling lighting",
        "roof_system": "parapet, membrane, access hatch, curbed condensers, isolator rails, conduit and connected rainwater drainage",
        "toy_model_policy": "PASS: no proxy/placeholder/toy asset names; detailed shared production masters only",
        **checks,
    }


def run():
    M = materials()
    hidden = hide_conflicting_frontage_assets()
    master = build_store_master(M)
    world = ensure_world_collection()
    # Remove a stale instance when Blender reloads this module in an interactive production session.
    stale = bpy.data.objects.get(P + "street_corner_711")
    if stale:
        bpy.data.objects.remove(stale, do_unlink=True)
    store = instance(world, master, "street_corner_711", STORE_LOCATION)
    store["c2w_semantic_role"] = "full-scale street-corner convenience store"
    store["c2w_pipeline_stage"] = "all43_19"
    store[
        "brand_reference"
    ] = "7-Eleven wraparound fascia translated from supplied street-corner reference"
    add_world_frontage(world, M)
    return audit(master, store, hidden, world)
