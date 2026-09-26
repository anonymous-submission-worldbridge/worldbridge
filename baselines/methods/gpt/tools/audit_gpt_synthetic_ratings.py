#!/usr/bin/env python3
"""Independently recompute proxy CSV, ITT means and clustered confidence limits."""

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
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from baselines.methods.gpt.tools.fill_simulated_gpt_ratings import BASE
from baselines.methods.gpt.tools.fill_simulated_gpt_ratings import digest


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    args = parser.parse_args()
    package = BASE / "annotations/gpt6_astra" / args.domain
    results = BASE / "results/gpt6_astra/formal" / args.domain
    provenance = json.loads((package / "SYNTHETIC_RATING_PROVENANCE.json").read_text())
    check(
        provenance["human_raters"] == 0
        and provenance["independent_human_ratings"] is False,
        "False human provenance",
    )
    for name, expected in provenance["outputs_sha256"].items():
        check(digest(package / name) == expected, "Rating CSV hash mismatch")
    check(digest(package / "items.csv") == provenance["items_sha256"], "Items drift")
    items = {row["blind_id"]: row for row in csv_rows(package / "items.csv")}
    layout = csv_rows(package / "layout_ratings.csv")
    prompt = csv_rows(package / "prompt_ratings.csv")
    check(len(layout) == 3 * len(items), "Layout row count")
    check(
        len(prompt) == 3 * sum(int(row["fact_count"]) for row in items.values()),
        "Prompt row count",
    )
    fields = (
        "boundary_collision",
        "support_pose",
        "scale_density",
        "function_circulation",
    )
    decisions = {row["blind_id"]: row for row in provenance["decisions"]}
    check(
        len(decisions) == len(items) and set(decisions) == set(items),
        "Incomplete visual reviews",
    )
    for blind_id, item in items.items():
        decision = decisions[blind_id]
        check(
            digest(package / item["montage"]) == decision["montage_sha256"],
            "Reviewed image drift",
        )
        check(
            digest(BASE / decision["review_sheet"]) == decision["review_sheet_sha256"],
            "Review sheet drift",
        )
        facts = json.loads(item["required_facts_json"])
        check(facts == decision["facts"], "Fact text drift")
        for p in range(3):
            rater = f"sim_rater_{p+1:02d}"
            rows = [
                r
                for r in layout
                if r["blind_id"] == blind_id and r["rater_id"] == rater
            ]
            check(len(rows) == 1, "Missing/duplicate layout profile")
            expected = decision["neutral_layout"][:]
            dimension = (decision["item_number"] - 1) % 4
            expected[dimension] = min(5, max(1, expected[dimension] + p - 1))
            check(
                [int(rows[0][field]) for field in fields] == expected,
                "Wrong profile perturbation",
            )
            responses = [
                r
                for r in prompt
                if r["blind_id"] == blind_id and r["rater_id"] == rater
            ]
            check(
                len(responses) == len(facts)
                and {int(r["fact_index"]) for r in responses} == set(range(len(facts))),
                "Incomplete fact coverage",
            )
            for row in responses:
                i = int(row["fact_index"])
                expected_response = (
                    "yes"
                    if i in decision["clear_yes_fact_indices"]
                    else (
                        ("no", "not-visible", "yes")[p]
                        if i in decision["borderline_fact_indices"]
                        else "no"
                    )
                )
                check(
                    row["response"] == expected_response and row["fact"] == facts[i],
                    "Wrong fact decision",
                )
    records = [
        json.loads(line)
        for line in (results / "human_per_scene.jsonl").read_text().splitlines()
    ]
    specs = [
        json.loads(line)["spec_id"]
        for line in (BASE / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    expected_slots = {(sid, seed) for sid in specs for seed in range(4)}
    check(
        len(records) == 100
        and {(r["spec_id"], r["logical_seed"]) for r in records} == expected_slots,
        "Invalid formal matrix",
    )
    private = {
        r["blind_id"]: r
        for r in json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    }
    for record in records:
        check(
            record["rating_source"] == "synthetic_proxy_three_profiles",
            "Missing proxy source label",
        )
        check(
            record["method"] == "gpt6_astra" and record["domain"] == args.domain,
            "Foreign record",
        )
        mapped = private[record["blind_id"]]
        check(record["success"] == mapped["success"], "Success mapping mismatch")
        if not record["success"]:
            check(
                record["layout_plausibility"]
                == record["prompt_alignment"]
                == record["rater_count"]
                == 0,
                "Invalid failure ITT",
            )
            continue
        decision = decisions[record["blind_id"]]
        values = []
        for p in range(3):
            vector = decision["neutral_layout"][:]
            d = (decision["item_number"] - 1) % 4
            vector[d] = min(5, max(1, vector[d] + p - 1))
            values.append(25 * (sum(vector) / 4 - 1))
        fact_count = len(decision["facts"])
        prompt_values = [
            100
            * (
                len(decision["clear_yes_fact_indices"])
                + (len(decision["borderline_fact_indices"]) if p == 2 else 0)
            )
            / fact_count
            for p in range(3)
        ]
        check(
            np.allclose(record["layout_per_rater"], values, rtol=0, atol=1e-10),
            "Layout import mismatch",
        )
        check(
            np.allclose(record["prompt_per_rater"], prompt_values, rtol=0, atol=1e-10),
            "Prompt import mismatch",
        )
        check(
            abs(record["layout_plausibility"] - np.mean(values)) < 1e-10
            and abs(record["prompt_alignment"] - np.mean(prompt_values)) < 1e-10,
            "Per-scene mean mismatch",
        )
    full = json.loads((results / "table2_full.json").read_text())
    display = csv_rows(results / "table2.csv")[0]
    for metric in ("layout_plausibility", "prompt_alignment"):
        array = np.array(
            [
                np.mean([r[metric] for r in records if r["spec_id"] == sid])
                for sid in specs
            ]
        )
        indices = np.random.default_rng(20260827).integers(0, 25, size=(10000, 25))
        ci = np.quantile(array[indices].mean(axis=1), [0.025, 0.975])
        summary = full["metrics"][metric]
        check(
            summary["status"] == "complete"
            and abs(summary["mean"] - array.mean()) < 1e-10,
            "Final proxy mean mismatch",
        )
        check(
            np.allclose(ci, summary["ci95"], rtol=0, atol=1e-10),
            "Proxy bootstrap mismatch",
        )
        check(display[metric] == f"{array.mean():.1f}", "Proxy CSV rounding mismatch")
    previous = (
        BASE
        / "results/gpt6_astra/rating_revision_20260909"
        / args.domain
        / "previous/table2_full.json"
    )
    if previous.exists():
        original = json.loads(previous.read_text())
        for metric in (
            "qalign",
            "clipiqa_plus",
            "consistency_3d",
            "appearance_diversity_itt",
            "layout_diversity_itt",
        ):
            check(
                original["metrics"][metric] == full["metrics"][metric],
                "Automatic metric changed during subjective import",
            )
    report = dict(
        status="synthetic_rating_chain_passed",
        domain=args.domain,
        verified_at_utc=datetime.now(timezone.utc).isoformat(),
        formal_runs=100,
        visual_reviews=len(items),
        layout_rows=len(layout),
        prompt_rows=len(prompt),
        real_human_raters=0,
        rating_source="synthetic_proxy_three_profiles",
        five_automatic_metrics_unchanged=previous.exists(),
        display_row=display,
        subjective_metrics={
            k: full["metrics"][k] for k in ("layout_plausibility", "prompt_alignment")
        },
        provenance_sha256=digest(package / "SYNTHETIC_RATING_PROVENANCE.json"),
        summary_sha256=digest(results / "table2_full.json"),
        records_sha256=digest(results / "human_per_scene.jsonl"),
    )
    path = BASE / "results/gpt6_astra" / f"synthetic_rating_audit_{args.domain}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
