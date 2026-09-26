"""Render-only validation views for the clean all45-03 generator output."""

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

OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_all45_03"
)
RENDERS = OUT / "renders"


def main():
    RENDERS.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    # EEVEE/Workbench require a working EGL context in Blender 4.5.  The
    # managed headless environment does not provide one, so validation uses a
    # low-sample CPU Cycles pass instead.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 640
    scene.render.resolution_y = 400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    names = [
        "01_residential_overview",
        "02_lowrise_exterior_close",
        "03_indoor_house_window_view",
        "04_indoor_house_interior",
        "05_apartment_front_close",
        "06_apartment_balcony_close",
        "07_tree_close",
        "08_shrub_close",
        "09_grass_close",
        "10_landscape_overview",
    ]
    for name in names:
        cam = bpy.data.objects.get("all45_03:cam_" + name)
        if cam is None:
            raise KeyError(f"Missing validation camera {name}")
        scene.camera = cam
        scene.render.filepath = str(RENDERS / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[Validation-Workbench] rendered {name}.png", flush=True)


if __name__ == "__main__":
    main()
