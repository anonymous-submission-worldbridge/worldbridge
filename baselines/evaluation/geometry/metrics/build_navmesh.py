#!/usr/bin/env python3
"""Build and score the frozen Recast NavMeshes for one canonical run."""

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
import zlib
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
import yaml


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def flatten(values: np.ndarray) -> list[float] | list[int]:
    return values.reshape(-1).tolist()


def load_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    loaded = trimesh.load(path, force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.dump(concatenate=True)
    vertices = np.asarray(loaded.vertices, dtype=np.float32)
    faces = np.asarray(loaded.faces, dtype=np.int32)
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or faces.ndim != 2
        or faces.shape[1] != 3
    ):
        raise RuntimeError(f"Invalid triangle mesh: {path}")
    if not np.isfinite(vertices).all() or len(vertices) == 0 or len(faces) == 0:
        raise RuntimeError(f"Empty or non-finite triangle mesh: {path}")
    return vertices, faces


def zup_to_yup(vertices: np.ndarray) -> np.ndarray:
    return np.column_stack((vertices[:, 0], vertices[:, 2], -vertices[:, 1])).astype(
        np.float32
    )


def yup_to_zup(vertices: np.ndarray) -> np.ndarray:
    return np.column_stack((vertices[:, 0], -vertices[:, 2], vertices[:, 1])).astype(
        np.float32
    )


def triangle_areas(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    triangles = vertices[faces]
    return 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )


