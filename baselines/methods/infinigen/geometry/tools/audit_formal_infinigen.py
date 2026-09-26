#!/usr/bin/env python3
"""Audit the frozen 100-run Infinigen Indoors Table 3 matrix.

This is deliberately independent of aggregation.  It checks the terminal
contract, implementation hashes, scene-level arithmetic, Table 2 ITT mapping,
and a deterministic 5% raw-to-metric hash sample.
"""

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
import random
from collections import Counter
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPECS = BASELINES / "protocol/geometry/indoor_specs.jsonl"
INVENTORY = BASELINES / "evaluation/geometry/results/reuse_inventory.json"
THRESHOLDS = BASELINES / "protocol/geometry/reference_thresholds.json"
DATA_ROOT = BASELINES / "data/table3/indoor/infinigen_indoors"
OUTPUT = BASELINES / "evaluation/geometry/results/formal_audit.json"

METRICS = (
    "collision_rate",
    "floating_rate",
    "oob_rate",
    "support_validity",
    "navigable_area_ratio",
    "connected_area_ratio",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def close(actual: float, expected: float, tolerance: float = 1e-8) -> bool:
    return math.isclose(
        float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance
    )


def ratio(numerator: int, denominator: int) -> float:
    return 100.0 * numerator / denominator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--sample-seed", type=int, default=20260909)
    parser.add_argument("--sample-count", type=int, default=5)
    args = parser.parse_args()

    specs = [
        json.loads(line)
        for line in SPECS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    inventory = read_json(INVENTORY)
    expected = {
        (entry["spec_id"], int(entry["seed"])): entry for entry in inventory["runs"]
    }
    thresholds = read_json(THRESHOLDS)
    errors: list[str] = []
    warnings: list[str] = []
    status_counts: Counter[str] = Counter()
    reuse_counts: Counter[str] = Counter()
    nav_successes = 0
    valid_scenes = 0
    eligible_objects = 0
    formal_runs: list[tuple[str, int, Path]] = []
    expected_hashes = None

    required_formal = (
        "GENERATION_SUCCESS",
        "input/boundaries.json",
        "input/native_input.json",
        "input/spec.json",
        "logs/export.log",
        "logs/export_record.json",
        "metrics/debug_structural_topdown.png",
        "scene/canonical/collision.glb",
        "scene/canonical/collision_geometry.npz",
        "scene/canonical/empty_reference_geometry.npz",
        "scene/canonical/instances.json",
        "scene/canonical/transform.json",
        "scene/raw/REFERENCE.json",
    )

    for spec in specs:
        spec_id = spec["spec_id"]
        for seed in range(4):
            run_id = f"{spec_id}/seed_{seed}"
            run_dir = args.data_root / spec_id / f"seed_{seed}"
            for relative in (
                "EVALUATION_SUCCESS",
                "run_manifest.json",
                "metrics/structural.json",
                "metrics/navigability.json",
            ):
                if not (run_dir / relative).is_file():
                    errors.append(f"{run_id}: missing {relative}")
            if errors and any(item.startswith(run_id + ":") for item in errors):
                continue

            manifest = read_json(run_dir / "run_manifest.json")
            structural = read_json(run_dir / "metrics/structural.json")
            nav = read_json(run_dir / "metrics/navigability.json")
            source = expected.get((spec_id, seed))
            if source is None:
                errors.append(f"{run_id}: absent from reuse inventory")
                continue
            source_status = source["table2_status"]
            status_counts[source_status] += 1
            reuse_counts[manifest.get("reuse_status", "missing")] += 1

            if (
                manifest.get("method") != "infinigen_indoors"
                or manifest.get("domain") != "indoor"
            ):
                errors.append(f"{run_id}: wrong method/domain")
            if (
                manifest.get("spec_id") != spec_id
                or int(manifest.get("logical_seed", -1)) != seed
            ):
                errors.append(f"{run_id}: manifest identity mismatch")
            if manifest.get("source_table2_status") != source_status:
                errors.append(f"{run_id}: Table 2 status mismatch")
            hashes = manifest.get("implementation_hashes")
            if expected_hashes is None:
                expected_hashes = hashes
            elif hashes != expected_hashes:
                errors.append(f"{run_id}: implementation hashes differ across matrix")

            for key in METRICS:
                value = structural.get(key) if key in structural else nav.get(key)
                if (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0.0 <= value <= 100.0
                ):
                    errors.append(f"{run_id}: invalid {key}={value!r}")

            nav_successes += bool(nav.get("navmesh_success"))
            valid_scenes += bool(nav.get("valid"))
            eligible_objects += int(structural.get("eligible_objects", 0))

            if source_status != "formal_success":
                expected_structural = {
                    "collision_rate": 100.0,
                    "floating_rate": 100.0,
                    "oob_rate": 100.0,
                    "support_validity": 0.0,
                }
                for key, value in expected_structural.items():
                    if not close(structural.get(key, math.nan), value):
                        errors.append(f"{run_id}: ITT {key} is not {value}")
                if any(
                    float(nav.get(key, math.nan)) != 0.0
                    for key in ("navigable_area_ratio", "connected_area_ratio")
                ):
                    errors.append(f"{run_id}: ITT navigation is not zero")
                if nav.get("navmesh_success") or nav.get("valid"):
                    errors.append(f"{run_id}: ITT success flag is true")
                if manifest.get("reuse_status") != "table2_failure_itt":
                    errors.append(f"{run_id}: wrong ITT reuse status")
                continue

            formal_runs.append((spec_id, seed, run_dir))
            for relative in required_formal:
                if not (run_dir / relative).is_file():
                    errors.append(f"{run_id}: missing formal artifact {relative}")
            if (
                manifest.get("reuse_status") != "reused_raw"
                or manifest.get("evaluation_status") != "success"
            ):
                errors.append(f"{run_id}: wrong formal terminal status")

            instances = read_json(run_dir / "scene/canonical/instances.json")
            instance_values = instances.get("instances", [])
            instance_ids = [item.get("instance_id") for item in instance_values]
            collision_instances = sum(
                bool(item.get("include_collision")) for item in instance_values
            )
            if collision_instances != int(structural["eligible_objects"]):
                errors.append(f"{run_id}: collision-instance/eligible count mismatch")
            if len(instance_ids) != len(set(instance_ids)):
                errors.append(f"{run_id}: duplicate native instance IDs")
            helper_ids = [
                value
                for value in instance_ids
                if value
                and any(
                    token in value.lower()
                    for token in ("placeholder", ".cutter", "spawn_placeholder")
                )
            ]
            if helper_ids:
                errors.append(f"{run_id}: helper instances leaked: {helper_ids[:3]}")

            denominator = int(structural["eligible_objects"])
            support_denominator = int(structural["support_required_objects"])
            edge_denominator = int(structural["required_support_edges"])
            arithmetic = (
                ("collision_rate", int(structural["collision_objects"]), denominator),
                (
                    "floating_rate",
                    int(structural["floating_objects"]),
                    support_denominator,
                ),
                ("oob_rate", int(structural["oob_objects"]), denominator),
                (
                    "support_validity",
                    int(structural["valid_support_edges"]),
                    edge_denominator,
                ),
            )
            for key, numerator, divisor in arithmetic:
                if divisor <= 0 or not close(
                    structural[key], ratio(numerator, divisor)
                ):
                    errors.append(f"{run_id}: inconsistent {key} arithmetic")

            if not nav.get("failures"):
                for relative in (
                    "navigation/components.json",
                    "navigation/debug_topdown.png",
                    "navigation/empty_reference.navmesh",
                    "navigation/final.navmesh",
                ):
                    if not (run_dir / relative).is_file():
                        errors.append(
                            f"{run_id}: completed Recast build missing {relative}"
                        )
            elif bool(nav.get("navmesh_success")):
                errors.append(f"{run_id}: successful NavMesh has failure records")

            if float(nav["empty_reference_area_m2"]) > 0.0:
                expected_nav = min(
                    100.0,
                    ratio(
                        float(nav["final_navmesh_area_m2"]),
                        float(nav["empty_reference_area_m2"]),
                    ),
                )
                if not close(nav["navigable_area_ratio"], expected_nav):
                    errors.append(f"{run_id}: inconsistent navigable area arithmetic")
            elif float(nav["navigable_area_ratio"]) != 0.0:
                errors.append(
                    f"{run_id}: nonzero navigable ratio with zero reference area"
                )
            if float(nav["final_navmesh_area_m2"]) <= 0.0:
                if float(nav["connected_area_ratio"]) != 0.0:
                    errors.append(
                        f"{run_id}: nonzero connectivity with zero final area"
                    )
            else:
                expected_connected = ratio(
                    float(nav["largest_component_area_m2"]),
                    float(nav["final_navmesh_area_m2"]),
                )
                if not close(nav["connected_area_ratio"], expected_connected):
                    errors.append(f"{run_id}: inconsistent connected area arithmetic")

            minimum_fraction = float(
                nav.get("recast_config", {})
                .get("success", {})
                .get("minimum_reference_area_fraction", 0.01)
            )
            expected_nav_success = bool(
                not nav.get("failures")
                and math.isfinite(float(nav["empty_reference_area_m2"]))
                and math.isfinite(float(nav["final_navmesh_area_m2"]))
                and float(nav["empty_reference_area_m2"]) > 0.0
                and float(nav["final_navmesh_area_m2"])
                >= minimum_fraction * float(nav["empty_reference_area_m2"])
                and bool(nav.get("spawn_check_passed"))
            )
            if bool(nav.get("navmesh_success")) != expected_nav_success:
                errors.append(
                    f"{run_id}: NavMesh success flag disagrees with frozen predicate"
                )

            expected_valid = (
                bool(structural.get("output_contract_passed"))
                and structural["collision_rate"] == 0.0
                and structural["floating_rate"] == 0.0
                and structural["oob_rate"] == 0.0
                and structural["support_validity"] == 100.0
                and bool(nav.get("navmesh_success"))
                and nav["navigable_area_ratio"] >= thresholds["navigable_area_ratio"]
                and nav["connected_area_ratio"] >= thresholds["connected_area_ratio"]
            )
            if bool(nav.get("valid")) != expected_valid:
                errors.append(f"{run_id}: valid flag disagrees with frozen predicate")

            reference = read_json(run_dir / "scene/raw/REFERENCE.json")
            source_scene = Path(reference.get("path", ""))
            if (
                not reference.get("preserved_by_reference")
                or not source_scene.is_file()
            ):
                errors.append(f"{run_id}: broken raw reference")
            elif source_scene.stat().st_size != int(reference.get("size_bytes", -1)):
                errors.append(f"{run_id}: raw reference size changed")

    formal_runs.sort(key=lambda item: (item[0], item[1]))
    rng = random.Random(args.sample_seed)
    sampled = sorted(rng.sample(formal_runs, min(args.sample_count, len(formal_runs))))
    sample_records = []
    for spec_id, seed, run_dir in sampled:
        run_id = f"{spec_id}/seed_{seed}"
        reference = read_json(run_dir / "scene/raw/REFERENCE.json")
        raw_path = Path(reference["path"])
        raw_hash = sha256(raw_path)
        if raw_hash != reference.get("sha256"):
            errors.append(f"{run_id}: sampled raw SHA-256 mismatch")
        hashed_files = {
            relative: sha256(run_dir / relative)
            for relative in (
                "scene/canonical/collision.glb",
                "scene/canonical/instances.json",
                "metrics/structural.json",
                "metrics/navigability.json",
            )
        }
        sample_records.append(
            {
                "run_id": run_id,
                "raw_path": str(raw_path),
                "raw_sha256": raw_hash,
                "raw_reference_match": raw_hash == reference.get("sha256"),
                "downstream_sha256": hashed_files,
            }
        )

    result = {
        "method": "infinigen_indoors",
        "domain": "indoor",
        "planned_runs": len(specs) * 4,
        "terminal_runs": sum(status_counts.values()),
        "source_status_counts": dict(sorted(status_counts.items())),
        "reuse_counts": dict(sorted(reuse_counts.items())),
        "formal_artifact_runs": len(formal_runs),
        "itt_runs": sum(
            count
            for status, count in status_counts.items()
            if status != "formal_success"
        ),
        "eligible_objects_total": eligible_objects,
        "navmesh_success_runs": nav_successes,
        "valid_scene_runs": valid_scenes,
        "implementation_hashes": expected_hashes,
        "sample_seed": args.sample_seed,
        "sample_count": len(sample_records),
        "raw_to_metric_samples": sample_records,
        "warnings": warnings,
        "errors": errors,
        "passed": not errors and sum(status_counts.values()) == len(specs) * 4,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "planned_runs",
                    "terminal_runs",
                    "source_status_counts",
                    "reuse_counts",
                    "formal_artifact_runs",
                    "itt_runs",
                    "navmesh_success_runs",
                    "valid_scene_runs",
                    "sample_count",
                    "passed",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        print("first_errors:")
        for item in errors[:20]:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
