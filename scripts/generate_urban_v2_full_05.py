"""Production entry point for the urban_v2_full_05 diversity rebuild.

This entry executes the complete source generator chain.  It never opens or
copies an older full-scene blend.  Set C2W_URBAN_VARIANT to demo1 or demo2.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path


variant = os.environ.get("C2W_URBAN_VARIANT", "demo1")
if variant not in {"demo1", "demo2"}:
    raise ValueError(f"urban_v2_full_05 supports demo1/demo2, got {variant!r}")

os.environ["C2W_FULL_REVISION"] = f"urban_v2_full_05/{variant}"
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
os.environ["C2W_GENERATOR_ENTRY"] = str(Path(__file__).resolve())
os.environ.pop("C2W_TREE_LIBRARY_PROFILE", None)
runpy.run_path(
    str(Path(__file__).with_name("generate_urban_v1_full_01.py")),
    run_name="__main__",
)
