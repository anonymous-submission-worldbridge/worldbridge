#!/usr/bin/env python3
"""Validate the frozen ten-run SpatialGen Table-3 pilot."""

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
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
    protocol_path = (
        BASELINES_ROOT / "methods/spatialgen/protocol/geometry/spatialgen_protocol.json"
    )
    agent_path = BASELINES_ROOT / "protocol/geometry/agent.yaml"
    reconstructor = (
        BASELINES_ROOT
        / "methods/spatialgen/geometry/tools/reconstruct_spatialgen_surface.py"
    )
    evaluator = (
        BASELINES_ROOT
        / "methods/spatialgen/geometry/metrics/eval_spatialgen_navigability.py"
    )
    root = BASELINES_ROOT / "data/table3_pilot/indoor/spatialgen"
    output = BASELINES_ROOT / "evaluation/geometry/results/spatialgen_pilot_audit.json"
    expected_hashes = {
        "protocol_sha256": sha256(protocol_path),
        "reconstructor_sha256": sha256(reconstructor),
        "navigation_evaluator_sha256": sha256(evaluator),
        "agent_sha256": sha256(agent_path),
    }
    specs = [
        json.loads(line)
        for line in ((BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"))
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    specs = [spec for spec in specs if spec["spec_id"].endswith("_00")]
    errors: list[str] = []
    rows = []
    for spec in specs:
        for seed in (0, 1):
            run = root / spec["spec_id"] / f"seed_{seed}"
            required = [
                run / "GENERATION_SUCCESS",
                run / "EVALUATION_SUCCESS",
                run / "run_manifest.json",
                run / "scene/reconstruction.json",
                run / "scene/canonical/collision_geometry.npz",
                run / "metrics/navigability.json",
            ]
            missing = [
                str(path.relative_to(run)) for path in required if not path.is_file()
            ]
            if missing:
                errors.append(f"{spec['spec_id']}/seed_{seed}: missing {missing}")
                continue
            manifest = read_json(required[2])
            reconstruction = read_json(required[3])
            metric = read_json(required[5])
            for key, expected_hash in expected_hashes.items():
                if manifest.get(key) != expected_hash:
                    errors.append(f"{spec['spec_id']}/seed_{seed}: stale {key}")
            rasterizer_hash = reconstruction.get("source_hashes", {}).get(
                "rasterizer_binary_sha256"
            )
            expected_rasterizer = read_json(protocol_path)["runtime"][
                "rasterizer_binary_sha256"
            ]
            if rasterizer_hash != expected_rasterizer:
                errors.append(
                    f"{spec['spec_id']}/seed_{seed}: rasterizer binary mismatch"
                )
            scale = float(reconstruction.get("calibration", {}).get("scale", 0.0))
            rmse = float(
                reconstruction.get("calibration", {}).get("position_rmse_m", math.inf)
            )
            values = [
                float(metric.get("navigable_area_ratio", math.nan)),
                float(metric.get("connected_area_ratio", math.nan)),
                100.0 if metric.get("navmesh_success") is True else 0.0,
            ]
            if not scale > 0 or rmse > 1e-4:
                errors.append(
                    f"{spec['spec_id']}/seed_{seed}: invalid similarity calibration"
                )
            if not all(math.isfinite(value) and 0 <= value <= 100 for value in values):
                errors.append(f"{spec['spec_id']}/seed_{seed}: metric outside [0,100]")
            if not metric.get("navmesh_success") and any(
                abs(value) > 1e-9 for value in values
            ):
                errors.append(
                    f"{spec['spec_id']}/seed_{seed}: ITT failure is not three zeros"
                )
            rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "scale_m_per_native": scale,
                    "camera_rmse_m": rmse,
                    "occupied_voxels": reconstruction["voxel_stats"]["occupied_voxels"],
                    "navigable_area_ratio": values[0],
                    "connected_area_ratio": values[1],
                    "navmesh_success": metric.get("navmesh_success"),
                    "diagnostic_navigable_area_ratio_before_itt": metric.get(
                        "diagnostic_navigable_area_ratio_before_itt"
                    ),
                    "debug_overlay": str(run / "navigation/debug_topdown.png")
                    if (run / "navigation/debug_topdown.png").is_file()
                    else None,
                    "failure": metric.get("failures", []),
                }
            )
    audit = {
        "method": "spatialgen",
        "phase": "pilot",
        "planned_runs": 10,
        "audited_runs": len(rows),
        "implementation_hashes": expected_hashes,
        "navmesh_successes": sum(row["navmesh_success"] is True for row in rows),
        "debug_overlays": sum(row["debug_overlay"] is not None for row in rows),
        "rows": rows,
        "errors": errors,
        "passed": len(rows) == 10 and not errors,
    }
    atomic_json(output, audit)
    print(
        json.dumps(
            {
                key: audit[key]
                for key in (
                    "audited_runs",
                    "navmesh_successes",
                    "debug_overlays",
                    "passed",
                )
            }
        )
    )
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
