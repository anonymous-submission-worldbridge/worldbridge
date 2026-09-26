#!/usr/bin/env python3
"""Full terminal/provenance/arithmetic audit for GPT-6 Astra Table 3."""

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


import csv
import hashlib
import json
import math
import random
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA = BASELINES / "data/table3_gpt6_astra"
RESULTS = BASELINES / "results/gpt6_astra/table3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def specs(domain: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (BASELINES / f"protocol/generation/{domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-7, abs_tol=1e-7)


def main() -> int:
    errors = []
    successful = []
    counts = {
        domain: {"planned": 0, "evaluated": 0, "itt": 0}
        for domain in ("indoor", "urban")
    }
    for domain in ("indoor", "urban"):
        for spec in specs(domain):
            for seed in range(4):
                counts[domain]["planned"] += 1
                run = DATA / domain / spec["spec_id"] / f"seed_{seed}"
                metric_path = run / "metrics/navigability.json"
                structural_path = run / "metrics/structural.json"
                manifest_path = run / "run_manifest.json"
                if (
                    not all(
                        path.is_file()
                        for path in (metric_path, structural_path, manifest_path)
                    )
                    or not (run / "EVALUATION_SUCCESS").is_file()
                ):
                    errors.append(f"missing terminal artifacts: {run}")
                    continue
                metric = json.loads(metric_path.read_text())
                structural = json.loads(structural_path.read_text())
                manifest = json.loads(manifest_path.read_text())
                key = (domain, spec["spec_id"], seed)
                if (
                    metric.get("domain"),
                    metric.get("spec_id"),
                    metric.get("logical_seed"),
                ) != key:
                    errors.append(f"metric key mismatch: {run}")
                if structural.get("reason_code") != "N/A-I" or any(
                    structural.get(name) is not None
                    for name in (
                        "collision_rate",
                        "floating_rate",
                        "oob_rate",
                        "support_validity",
                        "valid_scene_rate",
                    )
                ):
                    errors.append(f"invalid structural N/A-I contract: {run}")
                for name in ("navigable_area_ratio", "connected_area_ratio"):
                    value = float(metric[name])
                    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
                        errors.append(f"out-of-range {name}: {run}")
                if metric.get("failure_policy") == "itt_worst_case":
                    counts[domain]["itt"] += 1
                    if (
                        any(
                            float(metric[name]) != 0.0
                            for name in ("navigable_area_ratio", "connected_area_ratio")
                        )
                        or metric.get("navmesh_success") is not False
                    ):
                        errors.append(f"ITT value is not exact worst case: {run}")
                    continue
                counts[domain]["evaluated"] += 1
                successful.append(run)
                geometry_path = run / "scene/canonical/geometry_manifest.json"
                contract_files = (
                    run / "input/native_input.json",
                    run / "input/boundaries.json",
                    run / "scene/canonical/instances.json",
                    run / "scene/canonical/transform.json",
                    run / "navigation/empty_reference.navmesh",
                    run / "navigation/final.navmesh",
                    run / "navigation/components.json",
                    run / "navigation/debug_topdown.png",
                )
                if (
                    not geometry_path.is_file()
                    or not (run / "CANONICAL_SUCCESS").is_file()
                    or not (run / "GENERATION_SUCCESS").is_file()
                    or not all(path.is_file() for path in contract_files)
                ):
                    errors.append(f"missing canonical output: {run}")
                    continue
                geometry = json.loads(geometry_path.read_text())
                for name in (
                    "empty_reference_ply",
                    "collision_ply",
                    "empty_reference_glb",
                    "collision_glb",
                ):
                    artifact = (
                        run
                        / "scene/canonical"
                        / name.replace("_ply", ".ply").replace("_glb", ".glb")
                    )
                    if (
                        not artifact.is_file()
                        or sha256(artifact) != geometry[name]["sha256"]
                    ):
                        errors.append(f"canonical hash mismatch {name}: {run}")
                source_blend = Path(geometry["source_blend"])
                if (
                    not source_blend.is_file()
                    or sha256(source_blend) != geometry["source_blend_sha256"]
                ):
                    errors.append(f"source blend mismatch: {run}")
                reference = float(metric["reference_navmesh_area_m2"])
                final = float(metric["final_navmesh_area_m2"])
                expected_nav = (
                    100.0 * min(1.0, max(0.0, final / reference))
                    if reference > 0
                    else 0.0
                )
                expected_connected = (
                    100.0 * float(metric["component_areas_m2"][0]) / final
                    if final > 0 and metric["component_areas_m2"]
                    else 0.0
                )
                expected_success = bool(
                    reference > 0
                    and final >= 0.01 * reference
                    and math.isfinite(final)
                    and metric["final_spawn_projection"].get("projected")
                )
                if (
                    not close(expected_nav, metric["navigable_area_ratio"])
                    or not close(expected_connected, metric["connected_area_ratio"])
                    or expected_success != metric["navmesh_success"]
                ):
                    errors.append(f"navigation arithmetic mismatch: {run}")

    expected = {
        "indoor": {"planned": 100, "evaluated": 91, "itt": 9},
        "urban": {"planned": 100, "evaluated": 94, "itt": 6},
    }
    if counts != expected:
        errors.append(f"coverage mismatch: observed={counts}, expected={expected}")
    lock_path = RESULTS / "metrics.lock.json"
    if not lock_path.is_file():
        errors.append("missing metrics.lock.json")
    else:
        lock = json.loads(lock_path.read_text())
        for relative, expected_hash in lock.get("files", {}).items():
            path = BASELINES / relative
            if not path.is_file() or sha256(path) != expected_hash:
                errors.append(f"frozen file mismatch: {relative}")

    spot_rng = random.Random(20260909)
    spot = (
        sorted(spot_rng.sample(successful, 10), key=str)
        if len(successful) >= 10
        else successful
    )
    spot_results = []
    for run in spot:
        geometry = json.loads(
            (run / "scene/canonical/geometry_manifest.json").read_text()
        )
        chain_ok = (
            sha256(Path(geometry["source_blend"])) == geometry["source_blend_sha256"]
        )
        chain_ok = (
            chain_ok
            and sha256(run / "scene/canonical/geometry_manifest.json")
            == json.loads((run / "metrics/navigability.json").read_text())[
                "provenance"
            ]["canonical_manifest_sha256"]
        )
        spot_results.append(
            {"run": str(run.relative_to(BASELINES)), "passed": chain_ok}
        )
        if not chain_ok:
            errors.append(f"spot-chain mismatch: {run}")

    csv_path = RESULTS / "table3.csv"
    csv_rows = (
        list(csv.DictReader(csv_path.open(encoding="utf-8")))
        if csv_path.is_file()
        else []
    )
    full_path = RESULTS / "table3_full.json"
    if len(csv_rows) != 2 or not full_path.is_file():
        errors.append("aggregate output missing or does not contain exactly two rows")
    else:
        full = json.loads(full_path.read_text())
        by_domain = {item["domain"]: item for item in full["domains"]}
        for row in csv_rows:
            summary = by_domain[row["domain"]]
            for metric in (
                "navigable_area_ratio",
                "connected_area_ratio",
                "navmesh_success_rate",
            ):
                if not close(float(row[metric]), summary["metrics"][metric]["mean"]):
                    errors.append(f"CSV/full JSON mismatch: {row['domain']} {metric}")
    report = {
        "passed": not errors,
        "counts": counts,
        "terminal_runs": sum(value["planned"] for value in counts.values()),
        "spotcheck_seed": 20260909,
        "spotcheck_count": len(spot_results),
        "spotchecks": spot_results,
        "errors": errors,
    }
    atomic_json(RESULTS / "audit.json", report)
    print(
        json.dumps(
            {"passed": report["passed"], "counts": counts, "errors": len(errors)},
            sort_keys=True,
        )
    )
    if errors:
        for error in errors[:50]:
            print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
