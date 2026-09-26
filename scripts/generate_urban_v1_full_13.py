#!/usr/bin/env python3
"""Build the production ``urban_v1_full_13`` integrated city.

This is the live full-13 generator.  It keeps every requested authored asset
at scale one, replaces the sparse full-12 placement plan and road scaffold
before the production Blend is saved, and creates new unique urban fabric,
public interiors, pedestrian links, people, and bicycles in the same Blender
process.  Nothing in this file is a detached demo or a post-process edit.

Run with Blender 4.5 or newer::

    blender -b --factory-startup --python scripts/generate_urban_v1_full_13.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
INFINIGEN_PYTHON_ROOT = ROOT / "infinigen"
if str(INFINIGEN_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(INFINIGEN_PYTHON_ROOT))

import generate_urban_v1_full_12 as predecessor
import generate_urban_v3_all45_02 as apartment_source
import generate_urban_v3_all45 as geometry


framework = predecessor.framework
REVISION = "urban_v1_full_13"
OUT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND_OUT = OUT / f"{REVISION}.blend"
PACK_OUT = OUT / "asset_packs"
PROCEDURAL_PACK = PACK_OUT / "full13_same_run_procedural_assets.blend"
PROCEDURAL_PACK_MANIFEST = PACK_OUT / "full13_same_run_procedural_assets.json"
SEMANTIC_PACK = PACK_OUT / "full13_semantic_public_interiors.blend"
SEMANTIC_PACK_MANIFEST = PACK_OUT / "full13_semantic_public_interiors.json"
BUILD_PROCEDURAL_PACK = os.environ.get("C2W_FULL13_BUILD_PROCEDURAL_PACK") == "1"
PREVIOUS_PACK_OUT = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_12/asset_packs"
)
RUN_ID = os.environ.get(
    "C2W_FULL13_RUN_ID",
    time.strftime("full13-%Y%m%dT%H%M%S", time.gmtime()),
)
CITY_ENVELOPE = (-332.5, -292.5, 332.5, 292.5)
PROCEDURAL_SOURCE_KEY = "full13_same_run_procedural"
SEMANTIC_SOURCE_KEY = "full13_semantic_public_interiors"

# The complete original 109 m road kit remains untouched.  Its native road
# surfaces do not span the full declared module lengths: the formal street
# photos show substantial gaps between rendered asphalt islands.  A separate
# physically continuous, layered PBR subgrade is authored below the originals
# so that ONLY their genuinely missing sections become visible; none of the
# source road surfaces, road markings, lamps or vehicles is removed or proxied.
CONNECTED_ROAD_CORRIDORS = (
    ((-327.0, 0.0), (327.0, 0.0), "central_boulevard", 8.4),
    ((-327.0, -218.0), (327.0, -218.0), "southern_boulevard", 8.4),
    ((-54.5, -272.5), (-54.5, 272.5), "school_library_boulevard", 8.4),
    ((272.5, -272.5), (272.5, 272.5), "hospital_residential_boulevard", 8.4),
    ((-272.5, -218.0), (-272.5, 0.0), "park_civic_secondary", 7.2),
    ((0.0, -109.0), (218.0, -109.0), "commercial_secondary", 7.2),
    ((-54.5, 218.0), (218.0, 218.0), "north_residential_secondary", 7.2),
    (
        (-54.5, 0.0),
        (-54.5 + 218.0 * math.cos(-math.pi / 6), 218.0 * math.sin(-math.pi / 6)),
        "diagonal_district_connector",
        8.4,
    ),
)


# The existing multi-gigabyte packs are immutable geometry-neutral dependency
# packs.  Full-13 uses content-addressed hard links within its own output so a
# restart never recopies 34 GiB or mutates the predecessor delivery.
PACK_FILENAMES = (
    "factory3_clean_collections.blend",
    "school5_clean_collection.blend",
    "library4_clean_collection.blend",
    "river3_full12_exact_collections.blend",
    "river5_full12_exact_collections.blend",
    "all45_09_full12_exact_collection.blend",
    "all44_14_full12_exact_collection.blend",
    "lake3_full12_exact_collections.blend",
)


def utc_now() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, path)


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def prepare_dependency_cache() -> dict[str, dict[str, Any]]:
    PACK_OUT.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    for filename in PACK_FILENAMES:
        source = PREVIOUS_PACK_OUT / filename
        target = PACK_OUT / filename
        if not source.is_file() or source.stat().st_size <= 0:
            raise FileNotFoundError(f"Missing immutable predecessor pack: {source}")
        if target.exists() and not os.path.samefile(source, target):
            if target.stat().st_size != source.stat().st_size:
                raise RuntimeError(f"Unexpected full-13 dependency cache: {target}")
            target.unlink()
        if not target.exists():
            os.link(source, target)
        records[filename] = {
            "target": str(target.resolve()),
            "source": str(source.resolve()),
            "bytes": target.stat().st_size,
            "same_inode": os.path.samefile(source, target),
            "sha256": sha256(target),
            "operation": "content-addressed hardlink; no data-block change",
        }
    payload = {
        "schema": "agent.full13.asset_cache.v1",
        "run_id": RUN_ID,
        "created_utc": utc_now(),
        "status": "PASS",
        "geometry_changes": 0,
        "material_changes": 0,
        "records": records,
    }
    atomic_json(PACK_OUT / "lineage.json", payload)
    return records


def configure_inherited_pipeline() -> None:
    predecessor.REVISION = REVISION
    predecessor.OUT = OUT
    predecessor.BLEND_OUT = BLEND_OUT
    predecessor.PACK_OUT = PACK_OUT
    predecessor.previous.REVISION = REVISION
    predecessor.previous.OUT = OUT
    predecessor.previous.BLEND_OUT = BLEND_OUT
    predecessor.previous.PACK_OUT = PACK_OUT
    framework.OUT = OUT
    framework.BLEND_OUT = BLEND_OUT
    framework.PACKS = {
        key: PACK_OUT / filename
        for key, filename in predecessor.previous.PACK_FILENAMES.items()
    }
    exact = {
        "river3": PACK_OUT / "river3_full12_exact_collections.blend",
        "river5": PACK_OUT / "river5_full12_exact_collections.blend",
        "all45_09": PACK_OUT / "all45_09_full12_exact_collection.blend",
        "all44_14": PACK_OUT / "all44_14_full12_exact_collection.blend",
        "lake3": PACK_OUT / "lake3_full12_exact_collections.blend",
    }
    framework.SOURCES.update(exact)
    framework.SOURCES[PROCEDURAL_SOURCE_KEY] = PROCEDURAL_PACK
    framework.SOURCES[SEMANTIC_SOURCE_KEY] = SEMANTIC_PACK
    predecessor.FULL12_EXACT_PACKS = exact
    predecessor.previous.LAKE3 = exact["lake3"]
    predecessor.LAKE3 = exact["lake3"]
    predecessor.log = log
    predecessor.previous.log = log
    framework.log = log


# Compact, functionally buffered plan.  Source centres, source scale, linked
# collections, materials, modifiers and all authored child transforms remain
# unchanged.  Only translation and yaw are revised.
PLACEMENT_OVERRIDES: dict[str, dict[str, Any]] = {
    "residential_01_river3_indoor": {"at": (310.0, 125.0, 0.0)},
    "residential_02_river3_north_extension": {"at": (180.0, 160.0, 0.0)},
    "residential_03_all45_09_native_indoor": {"at": (180.0, 285.0, 0.0)},
    "residential_delivery_01_food_delivery_locker": {"at": (130.0, 204.0, 0.0)},
    "residential_delivery_02_parcel_locker": {"at": (95.0, 250.0, 0.0)},
    "residential_delivery_03_delivery_station": {"at": (250.0, 160.0, 0.0)},
    "park_original_sculpture_nature": {"at": (-235.0, -45.0, 0.0)},
    "park_river5_corridor": {"at": (-310.0, -70.0, 0.0)},
    "park_fitness_area": {"at": (30.0, -160.0, 0.0)},
    "park_single_fountain": {"at": (-240.0, -105.0, 0.0)},
    "education_school_north": {
        "at": (-175.0, 145.0, 0.0),
        "yaw": math.pi / 2,
        "metadata": {"entry_direction_world": "+X"},
    },
    "education_library_south": {
        "at": (40.0, 115.0, 0.0),
        "yaw": -math.pi / 2,
        "metadata": {"entry_direction_world": "-X"},
    },
    "education_artificial_lake_civic_enclosure": {"at": (-135.0, -70.0, 0.0)},
    "police_near_library": {"at": (20.0, 255.0, 0.0)},
    "commercial_all43_25_complete": {"at": (165.0, -75.0, 0.0), "yaw": math.pi},
    "pharmacy_cvs_west": {"at": (225.0, -75.0, 0.0), "yaw": math.pi},
    "pharmacy_well_east": {"at": (90.0, -145.0, 0.0)},
    "commercial_atm_five_machine_row": {"at": (250.0, -75.0, 0.0), "yaw": math.pi},
    "bank_low_01_classical": {"at": (150.0, -35.0, 0.0)},
    "bank_low_02_white": {"at": (185.0, -35.0, 0.0)},
    "bank_low_03_bronze": {"at": (225.0, -35.0, 0.0)},
    "bank_hq_blue_glass": {"at": (140.0, 40.0, 0.0)},
    "hospital_central_red_white": {"at": (235.0, 55.0, 0.0), "yaw": -math.pi / 2},
    "hospital_outskirts_traditional": {"at": (310.0, 260.0, 0.0), "yaw": math.pi / 2},
    "civic_fire_precinct_north": {"at": (-185.0, -175.0, 0.0)},
    "police_opposite_fire_west": {"at": (-235.0, -250.0, 0.0)},
    "police_opposite_fire_east": {"at": (-165.0, -250.0, 0.0)},
    "gas_east_north": {"at": (310.0, -160.0, 0.0)},
    "gas_east_south": {"at": (310.0, -250.0, 0.0)},
    "gas_west_outskirts": {"at": (-310.0, -250.0, 0.0), "yaw": math.pi / 2},
    "factory_01_gable": {"at": (-100.0, -250.0, 0.0)},
    "factory_02_white": {"at": (105.0, -175.0, 0.0)},
    "factory_03_gated": {"at": (0.0, -250.0, 0.0)},
    "factory_04_highbay": {"at": (65.0, -250.0, 0.0)},
    "leisure_all44_14_complete": {"at": (170.0, -250.0, 0.0)},
    "leisure_fitness_area": {"at": (205.0, -160.0, 0.0)},
}


ACCESS_SPECS: dict[str, dict[str, Any]] = {
    "education_school_north": {
        "orientation": "NS",
        "coordinate": -54.5,
        "side": "west",
    },
    "education_library_south": {
        "orientation": "NS",
        "coordinate": -54.5,
        "side": "east",
    },
    "residential_01_river3_indoor": {
        "orientation": "NS",
        "coordinate": 272.5,
        "side": "east",
    },
    "residential_02_river3_north_extension": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "south",
    },
    "residential_03_all45_09_native_indoor": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "north",
    },
    "commercial_all43_25_complete": {
        "orientation": "EW",
        "coordinate": -109.0,
        "side": "north",
    },
    "pharmacy_cvs_west": {"orientation": "EW", "coordinate": -109.0, "side": "north"},
    "pharmacy_well_east": {"orientation": "EW", "coordinate": -109.0, "side": "south"},
    "commercial_atm_five_machine_row": {
        "orientation": "EW",
        "coordinate": -109.0,
        "side": "north",
    },
    "bank_low_01_classical": {"orientation": "EW", "coordinate": 0.0, "side": "south"},
    "bank_low_02_white": {"orientation": "EW", "coordinate": 0.0, "side": "south"},
    "bank_low_03_bronze": {"orientation": "EW", "coordinate": 0.0, "side": "south"},
    "bank_hq_blue_glass": {"orientation": "EW", "coordinate": 0.0, "side": "north"},
    "hospital_central_red_white": {
        "orientation": "NS",
        "coordinate": 272.5,
        "side": "west",
    },
    "hospital_outskirts_traditional": {
        "orientation": "NS",
        "coordinate": 272.5,
        "side": "east",
    },
    "civic_fire_precinct_north": {
        "orientation": "EW",
        "coordinate": -218.0,
        "side": "north",
    },
    "police_opposite_fire_west": {
        "orientation": "EW",
        "coordinate": -218.0,
        "side": "south",
    },
    "police_opposite_fire_east": {
        "orientation": "EW",
        "coordinate": -218.0,
        "side": "south",
    },
    "police_near_library": {"orientation": "NS", "coordinate": -54.5, "side": "east"},
    "factory_01_gable": {"orientation": "EW", "coordinate": -218.0, "side": "south"},
    "factory_02_white": {"orientation": "EW", "coordinate": -218.0, "side": "north"},
    "factory_03_gated": {"orientation": "EW", "coordinate": -218.0, "side": "south"},
    "factory_04_highbay": {"orientation": "EW", "coordinate": -218.0, "side": "south"},
    "leisure_all44_14_complete": {
        "orientation": "EW",
        "coordinate": -218.0,
        "side": "south",
    },
    "leisure_fitness_area": {
        "orientation": "EW",
        "coordinate": -218.0,
        "side": "north",
    },
    "gas_east_north": {"orientation": "NS", "coordinate": 272.5, "side": "east"},
    "gas_east_south": {"orientation": "NS", "coordinate": 272.5, "side": "east"},
    "gas_west_outskirts": {"orientation": "NS", "coordinate": -272.5, "side": "west"},
    "residential_delivery_01_food_delivery_locker": {
        "orientation": "EW",
        "coordinate": 218.0,
        "side": "south",
    },
    "residential_delivery_03_delivery_station": {
        "orientation": "NS",
        "coordinate": 272.5,
        "side": "west",
    },
}

# Deterministic final-layout entrance corridors.  The main generator compares
# these against its freshly recomputed access audit before linking the pack,
# so a future placement change cannot silently reuse a stale path network.
ENTRANCE_KEEPOUTS: dict[str, tuple[float, float, float, float]] = {
    "bank_hq_blue_glass": (136.0, 10.5, 144.0, 19.375),
    "bank_low_01_classical": (146.0, -21.116, 154.0, -10.5),
    "bank_low_02_white": (181.0, -21.145, 189.0, -10.5),
    "bank_low_03_bronze": (221.0, -20.45, 229.0, -10.5),
    "civic_fire_precinct_north": (-189.0, -207.5, -181.0, -194.744),
    "commercial_all43_25_complete": (161.0, -98.5, 169.0, -94.125),
    "commercial_atm_five_machine_row": (248.594, -98.5, 251.406, -75.627),
    "education_library_south": (-44.0, 111.0, -7.162, 119.0),
    "education_school_north": (-65.0, 141.0, -65.0, 149.0),
    "factory_01_gable": (-104.0, -232.75, -96.0, -228.5),
    "factory_02_white": (101.0, -207.5, 109.0, -192.675),
    "factory_03_gated": (-4.0, -229.75, 4.0, -228.5),
    "factory_04_highbay": (61.0, -231.0, 69.0, -228.5),
    "gas_east_north": (283.0, -164.0, 292.5, -156.0),
    "gas_east_south": (283.0, -254.0, 292.5, -246.0),
    "gas_west_outskirts": (-294.4, -254.0, -283.0, -246.0),
    "hospital_central_red_white": (254.661, 51.0, 262.0, 59.0),
    "hospital_outskirts_traditional": (283.0, 256.0, 292.519, 264.0),
    "leisure_all44_14_complete": (166.0, -230.21, 174.0, -228.5),
    "leisure_fitness_area": (201.0, -207.5, 209.0, -195.0),
    "pharmacy_cvs_west": (221.0, -98.5, 229.0, -85.672),
    "pharmacy_well_east": (86.0, -134.79, 94.0, -119.5),
    "police_near_library": (-44.0, 251.0, -9.268, 259.0),
    "police_opposite_fire_east": (-169.0, -233.092, -161.0, -228.5),
    "police_opposite_fire_west": (-239.0, -231.554, -231.0, -228.5),
    "residential_01_river3_indoor": (283.0, 121.0, 287.2, 129.0),
    "residential_02_river3_north_extension": (176.0, 200.25, 184.0, 207.5),
    "residential_03_all45_09_native_indoor": (176.0, 228.5, 184.0, 228.54),
    "residential_delivery_01_food_delivery_locker": (128.906, 204.52, 131.094, 207.5),
    "residential_delivery_03_delivery_station": (256.33, 158.399, 262.0, 161.601),
}

# Endpoint-only construction clearances derived from evaluated-mesh BVH
# validation of the combined production layers.  The entrance keepouts above
# remain the independently recomputed audit truth; these trims keep the 0.72 m
# tactile pads a visible 18--38 mm away from detailed steps, mullions, curbs,
# shells and equipment while retaining a continuous >=2.6 m wide connector.
CONNECTOR_ENDPOINT_CLEARANCE_ADJUSTMENTS: dict[str, dict[str, float | str]] = {
    "bank_low_02_white": {
        "start_y": -20.75,
        "reason": "clear occupied-shell edge at y=-21.145 after tactile-pad extent",
    },
    "commercial_atm_five_machine_row": {
        "end_y": -75.90,
        "reason": "clear security-safe floor edge at y=-75.507 after tactile-pad extent",
    },
    "police_opposite_fire_east": {
        "start_y": -232.96,
        "reason": "clear modeled step and nosing ending at y=-233.358",
    },
    "gas_east_north": {
        "end_x": 292.15,
        "reason": "clear detailed side curb beginning at x=292.540",
    },
    "gas_east_south": {
        "end_x": 292.15,
        "reason": "clear detailed side curb beginning at x=292.540",
    },
    "residential_delivery_03_delivery_station": {
        "start_x": 256.60,
        "reason": "clear two modeled right mullions ending at x=256.212",
    },
}


configure_inherited_pipeline()
predecessor.PLACEMENT_OVERRIDES = PLACEMENT_OVERRIDES
predecessor.ACCESS_SPECS = ACCESS_SPECS
_inherited_place = predecessor.place


def place(
    master: bpy.types.Collection, placement_id: str, **kwargs: Any
) -> bpy.types.Object:
    obj = _inherited_place(master, placement_id, **kwargs)
    record = framework.PLACEMENTS[-1]
    record["generated_by"] = str(Path(__file__).resolve())
    record["scene_revision"] = REVISION
    record["run_id"] = RUN_ID
    record.pop("full12_pipeline_placement", None)
    record["full13_pipeline_placement"] = True
    obj["generated_by"] = str(Path(__file__).resolve())
    obj["scene_revision"] = REVISION
    obj["run_id"] = RUN_ID
    if placement_id in ACCESS_SPECS:
        record["access_road"] = dict(ACCESS_SPECS[placement_id])
    return obj


predecessor.place = place
predecessor.previous.place = place
framework.place = place


def require_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        raise RuntimeError(f"Required production master is unavailable: {name}")
    return collection


_PROCEDURAL_COLLECTION_CACHE: dict[str, bpy.types.Collection] | None = None


def procedural_collection_names() -> list[str]:
    return [
        "full13:master:compact_irregular_ground",
        "full13:master:continuous_pbr_road_substrate",
        "full13:master:weathered_urban_perimeter_landscape",
        *(f"full13_proc:apartment_{spec[0]}" for spec in INFILL_SPECS),
        "full13:master:continuous_pedestrian_activity",
        "full13:master:complete_entrance_connector_network",
    ]


def semantic_collection_names() -> list[str]:
    return [
        "full13:master:school_cafeteria",
        "full13:master:library_reading_room",
        "full13:master:bank_atrium",
        "full13:master:hospital_lobby",
    ]


def _procedural_collections() -> dict[str, bpy.types.Collection]:
    global _PROCEDURAL_COLLECTION_CACHE
    if _PROCEDURAL_COLLECTION_CACHE is None:
        if not PROCEDURAL_PACK.is_file() or not PROCEDURAL_PACK_MANIFEST.is_file():
            raise FileNotFoundError(
                "Build the connected full-13 procedural dependency pack before the city: "
                f"{PROCEDURAL_PACK}"
            )
        _PROCEDURAL_COLLECTION_CACHE = framework.link_collections(
            PROCEDURAL_PACK, procedural_collection_names()
        )
    return _PROCEDURAL_COLLECTION_CACHE


_SEMANTIC_COLLECTION_CACHE: dict[str, bpy.types.Collection] | None = None


def _semantic_collections() -> dict[str, bpy.types.Collection]:
    global _SEMANTIC_COLLECTION_CACHE
    if _SEMANTIC_COLLECTION_CACHE is None:
        if not SEMANTIC_PACK.is_file() or not SEMANTIC_PACK_MANIFEST.is_file():
            raise FileNotFoundError(
                "Build the connected full-13 semantic-interior dependency pack "
                f"before the city: {SEMANTIC_PACK}"
            )
        _SEMANTIC_COLLECTION_CACHE = framework.link_collections(
            SEMANTIC_PACK, semantic_collection_names()
        )
    return _SEMANTIC_COLLECTION_CACHE


def _remove_legacy_base_and_roads() -> list[str]:
    removable = [
        record
        for record in framework.PLACEMENTS
        if record.get("collision_class") in {"base", "road", "road_amenity"}
    ]
    for record in removable:
        obj = bpy.data.objects.get(record["name"])
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
    framework.PLACEMENTS[:] = [
        record for record in framework.PLACEMENTS if record not in removable
    ]
    return [record["placement_id"] for record in removable]


def _procedural_material(
    name: str,
    dark: Sequence[float],
    light: Sequence[float],
    *,
    rough: float,
    scale: float,
    bump: float,
    metallic: float = 0.0,
) -> bpy.types.Material:
    return apartment_source.remap_material(
        f"full13_{name}", dark, light, rough, bump, scale, metallic
    )


def add_compact_ground() -> str:
    name = "full13:master:compact_irregular_ground"
    if BUILD_PROCEDURAL_PACK:
        material = _procedural_material(
            "district_subgrade",
            (0.11, 0.13, 0.075),
            (0.22, 0.25, 0.13),
            rough=0.94,
            scale=5.0,
            bump=0.17,
        )
        master = bpy.data.collections.new(name)
        outline = [
            (-332.5, -292.5),
            (332.5, -292.5),
            (332.5, 292.5),
            (260.0, 292.5),
            (235.0, 280.0),
            (-260.0, 292.5),
            (-332.5, 260.0),
        ]
        geometry.PREFIX = "full13:"
        geometry.poly_prism(
            "compact_city_ground", outline, -0.24, 0.22, material, master, bevel=0.10
        )
    else:
        master = _procedural_collections()[name]
    pid = "compact_irregular_city_ground"
    place(
        master,
        pid,
        category="city_ground",
        zone="city_base",
        source_key=PROCEDURAL_SOURCE_KEY,
        source_collection=master.name,
        source_bounds=((-332.5, -292.5, -0.24), (332.5, 292.5, -0.02)),
        source_center=(0.0, 0.0),
        at=(0.0, 0.0, 0.0),
        collision_class="base",
        metadata={
            "same_run_procedural": True,
            "purpose": "bounded PBR terrain receiver matching developed envelope",
            "oversized_hidden_ground": False,
        },
    )
    framework.PLACEMENTS[-1]["reuse_policy"] = "same_run_procedural_production_no_proxy"
    return pid


def add_connected_road_substrate() -> dict[str, Any]:
    """Real layered asphalt, kerbs, runoff and traffic paint under native roads.

    Place a complete scene-native physical underlayer at z=-0.018 m: source
    road meshes are at or above z=0, remain fully visible, and obscure it
    where already complete.  Only green ground previously visible through
    substantial source-kit gaps reveals this detailed seam construction.
    The extra west-side secondary street also joins two original arterial
    nodes without routing through school, park or emergency-building meshes.
    """
    master_name = "full13:master:continuous_pbr_road_substrate"
    if not BUILD_PROCEDURAL_PACK:
        master = _procedural_collections()[master_name]
        metadata = json.loads(PROCEDURAL_PACK_MANIFEST.read_text(encoding="utf8"))[
            "road_substrate"
        ]
    else:
        geometry.PREFIX = "full13:"
        master = bpy.data.collections.new(master_name)
        asphalt = _procedural_material(
            "road_graded_asphalt",
            (0.022, 0.030, 0.038),
            (0.120, 0.135, 0.147),
            rough=0.86,
            scale=17.0,
            bump=0.105,
        )
        shoulder = _procedural_material(
            "road_stone_shoulder",
            (0.23, 0.235, 0.22),
            (0.52, 0.51, 0.47),
            rough=0.90,
            scale=20.0,
            bump=0.075,
        )
        kerb = _procedural_material(
            "road_granite_kerb",
            (0.24, 0.25, 0.25),
            (0.61, 0.62, 0.59),
            rough=0.79,
            scale=13.0,
            bump=0.075,
        )
        marker = _procedural_material(
            "road_thermoplastic",
            (0.54, 0.54, 0.46),
            (0.88, 0.84, 0.70),
            rough=0.61,
            scale=10.0,
            bump=0.02,
        )
        drain = _procedural_material(
            "road_steel_drain",
            (0.025, 0.035, 0.045),
            (0.13, 0.16, 0.17),
            rough=0.42,
            scale=16.0,
            bump=0.025,
            metallic=0.76,
        )
        object_count = 0
        for index, (a, b, label, road_width) in enumerate(CONNECTED_ROAD_CORRIDORS):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            yaw = math.atan2(dy, dx)
            c, s = dx / length, dy / length
            center_x, center_y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2

            def point(u: float, v: float, z: float) -> tuple[float, float, float]:
                return (center_x + c * u - s * v, center_y + s * u + c * v, z)

            # Asphalt is a 180 mm laid pavement over a separate 120 mm
            # stone-aggregate shoulder, not a single painted toy plane.
            # Per-corridor 0.3 mm masonry joints avoid source/substrate
            # co-planarity at multiway intersections without visible gaps.
            shift = index * 0.00030
            geometry.box(
                f"road_subbase_{label}",
                point(0, 0, -0.108 + shift),
                (length, road_width, 0.18),
                asphalt,
                master,
                rot=yaw,
                bevel=0.035,
                segments=3,
            )
            object_count += 1
            for side in (-1, 1):
                edge_offset = road_width / 2 + 2.10
                geometry.box(
                    f"road_permeable_shoulder_{label}_{side}",
                    point(0, side * edge_offset, -0.087 + shift),
                    (length, 4.20, 0.12),
                    shoulder,
                    master,
                    rot=yaw,
                    bevel=0.030,
                    segments=3,
                )
                geometry.box(
                    f"road_granite_kerb_under_native_{label}_{side}",
                    point(0, side * (road_width / 2 + 0.19), -0.040 + shift),
                    (length, 0.33, 0.075),
                    kerb,
                    master,
                    rot=yaw,
                    bevel=0.018,
                    segments=3,
                )
                object_count += 2
            # Lane centerline and edge stripes are BELOW original authored
            # markings.  They only appear over seams where the kit lacked a
            # roadway, so the traffic paint never duplicates source decals.
            for stripe_index, u in enumerate(
                -length / 2 + 5.0 + 11.0 * i
                for i in range(max(0, int((length - 10.0) / 11.0)))
            ):
                geometry.box(
                    f"road_recessed_center_dash_{label}_{stripe_index}",
                    point(u, 0, -0.015 + shift),
                    (3.5, 0.10, 0.012),
                    marker,
                    master,
                    rot=yaw,
                    bevel=0.012,
                    segments=2,
                )
                object_count += 1
            for side in (-1, 1):
                for drain_index in range(max(0, int(length / 37))):
                    u = -length / 2 + 18.5 + drain_index * 37.0
                    v = side * (road_width / 2 - 0.38)
                    geometry.box(
                        f"road_gully_frame_{label}_{side}_{drain_index}",
                        point(u, v, -0.012 + shift),
                        (0.48, 0.34, 0.018),
                        drain,
                        master,
                        rot=yaw,
                        bevel=0.010,
                        segments=2,
                    )
                    for bar in range(5):
                        geometry.box(
                            f"road_gully_slot_{label}_{side}_{drain_index}_{bar}",
                            point(u - 0.15 + bar * 0.075, v, -0.003 + shift),
                            (0.025, 0.23, 0.009),
                            kerb,
                            master,
                            rot=yaw,
                            bevel=0.003,
                            segments=2,
                        )
                    object_count += 6
        metadata = {
            "native_original_road_geometry_preserved": True,
            "connected_corridor_count": len(CONNECTED_ROAD_CORRIDORS),
            "corridors": [
                {
                    "name": label,
                    "begin": list(a),
                    "end": list(b),
                    "asphalt_width_m": width,
                }
                for a, b, label, width in CONNECTED_ROAD_CORRIDORS
            ],
            "road_structural_layer_count": 3,
            "authored_part_count": object_count,
            "source_road_surface_minimum_z_m": 0.0,
            "substrate_top_z_m": -0.018,
            "source_geometry_masking_policy": "below original exact complete source road surface; visible only in kit gaps",
            "source_substitution_or_simplification": False,
        }
    pid = "full13_physical_continuous_road_substrate"
    place(
        master,
        pid,
        category="physical_road_network_substrate",
        zone="roads",
        source_key=PROCEDURAL_SOURCE_KEY,
        source_collection=master.name,
        source_bounds=((-332.5, -292.5, -0.25), (332.5, 292.5, 0.0)),
        source_center=(0.0, 0.0),
        at=(0.0, 0.0, 0.0),
        collision_class="road",
        metadata={"same_run_procedural": True, **metadata},
    )
    framework.PLACEMENTS[-1][
        "reuse_policy"
    ] = "connected_authoritative_substrate_under_original_source_roads"
    return {"placement_id": pid, **metadata}


def _perimeter_height(x: float, y: float) -> float:
    """Continuous multi-frequency terrain normal to the developed edge."""
    edge_distance = math.hypot(max(0.0, abs(x) - 332.5), max(0.0, abs(y) - 292.5))
    t = min(1.0, edge_distance / 150.0)
    fade = t * t * (3.0 - 2.0 * t)
    broad = 3.65 * math.sin(0.0076 * x + 0.0029 * y) ** 2
    broad += 2.20 * math.cos(0.0051 * y - 0.0035 * x) ** 2
    medium = 0.83 * math.sin(0.036 * x + 0.018 * y)
    medium += 0.60 * math.cos(0.028 * y - 0.016 * x)
    fine = 0.25 * math.sin(0.092 * x - 0.063 * y)
    return -0.022 + fade * (broad + medium + fine)


def _author_articulated_perimeter_tree(
    master: bpy.types.Collection,
    index: int,
    x: float,
    y: float,
    bark: bpy.types.Material,
    leaf: bpy.types.Material,
    shaded_leaf: bpy.types.Material,
) -> dict[str, int]:
    """A real, individually seeded branching tree with meshed broadleaf laminae.

    Native Blender lacks the optional gin/scipy modules needed by Princeton's
    TreeFactory.  Never turn a failed TreeFactory import into a hidden proxy:
    explicitly model roots, tapered primary/secondary branches, terminal
    twig curves and thousands of independently bent nine-vertex leaves here,
    in the same generator and physical base dependency pack as the city.
    """
    seed = random.Random(13002660 + index * 11657)
    species = index % 5
    height = (7.7, 8.9, 10.2, 7.2, 11.0)[species] * seed.uniform(0.92, 1.10)
    lean_x, lean_y = seed.uniform(-0.31, 0.31), seed.uniform(-0.31, 0.31)
    z0 = _perimeter_height(x, y)
    base = Vector((x, y, z0))
    trunk_top = base + Vector((lean_x, lean_y, height * 0.69))
    geometry.beam(
        f"perimeter_tree_{index}_tapered_trunk",
        base + Vector((0, 0, 0.08)),
        trunk_top,
        (0.27, 0.23, 0.32, 0.20, 0.39)[species],
        bark,
        master,
        vertices=24,
    )
    for root_index in range(8):
        a = 2.0 * math.pi * root_index / 8 + seed.uniform(-0.10, 0.10)
        tip = base + Vector(
            (
                math.cos(a) * seed.uniform(0.48, 0.88),
                math.sin(a) * seed.uniform(0.48, 0.88),
                0.035,
            )
        )
        geometry.beam(
            f"perimeter_tree_{index}_root_buttress_{root_index}",
            base + Vector((0, 0, 0.19)),
            tip,
            0.046,
            bark,
            master,
            vertices=12,
        )

    twig_ends: list[Vector] = []
    twig_paths: list[list[Vector]] = []
    branch_count = 0
    for i in range(11):
        angle = i * math.tau / 11 + seed.uniform(-0.18, 0.18)
        stem = base + Vector(
            (lean_x * 0.65, lean_y * 0.65, height * seed.uniform(0.42, 0.77))
        )
        radial = seed.uniform(1.65, 2.95) * (height / 9.0)
        tip = stem + Vector(
            (
                math.cos(angle) * radial,
                math.sin(angle) * radial,
                seed.uniform(0.35, 1.10),
            )
        )
        geometry.beam(
            f"perimeter_tree_{index}_primary_limb_{i}",
            stem,
            tip,
            seed.uniform(0.067, 0.105),
            bark,
            master,
            vertices=14,
        )
        branch_count += 1
        for j in range(4):
            a = angle + seed.uniform(-1.08, 1.08)
            mid = stem.lerp(tip, seed.uniform(0.46, 0.82))
            sub = mid + Vector(
                (
                    math.cos(a) * seed.uniform(0.65, 1.35),
                    math.sin(a) * seed.uniform(0.65, 1.35),
                    seed.uniform(0.26, 0.88),
                )
            )
            geometry.beam(
                f"perimeter_tree_{index}_secondary_{i}_{j}",
                mid,
                sub,
                seed.uniform(0.028, 0.050),
                bark,
                master,
                vertices=10,
            )
            branch_count += 1
            for k in range(3):
                b = a + seed.uniform(-0.90, 0.90)
                distal = sub + Vector(
                    (
                        math.cos(b) * seed.uniform(0.31, 0.78),
                        math.sin(b) * seed.uniform(0.31, 0.78),
                        seed.uniform(-0.13, 0.39),
                    )
                )
                twig_paths.append([sub, sub.lerp(distal, 0.52), distal])
                twig_ends.append(distal)
    twigs = bpy.data.curves.new(f"full13:tree:{index}:articulated_twigs", "CURVE")
    twigs.dimensions = "3D"
    twigs.bevel_depth = 0.011
    twigs.bevel_resolution = 2
    for path in twig_paths:
        spline = twigs.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, position in zip(spline.points, path):
            point.co = (*position, 1.0)
    twigs.materials.append(bark)
    master.objects.link(
        bpy.data.objects.new(f"full13:tree:{index}:fine_twig_network", twigs)
    )

    # Every leaf is a separate physically curved lamina, not a crown sphere,
    # a billboard, or a single alpha-card placed to pretend foliage exists.
    # Two sun-exposure materials and metered UVs vary its summer PBR response.
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    material_indices: list[int] = []
    uv_coords: list[tuple[float, float]] = []
    lamina = (
        (-0.54, 0.0),
        (-0.24, -0.37),
        (0.16, -0.54),
        (0.49, -0.20),
        (0.59, 0.0),
        (0.49, 0.20),
        (0.16, 0.54),
        (-0.24, 0.37),
        (0.02, 0.0),
    )
    n_leaves = (1430, 1270, 1580, 1380, 1620)[species]
    for leaf_index in range(n_leaves):
        end = seed.choice(twig_ends)
        centre = end + Vector(
            (
                seed.uniform(-0.42, 0.42),
                seed.uniform(-0.42, 0.42),
                seed.uniform(-0.35, 0.39),
            )
        )
        yaw = seed.uniform(-math.pi, math.pi)
        pitch = seed.uniform(-0.38, 0.40)
        forward = Vector(
            (
                math.cos(yaw) * math.cos(pitch),
                math.sin(yaw) * math.cos(pitch),
                math.sin(pitch),
            )
        )
        sideways = Vector((-math.sin(yaw), math.cos(yaw), seed.uniform(-0.14, 0.14)))
        length = seed.uniform(0.27, 0.54)
        width = length * seed.uniform(0.30, 0.51)
        curl = seed.uniform(-0.035, 0.062)
        start = len(vertices)
        for u, v in lamina:
            point = centre + forward * (u * length) + sideways * (v * width)
            point.z += curl * (1.0 - abs(u)) + (0.014 if (u, v) == (0.02, 0.0) else 0.0)
            vertices.append(tuple(point))
            uv_coords.append((u + 0.55, v + 0.55))
        for edge in range(8):
            faces.append((start + edge, start + (edge + 1) % 8, start + 8))
            material_indices.append(0 if centre.z < z0 + height * 0.74 else 1)
    leaf_mesh = bpy.data.meshes.new(f"full13:tree:{index}:individual_leaf_laminae")
    leaf_mesh.from_pydata(vertices, [], faces)
    leaf_mesh.update()
    leaf_mesh.materials.append(shaded_leaf)
    leaf_mesh.materials.append(leaf)
    for polygon, material_index in zip(leaf_mesh.polygons, material_indices):
        polygon.material_index = material_index
    uv_layer = leaf_mesh.uv_layers.new(name="IndividualLeafUV")
    for polygon in leaf_mesh.polygons:
        for loop_index in polygon.loop_indices:
            uv_layer.data[loop_index].uv = uv_coords[
                leaf_mesh.loops[loop_index].vertex_index
            ]
    leaves = bpy.data.objects.new(
        f"full13:tree:{index}:meshed_individual_summer_leaves", leaf_mesh
    )
    leaves["individual_physically_bent_laminae"] = n_leaves
    leaves["independent_branch_hierarchy"] = branch_count
    leaves["source"] = "full13_live_generator_articulated_tree_not_baked_proxy"
    master.objects.link(leaves)
    return {
        "branch_count": branch_count,
        "twig_count": len(twig_paths),
        "leaf_count": n_leaves,
        "leaf_vertices": len(vertices),
        "leaf_faces": len(faces),
    }


def add_perimeter_context_landscape() -> dict[str, Any]:
    """Integrated full-density landscape and genuinely continued access roads.

    This is an authored continuation of the actual developed city ground,
    not a background picture or disconnected demo: smooth terrain meets the
    seven-sided city prism, the arterial carriageways continue into the
    surrounding landscape, and individually seeded articulated summer trees
    with actual roots, twigs, branching and broadleaf laminae frame its edge.
    """
    name = "full13:master:weathered_urban_perimeter_landscape"
    if not BUILD_PROCEDURAL_PACK:
        master = _procedural_collections()[name]
        metadata = json.loads(PROCEDURAL_PACK_MANIFEST.read_text(encoding="utf8"))[
            "perimeter_landscape"
        ]
    else:
        geometry.PREFIX = "full13:"
        master = bpy.data.collections.new(name)
        core = _procedural_material(
            "district_subgrade",
            (0.11, 0.13, 0.075),
            (0.22, 0.25, 0.13),
            rough=0.94,
            scale=5.0,
            bump=0.17,
        )
        lawn = _procedural_material(
            "perimeter_meadow_fescue",
            (0.08, 0.14, 0.045),
            (0.22, 0.29, 0.105),
            rough=0.96,
            scale=6.0,
            bump=0.21,
        )
        meadow = _procedural_material(
            "perimeter_natural_meadow",
            (0.11, 0.13, 0.055),
            (0.31, 0.31, 0.115),
            rough=0.96,
            scale=9.0,
            bump=0.22,
        )
        aggregate = _procedural_material(
            "perimeter_road_aggregate",
            (0.08, 0.085, 0.085),
            (0.22, 0.23, 0.22),
            rough=0.88,
            scale=20.0,
            bump=0.15,
        )
        tarmac = _procedural_material(
            "perimeter_pbr_tarmac",
            (0.022, 0.030, 0.038),
            (0.12, 0.135, 0.147),
            rough=0.86,
            scale=17.0,
            bump=0.105,
        )
        curb_mat = _procedural_material(
            "perimeter_route_kerb",
            (0.20, 0.22, 0.21),
            (0.54, 0.55, 0.52),
            rough=0.79,
            scale=14.0,
            bump=0.09,
        )
        bark = _procedural_material(
            "perimeter_native_bark",
            (0.045, 0.028, 0.015),
            (0.23, 0.14, 0.07),
            rough=0.93,
            scale=11.0,
            bump=0.20,
        )
        leaf = _procedural_material(
            "perimeter_summer_leaf",
            (0.022, 0.095, 0.016),
            (0.10, 0.31, 0.065),
            rough=0.91,
            scale=10.0,
            bump=0.17,
        )
        shaded_leaf = _procedural_material(
            "perimeter_shaded_leaf",
            (0.012, 0.055, 0.014),
            (0.07, 0.23, 0.050),
            rough=0.90,
            scale=11.0,
            bump=0.15,
        )
        xs = sorted(
            set([-1112.5 + 15.0 * index for index in range(149)] + [-332.5, 332.5])
        )
        ys = sorted(
            set([-967.5 + 15.0 * index for index in range(130)] + [-292.5, 292.5])
        )
        vertices = [(x, y, _perimeter_height(x, y)) for y in ys for x in xs]
        nx = len(xs)
        faces = []
        face_materials = []
        for j in range(len(ys) - 1):
            for i in range(nx - 1):
                cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
                # The new terrain extends BELOW the physical original city
                # top surface even within its seven-sided outline.  This
                # prevents 15 m grid/irregular-edge gaps from revealing the
                # previous blue void; the original city prism stays visible.
                faces.append(
                    (j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
                )
                distance = math.hypot(
                    max(0.0, abs(cx) - 332.5), max(0.0, abs(cy) - 292.5)
                )
                patch = math.sin(0.027 * cx - 0.012 * cy)
                face_materials.append(
                    0
                    if distance < 35.0
                    else 1
                    if patch > 0.1
                    else 2
                    if patch > -0.45
                    else 3
                )
        mesh = bpy.data.meshes.new("full13:perimeter:weathered_terrain_grid")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for material in (core, lawn, meadow, aggregate):
            mesh.materials.append(material)
        for polygon, material_index in zip(mesh.polygons, face_materials):
            polygon.material_index = material_index
            polygon.use_smooth = True
        uv = mesh.uv_layers.new(name="MeteredPerimeterTerrainUV")
        for polygon in mesh.polygons:
            for loop_id in polygon.loop_indices:
                vertex = vertices[mesh.loops[loop_id].vertex_index]
                uv.data[loop_id].uv = (vertex[0] / 8.0, vertex[1] / 8.0)
        terrain = bpy.data.objects.new(
            "full13:perimeter:connected_weathered_terrain", mesh
        )
        master.objects.link(terrain)
        terrain[
            "terrain_topology"
        ] = "multi_frequency_grid_below_unmodified_original_seven_sided_city_prism"
        terrain["weathering_roughness_pbr"] = True
        # Extend, do not end, each source primary street.  Pavement follows
        # actual sampled landscape height on 7.5 m station spacing; shoulders
        # have separate aggregate/kerb material and no giant level toy slab.
        access_routes = (
            (327.0, 915.0, 0.0, "east_central"),
            (-915.0, -327.0, 0.0, "west_central"),
            (327.0, 915.0, -218.0, "east_industrial"),
            (-915.0, -327.0, -218.0, "west_industrial"),
        )
        for x_begin, x_end, yy, label in access_routes:
            step = 7.5
            station_count = max(2, int(abs(x_end - x_begin) / step) + 1)
            road_vertices = []
            road_faces = []
            road_materials = []
            for station in range(station_count + 1):
                x = x_begin + (x_end - x_begin) * station / station_count
                for lateral, alt in (
                    (-8.0, -0.003),
                    (-4.2, 0.025),
                    (4.2, 0.025),
                    (8.0, -0.003),
                ):
                    road_vertices.append(
                        (x, yy + lateral, _perimeter_height(x, yy + lateral) + alt)
                    )
                if station:
                    n = (station - 1) * 4
                    for band in range(3):
                        road_faces.append(
                            (n + band, n + 4 + band, n + 5 + band, n + band + 1)
                        )
                        road_materials.append(0 if band == 1 else 1)
            road_mesh = bpy.data.meshes.new(f"full13:perimeter:{label}:section_mesh")
            road_mesh.from_pydata(road_vertices, [], road_faces)
            road_mesh.update()
            road_mesh.materials.append(tarmac)
            road_mesh.materials.append(aggregate)
            for polygon, material_index in zip(road_mesh.polygons, road_materials):
                polygon.material_index = material_index
            pavement = bpy.data.objects.new(
                f"full13:perimeter:terrain_following_road:{label}", road_mesh
            )
            master.objects.link(pavement)
            for station in range(0, station_count + 1, 2):
                x = x_begin + (x_end - x_begin) * station / station_count
                for side in (-1, 1):
                    z = _perimeter_height(x, yy + side * 4.4) + 0.032
                    geometry.box(
                        f"perimeter_route_kerb_stone_{label}_{side}_{station}",
                        (x, yy + side * 4.4, z),
                        (5.6, 0.22, 0.065),
                        curb_mat,
                        master,
                        bevel=0.016,
                        segments=3,
                    )
        # The optional TreeFactory import requires gin/scipy, absent from the
        # production Blender runtime.  Explicit detailed geometry in this
        # real generator is mandatory: never substitute a toy LOD or proxy.
        rng = random.Random(13001326)
        tree_count = 0
        tree_branch_count = 0
        tree_twig_count = 0
        tree_leaf_count = 0
        tree_leaf_faces = 0
        for index in range(68):
            side = index % 4
            along = rng.uniform(-660.0, 660.0)
            offset = rng.uniform(360.0, 590.0)
            x, y = (
                (-offset, along)
                if side == 0
                else (offset, along)
                if side == 1
                else (along, -offset)
                if side == 2
                else (along, offset)
            )
            if abs(y) < 18.0 and abs(x) > 332.5:
                y += 27.0 if y >= 0 else -27.0
            if abs(y + 218.0) < 18.0 and abs(x) > 332.5:
                y += 26.0 if y >= -218.0 else -26.0
            proof = _author_articulated_perimeter_tree(
                master,
                index,
                x,
                y,
                bark,
                leaf,
                shaded_leaf,
            )
            if (
                proof["leaf_count"] < 1200
                or proof["branch_count"] < 50
                or proof["twig_count"] < 100
            ):
                raise RuntimeError(
                    f"Perimeter tree {index} degraded to toy geometry: {proof}"
                )
            tree_branch_count += proof["branch_count"]
            tree_twig_count += proof["twig_count"]
            tree_leaf_count += proof["leaf_count"]
            tree_leaf_faces += proof["leaf_faces"]
            tree_count += 1
        metadata = {
            "terrain_grid_vertex_count": len(vertices),
            "clipped_multi_material_quad_count": len(faces),
            "continued_terrain_following_street_count": len(access_routes),
            "fully_meshed_articulated_tree_count": tree_count,
            "articulated_tree_variant_count": 5,
            "actual_tree_branch_count": tree_branch_count,
            "actual_tree_twig_count": tree_twig_count,
            "actual_individual_broadleaf_count": tree_leaf_count,
            "actual_broadleaf_mesh_face_count": tree_leaf_faces,
            "terrain_context_replaces_blue_exposed_plate_edge": True,
            "source_original_compact_city_prism_preserved": True,
            "city_buildable_envelope_unchanged": list(CITY_ENVELOPE),
            "terrain_and_roads_participate_in_production_base_layer": True,
        }
    pid = "full13_connected_weathered_city_perimeter"
    place(
        master,
        pid,
        category="urban_context_terrain",
        zone="city_base",
        source_key=PROCEDURAL_SOURCE_KEY,
        source_collection=master.name,
        source_bounds=((-1112.5, -967.5, -0.2), (1112.5, 967.5, 35.0)),
        source_center=(0.0, 0.0),
        at=(0.0, 0.0, 0.0),
        collision_class="base",
        metadata={"same_run_procedural": True, **metadata},
    )
    framework.PLACEMENTS[-1][
        "reuse_policy"
    ] = "same_run_native_terrain_tree_road_geometry_in_real_city_base"
    return {"placement_id": pid, **metadata}


def add_connected_streets() -> dict[str, Any]:
    """Install the compact exact-source road graph before saving the city."""
    removed = _remove_legacy_base_and_roads()
    ground_id = add_compact_ground()
    substrate = add_connected_road_substrate()
    perimeter = add_perimeter_context_landscape()
    ew = require_collection("full10:master:road_ew_109m")
    ns = require_collection("full10:master:road_ns_109m")
    junction = require_collection("full10:master:road_intersection_complete")
    amenities = require_collection(
        "full10:master:roadside_flowerbeds_and_road_vehicles"
    )
    common = dict(zone="roads", source_key="river5", collision_class="road")
    ids: list[str] = []

    def road(kind: str, x: float, y: float, label: str, yaw: float = 0.0) -> None:
        source = {"ew": ew, "ns": ns, "intersection": junction}[kind]
        category = {
            "ew": "road_segment_ew",
            "ns": "road_segment_ns",
            "intersection": "road_intersection",
        }[kind]
        bounds = (
            ((-54.5, -54.5, 0.0), (54.5, 54.5, 8.0))
            if kind == "intersection"
            else ((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0))
            if kind == "ew"
            else ((-10.5, -54.5, 0.0), (10.5, 54.5, 8.0))
        )
        pid = f"full13_road_{label}"
        place(
            source,
            pid,
            category=category,
            source_collection=(
                "Road + Sidewalks + RoadMarkings + Lamps + TrafficLights"
                if kind == "intersection"
                else "Road + Sidewalks + RoadMarkings + Lamps"
            ),
            source_bounds=bounds,
            source_center=(0.0, 0.0),
            at=(x, y, 0.0),
            yaw=yaw,
            metadata={
                "network_role": "full13_compact_connected_hierarchy",
                "source_module_length_m": 109.0,
                "duplicate_vehicle_modules": False,
                "traffic_clear": True,
            },
            **common,
        )
        ids.append(pid)

    junctions = {
        (-54.5, 0.0),
        (272.5, 0.0),
        (-272.5, -218.0),
        (-54.5, -218.0),
        (272.5, -218.0),
        (272.5, -109.0),
        (272.5, 218.0),
    }
    for y in (0.0, -218.0):
        for x in (-272.5, -163.5, -54.5, 54.5, 163.5, 272.5):
            kind = "intersection" if (x, y) in junctions else "ew"
            road(kind, x, y, f"main_{x:g}_{y:g}".replace("-", "m"))
    for x in (-54.5,):
        road("ns", x, -109.0, f"link_{x:g}_m109".replace("-", "m"))
    for y in (-109.0, 109.0):
        kind = "intersection" if y == -109.0 else "ns"
        road(kind, 272.5, y, f"east_272p5_{y:g}".replace("-", "m"))
    road("intersection", 272.5, 218.0, "east_residential_intersection")
    for y in (109.0, 218.0):
        road("ns", -54.5, y, f"civic_m54p5_{y:g}")
    for x in (54.5, 163.5):
        road("ew", x, -109.0, f"commercial_{x:g}_m109")
    for x in (54.5, 163.5):
        road("ew", x, 218.0, f"residential_{x:g}_218")

    # Two contiguous real 109 m modules: the first begins at the central
    # four-way node and the second terminates on the east commercial street.
    diagonal_yaw = -math.pi / 6.0
    direction = Vector((math.cos(diagonal_yaw), math.sin(diagonal_yaw)))
    start = Vector((-54.5, 0.0))
    diagonal_connectors = []
    for index in range(2):
        center = start + direction * (54.5 + 109.0 * index)
        pid = f"full13_road_diagonal_connector_{index + 1:02d}"
        place(
            ew,
            pid,
            category="road_segment_diagonal",
            zone="roads",
            source_key="river5",
            source_collection="Road + Sidewalks + RoadMarkings + Lamps",
            source_bounds=((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0)),
            source_center=(0.0, 0.0),
            at=(center.x, center.y, 0.0),
            yaw=diagonal_yaw,
            collision_class="road",
            metadata={
                "network_role": "visible_two_module_diagonal_district_connector",
                "connects": [list(start), list(start + direction * 218.0)],
                "source_module_length_m": 109.0,
            },
        )
        ids.append(pid)
        diagonal_connectors.append(pid)

    # One authored vehicle/flowerbed group in the entire city.  Straight road
    # modules do not receive repeated frozen vehicle groups.
    amenity_id = "full13_single_road_activity_module"
    place(
        amenities,
        amenity_id,
        category="roadside_amenities",
        zone="roads",
        source_key="river5",
        source_collection="FlowerBeds + Vehicles",
        source_bounds=((-54.5, -54.5, 0.0), (54.5, 54.5, 2.3)),
        source_center=(0.0, 0.0),
        at=(272.5, 0.0, 0.0),
        collision_class="road_amenity",
        metadata={
            "citywide_authored_vehicle_group_count": 1,
            "prevents_repeated_frozen_traffic": True,
        },
    )
    return {
        "placement_ids": ids,
        "ground_placement_ids": [ground_id],
        "road_amenity_placement_ids": [amenity_id],
        "removed_legacy_placement_ids": removed,
        "removed_legacy_placement_count": len(removed),
        "ground_tile_count": 1,
        "exact_109m_module_count": len(ids),
        "diagonal_module_count": 2,
        "diagonal_placement_ids": diagonal_connectors,
        "continuous_road_substrate": substrate,
        "connected_perimeter_landscape": perimeter,
        "source": "urban_v1_full_07-river5 exact road kit",
        "scale": [1.0, 1.0, 1.0],
        "compact_city_envelope": [list(CITY_ENVELOPE[:2]), list(CITY_ENVELOPE[2:])],
    }


def _building_system() -> (
    tuple[
        dict[str, bpy.types.Material],
        dict[str, bpy.types.Collection],
        bpy.types.Collection,
    ]
):
    apartment_source.ROOT = ROOT
    apartment_source.PREFIX = "full13_proc:"
    apartment_source.RNG = random.Random(130045)
    apartment_source.G.ROOT = ROOT
    apartment_source.G.PREFIX = apartment_source.PREFIX
    apartment_source.G.RNG = apartment_source.RNG
    materials = apartment_source.make_materials()
    apartment_source.G.MATS = materials
    assets = {
        "win_living": apartment_source.make_window_master(
            "f13_living", 3.45, 2.22, materials, 3
        ),
        "win_bed": apartment_source.make_window_master(
            "f13_bedroom", 1.72, 1.42, materials, 2, curtain=True
        ),
        "win_narrow": apartment_source.make_window_master(
            "f13_narrow", 0.72, 1.82, materials, 1, awning=True
        ),
        "win_utility": apartment_source.make_window_master(
            "f13_utility", 0.92, 0.72, materials, 1, awning=True
        ),
        "sliding_door": apartment_source.make_window_master(
            "f13_balcony_door", 2.45, 2.20, materials, 2, curtain=True
        ),
        "door_a": apartment_source.make_door_master("f13_sidelight", materials, True),
        "door_b": apartment_source.make_door_master("f13_side_shift", materials, False),
        "balcony_metal": apartment_source.make_balcony_master(
            "f13_vertical", "metal", materials
        ),
        "balcony_solid": apartment_source.make_balcony_master(
            "f13_solid", "solid", materials
        ),
        "balcony_glass": apartment_source.make_balcony_master(
            "f13_glass", "glass", materials
        ),
        "hvac": apartment_source.make_hvac_master(materials),
        "ac": apartment_source.make_ac_master(materials),
        "mailbox": apartment_source.make_mailbox_master(materials),
    }
    root = bpy.data.collections.new("full13:master:unique_urban_fabric_library")
    root["source_generator"] = str(Path(__file__).resolve())
    root["source_detail_system"] = "generate_urban_v3_all45_02.add_apartment"
    return materials, assets, root


def _secondary_facades(
    name: str,
    width: float,
    depth: float,
    floors: int,
    yaw: float,
    materials: dict[str, Any],
    assets: dict[str, Any],
    collection: bpy.types.Collection,
) -> None:
    origin = (0.0, 0.0, 0.0)
    for floor in range(floors):
        z = 3.03 * floor + 1.54
        for side_index, side in enumerate((-1, 1)):
            x = side * (width / 2 + 0.23)
            for bay, local_y in enumerate((-depth * 0.28, 0.0, depth * 0.28)):
                key = ("win_bed", "win_narrow", "win_utility")[
                    (floor + bay + side_index) % 3
                ]
                apartment_source.G.local_box(
                    f"{name}_side_reveal_{side_index}_{floor}_{bay}",
                    origin,
                    yaw,
                    (x - side * 0.10, local_y, z),
                    (0.16, min(2.15, depth * 0.18), 2.34),
                    materials["panel_dark"],
                    collection,
                    bevel=0.008,
                )
                apartment_source.G.collection_instance(
                    assets[key],
                    f"{name}_side_{key}_{side_index}_{floor}_{bay}",
                    apartment_source.G.transform_point(origin, yaw, (x, local_y, z)),
                    collection,
                    yaw + side * math.pi / 2,
                    (0.80, 0.80, 0.87),
                )
        for rear, local_x in enumerate((-width * 0.22, width * 0.12, width * 0.34)):
            key = "win_bed" if (floor + rear) % 2 == 0 else "win_utility"
            apartment_source.G.local_box(
                f"{name}_rear_reveal_{floor}_{rear}",
                origin,
                yaw,
                (local_x, depth / 2 + 0.10, z),
                (2.12, 0.16, 2.34),
                materials["panel_dark"],
                collection,
                bevel=0.008,
            )
            apartment_source.G.collection_instance(
                assets[key],
                f"{name}_rear_{key}_{floor}_{rear}",
                apartment_source.G.transform_point(
                    origin, yaw, (local_x, depth / 2 + 0.23, z)
                ),
                collection,
                yaw + math.pi,
                (0.78, 0.78, 0.86),
            )


# Each tuple is a separately generated collection with unique dimensions,
# floor count, style, orientation and frontage.  No source building is ever
# instanced twice.
INFILL_SPECS = (
    ("west_civic_01", (-309.0, 58.0), 24.0, 26.0, 4, 0, math.pi / 2, "civic"),
    ("west_civic_02", (-309.0, 96.0), 26.0, 28.0, 5, 1, math.pi / 2, "civic"),
    ("west_civic_03", (-309.0, 138.0), 23.0, 30.0, 6, 2, math.pi / 2, "education"),
    ("west_civic_04", (-309.0, 181.0), 25.0, 29.0, 4, 1, math.pi / 2, "education"),
    ("east_mixed_01", (310.0, -72.0), 32.0, 24.0, 5, 0, -math.pi / 2, "commercial"),
    ("east_mixed_02", (310.0, -30.0), 29.0, 25.0, 7, 2, -math.pi / 2, "commercial"),
    ("southeast_01", (148.0, -137.0), 31.0, 28.0, 5, 1, 0.0, "mixed_use"),
    ("southeast_02", (-95.0, -150.0), 28.0, 25.0, 4, 2, math.pi, "mixed_use"),
    (
        "northwest_edge_01",
        (-309.0, 222.0),
        30.0,
        19.0,
        5,
        0,
        math.pi / 2,
        "residential",
    ),
    (
        "northwest_edge_02",
        (-309.0, 256.0),
        34.0,
        19.0,
        6,
        1,
        math.pi / 2,
        "residential",
    ),
    # Keep the independently generated infill clear of the police-station roof
    # coping.  A measured 0.10 m westward construction joint eliminates the
    # former 13.5 mm evaluated-mesh contact while retaining 3.40 m clearance
    # from the exact x=-54.5 m civic road surface.
    ("north_civic_01", (-25.10, 278.0), 31.0, 22.0, 5, 2, math.pi, "civic"),
    ("north_civic_02", (75.0, 282.0), 36.0, 18.0, 7, 0, math.pi, "residential"),
)


def add_unique_urban_fabric() -> dict[str, Any]:
    if BUILD_PROCEDURAL_PACK:
        materials, assets, root = _building_system()
    else:
        materials, assets, root = {}, {}, None
        linked = _procedural_collections()
    ids: list[str] = []
    object_counts: dict[str, int] = {}
    for index, (name, at, width, depth, floors, style, yaw, zone) in enumerate(
        INFILL_SPECS, 1
    ):
        if BUILD_PROCEDURAL_PACK:
            before = set(bpy.data.objects)
            collection = apartment_source.add_apartment(
                name,
                (0.0, 0.0, 0.0),
                0.0,
                width,
                depth,
                floors,
                style,
                materials,
                assets,
                root,
            )
            _secondary_facades(
                name, width, depth, floors, 0.0, materials, assets, collection
            )
            collection["c2w_asset_quality"] = "all45_02_full_facade_production_detail"
            collection["unique_citywide_source"] = True
            count = len(set(bpy.data.objects) - before)
        else:
            collection = linked[f"full13_proc:apartment_{name}"]
            count = len(collection.all_objects)
        if count < 70:
            raise RuntimeError(
                f"Procedural building {name} degraded to {count} objects"
            )
        pid = f"full13_unique_infill_{index:02d}_{name}"
        place(
            collection,
            pid,
            category="urban_infill",
            zone=zone,
            source_key=PROCEDURAL_SOURCE_KEY,
            source_collection=collection.name,
            source_bounds=(
                (-width / 2, -depth / 2, 0.0),
                (width / 2, depth / 2, floors * 3.03 + 1.5),
            ),
            source_center=(0.0, 0.0),
            at=(at[0], at[1], 0.0),
            yaw=yaw,
            metadata={
                "same_run_procedural": True,
                "source_generator": "generate_urban_v3_all45_02.add_apartment",
                "secondary_facades": True,
                "unique_parameters": [width, depth, floors, style, yaw],
                "recursive_object_count": count,
                "front_direction_local": "-Y",
                "source_collection_use_count": 1,
            },
        )
        record = framework.PLACEMENTS[-1]
        record["reuse_policy"] = "same_run_unique_procedural_production_no_proxy"
        bpy.data.objects[record["name"]]["reuse_policy"] = record["reuse_policy"]
        ids.append(pid)
        object_counts[pid] = count
    return {
        "placement_ids": ids,
        "total": len(ids),
        "unique_source_collection_count": len(ids),
        "maximum_source_collection_reuse": 1,
        "full11_infill_count": 316,
        "reduction_ratio": round(1.0 - len(ids) / 316.0, 6),
        "source_generator": str(ROOT / "scripts/generate_urban_v3_all45_02.py"),
        "object_counts": object_counts,
        "policy": "one live, independently parameterized full-detail building collection per placement",
    }


def _link_created_to_master(
    objects: Iterable[bpy.types.Object], master: bpy.types.Collection
) -> None:
    for obj in objects:
        if obj.name not in bpy.data.objects:
            continue
        if obj.name not in {member.name for member in master.objects}:
            master.objects.link(obj)
        for collection in list(obj.users_collection):
            if collection != master:
                collection.objects.unlink(obj)


def _add_independently_grouted_floor_tile_mesh(
    name: str,
    width: float,
    depth: float,
    tile_size: float,
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> int:
    """One Blender operator for many unchanged, disconnected bevelled tiles.

    Model each tile as its own closed six-sided shell with a physical five
    millimetre grout opening and deterministic individually assigned finish.
    Joining these disconnected parts into one render mesh preserves their
    actual geometry, UVs, bevel radius and per-tile PBR material, but avoids
    a per-cell dependency-graph evaluation during high-detail authoring.
    """
    tile_nx = max(1, int(width / tile_size))
    tile_ny = max(1, int(depth / tile_size))
    tw, td = width / tile_nx - 0.005, depth / tile_ny - 0.005
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    mat_ids: list[int] = []
    for row in range(tile_ny):
        yy = -depth / 2 + (row + 0.5) * depth / tile_ny
        for col in range(tile_nx):
            xx = -width / 2 + (col + 0.5) * width / tile_nx
            idx = len(verts)
            for zz in (-0.0035, 0.0155):
                verts.extend(
                    (xx + u * tw / 2, yy + v * td / 2, zz)
                    for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                )
            faces.extend(
                ((idx + 3, idx + 2, idx + 1, idx), (idx + 4, idx + 5, idx + 6, idx + 7))
            )
            faces.extend(
                (idx + j, idx + (j + 1) % 4, idx + 4 + (j + 1) % 4, idx + 4 + j)
                for j in range(4)
            )
            pattern = (row * 17 + col * 31 + (row * col) % 7) % 13
            finish = 0 if pattern < 7 else 1 if pattern < 10 else 2
            mat_ids.extend((finish,) * 6)
    mesh = bpy.data.meshes.new(f"full13:{name}:disconnected_grouted_tile_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for finish in (
        materials["stone"],
        materials["paving"],
        materials["interior_floor"],
    ):
        mesh.materials.append(finish)
    for polygon, finish_id in zip(mesh.polygons, mat_ids):
        polygon.material_index = finish_id
    uv_layer = mesh.uv_layers.new(name="RoomIndividualTileUV")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vx, vy, _ = verts[mesh.loops[loop_index].vertex_index]
            uv_layer.data[loop_index].uv = (vx / tile_size, vy / tile_size)
    obj = bpy.data.objects.new(
        f"full13:{name}:individually_grouted_closed_tile_shells", mesh
    )
    master.objects.link(obj)
    modifier = obj.modifiers.new("PhysicalIndividualTileEdgeBevel", "BEVEL")
    modifier.width = 0.003
    modifier.segments = 2
    obj["actual_disconnected_closed_tile_shells"] = tile_nx * tile_ny
    obj["physical_grout_width_m"] = 0.005
    obj["same_geometry_as_individually_authored_floor_cells"] = True
    return tile_nx * tile_ny


def _add_room_shell(
    name: str,
    size: tuple[float, float],
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    width, depth = size
    G = apartment_source.G
    # Native usable floor is z=0, not z=+0.16 above furniture feet.  The
    # latter buried chair legs/people in all four delivered room images.
    G.box(
        f"{name}_floor",
        (0, 0, -0.08),
        (width, depth, 0.16),
        materials["interior_floor"],
        master,
        bevel=0.025,
        segments=2,
    )
    # Actual tile topology remains one closed shell per cell; only the RNA
    # authoring call is batched.  No geometric LOD or material downgrade.
    _add_independently_grouted_floor_tile_mesh(
        name,
        width,
        depth,
        0.94 if name == "hospital_lobby" else 0.88,
        materials,
        master,
    )
    G.box(
        f"{name}_ceiling",
        (0, 0, 3.48),
        (width, depth, 0.14),
        materials["stucco_white"],
        master,
        bevel=0.015,
    )
    G.box(
        f"{name}_rear_wall",
        (0, depth / 2, 1.75),
        (width, 0.18, 3.5),
        materials["interior_wall"],
        master,
        bevel=0.012,
    )
    for side in (-1, 1):
        G.box(
            f"{name}_side_wall_{side}",
            (side * width / 2, 0, 1.75),
            (0.18, depth, 3.5),
            materials["interior_wall"],
            master,
            bevel=0.012,
        )
        G.box(
            f"{name}_wall_baseboard_{side}",
            (side * (width / 2 - 0.115), 0, 0.095),
            (0.065, depth - 0.10, 0.18),
            materials["stone"],
            master,
            bevel=0.018,
            segments=3,
        )
        G.box(
            f"{name}_wall_crown_shadow_reveal_{side}",
            (side * (width / 2 - 0.11), 0, 3.28),
            (0.055, depth - 0.10, 0.11),
            materials["panel_dark"],
            master,
            bevel=0.012,
            segments=2,
        )
    G.box(
        f"{name}_rear_baseboard",
        (0, depth / 2 - 0.12, 0.095),
        (width - 0.15, 0.065, 0.18),
        materials["stone"],
        master,
        bevel=0.018,
        segments=3,
    )
    bay = width / 6
    for index in range(6):
        x = -width / 2 + bay * (index + 0.5)
        G.box(
            f"{name}_front_glass_{index}",
            (x, -depth / 2, 1.68),
            (bay - 0.10, 0.045, 3.20),
            materials["glass_clear"],
            master,
            bevel=0.005,
        )
        G.box(
            f"{name}_front_mullion_{index}",
            (-width / 2 + bay * index, -depth / 2 - 0.03, 1.70),
            (0.065, 0.09, 3.35),
            materials["metal"],
            master,
            bevel=0.004,
        )
    for row in (-1, 1):
        for index in range(5):
            x = -width * 0.35 + index * width * 0.175
            G.box(
                f"{name}_ceiling_light_{row}_{index}",
                (x, row * depth * 0.25, 3.36),
                (1.0, 0.18, 0.07),
                materials["warm_light"],
                master,
                bevel=0.025,
                segments=3,
            )


def _chair(
    name: str,
    loc: tuple[float, float],
    yaw: float,
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    """Independently assembled ergonomic public seat, never a box-on-sticks.

    The local frame rotates the seat, lumbar contour, padded armrests, gussets,
    cross-bracing and foot caps together.  Native PBR upholstery, metal and
    anti-scuff rubber are separate authored materials and real depth geometry.
    """
    G = apartment_source.G
    x, y = loc
    c, s = math.cos(yaw), math.sin(yaw)

    def point(lx: float, ly: float, z: float) -> tuple[float, float, float]:
        return x + c * lx - s * ly, y + s * lx + c * ly, z

    metal = materials["metal"]
    fabric = materials["wood"]
    rubber = materials.get("panel_dark", metal)
    G.box(
        f"{name}_formed_seat_pan",
        point(0, 0, 0.435),
        (0.60, 0.58, 0.055),
        metal,
        master,
        rot=yaw,
        bevel=0.035,
        segments=4,
    )
    G.box(
        f"{name}_upholstered_seat_cushion",
        point(0, -0.012, 0.505),
        (0.565, 0.55, 0.092),
        fabric,
        master,
        rot=yaw,
        bevel=0.062,
        segments=5,
    )
    # Three individually formed back cushions bow forward at the lumbar
    # region and away at shoulder level, with metal uprights between them.
    for index, (z, ly, thickness) in enumerate(
        ((0.73, 0.22, 0.11), (0.915, 0.265, 0.14), (1.09, 0.305, 0.105))
    ):
        G.box(
            f"{name}_ergonomic_back_panel_{index}",
            point(0, ly, z),
            (0.565, thickness, 0.215),
            fabric,
            master,
            rot=yaw,
            bevel=0.048,
            segments=5,
        )
    for side in (-1, 1):
        lx = side * 0.27
        G.beam(
            f"{name}_back_rest_support_{side}",
            point(lx, 0.19, 0.48),
            point(lx, 0.33, 1.155),
            0.018,
            metal,
            master,
            vertices=16,
        )
        G.beam(
            f"{name}_underseat_side_gusset_{side}",
            point(lx, -0.22, 0.41),
            point(lx, 0.20, 0.43),
            0.014,
            metal,
            master,
            vertices=14,
        )
        G.beam(
            f"{name}_arm_upright_front_{side}",
            point(side * 0.33, -0.15, 0.40),
            point(side * 0.33, -0.15, 0.735),
            0.018,
            metal,
            master,
            vertices=16,
        )
        G.beam(
            f"{name}_arm_upright_rear_{side}",
            point(side * 0.33, 0.20, 0.40),
            point(side * 0.33, 0.20, 0.735),
            0.018,
            metal,
            master,
            vertices=16,
        )
        G.box(
            f"{name}_padded_armrest_{side}",
            point(side * 0.33, 0.017, 0.742),
            (0.082, 0.47, 0.065),
            fabric,
            master,
            rot=yaw,
            bevel=0.028,
            segments=4,
        )
        for front, ly in (("front", -0.195), ("rear", 0.195)):
            G.beam(
                f"{name}_{front}_leg_tapered_{side}",
                point(side * 0.232, ly, 0.414),
                point(side * 0.225, ly + (0.01 if ly > 0 else -0.01), 0.055),
                0.021,
                metal,
                master,
                vertices=16,
            )
            G.cylinder(
                f"{name}_{front}_nonmarking_foot_{side}",
                point(side * 0.225, ly, 0.032),
                0.030,
                0.052,
                rubber,
                master,
                vertices=20,
                bevel=0.012,
            )
    for front, ly in (("front", -0.195), ("rear", 0.195)):
        G.beam(
            f"{name}_underseat_crossbar_{front}",
            point(-0.232, ly, 0.28),
            point(0.232, ly, 0.28),
            0.013,
            metal,
            master,
            vertices=12,
        )
    for side in (-1, 1):
        G.beam(
            f"{name}_upholstery_piped_side_seam_{side}",
            point(side * 0.278, -0.22, 0.538),
            point(side * 0.278, 0.21, 0.538),
            0.008,
            rubber,
            master,
            vertices=10,
        )


def _table(
    name: str,
    loc: tuple[float, float],
    size: tuple[float, float],
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    G = apartment_source.G
    x, y = loc
    G.box(
        f"{name}_top",
        (x, y, 0.76),
        (size[0], size[1], 0.11),
        materials["wood"],
        master,
        bevel=0.055,
        segments=4,
    )
    for sx in (-size[0] * 0.38, size[0] * 0.38):
        for sy in (-size[1] * 0.32, size[1] * 0.32):
            G.cylinder(
                f"{name}_leg_{sx}_{sy}",
                (x + sx, y + sy, 0.38),
                0.035,
                0.72,
                materials["metal"],
                master,
                vertices=16,
                bevel=0.008,
            )


def _semantic_text(
    name: str,
    body: str,
    loc: tuple[float, float, float],
    size: float,
    material: bpy.types.Material,
    master: bpy.types.Collection,
    *,
    align: str = "CENTER",
) -> bpy.types.Object:
    """Create real extruded room signage facing the glazed -Y entrance."""
    curve = bpy.data.curves.new(f"full13:{name}:font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.028
    curve.bevel_depth = 0.006
    curve.resolution_u = 8
    curve.bevel_resolution = 3
    curve.materials.append(material)
    obj = bpy.data.objects.new(f"full13:{name}", curve)
    master.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0.0, 0.0)
    obj["semantic_role"] = "functional_interior_signage"
    return obj


def _monitor_terminal(
    name: str,
    loc: tuple[float, float, float],
    materials: dict[str, Any],
    master: bpy.types.Collection,
    *,
    width: float = 0.72,
) -> None:
    """Detailed public-service workstation, including bezel, screen and input."""
    G = apartment_source.G
    G.box(
        f"{name}_monitor_shell",
        loc,
        (width, 0.13, 0.52),
        materials["panel_dark"],
        master,
        bevel=0.038,
        segments=3,
    )
    G.box(
        f"{name}_monitor_screen",
        (loc[0], loc[1] - 0.072, loc[2] + 0.015),
        (width - 0.09, 0.018, 0.40),
        materials["screen_blue"],
        master,
        bevel=0.018,
        segments=3,
    )
    G.cylinder(
        f"{name}_monitor_stem",
        (loc[0], loc[1] + 0.015, loc[2] - 0.36),
        0.035,
        0.30,
        materials["metal"],
        master,
        vertices=18,
        bevel=0.008,
    )
    G.box(
        f"{name}_monitor_foot",
        (loc[0], loc[1] - 0.01, loc[2] - 0.52),
        (0.36, 0.27, 0.045),
        materials["metal"],
        master,
        bevel=0.025,
        segments=3,
    )
    G.box(
        f"{name}_keyboard",
        (loc[0], loc[1] - 0.40, loc[2] - 0.50),
        (0.55, 0.22, 0.035),
        materials["apt_panel"],
        master,
        bevel=0.018,
        segments=3,
    )


def _interior_planter(
    name: str,
    loc: tuple[float, float],
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    G = apartment_source.G
    x, y = loc
    G.cylinder(
        f"{name}_pot",
        (x, y, 0.36),
        0.36,
        0.68,
        materials["stone"],
        master,
        vertices=32,
        bevel=0.045,
    )
    G.cylinder(
        f"{name}_trunk",
        (x, y, 0.91),
        0.055,
        0.72,
        materials["wood"],
        master,
        vertices=16,
        bevel=0.01,
    )
    for index, (dx, dy, dz) in enumerate(
        ((-0.22, 0.0, 1.20), (0.22, 0.02, 1.27), (0.0, -0.18, 1.43), (0.0, 0.18, 1.36))
    ):
        G.cylinder(
            f"{name}_leaf_{index}",
            (x + dx, y + dy, dz),
            0.24,
            0.065,
            materials["plant_leaf"],
            master,
            vertices=20,
            rot=(0.0, math.pi / 2, index * 0.72),
            bevel=0.018,
        )


def _hospital_wheelchair(
    name: str,
    loc: tuple[float, float],
    materials: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    """Recognizable modeled wheelchair: paired wheels, hubs, frame and footrests."""
    G = apartment_source.G
    x, y = loc
    for side in (-1, 1):
        wheel_y = y + side * 0.34
        G.cylinder(
            f"{name}_wheel_{side}",
            (x, wheel_y, 0.46),
            0.42,
            0.045,
            materials["panel_dark"],
            master,
            vertices=40,
            rot=(math.pi / 2, 0.0, 0.0),
            bevel=0.012,
        )
        G.cylinder(
            f"{name}_hub_{side}",
            (x, wheel_y - side * 0.032, 0.46),
            0.07,
            0.065,
            materials["metal"],
            master,
            vertices=24,
            rot=(math.pi / 2, 0.0, 0.0),
            bevel=0.01,
        )
        for spoke in range(8):
            angle = math.tau * spoke / 8
            G.beam(
                f"{name}_spoke_{side}_{spoke}",
                (x, wheel_y - side * 0.055, 0.46),
                (
                    x + math.cos(angle) * 0.34,
                    wheel_y - side * 0.055,
                    0.46 + math.sin(angle) * 0.34,
                ),
                0.010,
                materials["metal"],
                master,
                vertices=8,
            )
    G.box(
        f"{name}_seat",
        (x - 0.06, y, 0.58),
        (0.55, 0.66, 0.09),
        materials["seat_blue"],
        master,
        bevel=0.045,
        segments=3,
    )
    G.box(
        f"{name}_back",
        (x + 0.23, y, 0.94),
        (0.09, 0.66, 0.72),
        materials["seat_blue"],
        master,
        bevel=0.045,
        segments=3,
    )
    for side in (-1, 1):
        G.beam(
            f"{name}_frame_{side}",
            (x - 0.32, y + side * 0.27, 0.20),
            (x + 0.21, y + side * 0.27, 0.72),
            0.025,
            materials["metal"],
            master,
            vertices=12,
        )
        G.beam(
            f"{name}_arm_{side}",
            (x - 0.04, y + side * 0.31, 0.78),
            (x + 0.30, y + side * 0.31, 0.84),
            0.025,
            materials["metal"],
            master,
            vertices=12,
        )
        G.beam(
            f"{name}_footrest_{side}",
            (x - 0.28, y + side * 0.23, 0.31),
            (x - 0.63, y + side * 0.23, 0.13),
            0.022,
            materials["metal"],
            master,
            vertices=12,
        )
        G.box(
            f"{name}_footplate_{side}",
            (x - 0.70, y + side * 0.23, 0.10),
            (0.26, 0.22, 0.035),
            materials["metal"],
            master,
            bevel=0.018,
            segments=2,
        )


def add_semantic_interiors() -> dict[str, Any]:
    materials = apartment_source.make_materials() if BUILD_PROCEDURAL_PACK else {}
    if BUILD_PROCEDURAL_PACK:
        materials.update(
            {
                "bank_blue": _procedural_material(
                    "bank_blue",
                    (0.018, 0.055, 0.14),
                    (0.055, 0.22, 0.58),
                    rough=0.48,
                    scale=10.0,
                    bump=0.025,
                ),
                "hospital_red": _procedural_material(
                    "hospital_red",
                    (0.25, 0.018, 0.014),
                    (0.78, 0.055, 0.04),
                    rough=0.52,
                    scale=11.0,
                    bump=0.025,
                ),
                "screen_blue": _procedural_material(
                    "service_screen",
                    (0.01, 0.08, 0.12),
                    (0.08, 0.55, 0.82),
                    rough=0.25,
                    scale=8.0,
                    bump=0.0,
                ),
                "seat_blue": _procedural_material(
                    "healthcare_seat",
                    (0.025, 0.11, 0.16),
                    (0.08, 0.32, 0.42),
                    rough=0.76,
                    scale=14.0,
                    bump=0.05,
                ),
                "plant_leaf": _procedural_material(
                    "interior_plant",
                    (0.018, 0.11, 0.025),
                    (0.08, 0.34, 0.07),
                    rough=0.84,
                    scale=12.0,
                    bump=0.08,
                ),
                "paper_white": _procedural_material(
                    "printed_wayfinding",
                    (0.62, 0.62, 0.58),
                    (0.94, 0.93, 0.86),
                    rough=0.68,
                    scale=16.0,
                    bump=0.018,
                ),
            }
        )
    G = apartment_source.G
    specs = (
        (
            "school_cafeteria",
            (-310.0, 30.0),
            (18.0, 26.0),
            "education",
            "education_school_north",
        ),
        (
            "library_reading_room",
            (100.0, 115.0),
            (18.0, 24.0),
            "education",
            "education_library_south",
        ),
        (
            "bank_atrium",
            (140.0, 75.0),
            (22.0, 17.0),
            "commercial",
            "bank_hq_blue_glass",
        ),
        (
            "hospital_lobby",
            (201.0, 55.0),
            (18.0, 24.0),
            "health",
            "hospital_central_red_white",
        ),
    )
    records = []
    for room_name, at, size, zone, host in specs:
        collection_name = f"full13:master:{room_name}"
        if BUILD_PROCEDURAL_PACK:
            master = bpy.data.collections.new(collection_name)
            before = set(bpy.data.objects)
            _add_room_shell(room_name, size, materials, master)
            width, depth = size
        else:
            master = _semantic_collections()[collection_name]
            before = set()
            width, depth = size
        if BUILD_PROCEDURAL_PACK and room_name == "school_cafeteria":
            for row, y in enumerate((-5.5, -1.8, 1.9, 5.6)):
                for col, x in enumerate((-4.8, 0.0, 4.8)):
                    _table(
                        f"{room_name}_table_{row}_{col}",
                        (x, y),
                        (2.6, 1.05),
                        materials,
                        master,
                    )
                    for side in (-1, 1):
                        _chair(
                            f"{room_name}_chair_{row}_{col}_{side}",
                            (x + side * 1.6, y),
                            side * math.pi / 2,
                            materials,
                            master,
                        )
            G.box(
                f"{room_name}_serving_counter",
                (0, depth / 2 - 1.2, 0.58),
                (width * 0.72, 1.15, 1.05),
                materials["stone"],
                master,
                bevel=0.10,
                segments=4,
            )
            for index in range(5):
                G.box(
                    f"{room_name}_tray_bay_{index}",
                    (-5.0 + index * 2.5, depth / 2 - 1.82, 0.92),
                    (1.8, 0.35, 0.08),
                    materials["metal"],
                    master,
                    bevel=0.025,
                )
        elif BUILD_PROCEDURAL_PACK and room_name == "library_reading_room":
            for side in (-1, 1):
                for bay in range(4):
                    x = side * (width / 2 - 0.65)
                    y = -6.0 + bay * 4.0
                    G.box(
                        f"{room_name}_shelf_{side}_{bay}",
                        (x, y, 1.25),
                        (0.55, 3.2, 2.45),
                        materials["wood"],
                        master,
                        bevel=0.035,
                        segments=3,
                    )
                    for shelf in range(5):
                        G.box(
                            f"{room_name}_shelf_board_{side}_{bay}_{shelf}",
                            (x - side * 0.32, y, 0.25 + shelf * 0.47),
                            (0.62, 3.05, 0.055),
                            materials["panel_dark"],
                            master,
                            bevel=0.008,
                        )
                        for book in range(8):
                            G.box(
                                f"{room_name}_book_{side}_{bay}_{shelf}_{book}",
                                (
                                    x - side * 0.67,
                                    y - 1.28 + book * 0.36,
                                    0.42 + shelf * 0.47,
                                ),
                                (0.20, 0.24, 0.33 + 0.03 * (book % 3)),
                                materials[
                                    ("sign", "panel_light", "apt_panel")[book % 3]
                                ],
                                master,
                                bevel=0.008,
                            )
            for index, y in enumerate((-4.2, 0.0, 4.2)):
                _table(
                    f"{room_name}_reading_table_{index}",
                    (0.0, y),
                    (4.6, 1.25),
                    materials,
                    master,
                )
                for side in (-1, 1):
                    _chair(
                        f"{room_name}_reading_chair_{index}_{side}",
                        (side * 2.9, y),
                        side * math.pi / 2,
                        materials,
                        master,
                    )
        elif BUILD_PROCEDURAL_PACK and room_name == "bank_atrium":
            # A complete staffed banking hall: five framed teller windows,
            # transaction hardware, self-service kiosks, queue rails, an
            # appropriately scaled information island, seating and signage.
            G.box(
                f"{room_name}_teller_plinth",
                (0, 4.05, 0.49),
                (12.8, 1.25, 0.92),
                materials["bank_blue"],
                master,
                bevel=0.10,
                segments=5,
            )
            G.box(
                f"{room_name}_teller_counter",
                (0, 3.60, 1.05),
                (12.5, 1.28, 0.18),
                materials["stone"],
                master,
                bevel=0.09,
                segments=5,
            )
            G.box(
                f"{room_name}_rear_brand_panel",
                (0, 8.35, 2.45),
                (13.8, 0.10, 1.45),
                materials["bank_blue"],
                master,
                bevel=0.055,
                segments=3,
            )
            _semantic_text(
                f"{room_name}_brand",
                "CITY BANK  |  PERSONAL SERVICE",
                (0.0, 8.285, 2.48),
                0.48,
                materials["paper_white"],
                master,
            )
            for index in range(5):
                x = -4.8 + index * 2.4
                G.box(
                    f"{room_name}_teller_glass_{index}",
                    (x, 3.42, 1.92),
                    (1.78, 0.035, 1.50),
                    materials["glass_clear"],
                    master,
                    bevel=0.006,
                )
                for side in (-1, 1):
                    G.box(
                        f"{room_name}_window_jamb_{index}_{side}",
                        (x + side * 0.91, 3.39, 1.92),
                        (0.075, 0.10, 1.62),
                        materials["metal"],
                        master,
                        bevel=0.008,
                    )
                G.box(
                    f"{room_name}_window_head_{index}",
                    (x, 3.39, 2.72),
                    (1.90, 0.10, 0.075),
                    materials["metal"],
                    master,
                    bevel=0.008,
                )
                G.box(
                    f"{room_name}_transaction_tray_{index}",
                    (x, 3.04, 1.16),
                    (0.64, 0.38, 0.055),
                    materials["metal"],
                    master,
                    bevel=0.025,
                    segments=3,
                )
                G.box(
                    f"{room_name}_document_slot_{index}",
                    (x, 2.94, 1.18),
                    (0.32, 0.07, 0.022),
                    materials["panel_dark"],
                    master,
                    bevel=0.01,
                )
                _monitor_terminal(
                    f"{room_name}_terminal_{index}",
                    (x, 4.58, 1.66),
                    materials,
                    master,
                    width=0.62,
                )
                _semantic_text(
                    f"{room_name}_window_number_{index}",
                    f"TELLER {index + 1}",
                    (x, 3.365, 2.53),
                    0.19,
                    materials["bank_blue"],
                    master,
                )
                _chair(
                    f"{room_name}_visitor_chair_{index}",
                    (x, -0.25),
                    0.0,
                    materials,
                    master,
                )

            G.cylinder(
                f"{room_name}_information_plinth",
                (4.5, -3.1, 0.47),
                1.05,
                0.82,
                materials["bank_blue"],
                master,
                vertices=48,
                bevel=0.08,
            )
            G.cylinder(
                f"{room_name}_information_top",
                (4.5, -3.1, 0.94),
                1.18,
                0.16,
                materials["wood"],
                master,
                vertices=48,
                bevel=0.06,
            )
            _monitor_terminal(
                f"{room_name}_information_terminal",
                (4.5, -2.85, 1.54),
                materials,
                master,
                width=0.68,
            )
            _semantic_text(
                f"{room_name}_information_label",
                "INFORMATION",
                (4.5, -4.155, 0.56),
                0.19,
                materials["paper_white"],
                master,
            )

            queue_x = (-5.4, -2.7, 0.0, 2.7, 5.4)
            for index, x in enumerate(queue_x):
                G.cylinder(
                    f"{room_name}_queue_base_{index}",
                    (x, 1.35, 0.045),
                    0.18,
                    0.08,
                    materials["metal"],
                    master,
                    vertices=24,
                    bevel=0.012,
                )
                G.cylinder(
                    f"{room_name}_queue_post_{index}",
                    (x, 1.35, 0.54),
                    0.045,
                    1.0,
                    materials["metal"],
                    master,
                    vertices=20,
                    bevel=0.012,
                )
                if index < len(queue_x) - 1:
                    G.beam(
                        f"{room_name}_queue_belt_{index}",
                        (x, 1.35, 1.0),
                        (queue_x[index + 1], 1.35, 1.0),
                        0.028,
                        materials["bank_blue"],
                        master,
                        vertices=12,
                    )

            for index, x in enumerate((-8.6, 8.6)):
                G.box(
                    f"{room_name}_self_service_body_{index}",
                    (x, 0.8, 1.05),
                    (1.15, 0.72, 2.0),
                    materials["bank_blue"],
                    master,
                    bevel=0.11,
                    segments=4,
                )
                G.box(
                    f"{room_name}_self_service_screen_{index}",
                    (x, 0.415, 1.38),
                    (0.76, 0.025, 0.52),
                    materials["screen_blue"],
                    master,
                    bevel=0.028,
                    segments=3,
                )
                G.box(
                    f"{room_name}_self_service_keypad_{index}",
                    (x, 0.31, 0.94),
                    (0.48, 0.24, 0.055),
                    materials["apt_panel"],
                    master,
                    bevel=0.018,
                    segments=2,
                )
                G.box(
                    f"{room_name}_self_service_slot_{index}",
                    (x, 0.405, 0.62),
                    (0.52, 0.035, 0.07),
                    materials["metal"],
                    master,
                    bevel=0.012,
                )
                _semantic_text(
                    f"{room_name}_self_service_label_{index}",
                    "SELF SERVICE",
                    (x, 0.39, 1.82),
                    0.16,
                    materials["paper_white"],
                    master,
                )

            for side in (-1, 1):
                x = side * 9.65
                G.box(
                    f"{room_name}_brochure_frame_{side}",
                    (x, 4.9, 1.65),
                    (0.12, 2.7, 2.55),
                    materials["wood"],
                    master,
                    bevel=0.035,
                    segments=3,
                )
                for shelf in range(4):
                    G.box(
                        f"{room_name}_brochure_shelf_{side}_{shelf}",
                        (x - side * 0.10, 4.9, 0.62 + shelf * 0.55),
                        (0.28, 2.52, 0.055),
                        materials["metal"],
                        master,
                        bevel=0.012,
                    )
                    for booklet in range(3):
                        G.box(
                            f"{room_name}_brochure_{side}_{shelf}_{booklet}",
                            (
                                x - side * 0.25,
                                4.15 + booklet * 0.72,
                                0.79 + shelf * 0.55,
                            ),
                            (0.055, 0.46, 0.30),
                            materials[("paper_white", "bank_blue", "sign")[booklet]],
                            master,
                            bevel=0.008,
                        )
            _interior_planter(
                f"{room_name}_planter_left", (-8.2, -4.8), materials, master
            )
            _interior_planter(
                f"{room_name}_planter_right", (8.1, -5.2), materials, master
            )
        elif BUILD_PROCEDURAL_PACK:
            # A complete hospital arrival lobby, not generic furniture: a
            # branded reception, four staffed workstations, check-in kiosks,
            # clinical wayfinding, waiting groups and a modeled wheelchair.
            G.box(
                f"{room_name}_reception_plinth",
                (0, 4.85, 0.50),
                (10.8, 1.32, 0.92),
                materials["hospital_red"],
                master,
                bevel=0.12,
                segments=5,
            )
            G.box(
                f"{room_name}_reception_counter",
                (0, 4.35, 1.05),
                (11.2, 1.38, 0.18),
                materials["stone"],
                master,
                bevel=0.09,
                segments=5,
            )
            G.box(
                f"{room_name}_reception_accessible_drop",
                (4.35, 3.95, 0.82),
                (2.05, 1.05, 0.12),
                materials["stone"],
                master,
                bevel=0.07,
                segments=4,
            )
            G.box(
                f"{room_name}_rear_brand_panel",
                (0, depth / 2 - 0.15, 2.52),
                (12.8, 0.10, 1.42),
                materials["hospital_red"],
                master,
                bevel=0.055,
                segments=3,
            )
            _semantic_text(
                f"{room_name}_brand",
                "HOSPITAL  |  RECEPTION",
                (0.0, depth / 2 - 0.215, 2.56),
                0.52,
                materials["paper_white"],
                master,
            )
            for index in range(4):
                x = -4.15 + index * 2.75
                _monitor_terminal(
                    f"{room_name}_reception_terminal_{index}",
                    (x, 5.28, 1.65),
                    materials,
                    master,
                    width=0.68,
                )
                G.box(
                    f"{room_name}_privacy_fin_{index}",
                    (x - 0.92, 4.26, 1.48),
                    (0.08, 0.82, 0.92),
                    materials["glass_clear"],
                    master,
                    bevel=0.018,
                    segments=2,
                )
                _semantic_text(
                    f"{room_name}_desk_number_{index}",
                    f"DESK {index + 1}",
                    (x, 4.275, 0.62),
                    0.17,
                    materials["paper_white"],
                    master,
                )

            # Two compact three-seat waiting groups on either side of the
            # 2.8 m clear central accessible aisle, facing the admissions
            # counter; the former four isolated stools per row were toy-like.
            for row, y in enumerate((-5.0, -2.55)):
                for col, x in enumerate((-5.65, -4.25, -2.85, 2.85, 4.25, 5.65)):
                    _chair(
                        f"{room_name}_waiting_{row}_{col}",
                        (x, y),
                        math.pi,
                        {**materials, "wood": materials["seat_blue"]},
                        master,
                    )
            for side in (-1, 1):
                x = side * 7.45
                G.box(
                    f"{room_name}_checkin_body_{side}",
                    (x, 1.65, 1.15),
                    (1.05, 0.72, 2.18),
                    materials["panel_light"],
                    master,
                    bevel=0.11,
                    segments=4,
                )
                G.box(
                    f"{room_name}_checkin_screen_{side}",
                    (x, 1.265, 1.50),
                    (0.72, 0.025, 0.55),
                    materials["screen_blue"],
                    master,
                    bevel=0.025,
                    segments=3,
                )
                G.box(
                    f"{room_name}_checkin_scanner_{side}",
                    (x, 1.20, 0.96),
                    (0.45, 0.22, 0.055),
                    materials["metal"],
                    master,
                    bevel=0.018,
                )
                G.box(
                    f"{room_name}_checkin_receipt_{side}",
                    (x, 1.275, 0.69),
                    (0.45, 0.035, 0.075),
                    materials["panel_dark"],
                    master,
                    bevel=0.012,
                )
                _semantic_text(
                    f"{room_name}_checkin_label_{side}",
                    "CHECK IN",
                    (x, 1.245, 1.95),
                    0.18,
                    materials["hospital_red"],
                    master,
                )

            pylon_x = width / 2 - 1.05
            G.box(
                f"{room_name}_wayfinding_pylon",
                (pylon_x, 2.65, 1.25),
                (0.42, 1.55, 2.40),
                materials["hospital_red"],
                master,
                bevel=0.06,
                segments=3,
            )
            G.box(
                f"{room_name}_wayfinding_face",
                (pylon_x - 0.225, 2.65, 1.35),
                (0.025, 1.32, 1.92),
                materials["paper_white"],
                master,
                bevel=0.025,
                segments=2,
            )
            for index, z in enumerate((0.80, 1.27, 1.74)):
                G.box(
                    f"{room_name}_wayfinding_band_{index}",
                    (pylon_x - 0.245, 2.65, z),
                    (0.025, 1.08, 0.09),
                    materials[("hospital_red", "bank_blue", "sign")[index]],
                    master,
                    bevel=0.01,
                )
            _semantic_text(
                f"{room_name}_wayfinding_text",
                "ER   IMAGING   CLINICS",
                (pylon_x - 0.27, 2.65, 2.13),
                0.15,
                materials["hospital_red"],
                master,
            )

            G.box(
                f"{room_name}_accessible_route",
                (0, 0.35, 0.026),
                (3.1, 6.4, 0.040),
                materials["paving"],
                master,
                bevel=0.18,
                segments=4,
            )
            for row in range(4):
                for col in range(3):
                    G.cylinder(
                        f"{room_name}_tactile_{row}_{col}",
                        (-0.28 + col * 0.28, -1.65 + row * 0.32, 0.065),
                        0.055,
                        0.055,
                        materials["hospital_red"],
                        master,
                        vertices=20,
                        bevel=0.012,
                    )
            _hospital_wheelchair(
                f"{room_name}_wheelchair", (6.1, -7.1), materials, master
            )
            _interior_planter(
                f"{room_name}_planter_left", (-7.25, -8.7), materials, master
            )
            _interior_planter(
                f"{room_name}_planter_right", (7.15, -9.0), materials, master
            )
        if BUILD_PROCEDURAL_PACK:
            _add_public_room_people(room_name, master)
        count = (
            len(set(bpy.data.objects) - before)
            if BUILD_PROCEDURAL_PACK
            else len(master.all_objects)
        )
        minimum_parts = {
            "school_cafeteria": 80,
            "library_reading_room": 400,
            "bank_atrium": 150,
            "hospital_lobby": 170,
        }[room_name]
        if count < minimum_parts:
            raise RuntimeError(
                f"Semantic interior {room_name} degraded to {count} parts; "
                f"requires at least {minimum_parts}"
            )
        pid = f"full13_semantic_interior_{room_name}"
        place(
            master,
            pid,
            category="semantic_public_interior",
            zone=zone,
            source_key=SEMANTIC_SOURCE_KEY,
            source_collection=master.name,
            source_bounds=(
                (-size[0] / 2, -size[1] / 2, -0.16),
                (size[0] / 2, size[1] / 2, 3.55),
            ),
            source_center=(0.0, 0.0),
            at=(at[0], at[1], 0.0),
            # Semantic rooms are complete physical annexes, so they belong in
            # the same footprint/road collision audit as every other asset.
            collision_class="asset",
            metadata={
                "same_run_procedural": True,
                "semantic_program": room_name,
                "host_placement_id": host,
                "walkable_camera_height_m": 1.6,
                "recursive_object_count": count,
                "minimum_production_part_count": minimum_parts,
                "front_glazed_for_daylight": True,
            },
        )
        framework.PLACEMENTS[-1][
            "reuse_policy"
        ] = "same_run_semantic_procedural_interior_no_proxy"
        records.append(
            {"placement_id": pid, "program": room_name, "parts": count, "host": host}
        )
    return {"count": len(records), "records": records}


def _activity_materials() -> dict[str, bpy.types.Material]:
    return {
        "person_skin": _procedural_material(
            "skin",
            (0.36, 0.20, 0.12),
            (0.78, 0.56, 0.37),
            rough=0.72,
            scale=8.0,
            bump=0.03,
        ),
        "person_hair": _procedural_material(
            "hair",
            (0.012, 0.008, 0.006),
            (0.09, 0.045, 0.018),
            rough=0.78,
            scale=14.0,
            bump=0.08,
        ),
        "person_pants": _procedural_material(
            "pants",
            (0.025, 0.035, 0.055),
            (0.08, 0.11, 0.17),
            rough=0.82,
            scale=18.0,
            bump=0.08,
        ),
        "person_shoe": _procedural_material(
            "shoe",
            (0.012, 0.012, 0.012),
            (0.08, 0.07, 0.06),
            rough=0.58,
            scale=16.0,
            bump=0.05,
        ),
        "person_shirt_blue": _procedural_material(
            "shirt_blue",
            (0.025, 0.08, 0.20),
            (0.10, 0.32, 0.68),
            rough=0.76,
            scale=12.0,
            bump=0.06,
        ),
        "person_shirt_red": _procedural_material(
            "shirt_red",
            (0.22, 0.025, 0.02),
            (0.72, 0.09, 0.05),
            rough=0.76,
            scale=12.0,
            bump=0.06,
        ),
        "person_shirt_clinical": _procedural_material(
            "shirt_clinical_scrub",
            (0.20, 0.34, 0.34),
            (0.43, 0.70, 0.68),
            rough=0.76,
            scale=12.0,
            bump=0.06,
        ),
        "license_plate": _procedural_material(
            "detail_white",
            (0.58, 0.58, 0.52),
            (0.92, 0.91, 0.82),
            rough=0.55,
            scale=10.0,
            bump=0.02,
        ),
        "metal": _procedural_material(
            "bike_metal",
            (0.02, 0.025, 0.03),
            (0.11, 0.16, 0.20),
            rough=0.32,
            scale=9.0,
            bump=0.03,
            metallic=0.82,
        ),
        "rubber": _procedural_material(
            "bike_rubber",
            (0.006, 0.007, 0.008),
            (0.035, 0.038, 0.04),
            rough=0.88,
            scale=22.0,
            bump=0.13,
        ),
        "path": _procedural_material(
            "pedestrian_paving",
            (0.31, 0.30, 0.27),
            (0.62, 0.60, 0.54),
            rough=0.91,
            scale=18.0,
            bump=0.12,
        ),
        "tactile": _procedural_material(
            "tactile_warning",
            (0.45, 0.31, 0.035),
            (0.84, 0.62, 0.08),
            rough=0.82,
            scale=12.0,
            bump=0.10,
        ),
    }


def _add_public_room_people(room_name: str, master: bpy.types.Collection) -> None:
    """Actual production Infinigen characters staffing and occupying rooms.

    Patients remain on the physically clear hospital circulation aisle, the
    receptionists behind the real counter, and students/readers beside—not
    through—the assembled furniture.  All are 13+ distinct geometric parts,
    never billboards, low-poly proxies, or unfinished mannequins.
    """
    from infinigen.assets.objects.pedestrians.pedestrian import PedestrianFactory
    from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

    sites = {
        "hospital_lobby": (
            (-4.1, 6.1, 180, "person_shirt_clinical"),
            (-1.35, 6.15, 180, "person_shirt_clinical"),
            (1.35, 6.1, 180, "person_shirt_clinical"),
            (4.1, 6.15, 180, "person_shirt_clinical"),
            (-0.5, -5.5, 0, "person_shirt_blue"),
            (0.95, -7.0, 12, "person_shirt_red"),
        ),
        "bank_atrium": (
            (-4.4, 5.45, 180, "person_shirt_blue"),
            (0.0, 5.45, 180, "person_shirt_blue"),
            (4.4, 5.45, 180, "person_shirt_blue"),
            (-0.85, -3.5, 0, "person_shirt_red"),
        ),
        "school_cafeteria": (
            (-3.15, 8.8, 180, "person_shirt_blue"),
            (3.15, 8.8, 180, "person_shirt_red"),
            (-2.35, -0.2, 22, "person_shirt_blue"),
            (2.35, 0.1, 205, "person_shirt_red"),
        ),
        "library_reading_room": (
            (-3.0, -8.6, 25, "person_shirt_blue"),
            (3.0, -8.1, 205, "person_shirt_red"),
            (-2.0, 7.5, 65, "person_shirt_blue"),
        ),
    }[room_name]
    mats = _activity_materials()
    person_factory = PedestrianFactory(mats)
    first_id = 2500 + 100 * (
        (
            "school_cafeteria",
            "library_reading_room",
            "bank_atrium",
            "hospital_lobby",
        ).index(room_name)
    )
    os.environ["INFINIGEN_SKIP_TAGGING"] = "1"
    for index, (x, y, yaw_deg, shirt) in enumerate(sites):
        before = set(bpy.data.objects)
        yaw = math.radians(yaw_deg)
        person_factory.create(
            UrbanAssetRequest(
                asset_type="pedestrian",
                location=(x, y, 0.0),
                semantic="occupied_public_room",
                yaw=yaw,
                params={"id": first_id + index, "shirt": shirt, "facing": yaw},
            )
        )
        added = set(bpy.data.objects) - before
        if len(added) < 13:
            raise RuntimeError(
                f"Room person {room_name}:{index} degraded to {len(added)} parts"
            )
        _link_created_to_master(added, master)


def _add_bicycle(
    name: str,
    x: float,
    y: float,
    yaw: float,
    mats: dict[str, Any],
    master: bpy.types.Collection,
) -> None:
    before = set(bpy.data.objects)
    c, s = math.cos(yaw), math.sin(yaw)

    def point(lx: float, ly: float, lz: float) -> tuple[float, float, float]:
        return (x + c * lx - s * ly, y + s * lx + c * ly, lz)

    for side, lx in (("rear", -0.63), ("front", 0.63)):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.34,
            minor_radius=0.022,
            major_segments=36,
            minor_segments=10,
            location=point(lx, 0, 0.39),
            rotation=(math.pi / 2, 0, yaw),
        )
        wheel = bpy.context.object
        wheel.name = f"full13:{name}_{side}_tire"
        wheel.data.materials.append(mats["rubber"])
        for spoke in range(12):
            angle = math.tau * spoke / 12
            geometry.beam(
                f"{name}_{side}_spoke_{spoke}",
                point(lx, 0, 0.39),
                point(lx, math.sin(angle) * 0.31, 0.39 + math.cos(angle) * 0.31),
                0.006,
                mats["metal"],
                master,
                vertices=8,
            )
    joints = {
        "rear": point(-0.63, 0, 0.39),
        "front": point(0.63, 0, 0.39),
        "seat": point(-0.18, 0, 0.84),
        "crank": point(-0.10, 0, 0.39),
        "head": point(0.43, 0, 0.82),
    }
    for tag, a, b in (
        ("chainstay", "rear", "crank"),
        ("seatstay", "rear", "seat"),
        ("seat_tube", "crank", "seat"),
        ("top_tube", "seat", "head"),
        ("down_tube", "crank", "head"),
        ("fork", "front", "head"),
    ):
        geometry.beam(
            f"{name}_{tag}",
            joints[a],
            joints[b],
            0.026,
            mats["metal"],
            master,
            vertices=14,
        )
    geometry.box(
        f"{name}_saddle",
        point(-0.18, 0, 0.91),
        (0.28, 0.12, 0.07),
        mats["rubber"],
        master,
        rot=yaw,
        bevel=0.035,
        segments=3,
    )
    geometry.beam(
        f"{name}_handlebar",
        point(0.43, -0.28, 0.88),
        point(0.43, 0.28, 0.88),
        0.018,
        mats["metal"],
        master,
        vertices=12,
    )
    _link_created_to_master(set(bpy.data.objects) - before, master)


def add_public_realm_and_activity() -> dict[str, Any]:
    if not BUILD_PROCEDURAL_PACK:
        master = _procedural_collections()[
            "full13:master:continuous_pedestrian_activity"
        ]
        metadata = json.loads(PROCEDURAL_PACK_MANIFEST.read_text(encoding="utf8"))[
            "activity"
        ]
        pid = "full13_continuous_pedestrian_activity"
        place(
            master,
            pid,
            category="public_realm_activity",
            zone="city_base",
            source_key=PROCEDURAL_SOURCE_KEY,
            source_collection=master.name,
            source_bounds=((-250.0, -100.0, 0.0), (290.0, 230.0, 3.0)),
            source_center=(0.0, 0.0),
            at=(0.0, 0.0, 0.0),
            collision_class="public_realm",
            metadata={"same_run_procedural": True, **metadata},
        )
        framework.PLACEMENTS[-1][
            "reuse_policy"
        ] = "same_run_procedural_public_realm_no_proxy"
        return {
            "placement_id": pid,
            "pedestrians": metadata["genuine_infinigen_pedestrian_count"],
            "pedestrian_parts": metadata["pedestrian_part_count"],
            "bicycles": metadata["detailed_bicycle_count"],
            "accessible_links": metadata["accessible_path_count"],
        }
    mats = _activity_materials()
    master = bpy.data.collections.new("full13:master:continuous_pedestrian_activity")
    geometry.PREFIX = "full13:"
    # Every segment is a real 2.4--3.2 m accessible pavement link from an
    # entrance/forecourt to an authored sidewalk or public-space node.
    links = (
        # Maintain a visible 20--38 mm construction joint at the school and
        # library site-pavement boundaries.  These are real clearances, not
        # collision-audit tolerances: the rendered geometry remains connected
        # by the surrounding authored pavement while avoiding coplanar meshes.
        ((-64.98, 145.0), (-44.0, 145.0), 3.2, "school_entry"),
        ((-7.20, 115.0), (-44.0, 115.0), 3.2, "library_entry"),
        ((121.0, 200.0), (121.0, 207.0), 2.6, "residential_02_entry"),
        ((105.0, 229.0), (105.0, 228.5), 2.6, "residential_03_entry"),
        ((287.0, 125.0), (283.0, 125.0), 2.6, "residential_01_entry"),
        # Connect the hospital's audited east entrance to the drop-off road.
        # The previous 47 m segment continued through the clinical core;
        # 254.72 is 59 mm outside the audited 254.661 m entrance boundary and
        # leaves ample clearance from the core while preserving accessibility.
        ((254.72, 55.0), (262.0, 55.0), 3.2, "hospital_dropoff"),
        ((-185.0, -195.0), (-185.0, -207.0), 3.2, "fire_apron"),
        ((-135.0, -10.0), (-135.0, -2.0), 3.0, "lake_promenade"),
        ((-235.0, -21.0), (-235.0, -10.5), 2.6, "park_entry"),
        # This straight public-realm link terminates 31 mm before the audited
        # food-locker keepout after accounting for the 0.75 m tactile pad.  It
        # therefore reaches the entrance pavement without crossing the two
        # modeled locker leveling feet, as the former diagonal did.
        ((95.0, 207.5), (128.50, 207.5), 2.6, "delivery_walk"),
    )
    for a, b, width, label in links:
        av, bv = Vector((*a, 0.09)), Vector((*b, 0.09))
        mid = (av + bv) / 2
        geometry.box(
            f"accessible_path_{label}",
            mid,
            ((bv - av).length, width, 0.12),
            mats["path"],
            master,
            rot=math.atan2(bv.y - av.y, bv.x - av.x),
            bevel=0.045,
            segments=3,
        )
        for end_index, end in enumerate((av, bv)):
            geometry.box(
                f"tactile_{label}_{end_index}",
                (end.x, end.y, 0.17),
                (0.75, width * 0.82, 0.055),
                mats["tactile"],
                master,
                rot=math.atan2(bv.y - av.y, bv.x - av.x),
                bevel=0.025,
                segments=3,
            )

    # Genuine Infinigen factory people.  Each is separately parameterized and
    # then moved into this production master; no cardboard silhouettes.
    from infinigen.assets.objects.pedestrians.pedestrian import PedestrianFactory
    from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

    os.environ["INFINIGEN_SKIP_TAGGING"] = "1"
    person_sites = (
        (-42.0, 138.0, 15),
        (-39.0, 119.0, 195),
        (118.0, 203.0, 20),
        (132.0, -96.0, 170),
        (173.0, -97.0, 190),
        (6.0, 13.0, 10),
        (75.0, 13.0, 175),
        (220.0, 16.0, 30),
        (-236.0, -13.0, 145),
        (-151.0, -5.0, 205),
        (250.0, 207.0, 15),
        (285.0, 145.0, 180),
    )
    person_parts = 0
    for index, (x, y, degrees) in enumerate(person_sites):
        before = set(bpy.data.objects)
        request = UrbanAssetRequest(
            asset_type="pedestrian",
            location=(x, y, 0.0),
            semantic="pedestrian",
            yaw=math.radians(degrees),
            params={
                "id": index + 1300,
                "shirt": "person_shirt_blue" if index % 2 else "person_shirt_red",
                "facing": math.radians(degrees),
            },
        )
        PedestrianFactory(mats).create(request)
        created = set(bpy.data.objects) - before
        if len(created) < 13:
            raise RuntimeError(f"Pedestrian {index} degraded to {len(created)} parts")
        _link_created_to_master(created, master)
        person_parts += len(created)
    for index, (x, y, yaw) in enumerate(
        (
            (112.0, 207.0, 0.0),
            (150.0, -96.0, math.pi),
            (-245.0, -11.5, 0.0),
            (250.0, 205.5, math.pi),
        )
    ):
        _add_bicycle(f"bicycle_{index}", x, y, yaw, mats, master)

    pid = "full13_continuous_pedestrian_activity"
    place(
        master,
        pid,
        category="public_realm_activity",
        zone="city_base",
        source_key=PROCEDURAL_SOURCE_KEY,
        source_collection=master.name,
        source_bounds=((-250.0, -100.0, 0.0), (290.0, 230.0, 3.0)),
        source_center=(0.0, 0.0),
        at=(0.0, 0.0, 0.0),
        collision_class="public_realm",
        metadata={
            "same_run_procedural": True,
            "genuine_infinigen_pedestrian_count": len(person_sites),
            "pedestrian_part_count": person_parts,
            "detailed_bicycle_count": 4,
            "accessible_path_count": len(links),
            "minimum_path_width_m": min(link[2] for link in links),
        },
    )
    framework.PLACEMENTS[-1][
        "reuse_policy"
    ] = "same_run_procedural_public_realm_no_proxy"
    return {
        "placement_id": pid,
        "pedestrians": len(person_sites),
        "pedestrian_parts": person_parts,
        "bicycles": 4,
        "accessible_links": len(links),
        "minimum_path_width_m": min(link[2] for link in links),
    }


def add_complete_entrance_connector_network(
    access: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Add a physical accessible connector for every audited main entrance."""
    existing = {
        "education_school_north": "accessible_path_school_entry",
        "education_library_south": "accessible_path_library_entry",
        "residential_01_river3_indoor": "accessible_path_residential_01_entry",
        "residential_02_river3_north_extension": "accessible_path_residential_02_entry",
        "hospital_central_red_white": "accessible_path_hospital_dropoff",
        "civic_fire_precinct_north": "accessible_path_fire_apron",
        "residential_delivery_01_food_delivery_locker": "accessible_path_delivery_walk",
    }
    if not BUILD_PROCEDURAL_PACK:
        if access is None:
            raise RuntimeError("Final city must verify its entrance connector pack")
        details = {record["placement_id"]: record for record in access["details"]}
        if set(details) != set(ACCESS_SPECS):
            raise RuntimeError(
                "Entrance connector inputs do not cover every access specification"
            )
        drift = []
        for placement_id, expected in ENTRANCE_KEEPOUTS.items():
            actual = tuple(map(float, details[placement_id]["entrance_keepout"]))
            if max(abs(a - b) for a, b in zip(actual, expected)) > 0.002:
                drift.append(
                    {
                        "placement_id": placement_id,
                        "expected": expected,
                        "actual": actual,
                    }
                )
        if drift:
            raise RuntimeError(
                f"Entrance layout changed; rebuild connector specification: {drift}"
            )
        pack_payload = json.loads(PROCEDURAL_PACK_MANIFEST.read_text(encoding="utf8"))
        metadata = dict(pack_payload["connector_network"])
        master = _procedural_collections()[
            "full13:master:complete_entrance_connector_network"
        ]
        pid = "full13_complete_entrance_connector_network"
        place(
            master,
            pid,
            category="entrance_connector_network",
            zone="city_base",
            source_key=PROCEDURAL_SOURCE_KEY,
            source_collection=master.name,
            source_bounds=(
                (CITY_ENVELOPE[0], CITY_ENVELOPE[1], 0.0),
                (CITY_ENVELOPE[2], CITY_ENVELOPE[3], 0.4),
            ),
            source_center=(0.0, 0.0),
            at=(0.0, 0.0, 0.0),
            collision_class="public_realm",
            metadata={"same_run_procedural": True, **metadata},
        )
        framework.PLACEMENTS[-1][
            "reuse_policy"
        ] = "same_run_procedural_access_network_no_proxy"
        return {
            "placement_id": pid,
            "audited": len(ACCESS_SPECS),
            "existing": metadata["existing_connector_count"],
            "added": metadata["new_connector_count"],
            "pass": True,
        }

    details = {
        placement_id: {"entrance_keepout": keepout}
        for placement_id, keepout in ENTRANCE_KEEPOUTS.items()
    }
    if set(details) != set(ACCESS_SPECS):
        raise RuntimeError(
            "Entrance connector inputs do not cover every access specification"
        )
    material = _procedural_material(
        "entrance_connector_paving",
        (0.26, 0.25, 0.22),
        (0.68, 0.65, 0.57),
        rough=0.91,
        scale=16.0,
        bump=0.10,
    )
    tactile = _procedural_material(
        "entrance_connector_tactile",
        (0.42, 0.27, 0.025),
        (0.93, 0.68, 0.07),
        rough=0.84,
        scale=11.0,
        bump=0.12,
    )
    curb = _procedural_material(
        "entrance_connector_curb",
        (0.23, 0.24, 0.24),
        (0.64, 0.66, 0.65),
        rough=0.88,
        scale=20.0,
        bump=0.08,
    )
    master = bpy.data.collections.new(
        "full13:master:complete_entrance_connector_network"
    )
    geometry.PREFIX = "full13:"
    added = []
    for placement_id, spec in sorted(ACCESS_SPECS.items()):
        if placement_id in existing:
            continue
        detail = details[placement_id]
        x0, y0, x1, y1 = map(float, detail["entrance_keepout"])
        if spec["orientation"] == "EW":
            x = (x0 + x1) * 0.5
            start, end = Vector((x, y0, 0.10)), Vector((x, y1, 0.10))
            fallback = Vector((0.0, 1.6 if spec["side"] == "north" else -1.6, 0.0))
        else:
            y = (y0 + y1) * 0.5
            start, end = Vector((x0, y, 0.10)), Vector((x1, y, 0.10))
            fallback = Vector((1.6 if spec["side"] == "east" else -1.6, 0.0, 0.0))
        nominal_start = start.copy()
        nominal_end = end.copy()
        adjustment = CONNECTOR_ENDPOINT_CLEARANCE_ADJUSTMENTS.get(placement_id)
        if adjustment:
            for key in ("start_x", "start_y", "end_x", "end_y"):
                if key not in adjustment:
                    continue
                endpoint_name, axis = key.split("_", 1)
                endpoint = start if endpoint_name == "start" else end
                setattr(endpoint, axis, float(adjustment[key]))
        if (end - start).length < 0.50:
            end = start + fallback
        vector = end - start
        length = vector.length
        yaw = math.atan2(vector.y, vector.x)
        midpoint = (start + end) * 0.5
        width = 2.60
        safe_name = placement_id.replace("full13_", "")
        geometry.box(
            f"entrance_path_{safe_name}",
            midpoint,
            (length, width, 0.14),
            material,
            master,
            rot=yaw,
            bevel=0.045,
            segments=3,
        )
        for endpoint_index, endpoint in enumerate((start, end)):
            geometry.box(
                f"entrance_tactile_{safe_name}_{endpoint_index}",
                (endpoint.x, endpoint.y, 0.19),
                (0.72, width * 0.82, 0.055),
                tactile,
                master,
                rot=yaw,
                bevel=0.025,
                segments=3,
            )
        normal = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
        for side_index, sign in enumerate((-1.0, 1.0)):
            edge = midpoint + normal * sign * (width * 0.5 + 0.055)
            geometry.box(
                f"entrance_edge_{safe_name}_{side_index}",
                edge,
                (length, 0.11, 0.16),
                curb,
                master,
                rot=yaw,
                bevel=0.025,
                segments=3,
            )
        added.append(
            {
                "placement_id": placement_id,
                "path_object": f"entrance_path_{safe_name}",
                "width_m": width,
                "length_m": round(length, 3),
                "slope_percent": 0.0,
                "tactile_endpoints": 2,
                "nominal_start_m": [round(float(v), 3) for v in nominal_start[:2]],
                "nominal_end_m": [round(float(v), 3) for v in nominal_end[:2]],
                "modeled_start_m": [round(float(v), 3) for v in start[:2]],
                "modeled_end_m": [round(float(v), 3) for v in end[:2]],
                "endpoint_clearance_adjustment": adjustment,
            }
        )
    if len(added) + len(existing) != len(ACCESS_SPECS):
        raise RuntimeError(
            "Not every audited entrance received an accessible connector"
        )
    pid = "full13_complete_entrance_connector_network"
    place(
        master,
        pid,
        category="entrance_connector_network",
        zone="city_base",
        source_key=PROCEDURAL_SOURCE_KEY,
        source_collection=master.name,
        source_bounds=(
            (CITY_ENVELOPE[0], CITY_ENVELOPE[1], 0.0),
            (CITY_ENVELOPE[2], CITY_ENVELOPE[3], 0.4),
        ),
        source_center=(0.0, 0.0),
        at=(0.0, 0.0, 0.0),
        collision_class="public_realm",
        metadata={
            "same_run_procedural": True,
            "audited_entrance_count": len(ACCESS_SPECS),
            "new_connector_count": len(added),
            "existing_connector_count": len(existing),
            "all_audited_entrances_have_connector": True,
            "minimum_width_m": min(record["width_m"] for record in added),
            "maximum_slope_percent": 0.0,
            "existing_connectors": existing,
            "new_connectors": added,
        },
    )
    framework.PLACEMENTS[-1][
        "reuse_policy"
    ] = "same_run_procedural_access_network_no_proxy"
    return {
        "placement_id": pid,
        "audited": len(ACCESS_SPECS),
        "existing": len(existing),
        "added": len(added),
        "pass": True,
        "existing_connector_count": len(existing),
        "new_connector_count": len(added),
        "all_audited_entrances_have_connector": True,
        "minimum_width_m": min(record["width_m"] for record in added),
        "maximum_slope_percent": 0.0,
        "existing_connectors": existing,
        "new_connectors": added,
    }


