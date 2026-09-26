"""Generate urban_v3_all43_25 through the active production commercial chain.

The source is the clean all43-19 stage because the active generator rebuilds
all subsequent McDonald's, cafe, frontage and all43-25 bar work every run.
The saved Blend is therefore a reproducible generator result, not a hand patch.
"""
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
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_19/urban_v3_all43_19.blend"
)
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_25"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_mcdonalds_layout_generator_20 as generator
import commercial_reference_bars_generator_25 as bars25


FAST_PREVIEW = os.environ.get("C2W_FAST_PREVIEW") == "1"
RENDER_VALIDATION = os.environ.get("C2W_RENDER_VALIDATION") == "1"
RENDER_ONLY = {
    name.strip()
    for name in os.environ.get("C2W_RENDER_ONLY", "").split(",")
    if name.strip()
}
RESOLUTION = (800, 450) if FAST_PREVIEW else (1600, 900)


VIEWS = [
    (
        (-54.25, 2.6, 5.4),
        (-54.25, -11.25, 2.35),
        "01_copper_tap_reference_front_near.png",
        46,
        28,
    ),
    (
        (-46.05, 2.8, 6.0),
        (-46.05, -11.15, 2.80),
        "02_hawthorn_reference_front_near.png",
        47,
        28,
    ),
    (
        (-64.0, -0.5, 8.4),
        (-50.1, -11.7, 2.85),
        "03_adjacent_bar_pair_west_oblique.png",
        50,
        26,
    ),
    (
        (-37.0, -0.5, 7.2),
        (-48.2, -11.6, 2.70),
        "04_adjacent_bar_pair_east_oblique.png",
        50,
        26,
    ),
    (
        (-49.0, -3.0, 2.25),
        (-47.0, -10.50, 1.55),
        "05_bar_entrances_and_frontage_near.png",
        52,
        30,
    ),
    (
        (28.0, 20.0, 25.0),
        (-26.0, -24.0, 3.0),
        "06_complete_inverse_l_northeast_far.png",
        53,
        24,
    ),
    (
        (-105.0, 43.0, 38.0),
        (-30.0, -24.0, 3.0),
        "07_complete_inverse_l_northwest_far.png",
        58,
        24,
    ),
    (
        (42.0, -98.0, 39.0),
        (-30.0, -26.0, 3.0),
        "08_complete_inverse_l_southeast_far.png",
        58,
        24,
    ),
    (
        (-104.0, -98.0, 42.0),
        (-31.0, -26.0, 3.0),
        "09_complete_inverse_l_southwest_far.png",
        60,
        24,
    ),
    (
        (-30.0, 62.0, 28.0),
        (-30.0, -23.0, 3.0),
        "10_complete_north_frontage_far.png",
        48,
        24,
    ),
    (
        (-76.0, 19.0, 37.0),
        (-31.0, -25.0, 2.8),
        "11_complete_commercial_aerial.png",
        54,
        22,
    ),
    (
        (-31.0, -25.0, 112.0),
        (-31.0, -25.0, 0.0),
        "12_complete_layout_top_down.png",
        52,
        20,
    ),
]


def render_view(location, target, filename, lens, samples):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.clip_end = 1500
    scene.camera = camera
    if FAST_PREVIEW:
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "WORLD"
        scene.display.shading.curvature_ridge_factor = 1.45
        scene.display.shading.curvature_valley_factor = 1.20
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (0.055, 0.065, 0.075)
    else:
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
    blend_path = OUT / "urban_v3_all43_25.blend"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    render_times = {}
    if RENDER_VALIDATION:
        selected = [view for view in VIEWS if not RENDER_ONLY or view[2] in RENDER_ONLY]
        if not selected:
            raise RuntimeError({"unknown_render_selection": sorted(RENDER_ONLY)})
        for view in selected:
            view_started = time.perf_counter()
            render_view(*view)
            render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    report = {
        **stats,
        "source": str(SRC),
        "active_generator": str(
            ROOT / "scripts/commercial_mcdonalds_layout_generator_20.py"
        ),
        "connected_bar_module": str(
            ROOT / "scripts/commercial_reference_bars_generator_25.py"
        ),
        "complete_pipeline_consumer": str(
            ROOT / "scripts/generate_urban_v1_full_01.py"
        ),
        "pipeline_entry": str(ROOT / "scripts/refine_urban_v3_all43_25.py"),
        "output": str(blend_path),
        "output_revision": "urban_v3_all43_25",
        "reference_images": [bars25.REFERENCE_OPEN_BAR, bars25.REFERENCE_HAWTHORN],
        "revision_summary": "two adjacent reference-matched bars extend the north commercial street west of LEMON COFFEE while 7-Eleven remains the inverse-L corner and all customer entrances remain clear",
        "validation_view_count": len(VIEWS),
        "rendered_this_run": len(render_times),
        "render_times_seconds": render_times,
        "resolution": list(RESOLUTION),
        "fast_preview": FAST_PREVIEW,
        "blend_file_bytes": blend_path.stat().st_size,
        "total_seconds": round(time.perf_counter() - started, 2),
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_25_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
