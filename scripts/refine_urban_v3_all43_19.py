"""Build and validate all43-19 through the production corner-store generator."""
from __future__ import annotations

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
SRC = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_18/urban_v3_all43_18.blend"
)
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_19"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_corner_711_generator_19 as generator


RESOLUTION = (1600, 900)


def render_view(location, target, filename, lens, samples=24):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.clip_end = 1200
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.compression = 40
    scene.render.film_transparent = False
    scene.render.filepath = str(OUT / filename)
    bpy.ops.render.render(write_still=True)


def main():
    started = time.perf_counter()
    if not SRC.exists():
        raise FileNotFoundError(SRC)
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    stats = generator.run()
    bpy.context.preferences.filepaths.save_version = 0
    blend_path = OUT / "urban_v3_all43_19.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    views = [
        (
            (24.0, -92.0, 31.0),
            (-29.0, -25.0, 2.5),
            "commercial_overview_1600.png",
            52,
            24,
        ),
        (
            (15.0, 16.0, 17.0),
            (-26.0, -21.0, 3.2),
            "commercial_711_context_1600.png",
            54,
            24,
        ),
        (
            (11.0, 12.0, 12.5),
            (-13.2, -10.9, 5.55),
            "commercial_711_corner_1600.png",
            55,
            32,
        ),
        (
            (-3.0, -3.2, 3.0),
            (-13.0, -10.2, 2.05),
            "commercial_711_storefront_close_1600.png",
            58,
            32,
        ),
        (
            (-8.0, -4.1, 2.05),
            (-13.1, -10.3, 1.30),
            "commercial_711_interior_close_1600.png",
            54,
            32,
        ),
        (
            (-13.45, -11.20, 47.0),
            (-13.45, -11.20, 0.0),
            "commercial_711_top_down_1600.png",
            56,
            20,
        ),
    ]
    render_times = {}
    for view in views:
        view_started = time.perf_counter()
        render_view(*view)
        render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    report = {
        "source": str(SRC),
        "active_generator": str(ROOT / "scripts/commercial_corner_711_generator_19.py"),
        "pipeline_entry": str(ROOT / "scripts/refine_urban_v3_all43_19.py"),
        "output": str(blend_path),
        "output_revision": "urban_v3_all43_19",
        "reference_image": "https://img.alicdn.com/imgextra/i1/2212503442207/O1CN01OgMieX1SArDI3MQ7I_!!2212503442207.png",
        "reference_interpretation": "full-scale three-storey green masonry corner store; miniature/toy proportions intentionally rejected",
        "renders": [str(OUT / view[2]) for view in views],
        "render_view_count": len(views),
        "resolution": list(RESOLUTION),
        "render_engine": "CYCLES",
        "render_times_seconds": render_times,
        **stats,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_19_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