def connected_components(
    vertices: np.ndarray, faces: np.ndarray
) -> tuple[list[list[int]], list[float]]:
    if len(faces) == 0:
        return [], []
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_faces[tuple(sorted((int(a), int(b))))].append(face_index)
    neighbours: list[set[int]] = [set() for _ in range(len(faces))]
    for touching in edge_faces.values():
        for left in touching:
            neighbours[left].update(right for right in touching if right != left)
    unseen = set(range(len(faces)))
    components = []
    while unseen:
        root = unseen.pop()
        queue = deque([root])
        component = [root]
        while queue:
            current = queue.popleft()
            for neighbour in neighbours[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
                    component.append(neighbour)
        components.append(sorted(component))
    areas = triangle_areas(vertices, faces)
    component_areas = [float(areas[component].sum()) for component in components]
    order = sorted(
        range(len(components)), key=lambda index: component_areas[index], reverse=True
    )
    return [components[index] for index in order], [
        component_areas[index] for index in order
    ]


def build(
    mesh_path: Path, agent_config: dict[str, Any], floor_z: float
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    import recast

    vertices_zup, faces = load_mesh(mesh_path)
    vertices_yup = zup_to_yup(vertices_zup)
    double_faces = np.concatenate((faces, faces[:, [0, 2, 1]]), axis=0)
    agent = agent_config["agent"]
    config = agent_config["recast"]
    builder = recast.RecastNavMesh()
    ok = builder.build_from_vertices(
        flatten(vertices_yup),
        flatten(double_faces),
        float(config["cell_size_m"]),
        float(config["cell_height_m"]),
        float(agent["height_m"]),
        float(agent["radius_m"]),
        float(agent["max_climb_m"]),
        float(agent["max_slope_deg"]),
    )
    raw_vertices, raw_faces = builder.get_polymesh()
    nav_yup = np.asarray(list(raw_vertices), dtype=np.float32).reshape(-1, 3)
    nav_faces = np.asarray(list(raw_faces), dtype=np.int32).reshape(-1, 3)
    valid_index = np.all((nav_faces >= 0) & (nav_faces < len(nav_yup)), axis=1)
    nav_faces = nav_faces[valid_index]
    max_height = float(
        agent_config["postprocess"].get(
            "max_walkable_height_above_floor_m", agent["max_climb_m"]
        )
    )
    heights = nav_yup[nav_faces, 1].mean(axis=1) if len(nav_faces) else np.empty(0)
    height_mask = (heights >= floor_z - 0.10) & (heights <= floor_z + max_height)
    filtered_faces = nav_faces[height_mask]
    used = sorted(set(int(value) for value in filtered_faces.reshape(-1)))
    remap = {old: new for new, old in enumerate(used)}
    filtered_vertices_yup = (
        nav_yup[used] if used else np.empty((0, 3), dtype=np.float32)
    )
    filtered_faces = np.asarray(
        [[remap[int(value)] for value in face] for face in filtered_faces],
        dtype=np.int32,
    ).reshape(-1, 3)
    filtered_vertices_zup = yup_to_zup(filtered_vertices_yup)
    metadata = {
        "builder_returned": bool(ok),
        "recast_version": str(builder.get_version()),
        "input_vertices": int(len(vertices_zup)),
        "input_faces": int(len(faces)),
        "raw_nav_vertices": int(len(nav_yup)),
        "raw_nav_faces": int(len(nav_faces)),
        "height_filtered_nav_vertices": int(len(filtered_vertices_zup)),
        "height_filtered_nav_faces": int(len(filtered_faces)),
        "connect_components": False,
        "keep_largest_only": False,
    }
    return filtered_vertices_zup, filtered_faces, metadata


def write_ply(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
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
            handle.write(struct.pack("<fff", *[float(value) for value in vertex]))
        for face in faces:
            handle.write(struct.pack("<Biii", 3, *[int(value) for value in face]))


def point_segment_distance(
    point: tuple[float, float], left: np.ndarray, right: np.ndarray
) -> float:
    vector = right - left
    length_squared = float(np.dot(vector, vector))
    if length_squared <= 1e-15:
        return float(np.linalg.norm(np.asarray(point) - left))
    fraction = max(
        0.0,
        min(1.0, float(np.dot(np.asarray(point) - left, vector) / length_squared)),
    )
    return float(np.linalg.norm(np.asarray(point) - (left + fraction * vector)))


def point_triangle_horizontal_distance(
    point: tuple[float, float], triangle: np.ndarray
) -> float:
    xy = triangle[:, :2]
    signs = []
    for index in range(3):
        left = xy[index]
        right = xy[(index + 1) % 3]
        signs.append(
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
    if all(value >= -1e-8 for value in signs) or all(value <= 1e-8 for value in signs):
        return 0.0
    return min(
        point_segment_distance(point, xy[index], xy[(index + 1) % 3])
        for index in range(3)
    )


def spawn_projection(
    spawn: tuple[float, float, float], vertices: np.ndarray, faces: np.ndarray
) -> dict[str, Any]:
    if len(faces) == 0:
        return {"spawn": list(spawn), "projected": False, "horizontal_distance_m": None}
    best = None
    for face_index, face in enumerate(faces):
        triangle = vertices[face]
        horizontal = point_triangle_horizontal_distance((spawn[0], spawn[1]), triangle)
        vertical = abs(float(triangle[:, 2].mean()) - spawn[2])
        key = (horizontal, vertical, face_index)
        if best is None or key < best[0]:
            best = (key, face_index)
    assert best is not None
    horizontal, vertical, face_index = best[0]
    triangle = vertices[faces[face_index]]
    return {
        "spawn": list(spawn),
        "projected": horizontal <= 0.30 and vertical <= 0.50,
        "horizontal_distance_m": horizontal,
        "vertical_distance_m": vertical,
        "face_index": face_index,
        "point_m": [spawn[0], spawn[1], float(triangle[:, 2].mean())],
    }


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def draw_line(
    image: bytearray,
    size: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        if 0 <= x0 < size and 0 <= y0 < size:
            offset = (y0 * size + x0) * 3
            image[offset : offset + 3] = bytes(color)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def write_debug_png(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    components: list[list[int]],
    room_size: tuple[float, float],
    spawns: list[tuple[float, float, float]],
) -> None:
    size = 512
    image = bytearray([248] * size * size * 3)
    width, depth = room_size

    def pixel(point: tuple[float, float]) -> tuple[int, int]:
        x = int(round(10 + point[0] / max(width, 1e-6) * (size - 21)))
        y = int(round(size - 11 - point[1] / max(depth, 1e-6) * (size - 21)))
        return x, y

    colors = ((25, 130, 70), (40, 100, 180), (180, 120, 30), (140, 60, 160))
    for component_index, component in enumerate(components):
        color = colors[component_index % len(colors)]
        for face_index in component:
            face = faces[face_index]
            points = [pixel(tuple(vertices[index, :2])) for index in face]
            for left, right in zip(points, points[1:] + points[:1]):
                draw_line(image, size, left, right, color)
    draw_line(image, size, pixel((0, 0)), pixel((width, 0)), (0, 0, 0))
    draw_line(image, size, pixel((width, 0)), pixel((width, depth)), (0, 0, 0))
    draw_line(image, size, pixel((width, depth)), pixel((0, depth)), (0, 0, 0))
    draw_line(image, size, pixel((0, depth)), pixel((0, 0)), (0, 0, 0))
    for spawn in spawns:
        x, y = pixel((spawn[0], spawn[1]))
        for delta in range(-5, 6):
            draw_line(
                image, size, (x + delta, y - 5), (x + delta, y + 5), (220, 30, 30)
            )
    raw = b"".join(
        b"\x00" + bytes(image[row * size * 3 : (row + 1) * size * 3])
        for row in range(size)
    )
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(raw, 9))
    png += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def evaluate_run(
    run_dir: Path,
    agent_path: Path,
    navigable_threshold: float = 50.0,
    connected_threshold: float = 90.0,
) -> dict[str, Any]:
    canonical = run_dir / "scene/canonical"
    instances = json.loads((canonical / "instances.json").read_text())
    spec = json.loads((run_dir / "input/spec.json").read_text())
    structural = json.loads((run_dir / "metrics/structural.json").read_text())
    agent_config = yaml.safe_load(agent_path.read_text())
    floor_z = float(instances["floor_z_m"])
    room_polygon = instances["room_polygon_xy_m"]
    room_min_x = min(float(point[0]) for point in room_polygon)
    room_max_x = max(float(point[0]) for point in room_polygon)
    room_min_y = min(float(point[1]) for point in room_polygon)
    room_max_y = max(float(point[1]) for point in room_polygon)
    width = room_max_x - room_min_x
    depth = room_max_y - room_min_y

    reference_vertices, reference_faces, reference_meta = build(
        canonical / "empty_reference.ply", agent_config, floor_z
    )
    final_vertices, final_faces, final_meta = build(
        canonical / "collision.ply", agent_config, floor_z
    )
    reference_area = float(triangle_areas(reference_vertices, reference_faces).sum())
    final_area = float(triangle_areas(final_vertices, final_faces).sum())
    components, component_areas = connected_components(final_vertices, final_faces)
    navigable_ratio = (
        100.0 * min(1.0, max(0.0, final_area / reference_area))
        if reference_area > 0.0
        else 0.0
    )
    connected_ratio = (
        100.0 * component_areas[0] / final_area
        if final_area > 0.0 and component_areas
        else 0.0
    )
    boundary_path = run_dir / "input/boundaries.json"
    boundary = json.loads(boundary_path.read_text()) if boundary_path.is_file() else {}
    if spec.get("spawn_points"):
        first_spawn = spec["spawn_points"][0]
        spawn = (
            room_min_x + float(first_spawn["xy_fraction"][0]) * width,
            room_min_y + float(first_spawn["xy_fraction"][1]) * depth,
            floor_z,
        )
    else:
        candidate = boundary.get(
            "structural_spawn_candidate_m",
            [0.5 * (room_min_x + room_max_x), 0.5 * (room_min_y + room_max_y), floor_z],
        )
        spawn = tuple(float(value) for value in candidate)
    registered_spawn = spawn_projection(spawn, reference_vertices, reference_faces)
    final_spawn = (
        spawn_projection(
            tuple(registered_spawn["point_m"]), final_vertices, final_faces
        )
        if registered_spawn.get("projected")
        else {"spawn": list(spawn), "projected": False, "horizontal_distance_m": None}
    )
    spawn_records = [{"reference": registered_spawn, "final": final_spawn}]
    navmesh_success = bool(
        reference_area > 0.0
        and final_area >= 0.01 * reference_area
        and np.isfinite(final_area)
        and bool(final_spawn.get("projected"))
    )
    valid_scene = bool(
        structural["output_contract_passed"]
        and structural["collision_rate"] == 0.0
        and structural["floating_rate"] == 0.0
        and structural["oob_rate"] == 0.0
        and structural["support_validity"] == 100.0
        and navmesh_success
        and navigable_ratio >= navigable_threshold
        and connected_ratio >= connected_threshold
    )

    navigation = run_dir / "navigation"
    write_ply(
        navigation / "empty_reference.navmesh.ply", reference_vertices, reference_faces
    )
    write_ply(navigation / "final.navmesh.ply", final_vertices, final_faces)
    atomic_json(
        navigation / "empty_reference.navmesh",
        {
            "format": "recast_polymesh_ply_sidecar",
            "mesh": "empty_reference.navmesh.ply",
            "mesh_sha256": sha256(navigation / "empty_reference.navmesh.ply"),
            **reference_meta,
        },
    )
    atomic_json(
        navigation / "final.navmesh",
        {
            "format": "recast_polymesh_ply_sidecar",
            "mesh": "final.navmesh.ply",
            "mesh_sha256": sha256(navigation / "final.navmesh.ply"),
            **final_meta,
        },
    )
    atomic_json(
        navigation / "components.json",
        {
            "component_count": len(components),
            "component_areas_m2": component_areas,
            "total_area_m2": final_area,
            "largest_component_area_m2": component_areas[0] if component_areas else 0.0,
            "spawn_projections": spawn_records,
        },
    )
    write_debug_png(
        navigation / "debug_topdown.png",
        final_vertices,
        final_faces,
        components,
        (width, depth),
        [spawn],
    )
    payload = {
        "method": "sceneweaver",
        "domain": "indoor",
        "spec_id": spec["spec_id"],
        "logical_seed": int(run_dir.name.split("_")[-1]),
        "success": True,
        "failure_policy": "none",
        "reference_navmesh_area_m2": reference_area,
        "final_navmesh_area_m2": final_area,
        "navigable_area_ratio": navigable_ratio,
        "connected_area_ratio": connected_ratio,
        "navmesh_success": navmesh_success,
        "valid_scene": valid_scene,
        "valid": valid_scene,
        "component_count": len(components),
        "component_areas_m2": component_areas,
        "spawn_projections": spawn_records,
        "registered_spawn": registered_spawn,
        "final_spawn_projection": final_spawn,
        "valid_thresholds": {
            "navigable_area_ratio": navigable_threshold,
            "connected_area_ratio": connected_threshold,
        },
        "reference_build": reference_meta,
        "final_build": final_meta,
        "agent_config": agent_config,
        "provenance": {
            "evaluator_sha256": sha256(Path(__file__)),
            "agent_sha256": sha256(agent_path),
            "canonical_manifest_sha256": sha256(canonical / "geometry_manifest.json"),
            "spec_sha256": sha256(run_dir / "input/spec.json"),
        },
    }
    atomic_json(run_dir / "metrics/navigability.json", payload)
    (run_dir / "EVALUATION_SUCCESS").touch()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--agent",
        type=Path,
        default=(_BASELINE_PROJECT_ROOT / "baselines/protocol/geometry/agent.yaml"),
    )
    parser.add_argument("--navigable-threshold", type=float, default=50.0)
    parser.add_argument("--connected-threshold", type=float, default=90.0)
    args = parser.parse_args()
    payload = evaluate_run(
        args.run_dir.resolve(),
        args.agent.resolve(),
        args.navigable_threshold,
        args.connected_threshold,
    )
    print(
        "TABLE3_NAVIGATION "
        + json.dumps(
            {
                key: payload[key]
                for key in (
                    "spec_id",
                    "logical_seed",
                    "navigable_area_ratio",
                    "connected_area_ratio",
                    "navmesh_success",
                    "valid_scene",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
