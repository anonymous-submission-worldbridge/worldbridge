"""Production entry for the fully source-integrated ``urban_v1_full_09``.

This entry always performs a clean generator run.  It never opens a prior
full-city or regional Blend and never routes through the checkpoint-upgrade
branches used by earlier river revisions.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


os.environ["C2W_FULL_REVISION"] = "urban_v1_full_09"
os.environ["C2W_OUTPUT_REVISION"] = "urban_v1_full_09"
os.environ["C2W_ADD_RIVER"] = "1"
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
os.environ["C2W_GENERATOR_ENTRY"] = str(Path(__file__).resolve())

# A dense five-gigabyte source scene is saved before validation.  Production
# invocations may set this to 1 and render the saved generator result through
# bounded read-only workers; scene content is identical either way.
os.environ.setdefault("C2W_SKIP_VALIDATION_RENDER", "0")

scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(scripts_dir))

# Load the ALL45-09 source module before the long base/commercial passes.  The
# shared workspace can receive edits from independent jobs; caching the module
# here guarantees that one full-city run uses one coherent source revision.
import urban_v1_full_09_residential

urban_v1_full_09_residential.preload_source()
runpy.run_path(str(scripts_dir / "generate_urban_v1_full_01.py"), run_name="__main__")
