#!/usr/bin/env python3
"""Reuse frozen Gemini 3.1 Pro Table-2 meshes for the Table-3 nav track.

This runner has no remote-model transport.  It specializes the already audited
GLM Table-3 orchestration around the shared frozen Blender/Recast evaluator,
while enforcing Gemini's Table-2 identity and subscription-only provenance.
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
from collections import Counter
import copy
import json
from pathlib import Path

import baselines.methods.glm_flash.geometry.run_glm_flash_geometry as shared


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
DISPLAY_NAME = "Gemini 3.1 Pro"
MODEL_ID = "gemini-3.1-pro-high"
PROVIDER_MODEL = "Google AI Pro account / Antigravity CLI"
PROTOCOL = (
    BASELINES / "methods/gemini/protocol/geometry/gemini_3_1_pro_geometry_protocol.json"
)
SOURCE_LOCK = BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
RESULTS = BASELINES / "results/gemini_3_1_pro/table3"
DATA = BASELINES / "data/table3_gemini_3_1_pro"
METRICS_LOCK = RESULTS / "metrics.lock.json"


def sha256(path: Path) -> str:
    return shared.sha256(path)


def raw_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json(path: Path) -> dict:
    """Provide aliases needed by the shared audited orchestration."""
    payload = raw_json(path)
    if Path(path).resolve() == SOURCE_LOCK.resolve():
        payload = copy.deepcopy(payload)
        files = payload["files_sha256"]
        files["methods/glm_flash/protocol/generation/glm53_flash.json"] = files[
            "methods/gemini/protocol/generation/gemini_3_1_pro.json"
        ]
        files["methods/glm_flash/adapter.py"] = files["methods/gemini/adapter.py"]
    elif (
        "data/table2" in Path(path).as_posix()
        and f"/{METHOD}/" in Path(path).as_posix()
        and Path(path).name == "run_manifest.json"
        and source_identity_valid(payload)
    ):
        # The shared audit has a single identity tuple, while Gemini's frozen
        # Table-2 lock explicitly admits byte-exact pre/post client-recovery
        # tuples. Normalize only the in-memory view; source files stay intact.
        payload = copy.deepcopy(payload)
        files = raw_json(SOURCE_LOCK)["files_sha256"]
        payload["identity"]["protocol_sha256"] = files[
            "methods/gemini/protocol/generation/gemini_3_1_pro.json"
        ]
        payload["identity"]["adapter_sha256"] = files["methods/gemini/adapter.py"]
    return payload


def source_identity_valid(manifest: dict) -> bool:
    lock = raw_json(SOURCE_LOCK)
    files = lock["files_sha256"]
    amendment = raw_json(
        (
            BASELINES
            / "methods/gemini/protocol/generation/gemini_3_1_pro_client_recovery_amendment_20260918.json"
        )
    )
    identity = manifest.get("identity", {})
    helper_hashes = {
        lock.get("client_helper_sha256"),
        lock.get("legacy_client_helper_sha256"),
        files.get("methods/gemini/tools/ask_gemini_3_1_pro.sh"),
    }
    helper_hashes.discard(None)
    current_identity = (
        identity.get("protocol_sha256")
        == files["methods/gemini/protocol/generation/gemini_3_1_pro.json"]
        and identity.get("adapter_sha256") == files["methods/gemini/adapter.py"]
        and identity.get("client_helper_sha256")
        == files["methods/gemini/tools/ask_gemini_3_1_pro.sh"]
    )
    legacy = amendment["legacy_identity"]
    legacy_identity = all(
        identity.get(field) == legacy[field]
        for field in (
            "protocol_sha256",
            "adapter_sha256",
            "client_helper_sha256",
        )
    )
    return bool(
        manifest.get("method") == METHOD
        and manifest.get("model_requested") == MODEL_ID
        and manifest.get("model_returned") in (None, MODEL_ID)
        and (
            manifest.get("model_returned") == MODEL_ID
            or not manifest.get("generation_success")
        )
        and manifest.get("auth_mode")
        == "google_ai_pro_account_via_antigravity_no_api_key"
        and {"GEMINI_API_KEY", "GOOGLE_API_KEY"}.issubset(
            set(manifest.get("api_key_environment_cleared", []))
        )
        and identity.get("client_helper_sha256") in helper_hashes
        and (current_identity or legacy_identity)
    )


def source_status(source: Path) -> tuple[bool, str, dict | None]:
    manifest_path = source / "run_manifest.json"
    if not manifest_path.is_file():
        return False, "table2_manifest_missing", None
    manifest = raw_json(manifest_path)
    if not source_identity_valid(manifest):
        return False, "table2_identity_or_auth_mismatch", manifest
    if not manifest.get("generation_success"):
        return False, "table2_generation_failed", manifest
    if not manifest.get("build_success"):
        return False, "table2_build_failed", manifest
    if not (source / "scene/scene.blend").is_file():
        return False, "table2_blend_missing", manifest
    if not (source / "SUCCESS").is_file():
        return False, "table2_success_marker_missing", manifest
    return True, "reusable", manifest


def identity(source: Path, output: Path) -> dict:
    files = {
        "source_blend_sha256": source / "scene/scene.blend",
        "source_manifest_sha256": source / "run_manifest.json",
        "spec_sha256": output / "input/spec.json",
        "shared_exporter_sha256": shared.EXPORTER,
        "shared_evaluator_sha256": shared.EVALUATOR,
        "rules_sha256": shared.RULES,
        "agent_sha256": shared.AGENT,
        "protocol_sha256": PROTOCOL,
        "runner_sha256": Path(__file__),
    }
    return {name: sha256(path) for name, path in files.items()}


def configure_shared() -> None:
    assignments = {
        "METHOD": METHOD,
        "DISPLAY_NAME": DISPLAY_NAME,
        "MODEL_ID": MODEL_ID,
        "PROTOCOL": PROTOCOL,
        "SOURCE_LOCK": SOURCE_LOCK,
        "RESULTS": RESULTS,
        "DATA": DATA,
        "METRICS_LOCK": METRICS_LOCK,
        "source_status": source_status,
        "identity": identity,
        "read_json": read_json,
    }
    for name, value in assignments.items():
        setattr(shared, name, value)


configure_shared()

# Public aliases used by tests and operational inspection.
read_specs = shared.read_specs
source_path = shared.source_path
run_path = shared.run_path
itt_metric = shared.itt_metric
structural_na = shared.structural_na
deterministic_canonical_failure = shared.deterministic_canonical_failure
relabel_export_artifacts = shared.relabel_export_artifacts
atomic_json = shared.atomic_json
now = shared.now


def is_deterministic_navigation_failure(error: BaseException) -> bool:
    return str(error) == "Reference NavMesh has no connected component"


_shared_process_one = shared.process_one


def process_one(spec: dict, seed: int, force: bool) -> dict:
    """Convert a deterministic unusable reference surface to frozen ITT zero."""
    try:
        return _shared_process_one(spec, seed, force)
    except RuntimeError as error:
        if not is_deterministic_navigation_failure(error):
            raise
        output = run_path(spec["domain"], spec["spec_id"], seed)
        if not (output / "CANONICAL_SUCCESS").is_file():
            raise
        reason = "canonical_no_walkable_surface"
        metric = itt_metric(spec, seed, reason)
        metric["failure_detail"] = str(error)
        structural = structural_na(spec, seed)
        manifest = raw_json(output / "run_manifest.json")
        manifest.update(
            {
                "ended_at_utc": now(),
                "failure_reason": reason,
                "failure_detail": str(error),
                "failure_policy": "itt_worst_case",
                "table3_evaluable": False,
            }
        )
        atomic_json(output / "metrics/structural.json", structural)
        atomic_json(output / "metrics/navigability.json", metric)
        atomic_json(output / "run_manifest.json", manifest)
        (output / "EVALUATION_SUCCESS").touch()
        return {
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "seed": seed,
            "status": "itt",
            "reason": reason,
            "failure_detail": str(error),
        }


shared.process_one = process_one


def validate_frozen() -> None:
    protocol = raw_json(PROTOCOL)
    if protocol.get("status") != "frozen":
        raise RuntimeError(
            "Formal execution requires a frozen Gemini 3.1 Pro Table-3 protocol"
        )
    if not METRICS_LOCK.is_file():
        raise RuntimeError("Formal execution requires metrics.lock.json")
    mismatches = []
    for relative, expected in raw_json(METRICS_LOCK).get("files", {}).items():
        path = BASELINES / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError(f"Frozen Gemini Table-3 source changed: {mismatches}")


shared.validate_frozen = validate_frozen


def freeze() -> int:
    protocol = raw_json(PROTOCOL)
    if protocol.get("status") != "frozen":
        raise RuntimeError(
            "Set the Gemini Table-3 protocol to frozen only after pilot review"
        )
    relative_files = [
        "methods/gemini/protocol/geometry/gemini_3_1_pro_geometry_protocol.json",
        "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json",
        "protocol/geometry/agent.yaml",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "methods/gemini/geometry/run_gemini_geometry.py",
        "methods/glm_flash/geometry/run_glm_flash_geometry.py",
        "methods/gpt/tools/gpt_geometry_surface_rules.py",
        "methods/gpt/tools/export_gpt_geometry.py",
        "methods/gpt/tools/evaluate_gpt_geometry_nav.py",
        "methods/gemini/tests/test_gemini_geometry.py",
        "tools/recast_py311/recast.cpython-311-x86_64-linux-gnu.so",
    ]
    missing = [
        relative for relative in relative_files if not (BASELINES / relative).is_file()
    ]
    if missing:
        raise RuntimeError(f"Cannot freeze; missing files: {missing}")
    frozen_at = now()
    RESULTS.mkdir(parents=True, exist_ok=True)
    shared_lock = BASELINES / "results/gpt6_astra/table3/metrics.lock.json"
    atomic_json(
        RESULTS / "method.lock.json",
        {
            "method": METHOD,
            "display_name": DISPLAY_NAME,
            "model_id": MODEL_ID,
            "provider_model": PROVIDER_MODEL,
            "source_auth_mode": "google_ai_pro_account_via_antigravity_no_api_key",
            "source_table2_method_lock": "baselines/methods/gemini/protocol/generation/gemini_3_1_pro.lock.json",
            "source_table2_method_lock_sha256": sha256(SOURCE_LOCK),
            "shared_table3_metrics_lock_sha256": sha256(shared_lock),
            "model_requests_in_table3": 0,
            "reuse_only": True,
            "frozen_at_utc": frozen_at,
        },
    )
    atomic_json(
        METRICS_LOCK,
        {
            "protocol_id": protocol["protocol_id"],
            "files": {
                relative: sha256(BASELINES / relative) for relative in relative_files
            },
            "blender": protocol["blender"],
            "recast_version": "RecastNavigation Python Bindings (custom)",
            "aggregation": protocol["navigation"]["aggregation"],
            "bootstrap_repeats": protocol["navigation"]["bootstrap_repeats"],
            "bootstrap_seed": protocol["navigation"]["bootstrap_seed"],
            "frozen_at_utc": frozen_at,
        },
    )
    print(
        json.dumps(
            {"locked_files": len(relative_files), "frozen_at_utc": frozen_at},
            sort_keys=True,
        )
    )
    return 0


def audit() -> int:
    status = shared.audit()
    report_path = RESULTS / "audit.json"
    report = raw_json(report_path)
    auth_errors = []
    checked = 0
    for domain in ("indoor", "urban"):
        for spec in read_specs(domain):
            for seed in range(4):
                source = source_path(domain, spec["spec_id"], seed)
                manifest_path = source / "run_manifest.json"
                if not manifest_path.is_file() or not source_identity_valid(
                    raw_json(manifest_path)
                ):
                    auth_errors.append(
                        f"invalid frozen subscription provenance: {source}"
                    )
                checked += 1
    report["source_subscription_provenance"] = {
        "checked_runs": checked,
        "transport": "Antigravity CLI with Google AI Pro account subscription",
        "api_key_billing_used": False,
        "errors": auth_errors,
    }
    if auth_errors:
        report["errors"].extend(auth_errors)
        report["passed"] = False
        status = 1
    atomic_json(report_path, report)
    print(
        json.dumps(
            {"subscription_sources_checked": checked, "auth_errors": len(auth_errors)},
            sort_keys=True,
        )
    )
    return status


def seal() -> int:
    required = (
        "method.lock.json",
        "metrics.lock.json",
        "table3.csv",
        "table3_full.json",
        "audit.json",
        "matrix_formal.jsonl",
    )
    missing = [name for name in required if not (RESULTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing final Gemini Table-3 results: {missing}")
    audit_report = raw_json(RESULTS / "audit.json")
    protocol = raw_json(PROTOCOL)
    expected = {
        domain: {"planned": 100, **protocol["reuse"]["expected_coverage"][domain]}
        for domain in ("indoor", "urban")
    }
    if audit_report.get("passed") is not True or audit_report.get("counts") != expected:
        raise RuntimeError("Refusing to seal a failing or incomplete audit")
    rows = [
        json.loads(line)
        for line in (RESULTS / "matrix_formal.jsonl").read_text().splitlines()
        if line
    ]
    counts = Counter(row.get("status") for row in rows)
    if len(rows) != 200 or counts.get("error", 0):
        raise RuntimeError(f"Formal matrix record mismatch: {counts}")
    domains = {}
    for summary in raw_json(RESULTS / "table3_full.json")["domains"]:
        metrics = summary["metrics"]
        nav = float(metrics["navigable_area_ratio"]["mean"])
        connected = float(metrics["connected_area_ratio"]["mean"])
        success = float(metrics["navmesh_success_rate"]["mean"])
        domains[summary["domain"]] = {
            "planned_runs": 100,
            "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
            "itt_runs": summary["itt_failure_runs"],
            "navigable_area_ratio": nav,
            "connected_area_ratio": connected,
            "navmesh_success_rate": success,
            "display_row": [
                "N/A-I",
                "N/A-I",
                "N/A-I",
                "N/A-I",
                f"{nav:.1f}",
                f"{connected:.1f}",
                f"{success:.1f}",
                "N/A-I",
            ],
        }
    payload = {
        "status": "both_domains_table3_verified_and_ready_to_fill",
        "method": METHOD,
        "display_name": DISPLAY_NAME,
        "model_id": MODEL_ID,
        "provider_model": PROVIDER_MODEL,
        "model_requests_in_table3": 0,
        "api_key_billing_used_in_table3": False,
        "sealed_at_utc": now(),
        "formal_matrix": {
            "planned_runs": 200,
            "evaluated_geometry_runs": sum(
                item["evaluated_geometry_runs"] for item in domains.values()
            ),
            "itt_runs": sum(item["itt_runs"] for item in domains.values()),
            "new_runner_failures": 0,
            "matrix_status_counts": dict(counts),
        },
        "domains": domains,
        "files_sha256": {
            "methods/gemini/protocol/geometry/gemini_3_1_pro_geometry_protocol.json": sha256(
                PROTOCOL
            ),
            **{
                f"results/gemini_3_1_pro/table3/{name}": sha256(RESULTS / name)
                for name in required
            },
        },
    }
    atomic_json(RESULTS / "result.lock.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    matrix = subparsers.add_parser("run")
    matrix.add_argument("--phase", choices=("pilot", "formal"), required=True)
    matrix.add_argument("--domain", choices=("indoor", "urban", "both"), default="both")
    matrix.add_argument("--workers", type=int, default=8)
    matrix.add_argument("--force", action="store_true")
    for command in ("freeze", "aggregate", "audit", "seal"):
        subparsers.add_parser(command)
    args = parser.parse_args()
    if args.command == "run":
        return shared.run_matrix(args.phase, args.domain, args.workers, args.force)
    return {
        "freeze": freeze,
        "aggregate": shared.aggregate,
        "audit": audit,
        "seal": seal,
    }[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
