"""
Fix urban_v3_all14 tree leaves and save/render urban_v3_all15.

Diagnosis from all14:
  - The complex all8 leaf-cloud meshes exist and are render-visible.
  - Their object transforms stayed at the origin while their matching trunks
    were placed around the park, so the rendered trees looked leafless.

This script:
  - Moves each original all8 explicit leaf cloud to its matching trunk.
  - Adds linked all8-style explicit leaf clouds to every copied all8 roadside
    and yard tree.
  - Keeps the all14 belt/flowerbed vegetation improvements.
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


import math
import re
from pathlib import Path

import bpy

SRC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all14/urban_v3_all14.blend"
)
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all15")
OUT.mkdir(parents=True, exist_ok=True)

print("[all15] Opening all14 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print("[all15] Base loaded", flush=True)


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


def set_leaf_render_visibility(obj):
    obj.hide_viewport = False
    obj.hide_render = False
    obj.visible_camera = True
    obj.visible_diffuse = True
    obj.visible_glossy = True
    obj.visible_transmission = True
    obj.visible_volume_scatter = True
    obj.visible_shadow = True


def ensure_leaf_material():
    mat = bpy.data.materials.get("a15_all8_leaf_green_visible")
    if mat:
        return mat
    mat = bpy.data.materials.new("a15_all8_leaf_green_visible")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 8.0
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.025, 0.135, 0.025, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.155, 0.360, 0.075, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.72
    try:
        bsdf.inputs["Alpha"].default_value = 1.0
    except Exception:
        pass
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def assign_visible_leaf_material(obj):
    mat = ensure_leaf_material()
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def natural_key(name):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def original_all8_pairs():
    pairs = []
    for leaf in bpy.data.objects:
        if not leaf.name.startswith("all8veg_TreeFactory("):
            continue
        if "_explicit_leaf_cloud" not in leaf.name:
            continue
        trunk_name = leaf.name.split("_explicit_leaf_cloud")[0]
        trunk = bpy.data.objects.get(trunk_name)
        if trunk is None:
            continue
        pairs.append((trunk, leaf))
    pairs.sort(key=lambda pair: natural_key(pair[0].name))
    return pairs


def fix_original_all8_leaf_locations(pairs):
    fixed = 0
    for trunk, leaf in pairs:
        leaf.parent = None
        leaf.location = trunk.location
        leaf.rotation_euler = trunk.rotation_euler
        leaf.scale = trunk.scale
        set_leaf_render_visibility(leaf)
        assign_visible_leaf_material(leaf)
        fixed += 1
    print(
        f"[all15] Repositioned original all8 explicit leaf clouds: {fixed}", flush=True
    )


def copied_all8_trees():
    trees = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and obj.name.endswith("_all8_tree")
        and not obj.name.startswith("all8veg_TreeFactory(")
    ]
    trees.sort(key=lambda o: natural_key(o.name))
    return trees


def add_leaf_cloud_for_copied_trees(pairs, coll):
    if not pairs:
        raise RuntimeError("No all8 explicit leaf clouds available as templates")
    created = 0
    for idx, tree in enumerate(copied_all8_trees()):
        tag = tree.name[: -len("_all8_tree")]
        name = f"{tag}_all15_all8_explicit_leaf_cloud"
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        _, src_leaf = pairs[idx % len(pairs)]
        leaf = src_leaf.copy()
        leaf.data = src_leaf.data
        leaf.animation_data_clear()
        leaf.name = name
        leaf.parent = None
        leaf.location = tree.location
        leaf.rotation_euler = tree.rotation_euler
        # Slightly oversize the crown so it reads clearly in the park camera.
        s = max(tree.scale.x, tree.scale.y, tree.scale.z) * 1.22
        leaf.scale = (s, s, s)
        bpy.context.collection.objects.link(leaf)
        link_to_coll(leaf, coll)
        set_leaf_render_visibility(leaf)
        assign_visible_leaf_material(leaf)
        created += 1
    print(
        f"[all15] Added all8-style leaf clouds to copied trees: {created}", flush=True
    )


def strengthen_existing_leaf_complex():
    strengthened = 0
    for obj in bpy.data.objects:
        if "leaf_complex" not in obj.name or obj.type != "MESH":
            continue
        set_leaf_render_visibility(obj)
        assign_visible_leaf_material(obj)
        # These meshes were authored with absolute/world-space vertex
        # coordinates and object.location at the origin. Scaling the object
        # moves the leaves away from their tree, so keep transform scale at 1.
        obj.scale = (1.0, 1.0, 1.0)
        strengthened += 1
    print(
        f"[all15] Kept/strengthened supplemental leaf_complex meshes: {strengthened}",
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


pairs = original_all8_pairs()
print(f"[all15] Found original all8 trunk/leaf pairs: {len(pairs)}", flush=True)
fix_original_all8_leaf_locations(pairs)
leaf_coll = get_coll("All15_All8LeafCloudFix")
add_leaf_cloud_for_copied_trees(pairs, leaf_coll)
strengthen_existing_leaf_complex()

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all15.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all15] Blend saved: {out_blend}", flush=True)

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
        print(f"[all15] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all15] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all15] Done: {filename}", flush=True)

print("[all15] All complete.", flush=True)
