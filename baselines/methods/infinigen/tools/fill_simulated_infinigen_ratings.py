#!/usr/bin/env python3
"""Fill the Infinigen annotation package with reproducible proxy ratings.

These records are explicitly synthetic and are not human-subject data.  They
are useful only when a clearly labelled proxy is preferable to leaving the two
human-evaluation columns blank.
"""

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


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE = BASELINES_ROOT / "annotations/table2_infinigen_final_89"
RATERS = ("sim_rater_01", "sim_rater_02", "sim_rater_03")
LAYOUT_FIELDS = (
    "boundary_collision",
    "support_pose",
    "scale_density",
    "function_circulation",
)


# Entries follow items.csv order.  ``layout`` is the neutral 1--5 review;
# ``yes`` contains facts clearly satisfied in the montage/video composite;
# ``amb`` contains borderline facts on which the simulated profiles disagree.
DECISIONS = [
    ((4, 4, 3, 3), (4, 5), (2,)),
    ((4, 4, 4, 4), (0, 2, 3, 4, 5), (1,)),
    ((2, 4, 3, 2), (0, 2, 3, 4, 5), ()),
    ((3, 4, 3, 2), (0, 2, 4, 5), ()),
    ((4, 4, 4, 4), (0, 1, 2, 3, 4, 5, 6), ()),
    ((4, 4, 4, 4), (0, 1, 3, 4, 5, 6), ()),
    ((4, 4, 3, 3), (0, 4, 6), ()),
    ((4, 4, 3, 2), (2, 3, 5), ()),
    ((4, 4, 3, 2), (2, 3, 5), ()),
    ((4, 4, 4, 4), (0, 1, 4, 5, 6), (2,)),
    ((4, 4, 3, 3), (0, 2, 4, 5, 6), ()),
    ((4, 4, 4, 4), (0, 1, 4, 5, 6), ()),
    ((4, 4, 3, 3), (1, 2, 4, 5, 6), ()),
    ((4, 4, 3, 2), (5, 6), ()),
    ((4, 4, 3, 3), (0, 1, 2, 5, 6), ()),
    ((4, 4, 3, 3), (0, 2, 6), (1, 5)),
    ((3, 4, 3, 2), (0, 2, 4, 5, 6), ()),
    ((4, 4, 2, 1), (4, 5, 6), ()),
    ((2, 4, 3, 1), (0, 4, 5), ()),
    ((4, 4, 2, 1), (5, 6), ()),
    ((4, 4, 2, 1), (2, 5), ()),
    ((4, 4, 1, 1), (5,), ()),
    ((3, 4, 2, 1), (5,), ()),
    ((4, 4, 4, 4), (1, 3, 4, 5, 6), ()),
    ((4, 4, 2, 1), (3, 4, 5, 6), ()),
    ((4, 4, 2, 1), (3, 5, 6), ()),
    ((4, 4, 2, 1), (4, 6), ()),
    ((4, 4, 2, 1), (5, 6), ()),
    ((4, 4, 3, 2), (5, 6), ()),
    ((4, 4, 3, 2), (3, 6), ()),
    ((4, 4, 2, 2), (5, 6), ()),
    ((3, 4, 1, 1), (5,), ()),
    ((3, 4, 2, 2), (3, 5, 6), ()),
    ((4, 4, 3, 2), (3, 4, 6), ()),
    ((3, 3, 3, 3), (0, 1, 2, 3, 5, 6), ()),
    ((4, 4, 3, 4), (0, 1, 2, 3, 5, 6), ()),
    ((4, 4, 2, 1), (5, 6), ()),
    ((3, 4, 2, 1), (3, 6), ()),
    ((4, 4, 2, 1), (2, 5, 6), ()),
    ((4, 4, 2, 1), (2, 5, 6), ()),
    ((3, 3, 3, 3), (2, 4, 5, 6), (1, 3)),
    ((4, 4, 2, 1), (2, 6), (5,)),
    ((4, 4, 1, 1), (6,), ()),
    ((3, 4, 4, 4), (0, 1, 2, 4, 5, 6), (3,)),
    ((4, 4, 2, 1), (3, 5, 6), ()),
    ((4, 4, 2, 1), (2, 5), ()),
    ((3, 4, 4, 3), (1, 2, 4, 5), (0, 3)),
    ((4, 4, 1, 1), (5,), ()),
    ((4, 4, 1, 1), (5,), ()),
    ((3, 3, 3, 2), (1, 3, 4), (6,)),
    ((4, 4, 3, 3), (0, 3, 6), ()),
    ((4, 4, 1, 1), (1, 6), ()),
    ((3, 4, 3, 2), (0, 4, 6), (1, 3)),
    ((4, 4, 4, 4), (1, 2, 4, 5, 6), ()),
    ((3, 4, 3, 3), (0, 1, 4, 6), ()),
    ((4, 4, 3, 3), (0, 1, 2, 4, 6), ()),
    ((3, 4, 3, 3), (1, 4, 5, 6), (0,)),
    ((3, 4, 3, 3), (2, 3, 4, 5, 6), ()),
    ((4, 4, 2, 1), (4, 5, 6), (0,)),
    ((4, 4, 4, 4), (0, 2, 3, 4, 5, 6), ()),
    ((4, 4, 2, 1), (4, 5, 6), ()),
    ((4, 4, 3, 3), (1, 4, 5, 6), ()),
    ((4, 4, 3, 3), (3, 4, 5, 6), ()),
    ((3, 4, 4, 3), (1, 2, 5, 6), (3,)),
    ((4, 4, 3, 3), (5, 6), (0,)),
    ((4, 4, 2, 2), (0, 6), ()),
    ((4, 4, 3, 3), (5, 6), (1,)),
    ((4, 4, 3, 3), (0, 2, 5, 6), ()),
    ((3, 4, 3, 3), (1, 4, 6), ()),
    ((4, 4, 3, 3), (2, 5, 6), (0,)),
    ((4, 4, 4, 4), (1, 2, 4, 5, 6), ()),
    ((4, 4, 3, 3), (4, 5, 6), ()),
    ((4, 4, 4, 4), (0, 1, 3, 4, 5), ()),
    ((4, 4, 3, 3), (0, 3, 5), ()),
    ((3, 4, 3, 3), (0, 2, 3, 4), (1,)),
    ((4, 4, 3, 3), (3, 4, 5), (1,)),
    ((3, 4, 3, 2), (1, 3), ()),
    ((4, 4, 4, 4), (1, 3, 4, 5), ()),
    ((4, 4, 3, 3), (3, 5), ()),
    ((4, 4, 2, 1), (3, 4, 6), ()),
    ((4, 4, 3, 3), (0, 3, 4, 5, 6), ()),
    ((4, 4, 3, 2), (0, 3, 4, 6), ()),
    ((4, 4, 3, 3), (3, 4, 6), (0,)),
    ((3, 4, 3, 3), (0, 3, 4, 6), (1,)),
    ((4, 4, 3, 3), (2, 3, 4, 6), ()),
    ((4, 4, 3, 3), (0, 3, 4, 6), ()),
    ((4, 4, 4, 4), (0, 1, 2, 3, 5), (4,)),
    ((3, 4, 3, 3), (1, 2, 3), (4, 5)),
    ((3, 4, 3, 3), (1, 3, 5), ()),
]


