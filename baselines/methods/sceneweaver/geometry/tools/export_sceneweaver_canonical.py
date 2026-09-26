"""Export and evaluate one final SceneWeaver Blender scene.

Run this file through Blender after opening the retained Table-2 ``scene.blend``.
It never saves the source blend.  Object identity comes from the final native
layout and is matched to the final evaluated ``unique_assets`` meshes by
Factory class, size, and position.
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
import itertools
import json
import math
import re
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


FACE_CAP = 20_000
COLLISION_DEPTH_M = 0.01
COLLISION_VOLUME_M3 = 1e-5
COLLISION_SMALLER_VOLUME_FRACTION = 0.005
FLOATING_GAP_M = 0.02
OOB_RATIO = 0.01
SUPPORT_OVERLAP_RATIO = 0.05
SUPPORT_RELATIONS = {
    "onfloor": "gravity_floor",
    "on_floor": "gravity_floor",
    "on": "gravity_parent",
    "ontop": "gravity_parent",
    "on_top": "gravity_parent",
    "against_wall": "wall_attachment",
    "onwall": "wall_attachment",
    "on_wall": "wall_attachment",
    "onceiling": "ceiling_attachment",
    "on_ceiling": "ceiling_attachment",
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--face-cap", type=int, default=FACE_CAP)
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
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def factory_from_layout(name: str) -> str:
    return name.split("_", 1)[1] if "_" in name else name


def factory_from_blender(name: str) -> str:
    match = re.match(r"^([^.(]+Factory)\(", name)
    return match.group(1) if match else name.split("(", 1)[0]


def semantic_from_factory(factory: str) -> str:
    stem = re.sub(r"Factory$", "", factory)
    return re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()


def role_for(factory: str) -> str:
    if re.search(
        r"(?i)(window|door|mirror|picture|wallart|walldecor|wallshelf|ceiling|pendant|chandelier|walllamp)",
        factory,
    ):
        return "fixture"
    if re.search(r"(?i)(rug|carpet|curtain|blanket|cloth|wire)", factory):
        return "thin_or_flexible"
    return "placed_object"


def world_bounds(obj: bpy.types.Object) -> tuple[list[float], list[float]]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        [min(corner[axis] for corner in corners) for axis in range(3)],
        [max(corner[axis] for corner in corners) for axis in range(3)],
    )


def match_layout_objects(layout: dict) -> tuple[dict[str, bpy.types.Object], list[str]]:
    collection = bpy.data.collections.get("unique_assets")
    candidates = (
        [obj for obj in collection.objects if obj.type == "MESH"]
        if collection is not None
        else []
    )
    by_factory: dict[str, list[bpy.types.Object]] = {}
    for obj in candidates:
        by_factory.setdefault(factory_from_blender(obj.name), []).append(obj)

    matched: dict[str, bpy.types.Object] = {}
    used_objects: set[bpy.types.Object] = set()
    errors: list[str] = []
    records = layout.get("objects", {})
    for factory, grouped in itertools.groupby(
        sorted(records, key=factory_from_layout), key=factory_from_layout
    ):
        keys = list(grouped)
        objects = by_factory.get(factory, [])
        objects = [obj for obj in objects if obj not in used_objects]
        available = set(range(len(objects)))
        pairs = []
        for key in keys:
            record = records[key]
            location = [float(value) for value in record.get("location", [0, 0, 0])]
            size = [abs(float(value)) for value in record.get("size", [0, 0, 0])]
            for index, obj in enumerate(objects):
                minimum, maximum = world_bounds(obj)
                center = [(minimum[i] + maximum[i]) * 0.5 for i in range(3)]
                dimensions = [maximum[i] - minimum[i] for i in range(3)]
                # Native layout Z is the nominal base while Blender origins
                # differ by asset, so XY and dimensions dominate identity.
                xy_cost = math.hypot(center[0] - location[0], center[1] - location[1])
                size_cost = sum(abs(dimensions[i] - size[i]) for i in range(3))
                pairs.append((xy_cost + 0.5 * size_cost, key, index))
        for _, key, index in sorted(pairs):
            if key in matched or index not in available:
                continue
            matched[key] = objects[index]
            used_objects.add(objects[index])
            available.remove(index)

    # Objaverse records use a semantic layout key such as ``wardrobe`` while
    # every Blender node is named ``ObjaverseCategoryFactory``.  Resolve only
    # the still-unmatched records and meshes by final XY/size assignment; this
    # cannot disturb exact native Factory matches above.
    remaining_keys = [key for key in records if key not in matched]
    remaining_objects = [obj for obj in candidates if obj not in used_objects]
    fallback_pairs = []
    for key in remaining_keys:
        record = records[key]
        location = [float(value) for value in record.get("location", [0, 0, 0])]
        size = [abs(float(value)) for value in record.get("size", [0, 0, 0])]
        for index, obj in enumerate(remaining_objects):
            minimum, maximum = world_bounds(obj)
            center = [(minimum[i] + maximum[i]) * 0.5 for i in range(3)]
            dimensions = [maximum[i] - minimum[i] for i in range(3)]
            xy_cost = math.hypot(center[0] - location[0], center[1] - location[1])
            size_cost = sum(abs(dimensions[i] - size[i]) for i in range(3))
            fallback_pairs.append((xy_cost + 0.5 * size_cost, key, index))
    fallback_available = set(range(len(remaining_objects)))
    for _, key, index in sorted(fallback_pairs):
        if key in matched or index not in fallback_available:
            continue
        matched[key] = remaining_objects[index]
        used_objects.add(remaining_objects[index])
        fallback_available.remove(index)
    for key in records:
        if key not in matched:
            errors.append(f"unmatched_layout_instance:{key}")
    unexpected = sorted(
        obj.name for obj in candidates if obj not in set(matched.values())
    )
    errors.extend(f"unmatched_native_mesh:{name}" for name in unexpected)
    return matched, errors


def apply_decimation(obj: bpy.types.Object, face_cap: int) -> bpy.types.Object:
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.animation_data_clear()
    bpy.context.scene.collection.objects.link(duplicate)
    duplicate.matrix_world = obj.matrix_world.copy()
    polygon_count = len(duplicate.data.polygons)
    if polygon_count > face_cap:
        modifier = duplicate.modifiers.new("Table3UniformDecimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = max(0.0001, min(1.0, face_cap / float(polygon_count)))
        modifier.use_collapse_triangulate = True
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        duplicate.select_set(True)
        bpy.context.view_layer.objects.active = duplicate
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return duplicate


def proxy_geometry(
    obj: bpy.types.Object, face_cap: int
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], dict]:
    source_faces = len(obj.data.polygons)
    duplicate = apply_decimation(obj, face_cap)
    mesh = duplicate.data
    mesh.calc_loop_triangles()
    raw_vertices = [
        tuple(duplicate.matrix_world @ vertex.co) for vertex in mesh.vertices
    ]
    faces = [tuple(int(index) for index in tri.vertices) for tri in mesh.loop_triangles]
    used = sorted({index for face in faces for index in face})
    if not used:
        raise RuntimeError(f"Final mesh has no evaluated triangles: {obj.name}")
    remap = {old: new for new, old in enumerate(used)}
    vertices = [raw_vertices[index] for index in used]
    faces = [tuple(remap[index] for index in face) for face in faces]
    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    metadata = {
        "source_faces": source_faces,
        "proxy_faces": len(faces),
        "source_vertices": len(obj.data.vertices),
        "proxy_vertices": len(vertices),
        "simplification": "none"
        if source_faces <= face_cap
        else "blender_decimate_collapse",
        "world_aabb_min": minimum,
        "world_aabb_max": maximum,
    }
    data = duplicate.data
    bpy.data.objects.remove(duplicate, do_unlink=True)
    if data.users == 0:
        bpy.data.meshes.remove(data)
    return vertices, faces, metadata


def cross(
    o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set((round(x, 7), round(y, 7)) for x, y in points))
    if len(unique) <= 2:
        return unique
    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def polygon_area(polygon: list[tuple[float, float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    return 0.5 * abs(
        sum(
            polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
            - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
            for index in range(len(polygon))
        )
    )


def clip_halfplane(
    polygon: list[tuple[float, float]], axis: int, bound: float, keep_greater: bool
) -> list[tuple[float, float]]:
    if not polygon:
        return []

    def inside(point: tuple[float, float]) -> bool:
        return point[axis] >= bound if keep_greater else point[axis] <= bound

    output: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside != previous_inside:
            delta = current[axis] - previous[axis]
            ratio = 0.0 if abs(delta) < 1e-12 else (bound - previous[axis]) / delta
            point = (
                previous[0] + ratio * (current[0] - previous[0]),
                previous[1] + ratio * (current[1] - previous[1]),
            )
            output.append(point)
        if current_inside:
            output.append(current)
        previous, previous_inside = current, current_inside
    return output


def clip_rectangle(
    polygon: list[tuple[float, float]], width: float, depth: float
) -> list[tuple[float, float]]:
    result = polygon
    for axis, bound, greater in (
        (0, 0.0, True),
        (0, width, False),
        (1, 0.0, True),
        (1, depth, False),
    ):
        result = clip_halfplane(result, axis, bound, greater)
    return result


def point_in_convex(
    point: tuple[float, float], polygon: list[tuple[float, float]]
) -> bool:
    if len(polygon) < 3:
        return False
    signs = [
        cross(polygon[index], polygon[(index + 1) % len(polygon)], point)
        for index in range(len(polygon))
    ]
    return all(value >= -1e-7 for value in signs) or all(
        value <= 1e-7 for value in signs
    )


def convex_intersection(
    subject: list[tuple[float, float]], clipper: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    if len(subject) < 3 or len(clipper) < 3:
        return []
    output = subject
    orientation = sum(
        clipper[index][0] * clipper[(index + 1) % len(clipper)][1]
        - clipper[(index + 1) % len(clipper)][0] * clipper[index][1]
        for index in range(len(clipper))
    )
    for index in range(len(clipper)):
        edge_a = clipper[index]
        edge_b = clipper[(index + 1) % len(clipper)]
        source = output
        output = []
        if not source:
            break

        def inside(point: tuple[float, float]) -> bool:
            value = cross(edge_a, edge_b, point)
            return value >= -1e-8 if orientation >= 0 else value <= 1e-8

        previous = source[-1]
        previous_inside = inside(previous)
        for current in source:
            current_inside = inside(current)
            if current_inside != previous_inside:
                dc = (edge_a[0] - edge_b[0], edge_a[1] - edge_b[1])
                dp = (previous[0] - current[0], previous[1] - current[1])
                n1 = edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]
                n2 = previous[0] * current[1] - previous[1] * current[0]
                denominator = dc[0] * dp[1] - dc[1] * dp[0]
                if abs(denominator) > 1e-12:
                    output.append(
                        (
                            (n1 * dp[0] - n2 * dc[0]) / denominator,
                            (n1 * dp[1] - n2 * dc[1]) / denominator,
                        )
                    )
            if current_inside:
                output.append(current)
            previous, previous_inside = current, current_inside
    return output


def aabb_overlap(a: dict, b: dict) -> list[float]:
    return [
        min(a["world_aabb_max"][axis], b["world_aabb_max"][axis])
        - max(a["world_aabb_min"][axis], b["world_aabb_min"][axis])
        for axis in range(3)
    ]


def aabb_volume(proxy: dict) -> float:
    return math.prod(
        max(0.0, proxy["world_aabb_max"][axis] - proxy["world_aabb_min"][axis])
        for axis in range(3)
    )


def write_ply(
    path: Path,
    parts: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]],
) -> dict:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for part_vertices, part_faces in parts:
        offset = len(vertices)
        vertices.extend(part_vertices)
        faces.extend(tuple(index + offset for index in face) for face in part_faces)
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


def export_glb_from_parts(
    path: Path,
    parts: list[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]],
) -> dict:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for part_vertices, part_faces in parts:
        offset = len(vertices)
        vertices.extend(part_vertices)
        faces.extend(tuple(index + offset for index in face) for face in part_faces)
    mesh = bpy.data.meshes.new("Table3CanonicalMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Table3CanonicalCollision", mesh)
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


GROUP_ALIASES = {
    "bed": ("bed",),
    "bedside_table": ("side_table", "nightstand", "bedside"),
    "wardrobe": ("cabinet", "wardrobe"),
    "chest_of_drawers": ("cabinet", "dresser", "drawer"),
    "window": ("window",),
    "desk": ("desk",),
    "chair": ("chair", "stool"),
    "bookcase": ("bookcase", "bookshelf"),
    "rug": ("rug", "carpet"),
    "mirror": ("mirror",),
    "table_lamp": ("desk_lamp", "table_lamp"),
    "ceiling_light": ("ceiling", "pendant", "chandelier"),
    "floor_lamp": ("floor_lamp",),
    "task_light": ("lamp", "light"),
    "wall_art": ("picture", "wall_art", "wall_decor"),
    "sofa": ("sofa",),
    "armchair": ("arm_chair", "armchair", "chair"),
    "coffee_table": ("coffee_table",),
    "side_table": ("side_table",),
    "television": ("television", "tv"),
    "television_console": ("television_console", "tv_stand", "cabinet"),
    "refrigerator": ("fridge", "refrigerator"),
    "stove": ("oven", "stove", "cooktop"),
    "counter": ("kitchen_cabinet", "counter"),
    "cabinet": ("cabinet",),
    "sink": ("sink", "vanity"),
    "toilet": ("toilet",),
    "shower": ("shower",),
    "bathtub": ("bathtub", "bath_tub"),
    "towel_rail": ("towel",),
    "dining_table": ("table_dining", "dining_table", "table"),
    "plant": ("plant",),
    "storage": (
        "cabinet",
        "wardrobe",
        "bookcase",
        "bookshelf",
        "shelf",
        "dresser",
        "drawer",
    ),
    "seating": ("chair", "sofa", "stool", "seat"),
    "table": ("table",),
    "kitchen_appliance": ("fridge", "refrigerator", "oven", "stove", "cooktop"),
}


def coverage(spec: dict, instances: list[dict]) -> tuple[bool, list[dict]]:
    semantics = [instance["semantic"] for instance in instances]
    records = []
    passed = True
    for requirement in spec.get("required_instance_groups", []):
        if isinstance(requirement, str):
            group, minimum = requirement, 1
        else:
            group, minimum = requirement["group"], int(requirement["min_count"])
        aliases = GROUP_ALIASES.get(group, (group,))
        count = sum(
            any(alias in semantic for alias in aliases) for semantic in semantics
        )
        ok = count >= minimum
        passed = passed and ok
        records.append(
            {"group": group, "minimum": minimum, "observed": count, "passed": ok}
        )
    return passed, records


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    source_run = args.source_run.resolve()
    layout_path = source_run / "scene/layout.json"
    spec_path = run_dir / "input/spec.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    width, depth = [float(value) for value in layout["roomsize"][:2]]
    matched, matching_errors = match_layout_objects(layout)

    proxies: dict[str, dict] = {}
    instances = []
    for layout_key, obj in matched.items():
        vertices, faces, geometry = proxy_geometry(obj, args.face_cap)
        factory = factory_from_layout(layout_key)
        role = role_for(factory)
        hull = convex_hull([(vertex[0], vertex[1]) for vertex in vertices])
        parents = [
            {"parent": str(parent[0]), "relation": str(parent[1]).lower()}
            for parent in layout["objects"][layout_key].get("parent", [])
            if isinstance(parent, list) and len(parent) >= 2
        ]
        record = {
            "instance_id": layout_key,
            "semantic": semantic_from_factory(factory),
            "native_factory": factory,
            "role": role,
            "mesh_node": obj.name,
            "container_id": "room_0",
            "native_relations": parents,
            "include_collision": role == "placed_object",
            "include_floating": role == "placed_object",
            "source": "native_final_layout_and_mesh",
            "footprint_convex_hull_xy_m": hull,
            **geometry,
        }
        proxies[layout_key] = {"vertices": vertices, "faces": faces, **record}
        instances.append(record)

    floor_collection = bpy.data.collections.get("unique_assets:room_floor")
    wall_collection = bpy.data.collections.get("unique_assets:room_wall")
    structural_objects = []
    if floor_collection is not None:
        structural_objects.extend(
            obj for obj in floor_collection.objects if obj.type == "MESH"
        )
    if wall_collection is not None:
        structural_objects.extend(
            obj for obj in wall_collection.objects if obj.type == "MESH"
        )
    if not structural_objects:
        fallback = bpy.data.collections.get("placeholders:room_meshes")
        if fallback is not None:
            structural_objects.extend(
                obj for obj in fallback.objects if obj.type == "MESH"
            )
    structure_parts = []
    wall_parts = []
    structure_meta = []
    floor_z_values = []
    floor_vertices: list[tuple[float, float, float]] = []
    floor_faces: list[tuple[int, int, int]] = []
    ceiling_z_values = []
    for obj in structural_objects:
        vertices, faces, meta = proxy_geometry(obj, args.face_cap)
        structure_parts.append((vertices, faces))
        if wall_collection is not None and obj.name in wall_collection.objects:
            wall_parts.append((obj.name, vertices, faces, meta))
        structure_meta.append({"mesh_node": obj.name, **meta})
        if "floor" in obj.name.lower():
            floor_z_values.extend(vertex[2] for vertex in vertices)
            floor_vertices.extend(vertices)
            floor_faces.extend(faces)
        ceiling_z_values.extend(vertex[2] for vertex in vertices)
    if not floor_z_values:
        floor_z_values = [0.0]
    floor_z = sum(floor_z_values) / len(floor_z_values)
    ceiling_z = max(ceiling_z_values or [float(spec["extent_m"][2])])
    floor_hull = convex_hull([(vertex[0], vertex[1]) for vertex in floor_vertices])
    if len(floor_hull) < 3:
        floor_hull = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    floor_bounds = (
        min(point[0] for point in floor_hull),
        max(point[0] for point in floor_hull),
        min(point[1] for point in floor_hull),
        max(point[1] for point in floor_hull),
    )

    eligible = [record for record in instances if record["role"] == "placed_object"]
    support_eligible = [
        record for record in instances if record["role"] in {"placed_object", "fixture"}
    ]
    collision_ids: set[str] = set()
    pair_records = []
    bvh = {}
    for record in eligible:
        proxy = proxies[record["instance_id"]]
        bvh[record["instance_id"]] = BVHTree.FromPolygons(
            [Vector(vertex) for vertex in proxy["vertices"]],
            proxy["faces"],
            all_triangles=True,
            epsilon=0.0,
        )
    wall_bvhs = [
        (
            wall_name,
            BVHTree.FromPolygons(
                [Vector(vertex) for vertex in wall_vertices],
                wall_faces,
                all_triangles=True,
                epsilon=0.0,
            ),
        )
        for wall_name, wall_vertices, wall_faces, _ in wall_parts
    ]
    support_pairs = {
        (record["instance_id"], relation["parent"])
        for record in instances
        for relation in record["native_relations"]
        if SUPPORT_RELATIONS.get(relation["relation"]) == "gravity_parent"
    }
    for left_index, left in enumerate(eligible):
        left_proxy = proxies[left["instance_id"]]
        for right in eligible[left_index + 1 :]:
            right_proxy = proxies[right["instance_id"]]
            overlaps = aabb_overlap(left_proxy, right_proxy)
            if min(overlaps) < -1e-7:
                continue
            actual_overlap = bvh[left["instance_id"]].overlap(bvh[right["instance_id"]])
            if not actual_overlap:
                continue
            penetration_proxy = max(0.0, min(overlaps))
            overlap_volume_proxy = math.prod(max(0.0, value) for value in overlaps)
            volume_significant = (
                overlap_volume_proxy > COLLISION_VOLUME_M3
                and overlap_volume_proxy
                > COLLISION_SMALLER_VOLUME_FRACTION
                * min(aabb_volume(left_proxy), aabb_volume(right_proxy))
            )
            is_support_pair = (
                left["instance_id"],
                right["instance_id"],
            ) in support_pairs or (
                right["instance_id"],
                left["instance_id"],
            ) in support_pairs
            significant = penetration_proxy > COLLISION_DEPTH_M or volume_significant
            if is_support_pair and penetration_proxy <= COLLISION_DEPTH_M:
                significant = False
            pair_records.append(
                {
                    "a": left["instance_id"],
                    "b": right["instance_id"],
                    "actual_proxy_triangle_intersections": len(actual_overlap),
                    "aabb_axis_overlap_m": overlaps,
                    "penetration_depth_proxy_m": penetration_proxy,
                    "overlap_volume_proxy_m3": overlap_volume_proxy,
                    "volume_threshold_exceeded": volume_significant,
                    "registered_support_pair": is_support_pair,
                    "significant": significant,
                }
            )
            if significant:
                collision_ids.update((left["instance_id"], right["instance_id"]))

    oob_ids: set[str] = set()
    oob_records = []
    for record in eligible:
        proxy = proxies[record["instance_id"]]
        hull = proxy["footprint_convex_hull_xy_m"]
        area = polygon_area(hull)
        inside_area = polygon_area(convex_intersection(hull, floor_hull))
        outside_ratio = 1.0 if area <= 1e-12 else max(0.0, 1.0 - inside_area / area)
        center = (
            0.5 * (proxy["world_aabb_min"][0] + proxy["world_aabb_max"][0]),
            0.5 * (proxy["world_aabb_min"][1] + proxy["world_aabb_max"][1]),
        )
        center_outside = not point_in_convex(center, floor_hull)
        floor_min_x, floor_max_x, floor_min_y, floor_max_y = floor_bounds
        violation = max(
            0.0,
            floor_min_x - proxy["world_aabb_min"][0],
            proxy["world_aabb_max"][0] - floor_max_x,
            floor_min_y - proxy["world_aabb_min"][1],
            proxy["world_aabb_max"][1] - floor_max_y,
        )
        is_oob = center_outside or outside_ratio > OOB_RATIO
        if is_oob:
            oob_ids.add(record["instance_id"])
        if violation > COLLISION_DEPTH_M:
            collision_ids.add(record["instance_id"])
            pair_records.append(
                {
                    "a": record["instance_id"],
                    "b": "room_boundary",
                    "penetration_depth_proxy_m": violation,
                    "significant": True,
                }
            )
        if floor_z - proxy["world_aabb_min"][2] > COLLISION_DEPTH_M:
            collision_ids.add(record["instance_id"])
            pair_records.append(
                {
                    "a": record["instance_id"],
                    "b": "room_floor",
                    "penetration_depth_proxy_m": floor_z - proxy["world_aabb_min"][2],
                    "significant": True,
                }
            )
        oob_records.append(
            {
                "instance_id": record["instance_id"],
                "footprint_area_m2": area,
                "inside_area_m2": inside_area,
                "outside_area_ratio": outside_ratio,
                "center_outside": center_outside,
                "boundary_violation_m": violation,
                "oob": is_oob,
            }
        )

    support_records = []
    floating_ids: set[str] = set()
    valid_support = 0
    for record in support_eligible:
        proxy = proxies[record["instance_id"]]
        relations = [
            (relation, SUPPORT_RELATIONS.get(relation["relation"]))
            for relation in record["native_relations"]
            if SUPPORT_RELATIONS.get(relation["relation"])
        ]
        chosen = next((item for item in relations if item[1] == "gravity_parent"), None)
        chosen = chosen or next(
            (item for item in relations if item[1] == "gravity_floor"), None
        )
        # An ``against_wall`` relation is a placement constraint, not gravity
        # support for ordinary furniture such as wardrobes or cabinets.
        # Registered wall/ceiling attachment can explain fixtures only.
        if record["role"] == "fixture":
            chosen = chosen or next(
                (item for item in relations if item[1] == "wall_attachment"), None
            )
            chosen = chosen or next(
                (item for item in relations if item[1] == "ceiling_attachment"), None
            )
        source = "native"
        if chosen is None and record["role"] == "placed_object":
            possible = []
            child_center = (
                0.5 * (proxy["world_aabb_min"][0] + proxy["world_aabb_max"][0]),
                0.5 * (proxy["world_aabb_min"][1] + proxy["world_aabb_max"][1]),
            )
            for parent in eligible:
                if parent["instance_id"] == record["instance_id"]:
                    continue
                parent_proxy = proxies[parent["instance_id"]]
                gap = proxy["world_aabb_min"][2] - parent_proxy["world_aabb_max"][2]
                if gap >= -COLLISION_DEPTH_M and point_in_convex(
                    child_center, parent_proxy["footprint_convex_hull_xy_m"]
                ):
                    possible.append((abs(gap), parent["instance_id"]))
            floor_gap = proxy["world_aabb_min"][2] - floor_z
            if floor_gap >= -COLLISION_DEPTH_M:
                possible.append((abs(floor_gap), "room_floor"))
            if possible:
                _, parent_id = min(possible)
                mount = (
                    "gravity_floor" if parent_id == "room_floor" else "gravity_parent"
                )
                chosen = ({"parent": parent_id, "relation": "inferred"}, mount)
                source = "inferred"

        valid = False
        gap = None
        overlap_ratio = None
        center_supported = None
        parent_id = None
        mount = None
        attachment_triangle_intersections = None
        reason = "missing_legal_support"
        if chosen is not None:
            relation, mount = chosen
            parent_id = relation["parent"]
            child_hull = proxy["footprint_convex_hull_xy_m"]
            child_area = polygon_area(child_hull)
            child_center = (
                0.5 * (proxy["world_aabb_min"][0] + proxy["world_aabb_max"][0]),
                0.5 * (proxy["world_aabb_min"][1] + proxy["world_aabb_max"][1]),
            )
            if mount == "gravity_floor":
                gap = proxy["world_aabb_min"][2] - floor_z
                supported = convex_intersection(child_hull, floor_hull)
                overlap_ratio = (
                    0.0 if child_area <= 1e-12 else polygon_area(supported) / child_area
                )
                center_supported = point_in_convex(child_center, floor_hull)
                valid = (
                    -COLLISION_DEPTH_M <= gap <= FLOATING_GAP_M
                    and overlap_ratio >= SUPPORT_OVERLAP_RATIO
                    and center_supported
                )
            elif mount == "gravity_parent" and parent_id in proxies:
                parent = proxies[parent_id]
                gap = proxy["world_aabb_min"][2] - parent["world_aabb_max"][2]
                intersection = convex_intersection(
                    child_hull, parent["footprint_convex_hull_xy_m"]
                )
                overlap_ratio = (
                    0.0
                    if child_area <= 1e-12
                    else polygon_area(intersection) / child_area
                )
                center_supported = point_in_convex(
                    child_center, parent["footprint_convex_hull_xy_m"]
                )
                valid = (
                    -COLLISION_DEPTH_M <= gap <= FLOATING_GAP_M
                    and overlap_ratio >= SUPPORT_OVERLAP_RATIO
                    and center_supported
                )
            elif mount == "wall_attachment":
                child_tree = BVHTree.FromPolygons(
                    [Vector(vertex) for vertex in proxy["vertices"]],
                    proxy["faces"],
                    all_triangles=True,
                    epsilon=0.0,
                )
                attachment_triangle_intersections = sum(
                    len(child_tree.overlap(wall_tree)) for _, wall_tree in wall_bvhs
                )
                distances = [
                    abs(proxy["world_aabb_min"][0] - floor_bounds[0]),
                    abs(floor_bounds[1] - proxy["world_aabb_max"][0]),
                    abs(proxy["world_aabb_min"][1] - floor_bounds[2]),
                    abs(floor_bounds[3] - proxy["world_aabb_max"][1]),
                ]
                # Registered fixtures are intentionally embedded in the wall;
                # actual wall/fixture triangle intersection is valid attachment,
                # while non-intersecting fixtures retain the 2 cm gap rule.
                gap = 0.0 if attachment_triangle_intersections else min(distances)
                valid = bool(attachment_triangle_intersections) or gap <= FLOATING_GAP_M
                overlap_ratio = 1.0 if valid else 0.0
                center_supported = valid
            elif mount == "ceiling_attachment":
                gap = ceiling_z - proxy["world_aabb_max"][2]
                valid = -COLLISION_DEPTH_M <= gap <= FLOATING_GAP_M
                overlap_ratio = 1.0 if valid else 0.0
                center_supported = valid
            reason = "ok" if valid else "geometric_support_check_failed"
        if valid:
            valid_support += 1
        if record["role"] == "placed_object":
            if chosen is None or mount not in {"gravity_floor", "gravity_parent"}:
                floating_ids.add(record["instance_id"])
            elif gap is None or gap > FLOATING_GAP_M:
                floating_ids.add(record["instance_id"])
        support_records.append(
            {
                "child": record["instance_id"],
                "parent": parent_id,
                "mount": mount,
                "source": source,
                "gap_m": gap,
                "support_overlap_ratio": overlap_ratio,
                "center_supported": center_supported,
                "attachment_triangle_intersections": attachment_triangle_intersections,
                "valid": valid,
                "reason": reason,
            }
        )

    required_coverage_ok, coverage_records = coverage(spec, instances)
    output_contract_passed = (
        not matching_errors and len(eligible) > 0 and required_coverage_ok
    )
    structural = {
        "method": "sceneweaver",
        "domain": "indoor",
        "spec_id": spec["spec_id"],
        "logical_seed": int(run_dir.name.split("_")[-1]),
        "success": True,
        "failure_policy": "none",
        "eligible_objects": len(eligible),
        "collision_objects": len(collision_ids),
        "collision_rate": 100.0 * len(collision_ids) / len(eligible)
        if eligible
        else 100.0,
        "support_required_objects": len(eligible),
        "floating_objects": len(floating_ids),
        "floating_rate": 100.0 * len(floating_ids) / len(eligible)
        if eligible
        else 100.0,
        "oob_objects": len(oob_ids),
        "oob_rate": 100.0 * len(oob_ids) / len(eligible) if eligible else 100.0,
        "required_support_edges": len(support_eligible),
        "valid_support_edges": valid_support,
        "support_validity": 100.0 * valid_support / len(support_eligible)
        if support_eligible
        else 0.0,
        "collision_object_ids": sorted(collision_ids),
        "floating_object_ids": sorted(floating_ids),
        "oob_object_ids": sorted(oob_ids),
        "pairs": pair_records,
        "oob": oob_records,
        "support_edges": support_records,
        "instance_coverage": coverage_records,
        "output_contract_passed": output_contract_passed,
        "failures": matching_errors,
        "implementation": {
            "collision": "uniform_decimated_final_mesh_BVH_plus_axis_penetration_proxy",
            "footprint": "convex_hull_of_uniform_decimated_final_mesh_projection",
            "support": "native_relation_geometrically_revalidated",
            "face_cap_per_instance": args.face_cap,
            "penetration_depth_m": COLLISION_DEPTH_M,
            "overlap_volume_m3": COLLISION_VOLUME_M3,
            "smaller_object_volume_fraction": COLLISION_SMALLER_VOLUME_FRACTION,
            "floating_gap_m": FLOATING_GAP_M,
            "oob_ratio": OOB_RATIO,
            "support_overlap_ratio": SUPPORT_OVERLAP_RATIO,
        },
    }

    canonical = run_dir / "scene/canonical"
    object_parts = [
        (
            proxies[record["instance_id"]]["vertices"],
            proxies[record["instance_id"]]["faces"],
        )
        for record in instances
        if record["role"] in {"placed_object", "fixture"}
    ]
    collision_parts = structure_parts + object_parts
    collision_ply = write_ply(canonical / "collision.ply", collision_parts)
    empty_ply = write_ply(canonical / "empty_reference.ply", structure_parts)
    final_vertices = []
    final_faces = []
    for part_vertices, part_faces in collision_parts:
        offset = len(final_vertices)
        final_vertices.extend(part_vertices)
        final_faces.extend(
            tuple(index + offset for index in face) for face in part_faces
        )
    empty_vertices = []
    empty_faces = []
    for part_vertices, part_faces in structure_parts:
        offset = len(empty_vertices)
        empty_vertices.extend(part_vertices)
        empty_faces.extend(
            tuple(index + offset for index in face) for face in part_faces
        )
    np.savez_compressed(
        canonical / "collision_geometry.npz",
        vertices=np.asarray(final_vertices, dtype=np.float32),
        faces=np.asarray(final_faces, dtype=np.int32),
    )
    np.savez_compressed(
        canonical / "empty_reference_geometry.npz",
        vertices=np.asarray(empty_vertices, dtype=np.float32),
        faces=np.asarray(empty_faces, dtype=np.int32),
    )
    collision_glb = export_glb_from_parts(canonical / "collision.glb", collision_parts)
    empty_glb = export_glb_from_parts(
        canonical / "empty_reference.glb", structure_parts
    )
    atomic_json(
        canonical / "instances.json",
        {
            "coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "room_polygon_xy_m": floor_hull,
            "floor_z_m": floor_z,
            "instances": instances,
            "matching_errors": matching_errors,
        },
    )
    atomic_json(
        canonical / "transform.json",
        {
            "source_coordinate_system": "right-handed-z-up",
            "canonical_coordinate_system": "right-handed-z-up",
            "unit": "meter",
            "matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "scale_source": "native SceneWeaver/Infinigen meter convention",
        },
    )
    atomic_json(
        canonical / "geometry_manifest.json",
        {
            "exporter_sha256": sha256(Path(__file__)),
            "source_blend": str(source_run / "scene/scene.blend"),
            "source_blend_sha256": sha256(source_run / "scene/scene.blend"),
            "source_layout": str(layout_path),
            "source_layout_sha256": sha256(layout_path),
            "collision_ply": collision_ply,
            "empty_reference_ply": empty_ply,
            "collision_glb": collision_glb,
            "empty_reference_glb": empty_glb,
            "structure": structure_meta,
        },
    )
    floor_triangles = [
        [
            [float(floor_vertices[index][0]), float(floor_vertices[index][1])]
            for index in face
        ]
        for face in floor_faces
    ]
    if not floor_triangles:
        floor_triangles = [
            [
                [floor_hull[0][0], floor_hull[0][1]],
                [floor_hull[1][0], floor_hull[1][1]],
                [floor_hull[2][0], floor_hull[2][1]],
            ],
            [
                [floor_hull[0][0], floor_hull[0][1]],
                [floor_hull[2][0], floor_hull[2][1]],
                [floor_hull[3][0], floor_hull[3][1]],
            ],
        ]
    structural_spawn = [
        sum(point[0] for point in floor_hull) / len(floor_hull),
        sum(point[1] for point in floor_hull) / len(floor_hull),
        floor_z,
    ]
    atomic_json(
        run_dir / "input/boundaries.json",
        {
            "roi_type": "native_target_room_floor",
            "room_polygon_xy_m": floor_hull,
            "floor_triangles_xy_m": floor_triangles,
            "floor_z_m": floor_z,
            "structural_spawn_candidate_m": structural_spawn,
            "spawn_policy": "native floor centroid fallback because SceneWeaver final layout has no stable door identity",
            "allowed_boundary_crossings": spec.get("allowed_boundary_crossings", []),
        },
    )
    atomic_json(run_dir / "metrics/structural.json", structural)
    (run_dir / "CANONICAL_SUCCESS").touch()
    print(
        "TABLE3_SCENEWEAVER_EXPORT "
        + json.dumps(
            {
                "spec_id": spec["spec_id"],
                "instances": len(instances),
                "eligible": len(eligible),
                "matching_errors": len(matching_errors),
                "collision_rate": structural["collision_rate"],
                "floating_rate": structural["floating_rate"],
                "oob_rate": structural["oob_rate"],
                "support_validity": structural["support_validity"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
