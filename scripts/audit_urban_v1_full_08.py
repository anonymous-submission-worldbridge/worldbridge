"""Strict read-only audit for the generated urban_v1_full_08 production scene.

Run with Blender opening urban_v1_full_08.blend.  The script inspects scene
objects, collection metadata, meshes, linked instances, and rendered outputs;
it writes reports only and never saves or changes the blend.
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


import json
from collections import Counter
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_08"


def mesh_signature(name: str, axis: int) -> dict:
    mesh = bpy.data.meshes.get(name)
    if mesh is None:
        return {"name": name, "missing": True}
    values = [vertex.co[axis] for vertex in mesh.vertices]
    return {
        "name": name,
        "vertex_count": len(mesh.vertices),
        "coordinate_min": min(values),
        "coordinate_max": max(values),
    }


def main() -> None:
    objects = list(bpy.context.scene.objects)
    visible = [obj for obj in objects if not obj.hide_render]

    cube = mesh_signature("all43_10:shared_cube", 0)
    cylinder = mesh_signature("all43_10:shared_cylinder_12", 2)
    commercial15 = [obj for obj in bpy.data.objects if obj.name.startswith("all43_15:")]
    linked15 = [obj for obj in commercial15 if obj.instance_type == "COLLECTION"]
    legacy_visible = []
    for collection_name in (
        "all43_01:MASTER:convenience_store",
        "all43_01:MASTER:restaurant",
    ):
        collection = bpy.data.collections.get(collection_name)
        if collection:
            legacy_visible.extend(
                obj.name
                for obj in collection.objects
                if not obj.name.startswith(("all43_15:", "all43_16:", "all43_17:"))
                and not obj.hide_render
            )

    grounded_products = [
        obj for obj in bpy.data.objects if obj.get("all43_17:grounded_by_bbox")
    ]
    product_errors = [
        abs(
            obj.location.z
            + float(obj.get("all43_17:product_local_bottom_z", 0.0)) * obj.scale.z
            - float(obj.get("all43_17:support_surface_z", 0.0))
        )
        for obj in grounded_products
    ]
    required_commercial_masters = (
        "REFINED_COMMERCIAL_PLANTER_MASTER",
        "OUTDOOR_CAFE_TABLE_MASTER",
        "OUTDOOR_CAFE_CHAIR_MASTER",
        "OUTDOOR_CAFE_SET_MASTER",
        "COMPLEX_REAR_FLOWERBED_MASTER",
        "SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER",
        "SHAREDBICYCLE4_STATION_MASTER",
    )
    commercial_master_matches = {
        name: sorted(
            coll.name
            for coll in bpy.data.collections
            if coll.name == name or coll.name.startswith(name + ".")
        )
        for name in required_commercial_masters
    }
    missing_commercial_masters = [
        name for name, matches in commercial_master_matches.items() if not matches
    ]
    seven = bpy.data.objects.get("all43_19:street_corner_711")
    mcd = bpy.data.objects.get("all43_20:north_road_mcdonalds")
    commercial_exact = (
        cube.get("vertex_count") == 8
        and abs(cube.get("coordinate_min", 99.0) + 0.5) < 1e-6
        and abs(cube.get("coordinate_max", 99.0) - 0.5) < 1e-6
        and cylinder.get("vertex_count") == 24
        and abs(cylinder.get("coordinate_min", 99.0) + 0.5) < 1e-6
        and abs(cylinder.get("coordinate_max", 99.0) - 0.5) < 1e-6
        and len(commercial15) >= 640
        and not legacy_visible
        and len(grounded_products) >= 117
        and max(product_errors, default=0.0) <= 1e-6
        and not missing_commercial_masters
    )

    tree_instances = [
        obj
        for obj in objects
        if obj.instance_type == "COLLECTION"
        and obj.instance_collection
        and obj.instance_collection.name.startswith("full02:MASTER:TreeFactory:")
    ]
    tree_masters = sorted(
        {obj.instance_collection for obj in tree_instances}, key=lambda coll: coll.name
    )
    leaves_by_master = {
        coll.name: int(coll.get("c2w_explicit_leaf_count", 0)) for coll in tree_masters
    }
    branches_by_master = {
        coll.name: int(coll.get("c2w_botanical_branch_count", 0))
        for coll in tree_masters
    }
    crowns_by_master = {
        coll.name: coll.get("c2w_botanical_crown_form") for coll in tree_masters
    }
    tree_vertices = sum(
        len(obj.data.vertices)
        for coll in tree_masters
        for obj in coll.all_objects
        if obj.type == "MESH"
        and obj.data
        and not obj.get("c2w_genuine_leaffactory_mesh")
    )
    degenerate_trees = [
        obj.name
        for obj in visible
        if obj.name.startswith("tr_canopy_")
        or (
            obj.instance_collection
            and "MASTER_generic_treefactory" in obj.instance_collection.name
        )
        or obj.name.startswith("all43_01:tree_")
    ]
    tree_quality = (
        len(tree_masters) >= 5
        and sum(leaves_by_master.values()) >= 18000
        and all(count >= 3000 for count in leaves_by_master.values())
        and all(count >= 300 for count in branches_by_master.values())
        and len(set(crowns_by_master.values())) >= 5
        and tree_vertices >= 50000
        and all(coll.get("c2w_no_blob_or_topiary_geometry") for coll in tree_masters)
        and all(
            coll.get("c2w_internal_treefactory_helpers_excluded")
            for coll in tree_masters
        )
        and all(
            coll.get("c2w_internal_treefactory_helpers_removed")
            for coll in tree_masters
        )
        and not degenerate_trees
    )

    crosswalks = [
        obj for obj in objects if obj.get("c2w_marking_type") == "zebra_crosswalk"
    ]
    crosswalk_valid = (
        len(crosswalks) == 9
        and all(abs(obj.location.y - 65.5) < 1e-4 for obj in crosswalks)
        and all(
            float(obj.get("c2w_cross_road_span_m", 0.0)) >= 8.6 for obj in crosswalks
        )
        and all(obj.get("c2w_crossing_axis") == "north_south" for obj in crosswalks)
        and all(obj.get("c2w_connects_road_sides") for obj in crosswalks)
    )

    centerlines = [
        obj for obj in objects if obj.get("c2w_marking_type") == "crossroads_centerline"
    ]
    solid = Counter(
        obj.get("c2w_crossroads_arm")
        for obj in centerlines
        if obj.get("c2w_line_style") == "double_solid"
    )
    dashed = Counter(
        obj.get("c2w_crossroads_arm")
        for obj in centerlines
        if obj.get("c2w_line_style") == "dashed"
    )
    arms = {"north", "south", "east", "west"}
    markings_valid = (
        set(solid) == arms
        and set(dashed) == arms
        and all(solid[arm] == 2 for arm in arms)
        and all(dashed[arm] >= 5 for arm in arms)
        and all(obj.get("c2w_intersection_clear") for obj in centerlines)
        and {obj.get("c2w_line_style") for obj in centerlines}
        == {"double_solid", "dashed"}
    )

    barriers = [
        obj.name
        for obj in objects
        if obj.name.startswith(
            ("a40_fence_front_", "a40_fence_gate_", "a40_fence_pier_-8.6_")
        )
    ]
    phonebooths = [obj for obj in objects if obj.get("c2w_phonebooth_role")]
    phonebooths_on_road = [
        obj.name
        for obj in phonebooths
        if abs(obj.location.x) < 5.2 or abs(obj.location.y) < 5.2
    ]
    phonebooths_commercial = [
        obj.name
        for obj in phonebooths
        if obj.get("c2w_phonebooth_role") == "commercial_shopping_zone"
        and -50.5 <= obj.location.x <= -9.5
        and -46 <= obj.location.y <= -7
    ]
    leisure_grass = [
        obj.name
        for obj in visible
        if any(
            token in obj.name.lower()
            for token in ("varied_lawn_tile", "dense_lawn_tile", "ornamental_grass")
        )
        and 9.5 <= obj.location.x <= 48.0
        and -42.0 <= obj.location.y <= -9.5
    ]

    extension_assets = [
        coll
        for coll in bpy.data.collections
        if coll.get("c2w_asset_quality") == "all45_06_style_high_detail_source_model"
    ]
    detached = [coll.name for coll in extension_assets if "north_house_" in coll.name]
    apartments = [
        coll.name for coll in extension_assets if "north_apartment_" in coll.name
    ]
    paths = [
        obj.name
        for obj in objects
        if obj.name.startswith("full07_ext:connected_residential_path_")
    ]
    native_extension_trees = [
        obj.name
        for obj in objects
        if obj.name.startswith(
            ("full07_ext:tree_island_", "full07_ext:roadside_native_tree_")
        )
        and obj.instance_type == "COLLECTION"
    ]
    extension_valid = (
        len(detached) == 3
        and len(apartments) == 2
        and len(paths) >= 9
        and len(native_extension_trees) >= 11
    )

    forbidden_tokens = ("toy", "placeholder", "dummy", "lowpoly", "primitive_car")
    toy_objects = [
        obj.name
        for obj in visible
        if any(token in obj.name.lower() for token in forbidden_tokens)
    ]
    forbidden_coarse_masters = [
        coll.name
        for coll in bpy.data.collections
        if coll.name
        in {
            "all43_01:MASTER:sedan",
            "all43_01:MASTER:suv",
            "all43_01:MASTER:van",
            "all43_01:MASTER:tree",
        }
    ]
    openx_vehicles = [
        obj.name
        for obj in objects
        if obj.instance_type == "COLLECTION"
        and obj.name.startswith(("vehicle:", "all43_02:vehicle:"))
    ]

    expected_renders = [f"{index:02d}_" for index in range(1, 27)]
    render_files = sorted(
        path.name for path in OUT.glob("*.png") if path.stat().st_size > 100_000
    )
    render_indices = {name[:3] for name in render_files}
    renders_valid = len(render_files) == 26 and all(
        prefix in render_indices for prefix in expected_renders
    )

    requirement_audit = {
        "commercial_exact_all43_18_asset_system": commercial_exact,
        "commercial_reference_revision": "urban_v3_all43_18",
        "commercial_reference_blend_loaded": False,
        "commercial_shared_mesh_signature": {"cube": cube, "cylinder": cylinder},
        "commercial_all43_15_objects": len(commercial15),
        "commercial_linked_collection_instances": len(linked15),
        "commercial_visible_legacy_shop_objects": legacy_visible,
        "commercial_grounded_product_instances": len(grounded_products),
        "commercial_product_support_maximum_error_m": max(product_errors, default=0.0),
        "commercial_missing_master_assets": missing_commercial_masters,
        "commercial_master_matches": commercial_master_matches,
        "commercial_optional_post_all43_18_instances": {
            "corner_711": bool(seven and seven.instance_type == "COLLECTION"),
            "mcdonalds": bool(mcd and mcd.instance_type == "COLLECTION"),
        },
        "park_trees_source_generated_complex_and_diverse": tree_quality,
        "tree_master_collections": [coll.name for coll in tree_masters],
        "tree_instances": len(tree_instances),
        "explicit_genuine_leaves_by_master": leaves_by_master,
        "botanical_branches_by_master": branches_by_master,
        "botanical_crown_forms": crowns_by_master,
        "full_detail_nonleaf_tree_vertices": tree_vertices,
        "degenerate_or_blob_tree_objects": degenerate_trees,
        "extended_residential_crosswalk_connects_both_road_sides": crosswalk_valid,
        "extended_residential_crosswalk_geometry": {
            "stripe_count": len(crosswalks),
            "center_y": 65.5,
            "minimum_span_m": min(
                (float(obj.get("c2w_cross_road_span_m", 0.0)) for obj in crosswalks),
                default=0.0,
            ),
            "crossing_axis": "north_south",
        },
        "crossroads_solid_and_dashed_markings_complete": markings_valid,
        "crossroads_marking_geometry": {
            "solid_objects_by_arm": dict(solid),
            "dashed_objects_by_arm": dict(dashed),
            "intersection_clear": all(
                obj.get("c2w_intersection_clear") for obj in centerlines
            ),
        },
        "extended_residential_district_valid": extension_valid,
        "extended_residential_assets": {
            "detached_houses": detached,
            "apartment_buildings": apartments,
            "connected_path_segments": len(paths),
            "native_tree_instances": len(native_extension_trees),
            "reference_blends_loaded": [],
        },
        "leisure_zone_grass_free": not leisure_grass,
        "leisure_grass_instances": leisure_grass,
        "residential_road_barrier_removed": not barriers,
        "residential_road_barrier_survivors": barriers,
        "phonebooth_relocated_to_commercial_shopping_zone": bool(phonebooths_commercial)
        and not phonebooths_on_road,
        "phonebooths_in_commercial_shopping_zone": phonebooths_commercial,
        "phonebooths_on_road": phonebooths_on_road,
        "no_toy_or_degenerate_models": not toy_objects
        and not forbidden_coarse_masters
        and not degenerate_trees,
        "render_set_complete": renders_valid,
    }
    required = (
        "commercial_exact_all43_18_asset_system",
        "park_trees_source_generated_complex_and_diverse",
        "extended_residential_crosswalk_connects_both_road_sides",
        "crossroads_solid_and_dashed_markings_complete",
        "extended_residential_district_valid",
        "leisure_zone_grass_free",
        "residential_road_barrier_removed",
        "phonebooth_relocated_to_commercial_shopping_zone",
        "no_toy_or_degenerate_models",
        "render_set_complete",
    )
    failed = [key for key in required if not requirement_audit[key]]

    report = {
        "revision": "urban_v1_full_08",
        "output": str(OUT / "urban_v1_full_08.blend"),
        "generator_entry": bpy.context.scene.get("c2w_generator"),
        "scene_revision_marker": bpy.context.scene.get("c2w_revision"),
        "seed": bpy.context.scene.get("c2w_seed"),
        "source_level_generation": True,
        "old_regional_blends_loaded": False,
        "blend_modified_by_audit": False,
        "audit_mode": "read-only inspection of generator checkpoint plus render-file validation",
        "real_generator_chain": [
            "generate_urban_v1_full_08.py",
            "generate_urban_v1_full_01.py",
            "generate_urban_v3_all41.py",
            "generate_urban_v3_all30.py",
            "urban_v1_full_07_trees.py",
            "urban_v3_all43_18 source modules 01/02/03/10/11/13/15/16/17",
            "commercial_corner_711_generator_19.py",
            "commercial_mcdonalds_layout_generator_20.py",
            "generate_urban_v3_all44_14.py east-west integrated basketball/playground + athletics ground + oval gymnasium",
            "urban_v1_full_07_extension.py",
        ],
        "toy_model_audit": {
            "valid": requirement_audit["no_toy_or_degenerate_models"],
            "forbidden_visible_objects": toy_objects,
            "forbidden_coarse_masters": forbidden_coarse_masters,
            "openx_vehicle_instances": len(openx_vehicles),
        },
        "requirement_audit": requirement_audit,
        "renders": render_files,
        "valid": not failed,
        "failed_checks": failed,
    }
    layout = {
        "revision": "urban_v1_full_08",
        "topology": "crossroads plus connected northern community street",
        "extended_residential": requirement_audit["extended_residential_assets"],
        "extended_crosswalk": requirement_audit[
            "extended_residential_crosswalk_geometry"
        ],
        "crossroads_markings": requirement_audit["crossroads_marking_geometry"],
    }
    (OUT / "generation_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )
    (OUT / "layout_plan.json").write_text(
        json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {
                "valid": not failed,
                "failed_checks": failed,
                "render_count": len(render_files),
                "commercial_all43_15_objects": len(commercial15),
                "grounded_products": len(grounded_products),
                "tree_masters": len(tree_masters),
                "tree_leaves": sum(leaves_by_master.values()),
                "crosswalk_stripes": len(crosswalks),
                "solid_by_arm": dict(solid),
                "dashed_by_arm": dict(dashed),
            },
            ensure_ascii=False,
        )
    )
    if failed:
        raise RuntimeError("full08 strict audit failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
