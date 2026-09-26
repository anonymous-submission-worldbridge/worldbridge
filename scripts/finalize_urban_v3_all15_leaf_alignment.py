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

BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all15/urban_v3_all15.blend"
)
OUT = BLEND.parent

print("[all15-final] Opening all15 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(BLEND))

fixed = 0
for obj in bpy.data.objects:
    if "leaf_complex" not in obj.name or obj.type != "MESH":
        continue
    obj.scale = (1.0, 1.0, 1.0)
    obj.hide_viewport = False
    obj.hide_render = False
    fixed += 1
print(
    f"[all15-final] Reset supplemental leaf_complex object scales: {fixed}", flush=True
)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.render.resolution_x = 1600
scene.render.resolution_y = 900
scene.render.image_settings.file_format = "PNG"
scene.cycles.samples = 192
scene.cycles.use_denoising = True
try:
    scene.cycles.device = "GPU"
except Exception:
    pass
try:
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.25
    scene.view_settings.gamma = 1.0
except Exception:
    pass

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
print(f"[all15-final] Blend saved: {BLEND}", flush=True)

for cam_name, filename in [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(
            f"[all15-final] Missing camera {cam_name}, skipping {filename}", flush=True
        )
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all15-final] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all15-final] Done: {filename}", flush=True)

print("[all15-final] All complete.", flush=True)
