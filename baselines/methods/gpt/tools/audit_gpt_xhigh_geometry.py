#!/usr/bin/env python3
"""Audit Extra High Table-3 terminals, recovery provenance, and arithmetic."""

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
METHOD = "gpt6_astra_xhigh"
EFFORT = "xhigh"
DATA = Path("/data2/outputs/worldbridge_table3_gpt6_astra_xhigh/table3_eval")
SOURCE = Path("/data2/outputs/worldbridge_table3_gpt6_astra_xhigh/source_recovery")
RESULTS = BASELINES / "results/gpt6_astra_xhigh_table3"
PROTOCOL = (
    BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_xhigh_geometry_protocol.json"
)
RECOVERY_AMENDMENT = (
    BASELINES
    / "methods/gpt/protocol/geometry/gpt6_astra_xhigh_geometry_recovery_20260914.json"
)
TABLE2_AUDIT = BASELINES / "results/gpt6_astra_xhigh/formal_audit.json"
EXPORTER = BASELINES / "methods/gpt/tools/export_gpt_geometry.py"
EVALUATOR = BASELINES / "methods/gpt/tools/evaluate_gpt_geometry_nav.py"


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


def specs(domain: str) -> list[dict]:
    path = BASELINES / f"protocol/generation/{domain}_specs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-7, abs_tol=1e-7)


