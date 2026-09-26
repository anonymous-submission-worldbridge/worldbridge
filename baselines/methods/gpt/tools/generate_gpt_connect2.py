#!/usr/bin/env python3
"""Materialize GPT-6 Astra high blueprints for the connect2 3D showcase.

The blueprints are authored in-session by GPT-6 Astra high and intentionally
use only the repository's local procedural Blender API.  No downloads or
external assets are required.
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
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gpt6_astra/connect2"

SCENES = (
    (
        "residential_neighborhood",
        "apartments' living room with shared courtyard",
        ["residential area", "apartment", "Shared courtyard"],
    ),
    (
        "neighborhood_school",
        "Community school classrooms and campus front yard",
        ["school", "classroom", "school campus"],
    ),
    (
        "public_library",
        "Public library reading room and entrance plaza",
        ["library", "reading room", "square"],
    ),
    (
        "community_sports_hall",
        "Community gymnasium and outdoor court",
        ["gymnasium", "field", "changing facilities"],
    ),
    (
        "retail_pharmacy",
        "Community Shop, Pharmacy, and Pedestrian Street",
        ["shop", "pharmacy", "Retail Street"],
    ),
    (
        "police_station",
        "Community Police Department Reception Hall and Front Yard",
        ["police department", "reception", "police station courtyard"],
    ),
    (
        "fire_station",
        "Fire Department Equipment Section and Vehicle Parking Area",
        ["fire department", "Equipment Hall", "fire truck"],
    ),
    (
        "community_hospital",
        "Community Hospital's outpatient hall and emergency drop-off area",
        ["hospital", "Outpatient clinic", "emergency drop-off area"],
    ),
    (
        "light_factory",
        "Light industrial workshops and loading docks",
        ["factory", "workshop", "loading/unloading area"],
    ),
    (
        "delivery_service_hub",
        "delivery station and delivery cabinet for express deliveries",
        ["post office", "delivery box", "delivery cabinet"],
    ),
    (
        "community_bank_atm",
        "Community bank branch and outdoor ATM",
        ["bank", "ATM", "store"],
    ),
    (
        "gas_station_store",
        "Gas station convenience store and fueling area",
        ["gas station", "supermarket", "gasoline pump"],
    ),
    (
        "riverside_lake_park",
        "visitor center at the park, lake side, and small river",
        ["park", "by the lake", "Small river", "Visitor Center"],
    ),
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


class Blueprint:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.calls = 0

    def call(self, method: str, *args, **kwargs) -> None:
        parts = [repr(arg) for arg in args]
        parts.extend(f"{key}={value!r}" for key, value in kwargs.items())
        self.lines.append(f"    api.{method}({', '.join(parts)})")
        self.calls += 1

    def box(self, name, location, scale, material="Primary", bevel=0.04) -> None:
        self.call("box", name, location, scale, material, bevel)

    def cylinder(
        self, name, location, radius, depth, material="Metal", vertices=32
    ) -> None:
        self.call("cylinder", name, location, radius, depth, material, vertices)


def add_materials(b: Blueprint, scene_id: str) -> None:
    palettes = {
        "residential_neighborhood": (
            (0.78, 0.56, 0.34),
            (0.28, 0.47, 0.62),
            (0.72, 0.79, 0.68),
        ),
        "neighborhood_school": (
            (0.91, 0.66, 0.18),
            (0.12, 0.43, 0.68),
            (0.42, 0.66, 0.38),
        ),
        "public_library": ((0.46, 0.25, 0.13), (0.10, 0.38, 0.34), (0.72, 0.24, 0.20)),
        "community_sports_hall": (
            (0.10, 0.34, 0.64),
            (0.88, 0.38, 0.12),
            (0.16, 0.62, 0.48),
        ),
        "retail_pharmacy": ((0.18, 0.58, 0.46), (0.92, 0.92, 0.88), (0.20, 0.42, 0.68)),
        "police_station": ((0.10, 0.28, 0.56), (0.82, 0.85, 0.88), (0.72, 0.56, 0.18)),
        "fire_station": ((0.72, 0.08, 0.055), (0.18, 0.20, 0.22), (0.92, 0.66, 0.08)),
        "community_hospital": (
            (0.22, 0.62, 0.64),
            (0.90, 0.92, 0.90),
            (0.36, 0.62, 0.82),
        ),
        "light_factory": ((0.25, 0.32, 0.38), (0.92, 0.50, 0.08), (0.20, 0.52, 0.64)),
        "delivery_service_hub": (
            (0.92, 0.48, 0.06),
            (0.16, 0.36, 0.62),
            (0.86, 0.82, 0.22),
        ),
        "community_bank_atm": (
            (0.08, 0.30, 0.44),
            (0.70, 0.56, 0.22),
            (0.42, 0.62, 0.48),
        ),
        "gas_station_store": (
            (0.11, 0.45, 0.62),
            (0.90, 0.52, 0.06),
            (0.86, 0.16, 0.10),
        ),
        "riverside_lake_park": (
            (0.18, 0.45, 0.28),
            (0.16, 0.52, 0.68),
            (0.72, 0.58, 0.34),
        ),
    }
    primary, accent, secondary = palettes[scene_id]
    materials = (
        ("Primary", primary, 0.05, 0.48, 0.0),
        ("Accent", accent, 0.0, 0.46, 0.0),
        ("Secondary", secondary, 0.0, 0.55, 0.0),
        ("LightWood", (0.68, 0.45, 0.24), 0.0, 0.52, 0.0),
        ("DarkWood", (0.20, 0.105, 0.055), 0.0, 0.48, 0.0),
        ("Metal", (0.16, 0.18, 0.20), 0.72, 0.28, 0.0),
        ("Steel", (0.50, 0.55, 0.58), 0.78, 0.24, 0.0),
        ("White", (0.90, 0.90, 0.86), 0.0, 0.63, 0.0),
        ("Black", (0.025, 0.030, 0.035), 0.25, 0.27, 0.0),
        ("Glass", (0.38, 0.64, 0.74), 0.05, 0.10, 0.0),
        ("Glow", (1.0, 0.74, 0.38), 0.0, 0.20, 3.0),
        ("Green", (0.10, 0.34, 0.12), 0.0, 0.75, 0.0),
        ("LeafLight", (0.25, 0.55, 0.18), 0.0, 0.72, 0.0),
        ("Soil", (0.10, 0.055, 0.025), 0.0, 0.95, 0.0),
        ("Concrete", (0.46, 0.48, 0.47), 0.0, 0.86, 0.0),
        ("Asphalt", (0.075, 0.085, 0.09), 0.0, 0.94, 0.0),
        ("Water", (0.04, 0.35, 0.52), 0.05, 0.12, 0.0),
        ("Red", (0.70, 0.055, 0.035), 0.05, 0.38, 0.0),
        ("Blue", (0.035, 0.19, 0.60), 0.05, 0.36, 0.0),
        ("Yellow", (0.95, 0.58, 0.035), 0.0, 0.42, 0.0),
        ("Fabric", (0.62, 0.67, 0.62), 0.0, 0.88, 0.0),
        ("Product", (0.72, 0.30, 0.22), 0.0, 0.52, 0.0),
    )
    for name, color, metallic, roughness, emission in materials:
        b.call("mat", name, color, metallic, roughness, emission)


def add_bench(
    b: Blueprint, name: str, x: float, y: float, material="LightWood"
) -> None:
    b.box(name + "_seat", (x, y, 0.52), (2.0, 0.48, 0.13), material, 0.035)
    b.box(name + "_back", (x, y + 0.20, 0.90), (2.0, 0.10, 0.66), material, 0.035)
    for side in (-0.78, 0.78):
        b.box(
            name + f"_leg_{side}",
            (x + side, y, 0.25),
            (0.10, 0.40, 0.50),
            "Metal",
            0.018,
        )


def add_vehicle(
    b: Blueprint, name: str, x: float, y: float, body: str, length=4.5, emergency=None
) -> None:
    b.box(name + "_lower_body", (x, y, 0.65), (2.0, length, 0.78), body, 0.16)
    b.box(
        name + "_upper_cabin",
        (x, y - length * 0.18, 1.25),
        (1.78, length * 0.46, 0.65),
        "White",
        0.12,
    )
    b.box(
        name + "_windshield",
        (x, y - length * 0.425, 1.30),
        (1.48, 0.05, 0.42),
        "Glass",
        0.025,
    )
    for sx in (-0.92, 0.92):
        for sy in (-length * 0.30, length * 0.30):
            b.cylinder(
                name + f"_wheel_{sx}_{sy}",
                (x + sx, y + sy, 0.42),
                0.36,
                0.24,
                "Black",
                32,
            )
    b.box(
        name + "_front_bumper",
        (x, y - length / 2 - 0.06, 0.47),
        (1.82, 0.13, 0.22),
        "Metal",
        0.025,
    )
    b.box(
        name + "_rear_bumper",
        (x, y + length / 2 + 0.06, 0.47),
        (1.82, 0.13, 0.22),
        "Metal",
        0.025,
    )
    if emergency:
        b.box(
            name + "_side_stripe",
            (x - 1.015, y, 0.86),
            (0.045, length * 0.83, 0.18),
            emergency,
            0.01,
        )
        b.box(
            name + "_lightbar",
            (x, y - length * 0.18, 1.64),
            (1.04, 0.22, 0.14),
            emergency,
            0.025,
        )


def add_common_context(b: Blueprint, scene_id: str) -> None:
    # Dense but restrained context around a deliberately clear central route.
    if scene_id != "riverside_lake_park":
        b.call(
            "road",
            "Context_Street",
            (0, 17.5, -0.05),
            (30, 4.6, 0.16),
            "Asphalt",
            "White",
        )
        for x in (-11.8, 11.8):
            b.box(
                f"Context_building_{x}_body",
                (x, 11.0, 2.4),
                (5.2, 5.6, 4.8),
                "Concrete",
                0.08,
            )
            for row in range(2):
                for col in range(2):
                    b.call(
                        "window",
                        f"Context_window_{x}_{row}_{col}",
                        (x - 1.25 + col * 2.5, 8.17, 1.45 + row * 1.75),
                        (1.45, 0.07, 1.12),
                        "Metal",
                        "Glass",
                    )
        for x, y in ((-8.3, 5.4), (8.4, 6.7), (-9.2, 14.2), (9.4, 14.8)):
            b.call(
                "tree",
                f"Context_tree_{x}_{y}",
                (x, y, 0),
                2.7,
                1.25,
                "DarkWood",
                "Green",
            )
        for x, y in ((-5.8, 4.0), (5.8, 4.0), (-6.7, 12.2), (6.7, 12.2)):
            b.call("lamp", f"Context_lamp_{x}_{y}", (x, y, 0), 3.1, "Metal", "Glow")
        add_bench(b, "Context_left_bench", -4.2, 7.2)
        add_bench(b, "Context_right_bench", 4.2, 9.6)
    for x in (-4.55, 4.55):
        b.call(
            "plant",
            f"Entrance_planter_{x}",
            (x, 0.75, 0),
            1.10,
            "Concrete",
            "LeafLight",
        )
    b.box("Facade_accent_band", (0, 0.12, 3.42), (11.4, 0.10, 0.16), "Primary", 0.02)
    for x in (-3.6, 3.6):
        b.call(
            "window",
            f"Facade_display_window_{x}",
            (x, 0.13, 1.72),
            (3.5, 0.06, 2.35),
            "Metal",
            "Glass",
        )


def add_residential(b: Blueprint) -> None:
    b.call("rug", "Living_room_rug", (-3.0, -5.4, 0.0), (4.2, 3.1), "Fabric")
    b.call(
        "sofa",
        "Sectional_sofa",
        (-4.0, -5.8, 0.0),
        90,
        (3.2, 1.0, 1.0),
        "LightWood",
        "Fabric",
    )
    b.call(
        "table",
        "Coffee_table",
        (-2.3, -5.2, 0.0),
        (1.45, 0.82, 0.50),
        "LightWood",
        "Metal",
    )
    b.call("chair", "Lounge_chair", (-2.0, -7.0, 0), 155, "LightWood", "Accent")
    b.call(
        "cabinet",
        "Media_console",
        (3.75, -7.8, 0),
        (3.2, 0.55, 0.72),
        "LightWood",
        "White",
        "Metal",
    )
    b.box("Television_panel", (3.75, -8.72, 1.75), (2.5, 0.08, 1.38), "Black", 0.04)
    b.call(
        "shelf",
        "Family_bookcase",
        (-4.65, -8.55, 0),
        (2.0, 0.48, 2.65),
        "LightWood",
        "Accent",
    )
    b.call(
        "table",
        "Dining_table",
        (3.55, -3.65, 0),
        (2.9, 1.35, 0.76),
        "LightWood",
        "DarkWood",
    )
    for i, (x, y, yaw) in enumerate(
        ((2.5, -3.0, 180), (4.5, -3.0, 180), (2.5, -4.3, 0), (4.5, -4.3, 0))
    ):
        b.call("chair", f"Dining_chair_{i}", (x, y, 0), yaw, "DarkWood", "Secondary")
    for x, y, h in ((-5.0, -1.2, 1.5), (5.0, -6.2, 1.25), (2.2, -1.2, 0.95)):
        b.call("plant", f"Houseplant_{x}_{y}", (x, y, 0), h, "Accent", "Green")
    for x in (-4.2, -2.4, 2.4, 4.2):
        b.call(
            "art",
            f"Family_art_{x}",
            (x, -8.82, 2.22),
            (1.1, 0.05, 0.78),
            "Accent",
            "DarkWood",
        )
    # Shared courtyard and neighboring residential balconies.
    for x in (-7.4, 7.4):
        b.box(f"Courtyard_balcony_{x}", (x, 8.0, 1.5), (4.2, 0.22, 0.18), "Metal", 0.02)
        for j in range(5):
            b.box(
                f"Courtyard_baluster_{x}_{j}",
                (x - 1.7 + j * 0.85, 8.0, 0.82),
                (0.06, 0.10, 1.3),
                "Metal",
                0.01,
            )
    b.call(
        "table",
        "Courtyard_table",
        (3.2, 6.7, 0),
        (1.4, 1.4, 0.74),
        "LightWood",
        "Metal",
    )
    for i, (x, y, yaw) in enumerate(
        ((2.0, 6.7, 90), (4.4, 6.7, -90), (3.2, 5.5, 0), (3.2, 7.9, 180))
    ):
        b.call("chair", f"Courtyard_chair_{i}", (x, y, 0), yaw, "Metal", "Accent")


def add_school(b: Blueprint) -> None:
    b.box("Teaching_whiteboard", (0, -8.80, 2.05), (5.3, 0.08, 1.25), "White", 0.03)
    b.box("Whiteboard_lower_rail", (0, -8.70, 1.38), (5.5, 0.12, 0.10), "Metal", 0.02)
    b.call(
        "table", "Teacher_desk", (-3.9, -7.4, 0), (2.4, 0.9, 0.78), "LightWood", "Metal"
    )
    b.call("chair", "Teacher_chair", (-4.5, -8.1, 0), 0, "Metal", "Accent")
    for row, y in enumerate((-2.0, -3.5, -5.0, -6.5)):
        for side, x in enumerate((-2.6, 2.6)):
            b.call(
                "table",
                f"Student_desk_{row}_{side}",
                (x, y, 0),
                (1.5, 0.72, 0.72),
                "LightWood",
                "Metal",
            )
            b.call(
                "chair",
                f"Student_chair_{row}_{side}",
                (x, y + 0.68, 0),
                180,
                "Metal",
                "Primary" if side else "Accent",
            )
            for item in range(2):
                b.box(
                    f"Workbook_{row}_{side}_{item}",
                    (x - 0.25 + item * 0.4, y, 0.78 + item * 0.015),
                    (0.32, 0.24, 0.035),
                    "Product",
                    0.012,
                )
    b.call(
        "shelf",
        "Classroom_cubbies_left",
        (-5.35, -4.6, 0),
        (0.72, 0.48, 2.4),
        "LightWood",
        "Secondary",
    )
    b.call(
        "cabinet",
        "Science_storage",
        (5.3, -6.7, 0),
        (0.85, 0.55, 2.4),
        "White",
        "Primary",
        "Metal",
    )
    b.call("rug", "Reading_corner_rug", (-4.2, -1.6, 0), (2.6, 2.1), "Secondary")
    for x in (-4.8, -3.7):
        b.call(
            "chair",
            f"Reading_corner_chair_{x}",
            (x, -1.6, 0),
            90,
            "LightWood",
            "Accent",
        )
    # Campus forecourt and small multi-use playground.
    b.box("Playground_court", (0, 9.1, 0.01), (11.2, 7.2, 0.04), "Blue", 0.01)
    for x in (-4.7, 4.7):
        b.box(
            f"Court_side_line_{x}", (x, 9.1, 0.045), (0.05, 6.3, 0.025), "White", 0.002
        )
    for y in (6.0, 12.2):
        hoop_x = -3.6 if y < 9 else 3.6
        b.box(f"Court_end_line_{y}", (0, y, 0.045), (9.4, 0.05, 0.025), "White", 0.002)
        b.box(
            f"Basketball_post_{y}", (hoop_x, y, 1.55), (0.12, 0.12, 3.1), "Metal", 0.02
        )
        b.box(
            f"Basketball_backboard_{y}",
            (hoop_x, y + (-0.26 if y > 9 else 0.26), 2.75),
            (1.65, 0.08, 1.05),
            "White",
            0.02,
        )
        b.cylinder(
            f"Basketball_ring_{y}",
            (hoop_x, y + (-0.38 if y > 9 else 0.38), 2.46),
            0.32,
            0.055,
            "Red",
            32,
        )


def add_library(b: Blueprint) -> None:
    for x in (-5.15, 5.15):
        for y in (-7.3, -4.7, -2.1):
            b.call(
                "shelf",
                f"Library_stack_{x}_{y}",
                (x, y, 0),
                (1.25, 0.58, 2.75),
                "DarkWood",
                "Accent",
            )
    b.call(
        "shelf",
        "Library_feature_stack",
        (-2.8, -8.55, 0),
        (2.2, 0.48, 2.7),
        "DarkWood",
        "Secondary",
    )
    b.call(
        "counter",
        "Circulation_counter",
        (3.7, -7.65, 0),
        (3.2, 0.78, 1.04),
        "DarkWood",
        "LightWood",
        "Primary",
        "Metal",
    )
    for row, y in enumerate((-2.6, -5.3)):
        table_x = -3.05 if row == 0 else 3.05
        b.call(
            "table",
            f"Reading_table_{row}",
            (table_x, y, 0),
            (3.5, 1.25, 0.75),
            "LightWood",
            "DarkWood",
        )
        for i, (x, dy, yaw) in enumerate(
            ((-1.15, -0.86, 0), (1.15, -0.86, 0), (-1.15, 0.86, 180), (1.15, 0.86, 180))
        ):
            b.call(
                "chair",
                f"Reading_chair_{row}_{i}",
                (table_x + x, y + dy, 0),
                yaw,
                "DarkWood",
                "Secondary",
            )
        for i, x in enumerate((-0.9, 0, 0.9)):
            b.box(
                f"Reading_books_{row}_{i}",
                (table_x + x, y, 0.81 + i * 0.012),
                (0.42, 0.30, 0.06),
                "Accent",
                0.012,
            )
    b.call(
        "display_unit",
        "New_arrivals_display",
        (-3.7, -1.0, 0),
        (2.3, 0.65, 2.1),
        "LightWood",
        "Product",
        "Accent",
    )
    b.call("plant", "Library_fig_tree", (4.9, -1.2, 0), 1.65, "Concrete", "Green")
    # Reading plaza.
    for x in (-4.8, 4.8):
        add_bench(b, f"Plaza_reading_bench_{x}", x, 6.6)
        b.call(
            "plant", f"Plaza_planter_{x}", (x, 4.3, 0), 1.25, "Concrete", "LeafLight"
        )
    b.call(
        "cabinet",
        "Exterior_book_return",
        (-3.25, 1.0, 0),
        (1.0, 0.55, 1.25),
        "Primary",
        "Accent",
        "Metal",
    )
    b.box("Book_return_slot", (-3.25, 0.68, 0.87), (0.62, 0.04, 0.16), "Black", 0.01)


def add_sports_hall(b: Blueprint) -> None:
    b.box(
        "Indoor_court_surface", (0, -4.55, 0.02), (11.3, 8.3, 0.035), "Primary", 0.008
    )
    b.box("Indoor_center_line", (0, -4.55, 0.045), (0.045, 8.0, 0.018), "White", 0.002)
    b.cylinder("Indoor_center_circle", (0, -4.55, 0.064), 0.85, 0.022, "Accent", 48)
    for y in (-7.85, -1.25):
        hoop_x = -3.6 if y < -4 else 3.6
        b.box(
            f"Indoor_hoop_post_{y}", (hoop_x, y, 1.55), (0.12, 0.12, 3.0), "Metal", 0.02
        )
        b.box(
            f"Indoor_backboard_{y}",
            (hoop_x, y + (0.28 if y < -4 else -0.28), 2.72),
            (1.6, 0.08, 1.0),
            "White",
            0.02,
        )
        b.cylinder(
            f"Indoor_ring_{y}",
            (hoop_x, y + (0.42 if y < -4 else -0.42), 2.42),
            0.31,
            0.05,
            "Red",
            40,
        )
    for x in (-5.25, 5.25):
        for level in range(3):
            b.box(
                f"Bleacher_{x}_{level}_seat",
                (x, -5.0 + level * 0.18, 0.28 + level * 0.30),
                (1.0, 5.8, 0.13),
                "LightWood",
                0.025,
            )
            b.box(
                f"Bleacher_{x}_{level}_base",
                (x, -5.0 + level * 0.18, 0.14 + level * 0.30),
                (0.82, 5.6, 0.28 + level * 0.30),
                "Metal",
                0.015,
            )
    b.call(
        "cabinet",
        "Sports_equipment_locker",
        (-4.6, -8.55, 0),
        (2.0, 0.48, 2.6),
        "Metal",
        "Accent",
        "Black",
    )
    for i in range(8):
        b.call(
            "sphere",
            f"Sports_ball_{i}",
            (-5.0 + (i % 2) * 0.55, -1.4 - (i // 2) * 0.48, 0.25),
            (0.20, 0.20, 0.20),
            "Accent",
            24,
        )
    b.call("rug", "Training_mat_left", (-3.0, -2.3, 0), (2.0, 1.2), "Secondary")
    b.call("rug", "Training_mat_right", (3.0, -2.3, 0), (2.0, 1.2), "Secondary")
    # Outdoor half court.
    b.box("Outdoor_half_court", (0, 8.5, 0.015), (10.5, 7.0, 0.035), "Secondary", 0.008)
    for x in (-4.8, 4.8):
        add_bench(b, f"Team_bench_{x}", x, 12.5, "Primary")


def add_pharmacy(b: Blueprint) -> None:
    for x in (-4.75, 4.75):
        for y in (-6.8, -4.4, -2.0):
            b.call(
                "display_unit",
                f"Pharmacy_aisle_{x}_{y}",
                (x, y, 0),
                (1.65, 0.65, 2.15),
                "White",
                "Product",
                "Accent",
            )
    b.call(
        "counter",
        "Pharmacy_checkout",
        (-3.25, -7.7, 0),
        (3.5, 0.82, 1.02),
        "White",
        "LightWood",
        "Primary",
        "Metal",
    )
    b.call(
        "counter",
        "Prescription_counter",
        (3.2, -7.7, 0),
        (3.8, 0.82, 1.12),
        "White",
        "LightWood",
        "Accent",
        "Metal",
    )
    b.call(
        "cabinet",
        "Medicine_cabinet_left",
        (4.9, -8.48, 0),
        (1.45, 0.48, 2.75),
        "White",
        "Glass",
        "Metal",
    )
    b.call(
        "appliance",
        "Cold_medicine_fridge",
        (-5.15, -8.4, 0),
        (1.25, 0.58, 2.45),
        "White",
        "Glass",
        "Metal",
    )
    b.call(
        "table",
        "Consultation_table",
        (2.9, -2.0, 0),
        (1.8, 0.9, 0.74),
        "LightWood",
        "Metal",
    )
    for i, (x, y, yaw) in enumerate(((2.2, -1.3, 180), (3.6, -1.3, 180))):
        b.call("chair", f"Consultation_chair_{i}", (x, y, 0), yaw, "Metal", "Secondary")
    for i, x in enumerate((-4.5, -3.2, -1.9)):
        b.call(
            "chair", f"Pharmacy_waiting_chair_{i}", (x, -1.0, 0), 0, "Metal", "Accent"
        )
    b.call(
        "display_unit",
        "Sidewalk_health_display",
        (-3.8, 2.0, 0),
        (2.0, 0.65, 1.8),
        "White",
        "Product",
        "Primary",
    )
    b.box("Pharmacy_awning", (0, 1.25, 3.25), (8.8, 2.2, 0.16), "Primary", 0.05)


def add_police(b: Blueprint) -> None:
    b.call(
        "counter",
        "Public_reception_counter",
        (-3.6, -6.8, 0),
        (3.8, 0.85, 1.08),
        "White",
        "Concrete",
        "Blue",
        "Metal",
    )
    b.call(
        "cabinet",
        "Secure_file_cabinet",
        (-5.2, -8.35, 0),
        (1.25, 0.55, 2.55),
        "Metal",
        "Blue",
        "Black",
    )
    b.call(
        "shelf",
        "Case_file_shelf",
        (4.9, -8.45, 0),
        (1.55, 0.50, 2.55),
        "Metal",
        "Accent",
    )
    for index, (x, y) in enumerate(((-3.8, -3.9), (3.8, -5.7), (3.8, -3.0))):
        b.call(
            "table",
            f"Officer_workstation_{index}",
            (x, y, 0),
            (2.5, 1.05, 0.76),
            "LightWood",
            "Metal",
        )
        b.call(
            "chair", f"Officer_chair_{index}", (x, y + 0.82, 0), 180, "Metal", "Blue"
        )
        b.box(f"Monitor_{index}", (x, y - 0.2, 1.18), (0.72, 0.10, 0.52), "Black", 0.03)
        b.box(
            f"Keyboard_{index}",
            (x, y + 0.12, 0.81),
            (0.62, 0.25, 0.035),
            "Black",
            0.015,
        )
    for i, x in enumerate((-4.5, -3.1, -1.7)):
        b.call("chair", f"Public_wait_chair_{i}", (x, -1.25, 0), 0, "Metal", "Accent")
    for i, x in enumerate((-3.6, -1.8, 0, 1.8, 3.6)):
        b.call(
            "art",
            f"Incident_map_panel_{i}",
            (x, -8.78, 2.25),
            (1.25, 0.05, 0.82),
            "Secondary" if i % 2 else "Blue",
            "Metal",
        )
    add_vehicle(b, "Patrol_vehicle", -3.8, 7.3, "White", 4.6, "Blue")
    for x in (-1.5, 1.5, 4.5):
        b.cylinder(f"Forecourt_bollard_{x}", (x, 3.2, 0.48), 0.10, 0.96, "Metal", 28)


def add_fire_station(b: Blueprint) -> None:
    # Turnout gear and workshop zone surround the clear egress aisle.
    for side, x in enumerate((-5.15, 5.15)):
        for j, y in enumerate((-7.6, -6.1, -4.6, -3.1)):
            b.call(
                "cabinet",
                f"Turnout_locker_{side}_{j}",
                (x, y, 0),
                (1.15, 0.58, 2.55),
                "Metal",
                "Red",
                "Black",
            )
            b.box(
                f"Helmet_{side}_{j}",
                (x, y - 0.36, 2.22),
                (0.54, 0.36, 0.28),
                "Yellow",
                0.14,
            )
    b.call(
        "table",
        "Equipment_service_bench",
        (-3.2, -1.45, 0),
        (3.0, 1.05, 0.82),
        "Metal",
        "Black",
    )
    for i in range(6):
        b.cylinder(
            f"Hose_roll_{i}",
            (-4.15 + (i % 3) * 0.9, -1.4, 1.02 + (i // 3) * 0.52),
            0.34,
            0.16,
            "Yellow",
            40,
        )
    b.call(
        "shelf",
        "Breathing_apparatus_rack",
        (3.8, -8.45, 0),
        (3.1, 0.52, 2.6),
        "Metal",
        "Yellow",
    )
    for i, x in enumerate((-3.6, -2.4, 2.4, 3.6)):
        b.cylinder(f"Overhead_pipe_{i}", (x, -5.0, 3.25), 0.055, 7.0, "Steel", 24)
    add_vehicle(b, "Fire_engine", 3.9, 8.0, "Red", 5.8, "Yellow")
    b.box(
        "Fire_engine_equipment_body", (3.9, 8.75, 1.45), (1.92, 2.6, 1.35), "Red", 0.10
    )
    for j in range(4):
        b.box(
            f"Engine_side_compartment_{j}",
            (2.91, 7.9 + j * 0.56, 1.38),
            (0.04, 0.45, 0.55),
            "Steel",
            0.02,
        )
    b.box(
        "Station_forecourt_apron",
        (0, 7.7, 0.018),
        (12.0, 11.0, 0.04),
        "Concrete",
        0.008,
    )


def add_hospital(b: Blueprint) -> None:
    b.call(
        "counter",
        "Hospital_reception",
        (-3.4, -7.25, 0),
        (4.1, 0.9, 1.08),
        "White",
        "Concrete",
        "Accent",
        "Metal",
    )
    for i, (x, y) in enumerate(((-3.8, -4.9), (3.8, -5.5), (3.8, -2.8))):
        b.call(
            "table",
            f"Clinical_workstation_{i}",
            (x, y, 0),
            (2.15, 0.95, 0.76),
            "White",
            "Metal",
        )
        b.call(
            "chair", f"Clinical_chair_{i}", (x, y + 0.76, 0), 180, "Metal", "Secondary"
        )
        b.box(
            f"Clinical_monitor_{i}",
            (x, y - 0.20, 1.18),
            (0.65, 0.11, 0.50),
            "Black",
            0.025,
        )
    for i, x in enumerate((-4.8, -3.4, -2.0, 2.0, 3.4, 4.8)):
        b.call("chair", f"Waiting_seat_{i}", (x, -1.25, 0), 0, "Metal", "Primary")
    for side, x in enumerate((-4.7, 4.7)):
        b.box(f"Exam_bed_{side}", (x, -7.7, 0.72), (1.7, 0.78, 0.26), "White", 0.10)
        b.box(
            f"Exam_bed_mattress_{side}",
            (x, -7.7, 0.91),
            (1.58, 0.70, 0.14),
            "Secondary",
            0.08,
        )
        b.call(
            "cabinet",
            f"Medical_storage_{side}",
            (x, -8.45, 0),
            (1.35, 0.48, 2.3),
            "White",
            "Glass",
            "Metal",
        )
    b.call(
        "appliance",
        "Medicine_refrigerator",
        (5.2, -4.1, 0),
        (1.15, 0.58, 2.25),
        "White",
        "Glass",
        "Metal",
    )
    for i, x in enumerate((-3.8, -2.3, 2.3, 3.8)):
        b.call(
            "art",
            f"Wayfinding_color_panel_{i}",
            (x, -8.80, 2.35),
            (1.05, 0.05, 0.75),
            "Accent" if i % 2 else "Primary",
            "White",
        )
    add_vehicle(b, "Ambulance", -3.8, 7.8, "White", 5.3, "Red")
    b.box("Emergency_dropoff_canopy", (0, 5.2, 3.35), (10.5, 5.4, 0.20), "White", 0.04)
    for x in (-4.7, 4.7):
        b.box(f"Canopy_column_{x}", (x, 5.2, 1.68), (0.20, 0.20, 3.35), "Steel", 0.02)


def add_factory(b: Blueprint) -> None:
    for i, (x, y) in enumerate(((-4.2, -7.2), (4.2, -7.2), (-4.2, -4.4), (4.2, -4.4))):
        b.box(f"Machine_base_{i}", (x, y, 0.62), (2.4, 1.45, 1.24), "Metal", 0.10)
        b.box(
            f"Machine_control_{i}",
            (x, y - 0.77, 1.45),
            (0.85, 0.22, 0.78),
            "Accent",
            0.04,
        )
        for j in range(3):
            b.cylinder(
                f"Machine_dial_{i}_{j}",
                (x - 0.25 + j * 0.25, y - 0.91, 1.48),
                0.07,
                0.035,
                "Yellow" if j == 1 else "Black",
                24,
            )
    b.call(
        "table",
        "Assembly_bench_left",
        (-3.5, -1.65, 0),
        (3.4, 1.0, 0.86),
        "Steel",
        "Metal",
    )
    b.call(
        "table",
        "Assembly_bench_right",
        (3.5, -1.65, 0),
        (3.4, 1.0, 0.86),
        "Steel",
        "Metal",
    )
    for x in (-5.2, 5.2):
        b.call(
            "shelf",
            f"Parts_rack_{x}",
            (x, -5.7, 0),
            (1.1, 0.62, 2.75),
            "Metal",
            "Product",
        )
    for i, x in enumerate((-4.2, -2.8, 2.8, 4.2)):
        b.cylinder(
            f"Factory_service_pipe_{i}", (x, -5.0, 3.28), 0.065, 7.0, "Accent", 24
        )
    # Loading apron, pallets and forklift silhouette.
    for stack, (x, y) in enumerate(((-4.6, 5.0), (-4.6, 7.2), (4.8, 11.5))):
        for level in range(3):
            b.box(
                f"Pallet_stack_{stack}_{level}",
                (x, y, 0.16 + level * 0.34),
                (2.1, 1.2, 0.18),
                "LightWood",
                0.025,
            )
            for parcel in range(3):
                b.box(
                    f"Pallet_carton_{stack}_{level}_{parcel}",
                    (x - 0.65 + parcel * 0.65, y, 0.36 + level * 0.34),
                    (0.55, 0.75, 0.34),
                    "Product",
                    0.035,
                )
    b.box("Forklift_body", (3.4, 6.2, 0.65), (1.55, 2.2, 0.9), "Yellow", 0.10)
    b.box("Forklift_mast", (3.4, 5.0, 1.55), (1.25, 0.18, 2.7), "Metal", 0.025)
    for x in (3.0, 3.8):
        b.box(f"Forklift_fork_{x}", (x, 4.25, 0.18), (0.18, 1.7, 0.12), "Metal", 0.018)


def add_delivery(b: Blueprint) -> None:
    b.call(
        "counter",
        "Parcel_service_counter",
        (-3.6, -7.2, 0),
        (3.8, 0.9, 1.05),
        "LightWood",
        "White",
        "Primary",
        "Metal",
    )
    for x in (-5.15, 5.15):
        for y in (-7.2, -4.7, -2.2):
            b.call(
                "shelf",
                f"Sorting_rack_{x}_{y}",
                (x, y, 0),
                (1.20, 0.65, 2.65),
                "Metal",
                "Product",
            )
    for row, y in enumerate((-5.9, -4.4, -2.9, -1.4)):
        for side, x in enumerate((-3.2, 3.2)):
            for j in range(3):
                b.box(
                    f"Sorted_parcel_{row}_{side}_{j}",
                    (x - 0.55 + j * 0.55, y, 0.28 + 0.22 * (j % 2)),
                    (0.46, 0.62, 0.48 + 0.18 * (j % 2)),
                    "Product" if j % 2 else "Accent",
                    0.045,
                )
    b.call("table", "Packing_table", (3.5, -7.4, 0), (3.1, 1.0, 0.84), "Steel", "Metal")
    b.box(
        "Packing_tape_dispenser", (3.4, -7.3, 0.98), (0.34, 0.20, 0.20), "Primary", 0.06
    )
    # Parcel and takeaway lockers flank the entrance but leave it visible.
    for side, x in enumerate((-4.2, 4.2)):
        material = "Primary" if side == 0 else "Accent"
        for row in range(4):
            for col in range(4):
                px = x - 1.18 + col * 0.78
                pz = 0.38 + row * 0.58
                b.box(
                    f"Exterior_locker_{side}_{row}_{col}",
                    (px, 2.25, pz),
                    (0.70, 0.60, 0.50),
                    material,
                    0.025,
                )
                b.cylinder(
                    f"Locker_handle_{side}_{row}_{col}",
                    (px + 0.23, 1.93, pz),
                    0.025,
                    0.05,
                    "Metal",
                    20,
                )
        b.box(f"Locker_canopy_{side}", (x, 2.35, 2.95), (3.6, 1.0, 0.16), "Metal", 0.03)
    add_vehicle(b, "Delivery_van", 5.0, 9.4, "White", 5.0, "Primary")


def add_bank(b: Blueprint) -> None:
    for index, x in enumerate((-4.2, -2.4, 2.4, 4.2)):
        b.call(
            "counter",
            f"Teller_counter_{index}",
            (x, -7.4, 0),
            (1.5, 0.82, 1.10),
            "DarkWood",
            "Concrete",
            "Primary",
            "Metal",
        )
        b.box(
            f"Teller_screen_{index}",
            (x, -7.82, 1.62),
            (1.28, 0.05, 0.84),
            "Glass",
            0.015,
        )
    for index, (x, y) in enumerate(((-3.8, -4.2), (3.8, -4.2))):
        b.call(
            "table",
            f"Advisor_desk_{index}",
            (x, y, 0),
            (2.4, 1.05, 0.76),
            "LightWood",
            "Metal",
        )
        b.call(
            "chair", f"Advisor_chair_{index}", (x, y + 0.82, 0), 180, "Metal", "Accent"
        )
        b.call(
            "chair", f"Client_chair_{index}", (x, y - 0.82, 0), 0, "Metal", "Secondary"
        )
    for i, x in enumerate((-4.5, -3.0, -1.5, 1.5, 3.0, 4.5)):
        b.call("chair", f"Bank_wait_seat_{i}", (x, -1.25, 0), 0, "Metal", "Secondary")
    b.box("Vault_surround", (0, -8.72, 1.65), (2.6, 0.18, 3.0), "Steel", 0.10)
    b.cylinder("Vault_door", (0, -8.57, 1.65), 1.05, 0.22, "Metal", 48)
    b.cylinder("Vault_wheel", (0, -8.42, 1.65), 0.42, 0.10, "Accent", 40)
    # Exterior ATM wall with layered bezel, screen, keypad and cash slot.
    for side, x in enumerate((-3.8, 3.8)):
        b.box(f"ATM_body_{side}", (x, 1.05, 1.05), (1.15, 0.68, 1.95), "Primary", 0.08)
        b.box(f"ATM_screen_{side}", (x, 0.69, 1.45), (0.72, 0.05, 0.48), "Black", 0.025)
        b.box(f"ATM_keypad_{side}", (x, 0.65, 0.98), (0.60, 0.08, 0.30), "Steel", 0.025)
        b.box(
            f"ATM_cash_slot_{side}", (x, 0.63, 0.65), (0.60, 0.08, 0.10), "Black", 0.012
        )
        b.box(f"ATM_canopy_{side}", (x, 1.10, 2.32), (1.65, 1.1, 0.14), "Accent", 0.035)


def add_gas_station(b: Blueprint) -> None:
    for x in (-4.75, 4.75):
        for y in (-6.8, -4.2, -1.7):
            b.call(
                "display_unit",
                f"Convenience_aisle_{x}_{y}",
                (x, y, 0),
                (1.55, 0.68, 2.1),
                "White",
                "Product",
                "Accent",
            )
    b.call(
        "counter",
        "Store_checkout",
        (-3.4, -7.6, 0),
        (3.8, 0.90, 1.04),
        "White",
        "Steel",
        "Primary",
        "Metal",
    )
    b.call(
        "appliance",
        "Drink_cooler_left",
        (4.35, -8.4, 0),
        (1.45, 0.58, 2.45),
        "White",
        "Glass",
        "Metal",
    )
    b.call(
        "appliance",
        "Drink_cooler_right",
        (5.35, -8.4, 0),
        (1.45, 0.58, 2.45),
        "White",
        "Glass",
        "Metal",
    )
    b.call(
        "display_unit",
        "Impulse_display",
        (2.7, -7.5, 0),
        (1.3, 0.55, 1.5),
        "White",
        "Product",
        "Yellow",
    )
    # Pump canopy and two islands behind a clear entrance apron.
    b.box("Fuel_canopy_roof", (0, 9.0, 4.1), (14.0, 8.0, 0.30), "White", 0.06)
    b.box(
        "Fuel_canopy_color_band", (0, 5.08, 3.86), (14.0, 0.18, 0.38), "Primary", 0.02
    )
    for x in (-5.8, 5.8):
        for y in (6.0, 12.0):
            b.box(
                f"Canopy_column_{x}_{y}",
                (x, y, 2.02),
                (0.28, 0.28, 4.05),
                "Steel",
                0.03,
            )
    for index, x in enumerate((-3.4, 3.4)):
        b.box(
            f"Pump_island_{index}", (x, 9.0, 0.12), (2.2, 4.2, 0.24), "Concrete", 0.06
        )
        b.box(f"Fuel_pump_{index}", (x, 9.0, 1.25), (1.2, 0.75, 2.15), "White", 0.09)
        b.box(
            f"Pump_screen_{index}", (x, 8.60, 1.68), (0.68, 0.05, 0.45), "Black", 0.02
        )
        for side in (-0.76, 0.76):
            b.cylinder(
                f"Pump_hose_{index}_{side}",
                (x + side, 9.0, 1.30),
                0.035,
                1.35,
                "Black",
                24,
            )
    add_vehicle(b, "Customer_car", -6.0, 9.0, "Accent", 4.4)


def add_park(b: Blueprint) -> None:
    # Visitor-center interior.
    b.call(
        "counter",
        "Park_information_counter",
        (-3.6, -7.3, 0),
        (3.8, 0.86, 1.02),
        "LightWood",
        "Concrete",
        "Primary",
        "Metal",
    )
    b.call(
        "display_unit",
        "Nature_exhibit_left",
        (-4.8, -4.5, 0),
        (1.55, 0.65, 2.3),
        "DarkWood",
        "Green",
        "Accent",
    )
    b.call(
        "display_unit",
        "Nature_exhibit_right",
        (4.8, -4.5, 0),
        (1.55, 0.65, 2.3),
        "DarkWood",
        "Green",
        "Accent",
    )
    b.call(
        "table",
        "Visitor_reading_table",
        (3.25, -5.1, 0),
        (3.0, 1.2, 0.75),
        "LightWood",
        "DarkWood",
    )
    for i, (x, y, yaw) in enumerate(
        ((2.15, -4.25, 180), (4.35, -4.25, 180), (2.15, -5.95, 0), (4.35, -5.95, 0))
    ):
        b.call("chair", f"Visitor_chair_{i}", (x, y, 0), yaw, "DarkWood", "Secondary")
    b.call(
        "sofa",
        "Park_lounge_bench",
        (-3.9, -2.0, 0),
        90,
        (2.5, 0.85, 0.85),
        "LightWood",
        "Secondary",
    )
    b.call(
        "shelf",
        "Field_guide_shelf",
        (4.8, -7.8, 0),
        (1.5, 0.48, 2.4),
        "LightWood",
        "Accent",
    )
    for x, y, h in ((-5.0, -8.0, 1.3), (4.7, -1.2, 1.5), (-4.6, -5.5, 1.0)):
        b.call(
            "plant",
            f"Visitor_center_plant_{x}_{y}",
            (x, y, 0),
            h,
            "Concrete",
            "LeafLight",
        )
    # Lake and river remain shallow physical 3D surfaces surrounded by banks.
    b.box("Park_lawn", (0, 10.0, -0.06), (30, 20, 0.18), "Green", 0.02)
    b.box("Lake_water", (6.3, 12.2, 0.02), (11.0, 10.5, 0.08), "Water", 0.10)
    b.box("River_water", (-3.6, 10.8, 0.025), (4.0, 16.5, 0.09), "Water", 0.10)
    b.box(
        "Riverside_path_left", (-7.5, 10.0, 0.04), (3.5, 18.0, 0.10), "Concrete", 0.02
    )
    b.box("Lakeside_path", (6.4, 5.7, 0.045), (11.5, 2.0, 0.10), "Concrete", 0.02)
    # Footbridge crosses the river without blocking the entrance sightline.
    for j in range(11):
        b.box(
            f"Footbridge_plank_{j}",
            (-5.4 + j * 0.36, 8.5, 0.36),
            (0.32, 2.4, 0.16),
            "LightWood",
            0.025,
        )
    for x in (-5.6, -1.6):
        b.box(
            f"Bridge_rail_post_{x}", (x, 8.5, 0.92), (0.10, 2.5, 1.15), "DarkWood", 0.02
        )
    for x, y in (
        (-9.0, 4.0),
        (-9.5, 9.5),
        (-8.7, 15.5),
        (10.8, 5.5),
        (11.6, 16.0),
        (0.8, 17.0),
    ):
        b.call("tree", f"Park_tree_{x}_{y}", (x, y, 0), 3.4, 1.55, "DarkWood", "Green")
    for x, y in ((-8.0, 6.0), (-8.0, 13.5), (2.0, 5.2), (9.0, 6.0)):
        add_bench(b, f"Park_bench_{x}_{y}", x, y)
    for x, y in ((2.0, 10.0), (4.0, 14.0), (8.0, 9.0), (9.5, 15.5)):
        b.call(
            "sphere",
            f"Lake_rock_{x}_{y}",
            (x, y, 0.22),
            (0.55, 0.42, 0.30),
            "Concrete",
            24,
        )


BUILDERS = {
    "residential_neighborhood": add_residential,
    "neighborhood_school": add_school,
    "public_library": add_library,
    "community_sports_hall": add_sports_hall,
    "retail_pharmacy": add_pharmacy,
    "police_station": add_police,
    "fire_station": add_fire_station,
    "community_hospital": add_hospital,
    "light_factory": add_factory,
    "delivery_service_hub": add_delivery,
    "community_bank_atm": add_bank,
    "gas_station_store": add_gas_station,
    "riverside_lake_park": add_park,
}


def build_source(scene_id: str, title: str, categories: list[str]) -> tuple[str, int]:
    b = Blueprint()
    add_materials(b, scene_id)
    add_common_context(b, scene_id)
    BUILDERS[scene_id](b)
    # Interior lighting fixtures are explicit semantic geometry; real lights
    # are added by the rendering harness.
    for row, y in enumerate((-2.1, -4.8, -7.5)):
        for col, x in enumerate((-3.6, -1.2, 1.2, 3.6)):
            b.call(
                "ceiling_light",
                f"Interior_fixture_{row}_{col}",
                (x, y, 3.49),
                0.10,
                "Metal",
                "Glow",
                115,
            )
    spec = {
        "scene_id": scene_id,
        "title_zh": title,
        "categories_zh": categories,
        "concept": "small-scale, high-detail, physically connected indoor/outdoor civic scene",
        "entrance_clear_width_m": 2.2,
        "interior_detail_level": "high",
        "true_3d": True,
        "shared_coordinate_frame": True,
        "object_intent": [
            "architectural shell",
            "semantic interior",
            "open threshold",
            "exterior context",
            *categories,
        ],
    }
    source = (
        "# Generated by GPT-6 Astra with reasoning_effort=high.\n"
        "# True procedural 3D; no external assets or image textures.\n"
        f"SCENE_SPEC = {spec!r}\n\n"
        "def build_scene(api):\n" + "\n".join(b.lines) + "\n"
    )
    compile(source, f"<{scene_id}>", "exec")
    return source, b.calls


def prompt_for(scene_id: str, title: str, categories: list[str]) -> str:
    return f"""GPT-6 Astra high procedural 3D scene generation request
