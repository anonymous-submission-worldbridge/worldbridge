"""
generate_urban_v3_trees.py
==========================
Pre-generate real infinigen street trees and save to a reusable blend file.
Run this BEFORE generate_urban_v3_all4.py.

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trees/trees.blend
        Contains InfTree_0 .. InfTree_4 at X = 0, 25, 50, 75, 100
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import bpy, sys, math
from pathlib import Path

sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
import gin

gin.clear_config()

from infinigen.assets.objects.trees.generate import TreeFactory

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_trees")
OUT.mkdir(parents=True, exist_ok=True)

# Start clean
bpy.ops.wm.read_factory_settings(use_empty=True)

# 5 tree variants at seed diversity
SEEDS = [42, 137, 256, 381, 512]

for i, seed in enumerate(SEEDS):
    print(f"[trees] Generating InfTree_{i} (seed={seed})…")
    fac = TreeFactory(seed=seed, season="summer", coarse=False, fruit_chance=0.0)
    root = fac.spawn_asset(0, loc=(i * 25.0, 0, 0), rot=(0, 0, 0))

    # Rename root and tag all children with a prefix for easy import
    def _tag(obj, prefix):
        obj.name = f"{prefix}_{obj.name}"
        for child in obj.children:
            _tag(child, prefix)

    prefix = f"InfTree_{i}"
    # Don't rename root to prefix directly — use prefix_original_name
    old_name = root.name
    root.name = f"{prefix}_{old_name}"
    for child in root.children:
        _tag(child, prefix)

    print(f"  → {root.name} at ({i*25:.0f}, 0, 0)")

blend_path = str(OUT / "trees.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[done] Trees saved → {blend_path}")
