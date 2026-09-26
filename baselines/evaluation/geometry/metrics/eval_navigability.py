#!/usr/bin/env python3
"""Build the frozen Recast meshes and compute Table 3 navigation metrics."""

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
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import recast
from PIL import Image, ImageDraw

REPO_ROOT = _BASELINE_PROJECT_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.evaluation.geometry.metrics.geometry import triangle_area_3d


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def flatten(values):
    return [item for value in values for item in value]


def to_y_up(vertices):
    vertices = np.asarray(vertices, dtype=np.float32)
    return np.column_stack((vertices[:, 0], vertices[:, 2], -vertices[:, 1]))


def to_z_up(vertices):
    vertices = np.asarray(vertices, dtype=np.float32)
    return np.column_stack((vertices[:, 0], -vertices[:, 2], vertices[:, 1]))


def build_recast(geometry_path: Path, config: dict, floor_z: float):
    geometry = np.load(geometry_path)
    vertices = to_y_up(geometry["vertices"])
    faces = np.asarray(geometry["faces"], dtype=np.int32)
    double_faces = np.concatenate((faces, faces[:, [0, 2, 1]]), axis=0)
    agent = config["agent"]
    recast_config = config["recast"]
    builder = recast.RecastNavMesh()
    builder.build_from_vertices(
        flatten(vertices.tolist()),
        flatten(double_faces.tolist()),
        float(recast_config["cell_size_m"]),
        float(recast_config["cell_height_m"]),
        float(agent["height_m"]),
        float(agent["radius_m"]),
        float(agent["max_climb_m"]),
        float(agent["max_slope_deg"]),
    )
    vertices_flat, faces_flat = builder.get_polymesh()
    nav_vertices_y = np.asarray(vertices_flat, dtype=np.float64).reshape(-1, 3)
    nav_faces = np.asarray(faces_flat, dtype=np.int64).reshape(-1, 3)
    if len(nav_vertices_y) == 0 or len(nav_faces) == 0:
        raise RuntimeError("Recast returned an empty polymesh")
    # Recast legitimately considers table and cabinet tops walkable.  The main
    # indoor protocol retains only the target floor-height band, never the
    # largest component, so disconnected floor islands remain measurable.
    climb = float(agent["max_climb_m"])
    keep = []
    for face in nav_faces:
        mean_height = float(nav_vertices_y[face, 1].mean())
        if (
            floor_z - float(recast_config["cell_height_m"]) * 2
            <= mean_height
            <= floor_z + climb
        ):
            keep.append(face)
    if not keep:
        raise RuntimeError("No target-floor-height Recast polygons")
    nav_faces = np.asarray(keep, dtype=np.int64)
    used = sorted({int(index) for face in nav_faces for index in face})
    remap = {old: new for new, old in enumerate(used)}
    nav_faces = np.asarray(
        [[remap[int(index)] for index in face] for face in nav_faces], dtype=np.int64
    )
    nav_vertices = to_z_up(nav_vertices_y[used])
    return nav_vertices, nav_faces


def mesh_area(vertices, faces) -> float:
    return float(sum(triangle_area_3d(*vertices[face]) for face in faces))


