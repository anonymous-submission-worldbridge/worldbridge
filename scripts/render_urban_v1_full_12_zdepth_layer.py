#!/usr/bin/env python3
"""Render exact full-12 placement layers with camera-space Z passes.

This is the resource-safe renderer for the production full-12 Blend.  It does
not remodel, simplify, rescale, or save any city asset.  A temporary in-memory
scene first contains copies of the production placement *empties*.  For asset
partitions, Blender's render-breaking Empty-instance indirection is then
expanded into transient object shells which share the exact authored data,
materials, and modifiers at their dependency-graph world matrices.  Each
asset layer uses one ``Combined`` view containing the selected exact
placements plus the same authored ground/road receivers. The 32-bit
CombinedDepth pass is compared
pixel-for-pixel with the separately rendered exact BaseDepth pass during final
composition.  Pixels nearer than BaseDepth are the exact visible asset
surfaces; equal-depth pixels retain the layer's shadows/reflections on the
common receivers.

This combined-depth formulation avoids Blender Workbench 5.1's background bug
where an asset-only first view can return an uninitialized pass: the exact
receivers guarantee non-empty geometry in every partition. A separate driver
bug returned empty high-resolution buffers for dense linked Empty instances;
the exact transient object-shell expansion removes that indirection and each
source is rasterized once on the native 1920x1080 target grid. There is no
resize, resampling, interpolation, color conversion, or depth quantization.
The two linked sources whose live Geometry Nodes poison Workbench are
represented by exact dependency-graph evaluated meshes/instances in memory;
no visible geometry is omitted, simplified, or changed, and no source or
production Blend is saved.

The ``base`` layer renders the common ground/roads plus an exact transparent
camera no-hit mask; the delivery compositor supplies the daytime sky once. The
production Blend is the authoritative source and is never written by this
script.
"""

from __future__ import annotations

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

_wb_WORLDBRIDGE_PYTHON = _wb_paths["WORLDBRIDGE_PYTHON"]


import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import bpy
import numpy as np
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND = CITY / f"{REVISION}.blend"
LAYOUT = CITY / "layout_plan.json"
_DEFAULT_LAYER_ROOT = CITY / "renders" / "zdepth_layers"
LAYER_ROOT = Path(
    os.environ.get("C2W_FULL12_LAYER_ROOT", str(_DEFAULT_LAYER_ROOT))
).resolve()
if not LAYER_ROOT.is_relative_to(CITY.resolve()):
    raise RuntimeError("C2W_FULL12_LAYER_ROOT must remain inside the full-12 output")
RENDERER_PATH = ROOT / "scripts" / "render_urban_v1_full_12_daytime.py"
EXR_PROCESSOR_PATH = ROOT / "scripts" / "process_urban_v1_full_12_exr.py"
EXR_PROCESSOR_PYTHON = Path(
    os.environ.get(
        "C2W_FULL12_OPENEXR_PYTHON",
        f"{_wb_WORLDBRIDGE_PYTHON}",
    )
).resolve()
TEMP_PREFIX = "__full12_zdepth_tmp__"
GN_REALIZATION_PLACEMENTS = {
    "park_river5_corridor",
    "education_artificial_lake_civic_enclosure",
}
PERSISTENT_ID_SENTINEL = 2_147_483_647
MIN_NONDEGENERATE_EXR_BYTES = 256 * 1024
# A degenerate Workbench buffer is process-state corruption on this Blender
# build; repeating in the same process only wastes another full raster.  The
# chunk driver retries the incomplete batch in a fresh Blender process and the
# renderer skips every previously validated atomic frame.
MAX_FRAME_RENDER_ATTEMPTS = 1
MAX_WORLD_MATRIX_ABSOLUTE_ERROR = 1.0e-4
MAX_WORLD_MATRIX_RELATIVE_ERROR = 5.0e-7


