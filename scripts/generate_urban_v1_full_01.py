"""Generate the complete four-zone urban scene from source-level generators.

This entry deliberately never opens any urban_v3_all*.blend.  The all41 script
is executed as Python to recreate the road/park/residential backbone in a clean
file; commercial and recreation are then rebuilt by their latest asset
generators in the parcels defined by that backbone.
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
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]


import json
import math
import os
import runpy
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
REVISION = os.environ.get("C2W_FULL_REVISION", "urban_v1_full_01")
OUTPUT_REVISION = os.environ.get("C2W_OUTPUT_REVISION", REVISION)
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / OUTPUT_REVISION
VARIANT = os.environ.get("C2W_URBAN_VARIANT", "baseline")
SEED = int(os.environ.get("C2W_URBAN_SEED", "1001"))
STRICT_FULL03 = REVISION in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_05",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
    "urban_v1_full_09",
)
FULL06_LANDSCAPE = REVISION in (
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
    "urban_v1_full_09",
)
# full08 deliberately inherits every validated full07 requirement.  Dedicated
# FULL08 branches below add only the requested commercial and road corrections.
FULL07 = REVISION in ("urban_v1_full_07", "urban_v1_full_08", "urban_v1_full_09")
FULL09 = REVISION == "urban_v1_full_09"
# FULL09 inherits the audited zebra-crossing and centre-line corrections from
# FULL08, then pins the upgraded commercial and leisure regions to ALL43-24
# and ALL44-13 respectively before adding the third residential district.
FULL08 = REVISION in ("urban_v1_full_08", "urban_v1_full_09")
ADD_RIVER = FULL07 and os.environ.get("C2W_ADD_RIVER") == "1"
PARAMETRIC_PRODUCTION = REVISION.startswith("urban_v2_full_")

# These profiles are consumed by the real regional generators below.  Only
# layout and density vary; all profiles retain the verified high-detail asset
# families used by urban_v1_full_02.
VARIANT_PROFILES = {
    "baseline": {
        "park_tree_cap": 11,
        "park_shrub_probability": 0.34,
        "residential_apartment_floors": 5,
        "commercial_pattern": "standard",
        "leisure_court": "basketball",
        "leisure_play_modules": 3,
    },
    "demo1": {
        "park_tree_cap": 11,
        "park_shrub_probability": 0.34,
        "residential_apartment_floors": 5,
        "commercial_pattern": "open_forecourt",
        "leisure_court": "basketball",
        "leisure_play_modules": 3,
        "layout": "linear_street",
        "building_organization": "compact_linear_main_street_with_infill_blocks",
        "active_road_arms": ["north", "south"],
        "released_land_program": "west_mixed_use_infill_and_east_park_promenade",
    },
    "demo2": {
        "park_tree_cap": 18,
        "park_shrub_probability": 0.68,
        "residential_apartment_floors": 8,
        "commercial_pattern": "dense_mixed_use",
        "leisure_court": "multi_use",
        "leisure_play_modules": 4,
        "layout": "t_junction",
        "building_organization": "t_junction_terminal_building_civic_cluster",
        "active_road_arms": ["east", "south", "west"],
        "released_land_program": "north_terminal_retail_apartment_and_courtyard",
    },
}
if VARIANT not in VARIANT_PROFILES:
    raise ValueError(
        f"Unsupported C2W_URBAN_VARIANT={VARIANT!r}; "
        f"expected one of {sorted(VARIANT_PROFILES)}"
    )
PROFILE = VARIANT_PROFILES[VARIANT]

sys.path.insert(0, str(ROOT / "scripts"))


def log(section: str, message: str) -> None:
    line = f"[{section}] {message}"
    print(line, flush=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def remove_collection_contents(name: str) -> int:
    coll = bpy.data.collections.get(name)
    if coll is None:
        return 0
    objects = list(coll.all_objects)
    if objects:
        bpy.data.batch_remove(objects)
    return len(objects)


def import_all43_18_commercial() -> dict:
    """Append the exact final all43-18 commercial asset system into this scene.

    The reference is treated like the existing house/vehicle asset libraries:
    only visible commercial world objects are linked into the freshly generated
    city.  Roads, cameras and lights from the reference scene are excluded.
    """
    source = (
        ROOT
        / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_18/urban_v3_all43_18.blend"
    )
    if not source.exists():
        raise FileNotFoundError(
            f"Required all43-18 commercial reference missing: {source}"
        )
    with bpy.data.libraries.load(str(source), link=False) as (src, dst):
        if not src.scenes:
            raise RuntimeError(f"No scene datablock in commercial reference: {source}")
        dst.scenes = [src.scenes[0]]
    reference_scene = dst.scenes[0]
    commercial = bpy.data.collections.new("Full03_All43_18_Commercial")
    bpy.context.scene.collection.children.link(commercial)

    xmin, xmax, ymin, ymax = -50.5, -9.5, -46.0, -7.0
    selected = []
    for obj in reference_scene.objects:
        # A freshly appended Scene has no evaluated view layer in the current
        # window, so use the stored object transform.  All world-level all43-18
        # commercial objects are unparented by construction.
        p = obj.location
        if (
            obj.type not in {"CAMERA", "LIGHT"}
            and obj.name.startswith("all43_")
            and not obj.hide_render
            and xmin <= p.x <= xmax
            and ymin <= p.y <= ymax
        ):
            commercial.objects.link(obj)
            obj["c2w_reference_asset"] = "urban_v3_all43_18"
            selected.append(obj)
    bpy.data.scenes.remove(reference_scene)

    required_masters = (
        "STOREFRONT_FRAME_MASTER",
        "STOREFRONT_DOOR_MASTER",
        "STOREFRONT_WINDOW_MASTER",
        "SIGN_BAND_MASTER",
        "CHANNEL_LETTER_MASTER",
        "CANOPY_MASTER",
        "GROCERY_SHELF_MASTER",
        "GROCERY_FRIDGE_MASTER",
        "CHECKOUT_MASTER",
        "DINING_TABLE_MASTER",
        "DINING_CHAIR_MASTER",
        "RESTAURANT_COUNTER_MASTER",
        "KITCHEN_PREP_MASTER",
        "REFINED_COMMERCIAL_PLANTER_MASTER",
        "OUTDOOR_CAFE_SET_MASTER",
        "COMPLEX_REAR_FLOWERBED_MASTER",
        "SHAREDBICYCLE4_STATION_MASTER",
    )
    missing = [
        name for name in required_masters if bpy.data.collections.get(name) is None
    ]
    if missing:
        # Blender's Scene append omits an indirectly referenced collection when
        # its only users are nested collection instances.  Pull every required
        # final master explicitly so the integrated asset graph is identical to
        # the all43-18 source and remains self-contained after saving.
        with bpy.data.libraries.load(str(source), link=False) as (src, dst):
            absent_from_source = [
                name for name in missing if name not in src.collections
            ]
            if absent_from_source:
                raise RuntimeError(
                    f"Commercial masters absent from all43-18 source: {absent_from_source}"
                )
            dst.collections = missing
        missing = [
            name for name in required_masters if bpy.data.collections.get(name) is None
        ]
    shops = {
        name: bpy.data.objects.get(name)
        for name in ("all43_01:convenience_store", "all43_01:restaurant")
    }
    bad_shops = [
        name
        for name, obj in shops.items()
        if obj is None or obj.instance_type != "COLLECTION"
    ]
    visible_rebuild_parts = {
        name: sum(
            obj.name.startswith("all43_15:") and not obj.hide_render
            for obj in shops[name].instance_collection.objects
        )
        for name in shops
        if shops[name] is not None
    }
    if (
        missing
        or bad_shops
        or len(selected) < 100
        or min(visible_rebuild_parts.values(), default=0) < 150
    ):
        raise RuntimeError(
            {
                "commercial_reference_import_failed": True,
                "missing_masters": missing,
                "bad_shop_instances": bad_shops,
                "selected_world_objects": len(selected),
                "visible_rebuild_parts": visible_rebuild_parts,
            }
        )
    log(
        "Commercial",
        f"Imported exact all43-18 asset system ({len(selected)} visible world objects)",
    )
    return {
        "pipeline_strategy": "exact urban_v3_all43_18 final asset-system import",
        "reference_blend": str(source),
        "reference_blend_bytes": source.stat().st_size,
        "visible_world_objects": len(selected),
        "shop_instances": list(shops),
        "visible_all43_15_rebuild_parts": visible_rebuild_parts,
        "required_master_assets": list(required_masters),
        "missing_master_assets": missing,
        "reference_revision": "urban_v3_all43_18",
    }


def build_backbone() -> None:
    log(
        "Urban Layout",
        f"Generating clean four-parcel layout (seed={SEED}, variant={VARIANT})",
    )
    # all41 itself starts with UA.reset_scene and calls all30 as Python source.
    # Its .blend dependencies are reusable Indoor/vehicle/sculpture assets, not
    # any of the four regional final scenes prohibited by the task.
    if (
        REVISION
        in (
            "urban_v1_full_02",
            "urban_v1_full_03",
            "urban_v1_full_04",
            "urban_v1_full_05",
            "urban_v1_full_06",
            "urban_v1_full_07",
            "urban_v1_full_08",
            "urban_v1_full_09",
        )
        or PARAMETRIC_PRODUCTION
    ):
        os.environ["C2W_FULL_02"] = "1"
        os.environ["C2W_FORBID_TOY_MODELS"] = "1"
        if FULL07:
            # full07 creates a genuinely diverse palette in this run.  It does
            # not append a prior scene or cached vegetation blend.
            os.environ.pop("C2W_USE_TREE_MASTER_LIBRARY", None)
            os.environ.pop("C2W_TREE_LIBRARY_PROFILE", None)
            os.environ["C2W_REAL_TREE_MASTER_INSTANCES"] = "1"
            os.environ["C2W_TREE_PALETTE_SIZE"] = "5"
            os.environ["C2W_FLOWERBED_LANDSCAPE"] = "1"
        elif STRICT_FULL03:
            # Use the exact explicit-leaf vegetation prototypes validated by
            # urban_v3_all39_fast5/park.png; never regenerate the broken naked
            # TreeFactory bark blobs from full_02.
            os.environ["C2W_USE_TREE_MASTER_LIBRARY"] = "1"
            os.environ["C2W_TREE_LIBRARY_PROFILE"] = "all39_fast5"
            os.environ["C2W_FLOWERBED_LANDSCAPE"] = "1"
        elif PARAMETRIC_PRODUCTION:
            # Use the exact explicit-leaf trees already validated in the
            # all39_fast5 park render.  These are reusable source assets, not
            # a prior final urban scene, and avoid the pathological solid
            # crowns produced by several fresh TreeFactory seeds.
            os.environ["C2W_USE_TREE_MASTER_LIBRARY"] = "1"
            os.environ["C2W_TREE_LIBRARY_PROFILE"] = "all39_fast5"
            os.environ.pop("C2W_REAL_TREE_MASTER_INSTANCES", None)
            os.environ.pop("C2W_TREE_PALETTE_SIZE", None)
        else:
            os.environ.pop("C2W_USE_TREE_MASTER_LIBRARY", None)
    else:
        os.environ["C2W_USE_TREE_MASTER_LIBRARY"] = "1"
    # Feed topology directly into the source-level all30 road generator.
    # Existing revisions retain their verified crossroads unless a profile
    # explicitly requests a new layout.
    os.environ["C2W_URBAN_LAYOUT"] = PROFILE.get("layout", "crossroads")
    os.environ["C2W_SKIP_LEGACY_RENDERS"] = "1"
    os.environ["C2W_SKIP_INTERMEDIATE_SAVES"] = "1"
    runpy.run_path(
        str(ROOT / "scripts/generate_urban_v3_all41.py"), run_name="__full_backbone__"
    )
    generated_layout = bpy.context.scene.get("c2w_layout_mode")
    if generated_layout != PROFILE.get("layout", "crossroads"):
        raise RuntimeError(
            f"Source road generator ignored requested topology: "
            f"requested={PROFILE.get('layout')}, generated={generated_layout}"
        )
    log("Urban Layout", "Global layout generated")
    log("Urban Layout", "Road network generated")
    log("Urban Layout", f"Topology generated: {PROFILE.get('layout', 'crossroads')}")


def build_commercial() -> dict:
    removed = remove_collection_contents("Commercial")
    if STRICT_FULL03 and not FULL07:
        stats = {"removed_placeholder_objects": removed}
        stats.update(import_all43_18_commercial())
        log("Commercial", "Region boundary: x[-50.5,-9.5], y[-46,-7]")
        log("Commercial", "Generation success (exact all43-18 asset system)")
        return stats
    import generate_urban_v3_all43_01 as base
    import refine_urban_v3_all43_02 as realism
    import commercial_rebuild_generator_15 as rebuild
    import commercial_visibility_planter_generator_16 as visibility
    import commercial_detail_generator_17 as detail
    import commercial_corner_711_generator_19 as corner711
    import commercial_mcdonalds_layout_generator_20 as commercial20

    # all43_15 dimensions are authored against the exact half-unit shared
    # meshes created by all43_10/all43_11.  Calling those source factories is
    # essential: Blender's default size=2 cube doubles the entire mall shell.
    import commercial_asset_refinement_generator_10 as asset10
    import commercial_daylight_goods_generator_11_light as daylight11

    asset10.cube_mesh()
    asset10.cylinder_mesh()
    daylight11.sphere_mesh()
    root, registry = base.build_scene(OUT)
    stats = {
        "removed_placeholder_objects": removed,
        "base_instances": len(registry.instances),
    }
    if REVISION == "urban_v1_full_02" or FULL07 or PARAMETRIC_PRODUCTION:
        # Reuse the same procedural realism stage as all43_18: detailed store
        # masters, real OpenX vehicles, and no base generator toy assets.
        realism.add_facade_detail(
            bpy.data.collections["all43_01:MASTER:convenience_store"], False
        )
        realism.add_facade_detail(
            bpy.data.collections["all43_01:MASTER:restaurant"], True
        )
        realism.add_ground_realism(root)
        removed_toys = []
        for name in (
            "all43_01:car_red",
            "all43_01:car_blue",
            "all43_01:car_van",
            "all43_01:car_silver_variant",
            "all43_01:tree_0",
            "all43_01:tree_1",
            "all43_01:tree_2",
            "all43_01:tree_3",
        ):
            obj = bpy.data.objects.get(name)
            if obj:
                removed_toys.append(name)
                bpy.data.objects.remove(obj, do_unlink=True)
        vehicle_specs = (
            [
                (
                    "audi_tt",
                    "m1_audi_tt_2014_roadster",
                    (-28.7, -32.8, 0.18),
                    1.5707963268,
                ),
                (
                    "tucson",
                    "m1_hyundai_tucson_2015",
                    (-22.1, -32.8, 0.18),
                    1.5707963268,
                ),
                ("ducato", "n1_fiat_ducato_2014", (-15.5, -40.3, 0.18), -1.5707963268),
                ("audi_q7", "m1_audi_q7_2015", (-25.4, -40.3, 0.18), -1.5707963268),
            ]
            if VARIANT == "demo2"
            else [
                (
                    "audi_tt",
                    "m1_audi_tt_2014_roadster",
                    (-29, -32.8, 0.18),
                    1.5707963268,
                ),
                (
                    "tucson",
                    "m1_hyundai_tucson_2015",
                    (-22.4, -32.8, 0.18),
                    1.5707963268,
                ),
                ("ducato", "n1_fiat_ducato_2014", (-15.8, -40.3, 0.18), -1.5707963268),
                ("audi_q7", "m1_audi_q7_2015", (-25.7, -40.3, 0.18), -1.5707963268),
            ]
        )
        counts = {}
        for key, folder, loc, rot in vehicle_specs:
            path = (
                Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")
                / folder
                / (folder + ".blend")
            )
            master, count = realism.openx_master(key, path)
            counts[key] = count
            realism.instance_collection(master, "vehicle:" + key, loc, rot, root)
        stats.update(
            {
                "removed_toy_assets": removed_toys,
                "openx_vehicle_source_objects": counts,
                "openx_vehicle_instances": len(vehicle_specs),
            }
        )
    if FULL08:
        # Reproduce the parking/vehicle stage that is still visible in the
        # all43_18 result.  Later all43_15 hides and fully rebuilds both shop
        # masters, while these root-level stall markings and wheel stops remain.
        import refine_urban_v3_all43_03 as commercial03
        import commercial_cleanup_generator_13 as commercial13

        removed_roof = commercial03.remove_rooftop_equipment()
        removed_parking, vehicle_positions, clearance = commercial03.rebuild_parking(
            root
        )
        final_frontage = commercial13.frontage(commercial13.materials())
        stats.update(
            {
                "all43_03_removed_rooftop_equipment": removed_roof,
                "all43_03_removed_parking_objects": removed_parking,
                "all43_03_vehicle_positions": vehicle_positions,
                "all43_03_storefront_clearance_m": clearance,
                "all43_13_final_frontage_collection": final_frontage.name,
                "all43_13_restrained_parking_stripes": sum(
                    o.name.startswith("all43_13:restrained_parking_stripe")
                    and not o.hide_render
                    for o in final_frontage.all_objects
                ),
            }
        )
    stats.update({f"rebuild_{k}": v for k, v in rebuild.run().items()})
    stats.update({f"visibility_{k}": v for k, v in visibility.run().items()})
    try:
        stats.update({f"detail_{k}": v for k, v in detail.run().items()})
    except ValueError as exc:
        # all43_17's parking audit expects stripe objects inherited from its old
        # refinement blend.  In the clean rebuild all43_15 intentionally hides
        # those legacy stripes.  The detailed planters, rear assets, bicycles,
        # and grounded products are already generated before this audit gate.
        stats["detail_clean_scene_audit_note"] = str(exc)
        log("Commercial", "Legacy stripe audit skipped; clean parking layout retained")
    # The production all43-19 stage adds the full-scale street-corner 7-Eleven
    # from source.  This is deliberately part of the same clean reconstruction
    # path rather than an edit baked only into a demonstration blend.
    stats.update({f"corner711_{k}": v for k, v in corner711.run().items()})
    # The active production pass forms a connected L-shaped commercial block,
    # relocates all existing stores, adds the road-facing McDonald's, and fills
    # its verified west-side vacancy with the party-wall LEMON COFFEE shop and
    # the two all43-25 reference bars.  It operates after all43-19 so every
    # addition is regenerated from source in the complete pipeline rather than
    # appended from a demo Blend.
    commercial_target = "urban_v3_all43_24" if FULL09 else "urban_v3_all43_25"
    stats.update(
        {
            f"commercial20_{k}": v
            for k, v in commercial20.run(target_revision=commercial_target).items()
        }
    )
    cube = bpy.data.meshes.get("all43_10:shared_cube")
    cylinder = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    stats["all43_shared_mesh_signature"] = {
        "cube_coordinate_min": min((min(v.co) for v in cube.vertices), default=None)
        if cube
        else None,
        "cube_coordinate_max": max((max(v.co) for v in cube.vertices), default=None)
        if cube
        else None,
        "cube_vertices": len(cube.vertices) if cube else 0,
        "cylinder_z_min": min((v.co.z for v in cylinder.vertices), default=None)
        if cylinder
        else None,
        "cylinder_z_max": max((v.co.z for v in cylinder.vertices), default=None)
        if cylinder
        else None,
        "cylinder_vertices": len(cylinder.vertices) if cylinder else 0,
    }
    if FULL09:
        stats.update(
            {
                "pipeline_strategy": "source-level all43 reconstruction with all43_18 base, all43_19 7-Eleven and active all43_24 lengthened-McDonald's/protected-sign/road-facing-chair/collision-audited-botanical-cafe pass",
                "reference_blend": None,
                "reference_revision": "urban_v3_all43_24",
                "source_modules": [
                    "generate_urban_v3_all43_01.py",
                    "refine_urban_v3_all43_02.py",
                    "refine_urban_v3_all43_03.py",
                    "commercial_asset_refinement_generator_10.py",
                    "commercial_daylight_goods_generator_11_light.py",
                    "commercial_cleanup_generator_13.py: final active frontage and restrained parking",
                    "commercial_rebuild_generator_15.py",
                    "commercial_visibility_planter_generator_16.py",
                    "commercial_detail_generator_17.py",
                    "commercial_corner_711_generator_19.py",
                    "commercial_mcdonalds_layout_generator_20.py(target_revision=urban_v3_all43_24)",
                ],
                "reference_blends_loaded": [],
            }
        )
    elif FULL08:
        stats.update(
            {
                "pipeline_strategy": "source-level all43 reconstruction with all43_18 base, all43_19 corner 7-Eleven and active all43_25 connected McDonald's/cafe/two-reference-bar inverse-L pass",
                "reference_blend": None,
                "reference_revision": "urban_v3_all43_18",
                "source_modules": [
                    "generate_urban_v3_all43_01.py",
                    "refine_urban_v3_all43_02.py",
                    "refine_urban_v3_all43_03.py",
                    "commercial_asset_refinement_generator_10.py",
                    "commercial_daylight_goods_generator_11_light.py",
                    "commercial_cleanup_generator_13.py: final active frontage and restrained parking",
                    "commercial_rebuild_generator_15.py",
                    "commercial_visibility_planter_generator_16.py",
                    "commercial_detail_generator_17.py",
                    "commercial_corner_711_generator_19.py",
                    "commercial_mcdonalds_layout_generator_20.py",
                    "commercial_reference_bars_generator_25.py",
                ],
                "reference_blends_loaded": [],
            }
        )
    elif FULL07:
        stats.update(
            {
                "pipeline_strategy": "source-level all43 procedural reconstruction plus all43_19/25 connected commercial additions",
                "reference_blend": None,
                "reference_revision": None,
                "source_modules": [
                    "generate_urban_v3_all43_01.py",
                    "refine_urban_v3_all43_02.py",
                    "commercial_rebuild_generator_15.py",
                    "commercial_visibility_planter_generator_16.py",
                    "commercial_detail_generator_17.py",
                    "commercial_corner_711_generator_19.py",
                    "commercial_mcdonalds_layout_generator_20.py",
                    "commercial_reference_bars_generator_25.py",
                ],
            }
        )
    log(
        "Commercial",
        "Region boundary: x[-54.25,-9.5], y[-44.5,-6.25]"
        if FULL09
        else "Region boundary: x[-58.45,-9.5], y[-44.5,-6.25]",
    )
    log("Commercial", "Generation success")
    return stats


def build_leisure() -> dict:
    removed = remove_collection_contents(
        "Commercial"
    )  # old southeast placeholder, if any
    # FULL09 reproduces the user's requested ALL44-13 north/south sports campus
    # through its production hook.  Other revisions keep their existing active
    # generator.  Neither path opens a completed leisure-region Blend.
    if FULL09:
        import generate_urban_v3_all44_13 as zone
    else:
        import generate_urban_v3_all44_14 as zone

    zone.remove_old_court_playground()
    zone.tune_retained_materials()
    mats = zone.create_shared_materials()
    if STRICT_FULL03 and not FULL06_LANDSCAPE:
        # Outside the actual park, green ground is a planted bed rather than a
        # colored turf sheet.  Real grass clumps and shrubs remain above this
        # dark cultivated-soil substrate.
        mats["turf"] = zone.base.mat(
            "MAT_FULL03_CULTIVATED_FLOWERBED_SOIL",
            (0.085, 0.038, 0.014),
            0.96,
            noise=0.28,
        )
    _library, assets = zone.base.prepare_court_playground_asset_library(mats)
    root = zone.base.collection("COURT_PLAYGROUND_REBUILD")
    if FULL07:
        # The activity parcel is intentionally grass-free.  A resin-bound,
        # mineral aggregate base provides a durable realistic substrate under
        # the court, playground and circulation construction.
        mats["leisure_aggregate"] = zone.base.mat(
            "MAT_FULL07_LEISURE_RESIN_BOUND_AGGREGATE",
            (0.29, 0.25, 0.20),
            0.94,
            noise=0.31,
        )
        ground_coll = zone.base.collection("FULL07_GRASS_FREE_LEISURE_GROUND", root)
        outline = [
            (10.0, -10.1),
            (47.3, -10.1),
            (47.9, -10.7),
            (47.9, -41.3),
            (47.25, -41.9),
            (10.2, -41.9),
            (9.65, -41.25),
            (9.65, -10.8),
        ]
        leisure_ground = zone.base.irregular_lawn(
            "grass_free_resin_bound_aggregate",
            outline,
            0.132,
            0.13,
            mats["leisure_aggregate"],
            ground_coll,
        )
        leisure_ground["c2w_leisure_ground"] = "grass_free_resin_bound_aggregate"
        grass = 0
    else:
        grass = zone.generate_real_turf(mats, assets, root)
    leisure_cfg = (
        {
            "court_length": 27,
            "court_width": 14,
            "play_module_count": 4,
            "bench_count": 3,
            "shade_count": 2,
            "court_type": "multi_use",
        }
        if VARIANT == "demo2"
        else {
            "court_length": 28,
            "court_width": 15,
            "play_module_count": 3,
            "bench_count": 2,
            "shade_count": 1,
            "court_type": "basketball",
        }
    )
    zone.base.generate_court(
        {
            "court_length": leisure_cfg["court_length"],
            "court_width": leisure_cfg["court_width"],
            "line_width": 0.075,
            "corner_radius": 0.35,
            "surface_thickness": 0.16,
            "border_width": 0.8,
            "fence_height": 3.4,
            "fence_post_spacing": 3,
            "court_type": leisure_cfg["court_type"],
            "hoop_count": 2,
            "gate_count": 1,
            "light_pole_count": 4,
        },
        mats,
        assets,
        root,
    )
    zone.generate_playground(
        {
            "playground_width": 10,
            "playground_length": 10,
            "safety_surface_type": "rubber_tile",
            "play_module_count": leisure_cfg["play_module_count"],
            "bench_count": leisure_cfg["bench_count"],
            "shade_count": leisure_cfg["shade_count"],
            "fence_type": "low",
            "age_group": "5-12",
            "path_connection_count": 2,
            "thickness": 0.14,
        },
        mats,
        assets,
        root,
    )
    zone.base.generate_ground_system(mats, assets, root)
    zone.base.populate_court_details(mats, assets, root)
    zone.populate_playground_details(mats, assets, root)
    zone.add_service_building_details(mats, root)
    leisure_shrubs = 0
    if STRICT_FULL03 and not FULL06_LANDSCAPE:
        shrub_masters = sorted(
            [
                c
                for c in bpy.data.collections
                if c.name.startswith("All39Fast5_ShrubPrototype_")
            ],
            key=lambda c: c.name,
        )
        if len(shrub_masters) < 5:
            raise RuntimeError(
                f"Verified belt-style shrub masters missing in leisure zone: {len(shrub_masters)}"
            )
        planted = bpy.data.collections.new("Full03_Leisure_Layered_Flowerbeds")
        root.children.link(planted)
        shrub_sites = (
            (11.6, -25.5, 0.68),
            (11.7, -30.5, 0.76),
            (11.6, -35.5, 0.70),
            (11.8, -39.2, 0.62),
            (23.7, -12.0, 0.64),
            (24.2, -15.7, 0.72),
            (24.0, -19.4, 0.66),
            (46.7, -12.4, 0.62),
            (46.8, -17.0, 0.68),
            (46.8, -39.5, 0.62),
        )
        for i, (x, y, scale) in enumerate(shrub_sites):
            obj = bpy.data.objects.new(f"full03:leisure_belt4_shrub_{i:02d}", None)
            planted.objects.link(obj)
            obj.instance_type = "COLLECTION"
            obj.instance_collection = shrub_masters[i % len(shrub_masters)]
            obj.location = (x, y, 0.16)
            obj.rotation_euler[2] = (i * 2.39996323) % 6.28318531
            obj.scale = (scale, scale, scale)
            obj["c2w_landscape_role"] = "layered_flowerbed_shrub"
            leisure_shrubs += 1
    integrated_audit = json.loads(
        root.get(
            "all44_13_integrated_leisure_audit"
            if FULL09
            else "all44_14_integrated_leisure_audit",
            "{}",
        )
    )
    log(
        "Leisure",
        "Region boundary: x[9.5,54.4], y[-85.2,-9.5] (ALL44-13 south-only expansion)"
        if FULL09
        else "Region boundary: x[9.5,135.2], y[-41.9,-9.5] (east-only expansion)",
    )
    log("Leisure", "Generation success")
    return {
        "removed_placeholder_objects": removed,
        "parameters": leisure_cfg,
        "dense_lawn_tile_instances": grass,
        "collection_instances": sum(
            o.instance_type == "COLLECTION" for o in root.all_objects
        ),
        "ground_system": (
            "grass-free resin-bound mineral aggregate"
            if FULL07
            else (
                "muted realistic turf; isolated shrub instances disabled"
                if FULL06_LANDSCAPE
                else (
                    "cultivated-soil layered flowerbeds"
                    if STRICT_FULL03
                    else "muted turf"
                )
            )
        ),
        "verified_belt4_style_shrub_instances": leisure_shrubs,
        "full06_isolated_shrubs_disabled": FULL06_LANDSCAPE,
        "grass_free_leisure_zone": FULL07 and grass == 0,
        "integrated_basketball_athletics_gymnasium_precinct": integrated_audit,
        "source_revision": "urban_v3_all44_13" if FULL09 else "urban_v3_all44_14",
        "reference_blends_loaded": [],
    }


def apply_parametric_parcel_plan() -> dict:
    """Build occupied urban blocks in land released by the selected topology.

    This is part of the production generator, not a blend-file correction.
    all30 first authors the physical road graph; the code below then gives every
    removed approach a distinct land-use program, building mass and detailed
    public-realm assets.  A large single-colour cover slab is deliberately
    forbidden because it was the source of the empty full_05 result.
    """
    if not PARAMETRIC_PRODUCTION:
        return {}
    import urban_assets as UA

    layout = PROFILE["layout"]
    coll = bpy.data.collections.new("TopologyDrivenUrbanBlocks")
    bpy.context.scene.collection.children.link(coll)
    created: list[bpy.types.Object] = []
    asset_roles: dict[str, list[str]] = {}
    program_rectangles: list[dict] = []

    def material(name: str):
        mat = bpy.data.materials.get(name)
        if mat is None:
            raise RuntimeError(f"Required generated regional material missing: {name}")
        return mat

    mats = {
        "paver": material("all43_01:stone"),
        "residential": material("a40_marble_paving"),
        "seam": material("a40_dark_marble_seam"),
        "park": material("a8_grass_park_emerald"),
        "activity": material("all44_10:MAT_DESATURATED_TURF"),
        "soil": material("all44_10:MAT_TURF_SOIL_EDGE"),
        "rubber": material("all44_10:MAT_MUTED_EPDM_CHARCOAL"),
    }

    def program_surface(name, bounds, mat, role):
        x0, x1, y0, y1 = bounds
        obj = UA._box(
            f"c2w_{layout}_{name}",
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            0.065,
            x1 - x0,
            y1 - y0,
            0.07,
            mat,
            coll,
            bev=0.025,
        )
        obj["c2w_layout_role"] = "topology_driven_program_surface"
        obj["c2w_infill_program"] = role
        obj["c2w_topology"] = layout
        created.append(obj)
        program_rectangles.append(
            {
                "name": name,
                "role": role,
                "bounds": [x0, x1, y0, y1],
                "area_m2": round((x1 - x0) * (y1 - y0), 2),
            }
        )
        return obj

    def detail_box(name, location, dimensions, mat, role, bevel=0.02):
        obj = UA._box(
            f"c2w_{layout}_{name}", *location, *dimensions, mat, coll, bev=bevel
        )
        obj["c2w_layout_role"] = role
        obj["c2w_topology"] = layout
        created.append(obj)
        return obj

    def find_master(*, exact=None, prefix=None):
        master = (
            bpy.data.collections.get(exact)
            if exact
            else next(
                (c for c in bpy.data.collections if c.name.startswith(prefix)), None
            )
        )
        if master is None:
            raise RuntimeError(
                f"Required high-detail master missing: {exact or prefix}"
            )
        return master

    def master_vertices(master):
        return sum(
            len(obj.data.vertices)
            for obj in master.all_objects
            if obj.type == "MESH" and obj.data
        )

    def real_tree_scale(master, target_height):
        zs = [
            (obj.matrix_world @ Vector(corner)).z
            for obj in master.all_objects
            if obj.type == "MESH" and obj.data
            for corner in obj.bound_box
        ]
        source_height = max(zs) - min(zs) if zs else 0.0
        if source_height <= 0.0:
            raise RuntimeError(f"Tree master has invalid height: {master.name}")
        return target_height / source_height

    def instance(master, name, location, role, rotation=0.0, scale=1.0):
        obj = bpy.data.objects.new(f"c2w_{layout}_{name}", None)
        coll.objects.link(obj)
        obj.instance_type = "COLLECTION"
        obj.instance_collection = master
        obj.location = location
        obj.rotation_euler[2] = rotation
        obj.scale = (scale, scale, scale)
        obj["c2w_layout_role"] = role
        obj["c2w_high_detail_master"] = master.name
        obj["c2w_master_mesh_vertices"] = master_vertices(master)
        obj["c2w_topology"] = layout
        created.append(obj)
        asset_roles.setdefault(role, []).append(obj.name)
        return obj

    def centered_collection_instance(master, name, target_xy, role, rotation=0.0):
        points = [
            obj.matrix_world @ Vector(corner)
            for obj in master.all_objects
            if obj.type == "MESH" and not obj.hide_render
            for corner in obj.bound_box
        ]
        if not points:
            raise RuntimeError(
                f"Building collection has no renderable mesh: {master.name}"
            )
        center = Vector(
            (
                (min(p.x for p in points) + max(p.x for p in points)) / 2,
                (min(p.y for p in points) + max(p.y for p in points)) / 2,
                0,
            )
        )
        return instance(
            master,
            name,
            (target_xy[0] - center.x, target_xy[1] - center.y, 0),
            role,
            rotation,
        )

    tree_masters = sorted(
        (
            c
            for c in bpy.data.collections
            if (
                "generic_treefactory" in c.name.lower()
                or "master:treefactory:" in c.name.lower()
                or c.name.startswith("All39Fast5_TreePrototype_")
            )
            and master_vertices(c) >= 10000
        ),
        key=lambda c: c.name,
    )
    if len(tree_masters) < 2:
        raise RuntimeError(
            f"Need at least two verified high-detail tree masters, got {len(tree_masters)}"
        )
    apartment_master = find_master(exact="Residential_apartment_exterior")
    shop_master = find_master(exact="all43_01:MASTER:convenience_store")
    restaurant_master = find_master(exact="all43_01:MASTER:restaurant")
    bench_master = find_master(prefix="C2W_MASTER_prefix_furniture.blend_clbench_")
    bus_master = find_master(
        prefix="C2W_MASTER_collection_bus_stop.blend_v3_bus_shelter"
    )
    bike_master = find_master(
        prefix="C2W_MASTER_collection_bike_station.blend_bike_fleet"
    )
    art_master = find_master(prefix="C2W_MASTER_prefix_public_art.blend_knot_")
    cafe_master = find_master(exact="OUTDOOR_CAFE_SET_MASTER")
    planter_master = find_master(exact="COMPLEX_REAR_FLOWERBED_MASTER")
    play_master = find_master(exact="all44_10:MASTER_CLIMBING_FRAME_REBUILT")

    # Each surface is intentionally below 250 m2.  This creates recognizable
    # parcel/courtyard seams and makes a regression to the full_05 mega-slabs a
    # hard, measurable failure.
    if layout == "linear_street":
        for name, bounds, mat, role in (
            (
                "west_residential_court_s",
                (-54.5, -34.0, -10.5, 0.0),
                mats["residential"],
                "apartment_courtyard",
            ),
            (
                "west_residential_court_n",
                (-54.5, -34.0, 0.0, 10.5),
                mats["residential"],
                "apartment_courtyard",
            ),
            (
                "west_retail_frontage_s",
                (-34.0, -10.5, -10.5, 0.0),
                mats["paver"],
                "mixed_use_frontage",
            ),
            (
                "west_retail_frontage_n",
                (-34.0, -10.5, 0.0, 10.5),
                mats["paver"],
                "mixed_use_frontage",
            ),
            (
                "east_linear_park_s",
                (10.5, 32.0, -10.5, 0.0),
                mats["paver"],
                "tree_promenade",
            ),
            (
                "east_linear_park_n",
                (10.5, 32.0, 0.0, 10.5),
                mats["paver"],
                "tree_promenade",
            ),
            (
                "east_activity_plaza_s",
                (32.0, 54.5, -10.5, 0.0),
                mats["paver"],
                "community_activity_forecourt",
            ),
            (
                "east_activity_plaza_n",
                (32.0, 54.5, 0.0, 10.5),
                mats["paver"],
                "community_activity_forecourt",
            ),
        ):
            program_surface(name, bounds, mat, role)

        centered_collection_instance(
            apartment_master,
            "west_infill_apartment",
            (-44.0, 0.0),
            "high_detail_infill_building",
        )
        instance(
            shop_master,
            "mainstreet_convenience",
            (-17.2, -5.6, 0),
            "high_detail_infill_building",
            -math.pi / 2,
        )
        instance(
            restaurant_master,
            "mainstreet_restaurant",
            (-17.2, 6.5, 0),
            "high_detail_infill_building",
            -math.pi / 2,
        )

        # A paved promenade runs through a planted linear park.  Alternating
        # real trees, benches and flowerbeds eliminate the former empty lawn.
        detail_box(
            "east_prom_k",
            (25.0, 0, 0.125),
            (29.0, 4.0, 0.08),
            mats["paver"],
            "pedestrian_promenade",
        )
        tree_sites = (
            (13.5, -6.3),
            (13.5, 6.3),
            (20.5, -6.3),
            (25.5, 6.3),
            (31.5, -6.3),
            (36.5, 6.3),
            (41.5, -6.3),
            (46.5, 6.3),
            (51.5, -6.3),
            (51.5, 6.3),
        )
        for i, (x, y) in enumerate(tree_sites):
            detail_box(
                f"promenade_tree_bed_{i}",
                (x, y, 0.12),
                (4.2, 3.6, 0.12),
                mats["soil"],
                "planted_tree_bed",
                0.06,
            )
            tree_master = tree_masters[i % len(tree_masters)]
            target_height = 5.8 + 0.55 * (i % 3)
            tree = instance(
                tree_master,
                f"promenade_tree_{i}",
                (x, y, 0.18),
                "high_detail_tree",
                rotation=(i * 0.73) % (2 * math.pi),
                scale=real_tree_scale(tree_master, target_height),
            )
            tree["c2w_real_world_tree_height_m"] = target_height
        for i, (x, y, r) in enumerate(
            (
                (16, 2.7, math.pi),
                (23, -2.7, 0),
                (30, 2.7, math.pi),
                (39, -2.8, 0),
                (49, 2.8, math.pi),
            )
        ):
            instance(
                bench_master,
                f"promenade_bench_{i}",
                (x, y, 0.13),
                "detailed_street_furniture",
                r,
            )
        for i, (x, y) in enumerate(((35, -6.0), (41, -6.0), (47, -6.0))):
            instance(
                planter_master,
                f"activity_planter_{i}",
                (x, y, 0.18),
                "detailed_landscape",
                0,
                0.82,
            )
        for i, (x, y) in enumerate(((37, 5.0), (43, 5.0))):
            instance(
                cafe_master,
                f"community_cafe_{i}",
                (x, y, 0.18),
                "active_public_realm",
                0,
                0.88,
            )
        instance(
            bike_master,
            "promenade_bike_station",
            (51, -3.5, 0.08),
            "mobility_hub",
            math.pi / 2,
            0.9,
        )
        instance(
            play_master,
            "community_climbing_zone",
            (47.5, -6.0, 0.32),
            "active_public_realm",
            math.pi / 2,
            0.9,
        )
        detail_box(
            "climbing_safety_surface",
            (47.5, -6.0, 0.17),
            (9.0, 7.0, 0.12),
            mats["rubber"],
            "active_recreation_surface",
            0.15,
        )
        released_regions = [(-54.5, -10.5, -10.5, 10.5), (10.5, 54.5, -10.5, 10.5)]
        built_footprint = 12.6 * 22.0 + 2 * 12.0 * 8.0
    else:
        for name, bounds, mat, role in (
            (
                "terminal_plaza",
                (-10.5, 10.5, 10.5, 22.0),
                mats["paver"],
                "t_junction_terminal_plaza",
            ),
            (
                "terminal_residential_w_s",
                (-10.5, 0.0, 22.0, 34.0),
                mats["residential"],
                "terminal_mixed_use_block",
            ),
            (
                "terminal_residential_e_s",
                (0.0, 10.5, 22.0, 34.0),
                mats["residential"],
                "terminal_mixed_use_block",
            ),
            (
                "terminal_residential_w_n",
                (-10.5, 0.0, 34.0, 46.0),
                mats["residential"],
                "terminal_mixed_use_block",
            ),
            (
                "terminal_residential_e_n",
                (0.0, 10.5, 34.0, 46.0),
                mats["residential"],
                "terminal_mixed_use_block",
            ),
            (
                "terminal_garden",
                (-10.5, 10.5, 46.0, 54.5),
                mats["park"],
                "residential_courtyard_garden",
            ),
        ):
            program_surface(name, bounds, mat, role)

        # The road now terminates on a real façade instead of a green/white
        # strip.  The retail pavilion and the apartment behind it form a dense
        # layered terminal composition unique to the T-junction variant.
        instance(
            restaurant_master,
            "terminal_retail_pavilion",
            (0, 18.0, 0),
            "high_detail_infill_building",
            math.pi,
        )
        centered_collection_instance(
            apartment_master,
            "terminal_apartment",
            (0, 35.0),
            "high_detail_infill_building",
        )
        detail_box(
            "terminal_entry_walk",
            (0, 14.0, 0.125),
            (5.0, 7.0, 0.08),
            mats["residential"],
            "terminal_entry_walk",
        )
        instance(
            art_master,
            "terminal_landmark",
            (-6.8, 13.7, 0.10),
            "civic_landmark",
            0,
            0.8,
        )
        instance(
            bus_master,
            "terminal_bus_shelter",
            (7.1, 13.8, 0.08),
            "mobility_hub",
            math.pi,
            0.82,
        )
        instance(
            bike_master,
            "terminal_bike_station",
            (-7.0, 20.3, 0.08),
            "mobility_hub",
            math.pi / 2,
            0.8,
        )
        for i, (x, y) in enumerate(
            ((-7, 25), (7, 27), (-7, 39), (7, 42), (-7, 49), (7, 52))
        ):
            detail_box(
                f"terminal_tree_bed_{i}",
                (x, y, 0.12),
                (3.0, 3.0, 0.12),
                mats["soil"],
                "planted_tree_bed",
                0.06,
            )
            tree_master = tree_masters[i % len(tree_masters)]
            target_height = 5.6 + 0.6 * (i % 3)
            tree = instance(
                tree_master,
                f"terminal_tree_{i}",
                (x, y, 0.18),
                "high_detail_tree",
                rotation=(i * 0.91) % (2 * math.pi),
                scale=real_tree_scale(tree_master, target_height),
            )
            tree["c2w_real_world_tree_height_m"] = target_height
        for i, (x, y, r) in enumerate(
            (
                (-7, 17, math.pi / 2),
                (7, 23, -math.pi / 2),
                (-7, 46, math.pi / 2),
                (7, 47, -math.pi / 2),
            )
        ):
            instance(
                bench_master,
                f"terminal_bench_{i}",
                (x, y, 0.13),
                "detailed_street_furniture",
                r,
            )
        for i, (x, y) in enumerate(((-6, 21), (6, 21), (-6, 44), (6, 44))):
            instance(
                planter_master,
                f"terminal_planter_{i}",
                (x, y, 0.18),
                "detailed_landscape",
                math.pi / 2,
                0.76,
            )
        instance(
            cafe_master,
            "terminal_cafe_seating",
            (6.2, 17.0, 0.18),
            "active_public_realm",
            math.pi / 2,
            0.78,
        )
        released_regions = [(-10.5, 10.5, 10.5, 54.5)]
        built_footprint = 12.6 * 22.0 + 12.0 * 8.0

    # Add true paving joints to every public-realm corridor.  They are small
    # construction detail, not stand-in geometry.
    if layout == "linear_street":
        for i, x in enumerate(range(-32, -10, 3)):
            detail_box(
                f"mainstreet_paver_joint_{i}",
                (x, 0, 0.108),
                (0.025, 21.0, 0.012),
                mats["seam"],
                "paving_joint",
                0,
            )
        for i, x in enumerate(range(12, 55, 3)):
            detail_box(
                f"promenade_paver_joint_{i}",
                (x, 0, 0.108),
                (0.025, 4.0, 0.012),
                mats["seam"],
                "paving_joint",
                0,
            )
    else:
        for i, y in enumerate((12.5, 15.0, 17.5, 20.0)):
            detail_box(
                f"terminal_paver_joint_{i}",
                (0, y, 0.108),
                (21.0, 0.025, 0.012),
                mats["seam"],
                "paving_joint",
                0,
            )

    roads = bpy.data.collections.get("Road")
    visible_roads = sorted(o.name for o in roads.objects if not o.hide_render)
    expected_roads = {
        "linear_street": ["road_linear_ns"],
        "t_junction": ["road_e", "road_s", "road_w", "t_junction_center"],
    }[layout]
    traffic_lights = [
        o
        for o in bpy.data.collections.get("TrafficLights", []).objects
        if not o.hide_render
    ]
    expected_lights = 0 if layout == "linear_street" else 3
    crosswalk_groups = {
        name.split("_")[2]
        for name in (
            o.name
            for o in bpy.data.collections["RoadMarkings"].objects
            if not o.hide_render and o.name.startswith("xwk_")
        )
    }
    expected_crosswalk_groups = 1 if layout == "linear_street" else 3

    # Rasterize the authored land-use plan.  Any connected cell not covered by
    # an intentional program is an actual generation failure.  Ground alone is
    # insufficient: every rectangle above has a named urban function.
    cell = 1.0
    released_cells = set()
    for x0, x1, y0, y1 in released_regions:
        for ix in range(math.floor(x0), math.ceil(x1)):
            for iy in range(math.floor(y0), math.ceil(y1)):
                x, y = ix + 0.5, iy + 0.5
                if x0 <= x <= x1 and y0 <= y <= y1:
                    released_cells.add((ix, iy))
    covered_cells = set()
    for spec in program_rectangles:
        x0, x1, y0, y1 = spec["bounds"]
        for cell_xy in released_cells:
            x, y = cell_xy[0] + 0.5, cell_xy[1] + 0.5
            if x0 <= x <= x1 and y0 <= y <= y1:
                covered_cells.add(cell_xy)
    uncovered = released_cells - covered_cells
    largest_component = 0
    while uncovered:
        frontier = [uncovered.pop()]
        size = 0
        while frontier:
            x, y = frontier.pop()
            size += 1
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in uncovered:
                    uncovered.remove(neighbor)
                    frontier.append(neighbor)
        largest_component = max(largest_component, size)

    apartment_windows = sum(
        o.name.startswith("a41_apt_front_win_") and "_frame" in o.name
        for o in bpy.context.scene.objects
    )
    storefront_instances = [
        o.name
        for o in bpy.context.scene.objects
        if o.instance_type == "COLLECTION"
        and o.instance_collection
        and o.instance_collection.name
        in {"all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant"}
    ]
    released_area = len(released_cells) * cell * cell
    largest_surface = max(s["area_m2"] for s in program_rectangles)
    new_buildings = asset_roles.get("high_detail_infill_building", [])
    topology_tree_heights = [
        float(obj.get("c2w_real_world_tree_height_m"))
        for obj in created
        if obj.get("c2w_layout_role") == "high_detail_tree"
    ]
    detailed_public_assets = sum(
        len(names)
        for role, names in asset_roles.items()
        if role != "high_detail_infill_building"
    )
    errors = []
    if visible_roads != expected_roads:
        errors.append(f"road objects expected {expected_roads}, got {visible_roads}")
    if len(traffic_lights) != expected_lights:
        errors.append(
            f"traffic lights expected {expected_lights}, got {len(traffic_lights)}"
        )
    if len(crosswalk_groups) != expected_crosswalk_groups:
        errors.append(
            f"crosswalk groups expected {expected_crosswalk_groups}, got {sorted(crosswalk_groups)}"
        )
    if largest_component:
        errors.append(
            f"released land contains {largest_component:.1f} m2 contiguous unprogrammed area"
        )
    if largest_surface > 250.0:
        errors.append(
            f"single undifferentiated surface too large: {largest_surface:.1f} m2"
        )
    if len(new_buildings) < (3 if layout == "linear_street" else 2):
        errors.append(f"insufficient topology-specific building mass: {new_buildings}")
    if detailed_public_assets < (18 if layout == "linear_street" else 16):
        errors.append(
            f"insufficient detailed public-realm assets: {detailed_public_assets}"
        )
    if not topology_tree_heights or not all(
        5.5 <= h <= 7.0 for h in topology_tree_heights
    ):
        errors.append(
            f"infill trees lack realistic mature scale: {topology_tree_heights}"
        )
    if apartment_windows != PROFILE["residential_apartment_floors"] * 5:
        errors.append(
            f"apartment source organization mismatch: front windows={apartment_windows}"
        )
    if errors:
        raise RuntimeError(
            "topology-driven production layout audit failed: " + "; ".join(errors)
        )

    utilization = {
        "valid": True,
        "released_land_area_m2": round(released_area, 1),
        "programmed_land_area_m2": round(len(covered_cells) * cell * cell, 1),
        "programmed_ratio": round(len(covered_cells) / max(len(released_cells), 1), 4),
        "largest_contiguous_unprogrammed_area_m2": round(
            largest_component * cell * cell, 1
        ),
        "largest_single_surface_area_m2": round(largest_surface, 1),
        "estimated_new_building_footprint_m2": round(built_footprint, 1),
        "estimated_new_building_coverage": round(built_footprint / released_area, 3),
        "new_high_detail_buildings": new_buildings,
        "detailed_public_realm_asset_instances": detailed_public_assets,
        "mature_tree_heights_m": topology_tree_heights,
        "asset_roles": asset_roles,
        "program_rectangles": program_rectangles,
        "former_full05_megaslab_objects": 0,
    }
    plan = {
        "schema_version": "3.0-topology-driven-occupied-blocks",
        "seed": SEED,
        "variant": VARIANT,
        "road_topology": layout,
        "active_road_arms": PROFILE["active_road_arms"],
        "building_organization": PROFILE["building_organization"],
        "released_land_program": PROFILE["released_land_program"],
        "regional_parameters": {
            "commercial_pattern": PROFILE["commercial_pattern"],
            "residential_apartment_floors": PROFILE["residential_apartment_floors"],
            "park_tree_cap": PROFILE["park_tree_cap"],
            "leisure_court": PROFILE["leisure_court"],
        },
        "released_land_utilization_audit": utilization,
        "topology_audit": {
            "valid": True,
            "visible_road_objects": visible_roads,
            "traffic_light_approaches": len(traffic_lights),
            "crosswalk_groups": sorted(crosswalk_groups),
            "legacy_crossroads_components": [],
            "topology_driven_objects": [o.name for o in created],
            "apartment_front_window_groups": apartment_windows,
            "high_detail_storefront_instances": storefront_instances,
        },
    }
    (OUT / "layout_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf8"
    )
    log(
        "Urban Layout",
        f"Topology-driven occupied plan applied: {layout}; organization={PROFILE['building_organization']}; "
        f"programmed={utilization['programmed_ratio']:.0%}; new_buildings={len(new_buildings)}; "
        f"public_assets={detailed_public_assets}; roads={visible_roads}",
    )
    return plan


def add_validation_cameras() -> list[tuple[bpy.types.Object, str]]:
    layout = PROFILE.get("layout", "crossroads")
    topology_view = (
        ("02_linear_street_overview.png", (34, -42, 38), (0, 0, 0), 52)
        if layout == "linear_street"
        else (
            ("02_t_junction_overview.png", (34, -34, 38), (0, 0, 0), 52)
            if layout == "t_junction"
            else ("02_main_intersection.png", (32, -34, 35), (0, 0, 0), 52)
        )
    )
    street_view = (
        ("11_street_level_linear_street.png", (-7, -43, 1.72), (-2, 24, 1.5), 58)
        if layout == "linear_street"
        else (
            ("11_street_level_t_junction.png", (-42, -7, 1.72), (22, -2, 1.5), 58)
            if layout == "t_junction"
            else ("11_street_level_main_road.png", (2, -38, 1.72), (1, 10, 1.5), 58)
        )
    )
    specs = [
        (
            ("01_full_scene_aerial.png", (170, -210, 220), (-4, 70, 0), 50)
            if FULL09
            else (
                ("01_full_scene_aerial.png", (126, -148, 174), (14, 39, 0), 50)
                if ADD_RIVER
                else (
                    ("01_full_scene_aerial.png", (108, -126, 158), (0, 35, 0), 50)
                    if FULL07
                    else ("01_full_scene_aerial.png", (82, -92, 112), (0, 0, 0), 48)
                )
            )
        ),
        topology_view,
        (
            "03_commercial_region.png",
            (22, -100, 30) if STRICT_FULL03 else (-6, -56, 25),
            (-30, -26.5, 1) if STRICT_FULL03 else (-30, -26, 2),
            52,
        ),
        ("04_residential_region.png", (-5, 7, 31), (-34, 31, 4), 55),
        ("05_park_region.png", (9, 8, 29), (31, 30, 1), 53),
        ("06_leisure_region.png", (6, -7, 30), (29, -27, 2), 52),
        ("07_commercial_road_transition.png", (-5, -24, 8), (-13, -18, 0.5), 55),
        ("08_residential_road_transition.png", (-7, 22, 8), (-12, 16, 0.5), 55),
        ("09_park_road_transition.png", (7, 21, 8), (13, 16, 0.5), 55),
        ("10_region_boundary_overview.png", (0, -2, 78), (0, 0, 0), 47),
        street_view,
        ("12_street_level_commercial.png", (0, -28, 1.72), (-28, -25, 2.5), 56),
        ("13_street_level_residential.png", (0, 28, 1.72), (-30, 30, 3.0), 56),
        ("14_street_level_park.png", (0, 28, 1.72), (30, 30, 1.5), 56),
        ("15_street_level_leisure.png", (0, -28, 1.72), (28, -27, 1.8), 56),
    ]
    if PARAMETRIC_PRODUCTION:
        specs.extend(
            [
                (
                    (
                        "16_linear_released_land_program.png",
                        (66, -58, 48),
                        (14, 0, 2),
                        52,
                    )
                    if layout == "linear_street"
                    else (
                        "16_t_terminal_block_program.png",
                        (38, -30, 35),
                        (0, 27, 4),
                        52,
                    )
                ),
                (
                    ("17_linear_infill_frontage.png", (7, -32, 2.2), (-26, 0, 5.5), 44)
                    if layout == "linear_street"
                    else
                    # Pull back along the surviving south arm so the terminal facade,
                    # apartment marker and occupied public realm read together.  The
                    # closer camera sat beneath the pavilion awning and produced an
                    # uninformative wall-only frame.
                    ("17_t_terminal_street_view.png", (0, -38, 2.4), (0, 20, 5.2), 48)
                ),
            ]
        )
    if STRICT_FULL03:
        specs.extend(
            [
                ("16_park_reference_match.png", (66, -4, 34), (32, 31, 2.2), 50),
                ("17_roadside_flowerbed_close.png", (4, 17, 3.2), (9.25, 22, 0.55), 54),
                (
                    "18_leisure_flowerbed_close.png",
                    (5, -31, 3.1),
                    (11.7, -32, 0.55),
                    55,
                ),
            ]
        )
    if FULL07:
        specs.extend(
            [
                ("19_extended_residential_overview.png", (88, 43, 76), (0, 105, 5), 52),
                (
                    "20_extended_residential_street.png",
                    (-55, 65.2, 2.0),
                    (34, 87, 4.0),
                    56,
                ),
                ("21_commercial_phonebooth.png", (1, -27, 3.2), (-13, -26.5, 1.5), 52),
                ("22_residential_open_road_edge.png", (1, 28, 3.0), (-9, 30, 1.0), 55),
                ("23_park_tree_complexity.png", (11, 18, 5.2), (23, 27, 4.5), 48),
            ]
        )
    if FULL08 and not FULL09:
        specs.extend(
            [
                (
                    "24_commercial_all43_18_match.png",
                    (-30, -86, 13.0),
                    (-30, -25.5, 2.2),
                    55,
                ),
                (
                    "25_extended_crosswalk_connection.png",
                    (-17, 53, 12.5),
                    (0, 65.5, 0.1),
                    48,
                ),
                ("26_crossroads_lane_markings.png", (27, -29, 32), (0, 0, 0.1), 54),
            ]
        )
    if FULL09:
        specs.extend(
            [
                (
                    "24_commercial_all43_24_match.png",
                    (-30, -86, 13.0),
                    (-30, -25.5, 2.2),
                    55,
                ),
                (
                    "25_extended_crosswalk_connection.png",
                    (-17, 53, 12.5),
                    (0, 65.5, 0.1),
                    48,
                ),
                ("26_crossroads_lane_markings.png", (27, -29, 32), (0, 0, 0.1), 54),
                ("27_third_residential_aerial.png", (102, 102, 126), (-22, 188, 9), 52),
                (
                    "28_third_residential_street.png",
                    (-86, 126, 2.2),
                    (-28, 170, 6.5),
                    54,
                ),
                ("29_city_north_far.png", (8, 316, 116), (-4, 88, 4), 54),
                ("30_city_south_far.png", (3, -194, 100), (0, 52, 4), 54),
                ("31_city_east_far.png", (205, 45, 110), (6, 62, 4), 54),
                ("32_city_west_far.png", (-205, 40, 108), (-2, 64, 4), 54),
                ("33_city_top_down.png", (-5, 70, 330), (-5, 70, 0), 54),
                ("34_all44_13_leisure_overview.png", (2, -31, 110), (32, -46, 2), 40),
                ("35_all44_13_gymnasium_arrival.png", (6, -34, 14), (39.7, -53, 5), 52),
                ("36_all44_13_athletics_close.png", (7, -60, 20), (31, -75.3, 1), 50),
                ("37_all44_13_playground_close.png", (58, -7, 7.0), (40, -24, 2.0), 52),
            ]
        )
    if ADD_RIVER and FULL09:
        specs.extend(
            [
                ("38_river_corridor_aerial.png", (128, -92, 112), (68, 38, -0.15), 52),
                ("39_park_riverfront.png", (45, 17, 6.2), (68, 30, -0.10), 51),
                ("40_river_footbridge.png", (50, 15, 4.2), (68, 26, 0.55), 48),
                ("41_river_level_long_view.png", (68, -57, 1.35), (69, 47, -0.12), 55),
            ]
        )
    elif ADD_RIVER:
        specs.extend(
            [
                ("24_river_corridor_aerial.png", (128, -92, 112), (68, 38, -0.15), 52),
                ("25_park_riverfront.png", (45, 17, 6.2), (68, 30, -0.10), 51),
                ("26_leisure_riverfront.png", (45, -31, 5.8), (68, -27, -0.12), 51),
                ("27_river_footbridge.png", (50, 15, 4.2), (68, 26, 0.55), 48),
                ("28_river_level_long_view.png", (68, -57, 1.35), (69, 47, -0.12), 55),
            ]
        )
    result = []
    coll = bpy.data.collections.get("FullSceneValidation") or bpy.data.collections.new(
        "FullSceneValidation"
    )
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for filename, location, target, lens in specs:
        data = bpy.data.cameras.new("full:" + filename + ":data")
        cam = bpy.data.objects.new("full:" + filename, data)
        coll.objects.link(cam)
        cam.location = location
        data.lens = lens
        cam.rotation_euler = (
            (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        )
        result.append((cam, filename))
    return result


def render_validation(cameras) -> None:
    # Production recovery switch: the scene and all hard audits are still built
    # from source and the final blend/report are still written.  Validation
    # frames may then be rendered in isolated Blender workers, which prevents
    # Cycles BVH memory from accumulating across this unusually dense scene.
    if os.environ.get("C2W_SKIP_VALIDATION_RENDER", "0") == "1":
        log(
            "Validation", "Deferred validation rendering to isolated production workers"
        )
        return
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    render_device = os.environ.get("C2W_RENDER_DEVICE", "CPU").upper()
    if render_device == "GPU":
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for device in prefs.devices:
                device.use = device.type != "CPU"
            scene.cycles.device = "GPU"
            log("Validation", "Cycles OPTIX rendering enabled")
        except Exception as exc:
            scene.cycles.device = "CPU"
            log("Validation", f"OPTIX unavailable; using CPU: {exc}")
    else:
        scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    for cam, filename in cameras:
        scene.camera = cam
        scene.render.filepath = str(OUT / filename)
        bpy.ops.render.render(write_still=True)
        log("Validation", f"Rendered {filename}")


def main() -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf8")
    build_backbone()
    log("Park", "Region boundary: x[10.5,54.5], y[10.5,54.5]")
    log("Park", "Generation success (all40/all41 road-park source pipeline)")
    log("Residential", "Region boundary: x[-54.5,-10.5], y[10.5,54.5]")
    log("Residential", "Generation success (all40/all41 source pipeline)")
    commercial = build_commercial()
    # Large scatter node graphs make every subsequent bpy object operation
    # reevaluate millions of viewport instances.  Pause only modifier viewport
    # evaluation while assembling leisure assets, then restore it before audit,
    # save and render.  Render geometry and final scene content are unchanged.
    paused_scatter_modifiers = []
    if FULL06_LANDSCAPE or PARAMETRIC_PRODUCTION:
        for obj in bpy.context.scene.objects:
            for modifier in obj.modifiers:
                if modifier.type == "NODES" and modifier.show_viewport:
                    paused_scatter_modifiers.append(modifier)
                    modifier.show_viewport = False
        log(
            "Integration",
            f"Paused {len(paused_scatter_modifiers)} scatter modifiers during leisure assembly",
        )
    full07_revision = {}
    try:
        leisure = build_leisure()
        if FULL07:
            import urban_v1_full_07_extension

            full07_revision = urban_v1_full_07_extension.apply()
    finally:
        for modifier in paused_scatter_modifiers:
            modifier.show_viewport = True
    if paused_scatter_modifiers:
        log("Integration", "Restored all scatter modifiers before audit and render")
    layout_plan = apply_parametric_parcel_plan()
    if FULL07:
        layout_plan = {
            "base_layout": layout_plan,
            "full07_extension": full07_revision["residential_extension"],
            **(
                {
                    "full09_third_residential": full07_revision[
                        "third_residential_district"
                    ]
                }
                if FULL09
                else {}
            ),
        }
        revision_label = "Full09" if FULL09 else ("Full08" if FULL08 else "Full07")
        log(
            revision_label,
            "Removed the residential road-edge barrier and relocated the phone booth",
        )
        log(
            revision_label,
            "Generated the connected northern street and second residential district from source",
        )
        if FULL08:
            log(
                revision_label,
                "Corrected the extended-road crosswalk and completed solid/dashed crossroads markings",
            )
        if FULL09:
            log(
                revision_label,
                "Generated the ALL45-09-style third residential district and connected one-way street pair from source",
            )
            log(
                revision_label,
                "Installed the ALL44-13 south-planned gymnasium, athletics ground and retained playground/court precinct",
            )
    log("Integration", "Boundary transitions generated by shared road setbacks")
    log("Integration", "Streetscape generated by global road collections")
    log("Integration", "Vegetation exclusions applied at x/y road setback ±10.5m")
    log("Integration", "Collision check completed")
    cameras = add_validation_cameras()
    if FULL07:
        # Render the visually decisive revision views first.  A bad TreeFactory
        # crown must be caught before spending time on every inherited camera.
        priority = {
            "24_commercial_all43_24_match.png": 0,
            "27_third_residential_aerial.png": 1,
            "34_all44_13_leisure_overview.png": 2,
            "38_river_corridor_aerial.png": 3,
            "24_river_corridor_aerial.png": 0,
            "25_park_riverfront.png": 1,
            "26_leisure_riverfront.png": 2,
            "27_river_footbridge.png": 3,
            "28_river_level_long_view.png": 4,
            "24_commercial_all43_18_match.png": 0,
            "25_extended_crosswalk_connection.png": 1,
            "26_crossroads_lane_markings.png": 2,
            "23_park_tree_complexity.png": 0,
            "01_full_scene_aerial.png": 3,
            "18_leisure_flowerbed_close.png": 4,
            "19_extended_residential_overview.png": 5,
            "21_commercial_phonebooth.png": 6,
            "22_residential_open_road_edge.png": 7,
        }
        cameras.sort(key=lambda item: (priority.get(item[1], 10), item[1]))
    # Hard audit: these are generation failures, not optional decorations.
    road_markings = (
        list((bpy.data.collections.get("RoadMarkings") or []).all_objects)
        if bpy.data.collections.get("RoadMarkings")
        else []
    )
    streetlights = [o for o in bpy.data.objects if "streetlight" in o.name.lower()]
    if (
        REVISION in ("urban_v1_full_02", "urban_v1_full_03") or PARAMETRIC_PRODUCTION
    ) and (not road_markings or not streetlights):
        raise RuntimeError(
            f"streetscape audit failed: markings={len(road_markings)}, streetlights={len(streetlights)}"
        )
    requirement_audit = {}
    if STRICT_FULL03:
        tree_master_prefix = (
            "full02:MASTER:TreeFactory:" if FULL07 else "All39Fast5_TreePrototype_"
        )
        tree_instances = [
            o
            for o in bpy.context.scene.objects
            if o.instance_type == "COLLECTION"
            and o.instance_collection
            and o.instance_collection.name.startswith(tree_master_prefix)
        ]
        tree_masters = sorted(
            {o.instance_collection for o in tree_instances}, key=lambda c: c.name
        )
        explicit_leaves = sum(
            int(coll.get("c2w_explicit_leaf_count", 0))
            or sum(
                (
                    obj.name.startswith("all39_fast5_tree_mother_")
                    and "_leaf_" in obj.name
                )
                or bool(obj.get("c2w_genuine_leaffactory_mesh"))
                for obj in coll.all_objects
            )
            for coll in tree_masters
        )
        explicit_leaves_by_master = {
            coll.name: int(coll.get("c2w_explicit_leaf_count", 0))
            or sum(
                bool(obj.get("c2w_genuine_leaffactory_mesh"))
                for obj in coll.all_objects
            )
            for coll in tree_masters
        }
        visible_bark_objects_by_master = {
            coll.name: sum(
                obj.type == "MESH" and not obj.get("c2w_genuine_leaffactory_mesh")
                for obj in coll.all_objects
            )
            for coll in tree_masters
        }
        tree_vertices = sum(
            len(obj.data.vertices)
            for coll in tree_masters
            for obj in coll.all_objects
            if obj.type == "MESH" and obj.data and "_leaf_" not in obj.name
        )
        degenerate_tree_names = [
            o.name
            for o in bpy.context.scene.objects
            if not o.hide_render
            and (
                o.name.startswith("tr_canopy_")
                or (
                    o.instance_collection
                    and "MASTER_generic_treefactory" in o.instance_collection.name
                )
                or o.name.startswith("all43_01:tree_")
            )
        ]
        park_material = bpy.data.materials.get(
            "a8_grass_park_pale_full06" if FULL06_LANDSCAPE else "a8_grass_park_emerald"
        )
        park_ramp = (
            next(
                (
                    n
                    for n in park_material.node_tree.nodes
                    if n.bl_idname == "ShaderNodeValToRGB"
                ),
                None,
            )
            if park_material
            else None
        )
        park_colors = (
            [list(e.color) for e in park_ramp.color_ramp.elements] if park_ramp else []
        )
        park_lawn_palette_valid = bool(park_colors) and (
            all(
                c[0] >= 0.05 and c[1] <= 0.36 and c[1] / max(c[0], 0.001) < 3.0
                for c in park_colors
            )
            if FULL06_LANDSCAPE
            else all(c[1] > c[0] * 5 and c[1] > c[2] * 5 for c in park_colors)
        )
        flowerbed_grounds = [
            o
            for o in bpy.context.scene.objects
            if o.get("c2w_landscape_role") == "layered_flowerbed"
        ]
        flat_green_nonpark = [
            o.name
            for o in bpy.context.scene.objects
            if o.type == "MESH"
            and not o.hide_render
            and any(m and "greenstrip" in m.name.lower() for m in o.data.materials)
        ]
        mesh_signature = commercial.get("all43_shared_mesh_signature", {})
        commercial_exact = (
            commercial.get("reference_revision") == "urban_v3_all43_18"
            and not commercial.get("missing_master_assets")
            and (
                not FULL08
                or (
                    commercial.get("pipeline_strategy")
                    == "source-level all43 reconstruction with all43_18 base, all43_19 corner 7-Eleven and active all43_25 connected McDonald's/cafe/two-reference-bar inverse-L pass"
                    and commercial.get("reference_blend") is None
                    and not commercial.get("reference_blends_loaded")
                    and mesh_signature.get("cube_vertices") == 8
                    and abs(float(mesh_signature.get("cube_coordinate_min", 99)) + 0.5)
                    < 1e-6
                    and abs(float(mesh_signature.get("cube_coordinate_max", 99)) - 0.5)
                    < 1e-6
                    and mesh_signature.get("cylinder_vertices") == 24
                    and abs(float(mesh_signature.get("cylinder_z_min", 99)) + 0.5)
                    < 1e-6
                    and abs(float(mesh_signature.get("cylinder_z_max", 99)) - 0.5)
                    < 1e-6
                    and commercial.get("rebuild_visible_legacy_objects_in_shop_masters")
                    == 0
                    and commercial.get("rebuild_new_all43_15_objects", 0) >= 640
                    and commercial.get("detail_product_support_audit", "").startswith(
                        "PASS"
                    )
                    and commercial.get("detail_grounded_product_instances", 0) >= 117
                    and not commercial.get("detail_missing_master_assets")
                    and "detail_clean_scene_audit_note" not in commercial
                    and commercial.get("corner711_store_is_linked_collection_instance")
                    is True
                    and commercial.get(
                        "commercial20_mcdonalds_is_linked_collection_instance"
                    )
                    is True
                    and commercial.get("commercial20_shop_layout_changed_count") == 3
                    and commercial.get("commercial20_seven_mcdonalds_party_gap_m", 99)
                    <= 0.04
                    and commercial.get(
                        "commercial20_seven_mcdonalds_party_overlap_m", 0
                    )
                    >= 4.50
                    and commercial.get(
                        "commercial20_seven_corner_kitchen_party_gap_m", 99
                    )
                    <= 0.04
                    and commercial.get(
                        "commercial20_mcdonalds_corner_kitchen_party_gap_m", 99
                    )
                    <= 0.04
                    and commercial.get(
                        "commercial20_fresh_mart_corner_kitchen_party_gap_m", 99
                    )
                    <= 0.04
                    and commercial.get("commercial20_umbrella_count") == 4
                    and commercial.get("commercial20_entry_walk_clear_width_m", 0)
                    >= 2.40
                    and commercial.get(
                        "commercial20_mcdonalds_length_increase_from_all43_22_m", 0
                    )
                    >= 2.75
                    and commercial.get("commercial20_mcdonalds_sign_inside_own_patio")
                    is True
                    and commercial.get(
                        "commercial20_mcdonalds_sign_east_boundary_clearance_m", 0
                    )
                    >= 0.10
                    and commercial.get(
                        "commercial20_mcdonalds_sign_north_boundary_clearance_m", 0
                    )
                    >= 0.10
                    and commercial.get(
                        "commercial20_mcdonalds_sign_minimum_furniture_clearance_m", 0
                    )
                    >= 0.10
                    and commercial.get("commercial20_stall_count") == 16
                    and not commercial.get("commercial20_new_mesh_quality_failures")
                    and not commercial.get("commercial20_forbidden_toy_or_proxy_names")
                    and commercial.get(
                        "commercial20_cafe_is_linked_collection_instance"
                    )
                    is True
                    and commercial.get("commercial20_cafe_recursive_component_count", 0)
                    >= 240
                    and commercial.get("commercial20_cafe_mcdonalds_party_gap_m", 99)
                    <= 0.01
                    and commercial.get("commercial20_frontage_chair_count") == 3
                    and commercial.get("commercial20_frontage_table_count") == 2
                    and commercial.get("commercial20_frontage_chairs_face_road") is True
                    and commercial.get(
                        "commercial20_frontage_chair_back_clearance_to_facade_m", 99
                    )
                    <= 0.50
                    and commercial.get("commercial20_frontage_grounding_error_m", 99)
                    <= 0.002
                    and commercial.get("commercial20_planter_shell_is_hollow_assembly")
                    is True
                    and commercial.get(
                        "commercial20_planter_liner_is_hollow_five_piece_assembly"
                    )
                    is True
                    and commercial.get("commercial20_botanical_stem_count") == 3
                    and commercial.get("commercial20_botanical_leaf_count") == 22
                    and commercial.get("commercial20_botanical_leaf_vertices_each", 0)
                    >= 45
                    and commercial.get("commercial20_cafe_botanical_leaf_mesh_count")
                    == 22
                    and commercial.get(
                        "commercial20_cafe_botanical_continuous_stem_mesh_count"
                    )
                    == 3
                    and not commercial.get(
                        "commercial20_cafe_botanical_leaf_evaluated_intersections"
                    )
                    and commercial.get(
                        "commercial20_cafe_botanical_canopy_clearance_to_storefront_m",
                        0,
                    )
                    >= 0.20
                    and commercial.get(
                        "commercial20_cafe_botanical_lower_canopy_clearance_above_chair_m",
                        0,
                    )
                    >= 0.07
                    and commercial.get(
                        "commercial20_cafe_planter_foliage_clearance_to_mcdonalds_patio_fence_m",
                        0,
                    )
                    >= 0.18
                    and commercial.get("commercial20_parking_stalls_consumed") == 0
                    and not commercial.get(
                        "commercial20_cafe_new_mesh_quality_failures"
                    )
                    and not commercial.get(
                        "commercial20_cafe_forbidden_toy_or_proxy_names"
                    )
                    and commercial.get("commercial20_production_revision")
                    == "urban_v3_all43_25"
                    and commercial.get("commercial20_bar_store_count") == 2
                    and commercial.get(
                        "commercial20_copper_is_linked_collection_instance"
                    )
                    is True
                    and commercial.get(
                        "commercial20_hawthorn_is_linked_collection_instance"
                    )
                    is True
                    and commercial.get(
                        "commercial20_copper_recursive_component_count", 0
                    )
                    >= 235
                    and commercial.get(
                        "commercial20_hawthorn_recursive_component_count", 0
                    )
                    >= 245
                    and commercial.get("commercial20_bar_bottle_instance_count", 0)
                    >= 90
                    and commercial.get("commercial20_copper_front_stool_count") == 5
                    and commercial.get("commercial20_hawthorn_bistro_table_count") == 3
                    and commercial.get("commercial20_copper_hawthorn_party_gap_m", 99)
                    <= 0.01
                    and commercial.get("commercial20_hawthorn_cafe_party_gap_m", 99)
                    <= 0.01
                    and commercial.get("commercial20_inverse_l_north_arm_continuous")
                    is True
                    and commercial.get(
                        "commercial20_seven_eleven_retained_at_crossroads_corner"
                    )
                    is True
                    and commercial.get("commercial20_copper_entry_clear_width_m", 0)
                    >= 1.45
                    and commercial.get("commercial20_hawthorn_entry_clear_width_m", 0)
                    >= 1.50
                    and not commercial.get(
                        "commercial20_frontage_obstacles_inside_entry_routes"
                    )
                    and not commercial.get("commercial20_new_mesh_quality_failures")
                    and not commercial.get("commercial20_forbidden_toy_or_proxy_names")
                )
            )
        )
        commercial_all43_24_exact = (
            FULL09
            and commercial.get("reference_revision") == "urban_v3_all43_24"
            and commercial.get("reference_blend") is None
            and not commercial.get("reference_blends_loaded")
            and commercial.get("pipeline_strategy")
            == "source-level all43 reconstruction with all43_18 base, all43_19 7-Eleven and active all43_24 lengthened-McDonald's/protected-sign/road-facing-chair/collision-audited-botanical-cafe pass"
            and commercial.get("commercial20_production_revision")
            == "urban_v3_all43_24"
            and commercial.get("commercial20_all43_25_reference_bars_built") is False
            and mesh_signature.get("cube_vertices") == 8
            and abs(float(mesh_signature.get("cube_coordinate_min", 99)) + 0.5) < 1e-6
            and abs(float(mesh_signature.get("cube_coordinate_max", 99)) - 0.5) < 1e-6
            and mesh_signature.get("cylinder_vertices") == 24
            and abs(float(mesh_signature.get("cylinder_z_min", 99)) + 0.5) < 1e-6
            and abs(float(mesh_signature.get("cylinder_z_max", 99)) - 0.5) < 1e-6
            and commercial.get("commercial20_shop_layout_changed_count") == 3
            and commercial.get("commercial20_stall_count") == 16
            and commercial.get("commercial20_mcdonalds_is_linked_collection_instance")
            is True
            and commercial.get("commercial20_cafe_is_linked_collection_instance")
            is True
            and commercial.get("commercial20_cafe_recursive_component_count", 0) >= 240
            and commercial.get("commercial20_frontage_chair_count") == 3
            and commercial.get("commercial20_frontage_table_count") == 2
            and commercial.get("commercial20_frontage_chairs_face_road") is True
            and commercial.get("commercial20_botanical_stem_count") == 3
            and commercial.get("commercial20_botanical_leaf_count") == 22
            and not commercial.get(
                "commercial20_cafe_botanical_leaf_evaluated_intersections"
            )
            and not commercial.get("commercial20_new_mesh_quality_failures")
            and not commercial.get("commercial20_cafe_new_mesh_quality_failures")
            and not commercial.get("commercial20_forbidden_toy_or_proxy_names")
            and not commercial.get("commercial20_cafe_forbidden_toy_or_proxy_names")
        )
        commercial_source_valid = (
            FULL07
            and (
                commercial_all43_24_exact
                if FULL09
                else (
                    commercial.get("pipeline_strategy")
                    == "source-level all43 procedural reconstruction plus all43_19/25 connected commercial additions"
                    if not FULL08
                    else commercial_exact
                )
            )
            and commercial.get("reference_blend") is None
            and len(commercial.get("source_modules", [])) >= (9 if FULL08 else 6)
            and commercial.get("openx_vehicle_instances") == 4
            and not any(
                bpy.data.objects.get(name)
                for name in (
                    "all43_01:car_red",
                    "all43_01:car_blue",
                    "all43_01:car_van",
                    "all43_01:car_silver_variant",
                    "all43_01:tree_0",
                    "all43_01:tree_1",
                    "all43_01:tree_2",
                    "all43_01:tree_3",
                )
            )
        )
        phonebooths = [
            o for o in bpy.context.scene.objects if o.get("c2w_phonebooth_role")
        ]
        phonebooth_on_road = [
            o.name
            for o in phonebooths
            if abs(o.location.x) < 5.2 or abs(o.location.y) < 5.2
        ]
        phonebooths_in_commercial = [
            o.name
            for o in phonebooths
            if o.get("c2w_phonebooth_role") == "commercial_shopping_zone"
            and -50.5 <= o.location.x <= -9.5
            and -46 <= o.location.y <= -7
        ]
        green_plant_materials = {
            m.name
            for m in bpy.data.materials
            if m.name
            in {
                "a8_grass_park_emerald",
                "a8_grass_park_pale_full06",
                "shader_grass_texture_original",
                "all44_10:MAT_DESATURATED_GRASS_BLADES",
            }
        }
        isolated_prefixes = (
            "pk_ush",
            "pfp",
            "st_e",
            "st_w",
            "nt_e",
            "nt_w",
            "et_n",
            "et_s",
            "wt_n",
            "wt_s",
            "ysh_",
            "full03:leisure_belt4_shrub_",
        )
        forbidden_isolated_shrubs = [
            o.name
            for o in bpy.context.scene.objects
            if not o.hide_render
            and (
                o.name.lower().startswith(isolated_prefixes)
                or (o.name.lower().startswith("fb_") and "_sh" in o.name.lower())
            )
        ]
        flowerbed_layers = [
            o.name
            for o in bpy.context.scene.objects
            if str(o.get("c2w_landscape_role", "")).startswith(
                "road_aligned_flowerbed_"
            )
        ]
        road_aligned_beds = [
            o for o in flowerbed_grounds if o.get("c2w_road_alignment") == "parallel"
        ]
        misaligned_beds = [
            o.name
            for o in road_aligned_beds
            if o.get("c2w_flowerbed_axis") not in {"NS", "EW"}
            or abs(float(o.get("c2w_flowerbed_width", 0.0)) - 2.5) > 1e-4
            or float(o.get("c2w_flowerbed_length", 0.0)) <= 0.0
        ]
        park_path_objects = [
            o
            for o in bpy.context.scene.objects
            if o.name == "pk_ep" or o.name.startswith("ppth_")
        ]
        white_park_path_objects = (
            [
                o.name
                for o in park_path_objects
                if not any(
                    m and m.name == "full06_park_path_warm_paver"
                    for m in o.data.materials
                )
            ]
            if FULL06_LANDSCAPE
            else []
        )
        leisure_grass_instances = [
            o.name
            for o in bpy.context.scene.objects
            if not o.hide_render
            and (
                "varied_lawn_tile" in o.name.lower()
                or "dense_lawn_tile" in o.name.lower()
                or "ornamental_grass" in o.name.lower()
            )
            and 9.5 <= o.location.x <= 48.0
            and -42.0 <= o.location.y <= -9.5
        ]
        barrier_survivors = [
            o.name
            for o in bpy.context.scene.objects
            if o.name.startswith(
                ("a40_fence_front_", "a40_fence_gate_", "a40_fence_pier_-8.6_")
            )
        ]
        extension_stats = full07_revision.get("residential_extension", {})
        third_residential_stats = full07_revision.get("third_residential_district", {})
        extension_crosswalk = extension_stats.get("extended_road_crosswalk", {})
        crosswalk_objects = [
            o
            for o in bpy.context.scene.objects
            if o.get("c2w_marking_type") == "zebra_crosswalk"
        ]
        extension_crosswalk_valid = (
            FULL08
            and len(crosswalk_objects) == 9
            and extension_crosswalk.get("connects_both_sidewalks") is True
            and extension_crosswalk.get("crossing_axis") == "north_south"
            and abs(float(extension_crosswalk.get("crosswalk_center_y", 0)) - 65.5)
            < 1e-4
            and float(extension_crosswalk.get("cross_road_span_m", 0)) >= 8.6
            and all(
                abs(o.location.y - 65.5) < 1e-4
                and float(o.get("c2w_cross_road_span_m", 0)) >= 8.6
                and o.get("c2w_crossing_axis") == "north_south"
                for o in crosswalk_objects
            )
        )
        crossroads_stats = full07_revision.get("crossroads_markings", {})
        crossroads_marking_objects = [
            o
            for o in bpy.context.scene.objects
            if o.get("c2w_marking_type") == "crossroads_centerline"
        ]
        crossroads_markings_valid = (
            FULL08
            and crossroads_stats.get("all_four_arms_have_solid_and_dashed") is True
            and set(crossroads_stats.get("solid_objects_by_arm", {}))
            == {"north", "south", "east", "west"}
            and set(crossroads_stats.get("dashed_objects_by_arm", {}))
            == {"north", "south", "east", "west"}
            and all(
                v == 2
                for v in crossroads_stats.get("solid_objects_by_arm", {}).values()
            )
            and all(
                v >= 5
                for v in crossroads_stats.get("dashed_objects_by_arm", {}).values()
            )
            and all(o.get("c2w_intersection_clear") for o in crossroads_marking_objects)
            and {o.get("c2w_line_style") for o in crossroads_marking_objects}
            == {"double_solid", "dashed"}
        )
        full07_tree_quality = (
            len(tree_masters) >= 5
            and len({c.name for c in tree_masters}) >= 5
            and tree_vertices >= 50000
            and explicit_leaves >= 18000
            and all(count >= 3000 for count in explicit_leaves_by_master.values())
            and all(
                int(c.get("c2w_botanical_branch_count", 0)) >= 300 for c in tree_masters
            )
            and len({c.get("c2w_botanical_crown_form") for c in tree_masters}) >= 5
            and all(c.get("c2w_no_blob_or_topiary_geometry") for c in tree_masters)
            and all(count == 1 for count in visible_bark_objects_by_master.values())
            and all(
                c.get("c2w_internal_treefactory_helpers_excluded") for c in tree_masters
            )
            and all(
                c.get("c2w_internal_treefactory_helpers_removed") for c in tree_masters
            )
            and len([o for o in tree_instances if o.name.startswith("pk_tr")]) >= 8
            and not degenerate_tree_names
        )
        requirement_audit = {
            "all_trees_match_all39_fast5_reference": (
                None
                if FULL07
                else bool(tree_instances)
                and len(tree_masters) == 2
                and explicit_leaves >= 1400
                and not degenerate_tree_names
            ),
            "park_trees_source_generated_complex_and_diverse": full07_tree_quality
            if FULL07
            else None,
            "tree_instances": len(tree_instances),
            "tree_master_collections": [c.name for c in tree_masters],
            "explicit_linked_leaf_objects": explicit_leaves,
            "explicit_genuine_leaffactory_objects_by_master": explicit_leaves_by_master,
            "visible_final_bark_objects_by_master": visible_bark_objects_by_master,
            "internal_treefactory_helpers_excluded": all(
                c.get("c2w_internal_treefactory_helpers_excluded") for c in tree_masters
            ),
            "internal_treefactory_helpers_removed": all(
                c.get("c2w_internal_treefactory_helpers_removed") for c in tree_masters
            ),
            "botanical_branches_by_master": {
                c.name: int(c.get("c2w_botanical_branch_count", 0))
                for c in tree_masters
            },
            "botanical_crown_forms": {
                c.name: c.get("c2w_botanical_crown_form") for c in tree_masters
            },
            "blob_or_topiary_geometry_forbidden": all(
                c.get("c2w_no_blob_or_topiary_geometry") for c in tree_masters
            ),
            "full_detail_nonleaf_tree_vertices": tree_vertices,
            "degenerate_or_blob_tree_objects": degenerate_tree_names,
            "commercial_exact_all43_18_asset_system": commercial_exact
            if not FULL09
            else None,
            "commercial_exact_all43_24_asset_system": commercial_all43_24_exact
            if FULL09
            else None,
            "commercial_source_rebuild_without_reference_blend": commercial_source_valid
            if FULL07
            else None,
            "commercial_all43_18_shared_mesh_signature": mesh_signature
            if FULL08
            else None,
            "roadside_phonebooths_only": bool(phonebooths) and not phonebooth_on_road,
            "phonebooths_on_road": phonebooth_on_road,
            "phonebooths_in_commercial_shopping_zone": phonebooths_in_commercial,
            "summer_green_plant_materials": sorted(green_plant_materials),
            "park_lawn_palette_valid": park_lawn_palette_valid,
            "park_lawn_color_ramp": park_colors,
            "nonpark_layered_flowerbed_grounds": len(flowerbed_grounds),
            "flat_green_nonpark_ground_objects": flat_green_nonpark,
            "leisure_layered_flowerbed_shrubs": leisure.get(
                "verified_belt4_style_shrub_instances", 0
            ),
            "forbidden_isolated_shrub_objects": forbidden_isolated_shrubs,
            "road_aligned_flowerbed_grounds": len(road_aligned_beds),
            "road_aligned_flowerbed_total_length": round(
                sum(
                    float(o.get("c2w_flowerbed_length", 0.0)) for o in road_aligned_beds
                ),
                3,
            ),
            "road_aligned_flowerbed_misaligned": misaligned_beds,
            "belt4_scatter_layers": flowerbed_layers,
            "belt4_scatter_surface_faces": int(
                bpy.context.scene.get("c2w_full06_flowerbed_surface_faces", 0)
            ),
            "park_path_material": "full06_park_path_warm_paver"
            if FULL06_LANDSCAPE
            else "stone_path",
            "park_ground_white_strip_objects": white_park_path_objects,
            "leisure_grass_instances": leisure_grass_instances,
            "leisure_zone_grass_free": FULL07
            and leisure.get("grass_free_leisure_zone")
            and not leisure_grass_instances,
            "residential_road_barrier_survivors": barrier_survivors,
            "residential_road_barrier_removed": FULL07 and not barrier_survivors,
            "extended_residential_district": extension_stats,
            "extended_residential_district_valid": (
                FULL07
                and extension_stats.get("detached_houses") == 3
                and extension_stats.get("apartment_buildings") == 2
                and extension_stats.get("connected_path_segments", 0) >= 9
                and extension_stats.get("street_extension_length_m", 0) >= 100
                and not extension_stats.get("reference_blends_loaded")
            ),
            "third_residential_all45_09_source_rebuild": (
                None
                if not FULL09
                else bool(
                    third_residential_stats.get("valid")
                    and third_residential_stats.get("reference_revision")
                    == "urban_v3_all45_09"
                    and third_residential_stats.get("source_level_generation")
                    and not third_residential_stats.get(
                        "completed_residential_blends_loaded"
                    )
                    and not third_residential_stats.get("reference_blends_loaded")
                    and third_residential_stats.get("building_count") == 11
                    and third_residential_stats.get("lowrise_count") == 3
                    and third_residential_stats.get("highrise_count") == 8
                    and third_residential_stats.get("river_reserve_clearance_m", 0)
                    >= 3.0
                    and third_residential_stats.get("connected_street_system", {}).get(
                        "valid"
                    )
                    and third_residential_stats.get("connected_street_system", {}).get(
                        "third_district_zebra_stripes"
                    )
                    == 9
                    and third_residential_stats.get("connected_street_system", {}).get(
                        "third_district_zebra_span_m", 0
                    )
                    >= 10.5
                    and third_residential_stats.get("connected_street_system", {}).get(
                        "new_street_center_dashes", 0
                    )
                    >= 12
                    and third_residential_stats.get("no_toy_or_degenerate_models")
                )
            ),
            "third_residential_district": third_residential_stats if FULL09 else None,
            "leisure_exact_all44_13_source_plan": (
                None
                if not FULL09
                else bool(
                    leisure.get("source_revision") == "urban_v3_all44_13"
                    and not leisure.get("reference_blends_loaded")
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("pipeline_stage")
                    == "generate_urban_v3_all44_13.py"
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("source_level_integration")
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("athletics_ground_present")
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("gymnasium_present")
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("retained_basketball_court_objects", 0)
                    >= 20
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("retained_playground_objects", 0)
                    >= 8
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("southward_expansion_m", 0)
                    >= 43.0
                    and leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("east_west_expansion_m")
                    == 0.0
                    and not leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("forbidden_degenerate_asset_names")
                    and not leisure.get(
                        "integrated_basketball_athletics_gymnasium_precinct", {}
                    ).get("collapsed_new_meshes")
                )
            ),
            "extended_residential_crosswalk_connects_both_road_sides": extension_crosswalk_valid
            if FULL08
            else None,
            "extended_residential_crosswalk_geometry": extension_crosswalk
            if FULL08
            else None,
            "crossroads_solid_and_dashed_markings_complete": crossroads_markings_valid
            if FULL08
            else None,
            "crossroads_marking_geometry": crossroads_stats if FULL08 else None,
            "no_toy_or_degenerate_models": not degenerate_tree_names,
        }
        if FULL09:
            # FULL09 intentionally preserves the FULL07 park as authored and
            # pins its upgraded regional sources to ALL43-24/ALL44-13.  The
            # older FULL03/FULL06 palette, shrub-removal and warm-paver rules
            # describe different requested revisions and must not rewrite the
            # retained park or reject detailed shrubs in the new source zones.
            core_checks = [
                "park_trees_source_generated_complex_and_diverse",
                "commercial_source_rebuild_without_reference_blend",
                "commercial_exact_all43_24_asset_system",
                "roadside_phonebooths_only",
                "extended_residential_crosswalk_connects_both_road_sides",
                "crossroads_solid_and_dashed_markings_complete",
                "third_residential_all45_09_source_rebuild",
                "leisure_exact_all44_13_source_plan",
                "no_toy_or_degenerate_models",
            ]
        else:
            core_checks = [
                "park_lawn_palette_valid",
                "roadside_phonebooths_only",
                "no_toy_or_degenerate_models",
            ]
            core_checks.extend(
                (
                    [
                        "park_trees_source_generated_complex_and_diverse",
                        "commercial_source_rebuild_without_reference_blend",
                        "commercial_exact_all43_18_asset_system",
                        "extended_residential_crosswalk_connects_both_road_sides",
                        "crossroads_solid_and_dashed_markings_complete",
                    ]
                    if FULL08
                    else [
                        "park_trees_source_generated_complex_and_diverse",
                        "commercial_source_rebuild_without_reference_blend",
                    ]
                )
                if FULL07
                else [
                    "all_trees_match_all39_fast5_reference",
                    "commercial_exact_all43_18_asset_system",
                ]
            )
        failed = [key for key in core_checks if not requirement_audit[key]]
        if FULL06_LANDSCAPE and not FULL09:
            if forbidden_isolated_shrubs:
                failed.append("all_isolated_road_and_park_shrubs_removed")
            if len(road_aligned_beds) != 19 or misaligned_beds:
                failed.append("flowerbeds_follow_road_layout_and_dimensions")
            if (
                len(flowerbed_layers) < 3
                or int(bpy.context.scene.get("c2w_full06_flowerbed_surface_faces", 0))
                < 1000
            ):
                failed.append("belt4_dense_grass_and_flower_layers")
            if white_park_path_objects or len(park_path_objects) != 4:
                failed.append("park_white_ground_strips_recolored")
            if leisure.get("verified_belt4_style_shrub_instances", 0) != 0:
                failed.append("leisure_isolated_shrubs_removed")
        if FULL07:
            if not requirement_audit["leisure_zone_grass_free"]:
                failed.append("leisure_zone_grass_free")
            if len(phonebooths) != 1 or len(phonebooths_in_commercial) != 1:
                failed.append("phonebooth_relocated_to_commercial_shopping_zone")
            if not requirement_audit["residential_road_barrier_removed"]:
                failed.append("residential_road_barrier_removed")
            if not requirement_audit["extended_residential_district_valid"]:
                failed.append("extended_residential_district_valid")
        elif (
            len(flowerbed_grounds) < 10
            or flat_green_nonpark
            or leisure.get("verified_belt4_style_shrub_instances", 0) < 10
        ):
            failed.append("nonpark_green_ground_replaced_by_layered_flowerbeds")
        if failed:
            raise RuntimeError(
                f"full03 requirement audit failed: {failed}; details={requirement_audit}"
            )
    # The revision may contain a subdirectory (for example full_03/demo1).
    scene_path = OUT / f"{Path(OUTPUT_REVISION).name}.blend"
    # The final post-render save overwrites this checkpoint.  Suppress a second
    # multi-gigabyte .blend1 copy, while keeping the checkpoint itself.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.scene["c2w_generator"] = os.environ.get(
        "C2W_GENERATOR_ENTRY", str(Path(__file__).resolve())
    )
    bpy.context.scene["c2w_revision"] = OUTPUT_REVISION
    bpy.context.scene["c2w_base_revision"] = REVISION
    bpy.context.scene["c2w_variant"] = VARIANT
    bpy.context.scene["c2w_seed"] = SEED
    bpy.context.scene["c2w_variant_profile"] = json.dumps(PROFILE, sort_keys=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), compress=True)
    render_validation(cameras)
    forbidden = ("toy", "placeholder", "dummy", "lowpoly", "primitive_car")
    toy_objects = [
        o.name
        for o in bpy.context.scene.objects
        if not o.hide_render and any(k in o.name.lower() for k in forbidden)
    ]
    forbidden_masters = [
        c.name
        for c in bpy.data.collections
        if c.name
        in {
            "all43_01:MASTER:sedan",
            "all43_01:MASTER:suv",
            "all43_01:MASTER:van",
            "all43_01:MASTER:tree",
        }
    ]
    openx_instances = [
        o
        for o in bpy.context.scene.objects
        if o.instance_type == "COLLECTION"
        and (o.name.startswith("vehicle:") or o.name.startswith("all43_02:vehicle:"))
    ]
    treefactory_masters = [
        c
        for c in bpy.data.collections
        if (
            "generic_treefactory" in c.name.lower()
            or "master:treefactory:" in c.name.lower()
            or c.name.startswith("All39Fast5_TreePrototype_")
        )
        and sum(
            len(o.data.vertices) for o in c.all_objects if o.type == "MESH" and o.data
        )
        >= 10000
    ]
    realistic_tree_instances = [
        o
        for o in bpy.context.scene.objects
        if o.get("c2w_real_world_tree_height_m")
        and 5.0 <= float(o["c2w_real_world_tree_height_m"]) <= 8.0
    ]
    quality_errors = []
    if toy_objects:
        quality_errors.append("forbidden names: " + str(toy_objects[:30]))
    if forbidden_masters:
        quality_errors.append(
            "coarse commercial masters exist: " + str(forbidden_masters)
        )
    if PARAMETRIC_PRODUCTION and len(openx_instances) != 4:
        quality_errors.append(
            f"expected 4 OpenX vehicle instances, got {len(openx_instances)}"
        )
    if PARAMETRIC_PRODUCTION and not treefactory_masters:
        quality_errors.append("no verified high-detail explicit-leaf tree master found")
    if PARAMETRIC_PRODUCTION and len(realistic_tree_instances) < 15:
        quality_errors.append(
            f"expected at least 15 realistically scaled high-detail trees, got {len(realistic_tree_instances)}"
        )
    if FULL07 and len(treefactory_masters) < 5:
        quality_errors.append(
            f"expected five source-generated high-detail TreeFactory masters, got {len(treefactory_masters)}"
        )
    if ADD_RIVER and not full07_revision.get("river", {}).get("valid"):
        quality_errors.append("river corridor source-generation audit did not pass")
    if quality_errors:
        raise RuntimeError("asset quality audit failed: " + "; ".join(quality_errors))
    report = {
        "seed": SEED,
        "variant": VARIANT,
        "output": str(scene_path),
        "variant_profile": PROFILE,
        "layout_mode": PROFILE.get("layout", "crossroads"),
        "source_level_generation": True,
        "old_regional_blends_loaded": False,
        "generator_entry": bpy.context.scene["c2w_generator"],
        "real_generator_chain": (
            (
                [
                    (
                        "generate_urban_v1_full_09.py"
                        if FULL09
                        else (
                            "generate_urban_v1_full_08.py"
                            if FULL08
                            else "generate_urban_v1_full_07.py"
                        )
                    ),
                    "generate_urban_v3_all41.py",
                    "generate_urban_v3_all30.py",
                    "urban_v1_full_07_trees.py: five multilevel botanical masters with same-run genuine Infinigen LeafFactory merged crowns",
                    (
                        "all43_18 base reconstruction + all43_19 corner 7-Eleven + active all43_24 McDonald's/collision-audited cafe connected inverse-L pass"
                        if FULL09
                        else (
                            "all43_18 base reconstruction + all43_19 corner 7-Eleven + active all43_25 McDonald's/cafe/two-reference-bar connected inverse-L pass"
                            if FULL08
                            else "source-level all43 reconstruction + all43_19/25 connected commercial passes"
                        )
                    ),
                    (
                        "generate_urban_v3_all44_13.py south-planned basketball/playground + gymnasium + athletics ground"
                        if FULL09
                        else "generate_urban_v3_all44_14.py east-west integrated basketball/playground + athletics ground + oval gymnasium"
                    ),
                    "urban_v1_full_07_extension.py",
                    *(
                        [
                            "urban_v1_full_09_residential.py -> generate_urban_v3_all45_03.py source functions: three low-rise + eight high-rise district and connected streets"
                        ]
                        if FULL09
                        else []
                    ),
                    *(
                        [
                            "urban_v1_full_07_river.py + genuine Infinigen RiverWater/Grass recessed-bank river3 pipeline (reeds removed)"
                        ]
                        if ADD_RIVER
                        else []
                    ),
                ]
                if FULL07
                else [
                    "generate_urban_v1_full_06.py"
                    if FULL06_LANDSCAPE
                    else Path(__file__).name,
                    "generate_urban_v3_all41.py",
                    "generate_urban_v3_all30.py",
                    "urban_v3_all39_fast5 verified vegetation asset library",
                    "urban_v3_all43_18 exact commercial asset system",
                    "generate_urban_v3_all44_14.py east-west integrated basketball/playground + athletics ground + oval gymnasium",
                ]
            )
            if STRICT_FULL03
            else [
                "generate_urban_v3_all41.py",
                "generate_urban_v3_all30.py",
                "urban_v3_all39_fast5 verified explicit-leaf vegetation masters",
                "generate_urban_v3_all43_01.py",
                "commercial_rebuild_generator_15.py",
                "generate_urban_v3_all44_14.py east-west integrated basketball/playground + athletics ground + oval gymnasium",
            ]
        ),
        "toy_model_audit": {
            "valid": True,
            "forbidden_object_count": 0,
            "forbidden_coarse_master_count": 0,
            "openx_vehicle_instances": len(openx_instances),
            "high_detail_treefactory_masters": len(treefactory_masters),
            "realistically_scaled_high_detail_tree_instances": len(
                realistic_tree_instances
            ),
            "policy": "reject toy assets; never create coarse commercial car/tree masters",
        },
        "global": {
            "ground_z": 0.0,
            "road_half_width": 4.5,
            "sidewalk_width": 3.5,
            "protected_setback": 10.5,
        },
        "commercial": commercial,
        "leisure": leisure,
        "full07_revision": full07_revision,
        "layout_plan": layout_plan,
        "road_marking_objects": len(road_markings),
        "streetlight_objects": len(streetlights),
        "requirement_audit": requirement_audit,
        "renders": [name for _, name in cameras],
        "elapsed_seconds": round(time.time() - started, 2),
    }
    (OUT / "generation_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), compress=True)
    log("Integration", f"Complete scene saved: {scene_path}")


if __name__ == "__main__":
    main()
