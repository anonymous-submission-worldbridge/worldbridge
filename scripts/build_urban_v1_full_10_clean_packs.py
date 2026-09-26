#!/usr/bin/env python3
"""Build clean collection-level packs for three flat/filtered reference scenes.

These packs do not change geometry.  They only turn existing object hierarchies into
linkable collections so the full-city blend need not promote thousands of individual
external Object IDs while saving.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_10/asset_packs"

SOURCES = {
    "factory": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_factory3/urban_v3_factory.blend",
    "school": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_school5/urban_v3_school5.blend",
    "library": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_library4/urban_v3_library4.blend",
}


def descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    result = []
    stack = [root]
    seen = set()
    while stack:
        obj = stack.pop()
        if obj.as_pointer() in seen:
            continue
        seen.add(obj.as_pointer())
        result.append(obj)
        stack.extend(obj.children)
    return result


def write_pack(filename: str, datablocks: set[bpy.types.ID]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / filename
    temporary = OUT / (filename + ".tmp")
    if temporary.exists():
        temporary.unlink()
    bpy.data.libraries.write(
        str(temporary),
        datablocks,
        path_remap="ABSOLUTE",
        fake_user=True,
        compress=False,
    )
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise RuntimeError(f"Clean pack was not written: {temporary}")
    temporary.replace(target)
    print(f"C2W_PACK_SAVED {target} {target.stat().st_size}", flush=True)
    return target


def build_factory() -> None:
    bpy.ops.wm.open_mainfile(filepath=str(SOURCES["factory"]), load_ui=False)
    specs = [
        ("full10:clean:factory_01_gable", "urban:factory:0:gable_clerestory:root"),
        ("full10:clean:factory_02_white", "urban:factory:1:white_modern:root"),
        ("full10:clean:factory_03_gated", "urban:factory:2:gated_campus:root"),
        ("full10:clean:factory_04_highbay", "urban:factory:3:highbay_monochrome:root"),
    ]
    collections = set()
    for collection_name, root_name in specs:
        root = bpy.data.objects.get(root_name)
        if root is None:
            raise RuntimeError(f"Missing factory root: {root_name}")
        collection = bpy.data.collections.new(collection_name)
        for obj in descendants(root):
            collection.objects.link(obj)
        collection["source_path"] = str(SOURCES["factory"].resolve())
        collection["source_root_object"] = root_name
        collection["reuse_policy"] = "exact_hierarchy_repack_no_geometry_change"
        collections.add(collection)
    write_pack("factory3_clean_collections.blend", collections)


def build_school() -> None:
    bpy.ops.wm.open_mainfile(filepath=str(SOURCES["school"]), load_ui=False)
    child_names = [
        "school:DEDICATED_CAMPUS_SITE",
        "school:TRACK_AND_FOOTBALL_FIELD",
        "school:VOLLEYBALL_COURTS",
        "school:ACADEMIC_NORTH_WEST",
        "school:ACADEMIC_NORTH_CENTRE",
        "school:ACADEMIC_NORTH_EAST",
        "school:ACADEMIC_WEST_LINK",
        "school:ACADEMIC_EAST_LINK",
        "school:ACADEMIC_MID_EAST",
        "school:ADMINISTRATION_LIBRARY",
        "school:GYMNASIUM",
        "school:CIRCULAR_AUDITORIUM",
        "school:CAFETERIA_ARTS",
        "school:COVERED_CAMPUS_CONNECTIONS",
    ]
    missing = [name for name in child_names if bpy.data.collections.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing school child collections: {missing}")
    site_source = bpy.data.collections["school:DEDICATED_CAMPUS_SITE"]
    site_clean = bpy.data.collections.new(
        "full10:clean:school_site_without_regional_ground"
    )
    for obj in site_source.all_objects:
        if obj.name != "school:site:regional_ground":
            site_clean.objects.link(obj)
    root = bpy.data.collections.new("full10:clean:school5_complete_campus")
    root.children.link(site_clean)
    for name in child_names[1:]:
        root.children.link(bpy.data.collections[name])
    root["source_path"] = str(SOURCES["school"].resolve())
    root["excluded_validation_object"] = "school:site:regional_ground"
    root["reuse_policy"] = "exact_collections_repack_no_geometry_change"
    write_pack("school5_clean_collection.blend", {root})


def build_library() -> None:
    bpy.ops.wm.open_mainfile(filepath=str(SOURCES["library"]), load_ui=False)
    names = [
        "library4:LIBRARY_A_MODERN_CANTILEVER",
        "library4:LIBRARY_B_RED_MONUMENTAL",
        "library4:LIBRARY_COMPARISON_SITE",
    ]
    missing = [name for name in names if bpy.data.collections.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing library child collections: {missing}")
    site_source = bpy.data.collections["library4:LIBRARY_COMPARISON_SITE"]
    site_clean = bpy.data.collections.new(
        "full10:clean:library4_site_without_validation_ground"
    )
    for obj in site_source.all_objects:
        if obj.name != "library4:site:ground":
            site_clean.objects.link(obj)
    root = bpy.data.collections.new("full10:clean:library4_pair_and_site")
    root.children.link(bpy.data.collections["library4:LIBRARY_A_MODERN_CANTILEVER"])
    root.children.link(bpy.data.collections["library4:LIBRARY_B_RED_MONUMENTAL"])
    root.children.link(site_clean)
    root["source_path"] = str(SOURCES["library"].resolve())
    root["excluded_validation_object"] = "library4:site:ground"
    root["reuse_policy"] = "exact_collections_repack_no_geometry_change"
    write_pack("library4_clean_collection.blend", {root})


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    requested = args or ["factory", "school", "library"]
    builders = {
        "factory": build_factory,
        "school": build_school,
        "library": build_library,
    }
    unknown = [name for name in requested if name not in builders]
    if unknown:
        raise SystemExit(f"Unknown pack(s): {unknown}")
    for name in requested:
        print(f"C2W_PACK_BUILD {name}", flush=True)
        builders[name]()


if __name__ == "__main__":
    main()
