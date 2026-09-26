import bpy

for name in [
    "Tree.004",
    "Tree.010",
    "Tree.016",
    "Tree.022",
    "TreeFactory(42).spawn_asset(0)",
    "TreeFactory(137).spawn_asset(0)",
]:
    obj = bpy.data.objects.get(name)
    print("\nOBJ", name, bool(obj), flush=True)
    if not obj:
        continue
    print(
        "modifiers",
        [(m.name, m.type, getattr(m, "show_render", None)) for m in obj.modifiers],
        flush=True,
    )
    for m in obj.modifiers:
        print(" modifier", m.name, m.type, flush=True)
        for attr in ("node_group", "object", "collection", "instance_collection"):
            if hasattr(m, attr):
                val = getattr(m, attr)
                print("  ", attr, getattr(val, "name", val), flush=True)
    print("constraints", [(c.name, c.type) for c in obj.constraints], flush=True)
    print(
        "data attrs",
        list(obj.data.attributes.keys()) if obj.type == "MESH" else [],
        flush=True,
    )
    print(
        "shape keys",
        obj.data.shape_keys.name
        if obj.type == "MESH" and obj.data.shape_keys
        else None,
        flush=True,
    )
