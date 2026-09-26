#!/usr/bin/env python3
"""Fill MetaUrban's formal package with reproducible non-human proxy ratings.

The records intentionally conform to the frozen three-rater schema so the
strict importer and Table 2 aggregation can be exercised.  They are synthetic
proxy values requested by the user, not human-subject observations.
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
PACKAGE = BASELINES_ROOT / "annotations/metaurban/urban"
RATERS = ("sim_rater_01", "sim_rater_02", "sim_rater_03")
LAYOUT_FIELDS = (
    "boundary_collision",
    "support_pose",
    "scale_density",
    "function_circulation",
)


# (clearly visible fact indices, borderline fact indices).  Facts omitted from
# both groups receive ``no``.  The rules were set after inspecting one complete
# 8-view montage for every frozen spec.  They deliberately require visible
# evidence and do not infer a requested building's function from its facade.
PROMPT_RULES: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "urban_residential_four_way_00": ((0, 2, 4, 6), (3, 5)),
    "urban_residential_t_junction_01": ((0, 3, 4, 5, 6), (1,)),
    "urban_residential_main_side_02": ((0, 2, 3, 6), (4, 5)),
    "urban_residential_offset_03": ((2, 4, 6), (0, 1, 3, 5)),
    "urban_residential_irregular_04": ((2, 3, 4, 6), (0, 1, 5)),
    "urban_commercial_four_way_05": ((0, 2, 4, 6), (3, 5)),
    "urban_commercial_t_junction_06": ((0, 3, 4, 5, 6), (2,)),
    "urban_commercial_main_side_07": ((0, 3, 4, 5, 6), (1,)),
    "urban_commercial_offset_08": ((2, 3, 4, 6), (0, 5)),
    "urban_commercial_irregular_09": ((2, 3, 4, 6), (0, 5)),
    "urban_mixed_use_four_way_10": ((0, 2, 4, 6), (1, 3, 5)),
    "urban_mixed_use_t_junction_11": ((0, 3, 4, 5, 6), (1,)),
    "urban_mixed_use_main_side_12": ((0, 2, 3, 4, 6), (1, 5)),
    "urban_mixed_use_offset_13": ((3, 4, 5, 6), (0, 1, 2)),
    "urban_mixed_use_irregular_14": ((2, 3, 4, 6), (0, 5)),
    "urban_park_edge_four_way_15": ((0, 3, 5, 6), (1, 2, 4)),
    "urban_park_edge_t_junction_16": ((0, 1, 3, 4, 6), (5,)),
    "urban_park_edge_main_side_17": ((0, 1, 3, 4, 5, 6), (2,)),
    "urban_park_edge_offset_18": ((1, 3, 4, 5, 6), (0, 2)),
    "urban_park_edge_irregular_19": ((1, 3, 4, 5, 6), (0, 2)),
    "urban_leisure_civic_four_way_20": ((0, 3, 4, 5, 6), (2,)),
    "urban_leisure_civic_t_junction_21": ((0, 3, 4, 5, 6), ()),
    "urban_leisure_civic_main_side_22": ((0, 2, 3, 4, 5, 6), ()),
    "urban_leisure_civic_offset_23": ((2, 3, 4, 5, 6), (0,)),
    "urban_leisure_civic_irregular_24": ((2, 3, 4, 5, 6), (0,)),
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


def neutral_layout(spec_id: str, seed: int) -> list[int]:
    # The reviewed scenes are grounded and navigable, but often sparse and
    # contain occasional oversized vegetation/signage.  Compound TT/CX maps
    # also make circulation less immediately legible than X/T maps.
    values = [3, 4, 3, 4]
    if "_offset_" in spec_id or "_irregular_" in spec_id:
        values[3] = 3
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
    elif seed == 2 and yes:
        # A conservative, deterministic seed-level variation.  Across each
        # complete four-seed spec it avoids treating the reviewed seed as a
        # constant score for every generated layout.
        demoted = max(yes)
        yes.remove(demoted)
        ambiguous.add(demoted)
    return yes, ambiguous


def validate(
    items: list[dict[str, str]], private_by_id: dict[str, dict[str, Any]]
) -> None:
    if len(items) != 100 or len(private_by_id) != 100:
        raise RuntimeError(
            f"expected 100 formal items, got public={len(items)} private={len(private_by_id)}"
        )
    if not all(bool(row["success"]) for row in private_by_id.values()):
        raise RuntimeError(
            "the frozen MetaUrban package unexpectedly contains a failed item"
        )
    observed_specs = {private_by_id[item["blind_id"]]["spec_id"] for item in items}
    if observed_specs != set(PROMPT_RULES):
        raise RuntimeError(
            f"prompt-rule coverage mismatch: missing={sorted(observed_specs - set(PROMPT_RULES))} "
            f"extra={sorted(set(PROMPT_RULES) - observed_specs)}"
        )
    for item in items:
        spec_id = str(private_by_id[item["blind_id"]]["spec_id"])
        fact_count = int(item["fact_count"])
        clear, borderline = PROMPT_RULES[spec_id]
        valid = set(range(fact_count))
        if set(clear) & set(borderline) or not (set(clear) | set(borderline)) <= valid:
            raise RuntimeError(f"{spec_id}: invalid prompt-fact indices")


def main() -> int:
    items = read_csv(PACKAGE / "items.csv")
    private = json.loads(
        (PACKAGE / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    private_by_id = {row["blind_id"]: row for row in private}
    validate(items, private_by_id)

    for name in ("layout_ratings.csv", "prompt_ratings.csv"):
        blank = PACKAGE / name.replace(".csv", ".blank.csv")
        if not blank.exists():
            shutil.copy2(PACKAGE / name, blank)

    layout_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for item_number, item in enumerate(items, start=1):
        mapping = private_by_id[item["blind_id"]]
        spec_id = str(mapping["spec_id"])
        seed = int(mapping["logical_seed"])
        facts = json.loads(item["required_facts_json"])
        neutral = neutral_layout(spec_id, seed)
        yes, ambiguous = prompt_for_seed(*PROMPT_RULES[spec_id], seed)
        decisions.append(
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
            values = layout_for_profile(neutral, item_number, profile)
            layout_rows.append(
                {
                    "rater_id": rater_id,
                    "blind_id": item["blind_id"],
                    **dict(zip(LAYOUT_FIELDS, values)),
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
        "date": "2026-09-05",
        "method_scope": "metaurban_urban",
        "rater_ids": list(RATERS),
        "evidence_reviewed": (
            "The logical_seed=0 8-view montage for each of the 25 frozen specs "
            "was visually inspected. Remaining seeds use conservative, "
            "deterministic seed variation; all exact per-item decisions follow."
        ),
        "layout_decision_model": (
            "Grounding and circulation visible in the montages score positively; "
            "sparse density, occasional oversized assets, and less legible TT/CX "
            "compound layouts are penalized."
        ),
        "prompt_decision_model": (
            "Only visible facts count. Requested building functions are not inferred "
            "from generic facades. Clear facts are shared; borderline facts receive "
            "no/not-visible/yes from the three profiles."
        ),
        "warning": (
            "Proxy values explicitly requested by the user. Do not describe or "
            "publish these records as ratings from real independent human participants."
        ),
        "decisions": decisions,
    }
    provenance_path = PACKAGE / "SYNTHETIC_RATING_PROVENANCE.json"
    temporary = provenance_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(provenance_path)
    print(
        "SIMULATED_RATINGS_COMPLETE "
        f"items={len(items)} layout_rows={len(layout_rows)} prompt_rows={len(prompt_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
