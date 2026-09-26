#!/usr/bin/env python3
"""Verify the GLM-5.3 Flash pilot and offline metric sanity."""
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
from pathlib import Path
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.glm_flash.tools.audit_glm_flash import audit


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    config = json.loads(
        ((ROOT / "methods/glm_flash/protocol/generation/glm53_flash.json")).read_text()
    )
    if config.get("model") != "glm-5.3-flash":
        raise RuntimeError("Wrong target model")
    if (
        config.get("thinking") != {"type": "disabled"}
        or config.get("reasoning_effort") != "none"
    ):
        raise RuntimeError("No-thinking request is not frozen")
    report = audit(ROOT / "data/glm53_flash_pilot", True)
    if report["expected"] != 20 or set(report["counts"]) - {"valid", "quality"}:
        raise RuntimeError(
            "Pilot matrix is not terminal: " + json.dumps(report["counts"])
        )
    if report["verified_model_evidence"] != report["generated"]:
        raise RuntimeError("Every generated scene needs exact provider/model evidence")
    valid_by_domain = {
        domain: sum(
            row["domain"] == domain and row["status"] == "valid"
            for row in report["records"]
        )
        for domain in ("indoor", "urban")
    }
    metric_summary = {}
    for domain in ("indoor", "urban"):
        root = ROOT / "results/glm53_flash/pilot" / domain
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
            row["method"] == "glm53_flash" and row["domain"] == domain
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
                "request_thinking": config["thinking"],
                "request_reasoning_effort": config["reasoning_effort"],
                "actual_reasoning_tokens": report["reasoning_tokens"],
                "matrix_counts": report["counts"],
                "metrics": metric_summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
