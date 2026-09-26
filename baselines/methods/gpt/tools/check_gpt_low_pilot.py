#!/usr/bin/env python3
"""Verify the Astra Low pilot, metrics sanity, and parity with Astra High."""

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
from pathlib import Path

from baselines.methods.gpt.tools.audit_gpt_low import audit

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    low = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
    )
    high = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    high_lock = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json")).read_text()
    )
    parity_fields = [
        "model",
        "transport",
        "codex_version",
        "generation_timeout_s",
        "build_timeout_s",
        "build_workers",
        "domains",
        "spec_files",
        "seeds_file",
        "pilot_specs_per_domain",
        "pilot_seeds",
        "formal_specs_per_domain",
        "formal_seeds",
        "api_seed_supported",
        "max_output_tokens",
        "max_retries_infrastructure",
        "min_render_free_mib",
        "retry_quality_failures",
        "generation_weights",
        "formal_data_root",
        "metrics_lock",
        "blender_executable",
        "metrics_python",
        "camera",
        "render_timeout_s",
        "build_threads",
        "render_threads",
        "iqa_batch_size",
    ]
    mismatches = [field for field in parity_fields if low.get(field) != high.get(field)]
    if mismatches:
        raise RuntimeError(
            "Astra Low differs from High in experimental fields: "
            + ", ".join(mismatches)
        )
    if low.get("reasoning_effort") != "low" or high.get("reasoning_effort") != "high":
        raise RuntimeError("Reasoning-effort identity is wrong")
    frozen_equivalents = {
        "evaluation/visual/eval_worldscore_gpt_high_frozen.py": high_lock[
            "files_sha256"
        ]["evaluation/visual/eval_worldscore.py"],
        "methods/gpt/tools/make_annotation_package_gpt_high_frozen.py": high_lock[
            "files_sha256"
        ]["tools/make_annotation_package.py"],
    }
    for relative, expected in frozen_equivalents.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError("High frozen equivalent mismatch: " + relative)
    probe_reports = sorted(
        (ROOT / "results/gpt6_astra_low/codex_probe").glob("attempt_*/report.json")
    )
    if not probe_reports:
        raise RuntimeError("No Astra Low connectivity probe")
    probe = json.loads(probe_reports[-1].read_text())
    if (
        not probe.get("success")
        or probe.get("model_requested") != "gpt-6-astra"
        or probe.get("reasoning_effort") != "low"
    ):
        raise RuntimeError(
            "Latest Astra Low probe did not validate the requested transport"
        )
    report = audit(ROOT / "data/gpt6_astra_low_pilot", True)
    if report["expected"] != 20 or set(report["counts"]) - {"valid", "quality"}:
        raise RuntimeError(
            "Pilot matrix is not terminal: " + json.dumps(report["counts"])
        )
    valid_by_domain = {
        domain: sum(
            row["domain"] == domain and row["status"] == "valid"
            for row in report["records"]
        )
        for domain in ("indoor", "urban")
    }
    metric_summary = {}
    for domain in ("indoor", "urban"):
        root = ROOT / "results/gpt6_astra_low/pilot" / domain
        iqa = rows(root / "iqa_per_scene.jsonl")
        consistency = rows(root / "consistency_per_scene.jsonl")
        diversity = rows(root / "diversity_per_spec.jsonl")
        semantics = json.loads((root / "semantic_model.json").read_text())
        if len(iqa) != 10 or len(consistency) != 10 or len(diversity) != 5:
            raise RuntimeError(f"Incomplete {domain} pilot metric records")
        if sum(bool(row["success"]) for row in iqa) != valid_by_domain[domain]:
            raise RuntimeError(f"IQA success count does not match {domain} pilot")
        if semantics.get("generated") != valid_by_domain[domain] * 8:
            raise RuntimeError(f"Semantic-map count does not match {domain} pilot")
        if not all(
            row["method"] == "gpt6_astra_low" and row["domain"] == domain
            for row in iqa + consistency + diversity
        ):
            raise RuntimeError("Foreign method/domain in pilot metrics")
        if not any(row["valid_pair_count"] > 0 for row in diversity):
            raise RuntimeError(f"No real cross-seed diversity pair for {domain}")
        metric_summary[domain] = {
            "valid": valid_by_domain[domain],
            "iqa_records": len(iqa),
            "consistency_records": len(consistency),
            "semantic_maps": semantics["generated"],
            "diversity_specs": len(diversity),
        }
    print(
        json.dumps(
            {
                "status": "pilot_validated",
                "reasoning_effort": "low",
                "high_parity_fields": len(parity_fields),
                "high_frozen_equivalents": len(frozen_equivalents),
                "matrix_counts": report["counts"],
                "metrics": metric_summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
