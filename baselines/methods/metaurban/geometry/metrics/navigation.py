#!/usr/bin/env python3
"""Build the frozen external Recast meshes and score MetaUrban navigation."""

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


import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


PACKAGE = _BASELINE_PROJECT_ROOT / "baselines/methods/metaurban/geometry"
if str((PACKAGE / "recast")) not in sys.path:
    sys.path.insert(0, str((PACKAGE / "recast")))
import recast  # noqa: E402

REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256


def flatten(values) -> list:
    return [item for row in values for item in row]


def to_y_up(vertices: np.ndarray) -> np.ndarray:
    return np.column_stack((vertices[:, 0], vertices[:, 2], -vertices[:, 1])).astype(
        np.float32
    )


def to_z_up(vertices: np.ndarray) -> np.ndarray:
    return np.column_stack((vertices[:, 0], -vertices[:, 2], vertices[:, 1])).astype(
        np.float64
    )


def build_recast(path: Path, config: dict, floor_z: float = 0.0):
    geometry = np.load(path)
    vertices = np.asarray(geometry["vertices"], dtype=np.float32)
    faces = np.asarray(geometry["faces"], dtype=np.int32)
    if not len(vertices) or not len(faces) or not np.isfinite(vertices).all():
        raise RuntimeError(f"invalid canonical geometry: {path}")
    vertices_y = to_y_up(vertices)
    agent = config["agent"]
    settings = config["recast"]
    builder = recast.RecastNavMesh()
    ok = builder.build_from_vertices(
        flatten(vertices_y.tolist()),
        flatten(faces.tolist()),
        float(settings["cell_size_m"]),
        float(settings["cell_height_m"]),
        float(agent["height_m"]),
        float(agent["radius_m"]),
        float(agent["max_climb_m"]),
        float(agent["max_slope_deg"]),
    )
    raw_vertices, raw_faces = builder.get_polymesh()
    nav_vertices_y = np.asarray(raw_vertices, dtype=np.float64).reshape(-1, 3)
    nav_faces = np.asarray(raw_faces, dtype=np.int64).reshape(-1, 3)
    nav_faces = nav_faces[
        np.all((nav_faces >= 0) & (nav_faces < len(nav_vertices_y)), axis=1)
    ]
    minimum = floor_z - 2.0 * float(settings["cell_height_m"])
    maximum = floor_z + float(agent["max_climb_m"])
    nav_faces = np.asarray(
        [
            face
            for face in nav_faces
            if minimum <= float(nav_vertices_y[face, 1].mean()) <= maximum
        ],
        dtype=np.int64,
    ).reshape(-1, 3)
    if not bool(ok) or not len(nav_faces):
        raise RuntimeError("Recast returned no target-height polygons")
    used = sorted({int(index) for face in nav_faces for index in face})
    remap = {old: new for new, old in enumerate(used)}
    nav_faces = np.asarray(
        [[remap[int(index)] for index in face] for face in nav_faces], dtype=np.int32
    )
    nav_vertices = to_z_up(nav_vertices_y[used])
    return (
        nav_vertices,
        nav_faces,
        {
            "builder_returned": bool(ok),
            "recast_version": str(builder.get_version()),
            "input_vertices": int(len(vertices)),
            "input_faces": int(len(faces)),
            "nav_vertices": int(len(nav_vertices)),
            "nav_faces": int(len(nav_faces)),
            "connect_components": False,
            "keep_largest_only": False,
        },
    )


def triangle_areas(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    triangles = vertices[faces]
    return 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )


