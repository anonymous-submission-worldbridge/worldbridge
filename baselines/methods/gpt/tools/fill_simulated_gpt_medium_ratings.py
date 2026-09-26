#!/usr/bin/env python3
"""Medium-only visual proxy ratings; never real or independent human ratings."""
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
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    RATERS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    LAYOUT_FIELDS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    layout_for_profile,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    read_csv,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    write_csv,
)


BASE = _BASELINE_PROJECT_ROOT / "baselines"
PROFILE_SOURCE = (
    BASE / "methods/sceneweaver/tools/fill_simulated_sceneweaver_ratings.py"
)
EXPECTED_PROFILE_SHA = (
    "21e98ccf0db591564cf6022aff11d9c1511130990df28c103f14f029a6e326b4"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_review(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        number, layout, clear, borderline, note = line.split("|", 4)
        row = {
            "item_number": int(number),
            "neutral_layout": list(map(int, layout)),
            "clear_yes_fact_indices": list(map(int, clear)),
            "borderline_fact_indices": list(map(int, borderline)),
            "review_notes": note,
        }
        if row["item_number"] != len(rows) + 1:
            raise ValueError("Review order is incomplete or duplicated")
        if len(row["neutral_layout"]) != 4 or not all(
            1 <= value <= 5 for value in row["neutral_layout"]
        ):
            raise ValueError("Layout must have four integers in 1..5")
        clear_set = set(row["clear_yes_fact_indices"])
        borderline_set = set(row["borderline_fact_indices"])
        if (
            clear_set & borderline_set
            or len(clear_set) != len(row["clear_yes_fact_indices"])
            or len(borderline_set) != len(row["borderline_fact_indices"])
        ):
            raise ValueError("Fact decisions overlap or repeat")
        if not note.strip():
            raise ValueError("Every item requires a visual evidence note")
        rows.append(row)
    return rows


def verify_review_binding(review_path: Path, items_path: Path) -> None:
    sidecar = review_path.with_suffix(".items.sha256")
    if not sidecar.exists() or sidecar.read_text().strip() != digest(items_path):
        raise RuntimeError("Review is not hash-bound to the current items.csv")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--write", action="store_true", help="Otherwise validate only")
    args = parser.parse_args()

    package = BASE / "annotations/gpt6_astra_medium" / args.domain
    review_root = BASE / "work/gpt6_astra_medium/synthetic_review"
    review_path = review_root / f"{args.domain}_review.txt"
    items_path = package / "items.csv"
    if digest(PROFILE_SOURCE) != EXPECTED_PROFILE_SHA:
        raise RuntimeError(
            "Reference profile implementation changed; inspect before reuse"
        )
    verify_review_binding(review_path, items_path)

    lock = json.loads(
        (
            (BASE / "methods/gpt/protocol/generation/gpt6_astra_medium.lock.json")
        ).read_text()
    )
    if any(
        digest(BASE / path) != expected
        for path, expected in lock["files_sha256"].items()
    ):
        raise RuntimeError("A frozen Medium experimental source changed")

    items = read_csv(items_path)
    mapping = json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    if len(mapping) != 100 or any(
        item["method"] != "gpt6_astra_medium" or item["domain"] != args.domain
        for item in mapping
    ):
        raise RuntimeError("Expected the Medium-only formal 100-run domain")
    by_id = {item["blind_id"]: item for item in mapping}
    if len(by_id) != 100 or len(items) != sum(
        bool(item["success"]) for item in mapping
    ):
        raise RuntimeError("Stale or duplicated annotation mapping")

    reviews = parse_review(review_path)
    if len(reviews) != len(items) or len({item["blind_id"] for item in items}) != len(
        items
    ):
        raise RuntimeError("Each valid scene needs exactly one visual review")

    layout_rows, prompt_rows, decisions = [], [], []
    for item, review in zip(items, reviews):
        private = by_id[item["blind_id"]]
        if not private["success"]:
            raise RuntimeError("Non-successful scene in public items")
        facts = json.loads(item["required_facts_json"])
        clear = review["clear_yes_fact_indices"]
        borderline = review["borderline_fact_indices"]
        if int(item["fact_count"]) != len(facts) or not set(clear + borderline) <= set(
            range(len(facts))
        ):
            raise RuntimeError("Invalid fact indices or count")
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
                "review_sheet": str(sheet.relative_to(BASE)),
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
        "date": "2026-09-13",
        "method_scope": f"gpt6_astra_medium_{args.domain}",
        "human_raters": 0,
        "independent_human_ratings": False,
        "rater_ids": list(RATERS),
        "scored_scenes": len(items),
        "itt_zero_failure_scenes": 100 - len(items),
        "reviewer": "Codex assistant visual review",
        "authorization": "User requested the same configuration and experiment as GPT-6 Astra High on 2026-09-13.",
        "evidence_reviewed": f"All {len(items)} successful eight-view montages in four-item contact sheets. No continuous video review; no generated-code inference.",
        "reference_method": "Identical fixed profile function imported from the completed High/SceneWeaver workflow. No borrowed scene scores or target mean.",
        "layout_profile_rule": "Neutral vector for profile 02; profiles 01/03 apply -1/+1 to (item_number-1)%4 within 1..5.",
        "prompt_profile_rule": "Clear facts: all yes; borderline: no/not-visible/yes; remaining: all no. Unshown facts are not credited from code.",
        "limitations": "Synthetic subjective proxy, not a blind human study and not three independent model calls. Method identity known. Montage-only review can miss video-only evidence.",
        "scorer_sha256": digest(Path(__file__)),
        "profile_implementation_sha256": digest(PROFILE_SOURCE),
        "review_sha256": digest(review_path),
        "items_sha256": digest(items_path),
        "private_map_sha256": digest(package / "PRIVATE_blind_map.json"),
        "decisions": decisions,
    }
    if args.write:
        existing = package / "SYNTHETIC_RATING_PROVENANCE.json"
        if existing.exists():
            raise RuntimeError("Existing ratings require an explicit archived revision")
        for name, fields in (
            ("layout_ratings.csv", LAYOUT_FIELDS),
            ("prompt_ratings.csv", ("response",)),
        ):
            original = package / name
            if any(
                row[field].strip() for row in read_csv(original) for field in fields
            ):
                raise RuntimeError(f"Refusing overwrite of nonblank {name}")
            backup = package / name.replace(".csv", ".blank.csv")
            if backup.exists() and digest(backup) != digest(original):
                raise RuntimeError("Existing blank backup differs")
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
        temporary = existing.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(existing)

    print(
        json.dumps(
            {
                "status": "written" if args.write else "validated",
                "domain": args.domain,
                "scenes": len(items),
                "layout_rows": len(layout_rows),
                "prompt_rows": len(prompt_rows),
                "real_human_raters": 0,
                "frozen_sources_verified": len(lock["files_sha256"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
