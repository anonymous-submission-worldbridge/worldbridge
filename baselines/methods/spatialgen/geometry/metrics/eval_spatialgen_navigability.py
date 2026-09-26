#!/usr/bin/env python3
"""Evaluate the three Table-3 surface-only navigation metrics for SpatialGen."""

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
from typing import Any

import numpy as np


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.evaluation.geometry.metrics.eval_navigability import build_recast
from baselines.evaluation.geometry.metrics.eval_navigability import components
from baselines.evaluation.geometry.metrics.eval_navigability import make_debug
from baselines.evaluation.geometry.metrics.eval_navigability import mesh_area
from baselines.evaluation.geometry.metrics.eval_navigability import project_to_navmesh
from baselines.evaluation.geometry.metrics.eval_navigability import save_navmesh


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def failure_result(run_dir: Path, reason: str) -> dict[str, Any]:
    spec_path = run_dir / "input/spec.json"
    spec_id = (
        read_json(spec_path)["spec_id"] if spec_path.is_file() else run_dir.parent.name
    )
    return {
        "method": "spatialgen",
        "domain": "indoor",
        "track": "surface_only",
        "spec_id": spec_id,
        "navigable_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "navmesh_success": False,
        "empty_reference_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "largest_component_area_m2": 0.0,
        "component_count": 0,
        "spawn_check_passed": False,
        "failures": [{"type": "surface_or_navigation_failure", "message": reason}],
        "failure_policy": "ITT zero",
    }


def evaluate(run_dir: Path, agent_path: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    try:
        config = read_json(agent_path)
        boundary = read_json(run_dir / "input/boundaries.json")
        floor_z = float(boundary["floor_z_m"])
        ref_vertices, ref_faces = build_recast(
            run_dir / "scene/canonical/empty_reference_geometry.npz", config, floor_z
        )
        final_vertices, final_faces = build_recast(
            run_dir / "scene/canonical/collision_geometry.npz", config, floor_z
        )
        reference_area = mesh_area(ref_vertices, ref_faces)
        final_area = mesh_area(final_vertices, final_faces)
        component_rows = components(final_vertices, final_faces)
        largest_area = component_rows[0]["area_m2"] if component_rows else 0.0
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
        raw_ratio = (
            100.0 * min(1.0, final_area / reference_area) if reference_area > 0 else 0.0
        )
        raw_connected = 100.0 * largest_area / final_area if final_area > 0 else 0.0
        success = bool(
            math.isfinite(reference_area)
            and math.isfinite(final_area)
            and reference_area > 0
            and final_area
            >= float(config["success"]["minimum_reference_area_fraction"])
            * reference_area
            and spawn_ok
        )
        # Section 15.1 of the frozen Table-3 plan requires every surface-only
        # NavMesh predicate failure to contribute 0/0/false to the ITT matrix.
        ratio = raw_ratio if success else 0.0
        connected = raw_connected if success else 0.0
        boundary["registered_spawn_m"] = registered["point_m"] if registered else None
        boundary["registered_spawn_projection"] = registered
        atomic_json(run_dir / "input/boundaries.json", boundary)
        navigation_dir = run_dir / "navigation"
        navigation_dir.mkdir(parents=True, exist_ok=True)
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
        result = {
            "method": "spatialgen",
            "domain": "indoor",
            "track": "surface_only",
            "spec_id": read_json(run_dir / "input/spec.json")["spec_id"],
            "navigable_area_ratio": ratio,
            "connected_area_ratio": connected,
            "navmesh_success": success,
            "empty_reference_area_m2": reference_area,
            "final_navmesh_area_m2": final_area,
            "largest_component_area_m2": largest_area,
            "component_count": len(component_rows),
            "diagnostic_navigable_area_ratio_before_itt": raw_ratio,
            "diagnostic_connected_area_ratio_before_itt": raw_connected,
            "registered_spawn": registered,
            "final_spawn_projection": final_spawn,
            "spawn_check_passed": spawn_ok,
            "failures": []
            if success
            else [
                {
                    "type": "navmesh_success_predicate_failed",
                    "message": "area or spawn check failed; all three surface-only navigation scores use ITT zero",
                }
            ],
            "recast_config": config,
        }
    except Exception as error:
        result = failure_result(run_dir, f"{type(error).__name__}: {error}")
    metrics_path = run_dir / "metrics/navigability.json"
    atomic_json(metrics_path, result)
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        manifest["evaluation_status"] = (
            "success" if result["navmesh_success"] else "itt_failure"
        )
        manifest["navigation_evaluator_sha256"] = sha256(Path(__file__))
        manifest["agent_sha256"] = sha256(agent_path)
        manifest["metric_hashes"] = {
            "navigability_sha256": sha256(metrics_path),
            "empty_reference_navmesh_sha256": sha256(
                run_dir / "navigation/empty_reference.navmesh"
            )
            if (run_dir / "navigation/empty_reference.navmesh").is_file()
            else None,
            "final_navmesh_sha256": sha256(run_dir / "navigation/final.navmesh")
            if (run_dir / "navigation/final.navmesh").is_file()
            else None,
        }
        atomic_json(manifest_path, manifest)
    (run_dir / "EVALUATION_SUCCESS").write_text(
        "measured\n" if result["navmesh_success"] else "ITT zero terminal\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--agent", type=Path, default=(BASELINES_ROOT / "protocol/geometry/agent.yaml")
    )
    args = parser.parse_args()
    result = evaluate(args.run_dir, args.agent)
    print(json.dumps(result, ensure_ascii=False))
    # A terminal ITT failure is a successfully recorded experiment outcome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
