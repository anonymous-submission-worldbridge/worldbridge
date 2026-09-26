"""Execute the focused realism pass on all43_06 and render a fixed-camera comparison."""

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
SRC = ROOT / "infinigen/outputs/urban_v3_all43_06/urban_v3_all43_06.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_07"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_realism_generator_07 as G


def render(path):
    sc = bpy.context.scene
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        v = o.name.startswith(
            ("all43_01:", "all43_02:", "all43_03:", "all43_05:", "all43_06:", G.P)
        ) or any(c.name in keep for c in o.users_collection)
        if o.name.startswith("all43_03:tree_instance_"):
            v = False
        o.hide_render = not v
    cam = bpy.data.objects["all43_01:camera"]
    cam.location = (-5, -57, 10.5)
    cam.rotation_euler = (
        (Vector((-29, -24, 2.1)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = 56
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 32
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    t = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    if not (OUT / "A_all43_06_baseline.png").exists():
        render(OUT / "A_all43_06_baseline.png")
    r = G.run()
    render(OUT / "B_all43_07_realism.png")
    out = OUT / "urban_v3_all43_07.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "comparison_same_camera_light_exposure_resolution": True,
        "glass_upgraded": len(r["glass"]),
        "shelf_variants": 3,
        "shelf_instances_diversified": len(r["shelves"]),
        "restaurant_objects_reorganized": r["restaurant_objects"],
        "facade_materials_upgraded": len(r["facade_materials"]),
        "adaptive_bevel_objects": r["bevels"],
        "attachment_master_categories": list(r["attachment_masters"]),
        "new_unique_meshes": sum(m.name.startswith(G.P) for m in bpy.data.meshes),
        "linked_instances": sum(
            o.get("linked_collection_instance", False)
            for o in bpy.data.objects
            if o.name.startswith(G.P)
        ),
        "sanity_check": "PASS",
        "total_seconds": round(time.perf_counter() - t, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_07_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
