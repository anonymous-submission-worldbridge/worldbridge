"""Additional camera-only photographs of the existing connected market scene."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/market"

# Positions and targets are in the original scene's world coordinates.
SHOTS = [
    ("01_inside_left_rear", (-6.8, 7.6, 2.25), (-1, -2.5, 1.35), 20),
    ("02_inside_right_rear", (5.8, 7.0, 2.3), (-1.5, -2, 1.35), 20),
    ("03_inside_center_deep", (-0.5, 7.8, 2.35), (-0.7, -2, 1.4), 18),
    ("04_inside_left_cross", (-7.3, 3.0, 2.0), (0.1, -1.4, 1.3), 18),
    ("05_inside_right_cross", (6.2, 4.1, 2.1), (-2, -1.4, 1.3), 18),
    ("06_inside_left_aisle", (-1.4, 5.5, 2.25), (-4.5, -2.5, 1.3), 20),
    ("07_inside_right_aisle", (2.0, 6.7, 2.15), (-2, -2.2, 1.35), 19),
    ("08_inside_produce_left", (-6.6, 2.4, 1.95), (-1, -2, 1.25), 19),
    ("09_inside_checkout", (5.9, 3.8, 1.9), (-0.2, -2.5, 1.25), 21),
    ("10_inside_front_panorama", (-0.65, 4.9, 2.15), (-0.65, -2.5, 1.3), 16),
    ("11_inside_left_elevated", (-6.5, 7.8, 2.9), (-1.5, -1.7, 1.15), 19),
    ("12_inside_right_elevated", (4.7, 5.8, 2.65), (-1.2, -1.7, 1.15), 19),
    ("13_outside_full_front", (-0.62, -10.8, 2.7), (-0.62, 1.5, 2.45), 23),
    ("14_outside_front_left", (-4.3, -9.5, 2.5), (-0.5, 2, 2.05), 22),
    ("15_outside_front_right", (3.3, -9.5, 2.5), (-0.7, 2, 2.05), 22),
    ("16_outside_entry_wide", (-0.65, -2.6, 2.05), (-0.65, 4.8, 1.45), 16),
    ("17_outside_entry_left", (-0.9, -0.6, 2.3), (-3, 4, 1.25), 16),
    ("18_outside_entry_right", (-0.3, -0.6, 2.3), (2, 4, 1.25), 16),
    ("19_outside_left_window", (-4.05, -1.55, 2.15), (-4, 5, 1.3), 20),
    ("20_outside_right_window", (2.5, -2, 2.2), (1.8, 5, 1.3), 22),
    ("21_outside_left_display", (-5.4, -5.1, 2.3), (-2.7, 2.5, 1.6), 23),
    ("22_outside_right_display", (4.5, -5.1, 2.3), (0.8, 2.8, 1.6), 23),
    ("23_overall_front_compact", (-0.62, -17, 4.0), (-0.62, 0.2, 2.3), 34),
    ("24_overall_left_compact", (-6, -16, 4.8), (-1.7, 0, 2.5), 34),
    ("25_overall_right_compact", (4.8, -16, 4.8), (0.5, 0, 2.5), 34),
    ("26_overall_left_terrace", (-6.8, -11, 3.1), (-2.2, 0, 2.1), 25),
    ("27_overall_right_terrace", (5.5, -11.4, 3.1), (0.5, 0, 2.1), 25),
    ("28_overall_elevated_front", (-0.62, -14, 7.5), (-0.62, -0.7, 2.1), 28),
    ("29_overall_elevated_left", (-6, -15, 7), (-1.8, 0, 2.2), 33),
    ("30_overall_elevated_right", (4.8, -15, 7), (0.5, 0, 2.2), 33),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preview", action="store_true")
    p.add_argument("--shots", default="")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    dest = MARKET / ("images2/.previews" if args.preview else "images2")
    dest.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(MARKET / "scene.blend"), load_ui=False)
    s = bpy.context.scene
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    devices = []
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
        if d.use:
            devices.append(d.name)
    if not devices:
        raise RuntimeError("OptiX GPU unavailable")
    s.render.engine = "CYCLES"
    s.cycles.device = "GPU"
    s.cycles.samples = 20 if args.preview else 128
    s.cycles.use_denoising = True
    s.cycles.denoising_use_gpu = True
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.04 if args.preview else 0.015
    s.render.use_persistent_data = True
    s.render.resolution_x = 800 if args.preview else 1920
    s.render.resolution_y = 450 if args.preview else 1080
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.image_settings.compression = 30
    s.render.film_transparent = False
    camera_data = bpy.data.cameras.new("Images2_camera")
    camera = bpy.data.objects.new("Images2_camera", camera_data)
    s.collection.objects.link(camera)
    s.camera = camera
    camera_data.clip_start = 0.05
    camera_data.clip_end = 2200
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = False
    selected = set(args.shots.split(",")) if args.shots else None
    report_path = dest / "render_manifest.json"
    report = (
        json.loads(report_path.read_text())
        if report_path.exists()
        else {
            "source_blend": str(MARKET / "scene.blend"),
            "engine": "CYCLES",
            "devices": devices,
            "resolution": [s.render.resolution_x, s.render.resolution_y],
            "samples": s.cycles.samples,
            "geometry_modified": False,
            "renders": {},
        }
    )
    for name, pos, target, lens in SHOTS:
        if selected and name[:2] not in selected and name not in selected:
            continue
        path = dest / (name + ".png")
        if path.exists() and not args.overwrite:
            continue
        camera.location = pos
        camera.rotation_euler = (
            (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        )
        camera_data.lens = lens
        s.view_layers.update()
        s.render.filepath = str(path)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        report["renders"][name] = {
            "file": path.name,
            "position": pos,
            "target": target,
            "lens_mm": lens,
            "seconds": round(time.monotonic() - start, 2),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("IMAGES2_DONE", name, flush=True)


if __name__ == "__main__":
    main()
