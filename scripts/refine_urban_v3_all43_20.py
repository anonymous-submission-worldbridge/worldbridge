"""Build and validate all43-20 through the production commercial generator."""
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
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_20"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_mcdonalds_layout_generator_20 as generator


FAST_PREVIEW = os.environ.get("C2W_FAST_PREVIEW") == "1"
RENDER_ONLY = {
    name.strip()
    for name in os.environ.get("C2W_RENDER_ONLY", "").split(",")
    if name.strip()
}
RESOLUTION = (960, 540) if FAST_PREVIEW else (1600, 900)


def render_view(location, target, filename, lens, samples=28):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    camera.location = location
    camera.rotation_euler = (
        (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens
    camera.data.clip_end = 1200
    scene.camera = camera
    if FAST_PREVIEW:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.image_settings.file_format = "PNG"
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
    bpy.context.preferences.filepaths.save_version = 0
    blend_path = OUT / "urban_v3_all43_20.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    all_views = [
        (
            (19.0, 17.0, 17.0),
            (-25.0, -15.0, 3.2),
            "commercial_connected_overview_1600.png",
            55,
            26,
        ),
        (
            (-22.0, 8.5, 5.0),
            (-22.0, -10.6, 2.8),
            "commercial_north_streetwall_1600.png",
            52,
            30,
        ),
        (
            (-18.0, 3.0, 8.5),
            (-17.1, -10.2, 3.4),
            "commercial_711_mcdonalds_connection_1600.png",
            58,
            32,
        ),
        (
            (-25.0, -0.8, 3.0),
            (-24.5, -10.0, 2.25),
            "commercial_mcdonalds_front_1600.png",
            55,
            34,
        ),
        (
            (-25.0, -3.0, 2.35),
            (-24.2, -10.6, 1.42),
            "commercial_mcdonalds_interior_1600.png",
            52,
            36,
        ),
        (
            (24.0, -92.0, 31.0),
            (-31.0, -20.5, 2.6),
            "commercial_full_layout_1600.png",
            52,
            28,
        ),
        (
            (-31.5, -25.3, 100.0),
            (-31.5, -25.3, 0.0),
            "commercial_layout_top_down_1600.png",
            52,
            22,
        ),
    ]
    views = (
        all_views[:3]
        if FAST_PREVIEW
        else (
            [view for view in all_views if view[2] in RENDER_ONLY]
            if RENDER_ONLY
            else all_views
        )
    )
    if RENDER_ONLY and not views:
        raise RuntimeError({"unknown_render_selection": sorted(RENDER_ONLY)})
    render_times = {}
    for view in views:
        view_started = time.perf_counter()
        render_view(*view)
        render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    report = {
        "source": str(SRC),
        "active_generator": str(
            ROOT / "scripts/commercial_mcdonalds_layout_generator_20.py"
        ),
        "pipeline_entry": str(ROOT / "scripts/refine_urban_v3_all43_20.py"),
        "output": str(blend_path),
        "output_revision": "urban_v3_all43_20",
        "reference_image": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQY5pRjRWflgPIq387Q3J49s1COIhTlEQLmMTLscfpFiwZOFIkg_Cobra4&s=10",
        "reference_interpretation": "full-scale pale roadside McDonald's with bright yellow awnings, entrance arches and tall road sign",
        "layout_interpretation": "corner 7-Eleven and road-facing McDonald's form the north street wall; Corner Kitchen and Fresh Mart form the connected south wing",
        "renders": [
            str(OUT / view[2]) for view in (views if FAST_PREVIEW else all_views)
        ],
        "render_view_count": len(views if FAST_PREVIEW else all_views),
        "rendered_this_run": len(views),
        "render_only_selection": sorted(RENDER_ONLY),
        "resolution": list(RESOLUTION),
        "render_engine": "BLENDER_EEVEE_NEXT" if FAST_PREVIEW else "CYCLES",
        "fast_preview": FAST_PREVIEW,
        "render_times_seconds": render_times,
        **stats,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_20_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
