#!/usr/bin/env python3
"""Build one high-detail GPT-6 Astra connect3 scene in Blender."""
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
import math
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
from baselines.methods.gpt.tools.gpt_connect3_core import ASSET_LIBRARY
from baselines.methods.gpt.tools.gpt_connect3_core import Geo
from baselines.methods.gpt.tools.gpt_connect3_core import add_architectural_details
from baselines.methods.gpt.tools.gpt_connect3_core import add_context
from baselines.methods.gpt.tools.gpt_connect3_core import add_world_and_lights
from baselines.methods.gpt.tools.gpt_connect3_core import audit_connection
from baselines.methods.gpt.tools.gpt_connect3_core import build_shell
from baselines.methods.gpt.tools.gpt_connect3_core import clear_scene
from baselines.methods.gpt.tools.gpt_connect3_core import create_materials


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gpt6_astra/connect3"

SCENES = {
    "residential_neighborhood": {
        "title": "Fine residence: Living room with shared courtyard",
        "categories": ["residential area"],
        "seed": 63101,
        "style": "pitched",
        "floor": "wood",
        "canopy": "slatted",
        "palette": {
            "plaster": (0.76, 0.71, 0.62),
            "facade": (0.24, 0.15, 0.09),
            "primary": (0.22, 0.42, 0.52),
            "secondary": (0.64, 0.70, 0.55),
            "fabric": (0.53, 0.60, 0.57),
        },
    },
    "neighborhood_school": {
        "title": "Fine Community School and Campus Front Area",
        "categories": ["school"],
        "seed": 63102,
        "style": "flat",
        "floor": "wood",
        "canopy": "solid",
        "palette": {
            "plaster": (0.80, 0.77, 0.66),
            "facade": (0.68, 0.34, 0.06),
            "primary": (0.06, 0.34, 0.62),
            "secondary": (0.88, 0.58, 0.10),
            "fabric": (0.25, 0.47, 0.62),
        },
    },
    "public_library": {
        "title": "Fine Public Library and Reading Square",
        "categories": ["library"],
        "seed": 63103,
        "style": "pitched",
        "floor": "wood",
        "canopy": "slatted",
        "palette": {
            "plaster": (0.67, 0.60, 0.49),
            "facade": (0.075, 0.22, 0.20),
            "primary": (0.40, 0.16, 0.07),
            "secondary": (0.55, 0.11, 0.08),
            "fabric": (0.14, 0.31, 0.27),
        },
    },
    "community_sports_hall": {
        "title": "Fine Community Gymnasium with Outdoor Court",
        "categories": ["gymnasium"],
        "seed": 63104,
        "style": "industrial",
        "floor": "wood",
        "canopy": "solid",
        "palette": {
            "plaster": (0.68, 0.70, 0.69),
            "facade": (0.035, 0.20, 0.46),
            "primary": (0.04, 0.34, 0.68),
            "secondary": (0.86, 0.26, 0.045),
            "fabric": (0.08, 0.45, 0.40),
        },
    },
    "retail_pharmacy": {
        "title": "Fine Community Pharmacy Shop and Pedestrian Street",
        "categories": ["shop", "pharmacy"],
        "seed": 63105,
        "style": "flat",
        "floor": "stone",
        "canopy": "glass",
        "palette": {
            "plaster": (0.84, 0.86, 0.82),
            "facade": (0.06, 0.43, 0.33),
            "primary": (0.05, 0.54, 0.42),
            "secondary": (0.18, 0.38, 0.64),
            "fabric": (0.36, 0.60, 0.54),
        },
    },
    "police_station": {
        "title": "The Precise Community Police Bureau and the Police Front Yard",
        "categories": ["police department"],
        "seed": 63106,
        "style": "flat",
        "floor": "stone",
        "canopy": "solid",
        "palette": {
            "plaster": (0.72, 0.75, 0.76),
            "facade": (0.035, 0.12, 0.30),
            "primary": (0.02, 0.18, 0.52),
            "secondary": (0.72, 0.54, 0.10),
            "fabric": (0.19, 0.30, 0.44),
        },
    },
    "fire_station": {
        "title": "The Precision Fire Brigade Equipment Department and Fire Vehicle Parade Area",
        "categories": ["fire department"],
        "seed": 63107,
        "style": "industrial",
        "floor": "stone",
        "canopy": "solid",
        "palette": {
            "plaster": (0.66, 0.63, 0.58),
            "facade": (0.34, 0.025, 0.018),
            "primary": (0.70, 0.018, 0.010),
            "secondary": (0.92, 0.50, 0.02),
            "fabric": (0.20, 0.22, 0.22),
        },
    },
    "community_hospital": {
        "title": "Fine Community Hospital Outpatient and Emergency Drop-off Area",
        "categories": ["hospital"],
        "seed": 63108,
        "style": "flat",
        "floor": "stone",
        "canopy": "glass",
        "palette": {
            "plaster": (0.84, 0.86, 0.83),
            "facade": (0.08, 0.42, 0.47),
            "primary": (0.08, 0.56, 0.62),
            "secondary": (0.34, 0.62, 0.78),
            "fabric": (0.48, 0.72, 0.70),
        },
    },
    "light_factory": {
        "title": "Precision Light Industrial Factory and Loading Dock Company",
        "categories": ["factory"],
        "seed": 63109,
        "style": "industrial",
        "floor": "stone",
        "canopy": "solid",
        "palette": {
            "plaster": (0.52, 0.54, 0.53),
            "facade": (0.12, 0.16, 0.20),
            "primary": (0.90, 0.34, 0.015),
            "secondary": (0.05, 0.35, 0.46),
            "fabric": (0.24, 0.28, 0.30),
        },
    },
    "delivery_service_hub": {
        "title": "fine courier station, express box, food delivery cabinet",
        "categories": ["post office", "delivery box", "delivery cabinet"],
        "seed": 63110,
        "style": "flat",
        "floor": "stone",
        "canopy": "solid",
        "palette": {
            "plaster": (0.74, 0.72, 0.66),
            "facade": (0.64, 0.27, 0.02),
            "primary": (0.94, 0.42, 0.015),
            "secondary": (0.04, 0.26, 0.54),
            "fabric": (0.34, 0.42, 0.50),
        },
    },
    "community_bank_atm": {
        "title": "Fine Community Bank and Outdoor ATMs",
        "categories": ["bank", "ATM"],
        "seed": 63111,
        "style": "flat",
        "floor": "stone",
        "canopy": "glass",
        "palette": {
            "plaster": (0.76, 0.74, 0.68),
            "facade": (0.025, 0.17, 0.25),
            "primary": (0.02, 0.27, 0.42),
            "secondary": (0.62, 0.43, 0.10),
            "fabric": (0.21, 0.34, 0.38),
        },
    },
    "gas_station_store": {
        "title": "Fine Gas Station Convenience Store with Fueling Area",
        "categories": ["gas station", "shop"],
        "seed": 63112,
        "style": "flat",
        "floor": "stone",
        "canopy": "solid",
        "palette": {
            "plaster": (0.78, 0.80, 0.78),
            "facade": (0.025, 0.28, 0.43),
            "primary": (0.02, 0.40, 0.62),
            "secondary": (0.94, 0.43, 0.015),
            "fabric": (0.30, 0.46, 0.52),
        },
    },
    "riverside_lake_park": {
        "title": "Fine Park Visitor Center, Lake Side, and Small River",
        "categories": ["park", "by the lake", "Small river"],
        "seed": 63113,
        "style": "pitched",
        "floor": "wood",
        "canopy": "slatted",
        "palette": {
            "plaster": (0.66, 0.65, 0.54),
            "facade": (0.08, 0.26, 0.16),
            "primary": (0.08, 0.38, 0.20),
            "secondary": (0.05, 0.32, 0.48),
            "fabric": (0.44, 0.56, 0.42),
        },
    },
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def add_wall_art(g, m, prefix, y=9.72, xs=(-4.4, -2.4, 2.4, 4.4)):
    for index, x in enumerate(xs):
        g.box(
            f"{prefix} frame {index}",
            (x, y, 2.35),
            (1.45, 0.08, 1.10),
            m["Wood"],
            0.018,
        )
        g.box(
            f"{prefix} abstract panel {index}",
            (x, y - 0.055, 2.35),
            (1.28, 0.025, 0.93),
            m["Primary"] if index % 2 else m["Secondary"],
            0.008,
        )


def add_reception(g, m, prefix, x, y, width=3.4):
    g.asset(
        "counter", prefix + " high detail counter", (x, y, 0), (width / 3.2, 1.0, 1.0)
    )
    g.box(
        prefix + " stone worktop",
        (x, y - 0.02, 0.98),
        (width + 0.18, 1.04, 0.09),
        m["Stone"],
        0.025,
    )
    g.screen(
        prefix + " monitor",
        (x, y - 0.64, 1.45),
        (0.78, 0.11, 0.54),
        m["Metal"],
        m["CoolGlow"],
    )
    g.box(
        prefix + " keyboard",
        (x, y - 0.48, 1.06),
        (0.68, 0.28, 0.045),
        m["Black"],
        0.012,
    )
    g.asset("chair", prefix + " staff chair", (x, y + 0.92, 0), (1, 1, 1), math.pi)


def add_waiting(g, prefix, x0, y, count, spacing=1.05, rot=0):
    for i in range(count):
        g.asset(
            "chair",
            f"{prefix} upholstered chair {i}",
            (x0 + i * spacing, y, 0),
            (1, 1, 1),
            rot,
        )


def add_modular_sofa(g, m, prefix, loc, width=2.8, depth=1.05, rot=0.0):
    """Detailed rounded sofa without the reference sofa's costly shader graph."""
    x, y, z = loc

    def local(dx, dy, dz):
        return (
            x + math.cos(rot) * dx - math.sin(rot) * dy,
            y + math.sin(rot) * dx + math.cos(rot) * dy,
            z + dz,
        )

    g.box(
        prefix + " recessed plinth",
        local(0, 0, 0.16),
        (width * 0.86, depth * 0.72, 0.24),
        m["Metal"],
        0.07,
        (0, 0, rot),
    )
    g.box(
        prefix + " upholstered base",
        local(0, 0, 0.43),
        (width, depth, 0.38),
        m["Fabric"],
        0.14,
        (0, 0, rot),
    )
    modules = max(2, int(round(width / 0.85)))
    module_width = (width - 0.30) / modules
    for index in range(modules):
        dx = -width / 2 + 0.15 + module_width * (index + 0.5)
        g.box(
            prefix + f" seat cushion {index}",
            local(dx, -depth * 0.06, 0.70),
            (module_width - 0.05, depth * 0.72, 0.20),
            m["Fabric"],
            0.10,
            (0, 0, rot),
        )
        back = g.box(
            prefix + f" back cushion {index}",
            local(dx, depth * 0.37, 1.10),
            (module_width - 0.06, 0.24, 0.78),
            m["Fabric"],
            0.11,
            (0, 0, rot),
        )
        back.rotation_euler.rotate_axis("X", math.radians(-7))
        for stitch in (-0.18, 0.18):
            g.box(
                prefix + f" back seam {index} {stitch}",
                local(dx + stitch * module_width, depth * 0.235, 1.10),
                (0.018, 0.018, 0.58),
                m["Secondary"],
                0.004,
                (0, 0, rot),
            )
    for side in (-1, 1):
        g.box(
            prefix + f" armrest {side}",
            local(side * (width / 2 - 0.10), 0, 0.78),
            (0.24, depth, 0.68),
            m["Fabric"],
            0.12,
            (0, 0, rot),
        )
        for dy in (-depth * 0.31, depth * 0.31):
            g.cylinder(
                prefix + f" metal foot {side} {dy}",
                local(side * (width / 2 - 0.24), dy, 0.12),
                0.045,
                0.24,
                m["Steel"],
                20,
            )


def add_workstation(g, m, prefix, x, y, rot=0):
    g.box(
        prefix + " desktop",
        (x, y, 0.77),
        (2.1, 0.90, 0.10),
        m["LightWood"],
        0.035,
        (0, 0, rot),
    )
    for dx in (-0.85, 0.85):
        g.box(
            prefix + f" leg {dx}",
            (x + math.cos(rot) * dx, y + math.sin(rot) * dx, 0.38),
            (0.09, 0.09, 0.75),
            m["Metal"],
            0.018,
        )
    g.screen(
        prefix + " display",
        (x, y - 0.20, 1.28),
        (0.78, 0.10, 0.54),
        m["Metal"],
        m["CoolGlow"],
    )
    g.box(
        prefix + " keyboard", (x, y + 0.15, 0.84), (0.64, 0.26, 0.045), m["Black"], 0.01
    )
    g.asset("chair", prefix + " ergonomic chair", (x, y + 0.82, 0), (1, 1, 1), math.pi)


def add_residential(g, m):
    add_modular_sofa(
        g, m, "Tufted living room sofa", (-4.8, 6.3, 0), 3.0, 1.12, math.pi / 2
    )
    add_modular_sofa(
        g, m, "Compact lounge sofa", (4.9, 6.6, 0), 2.55, 1.02, -math.pi / 2
    )
    g.cylinder(
        "Sculpted side table stone top", (-3.4, 7.8, 0.62), 0.48, 0.12, m["Stone"], 48
    )
    g.cylinder(
        "Sculpted side table tapered base",
        (-3.4, 7.8, 0.31),
        0.24,
        0.56,
        m["Metal"],
        40,
        radius2=0.13,
    )
    g.torus("Sculpted side table foot ring", (-3.4, 7.8, 0.07), 0.31, 0.035, m["Steel"])
    g.table_set("Family dining", (4.5, 3.1, 0), seats=4, scale=1.12)
    g.box("Layered wool rug", (-4.15, 5.0, 0.045), (4.8, 3.6, 0.09), m["Fabric"], 0.07)
    g.box(
        "Coffee table stone top", (-3.7, 4.9, 0.52), (1.8, 1.0, 0.12), m["Stone"], 0.06
    )
    for x in (-4.35, -3.05):
        g.cylinder(
            f"Coffee table bronze leg {x}", (x, 4.9, 0.26), 0.055, 0.50, m["Metal"], 24
        )
    g.cabinet(
        "Media console",
        (4.35, 8.55, 0),
        (3.5, 0.65, 0.78),
        m["Wood"],
        m["LightWood"],
        m["Metal"],
        1,
        4,
    )
    g.screen(
        "Large television",
        (4.35, 9.60, 1.95),
        (2.9, 0.10, 1.55),
        m["Metal"],
        m["Black"],
    )
    g.asset(
        "shelf", "Residential stocked bookcase", (-5.25, 8.75, 0), (0.95, 0.95, 1.0), 0
    )
    for x, y, h in ((-6.0, 1.2, 1.6), (5.9, 5.0, 1.35), (-2.5, 8.6, 1.1)):
        g.plant(
            f"Residential botanical {x} {y}",
            (x, y, 0),
            h,
            m["Stone"],
            m["Leaf2"],
            m["Green"],
        )
    add_wall_art(g, m, "Residential art", xs=(-1.6, 0, 1.6))
    # Garden terrace cluster on one side of the clear route.
    g.table_set("Courtyard teak set", (4.2, -5.2, 0), seats=4, scale=1.0)
    for x in (-5.7, -3.6):
        g.box(
            f"Courtyard raised planter {x}",
            (x, -4.5, 0.45),
            (1.6, 2.0, 0.90),
            m["Stone"],
            0.06,
        )
        g.plant(
            f"Courtyard tall planting {x}",
            (x, -4.5, 0.85),
            1.5,
            m["Stone"],
            m["Green"],
            m["Leaf3"],
        )
    for j in range(9):
        g.box(
            f"Balcony privacy slat {j}",
            (-6.5 + j * 0.22, -8.0, 1.35),
            (0.11, 3.2, 2.7),
            m["Wood"],
            0.012,
        )


def add_school(g, m):
    g.box(
        "Five-layer teaching board frame",
        (-4.2, 9.70, 2.35),
        (4.8, 0.10, 1.45),
        m["Metal"],
        0.025,
    )
    g.box(
        "Teaching board writing surface",
        (-4.2, 9.62, 2.35),
        (4.55, 0.035, 1.20),
        m["White"],
        0.01,
    )
    g.box(
        "Teaching board chalk rail",
        (-4.2, 9.52, 1.70),
        (4.75, 0.17, 0.10),
        m["Steel"],
        0.012,
    )
    add_workstation(g, m, "Teacher workstation", 4.6, 8.0)
    for row, y in enumerate((2.0, 4.0, 6.0)):
        for side, x in enumerate((-3.7, 3.7)):
            g.box(
                f"Student desk top {row} {side}",
                (x, y, 0.72),
                (2.25, 0.78, 0.09),
                m["LightWood"],
                0.035,
            )
            for dx in (-0.85, 0.85):
                g.box(
                    f"Student desk leg {row} {side} {dx}",
                    (x + dx, y, 0.36),
                    (0.065, 0.065, 0.72),
                    m["Metal"],
                    0.015,
                )
            for index, px in enumerate((x - 0.55, x + 0.55)):
                g.asset(
                    "chair",
                    f"Student chair {row} {side} {index}",
                    (px, y - 0.72, 0),
                    (0.82, 0.82, 0.82),
                    0,
                )
                for book in range(3):
                    g.box(
                        f"Workbook {row} {side} {index} {book}",
                        (px, y, 0.80 + book * 0.025),
                        (0.42, 0.28, 0.022),
                        m["Primary"] if book % 2 else m["Secondary"],
                        0.006,
                    )
    g.asset("shelf", "Classroom reading shelf", (-5.2, 8.5, 0), (0.92, 0.90, 0.95), 0)
    g.cabinet(
        "Student storage cubbies",
        (5.7, 4.5, 0),
        (1.2, 5.2, 2.6),
        m["LightWood"],
        m["Primary"],
        m["Metal"],
        4,
        2,
    )
    # Detailed schoolyard with offset goals preserving the central path.
    g.box(
        "Schoolyard resilient court",
        (0, -7.8, 0.06),
        (13.0, 13.0, 0.08),
        m["Primary"],
        0.012,
    )
    for x in (-6.0, 6.0):
        g.box(
            f"Court sideline {x}",
            (x, -7.8, 0.115),
            (0.06, 12.0, 0.025),
            m["White"],
            0.003,
        )
    for y in (-2.0, -13.6):
        g.box(
            f"Court endline {y}", (0, y, 0.115), (12.0, 0.06, 0.025), m["White"], 0.003
        )
    for x, y in ((-4.6, -3.0), (4.6, -12.8)):
        g.box(
            f"Basketball post {x} {y}",
            (x, y, 1.55),
            (0.16, 0.16, 3.10),
            m["Metal"],
            0.025,
        )
        g.box(
            f"Basketball backboard {x} {y}",
            (x, y - 0.30, 2.78),
            (1.80, 0.10, 1.15),
            m["FrostedGlass"],
            0.018,
        )
        g.torus(
            f"Basketball hoop {x} {y}",
            (x, y - 0.48, 2.42),
            0.34,
            0.035,
            m["Secondary"],
            (math.pi / 2, 0, 0),
        )
        for j in range(9):
            angle = j * 2 * math.pi / 9
            g.rod(
                f"Hoop net cord {x} {y} {j}",
                (x + math.cos(angle) * 0.32, y - 0.48, 2.40 + math.sin(angle) * 0.02),
                (x + math.cos(angle) * 0.22, y - 0.48, 2.00),
                0.008,
                m["White"],
                8,
            )


def add_library(g, m):
    # High-density stocked reference shelves use the Astra reference mesh.
    for x in (-5.35, 5.35):
        for y in (2.0, 5.0, 8.0):
            g.asset(
                "shelf",
                f"Full stocked library stack {x} {y}",
                (x, y, 0),
                (0.88, 0.88, 1.18),
                math.pi / 2,
            )
    g.asset(
        "shelf", "Rear feature book wall left", (-4.2, 9.35, 0), (1.05, 0.85, 1.30), 0
    )
    g.asset(
        "shelf", "Rear feature book wall right", (4.2, 9.35, 0), (1.05, 0.85, 1.30), 0
    )
    add_reception(g, m, "Circulation", 4.3, 7.2, 3.6)
    for x, y in ((-3.3, 3.2), (3.3, 3.2), (-3.3, 6.6)):
        g.table_set(f"Reading table {x} {y}", (x, y, 0), seats=4, scale=0.94)
        for j in range(4):
            g.box(
                f"Reading book stack {x} {y} {j}",
                (x - 0.38 + j * 0.24, y, 0.82 + j * 0.025),
                (0.32, 0.24, 0.035),
                m["Secondary"] if j % 2 else m["Primary"],
                0.008,
            )
    for x in (-5.6, 5.6):
        g.plant(
            f"Library tall plant {x}",
            (x, 1.1, 0),
            1.6,
            m["Stone"],
            m["Leaf2"],
            m["Green"],
        )
    # Reading plaza/pergola.
    for x in (-5.5, 5.5):
        g.box(
            f"Reading terrace pergola post {x}",
            (x, -5.2, 1.65),
            (0.20, 0.20, 3.3),
            m["Wood"],
            0.025,
        )
        g.box(
            f"Reading terrace bench seat {x}",
            (x, -7.0, 0.55),
            (2.5, 0.65, 0.14),
            m["LightWood"],
            0.035,
        )
        g.box(
            f"Reading terrace bench back {x}",
            (x, -6.72, 1.02),
            (2.5, 0.12, 0.82),
            m["LightWood"],
            0.035,
        )
    for j in range(13):
        g.box(
            f"Reading pergola roof slat {j}",
            (-5.5 + j * 0.92, -6.3, 3.25),
            (0.13, 4.0, 0.16),
            m["Wood"],
            0.018,
        )
    g.cabinet(
        "Weatherproof book return",
        (-4.6, -2.4, 0),
        (1.4, 0.75, 1.55),
        m["Primary"],
        m["Steel"],
        m["Metal"],
        2,
        1,
    )
    g.box(
        "Book return slot", (-4.6, -2.81, 1.08), (0.82, 0.06, 0.18), m["Black"], 0.012
    )


def add_sports(g, m):
    g.box(
        "Professional sprung court",
        (0, 5.0, 0.045),
        (13.3, 9.3, 0.075),
        m["LightWood"],
        0.008,
    )
    # Keep only floor graphics in center aisle.
    g.box(
        "Court center stripe", (0, 5.0, 0.095), (0.045, 8.6, 0.018), m["White"], 0.002
    )
    g.torus("Court center ring", (0, 5.0, 0.11), 1.15, 0.035, m["Primary"], (0, 0, 0))
    for x, y, aim in ((-4.7, 1.1, 1), (4.7, 8.8, -1)):
        g.box(
            f"Indoor basket post {x}", (x, y, 1.6), (0.18, 0.18, 3.2), m["Metal"], 0.028
        )
        g.box(
            f"Indoor basket board {x}",
            (x, y + 0.28 * aim, 2.85),
            (1.9, 0.10, 1.15),
            m["FrostedGlass"],
            0.018,
        )
        g.torus(
            f"Indoor basket ring {x}",
            (x, y + 0.48 * aim, 2.48),
            0.35,
            0.038,
            m["Secondary"],
            (math.pi / 2, 0, 0),
        )
    # Tiered bleachers with seats, rails and stair gaps.
    for side, x in ((-1, -6.05), (1, 6.05)):
        for tier in range(4):
            g.box(
                f"Bleacher riser {side} {tier}",
                (x, 5.2, 0.18 + tier * 0.28),
                (1.25, 7.8, 0.36 + tier * 0.56),
                m["Concrete"],
                0.018,
            )
            for y in (2.1, 3.7, 5.3, 6.9, 8.5):
                g.box(
                    f"Bleacher seat {side} {tier} {y}",
                    (x - side * 0.10, y, 0.43 + tier * 0.56),
                    (0.55, 1.25, 0.14),
                    m["Primary"] if (tier + int(y)) % 2 else m["Secondary"],
                    0.04,
                )
    g.asset("shelf", "Sports equipment cage", (-5.2, 9.15, 0), (0.9, 0.8, 1.05), 0)
    for j in range(12):
        angle = j * 0.52
        g.sphere(
            f"Detailed sports ball {j}",
            (-5.5 + (j % 3) * 0.45, 8.4 - (j // 3) * 0.42, 0.24),
            (0.22, 0.22, 0.22),
            m["Secondary"] if j % 2 else m["Primary"],
            2,
        )
    # Outdoor multi-use court.
    g.box(
        "Outdoor rubber court",
        (0, -8.4, 0.055),
        (13.0, 12.5, 0.075),
        m["Primary"],
        0.01,
    )
    for x in (-6.0, 6.0):
        g.box(
            f"Outdoor court sideline {x}",
            (x, -8.4, 0.11),
            (0.05, 11.6, 0.02),
            m["White"],
            0.002,
        )
    for y in (-2.8, -14.0):
        g.box(
            f"Outdoor court endline {y}",
            (0, y, 0.11),
            (12.0, 0.05, 0.02),
            m["White"],
            0.002,
        )


def add_pharmacy(g, m):
    for x in (-5.25, 5.25):
        for y in (2.0, 5.0, 8.0):
            g.asset(
                "shelf",
                f"Fully stocked pharmacy bay {x} {y}",
                (x, y, 0),
                (0.90, 0.90, 1.05),
                math.pi / 2,
            )
    add_reception(g, m, "Prescription service", 4.2, 8.0, 3.8)
    add_reception(g, m, "Retail checkout", -4.2, 8.0, 3.4)
    g.cabinet(
        "Secure medicine cabinet",
        (5.7, 5.0, 0),
        (1.25, 2.2, 2.85),
        m["White"],
        m["FrostedGlass"],
        m["Metal"],
        4,
        2,
    )
    for x in (-4.8, -3.5, -2.2):
        g.asset("chair", f"Pharmacy waiting chair {x}", (x, 1.1, 0), (1, 1, 1), 0)
    g.box(
        "Consultation privacy screen",
        (4.7, 1.35, 1.45),
        (3.1, 0.10, 2.9),
        m["FrostedGlass"],
        0.02,
    )
    g.table_set("Consultation table", (4.2, 2.6, 0), seats=2, scale=0.85)
    # Individually modeled window display products and canopy fins.
    for side in (-1, 1):
        for row in range(3):
            for col in range(6):
                x = side * (3.0 + col * 0.55)
                g.box(
                    f"Window health product {side} {row} {col}",
                    (x, -0.55, 0.85 + row * 0.42),
                    (0.32, 0.28, 0.34 + 0.05 * ((row + col) % 2)),
                    m["Primary"] if col % 2 else m["Secondary"],
                    0.035,
                )
        g.box(
            f"Window display plinth {side}",
            (side * 4.4, -0.45, 0.48),
            (3.6, 0.70, 0.18),
            m["White"],
            0.03,
        )


def add_police(g, m):
    add_reception(g, m, "Public duty desk", -4.2, 7.8, 4.0)
    for x, y in ((4.3, 7.6), (-4.3, 4.5), (4.3, 4.2)):
        add_workstation(g, m, f"Officer workstation {x} {y}", x, y)
    g.asset("shelf", "Case archive shelf west", (-5.4, 8.9, 0), (0.92, 0.86, 1.12), 0)
    g.asset("shelf", "Case archive shelf east", (5.4, 8.9, 0), (0.92, 0.86, 1.12), 0)
    g.cabinet(
        "Secure evidence lockers",
        (5.7, 2.0, 0),
        (1.25, 2.8, 2.9),
        m["Metal"],
        m["Primary"],
        m["Steel"],
        5,
        2,
    )
    add_waiting(g, "Public waiting", -5.2, 1.2, 4, 1.05, 0)
    for i, x in enumerate((-4.8, -2.8, 2.8, 4.8)):
        g.box(
            f"Incident briefing frame {i}",
            (x, 9.72, 2.35),
            (1.55, 0.08, 1.12),
            m["Metal"],
            0.018,
        )
        g.box(
            f"Incident briefing map {i}",
            (x, 9.65, 2.35),
            (1.38, 0.02, 0.94),
            m["Blue"] if i % 2 else m["Secondary"],
            0.006,
        )
        for pin in range(6):
            g.cylinder(
                f"Map marker {i} {pin}",
                (x - 0.45 + (pin % 3) * 0.45, 9.62, 2.1 + (pin // 3) * 0.38),
                0.025,
                0.025,
                m["Red"],
                16,
                (0, 1, 0),
            )
    g.detailed_vehicle(
        "Detailed patrol vehicle",
        (-4.5, -7.8, 0),
        5.0,
        m["White"],
        m["Metal"],
        m["Glass"],
        m["Black"],
        m["Blue"],
    )
    for x in (-1.8, 1.8, 4.5):
        g.cylinder(f"Security bollard {x}", (x, -3.0, 0.52), 0.11, 1.04, m["Metal"], 28)
        g.torus(
            f"Bollard reflective ring {x}",
            (x, -3.0, 0.77),
            0.115,
            0.018,
            m["Secondary"],
        )


def add_fire(g, m):
    # Turnout lockers contain doors, vents, helmets, coats, boots and labels.
    for side, x in ((-1, -5.6), (1, 5.6)):
        for bay, y in enumerate((1.3, 3.1, 4.9, 6.7, 8.5)):
            g.cabinet(
                f"Turnout locker {side} {bay}",
                (x, y, 0),
                (1.15, 1.28, 2.85),
                m["Metal"],
                m["Red"],
                m["Steel"],
                2,
                1,
            )
            g.sphere(
                f"Fire helmet dome {side} {bay}",
                (x, y - 0.70, 2.38),
                (0.36, 0.27, 0.25),
                m["Yellow"],
                3,
            )
            g.box(
                f"Helmet brim {side} {bay}",
                (x, y - 0.72, 2.25),
                (0.74, 0.42, 0.08),
                m["Yellow"],
                0.035,
            )
            g.box(
                f"Turnout coat {side} {bay}",
                (x, y - 0.72, 1.38),
                (0.78, 0.16, 1.12),
                m["Primary"],
                0.12,
            )
            for boot in (-0.24, 0.24):
                g.box(
                    f"Fire boot {side} {bay} {boot}",
                    (x + boot, y - 0.68, 0.35),
                    (0.28, 0.40, 0.68),
                    m["Black"],
                    0.06,
                )
    g.asset("shelf", "Breathing apparatus rack", (-4.2, 9.15, 0), (1.0, 0.85, 1.15), 0)
    for side in (-1, 1):
        for row in range(3):
            y = 7.8 - row * 1.0
            g.cylinder(
                f"Compressed air bottle {side} {row}",
                (side * 4.3, y, 1.12),
                0.20,
                0.82,
                m["Steel"],
                32,
            )
            g.cylinder(
                f"Bottle valve {side} {row}",
                (side * 4.3, y, 1.57),
                0.07,
                0.10,
                m["Metal"],
                20,
            )
    for side, x in ((-1, -3.8), (1, 3.8)):
        g.torus(
            f"Coiled fire hose {side}",
            (x, 9.55, 1.75),
            0.58,
            0.10,
            m["Yellow"],
            (math.pi / 2, 0, 0),
        )
        g.torus(
            f"Inner coiled hose {side}",
            (x, 9.50, 1.75),
            0.35,
            0.08,
            m["Yellow"],
            (math.pi / 2, 0, 0),
        )
        g.tube(
            f"Hose tail {side}",
            [(x, 9.45, 1.2), (x + side * 0.6, 8.9, 0.9), (x + side * 1.0, 8.2, 0.35)],
            0.075,
            m["Yellow"],
        )
    # High-detail engine kept off the bidirectional center lane.
    g.detailed_vehicle(
        "Pumper fire engine",
        (4.4, -8.4, 0),
        6.8,
        m["Red"],
        m["Steel"],
        m["Glass"],
        m["Black"],
        m["Yellow"],
        True,
    )
    g.box(
        "Fire engine equipment superstructure",
        (4.4, -7.7, 1.72),
        (2.02, 3.4, 1.45),
        m["Red"],
        0.10,
    )
    for row in range(2):
        for col in range(4):
            g.box(
                f"Engine rollup compartment {row} {col}",
                (3.37 if row == 0 else 5.43, -8.8 + col * 0.75, 1.62),
                (0.045, 0.62, 0.82),
                m["Steel"],
                0.018,
            )
            for rib in range(6):
                g.box(
                    f"Compartment rib {row} {col} {rib}",
                    (
                        3.34 if row == 0 else 5.46,
                        -9.04 + col * 0.75 + rib * 0.095,
                        1.62,
                    ),
                    (0.025, 0.035, 0.74),
                    m["Metal"],
                    0.006,
                )
    for y in (-9.0, -7.8, -6.6):
        g.cylinder(f"Engine roof beacon {y}", (4.4, y, 2.55), 0.13, 0.18, m["Red"], 24)
    g.box(
        "Engine ladder rail left",
        (3.75, -7.2, 2.58),
        (0.10, 4.6, 0.10),
        m["Steel"],
        0.012,
    )
    g.box(
        "Engine ladder rail right",
        (5.05, -7.2, 2.58),
        (0.10, 4.6, 0.10),
        m["Steel"],
        0.012,
    )
    for j in range(12):
        g.box(
            f"Engine ladder rung {j}",
            (4.4, -9.25 + j * 0.38, 2.58),
            (1.35, 0.065, 0.065),
            m["Steel"],
            0.008,
        )


def add_hospital(g, m):
    add_reception(g, m, "Hospital admissions", -4.0, 7.8, 4.2)
    for x, y in ((4.5, 7.8), (-4.5, 4.7), (4.5, 4.7)):
        add_workstation(g, m, f"Clinical workstation {x} {y}", x, y)
    add_waiting(g, "Waiting east", 2.7, 1.25, 4, 1.0, 0)
    add_waiting(g, "Waiting west", -5.6, 1.25, 4, 1.0, 0)
    # Two fully modeled examination bays.
    for side, x in ((-1, -4.6), (1, 4.6)):
        g.box(
            f"Exam bed articulated base {side}",
            (x, 6.1, 0.58),
            (2.25, 0.92, 0.38),
            m["Steel"],
            0.10,
        )
        g.box(
            f"Exam bed mattress {side}",
            (x, 6.1, 0.84),
            (2.15, 0.86, 0.22),
            m["Fabric"],
            0.12,
        )
        g.box(
            f"Exam bed head cushion {side}",
            (x, 6.48, 1.02),
            (0.72, 0.80, 0.18),
            m["White"],
            0.10,
            (0, math.radians(side * 14), 0),
        )
        for dx in (-0.83, 0.83):
            for dy in (-0.30, 0.30):
                g.cylinder(
                    f"Exam bed caster {side} {dx} {dy}",
                    (x + dx, 6.1 + dy, 0.25),
                    0.11,
                    0.06,
                    m["Black"],
                    24,
                    (1, 0, 0),
                )
        g.cabinet(
            f"Bedside medical cabinet {side}",
            (x + side * 1.65, 6.4, 0),
            (0.72, 0.58, 0.95),
            m["White"],
            m["Primary"],
            m["Metal"],
            2,
            1,
        )
        g.rod(
            f"IV pole {side}",
            (x - side * 1.35, 6.2, 0.05),
            (x - side * 1.35, 6.2, 2.35),
            0.035,
            m["Steel"],
            18,
        )
        g.box(
            f"IV crossbar {side}",
            (x - side * 1.35, 6.2, 2.34),
            (0.58, 0.06, 0.06),
            m["Steel"],
            0.012,
        )
        g.box(
            f"IV fluid bag {side}",
            (x - side * 1.15, 6.2, 1.95),
            (0.25, 0.09, 0.48),
            m["FrostedGlass"],
            0.06,
        )
    g.cabinet(
        "Clinical supply wall",
        (5.8, 8.2, 0),
        (1.25, 2.7, 2.9),
        m["White"],
        m["FrostedGlass"],
        m["Metal"],
        5,
        2,
    )
    g.asset(
        "shelf",
        "High density clinical consumables rack",
        (-5.25, 8.95, 0),
        (0.92, 0.88, 1.08),
        0,
    )
    g.detailed_vehicle(
        "Detailed ambulance",
        (-4.5, -8.4, 0),
        6.2,
        m["White"],
        m["Steel"],
        m["Glass"],
        m["Black"],
        m["Red"],
        True,
    )
    g.box(
        "Ambulance medical box", (-4.5, -7.6, 1.62), (2.05, 3.2, 1.55), m["White"], 0.12
    )
    g.box(
        "Emergency dropoff canopy", (0, -6.2, 4.2), (13.2, 8.5, 0.32), m["White"], 0.05
    )
    for x in (-6.0, 6.0):
        g.box(
            f"Emergency canopy column {x}",
            (x, -6.2, 2.05),
            (0.26, 0.26, 4.10),
            m["Steel"],
            0.03,
        )


def add_factory(g, m):
    # Four layered CNC/work cells and visible utility network.
    for index, (x, y) in enumerate(((-4.4, 2.0), (4.4, 2.0), (-4.4, 6.1), (4.4, 6.1))):
        g.box(
            f"CNC machine plinth {index}",
            (x, y, 0.18),
            (3.1, 2.1, 0.36),
            m["Concrete"],
            0.06,
        )
        g.box(
            f"CNC machine body {index}",
            (x, y, 1.18),
            (2.65, 1.72, 1.75),
            m["Metal"],
            0.14,
        )
        g.box(
            f"CNC safety window {index}",
            (x, y - 0.88, 1.38),
            (1.35, 0.055, 0.78),
            m["FrostedGlass"],
            0.025,
        )
        g.box(
            f"CNC control arm {index}",
            (x + 1.45, y - 0.55, 1.65),
            (0.12, 0.12, 1.30),
            m["Steel"],
            0.025,
        )
        g.box(
            f"CNC control panel {index}",
            (x + 1.45, y - 0.75, 2.10),
            (0.72, 0.25, 0.78),
            m["Primary"],
            0.06,
        )
        g.box(
            f"CNC display {index}",
            (x + 1.45, y - 0.89, 2.23),
            (0.48, 0.035, 0.34),
            m["CoolGlow"],
            0.015,
        )
        for button in range(6):
            g.cylinder(
                f"CNC button {index} {button}",
                (x + 1.25 + (button % 3) * 0.20, y - 0.91, 1.86 + (button // 3) * 0.20),
                0.035,
                0.025,
                m["Red"] if button == 0 else m["Yellow"],
                16,
                (0, 1, 0),
            )
    for x in (-5.7, -3.8, 3.8, 5.7):
        g.tube(
            f"Factory overhead utility {x}",
            [(x, 0.8, 3.55), (x, 5.0, 3.55), (x, 9.0, 3.20)],
            0.085,
            m["Primary"] if x < 0 else m["Secondary"],
        )
    g.asset("shelf", "Parts shelf west", (-5.2, 8.9, 0), (0.92, 0.88, 1.15), 0)
    g.asset("shelf", "Parts shelf east", (5.2, 8.9, 0), (0.92, 0.88, 1.15), 0)
    # Loading yard: pallets, detailed forklift and pipe racks.
    for stack, (x, y) in enumerate(((-5.1, -4.2), (-5.1, -7.2), (5.2, -12.2))):
        for level in range(3):
            for slat in range(6):
                g.box(
                    f"Pallet {stack} {level} slat {slat}",
                    (x - 0.9 + slat * 0.36, y, 0.12 + level * 0.72),
                    (0.30, 1.35, 0.12),
                    m["LightWood"],
                    0.015,
                )
            for carton in range(3):
                g.box(
                    f"Pallet carton {stack} {level} {carton}",
                    (x - 0.66 + carton * 0.66, y, 0.46 + level * 0.72),
                    (0.58, 0.88, 0.56),
                    m["Secondary"],
                    0.05,
                )
    g.box(
        "Forklift counterweight", (4.6, -6.6, 0.75), (1.8, 2.0, 1.25), m["Yellow"], 0.18
    )
    g.box(
        "Forklift cabin frame", (4.6, -6.4, 1.85), (1.65, 1.65, 2.0), m["Metal"], 0.06
    )
    for x in (4.0, 5.2):
        g.box(
            f"Forklift mast {x}", (x, -7.8, 1.55), (0.12, 0.16, 3.1), m["Metal"], 0.018
        )
        g.box(
            f"Forklift fork {x}", (x, -8.75, 0.20), (0.16, 2.0, 0.12), m["Metal"], 0.018
        )
    for x in (3.75, 5.45):
        for y in (-6.0, -7.1):
            g.cylinder(
                f"Forklift tire {x} {y}",
                (x, y, 0.48),
                0.42,
                0.28,
                m["Black"],
                36,
                (1, 0, 0),
            )


def add_delivery(g, m):
    add_reception(g, m, "Parcel service", -4.1, 7.8, 4.0)
    for x in (-5.25, 5.25):
        for y in (2.0, 5.0, 8.0):
            g.asset(
                "shelf",
                f"Parcel sorting rack {x} {y}",
                (x, y, 0),
                (0.90, 0.92, 1.12),
                math.pi / 2,
            )
    for row, y in enumerate((2.0, 3.5, 5.0, 6.5, 8.0)):
        for side, x in enumerate((-3.6, 3.6)):
            for col in range(3):
                g.box(
                    f"Labeled parcel geometry {row} {side} {col}",
                    (x - 0.62 + col * 0.62, y, 0.24 + 0.17 * ((row + col) % 3)),
                    (0.52, 0.72, 0.42 + 0.15 * ((row + col) % 3)),
                    m["Secondary"] if col % 2 else m["Primary"],
                    0.055,
                )
                g.box(
                    f"Parcel tape {row} {side} {col}",
                    (x - 0.62 + col * 0.62, y - 0.37, 0.29 + 0.17 * ((row + col) % 3)),
                    (0.10, 0.025, 0.30),
                    m["White"],
                    0.004,
                )
    g.box(
        "Packing bench worktop", (4.2, 8.4, 0.86), (3.4, 1.15, 0.12), m["Steel"], 0.035
    )
    for x in (3.0, 5.4):
        g.box(
            f"Packing bench leg {x}",
            (x, 8.4, 0.42),
            (0.10, 0.95, 0.84),
            m["Metal"],
            0.018,
        )
    # Two richly constructed locker banks outside.
    for side, center in ((-1, -5.0), (1, 5.0)):
        body = m["Primary"] if side < 0 else m["Secondary"]
        g.box(
            f"Locker bank carcass {side}",
            (center, -4.4, 1.45),
            (4.25, 0.80, 2.90),
            m["Metal"],
            0.06,
        )
        for row in range(4):
            for col in range(5):
                x = center - 1.62 + col * 0.81
                z = 0.42 + row * 0.66
                g.box(
                    f"Locker door {side} {row} {col}",
                    (x, -4.83, z),
                    (0.73, 0.055, 0.58),
                    body,
                    0.025,
                )
                g.cylinder(
                    f"Locker status light {side} {row} {col}",
                    (x + 0.26, -4.87, z),
                    0.025,
                    0.025,
                    m["CoolGlow"],
                    14,
                    (0, 1, 0),
                )
        g.screen(
            f"Locker terminal {side}",
            (center, -4.86, 1.55),
            (0.58, 0.08, 0.82),
            m["Black"],
            m["CoolGlow"],
        )
        g.box(
            f"Locker weather canopy {side}",
            (center, -4.25, 3.18),
            (4.7, 1.45, 0.18),
            m["Metal"],
            0.035,
        )
    g.detailed_vehicle(
        "Electric delivery van",
        (4.6, -10.6, 0),
        5.5,
        m["White"],
        m["Metal"],
        m["Glass"],
        m["Black"],
        m["Primary"],
        True,
    )


def add_bank(g, m):
    for x in (-5.1, -3.2, 3.2, 5.1):
        add_reception(g, m, f"Teller station {x}", x, 8.3, 1.55)
        g.box(
            f"Teller safety glass {x}",
            (x, 7.78, 1.73),
            (1.42, 0.05, 1.08),
            m["Glass"],
            0.008,
        )
        g.box(
            f"Teller transaction slot {x}",
            (x, 7.73, 1.13),
            (0.62, 0.14, 0.06),
            m["Steel"],
            0.012,
        )
    for x in (-4.2, 4.2):
        add_workstation(g, m, f"Advisor desk {x}", x, 4.4)
        g.asset("chair", f"Advisor visitor chair {x}", (x, 3.2, 0), (1, 1, 1), 0)
    add_waiting(g, "Bank waiting west", -5.5, 1.2, 4, 1.0, 0)
    add_waiting(g, "Bank waiting east", 2.5, 1.2, 4, 1.0, 0)
    # Layered vault on rear wall, outside the center route.
    g.box(
        "Vault reinforced surround",
        (4.4, 9.65, 1.80),
        (3.3, 0.32, 3.55),
        m["Steel"],
        0.10,
    )
    g.cylinder(
        "Vault circular door", (4.4, 9.42, 1.80), 1.28, 0.24, m["Metal"], 56, (0, 1, 0)
    )
    g.torus(
        "Vault locking wheel rim",
        (4.4, 9.25, 1.80),
        0.48,
        0.065,
        m["Secondary"],
        (math.pi / 2, 0, 0),
    )
    for j in range(8):
        angle = j * math.pi / 4
        g.rod(
            f"Vault wheel spoke {j}",
            (4.4, 9.18, 1.80),
            (4.4 + math.cos(angle) * 0.42, 9.18, 1.80 + math.sin(angle) * 0.42),
            0.035,
            m["Secondary"],
            16,
        )
    # Two outdoor ATMs with layered controls.
    for x in (-4.8, 4.8):
        g.box(
            f"ATM recessed surround {x}",
            (x, -0.85, 1.35),
            (1.55, 0.80, 2.65),
            m["Primary"],
            0.08,
        )
        g.box(
            f"ATM fascia {x}", (x, -1.28, 1.35), (1.32, 0.08, 2.35), m["Steel"], 0.035
        )
        g.screen(
            f"ATM display {x}",
            (x, -1.34, 1.78),
            (0.78, 0.06, 0.58),
            m["Black"],
            m["CoolGlow"],
        )
        for row in range(4):
            for col in range(3):
                g.box(
                    f"ATM keypad key {x} {row} {col}",
                    (x - 0.19 + col * 0.19, -1.39, 1.30 - row * 0.12),
                    (0.12, 0.035, 0.075),
                    m["Metal"],
                    0.012,
                )
        g.box(
            f"ATM cash slot {x}",
            (x, -1.39, 0.72),
            (0.72, 0.035, 0.13),
            m["Black"],
            0.012,
        )
        g.box(
            f"ATM privacy wing left {x}",
            (x - 0.75, -1.55, 1.40),
            (0.10, 0.65, 2.30),
            m["Metal"],
            0.018,
        )
        g.box(
            f"ATM privacy wing right {x}",
            (x + 0.75, -1.55, 1.40),
            (0.10, 0.65, 2.30),
            m["Metal"],
            0.018,
        )


def add_gas(g, m):
    for x in (-5.25, 5.25):
        for y in (2.0, 5.0, 8.0):
            g.asset(
                "shelf",
                f"Convenience stocked shelf {x} {y}",
                (x, y, 0),
                (0.90, 0.92, 1.08),
                math.pi / 2,
            )
    add_reception(g, m, "Convenience checkout", -4.2, 8.0, 4.0)
    g.asset("shelf", "Chilled drinks wall", (4.3, 9.25, 0), (1.20, 0.90, 1.25), 0)
    for x in (3.3, 4.3, 5.3):
        g.box(
            f"Refrigerator glazed door {x}",
            (x, 9.00, 1.45),
            (0.86, 0.08, 2.65),
            m["Glass"],
            0.018,
        )
        g.box(
            f"Refrigerator handle {x}",
            (x + 0.33, 8.94, 1.45),
            (0.055, 0.06, 1.35),
            m["Steel"],
            0.012,
        )
    # Architecturally complete pump canopy.
    g.box(
        "Fuel canopy roof slab", (0, -8.0, 4.75), (15.2, 12.5, 0.42), m["White"], 0.06
    )
    g.box(
        "Fuel canopy primary fascia",
        (0, -14.15, 4.75),
        (15.2, 0.22, 0.60),
        m["Primary"],
        0.025,
    )
    g.box(
        "Fuel canopy secondary stripe",
        (0, -14.29, 4.75),
        (15.2, 0.08, 0.16),
        m["Secondary"],
        0.012,
    )
    for x in (-6.6, 6.6):
        for y in (-3.0, -13.0):
            g.box(
                f"Fuel canopy column {x} {y}",
                (x, y, 2.35),
                (0.34, 0.34, 4.7),
                m["Steel"],
                0.04,
            )
    for lane, x in enumerate((-4.2, 4.2)):
        g.box(
            f"Pump island {lane}",
            (x, -8.2, 0.16),
            (2.6, 6.0, 0.32),
            m["Concrete"],
            0.08,
        )
        g.box(
            f"Fuel dispenser {lane}",
            (x, -8.2, 1.25),
            (1.35, 0.82, 2.18),
            m["White"],
            0.10,
        )
        g.screen(
            f"Pump display {lane}",
            (x, -8.63, 1.66),
            (0.78, 0.06, 0.52),
            m["Black"],
            m["CoolGlow"],
        )
        for side in (-1, 1):
            g.tube(
                f"Fuel hose {lane} {side}",
                [
                    (x + side * 0.62, -8.2, 1.72),
                    (x + side * 1.02, -8.2, 1.3),
                    (x + side * 0.86, -8.2, 0.55),
                ],
                0.045,
                m["Black"],
            )
            g.box(
                f"Fuel nozzle {lane} {side}",
                (x + side * 0.85, -8.2, 0.68),
                (0.12, 0.10, 0.42),
                m["Metal"],
                0.035,
            )
        for grade in range(3):
            g.cylinder(
                f"Fuel grade button {lane} {grade}",
                (x - 0.28 + grade * 0.28, -8.65, 1.22),
                0.065,
                0.03,
                (m["Primary"], m["Secondary"], m["Yellow"])[grade],
                20,
                (0, 1, 0),
            )
    g.detailed_vehicle(
        "Fueling customer crossover",
        (-5.7, -11.0, 0),
        4.7,
        m["Secondary"],
        m["Metal"],
        m["Glass"],
        m["Black"],
    )


def add_park(g, m):
    add_reception(g, m, "Park information", -4.2, 8.0, 3.8)
    g.asset(
        "shelf",
        "Natural history display west",
        (-5.2, 5.2, 0),
        (0.95, 0.90, 1.05),
        math.pi / 2,
    )
    g.asset(
        "shelf",
        "Natural history display east",
        (5.2, 5.2, 0),
        (0.95, 0.90, 1.05),
        math.pi / 2,
    )
    g.table_set("Visitor reading table west", (-3.8, 3.0, 0), seats=4, scale=0.92)
    g.table_set("Visitor reading table east", (3.8, 3.0, 0), seats=4, scale=0.92)
    add_modular_sofa(
        g, m, "Visitor lounge sofa west", (-5.0, 7.0, 0), 2.55, 1.02, math.pi / 2
    )
    add_modular_sofa(
        g, m, "Visitor lounge sofa east", (5.0, 7.0, 0), 2.55, 1.02, -math.pi / 2
    )
    for x in (-5.8, 5.8):
        g.plant(
            f"Visitor center specimen {x}",
            (x, 1.0, 0),
            1.5,
            m["Stone"],
            m["Leaf2"],
            m["Green"],
        )
    # Replace generic context with an actual sculpted lake/river landscape.
    g.box("Park meadow base", (0, -8.0, -0.09), (26.0, 16.0, 0.18), m["Green"], 0.02)
    g.box("Lake basin water", (6.0, -9.8, 0.035), (10.6, 9.5, 0.07), m["Water"], 0.12)
    g.box(
        "River channel water", (-3.5, -8.0, 0.038), (3.5, 15.0, 0.075), m["Water"], 0.12
    )
    # Curving bank impression from clustered rocks and planted edges.
    for side in (-1, 1):
        for j in range(18):
            y = -1.0 - j * 0.78
            x = -3.5 + side * (1.85 + 0.25 * math.sin(j * 0.7))
            g.sphere(
                f"Riverbank stone {side} {j}",
                (x, y, 0.16),
                (0.32 + 0.06 * (j % 3), 0.24, 0.18),
                m["Stone"],
                2,
            )
            if j % 2 == 0:
                for blade in range(5):
                    bx = x + (blade - 2) * 0.07
                    g.rod(
                        f"River reed {side} {j} {blade}",
                        (bx, y, 0.12),
                        (bx + 0.05 * side, y, 0.75 + 0.08 * blade),
                        0.012,
                        m["Leaf3"],
                        8,
                    )
    # Detailed timber bridge offset from the center traversal path.
    for j in range(14):
        g.box(
            f"Bridge deck plank {j}",
            (-5.5 + j * 0.30, -8.0, 0.42),
            (0.27, 3.2, 0.15),
            m["LightWood"],
            0.025,
        )
    for x in (-5.75, -1.25):
        for y in (-9.35, -8.0, -6.65):
            g.box(
                f"Bridge rail post {x} {y}",
                (x, y, 1.0),
                (0.13, 0.13, 1.25),
                m["Wood"],
                0.018,
            )
        g.box(
            f"Bridge top rail {x}", (x, -8.0, 1.58), (0.15, 3.0, 0.15), m["Wood"], 0.018
        )
    # Lakeside deck, pergola and seating.
    g.box(
        "Lakeside timber deck",
        (7.0, -3.6, 0.22),
        (8.8, 3.2, 0.30),
        m["LightWood"],
        0.025,
    )
    g.table_set("Lakeside picnic setting", (6.0, -3.6, 0.36), seats=4, scale=1.0)
    for x, y, h in (
        (-9.2, -3.0, 5.6),
        (-9.0, -12.0, 6.0),
        (10.0, -3.2, 5.4),
        (10.2, -13.0, 6.2),
        (1.8, -13.8, 5.2),
    ):
        g.tree(
            f"Park mature tree {x} {y}",
            (x, y, 0),
            h,
            m["Bark"],
            [m["Green"], m["Leaf2"], m["Leaf3"]],
        )
    for x, y in ((-8.0, -5.0), (-8.2, -10.5), (8.0, -14.0)):
        for slat in range(6):
            g.box(
                f"Park bench {x} {y} seat {slat}",
                (x, y + slat * 0.12, 0.52),
                (2.2, 0.10, 0.10),
                m["LightWood"],
                0.016,
            )
        for slat in range(4):
            g.box(
                f"Park bench {x} {y} back {slat}",
                (x, y + 0.35, 0.78 + slat * 0.15),
                (2.2, 0.09, 0.10),
                m["LightWood"],
                0.016,
            )


BUILDERS = {
    "residential_neighborhood": add_residential,
    "neighborhood_school": add_school,
    "public_library": add_library,
    "community_sports_hall": add_sports,
    "retail_pharmacy": add_pharmacy,
    "police_station": add_police,
    "fire_station": add_fire,
    "community_hospital": add_hospital,
    "light_factory": add_factory,
    "delivery_service_hub": add_delivery,
    "community_bank_atm": add_bank,
    "gas_station_store": add_gas,
    "riverside_lake_park": add_park,
}


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", required=True, choices=sorted(SCENES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(arguments)
    config = SCENES[args.scene_id]
    root = OUTPUT / args.scene_id
    scene_path = root / "scene/scene.blend"
    manifest_path = root / "manifest.json"
    if not args.force and scene_path.is_file() and manifest_path.is_file():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("build_success") is True and old.get("scene_sha256") == sha256(
            scene_path
        ):
            print(f"ASTRA_CONNECT3_BUILD_REUSED scene={args.scene_id}", flush=True)
            return 0
    root.mkdir(parents=True, exist_ok=True)
    (root / "scene").mkdir(exist_ok=True)
    (root / "source").mkdir(exist_ok=True)
    (root / "input").mkdir(exist_ok=True)
    started = utc()
    print(f"ASTRA_CONNECT3_BUILD_START scene={args.scene_id}", flush=True)
    clear_scene()
    g = Geo(config["seed"])
    m = create_materials(g, config["palette"])
    build_shell(g, m, config["style"], config["floor"])
    add_architectural_details(g, m, config["canopy"])
    if args.scene_id != "riverside_lake_park":
        add_context(g, m, trees=True)
    BUILDERS[args.scene_id](g, m)
    camera = add_world_and_lights(g, m)
    connection = audit_connection()
    if not connection["passed"]:
        raise RuntimeError(
            f"physical connection is blocked: {connection['blockers'][:20]}"
        )
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in mesh_objects)
    polygons = sum(len(obj.data.polygons) for obj in mesh_objects)
    # Require both dense scene structure and substantial native topology.  The
    # fire hall deliberately uses hundreds of separately inspectable fittings
    # rather than inflating one hidden mesh, so its honest topology floor is
    # slightly above 30k vertices while the stocked/soft-furnishing scenes are
    # much denser.
    if len(mesh_objects) < 250 or vertices < 30_000:
        raise RuntimeError(
            f"insufficient detail: meshes={len(mesh_objects)} vertices={vertices}"
        )
    bpy.context.scene["gpt6_astra_scene_id"] = args.scene_id
    bpy.context.scene["gpt6_astra_reasoning_effort"] = "high"
    bpy.context.scene["true_shared_coordinate_3d"] = True
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), compress=True)
    prompt = (
        f"GPT-6 Astra high: generate a high-detail true 3D {config['title']} scene with unique "
        "architecture, semantic equipment, physically open indoor/outdoor connection, detailed "
        "materials and near/mid/far bidirectional cameras. No montage, labels, downloads or 2D cheats.\n"
    )
    (root / "input/prompt.txt").write_text(prompt, encoding="utf-8")
    source_record = {
        "method": "gpt6_astra",
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "builder": str(Path(__file__).relative_to(BASELINES)),
        "builder_sha256": sha256(Path(__file__)),
        "core": "methods/gpt/tools/gpt_connect3_core.py",
        "core_sha256": sha256((BASELINES / "methods/gpt/tools/gpt_connect3_core.py")),
        "reference_asset_library": str(ASSET_LIBRARY),
        "reference_meshes_appended": True,
        "external_downloads": False,
    }
    atomic_json(root / "source/generation_record.json", source_record)
    manifest = {
        "schema_version": 1,
        "method": "gpt6_astra",
        "model_requested": "gpt-6-astra",
        "reasoning_effort_requested": "high",
        "scene_id": args.scene_id,
        "title_zh": config["title"],
        "categories_zh": config["categories"],
        "build_started_at_utc": started,
        "build_completed_at_utc": utc(),
        "build_success": True,
        "render_success": False,
        "true_shared_coordinate_3d_scene": True,
        "native_geometry": True,
        "scene_file": "scene/scene.blend",
        "scene_sha256": sha256(scene_path),
        "source": source_record,
        "geometry": {
            "mesh_object_count": len(mesh_objects),
            "vertices_including_linked_instances": vertices,
            "polygons_including_linked_instances": polygons,
            "material_count": len(bpy.data.materials),
        },
        "connectivity": connection,
    }
    atomic_json(manifest_path, manifest)
    print(
        f"ASTRA_CONNECT3_BUILD_COMPLETE scene={args.scene_id} meshes={len(mesh_objects)} vertices={vertices} polygons={polygons}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
