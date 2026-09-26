"""Run the reusable commercial generator, test it, then integrate into all43_03."""

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

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_03/urban_v3_all43_03.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_04"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_zone_generator as C


def render(path, res, samples, test=False):
    sc = bpy.context.scene
    old = {o: o.hide_render for o in sc.objects}
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        visible = (
            o.name.startswith(C.P)
            or o.name in {"all43_01:convenience_store", "all43_01:restaurant"}
            or o.name.startswith("all43_02:vehicle:")
            or any(c.name in keep for c in o.users_collection)
        )
        o.hide_render = not visible
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for o, v in old.items():
        o.hide_render = v


def main():
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    loaded = time.perf_counter()
    root = bpy.data.collections["all43_01:commercial_root"]
    # Old hand-positioned parking furniture is superseded by generator output.
    for o in list(bpy.data.objects):
        if o.name.startswith(
            (
                "all43_03:wheelstop_",
                "all43_03:03_stall_",
                "all43_01:stall_line",
                "all43_01:wheelstop_",
            )
        ):
            bpy.data.objects.remove(o, do_unlink=True)
    zone, lib, meta = C.generate_commercial_zone(root, seed=4304)
    # Align four existing OpenX linked-asset vehicle instances to generated stalls.
    positions = {
        "all43_02:vehicle:audi_tt": (-29, -38, 0.18),
        "all43_02:vehicle:tucson": (-23.7, -38, 0.18),
        "all43_02:vehicle:ducato": (-18.4, -38, 0.18),
        "all43_02:vehicle:audi_q7": (-13.1, -38, 0.18),
    }
    for n, p in positions.items():
        if bpy.data.objects.get(n):
            bpy.data.objects[n].location = p
    # Mandatory isolated low-sample generator test before full scene save.
    render(OUT / "commercial_generator_test.png", (640, 420), 1, True)
    out = OUT / "urban_v3_all43_04.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    render(OUT / "commercial_final.png", (1280, 720), 24)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    newobjs = [o for o in bpy.data.objects if o.name.startswith(C.P)]
    meshes = {o.data.as_pointer() for o in newobjs if o.type == "MESH"}
    shared = [o for o in newobjs if o.type == "MESH" and o.data.users > 1]
    stats = {
        "source": str(SRC),
        "output": str(out),
        "seed": 4304,
        "generator_functions": [
            "prepare_commercial_asset_library",
            "generate_storefront",
            "generate_store_interior_proxy",
            "generate_commercial_frontage",
            "generate_parking_lot",
            "populate_commercial_details",
        ],
        "master_collections": len(lib.masters),
        "unique_mesh_count": len(meshes),
        "object_count": len(newobjs),
        "instance_count": sum(o.instance_type == "COLLECTION" for o in newobjs),
        "shared_mesh_object_count": len(shared),
        "unique_material_count": len(lib.mats),
        "vehicle_instances_repositioned": positions,
        "generation_seconds": round(meta["generation_seconds"], 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_04_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
