#!/usr/bin/env python3
"""Deterministic Table-2 adapter primitives for SpatialGen.

The shared indoor specifications contain semantic facts rather than the metric
oriented boxes required by SpatialGen.  This module compiles each frozen spec
into a single, method-native layout and a fixed 16-view camera path.  The
layout is deliberately independent of the generation seed: seeds control the
official text-to-image and multi-view diffusion stages, not their input.

All paths accepted by the CLI must remain below ``baselines/``.  Long-running
model execution is added as explicit stages below; the pure compilation logic
is kept dependency-free so it can be audited and unit-tested without a GPU.
"""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
import hashlib
import json
import math
import os
import platform
import signal
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
DEFAULT_SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
SPATIALGEN_ROOT = BASELINES_ROOT / "vendor/SpatialGen"
SPATIALGEN_PYTHON = BASELINES_ROOT / "envs/spatialgen/bin/python"
SPATIALGEN_ASSETS = BASELINES_ROOT / "spatialgen_assets"
SPATIALGEN_CKPT = SPATIALGEN_ASSETS / "spatialgen_ckpts"
FLUX_BASE_MODEL = SPATIALGEN_ASSETS / "flux1_dev"
FLUX_LORA = SPATIALGEN_ASSETS / "flux_wireframe_lora"
PREPARE_SCRIPT = (
    BASELINES_ROOT / "methods/spatialgen/tools/prepare_spatialgen_inputs.py"
)
REFERENCE_SCRIPT = (
    BASELINES_ROOT / "methods/spatialgen/tools/spatialgen_generate_reference.py"
)
RENDER_SCRIPT = (
    BASELINES_ROOT / "methods/spatialgen/tools/render_spatialgen_generation.py"
)
BASE_PROTOCOL = BASELINES_ROOT / "protocol/generation/protocol.yaml"
SPATIALGEN_PROTOCOL = (
    BASELINES_ROOT / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"
)
SPATIALGEN_INFERENCE = SPATIALGEN_ROOT / "src/inference_sd.py"
SPATIALGEN_UNET_LOADER = (
    SPATIALGEN_ROOT / "diffusers_spatialgen/models/unets/unet_mvmm2d_condition.py"
)
RADEGS_ROOT = SPATIALGEN_ROOT / "src/recons/Sparse-RaDeGS"
RADEGS_TRAIN = RADEGS_ROOT / "train.py"
RADEGS_LOSS = RADEGS_ROOT / "utils/loss_utils.py"
RADEGS_RENDER = RADEGS_ROOT / "render.py"
SPATIALGEN_COMMIT = "677c1168b359b00ae4a64a58783bc71048aabcdd"
RADEGS_COMMIT = "ee7b413d2089322dd140f644d597957aca257c09"
CAMERA_HEIGHT_M = 1.55
CAMERA_VIEWS = 16
CAMERA_HORIZONTAL_FOV_DEG = 70.0
CAMERA_RESOLUTION = 512


# SpatialGen's published color vocabulary.  Keep the strings byte-for-byte
# compatible with src/utils/colormaps.py; in particular, ``window `` has an
# upstream trailing space.
LABEL = {
    "armchair": "armchair",
    "bed": "bed",
    "cabinet": "cabinet",
    "ceiling_light": "chandelier",
    "chair": "seat",
    "counter": "buffet, counter, sideboard",
    "desk": "desk",
    "dresser": "chest of drawers, chest, bureau, dresser",
    "island": "kitchen island",
    "mirror": "mirror",
    "nightstand": "nightstand",
    "other": "other",
    "painting": "painting, picture",
    "plant": "plant",
    "refrigerator": "refrigerator, icebox",
    "rug": "rug",
    "screen_door": "screen door, screen",
    "sconce": "sconce",
    "shelf": "shelf",
    "shower": "shower",
    "sink": "sink",
    "sofa": "sofa",
    "stove": "stove",
    "table": "coffee table",
    "toilet": "toilet, can, commode, crapper, pot, potty, stool, throne",
    "tv": "tv",
    "tub": "tub",
    "wardrobe": "wardrobe, closet, press",
    "window": "window ",
}


@dataclass(frozen=True)
class LayoutBox:
    """A semantic oriented box in the metric, z-up room frame."""

    role: str
    semantic_class: str
    size: tuple[float, float, float]
    center: tuple[float, float, float]
    yaw_degrees: float = 0.0

    def transform(self) -> list[float]:
        angle = math.radians(self.yaw_degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        x, y, z = self.center
        return [
            cosine,
            -sine,
            0.0,
            x,
            sine,
            cosine,
            0.0,
            y,
            0.0,
            0.0,
            1.0,
            z,
            0.0,
            0.0,
            0.0,
            1.0,
        ]

    def official_payload(self) -> dict[str, Any]:
        return {
            "class": self.semantic_class,
            "size": [round(value, 6) for value in self.size],
            "transform": [round(value, 8) for value in self.transform()],
        }

    def audit_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "class": self.semantic_class,
            "size_m": [round(value, 6) for value in self.size],
            "center_m": [round(value, 6) for value in self.center],
            "yaw_degrees": self.yaw_degrees,
        }


def floor_box(
    role: str,
    semantic_class: str,
    size: tuple[float, float, float],
    x: float,
    y: float,
    yaw: float = 0.0,
) -> LayoutBox:
    return LayoutBox(role, semantic_class, size, (x, y, size[2] / 2.0), yaw)


def elevated_box(
    role: str,
    semantic_class: str,
    size: tuple[float, float, float],
    x: float,
    y: float,
    z: float,
    yaw: float = 0.0,
) -> LayoutBox:
    return LayoutBox(role, semantic_class, size, (x, y, z), yaw)


