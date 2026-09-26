"""Read source library names without importing scenes or modifying references."""
import json
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_astra"
sources = {
    "native_indoor": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09/indoor_sources/showcase/scene.blend",
    "native_companion": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09/indoor_sources/companion_b/scene.blend",
    "botanical_city": ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07/urban_v1_full_07.blend",
    "street_furniture": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_block_10/linked_assets_clean_min/street_furniture.blend",
}
result = {}
for key, path in sources.items():
    if not path.is_file():
        result[key] = {"missing": str(path)}
        continue
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        names = list(source.objects)
        selected = [
            n
            for n in names
            if any(
                t in n.lower()
                for t in (
                    "sofa",
                    "bedfactory",
                    "chairfactory",
                    "tablefactory",
                    "toiletfactory",
                    "sinkfactory",
                    "cabinetfactory",
                    "tree_master",
                    "leaffactory",
                    "bench",
                    "lamp",
                    "bin",
                )
            )
        ]
        result[key] = {
            "path": str(path),
            "objects": selected,
            "collections": list(source.collections),
            "total_objects": len(names),
        }
    print(key, len(names), len(selected), flush=True)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "source_inventory.json").write_text(
    json.dumps(result, indent=2), encoding="utf8"
)
print("ASSET_PROBE_COMPLETE", flush=True)
