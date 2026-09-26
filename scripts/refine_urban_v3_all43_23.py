"""Build, audit and render all43-23 through the active commercial generator."""
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
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_23"
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
REFERENCE_URL = "https://respic.3d66.com/coverimg/cache/08e7/f3369b2aa37f4d7597c7f3ae56f07653.jpg!medium-size-2?v=13114337&k=D41D8CD98F00B204E9800998ECF8427E"


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
        scene.eevee.taa_render_samples = 8
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.compression = 35
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
    blend_path = OUT / "urban_v3_all43_23.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    all_views = [
        (
            (-37.65, 5.8, 4.70),
            (-37.65, -10.45, 2.82),
            "commercial_cafe_grounded_front_1600.png",
            47,
            34,
        ),
        (
            (-45.0, 1.8, 6.30),
            (-37.20, -11.20, 2.48),
            "commercial_cafe_frontage_oblique_1600.png",
            50,
            34,
        ),
        (
            (-5.5, 8.5, 14.5),
            (-28.2, -12.2, 3.05),
            "commercial_cafe_mcdonalds_connection_1600.png",
            52,
            30,
        ),
        (
            (-10.5, 3.0, 7.20),
            (-24.8, -9.5, 2.65),
            "commercial_mcdonalds_extended_patio_sign_1600.png",
            52,
            32,
        ),
        (
            (-33.40, 0.8, 5.15),
            (-33.42, -10.55, 3.00),
            "commercial_party_wall_clearance_1600.png",
            58,
            34,
        ),
        (
            (-43.3, -3.2, 2.35),
            (-37.30, -9.25, 0.82),
            "commercial_cafe_grounded_furniture_detail_1600.png",
            58,
            36,
        ),
        (
            (-29.4, -4.1, 3.15),
            (-34.75, -10.02, 1.35),
            "commercial_cafe_drained_planter_detail_1600.png",
            61,
            36,
        ),
        (
            (-37.10, -5.0, 2.55),
            (-37.00, -11.55, 1.78),
            "commercial_cafe_working_bar_1600.png",
            52,
            38,
        ),
        (
            (25.0, -88.0, 34.0),
            (-29.5, -26.0, 2.5),
            "commercial_full_layout_1600.png",
            52,
            28,
        ),
        (
            (-29.5, -25.2, 100.0),
            (-29.5, -25.2, 0.0),
            "commercial_layout_top_down_1600.png",
            52,
            22,
        ),
    ]
    views = (
        [view for view in all_views if view[2] in RENDER_ONLY]
        if RENDER_ONLY
        else (all_views[:7] if FAST_PREVIEW else all_views)
    )
    if RENDER_ONLY and not views:
        raise RuntimeError({"unknown_render_selection": sorted(RENDER_ONLY)})
    render_times = {}
    for view in views:
        view_started = time.perf_counter()
        render_view(*view)
        render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    available_views = [view for view in all_views if (OUT / view[2]).exists()]
    report = {
        **stats,
        "source": str(SRC),
        "active_generator": str(
            ROOT / "scripts/commercial_mcdonalds_layout_generator_20.py"
        ),
        "complete_pipeline_consumer": str(
            ROOT / "scripts/generate_urban_v1_full_01.py"
        ),
        "pipeline_entry": str(ROOT / "scripts/refine_urban_v3_all43_23.py"),
        "output": str(blend_path),
        "output_revision": "urban_v3_all43_23",
        "reference_image": REFERENCE_URL,
        "reference_interpretation": "LEMON COFFEE black vertical-fluted facade, oak-framed glazed entrance, supported awning, working bar and grounded contract frontage furnishings",
        "layout_interpretation": "McDonald's is lengthened westward while retaining its 7-Eleven party line; the cafe shifts west and remains exactly connected, while the restaurant pylon is protected inside its own east patio",
        "collision_resolution": "the former remote twin-post sign is removed; the new low pylon has audited cafe, fence, boundary and patio-furniture clearances, and the cafe furniture/planter ground contacts are audited against the paver top",
        "renders": [str(OUT / view[2]) for view in available_views],
        "render_view_count": len(available_views),
        "rendered_this_run": len(views),
        "render_only_selection": sorted(RENDER_ONLY),
        "resolution": list(RESOLUTION),
        "render_engine": "BLENDER_EEVEE_NEXT" if FAST_PREVIEW else "CYCLES",
        "fast_preview": FAST_PREVIEW,
        "render_times_seconds": render_times,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_23_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
