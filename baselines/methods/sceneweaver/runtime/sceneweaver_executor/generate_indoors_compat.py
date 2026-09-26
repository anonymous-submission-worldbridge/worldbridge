#!/usr/bin/env python3
"""Memory-safe entry point for SceneWeaver's indoor executor.

SceneWeaver serializes ``state`` both directly and as ``solver.state``.  The
upstream incremental loader deserializes both ~equally-sized object graphs and
then immediately discards the copy embedded in ``solver``.  On shared workers
that transient duplication is enough for the Blender process to receive
SIGKILL.  Reuse the already serialized ``solver.state`` while preserving the
rest of the upstream restore and execution path.
"""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


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


import importlib
import ctypes
import gc
import os
import pickle
import runpy
import sys
from pathlib import Path


BASELINES_ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}/baselines")
SCENEWEAVER_ROOT = BASELINES_ROOT / "vendor/SceneWeaver"
sys.path.insert(0, str(SCENEWEAVER_ROOT))

import bpy  # noqa: E402
import dill  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from infinigen.core import init as infinigen_init  # noqa: E402
from infinigen.core import tagging  # noqa: E402
from infinigen.core.constraints import constraint_language as cl  # noqa: E402
from infinigen.core.constraints.example_solver import propose_relations  # noqa: E402
from infinigen.core.constraints.example_solver.geometry import stability  # noqa: E402
from infinigen.core.constraints.example_solver.geometry import parse_scene  # noqa: E402
from infinigen.core.constraints.example_solver.geometry.planes import (
    Planes,
)  # noqa: E402
from infinigen_examples.steps import record, tools  # noqa: E402
from infinigen_examples.util.visible import visible_layers  # noqa: E402
from infinigen.assets.objaverse_assets import local_retrieve  # noqa: E402


COLLISION_FACE_BUDGET = int(
    os.environ.get("SCENEWEAVER_COLLISION_FACE_BUDGET", "200000")
)
_ORIGINAL_TO_TRIMESH = parse_scene.to_trimesh
_ORIGINAL_PREPROCESS_OBJ = parse_scene.preprocess_obj
_ORIGINAL_TAG_CANONICAL_SURFACES = tagging.tag_canonical_surfaces
_SKIPPED_PREPROCESS: set[str] = set()
_SKIPPED_CANONICAL_TAGGING: set[str] = set()


def install_cycles_device_preference() -> None:
    """Honor an executor-only Cycles fallback selected after a GPU fault."""

    requested = os.environ.get("SCENEWEAVER_CYCLES_DEVICE", "").upper()
    if not requested:
        return
    supported = set(infinigen_init.CYCLES_GPUTYPES_PREFERENCE)
    if requested not in supported:
        raise ValueError(f"Unsupported SceneWeaver Cycles device: {requested!r}")
    infinigen_init.CYCLES_GPUTYPES_PREFERENCE[:] = [requested] + [
        item for item in infinigen_init.CYCLES_GPUTYPES_PREFERENCE if item != requested
    ]
    print(f"SCENEWEAVER_CYCLES_DEVICE device={requested}", flush=True)


def without_unconstrained_relations(relations, any_relation_type):
    """Remove only positive AnyRelation placeholders from explicit solving."""

    return [
        relation
        for relation in relations
        if not isinstance(relation[0], any_relation_type)
    ]


def install_given_assignment_anyrelation_fix() -> None:
    """Avoid dereferencing ``parent_tags`` on an AnyRelation placeholder.

    The upstream function's AnyRelation guard is commented out, while the
    subsequent code still assumes every relation has ``parent_tags``.  These
    unconstrained placeholders add no geometric restriction; explicit floor,
    wall, and parent relations remain in the list and retain full behavior.
    """

    original = propose_relations.find_given_assignments
    if getattr(original, "_sceneweaver_anyrelation_fixed", False):
        return

    def compatible_find_given_assignments(
        curr, relations, assignments=None, parent_obj_name=None
    ):
        explicit = without_unconstrained_relations(relations, cl.AnyRelation)
        removed = len(relations) - len(explicit)
        if removed:
            print(
                "SCENEWEAVER_ANYRELATION_FILTER "
                f"removed={removed} retained={len(explicit)}",
                flush=True,
            )
        return original(
            curr,
            explicit,
            assignments=assignments,
            parent_obj_name=parent_obj_name,
        )

    compatible_find_given_assignments._sceneweaver_anyrelation_fixed = True
    propose_relations.find_given_assignments = compatible_find_given_assignments


