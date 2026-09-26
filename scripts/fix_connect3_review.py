# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]

import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector

R = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(R / "scripts"))
from fix_connect3_fonts import fix

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
k = sys.argv[-1]
d = O / k
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
m = json.loads((d / "scene_manifest.json").read_text())
s = bpy.context.scene
if k == "coffee_corner" and not m.get("locker_facing_corrected"):
    for ob in s.objects:
        if ob.instance_collection and ob.instance_collection.name == "ASSET_parcel":
            ob.rotation_euler.z += math.pi
    m["locker_facing_corrected"] = True
if k == "medical_court" and not m.get("reception_lighting_corrected"):
    c = bpy.data.collections["Physical_lighting_and_cameras"]
    dg = bpy.context.evaluated_depsgraph_get()
    for x in [-3, 3]:
        for y in [3, 6.5]:
            hit, loc, n, face, obj, matrix = s.ray_cast(
                dg, Vector((x, y, m["floor_z"] + 0.2)), Vector((0, 0, 1)), distance=6
            )
            z = min(3.1, loc.z - 0.1) if hit else 3.1
            print("LIGHT_CEILING", x, y, z, obj.name if obj else None, flush=True)
            data = bpy.data.lights.new("Reception practical illumination", "AREA")
            data.energy = 110
            data.shape = "DISK"
            data.size = 2
            data.color = (1, 0.94, 0.86)
            ob = bpy.data.objects.new(data.name, data)
            c.objects.link(ob)
            ob.location = (x, y, z)
    m["reception_lighting_corrected"] = True
fix()
m["fonts_embedded"] = True
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