def load_specs(path: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            spec = json.loads(line)
            spec_id = spec["spec_id"]
            if spec_id in specs:
                raise ValueError(f"Duplicate spec_id={spec_id!r} at line {line_number}")
            specs[spec_id] = spec
    return specs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in range(4):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def _openings(
    length: float,
    width: float,
    include_window: bool,
    window_x: float | None = None,
) -> list[LayoutBox]:
    result = [
        elevated_box(
            "entrance_door",
            LABEL["screen_door"],
            (0.95, 0.12, 2.10),
            -0.31 * length,
            -width / 2.0 + 0.06,
            1.05,
        )
    ]
    if include_window:
        result.append(
            elevated_box(
                "window",
                LABEL["window"],
                (1.60, 0.10, 1.20),
                0.24 * length if window_x is None else window_x,
                width / 2.0 - 0.05,
                1.65,
            )
        )
    return result


def _ceiling_light(
    height: float,
    role: str = "ceiling_light",
    x: float = 0.0,
    y: float = 0.35,
) -> LayoutBox:
    return elevated_box(
        role,
        LABEL["ceiling_light"],
        (0.48, 0.48, 0.25),
        x,
        y,
        height - 0.18,
    )


def _bedroom(spec: dict[str, Any], variant: int) -> list[LayoutBox]:
    length, width, height = map(float, spec["extent_m"])
    right = length / 2.0
    boxes = _openings(length, width, include_window=True)
    if variant == 0:
        boxes += [
            floor_box("main_bed", LABEL["bed"], (1.80, 2.10, 0.65), 0.0, 0.62),
            floor_box(
                "bedside_table_left",
                LABEL["nightstand"],
                (0.52, 0.52, 0.58),
                -1.22,
                0.72,
            ),
            floor_box(
                "bedside_table_right",
                LABEL["nightstand"],
                (0.52, 0.52, 0.58),
                1.22,
                0.72,
            ),
            floor_box(
                "wardrobe", LABEL["wardrobe"], (0.62, 1.55, 2.20), right - 0.43, 1.20
            ),
        ]
    elif variant == 1:
        boxes += [
            floor_box("double_bed", LABEL["bed"], (2.00, 2.10, 0.66), 0.05, 0.55),
            floor_box("desk", LABEL["desk"], (1.25, 0.62, 0.76), -2.25, 1.72),
            floor_box("desk_chair", LABEL["chair"], (0.55, 0.55, 0.88), -2.25, 0.86),
            floor_box("dresser", LABEL["dresser"], (1.10, 0.52, 1.00), 2.28, 1.73),
            floor_box(
                "wardrobe", LABEL["wardrobe"], (0.62, 1.45, 2.20), right - 0.43, 0.20
            ),
        ]
    elif variant == 2:
        boxes += [
            floor_box("single_bed_left", LABEL["bed"], (1.10, 2.00, 0.62), -1.42, 0.68),
            floor_box("single_bed_right", LABEL["bed"], (1.10, 2.00, 0.62), 1.42, 0.68),
            floor_box(
                "bedside_table_between",
                LABEL["nightstand"],
                (0.50, 0.50, 0.57),
                0.0,
                0.72,
            ),
            floor_box(
                "wardrobe", LABEL["wardrobe"], (0.62, 1.35, 2.20), right - 0.43, 1.55
            ),
            _ceiling_light(height),
        ]
    elif variant == 3:
        boxes += [
            floor_box("single_bed", LABEL["bed"], (1.10, 2.00, 0.62), -1.55, 0.70),
            floor_box(
                "bookcase", LABEL["shelf"], (0.52, 1.20, 1.95), right - 0.38, 1.42
            ),
            floor_box("writing_desk", LABEL["desk"], (1.20, 0.62, 0.76), 1.10, 1.66),
            floor_box("desk_chair", LABEL["chair"], (0.55, 0.55, 0.88), 1.10, 0.82),
            floor_box("rug", LABEL["rug"], (1.65, 1.25, 0.035), 0.0, 0.20),
        ]
    elif variant == 4:
        boxes += [
            floor_box("main_bed", LABEL["bed"], (1.75, 2.10, 0.65), -0.35, 0.58),
            floor_box(
                "wardrobe", LABEL["wardrobe"], (0.62, 1.50, 2.20), right - 0.43, 1.30
            ),
            floor_box(
                "chest_of_drawers", LABEL["dresser"], (1.10, 0.52, 0.96), -2.15, 1.73
            ),
            elevated_box(
                "mirror",
                LABEL["mirror"],
                (1.00, 0.08, 0.90),
                -2.15,
                width / 2.0 - 0.05,
                1.62,
            ),
            floor_box(
                "bedside_table", LABEL["nightstand"], (0.52, 0.52, 0.58), 0.95, 0.62
            ),
            elevated_box(
                "bedside_lamp", LABEL["sconce"], (0.28, 0.20, 0.42), 0.95, 0.64, 1.08
            ),
        ]
    else:
        raise ValueError(f"Unsupported bedroom variant {variant}")
    return boxes


def _living_room(spec: dict[str, Any], variant: int) -> list[LayoutBox]:
    length, width, height = map(float, spec["extent_m"])
    left, right, top = -length / 2.0, length / 2.0, width / 2.0
    boxes = _openings(length, width, include_window=variant in {0, 2, 3})
    if variant == 0:
        boxes += [
            floor_box("sofa", LABEL["sofa"], (2.55, 0.88, 0.88), 0.0, top - 0.62),
            floor_box("coffee_table", LABEL["table"], (1.25, 0.72, 0.44), 0.0, 0.62),
            elevated_box(
                "television", LABEL["tv"], (1.35, 0.16, 0.78), 0.0, -0.45, 1.10
            ),
            floor_box(
                "side_seat_left",
                LABEL["armchair"],
                (0.88, 0.88, 0.92),
                -1.75,
                0.62,
                -18.0,
            ),
            floor_box(
                "side_seat_right",
                LABEL["armchair"],
                (0.88, 0.88, 0.92),
                1.75,
                0.62,
                18.0,
            ),
            floor_box("rug", LABEL["rug"], (3.10, 2.25, 0.035), 0.0, 0.72),
        ]
    elif variant == 1:
        boxes += [
            floor_box(
                "sofa_long", LABEL["sofa"], (2.70, 0.88, 0.88), -0.45, top - 0.62
            ),
            floor_box(
                "sofa_side", LABEL["sofa"], (2.10, 0.88, 0.88), right - 0.62, 0.72, 90.0
            ),
            floor_box("coffee_table", LABEL["table"], (1.30, 0.78, 0.44), 0.25, 0.72),
            floor_box(
                "side_table", LABEL["nightstand"], (0.52, 0.52, 0.58), -1.95, 1.28
            ),
            floor_box("floor_lamp", LABEL["sconce"], (0.32, 0.32, 1.55), -2.30, 1.72),
            floor_box(
                "bookcase", LABEL["shelf"], (0.52, 1.30, 1.95), left + 0.38, 1.00
            ),
        ]
    elif variant == 2:
        boxes += [
            floor_box("sofa", LABEL["sofa"], (2.35, 0.86, 0.86), 0.0, top - 0.60),
            floor_box(
                "armchair_left",
                LABEL["armchair"],
                (0.85, 0.85, 0.90),
                -1.55,
                0.65,
                -15.0,
            ),
            floor_box(
                "armchair_right",
                LABEL["armchair"],
                (0.85, 0.85, 0.90),
                1.55,
                0.65,
                15.0,
            ),
            floor_box("coffee_table", LABEL["table"], (1.15, 0.70, 0.43), 0.0, 0.60),
            floor_box(
                "television_console", LABEL["cabinet"], (1.65, 0.42, 0.62), 0.0, -0.48
            ),
            elevated_box(
                "television", LABEL["tv"], (1.20, 0.14, 0.68), 0.0, -0.46, 1.18
            ),
            elevated_box(
                "wall_decoration",
                LABEL["painting"],
                (1.10, 0.08, 0.72),
                left + 0.05,
                0.65,
                1.55,
                90.0,
            ),
        ]
    elif variant == 3:
        boxes += [
            floor_box(
                "l_sofa_long", LABEL["sofa"], (2.65, 0.88, 0.88), -0.42, top - 0.62
            ),
            floor_box(
                "l_sofa_return",
                LABEL["sofa"],
                (1.85, 0.88, 0.88),
                right - 0.62,
                1.05,
                90.0,
            ),
            floor_box("coffee_table", LABEL["table"], (1.20, 0.75, 0.44), 0.15, 0.72),
            elevated_box(
                "television",
                LABEL["tv"],
                (1.25, 0.14, 0.72),
                left + 0.10,
                0.75,
                1.18,
                90.0,
            ),
            floor_box(
                "bookcase", LABEL["shelf"], (0.52, 1.30, 1.95), left + 0.38, 1.72
            ),
            floor_box(
                "indoor_plant_left",
                LABEL["plant"],
                (0.52, 0.52, 1.20),
                -1.80,
                top - 0.48,
            ),
            floor_box(
                "indoor_plant_right",
                LABEL["plant"],
                (0.52, 0.52, 1.20),
                1.72,
                top - 0.48,
            ),
            floor_box("rug", LABEL["rug"], (3.00, 2.20, 0.035), 0.10, 0.72),
        ]
    elif variant == 4:
        boxes += [
            floor_box(
                "central_sofa", LABEL["sofa"], (2.75, 0.90, 0.90), 0.0, top - 0.65
            ),
            floor_box(
                "matching_armchair_left",
                LABEL["armchair"],
                (0.92, 0.92, 0.94),
                -1.85,
                0.62,
                -15.0,
            ),
            floor_box(
                "matching_armchair_right",
                LABEL["armchair"],
                (0.92, 0.92, 0.94),
                1.85,
                0.62,
                15.0,
            ),
            floor_box("coffee_table", LABEL["table"], (1.35, 0.82, 0.45), 0.0, 0.62),
            floor_box(
                "side_table_left", LABEL["nightstand"], (0.50, 0.50, 0.56), -1.78, 1.55
            ),
            floor_box(
                "side_table_right", LABEL["nightstand"], (0.50, 0.50, 0.56), 1.78, 1.55
            ),
            elevated_box(
                "lamp_left", LABEL["sconce"], (0.25, 0.20, 0.38), -1.78, 1.55, 1.02
            ),
            elevated_box(
                "lamp_right", LABEL["sconce"], (0.25, 0.20, 0.38), 1.78, 1.55, 1.02
            ),
            floor_box("large_rug", LABEL["rug"], (3.50, 2.45, 0.035), 0.0, 0.72),
            elevated_box(
                "wall_art", LABEL["painting"], (1.45, 0.08, 0.80), 0.0, top - 0.04, 1.60
            ),
        ]
    else:
        raise ValueError(f"Unsupported living-room variant {variant}")
    boxes.append(_ceiling_light(height))
    return boxes


def _kitchen(spec: dict[str, Any], variant: int) -> list[LayoutBox]:
    length, width, height = map(float, spec["extent_m"])
    left, right, top, bottom = -length / 2.0, length / 2.0, width / 2.0, -width / 2.0
    boxes = _openings(length, width, include_window=variant in {0, 1})
    if variant == 0:
        boxes += [
            floor_box(
                "continuous_counter",
                LABEL["counter"],
                (3.55, 0.66, 0.90),
                -0.42,
                top - 0.42,
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.72, 0.48, 0.18), -1.30, top - 0.42, 0.98
            ),
            elevated_box(
                "stove", LABEL["stove"], (0.72, 0.50, 0.18), 0.42, top - 0.42, 0.98
            ),
            floor_box(
                "refrigerator",
                LABEL["refrigerator"],
                (0.78, 0.82, 2.05),
                right - 0.55,
                1.30,
            ),
            elevated_box(
                "wall_cabinet_left",
                LABEL["cabinet"],
                (1.25, 0.42, 0.78),
                -1.55,
                top - 0.26,
                1.72,
            ),
            elevated_box(
                "wall_cabinet_right",
                LABEL["cabinet"],
                (1.25, 0.42, 0.78),
                0.78,
                top - 0.26,
                1.72,
            ),
        ]
    elif variant == 1:
        boxes += [
            floor_box(
                "counter_long", LABEL["counter"], (3.60, 0.66, 0.90), -0.45, top - 0.42
            ),
            floor_box(
                "counter_return",
                LABEL["counter"],
                (2.05, 0.66, 0.90),
                right - 0.42,
                0.72,
                90.0,
            ),
            elevated_box(
                "sink_beneath_window",
                LABEL["sink"],
                (0.75, 0.48, 0.18),
                0.95,
                top - 0.42,
                0.98,
            ),
            elevated_box(
                "stove", LABEL["stove"], (0.72, 0.50, 0.18), -0.62, top - 0.42, 0.98
            ),
            floor_box(
                "refrigerator",
                LABEL["refrigerator"],
                (0.78, 0.82, 2.05),
                left + 0.55,
                1.25,
            ),
            elevated_box(
                "upper_cabinet",
                LABEL["cabinet"],
                (1.40, 0.42, 0.78),
                -1.55,
                top - 0.26,
                1.72,
            ),
            floor_box(
                "lower_cabinet",
                LABEL["cabinet"],
                (0.70, 1.20, 0.86),
                right - 0.44,
                -0.48,
            ),
            elevated_box(
                "task_light", LABEL["sconce"], (0.35, 0.20, 0.25), 0.0, top - 0.20, 2.25
            ),
        ]
    elif variant == 2:
        boxes += [
            floor_box(
                "perimeter_counter",
                LABEL["counter"],
                (3.80, 0.66, 0.90),
                -0.25,
                top - 0.42,
            ),
            floor_box(
                "side_counter",
                LABEL["counter"],
                (1.75, 0.66, 0.90),
                right - 0.42,
                1.05,
                90.0,
            ),
            floor_box(
                "central_island", LABEL["island"], (1.65, 0.88, 0.92), 0.05, 0.42
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.70, 0.48, 0.18), -1.18, top - 0.42, 0.98
            ),
            elevated_box(
                "stove", LABEL["stove"], (0.72, 0.50, 0.18), 0.62, top - 0.42, 0.98
            ),
            floor_box(
                "refrigerator",
                LABEL["refrigerator"],
                (0.80, 0.84, 2.05),
                left + 0.56,
                1.45,
            ),
            elevated_box(
                "storage_cabinet",
                LABEL["cabinet"],
                (1.35, 0.42, 0.78),
                1.65,
                top - 0.26,
                1.72,
            ),
        ]
    elif variant == 3:
        # Two opposing runs leave the central y=0 aisle and the lower-left
        # doorway visible.  The bottom run is split around that doorway.
        boxes += [
            floor_box(
                "galley_counter_top",
                LABEL["counter"],
                (4.25, 0.66, 0.90),
                0.40,
                top - 0.42,
            ),
            floor_box(
                "galley_counter_bottom_right",
                LABEL["counter"],
                (2.15, 0.66, 0.90),
                1.45,
                bottom + 0.42,
            ),
            floor_box(
                "galley_counter_bottom_left",
                LABEL["counter"],
                (0.90, 0.66, 0.90),
                left + 0.60,
                bottom + 0.42,
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.72, 0.48, 0.18), -0.72, top - 0.42, 0.98
            ),
            elevated_box(
                "stove", LABEL["stove"], (0.72, 0.50, 0.18), 0.82, top - 0.42, 0.98
            ),
            floor_box(
                "refrigerator",
                LABEL["refrigerator"],
                (0.78, 0.82, 2.05),
                right - 0.55,
                bottom + 0.58,
            ),
            elevated_box(
                "overhead_cabinet",
                LABEL["cabinet"],
                (1.55, 0.42, 0.78),
                1.72,
                top - 0.25,
                1.72,
            ),
        ]
    elif variant == 4:
        boxes += [
            floor_box(
                "work_counter", LABEL["counter"], (3.75, 0.66, 0.90), 0.05, top - 0.42
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.70, 0.48, 0.18), -1.05, top - 0.42, 0.98
            ),
            elevated_box(
                "cooktop", LABEL["stove"], (0.72, 0.50, 0.18), 0.62, top - 0.42, 0.98
            ),
            floor_box("oven", LABEL["stove"], (0.72, 0.66, 0.76), 1.48, top - 0.42),
            floor_box(
                "refrigerator",
                LABEL["refrigerator"],
                (0.80, 0.84, 2.05),
                right - 0.56,
                1.35,
            ),
            elevated_box(
                "cabinets",
                LABEL["cabinet"],
                (1.35, 0.42, 0.78),
                -1.72,
                top - 0.25,
                1.72,
            ),
            floor_box(
                "breakfast_table", LABEL["table"], (1.20, 0.78, 0.74), -0.65, 0.45
            ),
            floor_box(
                "breakfast_chair_1", LABEL["chair"], (0.52, 0.52, 0.86), -1.55, 0.45
            ),
            floor_box(
                "breakfast_chair_2", LABEL["chair"], (0.52, 0.52, 0.86), 0.25, 0.45
            ),
        ]
    else:
        raise ValueError(f"Unsupported kitchen variant {variant}")
    boxes.append(_ceiling_light(height, y=0.15))
    return boxes


