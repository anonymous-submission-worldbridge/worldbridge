import bpy


def main():
    objs = list(bpy.data.objects)
    print("OBJECTS", len(objs), flush=True)
    for pat in [
        "all8veg_TreeFactory",
        "leaf_complex",
        "explicit_leaf_cloud",
        "TreeFactory",
    ]:
        matches = [o for o in objs if pat in o.name]
        print("PAT", pat, "COUNT", len(matches), flush=True)
        for o in matches[:60]:
            data = getattr(o, "data", None)
            verts = (
                len(data.vertices)
                if data is not None and hasattr(data, "vertices")
                else None
            )
            mats = []
            if data is not None and hasattr(data, "materials"):
                mats = [m.name if m else None for m in data.materials[:3]]
            print(
                o.name,
                o.type,
                "hideR",
                o.hide_render,
                "hideV",
                o.hide_viewport,
                "loc",
                tuple(round(v, 2) for v in o.location),
                "dim",
                tuple(round(v, 2) for v in o.dimensions),
                "verts",
                verts,
                "mats",
                mats,
                flush=True,
            )


main()
