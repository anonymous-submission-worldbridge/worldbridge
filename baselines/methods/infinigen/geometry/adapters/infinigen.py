#!/usr/bin/env python3
"""Run one Table 3 evaluation item by reusing the frozen Table 2 output."""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = _BASELINE_PROJECT_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines.evaluation.geometry.metrics.eval_navigability import evaluate_run
from baselines.methods.infinigen.tools.audit_infinigen_matrix import classify


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
TABLE2_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
TABLE3_ROOT = BASELINES / "data/table3"
SPECS = BASELINES / "protocol/geometry/indoor_specs.jsonl"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
EXPORTER = BASELINES / "methods/infinigen/geometry/tools/blender_export_infinigen.py"
ROLES = BASELINES / "protocol/geometry/object_roles.yaml"
SUPPORT = BASELINES / "protocol/geometry/support_rules.yaml"
COLLISION = BASELINES / "protocol/geometry/collision_exceptions.yaml"
AGENT = BASELINES / "protocol/geometry/agent.yaml"
THRESHOLDS = BASELINES / "protocol/geometry/reference_thresholds.json"
PROTOCOL = BASELINES / "protocol/geometry/protocol.yaml"
NAVIGATOR = BASELINES / "evaluation/geometry/metrics/eval_navigability.py"
GEOMETRY = BASELINES / "evaluation/geometry/metrics/geometry.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hashes() -> dict:
    paths = [
        Path(__file__),
        EXPORTER,
        NAVIGATOR,
        GEOMETRY,
        ROLES,
        SUPPORT,
        COLLISION,
        AGENT,
        THRESHOLDS,
        PROTOCOL,
    ]
    return {str(path.relative_to(BASELINES)): sha256(path) for path in paths}


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_spec(spec_id: str) -> dict:
    for line in SPECS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if value["spec_id"] == spec_id:
                return value
    raise KeyError(spec_id)


def complete(run_dir: Path, implementation_hashes: dict) -> bool:
    required = [
        run_dir / "EVALUATION_SUCCESS",
        run_dir / "metrics/structural.json",
        run_dir / "metrics/navigability.json",
        run_dir / "run_manifest.json",
    ]
    if not all(path.exists() for path in required):
        return False
    try:
        manifest = json.loads(
            (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.get("implementation_hashes") == implementation_hashes


def write_itt(
    run_dir: Path,
    spec: dict,
    seed: int,
    table2_status: str,
    implementation_hashes: dict,
) -> None:
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    structural = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "spec_id": spec["spec_id"],
        "seed": seed,
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
        "oob_details": [],
        "output_contract_passed": False,
        "failures": [{"type": "table2_non_success", "status": table2_status}],
        "failure_policy": "itt",
    }
    navigability = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "spec_id": spec["spec_id"],
        "seed": seed,
        "empty_reference_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "navigable_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "component_count": 0,
        "spawn_check_passed": False,
        "navmesh_success": False,
        "valid": False,
        "failures": [{"type": "table2_non_success", "status": table2_status}],
        "failure_policy": "itt",
    }
    atomic_json(run_dir / "metrics/structural.json", structural)
    atomic_json(run_dir / "metrics/navigability.json", navigability)
    atomic_json(
        run_dir / "run_manifest.json",
        {
            "method": "infinigen_indoors",
            "domain": "indoor",
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "source_table2_status": table2_status,
            "reuse_status": "table2_failure_itt",
            "generation_status": "failed_in_frozen_table2_matrix",
            "export_status": "not_attempted_by_protocol",
            "evaluation_status": "complete_itt",
            "failure_policy": "itt",
            "implementation_hashes": implementation_hashes,
            "completed_at_utc": utc_now(),
        },
    )
    (run_dir / "EVALUATION_SUCCESS").touch()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument("--gpu", type=int, default=2)
    parser.add_argument("--data-root", type=Path, default=TABLE3_ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    spec = load_spec(args.spec_id)
    source = TABLE2_ROOT / args.spec_id / f"seed_{args.seed}"
    run_dir = (
        args.data_root / "indoor/infinigen_indoors" / args.spec_id / f"seed_{args.seed}"
    )
    implementation_hashes = hashes()
    if not args.force and complete(run_dir, implementation_hashes):
        print(f"TABLE3_SKIP {args.spec_id} seed={args.seed}")
        return 0
    table2_status = classify(source)
    if table2_status != "formal_success":
        write_itt(run_dir, spec, args.seed, table2_status, implementation_hashes)
        print(
            f"TABLE3_ITT {args.spec_id} seed={args.seed} source_status={table2_status}"
        )
        return 0
    scene = source / "scene/scene.blend"
    if not scene.is_file():
        print(f"TABLE3_INFRA_FAILURE missing source scene {scene}")
        return 2

    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    command = [
        str(BLENDER),
        "-noaudio",
        "--background",
        str(scene),
        "--python",
        str(EXPORTER),
        "--",
        "--run-dir",
        str(run_dir),
        "--table2-run-dir",
        str(source),
        "--spec",
        str(run_dir / "input/spec.json"),
        "--object-roles",
        str(ROLES),
        "--support-rules",
        str(SUPPORT),
        "--collision-exceptions",
        str(COLLISION),
    ]
    started = utc_now()
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    log_path = run_dir / "logs/export.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=BASELINES.parent,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0 or not (run_dir / "metrics/structural.json").is_file():
        print(
            f"TABLE3_INFRA_FAILURE exporter exit={completed.returncode} log={log_path}"
        )
        return 3
    thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    navigation = evaluate_run(run_dir, AGENT, thresholds)
    manifest = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "spec_id": args.spec_id,
        "logical_seed": args.seed,
        "source_table2_status": table2_status,
        "source_table2_run": str(source),
        "reuse_status": "reused_raw",
        "generation_status": "reused_formal_success",
        "export_status": "success",
        "evaluation_status": "success",
        "navmesh_success": navigation["navmesh_success"],
        "hardware": {
            "hostname": platform.node(),
            "assigned_gpu": args.gpu,
            "gpu_used_by_geometry_evaluation": False,
        },
        "command": command,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "implementation_hashes": implementation_hashes,
    }
    atomic_json(run_dir / "run_manifest.json", manifest)
    (run_dir / "GENERATION_SUCCESS").touch()
    (run_dir / "EVALUATION_SUCCESS").touch()
    print(
        f"TABLE3_OK {args.spec_id} seed={args.seed} "
        f"nav={navigation['navigable_area_ratio']:.3f} connected={navigation['connected_area_ratio']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
