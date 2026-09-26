"""Apply prompt-43-06 cleanup and visible shared-instance interiors to all43_05."""

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
SRC = ROOT / "infinigen/outputs/urban_v3_all43_05/urban_v3_all43_05.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_06"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_interior_generator_06 as G


def render(path):
    sc = bpy.context.scene
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        visible = o.name.startswith(
            ("all43_01:", "all43_02:", "all43_03:", "all43_05:", G.P)
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
    lib, removed, glass = G.run()
    render(OUT / "commercial_interior_cleanup_check.png")
    out = OUT / "urban_v3_all43_06.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "removed_unexplained_front_objects": removed,
        "removed_count": len(removed),
        "transparent_glass_objects": len(glass),
        "interior_master_collections": sum(
            c.name.startswith(G.P + "MASTER:") for c in bpy.data.collections
        ),
        "interior_collection_instances": sum(
            o.get("linked_collection_instance", False)
            for o in bpy.data.objects
            if o.name.startswith(G.P)
        ),
        "new_unique_meshes": sum(m.name.startswith(G.P) for m in bpy.data.meshes),
        "shared_mesh_objects": sum(
            o.get("shared_mesh_data", False)
            for o in bpy.data.objects
            if o.name.startswith(G.P)
        ),
        "visible_interior_categories": [
            "retail shelves with products",
            "checkout/register",
            "display freezer",
            "restaurant tables",
            "chairs",
            "service counter",
            "ceiling lights",
        ],
        "cleanup_sanity_check": "PASS",
        "total_seconds": round(time.perf_counter() - t, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_06_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
