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

import bpy

src = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_04/urban_v1_full_04.blend"
bpy.ops.wm.open_mainfile(filepath=src)
for o in list(bpy.data.objects):
    if o.name.startswith(("st_e", "st_w", "nt_e", "nt_w")):
        bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects:
    if o.name.startswith("K6_"):
        if o.location.x > 0 and o.location.y < 0:
            o.location.x += 1.05
        elif o.location.x < 0 and o.location.y > 0:
            o.location.x -= 1.05
        o["c2w_phonebooth_role"] = "roadside_sidewalk"
    if (
        o.instance_type == "COLLECTION"
        and o.instance_collection
        and "phonebooth" in o.instance_collection.name.lower()
    ):
        o.location.x = -8.525
        o["c2w_phonebooth_role"] = "roadside_sidewalk"
bpy.context.scene["c2w_revision"] = "urban_v1_full_04"
bpy.context.scene[
    "c2w_generator"
] = f"{_wb_WORLDBRIDGE_ROOT}/scripts/generate_urban_v1_full_04.py"
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=src, compress=True)
print("full04 finalization complete")
