"""Strict read-only completion audit for ``urban_v1_full_09``.

Run with Blender opening the generated scene.  The script inspects generator
metadata, reachable render geometry, all five requested program areas, road
markings, camera coverage and render files.  It writes JSON only and never
saves or modifies the Blend.
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
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_09"
REPORT = OUT / "generation_audit.json"
FINAL = OUT / "strict_completion_audit.json"


def _reachable_render_objects() -> set[bpy.types.Object]:
    objects: set[bpy.types.Object] = set()
    visited: set[bpy.types.Collection] = set()

    def visit(collection: bpy.types.Collection) -> None:
        if collection in visited:
            return
        visited.add(collection)
        for obj in collection.objects:
            if obj.hide_render:
                continue
            objects.add(obj)
            if obj.instance_type == "COLLECTION" and obj.instance_collection:
                visit(obj.instance_collection)
        for child in collection.children:
            visit(child)

    visit(bpy.context.scene.collection)
    return objects


def _mesh_is_authored(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH" or not obj.data:
        return True
    procedural_render_host = bool(
        any(
            modifier.type == "NODES" and modifier.show_render
            for modifier in obj.modifiers
        )
        or obj.get("c2w_direct_infinigen_asset")
    )
    if len(obj.data.vertices) == 0:
        return procedural_render_host
    extents = []
    for axis in range(3):
        values = [vertex.co[axis] for vertex in obj.data.vertices]
        extents.append(max(values) - min(values))
    # Infinigen's Geometry Nodes scatters intentionally use a zero- or
    # one-vertex carrier mesh.  The carrier is not the visible asset: its
    # enabled nodes modifier emits the authored vegetation geometry at render
    # time.  Treat it as valid procedural geometry while continuing to reject
    # collapsed ordinary meshes.
    return sum(value > 1e-7 for value in extents) >= 2 or procedural_render_host


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf8"))
    reachable = _reachable_render_objects()
    scene_objects = list(bpy.context.scene.objects)

    third_root = next(
        (
            collection
            for collection in bpy.data.collections
            if collection.name.startswith(
                "full09_res:third_residential_all45_09_source_rebuild"
            )
        ),
        None,
    )
    third = (
        json.loads(third_root.get("c2w_full09_residential_audit", "{}"))
        if third_root
        else {}
    )
    leisure = report.get("leisure", {})
    leisure_audit = leisure.get(
        "integrated_basketball_athletics_gymnasium_precinct", {}
    )
    commercial = report.get("commercial", {})
    extension = report.get("full07_revision", {}).get("residential_extension", {})
    river = report.get("full07_revision", {}).get("river", {})

    base_residential_objects = [
        obj
        for obj in scene_objects
        if obj.name.startswith(("a40_", "a41_")) and not obj.hide_render
    ]
    second_residential_assets = [
        collection
        for collection in bpy.data.collections
        if collection.get("c2w_asset_quality")
        == "all45_06_style_high_detail_source_model"
    ]
    third_lowrise = [
        collection
        for collection in bpy.data.collections
        if collection.name.startswith("full09_res:detached_townhouse_")
        and collection.get("building_type") == "all45_09_native_scale_lowrise_exterior"
    ]
    third_highrise = [
        collection
        for collection in bpy.data.collections
        if collection.name.startswith("full09_res:highrise_tower_")
        and collection.get("building_type") == "highrise_shell_no_interior"
    ]

    inherited_zebra = [
        obj for obj in scene_objects if obj.get("c2w_marking_type") == "zebra_crosswalk"
    ]
    third_zebra = [
        obj
        for obj in scene_objects
        if obj.get("c2w_marking_type") == "full09_zebra_crosswalk"
    ]
    crossroads_lines = [
        obj
        for obj in scene_objects
        if obj.get("c2w_marking_type") == "crossroads_centerline"
    ]
    solid = Counter(
        obj.get("c2w_crossroads_arm")
        for obj in crossroads_lines
        if obj.get("c2w_line_style") == "double_solid"
    )
    dashed = Counter(
        obj.get("c2w_crossroads_arm")
        for obj in crossroads_lines
        if obj.get("c2w_line_style") == "dashed"
    )
    third_centerline = [
        obj
        for obj in scene_objects
        if obj.get("c2w_marking_type") == "full09_centerline"
    ]
    directions = [
        obj for obj in scene_objects if obj.get("c2w_marking_type") == "direction_arrow"
    ]

    cameras = sorted(
        obj.name.removeprefix("full:")
        for obj in bpy.data.objects
        if obj.type == "CAMERA"
        and obj.name.startswith("full:")
        and obj.name.endswith(".png")
    )
    expected_indices = {f"{index:02d}" for index in range(1, 42)}
    camera_indices = {name[:2] for name in cameras}
    render_files = {
        path.name: path.stat().st_size
        for path in OUT.glob("*.png")
        if path.stat().st_size > 100_000
    }

    forbidden_tokens = (
        "toy",
        "placeholder",
        "proxy",
        "dummy",
        "lowpoly",
        "low_poly",
        "primitive_car",
    )
    forbidden_reachable = sorted(
        obj.name
        for obj in reachable
        if any(token in obj.name.lower() for token in forbidden_tokens)
    )
    collapsed_reachable = sorted(
        obj.name for obj in reachable if not _mesh_is_authored(obj)
    )
    coarse_masters = sorted(
        collection.name
        for collection in bpy.data.collections
        if collection.name
        in {
            "all43_01:MASTER:sedan",
            "all43_01:MASTER:suv",
            "all43_01:MASTER:van",
            "all43_01:MASTER:tree",
        }
    )

    tree_masters = sorted(
        [
            collection
            for collection in bpy.data.collections
            if collection.name.startswith("full02:MASTER:TreeFactory:")
        ],
        key=lambda collection: collection.name,
    )
    park_trees = [
        obj
        for obj in scene_objects
        if obj.name.startswith("pk_tr") and obj.instance_collection in tree_masters
    ]
    park_paths = [
        obj
        for obj in scene_objects
        if obj.name == "pk_ep" or obj.name.startswith("ppth_")
    ]

    checks = {
        "generator_entry_is_full09": report.get("generator_entry")
        == str(ROOT / "scripts/generate_urban_v1_full_09.py"),
        "scene_revision_is_full09": bpy.context.scene.get("c2w_revision")
        == "urban_v1_full_09",
        "clean_source_level_generation": bool(
            report.get("source_level_generation")
            and not report.get("old_regional_blends_loaded")
        ),
        "commercial_all43_24_source_exact": bool(
            commercial.get("pipeline_strategy")
            == "source-level all43 reconstruction with all43_18 base, all43_19 7-Eleven and active all43_24 lengthened-McDonald's/protected-sign/road-facing-chair/collision-audited-botanical-cafe pass"
            and commercial.get("reference_blend") is None
            and not commercial.get("reference_blends_loaded")
            and commercial.get("commercial20_shop_layout_changed_count") == 3
            and commercial.get("commercial20_stall_count") == 16
            and commercial.get("commercial20_mcdonalds_is_linked_collection_instance")
            is True
            and commercial.get("commercial20_cafe_is_linked_collection_instance")
            is True
            and commercial.get("commercial20_frontage_chairs_face_road") is True
            and not commercial.get("commercial20_new_mesh_quality_failures")
            and not commercial.get("commercial20_cafe_new_mesh_quality_failures")
        ),
        "original_residential_region_present": len(base_residential_objects) >= 50,
        "second_residential_region_exact": bool(
            extension.get("detached_houses") == 3
            and extension.get("apartment_buildings") == 2
            and extension.get("connected_path_segments", 0) >= 9
            and len(second_residential_assets) == 5
            and not extension.get("reference_blends_loaded")
        ),
        "third_residential_all45_09_exact": bool(
            third.get("valid")
            and third.get("reference_revision") == "urban_v3_all45_09"
            and third.get("building_count") == 11
            and len(third_lowrise) == 3
            and len(third_highrise) == 8
            and third.get("river_reserve_clearance_m", 0) >= 3.0
            and not third.get("completed_residential_blends_loaded")
            and not third.get("reference_blends_loaded")
        ),
        "three_residential_regions_present": bool(
            len(base_residential_objects) >= 50
            and len(second_residential_assets) == 5
            and len(third_lowrise) == 3
            and len(third_highrise) == 8
        ),
        "leisure_all44_13_source_exact": bool(
            leisure.get("source_revision") == "urban_v3_all44_13"
            and leisure_audit.get("pipeline_stage") == "generate_urban_v3_all44_13.py"
            and leisure_audit.get("source_level_integration")
            and leisure_audit.get("retained_basketball_court_objects", 0) >= 20
            and leisure_audit.get("retained_playground_objects", 0) >= 8
            and leisure_audit.get("athletics_ground_present")
            and leisure_audit.get("gymnasium_present")
            and leisure_audit.get("southward_expansion_m", 0) >= 43.0
            and leisure_audit.get("east_west_expansion_m") == 0.0
            and not leisure_audit.get("forbidden_degenerate_asset_names")
            and not leisure_audit.get("collapsed_new_meshes")
        ),
        "park_full07_source_preserved": bool(
            len(park_trees) >= 8
            and len(park_paths) == 4
            and len(tree_masters) >= 5
            and all(
                int(master.get("c2w_explicit_leaf_count", 0)) >= 3000
                for master in tree_masters[:5]
            )
        ),
        "river_full07_source_valid": bool(
            river.get("valid")
            and river.get("checks", {}).get("original_city_environment_preserved")
            and river.get("checks", {}).get("water_surface_below_channel_banks")
            and river.get("infinigen_reed_instances", 0) == 0
            and not river.get("reference_blends_loaded")
        ),
        "inherited_zebra_realistic": bool(
            len(inherited_zebra) == 9
            and all(
                float(obj.get("c2w_cross_road_span_m", 0)) >= 8.6
                for obj in inherited_zebra
            )
            and all(obj.get("c2w_connects_road_sides") for obj in inherited_zebra)
        ),
        "third_district_zebra_realistic": bool(
            len(third_zebra) == 9
            and all(
                float(obj.get("c2w_cross_road_span_m", 0)) >= 10.5
                for obj in third_zebra
            )
            and all(obj.get("c2w_connects_road_sides") for obj in third_zebra)
        ),
        "lane_markings_realistic": bool(
            set(solid) == {"north", "south", "east", "west"}
            and set(dashed) == {"north", "south", "east", "west"}
            and all(solid[arm] == 2 and dashed[arm] >= 5 for arm in solid)
            and len(third_centerline) >= 12
            and len(directions) == 8
            and all(obj.get("c2w_conflict_area_clear") for obj in third_centerline)
        ),
        "no_toy_proxy_or_collapsed_render_geometry": bool(
            not forbidden_reachable and not collapsed_reachable and not coarse_masters
        ),
        "camera_multiview_coverage": bool(
            len(cameras) == 41
            and camera_indices == expected_indices
            and all(
                token in cameras
                for token in (
                    "29_city_north_far.png",
                    "30_city_south_far.png",
                    "31_city_east_far.png",
                    "32_city_west_far.png",
                    "33_city_top_down.png",
                    "28_third_residential_street.png",
                    "35_all44_13_gymnasium_arrival.png",
                    "36_all44_13_athletics_close.png",
                    "37_all44_13_playground_close.png",
                    "41_river_level_long_view.png",
                )
            )
        ),
        "all_render_files_complete": bool(
            len(render_files) == 41 and set(render_files) == set(cameras)
        ),
    }
    failed = [name for name, valid in checks.items() if not valid]
    result = {
        "valid": not failed,
        "revision": "urban_v1_full_09",
        "audit_mode": "read-only generated-scene inspection; Blend not saved or modified",
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "reachable_render_objects": len(reachable),
            "base_residential_objects": len(base_residential_objects),
            "second_residential_buildings": len(second_residential_assets),
            "third_residential_lowrise": len(third_lowrise),
            "third_residential_highrise": len(third_highrise),
            "inherited_zebra_stripes": len(inherited_zebra),
            "third_district_zebra_stripes": len(third_zebra),
            "crossroads_centerlines": len(crossroads_lines),
            "third_district_centerline_dashes": len(third_centerline),
            "direction_arrow_objects": len(directions),
            "generator_cameras": len(cameras),
            "completed_render_files": len(render_files),
        },
        "forbidden_reachable_names": forbidden_reachable,
        "collapsed_reachable_meshes": collapsed_reachable,
        "forbidden_coarse_masters": coarse_masters,
        "camera_files": cameras,
        "render_files": render_files,
        "blend_modified_by_audit": False,
    }
    FINAL.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
    print("FULL09_STRICT_AUDIT=" + json.dumps(result, ensure_ascii=False), flush=True)
    if failed:
        raise RuntimeError(f"FULL09 strict completion audit failed: {failed}")


if __name__ == "__main__":
    main()
