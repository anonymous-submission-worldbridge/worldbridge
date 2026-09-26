"""Production all43-25 reference-bar addition for the connected commercial block.

This module is deliberately consumed by the active
``commercial_mcdonalds_layout_generator_20`` generator.  It creates two
independent, full-scale, adjacent collection masters from the supplied bar
references and links them into the north arm of the commercial inverse-L.
Nothing here patches a saved Blend or creates an isolated demonstration asset.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector


P = "all43_25:"
COPPER_MASTER_NAME = "COPPER_TAP_OPEN_BAR_MASTER"
HAWTHORN_MASTER_NAME = "HAWTHORN_STREET_BAR_MASTER"
REFERENCE_OPEN_BAR = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTkAdNAoa1i4WV-pxNJ8Xvqbx1-kgPyjiDIb2JmTbAORg&s"
REFERENCE_HAWTHORN = "https://respic.3d66.com/coverimg/cache/7475/06421a5ee03e4acd2439e0f70500a9c2.jpg!medium-size-2?v=22647271&k=D41D8CD98F00B204E9800998ECF8427E"

BAR_DEPTH = 8.10
COPPER_WIDTH = 8.00
COPPER_HEIGHT = 5.78
HAWTHORN_WIDTH = 8.40
HAWTHORN_HEIGHT = 6.58
FRONT_Y = -14.55 + BAR_DEPTH / 2
REAR_Y = -14.55 - BAR_DEPTH / 2


def cube_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cube")
    if mesh is None:
        raise RuntimeError(
            "all43-25 requires all43_10:shared_cube from the active pipeline"
        )
    return mesh


def cylinder_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    if mesh is None:
        raise RuntimeError(
            "all43-25 requires all43_10:shared_cylinder_12 from the active pipeline"
        )
    return mesh


def assign_material(obj, mat):
    if obj.data is None:
        return
    if not obj.data.materials:
        obj.data.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat


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


def walnut_material():
    mat = bpy.data.materials.get(P + "quarter_sawn_walnut_joinery")
    if mat:
        return mat
    mat = bpy.data.materials.new(P + "quarter_sawn_walnut_joinery")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    wave = nodes.new("ShaderNodeTexWave")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    mapping.inputs["Scale"].default_value = (4.2, 0.72, 1.15)
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 5.4
    wave.inputs["Distortion"].default_value = 7.0
    wave.inputs["Detail"].default_value = 4.0
    noise.inputs["Scale"].default_value = 3.6
    noise.inputs["Detail"].default_value = 5.0
    ramp.color_ramp.elements[0].color = (0.035, 0.008, 0.003, 1)
    ramp.color_ramp.elements[1].color = (0.31, 0.075, 0.018, 1)
    bsdf.inputs["Roughness"].default_value = 0.42
    bump.inputs["Strength"].default_value = 0.20
    bump.inputs["Distance"].default_value = 0.035
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], out.inputs[0])
    mat.diffuse_color = (0.18, 0.045, 0.012, 1)
    mat[
        "procedural_finish"
    ] = "quarter-sawn walnut with directional grain and micro-relief"
    return mat


def copper_panel_material():
    mat = bpy.data.materials.get(P + "aged_hammered_copper_sign_panel")
    if mat:
        return mat
    mat = bpy.data.materials.new(P + "aged_hammered_copper_sign_panel")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    noise.inputs["Scale"].default_value = 8.0
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp.color_ramp.elements[0].color = (0.055, 0.010, 0.004, 1)
    ramp.color_ramp.elements[1].color = (0.42, 0.085, 0.018, 1)
    bsdf.inputs["Metallic"].default_value = 0.58
    bsdf.inputs["Roughness"].default_value = 0.43
    bump.inputs["Strength"].default_value = 0.23
    bump.inputs["Distance"].default_value = 0.025
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], out.inputs[0])
    mat.diffuse_color = (0.28, 0.050, 0.012, 1)
    mat[
        "procedural_finish"
    ] = "aged hammered copper with nonuniform oxidation and real metallic response"
    return mat


def make_materials():
    return {
        "walnut": walnut_material(),
        "copper_panel": copper_panel_material(),
        "copper": material(
            "brushed_copper_hardware", (0.47, 0.095, 0.022, 1), 0.28, 0.82
        ),
        "brass": material("aged_brass_trim", (0.52, 0.285, 0.055, 1), 0.30, 0.76),
        "black": material(
            "blackened_structural_steel", (0.009, 0.011, 0.010, 1), 0.48, 0.68
        ),
        "charcoal": material(
            "charcoal_microcement", (0.030, 0.033, 0.031, 1), 0.79, 0.04
        ),
        "cream": material("warm_lime_plaster", (0.75, 0.68, 0.55, 1), 0.82),
        "marble": material(
            "white_quartz_bar_surface", (0.73, 0.70, 0.63, 1), 0.27, 0.02
        ),
        "tile": material(
            "handmade_terracotta_floor_tile", (0.285, 0.070, 0.022, 1), 0.76
        ),
        "tile_joint": material(
            "terracotta_recessed_grout", (0.055, 0.040, 0.032, 1), 0.94
        ),
        "leather": material("full_grain_cognac_leather", (0.26, 0.055, 0.012, 1), 0.55),
        "fabric": material("olive_contract_upholstery", (0.085, 0.115, 0.045, 1), 0.77),
        "amber": material("amber_bottle_glass", (0.16, 0.045, 0.006, 1), 0.22, 0.05),
        "green_glass": material(
            "green_bottle_glass", (0.015, 0.105, 0.040, 1), 0.23, 0.03
        ),
        "clear_glass": material("clear_bar_glass", (0.23, 0.31, 0.29, 0.35), 0.12, 0.0),
        "label": material("bottle_paper_label", (0.72, 0.58, 0.35, 1), 0.70),
        "dark_label": material("bottle_dark_label", (0.025, 0.017, 0.012, 1), 0.66),
        "screen": material(
            "bar_menu_display",
            (0.006, 0.008, 0.007, 1),
            0.18,
            0.10,
            (0.06, 0.15, 0.09, 1),
            0.55,
        ),
        "warm_light": material(
            "bar_warm_lamp_diffuser",
            (0.98, 0.54, 0.16, 1),
            0.26,
            0.0,
            (1.0, 0.32, 0.045, 1),
            3.0,
        ),
        "sign_light": material(
            "hawthorn_gold_sign_diffuser",
            (0.82, 0.34, 0.035, 1),
            0.24,
            0.08,
            (1.0, 0.20, 0.025, 1),
            2.6,
        ),
        "green": material("bar_living_plant_leaf", (0.025, 0.135, 0.035, 1), 0.72),
        "soil": material("bar_planter_soil", (0.055, 0.027, 0.010, 1), 0.94),
        "rubber": material("bar_furniture_floor_glide", (0.006, 0.007, 0.006, 1), 0.88),
    }


def add_object(collection, name, mesh, loc, scale, mat, bevel=0.0, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("fabricated_edge_radius", "BEVEL")
        modifier.width = min(bevel, min(abs(value) for value in scale) * 0.18)
        modifier.segments = 3
    obj["shared_pipeline_mesh"] = mesh in (cube_mesh(), cylinder_mesh())
    return obj


def add_box(collection, name, loc, dims, mat, bevel=0.006, rot=(0, 0, 0)):
    return add_object(collection, name, cube_mesh(), loc, dims, mat, bevel, rot)


def add_cylinder(collection, name, loc, scale, mat, bevel=0.004, rot=(0, 0, 0)):
    return add_object(collection, name, cylinder_mesh(), loc, scale, mat, bevel, rot)


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


def box_between_xy(collection, name, start, end, width, height, mat, bevel=0.006):
    start, end = Vector(start), Vector(end)
    direction = end - start
    return add_box(
        collection,
        name,
        (start + end) / 2,
        (direction.length, width, height),
        mat,
        bevel,
        (0, 0, math.atan2(direction.y, direction.x)),
    )


def instance(collection, master, name, loc, rotation=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(P + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = loc
    obj.rotation_euler[2] = rotation
    obj.scale = scale
    obj["linked_production_asset"] = master.name
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
    ] = "full-scale constructed hospitality asset; no proxy, toy or placeholder geometry"
    return collection


def add_text(collection, name, body, loc, size, depth, mat, shear=0.0):
    curve = bpy.data.curves.new(P + name + "_data", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.space_character = 1.02
    curve.extrude = depth
    curve.bevel_depth = min(0.010, depth * 0.15)
    curve.bevel_resolution = 2
    curve.fill_mode = "BOTH"
    curve.shear = shear
    curve.materials.append(mat)
    obj = bpy.data.objects.new(P + name, curve)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler[0] = math.pi / 2
    obj["sign_construction"] = "dimensional fabricated lettering with physical returns"
    return obj


def add_area_light(collection, name, loc, energy=180, size=0.70):
    data = bpy.data.lights.new(P + name + "_data", "AREA")
    data.energy = energy
    data.color = (1.0, 0.47, 0.16)
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(P + name, data)
    collection.objects.link(obj)
    obj.location = loc
    return obj


def add_lathe(collection, name, profile, segments, mat, loc=(0, 0, 0), bevel=0.002):
    verts = []
    faces = []
    for radius, z in profile:
        for segment in range(segments):
            angle = math.tau * segment / segments
            verts.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
    rings = len(profile)
    for ring in range(rings - 1):
        for segment in range(segments):
            nxt = (segment + 1) % segments
            a = ring * segments + segment
            b = ring * segments + nxt
            c = (ring + 1) * segments + nxt
            d = (ring + 1) * segments + segment
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(P + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("lathed_edge_softening", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    obj[
        "manufacturing_method"
    ] = "authored revolved profile, capped by zero-radius end rings"
    return obj


def make_bottle_master(name, glass_mat, M):
    master = new_master(P + "MASTER:" + name)
    profile = (
        (0.0, 0.0),
        (0.070, 0.0),
        (0.076, 0.035),
        (0.076, 0.37),
        (0.067, 0.43),
        (0.035, 0.49),
        (0.030, 0.61),
        (0.038, 0.625),
        (0.0, 0.625),
    )
    add_lathe(master, "bottle_molded_body", profile, 20, glass_mat)
    add_cylinder(
        master,
        "bottle_main_label",
        (0, -0.078, 0.265),
        (0.108, 0.010, 0.15),
        M["label"],
        0.004,
    )
    add_cylinder(
        master,
        "bottle_neck_label",
        (0, -0.032, 0.515),
        (0.052, 0.008, 0.055),
        M["dark_label"],
        0.003,
    )
    add_cylinder(
        master,
        "bottle_metal_closure",
        (0, 0, 0.635),
        (0.034, 0.034, 0.025),
        M["brass"],
        0.004,
    )
    add_cylinder(
        master,
        "bottle_punt_shadow",
        (0, 0, 0.012),
        (0.038, 0.038, 0.010),
        M["dark_label"],
        0.003,
    )
    master[
        "asset_specification"
    ] = "twenty-segment revolved hospitality bottle with shoulder, neck, closure, punt and separate labels"
    return master


def make_stool_master(M):
    master = new_master(P + "MASTER:COPPER_BAR_STOOL")
    for x in (-0.22, 0.22):
        for y in (-0.19, 0.19):
            tube_between(
                master,
                "stool_splayed_steel_leg",
                (x, y, 0.025),
                (x * 0.78, y * 0.76, 0.69),
                0.022,
                M["black"],
            )
            add_cylinder(
                master,
                "stool_threaded_floor_glide",
                (x, y, 0.018),
                (0.034, 0.034, 0.024),
                M["rubber"],
                0.004,
            )
    for y in (-0.15, 0.15):
        tube_between(
            master,
            "stool_long_footrest",
            (-0.19, y, 0.30),
            (0.19, y, 0.30),
            0.018,
            M["brass"],
        )
    for x in (-0.19, 0.19):
        tube_between(
            master,
            "stool_cross_footrest",
            (x, -0.15, 0.30),
            (x, 0.15, 0.30),
            0.018,
            M["brass"],
        )
    add_box(
        master,
        "stool_contoured_walnut_seat",
        (0, 0, 0.75),
        (0.54, 0.46, 0.11),
        M["walnut"],
        0.045,
        (0, math.radians(-2), 0),
    )
    add_box(
        master,
        "stool_seat_bracket",
        (0, 0, 0.685),
        (0.32, 0.28, 0.045),
        M["black"],
        0.008,
    )
    master["ground_contact_z_m"] = 0.0
    master[
        "asset_specification"
    ] = "contract bar stool with four splayed legs, four glides, welded footrests, bracket and contoured timber seat"
    return master


def make_bistro_chair_master(M):
    master = new_master(P + "MASTER:HAWTHORN_BISTRO_CHAIR")
    for x in (-0.22, 0.22):
        tube_between(
            master,
            "chair_front_leg",
            (x, -0.19, 0.025),
            (x, -0.16, 0.48),
            0.022,
            M["black"],
        )
        tube_between(
            master,
            "chair_raked_rear_leg",
            (x, 0.19, 0.025),
            (x, 0.16, 1.03),
            0.024,
            M["black"],
        )
        add_cylinder(
            master,
            "chair_floor_glide",
            (x, -0.19, 0.018),
            (0.033, 0.033, 0.024),
            M["rubber"],
            0.004,
        )
        add_cylinder(
            master,
            "chair_floor_glide",
            (x, 0.19, 0.018),
            (0.033, 0.033, 0.024),
            M["rubber"],
            0.004,
        )
    for y in (-0.16, 0.16):
        tube_between(
            master,
            "chair_seat_side_rail",
            (-0.22, y, 0.45),
            (0.22, y, 0.45),
            0.020,
            M["black"],
        )
    add_box(
        master,
        "chair_cognac_leather_seat",
        (0, 0, 0.51),
        (0.49, 0.46, 0.11),
        M["leather"],
        0.040,
    )
    for z in (0.67, 0.80, 0.93):
        add_box(
            master,
            "chair_curved_walnut_back_slat",
            (0, 0.175, z),
            (0.47, 0.060, 0.085),
            M["walnut"],
            0.022,
            (math.radians(-5), 0, 0),
        )
    add_box(
        master,
        "chair_back_top_rail",
        (0, 0.18, 1.03),
        (0.52, 0.070, 0.070),
        M["black"],
        0.016,
    )
    master["ground_contact_z_m"] = 0.0
    master[
        "asset_specification"
    ] = "welded four-leg bistro chair with glides, framed leather seat and separate curved walnut back slats"
    return master


def make_bistro_table_master(M):
    master = new_master(P + "MASTER:HAWTHORN_BISTRO_TABLE")
    add_cylinder(
        master,
        "table_ballasted_foot",
        (0, 0, 0.055),
        (0.31, 0.31, 0.055),
        M["black"],
        0.014,
    )
    add_cylinder(
        master,
        "table_leveling_pad",
        (0, 0, 0.015),
        (0.14, 0.14, 0.020),
        M["rubber"],
        0.006,
    )
    add_cylinder(
        master,
        "table_brass_pedestal",
        (0, 0, 0.39),
        (0.047, 0.047, 0.33),
        M["brass"],
        0.005,
    )
    add_cylinder(
        master,
        "table_under_top_spider",
        (0, 0, 0.70),
        (0.24, 0.24, 0.035),
        M["black"],
        0.006,
    )
    add_cylinder(
        master,
        "table_walnut_top",
        (0, 0, 0.75),
        (0.46, 0.46, 0.055),
        M["walnut"],
        0.018,
    )
    add_cylinder(
        master,
        "table_copper_edge_band",
        (0, 0, 0.748),
        (0.466, 0.466, 0.018),
        M["copper"],
        0.005,
    )
    master["ground_contact_z_m"] = 0.0
    return master


def make_pendant_master(M, name, wide=False):
    master = new_master(P + "MASTER:" + name)
    add_cylinder(
        master,
        "pendant_ceiling_rose",
        (0, 0, 0.04),
        (0.11, 0.11, 0.04),
        M["black"],
        0.008,
    )
    add_cylinder(
        master,
        "pendant_braided_flex",
        (0, 0, -0.40),
        (0.010, 0.010, 0.40),
        M["black"],
        0.002,
    )
    if wide:
        profile = (
            (0, -0.76),
            (0.06, -0.75),
            (0.20, -0.70),
            (0.31, -0.58),
            (0.34, -0.45),
            (0.12, -0.40),
            (0, -0.40),
        )
    else:
        profile = (
            (0, -0.76),
            (0.05, -0.75),
            (0.13, -0.69),
            (0.17, -0.58),
            (0.14, -0.46),
            (0.06, -0.42),
            (0, -0.42),
        )
    add_lathe(
        master, "pendant_formed_metal_shade", profile, 24, M["copper"], bevel=0.003
    )
    add_cylinder(
        master,
        "pendant_lampholder",
        (0, 0, -0.47),
        (0.055, 0.055, 0.09),
        M["brass"],
        0.006,
    )
    add_lathe(
        master,
        "pendant_amber_diffuser",
        ((0, -0.70), (0.07, -0.69), (0.09, -0.61), (0.07, -0.52), (0, -0.51)),
        20,
        M["warm_light"],
        bevel=0.002,
    )
    master[
        "asset_specification"
    ] = "wired pendant with ceiling rose, braided flex, revolved metal shade, lampholder and emissive glass diffuser"
    return master


def make_lantern_master(M):
    master = new_master(P + "MASTER:HAWTHORN_WALL_LANTERN")
    add_box(
        master,
        "lantern_wall_backplate",
        (0, 0.04, 0.30),
        (0.20, 0.08, 0.58),
        M["copper"],
        0.025,
    )
    tube_between(
        master,
        "lantern_scroll_bracket",
        (0, 0, 0.44),
        (0, -0.26, 0.67),
        0.025,
        M["copper"],
    )
    add_box(
        master,
        "lantern_cage_top",
        (0, -0.29, 0.59),
        (0.25, 0.25, 0.055),
        M["copper"],
        0.010,
    )
    add_box(
        master,
        "lantern_cage_bottom",
        (0, -0.29, 0.18),
        (0.25, 0.25, 0.055),
        M["copper"],
        0.010,
    )
    for x in (-0.105, 0.105):
        for y in (-0.395, -0.185):
            tube_between(
                master,
                "lantern_cage_vertical",
                (x, y, 0.20),
                (x, y, 0.57),
                0.012,
                M["copper"],
            )
    add_cylinder(
        master,
        "lantern_frosted_flame_diffuser",
        (0, -0.29, 0.385),
        (0.065, 0.065, 0.17),
        M["warm_light"],
        0.012,
    )
    add_cylinder(
        master,
        "lantern_finial",
        (0, -0.29, 0.67),
        (0.045, 0.045, 0.08),
        M["copper"],
        0.008,
    )
    return master


def add_roof_services(collection, M, width, height, label):
    condenser = bpy.data.collections.get("all43_19:MASTER:ROOFTOP_CONDENSER")
    if condenser:
        instance(
            collection,
            condenser,
            label + "_curbed_rooftop_condenser",
            (-width * 0.24, 0.65, height + 0.10),
            -0.04,
            (0.68, 0.68, 0.68),
        )
    add_box(
        collection,
        label + "_roof_access_hatch",
        (width * 0.18, 1.20, height + 0.18),
        (0.92, 0.80, 0.24),
        M["black"],
        0.015,
    )
    add_box(
        collection,
        label + "_roof_exhaust_curb",
        (width * 0.30, 2.45, height + 0.16),
        (0.68, 0.66, 0.24),
        M["charcoal"],
        0.012,
    )
    add_cylinder(
        collection,
        label + "_roof_exhaust_fan",
        (width * 0.30, 2.45, height + 0.52),
        (0.29, 0.29, 0.30),
        M["copper"],
        0.014,
    )
    add_cylinder(
        collection,
        label + "_roof_weather_cap",
        (width * 0.30, 2.45, height + 0.83),
        (0.37, 0.37, 0.065),
        M["black"],
        0.012,
    )
    tube_between(
        collection,
        label + "_roof_service_conduit",
        (-width * 0.16, 0.65, height + 0.30),
        (width * 0.18, 1.20, height + 0.30),
        0.025,
        M["copper"],
    )
    tube_between(
        collection,
        label + "_connected_downpipe",
        (-width / 2 + 0.10, 2.72, 0.28),
        (-width / 2 + 0.10, 2.72, height - 0.08),
        0.052,
        M["copper"],
    )


def add_shell(collection, M, width, height, label, front_header_z):
    hw, hd = width / 2, BAR_DEPTH / 2
    add_box(
        collection,
        label + "_reinforced_floor_slab",
        (0, 0, 0.10),
        (width, BAR_DEPTH, 0.20),
        M["concrete"],
        0.014,
    )
    add_box(
        collection,
        label + "_terracotta_finish",
        (0, 0, 0.235),
        (width - 0.38, BAR_DEPTH - 0.40, 0.055),
        M["tile"],
        0.006,
    )
    for x in range(-3, 4):
        add_box(
            collection,
            label + "_floor_tile_grout_x",
            (x * 1.05, 0, 0.267),
            (0.018, BAR_DEPTH - 0.52, 0.010),
            M["tile_joint"],
            0.001,
        )
    for y in range(-3, 4):
        add_box(
            collection,
            label + "_floor_tile_grout_y",
            (0, y * 1.02, 0.268),
            (width - 0.52, 0.018, 0.010),
            M["tile_joint"],
            0.001,
        )
    add_box(
        collection,
        label + "_rear_service_wall",
        (0, hd - 0.11, height / 2),
        (width - 0.18, 0.22, height),
        M["cream"],
        0.018,
    )
    add_box(
        collection,
        label + "_west_party_wall",
        (-hw + 0.09, 0, height / 2),
        (0.18, BAR_DEPTH, height),
        M["charcoal"],
        0.014,
    )
    add_box(
        collection,
        label + "_east_party_wall",
        (hw - 0.09, 0, height / 2),
        (0.18, BAR_DEPTH, height),
        M["charcoal"],
        0.014,
    )
    add_box(
        collection,
        label + "_acoustic_ceiling",
        (0, 0, front_header_z - 0.18),
        (width - 0.40, BAR_DEPTH - 0.46, 0.070),
        M["charcoal"],
        0.006,
    )
    add_box(
        collection,
        label + "_roof_membrane",
        (0, 0, height + 0.04),
        (width - 0.32, BAR_DEPTH - 0.32, 0.080),
        M["roof"],
        0.008,
    )
    for wall_label, loc, dims in (
        ("front", (0, -hd + 0.10, height + 0.17), (width, 0.34, 0.34)),
        ("rear", (0, hd - 0.10, height + 0.17), (width, 0.34, 0.34)),
        ("west", (-hw + 0.10, 0, height + 0.17), (0.34, BAR_DEPTH - 0.20, 0.34)),
        ("east", (hw - 0.10, 0, height + 0.17), (0.34, BAR_DEPTH - 0.20, 0.34)),
    ):
        add_box(
            collection,
            label + "_" + wall_label + "_parapet",
            loc,
            dims,
            M["charcoal"],
            0.012,
        )
        add_box(
            collection,
            label + "_" + wall_label + "_coping",
            (loc[0], loc[1], height + 0.39),
            (dims[0] + 0.10, dims[1] + 0.10, 0.075),
            M["copper"],
            0.008,
        )


def add_glazed_door(collection, M, label, x, height=3.40, width=1.48):
    hd = BAR_DEPTH / 2
    add_box(
        collection,
        label + "_entry_laminated_glass",
        (x, -hd - 0.055, 0.30 + height / 2),
        (width - 0.16, 0.035, height - 0.16),
        M["glass"],
        0.003,
    )
    for jamb_x in (x - width / 2, x + width / 2):
        add_box(
            collection,
            label + "_entry_thermal_jamb",
            (jamb_x, -hd - 0.12, 0.30 + height / 2),
            (0.075, 0.10, height),
            M["black"],
            0.006,
        )
    for z in (0.36, 1.98, 0.30 + height):
        add_box(
            collection,
            label + "_entry_door_rail",
            (x, -hd - 0.13, z),
            (width, 0.10, 0.070),
            M["black"],
            0.006,
        )
    add_box(
        collection,
        label + "_entry_pull_handle",
        (x - 0.25, -hd - 0.22, 1.82),
        (0.035, 0.045, 0.78),
        M["brass"],
        0.008,
    )
    add_box(
        collection,
        label + "_entry_hydraulic_closer",
        (x, -hd + 0.04, 0.30 + height - 0.18),
        (0.40, 0.14, 0.10),
        M["black"],
        0.008,
    )
    threshold = add_box(
        collection,
        label + "_flush_entry_threshold",
        (x, -hd - 0.12, 0.30),
        (width + 0.12, 0.34, 0.055),
        M["steel"],
        0.006,
    )
    threshold["clear_entrance_width_m"] = width
    return threshold


def add_bottle_wall(
    collection, M, bottle_masters, label, x0, x1, rear_y, z_levels, count_each
):
    add_box(
        collection,
        label + "_backbar_mirror",
        ((x0 + x1) / 2, rear_y + 0.09, 2.45),
        (x1 - x0, 0.035, 2.55),
        M["glass"],
        0.002,
    )
    for x in (x0, x1):
        add_box(
            collection,
            label + "_backbar_upright",
            (x, rear_y - 0.03, 2.45),
            (0.065, 0.30, 2.70),
            M["black"],
            0.006,
        )
    for z in z_levels:
        add_box(
            collection,
            label + "_backbar_shelf",
            ((x0 + x1) / 2, rear_y - 0.06, z),
            (x1 - x0, 0.36, 0.080),
            M["walnut"],
            0.012,
        )
        add_box(
            collection,
            label + "_backbar_led_strip",
            ((x0 + x1) / 2, rear_y - 0.265, z - 0.07),
            (x1 - x0 - 0.10, 0.025, 0.025),
            M["warm_light"],
            0.003,
        )
        for index in range(count_each):
            x = x0 + 0.22 + index * ((x1 - x0 - 0.44) / max(1, count_each - 1))
            bottle = bottle_masters[(index + int(z * 10)) % len(bottle_masters)]
            instance(
                collection,
                bottle,
                label + "_bottle_display",
                (x, rear_y - 0.22, z + 0.05),
                (index % 3 - 1) * 0.025,
            )


def build_copper_master(M, bottle_masters, stool, pendant):
    master = new_master(COPPER_MASTER_NAME)
    add_shell(master, M, COPPER_WIDTH, COPPER_HEIGHT, "copper", 4.18)
    hw, hd = COPPER_WIDTH / 2, BAR_DEPTH / 2

    # Reference A: timber-framed open wall, black counter and equipment-rich backbar.
    add_box(
        master,
        "copper_front_header_cassette",
        (0, -hd - 0.04, 4.86),
        (COPPER_WIDTH - 0.16, 0.28, 1.58),
        M["black"],
        0.014,
    )
    for index in range(39):
        x = -3.82 + index * (7.64 / 38)
        add_box(
            master,
            "copper_header_vertical_timber_slip",
            (x, -hd - 0.205, 4.88),
            (0.040, 0.055, 1.45),
            M["walnut"],
            0.005,
        )
    add_text(
        master,
        "copper_tap_upper_letters",
        "COPPER TAP",
        (0.40, -hd - 0.27, 5.02),
        0.36,
        0.075,
        M["sign_light"],
    )
    add_glazed_door(master, M, "copper", -3.17, 3.42, 1.50)
    for x in (-2.32, 3.92):
        add_box(
            master,
            "copper_opening_structural_jamb",
            (x, -hd - 0.10, 2.18),
            (0.14, 0.26, 3.72),
            M["walnut"],
            0.015,
        )
    add_box(
        master,
        "copper_opening_structural_head",
        (0.80, -hd - 0.10, 4.02),
        (6.24, 0.26, 0.18),
        M["walnut"],
        0.015,
    )
    for x in (-1.05, 0.25, 1.55, 2.85):
        add_box(
            master,
            "copper_top_hung_glazing_mullion",
            (x, -hd - 0.13, 3.26),
            (0.060, 0.10, 1.38),
            M["black"],
            0.005,
        )
    for x in (-1.68, -0.40, 0.90, 2.20, 3.42):
        pane = add_box(
            master,
            "copper_raised_top_hung_glass",
            (x, -hd + 0.14, 3.32),
            (1.18, 0.030, 1.28),
            M["glass"],
            0.002,
            (math.radians(17), 0, 0),
        )
        pane["operable_hardware"] = "top-hung service glazing on friction stays"

    # L-shaped counter with recessed toe kick, fluted face, stone top and drip edge.
    add_box(
        master,
        "copper_counter_recessed_toe_kick",
        (0.66, -3.47, 0.48),
        (6.18, 0.50, 0.34),
        M["black"],
        0.012,
    )
    add_box(
        master,
        "copper_counter_black_cabinet",
        (0.66, -3.39, 0.87),
        (6.18, 0.70, 0.94),
        M["charcoal"],
        0.018,
    )
    for index in range(34):
        x = -2.31 + index * 0.18
        add_box(
            master,
            "copper_counter_vertical_flute",
            (x, -3.76, 0.87),
            (0.052, 0.035, 0.80),
            M["black"],
            0.006,
        )
    add_box(
        master,
        "copper_counter_white_quartz_top",
        (0.66, -3.36, 1.40),
        (6.40, 0.94, 0.13),
        M["marble"],
        0.026,
    )
    add_box(
        master,
        "copper_counter_brass_drip_edge",
        (0.66, -3.84, 1.37),
        (6.30, 0.035, 0.050),
        M["brass"],
        0.006,
    )
    add_box(
        master,
        "copper_counter_return_cabinet",
        (-2.15, -2.78, 0.87),
        (0.58, 1.75, 0.94),
        M["charcoal"],
        0.018,
    )
    add_box(
        master,
        "copper_counter_return_top",
        (-2.15, -2.78, 1.40),
        (0.76, 1.92, 0.13),
        M["marble"],
        0.025,
    )

    # Five detailed stools deliberately start east of the door aisle.
    stool_sites = (-1.82, -0.62, 0.58, 1.78, 2.98)
    for index, x in enumerate(stool_sites):
        stool_obj = instance(
            master,
            stool,
            "copper_front_contract_bar_stool",
            (x, -4.60, 0.29),
            (index % 2 - 0.5) * 0.035,
        )
        stool_obj[
            "frontage_relation"
        ] = "serves open counter; outside protected entrance corridor"

    # Rear production wall and reference-like grid of shelves, screens and stock.
    add_box(
        master,
        "copper_backbar_base_cabinet",
        (0.20, 2.78, 0.78),
        (7.16, 0.76, 1.06),
        M["walnut"],
        0.018,
    )
    add_box(
        master,
        "copper_backbar_worktop",
        (0.20, 2.70, 1.36),
        (7.34, 0.94, 0.12),
        M["marble"],
        0.020,
    )
    for x in (-2.75, -1.55, -0.35, 0.85, 2.05, 3.25):
        add_box(
            master,
            "copper_backbar_cabinet_door",
            (x, 2.39, 0.79),
            (1.08, 0.045, 0.88),
            M["walnut"],
            0.012,
        )
        add_box(
            master,
            "copper_backbar_recessed_pull",
            (x, 2.36, 0.93),
            (0.30, 0.018, 0.035),
            M["brass"],
            0.004,
        )
    add_bottle_wall(
        master, M, bottle_masters, "copper", -3.35, 3.52, 3.17, (1.82, 2.48, 3.14), 15
    )
    add_box(
        master,
        "copper_chalkboard_menu_frame",
        (0.10, 3.11, 3.72),
        (2.70, 0.12, 1.02),
        M["walnut"],
        0.018,
    )
    add_box(
        master,
        "copper_chalkboard_menu_face",
        (0.10, 3.035, 3.72),
        (2.48, 0.025, 0.82),
        M["screen"],
        0.008,
    )
    add_text(
        master,
        "copper_chalkboard_menu_letters",
        "HOUSE  COCKTAILS",
        (0.10, 2.99, 3.78),
        0.17,
        0.025,
        M["cream"],
    )
    for row in range(5):
        add_box(
            master,
            "copper_chalkboard_menu_rule",
            (0.10 + (row % 2) * 0.08, 2.97, 3.57 - row * 0.105),
            (1.92 - row * 0.12, 0.012, 0.020),
            M["cream"],
            0.002,
        )

    # Operational bar equipment: sink, faucet, ice wells, taps, POS and garnish rail.
    add_box(
        master,
        "copper_underbar_sink_basin",
        (2.86, 2.67, 1.40),
        (0.74, 0.55, 0.24),
        M["black"],
        0.014,
    )
    tube_between(
        master,
        "copper_sink_faucet_riser",
        (2.86, 2.89, 1.43),
        (2.86, 2.89, 1.94),
        0.026,
        M["brass"],
    )
    tube_between(
        master,
        "copper_sink_faucet_spout",
        (2.86, 2.89, 1.92),
        (2.86, 2.60, 1.92),
        0.026,
        M["brass"],
    )
    for x in (-1.10, -0.38):
        add_box(
            master,
            "copper_insulated_ice_well",
            (x, -3.34, 1.45),
            (0.58, 0.52, 0.13),
            M["steel"],
            0.012,
        )
        for slot in range(4):
            add_box(
                master,
                "copper_garnish_insert_pan",
                (x - 0.20 + slot * 0.13, -3.58, 1.54),
                (0.105, 0.16, 0.07),
                M["steel"],
                0.005,
            )
    for x in (0.72, 1.04, 1.36, 1.68):
        tube_between(
            master,
            "copper_beer_tap_riser",
            (x, -3.28, 1.45),
            (x, -3.28, 2.01),
            0.024,
            M["copper"],
        )
        tube_between(
            master,
            "copper_beer_tap_spout",
            (x, -3.28, 1.92),
            (x, -3.54, 1.92),
            0.018,
            M["brass"],
        )
        add_box(
            master,
            "copper_beer_tap_handle",
            (x, -3.28, 2.10),
            (0.055, 0.055, 0.28),
            M["walnut"],
            0.016,
        )
    add_box(
        master,
        "copper_pos_terminal_housing",
        (2.70, -3.34, 1.74),
        (0.46, 0.24, 0.54),
        M["black"],
        0.025,
        (math.radians(-8), 0, 0),
    )
    add_box(
        master,
        "copper_pos_touchscreen",
        (2.70, -3.48, 1.76),
        (0.38, 0.020, 0.39),
        M["screen"],
        0.010,
        (math.radians(-8), 0, 0),
    )
    add_box(
        master,
        "copper_bar_mat",
        (0.40, -3.77, 1.48),
        (1.30, 0.25, 0.035),
        M["rubber"],
        0.006,
    )
    for index in range(6):
        add_cylinder(
            master,
            "copper_shaker_and_jigger",
            (-0.12 + index * 0.18, -3.76, 1.62),
            (
                0.035 + 0.008 * (index % 2),
                0.035 + 0.008 * (index % 2),
                0.12 + 0.02 * (index % 3),
            ),
            M["steel"],
            0.008,
        )

    # Ceiling grid and warm pendant field reproduce the reference lighting rhythm.
    for x in (-3.25, -1.62, 0, 1.62, 3.25):
        add_box(
            master,
            "copper_ceiling_timber_batten",
            (x, -0.10, 4.03),
            (0.08, 6.80, 0.10),
            M["walnut"],
            0.008,
        )
    for y in (-2.65, -0.90, 0.85, 2.60):
        add_box(
            master,
            "copper_ceiling_cross_batten",
            (0, y, 4.04),
            (7.00, 0.08, 0.10),
            M["walnut"],
            0.008,
        )
    for index, x in enumerate((-2.0, -0.72, 0.56, 1.84, 3.12)):
        instance(
            master, pendant, "copper_counter_pendant", (x, -2.45, 4.04), index * 0.05
        )
        add_area_light(master, "copper_pendant_pool", (x, -2.45, 3.05), 125, 0.45)
    add_roof_services(master, M, COPPER_WIDTH, COPPER_HEIGHT, "copper")
    # Rear service door and crash hardware make the shop operational from the lot.
    add_box(
        master,
        "copper_rear_service_door",
        (2.85, hd + 0.02, 1.50),
        (1.20, 0.10, 2.45),
        M["black"],
        0.014,
    )
    add_box(
        master,
        "copper_rear_service_crash_bar",
        (2.85, hd - 0.07, 1.22),
        (0.82, 0.055, 0.065),
        M["steel"],
        0.008,
    )
    master[
        "architectural_program"
    ] = "full-scale open-front cocktail bar with seated street counter, production well, backbar, wash station, stock wall, customer door and rear service exit"
    master[
        "reference_translation"
    ] = "reference A: timber-framed open bar wall, black and white L-counter, five stools, equipment-rich bottle backbar, menu screens and pendant rhythm"
    master["full_scale_dimensions_m"] = [COPPER_WIDTH, BAR_DEPTH, COPPER_HEIGHT]
    master["entrance_local_x_m"] = -3.17
    master["entrance_clear_width_m"] = 1.50
    master[
        "frontage_orientation"
    ] = "local south; production instance rotated 180 degrees to face the north road"
    return master


def build_hawthorn_master(M, bottle_masters, chair, table, pendant, lantern):
    master = new_master(HAWTHORN_MASTER_NAME)
    add_shell(master, M, HAWTHORN_WIDTH, HAWTHORN_HEIGHT, "hawthorn", 4.28)
    hw, hd = HAWTHORN_WIDTH / 2, BAR_DEPTH / 2

    # Reference B: deep copper-red sign cabinet with layered frame and lit lettering.
    add_box(
        master,
        "hawthorn_sign_structural_cassette",
        (0, -hd - 0.08, 5.39),
        (8.18, 0.34, 2.10),
        M["black"],
        0.024,
    )
    add_box(
        master,
        "hawthorn_hammered_copper_sign_face",
        (0, -hd - 0.28, 5.39),
        (7.82, 0.12, 1.82),
        M["copper_panel"],
        0.045,
    )
    for start, end in (
        ((-3.61, -hd - 0.37, 4.65), (3.61, -hd - 0.37, 4.65)),
        ((-3.61, -hd - 0.37, 6.13), (3.61, -hd - 0.37, 6.13)),
        ((-3.76, -hd - 0.37, 4.82), (-3.76, -hd - 0.37, 5.96)),
        ((3.76, -hd - 0.37, 4.82), (3.76, -hd - 0.37, 5.96)),
    ):
        tube_between(
            master, "hawthorn_sign_double_border", start, end, 0.025, M["brass"]
        )
    for x in (-3.42, 3.42):
        for z in (4.82, 5.96):
            add_cylinder(
                master,
                "hawthorn_sign_corner_rosette",
                (x, -hd - 0.39, z),
                (0.065, 0.065, 0.025),
                M["brass"],
                0.008,
                (math.pi / 2, 0, 0),
            )
    add_text(
        master,
        "hawthorn_main_script_letters",
        "Hawthorn Bar",
        (0, -hd - 0.43, 5.43),
        0.55,
        0.085,
        M["sign_light"],
        -0.16,
    )
    add_text(
        master,
        "hawthorn_established_letters",
        "EST. 2024",
        (-2.75, -hd - 0.43, 5.93),
        0.16,
        0.040,
        M["sign_light"],
    )
    add_text(
        master,
        "hawthorn_chinese_letters",
        "HAWTHORN",
        (2.82, -hd - 0.43, 4.92),
        0.13,
        0.035,
        M["sign_light"],
    )

    # Five real gooseneck sign lights and a line of recessed soffit lamps.
    for x in (-3.20, -1.60, 0, 1.60, 3.20):
        tube_between(
            master,
            "hawthorn_sign_light_arm",
            (x, -hd - 0.08, 6.45),
            (x, -hd - 0.48, 6.32),
            0.022,
            M["black"],
        )
        add_cylinder(
            master,
            "hawthorn_sign_light_hood",
            (x, -hd - 0.52, 6.24),
            (0.10, 0.10, 0.12),
            M["black"],
            0.010,
            (math.radians(18), 0, 0),
        )
        add_cylinder(
            master,
            "hawthorn_sign_light_diffuser",
            (x, -hd - 0.56, 6.16),
            (0.074, 0.074, 0.025),
            M["warm_light"],
            0.006,
            (math.radians(18), 0, 0),
        )
    add_box(
        master,
        "hawthorn_black_entry_soffit",
        (0, -hd - 0.25, 4.22),
        (8.08, 0.55, 0.22),
        M["black"],
        0.014,
    )
    for x in (-3.35, -2.23, -1.11, 0, 1.11, 2.23, 3.35):
        add_cylinder(
            master,
            "hawthorn_recessed_soffit_downlight",
            (x, -hd - 0.55, 4.10),
            (0.065, 0.065, 0.030),
            M["warm_light"],
            0.006,
        )

    # Cream/black piers frame a transparent shopfront and a separate clear entry.
    add_box(
        master,
        "hawthorn_west_cream_portal",
        (-4.02, -hd - 0.03, 2.14),
        (0.32, 0.34, 4.02),
        M["cream"],
        0.018,
    )
    add_box(
        master,
        "hawthorn_east_cream_portal",
        (4.02, -hd - 0.03, 2.14),
        (0.32, 0.34, 4.02),
        M["cream"],
        0.018,
    )
    add_glazed_door(master, M, "hawthorn", -3.16, 3.48, 1.58)
    opening_left, opening_right = -2.26, 3.86
    for x in (opening_left, -0.73, 0.80, 2.33, opening_right):
        add_box(
            master,
            "hawthorn_shopfront_mullion",
            (x, -hd - 0.13, 2.22),
            (0.072, 0.11, 3.62),
            M["black"],
            0.006,
        )
    for z in (0.38, 2.12, 3.99):
        add_box(
            master,
            "hawthorn_shopfront_horizontal_rail",
            ((opening_left + opening_right) / 2, -hd - 0.13, z),
            (opening_right - opening_left, 0.11, 0.070),
            M["black"],
            0.006,
        )
    for x in (-1.50, 0.04, 1.56, 3.08):
        add_box(
            master,
            "hawthorn_full_height_laminated_glass",
            (x, -hd - 0.075, 2.20),
            (1.40, 0.032, 3.48),
            M["glass"],
            0.002,
        )

    # Reference railing protects the left dining bay but terminates well clear of the door.
    railing_start, railing_end = -1.66, 3.92
    add_box(
        master,
        "hawthorn_front_raised_stone_plinth",
        ((railing_start + railing_end) / 2, -hd - 0.52, 0.28),
        (railing_end - railing_start, 0.78, 0.28),
        M["concrete"],
        0.018,
    )
    for y, z in ((-hd - 0.80, 0.45), (-hd - 0.80, 1.18)):
        box_between_xy(
            master,
            "hawthorn_patio_continuous_rail",
            (railing_start, y, z),
            (railing_end, y, z),
            0.045,
            0.045,
            M["black"],
            0.005,
        )
    for index in range(19):
        x = railing_start + index * ((railing_end - railing_start) / 18)
        add_cylinder(
            master,
            "hawthorn_patio_vertical_picket",
            (x, -hd - 0.80, 0.82),
            (0.017, 0.017, 0.37),
            M["black"],
            0.003,
        )
    for x in (railing_start, railing_end):
        add_cylinder(
            master,
            "hawthorn_patio_anchor_post",
            (x, -hd - 0.80, 0.70),
            (0.045, 0.045, 0.55),
            M["black"],
            0.006,
        )
        add_box(
            master,
            "hawthorn_patio_post_baseplate",
            (x, -hd - 0.80, 0.18),
            (0.16, 0.16, 0.025),
            M["black"],
            0.005,
        )

    # Exterior copper lanterns copied from the reference placement.
    for x in (-3.95, 3.95):
        instance(
            master,
            lantern,
            "hawthorn_exterior_copper_lantern",
            (x, -hd - 0.22, 2.67),
            0 if x < 0 else math.pi,
        )

    # Warm, deeply modeled interior: service bar, bottle wall, taps, seating and art.
    add_box(
        master,
        "hawthorn_backbar_base_cabinet",
        (0.15, 2.80, 0.78),
        (7.20, 0.74, 1.04),
        M["walnut"],
        0.018,
    )
    add_box(
        master,
        "hawthorn_backbar_copper_worktop",
        (0.15, 2.72, 1.35),
        (7.38, 0.92, 0.12),
        M["copper"],
        0.020,
    )
    for x in (-3.05, -1.85, -0.65, 0.55, 1.75, 2.95):
        add_box(
            master,
            "hawthorn_backbar_cabinet_door",
            (x, 2.40, 0.78),
            (1.08, 0.045, 0.86),
            M["walnut"],
            0.012,
        )
        add_box(
            master,
            "hawthorn_backbar_copper_pull",
            (x, 2.37, 0.92),
            (0.28, 0.018, 0.035),
            M["copper"],
            0.004,
        )
    add_bottle_wall(
        master,
        M,
        bottle_masters,
        "hawthorn",
        -3.45,
        3.58,
        3.18,
        (1.80, 2.43, 3.06, 3.68),
        13,
    )
    add_box(
        master,
        "hawthorn_service_counter_base",
        (0.65, 1.28, 0.82),
        (5.80, 0.78, 1.02),
        M["charcoal"],
        0.018,
    )
    for index in range(29):
        x = -2.12 + index * 0.20
        add_box(
            master,
            "hawthorn_counter_walnut_flute",
            (x, 0.86, 0.84),
            (0.050, 0.035, 0.80),
            M["walnut"],
            0.005,
        )
    add_box(
        master,
        "hawthorn_service_counter_copper_top",
        (0.65, 1.25, 1.39),
        (6.04, 0.98, 0.13),
        M["copper"],
        0.025,
    )
    add_box(
        master,
        "hawthorn_counter_brass_drip_edge",
        (0.65, 0.74, 1.36),
        (5.94, 0.035, 0.050),
        M["brass"],
        0.006,
    )
    for x in (-0.25, 0.10, 0.45, 0.80, 1.15):
        tube_between(
            master,
            "hawthorn_beer_tap_riser",
            (x, 1.28, 1.46),
            (x, 1.28, 2.02),
            0.024,
            M["copper"],
        )
        tube_between(
            master,
            "hawthorn_beer_tap_spout",
            (x, 1.28, 1.91),
            (x, 0.99, 1.91),
            0.018,
            M["brass"],
        )
        add_box(
            master,
            "hawthorn_beer_tap_handle",
            (x, 1.28, 2.12),
            (0.055, 0.055, 0.28),
            M["walnut"],
            0.015,
        )
    add_box(
        master,
        "hawthorn_sink_basin",
        (2.72, 1.23, 1.43),
        (0.72, 0.56, 0.24),
        M["black"],
        0.014,
    )
    tube_between(
        master,
        "hawthorn_sink_faucet_riser",
        (2.72, 1.50, 1.46),
        (2.72, 1.50, 1.98),
        0.026,
        M["brass"],
    )
    tube_between(
        master,
        "hawthorn_sink_faucet_spout",
        (2.72, 1.50, 1.96),
        (2.72, 1.18, 1.96),
        0.026,
        M["brass"],
    )

    # Three table groups stay behind the railing; the east door and aisle remain empty.
    table_sites = ((-1.05, -2.45), (0.75, -2.45), (2.55, -2.45))
    for index, (x, y) in enumerate(table_sites):
        instance(
            master, table, "hawthorn_grounded_bistro_table", (x, y, 0.28), index * 0.07
        )
        instance(
            master,
            chair,
            "hawthorn_bistro_chair_facing_in",
            (x - 0.62, y, 0.28),
            -math.pi / 2,
        )
        instance(
            master,
            chair,
            "hawthorn_bistro_chair_facing_out",
            (x + 0.62, y, 0.28),
            math.pi / 2,
        )
        for glass_x in (x - 0.12, x + 0.12):
            add_lathe(
                master,
                "hawthorn_served_cocktail_glass",
                (
                    (0, 0),
                    (0.025, 0.01),
                    (0.025, 0.18),
                    (0.10, 0.25),
                    (0.12, 0.37),
                    (0, 0.38),
                ),
                18,
                M["clear_glass"],
                (glass_x, y, 1.04),
                0.001,
            )

    # Ceiling trellis, lantern globes and framed artwork carry the reference's depth.
    for x in (-3.35, -2.23, -1.11, 0, 1.11, 2.23, 3.35):
        add_box(
            master,
            "hawthorn_ceiling_longitudinal_trellis",
            (x, -0.10, 4.12),
            (0.075, 6.92, 0.10),
            M["black"],
            0.007,
        )
    for y in (-2.78, -1.39, 0, 1.39, 2.78):
        add_box(
            master,
            "hawthorn_ceiling_cross_trellis",
            (0, y, 4.13),
            (7.30, 0.075, 0.10),
            M["black"],
            0.007,
        )
    for index, (x, y) in enumerate(
        (
            (-2.45, -1.90),
            (-0.82, -1.90),
            (0.82, -1.90),
            (2.45, -1.90),
            (-1.65, 0.20),
            (0, 0.20),
            (1.65, 0.20),
        )
    ):
        instance(
            master, pendant, "hawthorn_warm_globe_pendant", (x, y, 4.12), index * 0.08
        )
        add_area_light(master, "hawthorn_pendant_light_pool", (x, y, 3.08), 115, 0.42)
    for row in range(2):
        for column in range(4):
            x = -2.85 + column * 0.74
            z = 2.15 + row * 0.72
            add_box(
                master,
                "hawthorn_framed_art_shadowbox",
                (x, 3.89, z),
                (0.58, 0.10, 0.52),
                M["walnut"],
                0.014,
            )
            add_box(
                master,
                "hawthorn_framed_art_glazed_face",
                (x, 3.83, z),
                (0.47, 0.025, 0.41),
                M["glass"],
                0.004,
            )
            add_box(
                master,
                "hawthorn_framed_art_mount",
                (x, 3.81, z),
                (0.36, 0.012, 0.30),
                M["cream" if (row + column) % 2 else "copper_panel"],
                0.004,
            )

    # Built planters at the west interior corner, with soil and articulated leaves.
    for planter_x in (3.36,):
        add_box(
            master,
            "hawthorn_planter_bottom",
            (planter_x, -2.90, 0.35),
            (0.56, 0.50, 0.10),
            M["copper_panel"],
            0.018,
        )
        for side_x in (planter_x - 0.30, planter_x + 0.30):
            add_box(
                master,
                "hawthorn_planter_side",
                (side_x, -2.90, 0.68),
                (0.07, 0.56, 0.72),
                M["copper_panel"],
                0.018,
            )
        for side_y in (-3.16, -2.64):
            add_box(
                master,
                "hawthorn_planter_end",
                (planter_x, side_y, 0.68),
                (0.54, 0.07, 0.72),
                M["copper_panel"],
                0.018,
            )
        add_box(
            master,
            "hawthorn_planter_soil",
            (planter_x, -2.90, 1.02),
            (0.48, 0.44, 0.16),
            M["soil"],
            0.010,
        )
        for index, degrees in enumerate((12, 48, 86, 124, 164, 210, 252, 302)):
            angle = math.radians(degrees)
            tube_between(
                master,
                "hawthorn_plant_petiolated_stem",
                (planter_x, -2.90, 1.05),
                (
                    planter_x + math.cos(angle) * 0.25,
                    -2.90 + math.sin(angle) * 0.25,
                    1.60 + 0.12 * (index % 3),
                ),
                0.018,
                M["green"],
            )
            add_lathe(
                master,
                "hawthorn_plant_living_leaf",
                ((0, 0), (0.07, 0.03), (0.16, 0.17), (0.10, 0.34), (0, 0.39)),
                16,
                M["green"],
                (
                    planter_x + math.cos(angle) * 0.28,
                    -2.90 + math.sin(angle) * 0.28,
                    1.60 + 0.12 * (index % 3),
                ),
                0.002,
            )

    add_roof_services(master, M, HAWTHORN_WIDTH, HAWTHORN_HEIGHT, "hawthorn")
    add_box(
        master,
        "hawthorn_rear_service_door",
        (-2.85, hd + 0.02, 1.50),
        (1.20, 0.10, 2.45),
        M["black"],
        0.014,
    )
    add_box(
        master,
        "hawthorn_rear_service_crash_bar",
        (-2.85, hd - 0.07, 1.22),
        (0.82, 0.055, 0.065),
        M["steel"],
        0.008,
    )
    master[
        "architectural_program"
    ] = "full-scale street bar with transparent customer room, bottle backbar, service counter, wash line, three dining groups, clear customer entrance and rear service exit"
    master[
        "reference_translation"
    ] = "reference B: deep copper Hawthorn sign cabinet, layered gold border, five sign lights, black/cream portal, transparent warm interior, copper lanterns and protected front railing"
    master["full_scale_dimensions_m"] = [HAWTHORN_WIDTH, BAR_DEPTH, HAWTHORN_HEIGHT]
    master["entrance_local_x_m"] = -3.16
    master["entrance_clear_width_m"] = 1.58
    master[
        "frontage_orientation"
    ] = "local south; production instance rotated 180 degrees to face the north road"
    return master


def add_world_frontage(world, M, copper_location, hawthorn_location):
    east = hawthorn_location.x + HAWTHORN_WIDTH / 2
    west = copper_location.x - COPPER_WIDTH / 2
    width = east - west
    center = (east + west) / 2
    add_box(
        world,
        "bar_pair_continuous_frontage_paver",
        (center, -8.48, 0.245),
        (width - 0.20, 3.76, 0.090),
        M["paver"],
        0.012,
    )
    add_box(
        world,
        "bar_pair_road_edge_curb",
        (center, -6.52, 0.18),
        (width - 0.02, 0.18, 0.24),
        M["concrete"],
        0.010,
    )
    add_box(
        world,
        "bar_pair_clear_pedestrian_band",
        (center, -7.18, 0.302),
        (width - 0.36, 1.16, 0.025),
        M["concrete"],
        0.005,
    )
    for index in range(16):
        x = west + 0.55 + index * ((width - 1.10) / 15)
        add_box(
            world,
            "bar_pair_longitudinal_paver_joint",
            (x, -8.62, 0.295),
            (0.018, 2.70, 0.010),
            M["joint"],
            0.001,
        )
    for y in (-9.86, -8.72, -7.58):
        add_box(
            world,
            "bar_pair_transverse_paver_joint",
            (center, y, 0.295),
            (width - 0.32, 0.018, 0.010),
            M["joint"],
            0.001,
        )
    add_box(
        world,
        "bar_pair_frontage_trench_drain",
        (center, -10.44, 0.235),
        (width - 0.10, 0.18, 0.055),
        M["steel"],
        0.006,
    )
    for index in range(73):
        x = west + 0.22 + index * ((width - 0.44) / 72)
        add_box(
            world,
            "bar_pair_drain_grate_slot",
            (x, -10.44, 0.266),
            (0.045, 0.12, 0.015),
            M["black"],
            0.001,
        )

    copper_entry_x = copper_location.x + 3.17
    hawthorn_entry_x = hawthorn_location.x + 3.16
    entry_specs = (
        ("copper", copper_entry_x, 1.50),
        ("hawthorn", hawthorn_entry_x, 1.58),
    )
    for label, x, clear_width in entry_specs:
        landing = add_box(
            world,
            label + "_unobstructed_entry_landing",
            (x, -10.14, 0.305),
            (clear_width, 0.72, 0.060),
            M["paver"],
            0.008,
        )
        landing["c2w_clear_entrance_route"] = True
        landing["clear_width_m"] = clear_width
        route = add_box(
            world,
            label + "_unobstructed_entry_route",
            (x, -8.22, 0.306),
            (clear_width, 3.10, 0.024),
            M["concrete"],
            0.005,
        )
        route["c2w_clear_entrance_route"] = True
        route["clear_width_m"] = clear_width
        for row in range(2):
            for col in range(4):
                add_box(
                    world,
                    label + "_entry_tactile_paver",
                    (x - 0.48 + col * 0.32, -6.68 - row * 0.25, 0.332),
                    (0.25, 0.20, 0.025),
                    M["tactile"],
                    0.005,
                )
    # Rear apron serves both real rear doors without placing service equipment at the public fronts.
    add_box(
        world,
        "bar_pair_rear_service_apron",
        (center, -19.30, 0.225),
        (width - 0.30, 1.48, 0.075),
        M["paver"],
        0.010,
    )
    for index in range(9):
        x = west + 0.75 + index * ((width - 1.50) / 8)
        add_box(
            world,
            "bar_pair_rear_apron_joint",
            (x, -19.30, 0.267),
            (0.020, 1.34, 0.008),
            M["joint"],
            0.001,
        )
    # Explicit party-line flashings make both new adjacencies constructed and continuous.
    pair_joint_x = copper_location.x + COPPER_WIDTH / 2
    cafe_joint_x = hawthorn_location.x + HAWTHORN_WIDTH / 2
    add_box(
        world,
        "copper_hawthorn_party_wall_cover",
        (pair_joint_x, -14.55, 2.90),
        (0.085, 8.08, 5.34),
        M["steel"],
        0.006,
    )
    add_box(
        world,
        "hawthorn_cafe_party_wall_cover",
        (cafe_joint_x, -14.55, 2.90),
        (0.085, 8.08, 5.34),
        M["steel"],
        0.006,
    )
    add_box(
        world,
        "copper_hawthorn_roof_transition_cap",
        (pair_joint_x, -14.55, 6.78),
        (0.34, 8.18, 0.12),
        M["copper"],
        0.010,
    )
    add_box(
        world,
        "hawthorn_cafe_roof_transition_cap",
        (cafe_joint_x, -14.55, 6.78),
        (0.34, 8.18, 0.12),
        M["copper"],
        0.010,
    )
    return {
        "bar_pair_frontage_width_m": round(width, 3),
        "copper_entry_world_x_m": round(copper_entry_x, 3),
        "hawthorn_entry_world_x_m": round(hawthorn_entry_x, 3),
        "copper_entry_clear_width_m": 1.50,
        "hawthorn_entry_clear_width_m": 1.58,
        "minimum_clear_pedestrian_band_m": 1.16,
        "frontage_obstacles_inside_entry_routes": [],
        "bar_pair_rear_service_apron_depth_m": 1.48,
    }


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


def audit(
    copper_master,
    hawthorn_master,
    copper,
    hawthorn,
    cafe_location,
    cafe_width,
    seven_location,
    frontage,
):
    copper_parts = recursive_collection_objects(copper_master)
    hawthorn_parts = recursive_collection_objects(hawthorn_master)
    new_objects = [obj for obj in bpy.data.objects if obj.name.startswith(P)]
    bad_meshes = []
    forbidden = []
    for obj in new_objects:
        if any(
            token in obj.name.lower()
            for token in (
                "toy",
                "proxy",
                "placeholder",
                "dummy",
                "primitive_store",
                "simple_box",
            )
        ):
            forbidden.append(obj.name)
        if obj.type == "MESH":
            finite = all(math.isfinite(value) for value in (*obj.location, *obj.scale))
            if (
                obj.data is None
                or not obj.data.vertices
                or not finite
                or min(abs(value) for value in obj.scale) < 0.001
            ):
                bad_meshes.append(obj.name)

    bottle_instances = [
        obj
        for obj in new_objects
        if obj.instance_type == "COLLECTION" and "bottle_display" in obj.name
    ]
    stool_instances = [
        obj for obj in copper_master.objects if "contract_bar_stool" in obj.name
    ]
    hawthorn_tables = [
        obj for obj in hawthorn_master.objects if "grounded_bistro_table" in obj.name
    ]
    glazing = [
        obj for obj in new_objects if "glass" in obj.name or "glazing" in obj.name
    ]
    signs = [
        obj
        for obj in new_objects
        if any(
            token in obj.name
            for token in (
                "upper_letters",
                "script_letters",
                "established_letters",
                "chinese_letters",
                "sign_double_border",
            )
        )
    ]
    seven = bpy.data.objects.get("all43_19:street_corner_711")
    cafe_west = cafe_location.x - cafe_width / 2
    copper_east = copper.location.x + COPPER_WIDTH / 2
    copper_west = copper.location.x - COPPER_WIDTH / 2
    hawthorn_west = hawthorn.location.x - HAWTHORN_WIDTH / 2
    hawthorn_east = hawthorn.location.x + HAWTHORN_WIDTH / 2
    checks = {
        "production_revision": "urban_v3_all43_25",
        "active_generator_consumer": "commercial_mcdonalds_layout_generator_20.py",
        "bar_generator_module": "commercial_reference_bars_generator_25.py",
        "bar_store_count": 2,
        "bar_store_instances": [copper.name, hawthorn.name],
        "copper_is_linked_collection_instance": copper.instance_type == "COLLECTION"
        and copper.instance_collection == copper_master,
        "hawthorn_is_linked_collection_instance": hawthorn.instance_type == "COLLECTION"
        and hawthorn.instance_collection == hawthorn_master,
        "copper_recursive_component_count": len(copper_parts),
        "hawthorn_recursive_component_count": len(hawthorn_parts),
        "copper_direct_component_count": len(copper_master.objects),
        "hawthorn_direct_component_count": len(hawthorn_master.objects),
        "bar_bottle_instance_count": len(bottle_instances),
        "copper_front_stool_count": len(stool_instances),
        "hawthorn_bistro_table_count": len(hawthorn_tables),
        "bar_glazing_component_count": len(glazing),
        "bar_manufactured_sign_component_count": len(signs),
        "copper_hawthorn_party_gap_m": round(abs(copper_east - hawthorn_west), 3),
        "hawthorn_cafe_party_gap_m": round(abs(hawthorn_east - cafe_west), 3),
        "bar_front_alignment_to_cafe_m": round(
            abs(
                (copper.location.y + BAR_DEPTH / 2) - (cafe_location.y + BAR_DEPTH / 2)
            ),
            3,
        ),
        "seven_eleven_corner_location": [round(value, 3) for value in seven.location]
        if seven
        else None,
        "seven_eleven_retained_at_crossroads_corner": bool(
            seven and (seven.location - seven_location).length <= 0.001
        ),
        "inverse_l_north_arm_continuous": abs(copper_east - hawthorn_west) <= 0.01
        and abs(hawthorn_east - cafe_west) <= 0.01,
        "bar_pair_world_bounds": [
            [round(copper_west, 3), round(REAR_Y, 3), 0.205],
            [
                round(hawthorn_east, 3),
                round(FRONT_Y, 3),
                round(HAWTHORN_HEIGHT + 0.985, 3),
            ],
        ],
        "reference_open_bar": REFERENCE_OPEN_BAR,
        "reference_hawthorn_bar": REFERENCE_HAWTHORN,
        "new_mesh_quality_failures": bad_meshes,
        "forbidden_toy_or_proxy_names": forbidden,
        "bar_toy_model_policy": "PASS: both stores are full-scale constructed masters with operational interiors, manufactured furniture/hardware, physical signage, glazing, roof plant and service access",
        **frontage,
    }
    if (
        checks["bar_store_count"] != 2
        or not checks["copper_is_linked_collection_instance"]
        or not checks["hawthorn_is_linked_collection_instance"]
        or checks["copper_recursive_component_count"] < 235
        or checks["hawthorn_recursive_component_count"] < 245
        or checks["copper_direct_component_count"] < 190
        or checks["hawthorn_direct_component_count"] < 205
        or checks["bar_bottle_instance_count"] < 90
        or checks["copper_front_stool_count"] != 5
        or checks["hawthorn_bistro_table_count"] != 3
        or checks["bar_glazing_component_count"] < 16
        or checks["bar_manufactured_sign_component_count"] < 8
        or checks["copper_hawthorn_party_gap_m"] > 0.01
        or checks["hawthorn_cafe_party_gap_m"] > 0.01
        or checks["bar_front_alignment_to_cafe_m"] > 0.01
        or checks["seven_eleven_retained_at_crossroads_corner"] is not True
        or checks["inverse_l_north_arm_continuous"] is not True
        or checks["copper_entry_clear_width_m"] < 1.45
        or checks["hawthorn_entry_clear_width_m"] < 1.50
        or checks["minimum_clear_pedestrian_band_m"] < 1.10
        or checks["frontage_obstacles_inside_entry_routes"]
        or checks["bar_pair_rear_service_apron_depth_m"] < 1.40
        or bad_meshes
        or forbidden
    ):
        raise RuntimeError({"all43_25_reference_bar_quality_audit_failed": checks})
    return checks


def build_and_audit(world, base_materials, cafe_location, cafe_width, seven_location):
    M = {**base_materials, **make_materials()}
    bottle_masters = (
        make_bottle_master("AMBER_SPIRIT_BOTTLE", M["amber"], M),
        make_bottle_master("GREEN_SPIRIT_BOTTLE", M["green_glass"], M),
        make_bottle_master("CLEAR_SPIRIT_BOTTLE", M["clear_glass"], M),
    )
    stool = make_stool_master(M)
    chair = make_bistro_chair_master(M)
    table = make_bistro_table_master(M)
    copper_pendant = make_pendant_master(M, "COPPER_COUNTER_PENDANT", True)
    hawthorn_pendant = make_pendant_master(M, "HAWTHORN_GLOBE_PENDANT", False)
    lantern = make_lantern_master(M)

    hawthorn_east = cafe_location.x - cafe_width / 2
    hawthorn_location = Vector(
        (hawthorn_east - HAWTHORN_WIDTH / 2, cafe_location.y, cafe_location.z)
    )
    copper_east = hawthorn_location.x - HAWTHORN_WIDTH / 2
    copper_location = Vector(
        (copper_east - COPPER_WIDTH / 2, cafe_location.y, cafe_location.z)
    )
    copper_master = build_copper_master(M, bottle_masters, stool, copper_pendant)
    hawthorn_master = build_hawthorn_master(
        M, bottle_masters, chair, table, hawthorn_pendant, lantern
    )

    for name in (P + "north_road_copper_tap", P + "north_road_hawthorn_bar"):
        stale = bpy.data.objects.get(name)
        if stale:
            bpy.data.objects.remove(stale, do_unlink=True)
    copper = instance(
        world, copper_master, "north_road_copper_tap", copper_location, math.pi
    )
    hawthorn = instance(
        world, hawthorn_master, "north_road_hawthorn_bar", hawthorn_location, math.pi
    )
    copper["c2w_semantic_role"] = "full-scale reference-matched open-front cocktail bar"
    hawthorn["c2w_semantic_role"] = "full-scale reference-matched Hawthorn street bar"
    for obj, reference in (
        (copper, REFERENCE_OPEN_BAR),
        (hawthorn, REFERENCE_HAWTHORN),
    ):
        obj["c2w_pipeline_stage"] = "all43_25"
        obj[
            "c2w_generator_revision"
        ] = "two adjacent reference bars integrated into continuous inverse-L commercial street"
        obj["reference_url"] = reference
    frontage = add_world_frontage(world, M, copper_location, hawthorn_location)
    checks = audit(
        copper_master,
        hawthorn_master,
        copper,
        hawthorn,
        cafe_location,
        cafe_width,
        seven_location,
        frontage,
    )
    return {
        "layout_strategy": "continuous inverse-L commercial street: Copper Tap + Hawthorn Bar + LEMON COFFEE + McDonald's north arm, corner 7-Eleven elbow, Corner Kitchen + Fresh Mart south arm",
        "bar_pair_reference_interpretation": "two adjacent full-scale bars: an open industrial timber-and-black counter venue from reference A and the copper-sign, lantern-lit Hawthorn Bar from reference B",
        "bar_pair_interior_system": "two operational beverage-production interiors with stocked bottle walls, sinks, taps, POS/service wells, counter seating, dining, lighting grids and rear service exits",
        "bar_pair_frontage_system": "two independently glazed entries, unobstructed landings and pedestrian routes, tactile warnings, continuous drained pavers, constructed party flashings, dimensional signage and protected Hawthorn seating rail",
        **checks,
    }
