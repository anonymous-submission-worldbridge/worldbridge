import mathutils
import bpy


def world_bbox(obj):
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    mn = mathutils.Vector(
        (
            min(v.x for v in corners),
            min(v.y for v in corners),
            min(v.z for v in corners),
        )
    )
    mx = mathutils.Vector(
        (
            max(v.x for v in corners),
            max(v.y for v in corners),
            max(v.z for v in corners),
        )
    )
    return mn, mx, (mn + mx) * 0.5


for name in sorted(o.name for o in bpy.data.objects if "all8veg_TreeFactory" in o.name):
    o = bpy.data.objects[name]
    mn, mx, cen = world_bbox(o)
    print(
        name,
        "loc",
        tuple(round(v, 2) for v in o.location),
        "min",
        tuple(round(v, 2) for v in mn),
        "max",
        tuple(round(v, 2) for v in mx),
        "center",
        tuple(round(v, 2) for v in cen),
        flush=True,
    )

print("leaf_complex samples", flush=True)
for name in sorted(o.name for o in bpy.data.objects if "leaf_complex" in o.name)[:20]:
    o = bpy.data.objects[name]
    mn, mx, cen = world_bbox(o)
    print(
        name,
        "min",
        tuple(round(v, 2) for v in mn),
        "max",
        tuple(round(v, 2) for v in mx),
        "center",
        tuple(round(v, 2) for v in cen),
        flush=True,
    )
