"""Compact real-geometry scenes assembled exclusively from authored asset masters.

Run with Blender -b -P this_file -- --scene lemon_coffee (or all).
No mesh primitives, external downloads, decimation, image backdrops or impostors.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
SOURCE = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_25/urban_v3_all43_25.blend"
)
REFERENCE = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_08/urban_v1_full_08.blend"
)
SPECS = {
    "fresh_mart": dict(
        title="fresh food store and garden street",
        master="all43_01:MASTER:convenience_store",
        width=15.45,
        door=0.62,
        front=-4.82,
    ),
    "corner_kitchen": dict(
        title="Community restaurant with outdoor dining area",
        master="all43_01:MASTER:restaurant",
        width=15.45,
        door=5.8,
        front=-4.82,
    ),
    "lemon_coffee": dict(
        title="Coffee shop with a greenery terrace",
        master="LEMON_COFFEE_ROADSIDE_CAFE_MASTER",
        width=8.4,
        door=3.0,
        front=-4.105,
        source_instance="all43_24:north_road_lemon_coffee",
        prefix="all43_24:",
    ),
    "mcdonalds": dict(
        title="Fast food restaurant with shaded courtyard",
        master="MCDONALDS_ROADSIDE_RESTAURANT_MASTER",
        width=16.4,
        door=3.32,
        front=-4.085,
        source_instance="all43_20:north_road_mcdonalds",
        prefix="all43_20:",
    ),
    "copper_tap": dict(
        title="Open-air cocktail bar and street bar counter",
        master="COPPER_TAP_OPEN_BAR_MASTER",
        width=8.0,
        door=-3.17,
        front=-4.105,
        source_instance="all43_25:north_road_copper_tap",
        prefix="all43_25:",
    ),
    "hawthorn": dict(
        title="Copper Bar with Floral Garden",
        master="HAWTHORN_STREET_BAR_MASTER",
        width=8.4,
        door=-3.16,
        front=-4.105,
        source_instance="all43_25:north_road_hawthorn_bar",
        prefix="all43_25:",
    ),
}


def copy_object(obj, collection, matrix=None):
    result = obj.copy()
    result.name = "connect:" + obj.name
    result["asset_source_object"] = obj.name
    result["asset_source_blend"] = str(SOURCE)
    collection.objects.link(result)
    if matrix is not None:
        result.matrix_world = matrix @ obj.matrix_world
    return result


def instance(master, collection, name, loc, rotation=0.0, scale=1.0):
    obj = bpy.data.objects.new(name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = loc
    obj.rotation_euler.z = rotation
    obj.scale = (scale,) * 3
    obj["asset_master"] = master.name
    obj["asset_source_blend"] = str(SOURCE)
    collection.objects.link(obj)
    return obj


def rotate_leaf(objects, pivot, angle):
    transform = (
        Matrix.Translation(Vector(pivot))
        @ Matrix.Rotation(math.radians(angle), 4, "Z")
        @ Matrix.Translation(-Vector(pivot))
    )
    for obj in objects:
        obj.matrix_world = transform @ obj.matrix_world
        obj["connect_door_open_degrees"] = angle


def open_authored_doors(master, key):
    """Articulate existing leaves; never replace detailed door geometry."""
    notes = []
    if key in ("fresh_mart", "corner_kitchen"):
        for inst in list(master.objects):
            if (
                not inst.instance_collection
                or inst.instance_collection.name != "STOREFRONT_DOOR_MASTER"
            ):
                continue
            original = inst.instance_collection
            coll = bpy.data.collections.new("connect:open_door:" + inst.name)
            leaf = []
            for obj in original.objects:
                # This historical solid reveal plate erroneously filled the door aperture.
                if obj.name == "all43_15:door_reveal":
                    notes.append(
                        {
                            "removed_backing_plate": obj.name,
                            "reason": "solid reveal covered entire authored door aperture",
                        }
                    )
                    continue
                new = copy_object(obj, coll)
                if any(
                    t in obj.name
                    for t in (
                        "glass_leaf",
                        "leaf_stile",
                        "leaf_top",
                        "leaf_kick",
                        "door_pull",
                        "hydraulic",
                    )
                ):
                    leaf.append(new)
            rotate_leaf(leaf, (-0.52, -0.22, 0), -100)
            inst.instance_collection = coll
            notes.append({"door": inst.name, "angle": -100, "leaf_parts": len(leaf)})
    elif key == "mcdonalds":
        tower = next(
            o for o in master.objects if o.name == "all43_20:entry_brand_tower"
        )
        tower.dimensions.z = 2.295
        tower.location.z = 4.3075
        notes.append(
            {
                "adjusted_source_fascia": tower.name,
                "reason": "restore door head clearance below brand fascia",
                "clearance_z_m": 3.16,
            }
        )
        inst = next(
            o
            for o in master.objects
            if o.instance_collection
            and "MCD_DOUBLE_ENTRY" in o.instance_collection.name
        )
        coll = bpy.data.collections.new("connect:open_mcd_double_door")
        leafs = {-1: [], 1: []}
        for obj in inst.instance_collection.objects:
            new = copy_object(obj, coll)
            if any(
                t in obj.name
                for t in (
                    "tempered_door",
                    "door_leaf",
                    "door_top",
                    "door_kick",
                    "pull_handle",
                    "hydraulic",
                )
            ):
                # Inner stiles share x=0; suffix preserves the generator's left/right order.
                side = -1 if obj.location.x < -0.001 else 1
                if "door_leaf_stile" in obj.name and abs(obj.location.x) < 0.001:
                    side = -1 if obj.name.endswith(".001") else 1
                leafs[side].append(new)
        for side, parts in leafs.items():
            rotate_leaf(parts, (side * 0.91, -0.10, 0), side * 100)
        inst.instance_collection = coll
        notes.append(
            {
                "door": inst.name,
                "angle": 100,
                "leaf_parts": sum(map(len, leafs.values())),
            }
        )
    else:
        leafs = [
            o
            for o in master.objects
            if any(
                t in o.name
                for t in (
                    "entry_laminated_glass",
                    "entry_door_rail",
                    "entry_pull_handle",
                    "entry_hydraulic_closer",
                )
            )
        ]
        x = SPECS[key]["door"]
        half = (
            0.86 if key == "lemon_coffee" else (0.75 if key == "copper_tap" else 0.79)
        )
        # Hinge toward outside edge of the building, away from the clear centerline.
        side = 1 if x > 0 else -1
        rotate_leaf(leafs, (x + side * half, -4.17, 0), side * 100)
        notes.append({"door": key, "angle": side * 100, "leaf_parts": len(leafs)})
    return notes


def add_area(collection, name, loc, target, power, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )
    return obj


def shots_for(key):
    s = SPECS[key]
    x = s["door"]
    y = s["front"]
    w = s["width"]
    # Each direction has a physically distinct viewpoint in the SAME complete scene.
    shots = {
        "exterior": dict(
            position=(w * 0.52, y - (w * 0.58 + 5.5), 5.0),
            target=(0, y + 1.0, 2.6),
            lens=30,
        ),
        "courtyard": dict(
            position=(w * 0.65 + 7.0, y - 6.8, 9.0), target=(0, y - 6.8, 1.3), lens=27
        ),
        "interior": dict(
            position=(x, y + 1.25, 1.85), target=(-1 if x > 0 else 1, 1.6, 1.5), lens=22
        ),
        "inside_to_outside": dict(
            position=(x, y + 2.0, 1.8), target=(x, y - 5.5, 1.3), lens=22
        ),
        "outside_to_inside": dict(
            position=(x, y - 2.25, 1.8), target=(x * 0.35, 1.6, 1.5), lens=22
        ),
        "detail": dict(position=(0, -0.8, 1.9), target=(0, 2.7, 1.9), lens=42),
    }
    if key == "fresh_mart":
        shots["interior"] = dict(
            position=(0.1, -3.1, 2), target=(-3.2, 1.6, 1.2), lens=23
        )
        shots["detail"] = dict(
            position=(-0.85, 0.2, 1.7), target=(-2.55, 0.4, 1.25), lens=35
        )
    elif key == "corner_kitchen":
        shots["interior"] = dict(
            position=(5.5, -3.5, 1.9), target=(-2.0, 0.2, 1.2), lens=23
        )
        shots["detail"] = dict(
            position=(-0.1, -0.2, 1.75), target=(-3.25, -2.15, 0.95), lens=40
        )
    elif key == "lemon_coffee":
        shots["interior"] = dict(
            position=(3.0, -3.35, 1.85), target=(-1.0, -1.6, 1.5), lens=21
        )
        shots["inside_to_outside"] = dict(
            position=(1.6, -1.2, 1.8), target=(3.0, -9.0, 1.3), lens=21
        )
        shots["detail"] = dict(
            position=(1.25, -1.65, 2.2), target=(-1.0, -2.8, 1.8), lens=38
        )
    elif key == "mcdonalds":
        shots["interior"] = dict(
            position=(3.3, -2.6, 1.9), target=(-2, 0.2, 1.3), lens=23
        )
        shots["detail"] = dict(
            position=(-3.5, -2.6, 1.8), target=(0.5, 1.6, 1.3), lens=32
        )
    else:
        shots["interior"] = dict(
            position=(-3.0, -2.5, 1.85), target=(0.4, 2.1, 1.7), lens=23
        )
        shots["detail"] = dict(
            position=(-1.4, -0.65, 1.8), target=(0.8, 2.9, 2.2), lens=38
        )
    return shots


def build(key):
    spec = SPECS[key]
    dest = OUT / key
    dest.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    old_scene = bpy.context.scene
    source_world = list(old_scene.objects)
    scene = bpy.data.scenes.new("CONNECT_" + key)
    bpy.context.window.scene = scene
    architecture = bpy.data.collections.new("Architecture_and_interior")
    scene.collection.children.link(architecture)
    exterior = bpy.data.collections.new("Detailed_outdoor_assets")
    scene.collection.children.link(exterior)
    lighting = bpy.data.collections.new("Photography_lighting")
    scene.collection.children.link(lighting)
    master = bpy.data.collections[spec["master"]]
    native_path = OUT / "shared_assets/native_indoor_assets.blend"
    if native_path.exists():
        with bpy.data.libraries.load(str(native_path), link=True) as (
            available,
            requested,
        ):
            requested.collections = list(available.collections)
        native_chair = bpy.data.collections.get("NATIVE_ChairFactory")
        if native_chair:
            dining = bpy.data.collections["DINING_CHAIR_MASTER"]
            for old in list(dining.objects):
                dining.objects.unlink(old)
            instance(
                native_chair, dining, "authored_native_dining_chair", (0, 0, 0), 0, 1.0
            )
        table = bpy.data.collections["DINING_TABLE_MASTER"]
        if bpy.data.collections.get("NATIVE_PlateFactory"):
            for x in (-0.27, 0.27):
                instance(
                    bpy.data.collections["NATIVE_PlateFactory"],
                    table,
                    "native_ceramic_plate",
                    (x, 0, 0.81),
                    0,
                    0.78,
                )
                instance(
                    bpy.data.collections["NATIVE_BowlFactory"],
                    table,
                    "native_ceramic_bowl",
                    (x, 0, 0.84),
                    0,
                    0.75,
                )
            instance(
                bpy.data.collections["NATIVE_VaseFactory"],
                table,
                "native_table_vase",
                (0, 0.22, 0.81),
                0,
                0.48,
            )
    # Keep authored mesh data and modifiers; discard only hidden obsolete iterations.
    for obj in list(master.objects):
        if obj.hide_render:
            master.objects.unlink(obj)
    door_notes = open_authored_doors(master, key)
    instance(master, architecture, "authored_complete_" + key, (0, 0, 0))
    if key == "lemon_coffee":
        # Additional authored furniture fills the customer room while keeping
        # the existing entrance, counter work aisle and rear sink reachable.
        for x, y in [(-2.4, 0.0), (0.0, 0.0)]:
            instance(
                bpy.data.collections["DINING_TABLE_MASTER"],
                architecture,
                "additional_library_cafe_table",
                (x, y, 0.26),
                0,
                0.82,
            )
            for dy, angle in [(-0.72, 0), (0.72, math.pi)]:
                instance(
                    bpy.data.collections["DINING_CHAIR_MASTER"],
                    architecture,
                    "additional_library_cafe_chair",
                    (x, y + dy, 0.26),
                    angle,
                    0.82,
                )
    front = spec["front"]
    width = spec["width"]
    # A second existing shop encloses a genuinely three-dimensional, compact
    # pedestrian courtyard; no flat backgrounds or hollow facade proxies.
    opposite_names = {
        "fresh_mart": "LEMON_COFFEE_ROADSIDE_CAFE_MASTER",
        "corner_kitchen": "COPPER_TAP_OPEN_BAR_MASTER",
        "lemon_coffee": "HAWTHORN_STREET_BAR_MASTER",
        "mcdonalds": "LEMON_COFFEE_ROADSIDE_CAFE_MASTER",
        "copper_tap": "LEMON_COFFEE_ROADSIDE_CAFE_MASTER",
        "hawthorn": "LEMON_COFFEE_ROADSIDE_CAFE_MASTER",
    }
    opposite = bpy.data.collections[opposite_names[key]]
    opposite_x = spec["door"] * 0.55
    instance(
        opposite,
        exterior,
        "authored_opposite_courtyard_shop",
        (opposite_x, front - 17.8, 0),
        math.pi,
    )
    if spec.get("source_instance"):
        inverse = bpy.data.objects[spec["source_instance"]].matrix_world.inverted()
        for obj in source_world:
            if (
                obj.hide_render
                or not obj.name.startswith(spec["prefix"])
                or "north_road_" in obj.name
            ):
                continue
            local = inverse @ obj.matrix_world.translation
            if abs(local.x) < width / 2 + 0.12 and -9.0 < local.y < front - 0.12:
                if obj.type == "MESH" and obj.dimensions.x > width + 0.3:
                    continue
                copy_object(obj, exterior, inverse)
    # Reuse the original detailed pavement, including its original shader/bevel.
    paver = copy_object(
        bpy.data.objects["all43_24:cafe_frontage_paver_field"], exterior
    )
    paver.location = (0, front - 7.0, 0.075)
    paver.rotation_euler = (0, 0, 0)
    paver.dimensions = (width + 9.0, 14.0, 0.12)
    # Keep paving seams as source components, repeated at architectural spacing.
    seams = [
        o for o in source_world if o.name.startswith("all43_24:") and "joint" in o.name
    ]
    if seams:
        for i in range(-int(width / 2) - 4, int(width / 2) + 5):
            seam = copy_object(seams[0], exterior)
            seam.rotation_euler = (0, 0, 0)
            seam.location = (i, front - 7.0, 0.138)
            seam.dimensions = (0.012, 13.9, 0.006)
    bed = bpy.data.collections["COMPLEX_REAR_FLOWERBED_MASTER"]
    for xx in (-width / 2 - 2.0, width / 2 + 2.0):
        instance(
            bed,
            exterior,
            "authored_flowerbed",
            (xx, front - 4.0, 0.14),
            math.pi / 2,
            0.8,
        )
    # The street-facing view is enclosed by actual 3D vegetation and furniture.
    for xx in (-width * 0.38, width * 0.38):
        instance(
            bed,
            exterior,
            "authored_forecourt_flowerbed",
            (xx, front - 8.0, 0.14),
            0,
            0.85,
        )
    for xx in (opposite_x - 2.3, opposite_x + 2.3):
        instance(
            bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"],
            exterior,
            "opposite_authored_terrace_seating",
            (xx, front - 11.8, 0.14),
            math.pi,
        )
        instance(
            bpy.data.collections["REFINED_COMMERCIAL_PLANTER_MASTER"],
            exterior,
            "opposite_authored_planter",
            (xx, front - 13.3, 0.14),
            0,
            0.8,
        )
    for xx, yy, angle in [
        (-width * 0.27, front - 5.2, 0.25),
        (width * 0.26, front - 8.9, -0.35),
    ]:
        instance(
            bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"],
            exterior,
            "courtyard_authored_seating_group",
            (xx, yy, 0.14),
            angle,
        )
    if key in ("fresh_mart", "corner_kitchen"):
        for xx in (-width * 0.25, width * 0.23):
            if abs(xx - spec["door"]) < 1.5:
                continue
            instance(
                bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"],
                exterior,
                "authored_patio_setting",
                (xx, front - 2.4, 0.14),
                0.2,
            )
    elif key in ("copper_tap", "hawthorn"):
        instance(
            bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"],
            exterior,
            "authored_patio_setting",
            (1.3, front - 2.2, 0.14),
            -0.2,
        )
    bike = bpy.data.collections["SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER"]
    instance(
        bike,
        exterior,
        "authored_detailed_bicycle",
        (width / 2 + 1.7, front - 6.5, 0.14),
        math.pi / 2,
    )
    # Append mature Infinigen foliage from the user's nominated reference scene.
    tree_name = "full02:MASTER:TreeFactory:42"
    shared_tree = OUT / "shared_assets/reference08_tree.blend"
    tree_source = shared_tree if shared_tree.exists() else REFERENCE
    with bpy.data.libraries.load(str(tree_source), link=shared_tree.exists()) as (
        available,
        requested,
    ):
        requested.collections = [tree_name]
    tree = requested.collections[0]
    for i, (xx, yy, scale) in enumerate(
        [
            (-width / 2 - 2.5, 1.0, 0.66),
            (width / 2 + 2.5, 1.5, 0.7),
            (-width / 2 - 4.0, front - 9.5, 0.65),
            (width / 2 + 4.0, front - 9.5, 0.62),
        ]
    ):
        obj = instance(
            tree,
            exterior,
            "reference08_mature_tree_" + str(i),
            (xx, yy, 0.1),
            i * 1.17,
            scale,
        )
        obj["asset_source_blend"] = str(REFERENCE)
    for i, yy in enumerate((front - 1.0, front - 4.5, front - 13.8, front - 17.5)):
        obj = instance(
            tree,
            exterior,
            "reference08_courtyard_boundary_tree_" + str(i),
            (-width / 2 - 4.4, yy, 0.1),
            0.63 + i * 1.7,
            0.68 + (i % 2) * 0.08,
        )
        obj["asset_source_blend"] = str(REFERENCE)
    # A larger piece of the existing asphalt supports the compact site; it is
    # not a new proxy for any scene object and is never used as an image plane.
    base = copy_object(
        bpy.data.objects["all43_20:relocated_rear_parking_asphalt"], exterior
    )
    base.location = (0, -8.0, -0.04)
    base.rotation_euler = (0, 0, 0)
    base.dimensions = (width + 25.0, 38.0, 0.1)
    scene.world = old_scene.world.copy()
    scene.world.use_nodes = True
    bg = next((n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        sky = next(
            (n for n in scene.world.node_tree.nodes if n.type == "TEX_SKY"), None
        )
        if sky:
            sky.sun_disc = False
            bg.inputs["Strength"].default_value = 0.07
        else:
            bg.inputs["Color"].default_value = (0.63, 0.73, 0.88, 1)
            bg.inputs["Strength"].default_value = 0.4
    for obj in source_world:
        if obj.type == "LIGHT" and obj.data.type == "SUN":
            sun = copy_object(obj, lighting)
            sun.data = obj.data.copy()
            sun.data.energy = 2.0
            sun.data.angle = math.radians(12)
            sun.rotation_euler = (
                math.radians(28),
                math.radians(-25),
                math.radians(-30),
            )
    add_area(
        lighting,
        "soft_front_daylight",
        (1, front - 5, 8),
        (0, 0, 1),
        700,
        8,
        (0.82, 0.9, 1),
    )
    add_area(
        lighting, "interior_bounce", (-1, 0, 3.2), (0, -3, 1), 95, 4, (1, 0.88, 0.73)
    )
    # Fixture power is adapted to a small room, preserving every authored lamp.
    for obj in master.objects:
        if obj.type == "LIGHT":
            obj.data = obj.data.copy()
            obj.data.energy *= 0.55
    # Neutral optical glazing, retaining the source glass geometry.
    for mat in bpy.data.materials:
        if mat.use_nodes and any(
            t in mat.name.lower()
            for t in (
                "laminated_glass",
                "clear_glass",
                "storefront_glass",
                "tempered_glass",
            )
        ):
            node = mat.node_tree.nodes.get("Principled BSDF")
            if node:
                node.inputs["Base Color"].default_value = (0.92, 0.97, 0.98, 1)
                node.inputs["Transmission Weight"].default_value = 1.0
                node.inputs["Roughness"].default_value = 0.055
    camera_data = bpy.data.cameras.new("Presentation_Camera")
    camera = bpy.data.objects.new("Presentation_Camera", camera_data)
    lighting.objects.link(camera)
    scene.camera = camera
    camera.data.clip_start = 0.05
    camera.data.clip_end = 200
    shots = shots_for(key)
    shot = shots["exterior"]
    camera.location = shot["position"]
    camera.rotation_euler = (
        (Vector(shot["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = shot["lens"]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 8
    scene.cycles.transparent_max_bounces = 12
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.25
    scene.render.film_transparent = False
    scene.render.fps = 24
    bpy.context.preferences.filepaths.save_version = 0
    for s in list(bpy.data.scenes):
        if s != scene:
            bpy.data.scenes.remove(s)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated_meshes = 0
    vertices = 0
    polygons = 0
    for inst in deps.object_instances:
        if inst.object.type == "MESH" and not inst.object.hide_render:
            evaluated_meshes += 1
            vertices += len(inst.object.data.vertices)
            polygons += len(inst.object.data.polygons)
    # Central line of sight through the open door, tested at human eye level.
    origin = Vector((spec["door"], front - 1.8, 1.8))
    direction = Vector((0, 1, 0))
    hit, loc, normal, index, obj, matrix = scene.ray_cast(
        deps, origin, direction, distance=3.2
    )
    portal = {
        "origin": list(origin),
        "direction": list(direction),
        "distance_m": 3.2,
        "clear": not hit,
        "first_hit": obj.name if hit else None,
        "hit_location": list(loc) if hit else None,
    }
    manifest = {
        "scene": key,
        "title": spec["title"],
        "source_blend": str(SOURCE),
        "reference_blend": str(REFERENCE),
        "reused_existing_complete_interior": True,
        "new_mesh_primitives": 0,
        "geometry_decimation": False,
        "master": spec["master"],
        "floorplan_width_m": width,
        "front_y": front,
        "door_x": spec["door"],
        "door_articulation": door_notes,
        "portal_eye_ray": portal,
        "evaluated_mesh_instances": evaluated_meshes,
        "evaluated_vertices": vertices,
        "evaluated_polygons": polygons,
        "shots": shots,
        "blend": str(dest / "scene.blend"),
    }
    (dest / "scene_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
    # Keep the complete deliverable folder movable as a unit.
    for library in bpy.data.libraries:
        library.filepath = "//" + os.path.relpath(
            bpy.path.abspath(library.filepath), dest
        )
    bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
    print("CONNECT_BUILT " + json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="all", choices=["all"] + list(SPECS))
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    for name in SPECS if args.scene == "all" else [args.scene]:
        build(name)