def _bathroom(spec: dict[str, Any], variant: int) -> list[LayoutBox]:
    length, width, height = map(float, spec["extent_m"])
    left, right, top = -length / 2.0, length / 2.0, width / 2.0
    boxes = _openings(length, width, include_window=variant in {0, 2})
    vanity_x = -0.35
    if variant == 0:
        boxes += [
            floor_box("toilet", LABEL["toilet"], (0.72, 0.88, 0.78), left + 0.65, 0.78),
            floor_box(
                "vanity", LABEL["cabinet"], (1.20, 0.58, 0.88), vanity_x, top - 0.38
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.62, 0.45, 0.18), vanity_x, top - 0.38, 0.96
            ),
            elevated_box(
                "mirror",
                LABEL["mirror"],
                (0.82, 0.08, 0.92),
                vanity_x,
                top - 0.04,
                1.62,
            ),
            floor_box(
                "shower", LABEL["shower"], (1.18, 1.18, 2.12), right - 0.75, top - 0.75
            ),
            floor_box(
                "towel_storage", LABEL["shelf"], (0.42, 0.82, 1.55), right - 0.32, -0.25
            ),
        ]
    elif variant == 1:
        boxes += [
            floor_box(
                "bathtub", LABEL["tub"], (1.75, 0.82, 0.62), left + 1.02, top - 0.55
            ),
            floor_box("toilet", LABEL["toilet"], (0.72, 0.88, 0.78), left + 0.62, 0.15),
            floor_box("vanity", LABEL["cabinet"], (1.22, 0.58, 0.88), 0.70, top - 0.38),
            elevated_box(
                "sink", LABEL["sink"], (0.62, 0.45, 0.18), 0.70, top - 0.38, 0.96
            ),
            elevated_box(
                "wall_mirror",
                LABEL["mirror"],
                (0.88, 0.08, 0.94),
                0.70,
                top - 0.04,
                1.62,
            ),
            floor_box(
                "storage_shelves",
                LABEL["shelf"],
                (0.45, 0.92, 1.65),
                right - 0.34,
                0.45,
            ),
            _ceiling_light(height),
        ]
    elif variant == 2:
        boxes += [
            floor_box(
                "corner_shower",
                LABEL["shower"],
                (1.15, 1.15, 2.12),
                right - 0.72,
                top - 0.72,
            ),
            floor_box("toilet", LABEL["toilet"], (0.70, 0.86, 0.77), left + 0.60, 0.62),
            floor_box(
                "pedestal_sink", LABEL["sink"], (0.62, 0.55, 0.88), 0.0, top - 0.38
            ),
            elevated_box(
                "mirror", LABEL["mirror"], (0.70, 0.08, 0.85), 0.0, top - 0.04, 1.58
            ),
            elevated_box(
                "towel_hooks",
                LABEL["sconce"],
                (0.42, 0.10, 0.20),
                left + 0.05,
                -0.10,
                1.45,
                90.0,
            ),
        ]
    elif variant == 3:
        boxes += [
            floor_box(
                "bathtub", LABEL["tub"], (1.82, 0.86, 0.64), left + 1.05, top - 0.58
            ),
            floor_box(
                "separate_shower",
                LABEL["shower"],
                (1.15, 1.15, 2.12),
                right - 0.72,
                top - 0.72,
            ),
            floor_box("toilet", LABEL["toilet"], (0.72, 0.88, 0.78), left + 0.62, 0.02),
            floor_box(
                "double_sink_vanity",
                LABEL["cabinet"],
                (2.05, 0.60, 0.88),
                0.55,
                top - 0.40,
            ),
            elevated_box(
                "sink_left", LABEL["sink"], (0.60, 0.46, 0.18), 0.05, top - 0.40, 0.96
            ),
            elevated_box(
                "sink_right", LABEL["sink"], (0.60, 0.46, 0.18), 1.05, top - 0.40, 0.96
            ),
            elevated_box(
                "mirror_left",
                LABEL["mirror"],
                (0.72, 0.08, 0.88),
                0.05,
                top - 0.04,
                1.62,
            ),
            elevated_box(
                "mirror_right",
                LABEL["mirror"],
                (0.72, 0.08, 0.88),
                1.05,
                top - 0.04,
                1.62,
            ),
            floor_box(
                "storage", LABEL["cabinet"], (0.50, 0.82, 1.70), right - 0.36, -0.20
            ),
        ]
    elif variant == 4:
        boxes += [
            floor_box(
                "shower", LABEL["shower"], (1.18, 1.18, 2.12), right - 0.74, top - 0.74
            ),
            floor_box("toilet", LABEL["toilet"], (0.70, 0.86, 0.77), left + 0.60, 0.62),
            floor_box(
                "vanity", LABEL["cabinet"], (1.18, 0.58, 0.88), -0.12, top - 0.38
            ),
            elevated_box(
                "sink", LABEL["sink"], (0.62, 0.45, 0.18), -0.12, top - 0.38, 0.96
            ),
            elevated_box(
                "mirror", LABEL["mirror"], (0.82, 0.08, 0.90), -0.12, top - 0.04, 1.60
            ),
            floor_box(
                "laundry_hamper", LABEL["other"], (0.52, 0.52, 0.72), left + 0.55, -0.28
            ),
            elevated_box(
                "wall_storage",
                LABEL["shelf"],
                (0.42, 0.22, 0.85),
                right - 0.13,
                -0.35,
                1.45,
                90.0,
            ),
            elevated_box(
                "task_light",
                LABEL["sconce"],
                (0.42, 0.16, 0.22),
                -0.12,
                top - 0.08,
                2.22,
            ),
        ]
    else:
        raise ValueError(f"Unsupported bathroom variant {variant}")
    if variant not in {1}:
        boxes.append(_ceiling_light(height, y=0.15))
    return boxes


