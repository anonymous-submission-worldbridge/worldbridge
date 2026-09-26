"""Additional presentation cameras for the existing school5 scene; source is read-only."""
import argparse
import json
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_school5/urban_v3_school5.blend"
)
OUT = SOURCE.parent / "renders2"
VIEWS = [
    (
        "01_main_gate_complete_campus",
        "Front view of campus showing main gate: teaching building, playground, double lane court.",
        (28, -285, 160),
        (0, -10, 3),
        38,
    ),
    ("02_main_gate_elevated_wide", "Main entrance raised to wide-angle: entry connects with campus functional areas", (28, -205, 90), (2, -18, 3), 28),
    (
        "03_southwest_campus_panorama",
        "Southwest Overview: Layers of Playground and Teaching Buildings",
        (-235, -265, 205),
        (0, -9, 3),
        44,
    ),
    (
        "04_southeast_campus_panorama",
        "Southeast panoramic view: double basketball court, main entrance, teaching building",
        (240, -285, 210),
        (0, -10, 3),
        46,
    ),
    (
        "05_athletics_and_academic_buildings",
        "Playfield adjacent to the teaching building: Sports area display",
        (-195, -155, 140),
        (-37, -4, 3),
        38,
    ),
    ("06_volleyball_courts_and_campus", "tennis courts and campus buildings", (121, -135, 42), (63, -49, 3), 44),
    ("07_academic_courtyards", "Grouping of teaching buildings and inner courtyard", (192, 152, 130), (35, 32, 6), 46),
    (
        "08_gate_axis_and_architecture",
        "Main entrance axis, circular auditorium, and teaching building facades",
        (28, -148, 28),
        (28, -45, 4),
        32,
    ),
]


def main():
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--gpu", type=int, default=6)
    parser.add_argument("--samples", type=int, default=128)
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "_preview" if args.preview else OUT
    destination.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    devices = [d for d in prefs.devices if d.type == "OPTIX"]
    if args.gpu >= len(devices):
        raise RuntimeError(f"GPU {args.gpu} unavailable: {list(prefs.devices)}")
    for device in prefs.devices:
        device.use = device == devices[args.gpu]
    print("DEVICE", devices[args.gpu].name, devices[args.gpu].id, flush=True)
    scene.cycles.device = "GPU"
    scene.cycles.samples = 16 if args.preview else args.samples
    scene.cycles.use_denoising = True
    scene.cycles.adaptive_threshold = 0.04 if args.preview else 0.01
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 6
    scene.render.use_persistent_data = True
    scene.render.resolution_x = 960 if args.preview else 2560
    scene.render.resolution_y = 600 if args.preview else 1600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -2.0
    selected = set(args.only.split(",")) if args.only else set()
    records = []
    for name, label, location, target, lens in VIEWS:
        data = bpy.data.cameras.new("renders2:" + name)
        camera = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(camera)
        camera.location = location
        camera.rotation_euler = (
            (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        data.lens = lens
        data.sensor_width = 36
        data.shift_y = {"01": -0.035, "02": -0.03, "03": -0.045, "04": -0.045}.get(
            name[:2], 0
        )
        data.clip_start = 0.1
        data.clip_end = 2500
        data.dof.use_dof = False
        resolution = {"01": (3200, 1800), "02": (3200, 1600)}.get(
            name[:2], (2560, 1600)
        )
        camera["render_resolution_x"], camera["render_resolution_y"] = resolution
        scene.render.resolution_x, scene.render.resolution_y = (
            (960, round(960 * resolution[1] / resolution[0]))
            if args.preview
            else resolution
        )
        records.append(
            dict(
                file=name + ".png",
                title=label,
                location=location,
                target=target,
                lens_mm=lens,
                shift_y=data.shift_y,
                resolution=list(resolution),
            )
        )
        if selected and name[:2] not in selected:
            continue
        scene.camera = camera
        scene.render.filepath = str(destination / (name + ".png"))
        started = time.monotonic()
        print("RENDER_START", name, flush=True)
        bpy.ops.render.render(write_still=True)
        records[-1]["seconds"] = round(time.monotonic() - started, 2)
        print("RENDER_DONE", name, records[-1]["seconds"], flush=True)
        (destination / (name + ".json")).write_text(
            json.dumps(records[-1], ensure_ascii=False, indent=2)
        )
    manifest = dict(
        source=str(SOURCE),
        preview=args.preview,
        engine="CYCLES",
        device=devices[args.gpu].name,
        samples=scene.cycles.samples,
        source_geometry_unchanged=True,
        views=records,
    )
    (
        destination / ("manifest_" + (args.only.replace(",", "_") or "all") + ".json")
    ).write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not args.preview and not selected:
        scene.camera = bpy.data.objects["renders2:" + VIEWS[0][0]]
        scene.render.resolution_x, scene.render.resolution_y = 3200, 1800
        scene.render.filepath = str(OUT / (VIEWS[0][0] + ".png"))
        bpy.ops.wm.save_as_mainfile(
            filepath=str(OUT / "school5_showcase_cameras.blend")
        )


if __name__ == "__main__":
    main()