# These groups partition every non-structural production placement.  Splits
# follow source complexity rather than city visibility: the final Z composite
# includes all groups in every view.
LAYER_SPECS: dict[str, dict[str, set[str]]] = {
    "base": {"collision_classes": {"base", "road", "road_amenity"}},
    "river5_nature": {
        "placement_ids": {
            "park_original_sculpture_nature",
            "park_river5_corridor",
        }
    },
    "river3_residential": {"source_keys": {"river3"}},
    "all45_unique_buildings": {"source_keys": {"all45_09"}},
    "all44_leisure": {"source_keys": {"all44_14"}},
    "commercial_services": {
        "source_keys": {"commercial25", "pharmacy5", "atm4", "bank5"}
    },
    "residential_delivery": {"source_keys": {"delivery6"}},
    "park_leisure_support": {"source_keys": {"fitness5", "fountain3"}},
    "artificial_lake": {"source_keys": {"lake3"}},
    "education_buildings": {"source_keys": {"school5", "library4"}},
    "public_safety": {"source_keys": {"fire7", "police3"}},
    "health": {"source_keys": {"hospital4"}},
    "industrial": {"source_keys": {"factory3", "gas4"}},
}
LAYERS = tuple(LAYER_SPECS)


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "full12_direct_renderer_shared", RENDERER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load renderer helpers from {RENDERER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def record_selected(record: dict[str, Any], layer_key: str) -> bool:
    spec = LAYER_SPECS[layer_key]
    if record.get("collision_class") in spec.get("collision_classes", set()):
        return True
    if record.get("placement_id") in spec.get("placement_ids", set()):
        return True
    if record.get("source_key") in spec.get("source_keys", set()):
        return True
    return False


def validate_partition(layout: dict[str, Any]) -> dict[str, str]:
    assignment: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    for record in layout["placements"]:
        matches = [
            layer_key for layer_key in LAYERS if record_selected(record, layer_key)
        ]
        if len(matches) != 1:
            duplicates[record["placement_id"]] = matches
        else:
            assignment[record["placement_id"]] = matches[0]
    if duplicates:
        raise RuntimeError(
            "Z-depth layer partition must cover each placement exactly once: "
            + json.dumps(duplicates, ensure_ascii=False, sort_keys=True)
        )
    return assignment


def copy_placement_roots(
    source_scene: bpy.types.Scene,
    target_collection: bpy.types.Collection,
    records: Iterable[dict[str, Any]],
) -> list[bpy.types.Object]:
    copies = []
    for record in records:
        source = bpy.data.objects.get(record["name"])
        if source is None or source.name not in source_scene.objects:
            source = next(
                (
                    obj
                    for obj in source_scene.objects
                    if obj.get("placement_id") == record["placement_id"]
                ),
                None,
            )
        if source is None:
            raise RuntimeError(
                f"Production placement root missing: {record['placement_id']}"
            )
        if source.instance_type != "COLLECTION" or source.instance_collection is None:
            raise RuntimeError(
                f"Production root is not an exact collection instance: {source.name}"
            )
        if source.parent is not None:
            raise RuntimeError(
                "Production placement roots must remain parentless for exact "
                f"render repacking: {source.name}"
            )
        # Reconstruct the authoritative placement transform from the same
        # fields and matrix order used by generate_urban_v1_full_10.place().
        # This is robust both for the production Blend and for dependency-only
        # render packs opened with --disable-depsgraph-on-file-load, where an
        # unevaluated matrix_world may be identity.
        at = tuple(float(value) for value in record["location"])
        center = tuple(float(value) for value in record["source_center"])
        yaw = float(record["yaw_radians"])
        production_basis = (
            Matrix.Translation(at)
            @ Matrix.Rotation(yaw, 4, "Z")
            @ Matrix.Translation((-center[0], -center[1], 0.0))
        )
        duplicate = source.copy()
        duplicate.name = f"{TEMP_PREFIX}:{record['placement_id']}"
        # Link first, then reassert the serialized production transform.  A
        # never-linked Blender object may otherwise receive an identity basis
        # when it first enters a Scene graph.
        duplicate.instance_type = "COLLECTION"
        duplicate.instance_collection = source.instance_collection
        duplicate.hide_viewport = False
        duplicate.hide_render = False
        target_collection.objects.link(duplicate)
        duplicate.matrix_basis = production_basis
        duplicate[
            "render_transform_source"
        ] = "production place() formula from layout location/yaw/source_center"
        if any(
            abs(duplicate.matrix_basis[row][column] - production_basis[row][column])
            > 1e-6
            for row in range(4)
            for column in range(4)
        ):
            raise RuntimeError(
                f"Failed to preserve serialized placement transform: {source.name}"
            )
        copies.append(duplicate)
    return copies


def layer_collection(
    view_layer: bpy.types.ViewLayer, collection_name: str
) -> bpy.types.LayerCollection:
    stack = [view_layer.layer_collection]
    while stack:
        current = stack.pop()
        if current.collection.name == collection_name:
            return current
        stack.extend(current.children)
    raise RuntimeError(
        f"Layer collection {collection_name!r} not found in {view_layer.name}"
    )


def configure_view_layers(
    scene: bpy.types.Scene,
    layer_key: str,
    base_collection: bpy.types.Collection,
    asset_collection: bpy.types.Collection,
) -> list[str]:
    primary = scene.view_layers[0]
    if layer_key == "base":
        primary.name = "Base"
        layer_collection(primary, asset_collection.name).exclude = True
        primary.use_pass_z = True
        return [primary.name]

    primary.name = "Combined"
    layer_collection(primary, base_collection.name).exclude = False
    layer_collection(primary, asset_collection.name).exclude = False
    primary.use_pass_z = True
    return [primary.name]


def compact_persistent_id(instance: Any) -> tuple[int, ...]:
    return tuple(
        int(value)
        for value in instance.persistent_id
        if int(value) != PERSISTENT_ID_SENTINEL
    )


def realize_problematic_visible_geometry_nodes(
    scene: bpy.types.Scene,
    asset_collection: bpy.types.Collection,
    asset_copies: Sequence[bpy.types.Object],
) -> dict[str, Any]:
    """Bake only renderer-breaking visible GN results into transient meshes.

    Blender Workbench 5.1 returns an uninitialized render for the authored
    river-water displacement and lake scatter modifiers when they are reached
    through a deeply nested linked collection instance.  Their evaluated
    results are nevertheless available from the dependency graph.  Copy those
    exact evaluated meshes/instances into this process-local render collection,
    then hide the precisely replaced controller.  Nothing is simplified,
    realized in the production Blend, or saved back to a source library.
    """

    roots = [
        root
        for root in asset_copies
        if root.get("placement_id") in GN_REALIZATION_PLACEMENTS
    ]
    if not roots:
        return {
            "enabled": False,
            "reason": "layer has no renderer-breaking visible GN placements",
            "controller_count": 0,
            "replacement_object_count": 0,
            "replacement_polygon_count": 0,
            "omitted_visible_geometry_count": 0,
            "source_files_saved": False,
            "production_blend_saved": False,
        }

    for view_layer in scene.view_layers:
        view_layer.update()
    if bpy.context.scene != scene:
        raise RuntimeError("GN evaluation context is not the temporary render scene")
    evaluation_view_layer = scene.view_layers.get("Combined") or scene.view_layers[0]
    # Evaluate authored GN from the authoritative Combined dependency graph,
    # where every selected asset root and exact shared receiver is present.
    if bpy.context.window is not None:
        bpy.context.window.view_layer = evaluation_view_layer
    if bpy.context.view_layer != evaluation_view_layer:
        raise RuntimeError(
            "Could not activate the authoritative Combined view layer for GN evaluation"
        )
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    # DepsgraphObjectInstance wrappers are iterator-owned and become invalid
    # as soon as the iterator advances. Snapshot only stable IDs and copied
    # values while each wrapper is alive.
    instances = []
    for instance in depsgraph.object_instances:
        instances.append(
            {
                "is_instance": bool(instance.is_instance),
                "parent_original": (
                    instance.parent.original if instance.parent is not None else None
                ),
                "object_original": (
                    instance.object.original if instance.object is not None else None
                ),
                "matrix_world": instance.matrix_world.copy(),
                "persistent_id": compact_persistent_id(instance),
            }
        )
    replacement_objects: list[bpy.types.Object] = []
    replacement_meshes: list[bpy.types.Mesh] = []
    controller_records: list[dict[str, Any]] = []

    for root in roots:
        source_collection = root.instance_collection
        if source_collection is None:
            raise RuntimeError(f"GN realization root has no collection: {root.name}")
        controllers = []
        for item in source_collection.all_objects:
            visible_modifiers = [
                modifier
                for modifier in item.modifiers
                if modifier.type == "NODES" and modifier.show_render
            ]
            if visible_modifiers:
                controllers.append((item, visible_modifiers))

        for controller, modifiers in controllers:
            direct = [
                instance
                for instance in instances
                if instance["is_instance"]
                and instance["parent_original"] == root
                and instance["object_original"] == controller
            ]
            if len(direct) != 1:
                raise RuntimeError(
                    "Expected one evaluated controller instance for "
                    f"{root.get('placement_id')}:{controller.name_full}, got {len(direct)}"
                )
            controller_instance = direct[0]
            controller_pid = controller_instance["persistent_id"]
            if not controller_pid:
                raise RuntimeError(
                    f"Missing persistent id for GN controller {controller.name_full}"
                )

            direct_original = controller_instance["object_original"]
            direct_evaluated = direct_original.evaluated_get(depsgraph)
            direct_probe = bpy.data.meshes.new_from_object(
                direct_evaluated,
                preserve_all_data_layers=True,
                depsgraph=depsgraph,
            )
            direct_has_mesh = bool(direct_probe.polygons)
            bpy.data.meshes.remove(direct_probe)
            evaluated_parts = [controller_instance]
            # A GN result with its own mesh component (the river/lake water)
            # is complete in the direct evaluated object. Only a pure
            # instance output (the lake flower scatter) needs its descendant
            # instances copied. Persistent IDs are stored inner-to-outer, so
            # generated leaves end with the controller's exact ID tuple.
            if not direct_has_mesh:
                evaluated_parts.extend(
                    instance
                    for instance in instances
                    if instance["is_instance"]
                    and instance["parent_original"] == root
                    and instance["object_original"] is not None
                    and len(instance["persistent_id"]) > len(controller_pid)
                    and instance["persistent_id"][-len(controller_pid) :]
                    == controller_pid
                )
            mesh_cache: dict[int, bpy.types.Mesh] = {}
            created_for_controller = 0
            polygons_for_controller = 0
            for part_index, instance in enumerate(evaluated_parts):
                original_object = instance["object_original"]
                if original_object is None or original_object.type != "MESH":
                    continue
                cache_key = original_object.as_pointer()
                mesh = mesh_cache.get(cache_key)
                if mesh is None:
                    evaluated_object = original_object.evaluated_get(depsgraph)
                    mesh = bpy.data.meshes.new_from_object(
                        evaluated_object,
                        preserve_all_data_layers=True,
                        depsgraph=depsgraph,
                    )
                    if not mesh.polygons:
                        bpy.data.meshes.remove(mesh)
                        continue
                    mesh.name = (
                        f"{TEMP_PREFIX}:evaluated_gn_mesh:"
                        f"{root.get('placement_id')}:{controller.name}:{part_index:04d}"
                    )
                    mesh_cache[cache_key] = mesh
                    replacement_meshes.append(mesh)
                replacement = bpy.data.objects.new(
                    f"{TEMP_PREFIX}:evaluated_gn:{root.get('placement_id')}:"
                    f"{controller.name}:{part_index:04d}",
                    mesh,
                )
                replacement["exact_evaluated_gn_replacement"] = True
                replacement["source_placement_id"] = root.get("placement_id")
                replacement["source_controller"] = controller.name_full
                asset_collection.objects.link(replacement)
                replacement.matrix_world = instance["matrix_world"]
                replacement_objects.append(replacement)
                created_for_controller += 1
                polygons_for_controller += len(mesh.polygons)

            if created_for_controller == 0:
                related = [
                    {
                        "object": instance["object_original"].name_full,
                        "type": instance["object_original"].type,
                        "persistent_id": list(instance["persistent_id"]),
                    }
                    for instance in evaluated_parts[:12]
                    if instance["object_original"] is not None
                ]
                raise RuntimeError(
                    "Visible GN controller produced no renderable exact replacements: "
                    f"{root.get('placement_id')}:{controller.name_full}; "
                    f"evaluated_parts={related}"
                )
            controller.hide_render = True
            controller.hide_viewport = True
            for modifier in modifiers:
                modifier.show_render = False
                modifier.show_viewport = False
            controller_records.append(
                {
                    "placement_id": root.get("placement_id"),
                    "controller": controller.name_full,
                    "modifier_names": [modifier.name for modifier in modifiers],
                    "controller_persistent_id": list(controller_pid),
                    "replacement_object_count": created_for_controller,
                    "replacement_polygon_references": polygons_for_controller,
                    "exact_evaluated_geometry": True,
                }
            )

    result = {
        "enabled": True,
        "method": (
            "dependency-graph evaluated GN mesh and instance copies in transient "
            "render scene; precisely replaced controllers hidden in memory only"
        ),
        "evaluation_view_layer": evaluation_view_layer.name,
        "controller_count": len(controller_records),
        "controllers": controller_records,
        "replacement_object_count": len(replacement_objects),
        "replacement_unique_mesh_count": len(replacement_meshes),
        "replacement_polygon_count": sum(
            len(mesh.polygons) for mesh in replacement_meshes
        ),
        "omitted_visible_geometry_count": 0,
        "geometry_simplification": False,
        "node_graphs_changed": False,
        "source_files_saved": False,
        "production_blend_saved": False,
    }
    return result


def matrix_maximum_error(left: Matrix, right: Matrix) -> float:
    return max(
        abs(left[row][column] - right[row][column])
        for row in range(4)
        for column in range(4)
    )


def assign_exact_affine_transform(
    duplicate: bpy.types.Object,
    expected: Matrix,
    asset_collection: bpy.types.Collection,
    index: int,
) -> tuple[list[bpy.types.Object], float, float]:
    """Represent any affine instance matrix with exact Blender TRS objects.

    A single Blender Object stores translation, rotation, and scale but not
    shear.  Nested authored collections can legitimately produce an affine
    world matrix with shear (for example, a rotated awning below a nonuniform
    scale).  SVD factors the 3x3 matrix into rotation * signed scale * rotation,
    each exactly representable by one parented TRS object.  The visible child
    still shares its original data and retains its modifiers.
    """

    location, rotation, scale = expected.decompose()
    single_trs = (
        Matrix.Translation(location)
        @ rotation.to_matrix().to_4x4()
        @ Matrix.Diagonal((*scale, 1.0))
    )
    affine_residual = matrix_maximum_error(expected, single_trs)
    if affine_residual <= 1.0e-5:
        duplicate.parent = None
        duplicate.matrix_basis = expected
        return [], affine_residual, 0.0

    linear = np.array(
        [[float(expected[row][column]) for column in range(3)] for row in range(3)],
        dtype=np.float64,
    )
    left, singular, right = np.linalg.svd(linear)
    if np.linalg.det(left) < 0.0:
        left[:, -1] *= -1.0
        singular[-1] *= -1.0
    if np.linalg.det(right) < 0.0:
        right[-1, :] *= -1.0
        singular[-1] *= -1.0
    reconstructed = left @ np.diag(singular) @ right
    factorization_error = float(np.max(np.abs(reconstructed - linear)))
    if factorization_error > 1.0e-10:
        raise RuntimeError(
            "Could not factor exact affine instance transform: "
            f"error={factorization_error}"
        )

    left_matrix = Matrix.Identity(4)
    right_matrix = Matrix.Identity(4)
    scale_matrix = Matrix.Identity(4)
    for row in range(3):
        for column in range(3):
            left_matrix[row][column] = float(left[row, column])
            right_matrix[row][column] = float(right[row, column])
        scale_matrix[row][row] = float(singular[row])
    left_matrix.translation = expected.to_translation()

    rotation_parent = bpy.data.objects.new(
        f"{TEMP_PREFIX}:affine_rotation:{index:06d}", None
    )
    scale_parent = bpy.data.objects.new(f"{TEMP_PREFIX}:affine_scale:{index:06d}", None)
    for helper in (rotation_parent, scale_parent):
        helper["exact_affine_instance_transform_helper"] = True
        helper.hide_render = False
        helper.hide_viewport = False
        asset_collection.objects.link(helper)
    rotation_parent.matrix_basis = left_matrix
    scale_parent.parent = rotation_parent
    scale_parent.matrix_parent_inverse = Matrix.Identity(4)
    scale_parent.matrix_basis = scale_matrix
    duplicate.parent = scale_parent
    duplicate.matrix_parent_inverse = Matrix.Identity(4)
    duplicate.matrix_basis = right_matrix
    duplicate["exact_affine_svd_factorization"] = True
    duplicate["affine_residual_if_single_trs"] = affine_residual
    duplicate["svd_factorization_error"] = factorization_error
    return [rotation_parent, scale_parent], affine_residual, factorization_error


def expand_exact_visible_asset_instances(
    scene: bpy.types.Scene,
    asset_collection: bpy.types.Collection,
    asset_copies: Sequence[bpy.types.Object],
) -> dict[str, Any]:
    """Remove only the transient collection-instance render indirection.

    Blender Workbench 5.1 can return an initialized EXR header with an empty
    1920x1080 payload when a sufficiently dense linked collection is reached
    through an Empty instance.  The authored object/data/material/modifier
    graph itself renders correctly.  In the process-local scene, make an
    object shell for every exact dependency-graph instance, share its authored
    data, preserve its evaluated world matrix and modifier configuration, and
    then hide only the now-redundant temporary placement Empty.  Affine shear
    is represented exactly by an SVD-derived rotation/scale/rotation parent
    chain because a single Blender TRS object cannot store shear.  This does
    not realize mesh data, apply modifiers, rescale geometry, edit a source,
    or save any Blend.
    """

    roots = list(asset_copies)
    if not roots:
        return {
            "enabled": False,
            "reason": "base layer has no asset collection instances",
            "placement_root_count": 0,
            "expanded_object_count": 0,
            "omitted_visible_geometry_count": 0,
            "source_data_copied": False,
            "source_files_saved": False,
            "production_blend_saved": False,
        }

    combined = scene.view_layers.get("Combined")
    if combined is None:
        raise RuntimeError("Exact asset expansion requires the Combined view layer")
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
        bpy.context.window.view_layer = combined
    for view_layer in scene.view_layers:
        view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()

    root_set = set(roots)
    renderable_types = {
        "MESH",
        "CURVE",
        "SURFACE",
        "META",
        "FONT",
        "VOLUME",
        "POINTCLOUD",
    }
    snapshots: list[dict[str, Any]] = []
    for instance in depsgraph.object_instances:
        parent_original = (
            instance.parent.original if instance.parent is not None else None
        )
        object_original = (
            instance.object.original if instance.object is not None else None
        )
        if (
            not instance.is_instance
            or parent_original not in root_set
            or object_original is None
            or object_original.type not in renderable_types
            or object_original.hide_render
            or (hasattr(instance, "show_self") and not instance.show_self)
        ):
            continue
        snapshots.append(
            {
                "root": parent_original,
                "original": object_original,
                "matrix_world": instance.matrix_world.copy(),
                "persistent_id": compact_persistent_id(instance),
            }
        )
    snapshots.sort(
        key=lambda item: (
            str(item["root"].get("placement_id", item["root"].name_full)),
            tuple(item["persistent_id"]),
            item["original"].name_full,
        )
    )
    counts_by_root = {root: 0 for root in roots}
    for item in snapshots:
        counts_by_root[item["root"]] += 1
    empty_roots = [
        str(root.get("placement_id", root.name_full))
        for root, count in counts_by_root.items()
        if count == 0
    ]
    if empty_roots:
        raise RuntimeError(
            "Asset placement produced no visible renderable instances: "
            + ", ".join(sorted(empty_roots))
        )

    expanded: list[bpy.types.Object] = []
    affine_helpers: list[bpy.types.Object] = []
    expected_matrices: list[tuple[bpy.types.Object, Matrix, bpy.types.Object]] = []
    type_counts: dict[str, int] = {}
    modifier_type_counts: dict[str, int] = {}
    modifier_count = 0
    polygon_reference_count = 0
    shared_data_count = 0
    constraint_count = 0
    sheared_object_count = 0
    maximum_single_trs_residual = 0.0
    maximum_svd_factorization_error = 0.0
    for index, item in enumerate(snapshots):
        original = item["original"]
        duplicate = original.copy()
        duplicate.name = (
            f"{TEMP_PREFIX}:expanded:{index:06d}:"
            f"{item['root'].get('placement_id', 'placement')}:{original.name}"
        )
        duplicate.parent = None
        duplicate.hide_render = False
        duplicate.hide_viewport = False
        duplicate["exact_collection_instance_expansion"] = True
        duplicate["source_object"] = original.name_full
        duplicate["source_placement_id"] = item["root"].get("placement_id")
        duplicate["source_persistent_id"] = list(item["persistent_id"])
        asset_collection.objects.link(duplicate)
        # Dependency-only packs opened with --disable-depsgraph-on-file-load
        # can expose an identity matrix_world on linked source objects even
        # when their authored matrix_basis is non-identity.  The exact
        # dependency-graph instance matrix is already a world-space matrix.
        # A normal affine transform is assigned directly; a genuine sheared
        # transform is factored into exact parented TRS matrices without
        # touching the visible object's authored data or modifiers.
        helpers, affine_residual, factorization_error = assign_exact_affine_transform(
            duplicate,
            item["matrix_world"],
            asset_collection,
            index,
        )
        affine_helpers.extend(helpers)
        if helpers:
            sheared_object_count += 1
        maximum_single_trs_residual = max(maximum_single_trs_residual, affine_residual)
        maximum_svd_factorization_error = max(
            maximum_svd_factorization_error, factorization_error
        )

        if getattr(original, "data", None) is not None:
            if duplicate.data is not original.data:
                raise RuntimeError(
                    f"Expanded object copied authored data: {original.name_full}"
                )
            shared_data_count += 1
        source_modifier_signature = [
            (modifier.name, modifier.type, modifier.show_render)
            for modifier in original.modifiers
        ]
        duplicate_modifier_signature = [
            (modifier.name, modifier.type, modifier.show_render)
            for modifier in duplicate.modifiers
        ]
        if duplicate_modifier_signature != source_modifier_signature:
            raise RuntimeError(
                f"Expanded object changed modifiers: {original.name_full}"
            )
        modifier_count += len(original.modifiers)
        constraint_count += len(original.constraints)
        for modifier in original.modifiers:
            modifier_type_counts[modifier.type] = (
                modifier_type_counts.get(modifier.type, 0) + 1
            )
        if original.type == "MESH" and original.data is not None:
            polygon_reference_count += len(original.data.polygons)
        type_counts[original.type] = type_counts.get(original.type, 0) + 1
        expanded.append(duplicate)
        expected_matrices.append((duplicate, item["matrix_world"], original))

    for root in roots:
        root.hide_render = True
        root.hide_viewport = True
    for view_layer in scene.view_layers:
        view_layer.update()
    matrix_mismatches = []
    maximum_world_matrix_error = 0.0
    maximum_world_matrix_relative_error = 0.0
    for duplicate, expected, original in expected_matrices:
        maximum_error = max(
            abs(duplicate.matrix_world[row][column] - expected[row][column])
            for row in range(4)
            for column in range(4)
        )
        maximum_world_matrix_error = max(maximum_world_matrix_error, maximum_error)
        reference_scale = max(
            1.0,
            max(abs(expected[row][column]) for row in range(3) for column in range(3)),
        )
        relative_error = maximum_error / reference_scale
        maximum_world_matrix_relative_error = max(
            maximum_world_matrix_relative_error, relative_error
        )
        if (
            maximum_error > MAX_WORLD_MATRIX_ABSOLUTE_ERROR
            and relative_error > MAX_WORLD_MATRIX_RELATIVE_ERROR
        ):
            matrix_mismatches.append(
                {
                    "object": duplicate.name_full,
                    "source": original.name_full,
                    "maximum_error": maximum_error,
                    "relative_error": relative_error,
                    "expected": [list(row) for row in expected],
                    "actual_world": [list(row) for row in duplicate.matrix_world],
                    "actual_basis": [list(row) for row in duplicate.matrix_basis],
                    "location": list(duplicate.location),
                    "rotation_euler": list(duplicate.rotation_euler),
                    "scale": list(duplicate.scale),
                    "delta_location": list(duplicate.delta_location),
                    "delta_rotation_euler": list(duplicate.delta_rotation_euler),
                    "delta_scale": list(duplicate.delta_scale),
                    "constraint_count": len(duplicate.constraints),
                    "has_animation_data": duplicate.animation_data is not None,
                    "rigid_body": duplicate.rigid_body is not None,
                }
            )
    if matrix_mismatches:
        raise RuntimeError(
            "Expanded object world matrices changed after dependency update: "
            + json.dumps(matrix_mismatches[:3], sort_keys=True)
        )

    return {
        "enabled": True,
        "method": (
            "process-local exact dependency-graph collection-instance object "
            "shells with shared authored data and preserved world matrices"
        ),
        "evaluation_view_layer": combined.name,
        "placement_root_count": len(roots),
        "expanded_object_count": len(expanded),
        "affine_transform_helper_count": len(affine_helpers),
        "sheared_object_count": sheared_object_count,
        "exact_svd_affine_factorization": True,
        "maximum_single_trs_residual": maximum_single_trs_residual,
        "maximum_svd_factorization_error": maximum_svd_factorization_error,
        "expanded_object_types": dict(sorted(type_counts.items())),
        "shared_authored_data_count": shared_data_count,
        "source_modifier_count": modifier_count,
        "source_modifier_types": dict(sorted(modifier_type_counts.items())),
        "source_constraint_count": constraint_count,
        "source_polygon_reference_count": polygon_reference_count,
        "all_world_matrices_preserved": True,
        "maximum_world_matrix_error": maximum_world_matrix_error,
        "maximum_world_matrix_relative_error": (maximum_world_matrix_relative_error),
        "maximum_world_matrix_absolute_error_allowed": (
            MAX_WORLD_MATRIX_ABSOLUTE_ERROR
        ),
        "maximum_world_matrix_relative_error_allowed": (
            MAX_WORLD_MATRIX_RELATIVE_ERROR
        ),
        "all_authored_data_shared": shared_data_count == len(expanded),
        "modifiers_applied": False,
        "mesh_data_realized": False,
        "geometry_simplification": False,
        "source_scale_changed": False,
        "placement_roots_hidden_after_exact_expansion": True,
        "omitted_visible_geometry_count": 0,
        "source_data_copied": False,
        "source_files_saved": False,
        "production_blend_saved": False,
        "per_placement_object_counts": {
            str(root.get("placement_id", root.name_full)): counts_by_root[root]
            for root in sorted(
                roots,
                key=lambda item: str(item.get("placement_id", item.name_full)),
            )
        },
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_exr(path: Path) -> bool:
    try:
        # A silently uninitialized 1920x1080 Workbench bundle can still be a
        # structurally valid, highly compressed EXR. Every real full-12 camera
        # hits the shared road/ground receiver and all verified bundles are far
        # larger.
        # Rejecting the degenerate constant payload here makes resume/skip and
        # final completion content-aware instead of header-only.
        return (
            path.stat().st_size >= MIN_NONDEGENERATE_EXR_BYTES
            and path.read_bytes()[:4] == b"v/1\x01"
        )
    except OSError:
        return False


def configure_exr(scene: bpy.types.Scene, layer_key: str) -> None:
    # Keep the camera no-hit mask in alpha for every layer, including the
    # common base.  The final compositor replaces only those exact no-hit
    # pixels with the daytime sky; geometry, receiver shadows, and Z remain
    # the unmodified Workbench rasterization.
    scene.render.film_transparent = True
    # Blender 5.1 removed the OPEN_EXR_MULTILAYER enum.  Individual 32-bit
    # color and Z files are therefore written by compositor File Output nodes.
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.use_single_layer = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "32"
    scene.render.image_settings.exr_codec = "ZIP"
    scene.render.use_file_extension = True
    scene.render.use_simplify = False
    if hasattr(scene.render, "use_persistent_data"):
        # Disabled by default because stale Workbench state previously
        # returned valid-header/all-zero passes. A diagnostic-only environment
        # switch exists to measure persistence only on independently
        # content-validated diagnostic paths.
        scene.render.use_persistent_data = (
            os.environ.get("C2W_FULL12_PERSISTENT_DATA", "0") == "1"
        )


def setup_output_compositor(
    scene: bpy.types.Scene, view_layer_names: Sequence[str]
) -> dict[str, bpy.types.Node]:
    group = bpy.data.node_groups.new(
        f"{TEMP_PREFIX}:compositor:{scene.name}", "CompositorNodeTree"
    )
    scene.compositing_node_group = group
    scene.use_nodes = True
    scene.render.use_compositing = True
    output = group.nodes.new("CompositorNodeOutputFile")
    output.name = f"{TEMP_PREFIX}:output:bundle"
    output.label = "authoritative exact color + camera-space depth bundle"
    output.directory = str(LAYER_ROOT)
    output.file_name = ".writing_bundle"
    output.format.color_depth = "32"
    output.format.exr_codec = "ZIP"
    outputs = {"bundle": output}
    for view_layer_name in view_layer_names:
        render_layer = group.nodes.new("CompositorNodeRLayers")
        render_layer.name = f"{TEMP_PREFIX}:rlayer:{view_layer_name}"
        render_layer.layer = view_layer_name
        if "Depth" not in render_layer.outputs:
            raise RuntimeError(
                f"Depth pass missing from compositor layer {view_layer_name}"
            )
        color_name = f"{view_layer_name}Color"
        depth_name = f"{view_layer_name}Depth"
        output.file_output_items.new("RGBA", color_name)
        output.file_output_items.new("FLOAT", depth_name)
        group.links.new(render_layer.outputs["Image"], output.inputs[color_name])
        group.links.new(render_layer.outputs["Depth"], output.inputs[depth_name])
    # Do not attach the render layer to a second sink, including Group Output.
    # The typed File Output is the authoritative product and every native
    # target-resolution bundle is independently reopened before promotion.
    return outputs


def render_bundle_paths(
    output_directory: Path, shot_stem: str, layer_key: str
) -> dict[str, Path]:
    return {"bundle": output_directory / f"{shot_stem}.exr"}


def valid_bundle(paths: dict[str, Path]) -> bool:
    return bool(paths) and all(valid_exr(path) for path in paths.values())


def frame_dependency_hash(layer_key: str) -> str | None:
    """Revision wrappers may supply a full content hash for safe reuse."""
    return None


def reusable_frame_record(
    record: dict[str, Any] | None,
    layer_key: str,
    targets: dict[str, Path],
    shot: Any,
) -> bool:
    if not record or not valid_bundle(targets):
        return False
    bundle = targets.get("bundle")
    if bundle is None:
        return False
    expected_parts = (
        ["BaseColor", "BaseDepth"]
        if layer_key == "base"
        else ["CombinedColor", "CombinedDepth"]
    )
    evidence = record.get("authoritative_exr_validation", {})
    projection = record.get("camera", {}).get("target_grid_projection", {})
    settings = record.get("render_settings", {})
    expansion = record.get("exact_collection_instance_expansion", {})
    expected_expansion = layer_key != "base"
    expected_dependency_hash = frame_dependency_hash(layer_key)
    frame_engine = settings.get("engine")
    shadow_quality = settings.get("eevee_shadow_quality")
    eevee_quality_valid = frame_engine not in {
        "BLENDER_EEVEE",
        "BLENDER_EEVEE_NEXT",
    } or (
        isinstance(shadow_quality, dict)
        and shadow_quality.get("policy")
        == "full12_complete_virtual_shadow_residency_v1"
        and shadow_quality.get("pool_size_mb") == 1024
        and shadow_quality.get("resolution_scale") == 0.5
        and shadow_quality.get("missing_shadow_pages_allowed") is False
    )
    return bool(
        record.get("status") == "rendered"
        and (
            expected_dependency_hash is None
            or record.get("render_dependency_hash") == expected_dependency_hash
        )
        and renderer_shot_spec_matches(record, shot)
        and Path(record.get("outputs", {}).get("bundle", "")).resolve()
        == bundle.resolve()
        and record.get("bytes", {}).get("bundle") == bundle.stat().st_size
        and record.get("sha256", {}).get("bundle") == sha256(bundle)
        and settings.get("native_resolution") == [1920, 1080]
        and settings.get("lattice_count") == 0
        and eevee_quality_valid
        and evidence.get("status") == "PASS"
        and evidence.get("operation") == "native_full_resolution_raster"
        and evidence.get("resolution") == [1920, 1080]
        and evidence.get("native_resolution") == [1920, 1080]
        and evidence.get("parts") == expected_parts
        and evidence.get("pixel_content_nondegenerate") is True
        and projection.get("method") == "single native full-resolution raster"
        and projection.get("full_resolution") == [1920, 1080]
        and projection.get("native_resolution") == [1920, 1080]
        and projection.get("camera_shift") == [0.0, 0.0]
        and expansion.get("enabled") is expected_expansion
        and expansion.get("omitted_visible_geometry_count") == 0
        and (
            not expected_expansion
            or (
                expansion.get("expanded_object_count", 0) > 0
                and expansion.get("all_world_matrices_preserved") is True
            )
        )
    )


def renderer_shot_spec_matches(record: dict[str, Any], shot: Any) -> bool:
    """Compare the serialized Shot without invalidating unchanged legacy rows."""

    expected = asdict(shot)
    recorded = {key: record.get(key) for key in expected}
    return json.dumps(
        recorded, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ) == json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def set_output_paths(
    nodes: dict[str, bpy.types.Node],
    output_directory: Path,
    shot_stem: str,
) -> dict[str, Path]:
    temporary: dict[str, Path] = {}
    for name, node in nodes.items():
        node.directory = str(output_directory)
        file_name = f".writing_{shot_stem}_{name}"
        node.file_name = file_name
        temporary[name] = output_directory / f"{file_name}.exr"
    return temporary


def promote_outputs(temporary: dict[str, Path], targets: dict[str, Path]) -> None:
    missing = [name for name, path in temporary.items() if not valid_exr(path)]
    if missing:
        raise RuntimeError(f"Compositor did not write valid EXRs: {missing}")
    for name, target in targets.items():
        os.replace(temporary[name], target)
    for name, path in temporary.items():
        if name not in targets:
            path.unlink(missing_ok=True)


def run_exr_processor(arguments: Sequence[str]) -> dict[str, Any]:
    if not EXR_PROCESSOR_PYTHON.is_file():
        raise RuntimeError(
            f"OpenEXR validation interpreter is missing: {EXR_PROCESSOR_PYTHON}"
        )
    if not EXR_PROCESSOR_PATH.is_file():
        raise RuntimeError(f"OpenEXR processor is missing: {EXR_PROCESSOR_PATH}")
    completed = subprocess.run(
        [
            str(EXR_PROCESSOR_PYTHON),
            str(EXR_PROCESSOR_PATH),
            *arguments,
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "OpenEXR content processing failed: "
            f"exit={completed.returncode} stdout={completed.stdout[-2000:]!r} "
            f"stderr={completed.stderr[-4000:]!r}"
        )
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError, TypeError) as exc:
        raise RuntimeError(
            f"OpenEXR processor returned invalid JSON: {completed.stdout[-4000:]!r}"
        ) from exc
    if result.get("status") != "PASS":
        raise RuntimeError(f"OpenEXR processor did not PASS: {result}")
    return result


def authoritative_bundle_from_render(
    layer_key: str,
    raw_outputs: dict[str, Path],
    resolution: tuple[int, int],
) -> tuple[dict[str, Path], dict[str, Any]]:
    width, height = resolution
    bundle = raw_outputs["bundle"]
    validation = run_exr_processor(
        [
            "validate-bundle",
            "--input",
            str(bundle),
            "--layer",
            layer_key,
            "--width",
            str(width),
            "--height",
            str(height),
        ]
    )
    return {"bundle": bundle}, validation


INTERLACE_LATTICES: tuple[tuple[str, float, float], ...] = (
    ("negative_negative", -1.0, -1.0),
    ("negative_positive", -1.0, 1.0),
    ("positive_negative", 1.0, -1.0),
    ("positive_positive", 1.0, 1.0),
)


def configure_interlace_lattice(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    full_resolution: tuple[int, int],
    x_sign: float,
    y_sign: float,
) -> dict[str, Any]:
    width, height = full_resolution
    if width % 2 or height % 2:
        raise RuntimeError(f"Interlaced resolution must be even: {width}x{height}")
    shift = 1.0 / (2.0 * width)
    scene.render.resolution_x = width // 2
    scene.render.resolution_y = height // 2
    scene.render.resolution_percentage = 100
    camera.data.shift_x = x_sign * shift
    camera.data.shift_y = y_sign * shift
    for view_layer in scene.view_layers:
        view_layer.update()
    return {
        "resolution": [width // 2, height // 2],
        "camera_shift": [camera.data.shift_x, camera.data.shift_y],
        "jitter_in_lattice_pixels": [x_sign * 0.25, y_sign * 0.25],
    }


def reset_interlace_camera(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    full_resolution: tuple[int, int],
) -> None:
    scene.render.resolution_x, scene.render.resolution_y = full_resolution
    scene.render.resolution_percentage = 100
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.0
    for view_layer in scene.view_layers:
        view_layer.update()


def interlace_lattice_bundles(
    layer_key: str,
    lattice_paths: dict[str, Path],
    output: Path,
    full_resolution: tuple[int, int],
) -> dict[str, Any]:
    width, height = full_resolution
    arguments = ["interlace-four"]
    for name, _x_sign, _y_sign in INTERLACE_LATTICES:
        arguments.extend([f"--{name.replace('_', '-')}", str(lattice_paths[name])])
    arguments.extend(
        [
            "--output",
            str(output),
            "--layer",
            layer_key,
            "--width",
            str(width),
            "--height",
            str(height),
        ]
    )
    return run_exr_processor(arguments)


def build_temporary_scene(
    layout: dict[str, Any], layer_key: str, renderer: Any
) -> tuple[bpy.types.Scene, dict[str, Any]]:
    source_scene = bpy.context.scene
    scene = bpy.data.scenes.new(f"{TEMP_PREFIX}:scene:{layer_key}")
    base_collection = bpy.data.collections.new(f"{TEMP_PREFIX}:base")
    asset_collection = bpy.data.collections.new(f"{TEMP_PREFIX}:assets:{layer_key}")
    scene.collection.children.link(base_collection)
    scene.collection.children.link(asset_collection)

    base_records = [
        record for record in layout["placements"] if record_selected(record, "base")
    ]
    asset_records = (
        []
        if layer_key == "base"
        else [
            record
            for record in layout["placements"]
            if record_selected(record, layer_key)
        ]
    )
    base_copies = copy_placement_roots(source_scene, base_collection, base_records)
    asset_copies = copy_placement_roots(source_scene, asset_collection, asset_records)
    view_layers = configure_view_layers(
        scene, layer_key, base_collection, asset_collection
    )

    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    gn_realization = realize_problematic_visible_geometry_nodes(
        scene, asset_collection, asset_copies
    )
    if gn_realization.get("enabled"):
        print(
            "FULL12_EXACT_GN_REALIZATION",
            json.dumps(gn_realization, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
    instance_expansion = expand_exact_visible_asset_instances(
        scene, asset_collection, asset_copies
    )
    if instance_expansion.get("enabled"):
        print(
            "FULL12_EXACT_INSTANCE_EXPANSION",
            json.dumps(instance_expansion, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
    settings, daylight = renderer.configure_daylight(scene)
    settings[
        "workbench_material_sync"
    ] = renderer.synchronize_workbench_material_colors(scene)
    configure_exr(scene, layer_key)
    settings["workbench_persistent_data"] = bool(
        getattr(scene.render, "use_persistent_data", False)
    )
    settings["non_delivery_warmup_content"] = "not_used_single_exact_receiver_view"
    settings["non_delivery_warmup_retained"] = False
    settings["content_aware_exr_validation"] = True
    settings["minimum_nondegenerate_exr_bytes"] = MIN_NONDEGENERATE_EXR_BYTES
    settings["authoritative_exr_pixel_validation"] = True
    settings["authoritative_exr_exact_parts_only"] = True
    settings["combined_part_extraction"] = "not_used_direct_exact_two_part_bundle"
    settings[
        "target_grid_rendering"
    ] = "single native full-resolution target-grid raster"
    settings["native_resolution"] = list(renderer.RESOLUTION)
    settings["lattice_resolution"] = None
    settings["lattice_count"] = 0
    settings["resizing"] = False
    settings["resampling"] = False
    settings["interpolation"] = False
    camera_data = bpy.data.cameras.new(f"{TEMP_PREFIX}:camera_data")
    camera = bpy.data.objects.new(f"{TEMP_PREFIX}:camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    output_nodes = setup_output_compositor(scene, view_layers)
    return scene, {
        "source_scene": source_scene,
        "base_collection": base_collection,
        "asset_collection": asset_collection,
        "base_copies": base_copies,
        "asset_copies": asset_copies,
        "view_layers": view_layers,
        "settings": settings,
        "daylight": daylight,
        "camera": camera,
        "camera_data": camera_data,
        "output_nodes": output_nodes,
        "base_records": base_records,
        "asset_records": asset_records,
        "gn_realization": gn_realization,
        "instance_expansion": instance_expansion,
    }


def destroy_temporary_scene(
    scene: bpy.types.Scene, state: dict[str, Any], renderer: Any
) -> None:
    try:
        renderer.remove_daylight(scene, state["daylight"])
    except (ReferenceError, RuntimeError):
        pass
    source_scene = state["source_scene"]
    if bpy.context.window is not None:
        bpy.context.window.scene = source_scene
    bpy.data.scenes.remove(scene)
    for obj in [*state["base_copies"], *state["asset_copies"]]:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    camera = state["camera"]
    if camera.name in bpy.data.objects:
        bpy.data.objects.remove(camera, do_unlink=True)
    camera_data = state["camera_data"]
    if camera_data.users == 0:
        bpy.data.cameras.remove(camera_data)
    for collection in (state["base_collection"], state["asset_collection"]):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def manifest_path(layer_key: str) -> Path:
    return LAYER_ROOT / f"layer_manifest_{layer_key}.json"


def write_manifest(layer_key: str, payload: dict[str, Any]) -> None:
    path = manifest_path(layer_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def main() -> None:
    tokens = args()
    if not tokens:
        raise RuntimeError(f"Expected layer key followed by views; layers={LAYERS}")
    layer_key = tokens.pop(0).removeprefix("layer:").strip().lower()
    if layer_key not in LAYER_SPECS:
        raise RuntimeError(f"Unknown layer {layer_key!r}; layers={LAYERS}")
    opened_blend = Path(bpy.data.filepath).resolve()
    expected_pack = (CITY / "render_dependency_packs" / f"{layer_key}.blend").resolve()
    if opened_blend not in {BLEND.resolve(), expected_pack}:
        raise RuntimeError(
            "Open either the production Blend or its exact render dependency "
            f"pack for {layer_key}: got {opened_blend}"
        )
    if opened_blend == expected_pack:
        if (
            bpy.context.scene.get("scene_revision") != REVISION
            or bpy.context.scene.get("render_pack_layer_key") != layer_key
            or Path(bpy.context.scene.get("production_blend", "")).resolve()
            != BLEND.resolve()
        ):
            raise RuntimeError(
                f"Invalid or stale render dependency pack: {expected_pack}"
            )

    renderer = load_renderer()
    selected = renderer.select_shots(tokens)
    if not selected:
        return
    layout = json.loads(LAYOUT.read_text(encoding="utf8"))
    if layout.get("scene_revision") != REVISION:
        raise RuntimeError("Layout revision mismatch")
    assignment = validate_partition(layout)
    by_id = {record["placement_id"]: record for record in layout["placements"]}
    blend_stat = BLEND.stat()
    before = {
        "path": str(BLEND.resolve()),
        "bytes": blend_stat.st_size,
        "mtime_ns": blend_stat.st_mtime_ns,
        "sha256": sha256(BLEND),
    }
    output_directory = LAYER_ROOT / layer_key
    output_directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records: dict[str, dict[str, Any]] = {}
    old_manifest = manifest_path(layer_key)
    if old_manifest.is_file():
        try:
            payload = json.loads(old_manifest.read_text(encoding="utf8"))
            records = {
                record["name"]: record
                for record in payload.get("views", [])
                if record.get("name") in renderer.SHOT_BY_NAME
            }
        except (OSError, ValueError, TypeError, KeyError):
            records = {}

    (
        saved_controllers,
        disabled_controllers,
    ) = renderer.disable_hidden_zero_face_geometry_node_controllers()
    scene = None
    state = None
    errors: list[dict[str, str]] = []
    force = os.environ.get("C2W_FULL12_RENDER_FORCE", "0") == "1"
    try:
        scene, state = build_temporary_scene(layout, layer_key, renderer)
        print(
            f"FULL12_ZLAYER_START layer={layer_key} views={len(selected)} "
            f"base_roots={len(state['base_records'])} "
            f"asset_roots={len(state['asset_records'])} "
            f"view_layers={state['view_layers']} resolution={renderer.RESOLUTION}",
            flush=True,
        )
        if os.environ.get("C2W_FULL12_PREFLIGHT_ONLY", "0") == "1":
            preflight_stat = BLEND.stat()
            preflight_after = {
                "path": str(BLEND.resolve()),
                "bytes": preflight_stat.st_size,
                "mtime_ns": preflight_stat.st_mtime_ns,
                "sha256": sha256(BLEND),
            }
            if before != preflight_after:
                raise RuntimeError(
                    "Production Blend changed during exact layer preflight"
                )
            preflight = {
                "schema": "agent.full12.layer_preflight.v1",
                "created_utc": utc_now(),
                "status": "PASS",
                "scene_revision": REVISION,
                "layer_key": layer_key,
                "base_placement_count": len(state["base_records"]),
                "asset_placement_count": len(state["asset_records"]),
                "view_layers": list(state["view_layers"]),
                "render_settings": state["settings"],
                "exact_evaluated_gn_replacement": state["gn_realization"],
                "exact_collection_instance_expansion": state["instance_expansion"],
                "production_blend_before": before,
                "production_blend_after": preflight_after,
                "production_blend_unchanged": True,
                "source_files_saved": False,
            }
            preflight_path = LAYER_ROOT / f"preflight_{layer_key}.json"
            preflight_path.parent.mkdir(parents=True, exist_ok=True)
            preflight_temporary = preflight_path.with_suffix(".writing.json")
            preflight_temporary.write_text(
                json.dumps(preflight, indent=2, ensure_ascii=False),
                encoding="utf8",
            )
            os.replace(preflight_temporary, preflight_path)
            print(
                "FULL12_ZLAYER_PREFLIGHT_PASS",
                json.dumps(
                    {
                        "layer": layer_key,
                        "asset_placement_count": len(state["asset_records"]),
                        "expanded_object_count": state["instance_expansion"].get(
                            "expanded_object_count", 0
                        ),
                        "sheared_object_count": state["instance_expansion"].get(
                            "sheared_object_count", 0
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        for index, shot in enumerate(selected, 1):
            shot_stem = Path(shot.filename).stem
            targets = render_bundle_paths(output_directory, shot_stem, layer_key)
            if not force and reusable_frame_record(
                records.get(shot.name), layer_key, targets, shot
            ):
                print(
                    f"FULL12_ZLAYER_SKIP {index}/{len(selected)} "
                    f"{layer_key}:{shot.name}",
                    flush=True,
                )
                continue
            frame_started = time.monotonic()
            try:
                bounds = renderer.resolve_bounds(shot, layout, by_id)
                camera_record = renderer.configure_camera(
                    state["camera"], shot, bounds, by_id
                )
                # Force both target-Scene dependency graphs to consume the
                # explicit camera matrix before Workbench starts either pass.
                # Without this, background renders of the largest linked
                # packs can retain a previous/identity camera transform.
                for target_view_layer in scene.view_layers:
                    target_view_layer.update()
                camera_record["matrix_validation"] = renderer.validate_camera_pose(
                    state["camera"], camera_record
                )
                renderer.position_interior_fill(
                    state["daylight"]["fill"],
                    state["camera"],
                    camera_record["target"],
                    shot.interior,
                )
                full_resolution = tuple(renderer.RESOLUTION)
                scene.render.resolution_x = full_resolution[0]
                scene.render.resolution_y = full_resolution[1]
                scene.render.resolution_percentage = 100
                state["camera"].data.shift_x = 0.0
                state["camera"].data.shift_y = 0.0
                for target_view_layer in scene.view_layers:
                    target_view_layer.update()
                raw_outputs = set_output_paths(
                    state["output_nodes"], output_directory, shot_stem
                )
                render_attempts = 0
                authoritative_exr_validation: dict[str, Any] = {}
                for render_attempt in range(1, MAX_FRAME_RENDER_ATTEMPTS + 1):
                    for temporary_path in raw_outputs.values():
                        temporary_path.unlink(missing_ok=True)
                    # The renderer-breaking collection indirection has been
                    # removed in memory, so this is one native target-grid
                    # raster with the authoritative camera and no tiling.
                    bpy.ops.render.render(write_still=False, scene=scene.name)
                    try:
                        (
                            authoritative_outputs,
                            validation,
                        ) = authoritative_bundle_from_render(
                            layer_key, raw_outputs, full_resolution
                        )
                    except Exception as exc:
                        print(
                            "FULL12_ZLAYER_NATIVE_CONTENT_RETRY "
                            f"{layer_key}:{shot.name} attempt={render_attempt} "
                            f"error={exc!r}",
                            flush=True,
                        )
                        authoritative_outputs = {}
                        validation = {}
                    if valid_bundle(authoritative_outputs):
                        render_attempts = render_attempt
                        authoritative_exr_validation = {
                            **validation,
                            "operation": "native_full_resolution_raster",
                            "full_resolution": list(full_resolution),
                            "native_resolution": list(full_resolution),
                            "target_pixel_centers_sampled_exactly": True,
                            "resizing": False,
                            "resampling": False,
                            "interpolation": False,
                            "color_conversion": False,
                            "depth_quantization": False,
                        }
                        promote_outputs(authoritative_outputs, targets)
                        authoritative_exr_validation["path"] = str(
                            targets["bundle"].resolve()
                        )
                        authoritative_exr_validation["bytes"] = (
                            targets["bundle"].stat().st_size
                        )
                        break
                    print(
                        "FULL12_ZLAYER_NATIVE_DEGENERATE_RETRY "
                        f"{layer_key}:{shot.name} attempt={render_attempt} "
                        f"bytes={{{', '.join(f'{name}:{path.stat().st_size if path.exists() else 0}' for name, path in raw_outputs.items())}}}",
                        flush=True,
                    )
                    for target_view_layer in scene.view_layers:
                        target_view_layer.update()
                if render_attempts == 0:
                    raise RuntimeError(
                        "Authoritative native EXR remained degenerate after "
                        f"{MAX_FRAME_RENDER_ATTEMPTS} attempts: "
                        f"{layer_key}:{shot.name}"
                    )
                camera_record["target_grid_projection"] = {
                    "method": "single native full-resolution raster",
                    "full_resolution": list(full_resolution),
                    "native_resolution": list(full_resolution),
                    "camera_shift": [0.0, 0.0],
                    "target_pixel_centers_sampled_exactly": True,
                    "resizing": False,
                    "resampling": False,
                    "interpolation": False,
                }
                record = {
                    **asdict(shot),
                    "camera_composition_revision": (
                        renderer.CAMERA_COMPOSITION_REVISION
                    ),
                    "shot_spec_sha256": renderer.shot_spec_sha256(shot),
                    "status": "rendered",
                    "layer_key": layer_key,
                    "render_dependency_hash": frame_dependency_hash(layer_key),
                    "render_engine": state["settings"].get("engine"),
                    "render_engine_role": (
                        "Blender 5.1 deterministic Workbench empty-buffer fallback"
                        if layer_key in {"river5_nature", "artificial_lake"}
                        and state["settings"].get("engine")
                        in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
                        else "primary exact layer rasterizer"
                    ),
                    # Store quality provenance per frame, not only in the
                    # rolling layer manifest. This lets a resumed pass verify
                    # the exact material-fidelity settings per bundle without
                    # trusting timestamps.
                    "render_settings": dict(state["settings"]),
                    "outputs": {
                        name: str(path.resolve()) for name, path in targets.items()
                    },
                    "bytes": {
                        name: path.stat().st_size for name, path in targets.items()
                    },
                    "sha256": {name: sha256(path) for name, path in targets.items()},
                    "camera": camera_record,
                    "render_seconds": round(time.monotonic() - frame_started, 3),
                    "render_attempts": render_attempts,
                    "authoritative_exr_validation": authoritative_exr_validation,
                    "authoritative_exr_processing": (
                        "one pixel-validated native 1920x1080 target-grid "
                        "raster without resize, resampling, or interpolation"
                    ),
                    "view_layers": list(state["view_layers"]),
                    "non_delivery_warmup_content": state["settings"][
                        "non_delivery_warmup_content"
                    ],
                    "exact_evaluated_gn_replacement": {
                        "enabled": state["gn_realization"].get("enabled", False),
                        "controller_count": state["gn_realization"].get(
                            "controller_count", 0
                        ),
                        "replacement_object_count": state["gn_realization"].get(
                            "replacement_object_count", 0
                        ),
                        "omitted_visible_geometry_count": state["gn_realization"].get(
                            "omitted_visible_geometry_count", 0
                        ),
                    },
                    "exact_collection_instance_expansion": {
                        "enabled": state["instance_expansion"].get("enabled", False),
                        "placement_root_count": state["instance_expansion"].get(
                            "placement_root_count", 0
                        ),
                        "expanded_object_count": state["instance_expansion"].get(
                            "expanded_object_count", 0
                        ),
                        "all_world_matrices_preserved": state["instance_expansion"].get(
                            "all_world_matrices_preserved", True
                        ),
                        "omitted_visible_geometry_count": state[
                            "instance_expansion"
                        ].get("omitted_visible_geometry_count", 0),
                    },
                    "depth_channel": (
                        "BaseDepth.V" if layer_key == "base" else "CombinedDepth.V"
                    ),
                    "cross_layer_lighting_pass": (
                        None
                        if layer_key == "base"
                        else (
                            "CombinedColor/CombinedDepth with shared exact road/ground "
                            "receivers; visible assets isolated by exact BaseDepth delta"
                        )
                    ),
                }
                records[shot.name] = record
                print(
                    f"FULL12_ZLAYER_DONE {index}/{len(selected)} "
                    f"{layer_key}:{shot.name} bytes={sum(record['bytes'].values())} "
                    f"seconds={record['render_seconds']}",
                    flush=True,
                )
                write_manifest(
                    layer_key,
                    {
                        "schema": "agent.full12.zdepth_layer.v1",
                        "status": "IN_PROGRESS",
                        "scene_revision": REVISION,
                        "layer_key": layer_key,
                        "views": [
                            records[name]
                            for name in renderer.SHOT_BY_NAME
                            if name in records
                        ],
                    },
                )
            except Exception as exc:
                errors.append({"view": shot.name, "error": repr(exc)})
                print(
                    f"FULL12_ZLAYER_ERROR {layer_key}:{shot.name} {exc!r}",
                    flush=True,
                )
                raise
    finally:
        # Deliberately do not remove the temporary scene/datablocks here.  On
        # these very large linked libraries Blender 5.1 can spend tens of GB
        # while destructing IDs and be killed after otherwise successful work.
        # The process exits via os._exit below; the OS reclaims all memory and
        # the production Blend remains unopened for writing.

        final_stat = BLEND.stat()
        after = {
            "path": str(BLEND.resolve()),
            "bytes": final_stat.st_size,
            "mtime_ns": final_stat.st_mtime_ns,
            "sha256": sha256(BLEND),
        }
        complete_names = [
            shot.name
            for shot in renderer.SHOTS
            if shot.name in records
            and valid_bundle(
                render_bundle_paths(
                    output_directory,
                    Path(shot.filename).stem,
                    layer_key,
                )
            )
        ]
        frame_engine_counts: dict[str, int] = {}
        for frame_record in records.values():
            frame_engine = str(
                frame_record.get("render_settings", {}).get("engine", "UNKNOWN")
            )
            frame_engine_counts[frame_engine] = (
                frame_engine_counts.get(frame_engine, 0) + 1
            )
        manifest_render_settings = dict(state["settings"]) if state is not None else {}
        manifest_render_settings["per_frame_engine_counts"] = dict(
            sorted(frame_engine_counts.items())
        )
        manifest_render_settings["mixed_frame_render_engines"] = (
            len(frame_engine_counts) > 1
        )
        manifest = {
            "schema": "agent.full12.zdepth_layer.v1",
            "created_utc": utc_now(),
            "status": "FAIL" if errors else "IN_PROGRESS",
            "scene_revision": REVISION,
            "layer_key": layer_key,
            "layer_spec": {
                key: sorted(value) for key, value in LAYER_SPECS[layer_key].items()
            },
            "assigned_placement_ids": sorted(
                placement_id
                for placement_id, assigned in assignment.items()
                if assigned == layer_key
            ),
            "assigned_placement_count": sum(
                assigned == layer_key for assigned in assignment.values()
            ),
            "partition_placement_count": len(assignment),
            "partition_exactly_once": len(assignment) == len(layout["placements"]),
            "production_blend": str(BLEND.resolve()),
            "opened_scene_file": str(opened_blend),
            "used_exact_render_dependency_pack": opened_blend == expected_pack,
            "production_blend_before": before,
            "production_blend_after": after,
            "production_blend_unchanged": before == after,
            "output_directory": str(output_directory.resolve()),
            "requested_view_names": [shot.name for shot in selected],
            "completed_view_names": complete_names,
            "completed_count": len(complete_names),
            "expected_count": len(renderer.SHOTS),
            "complete": len(complete_names) == len(renderer.SHOTS) and not errors,
            "render_method": (
                "exact production placement data; transient exact object-shell "
                "expansion of asset collection instances; one native 1920x1080 "
                "Combined asset+receiver raster per partition; camera-space 32-bit "
                "Z and exact BaseDepth delta isolate asset surfaces and shared-"
                "receiver lighting"
            ),
            "workbench_linked_instance_empty_pass_workaround": (
                "process-local exact object shells share authored data, materials, "
                "modifiers, and dependency-graph world matrices, removing only the "
                "linked Empty-instance indirection that caused Blender 5.1's dense "
                "1920x1080 empty buffer; no visible geometry omitted or simplified"
            ),
            "geometry_simplification": False,
            "source_scale_changed": False,
            "production_scene_saved": False,
            "temporary_instance_root_copies_only": not bool(
                state
                and (
                    state["gn_realization"].get("replacement_object_count", 0)
                    or state["instance_expansion"].get("expanded_object_count", 0)
                )
            ),
            "temporary_geometry_policy": (
                "exact collection-instance roots; exact shared-data object shells "
                "at dependency-graph matrices for asset partitions; exact evaluated "
                "GN result copies only for two renderer-breaking live controllers"
            ),
            "temporary_exact_evaluated_gn_replacements": (
                state["gn_realization"] if state is not None else {}
            ),
            "temporary_exact_collection_instance_expansion": (
                state["instance_expansion"] if state is not None else {}
            ),
            "temporary_disabled_hidden_zero_face_gn_controllers": (
                disabled_controllers
            ),
            "disabled_visible_geometry_count": 0,
            "render_settings": manifest_render_settings,
            "per_frame_render_engine_counts": dict(sorted(frame_engine_counts.items())),
            "mixed_frame_render_engines": len(frame_engine_counts) > 1,
            "eevee_workbench_degenerate_buffer_fallback_count": (
                frame_engine_counts.get("BLENDER_EEVEE", 0)
                + frame_engine_counts.get("BLENDER_EEVEE_NEXT", 0)
                if layer_key == "river5_nature"
                else 0
            ),
            "view_layers": state["view_layers"] if state is not None else [],
            "non_delivery_warmup_content": (
                state["settings"].get("non_delivery_warmup_content")
                if state is not None
                else None
            ),
            "non_delivery_warmup_retained": False,
            "content_aware_exr_validation": True,
            "minimum_nondegenerate_exr_bytes": MIN_NONDEGENERATE_EXR_BYTES,
            "authoritative_exr_pixel_validation": True,
            "authoritative_exr_exact_parts_only": True,
            "combined_part_extraction": "not_used_direct_exact_two_part_bundle",
            "warmup_parts_retained_in_committed_bundle": False,
            "target_grid_rendering": (
                "single native full-resolution target-grid raster"
            ),
            "native_resolution": list(renderer.RESOLUTION),
            "lattice_resolution": None,
            "lattice_count": 0,
            "target_pixel_centers_sampled_exactly": True,
            "resizing": False,
            "resampling": False,
            "interpolation": False,
            "views": [
                records[name] for name in renderer.SHOT_BY_NAME if name in records
            ],
            "errors": errors,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        if manifest["complete"]:
            manifest["status"] = "PASS"
        write_manifest(layer_key, manifest)
        print(
            f"FULL12_ZLAYER_FINISH layer={layer_key} "
            f"status={manifest['status']} "
            f"completed={manifest['completed_count']}/{manifest['expected_count']}",
            flush=True,
        )

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if errors else 0)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        # Blender's --python command may otherwise print a traceback yet exit
        # zero, causing a shell batch to treat a failed authoritative frame as
        # complete.  Preserve the traceback and make failure unambiguous.
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
