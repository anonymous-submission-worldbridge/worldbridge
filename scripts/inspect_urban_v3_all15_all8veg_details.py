import bpy

names = [
    n
    for n in bpy.data.objects.keys()
    if n.startswith("all8veg_TreeFactory") and "_explicit" not in n
]
names.sort()
print("count", len(names), flush=True)
for name in names[:16]:
    obj = bpy.data.objects[name]
    print(
        name,
        "verts",
        len(obj.data.vertices) if obj.type == "MESH" else None,
        "faces",
        len(obj.data.polygons) if obj.type == "MESH" else None,
        "mats",
        [s.material.name if s.material else None for s in obj.material_slots],
        "children",
        [c.name for c in obj.children],
        "loc",
        tuple(round(v, 2) for v in obj.location),
        flush=True,
    )
