#!/usr/bin/env python3
"""Write MetaUrban Table 3 method and metric lock files from local evidence."""

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


import sys
from pathlib import Path


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.methods.metaurban.geometry.common import BASELINES
from baselines.methods.metaurban.geometry.common import PACKAGE
from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import SOURCE
from baselines.methods.metaurban.geometry.common import atomic_json
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.common import sha256
from baselines.methods.metaurban.geometry.common import utc_now


def relative_hash(path: Path) -> dict:
    return {"path": str(path.relative_to(BASELINES)), "sha256": sha256(path)}


def main() -> None:
    environment = BASELINES / "methods/metaurban/environment/metaurban.json"
    full_assets = BASELINES / "methods/metaurban/environment/metaurban_full_assets.json"
    table2_audit = BASELINES / "results/metaurban/matrix_audit.json"
    source_lock = read_json(environment)
    method = {
        "method": "metaurban",
        "display_name": "MetaUrban",
        "domain": "urban",
        "track": "structured_physics_ready",
        "frozen_at_utc": utc_now(),
        "official_repository": source_lock["source"]["repository"],
        "source_commit": source_lock["source"]["commit"],
        "installed_version": source_lock["source"]["installed_version_string"],
        "license": {"spdx": "Apache-2.0", **relative_hash(SOURCE / "LICENSE.txt")},
        "environment_lock": relative_hash(environment),
        "full_asset_manifest": relative_hash(full_assets),
        "full_asset_archive": {
            "path": source_lock["assets"]["full_archive_path"],
            "size_bytes": source_lock["assets"]["full_archive_size_bytes"],
            "sha256": source_lock["assets"]["full_archive_sha256"],
            "static_glb_count": source_lock["assets"]["static_glb_count"],
            "metadata_json_count": source_lock["assets"]["metadata_json_count"],
            "building_glb_count": source_lock["assets"]["building_glb_count"],
        },
        "source_table2_audit": relative_hash(table2_audit),
        "source_table2_runs": "baselines/data/table2/urban/metaurban",
        "table2_reused_runs": 100,
        "table3_generation_policy": "deterministic_geometry_reconstruction_only_no_rgb_or_metric_regeneration",
        "adapter": relative_hash(BASELINES / "methods/metaurban/adapter.py"),
        "table2_protocol": relative_hash(
            BASELINES / "methods/metaurban/protocol/generation/metaurban_protocol.yaml"
        ),
        "final_representation": "native AssetManager instances, Bullet OBB colliders, Panda3D final visual bounds",
        "scale_source": "native MetaUrban meters",
    }
    atomic_json(PROTOCOL / "method.lock.json", method)

    thresholds = read_json(PROTOCOL / "reference_thresholds.json")
    metric_paths = {
        "evaluate_spec": PACKAGE / "evaluate_spec.py",
        "geometry": PACKAGE / "metrics/geometry.py",
        "navigation": PACKAGE / "metrics/navigation.py",
        "aggregate": PACKAGE / "metrics/aggregate.py",
        "calibrate_reference": PACKAGE / "tools/calibrate_reference.py",
        "urban_specs": PROTOCOL / "urban_specs.jsonl",
        "object_roles": PROTOCOL / "object_roles.json",
        "support_rules": PROTOCOL / "support_rules.json",
        "collision_exceptions": PROTOCOL / "collision_exceptions.json",
        "containers": PROTOCOL / "containers.json",
        "agent": PROTOCOL / "agent.json",
        "protocol": PROTOCOL / "protocol.json",
        "reference_thresholds": PROTOCOL / "reference_thresholds.json",
        "reference_definitions": PROTOCOL / "reference_urban.jsonl",
        "recast": next((PACKAGE / "recast").glob("recast*.so")),
    }
    metrics = {
        "protocol_id": "worldbridge-table3-metaurban-urban-v1",
        "frozen_at_utc": utc_now(),
        "collision_thresholds": read_json(PROTOCOL / "collision_exceptions.json"),
        "support_thresholds": read_json(PROTOCOL / "support_rules.json"),
        "oob_thresholds": {
            "outside_area_fraction": 0.01,
            "centroid_must_be_inside": True,
        },
        "navigation_agent": read_json(PROTOCOL / "agent.json"),
        "valid_scene_thresholds": {
            "navigable_area_ratio": thresholds["navigable_area_ratio"],
            "connected_area_ratio": thresholds["connected_area_ratio"],
            "reference_count": thresholds["reference_count"],
            "percentile": thresholds["percentile"],
            "calibration_result": "baselines/methods/metaurban/geometry/results/reference_urban_calibration.json",
        },
        "aggregation": read_json(PROTOCOL / "protocol.json")["aggregation"],
        "hashes": {name: sha256(path) for name, path in metric_paths.items()},
    }
    atomic_json(PROTOCOL / "metrics.lock.json", metrics)
    print(PROTOCOL / "method.lock.json")
    print(PROTOCOL / "metrics.lock.json")


if __name__ == "__main__":
    main()
