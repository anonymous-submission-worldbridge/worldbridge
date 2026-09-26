#!/usr/bin/env python3
"""Audit the complete SpatialGen Table-3 trace and ITT aggregation."""

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
import csv
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

from baselines.methods.spatialgen.geometry.adapters.spatialgen import locate_artifacts


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=BASELINES_ROOT / "data/table3/indoor/spatialgen",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=BASELINES_ROOT / "data/table2/indoor/spatialgen",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=(BASELINES_ROOT / "evaluation/geometry/results/spatialgen"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(BASELINES_ROOT / "evaluation/geometry/results/spatialgen/audit.json"),
    )
    args = parser.parse_args()

    protocol_path = (
        BASELINES_ROOT / "methods/spatialgen/protocol/geometry/spatialgen_protocol.json"
    )
    reconstructor = (
        BASELINES_ROOT
        / "methods/spatialgen/geometry/tools/reconstruct_spatialgen_surface.py"
    )
    evaluator = (
        BASELINES_ROOT
        / "methods/spatialgen/geometry/metrics/eval_spatialgen_navigability.py"
    )
    agent_path = BASELINES_ROOT / "protocol/geometry/agent.yaml"
    protocol = read_json(protocol_path)
    specs_path = REPO_ROOT / protocol["source_specs"]
    specs = [
        json.loads(line)
        for line in specs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected = [
        (spec["spec_id"], int(seed)) for spec in specs for seed in protocol["seeds"]
    ]
    expected_hashes = {
        "protocol_sha256": sha256(protocol_path),
        "reconstructor_sha256": sha256(reconstructor),
        "navigation_evaluator_sha256": sha256(evaluator),
        "agent_sha256": sha256(agent_path),
    }
    errors: list[str] = []
    rasterizer_binary = (
        REPO_ROOT
        / protocol["runtime"]["rasterizer_isolated_site"]
        / "diff_gaussian_rasterization/_C.cpython-310-x86_64-linux-gnu.so"
    )
    if not rasterizer_binary.is_file():
        errors.append(f"missing frozen rasterizer binary: {rasterizer_binary}")
    elif sha256(rasterizer_binary) != protocol["runtime"]["rasterizer_binary_sha256"]:
        errors.append("frozen rasterizer binary hash mismatch")
    rows = []
    geometry_runs: list[tuple[str, int, Path, dict[str, Any]]] = []
    source_valid = 0
    for spec_id, seed in expected:
        source_run = args.source_root / spec_id / f"seed_{seed}"
        run_dir = args.data_root / spec_id / f"seed_{seed}"
        try:
            locate_artifacts(source_run)
            source_valid += 1
        except Exception as error:
            errors.append(f"{spec_id}/seed_{seed}: invalid Table-2 source: {error}")
        required = [
            run_dir / "GENERATION_SUCCESS",
            run_dir / "EVALUATION_SUCCESS",
            run_dir / "run_manifest.json",
            run_dir / "scene/reconstruction.json",
            run_dir / "scene/canonical/collision_geometry.npz",
            run_dir / "scene/canonical/empty_reference_geometry.npz",
            run_dir / "metrics/navigability.json",
        ]
        missing = [
            str(path.relative_to(run_dir)) for path in required if not path.is_file()
        ]
        if missing:
            errors.append(f"{spec_id}/seed_{seed}: missing {missing}")
            continue
        manifest = read_json(run_dir / "run_manifest.json")
        metric = read_json(run_dir / "metrics/navigability.json")
        reconstruction = read_json(run_dir / "scene/reconstruction.json")
        for key, expected_hash in expected_hashes.items():
            if manifest.get(key) != expected_hash:
                errors.append(f"{spec_id}/seed_{seed}: stale {key}")
        if (
            manifest.get("spec_id") != spec_id
            or int(manifest.get("logical_seed", -1)) != seed
        ):
            errors.append(f"{spec_id}/seed_{seed}: manifest identity mismatch")
        canonical_files = {
            "collision_geometry_sha256": run_dir
            / "scene/canonical/collision_geometry.npz",
            "empty_reference_geometry_sha256": run_dir
            / "scene/canonical/empty_reference_geometry.npz",
            "surface_evidence_sha256": run_dir / "scene/canonical/surface_evidence.npz",
            "transform_sha256": run_dir / "scene/canonical/transform.json",
        }
        for key, path in canonical_files.items():
            if not path.is_file() or manifest.get("canonical_hashes", {}).get(
                key
            ) != sha256(path):
                errors.append(f"{spec_id}/seed_{seed}: canonical hash mismatch {key}")
        if manifest.get("metric_hashes", {}).get("navigability_sha256") != sha256(
            required[-1]
        ):
            errors.append(f"{spec_id}/seed_{seed}: navigability hash mismatch")
        for filename, key in (
            ("empty_reference.navmesh", "empty_reference_navmesh_sha256"),
            ("final.navmesh", "final_navmesh_sha256"),
        ):
            path = run_dir / "navigation" / filename
            recorded = manifest.get("metric_hashes", {}).get(key)
            if path.is_file() and recorded != sha256(path):
                errors.append(
                    f"{spec_id}/seed_{seed}: navigation hash mismatch {filename}"
                )
            if not path.is_file() and recorded is not None:
                errors.append(
                    f"{spec_id}/seed_{seed}: missing recorded navigation file {filename}"
                )
        calibration = reconstruction.get("calibration", {})
        if not (float(calibration.get("scale", 0.0)) > 0.0):
            errors.append(f"{spec_id}/seed_{seed}: invalid meter scale")
        if float(calibration.get("position_rmse_m", math.inf)) > float(
            protocol["surface_reconstruction"]["maximum_camera_position_rmse_m"]
        ):
            errors.append(
                f"{spec_id}/seed_{seed}: camera calibration exceeds tolerance"
            )
        scores = [
            float(metric.get("navigable_area_ratio", math.nan)),
            float(metric.get("connected_area_ratio", math.nan)),
            100.0 if metric.get("navmesh_success") is True else 0.0,
        ]
        if not all(math.isfinite(value) and 0.0 <= value <= 100.0 for value in scores):
            errors.append(f"{spec_id}/seed_{seed}: metric outside [0,100]")
        if not isinstance(metric.get("navmesh_success"), bool):
            errors.append(f"{spec_id}/seed_{seed}: navmesh_success is not bool")
        if not metric.get("navmesh_success") and any(
            abs(value) > 1e-9 for value in scores
        ):
            errors.append(
                f"{spec_id}/seed_{seed}: failed NavMesh did not receive three ITT zeros"
            )
        if metric.get("navmesh_success"):
            reference_area = float(metric.get("empty_reference_area_m2", math.nan))
            final_area = float(metric.get("final_navmesh_area_m2", math.nan))
            largest_area = float(metric.get("largest_component_area_m2", math.nan))
            expected_nav = 100.0 * min(1.0, final_area / reference_area)
            expected_connected = 100.0 * largest_area / final_area
            if not np.isclose(scores[0], expected_nav, atol=1e-10):
                errors.append(
                    f"{spec_id}/seed_{seed}: navigable area arithmetic mismatch"
                )
            if not np.isclose(scores[1], expected_connected, atol=1e-10):
                errors.append(
                    f"{spec_id}/seed_{seed}: connected area arithmetic mismatch"
                )
        rows.append({"spec_id": spec_id, "seed": seed, "scores": scores})
        geometry_runs.append((spec_id, seed, source_run, manifest))

    result_path = args.results_dir / "table3_full.json"
    csv_path = args.results_dir / "table3.csv"
    if not result_path.is_file() or not csv_path.is_file():
        errors.append("missing final aggregate outputs")
        aggregate_result = {}
        csv_row = {}
    else:
        aggregate_result = read_json(result_path)
        with csv_path.open(encoding="utf-8", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        csv_row = csv_rows[0] if len(csv_rows) == 1 else {}
        if len(csv_rows) != 1:
            errors.append("table3.csv must contain exactly one result row")

    independently_recomputed = {}
    if len(rows) == len(expected):
        for index, name in enumerate(
            ("navigable_area_ratio", "connected_area_ratio", "navmesh_success_rate")
        ):
            value = float(np.mean([row["scores"][index] for row in rows]))
            independently_recomputed[name] = value
            recorded = aggregate_result.get("metrics", {}).get(name, {}).get("mean")
            if recorded is None or not np.isclose(value, float(recorded), atol=1e-10):
                errors.append(
                    f"aggregate mismatch for {name}: recomputed={value}, recorded={recorded}"
                )
            if csv_row and csv_row.get(name) != f"{value:.1f}":
                errors.append(f"CSV rounding mismatch for {name}")
    else:
        errors.append(f"expected {len(expected)} metric rows, audited {len(rows)}")
    for name in (
        "collision_rate",
        "floating_rate",
        "oob_rate",
        "support_validity",
        "valid_scene_rate",
    ):
        if csv_row and csv_row.get(name) != "N/A-I":
            errors.append(f"{name} must be N/A-I")

    generator = np.random.default_rng(20260909)
    sample_count = min(5, len(geometry_runs))
    sampled_indices = (
        generator.choice(len(geometry_runs), size=sample_count, replace=False)
        if sample_count
        else []
    )
    spotchecks = []
    for index in sampled_indices:
        spec_id, seed, source_run, manifest = geometry_runs[int(index)]
        artifacts = locate_artifacts(source_run)
        source_hashes = {
            "gaussian_sha256": sha256(artifacts["gaussian"]),
            "compiled_cameras_sha256": sha256(artifacts["compiled_cameras"]),
            "normalized_cameras_sha256": sha256(artifacts["normalized_cameras"]),
            "table2_manifest_sha256": sha256(artifacts["manifest"]),
        }
        recorded_hashes = manifest.get("source_hashes", {})
        passed = all(
            recorded_hashes.get(key) == value for key, value in source_hashes.items()
        )
        if not passed:
            errors.append(f"{spec_id}/seed_{seed}: Table-2 source spot-check mismatch")
        spotchecks.append(
            {
                "spec_id": spec_id,
                "seed": seed,
                "source_run": str(source_run),
                "source_hashes": source_hashes,
                "passed": passed,
            }
        )

    audit = {
        "method": "spatialgen",
        "domain": "indoor",
        "track": "surface_only",
        "planned_runs": len(expected),
        "source_valid_runs": source_valid,
        "audited_terminal_runs": len(rows),
        "geometry_runs": len(geometry_runs),
        "independently_recomputed_means": independently_recomputed,
        "spotcheck_seed": 20260909,
        "spotchecks": spotchecks,
        "specs": str(specs_path),
        "specs_sha256": sha256(specs_path),
        "rasterizer_binary": str(rasterizer_binary),
        "rasterizer_binary_sha256": sha256(rasterizer_binary)
        if rasterizer_binary.is_file()
        else None,
        "implementation_hashes": expected_hashes,
        "errors": errors,
        "passed": not errors,
    }
    atomic_json(args.output, audit)
    print(
        json.dumps(
            {
                "passed": audit["passed"],
                "errors": len(errors),
                "output": str(args.output),
            }
        )
    )
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
