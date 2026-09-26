#!/usr/bin/env python3
"""Export and evaluate one reused Infinigen Indoors scene inside Blender.

The source ``.blend`` is never saved.  Native solver instances are merged with
their Blender child meshes, and final evaluated bounds form the common OBB
collision proxies.  Candidate object collisions receive a final mesh-BVH
surface-intersection check; the inexpensive OBB test is only the broad phase.
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
import re
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
if str(BASELINES.parent) not in sys.path:
    sys.path.insert(0, str(BASELINES.parent))

from baselines.evaluation.geometry.metrics.geometry import aabb_overlap_volume
from baselines.evaluation.geometry.metrics.geometry import box_corners
from baselines.evaluation.geometry.metrics.geometry import box_mesh
from baselines.evaluation.geometry.metrics.geometry import convex_hull_2d
from baselines.evaluation.geometry.metrics.geometry import polygon_area
from baselines.evaluation.geometry.metrics.geometry import polygon_area_inside_triangles
from baselines.evaluation.geometry.metrics.geometry import sat_obb_overlap
from baselines.evaluation.geometry.metrics.geometry import support_gap_valid


BOX_FACES = np.asarray(
    [
        (0, 2, 3),
        (0, 3, 1),
        (4, 5, 7),
        (4, 7, 6),
        (0, 1, 5),
        (0, 5, 4),
        (2, 6, 7),
        (2, 7, 3),
        (0, 4, 6),
        (0, 6, 2),
        (1, 3, 7),
        (1, 7, 5),
    ],
    dtype=np.int64,
)


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--table2-run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--object-roles", type=Path, required=True)
    parser.add_argument("--support-rules", type=Path, required=True)
    parser.add_argument("--collision-exceptions", type=Path, required=True)
    parser.add_argument("--bvh-vertex-cap", type=int, default=750_000)
    return parser.parse_args(values)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def semantics(record: dict) -> set[str]:
    answer = set()
    for tag in record.get("tags", []):
        match = re.fullmatch(r"Semantics\((.+)\)", tag)
        if match:
            answer.add(match.group(1))
    return answer


def factory_name(record: dict) -> str:
    value = record.get("generator") or ""
    return value.split("(", 1)[0]


def choose_target_room(records: dict, category: str) -> tuple[str, dict]:
    rooms = {key for key, value in records.items() if "room" in semantics(value)}
    normalized = category.replace("_", "-").lower()
    candidates = [
        key
        for key in rooms
        if normalized
        in {item.replace("_", "-").lower() for item in semantics(records[key])}
    ]
    if not candidates:
        candidates = sorted(rooms)
    direct_counts = {key: 0 for key in candidates}
    for record in records.values():
        if not record.get("generator"):
            continue
        for relation in record.get("relations", []):
            if (
                relation.get("target_name") in direct_counts
                and relation.get("relation", {}).get("relation_type") == "StableAgainst"
            ):
                direct_counts[relation["target_name"]] += 1
    target = min(candidates, key=lambda key: (-direct_counts[key], key))
    return target, {
        "candidate_rooms": sorted(candidates),
        "direct_instance_counts": direct_counts,
    }


def support_targets(record: dict) -> list[str]:
    return [
        relation["target_name"]
        for relation in record.get("relations", [])
        if relation.get("relation", {}).get("relation_type") == "StableAgainst"
    ]


def closure_in_room(records: dict, target_room: str) -> set[str]:
    memo: dict[str, bool] = {}

    def belongs(key: str, stack: tuple[str, ...] = ()) -> bool:
        if key == target_room:
            return True
        if key in memo:
            return memo[key]
        if key in stack:
            return False
        answer = any(
            belongs(parent, stack + (key,))
            for parent in support_targets(records[key])
            if parent in records
        )
        memo[key] = answer
        return answer

    return {
        key
        for key, value in records.items()
        if value.get("active") and value.get("generator") and belongs(key)
    }


def descendants_including(root: bpy.types.Object) -> list[bpy.types.Object]:
    answer = []
    stack = [root]
    while stack:
        item = stack.pop()
        collection_names = {collection.name for collection in item.users_collection}
        is_helper = (
            "spawn_placeholder" in item.name
            or ".cutter" in item.name
            or any(
                name == "placeholders" or name.startswith("placeholders:")
                for name in collection_names
            )
        )
        if item.type == "MESH" and not item.hide_render and not is_helper:
            answer.append(item)
        stack.extend(item.children)
    return answer


def evaluated_bound_corners(obj: bpy.types.Object, depsgraph) -> np.ndarray:
    evaluated = obj.evaluated_get(depsgraph)
    matrix = evaluated.matrix_world
    return np.asarray(
        [
            [float(value) for value in matrix @ Vector(corner)]
            for corner in evaluated.bound_box
        ]
    )


def group_obb(
    root: bpy.types.Object, meshes: list[bpy.types.Object], depsgraph
) -> dict:
    world_corners = np.concatenate(
        [evaluated_bound_corners(obj, depsgraph) for obj in meshes], axis=0
    )
    basis = np.asarray(root.matrix_world.to_3x3(), dtype=float)
    axes = np.zeros((3, 3), dtype=float)
    for index in range(3):
        column = basis[:, index]
        length = float(np.linalg.norm(column))
        axes[:, index] = column / length if length > 1e-9 else np.eye(3)[:, index]
    # Infinigen placements are rigid Z rotations.  Fall back to an AABB if
    # numerical shear leaves a non-orthogonal basis.
    if not np.allclose(axes.T @ axes, np.eye(3), atol=1e-4):
        axes = np.eye(3)
    coordinates = world_corners @ axes
    lower = coordinates.min(axis=0)
    upper = coordinates.max(axis=0)
    center = axes @ ((lower + upper) / 2.0)
    half_sizes = np.maximum((upper - lower) / 2.0, 1e-5)
    corners = box_corners(center, axes, half_sizes)
    return {
        "center": center.tolist(),
        "axes": axes.tolist(),
        "half_sizes": half_sizes.tolist(),
        "corners": corners.tolist(),
        "aabb_min": corners.min(axis=0).tolist(),
        "aabb_max": corners.max(axis=0).tolist(),
        "volume_m3": float(8.0 * np.prod(half_sizes)),
    }


def extract_mesh(obj: bpy.types.Object, depsgraph, vertex_cap: int):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    try:
        if len(mesh.vertices) > vertex_cap:
            vertices = evaluated_bound_corners(obj, depsgraph)
            return vertices, BOX_FACES.copy(), True
        matrix = evaluated.matrix_world
        vertices = np.asarray(
            [
                [float(value) for value in matrix @ vertex.co]
                for vertex in mesh.vertices
            ],
            dtype=np.float64,
        )
        mesh.calc_loop_triangles()
        faces = np.asarray(
            [
                [int(value) for value in triangle.vertices]
                for triangle in mesh.loop_triangles
            ],
            dtype=np.int64,
        )
        return vertices, faces, False
    finally:
        evaluated.to_mesh_clear()


def extract_upward_floor(obj: bpy.types.Object, depsgraph):
    vertices, faces, fallback = extract_mesh(obj, depsgraph, 2_000_000)
    selected = []
    for face in faces:
        a, b, c = vertices[face]
        normal = np.cross(b - a, c - a)
        length = float(np.linalg.norm(normal))
        if length > 1e-10 and normal[2] / length > 0.5:
            selected.append(face)
    if not selected:
        raise RuntimeError(f"No upward floor triangles in {obj.name}")
    selected = np.asarray(selected, dtype=np.int64)
    used = sorted({int(index) for face in selected for index in face})
    remap = {old: new for new, old in enumerate(used)}
    return (
        vertices[used],
        np.asarray([[remap[int(i)] for i in face] for face in selected]),
        fallback,
    )


def combine_meshes(parts):
    vertices = []
    faces = []
    offset = 0
    for part_vertices, part_faces in parts:
        vertices.append(np.asarray(part_vertices, dtype=np.float32))
        faces.append(np.asarray(part_faces, dtype=np.int32) + offset)
        offset += len(part_vertices)
    return np.concatenate(vertices, axis=0), np.concatenate(faces, axis=0)


def mesh_triangles_2d(vertices, faces):
    return [
        [[float(vertices[index][0]), float(vertices[index][1])] for index in face]
        for face in faces
    ]


class BVHCache:
    def __init__(self, depsgraph, vertex_cap: int):
        self.depsgraph = depsgraph
        self.vertex_cap = vertex_cap
        self.cache = {}
        self.fallback_objects: set[str] = set()

    def components(self, key: str, objects: list[bpy.types.Object]):
        if key not in self.cache:
            values = []
            for obj in objects:
                vertices, faces, fallback = extract_mesh(
                    obj, self.depsgraph, self.vertex_cap
                )
                if fallback:
                    self.fallback_objects.add(obj.name)
                if not len(vertices) or not len(faces):
                    continue
                values.append(
                    {
                        "aabb_min": vertices.min(axis=0),
                        "aabb_max": vertices.max(axis=0),
                        "tree": BVHTree.FromPolygons(
                            [Vector(value) for value in vertices],
                            [tuple(int(index) for index in face) for face in faces],
                            all_triangles=True,
                        ),
                    }
                )
            self.cache[key] = values
        return self.cache[key]

    def overlap(self, key_a, objects_a, key_b, objects_b) -> bool:
        for a in self.components(key_a, objects_a):
            for b in self.components(key_b, objects_b):
                if (
                    aabb_overlap_volume(
                        a["aabb_min"], a["aabb_max"], b["aabb_min"], b["aabb_max"]
                    )
                    <= 0
                ):
                    continue
                if a["tree"].overlap(b["tree"]):
                    return True
        return False

    def ray(self, key, objects, origin, direction, distance):
        hits = []
        origin = Vector(origin)
        direction = Vector(direction).normalized()
        for item in self.components(key, objects):
            result = item["tree"].ray_cast(origin, direction, distance)
            if result[0] is not None:
                hits.append(result)
        return min(hits, key=lambda result: result[3]) if hits else None

    def nearest_distance(self, key, objects, points) -> float | None:
        distances = []
        for item in self.components(key, objects):
            for point in points:
                result = item["tree"].find_nearest(Vector(point))
                if result[0] is not None:
                    distances.append(float(result[3]))
        return min(distances) if distances else None


def classify_instance(record: dict, roles: dict) -> tuple[str, bool]:
    factory = factory_name(record)
    tags = semantics(record)
    if factory in roles["thin_or_flexible_factories"] or "no-collision" in tags:
        return "thin_or_flexible", False
    if (
        factory in roles["fixture_factories"]
        or "ceiling-light" in tags
        or "wall-decoration" in tags
    ):
        return "fixture", True
    return "placed_object", True


def semantic_label(record: dict) -> str:
    generic = {
        "object",
        "real-placeholder",
        "handheld-item",
        "office-shelf-item",
        "no-children",
        "no-rotation",
        "single-generator",
        "asset-placeholder-for-children",
    }
    labels = sorted(semantics(record) - generic)
    if labels:
        return labels[0]
    return re.sub(r"Factory$", "", factory_name(record)).lower() or "object"


def choose_support(record: dict, role: str):
    candidates = [
        relation
        for relation in record.get("relations", [])
        if relation.get("relation", {}).get("relation_type") == "StableAgainst"
    ]
    if not candidates:
        return None

    def relation_mount(relation):
        tags = set(relation["relation"].get("child_tags", []))
        if "Subpart(top)" in tags:
            return "ceiling"
        if "Subpart(bottom)" in tags:
            return "gravity"
        if "Subpart(back)" in tags:
            return "wall"
        return "unknown"

    preference = ["gravity", "wall", "ceiling"]
    if role == "fixture":
        preference = ["ceiling", "wall", "gravity"]
    for mount in preference:
        matching = [item for item in candidates if relation_mount(item) == mount]
        if matching:
            item = sorted(matching, key=lambda value: value["target_name"])[0]
            return item, mount
    return candidates[0], "unknown"


def support_samples(obb: dict) -> list[list[float]]:
    center = np.asarray(obb["center"], dtype=float)
    axes = np.asarray(obb["axes"], dtype=float)
    half = np.asarray(obb["half_sizes"], dtype=float)
    z_min = float(np.asarray(obb["corners"])[:, 2].min())
    samples = []
    for u in (-0.6, 0.0, 0.6):
        for v in (-0.6, 0.0, 0.6):
            point = center + u * half[0] * axes[:, 0] + v * half[1] * axes[:, 1]
            samples.append([float(point[0]), float(point[1]), z_min])
    return samples


def evaluate_support(instance, parent_key, parent_objects, mount, cache, gap_limit):
    obb = instance["collision_proxy"]
    corners = np.asarray(obb["corners"], dtype=float)
    if mount == "gravity":
        child_surface = float(corners[:, 2].min())
        hits = []
        samples = support_samples(obb)
        room_floor_parent = parent_key.endswith(":gravity")
        if room_floor_parent:
            parent_top = max(
                float(item["aabb_max"][2])
                for item in cache.components(parent_key, parent_objects)
            )
            ray_origin_z = max(child_surface + 0.10, parent_top + 0.10)
            ray_distance = max(
                0.40, ray_origin_z - min(child_surface, parent_top) + 0.30
            )
        else:
            ray_origin_z = child_surface + 0.10
            ray_distance = 0.40
        for point in samples:
            result = cache.ray(
                parent_key,
                parent_objects,
                [point[0], point[1], ray_origin_z],
                [0.0, 0.0, -1.0],
                ray_distance,
            )
            if result is not None:
                hits.append((point, float(result[0][2])))
        admissible = (
            [value for _, value in hits]
            if room_floor_parent
            else [value for _, value in hits if value <= child_surface + 0.10 + 1e-6]
        )
        support_z = max(admissible) if admissible else None
        gap = child_surface - support_z if support_z is not None else None
        center_supported = any(
            abs(point[0] - obb["center"][0]) < 1e-6
            and abs(point[1] - obb["center"][1]) < 1e-6
            for point, _ in hits
        )
        coverage = len(hits) / len(samples)
        projection_valid = center_supported or coverage >= 0.05
    elif mount == "ceiling":
        child_surface = float(corners[:, 2].max())
        point = obb["center"]
        result = cache.ray(
            parent_key,
            parent_objects,
            [point[0], point[1], child_surface - 0.10],
            [0, 0, 1],
            0.40,
        )
        support_z = float(result[0][2]) if result is not None else None
        gap = support_z - child_surface if support_z is not None else None
        coverage = 1.0 if result is not None else 0.0
        projection_valid = result is not None
    elif mount == "wall":
        points = list(corners) + [np.asarray(obb["center"], dtype=float)]
        gap = cache.nearest_distance(parent_key, parent_objects, points)
        coverage = 1.0 if gap is not None and gap <= gap_limit else 0.0
        projection_valid = coverage > 0.0
    else:
        gap = None
        coverage = 0.0
        projection_valid = False
    valid = (
        support_gap_valid(gap, mount, gap_limit)
        and projection_valid
        and coverage >= 0.05
    )
    return {
        "child": instance["instance_id"],
        "parent": parent_key,
        "mount_type": mount,
        "gap_m": gap,
        "support_projection_coverage": coverage,
        "center_or_projection_valid": projection_valid,
        "valid": valid,
    }


def floor_centroid(vertices, faces):
    weighted = np.zeros(3, dtype=float)
    total = 0.0
    for face in faces:
        triangle = vertices[face]
        area = float(
            np.linalg.norm(
                np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            )
            / 2.0
        )
        weighted += area * triangle.mean(axis=0)
        total += area
    return weighted / total


def point_in_floor(point, floor_triangles) -> bool:
    probe = [
        [point[0] - 0.002, point[1] - 0.002],
        [point[0] + 0.002, point[1] - 0.002],
        [point[0] + 0.002, point[1] + 0.002],
        [point[0] - 0.002, point[1] + 0.002],
    ]
    return (
        polygon_area_inside_triangles(probe, floor_triangles)
        >= polygon_area(probe) * 0.9
    )


def structural_spawn(records, target_room, centroid, floor_z, floor_triangles):
    doors = []
    for key, record in records.items():
        if "door" not in semantics(record):
            continue
        if (
            any(
                relation.get("target_name") == target_room
                and relation.get("relation", {}).get("relation_type") == "CutFrom"
                for relation in record.get("relations", [])
            )
            and record.get("obj") in bpy.data.objects
        ):
            obj = bpy.data.objects[record["obj"]]
            corners = evaluated_bound_corners(
                obj, bpy.context.evaluated_depsgraph_get()
            )
            doors.append((key, corners.mean(axis=0)))
    for key, door_center in sorted(doors):
        direction = centroid[:2] - door_center[:2]
        length = float(np.linalg.norm(direction))
        if length < 1e-6:
            continue
        direction /= length
        for distance in (0.45, 0.65, 0.85, 1.0):
            candidate = [
                float(door_center[0] + distance * direction[0]),
                float(door_center[1] + distance * direction[1]),
                floor_z,
            ]
            if point_in_floor(candidate, floor_triangles):
                return candidate, {
                    "policy": "lexical_first_target_door_inward",
                    "door": key,
                    "inset_m": distance,
                }
    candidate = [float(centroid[0]), float(centroid[1]), floor_z]
    return candidate, {
        "policy": "target_floor_area_centroid",
        "door": None,
        "inset_m": None,
    }


def coverage_groups(instances, target_room, records):
    factories = {item["factory"] for item in instances}
    tags = {tag for item in instances for tag in item["native_semantics"]}
    groups = set()
    if any("Bed" in value for value in factories) or "bed" in tags:
        groups.add("bed")
    if (
        any(
            value in factories
            for value in {"SofaFactory", "ChairFactory", "DiningChairFactory"}
        )
        or "seating" in tags
    ):
        groups.add("seating")
    if (
        any("Table" in value or "Desk" in value for value in factories)
        or "table" in tags
    ):
        groups.add("table")
    if (
        any(
            value in factories for value in {"DiningTableFactory", "TableDiningFactory"}
        )
        or "dining-table" in tags
    ):
        groups.add("dining_table")
    if any(
        "Cabinet" in value or "Shelf" in value or "Bookcase" in value
        for value in factories
    ):
        groups.add("storage")
    if (
        any(
            value in factories
            for value in {
                "OvenFactory",
                "DishwasherFactory",
                "MicrowaveFactory",
                "BeverageFridgeFactory",
            }
        )
        or "kitchen-appliance" in tags
    ):
        groups.add("kitchen_appliance")
    if (
        any(value in factories for value in {"SinkFactory", "StandingSinkFactory"})
        or "sink" in tags
    ):
        groups.add("sink")
    if any(value == "ToiletFactory" for value in factories):
        groups.add("toilet")
    if any("LightFactory" in value for value in factories):
        groups.add("lighting")
    if any("RugFactory" in value for value in factories):
        groups.add("rug")
    if any("Plant" in value for value in factories):
        groups.add("plant")
    if any(
        "window" in semantics(record)
        and any(
            relation.get("target_name") == target_room
            for relation in record.get("relations", [])
        )
        for record in records.values()
    ):
        groups.add("window")
    if any(
        "door" in semantics(record)
        and any(
            relation.get("target_name") == target_room
            for relation in record.get("relations", [])
        )
        for record in records.values()
    ):
        groups.add("door")
    return sorted(groups)


def write_glb(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    mesh = bpy.data.meshes.new("table3_collision_mesh")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new("table3_collision", mesh)
    collection = bpy.data.collections.new("table3_canonical")
    bpy.context.scene.collection.children.link(collection)
    collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=False,
    )


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    source_dir = args.table2_run_dir.resolve()
    spec = read_json(args.spec)
    roles = read_json(args.object_roles)
    support_rules = read_json(args.support_rules)
    collision_rules = read_json(args.collision_exceptions)
    records = read_json(source_dir / "scene/solve_state.json")["objs"]
    target_room, selection_audit = choose_target_room(records, spec["category"])
    member_keys = closure_in_room(records, target_room)
    depsgraph = bpy.context.evaluated_depsgraph_get()

    floor_obj = bpy.data.objects.get(target_room + ".floor")
    wall_obj = bpy.data.objects.get(target_room + ".wall")
    ceiling_obj = bpy.data.objects.get(target_room + ".ceiling")
    if not floor_obj or not wall_obj or not ceiling_obj:
        raise RuntimeError(f"Incomplete room geometry for {target_room}")
    floor_vertices, floor_faces, floor_fallback = extract_upward_floor(
        floor_obj, depsgraph
    )
    wall_vertices, wall_faces, wall_fallback = extract_mesh(
        wall_obj, depsgraph, 2_000_000
    )
    floor_triangles = mesh_triangles_2d(floor_vertices, floor_faces)
    floor_area = float(sum(polygon_area(triangle) for triangle in floor_triangles))
    floor_z = float(np.median(floor_vertices[:, 2]))
    centroid = floor_centroid(floor_vertices, floor_faces)

    instances = []
    missing_native_objects = []
    group_objects = {}
    for key in sorted(member_keys):
        record = records[key]
        object_name = record.get("obj")
        root = bpy.data.objects.get(object_name)
        if root is None:
            missing_native_objects.append(
                {"solver_id": key, "object_name": object_name}
            )
            continue
        meshes = descendants_including(root)
        if not meshes:
            missing_native_objects.append(
                {
                    "solver_id": key,
                    "object_name": object_name,
                    "reason": "no_mesh_descendants",
                }
            )
            continue
        role, eligible = classify_instance(record, roles)
        obb = group_obb(root, meshes, depsgraph)
        item = {
            "instance_id": key,
            "semantic": semantic_label(record),
            "factory": factory_name(record),
            "role": role,
            "mesh_node": object_name,
            "mesh_nodes": [obj.name for obj in meshes],
            "container_id": target_room,
            "include_collision": eligible,
            "include_floating": eligible,
            "include_oob": eligible,
            "source": "native_infinigen_solve_state+final_evaluated_blender_bounds",
            "native_semantics": sorted(semantics(record)),
            "collision_proxy": obb,
        }
        support = choose_support(record, role) if eligible else None
        if support:
            relation, mount = support
            item.update(
                {
                    "support_parent": relation["target_name"],
                    "mount_type": mount,
                    "native_support_relation": relation,
                }
            )
        else:
            item.update(
                {
                    "support_parent": None,
                    "mount_type": None,
                    "native_support_relation": None,
                }
            )
        instances.append(item)
        group_objects[key] = meshes

    room_support_objects = {
        (target_room, "gravity"): [floor_obj],
        (target_room, "ceiling"): [ceiling_obj],
        (target_room, "wall"): [wall_obj],
    }
    instance_by_id = {item["instance_id"]: item for item in instances}
    cache = BVHCache(depsgraph, args.bvh_vertex_cap)
    support_edges = []
    for item in instances:
        if not item["include_floating"]:
            continue
        parent = item["support_parent"]
        mount = item["mount_type"]
        if parent == target_room:
            parent_objects = room_support_objects[(target_room, mount)]
            parent_key = f"{target_room}:{mount}"
        elif parent in group_objects:
            parent_objects = group_objects[parent]
            parent_key = parent
        else:
            support_edges.append(
                {
                    "child": item["instance_id"],
                    "parent": parent,
                    "mount_type": mount,
                    "gap_m": None,
                    "support_projection_coverage": 0.0,
                    "center_or_projection_valid": False,
                    "valid": False,
                    "failure": "missing_support_parent_geometry",
                }
            )
            continue
        support_edges.append(
            evaluate_support(
                item,
                parent_key,
                parent_objects,
                mount,
                cache,
                float(support_rules["support_gap_m"]),
            )
        )
    support_by_child = {edge["child"]: edge for edge in support_edges}

    # Exact target-floor containment of the final evaluated instance envelope.
    oob_objects = set()
    oob_records = []
    allowed_fixture_crossing = set(collision_rules["allowed_boundary_crossing_roles"])
    for item in instances:
        if not item["include_oob"]:
            continue
        footprint = convex_hull_2d(
            np.asarray(item["collision_proxy"]["corners"])[:, :2]
        )
        area = polygon_area(footprint)
        inside = min(area, polygon_area_inside_triangles(footprint, floor_triangles))
        outside_ratio = 1.0 if area <= 1e-12 else max(0.0, 1.0 - inside / area)
        center_inside = point_in_floor(
            item["collision_proxy"]["center"], floor_triangles
        )
        allowed = item["role"] in allowed_fixture_crossing
        is_oob = not allowed and (
            not center_inside
            or outside_ratio > float(collision_rules["oob_area_ratio"])
        )
        if is_oob:
            oob_objects.add(item["instance_id"])
        oob_records.append(
            {
                "instance_id": item["instance_id"],
                "footprint_area_m2": area,
                "outside_area_ratio": outside_ratio,
                "center_inside": center_inside,
                "allowed_boundary_crossing": allowed,
                "oob": is_oob,
            }
        )

    eligible = [item for item in instances if item["include_collision"]]
    collision_objects = set(oob_objects)
    collision_pairs = [
        {
            "a": key,
            "b": target_room + ":wall",
            "reason": "container_boundary_violation",
            "significant": True,
        }
        for key in sorted(oob_objects)
    ]
    penetration_threshold = float(collision_rules["penetration_depth_m"])
    embedded_support_children = {
        edge["child"]
        for edge in support_edges
        if edge.get("gap_m") is not None and edge["gap_m"] < -penetration_threshold
    }
    collision_objects.update(embedded_support_children)
    collision_pairs.extend(
        {
            "a": edge["child"],
            "b": edge["parent"],
            "reason": "support_embedding",
            "support_gap_m": edge["gap_m"],
            "significant": True,
        }
        for edge in support_edges
        if edge["child"] in embedded_support_children
    )
    support_pairs = {
        frozenset((edge["child"], edge["parent"]))
        for edge in support_edges
        if edge.get("parent") in instance_by_id
    }
    for index, a in enumerate(eligible):
        for b in eligible[index + 1 :]:
            sat = sat_obb_overlap(a["collision_proxy"], b["collision_proxy"])
            if not sat["overlap"]:
                continue
            overlap_volume = aabb_overlap_volume(
                np.asarray(a["collision_proxy"]["aabb_min"]),
                np.asarray(a["collision_proxy"]["aabb_max"]),
                np.asarray(b["collision_proxy"]["aabb_min"]),
                np.asarray(b["collision_proxy"]["aabb_max"]),
            )
            volume_threshold = overlap_volume > float(
                collision_rules["overlap_volume_m3"]
            ) and overlap_volume > float(
                collision_rules["smaller_object_volume_fraction"]
            ) * min(
                a["collision_proxy"]["volume_m3"], b["collision_proxy"]["volume_m3"]
            )
            significant_proxy = (
                sat["penetration_depth_m"]
                > float(collision_rules["penetration_depth_m"])
                or volume_threshold
            )
            if not significant_proxy:
                continue
            pair = frozenset((a["instance_id"], b["instance_id"]))
            if pair in support_pairs:
                # The primary support edge was already checked directly above.
                continue
            else:
                actual_overlap = cache.overlap(
                    a["instance_id"],
                    group_objects[a["instance_id"]],
                    b["instance_id"],
                    group_objects[b["instance_id"]],
                )
                reason = "mesh_bvh_surface_intersection"
            collision_pairs.append(
                {
                    "a": a["instance_id"],
                    "b": b["instance_id"],
                    "proxy_penetration_depth_m": sat["penetration_depth_m"],
                    "proxy_aabb_overlap_volume_m3": overlap_volume,
                    "actual_mesh_overlap": actual_overlap,
                    "reason": reason,
                    "significant": bool(actual_overlap),
                }
            )
            if actual_overlap:
                collision_objects.update((a["instance_id"], b["instance_id"]))

    support_required = len(support_edges)
    invalid_support = {edge["child"] for edge in support_edges if not edge["valid"]}
    floating_objects = set(invalid_support)
    denominator = len(eligible)
    detected_groups = coverage_groups(instances, target_room, records)
    required_groups = spec.get("required_instance_groups", [])
    missing_groups = sorted(set(required_groups) - set(detected_groups))
    output_contract = (
        not missing_native_objects
        and denominator > 0
        and not missing_groups
        and floor_area > 1.0
    )
    structural = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "spec_id": spec["spec_id"],
        "seed": read_json(source_dir / "run_manifest.json")["logical_seed"],
        "target_room": target_room,
        "eligible_objects": denominator,
        "collision_objects": len(collision_objects),
        "collision_rate": 100.0 * len(collision_objects) / denominator
        if denominator
        else 100.0,
        "support_required_objects": support_required,
        "floating_objects": len(floating_objects),
        "floating_rate": 100.0 * len(floating_objects) / support_required
        if support_required
        else 100.0,
        "oob_objects": len(oob_objects),
        "oob_rate": 100.0 * len(oob_objects) / denominator if denominator else 100.0,
        "required_support_edges": support_required,
        "valid_support_edges": support_required - len(invalid_support),
        "support_validity": 100.0
        * (support_required - len(invalid_support))
        / support_required
        if support_required
        else 0.0,
        "pairs": collision_pairs,
        "support_edges": support_edges,
        "oob_details": oob_records,
        "output_contract_passed": output_contract,
        "detected_instance_groups": detected_groups,
        "required_instance_groups": required_groups,
        "missing_instance_groups": missing_groups,
        "failures": [],
    }

    spawn, spawn_audit = structural_spawn(
        records, target_room, centroid, floor_z, floor_triangles
    )
    proxy_parts = [(floor_vertices, floor_faces), (wall_vertices, wall_faces)]
    for item in eligible:
        if item["role"] == "thin_or_flexible":
            continue
        proxy_parts.append(
            box_mesh(
                item["collision_proxy"]["center"],
                item["collision_proxy"]["axes"],
                item["collision_proxy"]["half_sizes"],
            )
        )
    reference_vertices, reference_faces = combine_meshes(
        [(floor_vertices, floor_faces), (wall_vertices, wall_faces)]
    )
    final_vertices, final_faces = combine_meshes(proxy_parts)

    canonical = run_dir / "scene/canonical"
    metrics_dir = run_dir / "metrics"
    navigation_dir = run_dir / "navigation"
    raw_dir = run_dir / "scene/raw"
    for directory in (
        canonical,
        metrics_dir,
        navigation_dir,
        raw_dir,
        run_dir / "input",
        run_dir / "logs",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    destination_spec = run_dir / "input/spec.json"
    if args.spec.resolve() != destination_spec.resolve():
        shutil.copy2(args.spec, destination_spec)
    shutil.copy2(
        source_dir / "input/native_input.json", run_dir / "input/native_input.json"
    )
    np.savez_compressed(
        canonical / "empty_reference_geometry.npz",
        vertices=reference_vertices,
        faces=reference_faces,
    )
    np.savez_compressed(
        canonical / "collision_geometry.npz", vertices=final_vertices, faces=final_faces
    )
    write_glb(canonical / "collision.glb", final_vertices, final_faces)
    atomic_json(
        canonical / "instances.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "instance_source": "native",
            "target_room": target_room,
            "instances": instances,
            "missing_native_objects": missing_native_objects,
        },
    )
    atomic_json(
        canonical / "transform.json",
        {
            "source_coordinate_system": "right-handed-z-up",
            "canonical_coordinate_system": "right-handed-z-up",
            "source_unit": "meter",
            "canonical_unit": "meter",
            "matrix_source_to_canonical": np.eye(4).tolist(),
            "scale_source": "Infinigen native meter-scale Blender scene",
        },
    )
    boundaries = {
        "target_room": target_room,
        "evaluation_roi": "native_target_room_floor",
        "floor_area_m2": floor_area,
        "floor_z_m": floor_z,
        "floor_triangles_xy_m": floor_triangles,
        "structural_spawn_candidate_m": spawn,
        "spawn_policy": spawn_audit,
        "selection_audit": selection_audit,
    }
    atomic_json(run_dir / "input/boundaries.json", boundaries)
    atomic_json(metrics_dir / "structural.json", structural)
    source_scene = source_dir / "scene/scene.blend"
    atomic_json(
        raw_dir / "REFERENCE.json",
        {
            "preserved_by_reference": True,
            "path": str(source_scene),
            "size_bytes": source_scene.stat().st_size,
            "sha256": sha256_file(source_scene),
            "table2_manifest": str(source_dir / "run_manifest.json"),
        },
    )
    export_record = {
        "target_room": target_room,
        "native_instance_count": len(member_keys),
        "exported_instance_count": len(instances),
        "eligible_instance_count": denominator,
        "floor_area_m2": floor_area,
        "reference_triangles": len(reference_faces),
        "final_triangles": len(final_faces),
        "floor_proxy_fallback": floor_fallback,
        "wall_proxy_fallback": wall_fallback,
        "mesh_bvh_fallback_objects": sorted(cache.fallback_objects),
        "bvh_vertex_cap": args.bvh_vertex_cap,
    }
    atomic_json(run_dir / "logs/export_record.json", export_record)
    print("TABLE3_EXPORT_COMPLETE=" + json.dumps(export_record, separators=(",", ":")))


if __name__ == "__main__":
    main()
