"""Production entry for topology-driven, fully occupied urban_v2_full_06.

This launches the complete source generator chain and never loads or copies a
previous full-scene blend.  The topology and the land released by that
topology are both consumed by generate_urban_v1_full_01.py in the same run.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path


variant = os.environ.get("C2W_URBAN_VARIANT", "demo1")
if variant not in {"demo1", "demo2"}:
    raise ValueError(f"urban_v2_full_06 supports demo1/demo2, got {variant!r}")

os.environ["C2W_FULL_REVISION"] = f"urban_v2_full_06/{variant}"
os.environ["C2W_URBAN_SEED"] = os.environ.get(
    "C2W_URBAN_SEED", "6101" if variant == "demo1" else "6203"
)
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
os.environ["C2W_GENERATOR_ENTRY"] = str(Path(__file__).resolve())
os.environ["C2W_TOPOLOGY_DRIVEN_OCCUPANCY"] = "1"
os.environ.pop("C2W_TREE_LIBRARY_PROFILE", None)

runpy.run_path(
    str(Path(__file__).with_name("generate_urban_v1_full_01.py")),
    run_name="__main__",
)
