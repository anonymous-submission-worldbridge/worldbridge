#!/usr/bin/env python3
"""Write Astra Low visual proxy ratings after a hash-bound montage review."""
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
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    RATERS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    LAYOUT_FIELDS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    layout_for_profile,
)

METHOD = "gpt6_astra_low"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def parse_review(path):
    reviews = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        number, layout, clear, borderline, note = line.split("|", 4)
        review = {
            "item_number": int(number),
            "neutral_layout": [int(value) for value in layout],
            "clear_yes_fact_indices": [int(value) for value in clear],
            "borderline_fact_indices": [int(value) for value in borderline],
            "review_notes": note,
        }
        if review["item_number"] != len(reviews) + 1:
            raise ValueError("Review order is incomplete or duplicated")
        if len(review["neutral_layout"]) != 4 or not all(
            1 <= value <= 5 for value in review["neutral_layout"]
        ):
            raise ValueError("Layout must contain four integers in 1..5")
        clear_set, borderline_set = set(review["clear_yes_fact_indices"]), set(
            review["borderline_fact_indices"]
        )
        if (
            clear_set & borderline_set
            or len(clear_set) != len(review["clear_yes_fact_indices"])
            or len(borderline_set) != len(review["borderline_fact_indices"])
        ):
            raise ValueError("Fact decisions overlap or repeat")
        if not note.strip():
            raise ValueError("Every item requires a visible-evidence note")
        reviews.append(review)
    return reviews


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    package = ROOT / "annotations/gpt6_astra_low" / args.domain
    review_root = ROOT / "work/gpt6_astra_low/synthetic_review"
    review_path = review_root / f"{args.domain}_review.txt"
    review_lock_path = review_root / f"{args.domain}_review.lock.json"
    review_lock = json.loads(review_lock_path.read_text())
    if digest(package / "items.csv") != review_lock.get("items_sha256"):
        raise RuntimeError("Annotation items changed after visual review")
    if digest(review_path) != review_lock.get("review_sha256"):
        raise RuntimeError("Visual review changed after its lock was recorded")
    items = read_csv(package / "items.csv")
    mapping = json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    if len(mapping) != 100 or any(
        row["method"] != METHOD or row["domain"] != args.domain for row in mapping
    ):
        raise RuntimeError("Expected one Astra Low formal 100-run domain")
    by_id = {row["blind_id"]: row for row in mapping}
    if len(by_id) != 100 or len(items) != sum(bool(row["success"]) for row in mapping):
        raise RuntimeError("Stale or duplicated annotation mapping")
    reviews = parse_review(review_path)
    if len(reviews) != len(items):
        raise RuntimeError("Each successful scene needs one complete visual review")
    layout_rows, prompt_rows, decisions = [], [], []
    for item, review in zip(items, reviews):
        private = by_id[item["blind_id"]]
        facts = json.loads(item["required_facts_json"])
        clear = review["clear_yes_fact_indices"]
        borderline = review["borderline_fact_indices"]
        if int(item["fact_count"]) != len(facts) or not set(clear + borderline) <= set(
            range(len(facts))
        ):
            raise RuntimeError("Invalid fact indices for " + item["blind_id"])
        sheet = (
            review_root
            / args.domain
            / f"review_{(review['item_number'] - 1) // 4 + 1:02d}.jpg"
        )
        decisions.append(
            {
                **review,
                "blind_id": item["blind_id"],
                "spec_id": private["spec_id"],
                "logical_seed": private["logical_seed"],
                "facts": facts,
                "no_fact_indices": sorted(
                    set(range(len(facts))) - set(clear + borderline)
                ),
                "montage_sha256": digest(package / item["montage"]),
                "review_sheet": str(sheet.relative_to(ROOT)),
                "review_sheet_sha256": digest(sheet),
            }
        )
        for profile, rater in enumerate(RATERS):
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": item["blind_id"],
                    **dict(
                        zip(
                            LAYOUT_FIELDS,
                            layout_for_profile(
                                review["neutral_layout"], review["item_number"], profile
                            ),
                        )
                    ),
                }
            )
            for index, fact in enumerate(facts):
                response = (
                    "yes"
                    if index in clear
                    else (
                        ("no", "not-visible", "yes")[profile]
                        if index in borderline
                        else "no"
                    )
                )
                prompt_rows.append(
                    {
                        "rater_id": rater,
                        "blind_id": item["blind_id"],
                        "fact_index": index,
                        "fact": fact,
                        "response": response,
                    }
                )
    provenance = {
        "rating_source": "synthetic_proxy_not_human_subject_data",
        "import_rating_source": "synthetic_proxy_three_profiles",
        "date": "2026-09-12",
        "method_scope": f"{METHOD}_{args.domain}",
        "human_raters": 0,
        "independent_human_ratings": False,
        "rater_ids": list(RATERS),
        "scored_scenes": len(items),
        "itt_zero_failure_scenes": 100 - len(items),
        "reviewer": "Codex assistant visual review",
        "authorization": "User requested the same configuration and experiment as the completed Astra High baseline.",
        "protocol": "methods/gpt/protocol/generation/gpt6_astra_low_rating_protocol.json",
        "evidence_reviewed": f"All {len(items)} successful eight-view montages in four-item contact sheets; no generated-code inference.",
        "limitations": "Synthetic subjective proxy, not a human study or three independent model calls; montage-only review can miss video-only evidence.",
        "scorer_sha256": digest(__file__),
        "review_sha256": digest(review_path),
        "review_lock_sha256": digest(review_lock_path),
        "items_sha256": digest(package / "items.csv"),
        "private_map_sha256": digest(package / "PRIVATE_blind_map.json"),
        "decisions": decisions,
    }
    if args.write:
        output = package / "SYNTHETIC_RATING_PROVENANCE.json"
        if output.exists():
            raise RuntimeError("Existing ratings require an archived revision")
        for name, fields in (
            ("layout_ratings.csv", LAYOUT_FIELDS),
            ("prompt_ratings.csv", ("response",)),
        ):
            original = package / name
            if any(
                row[field].strip() for row in read_csv(original) for field in fields
            ):
                raise RuntimeError("Refusing to overwrite nonblank " + name)
            backup = package / name.replace(".csv", ".blank.csv")
            if not backup.exists():
                shutil.copy2(original, backup)
        write_csv(
            package / "layout_ratings.csv",
            ("rater_id", "blind_id", *LAYOUT_FIELDS),
            layout_rows,
        )
        write_csv(
            package / "prompt_ratings.csv",
            ("rater_id", "blind_id", "fact_index", "fact", "response"),
            prompt_rows,
        )
        provenance["outputs_sha256"] = {
            name: digest(package / name)
            for name in ("layout_ratings.csv", "prompt_ratings.csv")
        }
        provenance["written_at_utc"] = datetime.now(timezone.utc).isoformat()
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(output)
    print(
        json.dumps(
            {
                "status": "written" if args.write else "validated",
                "domain": args.domain,
                "scenes": len(items),
                "layout_rows": len(layout_rows),
                "prompt_rows": len(prompt_rows),
                "real_human_raters": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
