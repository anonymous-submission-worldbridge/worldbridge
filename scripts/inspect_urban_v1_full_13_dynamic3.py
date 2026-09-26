"""Read-only inspection of dynamic2 scene state without evaluating geometry."""
import json
import bpy


def obj(o):
    return {
        "name": o.name,
        "type": o.type,
        "role": o.get("dynamic2_role"),
        "semantic": o.get("urban_semantic"),
        "location": list(o.location),
        "modifiers": [
            (
                m.name,
                m.node_group.name if m.type == "NODES" and m.node_group else m.type,
            )
            for m in o.modifiers
        ],
        "materials": [
            s.material.name if s.material else None for s in o.material_slots
        ],
    }


print(
    "DYN3_INSPECT",
    json.dumps(
        {
            "scenes": [
                {
                    "name": s.name,
                    "objects": len(s.objects),
                    "world": s.world.name if s.world else None,
                }
                for s in bpy.data.scenes
            ],
            "cameras": [
                {
                    "name": o.name,
                    "location": list(o.location),
                    "rotation": list(o.rotation_euler),
                    "lens": o.data.lens,
                }
                for o in bpy.data.objects
                if o.type == "CAMERA" and "DYN2" in o.name
            ],
            "water": [
                obj(o)
                for o in bpy.data.objects
                if o.get("dynamic2_role") in ("river_surface", "lake_surface")
            ],
            "roots": [
                {
                    "name": o.name,
                    "placement": o.get("placement_id"),
                    "location": list(o.location),
                }
                for o in bpy.data.objects
                if o.get("placement_id")
                and any(
                    x in o.get("placement_id", "")
                    for x in ("lake", "river", "fountain")
                )
            ],
            "world_nodes": [
                (
                    w.name,
                    [(n.name, n.bl_idname) for n in w.node_tree.nodes]
                    if w.use_nodes
                    else [],
                )
                for w in bpy.data.worlds
            ],
        },
        indent=2,
    ),
    flush=True,
)
