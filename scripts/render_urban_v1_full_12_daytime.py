#!/usr/bin/env python3
"""Define and directly render the complete full-12 city in daylight.

The same camera/visibility definitions are also consumed by the resource-safe
per-pixel Z renderer. No city zone, placement, interior collection, or
cross-region shadow receiver is omitted from a delivered view.
An auxiliary transparent top mask (not a delivery view) temporarily excludes
only the common ground and roads to measure actual rasterized mesh coverage.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import sys
import time
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY_ROOT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND_PATH = CITY_ROOT / f"{REVISION}.blend"
LAYOUT_PATH = CITY_ROOT / "layout_plan.json"
OUT = CITY_ROOT / "renders"
MANIFEST = OUT / "render_manifest.json"
PANORAMA_AUDIT = CITY_ROOT / "panorama_audit.json"
PROJECTION_AUDIT = CITY_ROOT / "mesh_projection_audit.json"
AUDIT_DIR = OUT / "audit"
TEMP_PREFIX = "__full12_daytime_tmp__"


def parse_resolution() -> tuple[int, int]:
    raw = os.environ.get("C2W_FULL12_RENDER_RESOLUTION", "1920x1080")
    match = re.fullmatch(r"\s*(\d+)\s*[xX,]\s*(\d+)\s*", raw)
    if not match:
        raise RuntimeError("C2W_FULL12_RENDER_RESOLUTION must look like 1920x1080")
    width, height = map(int, match.groups())
    if width < 1920 or height < 1080:
        raise RuntimeError("Full-12 final delivery renders must be at least 1920x1080")
    return width, height


RESOLUTION = parse_resolution()


@dataclass(frozen=True)
class Shot:
    name: str
    filename: str
    kind: str
    placement_ids: tuple[str, ...] = ()
    direction: tuple[float, float, float] = (0.65, -1.0, 0.45)
    lens: float = 52.0
    margin: float = 1.12
    projection: str = "PERSP"
    anchor_id: str | None = None
    source_camera: tuple[float, float, float] | None = None
    source_target: tuple[float, float, float] | None = None
    world_camera: tuple[float, float, float] | None = None
    world_target: tuple[float, float, float] | None = None
    interior: bool = False
    description: str = ""


SHOTS: list[Shot] = []


def fit(
    number: int,
    name: str,
    kind: str,
    ids: Sequence[str] = (),
    direction: tuple[float, float, float] = (0.65, -1.0, 0.45),
    lens: float = 52.0,
    margin: float = 1.12,
    projection: str = "PERSP",
    description: str = "",
) -> None:
    SHOTS.append(
        Shot(
            name,
            f"{number:02d}_{name}.png",
            kind,
            tuple(ids),
            direction,
            lens,
            margin,
            projection,
            description=description,
        )
    )


def local(
    number: int,
    name: str,
    kind: str,
    anchor: str,
    camera: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
    *,
    interior: bool = False,
    description: str = "",
) -> None:
    SHOTS.append(
        Shot(
            name,
            f"{number:02d}_{name}.png",
            kind,
            (anchor,),
            lens=lens,
            anchor_id=anchor,
            source_camera=camera,
            source_target=target,
            interior=interior,
            description=description,
        )
    )


def world(
    number: int,
    name: str,
    kind: str,
    camera: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
    ids: Sequence[str] = (),
    description: str = "",
) -> None:
    SHOTS.append(
        Shot(
            name,
            f"{number:02d}_{name}.png",
            kind,
            tuple(ids),
            lens=lens,
            world_camera=camera,
            world_target=target,
            description=description,
        )
    )


# Six city panoramas. The corrected fit uses projected frustum extents, so the
# city occupies the frame instead of becoming a tiny model surrounded by sky.
fit(
    1,
    "city_southwest_panorama",
    "city",
    direction=(-1.0, -1.0, 0.72),
    lens=52,
    margin=1.06,
)
fit(
    2,
    "city_southeast_panorama",
    "city",
    direction=(1.0, -1.0, 0.72),
    lens=52,
    margin=1.06,
)
fit(
    3,
    "city_northwest_panorama",
    "city",
    direction=(-1.0, 1.0, 0.72),
    lens=52,
    margin=1.06,
)
fit(
    4,
    "city_northeast_panorama",
    "city",
    direction=(1.0, 1.0, 0.72),
    lens=52,
    margin=1.06,
)
fit(
    5,
    "city_high_aerial_panorama",
    "city",
    direction=(0.28, -0.42, 1.0),
    lens=55,
    margin=1.05,
)
fit(
    6,
    "city_top_down_coverage",
    "city",
    direction=(0.001, -0.001, 1.0),
    margin=1.025,
    projection="ORTHO",
)


ZONE_IDS = {
    "residential": (
        "residential_01_river3_indoor",
        "residential_02_river3_north_extension",
        "residential_03_all45_09_native_indoor",
        "residential_delivery_01_food_delivery_locker",
        "residential_delivery_02_parcel_locker",
        "residential_delivery_03_delivery_station",
    ),
    "commercial": (
        "commercial_all43_25_complete",
        "pharmacy_cvs_west",
        "pharmacy_well_east",
        "commercial_atm_five_machine_row",
        "bank_low_01_classical",
        "bank_low_02_white",
        "bank_low_03_bronze",
        "bank_hq_blue_glass",
    ),
    "park": (
        "park_original_sculpture_nature",
        "park_river5_corridor",
        "park_fitness_area",
        "park_single_fountain",
    ),
    "leisure": ("leisure_all44_14_complete", "leisure_fitness_area"),
    "education": ("education_school_north", "education_library_south"),
    "civic": (
        "civic_fire_precinct_north",
        "police_opposite_fire_west",
        "police_opposite_fire_east",
        "police_near_library",
    ),
    "health": ("hospital_central_red_white", "hospital_outskirts_traditional"),
    "industrial": (
        "gas_east_north",
        "gas_east_south",
        "gas_west_outskirts",
        "factory_01_gable",
        "factory_02_white",
        "factory_03_gated",
        "factory_04_highbay",
    ),
    "roads": (
        "compact_road_intersection_0_m54p5",
        "compact_residential_ew_02",
        "compact_east_spine_02",
        "road_diagonal_greenway_connector",
    ),
}
ZONE_NEAR = {
    "residential": "residential_01_river3_indoor",
    "commercial": "commercial_all43_25_complete",
    "park": "park_original_sculpture_nature",
    "leisure": "leisure_all44_14_complete",
    "education": "education_library_south",
    "civic": "civic_fire_precinct_north",
    "health": "hospital_central_red_white",
    "industrial": "factory_03_gated",
    "roads": "compact_road_intersection_0_m54p5",
}
ZONE_DIRECTIONS = {
    "residential": (0.8, -1.0, 0.62),
    "commercial": (-0.7, -1.0, 0.55),
    "park": (-0.7, -1.0, 0.62),
    "leisure": (0.7, -1.0, 0.58),
    "education": (-0.65, -1.0, 0.62),
    "civic": (-0.8, -1.0, 0.55),
    "health": (0.8, -1.0, 0.55),
    "industrial": (-0.75, -1.0, 0.52),
    "roads": (0.9, -1.0, 0.34),
}
number = 10
for zone in ZONE_IDS:
    fit(
        number,
        f"{zone}_far",
        "zone_far",
        ZONE_IDS[zone],
        ZONE_DIRECTIONS[zone],
        54,
        1.10,
    )
    if zone == "residential":
        # The southeast fit used by full-11/full-12 initially put the camera
        # inside the bank headquarters and returned only curtain wall.  This
        # explicit east-side approach stays in the open street corridor and
        # looks across the complete first residential neighbourhood.
        local(
            number + 1,
            "residential_near",
            "zone_near",
            "residential_01_river3_indoor",
            (34.0, 32.5, 16.0),
            (-31.4, 32.5, 5.0),
            48,
            description="Unobstructed east-side residential neighbourhood view",
        )
    elif zone == "park":
        # Reuse the source-authored reference-match pose.  A bounds fit sees
        # the corridor's long, mostly flat extent and makes the actual park
        # disappear behind foreground roofs and pavement.
        local(
            number + 1,
            "park_near",
            "zone_near",
            "park_original_sculpture_nature",
            (66.0, -4.0, 34.0),
            (32.0, 31.0, 2.2),
            50,
            description="Source-authored landscaped park overview with paths, mature trees, seating, and sculpture",
        )
    else:
        fit(
            number + 1,
            f"{zone}_near",
            "zone_near",
            (ZONE_NEAR[zone],),
            ZONE_DIRECTIONS[zone],
            58,
            1.04,
        )
    number += 2


# Facility relationship, individual entrance, and equipment verification views.
fit(
    30,
    "school_far",
    "feature_far",
    ("education_school_north",),
    (0.7, -1.0, 0.65),
    54,
    1.10,
)
local(
    31,
    "school_main_gate_near",
    "feature_near",
    "education_school_north",
    (28, -132, 16),
    (28, -70, 3.2),
    48,
)
fit(
    32,
    "library_far",
    "feature_far",
    ("education_library_south",),
    (-0.7, -1.0, 0.58),
    54,
    1.10,
)
local(
    33,
    "library_modern_entrance_near",
    "feature_near",
    "education_library_south",
    (-49, -43, 5.2),
    (-38, -8.5, 4.6),
    52,
)
world(
    34,
    "school_library_shared_street",
    "relationship",
    (-109, 76, 9.5),
    (-109, 240, 4.5),
    44,
    ("education_school_north", "education_library_south"),
    "Street-level view along the shared north-south road with both facing entrances visible",
)
fit(
    35,
    "bank_commercial_far",
    "feature_far",
    (
        "commercial_all43_25_complete",
        "bank_low_01_classical",
        "bank_low_02_white",
        "bank_low_03_bronze",
        "bank_hq_blue_glass",
    ),
    (0.75, -1, 0.65),
    54,
    1.08,
)
local(
    36,
    "bank_low_row_entrance_near",
    "feature_near",
    "bank_low_01_classical",
    (-60.0, -3.0, 10.0),
    (-25.6, 21.1, 4.2),
    45,
    description="Pulled-back oblique of the carved corner entrance and low-bank frontage",
)
local(
    37,
    "bank_headquarters_near",
    "feature_near",
    "bank_hq_blue_glass",
    (48.0, 45.0, 16.0),
    (0.0, 69.0, 7.0),
    40,
    description="Source-authored headquarters podium street view, including the complete entrance",
)
fit(
    38,
    "hospital_central_far",
    "feature_far",
    ("hospital_central_red_white",),
    (0.75, -1, 0.55),
    54,
    1.10,
)
local(
    39,
    "hospital_central_emergency_near",
    "feature_near",
    "hospital_central_red_white",
    (37, -43, 8.5),
    (21, -11.5, 3.3),
    54,
)
fit(
    40,
    "hospital_outskirts_far",
    "feature_far",
    ("hospital_outskirts_traditional",),
    (0.8, -1, 0.58),
    54,
    1.12,
)
local(
    41,
    "hospital_outskirts_atrium_near",
    "feature_near",
    "hospital_outskirts_traditional",
    (-87, -38, 6.2),
    (-78, -5.8, 4.6),
    54,
)
fit(
    42,
    "gas_pair_far",
    "relationship",
    ("gas_east_north", "gas_east_south"),
    (0.85, -1, 0.52),
    52,
    1.14,
)
fit(
    43, "gas_north_near", "feature_near", ("gas_east_north",), (0.8, -1, 0.35), 58, 1.05
)
fit(
    44, "gas_south_near", "feature_near", ("gas_east_south",), (-0.8, 1, 0.35), 58, 1.05
)
fit(
    45,
    "gas_west_far",
    "feature_far",
    ("gas_west_outskirts",),
    (-0.75, -1, 0.55),
    54,
    1.12,
)
fit(
    46,
    "gas_west_near",
    "feature_near",
    ("gas_west_outskirts",),
    (-1, -0.25, 0.34),
    58,
    1.05,
)
fit(
    47,
    "factory_group_far",
    "feature_far",
    ("factory_01_gable", "factory_02_white", "factory_03_gated", "factory_04_highbay"),
    (-0.7, -1, 0.55),
    52,
    1.12,
)
for n, pid in enumerate(
    ("factory_01_gable", "factory_02_white", "factory_03_gated", "factory_04_highbay"),
    48,
):
    fit(n, f"{pid}_near", "feature_near", (pid,), (0.45, -1, 0.32), 58, 1.05)
fit(
    52,
    "fire_police_far",
    "relationship",
    (
        "civic_fire_precinct_north",
        "police_opposite_fire_west",
        "police_opposite_fire_east",
    ),
    (-0.8, -1, 0.55),
    52,
    1.12,
)
fit(
    53,
    "fire_station_near",
    "feature_near",
    ("civic_fire_precinct_north",),
    (0.1, -1, 0.30),
    58,
    1.04,
)
fit(
    54,
    "police_west_near",
    "feature_near",
    ("police_opposite_fire_west",),
    (-0.2, 1, 0.28),
    58,
    1.04,
)
fit(
    55,
    "police_east_near",
    "feature_near",
    ("police_opposite_fire_east",),
    (0.2, 1, 0.28),
    58,
    1.04,
)
local(
    56,
    "police_library_near",
    "feature_near",
    "police_near_library",
    (90.0, -44.0, 5.2),
    (62.0, -10.0, 4.8),
    45,
    description="Front oblique from the clear street gap north of the library roof",
)
fit(
    57,
    "artificial_lake_high",
    "feature_far",
    ("education_artificial_lake_civic_enclosure",),
    (0.65, -1, 0.92),
    52,
    1.08,
)
local(
    58,
    "artificial_lake_pavilion_near",
    "feature_near",
    "education_artificial_lake_civic_enclosure",
    (-36.0, 5.0, 6.8),
    (-18.0, 27.0, 2.55),
    50,
    description="Source-authored close view of the western Victorian lakeside pavilion",
)
local(
    59,
    "artificial_lake_shore_near",
    "feature_near",
    "education_artificial_lake_civic_enclosure",
    (-35.0, -8.0, 2.55),
    (-24.2, 0.8, 0.18),
    66,
    description="Source-authored ground-level shore and water view, clear of the bank row",
)
local(
    60,
    "park_sculpture_near",
    "feature_near",
    "park_original_sculpture_nature",
    (30.0, 14.0, 4.2),
    (30.0, 30.0, 1.8),
    50,
    description=(
        "Dedicated south-plaza close-up centered on the exact linked knot sculpture; "
        "the wider park/river relationship remains visible in the park far view"
    ),
)
fit(
    61,
    "park_fountain_near",
    "feature_near",
    ("park_single_fountain",),
    (0.5, -1, 0.28),
    62,
    1.05,
)
local(
    62,
    "park_fitness_near",
    "feature_near",
    "park_fitness_area",
    (0.0, -31.0, 8.0),
    (0.0, 0.0, 0.88),
    38,
    description="Source-authored wide front view in which every articulated fitness machine is legible",
)
fit(
    63,
    "leisure_facilities_relational",
    "relationship",
    ("leisure_all44_14_complete", "leisure_fitness_area"),
    (0.75, -1, 0.70),
    52,
    1.08,
)
fit(
    64,
    "leisure_courts_near",
    "feature_near",
    ("leisure_all44_14_complete",),
    (-0.55, -1, 0.30),
    58,
    0.94,
)
local(
    65,
    "leisure_fitness_near",
    "feature_near",
    "leisure_fitness_area",
    (0.0, -31.0, 8.0),
    (0.0, 0.0, 0.88),
    38,
    description="Source-authored wide front view in which every articulated fitness machine is legible",
)
local(
    66,
    "residential_01_river3_indoor_near",
    "feature_near",
    "residential_01_river3_indoor",
    (34.0, 32.5, 16.0),
    (-31.4, 32.5, 5.0),
    48,
    description="Clear east-side view of the first connected residential area",
)
local(
    67,
    "residential_02_river3_north_extension_near",
    "feature_near",
    "residential_02_river3_north_extension",
    (-55.0, 65.2, 2.0),
    (34.0, 87.0, 4.0),
    56,
    description="Source-authored street-level view along the second residential area's connected road",
)
fit(
    68,
    "residential_03_all45_09_native_indoor_near",
    "feature_near",
    ("residential_03_all45_09_native_indoor",),
    (0.55, -1, 0.34),
    58,
    1.04,
)
local(
    69,
    "residential_delivery_01_food_delivery_locker_near",
    "feature_near",
    "residential_delivery_01_food_delivery_locker",
    (-12.8, 13.65, 3.55),
    (-12.8, -0.05, 1.52),
    64,
    description="Source-authored front view of the numbered food-delivery locker",
)
local(
    70,
    "residential_delivery_02_parcel_locker_near",
    "feature_near",
    "residential_delivery_02_parcel_locker",
    (-3.2, 10.5, 3.55),
    (-3.2, -0.10, 1.48),
    50,
    description="Source-authored front view of the full Fengchao-style parcel locker",
)
local(
    71,
    "residential_delivery_03_delivery_station_near",
    "feature_near",
    "residential_delivery_03_delivery_station",
    (36.0, 2.7, 5.2),
    (11.6, -3.5, 1.8),
    48,
    description="Clear south-east oblique across the modeled fascia, glazed entrance, service counter, racks, and parcel inventory; the sightline passes south of the adjacent residential footprint",
)
local(
    72,
    "commercial_streetfront_near",
    "feature_near",
    "commercial_all43_25_complete",
    (-30, 14, 7.5),
    (-30, -14, 2.8),
    48,
)
fit(
    73,
    "pharmacy_cvs_near",
    "feature_near",
    ("pharmacy_cvs_west",),
    (0.25, -1, 0.24),
    60,
    1.04,
)
fit(
    74,
    "pharmacy_well_near",
    "feature_near",
    ("pharmacy_well_east",),
    (-0.25, 1, 0.24),
    60,
    1.04,
)
fit(
    75,
    "atm_row_front",
    "feature_near",
    ("commercial_atm_five_machine_row",),
    (0.05, -1, 0.18),
    65,
    1.08,
)
world(
    76,
    "road_intersection_street_level",
    "road_near",
    (-44, -96, 4.2),
    (0, -54.5, 1.0),
    46,
    ("compact_road_intersection_0_m54p5",),
)
world(
    77,
    "crosswalk_oblique",
    "road_near",
    (-51, -102, 21),
    (0, -54.5, 0.2),
    52,
    ("compact_road_intersection_0_m54p5",),
)
world(
    78,
    "diagonal_road_near",
    "road_near",
    (397.0, 179.45, 30.0),
    (342.95, 179.45, 0.5),
    42,
    ("road_diagonal_greenway_connector",),
    description="World-axis oblique makes the 45-degree greenway connector visibly diagonal while retaining its carriageway, markings, sidewalks, lamps, and urban context",
)
fit(79, "continuous_road_far", "road_far", ZONE_IDS["roads"], (0.9, -1, 0.75), 52, 1.14)


# Representative connected-interior/threshold views. No exterior or other zone
# is hidden; source-authored camera coordinates are transformed with each real
# city placement.
local(
    80,
    "interior_residential_native",
    "interior",
    "residential_03_all45_09_native_indoor",
    (-34.62748, -22.68998, 2.4766),
    (-39.57046, -23.39355, 1.5473),
    17,
    interior=True,
    description="Exact native townhouse camera after applying its nested source-instance transform and native 93.7-degree field of view",
)
local(
    81,
    "interior_commercial_bar",
    "interior",
    "commercial_all43_25_complete",
    (-54.0, -10.8, 2.1),
    (-54.0, -17.0, 2.0),
    58,
    interior=True,
)
local(
    82,
    "interior_school_cafeteria_threshold",
    "interior",
    "education_school_north",
    (72.0, -61.0, 7.5),
    (72.0, -31.9, 4.1),
    28,
    interior=True,
    description="Honest connected cafeteria threshold view from inside the athletic fence, showing the complete authored curtain wall, deep canopy, structural columns, entrance apron, and roof line; the source contains an occupied shell rather than fabricated dining furniture",
)
local(
    83,
    "interior_library_reading_room",
    "interior",
    "education_library_south",
    (-38.0, -6.0, 2.1),
    (-38.0, 7.0, 2.1),
    58,
    interior=True,
)
local(
    84,
    "interior_bank_atrium",
    "interior",
    "bank_low_03_bronze",
    (7.0, -46.0, 3.0),
    (0.0, -39.0, 3.0),
    30,
    interior=True,
    description="Source-faithful connected bronze-bank threshold showing the fabricated double-door system, canopy, monumental three-storey frame, rail, and adjacent deep facade bays; no cutaway is fabricated through the source's occupied shell",
)
local(
    85,
    "interior_hospital_lobby",
    "interior",
    "hospital_central_red_white",
    (-14.0, 1.0, 6.3),
    (-14.0, -4.2, 6.15),
    36,
    interior=True,
    description="Representative occupied public-hospital clinical interior after accounting for its authored +8 m root, tightly framing one complete patient-room bed, linen, monitor, IV, frame, and caster assembly between the modeled floor plates; the stable legacy filename is retained for delivery compatibility",
)


SHOT_BY_NAME = {shot.name: shot for shot in SHOTS}
if len(SHOT_BY_NAME) != len(SHOTS):
    raise RuntimeError("Duplicate full-12 shot name")


CAMERA_COMPOSITION_REVISION = "full12_authored_asset_framing_v2"


def shot_spec_sha256(shot: Shot) -> str:
    """Stable fingerprint used by every renderer/resume gate.

    Camera changes must invalidate only the affected view, while unchanged
    native layer bundles remain reusable.  Tuples serialize as JSON arrays so
    this also compares cleanly with records read back from a manifest.
    """

    payload = json.dumps(
        asdict(shot), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf8")
    return hashlib.sha256(payload).hexdigest()


def shot_record_matches_spec(record: dict[str, Any], shot: Shot) -> bool:
    expected = asdict(shot)
    recorded = {key: record.get(key) for key in expected}
    normalize = lambda value: json.dumps(  # noqa: E731 - compact local normalizer
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return normalize(recorded) == normalize(expected)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def select_shots(tokens: Sequence[str]) -> list[Shot]:
    requested = [
        piece.strip().lower()
        for token in tokens
        for piece in token.split(",")
        if piece.strip()
    ]
    if not requested or any(piece in {"all", "*"} for piece in requested):
        return list(SHOTS)
    if any(piece in {"list", "--list"} for piece in requested):
        for shot in SHOTS:
            print(f"{shot.name:45s} {shot.filename}")
        return []
    groups: dict[str, list[str]] = {
        "city": [shot.name for shot in SHOTS if shot.kind == "city"],
        "panoramas": [shot.name for shot in SHOTS if shot.kind == "city"],
        "regions": [shot.name for shot in SHOTS if shot.kind.startswith("zone_")],
        "near": [
            shot.name
            for shot in SHOTS
            if shot.kind.endswith("near") or shot.kind == "road_near"
        ],
        "far": [
            shot.name
            for shot in SHOTS
            if shot.kind.endswith("far") or shot.kind == "road_far"
        ],
        "interiors": [shot.name for shot in SHOTS if shot.interior],
        "roads": [shot.name for shot in SHOTS if shot.kind.startswith("road")],
    }
    for zone in ZONE_IDS:
        groups[zone] = [shot.name for shot in SHOTS if shot.name.startswith(zone + "_")]
    for shot in SHOTS:
        groups[shot.name] = [shot.name]
        groups[shot.filename.lower()] = [shot.name]
        groups[Path(shot.filename).stem.lower()] = [shot.name]
    names = []
    unknown = []
    for item in requested:
        if item not in groups:
            unknown.append(item)
            continue
        for name in groups[item]:
            if name not in names:
                names.append(name)
    if unknown:
        raise RuntimeError(f"Unknown full-12 render request: {unknown}")
    return [SHOT_BY_NAME[name] for name in names]


def footprint_bounds(record: dict[str, Any]) -> tuple[Vector, Vector]:
    footprint = record["footprint"]
    return Vector(footprint["min"]), Vector(footprint["max"])


def union_bounds(
    values: Iterable[tuple[Vector, Vector]]
) -> tuple[Vector, Vector] | None:
    items = list(values)
    if not items:
        return None
    return (
        Vector(tuple(min(item[0][axis] for item in items) for axis in range(3))),
        Vector(tuple(max(item[1][axis] for item in items) for axis in range(3))),
    )


def resolve_bounds(
    shot: Shot, layout: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> tuple[Vector, Vector]:
    if shot.kind == "city":
        return Vector(layout["city_bounds"]["min"]), Vector(
            layout["city_bounds"]["max"]
        )
    missing = [
        placement_id for placement_id in shot.placement_ids if placement_id not in by_id
    ]
    if missing:
        raise RuntimeError(f"Missing placement(s) for {shot.name}: {missing}")
    bounds = union_bounds(footprint_bounds(by_id[item]) for item in shot.placement_ids)
    if bounds is None:
        raise RuntimeError(f"No bounds for {shot.name}")
    return bounds


def bounds_corners(bounds: tuple[Vector, Vector]) -> list[Vector]:
    lower, upper = bounds
    return [
        Vector((x, y, z))
        for x in (lower.x, upper.x)
        for y in (lower.y, upper.y)
        for z in (lower.z, upper.z)
    ]


def fit_camera(
    camera: bpy.types.Object,
    bounds: tuple[Vector, Vector],
    shot: Shot,
    resolution: tuple[int, int] = RESOLUTION,
) -> dict[str, Any]:
    lower, upper = bounds
    span = upper - lower
    target = Vector(
        ((lower.x + upper.x) * 0.5, (lower.y + upper.y) * 0.5, lower.z + span.z * 0.38)
    )
    direction = Vector(shot.direction).normalized()
    view_direction = -direction
    rotation = view_direction.to_track_quat("-Z", "Y")
    right = rotation @ Vector((1.0, 0.0, 0.0))
    up = rotation @ Vector((0.0, 1.0, 0.0))
    aspect = resolution[0] / resolution[1]
    camera.data.type = shot.projection
    camera.data.lens = shot.lens
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0
    camera.data.clip_start = 0.10
    camera.data.clip_end = 8000.0
    corners = bounds_corners(bounds)
    if shot.projection == "ORTHO":
        horizontal = max(abs((corner - target).dot(right)) for corner in corners) * 2.0
        vertical = max(abs((corner - target).dot(up)) for corner in corners) * 2.0
        camera.data.ortho_scale = max(vertical, horizontal / aspect) * shot.margin
        distance = max(span.x, span.y, span.z, 1.0) * 1.7
    else:
        horizontal_fov = 2.0 * math.atan(36.0 / (2.0 * shot.lens))
        vertical_fov = 2.0 * math.atan(math.tan(horizontal_fov / 2.0) / aspect)
        tan_h = math.tan(horizontal_fov / 2.0)
        tan_v = math.tan(vertical_fov / 2.0)
        required = []
        for corner in corners:
            relative = corner - target
            required.append(relative.dot(direction) + abs(relative.dot(right)) / tan_h)
            required.append(relative.dot(direction) + abs(relative.dot(up)) / tan_v)
        distance = max(required) * shot.margin + 0.5
    location = target + direction * max(distance, 1.0)
    # ``camera`` belongs to a temporary non-active render Scene in the
    # resource-partition pipeline.  Component assignment can leave
    # ``matrix_world`` stale in background mode, making otherwise identical
    # layer packs rasterize from different poses.  Set the complete pose
    # matrix explicitly so every exact layer shares one evaluated camera.
    camera.matrix_world = Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
    return {
        "mode": "projected_bounds_fit",
        "projection": shot.projection,
        "location": [round(float(value), 4) for value in location],
        "target": [round(float(value), 4) for value in target],
        "lens_mm": shot.lens,
        "ortho_scale": round(float(camera.data.ortho_scale), 4)
        if shot.projection == "ORTHO"
        else None,
    }


def transform_source_point(record: dict[str, Any], point: Sequence[float]) -> Vector:
    center = record["source_center"]
    location = record["location"]
    yaw = float(record.get("yaw_radians", 0.0))
    x = float(point[0]) - float(center[0])
    y = float(point[1]) - float(center[1])
    c, s = math.cos(yaw), math.sin(yaw)
    return Vector(
        (
            float(location[0]) + c * x - s * y,
            float(location[1]) + s * x + c * y,
            float(location[2]) + float(point[2]),
        )
    )


def configure_camera(
    camera: bpy.types.Object,
    shot: Shot,
    bounds: tuple[Vector, Vector],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    camera.data.type = "PERSP"
    camera.data.lens = shot.lens
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0
    camera.data.clip_start = 0.08 if shot.interior else 0.10
    camera.data.clip_end = 8000.0
    if shot.source_camera is not None and shot.source_target is not None:
        record = by_id[str(shot.anchor_id)]
        location = transform_source_point(record, shot.source_camera)
        target = transform_source_point(record, shot.source_target)
        mode = "source_coordinate_entrance_or_interior"
    elif shot.world_camera is not None and shot.world_target is not None:
        location = Vector(shot.world_camera)
        target = Vector(shot.world_target)
        mode = "explicit_world_relationship"
    else:
        return fit_camera(camera, bounds, shot)
    rotation = (target - location).to_track_quat("-Z", "Y")
    camera.matrix_world = Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
    return {
        "mode": mode,
        "projection": "PERSP",
        "location": [round(float(value), 4) for value in location],
        "target": [round(float(value), 4) for value in target],
        "lens_mm": shot.lens,
        "ortho_scale": None,
    }


def validate_camera_pose(
    camera: bpy.types.Object, camera_record: dict[str, Any]
) -> dict[str, Any]:
    """Prove the evaluated render camera matches its serialized shot pose."""

    expected_location = Vector(camera_record["location"])
    target = Vector(camera_record["target"])
    actual_location = camera.matrix_world.translation.copy()
    expected_forward = (target - expected_location).normalized()
    actual_forward = (
        camera.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    ).normalized()
    location_error = float((actual_location - expected_location).length)
    forward_dot = float(actual_forward.dot(expected_forward))
    projection_matches = camera.data.type == camera_record["projection"]
    passed = location_error <= 1.0e-3 and forward_dot >= 0.999999 and projection_matches
    result = {
        "pass": passed,
        "matrix_world_explicit": True,
        "location_error_m": round(location_error, 9),
        "forward_dot": round(forward_dot, 9),
        "projection_matches": projection_matches,
    }
    if not passed:
        raise RuntimeError(f"Render camera matrix validation failed: {result}")
    return result


def force_all_regions_visible() -> (
    tuple[list[tuple[bpy.types.Collection, bool, bool]], list[str]]
):
    saved = []
    zones = []
    for collection in bpy.data.collections:
        if not collection.name.startswith("full10:zone:"):
            continue
        saved.append(
            (collection, bool(collection.hide_viewport), bool(collection.hide_render))
        )
        collection.hide_viewport = False
        collection.hide_render = False
        zones.append(collection.name.rsplit(":", 1)[-1])
    return saved, sorted(zones)


def restore_collection_visibility(
    saved: Iterable[tuple[bpy.types.Collection, bool, bool]],
) -> None:
    for collection, hide_viewport, hide_render in saved:
        try:
            collection.hide_viewport = hide_viewport
            collection.hide_render = hide_render
        except ReferenceError:
            continue


def synchronize_workbench_material_colors(
    scene: bpy.types.Scene,
) -> dict[str, Any]:
    """Expose authored Principled colors to Workbench without editing assets.

    Many exact reference materials intentionally leave Blender's legacy
    ``diffuse_color`` at its grey default and store their real color only in
    the Principled BSDF node.  Eevee evaluates that graph correctly, but on
    this city its shadow atlas overflows (thousands of pages) and can abort
    after a multi-minute panorama.  Workbench's MATERIAL mode reads only the
    legacy viewport field.  For the transient render process, copy the
    existing Principled constants into that viewport field.  No node, image,
    mesh, source Blend, or production Blend is changed or saved.
    """

    if scene.render.engine != "BLENDER_WORKBENCH":
        return {
            "enabled": False,
            "method": "not applicable outside Workbench",
            "materials_examined": len(bpy.data.materials),
            "principled_materials": 0,
            "viewport_colors_changed": 0,
            "write_failures": 0,
            "node_graphs_changed": False,
            "source_files_saved": False,
            "production_blend_saved": False,
        }

    examined = len(bpy.data.materials)
    principled = 0
    changed = 0
    failures = 0
    linked_base_color_inputs = 0
    for material in bpy.data.materials:
        if not material.use_nodes or material.node_tree is None:
            continue
        candidates = [
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeBsdfPrincipled"
            and node.inputs.get("Base Color") is not None
        ]
        if not candidates:
            continue
        principled += 1
        bsdf = candidates[0]
        base_socket = bsdf.inputs["Base Color"]
        if base_socket.is_linked:
            linked_base_color_inputs += 1
        color = tuple(float(value) for value in base_socket.default_value)
        if len(color) == 3:
            color = (*color, 1.0)
        color = tuple(max(0.0, min(1.0, value)) for value in color[:4])
        before = tuple(float(value) for value in material.diffuse_color)
        try:
            material.diffuse_color = color
            metallic = bsdf.inputs.get("Metallic")
            roughness = bsdf.inputs.get("Roughness")
            if metallic is not None and not metallic.is_linked:
                material.metallic = max(0.0, min(1.0, float(metallic.default_value)))
            if roughness is not None and not roughness.is_linked:
                material.roughness = max(0.0, min(1.0, float(roughness.default_value)))
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            failures += 1
            continue
        if any(abs(before[index] - color[index]) > 1e-5 for index in range(4)):
            changed += 1

    return {
        "enabled": True,
        "method": (
            "transient copy of existing Principled BSDF Base Color, Metallic, "
            "and Roughness constants to Workbench viewport fields"
        ),
        "materials_examined": examined,
        "principled_materials": principled,
        "linked_base_color_inputs_retained_as_authored_default": (
            linked_base_color_inputs
        ),
        "viewport_colors_changed": changed,
        "write_failures": failures,
        "node_graphs_changed": False,
        "source_files_saved": False,
        "production_blend_saved": False,
    }


def configure_daylight(scene: bpy.types.Scene) -> tuple[dict[str, Any], dict[str, Any]]:
    requested = os.environ.get("C2W_FULL12_RENDER_ENGINE", "WORKBENCH").strip().upper()
    if requested in {"EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        # Blender 4.x used BLENDER_EEVEE_NEXT while Blender 5.1 exposes the
        # production engine again as BLENDER_EEVEE.
        try:
            scene.render.engine = "BLENDER_EEVEE"
        except TypeError:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif requested in {"CYCLES", "OPTIX"}:
        scene.render.engine = "CYCLES"
    elif requested in {"WORKBENCH", "BLENDER_WORKBENCH"}:
        scene.render.engine = "BLENDER_WORKBENCH"
    else:
        raise RuntimeError(
            "C2W_FULL12_RENDER_ENGINE must be EEVEE, CYCLES, or WORKBENCH"
        )
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 22
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    # Do not simplify authored meshes or subdivision for the final delivery.
    scene.render.use_simplify = False
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.35

    previous_world = scene.world
    world_data = bpy.data.worlds.new(f"{TEMP_PREFIX}:world")
    world_data.use_nodes = True
    background = world_data.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.34, 0.59, 0.86, 1.0)
        background.inputs["Strength"].default_value = 0.62
    scene.world = world_data

    sun_data = bpy.data.lights.new(f"{TEMP_PREFIX}:sun_data", type="SUN")
    sun_data.energy = 2.6
    sun_data.angle = math.radians(4.0)
    sun = bpy.data.objects.new(f"{TEMP_PREFIX}:sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(29.0), math.radians(-18.0), math.radians(-42.0))

    fill_data = bpy.data.lights.new(f"{TEMP_PREFIX}:interior_fill_data", type="AREA")
    fill_data.energy = 0.0
    fill_data.shape = "DISK"
    fill_data.size = 4.0
    fill = bpy.data.objects.new(f"{TEMP_PREFIX}:interior_fill", fill_data)
    scene.collection.objects.link(fill)

    device_records = []
    samples = None
    denoising = False
    eevee_shadow_quality = None
    if scene.render.engine == "CYCLES":
        samples = max(16, int(os.environ.get("C2W_FULL12_RENDER_SAMPLES", "32")))
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.04
        scene.cycles.max_bounces = 6
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 3
        scene.cycles.transmission_bounces = 4
        denoising = True
        addon = bpy.context.preferences.addons.get("cycles")
        if addon is not None:
            preferences = addon.preferences
            for compute_type in ("OPTIX", "CUDA"):
                try:
                    preferences.compute_device_type = compute_type
                    preferences.get_devices()
                    enabled = []
                    for device in preferences.devices:
                        device.use = device.type == compute_type
                        if device.use:
                            enabled.append({"name": device.name, "type": device.type})
                    if enabled:
                        scene.cycles.device = "GPU"
                        device_records = enabled
                        break
                except (TypeError, ValueError, RuntimeError):
                    continue
        if not device_records:
            scene.cycles.device = "CPU"
            device_records = [{"name": "CPU fallback", "type": "CPU"}]
    elif scene.render.engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        # Blender 5's Eevee performs temporal sampling internally. Record the
        # requested quality budget even when the property name varies by build.
        samples = max(32, int(os.environ.get("C2W_FULL12_EEVEE_SAMPLES", "64")))
        for owner_name, property_name in (
            ("eevee", "taa_render_samples"),
            ("eevee", "taa_samples"),
        ):
            owner = getattr(scene, owner_name, None)
            if owner is not None and hasattr(owner, property_name):
                setattr(owner, property_name, samples)
        # The exact river/lake packs can expose several thousand simultaneous
        # virtual-shadow pages.  Blender's 512 MB default pool reports a full
        # buffer for those assets and silently drops shadows.  Use the largest
        # supported pool and a bounded resolution scale that keeps every page
        # resident at native 1920x1080 delivery resolution.  This changes only
        # the transient render Scene; no production or source Blend is saved.
        eevee = getattr(scene, "eevee", None)
        if eevee is None or not all(
            hasattr(eevee, name)
            for name in ("shadow_pool_size", "shadow_resolution_scale")
        ):
            raise RuntimeError(
                "This Blender build lacks the Eevee shadow-pool controls "
                "required for full-12 fallback quality"
            )
        shadow_pool_mb = int(os.environ.get("C2W_FULL12_EEVEE_SHADOW_POOL_MB", "1024"))
        if shadow_pool_mb != 1024:
            raise RuntimeError(
                "C2W_FULL12_EEVEE_SHADOW_POOL_MB must remain 1024 for the "
                "validated full-12 fallback"
            )
        shadow_resolution_scale = float(
            os.environ.get("C2W_FULL12_EEVEE_SHADOW_RESOLUTION_SCALE", "0.5")
        )
        if abs(shadow_resolution_scale - 0.5) > 1e-9:
            raise RuntimeError(
                "C2W_FULL12_EEVEE_SHADOW_RESOLUTION_SCALE must remain 0.5 "
                "for the validated full-12 fallback"
            )
        eevee.shadow_pool_size = str(shadow_pool_mb)
        eevee.shadow_resolution_scale = shadow_resolution_scale
        eevee_shadow_quality = {
            "policy": "full12_complete_virtual_shadow_residency_v1",
            "pool_size_mb": int(eevee.shadow_pool_size),
            "resolution_scale": float(eevee.shadow_resolution_scale),
            "missing_shadow_pages_allowed": False,
        }
    else:
        shading = scene.display.shading
        shading.light = "STUDIO"
        # High Workbench render AA plus the outdoor studio rig gives the
        # resource-safe depth partitions clean edges, readable facade relief,
        # directional daylight, contact shadows, and cavity detail.
        workbench_aa = int(os.environ.get("C2W_FULL12_WORKBENCH_AA", "16"))
        if workbench_aa not in {8, 16, 32}:
            raise RuntimeError("C2W_FULL12_WORKBENCH_AA must be 8, 16, or 32")
        scene.display.render_aa = str(workbench_aa)
        shading.studio_light = "outdoor.sl"
        shading.studiolight_rotate_z = 0.24
        workbench_color_type = (
            os.environ.get("C2W_FULL12_WORKBENCH_COLOR_TYPE", "MATERIAL")
            .strip()
            .upper()
        )
        if workbench_color_type not in {
            "MATERIAL",
            "OBJECT",
            "RANDOM",
            "TEXTURE",
            "VERTEX",
        }:
            raise RuntimeError(
                "C2W_FULL12_WORKBENCH_COLOR_TYPE must be MATERIAL, OBJECT, "
                "RANDOM, TEXTURE, or VERTEX"
            )
        shading.color_type = workbench_color_type
        shading.background_type = "VIEWPORT"
        shading.background_color = (0.34, 0.59, 0.86)
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "BOTH"
        shading.curvature_ridge_factor = 1.35
        shading.curvature_valley_factor = 1.15
        shading.show_specular_highlight = True
        samples = workbench_aa

    settings = {
        "engine": scene.render.engine,
        "resolution": list(RESOLUTION),
        "format": "PNG/RGB/8",
        "samples": samples,
        "denoising": denoising,
        "devices": device_records,
        "eevee_shadow_quality": eevee_shadow_quality,
        "mesh_simplification": False,
        "lighting": "clear daytime world + sun; temporary interior fill only for interior cameras",
        "composition": "none; direct full-scene depth rasterization",
        "workbench_color_type": (
            scene.display.shading.color_type
            if scene.render.engine == "BLENDER_WORKBENCH"
            else None
        ),
        "workbench_studio_light": (
            scene.display.shading.studio_light
            if scene.render.engine == "BLENDER_WORKBENCH"
            else None
        ),
        "workbench_antialiasing_samples": (
            int(scene.display.render_aa)
            if scene.render.engine == "BLENDER_WORKBENCH"
            else None
        ),
        "workbench_shadows_and_cavity": (
            bool(
                scene.display.shading.show_shadows and scene.display.shading.show_cavity
            )
            if scene.render.engine == "BLENDER_WORKBENCH"
            else None
        ),
    }
    temporary = {
        "previous_world": previous_world,
        "world": world_data,
        "sun": sun,
        "sun_data": sun_data,
        "fill": fill,
        "fill_data": fill_data,
    }
    return settings, temporary


def remove_daylight(scene: bpy.types.Scene, temporary: dict[str, Any]) -> None:
    scene.world = temporary["previous_world"]
    for key in ("sun", "fill"):
        obj = temporary.get(key)
        if obj is not None and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for key, datablocks in (
        ("sun_data", bpy.data.lights),
        ("fill_data", bpy.data.lights),
        ("world", bpy.data.worlds),
    ):
        data = temporary.get(key)
        if data is not None and data.users == 0:
            datablocks.remove(data)


def position_interior_fill(
    fill: bpy.types.Object,
    camera: bpy.types.Object,
    target: Sequence[float],
    active: bool,
) -> None:
    fill.data.energy = 450.0 if active else 0.0
    if not active:
        return
    target_vector = Vector(target)
    fill.location = camera.location + Vector((0.0, 0.0, 0.45))
    fill.rotation_euler = (
        (target_vector - fill.location).to_track_quat("-Z", "Y").to_euler()
    )


def blend_signature() -> dict[str, Any]:
    stat = BLEND_PATH.stat()
    return {
        "path": str(BLEND_PATH.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return None
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def write_manifest(payload: dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, MANIFEST)


def force_placement_roots_visible(
    layout: dict[str, Any],
) -> list[tuple[bpy.types.Object, bool, bool]]:
    """Guarantee that no placed facility is omitted from a delivery render."""
    saved: list[tuple[bpy.types.Object, bool, bool]] = []
    missing = []
    for record in layout["placements"]:
        obj = bpy.data.objects.get(record["name"])
        if obj is None:
            missing.append(record["placement_id"])
            continue
        saved.append((obj, bool(obj.hide_viewport), bool(obj.hide_render)))
        obj.hide_viewport = False
        obj.hide_render = False
    if missing:
        raise RuntimeError(f"Placement roots missing from production blend: {missing}")
    return saved


def restore_object_visibility(
    saved: Iterable[tuple[bpy.types.Object, bool, bool]],
) -> None:
    for obj, hide_viewport, hide_render in saved:
        try:
            obj.hide_viewport = hide_viewport
            obj.hide_render = hide_render
        except ReferenceError:
            continue


def disable_hidden_zero_face_geometry_node_controllers() -> (
    tuple[list[tuple[Any, bool, bool]], list[str]]
):
    """Disable only render-hidden, zero-face Geometry Nodes controllers.

    Blender 5 may recursively expand these kinematic carrier graphs before it
    checks ``hide_render`` on a linked collection instance.  They have no
    renderable faces and are already authored invisible, so disabling their
    modifiers changes neither delivered geometry nor appearance.
    """
    saved: list[tuple[Any, bool, bool]] = []
    names: list[str] = []
    for obj in bpy.data.objects:
        if (
            not obj.hide_render
            or obj.type != "MESH"
            or obj.data is None
            or len(obj.data.polygons) != 0
        ):
            continue
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            saved.append(
                (modifier, bool(modifier.show_viewport), bool(modifier.show_render))
            )
            modifier.show_viewport = False
            modifier.show_render = False
            names.append(f"{obj.name}:{modifier.name}")
    return saved, sorted(names)


def restore_modifier_visibility(saved: Iterable[tuple[Any, bool, bool]]) -> None:
    for modifier, show_viewport, show_render in saved:
        try:
            modifier.show_viewport = show_viewport
            modifier.show_render = show_render
        except ReferenceError:
            continue


def valid_delivery_png(path: Path) -> bool:
    return (
        png_dimensions(path) == RESOLUTION
        and path.is_file()
        and path.stat().st_size >= 5_000
    )


def png_alpha_statistics(path: Path) -> dict[str, Any]:
    """Decode an RGBA8 PNG with only the standard library.

    Blender's bundled Python deliberately has no Pillow in this environment.
    The explicit decoder also makes the raster acceptance independent of a
    workstation-specific image package.
    """
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Projection mask is not a PNG: {path}")
    cursor = 8
    width = height = bit_depth = colour_type = None
    compressed = bytearray()
    while cursor + 12 <= len(payload):
        length = struct.unpack(">I", payload[cursor : cursor + 4])[0]
        kind = payload[cursor + 4 : cursor + 8]
        data = payload[cursor + 8 : cursor + 8 + length]
        cursor += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, colour_type = struct.unpack(">IIBB", data[:10])
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    if not width or not height or bit_depth != 8 or colour_type != 6:
        raise RuntimeError(
            f"Expected RGBA8 projection mask, got {width}x{height}, "
            f"depth={bit_depth}, colour_type={colour_type}"
        )
    raw = zlib.decompress(bytes(compressed))
    channels = 4
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise RuntimeError(
            f"Unexpected projection-mask scanline size: {len(raw)} != {expected}"
        )

    previous = bytearray(stride)
    offset = 0
    alpha_16 = 0
    alpha_128 = 0

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    for _row in range(height):
        filter_type = raw[offset]
        filtered = raw[offset + 1 : offset + 1 + stride]
        offset += stride + 1
        decoded = bytearray(stride)
        for index, value in enumerate(filtered):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                result = value
            elif filter_type == 1:
                result = value + left
            elif filter_type == 2:
                result = value + above
            elif filter_type == 3:
                result = value + ((left + above) // 2)
            elif filter_type == 4:
                result = value + paeth(left, above, upper_left)
            else:
                raise RuntimeError(f"Unsupported PNG filter type {filter_type}")
            decoded[index] = result & 0xFF
        for alpha in decoded[3::4]:
            alpha_16 += alpha >= 16
            alpha_128 += alpha >= 128
        previous = decoded

    total = width * height
    return {
        "width": width,
        "height": height,
        "total_pixels": total,
        "alpha_at_least_16_pixels": alpha_16,
        "alpha_at_least_128_pixels": alpha_128,
        "coverage_ratio_alpha_16": round(alpha_16 / total, 6),
        "coverage_ratio_alpha_128": round(alpha_128 / total, 6),
    }


def render_mesh_projection_audit(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    layout: dict[str, Any],
) -> dict[str, Any]:
    """Measure actual projected asset meshes, not their coarse AABBs."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    mask_path = AUDIT_DIR / "mesh_asset_silhouette_2048.png"
    excluded_names = {"city_base", "roads"}
    hidden_state: list[tuple[bpy.types.Collection, bool, bool]] = []
    for collection in bpy.data.collections:
        if not collection.name.startswith("full10:zone:"):
            continue
        zone = collection.name.rsplit(":", 1)[-1]
        hidden_state.append(
            (collection, bool(collection.hide_viewport), bool(collection.hide_render))
        )
        collection.hide_viewport = zone in excluded_names
        collection.hide_render = zone in excluded_names

    previous = {
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "colour_mode": scene.render.image_settings.color_mode,
        "film_transparent": scene.render.film_transparent,
        "filepath": scene.render.filepath,
        "material_override": scene.view_layers[0].material_override,
    }
    mask_material = bpy.data.materials.new(f"{TEMP_PREFIX}:projection_mask_material")
    mask_material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    mask_material.use_nodes = True
    nodes = mask_material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    mask_material.node_tree.links.new(
        emission.outputs["Emission"], output.inputs["Surface"]
    )

    try:
        scene.render.resolution_x = 2048
        scene.render.resolution_y = 2048
        scene.render.resolution_percentage = 100
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.film_transparent = True
        scene.view_layers[0].material_override = mask_material
        bounds = (
            Vector(layout["city_bounds"]["min"]),
            Vector(layout["city_bounds"]["max"]),
        )
        mask_shot = Shot(
            name="mesh_projection_audit",
            filename=mask_path.name,
            kind="audit",
            direction=(0.001, -0.001, 1.0),
            margin=1.002,
            projection="ORTHO",
        )
        camera_record = fit_camera(camera, bounds, mask_shot, (2048, 2048))
        scene.render.filepath = str(mask_path)
        bpy.context.view_layer.update()
        bpy.ops.render.render(write_still=True)
        if png_dimensions(mask_path) != (2048, 2048):
            raise RuntimeError("Projection audit did not produce a 2048x2048 PNG")
        stats = png_alpha_statistics(mask_path)
    finally:
        scene.view_layers[0].material_override = previous["material_override"]
        scene.render.resolution_x = previous["resolution_x"]
        scene.render.resolution_y = previous["resolution_y"]
        scene.render.resolution_percentage = previous["resolution_percentage"]
        scene.render.image_settings.color_mode = previous["colour_mode"]
        scene.render.film_transparent = previous["film_transparent"]
        scene.render.filepath = previous["filepath"]
        restore_collection_visibility(hidden_state)
        if mask_material.users == 0:
            bpy.data.materials.remove(mask_material)

    threshold = float(layout["coverage_audit"]["minimum_mesh_projected_asset_ratio"])
    ratio = float(stats["coverage_ratio_alpha_128"])
    result = {
        "schema": "agent.mesh_projection_audit.v1",
        "scene_revision": REVISION,
        "created_utc": utc_now(),
        "status": "PASS" if ratio >= threshold else "FAIL",
        "method": (
            "2048x2048 orthographic top raster of actual renderable asset meshes; "
            "constant emissive material override; city ground and road zones excluded"
        ),
        "acceptance_geometry": "evaluated rendered mesh silhouettes; no AABB contribution",
        "delivery_view": False,
        "temporarily_excluded_only_for_auxiliary_audit": sorted(excluded_names),
        "all_asset_regions_included": True,
        "mask_file": str(mask_path.resolve()),
        "mask_bytes": mask_path.stat().st_size,
        "camera": camera_record,
        "statistics": stats,
        "accepted_ratio": ratio,
        "minimum_required_ratio": threshold,
        "pass": ratio >= threshold,
    }
    PROJECTION_AUDIT.write_text(json.dumps(result, indent=2), encoding="utf8")
    return result


