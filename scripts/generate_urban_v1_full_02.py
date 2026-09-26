"""Production entry point for the corrected full-scene revision."""
import os
import runpy
from pathlib import Path

os.environ["C2W_FULL_REVISION"] = "urban_v1_full_02"
runpy.run_path(
    str(Path(__file__).with_name("generate_urban_v1_full_01.py")), run_name="__main__"
)
