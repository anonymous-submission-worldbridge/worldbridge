#!/usr/bin/env python3
"""Seal the two audited GPT-6 Astra Low Table 2 rows and their original sources."""
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
import json
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str((ROOT / "methods"))]
from baselines.methods.gpt.adapter_low import digest
from baselines.methods.gpt.adapter_low import utc
from baselines.methods.gpt.adapter_low import write_json
from baselines.methods.gpt.run_low_metrics import verify_evaluation_lock

METHOD = "gpt6_astra_low"
METRICS = (
    "qalign",
    "clipiqa_plus",
    "layout_plausibility",
    "prompt_alignment",
    "consistency_3d",
    "appearance_diversity_itt",
    "layout_diversity_itt",
)
REQUIRED_ARTIFACTS = (
    "table2_full.json",
    "table2.csv",
    "iqa_per_scene.jsonl",
    "consistency_per_scene.jsonl",
    "human_per_scene.jsonl",
    "diversity_per_spec.jsonl",
    "table2_success_only.json",
)


def main() -> int:
    admitted_equivalents = verify_evaluation_lock()
    output = ROOT / "results/gpt6_astra_low/method.lock.json"
    if output.exists():
        raise RuntimeError("Completed method seal already exists; refusing overwrite")
    config = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
    )
    if config["reasoning_effort"] != "low" or config["model"] != "gpt-6-astra":
        raise RuntimeError("Method identity changed")
    document = (ROOT / "Comparison Experiment - Table 2.md").read_text()
    domains, artifacts = {}, {}
    for domain, label in (("indoor", "Indoor"), ("urban", "Urban")):
        folder = ROOT / "results/gpt6_astra_low/formal" / domain
        summary = json.loads((folder / "table2_full.json").read_text())
        if any(
            summary["metrics"][metric]["status"] != "complete" for metric in METRICS
        ):
            raise RuntimeError("Seven completed formal metrics required: " + domain)
        with (folder / "table2.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise RuntimeError("Exactly one official Table 2 row required")
        display = rows[0]
        expected = [
            display[metric]
            + ("⁵" if metric in ("layout_plausibility", "prompt_alignment") else "")
            for metric in METRICS
        ]
        row = f"| GPT-6 Astra Low ({label}) | " + " | ".join(expected) + " |"
        if document.count(row) != 1:
            raise RuntimeError(
                "Official markdown row does not match audited CSV: " + domain
            )
        supplementary = json.loads((folder / "table2_success_only.json").read_text())
        diagnostic_row = (
            f"| GPT-6 Astra Low ({label}) | {supplementary['metric_successful_runs']} | {supplementary['valid_diversity_specs']} | "
            + " | ".join(supplementary["display"])
            + " |"
        )
        if document.count(diagnostic_row) != 1:
            raise RuntimeError(
                "Supplementary successful-scene row does not match its sources: "
                + domain
            )
        audit_path = ROOT / "results/gpt6_astra_low" / f"chain_audit_{domain}.json"
        audit = json.loads(audit_path.read_text())
        if audit.get("status") != "full_chain_passed" or audit.get(
            "summary_sources_sha256", {}
        ).get("table2_full.json") != digest(folder / "table2_full.json"):
            raise RuntimeError("Audit stale or incomplete: " + domain)
        if audit.get("display_row") != display:
            raise RuntimeError("Table 2 display diverges from audit: " + domain)
        provenance_path = (
            ROOT
            / "annotations/gpt6_astra_low"
            / domain
            / "SYNTHETIC_RATING_PROVENANCE.json"
        )
        provenance = json.loads(provenance_path.read_text())
        if provenance.get("human_raters") != 0 or audit.get(
            "provenance_sha256"
        ) != digest(provenance_path):
            raise RuntimeError("Rating source stale or misidentified: " + domain)
        if (
            audit.get("expected_runs") != 100
            or audit.get("quality_failures") + audit.get("valid_runs") != 100
        ):
            raise RuntimeError("Incomplete ITT matrix: " + domain)
        domains[domain] = {
            "display_row": display,
            "run_audit": summary["run_audit"],
            "valid_runs": audit["valid_runs"],
            "quality_failures": audit["quality_failures"],
            "metrics": summary["metrics"],
            "visual_reviews": provenance["scored_scenes"],
        }
        for name in REQUIRED_ARTIFACTS:
            path = folder / name
            artifacts[str(path.relative_to(ROOT))] = digest(path)
        for path in (audit_path, provenance_path):
            artifacts[str(path.relative_to(ROOT))] = digest(path)
    operational = json.loads(
        (ROOT / "results/gpt6_astra_low/chain_audit_urban.json").read_text()
    )["operational_amendments_sha256"]
    for filename, expected in operational.items():
        if digest((ROOT / "protocol/generation") / filename) != expected:
            raise RuntimeError(
                "Operational recovery source changed after audit: " + filename
            )
    report = {
        "sealed_at_utc": utc(),
        "status": "both_domains_seven_metrics_verified_and_table_filled",
        "method": METHOD,
        "display_name": config["display_name"],
        "model_requested": config["model"],
        "reasoning_effort": config["reasoning_effort"],
        "transport": config["transport"],
        "model_snapshot_limitation": config["api_seed_note"],
        "remote_weights_not_downloaded": True,
        "real_human_raters": 0,
        "subjective_rating_source": "synthetic_proxy_three_profiles",
        "subjective_limitations": "One montage review and three deterministic rating profiles; no human blind ratings, independent model calls or continuous video review.",
        "frozen_protocol_sha256": digest(
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")
        ),
        "frozen_lock_sha256": digest(
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json")
        ),
        "admitted_equivalent_evaluators": admitted_equivalents,
        "operational_amendments_sha256": operational,
        "domains": domains,
        "artifacts_sha256": artifacts,
        "table_document_sha256": digest(ROOT / "Comparison Experiment - Table 2.md"),
        "sealer_sha256": digest(__file__),
    }
    write_json(output, report)
    print("SEALED", output, "sha256", digest(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
