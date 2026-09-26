"""Production entry point for urban_v1_full_07 and connected revisions.

The river5 production branch is a source-connected minimal upgrade from the
audited river2 checkpoint.  Set ``C2W_RIVER5_UPGRADE=1`` after opening that
checkpoint to retain river2 geometry, lower its real water system, remove its
reeds, and save the requested ``urban_v1_full_07-river5`` full-scene output.

``C2W_AGENT4_UPGRADE=1`` extends the audited river3 checkpoint with the real
bedroom-to-store humanoid mission; ``C2W_AGENT4_RENDER=1`` renders that complete
production blend.  Both remain on this entry point so the agent result cannot
silently fall back to a disconnected overlay or compact demo.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path

add_river = os.environ.get("C2W_ADD_RIVER", "1") not in {"0", "false", "False"}
agent4_upgrade = os.environ.get("C2W_AGENT4_UPGRADE", "0") == "1"
agent4_render = os.environ.get("C2W_AGENT4_RENDER", "0") == "1"
agent4_camera_repair = os.environ.get("C2W_AGENT4_CAMERA_REPAIR", "0") == "1"
river5_upgrade = os.environ.get("C2W_RIVER5_UPGRADE", "0") == "1"
os.environ["C2W_FULL_REVISION"] = "urban_v1_full_07"
os.environ["C2W_ADD_RIVER"] = "1" if add_river else "0"
os.environ.setdefault(
    "C2W_OUTPUT_REVISION",
    "urban_v1_full_07_agent4"
    if (agent4_upgrade or agent4_render or agent4_camera_repair)
    else (
        "urban_v1_full_07-river5"
        if river5_upgrade
        else ("urban_v1_full_07-river4" if add_river else "urban_v1_full_07")
    ),
)
os.environ["C2W_FORBID_TOY_MODELS"] = "1"
os.environ["C2W_GENERATOR_ENTRY"] = str(Path(__file__).resolve())

# Cycles/Embree can exhaust or corrupt its shared BVH buffers after many
# consecutive renders of this 5 GB production scene.  Recovery remains part of
# the real generator entry: Blender opens the checkpoint blend and this branch
# renders only missing validation cameras in bounded, fresh worker processes.
if agent4_camera_repair:
    runpy.run_path(
        str(Path(__file__).with_name("repair_urban_v1_full_07_agent4_camera.py")),
        run_name="__main__",
    )
elif agent4_render:
    runpy.run_path(
        str(Path(__file__).with_name("render_urban_v1_full_07_agent4.py")),
        run_name="__main__",
    )
elif agent4_upgrade:
    runpy.run_path(
        str(Path(__file__).with_name("upgrade_urban_v1_full_07_agent4.py")),
        run_name="__main__",
    )
elif os.environ.get("C2W_RESUME_VALIDATION", "0") == "1":
    runpy.run_path(
        str(Path(__file__).with_name("resume_urban_v1_full_07_validation.py")),
        run_name="__main__",
    )
elif river5_upgrade:
    runpy.run_path(
        str(Path(__file__).with_name("upgrade_urban_v1_full_07_river5.py")),
        run_name="__main__",
    )
elif os.environ.get("C2W_RIVER4_UPGRADE", "0") == "1":
    runpy.run_path(
        str(Path(__file__).with_name("upgrade_urban_v1_full_07_river4.py")),
        run_name="__main__",
    )
elif os.environ.get("C2W_RIVER3_UPGRADE", "0") == "1":
    runpy.run_path(
        str(Path(__file__).with_name("upgrade_urban_v1_full_07_river3.py")),
        run_name="__main__",
    )
elif os.environ.get("C2W_RIVER2_UPGRADE", "0") == "1":
    runpy.run_path(
        str(Path(__file__).with_name("upgrade_urban_v1_full_07_river2.py")),
        run_name="__main__",
    )
else:
    runpy.run_path(
        str(Path(__file__).with_name("generate_urban_v1_full_01.py")),
        run_name="__main__",
    )
