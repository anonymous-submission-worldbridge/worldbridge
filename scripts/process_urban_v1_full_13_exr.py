#!/usr/bin/env python3
"""Full-13 OpenEXR validator using the proven native-float implementation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "scripts/process_urban_v1_full_12_exr.py"
spec = importlib.util.spec_from_file_location("full13_exr_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = "urban_v1_full_13"
base.CITY = (ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13").resolve()
base.ASSET_LAYERS = (
    "river5_nature",
    "river3_residential",
    "all45_unique_buildings",
    "all44_leisure",
    "commercial_services",
    "residential_delivery",
    "park_leisure_support",
    "artificial_lake",
    "education_buildings",
    "public_safety",
    "health",
    "industrial",
    "full13_unique_urban_fabric",
    "full13_semantic_interiors",
    "full13_public_realm",
)
base.LAYERS = ("base", *base.ASSET_LAYERS)


if __name__ == "__main__":
    base.main()
