"""Build and render the all43-15 commercial-system reconstruction."""

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
SRC = ROOT / "infinigen/outputs/urban_v3_all43_14/urban_v3_all43_14.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_15"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_rebuild_generator_15 as generator


def render_view(location, target, filename, lens):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    scene.render.resolution_x = 2560
    scene.render.resolution_y = 1440
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(OUT / filename)
    bpy.ops.render.render(write_still=True)


def main():
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    stats = generator.run()
    blend_path = OUT / "urban_v3_all43_15.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    views = [
        ((-5.0, -57.0, 10.5), (-29.0, -24.0, 2.15), "commercial_overview_2560.png", 56),
        (
            (-40.0, -37.5, 4.8),
            (-40.0, -25.4, 2.25),
            "fresh_mart_front_close_2560.png",
            58,
        ),
        (
            (-40.2, -32.7, 2.55),
            (-40.5, -20.7, 1.30),
            "fresh_mart_interior_close_2560.png",
            54,
        ),
        (
            (-24.3, -37.2, 4.8),
            (-24.3, -25.4, 2.35),
            "corner_kitchen_front_close_2560.png",
            58,
        ),
        (
            (-28.0, -32.4, 2.55),
            (-27.6, -21.4, 1.25),
            "corner_kitchen_dining_close_2560.png",
            55,
        ),
        (
            (-20.8, -31.9, 2.65),
            (-21.0, -18.6, 1.40),
            "corner_kitchen_counter_kitchen_close_2560.png",
            56,
        ),
        (
            (-37.7, -30.2, 3.10),
            (-39.5, -25.65, 2.75),
            "storefront_detail_close_2560.png",
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
        "resolution": [2560, 1440],
        "render_engine": "CYCLES",
        "cycles_samples": 32,
        "render_times_seconds": render_times,
        **stats,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_15_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
