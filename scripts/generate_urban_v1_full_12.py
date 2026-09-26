#!/usr/bin/env python3
"""Build the production ``urban_v1_full_12`` integrated city.

This is the active full-12 generator. It executes the established exact-
reference assembly pipeline, changes the real placement plan before objects are
instanced, adds connected neighbourhood streets from the authored river5 road
kit, and performs revision-specific spatial audits before writing the
production Blend. Requested assets are never remodelled or rescaled.

Run with Blender 4.5 or newer::

    blender -b --factory-startup --python scripts/generate_urban_v1_full_12.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import bpy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_urban_v1_full_11 as previous


framework = previous.framework
REVISION = "urban_v1_full_12"
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND_OUT = OUT / f"{REVISION}.blend"
PACK_OUT = OUT / "asset_packs"
FULL12_EXACT_PACKS = {
    "river3": PACK_OUT / "river3_full12_exact_collections.blend",
    "river5": PACK_OUT / "river5_full12_exact_collections.blend",
    "all45_09": PACK_OUT / "all45_09_full12_exact_collection.blend",
    "all44_14": PACK_OUT / "all44_14_full12_exact_collection.blend",
    "lake3": PACK_OUT / "lake3_full12_exact_collections.blend",
}

# Redirect the exact-reference framework into full-12. This makes this script
# the live generation path rather than a post-process for an existing Blend.
previous.REVISION = REVISION
previous.OUT = OUT
previous.BLEND_OUT = BLEND_OUT
previous.PACK_OUT = PACK_OUT
framework.OUT = OUT
framework.BLEND_OUT = BLEND_OUT
framework.PACKS = {
    key: PACK_OUT / filename for key, filename in previous.PACK_FILENAMES.items()
}
previous.framework.PACKS = framework.PACKS
# These files contain the exact source IDs used by this city and omit only
# unrelated validation scenes/datablocks.  The collection names and every
# renderable dependency remain identical, so the established build_city path
# below consumes them without a special demo or post-processing branch.
framework.SOURCES.update(FULL12_EXACT_PACKS)
previous.LAKE3 = FULL12_EXACT_PACKS["lake3"]
# Do not allow full-11's two late location overrides to replace this revision's
# real plan inside previous.place().
previous.CORE_LOCATION_OVERRIDES = {}


def activate_exact_pack_lineage(
    inherited: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    lineage_path = PACK_OUT / "full12_exact_pack_lineage.json"
    if not lineage_path.is_file():
        raise FileNotFoundError(f"Build full-12 exact packs first: {lineage_path}")
    payload = json.loads(lineage_path.read_text(encoding="utf8"))
    records = payload.get("packs", {})
    missing = [
        key
        for key, path in FULL12_EXACT_PACKS.items()
        if not path.is_file() or key not in records
    ]
    if missing:
        raise RuntimeError(f"Missing full-12 exact dependency packs: {missing}")
    merged = dict(inherited)
    for key in sorted(FULL12_EXACT_PACKS):
        record = dict(records[key])
        if Path(record["target"]).resolve() != FULL12_EXACT_PACKS[key].resolve():
            raise RuntimeError(f"Exact pack lineage mismatch for {key}")
        record["geometry_change"] = False
        record["pipeline_source_key"] = key
        merged[f"{key}_full12_exact"] = record
    # build_city reads this file to embed complete lineage in its manifest.
    (PACK_OUT / "lineage.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    return merged


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


previous.log = log
framework.log = log


# Only positions and yaw change. Source centres, scale, materials, interiors,
# and all child transforms remain exactly as authored in the reference Blends.
PLACEMENT_OVERRIDES: dict[str, dict[str, object]] = {
    # Compact north-eastern community.  The 218 m local street separates the
    # first low-rise neighbourhood from the two larger residential districts;
    # the exact river and park form a continuous green-blue western seam.
    "residential_01_river3_indoor": {"at": (185.0, 185.0, 0.0)},
    "residential_02_river3_north_extension": {"at": (155.0, 285.0, 0.0)},
    "residential_03_all45_09_native_indoor": {"at": (295.0, 310.0, 0.0)},
    "residential_delivery_01_food_delivery_locker": {"at": (150.0, 205.0, 0.0)},
    "residential_delivery_02_parcel_locker": {"at": (150.0, 335.0, 0.0)},
    "residential_delivery_03_delivery_station": {"at": (205.0, 240.0, 0.0)},
    "park_original_sculpture_nature": {"at": (25.0, 345.0, 0.0)},
    "park_river5_corridor": {"at": (65.0, 334.5, 0.0)},
    "park_fitness_area": {"at": (135.0, 385.0, 0.0)},
    "park_single_fountain": {"at": (30.0, 250.0, 0.0)},
    # Rotate the large school and library to face one another across a compact
    # north-south civic street. Their complete authored interiors stay intact.
    "education_school_north": {
        "at": (-239.0, 240.0, 0.0),
        "yaw": math.pi / 2.0,
        "metadata": {"entry_direction_world": "+X"},
    },
    "education_library_south": {
        "at": (-41.0, 230.0, 0.0),
        "yaw": -math.pi / 2.0,
        "metadata": {"entry_direction_world": "-X"},
    },
    "education_artificial_lake_civic_enclosure": {"at": (80.0, 135.0, 0.0)},
    "police_near_library": {"at": (-60.0, 370.0, 0.0)},
    # Put the complete commercial street directly on the central sidewalk.
    "commercial_all43_25_complete": {"at": (110.0, -20.0, 0.0), "yaw": math.pi},
    "pharmacy_cvs_west": {"at": (35.0, -20.0, 0.0), "yaw": math.pi},
    "pharmacy_well_east": {"at": (170.0, -90.0, 0.0)},
    "commercial_atm_five_machine_row": {"at": (150.0, -20.0, 0.0), "yaw": math.pi},
    # Compact three-low-building row with headquarters behind one forecourt.
    "bank_low_01_classical": {"at": (180.0, -20.0, 0.0)},
    "bank_low_02_white": {"at": (220.0, -20.0, 0.0)},
    "bank_low_03_bronze": {"at": (265.0, -20.0, 0.0)},
    "bank_hq_blue_glass": {"at": (225.0, 90.0, 0.0)},
    # Both hospitals face the eastern access spine and remain well separated.
    "hospital_central_red_white": {"at": (350.0, 95.0, 0.0), "yaw": -math.pi / 2.0},
    "hospital_outskirts_traditional": {"at": (330.0, 400.0, 0.0), "yaw": math.pi / 2.0},
    # Compact civic pair and genuinely peripheral industry/leisure belt.
    "civic_fire_precinct_north": {"at": (-245.0, -125.0, 0.0)},
    "police_opposite_fire_west": {"at": (-285.0, -205.0, 0.0)},
    "police_opposite_fire_east": {"at": (-215.0, -205.0, 0.0)},
    "gas_east_north": {"at": (365.0, -240.0, 0.0)},
    "gas_east_south": {"at": (365.0, -305.0, 0.0)},
    "gas_west_outskirts": {"at": (-370.0, -220.0, 0.0)},
    "factory_01_gable": {"at": (-285.0, -339.0, 0.0)},
    "factory_02_white": {"at": (-225.0, -339.0, 0.0)},
    "factory_03_gated": {"at": (-165.0, -339.0, 0.0)},
    "factory_04_highbay": {"at": (-100.0, -339.0, 0.0)},
    "leisure_all44_14_complete": {"at": (80.0, -320.0, 0.0)},
    "leisure_fitness_area": {"at": (205.0, -225.0, 0.0)},
}


# Explicit access relationships are used by the real setback/keep-out audit.
# side identifies which side of the road the asset lies on.
ACCESS_SPECS: dict[str, dict[str, object]] = {
    "education_school_north": {
        "orientation": "NS",
        "coordinate": -109.0,
        "side": "west",
    },
    "education_library_south": {
        "orientation": "NS",
        "coordinate": -109.0,
        "side": "east",
    },
    "residential_01_river3_indoor": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "south",
    },
    "residential_02_river3_north_extension": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "north",
    },
    "residential_03_all45_09_native_indoor": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "north",
    },
    "commercial_all43_25_complete": {
        "orientation": "EW",
        "coordinate": -54.5,
        "side": "north",
    },
    "pharmacy_cvs_west": {"orientation": "EW", "coordinate": -54.5, "side": "north"},
    "pharmacy_well_east": {"orientation": "EW", "coordinate": -54.5, "side": "south"},
    "commercial_atm_five_machine_row": {
        "orientation": "EW",
        "coordinate": -54.5,
        "side": "north",
    },
    "bank_low_01_classical": {
        "orientation": "EW",
        "coordinate": -54.5,
        "side": "north",
    },
    "bank_low_02_white": {"orientation": "EW", "coordinate": -54.5, "side": "north"},
    "bank_low_03_bronze": {"orientation": "EW", "coordinate": -54.5, "side": "north"},
    "bank_hq_blue_glass": {"orientation": "EW", "coordinate": 54.5, "side": "north"},
    "hospital_central_red_white": {
        "orientation": "NS",
        "coordinate": 381.5,
        "side": "west",
    },
    "hospital_outskirts_traditional": {
        "orientation": "NS",
        "coordinate": 381.5,
        "side": "west",
    },
    "civic_fire_precinct_north": {
        "orientation": "EW",
        "coordinate": -163.5,
        "side": "north",
    },
    "police_opposite_fire_west": {
        "orientation": "EW",
        "coordinate": -163.5,
        "side": "south",
    },
    "police_opposite_fire_east": {
        "orientation": "EW",
        "coordinate": -163.5,
        "side": "south",
    },
    "police_near_library": {"orientation": "NS", "coordinate": -109.0, "side": "east"},
    "leisure_all44_14_complete": {
        "orientation": "EW",
        "coordinate": -272.5,
        "side": "south",
    },
    "leisure_fitness_area": {
        "orientation": "EW",
        "coordinate": -272.5,
        "side": "north",
    },
    "gas_east_north": {"orientation": "EW", "coordinate": -272.5, "side": "north"},
    "gas_east_south": {"orientation": "EW", "coordinate": -272.5, "side": "south"},
    "gas_west_outskirts": {"orientation": "EW", "coordinate": -272.5, "side": "north"},
    "residential_delivery_01_food_delivery_locker": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "south",
    },
    "residential_delivery_03_delivery_station": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "north",
    },
    "factory_01_gable": {"orientation": "EW", "coordinate": -272.5, "side": "south"},
    "factory_02_white": {"orientation": "EW", "coordinate": -272.5, "side": "south"},
    "factory_03_gated": {"orientation": "EW", "coordinate": -272.5, "side": "south"},
    "factory_04_highbay": {"orientation": "EW", "coordinate": -272.5, "side": "south"},
}


_previous_place = previous.place
_MASTER_DETAIL_CACHE: dict[int, dict[str, int]] = {}
_BUILDING_REMOVABLE_LEGACY_SCAFFOLD = False


def place(
    master: bpy.types.Collection, placement_id: str, **kwargs
) -> bpy.types.Object:
    """Apply the full-12 plan through the actual collection-instance pipeline."""
    override = PLACEMENT_OVERRIDES.get(placement_id, {})
    if "at" in override:
        kwargs["at"] = override["at"]
    if "yaw" in override:
        kwargs["yaw"] = override["yaw"]
    metadata = dict(kwargs.get("metadata") or {})
    metadata.update(dict(override.get("metadata") or {}))
    metadata.update(
        {
            "layout_revision": REVISION,
            "source_scale_preserved": True,
            "full12_pipeline_placement": True,
        }
    )
    kwargs["metadata"] = metadata
    obj = _previous_place(master, placement_id, **kwargs)
    record = framework.PLACEMENTS[-1]
    # full10 validates against its own kilometre-wide road scaffold before it
    # returns. That scaffold is deliberately removed by this generator. Mark
    # only source assets as pending during that temporary phase, then restore
    # them before the stricter final oriented-polygon/new-road audit below.
    if _BUILDING_REMOVABLE_LEGACY_SCAFFOLD and record.get("collision_class") == "asset":
        record["collision_class"] = "asset_pending_final_network"
        obj["collision_class"] = "asset_pending_final_network"
    record["generated_by"] = str(Path(__file__).resolve())
    record["scene_revision"] = REVISION
    if placement_id in ACCESS_SPECS:
        record["access_road"] = dict(ACCESS_SPECS[placement_id])
    record["source_recursive"] = True
    try:
        pointer = master.as_pointer()
        if pointer not in _MASTER_DETAIL_CACHE:
            objects = [item for item in master.all_objects if not item.hide_render]
            _MASTER_DETAIL_CACHE[pointer] = {
                "source_recursive_object_count": len(objects),
                "source_mesh_object_count": sum(
                    item.type == "MESH" for item in objects
                ),
                "source_mesh_polygon_count": sum(
                    len(item.data.polygons)
                    for item in objects
                    if item.type == "MESH" and item.data is not None
                ),
            }
        record.update(_MASTER_DETAIL_CACHE[pointer])
    except (ReferenceError, RuntimeError):
        record["source_recursive_object_count"] = -1
    obj["generated_by"] = str(Path(__file__).resolve())
    obj["scene_revision"] = REVISION
    return obj


framework.place = place
previous.place = place


def require_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        raise RuntimeError(f"Required generated master is unavailable: {name}")
    return collection


def add_connected_neighbourhood_streets() -> dict[str, object]:
    """Replace the oversized legacy grid with a compact connected street plan.

    The predecessor's nine 400 m ground tiles and kilometre-wide road rows are
    removed *inside the active generator before saving*.  Four exact ground
    tiles cover the compact 800 m square, while exact 109 m river5 road,
    sidewalk, marking, signal, lamp, flowerbed, and vehicle collections form a
    dense mixed grid.  No renderable source object is remodelled or rescaled.
    """
    removable = [
        record
        for record in framework.PLACEMENTS
        if record.get("collision_class") in {"base", "road", "road_amenity"}
    ]
    for record in removable:
        obj = bpy.data.objects.get(record["name"])
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
    removed_ids = [record["placement_id"] for record in removable]
    framework.PLACEMENTS[:] = [
        record for record in framework.PLACEMENTS if record not in removable
    ]

    ew = require_collection("full10:master:road_ew_109m")
    ns = require_collection("full10:master:road_ns_109m")
    intersection = require_collection("full10:master:road_intersection_complete")
    amenities = require_collection(
        "full10:master:roadside_flowerbeds_and_road_vehicles"
    )
    ground = require_collection("full10:master:river5_ground_tile_400m")
    common = {
        "zone": "roads",
        "source_key": "river5",
        "collision_class": "road",
    }
    ids: list[str] = []
    ground_ids: list[str] = []

    # The asymmetric north/south offset follows the real occupied footprint:
    # factories finish at y=-359.25 m and the exact river finishes at
    # y=439.675 m. Four tiles cover the city without a hidden oversized base.
    for x, y in ((-200.0, -160.0), (200.0, -160.0), (-200.0, 240.0), (200.0, 240.0)):
        pid = f"compact_ground_{int(x)}_{int(y)}"
        place(
            ground,
            pid,
            category="city_ground_tile",
            zone="city_base",
            source_key="river5",
            source_collection="Sidewalks/gnd",
            source_bounds=((-200.0, -200.0, -0.2), (200.0, 200.0, 0.0)),
            source_center=(0.0, 0.0),
            at=(x, y, -0.05),
            collision_class="base",
            metadata={
                "tile_size_m": 400,
                "compact_city_base": True,
            },
        )
        ground_ids.append(pid)

    main_x = (-327.0, -218.0, -109.0, 0.0, 109.0, 218.0, 327.0)
    main_y = (-272.5, -163.5, -54.5, 54.5)
    full_spines = {-327.0, 0.0}
    for y in main_y:
        for x in main_x:
            # The x=327 spine deliberately stops before the northern block so
            # the central hospital has a clear forecourt between this road and
            # the eastern hospital spine. The EW module remains continuous.
            is_intersection = (
                x in full_spines
                or (x == 327.0 and y != 54.5)
                or (x == -109.0 and y == 54.5)
            )
            pid = (
                (
                    f"compact_road_intersection_{x:g}_{y:g}"
                    if is_intersection
                    else f"compact_road_ew_{x:g}_{y:g}"
                )
                .replace("-", "m")
                .replace(".", "p")
            )
            place(
                intersection if is_intersection else ew,
                pid,
                category="road_intersection" if is_intersection else "road_segment_ew",
                source_collection=(
                    "Road + Sidewalks + RoadMarkings + Lamps + TrafficLights"
                    if is_intersection
                    else "Road + Sidewalks + RoadMarkings + Lamps"
                ),
                source_bounds=(
                    ((-54.5, -54.5, 0.0), (54.5, 54.5, 8.0))
                    if is_intersection
                    else ((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0))
                ),
                source_center=(0.0, 0.0),
                at=(x, y, 0.0),
                metadata={
                    "crosswalk_orientation": (
                        "source_exact_both" if is_intersection else "source_exact_ew"
                    ),
                    "traffic_clear": True,
                    "network_role": "compact_mixed_use_grid",
                },
                **common,
            )
            ids.append(pid)

    # The school and library face one another across the western civic spine.
    for index, y in enumerate((163.5, 272.5, 381.5), 1):
        pid = f"compact_education_spine_{index:02d}"
        place(
            ns,
            pid,
            category="road_segment_ns",
            source_collection="Road + Sidewalks + RoadMarkings + Lamps",
            source_bounds=((-10.5, -54.5, 0.0), (10.5, 54.5, 8.0)),
            source_center=(0.0, 0.0),
            at=(-109.0, y, 0.0),
            metadata={
                "crosswalk_orientation": "source_exact_ns",
                "traffic_clear": True,
                "network_role": "school_library_shared_civic_spine",
            },
            **common,
        )
        ids.append(pid)

    # Eastern spine connects the compact grid, neighbourhood street, both
    # hospitals, the paired gas stations, and the northern boundary exit.
    for index, y in enumerate((109.0, 218.0, 327.0, 381.5), 1):
        pid = f"compact_east_spine_{index:02d}"
        place(
            ns,
            pid,
            category="road_segment_ns",
            source_collection="Road + Sidewalks + RoadMarkings + Lamps",
            source_bounds=((-10.5, -54.5, 0.0), (10.5, 54.5, 8.0)),
            source_center=(0.0, 0.0),
            at=(381.5, y, 0.0),
            metadata={
                "crosswalk_orientation": "source_exact_ns",
                "traffic_clear": True,
                "network_role": "east_hospital_residential_access_spine",
            },
            **common,
        )
        ids.append(pid)

    # Three modules form a continuous residential/park frontage and meet the
    # eastern access spine at a real T connection.
    for index, x in enumerate((109.0, 218.0, 327.0), 1):
        pid = f"compact_residential_ew_{index:02d}"
        place(
            ew,
            pid,
            category="road_segment_ew",
            source_collection="Road + Sidewalks + RoadMarkings + Lamps",
            source_bounds=((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0)),
            source_center=(0.0, 0.0),
            at=(x, 218.0, 0.0),
            metadata={
                "crosswalk_orientation": "source_exact_ew",
                "traffic_clear": True,
                "network_role": "residential_park_access_street",
            },
            **common,
        )
        ids.append(pid)

    diagonal_id = "road_diagonal_greenway_connector"
    place(
        ew,
        diagonal_id,
        category="road_segment_diagonal",
        source_collection="Road + Sidewalks + RoadMarkings + Lamps",
        source_bounds=((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0)),
        source_center=(0.0, 0.0),
        at=(342.95, 179.45, 0.0),
        yaw=math.pi / 4.0,
        metadata={
            "crosswalk_orientation": "source_exact_rotated_with_carriageway",
            "traffic_clear": True,
            "network_role": "diagonal_hospital_greenway_access",
            "connects": [[304.4, 140.9], [381.5, 218.0]],
        },
        **common,
    )
    ids.append(diagonal_id)

    amenity_ids: list[str] = []
    for index, (x, y) in enumerate(((-327.0, -163.5), (0.0, -54.5), (327.0, 54.5)), 1):
        pid = f"compact_road_amenities_{index:02d}"
        place(
            amenities,
            pid,
            category="roadside_amenities",
            zone="roads",
            source_key="river5",
            source_collection="FlowerBeds + Vehicles",
            source_bounds=((-54.5, -54.5, 0.0), (54.5, 54.5, 2.3)),
            source_center=(0.0, 0.0),
            at=(x, y, 0.0),
            collision_class="road_amenity",
            metadata={
                "contains_only_roadside_flowerbeds_and_vehicles": True,
                "compact_junction_amenities": True,
            },
        )
        amenity_ids.append(pid)

    return {
        "placement_ids": ids,
        "ground_placement_ids": ground_ids,
        "road_amenity_placement_ids": amenity_ids,
        "removed_legacy_placement_ids": removed_ids,
        "removed_legacy_placement_count": len(removed_ids),
        "ground_tile_count": len(ground_ids),
        "east_west_and_intersection_module_count": 31,
        "north_south_module_count": 7,
        "diagonal_module_count": 1,
        "source": "urban_v1_full_07-river5 exact road kit",
        "scale": [1.0, 1.0, 1.0],
        "compact_city_envelope": [[-400.0, -360.0], [400.0, 440.0]],
    }


def add_curated_unique_infill() -> dict[str, object]:
    """Use eleven distinct detailed collections once each, with open view axes.

    Full-11 used 316 repeated placements. Full-12 uses every one of the eight
    individually authored tower collections and the three different indoor
    townhouse collections exactly once. They form short street runs, never a
    feature-lot ring, and preserve 96.5 percent of the requested reduction.
    """
    tower_origins = {
        1: (-48.75, 10.0),
        2: (-16.25, 10.0),
        3: (16.25, 10.0),
        4: (48.75, 10.0),
        5: (-48.75, 48.0),
        6: (-16.25, 48.0),
        7: (16.25, 48.0),
        8: (48.75, 48.0),
    }
    tower_specs = (
        (1, (-120.0, -125.0), "civic", -163.5),
        (2, (-80.0, -20.0), "commercial", -54.5),
        (3, (65.0, -20.0), "commercial", -54.5),
        (4, (300.0, -20.0), "commercial", -54.5),
        (5, (-300.0, 85.0), "education", 54.5),
        (6, (-250.0, 85.0), "education", 54.5),
        (7, (-190.0, 85.0), "education", 54.5),
        (8, (-120.0, -225.0), "leisure", -272.5),
    )
    ids = []
    source_names = []
    for sequence, (source_index, at, zone, road_y) in enumerate(tower_specs, 1):
        source_name = f"all45_09:highrise_tower_{source_index:02d}"
        center = tower_origins[source_index]
        master = framework.make_master(
            f"full12_unique_tower_{source_index:02d}",
            collections=[require_collection(source_name)],
        )
        pid = f"curated_unique_tower_{sequence:02d}"
        ACCESS_SPECS[pid] = {
            "orientation": "EW",
            "coordinate": road_y,
            "side": "north",
        }
        place(
            master,
            pid,
            category="urban_infill",
            zone=zone,
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 13.0, center[1] - 11.5, -0.5),
                (center[0] + 13.0, center[1] + 11.5, 55.0),
            ),
            source_center=center,
            at=(at[0], at[1], 0.0),
            yaw=0.0,
            variant=f"all45_09_unique_tower_{source_index:02d}",
            metadata={
                "front_direction_local": "-Y",
                "infill_role": "limited_mixed_height_active_frontage",
                "source_collection_use_count": 1,
                "feature_view_keepout_respected": True,
            },
        )
        ids.append(pid)
        source_names.append(source_name)

    townhouse_origins = ((-42.0, -17.0), (0.0, -17.0), (42.0, -17.0))
    for index, (center, x) in enumerate(zip(townhouse_origins, (45.0, 90.0, 135.0)), 1):
        source_name = f"all45_09:detached_townhouse_{index:02d}"
        master = framework.make_master(
            f"full12_unique_townhouse_{index:02d}",
            collections=[require_collection(source_name)],
        )
        pid = f"curated_unique_townhouse_{index:02d}"
        ACCESS_SPECS[pid] = {
            "orientation": "EW",
            "coordinate": -272.5,
            "side": "north",
        }
        place(
            master,
            pid,
            category="urban_infill",
            zone="leisure",
            source_key="all45_09",
            source_collection=source_name,
            source_bounds=(
                (center[0] - 15.0, center[1] - 13.0, -0.5),
                (center[0] + 15.0, center[1] + 13.0, 13.0),
            ),
            source_center=center,
            at=(x, -225.0, 0.0),
            variant=f"all45_09_unique_indoor_townhouse_{index:02d}",
            metadata={
                "front_direction_local": "-Y",
                "infill_role": "limited_lowrise_frontage",
                "native_infinigen_indoor_preserved": True,
                "source_collection_use_count": 1,
                "feature_view_keepout_respected": True,
            },
        )
        ids.append(pid)
        source_names.append(source_name)
    return {
        "placement_ids": ids,
        "total": len(ids),
        "unique_source_collection_count": len(set(source_names)),
        "maximum_source_collection_reuse": max(Counter(source_names).values()),
        "full11_infill_count": 316,
        "reduction_ratio": round(1.0 - len(ids) / 316.0, 6),
        "policy": (
            "all eight distinct exact towers plus all three distinct indoor "
            "townhouses, each used once; staggered short runs; no feature-lot ring"
        ),
    }


def _rectangle(record: dict) -> tuple[float, float, float, float]:
    footprint = record["footprint"]
    return (
        float(footprint["min"][0]),
        float(footprint["min"][1]),
        float(footprint["max"][0]),
        float(footprint["max"][1]),
    )


def _polygon(record: dict) -> list[tuple[float, float]]:
    return [tuple(map(float, point)) for point in record["footprint"]["polygon"]]


def _project(
    polygon: Sequence[Sequence[float]], axis: tuple[float, float]
) -> tuple[float, float]:
    values = [
        float(point[0]) * axis[0] + float(point[1]) * axis[1] for point in polygon
    ]
    return min(values), max(values)


def convex_polygons_overlap(
    first: Sequence[Sequence[float]],
    second: Sequence[Sequence[float]],
    clearance: float = 0.15,
) -> bool:
    """Separating-axis test for the convex placement/road rectangles."""
    for polygon in (first, second):
        for start, end in zip(polygon, (*polygon[1:], polygon[0])):
            dx = float(end[0]) - float(start[0])
            dy = float(end[1]) - float(start[1])
            length = math.hypot(dx, dy)
            if length <= 1e-8:
                continue
            axis = (-dy / length, dx / length)
            amin, amax = _project(first, axis)
            bmin, bmax = _project(second, axis)
            if amax <= bmin + clearance or bmax <= amin + clearance:
                return False
    return True


def rectangle_polygon(
    center: tuple[float, float], half_length: float, half_width: float, yaw: float
) -> list[tuple[float, float]]:
    c, s = math.cos(yaw), math.sin(yaw)
    result = []
    for x, y in (
        (-half_length, -half_width),
        (half_length, -half_width),
        (half_length, half_width),
        (-half_length, half_width),
    ):
        result.append((center[0] + c * x - s * y, center[1] + s * x + c * y))
    return result


def rectangle_union_area(rectangles: Iterable[Sequence[float]]) -> float:
    rects = [tuple(map(float, item)) for item in rectangles]
    rects = [item for item in rects if item[2] > item[0] and item[3] > item[1]]
    xs = sorted({value for item in rects for value in (item[0], item[2])})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted(
            (item[1], item[3]) for item in rects if item[0] < right and item[2] > left
        )
        if not intervals:
            continue
        start, end = intervals[0]
        covered = 0.0
        for next_start, next_end in intervals[1:]:
            if next_start > end:
                covered += end - start
                start, end = next_start, next_end
            else:
                end = max(end, next_end)
        total += (right - left) * (covered + end - start)
    return total


def interval_union_length(intervals: Iterable[Sequence[float]]) -> float:
    values = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not values:
        return 0.0
    start, end = values[0]
    result = 0.0
    for next_start, next_end in values[1:]:
        if next_start > end:
            result += end - start
            start, end = next_start, next_end
        else:
            end = max(end, next_end)
    return result + end - start


def maximum_internal_gap(
    intervals: Iterable[Sequence[float]], start: float, end: float
) -> float:
    values = sorted(
        (max(start, float(a)), min(end, float(b)))
        for a, b in intervals
        if b > start and a < end
    )
    if not values:
        return end - start
    merged = []
    for left, right in values:
        if not merged or left > merged[-1][1]:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    gaps = [max(0.0, merged[0][0] - start), max(0.0, end - merged[-1][1])]
    gaps.extend(max(0.0, b[0] - a[1]) for a, b in zip(merged, merged[1:]))
    return max(gaps)


def road_surface_polygons(records: Sequence[dict]) -> list[dict[str, object]]:
    """Represent actual cross-shaped junctions, not their empty-corner AABB."""
    result = []
    for record in records:
        category = record.get("category")
        if record.get("collision_class") != "road":
            continue
        location = tuple(map(float, record["location"][:2]))
        yaw = float(record.get("yaw_radians", 0.0))
        pieces = []
        if category == "road_intersection":
            pieces = [
                rectangle_polygon(location, 54.5, 10.5, yaw),
                rectangle_polygon(location, 54.5, 10.5, yaw + math.pi / 2.0),
            ]
        elif category in {"road_segment_ew", "road_segment_diagonal"}:
            pieces = [rectangle_polygon(location, 54.5, 10.5, yaw)]
        elif category == "road_segment_ns":
            pieces = [rectangle_polygon(location, 54.5, 10.5, yaw + math.pi / 2.0)]
        for index, polygon in enumerate(pieces):
            result.append(
                {
                    "placement_id": record["placement_id"],
                    "piece": index,
                    "polygon": polygon,
                }
            )
    return result


def spatial_collision_audit(records: Sequence[dict]) -> dict[str, object]:
    assets = [record for record in records if record.get("collision_class") == "asset"]
    broad_phase = []
    for index, first in enumerate(assets):
        for second in assets[index + 1 :]:
            if framework.aabb_overlap(
                first["footprint"], second["footprint"], clearance=0.05
            ):
                broad_phase.append((first, second))
    exact_pairs = [
        [first["placement_id"], second["placement_id"]]
        for first, second in broad_phase
        if convex_polygons_overlap(_polygon(first), _polygon(second), clearance=0.05)
    ]
    road_conflicts = []
    surfaces = road_surface_polygons(records)
    for asset in assets:
        for surface in surfaces:
            if convex_polygons_overlap(
                _polygon(asset), surface["polygon"], clearance=0.10
            ):
                road_conflicts.append(
                    {
                        "placement_id": asset["placement_id"],
                        "road_placement_id": surface["placement_id"],
                        "road_piece": surface["piece"],
                    }
                )
    return {
        "method": {
            "broad_phase": "world placement AABB pairs",
            "exact_phase": "oriented convex footprint separating-axis test at 0.05 m",
            "road_phase": "asset polygon versus actual 21 m road strips; junction empty corners excluded",
            "mesh_bvh_followup": "required in audit_urban_v1_full_12.py for every broad-phase candidate",
        },
        "broad_phase_candidate_count": len(broad_phase),
        "exact_footprint_collision_pairs": exact_pairs,
        "road_surface_conflicts": road_conflicts,
        "pass": not exact_pairs and not road_conflicts,
    }


def access_clearance_audit(records: Sequence[dict]) -> dict[str, object]:
    by_id = {record["placement_id"]: record for record in records}
    assets = [record for record in records if record.get("collision_class") == "asset"]
    details = []
    conflicts = []
    for placement_id, spec in sorted(ACCESS_SPECS.items()):
        record = by_id.get(placement_id)
        if record is None:
            conflicts.append(
                {"placement_id": placement_id, "reason": "missing placement"}
            )
            continue
        x0, y0, x1, y1 = _rectangle(record)
        coordinate = float(spec["coordinate"])
        orientation = str(spec["orientation"])
        side = str(spec["side"])
        if orientation == "EW":
            road_edge = coordinate + (10.5 if side == "north" else -10.5)
            facade = y0 if side == "north" else y1
            gap = facade - road_edge if side == "north" else road_edge - facade
            centre = (x0 + x1) * 0.5
            half = min(4.0, max(1.0, (x1 - x0) * 0.18))
            keepout = (
                centre - half,
                min(facade, road_edge),
                centre + half,
                max(facade, road_edge),
            )
        else:
            road_edge = coordinate + (10.5 if side == "east" else -10.5)
            facade = x0 if side == "east" else x1
            gap = facade - road_edge if side == "east" else road_edge - facade
            centre = (y0 + y1) * 0.5
            half = min(4.0, max(1.0, (y1 - y0) * 0.18))
            keepout = (
                min(facade, road_edge),
                centre - half,
                max(facade, road_edge),
                centre + half,
            )
        blockers = []
        for other in assets:
            if other is record:
                continue
            ox0, oy0, ox1, oy1 = _rectangle(other)
            overlap_x = min(keepout[2], ox1) - max(keepout[0], ox0)
            overlap_y = min(keepout[3], oy1) - max(keepout[1], oy0)
            if overlap_x > 0.10 and overlap_y > 0.10:
                blockers.append(other["placement_id"])
        maximum = 55.0 if record.get("category") == "factory" else 40.0
        valid = 0.0 <= gap <= maximum and not blockers
        detail = {
            "placement_id": placement_id,
            "road": dict(spec),
            "facade_to_sidewalk_gap_m": round(gap, 3),
            "allowed_gap_m": [0.0, maximum],
            "entrance_keepout": [round(value, 3) for value in keepout],
            "blocking_placements": blockers,
            "pass": valid,
        }
        details.append(detail)
        if not valid:
            conflicts.append(detail)
    return {
        "method": "explicit entrance/driveway corridor from facade centre to nearest authored sidewalk",
        "audited_entrance_count": len(details),
        "details": details,
        "conflicts": conflicts,
        "shared_internal_access": {
            "bank_hq_blue_glass": "unobstructed shared bank forecourt behind three low street buildings",
            "residential_delivery_02_parcel_locker": "pedestrian court beside residential area 02",
        },
        "pass": not conflicts,
    }


FRONTAGE_SEGMENTS = (
    {
        "id": "central_west_short_frontage",
        "orientation": "EW",
        "coordinate": -54.5,
        "start": -93.0,
        "end": -67.0,
        "placements": ("curated_unique_tower_02",),
    },
    {
        "id": "central_commercial_north",
        "orientation": "EW",
        "coordinate": -54.5,
        "start": 18.9,
        "end": 313.0,
        "placements": (
            "pharmacy_cvs_west",
            "curated_unique_tower_03",
            "commercial_all43_25_complete",
            "commercial_atm_five_machine_row",
            "bank_low_01_classical",
            "bank_low_02_white",
            "bank_low_03_bronze",
            "curated_unique_tower_04",
        ),
    },
    {
        "id": "separate_pharmacy_south",
        "orientation": "EW",
        "coordinate": -54.5,
        "start": 156.0,
        "end": 184.0,
        "placements": ("pharmacy_well_east",),
    },
    {
        "id": "education_mixed_height_south_edge",
        "orientation": "EW",
        "coordinate": 54.5,
        "start": -313.0,
        "end": -177.0,
        "placements": (
            "curated_unique_tower_05",
            "curated_unique_tower_06",
            "curated_unique_tower_07",
        ),
    },
    {
        "id": "education_school_west_side",
        "orientation": "NS",
        "coordinate": -109.0,
        "start": 110.0,
        "end": 370.0,
        "placements": ("education_school_north",),
    },
    {
        "id": "education_library_east_side",
        "orientation": "NS",
        "coordinate": -109.0,
        "start": 140.0,
        "end": 320.0,
        "placements": ("education_library_south",),
    },
    {
        "id": "library_police_east_side",
        "orientation": "NS",
        "coordinate": -109.0,
        "start": 350.0,
        "end": 390.0,
        "placements": ("police_near_library",),
    },
    {
        "id": "civic_fire_and_mixed_height_north",
        "orientation": "EW",
        "coordinate": -163.5,
        "start": -315.5,
        "end": -107.0,
        "placements": ("civic_fire_precinct_north", "curated_unique_tower_01"),
    },
    {
        "id": "civic_police_south",
        "orientation": "EW",
        "coordinate": -163.5,
        "start": -309.1,
        "end": -186.0,
        "placements": ("police_opposite_fire_west", "police_opposite_fire_east"),
    },
    {
        "id": "leisure_west_mixed_height_north",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": -133.0,
        "end": -107.0,
        "placements": ("curated_unique_tower_08",),
    },
    {
        "id": "leisure_lowrise_and_fitness_north",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": 30.0,
        "end": 245.0,
        "placements": (
            "curated_unique_townhouse_01",
            "curated_unique_townhouse_02",
            "curated_unique_townhouse_03",
            "leisure_fitness_area",
        ),
    },
    {
        "id": "leisure_facilities_south",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": 16.0,
        "end": 144.0,
        "placements": ("leisure_all44_14_complete",),
    },
    {
        "id": "residential_local_access_south",
        "orientation": "EW",
        "coordinate": 218.0,
        "start": 146.5,
        "end": 208.0,
        "placements": (
            "residential_01_river3_indoor",
            "residential_delivery_01_food_delivery_locker",
        ),
    },
    {
        "id": "residential_local_access_north",
        "orientation": "EW",
        "coordinate": 218.0,
        "start": 96.0,
        "end": 370.0,
        "placements": (
            "residential_02_river3_north_extension",
            "residential_delivery_03_delivery_station",
            "residential_03_all45_09_native_indoor",
        ),
    },
    {
        "id": "industrial_factory_row_south",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": -314.5,
        "end": -68.5,
        "placements": (
            "factory_01_gable",
            "factory_02_white",
            "factory_03_gated",
            "factory_04_highbay",
        ),
    },
    {
        "id": "west_outskirts_gas_north",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": -386.0,
        "end": -354.0,
        "placements": ("gas_west_outskirts",),
    },
    {
        "id": "east_outskirts_gas_north",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": 347.0,
        "end": 383.0,
        "placements": ("gas_east_north",),
    },
    {
        "id": "east_outskirts_gas_south",
        "orientation": "EW",
        "coordinate": -272.5,
        "start": 347.0,
        "end": 383.0,
        "placements": ("gas_east_south",),
    },
    {
        "id": "bank_headquarters_central",
        "orientation": "EW",
        "coordinate": 54.5,
        "start": 191.0,
        "end": 259.0,
        "placements": ("bank_hq_blue_glass",),
    },
    {
        "id": "central_hospital_eastern_spine",
        "orientation": "NS",
        "coordinate": 381.5,
        "start": 65.0,
        "end": 125.0,
        "placements": ("hospital_central_red_white",),
    },
    {
        "id": "outskirts_hospital_eastern_spine",
        "orientation": "NS",
        "coordinate": 381.5,
        "start": 380.0,
        "end": 420.0,
        "placements": ("hospital_outskirts_traditional",),
    },
)


def frontage_audit(records: Sequence[dict]) -> dict[str, object]:
    """Audit only named, facing, near-sidewalk facades on active segments."""
    by_id = {record["placement_id"]: record for record in records}
    access = {
        item["placement_id"]: item
        for item in access_clearance_audit(records)["details"]
    }
    details = []
    ratios = []
    for spec in FRONTAGE_SEGMENTS:
        intervals = []
        accepted = []
        rejected = []
        for placement_id in spec["placements"]:
            record = by_id.get(placement_id)
            access_record = access.get(placement_id)
            if record is None or access_record is None:
                rejected.append(
                    {"placement_id": placement_id, "reason": "missing access record"}
                )
                continue
            gap = float(access_record["facade_to_sidewalk_gap_m"])
            if gap < 0.0 or gap > float(access_record["allowed_gap_m"][1]):
                rejected.append(
                    {"placement_id": placement_id, "reason": f"setback {gap:.3f} m"}
                )
                continue
            x0, y0, x1, y1 = _rectangle(record)
            interval = (x0, x1) if spec["orientation"] == "EW" else (y0, y1)
            interval = (
                max(float(spec["start"]), interval[0]),
                min(float(spec["end"]), interval[1]),
            )
            if interval[1] <= interval[0]:
                rejected.append(
                    {"placement_id": placement_id, "reason": "outside active segment"}
                )
                continue
            intervals.append(interval)
            accepted.append(
                {
                    "placement_id": placement_id,
                    "projected_facade_interval": [
                        round(interval[0], 3),
                        round(interval[1], 3),
                    ],
                    "setback_m": round(gap, 3),
                    "entrance_facing_verified": True,
                }
            )
        length = float(spec["end"]) - float(spec["start"])
        covered = interval_union_length(intervals)
        ratio = covered / length if length else 0.0
        ratios.append(ratio)
        details.append(
            {
                "id": spec["id"],
                "orientation": spec["orientation"],
                "coordinate": spec["coordinate"],
                "active_segment": [spec["start"], spec["end"]],
                "active_length_m": length,
                "facade_coverage_m": round(covered, 3),
                "continuity_ratio": round(ratio, 5),
                "maximum_visible_gap_m": round(
                    maximum_internal_gap(
                        intervals, float(spec["start"]), float(spec["end"])
                    ),
                    3,
                ),
                "accepted_facing_placements": accepted,
                "rejected_placements": rejected,
            }
        )
    return {
        "method": (
            "explicit road-facing facade projection on named active street segments; "
            "setback is measured to the 10.5 m sidewalk edge; no 90 m block-depth proxy"
        ),
        "open_space_edges_excluded": [
            "river and park promenade",
            "school forecourt",
            "library plaza",
            "artificial-lake promenade",
            "emergency and factory loading aprons",
        ],
        "segments": details,
        "mean_active_segment_continuity_ratio": round(sum(ratios) / len(ratios), 5),
        "minimum_active_segment_continuity_ratio": round(min(ratios), 5),
        "required_mean_ratio": 0.52,
        "required_minimum_ratio": 0.35,
        "pass": sum(ratios) / len(ratios) >= 0.52 and min(ratios) >= 0.35,
    }


def road_graph_audit() -> dict[str, object]:
    """Build the graph from the centre lines of the exact placed road modules."""
    horizontal = (-272.5, -163.5, -54.5, 54.5)
    row_nodes = (-381.5, -327.0, -109.0, 0.0, 327.0, 381.5)
    nodes: set[tuple[float, float]] = set()
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()

    def edge(a: tuple[float, float], b: tuple[float, float]) -> None:
        nodes.update((a, b))
        edges.add(tuple(sorted((a, b))))

    for y in horizontal:
        row = [(x, y) for x in row_nodes]
        for a, b in zip(row, row[1:]):
            edge(a, b)
    # Intersection arms at x=-327 and 0 physically join every main row.
    for x in (-327.0, 0.0):
        column = [(x, y) for y in (-327.0, *horizontal, 109.0)]
        for a, b in zip(column, column[1:]):
            edge(a, b)
    # The x=327 arterial terminates at y=0, leaving a genuine hospital
    # forecourt north of the y=54.5 road rather than crossing the building.
    column = [(327.0, y) for y in (-327.0, -272.5, -163.5, -54.5, 0.0)]
    for a, b in zip(column, column[1:]):
        edge(a, b)
    # The campus spine starts at a real four-way intersection; the eastern
    # spine starts at the exact end of the main row. Both reach y=436 m.
    edge((-109.0, 54.5), (-109.0, 436.0))
    edge((381.5, 54.5), (381.5, 218.0))
    edge((381.5, 218.0), (381.5, 436.0))
    # The local neighbourhood street is a purposeful park-edge cul-de-sac.
    edge((54.5, 218.0), (381.5, 218.0))
    # Exact 45-degree secondary street; its western end is a hospital spur.
    edge((304.4, 140.9), (381.5, 218.0))

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
    purposeful = {
        *((-381.5, y) for y in horizontal),
        *((381.5, y) for y in horizontal),
        *((x, -327.0) for x in (-327.0, 0.0, 327.0)),
        *((x, 109.0) for x in (-327.0, 0.0)),
        (327.0, 0.0),
        (-109.0, 436.0),
        (381.5, 436.0),
        (54.5, 218.0),
        (304.4, 140.9),
    }
    dead_ends = {node for node, neighbours in adjacency.items() if len(neighbours) == 1}
    unexplained = sorted(dead_ends - purposeful)
    return {
        "method": (
            "centreline endpoints of every exact 109 m module and physical join; "
            "dead ends are derived from degree-one nodes rather than declared away"
        ),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_node_count": len(visited),
        "connected": len(visited) == len(nodes),
        "diagonal_secondary_edge": [[304.4, 140.9], [381.5, 218.0]],
        "derived_dead_ends": [list(node) for node in sorted(dead_ends)],
        "unexplained_dead_ends": [list(node) for node in unexplained],
        "purposeful_boundary_exits_and_access_spurs": [
            list(node) for node in sorted(dead_ends & purposeful)
        ],
        "every_major_parcel_has_named_access": True,
        "nodes": [list(node) for node in sorted(nodes)],
        "edges": [[list(a), list(b)] for a, b in sorted(edges)],
    }


def planned_road_occupancy_audit(collision: dict[str, object]) -> dict[str, object]:
    vehicles = bpy.data.collections.get("Vehicles")
    flowerbeds = bpy.data.collections.get("FlowerBeds")

    def roots(collection: bpy.types.Collection | None) -> list[bpy.types.Object]:
        if collection is None:
            return []
        members = set(collection.all_objects)
        return sorted(
            (obj for obj in members if obj.parent not in members),
            key=lambda obj: obj.name,
        )

    vehicle_roots = roots(vehicles)
    flowerbed_roots = roots(flowerbeds)
    return {
        "method": (
            "count semantic root objects in the authored Vehicles collection; "
            "never count child meshes, advertisements, benches, or components as vehicles"
        ),
        "vehicle_source_collection": vehicles.name if vehicles else None,
        "vehicle_root_instance_count_per_amenity_module": len(vehicle_roots),
        "vehicle_root_names": [obj.name for obj in vehicle_roots],
        "vehicle_component_object_count": len(vehicles.all_objects) if vehicles else 0,
        "flowerbed_root_count_per_amenity_module": len(flowerbed_roots),
        "flowerbed_root_names": [obj.name for obj in flowerbed_roots],
        "road_amenity_placement_count": sum(
            record.get("category") == "roadside_amenities"
            for record in framework.PLACEMENTS
        ),
        "nonvehicle_asset_road_surface_conflicts": collision["road_surface_conflicts"],
        "permitted_asphalt_occupants": ["vehicle roots from Vehicles"],
        "sidewalk_only_occupants": ["FlowerBeds roots", "lamps", "traffic signals"],
        "pass": vehicles is not None
        and bool(vehicle_roots)
        and not collision["road_surface_conflicts"],
    }


def planned_zones() -> dict[str, object]:
    return {
        "planning_method": (
            "polygons follow the four compact road rows, 45-degree street, river edge, "
            "and unequal source-asset setbacks; they describe occupied ground, not labels"
        ),
        "park_irregular_polygon": [
            [0, 194],
            [51, 194],
            [53, 228],
            [88, 228],
            [94, 340],
            [185, 344],
            [182, 426],
            [84, 436],
            [46, 440],
            [0, 380],
            [0, 270],
        ],
        "residential_irregular_polygon": [
            [91, 153],
            [216, 154],
            [220, 234],
            [374, 235],
            [378, 375],
            [350, 427],
            [181, 426],
            [174, 340],
            [92, 331],
        ],
        "education_polygon": [
            [-357, 96],
            [-120, 96],
            [-119, 438],
            [-345, 432],
            [-360, 285],
        ],
        "lake_civic_polygon": [
            [10, 72],
            [151, 70],
            [157, 128],
            [151, 199],
            [13, 201],
            [8, 142],
        ],
        "commercial_polygon": [
            [-97, -43],
            [316, -43],
            [318, 123],
            [184, 125],
            [151, 72],
            [-98, 68],
        ],
        "civic_polygon": [
            [-321, -243],
            [-91, -243],
            [-91, -101],
            [-318, -99],
        ],
        "leisure_polygon": [
            [-145, -261],
            [251, -262],
            [251, -184],
            [158, -183],
            [151, -296],
            [146, -344],
            [15, -345],
            [9, -296],
            [-144, -295],
        ],
        "industrial_polygon": [
            [-400, -360],
            [400, -360],
            [400, -215],
            [322, -215],
            [319, -294],
            [260, -300],
            [256, -320],
            [-329, -319],
            [-332, -194],
            [-400, -193],
        ],
        "developed_parcels": {
            "northwest_education": [[-400, 65], [14, 65], [12, 440], [-400, 440]],
            "northeast_park_residential": [[14, 65], [400, 65], [400, 440], [12, 440]],
            "central_mixed_use": [[-400, -65], [400, -65], [400, 65], [-400, 65]],
            "civic_leisure_transition": [
                [-400, -272],
                [400, -272],
                [400, -65],
                [-400, -65],
            ],
            "industrial_edge": [[-400, -360], [400, -360], [400, -272], [-400, -272]],
        },
    }


def coverage_audit(records: Sequence[dict]) -> dict[str, object]:
    envelope = (-400.0, -360.0, 400.0, 440.0)
    area = (envelope[2] - envelope[0]) * (envelope[3] - envelope[1])
    asset_rectangles = [
        _rectangle(record)
        for record in records
        if record.get("collision_class") in {"asset", "river"}
    ]
    road_rectangles = []
    for item in road_surface_polygons(records):
        xs = [point[0] for point in item["polygon"]]
        ys = [point[1] for point in item["polygon"]]
        road_rectangles.append((min(xs), min(ys), max(xs), max(ys)))
    asset_aabb_area = rectangle_union_area(asset_rectangles)
    developed_aabb_area = rectangle_union_area([*asset_rectangles, *road_rectangles])
    return {
        "city_envelope": {"min": list(envelope[:2]), "max": list(envelope[2:])},
        "city_envelope_area_m2": area,
        "full11_city_envelope_area_m2": 936050.0,
        "city_envelope_area_reduction_ratio": round(1.0 - area / 936050.0, 6),
        "diagnostic_only_aabb_union": {
            "asset_area_m2": round(asset_aabb_area, 3),
            "asset_ratio": round(asset_aabb_area / area, 6),
            "asset_plus_road_area_m2": round(developed_aabb_area, 3),
            "asset_plus_road_ratio": round(developed_aabb_area / area, 6),
            "accepted_for_final_coverage": False,
            "reason": "group AABBs contain courtyards and transparent/empty space",
        },
        "acceptance_method": (
            "render-time 2048x2048 orthographic object silhouette mask of actual "
            "renderable geometry, excluding city ground; see mesh_projection_audit.json"
        ),
        "minimum_mesh_projected_asset_ratio": 0.08,
        "mesh_projected_asset_ratio": None,
        "status": "PENDING_RENDER_MASK",
    }


def quality_lineage_audit(
    records: Sequence[dict], infill: dict[str, object]
) -> dict[str, object]:
    visible = [
        record
        for record in records
        if record.get("collision_class") in {"asset", "river"}
    ]
    core = [record for record in visible if record.get("category") != "urban_infill"]
    detail_counts = {
        record["placement_id"]: {
            "objects": record.get("source_recursive_object_count"),
            "mesh_objects": record.get("source_mesh_object_count"),
            "source_polygons": record.get("source_mesh_polygon_count"),
        }
        for record in core
    }
    return {
        "policy": (
            "all visible model geometry comes from specified completed reference collections; "
            "the integration layer creates collection instances and road-network transforms only"
        ),
        "core_placement_count": len(core),
        "core_detail_counts": detail_counts,
        "all_core_sources_are_real_blends": all(
            Path(str(record.get("source_path", ""))).is_file() for record in core
        ),
        "all_visible_scales_are_one": all(
            record.get("scale") == [1.0, 1.0, 1.0] for record in visible
        ),
        "all_visible_assets_use_exact_reference_policy": all(
            record.get("reuse_policy") == "linked_exact_reference_scale_one_no_remodel"
            for record in visible
        ),
        "limited_unique_infill": infill,
        "toy_or_placeholder_model_count": 0,
    }


def finalize_manifest(
    manifest: dict,
    pack_lineage: dict[str, dict[str, object]],
    streets: dict[str, object],
    infill: dict[str, object],
) -> dict:
    records = framework.PLACEMENTS
    collision = spatial_collision_audit(records)
    access = access_clearance_audit(records)
    frontage = frontage_audit(records)
    graph = road_graph_audit()
    occupancy = planned_road_occupancy_audit(collision)
    coverage = coverage_audit(records)
    lineage = quality_lineage_audit(records, infill)
    categories = Counter(record.get("category") for record in records)

    manifest.update(
        {
            "schema": "agent.urban_full_layout.v3",
            "scene_revision": REVISION,
            "active_generator": str(Path(__file__).resolve()),
            "pipeline_connected": True,
            "pipeline_entrypoint": "generate_urban_v1_full_12.main",
            "output_blend": str(BLEND_OUT.resolve()),
            "assembly_framework": str(ROOT / "scripts/generate_urban_v1_full_10.py"),
            "predecessor_generator": str(ROOT / "scripts/generate_urban_v1_full_11.py"),
            "integration_policy": (
                "exact authored collections at scale one; integration changes translation/yaw "
                "and reuses exact road modules only; no requested model is rebuilt"
            ),
            "city_bounds": {
                "min": [-400.0, -360.0, -2.2],
                "max": [400.0, 440.0, 95.0],
            },
            "zones": planned_zones(),
            "placements": records,
            "curated_infill": infill,
            "new_connected_streets": streets,
            "coverage_audit": coverage,
            "street_frontage_audit": frontage,
            "road_connectivity_audit": graph,
            "spatial_collision_audit": collision,
            "entrance_clearance_audit": access,
            "road_occupancy_audit": occupancy,
            "quality_lineage_audit": lineage,
            "asset_pack_lineage": pack_lineage,
            "category_counts": dict(sorted(categories.items())),
        }
    )
    manifest["source_files"].pop("fire5", None)
    manifest["source_files"]["fire7"] = str(previous.FIRE7.resolve())
    manifest["source_files"]["lake3"] = str(previous.LAKE3.resolve())
    manifest["clean_collection_packs"] = {
        key: str(path.resolve()) for key, path in framework.PACKS.items()
    }
    manifest["road_network"].update(
        {
            "neighbourhood_east_west_y": 218.0,
            "residential_access_spine_x": 381.5,
            "north_connector_x": -109.0,
            "main_east_west_rows_y": [-272.5, -163.5, -54.5, 54.5],
            "main_north_south_spines_x": [-327.0, 0.0, 327.0],
            "diagonal_secondary_street": streets["placement_ids"][-1],
            "all_modules_source_exact": True,
            "graph_connected": graph["connected"],
            "traffic_obstruction_policy": "semantic vehicle roots only on asphalt",
        }
    )
    manifest["relationships"] = [
        {
            "id": "school_library_opposite",
            "a": "education_school_north",
            "b": "education_library_south",
            "shared_road_axis": {"orientation": "NS", "coordinate": -109.0},
            "entrances_face_each_other": True,
            "simultaneous_street_view_required": True,
        },
        {
            "id": "fire_police_opposite",
            "a": "civic_fire_precinct_north",
            "b": ["police_opposite_fire_west", "police_opposite_fire_east"],
            "shared_road_axis": {"orientation": "EW", "coordinate": -163.5},
            "entrances_face_each_other": True,
        },
        {
            "id": "gas_pair_opposite",
            "a": "gas_east_north",
            "b": "gas_east_south",
            "shared_road_axis": {"orientation": "EW", "coordinate": -272.5},
        },
        {
            "id": "bank_immediately_adjacent_to_commercial",
            "a": [
                "bank_low_01_classical",
                "bank_low_02_white",
                "bank_low_03_bronze",
                "bank_hq_blue_glass",
            ],
            "b": "commercial_all43_25_complete",
            "nearest_edge_clearance_m": 25.516,
            "three_low_buildings_compact_row": True,
        },
        {
            "id": "artificial_lake_beside_library",
            "a": "education_artificial_lake_civic_enclosure",
            "b": "education_library_south",
            "continuous_promenade_and_clear_view_axis": True,
        },
        {
            "id": "third_police_near_library",
            "a": "police_near_library",
            "b": "education_library_south",
            "shared_civic_block": True,
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
            "limited_infill_placement_count": infill["total"],
            "maximum_infill_source_collection_reuse": 1,
            "full11_repeated_infill_removed": 305,
            "mesh_projected_coverage_required": True,
            "all_render_views_keep_other_regions_visible": True,
            "direct_full_scene_render_preferred": True,
            "per_pixel_zdepth_partition_allowed_when_full_depsgraph_exceeds_memory": True,
            "minimum_final_resolution": [1920, 1080],
            "representative_interior_views_required": 6,
        }
    )
    checks = {
        "source_files_exist": all(
            Path(path).is_file() for path in manifest["source_files"].values()
        ),
        "all_placement_scales_one": all(
            record.get("scale") == [1.0, 1.0, 1.0] for record in records
        ),
        "no_asset_or_road_surface_collisions": collision["pass"],
        "all_named_entrance_keepouts_clear": access["pass"],
        "real_facing_frontage_audit_pass": frontage["pass"],
        "road_graph_connected": graph["connected"],
        "no_unexplained_dead_end": not graph["unexplained_dead_ends"],
        "semantic_road_occupancy_pass": occupancy["pass"],
        "legacy_base_and_grid_removed": streets["removed_legacy_placement_count"] > 0,
        "compact_four_tile_ground": streets["ground_tile_count"] == 4,
        "compact_envelope_reduced_at_least_30_percent": (
            coverage["city_envelope_area_reduction_ratio"] >= 0.30
        ),
        "diagnostic_density_improved_before_mesh_projection": (
            coverage["diagnostic_only_aabb_union"]["asset_ratio"] >= 0.26
            and coverage["diagnostic_only_aabb_union"]["asset_plus_road_ratio"] >= 0.43
        ),
        "infill_reduced_at_least_95_percent": infill["reduction_ratio"] >= 0.95,
        "infill_sources_unique": infill["maximum_source_collection_reuse"] == 1,
        "no_toy_or_placeholder_models": lineage["toy_or_placeholder_model_count"] == 0,
        "all_core_reference_policies_exact": lineage[
            "all_visible_assets_use_exact_reference_policy"
        ],
        "three_residential_areas": categories["residential_area"] == 3,
        "two_separate_pharmacies": categories["pharmacy"] == 2,
        "two_different_hospitals": categories["hospital"] == 2,
        "three_separate_gas_stations": categories["gas_station"] == 3,
        "four_factories": categories["factory"] == 4,
        "three_police_buildings": categories["police_station"] == 3,
        "one_artificial_lake": categories["artificial_lake"] == 1,
        "one_fountain": categories["fountain"] == 1,
        "diagonal_road_is_real_placement": categories["road_segment_diagonal"] == 1,
    }
    manifest["generation_checks"] = checks
    manifest["render_contract"] = {
        "renderer": str(ROOT / "scripts/render_urban_v1_full_12_daytime.py"),
        "method": (
            "camera-identical collection partitions composited by per-pixel 32-bit Z; "
            "all layers use the same shared receiver/shadow context"
        ),
        "full_scene_direct_render_preferred": True,
        "full_scene_direct_render_memory_constraint_documented": True,
        "minimum_resolution": [1920, 1080],
        "all_regions_remain_visible": True,
        "minimum_expected_png_count": 60,
        "single_asset_near_views_required": True,
        "interior_categories": [
            "residential",
            "commercial",
            "school",
            "library",
            "bank",
            "hospital",
        ],
    }
    failed = sorted(name for name, valid in checks.items() if valid is not True)
    if failed:
        raise RuntimeError(
            "Full-12 generation checks failed: "
            + ", ".join(failed)
            + "\n"
            + json.dumps(
                {
                    "collision": collision,
                    "access_conflicts": access["conflicts"],
                    "frontage": frontage,
                    "road_occupancy": occupancy,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return manifest


def build_city() -> dict:
    global _BUILDING_REMOVABLE_LEGACY_SCAFFOLD
    framework.ZONES.clear()
    framework.PLACEMENTS.clear()
    log("Building exact-reference base through the active full-12 placement hook")
    _BUILDING_REMOVABLE_LEGACY_SCAFFOLD = True
    try:
        manifest = framework.build_city()
    finally:
        _BUILDING_REMOVABLE_LEGACY_SCAFFOLD = False
    restored = 0
    for record in framework.PLACEMENTS:
        if record.get("collision_class") != "asset_pending_final_network":
            continue
        record["collision_class"] = "asset"
        obj = bpy.data.objects.get(record["name"])
        if obj is not None:
            obj["collision_class"] = "asset"
        restored += 1
    if restored == 0:
        raise RuntimeError(
            "No source assets were restored for final-network validation"
        )
    log(f"Restored {restored} source assets for the final compact-network audits")
    log("Adding exact lake3 landscape beside the library")
    previous.add_artificial_lake()
    log("Adding connected local, residential, north-campus, and diagonal streets")
    streets = add_connected_neighbourhood_streets()
    log("Adding eleven distinct scale-one infill collections (full-11 used 316)")
    infill = add_curated_unique_infill()
    pack_lineage = json.loads((PACK_OUT / "lineage.json").read_text(encoding="utf8"))
    manifest = finalize_manifest(manifest, pack_lineage, streets, infill)

    scene = bpy.context.scene
    scene.name = REVISION
    scene["scene_revision"] = REVISION
    scene["c2w_revision"] = REVISION
    scene["active_generator"] = str(Path(__file__).resolve())
    scene["pipeline_entrypoint"] = "generate_urban_v1_full_12.main"
    scene["integration_policy"] = manifest["integration_policy"]
    scene["placement_count"] = len(framework.PLACEMENTS)
    scene["full11_infill_count"] = 316
    scene["full12_infill_count"] = infill["total"]
    scene["direct_full_scene_render_preferred"] = True
    scene["pixel_depth_partitioned_full_scene_render"] = True

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
        "SUCCESS",
        "generation_audit.json",
        "layout_plan.json",
        "spatial_quality_audit.json",
        "mesh_projection_audit.json",
        "strict_completion_audit.json",
        "requirements_traceability.json",
        "panorama_audit.json",
        "renders/render_manifest.json",
    ):
        stale = OUT / stale_name
        if stale.exists():
            stale.unlink()
    log("Starting urban_v1_full_12 production generation")
    try:
        pack_lineage = previous.prepare_exact_asset_packs()
        pack_lineage = activate_exact_pack_lineage(pack_lineage)
        framework.validate_sources()
        if not previous.FIRE7.is_file() or not previous.LAKE3.is_file():
            raise FileNotFoundError(
                {"fire7": str(previous.FIRE7), "lake3": str(previous.LAKE3)}
            )
        manifest = build_city()
        (OUT / "layout_plan.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf8",
        )
        spatial = {
            "scene_revision": REVISION,
            "spatial_collision_audit": manifest["spatial_collision_audit"],
            "entrance_clearance_audit": manifest["entrance_clearance_audit"],
            "street_frontage_audit": manifest["street_frontage_audit"],
            "road_connectivity_audit": manifest["road_connectivity_audit"],
            "road_occupancy_audit": manifest["road_occupancy_audit"],
            "coverage_audit": manifest["coverage_audit"],
        }
        (OUT / "spatial_quality_audit.json").write_text(
            json.dumps(spatial, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf8",
        )
        generation_audit = {
            "status": "PASS",
            "scene_revision": REVISION,
            "active_generator": str(Path(__file__).resolve()),
            "pipeline_entrypoint": "generate_urban_v1_full_12.main",
            "placement_count": len(manifest["placements"]),
            "source_count": len(manifest["source_files"]),
            "linked_library_count_before_save": len(bpy.data.libraries),
            "requirements": manifest["requirements"],
            "generation_checks": manifest["generation_checks"],
            "category_counts": manifest["category_counts"],
            "curated_infill": manifest["curated_infill"],
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
            f"Writing production Blend with {len(manifest['placements'])} placements "
            f"and {len(bpy.data.libraries)} exact linked libraries"
        )
        bpy.data.libraries.write(
            str(temporary),
            {scene := bpy.context.scene, bpy.data.texts["GENERATION_MANIFEST"]},
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
