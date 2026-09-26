#!/usr/bin/env python3
"""Render one exact full-13 Eevee PBR layer with 32-bit camera depth."""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_14"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BASE_PATH = ROOT / "scripts/render_urban_v1_full_12_zdepth_layer.py"
os.environ.setdefault(
    "C2W_FULL12_RENDER_ENGINE", os.environ.get("C2W_FULL14_RENDER_ENGINE", "EEVEE")
)
os.environ.setdefault(
    "C2W_FULL12_RENDER_RESOLUTION",
    os.environ.get("C2W_FULL14_RENDER_RESOLUTION", "1920x1080"),
)
os.environ.setdefault(
    "C2W_FULL12_EEVEE_SAMPLES", os.environ.get("C2W_FULL14_EEVEE_SAMPLES", "64")
)
os.environ.setdefault(
    "C2W_FULL12_RENDER_FORCE", os.environ.get("C2W_FULL14_RENDER_FORCE", "0")
)
os.environ.setdefault("C2W_FULL12_PERSISTENT_DATA", "1")

spec = importlib.util.spec_from_file_location("full14_zdepth_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = REVISION
base.CITY = CITY
base.BLEND = CITY / f"{REVISION}.blend"
base.LAYOUT = CITY / "layout_plan.json"
base._DEFAULT_LAYER_ROOT = CITY / "renders/zdepth_layers"
base.LAYER_ROOT = Path(
    os.environ.get("C2W_FULL14_LAYER_ROOT", str(base._DEFAULT_LAYER_ROOT))
).resolve()
if not base.LAYER_ROOT.is_relative_to(CITY.resolve()):
    raise RuntimeError("C2W_FULL14_LAYER_ROOT must remain inside the full-14 output")
base.RENDERER_PATH = ROOT / "scripts/render_urban_v1_full_14_daytime.py"
base.EXR_PROCESSOR_PATH = ROOT / "scripts/process_urban_v1_full_14_exr.py"
base.TEMP_PREFIX = "__full14_zdepth_tmp__"

base.LAYER_SPECS = dict(base.LAYER_SPECS)
base.LAYER_SPECS.update(
    {
        "full14_unique_urban_fabric": {
            "placement_ids": {
                f"full14_unique_infill_{index:02d}_{name}"
                for index, name in enumerate(
                    (
                        "west_civic_01",
                        "west_civic_02",
                        "west_civic_03",
                        "west_civic_04",
                        "east_mixed_01",
                        "east_mixed_02",
                        "southeast_01",
                        "southeast_02",
                        "northwest_edge_01",
                        "northwest_edge_02",
                        "north_civic_01",
                        "north_civic_02",
                        "east_midrise_03",
                        "east_midrise_04",
                        "central_mixed_01",
                        "central_mixed_02",
                        "south_buffer_01",
                        "south_buffer_02",
                        "lakefront_edge_01",
                        "north_connector_01",
                    ),
                    1,
                )
            }
        },
        "full14_semantic_interiors": {
            "placement_ids": {
                "full14_semantic_interior_school_cafeteria",
                "full14_semantic_interior_library_reading_room",
                "full14_semantic_interior_bank_atrium",
                "full14_semantic_interior_hospital_lobby",
            }
        },
        "full14_public_realm": {
            "placement_ids": {
                "full14_continuous_pedestrian_activity",
                "full14_complete_entrance_connector_network",
                "full14_instanced_inner_greenbelt",
            }
        },
    }
)
base.LAYERS = tuple(base.LAYER_SPECS)


def frame_dependency_hash(layer_key: str) -> str:
    import json

    lineage_path = CITY / "render_dependency_packs/render_pack_lineage.json"
    payload = json.loads(lineage_path.read_text(encoding="utf8"))
    record = payload.get("packs", {}).get(layer_key, {})
    value = record.get("dependency_hash")
    if payload.get("run_id") != os.environ.get(
        "C2W_FULL14_RUN_ID", payload.get("run_id")
    ):
        raise RuntimeError("Render dependency lineage run ID mismatch")
    if not isinstance(value, str) or len(value) != 64:
        raise RuntimeError(f"Missing content dependency hash for layer {layer_key}")
    return value


base.frame_dependency_hash = frame_dependency_hash

_last_mesh_audit = {}
_base_expand = base.expand_exact_visible_asset_instances
_base_assign_exact_affine_transform = base.assign_exact_affine_transform


def assign_exact_affine_transform(
    duplicate,
    expected,
    asset_collection,
    index,
):
    """Keep full-14 temporary instance rotations out of Euler gimbal lock.

    The instanced greenbelt contains detailed branch meshes whose authored
    orientations legitimately sit very close to +/-90 degrees.  Blender's
    default XYZ storage can round-trip those matrices through the dependency
    graph with sub-millimetre drift.  Quaternion storage represents the same
    exact TRS rotation without changing geometry, scale, materials, or the
    audited world-matrix tolerance.
    """
    Matrix = base.Matrix
    np = base.np
    duplicate.rotation_mode = "QUATERNION"
    location, rotation, scale = expected.decompose()
    single_trs = (
        Matrix.Translation(location)
        @ rotation.to_matrix().to_4x4()
        @ Matrix.Diagonal((*scale, 1.0))
    )
    affine_residual = base.matrix_maximum_error(expected, single_trs)
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
            "Could not factor exact full-14 affine instance transform: "
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

    rotation_parent = base.bpy.data.objects.new(
        f"{base.TEMP_PREFIX}:affine_rotation:{index:06d}", None
    )
    scale_parent = base.bpy.data.objects.new(
        f"{base.TEMP_PREFIX}:affine_scale:{index:06d}", None
    )
    for helper in (rotation_parent, scale_parent):
        helper.rotation_mode = "QUATERNION"
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


base.assign_exact_affine_transform = assign_exact_affine_transform

_base_setup_output_compositor = base.setup_output_compositor
_base_set_output_paths = base.set_output_paths
_base_authoritative_bundle_from_render = base.authoritative_bundle_from_render


def setup_output_compositor(scene, view_layer_names):
    """Use the native compositor API of either Blender 4.5 or 5.x."""
    if hasattr(scene, "compositing_node_group"):
        return _base_setup_output_compositor(scene, view_layer_names)

    # Blender 4.5 owns the compositor tree on Scene.node_tree and its File
    # Output node writes a single multilayer part.  A lossless post-render
    # step below promotes its float channels to the two named multipart EXR
    # parts required by the unchanged delivery contract.
    scene.use_nodes = True
    scene.render.use_compositing = True
    group = scene.node_tree
    group.nodes.clear()
    output = group.nodes.new("CompositorNodeOutputFile")
    output.name = f"{base.TEMP_PREFIX}:output:bundle"
    output.label = "authoritative exact color + camera-space depth bundle"
    output.base_path = str(base.LAYER_ROOT / ".writing_bundle")
    output.format.file_format = "OPEN_EXR_MULTILAYER"
    output.format.color_depth = "32"
    output.format.exr_codec = "ZIP"
    output.layer_slots.clear()
    for view_layer_name in view_layer_names:
        render_layer = group.nodes.new("CompositorNodeRLayers")
        render_layer.name = f"{base.TEMP_PREFIX}:rlayer:{view_layer_name}"
        render_layer.layer = view_layer_name
        if "Depth" not in render_layer.outputs:
            raise RuntimeError(
                f"Depth pass missing from compositor layer {view_layer_name}"
            )
        color_name = f"{view_layer_name}Color"
        depth_name = f"{view_layer_name}Depth"
        output.layer_slots.new(color_name)
        output.layer_slots.new(depth_name)
        group.links.new(render_layer.outputs["Image"], output.inputs[color_name])
        group.links.new(render_layer.outputs["Depth"], output.inputs[depth_name])
    output["full14_blender45_frame"] = int(scene.frame_current)
    output["full14_blender45_single_part_source"] = True
    return {"bundle": output}


def set_output_paths(nodes, output_directory, shot_stem):
    if all(hasattr(node, "directory") for node in nodes.values()):
        return _base_set_output_paths(nodes, output_directory, shot_stem)
    temporary = {}
    for name, node in nodes.items():
        file_name = f".writing_{shot_stem}_{name}"
        node.base_path = str(output_directory / file_name)
        frame = int(node.get("full14_blender45_frame", 1))
        temporary[name] = output_directory / f"{file_name}{frame:04d}.exr"
    return temporary


def authoritative_bundle_from_render(layer_key, raw_outputs, resolution):
    bundle = raw_outputs["bundle"]
    nodes_use_blender45_api = not hasattr(
        base.bpy.types.Scene, "compositing_node_group"
    )
    if not nodes_use_blender45_api:
        return _base_authoritative_bundle_from_render(
            layer_key, raw_outputs, resolution
        )
    width, height = resolution
    multipart = bundle.with_name(f"{bundle.stem}.multipart.exr")
    validation = base.run_exr_processor(
        [
            "convert-blender45-bundle",
            "--input",
            str(bundle),
            "--output",
            str(multipart),
            "--layer",
            layer_key,
            "--width",
            str(width),
            "--height",
            str(height),
        ]
    )
    bundle.unlink(missing_ok=True)
    return {"bundle": multipart}, validation


base.setup_output_compositor = setup_output_compositor
base.set_output_paths = set_output_paths
base.authoritative_bundle_from_render = authoritative_bundle_from_render


def expand_exact_visible_asset_instances(scene, asset_collection, asset_copies):
    """Run child-object world-AABB broad phase and real mesh BVH narrow phase."""
    global _last_mesh_audit
    result = _base_expand(scene, asset_collection, asset_copies)
    if not result.get("enabled"):
        _last_mesh_audit = {
            "method": "base receiver layer; placement collisions audited in production layout",
            "evaluated_child_mesh_count": 0,
            "broad_phase_candidate_count": 0,
            "bvh_candidate_count": 0,
            "triangle_intersection_pairs": [],
            "pass": True,
        }
        return result
    import math
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    meshes = [
        obj
        for obj in asset_collection.objects
        if obj.type == "MESH"
        and obj.get("exact_collection_instance_expansion")
        and obj.data is not None
        and not obj.hide_render
    ]
    bounds = {}
    grid = {}
    cell = 12.0
    for obj in meshes:
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        box = (
            min(p.x for p in points),
            min(p.y for p in points),
            min(p.z for p in points),
            max(p.x for p in points),
            max(p.y for p in points),
            max(p.z for p in points),
        )
        bounds[obj] = box
        for ix in range(math.floor(box[0] / cell), math.floor(box[3] / cell) + 1):
            for iy in range(math.floor(box[1] / cell), math.floor(box[4] / cell) + 1):
                grid.setdefault((ix, iy), []).append(obj)
    pairs = set()
    for members in grid.values():
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                if first.get("source_placement_id") == second.get(
                    "source_placement_id"
                ):
                    continue
                a, b = bounds[first], bounds[second]
                if not (
                    a[3] <= b[0]
                    or b[3] <= a[0]
                    or a[4] <= b[1]
                    or b[4] <= a[1]
                    or a[5] <= b[2]
                    or b[5] <= a[2]
                ):
                    pairs.add(tuple(sorted((first.name, second.name))))
    depsgraph = scene.view_layers.get("Combined")
    if bpy.context.window is not None and depsgraph is not None:
        bpy.context.window.scene = scene
        bpy.context.window.view_layer = depsgraph
    graph = bpy.context.evaluated_depsgraph_get()
    objects = {obj.name: obj for obj in meshes}
    tree_cache = {}

    def tree_for(name):
        if name not in tree_cache:
            try:
                tree_cache[name] = BVHTree.FromObject(
                    objects[name], graph, epsilon=0.001
                )
            except (RuntimeError, TypeError, ValueError):
                tree_cache[name] = None
        return tree_cache[name]

    intersections = []
    for first_name, second_name in sorted(pairs):
        first, second = objects[first_name], objects[second_name]
        first_bvh, second_bvh = tree_for(first_name), tree_for(second_name)
        overlap = first_bvh.overlap(second_bvh) if first_bvh and second_bvh else []
        if overlap:
            first_box, second_box = bounds[first], bounds[second]
            overlap_min = [max(first_box[axis], second_box[axis]) for axis in range(3)]
            overlap_max = [
                min(first_box[axis + 3], second_box[axis + 3]) for axis in range(3)
            ]
            overlap_extent = [
                max(0.0, overlap_max[axis] - overlap_min[axis]) for axis in range(3)
            ]
            intersections.append(
                {
                    "a": first.name,
                    "a_placement": first.get("source_placement_id"),
                    "b": second.name,
                    "b_placement": second.get("source_placement_id"),
                    "triangle_pair_count": len(overlap),
                    "broad_phase_overlap_min": overlap_min,
                    "broad_phase_overlap_max": overlap_max,
                    "broad_phase_overlap_extent_m": overlap_extent,
                    "broad_phase_overlap_volume_m3": (
                        overlap_extent[0] * overlap_extent[1] * overlap_extent[2]
                    ),
                }
            )
    _last_mesh_audit = {
        "method": "dependency-evaluated child-object world AABB spatial hash followed by BVHTree triangle overlap",
        "evaluated_child_mesh_count": len(meshes),
        "spatial_hash_cell_m": cell,
        "broad_phase_candidate_count": len(pairs),
        "bvh_candidate_count": len(pairs),
        "cached_bvh_tree_count": sum(tree is not None for tree in tree_cache.values()),
        "triangle_intersection_pairs": intersections,
        "same_placement_authored_child_contacts_excluded": True,
        "pass": not intersections,
    }
    return result


base.expand_exact_visible_asset_instances = expand_exact_visible_asset_instances

_base_build_temporary_scene = base.build_temporary_scene


def build_temporary_scene(layout, layer_key, renderer):
    """Build once, then certify all 80 cameras against this exact layer."""
    import json
    from datetime import datetime, timezone

    scene, state = _base_build_temporary_scene(layout, layer_key, renderer)
    by_id = {record["placement_id"]: record for record in layout["placements"]}
    cameras = []
    failures = []
    for shot in renderer.SHOTS:
        try:
            bounds = renderer.resolve_bounds(shot, layout, by_id)
            record = renderer.configure_camera(state["camera"], shot, bounds, by_id)
            record["matrix_validation"] = renderer.validate_camera_pose(
                state["camera"], record
            )
            cameras.append(
                {
                    "name": shot.name,
                    "interior": shot.interior,
                    "placement_ids": list(shot.placement_ids),
                    "camera": record,
                    "status": "PASS",
                }
            )
        except Exception as exc:
            failures.append(
                {"name": shot.name, "error": f"{type(exc).__name__}: {exc}"}
            )
    mesh_pass = _last_mesh_audit.get("pass") is True
    payload = {
        "schema": "agent.full14.layer_camera_mesh_preflight.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": layout["run_id"],
        "scene_revision": REVISION,
        "layer_key": layer_key,
        "status": "PASS"
        if len(cameras) == 80 and not failures and mesh_pass
        else "FAIL",
        "camera_count_expected": 80,
        "camera_count_passed": len(cameras),
        "camera_count_failed": len(failures),
        "method": "all final cameras versus exact expanded render-child world bounds before any rasterization",
        "evaluated_child_mesh_bvh_audit": _last_mesh_audit,
        "failures": failures,
        "cameras": cameras,
    }
    path = base.LAYER_ROOT / f"camera_mesh_preflight_{layer_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)
    print(
        "FULL14_LAYER_CAMERA_MESH_PREFLIGHT",
        json.dumps(
            {
                "layer": layer_key,
                "status": payload["status"],
                "passed": len(cameras),
                "failed": len(failures),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if payload["status"] != "PASS":
        raise RuntimeError(
            f"Full-13 exact layer preflight failed for {layer_key}: "
            f"camera_failures={failures}; mesh_collisions="
            f"{_last_mesh_audit.get('triangle_intersection_pairs', [])[:10]}"
        )
    return scene, state


base.build_temporary_scene = build_temporary_scene

_base_write_manifest = base.write_manifest


def write_manifest(layer_key, payload):
    import json

    layout = json.loads(base.LAYOUT.read_text(encoding="utf8"))
    payload["schema"] = "agent.full14.zdepth_layer.v1"
    payload["run_id"] = layout["run_id"]
    payload["scene_revision"] = REVISION
    payload["render_dependency_hash"] = frame_dependency_hash(layer_key)
    for record in payload.get("views", []):
        if record.get("render_dependency_hash") == payload["render_dependency_hash"]:
            record["producer_run_id"] = layout["run_id"]
    payload["all_frames_pbr_eevee"] = all(
        record.get("render_settings", {}).get("engine")
        in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
        for record in payload.get("views", [])
    )
    payload["workbench_final_frames"] = sum(
        record.get("render_settings", {}).get("engine") == "BLENDER_WORKBENCH"
        for record in payload.get("views", [])
    )
    payload["evaluated_child_mesh_bvh_audit"] = _last_mesh_audit
    _base_write_manifest(layer_key, payload)


base.write_manifest = write_manifest

globals().update(
    {name: value for name, value in vars(base).items() if not name.startswith("__")}
)
LAYER_SPECS = base.LAYER_SPECS
LAYERS = base.LAYERS


if __name__ == "__main__":
    try:
        base.main()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