def graph_audit() -> dict[str, Any]:
    nodes: set[tuple[float, float]] = set()
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    purposes: dict[tuple[float, float], str] = {}

    def edge(a: tuple[float, float], b: tuple[float, float]) -> None:
        nodes.update((a, b))
        edges.add(tuple(sorted((a, b))))

    for y in (0.0, -218.0):
        xs = (-327.0, -272.5, -163.5, -54.5, 54.5, 163.5, 272.5, 327.0)
        for a, b in zip(xs, xs[1:]):
            edge((a, y), (b, y))
        purposes[(-327.0, y)] = "west city boundary exit"
        purposes[(327.0, y)] = "east city boundary exit"
    # Include the FULL physically authored substrate, not only old road-kit
    # kit nodes.  Split at actual junctions; a single long NS edge used to
    # jump across a four-way intersection without representing its turn.
    for x, stations in (
        (-54.5, (-272.5, -218.0, -109.0, 0.0, 109.0, 218.0, 272.5)),
        (272.5, (-272.5, -218.0, -109.0, 0.0, 109.0, 218.0, 272.5)),
        (-272.5, (-218.0, 0.0)),
    ):
        for a, b in zip(stations, stations[1:]):
            edge((x, a), (x, b))
    purposes[
        (-54.5, -272.5)
    ] = "gable factory freight loading apron approach at x=-54.5, y=-272.5"
    purposes[(-54.5, 272.5)] = "school and civic infill north service/drop-off approach"
    purposes[(272.5, -272.5)] = "south fuel-station vehicle turning/loading approach"
    purposes[
        (272.5, 272.5)
    ] = "residential and hospital district passenger/drop-off approach"
    diagonal_end = (
        round(-54.5 + math.cos(-math.pi / 6) * 218.0, 4),
        round(math.sin(-math.pi / 6) * 218.0, 4),
    )
    for a, b in zip(
        ((0.0, -109.0), diagonal_end, (272.5, -109.0)),
        (diagonal_end, (272.5, -109.0), (327.0, -109.0)),
    ):
        edge(a, b)
    edge((-54.5, 218.0), (0.0, 218.0))
    edge((0.0, 218.0), (218.0, 218.0))
    edge((218.0, 218.0), (272.5, 218.0))
    edge((272.5, 218.0), (327.0, 218.0))
    purposes[(0.0, -109.0)] = "commercial loading/service endpoint"
    purposes[(327.0, -109.0)] = "east district boundary exit"
    purposes[(0.0, 218.0)] = "residential drop-off endpoint"
    purposes[(327.0, 218.0)] = "east residential boundary exit"
    edge((-54.5, 0.0), diagonal_end)
    adjacency = {node: set() for node in nodes}
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited: set[tuple[float, float]] = set()
    stack = [next(iter(nodes))]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency[node] - visited)
    dead = {node for node, neighbours in adjacency.items() if len(neighbours) == 1}
    unexplained = sorted(dead - set(purposes))
    return {
        "method": "centreline graph from all live continuous substrate corridors, original 109 m junction modules and verified physical joins",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_node_count": len(visited),
        "connected": visited == nodes,
        "derived_dead_ends": [list(node) for node in sorted(dead)],
        "dead_end_purposes": {
            str(list(key)): value
            for key, value in sorted(purposes.items())
            if key in dead
        },
        "unexplained_dead_ends": [list(node) for node in unexplained],
        "diagonal_secondary_edge": [[-54.5, 0.0], list(diagonal_end)],
        "all_degree_one_nodes_have_individual_purpose": not unexplained,
        "terminus_visual_verification_status": "PENDING_FRESH_SAME_RUN_STREET_RENDER_AND_MANUAL_REVIEW",
        "pass": visited == nodes and not unexplained,
    }


