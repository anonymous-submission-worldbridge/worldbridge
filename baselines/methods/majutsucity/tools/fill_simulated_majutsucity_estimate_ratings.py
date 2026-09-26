#!/usr/bin/env python3
"""Write explicitly synthetic, n=6 MajutsuCity deadline-estimate ratings.

These rows are a montage-based forecast requested after the formal generation
was stopped.  They are not human-subject data and are not a replacement for
the preregistered 100-run Table-2 study.
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
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    LAYOUT_FIELDS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    RATERS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    layout_for_profile,
)


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE = BASELINES / "annotations/majutsucity/urban"

# blind_id -> (neutral layout vector, clear yes facts, borderline facts, note)
# Remaining facts are no.  Borderline responses are no/not-visible/yes across
# the three deterministic profiles.
REVIEWS = {
    "U-6CA9157B0A5D": (
        [3, 4, 2, 2],
        [4],
        [2, 6],
        "Trees and lamps are visible, but the four-way residential layout, four crosswalks, and parked cars are not established.",
    ),
    "U-C4FE7A69B935": (
        [4, 4, 3, 4],
        [0, 2, 3, 4, 6],
        [],
        "The intersection, sidewalks/markings, lamps, trees, and open lanes are visible; low-rise homes on every corner and parked cars are absent.",
    ),
    "U-C4DF5AFF04CF": (
        [3, 3, 2, 1],
        [4],
        [],
        "The views are dominated by water and vegetation and do not visibly satisfy the requested residential intersection.",
    ),
    "U-05D897A7EFC2": (
        [4, 4, 3, 2],
        [4],
        [2],
        "Some houses, trees, lamps, and paved space are visible, but the requested four-way road structure and parked cars are not.",
    ),
    "U-2120B6DAEDAE": (
        [3, 3, 2, 2],
        [5],
        [3],
        "Lamps and roadside trees are visible; the T-junction, crosswalk, yards/fences, and detached-house organization are not established.",
    ),
    "U-42A5DD677778": (
        [4, 4, 4, 4],
        [0, 2, 3, 5, 6],
        [1],
        "A clear four-way road scene with buildings, crossings, lamps, trees, and open lanes is visible; the park corner is weak and paths/benches are absent.",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    items = read_csv(PACKAGE / "items.csv")
    private = json.loads(
        (PACKAGE / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    if len(private) != 100 or len(items) != 6:
        raise RuntimeError(
            f"Expected 100 slots and 6 successful items; got {len(private)}, {len(items)}"
        )
    if {row["blind_id"] for row in items} != set(REVIEWS):
        raise RuntimeError("Reviewed blind IDs do not match the current n=6 package")
    private_by_id = {row["blind_id"]: row for row in private}

    for name in ("layout_ratings.csv", "prompt_ratings.csv"):
        source = PACKAGE / name
        backup = PACKAGE / name.replace(".csv", ".blank.csv")
        if not backup.exists():
            shutil.copy2(source, backup)

    layout_rows: list[dict] = []
    prompt_rows: list[dict] = []
    decisions: list[dict] = []
    for item_number, item in enumerate(items, 1):
        blind_id = item["blind_id"]
        neutral, clear, borderline, note = REVIEWS[blind_id]
        facts = json.loads(item["required_facts_json"])
        if set(clear) & set(borderline) or not set(clear + borderline) <= set(
            range(len(facts))
        ):
            raise RuntimeError(f"Invalid fact decisions for {blind_id}")
        decisions.append(
            {
                "blind_id": blind_id,
                "spec_id": private_by_id[blind_id]["spec_id"],
                "logical_seed": private_by_id[blind_id]["logical_seed"],
                "neutral_layout": neutral,
                "clear_yes_fact_indices": clear,
                "borderline_fact_indices": borderline,
                "review_note": note,
                "montage_sha256": digest(PACKAGE / item["montage"]),
            }
        )
        for profile, rater in enumerate(RATERS):
            values = layout_for_profile(neutral, item_number, profile)
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": blind_id,
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
                        "blind_id": blind_id,
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
        "status": "deadline_estimate_not_formal_result",
        "rating_source": "synthetic_proxy_three_profiles_estimate_n6",
        "human_raters": 0,
        "independent_human_ratings": False,
        "scored_scenes": 6,
        "formal_slots": 100,
        "evidence_reviewed": "Six successful eight-view montages; videos were packaged but not continuously watched.",
        "limitations": "Five of six scenes come from two residential specs; diversity has only one four-seed spec. Severe selection and coverage bias.",
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
    }
    (PACKAGE / "ESTIMATE_RATING_PROVENANCE.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps({"layout_rows": len(layout_rows), "prompt_rows": len(prompt_rows)})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
