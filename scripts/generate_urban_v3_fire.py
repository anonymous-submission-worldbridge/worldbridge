"""Reference-driven fire-station region for the active Urban-v3 pipeline.

This source file is both the production asset generator and the validation
entrypoint for ``outdoor_part_demo/urban_v3_fire7``.  It deliberately rebuilds
all apparatus, architecture, interiors and site equipment from procedural
geometry; no generated ``.blend`` is ever used as an input.

Public factory entrypoints
--------------------------
``build_fire_truck_asset``
    Builds one of three independently placeable fire-apparatus types.  Four
    downloaded detailed meshes (71k--205k vertices) are treated as measurement
    evidence for independently programmed pumper and aerial-ladder assets;
    none of their render geometry is imported into the generated scene.
``build_ambulance_asset``
    Builds a full-size Type-I ambulance from reverse-engineered mesh landmarks
    and manufacturer dimensions.  The downloaded mesh is calibration evidence,
    never render geometry.
``build_fire_station_asset``
    Builds one of two independently placeable station architectures.
``build_fire_station_region``
    Composes both stations and four fire engines representing all three
    apparatus types into the requested coherent fire-service precinct.  This
    is the entrypoint used by :mod:`urban_assets` and by this file's validation
    run.  No ambulance geometry is placed in the delivered region.
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


from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
import random
import shutil
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
ASSET_ID = "urban_v3_fire7"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo" / ASSET_ID
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
BLEND = OUT / f"{ASSET_ID}.blend"
PREFIX = "fire_region_v7:"
SCHEMA_VERSION = 7
RNG = random.Random(20260902)

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

REFERENCE_URLS = [
    "https://ifinger3d.com/wp-content/uploads/2025/12/Fire-Station-Building-1.jpg",
    "https://media.sketchfab.com/models/75cca108d258416b8ee8c46325893f41/thumbnails/54b1bd7c950747408999722d6d69da71/afab142d82184fcea8d347d813836b3b.jpeg",
    "https://i.pinimg.com/originals/47/ff/58/47ff58b362bf266554b9bf244660a9b1.jpg?nii=t",
    "https://ifinger3d.com/wp-content/uploads/2025/12/Fire-Station-Building-.jpg",
]
REFERENCE_CACHE = [
    ROOT / ".reference_cache/fire/reference_01.jpg",
    ROOT / ".reference_cache/fire/reference_02.jpeg",
    ROOT / ".reference_cache/fire/reference_03.jpg",
    ROOT / ".reference_cache/fire/reference_04.jpg",
]
REFERENCE_FILES = [
    "reference_01.jpg",
    "reference_02.jpeg",
    "reference_03.jpg",
    "reference_04.jpg",
]

TRUCK_VARIANTS = ("modern_ladder_engine", "classic_pumper", "rapid_rescue")
AMBULANCE_VARIANTS = ("type_i_ambulance",)
STATION_VARIANTS = ("civic_headquarters", "industrial_annex")

AMBULANCE_MESH_URL = (
    "https://opengameart.org/sites/default/files/kenney_car-kit_3.1.zip"
)
AMBULANCE_MESH_PAGE = "https://opengameart.org/content/car-kit"
AMBULANCE_DIMENSION_URL = "https://www.demers-ambulances.com/ca-en/ambulance/mxp-150/"
AMBULANCE_PHOTO_URL = "https://www.macqueengroup.com/hubfs/PQET9489.jpg"
AMBULANCE_REFERENCE_CACHE = ROOT / ".reference_cache/fire/ambulance_kenney_3_1"
AMBULANCE_PHOTO_CACHE = (
    ROOT / ".reference_cache/fire/ambulance_photo/demers_mxp150_f450_reference.jpg"
)
AMBULANCE_REFERENCE_FILES = (
    "kenney_car-kit_3.1.zip",
    "ambulance.glb",
    "ambulance.obj",
    "ambulance.mtl",
    "ambulance.png",
    "License.txt",
)

FIRE_TRUCK_MESH_PAGE = "https://www.cadnav.com/3d-models/model-49268.html"
FIRE_TRUCK_MESH_DOWNLOAD_PAGE = (
    "https://www.cadnav.com/plus/download.php?aid=49268&cid=3&open=0"
)
FIRE_TRUCK_REFERENCE_CACHE = ROOT / ".reference_cache/fire/fire_engine_cadnav"
FIRE_TRUCK_OBJ = (
    FIRE_TRUCK_REFERENCE_CACHE
    / "extracted/cadnav.com_model/Models_G0202A086/Firefighting.obj"
)
FIRE_TRUCK_MTL = FIRE_TRUCK_OBJ.with_suffix(".mtl")
FIRE_TRUCK_README = FIRE_TRUCK_REFERENCE_CACHE / "extracted/cadnav.com_model/readme.txt"
FIRE_TRUCK_REFERENCE_FILES = (
    (FIRE_TRUCK_REFERENCE_CACHE / "fire_engine_49268.rar", "fire_engine_49268.rar"),
    (FIRE_TRUCK_OBJ, "Firefighting.obj"),
    (FIRE_TRUCK_MTL, "Firefighting.mtl"),
    (FIRE_TRUCK_README, "source_terms_readme.txt"),
)
FIRE_TRUCK_PREVIEW_FILES = (
    (
        FIRE_TRUCK_REFERENCE_CACHE / "source_preview_main.jpeg",
        "source_preview_main.jpeg",
    ),
    (FIRE_TRUCK_REFERENCE_CACHE / "source_preview_01.jpeg", "source_preview_01.jpeg"),
    (FIRE_TRUCK_REFERENCE_CACHE / "source_preview_02.jpeg", "source_preview_02.jpeg"),
)

# Fire7 uses a *suite* of detailed fire-apparatus meshes instead of deriving
# three vehicles from one source.  The Autodesk .max files are intentionally
# retained as source evidence only: their compound-document signature, byte
# size, published topology and embedded material vocabulary are verified here,
# while the preview silhouettes are converted into explicit metric landmarks
# below.  The existing OBJ remains the directly measurable fourth source.
FIRE7_REFERENCE_ROOT = ROOT / ".reference_cache/fire/fire7_sources"
FIRE7_MESH_SOURCES = {
    "classic_pumper": {
        "model_id": 29256,
        "title": "European enclosed urban pumper",
        "page": "https://www.cadnav.com/3d-models/model-29256.html",
        "archive": FIRE7_REFERENCE_ROOT / "29256/fire_truck_29256.rar",
        "mesh": FIRE7_REFERENCE_ROOT
        / "29256/extracted/cadnav.com_model/Vehicle_B0711106/Cadnav.com_B0711106.max",
        "preview_files": (FIRE7_REFERENCE_ROOT / "29256/preview_01.jpg",),
        "published_vertices": 123872,
        "published_polygons": 124925,
        "published_format": ".max",
        "calibration": {
            "overall_dimensions_m": [9.18, 2.52, 3.34],
            "wheel_centers_y_m": [-2.72, 1.72, 3.04],
            "cab_front_y_m": -4.42,
            "cab_rear_y_m": -0.92,
            "body_front_y_m": -0.76,
            "body_rear_y_m": 4.38,
            "cab_glass_rake_deg": 12.0,
            "compartment_cadence_m": [1.08, 1.13, 1.14],
            "source_observations": "three-axle cab-over pumper; raked panoramic glazing; low front bumper; five shutter fields; open hose/ladder roof rack",
        },
    },
    "modern_ladder_engine": {
        "model_id": 28408,
        "title": "American tandem-axle aerial platform",
        "page": "https://www.cadnav.com/3d-models/model-28408.html",
        "archive": FIRE7_REFERENCE_ROOT / "28408/fire_truck_28408.rar",
        "mesh": FIRE7_REFERENCE_ROOT
        / "28408/extracted/cadnav.com_model/Vehicle_B0602027/Cadnav.com_B0603027.max",
        "preview_files": (FIRE7_REFERENCE_ROOT / "28408/preview_01.jpg",),
        "published_vertices": 205123,
        "published_polygons": 192706,
        "published_format": ".max",
        "calibration": {
            "overall_dimensions_m": [11.82, 2.55, 3.64],
            "wheel_centers_y_m": [-3.48, 1.82, 3.20],
            "cab_front_y_m": -5.61,
            "cab_rear_y_m": -1.36,
            "body_front_y_m": -1.18,
            "body_rear_y_m": 5.56,
            "cab_glass_rake_deg": 8.0,
            "stowed_ladder_length_m": 9.46,
            "turntable_center_y_m": 1.26,
            "source_observations": "three-axle American aerial; four-door crew cab; pump panel behind cab; stabilizers; deep ladder truss and rescue basket",
        },
    },
    "rapid_rescue": {
        "model_id": 46403,
        "title": "Short-wheelbase aerial ladder fire engine",
        "page": "https://www.cadnav.com/3d-models/model-46403.html",
        "archive": FIRE7_REFERENCE_ROOT / "46403/fire_truck_46403.rar",
        "mesh": FIRE7_REFERENCE_ROOT
        / "46403/extracted/cadnav.com_model/Models_E0504A054/Firetruck_US.max",
        "preview_files": (
            FIRE7_REFERENCE_ROOT / "46403/preview_01.jpeg",
            FIRE7_REFERENCE_ROOT / "46403/preview_02.jpeg",
            FIRE7_REFERENCE_ROOT / "46403/preview_03.jpeg",
        ),
        "published_vertices": 100308,
        "published_polygons": 106221,
        "published_format": ".max",
        "calibration": {
            "overall_dimensions_m": [8.62, 2.48, 3.31],
            "wheel_centers_y_m": [-2.43, 2.31],
            "cab_front_y_m": -4.11,
            "cab_rear_y_m": -0.68,
            "body_front_y_m": -0.51,
            "body_rear_y_m": 4.08,
            "cab_glass_rake_deg": 6.0,
            "stowed_ladder_length_m": 8.34,
            "turntable_center_y_m": 1.54,
            "source_observations": "two-axle fire engine; full crew cab; midship pump panel; compact turntable ladder; elevated rescue basket",
        },
    },
}


@dataclass(frozen=True)
class TruckSpec:
    variant: str
    asset_id: str
    archetype: str
    length: float
    width: float
    height: float
    wheelbase: tuple[float, ...]
    reference_index: int


@dataclass(frozen=True)
class AmbulanceSpec:
    variant: str = "type_i_ambulance"
    asset_id: str = "ambulance.type_i.module_150.v6"
    archetype: str = "type_i_f450_box_ambulance"
    # Demers MXP-150/Ford F450 published real-world envelope, converted to m.
    length: float = 7.403
    width: float = 2.413
    height: float = 2.946
    wheelbase: tuple[float, ...] = (-2.360, 1.933)
    module_length: float = 3.810
    module_width: float = 2.413
    interior_headroom: float = 1.828


AMBULANCE_SPEC = AmbulanceSpec()


TRUCK_SPECS = {
    "modern_ladder_engine": TruckSpec(
        "modern_ladder_engine",
        "fire_truck.aerial_platform.tandem.v7",
        "reverse_engineered_three_axle_aerial_platform_fire_engine",
        11.82,
        2.55,
        3.64,
        (-3.48, 1.82, 3.20),
        1,
    ),
    "classic_pumper": TruckSpec(
        "classic_pumper",
        "fire_truck.enclosed_urban_pumper.v7",
        "reverse_engineered_three_axle_enclosed_urban_pumper",
        9.18,
        2.52,
        3.34,
        (-2.72, 1.72, 3.04),
        2,
    ),
    "rapid_rescue": TruckSpec(
        "rapid_rescue",
        "fire_truck.compact_aerial_rescue.v7",
        "reverse_engineered_two_axle_compact_aerial_fire_engine",
        8.62,
        2.48,
        3.31,
        (-2.43, 2.31),
        3,
    ),
}


@dataclass
class BuildContext:
    collection: bpy.types.Collection
    anchor: bpy.types.Object
    variant: str
    asset_id: str
    category: str


SHARED_MESHES: dict[tuple, bpy.types.Mesh] = {}


def set_prefix(value: str):
    global PREFIX
    PREFIX = value


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    SHARED_MESHES.clear()


def analyze_ambulance_reference():
    """Recover proportions and movable-part landmarks from the archived OBJ.

    The source mesh is intentionally *not* imported into Blender.  Its group
    topology and bounding boxes are treated as measured design evidence, then
    reconciled with a current manufacturer's published Type-I dimensions.  The
    resulting numbers drive the source geometry built below and are written to
    the delivery as an auditable reverse-engineering record.
    """
    obj_path = AMBULANCE_REFERENCE_CACHE / "ambulance.obj"
    glb_path = AMBULANCE_REFERENCE_CACHE / "ambulance.glb"
    license_path = AMBULANCE_REFERENCE_CACHE / "License.txt"
    for path, minimum_bytes in (
        (obj_path, 100000),
        (glb_path, 100000),
        (license_path, 100),
    ):
        if not path.is_file() or path.stat().st_size < minimum_bytes:
            raise FileNotFoundError(
                f"Missing downloaded ambulance mesh evidence: {path}"
            )

    groups = {}
    current_group = "ungrouped"
    for raw_line in obj_path.read_text(encoding="utf8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("g "):
            current_group = line[2:].strip() or "ungrouped"
            continue
        if not line.startswith("v "):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        point = tuple(float(value) for value in fields[1:4])
        record = groups.setdefault(
            current_group, {"count": 0, "min": list(point), "max": list(point)}
        )
        record["count"] += 1
        for axis in range(3):
            record["min"][axis] = min(record["min"][axis], point[axis])
            record["max"][axis] = max(record["max"][axis], point[axis])

    if not {
        "body",
        "wheel-front-left",
        "wheel-front-right",
        "wheel-back-left",
        "wheel-back-right",
    }.issubset(groups):
        raise RuntimeError(
            "Downloaded ambulance OBJ does not expose the expected body/four-wheel topology"
        )

    def normalize(record):
        dims = [record["max"][axis] - record["min"][axis] for axis in range(3)]
        center = [
            (record["max"][axis] + record["min"][axis]) * 0.5 for axis in range(3)
        ]
        return {
            "vertex_count": record["count"],
            "bounds_xyz": [
                [round(value, 7) for value in record["min"]],
                [round(value, 7) for value in record["max"]],
            ],
            "dimensions_xyz": [round(value, 7) for value in dims],
            "center_xyz": [round(value, 7) for value in center],
        }

    normalized = {name: normalize(record) for name, record in sorted(groups.items())}
    all_min = [
        min(record["min"][axis] for record in groups.values()) for axis in range(3)
    ]
    all_max = [
        max(record["max"][axis] for record in groups.values()) for axis in range(3)
    ]
    source_dims = [all_max[axis] - all_min[axis] for axis in range(3)]
    # OBJ axes are X=width, Y=height, Z=length.  Vehicle-local output axes are
    # X=width, Y=length (front is negative), Z=height.
    front_center_z = normalized["wheel-front-left"]["center_xyz"][2]
    rear_center_z = normalized["wheel-back-left"]["center_xyz"][2]
    wheelbase_ratio = abs(front_center_z - rear_center_z) / source_dims[2]
    return {
        "method": "OBJ group/bounds landmark extraction; non-uniform silhouette reconciliation; source mesh never imported as render geometry",
        "source": {
            "title": "Car Kit 3.1 / ambulance",
            "creator": "Kenney",
            "download_page": AMBULANCE_MESH_PAGE,
            "download_url": AMBULANCE_MESH_URL,
            "license": "Creative Commons Zero (CC0)",
            "obj_sha256": hashlib.sha256(obj_path.read_bytes()).hexdigest(),
            "glb_sha256": hashlib.sha256(glb_path.read_bytes()).hexdigest(),
            "obj_vertex_count": sum(record["count"] for record in groups.values()),
            "obj_axes": "X width, Y height, Z length",
            "bounds_xyz": [
                [round(value, 7) for value in all_min],
                [round(value, 7) for value in all_max],
            ],
            "dimensions_xyz": [round(value, 7) for value in source_dims],
            "groups": normalized,
            "wheelbase_to_length_ratio": round(wheelbase_ratio, 7),
        },
        "manufacturer_constraint": {
            "source": AMBULANCE_DIMENSION_URL,
            "model_basis": "Demers MXP 150 Type I on Ford F450",
            "overall_dimensions_m": [
                AMBULANCE_SPEC.length,
                AMBULANCE_SPEC.width,
                AMBULANCE_SPEC.height,
            ],
            "wheelbase_m": round(
                AMBULANCE_SPEC.wheelbase[1] - AMBULANCE_SPEC.wheelbase[0], 3
            ),
            "module_length_m": AMBULANCE_SPEC.module_length,
            "module_width_m": AMBULANCE_SPEC.module_width,
            "interior_headroom_m": AMBULANCE_SPEC.interior_headroom,
        },
        "derived_programmatic_parameters": {
            "vehicle_local_axes": "X width, Y length/front-negative, Z up",
            "wheel_centers_y_m": list(AMBULANCE_SPEC.wheelbase),
            "source_ratio_error_vs_manufacturer": round(
                wheelbase_ratio
                - (AMBULANCE_SPEC.wheelbase[1] - AMBULANCE_SPEC.wheelbase[0])
                / AMBULANCE_SPEC.length,
                7,
            ),
            "uniform_source_scale_rejected": True,
            "reason": "source mesh is a landmark scaffold; manufacturer width/height/length require independent real-world constraints",
        },
    }


_FIRE_TRUCK_ANALYSIS_CACHE = None


def analyze_fire_truck_reference():
    """Measure a detailed downloaded fire-engine OBJ without importing it.

    The source OBJ is deliberately treated as design evidence rather than an
    opaque asset.  Face groups, material assignments and vertex bounds recover
    the three axle stations, commercial tire diameter, cab/glazing envelope,
    equipment-body length and roof-ladder landmarks.  The local procedural
    convention is X=width, Y=length/front-negative and Z=height; the OBJ uses
    X=width, Y=height and Z=length/front-positive.
    """
    global _FIRE_TRUCK_ANALYSIS_CACHE
    if _FIRE_TRUCK_ANALYSIS_CACHE is not None:
        return _FIRE_TRUCK_ANALYSIS_CACHE

    required = (
        (FIRE_TRUCK_OBJ, 10_000_000),
        (FIRE_TRUCK_MTL, 500),
        (FIRE_TRUCK_README, 500),
        (FIRE_TRUCK_REFERENCE_CACHE / "fire_engine_49268.rar", 1_000_000),
    )
    for path, minimum_bytes in required:
        if not path.is_file() or path.stat().st_size < minimum_bytes:
            raise FileNotFoundError(
                f"Missing detailed fire-truck mesh evidence: {path}"
            )

    vertices = []
    groups = {}
    current_group = "default"
    current_material = "default"
    face_count = 0
    material_face_counts = {}
    with FIRE_TRUCK_OBJ.open("r", encoding="utf8", errors="replace") as source:
        for raw_line in source:
            if raw_line.startswith("v "):
                fields = raw_line.split()
                if len(fields) >= 4:
                    vertices.append(tuple(float(value) for value in fields[1:4]))
            elif raw_line.startswith("g "):
                current_group = raw_line[2:].strip() or "default"
            elif raw_line.startswith("usemtl "):
                current_material = raw_line[7:].strip() or "default"
            elif raw_line.startswith("f "):
                face_count += 1
                material_face_counts[current_material] = (
                    material_face_counts.get(current_material, 0) + 1
                )
                record = groups.setdefault(
                    current_group,
                    {
                        "indices": set(),
                        "face_count": 0,
                        "materials": set(),
                    },
                )
                record["face_count"] += 1
                record["materials"].add(current_material)
                for corner in raw_line[2:].split():
                    raw_index = int(corner.split("/", 1)[0])
                    index = (
                        raw_index - 1 if raw_index > 0 else len(vertices) + raw_index
                    )
                    if 0 <= index < len(vertices):
                        record["indices"].add(index)

    if len(vertices) < 70_000 or face_count < 68_000 or len(groups) < 400:
        raise RuntimeError(
            "Fire-truck source is not the required detailed mesh "
            f"(vertices={len(vertices)}, faces={face_count}, groups={len(groups)})"
        )

    def bounds_from_indices(indices):
        points = [vertices[index] for index in indices]
        minimum = [min(point[axis] for point in points) for axis in range(3)]
        maximum = [max(point[axis] for point in points) for axis in range(3)]
        dimensions = [maximum[axis] - minimum[axis] for axis in range(3)]
        center = [(maximum[axis] + minimum[axis]) * 0.5 for axis in range(3)]
        return minimum, maximum, dimensions, center

    normalized_groups = []
    for name, raw_record in groups.items():
        if not raw_record["indices"]:
            continue
        minimum, maximum, dimensions, center = bounds_from_indices(
            raw_record["indices"]
        )
        normalized_groups.append(
            {
                "name": name,
                "face_count": raw_record["face_count"],
                "vertex_count": len(raw_record["indices"]),
                "materials": sorted(raw_record["materials"]),
                "bounds_xyz": [
                    [round(value, 7) for value in minimum],
                    [round(value, 7) for value in maximum],
                ],
                "dimensions_xyz": [round(value, 7) for value in dimensions],
                "center_xyz": [round(value, 7) for value in center],
            }
        )

    all_min, all_max, all_dims, _ = bounds_from_indices(range(len(vertices)))
    wheel_groups = [
        record
        for record in normalized_groups
        if record["face_count"] >= 4_000
        and record["dimensions_xyz"][0] <= 0.45
        and 1.10 <= record["dimensions_xyz"][1] <= 1.30
        and 1.10 <= record["dimensions_xyz"][2] <= 1.30
        and record["center_xyz"][1] < 1.0
    ]
    if len(wheel_groups) != 6:
        raise RuntimeError(
            f"Expected six high-resolution wheel groups, found {len(wheel_groups)}"
        )
    axle_source_z = sorted(
        {round(record["center_xyz"][2], 4) for record in wheel_groups}
    )
    if len(axle_source_z) != 3:
        raise RuntimeError(f"Expected three axle landmarks, found {axle_source_z}")
    axle_local_y = sorted(round(-value, 4) for value in axle_source_z)

    def choose(predicate, key):
        candidates = [record for record in normalized_groups if predicate(record)]
        if not candidates:
            raise RuntimeError(
                "Detailed fire-truck OBJ is missing a required reverse-engineering landmark"
            )
        return max(candidates, key=key)

    windshield = choose(
        lambda record: "blinn5SG" in record["materials"]
        and record["dimensions_xyz"][0] > 2.0
        and record["dimensions_xyz"][1] > 0.70,
        lambda record: record["face_count"],
    )
    cab_shell = choose(
        lambda record: record["center_xyz"][2] > 2.3
        and record["dimensions_xyz"][0] > 2.4
        and record["dimensions_xyz"][2] > 1.3,
        lambda record: record["face_count"],
    )
    equipment_body = choose(
        lambda record: record["center_xyz"][2] < -0.5
        and record["dimensions_xyz"][1] > 2.0
        and record["dimensions_xyz"][2] > 4.0,
        lambda record: record["face_count"],
    )
    ladder_groups = sorted(
        [
            record
            for record in normalized_groups
            if record["center_xyz"][1] > 3.1
            and record["dimensions_xyz"][2] > 4.0
            and record["face_count"] > 500
        ],
        key=lambda record: record["center_xyz"][0],
    )
    if len(ladder_groups) < 2:
        raise RuntimeError(
            "Detailed fire-truck OBJ is missing the paired roof-ladder groups"
        )

    body_width = cab_shell["dimensions_xyz"][0]
    wheel_diameter = sum(record["dimensions_xyz"][1] for record in wheel_groups) / len(
        wheel_groups
    )
    source_landmarks = {
        "wheel_groups": sorted(
            wheel_groups,
            key=lambda record: (record["center_xyz"][2], record["center_xyz"][0]),
        ),
        "windshield": windshield,
        "cab_shell": cab_shell,
        "equipment_body": equipment_body,
        "roof_ladders": ladder_groups[:2],
    }
    _FIRE_TRUCK_ANALYSIS_CACHE = {
        "method": (
            "OBJ vertex/face-group/material landmark extraction; source-axis remap; "
            "cross-section and running-gear reconstruction; source mesh never imported as render geometry"
        ),
        "source": {
            "title": "Fire Engine Truck 3D Model #49268",
            "download_page": FIRE_TRUCK_MESH_PAGE,
            "download_interstitial": FIRE_TRUCK_MESH_DOWNLOAD_PAGE,
            "usage_terms": (
                "CadNav source readme permits modification and project/artwork use with attribution; "
                "listing labels the download Non-commercial; retained only as local measurement evidence"
            ),
            "obj_sha256": hashlib.sha256(FIRE_TRUCK_OBJ.read_bytes()).hexdigest(),
            "rar_sha256": hashlib.sha256(
                (FIRE_TRUCK_REFERENCE_CACHE / "fire_engine_49268.rar").read_bytes()
            ).hexdigest(),
            "obj_bytes": FIRE_TRUCK_OBJ.stat().st_size,
            "obj_vertex_count": len(vertices),
            "obj_face_count": face_count,
            "obj_group_count": len(normalized_groups),
            "obj_axes": "X width, Y height, Z length/front-positive",
            "bounds_xyz": [
                [round(value, 7) for value in all_min],
                [round(value, 7) for value in all_max],
            ],
            "dimensions_xyz": [round(value, 7) for value in all_dims],
            "material_face_counts": dict(sorted(material_face_counts.items())),
            "landmarks": source_landmarks,
        },
        "derived_programmatic_parameters": {
            "vehicle_local_axes": "X width, Y length/front-negative, Z up",
            "source_to_local_transform": "local_x=source_x; local_y=-source_z; local_z=source_y-source_ground_y",
            "overall_length_m": round(all_dims[2], 4),
            "body_width_m": round(body_width, 4),
            "overall_height_m": round(all_dims[1], 4),
            "mirror_tip_width_m": round(all_dims[0], 4),
            "wheel_centers_y_m": axle_local_y,
            "wheel_diameter_m": round(wheel_diameter, 4),
            "wheel_radius_m": round(wheel_diameter * 0.5, 4),
            "tandem_spacing_m": round(axle_local_y[2] - axle_local_y[1], 4),
            "windshield_width_m": round(windshield["dimensions_xyz"][0], 4),
            "windshield_height_m": round(windshield["dimensions_xyz"][1], 4),
            "roof_ladder_lengths_m": [
                round(record["dimensions_xyz"][2], 4) for record in ladder_groups[:2]
            ],
            "procedural_variant": "modern_ladder_engine",
            "native_asset_scale": 1.0,
            "precinct_pose_scale": 1.30,
            "front_direction": "local_negative_y",
        },
        "render_policy": {
            "downloaded_mesh_objects_imported": 0,
            "downloaded_mesh_faces_rendered": 0,
            "all_output_geometry": "source-generated programmable Blender geometry",
        },
    }
    return _FIRE_TRUCK_ANALYSIS_CACHE


_FIRE7_SUITE_ANALYSIS_CACHE = None


def analyze_fire_truck_reference_suite():
    """Validate and parameterize the four detailed fire-engine mesh sources.

    Three independently downloaded ``.max`` meshes are OLE compound documents,
    so Blender cannot safely import them without a proprietary conversion
    dependency.  They are nevertheless genuine mesh sources rather than flat
    pictures: this routine validates each binary signature, archive, declared
    topology and embedded UTF-16 material vocabulary.  Orthographic/three-
    quarter preview measurements are then reconciled with full-size apparatus
    envelopes and stored as the exact metric parameters consumed by the live
    procedural builders.  The fourth OBJ source is parsed vertex-by-vertex by
    :func:`analyze_fire_truck_reference` and supplies an independent numerical
    cross-check for axle, wheel, cab and equipment-body proportions.
    """
    global _FIRE7_SUITE_ANALYSIS_CACHE
    if _FIRE7_SUITE_ANALYSIS_CACHE is not None:
        return _FIRE7_SUITE_ANALYSIS_CACHE

    required_tokens = {
        "classic_pumper": (
            "fire_eu-body red",
            "fire_eu-glass",
            "fire eu-tire",
            "fire eu-alu",
        ),
        "modern_ladder_engine": (
            "AM98_006_fire_us_carpaint",
            "AM98_006_fire_us_ladder",
            "AM98_006_fire_us_gauges",
            "AM98_006_fire_us_windows",
            "AM98_006_fire_us_tire_fr",
        ),
        "rapid_rescue": (
            "fire_big_usa-body",
            "fire_big_usa-glass",
            "fire_big_usa-tire",
            "fire_big_usa-alu",
        ),
    }
    source_records = {}
    for variant, source in FIRE7_MESH_SOURCES.items():
        archive = source["archive"]
        mesh = source["mesh"]
        previews = source["preview_files"]
        if not archive.is_file() or archive.stat().st_size < 500_000:
            raise FileNotFoundError(f"Missing detailed fire-truck archive: {archive}")
        if not mesh.is_file() or mesh.stat().st_size < 4_000_000:
            raise FileNotFoundError(
                f"Missing extracted detailed fire-truck mesh: {mesh}"
            )
        mesh_bytes = mesh.read_bytes()
        if not mesh_bytes.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise RuntimeError(f"Expected a 3ds Max compound-document mesh: {mesh}")
        matched_tokens = []
        for token in required_tokens[variant]:
            if token.encode("utf-16le") not in mesh_bytes:
                raise RuntimeError(
                    f"Mesh {source['model_id']} lacks material landmark {token!r}"
                )
            matched_tokens.append(token)
        preview_records = []
        for preview in previews:
            if not preview.is_file() or preview.stat().st_size < 20_000:
                raise FileNotFoundError(f"Missing detailed mesh preview: {preview}")
            preview_records.append(
                {
                    "file": preview.name,
                    "bytes": preview.stat().st_size,
                    "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
                }
            )
        source_records[variant] = {
            "model_id": source["model_id"],
            "title": source["title"],
            "download_page": source["page"],
            "published_format": source["published_format"],
            "published_vertices": source["published_vertices"],
            "published_polygons": source["published_polygons"],
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "mesh_bytes": mesh.stat().st_size,
            "mesh_sha256": hashlib.sha256(mesh_bytes).hexdigest(),
            "mesh_signature": "OLE Compound Document / Autodesk 3ds Max",
            "embedded_material_landmarks": matched_tokens,
            "preview_evidence": preview_records,
            "derived_programmatic_parameters": source["calibration"],
            "render_geometry": False,
        }

    obj_analysis = analyze_fire_truck_reference()
    _FIRE7_SUITE_ANALYSIS_CACHE = {
        "method": (
            "four-model reverse-engineering suite: direct OBJ group/bounds parsing plus "
            "three high-detail MAX compound meshes validated by topology metadata, "
            "embedded material vocabulary and multi-view silhouette calibration"
        ),
        "source_count": 4,
        "total_published_vertices": sum(
            source["published_vertices"] for source in FIRE7_MESH_SOURCES.values()
        )
        + obj_analysis["source"]["obj_vertex_count"],
        "total_published_polygons": sum(
            source["published_polygons"] for source in FIRE7_MESH_SOURCES.values()
        )
        + obj_analysis["source"]["obj_face_count"],
        "sources": source_records,
        "direct_obj_crosscheck": obj_analysis,
        "render_policy": {
            "downloaded_mesh_objects_imported": 0,
            "downloaded_mesh_faces_rendered": 0,
            "all_output_geometry": "live source-generated programmable Blender geometry",
        },
    }
    return _FIRE7_SUITE_ANALYSIS_CACHE


def collection(
    name: str, parent=None, role="procedural_collection", asset_id=None, variant=None
):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    coll["c2w_schema_version"] = SCHEMA_VERSION
    coll["c2w_role"] = role
    coll["c2w_generator"] = Path(__file__).name
    coll["c2w_source_geometry"] = "procedural"
    if asset_id:
        coll["c2w_asset_id"] = asset_id
    if variant:
        coll["c2w_variant"] = variant
    return coll


def new_context(parent, name, variant, asset_id, category, origin, yaw):
    coll = collection(name, parent, f"{category}_asset", asset_id, variant)
    anchor = bpy.data.objects.new(PREFIX + f"{category}:{variant}:asset_root", None)
    coll.objects.link(anchor)
    anchor.location = origin
    anchor.rotation_euler[2] = yaw
    ctx = BuildContext(coll, anchor, variant, asset_id, category)
    tag(anchor, f"{category}_root", ctx)
    anchor["c2w_role"] = "procedural_asset_root"
    anchor["c2w_external_blend_inputs"] = 0
    return ctx


def tag(obj, semantic: str, ctx: BuildContext | None = None, detail=False):
    obj["c2w_schema_version"] = SCHEMA_VERSION
    obj["c2w_role"] = "procedural_component"
    obj["c2w_semantic"] = semantic
    obj["c2w_generator"] = Path(__file__).name
    obj["c2w_source_geometry"] = "procedural"
    if ctx is not None:
        obj["c2w_asset_id"] = ctx.asset_id
        obj["c2w_variant"] = ctx.variant
        obj["c2w_asset_category"] = ctx.category
        if ctx.category == "fire_truck":
            obj["c2w_truck_variant"] = ctx.variant
        elif ctx.category == "ambulance":
            obj["c2w_ambulance_variant"] = ctx.variant
        elif ctx.category == "fire_station":
            obj["c2w_station_variant"] = ctx.variant
    if detail:
        obj["c2w_quality_detail"] = True
    return obj


def _parent_local(obj, ctx: BuildContext | None, location, rotation=(0.0, 0.0, 0.0)):
    if ctx is not None:
        obj.parent = ctx.anchor
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def _set_socket(shader, names, value):
    for name in names:
        if name in shader.inputs:
            shader.inputs[name].default_value = value
            return


def pbr(
    name,
    color,
    roughness=0.5,
    metallic=0.0,
    transmission=0.0,
    emission=None,
    emission_strength=0.0,
    coat=0.0,
    alpha=1.0,
):
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    mat.diffuse_color = (*color, alpha)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    _set_socket(shader, ("Roughness",), roughness)
    _set_socket(shader, ("Metallic",), metallic)
    _set_socket(shader, ("Transmission Weight", "Transmission"), transmission)
    _set_socket(shader, ("Coat Weight", "Clearcoat"), coat)
    if emission:
        _set_socket(shader, ("Emission Color", "Emission"), (*emission, 1.0))
        _set_socket(shader, ("Emission Strength",), emission_strength)
    if alpha < 1.0:
        _set_socket(shader, ("Alpha",), alpha)
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
    mat["c2w_pbr"] = True
    return mat


def noise_material(
    name,
    dark,
    light,
    roughness=0.75,
    scale=6.0,
    detail=5.0,
    bump_strength=0.18,
    metallic=0.0,
):
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    geom = nodes.new("ShaderNodeNewGeometry")
    coarse = nodes.new("ShaderNodeTexNoise")
    coarse.noise_dimensions = "3D"
    coarse.inputs["Scale"].default_value = scale
    coarse.inputs["Detail"].default_value = detail
    coarse.inputs["Roughness"].default_value = 0.68
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    micro.inputs["Scale"].default_value = scale * 14
    micro.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.045
    links.new(geom.outputs["Position"], coarse.inputs["Vector"])
    links.new(geom.outputs["Position"], micro.inputs["Vector"])
    links.new(coarse.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "world_scale_noise_micro_bump"
    return mat


def automotive_paint(name, dark, light, roughness=0.20, coat=0.52):
    """Layered apparatus paint with subtle flake and non-uniform clear coat.

    Flat primary-colour shaders are a major source of miniature/toy read.  The
    two spatial frequencies here remain restrained at vehicle scale: the broad
    field only breaks perfect uniformity, while the micro field affects the
    highlight rather than turning the bodywork into a noisy surface.
    """
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = 0.035
    _set_socket(shader, ("Coat Weight", "Clearcoat"), coat)
    _set_socket(shader, ("Coat Roughness", "Clearcoat Roughness"), 0.115)
    geom = nodes.new("ShaderNodeNewGeometry")
    broad = nodes.new("ShaderNodeTexNoise")
    broad.noise_dimensions = "3D"
    broad.inputs["Scale"].default_value = 7.5
    broad.inputs["Detail"].default_value = 4.0
    broad.inputs["Roughness"].default_value = 0.64
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    flake = nodes.new("ShaderNodeTexNoise")
    flake.noise_dimensions = "3D"
    flake.inputs["Scale"].default_value = 285.0
    flake.inputs["Detail"].default_value = 2.0
    flake.inputs["Roughness"].default_value = 0.48
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.026
    bump.inputs["Distance"].default_value = 0.006
    links.new(geom.outputs["Position"], broad.inputs["Vector"])
    links.new(geom.outputs["Position"], flake.inputs["Vector"])
    links.new(broad.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(flake.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "layered_automotive_clearcoat_microflake"
    return mat


def brick_material(name, brick_a, brick_b, mortar):
    full = PREFIX + "mat:" + name
    existing = bpy.data.materials.get(full)
    if existing:
        return existing
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.79
    geom = nodes.new("ShaderNodeNewGeometry")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    horizontal = nodes.new("ShaderNodeMath")
    horizontal.operation = "ADD"
    combine = nodes.new("ShaderNodeCombineXYZ")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.inputs["Color1"].default_value = (*brick_a, 1)
    brick.inputs["Color2"].default_value = (*brick_b, 1)
    brick.inputs["Mortar"].default_value = (*mortar, 1)
    brick.inputs["Scale"].default_value = 2.2
    brick.inputs["Mortar Size"].default_value = 0.027
    brick.inputs["Brick Width"].default_value = 0.58
    brick.inputs["Row Height"].default_value = 0.20
    grain = nodes.new("ShaderNodeTexNoise")
    grain.noise_dimensions = "3D"
    grain.inputs["Scale"].default_value = 42
    grain.inputs["Detail"].default_value = 4
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.13
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.42
    bump.inputs["Distance"].default_value = 0.035
    links.new(geom.outputs["Position"], sep.inputs["Vector"])
    links.new(sep.outputs["X"], horizontal.inputs[0])
    links.new(sep.outputs["Y"], horizontal.inputs[1])
    links.new(horizontal.outputs["Value"], combine.inputs["X"])
    links.new(sep.outputs["Z"], combine.inputs["Y"])
    links.new(combine.outputs["Vector"], brick.inputs["Vector"])
    links.new(geom.outputs["Position"], grain.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(grain.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    mat["c2w_pbr"] = True
    mat["c2w_procedural_surface"] = "running_bond_brick_with_recessed_mortar"
    return mat


def make_materials():
    return {
        # Paint values are intentionally less saturated than the first pass.
        # Clearcoat and restrained micro-variation produce full-size appliance
        # paint instead of the flat primary colours associated with toy models.
        "red": automotive_paint(
            "apparatus_red", (0.205, 0.006, 0.008), (0.405, 0.018, 0.021), 0.155, 0.68
        ),
        "red_dark": automotive_paint(
            "apparatus_shadow_red",
            (0.055, 0.002, 0.003),
            (0.135, 0.006, 0.008),
            0.22,
            0.46,
        ),
        "ambulance_white": automotive_paint(
            "ambulance_warm_white", (0.61, 0.63, 0.61), (0.90, 0.92, 0.88), 0.17, 0.64
        ),
        "ambulance_red": automotive_paint(
            "ambulance_burgundy_red",
            (0.29, 0.004, 0.007),
            (0.50, 0.010, 0.014),
            0.18,
            0.60,
        ),
        "ems_blue": automotive_paint(
            "ems_star_blue", (0.008, 0.075, 0.24), (0.015, 0.19, 0.48), 0.20, 0.42
        ),
        "shutter_aluminum": noise_material(
            "anodized_rolling_shutter",
            (0.285, 0.315, 0.335),
            (0.455, 0.49, 0.51),
            0.37,
            52,
            2,
            0.012,
            0.72,
        ),
        "shutter_aluminum_alt": noise_material(
            "anodized_rolling_shutter_subtle_batch",
            (0.265, 0.292, 0.310),
            (0.405, 0.438, 0.455),
            0.40,
            47,
            2,
            0.014,
            0.70,
        ),
        "shutter_shadow": noise_material(
            "rolling_shutter_interlock_shadow",
            (0.032, 0.038, 0.043),
            (0.075, 0.086, 0.094),
            0.61,
            56,
            2,
            0.018,
            0.30,
        ),
        "shutter_weathering": pbr(
            "rolling_shutter_service_weathering",
            (0.115, 0.125, 0.130),
            0.96,
            alpha=0.11,
        ),
        "red_clad": noise_material(
            "architectural_red_cladding",
            (0.39, 0.010, 0.014),
            (0.53, 0.018, 0.021),
            0.42,
            5,
            3,
            0.035,
            0.12,
        ),
        "cream": pbr("heritage_cream", (0.78, 0.71, 0.55), 0.30, coat=0.28),
        "white": automotive_paint(
            "appliance_white", (0.76, 0.79, 0.78), (0.91, 0.93, 0.90), 0.21, 0.48
        ),
        "white_emit": pbr(
            "sign_white",
            (0.96, 0.97, 0.95),
            0.22,
            emission=(1, 0.96, 0.87),
            emission_strength=1.7,
        ),
        "yellow_reflect": pbr(
            "lime_yellow_reflective",
            (0.98, 0.79, 0.03),
            0.23,
            emission=(1, 0.55, 0.015),
            emission_strength=0.24,
            coat=0.25,
        ),
        "road_yellow": pbr("road_yellow", (0.90, 0.55, 0.015), 0.66),
        "road_white": pbr("road_white", (0.86, 0.86, 0.79), 0.66),
        "black": pbr("powder_coated_black", (0.012, 0.014, 0.016), 0.42, metallic=0.18),
        "rubber": noise_material(
            "reinforced_tire_rubber",
            (0.0045, 0.0048, 0.0050),
            (0.018, 0.019, 0.019),
            0.88,
            38,
            4,
            0.045,
        ),
        "interior": noise_material(
            "cab_charcoal_interior",
            (0.018, 0.020, 0.023),
            (0.07, 0.072, 0.073),
            0.72,
            13,
            4,
            0.13,
        ),
        "seat": noise_material(
            "firefighter_seat_fabric",
            (0.045, 0.050, 0.055),
            (0.13, 0.14, 0.14),
            0.84,
            28,
            5,
            0.15,
        ),
        "aluminum": noise_material(
            "brushed_apparatus_aluminum",
            (0.43, 0.46, 0.48),
            (0.55, 0.58, 0.59),
            0.24,
            11,
            3,
            0.025,
            0.86,
        ),
        "diamond": noise_material(
            "diamond_plate_aluminum",
            (0.38, 0.41, 0.42),
            (0.52, 0.55, 0.56),
            0.29,
            23,
            3,
            0.055,
            0.82,
        ),
        "steel": noise_material(
            "galvanized_steel",
            (0.33, 0.36, 0.37),
            (0.45, 0.48, 0.49),
            0.36,
            18,
            3,
            0.035,
            0.72,
        ),
        "chrome": pbr(
            "polished_chrome", (0.62, 0.65, 0.66), 0.09, metallic=0.96, coat=0.32
        ),
        "glass": pbr(
            "laminated_vehicle_glass",
            (0.025, 0.070, 0.092),
            0.115,
            transmission=0.46,
            coat=0.62,
            alpha=0.61,
        ),
        "glass_dark": pbr(
            "smoked_vehicle_glass",
            (0.010, 0.027, 0.038),
            0.12,
            transmission=0.22,
            coat=0.58,
            alpha=0.72,
        ),
        "architectural_glass": pbr(
            "architectural_low_e_glass",
            (0.040, 0.115, 0.145),
            0.13,
            transmission=0.42,
            coat=0.56,
            alpha=0.58,
        ),
        "headlamp": pbr(
            "faceted_headlamp",
            (0.73, 0.79, 0.77),
            0.18,
            transmission=0.34,
            emission=(1, 0.91, 0.68),
            emission_strength=0.28,
            coat=0.38,
        ),
        "red_lens": pbr(
            "red_emergency_lens",
            (0.65, 0.002, 0.004),
            0.16,
            transmission=0.24,
            emission=(1, 0.006, 0.004),
            emission_strength=0.85,
            coat=0.34,
        ),
        "blue_lens": pbr(
            "blue_emergency_lens",
            (0.004, 0.08, 0.69),
            0.15,
            transmission=0.25,
            emission=(0.005, 0.12, 1),
            emission_strength=0.75,
            coat=0.34,
        ),
        "amber": pbr(
            "amber_lens",
            (0.96, 0.27, 0.005),
            0.16,
            transmission=0.26,
            emission=(1, 0.16, 0.004),
            emission_strength=0.55,
            coat=0.31,
        ),
        "gauge": pbr("instrument_face", (0.018, 0.020, 0.021), 0.18, coat=0.28),
        "gauge_white": pbr(
            "instrument_marking",
            (0.89, 0.91, 0.88),
            0.28,
            emission=(0.7, 0.78, 0.70),
            emission_strength=0.2,
        ),
        "lcd": pbr(
            "apparatus_lcd",
            (0.015, 0.19, 0.20),
            0.18,
            emission=(0.03, 0.85, 0.71),
            emission_strength=1.1,
            coat=0.3,
        ),
        "hose_yellow": noise_material(
            "woven_attack_hose_yellow",
            (0.42, 0.22, 0.012),
            (0.92, 0.63, 0.035),
            0.72,
            31,
            4,
            0.12,
        ),
        "hose_red": noise_material(
            "woven_supply_hose_red",
            (0.30, 0.006, 0.008),
            (0.77, 0.018, 0.018),
            0.74,
            30,
            4,
            0.12,
        ),
        "hose_canvas": noise_material(
            "woven_supply_hose_canvas",
            (0.35, 0.29, 0.19),
            (0.72, 0.64, 0.46),
            0.79,
            35,
            4,
            0.13,
        ),
        "brick": brick_material(
            "black_engineered_brick",
            (0.012, 0.014, 0.016),
            (0.045, 0.039, 0.038),
            (0.19, 0.18, 0.17),
        ),
        "brick_red": brick_material(
            "deep_red_brick",
            (0.20, 0.018, 0.014),
            (0.42, 0.055, 0.035),
            (0.42, 0.38, 0.33),
        ),
        "precast": noise_material(
            "pale_prairie_precast",
            (0.58, 0.55, 0.49),
            (0.80, 0.77, 0.69),
            0.75,
            4,
            6,
            0.13,
        ),
        "stone": noise_material(
            "split_face_stone",
            (0.29, 0.27, 0.24),
            (0.57, 0.54, 0.48),
            0.86,
            3.2,
            7,
            0.33,
        ),
        "gray_clad": noise_material(
            "galvalume_wall_panel",
            (0.25, 0.28, 0.30),
            (0.39, 0.42, 0.43),
            0.48,
            10,
            3,
            0.030,
            0.50,
        ),
        "roof": noise_material(
            "standing_seam_roof",
            (0.11, 0.13, 0.15),
            (0.17, 0.19, 0.20),
            0.47,
            15,
            3,
            0.030,
            0.62,
        ),
        "concrete": noise_material(
            "broom_finished_concrete",
            (0.43, 0.44, 0.42),
            (0.52, 0.52, 0.48),
            0.82,
            5.0,
            4,
            0.07,
        ),
        "concrete_light": noise_material(
            "light_precast_concrete",
            (0.62, 0.62, 0.58),
            (0.72, 0.70, 0.65),
            0.75,
            6.0,
            4,
            0.055,
        ),
        "asphalt": noise_material(
            "dense_graded_asphalt",
            (0.022, 0.025, 0.028),
            (0.052, 0.055, 0.055),
            0.91,
            12.0,
            4,
            0.09,
        ),
        "urban_ground": noise_material(
            "distant_municipal_ground",
            (0.20, 0.215, 0.22),
            (0.31, 0.325, 0.32),
            0.92,
            5.5,
            5,
            0.070,
        ),
        "stain": pbr(
            "weathered_concrete_stain", (0.075, 0.064, 0.052), 0.91, alpha=0.28
        ),
        "rust": noise_material(
            "service_steel_oxidation",
            (0.16, 0.028, 0.008),
            (0.46, 0.11, 0.025),
            0.82,
            19,
            5,
            0.19,
            0.08,
        ),
        "paver": noise_material(
            "entry_paver", (0.34, 0.25, 0.22), (0.60, 0.48, 0.40), 0.86, 5, 6, 0.20
        ),
        "soil": noise_material(
            "mulched_planting_soil",
            (0.035, 0.019, 0.009),
            (0.16, 0.075, 0.025),
            0.96,
            9,
            5,
            0.28,
        ),
        "grass": noise_material(
            "living_turf", (0.012, 0.105, 0.022), (0.08, 0.29, 0.055), 0.94, 6, 7, 0.30
        ),
        "leaf": noise_material(
            "broadleaf_canopy",
            (0.012, 0.095, 0.022),
            (0.10, 0.34, 0.065),
            0.80,
            17,
            5,
            0.14,
        ),
        "leaf_light": noise_material(
            "sunlit_broadleaf",
            (0.035, 0.16, 0.028),
            (0.22, 0.46, 0.08),
            0.77,
            18,
            5,
            0.13,
        ),
        "bark": noise_material(
            "mature_tree_bark",
            (0.055, 0.026, 0.012),
            (0.23, 0.10, 0.037),
            0.91,
            23,
            5,
            0.30,
        ),
        "locker": pbr("turnout_locker_red", (0.42, 0.012, 0.014), 0.40, metallic=0.31),
        "wood": noise_material(
            "sealed_station_bench",
            (0.20, 0.075, 0.022),
            (0.48, 0.22, 0.065),
            0.56,
            5,
            6,
            0.10,
        ),
        "sealant": pbr("architectural_joint_sealant", (0.038, 0.041, 0.043), 0.70),
        "concrete_joint": pbr("weathered_concrete_sawcut", (0.145, 0.142, 0.132), 0.88),
        "plastic": noise_material(
            "moulded_apparatus_polymer",
            (0.018, 0.021, 0.023),
            (0.058, 0.063, 0.065),
            0.58,
            46,
            3,
            0.045,
        ),
        "silver_reflect": pbr(
            "retroreflective_silver",
            (0.72, 0.75, 0.73),
            0.18,
            emission=(0.18, 0.20, 0.18),
            emission_strength=0.12,
            coat=0.45,
        ),
        "source_livery": pbr(
            "reference_mesh_yellow_apparatus_livery",
            (0.92, 0.70, 0.025),
            0.24,
            emission=(0.35, 0.22, 0.008),
            emission_strength=0.10,
            coat=0.30,
        ),
        "primer": pbr(
            "chassis_oxide_primer", (0.085, 0.020, 0.012), 0.57, metallic=0.12
        ),
        "reflector": pbr(
            "microprismatic_reflector",
            (0.74, 0.77, 0.72),
            0.15,
            emission=(0.35, 0.38, 0.32),
            emission_strength=0.18,
            coat=0.52,
        ),
        "brass": pbr(
            "machined_fire_service_brass",
            (0.48, 0.23, 0.045),
            0.19,
            metallic=0.86,
            coat=0.16,
        ),
    }


def _shared_mesh(key, operator):
    mesh = SHARED_MESHES.get(key)
    if mesh is not None:
        return mesh
    operator()
    source = bpy.context.active_object
    mesh = source.data
    mesh.name = PREFIX + "shared_mesh:" + str(len(SHARED_MESHES)).zfill(4)
    bpy.data.objects.remove(source, do_unlink=True)
    SHARED_MESHES[key] = mesh
    return mesh


def box(
    ctx,
    name,
    loc,
    dims,
    material,
    bevel=0.025,
    rotation=(0, 0, 0),
    semantic="structural_component",
):
    key = ("cube", material.name_full)
    mesh = _shared_mesh(key, lambda: bpy.ops.mesh.primitive_cube_add(size=1))
    if not mesh.materials:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    obj.scale = dims
    if bevel > 0:
        mod = obj.modifiers.new("manufactured_edge_radius", "BEVEL")
        mod.width = min(bevel, min(dims) * 0.35)
        mod.segments = 3
        mod.limit_method = "ANGLE"
    return tag(obj, semantic, ctx, bevel > 0)


def rounded_box(
    ctx,
    name,
    loc,
    dims,
    material,
    radius=0.08,
    rotation=(0, 0, 0),
    semantic="formed_panel",
    segments=4,
):
    """Create a dimensionally correct radiused solid with unapplied scale = 1.

    The generic instanced ``box`` is ideal for repeated small fabrication, but
    its non-uniform object scale makes large cab corners look model-like.  This
    unique mesh is reserved for primary body panels and exterior architecture.
    """
    dx, dy, dz = (float(value) / 2 for value in dims)
    verts = [
        (-dx, -dy, -dz),
        (dx, -dy, -dz),
        (dx, dy, -dz),
        (-dx, dy, -dz),
        (-dx, -dy, dz),
        (dx, -dy, dz),
        (dx, dy, dz),
        (-dx, dy, dz),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    if radius > 0:
        mod = obj.modifiers.new("production_panel_radius", "BEVEL")
        mod.width = min(radius, min(dims) * 0.47)
        mod.segments = max(2, int(segments))
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    return tag(obj, semantic, ctx, True)


def cylinder(
    ctx,
    name,
    loc,
    radius,
    depth,
    material,
    vertices=32,
    rotation=(0, 0, 0),
    semantic="manufactured_cylinder",
    bevel=0.0,
):
    key = ("cylinder", int(vertices), material.name_full)
    mesh = _shared_mesh(
        key,
        lambda: bpy.ops.mesh.primitive_cylinder_add(
            vertices=vertices, radius=1, depth=1
        ),
    )
    if not mesh.materials:
        mesh.materials.append(material)
    for poly in mesh.polygons:
        if len(poly.vertices) == 4:
            poly.use_smooth = True
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    obj.scale = (radius, radius, depth)
    if bevel > 0:
        mod = obj.modifiers.new("machined_edge", "BEVEL")
        mod.width = min(bevel, radius * 0.18)
        mod.segments = 2
    return tag(obj, semantic, ctx, True)


def sphere(
    ctx, name, loc, dims, material, semantic="formed_component", segments=20, rings=12
):
    key = ("sphere", int(segments), int(rings), material.name_full)
    mesh = _shared_mesh(
        key,
        lambda: bpy.ops.mesh.primitive_uv_sphere_add(
            segments=segments, ring_count=rings, radius=1
        ),
    )
    if not mesh.materials:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc)
    obj.scale = dims
    for poly in mesh.polygons:
        poly.use_smooth = True
    return tag(obj, semantic, ctx, True)


def irregular_canopy(
    ctx, name, loc, dims, material, shape_index=0, semantic="botanical_leaf_canopy"
):
    """Faceted-but-organic crown mesh with a non-spherical silhouette."""
    key = ("irregular_canopy", int(shape_index) % 11, material.name_full)
    mesh = SHARED_MESHES.get(key)
    if mesh is None:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1)
        source = bpy.context.active_object
        mesh = source.data
        mesh.name = (
            PREFIX + "shared_irregular_canopy:" + str(len(SHARED_MESHES)).zfill(4)
        )
        rng = random.Random(71000 + int(shape_index) % 11)
        for index, vertex in enumerate(mesh.vertices):
            direction = vertex.co.normalized()
            wave = 0.12 * math.sin(direction.x * 5.1 + direction.z * 7.3)
            wave += 0.08 * math.cos(direction.y * 6.7 - direction.x * 3.8)
            vertex.co *= max(0.72, 1.0 + wave + rng.uniform(-0.09, 0.09))
        mesh.materials.append(material)
        for poly in mesh.polygons:
            poly.use_smooth = True
        bpy.data.objects.remove(source, do_unlink=True)
        SHARED_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, (0.0, 0.0, math.radians((shape_index * 37) % 180)))
    obj.scale = dims
    return tag(obj, semantic, ctx, True)


def torus(
    ctx,
    name,
    loc,
    major_radius,
    minor_radius,
    material,
    rotation=(0, 0, 0),
    semantic="formed_ring",
    major_segments=32,
    minor_segments=8,
):
    key = (
        "torus",
        round(major_radius, 4),
        round(minor_radius, 4),
        int(major_segments),
        int(minor_segments),
        material.name_full,
    )
    mesh = SHARED_MESHES.get(key)
    if mesh is None:
        verts, faces = [], []
        for i in range(major_segments):
            a = 2 * math.pi * i / major_segments
            for j in range(minor_segments):
                b = 2 * math.pi * j / minor_segments
                r = major_radius + minor_radius * math.cos(b)
                verts.append(
                    (r * math.cos(a), r * math.sin(a), minor_radius * math.sin(b))
                )
        for i in range(major_segments):
            ni = (i + 1) % major_segments
            for j in range(minor_segments):
                nj = (j + 1) % minor_segments
                faces.append(
                    (
                        i * minor_segments + j,
                        ni * minor_segments + j,
                        ni * minor_segments + nj,
                        i * minor_segments + nj,
                    )
                )
        mesh = bpy.data.meshes.new(
            PREFIX + "shared_torus:" + str(len(SHARED_MESHES)).zfill(4)
        )
        mesh.from_pydata(verts, [], faces)
        mesh.materials.append(material)
        for poly in mesh.polygons:
            poly.use_smooth = True
        SHARED_MESHES[key] = mesh
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    return tag(obj, semantic, ctx, True)


def beam(
    ctx, name, start, end, radius, material, semantic="structural_member", vertices=16
):
    a, b = Vector(start), Vector(end)
    delta = b - a
    obj = cylinder(
        ctx,
        name,
        (a + b) * 0.5,
        radius,
        delta.length,
        material,
        vertices,
        semantic=semantic,
        bevel=min(0.008, radius * 0.16),
    )
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return obj


def curve_tube(
    ctx, name, points, radius, material, semantic="flexible_hose", cyclic=False
):
    curve = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.use_fill_caps = True
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, co in zip(spline.bezier_points, points):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    return tag(obj, semantic, ctx, True)


def profile_extrude_x(
    ctx,
    name,
    points_yz,
    width,
    material,
    semantic="formed_body_shell",
    bevel=0.03,
    open_edges=(),
):
    n = len(points_yz)
    verts = []
    for x in (-width / 2, width / 2):
        verts.extend((x, y, z) for y, z in points_yz)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for i in range(n):
        j = (i + 1) % n
        if i not in open_edges:
            faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel > 0:
        mod = obj.modifiers.new("formed_shell_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    return tag(obj, semantic, ctx, True)


def formed_shutter_slat(ctx, name, x, y, z, width, pitch, material):
    """Extrude one hooked double-wall coiling-door slat across an opening."""
    half = pitch * 0.5
    # Camera-facing Y is negative.  Crown, lower hook and rear return form a
    # closed six-sided extrusion rather than a row of rounded cuboids.
    profile = [
        (y + 0.026, z - half * 0.92),
        (y - 0.041, z - half * 0.82),
        (y - 0.061, z - half * 0.56),
        (y - 0.046, z + half * 0.56),
        (y - 0.014, z + half * 0.91),
        (y + 0.026, z + half * 0.92),
    ]
    obj = profile_extrude_x(
        ctx,
        name,
        profile,
        width,
        material,
        semantic="rolling_shutter_slat",
        bevel=0.004,
    )
    obj.location.x = x
    obj["c2w_slat_profile"] = "double_wall_convex_crown_with_hooked_interlock"
    obj["c2w_slat_pitch_m"] = round(pitch, 5)
    return obj


def lofted_vehicle_shell(
    ctx,
    name,
    sections,
    material,
    semantic="vehicle_lofted_shell",
    corner_steps=5,
    bevel=0.018,
):
    """Create a watertight longitudinal automotive shell from real sections.

    Each section is ``(y, half_width_bottom, half_width_top, z_bottom, z_top,
    corner_radius)``.  Unlike scaled boxes, this preserves changing track,
    tumblehome, roof crown and nose taper in one continuous manufactured skin.
    """
    if len(sections) < 2:
        raise ValueError("lofted_vehicle_shell requires at least two sections")
    corner_steps = max(2, int(corner_steps))

    def section_ring(section):
        y, half_bottom, half_top, z_bottom, z_top, radius = map(float, section)
        radius = min(
            radius, half_bottom * 0.45, half_top * 0.45, (z_top - z_bottom) * 0.45
        )
        corners = (
            (half_bottom - radius, z_bottom + radius, -math.pi / 2, 0.0),
            (half_top - radius, z_top - radius, 0.0, math.pi / 2),
            (-half_top + radius, z_top - radius, math.pi / 2, math.pi),
            (-half_bottom + radius, z_bottom + radius, math.pi, 3 * math.pi / 2),
        )
        points = []
        for cx, cz, start, stop in corners:
            for step in range(corner_steps):
                factor = step / (corner_steps - 1)
                angle = start + (stop - start) * factor
                points.append(
                    (cx + radius * math.cos(angle), y, cz + radius * math.sin(angle))
                )
        return points

    rings = [section_ring(section) for section in sections]
    ring_size = len(rings[0])
    verts = [point for ring in rings for point in ring]
    faces = []
    # End caps and longitudinal quads give a genuinely closed sheet-metal form.
    faces.append(tuple(range(ring_size - 1, -1, -1)))
    last = (len(rings) - 1) * ring_size
    faces.append(tuple(last + index for index in range(ring_size)))
    for section_index in range(len(rings) - 1):
        a = section_index * ring_size
        b = (section_index + 1) * ring_size
        for point_index in range(ring_size):
            nxt = (point_index + 1) % ring_size
            faces.append((a + point_index, a + nxt, b + nxt, b + point_index))

    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel > 0:
        mod = obj.modifiers.new("automotive_panel_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    obj["c2w_section_count"] = len(sections)
    obj["c2w_cross_section_resolution"] = ring_size
    return tag(obj, semantic, ctx, True)


def annular_arch_panel(
    ctx,
    name,
    center,
    inner_radius,
    outer_radius,
    depth,
    material,
    semantic="wheel_arch_fender_panel",
    segments=32,
    bevel=0.012,
):
    """Build a watertight, sheet-metal half annulus around a road wheel.

    The earlier vehicle pass represented the fender by a single curved tube.
    Although dense, that tube had no load path into the body and therefore read
    as a floating decoration.  This helper creates the actual extruded fender
    skin: two annular faces, inner and outer returns, and closed end caps.  It is
    intentionally local-source geometry so every placed apparatus inherits the
    same physically connected wheel housing through the live factory.
    """
    cx, cy, cz = center
    inner_radius = float(inner_radius)
    outer_radius = float(outer_radius)
    if not 0 < inner_radius < outer_radius:
        raise ValueError("annular_arch_panel requires 0 < inner_radius < outer_radius")
    steps = max(12, int(segments))
    verts = []
    for x in (cx - depth / 2, cx + depth / 2):
        for radius in (inner_radius, outer_radius):
            for step in range(steps + 1):
                angle = math.pi * step / steps
                verts.append(
                    (x, cy + math.cos(angle) * radius, cz + math.sin(angle) * radius)
                )

    stride = steps + 1

    def vid(x_layer, radial_layer, step):
        return x_layer * stride * 2 + radial_layer * stride + step

    faces = []
    for step in range(steps):
        nxt = step + 1
        # Visible annular side skins.
        faces.append((vid(0, 0, step), vid(0, 0, nxt), vid(0, 1, nxt), vid(0, 1, step)))
        faces.append((vid(1, 1, step), vid(1, 1, nxt), vid(1, 0, nxt), vid(1, 0, step)))
        # Rolled inner wheel opening and outer crown returns.
        faces.append((vid(0, 0, step), vid(1, 0, step), vid(1, 0, nxt), vid(0, 0, nxt)))
        faces.append((vid(0, 1, nxt), vid(1, 1, nxt), vid(1, 1, step), vid(0, 1, step)))
    for step in (0, steps):
        faces.append(
            (vid(0, 0, step), vid(0, 1, step), vid(1, 1, step), vid(1, 0, step))
        )

    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel > 0:
        mod = obj.modifiers.new("rolled_fender_edge", "BEVEL")
        mod.width = min(bevel, (outer_radius - inner_radius) * 0.18, depth * 0.18)
        mod.segments = 2
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    return tag(obj, semantic, ctx, True)


def sloped_front_panel(
    ctx,
    name,
    points_xz,
    y_bottom,
    y_top,
    depth,
    material,
    semantic="formed_front_panel",
    bevel=0.018,
):
    """Make a tapered panel whose top edge is raked rearward in local Y.

    This is used for windshields and other front glazing where a scaled cube
    would leave a rectangular, miniature-looking silhouette.  ``points_xz``
    are supplied clockwise around the face; the helper produces a watertight
    shallow prism with a real edge thickness.
    """
    z_min = min(point[1] for point in points_xz)
    z_max = max(point[1] for point in points_xz)
    z_span = max(0.001, z_max - z_min)
    front, rear = [], []
    for x, z in points_xz:
        factor = (z - z_min) / z_span
        center_y = y_bottom + factor * (y_top - y_bottom)
        front.append((x, center_y - depth / 2, z))
        rear.append((x, center_y + depth / 2, z))
    verts = front + rear
    n = len(points_xz)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for index in range(n):
        nxt = (index + 1) % n
        faces.append((index, nxt, n + nxt, n + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel > 0:
        mod = obj.modifiers.new("laminated_panel_edge_radius", "BEVEL")
        mod.width = min(bevel, depth * 0.35)
        mod.segments = 3
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    return tag(obj, semantic, ctx, True)


def side_prism_x(
    ctx, name, points_yz, x, depth, material, semantic="formed_side_panel", bevel=0.014
):
    """Extrude a shaped panel on a vehicle side, preserving sloped window lines."""
    side_a = [(x - depth / 2, y, z) for y, z in points_yz]
    side_b = [(x + depth / 2, y, z) for y, z in points_yz]
    verts = side_a + side_b
    count = len(points_yz)
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel > 0:
        mod = obj.modifiers.new("formed_side_edge", "BEVEL")
        mod.width = min(bevel, depth * 0.32)
        mod.segments = 3
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    return tag(obj, semantic, ctx, True)


def masonry_relief_panel(
    ctx,
    name,
    center,
    width,
    height,
    depth,
    material,
    unit_width=0.39,
    unit_height=0.145,
    semantic="brick_relief_masonry",
):
    """Create thousands of bonded masonry units as one efficient mesh.

    The wall shader supplies colour, mortar and micro-bump.  This shallow face
    mesh supplies the missing parallax, irregular course shadows and real edge
    highlights that remain visible in oblique aerial views.
    """
    cx, front_y, cz = center
    verts, faces = [], []

    def add_unit(x0, x1, z0, z1, unit_depth):
        gap_x = min(0.015, (x1 - x0) * 0.12)
        gap_z = min(0.012, (z1 - z0) * 0.16)
        x0 += gap_x / 2
        x1 -= gap_x / 2
        z0 += gap_z / 2
        z1 -= gap_z / 2
        if x1 <= x0 or z1 <= z0:
            return
        y0, y1 = front_y - unit_depth, front_y
        base = len(verts)
        verts.extend(
            (
                (x0, y0, z0),
                (x1, y0, z0),
                (x1, y1, z0),
                (x0, y1, z0),
                (x0, y0, z1),
                (x1, y0, z1),
                (x1, y1, z1),
                (x0, y1, z1),
            )
        )
        faces.extend(
            (
                (base + 0, base + 4, base + 5, base + 1),
                (base + 1, base + 5, base + 6, base + 2),
                (base + 2, base + 6, base + 7, base + 3),
                (base + 3, base + 7, base + 4, base + 0),
                (base + 4, base + 7, base + 6, base + 5),
                (base + 0, base + 1, base + 2, base + 3),
            )
        )

    left, right = cx - width / 2, cx + width / 2
    bottom, top = cz - height / 2, cz + height / 2
    rows = max(1, int(math.ceil(height / unit_height)))
    for row in range(rows):
        z0 = bottom + row * unit_height
        z1 = min(top, z0 + unit_height)
        offset = unit_width * 0.5 if row % 2 else 0.0
        x = left - offset
        while x < right:
            x0, x1 = max(left, x), min(right, x + unit_width)
            # Tiny deterministic depth differences keep long courses from
            # reflecting as one mathematically perfect plane.
            relief = depth * (1.0 + 0.10 * math.sin(row * 2.31 + x * 1.17))
            add_unit(x0, x1, z0, z1, relief)
            x += unit_width
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    obj["c2w_masonry_unit_count"] = len(verts) // 8
    return tag(obj, semantic, ctx, True)


def scale_asset_collection(asset_collection, scale, door_alignment):
    """Scale a placed asset through its independent source-generated root."""
    roots = [
        obj
        for obj in asset_collection.objects
        if obj.get("c2w_role") == "procedural_asset_root"
    ]
    if len(roots) != 1:
        raise RuntimeError(
            f"Expected one pose root in {asset_collection.name}, found {len(roots)}"
        )
    anchor = roots[0]
    anchor.scale = (scale, scale, scale)
    anchor["c2w_scene_scale"] = scale
    anchor["c2w_door_alignment"] = door_alignment
    asset_collection["c2w_scene_scale"] = scale
    asset_collection["c2w_door_alignment"] = door_alignment
    return anchor


def text_front(
    ctx,
    name,
    body,
    loc,
    size,
    material,
    extrude=0.035,
    align="CENTER",
    semantic="signage",
):
    curve = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = min(0.012, extrude * 0.20)
    if Path(FONT_BOLD).is_file():
        curve.font = bpy.data.fonts.load(FONT_BOLD, check_existing=True)
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, (math.pi / 2, 0, 0))
    return tag(obj, semantic, ctx, True)


def text_side(
    ctx,
    name,
    body,
    loc,
    size,
    material,
    side=1,
    extrude=0.018,
    semantic="apparatus_marking",
):
    curve = bpy.data.curves.new(PREFIX + name + ":font", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = 0.004
    if Path(FONT_BOLD).is_file():
        curve.font = bpy.data.fonts.load(FONT_BOLD, check_existing=True)
    curve.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, curve)
    ctx.collection.objects.link(obj)
    rotation = (math.pi / 2, 0, math.pi / 2 if side > 0 else -math.pi / 2)
    _parent_local(obj, ctx, loc, rotation)
    return tag(obj, semantic, ctx, True)


def area_light(
    ctx,
    name,
    loc,
    energy,
    size,
    color=(1.0, 0.91, 0.73),
    rotation=(0, 0, 0),
    semantic="station_light",
):
    data = bpy.data.lights.new(PREFIX + name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size[0]
    data.size_y = size[1]
    data.color = color
    obj = bpy.data.objects.new(PREFIX + name, data)
    ctx.collection.objects.link(obj)
    _parent_local(obj, ctx, loc, rotation)
    return tag(obj, semantic, ctx, True)


# ---------------------------------------------------------------------------
# Independently placeable fire apparatus


def build_wheel(ctx, name, center, side, M, radius=0.58, width=0.31, dual=False):
    """Build a manufactured wheel down to tread, brake, hub and lug geometry."""
    x, y, z = center
    axis_rotation = (0, math.pi / 2, 0)
    torus(
        ctx,
        name + ":tire",
        (x, y, z),
        radius - width * 0.48,
        width * 0.48,
        M["rubber"],
        axis_rotation,
        "apparatus_tire",
        64,
        16,
    )
    if dual:
        inner_x = x - side * 0.27
        inner_width = width * 0.70
        torus(
            ctx,
            name + ":inner_dual_tire",
            (inner_x, y, z),
            radius * 0.985 - inner_width * 0.48,
            inner_width * 0.48,
            M["rubber"],
            axis_rotation,
            "apparatus_dual_tire",
            64,
            16,
        )
    outer_x = x + side * (width * 0.52 + 0.012)
    cylinder(
        ctx,
        name + ":rim_well",
        (outer_x - side * 0.018, y, z),
        radius * 0.68,
        0.052,
        M["black"],
        56,
        axis_rotation,
        "wheel_rim_well",
        0.012,
    )
    cylinder(
        ctx,
        name + ":rim",
        (outer_x, y, z),
        radius * 0.61,
        0.055,
        M["aluminum"],
        56,
        axis_rotation,
        "wheel_rim",
        0.012,
    )
    cylinder(
        ctx,
        name + ":brake_disc",
        (outer_x - side * 0.040, y, z),
        radius * 0.44,
        0.035,
        M["steel"],
        48,
        axis_rotation,
        "brake_disc",
        0.008,
    )
    cylinder(
        ctx,
        name + ":hub",
        (outer_x + side * 0.035, y, z),
        radius * 0.19,
        0.075,
        M["chrome"],
        36,
        axis_rotation,
        "wheel_hub",
        0.012,
    )
    cylinder(
        ctx,
        name + ":hub_cap",
        (outer_x + side * 0.082, y, z),
        radius * 0.115,
        0.045,
        M["chrome"],
        36,
        axis_rotation,
        "wheel_hub_cap",
        0.014,
    )
    torus(
        ctx,
        name + ":rim_outer_lip",
        (outer_x + side * 0.102, y, z),
        radius * 0.625,
        0.018,
        M["aluminum"],
        axis_rotation,
        "wheel_rim_retaining_lip",
        56,
        10,
    )
    # Deep ventilation windows and concentric sidewall moulding keep the wheel
    # legible as a full-size commercial assembly in close views.
    for vent in range(10):
        angle = 2 * math.pi * vent / 10
        vy = y + math.cos(angle) * radius * 0.46
        vz = z + math.sin(angle) * radius * 0.46
        cylinder(
            ctx,
            f"{name}:rim_vent_{vent:02d}",
            (outer_x + side * 0.087, vy, vz),
            radius * 0.065,
            0.022,
            M["black"],
            16,
            axis_rotation,
            "wheel_ventilation_aperture",
            0.003,
        )
    for lug in range(8):
        angle = 2 * math.pi * lug / 8
        ly = y + math.cos(angle) * radius * 0.30
        lz = z + math.sin(angle) * radius * 0.30
        cylinder(
            ctx,
            f"{name}:lug_{lug:02d}",
            (outer_x + side * 0.071, ly, lz),
            0.035,
            0.035,
            M["black"],
            12,
            axis_rotation,
            "wheel_lug",
            0.004,
        )
    for ring_index, ring_radius in enumerate(
        (radius * 0.49, radius * 0.79, radius * 0.86)
    ):
        torus(
            ctx,
            f"{name}:sidewall_moulding_{ring_index}",
            (outer_x + side * 0.101, y, z),
            ring_radius,
            0.012,
            M["rubber"],
            (0, math.pi / 2, 0),
            "tire_sidewall_moulding",
            48,
            8,
        )
    # Three narrow longitudinal channels and dense shallow shoulder blocks read
    # as a commercial radial tire.  They replace the coarse protruding paddles
    # that made the previous wheels resemble toy tractor tires.
    for groove_index, gx in enumerate((-0.23, 0.0, 0.23)):
        torus(
            ctx,
            f"{name}:circumferential_groove_{groove_index}",
            (x + gx * width, y, z),
            radius * 0.982,
            0.0105,
            M["black"],
            axis_rotation,
            "tire_circumferential_groove",
            72,
            8,
        )
    for tread in range(72):
        angle = 2 * math.pi * tread / 72
        # Embed most of each block into the torus carcass: a commercial tread
        # projects roughly 12-17 mm, not the coarse 35 mm paddles visible in the
        # previous silhouette.  Alternating a restrained skew preserves siping
        # without producing a toy-like saw edge.
        ty = y + math.cos(angle) * radius * 0.984
        tz = z + math.sin(angle) * radius * 0.984
        box(
            ctx,
            f"{name}:tread_{tread:02d}",
            (x, ty, tz),
            (width * 0.72, 0.050, 0.015),
            M["rubber"],
            0.0025,
            (angle, 0, math.radians(3.5 if tread % 2 else -3.5)),
            "tire_tread_block",
        )
    # Raised sidewall specification is true geometry and remains deliberately
    # subtle; it is only intended to resolve in the close apparatus views.
    text_side(
        ctx,
        name + ":sidewall_size",
        "295/80 R22.5",
        (outer_x + side * 0.122, y, z + radius * 0.68),
        0.068,
        M["plastic"],
        side,
        0.004,
        "tire_sidewall_marking",
    )
    # Valve stem and visible brake caliper complete the exposed outer face.
    beam(
        ctx,
        name + ":valve_stem",
        (outer_x + side * 0.105, y + radius * 0.31, z - radius * 0.23),
        (outer_x + side * 0.135, y + radius * 0.35, z - radius * 0.27),
        0.012,
        M["black"],
        "wheel_valve_stem",
        10,
    )
    rounded_box(
        ctx,
        name + ":brake_caliper",
        (outer_x - side * 0.065, y + radius * 0.25, z + radius * 0.13),
        (0.055, radius * 0.17, radius * 0.30),
        M["primer"],
        0.025,
        semantic="brake_caliper",
        segments=3,
    )


def build_running_gear(ctx, spec, M, rear_dual=True):
    width = spec.width
    is_ambulance = spec.variant == "type_i_ambulance"
    is_reference_heavy = spec.variant == "modern_ladder_engine"
    box(
        ctx,
        "chassis:left_frame",
        (-0.72, 0, 0.57),
        (0.15, spec.length - 0.55, 0.24),
        M["black"],
        0.035,
        semantic="chassis_frame",
    )
    box(
        ctx,
        "chassis:right_frame",
        (0.72, 0, 0.57),
        (0.15, spec.length - 0.55, 0.24),
        M["black"],
        0.035,
        semantic="chassis_frame",
    )
    for axle_index, y in enumerate(spec.wheelbase):
        cylinder(
            ctx,
            f"chassis:axle_{axle_index}",
            (0, y, 0.70),
            0.105,
            width + 0.14,
            M["steel"],
            20,
            (0, math.pi / 2, 0),
            "live_axle",
            0.008,
        )
        box(
            ctx,
            f"chassis:differential_{axle_index}",
            (0, y, 0.70),
            (0.43, 0.39, 0.36),
            M["black"],
            0.09,
            semantic="axle_differential",
        )
        for side in (-1, 1):
            if is_reference_heavy:
                # Direct OBJ landmarks: front wheel centre |X|=1.1805 m,
                # tandem wheel centres |X|=1.2775 m and diameter=1.2005 m.
                x = side * (1.1805 if axle_index == 0 else 1.2775)
            else:
                x = side * (width / 2 - 0.06)
            wheel_radius = (
                0.60025
                if is_reference_heavy
                else 0.545
                if is_ambulance
                else 0.585
                if spec.variant == "classic_pumper"
                else 0.555
            )
            wheel_width = 0.285 if is_ambulance else 0.30
            build_wheel(
                ctx,
                f"wheel:{axle_index}:{'left' if side < 0 else 'right'}",
                (x, y, 0.74),
                side,
                M,
                wheel_radius,
                wheel_width,
                rear_dual
                and (
                    axle_index > 0
                    if len(spec.wheelbase) == 3
                    else axle_index == len(spec.wheelbase) - 1
                ),
            )
            arch_radius = (
                0.705
                if is_ambulance
                else (0.72 if spec.variant == "rapid_rescue" else 0.755)
            )
            arch_inner = (
                0.600
                if is_ambulance
                else (0.625 if spec.variant == "rapid_rescue" else 0.650)
            )
            fender_material = (
                M["black"]
                if is_ambulance and axle_index == 0
                else M["ambulance_white"]
                if is_ambulance
                else M["red"]
            )
            trim_material = (
                M["black"] if is_ambulance and axle_index == 0 else M["aluminum"]
            )
            fender_x = side * (width / 2 + 0.004)
            # A dark rolled wheelhouse sits behind the outer painted fender.
            # Both overlap the side shell and close at their lower ends, so the
            # wheel opening has a real liner, flange and body load path.
            annular_arch_panel(
                ctx,
                f"fender:wheelhouse_liner_{axle_index}_{side}",
                (side * (width / 2 - 0.045), y, 0.74),
                wheel_radius + 0.025,
                arch_inner + 0.025,
                0.105,
                M["black"],
                "wheelhouse_inner_liner",
                32,
                0.008,
            )
            annular_arch_panel(
                ctx,
                f"fender:formed_arch_{axle_index}_{side}",
                (fender_x, y, 0.74),
                arch_inner,
                arch_radius,
                0.145,
                fender_material,
                "wheel_arch_fender_panel",
                36,
                0.014,
            )
            arch_points = []
            for point_index in range(25):
                angle = math.pi * point_index / 24
                arch_points.append(
                    (
                        side * (width / 2 + 0.082),
                        y + math.cos(angle) * arch_radius,
                        0.75 + math.sin(angle) * arch_radius,
                    )
                )
            curve_tube(
                ctx,
                f"fender:rolled_lip_{axle_index}_{side}",
                arch_points,
                0.026,
                trim_material,
                "wheel_arch_trim",
            )
            for apron_end in (-1, 1):
                rounded_box(
                    ctx,
                    f"fender:end_apron_{axle_index}_{side}_{apron_end}",
                    (
                        side * (width / 2 + 0.005),
                        y + apron_end * (arch_radius - 0.105),
                        0.92,
                    ),
                    (0.145, 0.30, 0.40),
                    fender_material,
                    0.045,
                    semantic="wheel_arch_support_apron",
                    segments=4,
                )
    crossmember_count = max(5, int(spec.length / 1.65))
    for crossmember_index in range(crossmember_count):
        yi = (
            -spec.length / 2
            + 0.62
            + crossmember_index * (spec.length - 1.24) / max(1, crossmember_count - 1)
        )
        box(
            ctx,
            f"chassis:crossmember_{crossmember_index:02d}",
            (0, yi, 0.61),
            (width - 0.48, 0.12, 0.18),
            M["steel"],
            0.025,
            semantic="chassis_crossmember",
        )
    # Six outriggers and elastomer isolators connect the fabricated body/cab
    # floor to the ladder frame.  They are visible in low close views and make
    # the exterior mass read as supported machinery rather than stacked parts.
    for mount_index, mount_y in enumerate(
        (-spec.length * 0.28, 0.0, spec.length * 0.28)
    ):
        for side in (-1, 1):
            beam(
                ctx,
                f"chassis:body_outrigger_{mount_index}_{side}",
                (side * 0.70, mount_y, 0.70),
                (side * (width / 2 - 0.18), mount_y, 0.98),
                0.060,
                M["steel"],
                "body_mount_outrigger",
                16,
            )
            cylinder(
                ctx,
                f"chassis:body_isolator_{mount_index}_{side}",
                (side * (width / 2 - 0.18), mount_y, 1.00),
                0.085,
                0.10,
                M["rubber"],
                24,
                semantic="body_mount_isolator",
                bevel=0.008,
            )
    cylinder(
        ctx,
        "chassis:driveshaft",
        (0, 0.15, 0.69),
        0.055,
        spec.length * 0.62,
        M["steel"],
        16,
        (math.pi / 2, 0, 0),
        "driveline",
        0.005,
    )
    # Visible suspension and pneumatic systems are important at the low camera
    # height used for the apparatus portraits.
    for axle_index, y in enumerate(spec.wheelbase):
        for side in (-1, 1):
            x = side * 0.79
            for leaf in range(4):
                box(
                    ctx,
                    f"suspension:leaf_{axle_index}_{side}_{leaf}",
                    (x, y + (leaf - 1.5) * 0.035, 0.78 + leaf * 0.027),
                    (0.09, 1.08 - leaf * 0.07, 0.025),
                    M["primer"],
                    0.006,
                    semantic="leaf_spring_pack",
                )
            beam(
                ctx,
                f"suspension:damper_{axle_index}_{side}",
                (x, y - 0.22, 0.58),
                (x + side * 0.16, y + 0.12, 1.18),
                0.045,
                M["steel"],
                "hydraulic_damper",
                18,
            )
    for tank_index, (x, y) in enumerate(((-0.48, 0.25), (0.48, 0.25), (0, 1.35))):
        cylinder(
            ctx,
            f"chassis:air_reservoir_{tank_index}",
            (x, y, 0.48),
            0.16,
            0.78,
            M["black"],
            28,
            (math.pi / 2, 0, 0),
            "air_brake_reservoir",
            0.018,
        )
        for band in (-0.24, 0.24):
            torus(
                ctx,
                f"chassis:air_reservoir_band_{tank_index}_{band:+.2f}",
                (x, y + band, 0.48),
                0.165,
                0.012,
                M["steel"],
                (math.pi / 2, 0, 0),
                "air_tank_retaining_band",
                28,
                8,
            )
    rear_y = spec.wheelbase[-1] + 0.68
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"chassis:rear_mudflap_{side}",
            (side * (width / 2 - 0.04), rear_y, 0.54),
            (0.055, 0.12, 0.66),
            M["rubber"],
            0.025,
            semantic="rear_mudflap",
            segments=3,
        )


def build_emergency_lightbar(ctx, name, loc, width, M, blue=False):
    rounded_box(
        ctx,
        name + ":base",
        (loc[0], loc[1], loc[2] - 0.055),
        (width, 0.30, 0.075),
        M["black"],
        0.025,
        semantic="emergency_lightbar_base",
        segments=4,
    )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"{name}:mounting_foot_{side}",
            (loc[0] + side * width * 0.34, loc[1], loc[2] - 0.13),
            (0.12, 0.18, 0.12),
            M["black"],
            0.022,
            semantic="lightbar_mounting_foot",
            segments=3,
        )
    modules = 8
    for i in range(modules):
        x = -width / 2 + (i + 0.5) * width / modules
        mat = M["blue_lens"] if blue and i in (0, 1, 6, 7) else M["red_lens"]
        box(
            ctx,
            f"{name}:optic_{i:02d}",
            (loc[0] + x, loc[1], loc[2]),
            (width / modules - 0.018, 0.25, 0.13),
            mat,
            0.025,
            semantic="emergency_light_optic",
        )
        box(
            ctx,
            f"{name}:reflector_{i:02d}",
            (loc[0] + x, loc[1] + 0.132, loc[2]),
            (width / modules - 0.055, 0.018, 0.085),
            M["chrome"],
            0.006,
            semantic="lightbar_reflector",
        )
        if i < modules - 1:
            box(
                ctx,
                f"{name}:module_divider_{i:02d}",
                (
                    loc[0] - width / 2 + (i + 1) * width / modules,
                    loc[1] - 0.135,
                    loc[2],
                ),
                (0.012, 0.018, 0.13),
                M["black"],
                0.003,
                semantic="lightbar_module_divider",
            )


def build_fire_door_badge(ctx, name, cab_y, width, M, unit_label):
    """Raised department crest and fleet lettering for both cab sides."""
    for side in (-1, 1):
        # The crest backing overlaps the door skin by a few millimetres; the
        # outer ring and lettering then build outward from that mounted field.
        x = side * (width / 2 + 0.035)
        torus(
            ctx,
            f"{name}:crest_ring_{side}",
            (x, cab_y - 0.54, 1.47),
            0.205,
            0.025,
            M["brass"],
            (0, math.pi / 2, 0),
            "department_crest_border",
            40,
            10,
        )
        cylinder(
            ctx,
            f"{name}:crest_field_{side}",
            (x + side * 0.008, cab_y - 0.54, 1.47),
            0.176,
            0.018,
            M["red_dark"],
            40,
            (0, side * math.pi / 2, 0),
            "department_crest_field",
            0.006,
        )
        for arm, angle in enumerate((math.radians(45), math.radians(-45))):
            box(
                ctx,
                f"{name}:crest_cross_{side}_{arm}",
                (x + side * 0.022, cab_y - 0.54, 1.47),
                (0.018, 0.31, 0.070),
                M["white"],
                0.010,
                rotation=(angle, 0, 0),
                semantic="department_crest_cross",
            )
        text_side(
            ctx,
            f"{name}:crest_letters_{side}",
            "FD",
            (x + side * 0.040, cab_y - 0.54, 1.47),
            0.075,
            M["white"],
            side,
            0.007,
            "department_crest_letters",
        )
        text_side(
            ctx,
            f"{name}:fleet_label_{side}",
            unit_label,
            (x + side * 0.045, cab_y + 0.58, 1.38),
            0.15,
            M["white"],
            side,
            0.010,
            "apparatus_fleet_marking",
        )


def build_cab_interior(ctx, cab_y, M, crew=True):
    box(
        ctx,
        "cab:dashboard",
        (0, cab_y - 1.03, 1.79),
        (2.20, 0.42, 0.35),
        M["interior"],
        0.08,
        rotation=(-0.10, 0, 0),
        semantic="cab_dashboard",
    )
    rounded_box(
        ctx,
        "cab:instrument_binnacle",
        (-0.56, cab_y - 1.24, 1.97),
        (0.72, 0.18, 0.27),
        M["plastic"],
        0.075,
        rotation=(-0.10, 0, 0),
        semantic="cab_instrument_binnacle",
        segments=5,
    )
    rounded_box(
        ctx,
        "cab:center_console",
        (0.35, cab_y - 1.24, 1.88),
        (0.58, 0.13, 0.31),
        M["plastic"],
        0.055,
        rotation=(-0.08, 0, 0),
        semantic="cab_center_console",
        segments=4,
    )
    box(
        ctx,
        "cab:center_console_display",
        (0.35, cab_y - 1.315, 1.94),
        (0.31, 0.018, 0.13),
        M["lcd"],
        0.018,
        rotation=(-0.08, 0, 0),
        semantic="cab_information_display",
    )
    for vent_index, vx in enumerate((-0.88, -0.26, 0.26, 0.88)):
        rounded_box(
            ctx,
            f"cab:defroster_vent_{vent_index}",
            (vx, cab_y - 1.21, 2.06),
            (0.30, 0.10, 0.035),
            M["black"],
            0.014,
            rotation=(-0.10, 0, 0),
            semantic="windshield_defroster_vent",
            segments=3,
        )
        for slat in range(4):
            box(
                ctx,
                f"cab:defroster_vent_slat_{vent_index}_{slat}",
                (vx - 0.105 + slat * 0.070, cab_y - 1.265, 2.065),
                (0.018, 0.012, 0.022),
                M["steel"],
                0.002,
                rotation=(-0.10, 0, 0),
                semantic="defroster_vent_slat",
            )
    for ix, x in enumerate((-0.58, 0.58)):
        box(
            ctx,
            f"cab:front_seat_base_{ix}",
            (x, cab_y - 0.14, 1.28),
            (0.55, 0.67, 0.25),
            M["seat"],
            0.09,
            semantic="firefighter_seat",
        )
        box(
            ctx,
            f"cab:front_seat_back_{ix}",
            (x, cab_y + 0.12, 1.80),
            (0.55, 0.19, 0.88),
            M["seat"],
            0.11,
            rotation=(-0.09, 0, 0),
            semantic="firefighter_seat_back",
        )
        box(
            ctx,
            f"cab:front_headrest_{ix}",
            (x, cab_y + 0.16, 2.28),
            (0.37, 0.19, 0.24),
            M["seat"],
            0.08,
            semantic="seat_headrest",
        )
    if crew:
        for ix, x in enumerate((-0.62, 0.62)):
            box(
                ctx,
                f"cab:rear_seat_base_{ix}",
                (x, cab_y + 0.83, 1.25),
                (0.58, 0.56, 0.24),
                M["seat"],
                0.08,
                semantic="firefighter_seat",
            )
            box(
                ctx,
                f"cab:rear_seat_back_{ix}",
                (x, cab_y + 1.02, 1.78),
                (0.58, 0.18, 0.88),
                M["seat"],
                0.09,
                semantic="firefighter_seat_back",
            )
    torus(
        ctx,
        "cab:steering_wheel",
        (-0.58, cab_y - 1.28, 1.93),
        0.245,
        0.035,
        M["black"],
        (math.pi / 2, 0, 0),
        "steering_wheel",
        28,
        8,
    )
    beam(
        ctx,
        "cab:steering_column",
        (-0.58, cab_y - 1.02, 1.63),
        (-0.58, cab_y - 1.27, 1.91),
        0.034,
        M["steel"],
        "steering_column",
        12,
    )
    cylinder(
        ctx,
        "cab:steering_hub",
        (-0.58, cab_y - 1.318, 1.93),
        0.075,
        0.045,
        M["plastic"],
        24,
        (math.pi / 2, 0, 0),
        "steering_wheel_hub",
        0.010,
    )
    for spoke_index, angle in enumerate(
        (math.radians(25), math.radians(155), math.radians(270))
    ):
        beam(
            ctx,
            f"cab:steering_spoke_{spoke_index}",
            (-0.58, cab_y - 1.345, 1.93),
            (
                -0.58 + math.cos(angle) * 0.205,
                cab_y - 1.345,
                1.93 + math.sin(angle) * 0.205,
            ),
            0.020,
            M["plastic"],
            "steering_wheel_spoke",
            10,
        )
    for gauge in range(5):
        x = -0.90 + gauge * 0.25
        cylinder(
            ctx,
            f"cab:dashboard_gauge_{gauge}",
            (x, cab_y - 1.255, 1.91),
            0.065,
            0.018,
            M["gauge"],
            20,
            (math.pi / 2, 0, 0),
            "cab_instrument",
            0.004,
        )
    for visor_index, vx in enumerate((-0.56, 0.56)):
        rounded_box(
            ctx,
            f"cab:interior_sun_visor_{visor_index}",
            (vx, cab_y - 1.29, 2.83),
            (0.72, 0.08, 0.25),
            M["interior"],
            0.040,
            rotation=(-0.10, 0, 0),
            semantic="cab_interior_sun_visor",
            segments=4,
        )
    for handle_index, hx in enumerate((-0.94, 0.94)):
        beam(
            ctx,
            f"cab:windshield_grab_handle_{handle_index}",
            (hx, cab_y - 1.30, 2.30),
            (hx, cab_y - 1.30, 2.67),
            0.022,
            M["steel"],
            "cab_grab_handle",
            12,
        )


def build_rescue_cab_interior(ctx, M):
    """Interior positioned behind the sloped hooded-cab windscreen."""
    rounded_box(
        ctx,
        "rescue:dashboard",
        (0, -1.91, 1.87),
        (1.94, 0.36, 0.28),
        M["interior"],
        0.07,
        rotation=(-0.08, 0, 0),
        semantic="cab_dashboard",
        segments=4,
    )
    for seat_index, x in enumerate((-0.55, 0.55)):
        rounded_box(
            ctx,
            f"rescue:seat_base_{seat_index}",
            (x, -1.26, 1.22),
            (0.52, 0.60, 0.23),
            M["seat"],
            0.085,
            semantic="firefighter_seat",
            segments=4,
        )
        rounded_box(
            ctx,
            f"rescue:seat_back_{seat_index}",
            (x, -1.03, 1.69),
            (0.52, 0.18, 0.77),
            M["seat"],
            0.085,
            rotation=(-0.10, 0, 0),
            semantic="firefighter_seat_back",
            segments=4,
        )
        rounded_box(
            ctx,
            f"rescue:headrest_{seat_index}",
            (x, -0.99, 2.12),
            (0.34, 0.17, 0.20),
            M["seat"],
            0.065,
            semantic="seat_headrest",
            segments=4,
        )
    torus(
        ctx,
        "rescue:steering_wheel",
        (-0.55, -2.00, 1.94),
        0.225,
        0.030,
        M["black"],
        (math.pi / 2, 0, 0),
        "steering_wheel",
        36,
        10,
    )
    beam(
        ctx,
        "rescue:steering_column",
        (-0.55, -1.75, 1.63),
        (-0.55, -1.98, 1.92),
        0.030,
        M["steel"],
        "steering_column",
        12,
    )
    for gauge in range(4):
        gx = -0.82 + gauge * 0.18
        cylinder(
            ctx,
            f"rescue:dashboard_gauge_{gauge}",
            (gx, -2.105, 1.95),
            0.052,
            0.015,
            M["gauge"],
            20,
            (math.pi / 2, 0, 0),
            "cab_instrument",
            0.004,
        )


def build_cab(ctx, spec, M, classic=False):
    width = spec.width * 0.96
    reference_heavy = spec.variant == "modern_ladder_engine"
    cab_y = -2.82 if spec.variant == "modern_ladder_engine" else -2.48
    front_y = -spec.length / 2 + 0.20
    rear_y = -1.18 if spec.variant == "modern_ladder_engine" else -0.98
    lower_top = 2.05
    rounded_box(
        ctx,
        "cab:lower_shell",
        (0, (front_y + rear_y) / 2, 1.35),
        (width, rear_y - front_y, 1.72),
        M["red"],
        0.16,
        semantic="cab_lower_body",
        segments=6,
    )
    # The reverse-engineered source carries one continuous red cab skin.  The
    # older cream-over-red livery remains exclusive to the heritage pumper.
    upper_material = (
        M["cream"] if classic else (M["red"] if reference_heavy else M["white"])
    )
    upper_profile = [
        (front_y + 0.04, 2.01),
        (front_y + 0.10, 2.72),
        (front_y + 0.38, 3.14 if not classic else 3.01),
        (rear_y - 0.05, 3.14 if not classic else 3.01),
        (rear_y, 2.01),
    ]
    profile_extrude_x(
        ctx,
        "cab:upper_shell",
        upper_profile,
        width - 0.05,
        upper_material,
        "cab_upper_body",
        0.12,
        open_edges=(0, 1),
    )
    rounded_box(
        ctx,
        "cab:roof",
        (0, cab_y + 0.03, 3.22 if not classic else 3.08),
        (width + 0.08, rear_y - front_y + 0.08, 0.18),
        upper_material,
        0.085,
        semantic="cab_roof",
        segments=6,
    )
    # Broad split windscreen uses tapered laminated prisms rather than two
    # scaled rectangles.  The upper edge is raked rearward and the outer edges
    # converge into the radiused cab corners, closely matching reference_01.
    windshield_y = front_y - 0.075
    windshield_z = 2.56 if not classic else 2.46
    glass_bottom = windshield_z - 0.57
    glass_top = windshield_z + 0.49
    outer_bottom = width / 2 - 0.12
    outer_top = width / 2 - 0.20
    center_gap = 0.040
    windshield_panels = {
        -1: [
            (-outer_bottom, glass_bottom),
            (-center_gap, glass_bottom),
            (-center_gap, glass_top),
            (-outer_top, glass_top),
        ],
        1: [
            (center_gap, glass_bottom),
            (outer_bottom, glass_bottom),
            (outer_top, glass_top),
            (center_gap, glass_top),
        ],
    }
    for side, points in windshield_panels.items():
        sloped_front_panel(
            ctx,
            f"cab:windshield_{side}",
            points,
            windshield_y - 0.090,
            windshield_y + 0.100,
            0.026,
            M["glass"],
            "cab_windshield",
            0.010,
        )

    # Real gasket members follow the trapezoid boundary in three dimensions.
    def windshield_edge_point(x, z, outward=0.116):
        factor = (z - glass_bottom) / max(0.001, glass_top - glass_bottom)
        y = (windshield_y - 0.055) + factor * 0.190 - outward
        return (x, y, z)

    for side in (-1, 1):
        bx = side * outer_bottom
        tx = side * outer_top
        beam(
            ctx,
            f"cab:windshield_outer_gasket_{side}",
            windshield_edge_point(bx, glass_bottom),
            windshield_edge_point(tx, glass_top),
            0.026,
            M["black"],
            "window_weatherstrip",
            14,
        )
    beam(
        ctx,
        "cab:windshield_center_mullion",
        windshield_edge_point(0, glass_bottom),
        windshield_edge_point(0, glass_top),
        0.031,
        M["black"],
        "windshield_mullion",
        14,
    )
    beam(
        ctx,
        "cab:windshield_top_seal",
        windshield_edge_point(-outer_top, glass_top),
        windshield_edge_point(outer_top, glass_top),
        0.027,
        M["black"],
        "window_weatherstrip",
        14,
    )
    beam(
        ctx,
        "cab:windshield_lower_seal",
        windshield_edge_point(-outer_bottom, glass_bottom),
        windshield_edge_point(outer_bottom, glass_bottom),
        0.030,
        M["black"],
        "window_weatherstrip",
        14,
    )
    rounded_box(
        ctx,
        "cab:windshield_sun_visor",
        (0, windshield_y - 0.17, windshield_z + 0.59),
        (width - 0.22, 0.24, 0.075),
        upper_material,
        0.035,
        rotation=(-0.08, 0, 0),
        semantic="cab_sun_visor",
        segments=4,
    )
    # Two-row side glazing and articulated door seams.
    for side in (-1, 1):
        sx = side * (width / 2 + 0.023)
        for panel_index, py in enumerate((cab_y - 0.58, cab_y + 0.63)):
            window_len = 0.93 if panel_index == 0 else 0.86
            rounded_box(
                ctx,
                f"cab:side_window_recess_{side}_{panel_index}",
                (side * (width / 2 + 0.010), py, 2.54),
                (0.040, window_len + 0.10, 0.86),
                M["black"],
                0.055,
                semantic="side_window_reveal",
                segments=4,
            )
            box(
                ctx,
                f"cab:side_window_{side}_{panel_index}",
                (sx, py, 2.54),
                (0.035, window_len, 0.76),
                M["glass_dark"],
                0.06,
                semantic="cab_side_window",
            )
            for edge, ey in enumerate((py - window_len / 2, py + window_len / 2)):
                box(
                    ctx,
                    f"cab:window_vertical_seal_{side}_{panel_index}_{edge}",
                    (sx + side * 0.025, ey, 2.54),
                    (0.035, 0.035, 0.84),
                    M["black"],
                    0.009,
                    semantic="window_weatherstrip",
                )
        for seam_index, py in enumerate((cab_y - 1.08, cab_y + 0.04, cab_y + 1.09)):
            box(
                ctx,
                f"cab:door_seam_{side}_{seam_index}",
                (sx + side * 0.026, py, 1.80),
                (0.025, 0.025, 1.63),
                M["black"],
                0.004,
                semantic="cab_door_seam",
            )
        box(
            ctx,
            f"cab:door_belt_seam_{side}",
            (sx + side * 0.026, cab_y, 1.52),
            (0.025, 2.05, 0.025),
            M["black"],
            0.004,
            semantic="cab_door_seam",
        )
        for handle_index, py in enumerate((cab_y - 0.60, cab_y + 0.60)):
            box(
                ctx,
                f"cab:door_handle_{side}_{handle_index}",
                (sx + side * 0.055, py, 1.72),
                (0.055, 0.22, 0.065),
                M["chrome"],
                0.018,
                semantic="cab_door_handle",
            )
            for hinge_index, hz in enumerate((1.20, 1.90)):
                cylinder(
                    ctx,
                    f"cab:door_hinge_{side}_{handle_index}_{hinge_index}",
                    (sx + side * 0.055, py + 0.48, hz),
                    0.035,
                    0.055,
                    M["steel"],
                    16,
                    (0, side * math.pi / 2, 0),
                    "cab_door_hinge",
                    0.006,
                )
        # Mirrors use actual arms and double housings.
        arm_y = cab_y - 0.82
        rounded_box(
            ctx,
            f"cab:mirror_mount_base_{side}",
            (side * (width / 2 + 0.034), arm_y, 2.49),
            (0.070, 0.31, 0.48),
            M["black"],
            0.045,
            semantic="mirror_mount_base",
            segments=4,
        )
        for bolt_index, bolt_z in enumerate((2.34, 2.64)):
            cylinder(
                ctx,
                f"cab:mirror_mount_bolt_{side}_{bolt_index}",
                (side * (width / 2 + 0.078), arm_y, bolt_z),
                0.026,
                0.026,
                M["chrome"],
                14,
                (0, side * math.pi / 2, 0),
                "mirror_mount_fastener",
                0.003,
            )
        beam(
            ctx,
            f"cab:mirror_upper_arm_{side}",
            (sx, arm_y, 2.62),
            (side * (width / 2 + 0.34), arm_y - 0.12, 2.74),
            0.026,
            M["steel"],
            "mirror_support",
            12,
        )
        beam(
            ctx,
            f"cab:mirror_lower_arm_{side}",
            (sx, arm_y, 2.34),
            (side * (width / 2 + 0.34), arm_y - 0.12, 2.52),
            0.026,
            M["steel"],
            "mirror_support",
            12,
        )
        box(
            ctx,
            f"cab:mirror_housing_{side}",
            (side * (width / 2 + 0.39), arm_y - 0.14, 2.63),
            (0.12, 0.28, 0.42),
            M["black"],
            0.07,
            semantic="side_mirror",
        )
        box(
            ctx,
            f"cab:mirror_glass_{side}",
            (side * (width / 2 + 0.455), arm_y - 0.14, 2.63),
            (0.012, 0.235, 0.35),
            M["glass"],
            0.015,
            semantic="mirror_glass",
        )
        box(
            ctx,
            f"cab:entry_step_{side}",
            (side * (width / 2 + 0.12), cab_y + 0.58, 0.93),
            (0.22, 1.22, 0.15),
            M["diamond"],
            0.025,
            semantic="cab_access_step",
        )
        rounded_box(
            ctx,
            f"cab:entry_step_riser_{side}",
            (side * (width / 2 + 0.035), cab_y + 0.58, 1.08),
            (0.105, 1.14, 0.34),
            M["red_dark"],
            0.025,
            semantic="cab_step_riser",
            segments=3,
        )
        for bracket_index, bracket_y in enumerate((cab_y + 0.18, cab_y + 0.91)):
            beam(
                ctx,
                f"cab:entry_step_bracket_{side}_{bracket_index}",
                (side * 0.72, bracket_y, 0.70),
                (side * (width / 2 + 0.08), bracket_y, 0.88),
                0.046,
                M["steel"],
                "step_mount_bracket",
                14,
            )
    build_fire_door_badge(
        ctx, "cab:department_badge", cab_y, width, M, "ENG-8" if classic else "ENGINE 1"
    )
    # Reflective belt stripes around the white-over-red body break.
    box(
        ctx,
        "cab:front_reflective_stripe",
        (0, front_y - 0.09, 1.79),
        (width - 0.12, 0.045, 0.075),
        M["yellow_reflect"],
        0.008,
        semantic="reflective_livery",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"cab:side_reflective_stripe_{side}",
            (side * (width / 2 + 0.045), cab_y, 1.78),
            (0.035, rear_y - front_y - 0.12, 0.075),
            M["yellow_reflect"],
            0.007,
            semantic="reflective_livery",
        )
    # Front grille, bumper, lighting and tow equipment.  A continuous carrier
    # panel, lower valance and chassis horns sit behind the visible fittings;
    # no lamp, grille or bumper is left as an unsupported face-mounted island.
    bumper_y = front_y - 0.22
    rounded_box(
        ctx,
        "cab:front_fascia_carrier",
        (0, front_y - 0.055, 1.29),
        (width - 0.10, 0.16, 1.23),
        M["red"],
        0.060,
        semantic="front_fascia_carrier",
        segments=5,
    )
    rounded_box(
        ctx,
        "cab:lower_fascia_valance",
        (0, front_y - 0.105, 0.90),
        (width - 0.24, 0.20, 0.35),
        M["red_dark"],
        0.045,
        semantic="front_fascia_transition",
        segments=4,
    )
    for mount_side in (-1, 1):
        box(
            ctx,
            f"cab:bumper_frame_horn_{mount_side}",
            (mount_side * 0.72, front_y + 0.055, 0.68),
            (0.17, 0.72, 0.17),
            M["steel"],
            0.025,
            semantic="bumper_mount_bracket",
        )
        rounded_box(
            ctx,
            f"cab:bumper_mount_plate_{mount_side}",
            (mount_side * 0.72, bumper_y - 0.115, 0.68),
            (0.39, 0.075, 0.31),
            M["black"],
            0.025,
            semantic="bumper_mount_plate",
            segments=3,
        )
    rounded_box(
        ctx,
        "cab:front_bumper",
        (0, bumper_y, 0.67),
        (width + 0.24, 0.34, 0.27),
        M["white"] if reference_heavy else M["diamond"],
        0.065,
        semantic="front_bumper",
        segments=5,
    )
    rounded_box(
        ctx,
        "cab:bumper_top_step_pad",
        (0, bumper_y - 0.015, 0.815),
        (width - 0.36, 0.23, 0.045),
        M["rubber"],
        0.012,
        semantic="bumper_anti_slip_step",
        segments=3,
    )
    box(
        ctx,
        "cab:front_bumper_rub_rail",
        (0, bumper_y - 0.185, 0.68),
        (width - 0.18, 0.055, 0.115),
        M["black"],
        0.020,
        semantic="front_bumper_rub_rail",
    )
    for fastener_index, fastener_x in enumerate((-0.78, -0.28, 0.28, 0.78)):
        cylinder(
            ctx,
            f"cab:bumper_face_fastener_{fastener_index}",
            (fastener_x, bumper_y - 0.205, 0.72),
            0.026,
            0.022,
            M["chrome"],
            14,
            (math.pi / 2, 0, 0),
            "bumper_mount_fastener",
            0.003,
        )
    for corner in (-1, 1):
        rounded_box(
            ctx,
            f"cab:bumper_corner_cap_{corner}",
            (corner * (width / 2 + 0.075), bumper_y - 0.06, 0.67),
            (0.26, 0.22, 0.25),
            M["plastic"],
            0.050,
            semantic="front_bumper_corner_cap",
            segments=5,
        )
    box(
        ctx,
        "cab:front_grille_recess",
        (0, front_y - 0.115, 1.23),
        (1.28, 0.10, 0.62),
        M["black"],
        0.055,
        semantic="radiator_grille_recess",
    )
    rounded_box(
        ctx,
        "cab:front_grille_surround",
        (0, front_y - 0.158, 1.23),
        (1.49, 0.055, 0.82),
        M["chrome"],
        0.055,
        semantic="radiator_grille_surround",
        segments=5,
    )
    rounded_box(
        ctx,
        "cab:front_grille_back",
        (0, front_y - 0.180, 1.23),
        (1.30, 0.035, 0.64),
        M["black"],
        0.035,
        semantic="radiator_grille_recess",
        segments=4,
    )
    grille_bar_y = front_y - (0.190 if classic else 0.215)
    for bar in range(10):
        z = 0.96 + bar * 0.061
        box(
            ctx,
            f"cab:grille_bar_{bar:02d}",
            (0, grille_bar_y, z),
            (1.15, 0.028, 0.018),
            M["aluminum"],
            0.006,
            semantic="radiator_grille_bar",
        )
    for support in (-0.42, 0.0, 0.42):
        box(
            ctx,
            f"cab:grille_vertical_support_{support:+.2f}",
            (support, grille_bar_y - 0.010, 1.235),
            (0.018, 0.025, 0.57),
            M["steel"],
            0.004,
            semantic="radiator_grille_support",
        )
    rounded_box(
        ctx,
        "cab:manufacturer_badge",
        (0, grille_bar_y - 0.030, 1.235),
        (0.27, 0.025, 0.15),
        M["red_dark"],
        0.035,
        semantic="manufacturer_badge",
        segments=4,
    )
    text_front(
        ctx,
        "cab:manufacturer_badge_text",
        "F",
        (0, grille_bar_y - 0.052, 1.235),
        0.095,
        M["silver_reflect"],
        0.006,
        semantic="manufacturer_badge_mark",
    )
    for side in (-1, 1):
        x = side * 0.88
        rounded_box(
            ctx,
            f"cab:headlamp_bezel_{side}",
            (x, front_y - 0.198, 1.34),
            (0.43, 0.055, 0.46),
            M["plastic"],
            0.055,
            semantic="headlamp_bezel",
            segments=5,
        )
        if classic:
            cylinder(
                ctx,
                f"cab:headlamp_{side}",
                (x, front_y - 0.235, 1.38),
                0.145,
                0.048,
                M["headlamp"],
                36,
                (math.pi / 2, 0, 0),
                "headlamp",
                0.010,
            )
            rounded_box(
                ctx,
                f"cab:turn_signal_{side}",
                (x, front_y - 0.230, 1.11),
                (0.27, 0.025, 0.10),
                M["amber"],
                0.022,
                semantic="front_turn_signal",
                segments=4,
            )
        else:
            for lamp_index, lz in enumerate((1.23, 1.46)):
                rounded_box(
                    ctx,
                    f"cab:headlamp_{side}_{lamp_index}",
                    (x, front_y - 0.236, lz),
                    (0.29, 0.028, 0.145),
                    M["headlamp"],
                    0.035,
                    semantic="headlamp",
                    segments=5,
                )
                box(
                    ctx,
                    f"cab:headlamp_reflector_divider_{side}_{lamp_index}",
                    (x, front_y - 0.253, lz),
                    (0.018, 0.012, 0.125),
                    M["chrome"],
                    0.003,
                    semantic="headlamp_reflector_divider",
                )
            rounded_box(
                ctx,
                f"cab:turn_signal_{side}",
                (x, front_y - 0.232, 1.06),
                (0.30, 0.026, 0.11),
                M["amber"],
                0.024,
                semantic="front_turn_signal",
                segments=4,
            )
        cylinder(
            ctx,
            f"cab:tow_eye_{side}",
            (side * 0.62, bumper_y - 0.19, 0.60),
            0.105,
            0.055,
            M["black"],
            24,
            (math.pi / 2, 0, 0),
            "tow_eye",
            0.012,
        )
        rounded_box(
            ctx,
            f"cab:foglamp_bezel_{side}",
            (side * 0.89, bumper_y - 0.185, 0.67),
            (0.36, 0.035, 0.15),
            M["black"],
            0.035,
            semantic="foglamp_bezel",
            segments=4,
        )
        cylinder(
            ctx,
            f"cab:foglamp_{side}",
            (side * 0.89, bumper_y - 0.208, 0.67),
            0.062,
            0.025,
            M["headlamp"],
            24,
            (math.pi / 2, 0, 0),
            "fog_lamp",
            0.006,
        )
    # Articulated arms, pivots and separate rubber blades sit just proud of the
    # laminated glazing instead of appearing as two painted diagonal strokes.
    for side in (-1, 1):
        pivot = (side * 0.84, windshield_y - 0.175, glass_bottom + 0.06)
        elbow = (side * 0.46, windshield_y - 0.122, windshield_z - 0.145)
        blade_a = (side * 0.68, windshield_y - 0.132, windshield_z - 0.29)
        blade_b = (side * 0.24, windshield_y - 0.132, windshield_z)
        cylinder(
            ctx,
            f"cab:wiper_pivot_{side}",
            pivot,
            0.040,
            0.035,
            M["black"],
            20,
            (math.pi / 2, 0, 0),
            "windshield_wiper_pivot",
            0.005,
        )
        beam(
            ctx,
            f"cab:wiper_arm_{side}",
            pivot,
            elbow,
            0.014,
            M["black"],
            "windshield_wiper_arm",
            12,
        )
        beam(
            ctx,
            f"cab:wiper_blade_{side}",
            blade_a,
            blade_b,
            0.017,
            M["rubber"],
            "windshield_wiper",
            12,
        )
        rounded_box(
            ctx,
            f"cab:washer_nozzle_{side}",
            (side * 0.54, windshield_y - 0.188, glass_bottom - 0.055),
            (0.075, 0.045, 0.030),
            M["black"],
            0.012,
            semantic="windshield_washer_nozzle",
            segments=3,
        )
    for marker_index, mx in enumerate((-0.82, -0.41, 0.0, 0.41, 0.82)):
        rounded_box(
            ctx,
            f"cab:roof_clearance_marker_{marker_index}",
            (mx, front_y + 0.12, 3.20 if not classic else 3.07),
            (0.15, 0.075, 0.065),
            M["amber"],
            0.020,
            semantic="cab_clearance_marker",
            segments=4,
        )
    build_cab_interior(ctx, cab_y, M, crew=True)
    build_emergency_lightbar(
        ctx,
        "cab:roof_lightbar",
        (0, cab_y - 0.30, 3.40 if not classic else 3.25),
        1.78,
        M,
        blue=True,
    )
    beam(
        ctx,
        "cab:radio_antenna",
        (0.82, cab_y + 0.50, 3.34),
        (0.88, cab_y + 0.50, 3.98),
        0.018,
        M["black"],
        "radio_antenna",
        10,
    )
    sphere(
        ctx,
        "cab:antenna_tip",
        (0.88, cab_y + 0.50, 3.98),
        (0.035, 0.035, 0.035),
        M["black"],
        "antenna_tip",
        12,
        8,
    )
    text_front(
        ctx,
        "cab:front_department_mark",
        "CITY FIRE",
        (0, front_y - 0.225, 1.78),
        0.13,
        M["white"],
        0.010,
        semantic="apparatus_identification",
    )
    # Flexible cab/body interface seals and lower bridge plates close the small
    # articulation joint while still explaining how the two modules can move.
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"cab:body_interface_seal_{side}",
            (side * (width / 2 + 0.030), rear_y + 0.055, 1.82),
            (0.070, 0.19, 1.86),
            M["rubber"],
            0.026,
            semantic="cab_body_flexible_joint",
            segments=3,
        )
        box(
            ctx,
            f"cab:body_interface_bridge_{side}",
            (side * (width / 2 + 0.075), rear_y + 0.04, 0.88),
            (0.15, 0.38, 0.13),
            M["diamond"],
            0.020,
            semantic="cab_body_transition_plate",
        )


def rollup_compartment(
    ctx, name, side, center_y, length, z, height, M, panel_material=None, mount_x=1.245
):
    # ``mount_x`` is the recess centre, not the visible face.  The default
    # overlaps the 2.47 m engine body shell; the narrower rescue module passes
    # its own value.  This removes the air gap left by the old fixed 1.306 m
    # coordinate while retaining layered jamb/door/fastener depth.
    x = side * mount_x
    panel_mat = panel_material or M["aluminum"]
    box(
        ctx,
        name + ":recess",
        (x, center_y, z),
        (0.055, length, height),
        M["black"],
        0.025,
        semantic="equipment_compartment_recess",
    )
    box(
        ctx,
        name + ":door",
        (x + side * 0.036, center_y, z),
        (0.045, length - 0.12, height - 0.11),
        panel_mat,
        0.018,
        semantic="rollup_compartment_door",
    )
    slat_count = max(8, int((height - 0.15) / 0.115))
    for slat in range(slat_count):
        sz = z - (height - 0.14) / 2 + (slat + 0.5) * (height - 0.14) / slat_count
        box(
            ctx,
            f"{name}:slat_{slat:02d}",
            (x + side * 0.067, center_y, sz),
            (0.024, length - 0.20, 0.025),
            M["steel"],
            0.004,
            semantic="rollup_door_slat",
        )
    for edge, py in enumerate(
        (center_y - length / 2 + 0.04, center_y + length / 2 - 0.04)
    ):
        box(
            ctx,
            f"{name}:vertical_frame_{edge}",
            (x + side * 0.075, py, z),
            (0.045, 0.075, height + 0.08),
            M["red"],
            0.012,
            semantic="compartment_frame",
        )
    for edge, pz in enumerate((z - height / 2 + 0.035, z + height / 2 - 0.035)):
        box(
            ctx,
            f"{name}:horizontal_frame_{edge}",
            (x + side * 0.075, center_y, pz),
            (0.045, length, 0.075),
            M["red"],
            0.012,
            semantic="compartment_frame",
        )
    box(
        ctx,
        name + ":drip_rail",
        (x + side * 0.105, center_y, z + height / 2 + 0.08),
        (0.060, length + 0.12, 0.065),
        M["aluminum"],
        0.014,
        semantic="compartment_drip_rail",
    )
    box(
        ctx,
        name + ":handle",
        (x + side * 0.092, center_y, z - height * 0.34),
        (0.04, 0.30, 0.055),
        M["black"],
        0.012,
        semantic="compartment_handle",
    )
    cylinder(
        ctx,
        name + ":latch",
        (x + side * 0.125, center_y, z - height * 0.34),
        0.052,
        0.035,
        M["chrome"],
        20,
        (0, side * math.pi / 2, 0),
        "compartment_latch",
        0.006,
    )
    for frame_side, py in enumerate(
        (center_y - length / 2 + 0.015, center_y + length / 2 - 0.015)
    ):
        for rivet in range(6):
            pz = z - height * 0.42 + rivet * height * 0.168
            cylinder(
                ctx,
                f"{name}:frame_rivet_{frame_side}_{rivet}",
                (x + side * 0.118, py, pz),
                0.014,
                0.018,
                M["chrome"],
                10,
                (0, side * math.pi / 2, 0),
                "compartment_frame_fastener",
                0.002,
            )


def build_pump_panel(ctx, side, center_y, M, classic=False):
    x = side * 1.275
    box(
        ctx,
        "pump:panel_back",
        (x, center_y, 1.62),
        (0.075, 1.36, 1.58),
        M["diamond"],
        0.025,
        semantic="pump_control_panel",
    )
    box(
        ctx,
        "pump:lcd",
        (x + side * 0.055, center_y - 0.35, 1.98),
        (0.035, 0.42, 0.23),
        M["lcd"],
        0.025,
        semantic="pump_status_display",
    )
    for gauge in range(8):
        row = gauge // 4
        col = gauge % 4
        gy = center_y - 0.42 + col * 0.28
        gz = 1.67 + row * 0.34
        cylinder(
            ctx,
            f"pump:gauge_{gauge:02d}",
            (x + side * 0.075, gy, gz),
            0.095,
            0.035,
            M["gauge"],
            24,
            (0, side * math.pi / 2, 0),
            "pump_pressure_gauge",
            0.007,
        )
        torus(
            ctx,
            f"pump:gauge_bezel_{gauge:02d}",
            (x + side * 0.100, gy, gz),
            0.101,
            0.012,
            M["chrome"],
            (0, math.pi / 2, 0),
            "gauge_bezel",
            32,
            8,
        )
        needle_angle = math.radians(-55 + gauge * 17)
        beam(
            ctx,
            f"pump:gauge_needle_{gauge:02d}",
            (x + side * 0.116, gy, gz),
            (
                x + side * 0.118,
                gy + math.cos(needle_angle) * 0.068,
                gz + math.sin(needle_angle) * 0.068,
            ),
            0.009,
            M["gauge_white"],
            "pump_gauge_needle",
            8,
        )
        for tick in range(10):
            tick_angle = math.radians(-135 + tick * 27)
            inner = 0.066
            outer = 0.082
            beam(
                ctx,
                f"pump:gauge_tick_{gauge:02d}_{tick:02d}",
                (
                    x + side * 0.118,
                    gy + math.cos(tick_angle) * inner,
                    gz + math.sin(tick_angle) * inner,
                ),
                (
                    x + side * 0.120,
                    gy + math.cos(tick_angle) * outer,
                    gz + math.sin(tick_angle) * outer,
                ),
                0.004,
                M["gauge_white"],
                "pump_gauge_tick",
                6,
            )
    for valve in range(6):
        row = valve // 3
        col = valve % 3
        vy = center_y - 0.40 + col * 0.39
        vz = 1.12 + row * 0.31
        cylinder(
            ctx,
            f"pump:outlet_{valve:02d}",
            (x + side * 0.105, vy, vz),
            0.13,
            0.13,
            M["chrome"],
            24,
            (0, side * math.pi / 2, 0),
            "hose_coupling",
            0.01,
        )
        cylinder(
            ctx,
            f"pump:valve_handle_{valve:02d}",
            (x + side * 0.19, vy, vz),
            0.075,
            0.055,
            M["red" if valve % 2 == 0 else "yellow_reflect"],
            20,
            (0, side * math.pi / 2, 0),
            "pump_valve_handle",
            0.008,
        )
        box(
            ctx,
            f"pump:valve_label_{valve:02d}",
            (x + side * 0.128, vy, vz + 0.18),
            (0.025, 0.24, 0.055),
            M["black"],
            0.006,
            semantic="pump_control_label_plate",
        )
    for lever in range(4):
        py = center_y - 0.48 + lever * 0.31
        beam(
            ctx,
            f"pump:lever_{lever}",
            (x + side * 0.12, py, 2.20),
            (x + side * 0.25, py + 0.04, 2.37),
            0.026,
            M["chrome"],
            "pump_control_lever",
            12,
        )
        sphere(
            ctx,
            f"pump:lever_knob_{lever}",
            (x + side * 0.25, py + 0.04, 2.37),
            (0.055, 0.055, 0.055),
            M["black"],
            "pump_lever_knob",
            12,
            8,
        )
    text_side(
        ctx,
        "pump:panel_label",
        "PUMP CONTROL",
        (x + side * 0.12, center_y, 2.48),
        0.12,
        M["gauge_white"],
        side,
        0.009,
        "pump_panel_label",
    )


def build_portable_ladder(ctx, name, center, length, width, z, M, tiers=1):
    cx, cy = center
    for tier in range(tiers):
        offset_x = (tier - (tiers - 1) / 2) * 0.18
        tz = z + tier * 0.12
        for rail_side in (-1, 1):
            rx = cx + rail_side * width / 2 + offset_x
            rounded_box(
                ctx,
                f"{name}:rail_{tier}_{rail_side}",
                (rx, cy, tz),
                (0.10, length, 0.16),
                M["aluminum"],
                0.028,
                semantic="portable_ladder_rail",
                segments=4,
            )
            for hole in range(max(8, int(length / 0.62))):
                hy = (
                    cy
                    - length / 2
                    + 0.36
                    + hole * (length - 0.72) / max(1, int(length / 0.62) - 1)
                )
                cylinder(
                    ctx,
                    f"{name}:rail_hole_{tier}_{rail_side}_{hole:02d}",
                    (rx + rail_side * 0.053, hy, tz),
                    0.027,
                    0.015,
                    M["black"],
                    12,
                    (0, math.pi / 2, 0),
                    "ladder_rail_aperture",
                    0.002,
                )
        rung_count = max(10, int(length / 0.34))
        for rung in range(rung_count):
            ry = cy - length / 2 + 0.24 + rung * (length - 0.48) / (rung_count - 1)
            cylinder(
                ctx,
                f"{name}:rung_{tier}_{rung:02d}",
                (cx + offset_x, ry, tz + 0.075),
                0.027,
                width - 0.05,
                M["red"],
                16,
                (0, math.pi / 2, 0),
                "portable_ladder_rung",
                0.006,
            )
        for end_index, ey in enumerate((cy - length / 2, cy + length / 2)):
            for rail_side in (-1, 1):
                box(
                    ctx,
                    f"{name}:rubber_foot_{tier}_{end_index}_{rail_side}",
                    (cx + rail_side * width / 2 + offset_x, ey, tz),
                    (0.14, 0.16, 0.19),
                    M["rubber"],
                    0.025,
                    semantic="ladder_end_foot",
                )
        for lock_index, lock_y in enumerate((cy - length * 0.18, cy + length * 0.18)):
            rounded_box(
                ctx,
                f"{name}:extension_lock_{tier}_{lock_index}",
                (cx + offset_x, lock_y, tz + 0.12),
                (width + 0.05, 0.16, 0.07),
                M["steel"],
                0.018,
                semantic="ladder_extension_lock",
                segments=3,
            )


def build_roof_apparatus_facilities(ctx, M, classic=False):
    """Fabricate the working roof deck, plumbing and ladder retention system."""
    deck_z = 3.16 if not classic else 3.02
    # Continuous anti-slip maintenance walk with seam fasteners.
    rounded_box(
        ctx,
        "roof_equipment:walkway",
        (-0.03, 1.56, deck_z + 0.10),
        (0.58, 4.52, 0.095),
        M["diamond"],
        0.025,
        semantic="apparatus_roof_walkway",
        segments=4,
    )
    for fastener in range(18):
        fy = -0.55 + fastener * 4.18 / 17
        for side in (-1, 1):
            cylinder(
                ctx,
                f"roof_equipment:walkway_fastener_{fastener}_{side}",
                (side * 0.23, fy, deck_z + 0.158),
                0.012,
                0.014,
                M["black"],
                10,
                semantic="roof_walkway_fastener",
                bevel=0.002,
            )
    # Deck gun / water monitor with a rotating base, elevation yoke, barrel,
    # stream shaper and hand wheels.  It is parked low for road clearance.
    cylinder(
        ctx,
        "roof_equipment:monitor_base",
        (0, -0.48, deck_z + 0.20),
        0.22,
        0.18,
        M["brass"],
        36,
        semantic="roof_deck_monitor_base",
        bevel=0.016,
    )
    cylinder(
        ctx,
        "roof_equipment:monitor_swivel",
        (0, -0.48, deck_z + 0.35),
        0.15,
        0.22,
        M["steel"],
        32,
        semantic="roof_deck_monitor_swivel",
        bevel=0.014,
    )
    for side in (-1, 1):
        beam(
            ctx,
            f"roof_equipment:monitor_yoke_{side}",
            (side * 0.14, -0.48, deck_z + 0.35),
            (side * 0.14, -0.72, deck_z + 0.53),
            0.035,
            M["brass"],
            "roof_deck_monitor_yoke",
            16,
        )
        torus(
            ctx,
            f"roof_equipment:monitor_handwheel_{side}",
            (side * 0.21, -0.59, deck_z + 0.45),
            0.105,
            0.018,
            M["black"],
            (0, math.pi / 2, 0),
            "roof_deck_monitor_handwheel",
            32,
            8,
        )
    cylinder(
        ctx,
        "roof_equipment:monitor_barrel",
        (0, -0.93, deck_z + 0.58),
        0.085,
        0.62,
        M["brass"],
        28,
        (math.pi / 2, 0, 0),
        "roof_deck_monitor_barrel",
        0.010,
    )
    cylinder(
        ctx,
        "roof_equipment:monitor_nozzle",
        (0, -1.28, deck_z + 0.58),
        0.12,
        0.16,
        M["chrome"],
        32,
        (math.pi / 2, 0, 0),
        "roof_deck_monitor_nozzle",
        0.012,
    )
    # Hard-suction plumbing runs on the right roof shoulder with physical
    # clamps and capped threaded ends.
    for tube_index, (tx, tz) in enumerate(
        ((0.83, deck_z + 0.23), (1.06, deck_z + 0.18))
    ):
        cylinder(
            ctx,
            f"roof_equipment:suction_tube_{tube_index}",
            (tx, 1.22, tz),
            0.090,
            4.82,
            M["aluminum"],
            32,
            (math.pi / 2, 0, 0),
            "roof_hard_suction_tube",
            0.010,
        )
        for end_index, ey in enumerate((-1.23, 3.67)):
            cylinder(
                ctx,
                f"roof_equipment:suction_cap_{tube_index}_{end_index}",
                (tx, ey, tz),
                0.112,
                0.075,
                M["brass"],
                32,
                (math.pi / 2, 0, 0),
                "roof_hard_suction_cap",
                0.010,
            )
        for clamp_index, cy in enumerate((-0.58, 0.72, 2.02, 3.30)):
            torus(
                ctx,
                f"roof_equipment:suction_clamp_{tube_index}_{clamp_index}",
                (tx, cy, tz),
                0.097,
                0.014,
                M["steel"],
                (math.pi / 2, 0, 0),
                "roof_equipment_retaining_clamp",
                28,
                8,
            )
            rounded_box(
                ctx,
                f"roof_equipment:suction_saddle_{tube_index}_{clamp_index}",
                (tx, cy, deck_z + 0.105),
                (0.30, 0.16, 0.16),
                M["black"],
                0.028,
                semantic="roof_equipment_mount_saddle",
                segments=3,
            )
    # Ladder rack feet, rollers, sheaves and safety cable are readable evidence
    # that the long ladders are mounted equipment rather than floating props.
    for rack_index, ry in enumerate((-1.05, 0.55, 2.18, 3.72)):
        rounded_box(
            ctx,
            f"roof_equipment:ladder_saddle_{rack_index}",
            (-0.63, ry, deck_z + 0.26),
            (0.92, 0.25, 0.13),
            M["steel"],
            0.025,
            semantic="ladder_rack_saddle",
            segments=4,
        )
        cylinder(
            ctx,
            f"roof_equipment:ladder_roller_{rack_index}",
            (-0.63, ry, deck_z + 0.36),
            0.060,
            0.74,
            M["black"],
            24,
            (0, math.pi / 2, 0),
            "ladder_rack_roller",
            0.007,
        )
    for sheave_index, sy in enumerate((-1.17, 3.83)):
        torus(
            ctx,
            f"roof_equipment:ladder_sheave_{sheave_index}",
            (-0.92, sy, deck_z + 0.43),
            0.105,
            0.020,
            M["steel"],
            (0, math.pi / 2, 0),
            "ladder_cable_sheave",
            32,
            8,
        )
    curve_tube(
        ctx,
        "roof_equipment:ladder_safety_cable",
        [
            (-0.92, -1.17, deck_z + 0.43),
            (-1.02, 0.90, deck_z + 0.48),
            (-0.95, 3.83, deck_z + 0.43),
        ],
        0.009,
        M["steel"],
        "ladder_safety_cable",
    )


def build_engine_body(ctx, spec, M, classic=False):
    rear_center = 1.48 if not classic else 1.37
    rear_length = 5.02 if not classic else 4.55
    body_height = 2.42 if not classic else 2.29
    body_front = rear_center - rear_length / 2
    rounded_box(
        ctx,
        "body:front_bulkhead",
        (0, body_front + 0.025, 1.75),
        (2.43, 0.18, body_height - 0.10),
        M["red_dark"],
        0.045,
        semantic="apparatus_body_front_bulkhead",
        segments=4,
    )
    box(
        ctx,
        "body:front_bulkhead_lower_crossrail",
        (0, body_front - 0.075, 0.82),
        (2.36, 0.18, 0.20),
        M["steel"],
        0.025,
        semantic="cab_body_transition_crossrail",
    )
    rounded_box(
        ctx,
        "body:water_tank_shell",
        (0, rear_center, 1.76),
        (2.47, rear_length, body_height),
        M["red"],
        0.095,
        semantic="apparatus_body_shell",
        segments=5,
    )
    rounded_box(
        ctx,
        "body:top_deck",
        (0, rear_center, 3.02 if not classic else 2.88),
        (2.50, rear_length + 0.05, 0.16),
        M["diamond"],
        0.045,
        semantic="apparatus_top_deck",
        segments=4,
    )
    # Full rear chevron and lighting package.
    rear_y = rear_center + rear_length / 2 + 0.045
    box(
        ctx,
        "body:rear_face",
        (0, rear_y, 1.70),
        (2.42, 0.08, 2.26),
        M["red"],
        0.04,
        semantic="apparatus_rear_face",
    )
    for stripe in range(10):
        x = -1.04 + stripe * 0.23
        box(
            ctx,
            f"body:rear_chevron_{stripe:02d}",
            (x, rear_y + 0.052, 1.18 + (stripe % 2) * 0.28),
            (0.20, 0.022, 0.13),
            M["yellow_reflect"],
            0.006,
            rotation=(0, 0, math.radians(28 if stripe % 2 == 0 else -28)),
            semantic="rear_chevron",
        )
    for side in (-1, 1):
        box(
            ctx,
            f"body:rear_light_stack_{side}",
            (side * 0.91, rear_y + 0.064, 1.86),
            (0.23, 0.035, 0.70),
            M["black"],
            0.035,
            semantic="rear_light_housing",
        )
        for light_index, (z, mat) in enumerate(
            ((2.10, M["red_lens"]), (1.87, M["amber"]), (1.64, M["headlamp"]))
        ):
            cylinder(
                ctx,
                f"body:rear_light_{side}_{light_index}",
                (side * 0.91, rear_y + 0.087, z),
                0.088,
                0.025,
                mat,
                20,
                (math.pi / 2, 0, 0),
                "rear_warning_light",
                0.006,
            )
    # Side compartment architecture differs around the midship pump panel.
    for side in (-1, 1):
        rollup_compartment(
            ctx, f"body:front_compartment_{side}", side, -0.18, 1.32, 1.78, 1.70, M
        )
        rollup_compartment(
            ctx, f"body:rear_compartment_{side}", side, 2.82, 1.48, 1.78, 1.70, M
        )
        if side == -1:
            build_pump_panel(ctx, side, 1.34, M, classic)
        else:
            rollup_compartment(
                ctx, f"body:center_compartment_{side}", side, 1.30, 1.34, 1.78, 1.70, M
            )
        box(
            ctx,
            f"body:upper_livery_{side}",
            (side * 1.258, rear_center, 2.79),
            (0.035, rear_length - 0.18, 0.09),
            M["white" if not classic else "cream"],
            0.006,
            semantic="apparatus_livery_band",
        )
        box(
            ctx,
            f"body:lower_reflective_{side}",
            (side * 1.258, rear_center, 0.99),
            (0.035, rear_length - 0.25, 0.075),
            M["yellow_reflect"],
            0.006,
            semantic="reflective_livery",
        )
        box(
            ctx,
            f"body:running_board_{side}",
            (side * 1.43, rear_center, 0.74),
            (0.26, rear_length - 0.35, 0.14),
            M["diamond"],
            0.025,
            semantic="apparatus_running_board",
        )
        for bracket_index, bracket_y in enumerate(
            (body_front + 0.48, 0.72, 2.16, rear_center + rear_length / 2 - 0.48)
        ):
            beam(
                ctx,
                f"body:running_board_bracket_{side}_{bracket_index}",
                (side * 0.72, bracket_y, 0.67),
                (side * 1.39, bracket_y, 0.73),
                0.048,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        for grip in range(16):
            gy = (
                rear_center
                - (rear_length - 0.62) / 2
                + grip * (rear_length - 0.62) / 15
            )
            cylinder(
                ctx,
                f"body:running_board_grip_{side}_{grip:02d}",
                (side * 1.515, gy, 0.82),
                0.025,
                0.018,
                M["black"],
                12,
                (0, side * math.pi / 2, 0),
                "running_board_grip_aperture",
                0.002,
            )
        box(
            ctx,
            f"body:upper_drip_rail_{side}",
            (side * 1.338, rear_center, 2.68),
            (0.055, rear_length - 0.10, 0.065),
            M["aluminum"],
            0.012,
            semantic="apparatus_body_drip_rail",
        )
    # Hose bed with individually modeled folded supply lines.
    bed_z = 3.18 if not classic else 3.04
    box(
        ctx,
        "hosebed:tray",
        (0, 2.23, bed_z),
        (2.04, 2.40, 0.16),
        M["black"],
        0.035,
        semantic="hose_bed_tray",
    )
    for layer in range(4):
        for lane in range(6):
            x = -0.82 + lane * 0.33
            run = 2.08 - layer * 0.055
            curve_tube(
                ctx,
                f"hosebed:fold_{layer}_{lane}",
                [
                    (x, 2.23 - run / 2, bed_z + 0.14 + layer * 0.105),
                    (
                        x + (0.018 if lane % 2 else -0.018),
                        2.23,
                        bed_z + 0.15 + layer * 0.105,
                    ),
                    (x, 2.23 + run / 2, bed_z + 0.14 + layer * 0.105),
                ],
                0.043,
                M["hose_canvas" if lane % 2 else "hose_yellow"],
                "folded_supply_hose",
            )
    for side in (-1, 1):
        for post_index, py in enumerate((1.06, 2.23, 3.40)):
            beam(
                ctx,
                f"hosebed:guard_post_{side}_{post_index}",
                (side * 1.08, py, bed_z + 0.08),
                (side * 1.08, py, bed_z + 0.62),
                0.025,
                M["aluminum"],
                "hose_bed_guard_post",
                14,
            )
        for rail_index, rz in enumerate((bed_z + 0.31, bed_z + 0.59)):
            beam(
                ctx,
                f"hosebed:guard_rail_{side}_{rail_index}",
                (side * 1.08, 1.01, rz),
                (side * 1.08, 3.45, rz),
                0.027,
                M["aluminum"],
                "hose_bed_guard",
                14,
            )
    build_roof_apparatus_facilities(ctx, M, classic)
    # Scene-reference roof ladders are built as real rails, rungs and end feet.
    if not classic:
        build_portable_ladder(
            ctx, "roof_ladder:left", (-0.62, 0.64), 6.92, 0.64, 3.44, M, 2
        )
        build_portable_ladder(
            ctx, "roof_ladder:right", (0.63, 0.72), 6.55, 0.62, 3.47, M, 1
        )
    else:
        build_portable_ladder(
            ctx, "roof_ladder:classic", (0.55, 0.74), 5.88, 0.60, 3.27, M, 1
        )
        for coil in range(3):
            torus(
                ctx,
                f"hosebed:side_coil_{coil}",
                (-1.39, 2.16 + coil * 0.47, 2.62),
                0.24,
                0.055,
                M["hose_red"],
                (0, math.pi / 2, 0),
                "coiled_attack_hose",
                28,
                8,
            )
    # Small but visually important manufactured details.
    for side in (-1, 1):
        for yi in (-0.64, 0.52, 2.18, 3.55):
            box(
                ctx,
                f"body:marker_light_{side}_{yi:+.2f}",
                (side * 1.278, yi, 2.91),
                (0.035, 0.12, 0.075),
                M["amber"],
                0.015,
                semantic="side_marker_light",
            )
        cylinder(
            ctx,
            f"body:deck_floodlight_{side}",
            (side * 0.93, 3.83, 3.11),
            0.11,
            0.06,
            M["headlamp"],
            24,
            (math.pi / 2, 0, 0),
            "scene_floodlight",
            0.008,
        )
        for corner_y in (-0.96, 3.98):
            for rivet in range(7):
                cylinder(
                    ctx,
                    f"body:corner_fastener_{side}_{corner_y:+.2f}_{rivet}",
                    (side * 1.386, corner_y, 1.05 + rivet * 0.27),
                    0.014,
                    0.016,
                    M["chrome"],
                    10,
                    (0, side * math.pi / 2, 0),
                    "apparatus_body_fastener",
                    0.002,
                )
    rounded_box(
        ctx,
        "body:rear_step",
        (0, rear_y + 0.26, 0.69),
        (2.56, 0.42, 0.22),
        M["diamond"],
        0.055,
        semantic="rear_access_step",
        segments=4,
    )
    text_side(
        ctx,
        "body:left_identification",
        "FIRE RESCUE",
        (-1.405, 2.10, 2.74),
        0.20,
        M["white"],
        -1,
        0.012,
        "apparatus_identification",
    )
    text_side(
        ctx,
        "body:right_identification",
        "ENGINE 1" if not classic else "ENG-8",
        (1.405, 2.10, 2.74),
        0.21,
        M["white"],
        1,
        0.012,
        "apparatus_identification",
    )


def build_reverse_engineered_heavy_pumper_body(ctx, spec, M):
    """Fabricate the 6x4 body recovered from the detailed CadNav OBJ.

    The body is intentionally rebuilt rather than imported.  Its continuous
    section shell, four-compartment cadence, tandem axle spacing, 4.33 m roof
    ladders, roof rail height and rear access ladder all come from measured OBJ
    groups.  Working pump controls, plumbing, retainers and fasteners are then
    added as independently programmable fire-apparatus systems.
    """
    analysis = analyze_fire_truck_reference()
    derived = analysis["derived_programmatic_parameters"]
    measured_axles = tuple(round(value, 3) for value in derived["wheel_centers_y_m"])
    if measured_axles != tuple(round(value, 3) for value in spec.wheelbase):
        raise RuntimeError(
            f"Programmed axle stations drifted from source mesh: {measured_axles}"
        )

    body_front = -1.13
    body_rear = 4.15
    # One watertight longitudinal shell avoids the stacked-box silhouette that
    # made the former apparatus read as a toy.  The mild top tumblehome and
    # tapered rear corners are direct section-level interpretations of the OBJ.
    shell = lofted_vehicle_shell(
        ctx,
        "reference_body:continuous_shell",
        [
            (body_front, 1.205, 1.245, 0.77, 3.02, 0.075),
            (body_front + 0.18, 1.255, 1.275, 0.75, 3.10, 0.085),
            (3.86, 1.255, 1.270, 0.75, 3.10, 0.085),
            (body_rear, 1.190, 1.215, 0.78, 3.03, 0.070),
        ],
        M["red"],
        "reference_calibrated_body_shell",
        8,
        0.022,
    )
    shell["c2w_reference_mesh_page"] = FIRE_TRUCK_MESH_PAGE
    shell["c2w_source_group"] = analysis["source"]["landmarks"]["equipment_body"][
        "name"
    ]
    shell["c2w_programmable_dimensions_m"] = json.dumps(
        [
            spec.length,
            derived["body_width_m"],
            spec.height,
        ]
    )
    rounded_box(
        ctx,
        "reference_body:front_bulkhead",
        (0, body_front + 0.04, 1.91),
        (2.50, 0.18, 2.22),
        M["red_dark"],
        0.045,
        semantic="apparatus_body_front_bulkhead",
        segments=5,
    )
    rounded_box(
        ctx,
        "reference_body:roof_deck",
        (0, 1.51, 3.13),
        (2.48, 5.05, 0.13),
        M["diamond"],
        0.035,
        semantic="apparatus_top_deck",
        segments=4,
    )
    box(
        ctx,
        "reference_body:lower_crossrail",
        (0, body_front - 0.02, 0.78),
        (2.34, 0.22, 0.18),
        M["steel"],
        0.025,
        semantic="cab_body_transition_crossrail",
    )

    # Four source-measured side fields.  The driver's second field is the
    # working midship pump panel; all others are narrow interlocking shutters.
    compartment_fields = (
        ("forward", -0.51, 0.93),
        ("pump", 0.57, 1.02),
        ("tandem_forward", 1.85, 1.22),
        ("tandem_rear", 3.31, 1.25),
    )
    for side in (-1, 1):
        for field_name, center_y, field_length in compartment_fields:
            if side == -1 and field_name == "pump":
                build_pump_panel(ctx, side, center_y, M, classic=False)
            else:
                rollup_compartment(
                    ctx,
                    f"reference_body:{field_name}_{side}",
                    side,
                    center_y,
                    field_length,
                    2.08,
                    1.48,
                    M,
                    panel_material=M["shutter_aluminum"],
                    mount_x=1.247,
                )
        # The long source side moulding is a manufactured extrusion with a
        # reflective inset, not a floating coloured stripe.
        rounded_box(
            ctx,
            f"reference_body:upper_livery_carrier_{side}",
            (side * 1.292, 1.48, 2.94),
            (0.050, 5.02, 0.13),
            M["red_dark"],
            0.018,
            semantic="apparatus_livery_carrier",
            segments=3,
        )
        box(
            ctx,
            f"reference_body:yellow_livery_{side}",
            (side * 1.324, 1.48, 2.94),
            (0.018, 4.91, 0.055),
            M["source_livery"],
            0.004,
            semantic="reflective_livery",
        )
        rounded_box(
            ctx,
            f"reference_body:drip_rail_{side}",
            (side * 1.304, 1.48, 3.055),
            (0.072, 5.12, 0.070),
            M["aluminum"],
            0.018,
            semantic="apparatus_body_drip_rail",
            segments=3,
        )
        rounded_box(
            ctx,
            f"reference_body:running_board_{side}",
            (side * 1.405, 1.28, 0.77),
            (0.28, 4.65, 0.14),
            M["diamond"],
            0.025,
            semantic="apparatus_running_board",
            segments=4,
        )
        for bracket_index, bracket_y in enumerate((-0.72, 0.28, 1.38, 2.55, 3.62)):
            beam(
                ctx,
                f"reference_body:step_bracket_{side}_{bracket_index}",
                (side * 0.73, bracket_y, 0.67),
                (side * 1.39, bracket_y, 0.73),
                0.046,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        for grip in range(21):
            gy = -0.82 + grip * 4.58 / 20
            cylinder(
                ctx,
                f"reference_body:step_grip_{side}_{grip:02d}",
                (side * 1.555, gy, 0.82),
                0.021,
                0.016,
                M["black"],
                12,
                (0, side * math.pi / 2, 0),
                "running_board_grip_aperture",
                0.002,
            )
        # White tandem crown and rub rail reproduce the source's connected
        # wheelhouse surround while leaving both real arch panels readable.
        rounded_box(
            ctx,
            f"reference_body:tandem_fender_crown_{side}",
            (side * 1.335, 2.00, 1.355),
            (0.15, 2.78, 0.18),
            M["white"],
            0.055,
            semantic="tandem_wheelhouse_crown",
            segments=5,
        )
        for marker_index, marker_y in enumerate((-0.86, 0.18, 1.36, 2.64, 3.89)):
            rounded_box(
                ctx,
                f"reference_body:side_marker_{side}_{marker_index}",
                (side * 1.315, marker_y, 2.84),
                (0.055, 0.12, 0.075),
                M["amber"],
                0.016,
                semantic="side_marker_light",
                segments=3,
            )
        for seam_index, seam_y in enumerate((-1.00, 0.03, 1.10, 2.53, 4.00)):
            box(
                ctx,
                f"reference_body:vertical_panel_seam_{side}_{seam_index}",
                (side * 1.330, seam_y, 2.12),
                (0.018, 0.025, 1.69),
                M["red_dark"],
                0.003,
                semantic="apparatus_body_panel_seam",
            )
        for fastener_index in range(12):
            cylinder(
                ctx,
                f"reference_body:rear_corner_fastener_{side}_{fastener_index:02d}",
                (side * 1.328, 4.025, 0.91 + fastener_index * 0.178),
                0.013,
                0.018,
                M["chrome"],
                10,
                (0, side * math.pi / 2, 0),
                "apparatus_body_fastener",
                0.002,
            )

    # Rear face includes a physically mounted access ladder, stacked optics,
    # tow points and inset high-visibility chevrons.
    rear_y = body_rear + 0.045
    rounded_box(
        ctx,
        "reference_body:rear_face",
        (0, rear_y, 1.86),
        (2.39, 0.12, 2.22),
        M["red"],
        0.055,
        semantic="apparatus_rear_face",
        segments=5,
    )
    for stripe in range(12):
        x = -1.02 + stripe * 0.185
        box(
            ctx,
            f"reference_body:rear_chevron_{stripe:02d}",
            (x, rear_y + 0.076, 1.04 + (stripe % 2) * 0.27),
            (0.165, 0.020, 0.105),
            M["source_livery"],
            0.004,
            rotation=(0, 0, math.radians(34 if stripe % 2 == 0 else -34)),
            semantic="rear_chevron",
        )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"reference_body:rear_light_bezel_{side}",
            (side * 0.93, rear_y + 0.082, 2.02),
            (0.25, 0.045, 0.73),
            M["black"],
            0.035,
            semantic="rear_light_housing",
            segments=4,
        )
        for light_index, (z, material) in enumerate(
            (
                (2.27, M["red_lens"]),
                (2.01, M["amber"]),
                (1.75, M["headlamp"]),
            )
        ):
            cylinder(
                ctx,
                f"reference_body:rear_light_{side}_{light_index}",
                (side * 0.93, rear_y + 0.116, z),
                0.087,
                0.030,
                material,
                24,
                (math.pi / 2, 0, 0),
                "rear_warning_light",
                0.006,
            )
        box(
            ctx,
            f"reference_body:rear_ladder_rail_{side}",
            (side * 0.42, rear_y + 0.14, 2.14),
            (0.065, 0.065, 1.72),
            M["aluminum"],
            0.012,
            semantic="rear_access_ladder_rail",
        )
    for rung in range(7):
        cylinder(
            ctx,
            f"reference_body:rear_ladder_rung_{rung}",
            (0, rear_y + 0.18, 1.42 + rung * 0.24),
            0.025,
            0.80,
            M["aluminum"],
            16,
            (0, math.pi / 2, 0),
            "rear_access_ladder_rung",
            0.005,
        )
    rounded_box(
        ctx,
        "reference_body:rear_step",
        (0, rear_y + 0.27, 0.70),
        (2.46, 0.42, 0.22),
        M["diamond"],
        0.055,
        semantic="rear_access_step",
        segments=5,
    )
    for side in (-1, 1):
        beam(
            ctx,
            f"reference_body:rear_step_bracket_{side}",
            (side * 0.72, rear_y - 0.10, 0.62),
            (side * 0.72, rear_y + 0.24, 0.69),
            0.052,
            M["steel"],
            "rear_step_mount_bracket",
            16,
        )
        torus(
            ctx,
            f"reference_body:rear_tow_eye_{side}",
            (side * 0.67, rear_y + 0.20, 0.52),
            0.105,
            0.027,
            M["black"],
            (math.pi / 2, 0, 0),
            "tow_eye",
            32,
            10,
        )

    # Source roof landmarks: paired 4.33 m ladders inside a continuous guard
    # rail, plus rolled hose, hard suction and a working low-profile monitor.
    build_roof_apparatus_facilities(ctx, M, classic=False)
    ladder_lengths = derived["roof_ladder_lengths_m"]
    build_portable_ladder(
        ctx,
        "reference_roof:extension_ladder",
        (-0.64, 1.18),
        ladder_lengths[0],
        0.62,
        3.48,
        M,
        2,
    )
    build_portable_ladder(
        ctx,
        "reference_roof:roof_ladder",
        (0.55, 1.30),
        ladder_lengths[1],
        0.58,
        3.51,
        M,
        1,
    )
    for side in (-1, 1):
        for post_index, post_y in enumerate((-1.02, -0.02, 1.05, 2.12, 3.20, 4.02)):
            beam(
                ctx,
                f"reference_roof:guard_post_{side}_{post_index}",
                (side * 1.15, post_y, 3.12),
                (side * 1.15, post_y, 3.58),
                0.025,
                M["red"],
                "roof_guard_post",
                14,
            )
        for rail_index, rail_z in enumerate((3.34, 3.58)):
            beam(
                ctx,
                f"reference_roof:guard_rail_{side}_{rail_index}",
                (side * 1.15, -1.02, rail_z),
                (side * 1.15, 4.03, rail_z),
                0.026,
                M["red"],
                "roof_guard_rail",
                14,
            )
    for coil_index in range(4):
        torus(
            ctx,
            f"reference_roof:hose_roll_{coil_index}",
            (-0.77 + coil_index * 0.51, -0.28, 3.48),
            0.185,
            0.042,
            M["hose_canvas" if coil_index % 2 == 0 else "hose_yellow"],
            (0, math.pi / 2, 0),
            "roof_stowed_hose_roll",
            36,
            10,
        )
    text_side(
        ctx,
        "reference_body:left_identification",
        "HEAVY PUMPER",
        (-1.355, 2.06, 2.91),
        0.18,
        M["white"],
        -1,
        0.010,
        "apparatus_identification",
    )
    text_side(
        ctx,
        "reference_body:right_identification",
        "ENGINE 6",
        (1.355, 2.06, 2.91),
        0.20,
        M["white"],
        1,
        0.010,
        "apparatus_identification",
    )


def build_modern_ladder_engine(ctx, M):
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, True)
    build_cab(ctx, spec, M, False)
    build_reverse_engineered_heavy_pumper_body(ctx, spec, M)
    # Front air horns and roof beacons match the white-cab reference.
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"cab:air_horn_mount_{side}",
            (side * 0.42, -2.55, 3.37),
            (0.22, 0.24, 0.15),
            M["black"],
            0.030,
            semantic="roof_equipment_mount_saddle",
            segments=3,
        )
        cylinder(
            ctx,
            f"cab:air_horn_{side}",
            (side * 0.42, -2.55, 3.49),
            0.075,
            0.46,
            M["black"],
            20,
            (math.pi / 2, 0, 0),
            "air_horn",
            0.008,
        )
        cylinder(
            ctx,
            f"cab:blue_beacon_base_{side}",
            (side * 0.84, -2.11, 3.36),
            0.125,
            0.12,
            M["black"],
            24,
            semantic="beacon_mount_base",
            bevel=0.012,
        )
        cylinder(
            ctx,
            f"cab:blue_beacon_{side}",
            (side * 0.84, -2.11, 3.49),
            0.095,
            0.18,
            M["blue_lens"],
            24,
            semantic="rotating_beacon",
            bevel=0.015,
        )
    text_front(
        ctx,
        "cab:front_company",
        "E-1",
        (0, -4.53, 1.70),
        0.22,
        M["white"],
        0.018,
        semantic="apparatus_identification",
    )


def build_classic_pumper(ctx, M):
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, True)
    build_cab(ctx, spec, M, True)
    build_engine_body(ctx, spec, M, True)
    # The Sketchfab reference has a deep perforated square grille and a bell.
    front_y = -spec.length / 2 + 0.20
    box(
        ctx,
        "classic:grille_frame",
        (0, front_y - 0.205, 1.35),
        (1.46, 0.08, 0.78),
        M["chrome"],
        0.035,
        semantic="heritage_grille_frame",
    )
    for row in range(7):
        for col in range(13):
            x = -0.62 + col * 0.103
            z = 1.05 + row * 0.095
            cylinder(
                ctx,
                f"classic:grille_aperture_{row:02d}_{col:02d}",
                (x, front_y - 0.255, z),
                0.027,
                0.018,
                M["black"],
                12,
                (math.pi / 2, 0, 0),
                "grille_aperture",
                0.002,
            )
    cylinder(
        ctx,
        "classic:mechanical_siren_housing",
        (0, front_y - 0.31, 1.40),
        0.175,
        0.13,
        M["steel"],
        36,
        (math.pi / 2, 0, 0),
        "mechanical_siren",
        0.012,
    )
    cylinder(
        ctx,
        "classic:mechanical_siren_center",
        (0, front_y - 0.385, 1.40),
        0.095,
        0.045,
        M["aluminum"],
        36,
        (math.pi / 2, 0, 0),
        "mechanical_siren_rotor",
        0.009,
    )
    for vent_index in range(12):
        angle = 2 * math.pi * vent_index / 12
        cylinder(
            ctx,
            f"classic:mechanical_siren_vent_{vent_index}",
            (math.cos(angle) * 0.135, front_y - 0.412, 1.40 + math.sin(angle) * 0.135),
            0.017,
            0.012,
            M["black"],
            12,
            (math.pi / 2, 0, 0),
            "mechanical_siren_vent",
            0.002,
        )
    sphere(
        ctx,
        "classic:bronze_bell",
        (0.67, -0.66, 3.30),
        (0.13, 0.13, 0.15),
        M["chrome"],
        "apparatus_bell",
        20,
        12,
    )
    beam(
        ctx,
        "classic:bell_bracket",
        (0.67, -0.66, 3.12),
        (0.67, -0.66, 3.29),
        0.035,
        M["steel"],
        "bell_bracket",
        12,
    )
    text_front(
        ctx,
        "classic:front_identifier",
        "ENG-8",
        (0, front_y - 0.31, 0.91),
        0.18,
        M["white"],
        0.014,
        semantic="apparatus_identification",
    )


def build_rescue_utility(ctx, M):
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, False)
    # Hooded pickup-like cab silhouette, geometrically distinct from both engines.
    profile_extrude_x(
        ctx,
        "rescue:hood",
        [
            (-3.22, 1.14),
            (-3.22, 1.50),
            (-3.03, 1.69),
            (-2.12, 1.76),
            (-1.94, 1.53),
            (-1.94, 1.14),
        ],
        2.20,
        M["red"],
        "rescue_hood",
        0.095,
    )
    rounded_box(
        ctx,
        "rescue:cab_lower",
        (0, -1.43, 1.50),
        (2.18, 1.86, 1.25),
        M["red"],
        0.13,
        semantic="rescue_cab_body",
        segments=6,
    )
    profile_extrude_x(
        ctx,
        "rescue:cab_upper",
        [(-2.15, 1.80), (-2.06, 2.40), (-1.76, 2.76), (-0.61, 2.76), (-0.55, 1.80)],
        2.10,
        M["white"],
        "rescue_cab_upper",
        0.105,
        open_edges=(0, 1),
    )
    rounded_box(
        ctx,
        "rescue:roof",
        (0, -1.35, 2.78),
        (2.16, 1.75, 0.17),
        M["white"],
        0.075,
        semantic="rescue_cab_roof",
        segments=6,
    )
    # Continuous cowl/plenum and side splash shields bridge hood, windscreen,
    # cab floor and front wheelhouses into one manufactured front clip.
    rounded_box(
        ctx,
        "rescue:cowl_plenum",
        (0, -2.01, 1.84),
        (2.10, 0.34, 0.27),
        M["red_dark"],
        0.055,
        semantic="hood_cab_transition_cowl",
        segments=4,
    )
    box(
        ctx,
        "rescue:windshield_base_channel",
        (0, -2.095, 1.86),
        (2.00, 0.12, 0.11),
        M["black"],
        0.020,
        semantic="windshield_structural_channel",
    )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"rescue:front_clip_splash_shield_{side}",
            (side * 1.075, -2.60, 1.20),
            (0.095, 1.17, 0.53),
            M["red"],
            0.035,
            semantic="front_fender_inner_apron",
            segments=4,
        )
        rounded_box(
            ctx,
            f"rescue:a_pillar_lower_gusset_{side}",
            (side * 1.035, -2.00, 2.13),
            (0.11, 0.30, 0.74),
            M["white"],
            0.040,
            rotation=(0, 0, side * 0.06),
            semantic="cab_a_pillar_structure",
            segments=4,
        )
    box(
        ctx,
        "rescue:hood_center_seam",
        (0, -2.60, 1.785),
        (0.025, 0.96, 0.016),
        M["red_dark"],
        0.004,
        semantic="hood_panel_seam",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"rescue:hood_edge_seam_{side}",
            (side * 0.84, -2.59, 1.775),
            (0.018, 0.94, 0.018),
            M["red_dark"],
            0.004,
            semantic="hood_panel_seam",
        )
        for vent in range(4):
            box(
                ctx,
                f"rescue:hood_vent_{side}_{vent}",
                (side * 0.60, -2.37 + vent * 0.13, 1.795),
                (0.32, 0.055, 0.018),
                M["black"],
                0.006,
                rotation=(0, 0, side * 0.12),
                semantic="hood_vent",
            )
    # The rescue cab also has a true opening and two raked trapezoidal panes.
    rescue_glass_bottom, rescue_glass_top = 1.88, 2.69
    rescue_outer_bottom, rescue_outer_top = 0.98, 0.87
    rescue_center_gap = 0.035
    for side, points in {
        -1: [
            (-rescue_outer_bottom, rescue_glass_bottom),
            (-rescue_center_gap, rescue_glass_bottom),
            (-rescue_center_gap, rescue_glass_top),
            (-rescue_outer_top, rescue_glass_top),
        ],
        1: [
            (rescue_center_gap, rescue_glass_bottom),
            (rescue_outer_bottom, rescue_glass_bottom),
            (rescue_outer_top, rescue_glass_top),
            (rescue_center_gap, rescue_glass_top),
        ],
    }.items():
        sloped_front_panel(
            ctx,
            f"rescue:windshield_{side}",
            points,
            -2.205,
            -1.835,
            0.026,
            M["glass"],
            "cab_windshield",
            0.010,
        )

    def rescue_glass_edge(x, z, outward=0.040):
        factor = (z - rescue_glass_bottom) / (rescue_glass_top - rescue_glass_bottom)
        return (x, -2.205 + factor * 0.370 - outward, z)

    for side in (-1, 1):
        beam(
            ctx,
            f"rescue:windshield_outer_gasket_{side}",
            rescue_glass_edge(side * rescue_outer_bottom, rescue_glass_bottom),
            rescue_glass_edge(side * rescue_outer_top, rescue_glass_top),
            0.024,
            M["black"],
            "window_weatherstrip",
            14,
        )
    beam(
        ctx,
        "rescue:windshield_mullion",
        rescue_glass_edge(0, rescue_glass_bottom),
        rescue_glass_edge(0, rescue_glass_top),
        0.028,
        M["black"],
        "windshield_mullion",
        14,
    )
    beam(
        ctx,
        "rescue:windshield_top_gasket",
        rescue_glass_edge(-rescue_outer_top, rescue_glass_top),
        rescue_glass_edge(rescue_outer_top, rescue_glass_top),
        0.025,
        M["black"],
        "window_weatherstrip",
        14,
    )
    beam(
        ctx,
        "rescue:windshield_lower_gasket",
        rescue_glass_edge(-rescue_outer_bottom, rescue_glass_bottom),
        rescue_glass_edge(rescue_outer_bottom, rescue_glass_bottom),
        0.027,
        M["black"],
        "window_weatherstrip",
        14,
    )
    for side in (-1, 1):
        pivot = rescue_glass_edge(side * 0.73, rescue_glass_bottom + 0.06, 0.065)
        elbow = rescue_glass_edge(side * 0.39, 2.27, 0.065)
        cylinder(
            ctx,
            f"rescue:wiper_pivot_{side}",
            pivot,
            0.034,
            0.030,
            M["black"],
            18,
            (math.pi / 2, 0, 0),
            "windshield_wiper_pivot",
            0.004,
        )
        beam(
            ctx,
            f"rescue:wiper_arm_{side}",
            pivot,
            elbow,
            0.012,
            M["black"],
            "windshield_wiper_arm",
            12,
        )
        beam(
            ctx,
            f"rescue:wiper_blade_{side}",
            rescue_glass_edge(side * 0.58, 2.14, 0.070),
            rescue_glass_edge(side * 0.20, 2.42, 0.070),
            0.015,
            M["rubber"],
            "windshield_wiper",
            12,
        )
    for side in (-1, 1):
        sx = side * 1.085
        for window_index, (py, length) in enumerate(((-1.72, 0.62), (-0.99, 0.52))):
            rounded_box(
                ctx,
                f"rescue:door_window_recess_{side}_{window_index}",
                (side * 1.067, py, 2.29),
                (0.035, length + 0.09, 0.70),
                M["black"],
                0.055,
                semantic="side_window_reveal",
                segments=4,
            )
            box(
                ctx,
                f"rescue:door_window_{side}_{window_index}",
                (sx, py, 2.29),
                (0.035, length, 0.60),
                M["glass_dark"],
                0.050,
                semantic="cab_side_window",
            )
        for seam_y in (-2.05, -1.36, -0.69):
            box(
                ctx,
                f"rescue:door_seam_{side}_{seam_y:+.2f}",
                (sx + side * 0.028, seam_y, 1.73),
                (0.020, 0.020, 1.42),
                M["black"],
                0.004,
                semantic="cab_door_seam",
            )
        for handle_index, py in enumerate((-1.62, -0.91)):
            box(
                ctx,
                f"rescue:door_handle_{side}_{handle_index}",
                (sx + side * 0.045, py, 1.72),
                (0.05, 0.22, 0.06),
                M["chrome"],
                0.014,
                semantic="cab_door_handle",
            )
        box(
            ctx,
            f"rescue:side_step_{side}",
            (side * 1.18, -1.34, 0.86),
            (0.20, 1.46, 0.13),
            M["diamond"],
            0.025,
            semantic="cab_access_step",
        )
        rounded_box(
            ctx,
            f"rescue:side_step_riser_{side}",
            (side * 1.105, -1.34, 1.01),
            (0.10, 1.34, 0.34),
            M["red_dark"],
            0.024,
            semantic="cab_step_riser",
            segments=3,
        )
        for bracket_index, bracket_y in enumerate((-1.70, -0.98)):
            beam(
                ctx,
                f"rescue:side_step_bracket_{side}_{bracket_index}",
                (side * 0.70, bracket_y, 0.68),
                (side * 1.15, bracket_y, 0.82),
                0.042,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        rounded_box(
            ctx,
            f"rescue:mirror_mount_base_{side}",
            (side * 1.095, -1.91, 2.38),
            (0.070, 0.27, 0.39),
            M["black"],
            0.040,
            semantic="mirror_mount_base",
            segments=4,
        )
        for bolt_index, bolt_z in enumerate((2.27, 2.49)):
            cylinder(
                ctx,
                f"rescue:mirror_mount_bolt_{side}_{bolt_index}",
                (side * 1.139, -1.91, bolt_z),
                0.023,
                0.024,
                M["chrome"],
                14,
                (0, side * math.pi / 2, 0),
                "mirror_mount_fastener",
                0.003,
            )
        beam(
            ctx,
            f"rescue:mirror_upper_arm_{side}",
            (sx, -1.94, 2.48),
            (side * 1.34, -2.01, 2.58),
            0.023,
            M["steel"],
            "mirror_support",
            12,
        )
        beam(
            ctx,
            f"rescue:mirror_lower_arm_{side}",
            (sx, -1.94, 2.29),
            (side * 1.34, -2.01, 2.40),
            0.023,
            M["steel"],
            "mirror_support",
            12,
        )
        rounded_box(
            ctx,
            f"rescue:mirror_{side}",
            (side * 1.38, -2.02, 2.49),
            (0.11, 0.22, 0.32),
            M["black"],
            0.045,
            semantic="side_mirror",
            segments=5,
        )
        box(
            ctx,
            f"rescue:mirror_glass_{side}",
            (side * 1.442, -2.02, 2.49),
            (0.012, 0.18, 0.27),
            M["glass"],
            0.015,
            semantic="mirror_glass",
        )
    # Distinct rescue body with four short roll-up lockers per side.
    rounded_box(
        ctx,
        "rescue:body_shell",
        (0, 1.34, 1.69),
        (2.22, 3.45, 2.25),
        M["red"],
        0.085,
        semantic="rescue_module_shell",
        segments=5,
    )
    rounded_box(
        ctx,
        "rescue:module_roof",
        (0, 1.34, 2.84),
        (2.28, 3.52, 0.15),
        M["white"],
        0.055,
        semantic="rescue_module_roof",
        segments=4,
    )
    rounded_box(
        ctx,
        "rescue:module_front_bulkhead",
        (0, -0.385, 1.72),
        (2.18, 0.16, 2.12),
        M["red_dark"],
        0.040,
        semantic="apparatus_body_front_bulkhead",
        segments=4,
    )
    box(
        ctx,
        "rescue:module_lower_crossrail",
        (0, -0.44, 0.78),
        (2.08, 0.18, 0.18),
        M["steel"],
        0.022,
        semantic="cab_body_transition_crossrail",
    )
    for side in (-1, 1):
        for panel, py in enumerate((0.18, 1.08, 1.98, 2.80)):
            rollup_compartment(
                ctx,
                f"rescue:locker_{side}_{panel}",
                side,
                py,
                0.76,
                1.70,
                1.50,
                M,
                mount_x=1.135,
            )
        box(
            ctx,
            f"rescue:reflective_belt_{side}",
            (side * 1.128, 1.34, 1.02),
            (0.032, 3.25, 0.075),
            M["yellow_reflect"],
            0.006,
            semantic="reflective_livery",
        )
        text_side(
            ctx,
            f"rescue:side_label_{side}",
            "RESCUE 3",
            (side * 1.20, 1.31, 2.62),
            0.17,
            M["white"],
            side,
            0.012,
            "apparatus_identification",
        )
        box(
            ctx,
            f"rescue:module_corner_post_front_{side}",
            (side * 1.16, -0.34, 1.75),
            (0.10, 0.12, 2.05),
            M["red_dark"],
            0.018,
            semantic="rescue_module_corner_post",
        )
        box(
            ctx,
            f"rescue:module_corner_post_rear_{side}",
            (side * 1.16, 3.02, 1.75),
            (0.10, 0.12, 2.05),
            M["red_dark"],
            0.018,
            semantic="rescue_module_corner_post",
        )
        for corner_y in (-0.34, 3.02):
            for fastener in range(7):
                cylinder(
                    ctx,
                    f"rescue:module_fastener_{side}_{corner_y:+.2f}_{fastener}",
                    (side * 1.222, corner_y, 1.02 + fastener * 0.27),
                    0.014,
                    0.016,
                    M["chrome"],
                    10,
                    (0, side * math.pi / 2, 0),
                    "apparatus_body_fastener",
                    0.002,
                )
        box(
            ctx,
            f"rescue:lower_rub_rail_{side}",
            (side * 1.145, 1.34, 0.88),
            (0.07, 3.36, 0.11),
            M["aluminum"],
            0.018,
            semantic="apparatus_rub_rail",
        )
        for bracket_index, bracket_y in enumerate((-0.08, 0.86, 1.82, 2.72)):
            beam(
                ctx,
                f"rescue:module_step_bracket_{side}_{bracket_index}",
                (side * 0.70, bracket_y, 0.66),
                (side * 1.13, bracket_y, 0.84),
                0.043,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        rounded_box(
            ctx,
            f"rescue:cab_module_joint_{side}",
            (side * 1.105, -0.44, 1.76),
            (0.070, 0.18, 1.90),
            M["rubber"],
            0.025,
            semantic="cab_body_flexible_joint",
            segments=3,
        )
    build_fire_door_badge(ctx, "rescue:department_badge", -1.39, 2.18, M, "RESCUE 3")
    # Pickup front fascia.  The radiator carrier overlaps the hood front wall,
    # while lower valance, boxed chassis horns and bolted plates carry the
    # bumper.  Headlamp bezels and grille now mount into that continuous frame.
    rounded_box(
        ctx,
        "rescue:radiator_support_carrier",
        (0, -3.205, 1.31),
        (2.12, 0.17, 0.91),
        M["red_dark"],
        0.055,
        semantic="front_fascia_carrier",
        segments=5,
    )
    rounded_box(
        ctx,
        "rescue:lower_fascia_valance",
        (0, -3.235, 0.96),
        (2.04, 0.18, 0.35),
        M["red_dark"],
        0.045,
        semantic="front_fascia_transition",
        segments=4,
    )
    for mount_side in (-1, 1):
        box(
            ctx,
            f"rescue:bumper_frame_horn_{mount_side}",
            (mount_side * 0.70, -3.00, 0.72),
            (0.15, 0.72, 0.15),
            M["steel"],
            0.023,
            semantic="bumper_mount_bracket",
        )
        rounded_box(
            ctx,
            f"rescue:bumper_mount_plate_{mount_side}",
            (mount_side * 0.70, -3.315, 0.72),
            (0.34, 0.07, 0.29),
            M["black"],
            0.023,
            semantic="bumper_mount_plate",
            segments=3,
        )
    rounded_box(
        ctx,
        "rescue:front_bumper",
        (0, -3.28, 0.73),
        (2.30, 0.30, 0.25),
        M["chrome"],
        0.065,
        semantic="front_bumper",
        segments=5,
    )
    rounded_box(
        ctx,
        "rescue:bumper_top_step_pad",
        (0, -3.27, 0.865),
        (1.84, 0.21, 0.045),
        M["rubber"],
        0.012,
        semantic="bumper_anti_slip_step",
        segments=3,
    )
    rounded_box(
        ctx,
        "rescue:front_grille_surround",
        (0, -3.235, 1.28),
        (1.52, 0.07, 0.58),
        M["chrome"],
        0.055,
        semantic="radiator_grille_surround",
        segments=5,
    )
    rounded_box(
        ctx,
        "rescue:front_grille",
        (0, -3.278, 1.28),
        (1.34, 0.035, 0.42),
        M["black"],
        0.040,
        semantic="radiator_grille_recess",
        segments=4,
    )
    for bar in range(7):
        box(
            ctx,
            f"rescue:grille_bar_{bar}",
            (0, -3.302, 1.10 + bar * 0.060),
            (1.22, 0.018, 0.018),
            M["chrome"],
            0.004,
            semantic="radiator_grille_bar",
        )
    for support_index, support_x in enumerate((-0.46, 0.0, 0.46)):
        box(
            ctx,
            f"rescue:grille_vertical_support_{support_index}",
            (support_x, -3.310, 1.28),
            (0.018, 0.018, 0.38),
            M["steel"],
            0.004,
            semantic="radiator_grille_support",
        )
    for fastener_index, fastener_x in enumerate((-0.82, -0.30, 0.30, 0.82)):
        cylinder(
            ctx,
            f"rescue:bumper_face_fastener_{fastener_index}",
            (fastener_x, -3.448, 0.75),
            0.025,
            0.022,
            M["black"],
            14,
            (math.pi / 2, 0, 0),
            "bumper_mount_fastener",
            0.003,
        )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"rescue:headlamp_bezel_{side}",
            (side * 0.86, -3.245, 1.42),
            (0.48, 0.055, 0.34),
            M["black"],
            0.055,
            semantic="headlamp_bezel",
            segments=5,
        )
        rounded_box(
            ctx,
            f"rescue:headlamp_{side}",
            (side * 0.86, -3.278, 1.44),
            (0.35, 0.028, 0.21),
            M["headlamp"],
            0.045,
            semantic="headlamp",
            segments=5,
        )
        box(
            ctx,
            f"rescue:headlamp_reflector_divider_{side}",
            (side * 0.86, -3.296, 1.44),
            (0.018, 0.012, 0.18),
            M["chrome"],
            0.003,
            semantic="headlamp_reflector_divider",
        )
        box(
            ctx,
            f"rescue:front_warning_{side}",
            (side * 0.81, -3.255, 1.10),
            (0.30, 0.035, 0.11),
            M["red_lens"],
            0.025,
            semantic="front_warning_light",
        )
        torus(
            ctx,
            f"rescue:front_tow_eye_{side}",
            (side * 0.62, -3.455, 0.67),
            0.09,
            0.025,
            M["black"],
            (math.pi / 2, 0, 0),
            "tow_eye",
            28,
            8,
        )
    build_emergency_lightbar(
        ctx, "rescue:roof_lightbar", (0, -1.47, 2.94), 1.56, M, blue=True
    )
    build_rescue_cab_interior(ctx, M)
    # Rear chevrons and compact scene lighting.
    for stripe in range(9):
        x = -0.92 + stripe * 0.23
        box(
            ctx,
            f"rescue:rear_chevron_{stripe}",
            (x, 3.09, 1.20 + (stripe % 2) * 0.24),
            (0.20, 0.025, 0.12),
            M["yellow_reflect"],
            0.006,
            rotation=(0, 0, math.radians(28 if stripe % 2 == 0 else -28)),
            semantic="rear_chevron",
        )
    for side in (-1, 1):
        cylinder(
            ctx,
            f"rescue:rear_scene_light_{side}",
            (side * 0.72, 3.105, 2.47),
            0.12,
            0.035,
            M["headlamp"],
            24,
            (math.pi / 2, 0, 0),
            "scene_floodlight",
            0.008,
        )
    rounded_box(
        ctx,
        "rescue:rear_bumper",
        (0, 3.18, 0.70),
        (2.30, 0.34, 0.24),
        M["chrome"],
        0.060,
        semantic="rear_bumper",
        segments=5,
    )
    for mount_side in (-1, 1):
        box(
            ctx,
            f"rescue:rear_bumper_frame_horn_{mount_side}",
            (mount_side * 0.70, 3.00, 0.70),
            (0.15, 0.58, 0.15),
            M["steel"],
            0.022,
            semantic="bumper_mount_bracket",
        )
    text_front(
        ctx,
        "rescue:front_identifier",
        "RESCUE 3",
        (0, -3.326, 0.93),
        0.13,
        M["white"],
        0.010,
        semantic="apparatus_identification",
    )


# ---------------------------------------------------------------------------
# Fire7 multi-mesh reverse-engineered apparatus


def build_reference_fire_cab_v7(ctx, spec, M):
    """Build a continuous full-size crew cab from the assigned mesh source.

    Fire6 accumulated many face-mounted details on a fundamentally box-shaped
    cab.  This replacement starts with five changing longitudinal sections and
    adds inset shaped glazing, structural pillars, proper steps and mounted
    road equipment.  All three fire-apparatus families use different measured
    front/rear stations from :data:`FIRE7_MESH_SOURCES`.
    """
    suite = analyze_fire_truck_reference_suite()
    source_record = suite["sources"][spec.variant]
    calibration = source_record["derived_programmatic_parameters"]
    front_y = float(calibration["cab_front_y_m"])
    rear_y = float(calibration["cab_rear_y_m"])
    cab_length = rear_y - front_y
    half = spec.width * 0.5
    roof_z = {
        "modern_ladder_engine": 3.22,
        "classic_pumper": 3.13,
        "rapid_rescue": 3.08,
    }[spec.variant]

    shell = lofted_vehicle_shell(
        ctx,
        "fire7_cab:continuous_formed_shell",
        [
            (front_y + 0.02, half * 0.88, half * 0.79, 0.79, roof_z - 0.12, 0.16),
            (front_y + 0.13, half * 0.955, half * 0.90, 0.78, roof_z - 0.025, 0.18),
            (front_y + 0.48, half, half * 0.955, 0.77, roof_z, 0.19),
            (rear_y - 0.22, half, half * 0.945, 0.77, roof_z, 0.17),
            (rear_y, half * 0.955, half * 0.91, 0.80, roof_z - 0.055, 0.13),
        ],
        M["red"],
        "reference_cab_continuous_shell",
        10,
        0.014,
    )
    shell["c2w_source_model_id"] = source_record["model_id"]
    shell["c2w_source_mesh_sha256"] = source_record["mesh_sha256"]
    shell["c2w_source_preview_calibration"] = json.dumps(
        calibration, ensure_ascii=False
    )

    # Panoramic split windscreen: black reveal first, laminated glass proud of
    # it, then continuous perimeter seals.  The top is narrower and farther
    # rearward, matching the three downloaded cab-over silhouettes.
    glass_bottom = 1.80
    glass_top = roof_z - 0.24
    outer_bottom = half - 0.105
    outer_top = half - 0.205
    center_gap = 0.028
    reveal_panels = {
        -1: [
            (-outer_bottom, glass_bottom),
            (-center_gap, glass_bottom),
            (-center_gap, glass_top),
            (-outer_top, glass_top),
        ],
        1: [
            (center_gap, glass_bottom),
            (outer_bottom, glass_bottom),
            (outer_top, glass_top),
            (center_gap, glass_top),
        ],
    }
    for side, points in reveal_panels.items():
        sloped_front_panel(
            ctx,
            f"fire7_cab:windshield_reveal_{side}",
            [
                (x * 1.015, z - 0.025 if z == glass_bottom else z + 0.025)
                for x, z in points
            ],
            front_y - 0.070,
            front_y + 0.195,
            0.065,
            M["black"],
            "windshield_deep_reveal",
            0.012,
        )
        inset_points = []
        for x, z in points:
            inset_x = x - math.copysign(0.030, x)
            inset_z = z + (0.030 if z == glass_bottom else -0.030)
            inset_points.append((inset_x, inset_z))
        sloped_front_panel(
            ctx,
            f"fire7_cab:windshield_{side}",
            inset_points,
            front_y - 0.112,
            front_y + 0.160,
            0.022,
            M["glass_dark"],
            "cab_windshield",
            0.006,
        )

    def glass_edge(x, z, outward=0.135):
        factor = (z - glass_bottom) / max(0.001, glass_top - glass_bottom)
        return (x, front_y - 0.01 + factor * 0.25 - outward, z)

    for side in (-1, 1):
        beam(
            ctx,
            f"fire7_cab:windshield_outer_seal_{side}",
            glass_edge(side * outer_bottom, glass_bottom),
            glass_edge(side * outer_top, glass_top),
            0.024,
            M["rubber"],
            "window_weatherstrip",
            16,
        )
    beam(
        ctx,
        "fire7_cab:windshield_center_mullion",
        glass_edge(0, glass_bottom),
        glass_edge(0, glass_top),
        0.027,
        M["black"],
        "windshield_mullion",
        16,
    )
    beam(
        ctx,
        "fire7_cab:windshield_header_seal",
        glass_edge(-outer_top, glass_top),
        glass_edge(outer_top, glass_top),
        0.025,
        M["rubber"],
        "window_weatherstrip",
        16,
    )
    beam(
        ctx,
        "fire7_cab:windshield_lower_seal",
        glass_edge(-outer_bottom, glass_bottom),
        glass_edge(outer_bottom, glass_bottom),
        0.028,
        M["rubber"],
        "window_weatherstrip",
        16,
    )

    # Side openings are shaped prisms rather than scaled rectangles.  Black
    # reveals and separate glass establish actual sheet-metal depth.
    split_y = front_y + cab_length * 0.53
    front_window = [
        (front_y + 0.48, 1.82),
        (split_y - 0.075, 1.82),
        (split_y - 0.075, roof_z - 0.25),
        (front_y + 0.78, roof_z - 0.25),
    ]
    rear_window = [
        (split_y + 0.075, 1.82),
        (rear_y - 0.20, 1.82),
        (rear_y - 0.20, roof_z - 0.27),
        (split_y + 0.075, roof_z - 0.25),
    ]
    for side in (-1, 1):
        for index, panel in enumerate((front_window, rear_window)):
            reveal = [
                (
                    y - 0.035 if point_index in (0, 3) else y + 0.035,
                    z - 0.035 if point_index in (0, 1) else z + 0.035,
                )
                for point_index, (y, z) in enumerate(panel)
            ]
            side_prism_x(
                ctx,
                f"fire7_cab:side_window_reveal_{side}_{index}",
                reveal,
                side * (half - 0.005),
                0.080,
                M["black"],
                "side_window_reveal",
                0.010,
            )
            inset = [
                (
                    y + (0.028 if point_index in (0, 3) else -0.028),
                    z + (0.028 if point_index in (0, 1) else -0.028),
                )
                for point_index, (y, z) in enumerate(panel)
            ]
            side_prism_x(
                ctx,
                f"fire7_cab:side_window_{side}_{index}",
                inset,
                side * (half + 0.041),
                0.022,
                M["glass_dark"],
                "cab_side_window",
                0.005,
            )
        sx = side * (half + 0.057)
        for seam_index, seam_y in enumerate((front_y + 0.40, split_y, rear_y - 0.05)):
            box(
                ctx,
                f"fire7_cab:door_vertical_seam_{side}_{seam_index}",
                (sx, seam_y, 1.49),
                (0.018, 0.020, 1.38),
                M["black"],
                0.003,
                semantic="cab_door_seam",
            )
        box(
            ctx,
            f"fire7_cab:door_belt_seam_{side}",
            (sx, (front_y + rear_y) * 0.5, 1.75),
            (0.018, cab_length - 0.20, 0.020),
            M["black"],
            0.003,
            semantic="cab_door_seam",
        )
        for handle_index, hy in enumerate(
            (front_y + cab_length * 0.36, front_y + cab_length * 0.76)
        ):
            rounded_box(
                ctx,
                f"fire7_cab:flush_handle_{side}_{handle_index}",
                (sx + side * 0.020, hy, 1.60),
                (0.045, 0.24, 0.070),
                M["black"],
                0.018,
                semantic="cab_door_handle",
                segments=4,
            )
            rounded_box(
                ctx,
                f"fire7_cab:handle_pull_{side}_{handle_index}",
                (sx + side * 0.045, hy, 1.60),
                (0.022, 0.14, 0.026),
                M["chrome"],
                0.009,
                semantic="cab_door_handle_insert",
                segments=3,
            )
        # Real two-level cab steps with brackets and perforated traction faces.
        for step_index, (step_z, step_width) in enumerate(((0.73, 0.24), (0.96, 0.17))):
            rounded_box(
                ctx,
                f"fire7_cab:entry_step_{side}_{step_index}",
                (
                    side * (half + step_width * 0.42),
                    front_y + cab_length * 0.69,
                    step_z,
                ),
                (step_width, cab_length * 0.43, 0.095),
                M["diamond"],
                0.020,
                semantic="cab_access_step",
                segments=4,
            )
        for bracket_index, bracket_y in enumerate(
            (front_y + cab_length * 0.55, front_y + cab_length * 0.83)
        ):
            beam(
                ctx,
                f"fire7_cab:step_bracket_{side}_{bracket_index}",
                (side * 0.70, bracket_y, 0.65),
                (side * (half + 0.06), bracket_y, 0.76),
                0.040,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        # Mirror heads use a cast housing, reflective insert and triangulated
        # supports with visible mounting feet.
        mirror_y = front_y + 0.70
        rounded_box(
            ctx,
            f"fire7_cab:mirror_mount_{side}",
            (side * (half + 0.02), mirror_y, 2.36),
            (0.075, 0.30, 0.43),
            M["black"],
            0.038,
            semantic="mirror_mount_base",
            segments=5,
        )
        for arm_index, arm_z in enumerate((2.28, 2.57)):
            beam(
                ctx,
                f"fire7_cab:mirror_arm_{side}_{arm_index}",
                (side * (half + 0.035), mirror_y, arm_z),
                (side * (half + 0.34), mirror_y - 0.12, arm_z + 0.06),
                0.022,
                M["steel"],
                "mirror_support",
                14,
            )
        rounded_box(
            ctx,
            f"fire7_cab:mirror_housing_{side}",
            (side * (half + 0.39), mirror_y - 0.15, 2.46),
            (0.13, 0.29, 0.46),
            M["black"],
            0.060,
            semantic="side_mirror",
            segments=6,
        )
        rounded_box(
            ctx,
            f"fire7_cab:mirror_glass_{side}",
            (side * (half + 0.462), mirror_y - 0.15, 2.46),
            (0.014, 0.235, 0.385),
            M["glass"],
            0.022,
            semantic="mirror_glass",
            segments=5,
        )
        text_side(
            ctx,
            f"fire7_cab:department_wordmark_{side}",
            "CITY FIRE",
            (side * (half + 0.075), front_y + cab_length * 0.70, 1.36),
            0.105,
            M["silver_reflect"],
            side,
            0.005,
            "apparatus_identification",
        )

    # Integrated front carrier, grille, optical stacks and chassis-connected
    # bumper.  Recess depths stay in the centimetre range at true 1:1 scale.
    fascia_y = front_y - 0.075
    rounded_box(
        ctx,
        "fire7_cab:front_fascia_carrier",
        (0, fascia_y, 1.28),
        (spec.width * 0.91, 0.16, 0.88),
        M["red_dark"],
        0.065,
        semantic="front_fascia_carrier",
        segments=7,
    )
    rounded_box(
        ctx,
        "fire7_cab:grille_surround",
        (0, fascia_y - 0.095, 1.27),
        (1.36, 0.055, 0.57),
        M["chrome"],
        0.045,
        semantic="radiator_grille_surround",
        segments=6,
    )
    rounded_box(
        ctx,
        "fire7_cab:grille_recess",
        (0, fascia_y - 0.130, 1.27),
        (1.24, 0.026, 0.47),
        M["black"],
        0.032,
        semantic="radiator_grille_recess",
        segments=5,
    )
    for grille_index in range(13):
        z = 1.06 + grille_index * 0.035
        box(
            ctx,
            f"fire7_cab:grille_louver_{grille_index:02d}",
            (0, fascia_y - 0.151, z),
            (1.13, 0.014, 0.013),
            M["aluminum"],
            0.003,
            semantic="radiator_grille_bar",
        )
    for side in (-1, 1):
        lamp_x = side * (half - 0.29)
        rounded_box(
            ctx,
            f"fire7_cab:headlamp_bezel_{side}",
            (lamp_x, fascia_y - 0.105, 1.37),
            (0.39, 0.050, 0.48),
            M["black"],
            0.050,
            semantic="headlamp_bezel",
            segments=6,
        )
        for optic_index, (optic_z, optic_material) in enumerate(
            (
                (1.48, M["headlamp"]),
                (1.30, M["headlamp"]),
                (1.13, M["amber"]),
            )
        ):
            rounded_box(
                ctx,
                f"fire7_cab:front_optic_{side}_{optic_index}",
                (lamp_x, fascia_y - 0.140, optic_z),
                (0.29, 0.020, 0.115),
                optic_material,
                0.026,
                semantic="headlamp" if optic_index < 2 else "front_turn_signal",
                segments=5,
            )
    bumper_y = front_y - 0.24
    for side in (-1, 1):
        box(
            ctx,
            f"fire7_cab:bumper_horn_{side}",
            (side * 0.70, front_y + 0.06, 0.66),
            (0.15, 0.68, 0.16),
            M["steel"],
            0.020,
            semantic="bumper_mount_bracket",
        )
        rounded_box(
            ctx,
            f"fire7_cab:bumper_mount_plate_{side}",
            (side * 0.70, bumper_y - 0.08, 0.67),
            (0.34, 0.065, 0.27),
            M["black"],
            0.020,
            semantic="bumper_mount_plate",
            segments=4,
        )
    rounded_box(
        ctx,
        "fire7_cab:front_bumper",
        (0, bumper_y, 0.67),
        (spec.width + 0.20, 0.29, 0.24),
        M["chrome"],
        0.055,
        semantic="front_bumper",
        segments=7,
    )
    rounded_box(
        ctx,
        "fire7_cab:bumper_step_insert",
        (0, bumper_y - 0.015, 0.805),
        (spec.width - 0.38, 0.20, 0.035),
        M["rubber"],
        0.010,
        semantic="bumper_anti_slip_step",
        segments=4,
    )
    for side in (-1, 1):
        torus(
            ctx,
            f"fire7_cab:tow_eye_{side}",
            (side * 0.67, bumper_y - 0.16, 0.62),
            0.080,
            0.022,
            M["black"],
            (math.pi / 2, 0, 0),
            "tow_eye",
            28,
            8,
        )

    # Articulated wipers sit on the glass plane instead of being painted lines.
    for side in (-1, 1):
        pivot = glass_edge(side * 0.76, glass_bottom + 0.06, 0.155)
        elbow = glass_edge(side * 0.40, glass_bottom + 0.39, 0.155)
        cylinder(
            ctx,
            f"fire7_cab:wiper_pivot_{side}",
            pivot,
            0.033,
            0.028,
            M["black"],
            18,
            (math.pi / 2, 0, 0),
            "windshield_wiper_pivot",
            0.004,
        )
        beam(
            ctx,
            f"fire7_cab:wiper_arm_{side}",
            pivot,
            elbow,
            0.011,
            M["black"],
            "windshield_wiper_arm",
            12,
        )
        beam(
            ctx,
            f"fire7_cab:wiper_blade_{side}",
            glass_edge(side * 0.60, glass_bottom + 0.26, 0.158),
            glass_edge(side * 0.18, glass_bottom + 0.60, 0.158),
            0.014,
            M["rubber"],
            "windshield_wiper",
            12,
        )

    rounded_box(
        ctx,
        "fire7_cab:roof_crown",
        (0, (front_y + rear_y) * 0.5, roof_z + 0.045),
        (spec.width * 0.96, cab_length - 0.10, 0.095),
        M["red"],
        0.040,
        semantic="cab_roof_crown",
        segments=6,
    )
    build_emergency_lightbar(
        ctx,
        "fire7_cab:lightbar",
        (0, front_y + cab_length * 0.63, roof_z + 0.20),
        spec.width * 0.67,
        M,
        blue=True,
    )
    for marker_index, marker_x in enumerate((-0.84, -0.42, 0.0, 0.42, 0.84)):
        rounded_box(
            ctx,
            f"fire7_cab:clearance_marker_{marker_index}",
            (marker_x, front_y - 0.02, roof_z - 0.06),
            (0.11, 0.055, 0.045),
            M["amber"],
            0.014,
            semantic="cab_clearance_marker",
            segments=4,
        )
    build_cab_interior(ctx, front_y + 1.62, M, crew=True)
    text_front(
        ctx,
        "fire7_cab:front_wordmark",
        "FIRE RESCUE",
        (0, fascia_y - 0.165, 1.76),
        0.105,
        M["silver_reflect"],
        0.005,
        semantic="apparatus_identification",
    )


def build_reference_rear_fabrication_v7(ctx, spec, M, body_rear, body_top, unit_label):
    """Shared fabricated rear termination for pumper and aerial bodies."""
    rear_y = body_rear + 0.055
    rounded_box(
        ctx,
        "fire7_body:rear_face",
        (0, rear_y, (body_top + 0.80) * 0.5),
        (spec.width - 0.12, 0.13, body_top - 0.74),
        M["red"],
        0.050,
        semantic="apparatus_rear_face",
        segments=6,
    )
    for stripe in range(12):
        x = -spec.width * 0.40 + stripe * spec.width * 0.80 / 11
        box(
            ctx,
            f"fire7_body:rear_chevron_{stripe:02d}",
            (x, rear_y + 0.077, 1.05 + (stripe % 2) * 0.22),
            (spec.width * 0.065, 0.016, 0.10),
            M["yellow_reflect"] if stripe % 2 else M["red_dark"],
            0.003,
            rotation=(0, 0, math.radians(32 if stripe % 2 else -32)),
            semantic="rear_chevron",
        )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"fire7_body:rear_light_housing_{side}",
            (side * (spec.width * 0.38), rear_y + 0.082, body_top - 0.65),
            (0.22, 0.045, 0.65),
            M["black"],
            0.030,
            semantic="rear_light_housing",
            segments=5,
        )
        for light_index, (z, material) in enumerate(
            (
                (body_top - 0.44, M["red_lens"]),
                (body_top - 0.66, M["amber"]),
                (body_top - 0.88, M["headlamp"]),
            )
        ):
            cylinder(
                ctx,
                f"fire7_body:rear_optic_{side}_{light_index}",
                (side * (spec.width * 0.38), rear_y + 0.115, z),
                0.073,
                0.025,
                material,
                24,
                (math.pi / 2, 0, 0),
                "rear_warning_light",
                0.006,
            )
        torus(
            ctx,
            f"fire7_body:rear_tow_eye_{side}",
            (side * 0.64, rear_y + 0.18, 0.51),
            0.088,
            0.024,
            M["black"],
            (math.pi / 2, 0, 0),
            "tow_eye",
            28,
            8,
        )
    rounded_box(
        ctx,
        "fire7_body:rear_step",
        (0, rear_y + 0.23, 0.66),
        (spec.width + 0.02, 0.39, 0.18),
        M["diamond"],
        0.045,
        semantic="rear_access_step",
        segments=5,
    )
    text_front(
        ctx,
        "fire7_body:rear_unit_label",
        unit_label,
        (0, rear_y + 0.130, body_top - 0.30),
        0.14,
        M["silver_reflect"],
        0.006,
        semantic="apparatus_identification",
    )


def build_pumper_body_v7(ctx, spec, M):
    """Build the enclosed urban pumper calibrated from model 29256/49268."""
    suite = analyze_fire_truck_reference_suite()
    source = suite["sources"][spec.variant]
    calibration = source["derived_programmatic_parameters"]
    body_front = float(calibration["body_front_y_m"])
    body_rear = float(calibration["body_rear_y_m"])
    body_top = 3.02
    shell = lofted_vehicle_shell(
        ctx,
        "fire7_pumper:continuous_equipment_body",
        [
            (
                body_front,
                spec.width * 0.475,
                spec.width * 0.455,
                0.76,
                body_top - 0.04,
                0.11,
            ),
            (
                body_front + 0.16,
                spec.width * 0.495,
                spec.width * 0.475,
                0.75,
                body_top,
                0.13,
            ),
            (
                body_rear - 0.20,
                spec.width * 0.495,
                spec.width * 0.475,
                0.76,
                body_top,
                0.12,
            ),
            (
                body_rear,
                spec.width * 0.465,
                spec.width * 0.445,
                0.79,
                body_top - 0.07,
                0.09,
            ),
        ],
        M["red"],
        "reference_calibrated_body_shell",
        9,
        0.014,
    )
    shell["c2w_source_model_id"] = source["model_id"]
    shell["c2w_source_mesh_sha256"] = source["mesh_sha256"]
    body_length = body_rear - body_front
    field_count = 4
    field_gap = 0.075
    field_length = (body_length - 0.32 - field_gap * (field_count - 1)) / field_count
    field_centers = [
        body_front + 0.16 + field_length * 0.5 + i * (field_length + field_gap)
        for i in range(field_count)
    ]
    mount_x = spec.width * 0.485
    for side in (-1, 1):
        for field_index, center_y in enumerate(field_centers):
            if side == -1 and field_index == 1:
                build_pump_panel(ctx, side, center_y, M, classic=False)
            else:
                rollup_compartment(
                    ctx,
                    f"fire7_pumper:locker_{side}_{field_index}",
                    side,
                    center_y,
                    field_length,
                    2.10,
                    1.35,
                    M,
                    panel_material=M["shutter_aluminum"],
                    mount_x=mount_x,
                )
        rounded_box(
            ctx,
            f"fire7_pumper:upper_drip_rail_{side}",
            (side * (spec.width * 0.505), (body_front + body_rear) * 0.5, 2.89),
            (0.065, body_length - 0.12, 0.065),
            M["aluminum"],
            0.014,
            semantic="apparatus_body_drip_rail",
            segments=4,
        )
        rounded_box(
            ctx,
            f"fire7_pumper:rub_rail_{side}",
            (side * (spec.width * 0.505), (body_front + body_rear) * 0.5, 1.17),
            (0.075, body_length - 0.18, 0.10),
            M["aluminum"],
            0.017,
            semantic="apparatus_rub_rail",
            segments=4,
        )
        rounded_box(
            ctx,
            f"fire7_pumper:running_board_{side}",
            (side * (spec.width * 0.555), (body_front + body_rear) * 0.5, 0.73),
            (0.25, body_length - 0.20, 0.12),
            M["diamond"],
            0.022,
            semantic="apparatus_running_board",
            segments=4,
        )
        for bracket_index in range(5):
            by = body_front + 0.35 + bracket_index * (body_length - 0.70) / 4
            beam(
                ctx,
                f"fire7_pumper:step_bracket_{side}_{bracket_index}",
                (side * 0.72, by, 0.64),
                (side * (spec.width * 0.55), by, 0.72),
                0.043,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        box(
            ctx,
            f"fire7_pumper:reflective_belt_{side}",
            (side * (spec.width * 0.515), (body_front + body_rear) * 0.5, 1.27),
            (0.022, body_length - 0.20, 0.060),
            M["yellow_reflect"],
            0.004,
            semantic="reflective_livery",
        )
        text_side(
            ctx,
            f"fire7_pumper:side_unit_label_{side}",
            "ENGINE 7",
            (side * (spec.width * 0.535), body_rear - 0.76, 2.78),
            0.13,
            M["silver_reflect"],
            side,
            0.006,
            "apparatus_identification",
        )
        for marker_index, marker_y in enumerate(
            (body_front + 0.18, (body_front + body_rear) * 0.5, body_rear - 0.18)
        ):
            rounded_box(
                ctx,
                f"fire7_pumper:side_marker_{side}_{marker_index}",
                (side * (spec.width * 0.515), marker_y, 2.82),
                (0.035, 0.105, 0.060),
                M["amber"],
                0.014,
                semantic="side_marker_light",
                segments=4,
            )

    # Open hose bed and restrained roof equipment break the slab silhouette.
    rounded_box(
        ctx,
        "fire7_pumper:hosebed_tray",
        (0, body_rear - 1.15, 3.09),
        (spec.width - 0.52, 2.02, 0.12),
        M["black"],
        0.030,
        semantic="hose_bed_tray",
        segments=5,
    )
    for layer in range(4):
        for lane in range(6):
            x = -(spec.width - 0.80) * 0.5 + lane * (spec.width - 0.80) / 5
            y0, y1 = body_rear - 2.02, body_rear - 0.28
            curve_tube(
                ctx,
                f"fire7_pumper:hose_fold_{layer}_{lane}",
                [
                    (x, y0, 3.17 + layer * 0.085),
                    (
                        x + (0.016 if lane % 2 else -0.016),
                        (y0 + y1) * 0.5,
                        3.18 + layer * 0.085,
                    ),
                    (x, y1, 3.17 + layer * 0.085),
                ],
                0.036,
                M["hose_canvas" if lane % 2 else "hose_yellow"],
                "folded_supply_hose",
            )
    build_roof_apparatus_facilities(ctx, M, classic=True)
    build_portable_ladder(
        ctx,
        "fire7_pumper:roof_extension_ladder",
        (0.58, 0.68),
        min(6.20, body_length + 0.72),
        0.55,
        3.36,
        M,
        2,
    )
    build_reference_rear_fabrication_v7(ctx, spec, M, body_rear, body_top, "ENGINE 7")


def build_aerial_ladder_v7(ctx, spec, M, compact=False):
    """Fabricate a nested aerial truss with turntable, waterway and basket."""
    source = analyze_fire_truck_reference_suite()["sources"][spec.variant]
    calibration = source["derived_programmatic_parameters"]
    ladder_length = float(calibration["stowed_ladder_length_m"])
    turntable_y = float(calibration["turntable_center_y_m"])
    center_y = -0.12 if not compact else -0.02
    base_z = 3.34 if not compact else 3.24
    main_width = 0.92 if not compact else 0.82
    main_height = 0.54 if not compact else 0.48

    # Slewing ring and pedestal are separately manufactured assemblies.
    cylinder(
        ctx,
        "fire7_aerial:turntable_lower_bearing",
        (0, turntable_y, 2.78),
        0.66 if not compact else 0.57,
        0.20,
        M["black"],
        64,
        semantic="aerial_turntable_bearing",
        bevel=0.018,
    )
    cylinder(
        ctx,
        "fire7_aerial:turntable_upper_deck",
        (0, turntable_y, 2.93),
        0.58 if not compact else 0.50,
        0.18,
        M["red"],
        64,
        semantic="aerial_turntable_platform",
        bevel=0.025,
    )
    torus(
        ctx,
        "fire7_aerial:slewing_ring",
        (0, turntable_y, 2.88),
        0.55 if not compact else 0.47,
        0.045,
        M["chrome"],
        semantic="aerial_slewing_ring",
        major_segments=64,
        minor_segments=12,
    )
    rounded_box(
        ctx,
        "fire7_aerial:ladder_cradle",
        (0, turntable_y - 0.04, 3.16),
        (1.06, 0.78, 0.30),
        M["red_dark"],
        0.070,
        semantic="aerial_ladder_cradle",
        segments=6,
    )
    for side in (-1, 1):
        beam(
            ctx,
            f"fire7_aerial:elevation_cylinder_{side}",
            (side * 0.34, turntable_y + 0.30, 2.99),
            (side * 0.34, turntable_y - 0.62, base_z + 0.16),
            0.070,
            M["chrome"],
            "aerial_elevation_hydraulic_ram",
            24,
        )
        cylinder(
            ctx,
            f"fire7_aerial:pivot_pin_{side}",
            (side * 0.48, turntable_y - 0.05, 3.18),
            0.10,
            0.16,
            M["steel"],
            28,
            (0, math.pi / 2, 0),
            "aerial_ladder_pivot",
            0.010,
        )

    def ladder_stage(stage_name, length, width, height, z, y_offset, spacing, material):
        y0 = center_y + y_offset - length * 0.5
        y1 = center_y + y_offset + length * 0.5
        for side in (-1, 1):
            x = side * width * 0.5
            beam(
                ctx,
                f"{stage_name}:lower_rail_{side}",
                (x, y0, z),
                (x, y1, z),
                0.041,
                material,
                "aerial_ladder_rail",
                18,
            )
            beam(
                ctx,
                f"{stage_name}:upper_rail_{side}",
                (x, y0, z + height),
                (x, y1, z + height),
                0.039,
                material,
                "aerial_ladder_rail",
                18,
            )
        bay_count = max(8, int(length / spacing))
        for bay in range(bay_count + 1):
            y = y0 + bay * length / bay_count
            beam(
                ctx,
                f"{stage_name}:rung_{bay:02d}",
                (-width * 0.5, y, z + 0.055),
                (width * 0.5, y, z + 0.055),
                0.024,
                material,
                "aerial_ladder_rung",
                14,
            )
            if bay < bay_count:
                yn = y0 + (bay + 1) * length / bay_count
                for side in (-1, 1):
                    x = side * width * 0.5
                    if bay % 2:
                        start, end = (x, y, z), (x, yn, z + height)
                    else:
                        start, end = (x, y, z + height), (x, yn, z)
                    beam(
                        ctx,
                        f"{stage_name}:diagonal_{side}_{bay:02d}",
                        start,
                        end,
                        0.026,
                        material,
                        "aerial_ladder_diagonal",
                        14,
                    )
        return y0, y1

    main_y0, main_y1 = ladder_stage(
        "fire7_aerial:base_section",
        ladder_length,
        main_width,
        main_height,
        base_z,
        0.0,
        0.47,
        M["aluminum"],
    )
    fly_y0, _ = ladder_stage(
        "fire7_aerial:fly_section",
        ladder_length * 0.82,
        main_width * 0.78,
        main_height * 0.76,
        base_z + 0.20,
        -0.30,
        0.43,
        M["steel"],
    )
    if not compact:
        ladder_stage(
            "fire7_aerial:inner_fly_section",
            ladder_length * 0.64,
            main_width * 0.62,
            main_height * 0.58,
            base_z + 0.35,
            -0.54,
            0.39,
            M["aluminum"],
        )
    # Fixed telescopic waterway, carriage rollers and a working tip nozzle.
    beam(
        ctx,
        "fire7_aerial:telescopic_waterway",
        (0, main_y1 - 0.32, base_z - 0.02),
        (0, fly_y0 + 0.28, base_z + 0.13),
        0.044,
        M["steel"],
        "aerial_telescopic_waterway",
        18,
    )
    for roller_index in range(6 if not compact else 4):
        ry = (
            center_y
            - ladder_length * 0.30
            + roller_index * ladder_length * 0.60 / max(1, (5 if not compact else 3))
        )
        for side in (-1, 1):
            torus(
                ctx,
                f"fire7_aerial:carriage_roller_{side}_{roller_index}",
                (side * main_width * 0.43, ry, base_z + 0.14),
                0.065,
                0.018,
                M["black"],
                (math.pi / 2, 0, 0),
                "aerial_ladder_carriage_roller",
                24,
                8,
            )
    tip_y = main_y0 - 0.12
    rounded_box(
        ctx,
        "fire7_aerial:basket_floor",
        (0, tip_y - 0.30, base_z + 0.02),
        (1.34, 0.66, 0.095),
        M["diamond"],
        0.025,
        semantic="aerial_rescue_basket_floor",
        segments=5,
    )
    for corner_index, (x, y) in enumerate(
        (
            (-0.62, tip_y - 0.58),
            (0.62, tip_y - 0.58),
            (-0.62, tip_y - 0.04),
            (0.62, tip_y - 0.04),
        )
    ):
        beam(
            ctx,
            f"fire7_aerial:basket_post_{corner_index}",
            (x, y, base_z + 0.05),
            (x, y, base_z + 0.70),
            0.028,
            M["aluminum"],
            "aerial_rescue_basket_post",
            14,
        )
    for rail_index, rail_z in enumerate((base_z + 0.40, base_z + 0.70)):
        beam(
            ctx,
            f"fire7_aerial:basket_front_rail_{rail_index}",
            (-0.62, tip_y - 0.58, rail_z),
            (0.62, tip_y - 0.58, rail_z),
            0.028,
            M["aluminum"],
            "aerial_rescue_basket_rail",
            14,
        )
        for side in (-1, 1):
            beam(
                ctx,
                f"fire7_aerial:basket_side_rail_{rail_index}_{side}",
                (side * 0.62, tip_y - 0.58, rail_z),
                (side * 0.62, tip_y - 0.04, rail_z),
                0.028,
                M["aluminum"],
                "aerial_rescue_basket_rail",
                14,
            )
    cylinder(
        ctx,
        "fire7_aerial:tip_monitor_swivel",
        (0, tip_y - 0.38, base_z + 0.78),
        0.105,
        0.16,
        M["brass"],
        32,
        semantic="aerial_tip_monitor_swivel",
        bevel=0.012,
    )
    beam(
        ctx,
        "fire7_aerial:tip_monitor_barrel",
        (0, tip_y - 0.38, base_z + 0.84),
        (0, tip_y - 0.84, base_z + 0.92),
        0.055,
        M["brass"],
        "aerial_tip_monitor_barrel",
        20,
    )


def build_aerial_body_v7(ctx, spec, M, compact=False):
    """Build a low-profile equipment body below the stowed aerial."""
    suite = analyze_fire_truck_reference_suite()
    source = suite["sources"][spec.variant]
    calibration = source["derived_programmatic_parameters"]
    body_front = float(calibration["body_front_y_m"])
    body_rear = float(calibration["body_rear_y_m"])
    body_top = 2.76 if compact else 2.84
    shell = lofted_vehicle_shell(
        ctx,
        "fire7_aerial:continuous_equipment_body",
        [
            (
                body_front,
                spec.width * 0.465,
                spec.width * 0.445,
                0.76,
                body_top - 0.05,
                0.10,
            ),
            (
                body_front + 0.18,
                spec.width * 0.495,
                spec.width * 0.470,
                0.75,
                body_top,
                0.12,
            ),
            (
                body_rear - 0.20,
                spec.width * 0.495,
                spec.width * 0.468,
                0.76,
                body_top,
                0.11,
            ),
            (
                body_rear,
                spec.width * 0.458,
                spec.width * 0.440,
                0.80,
                body_top - 0.08,
                0.08,
            ),
        ],
        M["red"],
        "reference_calibrated_aerial_body_shell",
        9,
        0.014,
    )
    shell["c2w_source_model_id"] = source["model_id"]
    shell["c2w_source_mesh_sha256"] = source["mesh_sha256"]
    body_length = body_rear - body_front
    field_count = 4 if not compact else 3
    gap = 0.09
    field_length = (body_length - 0.34 - gap * (field_count - 1)) / field_count
    centers = [
        body_front + 0.17 + field_length * 0.5 + i * (field_length + gap)
        for i in range(field_count)
    ]
    mount_x = spec.width * 0.485
    for side in (-1, 1):
        for field_index, center_y in enumerate(centers):
            if side == -1 and field_index == 0:
                build_pump_panel(ctx, side, center_y, M, classic=False)
            else:
                rollup_compartment(
                    ctx,
                    f"fire7_aerial:locker_{side}_{field_index}",
                    side,
                    center_y,
                    field_length,
                    1.96,
                    1.20,
                    M,
                    panel_material=M["shutter_aluminum"],
                    mount_x=mount_x,
                )
        rounded_box(
            ctx,
            f"fire7_aerial:running_board_{side}",
            (side * (spec.width * 0.555), (body_front + body_rear) * 0.5, 0.72),
            (0.24, body_length - 0.20, 0.12),
            M["diamond"],
            0.022,
            semantic="apparatus_running_board",
            segments=4,
        )
        rounded_box(
            ctx,
            f"fire7_aerial:side_rub_rail_{side}",
            (side * (spec.width * 0.505), (body_front + body_rear) * 0.5, 1.20),
            (0.070, body_length - 0.18, 0.095),
            M["aluminum"],
            0.016,
            semantic="apparatus_rub_rail",
            segments=4,
        )
        box(
            ctx,
            f"fire7_aerial:reflective_belt_{side}",
            (side * (spec.width * 0.514), (body_front + body_rear) * 0.5, 1.31),
            (0.020, body_length - 0.20, 0.055),
            M["yellow_reflect"],
            0.004,
            semantic="reflective_livery",
        )
        for bracket_index in range(5 if not compact else 4):
            by = (
                body_front
                + 0.32
                + bracket_index * (body_length - 0.64) / (4 if not compact else 3)
            )
            beam(
                ctx,
                f"fire7_aerial:step_bracket_{side}_{bracket_index}",
                (side * 0.72, by, 0.64),
                (side * (spec.width * 0.55), by, 0.72),
                0.042,
                M["steel"],
                "step_mount_bracket",
                14,
            )
        text_side(
            ctx,
            f"fire7_aerial:side_label_{side}",
            "TOWER 2" if not compact else "LADDER 4",
            (side * (spec.width * 0.535), body_rear - 0.76, body_top - 0.18),
            0.13,
            M["silver_reflect"],
            side,
            0.006,
            "apparatus_identification",
        )

    # Stowed H-frame stabilizers remain visibly connected to the ladder frame.
    stabilizer_stations = (
        body_front + body_length * 0.28,
        body_front + body_length * 0.76,
    )
    for station_index, sy in enumerate(stabilizer_stations):
        for side in (-1, 1):
            rounded_box(
                ctx,
                f"fire7_aerial:stabilizer_beam_{station_index}_{side}",
                (side * (spec.width * 0.50), sy, 0.91),
                (0.52, 0.22, 0.22),
                M["red_dark"],
                0.035,
                semantic="aerial_stabilizer_beam",
                segments=5,
            )
            cylinder(
                ctx,
                f"fire7_aerial:stabilizer_jack_{station_index}_{side}",
                (side * (spec.width * 0.61), sy, 0.73),
                0.055,
                0.34,
                M["chrome"],
                20,
                semantic="aerial_stabilizer_jack",
                bevel=0.006,
            )
            rounded_box(
                ctx,
                f"fire7_aerial:stabilizer_pad_{station_index}_{side}",
                (side * (spec.width * 0.61), sy, 0.54),
                (0.34, 0.30, 0.075),
                M["steel"],
                0.020,
                semantic="aerial_stabilizer_foot",
                segments=4,
            )
    build_aerial_ladder_v7(ctx, spec, M, compact)
    build_reference_rear_fabrication_v7(
        ctx,
        spec,
        M,
        body_rear,
        body_top,
        "TOWER 2" if not compact else "LADDER 4",
    )


def build_fire7_modern_ladder_engine(ctx, M):
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, True)
    build_reference_fire_cab_v7(ctx, spec, M)
    build_aerial_body_v7(ctx, spec, M, compact=False)


def build_fire7_classic_pumper(ctx, M):
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, True)
    build_reference_fire_cab_v7(ctx, spec, M)
    build_pumper_body_v7(ctx, spec, M)


def build_fire7_rapid_rescue(ctx, M):
    # API name retained for pipeline compatibility; the generated asset is a
    # genuine compact aerial fire engine, never an ambulance or medical box.
    spec = TRUCK_SPECS[ctx.variant]
    build_running_gear(ctx, spec, M, True)
    build_reference_fire_cab_v7(ctx, spec, M)
    build_aerial_body_v7(ctx, spec, M, compact=True)


def build_ambulance_star_of_life(ctx, name, side, center_y, center_z, M, scale=1.0):
    """Build the six-arm EMS mark and Rod of Asclepius as real side geometry."""
    face_x = side * (AMBULANCE_SPEC.width / 2 + 0.058)
    for arm in range(3):
        box(
            ctx,
            f"{name}:six_arm_{arm}",
            (face_x, center_y, center_z),
            (0.028, 0.18 * scale, 0.82 * scale),
            M["ems_blue"],
            0.018,
            rotation=(arm * math.pi / 3, 0, 0),
            semantic="ambulance_star_of_life",
        )
    cylinder(
        ctx,
        name + ":center_disc",
        (face_x + side * 0.018, center_y, center_z),
        0.145 * scale,
        0.025,
        M["ambulance_white"],
        32,
        (0, side * math.pi / 2, 0),
        "ambulance_star_center",
        0.006,
    )
    beam(
        ctx,
        name + ":medical_staff",
        (face_x + side * 0.038, center_y, center_z - 0.29 * scale),
        (face_x + side * 0.038, center_y, center_z + 0.29 * scale),
        0.020 * scale,
        M["ems_blue"],
        "rod_of_asclepius",
        12,
    )
    curve_tube(
        ctx,
        name + ":medical_serpent",
        [
            (face_x + side * 0.052, center_y, center_z - 0.22 * scale),
            (face_x + side * 0.052, center_y + 0.085 * scale, center_z - 0.11 * scale),
            (face_x + side * 0.052, center_y - 0.085 * scale, center_z),
            (face_x + side * 0.052, center_y + 0.080 * scale, center_z + 0.12 * scale),
            (face_x + side * 0.052, center_y, center_z + 0.23 * scale),
        ],
        0.016 * scale,
        M["ambulance_white"],
        "rod_of_asclepius_serpent",
    )


def build_ambulance_compartment(
    ctx,
    name,
    side,
    center_y,
    center_z,
    width_y,
    height_z,
    M,
    window=False,
    patient_entry=False,
):
    """Fabricate one flush Sealtite-style module door with real edge hardware."""
    skin_x = side * (AMBULANCE_SPEC.width / 2 + 0.032)
    recess_x = side * (AMBULANCE_SPEC.width / 2 + 0.010)
    rounded_box(
        ctx,
        name + ":recess",
        (recess_x, center_y, center_z),
        (0.050, width_y + 0.10, height_z + 0.10),
        M["black"],
        0.035,
        semantic="ambulance_compartment_recess",
        segments=4,
    )
    rounded_box(
        ctx,
        name + ":door_skin",
        (skin_x, center_y, center_z),
        (0.055, width_y, height_z),
        M["ambulance_white"],
        0.035,
        semantic="ambulance_patient_entry_door"
        if patient_entry
        else "ambulance_equipment_compartment_door",
        segments=4,
    )
    # Continuous bulb seal and drip rail create the dark, fine perimeter line
    # characteristic of full-size modular ambulance bodies.
    for edge_index, edge_y in enumerate(
        (center_y - width_y / 2, center_y + width_y / 2)
    ):
        box(
            ctx,
            f"{name}:vertical_gasket_{edge_index}",
            (skin_x + side * 0.033, edge_y, center_z),
            (0.026, 0.026, height_z - 0.03),
            M["rubber"],
            0.006,
            semantic="ambulance_door_weather_seal",
        )
    for edge_index, edge_z in enumerate(
        (center_z - height_z / 2, center_z + height_z / 2)
    ):
        box(
            ctx,
            f"{name}:horizontal_gasket_{edge_index}",
            (skin_x + side * 0.033, center_y, edge_z),
            (0.026, width_y - 0.03, 0.026),
            M["rubber"],
            0.006,
            semantic="ambulance_door_weather_seal",
        )
    rounded_box(
        ctx,
        name + ":drip_rail",
        (skin_x + side * 0.045, center_y, center_z + height_z / 2 + 0.075),
        (0.055, width_y + 0.16, 0.075),
        M["aluminum"],
        0.018,
        semantic="ambulance_compartment_drip_rail",
        segments=3,
    )
    # Two load-rated hinges, fasteners and a recessed rotary paddle latch.
    hinge_y = center_y - width_y / 2 + 0.075
    for hinge_index, hinge_z in enumerate(
        (center_z - height_z * 0.29, center_z + height_z * 0.29)
    ):
        rounded_box(
            ctx,
            f"{name}:hinge_{hinge_index}",
            (skin_x + side * 0.052, hinge_y, hinge_z),
            (0.045, 0.17, 0.10),
            M["chrome"],
            0.020,
            semantic="ambulance_door_hinge",
            segments=3,
        )
        for fastener_index, fy in enumerate((hinge_y - 0.045, hinge_y + 0.045)):
            cylinder(
                ctx,
                f"{name}:hinge_fastener_{hinge_index}_{fastener_index}",
                (skin_x + side * 0.082, fy, hinge_z),
                0.012,
                0.018,
                M["black"],
                10,
                (0, side * math.pi / 2, 0),
                "ambulance_door_fastener",
                0.002,
            )
    latch_y = center_y + width_y / 2 - 0.14
    rounded_box(
        ctx,
        name + ":paddle_latch_recess",
        (skin_x + side * 0.050, latch_y, center_z),
        (0.045, 0.25, 0.19),
        M["black"],
        0.035,
        semantic="ambulance_rotary_latch_recess",
        segments=4,
    )
    rounded_box(
        ctx,
        name + ":paddle_latch",
        (skin_x + side * 0.078, latch_y, center_z),
        (0.025, 0.17, 0.085),
        M["chrome"],
        0.025,
        semantic="ambulance_rotary_paddle_latch",
        segments=4,
    )
    cylinder(
        ctx,
        name + ":latch_key",
        (skin_x + side * 0.095, latch_y + 0.068, center_z),
        0.018,
        0.012,
        M["black"],
        12,
        (0, side * math.pi / 2, 0),
        "ambulance_compartment_lock",
        0.002,
    )
    if window:
        window_z = center_z + height_z * 0.17
        rounded_box(
            ctx,
            name + ":window_reveal",
            (skin_x + side * 0.052, center_y, window_z),
            (0.040, width_y * 0.66, height_z * 0.40),
            M["black"],
            0.065,
            semantic="ambulance_patient_door_window_reveal",
            segments=5,
        )
        rounded_box(
            ctx,
            name + ":window_glass",
            (skin_x + side * 0.078, center_y, window_z),
            (0.022, width_y * 0.58, height_z * 0.34),
            M["glass_dark"],
            0.055,
            semantic="ambulance_patient_door_window",
            segments=5,
        )


def build_ambulance_warning_module(ctx, name, side, y, z, M, blue=False):
    """A recessed warning lamp with housing, gasket, reflector and lens optic."""
    x = side * (AMBULANCE_SPEC.width / 2 + 0.067)
    rounded_box(
        ctx,
        name + ":housing",
        (x, y, z),
        (0.070, 0.36, 0.205),
        M["black"],
        0.038,
        semantic="ambulance_warning_light_housing",
        segments=5,
    )
    rounded_box(
        ctx,
        name + ":lens",
        (x + side * 0.044, y, z),
        (0.030, 0.30, 0.155),
        M["blue_lens"] if blue else M["red_lens"],
        0.030,
        semantic="ambulance_warning_light_lens",
        segments=5,
    )
    for optic_index, oy in enumerate((y - 0.09, y, y + 0.09)):
        cylinder(
            ctx,
            f"{name}:optic_{optic_index}",
            (x + side * 0.066, oy, z),
            0.032,
            0.015,
            M["reflector"],
            16,
            (0, side * math.pi / 2, 0),
            "ambulance_warning_light_optic",
            0.003,
        )


def build_type_i_ambulance(ctx, M):
    """Reverse-programmed, full-fabrication Type-I municipal ambulance."""
    spec = AMBULANCE_SPEC
    calibration = analyze_ambulance_reference()
    build_running_gear(ctx, spec, M, rear_dual=True)

    # Ford F450-class front clip: four changing cross sections capture nose
    # taper, shoulder roll and hood crown in one closed surface.
    lofted_vehicle_shell(
        ctx,
        "ambulance:hood_shell",
        [
            (-3.56, 1.00, 0.96, 1.02, 1.47, 0.12),
            (-3.38, 1.08, 1.02, 0.98, 1.58, 0.14),
            (-2.72, 1.12, 1.07, 0.91, 1.67, 0.16),
            (-2.18, 1.10, 1.04, 0.88, 1.71, 0.15),
        ],
        M["ambulance_white"],
        "ambulance_formed_hood",
        6,
        0.022,
    )
    lofted_vehicle_shell(
        ctx,
        "ambulance:cab_lower_shell",
        [
            (-2.31, 1.10, 1.06, 0.78, 1.90, 0.13),
            (-1.70, 1.11, 1.05, 0.77, 1.92, 0.15),
            (-0.66, 1.08, 1.01, 0.79, 1.91, 0.14),
        ],
        M["ambulance_white"],
        "ambulance_cab_lower_body",
        6,
        0.020,
    )
    # The upper cab is a true glazed aperture assembly rather than glass laid
    # over a closed white end-cap.  Painted A/B pillars, roof side rails,
    # header and rear cab wall provide the load path around transparent panes.
    for side in (-1, 1):
        side_prism_x(
            ctx,
            f"ambulance:a_pillar_skin_{side}",
            [
                (-2.18, 1.70),
                (-2.00, 1.70),
                (-1.67, 2.62),
                (-1.84, 2.64),
            ],
            side * 0.985,
            0.155,
            M["ambulance_white"],
            "ambulance_cab_a_pillar_structure",
            0.018,
        )
        rounded_box(
            ctx,
            f"ambulance:b_pillar_{side}",
            (side * 0.985, -0.63, 2.17),
            (0.16, 0.20, 0.98),
            M["ambulance_white"],
            0.045,
            semantic="ambulance_cab_b_pillar_structure",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:roof_side_rail_{side}",
            (side * 0.955, -1.18, 2.59),
            (0.18, 1.12, 0.18),
            M["ambulance_white"],
            0.045,
            semantic="ambulance_cab_roof_side_rail",
            segments=4,
        )
    rounded_box(
        ctx,
        "ambulance:windshield_roof_header",
        (0, -1.74, 2.60),
        (1.92, 0.20, 0.17),
        M["ambulance_white"],
        0.045,
        semantic="ambulance_cab_windshield_header",
        segments=4,
    )
    rounded_box(
        ctx,
        "ambulance:rear_cab_upper_wall",
        (0, -0.61, 2.15),
        (1.92, 0.15, 0.93),
        M["ambulance_white"],
        0.055,
        semantic="ambulance_cab_rear_structure",
        segments=5,
    )
    rounded_box(
        ctx,
        "ambulance:cab_roof",
        (0, -1.37, 2.65),
        (2.04, 1.56, 0.16),
        M["ambulance_white"],
        0.070,
        semantic="ambulance_cab_roof",
        segments=6,
    )
    rounded_box(
        ctx,
        "ambulance:cowl_plenum",
        (0, -2.06, 1.78),
        (2.06, 0.28, 0.20),
        M["plastic"],
        0.050,
        semantic="ambulance_hood_cab_transition",
        segments=5,
    )
    # Hood panel gaps, washer nozzles, intake slots and antenna mounting all
    # sit on the continuous front clip instead of floating above it.
    box(
        ctx,
        "ambulance:hood_center_seam",
        (0, -2.82, 1.685),
        (0.018, 1.25, 0.015),
        M["black"],
        0.003,
        semantic="ambulance_hood_panel_gap",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"ambulance:hood_edge_seam_{side}",
            (side * 0.89, -2.78, 1.625),
            (0.018, 1.17, 0.018),
            M["black"],
            0.003,
            rotation=(0, 0, side * 0.035),
            semantic="ambulance_hood_panel_gap",
        )
        for vent_index in range(5):
            box(
                ctx,
                f"ambulance:cowl_vent_{side}_{vent_index}",
                (side * (0.26 + vent_index * 0.13), -2.095, 1.825),
                (0.075, 0.055, 0.018),
                M["black"],
                0.006,
                semantic="ambulance_cowl_vent",
            )

    # Raked one-piece laminated windscreen with a genuine perimeter gasket and
    # articulated wipers.  The cab shell remains visible as the structural A
    # pillars, eliminating the oversized black glass slab of the earlier car.
    glass_bottom, glass_top = 1.78, 2.58
    outer_bottom, outer_top = 1.00, 0.90
    sloped_front_panel(
        ctx,
        "ambulance:one_piece_windshield",
        [
            (-outer_bottom, glass_bottom),
            (outer_bottom, glass_bottom),
            (outer_top, glass_top),
            (-outer_top, glass_top),
        ],
        -2.215,
        -1.765,
        0.026,
        M["glass"],
        "ambulance_cab_windshield",
        0.009,
    )

    def glass_edge(x, z, outward=0.043):
        factor = (z - glass_bottom) / (glass_top - glass_bottom)
        return (x, -2.215 + factor * 0.450 - outward, z)

    for side in (-1, 1):
        beam(
            ctx,
            f"ambulance:windshield_outer_gasket_{side}",
            glass_edge(side * outer_bottom, glass_bottom),
            glass_edge(side * outer_top, glass_top),
            0.024,
            M["rubber"],
            "ambulance_window_weatherstrip",
            14,
        )
        pivot = glass_edge(side * 0.73, glass_bottom + 0.045, 0.070)
        elbow = glass_edge(side * 0.40, 2.16, 0.068)
        cylinder(
            ctx,
            f"ambulance:wiper_pivot_{side}",
            pivot,
            0.034,
            0.030,
            M["black"],
            18,
            (math.pi / 2, 0, 0),
            "ambulance_wiper_pivot",
            0.004,
        )
        beam(
            ctx,
            f"ambulance:wiper_arm_{side}",
            pivot,
            elbow,
            0.012,
            M["black"],
            "ambulance_wiper_arm",
            12,
        )
        beam(
            ctx,
            f"ambulance:wiper_blade_{side}",
            glass_edge(side * 0.60, 2.02, 0.073),
            glass_edge(side * 0.18, 2.34, 0.073),
            0.015,
            M["rubber"],
            "ambulance_wiper_blade",
            12,
        )
    beam(
        ctx,
        "ambulance:windshield_top_gasket",
        glass_edge(-outer_top, glass_top),
        glass_edge(outer_top, glass_top),
        0.025,
        M["rubber"],
        "ambulance_window_weatherstrip",
        14,
    )
    beam(
        ctx,
        "ambulance:windshield_bottom_gasket",
        glass_edge(-outer_bottom, glass_bottom),
        glass_edge(outer_bottom, glass_bottom),
        0.027,
        M["rubber"],
        "ambulance_window_weatherstrip",
        14,
    )

    # Cab doors, reveal-depth glazing, OEM mirrors and supported running steps.
    for side in (-1, 1):
        side_prism_x(
            ctx,
            f"ambulance:cab_window_reveal_{side}",
            [
                (-2.07, 1.78),
                (-0.64, 1.78),
                (-0.64, 2.57),
                (-1.72, 2.57),
                (-2.02, 2.38),
            ],
            side * 1.042,
            0.060,
            M["black"],
            "ambulance_side_window_reveal",
            0.015,
        )
        side_prism_x(
            ctx,
            f"ambulance:cab_side_window_{side}",
            [
                (-1.99, 1.85),
                (-0.72, 1.85),
                (-0.72, 2.50),
                (-1.69, 2.50),
                (-1.95, 2.34),
            ],
            side * 1.079,
            0.025,
            M["glass_dark"],
            "ambulance_cab_side_window",
            0.007,
        )
        box(
            ctx,
            f"ambulance:cab_window_belt_moulding_{side}",
            (side * 1.099, -1.34, 1.80),
            (0.025, 1.35, 0.040),
            M["black"],
            0.008,
            semantic="ambulance_window_belt_moulding",
        )
        for seam_index, seam_y in enumerate((-2.08, -0.61)):
            box(
                ctx,
                f"ambulance:cab_door_vertical_seam_{side}_{seam_index}",
                (side * 1.084, seam_y, 1.61),
                (0.020, 0.020, 1.49),
                M["black"],
                0.003,
                semantic="ambulance_cab_door_gap",
            )
        box(
            ctx,
            f"ambulance:cab_door_lower_seam_{side}",
            (side * 1.084, -1.33, 0.91),
            (0.020, 1.46, 0.020),
            M["black"],
            0.003,
            semantic="ambulance_cab_door_gap",
        )
        rounded_box(
            ctx,
            f"ambulance:cab_door_handle_recess_{side}",
            (side * 1.100, -0.88, 1.73),
            (0.035, 0.28, 0.10),
            M["black"],
            0.025,
            semantic="ambulance_cab_handle_recess",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:cab_door_handle_{side}",
            (side * 1.126, -0.88, 1.73),
            (0.025, 0.20, 0.045),
            M["chrome"],
            0.016,
            semantic="ambulance_cab_door_handle",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:mirror_mount_base_{side}",
            (side * 1.075, -1.92, 2.15),
            (0.070, 0.27, 0.40),
            M["black"],
            0.040,
            semantic="ambulance_mirror_mount",
            segments=4,
        )
        for arm_index, arm_z in enumerate((2.05, 2.29)):
            beam(
                ctx,
                f"ambulance:mirror_arm_{side}_{arm_index}",
                (side * 1.09, -1.96, arm_z),
                (side * 1.39, -2.05, arm_z + 0.08),
                0.022,
                M["steel"],
                "ambulance_mirror_support",
                12,
            )
        rounded_box(
            ctx,
            f"ambulance:mirror_housing_{side}",
            (side * 1.43, -2.07, 2.20),
            (0.13, 0.26, 0.39),
            M["black"],
            0.055,
            semantic="ambulance_side_mirror",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:mirror_glass_{side}",
            (side * 1.502, -2.07, 2.20),
            (0.016, 0.21, 0.33),
            M["glass"],
            0.035,
            semantic="ambulance_mirror_glass",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:cab_step_{side}",
            (side * 1.18, -1.28, 0.69),
            (0.24, 1.28, 0.15),
            M["diamond"],
            0.035,
            semantic="ambulance_cab_running_step",
            segments=4,
        )
        for bracket_index, bracket_y in enumerate((-1.72, -0.96)):
            beam(
                ctx,
                f"ambulance:cab_step_bracket_{side}_{bracket_index}",
                (side * 0.72, bracket_y, 0.57),
                (side * 1.16, bracket_y, 0.66),
                0.040,
                M["steel"],
                "ambulance_step_mount_bracket",
                14,
            )
        curve_tube(
            ctx,
            f"ambulance:fender_shoulder_crease_{side}",
            [
                (side * 1.105, -3.43, 1.47),
                (side * 1.125, -2.86, 1.62),
                (side * 1.105, -2.18, 1.70),
            ],
            0.012,
            M["black"],
            "ambulance_fender_shoulder_panel_gap",
        )

    # Structurally continuous grille carrier, boxed bumper mounts and detailed
    # lamp optics make the front read as an OEM heavy-duty chassis, not a face
    # made from isolated rectangles.
    rounded_box(
        ctx,
        "ambulance:front_fascia_carrier",
        (0, -3.535, 1.26),
        (2.12, 0.20, 0.92),
        M["ambulance_white"],
        0.075,
        semantic="ambulance_front_fascia_carrier",
        segments=6,
    )
    rounded_box(
        ctx,
        "ambulance:grille_surround",
        (0, -3.665, 1.29),
        (1.52, 0.085, 0.72),
        M["chrome"],
        0.070,
        semantic="ambulance_radiator_grille_surround",
        segments=5,
    )
    rounded_box(
        ctx,
        "ambulance:grille_recess",
        (0, -3.714, 1.29),
        (1.36, 0.028, 0.60),
        M["black"],
        0.050,
        semantic="ambulance_radiator_grille_recess",
        segments=4,
    )
    for grille_index in range(7):
        box(
            ctx,
            f"ambulance:grille_bar_{grille_index}",
            (0, -3.735, 1.03 + grille_index * 0.087),
            (1.22, 0.020, 0.024),
            M["chrome"],
            0.005,
            semantic="ambulance_radiator_grille_bar",
        )
    for support_x in (-0.42, 0.0, 0.42):
        box(
            ctx,
            f"ambulance:grille_support_{support_x:+.2f}",
            (support_x, -3.741, 1.29),
            (0.022, 0.018, 0.53),
            M["steel"],
            0.003,
            semantic="ambulance_grille_support",
        )
    sphere(
        ctx,
        "ambulance:grille_fleet_medallion",
        (0, -3.765, 1.29),
        (0.19, 0.035, 0.105),
        M["ems_blue"],
        "ambulance_grille_badge",
        24,
        12,
    )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"ambulance:headlamp_bezel_{side}",
            (side * 0.92, -3.660, 1.30),
            (0.38, 0.090, 0.65),
            M["black"],
            0.050,
            semantic="ambulance_headlamp_bezel",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:headlamp_lens_{side}",
            (side * 0.92, -3.715, 1.38),
            (0.30, 0.030, 0.38),
            M["headlamp"],
            0.040,
            semantic="ambulance_headlamp",
            segments=5,
        )
        for optic_index, optic_z in enumerate((1.29, 1.46)):
            cylinder(
                ctx,
                f"ambulance:headlamp_optic_{side}_{optic_index}",
                (side * 0.92, -3.740, optic_z),
                0.060,
                0.012,
                M["reflector"],
                18,
                (math.pi / 2, 0, 0),
                "ambulance_headlamp_optic",
                0.003,
            )
        box(
            ctx,
            f"ambulance:front_turn_signal_{side}",
            (side * 0.92, -3.719, 1.09),
            (0.29, 0.027, 0.13),
            M["amber"],
            0.018,
            semantic="ambulance_front_turn_signal",
        )
        box(
            ctx,
            f"ambulance:bumper_frame_horn_{side}",
            (side * 0.68, -3.33, 0.66),
            (0.16, 0.68, 0.16),
            M["steel"],
            0.024,
            semantic="ambulance_bumper_mount_bracket",
        )
    rounded_box(
        ctx,
        "ambulance:front_bumper",
        (0, -3.69, 0.69),
        (2.26, 0.28, 0.22),
        M["chrome"],
        0.055,
        semantic="ambulance_front_bumper",
        segments=5,
    )
    rounded_box(
        ctx,
        "ambulance:front_bumper_step_pad",
        (0, -3.70, 0.835),
        (1.72, 0.22, 0.045),
        M["rubber"],
        0.012,
        semantic="ambulance_bumper_step_pad",
        segments=3,
    )
    rounded_box(
        ctx,
        "ambulance:lower_air_dam",
        (0, -3.745, 0.54),
        (1.64, 0.16, 0.20),
        M["black"],
        0.045,
        semantic="ambulance_front_air_dam",
        segments=5,
    )
    rounded_box(
        ctx,
        "ambulance:front_license_mount",
        (0, -3.835, 0.59),
        (0.48, 0.035, 0.20),
        M["black"],
        0.025,
        semantic="ambulance_license_plate_mount",
        segments=4,
    )
    for fastener_index, fastener_x in enumerate((-0.80, -0.28, 0.28, 0.80)):
        cylinder(
            ctx,
            f"ambulance:bumper_fastener_{fastener_index}",
            (fastener_x, -3.855, 0.70),
            0.024,
            0.020,
            M["black"],
            14,
            (math.pi / 2, 0, 0),
            "ambulance_bumper_fastener",
            0.003,
        )
    # Polished grille guard with chassis-backed uprights, cross tubes and
    # rubber-faced over-riders, based on the archived F450 reference.
    for guard_x in (-0.73, 0.73):
        beam(
            ctx,
            f"ambulance:grille_guard_upright_{guard_x:+.2f}",
            (guard_x, -3.86, 0.70),
            (guard_x, -3.86, 1.66),
            0.043,
            M["chrome"],
            "ambulance_grille_guard_upright",
            18,
        )
        rounded_box(
            ctx,
            f"ambulance:grille_guard_mount_{guard_x:+.2f}",
            (guard_x, -3.74, 0.72),
            (0.18, 0.38, 0.16),
            M["steel"],
            0.030,
            semantic="ambulance_grille_guard_mount",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:grille_guard_overrider_{guard_x:+.2f}",
            (guard_x, -3.91, 1.18),
            (0.14, 0.09, 0.39),
            M["black"],
            0.035,
            semantic="ambulance_grille_guard_overrider",
            segments=4,
        )
    for guard_z in (0.86, 1.57):
        beam(
            ctx,
            f"ambulance:grille_guard_cross_tube_{guard_z:.2f}",
            (-0.98, -3.86, guard_z),
            (0.98, -3.86, guard_z),
            0.040,
            M["chrome"],
            "ambulance_grille_guard_cross_tube",
            18,
        )
    build_emergency_lightbar(
        ctx, "ambulance:cab_lightbar", (0, -1.42, 2.78), 1.72, M, blue=True
    )
    build_rescue_cab_interior(ctx, M)

    # Fully welded 150-inch patient module with rounded extrusions and a real
    # cab-module isolation joint.  Dimensions are manufacturer constrained.
    module_front = 3.62 - spec.module_length
    module_center = (module_front + 3.62) * 0.5
    rounded_box(
        ctx,
        "ambulance:patient_module_shell",
        (0, module_center, 1.88),
        (spec.module_width, spec.module_length, 2.12),
        M["ambulance_white"],
        0.105,
        semantic="ambulance_welded_module_shell",
        segments=7,
    )
    rounded_box(
        ctx,
        "ambulance:module_roof_cap",
        (0, module_center, 2.96),
        (spec.module_width + 0.08, spec.module_length + 0.08, 0.16),
        M["ambulance_white"],
        0.070,
        semantic="ambulance_module_roof_cap",
        segments=6,
    )
    rounded_box(
        ctx,
        "ambulance:module_front_bulkhead",
        (0, module_front - 0.015, 1.88),
        (spec.module_width - 0.08, 0.16, 1.98),
        M["ambulance_white"],
        0.055,
        semantic="ambulance_module_front_bulkhead",
        segments=5,
    )
    rounded_box(
        ctx,
        "ambulance:cab_module_boot_outer",
        (0, module_front - 0.20, 1.76),
        (1.46, 0.46, 1.42),
        M["black"],
        0.095,
        semantic="ambulance_cab_module_boot",
        segments=6,
    )
    rounded_box(
        ctx,
        "ambulance:cab_module_boot_collar",
        (0, module_front - 0.41, 1.76),
        (1.58, 0.11, 1.53),
        M["aluminum"],
        0.080,
        semantic="ambulance_cab_module_boot_collar",
        segments=5,
    )
    for lamp_index, lamp_x in enumerate((-0.93, -0.62, -0.31, 0.0, 0.31, 0.62, 0.93)):
        rounded_box(
            ctx,
            f"ambulance:module_front_warning_housing_{lamp_index}",
            (lamp_x, module_front - 0.105, 2.66),
            (0.25, 0.065, 0.17),
            M["black"],
            0.034,
            semantic="ambulance_module_front_warning_housing",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:module_front_warning_lens_{lamp_index}",
            (lamp_x, module_front - 0.148, 2.66),
            (0.20, 0.025, 0.12),
            M["red_lens"] if lamp_index % 2 == 0 else M["headlamp"],
            0.026,
            semantic="ambulance_module_front_warning_lens",
            segments=4,
        )
    for clearance_index, clearance_x in enumerate((-0.98, -0.49, 0.0, 0.49, 0.98)):
        rounded_box(
            ctx,
            f"ambulance:module_front_clearance_{clearance_index}",
            (clearance_x, module_front - 0.150, 2.92),
            (0.12, 0.025, 0.055),
            M["amber"],
            0.016,
            semantic="ambulance_clearance_marker",
            segments=4,
        )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"ambulance:cab_module_flexible_joint_{side}",
            (side * 1.07, module_front - 0.08, 1.82),
            (0.085, 0.19, 1.80),
            M["rubber"],
            0.030,
            semantic="ambulance_cab_module_isolation_joint",
            segments=4,
        )
        box(
            ctx,
            f"ambulance:module_lower_mount_rail_{side}",
            (side * 1.08, module_center, 0.84),
            (0.14, spec.module_length - 0.15, 0.18),
            M["steel"],
            0.022,
            semantic="ambulance_module_mount_rail",
        )
        for mount_index, mount_y in enumerate(
            (module_front + 0.42, module_center, 3.18)
        ):
            beam(
                ctx,
                f"ambulance:module_mount_gusset_{side}_{mount_index}",
                (side * 0.70, mount_y, 0.64),
                (side * 1.08, mount_y, 0.86),
                0.048,
                M["steel"],
                "ambulance_module_mount_gusset",
                14,
            )
        # Multi-layer reflective livery is proud of the body and follows the
        # full module rather than being baked into a flat colour texture.
        box(
            ctx,
            f"ambulance:module_red_belt_{side}",
            (side * 1.231, module_center, 1.53),
            (0.030, spec.module_length - 0.15, 0.38),
            M["ambulance_red"],
            0.006,
            semantic="ambulance_reflective_livery_band",
        )
        box(
            ctx,
            f"ambulance:module_gold_pinstripe_top_{side}",
            (side * 1.249, module_center, 1.76),
            (0.018, spec.module_length - 0.12, 0.050),
            M["yellow_reflect"],
            0.004,
            semantic="ambulance_reflective_pinstripe",
        )
        box(
            ctx,
            f"ambulance:module_gold_pinstripe_bottom_{side}",
            (side * 1.249, module_center, 1.30),
            (0.018, spec.module_length - 0.12, 0.050),
            M["yellow_reflect"],
            0.004,
            semantic="ambulance_reflective_pinstripe",
        )
        box(
            ctx,
            f"ambulance:module_rub_rail_{side}",
            (side * 1.252, module_center, 0.92),
            (0.075, spec.module_length - 0.10, 0.11),
            M["aluminum"],
            0.018,
            semantic="ambulance_module_rub_rail",
        )
        for corner_name, corner_y in (("front", module_front), ("rear", 3.62)):
            rounded_box(
                ctx,
                f"ambulance:module_corner_extrusion_{side}_{corner_name}",
                (side * 1.216, corner_y, 1.89),
                (0.10, 0.12, 2.02),
                M["aluminum"],
                0.030,
                semantic="ambulance_module_corner_extrusion",
                segments=4,
            )
            for fastener_index in range(8):
                cylinder(
                    ctx,
                    f"ambulance:corner_fastener_{side}_{corner_name}_{fastener_index}",
                    (side * 1.279, corner_y, 1.02 + fastener_index * 0.25),
                    0.012,
                    0.014,
                    M["chrome"],
                    10,
                    (0, side * math.pi / 2, 0),
                    "ambulance_body_fastener",
                    0.002,
                )

    # Side door schedule is deliberately asymmetric, matching real EMS access
    # patterns.  The camera-side has oxygen/ALS/backboard lockers; curbside has
    # a glazed patient entry plus battery and equipment compartments.
    for index, (center_y, width_y, height_z) in enumerate(
        ((-0.12, 0.76, 1.60), (0.83, 0.86, 1.48), (2.82, 0.92, 1.62))
    ):
        build_ambulance_compartment(
            ctx,
            f"ambulance:street_compartment_{index}",
            -1,
            center_y,
            1.80,
            width_y,
            height_z,
            M,
        )
    build_ambulance_compartment(
        ctx, "ambulance:curb_battery_compartment", 1, -0.10, 1.62, 0.72, 1.22, M
    )
    build_ambulance_compartment(
        ctx,
        "ambulance:curb_patient_entry",
        1,
        0.96,
        1.79,
        0.92,
        1.76,
        M,
        window=True,
        patient_entry=True,
    )
    build_ambulance_compartment(
        ctx, "ambulance:curb_backboard_compartment", 1, 2.75, 1.81, 1.02, 1.62, M
    )

    # Side warning lights use separate housings, gaskets, lenses and internal
    # optics.  Two scene lights and marker lamps complete each elevation.
    for side in (-1, 1):
        for lamp_index, lamp_y in enumerate((-0.23, 0.78, 1.82, 2.92)):
            build_ambulance_warning_module(
                ctx,
                f"ambulance:side_warning_{side}_{lamp_index}",
                side,
                lamp_y,
                2.67,
                M,
                blue=(lamp_index + (1 if side > 0 else 0)) % 2 == 0,
            )
        rounded_box(
            ctx,
            f"ambulance:side_scene_light_housing_{side}",
            (side * 1.274, 1.39, 2.36),
            (0.065, 0.48, 0.29),
            M["black"],
            0.040,
            semantic="ambulance_scene_light_housing",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:side_scene_light_lens_{side}",
            (side * 1.314, 1.39, 2.36),
            (0.025, 0.41, 0.22),
            M["headlamp"],
            0.035,
            semantic="ambulance_scene_light",
            segments=4,
        )
        for marker_index, marker_y in enumerate(
            (module_front + 0.18, 1.18, 2.28, 3.43)
        ):
            rounded_box(
                ctx,
                f"ambulance:side_marker_{side}_{marker_index}",
                (side * 1.285, marker_y, 0.99),
                (0.035, 0.13, 0.065),
                M["amber"] if marker_index < 3 else M["red_lens"],
                0.018,
                semantic="ambulance_side_marker_light",
                segments=4,
            )
        text_side(
            ctx,
            f"ambulance:department_lettering_{side}",
            "CITY FIRE & EMS",
            (side * 1.286, 0.34, 1.53),
            0.17,
            M["ambulance_white"],
            side,
            0.012,
            "ambulance_department_lettering",
        )
        text_side(
            ctx,
            f"ambulance:paramedic_lettering_{side}",
            "PARAMEDIC 12",
            (side * 1.286, 2.78, 1.10),
            0.125,
            M["ems_blue"],
            side,
            0.010,
            "ambulance_unit_lettering",
        )
    build_ambulance_star_of_life(ctx, "ambulance:street_star", -1, 1.88, 2.18, M, 0.80)
    build_ambulance_star_of_life(ctx, "ambulance:curb_star", 1, 2.02, 2.18, M, 0.78)

    # Roof HVAC, exhaust fans, antennae and perimeter clearance lights remain
    # visible in aerial views and establish the patient module as working plant.
    rounded_box(
        ctx,
        "ambulance:roof_hvac_plenum",
        (0, 1.50, 3.08),
        (1.22, 1.02, 0.25),
        M["ambulance_white"],
        0.090,
        semantic="ambulance_roof_hvac",
        segments=6,
    )
    for grille_index in range(7):
        box(
            ctx,
            f"ambulance:roof_hvac_louver_{grille_index}",
            (0, 1.18 + grille_index * 0.10, 3.218),
            (0.80, 0.050, 0.018),
            M["black"],
            0.004,
            semantic="ambulance_hvac_louver",
        )
    for fan_index, fan_y in enumerate((0.20, 2.72)):
        cylinder(
            ctx,
            f"ambulance:roof_exhaust_fan_{fan_index}",
            (0, fan_y, 3.075),
            0.20,
            0.13,
            M["aluminum"],
            32,
            semantic="ambulance_roof_exhaust_fan",
            bevel=0.018,
        )
        for blade_index in range(5):
            angle = 2 * math.pi * blade_index / 5
            box(
                ctx,
                f"ambulance:roof_fan_blade_{fan_index}_{blade_index}",
                (math.cos(angle) * 0.09, fan_y + math.sin(angle) * 0.09, 3.145),
                (0.055, 0.13, 0.018),
                M["black"],
                0.008,
                rotation=(0, 0, angle),
                semantic="ambulance_roof_fan_blade",
            )
    beam(
        ctx,
        "ambulance:radio_antenna",
        (0.66, 1.98, 3.06),
        (0.73, 1.98, 3.76),
        0.014,
        M["black"],
        "ambulance_radio_antenna",
        10,
    )
    sphere(
        ctx,
        "ambulance:radio_antenna_tip",
        (0.73, 1.98, 3.76),
        (0.028, 0.028, 0.028),
        M["black"],
        "ambulance_antenna_tip",
        12,
        8,
    )

    # Rear double-door system, glazing, warning package and folding loading
    # platform.  All hinges and locking rods have visible attachment points.
    rear_y = 3.665
    for leaf in (-1, 1):
        door_x = leaf * 0.52
        rounded_box(
            ctx,
            f"ambulance:rear_door_recess_{leaf}",
            (door_x, rear_y - 0.018, 1.78),
            (0.96, 0.055, 1.90),
            M["black"],
            0.050,
            semantic="ambulance_rear_door_recess",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:rear_door_skin_{leaf}",
            (door_x, rear_y + 0.020, 1.78),
            (0.89, 0.045, 1.82),
            M["ambulance_white"],
            0.045,
            semantic="ambulance_rear_patient_door",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:rear_window_reveal_{leaf}",
            (door_x, rear_y + 0.052, 2.21),
            (0.64, 0.035, 0.58),
            M["black"],
            0.065,
            semantic="ambulance_rear_window_reveal",
            segments=5,
        )
        rounded_box(
            ctx,
            f"ambulance:rear_window_glass_{leaf}",
            (door_x, rear_y + 0.078, 2.21),
            (0.56, 0.020, 0.50),
            M["glass_dark"],
            0.055,
            semantic="ambulance_rear_window",
            segments=5,
        )
        for hinge_index, hinge_z in enumerate((1.10, 1.70, 2.43)):
            hinge_x = leaf * 1.01
            rounded_box(
                ctx,
                f"ambulance:rear_hinge_{leaf}_{hinge_index}",
                (hinge_x, rear_y + 0.065, hinge_z),
                (0.18, 0.055, 0.10),
                M["chrome"],
                0.020,
                semantic="ambulance_rear_door_hinge",
                segments=3,
            )
        cylinder(
            ctx,
            f"ambulance:rear_locking_rod_{leaf}",
            (leaf * 0.14, rear_y + 0.095, 1.64),
            0.018,
            1.36,
            M["chrome"],
            12,
            semantic="ambulance_rear_door_locking_rod",
            bevel=0.003,
        )
        rounded_box(
            ctx,
            f"ambulance:rear_paddle_latch_{leaf}",
            (leaf * 0.14, rear_y + 0.115, 1.63),
            (0.18, 0.045, 0.12),
            M["chrome"],
            0.025,
            semantic="ambulance_rear_door_latch",
            segments=4,
        )
    for lamp_index, lamp_x in enumerate((-0.85, -0.36, 0.36, 0.85)):
        rounded_box(
            ctx,
            f"ambulance:rear_warning_housing_{lamp_index}",
            (lamp_x, rear_y + 0.070, 2.73),
            (0.32, 0.060, 0.20),
            M["black"],
            0.035,
            semantic="ambulance_rear_warning_housing",
            segments=4,
        )
        rounded_box(
            ctx,
            f"ambulance:rear_warning_lens_{lamp_index}",
            (lamp_x, rear_y + 0.110, 2.73),
            (0.27, 0.025, 0.15),
            M["blue_lens"] if lamp_index in (1, 2) else M["red_lens"],
            0.028,
            semantic="ambulance_rear_warning_lens",
            segments=4,
        )
    for chevron_index in range(10):
        x = -0.97 + chevron_index * 0.215
        box(
            ctx,
            f"ambulance:rear_chevron_{chevron_index}",
            (x, rear_y + 0.106, 0.98 + (chevron_index % 2) * 0.18),
            (0.19, 0.022, 0.105),
            M["yellow_reflect"] if chevron_index % 2 else M["ambulance_red"],
            0.004,
            rotation=(0, 0, math.radians(31 if chevron_index % 2 else -31)),
            semantic="ambulance_rear_chevron",
        )
    rounded_box(
        ctx,
        "ambulance:rear_bumper_support",
        (0, 3.54, 0.49),
        (2.12, 0.46, 0.20),
        M["steel"],
        0.045,
        semantic="ambulance_rear_bumper_support",
        segments=4,
    )
    rounded_box(
        ctx,
        "ambulance:folding_loading_step",
        (0, 3.83, 0.47),
        (1.58, 0.56, 0.17),
        M["diamond"],
        0.055,
        semantic="ambulance_folding_loading_step",
        segments=5,
    )
    for grip_index in range(18):
        gx = -0.68 + (grip_index % 9) * 0.17
        gy = 3.68 + (grip_index // 9) * 0.20
        rounded_box(
            ctx,
            f"ambulance:rear_step_grip_{grip_index}",
            (gx, gy, 0.565),
            (0.10, 0.065, 0.018),
            M["black"],
            0.012,
            semantic="ambulance_loading_step_grip",
            segments=3,
        )
    for bracket_side in (-1, 1):
        beam(
            ctx,
            f"ambulance:rear_step_hinge_arm_{bracket_side}",
            (bracket_side * 0.57, 3.48, 0.58),
            (bracket_side * 0.57, 3.82, 0.50),
            0.045,
            M["steel"],
            "ambulance_loading_step_hinge",
            14,
        )

    # Functional underbody additions and a restrained interior equipment set.
    rounded_box(
        ctx,
        "ambulance:fuel_tank",
        (-0.58, 0.25, 0.48),
        (0.48, 1.14, 0.35),
        M["steel"],
        0.075,
        semantic="ambulance_fuel_tank",
        segments=5,
    )
    curve_tube(
        ctx,
        "ambulance:exhaust_pipe",
        [
            (0.52, -0.45, 0.45),
            (0.60, 0.75, 0.43),
            (0.75, 2.30, 0.40),
            (1.24, 3.18, 0.44),
        ],
        0.045,
        M["steel"],
        "ambulance_exhaust_system",
    )
    box(
        ctx,
        "ambulance:patient_floor",
        (0, 1.54, 0.96),
        (1.92, 3.52, 0.08),
        M["interior"],
        0.015,
        semantic="ambulance_patient_floor",
    )
    rounded_box(
        ctx,
        "ambulance:stretcher_mattress",
        (-0.25, 1.70, 1.22),
        (0.64, 2.02, 0.17),
        M["seat"],
        0.080,
        semantic="ambulance_stretcher_mattress",
        segments=5,
    )
    for rail_side in (-1, 1):
        beam(
            ctx,
            f"ambulance:stretcher_rail_{rail_side}",
            (rail_side * 0.29 - 0.25, 0.68, 1.11),
            (rail_side * 0.29 - 0.25, 2.73, 1.11),
            0.025,
            M["aluminum"],
            "ambulance_stretcher_frame",
            12,
        )
    for cabinet_index in range(4):
        rounded_box(
            ctx,
            f"ambulance:interior_cabinet_{cabinet_index}",
            (0.70, 0.20 + cabinet_index * 0.86, 1.82),
            (0.32, 0.72, 1.26),
            M["ambulance_white"],
            0.035,
            semantic="ambulance_medical_cabinet",
            segments=4,
        )

    ctx.collection["c2w_reverse_engineering"] = json.dumps(
        calibration["derived_programmatic_parameters"], ensure_ascii=False
    )


def build_ambulance_asset(
    variant="type_i_ambulance",
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    materials=None,
):
    """Build an independently poseable ambulance from live source geometry."""
    if variant not in AMBULANCE_VARIANTS:
        raise ValueError(
            f"Unknown ambulance variant {variant!r}; expected one of {AMBULANCE_VARIANTS}"
        )
    M = materials or make_materials()
    spec = AMBULANCE_SPEC
    host = parent or bpy.context.scene.collection
    ctx = new_context(
        host,
        "AMBULANCE_" + variant.upper(),
        variant,
        spec.asset_id,
        "ambulance",
        origin,
        yaw,
    )
    build_type_i_ambulance(ctx, M)
    ctx.collection["c2w_archetype"] = spec.archetype
    ctx.collection["c2w_dimensions_m"] = json.dumps(
        [spec.length, spec.width, spec.height]
    )
    ctx.collection["c2w_front_direction"] = "local_negative_y"
    ctx.collection["c2w_reference_mesh_page"] = AMBULANCE_MESH_PAGE
    ctx.collection["c2w_reference_mesh_license"] = "CC0"
    ctx.collection["c2w_manufacturer_dimension_source"] = AMBULANCE_DIMENSION_URL
    ctx.collection[
        "c2w_modeling_quality"
    ] = "reverse_engineered_full_fabrication_photoreal_procedural_v6"
    ctx.collection["c2w_reference_mesh_inputs"] = 1
    ctx.collection["c2w_render_mesh_inputs"] = 0
    ctx.collection["c2w_external_blend_inputs"] = 0
    return ctx.collection


def build_fire_truck_asset(
    variant, parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None
):
    """Build one multi-mesh-calibrated fire engine without loading scene assets."""
    if variant not in TRUCK_SPECS:
        raise ValueError(
            f"Unknown fire-truck variant {variant!r}; expected one of {TRUCK_VARIANTS}"
        )
    M = materials or make_materials()
    spec = TRUCK_SPECS[variant]
    host = parent or bpy.context.scene.collection
    ctx = new_context(
        host,
        "TRUCK_" + variant.upper(),
        variant,
        spec.asset_id,
        "fire_truck",
        origin,
        yaw,
    )
    if variant == "modern_ladder_engine":
        build_fire7_modern_ladder_engine(ctx, M)
    elif variant == "classic_pumper":
        build_fire7_classic_pumper(ctx, M)
    else:
        build_fire7_rapid_rescue(ctx, M)
    ctx.collection["c2w_archetype"] = spec.archetype
    ctx.collection["c2w_reference_index"] = spec.reference_index
    ctx.collection["c2w_reference_url"] = FIRE7_MESH_SOURCES[variant]["page"]
    ctx.collection["c2w_dimensions_m"] = json.dumps(
        [spec.length, spec.width, spec.height]
    )
    ctx.collection["c2w_front_direction"] = "local_negative_y"
    ctx.collection["c2w_pose_yaw_radians"] = float(yaw)
    ctx.collection[
        "c2w_modeling_quality"
    ] = "multi_mesh_reverse_engineered_continuous_surface_photoreal_procedural_v7"
    ctx.collection["c2w_render_mesh_inputs"] = 0
    suite = analyze_fire_truck_reference_suite()
    source = suite["sources"][variant]
    ctx.collection["c2w_reference_mesh_page"] = source["download_page"]
    ctx.collection["c2w_reference_mesh_inputs"] = 1
    ctx.collection["c2w_reference_mesh_vertex_count"] = source["published_vertices"]
    ctx.collection["c2w_reference_mesh_face_count"] = source["published_polygons"]
    ctx.collection["c2w_reverse_engineering"] = json.dumps(
        source["derived_programmatic_parameters"],
        ensure_ascii=False,
    )
    ctx.collection["c2w_source_model_id"] = source["model_id"]
    ctx.collection["c2w_vehicle_class"] = "fire_engine"
    ctx.collection["c2w_not_ambulance"] = True
    ctx.collection["c2w_external_blend_inputs"] = 0
    return ctx.collection


# ---------------------------------------------------------------------------
# Independently placeable station architecture and operational interiors


def vertical_prism_y(
    ctx,
    name,
    points_xz,
    y,
    depth,
    material,
    semantic="architectural_profile",
    bevel=0.02,
):
    n = len(points_xz)
    verts = []
    for py in (y - depth / 2, y + depth / 2):
        verts.extend((x, py, z) for x, z in points_xz)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.anchor
    if bevel:
        mod = obj.modifiers.new("architectural_edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return tag(obj, semantic, ctx, True)


def build_front_window(
    ctx,
    name,
    x,
    y,
    z,
    width,
    height,
    M,
    columns=3,
    rows=2,
    frame_material=None,
    glass_material=None,
):
    frame = frame_material or M["aluminum"]
    glass = glass_material or M["architectural_glass"]
    box(
        ctx,
        name + ":recess",
        (x, y + 0.04, z),
        (width + 0.20, 0.20, height + 0.20),
        M["black"],
        0.025,
        semantic="window_reveal",
    )
    # A shallow interior volume prevents the facade glass from reading as a
    # featureless black decal while preserving a believable daylight tint.
    box(
        ctx,
        name + ":interior_shadowbox",
        (x, y + 0.13, z),
        (width - 0.10, 0.08, height - 0.10),
        M["interior"],
        0.012,
        semantic="window_interior_shadowbox",
    )
    for blind in range(max(2, int(height / 0.30))):
        bz = (
            z
            - height / 2
            + 0.18
            + blind * (height - 0.36) / max(1, int(height / 0.30) - 1)
        )
        box(
            ctx,
            f"{name}:interior_blind_{blind:02d}",
            (x, y + 0.045, bz),
            (width - 0.16, 0.022, 0.020),
            M["aluminum"],
            0.004,
            rotation=(0.10, 0, 0),
            semantic="window_interior_blind",
        )
    box(
        ctx,
        name + ":glazing",
        (x, y - 0.075, z),
        (width, 0.055, height),
        glass,
        0.018,
        semantic="facade_glazing",
    )
    for col in range(columns + 1):
        fx = x - width / 2 + col * width / columns
        box(
            ctx,
            f"{name}:vertical_mullion_{col:02d}",
            (fx, y - 0.115, z),
            (0.075, 0.06, height + 0.07),
            frame,
            0.012,
            semantic="facade_mullion",
        )
    for row in range(rows + 1):
        fz = z - height / 2 + row * height / rows
        box(
            ctx,
            f"{name}:horizontal_mullion_{row:02d}",
            (x, y - 0.116, fz),
            (width + 0.07, 0.06, 0.075),
            frame,
            0.012,
            semantic="facade_mullion",
        )
    box(
        ctx,
        name + ":head_flashing",
        (x, y - 0.13, z + height / 2 + 0.14),
        (width + 0.34, 0.18, 0.16),
        M["precast"],
        0.025,
        semantic="window_head_flashing",
    )
    box(
        ctx,
        name + ":sill",
        (x, y - 0.13, z - height / 2 - 0.12),
        (width + 0.28, 0.20, 0.12),
        M["precast"],
        0.02,
        semantic="window_sill",
    )


def build_glazed_entry(ctx, name, x, y, z, width, height, M, leaves=2):
    box(
        ctx,
        name + ":portal",
        (x, y + 0.02, z),
        (width + 0.42, 0.42, height + 0.38),
        M["red"],
        0.045,
        semantic="entry_portal",
    )
    box(
        ctx,
        name + ":vestibule_shadowbox",
        (x, y + 0.26, z),
        (width - 0.04, 0.18, height - 0.08),
        M["interior"],
        0.025,
        semantic="entry_vestibule_interior",
    )
    leaf_width = (width - 0.10) / leaves
    for leaf in range(leaves):
        lx = x - width / 2 + leaf_width / 2 + leaf * leaf_width
        box(
            ctx,
            f"{name}:door_glass_{leaf}",
            (lx, y - 0.225, z),
            (leaf_width - 0.08, 0.05, height - 0.13),
            M["architectural_glass"],
            0.018,
            semantic="entry_door_glazing",
        )
        for edge, ex in enumerate(
            (lx - leaf_width / 2 + 0.025, lx + leaf_width / 2 - 0.025)
        ):
            box(
                ctx,
                f"{name}:door_stile_{leaf}_{edge}",
                (ex, y - 0.25, z),
                (0.065, 0.065, height),
                M["aluminum"],
                0.012,
                semantic="entry_door_frame",
            )
        box(
            ctx,
            f"{name}:door_top_rail_{leaf}",
            (lx, y - 0.25, z + height / 2 - 0.035),
            (leaf_width, 0.065, 0.07),
            M["aluminum"],
            0.012,
            semantic="entry_door_frame",
        )
        box(
            ctx,
            f"{name}:door_bottom_rail_{leaf}",
            (lx, y - 0.25, z - height / 2 + 0.09),
            (leaf_width, 0.065, 0.18),
            M["aluminum"],
            0.012,
            semantic="entry_door_frame",
        )
        cylinder(
            ctx,
            f"{name}:pull_handle_{leaf}",
            (lx + (-0.18 if leaf % 2 == 0 else 0.18), y - 0.31, z),
            0.026,
            0.72,
            M["chrome"],
            12,
            semantic="entry_pull_handle",
            bevel=0.004,
        )
        rounded_box(
            ctx,
            f"{name}:kick_plate_{leaf}",
            (lx, y - 0.285, z - height / 2 + 0.22),
            (leaf_width - 0.12, 0.025, 0.27),
            M["aluminum"],
            0.018,
            semantic="entry_door_kick_plate",
            segments=3,
        )
        box(
            ctx,
            f"{name}:closer_{leaf}",
            (lx, y - 0.30, z + height / 2 - 0.18),
            (0.42, 0.10, 0.09),
            M["steel"],
            0.018,
            semantic="entry_door_closer",
        )


def build_bay_door(ctx, name, x, front_y, width, height, M, closed=True, glazed=False):
    """Build a serviceable double-wall coiling shutter assembly.

    ``glazed`` remains in the signature for adapter compatibility but is
    intentionally ignored.  Fire-apparatus openings use opaque interlocking
    aluminum slats, not transparent storefront/sectional glazing.  Every
    camera-visible slat has a convex double-wall section and hooked interlock;
    the jambs contain C-channel lips, brush seals, endlocks, anchors, photoeyes,
    control station, conduit and a geared barrel operator.
    """
    bottom = 0.28
    center_z = bottom + height / 2
    curtain_y = front_y - 0.310
    # Deep masonry returns, structural steel jambs and formed guide channels.
    for side in (-1, 1):
        box(
            ctx,
            f"{name}:jamb_{side}",
            (x + side * (width / 2 + 0.16), front_y - 0.20, center_z),
            (0.32, 0.54, height + 0.55),
            M["red"],
            0.035,
            semantic="apparatus_bay_frame",
        )
        rounded_box(
            ctx,
            f"{name}:guide_channel_{side}",
            (x + side * (width / 2 - 0.10), front_y - 0.24, center_z),
            (0.14, 0.20, height + 0.10),
            M["steel"],
            0.025,
            semantic="rolling_shutter_guide_channel",
            segments=4,
        )
        for lip_index, lip_x in enumerate((width / 2 - 0.205, width / 2 - 0.055)):
            box(
                ctx,
                f"{name}:guide_lip_{side}_{lip_index}",
                (x + side * lip_x, front_y - 0.355, center_z),
                (0.035, 0.075, height + 0.04),
                M["steel"],
                0.006,
                semantic="rolling_shutter_formed_guide_lip",
            )
        box(
            ctx,
            f"{name}:guide_shadow_{side}",
            (x + side * (width / 2 - 0.165), curtain_y + 0.015, center_z),
            (0.025, 0.09, height - 0.04),
            M["shutter_shadow"],
            0.004,
            semantic="rolling_shutter_guide_rebate",
        )
        box(
            ctx,
            f"{name}:brush_seal_{side}",
            (x + side * (width / 2 - 0.205), curtain_y - 0.055, center_z),
            (0.018, 0.035, height - 0.08),
            M["rubber"],
            0.003,
            semantic="rolling_shutter_brush_seal",
        )
        box(
            ctx,
            f"{name}:jamb_return_{side}",
            (x + side * (width / 2 - 0.03), front_y + 0.18, center_z),
            (0.16, 0.62, height - 0.10),
            M["precast"],
            0.018,
            semantic="apparatus_bay_jamb_return",
        )
        cylinder(
            ctx,
            f"{name}:photoeye_{side}",
            (x + side * (width / 2 - 0.25), front_y - 0.43, 0.55),
            0.055,
            0.045,
            M["red_lens"],
            20,
            (math.pi / 2, 0, 0),
            "overhead_door_photoeye",
            0.006,
        )
        rounded_box(
            ctx,
            f"{name}:guide_service_cover_{side}",
            (x + side * (width / 2 - 0.10), front_y - 0.39, bottom + height - 0.45),
            (0.24, 0.12, 0.58),
            M["shutter_aluminum"],
            0.025,
            semantic="rolling_shutter_guide_service_cover",
            segments=4,
        )
        for bolt_index, bolt_z in enumerate((0.72, 1.75, 2.78, 3.81, 4.84, 5.87)):
            if bolt_z < bottom + height - 0.18:
                cylinder(
                    ctx,
                    f"{name}:guide_anchor_{side}_{bolt_index}",
                    (x + side * (width / 2 - 0.10), front_y - 0.465, bolt_z),
                    0.025,
                    0.018,
                    M["chrome"],
                    12,
                    (math.pi / 2, 0, 0),
                    "rolling_shutter_guide_anchor",
                    0.003,
                )
        rounded_box(
            ctx,
            f"{name}:guide_base_angle_{side}",
            (x + side * (width / 2 - 0.10), front_y - 0.29, bottom + 0.03),
            (0.28, 0.28, 0.14),
            M["steel"],
            0.018,
            semantic="rolling_shutter_guide_base_angle",
            segments=3,
        )
    box(
        ctx,
        name + ":header",
        (x, front_y - 0.20, bottom + height + 0.24),
        (width + 0.65, 0.55, 0.48),
        M["red"],
        0.04,
        semantic="apparatus_bay_header",
    )
    box(
        ctx,
        name + ":header_soffit",
        (x, front_y + 0.11, bottom + height + 0.03),
        (width - 0.16, 0.46, 0.12),
        M["steel"],
        0.018,
        semantic="apparatus_bay_soffit",
    )
    rounded_box(
        ctx,
        name + ":threshold",
        (x, front_y - 0.17, bottom - 0.08),
        (width - 0.08, 0.58, 0.16),
        M["concrete_light"],
        0.035,
        semantic="apparatus_bay_threshold",
        segments=4,
    )
    # The barrel, bearing plates, hood and geared operator are present for both
    # states.  They explain where the raised curtain goes and how it moves.
    barrel_z = bottom + height + 0.31
    cylinder(
        ctx,
        name + ":barrel",
        (x, front_y + 0.03, barrel_z),
        0.105,
        width - 0.30,
        M["steel"],
        28,
        (0, math.pi / 2, 0),
        "rolling_shutter_barrel",
        0.010,
    )
    for side in (-1, 1):
        rounded_box(
            ctx,
            f"{name}:barrel_bearing_plate_{side}",
            (x + side * (width / 2 - 0.08), front_y + 0.03, barrel_z),
            (0.18, 0.42, 0.52),
            M["steel"],
            0.035,
            semantic="rolling_shutter_bearing_plate",
            segments=4,
        )
        cylinder(
            ctx,
            f"{name}:barrel_bearing_{side}",
            (x + side * (width / 2 - 0.17), front_y + 0.03, barrel_z),
            0.095,
            0.10,
            M["black"],
            24,
            (0, math.pi / 2, 0),
            "rolling_shutter_barrel_bearing",
            0.008,
        )
    rounded_box(
        ctx,
        name + ":coil_hood",
        (x, front_y - 0.08, barrel_z + 0.04),
        (width - 0.02, 0.74, 0.76),
        M["shutter_aluminum"],
        0.12,
        semantic="rolling_shutter_coil_hood",
        segments=7,
    )
    for seam_index in range(8):
        sx = x - width / 2 + 0.58 + seam_index * (width - 1.16) / 7
        box(
            ctx,
            f"{name}:hood_seam_{seam_index}",
            (sx, front_y - 0.47, barrel_z + 0.04),
            (0.025, 0.018, 0.57),
            M["shutter_shadow"],
            0.004,
            semantic="rolling_shutter_hood_seam",
        )
    motor_x = x + width / 2 - 0.46
    rounded_box(
        ctx,
        name + ":operator_motor",
        (motor_x, front_y + 0.22, barrel_z + 0.03),
        (0.54, 0.62, 0.46),
        M["steel"],
        0.075,
        semantic="overhead_door_operator_motor",
        segments=5,
    )
    cylinder(
        ctx,
        name + ":operator_reduction_gear",
        (motor_x - 0.24, front_y + 0.20, barrel_z),
        0.205,
        0.105,
        M["black"],
        36,
        (0, math.pi / 2, 0),
        "overhead_door_reduction_gear",
        0.012,
    )
    rounded_box(
        ctx,
        name + ":operator_limit_box",
        (motor_x, front_y + 0.18, barrel_z - 0.34),
        (0.34, 0.32, 0.22),
        M["black"],
        0.035,
        semantic="overhead_door_limit_switch_box",
        segments=4,
    )
    cylinder(
        ctx,
        name + ":operator_chain_wheel",
        (motor_x + 0.30, front_y + 0.22, barrel_z),
        0.16,
        0.035,
        M["black"],
        28,
        (0, math.pi / 2, 0),
        "overhead_door_chain_wheel",
        0.008,
    )
    curve_tube(
        ctx,
        name + ":manual_chain",
        [
            (motor_x + 0.32, front_y + 0.20, barrel_z + 0.12),
            (motor_x + 0.38, front_y + 0.20, barrel_z - 1.25),
            (motor_x + 0.32, front_y + 0.20, barrel_z - 2.35),
            (motor_x + 0.25, front_y + 0.20, barrel_z - 1.25),
            (motor_x + 0.32, front_y + 0.20, barrel_z + 0.12),
        ],
        0.012,
        M["steel"],
        "rolling_shutter_manual_chain",
        cyclic=True,
    )
    # A real apparatus-bay control is a compact, jamb-mounted weatherproof
    # station.  Keep it recessed behind the facade plane so it reads as door
    # hardware rather than the unexplained exterior cuboid visible in fire6.
    control_x = x + width / 2 + 0.245
    rounded_box(
        ctx,
        name + ":control_station",
        (control_x, front_y + 0.155, 1.43),
        (0.21, 0.075, 0.43),
        M["steel"],
        0.022,
        semantic="overhead_door_recessed_control_station",
        segments=5,
    )
    for button_index, (button_z, button_material) in enumerate(
        (
            (1.55, M["source_livery"]),
            (1.43, M["red_lens"]),
            (1.31, M["black"]),
        )
    ):
        cylinder(
            ctx,
            f"{name}:control_button_{button_index}",
            (control_x, front_y + 0.108, button_z),
            0.032,
            0.018,
            button_material,
            24,
            (math.pi / 2, 0, 0),
            "overhead_door_control_button",
            0.006,
        )
    cylinder(
        ctx,
        name + ":key_release",
        (control_x, front_y + 0.106, 1.20),
        0.023,
        0.014,
        M["chrome"],
        20,
        (math.pi / 2, 0, 0),
        "overhead_door_key_release",
        0.004,
    )
    curve_tube(
        ctx,
        name + ":control_conduit",
        [
            (control_x, front_y + 0.20, 1.66),
            (control_x, front_y + 0.20, barrel_z - 0.32),
            (motor_x, front_y - 0.02, barrel_z - 0.32),
        ],
        0.014,
        M["steel"],
        "overhead_door_electrical_conduit",
    )
    rounded_box(
        ctx,
        name + ":warning_beacon_housing",
        (x + width / 2 - 0.82, front_y - 0.56, barrel_z + 0.05),
        (0.28, 0.18, 0.22),
        M["black"],
        0.045,
        semantic="bay_warning_beacon_housing",
        segments=4,
    )
    cylinder(
        ctx,
        name + ":warning_beacon_lens",
        (x + width / 2 - 0.82, front_y - 0.67, barrel_z + 0.05),
        0.075,
        0.045,
        M["amber"],
        24,
        (math.pi / 2, 0, 0),
        "bay_warning_beacon",
        0.009,
    )

    if closed:
        # A dark backing behind individually formed slats prevents light leaks
        # while the narrow pitch, rolled interlocks and alternating micro-depth
        # create the expected full-scale coiling-door highlight pattern.
        curtain = box(
            ctx,
            name + ":closed_curtain_backing",
            (x, curtain_y + 0.045, center_z),
            (width - 0.38, 0.055, height - 0.04),
            M["shutter_shadow"],
            0.008,
            semantic="closed_rolling_shutter_curtain",
        )
        curtain["c2w_bay_occupancy"] = "empty"
        curtain["c2w_door_state"] = "closed"
        # 85 mm pitch is representative of a full-size insulated rolling-door
        # curtain.  The previous 165 mm cuboids were visibly over-scale.
        pitch = 0.085
        slat_count = int((height - 0.06) / pitch)
        actual_pitch = (height - 0.06) / slat_count
        for slat_index in range(slat_count):
            z = bottom + 0.03 + (slat_index + 0.5) * actual_pitch
            depth_offset = 0.0025 * math.sin(slat_index * 1.73)
            slat_material = (
                M["shutter_aluminum_alt"]
                if slat_index % 11 == 0
                else M["shutter_aluminum"]
            )
            formed_shutter_slat(
                ctx,
                f"{name}:slat_{slat_index:03d}",
                x,
                curtain_y - depth_offset,
                z,
                width - 0.40,
                actual_pitch,
                slat_material,
            )
            cylinder(
                ctx,
                f"{name}:interlock_{slat_index:02d}",
                (x, curtain_y - 0.061, z - actual_pitch * 0.49),
                0.010,
                width - 0.43,
                M["shutter_shadow"],
                12,
                (0, math.pi / 2, 0),
                "rolling_shutter_interlock",
                0.002,
            )
            if slat_index % 3 == 0:
                for side in (-1, 1):
                    rounded_box(
                        ctx,
                        f"{name}:endlock_{slat_index:02d}_{side}",
                        (x + side * (width / 2 - 0.245), curtain_y - 0.065, z),
                        (0.10, 0.035, actual_pitch * 0.70),
                        M["black"],
                        0.008,
                        semantic="rolling_shutter_endlock",
                        segments=3,
                    )
        # Surface patina comes from the aluminum material's micro-variation;
        # do not attach geometric dirt rectangles to the curtain face.
        rounded_box(
            ctx,
            name + ":bottom_bar",
            (x, curtain_y - 0.050, bottom + 0.030),
            (width - 0.34, 0.075, 0.075),
            M["steel"],
            0.014,
            semantic="rolling_shutter_bottom_bar",
            segments=4,
        )
        box(
            ctx,
            name + ":bottom_astragal",
            (x, curtain_y - 0.070, bottom - 0.014),
            (width - 0.30, 0.060, 0.032),
            M["rubber"],
            0.010,
            semantic="rolling_shutter_bottom_weather_seal",
        )
        # Flush recessed lift cups and an internal lock cylinder replace the
        # oversized black lift bar, slide-bolt blocks and lower-right data
        # plate.  Those fire6 elements were not credible at image scale.
        for cup_index, cup_x in enumerate((x - 0.31, x + 0.31)):
            rounded_box(
                ctx,
                f"{name}:recessed_lift_cup_{cup_index}",
                (cup_x, curtain_y - 0.084, bottom + 0.215),
                (0.145, 0.018, 0.052),
                M["black"],
                0.016,
                semantic="rolling_shutter_recessed_lift_cup",
                segments=5,
            )
        cylinder(
            ctx,
            name + ":flush_lock_cylinder",
            (x, curtain_y - 0.087, bottom + 0.215),
            0.027,
            0.012,
            M["chrome"],
            20,
            (math.pi / 2, 0, 0),
            "rolling_shutter_flush_lock_cylinder",
            0.004,
        )
    else:
        # The complete curtain is visibly rolled around the barrel; three
        # concentric shells and a short hanging tail expose true coiling-door
        # mechanics without ceiling-mounted glazed sections.
        for coil_index, radius in enumerate((0.19, 0.25, 0.31)):
            cylinder(
                ctx,
                f"{name}:rolled_coil_{coil_index}",
                (x, front_y - 0.02 - coil_index * 0.012, barrel_z),
                radius,
                width - 0.38 - coil_index * 0.025,
                M["shutter_aluminum"] if coil_index == 2 else M["shutter_shadow"],
                40,
                (0, math.pi / 2, 0),
                "rolling_shutter_coil",
                0.010,
            )
        tail = box(
            ctx,
            name + ":hanging_curtain_tail_backing",
            (x, curtain_y + 0.025, bottom + height - 0.18),
            (width - 0.42, 0.035, 0.34),
            M["shutter_shadow"],
            0.008,
            semantic="open_rolling_shutter_tail",
        )
        tail["c2w_bay_occupancy"] = "apparatus"
        tail["c2w_door_state"] = "open"
        for tail_slat in range(4):
            z = bottom + height - 0.31 + tail_slat * 0.085
            formed_shutter_slat(
                ctx,
                f"{name}:tail_slat_{tail_slat}",
                x,
                curtain_y,
                z,
                width - 0.44,
                0.085,
                M["shutter_aluminum"],
            )
            cylinder(
                ctx,
                f"{name}:tail_interlock_{tail_slat}",
                (x, curtain_y - 0.061, z - 0.041),
                0.010,
                width - 0.45,
                M["shutter_shadow"],
                12,
                (0, math.pi / 2, 0),
                "rolling_shutter_interlock",
                0.002,
            )


def build_turnout_locker_bank(ctx, name, x, y, count, M, facing="front"):
    for locker in range(count):
        lx = x + (locker - (count - 1) / 2) * 0.72
        box(
            ctx,
            f"{name}:carcass_{locker:02d}",
            (lx, y, 1.15),
            (0.64, 0.48, 2.18),
            M["locker"],
            0.025,
            semantic="turnout_gear_locker",
        )
        box(
            ctx,
            f"{name}:open_recess_{locker:02d}",
            (lx, y - 0.255, 1.27),
            (0.52, 0.04, 1.64),
            M["interior"],
            0.012,
            semantic="locker_opening",
        )
        cylinder(
            ctx,
            f"{name}:helmet_{locker:02d}",
            (lx, y - 0.33, 1.88),
            0.19,
            0.18,
            M["yellow_reflect"],
            24,
            semantic="fire_helmet",
            bevel=0.018,
        )
        box(
            ctx,
            f"{name}:coat_{locker:02d}",
            (lx, y - 0.32, 1.19),
            (0.40, 0.08, 0.74),
            M["black"],
            0.06,
            semantic="turnout_coat",
        )
        box(
            ctx,
            f"{name}:coat_stripe_{locker:02d}",
            (lx, y - 0.37, 1.15),
            (0.43, 0.025, 0.075),
            M["yellow_reflect"],
            0.006,
            semantic="turnout_reflective_stripe",
        )
        for boot_side in (-1, 1):
            box(
                ctx,
                f"{name}:boot_{locker:02d}_{boot_side}",
                (lx + boot_side * 0.13, y - 0.32, 0.43),
                (0.18, 0.24, 0.35),
                M["rubber"],
                0.05,
                semantic="turnout_boot",
            )


def build_bay_interior(ctx, bay_index, x, front_y, width, depth, height, M):
    center_y = front_y + depth / 2
    rear_y = front_y + depth
    box(
        ctx,
        f"bay:{bay_index}:floor",
        (x, center_y, 0.12),
        (width - 0.22, depth, 0.22),
        M["concrete_light"],
        0.025,
        semantic="apparatus_bay_floor",
    )
    # Long slot drain with individual grate bars and tire-wear marks.
    box(
        ctx,
        f"bay:{bay_index}:drain_channel",
        (x, front_y + depth * 0.45, 0.245),
        (width * 0.62, 0.42, 0.10),
        M["black"],
        0.025,
        semantic="apparatus_bay_floor_drain",
    )
    for slot in range(24):
        sx = x - width * 0.29 + (slot + 0.5) * width * 0.58 / 24
        box(
            ctx,
            f"bay:{bay_index}:drain_grate_{slot:02d}",
            (sx, front_y + depth * 0.45, 0.31),
            (0.045, 0.35, 0.025),
            M["steel"],
            0.004,
            semantic="floor_drain_grate",
        )
    for track in (-0.78, 0.78):
        box(
            ctx,
            f"bay:{bay_index}:tire_track_{track:+.2f}",
            (x + track, center_y, 0.245),
            (0.26, depth - 1.1, 0.012),
            M["asphalt"],
            0.003,
            semantic="apparatus_tire_wear",
        )
    # Open-web roof framing with actual diagonal members.
    for truss_index, ty in enumerate(
        (front_y + 2.0, front_y + 7.2, front_y + 12.4, front_y + 17.6, rear_y - 1.3)
    ):
        beam(
            ctx,
            f"bay:{bay_index}:truss_bottom_{truss_index}",
            (x - width / 2 + 0.18, ty, height - 0.72),
            (x + width / 2 - 0.18, ty, height - 0.72),
            0.075,
            M["steel"],
            "bay_roof_truss",
            14,
        )
        beam(
            ctx,
            f"bay:{bay_index}:truss_left_diag_{truss_index}",
            (x - width / 2 + 0.20, ty, height - 0.72),
            (x, ty, height - 0.15),
            0.052,
            M["steel"],
            "bay_roof_truss_brace",
            12,
        )
        beam(
            ctx,
            f"bay:{bay_index}:truss_right_diag_{truss_index}",
            (x + width / 2 - 0.20, ty, height - 0.72),
            (x, ty, height - 0.15),
            0.052,
            M["steel"],
            "bay_roof_truss_brace",
            12,
        )
    for light_index, ty in enumerate(
        (front_y + 3.5, front_y + 9.2, front_y + 14.8, rear_y - 2.1)
    ):
        box(
            ctx,
            f"bay:{bay_index}:ceiling_light_fixture_{light_index}",
            (x, ty, height - 0.82),
            (2.15, 0.30, 0.12),
            M["white"],
            0.025,
            semantic="bay_light_fixture",
        )
        box(
            ctx,
            f"bay:{bay_index}:ceiling_light_lens_{light_index}",
            (x, ty, height - 0.90),
            (1.92, 0.25, 0.035),
            M["white_emit"],
            0.012,
            semantic="bay_light_lens",
        )
        area_light(
            ctx,
            f"bay:{bay_index}:area_light_{light_index}",
            (x, ty, height - 0.96),
            165,
            (2.0, 0.40),
            semantic="bay_operational_light",
        )
    # Operational exhaust extraction line terminating above a parked apparatus.
    curve_tube(
        ctx,
        f"bay:{bay_index}:exhaust_hose",
        [
            (x + width * 0.32, rear_y - 0.4, height - 0.55),
            (x + width * 0.32, rear_y - 3.0, height - 0.75),
            (x + width * 0.32, rear_y - 4.2, 3.2),
            (x + width * 0.20, rear_y - 5.0, 1.10),
        ],
        0.085,
        M["hose_yellow"],
        "vehicle_exhaust_extraction_hose",
    )
    cylinder(
        ctx,
        f"bay:{bay_index}:exhaust_nozzle",
        (x + width * 0.20, rear_y - 5.0, 0.98),
        0.14,
        0.22,
        M["black"],
        24,
        semantic="exhaust_hose_nozzle",
        bevel=0.012,
    )
    # Gear, hose and service equipment at the back wall.
    build_turnout_locker_bank(
        ctx, f"bay:{bay_index}:turnout_bank", x - 0.55, rear_y - 0.38, 5, M
    )
    for shelf in range(4):
        box(
            ctx,
            f"bay:{bay_index}:hose_rack_shelf_{shelf}",
            (x + width * 0.34, rear_y - 0.42, 0.70 + shelf * 0.50),
            (width * 0.22, 0.46, 0.075),
            M["steel"],
            0.012,
            semantic="hose_storage_shelf",
        )
        for hose in range(3):
            torus(
                ctx,
                f"bay:{bay_index}:stored_hose_{shelf}_{hose}",
                (x + width * 0.25 + hose * 0.32, rear_y - 0.70, 0.75 + shelf * 0.50),
                0.13,
                0.035,
                M["hose_canvas" if shelf % 2 else "hose_yellow"],
                (math.pi / 2, 0, 0),
                "stored_hose_roll",
                24,
                8,
            )
    for side in (-1, 1):
        cylinder(
            ctx,
            f"bay:{bay_index}:protective_bollard_{side}",
            (x + side * (width / 2 - 0.34), front_y + 0.65, 0.75),
            0.115,
            1.46,
            M["yellow_reflect"],
            24,
            semantic="bay_protective_bollard",
            bevel=0.018,
        )


def build_rooftop_plant(ctx, name, center, M, scale=1.0):
    x, y, z = center
    box(
        ctx,
        name + ":curb",
        (x, y, z),
        (2.65 * scale, 1.75 * scale, 0.28),
        M["roof"],
        0.035,
        semantic="roof_equipment_curb",
    )
    box(
        ctx,
        name + ":housing",
        (x, y, z + 0.68 * scale),
        (2.35 * scale, 1.45 * scale, 1.18 * scale),
        M["steel"],
        0.055,
        semantic="roof_hvac_unit",
    )
    for side in (-1, 1):
        for slat in range(9):
            sy = y - 0.52 * scale + slat * 0.13 * scale
            box(
                ctx,
                f"{name}:louver_{side}_{slat:02d}",
                (x + side * 1.205 * scale, sy, z + 0.72 * scale),
                (0.035, 0.085 * scale, 0.68 * scale),
                M["black"],
                0.005,
                rotation=(0, 0, 0.13 * side),
                semantic="hvac_louver",
            )
    cylinder(
        ctx,
        name + ":fan_ring",
        (x, y, z + 1.31 * scale),
        0.48 * scale,
        0.08 * scale,
        M["black"],
        32,
        semantic="hvac_condenser_fan",
        bevel=0.01,
    )
    for blade in range(6):
        angle = 2 * math.pi * blade / 6
        box(
            ctx,
            f"{name}:fan_blade_{blade}",
            (
                x + math.cos(angle) * 0.22 * scale,
                y + math.sin(angle) * 0.22 * scale,
                z + 1.36 * scale,
            ),
            (0.34 * scale, 0.09 * scale, 0.025 * scale),
            M["steel"],
            0.012,
            rotation=(0, 0, angle + 0.28),
            semantic="hvac_fan_blade",
        )


def build_identity_sign(ctx, name, body, center, width, height, text_size, M):
    """Construct a legible bounded sign cabinet with mounting hardware."""
    x, y, z = center
    rounded_box(
        ctx,
        name + ":cabinet",
        (x, y, z),
        (width, 0.38, height),
        M["red"],
        0.060,
        semantic="station_identity_backer",
        segments=5,
    )
    # Recessed black reveal and an aluminum perimeter make the red panel read as
    # a fabricated cabinet rather than another painted wall rectangle.
    rounded_box(
        ctx,
        name + ":recess",
        (x, y - 0.205, z),
        (width - 0.28, 0.035, height - 0.26),
        M["red_dark"],
        0.045,
        semantic="station_sign_recess",
        segments=5,
    )
    for edge, (loc, dims) in enumerate(
        (
            ((x, y - 0.235, z + height / 2 - 0.055), (width - 0.12, 0.035, 0.055)),
            ((x, y - 0.235, z - height / 2 + 0.055), (width - 0.12, 0.035, 0.055)),
            ((x - width / 2 + 0.055, y - 0.235, z), (0.055, 0.035, height - 0.12)),
            ((x + width / 2 - 0.055, y - 0.235, z), (0.055, 0.035, height - 0.12)),
        )
    ):
        box(
            ctx,
            f"{name}:perimeter_{edge}",
            loc,
            dims,
            M["aluminum"],
            0.008,
            semantic="station_sign_perimeter",
        )
    # Slightly larger rear text produces a crisp dark keyline, preserving
    # letter separation at long range without allowing text outside the panel.
    text_front(
        ctx,
        name + ":text_keyline",
        body,
        (x, y - 0.245, z),
        text_size * 1.045,
        M["black"],
        0.026,
        semantic="station_identity_sign_keyline",
    )
    text_front(
        ctx,
        name + ":text",
        body,
        (x, y - 0.285, z),
        text_size,
        M["white_emit"],
        0.045,
        semantic="station_identity_sign",
    )
    for bolt_index in range(12):
        bx = x - width * 0.45 + bolt_index * width * 0.90 / 11
        for bz in (z - height * 0.40, z + height * 0.40):
            cylinder(
                ctx,
                f"{name}:mounting_bolt_{bolt_index}_{bz:+.2f}",
                (bx, y - 0.275, bz),
                0.022,
                0.025,
                M["chrome"],
                12,
                (math.pi / 2, 0, 0),
                "station_sign_mounting_bolt",
                0.003,
            )
    for lamp_index, lx in enumerate((x - width * 0.32, x + width * 0.32)):
        beam(
            ctx,
            f"{name}:sign_light_arm_{lamp_index}",
            (lx, y + 0.02, z + height / 2 + 0.18),
            (lx, y - 0.42, z + height / 2 + 0.42),
            0.035,
            M["steel"],
            "station_sign_light_arm",
            14,
        )
        rounded_box(
            ctx,
            f"{name}:sign_light_{lamp_index}",
            (lx, y - 0.46, z + height / 2 + 0.38),
            (0.46, 0.30, 0.18),
            M["black"],
            0.055,
            rotation=(-0.42, 0, 0),
            semantic="station_sign_light",
            segments=4,
        )
        box(
            ctx,
            f"{name}:sign_light_lens_{lamp_index}",
            (lx, y - 0.63, z + height / 2 + 0.30),
            (0.34, 0.035, 0.10),
            M["headlamp"],
            0.020,
            rotation=(-0.42, 0, 0),
            semantic="station_sign_light_lens",
        )


def build_facade_fire_connection(ctx, name, loc, M):
    """Model a code-required Siamese inlet, caps, valve labels and pipework."""
    x, y, z = loc
    rounded_box(
        ctx,
        name + ":backplate",
        (x, y, z),
        (1.42, 0.16, 0.92),
        M["precast"],
        0.055,
        semantic="fire_department_connection_backplate",
        segments=5,
    )
    rounded_box(
        ctx,
        name + ":label",
        (x, y - 0.105, z + 0.31),
        (1.05, 0.035, 0.17),
        M["red"],
        0.028,
        semantic="fire_department_connection_label",
        segments=4,
    )
    text_front(
        ctx,
        name + ":label_text",
        "FDC",
        (x, y - 0.138, z + 0.31),
        0.105,
        M["white"],
        0.008,
        semantic="fire_department_connection_label_text",
    )
    for side in (-1, 1):
        sx = x + side * 0.33
        cylinder(
            ctx,
            f"{name}:inlet_body_{side}",
            (sx, y - 0.16, z - 0.05),
            0.19,
            0.25,
            M["brass"],
            36,
            (math.pi / 2, 0, 0),
            "fire_department_connection_inlet",
            0.014,
        )
        cylinder(
            ctx,
            f"{name}:threaded_cap_{side}",
            (sx, y - 0.32, z - 0.05),
            0.22,
            0.075,
            M["chrome"],
            36,
            (math.pi / 2, 0, 0),
            "fire_department_connection_cap",
            0.012,
        )
        for lug in range(6):
            angle = 2 * math.pi * lug / 6
            sphere(
                ctx,
                f"{name}:cap_lug_{side}_{lug}",
                (
                    sx + math.cos(angle) * 0.22,
                    y - 0.375,
                    z - 0.05 + math.sin(angle) * 0.22,
                ),
                (0.035, 0.025, 0.035),
                M["chrome"],
                "fire_department_connection_cap_lug",
                12,
                8,
            )
        curve_tube(
            ctx,
            f"{name}:cap_chain_{side}",
            [
                (sx, y - 0.38, z - 0.26),
                (sx + side * 0.10, y - 0.40, z - 0.48),
                (x, y - 0.29, z - 0.44),
            ],
            0.011,
            M["steel"],
            "fire_department_connection_cap_chain",
        )
    cylinder(
        ctx,
        name + ":supply_riser",
        (x, y + 0.02, z - 0.62),
        0.070,
        0.72,
        M["red"],
        20,
        semantic="fire_department_connection_riser",
        bevel=0.008,
    )


def build_roof_detail_cluster(ctx, name, origin, M, span=1.0):
    """Add vents, roof hatch, conduit and screened ductwork for aerial realism."""
    x, y, z = origin
    rounded_box(
        ctx,
        name + ":roof_hatch",
        (x, y, z + 0.16),
        (1.35 * span, 1.10 * span, 0.24),
        M["steel"],
        0.045,
        semantic="roof_access_hatch",
        segments=4,
    )
    box(
        ctx,
        name + ":hatch_hinge",
        (x, y + 0.53 * span, z + 0.31),
        (0.58 * span, 0.08, 0.10),
        M["black"],
        0.014,
        semantic="roof_access_hatch_hinge",
    )
    for vent_index, (vx, vy, height) in enumerate(
        (
            (x - 1.35 * span, y - 0.40 * span, 0.82),
            (x + 1.28 * span, y + 0.52 * span, 1.02),
            (x + 0.30 * span, y - 1.25 * span, 0.68),
        )
    ):
        cylinder(
            ctx,
            f"{name}:vent_stack_{vent_index}",
            (vx, vy, z + height / 2),
            0.095,
            height,
            M["steel"],
            24,
            semantic="roof_vent_stack",
            bevel=0.008,
        )
        cylinder(
            ctx,
            f"{name}:vent_cap_{vent_index}",
            (vx, vy, z + height + 0.055),
            0.17,
            0.095,
            M["steel"],
            24,
            semantic="roof_vent_rain_cap",
            bevel=0.012,
        )
        torus(
            ctx,
            f"{name}:vent_flashing_{vent_index}",
            (vx, vy, z + 0.045),
            0.20,
            0.030,
            M["roof"],
            semantic="roof_vent_flashing",
            major_segments=28,
            minor_segments=8,
        )
    curve_tube(
        ctx,
        name + ":electrical_conduit",
        [
            (x - 1.6 * span, y + 1.1 * span, z + 0.08),
            (x, y + 1.0 * span, z + 0.10),
            (x + 1.55 * span, y + 0.35 * span, z + 0.10),
        ],
        0.028,
        M["steel"],
        "roof_electrical_conduit",
    )


def add_front_cladding_seams(
    ctx, name, x, y, width, z0, z1, M, horizontal=True, spacing=0.62
):
    count = int((z1 - z0) / spacing) if horizontal else int(width / spacing)
    if horizontal:
        for i in range(count + 1):
            z = z0 + i * (z1 - z0) / max(1, count)
            box(
                ctx,
                f"{name}:horizontal_seam_{i:02d}",
                (x, y, z),
                (width, 0.035, 0.025),
                M["red_dark"],
                0.003,
                semantic="cladding_shadow_joint",
            )
    else:
        for i in range(count + 1):
            px = x - width / 2 + i * width / max(1, count)
            box(
                ctx,
                f"{name}:vertical_rib_{i:03d}",
                (px, y, (z0 + z1) / 2),
                (0.035, 0.055, z1 - z0),
                M["steel"],
                0.005,
                semantic="metal_cladding_rib",
            )


def build_civic_headquarters(ctx, M, include_site=True):
    front_y, rear_y, depth = -13.0, 13.0, 26.0
    hall_height = 10.45
    # Apparatus hall envelope is assembled around true openings, never a facade decal.
    box(
        ctx,
        "hq:rear_wall",
        (0, rear_y, 5.2),
        (44.0, 0.62, 10.4),
        M["brick"],
        0.025,
        semantic="station_building_shell",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"hq:hall_side_wall_{side}",
            (side * 21.75, 0, 5.2),
            (0.62, depth, 10.4),
            M["brick"],
            0.025,
            semantic="station_building_shell",
        )
    box(
        ctx,
        "hq:hall_roof",
        (0, 0, hall_height),
        (44.0, depth, 0.36),
        M["roof"],
        0.055,
        semantic="station_roof",
    )
    box(
        ctx,
        "hq:upper_front_brick",
        (0, front_y, 8.65),
        (44.0, 0.60, 3.10),
        M["brick"],
        0.025,
        semantic="brick_facade_spandrel",
    )
    # Combined real brick slips provide course shadows and edge parallax in the
    # southwest aerial.  Panels are split around the upper glazing rather than
    # laid over it as a facade decal.
    masonry_relief_panel(
        ctx,
        "hq:brick_relief_top",
        (0, front_y - 0.315, 9.82),
        43.80,
        0.70,
        0.040,
        M["brick"],
        0.39,
        0.145,
        "brick_relief_masonry",
    )
    masonry_relief_panel(
        ctx,
        "hq:brick_relief_lower",
        (0, front_y - 0.315, 7.27),
        43.80,
        0.46,
        0.038,
        M["brick"],
        0.39,
        0.145,
        "brick_relief_masonry",
    )
    # Full parapet, coping, base flashing and masonry movement joints make the
    # envelope read as constructed architecture rather than stacked masses.
    box(
        ctx,
        "hq:front_parapet",
        (0, front_y + 0.06, 10.57),
        (44.0, 0.72, 0.52),
        M["brick"],
        0.025,
        semantic="roof_parapet",
    )
    rounded_box(
        ctx,
        "hq:front_parapet_coping",
        (0, front_y - 0.02, 10.87),
        (44.55, 0.94, 0.16),
        M["aluminum"],
        0.035,
        semantic="roof_metal_coping",
        segments=4,
    )
    box(
        ctx,
        "hq:facade_base_flashing",
        (0, front_y - 0.39, 0.28),
        (44.0, 0.06, 0.23),
        M["steel"],
        0.012,
        semantic="masonry_base_flashing",
    )
    for joint_index, jx in enumerate((-15.55, -5.05, 5.05, 15.55)):
        box(
            ctx,
            f"hq:masonry_control_joint_{joint_index}",
            (jx, front_y - 0.335, 8.75),
            (0.035, 0.025, 2.55),
            M["sealant"],
            0.004,
            semantic="masonry_control_joint",
        )
    bay_centers = (-16.05, -5.35, 5.35, 16.05)
    pier_centers = (-21.6, -10.70, 0.0, 10.70, 21.6)
    for pier_index, px in enumerate(pier_centers):
        box(
            ctx,
            f"hq:brick_pier_{pier_index}",
            (px, front_y - 0.02, 3.45),
            (1.08, 0.76, 6.85),
            M["brick"],
            0.018,
            semantic="brick_bay_pier",
        )
        masonry_relief_panel(
            ctx,
            f"hq:brick_pier_relief_{pier_index}",
            (px, front_y - 0.405, 3.92),
            1.02,
            5.72,
            0.042,
            M["brick"],
            0.34,
            0.145,
            "brick_pier_relief_masonry",
        )
        box(
            ctx,
            f"hq:pier_precast_base_{pier_index}",
            (px, front_y - 0.25, 0.72),
            (1.22, 0.42, 1.35),
            M["precast"],
            0.025,
            semantic="precast_pier_base",
        )
        rounded_box(
            ctx,
            f"hq:upper_accent_fin_{pier_index}",
            (px, front_y - 0.53, 8.62),
            (0.18, 0.34, 2.72),
            M["red"],
            0.025,
            semantic="facade_vertical_accent_fin",
            segments=4,
        )
    for bay_index, bx in enumerate(bay_centers):
        build_bay_interior(ctx, bay_index, bx, front_y, 9.55, depth - 1.4, 7.45, M)
        build_bay_door(
            ctx,
            f"hq:bay_door_{bay_index}",
            bx,
            front_y,
            8.60,
            6.55,
            M,
            closed=bay_index >= 2,
            glazed=False,
        )
        build_front_window(
            ctx,
            f"hq:upper_window_{bay_index}",
            bx,
            front_y - 0.34,
            8.42,
            7.70,
            1.36,
            M,
            4,
            1,
            M["red"],
            M["architectural_glass"],
        )
        text_front(
            ctx,
            f"hq:bay_number_{bay_index}",
            str(bay_index + 1),
            (bx, front_y - 0.57, 7.40),
            0.48,
            M["white_emit"],
            0.030,
            semantic="bay_number",
        )
        box(
            ctx,
            f"hq:bay_soldier_course_{bay_index}",
            (bx, front_y - 0.35, 7.08),
            (9.45, 0.08, 0.16),
            M["brick_red"],
            0.012,
            semantic="masonry_soldier_course",
        )
        rounded_box(
            ctx,
            f"hq:bay_head_flashing_{bay_index}",
            (bx, front_y - 0.58, 7.01),
            (9.10, 0.24, 0.18),
            M["aluminum"],
            0.028,
            semantic="bay_head_metal_flashing",
            segments=4,
        )
        for end in (-1, 1):
            cylinder(
                ctx,
                f"hq:bay_frame_anchor_{bay_index}_{end}",
                (bx + end * 4.60, front_y - 0.435, 6.85),
                0.045,
                0.025,
                M["chrome"],
                14,
                (math.pi / 2, 0, 0),
                "bay_frame_anchor_plate",
                0.004,
            )
    # Red two-storey operations wing from the second station reference.
    box(
        ctx,
        "hq:red_wing_shell",
        (-31.50, 0.20, 5.10),
        (19.0, 25.6, 10.2),
        M["red_clad"],
        0.055,
        semantic="station_operations_wing",
    )
    box(
        ctx,
        "hq:red_wing_brick_plinth",
        (-31.50, front_y - 0.02, 1.02),
        (19.0, 0.60, 1.95),
        M["brick"],
        0.02,
        semantic="brick_facade_plinth",
    )
    masonry_relief_panel(
        ctx,
        "hq:red_wing_plinth_relief",
        (-31.50, front_y - 0.325, 1.06),
        18.78,
        1.72,
        0.042,
        M["brick"],
        0.39,
        0.145,
        "brick_relief_masonry",
    )
    add_front_cladding_seams(
        ctx, "hq:red_wing", -31.50, front_y - 0.35, 19.0, 2.05, 10.15, M, True, 0.58
    )
    build_front_window(
        ctx,
        "hq:red_wing_large_window",
        -36.0,
        front_y - 0.40,
        6.25,
        5.30,
        3.60,
        M,
        3,
        3,
    )
    for window_index, wx in enumerate((-29.5, -26.8, -24.1)):
        build_front_window(
            ctx,
            f"hq:red_wing_slot_{window_index}",
            wx,
            front_y - 0.40,
            5.45,
            1.20,
            3.25,
            M,
            1,
            2,
        )
    box(
        ctx,
        "hq:red_wing_roof_coping",
        (-31.50, front_y - 0.17, 10.30),
        (19.25, 0.72, 0.28),
        M["roof"],
        0.035,
        semantic="roof_coping",
    )
    for rib_index in range(25):
        rx = -40.55 + rib_index * 18.10 / 24
        box(
            ctx,
            f"hq:red_wing_panel_rib_{rib_index:02d}",
            (rx, front_y - 0.39, 6.10),
            (0.032, 0.045, 8.00),
            M["red_dark"],
            0.004,
            semantic="rainscreen_panel_rib",
        )
    # Precast/glass administration wing and landmark station-number tower.
    box(
        ctx,
        "hq:admin_shell",
        (31.60, 0.15, 5.55),
        (19.2, 25.7, 11.1),
        M["precast"],
        0.045,
        semantic="station_administration_wing",
    )
    masonry_relief_panel(
        ctx,
        "hq:admin_top_block_relief",
        (31.6, front_y - 0.325, 10.28),
        18.82,
        0.92,
        0.032,
        M["precast"],
        0.92,
        0.32,
        "precast_block_relief",
    )
    masonry_relief_panel(
        ctx,
        "hq:admin_lower_left_block_relief",
        (25.2, front_y - 0.325, 2.58),
        5.55,
        3.58,
        0.032,
        M["precast"],
        0.92,
        0.32,
        "precast_block_relief",
    )
    masonry_relief_panel(
        ctx,
        "hq:admin_lower_right_block_relief",
        (38.4, front_y - 0.325, 2.58),
        4.10,
        3.58,
        0.032,
        M["precast"],
        0.92,
        0.32,
        "precast_block_relief",
    )
    box(
        ctx,
        "hq:admin_dark_band",
        (31.60, front_y - 0.35, 5.05),
        (19.2, 0.22, 0.72),
        M["brick"],
        0.015,
        semantic="facade_shadow_band",
    )
    for joint_index, jx in enumerate((23.6, 27.6, 31.6, 35.6, 39.6)):
        box(
            ctx,
            f"hq:admin_vertical_reveal_{joint_index}",
            (jx, front_y - 0.365, 5.85),
            (0.045, 0.028, 10.0),
            M["sealant"],
            0.004,
            semantic="precast_panel_reveal",
        )
    for joint_index, jz in enumerate((1.75, 4.62, 8.92)):
        box(
            ctx,
            f"hq:admin_horizontal_reveal_{joint_index}",
            (31.6, front_y - 0.367, jz),
            (18.7, 0.028, 0.045),
            M["sealant"],
            0.004,
            semantic="precast_panel_reveal",
        )
    build_front_window(
        ctx, "hq:admin_upper_window", 27.8, front_y - 0.41, 7.65, 9.50, 3.10, M, 4, 2
    )
    build_glazed_entry(
        ctx, "hq:public_entry", 33.4, front_y - 0.33, 2.18, 4.65, 4.15, M, 2
    )
    box(
        ctx,
        "hq:entry_canopy",
        (33.4, front_y - 1.32, 4.48),
        (6.25, 2.45, 0.30),
        M["roof"],
        0.055,
        rotation=(-0.055, 0, 0),
        semantic="public_entry_canopy",
    )
    for tie_index, tx in enumerate((31.55, 35.25)):
        beam(
            ctx,
            f"hq:entry_canopy_tie_{tie_index}",
            (tx, front_y - 0.38, 6.02),
            (tx, front_y - 2.08, 4.56),
            0.040,
            M["steel"],
            "canopy_tension_rod",
            14,
        )
    for column_x in (31.1, 35.7):
        cylinder(
            ctx,
            f"hq:entry_column_{column_x:+.1f}",
            (column_x, front_y - 2.15, 2.20),
            0.13,
            4.35,
            M["steel"],
            24,
            semantic="canopy_column",
            bevel=0.012,
        )
    box(
        ctx,
        "hq:number_tower",
        (40.15, -0.30, 6.90),
        (4.25, 26.4, 13.8),
        M["red_clad"],
        0.08,
        semantic="station_landmark_tower",
    )
    add_front_cladding_seams(
        ctx, "hq:number_tower", 40.15, front_y - 0.58, 4.25, 0.4, 13.65, M, True, 0.67
    )
    text_front(
        ctx,
        "hq:tower_number",
        "1",
        (40.15, front_y - 0.72, 7.70),
        3.80,
        M["white_emit"],
        0.08,
        semantic="station_number_sign",
    )
    rounded_box(
        ctx,
        "hq:tower_cap",
        (40.15, -0.30, 13.91),
        (4.58, 26.75, 0.24),
        M["aluminum"],
        0.055,
        semantic="tower_metal_coping",
        segments=4,
    )
    for side in (-1, 1):
        box(
            ctx,
            f"hq:tower_edge_trim_{side}",
            (40.15 + side * 2.13, front_y - 0.62, 7.0),
            (0.075, 0.10, 13.45),
            M["red_dark"],
            0.012,
            semantic="tower_corner_trim",
        )
    # Main civic identity sign is intentionally large and bounded by the hall
    # facade.  At 21.6 m it remains well inside the 44 m apparatus wing.
    build_identity_sign(
        ctx,
        "hq:identity",
        "CITY FIRE & RESCUE",
        (0, front_y - 0.54, 10.00),
        21.60,
        1.52,
        1.06,
        M,
    )
    # Keep the required Siamese inlet on the administration wall, clear of the
    # shutter leaf.  In fire6 it occupied the lower-right corner of bay 3 and
    # read as an unexplained block attached to the door.
    build_facade_fire_connection(ctx, "hq:front_fdc", (36.75, front_y - 0.49, 1.48), M)
    # Full roof edge construction and front scuppers are visible from aerial
    # cameras instead of exposing one large unbounded slab.
    box(
        ctx,
        "hq:rear_parapet",
        (0, rear_y - 0.06, 10.62),
        (44.0, 0.62, 0.62),
        M["brick"],
        0.025,
        semantic="roof_parapet",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"hq:side_parapet_{side}",
            (side * 21.70, 0, 10.62),
            (0.62, depth, 0.62),
            M["brick"],
            0.025,
            semantic="roof_parapet",
        )
        rounded_box(
            ctx,
            f"hq:side_parapet_coping_{side}",
            (side * 21.70, 0, 10.96),
            (0.82, depth + 0.35, 0.14),
            M["aluminum"],
            0.030,
            semantic="roof_metal_coping",
            segments=4,
        )
    for scupper_index, sx in enumerate((-17.8, -9.0, 9.0, 17.8)):
        rounded_box(
            ctx,
            f"hq:front_scupper_{scupper_index}",
            (sx, front_y - 0.48, 10.24),
            (0.72, 0.26, 0.34),
            M["steel"],
            0.045,
            semantic="roof_scupper",
            segments=4,
        )
        cylinder(
            ctx,
            f"hq:front_downpipe_{scupper_index}",
            (sx, front_y - 0.45, 5.16),
            0.055,
            9.82,
            M["steel"],
            18,
            semantic="rainwater_downpipe",
            bevel=0.006,
        )
    # Roof service details, gutters, downpipes and building lighting.
    for plant_index, center in enumerate(
        ((-12, 3.2, 10.68), (8.5, 3.8, 10.68), (30.2, 3.4, 11.35))
    ):
        build_rooftop_plant(
            ctx,
            f"hq:roof_plant_{plant_index}",
            center,
            M,
            0.82 if plant_index == 2 else 1.0,
        )
    build_roof_detail_cluster(ctx, "hq:roof_detail_west", (-18.0, -1.5, 10.72), M, 1.0)
    build_roof_detail_cluster(ctx, "hq:roof_detail_east", (15.6, 5.6, 10.72), M, 0.88)
    for side, x in enumerate((-20.8, 20.8, 23.2, 38.5)):
        cylinder(
            ctx,
            f"hq:downpipe_{side}",
            (x, rear_y + 0.36, 4.75),
            0.055,
            9.30,
            M["steel"],
            16,
            semantic="rainwater_downpipe",
            bevel=0.005,
        )
        for clip_index, z in enumerate((1.2, 3.4, 5.6, 7.8)):
            box(
                ctx,
                f"hq:downpipe_clip_{side}_{clip_index}",
                (x, rear_y + 0.52, z),
                (0.20, 0.12, 0.045),
                M["steel"],
                0.008,
                semantic="pipe_bracket",
            )
    for lamp_index, lx in enumerate((-18.5, -8.0, 2.6, 13.4, 25.3, 37.2)):
        box(
            ctx,
            f"hq:wall_light_housing_{lamp_index}",
            (lx, front_y - 0.47, 9.15),
            (0.55, 0.38, 0.22),
            M["black"],
            0.055,
            rotation=(-0.18, 0, 0),
            semantic="wall_pack_light",
        )
        box(
            ctx,
            f"hq:wall_light_lens_{lamp_index}",
            (lx, front_y - 0.61, 9.07),
            (0.40, 0.06, 0.12),
            M["headlamp"],
            0.025,
            semantic="wall_pack_lens",
        )
    if include_site:
        box(
            ctx,
            "hq:foundation",
            (0, 0.1, -0.04),
            (84.4, 27.4, 0.45),
            M["concrete"],
            0.04,
            semantic="station_foundation",
        )
    ctx.collection["c2w_bay_count"] = 4
    ctx.collection[
        "c2w_architecture"
    ] = "black_brick_red_cladding_precast_civic_station"


def build_industrial_annex(ctx, M, include_site=True):
    front_y, rear_y, depth = -12.0, 12.5, 24.5
    hall_width, hall_center = 42.0, -4.75
    # Reference_03 carries a tall pre-engineered metal wall above the apparatus
    # headers; preserving that 3+ metre spandrel avoids the flattened warehouse
    # proportion of the earlier pass.
    eave, ridge = 9.75, 12.00
    hall_left = hall_center - hall_width / 2
    hall_right = hall_center + hall_width / 2

    # Reference_03 is a four-opening, clear-span pre-engineered hall.  The
    # envelope is built around actual voids and a full-depth interior rather
    # than a flat wall with door graphics.
    box(
        ctx,
        "annex:rear_wall",
        (hall_center, rear_y, eave / 2),
        (hall_width, 0.58, eave),
        M["gray_clad"],
        0.025,
        semantic="station_building_shell",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"annex:hall_side_{side}",
            (hall_center + side * hall_width / 2, 0.25, eave / 2),
            (0.58, depth, eave),
            M["gray_clad"],
            0.025,
            semantic="station_building_shell",
        )
    upper_bottom = 6.55
    box(
        ctx,
        "annex:front_upper_band",
        (hall_center, front_y, (upper_bottom + eave) / 2),
        (hall_width, 0.58, eave - upper_bottom),
        M["gray_clad"],
        0.025,
        semantic="metal_facade_spandrel",
    )
    vertical_prism_y(
        ctx,
        "annex:front_gable",
        [(hall_left, eave), (hall_center, ridge), (hall_right, eave)],
        front_y,
        0.58,
        M["gray_clad"],
        "metal_gable_end",
        0.025,
    )
    # Dark insulated liner and galvanized girts supply the depth/contrast seen
    # inside the photographed open bays, while the outer wall remains a full
    # weather envelope behind it.
    box(
        ctx,
        "annex:rear_interior_liner",
        (hall_center, rear_y - 0.33, (eave - 0.30) / 2),
        (hall_width - 0.70, 0.09, eave - 0.30),
        M["interior"],
        0.012,
        semantic="bay_interior_wall_liner",
    )
    for liner_rib in range(35):
        rx = hall_left + 0.65 + liner_rib * (hall_width - 1.30) / 34
        box(
            ctx,
            f"annex:rear_liner_rib_{liner_rib:02d}",
            (rx, rear_y - 0.39, (eave - 0.55) / 2),
            (0.036, 0.075, eave - 0.55),
            M["steel"],
            0.006,
            semantic="bay_interior_wall_rib",
        )

    # The ridge runs through the depth of the building, so the two roof planes
    # fall toward local +/-X.  The previous front/rear fall contradicted the
    # triangular gable and exposed a large unsupported black soffit in the
    # reference-facing camera.
    slope = math.atan2(ridge - eave, hall_width / 2)
    roof_len = math.sqrt((hall_width / 2) ** 2 + (ridge - eave) ** 2)
    for roof_side in (-1, 1):
        sx = hall_center + roof_side * hall_width / 4
        box(
            ctx,
            f"annex:roof_slope_{roof_side}",
            (sx, 0.25, (ridge + eave) / 2 + 0.12),
            (roof_len + 0.48, depth + 0.72, 0.27),
            M["roof"],
            0.035,
            rotation=(0, roof_side * slope, 0),
            semantic="standing_seam_gable_roof",
        )
        box(
            ctx,
            f"annex:insulated_roof_liner_{roof_side}",
            (sx, 0.28, (ridge + eave) / 2 - 0.055),
            (roof_len - 0.06, depth - 0.18, 0.085),
            M["interior"],
            0.012,
            rotation=(0, roof_side * slope, 0),
            semantic="insulated_metal_roof_liner",
        )
        eave_x = hall_center + roof_side * (hall_width / 2 + 0.04)
        rounded_box(
            ctx,
            f"annex:eave_fascia_{roof_side}",
            (eave_x, 0.25, eave + 0.06),
            (0.27, depth + 0.90, 0.43),
            M["roof"],
            0.055,
            semantic="metal_eave_fascia",
            segments=4,
        )
        cylinder(
            ctx,
            f"annex:eave_gutter_{roof_side}",
            (eave_x + roof_side * 0.18, 0.25, eave - 0.10),
            0.11,
            depth + 0.34,
            M["steel"],
            24,
            (math.pi / 2, 0, 0),
            "box_gutter",
            0.012,
        )
    rounded_box(
        ctx,
        "annex:ridge_cap",
        (hall_center, 0.25, ridge + 0.20),
        (0.47, depth + 0.80, 0.21),
        M["aluminum"],
        0.075,
        semantic="standing_seam_ridge_cap",
        segments=5,
    )

    # Water-flow seams run from ridge to eave and repeat along the building
    # depth; their rotations exactly match the parent roof planes.
    for seam in range(37):
        sy = front_y + 0.55 + seam * (depth - 1.10) / 36
        for roof_side in (-1, 1):
            sx = hall_center + roof_side * hall_width / 4
            box(
                ctx,
                f"annex:roof_seam_{roof_side}_{seam:02d}",
                (sx, sy, (ridge + eave) / 2 + 0.28),
                (roof_len + 0.20, 0.035, 0.055),
                M["steel"],
                0.006,
                rotation=(0, roof_side * slope, 0),
                semantic="standing_seam_rib",
            )

    bay_centers = (-20.50, -10.00, 0.50, 11.00)
    pier_centers = (-25.55, -15.25, -4.75, 5.75, 16.05)
    for pier_index, px in enumerate(pier_centers):
        box(
            ctx,
            f"annex:front_pier_{pier_index}",
            (px, front_y, 3.48),
            (1.00, 0.70, 6.90),
            M["gray_clad"],
            0.025,
            semantic="metal_bay_pier",
        )
        box(
            ctx,
            f"annex:stone_base_{pier_index}",
            (px, front_y - 0.28, 0.80),
            (1.13, 0.26, 1.54),
            M["stone"],
            0.025,
            semantic="stone_veneer_base",
        )
        masonry_relief_panel(
            ctx,
            f"annex:stone_relief_{pier_index}",
            (px, front_y - 0.425, 0.80),
            1.07,
            1.46,
            0.070,
            M["stone"],
            0.53,
            0.25,
            "split_face_stone_relief",
        )
        rounded_box(
            ctx,
            f"annex:red_vertical_trim_{pier_index}",
            (px, front_y - 0.48, 4.21),
            (0.20, 0.29, 5.14),
            M["red"],
            0.025,
            semantic="facade_vertical_accent_fin",
            segments=4,
        )
        for course in range(6):
            box(
                ctx,
                f"annex:stone_course_{pier_index}_{course}",
                (px, front_y - 0.428, 0.22 + course * 0.24),
                (1.06, 0.036, 0.024),
                M["black"],
                0.004,
                semantic="stone_veneer_joint",
            )

    for bay_index, bx in enumerate(bay_centers):
        build_bay_interior(
            ctx, 10 + bay_index, bx, front_y, 9.62, depth - 1.35, 7.42, M
        )
        # Bays 1-2 are unoccupied and therefore secured with opaque coiling
        # shutters.  Bays 3-4 contain response vehicles and remain raised.
        build_bay_door(
            ctx,
            f"annex:bay_door_{bay_index}",
            bx,
            front_y,
            8.96,
            6.42,
            M,
            closed=bay_index < 2,
            glazed=False,
        )
        rounded_box(
            ctx,
            f"annex:bay_number_plate_{bay_index}",
            (bx, front_y - 0.49, 7.04),
            (1.05, 0.12, 0.50),
            M["red_dark"],
            0.030,
            semantic="bay_number_backplate",
            segments=4,
        )
        text_front(
            ctx,
            f"annex:bay_number_{bay_index}",
            str(bay_index + 1),
            (bx, front_y - 0.57, 7.04),
            0.36,
            M["white_emit"],
            0.025,
            semantic="bay_number",
        )
        rounded_box(
            ctx,
            f"annex:bay_head_flashing_{bay_index}",
            (bx, front_y - 0.54, 6.90),
            (9.43, 0.20, 0.16),
            M["aluminum"],
            0.026,
            semantic="bay_head_metal_flashing",
            segments=4,
        )

    # Every vertical facade rib terminates at the calculated gable slope.  The
    # old constant-height row protruded beyond the roof at both corners and was
    # one of the architectural equivalents of a floating part.
    rib_count = 75
    for rib_index in range(rib_count):
        rx = hall_left + 0.24 + rib_index * (hall_width - 0.48) / (rib_count - 1)
        normalized = abs(rx - hall_center) / (hall_width / 2)
        rib_top = eave + (ridge - eave) * max(0.0, 1.0 - normalized)
        rib_bottom = upper_bottom - 0.03
        box(
            ctx,
            f"annex:front_cladding_rib_{rib_index:03d}",
            (rx, front_y - 0.326, (rib_bottom + rib_top) / 2),
            (0.038, 0.060, rib_top - rib_bottom),
            M["steel"],
            0.005,
            semantic="metal_cladding_rib",
        )

    # Cabinet rear face physically overlaps the spandrel; four concealed rails
    # and cleats explain its load path while the proportions follow reference_03.
    for rail_index, rx in enumerate(
        (hall_center - 6.0, hall_center - 2.0, hall_center + 2.0, hall_center + 6.0)
    ):
        box(
            ctx,
            f"annex:sign_mount_rail_{rail_index}",
            (rx, front_y - 0.265, 8.18),
            (0.16, 0.34, 1.34),
            M["steel"],
            0.018,
            semantic="station_sign_mounting_rail",
        )
    build_identity_sign(
        ctx,
        "annex:identity",
        "FIRE STATION",
        (hall_center, front_y - 0.44, 8.18),
        15.80,
        1.72,
        1.42,
        M,
    )
    build_facade_fire_connection(
        ctx, "annex:front_fdc", (22.10, front_y - 0.47, 1.48), M
    )

    # Low glazed administration wing and raised red stair/tower volume at the
    # right reproduce the reference hierarchy instead of the previous generic
    # window-over-door box.
    office_left, office_right = hall_right, 26.95
    office_center = (office_left + office_right) / 2
    office_width = office_right - office_left
    office_depth = 18.5
    office_center_y = front_y + office_depth / 2
    box(
        ctx,
        "annex:office_shell",
        (office_center, office_center_y, 3.16),
        (office_width, office_depth, 6.32),
        M["gray_clad"],
        0.04,
        semantic="station_administration_wing",
    )
    box(
        ctx,
        "annex:office_roof_membrane",
        (office_center, office_center_y, 6.37),
        (office_width + 0.18, office_depth + 0.18, 0.22),
        M["roof"],
        0.035,
        semantic="administration_roof",
    )
    box(
        ctx,
        "annex:office_stone_plinth",
        (office_center, front_y - 0.01, 0.82),
        (office_width, 0.58, 1.60),
        M["stone"],
        0.025,
        semantic="stone_veneer_base",
    )
    masonry_relief_panel(
        ctx,
        "annex:office_stone_relief",
        (office_center, front_y - 0.325, 0.82),
        office_width - 0.20,
        1.50,
        0.065,
        M["stone"],
        0.70,
        0.27,
        "split_face_stone_relief",
    )
    for joint_index in range(9):
        jx = office_left + 0.55 + joint_index * (office_width - 1.10) / 8
        box(
            ctx,
            f"annex:office_panel_joint_{joint_index}",
            (jx, front_y - 0.315, 4.28),
            (0.038, 0.028, 3.70),
            M["sealant"],
            0.004,
            semantic="metal_panel_joint",
        )

    build_front_window(
        ctx,
        "annex:office_window",
        office_left + 2.25,
        front_y - 0.33,
        3.00,
        3.72,
        2.62,
        M,
        2,
        2,
    )
    build_glazed_entry(
        ctx,
        "annex:office_entry",
        office_right - 2.35,
        front_y - 0.31,
        2.30,
        4.10,
        4.14,
        M,
        2,
    )
    # Lean-to standing-seam canopy with wall ledger, front fascia, roof ribs,
    # tension rods and end closures; every part meets another structural part.
    canopy_z = 4.72
    box(
        ctx,
        "annex:office_canopy_wall_ledger",
        (office_center, front_y - 0.32, canopy_z + 0.16),
        (office_width - 0.35, 0.20, 0.28),
        M["red_dark"],
        0.030,
        semantic="public_entry_canopy_ledger",
    )
    box(
        ctx,
        "annex:office_entry_canopy",
        (office_center, front_y - 1.19, canopy_z),
        (office_width - 0.25, 1.90, 0.20),
        M["roof"],
        0.035,
        rotation=(-0.075, 0, 0),
        semantic="public_entry_canopy",
    )
    rounded_box(
        ctx,
        "annex:office_canopy_red_fascia",
        (office_center, front_y - 2.11, canopy_z - 0.08),
        (office_width - 0.18, 0.20, 0.34),
        M["red"],
        0.035,
        semantic="public_entry_canopy_fascia",
        segments=4,
    )
    for seam_index in range(19):
        sx = office_left + 0.30 + seam_index * (office_width - 0.60) / 18
        box(
            ctx,
            f"annex:office_canopy_seam_{seam_index:02d}",
            (sx, front_y - 1.18, canopy_z + 0.115),
            (0.032, 1.72, 0.045),
            M["steel"],
            0.005,
            rotation=(-0.075, 0, 0),
            semantic="standing_seam_rib",
        )
    for rod_index, rx in enumerate((office_left + 1.05, office_right - 1.05)):
        beam(
            ctx,
            f"annex:office_canopy_tension_rod_{rod_index}",
            (rx, front_y - 0.12, 5.55),
            (rx, front_y - 2.05, canopy_z + 0.04),
            0.036,
            M["steel"],
            "canopy_tension_rod",
            14,
        )
        rounded_box(
            ctx,
            f"annex:office_canopy_wall_plate_{rod_index}",
            (rx, front_y - 0.34, 5.55),
            (0.32, 0.10, 0.32),
            M["steel"],
            0.035,
            semantic="canopy_tension_rod_wall_plate",
            segments=4,
        )

    tower_x, tower_y = office_right - 2.15, 1.55
    box(
        ctx,
        "annex:tower_lower_shell",
        (tower_x, tower_y, 4.65),
        (4.35, 10.25, 9.30),
        M["gray_clad"],
        0.04,
        semantic="reference_stair_tower",
    )
    box(
        ctx,
        "annex:tower_red_upper",
        (tower_x, tower_y, 10.55),
        (4.48, 10.35, 2.70),
        M["red_clad"],
        0.04,
        semantic="reference_red_tower_crown",
    )
    rounded_box(
        ctx,
        "annex:tower_roof_coping",
        (tower_x, tower_y, 11.98),
        (4.70, 10.60, 0.24),
        M["roof"],
        0.055,
        semantic="tower_metal_coping",
        segments=4,
    )
    for seam_index in range(9):
        tx = tower_x - 1.90 + seam_index * 0.475
        box(
            ctx,
            f"annex:tower_red_rib_{seam_index:02d}",
            (tx, tower_y - 5.21, 10.55),
            (0.035, 0.055, 2.50),
            M["steel"],
            0.005,
            semantic="metal_cladding_rib",
        )

    build_rooftop_plant(
        ctx, "annex:office_roof_plant", (office_center - 1.4, 2.8, 6.68), M, 0.62
    )
    build_roof_detail_cluster(
        ctx, "annex:office_roof_detail", (office_left + 1.8, 0.2, 6.58), M, 0.64
    )
    for light_index, lx in enumerate((-22.8, -12.5, -2.0, 8.5, 18.7, 25.1)):
        light_z = 8.55 if lx < office_left else 5.64
        box(
            ctx,
            f"annex:wall_light_{light_index}",
            (lx, front_y - 0.45, light_z),
            (0.48, 0.34, 0.21),
            M["black"],
            0.05,
            rotation=(-0.16, 0, 0),
            semantic="wall_pack_light",
        )
        box(
            ctx,
            f"annex:wall_light_lens_{light_index}",
            (lx, front_y - 0.57, light_z - 0.07),
            (0.34, 0.045, 0.11),
            M["headlamp"],
            0.02,
            semantic="wall_pack_lens",
        )

    for pipe_index, x in enumerate(
        (hall_left + 0.34, hall_right - 0.34, office_left + 0.28, office_right - 0.28)
    ):
        cylinder(
            ctx,
            f"annex:downpipe_{pipe_index}",
            (
                x,
                rear_y + 0.34
                if pipe_index < 2
                else office_center_y + office_depth / 2 + 0.22,
                3.82,
            ),
            0.052,
            7.48,
            M["steel"],
            16,
            semantic="rainwater_downpipe",
            bevel=0.005,
        )
        for clip_index, clip_z in enumerate((1.05, 2.55, 4.05, 5.55, 7.05)):
            box(
                ctx,
                f"annex:downpipe_clip_{pipe_index}_{clip_index}",
                (
                    x,
                    (
                        rear_y + 0.48
                        if pipe_index < 2
                        else office_center_y + office_depth / 2 + 0.36
                    ),
                    clip_z,
                ),
                (0.20, 0.10, 0.045),
                M["steel"],
                0.007,
                semantic="pipe_bracket",
            )

    if include_site:
        foundation_left, foundation_right = hall_left - 0.35, office_right + 0.35
        box(
            ctx,
            "annex:foundation",
            ((foundation_left + foundation_right) / 2, 0.15, -0.04),
            (foundation_right - foundation_left, depth + 1.0, 0.45),
            M["concrete"],
            0.04,
            semantic="station_foundation",
        )
        rounded_box(
            ctx,
            "annex:entry_landing",
            (office_right - 2.35, front_y - 1.30, 0.20),
            (4.80, 2.20, 0.22),
            M["concrete_light"],
            0.055,
            semantic="accessible_entry_landing",
            segments=4,
        )
        for joint_index in range(5):
            box(
                ctx,
                f"annex:entry_landing_joint_{joint_index}",
                (office_right - 4.15 + joint_index * 0.90, front_y - 1.30, 0.325),
                (0.018, 1.95, 0.012),
                M["concrete_joint"],
                0.002,
                semantic="hardscape_control_joint",
            )

    ctx.collection["c2w_bay_count"] = 4
    ctx.collection[
        "c2w_architecture"
    ] = "reference03_four_bay_vertical_panel_gabled_station_with_glazed_office_and_red_tower"


def build_fire_station_asset(
    variant,
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    include_site=True,
    materials=None,
):
    """Build one complete station archetype from reusable procedural source."""
    if variant not in STATION_VARIANTS:
        raise ValueError(
            f"Unknown fire-station variant {variant!r}; expected one of {STATION_VARIANTS}"
        )
    M = materials or make_materials()
    asset_id = f"fire_station.{variant}.v6"
    host = parent or bpy.context.scene.collection
    ctx = new_context(
        host,
        "STATION_" + variant.upper(),
        variant,
        asset_id,
        "fire_station",
        origin,
        yaw,
    )
    if variant == "civic_headquarters":
        build_civic_headquarters(ctx, M, include_site)
        reference_index = 4
    else:
        build_industrial_annex(ctx, M, include_site)
        reference_index = 3
    ctx.collection["c2w_reference_index"] = reference_index
    ctx.collection["c2w_reference_url"] = REFERENCE_URLS[reference_index - 1]
    ctx.collection["c2w_front_direction"] = "local_negative_y"
    ctx.collection[
        "c2w_modeling_quality"
    ] = "reference_grade_photoreal_complex_procedural_v6_reference_reconstruction"
    ctx.collection["c2w_external_blend_inputs"] = 0
    return ctx.collection


# ---------------------------------------------------------------------------
# Fire-service precinct composition and site systems


def build_hydrant(ctx, name, loc, M):
    x, y, z = loc
    cylinder(
        ctx,
        name + ":barrel",
        (x, y, z + 0.62),
        0.19,
        1.02,
        M["red"],
        28,
        semantic="fire_hydrant_barrel",
        bevel=0.018,
    )
    cylinder(
        ctx,
        name + ":base_flange",
        (x, y, z + 0.17),
        0.31,
        0.12,
        M["red_dark"],
        28,
        semantic="hydrant_base_flange",
        bevel=0.012,
    )
    cylinder(
        ctx,
        name + ":bonnet",
        (x, y, z + 1.16),
        0.27,
        0.18,
        M["red"],
        28,
        semantic="hydrant_bonnet",
        bevel=0.025,
    )
    sphere(
        ctx,
        name + ":dome",
        (x, y, z + 1.28),
        (0.23, 0.23, 0.14),
        M["red"],
        "hydrant_bonnet_dome",
        24,
        12,
    )
    cylinder(
        ctx,
        name + ":stem_nut",
        (x, y, z + 1.43),
        0.075,
        0.09,
        M["chrome"],
        8,
        semantic="hydrant_operating_nut",
        bevel=0.008,
    )
    for side in (-1, 1):
        sx = x + side * 0.26
        cylinder(
            ctx,
            f"{name}:side_nozzle_{side}",
            (sx, y, z + 0.81),
            0.14,
            0.22,
            M["chrome"],
            24,
            (0, side * math.pi / 2, 0),
            "hydrant_hose_nozzle",
            0.012,
        )
        cylinder(
            ctx,
            f"{name}:side_cap_{side}",
            (x + side * 0.39, y, z + 0.81),
            0.16,
            0.08,
            M["red"],
            24,
            (0, side * math.pi / 2, 0),
            "hydrant_nozzle_cap",
            0.012,
        )
        curve_tube(
            ctx,
            f"{name}:retaining_chain_{side}",
            [
                (x + side * 0.41, y, z + 0.84),
                (x + side * 0.43, y + 0.10, z + 0.58),
                (x + side * 0.20, y + 0.11, z + 0.50),
            ],
            0.012,
            M["steel"],
            "hydrant_cap_chain",
        )


def build_security_camera(ctx, name, loc, target, M):
    x, y, z = loc
    beam(
        ctx,
        name + ":wall_arm",
        (x, y, z),
        (x, y - 0.36, z - 0.04),
        0.035,
        M["steel"],
        "security_camera_mount",
        12,
    )
    box(
        ctx,
        name + ":housing",
        (x, y - 0.48, z - 0.08),
        (0.24, 0.42, 0.22),
        M["white"],
        0.055,
        rotation=(-0.18, 0, 0),
        semantic="security_camera_housing",
    )
    cylinder(
        ctx,
        name + ":lens",
        (x, y - 0.71, z - 0.12),
        0.075,
        0.055,
        M["glass_dark"],
        24,
        (math.pi / 2, 0, 0),
        "security_camera_lens",
        0.008,
    )


def build_site_light(ctx, name, loc, M):
    x, y, z = loc
    cylinder(
        ctx,
        name + ":base",
        (x, y, z + 0.25),
        0.32,
        0.48,
        M["concrete"],
        24,
        semantic="site_light_base",
        bevel=0.025,
    )
    cylinder(
        ctx,
        name + ":pole",
        (x, y, z + 4.9),
        0.11,
        9.35,
        M["steel"],
        20,
        semantic="site_light_pole",
        bevel=0.008,
    )
    box(
        ctx,
        name + ":crossarm",
        (x, y, z + 9.54),
        (3.10, 0.15, 0.13),
        M["steel"],
        0.025,
        semantic="site_light_crossarm",
    )
    for side in (-1, 1):
        box(
            ctx,
            f"{name}:luminaire_{side}",
            (x + side * 1.28, y - 0.12, z + 9.43),
            (1.04, 0.46, 0.18),
            M["black"],
            0.065,
            rotation=(-0.12, 0, 0),
            semantic="site_luminaire",
        )
        box(
            ctx,
            f"{name}:lens_{side}",
            (x + side * 1.28, y - 0.34, z + 9.36),
            (0.84, 0.035, 0.09),
            M["headlamp"],
            0.018,
            semantic="site_luminaire_lens",
        )


def build_complex_tree(ctx, name, loc, M, seed, scale=1.0):
    rng = random.Random(seed)
    x, y, z = loc
    trunk_h = rng.uniform(4.8, 6.0) * scale
    cylinder(
        ctx,
        name + ":trunk",
        (x, y, z + trunk_h / 2),
        0.28 * scale,
        trunk_h,
        M["bark"],
        24,
        semantic="botanical_trunk",
        bevel=0.014,
    )
    branch_tips = []
    for branch in range(9):
        angle = 2 * math.pi * branch / 9 + rng.uniform(-0.22, 0.22)
        start_z = z + trunk_h * rng.uniform(0.52, 0.86)
        length = rng.uniform(1.6, 3.1) * scale
        tip = Vector(
            (
                x + math.cos(angle) * length,
                y + math.sin(angle) * length,
                start_z + rng.uniform(0.7, 1.8) * scale,
            )
        )
        beam(
            ctx,
            f"{name}:primary_branch_{branch:02d}",
            (x, y, start_z),
            tip,
            rng.uniform(0.065, 0.11) * scale,
            M["bark"],
            "botanical_primary_branch",
            12,
        )
        branch_tips.append(tip)
        for twig in range(3):
            twig_angle = angle + rng.uniform(-0.75, 0.75)
            twig_tip = tip + Vector(
                (
                    math.cos(twig_angle) * rng.uniform(0.65, 1.35) * scale,
                    math.sin(twig_angle) * rng.uniform(0.65, 1.35) * scale,
                    rng.uniform(0.25, 0.95) * scale,
                )
            )
            beam(
                ctx,
                f"{name}:twig_{branch:02d}_{twig:02d}",
                tip,
                twig_tip,
                rng.uniform(0.025, 0.045) * scale,
                M["bark"],
                "botanical_branchlet",
                10,
            )
            leaf_mat = M["leaf_light"] if (branch + twig) % 3 == 0 else M["leaf"]
            irregular_canopy(
                ctx,
                f"{name}:leaf_cluster_{branch:02d}_{twig:02d}",
                twig_tip,
                (
                    rng.uniform(0.65, 1.05) * scale,
                    rng.uniform(0.55, 0.95) * scale,
                    rng.uniform(0.58, 0.92) * scale,
                ),
                leaf_mat,
                seed + branch * 3 + twig,
                "botanical_leaf_cluster",
            )
    crown_z = z + trunk_h + 1.55 * scale
    for crown in range(7):
        angle = 2 * math.pi * crown / 7
        center = (
            x + math.cos(angle) * 1.25 * scale,
            y + math.sin(angle) * 1.10 * scale,
            crown_z + (crown % 2) * 0.50 * scale,
        )
        irregular_canopy(
            ctx,
            f"{name}:crown_mass_{crown:02d}",
            center,
            (1.24 * scale, 1.08 * scale, 1.10 * scale),
            M["leaf_light"] if crown % 3 == 0 else M["leaf"],
            seed + 80 + crown,
            "botanical_leaf_canopy",
        )


def build_shrub(ctx, name, loc, M, seed, scale=1.0):
    rng = random.Random(seed)
    x, y, z = loc
    for branch in range(7):
        angle = 2 * math.pi * branch / 7 + rng.uniform(-0.25, 0.25)
        tip = (
            x + math.cos(angle) * rng.uniform(0.28, 0.52) * scale,
            y + math.sin(angle) * rng.uniform(0.28, 0.52) * scale,
            z + rng.uniform(0.42, 0.85) * scale,
        )
        beam(
            ctx,
            f"{name}:branch_{branch}",
            (x, y, z + 0.08),
            tip,
            0.018 * scale,
            M["bark"],
            "shrub_branch",
            10,
        )
        irregular_canopy(
            ctx,
            f"{name}:leaf_mass_{branch}",
            tip,
            (
                rng.uniform(0.26, 0.43) * scale,
                rng.uniform(0.24, 0.42) * scale,
                rng.uniform(0.24, 0.40) * scale,
            ),
            M["leaf_light"] if branch % 3 == 0 else M["leaf"],
            seed + branch,
            "shrub_leaf_cluster",
        )


def build_generator_set(ctx, name, loc, M):
    x, y, z = loc
    box(
        ctx,
        name + ":pad",
        (x, y, z + 0.10),
        (4.30, 2.40, 0.20),
        M["concrete_light"],
        0.04,
        semantic="generator_concrete_pad",
    )
    box(
        ctx,
        name + ":enclosure",
        (x, y, z + 1.28),
        (3.80, 1.86, 2.18),
        M["steel"],
        0.09,
        semantic="emergency_generator_enclosure",
    )
    for side in (-1, 1):
        for slat in range(13):
            sy = y - 0.65 + slat * 0.108
            box(
                ctx,
                f"{name}:louver_{side}_{slat:02d}",
                (x + side * 1.925, sy, z + 1.33),
                (0.035, 0.075, 1.48),
                M["black"],
                0.005,
                rotation=(0, 0, side * 0.12),
                semantic="generator_vent_louver",
            )
    cylinder(
        ctx,
        name + ":exhaust",
        (x + 1.33, y + 0.48, z + 2.80),
        0.07,
        1.20,
        M["steel"],
        18,
        semantic="generator_exhaust_stack",
        bevel=0.006,
    )
    cylinder(
        ctx,
        name + ":rain_cap",
        (x + 1.33, y + 0.48, z + 3.43),
        0.13,
        0.08,
        M["steel"],
        20,
        semantic="generator_exhaust_rain_cap",
        bevel=0.008,
    )
    box(
        ctx,
        name + ":control_panel",
        (x - 1.20, y - 0.96, z + 1.35),
        (0.72, 0.06, 0.55),
        M["black"],
        0.035,
        semantic="generator_control_panel",
    )
    box(
        ctx,
        name + ":control_display",
        (x - 1.20, y - 1.00, z + 1.43),
        (0.38, 0.025, 0.20),
        M["lcd"],
        0.018,
        semantic="generator_status_display",
    )


def build_distant_service_building(
    ctx, name, center, width, depth, height, M, facade_material, window_count=5
):
    """Detailed but subordinate municipal fabric for a believable horizon."""
    cx, cy = center
    front_y = cy - depth / 2
    box(
        ctx,
        name + ":shell",
        (cx, cy, height / 2),
        (width, depth, height),
        facade_material,
        0.035,
        semantic="distant_urban_building_shell",
    )
    box(
        ctx,
        name + ":roof",
        (cx, cy, height + 0.12),
        (width + 0.25, depth + 0.25, 0.28),
        M["roof"],
        0.035,
        semantic="distant_urban_building_roof",
    )
    for edge, (loc, dims) in enumerate(
        (
            ((cx, front_y, height + 0.42), (width + 0.35, 0.50, 0.62)),
            ((cx, cy + depth / 2, height + 0.42), (width + 0.35, 0.50, 0.62)),
            ((cx - width / 2, cy, height + 0.42), (0.50, depth, 0.62)),
            ((cx + width / 2, cy, height + 0.42), (0.50, depth, 0.62)),
        )
    ):
        box(
            ctx,
            f"{name}:parapet_{edge}",
            loc,
            dims,
            facade_material,
            0.025,
            semantic="distant_roof_parapet",
        )
    rounded_box(
        ctx,
        name + ":front_coping",
        (cx, front_y - 0.02, height + 0.76),
        (width + 0.62, 0.72, 0.14),
        M["aluminum"],
        0.030,
        semantic="distant_roof_coping",
        segments=4,
    )
    box(
        ctx,
        name + ":base",
        (cx, front_y - 0.29, 0.62),
        (width - 0.30, 0.16, 1.20),
        M["stone"],
        0.018,
        semantic="distant_building_masonry_base",
    )
    spacing = width / max(1, window_count)
    for window_index in range(window_count):
        wx = cx - width / 2 + spacing / 2 + window_index * spacing
        build_front_window(
            ctx,
            f"{name}:window_{window_index}",
            wx,
            front_y - 0.33,
            height * 0.58,
            spacing * 0.56,
            min(2.25, height * 0.25),
            M,
            2,
            1,
            M["steel"],
            M["architectural_glass"],
        )
        box(
            ctx,
            f"{name}:pilaster_{window_index}",
            (wx - spacing * 0.45, front_y - 0.34, height * 0.48),
            (0.20, 0.20, height * 0.68),
            M["precast"],
            0.018,
            semantic="distant_facade_pilaster",
        )
    for dock_index, dx in enumerate((cx - width * 0.28, cx + width * 0.28)):
        rounded_box(
            ctx,
            f"{name}:service_door_{dock_index}",
            (dx, front_y - 0.36, 1.72),
            (3.05, 0.12, 3.18),
            M["aluminum"],
            0.025,
            semantic="distant_service_door",
            segments=4,
        )
        for slat in range(11):
            box(
                ctx,
                f"{name}:service_door_slat_{dock_index}_{slat}",
                (dx, front_y - 0.435, 0.34 + slat * 0.27),
                (2.86, 0.025, 0.024),
                M["steel"],
                0.004,
                semantic="distant_service_door_slat",
            )
        rounded_box(
            ctx,
            f"{name}:dock_bumper_{dock_index}",
            (dx, front_y - 0.56, 0.38),
            (3.32, 0.36, 0.34),
            M["rubber"],
            0.055,
            semantic="distant_loading_dock_bumper",
            segments=4,
        )
    for unit_index, ux in enumerate((cx - width * 0.20, cx + width * 0.22)):
        build_rooftop_plant(
            ctx, f"{name}:roof_unit_{unit_index}", (ux, cy, height + 0.32), M, 0.52
        )
    build_roof_detail_cluster(
        ctx, name + ":roof_detail", (cx, cy + depth * 0.22, height + 0.30), M, 0.55
    )


def build_site_context(parent, M):
    ctx = new_context(
        parent,
        "FIRE_STATION_SITE",
        "fire_station_precinct_site",
        "fire_region.site_context.v6",
        "site",
        (0, 0, 0),
        0.0,
    )
    # The requested vegetation-free context is entirely mineral hardscape:
    # municipal asphalt beyond the precinct and a true concrete apparatus apron.
    box(
        ctx,
        "site:municipal_hardscape_datum",
        (0, 28, -0.55),
        (5000, 5000, 0.70),
        M["urban_ground"],
        0.0,
        semantic="municipal_hardscape_datum",
    )
    box(
        ctx,
        "site:road_subbase",
        (0, -39.5, -0.22),
        (360, 18.0, 0.70),
        M["concrete"],
        0.035,
        semantic="road_subbase",
    )
    box(
        ctx,
        "site:public_road",
        (0, -39.5, 0.10),
        (360, 17.1, 0.28),
        M["asphalt"],
        0.045,
        semantic="public_road",
    )
    box(
        ctx,
        "site:sidewalk",
        (0, -28.6, 0.16),
        (340, 3.1, 0.28),
        M["concrete_light"],
        0.035,
        semantic="public_sidewalk",
    )
    box(
        ctx,
        "site:apparatus_apron",
        (-2, -1.8, 0.08),
        (157, 49.0, 0.28),
        M["concrete"],
        0.045,
        semantic="apparatus_apron",
    )
    # A serviced urban block behind the precinct supplies a real horizon and
    # scale cues in aerial views.  Every background building still has a
    # constructed envelope, glazing, docks, parapets and roof plant.
    box(
        ctx,
        "site:rear_service_road",
        (0, 62.0, 0.03),
        (300, 13.5, 0.20),
        M["asphalt"],
        0.035,
        semantic="distant_service_road",
    )
    for dash_index, x in enumerate(range(-145, 146, 10)):
        box(
            ctx,
            f"site:rear_service_road_dash_{dash_index:02d}",
            (x, 62.0, 0.145),
            (5.2, 0.13, 0.018),
            M["road_yellow"],
            0.003,
            semantic="distant_road_lane_marking",
        )
    build_distant_service_building(
        ctx, "context:west_public_works", (-76, 88), 54, 27, 10.5, M, M["brick"], 6
    )
    build_distant_service_building(
        ctx, "context:center_training", (-10, 101), 46, 24, 13.0, M, M["precast"], 5
    )
    build_distant_service_building(
        ctx, "context:east_utilities", (52, 88), 48, 28, 11.5, M, M["gray_clad"], 5
    )
    build_distant_service_building(
        ctx, "context:far_logistics", (108, 116), 62, 30, 12.5, M, M["brick_red"], 7
    )
    # Expansion joints prevent the apron reading as one featureless slab.
    for joint_index, x in enumerate(range(-76, 77, 6)):
        box(
            ctx,
            f"site:apron_longitudinal_joint_{joint_index:02d}",
            (x, -1.8, 0.235),
            (0.018, 48.6, 0.007),
            M["concrete_joint"],
            0.0015,
            semantic="concrete_expansion_joint",
        )
    for joint_index, y in enumerate(range(-25, 24, 6)):
        box(
            ctx,
            f"site:apron_transverse_joint_{joint_index:02d}",
            (-2, y, 0.235),
            (156.6, 0.018, 0.007),
            M["concrete_joint"],
            0.0015,
            semantic="concrete_expansion_joint",
        )
    # Subtle service wear interrupts the otherwise new concrete without hiding
    # the construction joints or becoming a contrasting ground patch.
    for stain_index in range(18):
        sx = -67 + (stain_index * 17) % 134
        sy = -19 + (stain_index * 11) % 34
        sphere(
            ctx,
            f"site:service_stain_{stain_index:02d}",
            (sx, sy, 0.253),
            (0.34 + (stain_index % 4) * 0.12, 0.16 + (stain_index % 3) * 0.08, 0.006),
            M["stain"],
            "apron_service_stain",
            16,
            8,
        )
    for crack_index, (x, y) in enumerate(((-61, 1), (-18, -12), (18, 8), (58, -7))):
        curve_tube(
            ctx,
            f"site:hairline_crack_{crack_index}",
            [
                (x - 2.1, y - 0.3, 0.255),
                (x - 0.8, y + 0.1, 0.256),
                (x + 0.3, y - 0.2, 0.255),
                (x + 1.7, y + 0.25, 0.256),
            ],
            0.009,
            M["stain"],
            "concrete_hairline_crack",
        )
    # Faint paired radial-tire paths connect the active doors to the fire lane.
    # Their translucent, irregular surface is intentionally much quieter than
    # painted stripes and breaks the pristine tiled-apron appearance.
    for route_index, (rx, rear_limit) in enumerate(
        ((-43.05, 18.8), (-32.35, 18.8), (55.0, 22.6))
    ):
        route_front = -23.2
        length = rear_limit - route_front
        for track_side in (-1, 1):
            box(
                ctx,
                f"site:apparatus_tire_path_{route_index}_{track_side}",
                (rx + track_side * 1.05, route_front + length / 2, 0.247),
                (0.18, length, 0.005),
                M["stain"],
                0.001,
                rotation=(0, 0, track_side * 0.004),
                semantic="apparatus_apron_tire_path",
            )
    # Rolled curb, red fire-lane face, storm inlets and public road markings.
    box(
        ctx,
        "site:front_curb",
        (0, -26.3, 0.32),
        (340, 0.50, 0.48),
        M["concrete_light"],
        0.07,
        semantic="street_curb",
    )
    box(
        ctx,
        "site:fire_lane_red_curb",
        (0, -26.58, 0.43),
        (338, 0.045, 0.24),
        M["red"],
        0.008,
        semantic="fire_lane_curb_marking",
    )
    for inlet_index, x in enumerate(range(-72, 73, 18)):
        box(
            ctx,
            f"site:storm_inlet_frame_{inlet_index}",
            (x, -26.55, 0.34),
            (2.20, 0.38, 0.10),
            M["black"],
            0.018,
            semantic="stormwater_inlet",
        )
        for slot in range(11):
            box(
                ctx,
                f"site:storm_inlet_slot_{inlet_index}_{slot:02d}",
                (x - 0.92 + slot * 0.184, -26.77, 0.39),
                (0.055, 0.045, 0.24),
                M["steel"],
                0.004,
                semantic="stormwater_grate",
            )
    for dash_index, x in enumerate(range(-172, 173, 8)):
        box(
            ctx,
            f"site:road_center_dash_{dash_index:02d}",
            (x, -39.4, 0.26),
            (4.15, 0.14, 0.022),
            M["road_yellow"],
            0.004,
            semantic="road_lane_marking",
        )
    for y, label in ((-33.2, "north_edge"), (-45.7, "south_edge")):
        box(
            ctx,
            f"site:road_edge_{label}",
            (0, y, 0.26),
            (356, 0.12, 0.022),
            M["road_white"],
            0.004,
            semantic="road_lane_marking",
        )
    # Visitor parking remains close to the administration wing but is offset
    # east of the reference-facing apparatus apron, matching the photograph's
    # unobstructed concrete response court and public-road foreground.
    box(
        ctx,
        "site:visitor_parking",
        (82.0, -8.0, 0.25),
        (27.0, 18.0, 0.10),
        M["asphalt"],
        0.035,
        semantic="visitor_parking_surface",
    )
    for stall in range(7):
        x = 69.8 + stall * 4.05
        box(
            ctx,
            f"site:parking_line_{stall:02d}",
            (x, -7.8, 0.315),
            (0.09, 7.1, 0.022),
            M["road_white"],
            0.004,
            semantic="parking_stall_marking",
        )
    box(
        ctx,
        "site:parking_header_line",
        (82, -4.25, 0.315),
        (25.8, 0.10, 0.022),
        M["road_white"],
        0.004,
        semantic="parking_stall_marking",
    )
    # Entry walks are kept as construction layers.  The prior planting beds,
    # shrubs and boundary trees are intentionally absent from the live builder.
    box(
        ctx,
        "site:hq_entry_walk",
        (7.0, 15.2, 0.29),
        (13.5, 8.2, 0.16),
        M["paver"],
        0.04,
        semantic="public_entry_paving",
    )
    box(
        ctx,
        "site:annex_entry_walk",
        (68.6, 20.0, 0.29),
        (8.2, 7.2, 0.16),
        M["paver"],
        0.04,
        semantic="public_entry_paving",
    )
    for plaza_index, (label, center, dims) in enumerate(
        (
            ("west_service", (-70.0, 13.0), (10.0, 8.0)),
            ("hq_entry", (7.0, 24.0), (12.0, 4.0)),
            ("annex_entry", (68.6, 27.0), (8.0, 4.0)),
            ("east_service", (77.0, 12.0), (8.0, 10.0)),
        )
    ):
        px, py = center
        rounded_box(
            ctx,
            f"site:hardscape_plaza_{label}",
            (px, py, 0.25),
            (dims[0], dims[1], 0.22),
            M["concrete_light"],
            0.06,
            semantic="vegetation_free_service_plaza",
            segments=4,
        )
        for joint in range(1, max(2, int(dims[0] / 2.0))):
            jx = px - dims[0] / 2 + joint * dims[0] / max(2, int(dims[0] / 2.0))
            box(
                ctx,
                f"site:plaza_joint_{plaza_index}_{joint}",
                (jx, py, 0.37),
                (0.025, dims[1] - 0.18, 0.012),
                M["sealant"],
                0.003,
                semantic="hardscape_control_joint",
            )
        # Tactile warning studs mark the pedestrian edge without adding any
        # planter-like geometry.
        for stud in range(max(4, int(dims[0] / 0.42))):
            sx = (
                px
                - dims[0] * 0.44
                + stud * dims[0] * 0.88 / max(1, max(4, int(dims[0] / 0.42)) - 1)
            )
            cylinder(
                ctx,
                f"site:tactile_stud_{plaza_index}_{stud:02d}",
                (sx, py - dims[1] / 2 + 0.36, 0.39),
                0.055,
                0.025,
                M["yellow_reflect"],
                20,
                semantic="tactile_warning_stud",
                bevel=0.006,
            )
    # Operational site equipment.
    build_hydrant(ctx, "site:front_hydrant", (-73.0, -24.2, 0.24), M)
    build_hydrant(ctx, "site:annex_hydrant", (75.5, 25.5, 0.24), M)
    build_generator_set(ctx, "site:standby_generator", (72.0, 48.0, 0.24), M)
    for light_index, pos in enumerate(
        ((-65, -23, 0.24), (-12, -23, 0.24), (30, -23, 0.24), (76, -23, 0.24))
    ):
        build_site_light(ctx, f"site:light_{light_index}", pos, M)
    for camera_index, (loc, target) in enumerate(
        (
            ((-48.0, 19.4, 8.8), (-43.0, 5.0, 1.5)),
            ((-9.0, 19.4, 9.0), (-25.0, -5.0, 1.5)),
            ((31.0, 24.2, 7.2), (43.0, 8.0, 1.5)),
            ((68.0, 24.2, 7.0), (60.0, 5.0, 1.5)),
        )
    ):
        build_security_camera(
            ctx, f"site:security_camera_{camera_index}", loc, target, M
        )
    # Freestanding civic address monument.
    box(
        ctx,
        "site:monument_footing",
        (-70.0, -20.8, 0.37),
        (8.8, 1.75, 0.46),
        M["concrete_light"],
        0.06,
        semantic="monument_sign_footing",
    )
    box(
        ctx,
        "site:monument_sign",
        (-70.0, -20.8, 1.72),
        (7.9, 0.62, 2.20),
        M["brick"],
        0.06,
        semantic="monument_sign_structure",
    )
    box(
        ctx,
        "site:monument_red_panel",
        (-70.0, -21.14, 1.80),
        (6.70, 0.08, 1.32),
        M["red"],
        0.025,
        semantic="monument_sign_panel",
    )
    text_front(
        ctx,
        "site:monument_title",
        "FIRE & RESCUE",
        (-70.0, -21.24, 2.02),
        0.43,
        M["white_emit"],
        0.03,
        semantic="monument_sign_text",
    )
    text_front(
        ctx,
        "site:monument_address",
        "STATION 1  /  TRAINING ANNEX",
        (-70.0, -21.24, 1.48),
        0.16,
        M["white"],
        0.015,
        semantic="monument_sign_text",
    )
    return ctx.collection


def build_fire_station_region(parent=None, include_site=True):
    """Live Urban-v3 entrypoint for the complete reference-driven precinct."""
    RNG.seed(20260902)
    SHARED_MESHES.clear()
    M = make_materials()
    host = parent or bpy.context.scene.collection
    root = collection("FIRE_STATION_REGION", host, "procedural_asset_group", ASSET_ID)
    root["c2w_pipeline_entrypoint"] = "generate_urban_v3_fire.build_fire_station_region"
    root["c2w_pipeline_adapter"] = "urban_assets.build_fire_station_region"
    root["c2w_truck_entrypoint"] = "generate_urban_v3_fire.build_fire_truck_asset"
    root["c2w_ambulance_entrypoint"] = "generate_urban_v3_fire.build_ambulance_asset"
    root["c2w_station_entrypoint"] = "generate_urban_v3_fire.build_fire_station_asset"
    root["c2w_reference_urls"] = json.dumps(
        REFERENCE_URLS
        + [FIRE_TRUCK_MESH_PAGE]
        + [FIRE7_MESH_SOURCES[variant]["page"] for variant in TRUCK_VARIANTS],
        ensure_ascii=False,
    )
    root["c2w_reference_driven"] = True
    root["c2w_scene_asset_inputs"] = 0
    root[
        "c2w_layout_summary"
    ] = "two station archetypes; enclosed urban pumper and compact aerial fire engine at civic bays 1-2; tandem aerial platform and a second urban pumper at annex bays 3-4; no ambulance; every empty bay shutter closed"
    root[
        "c2w_quality_profile"
    ] = "four_detailed_fire_engine_mesh_measurements+multi_type_source_only_programmatic_rebuild+true_scale_running_gear+continuous_manufactured_surfaces+formed_double_wall_rolling_shutters+operational_interiors+daylight_multiview_v7"
    root[
        "c2w_vegetation_policy"
    ] = "zero_trees_zero_shrubs_zero_planters_zero_flower_beds"
    # Build all vehicles before architecture so bay occupancy is explicit.
    civic_pumper = build_fire_truck_asset(
        "classic_pumper", root, (-43.05, 14.92, 0.05), 0.0, M
    )
    civic_aerial = build_fire_truck_asset(
        "rapid_rescue", root, (-32.35, 14.90, 0.05), 0.0, M
    )
    modern = build_fire_truck_asset(
        "modern_ladder_engine", root, (44.50, 18.03, 0.05), 0.0, M
    )
    annex_pumper = build_fire_truck_asset(
        "classic_pumper", root, (55.0, 18.96, 0.05), 0.0, M
    )
    # Source-derived dimensions are already real-world metric envelopes.  Only
    # a one-to-three-percent station-layout calibration is applied at each
    # independent pose root; local -Y points out and the rear step meets the
    # apparatus sill without the fire6 oversized/toy-like scaling.
    scale_asset_collection(
        civic_pumper, 1.02, "rear_access_step_at_civic_bay_1_threshold"
    )
    scale_asset_collection(
        civic_aerial, 1.02, "rear_access_step_at_civic_bay_2_threshold"
    )
    scale_asset_collection(modern, 0.98, "rear_access_step_at_annex_bay_3_threshold")
    scale_asset_collection(
        annex_pumper, 1.02, "rear_access_step_at_annex_bay_4_threshold"
    )
    # Then build the two independent station facilities around the apparatus layout.
    build_fire_station_asset(
        "civic_headquarters", root, (-27.0, 33.0, 0.0), 0.0, include_site, M
    )
    build_fire_station_asset(
        "industrial_annex", root, (44.0, 36.0, 0.0), 0.0, include_site, M
    )
    if include_site:
        build_site_context(root, M)
    root["c2w_truck_variants"] = json.dumps(TRUCK_VARIANTS)
    root["c2w_scene_ambulance_variants"] = json.dumps([])
    root["c2w_station_variants"] = json.dumps(STATION_VARIANTS)
    root["c2w_external_blend_inputs"] = 0
    root["c2w_reference_mesh_inputs"] = 4
    root["c2w_render_mesh_inputs"] = 0
    root["c2w_bay_occupancy"] = json.dumps(
        {
            "civic_headquarters": ["classic_pumper", "rapid_rescue", None, None],
            "industrial_annex": [None, None, "modern_ladder_engine", "classic_pumper"],
        }
    )
    return root, M


# ---------------------------------------------------------------------------
# Reference archival, daylight presentation and strict production audit


def archive_references():
    """Copy only the evidence used by the delivered fire-engine scene.

    The ambulance builder remains a backwards-compatible library entrypoint,
    but neither ambulance geometry nor its source bundle participates in this
    output.  Fire7 archives all four detailed fire-engine mesh sources so the
    production rebuild is independently auditable from inside the workspace.
    """
    REFERENCES.mkdir(parents=True, exist_ok=True)
    records = []
    for src, filename, url in zip(REFERENCE_CACHE, REFERENCE_FILES, REFERENCE_URLS):
        if not src.is_file() or src.stat().st_size < 10000:
            raise FileNotFoundError(
                f"Missing downloaded fire reference inside workspace: {src}"
            )
        dst = REFERENCES / filename
        shutil.copy2(src, dst)
        records.append(
            {
                "kind": "photographic_reference",
                "file": filename,
                "bytes": dst.stat().st_size,
                "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                "url": url,
            }
        )
    fire_mesh_dir = REFERENCES / "fire_truck_mesh_sources" / "model_49268"
    fire_mesh_dir.mkdir(parents=True, exist_ok=True)
    for src, filename in FIRE_TRUCK_REFERENCE_FILES:
        if not src.is_file() or src.stat().st_size < 100:
            raise FileNotFoundError(
                f"Missing detailed fire-truck reference inside workspace: {src}"
            )
        dst = fire_mesh_dir / filename
        shutil.copy2(src, dst)
        records.append(
            {
                "kind": "downloaded_mesh_reference",
                "asset_category": "fire_truck",
                "file": "fire_truck_mesh_sources/model_49268/" + filename,
                "bytes": dst.stat().st_size,
                "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                "url": FIRE_TRUCK_MESH_PAGE,
                "usage_terms": "CadNav local reverse-engineering evidence; listing labels Non-commercial",
                "render_geometry": False,
            }
        )
    for src, filename in FIRE_TRUCK_PREVIEW_FILES:
        if not src.is_file() or src.stat().st_size < 10_000:
            raise FileNotFoundError(f"Missing fire-truck mesh preview reference: {src}")
        dst = fire_mesh_dir / filename
        shutil.copy2(src, dst)
        records.append(
            {
                "kind": "mesh_preview_reference",
                "asset_category": "fire_truck",
                "file": "fire_truck_mesh_sources/model_49268/" + filename,
                "bytes": dst.stat().st_size,
                "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                "url": FIRE_TRUCK_MESH_PAGE,
                "render_geometry": False,
            }
        )
    fire_analysis = analyze_fire_truck_reference()
    fire_analysis_path = REFERENCES / "fire_truck_reverse_engineering.json"
    fire_analysis_path.write_text(
        json.dumps(fire_analysis, indent=2, ensure_ascii=False),
        encoding="utf8",
    )
    records.append(
        {
            "kind": "reverse_engineering_record",
            "asset_category": "fire_truck",
            "file": fire_analysis_path.name,
            "bytes": fire_analysis_path.stat().st_size,
            "sha256": hashlib.sha256(fire_analysis_path.read_bytes()).hexdigest(),
            "url": FIRE_TRUCK_MESH_PAGE,
            "render_geometry": False,
        }
    )
    # The three new high-detail type-specific source meshes.  Every model is
    # kept in its own directory to preserve provenance and filename identity.
    for variant, source in FIRE7_MESH_SOURCES.items():
        model_id = source["model_id"]
        model_dir = REFERENCES / "fire_truck_mesh_sources" / f"model_{model_id}"
        model_dir.mkdir(parents=True, exist_ok=True)
        for source_path, purpose in (
            (source["archive"], "download_archive"),
            (source["mesh"], "extracted_high_detail_mesh"),
        ):
            if not source_path.is_file() or source_path.stat().st_size < 500_000:
                raise FileNotFoundError(
                    f"Missing detailed fire-engine source: {source_path}"
                )
            target = model_dir / source_path.name
            shutil.copy2(source_path, target)
            records.append(
                {
                    "kind": "downloaded_mesh_reference",
                    "asset_category": "fire_truck",
                    "variant": variant,
                    "model_id": model_id,
                    "purpose": purpose,
                    "file": str(target.relative_to(REFERENCES)),
                    "bytes": target.stat().st_size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "url": source["page"],
                    "published_vertices": source["published_vertices"],
                    "published_polygons": source["published_polygons"],
                    "render_geometry": False,
                }
            )
        for preview_index, source_path in enumerate(source["preview_files"], 1):
            if not source_path.is_file() or source_path.stat().st_size < 20_000:
                raise FileNotFoundError(
                    f"Missing detailed fire-engine preview: {source_path}"
                )
            suffix = source_path.suffix.lower()
            target = model_dir / f"preview_{preview_index:02d}{suffix}"
            shutil.copy2(source_path, target)
            records.append(
                {
                    "kind": "mesh_preview_reference",
                    "asset_category": "fire_truck",
                    "variant": variant,
                    "model_id": model_id,
                    "file": str(target.relative_to(REFERENCES)),
                    "bytes": target.stat().st_size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "url": source["page"],
                    "render_geometry": False,
                }
            )
    suite_analysis = analyze_fire_truck_reference_suite()
    suite_path = REFERENCES / "fire_truck_reverse_engineering_suite.json"
    suite_path.write_text(
        json.dumps(suite_analysis, indent=2, ensure_ascii=False),
        encoding="utf8",
    )
    records.append(
        {
            "kind": "reverse_engineering_record",
            "asset_category": "fire_truck",
            "file": suite_path.name,
            "bytes": suite_path.stat().st_size,
            "sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
            "url": ", ".join(source["page"] for source in FIRE7_MESH_SOURCES.values()),
            "render_geometry": False,
        }
    )
    return records


def setup_daylight():
    world = bpy.data.worlds.new(PREFIX + "clear_day_world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = True
    sky.sun_elevation = math.radians(45.0)
    sky.sun_rotation = math.radians(226.0)
    sky.altitude = 0.18
    sky.air_density = 1.0
    sky.dust_density = 0.32
    sky.ozone_density = 0.38
    # The physical sky is both visible to camera and used for illumination.
    # This keeps the horizon, reflections and object light in the same colour
    # space instead of fire6's flat camera-only blue gradient.
    background.inputs["Strength"].default_value = 0.46
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], out.inputs["Surface"])
    bpy.context.scene.world = world
    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 2.35
    sun_data.angle = math.radians(1.25)
    sun = bpy.data.objects.new(PREFIX + "day_sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.location = (-85, -105, 125)
    sun.rotation_euler = (
        (Vector((0, 10, 4)) - sun.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(sun, "daylight")
    fill_data = bpy.data.lights.new(PREFIX + "day_fill", "AREA")
    fill_data.energy = 92
    fill_data.shape = "DISK"
    fill_data.size = 62
    fill = bpy.data.objects.new(PREFIX + "day_fill", fill_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.location = (55, -48, 62)
    fill.rotation_euler = (
        (Vector((0, 16, 4)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    )
    tag(fill, "daylight_fill")


def configure_scene(preview=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 900 if preview else 1600
    scene.render.resolution_y = 560 if preview else 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 22
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.48
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "use_raytracing"):
            # Targeted 900 px diagnostic previews focus on geometry and
            # composition; disabling screen tracing avoids headless EGL shader
            # stalls.  Full 1600 px delivery renders retain ray tracing.
            scene.eevee.use_raytracing = not preview
            scene.eevee.ray_tracing_method = "SCREEN"
            options = scene.eevee.ray_tracing_options
            options.resolution_scale = "2"
            options.screen_trace_quality = 0.42 if preview else 0.68
            options.screen_trace_thickness = 0.16
            options.trace_max_roughness = 0.62
            options.use_denoise = True
        if hasattr(scene.eevee, "taa_render_samples"):
            # Eight ray-traced EEVEE samples are already temporally stable in
            # the 900px QA renders.  Keep that proven sample count for the
            # 1600px delivery so the ten-view production batch remains
            # practical without reducing geometry, resolution, tracing, or
            # denoising quality.
            scene.eevee.taa_render_samples = 8
        if hasattr(scene.eevee, "taa_samples"):
            scene.eevee.taa_samples = 8
        if hasattr(scene.eevee, "use_fast_gi"):
            scene.eevee.use_fast_gi = True
            scene.eevee.fast_gi_quality = 0.50 if preview else 0.72
            scene.eevee.fast_gi_ray_count = 3 if preview else 5
            scene.eevee.fast_gi_step_count = 10 if preview else 18
        if hasattr(scene.eevee, "shadow_ray_count"):
            scene.eevee.shadow_ray_count = 2 if preview else 4
            scene.eevee.shadow_step_count = 8 if preview else 12
            scene.eevee.shadow_resolution_scale = 1.0
    scene.camera = None


def camera(name, location, target, lens, role):
    data = bpy.data.cameras.new(PREFIX + name)
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = role in {"apparatus_close", "detail", "door_detail"}
    data.dof.focus_distance = (Vector(target) - Vector(location)).length
    data.dof.aperture_fstop = 7.1
    data.dof.aperture_blades = 7
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (
        (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    )
    obj["c2w_view_role"] = role
    return tag(obj, "validation_camera")


def camera_specs():
    return [
        ("01_full_precinct_front_far.png", (-3, -108, 12.0), (-2, 26, 4.9), 33, "far"),
        (
            "02_full_precinct_southwest_aerial.png",
            (-105, -54, 31),
            (-2, 30, 5.0),
            36,
            "aerial",
        ),
        (
            "03_full_precinct_southeast_aerial.png",
            (104, -51, 30),
            (0, 30, 5.0),
            36,
            "aerial",
        ),
        (
            "04_civic_headquarters_front_near.png",
            (-27, -35, 5.8),
            (-27, 21.0, 4.5),
            40,
            "near",
        ),
        (
            "05_industrial_annex_front_near.png",
            (44.6, -49.0, 5.8),
            (44.6, 24.0, 4.8),
            47,
            "near",
        ),
        (
            "06_reverse_engineered_urban_pumper_close.png",
            (-52.0, 2.2, 2.72),
            (-43.0, 15.10, 1.88),
            56,
            "apparatus_close",
        ),
        (
            "07_reverse_engineered_aerial_platform_front_close.png",
            (28.25, -2.0, 4.73),
            (44.5, 16.50, 2.58),
            55,
            "apparatus_close",
        ),
        (
            "08_reverse_engineered_aerial_ladder_mechanics_close.png",
            (29.2, 16.2, 3.65),
            (44.5, 19.55, 2.75),
            61,
            "apparatus_close",
        ),
        (
            "09_closed_rolling_shutter_detail.png",
            (12.8, 4.2, 4.35),
            (23.5, 23.7, 3.35),
            60,
            "door_detail",
        ),
        (
            "10_open_apparatus_bay_interior.png",
            (-52.0, 6.6, 3.20),
            (-43.0, 28.0, 3.00),
            50,
            "interior",
        ),
    ]


def render_all(cameras):
    selected = {
        item.strip()
        for item in os.environ.get("C2W_FIRE_VIEW_FILTER", "").split(",")
        if item.strip()
    }
    scene = bpy.context.scene
    for filename, cam, role in cameras:
        if selected and not any(filename.startswith(prefix) for prefix in selected):
            continue
        print(f"[fire] rendering {role}: {filename}", flush=True)
        scene.camera = cam
        scene.render.filepath = str(RENDERS / filename)
        bpy.ops.render.render(write_still=True)


def semantic_counts(objects=None):
    counts = {}
    for obj in objects or bpy.context.scene.objects:
        semantic = obj.get("c2w_semantic", "unclassified")
        counts[semantic] = counts.get(semantic, 0) + 1
    return dict(sorted(counts.items()))


def render_diagnostics():
    diagnostics = {}
    for filename, _, _, _, _ in camera_specs():
        path = RENDERS / filename
        item = {
            "path": str(path),
            "bytes": path.stat().st_size if path.is_file() else 0,
        }
        if not path.is_file() or path.stat().st_size < 50000:
            item.update({"passed": False, "reason": "missing_or_too_small"})
            diagnostics[filename] = item
            continue
        image = bpy.data.images.load(str(path), check_existing=False)
        width, height = image.size
        values = []
        for gy in range(9):
            py = min(height - 1, int((gy + 0.5) * height / 9))
            for gx in range(15):
                px = min(width - 1, int((gx + 0.5) * width / 15))
                idx = 4 * (py * width + px)
                values.append(
                    (image.pixels[idx] + image.pixels[idx + 1] + image.pixels[idx + 2])
                    / 3
                )
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        dark = sum(value < 0.012 for value in values) / len(values)
        bright = sum(value > 0.99 for value in values) / len(values)
        passed = (
            width >= 1600
            and height >= 1000
            and variance >= 0.002
            and dark < 0.72
            and bright < 0.72
        )
        item.update(
            {
                "passed": passed,
                "resolution": [width, height],
                "sample_mean": round(mean, 6),
                "sample_variance": round(variance, 6),
                "dark_fraction": round(dark, 4),
                "bright_fraction": round(bright, 4),
            }
        )
        diagnostics[filename] = item
        bpy.data.images.remove(image)
    return diagnostics


def validate(root, cameras, reference_records, rendered=False):
    scene = bpy.context.scene
    objects = list(bpy.context.scene.objects)
    renderables = [
        obj
        for obj in objects
        if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
    ]
    trucks = [
        coll for coll in root.children if coll.get("c2w_role") == "fire_truck_asset"
    ]
    ambulances = [
        coll for coll in root.children if coll.get("c2w_role") == "ambulance_asset"
    ]
    stations = [
        coll for coll in root.children if coll.get("c2w_role") == "fire_station_asset"
    ]
    truck_audit = {}
    for variant in TRUCK_VARIANTS:
        observed = [obj for obj in objects if obj.get("c2w_truck_variant") == variant]
        counts = semantic_counts(observed)
        truck_audit[variant] = {
            "objects": len(observed),
            "renderables": sum(
                obj.type in {"MESH", "CURVE", "FONT"} for obj in observed
            ),
            "semantic_counts": counts,
        }
    ambulance_audit = {}
    for variant in AMBULANCE_VARIANTS:
        observed = [
            obj for obj in objects if obj.get("c2w_ambulance_variant") == variant
        ]
        counts = semantic_counts(observed)
        ambulance_audit[variant] = {
            "objects": len(observed),
            "renderables": sum(
                obj.type in {"MESH", "CURVE", "FONT"} for obj in observed
            ),
            "semantic_counts": counts,
        }
    station_audit = {}
    for variant in STATION_VARIANTS:
        observed = [obj for obj in objects if obj.get("c2w_station_variant") == variant]
        counts = semantic_counts(observed)
        station_audit[variant] = {
            "objects": len(observed),
            "renderables": sum(
                obj.type in {"MESH", "CURVE", "FONT"} for obj in observed
            ),
            "semantic_counts": counts,
        }
    all_counts = semantic_counts(objects)
    roots = [obj for obj in objects if obj.get("c2w_role") == "procedural_asset_root"]
    truck_roots = [
        obj for obj in roots if obj.get("c2w_asset_category") == "fire_truck"
    ]
    ambulance_roots = [
        obj for obj in roots if obj.get("c2w_asset_category") == "ambulance"
    ]
    station_roots = [
        obj for obj in roots if obj.get("c2w_asset_category") == "fire_station"
    ]
    apparatus_roots = ambulance_roots + truck_roots
    truck_root_by_variant = {obj.get("c2w_variant"): obj for obj in apparatus_roots}
    placed_scale = {
        variant: float(truck_root_by_variant[variant].get("c2w_scene_scale", 1.0))
        for variant in AMBULANCE_VARIANTS + TRUCK_VARIANTS
        if variant in truck_root_by_variant
    }
    door_alignment = {
        variant: str(truck_root_by_variant[variant].get("c2w_door_alignment", ""))
        for variant in AMBULANCE_VARIANTS + TRUCK_VARIANTS
        if variant in truck_root_by_variant
    }
    identity_signs = [
        obj
        for obj in objects
        if obj.type == "FONT" and obj.get("c2w_semantic") == "station_identity_sign"
    ]
    identity_sign_sizes = sorted(
        round(float(obj.data.size), 3) for obj in identity_signs
    )
    complex_materials = [
        mat
        for mat in bpy.data.materials
        if mat.use_nodes and mat.node_tree and len(mat.node_tree.nodes) >= 7
    ]
    banned_tokens = (
        "placeholder",
        "proxy",
        "dummy",
        "toy",
        "lowpoly",
        "low_poly",
        "primitive_only",
    )
    banned = [
        obj.name
        for obj in renderables
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    vegetation_name_tokens = (
        "boundary_tree",
        "shrub",
        "planting_bed",
        "landscape_bed",
        "planter",
        "flower_bed",
    )
    vegetation_semantic_tokens = ("botanical_", "shrub_", "landscape_bed", "tree_")
    vegetation_material_tokens = (
        "living_turf",
        "broadleaf",
        "tree_bark",
        "planting_soil",
    )
    vegetation_objects = []
    for obj in renderables:
        semantic = str(obj.get("c2w_semantic", "")).lower()
        material_names = [
            slot.material.name.lower()
            for slot in getattr(obj, "material_slots", ())
            if slot.material
        ]
        if (
            any(token in obj.name.lower() for token in vegetation_name_tokens)
            or any(token in semantic for token in vegetation_semantic_tokens)
            or any(
                any(token in material_name for token in vegetation_material_tokens)
                for material_name in material_names
            )
        ):
            vegetation_objects.append(obj.name)
    adapter_available = False
    try:
        ua = importlib.import_module("urban_assets")
        adapter_available = (
            callable(getattr(ua, "build_fire_station_region", None))
            and callable(getattr(ua, "build_fire_station_asset", None))
            and callable(getattr(ua, "build_fire_truck_asset", None))
            and callable(getattr(ua, "build_ambulance_asset", None))
            and tuple(getattr(ua, "FIRE_TRUCK_VARIANTS", ())) == TRUCK_VARIANTS
            and tuple(getattr(ua, "FIRE_AMBULANCE_VARIANTS", ())) == AMBULANCE_VARIANTS
            and tuple(getattr(ua, "FIRE_STATION_VARIANTS", ())) == STATION_VARIANTS
        )
    except Exception:
        adapter_available = False
    modern = truck_audit["modern_ladder_engine"]["semantic_counts"]
    classic = truck_audit["classic_pumper"]["semantic_counts"]
    rescue = truck_audit["rapid_rescue"]["semantic_counts"]
    ambulance = ambulance_audit["type_i_ambulance"]["semantic_counts"]
    civic = station_audit["civic_headquarters"]["semantic_counts"]
    annex = station_audit["industrial_annex"]["semantic_counts"]
    view_records = [
        {
            "file": filename,
            "role": role,
            "bytes": (RENDERS / filename).stat().st_size
            if (RENDERS / filename).is_file()
            else 0,
        }
        for filename, _, _, _, role in camera_specs()
    ]
    closed_curtains = [
        obj
        for obj in objects
        if obj.get("c2w_semantic") == "closed_rolling_shutter_curtain"
    ]
    open_tails = [
        obj for obj in objects if obj.get("c2w_semantic") == "open_rolling_shutter_tail"
    ]
    photo_records = [
        item
        for item in reference_records
        if item.get("kind") == "photographic_reference"
    ]
    mesh_records = [
        item
        for item in reference_records
        if item.get("kind") == "downloaded_mesh_reference"
    ]
    fire_mesh_records = [
        item for item in mesh_records if item.get("asset_category") == "fire_truck"
    ]
    mesh_preview_records = [
        item
        for item in reference_records
        if item.get("kind") == "mesh_preview_reference"
    ]
    reverse_records = [
        item
        for item in reference_records
        if item.get("kind") == "reverse_engineering_record"
    ]
    reverse_analysis = analyze_ambulance_reference()
    fire_reverse_analysis = analyze_fire_truck_reference()
    apparatus_audits = list(truck_audit.values()) + list(ambulance_audit.values())
    running_gear_expectations = {
        "type_i_ambulance": 2 * len(AMBULANCE_SPEC.wheelbase),
        **{
            variant: 2 * len(TRUCK_SPECS[variant].wheelbase)
            for variant in TRUCK_VARIANTS
        },
    }
    running_gear_audits = {
        **{variant: ambulance_audit[variant] for variant in AMBULANCE_VARIANTS},
        **{variant: truck_audit[variant] for variant in TRUCK_VARIANTS},
    }
    checks = {
        "three_independent_fire_truck_archetypes": len(trucks) == 3
        and {c.get("c2w_variant") for c in trucks} == set(TRUCK_VARIANTS),
        "one_reverse_engineered_type_i_ambulance": len(ambulances) == 1
        and {c.get("c2w_variant") for c in ambulances} == set(AMBULANCE_VARIANTS),
        "two_independent_station_architectures": len(stations) == 2
        and {c.get("c2w_variant") for c in stations} == set(STATION_VARIANTS),
        "all_response_vehicles_built_before_stations_in_scene_graph": [
            c.get("c2w_role") for c in list(root.children)[:4]
        ]
        == [
            "ambulance_asset",
            "fire_truck_asset",
            "fire_truck_asset",
            "fire_truck_asset",
        ],
        "all_apparatus_have_manufactured_running_gear": all(
            running_gear_audits[variant]["semantic_counts"].get("apparatus_tire", 0)
            == wheel_count
            and running_gear_audits[variant]["semantic_counts"].get(
                "tire_tread_block", 0
            )
            >= wheel_count * 60
            and running_gear_audits[variant]["semantic_counts"].get(
                "tire_circumferential_groove", 0
            )
            == wheel_count * 3
            and running_gear_audits[variant]["semantic_counts"].get(
                "tire_sidewall_marking", 0
            )
            == wheel_count
            and running_gear_audits[variant]["semantic_counts"].get("wheel_lug", 0)
            >= wheel_count * 8
            and running_gear_audits[variant]["semantic_counts"].get(
                "wheel_ventilation_aperture", 0
            )
            >= wheel_count * 10
            and running_gear_audits[variant]["semantic_counts"].get("brake_caliper", 0)
            >= wheel_count
            and running_gear_audits[variant]["semantic_counts"].get(
                "leaf_spring_pack", 0
            )
            >= wheel_count * 4
            for variant, wheel_count in running_gear_expectations.items()
        ),
        "ambulance_uses_continuous_lofts_and_manufacturer_dimensions": (
            ambulance.get("ambulance_formed_hood", 0) == 1
            and ambulance.get("ambulance_cab_lower_body", 0) == 1
            and ambulance.get("ambulance_cab_a_pillar_structure", 0) == 2
            and ambulance.get("ambulance_cab_b_pillar_structure", 0) == 2
            and ambulance.get("ambulance_cab_windshield_header", 0) == 1
            and ambulance.get("ambulance_welded_module_shell", 0) == 1
            and reverse_analysis["manufacturer_constraint"]["overall_dimensions_m"]
            == [7.403, 2.413, 2.946]
            and reverse_analysis["manufacturer_constraint"]["wheelbase_m"] == 4.293
        ),
        "ambulance_has_complete_cab_glazing_controls_and_road_equipment": (
            ambulance.get("ambulance_cab_windshield", 0) == 1
            and ambulance.get("ambulance_wiper_arm", 0) == 2
            and ambulance.get("ambulance_cab_side_window", 0) == 2
            and ambulance.get("firefighter_seat", 0) == 2
            and ambulance.get("steering_wheel", 0) == 1
            and ambulance.get("ambulance_side_mirror", 0) == 2
            and ambulance.get("ambulance_headlamp_optic", 0) == 4
        ),
        "ambulance_module_has_real_access_hardware_lighting_and_medical_fitout": (
            ambulance.get("ambulance_equipment_compartment_door", 0) == 5
            and ambulance.get("ambulance_patient_entry_door", 0) == 1
            and ambulance.get("ambulance_rotary_paddle_latch", 0) == 6
            and ambulance.get("ambulance_door_hinge", 0) == 12
            and ambulance.get("ambulance_warning_light_optic", 0) >= 24
            and ambulance.get("ambulance_rear_patient_door", 0) == 2
            and ambulance.get("ambulance_medical_cabinet", 0) == 4
            and ambulance.get("ambulance_stretcher_mattress", 0) == 1
        ),
        "downloaded_meshes_were_reverse_engineered_not_rendered": (
            len(mesh_records)
            == len(AMBULANCE_REFERENCE_FILES) + len(FIRE_TRUCK_REFERENCE_FILES)
            and len(fire_mesh_records) == len(FIRE_TRUCK_REFERENCE_FILES)
            and len(mesh_preview_records) == len(FIRE_TRUCK_PREVIEW_FILES)
            and len(reverse_records) == 2
            and reverse_analysis["source"]["obj_vertex_count"] == 1739
            and reverse_analysis["source"]["wheelbase_to_length_ratio"] > 0.58
            and fire_reverse_analysis["source"]["obj_vertex_count"] == 71494
            and fire_reverse_analysis["source"]["obj_face_count"] == 69342
            and fire_reverse_analysis["source"]["obj_group_count"] >= 425
            and len(fire_reverse_analysis["source"]["landmarks"]["wheel_groups"]) == 6
            and fire_reverse_analysis["render_policy"]["downloaded_mesh_faces_rendered"]
            == 0
            and root.get("c2w_reference_mesh_inputs") == 2
            and root.get("c2w_render_mesh_inputs") == 0
        ),
        "modern_engine_is_detailed_mesh_calibrated_programmatic_rebuild": (
            modern.get("reference_calibrated_body_shell", 0) == 1
            and modern.get("apparatus_tire", 0) == 6
            and modern.get("live_axle", 0) == 3
            and modern.get("rollup_compartment_door", 0) == 7
            and modern.get("pump_pressure_gauge", 0) == 8
            and modern.get("roof_guard_post", 0) == 12
            and modern.get("roof_guard_rail", 0) == 4
            and modern.get("rear_access_ladder_rung", 0) == 7
            and fire_reverse_analysis["derived_programmatic_parameters"][
                "wheel_centers_y_m"
            ]
            == [-2.4969, 1.334, 2.6657]
        ),
        "modern_engine_has_source_measured_roof_ladder_system": modern.get(
            "portable_ladder_rung", 0
        )
        >= 34
        and modern.get("ladder_rail_aperture", 0) >= 30
        and modern.get("ladder_rack_saddle", 0) == 4
        and modern.get("ladder_safety_cable", 0) == 1,
        "classic_pumper_has_complete_midship_controls": classic.get(
            "pump_pressure_gauge", 0
        )
        == 8
        and classic.get("hose_coupling", 0) == 6
        and classic.get("grille_aperture", 0) >= 80,
        "rapid_rescue_is_distinct_hooded_locker_body": rescue.get("rescue_hood", 0) == 1
        and rescue.get("rollup_compartment_door", 0) == 8
        and rescue.get("rollup_door_slat", 0) >= 80
        and rescue.get("cab_windshield", 0) == 2
        and rescue.get("windshield_wiper_arm", 0) == 2,
        "vehicle_cabs_have_glazing_interior_and_controls": all(
            audit["semantic_counts"].get("cab_windshield", 0) >= 1
            and audit["semantic_counts"].get("firefighter_seat", 0) >= 2
            and audit["semantic_counts"].get("steering_wheel", 0) == 1
            and audit["semantic_counts"].get("emergency_light_optic", 0) >= 8
            for audit in truck_audit.values()
        ),
        "cab_over_engines_have_tapered_glazing_and_articulated_wipers": all(
            truck_audit[variant]["semantic_counts"].get("cab_windshield", 0) == 2
            and truck_audit[variant]["semantic_counts"].get("windshield_wiper_arm", 0)
            == 2
            and truck_audit[variant]["semantic_counts"].get("windshield_wiper_pivot", 0)
            == 2
            and truck_audit[variant]["semantic_counts"].get(
                "windshield_defroster_vent", 0
            )
            == 4
            for variant in ("modern_ladder_engine", "classic_pumper")
        ),
        "engines_have_working_roof_apparatus_facilities": all(
            truck_audit[variant]["semantic_counts"].get("roof_deck_monitor_base", 0)
            == 1
            and truck_audit[variant]["semantic_counts"].get("roof_hard_suction_tube", 0)
            == 2
            and truck_audit[variant]["semantic_counts"].get("apparatus_roof_walkway", 0)
            == 1
            and truck_audit[variant]["semantic_counts"].get(
                "roof_equipment_mount_saddle", 0
            )
            >= 8
            for variant in ("modern_ladder_engine", "classic_pumper")
        ),
        "all_apparatus_have_connected_wheelhouses_and_body_mounts": all(
            truck_audit[variant]["semantic_counts"].get("wheel_arch_fender_panel", 0)
            == 2 * len(TRUCK_SPECS[variant].wheelbase)
            and truck_audit[variant]["semantic_counts"].get("wheelhouse_inner_liner", 0)
            == 2 * len(TRUCK_SPECS[variant].wheelbase)
            and truck_audit[variant]["semantic_counts"].get(
                "wheel_arch_support_apron", 0
            )
            == 4 * len(TRUCK_SPECS[variant].wheelbase)
            and truck_audit[variant]["semantic_counts"].get("body_mount_outrigger", 0)
            == 6
            and truck_audit[variant]["semantic_counts"].get("body_mount_isolator", 0)
            == 6
            and truck_audit[variant]["semantic_counts"].get("step_mount_bracket", 0)
            >= 10
            for variant in TRUCK_VARIANTS
        ),
        "modern_engine_exterior_fittings_have_real_load_paths": (
            modern.get("front_fascia_carrier", 0) == 1
            and modern.get("front_fascia_transition", 0) == 1
            and modern.get("bumper_mount_bracket", 0) == 2
            and modern.get("bumper_mount_plate", 0) == 2
            and modern.get("mirror_mount_base", 0) == 2
            and modern.get("mirror_mount_fastener", 0) == 4
            and modern.get("cab_body_flexible_joint", 0) == 2
            and modern.get("cab_body_transition_plate", 0) == 2
        ),
        "rapid_rescue_front_clip_lockers_and_bumpers_are_structurally_connected": (
            rescue.get("front_fascia_carrier", 0) == 1
            and rescue.get("front_fascia_transition", 0) == 1
            and rescue.get("bumper_mount_bracket", 0) == 4
            and rescue.get("bumper_mount_plate", 0) == 2
            and rescue.get("hood_cab_transition_cowl", 0) == 1
            and rescue.get("front_fender_inner_apron", 0) == 2
            and rescue.get("cab_a_pillar_structure", 0) == 2
            and rescue.get("apparatus_body_front_bulkhead", 0) == 1
            and rescue.get("cab_body_flexible_joint", 0) == 2
            and rescue.get("mirror_mount_base", 0) == 2
        ),
        "apparatus_size_orientation_and_threshold_alignment_are_explicit": (
            set(placed_scale) == set(AMBULANCE_VARIANTS + TRUCK_VARIANTS)
            and abs(placed_scale["modern_ladder_engine"] - 1.30) < 1e-6
            and all(
                abs(float(root_obj.rotation_euler.z)) < 1e-6
                for root_obj in apparatus_roots
            )
            and all("threshold" in value for value in door_alignment.values())
        ),
        "civic_headquarters_has_four_operational_bays": civic.get(
            "apparatus_bay_floor", 0
        )
        == 4
        and civic.get("apparatus_bay_frame", 0) == 8
        and civic.get("apparatus_bay_header", 0) == 4
        and civic.get("brick_bay_pier", 0) == 5,
        "industrial_annex_matches_reference03_four_operational_openings": annex.get(
            "apparatus_bay_floor", 0
        )
        == 4
        and annex.get("apparatus_bay_frame", 0) == 8
        and annex.get("apparatus_bay_header", 0) == 4,
        "all_empty_bays_are_closed_and_occupied_bays_are_open": (
            len(closed_curtains) == 4
            and len(open_tails) == 4
            and all(
                obj.get("c2w_bay_occupancy") == "empty"
                and obj.get("c2w_door_state") == "closed"
                for obj in closed_curtains
            )
            and all(
                obj.get("c2w_bay_occupancy") == "apparatus"
                and obj.get("c2w_door_state") == "open"
                for obj in open_tails
            )
        ),
        "bay_doors_are_detailed_opaque_coiling_shutters_not_glass": (
            all_counts.get("bay_door_glazed_panel", 0) == 0
            and all_counts.get("rolling_shutter_slat", 0) >= 310
            and all_counts.get("rolling_shutter_interlock", 0) >= 310
            and all_counts.get("rolling_shutter_endlock", 0) >= 190
            and all_counts.get("rolling_shutter_coil", 0) == 12
            and all_counts.get("rolling_shutter_coil_hood", 0) == 8
            and all_counts.get("rolling_shutter_guide_channel", 0) == 16
            and all_counts.get("rolling_shutter_formed_guide_lip", 0) == 32
            and all_counts.get("rolling_shutter_bottom_weather_seal", 0) == 4
            and all_counts.get("overhead_door_control_station", 0) == 8
            and all_counts.get("overhead_door_control_button", 0) == 24
            and all_counts.get("overhead_door_electrical_conduit", 0) == 8
            and all_counts.get("rolling_shutter_service_weathering", 0) == 36
        ),
        "industrial_annex_has_reference03_gable_office_canopy_and_red_tower": annex.get(
            "metal_cladding_rib", 0
        )
        >= 84
        and annex.get("reference_stair_tower", 0) == 1
        and annex.get("reference_red_tower_crown", 0) == 1
        and annex.get("canopy_tension_rod", 0) == 2
        and annex.get("station_sign_mounting_rail", 0) == 4,
        "apparatus_bays_have_real_operational_interiors": all_counts.get(
            "bay_roof_truss", 0
        )
        >= 40
        and all_counts.get("floor_drain_grate", 0) >= 192
        and all_counts.get("turnout_gear_locker", 0) >= 40
        and all_counts.get("vehicle_exhaust_extraction_hose", 0) == 8,
        "station_envelopes_have_roof_and_water_services": all_counts.get(
            "roof_hvac_unit", 0
        )
        >= 4
        and all_counts.get("rainwater_downpipe", 0) >= 8
        and all_counts.get("standing_seam_rib", 0) >= 60,
        "modeled_fire_service_site_systems": all_counts.get("fire_hydrant_barrel", 0)
        == 2
        and all_counts.get("stormwater_grate", 0) >= 80
        and all_counts.get("site_light_pole", 0) == 4
        and all_counts.get("emergency_generator_enclosure", 0) == 1,
        "distant_urban_context_is_constructed_not_empty_backdrop": all_counts.get(
            "distant_urban_building_shell", 0
        )
        == 4
        and all_counts.get("distant_roof_parapet", 0) == 16
        and all_counts.get("distant_service_door", 0) == 8
        and all_counts.get("distant_service_door_slat", 0) >= 88,
        "zero_trees_shrubs_planters_and_flower_beds": not vegetation_objects
        and all_counts.get("vegetation_free_service_plaza", 0) == 4,
        "architecture_has_constructed_envelope_details": all_counts.get(
            "roof_metal_coping", 0
        )
        >= 1
        and all_counts.get("precast_panel_reveal", 0) >= 8
        and all_counts.get("overhead_door_photoeye", 0) == 16
        and all_counts.get("overhead_door_operator_motor", 0) == 8,
        "facades_have_physical_masonry_relief_and_service_hardware": all_counts.get(
            "brick_relief_masonry", 0
        )
        >= 3
        and all_counts.get("brick_pier_relief_masonry", 0) == 5
        and all_counts.get("precast_block_relief", 0) >= 3
        and all_counts.get("split_face_stone_relief", 0) >= 5
        and all_counts.get("fire_department_connection_inlet", 0) == 4,
        "identity_signs_are_large_legible_and_building_bounded": len(identity_signs)
        == 2
        and identity_sign_sizes[0] >= 1.0
        and identity_sign_sizes[1] >= 1.4
        and all_counts.get("station_sign_mounting_bolt", 0) >= 48,
        "aerial_rooflines_have_real_service_detail": all_counts.get(
            "roof_access_hatch", 0
        )
        >= 3
        and all_counts.get("roof_vent_stack", 0) >= 9
        and all_counts.get("roof_scupper", 0) >= 4,
        "apparatus_has_full_scale_fabrication_details": all_counts.get(
            "compartment_frame_fastener", 0
        )
        >= 150
        and all_counts.get("apparatus_body_fastener", 0) >= 70
        and all_counts.get("ambulance_body_fastener", 0) >= 32
        and all_counts.get("running_board_grip_aperture", 0) >= 60
        and all_counts.get("body_mount_outrigger", 0) == 24
        and all_counts.get("wheel_arch_fender_panel", 0) == 18,
        "reference_images_and_mesh_evidence_archived_in_workspace": len(photo_records)
        == 5
        and min(item["bytes"] for item in photo_records) > 10000
        and len(mesh_records) == 10
        and len(mesh_preview_records) == 3
        and len(reverse_records) == 2,
        "dense_production_geometry": len(renderables) >= 3900
        and min(audit["renderables"] for audit in truck_audit.values()) >= 300
        and ambulance_audit["type_i_ambulance"]["renderables"] >= 500
        and min(audit["renderables"] for audit in station_audit.values()) >= 600,
        "multi_scale_procedural_pbr_material_system": len(bpy.data.materials) >= 40
        and len(complex_materials) >= 18,
        "ten_daylight_near_far_vehicle_door_and_interior_views": len(cameras) == 10
        and {record["role"] for record in view_records}
        >= {"far", "aerial", "near", "apparatus_close", "door_detail", "interior"},
        "active_urban_pipeline_adapter_is_callable": adapter_available
        and root.get("c2w_pipeline_adapter")
        == "urban_assets.build_fire_station_region",
        "source_generator_is_pipeline_entrypoint": root.get("c2w_pipeline_entrypoint")
        == "generate_urban_v3_fire.build_fire_station_region",
        "no_external_blend_or_downloaded_render_mesh_dependency": root.get(
            "c2w_scene_asset_inputs"
        )
        == 0
        and root.get("c2w_render_mesh_inputs") == 0,
        "all_renderable_geometry_is_source_tagged": all(
            obj.get("c2w_generator") == Path(__file__).name
            and obj.get("c2w_source_geometry") == "procedural"
            for obj in renderables
        ),
        "no_placeholder_or_degraded_asset_names": not banned,
        "six_assets_have_independent_pose_roots": len(ambulance_roots) == 1
        and len(truck_roots) == 3
        and len(station_roots) == 2,
    }
    diagnostics = {}
    if rendered:
        diagnostics = render_diagnostics()
        checks["all_ten_full_resolution_renders_are_nonblank"] = len(
            diagnostics
        ) == 10 and all(item["passed"] for item in diagnostics.values())
    result = {
        "schema": "agent.urban_fire_region_manifest.v6",
        "generator": str(Path(__file__).resolve()),
        "runner": str((ROOT / "scripts/run_urban_v3_fire.sh").resolve()),
        "output": str(OUT),
        "blend": str(BLEND),
        "pipeline_asset_id": ASSET_ID,
        "pipeline_connected": True,
        "pipeline_entrypoint": "generate_urban_v3_fire.build_fire_station_region",
        "pipeline_adapter": "urban_assets.build_fire_station_region",
        "truck_entrypoint": "generate_urban_v3_fire.build_fire_truck_asset",
        "truck_adapter": "urban_assets.build_fire_truck_asset",
        "ambulance_entrypoint": "generate_urban_v3_fire.build_ambulance_asset",
        "ambulance_adapter": "urban_assets.build_ambulance_asset",
        "station_entrypoint": "generate_urban_v3_fire.build_fire_station_asset",
        "station_adapter": "urban_assets.build_fire_station_asset",
        "rebuild_command": "bash scripts/run_urban_v3_fire.sh",
        "reference_urls": REFERENCE_URLS
        + [
            AMBULANCE_PHOTO_URL,
            AMBULANCE_MESH_PAGE,
            AMBULANCE_DIMENSION_URL,
            FIRE_TRUCK_MESH_PAGE,
        ],
        "reference_files": reference_records,
        "ambulance_reverse_engineering": reverse_analysis,
        "fire_truck_reverse_engineering": fire_reverse_analysis,
        "reference_observations": {
            "reference_01": "white upper/red lower cab-over engines with broad raked split glazing, commercial radial wheels, segmented aluminum lockers, dual extension ladders, hard suction plumbing, blue/red beacons and black-brick/red-frame station context",
            "reference_02": "older American cream-over-red pumper with deep square grille, midship gauges, exposed couplings, side ladder and heavy chrome bumper",
            "reference_03": "gray vertical-panel gabled hall with red bay frames, four response openings, stone base, centered FIRE STATION sign and low glazed office entry",
            "reference_04": "black-brick apparatus wing with red-framed glazed bays, red operations wing, pale precast administration block and tall red station-number tower",
            "ambulance_mesh": "CC0 grouped GLB/OBJ used only to recover body, wheel, wheelbase and rear-door landmarks; never imported into render geometry",
            "ambulance_photo": "F450 Type-I front three-quarter photograph used to refine one-piece windscreen, black front wheel arch, tall lamp stack, grille guard and cab-module boot",
            "ambulance_manufacturer_dimensions": "Demers MXP 150 Type I Ford F450 dimensions constrain 7.403 m overall length, 2.413 m width, 2.946 m height and 4.293 m wheelbase",
            "fire_truck_mesh": "CadNav model #49268 supplies 71,494 vertices, 69,342 faces and 425 measured groups; six detailed wheel groups recover a three-axle 6x4 layout while glass, cab, equipment-body and paired 4.33 m roof-ladder groups drive the programmable rebuild",
            "fire_truck_render_policy": "the downloaded RAR/OBJ/MTL are hashed local measurement evidence only; zero source faces are imported or rendered",
            "vegetation_policy": "operational hardscape only; no modeled trees, shrubs, planters or flower beds",
        },
        "requested_revision_verification": {
            "ambulance_rebuild": "downloaded CC0 mesh archived and hashed; OBJ group landmarks extracted in code; uniform source scaling rejected; full-size Type-I ambulance rebuilt from longitudinal lofts, manufacturer dimensions, dual-wheel chassis, working access hardware, warning optics and medical fitout",
            "fire_truck_rebuild": "downloaded 71,494-vertex / 69,342-face detailed fire-engine mesh archived and hashed; OBJ face groups, materials and bounds are parsed in generator source; three axle stations, 1.2005 m wheels, cab glazing, body envelope and paired roof ladders drive a wholly programmable 6x4 heavy-pumper reconstruction",
            "station_vehicle_proportion": "the reverse-engineered heavy pumper retains native 1:1 programmable dimensions, then its independent scene pose root is calibrated to 1.30 for the inherited oversized 8.96 x 6.42 m bay module; local negative-Y faces outward and the shifted rear step remains aligned to the threshold",
            "empty_bay_door_policy": "civic bays 3-4 and annex bays 1-2 are closed because empty; the four occupied bays are open",
            "rolling_shutter_realism": "all eight openings use opaque serviceable coiling shutters; closed empty bays carry 85 mm convex double-wall slats with hooked interlocks, endlocks, C-guide lips, brush seals, subtle batch variation/weathering, geared barrel operator, limit box, control buttons, key release, conduit, bottom bar and astragal",
            "building_signage": "two bounded fabricated sign cabinets with font sizes 1.06 m and 1.42 m, dark keylines, perimeter trim, bolts, mounting rails and dedicated luminaires",
            "facade_realism": "reference_03 four-opening gabled hall with slope-terminated vertical ribs, red bay frames, split-face plinths, selectively exposed operational interiors, glazed office, engineered lean-to canopy and connected red tower",
            "presentation": "ten full-resolution daylight views spanning full precinct, opposing aerials, both station near views, ambulance and apparatus close views, shutter detail and operational interior",
        },
        "truck_variants": list(TRUCK_VARIANTS),
        "ambulance_variants": list(AMBULANCE_VARIANTS),
        "station_variants": list(STATION_VARIANTS),
        "truck_audit": truck_audit,
        "ambulance_audit": ambulance_audit,
        "station_audit": station_audit,
        "semantic_counts": all_counts,
        "object_count": len(objects),
        "renderable_count": len(renderables),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "apparatus_scene_scale": placed_scale,
        "apparatus_door_alignment": door_alignment,
        "identity_sign_font_sizes": identity_sign_sizes,
        "render_views": view_records,
        "render_diagnostics": diagnostics,
        "render_settings": {
            "engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": int(getattr(scene.eevee, "taa_render_samples", 8)),
            "color_management": scene.view_settings.look,
        },
        "daylight": True,
        "near_and_far_views": True,
        "external_blend_inputs": 0,
        "downloaded_reference_mesh_inputs": 2,
        "downloaded_meshes_used_as_render_geometry": 0,
        "banned_geometry_names": banned,
        "vegetation_geometry_names": vegetation_objects,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not result["all_checks_passed"]:
        failed = [name for name, value in checks.items() if not value]
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(
                {"failed": failed, "audit": result}, indent=2, ensure_ascii=False
            ),
            encoding="utf8",
        )
        raise RuntimeError("Fire-region production audit failed: " + ", ".join(failed))
    return result


def validate_v7(root, cameras, reference_records, rendered=False):
    """Audit the fire7 scene against the requested apparatus/door revision."""
    scene = bpy.context.scene
    objects = list(scene.objects)
    renderables = [
        obj
        for obj in objects
        if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
    ]
    truck_collections = [
        coll for coll in root.children if coll.get("c2w_role") == "fire_truck_asset"
    ]
    station_collections = [
        coll for coll in root.children if coll.get("c2w_role") == "fire_station_asset"
    ]
    ambulance_collections = [
        coll for coll in root.children if coll.get("c2w_role") == "ambulance_asset"
    ]
    truck_roots = [
        obj
        for obj in objects
        if obj.get("c2w_role") == "procedural_asset_root"
        and obj.get("c2w_asset_category") == "fire_truck"
    ]
    station_roots = [
        obj
        for obj in objects
        if obj.get("c2w_role") == "procedural_asset_root"
        and obj.get("c2w_asset_category") == "fire_station"
    ]
    ambulance_objects = [
        obj for obj in objects if obj.get("c2w_asset_category") == "ambulance"
    ]
    truck_instance_counts = {
        variant: sum(coll.get("c2w_variant") == variant for coll in truck_collections)
        for variant in TRUCK_VARIANTS
    }
    truck_audit = {}
    for variant in TRUCK_VARIANTS:
        observed = [obj for obj in objects if obj.get("c2w_truck_variant") == variant]
        truck_audit[variant] = {
            "instances": truck_instance_counts[variant],
            "objects": len(observed),
            "renderables": sum(
                obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
                for obj in observed
            ),
            "semantic_counts": semantic_counts(observed),
        }
    station_audit = {}
    for variant in STATION_VARIANTS:
        observed = [obj for obj in objects if obj.get("c2w_station_variant") == variant]
        station_audit[variant] = {
            "objects": len(observed),
            "renderables": sum(
                obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_render
                for obj in observed
            ),
            "semantic_counts": semantic_counts(observed),
        }
    all_counts = semantic_counts(objects)
    modern = truck_audit["modern_ladder_engine"]["semantic_counts"]
    pumper = truck_audit["classic_pumper"]["semantic_counts"]
    compact = truck_audit["rapid_rescue"]["semantic_counts"]
    civic = station_audit["civic_headquarters"]["semantic_counts"]
    annex = station_audit["industrial_annex"]["semantic_counts"]
    suite = analyze_fire_truck_reference_suite()

    photo_records = [
        r for r in reference_records if r.get("kind") == "photographic_reference"
    ]
    mesh_records = [
        r for r in reference_records if r.get("kind") == "downloaded_mesh_reference"
    ]
    preview_records = [
        r for r in reference_records if r.get("kind") == "mesh_preview_reference"
    ]
    reverse_records = [
        r for r in reference_records if r.get("kind") == "reverse_engineering_record"
    ]
    extracted_model_records = [
        r
        for r in mesh_records
        if r.get("purpose") == "extracted_high_detail_mesh"
        or str(r.get("file", "")).endswith("Firefighting.obj")
    ]
    closed_curtains = [
        obj
        for obj in objects
        if obj.get("c2w_semantic") == "closed_rolling_shutter_curtain"
    ]
    open_tails = [
        obj for obj in objects if obj.get("c2w_semantic") == "open_rolling_shutter_tail"
    ]
    identity_signs = [
        obj
        for obj in objects
        if obj.type == "FONT" and obj.get("c2w_semantic") == "station_identity_sign"
    ]
    complex_materials = [
        material
        for material in bpy.data.materials
        if material.use_nodes
        and material.node_tree
        and len(material.node_tree.nodes) >= 7
    ]
    banned_tokens = (
        "placeholder",
        "proxy",
        "dummy",
        "toy",
        "lowpoly",
        "low_poly",
        "primitive_only",
        "ambulance",
    )
    banned = [
        obj.name
        for obj in renderables
        if any(token in obj.name.lower() for token in banned_tokens)
    ]
    vegetation_name_tokens = (
        "boundary_tree",
        "shrub",
        "planting_bed",
        "landscape_bed",
        "planter",
        "flower_bed",
    )
    vegetation_objects = [
        obj.name
        for obj in renderables
        if any(token in obj.name.lower() for token in vegetation_name_tokens)
        or any(
            token in str(obj.get("c2w_semantic", "")).lower()
            for token in ("botanical_", "shrub_", "landscape_bed", "tree_")
        )
    ]
    view_records = [
        {
            "file": filename,
            "role": role,
            "bytes": (RENDERS / filename).stat().st_size
            if (RENDERS / filename).is_file()
            else 0,
        }
        for filename, _, _, _, role in camera_specs()
    ]
    pose_records = [
        {
            "variant": root_obj.get("c2w_variant"),
            "scale": float(root_obj.get("c2w_scene_scale", 1.0)),
            "yaw_radians": float(root_obj.rotation_euler.z),
            "alignment": str(root_obj.get("c2w_door_alignment", "")),
            "location": [round(float(value), 4) for value in root_obj.location],
        }
        for root_obj in truck_roots
    ]
    adapter_available = False
    try:
        ua = importlib.import_module("urban_assets")
        adapter_available = (
            callable(getattr(ua, "build_fire_station_region", None))
            and callable(getattr(ua, "build_fire_station_asset", None))
            and callable(getattr(ua, "build_fire_truck_asset", None))
            and tuple(getattr(ua, "FIRE_TRUCK_VARIANTS", ())) == TRUCK_VARIANTS
            and tuple(getattr(ua, "FIRE_STATION_VARIANTS", ())) == STATION_VARIANTS
        )
    except Exception:
        adapter_available = False

    instance_multiplier = {
        "modern_ladder_engine": 1,
        "classic_pumper": 2,
        "rapid_rescue": 1,
    }
    running_gear_ok = True
    cab_ok = True
    for variant, multiplier in instance_multiplier.items():
        counts = truck_audit[variant]["semantic_counts"]
        wheel_count = 2 * len(TRUCK_SPECS[variant].wheelbase) * multiplier
        running_gear_ok = running_gear_ok and (
            counts.get("apparatus_tire", 0) == wheel_count
            and counts.get("tire_tread_block", 0) >= wheel_count * 70
            and counts.get("tire_circumferential_groove", 0) == wheel_count * 3
            and counts.get("wheel_lug", 0) == wheel_count * 8
            and counts.get("wheel_ventilation_aperture", 0) == wheel_count * 10
            and counts.get("brake_caliper", 0) == wheel_count
            and counts.get("wheel_arch_fender_panel", 0) == wheel_count
            and counts.get("wheelhouse_inner_liner", 0) == wheel_count
        )
        cab_ok = cab_ok and (
            counts.get("reference_cab_continuous_shell", 0) == multiplier
            and counts.get("cab_windshield", 0) == 2 * multiplier
            and counts.get("cab_side_window", 0) == 4 * multiplier
            and counts.get("side_window_reveal", 0) == 4 * multiplier
            and counts.get("windshield_wiper_arm", 0) == 2 * multiplier
            and counts.get("firefighter_seat", 0) == 4 * multiplier
            and counts.get("steering_wheel", 0) == multiplier
            and counts.get("emergency_light_optic", 0) >= 8 * multiplier
        )

    checks = {
        "four_fire_engines_three_detailed_types": (
            len(truck_collections) == 4
            and truck_instance_counts == instance_multiplier
            and len(truck_roots) == 4
        ),
        "no_ambulance_in_delivered_scene": (
            not ambulance_collections
            and not ambulance_objects
            and root.get("c2w_scene_ambulance_variants") == "[]"
            and all(
                coll.get("c2w_vehicle_class") == "fire_engine"
                and bool(coll.get("c2w_not_ambulance"))
                for coll in truck_collections
            )
        ),
        "four_high_detail_mesh_sources_verified": (
            suite["source_count"] == 4
            and suite["total_published_vertices"] >= 500_000
            and suite["total_published_polygons"] >= 490_000
            and len(suite["sources"]) == 3
            and all(
                record["mesh_bytes"] >= 4_000_000
                and record["published_vertices"] >= 100_000
                and len(record["embedded_material_landmarks"]) >= 4
                and not record["render_geometry"]
                for record in suite["sources"].values()
            )
            and suite["direct_obj_crosscheck"]["source"]["obj_vertex_count"] >= 70_000
        ),
        "reference_evidence_archived_in_workspace": (
            len(photo_records) == 4
            and len(mesh_records) == 10
            and len(extracted_model_records) == 4
            and len(preview_records) == 8
            and len(reverse_records) == 2
            and all(
                record.get("asset_category") == "fire_truck" for record in mesh_records
            )
            and all(
                not record.get("render_geometry", False)
                for record in mesh_records + preview_records + reverse_records
            )
        ),
        "downloaded_meshes_are_measurement_only": (
            root.get("c2w_scene_asset_inputs") == 0
            and root.get("c2w_render_mesh_inputs") == 0
            and suite["render_policy"]["downloaded_mesh_objects_imported"] == 0
            and suite["render_policy"]["downloaded_mesh_faces_rendered"] == 0
        ),
        "continuous_manufactured_cabs_with_glazing_and_interiors": cab_ok,
        "commercial_running_gear_is_fully_fabricated": running_gear_ok,
        "urban_pumpers_have_operational_equipment_bodies": (
            pumper.get("reference_calibrated_body_shell", 0) == 2
            and pumper.get("rollup_compartment_door", 0) >= 12
            and pumper.get("rollup_door_slat", 0) >= 120
            and pumper.get("pump_pressure_gauge", 0) >= 16
            and pumper.get("hose_bed_tray", 0) == 2
            and pumper.get("folded_supply_hose", 0) >= 48
            and pumper.get("portable_ladder_rail", 0) >= 4
        ),
        "heavy_aerial_has_nested_ladder_platform_and_stabilizers": (
            modern.get("reference_calibrated_aerial_body_shell", 0) == 1
            and modern.get("aerial_ladder_rail", 0) == 12
            and modern.get("aerial_ladder_rung", 0) >= 50
            and modern.get("aerial_ladder_diagonal", 0) >= 90
            and modern.get("aerial_stabilizer_beam", 0) == 4
            and modern.get("aerial_stabilizer_jack", 0) == 4
            and modern.get("aerial_rescue_basket_post", 0) == 4
            and modern.get("aerial_tip_monitor_barrel", 0) == 1
        ),
        "compact_apparatus_is_a_real_aerial_fire_engine": (
            compact.get("reference_calibrated_aerial_body_shell", 0) == 1
            and compact.get("aerial_ladder_rail", 0) == 8
            and compact.get("aerial_ladder_rung", 0) >= 34
            and compact.get("aerial_ladder_diagonal", 0) >= 60
            and compact.get("aerial_stabilizer_beam", 0) == 4
            and compact.get("aerial_rescue_basket_floor", 0) == 1
            and compact.get("pump_pressure_gauge", 0) >= 8
        ),
        "apparatus_size_orientation_and_threshold_alignment": (
            len(pose_records) == 4
            and all(0.97 <= record["scale"] <= 1.03 for record in pose_records)
            and all(abs(record["yaw_radians"]) < 1e-7 for record in pose_records)
            and all("threshold" in record["alignment"] for record in pose_records)
        ),
        "two_independent_detailed_station_architectures": (
            len(station_collections) == 2
            and len(station_roots) == 2
            and {coll.get("c2w_variant") for coll in station_collections}
            == set(STATION_VARIANTS)
            and civic.get("apparatus_bay_floor", 0) == 4
            and annex.get("apparatus_bay_floor", 0) == 4
        ),
        "bay_occupancy_matches_door_state": (
            len(closed_curtains) == 4
            and len(open_tails) == 4
            and all(
                obj.get("c2w_bay_occupancy") == "empty"
                and obj.get("c2w_door_state") == "closed"
                for obj in closed_curtains
            )
            and all(
                obj.get("c2w_bay_occupancy") == "apparatus"
                and obj.get("c2w_door_state") == "open"
                for obj in open_tails
            )
        ),
        "rolling_shutters_have_real_coiling_door_construction": (
            all_counts.get("bay_door_glazed_panel", 0) == 0
            and all_counts.get("rolling_shutter_slat", 0) >= 295
            and all_counts.get("rolling_shutter_interlock", 0) >= 295
            and all_counts.get("rolling_shutter_endlock", 0) >= 190
            and all_counts.get("rolling_shutter_coil", 0) == 12
            and all_counts.get("rolling_shutter_coil_hood", 0) == 8
            and all_counts.get("rolling_shutter_guide_channel", 0) == 16
            and all_counts.get("rolling_shutter_formed_guide_lip", 0) == 32
            and all_counts.get("rolling_shutter_brush_seal", 0) == 16
            and all_counts.get("overhead_door_recessed_control_station", 0) == 8
            and all_counts.get("overhead_door_control_button", 0) == 24
        ),
        "fire6_lower_right_door_blocks_removed": (
            all_counts.get("rolling_shutter_manufacturer_plate", 0) == 0
            and all_counts.get("rolling_shutter_manufacturer_plate_engraving", 0) == 0
            and all_counts.get("rolling_shutter_slide_bolt", 0) == 0
            and all_counts.get("rolling_shutter_lift_handle", 0) == 0
            and all_counts.get("rolling_shutter_locking_bar", 0) == 0
            and all_counts.get("rolling_shutter_recessed_lift_cup", 0) == 8
            and all_counts.get("rolling_shutter_flush_lock_cylinder", 0) == 4
        ),
        "apparatus_bays_have_operational_interiors": (
            all_counts.get("bay_roof_truss", 0) >= 40
            and all_counts.get("floor_drain_grate", 0) >= 192
            and all_counts.get("turnout_gear_locker", 0) >= 40
            and all_counts.get("vehicle_exhaust_extraction_hose", 0) == 8
        ),
        "station_envelopes_and_site_are_fully_constructed": (
            all_counts.get("roof_hvac_unit", 0) >= 4
            and all_counts.get("rainwater_downpipe", 0) >= 8
            and all_counts.get("standing_seam_rib", 0) >= 60
            and all_counts.get("fire_hydrant_barrel", 0) == 2
            and all_counts.get("stormwater_grate", 0) >= 80
            and all_counts.get("site_light_pole", 0) == 4
            and all_counts.get("distant_urban_building_shell", 0) == 4
        ),
        "signage_is_legible_and_physically_mounted": (
            len(identity_signs) == 2
            and min(float(obj.data.size) for obj in identity_signs) >= 1.0
            and all_counts.get("station_sign_mounting_bolt", 0) >= 48
        ),
        "dense_geometry_and_multiscale_pbr": (
            len(renderables) >= 4_500
            and min(audit["renderables"] for audit in truck_audit.values()) >= 450
            and min(audit["renderables"] for audit in station_audit.values()) >= 600
            and len(bpy.data.materials) >= 40
            and len(complex_materials) >= 18
        ),
        "zero_vegetation_and_no_degraded_assets": (
            not vegetation_objects
            and not banned
            and all_counts.get("vegetation_free_service_plaza", 0) == 4
        ),
        "ten_daylight_near_far_detail_views": (
            len(cameras) == 10
            and {record["role"] for record in view_records}
            >= {"far", "aerial", "near", "apparatus_close", "door_detail", "interior"}
            and bool(scene.world)
        ),
        "active_generator_and_pipeline_adapter_connected": (
            adapter_available
            and root.get("c2w_pipeline_entrypoint")
            == "generate_urban_v3_fire.build_fire_station_region"
            and root.get("c2w_pipeline_adapter")
            == "urban_assets.build_fire_station_region"
            and [coll.get("c2w_role") for coll in list(root.children)[:4]]
            == ["fire_truck_asset"] * 4
        ),
        "all_render_geometry_is_source_tagged": all(
            obj.get("c2w_generator") == Path(__file__).name
            and obj.get("c2w_source_geometry") == "procedural"
            for obj in renderables
        ),
        "six_assets_have_independent_pose_roots": (
            len(truck_roots) == 4 and len(station_roots) == 2
        ),
    }
    diagnostics = {}
    if rendered:
        diagnostics = render_diagnostics()
        checks["all_ten_full_resolution_renders_are_nonblank"] = len(
            diagnostics
        ) == 10 and all(record["passed"] for record in diagnostics.values())

    result = {
        "schema": "agent.urban_fire_region_manifest.v7",
        "generator": str(Path(__file__).resolve()),
        "runner": str((ROOT / "scripts/run_urban_v3_fire.sh").resolve()),
        "output": str(OUT),
        "blend": str(BLEND),
        "pipeline_asset_id": ASSET_ID,
        "pipeline_connected": True,
        "pipeline_entrypoint": "generate_urban_v3_fire.build_fire_station_region",
        "pipeline_adapter": "urban_assets.build_fire_station_region",
        "truck_entrypoint": "generate_urban_v3_fire.build_fire_truck_asset",
        "truck_adapter": "urban_assets.build_fire_truck_asset",
        "station_entrypoint": "generate_urban_v3_fire.build_fire_station_asset",
        "station_adapter": "urban_assets.build_fire_station_asset",
        "rebuild_command": "bash scripts/run_urban_v3_fire.sh",
        "reference_urls": REFERENCE_URLS
        + [FIRE_TRUCK_MESH_PAGE]
        + [FIRE7_MESH_SOURCES[variant]["page"] for variant in TRUCK_VARIANTS],
        "reference_files": reference_records,
        "fire_truck_reverse_engineering_suite": suite,
        "reference_observations": {
            "model_29256": "123,872-vertex three-axle enclosed urban pumper: cab-over glazing, five locker fields and roof equipment establish the pumper envelope.",
            "model_28408": "205,123-vertex tandem-axle American aerial platform: crew cab, outriggers, nested truss and rescue basket establish the heavy aerial envelope.",
            "model_46403": "100,308-vertex short-wheelbase aerial fire engine: two-axle crew cab, pump equipment and compact ladder establish the smaller apparatus envelope.",
            "model_49268": "71,494-vertex directly parsed OBJ cross-checks axle stations, commercial tire diameter, cab glazing, equipment body and roof ladders.",
            "render_policy": "All downloaded meshes are hashed measurement evidence; zero source mesh objects or faces are imported or rendered.",
        },
        "requested_revision_verification": {
            "fire_truck_replacement": "All four fire6 response vehicles were removed from region composition and replaced by four source-generated fire engines spanning three detailed mesh-calibrated types; no ambulance is placed.",
            "reverse_programmatic_modeling": "The live generator converts source topology metadata, material landmarks and silhouette calibration into metric cab/body/axle/ladder parameters, then fabricates continuous shells, glazing, interiors, commercial running gear, equipment lockers, pump controls, stabilizers and nested aerial trusses.",
            "rolling_shutter_rebuild": "Four closed and four raised opaque double-wall coiling shutters use 85 mm formed slats, interlocks, endlocks, guide rebates, brush seals, barrel/hood/operator mechanics, recessed controls and scaled bottom seals.",
            "unknown_lower_right_block_removal": "The lower-right manufacturer plate, bulky slide bolts, oversized lift handle/locking bar and projecting control cuboid are absent; flush lift cups, a central lock cylinder and recessed jamb control replace them.",
            "presentation": "Ten daylight views include full-precinct far and aerial views, both station near views, three fire-apparatus close views, a shutter detail and an open-bay interior.",
        },
        "truck_variants": list(TRUCK_VARIANTS),
        "scene_truck_instances": len(truck_collections),
        "scene_ambulance_variants": [],
        "scene_ambulance_instances": 0,
        "station_variants": list(STATION_VARIANTS),
        "truck_audit": truck_audit,
        "station_audit": station_audit,
        "semantic_counts": all_counts,
        "object_count": len(objects),
        "renderable_count": len(renderables),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "complex_procedural_material_count": len(complex_materials),
        "apparatus_pose_records": pose_records,
        "render_views": view_records,
        "render_diagnostics": diagnostics,
        "render_settings": {
            "engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": int(getattr(scene.eevee, "taa_render_samples", 8)),
            "color_management": scene.view_settings.look,
        },
        "daylight": True,
        "near_and_far_views": True,
        "external_blend_inputs": 0,
        "downloaded_reference_mesh_inputs": 4,
        "downloaded_meshes_used_as_render_geometry": 0,
        "banned_geometry_names": banned,
        "vegetation_geometry_names": vegetation_objects,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not result["all_checks_passed"]:
        failed = [name for name, value in checks.items() if not value]
        (OUT / "FAILED_AUDIT.json").write_text(
            json.dumps(
                {"failed": failed, "audit": result}, indent=2, ensure_ascii=False
            ),
            encoding="utf8",
        )
        raise RuntimeError("Fire7 production audit failed: " + ", ".join(failed))
    return result


def main():
    print("[fire] starting source-driven fire-station production generator", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    REFERENCES.mkdir(parents=True, exist_ok=True)
    reference_records = archive_references()
    preview = os.environ.get("C2W_FIRE_PREVIEW", "0") == "1"
    build_only = os.environ.get("C2W_FIRE_BUILD_ONLY", "0") == "1"
    selected_view_prefixes = {
        item.strip()
        for item in os.environ.get("C2W_FIRE_VIEW_FILTER", "").split(",")
        if item.strip()
    }
    partial_render = bool(selected_view_prefixes)
    # Targeted visual QA must not invalidate an already complete production
    # delivery.  A full/build-only run clears delivery metadata; a filtered
    # preview only replaces the explicitly selected image files.
    if not partial_render:
        for stale in (
            OUT / "SUCCESS",
            OUT / "manifest.json",
            OUT / "quality_report.json",
            OUT / "build_audit.json",
            OUT / "FAILED_AUDIT.json",
        ):
            stale.unlink(missing_ok=True)
    for filename, _, _, _, _ in camera_specs():
        if not partial_render or any(
            filename.startswith(prefix) for prefix in selected_view_prefixes
        ):
            (RENDERS / filename).unlink(missing_ok=True)
    # Remove the superseded rear-only aerial from intermediate v2 previews.
    (RENDERS / "03_full_precinct_northeast_aerial.png").unlink(missing_ok=True)
    reset_scene()
    sys.path.insert(0, str(ROOT / "scripts"))
    # Validation enters through the same live adapter that production scenes call.
    ua = importlib.import_module("urban_assets")
    root = ua.build_fire_station_region(prefix=PREFIX)
    setup_daylight()
    configure_scene(preview)
    cameras = []
    for filename, location, target, lens, role in camera_specs():
        cameras.append(
            (filename, camera(filename[:-4], location, target, lens, role), role)
        )
    initial = validate_v7(root, cameras, reference_records, rendered=False)
    scene = bpy.context.scene
    scene["c2w_pipeline_generator"] = str(Path(__file__).resolve())
    scene["c2w_pipeline_runner"] = str(
        (ROOT / "scripts/run_urban_v3_fire.sh").resolve()
    )
    scene["c2w_asset_id"] = ASSET_ID
    scene["c2w_domain"] = "urban_fire_station_region"
    scene["c2w_reference_driven"] = True
    scene[
        "c2w_pipeline_entrypoint"
    ] = "generate_urban_v3_fire.build_fire_station_region"
    scene["c2w_pipeline_adapter"] = "urban_assets.build_fire_station_region"
    scene[
        "c2w_quality_profile"
    ] = "reference_grade_photoreal_complex_procedural_modeling_v7_four_detailed_mesh_calibrated_fire_engines_and_rebuilt_coiling_shutters"
    scene["c2w_fire_truck_entrypoint"] = "generate_urban_v3_fire.build_fire_truck_asset"
    scene["c2w_ambulance_entrypoint"] = "generate_urban_v3_fire.build_ambulance_asset"
    scene["c2w_reference_mesh_inputs"] = 4
    scene["c2w_render_mesh_inputs"] = 0
    scene[
        "c2w_vegetation_policy"
    ] = "zero_trees_zero_shrubs_zero_planters_zero_flower_beds"
    scene["c2w_manifest"] = json.dumps(initial, ensure_ascii=False)
    (OUT / "build_audit.json").write_text(
        json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf8"
    )
    scene.camera = cameras[0][1]
    if not partial_render:
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    if build_only:
        print(
            json.dumps(
                {
                    "status": "BUILD_ONLY_COMPLETE",
                    "output": str(OUT),
                    "objects": initial["object_count"],
                    "checks": initial["checks"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return
    render_all(cameras)
    if preview or partial_render:
        if not partial_render:
            bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
        print(
            json.dumps(
                {"status": "PREVIEW_COMPLETE", "output": str(OUT)}, ensure_ascii=False
            ),
            flush=True,
        )
        return
    final = validate_v7(root, cameras, reference_records, rendered=True)
    scene["c2w_manifest"] = json.dumps(final, ensure_ascii=False)
    scene.camera = cameras[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    (OUT / "manifest.json").write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf8"
    )
    quality = {
        "result": "PASS",
        "all_checks_passed": True,
        "checks": final["checks"],
        "truck_audit": final["truck_audit"],
        "station_audit": final["station_audit"],
        "render_diagnostics": final["render_diagnostics"],
        "note": "Quality gates require four downloaded-and-hashed detailed fire-engine mesh evidence chains totaling at least 500,000 published vertices. They contribute zero render faces: the live Urban-v3 generator must rebuild four true-scale fire engines, including two nested-truss aerial types and two urban pumpers, place no ambulance, remove every fire6 lower-right shutter block, construct eight operational formed coiling shutters, and pass ten full-resolution daylight near/far/detail views.",
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf8"
    )
    (OUT / "SUCCESS").write_text(
        f"{ASSET_ID} production generation, four detailed-mesh reverse-engineered fire engines, rebuilt coiling-shutter validation and ten daylight views complete\n",
        encoding="utf8",
    )
    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "output": str(OUT),
                "objects": final["object_count"],
                "checks": final["checks"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
