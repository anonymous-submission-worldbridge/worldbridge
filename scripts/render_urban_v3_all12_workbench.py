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

import math
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all12")

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = 1600
sc.render.resolution_y = 900
sc.render.image_settings.file_format = "PNG"
try:
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
except Exception as exc:
    print(f"[all12_render] View settings note: {exc}", flush=True)
try:
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
except Exception as exc:
    print(f"[all12_render] Workbench shading note: {exc}", flush=True)


def make_cam(name, loc, target, fov=58):
    cam = bpy.data.objects.get(name)
    if cam is None:
        bpy.ops.object.camera_add(location=loc)
        cam = bpy.context.active_object
        cam.name = name
        cam.data.name = name
    cam.location = loc
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov)
    dv = Vector(target) - Vector(loc)
    if dv.length > 0:
        cam.rotation_euler = dv.to_track_quat("-Z", "Y").to_euler()
    return cam


cameras = [
    (make_cam("cam_overview", (5, -75, 95), (0, 10, 0), 64), "overview.png"),
    (make_cam("cam_residential", (15, 5, 28), (-30, 36, 8), 58), "residential.png"),
    (make_cam("cam_park", (-12, 36, 22), (34, 28, 2), 62), "park.png"),
    (make_cam("cam_commercial", (5, -5, 20), (32, -30, 4), 60), "commercial.png"),
    (make_cam("cam_intersection", (-20, -22, 18), (0, 0, 0), 56), "intersection.png"),
]

for cam, fname in cameras:
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all12_render] Rendering {fname}", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all12_render] Done {fname}", flush=True)

print("[all12_render] Complete", flush=True)
