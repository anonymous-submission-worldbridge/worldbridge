import bpy
from mathutils import Vector


def bbox(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mins = tuple(round(min(p[i] for p in pts), 3) for i in range(3))
    maxs = tuple(round(max(p[i] for p in pts), 3) for i in range(3))
    center = tuple(round((mins[i] + maxs[i]) / 2, 3) for i in range(3))
    dims = tuple(round(maxs[i] - mins[i], 3) for i in range(3))
    return mins, maxs, center, dims


names = [
    "Tree.004",
    "Tree.010",
    "Tree.016",
    "Tree.022",
    "Tree.028",
    "Tree.034",
    "Tree.040",
    "Tree.046",
    "TreeFactory(42).spawn_asset(0)",
    "TreeFactory(137).spawn_asset(0)",
]

for name in names:
    obj = bpy.data.objects.get(name)
    print("\nOBJ", name, "exists", bool(obj), flush=True)
    if not obj:
        continue
    print(
        "type",
        obj.type,
        "display",
        obj.display_type,
        "hide_render",
        obj.hide_render,
        "hide_viewport",
        obj.hide_viewport,
        flush=True,
    )
    print(
        "loc",
        tuple(round(v, 3) for v in obj.location),
        "rot",
        tuple(round(v, 3) for v in obj.rotation_euler),
        "scale",
        tuple(round(v, 3) for v in obj.scale),
        flush=True,
    )
    print("bbox", bbox(obj), flush=True)
    print(
        "data",
        obj.data.name if obj.data else None,
        "verts",
        len(obj.data.vertices) if obj.type == "MESH" else None,
        "faces",
        len(obj.data.polygons) if obj.type == "MESH" else None,
        flush=True,
    )
    print(
        "materials",
        [slot.material.name if slot.material else None for slot in obj.material_slots],
        flush=True,
    )
    print("users_collection", [c.name for c in obj.users_collection], flush=True)
    print("children", [ch.name for ch in obj.children], flush=True)
    print(
        "instance_type",
        obj.instance_type,
        "instance_collection",
        obj.instance_collection.name if obj.instance_collection else None,
        flush=True,
    )

print("\nTREE-LIKE LOW MATERIAL OBJECTS", flush=True)
for obj in sorted(bpy.data.objects, key=lambda o: o.name):
    if obj.type == "MESH" and obj.name.startswith("Tree."):
        print(
            obj.name,
            "bbox",
            bbox(obj),
            "verts",
            len(obj.data.vertices),
            "faces",
            len(obj.data.polygons),
            "mats",
            [
                slot.material.name if slot.material else None
                for slot in obj.material_slots
            ],
            flush=True,
        )
