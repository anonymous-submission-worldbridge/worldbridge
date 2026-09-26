"""Additional physical camera views of the existing Corner Kitchen scene."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_urban_v1_full_connect import configure, pose

ROOT = Path(__file__).resolve().parents[1]
SCENE = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect/corner_kitchen"
)

# All coordinates are in the unchanged source scene's world space.
VIEWS = [
    ("01_far_front_overview", "Vision: Frontal building with courtyard", (0, -30, 16), (0, -8, 1.8), 28),
    ("02_far_right_overview", "Foreground: wide shot to the right front", (24, -28, 16), (0, -8, 2), 38),
    ("03_far_left_overview", "Foreground: wide-angle view to the left front", (-22, -27, 16), (0, -7, 2), 36),
    ("04_high_courtyard_overview", "Looking down: Relationship of courtyard space", (18, -20, 26), (0, -9, 1.5), 30),
    ("05_front_full_facade", "Medium shot: Full front facade visible", (0, -17, 4.2), (0, -4.8, 2.8), 25),
    ("06_front_left_angle", "Medium shot: Left front facade.", (-10, -14.5, 4.2), (0, -4.8, 2.3), 27),
    ("07_front_right_angle", "Medium shot: Right front facade.", (7, -16, 5), (0, -4.8, 2.3), 26),
    ("08_courtyard_eye_level", "yard: pedestrian perspective", (8, -16, 1.75), (0, -7.2, 1.5), 26),
    ("09_patio_and_windows", "Close-up: Terrace with glass window", (-7, -10, 2.3), (-3.2, -5.3, 1.5), 32),
    ("10_entry_close", "Close-up: Entrance to indoor area", (6.3, -8.1, 1.8), (5.3, -2.8, 1.5), 30),
    ("11_interior_front_left", "In the room: looking out the window at the counter.", (-6.7, -3.65, 1.85), (1.5, 0.5, 1.4), 22),
    ("12_interior_rear_left", "Inside: Looking towards the entrance from behind.", (-6.7, 2.05, 1.85), (0.8, -3.2, 1.4), 23),
    ("13_interior_rear_right", "Kitchen: Looking towards the dining area.", (6.5, -0.1, 1.9), (-3.4, -2, 1.25), 24),
    ("14_dining_to_courtyard", "Kitchen: Looking out to the courtyard.", (-3.5, 1.8, 1.8), (-1.8, -6.5, 1.3), 25),
    ("15_counter_frontal", "Medium close-up: Point-of-sale and pickup counter", (3.5, -3.25, 1.85), (3.4, 1.5, 1.5), 30),
    ("16_counter_oblique_close", "Close-up: Details of the counter side panel", (0.3, -1.2, 1.8), (3.45, 1.2, 1.25), 40),
    ("17_dining_table_close", "Close-up: Tableware", (-1.5, -0.65, 2.15), (-3.25, -2.15, 1.1), 48),
    (
        "18_window_table_close",
        "Close-up: Double-person table by the window",
        (-6.95, -1.1, 1.75),
        (-5.55, -2.55, 1.05),
        38,
    ),
    ("19_patio_table_close", "Close-up: Outdoor furniture", (1.1, -9.7, 1.9), (3.55, -7.22, 0.95), 42),
    ("20_sign_and_canopy_close", "Close-up: Sign and awning", (0, -12, 5.5), (0, -4.9, 4.6), 24),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--shots", default="")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    out = SCENE / "images2"
    out.mkdir(exist_ok=True)
    target_dir = out / ".previews" if args.preview else out
    target_dir.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SCENE / "scene.blend"), load_ui=False)
    scene = bpy.context.scene
    devices = configure(
        scene, 640 if args.preview else 1920, 16 if args.preview else 96
    )
    scene.camera.data.dof.use_dof = False
    selected = set(args.shots.split(",")) if args.shots else None
    report_path = target_dir / "render_manifest.json"
    report = (
        json.loads(report_path.read_text())
        if report_path.exists()
        else {
            "source_blend": str(SCENE / "scene.blend"),
            "engine": "CYCLES",
            "devices": devices,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": scene.cycles.samples,
            "renders": [],
        }
    )
    for name, label, position, target, lens in VIEWS:
        if selected and name not in selected:
            continue
        path = target_dir / (name + ".png")
        if path.exists() and not args.overwrite:
            continue
        pose(scene, position, target, lens)
        scene.render.filepath = str(path)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        entry = dict(
            name=name,
            description=label,
            file=str(path),
            position=position,
            target=target,
            lens_mm=lens,
            seconds=round(time.monotonic() - start, 2),
        )
        report["renders"] = [r for r in report["renders"] if r["name"] != name] + [
            entry
        ]
        report["renders"].sort(key=lambda r: r["name"])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("IMAGES2_DONE " + name, flush=True)


if __name__ == "__main__":
    main()
