"""Apply all45_04 quality settings to a generator-produced checkpoint."""

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

OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_all45_04"
)
R = OUT / "renders"
R.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 32
sc.cycles.use_denoising = True
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.025
sc.render.resolution_x = 800
sc.render.resolution_y = 500
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
sc.view_settings.look = "AgX - Medium High Contrast"

# Upgrade every generated facade glass material for true interior visibility.
for mat in bpy.data.materials:
    if "glass" not in mat.name.lower() or not mat.use_nodes:
        continue
    for n in mat.node_tree.nodes:
        if n.type != "BSDF_PRINCIPLED":
            continue
        for key, val in [
            ("Transmission Weight", 0.92),
            ("Alpha", 0.16),
            ("Roughness", 0.035),
            ("IOR", 1.45),
        ]:
            if key in n.inputs:
                n.inputs[key].default_value = val

# Permanent practical lights inside the low-rise buildings.
coll = (
    bpy.data.collections.get("all45_03:residential_zone_generator_45_03")
    or sc.collection
)
for hi, (x, y) in enumerate(((-36, -18), (-5, -20), (29, -18))):
    for floor in range(2):
        d = bpy.data.lights.new(f"all45_04:indoor_light_{hi}_{floor}", "AREA")
        d.energy = 900
        d.color = (1, 0.72, 0.48)
        d.shape = "DISK"
        d.size = 5
        o = bpy.data.objects.new(d.name, d)
        coll.objects.link(o)
        o.location = (x, y, 2.25 + floor * 3.18)

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45_04.blend"))
for name in (
    "01_residential_overview",
    "02_lowrise_exterior_close",
    "03_indoor_house_window_view",
    "04_indoor_house_interior",
    "07_tree_close",
    "10_landscape_overview",
):
    cam = bpy.data.objects.get("all45_03:cam_" + name)
    if not cam:
        continue
    sc.camera = cam
    sc.render.filepath = str(R / (name + ".png"))
    bpy.ops.render.render(write_still=True)
    print("[all45_04] rendered", name, flush=True)
