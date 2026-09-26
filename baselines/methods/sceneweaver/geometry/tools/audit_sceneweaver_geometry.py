#!/usr/bin/env python3
"""Verify SceneWeaver Table-3 terminal coverage and cell provenance."""

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
import sys
from collections import Counter
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))
from baselines.evaluation.geometry.common import BASELINES
from baselines.evaluation.geometry.common import SPEC_FILE
from baselines.evaluation.geometry.common import TABLE3_ROOT
from baselines.evaluation.geometry.common import atomic_json
from baselines.evaluation.geometry.common import load_specs
from baselines.evaluation.geometry.common import sha256  # noqa: E402


EXPORTER = (
    BASELINES / "methods/sceneweaver/geometry/tools/export_sceneweaver_canonical.py"
)
NAV_EVALUATOR = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"
AGENT = BASELINES / "protocol/geometry/agent.yaml"
THRESHOLDS = BASELINES / "protocol/geometry/reference_thresholds.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=TABLE3_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES / "table3/results/sceneweaver_audit.json",
    )
    args = parser.parse_args()
    records = []
    status_counts: Counter[str] = Counter()
    for spec in load_specs(args.spec_file):
        for seed in range(4):
            run_dir = args.data_root / spec["spec_id"] / f"seed_{seed}"
            errors = []
            manifest_path = run_dir / "run_manifest.json"
            structural_path = run_dir / "metrics/structural.json"
            navigation_path = run_dir / "metrics/navigability.json"
            if not manifest_path.is_file():
                errors.append("missing_run_manifest")
                manifest = {}
            else:
                manifest = json.loads(manifest_path.read_text())
            for path, name in (
                (structural_path, "structural"),
                (navigation_path, "navigability"),
            ):
                if not path.is_file():
                    errors.append(f"missing_{name}")
                    continue
                payload = json.loads(path.read_text())
                for key, value in (
                    ("method", "sceneweaver"),
                    ("domain", "indoor"),
                    ("spec_id", spec["spec_id"]),
                    ("logical_seed", seed),
                ):
                    if payload.get(key) != value:
                        errors.append(f"{name}_{key}_mismatch")
            status = str(manifest.get("status", "missing"))
            status_counts[status] += 1
            if status == "complete":
                required = (
                    run_dir / "CANONICAL_SUCCESS",
                    run_dir / "EVALUATION_SUCCESS",
                    run_dir / "scene/canonical/collision.glb",
                    run_dir / "scene/canonical/collision.ply",
                    run_dir / "scene/canonical/instances.json",
                    run_dir / "scene/canonical/geometry_manifest.json",
                    run_dir / "navigation/final.navmesh",
                    run_dir / "navigation/final.navmesh.ply",
                    run_dir / "navigation/debug_topdown.png",
                )
                for path in required:
                    if not path.is_file():
                        errors.append(f"missing_complete_artifact:{path.name}")
                geometry_path = run_dir / "scene/canonical/geometry_manifest.json"
                if geometry_path.is_file() and navigation_path.is_file():
                    geometry = json.loads(geometry_path.read_text())
                    navigation = json.loads(navigation_path.read_text())
                    provenance = navigation.get("provenance", {})
                    expected_thresholds = json.loads(THRESHOLDS.read_text())
                    if geometry.get("exporter_sha256") != sha256(EXPORTER):
                        errors.append("stale_exporter_hash")
                    if provenance.get("evaluator_sha256") != sha256(NAV_EVALUATOR):
                        errors.append("stale_nav_evaluator_hash")
                    if provenance.get("agent_sha256") != sha256(AGENT):
                        errors.append("stale_agent_hash")
                    if provenance.get("canonical_manifest_sha256") != sha256(
                        geometry_path
                    ):
                        errors.append("canonical_manifest_hash_mismatch")
                    if navigation.get("valid_thresholds") != {
                        "navigable_area_ratio": float(
                            expected_thresholds["navigable_area_ratio"]
                        ),
                        "connected_area_ratio": float(
                            expected_thresholds["connected_area_ratio"]
                        ),
                    }:
                        errors.append("valid_threshold_mismatch")
            elif status != "complete_itt_failure":
                errors.append(f"nonterminal_status:{status}")
            records.append(
                {
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "status": status,
                    "valid": not errors,
                    "errors": errors,
                    "run_dir": str(run_dir),
                    "structural_sha256": sha256(structural_path)
                    if structural_path.is_file()
                    else None,
                    "navigability_sha256": sha256(navigation_path)
                    if navigation_path.is_file()
                    else None,
                }
            )
    result_csv = BASELINES / "table3/results/sceneweaver_table3.csv"
    result_json = BASELINES / "table3/results/sceneweaver_table3_full.json"
    payload = {
        "method": "sceneweaver",
        "domain": "indoor",
        "expected": 100,
        "valid": sum(record["valid"] for record in records),
        "status_counts": dict(sorted(status_counts.items())),
        "result_csv_sha256": sha256(result_csv) if result_csv.is_file() else None,
        "result_json_sha256": sha256(result_json) if result_json.is_file() else None,
        "records": records,
    }
    atomic_json(args.output, payload)
    print(
        f"TABLE3_SCENEWEAVER_AUDIT expected=100 valid={payload['valid']} statuses={payload['status_counts']}"
    )
    for record in records:
        for error in record["errors"]:
            print(
                f"AUDIT_ERROR {record['spec_id']} seed={record['logical_seed']} {error}"
            )
    return 0 if payload["valid"] == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
