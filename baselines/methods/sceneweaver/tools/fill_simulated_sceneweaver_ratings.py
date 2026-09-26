#!/usr/bin/env python3
"""Write explicitly synthetic SceneWeaver ratings from a Codex montage review."""

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
import hashlib
import json
import shutil
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE = BASELINES / "annotations/sceneweaver/indoor"
RATERS = ("sim_rater_01", "sim_rater_02", "sim_rater_03")
LAYOUT_FIELDS = (
    "boundary_collision",
    "support_pose",
    "scale_density",
    "function_circulation",
)


# One visually reviewed row per successful item, in items.csv order:
# neutral four-dimensional layout | clearly satisfied facts | borderline facts.
# Remaining facts are scored no. Borderline facts use no/not-visible/yes across
# the three fixed simulated profiles.
REVIEW = """
3422|025|134
4433|025|14
3432|01245|6
4433|01245|6
4433|01245|6
3433|0125|4
4433|015|4
4434|0125|4
4433|0235|16
4432|03|16
4433|023|6
3432|01235|6
4433|012356|
4434|01346|2
3433|0134|26
3433|046|123
3423|346|02
4434|02346|1
3433|0345|12
3433|0245|13
3422|4|0135
4434|123456|0
4433|12345|6
4434|123456|0
4434|123456|0
4434|012346|5
3422|12|46
3423|026|1
4433|0256|
4423|026|
4433|0246|3
3423|146|2
4433|015|34
4434|0135|
4434|0135|4
4434|0135|
3423|0345|1
4434|01345|
3433|0135|6
4433|01|36
4434|01456|3
4434|013456|
3433|0134|6
4434|0135|4
4434|01345|
4434|01345|
4434|01345|
"""


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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layout_for_profile(neutral: list[int], item_number: int, profile: int) -> list[int]:
    values = list(neutral)
    dimension = (item_number - 1) % len(values)
    if profile == 0 and values[dimension] > 1:
        values[dimension] -= 1
    elif profile == 2 and values[dimension] < 5:
        values[dimension] += 1
    return values


def main() -> int:
    items = read_csv(PACKAGE / "items.csv")
    private = json.loads(
        (PACKAGE / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    mapping = {row["blind_id"]: row for row in private}
    reviews = [line.split("|") for line in REVIEW.strip().splitlines()]
    if len(private) != 100 or len(items) != 47 or len(reviews) != len(items):
        raise RuntimeError(
            f"Expected 100 slots, 47 successful items and 47 reviews; got "
            f"{len(private)}, {len(items)}, {len(reviews)}"
        )
    if any(row.get("method") != "sceneweaver" for row in private):
        raise RuntimeError("Annotation package contains a non-SceneWeaver slot")
    if sum(bool(row.get("success")) for row in private) != len(items):
        raise RuntimeError("Annotation package success count is stale")

    for name in ("layout_ratings.csv", "prompt_ratings.csv"):
        blank = PACKAGE / name.replace(".csv", ".blank.csv")
        if not blank.exists():
            shutil.copy2(PACKAGE / name, blank)

    layout_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for number, (item, review) in enumerate(zip(items, reviews), 1):
        neutral, clear, borderline = ([int(value) for value in part] for part in review)
        facts = json.loads(item["required_facts_json"])
        row = mapping[item["blind_id"]]
        if not row.get("success"):
            raise RuntimeError(
                f"Public item is not a successful slot: {item['blind_id']}"
            )
        if len(neutral) != 4 or not all(1 <= value <= 5 for value in neutral):
            raise RuntimeError(f"Invalid layout vector for item {number}")
        if set(clear) & set(borderline):
            raise RuntimeError(f"Overlapping fact decisions for item {number}")
        if not set(clear + borderline) <= set(range(len(facts))):
            raise RuntimeError(f"Out-of-range fact decision for item {number}")
        if int(item["fact_count"]) != len(facts):
            raise RuntimeError(f"Fact count mismatch for item {number}")

        decisions.append(
            {
                "item_number": number,
                "blind_id": item["blind_id"],
                "spec_id": row["spec_id"],
                "logical_seed": row["logical_seed"],
                "neutral_layout": neutral,
                "clear_yes_fact_indices": clear,
                "borderline_fact_indices": borderline,
                "no_fact_indices": sorted(
                    set(range(len(facts))) - set(clear + borderline)
                ),
                "montage_sha256": digest(PACKAGE / item["montage"]),
            }
        )
        for profile, rater in enumerate(RATERS):
            values = layout_for_profile(neutral, number, profile)
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": item["blind_id"],
                    **dict(zip(LAYOUT_FIELDS, values)),
                }
            )
            for fact_index, fact in enumerate(facts):
                if fact_index in clear:
                    response = "yes"
                elif fact_index in borderline:
                    response = ("no", "not-visible", "yes")[profile]
                else:
                    response = "no"
                prompt_rows.append(
                    {
                        "rater_id": rater,
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
        "import_rating_source": "synthetic_proxy_three_profiles",
        "date": "2026-09-08",
        "method_scope": "sceneweaver_indoor_mixed_minimax_codex_planner",
        "human_raters": 0,
        "independent_human_ratings": False,
        "rater_ids": list(RATERS),
        "scored_scenes": len(items),
        "itt_zero_failure_scenes": 100 - len(items),
        "reviewer": "Codex assistant visual review requested during experiment completion",
        "evidence_reviewed": (
            "All 47 successful frozen eight-view montages, grouped into five "
            "contact sheets. The 50-frame sequences were not continuously viewed."
        ),
        "layout_profile_rule": (
            "The reviewed neutral four-integer vector is used by sim_rater_02; "
            "profiles 01/03 apply a deterministic symmetric -1/+1 perturbation "
            "to one rotating dimension when the 1..5 boundary permits."
        ),
        "prompt_profile_rule": (
            "Clear facts are yes for all profiles; borderline facts are "
            "no/not-visible/yes; remaining facts are no."
        ),
        "limitations": (
            "Synthetic subjective proxy, not three humans and not a blind human "
            "study. Method identity and overall experiment status were known. "
            "Unseen geometry is not inferred, and montage-only review can miss "
            "evidence present only between sequence frames."
        ),
        "scorer_sha256": digest(Path(__file__)),
        "items_sha256": digest(PACKAGE / "items.csv"),
        "private_map_sha256": digest(PACKAGE / "PRIVATE_blind_map.json"),
        "outputs_sha256": {
            name: digest(PACKAGE / name)
            for name in ("layout_ratings.csv", "prompt_ratings.csv")
        },
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
        f"SIMULATED_SCENEWEAVER_RATINGS_COMPLETE items={len(items)} "
        f"layout_rows={len(layout_rows)} prompt_rows={len(prompt_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
