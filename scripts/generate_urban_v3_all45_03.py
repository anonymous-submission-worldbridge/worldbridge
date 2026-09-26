"""Production residential generator for urban_v3_all45_09.

This starts from a clean scene. Layout, count/density and facade language are
controlled by DEFAULT_CONFIG and may be overridden by a JSON file passed after
``-- --config path.json`` or through ``C2W_RESIDENTIAL_CONFIG``. High-rises
intentionally have no interior. Every low-rise uses a genuine Infinigen Indoor
solve at its native architectural scale. The first low-rise is the richly
furnished showcase residence; the other two instance a verified reduced solve.
All visible vegetation comes from verified generated tree masters; no proxy,
placeholder, floating, fragmented groundcover, or toy assets are used.
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


import argparse
import copy
import importlib.util
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09"
RENDERS = OUT / "renders"
PREFIX = "all45_09:"
sys.path[:0] = [str(ROOT / "infinigen"), str(ROOT / "scripts")]
spec = importlib.util.spec_from_file_location(
    "all45_02_generator", ROOT / "scripts/generate_urban_v3_all45_02.py"
)
P = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(P)

INDOOR_SOURCES = [
    OUT / "indoor_sources/showcase/scene.blend",
    # The earlier companion_a solve contains a bedroom floor but no evaluated
    # BedFactory in its final saved state.  Reuse the verified reduced
    # companion_b solve for both secondary buildings; each remains a separate
    # native-scale collection instance in the production scene.
    OUT / "indoor_sources/companion_b/scene.blend",
    OUT / "indoor_sources/companion_b/scene.blend",
]
VERIFIED_CHAIR_SOURCE = (
    ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all40_house/scene.blend"
)
VERIFIED_CHAIR_OBJECT = "ChairFactory(7316159).spawn_asset(5570908)"

DEFAULT_CONFIG = {
    "schema_version": "3.0",
    "seed": 4509,
    "layout": {
        "mode": "dense_courtyard",
        "building_count": 11,
        "lowrise_count": 3,
        "density": 0.84,
        "site_width": 138.0,
        "site_depth": 108.0,
        "street_width": 12.0,
        "highrise_column_spacing": 32.5,
        "highrise_row_spacing": 38.0,
        "highrise_center_y": 29.0,
        "lowrise_column_spacing": 42.0,
        "lowrise_center_y": -17.0,
    },
    "highrise": {
        "floor_range": [8, 12],
        "base_width": 18.2,
        "base_depth": 14.4,
        "interiors": False,
    },
    "lowrise": {
        "floors": 2,
        "base_width": 22.4,
        "base_depth": 15.0,
        "indoor_source_indices": [0, 1, 2],
        "building_source_indices": [0, 1, 2],
        "building_roles": ["showcase_rich", "companion_reduced", "companion_reduced"],
        "interiors": "native_infinigen_indoor",
        "minimum_native_scale": 0.95,
        "maximum_native_scale": 1.08,
    },
    "facade": {
        "style": "oxidized_copper_brick_expressionism",
        "palette": {
            "brick_dark": [[0.13, 0.028, 0.018], [0.36, 0.085, 0.040]],
            "brick_warm": [[0.27, 0.060, 0.025], [0.58, 0.18, 0.060]],
            "copper": [[0.035, 0.15, 0.13], [0.12, 0.42, 0.34]],
            "concrete": [[0.28, 0.25, 0.21], [0.56, 0.50, 0.42]],
            "metal": [[0.012, 0.016, 0.017], [0.055, 0.070, 0.073]],
        },
        "color_variation": 0.18,
        "balcony_frequency": 0.58,
        "vertical_fin_frequency": 0.72,
    },
    "landscape": {
        "tree_count": 12,
        "bed_count": 8,
        "shrubs_per_bed": 0,
        # all45_09 deliberately removes every small ground-level vegetation
        # prototype. Even after normalizing transforms, shrub/flower/grass
        # evaluated sub-meshes read as floating fragments in the courtyard.
        # Only complete native trees remain; no proxy ground cover replaces
        # the removed collections.
        "flowers_per_bed": 0,
        "grass_per_bed": 0,
        "asset_source": "urban_v3_all39_fast5",
        "placement_policy": "complete_native_trees_only; all_fragmentary_groundcover_removed",
    },
    "render": {
        "engine": "CYCLES",
        "samples": 24,
        "resolution": [900, 560],
        "validation_views": [
            "01_spaced_district_overview.png",
            "02_street_wall.png",
            "03_highrise_facade_close.png",
            "04_lowrise_native_indoor_window.png",
            "05_courtyard_native_landscape.png",
            "06_layout_aerial.png",
        ],
    },
}


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in override.items():
        out[key] = (
            deep_merge(out[key], value)
            if isinstance(value, dict) and isinstance(out.get(key), dict)
            else value
        )
    return out


def validate_config(config):
    layout = config["layout"]
    if layout["mode"] not in {"dense_courtyard", "orthogonal_grid", "perimeter"}:
        raise ValueError(
            "layout.mode must be dense_courtyard, orthogonal_grid, or perimeter"
        )
    count, low = int(layout["building_count"]), int(layout["lowrise_count"])
    if not 2 <= count <= 24 or not 1 <= low < count:
        raise ValueError(
            "building_count must be 2..24 and lowrise_count must be 1..building_count-1"
        )
    if low > 12 or count - low > 12:
        raise ValueError(
            "The production site supports at most 12 low-rises and 12 high-rises"
        )
    if not 0.25 <= float(layout["density"]) <= 1.0:
        raise ValueError("layout.density must be in [0.25, 1.0]")
    if (
        float(layout["highrise_column_spacing"]) < 30.0
        or float(layout["highrise_row_spacing"]) < 34.0
    ):
        raise ValueError(
            "High-rise spacing must preserve the all45_08 open tower layout"
        )
    if float(layout["lowrise_column_spacing"]) <= float(
        config["lowrise"]["base_width"]
    ):
        raise ValueError(
            "Low-rise center spacing must exceed the enlarged building width"
        )
    lo, hi = config["highrise"]["floor_range"]
    if lo < 5 or hi < lo or hi > 30:
        raise ValueError("highrise.floor_range must be an increasing [5..30] range")
    if config["highrise"].get("interiors") is not False:
        raise ValueError("High-rise interiors must remain disabled")
    if config["lowrise"].get("interiors") != "native_infinigen_indoor":
        raise ValueError("Low-rise interiors must use native_infinigen_indoor")
    source_indices = [
        int(index) for index in config["lowrise"].get("indoor_source_indices", [])
    ]
    if not source_indices or any(
        index not in range(len(INDOOR_SOURCES)) for index in source_indices
    ):
        raise ValueError(
            "lowrise.indoor_source_indices must select available native Indoor solves"
        )
    building_sources = [
        int(index) for index in config["lowrise"].get("building_source_indices", [])
    ]
    building_roles = config["lowrise"].get("building_roles", [])
    if (
        len(building_sources) != low
        or len(set(building_sources)) != low
        or any(index not in source_indices for index in building_sources)
    ):
        raise ValueError(
            "lowrise.building_source_indices must assign one dedicated selected Indoor solve to every low-rise"
        )
    if len(building_roles) != low or building_roles.count("showcase_rich") != 1:
        raise ValueError(
            "lowrise.building_roles must identify exactly one showcase_rich low-rise"
        )
    if (
        float(config["lowrise"]["base_width"]) < 21.5
        or float(config["lowrise"]["base_depth"]) < 14.0
    ):
        raise ValueError(
            "Low-rise footprint must retain the native 21.5 x 14 m Indoor scale"
        )
    if config["facade"]["style"] not in {
        "oxidized_copper_brick_expressionism",
        "light_terracotta_arcade",
        "dark_metal_vertical",
    }:
        raise ValueError("Unsupported facade.style")


def load_config():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config")
    args, _ = parser.parse_known_args(argv)
    path = args.config or os.environ.get("C2W_RESIDENTIAL_CONFIG")
    config = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        with Path(path).open("r", encoding="utf8") as handle:
            config = deep_merge(config, json.load(handle))
        config["config_source"] = str(Path(path).resolve())
    else:
        config["config_source"] = "embedded DEFAULT_CONFIG"
    validate_config(config)
    return config


def configure(config):
    seed = int(config["seed"])
    P.ROOT, P.OUT, P.PREFIX, P.RNG = ROOT, OUT, PREFIX, random.Random(seed)
    P.G.ROOT, P.G.OUT, P.G.PREFIX, P.G.RNG = ROOT, OUT, PREFIX, random.Random(seed)


def make_materials(config):
    M = P.make_materials()
    palette = config["facade"]["palette"]
    variation = max(0.0, min(1.0, float(config["facade"]["color_variation"])))

    def pair(key):
        c0, c1 = tuple(palette[key][0]), tuple(palette[key][1])
        # 0.18 reproduces the authored default; lower/higher values reduce or
        # increase the procedural facade color range around the first color.
        factor = variation / 0.18
        return c0, tuple(
            max(0.0, min(1.0, a + (b - a) * factor)) for a, b in zip(c0, c1)
        )

    dark0, dark1 = pair("brick_dark")
    warm0, warm1 = pair("brick_warm")
    copper0, copper1 = pair("copper")
    concrete0, concrete1 = pair("concrete")
    metal0, metal1 = pair("metal")
    M["brick_dark"] = P.remap_material(
        "07_kiln_fired_claret_brick", dark0, dark1, 0.82, 0.30, 34.0
    )
    M["brick_warm"] = P.remap_material(
        "07_variegated_terracotta_brick", warm0, warm1, 0.84, 0.28, 31.0
    )
    M["copper_patina"] = P.remap_material(
        "07_oxidized_copper_rainscreen", copper0, copper1, 0.41, 0.16, 9.0, 0.72
    )
    M["board_concrete"] = P.remap_material(
        "07_board_formed_concrete", concrete0, concrete1, 0.88, 0.18, 6.5
    )
    M["black_metal"] = P.remap_material(
        "07_blackened_steel", metal0, metal1, 0.32, 0.035, 12.0, 0.82
    )
    M["dark_paver"] = P.remap_material(
        "07_dark_clinker_paver",
        (0.095, 0.055, 0.040),
        (0.26, 0.13, 0.075),
        0.91,
        0.24,
        23.0,
    )
    M["pale_paver"] = P.remap_material(
        "07_exposed_aggregate_paver",
        (0.34, 0.31, 0.27),
        (0.61, 0.56, 0.47),
        0.90,
        0.21,
        17.0,
    )
    M["podium_stone"] = P.remap_material(
        "07_burnished_basalt_plinth",
        (0.035, 0.042, 0.043),
        (0.13, 0.15, 0.15),
        0.72,
        0.14,
        10.0,
    )
    M["stucco_cream"], M["stucco_white"], M["stucco_gray"] = (
        M["brick_warm"],
        M["brick_dark"],
        M["copper_patina"],
    )
    M["apt_plaster"], M["apt_panel"] = M["brick_dark"], M["copper_patina"]
    M["panel_light"], M["panel_dark"], M["metal"] = (
        M["board_concrete"],
        M["black_metal"],
        M["black_metal"],
    )
    M["fascia"] = M["black_metal"]
    M["roof_tile"] = P.G.roof_tile_material(
        "07_blue_black_ceramic_roof", (0.018, 0.032, 0.036), (0.055, 0.10, 0.105)
    )
    M["roof_warm"] = P.G.roof_tile_material(
        "07_aged_copper_roof", (0.025, 0.11, 0.10), (0.10, 0.31, 0.26)
    )
    return M


def make_assets(M):
    # No legacy sphere/blob vegetation is allowed, even in unused masters.
    old_tree, old_shrub = P.make_tree_master, P.make_shrub_master
    P.make_tree_master = lambda *a, **k: bpy.data.collections.new(
        PREFIX + "UNUSED_LEGACY_TREE_SLOT"
    )
    P.make_shrub_master = lambda *a, **k: bpy.data.collections.new(
        PREFIX + "UNUSED_LEGACY_SHRUB_SLOT"
    )
    try:
        return P.make_assets(M)
    finally:
        P.make_tree_master, P.make_shrub_master = old_tree, old_shrub


def grounded_specimen_master(obj, name):
    """Copy one generated specimen into a local, bottom-anchored master.

    FlowerPlantFactory/GrassTuftFactory source objects retain their solved world
    transforms. Linking those objects directly into a new collection and then
    instancing that collection applies the offset twice, which caused the
    all45_08 floating plants. Preserve the generated mesh/material/modifiers but
    translate its evaluated source bounds so XY is centered and min-Z is zero.
    """
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[axis] for point in corners) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in corners) for axis in range(3)))
    center = (minimum + maximum) * 0.5
    shift = Vector((-center.x, -center.y, -minimum.z))
    specimen = obj.copy()
    specimen.parent = None
    specimen.matrix_world = Matrix.Translation(shift) @ obj.matrix_world.copy()
    specimen.hide_render = False
    coll = bpy.data.collections.new(PREFIX + name)
    coll.objects.link(specimen)
    coll["generated_factory_source"] = obj.name
    coll["grounded_specimen"] = True
    coll["source_bottom_z"] = float(minimum.z)
    coll["source_horizontal_offset"] = float(math.hypot(center.x, center.y))
    return coll


def native_vegetation_assets(A):
    source = (
        ROOT
        / "infinigen/outputs/outdoor_part_demo/urban_v3_all39_fast5/urban_v3_all39_fast5.blend"
    )
    tree_names = [f"All39Fast5_TreePrototype_{i:02d}" for i in range(5)]
    # Do not import any small shrub/flower/grass collection. At courtyard scale
    # their evaluated branches read as detached or floating fragments.
    # Removing the masters is stronger than merely setting placement counts to
    # zero: no later collection instance can leak them back into production.
    wanted = tree_names
    with bpy.data.libraries.load(str(source), link=False) as (src, dst):
        missing = [name for name in wanted if name not in src.collections]
        if missing:
            raise RuntimeError(
                f"Verified Infinigen vegetation collections are missing: {missing}"
            )
        dst.collections = wanted
    loaded = {
        requested_name: collection
        for requested_name, collection in zip(wanted, dst.collections)
        if collection is not None
    }
    missing_loaded = [name for name in wanted if name not in loaded]
    if missing_loaded:
        raise RuntimeError(
            f"Verified tree collections failed to load: {missing_loaded}"
        )
    for i, name in enumerate(tree_names):
        A[f"native_tree_{i}"] = loaded[name]
    A["native_shrub_count"] = 0
    A["native_flower_count"], A["native_grass_count"] = 0, 0
    return {
        "tree_masters": 5,
        "shrub_masters": 0,
        "flower_masters": 0,
        "grass_masters": 0,
        "source": str(source),
        "grounded_specimen_masters": 0,
        "grounding": [],
        "removed_floating_groundcover_factories": [
            "All39Fast5_ShrubPrototype_*",
            "FlowerPlantFactory",
            "GrassTuftFactory",
        ],
    }


def load_verified_chair_template():
    """Load one visually verified, detailed Infinigen Indoor dining chair."""
    if not VERIFIED_CHAIR_SOURCE.exists():
        raise FileNotFoundError(
            f"Verified Indoor chair source missing: {VERIFIED_CHAIR_SOURCE}"
        )
    with bpy.data.libraries.load(str(VERIFIED_CHAIR_SOURCE), link=False) as (src, dst):
        if VERIFIED_CHAIR_OBJECT not in src.objects:
            raise RuntimeError(
                f"Verified Indoor chair {VERIFIED_CHAIR_OBJECT} missing from {VERIFIED_CHAIR_SOURCE}"
            )
        dst.objects = [VERIFIED_CHAIR_OBJECT]
    reference = dst.objects[0]
    if reference is None or reference.type != "MESH":
        raise RuntimeError(f"Verified Indoor chair is not a mesh: {reference}")
    mesh = reference.data.copy()
    mesh.name = PREFIX + "verified_infinigen_indoor_dining_chair_mesh"
    # Bake the source object's authored transform, then make a clean local
    # mesh centred on XY and grounded at Z=0 for deterministic reuse at the
    # target Indoor solver's seating anchors.
    mesh.transform(reference.matrix_world)
    minimum = Vector(
        tuple(min(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3))
    )
    maximum = Vector(
        tuple(max(vertex.co[axis] for vertex in mesh.vertices) for axis in range(3))
    )
    center = (minimum + maximum) * 0.5
    mesh.transform(Matrix.Translation((-center.x, -center.y, -minimum.z)))
    dimensions = maximum - minimum
    if (
        not 0.42 <= min(dimensions.x, dimensions.y) <= 0.75
        or not 0.50 <= max(dimensions.x, dimensions.y) <= 0.82
        or not 0.75 <= dimensions.z <= 1.10
        or len(mesh.vertices) < 1000
    ):
        raise RuntimeError(
            f"Verified Indoor chair failed geometry audit: dimensions={tuple(dimensions)} "
            f"vertices={len(mesh.vertices)}"
        )
    material_names = sorted(material.name for material in mesh.materials if material)
    bpy.data.objects.remove(reference, do_unlink=True)
    return {
        "mesh": mesh,
        "source": str(VERIFIED_CHAIR_SOURCE),
        "source_object": VERIFIED_CHAIR_OBJECT,
        "dimensions_m": [round(float(value), 4) for value in dimensions],
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
        "materials": material_names,
    }


def load_native_indoor(path, source_index, role, chair_template):
    if not path.exists():
        raise FileNotFoundError(
            f"Required native Infinigen Indoor solve missing: {path}"
        )
    # `Collection` contains genuine evaluated children of placed assets (for
    # example MattressFactory, ComforterFactory, BlanketFactory and pillows).
    # The previous whitelist omitted it, leaving visible bed frames without
    # mattresses.  Conversely, standalone door_base_elements collections are
    # construction remnants and can appear as floating rails/frames, so they
    # are intentionally not imported.
    wanted = lambda n: n in {"unique_assets", "skirting", "Collection"}
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [name for name in src.collections if wanted(name)]
    master = bpy.data.collections.new(
        PREFIX + f"MASTER_native_infinigen_indoor_{source_index:02d}"
    )
    imported = set()
    for source_coll in filter(None, dst.collections):
        imported.update(source_coll.all_objects)
    placeholder_tokens = (".bbox_placeholder(", ".spawn_placeholder(")
    # Some native PlantContainerFactory variants evaluate as an opaque,
    # low-detail brown mass in the production render.  Genuine provenance is
    # not enough when the evaluated result is visibly blob-like, so exclude
    # the complete root hierarchies and leave the surrounding real furniture
    # untouched.  Do not replace them with proxy vegetation.
    rejected_plant_tokens = ("PlantContainerFactory",)
    # NatureShelfTrinketsFactory may generate procedural animal figurines.
    # The currently running Indoor solve was started before its cached
    # home.py asset-usage alias was patched, so enforce the production rule at
    # the final import boundary as well and discard each complete hierarchy.
    rejected_toy_tokens = ("NatureShelfTrinketsFactory",)

    def belongs_to_rejected_plant(obj):
        current = obj
        while current is not None:
            if any(token in current.name for token in rejected_plant_tokens):
                return True
            current = current.parent
        return False

    def belongs_to_rejected_toy(obj):
        current = obj
        while current is not None:
            if any(token in current.name for token in rejected_toy_tokens):
                return True
            current = current.parent
        return False

    rejected_blob_plants = {obj for obj in imported if belongs_to_rejected_plant(obj)}
    rejected_blob_plant_roots = {
        obj for obj in rejected_blob_plants if obj.parent not in rejected_blob_plants
    }
    rejected_toy_trinkets = {obj for obj in imported if belongs_to_rejected_toy(obj)}
    rejected_toy_trinket_roots = {
        obj for obj in rejected_toy_trinkets if obj.parent not in rejected_toy_trinkets
    }
    source_placeholder_objects = {
        obj
        for obj in imported
        if any(token in obj.name for token in placeholder_tokens)
    }
    preliminary_objects = [
        obj
        for obj in imported
        if obj.type != "CAMERA"
        and obj not in rejected_blob_plants
        and obj not in rejected_toy_trinkets
        and not any(token in obj.name for token in placeholder_tokens)
    ]

    def world_bounds(obj):
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return (
            Vector(tuple(min(point[axis] for point in points) for axis in range(3))),
            Vector(tuple(max(point[axis] for point in points) for axis in range(3))),
        )

    floors = [
        obj
        for obj in preliminary_objects
        if obj.type == "MESH" and ".floor" in obj.name
    ]
    if not floors:
        raise RuntimeError(f"Native Indoor solve contains no room floors: {path}")
    floor_bounds = [world_bounds(obj) for obj in floors]
    floor_min = Vector(
        tuple(min(item[0][axis] for item in floor_bounds) for axis in range(3))
    )
    floor_max = Vector(
        tuple(max(item[1][axis] for item in floor_bounds) for axis in range(3))
    )

    def belongs_to_placed_asset(obj):
        current = obj
        while current is not None:
            if ".spawn_asset(" in current.name:
                return True
            current = current.parent
        return False

    spatial_remnant_roots = set()
    for obj in preliminary_objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT"}:
            continue
        minimum, maximum = world_bounds(obj)
        center = (minimum + maximum) * 0.5
        outside_plan = not (
            floor_min.x - 1.0 <= center.x <= floor_max.x + 1.0
            and floor_min.y - 1.0 <= center.y <= floor_max.y + 1.0
        )
        # Trust every populated Infinigen `spawn_asset` hierarchy.  Some
        # procedurally evaluated chair legs and soft furnishings extend below
        # their support plane even though the asset origin and visible body are
        # correctly placed.  The old min-Z test incorrectly discarded those
        # genuine furnishings.  Underground filtering is only for unplaced
        # construction remnants, never for evaluated production assets.
        below_plan = not belongs_to_placed_asset(obj) and minimum.z < floor_min.z - 0.15
        if outside_plan or below_plan:
            spatial_remnant_roots.add(obj)

    def belongs_to_spatial_remnant(obj):
        current = obj
        while current is not None:
            if current in spatial_remnant_roots:
                return True
            current = current.parent
        return False

    rejected_spatial_remnants = {
        obj for obj in preliminary_objects if belongs_to_spatial_remnant(obj)
    }
    production_objects = [
        obj for obj in preliminary_objects if obj not in rejected_spatial_remnants
    ]
    # Reject the entire hierarchy of any objectively room-sized bed asset.
    # These are not simplified substitutes: they are occasional failed
    # procedural evaluations whose frame balloons into multi-metre circular
    # shells.  Two correctly evaluated, fully dressed BedFactory hierarchies
    # remain in the showcase residence.
    degenerate_bed_roots = set()
    degenerate_bed_details = []
    for obj in production_objects:
        if (
            obj.type != "MESH"
            or "BedFactory" not in obj.name
            or ".spawn_asset(" not in obj.name
        ):
            continue
        minimum, maximum = world_bounds(obj)
        dimensions = maximum - minimum
        if max(dimensions.x, dimensions.y) <= 2.8 and dimensions.z <= 2.1:
            continue
        degenerate_bed_roots.add(obj)
        degenerate_bed_details.append(
            {
                "object": obj.name,
                "dimensions_m": [round(float(value), 4) for value in dimensions],
                "reason": "room-sized procedural bed frame",
            }
        )

    def belongs_to_degenerate_bed(obj):
        current = obj
        while current is not None:
            if current in degenerate_bed_roots:
                return True
            current = current.parent
        return False

    rejected_degenerate_beds = {
        obj for obj in production_objects if belongs_to_degenerate_bed(obj)
    }
    production_objects = [
        obj for obj in production_objects if obj not in rejected_degenerate_beds
    ]
    floor_surface_z = sorted(item[1].z for item in floor_bounds)[len(floor_bounds) // 2]
    rejected_degenerate_chairs = []
    retained_chairs = []
    for obj in production_objects:
        if (
            obj.type != "MESH"
            or "ChairFactory" not in obj.name
            or ".spawn_asset(" not in obj.name
        ):
            continue
        minimum, maximum = world_bounds(obj)
        dimensions = maximum - minimum
        # Current all45_09 Indoor solves occasionally emit a closed pod/shell
        # from ChairFactory.  Its multi-metre envelope and below-floor geometry
        # are deterministic failure signals. Never shrink such a failed mesh:
        # replace it with a visually verified chair from an earlier genuine
        # Infinigen Indoor solve, preserving the target solve's authored origin
        # and yaw around the dining table.
        if max(dimensions) <= 1.25 and minimum.z >= floor_surface_z - 0.08:
            retained_chairs.append(obj)
            continue
        rejected_degenerate_chairs.append(
            {
                "object": obj,
                "dimensions_m": [round(float(value), 4) for value in dimensions],
                # Appended source collections are not linked to a view layer yet,
                # so matrix_world can still be its unevaluated identity here.
                # Root ChairFactory assets store their solver transform directly
                # in location/rotation_euler.
                "placement_anchor": obj.location.copy(),
                "yaw": float(obj.rotation_euler.z),
            }
        )
    rejected_degenerate_chair_objects = {
        item["object"] for item in rejected_degenerate_chairs
    }
    production_objects = [
        obj
        for obj in production_objects
        if obj not in rejected_degenerate_chair_objects
    ]
    verified_chair_replacements = []
    for replacement_index, item in enumerate(rejected_degenerate_chairs):
        anchor = item["placement_anchor"]
        replacement_ground_z = anchor.z - float(chair_template["dimensions_m"][2]) * 0.5
        if abs(replacement_ground_z - floor_surface_z) > 0.18:
            raise RuntimeError(
                f"ChairFactory solver anchor has an implausible support plane: "
                f"anchor={tuple(anchor)} floor_surface_z={floor_surface_z}"
            )
        replacement = bpy.data.objects.new(
            PREFIX
            + f"VerifiedChairFactory({source_index}).spawn_asset({replacement_index})",
            chair_template["mesh"],
        )
        replacement.matrix_world = Matrix.Translation(
            (anchor.x, anchor.y, replacement_ground_z)
        ) @ Matrix.Rotation(item["yaw"], 4, "Z")
        replacement["verified_chair_replacement"] = True
        replacement["replaces_failed_object"] = item["object"].name
        replacement["source_blend"] = chair_template["source"]
        replacement["source_object"] = chair_template["source_object"]
        after_minimum, after_maximum = world_bounds(replacement)
        after_dimensions = after_maximum - after_minimum
        after_center = (after_minimum + after_maximum) * 0.5
        if (
            max(after_dimensions.x, after_dimensions.y) > 0.83
            or after_dimensions.z > 1.11
            or abs(after_minimum.z - replacement_ground_z) > 0.02
            or abs(after_center.x - anchor.x) > 0.02
            or abs(after_center.y - anchor.y) > 0.02
        ):
            raise RuntimeError(
                f"Verified ChairFactory replacement failed for {replacement.name}: "
                f"dimensions={tuple(after_dimensions)} min_z={after_minimum.z} "
                f"center={tuple(after_center)} anchor={tuple(anchor)}"
            )
        production_objects.append(replacement)
        verified_chair_replacements.append(
            {
                "object": replacement.name,
                "replaces": item["object"].name,
                "rejected_dimensions_m": item["dimensions_m"],
                "dimensions_m": [round(float(value), 4) for value in after_dimensions],
                "placement_anchor_xy_m": [
                    round(float(anchor.x), 4),
                    round(float(anchor.y), 4),
                ],
                "center_xy_m": [
                    round(float(after_center.x), 4),
                    round(float(after_center.y), 4),
                ],
                "ground_z": round(float(after_minimum.z), 4),
                "source": chair_template["source"],
                "source_object": chair_template["source_object"],
            }
        )
    for obj in production_objects:
        try:
            master.objects.link(obj)
        except RuntimeError:
            pass
    names = [obj.name for obj in production_objects]
    placed_names = [name for name in names if ".spawn_asset(" in name]
    counts = {
        "room_architecture_objects": sum(
            any(token in name for token in (".floor", ".wall", ".ceiling", ".exterior"))
            for name in names
        ),
        "room_types": {
            room_type: sum(
                name.startswith(room_type + "_") and ".floor" in name for name in names
            )
            for room_type in (
                "living-room",
                "dining-room",
                "kitchen",
                "bedroom",
                "bathroom",
                "closet",
                "balcony",
            )
        },
        "beds": sum("BedFactory" in name for name in names),
        "tables": sum("Table" in name and ".spawn_asset(" in name for name in names),
        "cabinets": sum(
            "CabinetFactory" in name and ".spawn_asset(" in name for name in names
        ),
        "kitchen": sum("Kitchen" in name and ".spawn_asset(" in name for name in names),
        "kitchen_spaces": sum("KitchenSpaceFactory" in name for name in placed_names),
        "sanitary": sum(
            token in name and ".spawn_asset(" in name
            for name in names
            for token in ("ToiletFactory", "SinkFactory")
        ),
        "mesh_objects": sum(obj.type == "MESH" for obj in production_objects),
        "light_objects": sum(obj.type == "LIGHT" for obj in production_objects),
        "placed_asset_objects": len(placed_names),
        "seating": sum(
            any(token in name for token in ("ChairFactory", "SofaFactory"))
            for name in placed_names
        ),
        "sofas": sum("SofaFactory" in name for name in placed_names),
        "storage_and_display": sum(
            any(
                token in name
                for token in (
                    "CabinetFactory",
                    "BookcaseFactory",
                    "ShelfFactory",
                    "TVStandFactory",
                )
            )
            for name in placed_names
        ),
        "decor_and_lighting": sum(
            any(
                token in name
                for token in (
                    "LampFactory",
                    "RugFactory",
                    "PlantContainerFactory",
                    "WallArtFactory",
                )
            )
            for name in placed_names
        ),
        "bed_textile_objects": sum(
            any(
                token in name
                for token in (
                    "MattressFactory",
                    "ComforterFactory",
                    "BlanketFactory",
                    "PillowFactory",
                    "TowelFactory",
                )
            )
            for name in names
        ),
        "placeholder_objects_excluded": len(source_placeholder_objects),
        "blob_plant_roots_excluded": len(rejected_blob_plant_roots),
        "blob_plant_objects_excluded": len(rejected_blob_plants),
        "toy_trinket_roots_excluded": len(rejected_toy_trinket_roots),
        "toy_trinket_objects_excluded": len(rejected_toy_trinkets),
        "spatial_remnant_objects_excluded": len(rejected_spatial_remnants),
        "degenerate_bed_roots_excluded": len(degenerate_bed_roots),
        "degenerate_bed_objects_excluded": len(rejected_degenerate_beds),
        "degenerate_bed_details": degenerate_bed_details,
        "retained_chair_assets": len(retained_chairs),
        "degenerate_chair_assets_excluded": len(rejected_degenerate_chairs),
        "verified_chair_replacements": len(verified_chair_replacements),
        "verified_chair_replacement_details": verified_chair_replacements,
        "normalized_chair_assets": 0,
        "normalized_chair_details": [],
    }
    if (
        counts["room_architecture_objects"] == 0
        or sum(counts[k] for k in ("beds", "tables", "cabinets", "kitchen")) == 0
    ):
        raise RuntimeError(
            f"Native Indoor solve has no valid rooms/furniture: {counts}"
        )
    master["native_infinigen_indoor"] = True
    master["source_blend"] = str(path)
    master["source_index"] = source_index
    master["interior_role"] = role
    master["native_floorplan_bounds"] = json.dumps(
        {
            "min": [round(float(value), 5) for value in floor_min],
            "max": [round(float(value), 5) for value in floor_max],
        }
    )
    master["placeholder_objects_excluded"] = counts["placeholder_objects_excluded"]
    master["blob_plant_roots_excluded"] = counts["blob_plant_roots_excluded"]
    master["blob_plant_objects_excluded"] = counts["blob_plant_objects_excluded"]
    master["toy_trinket_roots_excluded"] = counts["toy_trinket_roots_excluded"]
    master["toy_trinket_objects_excluded"] = counts["toy_trinket_objects_excluded"]
    master["spatial_remnant_objects_excluded"] = counts[
        "spatial_remnant_objects_excluded"
    ]
    master["degenerate_bed_roots_excluded"] = counts["degenerate_bed_roots_excluded"]
    master["degenerate_bed_objects_excluded"] = counts[
        "degenerate_bed_objects_excluded"
    ]
    master["degenerate_chair_assets_excluded"] = counts[
        "degenerate_chair_assets_excluded"
    ]
    master["verified_chair_replacements"] = counts["verified_chair_replacements"]
    master["normalized_chair_assets"] = counts["normalized_chair_assets"]
    return master, counts


def validate_indoor_quality(source_path, role, counts):
    missing_rooms = [
        room_type
        for room_type in (
            "living-room",
            "dining-room",
            "kitchen",
            "bedroom",
            "bathroom",
        )
        if counts["room_types"].get(room_type, 0) == 0
    ]
    if missing_rooms:
        raise RuntimeError(
            f"{role} Indoor solve is missing required rooms {missing_rooms}: {source_path}"
        )
    if (
        counts["degenerate_chair_assets_excluded"]
        != counts["verified_chair_replacements"]
    ):
        raise RuntimeError(
            f"Every failed ChairFactory must receive a verified Indoor replacement: "
            f"{source_path} counts={counts}"
        )
    minimum_assets = 20 if role == "showcase_rich" else 12
    minimum_storage = 4 if role == "showcase_rich" else 1
    if (
        counts["placed_asset_objects"] < minimum_assets
        or counts["storage_and_display"] < minimum_storage
    ):
        raise RuntimeError(
            f"{role} Indoor solve is too sparse for production: {source_path} counts={counts}"
        )
    if counts["beds"] < 1:
        raise RuntimeError(
            f"{role} Indoor residence has no genuine BedFactory asset: "
            f"{source_path} counts={counts}"
        )
    if role == "showcase_rich" and counts["beds"] < 2:
        raise RuntimeError(
            f"Showcase Indoor residence needs at least two non-degenerate "
            f"BedFactory assets: {source_path} counts={counts}"
        )
    if counts["bed_textile_objects"] < counts["beds"] * 3:
        raise RuntimeError(
            f"{role} Indoor beds are missing genuine mattress/bedding children: "
            f"{source_path} counts={counts}"
        )
    if role == "showcase_rich" and counts["sofas"] < 1:
        raise RuntimeError(
            f"Showcase Indoor living room has no genuine SofaFactory asset: "
            f"{source_path} counts={counts}"
        )
    if role == "showcase_rich" and counts["kitchen_spaces"] < 1:
        raise RuntimeError(
            f"Showcase Indoor kitchen has no genuine KitchenSpaceFactory counter system: "
            f"{source_path} counts={counts}"
        )
    if role == "showcase_rich" and counts["seating"] < 4:
        raise RuntimeError(
            f"Showcase Indoor living/dining areas need at least four genuine seats: "
            f"{source_path} counts={counts}"
        )
    if role == "showcase_rich" and counts["sanitary"] < 2:
        raise RuntimeError(
            f"Showcase Indoor bathrooms need genuine sanitary fixtures: "
            f"{source_path} counts={counts}"
        )
    if counts["placeholder_objects_excluded"]:
        print(
            f"[all45_09] excluded {counts['placeholder_objects_excluded']} source-only placeholder objects from {source_path}",
            flush=True,
        )
    if counts["blob_plant_objects_excluded"]:
        print(
            "[all45_09] excluded "
            f"{counts['blob_plant_roots_excluded']} blob-like native plant roots / "
            f"{counts['blob_plant_objects_excluded']} hierarchy objects from {source_path}",
            flush=True,
        )
    if counts["toy_trinket_objects_excluded"]:
        print(
            "[all45_09] excluded "
            f"{counts['toy_trinket_roots_excluded']} toy-trinket roots / "
            f"{counts['toy_trinket_objects_excluded']} hierarchy objects from {source_path}",
            flush=True,
        )
    if counts["degenerate_bed_objects_excluded"]:
        print(
            "[all45_09] excluded "
            f"{counts['degenerate_bed_roots_excluded']} room-sized failed BedFactory roots / "
            f"{counts['degenerate_bed_objects_excluded']} hierarchy objects from {source_path}",
            flush=True,
        )
    if counts["verified_chair_replacements"]:
        print(
            "[all45_09] replaced "
            f"{counts['degenerate_chair_assets_excluded']} failed ChairFactory shells with "
            f"{counts['verified_chair_replacements']} verified Infinigen Indoor chairs in {source_path}",
            flush=True,
        )


def centered_positions(count, span):
    if count <= 1:
        return [0.0]
    return [-span / 2 + span * i / (count - 1) for i in range(count)]


def generate_layout(config):
    layout = config["layout"]
    total, low_count = int(layout["building_count"]), int(layout["lowrise_count"])
    high_count = total - low_count
    low_cols = min(3, low_count)
    low_rows = math.ceil(low_count / low_cols)
    low_spacing = float(layout["lowrise_column_spacing"])
    low_row_spacing = float(config["lowrise"]["base_depth"]) + 5.0
    low_xs = centered_positions(low_cols, (low_cols - 1) * low_spacing)
    low_slots = [
        (x, float(layout["lowrise_center_y"]) + row * low_row_spacing)
        for row in range(low_rows)
        for x in low_xs
    ]
    low = [
        {
            "name": f"townhouse_{i+1:02d}",
            "origin": (x, y, 0),
            "yaw": math.radians((-3, 2, -1, 3, -2, 1)[i % 6]),
        }
        for i, (x, y) in enumerate(low_slots[:low_count])
    ]
    high, mode = [], layout["mode"]
    if mode in {"dense_courtyard", "orthogonal_grid"}:
        cols, rows = min(4, high_count), math.ceil(high_count / min(4, high_count))
        xs = centered_positions(
            cols, (cols - 1) * float(layout["highrise_column_spacing"])
        )
        ys = centered_positions(
            rows, (rows - 1) * float(layout["highrise_row_spacing"])
        )
        slots = [(x, float(layout["highrise_center_y"]) + y) for y in ys for x in xs]
        if mode == "orthogonal_grid":
            slots = [(x, y + 2.0 * ((i % 2) - 0.5)) for i, (x, y) in enumerate(slots)]
        for i, (x, y) in enumerate(slots[:high_count]):
            high.append(
                {
                    "name": f"tower_{i+1:02d}",
                    "origin": (x, y, 0),
                    "yaw": math.radians((-4, 3, -2, 4)[i % 4]),
                }
            )
    else:
        left_n = math.ceil(high_count / 2)
        for side, count in ((-1, left_n), (1, high_count - left_n)):
            for y in centered_positions(
                count, (count - 1) * float(layout["highrise_row_spacing"])
            ):
                high.append(
                    {
                        "name": f"tower_{len(high)+1:02d}",
                        "origin": (
                            side * float(layout["highrise_column_spacing"]),
                            float(layout["highrise_center_y"]) + y,
                            0,
                        ),
                        "yaw": math.radians(-side * 7),
                    }
                )
    return low, high


def layout_clearance_audit(low, high, config):
    density = float(config["layout"]["density"])
    high_dims = (
        float(config["highrise"]["base_width"]) * (0.92 + 0.08 * density),
        float(config["highrise"]["base_depth"]) * (0.94 + 0.06 * density),
    )
    low_dims = (
        float(config["lowrise"]["base_width"]),
        float(config["lowrise"]["base_depth"]),
    )

    def edge_clearance(a, a_dims, b, b_dims):
        dx = max(
            0.0, abs(a["origin"][0] - b["origin"][0]) - (a_dims[0] + b_dims[0]) / 2
        )
        dy = max(
            0.0, abs(a["origin"][1] - b["origin"][1]) - (a_dims[1] + b_dims[1]) / 2
        )
        return math.hypot(dx, dy)

    high_high = [
        edge_clearance(a, high_dims, b, high_dims)
        for i, a in enumerate(high)
        for b in high[i + 1 :]
    ]
    low_high = [edge_clearance(a, low_dims, b, high_dims) for a in low for b in high]
    low_low = [
        edge_clearance(a, low_dims, b, low_dims)
        for i, a in enumerate(low)
        for b in low[i + 1 :]
    ]
    return {
        "method": "axis-aligned footprint edge clearance; small authored yaws ignored conservatively",
        "highrise_footprint_m": [round(value, 3) for value in high_dims],
        "lowrise_footprint_m": [round(value, 3) for value in low_dims],
        "minimum_highrise_to_highrise_m": round(min(high_high), 3)
        if high_high
        else None,
        "minimum_lowrise_to_highrise_m": round(min(low_high), 3) if low_high else None,
        "minimum_lowrise_to_lowrise_m": round(min(low_low), 3) if low_low else None,
    }


def add_tower(name, origin, yaw, floors, variant, config, M, A, root):
    """Detailed high-rise shell; deliberately contains no interior assets."""
    c = P.G.make_collection("highrise_" + name, root)
    density = float(config["layout"]["density"])
    w = float(config["highrise"]["base_width"]) * (0.92 + 0.08 * density)
    d = float(config["highrise"]["base_depth"]) * (0.94 + 0.06 * density)
    fh, podium_h = 3.08, 3.65
    h, front = podium_h + floors * fh, -d / 2
    style = config["facade"]["style"]
    if style == "light_terracotta_arcade":
        brick, accent, balcony_master = (
            M["brick_warm"],
            M["board_concrete"],
            "balcony_solid",
        )
    elif style == "dark_metal_vertical":
        brick, accent, balcony_master = (
            M["black_metal"],
            M["copper_patina"],
            "balcony_metal",
        )
    else:
        brick = M["brick_dark" if variant % 2 == 0 else "brick_warm"]
        accent, balcony_master = M["copper_patina"], "balcony_glass"
    P.G.local_box(
        f"{name}_basalt_plinth",
        origin,
        yaw,
        (0, 0.35, 0.52),
        (w + 2.0, d + 1.2, 1.04),
        M["podium_stone"],
        c,
        bevel=0.10,
        segments=4,
    )
    P.G.local_box(
        f"{name}_podium",
        origin,
        yaw,
        (0, 0.15, podium_h / 2),
        (w + 1.25, d + 0.75, podium_h),
        M["board_concrete"],
        c,
        bevel=0.065,
        segments=4,
    )
    P.G.local_box(
        f"{name}_brick_tower",
        origin,
        yaw,
        (-w * 0.075, 0.45, podium_h + floors * fh / 2),
        (w * 0.83, d - 0.25, floors * fh),
        brick,
        c,
        bevel=0.045,
        segments=3,
    )
    P.G.local_box(
        f"{name}_copper_sidecar",
        origin,
        yaw,
        (w * 0.40, 1.0, podium_h + floors * fh * 0.46),
        (w * 0.24, d - 1.45, floors * fh * 0.88),
        accent,
        c,
        bevel=0.055,
        segments=4,
    )
    P.G.local_box(
        f"{name}_shadow_reveal",
        origin,
        yaw,
        (-w * 0.12, front - 0.06, podium_h + floors * fh / 2),
        (w * 0.52, 0.24, floors * fh - 0.75),
        M["black_metal"],
        c,
        bevel=0.012,
    )
    bays = [-w * 0.34, -w * 0.13, w * 0.09, w * 0.31]
    balcony_frequency = float(config["facade"]["balcony_frequency"])
    for floor in range(floors):
        z = podium_h + floor * fh + fh / 2
        P.G.local_box(
            f"{name}_floor_band_{floor:02d}",
            origin,
            yaw,
            (0, front - 0.20, podium_h + floor * fh),
            (w + 0.20, 0.20, 0.11),
            M["board_concrete"],
            c,
            bevel=0.012,
        )
        for bay, x in enumerate(bays):
            use_balcony = (
                (floor * 7 + bay * 3 + variant) % 100
            ) / 100.0 < balcony_frequency
            P.G.local_box(
                f"{name}_recess_{floor:02d}_{bay}",
                origin,
                yaw,
                (x, front - 0.16, z),
                (3.0, 0.30, 2.46),
                M["black_metal"],
                c,
                bevel=0.008,
            )
            if use_balcony and floor > 0:
                P.G.collection_instance(
                    A["sliding_door"],
                    f"{name}_door_{floor}_{bay}",
                    P.G.transform_point(origin, yaw, (x, front - 0.36, z)),
                    c,
                    yaw,
                    (0.76, 0.76, 0.95),
                )
                P.G.collection_instance(
                    A[balcony_master],
                    f"{name}_balcony_{floor}_{bay}",
                    P.G.transform_point(origin, yaw, (x, front - 0.58, z)),
                    c,
                    yaw,
                    (0.69, 0.80, 0.88),
                )
                if (floor + bay + variant) % 4 == 0:
                    P.G.local_box(
                        f"{name}_balcony_planter_{floor}_{bay}",
                        origin,
                        yaw,
                        (x - 0.82, front - 1.72, z - 0.35),
                        (0.64, 0.28, 0.27),
                        accent,
                        c,
                        bevel=0.04,
                        segments=3,
                    )
            else:
                key = "win_living" if (floor + bay) % 3 == 0 else "win_bed"
                scale = (
                    (0.68, 0.70, 0.88) if key == "win_living" else (0.82, 0.82, 0.92)
                )
                P.G.collection_instance(
                    A[key],
                    f"{name}_window_{floor}_{bay}",
                    P.G.transform_point(origin, yaw, (x, front - 0.35, z)),
                    c,
                    yaw,
                    scale,
                )
        for bay, x in enumerate((-w * 0.27, 0, w * 0.27)):
            P.G.local_box(
                f"{name}_rear_recess_{floor}_{bay}",
                origin,
                yaw,
                (x, d / 2 + 0.08, z),
                (2.28, 0.22, 1.95),
                M["black_metal"],
                c,
                bevel=0.008,
            )
            P.G.collection_instance(
                A["win_bed"],
                f"{name}_rear_window_{floor}_{bay}",
                P.G.transform_point(origin, yaw, (x, d / 2 + 0.25, z)),
                c,
                yaw + math.pi,
                (0.74, 0.74, 0.84),
            )
    for i, x in enumerate((-w * 0.48, -w * 0.235, w * 0.195, w * 0.48)):
        if ((i + variant) % 4) / 4.0 <= float(
            config["facade"]["vertical_fin_frequency"]
        ):
            P.G.local_box(
                f"{name}_copper_fin_{i}",
                origin,
                yaw,
                (x, front - 0.48, podium_h + floors * fh / 2),
                (0.18, 0.66, floors * fh + 0.35),
                accent,
                c,
                bevel=0.025,
                segments=3,
            )
    for i, x in enumerate((-1.36, -0.46, 0.46, 1.36)):
        P.G.local_box(
            f"{name}_lobby_glass_{i}",
            origin,
            yaw,
            (x, front - 0.48, 1.88),
            (0.78, 0.055, 2.72),
            M["glass_clear"],
            c,
            bevel=0.008,
        )
    P.G.local_box(
        f"{name}_entrance_canopy",
        origin,
        yaw,
        (0, front - 1.72, 3.32),
        (5.9, 2.65, 0.24),
        accent,
        c,
        bevel=0.035,
        segments=3,
    )
    for x in (-2.55, 2.55):
        P.G.local_box(
            f"{name}_canopy_post_{x}",
            origin,
            yaw,
            (x, front - 2.45, 1.66),
            (0.11, 0.11, 3.20),
            M["black_metal"],
            c,
            bevel=0.012,
        )
    roof_z = h + 0.18
    P.G.local_box(
        f"{name}_roof_membrane",
        origin,
        yaw,
        (0, 0.4, roof_z),
        (w + 0.05, d - 0.18, 0.20),
        M["black_metal"],
        c,
        bevel=0.012,
    )
    for tag, lx, ly, sx, sy in (
        ("front", 0, front, w + 0.35, 0.26),
        ("rear", 0, d / 2, w + 0.35, 0.26),
        ("left", -w / 2, 0, 0.26, d + 0.28),
        ("right", w / 2, 0, 0.26, d + 0.28),
    ):
        P.G.local_box(
            f"{name}_parapet_{tag}",
            origin,
            yaw,
            (lx, ly, h + 0.72),
            (sx, sy, 1.18),
            brick,
            c,
            bevel=0.018,
            segments=2,
        )
    P.G.local_box(
        f"{name}_roof_access",
        origin,
        yaw,
        (w * 0.12, 1.4, h + 0.95),
        (2.6, 2.4, 1.70),
        accent,
        c,
        bevel=0.06,
        segments=4,
    )
    for i, (x, y, scale) in enumerate(
        ((-w * 0.24, -1.5, 0.82), (w * 0.27, -0.2, 0.90))
    ):
        P.G.collection_instance(
            A["hvac"],
            f"{name}_native_hvac_{i}",
            P.G.transform_point(origin, yaw, (x, y, h + 0.32)),
            c,
            yaw,
            (scale,) * 3,
        )
    c["building_type"], c["facade_style"], c["floors"], c["interiors_generated"] = (
        "highrise_shell_no_interior",
        config["facade"]["style"],
        floors,
        False,
    )
    return c, {"name": name, "floors": floors, "width": w, "depth": d}


def lowrise_design(index, config):
    width = float(config["lowrise"]["base_width"])
    return {
        "language": ("B", "C", "A")[index % 3],
        "w": width,
        "d": float(config["lowrise"]["base_depth"]),
        "wall": ("stucco_cream", "stucco_white", "stucco_gray")[index % 3],
        "roof": "gable" if index % 2 == 0 else "mixed",
        "roof_warm": index % 3 == 2,
        "door": "door_a" if index % 2 == 0 else "door_b",
        "door_x": (-0.55, 0.0, 0.55)[index % 3],
        "windows": [
            (-width * 0.37, 1.52, "bed"),
            (-width * 0.205, 1.55, "living"),
            (width * 0.145, 1.58, "narrow"),
            (width * 0.36, 1.52, "bed"),
            (-width * 0.36, 4.70, "bed"),
            (-width * 0.14, 4.70, "slide"),
            (width * 0.10, 4.70, "bed"),
            (width * 0.35, 4.70, "bed"),
        ],
        "balcony": -width * 0.14,
        "balcony_kind": "balcony_metal" if index % 2 else "balcony_glass",
    }


def add_native_indoor_instances(
    name, sources, design, origin, yaw, collection, floors, building_index, config
):
    scale_xy = min((design["w"] - 0.55) / 21.5, (design["d"] - 0.55) / 14.0)
    minimum = float(config["lowrise"]["minimum_native_scale"])
    maximum = float(config["lowrise"]["maximum_native_scale"])
    if not minimum <= scale_xy <= maximum:
        raise RuntimeError(
            f"Native Indoor scale {scale_xy:.3f} for {name} is outside the quality range [{minimum}, {maximum}]"
        )
    roots = []
    source_index = int(config["lowrise"]["building_source_indices"][building_index])
    source = next(
        item for item in sources if int(item.get("source_index", -1)) == source_index
    )
    role = str(config["lowrise"]["building_roles"][building_index])
    for floor in range(floors):
        obj = bpy.data.objects.new(PREFIX + f"{name}_native_indoor_floor_{floor}", None)
        obj.instance_type, obj.instance_collection = "COLLECTION", source
        obj.rotation_euler.z, obj.scale = yaw - math.pi / 2, (scale_xy, scale_xy, 1.0)
        c, s = math.cos(yaw), math.sin(yaw)
        center = (8.25 * scale_xy, -5.5 * scale_xy)
        obj.location = (
            origin[0] - (c * center[0] - s * center[1]),
            origin[1] - (s * center[0] + c * center[1]),
            0.16 + floor * P.FLOOR_H,
        )
        obj["native_infinigen_indoor"] = True
        obj["source_blend"] = source.get("source_blend", "")
        obj["source_index"] = int(source.get("source_index", 0))
        obj["interior_role"] = role
        obj["building_name"] = name
        obj["floor_index"] = floor
        obj["native_scale_xy"] = scale_xy
        collection.objects.link(obj)
        roots.append(obj)
    return roots


def add_lowrise(name, origin, yaw, index, config, indoor_sources, M, A, root):
    design = lowrise_design(index, config)
    coll = P.add_house_exterior(name, design, origin, yaw, M, A, root)
    indoor_roots = add_native_indoor_instances(
        name,
        indoor_sources,
        design,
        origin,
        yaw,
        coll,
        int(config["lowrise"]["floors"]),
        index,
        config,
    )
    front = -design["d"] / 2
    for x in (-design["w"] / 2 + 0.22, design["w"] / 2 - 0.22):
        P.G.local_box(
            f"{name}_expressionist_pier_{x:.2f}",
            origin,
            yaw,
            (x, front - 0.36, 3.15),
            (0.42, 0.58, 6.10),
            M["copper_patina"],
            coll,
            bevel=0.025,
            segments=3,
        )
    coll["building_type"] = "lowrise_native_infinigen_indoor"
    coll["facade_style"] = config["facade"]["style"]
    coll["interiors_generated"] = True
    coll["native_indoor_scale"] = indoor_roots[0]["native_scale_xy"]
    coll["native_indoor_sources"] = len(
        {indoor_root["source_index"] for indoor_root in indoor_roots}
    )
    coll["interior_role"] = str(config["lowrise"]["building_roles"][index])
    return coll, indoor_roots


def ellipse_points(cx, cy, rx, ry, count=24):
    return [
        (
            cx + rx * math.cos(math.tau * i / count),
            cy + ry * math.sin(math.tau * i / count),
        )
        for i in range(count)
    ]


def add_site_and_native_landscape(config, M, A, root):
    c = P.G.make_collection("dense_residential_public_realm", root)
    layout = config["layout"]
    w, d = float(layout["site_width"]), float(layout["site_depth"])
    P.G.poly_prism(
        "dense_district_ground",
        [
            (-w / 2, -d * 0.38),
            (w / 2, -d * 0.38),
            (w / 2, d * 0.56),
            (-w / 2, d * 0.56),
        ],
        -0.12,
        0.16,
        M["dark_paver"],
        c,
        bevel=0.08,
    )
    street_y = -d * 0.43
    P.G.box(
        "connected_public_street",
        (0, street_y, -0.08),
        (w + 12, float(layout["street_width"]), 0.20),
        M["asphalt"],
        c,
        bevel=0.055,
    )
    P.G.box(
        "public_sidewalk",
        (0, street_y + float(layout["street_width"]) * 0.55, 0.04),
        (w + 8, 3.4, 0.14),
        M["pale_paver"],
        c,
        bevel=0.045,
    )
    P.G.box(
        "east_west_shared_mews",
        (0, 0, 0.055),
        (w - 8, 5.2, 0.13),
        M["pale_paver"],
        c,
        bevel=0.07,
    )
    P.G.box(
        "north_south_shared_mews",
        (0, d * 0.19, 0.06),
        (5.2, d * 0.71, 0.14),
        M["pale_paver"],
        c,
        bevel=0.07,
    )
    for i, x in enumerate(centered_positions(9, w - 18)):
        P.G.box(
            f"street_tree_pit_{i:02d}",
            (x, street_y + 5.65, 0.13),
            (2.0, 1.75, 0.18),
            M["mulch"],
            c,
            bevel=0.30,
            segments=5,
        )
    land = config["landscape"]
    candidates = [
        (-w * 0.40, -2, 3.4, 2.1),
        (-w * 0.25, 2, 3, 1.8),
        (-w * 0.10, -2, 3, 2),
        (w * 0.10, 2, 3, 1.9),
        (w * 0.25, -2, 3.1, 1.8),
        (w * 0.40, 2, 3.4, 2.1),
        (-w * 0.18, d * 0.48, 3.2, 2),
        (w * 0.18, d * 0.48, 3.2, 2),
    ]
    bed_count = min(int(land["bed_count"]), len(candidates))
    rng = random.Random(int(config["seed"]) + 91)
    planting_z = 0.22
    stats = {
        "trees": 0,
        "shrubs": 0,
        "flowers": 0,
        "grass": 0,
        "beds": bed_count,
        "planting_surface_z": planting_z,
        "grounded_instance_roots": 0,
        "instances_outside_authored_beds_or_tree_pits": 0,
    }
    for bed_i, (cx, cy, rx, ry) in enumerate(candidates[:bed_count]):
        P.G.poly_prism(
            f"native_bed_{bed_i:02d}_basalt_edge",
            ellipse_points(cx, cy, rx, ry),
            0.08,
            0.16,
            M["podium_stone"],
            c,
            bevel=0.035,
        )
        P.G.poly_prism(
            f"native_bed_{bed_i:02d}_mulch",
            ellipse_points(cx, cy, rx - 0.28, ry - 0.25),
            0.17,
            0.05,
            M["mulch"],
            c,
            bevel=0.025,
        )
        if bed_i % 2 == 0 and stats["trees"] < int(land["tree_count"]):
            scale = rng.uniform(0.62, 0.78)
            P.G.collection_instance(
                A[f"native_tree_{bed_i%5}"],
                f"native_tree_bed_{bed_i}",
                (cx, cy, planting_z),
                c,
                rng.uniform(0, math.tau),
                (scale,) * 3,
            )
            stats["trees"] += 1
            stats["grounded_instance_roots"] += 1
        for kind, count in (
            ("shrub", int(land["shrubs_per_bed"])),
            ("flower", int(land["flowers_per_bed"])),
            ("grass", int(land["grass_per_bed"])),
        ):
            if count:
                raise RuntimeError(
                    f"{kind} small-vegetation instances are disabled in all45_09; got count={count}"
                )
            master_count = A[f"native_{kind}_count"]
            for j in range(count):
                angle, radial = rng.uniform(0, math.tau), math.sqrt(
                    rng.uniform(0.08, 0.82)
                )
                x, y = cx + rx * radial * math.cos(angle), cy + ry * radial * math.sin(
                    angle
                )
                scale = (
                    rng.uniform(0.42, 0.68)
                    if kind == "flower"
                    else rng.uniform(0.85, 1.25)
                )
                P.G.collection_instance(
                    A[f"native_{kind}_{(j*3+bed_i*5)%master_count}"],
                    f"native_{kind}_{bed_i}_{j}",
                    (x, y, planting_z),
                    c,
                    rng.uniform(0, math.tau),
                    (scale,) * 3,
                )
                stats[
                    {"shrub": "shrubs", "flower": "flowers", "grass": "grass"}[kind]
                ] += 1
                stats["grounded_instance_roots"] += 1
    remaining = max(0, int(land["tree_count"]) - stats["trees"])
    for i, x in enumerate(centered_positions(remaining, w - 18)):
        scale = 0.64 + 0.04 * (i % 4)
        P.G.collection_instance(
            A[f"native_tree_{i%5}"],
            f"native_street_tree_{i}",
            (x, street_y + 5.65, planting_z),
            c,
            i * 0.81,
            (scale,) * 3,
        )
        stats["trees"] += 1
        stats["grounded_instance_roots"] += 1
    stats["expected_instance_roots"] = (
        stats["trees"] + stats["shrubs"] + stats["flowers"] + stats["grass"]
    )
    if stats["grounded_instance_roots"] != stats["expected_instance_roots"]:
        raise RuntimeError(f"Landscape grounding audit failed: {stats}")
    if stats["shrubs"] or stats["flowers"] or stats["grass"]:
        raise RuntimeError(f"Floating ground-cover removal audit failed: {stats}")
    return stats


def add_lighting():
    world = bpy.data.worlds.new(PREFIX + "late_afternoon_sky")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (
        0.32,
        0.43,
        0.56,
        1,
    ), 0.48
    bpy.context.scene.world = world
    bpy.ops.object.light_add(
        type="SUN",
        location=(-35, -55, 72),
        rotation=(math.radians(31), math.radians(-18), math.radians(-36)),
    )
    sun = bpy.context.object
    sun.name, sun.data.energy, sun.data.angle = PREFIX + "sun", 3.1, math.radians(5)
    bpy.ops.object.light_add(type="AREA", location=(0, -30, 46))
    fill = bpy.context.object
    fill.name, fill.data.energy, fill.data.shape, fill.data.size = (
        PREFIX + "sky_fill",
        850,
        "DISK",
        32,
    )


def cameras(config):
    d = float(config["layout"]["site_depth"])

    def camera(name, location, target, fov):
        bpy.ops.object.camera_add(location=location)
        obj = bpy.context.object
        obj.name, obj.data.lens_unit, obj.data.angle, obj.data.clip_start = (
            PREFIX + "cam_" + name,
            "FOV",
            math.radians(fov),
            0.04,
        )
        obj.rotation_euler = (
            (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        )
        return obj, name + ".png"

    specs = [
        ("01_spaced_district_overview", (0, -150, 88), (0, 12, 13), 60),
        ("02_street_wall", (-68, -71, 9.0), (-42, -17, 5), 57),
        ("03_highrise_facade_close", (-70, -27, 15), (-49, 10, 17), 47),
        ("04_lowrise_native_indoor_window", (-42, -34, 2.35), (-42, -24.3, 1.45), 54),
        ("05_courtyard_native_landscape", (-18, -7, 2.6), (-38, 1.0, 0.65), 56),
        ("06_layout_aerial", (86, -94, 118), (0, d * 0.10, 5), 55),
    ]
    return [camera(*item) for item in specs]


def configure_render(config):
    sc, render = bpy.context.scene, config["render"]
    sc.render.engine = render["engine"]
    if sc.render.engine == "CYCLES":
        sc.cycles.device, sc.cycles.samples = "CPU", int(render["samples"])
        (
            sc.cycles.use_denoising,
            sc.cycles.use_adaptive_sampling,
            sc.cycles.adaptive_threshold,
        ) = (True, True, 0.03)
    sc.render.resolution_x, sc.render.resolution_y = map(int, render["resolution"])
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = (
        "PNG",
        "RGBA",
    )
    sc.view_settings.look = "AgX - Medium High Contrast"


def main():
    started, config = time.time(), load_config()
    configure(config)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    P.G.reset_scene()
    print(f"[all45_09] config={json.dumps(config, ensure_ascii=False)}", flush=True)
    root = P.G.make_collection("parameterized_residential_generator_45_09")
    root["production_generator"], root["parameter_schema_version"] = (
        True,
        config["schema_version"],
    )
    root["layout_mode"], root["facade_style"] = (
        config["layout"]["mode"],
        config["facade"]["style"],
    )
    M = make_materials(config)
    P.G.MATS = M
    A = make_assets(M)
    vegetation_assets = native_vegetation_assets(A)
    chair_template = load_verified_chair_template()
    source_indices = [
        int(index) for index in config["lowrise"]["indoor_source_indices"]
    ]
    building_sources = [
        int(index) for index in config["lowrise"]["building_source_indices"]
    ]
    building_roles = [str(role) for role in config["lowrise"]["building_roles"]]
    role_by_source = dict(zip(building_sources, building_roles))
    indoor_sources, indoor_counts = [], []
    for source_index in source_indices:
        role = role_by_source[source_index]
        source, counts = load_native_indoor(
            INDOOR_SOURCES[source_index], source_index, role, chair_template
        )
        validate_indoor_quality(INDOOR_SOURCES[source_index], role, counts)
        indoor_sources.append(source)
        indoor_counts.append(
            {
                "source": str(INDOOR_SOURCES[source_index]),
                "role": role,
                "counts": counts,
            }
        )
    showcase_count = next(
        item["counts"]["placed_asset_objects"]
        for item in indoor_counts
        if item["role"] == "showcase_rich"
    )
    companion_counts = [
        item["counts"]["placed_asset_objects"]
        for item in indoor_counts
        if item["role"] == "companion_reduced"
    ]
    if showcase_count <= max(companion_counts):
        raise RuntimeError(
            f"Showcase Indoor must be richer than both companions: showcase={showcase_count}, companions={companion_counts}"
        )
    low_layout, high_layout = generate_layout(config)
    clearance_audit = layout_clearance_audit(low_layout, high_layout, config)
    if clearance_audit["minimum_highrise_to_highrise_m"] <= 12.0:
        raise RuntimeError(f"High-rise spacing audit failed: {clearance_audit}")
    if (
        clearance_audit["minimum_lowrise_to_highrise_m"]
        >= clearance_audit["minimum_highrise_to_highrise_m"]
    ):
        raise RuntimeError(
            f"Low-rise/high-rise proximity audit failed: {clearance_audit}"
        )
    print(
        f"[all45_09] layout lowrise={len(low_layout)} highrise={len(high_layout)} "
        f"clearances={json.dumps(clearance_audit, ensure_ascii=False)}",
        flush=True,
    )
    landscape = add_site_and_native_landscape(config, M, A, root)
    indoor_roots = []
    for i, item in enumerate(low_layout):
        _, roots = add_lowrise(
            item["name"],
            item["origin"],
            item["yaw"],
            i,
            config,
            indoor_sources,
            M,
            A,
            root,
        )
        indoor_roots.extend(roots)
    rng = random.Random(int(config["seed"]) + 17)
    floor_lo, floor_hi = map(int, config["highrise"]["floor_range"])
    tower_stats = []
    for i, item in enumerate(high_layout):
        _, stats = add_tower(
            item["name"],
            item["origin"],
            item["yaw"],
            rng.randint(floor_lo, floor_hi),
            i,
            config,
            M,
            A,
            root,
        )
        tower_stats.append(stats)
    for key in ("glass", "glass_clear", "glass_balcony"):
        material = M[key]
        bsdf = next(
            (
                node
                for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED"
            ),
            None,
        )
        if bsdf:
            P.G.set_input(bsdf, "Transmission Weight", 0.92)
            P.G.set_input(bsdf, "Alpha", 0.18)
            P.G.set_input(bsdf, "Roughness", 0.04)
            P.G.set_input(bsdf, "IOR", 1.45)
    add_lighting()
    cam_list = cameras(config)
    configure_render(config)
    (OUT / "generation_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf8"
    )
    gross = sum(t["width"] * t["depth"] * t["floors"] for t in tower_stats)
    gross += (
        len(low_layout)
        * float(config["lowrise"]["base_width"])
        * float(config["lowrise"]["base_depth"])
        * int(config["lowrise"]["floors"])
    )
    audit = {
        "clean_scene": True,
        "entry_point": __file__,
        "revision": "urban_v3_all45_09",
        "parameterized_controls": [
            "layout.mode",
            "layout.building_count",
            "layout.lowrise_count",
            "layout.density",
            "layout.highrise_column_spacing",
            "layout.highrise_row_spacing",
            "layout.highrise_center_y",
            "layout.lowrise_column_spacing",
            "layout.lowrise_center_y",
            "highrise.floor_range",
            "lowrise.base_width",
            "lowrise.base_depth",
            "facade.style",
            "facade.palette",
            "facade.color_variation",
            "facade.balcony_frequency",
            "facade.vertical_fin_frequency",
        ],
        "resolved_config": config,
        "building_count": len(low_layout) + len(high_layout),
        "lowrise_count": len(low_layout),
        "highrise_count": len(high_layout),
        "highrise_interiors": 0,
        "layout_clearances": clearance_audit,
        "lowrise_native_indoor_instances": len(indoor_roots),
        "lowrise_native_indoor_sources": [
            str(INDOOR_SOURCES[index]) for index in source_indices
        ],
        "lowrise_building_roles": [
            {
                "building": low_layout[index]["name"],
                "role": building_roles[index],
                "source_index": building_sources[index],
                "source": str(INDOOR_SOURCES[building_sources[index]]),
            }
            for index in range(len(low_layout))
        ],
        "lowrise_native_scale_range": [
            round(min(float(obj["native_scale_xy"]) for obj in indoor_roots), 4),
            round(max(float(obj["native_scale_xy"]) for obj in indoor_roots), 4),
        ],
        "native_indoor_counts": indoor_counts,
        "tower_stats": tower_stats,
        "verified_infinigen_chair_template": {
            key: value for key, value in chair_template.items() if key != "mesh"
        },
        "estimated_gross_floor_area_m2": round(gross, 1),
        "facade_style": config["facade"]["style"],
        "revision_from_all45_08": "all fragmentary shrub/flower/grass masters removed; verified native Infinigen Indoor sources instanced as one rich showcase and two reduced companions; failed ChairFactory shells replaced at authored solver anchors with visually verified genuine Infinigen Indoor chairs; room-sized failed BedFactory hierarchy rejected; room views assigned by actual floor polygons",
        "vegetation_assets": vegetation_assets,
        "landscape_instances": landscape,
        "proxy_or_blob_vegetation_assets": 0,
        "toy_or_placeholder_interior_assets": 0,
        "renders": [filename for _, filename in cam_list],
    }
    (OUT / "generation_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45_09.blend"))
    selected = set(config["render"]["validation_views"])
    for camera, filename in cam_list:
        if filename not in selected:
            continue
        indoor_view = filename == "04_lowrise_native_indoor_window.png"
        for i, indoor in enumerate(indoor_roots):
            indoor.hide_render = not (indoor_view and i < 2)
        bpy.context.scene.camera, bpy.context.scene.render.filepath = camera, str(
            RENDERS / filename
        )
        bpy.ops.render.render(write_still=True)
        print(f"[all45_09] rendered {filename}", flush=True)
    print(f"[all45_09] complete in {time.time()-started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