def _chairs_around_table(
    count: int,
    table_x: float,
    table_y: float,
    table_length: float,
    table_width: float,
) -> list[LayoutBox]:
    if count not in {4, 6, 8}:
        raise ValueError("Dining chair helper supports 4, 6, or 8 chairs")
    positions: list[tuple[float, float, float]] = []
    side_count = (count - 2) // 2
    for index in range(side_count):
        x = table_x - table_length / 2.0 + (index + 1) * table_length / (side_count + 1)
        positions.append((x, table_y + table_width / 2.0 + 0.52, 180.0))
        positions.append((x, table_y - table_width / 2.0 - 0.52, 0.0))
    positions.append((table_x - table_length / 2.0 - 0.52, table_y, -90.0))
    positions.append((table_x + table_length / 2.0 + 0.52, table_y, 90.0))
    return [
        floor_box(
            f"dining_chair_{index + 1}",
            LABEL["chair"],
            (0.50, 0.50, 0.88),
            x,
            y,
            yaw,
        )
        for index, (x, y, yaw) in enumerate(positions)
    ]


def _dining_room(spec: dict[str, Any], variant: int) -> list[LayoutBox]:
    length, width, height = map(float, spec["extent_m"])
    right, top = length / 2.0, width / 2.0
    boxes = _openings(length, width, include_window=variant in {0, 2, 4})
    if variant == 0:
        table = (0.0, 0.55, 2.10, 0.92)
        boxes += [
            floor_box(
                "rectangular_dining_table",
                LABEL["table"],
                (table[2], table[3], 0.76),
                table[0],
                table[1],
            )
        ]
        boxes += _chairs_around_table(6, *table)
        boxes += [
            floor_box(
                "sideboard",
                LABEL["counter"],
                (1.55, 0.48, 0.92),
                right - 0.40,
                1.40,
                90.0,
            ),
            _ceiling_light(height, x=table[0], y=table[1]),
        ]
    elif variant == 1:
        table = (0.0, 0.48, 1.25, 1.25)
        boxes += [
            floor_box(
                "round_dining_table",
                LABEL["table"],
                (table[2], table[3], 0.75),
                table[0],
                table[1],
            )
        ]
        boxes += _chairs_around_table(4, *table)
        boxes += [
            floor_box(
                "cabinet", LABEL["cabinet"], (0.52, 1.18, 1.62), right - 0.38, 1.30
            ),
            elevated_box(
                "wall_decoration",
                LABEL["painting"],
                (1.05, 0.08, 0.72),
                -1.45,
                top - 0.04,
                1.58,
            ),
            _ceiling_light(height, role="pendant_lamp", x=table[0], y=table[1]),
        ]
    elif variant == 2:
        table = (0.0, 0.55, 2.05, 0.92)
        boxes += [
            floor_box(
                "table_for_six",
                LABEL["table"],
                (table[2], table[3], 0.76),
                table[0],
                table[1],
            ),
            floor_box(
                "rug_beneath_table",
                LABEL["rug"],
                (3.25, 2.35, 0.035),
                table[0],
                table[1],
            ),
        ]
        boxes += _chairs_around_table(6, *table)
        boxes += [
            floor_box(
                "storage_cabinet",
                LABEL["cabinet"],
                (0.52, 1.25, 1.62),
                right - 0.38,
                1.35,
            ),
            _ceiling_light(height, role="ceiling_fixture", x=table[0], y=table[1]),
        ]
    elif variant == 3:
        table = (0.0, 0.52, 2.85, 1.00)
        boxes += [
            floor_box(
                "long_dining_table",
                LABEL["table"],
                (table[2], table[3], 0.77),
                table[0],
                table[1],
            )
        ]
        boxes += _chairs_around_table(8, *table)
        boxes += [
            _ceiling_light(height, role="ceiling_light_1", x=-0.72, y=table[1]),
            _ceiling_light(height, role="ceiling_light_2", x=0.72, y=table[1]),
            floor_box(
                "sideboard",
                LABEL["counter"],
                (1.60, 0.50, 0.92),
                right - 0.41,
                1.52,
                90.0,
            ),
            floor_box(
                "display_shelves",
                LABEL["shelf"],
                (0.48, 1.30, 1.88),
                -length / 2.0 + 0.36,
                1.45,
            ),
            elevated_box(
                "wall_art", LABEL["painting"], (1.25, 0.08, 0.76), 0.0, top - 0.04, 1.62
            ),
        ]
    elif variant == 4:
        table = (-0.15, 0.48, 1.40, 1.40)
        boxes += [
            floor_box(
                "square_dining_table",
                LABEL["table"],
                (table[2], table[3], 0.75),
                table[0],
                table[1],
            )
        ]
        boxes += _chairs_around_table(4, *table)
        boxes += [
            _ceiling_light(height, role="ceiling_lamp", x=table[0], y=table[1]),
            floor_box(
                "small_storage_unit",
                LABEL["cabinet"],
                (0.48, 1.00, 1.15),
                right - 0.34,
                1.35,
            ),
            floor_box(
                "plant_left", LABEL["plant"], (0.48, 0.48, 1.08), 0.78, top - 0.38
            ),
            floor_box(
                "plant_right", LABEL["plant"], (0.48, 0.48, 1.08), 1.42, top - 0.38
            ),
        ]
    else:
        raise ValueError(f"Unsupported dining-room variant {variant}")
    return boxes


