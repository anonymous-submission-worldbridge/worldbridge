"""Memory-light render-only correction for all43_08 glass; does not duplicate the 4GB scene."""

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

import sys
from pathlib import Path
import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
import commercial_realism_generator_08 as G
import refine_urban_v3_all43_08 as R

bpy.ops.wm.open_mainfile(
    filepath=str(ROOT / "infinigen/outputs/urban_v3_all43_08/urban_v3_all43_08.blend"),
    load_ui=False,
)
G.glass_material()
R.render(ROOT / "infinigen/outputs/urban_v3_all43_08/urban_v3_all43_08.png")
