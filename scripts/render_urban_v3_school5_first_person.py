"""Human-eye-height views of the existing school5 scene; source is read-only."""
import argparse
import json
import math
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
    ("pov01_main_gate", "Pedestrian perspective from the entrance facing forward", (28, -114, 1.9), (28, -4, 4), 25),
    ("pov02_gate_sports_and_teaching", "From the main entrance of the campus, view along the central axis.", (31, -74, 1.9), (28, -8, 4), 23),
    ("pov03_running_track", "Looking at the teaching building from the runway.", (-92, -63, 1.99), (-26, 35, 4), 28),
    ("pov04_field_and_teaching", "Watching the gymnasium and teaching building from the playground.", (-91, -16, 2.0), (-6, 24, 4), 28),
    ("pov05_volleyball_courtside", "First-person view inside an indoor volleyball court", (91, -76, 2.02), (61, -38, 4), 24),
    ("pov06_auditorium_plaza", "Walking Square and Round Hall", (26, -63, 1.95), (5, -29, 4), 28),
    ("pov07_academic_courtyard", "Pedestrian perspective within the courtyard of the teaching building", (26, 26, 1.95), (9, 65, 5), 24),
    ("pov08_east_teaching_walk", "pedestrian space in front of the teaching building", (67, 8, 1.95), (86, 40, 5), 24),
    (
        "pov09_gate_160deg_panorama",
        "The width of 160 degrees at the entrance to the main gate: teaching building, playground, and volleyball court.",
        (28, -76, 1.95),
        (28, 0, 1.95),
        24,
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
    destination = OUT / "_preview_first_person" if args.preview else OUT
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
    depsgraph = bpy.context.evaluated_depsgraph_get()

    records = []
    for name, label, location, target, lens in VIEWS:
        data = bpy.data.cameras.new("first_person:" + name)
        camera = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(camera)
        # Ground contact is measured at the camera's XY; reject elevated props.
        hit, floor, normal, face, obj, matrix = scene.ray_cast(
            depsgraph,
            Vector((location[0], location[1], 2.5)),
            Vector((0, 0, -1)),
            distance=4,
        )
        if not hit or not -0.2 <= floor.z <= 0.55:
            raise RuntimeError(f"Invalid pedestrian position: {name}, {floor}, {obj}")
        location = (location[0], location[1], floor.z + 1.65)
        camera.location = location
        camera.rotation_euler = (
            (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        data.lens = lens
        data.sensor_width = 36
        data.shift_y = 0.0
        data.clip_start = 0.1
        data.clip_end = 2500
        data.dof.use_dof = False
        if name.startswith("pov09"):
            data.type = "PANO"
            data.panorama_type = "EQUIRECTANGULAR"
            data.longitude_min, data.longitude_max = math.radians(-80), math.radians(80)
            data.latitude_min, data.latitude_max = math.radians(-25), math.radians(25)
        resolution = (4000, 1250) if name.startswith("pov09") else (3200, 1800)
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
                ground_z=floor.z,
                eye_height_m=1.65,
                projection=data.type,
                exposure=-1.3 if name.startswith("pov08") else -2.0,
            )
        )
        if selected and name[3:5] not in selected:
            continue
        scene.camera = camera
        scene.view_settings.exposure = records[-1]["exposure"]
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
        camera_eye_height_m=1.65,
        views=records,
    )
    (
        destination
        / ("first_person_manifest_" + (args.only.replace(",", "_") or "all") + ".json")
    ).write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not args.preview and not selected:
        scene.camera = bpy.data.objects["first_person:" + VIEWS[0][0]]
        scene.render.resolution_x, scene.render.resolution_y = 3200, 1800
        scene.render.filepath = str(OUT / (VIEWS[0][0] + ".png"))
        scene.view_settings.exposure = -2.0
        bpy.ops.wm.save_as_mainfile(
            filepath=str(OUT / "school5_first_person_cameras.blend")
        )


if __name__ == "__main__":
    main()