def compile_boxes(spec: dict[str, Any]) -> list[LayoutBox]:
    spec_id = str(spec["spec_id"])
    try:
        variant = int(spec_id.rsplit("_", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Cannot parse variant from {spec_id!r}") from exc
    category = spec["category"]
    if category == "bedroom":
        boxes = _bedroom(spec, variant)
    elif category == "living_room":
        boxes = _living_room(spec, variant)
    elif category == "kitchen":
        boxes = _kitchen(spec, variant)
    elif category == "bathroom":
        boxes = _bathroom(spec, variant)
    elif category == "dining_room":
        boxes = _dining_room(spec, variant)
    else:
        raise ValueError(f"Unsupported indoor category {category!r}")
    validate_boxes(spec, boxes)
    return boxes


def _rotated_half_extents(box: LayoutBox) -> tuple[float, float]:
    angle = math.radians(box.yaw_degrees)
    cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
    half_x, half_y = box.size[0] / 2.0, box.size[1] / 2.0
    return cosine * half_x + sine * half_y, sine * half_x + cosine * half_y


def validate_boxes(spec: dict[str, Any], boxes: Iterable[LayoutBox]) -> None:
    length, width, height = map(float, spec["extent_m"])
    boxes = list(boxes)
    if not boxes:
        raise ValueError(f"{spec['spec_id']}: layout has no boxes")
    roles: set[str] = set()
    for box in boxes:
        if box.role in roles:
            raise ValueError(f"{spec['spec_id']}: duplicate role {box.role!r}")
        roles.add(box.role)
        if box.semantic_class not in set(LABEL.values()):
            raise ValueError(
                f"{spec['spec_id']}: unknown SpatialGen class {box.semantic_class!r}"
            )
        if any(not math.isfinite(value) or value <= 0 for value in box.size):
            raise ValueError(f"{spec['spec_id']}: invalid size for {box.role}")
        if any(not math.isfinite(value) for value in box.center):
            raise ValueError(f"{spec['spec_id']}: invalid center for {box.role}")
        half_x, half_y = _rotated_half_extents(box)
        x, y, z = box.center
        tolerance = 0.08 if box.role in {"entrance_door", "window"} else 1e-6
        if abs(x) + half_x > length / 2.0 + tolerance:
            raise ValueError(f"{spec['spec_id']}: {box.role} exceeds room x boundary")
        if abs(y) + half_y > width / 2.0 + tolerance:
            raise ValueError(f"{spec['spec_id']}: {box.role} exceeds room y boundary")
        if (
            z - box.size[2] / 2.0 < -tolerance
            or z + box.size[2] / 2.0 > height + tolerance
        ):
            raise ValueError(f"{spec['spec_id']}: {box.role} exceeds room z boundary")


def build_room_layout(spec: dict[str, Any], boxes: list[LayoutBox]) -> dict[str, Any]:
    length, width, height = map(float, spec["extent_m"])
    corners = [
        (-length / 2.0, -width / 2.0),
        (length / 2.0, -width / 2.0),
        (length / 2.0, width / 2.0),
        (-length / 2.0, width / 2.0),
    ]

    def boundary(z_m: float) -> list[dict[str, dict[str, float]]]:
        return [
            {
                "start": {
                    "x": round(x * 1000.0, 3),
                    "y": round(y * 1000.0, 3),
                    "z": round(z_m * 1000.0, 3),
                }
            }
            for x, y in corners
        ]

    return {
        "floor": boundary(0.0),
        "ceil": boundary(height),
        "bboxes": [box.official_payload() for box in boxes],
    }


def _camera_pose(x: float, y: float, z: float, yaw_degrees: float) -> list[list[float]]:
    """Return an OpenCV camera-to-world pose (x right, y down, z forward)."""
    yaw = math.radians(yaw_degrees)
    forward = (math.cos(yaw), math.sin(yaw), 0.0)
    right = (math.sin(yaw), -math.cos(yaw), 0.0)
    down = (0.0, 0.0, -1.0)
    return [
        [right[0], down[0], forward[0], x],
        [right[1], down[1], forward[1], y],
        [right[2], down[2], forward[2], z],
        [0.0, 0.0, 0.0, 1.0],
    ]


def build_cameras(spec: dict[str, Any]) -> dict[str, Any]:
    length, width, _ = map(float, spec["extent_m"])
    category = spec["category"]
    variant = int(str(spec["spec_id"]).rsplit("_", 1)[1])
    if category == "kitchen" and variant == 3:
        base_y = 0.0
        yaw_start, yaw_end = 35.0, 105.0
    else:
        base_y = -0.32 * width
        yaw_start, yaw_end = 48.0, 118.0
    poses: dict[str, list[list[float]]] = {}
    centers: list[tuple[float, float, float]] = []
    for index in range(CAMERA_VIEWS):
        fraction = index / (CAMERA_VIEWS - 1)
        x = (-0.40 + 0.80 * fraction) * length
        y = base_y + 0.055 * width * math.sin(math.pi * fraction)
        yaw = yaw_start + (yaw_end - yaw_start) * fraction
        centers.append((x, y, CAMERA_HEIGHT_M))
        poses[str(index)] = _camera_pose(x, y, CAMERA_HEIGHT_M, yaw)
    path_length = sum(
        math.dist(previous, current) for previous, current in zip(centers, centers[1:])
    )
    displacement = max(math.dist(centers[0], center) for center in centers)
    if not 0.8 * length <= path_length <= 1.2 * length:
        raise ValueError(
            f"{spec['spec_id']}: camera path {path_length:.3f} is outside "
            f"[0.8,1.2] * room length"
        )
    if displacement < 0.5:
        raise ValueError(f"{spec['spec_id']}: camera displacement is too small")
    focal = (
        0.5
        * CAMERA_RESOLUTION
        / math.tan(math.radians(CAMERA_HORIZONTAL_FOV_DEG) / 2.0)
    )
    return {
        "width": CAMERA_RESOLUTION,
        "height": CAMERA_RESOLUTION,
        "intrinsic": [
            [focal, 0.0, CAMERA_RESOLUTION / 2.0],
            [0.0, focal, CAMERA_RESOLUTION / 2.0],
            [0.0, 0.0, 1.0],
        ],
        "cameras": poses,
        "coordinate_system": "opencv_camera_to_world_z_up_world",
        "trajectory": {
            "frame_count": CAMERA_VIEWS,
            "height_m": CAMERA_HEIGHT_M,
            "horizontal_fov_degrees": CAMERA_HORIZONTAL_FOV_DEG,
            "path_length_m": path_length,
            "max_displacement_m": displacement,
            "total_yaw_change_degrees": yaw_end - yaw_start,
        },
    }


def build_native_input(
    spec: dict[str, Any],
    logical_seed: int,
    boxes: list[LayoutBox],
    cameras: dict[str, Any],
) -> dict[str, Any]:
    model_seed = method_seed(spec, logical_seed)
    return {
        "adapter": "spatialgen",
        "spec_id": spec["spec_id"],
        "logical_seed": logical_seed,
        "method_seed": model_seed,
        "prompt_en": spec["prompt_en"],
        "input_mode": "semantic_layout+text",
        "layout_seed_dependent": False,
        "layout_compiler": "table2-spatialgen-box-layout-v1",
        "layout_objects": [box.audit_payload() for box in boxes],
        "camera": cameras["trajectory"],
        "official_stages": [
            "FLUX.1-dev + FLUX.1-Wireframe-dev-lora reference image",
            "SpatialGen-1.0 multi-view RGB/SCM/semantic diffusion",
            "Sparse-RaDeGS 7000-iteration Gaussian optimization",
        ],
        "stage_boundary_note": (
            "The official text-to-scene pipeline is executed in two processes so "
            "FLUX is released before SpatialGen MVD loads; model algorithms and "
            "published inference parameters are unchanged."
        ),
    }


def _assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside baselines/: {resolved}") from exc
    return resolved


def atomic_json(path: Path, payload: Any) -> None:
    _assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def compile_run_input(
    spec: dict[str, Any], logical_seed: int, output_dir: Path, spec_file: Path
) -> dict[str, Any]:
    output_dir = _assert_baselines_path(output_dir)
    boxes = compile_boxes(spec)
    cameras = build_cameras(spec)
    native = build_native_input(spec, logical_seed, boxes, cameras)
    scene_dir = output_dir / "input/dataset" / spec["spec_id"]
    atomic_json(output_dir / "input/spec.json", spec)
    atomic_json(output_dir / "input/native_input.json", native)
    atomic_json(scene_dir / "room_layout.json", build_room_layout(spec, boxes))
    atomic_json(scene_dir / "cameras.json", cameras)
    split_path = output_dir / "input/dataset/test_split.txt"
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(spec["spec_id"] + "\n", encoding="utf-8")
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "method": "spatialgen",
            "domain": "indoor",
            "spec_id": spec["spec_id"],
            "spec_index": spec["spec_index"],
            "logical_seed": logical_seed,
            "method_seed": method_seed(spec, logical_seed),
            "hardware": {"hostname": platform.node(), "gpu_index": None},
            "attempts": [],
            "generation_success": False,
            "render_success": False,
            "failure_reason": None,
        }
    manifest.update(
        {
            "method": "spatialgen",
            "domain": "indoor",
            "spec_id": spec["spec_id"],
            "spec_index": spec["spec_index"],
            "logical_seed": logical_seed,
            "method_seed": method_seed(spec, logical_seed),
            "method_commit": SPATIALGEN_COMMIT,
            "sparseradegs_commit": RADEGS_COMMIT,
            "spec_sha256": sha256_file(spec_file),
            "adapter_sha256": sha256_file(Path(__file__)),
            "prepare_script_sha256": sha256_file(PREPARE_SCRIPT),
            "reference_script_sha256": sha256_file(REFERENCE_SCRIPT),
            "renderer_sha256": sha256_file(RENDER_SCRIPT),
            "base_protocol_sha256": sha256_file(BASE_PROTOCOL),
            "spatialgen_protocol_sha256": sha256_file(SPATIALGEN_PROTOCOL),
            "spatialgen_inference_sha256": sha256_file(SPATIALGEN_INFERENCE),
            "spatialgen_unet_loader_sha256": sha256_file(SPATIALGEN_UNET_LOADER),
            "sparseradegs_train_sha256": sha256_file(RADEGS_TRAIN),
            "sparseradegs_loss_sha256": sha256_file(RADEGS_LOSS),
            "sparseradegs_render_sha256": sha256_file(RADEGS_RENDER),
            "native_input": "input/native_input.json",
            "stage_seed_policy": (
                "Each isolated official stage is initialized with method_seed; "
                "the FLUX post-stage generator state is retained for audit but "
                "not consumed by the separate MVD process."
            ),
        }
    )
    atomic_json(manifest_path, manifest)
    return manifest


def run_directory(data_root: Path, spec: dict[str, Any], logical_seed: int) -> Path:
    return _assert_baselines_path(
        data_root / "indoor" / "spatialgen" / spec["spec_id"] / f"seed_{logical_seed}"
    )


def baseline_environment(gpu: int) -> dict[str, str]:
    env = os.environ.copy()
    work_root = BASELINES_ROOT / "work/spatialgen"
    cache_root = BASELINES_ROOT / "cache"
    for directory in (
        work_root / "home",
        work_root / "tmp",
        cache_root / "torch_extensions",
        cache_root / "matplotlib",
        cache_root / "numba",
        cache_root / "xdg",
        cache_root / "wandb",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    existing_pythonpath = env.get("PYTHONPATH", "")
    python_paths = [
        str(SPATIALGEN_ROOT),
        str(SPATIALGEN_ROOT / "src/recons/Sparse-RaDeGS"),
    ]
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "PATH": str(SPATIALGEN_PYTHON.parent) + os.pathsep + env.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(python_paths),
            "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
            "HOME": str(work_root / "home"),
            "TMPDIR": str(work_root / "tmp"),
            "HF_HOME": str(cache_root / "huggingface"),
            "HF_HUB_CACHE": str(cache_root / "huggingface/hub"),
            "HF_DATASETS_CACHE": str(cache_root / "huggingface/datasets"),
            "TRANSFORMERS_CACHE": str(cache_root / "huggingface/transformers"),
            "PIP_CACHE_DIR": str(cache_root / "pip"),
            "TORCH_HOME": str(cache_root / "torch"),
            "TORCH_EXTENSIONS_DIR": str(cache_root / "torch_extensions"),
            "MPLCONFIGDIR": str(cache_root / "matplotlib"),
            "NUMBA_CACHE_DIR": str(cache_root / "numba"),
            "XDG_CACHE_HOME": str(cache_root / "xdg"),
            "XDG_CONFIG_HOME": str(cache_root / "config"),
            "WANDB_DIR": str(cache_root / "wandb"),
            "WANDB_MODE": "offline",
            "HF_HUB_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    return env


def run_logged(
    command: list[str],
    log_path: Path,
    env: dict[str, str],
    timeout_s: int,
    cwd: Path,
) -> tuple[int, float, bool]:
    _assert_baselines_path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND_JSON=" + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            exit_code = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                exit_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                exit_code = process.wait()
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise
    return exit_code, time.monotonic() - started, timed_out


def log_has_traceback(path: Path) -> bool:
    if not path.is_file():
        return True
    return "Traceback (most recent call last):" in path.read_text(
        encoding="utf-8", errors="replace"
    )


def _attempt_index(manifest: dict[str, Any], phase: str) -> int:
    return 1 + sum(attempt.get("phase") == phase for attempt in manifest["attempts"])


def _reload_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))


