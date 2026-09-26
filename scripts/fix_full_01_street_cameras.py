"""Correct and rerender the four obstructed full_01 human-height views."""

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

from pathlib import Path
import bpy
from mathutils import Vector

OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_01"
)
views = {
    "12_street_level_commercial.png": ((0, -28, 1.72), (-28, -25, 2.5)),
    "13_street_level_residential.png": ((0, 28, 1.72), (-30, 30, 3.0)),
    "14_street_level_park.png": ((0, 28, 1.72), (30, 30, 1.5)),
    "15_street_level_leisure.png": ((0, -28, 1.72), (28, -27, 1.8)),
}
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 16
sc.cycles.use_denoising = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
for filename, (loc, target) in views.items():
    cam = bpy.data.objects["full:" + filename]
    cam.location = loc
    cam.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    sc.camera = cam
    sc.render.filepath = str(OUT / filename)
    bpy.ops.render.render(write_still=True)
    print("[Validation] Corrected " + filename, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v1_full_01.blend"), compress=True)