def components(vertices, faces):
    edge_to_faces = defaultdict(list)
    for face_index, face in enumerate(faces):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_to_faces[tuple(sorted((int(a), int(b))))].append(face_index)
    graph = defaultdict(set)
    for members in edge_to_faces.values():
        for a in members:
            graph[a].update(value for value in members if value != a)
    unseen = set(range(len(faces)))
    answer = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        member_faces = []
        while queue:
            current = queue.popleft()
            member_faces.append(current)
            for neighbor in graph[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        area = mesh_area(vertices, faces[member_faces])
        answer.append(
            {
                "face_indices": sorted(member_faces),
                "face_count": len(member_faces),
                "area_m2": area,
            }
        )
    answer.sort(key=lambda value: (-value["area_m2"], value["face_indices"][0]))
    return answer


def closest_point_segment_2d(point, a, b):
    point = np.asarray(point, dtype=float)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    delta = b - a
    denominator = float(np.dot(delta, delta))
    t = (
        0.0
        if denominator <= 1e-12
        else min(1.0, max(0.0, float(np.dot(point - a, delta) / denominator)))
    )
    return a + t * delta


def point_in_triangle_2d(point, triangle):
    point = np.asarray(point, dtype=float)
    triangle = np.asarray(triangle, dtype=float)
    signs = []
    for index in range(3):
        a = triangle[index]
        b = triangle[(index + 1) % 3]
        signs.append(float(np.cross(b - a, point - a)))
    return all(value >= -1e-8 for value in signs) or all(
        value <= 1e-8 for value in signs
    )


def project_to_navmesh(point, vertices, faces):
    point = np.asarray(point, dtype=float)
    best = None
    for face_index, face in enumerate(faces):
        triangle = vertices[face]
        xy = triangle[:, :2]
        if point_in_triangle_2d(point[:2], xy):
            candidate_xy = point[:2]
        else:
            options = [
                closest_point_segment_2d(point[:2], xy[i], xy[(i + 1) % 3])
                for i in range(3)
            ]
            candidate_xy = min(
                options, key=lambda value: float(np.linalg.norm(value - point[:2]))
            )
        # The retained polygons are a near-horizontal target-floor band.
        candidate = np.asarray(
            [candidate_xy[0], candidate_xy[1], float(triangle[:, 2].mean())]
        )
        horizontal = float(np.linalg.norm(candidate[:2] - point[:2]))
        vertical = abs(float(candidate[2] - point[2]))
        key = (horizontal, vertical, face_index)
        if best is None or key < best[0]:
            best = (key, candidate, face_index)
    if best is None:
        return None
    return {
        "point_m": best[1].tolist(),
        "face_index": best[2],
        "horizontal_distance_m": best[0][0],
        "vertical_distance_m": best[0][1],
    }


def save_navmesh(path: Path, vertices, faces) -> None:
    with path.open("wb") as handle:
        np.savez_compressed(
            handle,
            vertices=np.asarray(vertices, dtype=np.float32),
            faces=np.asarray(faces, dtype=np.int32),
        )


def make_debug(
    run_dir: Path, ref_vertices, ref_faces, final_vertices, final_faces, component_rows
) -> None:
    boundary = read_json(run_dir / "input/boundaries.json")
    floor_points = np.asarray(
        [point for triangle in boundary["floor_triangles_xy_m"] for point in triangle],
        dtype=float,
    )
    lower = floor_points.min(axis=0)
    upper = floor_points.max(axis=0)
    span = np.maximum(upper - lower, 1e-6)
    size = 1024
    margin = 32

    def pixel(point):
        x = margin + (float(point[0]) - lower[0]) / span[0] * (size - 2 * margin)
        y = size - margin - (float(point[1]) - lower[1]) / span[1] * (size - 2 * margin)
        return (round(x), round(y))

    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    for face in ref_faces:
        draw.polygon(
            [pixel(ref_vertices[index]) for index in face], fill=(210, 220, 230, 100)
        )
    palette = [
        (37, 99, 235, 180),
        (239, 68, 68, 180),
        (16, 185, 129, 180),
        (168, 85, 255, 180),
    ]
    face_component = {}
    for component_index, row in enumerate(component_rows):
        for face_index in row["face_indices"]:
            face_component[face_index] = component_index
    for face_index, face in enumerate(final_faces):
        color = palette[face_component.get(face_index, 0) % len(palette)]
        draw.polygon([pixel(final_vertices[index]) for index in face], fill=color)
    spawn = (
        boundary.get("registered_spawn_m") or boundary["structural_spawn_candidate_m"]
    )
    px, py = pixel(spawn)
    draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill=(0, 0, 0, 255))
    image.save(run_dir / "navigation/debug_topdown.png")


def make_structural_debug(run_dir: Path) -> None:
    boundary = read_json(run_dir / "input/boundaries.json")
    structural = read_json(run_dir / "metrics/structural.json")
    instances = read_json(run_dir / "scene/canonical/instances.json")["instances"]
    floor_points = np.asarray(
        [point for triangle in boundary["floor_triangles_xy_m"] for point in triangle],
        dtype=float,
    )
    lower = floor_points.min(axis=0)
    upper = floor_points.max(axis=0)
    span = np.maximum(upper - lower, 1e-6)
    size = 1024
    margin = 32

    def pixel(point):
        x = margin + (float(point[0]) - lower[0]) / span[0] * (size - 2 * margin)
        y = size - margin - (float(point[1]) - lower[1]) / span[1] * (size - 2 * margin)
        return (round(x), round(y))

    collision = {
        value
        for pair in structural.get("pairs", [])
        if pair.get("significant")
        for value in (pair.get("a"), pair.get("b"))
    }
    floating = {
        edge["child"]
        for edge in structural.get("support_edges", [])
        if not edge.get("valid")
    }
    oob = {
        item["instance_id"]
        for item in structural.get("oob_details", [])
        if item.get("oob")
    }
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    for triangle in boundary["floor_triangles_xy_m"]:
        draw.polygon([pixel(point) for point in triangle], fill=(226, 232, 240, 210))
    for item in instances:
        if not item.get("include_collision"):
            continue
        corners = np.asarray(item["collision_proxy"]["corners"], dtype=float)
        # The 8 OBB corners project to a convex quadrilateral for rigid Z-up placements.
        from baselines.evaluation.geometry.metrics.geometry import convex_hull_2d

        footprint = convex_hull_2d(corners[:, :2])
        color = (34, 197, 94, 100)
        if item["instance_id"] in floating:
            color = (245, 158, 11, 170)
        if item["instance_id"] in collision:
            color = (239, 68, 68, 190)
        if item["instance_id"] in oob:
            color = (168, 85, 247, 190)
        draw.polygon(
            [pixel(point) for point in footprint], fill=color, outline=(15, 23, 42, 170)
        )
    image.save(run_dir / "metrics/debug_structural_topdown.png")


