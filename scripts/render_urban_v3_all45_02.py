"""Render and validate the ten prompt-45-02 residential cameras."""

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
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/urban_v3_all45_02"
RENDER_BLEND = OUT / "urban_v3_all45_02_render.blend"
PREFIX = "all45_02:"
RENDERS = [
    "residential_overview",
    "lowrise_group_view",
    "indoor_house_exterior_close",
    "indoor_house_window_view",
    "indoor_house_interior_view",
    "apartment_front_close",
    "apartment_balcony_close",
    "apartment_entrance_close",
    "residential_courtyard_view",
    "residential_landscape_close",
]
INDOOR_SIMPLIFIED = False
TREE_LOD_REMAPPED = False


def simple_material(name, color, roughness=0.65, metallic=0.0, alpha=1.0):
    mat = bpy.data.materials.get(PREFIX + name) or bpy.data.materials.new(PREFIX + name)
    mat.diffuse_color = (*color, alpha)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, alpha)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
    return mat


def simplify_indoor_materials():
    """Keep true Infinigen geometry but replace 452 heavy shaders for validation."""
    global INDOOR_SIMPLIFIED
    if INDOOR_SIMPLIFIED:
        return
    mats = {
        "wall": simple_material("render_indoor_wall", (0.72, 0.69, 0.62), 0.88),
        "floor": simple_material("render_indoor_oak", (0.34, 0.18, 0.075), 0.56),
        "fabric": simple_material("render_indoor_fabric", (0.18, 0.27, 0.28), 0.82),
        "linen": simple_material("render_indoor_linen", (0.66, 0.64, 0.58), 0.90),
        "wood": simple_material("render_indoor_wood", (0.27, 0.12, 0.045), 0.58),
        "ceramic": simple_material("render_indoor_ceramic", (0.70, 0.70, 0.66), 0.48),
        "metal": simple_material("render_indoor_metal", (0.12, 0.13, 0.13), 0.34, 0.64),
        "glass": simple_material(
            "render_indoor_glass", (0.40, 0.55, 0.55), 0.10, 0.02, 0.28
        ),
        "accent": simple_material("render_indoor_accent", (0.40, 0.30, 0.20), 0.70),
    }
    source = bpy.data.collections.get(PREFIX + "MASTER_infinigen_indoor_shared_source")
    if source is None:
        raise KeyError("Missing true Infinigen Indoor source collection")
    for obj in source.all_objects:
        if obj is None:
            continue
        if obj.type != "MESH":
            continue
        n = obj.name.lower()
        if ".exterior" in n:
            obj.hide_render = True
            continue
        if ".wall" in n or ".ceiling" in n:
            mat = mats["wall"]
        elif ".floor" in n:
            mat = mats["floor"]
        elif "windowfactory" in n:
            mat = mats["glass"]
        elif "sofa" in n or "chairfactory" in n:
            mat = mats["fabric"]
        elif "bedfactory" in n or "curtain" in n:
            mat = mats["linen"]
        elif any(k in n for k in ("cabinet", "shelf", "table", "book")):
            mat = mats["wood"]
        elif any(k in n for k in ("sink", "toilet", "bowl", "plate", "cup")):
            mat = mats["ceramic"]
        elif any(k in n for k in ("hardware", "oven", "dishwasher", "lamp")):
            mat = mats["metal"]
        else:
            mat = mats["accent"]
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    INDOOR_SIMPLIFIED = True


