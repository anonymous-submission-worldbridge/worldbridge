#!/usr/bin/env python3
"""Export one retained GPT-6 Astra Blender scene for Table-3 navigation.

This script is executed by Blender after opening the frozen Table-2 ``.blend``.
It never saves the source scene and deliberately does not infer object instances.
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


import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import aabb_intersects_roi
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import (
    exclude_from_nav_obstacles,
)
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import is_crosswalk
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import is_walkable_surface
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import load_rules
from baselines.methods.gpt.tools.gpt_geometry_surface_rules import roi_for_spec


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def world_geometry(obj: bpy.types.Object) -> dict | None:
    if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"} or obj.hide_render:
        return None
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    try:
        mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    except RuntimeError:
        return None
    try:
        mesh.calc_loop_triangles()
        matrix = evaluated.matrix_world
        vertices = [
            tuple(float(value) for value in (matrix @ vertex.co))
            for vertex in mesh.vertices
        ]
        faces = [
            tuple(int(value) for value in triangle.vertices)
            for triangle in mesh.loop_triangles
        ]
    finally:
        evaluated.to_mesh_clear()
    if not vertices or not faces:
        return None
    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    return {
        "name": obj.name,
        "vertices": vertices,
        "faces": faces,
        "minimum": minimum,
        "maximum": maximum,
    }


def triangle_area(a, b, c) -> float:
    return 0.5 * Vector(b - a).cross(Vector(c - a)).length


def clip_axis(polygon, axis: int, bound: float, keep_greater: bool):
    if not polygon:
        return []

    def inside(point):
        return point[axis] >= bound if keep_greater else point[axis] <= bound

    output = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside != previous_inside:
            denominator = current[axis] - previous[axis]
            fraction = (
                0.0
                if abs(denominator) < 1e-12
                else (bound - previous[axis]) / denominator
            )
            output.append(
                tuple(
                    previous[index] + fraction * (current[index] - previous[index])
                    for index in range(3)
                )
            )
        if current_inside:
            output.append(tuple(current))
        previous = current
        previous_inside = current_inside
    return output


def clip_triangle(triangle, roi):
    xmin, xmax, ymin, ymax = roi
    polygon = [tuple(point) for point in triangle]
    for axis, bound, greater in (
        (0, xmin, True),
        (0, xmax, False),
        (1, ymin, True),
        (1, ymax, False),
    ):
        polygon = clip_axis(polygon, axis, bound, greater)
    return polygon


def clipped_part(record: dict, roi, upward_only: bool, rules: dict):
    vertices = []
    faces = []
    normal_limit = float(rules["upward_normal_min_z"])
    minimum_area = float(rules["minimum_triangle_area_m2"])
    source_vertices = record["vertices"]
    for face in record["faces"]:
        triangle = [Vector(source_vertices[index]) for index in face]
        cross = (triangle[1] - triangle[0]).cross(triangle[2] - triangle[0])
        if cross.length <= 2.0 * minimum_area:
            continue
        if upward_only and cross.normalized().z < normal_limit:
            continue
        polygon = clip_triangle(triangle, roi)
        if len(polygon) < 3:
            continue
        offset = len(vertices)
        vertices.extend(tuple(float(value) for value in point) for point in polygon)
        for index in range(1, len(polygon) - 1):
            candidate = (offset, offset + index, offset + index + 1)
            if (
                triangle_area(*(Vector(vertices[value]) for value in candidate))
                >= minimum_area
            ):
                faces.append(candidate)
    return vertices, faces


def rectangle_part(minimum, maximum, z: float, roi):
    xmin = max(float(minimum[0]), roi[0])
    xmax = min(float(maximum[0]), roi[1])
    ymin = max(float(minimum[1]), roi[2])
    ymax = min(float(maximum[1]), roi[3])
    if xmax - xmin <= 1e-5 or ymax - ymin <= 1e-5:
        return [], []
    return (
        [(xmin, ymin, z), (xmax, ymin, z), (xmax, ymax, z), (xmin, ymax, z)],
        [(0, 1, 2), (0, 2, 3)],
    )


def crosswalk_envelopes(records: list[dict], roi, rules: dict):
    if not records:
        return [], []
    threshold = float(rules["crosswalk_cluster_center_distance_m"])
    parents = list(range(len(records)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    centers = [
        (
            0.5 * (record["minimum"][0] + record["maximum"][0]),
            0.5 * (record["minimum"][1] + record["maximum"][1]),
        )
        for record in records
    ]
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if math.dist(centers[left], centers[right]) <= threshold:
                union(left, right)
    groups = {}
    for index, record in enumerate(records):
        groups.setdefault(find(index), []).append(record)
    parts = []
    metadata = []
    for members in groups.values():
        minimum = [
            min(record["minimum"][axis] for record in members) for axis in range(3)
        ]
        maximum = [
            max(record["maximum"][axis] for record in members) for axis in range(3)
        ]
        z = max(record["maximum"][2] for record in members)
        part = rectangle_part(minimum, maximum, z, roi)
        if part[1]:
            parts.append(part)
            metadata.append(
                {
                    "source_nodes": sorted(record["name"] for record in members),
                    "envelope_min": minimum,
                    "envelope_max": maximum,
                    "top_z_m": z,
                }
            )
    return parts, metadata


def merge_parts(parts):
    vertices = []
    faces = []
    for part_vertices, part_faces in parts:
        offset = len(vertices)
        vertices.extend(part_vertices)
        faces.extend(tuple(offset + index for index in face) for face in part_faces)
    return vertices, faces


def write_ply(path: Path, parts) -> dict:
    vertices, faces = merge_parts(parts)
    if not vertices or not faces:
        raise RuntimeError(f"Refusing to write empty canonical mesh: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        header = (
            "ply\nformat binary_little_endian 1.0\n"
            f"element vertex {len(vertices)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            f"element face {len(faces)}\n"
            "property list uchar int vertex_indices\nend_header\n"
        )
        handle.write(header.encode("ascii"))
        for vertex in vertices:
            handle.write(struct.pack("<fff", *vertex))
        for face in faces:
            handle.write(struct.pack("<Biii", 3, *face))
    return {"vertices": len(vertices), "faces": len(faces), "sha256": sha256(path)}


def write_glb(path: Path, parts) -> dict:
    vertices, faces = merge_parts(parts)
    mesh = bpy.data.meshes.new("GPT6AstraTable3Canonical")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("GPT6AstraTable3Canonical", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_materials="NONE",
        export_cameras=False,
        export_lights=False,
    )
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    return {"vertices": len(vertices), "faces": len(faces), "sha256": sha256(path)}


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    source_run = args.source_run.resolve()
    if not run_dir.is_relative_to(BASELINES) or not source_run.is_relative_to(
        BASELINES
    ):
        raise ValueError("All Table-3 paths must remain under baselines")
    spec = json.loads((run_dir / "input/spec.json").read_text(encoding="utf-8"))
    rules = load_rules()
    domain = spec["domain"]
    roi = roi_for_spec(spec, rules)

    records = []
    for obj in bpy.context.scene.objects:
        record = world_geometry(obj)
        if record is not None and aabb_intersects_roi(
            record["minimum"], record["maximum"], roi
        ):
            records.append(record)
    if not records:
        raise RuntimeError(
            "Final Blender scene has no mesh-like geometry in the frozen ROI"
        )

    walkable = [
        record
        for record in records
        if is_walkable_surface(record["name"], rules, domain)
    ]
    if domain == "indoor":
        if not walkable:
            raise RuntimeError(
                "No indoor floor node matched the frozen walkable-surface rule"
            )
        selected = max(
            walkable,
            key=lambda record: (record["maximum"][0] - record["minimum"][0])
            * (record["maximum"][1] - record["minimum"][1]),
        )
        reference_parts = [clipped_part(selected, roi, True, rules)]
        reference_nodes = [selected["name"]]
        crosswalk_metadata = []
    else:
        ordinary = [record for record in walkable if not is_crosswalk(record["name"])]
        crossings = [record for record in walkable if is_crosswalk(record["name"])]
        reference_parts = [
            clipped_part(record, roi, True, rules) for record in ordinary
        ]
        crossing_parts, crosswalk_metadata = crosswalk_envelopes(crossings, roi, rules)
        reference_parts.extend(crossing_parts)
        reference_nodes = sorted(record["name"] for record in walkable)
    reference_parts = [part for part in reference_parts if part[1]]
    if not reference_parts:
        raise RuntimeError(
            "Frozen semantic walkable selection produced no upward triangles"
        )

    obstacle_parts = []
    obstacle_nodes = []
    for record in records:
        if exclude_from_nav_obstacles(record["name"], rules):
            continue
        part = clipped_part(record, roi, False, rules)
        if part[1]:
            obstacle_parts.append(part)
            obstacle_nodes.append(record["name"])
    collision_parts = reference_parts + obstacle_parts
    reference_vertices, _ = merge_parts(reference_parts)
    floor_z = min(vertex[2] for vertex in reference_vertices)
    canonical = run_dir / "scene/canonical"
    reference_ply = write_ply(canonical / "empty_reference.ply", reference_parts)
    collision_ply = write_ply(canonical / "collision.ply", collision_parts)
    reference_glb = write_glb(canonical / "empty_reference.glb", reference_parts)
    collision_glb = write_glb(canonical / "collision.glb", collision_parts)

    atomic_json(
        canonical / "instances.json",
        {
            "method": "gpt6_astra",
            "domain": domain,
            "instance_capability": False,
            "instance_metric_status": "N/A-I",
            "reason": "Frozen final output has no stable independent-instance graph or native support edges",
            "instances": [],
            "floor_z_m": floor_z,
            "evaluation_polygon_xy_m": [
                [roi[0], roi[2]],
                [roi[1], roi[2]],
                [roi[1], roi[3]],
                [roi[0], roi[3]],
            ],
        },
    )
    structural_na = {
        "method": "gpt6_astra",
        "domain": domain,
        "spec_id": spec["spec_id"],
        "logical_seed": int(run_dir.name.split("_")[-1]),
        "status": "not_applicable",
        "reason_code": "N/A-I",
        "reason": "No verifiable independent object instances or native support graph",
        "collision_rate": None,
        "floating_rate": None,
        "oob_rate": None,
        "support_validity": None,
        "valid_scene_rate": None,
    }
    atomic_json(run_dir / "metrics/structural.json", structural_na)
    atomic_json(
        run_dir / "input/boundaries.json",
        {
            "type": "fixed_rectangle",
            "xy_m": [
                [roi[0], roi[2]],
                [roi[1], roi[2]],
                [roi[1], roi[3]],
                [roi[0], roi[3]],
            ],
            "floor_z_m": floor_z,
            "walkable_selection": "native final floor"
            if domain == "indoor"
            else "frozen native pedestrian-surface name rules",
            "spawn_policy": "reference-navmesh point nearest ROI center; largest reference component only",
        },
    )
    atomic_json(
        canonical / "transform.json",
        {
            "source_coordinate_system": "Blender meters, Z up",
            "canonical_coordinate_system": "meters, Z up",
            "source_to_canonical_matrix_row_major": [
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
            ],
            "scale_m_per_source_unit": 1.0,
        },
    )
    manifest = {
        "method": "gpt6_astra",
        "domain": domain,
        "spec_id": spec["spec_id"],
        "source_blend": str(source_run / "scene/scene.blend"),
        "source_blend_sha256": sha256(source_run / "scene/scene.blend"),
        "exporter_sha256": sha256(Path(__file__)),
        "rules_sha256": sha256(
            (
                BASELINES
                / "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json"
            )
        ),
        "roi_xy_m": list(roi),
        "floor_z_m": floor_z,
        "source_mesh_nodes_in_roi": len(records),
        "walkable_source_nodes": reference_nodes,
        "walkable_source_node_count": len(reference_nodes),
        "crosswalk_envelopes": crosswalk_metadata,
        "obstacle_source_nodes": sorted(obstacle_nodes),
        "obstacle_source_node_count": len(obstacle_nodes),
        "empty_reference_ply": reference_ply,
        "collision_ply": collision_ply,
        "empty_reference_glb": reference_glb,
        "collision_glb": collision_glb,
    }
    atomic_json(canonical / "geometry_manifest.json", manifest)
    (run_dir / "CANONICAL_SUCCESS").touch()
    print(
        "GPT6_ASTRA_TABLE3_EXPORT "
        + json.dumps(
            {
                "domain": domain,
                "spec_id": spec["spec_id"],
                "source_nodes": len(records),
                "walkable_nodes": len(reference_nodes),
                "obstacle_nodes": len(obstacle_nodes),
                "reference_faces": reference_ply["faces"],
                "collision_faces": collision_ply["faces"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
