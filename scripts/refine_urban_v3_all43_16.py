"""Build all43-16 and render compact multi-direction commercial checks."""

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

import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_15/urban_v3_all43_15.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_16"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_visibility_planter_generator_16 as generator


RESOLUTION = (1600, 900)


def render_view(location, target, filename, lens):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.clip_end = 1000
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.compression = 40
    scene.render.film_transparent = False
    scene.render.filepath = str(OUT / filename)
    bpy.ops.render.render(write_still=True)


def main():
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    stats = generator.run()
    blend_path = OUT / "urban_v3_all43_16.blend"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    views = [
        ((-5.0, -57.0, 11.5), (-31.5, -23.5, 2.0), "commercial_overview_1600.png", 54),
        (
            (-7.0, -50.0, 37.0),
            (-31.5, -22.0, 1.0),
            "commercial_aerial_oblique_1600.png",
            50,
        ),
        ((-31.8, -23.0, 55.0), (-31.8, -23.0, 0.0), "commercial_top_down_1600.png", 56),
        ((-32.0, -48.0, 6.3), (-32.0, -22.0, 2.2), "commercial_front_1600.png", 52),
        ((-32.0, 3.0, 6.3), (-32.0, -20.0, 2.2), "commercial_rear_1600.png", 52),
        ((-62.0, -22.0, 6.0), (-32.0, -21.0, 2.1), "commercial_left_1600.png", 55),
        ((5.0, -22.0, 6.0), (-32.0, -21.0, 2.1), "commercial_right_1600.png", 55),
        (
            (-40.0, -37.0, 4.6),
            (-40.0, -25.2, 2.2),
            "fresh_mart_front_close_1600.png",
            58,
        ),
        (
            (-40.2, -32.0, 2.45),
            (-40.4, -20.4, 1.35),
            "fresh_mart_interior_close_1600.png",
            53,
        ),
        (
            (-48.7, -31.5, 1.75),
            (-46.45, -26.82, 1.10),
            "fresh_mart_planter_detail_1600.png",
            68,
        ),
        (
            (-24.3, -37.0, 4.7),
            (-24.3, -25.2, 2.3),
            "corner_kitchen_front_close_1600.png",
            58,
        ),
        (
            (-28.0, -32.0, 2.50),
            (-27.6, -21.2, 1.30),
            "corner_kitchen_dining_close_1600.png",
            54,
        ),
        (
            (-20.7, -31.4, 2.55),
            (-21.0, -18.5, 1.45),
            "corner_kitchen_counter_kitchen_close_1600.png",
            55,
        ),
        (
            (-33.0, -31.5, 1.75),
            (-30.55, -26.82, 1.10),
            "corner_kitchen_planter_detail_1600.png",
            68,
        ),
        (
            (-36.3, -30.5, 2.35),
            (-36.6, -23.0, 1.50),
            "storefront_glass_detail_1600.png",
            62,
        ),
    ]
    render_times = {}
    for view in views:
        view_started = time.perf_counter()
        render_view(*view)
        render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    report = {
        "source": str(SRC),
        "output": str(blend_path),
        "renders": [str(OUT / view[2]) for view in views],
        "render_view_count": len(views),
        "resolution": list(RESOLUTION),
        "render_engine": "CYCLES",
        "cycles_samples": 24,
        "render_times_seconds": render_times,
        **stats,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_16_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
