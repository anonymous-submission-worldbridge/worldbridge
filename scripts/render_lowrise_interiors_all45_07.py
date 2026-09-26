"""Render true Infinigen Indoor views from the saved all45_07 scene."""
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
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_07"
RENDERS = OUT / "renders"
PREFIX = "all45_07:indoor_render:"


def world_point(instance, source_point):
    return instance.matrix_world @ Vector(source_point)


def add_camera(name, instance, source_location, source_target, fov):
    location = world_point(instance, source_location)
    target = world_point(instance, source_target)
    data = bpy.data.cameras.new(PREFIX + name + "_data")
    data.lens_unit = "FOV"
    data.angle = math.radians(fov)
    data.clip_start = 0.025
    camera = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    return camera, target


def add_fill(name, location, target):
    data = bpy.data.lights.new(PREFIX + name + "_data", "AREA")
    data.energy = 260
    data.color = (1.0, 0.78, 0.58)
    data.shape = "DISK"
    data.size = 2.2
    light = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location + Vector((0, 0, 0.35))
    light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    return light


def main():
    started = time.time()
    RENDERS.mkdir(parents=True, exist_ok=True)
    master = bpy.data.collections.get("all45_07:MASTER_native_infinigen_indoor")
    if master is None:
        raise RuntimeError("Native Infinigen Indoor master is absent from all45_07")
    instances = sorted(
        [obj for obj in bpy.data.objects if obj.get("native_infinigen_indoor") is True],
        key=lambda obj: obj.name,
    )
    if len(instances) != 12:
        raise RuntimeError(
            f"Expected 12 low-rise Indoor instances, found {len(instances)}"
        )
    target_instance = next(
        obj
        for obj in instances
        if obj.name == "all45_07:townhouse_01_native_indoor_floor_0"
    )
    # Only the inspected ground-floor instance is needed in these views. This
    # reduces render memory without changing the saved blend or the generated scene.
    for obj in instances:
        obj.hide_render = obj != target_instance

    # Render-only architectural cutaway: keep every generated furniture asset and
    # floor, but omit room walls/ceilings so the camera cannot be occluded. The
    # blend file is never saved by this script, so the generated scene stays intact.
    cutaway_objects = [
        obj
        for obj in master.all_objects
        if obj.name.endswith((".wall", ".ceiling", ".exterior"))
    ]
    for obj in cutaway_objects:
        obj.hide_render = True

    names = [obj.name for obj in master.all_objects]
    furniture = {
        "beds": sum("BedFactory" in name for name in names),
        "dining_tables": sum("TableDiningFactory" in name for name in names),
        "kitchen_cabinets": sum("KitchenCabinetFactory" in name for name in names),
        "kitchen_spaces": sum("KitchenSpaceFactory" in name for name in names),
        "ovens": sum("OvenFactory" in name for name in names),
        "tv_stands": sum("TVStandFactory" in name for name in names),
        "bookcases": sum("BookcaseFactory" in name for name in names),
        "rugs": sum("RugFactory" in name for name in names),
    }
    if sum(furniture.values()) == 0:
        raise RuntimeError("The low-rise Indoor source has no placed furniture")

    specs = [
        (
            "07_lowrise_interior_living_dining",
            (11.15, 3.15, 1.52),
            (13.74, 5.29, 0.66),
            68,
            "Dining-room view toward the generated TableDiningFactory asset",
        ),
        (
            "08_lowrise_interior_kitchen",
            (11.15, 1.45, 1.48),
            (14.35, -0.70, 0.88),
            70,
            "Kitchen view toward generated cabinets, oven and KitchenSpaceFactory assembly",
        ),
        (
            "09_lowrise_interior_bedroom",
            (1.10, 7.20, 1.48),
            (6.18, 9.77, 0.78),
            64,
            "Bedroom view toward the generated BedFactory asset",
        ),
    ]

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    scene.render.resolution_x = 900
    scene.render.resolution_y = 560
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"

    rendered = []
    for name, source_location, source_target, fov, description in specs:
        camera, target = add_camera(
            name, target_instance, source_location, source_target, fov
        )
        fill = add_fill(name + "_fill", camera.location, target)
        scene.camera = camera
        filepath = RENDERS / f"{name}.png"
        scene.render.filepath = str(filepath)
        bpy.ops.render.render(write_still=True)
        rendered.append(
            {
                "file": str(filepath),
                "description": description,
                "source_camera": list(source_location),
                "source_target": list(source_target),
            }
        )
        bpy.data.objects.remove(fill, do_unlink=True)
        print(f"[all45_07 indoor] rendered {filepath.name}", flush=True)

    audit = {
        "source_blend": str(OUT / "urban_v3_all45_07.blend"),
        "native_infinigen_indoor_master": master.name,
        "master_object_count": len(master.all_objects),
        "lowrise_indoor_instance_count": len(instances),
        "rendered_instance": target_instance.name,
        "furniture_counts": furniture,
        "render_engine": "CYCLES",
        "samples": 32,
        "temporary_cutaway": {
            "enabled": True,
            "hidden_architecture_object_count": len(cutaway_objects),
            "hidden_suffixes": [".wall", ".ceiling", ".exterior"],
            "saved_to_blend": False,
        },
        "renders": rendered,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (OUT / "lowrise_interior_render_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print("LOWRISE_INTERIOR_AUDIT=" + json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
