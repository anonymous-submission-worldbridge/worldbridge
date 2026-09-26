#!/usr/bin/env python3
"""Strict terminal-state and provenance audit for Gemini 3.1 Pro Table 2."""
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
from pathlib import Path
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gemini.adapter import digest
from baselines.methods.gemini.adapter import write_json


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def audit(data_root: Path, pilot: bool, require_metrics: bool = False) -> dict:
    config = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    current_helper = (config["client_helper"], config["client_helper_sha256"])
    legacy_helper = (
        config["legacy_client_helper"]["path"],
        config["legacy_client_helper"]["sha256"],
    )
    allowed_helper_hashes = {current_helper[1], legacy_helper[1]}
    allowed_helper_paths = {current_helper[0], legacy_helper[0]}
    seeds = [0, 1] if pilot else [0, 1, 2, 3]
    records, problems = [], []
    per_domain = {}
    for domain in ("indoor", "urban"):
        specs = read_jsonl(ROOT / f"protocol/generation/{domain}_specs.jsonl")
        if pilot:
            specs = [spec for spec in specs if spec["spec_index"] % 5 == 0]
        domain_records = []
        for spec in specs:
            for seed in seeds:
                run = data_root / domain / METHOD / spec["spec_id"] / f"seed_{seed}"
                manifest_path = run / "run_manifest.json"
                if not manifest_path.exists():
                    problems.append(f"missing manifest: {run}")
                    continue
                manifest = json.loads(manifest_path.read_text())
                key = f"{domain}/{spec['spec_id']}/seed_{seed}"
                local = []
                if manifest.get("method") != METHOD or manifest.get("domain") != domain:
                    local.append("method/domain mismatch")
                if manifest.get("model_requested") != "gemini-3.1-pro-high":
                    local.append("wrong requested model")
                if (
                    manifest.get("auth_mode")
                    != "google_ai_pro_account_via_antigravity_no_api_key"
                ):
                    local.append("wrong authentication mode")
                cleared = manifest.get("api_key_environment_cleared")
                if cleared not in (
                    ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
                    ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL"],
                ):
                    local.append("API-key environment clearing not recorded")
                identity = manifest.get("identity", {})
                helper_hash = identity.get("client_helper_sha256")
                if helper_hash not in allowed_helper_hashes:
                    local.append("helper hash mismatch")
                elif helper_hash == current_helper[1]:
                    if identity.get("protocol_sha256") != digest(
                        (
                            ROOT
                            / "methods/gemini/protocol/generation/gemini_3_1_pro.json"
                        )
                    ):
                        local.append("current protocol hash mismatch")
                    if identity.get("adapter_sha256") != digest(
                        (ROOT / "methods/gemini/adapter.py")
                    ):
                        local.append("current adapter hash mismatch")
                else:
                    legacy = config["legacy_run_identity"]
                    for field in (
                        "protocol_sha256",
                        "adapter_sha256",
                        "client_helper_sha256",
                    ):
                        if identity.get(field) != legacy[field]:
                            local.append("legacy identity mismatch: " + field)
                for attempt in manifest.get("attempts", []):
                    command = attempt.get("command")
                    if (
                        not isinstance(command, list)
                        or len(command) != 1
                        or command[0] not in allowed_helper_paths
                    ):
                        local.append("generation command bypassed frozen helper")
                    if attempt.get("auth_mode") != "account_subscription_no_api_key":
                        local.append("attempt authentication mismatch")
                    if (
                        command == [current_helper[0]]
                        and attempt.get("client_helper_sha256") != current_helper[1]
                    ):
                        local.append("current helper attempt lacks hash")
                success = (run / "SUCCESS").exists()
                quality = manifest.get("failure_class") == "quality"
                if success:
                    required = [
                        manifest.get("generation_success"),
                        manifest.get("build_success"),
                        manifest.get("render_success"),
                        (run / "scene/generated.py").exists(),
                        (run / "scene/scene.blend").exists(),
                        (run / "validation.json").exists(),
                    ]
                    if not all(required):
                        local.append(
                            "SUCCESS lacks complete generation/build/render artifacts"
                        )
                    if len(list((run / "renders/anchors").glob("rgb_*.png"))) != 8:
                        local.append("wrong anchor count")
                    if len(list((run / "renders/sequence").glob("rgb_*.png"))) != 50:
                        local.append("wrong sequence count")
                elif not quality:
                    local.append("slot is not terminal SUCCESS or quality failure")
                if success and quality:
                    local.append("slot is both SUCCESS and quality failure")
                if local:
                    problems.extend(f"{key}: {item}" for item in local)
                record = {
                    "domain": domain,
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "success": success,
                    "quality_failure": quality,
                    "generation_success": bool(manifest.get("generation_success")),
                    "failure_reason": manifest.get("failure_reason"),
                    "problems": local,
                }
                records.append(record)
                domain_records.append(record)
        per_domain[domain] = {
            "expected": len(specs) * len(seeds),
            "terminal": sum(
                item["success"] or item["quality_failure"] for item in domain_records
            ),
            "success": sum(item["success"] for item in domain_records),
            "quality_failure": sum(item["quality_failure"] for item in domain_records),
        }
        if pilot:
            for spec in specs:
                if not any(
                    item["success"]
                    for item in domain_records
                    if item["spec_id"] == spec["spec_id"]
                ):
                    problems.append(
                        f"{domain}/{spec['spec_id']}: no successful pilot seed"
                    )
        if require_metrics:
            folder = (
                ROOT
                / "results/gemini_3_1_pro"
                / ("pilot" if pilot else "formal")
                / domain
            )
            expected_scene = len(specs) * len(seeds)
            for name in ("iqa_per_scene.jsonl", "consistency_per_scene.jsonl"):
                path = folder / name
                if not path.exists() or len(read_jsonl(path)) != expected_scene:
                    problems.append(f"{domain}: incomplete {name}")
            diversity = folder / "diversity_per_spec.jsonl"
            if not diversity.exists() or len(read_jsonl(diversity)) != len(specs):
                problems.append(f"{domain}: incomplete diversity_per_spec.jsonl")
    report = {
        "method": METHOD,
        "pilot": pilot,
        "data_root": str(data_root),
        "expected": sum(item["expected"] for item in per_domain.values()),
        "terminal": sum(item["terminal"] for item in per_domain.values()),
        "success": sum(item["success"] for item in per_domain.values()),
        "quality_failure": sum(item["quality_failure"] for item in per_domain.values()),
        "per_domain": per_domain,
        "problems": problems,
        "passed": not problems,
        "records": records,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--require-metrics", action="store_true")
    args = parser.parse_args()
    data_root = args.data_root or ROOT / (
        "data/gemini_3_1_pro_pilot" if args.pilot else "data/table2"
    )
    report = audit(data_root.resolve(), args.pilot, args.require_metrics)
    output = (
        ROOT
        / "results/gemini_3_1_pro"
        / ("pilot_audit.json" if args.pilot else "formal_audit.json")
    )
    write_json(output, report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "expected",
                    "terminal",
                    "success",
                    "quality_failure",
                    "passed",
                )
            },
            indent=2,
        )
    )
    if report["problems"]:
        print("\n".join(report["problems"][:30]))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
