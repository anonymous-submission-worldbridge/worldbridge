"""Run all43_10 from all43_09 and render the unchanged commercial camera."""

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
SRC = ROOT / "infinigen/outputs/urban_v3_all43_09/urban_v3_all43_09.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_10"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_asset_refinement_generator_10 as G


def render(path):
    sc = bpy.context.scene
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        visible = o.name.startswith(
            (
                "all43_01:",
                "all43_02:",
                "all43_03:",
                "all43_05:",
                "all43_06:",
                "all43_07:",
                "all43_09:",
                G.P,
            )
        ) or any(c.name in keep for c in o.users_collection)
        if o.name.startswith("all43_03:tree_instance_"):
            visible = False
        o.hide_render = o.hide_render or not visible
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
    r = G.run()
    render(OUT / "urban_v3_all43_10.png")
    out = OUT / "urban_v3_all43_10.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "render": str(OUT / "urban_v3_all43_10.png"),
        "same_camera_light_exposure_resolution_as_all43_09": True,
        **r,
        "total_seconds": round(time.perf_counter() - t, 2),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_10_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
