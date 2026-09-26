"""Build, audit and render all43-24 through the active commercial generator.

This focused production entry consumes the same source and invokes the same
generator as the complete urban pipeline.  It exists to make commercial-only
iteration and multi-angle validation practical; it does not author a separate
demo asset or patch a saved Blend.
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
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_24"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_mcdonalds_layout_generator_20 as generator


FAST_PREVIEW = os.environ.get("C2W_FAST_PREVIEW") == "1"
REUSE_OUTPUT_BLEND = os.environ.get("C2W_REUSE_OUTPUT_BLEND") == "1"
RENDER_ONLY = {
    name.strip()
    for name in os.environ.get("C2W_RENDER_ONLY", "").split(",")
    if name.strip()
}
RESOLUTION = (720, 405) if FAST_PREVIEW else (1600, 900)
REFERENCE_URL = "https://respic.3d66.com/coverimg/cache/08e7/f3369b2aa37f4d7597c7f3ae56f07653.jpg!medium-size-2?v=13114337&k=D41D8CD98F00B204E9800998ECF8427E"


def configure_commercial_preview_lighting():
    """Keep sun shadows while avoiding thousands of irrelevant local shadow maps."""
    if not FAST_PREVIEW:
        return 0
    disabled = 0
    for light in bpy.data.lights:
        if light.type != "SUN" and hasattr(light, "use_shadow") and light.use_shadow:
            light.use_shadow = False
            disabled += 1
    return disabled


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
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_shadows = True
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "WORLD"
        scene.display.shading.curvature_ridge_factor = 1.45
        scene.display.shading.curvature_valley_factor = 1.20
        scene.display.shading.show_specular_highlight = True
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (0.055, 0.065, 0.075)
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
    blend_path = OUT / "urban_v3_all43_24.blend"
    report_path = OUT / "performance_stats.json"
    if REUSE_OUTPUT_BLEND:
        if not blend_path.exists() or not report_path.exists():
            raise FileNotFoundError(
                "render-only reuse requires the generated all43-24 Blend and report"
            )
        bpy.ops.wm.open_mainfile(filepath=str(blend_path), load_ui=False)
        stats = json.loads(report_path.read_text(encoding="utf8"))
    else:
        if not SRC.exists():
            raise FileNotFoundError(SRC)
        bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
        stats = generator.run()
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)
    preview_local_shadow_count = configure_commercial_preview_lighting()

    # Near/far and north/east/south/west coverage.  Close botanical and chair
    # views make direction, support contact and mesh clearance independently
    # inspectable instead of relying on one flattering facade shot.
    all_views = [
        (
            (-37.65, -3.0, 3.55),
            (-37.65, -10.05, 2.10),
            "commercial_cafe_front_near_1600.png",
            48,
            32,
        ),
        (
            (-37.65, 6.5, 6.80),
            (-37.65, -10.55, 2.60),
            "commercial_cafe_front_far_1600.png",
            52,
            28,
        ),
        (
            (-45.0, -1.0, 5.80),
            (-37.25, -10.45, 2.30),
            "commercial_cafe_northwest_oblique_1600.png",
            52,
            30,
        ),
        (
            (-30.2, -1.2, 5.75),
            (-36.75, -10.35, 2.25),
            "commercial_cafe_northeast_oblique_1600.png",
            52,
            30,
        ),
        (
            (-44.1, -7.2, 3.45),
            (-37.65, -10.55, 2.05),
            "commercial_cafe_west_side_near_1600.png",
            56,
            32,
        ),
        (
            (-31.0, -6.1, 3.65),
            (-35.10, -10.10, 1.80),
            "commercial_cafe_east_side_near_1600.png",
            58,
            32,
        ),
        (
            (-37.65, -5.2, 1.72),
            (-37.65, -9.48, 0.79),
            "commercial_cafe_road_facing_chairs_front_detail_1600.png",
            62,
            36,
        ),
        (
            (-42.5, -7.1, 1.85),
            (-37.55, -9.52, 0.80),
            "commercial_cafe_road_facing_chairs_side_detail_1600.png",
            61,
            36,
        ),
        (
            (-34.75, -4.45, 2.75),
            (-34.75, -10.02, 2.25),
            "commercial_cafe_botanical_front_detail_1600.png",
            50,
            38,
        ),
        (
            (-34.75, -2.65, 2.50),
            (-34.75, -10.02, 1.98),
            "commercial_cafe_botanical_full_1600.png",
            40,
            36,
        ),
        (
            (-39.65, -6.75, 3.00),
            (-34.72, -10.02, 2.22),
            "commercial_cafe_botanical_west_detail_1600.png",
            52,
            38,
        ),
        (
            (-33.62, -6.72, 2.75),
            (-34.72, -10.02, 2.18),
            "commercial_cafe_botanical_east_detail_1600.png",
            55,
            38,
        ),
        (
            (-28.0, 10.0, 13.0),
            (-29.2, -13.2, 2.75),
            "commercial_north_frontage_far_1600.png",
            52,
            28,
        ),
        (
            (-60.0, -2.5, 16.5),
            (-34.0, -16.2, 2.55),
            "commercial_west_far_1600.png",
            54,
            26,
        ),
        (
            (8.0, -2.0, 16.0),
            (-24.5, -17.2, 2.65),
            "commercial_east_far_1600.png",
            55,
            26,
        ),
        (
            (-31.0, -60.0, 18.5),
            (-30.0, -19.0, 2.70),
            "commercial_south_rear_far_1600.png",
            56,
            26,
        ),
        (
            (-55.0, 14.0, 34.0),
            (-29.5, -22.0, 2.30),
            "commercial_aerial_northwest_1600.png",
            54,
            24,
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
        else all_views
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
        "pipeline_entry": str(ROOT / "scripts/refine_urban_v3_all43_24.py"),
        "output": str(blend_path),
        "output_revision": "urban_v3_all43_24",
        "reference_image": REFERENCE_URL,
        "revision_summary": "all cafe lounge chairs face the north road with backs toward the facade; the former intersecting sheet yucca is replaced by a three-stem, separately petioled, solid cambered fiddle-leaf fig in a layered hollow planter",
        "botanical_collision_policy": "evaluated leaf meshes are checked pairwise with BVH; canopy clearances to storefront, chair envelope and McDonald's patio fence are enforced by the active generator",
        "view_coverage": "18 commercial-only validation cameras: close and distant frontage, northwest/northeast/west/east, two chair details, three botanical details plus one full-plant view, north/west/east/south far views, aerial and top-down",
        "renders": [str(OUT / view[2]) for view in available_views],
        "render_view_count": len(available_views),
        "rendered_this_run": len(views),
        "render_only_selection": sorted(RENDER_ONLY),
        "resolution": list(RESOLUTION),
        "render_engine": "BLENDER_WORKBENCH material-color validation"
        if FAST_PREVIEW
        else "CYCLES",
        "fast_preview": FAST_PREVIEW,
        "generation_reexecuted_this_run": not REUSE_OUTPUT_BLEND,
        "reused_generated_output_blend_for_render_only": REUSE_OUTPUT_BLEND,
        "preview_local_light_shadows_disabled_after_blend_save": preview_local_shadow_count,
        "render_times_seconds": render_times,
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_24_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