def _current_attempt_provenance(run_dir: Path) -> dict[str, str]:
    """Return the source/input fingerprints that make a cached stage reusable."""

    return {
        "adapter_sha256": sha256_file(Path(__file__)),
        "prepare_script_sha256": sha256_file(PREPARE_SCRIPT),
        "reference_script_sha256": sha256_file(REFERENCE_SCRIPT),
        "renderer_sha256": sha256_file(RENDER_SCRIPT),
        "base_protocol_sha256": sha256_file(BASE_PROTOCOL),
        "spatialgen_protocol_sha256": sha256_file(SPATIALGEN_PROTOCOL),
        "spatialgen_inference_sha256": sha256_file(SPATIALGEN_INFERENCE),
        "spatialgen_unet_loader_sha256": sha256_file(SPATIALGEN_UNET_LOADER),
        "sparseradegs_train_sha256": sha256_file(RADEGS_TRAIN),
        "sparseradegs_loss_sha256": sha256_file(RADEGS_LOSS),
        "sparseradegs_render_sha256": sha256_file(RADEGS_RENDER),
        "native_input_sha256": sha256_file(run_dir / "input/native_input.json"),
    }


def _successful_attempt_is_current(
    manifest: dict[str, Any], phase: str, run_dir: Path
) -> bool:
    """Reject stale markers after any frozen implementation/input change."""

    attempt = next(
        (
            item
            for item in reversed(manifest.get("attempts", []))
            if item.get("phase") == phase and item.get("success") is True
        ),
        None,
    )
    if attempt is None:
        return False
    return all(
        attempt.get(key) == value
        for key, value in _current_attempt_provenance(run_dir).items()
    )


def _prepared_inputs_valid(run_dir: Path, spec_id: str) -> bool:
    preparation_path = run_dir / "input/preparation.json"
    scene_input = run_dir / "input/dataset" / spec_id
    if not preparation_path.is_file():
        return False
    try:
        preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if (
        preparation.get("frame_count") != CAMERA_VIEWS
        or preparation.get("room_layout_sha256")
        != sha256_file(scene_input / "room_layout.json")
        or preparation.get("cameras_sha256")
        != sha256_file(scene_input / "cameras.json")
    ):
        return False
    expected_files = [
        scene_input / subdir / f"frame_{index}.{extension}"
        for subdir, extension in (
            ("rgb", "jpg"),
            ("depth", "png"),
            ("semantic", "jpg"),
            ("layout_semantic", "jpg"),
            ("layout_depth", "png"),
            ("condition", "jpg"),
        )
        for index in range(CAMERA_VIEWS)
    ]
    return all(path.is_file() and path.stat().st_size > 0 for path in expected_files)


def _reference_output_valid(
    run_dir: Path, spec: dict[str, Any], logical_seed: int
) -> bool:
    reference_path = run_dir / "scene/intermediate/flux_reference.json"
    if not reference_path.is_file():
        return False
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    scene_input = run_dir / "input/dataset" / spec["spec_id"]
    artifacts = {
        "control_image_sha256": scene_input / "condition/frame_0.jpg",
        "reference_1024_sha256": run_dir / "scene/intermediate/flux_reference_1024.png",
        "reference_512_sha256": run_dir / "scene/intermediate/flux_reference_512.jpg",
        "native_frame_sha256": scene_input / "rgb/frame_0.jpg",
    }
    return (
        reference.get("spec_id") == spec["spec_id"]
        and reference.get("method_seed") == method_seed(spec, logical_seed)
        and reference.get("prompt") == spec["prompt_en"]
        and all(
            path.is_file()
            and path.stat().st_size > 0
            and reference.get(key) == sha256_file(path)
            for key, path in artifacts.items()
        )
        and (run_dir / "scene/intermediate/flux_generator_state.pt").is_file()
    )


def _record_attempt(
    run_dir: Path,
    manifest: dict[str, Any],
    phase: str,
    command: list[str],
    log_path: Path,
    gpu: int,
    started_at: str,
    exit_code: int,
    wall_time_s: float,
    timed_out: bool,
    success: bool,
) -> None:
    provenance = _current_attempt_provenance(run_dir)
    manifest["attempts"].append(
        {
            "phase": phase,
            **provenance,
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "wall_time_s": wall_time_s,
            "gpu_index": gpu,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "log": str(log_path.relative_to(run_dir)),
            "command": command,
            "success": success,
        }
    )
    manifest.setdefault("hardware", {})["gpu_index"] = gpu
    atomic_json(run_dir / "run_manifest.json", manifest)


def prepare_inputs(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    spec_file: Path,
    gpu: int,
    device: str,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir = run_directory(data_root, spec, logical_seed)
    compile_run_input(spec, logical_seed, run_dir, spec_file)
    marker = run_dir / "INPUT_SUCCESS"
    manifest = _reload_manifest(run_dir)
    if (
        marker.exists()
        and not force
        and _successful_attempt_is_current(manifest, "prepare", run_dir)
        and _prepared_inputs_valid(run_dir, spec["spec_id"])
    ):
        print(f"SKIP input preparation {spec['spec_id']} seed={logical_seed}")
        return True
    marker.unlink(missing_ok=True)
    attempt_index = _attempt_index(manifest, "prepare")
    log_path = run_dir / f"logs/prepare_attempt_{attempt_index:02d}.log"
    command = [
        str(SPATIALGEN_PYTHON),
        str(PREPARE_SCRIPT),
        "--run-dir",
        str(run_dir),
        "--device",
        device,
    ]
    started_at = utc_now()
    exit_code, wall_time_s, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), timeout_s, REPO_ROOT
    )
    scene_input = run_dir / "input/dataset" / spec["spec_id"]
    success = (
        exit_code == 0
        and not timed_out
        and not log_has_traceback(log_path)
        and _prepared_inputs_valid(run_dir, spec["spec_id"])
    )
    _record_attempt(
        run_dir,
        manifest,
        "prepare",
        command,
        log_path,
        gpu,
        started_at,
        exit_code,
        wall_time_s,
        timed_out,
        success,
    )
    if success:
        marker.touch()
    else:
        manifest = _reload_manifest(run_dir)
        manifest["failure_reason"] = "input_preparation_failed"
        atomic_json(run_dir / "run_manifest.json", manifest)
    print(
        f"PREPARE {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} wall={wall_time_s:.1f}s"
    )
    return success