def catalogue() -> list[dict[str, Any]]:
    return [
        {
            **asdict(shot),
            "output": str((OUT / shot.filename).resolve()),
        }
        for shot in SHOTS
    ]


def manifest_payload(
    *,
    records: dict[str, dict[str, Any]],
    requested: Sequence[Shot],
    settings: dict[str, Any],
    visible_zones: Sequence[str],
    before: dict[str, Any],
    started: float,
    errors: Sequence[dict[str, Any]],
    projection: dict[str, Any] | None,
    temporary_camera_removed: bool,
) -> dict[str, Any]:
    completed = []
    for shot in SHOTS:
        record = records.get(shot.name)
        if record and valid_delivery_png(OUT / shot.filename):
            completed.append(shot.name)
    missing = [shot.name for shot in SHOTS if shot.name not in completed]
    after = blend_signature()
    complete = (
        not missing
        and not errors
        and projection is not None
        and projection.get("pass") is True
    )
    return {
        "schema": "agent.direct_city_render_manifest.v1",
        "scene_revision": REVISION,
        "created_utc": utc_now(),
        "status": "PASS" if complete else ("FAIL" if errors else "IN_PROGRESS"),
        "complete": complete,
        "expected_count": len(SHOTS),
        "completed_count": len(completed),
        "completed_view_names": completed,
        "missing_view_names": missing,
        "requested_views": [shot.name for shot in requested],
        "output_directory": str(OUT.resolve()),
        "blend_file": str(BLEND_PATH.resolve()),
        "blend_before": before,
        "blend_after": after,
        "blend_file_unchanged": before == after,
        "blend_saved_by_renderer": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "render_settings": settings,
        "visibility_scope": {
            "all_zone_collections_visible_in_every_delivery_view": True,
            "visible_zones": list(visible_zones),
            "temporarily_hidden_zones_in_delivery_views": [],
            "temporarily_hidden_placements_in_delivery_views": [],
            "temporarily_hidden_interiors_in_delivery_views": [],
            "cross_region_depth_occlusion_shadows_reflections": True,
        },
        "render_method": "single-pass direct full-scene depth rasterization",
        "layer_composition": False,
        "representative_interior_view_count": sum(shot.interior for shot in SHOTS),
        "projection_audit": projection,
        "temporary_camera_removed": temporary_camera_removed,
        "errors": list(errors),
        "catalogue": catalogue(),
        "views": [records[name] for name in completed if name in records],
    }


