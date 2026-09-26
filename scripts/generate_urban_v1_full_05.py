"""Entry point for the audited urban_v1_full_05 revision."""
from __future__ import annotations

import os
import runpy

os.environ["C2W_FULL_REVISION"] = "urban_v1_full_05"
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
runpy.run_path(
    os.path.join(os.path.dirname(__file__), "generate_urban_v1_full_01.py"),
    run_name="__main__",
)
