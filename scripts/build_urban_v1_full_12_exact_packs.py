#!/usr/bin/env python3
"""Repack only the exact collections used by the full-12 production scene.

This is a dependency/IO optimization, not a geometry optimization: collections,
objects, meshes, modifiers, materials, interiors, and transforms are serialized
unchanged.  Omitting unrelated validation scenes/datablocks substantially lowers
the cost of opening the integrated city while preserving all requested assets.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_12/asset_packs"
LINEAGE = OUT / "full12_exact_pack_lineage.json"

SPECS = {
    "river3": {
        "source": ROOT
        / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river3/urban_v1_full_07-river3.blend",
        "target": "river3_full12_exact_collections.blend",
        "collections": [
            "Residential",
            "Residential_marble_quadrant",
            "House_large_indoor",
            "House_small_a_indoor",
            "House_small_b_indoor",
            "Residential_apartment_exterior",
            "full07_ext:full07_north_residential_extension",
        ],
    },
    "river5": {
        "source": ROOT
        / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river5/urban_v1_full_07-river5.blend",
        "target": "river5_full12_exact_collections.blend",
        "collections": [
            "Park",
            "full07_river5:River_Corridor_Production",
            "Road",
            "Sidewalks",
            "RoadMarkings",
            "TrafficLights",
            "Lamps",
            "FlowerBeds",
            "Vehicles",
        ],
    },
    "all45_09": {
        "source": ROOT
        / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09/urban_v3_all45_09.blend",
        "target": "all45_09_full12_exact_collection.blend",
        "collections": ["all45_09:parameterized_residential_generator_45_09"],
    },
    "all44_14": {
        "source": ROOT
        / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_14/urban_v3_all44_14.blend",
        "target": "all44_14_full12_exact_collection.blend",
        "collections": ["all44_10:COURT_PLAYGROUND_REBUILD"],
    },
    "lake3": {
        "source": ROOT
        / "infinigen/outputs/outdoor_part_demo/urban_v3_lake3/urban_v3_lake3.blend",
        "target": "lake3_full12_exact_collections.blend",
        "collections": [
            "urban_v3_lake3_PRODUCTION_LAKE_ASSET",
            "urban:lake3:paths",
            "urban:lake3:vegetation",
            "urban:lake3:furnishings",
            "urban:lake3:pavilion",
        ],
    },
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def collection_counts(collection: bpy.types.Collection) -> dict[str, int]:
    objects = list(collection.all_objects)
    return {
        "recursive_object_count": len(objects),
        "recursive_mesh_object_count": sum(obj.type == "MESH" for obj in objects),
        "recursive_source_polygon_count": sum(
            len(obj.data.polygons)
            for obj in objects
            if obj.type == "MESH" and obj.data is not None
        ),
        "recursive_collection_instance_count": sum(
            obj.instance_type == "COLLECTION" and obj.instance_collection is not None
            for obj in objects
        ),
    }


def build(key: str) -> None:
    spec = SPECS[key]
    source = Path(spec["source"])
    if not source.is_file():
        raise FileNotFoundError(source)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"FULL12_PACK_OPEN key={key} source={source}", flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    missing = [
        name for name in spec["collections"] if bpy.data.collections.get(name) is None
    ]
    if missing:
        raise RuntimeError(f"Missing {key} collection(s): {missing}")
    selected = {bpy.data.collections[name] for name in spec["collections"]}
    before = {
        name: collection_counts(bpy.data.collections[name])
        for name in spec["collections"]
    }
    target = OUT / str(spec["target"])
    temporary = OUT / (target.name + ".writing")
    if temporary.exists():
        temporary.unlink()
    bpy.data.libraries.write(
        str(temporary),
        selected,
        path_remap="ABSOLUTE",
        fake_user=True,
        compress=False,
    )
    if not temporary.is_file() or temporary.stat().st_size <= 0:
        raise RuntimeError(f"Exact collection pack was not written: {temporary}")
    os.replace(temporary, target)
    existing = {}
    if LINEAGE.is_file():
        try:
            existing = json.loads(LINEAGE.read_text(encoding="utf8")).get("packs", {})
        except (OSError, ValueError):
            existing = {}
    existing[key] = {
        "created_utc": utc_now(),
        "source": str(source.resolve()),
        "source_bytes": source.stat().st_size,
        "target": str(target.resolve()),
        "target_bytes": target.stat().st_size,
        "collections": list(spec["collections"]),
        "collection_counts_before_repack": before,
        "policy": "exact ID dependency repack; no geometry, material, modifier, interior, scale, or transform changes",
    }
    LINEAGE.write_text(
        json.dumps(
            {
                "schema": "agent.full12.exact_collection_packs.v1",
                "created_utc": utc_now(),
                "packs": existing,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf8",
    )
    print(
        f"FULL12_PACK_DONE key={key} bytes={target.stat().st_size} target={target}",
        flush=True,
    )


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    requested = args or list(SPECS)
    unknown = [key for key in requested if key not in SPECS]
    if unknown:
        raise RuntimeError(f"Unknown exact-pack keys: {unknown}")
    if len(requested) != 1:
        raise RuntimeError(
            "Build one exact pack per Blender process to bound peak memory"
        )
    build(requested[0])


if __name__ == "__main__":
    main()