def write_panorama_audit(manifest: dict[str, Any]) -> dict[str, Any]:
    complete_names = set(manifest["completed_view_names"])
    city = [shot for shot in SHOTS if shot.kind == "city"]
    interiors = [shot for shot in SHOTS if shot.interior]
    regional_pairs = {zone: [f"{zone}_far", f"{zone}_near"] for zone in ZONE_IDS}
    audit = {
        "schema": "agent.panorama_audit.v2",
        "scene_revision": REVISION,
        "created_utc": utc_now(),
        "status": "PASS" if manifest["complete"] else "FAIL",
        "citywide_panorama_count": len(city),
        "regional_near_far_pair_count": len(regional_pairs),
        "total_delivery_png_count": manifest["completed_count"],
        "minimum_delivery_png_count": 60,
        "resolution": list(RESOLUTION),
        "minimum_resolution": [1920, 1080],
        "all_regions_visible_in_every_delivery_view": True,
        "direct_depth_rendering": True,
        "alpha_or_layer_composition": False,
        "representative_interior_view_count": len(interiors),
        "citywide_files": [shot.filename for shot in city],
        "regional_pairs": regional_pairs,
        "all_citywide_views_complete": all(
            shot.name in complete_names for shot in city
        ),
        "all_regional_pairs_complete": all(
            all(name in complete_names for name in names)
            for names in regional_pairs.values()
        ),
        "all_interior_views_complete": all(
            shot.name in complete_names for shot in interiors
        ),
        "mesh_projection_audit_pass": bool(
            manifest.get("projection_audit")
            and manifest["projection_audit"].get("pass")
        ),
        "render_manifest": str(MANIFEST.resolve()),
    }
    checks = [
        audit["total_delivery_png_count"] >= audit["minimum_delivery_png_count"],
        audit["resolution"][0] >= 1920 and audit["resolution"][1] >= 1080,
        audit["all_citywide_views_complete"],
        audit["all_regional_pairs_complete"],
        audit["all_interior_views_complete"],
        audit["mesh_projection_audit_pass"],
        manifest["blend_file_unchanged"],
    ]
    audit["checks_pass"] = all(checks)
    audit["status"] = "PASS" if audit["checks_pass"] else "FAIL"
    PANORAMA_AUDIT.write_text(json.dumps(audit, indent=2), encoding="utf8")
    return audit