def prune_indoor_render_geometry():
    """Drop only costly decoration; retain real rooms and required furniture."""
    source = bpy.data.collections.get(PREFIX + "MASTER_infinigen_indoor_shared_source")
    if source is None:
        raise KeyError("Missing true Infinigen Indoor source collection")
    required = (
        ".wall",
        ".floor",
        ".ceiling",
        "windowfactory",
        "doorfactory",
        "sofafactory",
        "bedfactory",
        "tablediningfactory",
        "chairfactory",
        "kitchencabinetfactory",
        "singlecabinetfactory",
        "bookcasefactory",
        "largeshelffactory",
        "cellshelffactory",
        "standingsinkfactory",
        "toiletfactory",
        "ovenfactory",
        "dishwasherfactory",
        "lampfactory",
        "ceilinglightfactory",
        "wallartfactory",
        "mirrorfactory",
    )
    removed_vertices = 0
    removed_objects = 0
    for obj in list(source.all_objects):
        if obj is None:
            continue
        if obj.type != "MESH" or any(token in obj.name.lower() for token in required):
            continue
        removed_vertices += len(obj.data.vertices)
        bpy.data.objects.remove(obj, do_unlink=True)
        removed_objects += 1
    source["render_geometry"] = "true Infinigen rooms and core household furniture"
    source["render_removed_decor_objects"] = removed_objects
    source["render_removed_decor_vertices"] = removed_vertices
    print(
        f"[all45_02 render] pruned {removed_objects} decorative Indoor objects "
        f"({removed_vertices} vertices), retained {len(source.all_objects)} objects",
        flush=True,
    )


def remap_treefactory_render_lods():
    """Use local branch/leaf LODs for PNGs while preserving linked masters in .blend."""
    global TREE_LOD_REMAPPED
    if TREE_LOD_REMAPPED:
        return
    lod_names = [
        PREFIX + "MASTER_tree_maple",
        PREFIX + "MASTER_tree_birch",
        PREFIX + "MASTER_tree_zelkova",
        PREFIX + "MASTER_tree_pear",
        PREFIX + "MASTER_tree_oak",
        PREFIX + "MASTER_tree_hornbeam",
    ]
    lods = [bpy.data.collections.get(name) for name in lod_names]
    if not all(lods):
        sys.path.insert(0, str(ROOT / "scripts"))
        import generate_urban_v3_all45_02 as generator

        generator.configure_base()
        tree_mats = {
            "trunk": simple_material("render_tree_bark", (0.12, 0.065, 0.025), 0.90),
            "leaf_a": simple_material(
                "render_tree_leaf_deep", (0.045, 0.17, 0.035), 0.90
            ),
            "leaf_b": simple_material(
                "render_tree_leaf_fresh", (0.08, 0.24, 0.045), 0.89
            ),
            "leaf_c": simple_material(
                "render_tree_leaf_olive", (0.13, 0.22, 0.045), 0.90
            ),
        }
        specs = [
            ("maple", "leaf_a", 1.05, 1.0),
            ("birch", "leaf_b", 0.90, 0.80),
            ("zelkova", "leaf_a", 1.15, 1.16),
            ("pear", "leaf_c", 0.82, 0.76),
            ("oak", "leaf_b", 1.20, 1.25),
            ("hornbeam", "leaf_c", 1.00, 0.88),
        ]
        lods = [
            generator.make_tree_master(name, tree_mats, leaf, height, spread, 500 + i)
            for i, (name, leaf, height, spread) in enumerate(specs)
        ]
    instances = [
        obj
        for obj in bpy.data.objects
        if obj.instance_type == "COLLECTION"
        and obj.instance_collection
        and obj.instance_collection.get("render_runtime_heavy")
    ]
    linked_sources = {obj.instance_collection for obj in instances}
    for i, obj in enumerate(sorted(instances, key=lambda x: x.name)):
        source_name = obj.instance_collection.name
        obj.instance_collection = lods[i % len(lods)]
        obj["render_lod_of"] = source_name
    # These linked masters are part of the deliverable .blend, but after the
    # PNG-only remap they must not remain in the render dependency graph.
    for source in linked_sources:
        bpy.data.collections.remove(source, do_unlink=True)
    for obj in list(bpy.data.objects):
        if obj.library and "urban_v3_trees/trees.blend" in obj.library.filepath:
            bpy.data.objects.remove(obj, do_unlink=True)
    TREE_LOD_REMAPPED = True
    print(
        f"[all45_02 render] remapped {len(instances)} TreeFactory instances to local LODs",
        flush=True,
    )


