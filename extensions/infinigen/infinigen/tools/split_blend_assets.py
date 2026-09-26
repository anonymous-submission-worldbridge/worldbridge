# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory of this source tree.

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import bpy

logger = logging.getLogger(__name__)


def parse_blender_args(parser):
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def safe_blend_stem(name):
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip().lower())
    return stem.strip("._") or "assets"


def urban_linked_asset_group(obj):
    if obj.type in {"CAMERA", "LIGHT"} or obj.library is not None:
        return None
    if obj.name.startswith("Tree.") or any(
        token in obj.name
        for token in [
            "LeafFactory",
            "GenericTreeFactory",
            "BranchFactory",
            "TreeFlowerFactory",
        ]
    ):
        return "vegetation"
    if not obj.name.startswith("urban:"):
        return None

    token = obj.name.split(":", 2)[1]
    if token in {
        "road",
        "sidewalk",
        "sidewalk_joint",
        "lawn",
        "curb",
        "curb_ramp",
        "crosswalk",
        "lane_marking",
        "stop_line",
        "asphalt_patch",
        "road_stain",
        "road_crack",
        "manhole",
        "tactile_paving",
        "bollard",
        "storm_drain",
    }:
        return "base_road_sidewalk"
    if token == "surface":
        return "surface_micro_details"
    if token in {
        "building",
        "window",
        "window_frame",
        "window_ac",
        "window_ac_vent",
        "window_stain",
        "door",
        "door_frame",
        "entrance_step",
        "storefront_sign",
        "storefront_sign_glyph",
        "awning",
        "facade_ledge",
        "facade_vertical_trim",
        "facade_cable",
        "facade_stain",
        "downspout",
        "graffiti",
        "rooftop_vent",
        "rooftop_vent_cap",
        "rooftop_hvac",
        "rooftop_hvac_grille",
    }:
        return "buildings_facades"
    if token in {
        "tree",
        "nature_tree",
        "nature_tree_prototype",
        "nature_bush",
        "nature_grass_tuft",
        "nature_flowerplant",
        "grass_blades",
        "grass_seed_stems",
        "grass_seed_head",
        "grass_litter_leaf",
        "shrub",
        "fallback_flowerplant",
    }:
        return "vegetation"
    if token in {
        "street_lamp",
        "bus_stop",
        "bike_rack",
        "fire_hydrant",
        "bench",
        "trash_bin",
        "planter",
        "traffic_sign",
    }:
        return "street_furniture"
    if token == "traffic_light":
        return "traffic_signals"
    if token == "vehicle":
        return "vehicles"
    if token == "pedestrian":
        return "pedestrians"
    if token in {"fountain", "sculpture"}:
        return "public_space"
    return "urban_misc"


def colon_prefix_linked_asset_group(obj):
    if obj.type in {"CAMERA", "LIGHT"} or obj.library is not None:
        return None
    parts = obj.name.split(":")
    if len(parts) >= 2:
        return safe_blend_stem(parts[1])
    return "scene_objects"


def linked_asset_grouper(grouping):
    if grouping == "urban":
        return urban_linked_asset_group
    if grouping == "colon_prefix":
        return colon_prefix_linked_asset_group
    raise ValueError(f"Unknown grouping {grouping!r}")


def relpath(path, parent):
    try:
        return str(path.relative_to(parent))
    except ValueError:
        return str(path)


def snapshot_scene_settings():
    scene = bpy.context.scene
    world = scene.world
    view = scene.view_settings
    return {
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "camera": scene.camera.name if scene.camera is not None else None,
        "world_color": tuple(world.color) if world is not None else None,
        "view_transform": view.view_transform,
        "look": view.look,
        "exposure": view.exposure,
        "gamma": view.gamma,
    }


def restore_scene_settings(settings):
    scene = bpy.context.scene
    scene.frame_start = settings["frame_start"]
    scene.frame_end = settings["frame_end"]
    scene.frame_set(settings["frame_current"])
    scene.render.fps = settings["fps"]
    scene.render.resolution_x = settings["resolution_x"]
    scene.render.resolution_y = settings["resolution_y"]

    if settings["world_color"] is not None:
        world = bpy.data.worlds.new("World")
        scene.world = world
        world.color = settings["world_color"]

    view = scene.view_settings
    for key in ["view_transform", "look", "exposure", "gamma"]:
        try:
            setattr(view, key, settings[key])
        except TypeError:
            logger.info("Skipping unsupported view setting %s=%s", key, settings[key])


