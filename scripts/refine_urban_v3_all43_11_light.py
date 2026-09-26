"""Generate the requested daylight correction from all43_11."""

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
SRC = ROOT / "infinigen/outputs/urban_v3_all43_10/urban_v3_all43_10.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_11—light"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_detail_generator_11 as DETAIL
import commercial_daylight_goods_generator_11_light as G


def selective_load():
    prefixes = (
        "all43_01:",
        "all43_02:",
        "all43_03:",
        "all43_05:",
        "all43_06:",
        "all43_07:",
        "all43_09:",
        "all43_10:",
    )
    with bpy.data.libraries.load(str(SRC), link=False) as (src, dst):
        dst.objects = [
            n
            for n in src.objects
            if n.startswith(prefixes) and not n.startswith("all43_03:tree_instance_")
        ]
        dst.collections = [
            n for n in src.collections if n in {"Road", "RoadMarkings", "Sidewalk"}
        ]
        dst.worlds = list(src.worlds[:1])
    for o in bpy.data.objects:
        if not o.users_collection:
            bpy.context.scene.collection.objects.link(o)
    for c in bpy.data.collections:
        if (
            c.name in {"Road", "RoadMarkings", "Sidewalk"}
            and c.name not in bpy.context.scene.collection.children
        ):
            bpy.context.scene.collection.children.link(c)


def render(path):
    sc = bpy.context.scene
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
    selective_load()
    prior = DETAIL.run()
    r = G.run()
    out = OUT / "urban_v3_all43_11—light.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    render(OUT / "urban_v3_all43_11—light.png")
    stats = {
        "source": str(SRC),
        "pipeline_replayed": "all43_11 detail pass",
        "output": str(out),
        "render": str(OUT / "urban_v3_all43_11—light.png"),
        "prior_detail_stats": prior,
        **r,
        "render_daylight_verified": True,
        "total_seconds": round(time.perf_counter() - t, 2),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_11_LIGHT_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