def main() -> None:
    if not BLEND_PATH.is_file() or not LAYOUT_PATH.is_file():
        raise RuntimeError("Generate urban_v1_full_12 before rendering it")
    if Path(bpy.data.filepath).resolve() != BLEND_PATH.resolve():
        raise RuntimeError(
            f"Renderer must be opened on the production blend: {BLEND_PATH}; "
            f"got {bpy.data.filepath}"
        )
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    if layout.get("scene_revision") != REVISION:
        raise RuntimeError("Layout revision does not match full-12")
    by_id = {record["placement_id"]: record for record in layout["placements"]}
    selected = select_shots(script_args())
    if not selected:
        return

    OUT.mkdir(parents=True, exist_ok=True)
    before = blend_signature()
    started = time.monotonic()
    errors: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    if MANIFEST.is_file():
        try:
            existing = json.loads(MANIFEST.read_text(encoding="utf8"))
            if existing.get("scene_revision") == REVISION:
                records = {
                    record["name"]: record
                    for record in existing.get("views", [])
                    if record.get("name") in SHOT_BY_NAME
                }
        except (OSError, ValueError, KeyError):
            records = {}

    scene = bpy.context.scene
    previous_camera = scene.camera
    previous_nodes = scene.use_nodes
    previous_compositing = getattr(scene.render, "use_compositing", None)
    previous_sequencer = getattr(scene.render, "use_sequencer", None)
    scene.use_nodes = False
    if previous_compositing is not None:
        scene.render.use_compositing = False
    if previous_sequencer is not None:
        scene.render.use_sequencer = False

    saved_collections: list[tuple[bpy.types.Collection, bool, bool]] = []
    saved_objects: list[tuple[bpy.types.Object, bool, bool]] = []
    saved_controllers: list[tuple[Any, bool, bool]] = []
    disabled_controllers: list[str] = []
    daylight: dict[str, Any] | None = None
    camera = None
    camera_data = None
    settings: dict[str, Any] = {}
    projection: dict[str, Any] | None = None
    visible_zones: list[str] = []
    force = os.environ.get("C2W_FULL12_RENDER_FORCE", "0") == "1"
    try:
        saved_collections, visible_zones = force_all_regions_visible()
        saved_objects = force_placement_roots_visible(layout)
        (
            saved_controllers,
            disabled_controllers,
        ) = disable_hidden_zero_face_geometry_node_controllers()
        expected_zones = sorted({record["zone"] for record in layout["placements"]})
        if visible_zones != expected_zones:
            raise RuntimeError(
                f"Production zone mismatch: scene={visible_zones}, layout={expected_zones}"
            )
        settings, daylight = configure_daylight(scene)
        settings["workbench_material_sync"] = synchronize_workbench_material_colors(
            scene
        )
        settings[
            "disabled_preexisting_hidden_zero_face_gn_controllers"
        ] = disabled_controllers
        settings["disabled_visible_geometry_count"] = 0
        camera_data = bpy.data.cameras.new(f"{TEMP_PREFIX}:camera_data")
        camera = bpy.data.objects.new(f"{TEMP_PREFIX}:camera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera

        print(
            f"FULL12_RENDER_START views={len(selected)} expected={len(SHOTS)} "
            f"resolution={RESOLUTION[0]}x{RESOLUTION[1]} engine={settings['engine']}",
            flush=True,
        )
        for index, shot in enumerate(selected, 1):
            target_path = OUT / shot.filename
            if (
                not force
                and valid_delivery_png(target_path)
                and shot.name in records
                and shot_record_matches_spec(records[shot.name], shot)
            ):
                print(
                    f"FULL12_RENDER_SKIP {index}/{len(selected)} {shot.name}",
                    flush=True,
                )
                continue
            shot_started = time.monotonic()
            try:
                bounds = resolve_bounds(shot, layout, by_id)
                camera_record = configure_camera(camera, shot, bounds, by_id)
                position_interior_fill(
                    daylight["fill"], camera, camera_record["target"], shot.interior
                )
                # These invariants are reasserted before every delivery image.
                hidden_zones = [
                    collection.name
                    for collection, _old_viewport, _old_render in saved_collections
                    if collection.hide_viewport or collection.hide_render
                ]
                hidden_roots = [
                    obj.name
                    for obj, _old_viewport, _old_render in saved_objects
                    if obj.hide_viewport or obj.hide_render
                ]
                if hidden_zones or hidden_roots:
                    raise RuntimeError(
                        f"Visibility invariant violated: zones={hidden_zones}, placements={hidden_roots}"
                    )
                scene.render.filepath = str(target_path)
                bpy.context.view_layer.update()
                bpy.ops.render.render(write_still=True)
                if not valid_delivery_png(target_path):
                    raise RuntimeError(
                        f"Invalid delivery PNG {target_path}: dimensions={png_dimensions(target_path)}"
                    )
                record = {
                    **asdict(shot),
                    "camera_composition_revision": CAMERA_COMPOSITION_REVISION,
                    "shot_spec_sha256": shot_spec_sha256(shot),
                    "output": str(target_path.resolve()),
                    "bounds": {
                        "min": [round(float(value), 4) for value in bounds[0]],
                        "max": [round(float(value), 4) for value in bounds[1]],
                    },
                    "camera": camera_record,
                    "status": "rendered",
                    "bytes": target_path.stat().st_size,
                    "dimensions": list(RESOLUTION),
                    "render_seconds": round(time.monotonic() - shot_started, 3),
                    "render_method": "single-pass direct full-scene depth rasterization",
                    "all_regions_visible": True,
                    "temporarily_hidden_zones": [],
                    "temporarily_hidden_placements": [],
                    "temporarily_hidden_interiors": [],
                    "layer_composition": False,
                }
                records[shot.name] = record
                print(
                    f"FULL12_RENDER_DONE {index}/{len(selected)} {shot.name} "
                    f"bytes={record['bytes']} seconds={record['render_seconds']}",
                    flush=True,
                )
                interim = manifest_payload(
                    records=records,
                    requested=selected,
                    settings=settings,
                    visible_zones=visible_zones,
                    before=before,
                    started=started,
                    errors=errors,
                    projection=None,
                    temporary_camera_removed=False,
                )
                write_manifest(interim)
            except Exception as exc:
                errors.append({"view": shot.name, "error": repr(exc)})
                print(f"FULL12_RENDER_ERROR {shot.name}: {exc!r}", flush=True)
                raise

        all_outputs_ready = all(
            valid_delivery_png(OUT / shot.filename) and shot.name in records
            for shot in SHOTS
        )
        if all_outputs_ready:
            projection = render_mesh_projection_audit(scene, camera, layout)
            if not projection["pass"]:
                errors.append(
                    {
                        "view": "mesh_projection_audit",
                        "error": (
                            f"actual mesh coverage {projection['accepted_ratio']} is below "
                            f"{projection['minimum_required_ratio']}"
                        ),
                    }
                )
    finally:
        if camera is not None and camera.name in bpy.data.objects:
            bpy.data.objects.remove(camera, do_unlink=True)
        if camera_data is not None and camera_data.users == 0:
            bpy.data.cameras.remove(camera_data)
        scene.camera = previous_camera
        if daylight is not None:
            remove_daylight(scene, daylight)
        restore_object_visibility(saved_objects)
        restore_collection_visibility(saved_collections)
        restore_modifier_visibility(saved_controllers)
        scene.use_nodes = previous_nodes
        if previous_compositing is not None:
            scene.render.use_compositing = previous_compositing
        if previous_sequencer is not None:
            scene.render.use_sequencer = previous_sequencer

        final_manifest = manifest_payload(
            records=records,
            requested=selected,
            settings=settings,
            visible_zones=visible_zones,
            before=before,
            started=started,
            errors=errors,
            projection=projection,
            temporary_camera_removed=True,
        )
        write_manifest(final_manifest)
        write_panorama_audit(final_manifest)
        print(
            f"FULL12_RENDER_FINISH status={final_manifest['status']} "
            f"completed={final_manifest['completed_count']}/{final_manifest['expected_count']} "
            f"elapsed={final_manifest['elapsed_seconds']}",
            flush=True,
        )

    if errors:
        raise RuntimeError(f"Full-12 render audit failed: {errors}")


if __name__ == "__main__":
    main()
