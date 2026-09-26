"""
scripts/urban_assets.py — LegacyWorld outdoor urban asset library

Provides:
  • _import_coll / _import_prefix — append pre-built .blend assets
  • _place — reposition a batch of objects to a target XY with optional yaw
  • place_* — per-asset convenience wrappers
  • Procedural builders: road, sidewalk, green-belt, tree, flowerbed, car, house
  • Shared material system (M dict populated by build_all_materials())

Usage from a Blender scene script:
    import sys
    sys.path.insert(0, "./scripts")
    import urban_assets as UA
    UA.build_all_materials()
    C_road = UA.new_coll("Road")
    UA.build_road(C_road)
    UA.place_trafficlight((0, -30), C_tl)
    ...
"""

from pathlib import Path as _AssetPath
_ASSET_PROJECT_ROOT = next(p for p in _AssetPath(__file__).resolve().parents if (p / "worldbridge").is_dir())


import importlib.util
import math
import bpy
from pathlib import Path
from mathutils import Vector, Matrix


def _load_delivery_generator(prefix="urban_delivery:"):
    """Load the live delivery source generator without reading a result blend."""
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_delivery.py"
    spec = importlib.util.spec_from_file_location("c2w_delivery_reference_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural delivery generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_food_delivery_locker(C=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                               prefix="urban_delivery:food:"):
    """Build one detailed food-delivery locker directly from procedural source."""
    module, generator_path = _load_delivery_generator(prefix)
    asset = module.build_food_delivery_locker(
        C or bpy.context.scene.collection, origin=origin, yaw=yaw)
    asset["c2w_pipeline_adapter"] = "urban_assets.build_food_delivery_locker"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_parcel_locker(C=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                        prefix="urban_delivery:parcel:"):
    """Build one detailed green parcel locker directly from procedural source."""
    module, generator_path = _load_delivery_generator(prefix)
    asset = module.build_parcel_locker(
        C or bpy.context.scene.collection, origin=origin, yaw=yaw)
    asset["c2w_pipeline_adapter"] = "urban_assets.build_parcel_locker"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_delivery_station(C=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                           prefix="urban_delivery:station:"):
    """Build the glazed, stocked parcel station directly from procedural source."""
    module, generator_path = _load_delivery_generator(prefix)
    asset = module.build_delivery_station(
        C or bpy.context.scene.collection, origin=origin, yaw=yaw)
    asset["c2w_pipeline_adapter"] = "urban_assets.build_delivery_station"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_delivery_reference_row(C=None, include_site=True,
                                 origin=(0.0, 0.0, 0.0), yaw=0.0,
                                 prefix="urban_delivery:"):
    """Build all three delivery assets through the live Urban-v3 adapter."""
    module, generator_path = _load_delivery_generator(prefix)
    root, _materials = module.build_delivery_reference_row(
        C or bpy.context.scene.collection, include_site=include_site,
        origin=origin, yaw=yaw)
    root["c2w_pipeline_adapter"] = "urban_assets.build_delivery_reference_row"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


FITNESS_VARIANTS = (
    "air_walker_double",
    "ski_walker",
    "rider_trainer",
    "stepper_station",
    "double_leg_press",
    "double_surf_board",
    "double_traction_station",
    "stall_bars",
    "rowing_machine",
    "fitness_notice_board",
)


def _load_outdoor_fitness_generator(prefix):
    """Load the canonical procedural source; never append the validation blend."""
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_fitness.py"
    spec = importlib.util.spec_from_file_location("c2w_outdoor_fitness_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural fitness generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    import sys
    # The source uses dataclasses, which resolve their module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_outdoor_fitness_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                                prefix="urban_fitness:"):
    """Build one independently selectable, high-detail outdoor fitness machine."""
    if variant not in FITNESS_VARIANTS:
        raise ValueError(f"Unknown fitness variant {variant!r}; expected one of {FITNESS_VARIANTS}")
    module, generator_path = _load_outdoor_fitness_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_outdoor_fitness_asset(
        variant, parent=parent, origin=location, yaw=yaw
    )
    asset["c2w_pipeline_adapter"] = "urban_assets.build_outdoor_fitness_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_outdoor_fitness_area(C=None, include_site=True, layout=None,
                               location=(0.0, 0.0, 0.0), yaw=0.0,
                               prefix="urban_fitness:"):
    """Build and arrange all twenty reference-driven stations in one park zone.

    This is the live Urban-v3 pipeline adapter.  The generated ``.blend`` is a
    validation artifact only; production scenes execute the source builder here.
    """
    module, generator_path = _load_outdoor_fitness_generator(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_outdoor_fitness_area(
        parent=parent, include_site=include_site, layout=layout,
        origin=location, yaw=yaw,
    )
    root["c2w_pipeline_adapter"] = "urban_assets.build_outdoor_fitness_area"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


FIRE_TRUCK_VARIANTS = ("modern_ladder_engine", "classic_pumper", "rapid_rescue")
FIRE_STATION_VARIANTS = ("civic_headquarters", "industrial_annex")


def _load_fire_region_generator(prefix):
    """Load the source fire-region factory, never its validation blend."""
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_fire.py"
    spec = importlib.util.spec_from_file_location("c2w_fire_station_region_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural fire-region generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_fire_truck_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                           prefix="urban_fire:"):
    """Build one high-detail procedural apparatus type at a pipeline pose."""
    if variant not in FIRE_TRUCK_VARIANTS:
        raise ValueError(f"Unknown fire-truck variant {variant!r}; expected one of {FIRE_TRUCK_VARIANTS}")
    module, generator_path = _load_fire_region_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_fire_truck_asset(variant, parent=parent, origin=location, yaw=yaw)
    asset["c2w_pipeline_adapter"] = "urban_assets.build_fire_truck_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_fire_station_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                             include_site=True, prefix="urban_fire:"):
    """Build one complete procedural station archetype at a pipeline pose."""
    if variant not in FIRE_STATION_VARIANTS:
        raise ValueError(f"Unknown fire-station variant {variant!r}; expected one of {FIRE_STATION_VARIANTS}")
    module, generator_path = _load_fire_region_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_fire_station_asset(
        variant, parent=parent, origin=location, yaw=yaw, include_site=include_site
    )
    asset["c2w_pipeline_adapter"] = "urban_assets.build_fire_station_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_fire_station_region(C=None, include_site=True, prefix="urban_fire:"):
    """Build the two-station/three-apparatus precinct from live source.

    The validation ``.blend`` is intentionally never loaded: production calls
    the same source entrypoint used by the isolated verification run.
    """
    module, generator_path = _load_fire_region_generator(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_fire_station_region(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_fire_station_region"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


GAS_STATION_VARIANTS = ("nobile_wave", "blue_orange", "red_yellow")


def _load_gas_station_generator(prefix):
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_gass.py"
    spec = importlib.util.spec_from_file_location("c2w_gas_station_reference_row_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural gas-station generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their defining module through sys.modules while the
    # source is executed; register this dynamic module before exec_module.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_gas_station_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                            include_site=True, prefix="urban_gas_station:"):
    """Build one selected high-detail station at a pipeline-controlled pose."""
    if variant not in GAS_STATION_VARIANTS:
        raise ValueError(f"Unknown gas-station variant {variant!r}; expected one of {GAS_STATION_VARIANTS}")
    module, generator_path = _load_gas_station_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_gas_station_asset(
        variant, parent=parent, origin=location, yaw=yaw, include_site=include_site
    )
    asset["c2w_pipeline_adapter"] = "urban_assets.build_gas_station_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_gas_station_reference_row(C=None, include_site=True, prefix="urban_gas_station:"):
    """Build all three detailed gas-station archetypes from procedural source.

    This is the active Urban-v3 adapter.  It invokes the same source entrypoint
    used by the isolated validation run and never appends the generated blend,
    so production scenes cannot fall back to a stale or simplified station.
    """
    module, generator_path = _load_gas_station_generator(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_gas_station_reference_row(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_gas_station_reference_row"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


def build_library_pair(C=None, include_site=True, prefix="urban_library:"):
    """Build both reference-driven public libraries from procedural source.

    This is the active urban-pipeline adapter.  It imports the source generator
    and invokes ``build_library_pair`` directly; the validation blend under
    ``outputs/`` is deliberately not loaded.
    """
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_library.py"
    spec = importlib.util.spec_from_file_location("c2w_library_pair_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural library generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_library_pair(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_library_pair"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


HOSPITAL_VARIANTS = (
    "traditional_brick",
    "red_white_public",
    "glass_ribbon_modern",
)


def _load_hospital_generator(prefix):
    """Load the live source generator, never the validation blend output."""
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_hospital.py"
    spec = importlib.util.spec_from_file_location("c2w_hospital_reference_row_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural hospital generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_hospital_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                         include_site=True, prefix="urban_hospital:"):
    """Build one of the three high-detail reference hospitals from source.

    This adapter is the production single-asset entry point.  It creates the
    requested variant at a pipeline-controlled transform and has no dependency
    on ``outputs/outdoor_part_demo/urban_v3_hospital/*.blend``.
    """
    if variant not in HOSPITAL_VARIANTS:
        raise ValueError(f"Unknown hospital variant {variant!r}; expected one of {HOSPITAL_VARIANTS}")
    module, generator_path = _load_hospital_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_hospital_asset(
        variant,
        parent=parent,
        origin=location,
        yaw=yaw,
        include_site=include_site,
    )
    asset["c2w_pipeline_adapter"] = "urban_assets.build_hospital_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_hospital_reference_row(C=None, include_site=True, prefix="urban_hospital:"):
    """Build all three reference-matched hospitals in the active pipeline.

    The source generator is invoked directly, so the same detailed geometry
    used for validation is what downstream urban scenes receive.  The saved
    validation blend is never appended and cannot drift from production code.
    """
    module, generator_path = _load_hospital_generator(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_hospital_reference_row(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_hospital_reference_row"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


POLICE_STATION_VARIANTS = (
    "blue_white_civic",
    "brick_tower_municipal",
    "blue_portal_cmu",
)


def _load_police_generator(prefix):
    """Load the live police source generator, never its validation blend."""
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_police.py"
    spec = importlib.util.spec_from_file_location("c2w_police_reference_region_v8", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural police generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    return module, generator_path


def build_police_station_asset(variant, C=None, location=(0.0, 0.0, 0.0), yaw=0.0,
                               include_site=False, prefix="urban_police:"):
    """Build one selected high-detail reference police station from source.

    This is the production single-asset entry point.  It has no dependency on
    ``outputs/outdoor_part_demo/urban_v3_police2/urban_v3_police2.blend``.
    """
    if variant not in POLICE_STATION_VARIANTS:
        raise ValueError(
            f"Unknown police-station variant {variant!r}; expected one of {POLICE_STATION_VARIANTS}"
        )
    module, generator_path = _load_police_generator(prefix)
    parent = C or bpy.context.scene.collection
    asset = module.build_police_station_asset(
        variant, parent=parent, origin=location, yaw=yaw, include_site=include_site
    )
    asset["c2w_pipeline_adapter"] = "urban_assets.build_police_station_asset"
    asset["c2w_source_generator"] = generator_path.name
    asset["c2w_scene_asset_inputs"] = 0
    return asset


def build_police_reference_row(C=None, include_site=False, prefix="urban_police:"):
    """Build and arrange all three reference stations from the live generator.

    Production and isolated validation execute the identical source builder;
    the saved blend is an output artifact and is never appended here.
    """
    module, generator_path = _load_police_generator(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_police_reference_row(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_police_reference_row"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


def build_financial_bank_campus(C=None, include_public_realm=True, prefix="urban_bank:"):
    """Build the all46_2 four-bank campus directly from procedural source.

    This is the urban pipeline adapter.  It deliberately imports the generator
    module rather than appending the validation ``.blend`` so production scenes
    receive the same reference-driven geometry and metadata as the demo run.
    """
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_all46_2.py"
    spec = importlib.util.spec_from_file_location("c2w_bank_campus_all46_2", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural bank generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PREFIX = prefix
    module.G.PREFIX = prefix
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_financial_campus(parent, include_public_realm=include_public_realm)
    root["c2w_pipeline_adapter"] = "urban_assets.build_financial_bank_campus"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root


def build_pharmacy_reference_row(C=None, include_site=True, prefix="urban_pharmacy:"):
    """Build both detailed pharmacy archetypes directly from procedural source.

    This is the live Urban-v3 adapter.  It deliberately calls the same source
    entrypoint that creates the validation result instead of appending a blend,
    so pipeline scenes cannot silently fall back to an older simplified asset.
    """
    generator_path = Path(__file__).resolve().parent / "generate_urban_v3_pharmacy.py"
    spec = importlib.util.spec_from_file_location("c2w_pharmacy_reference_row_v3", generator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load procedural pharmacy generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.set_prefix(prefix)
    parent = C or bpy.context.scene.collection
    root, _materials = module.build_pharmacy_reference_row(parent, include_site=include_site)
    root["c2w_pipeline_adapter"] = "urban_assets.build_pharmacy_reference_row"
    root["c2w_source_generator"] = generator_path.name
    root["c2w_scene_asset_inputs"] = 0
    return root

# ─── BLEND FILE PATHS ─────────────────────────────────────────────────────────
_BASE = Path(str(_ASSET_PROJECT_ROOT / 'assets/models/urban_components'))
BLEND = {
    "trafficlight": _BASE / "urban_v3_trafficlight3/traffic_lights.blend",
    "busstop":      _BASE / "urban_v3_busstop/bus_stop.blend",
    "bench_bin":    _BASE / "urban_v3_longchair+trashbin2/furniture.blend",
    "kiosk5":       _BASE / "urban_v3_kiosk5/kiosk.blend",
    "bicycle":      _BASE / "urban_v3_sharedbicycle4/bike_station.blend",
    "phonebooth":   _BASE / "urban_v3_phonebooth3/phonebooth3.blend",
    "streetlight":  _BASE / "urban_v3_streetlight/streetlight.blend",
    "belt2":        _BASE / "urban_v3_belt2/belt2.blend",
    "vehicle":      _BASE / "urban_v3_vehicle/openx_preview.blend",
    "vehicles_inf": _BASE / "urban_block_10/linked_assets_clean_min/vehicles.blend",
    "trees_inf":    _BASE / "urban_v3_trees/trees.blend",
    # Generated from scripts/generate_urban_v3_atm.py.  Keep this path rooted
    # in the checkout so the ATM factory/asset works in the current pipeline
    # even when the legacy /data mount alias is absent.
    "atm4":         Path(__file__).resolve().parents[1] / "infinigen/outputs/outdoor_part_demo/urban_v3_atm4/urban_v3_atm4.blend",
}

# ─── GLOBAL MATERIAL DICT ─────────────────────────────────────────────────────
M: dict = {}
_PRIMITIVE_MESHES: dict = {}
_ASSET_PROTOTYPES: dict = {}
_LIBRARY_LOADS: dict = {}

# ─── SCENE UTILITIES ──────────────────────────────────────────────────────────
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.engine = "CYCLES"
    _PRIMITIVE_MESHES.clear()
    _ASSET_PROTOTYPES.clear()
    _LIBRARY_LOADS.clear()

def new_coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c

def _tag_instance(obj, asset_id):
    obj["c2w_role"] = "instance"
    obj["c2w_asset_id"] = asset_id
    obj["c2w_instance_id"] = obj.name
    obj["c2w_run_id"] = "urban_pipeline"
    obj["c2w_schema_version"] = 2
    return obj

def _material_key(mat):
    return mat.name_full if mat else ""

def _mesh_from_operator(key, operator):
    mesh = _PRIMITIVE_MESHES.get(key)
    if mesh is not None:
        return mesh
    operator()
    source = bpy.context.active_object
    mesh = source.data
    mesh.name = "C2W_MESH_" + str(len(_PRIMITIVE_MESHES)).zfill(4)
    bpy.data.objects.remove(source, do_unlink=True)
    mesh["c2w_asset_id"] = "primitive:" + repr(key)
    _PRIMITIVE_MESHES[key] = mesh
    return mesh

def to_coll(obj, c):
    for oc in list(obj.users_collection):
        try: oc.objects.unlink(obj)
        except RuntimeError: pass
    try: c.objects.link(obj)
    except RuntimeError: pass
    return obj

# ─── PRIMITIVE BUILDERS ───────────────────────────────────────────────────────
def _box(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=0.0, rz=0.0):
    key = ("cube", _material_key(mat), round(bev, 6))
    mesh = _mesh_from_operator(key, lambda: bpy.ops.mesh.primitive_cube_add(size=1))
    o = bpy.data.objects.new(name, mesh)
    coll.objects.link(o)
    o.location = (cx, cy, cz); o.scale = (dx, dy, dz)
    o.name = name
    if bev > 0:
        m = o.modifiers.new("Bev", "BEVEL")
        m.width = bev; m.segments = 2; m.limit_method = "ANGLE"
        m.angle_limit = math.radians(30)
    if rz: o.rotation_euler[2] = rz
    if mat and not o.data.materials: o.data.materials.append(mat)
    _tag_instance(o, "primitive.box:" + _material_key(mat))
    return o

def _cyl(name, cx, cy, cz, r, h, mat, coll, verts=32, rx=0.0, rz=0.0, cap_ends=True):
    key = ("cylinder", int(verts), bool(cap_ends), _material_key(mat))
    mesh = _mesh_from_operator(key, lambda: bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=1, depth=1,
        end_fill_type="NGON" if cap_ends else "NOTHING"))
    o = bpy.data.objects.new(name, mesh); coll.objects.link(o)
    o.location = (cx, cy, cz + h / 2); o.scale = (r, r, h)
    o.name = name
    if rx: o.rotation_euler[0] = rx
    if rz: o.rotation_euler[2] = rz
    if mat and not o.data.materials: o.data.materials.append(mat)
    _tag_instance(o, "primitive.cylinder:" + _material_key(mat))
    return o

def _sph(name, cx, cy, cz, r, mat, coll, segs=24, rings=16):
    key = ("sphere", int(segs), int(rings), _material_key(mat))
    mesh = _mesh_from_operator(key, lambda: bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segs, ring_count=rings, radius=1))
    o = bpy.data.objects.new(name, mesh); coll.objects.link(o)
    o.location = (cx, cy, cz); o.scale = (r, r, r)
    o.name = name
    if mat and not o.data.materials: o.data.materials.append(mat)
    _tag_instance(o, "primitive.sphere:" + _material_key(mat))
    return o

# ─── MATERIAL SYSTEM ──────────────────────────────────────────────────────────
def _pbr(name, rgb, rough=0.5, metal=0.0, emit=None, emit_str=1.0, alpha=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit_str
    if alpha < 1.0:
        try: bsdf.inputs["Transmission Weight"].default_value = 1.0 - alpha
        except KeyError: pass
        mat.blend_method = "BLEND"
    return mat

def _noise_mat(name, rgb1, rgb2, rough=0.65, scale=6.0, detail=4.0):
    """PBR material with subtle noise color variation."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes; links = nt.links
    for n in nodes: nodes.remove(n)

    out  = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    mix  = nodes.new("ShaderNodeMixRGB")
    noi  = nodes.new("ShaderNodeTexNoise")
    cord = nodes.new("ShaderNodeTexCoord")

    cord.location = (-600, 0); noi.location = (-400, 0)
    mix.location  = (-200, 0); bsdf.location = (0, 0); out.location = (250, 0)

    noi.inputs["Scale"].default_value  = scale
    noi.inputs["Detail"].default_value = detail
    mix.blend_type = "MIX"
    mix.inputs["Color1"].default_value = (*rgb1, 1.0)
    mix.inputs["Color2"].default_value = (*rgb2, 1.0)
    bsdf.inputs["Roughness"].default_value = rough

    links.new(cord.outputs["Generated"], noi.inputs["Vector"])
    links.new(noi.outputs["Fac"],        mix.inputs["Fac"])
    links.new(mix.outputs["Color"],      bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"],      out.inputs["Surface"])
    return mat

def _glass(name, tint=(0.88, 0.95, 0.98)):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.02
    bsdf.inputs["IOR"].default_value = 1.45
    try: bsdf.inputs["Transmission Weight"].default_value = 1.0
    except KeyError: pass
    mat.blend_method = "BLEND"
    return mat

def build_all_materials():
    """Populate M dict with all scene materials."""
    M["road"]       = _noise_mat("road",     (0.07,0.07,0.07),(0.11,0.11,0.11), rough=0.93, scale=8)
    M["sidewalk"]   = _noise_mat("sidewalk", (0.72,0.70,0.68),(0.62,0.60,0.58), rough=0.78, scale=10)
    M["curb"]       = _pbr("curb",      (0.55,0.53,0.50), rough=0.80)
    M["greenstrip"] = _noise_mat("greenstrip",(0.12,0.28,0.08),(0.18,0.35,0.12), rough=0.85, scale=18)
    M["soil"]       = _noise_mat("soil",     (0.22,0.14,0.08),(0.28,0.18,0.10), rough=0.90, scale=12)
    M["wall"]       = _pbr("wall",      (0.88,0.86,0.80), rough=0.62)
    M["wall2"]      = _pbr("wall2",     (0.78,0.82,0.78), rough=0.62)
    M["roof_tile"]  = _pbr("roof_tile", (0.60,0.22,0.10), rough=0.68)
    M["roof_flat"]  = _pbr("roof_flat", (0.35,0.33,0.32), rough=0.75)
    M["window"]     = _glass("window")
    M["door"]       = _pbr("door",      (0.35,0.22,0.12), rough=0.45)
    M["fence"]      = _pbr("fence",     (0.90,0.88,0.85), rough=0.65)
    M["car_paint"]  = _pbr("car_paint", (0.05,0.10,0.55), rough=0.15, metal=0.0)
    M["car_paint2"] = _pbr("car_paint2",(0.55,0.10,0.08), rough=0.15, metal=0.0)
    M["car_glass"]  = _glass("car_glass", tint=(0.78,0.88,0.95))
    M["car_tire"]   = _pbr("car_tire",  (0.03,0.03,0.03), rough=0.90)
    M["car_chrome"] = _pbr("car_chrome",(0.82,0.82,0.82), rough=0.12, metal=0.95)
    M["car_light"]  = _pbr("car_light", (0.95,0.95,0.75), rough=0.05,
                             emit=(0.95,0.95,0.75), emit_str=3.0)
    M["tree_trunk"] = _pbr("tree_trunk",(0.35,0.22,0.10), rough=0.85)
    M["tree_leaf"]  = _noise_mat("tree_leaf",(0.12,0.32,0.06),(0.16,0.40,0.08), rough=0.80, scale=14)
    M["flower_pot"] = _pbr("flower_pot",(0.50,0.32,0.22), rough=0.72)
    M["flower_r"]   = _pbr("flower_r",  (0.88,0.18,0.12), rough=0.60,
                             emit=(0.88,0.18,0.12), emit_str=0.3)
    M["flower_y"]   = _pbr("flower_y",  (0.95,0.80,0.10), rough=0.55,
                             emit=(0.95,0.80,0.10), emit_str=0.2)
    M["flower_p"]   = _pbr("flower_p",  (0.65,0.20,0.78), rough=0.58,
                             emit=(0.65,0.20,0.78), emit_str=0.2)
    M["flower_w"]   = _pbr("flower_w",  (0.92,0.92,0.92), rough=0.50)
    M["flower_leaf"]= _pbr("flower_leaf",(0.10,0.30,0.05), rough=0.78)
    M["stripe_w"]   = _pbr("stripe_w",  (0.94,0.94,0.88), rough=0.65)
    M["stripe_y"]   = _pbr("stripe_y",  (0.88,0.72,0.10), rough=0.65)
    M["xwalk"]      = _pbr("xwalk",     (0.90,0.88,0.82), rough=0.72)

# ─── IMPORT HELPERS ───────────────────────────────────────────────────────────
def _prototype_instance(asset_key, blend_path, target_coll, raw_loader):
    prototype = _ASSET_PROTOTYPES.get(asset_key)
    if prototype is None:
        prototype = bpy.data.collections.new("C2W_MASTER_" + asset_key.replace(":", "_"))
        raw_objects = raw_loader(prototype)
        if not raw_objects:
            bpy.data.collections.remove(prototype)
            return []
        # Normalize the prototype once; placement transforms then live on the Empty.
        roots = [o for o in raw_objects if o.parent not in raw_objects]
        if roots:
            xs = [o.location.x for o in roots]; ys = [o.location.y for o in roots]
            zs = [o.location.z for o in roots]
            cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2; cz = min(zs)
            for root in roots:
                root.location.x -= cx; root.location.y -= cy; root.location.z -= cz
        for obj in raw_objects:
            obj["c2w_role"] = "master"; obj["c2w_asset_id"] = asset_key
        prototype["c2w_role"] = "master"; prototype["c2w_asset_id"] = asset_key
        _ASSET_PROTOTYPES[asset_key] = prototype
        path_key = str(Path(blend_path))
        _LIBRARY_LOADS[path_key] = _LIBRARY_LOADS.get(path_key, 0) + 1
    inst = bpy.data.objects.new(asset_key + ":instance", None)
    inst.instance_type = "COLLECTION"; inst.instance_collection = prototype
    target_coll.objects.link(inst)
    _tag_instance(inst, asset_key)
    return [inst]

def _import_coll_raw(blend_path, coll_name, target_coll, excl=()):
    """Append a collection from blend_path into target_coll, skipping excluded prefixes."""
    blend_path = Path(blend_path)
    if not blend_path.exists():
        print(f"[UA] MISSING: {blend_path}")
        return []
    with bpy.data.libraries.load(str(blend_path), link=False) as (src, dst):
        if coll_name not in src.collections:
            print(f"[UA] '{coll_name}' not found in {blend_path.name}")
            return []
        dst.collections = [coll_name]

    imported = dst.collections[0] if dst.collections else None
    if not imported:
        return []

    objs = []
    for obj in list(imported.all_objects):
        if any(obj.name.startswith(e) for e in excl if e):
            continue
        try: target_coll.objects.link(obj)
        except RuntimeError: pass
        objs.append(obj)
    return objs

def _import_coll(blend_path, coll_name, target_coll, excl=()):
    key = f"collection:{Path(blend_path).name}:{coll_name}:{','.join(excl)}"
    return _prototype_instance(
        key, blend_path, target_coll,
        lambda prototype: _import_coll_raw(blend_path, coll_name, prototype, excl),
    )

def _import_prefix_raw(blend_path, prefix, target_coll):
    """Append objects whose names start with prefix."""
    blend_path = Path(blend_path)
    if not blend_path.exists():
        print(f"[UA] MISSING: {blend_path}")
        return []
    with bpy.data.libraries.load(str(blend_path), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith(prefix)]

    objs = []
    for obj in dst.objects:
        if obj is None: continue
        try: target_coll.objects.link(obj)
        except RuntimeError: pass
        objs.append(obj)
    return objs

def _import_prefix(blend_path, prefix, target_coll):
    key = f"prefix:{Path(blend_path).name}:{prefix}"
    return _prototype_instance(
        key, blend_path, target_coll,
        lambda prototype: _import_prefix_raw(blend_path, prefix, prototype),
    )

def asset_stats():
    return {
        "prototype_collections": len(_ASSET_PROTOTYPES),
        "primitive_meshes": len(_PRIMITIVE_MESHES),
        "external_library_loads": dict(_LIBRARY_LOADS),
    }

def _place(objects, tx, ty, tz=0.0, yaw=0.0):
    """Translate objects so their bounding-box centre lands at (tx, ty, tz)."""
    if not objects: return
    xs = [o.location.x for o in objects]
    ys = [o.location.y for o in objects]
    zs = [o.location.z for o in objects]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    cz = min(zs)
    dx, dy, dz = tx - cx, ty - cy, tz - cz
    if yaw == 0.0:
        for o in objects:
            o.location.x += dx
            o.location.y += dy
            o.location.z += dz
    else:
        rot = Matrix.Rotation(yaw, 4, 'Z')
        for o in objects:
            rel = Vector((o.location.x - cx, o.location.y - cy, 0.0))
            nr  = rot @ rel
            o.location.x = tx + nr.x
            o.location.y = ty + nr.y
            o.location.z += dz
            o.rotation_euler.z += yaw

# ─── ASSET PLACEMENT WRAPPERS ─────────────────────────────────────────────────
# Traffic-light gantry + upright — translate only (road runs along Y in both source and scene)
# yaw corrections for crossroads: 0=N-arm, π=S-arm, +π/2=E-arm(W-approach), −π/2=W-arm(E-approach)
_TL_EXCL = ("ground:", "Sun", "Camera", "cam", "key_", "orbit_")

def place_trafficlight(at, C, yaw=0.0):
    objs = _import_coll(BLEND["trafficlight"], "v33_traffic_lights", C, excl=_TL_EXCL)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# Bus-stop shelter opens toward −Y in source → rotate −π/2 so it opens toward −X (road)
_BS_EXCL = ("tree:", "ground:", "gnd:", "context:", "Sun", "Camera", "cam", "focus")

def place_busstop(at, C, yaw=-math.pi/2, scale=1.0):
    objs = _import_coll(BLEND["busstop"], "v3_bus_shelter", C, excl=_BS_EXCL)
    if scale != 1.0:
        for o in objs:
            o.scale = (scale, scale, scale)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# Individual bench (classic slatted)
def place_bench_classic(at, C, yaw=0.0):
    objs = _import_prefix(BLEND["bench_bin"], "clbench:", C)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# Individual domed litter bin
def place_bin_domed(at, C, yaw=0.0):
    objs = _import_prefix(BLEND["bench_bin"], "bin_domed:", C)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# McDonald's-style freestanding kiosk — front at −Y in source → −X in scene
_KI_EXCL = ("gnd:", "ground:", "Sun", "Camera", "cam", "key_sun")

def place_kiosk5(at, C, yaw=-math.pi/2, scale=1.0):
    objs = _import_coll(BLEND["kiosk5"], "k3_mcd", C, excl=_KI_EXCL)
    if scale != 1.0:
        for o in objs:
            o.scale = (scale, scale, scale)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# Bicycle docking station (fleet + dock combined)
_BK_EXCL = ("plaza:", "lawn:", "Sun", "Camera", "cam", "hero_", "overview_", "gallery_")

def place_bicycle_station(at, C, yaw=0.0):
    fleet = _import_coll(BLEND["bicycle"], "bike_fleet", C, excl=_BK_EXCL + ("kiosk:",))
    dock  = _import_coll(BLEND["bicycle"], "bike_dock",  C, excl=_BK_EXCL)
    objs  = fleet + dock
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# K6 red telephone box
def place_phonebooth(at, C, yaw=0.0):
    objs = _import_prefix(BLEND["phonebooth"], "K6_", C)
    _place(objs, at[0], at[1], yaw=yaw)
    return objs

# LED street lamp — arm extends along +Y in source
#   Right-side lamps (X > 0) need yaw=+π/2 → arm points toward −X (over road)
#   Left-side lamps  (X < 0) need yaw=−π/2 → arm points toward +X (over road)
#   day=True: disable emission so lamps look off during daytime
def place_streetlight(at, C, yaw=math.pi/2, day=True):
    objs = _import_prefix(BLEND["streetlight"], "SL_", C)
    if day:
        for o in objs:
            for slot in o.material_slots:
                mat = slot.material
                if mat and mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == "BSDF_PRINCIPLED":
                            try:
                                node.inputs["Emission Strength"].default_value = 0.0
                            except (KeyError, TypeError):
                                pass
    _place(objs, at[0], at[1], yaw=yaw)
    return objs


# Reference-driven ATM family.  These collection names are the stable public
# output of scripts/generate_urban_v3_atm.py; the source generator also exposes
# build_atm(...) for pipelines that prefer direct procedural construction.
ATM_VARIANTS = (
    "silver_freestanding_2in1",
    "silver_through_wall_2in1",
    "white_oxford_through_wall",
    "bronze_deep_recess",
    "bank_branded_narrow",
)
_ATM_COLLECTIONS = (
    "urban_v3_atm4:ATM_01A_SILVER_FREESTANDING",
    "urban_v3_atm4:ATM_01B_SILVER_THROUGH_WALL",
    "urban_v3_atm4:ATM_02_WHITE_OXFORD_WALL",
    "urban_v3_atm4:ATM_03_BRONZE_DEEP_RECESS",
    "urban_v3_atm4:ATM_04_BANK_BRANDED_NARROW",
)


def _ground_collection_instance(instance, ground_z=0.0):
    """Place an instanced collection's evaluated source bounds on ``ground_z``.

    The generic prototype cache normalizes assets from root object origins,
    which is appropriate for simple parented props.  A dense procedural ATM
    collection has many unparented custom-profile meshes whose data-space
    origins do not coincide with their floor, so origin normalization alone can
    sink the cabinet by roughly half its height.  Use actual geometry bounds at
    the adapter boundary instead.
    """
    coll = getattr(instance, "instance_collection", None)
    if coll is None:
        return 0.0
    # Prototype transforms loaded from a library are cached until Blender's
    # dependency graph sees the newly linked collection instance.  Refresh
    # before measuring so bounds reflect the generic prototype normalization,
    # not stale source-file matrices.
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner)
              for obj in coll.all_objects if obj.type in {"MESH","CURVE","FONT"}
              for corner in obj.bound_box]
    if not points:
        return 0.0
    local_min_z = min(point.z for point in points)
    correction = ground_z - (instance.location.z + local_min_z * instance.scale.z)
    instance.location.z += correction
    instance["c2w_ground_correction_m"] = correction
    instance["c2w_ground_plane_z"] = ground_z
    return correction


def place_atm(at, C, variant=0, yaw=0.0, scale=1.0):
    """Instance one production ATM variant at ``at`` in an urban scene.

    ``variant`` may be an integer 0..4 or a canonical name in ATM_VARIANTS.
    Generated collections contain only the ATM asset; validation cameras,
    lights, and presentation ground are deliberately excluded.
    """
    if isinstance(variant, str):
        try:
            variant = ATM_VARIANTS.index(variant)
        except ValueError as exc:
            raise ValueError(f"Unknown ATM variant {variant!r}; expected one of {ATM_VARIANTS}") from exc
    if not isinstance(variant, int) or not 0 <= variant < len(_ATM_COLLECTIONS):
        raise ValueError("ATM variant must be an integer 0..4 or a canonical ATM_VARIANTS name")
    objs = _import_coll(BLEND["atm4"], _ATM_COLLECTIONS[variant], C)
    if scale != 1.0:
        for obj in objs:
            obj.scale = (scale, scale, scale)
    _place(objs, at[0], at[1], yaw=yaw)
    for obj in objs:
        _ground_collection_instance(obj, 0.0)
        obj["c2w_asset_id"] = "atm:" + ATM_VARIANTS[variant]
        obj["c2w_source_generator"] = "scripts/generate_urban_v3_atm.py"
    return objs


# ─── INFINIGEN VEHICLE (car / bus from urban_block vehicles.blend) ─────────────
# vehicle_key: 'car_eastbound' | 'car_westbound' | 'car_southbound' | 'bus_northbound'
# Source orientations: eastbound→+X, westbound→−X, southbound→−Y, northbound→+Y
# Use yaw_extra to rotate to desired travel direction.
def place_infinigen_car(tag, vehicle_key, at, C, yaw_extra=0.0):
    bp = BLEND.get("vehicles_inf")
    if not bp or not bp.exists():
        print(f"[UA] MISSING vehicles_inf blend"); return []
    suffix = f":{vehicle_key}"
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.endswith(suffix)]
    objs = []
    for o in dst.objects:
        if o is None: continue
        o.name = f"{tag}_{o.name}"
        try: C.objects.link(o)
        except RuntimeError: pass
        objs.append(o)
    if objs:
        _place(objs, at[0], at[1], yaw=yaw_extra)
    return objs


# ─── REAL INFINIGEN TREE (pre-generated, from urban_v3_trees/trees.blend) ──────
# tree_idx in [0..4]; each InfTree_N is a real TreeFactory tree ~9-10m tall.
def place_infinigen_tree(tag, at, C, tree_idx=0, scale=1.0):
    bp = BLEND.get("trees_inf")
    if not bp or not bp.exists():
        print(f"[UA] MISSING trees_inf blend (run generate_urban_v3_trees.py first)")
        return []
    prefix = f"InfTree_{tree_idx % 5}_"
    objs = _import_prefix(bp, prefix, C)
    if objs:
        objs[0].name = tag
        objs[0].scale = (scale, scale, scale)
        _place(objs, at[0], at[1])
    return objs

# ─── ROAD / SIDEWALK / GREEN BELT ─────────────────────────────────────────────
ROAD_X1, ROAD_X2  = -4.0,  4.0   # asphalt
SIDEW_W           = 3.0           # sidewalk width each side
GREEN_W           = 2.5           # green-belt width each side
ROAD_LEN          = 80.0          # total Y extent (±40)

def build_road(C):
    """Asphalt deck + white lane dash + yellow centre line + crosswalk."""
    # Asphalt slab
    _box("road_asphalt", 0, 0, -0.02, ROAD_X2-ROAD_X1, ROAD_LEN, 0.04, M["road"], C)
    # Yellow double centre line
    for dx in (-0.08, 0.08):
        _box(f"road_cl{dx:.0f}", dx, 0, 0.003, 0.06, ROAD_LEN, 0.004, M["stripe_y"], C)
    # White lane dashes (right lane, 3m gaps)
    for yi in range(-18, 19):
        y = yi * 4.0
        _box(f"road_dash_r{yi}", 2.0, y, 0.003, 0.12, 2.0, 0.004, M["stripe_w"], C)
        _box(f"road_dash_l{yi}",-2.0, y, 0.003, 0.12, 2.0, 0.004, M["stripe_w"], C)
    # Crosswalk at Y = −30
    for i in range(8):
        x0 = ROAD_X1 + 0.5 + i * (ROAD_X2-ROAD_X1-1.0) / 8
        _box(f"xwalk_{i}", x0, -30.0, 0.004, 0.8, 2.5, 0.005, M["xwalk"], C)
    # Stop line
    _box("road_stop", 0, -31.5, 0.004, ROAD_X2-ROAD_X1, 0.4, 0.005, M["stripe_w"], C)

def build_sidewalks(C):
    """Concrete sidewalk slabs both sides + raised kerb."""
    for sign, sfx in [(1, "r"), (-1, "l")]:
        sx = (ROAD_X2 if sign > 0 else ROAD_X1)
        cx = sx + sign * SIDEW_W / 2
        _box(f"sw_{sfx}", cx, 0, 0.06, SIDEW_W, ROAD_LEN, 0.12, M["sidewalk"], C)
        # Kerb strip
        kx = sx + sign * 0.08
        _box(f"kerb_{sfx}", kx, 0, 0.10, 0.16, ROAD_LEN, 0.20, M["curb"], C)

def build_green_belts(C):
    """Grass strips both sides."""
    for sign, sfx in [(1, "r"), (-1, "l")]:
        gx_inner = (ROAD_X2 if sign > 0 else ROAD_X1) + sign * SIDEW_W
        cx = gx_inner + sign * GREEN_W / 2
        _box(f"green_{sfx}", cx, 0, 0.0, GREEN_W, ROAD_LEN, 0.04, M["greenstrip"], C)

# ─── TREE ─────────────────────────────────────────────────────────────────────
def build_tree(tag, cx, cy, C, trunk_h=2.4, canopy_r=2.2):
    _cyl(f"tr_trunk_{tag}", cx, cy, 0.0, 0.12, trunk_h, M["tree_trunk"], C, verts=12)
    # Multi-layer canopy
    for i, (dz, r, scale) in enumerate([
            (0.0, canopy_r,       1.0),
            (0.7, canopy_r*0.80,  1.0),
            (1.3, canopy_r*0.58,  1.0)]):
        _sph(f"tr_canopy_{tag}_{i}", cx, cy, trunk_h + dz,
             r * scale, M["tree_leaf"], C, segs=14, rings=10)

# ─── FLOWER BED ───────────────────────────────────────────────────────────────
import random as _rng

def build_flowerbed(tag, cx, cy, C, w=1.8, d=0.8, n_flowers=22, seed=0):
    """Raised planter with soil and scattered flowers."""
    _rng.seed(seed)
    _box(f"fb_planter_{tag}", cx, cy, 0.15, w, d, 0.30, M["flower_pot"], C, bev=0.02)
    _box(f"fb_soil_{tag}",    cx, cy, 0.32, w-0.06, d-0.06, 0.06, M["soil"], C)
    colors = [M["flower_r"], M["flower_y"], M["flower_p"], M["flower_w"]]
    for k in range(n_flowers):
        fx = cx + _rng.uniform(-w/2+0.08, w/2-0.08)
        fy = cy + _rng.uniform(-d/2+0.06, d/2-0.06)
        fh = _rng.uniform(0.18, 0.32)
        _cyl(f"fb_stem_{tag}_{k}", fx, fy, 0.33, 0.008, fh, M["flower_leaf"], C, verts=6)
        _sph(f"fb_bloom_{tag}_{k}", fx, fy, 0.33+fh,
             _rng.uniform(0.04, 0.07), _rng.choice(colors), C, segs=8, rings=6)

# ─── PROCEDURAL SEDAN CAR ─────────────────────────────────────────────────────
def build_car(tag, cx, cy, C, yaw=0.0, mat_body=None, mat_body2=None):
    """Low-poly sedan. yaw=0 → faces +Y (travelling north)."""
    mb  = mat_body  if mat_body  else M["car_paint"]
    mb2 = mat_body2 if mat_body2 else mb

    # --- build at origin, rotate, then translate ---
    L, W, H = 4.40, 1.82, 0.90   # body box
    CH = 0.72                      # cabin height above body
    WR = 0.32                      # wheel radius

    parts = []

    def bx(name, lx, ly, lz, dx, dy, dz, mat, bv=0.0):
        o = _box(name, lx, ly, lz, dx, dy, dz, mat, C, bev=bv)
        parts.append(o); return o

    def cy_(name, lx, ly, lz, r, h, mat, rx=0.0):
        o = _cyl(name, lx, ly, lz, r, h, mat, C, verts=32, rx=rx)
        parts.append(o); return o

    # main body
    bx(f"c_{tag}_body",   0,  0,  H/2,        L,     W,    H,    mb,  bv=0.06)
    # cabin top (shifted 0.4m rearward = −y since car faces +y)
    bx(f"c_{tag}_cab",    0, -0.3, H+CH/2,    L*0.52, W*0.92, CH, mb,  bv=0.06)
    # windshield
    bx(f"c_{tag}_wshld",  0,  L*0.52/2-0.15, H+CH*0.42, 0.06, W*0.84, CH*0.66, M["car_glass"])
    # rear window
    bx(f"c_{tag}_rwin",   0, -L*0.52/2-0.3+0.15, H+CH*0.42, 0.06, W*0.84, CH*0.60, M["car_glass"])
    # side windows
    for sx, sfx in [(-W/2, "l"), (W/2, "r")]:
        bx(f"c_{tag}_sw_{sfx}", 0, -0.3, H+CH*0.44, L*0.38, 0.05, CH*0.62, M["car_glass"])
    # front/rear bumpers
    bx(f"c_{tag}_fbumper",  0,  L/2+0.04, H*0.35, L*0.02+0.08, W*0.90, H*0.38, M["car_chrome"], bv=0.03)
    bx(f"c_{tag}_rbumper",  0, -L/2-0.04, H*0.35, L*0.02+0.08, W*0.90, H*0.38, M["car_chrome"], bv=0.03)
    # headlights
    for sx in [-0.52, 0.52]:
        bx(f"c_{tag}_hl_{sx:.0f}", sx, L/2+0.01, H*0.62, 0.04, 0.36, 0.16, M["car_light"])
    # tail lights
    for sx in [-0.50, 0.50]:
        bx(f"c_{tag}_tl_{sx:.0f}", sx, -L/2-0.01, H*0.58, 0.04, 0.28, 0.18,
           _pbr(f"c_{tag}_tlm", (0.85, 0.05, 0.05), rough=0.05,
                emit=(0.85, 0.05, 0.05), emit_str=1.5))
    # 4 wheels
    for wy, wsfx in [( W/2+0.06, "ol"), (-W/2-0.06, "or")]:
        for wx, wsfx2 in [(1.22, "f"), (-1.22, "r")]:
            cy_(f"c_{tag}_tire_{wsfx}_{wsfx2}", wx, wy, WR, WR,   0.22, M["car_tire"], rx=math.pi/2)
            cy_(f"c_{tag}_rim_{wsfx}_{wsfx2}",  wx, wy, WR, WR*0.72, 0.18, M["car_chrome"], rx=math.pi/2)

    # rotate then translate
    if yaw != 0.0:
        rot = Matrix.Rotation(yaw, 4, 'Z')
        for o in parts:
            o.location = rot @ Vector(o.location)
            o.rotation_euler.z += yaw
    for o in parts:
        o.location.x += cx
        o.location.y += cy

    return parts

# ─── PROCEDURAL SINGLE-STORY HOUSE (single-story house) ─────────────────────────────────────
def build_house(tag, cx, cy, C,
                w=12.0, d=8.0, wall_h=3.4, yaw=0.0,
                mat_wall=None, mat_roof=None, n_win_front=3):
    """Chinese single-story house with flat roof and parapet."""
    mw = mat_wall if mat_wall else M["wall"]
    mr = mat_roof if mat_roof else M["roof_flat"]
    parts = []

    def bx(name, lx, ly, lz, dx, dy, dz, mat, bv=0.0):
        o = _box(name, lx, ly, lz, dx, dy, dz, mat, C, bev=bv)
        parts.append(o); return o

    # Main wall body
    bx(f"h_{tag}_body",    0, 0, wall_h/2,       w,      d,      wall_h,    mw, bv=0.01)
    # Flat roof slab (overhangs 0.25m each side)
    bx(f"h_{tag}_roof",    0, 0, wall_h+0.15,    w+0.5,  d+0.5,  0.30,      mr)
    # Parapet (front and rear, side)
    for py, sfx in [( d/2+0.25, "r"), (-d/2-0.25, "f")]:
        bx(f"h_{tag}_par_{sfx}", 0, py, wall_h+0.55, w+0.5, 0.20, 0.60, mw, bv=0.01)
    for px, sfx in [( w/2+0.25, "s1"), (-w/2-0.25, "s2")]:
        bx(f"h_{tag}_par_{sfx}", px, 0, wall_h+0.55, 0.20, d+0.90, 0.60, mw, bv=0.01)

    # Front windows (evenly spaced along front face)
    ww, wh = 1.20, 1.10
    spacing = w / (n_win_front + 1)
    for i in range(n_win_front):
        wx = -w/2 + spacing * (i + 1)
        bx(f"h_{tag}_win_f{i}", wx, -d/2, wall_h*0.55, ww, 0.08, wh, M["window"])
        # window frame
        bx(f"h_{tag}_wfr_f{i}", wx, -d/2-0.01, wall_h*0.55, ww+0.08, 0.06, wh+0.08, mw, bv=0.01)

    # Side windows (2 on each side)
    for si in range(2):
        wy = -d/4 + si * d/2
        for sx, sfx in [( w/2, "r"), (-w/2, "l")]:
            bx(f"h_{tag}_win_s{si}_{sfx}", sx, wy, wall_h*0.55, 0.08, 0.90, wh, M["window"])

    # Door (centred on front face)
    dw, dh = 1.0, 2.4
    bx(f"h_{tag}_door", 0.0, -d/2, dh/2, dw, 0.08, dh, M["door"])
    bx(f"h_{tag}_door_fr", 0.0, -d/2-0.01, dh/2, dw+0.10, 0.06, dh+0.10, mw, bv=0.01)

    # Front boundary wall / fence
    bx(f"h_{tag}_fence", 0, -d/2-1.8, 0.9, w+1.0, 0.18, 1.8, M["fence"], bv=0.01)

    # Rotate then translate
    if yaw != 0.0:
        rot = Matrix.Rotation(yaw, 4, 'Z')
        for o in parts:
            o.location = rot @ Vector(o.location)
            o.rotation_euler.z += yaw
    for o in parts:
        o.location.x += cx
        o.location.y += cy

    return parts

# ─── REAL ASSET: BELT2 SHRUBS ─────────────────────────────────────────────────
# belt2.blend has Shrub_0..4_bark (parent) + Shrub_0..4_leaf (child).
# Each shrub is ~1.0-1.3m tall at scale=1.0; scale=2.5 gives street-tree height.
_SHRUB_SRC_X = (1.5, 4.5, 7.5, 10.5, 13.5)  # source world-X for each shrub index

def place_shrub_belt2(tag, at, C, scale=1.0, shrub_idx=0, yaw=0.0):
    """Import a shrub pair (bark+leaf) from belt2.blend and place at (at[0], at[1], 0)."""
    bp = BLEND["belt2"]
    if not bp.exists():
        print(f"[UA] MISSING: {bp}")
        return []
    si   = shrub_idx % 5
    bark_src = f"Shrub_{si}_bark"
    leaf_src = f"Shrub_{si}_leaf"
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        avail = [n for n in src.objects if n in (bark_src, leaf_src)]
        dst.objects = avail

    bark_obj = None
    objs = []
    for o in dst.objects:
        if o is None:
            continue
        # rename before linking to avoid future-conflict confusion
        o.name = f"{tag}_{o.name}"
        try:
            C.objects.link(o)
        except RuntimeError:
            pass
        objs.append(o)
        if "bark" in o.name:
            bark_obj = o

    if bark_obj:
        # Move bark to target; leaf follows via parent link
        bark_obj.location.x = at[0]
        bark_obj.location.y = at[1]
        bark_obj.location.z = 0.0
        if scale != 1.0:
            bark_obj.scale = (scale, scale, scale)
        if yaw != 0.0:
            bark_obj.rotation_euler.z = yaw
    else:
        print(f"[UA] WARNING: bark not found for shrub {tag} (idx={si})")
    return objs


# ─── REAL ASSET: FIAT DUCATO VEHICLE ──────────────────────────────────────────
# Van front faces +X in source. Yaw corrections:
#   +π/2 → travels north (+Y)    −π/2 → travels south (−Y)
#   0    → travels east  (+X)    π    → travels west  (−X)
_VEHICLE_EXCL = {"CameraTarget", "KeyLight", "OrbitCamera"}

def place_vehicle(tag, at, C, yaw=0.0):
    """Import Fiat Ducato from openx_preview.blend and place at (at[0], at[1], 0)."""
    bp = BLEND["vehicle"]
    if not bp.exists():
        print(f"[UA] MISSING: {bp}")
        return []
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n not in _VEHICLE_EXCL]

    root = None
    objs = []
    for o in dst.objects:
        if o is None:
            continue
        try:
            C.objects.link(o)
        except RuntimeError:
            pass
        objs.append(o)
        if o.name == "Grp_Root" and o.parent is None:
            root = o

    # Rename after identifying root (renaming does not break parent links)
    for o in objs:
        o.name = f"{tag}_{o.name}"

    if root is None:
        # Fallback: find parent-less empty
        for o in objs:
            if o.parent is None and o.type == "EMPTY":
                root = o
                break

    if root:
        root.location.x = at[0]
        root.location.y = at[1]
        root.location.z = 0.0
        root.rotation_euler.z = yaw
    else:
        print(f"[UA] WARNING: Grp_Root not found for vehicle {tag}")
    return objs


# ─── LIGHTING ─────────────────────────────────────────────────────────────────
def build_world_lighting():
    """Nishita sky + Light-Path split (no blown reflections) + warm sun."""
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)

    out   = nt.nodes.new("ShaderNodeOutputWorld")
    mix   = nt.nodes.new("ShaderNodeMixShader")
    sky_b = nt.nodes.new("ShaderNodeBackground")   # for camera rays (full strength)
    sky_l = nt.nodes.new("ShaderNodeBackground")   # for light rays (dimmed)
    nish  = nt.nodes.new("ShaderNodeTexSky")
    lpath = nt.nodes.new("ShaderNodeLightPath")

    nish.sky_type          = "NISHITA"
    nish.sun_elevation     = math.radians(38)
    nish.sun_rotation      = math.radians(215)
    nish.air_density       = 1.0
    nish.dust_density      = 0.3
    sky_b.inputs["Strength"].default_value = 1.0
    sky_l.inputs["Strength"].default_value = 0.26

    nt.links.new(nish.outputs["Color"],   sky_b.inputs["Color"])
    nt.links.new(nish.outputs["Color"],   sky_l.inputs["Color"])
    nt.links.new(sky_l.outputs["Background"], mix.inputs[1])
    nt.links.new(sky_b.outputs["Background"], mix.inputs[2])
    nt.links.new(lpath.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Shader"],   out.inputs["Surface"])

    # Sun lamp
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.active_object
    sun.name = "Sun"
    sun.data.energy = 3.8
    sun.data.angle  = math.radians(0.5)
    sun.rotation_euler = (math.radians(52), 0.0, math.radians(215))

    # Soft fill
    bpy.ops.object.light_add(type="AREA", location=(0, -15, 18))
    fill = bpy.context.active_object
    fill.name = "Fill"
    fill.data.energy = 140
    fill.data.size    = 12
    fill.rotation_euler = (math.radians(55), 0, 0)