def install_plane_projection_fix() -> None:
    """Fix the upstream Y-axis tangent-basis division by zero.

    SceneWeaver's ``anti_project_to_3d`` has the same condition in both arms.
    For a plane normal parallel to the world Y axis it consequently computes
    ``cross(Y, Y)`` and normalizes the zero vector.  Window constraints can
    naturally have exactly that normal, so the resulting NaNs later poison
    plane hashing.  This replacement keeps the intended basis construction
    and fails explicitly only for a genuinely invalid zero/non-finite normal.
    """

    if getattr(stability.anti_project_to_3d, "_sceneweaver_y_axis_fixed", False):
        return

    def anti_project_to_3d(point_2d, normal_b, origin_b=(0, 0, 0)):
        normal = np.asarray(normal_b, dtype=np.float64)
        normal_norm = np.linalg.norm(normal)
        if not np.isfinite(normal_norm) or normal_norm == 0:
            raise ValueError(f"Invalid plane normal for projection: {normal_b!r}")
        normal = normal / normal_norm

        if np.isclose(abs(normal[1]), 1.0, rtol=0.0, atol=1e-12):
            tangent_1 = np.array([1.0, 0.0, 0.0])
        else:
            tangent_1 = np.cross(normal, [0.0, 1.0, 0.0])
            tangent_1 = tangent_1 / np.linalg.norm(tangent_1)
        tangent_2 = np.cross(normal, tangent_1)
        tangent_2 = tangent_2 / np.linalg.norm(tangent_2)

        point = np.asarray(point_2d, dtype=np.float64)
        origin = np.asarray(origin_b, dtype=np.float64)
        return origin + point[0] * tangent_1 + point[1] * tangent_2

    anti_project_to_3d._sceneweaver_y_axis_fixed = True
    stability.anti_project_to_3d = anti_project_to_3d


def install_collision_mesh_budget() -> None:
    """Bound FCL complexity without changing any visible/rendered geometry."""

    if getattr(parse_scene.to_trimesh, "_sceneweaver_budgeted", False):
        return

    def budgeted_preprocess_obj(obj):
        face_count = len(obj.data.polygons)
        if face_count <= COLLISION_FACE_BUDGET:
            return _ORIGINAL_PREPROCESS_OBJ(obj)
        if obj.name not in _SKIPPED_PREPROCESS:
            print(
                "SCENEWEAVER_COLLISION_PREPROCESS_SKIPPED "
                f"object={obj.name!r} faces={face_count} "
                f"budget={COLLISION_FACE_BUDGET}",
                flush=True,
            )
            _SKIPPED_PREPROCESS.add(obj.name)
        # The collision proxy below reads the local bounding box and is then
        # synchronized with the object's complete matrix_world, including its
        # unapplied scale.  Mutating the visible mesh is therefore unnecessary.
        return None

    def budgeted_to_trimesh(obj):
        face_count = len(obj.data.polygons)
        if face_count <= COLLISION_FACE_BUDGET:
            return _ORIGINAL_TO_TRIMESH(obj)
        corners = np.asarray(obj.bound_box, dtype=np.float64)
        lower = corners.min(axis=0)
        upper = corners.max(axis=0)
        extents = np.maximum(upper - lower, 1e-6)
        mesh = trimesh.creation.box(extents=extents)
        mesh.apply_translation((lower + upper) / 2.0)
        mesh.current_transform = trimesh.transformations.identity_matrix()
        print(
            "SCENEWEAVER_COLLISION_PROXY "
            f"object={obj.name!r} faces={face_count} budget={COLLISION_FACE_BUDGET}",
            flush=True,
        )
        return mesh

    def budgeted_tag_canonical_surfaces(obj, *args, **kwargs):
        face_count = len(obj.data.polygons)
        if face_count <= COLLISION_FACE_BUDGET:
            return _ORIGINAL_TAG_CANONICAL_SURFACES(obj, *args, **kwargs)
        if obj.name not in _SKIPPED_CANONICAL_TAGGING:
            print(
                "SCENEWEAVER_COLLISION_TAGGING_SKIPPED "
                f"object={obj.name!r} faces={face_count} "
                f"budget={COLLISION_FACE_BUDGET}",
                flush=True,
            )
            _SKIPPED_CANONICAL_TAGGING.add(obj.name)
        # Oversized assets use a bounding-box collision mesh and therefore
        # cannot preserve a one-to-one render-face tag mask.  Child relation
        # checks still use their lightweight placeholder; visible geometry is
        # left untouched.  Normal-sized supporters retain full canonical tags.
        return None

    budgeted_to_trimesh._sceneweaver_budgeted = True
    budgeted_preprocess_obj._sceneweaver_budgeted = True
    parse_scene.preprocess_obj = budgeted_preprocess_obj
    parse_scene.to_trimesh = budgeted_to_trimesh
    tagging.tag_canonical_surfaces = budgeted_tag_canonical_surfaces