def connected_components(vertices: np.ndarray, faces: np.ndarray) -> list[dict]:
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for left, right in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_faces[tuple(sorted((int(left), int(right))))].append(face_index)
    graph: dict[int, set[int]] = defaultdict(set)
    for members in edge_faces.values():
        for member in members:
            graph[member].update(other for other in members if other != member)
    areas = triangle_areas(vertices, faces)
    unseen = set(range(len(faces)))
    rows = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        members = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbour in graph[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
        rows.append(
            {
                "face_indices": sorted(members),
                "face_count": len(members),
                "area_m2": float(areas[members].sum()),
            }
        )
    rows.sort(key=lambda row: (-row["area_m2"], row["face_indices"][0]))
    return rows


def closest_on_segment(
    point: np.ndarray, left: np.ndarray, right: np.ndarray
) -> np.ndarray:
    delta = right - left
    denominator = float(np.dot(delta, delta))
    fraction = (
        0.0
        if denominator <= 1e-12
        else min(1.0, max(0.0, float(np.dot(point - left, delta) / denominator)))
    )
    return left + fraction * delta


def point_in_triangle(point: np.ndarray, triangle: np.ndarray) -> bool:
    signs = []
    for index in range(3):
        left, right = triangle[index], triangle[(index + 1) % 3]
        signs.append(float(np.cross(right - left, point - left)))
    return all(value >= -1e-8 for value in signs) or all(
        value <= 1e-8 for value in signs
    )


def project(point, vertices: np.ndarray, faces: np.ndarray):
    point = np.asarray(point, dtype=float)
    best = None
    for face_index, face in enumerate(faces):
        triangle = vertices[face]
        xy = triangle[:, :2]
        if point_in_triangle(point[:2], xy):
            candidate_xy = point[:2]
        else:
            candidates = [
                closest_on_segment(point[:2], xy[index], xy[(index + 1) % 3])
                for index in range(3)
            ]
            candidate_xy = min(
                candidates, key=lambda value: float(np.linalg.norm(value - point[:2]))
            )
        candidate = np.asarray(
            [candidate_xy[0], candidate_xy[1], float(triangle[:, 2].mean())]
        )
        key = (
            float(np.linalg.norm(candidate[:2] - point[:2])),
            abs(float(candidate[2] - point[2])),
            face_index,
        )
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


def save_navmesh(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        np.savez_compressed(
            handle, vertices=vertices.astype(np.float32), faces=faces.astype(np.int32)
        )


def debug_image(
    path: Path, boundary: dict, final_vertices, final_faces, component_rows
) -> None:
    lower = np.asarray(boundary["roi_xy_m"][0], dtype=float)
    upper = np.asarray(boundary["roi_xy_m"][2], dtype=float)
    span = upper - lower
    size, margin = 1024, 24

    def pixel(point):
        x = margin + (float(point[0]) - lower[0]) / span[0] * (size - 2 * margin)
        y = size - margin - (float(point[1]) - lower[1]) / span[1] * (size - 2 * margin)
        return round(x), round(y)

    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    for polygon in boundary["walkable_polygons_xy_m"]:
        draw.polygon([pixel(point) for point in polygon], fill=(220, 228, 238, 200))
    palette = [
        (37, 99, 235, 180),
        (16, 185, 129, 180),
        (239, 68, 68, 180),
        (168, 85, 247, 180),
    ]
    membership = {}
    for component_index, row in enumerate(component_rows):
        for face_index in row["face_indices"]:
            membership[face_index] = component_index
    for face_index, face in enumerate(final_faces):
        draw.polygon(
            [pixel(final_vertices[index]) for index in face],
            fill=palette[membership.get(face_index, 0) % len(palette)],
        )
    x, y = pixel(boundary["structural_spawn_candidate_m"])
    draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def evaluate(run_dir: Path, agent_path: Path, threshold_path: Path) -> dict:
    boundary = read_json(run_dir / "input/boundaries.json")
    structural = read_json(run_dir / "metrics/structural.json")
    spec = read_json(run_dir / "input/spec.json")
    config = read_json(agent_path)
    thresholds = read_json(threshold_path)
    reference_vertices, reference_faces, reference_build = build_recast(
        run_dir / "scene/canonical/empty_reference_geometry.npz", config
    )
    final_vertices, final_faces, final_build = build_recast(
        run_dir / "scene/canonical/collision_geometry.npz", config
    )
    reference_area = float(triangle_areas(reference_vertices, reference_faces).sum())
    final_area = float(triangle_areas(final_vertices, final_faces).sum())
    component_rows = connected_components(final_vertices, final_faces)
    largest = component_rows[0]["area_m2"] if component_rows else 0.0
    nav_ratio = (
        100.0 * min(1.0, max(0.0, final_area / reference_area))
        if reference_area > 0
        else 0.0
    )
    connected_ratio = 100.0 * largest / final_area if final_area > 0 else 0.0
    registered = project(
        boundary["structural_spawn_candidate_m"], reference_vertices, reference_faces
    )
    final_spawn = (
        project(registered["point_m"], final_vertices, final_faces)
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
    navmesh_success = bool(
        math.isfinite(reference_area)
        and math.isfinite(final_area)
        and reference_area > 0.0
        and final_area
        >= float(config["success"]["minimum_reference_area_fraction"]) * reference_area
        and spawn_ok
    )
    valid = bool(
        structural["output_contract_passed"]
        and structural["collision_rate"] == 0.0
        and structural["floating_rate"] == 0.0
        and structural["oob_rate"] == 0.0
        and structural["support_validity"] == 100.0
        and navmesh_success
        and nav_ratio >= float(thresholds["navigable_area_ratio"])
        and connected_ratio >= float(thresholds["connected_area_ratio"])
    )
    navigation = run_dir / "navigation"
    save_navmesh(
        navigation / "empty_reference.navmesh", reference_vertices, reference_faces
    )
    save_navmesh(navigation / "final.navmesh", final_vertices, final_faces)
    atomic_json(
        navigation / "components.json",
        {"component_count": len(component_rows), "components": component_rows},
    )
    debug_image(
        navigation / "debug_topdown.png",
        boundary,
        final_vertices,
        final_faces,
        component_rows,
    )
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "spec_id": spec["spec_id"],
        "logical_seed": int(run_dir.name.split("_")[-1]),
        "success": True,
        "empty_reference_area_m2": reference_area,
        "final_navmesh_area_m2": final_area,
        "navigable_area_ratio": nav_ratio,
        "largest_component_area_m2": largest,
        "connected_area_ratio": connected_ratio,
        "component_count": len(component_rows),
        "registered_spawn": registered,
        "final_spawn_projection": final_spawn,
        "spawn_check_passed": spawn_ok,
        "navmesh_success": navmesh_success,
        "valid_scene": valid,
        "valid": valid,
        "valid_scene_thresholds": thresholds,
        "reference_build": reference_build,
        "final_build": final_build,
        "agent_config": config,
        "failures": [],
        "provenance": {
            "evaluator_sha256": sha256(Path(__file__)),
            "agent_sha256": sha256(agent_path),
            "thresholds_sha256": sha256(threshold_path),
            "canonical_manifest_sha256": sha256(
                run_dir / "scene/canonical/geometry_manifest.json"
            ),
        },
    }
    atomic_json(run_dir / "metrics/navigability.json", payload)
    return payload
