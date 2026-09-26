#!/usr/bin/env python3
"""Build the production ``urban_v1_full_11`` integrated city.

This is the active full-11 generator, not a post-process for a saved Blend.  It
uses the proven full-10 exact-reference assembly framework, replaces the one
outdated fire-station dependency with the requested fire7 source, adds the
requested lake3 asset, and densifies the street walls with scale-one instances
of already-authored all45_09 and all43_25 collections.  No requested building,
facility, landscape object, interior, or road object is remodelled here.

Run with Blender 4.5 or newer::

    blender -b --factory-startup --python scripts/generate_urban_v1_full_11.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Iterable, Sequence

import bpy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_urban_v1_full_10 as framework


REVISION = "urban_v1_full_11"
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND_OUT = OUT / f"{REVISION}.blend"
FULL10_PACKS = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_10/asset_packs"
PACK_OUT = OUT / "asset_packs"

FIRE7 = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_fire7/urban_v3_fire7.blend"
LAKE3 = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_lake3/urban_v3_lake3.blend"

PACK_FILENAMES = {
    "factory3": "factory3_clean_collections.blend",
    "school5": "school5_clean_collection.blend",
    "library4": "library4_clean_collection.blend",
}

# The integration framework is intentionally retained as a library.  These
# overrides are the full-11 production inputs used by the live build below.
framework.OUT = OUT
framework.BLEND_OUT = BLEND_OUT
framework.SOURCES = dict(framework.SOURCES)
framework.SOURCES["fire5"] = FIRE7  # compatibility key used inside build_city
framework.SOURCES["fire7"] = FIRE7
framework.SOURCES["lake3"] = LAKE3
framework.PACKS = {key: PACK_OUT / filename for key, filename in PACK_FILENAMES.items()}


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def prepare_exact_asset_packs() -> dict[str, dict[str, object]]:
    """Expose the existing geometry-neutral packs inside the full-11 output.

    The packs only group exact source collections; they contain no replacement
    geometry.  Hard links avoid copying the multi-gigabyte library pack while
    keeping every dependency under the requested result directory.
    """
    PACK_OUT.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, object]] = {}
    for key, filename in PACK_FILENAMES.items():
        source = FULL10_PACKS / filename
        target = PACK_OUT / filename
        if not source.is_file() or source.stat().st_size <= 0:
            raise FileNotFoundError(
                f"Required exact collection pack is missing: {source}"
            )
        if target.exists():
            same_file = False
            try:
                same_file = os.path.samefile(source, target)
            except OSError:
                pass
            if not same_file:
                if target.stat().st_size != source.stat().st_size:
                    raise RuntimeError(
                        f"Refusing to replace unexpected full-11 asset pack: {target}"
                    )
                target.unlink()
        if not target.exists():
            os.link(source, target)
        records[key] = {
            "path": str(target.resolve()),
            "source_pack": str(source.resolve()),
            "bytes": target.stat().st_size,
            "same_inode": os.path.samefile(source, target),
            "policy": "hardlinked exact collection repack; no geometry change",
        }
    (OUT / "asset_packs/lineage.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf8"
    )
    return records


_framework_link_collections = framework.link_collections
_framework_place = framework.place

FIRE7_COLLECTION_MAP = {
    "fire_region_v5:AMBULANCE_TYPE_I_AMBULANCE": "fire_region_v7:TRUCK_CLASSIC_PUMPER.001",
    "fire_region_v5:TRUCK_CLASSIC_PUMPER": "fire_region_v7:TRUCK_CLASSIC_PUMPER",
    "fire_region_v5:TRUCK_MODERN_LADDER_ENGINE": "fire_region_v7:TRUCK_MODERN_LADDER_ENGINE",
    "fire_region_v5:TRUCK_RAPID_RESCUE": "fire_region_v7:TRUCK_RAPID_RESCUE",
    "fire_region_v5:STATION_CIVIC_HEADQUARTERS": "fire_region_v7:STATION_CIVIC_HEADQUARTERS",
    "fire_region_v5:STATION_INDUSTRIAL_ANNEX": "fire_region_v7:STATION_INDUSTRIAL_ANNEX",
}


def link_collections(source: Path, names: list[str]) -> dict[str, bpy.types.Collection]:
    """Link requested IDs, translating only the legacy fire5 API names."""
    if source.resolve() == FIRE7.resolve():
        translated = [FIRE7_COLLECTION_MAP.get(name, name) for name in names]
        linked = _framework_link_collections(source, translated)
        return {
            requested: linked[actual] for requested, actual in zip(names, translated)
        }
    return _framework_link_collections(source, names)


CORE_LOCATION_OVERRIDES = {
    # Keep the third station genuinely near the library while clearing the
    # lake's western promenade and all entrance aprons.
    "police_near_library": (-172.0, 20.0, 0.0),
    # This remains on the opposite side of the city but no longer inflates the
    # developed envelope into an isolated western asset island.
    "gas_west_outskirts": (-455.0, 250.0, 0.0),
}

INTERNAL_SPINE_X = (-163.5, 272.5)
INTERNAL_SPINE_Y = (-381.5, -272.5, -163.5, -54.5)
NORTH_CONNECTOR_X = -155.0


def place(
    master: bpy.types.Collection,
    placement_id: str,
    **kwargs,
) -> bpy.types.Object:
    """Apply the full-11 plan while preserving exact source transforms."""
    if placement_id in CORE_LOCATION_OVERRIDES:
        kwargs["at"] = CORE_LOCATION_OVERRIDES[placement_id]

    if kwargs.get("source_key") == "fire5":
        kwargs["source_key"] = "fire7"
        source_collection = str(kwargs.get("source_collection", ""))
        for old, new in FIRE7_COLLECTION_MAP.items():
            source_collection = source_collection.replace(old, new)
        kwargs["source_collection"] = source_collection
        kwargs["variant"] = "fire7_two_station_four_detailed_fire_engine_precinct"
        metadata = dict(kwargs.get("metadata") or {})
        metadata.update(
            {
                "fire_revision": "urban_v3_fire7",
                "ambulance_count": 0,
                "fire_engine_count": 4,
                "fire_engine_types": 3,
            }
        )
        kwargs["metadata"] = metadata

    at = tuple(float(value) for value in kwargs.get("at", (0.0, 0.0, 0.0)))
    if (
        kwargs.get("category") == "road_segment_ew"
        and any(abs(at[0] - x) < 1e-4 for x in INTERNAL_SPINE_X)
        and any(abs(at[1] - y) < 1e-4 for y in INTERNAL_SPINE_Y)
    ):
        intersection = bpy.data.collections.get(
            "full10:master:road_intersection_complete"
        )
        if intersection is None:
            raise RuntimeError(
                "Internal road spine requested before road master exists"
            )
        master = intersection
        kwargs["category"] = "road_intersection"
        kwargs[
            "source_collection"
        ] = "Road + Sidewalks + RoadMarkings + Lamps + TrafficLights"
        kwargs["source_bounds"] = (
            (-54.5, -54.5, 0.0),
            (54.5, 54.5, 8.0),
        )
        metadata = dict(kwargs.get("metadata") or {})
        metadata.update(
            {
                "crosswalk_orientation": "source_exact_both",
                "traffic_clear": True,
                "internal_spine_intersection": True,
            }
        )
        kwargs["metadata"] = metadata

    obj = _framework_place(master, placement_id, **kwargs)
    obj["generated_by"] = str(Path(__file__).resolve())
    obj["scene_revision"] = REVISION
    return obj


# Patch only the framework extension points; the original reference-selection
# and exact scale-one assembly logic remains untouched.
framework.link_collections = link_collections
framework.place = place


def require_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        raise RuntimeError(f"Expected linked source collection is unavailable: {name}")
    return collection


def add_artificial_lake() -> None:
    """Add the requested lake3 lake, paths, trees, pavilion, and benches.

    The 300 x 270 m validation-only rolling ground is intentionally not linked:
    the continuous city ground already supplies that role.  Every designed
    lake, apron, path, vegetation, pavilion, and furnishing collection is used
    unchanged at source scale.
    """
    names = [
        "urban_v3_lake3_PRODUCTION_LAKE_ASSET",
        "urban:lake3:paths",
        "urban:lake3:vegetation",
        "urban:lake3:furnishings",
        "urban:lake3:pavilion",
    ]
    linked = link_collections(LAKE3, names)
    master = framework.make_master(
        "artificial_lake3_complete_city_context",
        collections=[linked[name] for name in names],
    )
    place(
        master,
        "education_artificial_lake_civic_enclosure",
        category="artificial_lake",
        zone="education",
        source_key="lake3",
        source_collection=" + ".join(names),
        source_bounds=((-65.0, -55.0, -2.2), (65.0, 55.0, 10.0)),
        source_center=(0.0, 0.0),
        at=(-75.0, 95.0, 0.0),
        variant="lake3_irregular_lake_pavilion_trees_benches_paths",
        metadata={
            "waterbody_count": 1,
            "pavilion_count": 1,
            "tree_instance_count": 26,
            "bench_instance_count": 11,
            "near_library": True,
            "surrounded_by_urban_frontage": True,
            "excluded_source_validation_object": "urban:lake3:landscape:continuous_excavated_rolling_park_ground",
            "city_ground_replaces_only_source_wide_validation_terrain": True,
        },
    )


def add_northern_connector_road() -> None:
    """Join the northern civic campuses to the shared street network.

    The connector occupies the measured 4.5 m clear slot between the school
    parcel and the artificial-lake parcel.  It reuses one complete river5
    signalised intersection and two untouched 109 m north/south road modules;
    no road, marking, crosswalk, lamp, kerb, or signal geometry is rebuilt.
    """
    intersection = require_collection("full10:master:road_intersection_complete")
    north_south = require_collection("full10:master:road_ns_109m")
    place(
        intersection,
        "road_north_connector_signalised_junction",
        category="road_intersection",
        zone="roads",
        source_key="river5",
        source_collection=("Road + Sidewalks + RoadMarkings + Lamps + TrafficLights"),
        source_bounds=((-54.5, -54.5, 0.0), (54.5, 54.5, 8.0)),
        source_center=(0.0, 0.0),
        at=(NORTH_CONNECTOR_X, 163.5, 0.0),
        collision_class="road",
        metadata={
            "crosswalk_orientation": "source_exact_both",
            "traffic_clear": True,
            "north_campus_connector": True,
            "exact_river5_module": True,
        },
    )
    for index, y in enumerate((272.5, 381.5), 1):
        place(
            north_south,
            f"road_north_connector_segment_{index:02d}",
            category="road_segment_ns",
            zone="roads",
            source_key="river5",
            source_collection="Road + Sidewalks + RoadMarkings + Lamps",
            source_bounds=((-10.5, -54.5, 0.0), (10.5, 54.5, 8.0)),
            source_center=(0.0, 0.0),
            at=(NORTH_CONNECTOR_X, y, 0.0),
            collision_class="road",
            metadata={
                "crosswalk_orientation": "source_exact_ns",
                "traffic_clear": True,
                "north_campus_connector": True,
                "exact_river5_module": True,
            },
        )


def add_exact_streetwall_infill() -> dict[str, int]:
    """Fill empty frontage with existing detailed assets at exact scale."""
    tower_origins = (
        (-48.75, 10.0),
        (-16.25, 10.0),
        (16.25, 10.0),
        (48.75, 10.0),
        (-48.75, 48.0),
        (-16.25, 48.0),
        (16.25, 48.0),
        (48.75, 48.0),
    )
    tower_targets = (
        (-455.0, -30.0),
        (-415.0, -30.0),
        (-375.0, -30.0),
        (-315.0, -30.0),
        (-275.0, -30.0),
        (-235.0, -30.0),
        (75.0, -30.0),
        (115.0, -30.0),
        (-285.0, -190.0),
        (-245.0, -190.0),
        (-205.0, -190.0),
        (65.0, -190.0),
        (105.0, -190.0),
        (205.0, -190.0),
        (245.0, -190.0),
        (325.0, -190.0),
    )
    tower_masters = []
    for index, center in enumerate(tower_origins, 1):
        name = f"all45_09:highrise_tower_{index:02d}"
        collection = require_collection(name)
        tower_masters.append(
            (
                framework.make_master(
                    f"infill_all45_tower_{index:02d}", collections=[collection]
                ),
                name,
                center,
            )
        )
    for index, target in enumerate(tower_targets):
        master, source_name, center = tower_masters[index % len(tower_masters)]
        place(
            master,
            f"streetwall_tower_{index + 1:02d}",
            category="urban_infill",
            zone="commercial" if target[1] > -100 else "civic",
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 13.0, center[1] - 11.5, -0.5),
                (center[0] + 13.0, center[1] + 11.5, 55.0),
            ),
            source_center=center,
            at=(target[0], target[1], 0.0),
            variant=f"all45_09_exact_tower_{index % 8 + 1:02d}",
            metadata={
                "infill_role": "continuous_urban_streetwall",
                "source_scale_preserved": True,
                "front_direction_local": "-Y",
            },
        )

    townhouse_origins = ((-42.0, -17.0), (0.0, -17.0), (42.0, -17.0))
    townhouse_targets = (
        (-450.0, -245.0),
        (-410.0, -245.0),
        (-370.0, -245.0),
        (-285.0, -245.0),
        (-245.0, -245.0),
        (-205.0, -245.0),
        (-115.0, -245.0),
        (-75.0, -245.0),
        (-35.0, -245.0),
        (205.0, -245.0),
        (245.0, -245.0),
        (325.0, -245.0),
    )
    townhouse_masters = []
    for index, center in enumerate(townhouse_origins, 1):
        name = f"all45_09:detached_townhouse_{index:02d}"
        collection = require_collection(name)
        townhouse_masters.append(
            (
                framework.make_master(
                    f"infill_all45_townhouse_{index:02d}", collections=[collection]
                ),
                name,
                center,
            )
        )
    for index, target in enumerate(townhouse_targets):
        master, source_name, center = townhouse_masters[index % 3]
        place(
            master,
            f"streetwall_townhouse_{index + 1:02d}",
            category="urban_infill",
            zone="leisure",
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 15.0, center[1] - 13.0, -0.5),
                (center[0] + 15.0, center[1] + 13.0, 13.0),
            ),
            source_center=center,
            at=(target[0], target[1], 0.0),
            variant=f"all45_09_exact_indoor_townhouse_{index % 3 + 1:02d}",
            metadata={
                "infill_role": "continuous_lowrise_streetwall",
                "native_infinigen_indoor_preserved": True,
                "front_direction_local": "-Y",
            },
        )

    commercial_master = require_collection("full10:master:commercial_all43_25")
    commercial_targets = (
        (-270.0, -125.0, math.pi),
        (0.0, -125.0, math.pi),
        (100.0, -125.0, math.pi),
        (235.0, -125.0, math.pi),
        (-120.0, -415.0, 0.0),
        (-55.0, -415.0, 0.0),
        (20.0, -415.0, 0.0),
        (85.0, -415.0, 0.0),
        (155.0, -415.0, 0.0),
        (220.0, -415.0, 0.0),
    )
    for index, (x, y, yaw) in enumerate(commercial_targets, 1):
        place(
            commercial_master,
            f"streetwall_shopfront_{index:02d}",
            category="urban_infill",
            zone="commercial" if y > -200 else "industrial",
            source_key="commercial25",
            source_collection=(
                "all43_17:rear_commercial_assets + "
                "all43_19:corner_store_world + "
                "all43_20:connected_commercial_world"
            ),
            source_bounds=((-58.45, -44.5, 0.0), (-6.25, -6.25, 10.25)),
            source_center=(-32.35, -25.375),
            at=(x, y, 0.0),
            yaw=yaw,
            variant="all43_25_exact_complete_streetwall_infill",
            metadata={
                "infill_role": "continuous_active_shop_frontage",
                "all_customer_entrances_preserved": True,
                "front_direction_local": "+Y",
            },
        )

    # Fill the remaining road-facing gaps with the same authored assets.  The
    # candidate lattice follows the real 21 m road/sidewalk clearances and is
    # accepted only when its exact rotated footprint clears every prior asset,
    # river, and road corridor.  This turns the former isolated compounds into
    # continuous blocks without manufacturing any new building geometry.
    occupied = [
        _rectangle(record)
        for record in framework.PLACEMENTS
        if record.get("collision_class") in {"asset", "river"}
    ]
    corridors = road_rectangles()

    def overlaps_with_clearance(
        first: Sequence[float],
        second: Sequence[float],
        clearance: float,
    ) -> bool:
        return not (
            float(first[2]) + clearance <= float(second[0])
            or float(second[2]) + clearance <= float(first[0])
            or float(first[3]) + clearance <= float(second[1])
            or float(second[3]) + clearance <= float(first[1])
        )

    def candidate_available(rectangle: Sequence[float]) -> bool:
        return not any(
            overlaps_with_clearance(rectangle, corridor, 0.75) for corridor in corridors
        ) and not any(
            overlaps_with_clearance(rectangle, existing, 1.5) for existing in occupied
        )

    dense_counts = {
        "dense_highrise_towers": 0,
        "dense_indoor_townhouses": 0,
        "dense_commercial_streetwalls": 0,
    }
    dense_index = 0

    def add_dense_tower(
        x: float,
        y: float,
        zone: str,
        yaw: float,
    ) -> bool:
        nonlocal dense_index
        vertical = abs(math.sin(yaw)) > 0.5
        half_x, half_y = (11.5, 13.0) if vertical else (13.0, 11.5)
        predicted = (x - half_x, y - half_y, x + half_x, y + half_y)
        if not candidate_available(predicted):
            return False
        template_index = dense_index % len(tower_masters)
        master, source_name, center = tower_masters[template_index]
        dense_index += 1
        placed = place(
            master,
            f"dense_streetwall_tower_{dense_index:03d}",
            category="urban_infill",
            zone=zone,
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 13.0, center[1] - 11.5, -0.5),
                (center[0] + 13.0, center[1] + 11.5, 55.0),
            ),
            source_center=center,
            at=(x, y, 0.0),
            yaw=yaw,
            variant=f"all45_09_exact_tower_{template_index + 1:02d}",
            metadata={
                "infill_role": "dense_continuous_urban_streetwall",
                "source_scale_preserved": True,
                "front_direction_local": "-Y",
                "road_clearance_verified": True,
            },
        )
        occupied.append(_rectangle(framework.PLACEMENTS[-1]))
        dense_counts["dense_highrise_towers"] += 1
        return placed is not None

    townhouse_index = 0

    def add_dense_townhouse(
        x: float,
        y: float,
        zone: str,
        yaw: float,
    ) -> bool:
        nonlocal townhouse_index
        vertical = abs(math.sin(yaw)) > 0.5
        half_x, half_y = (13.0, 15.0) if vertical else (15.0, 13.0)
        predicted = (x - half_x, y - half_y, x + half_x, y + half_y)
        if not candidate_available(predicted):
            return False
        template_index = townhouse_index % len(townhouse_masters)
        master, source_name, center = townhouse_masters[template_index]
        townhouse_index += 1
        placed = place(
            master,
            f"dense_streetwall_townhouse_{townhouse_index:03d}",
            category="urban_infill",
            zone=zone,
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 15.0, center[1] - 13.0, -0.5),
                (center[0] + 15.0, center[1] + 13.0, 13.0),
            ),
            source_center=center,
            at=(x, y, 0.0),
            yaw=yaw,
            variant=(f"all45_09_exact_indoor_townhouse_{template_index + 1:02d}"),
            metadata={
                "infill_role": "dense_continuous_lowrise_streetwall",
                "native_infinigen_indoor_preserved": True,
                "front_direction_local": "-Y",
                "road_clearance_verified": True,
            },
        )
        occupied.append(_rectangle(framework.PLACEMENTS[-1]))
        dense_counts["dense_indoor_townhouses"] += 1
        return placed is not None

    shop_index = 0

    def add_dense_shopfront(x: float, y: float, yaw: float) -> bool:
        nonlocal shop_index
        predicted = (x - 26.1, y - 19.125, x + 26.1, y + 19.125)
        if not candidate_available(predicted):
            return False
        shop_index += 1
        placed = place(
            commercial_master,
            f"dense_streetwall_shopfront_{shop_index:03d}",
            category="urban_infill",
            zone="industrial",
            source_key="commercial25",
            source_collection=(
                "all43_17:rear_commercial_assets + "
                "all43_19:corner_store_world + "
                "all43_20:connected_commercial_world"
            ),
            source_bounds=((-58.45, -44.5, 0.0), (-6.25, -6.25, 10.25)),
            source_center=(-32.35, -25.375),
            at=(x, y, 0.0),
            yaw=yaw,
            variant="all43_25_exact_complete_dense_streetwall_infill",
            metadata={
                "infill_role": "dense_continuous_active_shop_frontage",
                "all_customer_entrances_preserved": True,
                "front_direction_local": "+Y",
                "road_clearance_verified": True,
            },
        )
        occupied.append(_rectangle(framework.PLACEMENTS[-1]))
        dense_counts["dense_commercial_streetwalls"] += 1
        return placed is not None

    horizontal_tower_rows = (
        ("commercial", -137.0, 0.0),
        ("commercial", -81.0, math.pi),
        ("commercial", -29.0, 0.0),
        ("commercial", 25.0, math.pi),
        ("commercial", 78.0, 0.0),
        ("commercial", 132.0, math.pi),
        ("civic", -245.0, 0.0),
        ("civic", -191.0, math.pi),
    )
    for zone, y, yaw in horizontal_tower_rows:
        for x in range(-466, 360, 30):
            add_dense_tower(float(x), y, zone, yaw)

    for y, yaw in ((-355.0, 0.0), (-300.0, math.pi)):
        for x in range(-464, 360, 33):
            add_dense_townhouse(float(x), y, "leisure", yaw)

    # The first dense pass left unnecessarily deep rear yards inside otherwise
    # road-bounded blocks.  These middle rows use the same scale-one assets and
    # retain 1.5 m audited clearance, producing plausible compact urban blocks
    # rather than rows of isolated assets.
    for x in range(-464, 360, 33):
        add_dense_townhouse(float(x), -327.5, "leisure", 0.0)

    for zone, y, yaw in (
        ("civic", -218.0, math.pi),
        ("commercial", -109.0, 0.0),
        ("commercial", -2.0, math.pi),
        ("commercial", 51.5, 0.0),
        ("commercial", 105.0, math.pi),
    ):
        for x in range(-466, 360, 30):
            add_dense_tower(float(x), y, zone, yaw)

    for y, yaw in ((-465.0, math.pi), (-412.0, 0.0)):
        for x in range(-457, 360, 58):
            add_dense_shopfront(float(x), y, yaw)

    # Complete both north-south outer frontages around the large school,
    # library, residential, park, and river parcels.
    for x, zone, yaw in (
        (-465.0, "education", -math.pi / 2.0),
        (355.0, "residential", math.pi / 2.0),
    ):
        for y in range(185, 451, 30):
            add_dense_tower(x, float(y), zone, yaw)

    # Complete the formerly empty northern seam.  The tower frontage faces the
    # new connector while authored indoor townhouses form a compact mixed-
    # height block between the school/lake and park/residences.
    for y in (195.0, 229.0, 263.0, 297.0, 331.0, 365.0, 399.0, 433.0):
        add_dense_tower(-125.0, y, "education", -math.pi / 2.0)
        for x in (-92.0, -62.0, -32.0, -2.0):
            add_dense_townhouse(x, y, "education", -math.pi / 2.0)

    # Fill residual corners along the two real internal road spines.  Most
    # candidates are intentionally rejected where a horizontal street wall or
    # a primary civic asset already occupies the parcel.
    for x, yaw in (
        (-188.0, math.pi / 2.0),
        (-139.0, -math.pi / 2.0),
        (247.0, math.pi / 2.0),
        (296.0, -math.pi / 2.0),
    ):
        for y in range(-355, -68, 30):
            zone = "leisure" if y < -272 else "civic" if y < -163 else "commercial"
            add_dense_tower(x, float(y), zone, yaw)

    return {
        "initial_highrise_towers": len(tower_targets),
        "initial_indoor_townhouses": len(townhouse_targets),
        "initial_complete_commercial_streetwalls": len(commercial_targets),
        **dense_counts,
    }


def _rectangle(record: dict) -> tuple[float, float, float, float]:
    footprint = record["footprint"]
    return (
        float(footprint["min"][0]),
        float(footprint["min"][1]),
        float(footprint["max"][0]),
        float(footprint["max"][1]),
    )


def rectangle_union_area(
    rectangles: Iterable[Sequence[float]],
) -> float:
    rects = [tuple(map(float, rect)) for rect in rectangles]
    rects = [rect for rect in rects if rect[2] > rect[0] and rect[3] > rect[1]]
    xs = sorted({value for rect in rects for value in (rect[0], rect[2])})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (rect[1], rect[3]) for rect in rects if rect[0] < right and rect[2] > left
        )
        covered = 0.0
        if intervals:
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start > end:
                    covered += end - start
                    start, end = next_start, next_end
                else:
                    end = max(end, next_end)
            covered += end - start
        total += (right - left) * covered
    return total


def interval_union_length(intervals: Iterable[Sequence[float]]) -> float:
    values = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not values:
        return 0.0
    total = 0.0
    start, end = values[0]
    for next_start, next_end in values[1:]:
        if next_start > end:
            total += end - start
            start, end = next_start, next_end
        else:
            end = max(end, next_end)
    return total + end - start


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    return (
        abs(
            sum(
                float(a[0]) * float(b[1]) - float(b[0]) * float(a[1])
                for a, b in zip(points, (*points[1:], points[0]))
            )
        )
        * 0.5
    )


def road_rectangles() -> list[tuple[float, float, float, float]]:
    half = 10.5
    rects = [
        (-545.0, y - half, 436.0, y + half)
        for y in (-381.5, -272.5, -163.5, -54.5, 163.5)
    ]
    rects.extend((x - half, -436.0, x + half, 436.0) for x in (-490.5, 381.5))
    rects.extend((x - half, -436.0, x + half, 0.0) for x in INTERNAL_SPINE_X)
    rects.append(
        (
            NORTH_CONNECTOR_X - half,
            109.0,
            NORTH_CONNECTOR_X + half,
            436.0,
        )
    )
    return rects


def road_intrusions(records: list[dict]) -> list[dict[str, object]]:
    intrusions = []
    corridors = road_rectangles()
    for record in records:
        if record.get("collision_class") != "asset":
            continue
        ax0, ay0, ax1, ay1 = _rectangle(record)
        for index, (rx0, ry0, rx1, ry1) in enumerate(corridors):
            overlap_x = min(ax1, rx1) - max(ax0, rx0)
            overlap_y = min(ay1, ry1) - max(ay0, ry0)
            if overlap_x > 0.15 and overlap_y > 0.15:
                intrusions.append(
                    {
                        "placement_id": record["placement_id"],
                        "corridor_index": index,
                        "overlap_m": [round(overlap_x, 3), round(overlap_y, 3)],
                    }
                )
    return intrusions


def frontage_audit(records: list[dict]) -> dict[str, object]:
    corridors = (
        ("education_boulevard", "EW", 163.5, -470.0, 360.0),
        ("central_main_street", "EW", -54.5, -470.0, 360.0),
        ("civic_services_avenue", "EW", -163.5, -470.0, 360.0),
        ("leisure_connector", "EW", -272.5, -470.0, 360.0),
        ("industrial_edge_street", "EW", -381.5, -460.0, 350.0),
    )
    eligible = [
        record for record in records if record.get("collision_class") == "asset"
    ]
    details = []
    ratios = []
    for name, orientation, coordinate, start, end in corridors:
        intervals = []
        ids = []
        for record in eligible:
            x0, y0, x1, y1 = _rectangle(record)
            perpendicular_gap = (
                0.0
                if y0 <= coordinate <= y1
                else min(abs(coordinate - y0), abs(coordinate - y1))
            )
            if perpendicular_gap > 90.0:
                continue
            left, right = max(start, x0), min(end, x1)
            if right - left > 0.5:
                intervals.append((left, right))
                ids.append(record["placement_id"])
        covered = interval_union_length(intervals)
        ratio = covered / (end - start)
        ratios.append(ratio)
        details.append(
            {
                "id": name,
                "orientation": orientation,
                "coordinate": coordinate,
                "audited_length_m": end - start,
                "covered_frontage_m": round(covered, 3),
                "continuity_ratio": round(ratio, 5),
                "contributing_placements": sorted(ids),
            }
        )
    return {
        "method": "union of real planned asset-footprint projections within 90 m urban block depth",
        "corridors": details,
        "mean_continuity_ratio": round(sum(ratios) / len(ratios), 5),
        "minimum_corridor_ratio": round(min(ratios), 5),
        "required_mean_ratio": 0.62,
        "required_minimum_corridor_ratio": 0.50,
    }


def road_graph_audit() -> dict[str, object]:
    horizontal = (-381.5, -272.5, -163.5, -54.5, 163.5)
    outer_x = (-490.5, 381.5)
    nodes = {(x, y) for x in outer_x for y in horizontal}
    nodes.update((x, y) for x in INTERNAL_SPINE_X for y in INTERNAL_SPINE_Y)
    nodes.update(
        {
            (NORTH_CONNECTOR_X, 163.5),
            (NORTH_CONNECTOR_X, 436.0),
        }
    )
    edges = set()
    for y in horizontal:
        row = sorted(x for x, node_y in nodes if node_y == y)
        edges.update(
            ((row[index], y), (row[index + 1], y)) for index in range(len(row) - 1)
        )
    for x in (*outer_x, *INTERNAL_SPINE_X):
        column = sorted(y for node_x, y in nodes if node_x == x)
        edges.update(
            ((x, column[index]), (x, column[index + 1]))
            for index in range(len(column) - 1)
        )
    edges.add(
        (
            (NORTH_CONNECTOR_X, 163.5),
            (NORTH_CONNECTOR_X, 436.0),
        )
    )
    adjacency = {node: set() for node in nodes}
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    visited = set()
    stack = [next(iter(nodes))]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency[node] - visited)
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_node_count": len(visited),
        "connected": len(visited) == len(nodes),
        "dead_end_count": sum(
            len(neighbours) == 1 for neighbours in adjacency.values()
        ),
        "outer_loop_present": True,
        "internal_spine_x": list(INTERNAL_SPINE_X),
        "north_connector_x": NORTH_CONNECTOR_X,
        "nodes": [list(node) for node in sorted(nodes)],
        "edges": [[list(first), list(second)] for first, second in sorted(edges)],
    }


def coverage_audit(records: list[dict], zones: dict[str, object]) -> dict[str, object]:
    envelope = (-510.0, -490.0, 455.0, 480.0)
    envelope_area = (envelope[2] - envelope[0]) * (envelope[3] - envelope[1])
    strict_rectangles = [
        _rectangle(record)
        for record in records
        if record.get("collision_class") in {"asset", "river"}
    ]
    occupied_area = rectangle_union_area(strict_rectangles)
    roads = road_rectangles()
    road_area = rectangle_union_area(roads)
    visible_developed_area = rectangle_union_area([*strict_rectangles, *roads])
    parcel_polygons = list(zones["developed_parcels"].values())
    parcel_area = sum(polygon_area(polygon) for polygon in parcel_polygons)
    return {
        "method": {
            "asset_footprints": "exact union of generated placement AABBs; overlaps counted once",
            "visible_development": "exact union of real asset/river footprints and connected road corridors",
            "planned_parcels": "reported separately and never counted as visible built coverage",
            "roads": "exact union of connected 21 m road-and-sidewalk corridors",
        },
        "city_envelope": {"min": list(envelope[:2]), "max": list(envelope[2:])},
        "city_envelope_area_m2": round(envelope_area, 3),
        "occupied_asset_footprint_area_m2": round(occupied_area, 3),
        "occupied_asset_footprint_ratio": round(occupied_area / envelope_area, 5),
        "developed_parcel_area_m2": round(parcel_area, 3),
        "planned_developed_parcel_ratio": round(parcel_area / envelope_area, 5),
        "road_corridor_area_m2": round(road_area, 3),
        "visible_built_and_road_area_m2": round(visible_developed_area, 3),
        "developed_city_coverage_ratio": round(
            visible_developed_area / envelope_area, 5
        ),
        "required_asset_footprint_ratio": 0.34,
        "required_developed_city_coverage_ratio": 0.50,
        "ground_tile_coverage_ratio": 1.0,
        "asset_island_policy": "forbidden; every primary parcel touches a connected road or another developed parcel",
    }


def planned_zones() -> dict[str, object]:
    return {
        "park_irregular_polygon": [
            [18, 238],
            [112, 232],
            [152, 250],
            [184, 310],
            [178, 470],
            [92, 478],
            [12, 448],
            [22, 330],
        ],
        "leisure_south_polygon": [
            [-470, -282],
            [356, -286],
            [368, -328],
            [338, -370],
            [-455, -368],
            [-478, -332],
        ],
        "residential_north_east_polygon": [
            [8, 232],
            [188, 235],
            [198, 224],
            [366, 238],
            [374, 474],
            [12, 476],
            [-2, 402],
        ],
        "education_west_polygon": [
            [-476, 174],
            [-146, 174],
            [-139, 224],
            [-151, 474],
            [-476, 466],
            [-485, 318],
        ],
        "education_lake_polygon": [
            [-408, 34],
            [-2, 34],
            [8, 154],
            [-414, 154],
        ],
        "commercial_center_polygon": [
            [-475, -145],
            [368, -145],
            [372, 154],
            [-6, 154],
            [-18, 30],
            [-475, 30],
        ],
        "civic_services_polygon": [
            [-476, -260],
            [366, -260],
            [372, -177],
            [-468, -174],
        ],
        "industrial_outer_polygon": [
            [-476, -486],
            [365, -486],
            [374, -397],
            [-470, -394],
        ],
        "developed_parcels": {
            "north_west_education": [
                [-475, 175],
                [-150, 175],
                [-142, 235],
                [-150, 475],
                [-475, 465],
            ],
            "north_east_residential_park": [
                [-142, 225],
                [372, 235],
                [374, 474],
                [-150, 475],
            ],
            "central_mixed_use": [[-475, -145], [370, -145], [372, 154], [-475, 154]],
            "civic_transition": [[-475, -260], [370, -260], [370, -176], [-475, -176]],
            "leisure_band": [[-475, -370], [370, -370], [370, -285], [-475, -285]],
            "industrial_band": [[-475, -486], [370, -486], [370, -395], [-475, -395]],
        },
    }


def finalize_manifest(
    manifest: dict,
    pack_lineage: dict[str, dict[str, object]],
    infill_counts: dict[str, int],
) -> dict:
    records = framework.PLACEMENTS
    strict_assets = [
        record for record in records if record["collision_class"] == "asset"
    ]
    overlaps = []
    for index, first in enumerate(strict_assets):
        for second in strict_assets[index + 1 :]:
            if framework.aabb_overlap(first["footprint"], second["footprint"]):
                overlaps.append([first["placement_id"], second["placement_id"]])
    intrusions = road_intrusions(records)
    zones = planned_zones()
    coverage = coverage_audit(records, zones)
    frontage = frontage_audit(records)
    graph = road_graph_audit()

    manifest.update(
        {
            "schema": "agent.urban_full_layout.v2",
            "scene_revision": REVISION,
            "output_blend": str(BLEND_OUT.resolve()),
            "active_generator": str(Path(__file__).resolve()),
            "assembly_framework": str(ROOT / "scripts/generate_urban_v1_full_10.py"),
            "integration_policy": (
                "link approved final reference assets at exact scale; translate/yaw only; "
                "reuse exact authored collections for infill; never remodel requested objects"
            ),
            "internal_collection_namespace": (
                "full10 (stable namespace inherited from the exact-reference framework)"
            ),
            "city_bounds": {
                "min": [-510.0, -490.0, -2.2],
                "max": [455.0, 480.0, 95.0],
            },
            "zones": zones,
            "placements": records,
            "coverage_audit": coverage,
            "street_frontage_audit": frontage,
            "road_connectivity_audit": graph,
            "asset_pack_lineage": pack_lineage,
            "infill": {
                "counts": infill_counts,
                "total": sum(infill_counts.values()),
                "policy": "existing detailed all45_09/all43_25 assets, scale one, no remodel",
            },
        }
    )
    manifest["source_files"].pop("fire5", None)
    manifest["source_files"]["fire7"] = str(FIRE7.resolve())
    manifest["source_files"]["lake3"] = str(LAKE3.resolve())
    manifest["clean_collection_packs"] = {
        key: str(path.resolve()) for key, path in framework.PACKS.items()
    }
    manifest["road_network"].update(
        {
            "vertical_internal_spines": [
                {"x": x, "y_min": -436.0, "y_max": 0.0} for x in INTERNAL_SPINE_X
            ],
            "all_modules_source_exact": True,
            "graph_connected": graph["connected"],
            "traffic_obstruction_policy": "vehicles only",
        }
    )
    manifest["relationships"] = [
        relation
        for relation in manifest["relationships"]
        if relation.get("id") != "third_police_near_library"
    ] + [
        {
            "id": "third_police_near_library",
            "a": "police_near_library",
            "b": "education_library_south",
            "nearest_edge_clearance_m": 8.0,
        },
        {
            "id": "lake_near_library_and_urban_frontage",
            "a": "education_artificial_lake_civic_enclosure",
            "b": [
                "education_library_south",
                "police_near_library",
                "bank_low_01_classical",
                "commercial_all43_25_complete",
            ],
            "role": "natural_lake_landscape_enclosed_by_civic_and_commercial_frontage",
        },
    ]
    manifest["requirements"].update(
        {
            "artificial_lake_count": 1,
            "lake_pavilion_count": 1,
            "lake_reference": "urban_v3_lake3",
            "fire_reference": "urban_v3_fire7",
            "fire_ambulance_count": 0,
            "fire_engine_count": 4,
            "continuous_infill_placement_count": sum(infill_counts.values()),
            "minimum_developed_city_coverage_ratio": 0.50,
            "minimum_asset_footprint_ratio": 0.34,
            "minimum_top_down_non_base_pixel_coverage_ratio": 0.25,
            "minimum_mean_street_frontage_continuity": 0.62,
            "all_render_views_keep_other_regions_visible": True,
        }
    )
    manifest["generation_checks"] = {
        "asset_aabb_overlap_pairs": overlaps,
        "asset_road_intrusions": intrusions,
        "all_placement_scales_one": all(
            record["scale"] == [1.0, 1.0, 1.0] for record in records
        ),
        "source_files_exist": all(
            Path(path).is_file() for path in manifest["source_files"].values()
        ),
        "road_graph_connected": graph["connected"],
        "developed_city_coverage_pass": (
            coverage["developed_city_coverage_ratio"]
            >= coverage["required_developed_city_coverage_ratio"]
        ),
        "asset_footprint_coverage_pass": (
            coverage["occupied_asset_footprint_ratio"]
            >= coverage["required_asset_footprint_ratio"]
        ),
        "street_frontage_continuity_pass": (
            frontage["mean_continuity_ratio"] >= frontage["required_mean_ratio"]
            and frontage["minimum_corridor_ratio"]
            >= frontage["required_minimum_corridor_ratio"]
        ),
        "lake_present_near_library": True,
        "fire7_source_used": True,
    }
    manifest["render_contract"] = {
        "renderer": str(ROOT / "scripts/render_urban_v1_full_11_daytime.py"),
        "all_regions_remain_visible": True,
        "required_groups": ["city", "regions", "features"],
        "panorama_views": 6,
        "regional_near_far_pairs": 9,
        "feature_near_far_pairs": 8,
        "expected_minimum_png_count": 40,
    }

    failed = [
        name
        for name, valid in manifest["generation_checks"].items()
        if name not in {"asset_aabb_overlap_pairs", "asset_road_intrusions"}
        and valid is not True
    ]
    if overlaps:
        failed.append("asset_aabb_overlap_pairs")
    if intrusions:
        failed.append("asset_road_intrusions")
    if failed:
        raise RuntimeError(
            "Full-11 generation contract failed: "
            + ", ".join(sorted(failed))
            + f"; overlaps={overlaps}; intrusions={intrusions}; "
            + f"coverage={coverage}; frontage={frontage}"
        )
    return manifest


def build_city() -> dict:
    framework.ZONES.clear()
    framework.PLACEMENTS.clear()
    log("Building exact-reference base placements with fire7 compatibility")
    manifest = framework.build_city()
    log("Adding the exact lake3 urban lake beside the library")
    add_artificial_lake()
    log("Adding the exact river5 northern campus road connector")
    add_northern_connector_road()
    log("Adding exact all45_09/all43_25 scale-one streetwall infill")
    infill_counts = add_exact_streetwall_infill()
    pack_lineage = json.loads(
        (OUT / "asset_packs/lineage.json").read_text(encoding="utf8")
    )
    manifest = finalize_manifest(manifest, pack_lineage, infill_counts)

    scene = bpy.context.scene
    scene.name = REVISION
    scene["scene_revision"] = REVISION
    scene["c2w_revision"] = REVISION
    scene["active_generator"] = str(Path(__file__).resolve())
    scene["integration_policy"] = manifest["integration_policy"]
    scene["placement_count"] = len(framework.PLACEMENTS)
    scene["strict_asset_overlap_count"] = len(
        manifest["generation_checks"]["asset_aabb_overlap_pairs"]
    )
    scene["asset_road_intrusion_count"] = len(
        manifest["generation_checks"]["asset_road_intrusions"]
    )
    scene["developed_city_coverage_ratio"] = manifest["coverage_audit"][
        "developed_city_coverage_ratio"
    ]
    scene["street_frontage_continuity_ratio"] = manifest["street_frontage_audit"][
        "mean_continuity_ratio"
    ]

    text = bpy.data.texts.get("GENERATION_MANIFEST")
    if text is None:
        text = bpy.data.texts.new("GENERATION_MANIFEST")
    text.clear()
    text.write(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return manifest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf8")
    for stale_name in (
        "GENERATION_FAILED.txt",
        "strict_completion_audit.json",
        "SUCCESS",
        "render_manifest.json",
        "panorama_audit.json",
    ):
        stale = OUT / stale_name
        if stale.exists():
            stale.unlink()
    log("Starting urban_v1_full_11 production generation")
    try:
        pack_lineage = prepare_exact_asset_packs()
        framework.validate_sources()
        if not FIRE7.is_file() or not LAKE3.is_file():
            raise FileNotFoundError({"fire7": str(FIRE7), "lake3": str(LAKE3)})
        manifest = build_city()
        (OUT / "layout_plan.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf8",
        )
        generation_audit = {
            "status": "PASS",
            "scene_revision": REVISION,
            "active_generator": str(Path(__file__).resolve()),
            "placement_count": len(manifest["placements"]),
            "source_count": len(manifest["source_files"]),
            "linked_library_count_before_save": len(bpy.data.libraries),
            "requirements": manifest["requirements"],
            "generation_checks": manifest["generation_checks"],
            "coverage_audit": manifest["coverage_audit"],
            "street_frontage_audit": manifest["street_frontage_audit"],
            "road_connectivity_audit": manifest["road_connectivity_audit"],
            "asset_pack_lineage": pack_lineage,
        }
        (OUT / "generation_audit.json").write_text(
            json.dumps(generation_audit, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf8",
        )
        temporary = OUT / f"{REVISION}.writing.blend"
        if temporary.exists():
            temporary.unlink()
        log(
            f"Writing scene-reachable production blend with "
            f"{len(manifest['placements'])} placements and "
            f"{len(bpy.data.libraries)} linked libraries"
        )
        bpy.data.libraries.write(
            str(temporary),
            {bpy.context.scene, bpy.data.texts["GENERATION_MANIFEST"]},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("Blender did not write a non-empty production Blend")
        temporary.replace(BLEND_OUT)
        log(f"Saved {BLEND_OUT}")
    except Exception:
        failure = traceback.format_exc()
        log("FAILED\n" + failure)
        (OUT / "GENERATION_FAILED.txt").write_text(failure, encoding="utf8")
        raise


if __name__ == "__main__":
    main()