scene_id: {scene_id}
title: {title}
categories: {', '.join(categories)}
Build a fine-grained, small-scale true Blender 3D scene with one shared indoor/outdoor
coordinate frame, a flush 2.2 m open doorway, a clear walking/camera path, detailed
semantic interior furniture and recognizable exterior context. Include foreground,
midground and background geometry. Avoid text, logos, downloads and external assets.
The result must support indoor-only, outdoor-only, indoor-to-outdoor and
outdoor-to-indoor near/mid/far/oblique renders plus a bidirectional traversal video.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--scene", action="append", default=[])
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(BASELINES.resolve())
    wanted = set(args.scene)
    selected = [row for row in SCENES if not wanted or row[0] in wanted]
    unknown = wanted - {row[0] for row in SCENES}
    if unknown:
        raise ValueError(f"unknown scene ids: {sorted(unknown)}")
    output.mkdir(parents=True, exist_ok=True)
    index = []
    for scene_id, title, categories in selected:
        root = output / scene_id
        source_path = root / "source/generated.py"
        manifest_path = root / "generation_manifest.json"
        prompt = prompt_for(scene_id, title, list(categories))
        source, calls = build_source(scene_id, title, list(categories))
        prompt_hash = sha256_bytes(prompt.encode("utf-8"))
        source_hash = sha256_bytes(source.encode("utf-8"))
        reused = False
        if not args.force and source_path.is_file() and manifest_path.is_file():
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            reused = (
                old.get("generation_success") is True
                and old.get("prompt_sha256") == prompt_hash
                and sha256(source_path)
                == old.get("generated_code_sha256")
                == source_hash
            )
        if not reused:
            atomic_text(root / "input/prompt.txt", prompt)
            atomic_text(source_path, source)
            manifest = {
                "schema_version": 1,
                "generation_success": True,
                "method": "gpt6_astra",
                "model_requested": "gpt-6-astra",
                "reasoning_effort_requested": "high",
                "provider": "openai_codex",
                "generation_mode": "in_session_model_authored_procedural_blueprint",
                "scene_id": scene_id,
                "title_zh": title,
                "categories_zh": list(categories),
                "prompt_sha256": prompt_hash,
                "generated_code_sha256": source_hash,
                "high_level_api_calls": calls,
                "generated_at_utc": utc(),
                "external_assets": False,
                "downloads": False,
            }
            atomic_json(manifest_path, manifest)
            print(
                f"ASTRA_CONNECT2_GENERATED scene={scene_id} calls={calls}", flush=True
            )
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            print(f"ASTRA_CONNECT2_REUSED scene={scene_id}", flush=True)
        index.append(
            {"scene_id": scene_id, "title_zh": title, "categories_zh": list(categories)}
        )
    atomic_json(
        output / "scene_index.json",
        {"method": "gpt6_astra", "reasoning_effort": "high", "scenes": index},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