def evaluate_run(
    run_dir: Path, agent_path: Path, thresholds: dict | None = None
) -> dict:
    run_dir = Path(run_dir)
    config = read_json(agent_path)
    boundary = read_json(run_dir / "input/boundaries.json")
    navigation_dir = run_dir / "navigation"
    navigation_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "spec_id": read_json(run_dir / "input/spec.json")["spec_id"],
        "failures": [],
    }
    make_structural_debug(run_dir)
    try:
        ref_vertices, ref_faces = build_recast(
            run_dir / "scene/canonical/empty_reference_geometry.npz",
            config,
            float(boundary["floor_z_m"]),
        )
        final_vertices, final_faces = build_recast(
            run_dir / "scene/canonical/collision_geometry.npz",
            config,
            float(boundary["floor_z_m"]),
        )
        ref_area = mesh_area(ref_vertices, ref_faces)
        final_area = mesh_area(final_vertices, final_faces)
        component_rows = components(final_vertices, final_faces)
        largest = component_rows[0]["area_m2"] if component_rows else 0.0
        registered = project_to_navmesh(
            boundary["structural_spawn_candidate_m"], ref_vertices, ref_faces
        )
        final_spawn = (
            project_to_navmesh(registered["point_m"], final_vertices, final_faces)
            if registered
            else None
        )
        spawn_ok = bool(
            registered
            and final_spawn
            and final_spawn["horizontal_distance_m"]
            <= float(config["spawn"]["horizontal_tolerance_m"])
            and final_spawn["vertical_distance_m"]
            <= float(config["spawn"]["vertical_tolerance_m"])
        )
        nav_ratio = 100.0 * min(1.0, final_area / ref_area) if ref_area > 0 else 0.0
        connected_ratio = 100.0 * largest / final_area if final_area > 0 else 0.0
        success = bool(
            math.isfinite(ref_area)
            and math.isfinite(final_area)
            and ref_area > 0
            and final_area
            >= float(config["success"]["minimum_reference_area_fraction"]) * ref_area
            and spawn_ok
        )
        boundary["registered_spawn_m"] = registered["point_m"] if registered else None
        boundary["registered_spawn_projection"] = registered
        atomic_json(run_dir / "input/boundaries.json", boundary)
        save_navmesh(
            navigation_dir / "empty_reference.navmesh", ref_vertices, ref_faces
        )
        save_navmesh(navigation_dir / "final.navmesh", final_vertices, final_faces)
        atomic_json(
            navigation_dir / "components.json",
            {"component_count": len(component_rows), "components": component_rows},
        )
        make_debug(
            run_dir,
            ref_vertices,
            ref_faces,
            final_vertices,
            final_faces,
            component_rows,
        )
        result.update(
            {
                "empty_reference_area_m2": ref_area,
                "final_navmesh_area_m2": final_area,
                "navigable_area_ratio": nav_ratio,
                "largest_component_area_m2": largest,
                "connected_area_ratio": connected_ratio,
                "component_count": len(component_rows),
                "registered_spawn": registered,
                "final_spawn_projection": final_spawn,
                "spawn_check_passed": spawn_ok,
                "navmesh_success": success,
                "recast_config": config,
            }
        )
    except Exception as error:
        result.update(
            {
                "empty_reference_area_m2": 0.0,
                "final_navmesh_area_m2": 0.0,
                "navigable_area_ratio": 0.0,
                "largest_component_area_m2": 0.0,
                "connected_area_ratio": 0.0,
                "component_count": 0,
                "registered_spawn": None,
                "final_spawn_projection": None,
                "spawn_check_passed": False,
                "navmesh_success": False,
            }
        )
        result["failures"].append({"type": type(error).__name__, "message": str(error)})
    if thresholds is not None:
        structural = read_json(run_dir / "metrics/structural.json")
        result["valid"] = bool(
            structural["output_contract_passed"]
            and structural["collision_rate"] == 0.0
            and structural["floating_rate"] == 0.0
            and structural["oob_rate"] == 0.0
            and structural["support_validity"] == 100.0
            and result["navmesh_success"]
            and result["navigable_area_ratio"]
            >= float(thresholds["navigable_area_ratio"])
            and result["connected_area_ratio"]
            >= float(thresholds["connected_area_ratio"])
        )
        result["valid_scene_thresholds"] = thresholds
    atomic_json(run_dir / "metrics/navigability.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path)
    args = parser.parse_args()
    thresholds = read_json(args.thresholds) if args.thresholds else None
    result = evaluate_run(args.run_dir, args.agent, thresholds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["navmesh_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
