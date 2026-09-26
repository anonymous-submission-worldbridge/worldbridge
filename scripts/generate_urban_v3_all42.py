"""Build all42 from the all41 visual baseline with all39_fast5 vegetation instances.

Default mode opens the immutable all41 blend for a lossless visual migration.
Use ``-- --rebuild`` to run the original all41 source pipeline in-memory first;
that mode is intentionally slower because the legacy all41 script also renders.
"""
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


import ast
import json
import math
import random
import re
import runpy
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
ALL41_BLEND = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
ALL41_SCRIPT = ROOT / "scripts/generate_urban_v3_all41.py"
FAST5_SCRIPT = ROOT / "scripts/refine_urban_v3_all39_fast5.py"
OUT = ROOT / "infinigen/outputs/urban_v3_all42"
OUT.mkdir(parents=True, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
REBUILD = "--rebuild" in ARGS
SMOKE = "--smoke" in ARGS
STARTED = time.perf_counter()


def log(message):
    print(f"[all42] {message}", flush=True)


def scene_counts():
    return {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "collections": len(bpy.data.collections),
    }


if REBUILD:
    log(f"formal rebuild through {ALL41_SCRIPT}")
    runpy.run_path(str(ALL41_SCRIPT), run_name="__main__")
else:
    if not ALL41_BLEND.exists():
        raise FileNotFoundError(ALL41_BLEND)
    log(f"opening visual baseline {ALL41_BLEND}")
    bpy.ops.wm.open_mainfile(filepath=str(ALL41_BLEND))

BASELINE = scene_counts()
BASELINE_CAMERAS = {}
for name in (
    "cam_overview",
    "cam_residential",
    "cam_park",
    "cam_commercial",
    "cam_intersection",
    "cam_int_furniture",
    "cam_int_window",
):
    cam = bpy.data.objects.get(name)
    if cam:
        BASELINE_CAMERAS[name] = {
            "location": list(cam.location),
            "rotation_euler": list(cam.rotation_euler),
            "angle": float(cam.data.angle),
        }
log(f"baseline counts {BASELINE}")


# Reuse the exact, reviewed all39_fast5 vegetation implementation.  Extracting
# named functions avoids executing that module's top-level all34/house pipeline.
FAST5_FUNCTIONS = {
    "_base_name",
    "_faces",
    "_safe_height",
    "_bbox_world",
    "_get_target_collection",
    "_new_collection_instance",
    "_tree_roots",
    "_protect_leaf_assets",
    "_local_bbox_mesh",
    "_tree_factory_id",
    "_leaf_assets_for_tree",
    "_sample_canopy_points",
    "_create_visible_leaf_canopy",
    "_make_tree_prototype",
    "_find_shrub_pairs",
    "_make_shrub_prototype",
    "_purge_factory_asset_collections",
    "optimize_existing_vegetation",
}
tree = ast.parse(FAST5_SCRIPT.read_text(encoding="utf-8"), filename=str(FAST5_SCRIPT))
selected = [
    node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in FAST5_FUNCTIONS
]
missing = FAST5_FUNCTIONS - {node.name for node in selected}
if missing:
    raise RuntimeError(f"fast5 function extraction incomplete: {sorted(missing)}")
namespace = {"bpy": bpy, "Vector": Vector, "math": math, "random": random, "re": re}
exec(
    compile(ast.Module(body=selected, type_ignores=[]), str(FAST5_SCRIPT), "exec"),
    namespace,
)

tree_roots_before = namespace["_tree_roots"]()
if not tree_roots_before:
    raise RuntimeError("all41 contains no eligible Park TreeFactory roots")
log(f"migrating {len(tree_roots_before)} TreeFactory roots with exact fast5 optimizer")
namespace["optimize_existing_vegetation"]()


# Stable master/instance hierarchy and metadata. Prototype collections remain
# unlinked from the visible scene and are rendered only through their instances.
masters_root = bpy.data.collections.get("C2W_MASTERS") or bpy.data.collections.new(
    "C2W_MASTERS"
)
masters_root["c2w_role"] = "master_root"
# The master root intentionally stays outside the visible scene hierarchy so
# prototypes render only through collection instances. Preserve that unlinked ID.
masters_root.use_fake_user = True
instance_root = bpy.data.collections.get("C2W_INSTANCES")
if instance_root is None:
    instance_root = bpy.data.collections.new("C2W_INSTANCES")
    bpy.context.scene.collection.children.link(instance_root)
instance_root["c2w_role"] = "instance_root"

tree_proto_colls = sorted(
    [c for c in bpy.data.collections if c.name.startswith("All39Fast5_TreePrototype_")],
    key=lambda c: c.name,
)
shrub_proto_colls = sorted(
    [
        c
        for c in bpy.data.collections
        if c.name.startswith("All39Fast5_ShrubPrototype_")
    ],
    key=lambda c: c.name,
)
for coll in tree_proto_colls + shrub_proto_colls:
    coll["c2w_role"] = "master"
    coll["c2w_asset_id"] = (
        "vegetation.tree." if coll in tree_proto_colls else "vegetation.shrub."
    ) + coll.name
    if coll.name not in masters_root.children:
        masters_root.children.link(coll)
    for obj in coll.all_objects:
        obj["c2w_role"] = "master"
        obj["c2w_asset_id"] = coll["c2w_asset_id"]

tree_instances = sorted(
    [o for o in bpy.data.objects if o.name.startswith("all39_fast5_tree_inst_")],
    key=lambda o: o.name,
)
shrub_instances = sorted(
    [o for o in bpy.data.objects if o.name.startswith("all39_fast5_shrub_inst_")],
    key=lambda o: o.name,
)
for idx, obj in enumerate(tree_instances + shrub_instances):
    obj["c2w_role"] = "instance"
    obj["c2w_instance_id"] = obj.name
    obj["c2w_asset_id"] = (
        obj.instance_collection.get("c2w_asset_id", "")
        if obj.instance_collection
        else ""
    )
    obj["c2w_source"] = str(FAST5_SCRIPT)
    obj["c2w_variant"] = obj.instance_collection.name if obj.instance_collection else ""
    obj["c2w_run_id"] = "urban_v3_all42"


HOUSE_SOURCES = {
    "House_large_indoor": ROOT
    / "infinigen/outputs/urban_v3_all41_house_large/scene.blend",
    "House_small_a_indoor": ROOT
    / "infinigen/outputs/urban_v3_all41_house_small_a/scene.blend",
    "House_small_b_indoor": ROOT
    / "infinigen/outputs/urban_v3_all41_house_small_b/scene.blend",
}
house_report = {}
for coll_name, source in HOUSE_SOURCES.items():
    coll = bpy.data.collections.get(coll_name)
    objects = list(coll.all_objects) if coll else []
    meshes = [o for o in objects if o.type == "MESH"]
    if not objects:
        raise RuntimeError(f"required all41 house collection missing: {coll_name}")
    for obj in objects:
        obj["c2w_source"] = str(source)
        obj["c2w_asset_id"] = "residential.house." + coll_name.lower()
        obj[
            "c2w_role"
        ] = "unique"  # one locally enhanced variant; preserve interiors/materials
        obj["c2w_unique_reason"] = "all41 local roof/material/interior enhancement"
    house_report[coll_name] = {
        "source": str(source),
        "objects": len(objects),
        "meshes": len(meshes),
        "source_exists": source.exists(),
    }

apartment = bpy.data.collections.get("Residential_apartment_exterior")
if apartment is None:
    candidates = [c for c in bpy.data.collections if "Apartment" in c.name]
    apartment = candidates[0] if candidates else None
if apartment is None:
    raise RuntimeError("all41 apartment collection missing")
house_report[apartment.name] = {
    "source": "all41 verified procedural asset",
    "objects": len(apartment.all_objects),
}


scene = bpy.context.scene
scene["c2w_pipeline"] = "urban_v3_all42"
scene["c2w_visual_baseline"] = str(ALL41_BLEND)
scene["c2w_tree_baseline"] = str(FAST5_SCRIPT)
if SMOKE:
    scene.cycles.samples = min(scene.cycles.samples, 32)
    scene.render.resolution_percentage = 50

OUT_BLEND = OUT / "urban_v3_all42.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
log(f"saved {OUT_BLEND}")


def reset_large_house_visibility():
    coll = bpy.data.collections.get("House_large_indoor")
    for obj in coll.all_objects if coll else []:
        if obj is not None and obj.type == "MESH":
            obj.hide_render = False


def in_source_collection(obj, needle):
    return obj is not None and any(needle in c.name for c in obj.users_collection)


render_times = {}
views = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
if SMOKE:
    views = views[:3]
for camera_name, filename in views:
    cam = bpy.data.objects.get(camera_name)
    if not cam:
        raise RuntimeError(f"missing all41 camera: {camera_name}")
    reset_large_house_visibility()
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    started = time.perf_counter()
    log(f"render {filename}")
    bpy.ops.render.render(write_still=True)
    render_times[filename] = round(time.perf_counter() - started, 3)

if not SMOKE:
    large = bpy.data.collections.get("House_large_indoor")
    large_objects = [o for o in large.all_objects if o is not None] if large else []
    reset_large_house_visibility()
    for obj in large_objects:
        if obj.type == "MESH" and (
            in_source_collection(obj, "room_wall")
            or in_source_collection(obj, "room_exterior")
            or in_source_collection(obj, "room_ceiling")
        ):
            obj.hide_render = True
    scene.camera = bpy.data.objects["cam_int_furniture"]
    scene.render.filepath = str(OUT / "interior_furniture.png")
    started = time.perf_counter()
    log("render interior_furniture.png")
    bpy.ops.render.render(write_still=True)
    render_times["interior_furniture.png"] = round(time.perf_counter() - started, 3)

    reset_large_house_visibility()
    for obj in large_objects:
        if obj.type == "MESH" and (
            in_source_collection(obj, "room_wall")
            or in_source_collection(obj, "room_exterior")
        ):
            obj.hide_render = True
    scene.camera = bpy.data.objects["cam_int_window"]
    scene.render.filepath = str(OUT / "interior_window.png")
    started = time.perf_counter()
    log("render interior_window.png")
    bpy.ops.render.render(write_still=True)
    render_times["interior_window.png"] = round(time.perf_counter() - started, 3)
    reset_large_house_visibility()

leaf_objects = [
    o
    for o in bpy.data.objects
    if o.name.startswith("all39_fast5_tree_mother_") and "_leaf_" in o.name
]
leaf_meshes = {o.data.name for o in leaf_objects if o.data}
instances_valid = all(
    o.instance_type == "COLLECTION" and o.instance_collection for o in tree_instances
)
camera_unchanged = all(
    name in BASELINE_CAMERAS
    and list(bpy.data.objects[name].location) == data["location"]
    and list(bpy.data.objects[name].rotation_euler) == data["rotation_euler"]
    and abs(float(bpy.data.objects[name].data.angle) - data["angle"]) < 1e-8
    for name, data in BASELINE_CAMERAS.items()
)
validation = {
    "passed": bool(
        len(tree_proto_colls) > 1
        and len(tree_proto_colls) <= 9
        and tree_instances
        and instances_valid
        and leaf_objects
        and camera_unchanged
        and all(
            item["source_exists"]
            for key, item in house_report.items()
            if "source_exists" in item
        )
    ),
    "all41_house_assets": house_report,
    "tree_instances": len(tree_instances),
    "tree_master_collections": len(tree_proto_colls),
    "shrub_instances": len(shrub_instances),
    "shrub_master_collections": len(shrub_proto_colls),
    "visible_leaf_objects": len(leaf_objects),
    "unique_leaf_meshes": len(leaf_meshes),
    "tree_instances_valid": instances_valid,
    "c2w_masters_present": bpy.data.collections.get("C2W_MASTERS") is not None,
    "cameras_unchanged": camera_unchanged,
    "saved_blend": str(OUT_BLEND),
}
stats = {
    "baseline": BASELINE,
    "final": scene_counts(),
    "master_objects": sum(o.get("c2w_role") == "master" for o in bpy.data.objects),
    "instance_objects": sum(o.get("c2w_role") == "instance" for o in bpy.data.objects),
    "unique_meshes": len(bpy.data.meshes),
    "materials": len(bpy.data.materials),
    "tree_instances": len(tree_instances),
    "tree_master_collections": len(tree_proto_colls),
    "unique_leaf_meshes": len(leaf_meshes),
    "house_library_loads": 3 if REBUILD else 0,
    "external_library_loads": {
        str(path): (1 if REBUILD else 0) for path in HOUSE_SOURCES.values()
    },
    "build_seconds": round(
        time.perf_counter() - STARTED - sum(render_times.values()), 3
    ),
    "render_seconds_per_view": render_times,
    "blend_file_size_bytes": OUT_BLEND.stat().st_size,
    "mode": "rebuild" if REBUILD else "lossless_all41_migration",
}
(OUT / "validation_report.json").write_text(
    json.dumps(validation, indent=2), encoding="utf-8"
)
(OUT / "asset_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
(OUT / "camera_baseline.json").write_text(
    json.dumps(BASELINE_CAMERAS, indent=2), encoding="utf-8"
)
log(f"complete validation_passed={validation['passed']}")
