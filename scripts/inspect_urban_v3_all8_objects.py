import bpy
from mathutils import Vector


def bbox(obj):
    if not getattr(obj, "bound_box", None):
        return None
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mins = tuple(round(min(p[i] for p in pts), 2) for i in range(3))
    maxs = tuple(round(max(p[i] for p in pts), 2) for i in range(3))
    center = tuple(round((mins[i] + maxs[i]) / 2, 2) for i in range(3))
    dims = tuple(round(maxs[i] - mins[i], 2) for i in range(3))
    return mins, maxs, center, dims


def mats(obj):
    return [slot.material.name for slot in obj.material_slots if slot.material]


for coll_name in ("Park", "Trees", "FlowerBeds"):
    coll = bpy.data.collections.get(coll_name)
    print("\nCOLL", coll_name, "exists", bool(coll), flush=True)
    if not coll:
        continue
    objs = sorted(coll.objects, key=lambda o: o.name)
    print("count", len(objs), flush=True)
    for o in objs[:220]:
        print(
            o.name,
            o.type,
            "loc",
            tuple(round(v, 2) for v in o.location),
            "bbox",
            bbox(o),
            "mats",
            mats(o)[:4],
            flush=True,
        )
