"""All43-16: transparent storefront glass and realistic frontage planters."""
import math
import random

import bpy
from mathutils import Quaternion, Vector


P = "all43_16:"
FRESH_COLLECTION = "all43_01:MASTER:convenience_store"
RESTAURANT_COLLECTION = "all43_01:MASTER:restaurant"


def cube_mesh():
    return bpy.data.meshes["all43_10:shared_cube"]


def cylinder_mesh():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


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
        tex.inputs["Roughness"].default_value = 0.63
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(
            max(0.0, value * 0.84) for value in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1.0, value * 1.12 + 0.008) for value in color[:3]
        ) + (1,)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump_node = nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.012
        links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def clear_storefront_glass():
    """Use a mostly camera-transparent mix while retaining subtle glass response."""
    mat = bpy.data.materials.get(P + "clear_interior_visible_storefront_glass")
    if mat is None:
        mat = bpy.data.materials.new(P + "clear_interior_visible_storefront_glass")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    links = mat.node_tree.links

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = P + "glass_output"
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.name = P + "camera_visibility"
    transparent.inputs["Color"].default_value = (0.82, 0.90, 0.90, 1)
    glass = nodes.new("ShaderNodeBsdfPrincipled")
    glass.name = P + "subtle_physical_glass"
    glass.inputs["Base Color"].default_value = (0.10, 0.16, 0.16, 1)
    glass.inputs["Roughness"].default_value = 0.075
    glass.inputs["Metallic"].default_value = 0.0
    glass.inputs["Transmission Weight"].default_value = 1.0
    glass.inputs["IOR"].default_value = 1.45
    glass.inputs["Coat Weight"].default_value = 0.12
    glass.inputs["Coat Roughness"].default_value = 0.06
    mix = nodes.new("ShaderNodeMixShader")
    mix.name = P + "visibility_reflection_balance"
    mix.inputs[0].default_value = 0.18
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(glass.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    mat.diffuse_color = (0.12, 0.18, 0.18, 0.16)
    mat["transparent_camera_fraction"] = 0.82
    mat["purpose"] = "storefront interior visibility with restrained reflection"
    return mat


def plant_materials():
    return {
        "pot": material(
            "planter_powdercoat", (0.075, 0.090, 0.082, 1), 0.50, 0.45, 42, 0.020
        ),
        "pot_inset": material(
            "planter_inset_panel", (0.12, 0.14, 0.125, 1), 0.58, 0.30, 38, 0.018
        ),
        "rim": material(
            "planter_top_rim", (0.23, 0.25, 0.225, 1), 0.40, 0.58, 45, 0.012
        ),
        "soil": material(
            "rich_planter_soil", (0.075, 0.043, 0.022, 1), 0.94, 0, 44, 0.12
        ),
        "stem": material(
            "natural_woody_stem", (0.18, 0.105, 0.040, 1), 0.76, 0, 35, 0.055
        ),
        "leaf_dark": material(
            "leaf_deep_green", (0.028, 0.14, 0.050, 1), 0.66, 0, 30, 0.040
        ),
        "leaf_mid": material(
            "leaf_mid_green", (0.055, 0.235, 0.078, 1), 0.62, 0, 34, 0.045
        ),
        "leaf_light": material(
            "leaf_new_growth", (0.12, 0.34, 0.095, 1), 0.60, 0, 30, 0.038
        ),
        "pebble": material(
            "drainage_pebble", (0.24, 0.22, 0.18, 1), 0.90, 0, 38, 0.085
        ),
    }


def assign_material(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat


def add_shared(collection, name, mesh, loc, scale, mat, bevel=0.0, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("realistic_edge_radius", "BEVEL")
        modifier.width = min(bevel, min(scale) * 0.18)
        modifier.segments = 3
    obj["shared_mesh_data"] = True
    return obj


def add_box(collection, name, loc, scale, mat, bevel=0.006, rot=(0, 0, 0)):
    return add_shared(collection, name, cube_mesh(), loc, scale, mat, bevel, rot)


def cylinder_between(collection, name, start, end, radius, mat):
    start = Vector(start)
    end = Vector(end)
    direction = end - start
    obj = add_shared(
        collection,
        name,
        cylinder_mesh(),
        (start + end) / 2,
        (radius, radius, direction.length / 2),
        mat,
        0.002,
    )
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def tapered_planter_mesh():
    name = P + "hollow_tapered_planter_mesh"
    existing = bpy.data.meshes.get(name)
    if existing:
        return existing
    outer_bottom = [
        (-0.42, -0.28, 0.06),
        (0.42, -0.28, 0.06),
        (0.42, 0.28, 0.06),
        (-0.42, 0.28, 0.06),
    ]
    outer_top = [
        (-0.52, -0.36, 0.64),
        (0.52, -0.36, 0.64),
        (0.52, 0.36, 0.64),
        (-0.52, 0.36, 0.64),
    ]
    inner_top = [
        (-0.43, -0.27, 0.64),
        (0.43, -0.27, 0.64),
        (0.43, 0.27, 0.64),
        (-0.43, 0.27, 0.64),
    ]
    inner_low = [
        (-0.38, -0.23, 0.50),
        (0.38, -0.23, 0.50),
        (0.38, 0.23, 0.50),
        (-0.38, 0.23, 0.50),
    ]
    vertices = outer_bottom + outer_top + inner_top + inner_low
    faces = [(0, 3, 2, 1)]
    for index in range(4):
        nxt = (index + 1) % 4
        faces.append((index, nxt, 4 + nxt, 4 + index))
        faces.append((4 + index, 4 + nxt, 8 + nxt, 8 + index))
        faces.append((8 + index, 8 + nxt, 12 + nxt, 12 + index))
    faces.append((12, 13, 14, 15))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def leaf_mesh(name, length, width):
    mesh_name = P + name
    existing = bpy.data.meshes.get(mesh_name)
    if existing:
        return existing
    profile = [
        (0, 0, 0),
        (-width * 0.55, 0.010, length * 0.20),
        (-width, 0.022, length * 0.48),
        (-width * 0.52, 0.016, length * 0.78),
        (0, 0, length),
        (width * 0.52, 0.016, length * 0.78),
        (width, 0.022, length * 0.48),
        (width * 0.55, 0.010, length * 0.20),
    ]
    thickness = 0.004
    vertices = [(x, y - thickness, z) for x, y, z in profile]
    vertices += [(x, y + thickness, z) for x, y, z in profile]
    faces = [tuple(range(8)), tuple(reversed(range(8, 16)))]
    for index in range(8):
        nxt = (index + 1) % 8
        faces.append((index, nxt, 8 + nxt, 8 + index))
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def add_leaf(collection, mesh, name, loc, direction, scale, mat, roll):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = (scale, scale, scale)
    direction = Vector(direction).normalized()
    orientation = direction.to_track_quat("Z", "Y")
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = orientation @ Quaternion(Vector((0, 0, 1)), roll)
    assign_material(obj, mat)
    obj["shared_botanical_mesh"] = True
    return obj


def make_planter_master(M):
    old = bpy.data.collections.get("COMMERCIAL_PLANTER_MASTER")
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("COMMERCIAL_PLANTER_MASTER")
    collection.use_fake_user = True
    collection["asset_role"] = "hollow architectural planter with branched live shrub"

    pot = bpy.data.objects.new(
        P + "hollow_tapered_metal_planter", tapered_planter_mesh()
    )
    collection.objects.link(pot)
    assign_material(pot, M["pot"])
    bevel = pot.modifiers.new("formed_planter_edge_radius", "BEVEL")
    bevel.width = 0.022
    bevel.segments = 3
    pot["not_a_primitive_box"] = True

    for x in (-0.36, 0.36):
        for y in (-0.22, 0.22):
            add_box(
                collection,
                "recessed_planter_foot",
                (x, y, 0.035),
                (0.12, 0.10, 0.07),
                M["pot"],
                0.010,
            )
    add_box(
        collection,
        "front_recessed_planter_panel",
        (0, -0.348, 0.35),
        (0.70, 0.024, 0.31),
        M["pot_inset"],
        0.008,
    )
    add_box(
        collection,
        "rear_recessed_planter_panel",
        (0, 0.348, 0.35),
        (0.70, 0.024, 0.31),
        M["pot_inset"],
        0.008,
    )
    add_box(
        collection,
        "planter_soil_bed",
        (0, 0, 0.565),
        (0.82, 0.50, 0.075),
        M["soil"],
        0.004,
    )
    for x, y, size in (
        (-0.31, -0.12, 0.045),
        (-0.12, 0.18, 0.035),
        (0.10, -0.15, 0.050),
        (0.30, 0.12, 0.038),
        (0.02, 0.16, 0.028),
    ):
        add_shared(
            collection,
            "visible_drainage_pebble",
            cylinder_mesh(),
            (x, y, 0.615),
            (size, size * 0.82, size * 0.34),
            M["pebble"],
            0.003,
        )

    broad_leaf = leaf_mesh("broad_lanceolate_leaf_mesh", 0.38, 0.085)
    narrow_leaf = leaf_mesh("narrow_lanceolate_leaf_mesh", 0.43, 0.058)
    rng = random.Random(431601)
    leaf_count = 0
    branch_count = 0
    stem_count = 0
    stem_specs = []
    for index in range(9):
        angle = index * (math.tau / 9) + rng.uniform(-0.20, 0.20)
        base = Vector(
            (
                math.cos(angle) * rng.uniform(0.04, 0.20),
                math.sin(angle) * rng.uniform(0.04, 0.15),
                0.61,
            )
        )
        height = rng.uniform(0.92, 1.28)
        top = Vector(
            (
                base.x + math.cos(angle) * rng.uniform(0.12, 0.32),
                base.y + math.sin(angle) * rng.uniform(0.08, 0.24),
                0.61 + height,
            )
        )
        cylinder_between(
            collection,
            "woody_primary_stem",
            base,
            top,
            rng.uniform(0.014, 0.023),
            M["stem"],
        )
        stem_specs.append((base, top, angle))
        stem_count += 1

    for stem_index, (base, top, stem_angle) in enumerate(stem_specs):
        for level_index, factor in enumerate((0.32, 0.49, 0.66, 0.82)):
            start = base.lerp(top, factor)
            azimuth = (
                stem_angle
                + (math.pi * 0.70 if level_index % 2 else -math.pi * 0.58)
                + rng.uniform(-0.35, 0.35)
            )
            branch_length = rng.uniform(0.20, 0.36) * (1.05 - factor * 0.28)
            end = start + Vector(
                (
                    math.cos(azimuth) * branch_length,
                    math.sin(azimuth) * branch_length,
                    rng.uniform(0.08, 0.17),
                )
            )
            cylinder_between(
                collection,
                "tapered_side_branch",
                start,
                end,
                rng.uniform(0.007, 0.011),
                M["stem"],
            )
            branch_count += 1
            for leaf_side in (-1, 1):
                radial = Vector(
                    (
                        math.cos(azimuth + leaf_side * 0.52),
                        math.sin(azimuth + leaf_side * 0.52),
                        rng.uniform(0.20, 0.42),
                    )
                )
                position = start.lerp(end, 0.66 if leaf_side < 0 else 0.92)
                leaf_mat = (
                    M["leaf_light"]
                    if factor > 0.78 and leaf_side > 0
                    else M[
                        "leaf_mid" if (stem_index + level_index) % 3 else "leaf_dark"
                    ]
                )
                add_leaf(
                    collection,
                    broad_leaf
                    if (stem_index + level_index + leaf_side) % 2
                    else narrow_leaf,
                    "individual_lanceolate_leaf",
                    position,
                    radial,
                    rng.uniform(0.76, 1.13),
                    leaf_mat,
                    rng.uniform(-math.pi, math.pi),
                )
                leaf_count += 1
        top_direction = Vector(
            (math.cos(stem_angle) * 0.25, math.sin(stem_angle) * 0.25, 1.0)
        )
        add_leaf(
            collection,
            narrow_leaf,
            "upright_new_growth_leaf",
            top,
            top_direction,
            rng.uniform(0.78, 1.02),
            M["leaf_light"],
            rng.uniform(-math.pi, math.pi),
        )
        leaf_count += 1

    collection["primary_stem_count"] = stem_count
    collection["side_branch_count"] = branch_count
    collection["individual_leaf_count"] = leaf_count
    collection["foliage_geometry"] = "shared custom lanceolate meshes; no spheres"
    return collection, {
        "primary_stems": stem_count,
        "side_branches": branch_count,
        "individual_leaves": leaf_count,
    }


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


def replace_planters():
    hidden = []
    for collection_name in (FRESH_COLLECTION, RESTAURANT_COLLECTION):
        collection = bpy.data.collections[collection_name]
        for obj in collection.objects:
            if obj.name.startswith("all43_15:") and any(
                token in obj.name
                for token in (
                    "anchored_frontage_planter",
                    "planter_soil",
                    "planter_foliage",
                )
            ):
                obj.hide_render = True
                obj.hide_viewport = True
                obj[
                    P + "hidden_reason"
                ] = "replace spherical toy foliage with branched botanical asset"
                hidden.append(obj.name)
    M = plant_materials()
    master, plant_stats = make_planter_master(M)
    fresh = bpy.data.collections[FRESH_COLLECTION]
    restaurant = bpy.data.collections[RESTAURANT_COLLECTION]
    instance(
        fresh,
        master,
        "fresh_mart_realistic_frontage_planter",
        (-6.45, -5.82, 0.22),
        math.radians(-5),
        (1.05, 1.05, 1.05),
    )
    instance(
        restaurant,
        master,
        "corner_kitchen_realistic_frontage_planter",
        (-6.25, -5.82, 0.22),
        math.radians(8),
        (0.98, 0.98, 1.02),
    )
    return hidden, plant_stats


def fix_storefront_visibility():
    blockers = []
    for collection_name, blocker_token in (
        ("STOREFRONT_FRAME_MASTER", "frame_recess_shadow"),
        ("STOREFRONT_DOOR_MASTER", "door_reveal"),
    ):
        collection = bpy.data.collections[collection_name]
        for obj in collection.objects:
            if blocker_token in obj.name:
                obj.hide_render = True
                obj.hide_viewport = True
                obj[P + "hidden_reason"] = "solid geometry blocked interior visibility"
                blockers.append(obj.name)

    glass = clear_storefront_glass()
    updated = []
    targets = (
        ("STOREFRONT_WINDOW_MASTER", "laminated_display_glass"),
        ("STOREFRONT_DOOR_MASTER", "door_glass_leaf"),
    )
    for collection_name, token in targets:
        for obj in bpy.data.collections[collection_name].objects:
            if token in obj.name:
                assign_material(obj, glass)
                obj[P + "glass_role"] = "interior-visible storefront glazing"
                updated.append(obj.name)
    return blockers, updated, glass


def audit(blockers, glass_objects, hidden_planters, plant_stats, glass):
    master = bpy.data.collections.get("COMMERCIAL_PLANTER_MASTER")
    if not master:
        raise RuntimeError("COMMERCIAL_PLANTER_MASTER missing")
    if len(blockers) != 2 or len(glass_objects) != 2:
        raise RuntimeError({"blockers": blockers, "glass_objects": glass_objects})
    sphere_foliage = [
        obj.name
        for obj in bpy.data.objects
        if obj.name.startswith(P)
        and "foliage" in obj.name.lower()
        and obj.data == bpy.data.meshes.get("all43_11_light:shared_produce_sphere")
    ]
    if sphere_foliage:
        raise RuntimeError({"new_spherical_foliage": sphere_foliage})
    planter_instances = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(P) and obj.instance_collection == master
    ]
    return {
        "source_revision": "urban_v3_all43_15",
        "glass_blocking_solids_hidden": blockers,
        "storefront_glass_master_objects_updated": glass_objects,
        "storefront_glass_transparent_fraction": glass["transparent_camera_fraction"],
        "glass_visibility_fix": "removed solid recess blockers and applied transparent/physical glass mix",
        "legacy_toy_planter_objects_hidden": len(hidden_planters),
        "realistic_planter_instances": len(planter_instances),
        "planter_master": master.name,
        "planter_geometry": "hollow tapered pot, recessed panels, soil, pebbles, woody stems, side branches, custom leaves",
        "new_spherical_foliage_count": len(sphere_foliage),
        **plant_stats,
    }


def run():
    blockers, glass_objects, glass = fix_storefront_visibility()
    hidden_planters, plant_stats = replace_planters()
    return audit(blockers, glass_objects, hidden_planters, plant_stats, glass)
