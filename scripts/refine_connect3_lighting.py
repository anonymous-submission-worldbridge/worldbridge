"""Place practical illumination below ceilings in the actual occupied entrance rooms."""
import bpy, sys, json
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"


def correct(m):
    if (
        m.get("focus_lighting_corrected")
        or m.get("reception_lighting_corrected")
        or m["focus"] not in {"library", "hospital"}
    ):
        return
    s = bpy.context.scene
    c = bpy.data.collections["Physical_lighting_and_cameras"]
    dg = bpy.context.evaluated_depsgraph_get()
    for x in [-3, 3]:
        for y in [3, 6.5]:
            hit, loc, n, face, obj, matrix = s.ray_cast(
                dg, Vector((x, y, m["floor_z"] + 0.2)), Vector((0, 0, 1)), distance=6
            )
            z = min(3.1, loc.z - 0.1) if hit else 3.1
            data = bpy.data.lights.new("Occupied room practical", "AREA")
            data.energy = 100
            data.shape = "DISK"
            data.size = 2
            data.color = (1, 0.94, 0.86)
            ob = bpy.data.objects.new(data.name, data)
            c.objects.link(ob)
            ob.location = (x, y, z)
    m["focus_lighting_corrected"] = True


if __name__ == "__main__":
    d = O / sys.argv[-1]
    m = json.loads((d / "scene_manifest.json").read_text())
    bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
    correct(m)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
    (d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
