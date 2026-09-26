import argparse
from pathlib import Path

import bpy


TREE_PREFIXES = (
    "urban:nature_tree:",
    "urban:nature_bush:",
    "urban:tree:",
    "urban:shrub:",
)

ASSET_NAME_MARKERS = (
    "GenericTreeFactory",
    "TreeFactory",
    "BushFactory",
    "LeafFactory",
    "TreeFlowerFactory",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    argv = []
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    return parser.parse_args(argv)


def is_current_tree_object(obj):
    name = obj.name
    return name.startswith(TREE_PREFIXES) or any(marker in name for marker in ASSET_NAME_MARKERS)


def is_source_visible_tree_name(name):
    return name.startswith(("urban:nature_tree:", "urban:nature_bush:"))


def remove_current_tree_objects():
    removed = 0
    for obj in list(bpy.data.objects):
        if is_current_tree_object(obj):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for curve in list(bpy.data.curves):
        if curve.users == 0:
            bpy.data.curves.remove(curve)
    return removed


def append_source_trees(source):
    with bpy.data.libraries.load(str(source), link=False) as (data_from, data_to):
        names = [name for name in data_from.objects if is_source_visible_tree_name(name)]
        data_to.objects = names
    collection = bpy.data.collections.get("urban_tree_style_from_block_10")
    if collection is None:
        collection = bpy.data.collections.new("urban_tree_style_from_block_10")
        bpy.context.scene.collection.children.link(collection)
    appended = 0
    for obj in data_to.objects:
        if obj is None:
            continue
        if not obj.users_collection:
            collection.objects.link(obj)
        else:
            for col in list(obj.users_collection):
                if col != collection:
                    col.objects.unlink(obj)
            if obj.name not in collection.objects:
                collection.objects.link(obj)
        obj.hide_viewport = False
        obj.hide_render = False
        appended += 1
    return appended


def main():
    args = parse_args()
    removed = remove_current_tree_objects()
    appended = append_source_trees(args.source)
    print(f"[tree-replace] removed={removed} appended={appended} source={args.source}")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))


if __name__ == "__main__":
    main()
