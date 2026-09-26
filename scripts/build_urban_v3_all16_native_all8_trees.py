"""
Build urban_v3_all16 from all15, replacing the all15 artificial leaf patches
with the native all8 TreeFactory child foliage system.

The all8 park trees render their leafy crowns through child objects named
Tree.004, Tree.010, ... with add_tree_children geometry-node modifiers. The
all15 fix only added explicit mesh leaf clouds, so the trees had leaves but
did not match the all8 visual style. This script appends those native all8
child foliage objects and attaches them to both the original park TreeFactory
trunks and the copied roadside/yard all8 tree instances.
"""

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


from pathlib import Path

import bpy

SRC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all15/urban_v3_all15.blend"
)
ALL8_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all8/urban_v3_all8.blend"
)
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all16")
OUT.mkdir(parents=True, exist_ok=True)

SEED_TO_CHILD = {
    42: "Tree.004",
    137: "Tree.010",
    256: "Tree.016",
    381: "Tree.022",
    512: "Tree.028",
    619: "Tree.034",
    734: "Tree.040",
    851: "Tree.046",
}


def get_coll(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_to_coll(obj, coll):
    try:
        coll.objects.link(obj)
    except RuntimeError:
        pass
    return obj


def unlink_from_all_collections(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def remove_artificial_leaf_fixes():
    removed = 0
    for obj in list(bpy.data.objects):
        name = obj.name
        if "_explicit_leaf_cloud" in name or "leaf_complex" in name:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(f"[all16] Removed all15 artificial leaf-cloud objects: {removed}", flush=True)


def append_all8_native_children():
    child_names = list(SEED_TO_CHILD.values())
    with bpy.data.libraries.load(str(ALL8_BLEND), link=False) as (data_from, data_to):
        missing = [name for name in child_names if name not in data_from.objects]
        if missing:
            raise RuntimeError(f"Missing all8 native tree child objects: {missing}")
        data_to.objects = child_names

    loaded = {obj.name: obj for obj in data_to.objects if obj is not None}
    if len(loaded) != len(child_names):
        raise RuntimeError(
            f"Loaded {len(loaded)} all8 child objects, expected {len(child_names)}"
        )
    print(f"[all16] Appended native all8 tree child objects: {len(loaded)}", flush=True)
    return loaded


def set_native_child_visibility(obj):
    obj.hide_viewport = False
    obj.hide_render = False
    obj.visible_camera = True
    obj.visible_diffuse = True
    obj.visible_glossy = True
    obj.visible_transmission = True
    obj.visible_volume_scatter = True
    obj.visible_shadow = True
    for mod in obj.modifiers:
        mod.show_render = True
        mod.show_viewport = True


def attach_template_children(loaded, coll):
    templates_by_data = {}
    attached = 0
    for seed, child_name in SEED_TO_CHILD.items():
        child = loaded[child_name]
        trunk = bpy.data.objects.get(f"all8veg_TreeFactory({seed}).spawn_asset(0)")
        if trunk is None:
            raise RuntimeError(f"Missing all15 all8 trunk for seed {seed}")

        child.name = f"a16_native_all8_crown_{seed}"
        child.parent = trunk
        child.matrix_parent_inverse.identity()
        child.location = (0.0, 0.0, 0.0)
        child.rotation_euler = (0.0, 0.0, 0.0)
        child.scale = (1.0, 1.0, 1.0)
        link_to_coll(child, coll)
        set_native_child_visibility(child)
        templates_by_data[trunk.data.name] = child
        attached += 1

    print(f"[all16] Attached native all8 crowns to park trunks: {attached}", flush=True)
    return templates_by_data


def remove_appended_duplicate_parents():
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.name.startswith("TreeFactory("):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(
        f"[all16] Removed temporary appended all8 parent trunks: {removed}", flush=True
    )


def attach_crowns_to_copied_trees(templates_by_data, coll):
    created = 0
    skipped = []
    for tree in sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH" and obj.name.endswith("_all8_tree")
        ),
        key=lambda obj: obj.name,
    ):
        template = templates_by_data.get(tree.data.name)
        if template is None:
            skipped.append((tree.name, tree.data.name))
            continue
        crown = template.copy()
        crown.data = template.data
        crown.animation_data_clear()
        crown.name = tree.name[: -len("_all8_tree")] + "_a16_native_all8_crown"
        crown.parent = tree
        crown.matrix_parent_inverse.identity()
        crown.location = (0.0, 0.0, 0.0)
        crown.rotation_euler = (0.0, 0.0, 0.0)
        crown.scale = (1.0, 1.0, 1.0)
        link_to_coll(crown, coll)
        set_native_child_visibility(crown)
        created += 1
    print(
        f"[all16] Attached native all8 crowns to copied roadside/yard trees: {created}",
        flush=True,
    )
    if skipped:
        print(
            f"[all16] Skipped copied trees without matching all8 template: {skipped[:12]}",
            flush=True,
        )


def ensure_cycles_color_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.image_settings.file_format = "PNG"
    scene.cycles.samples = 192
    scene.cycles.use_denoising = True
    try:
        scene.cycles.device = "GPU"
    except Exception:
        pass
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = -0.25
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


print("[all16] Opening all15 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print("[all16] Base loaded", flush=True)

remove_artificial_leaf_fixes()
native_coll = get_coll("All16_All8NativeTreeChildren")
loaded_children = append_all8_native_children()
templates = attach_template_children(loaded_children, native_coll)
remove_appended_duplicate_parents()
attach_crowns_to_copied_trees(templates, native_coll)

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all16.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all16] Blend saved: {out_blend}", flush=True)

cameras = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]

scene = bpy.context.scene
for cam_name, filename in cameras:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all16] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all16] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all16] Done: {filename}", flush=True)

print("[all16] All complete.", flush=True)
