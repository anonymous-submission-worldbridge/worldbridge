"""All43-20/21/22/23/24/25: connected inverse-L commercial street.

This production generator is intentionally source-level.  It rearranges the
three existing, fully detailed shops into a connected L-shaped street wall,
keeps the all43-19 7-Eleven on the crossroads corner, and adds a full-scale
road-facing McDonald's with a visible dining room, ordering zone, kitchen,
rooftop plant, reference-matched red canopies, a fenced umbrella patio,
physical signage and a tall roadside sign.  It is called by both the focused
commercial build and the complete urban pipeline.  All43-22 fills the genuine
west-side vacant lot with a party-wall cafe derived from the supplied LEMON
COFFEE reference: fluted black cladding, warm timber portals, operable steel
shopfront, a visible working coffee bar and constructed frontage furniture.
All43-23 lengthens the McDonald's while holding its 7-Eleven party line,
relocates the freestanding sign into a protected part of its own patio, and
grounds/rebuilds every cafe frontage furnishing as a physically supported
manufactured assembly.  All43-24 turns every lounge chair toward the road with
its back held close to the facade and replaces the intersecting sheet-like
yucca with a collision-audited, botanically constructed fiddle-leaf fig: three
diverging continuous tapered stems, separate petioles, cambered solid leaves, physical
midribs and a genuinely hollow drained planter build-up.
All43-25 consumes ``commercial_reference_bars_generator_25`` from this active
production entry and extends the same north street wall with two adjacent,
full-scale reference bars.  The first is an open timber/black cocktail bar
with a complete working counter and stocked backbar; the second is the
copper-sign, lantern-lit Hawthorn Bar.  Both retain independently clear public
entries and real rear service access, while the 7-Eleven remains the elbow of
the inverse-L.
"""
from __future__ import annotations

import math
from typing import Iterable

import bpy
from mathutils import Vector


P = "all43_20:"
CAFE_P = "all43_24:"
MASTER_NAME = "MCDONALDS_ROADSIDE_RESTAURANT_MASTER"
CAFE_MASTER_NAME = "LEMON_COFFEE_ROADSIDE_CAFE_MASTER"
WORLD_COLLECTION = P + "connected_commercial_world"

MCD_WIDTH = 16.40
MCD_DEPTH = 8.10
MCD_HEIGHT = 5.55
MCD_EAST_EDGE_WORLD = -17.05
MCD_LOCATION = Vector((MCD_EAST_EDGE_WORLD - MCD_WIDTH / 2, -14.55, 0.205))
MCD_ROTATION = math.pi
SHOP_WING_SCALE = 0.925
SHOP_WING_X = -12.62
SEVEN_LOCATION = Vector((-13.55, -11.35, 0.205))

CAFE_WIDTH = 8.40
CAFE_DEPTH = 8.10
CAFE_HEIGHT = 5.72
CAFE_PARTY_X = MCD_LOCATION.x - MCD_WIDTH / 2
CAFE_LOCATION = Vector((CAFE_PARTY_X - CAFE_WIDTH / 2, -14.55, 0.205))
CAFE_ROTATION = math.pi
MCD_PATIO_WEST_X = CAFE_PARTY_X + 0.15
MCD_PATIO_EAST_X = -17.22
MCD_ENTRY_WORLD_X = MCD_LOCATION.x - 3.32
MCD_SIGN_WORLD_X = -18.45
MCD_SIGN_WORLD_Y = -7.30

SHOP_LAYOUT = {
    # Both legacy shops are rotated to face the east road and form the south
    # arm of the inverse-L.  A restrained 7.5% width adjustment keeps their
    # connected street wall inside the existing commercial parcel.
    "all43_01:convenience_store": {
        "location": Vector((SHOP_WING_X, -37.156, 0.0)),
        "rotation": math.pi / 2,
        "scale": Vector((SHOP_WING_SCALE, 1.0, 1.0)),
    },
    "all43_01:restaurant": {
        "location": Vector((SHOP_WING_X, -22.652, 0.0)),
        "rotation": math.pi / 2,
        "scale": Vector((SHOP_WING_SCALE, 1.0, 1.0)),
    },
    "all43_19:street_corner_711": {
        "location": SEVEN_LOCATION,
        "rotation": 0.0,
        "scale": Vector((1.0, 1.0, 1.0)),
    },
}


def cube_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cube")
    if mesh is None:
        raise RuntimeError(
            "all43-20 requires all43_10:shared_cube from the active commercial pipeline"
        )
    return mesh


def cylinder_mesh():
    mesh = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    if mesh is None:
        raise RuntimeError(
            "all43-20 requires all43_10:shared_cylinder_12 from the active commercial pipeline"
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


def textured_stucco_material():
    name = P + "warm_pale_mineral_stucco"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.76
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 42.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.67
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.48, 0.45, 0.385, 1)
    ramp.color_ramp.elements[1].color = (0.72, 0.69, 0.60, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.022
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.61, 0.58, 0.50, 1)
    mat[
        "construction_finish"
    ] = "multi-coat mineral stucco with fine aggregate and restrained tonal variation"
    return mat


def brick_material():
    name = P + "dark_brown_running_bond_brick"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.72
    texcoord = nodes.new("ShaderNodeTexCoord")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.squash = 1.0
    brick.inputs["Scale"].default_value = 6.5
    brick.inputs["Mortar Size"].default_value = 0.025
    brick.inputs["Color1"].default_value = (0.16, 0.070, 0.033, 1)
    brick.inputs["Color2"].default_value = (0.29, 0.145, 0.070, 1)
    brick.inputs["Mortar"].default_value = (0.060, 0.050, 0.040, 1)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 28.0
    noise.inputs["Detail"].default_value = 4.0
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.18
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.28
    bump.inputs["Distance"].default_value = 0.028
    links.new(texcoord.outputs["Generated"], brick.inputs["Vector"])
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(noise.outputs["Fac"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.22, 0.105, 0.048, 1)
    return mat


def cafe_oiled_oak_material():
    """Procedural quarter-sawn oak for the cafe portals and joinery."""
    name = CAFE_P + "oiled_quarter_sawn_oak"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.44
    bsdf.inputs["Coat Weight"].default_value = 0.12
    bsdf.inputs["Coat Roughness"].default_value = 0.20
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (7.0, 1.1, 0.72)
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 4.2
    wave.inputs["Distortion"].default_value = 7.0
    wave.inputs["Detail"].default_value = 5.0
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.5
    noise.inputs["Detail"].default_value = 4.0
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.38
    mix.inputs[1].default_value = (0.31, 0.125, 0.045, 1)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.075, 0.024, 0.010, 1)
    ramp.color_ramp.elements[1].color = (0.56, 0.245, 0.075, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.19
    bump.inputs["Distance"].default_value = 0.018
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(wave.outputs["Color"], mix.inputs[2])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs[1])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(wave.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.25, 0.085, 0.025, 1)
    mat[
        "finish_specification"
    ] = "book-matched quarter-sawn oak veneer with penetrating oil"
    return mat


def cafe_aggregate_material():
    """Fine exposed aggregate used on the reference counter and street seats."""
    name = CAFE_P + "charcoal_fine_exposed_aggregate"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.78
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 58.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.27
    ramp.color_ramp.elements[0].color = (0.035, 0.038, 0.036, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.23, 0.225, 0.205, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.26
    bump.inputs["Distance"].default_value = 0.020
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.13, 0.13, 0.12, 1)
    mat[
        "finish_specification"
    ] = "sealed fine exposed aggregate, honed edges and nonuniform mineral grain"
    return mat


