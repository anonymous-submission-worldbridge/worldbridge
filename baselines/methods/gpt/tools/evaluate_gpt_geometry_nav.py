#!/usr/bin/env python3
"""Build and score the frozen GPT-6 Astra Table-3 Recast meshes."""

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
import sys
from pathlib import Path

import numpy as np


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
VENDOR = BASELINES / "tools/recast_py311"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))
REPO = BASELINES.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.evaluation.geometry.metrics.build_navmesh import build
from baselines.evaluation.geometry.metrics.build_navmesh import connected_components
from baselines.evaluation.geometry.metrics.build_navmesh import spawn_projection
from baselines.evaluation.geometry.metrics.build_navmesh import triangle_areas
from baselines.evaluation.geometry.metrics.build_navmesh import write_debug_png
from baselines.evaluation.geometry.metrics.build_navmesh import write_ply


RULES = BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json"
AGENT = BASELINES / "protocol/geometry/agent.yaml"


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


def point_in_triangle(point: np.ndarray, triangle: np.ndarray) -> bool:
    signs = []
    for index in range(3):
        left = triangle[index]
        right = triangle[(index + 1) % 3]
        signs.append(
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
    return all(value >= -1e-7 for value in signs) or all(
        value <= 1e-7 for value in signs
    )


def compact(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    used = sorted(set(int(index) for index in faces.reshape(-1))) if len(faces) else []
    remap = {old: new for new, old in enumerate(used)}
    new_vertices = vertices[used] if used else np.empty((0, 3), dtype=np.float32)
    new_faces = np.asarray(
        [[remap[int(index)] for index in face] for face in faces], dtype=np.int32
    ).reshape(-1, 3)
    return new_vertices, new_faces


def mask_to_reference(
    final_vertices: np.ndarray,
    final_faces: np.ndarray,
    reference_vertices: np.ndarray,
    reference_faces: np.ndarray,
    bin_size: float,
    vertical_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, dict]:
    bins: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(reference_faces):
        triangle = reference_vertices[face]
        lower = np.floor(triangle[:, :2].min(axis=0) / bin_size).astype(int)
        upper = np.floor(triangle[:, :2].max(axis=0) / bin_size).astype(int)
        for ix in range(lower[0], upper[0] + 1):
            for iy in range(lower[1], upper[1] + 1):
                bins.setdefault((ix, iy), []).append(face_index)
    kept = []
    for face in final_faces:
        triangle = final_vertices[face]
        centroid = triangle.mean(axis=0)
        key = tuple(np.floor(centroid[:2] / bin_size).astype(int))
        for reference_index in bins.get(key, []):
            reference = reference_vertices[reference_faces[reference_index]]
            if (
                point_in_triangle(centroid[:2], reference[:, :2])
                and abs(float(centroid[2] - reference[:, 2].mean()))
                <= vertical_tolerance
            ):
                kept.append(face)
                break
    kept_faces = np.asarray(kept, dtype=np.int32).reshape(-1, 3)
    masked_vertices, masked_faces = compact(final_vertices, kept_faces)
    return (
        masked_vertices,
        masked_faces,
        {
            "input_faces": int(len(final_faces)),
            "retained_faces": int(len(masked_faces)),
            "reference_bins": len(bins),
            "bin_size_m": bin_size,
            "vertical_tolerance_m": vertical_tolerance,
        },
    )


def reference_spawn(
    vertices: np.ndarray, faces: np.ndarray, roi: list[float]
) -> tuple[tuple[float, float, float], dict]:
    components, areas = connected_components(vertices, faces)
    if not components:
        raise RuntimeError("Reference NavMesh has no connected component")
    center = np.asarray([0.5 * (roi[0] + roi[1]), 0.5 * (roi[2] + roi[3])], dtype=float)
    face_index = min(
        components[0],
        key=lambda index: (
            float(np.linalg.norm(vertices[faces[index], :2].mean(axis=0) - center)),
            index,
        ),
    )
    triangle = vertices[faces[face_index]]
    centroid = triangle.mean(axis=0)
    return tuple(float(value) for value in centroid), {
        "policy": "triangle centroid nearest ROI center in largest empty-reference component",
        "reference_component_area_m2": float(areas[0]),
        "reference_component_count": len(components),
        "reference_face_index": int(face_index),
    }


def evaluate_run(
    run_dir: Path, agent_path: Path = AGENT, rules_path: Path = RULES
) -> dict:
    run_dir = run_dir.resolve()
    if not run_dir.is_relative_to(BASELINES):
        raise ValueError("Run directory escapes baselines")
    spec = json.loads((run_dir / "input/spec.json").read_text(encoding="utf-8"))
    geometry = json.loads(
        (run_dir / "scene/canonical/geometry_manifest.json").read_text(encoding="utf-8")
    )
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    floor_z = float(geometry["floor_z_m"])
    agent_config = json.loads(agent_path.read_text(encoding="utf-8"))
    reference_vertices, reference_faces, reference_build = build(
        run_dir / "scene/canonical/empty_reference.ply", agent_config, floor_z
    )
    final_vertices, final_faces, final_build = build(
        run_dir / "scene/canonical/collision.ply", agent_config, floor_z
    )
    final_vertices, final_faces, mask_meta = mask_to_reference(
        final_vertices,
        final_faces,
        reference_vertices,
        reference_faces,
        float(rules["reference_mask_bin_m"]),
        float(rules["reference_mask_vertical_tolerance_m"]),
    )
    reference_area = float(triangle_areas(reference_vertices, reference_faces).sum())
    final_area = float(triangle_areas(final_vertices, final_faces).sum())
    components, component_areas = connected_components(final_vertices, final_faces)
    navigable_ratio = (
        100.0 * min(1.0, max(0.0, final_area / reference_area))
        if reference_area > 0
        else 0.0
    )
    connected_ratio = (
        100.0 * component_areas[0] / final_area
        if final_area > 0 and component_areas
        else 0.0
    )
    roi = [float(value) for value in geometry["roi_xy_m"]]
    spawn, spawn_policy = reference_spawn(reference_vertices, reference_faces, roi)
    registered = spawn_projection(spawn, reference_vertices, reference_faces)
    final_projection = spawn_projection(
        tuple(registered["point_m"]), final_vertices, final_faces
    )
    navmesh_success = bool(
        reference_area > 0.0
        and final_area >= 0.01 * reference_area
        and np.isfinite(final_area)
        and final_projection.get("projected")
    )

    navigation = run_dir / "navigation"
    navigation.mkdir(parents=True, exist_ok=True)
    write_ply(
        navigation / "empty_reference.navmesh.ply", reference_vertices, reference_faces
    )
    write_ply(navigation / "final.navmesh.ply", final_vertices, final_faces)
    write_ply(
        navigation / "empty_reference.navmesh", reference_vertices, reference_faces
    )
    write_ply(navigation / "final.navmesh", final_vertices, final_faces)
    atomic_json(
        navigation / "components.json",
        {
            "component_count": len(components),
            "component_areas_m2": component_areas,
            "total_area_m2": final_area,
            "spawn_policy": spawn_policy,
            "registered_spawn": registered,
            "final_spawn_projection": final_projection,
        },
    )
    translated = final_vertices.copy()
    translated[:, 0] -= roi[0]
    translated[:, 1] -= roi[2]
    translated_spawn = (spawn[0] - roi[0], spawn[1] - roi[2], spawn[2])
    write_debug_png(
        navigation / "debug_topdown.png",
        translated,
        final_faces,
        components,
        (roi[1] - roi[0], roi[3] - roi[2]),
        [translated_spawn],
    )
    payload = {
        "method": "gpt6_astra",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": int(run_dir.name.split("_")[-1]),
        "success": True,
        "failure_policy": "none",
        "reference_navmesh_area_m2": reference_area,
        "final_navmesh_area_m2": final_area,
        "navigable_area_ratio": navigable_ratio,
        "connected_area_ratio": connected_ratio,
        "navmesh_success": navmesh_success,
        "valid_scene": None,
        "valid_scene_reason_code": "N/A-I",
        "component_count": len(components),
        "component_areas_m2": component_areas,
        "registered_spawn": registered,
        "final_spawn_projection": final_projection,
        "spawn_policy": spawn_policy,
        "reference_build": reference_build,
        "final_build": final_build,
        "reference_mask": mask_meta,
        "provenance": {
            "evaluator_sha256": sha256(Path(__file__)),
            "agent_sha256": sha256(agent_path),
            "rules_sha256": sha256(rules_path),
            "canonical_manifest_sha256": sha256(
                run_dir / "scene/canonical/geometry_manifest.json"
            ),
            "spec_sha256": sha256(run_dir / "input/spec.json"),
        },
    }
    atomic_json(run_dir / "metrics/navigability.json", payload)
    (run_dir / "EVALUATION_SUCCESS").touch()
    print(
        "GPT6_ASTRA_TABLE3_NAV "
        + json.dumps(
            {
                "domain": payload["domain"],
                "spec_id": payload["spec_id"],
                "seed": payload["logical_seed"],
                "navigable_area_ratio": navigable_ratio,
                "connected_area_ratio": connected_ratio,
                "navmesh_success": navmesh_success,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--agent", type=Path, default=AGENT)
    parser.add_argument("--rules", type=Path, default=RULES)
    args = parser.parse_args()
    evaluate_run(args.run_dir, args.agent, args.rules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
