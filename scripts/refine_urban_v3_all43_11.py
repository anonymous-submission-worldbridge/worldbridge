"""Run all43_11 from all43_10 and render the same commercial view."""

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
OUT = ROOT / "infinigen/outputs/urban_v3_all43_11"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_detail_generator_11 as G


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
        if c.name in {"Road", "RoadMarkings", "Sidewalk"} and not any(
            x == c for x in bpy.context.scene.collection.children
        ):
            bpy.context.scene.collection.children.link(c)
    source_world = next(
        (
            w
            for w in bpy.data.worlds
            if w.use_nodes
            and any(n.bl_idname == "ShaderNodeTexSky" for n in w.node_tree.nodes)
        ),
        None,
    )
    if source_world:
        bpy.context.scene.world = source_world


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
                "all43_10:",
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
    # Match the darker commercial comparison grade used by the source scene.
    sc.view_settings.exposure = -1.0
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


def trim_render_copy():
    # Called only after the complete blend is saved. Release objects excluded from this fixed view.
    doomed = [o for o in bpy.data.objects if o.hide_render]
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.orphans_purge(do_recursive=True)
    return len(doomed)


def main():
    t = time.perf_counter()
    if Path(bpy.data.filepath).resolve() != SRC.resolve():
        selective_load()
    print("ALL43_11_STAGE=loaded", flush=True)
    r = G.run()
    print("ALL43_11_STAGE=detail_complete", flush=True)
    out = OUT / "urban_v3_all43_11.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print("ALL43_11_STAGE=saved", flush=True)
    # Establish visibility, then trim only the ephemeral in-memory render copy.
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
                "all43_10:",
                G.P,
            )
        ) or any(c.name in keep for c in o.users_collection)
        if o.name.startswith("all43_03:tree_instance_"):
            visible = False
        o.hide_render = o.hide_render or not visible
    trimmed = trim_render_copy()
    render(OUT / "urban_v3_all43_11.png")
    stats = {
        "source": str(SRC),
        "load_mode": "selective visible-scene append",
        "output": str(out),
        "render": str(OUT / "urban_v3_all43_11.png"),
        "same_camera_light_exposure_resolution_as_all43_10": True,
        **r,
        "render_copy_objects_trimmed": trimmed,
        "total_seconds": round(time.perf_counter() - t, 2),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_11_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
