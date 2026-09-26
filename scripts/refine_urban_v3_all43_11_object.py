"""Generate the grounded-object pass and four high-resolution views."""

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

import json, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_11—res/urban_v3_all43_11—res.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_11—object"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_physical_interior_generator_11_object as G


def render(loc, target, name, lens):
    sc = bpy.context.scene
    cam = bpy.data.objects["all43_01:camera"]
    cam.location = loc
    cam.rotation_euler = (
        (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = lens
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 2560
    sc.render.resolution_y = 1440
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(OUT / name)
    bpy.ops.render.render(write_still=True)


def main():
    t = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    r = G.run()
    out = OUT / "urban_v3_all43_11—object.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    views = [
        ((-5, -57, 10.5), (-29, -24, 2.1), "A_hero_2560.png", 56),
        ((-24, -45, 5.4), (-42, -24, 1.55), "B_fresh_grounded_2560.png", 60),
        ((2, -43, 5.0), (-18, -24, 1.45), "C_kitchen_furniture_2560.png", 58),
        ((-11, -42, 3.8), (-30, -24, 1.35), "D_both_interiors_2560.png", 52),
    ]
    for v in views:
        render(*v)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "renders": [str(OUT / v[2]) for v in views],
        "resolution": [2560, 1440],
        "cycles_samples": 48,
        **r,
        "total_seconds": round(time.perf_counter() - t, 2),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_11_OBJECT_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
