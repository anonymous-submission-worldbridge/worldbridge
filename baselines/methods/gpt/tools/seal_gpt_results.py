#!/usr/bin/env python3
"""Seal completed Astra-only results after both independent audits and MD edit."""

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

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE / "tools"), str((BASE / "methods"))]
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json

METRICS = (
    "qalign",
    "clipiqa_plus",
    "layout_plausibility",
    "prompt_alignment",
    "consistency_3d",
    "appearance_diversity_itt",
    "layout_diversity_itt",
)


def main():
    verify_lock()
    output = BASE / "results/gpt6_astra/method.lock.json"
    if output.exists():
        raise RuntimeError("Final seal already exists; refusing overwrite")
    frozen = json.loads(
        ((BASE / "methods/gpt/protocol/generation/gpt6_astra.lock.json")).read_text()
    )
    config = json.loads(
        ((BASE / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    document = (BASE / "Comparison Experiment - Table 2.md").read_text()
    domains, artifacts = {}, {}
    for domain in ("indoor", "urban"):
        folder = BASE / "results/gpt6_astra/formal" / domain
        full = json.loads((folder / "table2_full.json").read_text())
        if any(full["metrics"][m]["status"] != "complete" for m in METRICS):
            raise RuntimeError("Seven complete metrics required")
        with (folder / "table2.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise RuntimeError("Single result row required")
        row = rows[0]
        label = "Indoor" if domain == "indoor" else "Urban"
        expected = [
            row[m] + ("¹" if m in ("layout_plausibility", "prompt_alignment") else "")
            for m in METRICS
        ]
        expected_line = "| GPT-6 Astra (" + label + ") | " + " | ".join(expected) + " |"
        if document.count(expected_line) != 1:
            raise RuntimeError("Markdown row does not match verified CSV: " + domain)
        for name in (
            "chain_audit_" + domain + ".json",
            "synthetic_rating_audit_" + domain + ".json",
        ):
            path = BASE / "results/gpt6_astra" / name
            report = json.loads(path.read_text())
            expected_hash = report.get(
                "summary_sha256",
                report.get("summary_sources_sha256", {}).get("table2_full.json"),
            )
            if expected_hash != digest(folder / "table2_full.json"):
                raise RuntimeError("Audit refers to stale summary")
            artifacts[str(path.relative_to(BASE))] = digest(path)
        package = BASE / "annotations/gpt6_astra" / domain
        provenance = json.loads(
            (package / "SYNTHETIC_RATING_PROVENANCE.json").read_text()
        )
        if provenance["human_raters"] != 0:
            raise RuntimeError("Unexpected human provenance")
        domains[domain] = dict(
            display_row=row,
            run_audit=full["run_audit"],
            metrics=full["metrics"],
            actual_visual_reviews=provenance["scored_scenes"],
        )
        for path in [
            folder / f
            for f in (
                "table2_full.json",
                "table2.csv",
                "iqa_per_scene.jsonl",
                "consistency_per_scene.jsonl",
                "diversity_per_spec.jsonl",
                "human_per_scene.jsonl",
            )
        ]:
            artifacts[str(path.relative_to(BASE))] = digest(path)
        for name in (
            "items.csv",
            "PRIVATE_blind_map.json",
            "layout_ratings.csv",
            "prompt_ratings.csv",
            "SYNTHETIC_RATING_PROVENANCE.json",
        ):
            artifacts[str((package / name).relative_to(BASE))] = digest(package / name)
    amendments = [
        "gpt6_astra_rating_amendment_20260909.json",
        "gpt6_astra_render_amendment_20260909.json",
        "gpt6_astra_interruption_recovery_20260909.json",
    ]
    amendment_hashes = {
        "protocol/" + name: digest((BASE / "protocol/generation") / name)
        for name in amendments
    }
    authorized = json.loads(
        ((BASE / "protocol/generation") / amendments[-1]).read_text()
    )
    recovery = BASE / "results/gpt6_astra/urban_interruption_recovery_20260909"
    for target in authorized["targets"]:
        run = BASE / "data/table2/urban/gpt6_astra" / target
        current = json.loads((run / "run_manifest.json").read_text())
        prior = json.loads(
            (recovery / "previous" / target / "run_manifest.json").read_text()
        )
        attempts = current["render_attempts"]
        if (
            len(attempts) != 5
            or attempts[:4] != prior["render_attempts"]
            or not attempts[-1].get("ended_at_utc")
        ):
            raise RuntimeError("Recovery did not preserve all four original attempts")
        if attempts[-1]["resource_amendment"] != "protocol/" + amendments[-1]:
            raise RuntimeError("Recovery authorization mismatch")
        artifacts[str((run / "run_manifest.json").relative_to(BASE))] = digest(
            run / "run_manifest.json"
        )
    result = dict(
        sealed_at_utc=utc(),
        status="both_domains_seven_metrics_verified_and_table_filled",
        method="gpt6_astra",
        display_name="GPT-6 Astra",
        definition=config["method_definition"],
        transport=config["transport"],
        model_requested=config["model"],
        codex_version=config["codex_version"],
        remote_weights_not_downloaded=True,
        model_snapshot_limitation=config["api_seed_note"],
        original_frozen_lock_sha256=digest(
            (BASE / "methods/gpt/protocol/generation/gpt6_astra.lock.json")
        ),
        original_frozen_sources_sha256=frozen["files_sha256"],
        amendments_sha256=amendment_hashes,
        real_human_raters=0,
        subjective_rating_source="synthetic_proxy_three_profiles",
        subjective_limitations="Single assistant montage review, three deterministic profiles; not real blind human ratings, not independent model calls, no continuous video review.",
        domains=domains,
        artifacts_sha256=artifacts,
        table_document_sha256=digest(BASE / "Comparison Experiment - Table 2.md"),
        sealer_sha256=digest(__file__),
    )
    write_json(output, result)
    print("SEALED", str(output), "sha256", digest(output))


if __name__ == "__main__":
    main()
