"""Build all43-18 through the active all43 commercial detail generator."""

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
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_16/urban_v3_all43_16.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_18"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_detail_generator_17 as generator


RESOLUTION = (1600, 900)
COMMERCIAL_AUDIT_BOUNDS = (
    (-50.5, -46.0, 0.0),
    (-9.5, -7.0, 7.0),
)


def render_view(location, target, filename, lens):
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


def audit_wide_camera_views(views):
    scene = bpy.context.scene
    camera = bpy.data.objects["all43_01:camera"]
    low, high = COMMERCIAL_AUDIT_BOUNDS
    corners = [
        Vector((x, y, z))
        for x in (low[0], high[0])
        for y in (low[1], high[1])
        for z in (low[2], high[2])
    ]
    results = {}
    for location, target, filename, lens in views:
        camera.location = location
        camera.rotation_euler = (
            (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        camera.data.lens = lens
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, camera, corner) for corner in corners]
        bounds = {
            "min_x": min(point.x for point in projected),
            "max_x": max(point.x for point in projected),
            "min_y": min(point.y for point in projected),
            "max_y": max(point.y for point in projected),
            "minimum_depth": min(point.z for point in projected),
        }
        if (
            bounds["min_x"] < 0.04
            or bounds["max_x"] > 0.96
            or bounds["min_y"] < 0.04
            or bounds["max_y"] > 0.96
            or bounds["minimum_depth"] <= 0
        ):
            raise RuntimeError(
                "Wide camera clips commercial audit bounds: %s %r" % (filename, bounds)
            )
        results[filename] = {key: round(value, 4) for key, value in bounds.items()}
    return results


def main():
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    stats = generator.run()
    blend_path = OUT / "urban_v3_all43_18.blend"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    views = [
        ((22.0, -100.0, 30.0), (-30.0, -26.5, 1.0), "commercial_overview_1600.png", 52),
        (
            (20.0, -105.0, 82.0),
            (-30.0, -26.5, 0.0),
            "commercial_aerial_oblique_1600.png",
            50,
        ),
        (
            (-30.0, -26.5, 120.0),
            (-30.0, -26.5, 0.0),
            "commercial_top_down_1600.png",
            50,
        ),
        ((-30.0, -115.0, 14.0), (-30.0, -26.5, 2.0), "commercial_front_1600.png", 52),
        ((-30.0, 62.0, 14.0), (-30.0, -26.5, 2.0), "commercial_rear_1600.png", 52),
        ((-118.0, -26.5, 14.0), (-30.0, -26.5, 2.0), "commercial_left_1600.png", 52),
        ((58.0, -26.5, 14.0), (-30.0, -26.5, 2.0), "commercial_right_1600.png", 52),
        (
            (-31.0, -4.0, 3.5),
            (-31.0, -12.5, 1.1),
            "commercial_rear_cafe_flowerbed_detail_1600.png",
            55,
        ),
        (
            (-44.0, -7.2, 2.25),
            (-43.6, -13.25, 0.70),
            "commercial_rear_shared_bicycles_detail_1600.png",
            58,
        ),
        (
            (-50.8, -46.0, 3.40),
            (-46.1, -39.0, 0.70),
            "fresh_mart_bicycle_station_detail_1600.png",
            55,
        ),
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
            (-48.2, -31.0, 1.65),
            (-46.45, -26.82, 1.15),
            "fresh_mart_planter_detail_1600.png",
            65,
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
            (-36.3, -30.5, 2.35),
            (-36.6, -23.0, 1.50),
            "storefront_glass_detail_1600.png",
            62,
        ),
        (
            (-40.5, -29.6, 1.60),
            (-42.7, -21.2, 1.05),
            "fresh_mart_shelf_product_support_1600.png",
            66,
        ),
    ]
    wide_camera_audit = audit_wide_camera_views(views[:7])
    render_times = {}
    for view in views:
        view_started = time.perf_counter()
        render_view(*view)
        render_times[view[2]] = round(time.perf_counter() - view_started, 2)

    report = {
        "source": str(SRC),
        "active_generator": str(ROOT / "scripts/commercial_detail_generator_17.py"),
        "output": str(blend_path),
        "renders": [str(OUT / view[2]) for view in views],
        "render_view_count": len(views),
        "resolution": list(RESOLUTION),
        "render_engine": "CYCLES",
        "cycles_samples": 24,
        "commercial_audit_world_bounds": [
            list(COMMERCIAL_AUDIT_BOUNDS[0]),
            list(COMMERCIAL_AUDIT_BOUNDS[1]),
        ],
        "wide_camera_projection_audit": wide_camera_audit,
        "render_times_seconds": render_times,
        **stats,
        "output_revision": "urban_v3_all43_18",
        "total_seconds": round(time.perf_counter() - started, 2),
        "blend_file_bytes": blend_path.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("ALL43_18_STATS=" + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
