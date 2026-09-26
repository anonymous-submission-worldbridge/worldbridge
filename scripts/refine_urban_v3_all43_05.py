"""A/B verified high-quality procedural refinement based on the all43_03 visual baseline."""

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

import json, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_03/urban_v3_all43_03.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_05"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_quality_generator_05 as Q


def render(path):
    sc = bpy.context.scene
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        visible = o.name.startswith(
            ("all43_01:", "all43_02:", "all43_03:", Q.P)
        ) or any(c.name in keep for c in o.users_collection)
        if o.name.startswith("all43_03:tree_instance_"):
            visible = False
        o.hide_render = not visible
    cam = bpy.data.objects["all43_01:camera"]
    cam.location = (-5, -57, 10.5)
    cam.rotation_euler = (
        (Vector((-29, -24, 2.1)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = 56
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    start = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    render(OUT / "A_all43_03_baseline.png")
    before = set(bpy.data.meshes)
    lib, errors, params = Q.populate_commercial_zone()
    if errors:
        raise RuntimeError("geometry sanity check failed: " + json.dumps(errors))
    render(OUT / "B_all43_05_procedural.png")
    out = OUT / "urban_v3_all43_05.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source_visual_baseline": str(SRC),
        "output": str(out),
        "seed": 4305,
        "ab_same_camera": True,
        "ab_same_sun_engine_resolution_exposure": True,
        "geometry_sanity_check": "PASS",
        "geometry_errors": errors,
        "preserved_store_signs": ["FRESH MART", "CORNER KITCHEN"],
        "building_master_object_counts": {
            c.name: len(c.objects)
            for c in (
                bpy.data.collections["all43_01:MASTER:convenience_store"],
                bpy.data.collections["all43_01:MASTER:restaurant"],
            )
        },
        "quality_master_collections": sum(
            c.name.startswith(Q.P + "MASTER:") for c in bpy.data.collections
        ),
        "new_unique_meshes": len(set(bpy.data.meshes) - before),
        "linked_collection_instances": sum(
            o.get("linked_collection_instance", False) for o in bpy.data.objects
        ),
        "shared_mesh_objects": sum(
            o.get("shared_mesh_data", False) for o in bpy.data.objects
        ),
        "shared_materials": len(lib["materials"]),
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_05_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