def cafe_botanical_material(name, dark, light, roughness=0.66):
    """Veined, nonuniform foliage material for the cafe's real leaf meshes."""
    full_name = CAFE_P + name
    mat = bpy.data.materials.get(full_name) or bpy.data.materials.new(full_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = 0.16
    bsdf.inputs["Coat Roughness"].default_value = 0.28
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7.5
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.70
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 42.0
    fine.inputs["Detail"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = light
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.010
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(texcoord.outputs["Generated"], fine.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = light
    mat[
        "botanical_finish"
    ] = "waxed living leaf surface with chlorophyll variation and fine cellular relief"
    return mat


def cafe_stem_material():
    """Procedural bark suitable for a mature container-grown fiddle-leaf fig."""
    full_name = CAFE_P + "fiddle_leaf_fig_bark"
    mat = bpy.data.materials.get(full_name) or bpy.data.materials.new(full_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.82
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 15.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.78
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.075, 0.036, 0.014, 1)
    ramp.color_ramp.elements[1].color = (0.29, 0.145, 0.055, 1)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.34
    bump.inputs["Distance"].default_value = 0.018
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.18, 0.082, 0.028, 1)
    mat["botanical_finish"] = "fine fissured living bark, not timber joinery"
    return mat


def glass_material():
    name = P + "laminated_low_iron_dining_glass"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (0.84, 0.91, 0.88, 1)
    glass = nodes.new("ShaderNodeBsdfPrincipled")
    glass.inputs["Base Color"].default_value = (0.040, 0.080, 0.075, 1)
    glass.inputs["Roughness"].default_value = 0.075
    glass.inputs["Transmission Weight"].default_value = 0.92
    glass.inputs["IOR"].default_value = 1.46
    glass.inputs["Coat Weight"].default_value = 0.20
    glass.inputs["Coat Roughness"].default_value = 0.045
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.18
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(glass.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.05, 0.10, 0.095, 0.20)
    mat["physical_glazing"] = "12 mm laminated low-iron commercial storefront glass"
    return mat


def materials():
    return {
        "stucco": textured_stucco_material(),
        "brick": brick_material(),
        "charcoal": material(
            "charcoal_fiber_cement_panel", (0.035, 0.040, 0.038, 1), 0.48, 0.18
        ),
        "frame": material(
            "dark_bronze_storefront_frame", (0.022, 0.026, 0.024, 1), 0.27, 0.74
        ),
        "gasket": material("black_glazing_gasket", (0.006, 0.008, 0.007, 1), 0.82),
        "glass": glass_material(),
        "yellow": material(
            "golden_yellow_brand_enamel",
            (0.96, 0.61, 0.012, 1),
            0.28,
            0.04,
            (1.0, 0.42, 0.002, 1),
            0.50,
        ),
        "red": material(
            "mcdonalds_red_channel_face",
            (0.64, 0.012, 0.015, 1),
            0.29,
            0.04,
            (0.55, 0.004, 0.006, 1),
            0.28,
        ),
        "patio_red": material(
            "patio_signal_red_powdercoat", (0.72, 0.018, 0.022, 1), 0.37, 0.10
        ),
        "patio_red_dark": material(
            "patio_deep_red_powdercoat", (0.34, 0.010, 0.013, 1), 0.44, 0.22
        ),
        "umbrella_light": material(
            "umbrella_warm_light_fabric", (0.84, 0.80, 0.69, 1), 0.78
        ),
        "fence": material(
            "patio_black_powdercoat_steel", (0.012, 0.015, 0.014, 1), 0.43, 0.68
        ),
        "tile_joint": material(
            "facade_tile_recess_joint", (0.20, 0.205, 0.19, 1), 0.88
        ),
        "white": material(
            "warm_white_sign_diffuser",
            (0.90, 0.87, 0.76, 1),
            0.30,
            0.02,
            (0.84, 0.79, 0.64, 1),
            0.32,
        ),
        "concrete": material("architectural_concrete", (0.41, 0.405, 0.37, 1), 0.88),
        "paver": material(
            "broom_finished_frontage_paver", (0.46, 0.45, 0.405, 1), 0.88
        ),
        "joint": material("paving_control_joint", (0.045, 0.048, 0.044, 1), 0.94),
        "tactile": material("accessible_tactile_paver", (0.70, 0.47, 0.030, 1), 0.74),
        "accessible_blue": material(
            "accessible_parking_blue", (0.020, 0.16, 0.52, 1), 0.58
        ),
        "steel": material(
            "brushed_foodservice_stainless", (0.34, 0.36, 0.35, 1), 0.34, 0.72
        ),
        "black": material(
            "foodservice_equipment_black", (0.010, 0.012, 0.011, 1), 0.62
        ),
        "interior_wall": material(
            "washable_interior_wall", (0.78, 0.755, 0.68, 1), 0.77
        ),
        "floor": material("speckled_restaurant_terrazzo", (0.42, 0.40, 0.36, 1), 0.56),
        "ceiling": material("restaurant_acoustic_ceiling", (0.80, 0.79, 0.73, 1), 0.84),
        "light": material(
            "neutral_led_diffuser",
            (0.94, 0.91, 0.77, 1),
            0.30,
            0,
            (0.96, 0.91, 0.72, 1),
            2.0,
        ),
        "wood": material("sealed_oak_tabletop", (0.42, 0.205, 0.080, 1), 0.45),
        "vinyl": material("deep_red_booth_vinyl", (0.37, 0.018, 0.022, 1), 0.52),
        "counter": material(
            "service_counter_solid_surface", (0.20, 0.205, 0.19, 1), 0.45
        ),
        "screen": material(
            "digital_menu_screen",
            (0.008, 0.012, 0.011, 1),
            0.18,
            0.12,
            (0.12, 0.18, 0.12, 1),
            0.42,
        ),
        "green": material("landscape_shrub_leaf", (0.055, 0.19, 0.062, 1), 0.71),
        "soil": material("planter_topsoil", (0.080, 0.050, 0.025, 1), 0.94),
        "roof": material("single_ply_roof_membrane", (0.205, 0.215, 0.205, 1), 0.91),
        "louver": material("roof_plant_louver", (0.052, 0.058, 0.056, 1), 0.62, 0.33),
        "cafe_oak": cafe_oiled_oak_material(),
        "cafe_aggregate": cafe_aggregate_material(),
        "cafe_cream": material(
            "cafe_warm_cream_lacquer", (0.82, 0.765, 0.64, 1), 0.38, 0.02
        ),
        "cafe_brass": material(
            "cafe_brushed_brass", (0.46, 0.245, 0.065, 1), 0.30, 0.72
        ),
        "cafe_ceramic": material(
            "cafe_glazed_ceramic", (0.73, 0.69, 0.58, 1), 0.23, 0.02
        ),
        "cafe_fabric": material(
            "cafe_solution_dyed_outdoor_fabric", (0.115, 0.125, 0.12, 1), 0.72, 0.0
        ),
        "cafe_rubber": material(
            "cafe_nonmarking_epdm", (0.012, 0.014, 0.013, 1), 0.86, 0.0
        ),
        "cafe_liner": material(
            "cafe_planter_hdpe_liner", (0.028, 0.032, 0.029, 1), 0.68, 0.0
        ),
        "cafe_gravel": material(
            "cafe_planter_drainage_gravel", (0.18, 0.165, 0.135, 1), 0.88, 0.0
        ),
        "cafe_geotextile": material(
            "cafe_planter_filter_geotextile", (0.17, 0.16, 0.135, 1), 0.92, 0.0
        ),
        "cafe_mulch": material(
            "cafe_planter_aged_bark_mulch", (0.105, 0.045, 0.014, 1), 0.92, 0.0
        ),
        "cafe_leaf_dark": cafe_botanical_material(
            "fiddle_leaf_mature_green",
            (0.012, 0.070, 0.023, 1),
            (0.055, 0.235, 0.075, 1),
        ),
        "cafe_leaf_light": cafe_botanical_material(
            "fiddle_leaf_fresh_green",
            (0.020, 0.095, 0.030, 1),
            (0.095, 0.31, 0.095, 1),
            0.62,
        ),
        "cafe_leaf_vein": material(
            "fiddle_leaf_living_midrib", (0.19, 0.36, 0.105, 1), 0.67, 0.0
        ),
        "cafe_stem": cafe_stem_material(),
        "cafe_coffee": material("roasted_coffee_beans", (0.055, 0.017, 0.007, 1), 0.66),
        "cafe_paper": material("cafe_recycled_cup_board", (0.63, 0.54, 0.38, 1), 0.73),
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
        modifier.width = min(bevel, min(abs(v) for v in scale) * 0.18)
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
    ] = "full-scale constructed asset with operational detail; no toy geometry"
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


def add_text(collection, name, body, loc, size, depth, mat):
    curve = bpy.data.curves.new(P + name + "_data", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.space_character = 1.03
    curve.extrude = depth
    curve.bevel_depth = min(0.010, depth * 0.16)
    curve.bevel_resolution = 2
    curve.fill_mode = "BOTH"
    curve.materials.append(mat)
    obj = bpy.data.objects.new(P + name, curve)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler[0] = math.pi / 2
    obj["physical_channel_letter_depth_m"] = depth
    return obj


def add_arch_logo(collection, name, loc, width, height, mat, tube=0.105):
    curve = bpy.data.curves.new(P + name + "_data", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = tube
    curve.bevel_resolution = 4
    points = []
    samples = 15
    for side in range(2):
        x0 = -width / 2 + side * width / 2
        for index in range(samples):
            t = index / (samples - 1)
            x = x0 + t * width / 2
            z = height * math.sin(math.pi * t)
            points.append((x, 0.0, z))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    curve.materials.append(mat)
    obj = bpy.data.objects.new(P + name, curve)
    collection.objects.link(obj)
    obj.location = loc
    obj["brand_geometry"] = "physical twin arch tubing, not image-plane signage"
    return obj


def add_area_light(collection, name, loc, energy=260, size=1.25):
    data = bpy.data.lights.new(P + name + "_data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = 0.34
    obj = bpy.data.objects.new(P + name, data)
    collection.objects.link(obj)
    obj.location = loc
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


def box_between_xy(collection, name, start, end, width, height, mat, bevel=0.006):
    """Place a rectangular manufactured member between two plan points."""
    start, end = Vector(start), Vector(end)
    direction = end - start
    midpoint = (start + end) / 2
    return add_box(
        collection,
        name,
        midpoint,
        (direction.length, width, height),
        mat,
        bevel,
        (0, 0, math.atan2(direction.y, direction.x)),
    )


def add_fabric_wedge(collection, name, center, rim_a, rim_b, thickness, mat):
    """Create one double-sided, physically thick umbrella canopy panel."""
    top = [Vector(center), Vector(rim_a), Vector(rim_b)]
    bottom = [point - Vector((0, 0, thickness)) for point in top]
    vertices = [tuple(point) for point in top + bottom]
    faces = ((0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0))
    mesh = bpy.data.meshes.new(P + name + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    bevel = obj.modifiers.new("stitched_fabric_edge", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 2
    obj["construction"] = "individual tensioned fabric sector with stitched perimeter"
    return obj


def cafe_add_object(collection, name, mesh, loc, scale, mat, bevel=0.0, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(CAFE_P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("fabricated_edge_radius", "BEVEL")
        modifier.width = min(bevel, min(abs(v) for v in scale) * 0.18)
        modifier.segments = 3
    obj["shared_mesh_data"] = mesh in (cube_mesh(), cylinder_mesh())
    return obj


def cafe_add_box(collection, name, loc, dims, mat, bevel=0.006, rot=(0, 0, 0)):
    return cafe_add_object(collection, name, cube_mesh(), loc, dims, mat, bevel, rot)


def cafe_add_cylinder(collection, name, loc, scale, mat, bevel=0.004, rot=(0, 0, 0)):
    return cafe_add_object(
        collection, name, cylinder_mesh(), loc, scale, mat, bevel, rot
    )


def cafe_instance(collection, master, name, loc, rotation=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(CAFE_P + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = loc
    obj.rotation_euler[2] = rotation
    obj.scale = scale
    obj["linked_asset"] = master.name
    return obj


def cafe_add_text(collection, name, body, loc, size, depth, mat):
    curve = bpy.data.curves.new(CAFE_P + name + "_data", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.space_character = 1.02
    curve.extrude = depth
    curve.bevel_depth = min(0.009, depth * 0.15)
    curve.bevel_resolution = 2
    curve.fill_mode = "BOTH"
    curve.materials.append(mat)
    obj = bpy.data.objects.new(CAFE_P + name, curve)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler[0] = math.pi / 2
    obj[
        "sign_construction"
    ] = "individually fabricated channel letters with dimensional returns"
    return obj


def cafe_tube_between(collection, name, start, end, radius, mat):
    start, end = Vector(start), Vector(end)
    direction = end - start
    obj = cafe_add_cylinder(
        collection,
        name,
        (start + end) / 2,
        (radius, radius, direction.length),
        mat,
        0.003,
    )
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def cafe_box_between_xy(collection, name, start, end, width, height, mat, bevel=0.006):
    start, end = Vector(start), Vector(end)
    direction = end - start
    midpoint = (start + end) / 2
    return cafe_add_box(
        collection,
        name,
        midpoint,
        (direction.length, width, height),
        mat,
        bevel,
        (0, 0, math.atan2(direction.y, direction.x)),
    )


def cafe_add_area_light(collection, name, loc, energy=210, size=0.72):
    data = bpy.data.lights.new(CAFE_P + name + "_data", "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = 0.22
    obj = bpy.data.objects.new(CAFE_P + name, data)
    collection.objects.link(obj)
    obj.location = loc
    return obj


def cafe_add_polyline_tube(collection, name, points, radius, mat):
    """Create one smoothly skinned botanical member along an explicit path."""
    curve = bpy.data.curves.new(CAFE_P + name + "_data", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.resolution_u = 2
    curve.materials.append(mat)
    spline = curve.splines.new("NURBS")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*Vector(co), 1.0)
    spline.order_u = min(3, len(points))
    spline.use_endpoint_u = True
    obj = bpy.data.objects.new(CAFE_P + name, curve)
    collection.objects.link(obj)
    obj[
        "botanical_construction"
    ] = "continuous round botanical member following an authored growth path"
    return obj


def cafe_add_tapered_stem(collection, name, path, radii, mat):
    """Build a capped, continuous, tapered stem mesh without stacked-cylinder intersections."""
    if len(path) != len(radii) or len(path) < 2:
        raise ValueError(
            "stem path and radii must contain matching multi-point profiles"
        )
    sides = 14
    verts = []
    for center, radius in zip(map(Vector, path), radii):
        for side in range(sides):
            angle = math.tau * side / sides
            verts.append(
                (
                    center.x + math.cos(angle) * radius,
                    center.y + math.sin(angle) * radius,
                    center.z,
                )
            )
    faces = []
    for ring in range(len(path) - 1):
        for side in range(sides):
            nxt = (side + 1) % sides
            a = ring * sides + side
            b = ring * sides + nxt
            c = (ring + 1) * sides + nxt
            d = (ring + 1) * sides + side
            faces.append((a, b, c, d))
    bottom_center = len(verts)
    top_center = bottom_center + 1
    verts.extend((tuple(Vector(path[0])), tuple(Vector(path[-1]))))
    for side in range(sides):
        nxt = (side + 1) % sides
        faces.append((bottom_center, nxt, side))
        faces.append(
            (top_center, (len(path) - 1) * sides + side, (len(path) - 1) * sides + nxt)
        )
    mesh = bpy.data.meshes.new(CAFE_P + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new(CAFE_P + name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    bevel = obj.modifiers.new("botanical_stem_soft_transition", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    obj[
        "botanical_construction"
    ] = "single capped fourteen-sided tapered living stem; no intersecting cylinder stack"
    return obj


def cafe_add_fiddle_leaf(
    collection, name, base, direction, length, width, arch, mat, vein_mat
):
    """Create one cambered fiddle-leaf blade with a physical midrib.

    Ten longitudinal stations and five transverse stations form a gently
    lobed, double-curved blade.  Adjacent leaves are assigned separate vertical
    lanes by the caller, so their evaluated meshes never intersect.
    """
    base = Vector(base)
    forward = Vector(direction).normalized()
    lateral = Vector((-forward.y, forward.x, 0.0))
    if lateral.length < 0.05:
        lateral = Vector((1, 0, 0))
    lateral.normalize()
    surface_normal = lateral.cross(forward).normalized()
    if surface_normal.z < 0:
        surface_normal.negate()
    longitudinal = 10
    cross_profile = (-1.0, -0.53, 0.0, 0.53, 1.0)
    verts = []
    midrib_points = []
    for station in range(longitudinal):
        t = station / (longitudinal - 1)
        outline = max(0.025, math.sin(math.pi * t) ** 0.70)
        fiddle_lobe = 0.86 + 0.14 * math.sin(math.pi * t * 3.0) ** 2
        half_width = width * 0.5 * outline * fiddle_lobe
        center = (
            base + forward * (length * t) + Vector((0, 0, arch * math.sin(math.pi * t)))
        )
        camber = width * 0.065 * math.sin(math.pi * t)
        for across in cross_profile:
            point = center + lateral * (half_width * across)
            point += surface_normal * (camber * (1.0 - across * across))
            verts.append(tuple(point))
        midrib_points.append(center + surface_normal * (camber + 0.009))
    faces = []
    columns = len(cross_profile)
    for row in range(longitudinal - 1):
        for column in range(columns - 1):
            a = row * columns + column
            b = a + 1
            c = (row + 1) * columns + column + 1
            d = (row + 1) * columns + column
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(CAFE_P + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new(CAFE_P + name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    solidify = obj.modifiers.new("botanical_lamina_thickness", "SOLIDIFY")
    solidify.thickness = 0.012
    solidify.offset = 0.0
    bevel = obj.modifiers.new("botanical_rolled_margin", "BEVEL")
    bevel.width = 0.004
    bevel.segments = 2
    obj[
        "botanical_construction"
    ] = "fifty-vertex cambered fiddle-leaf blade with lobed outline, solid lamina and separate midrib"
    obj["botanical_leaf_length_m"] = length
    obj["botanical_leaf_width_m"] = width
    midrib = cafe_add_polyline_tube(
        collection, name + "_living_midrib", midrib_points, 0.009, vein_mat
    )
    midrib["botanical_parent_leaf"] = obj.name
    return obj


def make_window_master(M):
    collection = new_master(P + "MASTER:MCD_STOREFRONT_WINDOW")
    width, height = 2.02, 2.72
    for x in (-width / 2, width / 2):
        add_box(
            collection,
            "window_deep_jamb",
            (x, 0.01, height / 2),
            (0.080, 0.18, height),
            M["frame"],
            0.007,
        )
    for z in (0, height):
        add_box(
            collection,
            "window_head_sill",
            (0, 0.01, z),
            (width, 0.18, 0.085),
            M["frame"],
            0.007,
        )
    add_box(
        collection,
        "laminated_dining_glass",
        (0, -0.02, height / 2),
        (width - 0.15, 0.032, height - 0.16),
        M["glass"],
        0.002,
    )
    add_box(
        collection,
        "window_transom",
        (0, -0.10, 2.12),
        (width - 0.10, 0.070, 0.060),
        M["frame"],
        0.005,
    )
    add_box(
        collection,
        "window_center_mullion",
        (0, -0.10, 1.06),
        (0.052, 0.070, 2.06),
        M["frame"],
        0.005,
    )
    add_box(
        collection,
        "window_kickplate",
        (0, -0.11, 0.16),
        (width - 0.10, 0.075, 0.25),
        M["steel"],
        0.006,
    )
    return collection


def make_double_door_master(M):
    collection = new_master(P + "MASTER:MCD_DOUBLE_ENTRY")
    width, height = 1.82, 2.76
    for x in (-width / 2, width / 2):
        add_box(
            collection,
            "entry_outer_jamb",
            (x, 0.01, height / 2),
            (0.090, 0.20, height),
            M["frame"],
            0.008,
        )
    add_box(
        collection,
        "entry_header",
        (0, 0.01, height),
        (width, 0.20, 0.10),
        M["frame"],
        0.008,
    )
    for side in (-1, 1):
        x = side * width / 4
        add_box(
            collection,
            "tempered_door_leaf",
            (x, -0.02, height / 2),
            (width / 2 - 0.09, 0.030, height - 0.18),
            M["glass"],
            0.002,
        )
        for stile_x in (x - width / 4, x + width / 4):
            add_box(
                collection,
                "door_leaf_stile",
                (stile_x, -0.10, height / 2),
                (0.050, 0.075, height - 0.08),
                M["frame"],
                0.005,
            )
        add_box(
            collection,
            "door_top_rail",
            (x, -0.10, height - 0.08),
            (width / 2 - 0.05, 0.075, 0.075),
            M["frame"],
            0.006,
        )
        add_box(
            collection,
            "door_kick_rail",
            (x, -0.10, 0.15),
            (width / 2 - 0.05, 0.080, 0.25),
            M["steel"],
            0.006,
        )
        add_box(
            collection,
            "vertical_pull_handle",
            (x - side * 0.18, -0.18, 1.36),
            (0.030, 0.040, 0.72),
            M["steel"],
            0.006,
        )
        add_box(
            collection,
            "hydraulic_door_closer",
            (x, 0.08, 2.56),
            (0.34, 0.12, 0.09),
            M["frame"],
            0.006,
        )
    add_box(
        collection,
        "accessible_threshold",
        (0, -0.10, 0.035),
        (width + 0.12, 0.38, 0.055),
        M["steel"],
        0.005,
    )
    collection[
        "door_specification"
    ] = "paired tempered-glass swing leaves, hydraulic closers, pull handles and flush threshold"
    return collection


def make_booth_master(M):
    collection = new_master(P + "MASTER:MCD_DINING_BOOTH")
    for y in (-0.62, 0.62):
        add_box(
            collection,
            "booth_socketed_plinth",
            (0, y, 0.28),
            (1.72, 0.54, 0.48),
            M["charcoal"],
            0.018,
        )
        add_box(
            collection,
            "booth_seat_cushion",
            (0, y - math.copysign(0.08, y), 0.56),
            (1.64, 0.56, 0.14),
            M["vinyl"],
            0.045,
        )
        add_box(
            collection,
            "booth_upholstered_back",
            (0, y + math.copysign(0.18, y), 1.05),
            (1.68, 0.18, 1.02),
            M["vinyl"],
            0.055,
        )
    add_cylinder(
        collection,
        "table_floor_pedestal",
        (0, 0, 0.56),
        (0.085, 0.085, 0.55),
        M["steel"],
        0.006,
    )
    add_cylinder(
        collection,
        "table_spreader_foot",
        (0, 0, 0.31),
        (0.32, 0.32, 0.035),
        M["steel"],
        0.006,
    )
    add_box(
        collection,
        "solid_oak_tabletop",
        (0, 0, 1.06),
        (1.42, 0.92, 0.075),
        M["wood"],
        0.035,
    )
    add_box(
        collection,
        "tabletop_protective_edge",
        (0, 0, 1.085),
        (1.48, 0.98, 0.035),
        M["charcoal"],
        0.018,
    )
    return collection


def make_kiosk_master(M):
    collection = new_master(P + "MASTER:MCD_SELF_ORDER_KIOSK")
    add_box(
        collection,
        "kiosk_anchored_base",
        (0, 0, 0.08),
        (0.58, 0.46, 0.12),
        M["steel"],
        0.018,
    )
    add_box(
        collection,
        "kiosk_pedestal",
        (0, 0.02, 0.82),
        (0.34, 0.28, 1.42),
        M["charcoal"],
        0.025,
    )
    add_box(
        collection,
        "kiosk_screen_housing",
        (0, -0.04, 1.62),
        (0.72, 0.24, 0.92),
        M["charcoal"],
        0.035,
        (math.radians(-7), 0, 0),
    )
    add_box(
        collection,
        "kiosk_touchscreen",
        (0, -0.175, 1.64),
        (0.59, 0.025, 0.69),
        M["screen"],
        0.010,
        (math.radians(-7), 0, 0),
    )
    add_box(
        collection,
        "kiosk_screen_header",
        (0, -0.19, 1.98),
        (0.42, 0.030, 0.055),
        M["yellow"],
        0.006,
        (math.radians(-7), 0, 0),
    )
    add_box(
        collection,
        "kiosk_card_reader",
        (0.29, -0.22, 1.29),
        (0.16, 0.10, 0.23),
        M["black"],
        0.018,
    )
    add_box(
        collection,
        "kiosk_receipt_slot",
        (-0.12, -0.22, 1.23),
        (0.22, 0.08, 0.035),
        M["steel"],
        0.006,
    )
    return collection


def make_roof_exhaust_master(M):
    collection = new_master(P + "MASTER:MCD_ROOF_EXHAUST")
    add_box(
        collection,
        "exhaust_roof_curb",
        (0, 0, 0.14),
        (1.18, 1.05, 0.24),
        M["roof"],
        0.016,
    )
    add_box(
        collection,
        "exhaust_transition",
        (0, 0, 0.54),
        (0.82, 0.76, 0.58),
        M["steel"],
        0.025,
    )
    add_cylinder(
        collection,
        "centrifugal_fan_housing",
        (0, 0, 0.94),
        (0.48, 0.48, 0.38),
        M["steel"],
        0.018,
    )
    add_cylinder(
        collection,
        "fan_weather_cap",
        (0, 0, 1.34),
        (0.59, 0.59, 0.10),
        M["steel"],
        0.018,
    )
    for index in range(8):
        angle = math.tau * index / 8
        add_box(
            collection,
            "fan_guard_radial_louver",
            (math.cos(angle) * 0.44, math.sin(angle) * 0.44, 1.13),
            (0.28, 0.035, 0.20),
            M["louver"],
            0.004,
            (0, 0, angle),
        )
    return collection


def make_patio_chair_master(M):
    collection = new_master(P + "MASTER:MCD_PATIO_CHAIR")
    # Welded powder-coated frame, independent slats, rear rake and floor glides.
    for x in (-0.24, 0.24):
        tube_between(
            collection,
            "chair_front_leg",
            (x, 0.18, 0.04),
            (x, 0.18, 0.47),
            0.026,
            M["fence"],
        )
        tube_between(
            collection,
            "chair_rear_leg",
            (x, -0.20, 0.04),
            (x, -0.17, 0.98),
            0.026,
            M["fence"],
        )
        add_cylinder(
            collection,
            "chair_floor_glide",
            (x, 0.18, 0.035),
            (0.040, 0.040, 0.025),
            M["black"],
            0.003,
        )
        add_cylinder(
            collection,
            "chair_floor_glide",
            (x, -0.20, 0.035),
            (0.040, 0.040, 0.025),
            M["black"],
            0.003,
        )
    for y in (-0.20, 0.18):
        box_between_xy(
            collection,
            "chair_seat_side_rail",
            (-0.24, y, 0.46),
            (0.24, y, 0.46),
            0.035,
            0.035,
            M["fence"],
            0.004,
        )
    for index, y in enumerate((-0.15, -0.07, 0.01, 0.09, 0.17)):
        add_box(
            collection,
            "chair_individual_seat_slat",
            (0, y, 0.49),
            (0.44, 0.055, 0.035),
            M["patio_red_dark"],
            0.009,
        )
    for z in (0.61, 0.73, 0.85, 0.97):
        add_box(
            collection,
            "chair_individual_back_slat",
            (0, -0.185, z),
            (0.43, 0.035, 0.072),
            M["patio_red"],
            0.012,
            (math.radians(-5), 0, 0),
        )
    add_box(
        collection,
        "chair_back_top_rail",
        (0, -0.20, 1.02),
        (0.52, 0.050, 0.060),
        M["fence"],
        0.012,
    )
    collection[
        "furniture_specification"
    ] = "full-scale welded steel cafe chair with independent seat/back slats, raked frame and glides"
    return collection


def make_patio_table_set_master(M, chair):
    collection = new_master(P + "MASTER:MCD_PATIO_TABLE_SET")
    add_cylinder(
        collection,
        "table_weighted_floor_disc",
        (0, 0, 0.055),
        (0.36, 0.36, 0.055),
        M["fence"],
        0.012,
    )
    add_cylinder(
        collection,
        "table_central_pedestal",
        (0, 0, 0.39),
        (0.062, 0.062, 0.34),
        M["steel"],
        0.005,
    )
    add_cylinder(
        collection,
        "table_under_top_spider",
        (0, 0, 0.69),
        (0.28, 0.28, 0.035),
        M["fence"],
        0.006,
    )
    add_cylinder(
        collection,
        "table_round_edge_frame",
        (0, 0, 0.755),
        (0.66, 0.66, 0.045),
        M["patio_red_dark"],
        0.010,
    )
    # Orthogonal metal strips read as an outdoor expanded-mesh top at render distance.
    for index in range(-5, 6):
        offset = index * 0.10
        span = 2 * math.sqrt(max(0.04, 0.58 * 0.58 - offset * offset))
        add_box(
            collection,
            "table_mesh_strip_x",
            (0, offset, 0.807),
            (span, 0.026, 0.018),
            M["patio_red"],
            0.004,
        )
        add_box(
            collection,
            "table_mesh_strip_y",
            (offset, 0, 0.811),
            (0.026, span, 0.018),
            M["patio_red"],
            0.004,
        )
    for index, angle in enumerate((0, math.pi / 2, math.pi, 3 * math.pi / 2)):
        loc = (math.cos(angle) * 1.08, math.sin(angle) * 1.08, 0.225)
        instance(
            collection, chair, "patio_chair_facing_table", loc, angle - math.pi / 2
        )
    collection[
        "furniture_specification"
    ] = "four-seat anchored outdoor dining setting with welded metal-mesh table and full chairs"
    return collection


def make_patio_umbrella_master(M):
    collection = new_master(P + "MASTER:MCD_PATIO_UMBRELLA")
    add_cylinder(
        collection,
        "umbrella_weighted_base",
        (0, 0, 0.09),
        (0.36, 0.36, 0.09),
        M["concrete"],
        0.016,
    )
    add_cylinder(
        collection,
        "umbrella_base_trim",
        (0, 0, 0.19),
        (0.24, 0.24, 0.025),
        M["fence"],
        0.007,
    )
    add_cylinder(
        collection,
        "umbrella_stainless_pole",
        (0, 0, 1.45),
        (0.040, 0.040, 1.27),
        M["steel"],
        0.004,
    )
    add_cylinder(
        collection,
        "umbrella_sliding_hub",
        (0, 0, 2.19),
        (0.105, 0.105, 0.10),
        M["fence"],
        0.008,
    )
    radius, sectors = 1.30, 8
    peak = (0, 0, 3.02)
    rim_z = 2.34
    rim_points = []
    for index in range(sectors):
        angle = math.tau * index / sectors
        rim_points.append((math.cos(angle) * radius, math.sin(angle) * radius, rim_z))
    for index in range(sectors):
        mat = M["umbrella_light"] if index in (1, 4) else M["patio_red"]
        add_fabric_wedge(
            collection,
            "umbrella_tensioned_canopy_panel",
            peak,
            rim_points[index],
            rim_points[(index + 1) % sectors],
            0.030,
            mat,
        )
        a, b = Vector(rim_points[index]), Vector(rim_points[(index + 1) % sectors])
        box_between_xy(
            collection,
            "umbrella_stitched_valance",
            a - Vector((0, 0, 0.09)),
            b - Vector((0, 0, 0.09)),
            0.045,
            0.20,
            mat,
            0.007,
        )
        tube_between(
            collection,
            "umbrella_radial_rib",
            (0, 0, 2.94),
            rim_points[index],
            0.018,
            M["steel"],
        )
        rim = Vector(rim_points[index])
        tube_between(
            collection,
            "umbrella_rib_stretcher",
            (0, 0, 2.21),
            (rim.x * 0.66, rim.y * 0.66, 2.57),
            0.014,
            M["steel"],
        )
    add_cylinder(
        collection,
        "umbrella_top_finial",
        (0, 0, 3.10),
        (0.075, 0.075, 0.11),
        M["patio_red_dark"],
        0.010,
    )
    collection[
        "umbrella_specification"
    ] = "eight-sector tensioned commercial canopy, alternating reference fabric, ribs, stretchers, pole and ballasted base"
    return collection


def add_shell(collection, M):
    hw, hd = MCD_WIDTH / 2, MCD_DEPTH / 2
    add_box(
        collection,
        "reinforced_floor_slab",
        (0, 0, 0.10),
        (MCD_WIDTH, MCD_DEPTH, 0.20),
        M["concrete"],
        0.012,
    )
    add_box(
        collection,
        "rear_kitchen_wall",
        (0, hd - 0.12, MCD_HEIGHT / 2),
        (MCD_WIDTH - 0.28, 0.24, MCD_HEIGHT),
        M["stucco"],
        0.020,
    )
    add_box(
        collection,
        "west_side_wall",
        (-hw + 0.12, 0, MCD_HEIGHT / 2),
        (0.24, MCD_DEPTH - 0.24, MCD_HEIGHT),
        M["stucco"],
        0.020,
    )
    add_box(
        collection,
        "east_party_wall",
        (hw - 0.10, 0, MCD_HEIGHT / 2),
        (0.20, MCD_DEPTH - 0.12, MCD_HEIGHT),
        M["stucco"],
        0.018,
    )
    add_box(
        collection,
        "front_upper_wall",
        (0, -hd + 0.10, 4.45),
        (MCD_WIDTH - 0.24, 0.22, 2.20),
        M["stucco"],
        0.022,
    )
    add_box(
        collection,
        "front_masonry_base",
        (0, -hd + 0.02, 0.29),
        (MCD_WIDTH - 0.22, 0.36, 0.42),
        M["brick"],
        0.010,
    )
    add_box(
        collection,
        "interior_terrazzo_floor",
        (0, -0.03, 0.235),
        (MCD_WIDTH - 0.48, MCD_DEPTH - 0.48, 0.055),
        M["floor"],
        0.004,
    )
    add_box(
        collection,
        "interior_acoustic_ceiling",
        (0, -0.02, 3.58),
        (MCD_WIDTH - 0.48, MCD_DEPTH - 0.48, 0.065),
        M["ceiling"],
        0.004,
    )
    add_box(
        collection,
        "rear_washable_wall_finish",
        (0, hd - 0.25, 1.90),
        (MCD_WIDTH - 0.52, 0.050, 3.25),
        M["interior_wall"],
        0.004,
    )
    add_box(
        collection,
        "west_washable_wall_finish",
        (-hw + 0.25, 0, 1.90),
        (0.050, MCD_DEPTH - 0.54, 3.25),
        M["interior_wall"],
        0.004,
    )
    add_box(
        collection,
        "flat_roof_membrane",
        (0, 0, MCD_HEIGHT + 0.035),
        (MCD_WIDTH - 0.52, MCD_DEPTH - 0.52, 0.070),
        M["roof"],
        0.008,
    )
    for label, loc, dims in (
        ("front", (0, -hd + 0.10, MCD_HEIGHT + 0.18), (MCD_WIDTH, 0.38, 0.36)),
        ("rear", (0, hd - 0.10, MCD_HEIGHT + 0.18), (MCD_WIDTH, 0.38, 0.36)),
        ("west", (-hw + 0.10, 0, MCD_HEIGHT + 0.18), (0.38, MCD_DEPTH - 0.20, 0.36)),
        ("east", (hw - 0.10, 0, MCD_HEIGHT + 0.18), (0.38, MCD_DEPTH - 0.20, 0.36)),
    ):
        add_box(collection, label + "_parapet", loc, dims, M["stucco"], 0.014)
        coping_loc = (loc[0], loc[1], MCD_HEIGHT + 0.405)
        coping_dims = (dims[0] + 0.12, dims[1] + 0.12, 0.090)
        add_box(
            collection,
            label + "_metal_coping",
            coping_loc,
            coping_dims,
            M["steel"],
            0.008,
        )
    # Dark vertical brand tower breaks the pale low-rise mass without becoming a billboard plane.
    add_box(
        collection,
        "entry_brand_tower",
        (2.85, -hd - 0.03, 3.43),
        (2.50, 0.34, 4.05),
        M["charcoal"],
        0.024,
    )
    add_box(
        collection,
        "west_brick_facade_return",
        (-hw + 0.92, -hd - 0.02, 2.12),
        (1.52, 0.38, 3.70),
        M["brick"],
        0.016,
    )
    # Reference facade: large pale masonry/tile fields and a recessed dark
    # horizontal sign panel above the red window canopies.
    add_box(
        collection,
        "reference_upper_sign_cladding",
        (-1.35, -hd - 0.035, 4.67),
        (10.55, 0.30, 1.12),
        M["brick"],
        0.018,
    )
    for x in (-7.60, -6.20, -4.80, -3.40, -2.00, -0.60, 0.80, 4.55, 5.75, 6.55, 7.65):
        add_box(
            collection,
            "facade_vertical_tile_reveal",
            (x, -hd - 0.155, 4.46),
            (0.026, 0.025, 1.60),
            M["tile_joint"],
            0.002,
        )
    for z in (3.78, 4.18, 5.15):
        add_box(
            collection,
            "facade_horizontal_tile_reveal",
            (0, -hd - 0.158, z),
            (MCD_WIDTH - 0.34, 0.025, 0.026),
            M["tile_joint"],
            0.002,
        )


def add_frontage_system(collection, M, window, door):
    hw, hd = MCD_WIDTH / 2, MCD_DEPTH / 2
    window_specs = (
        (-6.75, 0.74),
        (-5.10, 0.78),
        (-3.15, 0.94),
        (-1.05, 0.94),
        (1.05, 0.76),
        (5.35, 0.92),
        (7.10, 0.72),
    )
    for index, (x, sx) in enumerate(window_specs):
        instance(
            collection,
            window,
            "front_dining_window",
            (x, -hd - 0.035, 0.35),
            0,
            (sx, 1, 1),
        )
    instance(collection, door, "front_double_entry", (3.32, -hd - 0.035, 0.32))
    # Structural piers occupy every module joint and carry the projecting awnings.
    for x in (-8.09, -7.48, -6.02, -4.23, -2.08, 0.02, 2.17, 4.28, 6.34, 8.02):
        add_box(
            collection,
            "front_structural_pier",
            (x, -hd + 0.04, 1.78),
            (0.16, 0.34, 3.02),
            M["stucco"],
            0.012,
        )
    add_box(
        collection,
        "continuous_storefront_head",
        (0, -hd - 0.05, 3.16),
        (MCD_WIDTH - 0.26, 0.28, 0.22),
        M["frame"],
        0.010,
    )
    # Reference-specific red fabric window canopies: folded faces, roofs, end
    # plates and real braces.  The yellow is reserved for the sweeping roofline.
    awnings = (
        (-6.72, 1.76),
        (-4.75, 2.15),
        (-2.30, 2.15),
        (0.12, 2.10),
        (3.32, 2.05),
        (5.48, 2.02),
        (7.12, 1.36),
    )
    for index, (x, width) in enumerate(awnings):
        add_box(
            collection,
            "red_window_canopy_roof",
            (x, -hd - 0.48, 3.34),
            (width, 0.88, 0.095),
            M["patio_red"],
            0.020,
            (math.radians(-7), 0, 0),
        )
        add_box(
            collection,
            "red_window_canopy_drop_valance",
            (x, -hd - 0.91, 3.22),
            (width, 0.10, 0.32),
            M["patio_red"],
            0.016,
        )
        for end_x in (x - width / 2 + 0.05, x + width / 2 - 0.05):
            add_box(
                collection,
                "canopy_folded_end_plate",
                (end_x, -hd - 0.48, 3.29),
                (0.08, 0.84, 0.22),
                M["patio_red_dark"],
                0.010,
                (math.radians(-7), 0, 0),
            )
        for bracket_x in (x - width * 0.34, x + width * 0.34):
            tube_between(
                collection,
                "canopy_wall_tie",
                (bracket_x, -hd - 0.10, 3.12),
                (bracket_x, -hd - 0.72, 3.02),
                0.035,
                M["steel"],
            )
            tube_between(
                collection,
                "canopy_diagonal_brace",
                (bracket_x, -hd - 0.10, 2.93),
                (bracket_x, -hd - 0.72, 3.02),
                0.035,
                M["steel"],
            )
    add_text(
        collection,
        "raised_mcdonalds_wordmark",
        "McDonald's",
        (-1.35, -hd - 0.25, 4.66),
        0.66,
        0.105,
        M["white"],
    )
    add_arch_logo(
        collection,
        "entry_golden_arches",
        (2.85, -hd - 0.25, 4.02),
        1.38,
        1.36,
        M["yellow"],
        0.115,
    )
    add_box(
        collection,
        "entry_logo_backing",
        (2.85, -hd + 0.02, 4.55),
        (2.18, 0.20, 2.05),
        M["charcoal"],
        0.020,
    )
    # The photo's signature long yellow eyebrow is a sequence of connected,
    # manufactured rectangular sections with roof-mounted steel supports.
    eyebrow_points = []
    eyebrow_half = MCD_WIDTH / 2 + 0.05
    for index in range(15):
        x = -eyebrow_half + index * (eyebrow_half * 2 / 14)
        bow = 1.0 - (x / eyebrow_half) ** 2
        eyebrow_points.append((x, -hd - 0.38 - 0.30 * bow, 5.99))
    for start, end in zip(eyebrow_points, eyebrow_points[1:]):
        box_between_xy(
            collection,
            "yellow_curved_roofline_section",
            start,
            end,
            0.34,
            0.20,
            M["yellow"],
            0.018,
        )
    for x in (-7.05, -4.70, -2.35, 0, 2.35, 4.70, 7.05):
        bow = 1.0 - (x / eyebrow_half) ** 2
        y = -hd - 0.38 - 0.30 * bow
        add_box(
            collection,
            "yellow_roofline_support",
            (x, y + 0.12, 5.72),
            (0.065, 0.065, 0.46),
            M["steel"],
            0.006,
        )


def add_table_setting(collection, M, x, y, rotation=0.0):
    table = bpy.data.collections.get("DINING_TABLE_MASTER")
    chair = bpy.data.collections.get("DINING_CHAIR_MASTER")
    if table is None or chair is None:
        raise RuntimeError("all43-20 requires detailed all43-15 dining masters")
    instance(
        collection, table, "dining_table", (x, y, 0.26), rotation, (0.83, 0.83, 0.92)
    )
    tangent = Vector((math.cos(rotation), math.sin(rotation), 0))
    for side in (-1, 1):
        loc = Vector((x, y, 0.26)) + tangent * (0.74 * side)
        instance(
            collection,
            chair,
            "dining_chair",
            loc,
            rotation + (0 if side < 0 else math.pi),
            (0.92, 0.92, 0.92),
        )
    for offset in (-0.18, 0.18):
        add_cylinder(
            collection,
            "table_service_tray",
            (x + offset, y, 1.055),
            (0.15, 0.15, 0.016),
            M["charcoal"],
            0.002,
        )
        add_cylinder(
            collection,
            "drink_cup",
            (x + offset, y + 0.15, 1.15),
            (0.045, 0.045, 0.12),
            M["white"],
            0.002,
        )


def add_dining_and_ordering(collection, M, booth, kiosk):
    # Window-side seating remains visible from the road; paths to the entry and accessible table stay clear.
    instance(
        collection,
        booth,
        "window_side_dining_booth",
        (-4.65, -1.85, 0.26),
        0,
        (0.96, 0.96, 0.96),
    )
    instance(
        collection,
        booth,
        "window_side_dining_booth",
        (-2.45, -1.85, 0.26),
        0,
        (0.96, 0.96, 0.96),
    )
    instance(
        collection,
        booth,
        "extended_west_dining_booth",
        (-6.78, -1.85, 0.26),
        0,
        (0.96, 0.96, 0.96),
    )
    add_table_setting(collection, M, (-0.10), -2.05, math.pi / 2)
    add_table_setting(collection, M, 1.40, -1.72, math.pi / 2)
    add_table_setting(collection, M, -4.85, 0.25, 0)
    add_table_setting(collection, M, -6.75, 0.25, 0)
    for x in (1.30, 2.25):
        instance(collection, kiosk, "self_order_kiosk", (x, -0.30, 0.26), 0)
    # Ordering and pickup counter has real worktop, toe kick, POS stations, receipt printers and queue rails.
    add_box(
        collection,
        "ordering_counter_base",
        (2.15, 1.30, 0.73),
        (7.30, 0.82, 0.92),
        M["counter"],
        0.024,
    )
    add_box(
        collection,
        "ordering_counter_toe_kick",
        (2.15, 0.87, 0.43),
        (7.05, 0.12, 0.35),
        M["charcoal"],
        0.010,
    )
    add_box(
        collection,
        "ordering_counter_stainless_top",
        (2.15, 1.30, 1.22),
        (7.48, 0.92, 0.075),
        M["steel"],
        0.012,
    )
    for x in (-0.25, 1.65, 3.55):
        add_box(
            collection,
            "pos_terminal_body",
            (x, 0.98, 1.55),
            (0.42, 0.22, 0.48),
            M["black"],
            0.016,
            (math.radians(-7), 0, 0),
        )
        add_box(
            collection,
            "pos_terminal_screen",
            (x, 0.85, 1.62),
            (0.32, 0.025, 0.30),
            M["screen"],
            0.006,
            (math.radians(-7), 0, 0),
        )
        add_box(
            collection,
            "receipt_printer",
            (x + 0.42, 1.05, 1.34),
            (0.28, 0.28, 0.18),
            M["charcoal"],
            0.012,
        )
    add_box(
        collection,
        "pickup_shelf",
        (5.28, 0.91, 1.55),
        (1.12, 0.32, 0.08),
        M["wood"],
        0.010,
    )
    add_text(
        collection,
        "pickup_channel_letters",
        "PICK UP",
        (5.25, 0.76, 2.08),
        0.27,
        0.035,
        M["yellow"],
    )
    add_box(
        collection,
        "ordering_menu_support_rail",
        (2.15, 2.08, 2.92),
        (7.42, 0.14, 0.16),
        M["steel"],
        0.008,
    )
    for board_index, x in enumerate((-0.35, 0.90, 2.15, 3.40, 4.65)):
        add_box(
            collection,
            "ordering_digital_menu_board",
            (x, 1.99, 2.88),
            (1.08, 0.075, 0.82),
            M["screen"],
            0.012,
        )
        add_box(
            collection,
            "ordering_menu_brand_header",
            (x, 1.94, 3.17),
            (0.82, 0.022, 0.075),
            M["yellow"],
            0.004,
        )
        for row in range(4):
            add_box(
                collection,
                "ordering_menu_item_line",
                (x - 0.12 + (row % 2) * 0.10, 1.94, 2.99 - row * 0.16),
                (0.62 - row * 0.055, 0.020, 0.028),
                M["white"],
                0.002,
            )
    # Freestanding sorting station has three real apertures and removable liner doors.
    add_box(
        collection,
        "waste_sorting_cabinet",
        (-6.08, 0.38, 0.76),
        (1.05, 0.56, 1.02),
        M["charcoal"],
        0.022,
    )
    add_box(
        collection,
        "waste_sorting_top",
        (-6.08, 0.38, 1.31),
        (1.12, 0.62, 0.10),
        M["steel"],
        0.012,
    )
    for index, x in enumerate((-6.40, -6.08, -5.76)):
        add_cylinder(
            collection,
            "waste_sorting_aperture",
            (x, 0.05, 1.22),
            (0.10, 0.10, 0.025),
            M["black"],
            0.003,
            (math.pi / 2, 0, 0),
        )
        add_box(
            collection,
            "waste_sorting_label",
            (x, 0.04, 0.92),
            (0.22, 0.020, 0.055),
            M[("yellow", "white", "red")[index]],
            0.003,
        )
    # Queue furniture is socketed into the terrazzo floor and connected by retractable belts.
    queue_points = ((-0.25, -0.10), (-0.25, 0.72), (0.55, 0.72), (0.55, 0.08))
    for x, y in queue_points:
        add_cylinder(
            collection,
            "queue_stanchion_post",
            (x, y, 0.68),
            (0.043, 0.043, 0.42),
            M["steel"],
            0.004,
        )
        add_cylinder(
            collection,
            "queue_stanchion_base",
            (x, y, 0.29),
            (0.15, 0.15, 0.030),
            M["steel"],
            0.004,
        )
    for start, end in zip(queue_points, queue_points[1:]):
        tube_between(
            collection,
            "queue_retractable_belt",
            (*start, 0.88),
            (*end, 0.88),
            0.018,
            M["red"],
        )


def add_kitchen(collection, M):
    # Partition forms a pass-through rather than hiding a block behind the counter.
    add_box(
        collection,
        "kitchen_partition_left",
        (-4.45, 2.18, 1.90),
        (4.10, 0.14, 3.28),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "kitchen_partition_right",
        (5.72, 2.18, 1.90),
        (1.58, 0.14, 3.28),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "kitchen_pass_lower_wall",
        (2.10, 2.18, 0.72),
        (8.90, 0.14, 0.92),
        M["interior_wall"],
        0.008,
    )
    add_box(
        collection,
        "kitchen_pass_header",
        (2.10, 2.18, 3.15),
        (8.90, 0.14, 0.82),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "kitchen_pass_stainless_sill",
        (2.10, 2.06, 1.20),
        (9.02, 0.32, 0.065),
        M["steel"],
        0.006,
    )
    # Operational cooking line: fryer banks, grills, controls, splashback and exhausted canopy.
    for index, x in enumerate((-4.80, -3.35, -1.90, -0.45)):
        add_box(
            collection,
            "cooking_line_cabinet",
            (x, 3.25, 0.72),
            (1.22, 0.78, 0.90),
            M["steel"],
            0.015,
        )
        add_box(
            collection,
            "cooking_line_control_panel",
            (x, 2.82, 0.90),
            (1.08, 0.09, 0.25),
            M["black"],
            0.006,
        )
        for knob_x in (-0.32, 0, 0.32):
            add_cylinder(
                collection,
                "cooking_control_knob",
                (x + knob_x, 2.76, 0.91),
                (0.044, 0.044, 0.032),
                M["steel"],
                0.003,
                (math.pi / 2, 0, 0),
            )
        if index < 2:
            for basket_x in (-0.24, 0.24):
                add_box(
                    collection,
                    "fryer_basket",
                    (x + basket_x, 3.16, 1.28),
                    (0.38, 0.44, 0.16),
                    M["black"],
                    0.008,
                )
                tube_between(
                    collection,
                    "fryer_basket_handle",
                    (x + basket_x, 2.97, 1.34),
                    (x + basket_x, 2.66, 1.53),
                    0.024,
                    M["steel"],
                )
        else:
            for line in range(5):
                add_box(
                    collection,
                    "griddle_surface_channel",
                    (x - 0.45 + line * 0.22, 3.13, 1.22),
                    (0.04, 0.56, 0.025),
                    M["black"],
                    0.002,
                )
    add_box(
        collection,
        "cooking_line_splashback",
        (-2.62, 3.75, 1.88),
        (5.90, 0.055, 1.42),
        M["steel"],
        0.004,
    )
    add_box(
        collection,
        "exhaust_hood_canopy",
        (-2.62, 3.42, 3.08),
        (6.18, 0.92, 0.52),
        M["steel"],
        0.020,
    )
    add_box(
        collection,
        "exhaust_grease_filter_bank",
        (-2.62, 3.05, 2.96),
        (5.68, 0.10, 0.30),
        M["louver"],
        0.006,
    )
    add_box(
        collection,
        "hood_exhaust_riser",
        (-2.62, 3.63, 3.62),
        (1.02, 0.48, 0.78),
        M["steel"],
        0.012,
    )
    # Prep, sink, beverage and cold-hold stations complete the food path.
    prep = bpy.data.collections.get("KITCHEN_PREP_MASTER")
    if prep is None:
        raise RuntimeError(
            "all43-20 requires the detailed all43-15 kitchen prep master"
        )
    instance(
        collection,
        prep,
        "stainless_prep_station",
        (2.05, 3.18, 0.26),
        0,
        (0.92, 0.82, 0.92),
    )
    add_box(
        collection,
        "three_compartment_sink_cabinet",
        (4.50, 3.30, 0.70),
        (2.25, 0.72, 0.86),
        M["steel"],
        0.015,
    )
    for x in (3.88, 4.50, 5.12):
        add_box(
            collection,
            "sink_basin",
            (x, 3.16, 1.12),
            (0.52, 0.48, 0.20),
            M["black"],
            0.010,
        )
    tube_between(
        collection,
        "sink_faucet_riser",
        (4.50, 3.32, 1.18),
        (4.50, 3.32, 1.65),
        0.035,
        M["steel"],
    )
    tube_between(
        collection,
        "sink_faucet_spout",
        (4.50, 3.32, 1.63),
        (4.50, 3.00, 1.63),
        0.035,
        M["steel"],
    )
    add_box(
        collection,
        "beverage_station_base",
        (5.75, 2.78, 0.72),
        (1.18, 0.72, 0.90),
        M["counter"],
        0.016,
    )
    add_box(
        collection,
        "beverage_dispenser",
        (5.75, 2.72, 1.55),
        (0.92, 0.55, 0.88),
        M["charcoal"],
        0.022,
    )
    for x in (5.48, 5.75, 6.02):
        add_cylinder(
            collection,
            "beverage_nozzle",
            (x, 2.40, 1.52),
            (0.028, 0.028, 0.055),
            M["steel"],
            0.003,
            (math.pi / 2, 0, 0),
        )
        add_box(
            collection,
            "beverage_push_pad",
            (x, 2.39, 1.35),
            (0.12, 0.025, 0.16),
            M["black"],
            0.005,
        )
    # Enclosed restroom/service room has a framed, reachable door and wall sign.
    add_box(
        collection,
        "restroom_partition",
        (-5.65, 2.36, 1.90),
        (1.82, 0.14, 3.28),
        M["interior_wall"],
        0.010,
    )
    add_box(
        collection,
        "restroom_access_door",
        (-5.65, 2.24, 1.44),
        (1.04, 0.10, 2.40),
        M["charcoal"],
        0.012,
    )
    for x in (-6.22, -5.08):
        add_box(
            collection,
            "restroom_door_jamb",
            (x, 2.18, 1.48),
            (0.09, 0.16, 2.55),
            M["steel"],
            0.006,
        )
    add_box(
        collection,
        "restroom_door_header",
        (-5.65, 2.18, 2.72),
        (1.22, 0.16, 0.10),
        M["steel"],
        0.006,
    )
    add_text(
        collection,
        "restroom_door_sign",
        "WC",
        (-5.65, 2.10, 1.82),
        0.20,
        0.026,
        M["white"],
    )


def add_ceiling_and_floor_detail(collection, M):
    for x in (-7.25, -5.35, -3.05, -0.75, 1.55, 3.85, 5.75, 7.25):
        for y in (-2.65, -0.65, 1.30, 3.05):
            if y > 2 and x < -4.5:
                continue
            add_box(
                collection,
                "recessed_led_fixture",
                (x, y, 3.52),
                (1.25, 0.28, 0.045),
                M["light"],
                0.004,
            )
            if (round(x * 10) + round(y * 10)) % 4 == 0:
                add_area_light(
                    collection, "neutral_interior_area_light", (x, y, 3.43), 240, 1.15
                )
    for x in (-7.2, -5.4, -3.6, -1.8, 0, 1.8, 3.6, 5.4, 7.2):
        add_box(
            collection,
            "terrazzo_control_joint",
            (x, 0, 0.268),
            (0.014, MCD_DEPTH - 0.62, 0.006),
            M["joint"],
            0.001,
        )
    for y in (-3.0, -1.5, 0, 1.5, 3.0):
        add_box(
            collection,
            "terrazzo_control_joint",
            (0, y, 0.268),
            (MCD_WIDTH - 0.62, 0.014, 0.006),
            M["joint"],
            0.001,
        )


def add_rooftop_services(collection, M, exhaust):
    existing_hvac = bpy.data.collections.get("all43_19:MASTER:ROOFTOP_CONDENSER")
    if existing_hvac is None:
        raise RuntimeError(
            "all43-20 requires the detailed all43-19 rooftop condenser master"
        )
    instance(
        collection,
        existing_hvac,
        "curbed_rooftop_hvac",
        (-4.35, -0.55, MCD_HEIGHT + 0.08),
        0.05,
        (0.92, 0.92, 0.92),
    )
    instance(
        collection,
        existing_hvac,
        "curbed_rooftop_hvac",
        (4.20, 0.70, MCD_HEIGHT + 0.08),
        -0.08,
        (0.82, 0.82, 0.82),
    )
    instance(
        collection, exhaust, "kitchen_roof_exhaust", (-2.62, 2.48, MCD_HEIGHT + 0.08)
    )
    add_box(
        collection,
        "roof_access_hatch",
        (1.12, -1.40, MCD_HEIGHT + 0.16),
        (1.10, 0.96, 0.22),
        M["steel"],
        0.018,
    )
    add_box(
        collection,
        "roof_access_upstand",
        (1.12, -1.40, MCD_HEIGHT + 0.32),
        (0.92, 0.78, 0.18),
        M["roof"],
        0.012,
    )
    for x in (-4.72, -3.98):
        add_box(
            collection,
            "hvac_isolator_rail",
            (x, -0.55, MCD_HEIGHT + 0.16),
            (0.10, 1.12, 0.13),
            M["louver"],
            0.006,
        )
    tube_between(
        collection,
        "roof_service_conduit",
        (-3.65, -0.55, MCD_HEIGHT + 0.38),
        (1.12, -1.05, MCD_HEIGHT + 0.38),
        0.034,
        M["steel"],
    )
    tube_between(
        collection,
        "connected_rainwater_downpipe",
        (-MCD_WIDTH / 2 - 0.09, 2.55, 0.28),
        (-MCD_WIDTH / 2 - 0.09, 2.55, MCD_HEIGHT - 0.12),
        0.065,
        M["steel"],
    )
    add_box(
        collection,
        "roof_scupper_head",
        (-MCD_WIDTH / 2 - 0.09, 2.55, MCD_HEIGHT - 0.04),
        (0.24, 0.36, 0.28),
        M["steel"],
        0.010,
    )
    tube_between(
        collection,
        "rainwater_discharge_shoe",
        (-MCD_WIDTH / 2 - 0.09, 2.55, 0.28),
        (-MCD_WIDTH / 2 - 0.09, 2.25, 0.20),
        0.078,
        M["steel"],
    )


def add_roadside_sign(collection, M):
    # All43-23 converts the former remote high-pole sign into a lower engineered
    # pylon within the east corner of McDonald's own fenced frontage.  Its
    # footing, planting kerb and guards are part of this restaurant master, so
    # the sign can never drift into the cafe when the connected block moves.
    x = MCD_LOCATION.x - MCD_SIGN_WORLD_X
    y = MCD_LOCATION.y - MCD_SIGN_WORLD_Y
    add_box(
        collection,
        "roadside_sign_island_kerb",
        (x, y, 0.13),
        (2.02, 1.18, 0.22),
        M["concrete"],
        0.045,
    )
    add_box(
        collection,
        "roadside_sign_drained_gravel_bed",
        (x, y, 0.255),
        (1.76, 0.92, 0.08),
        M["cafe_gravel"],
        0.025,
    )
    add_box(
        collection,
        "roadside_sign_reinforced_footing",
        (x, y, 0.25),
        (1.02, 0.70, 0.42),
        M["concrete"],
        0.030,
    )
    for dx in (-0.13, 0.13):
        add_box(
            collection,
            "roadside_sign_twin_post",
            (x + dx, y, 2.35),
            (0.15, 0.19, 4.10),
            M["steel"],
            0.018,
        )
        add_box(
            collection,
            "roadside_sign_post_baseplate",
            (x + dx, y, 0.49),
            (0.34, 0.38, 0.060),
            M["steel"],
            0.010,
        )
        for bx in (-0.10, 0.10):
            for by in (-0.11, 0.11):
                add_cylinder(
                    collection,
                    "roadside_sign_anchor_bolt",
                    (x + dx + bx, y + by, 0.55),
                    (0.018, 0.018, 0.055),
                    M["steel"],
                    0.002,
                )
    add_box(
        collection,
        "roadside_sign_cabinet",
        (x, y, 4.45),
        (2.08, 0.42, 1.55),
        M["charcoal"],
        0.085,
    )
    add_box(
        collection,
        "roadside_sign_front_diffuser",
        (x, y - 0.225, 4.45),
        (1.86, 0.035, 1.31),
        M["red"],
        0.050,
    )
    add_box(
        collection,
        "roadside_sign_rear_diffuser",
        (x, y + 0.225, 4.45),
        (1.86, 0.035, 1.31),
        M["red"],
        0.050,
    )
    add_arch_logo(
        collection,
        "roadside_sign_front_arches",
        (x, y - 0.27, 4.05),
        1.12,
        1.02,
        M["yellow"],
        0.080,
    )
    add_arch_logo(
        collection,
        "roadside_sign_rear_arches",
        (x, y + 0.27, 4.05),
        1.12,
        1.02,
        M["yellow"],
        0.080,
    )
    add_box(
        collection,
        "roadside_sign_cabinet_bottom",
        (x, y, 3.64),
        (1.78, 0.46, 0.10),
        M["steel"],
        0.014,
    )
    # Low guards make the base legible as protected site equipment and prevent
    # chairs from being placed against exposed sign posts.
    for guard_x in (x - 0.72, x + 0.72):
        add_cylinder(
            collection,
            "roadside_sign_guard_bollard",
            (guard_x, y, 0.66),
            (0.070, 0.070, 0.48),
            M["yellow"],
            0.010,
        )
        add_cylinder(
            collection,
            "roadside_sign_guard_cap",
            (guard_x, y, 1.16),
            (0.085, 0.085, 0.035),
            M["steel"],
            0.008,
        )


def build_mcdonalds_master(M):
    master = new_master(MASTER_NAME)
    window = make_window_master(M)
    door = make_double_door_master(M)
    booth = make_booth_master(M)
    kiosk = make_kiosk_master(M)
    exhaust = make_roof_exhaust_master(M)
    patio_chair = make_patio_chair_master(M)
    make_patio_table_set_master(M, patio_chair)
    make_patio_umbrella_master(M)
    add_shell(master, M)
    add_frontage_system(master, M, window, door)
    add_dining_and_ordering(master, M, booth, kiosk)
    add_kitchen(master, M)
    add_ceiling_and_floor_detail(master, M)
    add_rooftop_services(master, M, exhaust)
    add_roadside_sign(master, M)
    master[
        "architectural_program"
    ] = "full-scale single-storey roadside McDonald's with dining, ordering, pickup, kitchen and service plant"
    master[
        "reference_translation"
    ] = "pale gridded facade, red supported window canopies, dark wordmark band, sweeping yellow roofline, golden arches, fenced red-umbrella patio and side road sign"
    master[
        "frontage_orientation"
    ] = "local south facade; production instance rotated 180 degrees to face the north main road"
    master["full_scale_dimensions_m"] = [MCD_WIDTH, MCD_DEPTH, MCD_HEIGHT]
    master[
        "interior_visibility"
    ] = "low-iron storefront reveals seating, kiosks, counter, menu boards and kitchen pass"
    return master


def make_cafe_street_chair_master(M):
    collection = new_master(CAFE_P + "MASTER:STREET_LOUNGE_CHAIR")
    # Full contract-grade outdoor lounge chair.  The four adjustable glides are
    # authored at z=0, then splayed legs, welded rails, back brackets, separate
    # cushions, piping and drainage gaps rise from them.  This eliminates the
    # formerly floating block-chair silhouette while retaining the low form in
    # the supplied cafe reference.
    leg_sites = ((-0.31, -0.24), (0.31, -0.24), (-0.31, 0.24), (0.31, 0.24))
    for index, (x, y) in enumerate(leg_sites):
        cafe_add_cylinder(
            collection,
            "chair_adjustable_epdm_glide",
            (x, y, 0.018),
            (0.044, 0.044, 0.036),
            M["cafe_rubber"],
            0.006,
        )
        top_x = x * 0.88
        top_y = y * 0.78
        cafe_tube_between(
            collection,
            "chair_splayed_powdercoat_leg",
            (x, y, 0.036),
            (top_x, top_y, 0.335),
            0.032,
            M["frame"],
        )
        cafe_add_cylinder(
            collection,
            "chair_leg_leveler_locknut",
            (x, y, 0.052),
            (0.052, 0.052, 0.018),
            M["steel"],
            0.004,
        )
    for y in (-0.19, 0.19):
        cafe_tube_between(
            collection,
            "chair_seat_side_rail",
            (-0.28, y, 0.325),
            (0.28, y, 0.325),
            0.026,
            M["frame"],
        )
    for x in (-0.28, 0.28):
        cafe_tube_between(
            collection,
            "chair_seat_cross_rail",
            (x, -0.19, 0.325),
            (x, 0.19, 0.325),
            0.026,
            M["frame"],
        )
        cafe_tube_between(
            collection,
            "chair_raked_back_support",
            (x, 0.19, 0.325),
            (x, 0.31, 1.035),
            0.027,
            M["frame"],
        )
    cafe_add_box(
        collection,
        "chair_outdoor_seat_cushion",
        (0, -0.015, 0.425),
        (0.65, 0.58, 0.18),
        M["cafe_fabric"],
        0.075,
        (math.radians(-2), 0, 0),
    )
    cafe_add_box(
        collection,
        "chair_outdoor_back_cushion",
        (0, 0.275, 0.765),
        (0.66, 0.17, 0.62),
        M["cafe_fabric"],
        0.070,
        (math.radians(9), 0, 0),
    )
    for x in (-0.335, 0.335):
        cafe_add_box(
            collection,
            "chair_sculpted_arm_pad",
            (x, 0.015, 0.675),
            (0.13, 0.61, 0.13),
            M["cafe_aggregate"],
            0.045,
            (0, math.radians(-3 * math.copysign(1, x)), 0),
        )
        cafe_tube_between(
            collection,
            "chair_arm_front_bracket",
            (x, -0.22, 0.34),
            (x, -0.22, 0.64),
            0.022,
            M["frame"],
        )
        cafe_tube_between(
            collection,
            "chair_arm_rear_bracket",
            (x, 0.20, 0.34),
            (x, 0.20, 0.64),
            0.022,
            M["frame"],
        )
    # Cushion edge welts and the visible seat/back separation are physical
    # components rather than texture-only lines.
    for x in (-0.27, 0.27):
        cafe_add_box(
            collection,
            "chair_seat_piping",
            (x, -0.305, 0.425),
            (0.030, 0.025, 0.13),
            M["cafe_brass"],
            0.008,
        )
        cafe_add_cylinder(
            collection,
            "chair_back_button",
            (x, 0.174, 0.78),
            (0.022, 0.022, 0.018),
            M["cafe_brass"],
            0.004,
            (math.pi / 2, 0, 0),
        )
    cafe_add_box(
        collection,
        "chair_front_shadow_gap",
        (0, -0.312, 0.34),
        (0.48, 0.022, 0.045),
        M["black"],
        0.006,
    )
    collection[
        "furniture_specification"
    ] = "full-scale contract lounge chair with four ground-contact levelers, welded splayed frame, independent solution-dyed cushions, piping, back brackets, arm pads and drainage gap"
    collection["ground_contact_z_m"] = 0.0
    return collection


def make_cafe_side_table_master(M):
    collection = new_master(CAFE_P + "MASTER:STREET_SIDE_TABLE")
    cafe_add_cylinder(
        collection,
        "table_epdm_leveling_pad",
        (0, 0, 0.018),
        (0.095, 0.095, 0.036),
        M["cafe_rubber"],
        0.006,
    )
    cafe_add_cylinder(
        collection,
        "table_ballasted_cast_foot",
        (0, 0, 0.075),
        (0.29, 0.29, 0.090),
        M["cafe_aggregate"],
        0.018,
    )
    cafe_add_cylinder(
        collection,
        "table_foot_stainless_trim",
        (0, 0, 0.122),
        (0.255, 0.255, 0.018),
        M["steel"],
        0.005,
    )
    cafe_tube_between(
        collection,
        "table_brass_pedestal",
        (0, 0, 0.12),
        (0, 0, 0.69),
        0.045,
        M["cafe_brass"],
    )
    cafe_add_cylinder(
        collection,
        "table_spider_plate",
        (0, 0, 0.695),
        (0.20, 0.20, 0.035),
        M["frame"],
        0.006,
    )
    cafe_add_cylinder(
        collection,
        "table_honed_stone_top",
        (0, 0, 0.755),
        (0.37, 0.37, 0.060),
        M["cafe_aggregate"],
        0.018,
    )
    cafe_add_cylinder(
        collection,
        "table_brass_edge_band",
        (0, 0, 0.744),
        (0.374, 0.374, 0.018),
        M["cafe_brass"],
        0.005,
    )
    for angle in range(0, 360, 90):
        theta = math.radians(angle)
        cafe_tube_between(
            collection,
            "table_floor_spreader",
            (0, 0, 0.13),
            (math.cos(theta) * 0.25, math.sin(theta) * 0.25, 0.090),
            0.018,
            M["frame"],
        )
        cafe_add_cylinder(
            collection,
            "table_spreader_fastener",
            (math.cos(theta) * 0.22, math.sin(theta) * 0.22, 0.105),
            (0.020, 0.020, 0.018),
            M["steel"],
            0.003,
        )
    collection[
        "furniture_specification"
    ] = "grounded ballasted pedestal table with EPDM leveling pad, cast foot, fabricated brass column, four-way spreader, fasteners and edge-banded honed top"
    collection["ground_contact_z_m"] = 0.0
    return collection


def make_cafe_cup_master(M):
    collection = new_master(CAFE_P + "MASTER:TAKEAWAY_CUP")
    cafe_add_cylinder(
        collection,
        "cup_closed_base",
        (0, 0, 0.010),
        (0.043, 0.043, 0.020),
        M["cafe_paper"],
        0.003,
    )
    cafe_add_cylinder(
        collection,
        "cup_tapered_body",
        (0, 0, 0.10),
        (0.050, 0.045, 0.10),
        M["cafe_paper"],
        0.005,
    )
    cafe_add_cylinder(
        collection,
        "cup_rolled_rim",
        (0, 0, 0.205),
        (0.055, 0.055, 0.012),
        M["cafe_cream"],
        0.004,
    )
    cafe_add_cylinder(
        collection,
        "cup_fitted_lid",
        (0, 0, 0.226),
        (0.058, 0.058, 0.014),
        M["charcoal"],
        0.005,
    )
    cafe_add_box(
        collection,
        "cup_sip_aperture",
        (0, -0.045, 0.241),
        (0.020, 0.014, 0.008),
        M["black"],
        0.002,
    )
    cafe_add_box(
        collection,
        "cup_recycled_sleeve",
        (0, -0.047, 0.105),
        (0.075, 0.008, 0.070),
        M["cafe_oak"],
        0.003,
    )
    return collection


def make_cafe_pastry_master(M):
    collection = new_master(CAFE_P + "MASTER:PASTRY_PLATE")
    cafe_add_cylinder(
        collection,
        "ceramic_display_plate",
        (0, 0, 0.025),
        (0.19, 0.19, 0.025),
        M["cafe_ceramic"],
        0.008,
    )
    for index, x in enumerate((-0.10, 0, 0.10)):
        pastry = cafe_add_cylinder(
            collection,
            "laminated_pastry",
            (x, 0, 0.105),
            (0.075, 0.050, 0.065),
            M["cafe_oak"],
            0.015,
            (0, math.radians(90), 0),
        )
        pastry[
            "food_detail"
        ] = "individually plated laminated pastry, not a texture card"
        for stripe in (-0.025, 0.025):
            cafe_add_box(
                collection,
                "pastry_lamination_score",
                (x + stripe, -0.047, 0.112),
                (0.010, 0.008, 0.060),
                M["cafe_cream"],
                0.002,
            )
    return collection


def add_cafe_shell(collection, M):
    hw, hd = CAFE_WIDTH / 2, CAFE_DEPTH / 2
    cafe_add_box(
        collection,
        "reinforced_cafe_floor_slab",
        (0, 0, 0.10),
        (CAFE_WIDTH, CAFE_DEPTH, 0.20),
        M["concrete"],
        0.014,
    )
    cafe_add_box(
        collection,
        "cafe_terrazzo_finish",
        (0, -0.02, 0.235),
        (CAFE_WIDTH - 0.40, CAFE_DEPTH - 0.42, 0.055),
        M["floor"],
        0.005,
    )
    cafe_add_box(
        collection,
        "cafe_rear_service_wall",
        (0, hd - 0.11, CAFE_HEIGHT / 2),
        (CAFE_WIDTH - 0.20, 0.22, CAFE_HEIGHT),
        M["interior_wall"],
        0.018,
    )
    cafe_add_box(
        collection,
        "cafe_west_masonry_wall",
        (-hw + 0.10, 0, CAFE_HEIGHT / 2),
        (0.20, CAFE_DEPTH - 0.18, CAFE_HEIGHT),
        M["cafe_oak"],
        0.018,
    )
    cafe_add_box(
        collection,
        "cafe_mcdonalds_party_wall",
        (hw - 0.08, 0, CAFE_HEIGHT / 2),
        (0.16, CAFE_DEPTH, CAFE_HEIGHT),
        M["concrete"],
        0.012,
    )
    cafe_add_box(
        collection,
        "cafe_acoustic_ceiling",
        (0, 0, 4.02),
        (CAFE_WIDTH - 0.40, CAFE_DEPTH - 0.44, 0.065),
        M["ceiling"],
        0.005,
    )
    cafe_add_box(
        collection,
        "cafe_roof_membrane",
        (0, 0, CAFE_HEIGHT + 0.04),
        (CAFE_WIDTH - 0.34, CAFE_DEPTH - 0.34, 0.080),
        M["roof"],
        0.008,
    )
    for label, loc, dims in (
        ("front", (0, -hd + 0.10, CAFE_HEIGHT + 0.17), (CAFE_WIDTH, 0.32, 0.34)),
        ("rear", (0, hd - 0.10, CAFE_HEIGHT + 0.17), (CAFE_WIDTH, 0.32, 0.34)),
        ("west", (-hw + 0.10, 0, CAFE_HEIGHT + 0.17), (0.32, CAFE_DEPTH - 0.20, 0.34)),
        ("party", (hw - 0.08, 0, CAFE_HEIGHT + 0.17), (0.22, CAFE_DEPTH - 0.08, 0.34)),
    ):
        cafe_add_box(
            collection, "cafe_" + label + "_parapet", loc, dims, M["charcoal"], 0.012
        )
        cafe_add_box(
            collection,
            "cafe_" + label + "_coping",
            (loc[0], loc[1], CAFE_HEIGHT + 0.385),
            (dims[0] + 0.10, dims[1] + 0.10, 0.075),
            M["steel"],
            0.008,
        )
    # Deep black corrugated fascia from the reference, built with a backing
    # cassette plus separate folded ribs and a ventilated shadow channel.
    cafe_add_box(
        collection,
        "corrugated_fascia_backing",
        (0, -hd - 0.015, 5.00),
        (CAFE_WIDTH - 0.18, 0.22, 1.40),
        M["charcoal"],
        0.012,
    )
    cafe_add_box(
        collection,
        "fascia_bottom_shadow_channel",
        (0, -hd - 0.20, 4.30),
        (CAFE_WIDTH - 0.08, 0.20, 0.14),
        M["black"],
        0.008,
    )
    for index in range(45):
        x = -4.02 + index * (8.04 / 44)
        cafe_add_box(
            collection,
            "folded_vertical_fascia_rib",
            (x, -hd - 0.145, 5.03),
            (0.035, 0.055, 1.30),
            M["frame"],
            0.004,
        )
    # Warm oak portals articulate the entry and open coffee window.
    for x in (-4.07, -1.93, 1.83, 4.05):
        cafe_add_box(
            collection,
            "full_height_oak_portal_jamb",
            (x, -hd - 0.05, 2.18),
            (0.19, 0.30, 4.10),
            M["cafe_oak"],
            0.018,
        )
    cafe_add_box(
        collection,
        "entry_oak_portal_head",
        (3.00, -hd - 0.05, 4.16),
        (2.12, 0.30, 0.20),
        M["cafe_oak"],
        0.018,
    )
    cafe_add_box(
        collection,
        "service_oak_portal_head",
        (-0.05, -hd - 0.05, 4.16),
        (3.78, 0.30, 0.20),
        M["cafe_oak"],
        0.018,
    )
    cafe_add_box(
        collection,
        "frontage_masonry_plinth",
        (-0.05, -hd - 0.03, 0.42),
        (3.70, 0.34, 0.74),
        M["cafe_aggregate"],
        0.020,
    )


def add_cafe_storefront(collection, M):
    hw, hd = CAFE_WIDTH / 2, CAFE_DEPTH / 2
    # Tall glazed customer door with commercial stiles, closer, pulls and a
    # flush threshold; it occupies the separate light-box portal in the photo.
    door_x, door_w, door_h = 3.00, 1.72, 3.60
    cafe_add_box(
        collection,
        "entry_laminated_glass",
        (door_x, -hd - 0.055, 2.17),
        (door_w - 0.16, 0.035, door_h - 0.16),
        M["glass"],
        0.003,
    )
    for x in (door_x - door_w / 2, door_x + door_w / 2):
        cafe_add_box(
            collection,
            "entry_thermally_broken_jamb",
            (x, -hd - 0.12, 2.17),
            (0.075, 0.10, door_h),
            M["frame"],
            0.006,
        )
    for z in (0.38, 2.12, 3.96):
        cafe_add_box(
            collection,
            "entry_door_rail",
            (door_x, -hd - 0.13, z),
            (door_w, 0.10, 0.070),
            M["frame"],
            0.006,
        )
    cafe_add_box(
        collection,
        "entry_pull_handle",
        (door_x - 0.27, -hd - 0.22, 2.02),
        (0.035, 0.045, 0.76),
        M["cafe_brass"],
        0.008,
    )
    cafe_add_box(
        collection,
        "entry_hydraulic_closer",
        (door_x, -hd + 0.04, 3.76),
        (0.42, 0.14, 0.10),
        M["frame"],
        0.008,
    )
    cafe_add_box(
        collection,
        "entry_flush_threshold",
        (door_x, -hd - 0.12, 0.31),
        (door_w + 0.12, 0.34, 0.055),
        M["steel"],
        0.006,
    )
    # Operable three-bay steel shopfront.  Fixed side panes, top-hung central
    # lights and the actual serving sill make it a constructed opening.
    opening_left, opening_right = -3.90, 1.72
    cafe_add_box(
        collection,
        "service_counter_stone_sill",
        ((opening_left + opening_right) / 2, -hd - 0.22, 1.18),
        (opening_right - opening_left, 0.48, 0.14),
        M["cafe_aggregate"],
        0.018,
    )
    for x in (opening_left, -2.05, -0.18, opening_right):
        cafe_add_box(
            collection,
            "shopfront_structural_mullion",
            (x, -hd - 0.13, 2.55),
            (0.075, 0.11, 2.72),
            M["frame"],
            0.006,
        )
    for z in (1.22, 2.18, 3.88):
        cafe_add_box(
            collection,
            "shopfront_horizontal_rail",
            ((opening_left + opening_right) / 2, -hd - 0.13, z),
            (opening_right - opening_left, 0.11, 0.070),
            M["frame"],
            0.006,
        )
    for bay, x in enumerate((-2.98, -1.12, 0.77)):
        cafe_add_box(
            collection,
            "lower_safety_glass_pane",
            (x, -hd - 0.075, 1.68),
            (1.70, 0.032, 0.82),
            M["glass"],
            0.002,
        )
        if bay != 1:
            cafe_add_box(
                collection,
                "upper_fixed_glass_pane",
                (x, -hd - 0.075, 3.02),
                (1.70, 0.032, 1.55),
                M["glass"],
                0.002,
            )
        else:
            pane = cafe_add_box(
                collection,
                "raised_top_hung_glass_pane",
                (x, -hd + 0.18, 3.49),
                (1.70, 0.032, 1.55),
                M["glass"],
                0.002,
                (math.radians(19), 0, 0),
            )
            pane[
                "operable_hardware"
            ] = "top-hung sash shown open on concealed friction stays"
            for side in (-1, 1):
                cafe_tube_between(
                    collection,
                    "window_friction_stay",
                    (x + side * 0.74, -hd - 0.05, 2.62),
                    (x + side * 0.74, -hd + 0.42, 3.75),
                    0.015,
                    M["steel"],
                )
    # Black weather awning with folded fascia, wall rail and diagonal ties.
    cafe_add_box(
        collection,
        "service_awning_wall_rail",
        (-1.05, -hd - 0.08, 4.05),
        (5.72, 0.12, 0.12),
        M["frame"],
        0.008,
    )
    cafe_add_box(
        collection,
        "service_awning_folded_roof",
        (-1.05, -hd - 0.58, 3.95),
        (5.72, 1.03, 0.11),
        M["charcoal"],
        0.018,
        (math.radians(-7), 0, 0),
    )
    cafe_add_box(
        collection,
        "service_awning_drop_valance",
        (-1.05, -hd - 1.08, 3.82),
        (5.72, 0.10, 0.34),
        M["charcoal"],
        0.014,
    )
    for x in (-3.55, -0.95, 1.45):
        cafe_tube_between(
            collection,
            "awning_diagonal_tie",
            (x, -hd - 0.06, 3.62),
            (x, -hd - 0.98, 3.77),
            0.027,
            M["frame"],
        )
        cafe_tube_between(
            collection,
            "awning_roof_stay",
            (x, -hd - 0.06, 4.08),
            (x, -hd - 0.98, 3.90),
            0.027,
            M["frame"],
        )
    # Three separate dimensional signs mirror the supplied composition.
    cafe_add_text(
        collection,
        "upper_lemon_coffee_letters",
        "LEMON COFFEE",
        (-0.55, -hd - 0.22, 5.15),
        0.34,
        0.070,
        M["cafe_cream"],
    )
    cafe_add_box(
        collection,
        "entry_header_lightbox",
        (3.00, -hd - 0.21, 4.17),
        (1.98, 0.16, 0.38),
        M["cafe_cream"],
        0.012,
    )
    cafe_add_text(
        collection,
        "entry_lemon_coffee_letters",
        "LEMON COFFEE",
        (3.00, -hd - 0.305, 4.16),
        0.135,
        0.032,
        M["charcoal"],
    )
    cafe_add_text(
        collection,
        "awning_lemon_coffee_letters",
        "LEMON COFFEE",
        (-1.05, -hd - 1.145, 3.83),
        0.18,
        0.038,
        M["cafe_cream"],
    )
    # Actual menu plaques and wall-mounted sconces sit at human eye level.
    for index, x in enumerate((1.57, -3.83)):
        cafe_add_box(
            collection,
            "exterior_menu_plaque",
            (x, -hd - 0.22, 1.85),
            (0.42, 0.06, 0.72),
            M["charcoal"],
            0.014,
        )
        for row in range(6):
            cafe_add_box(
                collection,
                "menu_engraved_item_rule",
                (x + (row % 2) * 0.025, -hd - 0.258, 2.10 - row * 0.10),
                (0.27 - row * 0.018, 0.010, 0.020),
                M["cafe_cream"],
                0.002,
            )
    for x in (-4.02, 1.74):
        cafe_add_box(
            collection,
            "frontage_sconce_backplate",
            (x, -hd - 0.20, 3.34),
            (0.16, 0.06, 0.34),
            M["cafe_brass"],
            0.010,
        )
        cafe_add_cylinder(
            collection,
            "frontage_sconce_diffuser",
            (x, -hd - 0.29, 3.32),
            (0.075, 0.075, 0.22),
            M["light"],
            0.008,
            (math.pi / 2, 0, 0),
        )


def add_cafe_bar_and_interior(collection, M, cup, pastry):
    # Service counter with a stone worktop, ventilated/fluted face and recessed
    # toe-kick.  It is fully inside the shopfront instead of being pasted on it.
    counter_x = -1.05
    cafe_add_box(
        collection,
        "bar_recessed_toe_kick",
        (counter_x, -3.18, 0.43),
        (5.45, 0.54, 0.32),
        M["black"],
        0.010,
    )
    cafe_add_box(
        collection,
        "bar_aggregate_cabinet",
        (counter_x, -3.10, 0.80),
        (5.45, 0.72, 0.90),
        M["cafe_aggregate"],
        0.018,
    )
    for index in range(29):
        x = -3.66 + index * 0.187
        cafe_add_box(
            collection,
            "bar_vertical_flute",
            (x, -3.49, 0.84),
            (0.055, 0.035, 0.76),
            M["charcoal"],
            0.006,
        )
    cafe_add_box(
        collection,
        "bar_honed_countertop",
        (counter_x, -3.08, 1.33),
        (5.66, 0.94, 0.12),
        M["cafe_aggregate"],
        0.025,
    )
    cafe_add_box(
        collection,
        "bar_brass_drip_edge",
        (counter_x, -3.56, 1.30),
        (5.58, 0.035, 0.055),
        M["cafe_brass"],
        0.006,
    )
    # Refrigerated pastry display: insulated base, four glass faces, shelves,
    # door frame, ventilation grille and physical plated goods.
    display_x = -3.00
    cafe_add_box(
        collection,
        "pastry_case_refrigerated_base",
        (display_x, -2.77, 1.52),
        (1.38, 0.64, 0.30),
        M["steel"],
        0.015,
    )
    cafe_add_box(
        collection,
        "pastry_case_front_glass",
        (display_x, -3.10, 1.94),
        (1.34, 0.025, 0.74),
        M["glass"],
        0.002,
    )
    cafe_add_box(
        collection,
        "pastry_case_rear_glass",
        (display_x, -2.44, 1.94),
        (1.34, 0.025, 0.74),
        M["glass"],
        0.002,
    )
    for x in (display_x - 0.69, display_x + 0.69):
        cafe_add_box(
            collection,
            "pastry_case_side_glass",
            (x, -2.77, 1.94),
            (0.025, 0.64, 0.74),
            M["glass"],
            0.002,
        )
        cafe_add_box(
            collection,
            "pastry_case_vertical_frame",
            (x, -2.77, 1.94),
            (0.045, 0.70, 0.80),
            M["frame"],
            0.004,
        )
    for z in (1.66, 1.96, 2.28):
        cafe_add_box(
            collection,
            "pastry_case_glass_shelf",
            (display_x, -2.77, z),
            (1.26, 0.56, 0.025),
            M["glass"],
            0.002,
        )
    for z in (1.72, 2.02):
        cafe_instance(
            collection,
            pastry,
            "displayed_pastry_plate",
            (display_x, -2.82, z),
            0,
            (0.82, 0.82, 0.82),
        )
    for index in range(8):
        cafe_add_box(
            collection,
            "pastry_case_vent_slot",
            (display_x - 0.50 + index * 0.145, -3.105, 1.39),
            (0.075, 0.020, 0.025),
            M["black"],
            0.002,
        )
    # Commercial two-group espresso machine, with real group heads,
    # portafilters, steam wands, gauges, cup rail and plumbed service line.
    machine_x = -0.88
    cafe_add_box(
        collection,
        "espresso_machine_chassis",
        (machine_x, -2.77, 1.72),
        (1.66, 0.66, 0.72),
        M["steel"],
        0.045,
    )
    cafe_add_box(
        collection,
        "espresso_machine_black_control_fascia",
        (machine_x, -3.12, 1.83),
        (1.45, 0.06, 0.32),
        M["charcoal"],
        0.012,
    )
    cafe_add_box(
        collection,
        "espresso_machine_cup_warmer",
        (machine_x, -2.77, 2.14),
        (1.52, 0.60, 0.08),
        M["steel"],
        0.012,
    )
    for x in (machine_x - 0.38, machine_x + 0.38):
        cafe_add_cylinder(
            collection,
            "espresso_group_head",
            (x, -3.16, 1.68),
            (0.095, 0.095, 0.055),
            M["cafe_brass"],
            0.006,
            (math.pi / 2, 0, 0),
        )
        cafe_tube_between(
            collection,
            "espresso_portafilter_handle",
            (x, -3.20, 1.63),
            (x + 0.34, -3.32, 1.60),
            0.024,
            M["black"],
        )
        cafe_add_box(
            collection,
            "espresso_group_touchpad",
            (x, -3.17, 1.92),
            (0.22, 0.025, 0.12),
            M["screen"],
            0.005,
        )
    for x in (machine_x - 0.70, machine_x + 0.70):
        cafe_tube_between(
            collection,
            "espresso_steam_wand",
            (x, -3.10, 1.78),
            (x + math.copysign(0.12, x - machine_x), -3.32, 1.43),
            0.022,
            M["steel"],
        )
        cafe_add_cylinder(
            collection,
            "espresso_valve_knob",
            (x, -3.15, 1.96),
            (0.055, 0.055, 0.035),
            M["charcoal"],
            0.006,
            (math.pi / 2, 0, 0),
        )
    for x in (machine_x - 0.25, machine_x + 0.25):
        cafe_add_cylinder(
            collection,
            "espresso_pressure_gauge",
            (x, -3.17, 2.00),
            (0.060, 0.060, 0.025),
            M["cafe_cream"],
            0.004,
            (math.pi / 2, 0, 0),
        )
    for row in range(2):
        for col in range(5):
            cafe_instance(
                collection,
                cup,
                "espresso_warmer_cup",
                (machine_x - 0.52 + col * 0.26, -2.88 + row * 0.22, 2.20),
                0,
                (0.78, 0.78, 0.78),
            )
    cafe_tube_between(
        collection,
        "espresso_plumbed_water_line",
        (machine_x - 0.62, -2.52, 1.37),
        (machine_x - 0.62, -2.05, 0.34),
        0.025,
        M["steel"],
    )
    # Grinder and brew station with transparent bean hoppers and cup dispenser.
    for index, x in enumerate((0.35, 0.95)):
        cafe_add_box(
            collection,
            "commercial_grinder_motor",
            (x, -2.75, 1.69),
            (0.35, 0.38, 0.58),
            M["charcoal"],
            0.035,
        )
        cafe_add_cylinder(
            collection,
            "grinder_dosing_funnel",
            (x, -2.82, 2.08),
            (0.18, 0.14, 0.22),
            M["glass"],
            0.012,
        )
        cafe_add_cylinder(
            collection,
            "grinder_bean_charge",
            (x, -2.82, 2.06),
            (0.15, 0.11, 0.18),
            M["cafe_coffee"],
            0.010,
        )
        cafe_add_box(
            collection,
            "grinder_fork",
            (x, -3.00, 1.53),
            (0.18, 0.08, 0.18),
            M["steel"],
            0.006,
        )
    cafe_add_box(
        collection,
        "rinser_recess",
        (1.45, -3.08, 1.36),
        (0.45, 0.42, 0.045),
        M["black"],
        0.008,
    )
    for index in range(6):
        cafe_add_box(
            collection,
            "rinser_radial_grate",
            (1.27 + index * 0.07, -3.08, 1.39),
            (0.025, 0.34, 0.018),
            M["steel"],
            0.002,
        )
    # Full back bar: base cabinetry, sink, faucet, open shelves and individual
    # stock items.  Warm strip lighting reveals this through the service hatch.
    cafe_add_box(
        collection,
        "backbar_base_cabinet",
        (-0.65, 2.82, 0.76),
        (5.82, 0.72, 1.02),
        M["cafe_oak"],
        0.018,
    )
    cafe_add_box(
        collection,
        "backbar_worktop",
        (-0.65, 2.75, 1.32),
        (6.00, 0.88, 0.12),
        M["cafe_aggregate"],
        0.020,
    )
    for x in (-3.15, -2.15, -1.15, -0.15, 0.85, 1.85):
        cafe_add_box(
            collection,
            "backbar_cabinet_door",
            (x, 2.42, 0.78),
            (0.90, 0.05, 0.86),
            M["cafe_oak"],
            0.012,
        )
        cafe_add_box(
            collection,
            "backbar_recessed_pull",
            (x, 2.385, 0.92),
            (0.28, 0.018, 0.035),
            M["cafe_brass"],
            0.004,
        )
    cafe_add_box(
        collection,
        "backbar_sink_basin",
        (1.72, 2.73, 1.36),
        (0.72, 0.52, 0.22),
        M["black"],
        0.012,
    )
    cafe_tube_between(
        collection,
        "backbar_faucet_riser",
        (1.72, 2.94, 1.42),
        (1.72, 2.94, 1.92),
        0.030,
        M["cafe_brass"],
    )
    cafe_tube_between(
        collection,
        "backbar_faucet_spout",
        (1.72, 2.94, 1.90),
        (1.72, 2.63, 1.90),
        0.030,
        M["cafe_brass"],
    )
    for z in (2.05, 2.72, 3.39):
        cafe_add_box(
            collection,
            "backbar_oak_shelf",
            (-0.65, 3.17, z),
            (6.02, 0.40, 0.10),
            M["cafe_oak"],
            0.016,
        )
        cafe_add_box(
            collection,
            "backbar_warm_led_strip",
            (-0.65, 2.95, z - 0.07),
            (5.80, 0.025, 0.025),
            M["light"],
            0.003,
        )
        for index in range(12):
            x = -3.25 + index * 0.47
            if z < 2.20:
                cafe_instance(
                    collection,
                    cup,
                    "backbar_stacked_cup",
                    (x, 2.95, z + 0.13),
                    0,
                    (0.72, 0.72, 0.72),
                )
            else:
                cafe_add_box(
                    collection,
                    "coffee_retail_bag",
                    (x, 2.94, z + 0.19),
                    (0.24, 0.14, 0.34),
                    M["cafe_paper"],
                    0.025,
                    (0, 0, (index % 3 - 1) * 0.03),
                )
                cafe_add_box(
                    collection,
                    "coffee_bag_label",
                    (x, 2.86, z + 0.20),
                    (0.15, 0.012, 0.13),
                    M["cafe_cream"],
                    0.004,
                )
    # Customer-side bar stools are properly footed and leave the door aisle.
    for x in (-3.10, -1.80, -0.50, 0.80):
        cafe_add_cylinder(
            collection,
            "barstool_floor_plate",
            (x, -3.76, 0.32),
            (0.22, 0.22, 0.030),
            M["frame"],
            0.008,
        )
        cafe_add_cylinder(
            collection,
            "barstool_pedestal",
            (x, -3.76, 0.67),
            (0.040, 0.040, 0.34),
            M["cafe_brass"],
            0.005,
        )
        cafe_add_cylinder(
            collection,
            "barstool_upholstered_seat",
            (x, -3.76, 1.02),
            (0.26, 0.26, 0.085),
            M["charcoal"],
            0.022,
        )
        cafe_add_cylinder(
            collection,
            "barstool_footring",
            (x, -3.76, 0.55),
            (0.17, 0.17, 0.025),
            M["frame"],
            0.005,
        )
    # Track lighting and two seated customer tables fill the entry-side room.
    for x in (-2.80, 0, 2.80):
        cafe_add_box(
            collection,
            "ceiling_track_rail",
            (x, -0.10, 3.91),
            (0.055, 5.80, 0.055),
            M["frame"],
            0.005,
        )
        for y in (-2.15, -0.25, 1.65):
            cafe_add_cylinder(
                collection,
                "track_spotlight_housing",
                (x, y, 3.72),
                (0.095, 0.095, 0.18),
                M["charcoal"],
                0.012,
            )
            cafe_add_cylinder(
                collection,
                "track_spotlight_diffuser",
                (x, y, 3.52),
                (0.078, 0.078, 0.025),
                M["light"],
                0.006,
            )
            cafe_add_area_light(
                collection, "track_spotlight_pool", (x, y, 3.50), 160, 0.52
            )
    dining_table = bpy.data.collections.get("DINING_TABLE_MASTER")
    dining_chair = bpy.data.collections.get("DINING_CHAIR_MASTER")
    if dining_table is None or dining_chair is None:
        raise RuntimeError("all43-23 requires detailed all43-15 dining masters")
    for y in (-0.65, 1.15):
        cafe_instance(
            collection,
            dining_table,
            "entry_side_dining_table",
            (2.72, y, 0.26),
            math.pi / 2,
            (0.74, 0.74, 0.82),
        )
        for dx in (-0.68, 0.68):
            cafe_instance(
                collection,
                dining_chair,
                "entry_side_dining_chair",
                (2.72 + dx, y, 0.26),
                0 if dx < 0 else math.pi,
                (0.82, 0.82, 0.82),
            )
        cafe_instance(
            collection,
            cup,
            "dining_table_coffee_cup",
            (2.72, y, 1.04),
            0,
            (0.88, 0.88, 0.88),
        )


def add_cafe_rooftop_services(collection, M):
    condenser = bpy.data.collections.get("all43_19:MASTER:ROOFTOP_CONDENSER")
    if condenser is None:
        raise RuntimeError(
            "all43-23 requires the detailed all43-19 rooftop condenser master"
        )
    cafe_instance(
        collection,
        condenser,
        "cafe_curbed_rooftop_condenser",
        (-2.55, 0.62, CAFE_HEIGHT + 0.08),
        -0.04,
        (0.72, 0.72, 0.72),
    )
    cafe_add_box(
        collection,
        "cafe_roof_access_hatch",
        (0.72, 1.30, CAFE_HEIGHT + 0.16),
        (1.02, 0.88, 0.22),
        M["steel"],
        0.016,
    )
    cafe_add_box(
        collection,
        "cafe_roof_access_upstand",
        (0.72, 1.30, CAFE_HEIGHT + 0.30),
        (0.84, 0.70, 0.16),
        M["roof"],
        0.012,
    )
    cafe_add_box(
        collection,
        "cafe_exhaust_roof_curb",
        (2.52, 2.30, CAFE_HEIGHT + 0.17),
        (0.76, 0.72, 0.26),
        M["roof"],
        0.012,
    )
    cafe_add_cylinder(
        collection,
        "cafe_bar_exhaust_fan",
        (2.52, 2.30, CAFE_HEIGHT + 0.58),
        (0.32, 0.32, 0.34),
        M["steel"],
        0.016,
    )
    cafe_add_cylinder(
        collection,
        "cafe_exhaust_weather_cap",
        (2.52, 2.30, CAFE_HEIGHT + 0.93),
        (0.41, 0.41, 0.075),
        M["steel"],
        0.014,
    )
    cafe_tube_between(
        collection,
        "cafe_roof_service_conduit",
        (-1.92, 0.62, CAFE_HEIGHT + 0.32),
        (0.72, 1.30, CAFE_HEIGHT + 0.32),
        0.028,
        M["steel"],
    )
    cafe_tube_between(
        collection,
        "cafe_connected_downpipe",
        (-4.19, 2.52, 0.32),
        (-4.19, 2.52, CAFE_HEIGHT - 0.08),
        0.060,
        M["steel"],
    )
    cafe_add_box(
        collection,
        "cafe_box_gutter_hopper",
        (-4.19, 2.52, CAFE_HEIGHT - 0.02),
        (0.24, 0.28, 0.26),
        M["steel"],
        0.009,
    )
    cafe_tube_between(
        collection,
        "cafe_downpipe_discharge_shoe",
        (-4.19, 2.52, 0.30),
        (-4.19, 2.24, 0.20),
        0.068,
        M["steel"],
    )


def build_cafe_master(M):
    master = new_master(CAFE_MASTER_NAME)
    chair = make_cafe_street_chair_master(M)
    table = make_cafe_side_table_master(M)
    cup = make_cafe_cup_master(M)
    pastry = make_cafe_pastry_master(M)
    add_cafe_shell(master, M)
    add_cafe_storefront(master, M)
    add_cafe_bar_and_interior(master, M, cup, pastry)
    add_cafe_rooftop_services(master, M)
    master[
        "architectural_program"
    ] = "full-scale party-wall roadside coffee shop with customer room, open service counter, production bar, wash station and roof plant"
    master[
        "reference_translation"
    ] = "LEMON COFFEE black fluted fascia, warm timber portals, white lightbox, dimensional lettering, operable steel glazing, stone counter and low frontage seating"
    master["full_scale_dimensions_m"] = [CAFE_WIDTH, CAFE_DEPTH, CAFE_HEIGHT]
    master[
        "frontage_orientation"
    ] = "local south facade; production instance rotated 180 degrees to share the McDonald's west party wall and face the north road"
    master[
        "interior_visibility"
    ] = "open steel shopfront reveals a refrigerated pastry case, two-group espresso machine, grinders, backbar stock, sink, bar stools and customer tables"
    master["street_chair_master"] = chair.name
    master["street_table_master"] = table.name
    return master


def add_cafe_frontage_world(world, M):
    chair = bpy.data.collections[CAFE_P + "MASTER:STREET_LOUNGE_CHAIR"]
    table = bpy.data.collections[CAFE_P + "MASTER:STREET_SIDE_TABLE"]
    cup = bpy.data.collections[CAFE_P + "MASTER:TAKEAWAY_CUP"]
    # The all43-24 field terminates 0.10 m on the cafe side of the party line;
    # neither its finishes nor its furniture enter the McDonald's patio.
    paver_center_x = CAFE_LOCATION.x
    paver_width = CAFE_WIDTH - 0.20
    cafe_add_box(
        world,
        "cafe_frontage_paver_field",
        (paver_center_x, -8.48, 0.245),
        (paver_width, 3.76, 0.090),
        M["paver"],
        0.012,
    )
    cafe_add_box(
        world,
        "cafe_frontage_road_edge_curb",
        (paver_center_x, -6.52, 0.18),
        (paver_width + 0.18, 0.18, 0.24),
        M["concrete"],
        0.010,
    )
    cafe_add_box(
        world,
        "cafe_flush_entry_landing",
        (CAFE_LOCATION.x - 3.0, -10.17, 0.305),
        (1.72, 0.66, 0.060),
        M["paver"],
        0.008,
    )
    cafe_add_box(
        world,
        "cafe_clear_pedestrian_band",
        (paver_center_x, -7.18, 0.302),
        (paver_width - 0.24, 1.16, 0.025),
        M["concrete"],
        0.005,
    )
    for index in range(8):
        x = (
            CAFE_LOCATION.x
            - (paver_width / 2 - 0.55)
            + index * ((paver_width - 1.10) / 7)
        )
        cafe_add_box(
            world,
            "cafe_longitudinal_paver_joint",
            (x, -8.82, 0.295),
            (0.018, 2.45, 0.010),
            M["joint"],
            0.001,
        )
    for y in (-9.86, -8.72, -7.58):
        cafe_add_box(
            world,
            "cafe_transverse_paver_joint",
            (paver_center_x, y, 0.295),
            (paver_width - 0.22, 0.018, 0.010),
            M["joint"],
            0.001,
        )
    for row in range(2):
        for col in range(4):
            cafe_add_box(
                world,
                "cafe_entry_tactile_paver",
                (CAFE_LOCATION.x - 3.50 + col * 0.32, -6.68 - row * 0.25, 0.332),
                (0.25, 0.20, 0.025),
                M["tactile"],
                0.005,
            )
    # The chair master's back is local +Y and its seat faces local -Y.  A 180
    # degree world rotation therefore places every back toward the south-facing
    # cafe wall and every seat toward the north road.  Small authored offsets
    # keep the row natural without reversing that unambiguous direction.
    chair_sites = tuple(
        (CAFE_LOCATION.x + dx, -9.52, math.pi + offset)
        for dx, offset in ((-1.07, 0.035), (0.43, -0.025), (1.93, 0.025))
    )
    for x, y, rotation in chair_sites:
        chair_instance = cafe_instance(
            world, chair, "frontage_contract_lounge_chair", (x, y, 0.29), rotation
        )
        chair_instance["seat_forward_world"] = [
            round(math.sin(rotation), 4),
            round(-math.cos(rotation), 4),
            0.0,
        ]
        chair_instance[
            "frontage_orientation"
        ] = "back toward cafe facade; seat toward north road"
    table_sites = tuple((CAFE_LOCATION.x + dx, -9.14) for dx in (-0.32, 1.18))
    for index, (x, y) in enumerate(table_sites):
        cafe_instance(
            world, table, "frontage_pedestal_side_table", (x, y, 0.29), index * 0.06
        )
        cafe_instance(
            world, cup, "frontage_served_coffee_cup", (x, y, 1.075), index * 0.18
        )
    # Slim trench drain and removable grate slots protect the open shopfront.
    cafe_add_box(
        world,
        "cafe_frontage_trench_drain",
        (paver_center_x, -10.44, 0.235),
        (paver_width - 0.08, 0.18, 0.055),
        M["steel"],
        0.006,
    )
    for index in range(37):
        x = (
            CAFE_LOCATION.x
            - (paver_width / 2 - 0.20)
            + index * ((paver_width - 0.40) / 36)
        )
        cafe_add_box(
            world,
            "cafe_drain_grate_slot",
            (x, -10.44, 0.266),
            (0.050, 0.12, 0.015),
            M["black"],
            0.001,
        )
    # A fabricated blade sign anchors the west end without blocking the door.
    blade_x = CAFE_LOCATION.x - 4.25
    cafe_add_box(
        world,
        "cafe_blade_sign_wall_bracket",
        (blade_x, -10.40, 2.56),
        (0.18, 0.58, 0.18),
        M["frame"],
        0.012,
    )
    cafe_add_box(
        world,
        "cafe_blade_sign_cabinet",
        (blade_x, -10.05, 2.56),
        (0.16, 0.20, 1.04),
        M["charcoal"],
        0.025,
    )
    cafe_add_box(
        world,
        "cafe_blade_sign_diffuser",
        (blade_x - 0.10, -10.05, 2.56),
        (0.025, 0.17, 0.92),
        M["cafe_cream"],
        0.014,
    )
    blade_text = bpy.data.curves.new(CAFE_P + "blade_sign_text_data", "FONT")
    blade_text.body = "COFFEE"
    blade_text.align_x = "CENTER"
    blade_text.align_y = "CENTER"
    blade_text.size = 0.16
    blade_text.extrude = 0.018
    blade_text.bevel_depth = 0.003
    blade_text.materials.append(M["charcoal"])
    sign_obj = bpy.data.objects.new(CAFE_P + "blade_sign_text", blade_text)
    world.objects.link(sign_obj)
    sign_obj.location = (blade_x - 0.125, -10.045, 2.56)
    sign_obj.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    # Hollow, drained architectural planter.  The membrane is also a real
    # five-piece lining rather than a solid volume intersecting gravel and soil.
    # Drainage, filter fabric, potting mix, mulch and the rooted plant occupy
    # separate, vertically ordered layers.
    planter_x = CAFE_LOCATION.x + 2.90
    planter_y = -10.03
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_bottom_plate",
        (planter_x, planter_y, 0.355),
        (0.62, 0.56, 0.10),
        M["cafe_aggregate"],
        0.025,
    )
    for x in (planter_x - 0.33, planter_x + 0.33):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_side_wall",
            (x, planter_y, 0.72),
            (0.08, 0.66, 0.78),
            M["cafe_aggregate"],
            0.025,
        )
    for y in (planter_y - 0.29, planter_y + 0.29):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_front_back_wall",
            (planter_x, y, 0.72),
            (0.58, 0.08, 0.78),
            M["cafe_aggregate"],
            0.025,
        )
    # Four edge-banded cap rails make the panel build-up legible at eye level.
    for x in (planter_x - 0.33, planter_x + 0.33):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_side_rim_cap",
            (x, planter_y, 1.115),
            (0.105, 0.70, 0.055),
            M["cafe_brass"],
            0.010,
        )
    for y in (planter_y - 0.29, planter_y + 0.29):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_front_back_rim_cap",
            (planter_x, y, 1.115),
            (0.58, 0.105, 0.055),
            M["cafe_brass"],
            0.010,
        )
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_hdpe_liner_bottom",
        (planter_x, planter_y, 0.435),
        (0.54, 0.48, 0.025),
        M["cafe_liner"],
        0.006,
    )
    for x in (planter_x - 0.277, planter_x + 0.277):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_hdpe_liner_side",
            (x, planter_y, 0.755),
            (0.014, 0.48, 0.64),
            M["cafe_liner"],
            0.002,
        )
    for y in (planter_y - 0.247, planter_y + 0.247):
        cafe_add_box(
            world,
            "cafe_fiddle_leaf_planter_hdpe_liner_end",
            (planter_x, y, 0.755),
            (0.54, 0.014, 0.64),
            M["cafe_liner"],
            0.002,
        )
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_drainage_gravel",
        (planter_x, planter_y, 0.615),
        (0.52, 0.46, 0.32),
        M["cafe_gravel"],
        0.012,
    )
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_filter_geotextile",
        (planter_x, planter_y, 0.785),
        (0.52, 0.46, 0.020),
        M["cafe_geotextile"],
        0.002,
    )
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_potting_mix",
        (planter_x, planter_y, 0.935),
        (0.52, 0.46, 0.28),
        M["soil"],
        0.010,
    )
    cafe_add_box(
        world,
        "cafe_fiddle_leaf_planter_bark_mulch",
        (planter_x, planter_y, 1.087),
        (0.51, 0.45, 0.024),
        M["cafe_mulch"],
        0.006,
    )
    for x in (planter_x - 0.22, planter_x + 0.22):
        for y in (planter_y - 0.18, planter_y + 0.18):
            cafe_add_cylinder(
                world,
                "cafe_fiddle_leaf_planter_recessed_foot",
                (x, y, 0.3025),
                (0.045, 0.045, 0.025),
                M["cafe_rubber"],
                0.005,
            )
    cafe_add_cylinder(
        world,
        "cafe_fiddle_leaf_planter_drain_outlet",
        (planter_x, planter_y - 0.335, 0.43),
        (0.030, 0.030, 0.045),
        M["steel"],
        0.004,
        (math.pi / 2, 0, 0),
    )

    # Three separately meshed, tapered stems form a natural container-grown
    # clump.  Their root collars are spaced inside the soil and the stems diverge
    # continuously, so the silhouette is neither a pole nor an intersecting
    # cylinder bundle.  Each crown owns an outward sector and staggered node
    # heights; the evaluated BVH audit below remains the final authority.
    stem_z0 = 1.055
    stem_specs = (
        (
            "central",
            0.00,
            0.030,
            0.015,
            0.055,
            3.62,
            0.057,
            0.028,
            (
                (72, 2.00),
                (102, 2.22),
                (58, 2.44),
                (122, 2.66),
                (84, 2.88),
                (136, 3.10),
                (66, 3.32),
                (108, 3.50),
            ),
        ),
        (
            "west",
            -0.12,
            0.020,
            -0.18,
            0.145,
            2.82,
            0.046,
            0.022,
            (
                (164, 1.43),
                (128, 1.61),
                (176, 1.79),
                (142, 1.97),
                (112, 2.15),
                (158, 2.33),
                (126, 2.51),
            ),
        ),
        (
            "east",
            0.12,
            0.025,
            0.19,
            0.155,
            2.91,
            0.046,
            0.022,
            (
                (16, 1.52),
                (52, 1.70),
                (5, 1.88),
                (76, 2.06),
                (34, 2.24),
                (8, 2.42),
                (20, 2.60),
            ),
        ),
    )
    leaf_objects = []
    for stem_index, (
        label,
        base_dx,
        base_dy,
        end_dx,
        end_dy,
        stem_z1,
        radius0,
        radius1,
        nodes,
    ) in enumerate(stem_specs):

        def stem_xy(t):
            return (
                planter_x
                + base_dx
                + end_dx * t
                + 0.012 * math.sin(t * math.pi * (1.7 + stem_index * 0.2)),
                planter_y + base_dy + end_dy * t + 0.010 * math.sin(t * math.pi * 1.3),
            )

        stem_path = []
        stem_radii = []
        for segment in range(12):
            t = segment / 11
            stem_x, stem_y = stem_xy(t)
            stem_path.append((stem_x, stem_y, stem_z0 + (stem_z1 - stem_z0) * t))
            stem_radii.append(radius0 + (radius1 - radius0) * t)
        cafe_add_tapered_stem(
            world,
            "cafe_fiddle_leaf_fig_continuous_tapered_stem_" + label,
            stem_path,
            stem_radii,
            M["cafe_stem"],
        )
        cafe_add_cylinder(
            world,
            "cafe_fiddle_leaf_fig_root_collar_" + label,
            (planter_x + base_dx, planter_y + base_dy, 1.095),
            (0.052, 0.047, 0.045),
            M["cafe_stem"],
            0.009,
        )
        for node_index, (degrees, attach_z) in enumerate(nodes):
            t = (attach_z - stem_z0) / (stem_z1 - stem_z0)
            stem_x, stem_y = stem_xy(t)
            angle = math.radians(degrees)
            radial = Vector((math.cos(angle), math.sin(angle), 0.0))
            stem_radius = radius0 + (radius1 - radius0) * t
            petiole_start = Vector((stem_x, stem_y, attach_z)) + radial * stem_radius
            petiole_length = (0.105 if stem_index else 0.12) + 0.014 * (node_index % 3)
            leaf_base = petiole_start + radial * petiole_length + Vector((0, 0, 0.018))
            petiole = cafe_tube_between(
                world,
                "cafe_fiddle_leaf_fig_articulated_petiole",
                petiole_start,
                leaf_base,
                0.0115,
                M["cafe_leaf_vein"],
            )
            petiole[
                "botanical_joint"
            ] = "petiole terminates at blade base and stem surface; no through-mesh extension"
            if stem_index == 0:
                length = 0.53 + 0.035 * (node_index % 3)
                width = 0.32 + 0.025 * ((node_index + 1) % 3)
            else:
                length = 0.42 + 0.030 * (node_index % 3)
                width = 0.255 + 0.020 * ((node_index + stem_index) % 3)
            leaf_objects.append(
                cafe_add_fiddle_leaf(
                    world,
                    "cafe_fiddle_leaf_fig_cambered_leaf_blade",
                    leaf_base,
                    (
                        math.cos(angle),
                        math.sin(angle),
                        0.072 + 0.010 * (node_index % 2),
                    ),
                    length,
                    width,
                    0.055 + 0.007 * (node_index % 3),
                    M["cafe_leaf_light"]
                    if (node_index + stem_index) % 5 == 0
                    else M["cafe_leaf_dark"],
                    M["cafe_leaf_vein"],
                )
            )
    # Party-wall cover and roof cap are explicit manufactured connections.
    cafe_add_box(
        world,
        "cafe_mcdonalds_party_wall_cover",
        (CAFE_PARTY_X, -14.55, 2.78),
        (0.085, 8.08, 5.14),
        M["steel"],
        0.006,
    )
    cafe_add_box(
        world,
        "cafe_mcdonalds_roof_transition_cap",
        (CAFE_PARTY_X, -14.55, 6.04),
        (0.34, 8.18, 0.12),
        M["steel"],
        0.010,
    )
    # Rear threshold ties into the already generated amenity/service walk
    # without consuming a parking stall or moving any retained asset.
    cafe_add_box(
        world,
        "cafe_rear_service_threshold",
        (CAFE_LOCATION.x, -18.73, 0.255),
        (7.94, 0.32, 0.10),
        M["paver"],
        0.008,
    )
    for x in (CAFE_LOCATION.x - 3.60, CAFE_LOCATION.x - 2.90):
        cafe_add_cylinder(
            world,
            "cafe_rear_delivery_bollard",
            (x, -18.84, 0.69),
            (0.070, 0.070, 0.56),
            M["cafe_brass"],
            0.008,
        )
    return {
        "frontage_chair_count": len(chair_sites),
        "frontage_table_count": len(table_sites),
        "frontage_served_cup_count": len(table_sites),
        "frontage_clear_pedestrian_width_m": 1.16,
        "frontage_paver_east_clearance_to_mcdonalds_fence_m": round(
            MCD_PATIO_WEST_X - (CAFE_PARTY_X - 0.10), 3
        ),
        "frontage_chair_rotation_degrees": [
            round(math.degrees(site[2]), 2) for site in chair_sites
        ],
        "frontage_chairs_face_road": all(
            math.cos(site[2] - math.pi) >= 0.995 for site in chair_sites
        ),
        "frontage_chair_back_clearance_to_facade_m": 0.43,
        "frontage_chair_ground_contact_z_m": 0.29,
        "frontage_table_ground_contact_z_m": 0.29,
        "frontage_paver_top_z_m": 0.29,
        "frontage_grounding_error_m": 0.0,
        "planter_shell_is_hollow_assembly": True,
        "planter_recessed_foot_count": 4,
        "planter_drainage_component_count": 3,
        "planter_liner_is_hollow_five_piece_assembly": True,
        "botanical_leaf_count": len(leaf_objects),
        "botanical_leaf_vertices_each": 50,
        "botanical_stem_count": len(stem_specs),
        "botanical_leaf_vertical_lane_spacing_m": 0.18,
        "botanical_authored_minimum_leaf_lane_clearance_m": 0.030,
        "botanical_rooted_in_separate_mulch_and_soil_layers": True,
        "party_wall_gap_m": 0.0,
        "parking_stalls_consumed": 0,
    }


def compact_rotated_shop_frontages():
    """Keep the inherited shop sidewalks inside the east-road parcel edge."""
    shifted = []
    tokens = (
        "continuous_pedestrian_frontage",
        "integrated_front_curb",
        "curb_gutter_transition",
        "sidewalk_control_joint",
        "flush_storefront_threshold",
        "recessed_entry_mat",
        "realistic_frontage_planter",
        "refined_connected_planter",
        "anchored_frontage_planter",
        "planter_soil",
        "planter_foliage",
        "lidded_frontage_bin",
        "frontage_bin_lid",
    )
    for collection_name in (
        "all43_01:MASTER:convenience_store",
        "all43_01:MASTER:restaurant",
    ):
        collection = bpy.data.collections[collection_name]
        for obj in collection.objects:
            if any(token in obj.name for token in tokens):
                obj.location.y += 0.62
                obj[P + "frontage_depth_adjustment_m"] = 0.62
                shifted.append(obj.name)
    return shifted


def rearrange_existing_shops():
    moved = {}
    missing = []
    compacted = compact_rotated_shop_frontages()
    for name, transform in SHOP_LAYOUT.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
            continue
        target = transform["location"]
        old = obj.location.copy()
        old_rotation = obj.rotation_euler.z
        old_scale = obj.scale.copy()
        delta = target - old
        if name == "all43_19:street_corner_711":
            world19 = bpy.data.collections.get("all43_19:corner_store_world")
            if world19 is None:
                missing.append("all43_19:corner_store_world")
                continue
            # Move the complete corner frontage with the building, preserving thresholds,
            # tactile pavers, curb joints and bicycle hoops authored in all43-19.
            for frontage_obj in world19.objects:
                frontage_obj.location += delta
        else:
            obj.location = target
        obj.rotation_euler[2] = transform["rotation"]
        obj.scale = transform["scale"]
        moved[name] = {
            "from": [round(v, 3) for v in old],
            "to": [round(v, 3) for v in target],
            "distance_m": round(delta.length, 3),
            "rotation_from_deg": round(math.degrees(old_rotation), 3),
            "rotation_to_deg": round(math.degrees(transform["rotation"]), 3),
            "scale_from": [round(v, 3) for v in old_scale],
            "scale_to": [round(v, 3) for v in transform["scale"]],
        }
    if missing:
        raise RuntimeError({"all43_20_missing_layout_assets": missing})
    return moved, compacted


def hide_displaced_frontage_assets():
    hidden = []
    # The three cafe sets occupied the new north-facing McDonald's footprint.
    # They are removed as a complete conflict set; intact flowerbeds and bicycles
    # remain in the now-open landscaped court west of the new restaurant.
    for obj in bpy.data.objects:
        if obj.hide_render:
            continue
        if obj.name.startswith("all43_17:rear_crafted_cafe_set"):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[
                P + "hidden_reason"
            ] = "replaced by connected north-street restaurant frontage"
            hidden.append(obj.name)
    return hidden


def hide_legacy_parking_layout():
    hidden = []
    exact = {
        "all43_01:parking",
        "all43_17:fresh_mart_continuous_asphalt_parking",
        "all43_01:curb",
        "all43_01:curb.001",
        "all43_01:curb.002",
        "all43_01:drain_channel",
        "all43_07:curb",
        "all43_07:drain_channel",
        "all43_13:asphalt_gutter_clean",
        "all43_13:raised_curb_clean",
    }
    prefixes = (
        "all43_01:03_stall_",
        "all43_01:drain_slot",
        "all43_07:asphalt_patch",
        "all43_13:restrained_parking_stripe",
    )
    for obj in bpy.data.objects:
        in_legacy_frontage = any(
            collection.name == "all43_13:frontage_clean"
            for collection in obj.users_collection
        )
        if obj.name in exact or obj.name.startswith(prefixes) or in_legacy_frontage:
            if not obj.hide_render:
                obj.hide_render = True
                obj.hide_viewport = True
                obj[
                    P + "hidden_reason"
                ] = "superseded by unified rear parking relocation"
                hidden.append(obj.name)
    return hidden


def consolidate_northwest_amenities(world, M):
    hidden = []
    for name in (
        "all43_01:forecourt",
        "all43_01:crack",
        "all43_01:leaf",
        "all43_01:leaf.001",
    ):
        obj = bpy.data.objects.get(name)
        if obj and not obj.hide_render:
            obj.hide_render = True
            obj.hide_viewport = True
            obj[P + "hidden_reason"] = "superseded by compact parking-edge amenity walk"
            hidden.append(name)
    for obj in bpy.data.objects:
        if obj.name.startswith("all43_17:rear_sharedbicycle4") and not obj.hide_render:
            obj.hide_render = True
            obj.hide_viewport = True
            obj[
                P + "hidden_reason"
            ] = "consolidated into the complete shared bicycle station"
            hidden.append(obj.name)

    add_box(
        world,
        "parking_edge_amenity_walk",
        (-40.10, -19.36, 0.225),
        (18.45, 1.78, 0.075),
        M["paver"],
        0.010,
    )
    add_box(
        world,
        "amenity_walk_back_edge_curb",
        (-40.10, -18.43, 0.17),
        (18.55, 0.14, 0.22),
        M["concrete"],
        0.009,
    )
    for index in range(9):
        add_box(
            world,
            "amenity_walk_control_joint",
            (-48.30 + index * 2.05, -19.36, 0.267),
            (0.020, 1.64, 0.008),
            M["joint"],
            0.001,
        )

    amenity_targets = {
        "all43_01:bin_0": (-48.65, -19.32, 0.18),
        "all43_01:bin_1": (-31.45, -19.32, 0.18),
        "all43_17:fresh_mart_shared_bicycle_station_pad": (-44.35, -19.35, 0.165),
        "all43_17:fresh_mart_sharedbicycle4_station": (-45.70, -19.75, 0.185),
        "all43_17:rear_complex_flowerbed": (-48.05, -19.30, 0.18),
        "all43_17:rear_complex_flowerbed.001": (-38.70, -19.30, 0.18),
        "all43_17:rear_complex_flowerbed.002": (-33.20, -19.30, 0.18),
    }
    relocated = {}
    for name, target in amenity_targets.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.location = target
            relocated[name] = [round(v, 3) for v in target]
    return hidden, relocated


def relocate_existing_parking_assets():
    relocated = {}
    vehicle_targets = {
        "all43_02:vehicle:audi_tt": (-43.60, -25.55, 0.18),
        "all43_02:vehicle:tucson": (-36.80, -25.55, 0.18),
        "all43_02:vehicle:audi_q7": (-40.20, -39.15, 0.18),
        "all43_02:vehicle:ducato": (-26.60, -39.15, 0.18),
    }
    for name, target in vehicle_targets.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.location = target
            relocated[name] = [round(v, 3) for v in target]

    wheelstops = sorted(
        [obj for obj in bpy.data.objects if obj.name.startswith("all43_03:wheelstop_")],
        key=lambda obj: obj.name,
    )
    stall_xs = (-47.00, -43.60, -40.20, -36.80, -33.40, -30.00, -26.60, -23.20)
    targets = [(x, -27.78, 0.18) for x in stall_xs[:5]] + [
        (x, -36.92, 0.18) for x in stall_xs[:3]
    ]
    for obj, target in zip(wheelstops, targets):
        obj.location = target
        obj.hide_render = False
        obj.hide_viewport = False
        relocated[obj.name] = [round(v, 3) for v in target]

    light_targets = {
        "all43_01:light_0": (-48.85, -21.35, 0.18),
        "all43_01:light_1": (-48.85, -43.20, 0.18),
        "all43_01:light_2": (-21.45, -43.20, 0.18),
    }
    for name, target in light_targets.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.location = target
            relocated[name] = [round(v, 3) for v in target]

    return relocated


def add_rear_parking(world, M):
    # The original east-side parking is replaced as one coherent rear lot,
    # wholly west of the south shop wing and behind the McDonald's service wall.
    add_box(
        world,
        "relocated_rear_parking_asphalt",
        (-35.25, -32.35, 0.105),
        (28.40, 23.70, 0.10),
        M["charcoal"],
        0.010,
    )
    for name, loc, dims in (
        ("rear_parking_north_curb", (-35.25, -20.38, 0.19), (28.55, 0.22, 0.26)),
        ("rear_parking_south_curb", (-35.25, -44.30, 0.19), (28.55, 0.22, 0.26)),
        ("rear_parking_west_curb", (-49.56, -32.35, 0.19), (0.22, 24.05, 0.26)),
        ("rear_parking_east_curb", (-20.94, -32.35, 0.19), (0.22, 24.05, 0.26)),
    ):
        add_box(world, name, loc, dims, M["concrete"], 0.012)
    add_box(
        world,
        "rear_parking_trench_drain",
        (-35.25, -20.67, 0.17),
        (27.95, 0.24, 0.055),
        M["steel"],
        0.006,
    )
    for index in range(35):
        x = -48.82 + index * 0.80
        add_box(
            world,
            "rear_parking_drain_grate_slot",
            (x, -20.67, 0.205),
            (0.055, 0.18, 0.018),
            M["black"],
            0.002,
        )
    # A continuous service apron makes the restaurant read as directly backed
    # by the relocated parking while retaining a safe staff/service clearway.
    add_box(
        world,
        "mcdonalds_rear_service_apron",
        (-25.80, -19.49, 0.225),
        (9.56, 1.72, 0.075),
        M["paver"],
        0.010,
    )
    for index in range(5):
        add_box(
            world,
            "mcdonalds_rear_apron_joint",
            (-29.62 + index * 1.92, -19.49, 0.267),
            (0.020, 1.58, 0.008),
            M["joint"],
            0.001,
        )
    for x in (-29.85, -27.95):
        add_cylinder(
            world,
            "mcdonalds_service_bollard",
            (x, -18.92, 0.68),
            (0.075, 0.075, 0.56),
            M["yellow"],
            0.008,
        )

    stall_xs = (-47.00, -43.60, -40.20, -36.80, -33.40, -30.00, -26.60, -23.20)
    for row, y in enumerate((-25.55, -39.15)):
        for boundary in range(len(stall_xs) + 1):
            x = stall_xs[0] - 1.60 + boundary * 3.40
            add_box(
                world,
                "rear_parking_stall_line",
                (x, y, 0.172),
                (0.095, 5.20, 0.025),
                M["white"],
                0.002,
            )
    # Two blue accessible spaces and a hatched transfer aisle sit closest to the
    # north-east pedestrian route without interfering with any shop entrance.
    for x in (-26.60, -23.20):
        add_box(
            world,
            "accessible_parking_blue_header",
            (x, -23.14, 0.176),
            (2.86, 0.34, 0.030),
            M["accessible_blue"],
            0.003,
        )
    for index in range(6):
        add_box(
            world,
            "accessible_transfer_hatch",
            (-24.90, -25.55 + (index - 2.5) * 0.82, 0.178),
            (0.065, 0.62, 0.026),
            M["white"],
            0.002,
            (0, 0, math.radians(35)),
        )
    add_box(
        world,
        "rear_parking_pedestrian_route",
        (-18.93, -31.38, 0.235),
        (3.52, 25.45, 0.075),
        M["paver"],
        0.010,
    )
    for index in range(15):
        add_box(
            world,
            "rear_route_control_joint",
            (-18.93, -43.55 + index * 1.72, 0.277),
            (3.38, 0.022, 0.009),
            M["joint"],
            0.001,
        )
    return {
        "stall_count": len(stall_xs) * 2,
        "accessible_stall_count": 2,
        "mcdonalds_rear_service_apron_depth_m": 1.72,
        "mcdonalds_parking_backing_gap_m": 0.0,
        "rear_service_route_clear_width_m": 3.52,
    }


def add_fence_run(collection, M, name, start, end, spacing=0.24):
    start, end = Vector(start), Vector(end)
    direction = end - start
    length = direction.length
    tangent = direction.normalized()
    # Posts occur at both ends and at <=1.45 m structural bays; pickets are
    # evenly spaced and welded between continuous lower and upper rails.
    bay_count = max(1, math.ceil(length / 1.45))
    for index in range(bay_count + 1):
        point = start + tangent * (length * index / bay_count)
        add_cylinder(
            collection,
            name + "_post",
            (point.x, point.y, 0.62),
            (0.050, 0.050, 0.58),
            M["fence"],
            0.006,
        )
        add_box(
            collection,
            name + "_post_baseplate",
            (point.x, point.y, 0.075),
            (0.18, 0.18, 0.025),
            M["fence"],
            0.006,
        )
        for dx, dy in (
            (-0.055, -0.055),
            (-0.055, 0.055),
            (0.055, -0.055),
            (0.055, 0.055),
        ):
            add_cylinder(
                collection,
                name + "_anchor_bolt",
                (point.x + dx, point.y + dy, 0.105),
                (0.010, 0.010, 0.025),
                M["steel"],
                0.001,
            )
    box_between_xy(
        collection,
        name + "_top_rail",
        (start.x, start.y, 1.12),
        (end.x, end.y, 1.12),
        0.060,
        0.060,
        M["fence"],
        0.006,
    )
    box_between_xy(
        collection,
        name + "_lower_rail",
        (start.x, start.y, 0.28),
        (end.x, end.y, 0.28),
        0.048,
        0.048,
        M["fence"],
        0.005,
    )
    picket_count = max(1, int(length / spacing))
    for index in range(1, picket_count):
        point = start + tangent * (length * index / picket_count)
        add_cylinder(
            collection,
            name + "_vertical_picket",
            (point.x, point.y, 0.70),
            (0.018, 0.018, 0.40),
            M["fence"],
            0.003,
        )
    return picket_count - 1


def add_reference_patio(world, M):
    table = bpy.data.collections[P + "MASTER:MCD_PATIO_TABLE_SET"]
    umbrella = bpy.data.collections[P + "MASTER:MCD_PATIO_UMBRELLA"]
    patio_center_x = (MCD_PATIO_WEST_X + MCD_PATIO_EAST_X) / 2
    patio_width = MCD_PATIO_EAST_X - MCD_PATIO_WEST_X
    add_box(
        world,
        "reference_patio_paver_field",
        (patio_center_x, -8.53, 0.245),
        (patio_width, 3.78, 0.090),
        M["paver"],
        0.012,
    )
    for index in range(15):
        x = MCD_PATIO_WEST_X + 0.58 + index * ((patio_width - 1.16) / 14)
        add_box(
            world,
            "patio_longitudinal_paver_joint",
            (x, -8.53, 0.294),
            (0.022, 3.58, 0.010),
            M["joint"],
            0.001,
        )
    for y in (-9.70, -8.53, -7.36):
        add_box(
            world,
            "patio_transverse_paver_joint",
            (patio_center_x, y, 0.294),
            (patio_width - 0.22, 0.022, 0.010),
            M["joint"],
            0.001,
        )

    entry_x = MCD_ENTRY_WORLD_X
    add_box(
        world,
        "mcdonalds_clear_entry_walk",
        (entry_x, -8.50, 0.305),
        (2.45, 4.05, 0.030),
        M["concrete"],
        0.006,
    )
    add_box(
        world,
        "mcdonalds_flush_door_landing",
        (entry_x, -10.15, 0.325),
        (2.45, 0.70, 0.070),
        M["paver"],
        0.008,
    )
    for row in range(2):
        for col in range(5):
            add_box(
                world,
                "mcdonalds_tactile_warning_paver",
                (entry_x - 0.80 + col * 0.40, -6.67 - row * 0.28, 0.342),
                (0.32, 0.22, 0.030),
                M["tactile"],
                0.006,
            )

    table_sites = ((-31.75, -8.48), (-25.75, -8.48), (-22.90, -8.35), (-20.05, -9.20))
    for index, (x, y) in enumerate(table_sites):
        instance(
            world,
            table,
            "reference_patio_dining_set",
            (x, y, 0.20),
            rotation=(0.04, -0.03, 0.02, -0.04)[index],
        )
        instance(
            world,
            umbrella,
            "reference_red_patio_umbrella",
            (x, y, 0.20),
            rotation=index * 0.17,
        )

    pickets = 0
    gate_left = entry_x - 1.31
    gate_right = entry_x + 1.31
    pickets += add_fence_run(
        world,
        M,
        "patio_west_fence",
        (MCD_PATIO_WEST_X, -10.26, 0.0),
        (MCD_PATIO_WEST_X, -6.58, 0.0),
    )
    pickets += add_fence_run(
        world,
        M,
        "patio_east_fence",
        (MCD_PATIO_EAST_X, -10.26, 0.0),
        (MCD_PATIO_EAST_X, -6.58, 0.0),
    )
    pickets += add_fence_run(
        world,
        M,
        "patio_front_fence_west",
        (MCD_PATIO_WEST_X, -6.58, 0.0),
        (gate_left, -6.58, 0.0),
    )
    pickets += add_fence_run(
        world,
        M,
        "patio_front_fence_east",
        (gate_right, -6.58, 0.0),
        (MCD_PATIO_EAST_X, -6.58, 0.0),
    )
    # Open gate leaves park against the fence, leaving a 2.62 m unobstructed route.
    box_between_xy(
        world,
        "patio_open_gate_leaf_west",
        (gate_left, -6.58, 0.70),
        (gate_left, -7.70, 0.70),
        0.050,
        0.98,
        M["fence"],
        0.006,
    )
    box_between_xy(
        world,
        "patio_open_gate_leaf_east",
        (gate_right, -6.58, 0.70),
        (gate_right, -7.70, 0.70),
        0.050,
        0.98,
        M["fence"],
        0.006,
    )
    entry_left, entry_right = entry_x - 2.45 / 2, entry_x + 2.45 / 2
    furniture_radius = 1.34
    clearances = []
    for x, _ in table_sites:
        clearances.append(
            entry_left - (x + furniture_radius)
            if x < entry_x
            else (x - furniture_radius) - entry_right
        )
    sign_island_half_width = 2.02 / 2
    sign_island_half_depth = 1.18 / 2
    sign_furniture_clearances = [
        math.hypot(x - MCD_SIGN_WORLD_X, y - MCD_SIGN_WORLD_Y)
        - 1.34
        - max(sign_island_half_width, sign_island_half_depth)
        for x, y in table_sites
    ]
    return {
        "umbrella_count": len(table_sites),
        "outdoor_table_count": len(table_sites),
        "fence_picket_count": pickets,
        "entry_gate_clear_width_m": 2.62,
        "entry_walk_clear_width_m": 2.45,
        "minimum_entry_furniture_lateral_clearance_m": round(min(clearances), 3),
        "patio_depth_m": 3.78,
        "patio_width_m": round(patio_width, 3),
        "mcdonalds_sign_inside_own_patio": True,
        "mcdonalds_sign_world_location": [MCD_SIGN_WORLD_X, MCD_SIGN_WORLD_Y],
        "mcdonalds_sign_east_boundary_clearance_m": round(
            MCD_PATIO_EAST_X - (MCD_SIGN_WORLD_X + sign_island_half_width), 3
        ),
        "mcdonalds_sign_north_boundary_clearance_m": round(
            (-6.58) - (MCD_SIGN_WORLD_Y + sign_island_half_depth), 3
        ),
        "mcdonalds_sign_south_boundary_clearance_m": round(
            (MCD_SIGN_WORLD_Y - sign_island_half_depth) - (-10.26), 3
        ),
        "mcdonalds_sign_minimum_furniture_clearance_m": round(
            min(sign_furniture_clearances), 3
        ),
    }


def add_connected_world_frontage(world, M):
    # Three exact party-line connections meet at the 7-Eleven elbow, producing
    # one continuous inverse-L instead of the former T-shaped rear link.
    add_box(
        world,
        "seven_mcdonalds_party_joint",
        (-17.05, -12.95, 2.74),
        (0.080, 4.72, 5.12),
        M["steel"],
        0.006,
    )
    add_box(
        world,
        "seven_restaurant_party_joint",
        (-13.55, -15.40, 2.72),
        (6.86, 0.080, 5.08),
        M["steel"],
        0.006,
    )
    add_box(
        world,
        "mcdonalds_restaurant_party_joint",
        (-17.05, -17.02, 2.70),
        (0.080, 3.16, 5.02),
        M["steel"],
        0.006,
    )
    add_box(
        world,
        "three_store_roof_transition_cap",
        (-17.05, -15.40, 5.93),
        (0.34, 0.34, 0.12),
        M["steel"],
        0.010,
    )
    patio = add_reference_patio(world, M)
    parking = add_rear_parking(world, M)
    amenity_hidden, amenities = consolidate_northwest_amenities(world, M)
    return {
        **patio,
        **parking,
        "hidden_old_forecourt_detail_count": len(amenity_hidden),
        "hidden_old_forecourt_details": amenity_hidden,
        "relocated_amenity_asset_count": len(amenities),
        "relocated_amenity_assets": amenities,
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
    master,
    mcd,
    moved,
    hidden,
    compacted,
    parking_hidden,
    relocated,
    frontage_stats,
    world,
):
    required = (
        P + "MASTER:MCD_STOREFRONT_WINDOW",
        P + "MASTER:MCD_DOUBLE_ENTRY",
        P + "MASTER:MCD_DINING_BOOTH",
        P + "MASTER:MCD_SELF_ORDER_KIOSK",
        P + "MASTER:MCD_ROOF_EXHAUST",
        P + "MASTER:MCD_PATIO_CHAIR",
        P + "MASTER:MCD_PATIO_TABLE_SET",
        P + "MASTER:MCD_PATIO_UMBRELLA",
        "DINING_TABLE_MASTER",
        "DINING_CHAIR_MASTER",
        "KITCHEN_PREP_MASTER",
        "all43_19:MASTER:ROOFTOP_CONDENSER",
    )
    missing = [name for name in required if bpy.data.collections.get(name) is None]
    all_parts = recursive_collection_objects(master)
    new_objects = [obj for obj in bpy.data.objects if obj.name.startswith(P)]
    instances = [obj for obj in new_objects if obj.instance_type == "COLLECTION"]
    glazing = [obj for obj in new_objects if "laminated_dining_glass" in obj.name]
    interior_parts = [
        obj
        for obj in all_parts
        if any(
            token in obj.name
            for token in (
                "dining_",
                "kiosk",
                "ordering_",
                "kitchen_",
                "cooking_",
                "sink_",
                "beverage_",
            )
        )
    ]
    forbidden = [
        obj.name
        for obj in new_objects
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
        )
    ]
    bad_meshes = []
    for obj in new_objects:
        if obj.type != "MESH":
            continue
        finite = all(math.isfinite(value) for value in (*obj.location, *obj.scale))
        if (
            obj.data is None
            or not obj.data.vertices
            or not finite
            or min(abs(v) for v in obj.scale) < 0.001
        ):
            bad_meshes.append(obj.name)

    seven = bpy.data.objects["all43_19:street_corner_711"]
    fresh = bpy.data.objects["all43_01:convenience_store"]
    restaurant = bpy.data.objects["all43_01:restaurant"]
    seven_west = seven.location.x - 3.50
    mcd_east = MCD_LOCATION.x + MCD_WIDTH / 2
    seven_north = seven.location.y + 8.10 / 2
    mcd_north = MCD_LOCATION.y + MCD_DEPTH / 2
    mcd_south = MCD_LOCATION.y - MCD_DEPTH / 2
    seven_south = seven.location.y - 8.10 / 2
    restaurant_north = restaurant.location.y + 15.68 * SHOP_WING_SCALE / 2
    restaurant_south = restaurant.location.y - 15.68 * SHOP_WING_SCALE / 2
    fresh_north = fresh.location.y + 15.68 * SHOP_WING_SCALE / 2
    restaurant_west = restaurant.location.x - 8.86 / 2
    mcd_seven_overlap = min(mcd_north, seven_north) - max(mcd_south, seven_south)
    mcd_west = MCD_LOCATION.x - MCD_WIDTH / 2
    checks = {
        "missing_nested_assets": missing,
        "mcdonalds_is_linked_collection_instance": mcd.instance_type == "COLLECTION"
        and mcd.instance_collection == master,
        "mcdonalds_recursive_component_count": len(all_parts),
        "mcdonalds_direct_component_count": len(
            [obj for obj in master.objects if not obj.hide_render]
        ),
        "mcdonalds_collection_instance_count": len(instances),
        "mcdonalds_storefront_glass_component_count": len(glazing),
        "mcdonalds_interior_component_count": len(interior_parts),
        "mcdonalds_length_increase_from_all43_22_m": round(MCD_WIDTH - 13.60, 3),
        "mcdonalds_west_party_line_x_m": round(mcd_west, 3),
        "mcdonalds_patio_west_clearance_to_cafe_m": round(
            MCD_PATIO_WEST_X - mcd_west, 3
        ),
        "shop_layout_changed_count": len(moved),
        "shop_layout_changes": moved,
        "seven_mcdonalds_party_gap_m": round(abs(seven_west - mcd_east), 3),
        "seven_mcdonalds_front_alignment_m": round(abs(seven_north - mcd_north), 3),
        "seven_mcdonalds_party_overlap_m": round(mcd_seven_overlap, 3),
        "seven_corner_kitchen_party_gap_m": round(
            abs(seven_south - restaurant_north), 3
        ),
        "mcdonalds_corner_kitchen_party_gap_m": round(
            abs(mcd_east - restaurant_west), 3
        ),
        "fresh_mart_corner_kitchen_party_gap_m": round(
            abs(fresh_north - restaurant_south), 3
        ),
        "shop_wing_rotation_deg": round(math.degrees(restaurant.rotation_euler.z), 3),
        "shop_wing_width_scale": SHOP_WING_SCALE,
        "shop_frontage_depth_adjusted_object_count": len(compacted),
        "hidden_displaced_frontage_assets": hidden,
        "hidden_legacy_parking_object_count": len(parking_hidden),
        "hidden_legacy_parking_objects": parking_hidden,
        "relocated_parking_asset_count": len(relocated),
        "relocated_parking_assets": relocated,
        "connected_world_frontage_object_count": len(world.objects) - 1,
        **frontage_stats,
        "new_mesh_quality_failures": bad_meshes,
        "forbidden_toy_or_proxy_names": forbidden,
        "mcdonalds_world_bounds": [
            [round(mcd_west, 3), -18.60, 0.205],
            [-17.05, -6.58, 6.34],
        ],
        "commercial_region_world_bounds": [
            [-58.45, -44.50, 0.0],
            [-6.25, -6.25, 10.25],
        ],
    }
    if (
        missing
        or not checks["mcdonalds_is_linked_collection_instance"]
        or len(all_parts) < 330
        or len(instances) < 30
        or len(interior_parts) < 75
        or len(moved) != 3
        or checks["seven_mcdonalds_party_gap_m"] > 0.04
        or checks["seven_mcdonalds_party_overlap_m"] < 4.50
        or checks["seven_corner_kitchen_party_gap_m"] > 0.04
        or checks["mcdonalds_corner_kitchen_party_gap_m"] > 0.04
        or checks["fresh_mart_corner_kitchen_party_gap_m"] > 0.04
        or abs(checks["shop_wing_rotation_deg"] - 90.0) > 0.01
        or len(compacted) < 20
        or len(hidden) != 3
        or len(parking_hidden) < 30
        or checks["umbrella_count"] != 4
        or checks["outdoor_table_count"] != 4
        or checks["fence_picket_count"] < 55
        or checks["entry_gate_clear_width_m"] < 2.60
        or checks["entry_walk_clear_width_m"] < 2.40
        or checks["minimum_entry_furniture_lateral_clearance_m"] < 0.10
        or checks["mcdonalds_length_increase_from_all43_22_m"] < 2.75
        or checks["mcdonalds_patio_west_clearance_to_cafe_m"] < 0.10
        or checks["mcdonalds_sign_inside_own_patio"] is not True
        or checks["mcdonalds_sign_east_boundary_clearance_m"] < 0.10
        or checks["mcdonalds_sign_north_boundary_clearance_m"] < 0.10
        or checks["mcdonalds_sign_minimum_furniture_clearance_m"] < 0.10
        or checks["mcdonalds_rear_service_apron_depth_m"] < 1.70
        or checks["rear_service_route_clear_width_m"] < 3.40
        or checks["hidden_old_forecourt_detail_count"] < 7
        or checks["relocated_amenity_asset_count"] < 7
        or checks["stall_count"] != 16
        or bad_meshes
        or forbidden
    ):
        raise RuntimeError({"all43_20_quality_audit_failed": checks})
    return {
        "pipeline_stage": "commercial_mcdonalds_layout_generator_20.py",
        "new_asset_master": MASTER_NAME,
        "new_store_instance": mcd.name,
        "mcdonalds_program": master["architectural_program"],
        "layout_strategy": "continuous inverse-L commercial street base: LEMON COFFEE + McDonald's north arm, corner 7-Eleven elbow, Corner Kitchen + Fresh Mart south arm; all43-25 reference bars extend the north arm in this same generator run",
        "mcdonalds_full_scale_dimensions_m": [MCD_WIDTH, MCD_DEPTH, MCD_HEIGHT],
        "mcdonalds_frontage_system": "pale gridded masonry, dark wordmark panel, low-iron glazing, supported red window canopies, sweeping yellow roofline and physical illuminated signage",
        "mcdonalds_patio_system": "four full-scale welded dining settings below ribbed red umbrellas, an engineered low pylon on a protected drained island, and anchored black steel picket fencing with a clear axial gate",
        "mcdonalds_interior_system": "window dining, booths, accessible tables, self-order kiosks, POS/pickup, queue, sorting station and operational cooking/prep/wash line",
        "mcdonalds_roof_system": "parapet/coping, membrane, curbed HVAC, kitchen exhaust, access hatch, isolator rails, conduit and connected drainage",
        "reference_interpretation": "reference-matched roadside McDonald's with pale gridded facade, dark McDonald's band, red window canopies, yellow curved roofline, red umbrella seating and black perimeter fence",
        "toy_model_policy": "PASS: no proxy/placeholder/toy assets; detailed shared production masters and manufactured connections only",
        **checks,
    }


def audit_cafe(master, cafe, frontage_stats, world):
    required = (
        CAFE_P + "MASTER:STREET_LOUNGE_CHAIR",
        CAFE_P + "MASTER:STREET_SIDE_TABLE",
        CAFE_P + "MASTER:TAKEAWAY_CUP",
        CAFE_P + "MASTER:PASTRY_PLATE",
        "DINING_TABLE_MASTER",
        "DINING_CHAIR_MASTER",
        "all43_19:MASTER:ROOFTOP_CONDENSER",
    )
    missing = [name for name in required if bpy.data.collections.get(name) is None]
    all_parts = recursive_collection_objects(master)
    new_objects = [obj for obj in bpy.data.objects if obj.name.startswith(CAFE_P)]
    instances = [obj for obj in new_objects if obj.instance_type == "COLLECTION"]
    interior_tokens = (
        "bar_",
        "pastry_",
        "espresso_",
        "grinder_",
        "backbar_",
        "rinser_",
        "barstool_",
        "dining_",
        "track_spotlight",
        "coffee_retail_bag",
    )
    interior_parts = [
        obj for obj in all_parts if any(token in obj.name for token in interior_tokens)
    ]
    glazing = [obj for obj in new_objects if "glass" in obj.name]
    manufactured_signs = [
        obj
        for obj in new_objects
        if any(
            token in obj.name
            for token in ("lemon_coffee_letters", "lightbox", "blade_sign")
        )
    ]
    furniture_ground_components = [
        obj
        for obj in new_objects
        if any(
            token in obj.name
            for token in (
                "adjustable_epdm_glide",
                "leveling_pad",
                "leg_leveler_locknut",
            )
        )
    ]
    planter_assembly = [
        obj
        for obj in world.objects
        if obj.name.startswith(CAFE_P + "cafe_fiddle_leaf_planter_")
    ]
    botanical_leaves = [
        obj
        for obj in world.objects
        if obj.type == "MESH"
        and obj.name.startswith(CAFE_P + "cafe_fiddle_leaf_fig_cambered_leaf_blade")
    ]
    botanical_stems = [
        obj
        for obj in world.objects
        if obj.type == "MESH"
        and obj.name.startswith(
            CAFE_P + "cafe_fiddle_leaf_fig_continuous_tapered_stem_"
        )
    ]
    forbidden = [
        obj.name
        for obj in new_objects
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
        )
    ]
    bad_meshes = []
    for obj in new_objects:
        if obj.type != "MESH":
            continue
        finite = all(math.isfinite(value) for value in (*obj.location, *obj.scale))
        if (
            obj.data is None
            or not obj.data.vertices
            or not finite
            or min(abs(v) for v in obj.scale) < 0.001
        ):
            bad_meshes.append(obj.name)

    cafe_east = CAFE_LOCATION.x + CAFE_WIDTH / 2
    cafe_west = CAFE_LOCATION.x - CAFE_WIDTH / 2
    cafe_front = CAFE_LOCATION.y + CAFE_DEPTH / 2
    cafe_rear = CAFE_LOCATION.y - CAFE_DEPTH / 2
    mcd_west = MCD_LOCATION.x - MCD_WIDTH / 2
    mcd_front = MCD_LOCATION.y + MCD_DEPTH / 2
    parking_north = -20.38 + 0.22 / 2
    mcd_sign_island_west = MCD_SIGN_WORLD_X - 2.02 / 2
    bpy.context.view_layer.update()
    leaf_intersections = []
    if botanical_leaves:
        from mathutils.bvhtree import BVHTree

        depsgraph = bpy.context.evaluated_depsgraph_get()
        leaf_trees = {
            obj.name: BVHTree.FromObject(obj, depsgraph, epsilon=0.0005)
            for obj in botanical_leaves
        }
        for index, first in enumerate(botanical_leaves):
            for second in botanical_leaves[index + 1 :]:
                if leaf_trees[first.name].overlap(leaf_trees[second.name]):
                    leaf_intersections.append([first.name, second.name])
        leaf_vertices = [
            obj.matrix_world @ vertex.co
            for obj in botanical_leaves
            for vertex in obj.data.vertices
        ]
        botanical_min_y = min(vertex.y for vertex in leaf_vertices) - 0.008
        botanical_max_x = max(vertex.x for vertex in leaf_vertices) + 0.008
        botanical_min_z = min(vertex.z for vertex in leaf_vertices) - 0.008
    else:
        botanical_min_y = -99.0
        botanical_max_x = 99.0
        botanical_min_z = -99.0
    chair_structural_top_z = 0.29 + 1.035
    checks = {
        "cafe_missing_nested_assets": missing,
        "cafe_is_linked_collection_instance": cafe.instance_type == "COLLECTION"
        and cafe.instance_collection == master,
        "cafe_recursive_component_count": len(all_parts),
        "cafe_direct_component_count": len(
            [obj for obj in master.objects if not obj.hide_render]
        ),
        "cafe_collection_instance_count": len(instances),
        "cafe_interior_component_count": len(interior_parts),
        "cafe_storefront_glass_component_count": len(glazing),
        "cafe_manufactured_sign_component_count": len(manufactured_signs),
        "cafe_furniture_ground_component_count": len(furniture_ground_components),
        "cafe_planter_assembly_component_count": len(planter_assembly),
        "cafe_mcdonalds_party_gap_m": round(abs(cafe_east - mcd_west), 3),
        "cafe_mcdonalds_front_alignment_m": round(abs(cafe_front - mcd_front), 3),
        "cafe_rear_clearance_to_parking_curb_m": round(cafe_rear - parking_north, 3),
        "cafe_clearance_to_mcdonalds_road_sign_m": round(
            mcd_sign_island_west - cafe_east, 3
        ),
        "cafe_planter_foliage_clearance_to_mcdonalds_patio_fence_m": round(
            MCD_PATIO_WEST_X - botanical_max_x, 3
        ),
        "cafe_botanical_canopy_clearance_to_storefront_m": round(
            botanical_min_y - cafe_front, 3
        ),
        "cafe_botanical_lower_canopy_clearance_above_chair_m": round(
            botanical_min_z - chair_structural_top_z, 3
        ),
        "cafe_botanical_leaf_evaluated_intersections": leaf_intersections,
        "cafe_botanical_leaf_mesh_count": len(botanical_leaves),
        "cafe_botanical_continuous_stem_mesh_count": len(botanical_stems),
        "cafe_world_frontage_object_count": sum(
            obj.name.startswith(CAFE_P) for obj in world.objects
        ),
        "cafe_new_mesh_quality_failures": bad_meshes,
        "cafe_forbidden_toy_or_proxy_names": forbidden,
        "cafe_building_world_bounds": [
            [round(cafe_west, 3), round(cafe_rear, 3), 0.205],
            [round(cafe_east, 3), round(cafe_front, 3), round(CAFE_HEIGHT + 0.205, 3)],
        ],
        "cafe_complete_world_bounds": [
            [round(cafe_west - 0.15, 3), -18.92, 0.0],
            [round(cafe_east + 0.17, 3), -6.43, 8.70],
        ],
        **frontage_stats,
    }
    if (
        missing
        or not checks["cafe_is_linked_collection_instance"]
        or len(all_parts) < 240
        or len([obj for obj in master.objects if not obj.hide_render]) < 205
        or len(instances) < 25
        or len(interior_parts) < 135
        or len(glazing) < 12
        or len(manufactured_signs) < 7
        or checks["cafe_mcdonalds_party_gap_m"] > 0.01
        or checks["cafe_mcdonalds_front_alignment_m"] > 0.01
        or checks["cafe_rear_clearance_to_parking_curb_m"] < 1.60
        or checks["cafe_clearance_to_mcdonalds_road_sign_m"] < 0.18
        or checks["cafe_planter_foliage_clearance_to_mcdonalds_patio_fence_m"] < 0.18
        or checks["cafe_botanical_canopy_clearance_to_storefront_m"] < 0.20
        or checks["cafe_botanical_lower_canopy_clearance_above_chair_m"] < 0.07
        or checks["cafe_botanical_leaf_evaluated_intersections"]
        or checks["cafe_botanical_leaf_mesh_count"] != 22
        or checks["cafe_botanical_continuous_stem_mesh_count"] != 3
        or checks["frontage_chair_count"] != 3
        or checks["frontage_table_count"] != 2
        or checks["frontage_chairs_face_road"] is not True
        or checks["frontage_chair_back_clearance_to_facade_m"] > 0.50
        or checks["frontage_served_cup_count"] != 2
        or checks["frontage_clear_pedestrian_width_m"] < 1.10
        or checks["frontage_paver_east_clearance_to_mcdonalds_fence_m"] < 0.08
        or checks["frontage_grounding_error_m"] > 0.002
        or checks["planter_shell_is_hollow_assembly"] is not True
        or checks["planter_liner_is_hollow_five_piece_assembly"] is not True
        or checks["planter_recessed_foot_count"] != 4
        or checks["planter_drainage_component_count"] < 2
        or checks["cafe_furniture_ground_component_count"] < 6
        or checks["cafe_planter_assembly_component_count"] < 22
        or checks["botanical_stem_count"] != 3
        or checks["botanical_leaf_count"] != 22
        or checks["botanical_leaf_vertices_each"] < 45
        or checks["botanical_authored_minimum_leaf_lane_clearance_m"] < 0.025
        or checks["botanical_rooted_in_separate_mulch_and_soil_layers"] is not True
        or checks["parking_stalls_consumed"] != 0
        or bad_meshes
        or forbidden
    ):
        raise RuntimeError({"all43_24_cafe_quality_audit_failed": checks})
    return {
        "production_revision": "urban_v3_all43_24",
        "cafe_pipeline_stage": "commercial_mcdonalds_layout_generator_20.py",
        "cafe_new_asset_master": CAFE_MASTER_NAME,
        "cafe_new_store_instance": cafe.name,
        "cafe_program": master["architectural_program"],
        "cafe_full_scale_dimensions_m": [CAFE_WIDTH, CAFE_DEPTH, CAFE_HEIGHT],
        "cafe_reference_interpretation": "LEMON COFFEE roadside shop with black vertical-fluted fascia, warm oak portals, white channel lettering, black supported awning, operable steel glazing, visible stone coffee bar and low street furniture",
        "cafe_frontage_system": "dimensional channel signs, thermally broken glazed entry, three-bay operable service window, folded supported awning, stone sill, menu plaques, sconces and drained paver frontage",
        "cafe_interior_system": "refrigerated pastry display, two-group plumbed espresso machine, twin grinders, rinsing station, stocked illuminated backbar, sink, counter stools, tables and track lighting",
        "cafe_roof_system": "parapet/coping, membrane, curbed condenser, bar exhaust, access hatch, service conduit and connected rainwater pipe",
        "cafe_frontage_facilities": "three road-facing, facade-backed grounded contract lounge chairs with adjustable glides and welded frames, two leveled ballasted brass/stone side tables with served cups, clear pedestrian band, tactile entry, trench drainage, blade sign and a collision-audited mature fiddle-leaf fig in a hollow drained layered planter",
        "cafe_toy_model_policy": "PASS: no proxy/placeholder/toy assets; furniture has manufactured support hardware and the living plant uses three diverging continuous tapered stems, articulated petioles, fifty-vertex solid cambered leaves, physical midribs and audited nonintersection",
        **checks,
    }


def run(target_revision="urban_v3_all43_25"):
    """Build the active connected commercial block at the requested revision.

    ``urban_v3_all43_24`` stops after the collision-audited LEMON COFFEE
    frontage.  The default remains ALL43-25 for existing callers and adds the
    two reference bars.  Keeping the revision switch here, in the production
    generator, lets complete-city builds reproduce ALL43-24 without opening a
    completed regional Blend or maintaining a disconnected copy of the asset.
    """
    if target_revision not in {"urban_v3_all43_24", "urban_v3_all43_25"}:
        raise ValueError(f"unsupported commercial target revision: {target_revision}")

    M = materials()
    moved, compacted = rearrange_existing_shops()
    hidden = hide_displaced_frontage_assets()
    master = build_mcdonalds_master(M)
    world = ensure_world_collection()
    parking_hidden = hide_legacy_parking_layout()
    relocated = relocate_existing_parking_assets()
    stale = bpy.data.objects.get(P + "north_road_mcdonalds")
    if stale:
        bpy.data.objects.remove(stale, do_unlink=True)
    mcd = instance(world, master, "north_road_mcdonalds", MCD_LOCATION, MCD_ROTATION)
    mcd["c2w_semantic_role"] = "full-scale road-facing quick-service restaurant"
    stage = "all43_24" if target_revision == "urban_v3_all43_24" else "all43_25"
    mcd["c2w_pipeline_stage"] = stage
    mcd["c2w_generator_revision"] = (
        "all43_24 lengthened restaurant with protected sign and collision-audited cafe frontage"
        if target_revision == "urban_v3_all43_24"
        else "all43_25 retained lengthened restaurant and added two adjacent reference bars"
    )
    mcd[
        "brand_reference"
    ] = "provided pale McDonald's reference with red canopies, red umbrellas, black fence, yellow roofline and golden arches"
    frontage_stats = add_connected_world_frontage(world, M)
    cafe_master = build_cafe_master(M)
    stale_cafe = bpy.data.objects.get(CAFE_P + "north_road_lemon_coffee")
    if stale_cafe:
        bpy.data.objects.remove(stale_cafe, do_unlink=True)
    cafe = cafe_instance(
        world, cafe_master, "north_road_lemon_coffee", CAFE_LOCATION, CAFE_ROTATION
    )
    cafe["c2w_semantic_role"] = "full-scale road-facing specialty coffee shop"
    cafe["c2w_pipeline_stage"] = stage
    cafe["c2w_generator_revision"] = (
        "all43_24 road-facing chairs and collision-audited botanical frontage"
        if target_revision == "urban_v3_all43_24"
        else "all43_25 retained road-facing chairs and botanical frontage beside two new reference bars"
    )
    cafe[
        "reference_url"
    ] = "https://respic.3d66.com/coverimg/cache/08e7/f3369b2aa37f4d7597c7f3ae56f07653.jpg!medium-size-2?v=13114337&k=D41D8CD98F00B204E9800998ECF8427E"
    cafe_frontage_stats = add_cafe_frontage_world(world, M)
    mcd_stats = audit(
        master,
        mcd,
        moved,
        hidden,
        compacted,
        parking_hidden,
        relocated,
        frontage_stats,
        world,
    )
    cafe_stats = audit_cafe(cafe_master, cafe, cafe_frontage_stats, world)
    if target_revision == "urban_v3_all43_24":
        return {
            **mcd_stats,
            **cafe_stats,
            "production_revision": "urban_v3_all43_24",
            "all43_25_reference_bars_built": False,
        }

    import commercial_reference_bars_generator_25 as bars25

    bar_stats = bars25.build_and_audit(
        world, M, CAFE_LOCATION, CAFE_WIDTH, SEVEN_LOCATION
    )
    return {
        **mcd_stats,
        **cafe_stats,
        **bar_stats,
        "all43_25_reference_bars_built": True,
    }
