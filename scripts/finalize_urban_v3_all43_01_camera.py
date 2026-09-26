"""Reframe and render an already generated all43_01 scene."""

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

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all43_01")
bpy.ops.wm.open_mainfile(filepath=str(OUT / "urban_v3_all43_01.blend"), load_ui=False)
cam = bpy.data.objects["all43_01:camera"]
cam.location = (-5, -54, 15)
cam.rotation_euler = (
    (Vector((-29, -22, 2.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
)
cam.data.lens = 52
fore = bpy.data.objects.get("all43_01:forecourt")
if fore:
    fore.location.y = -13.5
    fore.dimensions.y = 8.0
    bpy.context.view_layer.objects.active = fore
    fore.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    fore.select_set(False)
yard = bpy.data.objects.get("all43_01:service_yard")
if yard:
    yard.location.x = -40
    yard.dimensions.x = 18.5
    bpy.context.view_layer.objects.active = yard
    yard.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    yard.select_set(False)
for o in bpy.data.objects:
    if o.name.startswith("all43_01:paving_joint"):
        o.location.y = -13.5
        o.dimensions.y = 8.0
sc = bpy.context.scene
sc.camera = cam
old = {o: o.hide_render for o in sc.objects}
keep = {"Road", "RoadMarkings", "Sidewalk"}
for o in sc.objects:
    o.hide_render = not (
        o.name.startswith("all43_01:")
        or any(c.name in keep for c in o.users_collection)
    )
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 16
sc.cycles.use_denoising = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = str(OUT / "commercial_final.png")
bpy.ops.render.render(write_still=True)
for o, v in old.items():
    o.hide_render = v
bpy.ops.wm.save_as_mainfile(
    filepath=str(OUT / "urban_v3_all43_01.blend"), compress=True
)
print("[all43_01] reframed preview and blend saved", flush=True)
