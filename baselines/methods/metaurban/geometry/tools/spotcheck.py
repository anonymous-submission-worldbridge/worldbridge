#!/usr/bin/env python3
"""Recompute a fixed 5% raw-to-canonical-to-metric MetaUrban sample."""

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
from pathlib import Path

import numpy as np


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import TABLE3
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import load_jsonl
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256
from baselines.methods.metaurban.geometry.metrics.navigation import connected_components
from baselines.methods.metaurban.geometry.metrics.navigation import triangle_areas


def main() -> int:
    candidates = [
        (spec["spec_id"], seed)
        for spec in load_jsonl(PROTOCOL / "urban_specs.jsonl")
        for seed in range(4)
    ]
    rng = np.random.default_rng(20260909)
    chosen = sorted(
        candidates[index]
        for index in rng.choice(len(candidates), size=5, replace=False)
    )
    rows = []
    for spec_id, seed in chosen:
        run_dir = TABLE3 / spec_id / f"seed_{seed}"
        source = read_json(run_dir / "scene/raw/source.json")
        source_run = Path(source["table2_run"])
        geometry_manifest = read_json(
            run_dir / "scene/canonical/geometry_manifest.json"
        )
        structural = read_json(run_dir / "metrics/structural.json")
        navigation = read_json(run_dir / "metrics/navigability.json")
        checks = {
            "table2_manifest": sha256(source_run / "run_manifest.json")
            == source["table2_manifest_sha256"],
            "table2_scene": sha256(source_run / "scene/scene.json")
            == source["table2_scene_descriptor_sha256"],
            "native_input_copy": sha256(source_run / "input/native_input.json")
            == sha256(run_dir / "input/native_input.json"),
            "canonical_files": all(
                sha256(run_dir / "scene/canonical" / filename) == digest
                for filename, digest in geometry_manifest["files"].items()
            ),
        }
        with np.load(run_dir / "navigation/empty_reference.navmesh") as archive:
            reference_vertices, reference_faces = archive["vertices"], archive["faces"]
        with np.load(run_dir / "navigation/final.navmesh") as archive:
            final_vertices, final_faces = archive["vertices"], archive["faces"]
        reference_area = float(
            triangle_areas(reference_vertices, reference_faces).sum()
        )
        final_area = float(triangle_areas(final_vertices, final_faces).sum())
        components = connected_components(final_vertices, final_faces)
        largest = components[0]["area_m2"]
        checks.update(
            {
                "reference_area": math.isclose(
                    reference_area, navigation["empty_reference_area_m2"], rel_tol=1e-6
                ),
                "final_area": math.isclose(
                    final_area, navigation["final_navmesh_area_m2"], rel_tol=1e-6
                ),
                "component_count": len(components) == navigation["component_count"],
                "navigable_ratio": math.isclose(
                    100 * min(1.0, final_area / reference_area),
                    navigation["navigable_area_ratio"],
                    rel_tol=1e-6,
                ),
                "connected_ratio": math.isclose(
                    100 * largest / final_area,
                    navigation["connected_area_ratio"],
                    rel_tol=1e-6,
                ),
                "structural_arithmetic": all(
                    (
                        math.isclose(
                            100 * structural[numerator] / structural[denominator],
                            structural[metric],
                            rel_tol=1e-10,
                        )
                    )
                    for numerator, denominator, metric in (
                        ("collision_objects", "eligible_objects", "collision_rate"),
                        ("floating_objects", "eligible_objects", "floating_rate"),
                        ("oob_objects", "eligible_objects", "oob_rate"),
                        (
                            "valid_support_edges",
                            "required_support_edges",
                            "support_validity",
                        ),
                    )
                ),
            }
        )
        rows.append(
            {
                "spec_id": spec_id,
                "seed": seed,
                "passed": all(checks.values()),
                "checks": checks,
            }
        )
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "selection_seed": 20260909,
        "population": 100,
        "sample_count": 5,
        "sample_percent": 5.0,
        "passed": all(row["passed"] for row in rows),
        "runs": rows,
    }
    atomic_json(PACKAGE / "results/spotcheck.json", payload)
    print(json.dumps({"passed": payload["passed"], "sample": chosen}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
