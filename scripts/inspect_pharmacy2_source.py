import bpy, json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
bpy.ops.wm.open_mainfile(filepath=str(O / "pharmacy/scene.blend"), load_ui=False)
c = bpy.data.collections["Architecture_and_furnished_interior"]
rows = []
for o in c.objects:
    if ":well_" not in o.name:
        continue
    rows.append(
        {
            "name": o.name,
            "type": o.type,
            "loc": list(o.location),
            "dim": list(o.dimensions),
            "rot": list(o.rotation_euler),
            "scale": list(o.scale),
            "matrix": [list(x) for x in o.matrix_world],
            "mesh": o.data.name if o.data else None,
            "attrs": {k: str(o[k]) for k in o.keys()},
            "materials": [
                s.material.name if s.material else None for s in o.material_slots
            ],
        }
    )
(O / "pharmacy2").mkdir(exist_ok=True)
(O / "pharmacy2/logs").mkdir(exist_ok=True)
(O / "pharmacy2/logs/source_objects.json").write_text(json.dumps(rows, indent=2))
print("SOURCE_OBJECTS", len(rows), flush=True)
