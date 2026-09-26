"""Build a reusable, source-traceable mesh library for the active Astra pipeline."""
import json
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.assets import AssetLibrary
from astra_city.plan import OUT

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
lib = AssetLibrary()
print("DETAIL_MASTERS_READY", flush=True)
lib.commercial()
print("RETAIL_MASTERS_READY", flush=True)
lib.botanical_trees()
print("TREE_MASTERS_READY", flush=True)
lib.native_furniture()
print("NATIVE_MASTERS_READY", flush=True)
lib.save()
(OUT / "asset_library_index.json").write_text(
    json.dumps(
        {
            "meshes": {k: v.name for k, v in lib.meshes.items()},
            "materials": {k: v.name for k, v in lib.materials.items()},
            "native_bounds": lib.native_bounds,
        },
        indent=2,
    ),
    encoding="utf8",
)
print("ASSET_LIBRARY_COMPLETE", flush=True)
