"""Re-extract only native furniture, preserving expensive botanical source meshes."""
import json, sys
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.assets import AssetLibrary
from astra_city.plan import OUT

index = json.loads((OUT / "asset_library_index.json").read_text())
with bpy.data.libraries.load(str(OUT / "asset_library.blend"), link=False) as (
    src,
    dst,
):
    dst.meshes = sorted(set(index["meshes"].values()))
    dst.materials = sorted(set(index["materials"].values()))
lib = object.__new__(AssetLibrary)
lib.records = [
    r
    for r in json.loads((OUT / "asset_registry.json").read_text())["assets"]
    if not r.get("source_object")
]
lib.meshes = {k: bpy.data.meshes[v] for k, v in index["meshes"].items()}
lib.materials = {k: bpy.data.materials[v] for k, v in index["materials"].items()}
lib.native_bounds = {}
for key in ("sofa", "bed", "cabinet", "kitchen", "toilet", "sink", "side_table"):
    lib.meshes[key].name = "previous_" + lib.meshes[key].name
lib.native_furniture()
lib.save()
(OUT / "asset_library_index.json").write_text(
    json.dumps(
        {
            "meshes": {k: v.name for k, v in lib.meshes.items()},
            "materials": {k: v.name for k, v in lib.materials.items()},
            "native_bounds": lib.native_bounds,
        },
        indent=2,
    )
)
for key in ("sofa", "bed", "cabinet", "kitchen", "toilet", "sink", "side_table"):
    print(
        "FIXED_MATERIALS",
        key,
        [m.name if m else None for m in lib.meshes[key].materials],
        flush=True,
    )
