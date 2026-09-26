"""Shared Table-3 filesystem and provenance helpers."""

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


import hashlib
import json
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
TABLE2_ROOT = BASELINES / "data/table2/indoor/sceneweaver"
TABLE3_ROOT = BASELINES / "data/table3/indoor/sceneweaver"
SPEC_FILE = BASELINES / "protocol/geometry/indoor_specs.jsonl"


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


def load_specs(path: Path = SPEC_FILE) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def classify_table2_run(run_dir: Path) -> dict[str, Any]:
    success = (run_dir / "SUCCESS").is_file()
    render_failed = (run_dir / "RENDER_VALIDATION_FAILED").is_file()
    planner_failed = (run_dir / "PLANNER_BUDGET_EXHAUSTED").is_file()
    generation_success = (run_dir / "GENERATION_SUCCESS").is_file()
    scene = run_dir / "scene/scene.blend"
    layout = run_dir / "scene/layout.json"
    geometry_complete = generation_success and scene.is_file() and layout.is_file()
    unique_terminal = int(success) + int(render_failed) + int(planner_failed) == 1
    if geometry_complete and success:
        classification = "reusable_table2_success_geometry"
    elif geometry_complete and render_failed:
        classification = "reusable_generation_geometry_table2_render_failed"
    elif planner_failed:
        classification = "table2_generation_failure"
    elif not unique_terminal:
        classification = "nonunique_or_nonterminal"
    else:
        classification = "missing_final_geometry"
    return {
        "classification": classification,
        "reusable_raw": classification.startswith("reusable_"),
        "table2_success": success,
        "table2_render_failed": render_failed,
        "table2_planner_failed": planner_failed,
        "generation_success": generation_success,
        "geometry_complete": geometry_complete,
        "unique_terminal": unique_terminal,
        "scene": str(scene),
        "layout": str(layout),
    }


def itt_structural(spec_id: str, seed: int, reason: str) -> dict[str, Any]:
    return {
        "method": "sceneweaver",
        "domain": "indoor",
        "spec_id": spec_id,
        "logical_seed": seed,
        "success": False,
        "failure_policy": "itt_worst_case",
        "failure_reason": reason,
        "eligible_objects": 0,
        "collision_objects": 0,
        "collision_rate": 100.0,
        "support_required_objects": 0,
        "floating_objects": 0,
        "floating_rate": 100.0,
        "oob_objects": 0,
        "oob_rate": 100.0,
        "required_support_edges": 0,
        "valid_support_edges": 0,
        "support_validity": 0.0,
        "pairs": [],
        "support_edges": [],
        "oob": [],
        "instance_coverage": [],
        "output_contract_passed": False,
        "failures": [reason],
    }


def itt_navigation(spec_id: str, seed: int, reason: str) -> dict[str, Any]:
    return {
        "method": "sceneweaver",
        "domain": "indoor",
        "spec_id": spec_id,
        "logical_seed": seed,
        "success": False,
        "failure_policy": "itt_worst_case",
        "failure_reason": reason,
        "reference_navmesh_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "navigable_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "navmesh_success": False,
        "valid_scene": False,
        "component_count": 0,
        "component_areas_m2": [],
        "spawn_projections": [],
    }
