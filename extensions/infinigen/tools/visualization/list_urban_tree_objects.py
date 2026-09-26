import bpy


for obj in bpy.data.objects:
    name = obj.name
    if (
        name.startswith("urban:nature_tree:")
        or name.startswith("urban:tree:")
        or name.startswith("urban:nature_bush:")
        or name.startswith("urban:shrub:")
        or "TreeFactory" in name
        or "BushFactory" in name
    ):
        mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
        verts = len(mesh.vertices) if mesh is not None else 0
        faces = len(mesh.polygons) if mesh is not None else 0
        print(f"{obj.type}\t{name}\tverts={verts}\tfaces={faces}\thidden={obj.hide_render}")
