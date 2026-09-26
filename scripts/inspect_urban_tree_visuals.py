import bpy
from collections import Counter, defaultdict


def world_bbox(obj):
    if not getattr(obj, "bound_box", None):
        return None
    pts = [obj.matrix_world @ __import__("mathutils").Vector(c) for c in obj.bound_box]
    mins = tuple(min(p[i] for p in pts) for i in range(3))
    maxs = tuple(max(p[i] for p in pts) for i in range(3))
    center = tuple((mins[i] + maxs[i]) / 2 for i in range(3))
    dims = tuple(maxs[i] - mins[i] for i in range(3))
    return mins, maxs, center, dims


def is_leafish(obj):
    n = obj.name.lower()
    mats = " ".join(
        slot.material.name.lower() for slot in obj.material_slots if slot.material
    )
    return any(
        k in n or k in mats
        for k in ("leaf", "leaves", "foliage", "grass", "flower", "shrub", "tree")
    )


def is_treeish(obj):
    n = obj.name.lower()
    mats = " ".join(
        slot.material.name.lower() for slot in obj.material_slots if slot.material
    )
    return any(
        k in n or k in mats
        for k in ("tree", "trunk", "bark", "leaf", "leaves", "foliage")
    )


objs = list(bpy.data.objects)
print("FILE", bpy.data.filepath, flush=True)
print(
    "objects", len(objs), "meshes", sum(1 for o in objs if o.type == "MESH"), flush=True
)

coll_counts = Counter()
for o in objs:
    if is_leafish(o) or is_treeish(o):
        for c in o.users_collection:
            coll_counts[c.name] += 1
print("vegetation collections")
for name, count in coll_counts.most_common(30):
    print(count, name, flush=True)

name_counts = Counter()
for o in objs:
    n = o.name.lower()
    if "treefactory" in n:
        name_counts["treefactory"] += 1
    if "explicit_leaf_cloud" in n:
        name_counts["explicit_leaf_cloud"] += 1
    if "leaf_complex" in n:
        name_counts["leaf_complex"] += 1
    if "shr" in n or "shrub" in n:
        name_counts["shrub"] += 1
    if "flower" in n:
        name_counts["flower"] += 1
    if "grass" in n:
        name_counts["grass"] += 1
print("name counts", dict(name_counts), flush=True)

samples = []
for o in objs:
    if o.type == "MESH" and (
        "explicit_leaf_cloud" in o.name or "leaf_complex" in o.name
    ):
        bb = world_bbox(o)
        if bb:
            samples.append(
                (
                    o.name,
                    bb[2],
                    bb[3],
                    len(o.data.vertices),
                    len(o.data.polygons),
                    [slot.material.name for slot in o.material_slots if slot.material],
                )
            )
samples.sort()
print("leaf samples")
for row in samples[:80]:
    print(row, flush=True)

by_mesh = defaultdict(int)
for o in objs:
    if o.type == "MESH" and is_treeish(o):
        by_mesh[o.data.name] += 1
print(
    "reused tree meshes", sorted(by_mesh.items(), key=lambda x: -x[1])[:40], flush=True
)
