#!/usr/bin/env python3
"""Audit the complete formal GLM-5.3 Flash Table-2 result chain."""
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


from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "glm53_flash"
EXPECTED_VALID = {"indoor": 44, "urban": 30}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    lock = json.loads(
        (
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash.lock.json")
        ).read_text()
    )
    for relative, expected in lock["files_sha256"].items():
        actual = digest(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"Frozen hash mismatch: {relative}: {actual}")

    model_audit = json.loads(
        (ROOT / "results/glm53_flash/formal_audit.json").read_text()
    )
    if (
        model_audit["expected"] != 200
        or model_audit["counts"] != {"quality": 126, "valid": 74}
        or model_audit["generated"] != 108
        or model_audit["built"] != 74
        or model_audit["verified_model_evidence"] != 108
    ):
        raise RuntimeError(
            "Generation/model-evidence audit is not the expected formal terminal state"
        )

    report = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "full_chain_passed",
        "method": METHOD,
        "model": "glm-coding-plan/glm-5.3-flash",
        "formal_lock_sha256": digest(
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash.lock.json")
        ),
        "model_evidence": {
            "generated": model_audit["generated"],
            "built": model_audit["built"],
            "verified_exact_provider_model": model_audit["verified_model_evidence"],
            "reasoning_tokens": model_audit["reasoning_tokens"],
        },
        "domains": {},
    }
    for domain, expected_valid in EXPECTED_VALID.items():
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if line
        ]
        expected_keys = {(row["spec_id"], seed) for row in specs for seed in range(4)}
        successes = set()
        quality = set()
        for spec_id, seed in sorted(expected_keys):
            run = ROOT / "data/table2" / domain / METHOD / spec_id / f"seed_{seed}"
            manifest_path = run / "run_manifest.json"
            if not manifest_path.exists():
                raise RuntimeError(f"Missing manifest: {run}")
            manifest = json.loads(manifest_path.read_text())
            if (run / "SUCCESS").exists():
                successes.add((spec_id, seed))
            elif manifest.get("failure_class") == "quality":
                quality.add((spec_id, seed))
            else:
                raise RuntimeError(f"Nonterminal formal run: {run}")
        if successes | quality != expected_keys or successes & quality:
            raise RuntimeError(f"Invalid terminal partition for {domain}")
        if len(successes) != expected_valid:
            raise RuntimeError(f"Unexpected success count for {domain}")

        result_root = ROOT / "results/glm53_flash/formal" / domain
        names_and_counts = {
            "iqa_per_scene.jsonl": 100,
            "consistency_per_scene.jsonl": 100,
            "human_per_scene.jsonl": 100,
            "diversity_per_spec.jsonl": 25,
        }
        rows_by_name = {}
        for name, expected_count in names_and_counts.items():
            rows = jsonl(result_root / name)
            if len(rows) != expected_count:
                raise RuntimeError(f"{domain}/{name}: {len(rows)} != {expected_count}")
            rows_by_name[name] = rows

        for name in (
            "iqa_per_scene.jsonl",
            "consistency_per_scene.jsonl",
            "human_per_scene.jsonl",
        ):
            rows = rows_by_name[name]
            keys = {(row["spec_id"], int(row["logical_seed"])) for row in rows}
            if keys != expected_keys or len(keys) != len(rows):
                raise RuntimeError(f"Incomplete or duplicate {domain}/{name}")
            row_successes = {
                (row["spec_id"], int(row["logical_seed"]))
                for row in rows
                if row["success"]
            }
            if row_successes != successes:
                raise RuntimeError(f"Success set mismatch in {domain}/{name}")

        human_rows = rows_by_name["human_per_scene.jsonl"]
        if any(
            row["rating_source"] != "synthetic_proxy_three_profiles"
            for row in human_rows
        ):
            raise RuntimeError(f"Wrong subjective provenance for {domain}")
        if any(
            row["rater_count"] != (3 if row["success"] else 0) for row in human_rows
        ):
            raise RuntimeError(f"Wrong rater-count policy for {domain}")

        semantic = json.loads((result_root / "semantic_model.json").read_text())
        if semantic["generated"] != expected_valid * 8:
            raise RuntimeError(f"Incomplete semantic anchors for {domain}")
        diversity_specs = {
            row["spec_id"] for row in rows_by_name["diversity_per_spec.jsonl"]
        }
        if diversity_specs != {row["spec_id"] for row in specs}:
            raise RuntimeError(f"Incomplete diversity specs for {domain}")

        package = ROOT / "annotations/glm53_flash" / domain
        with (package / "items.csv").open(newline="", encoding="utf-8") as handle:
            items = list(csv.DictReader(handle))
        provenance = json.loads(
            (package / "SYNTHETIC_RATING_PROVENANCE.json").read_text()
        )
        if len(items) != expected_valid or provenance["human_raters"] != 0:
            raise RuntimeError(f"Invalid annotation provenance for {domain}")
        review_root = ROOT / "work/glm53_flash/synthetic_review"
        review_path = review_root / f"{domain}_review.txt"
        review_lock_path = review_root / f"{domain}_review.lock.json"
        review_lock = json.loads(review_lock_path.read_text())
        if review_lock["items_sha256"] != digest(package / "items.csv"):
            raise RuntimeError(f"Stale item lock for {domain}")
        if review_lock["review_sha256"] != digest(review_path):
            raise RuntimeError(f"Stale review lock for {domain}")

        full = json.loads((result_root / "table2_full.json").read_text())
        if set(full["metrics"]) != {
            "qalign",
            "clipiqa_plus",
            "layout_plausibility",
            "prompt_alignment",
            "consistency_3d",
            "appearance_diversity_itt",
            "layout_diversity_itt",
        }:
            raise RuntimeError(f"Metric set mismatch for {domain}")
        for metric, payload in full["metrics"].items():
            if payload["status"] != "complete" or payload["spec_count"] != 25:
                raise RuntimeError(f"Incomplete aggregate: {domain}/{metric}")
            if not math.isfinite(float(payload["mean"])) or not all(
                math.isfinite(float(x)) for x in payload["ci95"]
            ):
                raise RuntimeError(f"Non-finite aggregate: {domain}/{metric}")

        csv_rows = list(csv.DictReader((result_root / "table2.csv").open()))
        if (
            len(csv_rows) != 1
            or csv_rows[0]["method"] != METHOD
            or csv_rows[0]["domain"] != domain
        ):
            raise RuntimeError(f"Invalid Table-2 CSV for {domain}")
        report["domains"][domain] = {
            "formal_runs": 100,
            "valid": len(successes),
            "quality_failures": len(quality),
            "render_success_rate": len(successes) / 100,
            "semantic_anchors": semantic["generated"],
            "objective_rows": {name: len(rows) for name, rows in rows_by_name.items()},
            "annotation_items": len(items),
            "human_raters": provenance["human_raters"],
            "rating_source": provenance["rating_source"],
            "metrics": {
                name: payload["mean"] for name, payload in full["metrics"].items()
            },
            "ci95": {
                name: payload["ci95"] for name, payload in full["metrics"].items()
            },
            "sha256": {
                name: digest(result_root / name)
                for name in (
                    "iqa_per_scene.jsonl",
                    "consistency_per_scene.jsonl",
                    "diversity_per_spec.jsonl",
                    "human_per_scene.jsonl",
                    "table2.csv",
                    "table2_full.json",
                )
            },
        }

    output = ROOT / "results/glm53_flash/final_audit.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "indoor_valid": report["domains"]["indoor"]["valid"],
                "urban_valid": report["domains"]["urban"]["valid"],
                "metrics_per_domain": len(report["domains"]["indoor"]["metrics"]),
                "output": str(output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