def read_items() -> list[dict[str, str]]:
    with (PACKAGE / "items.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def layout_for_profile(
    neutral: tuple[int, int, int, int], item_number: int, profile: int
) -> list[int]:
    values = list(neutral)
    dimension = (item_number - 1) % len(values)
    if profile == 0 and values[dimension] > 1:
        values[dimension] -= 1
    elif profile == 2 and values[dimension] < 5:
        values[dimension] += 1
    return values


def write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]
) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    items = read_items()
    if len(items) != 89 or len(DECISIONS) != len(items):
        raise RuntimeError(
            f"expected 89 items/decisions, got {len(items)}/{len(DECISIONS)}"
        )

    layout_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    audit_decisions: list[dict[str, object]] = []
    for item_number, (item, decision) in enumerate(zip(items, DECISIONS), start=1):
        layout, yes_indices, ambiguous_indices = decision
        facts = json.loads(item["required_facts_json"])
        fact_indices = set(range(len(facts)))
        yes = set(yes_indices)
        ambiguous = set(ambiguous_indices)
        if yes & ambiguous or not (yes | ambiguous) <= fact_indices:
            raise RuntimeError(f"invalid fact decision for {item['blind_id']}")
        if int(item["fact_count"]) != len(facts):
            raise RuntimeError(f"fact_count mismatch for {item['blind_id']}")

        audit_decisions.append(
            {
                "item_number": item_number,
                "blind_id": item["blind_id"],
                "neutral_layout": list(layout),
                "clear_yes_fact_indices": sorted(yes),
                "borderline_fact_indices": sorted(ambiguous),
            }
        )
        for profile, rater_id in enumerate(RATERS):
            layout_values = layout_for_profile(layout, item_number, profile)
            layout_rows.append(
                {
                    "rater_id": rater_id,
                    "blind_id": item["blind_id"],
                    **dict(zip(LAYOUT_FIELDS, layout_values)),
                }
            )
            for fact_index, fact in enumerate(facts):
                if fact_index in yes:
                    response = "yes"
                elif fact_index in ambiguous:
                    response = ("no", "not-visible", "yes")[profile]
                else:
                    response = "no"
                prompt_rows.append(
                    {
                        "rater_id": rater_id,
                        "blind_id": item["blind_id"],
                        "fact_index": fact_index,
                        "fact": fact,
                        "response": response,
                    }
                )

    if len(layout_rows) != 267 or len(prompt_rows) != 1800:
        raise RuntimeError(
            f"unexpected task totals: layout={len(layout_rows)} prompt={len(prompt_rows)}"
        )
    write_csv(
        PACKAGE / "layout_ratings.csv",
        ("rater_id", "blind_id", *LAYOUT_FIELDS),
        layout_rows,
    )
    write_csv(
        PACKAGE / "prompt_ratings.csv",
        ("rater_id", "blind_id", "fact_index", "fact", "response"),
        prompt_rows,
    )
    provenance = {
        "rating_source": "synthetic_proxy_not_human_subject_data",
        "date": "2026-09-04",
        "method_scope": "infinigen_indoors",
        "rater_ids": list(RATERS),
        "evidence_per_item": "8-view montage plus 5 frames sampled from the 50-frame video",
        "layout_profile_rule": (
            "sim_rater_02 uses the reviewed neutral vector; sim_rater_01 and "
            "sim_rater_03 apply a deterministic symmetric -1/+1 perturbation to "
            "one rotating dimension when the 1..5 boundary permits"
        ),
        "prompt_profile_rule": (
            "all profiles agree on clear facts; borderline facts are respectively "
            "no, not-visible, and yes"
        ),
        "warning": (
            "Proxy values requested by the user. Do not describe or publish these "
            "records as ratings from three real independent human participants."
        ),
        "decisions": audit_decisions,
    }
    provenance_path = PACKAGE / "SYNTHETIC_RATING_PROVENANCE.json"
    temporary = provenance_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(provenance_path)
    print(
        f"SIMULATED_RATINGS_COMPLETE items={len(items)} "
        f"layout_rows={len(layout_rows)} prompt_rows={len(prompt_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