def write_collection_library(asset_dir, group_name, objects, output_parent, compress=True):
    collection_name = f"linked_assets:{group_name}"
    collection = bpy.data.collections.new(collection_name)
    for obj in objects:
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)

    lib_path = asset_dir / f"{safe_blend_stem(group_name)}.blend"
    bpy.data.libraries.write(
        str(lib_path),
        {collection},
        fake_user=True,
        compress=compress,
        path_remap="RELATIVE_ALL",
    )
    bpy.data.collections.remove(collection, do_unlink=True)
    return {
        "group": group_name,
        "file": relpath(lib_path, output_parent),
        "collection": collection_name,
        "object_count": len(objects),
    }


def rebuild_clean_main(output_blend, manifest, settings):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    restore_scene_settings(settings)

    for entry in manifest["libraries"]:
        lib_path = output_blend.parent / entry["file"]
        with bpy.data.libraries.load(str(lib_path), link=True, relative=True) as (
            _data_from,
            data_to,
        ):
            data_to.collections = [entry["collection"]]
        collection = data_to.collections[0]
        if bpy.context.scene.collection.children.get(collection.name) is None:
            bpy.context.scene.collection.children.link(collection)

    camera_name = settings.get("camera")
    if camera_name is not None and bpy.data.objects.get(camera_name) is not None:
        bpy.context.scene.camera = bpy.data.objects[camera_name]

    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))


def split_blend(input_blend, output_blend, asset_dir, grouping, keep_unmatched_objects):
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Opening %s", input_blend)
    bpy.ops.wm.open_mainfile(filepath=str(input_blend))
    settings = snapshot_scene_settings()

    group_for_obj = linked_asset_grouper(grouping)
    groups = {}
    core_objects = []
    skipped_unmatched = []
    for obj in list(bpy.context.scene.objects):
        group = group_for_obj(obj)
        if group is None:
            if keep_unmatched_objects or obj.type in {"CAMERA", "LIGHT", "EMPTY"}:
                core_objects.append(obj)
            else:
                skipped_unmatched.append(obj.name)
        else:
            groups.setdefault(group, []).append(obj)

    manifest = {
        "main_blend": output_blend.name,
        "asset_dir": relpath(asset_dir, output_blend.parent),
        "grouping": grouping,
        "clean_rebuild": True,
        "keep_unmatched_objects": keep_unmatched_objects,
        "skipped_unmatched_objects": skipped_unmatched,
        "libraries": [],
    }

    if core_objects:
        manifest["libraries"].append(
            write_collection_library(
                asset_dir,
                "_scene_core",
                core_objects,
                output_blend.parent,
            )
        )

    for group_name, objects in sorted(groups.items()):
        manifest["libraries"].append(
            write_collection_library(
                asset_dir,
                group_name,
                objects,
                output_blend.parent,
            )
        )

    manifest_path = output_blend.parent / "linked_assets_manifest.json"
    with manifest_path.open("w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(
        "Rebuilding clean main blend with %d linked libraries",
        len(manifest["libraries"]),
    )
    rebuild_clean_main(output_blend, manifest, settings)
    logger.info("Wrote %s", output_blend)
    logger.info("Wrote %s", manifest_path)


def main(args):
    input_blend = Path(args.input_blend).resolve()
    if args.output_blend is None:
        output_blend = input_blend.with_name(f"{input_blend.stem}_linked.blend")
    else:
        output_blend = Path(args.output_blend).resolve()
    asset_dir = (
        Path(args.asset_dir).resolve()
        if args.asset_dir is not None
        else output_blend.parent / "linked_assets"
    )
    split_blend(
        input_blend,
        output_blend,
        asset_dir,
        args.grouping,
        args.keep_unmatched_objects,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_blend", type=Path)
    parser.add_argument("--output_blend", type=Path, default=None)
    parser.add_argument("--asset_dir", type=Path, default=None)
    parser.add_argument(
        "--grouping",
        choices=["urban", "colon_prefix"],
        default="urban",
        help="Object grouping strategy used when writing linked asset blend libraries.",
    )
    parser.add_argument(
        "--keep_unmatched_objects",
        action="store_true",
        help="Keep non-grouped mesh/curve objects in the scene core library. By default only cameras, lights, and empties are kept.",
    )
    args = parse_blender_args(parser)
    logging.basicConfig(
        format="[%(asctime)s.%(msecs)03d] [%(module)s] [%(levelname)s] | %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    main(args)
