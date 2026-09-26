"""Production entry point for the strictly validated full-scene revision 03."""
import os
import runpy
from pathlib import Path

os.environ["C2W_FULL_REVISION"] = "urban_v1_full_03"
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
runpy.run_path(
    str(Path(__file__).with_name("generate_urban_v1_full_01.py")), run_name="__main__"
)