def generate_reference(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    gpu: int,
    offload: str,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir = run_directory(data_root, spec, logical_seed)
    if not (run_dir / "INPUT_SUCCESS").exists():
        print(f"REFERENCE FAILED missing INPUT_SUCCESS: {run_dir}", file=sys.stderr)
        return False
    marker = run_dir / "REFERENCE_SUCCESS"
    manifest = _reload_manifest(run_dir)
    if (
        marker.exists()
        and not force
        and _successful_attempt_is_current(manifest, "reference", run_dir)
        and _reference_output_valid(run_dir, spec, logical_seed)
    ):
        print(f"SKIP reference {spec['spec_id']} seed={logical_seed}")
        return True
    marker.unlink(missing_ok=True)
    attempt_index = _attempt_index(manifest, "reference")
    log_path = run_dir / f"logs/reference_attempt_{attempt_index:02d}.log"
    command = [
        str(SPATIALGEN_PYTHON),
        str(REFERENCE_SCRIPT),
        "--run-dir",
        str(run_dir),
        "--base-model",
        str(FLUX_BASE_MODEL),
        "--lora",
        str(FLUX_LORA),
        "--device",
        "cuda:0",
        "--offload",
        offload,
    ]
    started_at = utc_now()
    exit_code, wall_time_s, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), timeout_s, REPO_ROOT
    )
    native_frame = run_dir / "input/dataset" / spec["spec_id"] / "rgb/frame_0.jpg"
    success = (
        exit_code == 0
        and not timed_out
        and not log_has_traceback(log_path)
        and native_frame.is_file()
        and native_frame.stat().st_size > 1024
        and _reference_output_valid(run_dir, spec, logical_seed)
    )
    _record_attempt(
        run_dir,
        manifest,
        "reference",
        command,
        log_path,
        gpu,
        started_at,
        exit_code,
        wall_time_s,
        timed_out,
        success,
    )
    if success:
        marker.touch()
    else:
        manifest = _reload_manifest(run_dir)
        manifest["failure_reason"] = "flux_reference_failed"
        atomic_json(run_dir / "run_manifest.json", manifest)
    print(
        f"REFERENCE {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} method_seed={method_seed(spec, logical_seed)} "
        f"wall={wall_time_s:.1f}s"
    )
    return success


def _archive_partial_native(run_dir: Path, attempt_index: int) -> None:
    native_dir = run_dir / "scene/native"
    if not native_dir.exists():
        return
    archive_dir = run_dir / "scene" / f"native_before_attempt_{attempt_index:02d}"
    suffix = 1
    while archive_dir.exists():
        archive_dir = (
            run_dir
            / "scene"
            / (f"native_before_attempt_{attempt_index:02d}_{suffix:02d}")
        )
        suffix += 1
    shutil.move(str(native_dir), str(archive_dir))


def _valid_mvd_archive(path: Path) -> bool:
    """Check that a resumable SpatialGen NPZ has a complete ZIP payload."""

    if not path.is_file() or path.stat().st_size <= 1024 * 1024:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            return (
                len(names) == 1
                and names[0].endswith(".npy")
                and archive.testzip() is None
            )
    except (OSError, zipfile.BadZipFile):
        return False


def generate_mvd_and_gaussian(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir = run_directory(data_root, spec, logical_seed)
    if not (run_dir / "REFERENCE_SUCCESS").exists():
        print(
            f"GENERATION FAILED missing REFERENCE_SUCCESS: {run_dir}", file=sys.stderr
        )
        return False
    marker = run_dir / "GENERATION_SUCCESS"
    existing_gaussians = sorted(
        (run_dir / "scene/native").glob("**/point_cloud/iteration_7000/point_cloud.ply")
    )
    manifest = _reload_manifest(run_dir)
    existing_inference = sorted(
        (run_dir / "scene/native").glob("**/inference_results.npz")
    )
    if (
        marker.exists()
        and not force
        and _successful_attempt_is_current(manifest, "generate", run_dir)
        and len(existing_inference) == 1
        and existing_inference[0].stat().st_size > 1024 * 1024
        and len(existing_gaussians) == 1
        and existing_gaussians[0].stat().st_size > 1024 * 1024
    ):
        print(f"SKIP MVD/Gaussian {spec['spec_id']} seed={logical_seed}")
        return True
    marker.unlink(missing_ok=True)
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    attempt_index = _attempt_index(manifest, "generate")
    reusable_mvd = len(existing_inference) == 1 and _valid_mvd_archive(
        existing_inference[0]
    )
    if (run_dir / "scene/native").exists() and not reusable_mvd:
        _archive_partial_native(run_dir, attempt_index)
    native_output = run_dir / "scene/native"
    native_output.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"logs/generate_attempt_{attempt_index:02d}.log"
    input_dataset = run_dir / "input/dataset"
    command = [
        str(SPATIALGEN_PYTHON),
        "src/inference_sd.py",
        "--config_file",
        "configs/test_spatialgen_sd21.yaml",
        "--tag",
        "official",
        "--infer_tag",
        f"table2_seed_{method_seed(spec, logical_seed):03d}",
        "--allow_tf32",
        "--seed",
        str(method_seed(spec, logical_seed)),
        "--num_inference_steps",
        "20",
        "--scene_id",
        spec["spec_id"],
        "--style_prompt",
        spec["prompt_en"],
        "--guidance_scale",
        "3.5",
        "--output_dir",
        str(native_output),
        f"opt.pretrained_model_name_or_path={SPATIALGEN_CKPT}",
        f"opt.test_data_dir={input_dataset}",
        f"opt.test_split_file={input_dataset / 'test_split.txt'}",
        "opt.input_res=512",
        "opt.num_input_views=1",
        "opt.num_views=16",
        "opt.prediction_type=v_prediction",
        "opt.use_layout_prior=true",
        "opt.use_scene_coord_map=true",
        "opt.use_metric_depth=false",
        "opt.input_concat_binary_mask=true",
        "opt.input_concat_warpped_image=true",
        f"opt.spatiallm_data_dir={run_dir / 'input/none'}",
        f"opt.structured3d_data_dir={run_dir / 'input/none'}",
        "opt.trajectory_sampler_type=spiral",
    ]
    started_at = utc_now()
    exit_code, wall_time_s, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), timeout_s, SPATIALGEN_ROOT
    )
    inference_files = sorted(native_output.glob("**/inference_results.npz"))
    gaussian_files = sorted(
        native_output.glob("**/point_cloud/iteration_7000/point_cloud.ply")
    )
    success = (
        exit_code == 0
        and not timed_out
        and not log_has_traceback(log_path)
        and len(inference_files) == 1
        and inference_files[0].stat().st_size > 1024 * 1024
        and len(gaussian_files) == 1
        and gaussian_files[0].stat().st_size > 1024 * 1024
    )
    _record_attempt(
        run_dir,
        manifest,
        "generate",
        command,
        log_path,
        gpu,
        started_at,
        exit_code,
        wall_time_s,
        timed_out,
        success,
    )
    manifest = _reload_manifest(run_dir)
    manifest["generation_success"] = success
    manifest["failure_reason"] = None if success else "mvd_or_gaussian_failed"
    if success:
        manifest["native_inference_results"] = str(
            inference_files[0].relative_to(run_dir)
        )
        manifest["native_gaussian"] = str(gaussian_files[0].relative_to(run_dir))
        marker.touch()
    atomic_json(run_dir / "run_manifest.json", manifest)
    print(
        f"GENERATION {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} method_seed={method_seed(spec, logical_seed)} "
        f"wall={wall_time_s:.1f}s"
    )
    return success


