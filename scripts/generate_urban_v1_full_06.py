"""Production entry point for the source-generated urban_v1_full_06 scene."""
from __future__ import annotations

import os
import runpy
from pathlib import Path

os.environ["C2W_FULL_REVISION"] = "urban_v1_full_06"
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
os.environ["C2W_GENERATOR_ENTRY"] = str(Path(__file__).resolve())
runpy.run_path(
    str(Path(__file__).with_name("generate_urban_v1_full_01.py")), run_name="__main__"
)
