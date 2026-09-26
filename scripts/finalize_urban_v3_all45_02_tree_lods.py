"""Replace heavy linked TreeFactory masters with extracted GenericTreeFactory LODs."""

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


import json
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/urban_v3_all45_02"
LOD_BLEND = OUT / "all45_02_treefactory_lods.blend"
MAIN_BLEND = OUT / "urban_v3_all45_02.blend"
AUDIT = OUT / "all45_02_residential_audit.json"
SEEDS = (42, 256, 512, 619, 851)


def main():
    names = [f"all45_02:MASTER_generic_treefactory_{seed}" for seed in SEEDS]
    with bpy.data.libraries.load(str(LOD_BLEND), link=False) as (src, dst):
        missing = [name for name in names if name not in src.collections]
        if missing:
            raise RuntimeError(f"Missing LOD collections: {missing}")
        dst.collections = names
    lods = [coll for coll in dst.collections if coll]
    instances = [
        obj
        for obj in bpy.data.objects
        if obj.instance_type == "COLLECTION"
        and obj.instance_collection
        and obj.instance_collection.get("infinigen_factory")
    ]
    old_masters = {obj.instance_collection for obj in instances}
    for i, obj in enumerate(sorted(instances, key=lambda item: item.name)):
        obj.instance_collection = lods[i % len(lods)]
        obj["tree_lod_source"] = str(LOD_BLEND)
    for coll in old_masters:
        bpy.data.collections.remove(coll, do_unlink=True)
    for obj in list(bpy.data.objects):
        if obj.library and "urban_v3_trees/trees.blend" in obj.library.filepath:
            bpy.data.objects.remove(obj, do_unlink=True)
    for _ in range(3):
        bpy.ops.outliner.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(MAIN_BLEND))

    stats = json.loads(AUDIT.read_text(encoding="utf-8"))
    stats.pop("tree_factory_source_blend", None)
    stats["tree_factory_lod_blend"] = str(LOD_BLEND)
    stats["tree_factory_lod_vertices"] = sum(
        coll.get("lod_vertices", 0) for coll in lods
    )
    stats["object_count"] = len(bpy.data.objects)
    stats["mesh_count"] = len(bpy.data.meshes)
    stats["collection_instances"] = sum(
        obj.instance_type == "COLLECTION" for obj in bpy.data.objects
    )
    AUDIT.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(
        f"[all45_02 finalize] remapped={len(instances)} lods={len(lods)} "
        f"vertices={stats['tree_factory_lod_vertices']} libraries={len(bpy.data.libraries)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
