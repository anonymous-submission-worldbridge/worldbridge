from __future__ import annotations

from collections import Counter

import bpy


def recursive_collections(root):
    pending = [root]
    seen = set()
    while pending:
        collection = pending.pop()
        if collection in seen:
            continue
        seen.add(collection)
        yield collection
        pending.extend(collection.children)


for collection in sorted(bpy.data.collections, key=lambda item: item.name):
    if collection.name not in {
        "delivery:FOOD_DELIVERY_LOCKER",
        "delivery:PARCEL_LOCKER",
        "delivery:DELIVERY_STATION",
    }:
        continue
    nested = list(recursive_collections(collection))
    objects = {obj for child in nested for obj in child.objects}
    meshes = [obj for obj in objects if obj.type == "MESH" and obj.data is not None]
    modifiers = Counter(mod.type for obj in objects for mod in obj.modifiers)
    vertex_count = sum(len(obj.data.vertices) for obj in meshes)
    polygon_count = sum(len(obj.data.polygons) for obj in meshes)
    outside_parents = sum(
        1 for obj in objects if obj.parent and obj.parent not in objects
    )
    collection_instances = [
        obj
        for obj in objects
        if obj.type == "EMPTY" and obj.instance_type == "COLLECTION"
    ]
    multi_collection = sum(1 for obj in objects if len(obj.users_collection) > 1)
    print(
        "C2W_DELIVERY_COLLECTION",
        collection.name,
        f"nested_collections={len(nested)}",
        f"objects={len(objects)}",
        f"meshes={len(meshes)}",
        f"vertices={vertex_count}",
        f"polygons={polygon_count}",
        f"outside_parents={outside_parents}",
        f"collection_instances={len(collection_instances)}",
        f"multi_collection={multi_collection}",
        f"modifiers={dict(modifiers)}",
    )
    for instancer in collection_instances[:20]:
        target = instancer.instance_collection
        print(
            "C2W_DELIVERY_INSTANCE",
            collection.name,
            instancer.name,
            target.name if target else None,
        )
    for obj in sorted(objects, key=lambda item: item.name):
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            group = modifier.node_group
            referenced = []
            if group is not None:
                for node in group.nodes:
                    for attr in ("collection", "object"):
                        value = getattr(node, attr, None)
                        if value is not None:
                            referenced.append(f"{node.bl_idname}.{attr}={value.name}")
            print(
                "C2W_DELIVERY_GEOMETRY_NODES",
                collection.name,
                f"object={obj.name}",
                f"object_hide_render={obj.hide_render}",
                f"modifier={modifier.name}",
                f"modifier_show_render={modifier.show_render}",
                f"group={group.name if group else None}",
                f"references={referenced}",
            )
            original_show_render = modifier.show_render
            try:
                modifier.show_render = False
                writable = modifier.show_render is False
            except (
                Exception
            ) as error:  # Blender reports linked-ID write restrictions here.
                writable = False
                print("C2W_DELIVERY_MODIFIER_WRITE_ERROR", repr(error))
            finally:
                if writable:
                    modifier.show_render = original_show_render
            print(
                "C2W_DELIVERY_LINK_STATUS",
                f"object_library={obj.library.filepath if obj.library else None}",
                f"modifier_runtime_writable={writable}",
            )