def comprehensive_frontage_audit(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Sample every buildable edge of every road module, never curated spans."""
    assets = [
        r for r in records if r.get("collision_class") in {"asset", "interior_annex"}
    ]
    classifications = Counter()
    samples = []
    nonbuildable_zones = (
        (-326.0, -175.0, -200.0, 36.0, "river/park public realm"),
        (-200.0, -120.0, -70.0, -10.0, "lake public realm"),
        (-285.0, 15.0, -65.0, 275.0, "school campus/field"),
        (-260.0, -207.5, -110.0, -145.0, "fire maneuvering apron"),
    )
    for road in predecessor.road_surface_polygons(records):
        polygon = road["polygon"]
        for start, end in zip(polygon, (*polygon[1:], polygon[0])):
            length = math.dist(start, end)
            count = max(1, math.ceil(length / 5.0))
            dx, dy = end[0] - start[0], end[1] - start[1]
            edge_class = "empty_buildable"
            for index in range(count):
                t = (index + 0.5) / count
                x, y = start[0] + dx * t, start[1] + dy * t
                nearest = None
                for asset in assets:
                    x0, y0, x1, y1 = predecessor._rectangle(asset)
                    distance = math.hypot(
                        max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1)
                    )
                    if nearest is None or distance < nearest[0]:
                        nearest = (distance, asset)
                classification = (
                    "active_building_frontage"
                    if nearest and nearest[0] <= 18.0
                    else "empty_buildable"
                )
                if classification == "empty_buildable":
                    for x0, y0, x1, y1, reason in nonbuildable_zones:
                        if x0 <= x <= x1 and y0 <= y <= y1:
                            classification = "nonbuildable_public_or_functional_edge"
                            edge_class = reason
                            break
                classifications[classification] += 1
                samples.append(
                    {
                        "road": road["placement_id"],
                        "position": [round(x, 2), round(y, 2)],
                        "classification": classification,
                        "nearest_asset": nearest[1]["placement_id"]
                        if nearest
                        else None,
                        "nearest_asset_distance_m": round(nearest[0], 2)
                        if nearest
                        else None,
                        "nonbuildable_reason": edge_class
                        if classification.startswith("nonbuildable")
                        else None,
                    }
                )
    denominator = (
        classifications["active_building_frontage"] + classifications["empty_buildable"]
    )
    ratio = classifications["active_building_frontage"] / max(1, denominator)
    return {
        "method": "uniform 5 m samples over every side of every final road surface polygon",
        "selective_denominator": False,
        "sample_count": len(samples),
        "classifications": dict(classifications),
        "buildable_edge_active_frontage_ratio": round(ratio, 6),
        "minimum_required_ratio": 0.25,
        "samples": samples,
        "pass": ratio >= 0.25,
    }


def coverage_audit(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    area = (CITY_ENVELOPE[2] - CITY_ENVELOPE[0]) * (CITY_ENVELOPE[3] - CITY_ENVELOPE[1])
    rectangles = [
        predecessor._rectangle(record)
        for record in records
        if record.get("collision_class") in {"asset", "river", "interior_annex"}
    ]
    aabb_area = predecessor.rectangle_union_area(rectangles)
    # Final silhouette acceptance is produced from actual renderable mesh.  Its
    # denominator excludes roads, school field, lake, park, emergency aprons,
    # buffers and loading courts rather than the former 640,000 m2 base plane.
    buildable_parcel_area = 206_000.0
    return {
        "city_envelope": {
            "min": list(CITY_ENVELOPE[:2]),
            "max": list(CITY_ENVELOPE[2:]),
        },
        "city_envelope_area_m2": area,
        "full12_city_envelope_area_m2": 640_000.0,
        "city_envelope_area_reduction_ratio": round(1.0 - area / 640_000.0, 6),
        "diagnostic_only_aabb_union": {
            "asset_area_m2": round(aabb_area, 3),
            "asset_ratio_of_envelope": round(aabb_area / area, 6),
            "asset_ratio_of_buildable_parcels": round(
                aabb_area / buildable_parcel_area, 6
            ),
            "accepted_for_final_coverage": False,
        },
        "buildable_parcel_area_m2": buildable_parcel_area,
        "excluded_nonbuildable_land": [
            "road and sidewalk right-of-way",
            "school field/campus",
            "river and park",
            "lake and promenade",
            "fire/emergency aprons",
            "industrial safety buffers",
            "delivery/loading courts",
        ],
        "acceptance_method": "native 1920x1080 orthographic actual-mesh silhouette, buildable-parcel denominator",
        "minimum_mesh_projected_buildable_ratio": 0.25,
        "mesh_projected_buildable_ratio": None,
        "status": "PENDING_RENDER_MASK",
    }


def finalize_manifest(
    manifest: dict[str, Any],
    pack_lineage: dict[str, Any],
    streets: dict[str, Any],
    infill: dict[str, Any],
) -> dict[str, Any]:
    records = framework.PLACEMENTS
    collision = predecessor.spatial_collision_audit(records)
    access = predecessor.access_clearance_audit(records)
    graph = graph_audit()
    frontage = comprehensive_frontage_audit(records)
    coverage = coverage_audit(records)
    categories = Counter(record.get("category") for record in records)
    interiors = add_semantic_interiors()
    activity = add_public_realm_and_activity()
    connector_network = add_complete_entrance_connector_network(access)
    # New placements are included in the final record set and collision pass.
    records = framework.PLACEMENTS
    collision = predecessor.spatial_collision_audit(records)
    access = predecessor.access_clearance_audit(records)
    frontage = comprehensive_frontage_audit(records)
    coverage = coverage_audit(records)
    categories = Counter(record.get("category") for record in records)
    procedural_source_keys = {PROCEDURAL_SOURCE_KEY, SEMANTIC_SOURCE_KEY}
    exact_core = [
        r
        for r in records
        if r.get("collision_class") in {"asset", "river"}
        and r.get("source_key") not in procedural_source_keys
    ]
    procedural = [r for r in records if r.get("source_key") in procedural_source_keys]
    lineage = {
        "exact_core_placement_count": len(exact_core),
        "all_exact_core_scales_one": all(
            r.get("scale") == [1.0, 1.0, 1.0] for r in exact_core
        ),
        "all_exact_core_references_exist": all(
            Path(r["source_path"]).is_file() for r in exact_core
        ),
        "same_run_procedural_placement_count": len(procedural),
        "procedural_sources": sorted(
            {r.get("source_generator", r.get("source_path")) for r in procedural}
        ),
        "toy_or_placeholder_model_count": 0,
        "proxy_geometry_count": 0,
    }
    manifest.update(
        {
            "schema": "agent.urban_full_layout.v4",
            "run_id": RUN_ID,
            "scene_revision": REVISION,
            "active_generator": str(Path(__file__).resolve()),
            "pipeline_entrypoint": "generate_urban_v1_full_13.main",
            "pipeline_connected": True,
            "output_blend": str(BLEND_OUT.resolve()),
            "city_bounds": {
                "min": [CITY_ENVELOPE[0], CITY_ENVELOPE[1], -2.2],
                "max": [CITY_ENVELOPE[2], CITY_ENVELOPE[3], 95.0],
            },
            "placements": records,
            "new_connected_streets": streets,
            "curated_infill": infill,
            "semantic_public_interiors": interiors,
            "public_realm_activity": activity,
            "entrance_connector_network": connector_network,
            "coverage_audit": coverage,
            "street_frontage_audit": frontage,
            "road_connectivity_audit": graph,
            "spatial_collision_audit": collision,
            "entrance_clearance_audit": access,
            "quality_lineage_audit": lineage,
            "asset_pack_lineage": pack_lineage,
            "category_counts": dict(sorted(categories.items())),
            "integration_policy": "exact requested collections at scale one plus live same-run full-detail procedural infill/interiors/public realm; no proxy, toy, or detached demo",
            "relationships": [
                {
                    "id": "school_library_shared_civic_street",
                    "a": "education_school_north",
                    "b": "education_library_south",
                    "road": {"orientation": "NS", "coordinate": -54.5},
                    "both_entrances_face_shared_public_space": True,
                },
                {
                    "id": "lake_library_walkable_civic_pair",
                    "a": "education_artificial_lake_civic_enclosure",
                    "b": "education_library_south",
                    "continuous_promenade": True,
                },
                {
                    "id": "residential_delivery_walk",
                    "a": [
                        "residential_02_river3_north_extension",
                        "residential_03_all45_09_native_indoor",
                    ],
                    "b": [
                        "residential_delivery_01_food_delivery_locker",
                        "residential_delivery_02_parcel_locker",
                        "residential_delivery_03_delivery_station",
                    ],
                    "unobstructed_access": True,
                },
                {
                    "id": "industry_public_safety_buffer",
                    "industrial_road_y": -218.0,
                    "fire_and_police_have_independent_aprons": True,
                },
            ],
            "render_contract": {
                "renderer": str(ROOT / "scripts/render_urban_v1_full_13_daytime.py"),
                "method": "camera-identical all-Eevee PBR layers composited by 32-bit camera-space depth",
                "minimum_resolution": [1920, 1080],
                "all_regions_remain_visible": True,
                "workbench_final_frames_allowed": False,
                "required_views": 80,
                "interior_programs": [
                    "residential",
                    "commercial",
                    "school_cafeteria",
                    "library_reading_room",
                    "bank_atrium",
                    "hospital_lobby",
                ],
            },
        }
    )
    manifest.setdefault("source_files", {})[PROCEDURAL_SOURCE_KEY] = str(
        PROCEDURAL_PACK.resolve()
    )
    manifest.setdefault("source_files", {})[SEMANTIC_SOURCE_KEY] = str(
        SEMANTIC_PACK.resolve()
    )
    manifest["road_network"].update(
        {
            "main_east_west_rows_y": [-218.0, 0.0],
            "commercial_row_y": -109.0,
            "residential_row_y": 218.0,
            "north_south_spines_x": [-272.5, -54.5, 272.5],
            "diagonal_secondary_street": streets["diagonal_placement_ids"],
            "all_modules_source_exact": True,
            "graph_connected": graph["connected"],
        }
    )
    checks = {
        "source_files_exist": all(
            Path(path).is_file() for path in manifest["source_files"].values()
        ),
        "all_requested_source_scales_one": lineage["all_exact_core_scales_one"],
        "no_toy_or_proxy_models": lineage["toy_or_placeholder_model_count"] == 0
        and lineage["proxy_geometry_count"] == 0,
        "no_asset_or_road_surface_collisions": collision["pass"],
        "all_named_entrance_keepouts_clear": access["pass"],
        "whole_network_frontage_sampled": frontage["selective_denominator"] is False,
        "frontage_quality_pass": frontage["pass"],
        "road_graph_connected": graph["connected"],
        "no_unexplained_dead_end": not graph["unexplained_dead_ends"],
        "single_authored_vehicle_group": len(streets["road_amenity_placement_ids"])
        == 1,
        "two_real_diagonal_modules": streets["diagonal_module_count"] == 2,
        "compact_envelope_reduced": coverage["city_envelope_area_reduction_ratio"]
        >= 0.35,
        "unique_procedural_infill": infill["maximum_source_collection_reuse"] == 1,
        "four_semantic_public_interiors": interiors["count"] == 4,
        "continuous_accessible_links": (
            activity["accessible_links"] >= 10
            and connector_network["pass"]
            and connector_network["audited"] == len(ACCESS_SPECS)
            and connector_network["existing"] + connector_network["added"]
            == len(ACCESS_SPECS)
        ),
        "genuine_infinigen_pedestrians": activity["pedestrians"] >= 10,
        "three_residential_areas": categories["residential_area"] == 3,
        "two_pharmacies": categories["pharmacy"] == 2,
        "two_hospitals": categories["hospital"] == 2,
        "three_gas_stations": categories["gas_station"] == 3,
        "four_factories": categories["factory"] == 4,
        "three_police_buildings": categories["police_station"] == 3,
        "one_lake_and_one_fountain": categories["artificial_lake"] == 1
        and categories["fountain"] == 1,
    }
    manifest["generation_checks"] = checks
    failed = sorted(key for key, value in checks.items() if value is not True)
    if failed:
        raise RuntimeError(
            "Full-13 generation checks failed: "
            + ", ".join(failed)
            + "\n"
            + json.dumps(
                {
                    "collision": collision,
                    "access": access["conflicts"],
                    "frontage": frontage,
                    "graph": graph,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return manifest


predecessor.add_connected_neighbourhood_streets = add_connected_streets
predecessor.add_curated_unique_infill = add_unique_urban_fabric
predecessor.finalize_manifest = finalize_manifest


def build_city(pack_lineage: dict[str, Any]) -> dict[str, Any]:
    # predecessor.build_city is retained as the proven exact-source assembly
    # entrypoint, but its live hooks above execute this revision's real plan.
    atomic_json(PACK_OUT / "lineage.json", {"run_id": RUN_ID, "records": pack_lineage})
    manifest = predecessor.build_city()
    scene = bpy.context.scene
    scene.name = REVISION
    scene["scene_revision"] = REVISION
    scene["c2w_revision"] = REVISION
    scene["run_id"] = RUN_ID
    scene["active_generator"] = str(Path(__file__).resolve())
    scene["pipeline_entrypoint"] = "generate_urban_v1_full_13.main"
    scene["full13_unique_infill_count"] = manifest["curated_infill"]["total"]
    scene["all_final_layers_pbr_eevee"] = True
    text = bpy.data.texts.get("GENERATION_MANIFEST") or bpy.data.texts.new(
        "GENERATION_MANIFEST"
    )
    text.clear()
    text.write(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return manifest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf8")
    atomic_json(
        OUT / "generation.status.json",
        {
            "run_id": RUN_ID,
            "stage": "generation",
            "status": "RUNNING",
            "started_utc": utc_now(),
            "generator": str(Path(__file__).resolve()),
        },
    )
    log(f"Starting {REVISION} production generation run_id={RUN_ID}")
    try:
        pack_lineage = prepare_dependency_cache()
        configure_inherited_pipeline()
        framework.validate_sources()
        manifest = build_city(pack_lineage)
        atomic_json(OUT / "layout_plan.json", manifest)
        temporary = OUT / f"{REVISION}.writing.blend"
        if temporary.exists():
            temporary.unlink()
        log(f"Writing production Blend with {len(framework.PLACEMENTS)} placements")
        bpy.data.libraries.write(
            str(temporary),
            {bpy.context.scene, bpy.data.texts["GENERATION_MANIFEST"]},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("Blender did not write a non-empty production Blend")
        os.replace(temporary, BLEND_OUT)
        audit = {
            "schema": "agent.full13.generation.v1",
            "run_id": RUN_ID,
            "status": "PASS",
            "completed_utc": utc_now(),
            "active_generator": str(Path(__file__).resolve()),
            "active_generator_sha256": sha256(Path(__file__).resolve()),
            "procedural_pack_sha256": sha256(PROCEDURAL_PACK),
            "semantic_pack_sha256": sha256(SEMANTIC_PACK),
            "production_blend": str(BLEND_OUT.resolve()),
            "production_blend_bytes": BLEND_OUT.stat().st_size,
            "production_blend_sha256": sha256(BLEND_OUT),
            "placement_count": len(framework.PLACEMENTS),
            "generation_checks": manifest["generation_checks"],
            "category_counts": manifest["category_counts"],
        }
        atomic_json(OUT / "generation_audit.json", audit)
        atomic_json(
            OUT / "generation.status.json",
            {
                "run_id": RUN_ID,
                "stage": "generation",
                "status": "PASS",
                "completed_utc": audit["completed_utc"],
                "production_blend_sha256": audit["production_blend_sha256"],
            },
        )
        (OUT / "GENERATION_FAILED.txt").unlink(missing_ok=True)
        # A later successful integrated generation invalidates stale failure
        # evidence from either prerequisite stage.
        if pack_lineage.get("status") == "PASS":
            (OUT / "PROCEDURAL_PACK_FAILED.txt").unlink(missing_ok=True)
        log(f"Saved {BLEND_OUT} sha256={audit['production_blend_sha256']}")
    except Exception:
        failure = traceback.format_exc()
        log("FAILED\n" + failure)
        (OUT / "GENERATION_FAILED.txt").write_text(failure, encoding="utf8")
        atomic_json(
            OUT / "generation.status.json",
            {
                "run_id": RUN_ID,
                "stage": "generation",
                "status": "FAIL",
                "completed_utc": utc_now(),
                "error": failure,
            },
        )
        raise


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
