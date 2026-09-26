#!/usr/bin/env python3
"""Deterministic 5% raw-to-metric integrity audit for WorldGen Table 3."""

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
import random
from pathlib import Path

import numpy as np


REPO_ROOT = _BASELINE_PROJECT_ROOT
DATA_ROOT = REPO_ROOT / "baselines/data/table3_worldgen"
OUTPUT = REPO_ROOT / "baselines/results/table3_worldgen/spotcheck.json"
SEED = 20260909


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def navmesh_area(path: Path) -> float:
    archive = np.load(path)
    vertices = archive["vertices"].astype(np.float64, copy=False)
    faces = archive["faces"].astype(np.int64, copy=False)
    if not len(faces):
        return 0.0
    triangles = vertices[faces]
    return float(
        0.5
        * np.linalg.norm(
            np.cross(
                triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            ),
            axis=1,
        ).sum()
    )


def close(actual: float, expected: float) -> bool:
    return bool(np.isclose(actual, expected, rtol=1e-6, atol=1e-5))


def check(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    metrics = json.loads((run_dir / "metrics/navigability.json").read_text())
    components = json.loads((run_dir / "navigation/components.json").read_text())

    raw_path = run_dir / "scene/raw/splat.ply"
    canonical_path = run_dir / "scene/canonical/collision.ply"
    reference_area = navmesh_area(run_dir / "navigation/empty_reference.navmesh")
    final_area = navmesh_area(run_dir / "navigation/final.navmesh")
    component_areas = [float(value) for value in components["component_areas_m2"]]
    largest_area = max(component_areas, default=0.0)
    navigable_ratio = (
        100.0 * final_area / reference_area if reference_area > 0.0 else 0.0
    )
    connected_ratio = 100.0 * largest_area / final_area if final_area > 0.0 else 0.0

    checks = {
        "raw_symlink": raw_path.is_symlink(),
        "raw_sha256": sha256(raw_path) == manifest["raw_splat_sha256"],
        "canonical_sha256": sha256(canonical_path)
        == manifest["canonical_collision_sha256"],
        "reference_area": close(reference_area, metrics["empty_reference_area_m2"]),
        "final_area": close(final_area, metrics["final_navmesh_area_m2"]),
        "component_count": len(component_areas) == metrics["component_count"],
        "largest_component_area": close(
            largest_area, metrics["largest_component_area_m2"]
        ),
        "navigable_area_ratio": close(navigable_ratio, metrics["navigable_area_ratio"]),
        "connected_area_ratio": close(connected_ratio, metrics["connected_area_ratio"]),
        "formal_marker": (run_dir / "EVALUATION_SUCCESS").is_file(),
    }
    return {
        "run": str(run_dir.relative_to(REPO_ROOT)),
        "domain": manifest["domain"],
        "spec_id": manifest["spec_id"],
        "logical_seed": manifest["logical_seed"],
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    runs = sorted(
        path.parent for path in DATA_ROOT.glob("*/*/*/seed_*/run_manifest.json")
    )
    if len(runs) != 200:
        raise SystemExit(f"expected 200 formal runs, found {len(runs)}")
    selected = sorted(random.Random(SEED).sample(runs, len(runs) // 20))
    records = [check(run) for run in selected]
    report = {
        "audit": "deterministic_raw_to_metric_spotcheck",
        "population": len(runs),
        "sample_fraction": 0.05,
        "sample_seed": SEED,
        "sample_size": len(records),
        "passed": all(record["passed"] for record in records),
        "passed_count": sum(record["passed"] for record in records),
        "records": records,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        f"WORLDGEN_SPOTCHECK passed={report['passed']} "
        f"sample={report['passed_count']}/{report['sample_size']} population={report['population']}"
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
