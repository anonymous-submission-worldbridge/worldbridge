"""
export_car_glb_all31.py — export a single openx car as GLB.

Usage: python export_car_glb_all31.py <car_subdir>

Opens the car blend, selects all mesh objects, exports as GLB to
/tmp/all31_cars/<car_subdir>.glb
"""

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

_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]

import sys, math
from pathlib import Path
import bpy

car_subdir = sys.argv[1]
src = Path(
    f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main/{car_subdir}/{car_subdir}.blend"
)
out_dir = Path("/tmp/all31_cars")
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / f"{car_subdir}.glb"

print(f"[exp] opening {src.name} ...")
bpy.ops.wm.open_mainfile(filepath=str(src))

EXCL = {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}

# select all mesh + empty objects (exclude cameras/lights)
bpy.ops.object.select_all(action="DESELECT")
sel_count = 0
for o in bpy.data.objects:
    if o.name in EXCL:
        continue
    if o.type in ("MESH", "EMPTY"):
        o.select_set(True)
        sel_count += 1
print(f"[exp] selected {sel_count} objects")

# export selected as GLB
print(f"[exp] exporting to {out.name} ...")
bpy.ops.export_scene.gltf(
    filepath=str(out),
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_yup=True,
    export_materials="EXPORT",
    export_cameras=False,
    export_lights=False,
    export_extras=False,
)
print(f"[exp] done: {out} ({out.stat().st_size // 1024} KB)")