def main() -> int:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    table2 = json.loads(TABLE2_AUDIT.read_text(encoding="utf-8"))
    originals = {
        (row["domain"], row["spec_id"], int(row["seed"])): row
        for row in table2["records"]
    }
    errors: list[str] = []
    successful: list[Path] = []
    counts = {
        domain: {
            "planned": 0,
            "evaluated": 0,
            "itt": 0,
            "original_itt": 0,
            "recovery_itt": 0,
        }
        for domain in ("indoor", "urban")
    }
    for domain in ("indoor", "urban"):
        for spec in specs(domain):
            for seed in range(4):
                counts[domain]["planned"] += 1
                key = (domain, spec["spec_id"], seed)
                original = originals[key]
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
                try:
                    metric = json.loads(metric_path.read_text(encoding="utf-8"))
                    structural = json.loads(structural_path.read_text(encoding="utf-8"))
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    errors.append(f"unreadable terminal artifact: {run}: {error}")
                    continue
                expected_key = (METHOD, domain, spec["spec_id"], seed)
                if (
                    metric.get("method"),
                    metric.get("domain"),
                    metric.get("spec_id"),
                    metric.get("logical_seed"),
                ) != expected_key:
                    errors.append(f"metric key mismatch: {run}")
                if (
                    manifest.get("method"),
                    manifest.get("domain"),
                    manifest.get("spec_id"),
                    manifest.get("logical_seed"),
                ) != expected_key:
                    errors.append(f"manifest key mismatch: {run}")
                if (
                    structural.get("method") != METHOD
                    or structural.get("reason_code") != "N/A-I"
                ):
                    errors.append(f"structural identity/N/A-I mismatch: {run}")
                if any(
                    structural.get(name) is not None
                    for name in (
                        "collision_rate",
                        "floating_rate",
                        "oob_rate",
                        "support_validity",
                        "valid_scene_rate",
                    )
                ):
                    errors.append(f"invalid structural N/A-I values: {run}")
                for name in ("navigable_area_ratio", "connected_area_ratio"):
                    try:
                        value = float(metric[name])
                    except (KeyError, TypeError, ValueError):
                        errors.append(f"missing numeric {name}: {run}")
                        value = -1.0
                    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
                        errors.append(f"out-of-range {name}: {run}")
                if metric.get("failure_policy") == "itt_worst_case":
                    counts[domain]["itt"] += 1
                    if original.get("scene_built") is True:
                        counts[domain]["recovery_itt"] += 1
                    else:
                        counts[domain]["original_itt"] += 1
                    if any(
                        float(metric.get(name, -1)) != 0.0
                        for name in ("navigable_area_ratio", "connected_area_ratio")
                    ):
                        errors.append(f"ITT continuous value is not zero: {run}")
                    if (
                        metric.get("navmesh_success") is not False
                        or manifest.get("geometry_source_available") is not False
                    ):
                        errors.append(f"ITT status mismatch: {run}")
                    if (
                        original.get("scene_built") is not True
                        and metric.get("failure_reason") != "original_table2_unbuilt"
                    ):
                        errors.append(f"original failure was not preserved: {run}")
                    continue

                counts[domain]["evaluated"] += 1
                successful.append(run)
                if original.get("scene_built") is not True:
                    errors.append(f"originally unbuilt slot was regenerated: {run}")
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
                geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
                instances = json.loads(
                    (run / "scene/canonical/instances.json").read_text(encoding="utf-8")
                )
                if (
                    geometry.get("method") != METHOD
                    or instances.get("method") != METHOD
                ):
                    errors.append(f"canonical method identity mismatch: {run}")
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
                source = SOURCE / domain / METHOD / spec["spec_id"] / f"seed_{seed}"
                source_blend = source / "scene/scene.blend"
                source_manifest_path = source / "run_manifest.json"
                recovery_path = source / "table3_source_recovery.json"
                if (
                    Path(geometry["source_blend"]) != source_blend
                    or not source_blend.is_file()
                ):
                    errors.append(f"wrong recovery source blend: {run}")
                elif sha256(source_blend) != geometry.get("source_blend_sha256"):
                    errors.append(f"recovery source blend hash mismatch: {run}")
                if not source_manifest_path.is_file() or not recovery_path.is_file():
                    errors.append(f"missing source recovery provenance: {run}")
                else:
                    source_manifest = json.loads(
                        source_manifest_path.read_text(encoding="utf-8")
                    )
                    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
                    if (
                        source_manifest.get("method") != METHOD
                        or source_manifest.get("reasoning_effort_requested") != EFFORT
                        or not source_manifest.get("build_success")
                    ):
                        errors.append(f"source is not an xhigh recovery build: {run}")
                    if (
                        recovery.get("exact_byte_recovery") is not False
                        or recovery.get("recovery_amendment_sha256")
                        != sha256(RECOVERY_AMENDMENT)
                        or recovery.get("original_table2_record") != original
                    ):
                        errors.append(f"source recovery disclosure mismatch: {run}")
                if geometry.get("exporter_sha256") != sha256(EXPORTER):
                    errors.append(f"shared High exporter provenance mismatch: {run}")
                provenance = metric.get("provenance", {})
                if provenance.get("evaluator_sha256") != sha256(EVALUATOR):
                    errors.append(f"shared High evaluator provenance mismatch: {run}")
                if provenance.get("canonical_manifest_sha256") != sha256(geometry_path):
                    errors.append(f"metric/canonical provenance mismatch: {run}")
                reference = float(metric["reference_navmesh_area_m2"])
                final = float(metric["final_navmesh_area_m2"])
                expected_nav = (
                    100.0 * min(1.0, max(0.0, final / reference))
                    if reference > 0
                    else 0.0
                )
                component_areas = metric["component_areas_m2"]
                expected_connected = (
                    100.0 * float(component_areas[0]) / final
                    if final > 0 and component_areas
                    else 0.0
                )
                expected_success = bool(
                    reference > 0
                    and final >= 0.01 * reference
                    and math.isfinite(final)
                    and metric["final_spawn_projection"].get("projected")
                )
                if not close(expected_nav, metric["navigable_area_ratio"]):
                    errors.append(f"navigable arithmetic mismatch: {run}")
                if not close(expected_connected, metric["connected_area_ratio"]):
                    errors.append(f"connected arithmetic mismatch: {run}")
                if expected_success != metric.get("navmesh_success"):
                    errors.append(f"NavMesh success arithmetic mismatch: {run}")

    for domain in ("indoor", "urban"):
        expected = protocol["source_recovery"]["expected_coverage"][domain]
        if counts[domain]["planned"] != 100:
            errors.append(f"{domain} planned coverage mismatch: {counts[domain]}")
        if counts[domain]["evaluated"] != int(expected["evaluated"]) or counts[domain][
            "itt"
        ] != int(expected["itt"]):
            errors.append(
                f"{domain} evaluated/ITT mismatch: observed={counts[domain]}, expected={expected}"
            )
    lock_path = RESULTS / "metrics.lock.json"
    if not lock_path.is_file():
        errors.append("missing metrics.lock.json")
    else:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for relative, expected_hash in lock.get("files", {}).items():
            path = BASELINES / relative
            if not path.is_file() or sha256(path) != expected_hash:
                errors.append(f"frozen file mismatch: {relative}")

    rng = random.Random(int(protocol["navigation"]["bootstrap_seed"]))
    spot = (
        sorted(rng.sample(successful, 10), key=str)
        if len(successful) >= 10
        else successful
    )
    spot_results = []
    for run in spot:
        geometry_path = run / "scene/canonical/geometry_manifest.json"
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        metric = json.loads(
            (run / "metrics/navigability.json").read_text(encoding="utf-8")
        )
        passed = (
            sha256(Path(geometry["source_blend"])) == geometry["source_blend_sha256"]
        )
        passed = (
            passed
            and sha256(geometry_path)
            == metric["provenance"]["canonical_manifest_sha256"]
        )
        spot_results.append({"run": str(run), "passed": passed})
        if not passed:
            errors.append(f"spot-chain mismatch: {run}")

    csv_path = RESULTS / "table3.csv"
    full_path = RESULTS / "table3_full.json"
    csv_rows = (
        list(csv.DictReader(csv_path.open(encoding="utf-8")))
        if csv_path.is_file()
        else []
    )
    if len(csv_rows) != 2 or not full_path.is_file():
        errors.append("aggregate output missing or does not contain exactly two rows")
    else:
        full = json.loads(full_path.read_text(encoding="utf-8"))
        if full.get("protocol_id") != protocol["protocol_id"]:
            errors.append("aggregate protocol identity mismatch")
        by_domain = {item["domain"]: item for item in full["domains"]}
        for row in csv_rows:
            if (
                row.get("method") != METHOD
                or row.get("exact_table2_byte_reuse") != "false"
            ):
                errors.append(f"aggregate method/recovery identity mismatch: {row}")
                continue
            summary = by_domain[row["domain"]]
            for metric_name in (
                "navigable_area_ratio",
                "connected_area_ratio",
                "navmesh_success_rate",
            ):
                if not close(
                    float(row[metric_name]), summary["metrics"][metric_name]["mean"]
                ):
                    errors.append(
                        f"CSV/full JSON mismatch: {row['domain']} {metric_name}"
                    )

    report = {
        "passed": not errors,
        "method": METHOD,
        "reasoning_effort": EFFORT,
        "source_recovery": True,
        "exact_table2_byte_reuse": False,
        "original_table2_audit_sha256": sha256(TABLE2_AUDIT),
        "recovery_amendment_sha256": sha256(RECOVERY_AMENDMENT),
        "counts": counts,
        "terminal_runs": sum(values["planned"] for values in counts.values()),
        "spotcheck_seed": int(protocol["navigation"]["bootstrap_seed"]),
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
    for error in errors[:50]:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
