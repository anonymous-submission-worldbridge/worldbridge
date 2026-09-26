"""Extract five lightweight Infinigen GenericTreeFactory meshes from all41."""

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


from pathlib import Path

import bpy
from mathutils import Matrix, Vector


OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all45_02/all45_02_treefactory_lods.blend"
)
SEEDS = (42, 256, 512, 619, 851)


def find_source(seed):
    token = f"GenericTreeFactory({seed}).spawn_asset(0)"
    matches = [
        obj for obj in bpy.data.objects if token in obj.name and obj.type == "MESH"
    ]
    if not matches:
        raise KeyError(f"Missing {token}")
    return min(matches, key=lambda obj: len(obj.data.vertices))


def normalized_copy(src, seed, index):
    mesh = src.data.copy()
    basis = src.matrix_world.to_3x3().to_4x4()
    mesh.transform(basis)
    points = [Vector(v.co) for v in mesh.vertices]
    cx = (min(p.x for p in points) + max(p.x for p in points)) / 2
    cy = (min(p.y for p in points) + max(p.y for p in points)) / 2
    z0 = min(p.z for p in points)
    mesh.transform(Matrix.Translation((-cx, -cy, -z0)))
    mesh.name = f"all45_02:GenericTreeFactoryLOD_{seed}_mesh"
    obj = bpy.data.objects.new(f"all45_02:GenericTreeFactoryLOD_{seed}", mesh)
    coll = bpy.data.collections.new(f"all45_02:MASTER_generic_treefactory_{seed}")
    bpy.context.scene.collection.children.link(coll)
    coll.objects.link(obj)
    coll["infinigen_factory"] = f"GenericTreeFactory(seed={seed})"
    coll[
        "source_blend"
    ] = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
    coll["source_object"] = src.name
    coll["lod_vertices"] = len(mesh.vertices)
    obj["infinigen_factory"] = coll["infinigen_factory"]
    return obj, coll


def main():
    keep_objects = []
    keep_collections = []
    for index, seed in enumerate(SEEDS):
        obj, coll = normalized_copy(find_source(seed), seed, index)
        keep_objects.append(obj)
        keep_collections.append(coll)

    for obj in list(bpy.data.objects):
        if obj not in keep_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        if coll not in keep_collections:
            bpy.data.collections.remove(coll, do_unlink=True)
    for _ in range(3):
        bpy.ops.outliner.orphans_purge(do_recursive=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
    print(
        "[all45_02 tree LODs]",
        [(seed, len(obj.data.vertices)) for seed, obj in zip(SEEDS, keep_objects)],
        flush=True,
    )


if __name__ == "__main__":
    main()
