#!/usr/bin/env python3
"""Audit Gemini 3.1 Pro generation, ratings and all seven Table-2 metrics."""
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
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
EXPECTED_VALID = {"indoor": 78, "urban": 76}
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str((ROOT / "evaluation/visual")))
from baselines.methods.gemini.tools.audit_gemini import (
    audit as audit_generation,
)  # noqa: E402
from baselines.evaluation.visual.aggregate_generation import DISPLAY_PRECISION
from baselines.evaluation.visual.aggregate_generation import METRIC_COLUMNS
from baselines.evaluation.visual.aggregate_generation import bootstrap_metrics
from baselines.evaluation.visual.aggregate_generation import group_scene_metric
from baselines.evaluation.visual.aggregate_generation import group_spec_metric


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


def main() -> int:
    lock_path = ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        actual = digest(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"Frozen hash mismatch: {relative}: {actual}")
    generation = audit_generation((ROOT / "data/table2").resolve(), False, True)
    if not generation["passed"] or generation["expected"] != 200:
        raise RuntimeError("Generation/metric provenance audit did not pass")
    if generation["success"] != 154 or generation["quality_failure"] != 46:
        raise RuntimeError("Unexpected formal terminal partition")

    report = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "full_chain_passed",
        "method": METHOD,
        "model": "gemini-3.1-pro-high",
        "transport": "Antigravity CLI with Google AI Pro account subscription",
        "api_key_billing_used": False,
        "formal_lock_sha256": digest(lock_path),
        "generation_audit": {
            key: generation[key]
            for key in ("expected", "terminal", "success", "quality_failure", "passed")
        },
        "domains": {},
    }
    for domain, expected_valid in EXPECTED_VALID.items():
        specs = jsonl(ROOT / f"protocol/generation/{domain}_specs.jsonl")
        spec_ids = [row["spec_id"] for row in specs]
        expected_keys = {(spec_id, seed) for spec_id in spec_ids for seed in range(4)}
        successes, quality = set(), set()
        for spec_id, seed in expected_keys:
            run = ROOT / "data/table2" / domain / METHOD / spec_id / f"seed_{seed}"
            manifest = json.loads((run / "run_manifest.json").read_text())
            if (run / "SUCCESS").exists():
                successes.add((spec_id, seed))
            elif manifest.get("failure_class") == "quality":
                quality.add((spec_id, seed))
            else:
                raise RuntimeError(f"Nonterminal run: {run}")
        if successes | quality != expected_keys or successes & quality:
            raise RuntimeError(f"Invalid terminal partition: {domain}")
        if len(successes) != expected_valid:
            raise RuntimeError(f"Unexpected valid-scene count: {domain}")

        result_root = ROOT / "results" / METHOD / "formal" / domain
        names_and_counts = {
            "iqa_per_scene.jsonl": 100,
            "consistency_per_scene.jsonl": 100,
            "human_per_scene.jsonl": 100,
            "diversity_per_spec.jsonl": 25,
        }
        rows = {}
        for name, expected_count in names_and_counts.items():
            rows[name] = jsonl(result_root / name)
            if len(rows[name]) != expected_count:
                raise RuntimeError(f"{domain}/{name}: wrong record count")
        for name in (
            "iqa_per_scene.jsonl",
            "consistency_per_scene.jsonl",
            "human_per_scene.jsonl",
        ):
            keys = {(row["spec_id"], int(row["logical_seed"])) for row in rows[name]}
            if keys != expected_keys or len(keys) != len(rows[name]):
                raise RuntimeError(f"{domain}/{name}: missing or duplicate scene")
            row_success = {
                (row["spec_id"], int(row["logical_seed"]))
                for row in rows[name]
                if row["success"]
            }
            if row_success != successes:
                raise RuntimeError(f"{domain}/{name}: success set mismatch")

        human = rows["human_per_scene.jsonl"]
        if any(
            row["rating_source"] != "synthetic_proxy_three_profiles" for row in human
        ):
            raise RuntimeError(f"Wrong subjective provenance: {domain}")
        if any(row["rater_count"] != (3 if row["success"] else 0) for row in human):
            raise RuntimeError(f"Wrong rater-count policy: {domain}")
        if any(
            row[metric] != 0.0
            for row in human
            if not row["success"]
            for metric in ("layout_plausibility", "prompt_alignment")
        ):
            raise RuntimeError(f"ITT subjective failure is not zero: {domain}")

        semantic = json.loads((result_root / "semantic_model.json").read_text())
        if semantic["generated"] != expected_valid * 8:
            raise RuntimeError(f"Incomplete semantic anchors: {domain}")
        if {row["spec_id"] for row in rows["diversity_per_spec.jsonl"]} != set(
            spec_ids
        ):
            raise RuntimeError(f"Incomplete diversity specs: {domain}")

        package = ROOT / "annotations" / METHOD / domain
        with (package / "items.csv").open(newline="", encoding="utf-8") as handle:
            items = list(csv.DictReader(handle))
        provenance = json.loads(
            (package / "SYNTHETIC_RATING_PROVENANCE.json").read_text()
        )
        if (
            len(items) != expected_valid
            or provenance["human_raters"] != 0
            or provenance["independent_human_ratings"] is not False
            or provenance["import_rating_source"] != "synthetic_proxy_three_profiles"
            or len(provenance["decisions"]) != expected_valid
        ):
            raise RuntimeError(f"Invalid rating provenance: {domain}")
        for name, expected in provenance["outputs_sha256"].items():
            if digest(package / name) != expected:
                raise RuntimeError(f"Rating output changed: {domain}/{name}")
        review_root = ROOT / "work" / METHOD / "synthetic_review"
        review_path = review_root / f"{domain}_review.txt"
        review_lock_path = review_root / f"{domain}_review.lock.json"
        review_lock = json.loads(review_lock_path.read_text())
        if review_lock["items_sha256"] != digest(package / "items.csv"):
            raise RuntimeError(f"Stale item lock: {domain}")
        if review_lock["review_sha256"] != digest(review_path):
            raise RuntimeError(f"Stale visual-review lock: {domain}")

        grouped = {
            "qalign": group_scene_metric(
                rows["iqa_per_scene.jsonl"], "qalign", spec_ids
            ),
            "clipiqa_plus": group_scene_metric(
                rows["iqa_per_scene.jsonl"], "clipiqa_plus", spec_ids
            ),
            "layout_plausibility": group_scene_metric(
                human, "layout_plausibility", spec_ids
            ),
            "prompt_alignment": group_scene_metric(human, "prompt_alignment", spec_ids),
            "consistency_3d": group_scene_metric(
                rows["consistency_per_scene.jsonl"], "consistency_3d", spec_ids
            ),
            "appearance_diversity_itt": group_spec_metric(
                rows["diversity_per_spec.jsonl"], "appearance_diversity_itt", spec_ids
            ),
            "layout_diversity_itt": group_spec_metric(
                rows["diversity_per_spec.jsonl"], "layout_diversity_itt", spec_ids
            ),
        }
        recomputed = bootstrap_metrics(grouped, spec_ids, 20260827)
        full = json.loads((result_root / "table2_full.json").read_text())
        if full["bootstrap"] != {
            "unit": "spec_id",
            "replicates": 10000,
            "seed": 20260827,
        }:
            raise RuntimeError(f"Wrong bootstrap configuration: {domain}")
        for metric in METRIC_COLUMNS:
            actual, expected = full["metrics"][metric], recomputed[metric]
            if actual["status"] != "complete" or actual["spec_count"] != 25:
                raise RuntimeError(f"Incomplete aggregate: {domain}/{metric}")
            if not close(actual["mean"], expected["mean"]) or any(
                not close(left, right)
                for left, right in zip(actual["ci95"], expected["ci95"])
            ):
                raise RuntimeError(f"Aggregate mismatch: {domain}/{metric}")

        csv_rows = list(csv.DictReader((result_root / "table2.csv").open()))
        if len(csv_rows) != 1 or csv_rows[0]["method"] != METHOD:
            raise RuntimeError(f"Invalid Table-2 CSV: {domain}")
        for metric in METRIC_COLUMNS:
            displayed = f"{recomputed[metric]['mean']:.{DISPLAY_PRECISION[metric]}f}"
            if csv_rows[0][metric] != displayed:
                raise RuntimeError(f"Display rounding mismatch: {domain}/{metric}")
        if csv_rows[0]["render_success_rate"] != f"{expected_valid / 100:.4f}":
            raise RuntimeError(f"Success-rate mismatch: {domain}")

        success_only = json.loads(
            (result_root / "table2_success_only.json").read_text()
        )
        if success_only["metric_successful_runs"] != expected_valid:
            raise RuntimeError(f"Successful-scene report mismatch: {domain}")
        report["domains"][domain] = {
            "formal_runs": 100,
            "valid": expected_valid,
            "quality_failures": 100 - expected_valid,
            "render_success_rate": expected_valid / 100,
            "semantic_anchors": semantic["generated"],
            "annotation_items": len(items),
            "real_human_raters": 0,
            "rating_source": "synthetic_proxy_three_profiles",
            "metrics": {
                metric: full["metrics"][metric]["mean"] for metric in METRIC_COLUMNS
            },
            "ci95": {
                metric: full["metrics"][metric]["ci95"] for metric in METRIC_COLUMNS
            },
            "success_only": success_only,
            "sha256": {
                name: digest(result_root / name)
                for name in (
                    "iqa_per_scene.jsonl",
                    "consistency_per_scene.jsonl",
                    "diversity_per_spec.jsonl",
                    "human_per_scene.jsonl",
                    "table2.csv",
                    "table2_full.json",
                    "table2_success_only.json",
                )
            },
        }

    output = ROOT / "results" / METHOD / "final_audit.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
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
