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

import bpy

ALL8 = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all8/urban_v3_all8.blend"
names = ["Tree.004", "Tree.010"]
before = len(bpy.data.objects)
with bpy.data.libraries.load(ALL8, link=False) as (data_from, data_to):
    print("available?", [n for n in names if n in data_from.objects], flush=True)
    data_to.objects = names
loaded = [o for o in data_to.objects if o]
print(
    "before",
    before,
    "after",
    len(bpy.data.objects),
    "loaded",
    [o.name for o in loaded],
    flush=True,
)
for o in loaded:
    print(
        o.name,
        "parent",
        o.parent.name if o.parent else None,
        "colls",
        [c.name for c in o.users_collection],
        "mods",
        [(m.name, m.type) for m in o.modifiers],
        flush=True,
    )
print(
    "has TreeFactory42?",
    bool(bpy.data.objects.get("TreeFactory(42).spawn_asset(0)")),
    flush=True,
)