def compact_load_record(iteration: int):
    """Restore one recorded iteration without deserializing duplicate state."""

    install_collision_mesh_budget()
    save_dir = Path(os.environ["save_dir"])
    record_dir = save_dir / "record_files"

    with (record_dir / f"solver_{iteration}.pkl").open("rb") as handle:
        solver = dill.load(handle)
    state = solver.state

    # The persisted scene contains high-poly render meshes (one plant in the
    # first pilot has 1.57M faces).  They have no live FCL handles after
    # serialization, and rebuilding them here is redundant: the normal
    # ``populate_assets`` stage reconstructs those collision meshes after the
    # requested graph edit.  Restore the lightweight placeholders first, as in
    # the initial generation path, and release the serialized mesh arrays
    # before opening the packed .blend file.
    state.trimesh_scene = None
    state.bvh_cache = None
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (AttributeError, OSError):
        pass

    with (record_dir / f"terrain_{iteration}.pkl").open("rb") as handle:
        terrain = pickle.load(handle)
    with (record_dir / f"house_bbox_{iteration}.pkl").open("rb") as handle:
        house_bbox = pickle.load(handle)
    with (record_dir / f"solved_bbox_{iteration}.pkl").open("rb") as handle:
        solved_bbox = pickle.load(handle)

    tagging.tag_system.load_tag(str(record_dir / "MaskTag.json"))
    scene_path = record_dir / f"scene_{iteration}.blend"
    if not bpy.data.objects.get("newroom_0-0"):
        bpy.ops.wm.open_mainfile(
            filepath=str(scene_path), load_ui=False, use_scripts=False
        )
    visible_layers()

    for obj_info in state.objs.values():
        obj_info.obj = bpy.data.objects.get(obj_info.obj)
        tools.recover_attr(
            obj_info.generator,
            tools.is_module,
            lambda attr: importlib.import_module(attr),
        )
        tools.recover_attr(
            obj_info.generator,
            tools.is_material,
            lambda attr: bpy.data.materials.get(attr),
        )
        tools.recover_attr(
            obj_info.generator,
            tools.is_collection,
            lambda attr: bpy.data.collections.get(attr),
        )

    placeholder_objects = [
        obj_info.obj for obj_info in state.objs.values() if obj_info.obj is not None
    ]
    state.trimesh_scene = parse_scene.parse_scene(placeholder_objects)
    # SceneWeaver's relation checks use the populated asset for supporter
    # surfaces, including its original tagged face indices.  Reconstruct that
    # exact collision geometry when it is within the frozen face budget;
    # ``budgeted_to_trimesh`` substitutes a box only for oversized assets.
    # Reusing placeholder boxes for every asset is not sufficient here: an
    # ``on`` relation may legitimately address (for example) face 2336 of a
    # shelf, which would be out of range in a 12-face placeholder box.
    for obj_info in state.objs.values():
        asset_name = getattr(obj_info, "populate_obj", None)
        if not asset_name or asset_name not in bpy.data.objects:
            continue
        asset_obj = bpy.data.objects[asset_name]
        # The recorded blend already contains the triangulated/tagged mesh
        # produced by the preceding population stage.  Do not triangulate a
        # second time, because that could renumber its persisted face tags.
        parse_scene.add_to_scene(state.trimesh_scene, asset_obj, preprocess=False)
    state.planes = Planes()
    state.bvh_cache = {}
    solver.state = state

    with (record_dir / f"env_{iteration}.pkl").open("rb") as handle:
        recorded_environment = pickle.load(handle)
    json_name = os.environ.get("JSON_RESULTS", "")
    os.environ.update(recorded_environment)
    os.environ["save_dir"] = str(save_dir)
    os.environ["JSON_RESULTS"] = json_name
    return state, solver, terrain, house_bbox, solved_bbox, None


def main() -> None:
    # ``generate_indoors`` calls ``record.load_scene``; patch both names for
    # completeness because other executor modules import ``load_record``.
    install_collision_mesh_budget()
    install_plane_projection_fix()
    install_given_assignment_anyrelation_fix()
    install_cycles_device_preference()
    local_retrieve.ALIASES.setdefault("lshapedsofa", ("l shaped sofa",))
    tools.load_record = compact_load_record
    record.load_record = compact_load_record
    record.load_scene = compact_load_record
    runpy.run_module("infinigen_examples.generate_indoors", run_name="__main__")


if __name__ == "__main__":
    main()
