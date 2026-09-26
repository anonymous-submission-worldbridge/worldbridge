#!/usr/bin/env python3
"""Fill WorldGen rating packages with reproducible, non-human proxy ratings.

The output follows the frozen three-rater schema so that the existing strict
importer and ITT aggregation can be exercised.  These records are synthetic
proxy data and must never be represented as a human-subject experiment.
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
import shutil
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE_ROOT = BASELINES_ROOT / "annotations/worldgen"
RATERS = ("sim_rater_01", "sim_rater_02", "sim_rater_03")
LAYOUT_FIELDS = (
    "boundary_collision",
    "support_pose",
    "scale_density",
    "function_circulation",
)


# The first profile element contains clearly visible facts; the second contains
# borderline facts.  All remaining preregistered facts receive ``no``.  These
# templates were assigned after reviewing the 8-view contact sheets by prompt
# family.  Seed profiles below introduce a small, symmetric item-level variation.
INDOOR_PROMPT_RULES: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "indoor_bedroom_00": ((0, 3, 4, 5), (1,)),
    "indoor_bedroom_01": ((0, 1, 2, 6), (3,)),
    "indoor_bedroom_02": ((0, 1, 4, 5), (3,)),
    "indoor_bedroom_03": ((0, 2, 3, 5), (6,)),
    "indoor_bedroom_04": ((0, 2, 4, 5, 6), (3,)),
    "indoor_living_room_00": ((0, 1, 2, 4, 5), (6,)),
    "indoor_living_room_01": ((0, 2, 3, 5), (1,)),
    "indoor_living_room_02": ((0, 2, 3, 4, 5), (6,)),
    "indoor_living_room_03": ((0, 1, 2, 3, 4), (6,)),
    "indoor_living_room_04": ((0, 2, 3, 4, 5), (6,)),
    "indoor_kitchen_00": ((0, 1, 2, 3, 4, 6), (5,)),
    "indoor_kitchen_01": ((0, 1, 2, 3, 4), (6,)),
    "indoor_kitchen_02": ((0, 1, 2, 3, 4, 5), (6,)),
    "indoor_kitchen_03": ((0, 1, 2, 3, 4), (5,)),
    "indoor_kitchen_04": ((0, 1, 2, 3), (6,)),
    "indoor_bathroom_00": ((1, 2, 4, 5), (6,)),
    "indoor_bathroom_01": ((2, 3, 4, 5), (6,)),
    "indoor_bathroom_02": ((0, 2, 3, 5), (6,)),
    "indoor_bathroom_03": ((3, 4, 5, 6), (0,)),
    "indoor_bathroom_04": ((0, 1, 2, 5), (6,)),
    "indoor_dining_room_00": ((0, 1, 2, 4, 5), (3,)),
    "indoor_dining_room_01": ((0, 1, 2, 4), (5,)),
    "indoor_dining_room_02": ((0, 1, 3, 4, 5), (6,)),
    "indoor_dining_room_03": ((0, 1, 3, 5, 6), (2,)),
    "indoor_dining_room_04": ((0, 1, 2, 4), (5,)),
}

URBAN_PROMPT_RULES: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "urban_residential_four_way_00": ((2, 4, 6), (5,)),
    "urban_residential_t_junction_01": ((1, 2, 3, 6), (5,)),
    "urban_residential_main_side_02": ((1, 2, 6), (5,)),
    "urban_residential_offset_03": ((1, 2, 6), (4,)),
    "urban_residential_irregular_04": ((1, 2, 6), (4,)),
    "urban_commercial_four_way_05": ((1, 2, 4, 6), (5,)),
    "urban_commercial_t_junction_06": ((1, 3, 5, 6), (4,)),
    "urban_commercial_main_side_07": ((1, 2, 3, 6), (5,)),
    "urban_commercial_offset_08": ((1, 2, 4, 6), (3,)),
    "urban_commercial_irregular_09": ((1, 2, 4, 6), (5,)),
    "urban_mixed_use_four_way_10": ((1, 2, 4, 6), (3,)),
    "urban_mixed_use_t_junction_11": ((1, 3, 6), (4,)),
    "urban_mixed_use_main_side_12": ((1, 2, 6), (4,)),
    "urban_mixed_use_offset_13": ((1, 3, 6), (5,)),
    "urban_mixed_use_irregular_14": ((1, 2, 6), (4,)),
    "urban_park_edge_four_way_15": ((1, 2, 4, 6), (5,)),
    "urban_park_edge_t_junction_16": ((1, 2, 6), (5,)),
    "urban_park_edge_main_side_17": ((1, 2, 6), (5,)),
    "urban_park_edge_offset_18": ((1, 2, 6), (4,)),
    "urban_park_edge_irregular_19": ((1, 2, 6), (4,)),
    "urban_leisure_civic_four_way_20": ((2, 4, 6), (5,)),
    "urban_leisure_civic_t_junction_21": ((3, 5, 6), (2,)),
    "urban_leisure_civic_main_side_22": ((2, 3, 6), (5,)),
    "urban_leisure_civic_offset_23": ((2, 4, 6), (5,)),
    "urban_leisure_civic_irregular_24": ((2, 4, 6), (5,)),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]
) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def layout_neutral(domain: str, spec_id: str, seed: int) -> list[int]:
    if domain == "indoor":
        if "bedroom" in spec_id:
            values = [4, 4, 3, 4]
        elif "bathroom" in spec_id:
            values = [4, 4, 3, 3]
        else:
            values = [4, 4, 4, 4]
    elif "park_edge" in spec_id or "leisure_civic" in spec_id:
        values = [3, 4, 4, 3]
    else:
        values = [3, 3, 4, 3]

    # Contact-sheet review showed modest within-family variation.  Apply a
    # symmetric seed adjustment to density so complete four-seed specs retain
    # the reviewed family mean.
    values[2] += (0, 1, -1, 0)[seed]
    return values


def layout_for_profile(neutral: list[int], item_number: int, profile: int) -> list[int]:
    values = list(neutral)
    dimension = (item_number - 1) % len(values)
    if profile == 0 and values[dimension] > 1:
        values[dimension] -= 1
    elif profile == 2 and values[dimension] < 5:
        values[dimension] += 1
    return values


def prompt_for_seed(
    clear: tuple[int, ...], borderline: tuple[int, ...], seed: int
) -> tuple[set[int], set[int]]:
    yes = set(clear)
    ambiguous = set(borderline)
    if seed == 1:
        yes.update(ambiguous)
        ambiguous.clear()
    elif seed == 2:
        # Demoting one secondary clear fact balances the seed-1 promotion over
        # a complete four-seed spec while keeping the decision conservative.
        demoted = max(yes)
        yes.remove(demoted)
        ambiguous.add(demoted)
    return yes, ambiguous


def validate_templates(
    domain: str,
    items: list[dict[str, str]],
    private_by_id: dict[str, dict[str, Any]],
    rules: dict[str, tuple[tuple[int, ...], tuple[int, ...]]],
) -> None:
    observed_specs = {private_by_id[item["blind_id"]]["spec_id"] for item in items}
    if observed_specs != set(rules):
        raise RuntimeError(
            f"{domain}: prompt-rule coverage mismatch: "
            f"missing={sorted(observed_specs - set(rules))} "
            f"extra={sorted(set(rules) - observed_specs)}"
        )
    for item in items:
        spec_id = private_by_id[item["blind_id"]]["spec_id"]
        facts = json.loads(item["required_facts_json"])
        clear, borderline = rules[spec_id]
        valid = set(range(len(facts)))
        if set(clear) & set(borderline) or not (set(clear) | set(borderline)) <= valid:
            raise RuntimeError(f"{domain}/{spec_id}: invalid prompt-fact indices")


def fill_domain(domain: str) -> tuple[int, int, int]:
    package = PACKAGE_ROOT / domain
    items = read_csv(package / "items.csv")
    private = json.loads(
        (package / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    private_by_id = {row["blind_id"]: row for row in private}
    rules = INDOOR_PROMPT_RULES if domain == "indoor" else URBAN_PROMPT_RULES
    expected_items = 100 if domain == "indoor" else 98
    if len(items) != expected_items:
        raise RuntimeError(
            f"{domain}: expected {expected_items} successful items, got {len(items)}"
        )
    validate_templates(domain, items, private_by_id, rules)

    for name in ("layout_ratings.csv", "prompt_ratings.csv"):
        blank = package / name.replace(".csv", ".blank.csv")
        if not blank.exists():
            shutil.copy2(package / name, blank)

    layout_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    audit_decisions: list[dict[str, object]] = []
    for item_number, item in enumerate(items, start=1):
        mapping = private_by_id[item["blind_id"]]
        spec_id = str(mapping["spec_id"])
        seed = int(mapping["logical_seed"])
        facts = json.loads(item["required_facts_json"])
        neutral = layout_neutral(domain, spec_id, seed)
        yes, ambiguous = prompt_for_seed(*rules[spec_id], seed)
        audit_decisions.append(
            {
                "item_number": item_number,
                "blind_id": item["blind_id"],
                "spec_id": spec_id,
                "logical_seed": seed,
                "neutral_layout": neutral,
                "clear_yes_fact_indices": sorted(yes),
                "borderline_fact_indices": sorted(ambiguous),
            }
        )
        for profile, rater_id in enumerate(RATERS):
            layout_values = layout_for_profile(neutral, item_number, profile)
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
    provenance = {
        "rating_source": "synthetic_proxy_not_human_subject_data",
        "date": "2026-09-05",
        "method_scope": f"worldgen_{domain}",
        "rater_ids": list(RATERS),
        "evidence_reviewed": (
            "All successful items were visually reviewed in ten domain contact "
            "sheets, each item containing the frozen 8-view montage. The supplied "
            "50-frame videos remain in the package but were not treated as human observations."
        ),
        "decision_model": (
            "Prompt-family proxy templates from the visual review, with symmetric "
            "seed-level variation; exact item decisions are recorded below."
        ),
        "layout_profile_rule": (
            "sim_rater_02 uses the proxy neutral vector; sim_rater_01 and "
            "sim_rater_03 apply a deterministic symmetric -1/+1 perturbation to "
            "one rotating dimension when the 1..5 boundary permits."
        ),
        "prompt_profile_rule": (
            "All profiles agree on clear facts; borderline facts are respectively "
            "no, not-visible, and yes."
        ),
        "warning": (
            "Proxy values requested by the user. Do not describe or publish these "
            "records as ratings from three real independent human participants."
        ),
        "decisions": audit_decisions,
    }
    provenance_path = package / "SYNTHETIC_RATING_PROVENANCE.json"
    temporary = provenance_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(provenance_path)
    return len(items), len(layout_rows), len(prompt_rows)


def main() -> int:
    for domain in ("indoor", "urban"):
        items, layout_rows, prompt_rows = fill_domain(domain)
        print(
            f"SIMULATED_RATINGS_COMPLETE domain={domain} items={items} "
            f"layout_rows={layout_rows} prompt_rows={prompt_rows}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