def inspect_rendered_output(run_dir: Path) -> dict[str, Any]:
    import numpy as np
    from PIL import Image, ImageStat

    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    records: list[dict[str, Any]] = []
    valid = True
    for path, expected_size in [
        *((path, (1280, 720)) for path in anchors),
        *((path, (512, 512)) for path in sequence),
    ]:
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                stats = ImageStat.Stat(rgb)
                mean = sum(stats.mean) / (3.0 * 255.0)
                std = sum(stats.stddev) / (3.0 * 255.0)
                record = {
                    "path": str(path.relative_to(run_dir)),
                    "size": list(rgb.size),
                    "mean": mean,
                    "std": std,
                }
                records.append(record)
                if rgb.size != expected_size or not (
                    0.01 <= mean <= 0.99 and std >= 0.01
                ):
                    valid = False
        except Exception as exc:
            records.append({"path": str(path.relative_to(run_dir)), "error": repr(exc)})
            valid = False

    cameras_path = run_dir / "renders/sequence/cameras.json"
    trajectory = {
        "valid": False,
        "frame_count": 0,
        "path_length_m": 0.0,
        "max_displacement_from_first_m": 0.0,
        "max_height_error_m": None,
        "min_path_length_m": 1.0,
        "min_max_displacement_m": 0.5,
    }
    if cameras_path.is_file():
        try:
            payload = json.loads(cameras_path.read_text(encoding="utf-8"))
            camera_records = payload.get("sequence", [])
            matrices = [
                np.asarray(record["camera_to_world_opencv"], dtype=np.float64)
                for record in camera_records
            ]
            centers = [matrix[:3, 3] for matrix in matrices]
            if centers:
                path_length = sum(
                    float(np.linalg.norm(current - previous))
                    for previous, current in zip(centers, centers[1:])
                )
                displacement = max(
                    float(np.linalg.norm(center - centers[0])) for center in centers
                )
                height_error = max(
                    abs(float(center[2]) - CAMERA_HEIGHT_M) for center in centers
                )
                rotations_valid = all(
                    np.max(np.abs(matrix[:3, :3].T @ matrix[:3, :3] - np.eye(3)))
                    <= 1e-4
                    and abs(float(np.linalg.det(matrix[:3, :3])) - 1.0) <= 1e-4
                    for matrix in matrices
                )
                fov_valid = all(
                    abs(
                        float(record["horizontal_fov_degrees"])
                        - CAMERA_HORIZONTAL_FOV_DEG
                    )
                    <= 1e-6
                    for record in camera_records
                )
                trajectory.update(
                    {
                        "frame_count": len(centers),
                        "path_length_m": path_length,
                        "max_displacement_from_first_m": displacement,
                        "max_height_error_m": height_error,
                        "rotations_valid": rotations_valid,
                        "horizontal_fov_valid": fov_valid,
                        "valid": len(centers) == 50
                        and path_length >= trajectory["min_path_length_m"]
                        and displacement >= trajectory["min_max_displacement_m"]
                        and height_error <= 1e-4
                        and rotations_valid
                        and fov_valid,
                    }
                )
        except Exception as exc:
            trajectory["error"] = repr(exc)
    scene_file = run_dir / "scene/scene.ply"
    valid = (
        valid
        and len(anchors) == 8
        and len(sequence) == 50
        and cameras_path.is_file()
        and trajectory["valid"]
        and scene_file.is_file()
        and scene_file.stat().st_size > 1024 * 1024
    )
    return {
        "valid": valid,
        "scene_file": str(scene_file.relative_to(run_dir)),
        "scene_file_exists": scene_file.is_file(),
        "anchor_count": len(anchors),
        "sequence_count": len(sequence),
        "cameras_json": cameras_path.is_file(),
        "trajectory": trajectory,
        "images": records,
    }


def render_table2(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    gpu: int,
    timeout_s: int,
    force: bool,
) -> bool:
    run_dir = run_directory(data_root, spec, logical_seed)
    if not (run_dir / "GENERATION_SUCCESS").exists():
        print(f"RENDER FAILED missing GENERATION_SUCCESS: {run_dir}", file=sys.stderr)
        return False
    marker = run_dir / "SUCCESS"
    manifest = _reload_manifest(run_dir)
    if (
        marker.exists()
        and not force
        and _successful_attempt_is_current(manifest, "render", run_dir)
    ):
        validation = inspect_rendered_output(run_dir)
        if validation["valid"]:
            print(f"SKIP render {spec['spec_id']} seed={logical_seed}")
            return True
    marker.unlink(missing_ok=True)
    attempt_index = _attempt_index(manifest, "render")
    log_path = run_dir / f"logs/render_attempt_{attempt_index:02d}.log"
    command = [str(SPATIALGEN_PYTHON), str(RENDER_SCRIPT), "--run-dir", str(run_dir)]
    started_at = utc_now()
    exit_code, wall_time_s, timed_out = run_logged(
        command, log_path, baseline_environment(gpu), timeout_s, REPO_ROOT
    )
    validation = (
        inspect_rendered_output(run_dir)
        if exit_code == 0 and not timed_out
        else {
            "valid": False,
            "anchor_count": 0,
            "sequence_count": 0,
            "cameras_json": False,
            "images": [],
        }
    )
    atomic_json(run_dir / "renders/validation.json", validation)
    success = (
        exit_code == 0
        and not timed_out
        and not log_has_traceback(log_path)
        and validation["valid"]
    )
    _record_attempt(
        run_dir,
        manifest,
        "render",
        command,
        log_path,
        gpu,
        started_at,
        exit_code,
        wall_time_s,
        timed_out,
        success,
    )
    manifest = _reload_manifest(run_dir)
    manifest["render_success"] = success
    manifest["failure_reason"] = None if success else "render_or_validation_failed"
    atomic_json(run_dir / "run_manifest.json", manifest)
    if success:
        marker.touch()
    print(
        f"RENDER {'OK' if success else 'FAILED'} {spec['spec_id']} "
        f"seed={logical_seed} wall={wall_time_s:.1f}s"
    )
    return success


def run_pipeline(
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path,
    spec_file: Path,
    phase: str,
    gpu: int,
    prepare_device: str,
    flux_offload: str,
    prepare_timeout_s: int,
    reference_timeout_s: int,
    generation_timeout_s: int,
    render_timeout_s: int,
    force: bool,
) -> bool:
    run_dir = run_directory(data_root, spec, logical_seed)
    compile_run_input(spec, logical_seed, run_dir, spec_file)
    if phase == "compile":
        return True
    if phase in {"prepare", "all"}:
        if not prepare_inputs(
            spec,
            logical_seed,
            data_root,
            spec_file,
            gpu,
            prepare_device,
            prepare_timeout_s,
            force,
        ):
            return False
        if phase == "prepare":
            return True
    if phase in {"reference", "all"}:
        if not generate_reference(
            spec,
            logical_seed,
            data_root,
            gpu,
            flux_offload,
            reference_timeout_s,
            force,
        ):
            return False
        if phase == "reference":
            return True
    if phase in {"generate", "all"}:
        if not generate_mvd_and_gaussian(
            spec,
            logical_seed,
            data_root,
            gpu,
            generation_timeout_s,
            force,
        ):
            return False
        if phase == "generate":
            return True
    if phase in {"render", "all"}:
        return render_table2(
            spec, logical_seed, data_root, gpu, render_timeout_s, force
        )
    raise ValueError(f"Unknown phase: {phase}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser(
        "compile", help="compile one native SpatialGen input"
    )
    compile_parser.add_argument("--spec-file", type=Path, default=DEFAULT_SPEC_FILE)
    compile_parser.add_argument("--spec-id", required=True)
    compile_parser.add_argument("--seed", type=int, required=True)
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser = subparsers.add_parser("run", help="execute one SpatialGen Table-2 run")
    run_parser.add_argument("--spec-file", type=Path, default=DEFAULT_SPEC_FILE)
    run_parser.add_argument("--spec-id", required=True)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    run_parser.add_argument(
        "--phase",
        choices=("compile", "prepare", "reference", "generate", "render", "all"),
        default="all",
    )
    run_parser.add_argument("--gpu", type=int, default=0)
    run_parser.add_argument(
        "--prepare-device", choices=("cpu", "cuda:0"), default="cuda:0"
    )
    run_parser.add_argument(
        "--flux-offload", choices=("model", "sequential", "none"), default="sequential"
    )
    run_parser.add_argument("--prepare-timeout-s", type=int, default=1800)
    run_parser.add_argument("--reference-timeout-s", type=int, default=7200)
    run_parser.add_argument("--generation-timeout-s", type=int, default=14400)
    run_parser.add_argument("--render-timeout-s", type=int, default=3600)
    run_parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "compile":
        specs = load_specs(args.spec_file)
        if args.spec_id not in specs:
            raise KeyError(f"Unknown spec_id={args.spec_id!r}")
        compile_run_input(
            specs[args.spec_id], args.seed, args.output_dir, args.spec_file
        )
        print(
            f"SPATIALGEN_INPUT_COMPILED spec={args.spec_id} seed={args.seed} "
            f"output={args.output_dir}",
            flush=True,
        )
        return 0
    if args.command == "run":
        specs = load_specs(args.spec_file)
        if args.spec_id not in specs:
            raise KeyError(f"Unknown spec_id={args.spec_id!r}")
        ok = run_pipeline(
            specs[args.spec_id],
            args.seed,
            args.data_root,
            args.spec_file,
            args.phase,
            args.gpu,
            args.prepare_device,
            args.flux_offload,
            args.prepare_timeout_s,
            args.reference_timeout_s,
            args.generation_timeout_s,
            args.render_timeout_s,
            args.force,
        )
        return 0 if ok else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