def configure(preview=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 560 if preview else 1120
    scene.render.resolution_y = 350 if preview else 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_simplify = True
    scene.render.simplify_subdivision_render = 0
    scene.render.simplify_child_particles_render = 0
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.eevee.taa_samples = 8 if preview else 24
    scene.eevee.taa_render_samples = 8 if preview else 24


def tune_validation_views():
    """Keep glass readable and frame Indoor depth rather than a flat pane."""
    for name in (PREFIX + "clear_window_glass", PREFIX + "render_indoor_glass"):
        mat = bpy.data.materials.get(name)
        if not mat or not mat.use_nodes:
            continue
        bsdf = next(
            (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
        )
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.18, 0.23, 0.23, 0.045)
            bsdf.inputs["Roughness"].default_value = 0.035
            bsdf.inputs["Alpha"].default_value = 0.045
        mat.diffuse_color = (0.18, 0.23, 0.23, 0.045)
        mat.surface_render_method = "BLENDED"
    views = {
        "indoor_house_window_view": (
            (-30.56, -30.27, 2.20),
            (-32.38, -21.19, 1.05),
            43,
        ),
        "indoor_house_interior_view": (
            (-36.27, -21.79, 1.55),
            (-31.60, -18.11, 1.00),
            70,
        ),
    }
    for name, (loc, target, fov) in views.items():
        cam = bpy.data.objects.get(PREFIX + "cam_" + name)
        if not cam:
            continue
        cam.location = loc
        cam.rotation_euler = (
            (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
        )
        cam.data.angle = math.radians(fov)


def indoor_instances():
    return sorted(
        [
            obj
            for obj in bpy.data.objects
            if obj.instance_type == "COLLECTION"
            and obj.instance_collection
            and "MASTER_infinigen_indoor_shared_source" in obj.instance_collection.name
        ],
        key=lambda obj: obj.name,
    )


def set_indoor_visibility(filename):
    show_house_a = filename in {
        "indoor_house_exterior_close.png",
        "indoor_house_window_view.png",
        "indoor_house_interior_view.png",
    }
    for obj in indoor_instances():
        is_house_a = "house_a_" in obj.name
        obj.hide_render = not (show_house_a and is_house_a)
    if show_house_a:
        simplify_indoor_materials()


def render(names, preview=False, overwrite=False):
    configure(preview)
    remap_treefactory_render_lods()
    tune_validation_views()
    suffix = "_preview.png" if preview else ".png"
    for name in names:
        filename = name + suffix
        path = OUT / filename
        if path.exists() and path.stat().st_size > 100_000 and not overwrite:
            print(f"[all45_02 render] skip existing {filename}", flush=True)
            continue
        cam = bpy.data.objects.get(PREFIX + "cam_" + name)
        if cam is None:
            raise KeyError(f"Missing camera {PREFIX}cam_{name}")
        set_indoor_visibility(name + ".png")
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"[all45_02 render] rendered {filename}", flush=True)


def prepare_render_blend():
    configure(preview=True)
    remap_treefactory_render_lods()
    simplify_indoor_materials()
    prune_indoor_render_geometry()
    # Wider grouping camera shows all three detached houses rather than one.
    cam = bpy.data.objects.get(PREFIX + "cam_lowrise_group_view")
    if cam:
        cam.location = (-3, -83, 20)
        cam.rotation_euler = (
            (Vector((-4, -18, 3.5)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        )
        cam.data.angle = 1.12
    for obj in indoor_instances():
        obj.hide_render = True
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(RENDER_BLEND))
    print(f"[all45_02 render] prepared {RENDER_BLEND}", flush=True)


def main():
    args = set(sys.argv[sys.argv.index("--") + 1 :]) if "--" in sys.argv else set()
    preview = "--preview" in args
    overwrite = "--overwrite" in args
    if "--prepare" in args:
        prepare_render_blend()
        return
    requested = [name for name in RENDERS if name in args]
    render(requested or RENDERS, preview=preview, overwrite=overwrite)


if __name__ == "__main__":
    main()
