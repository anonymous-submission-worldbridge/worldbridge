#!/usr/bin/env python3
"""Reproduce visually reviewed SpatialGen proxies using the Infinigen profiles.

Synthetic judgments, not human-subject observations. No target mean, rescaling,
Qwen response reuse, or seed-based imputation is used. Decisions follow items.csv.
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


import hashlib
import json
from pathlib import Path

from baselines.methods.worldgen.tools.fill_simulated_worldgen_ratings import RATERS
from baselines.methods.worldgen.tools.fill_simulated_worldgen_ratings import (
    LAYOUT_FIELDS,
)
from baselines.methods.worldgen.tools.fill_simulated_worldgen_ratings import (
    layout_for_profile,
)
from baselines.methods.worldgen.tools.fill_simulated_worldgen_ratings import read_csv
from baselines.methods.worldgen.tools.fill_simulated_worldgen_ratings import write_csv

BASE = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE = BASE / "annotations/spatialgen/indoor"

# Each row: four neutral layout integers | clear fact indices | borderline indices.
# Four rows per spec, individually reviewed; no synthetic seed perturbation.
REVIEW = """
3343|0235|4
3333|0235|14
3343|0235|14
3343|0235|14
3343|01235|6
3343|01235|6
3343|01235|46
3343|01235|46
3343|0135|24
3343|01235|4
3343|01235|4
3343|01235|4
3343|01235|6
3343|012345|6
3343|012345|6
3343|012345|6
3343|01235|46
3343|01235|46
4344|0125|346
4344|01235|46
3343|0345|126
3343|0345|126
3343|0345|126
3343|0345|126
4344|01234|5
4344|0123|45
4344|0123|45
4344|01234|5
3343|012345|6
3343|01235|6
3343|01234|56
3343|01235|46
4344|1345|026
4344|1345|026
4344|145|026
4344|12345|06
3343|012345|6
3343|012345|6
3343|012345|6
3343|012345|6
4444|012356|4
4444|0123456|
4444|012356|4
4344|0123456|
4444|012456|3
4444|01256|34
4444|012456|3
4444|012456|3
3343|01235|46
3343|012345|6
3343|012345|6
3343|012345|6
3333|124|035
3333|12|0345
3333|1234|05
3333|1234|05
3343|01234|56
3343|01234|56
3343|01234|56
3343|01234|56
4344|012345|6
4344|012345|6
4344|01234|6
4344|012345|6
4344|012345|6
4344|012345|6
4344|012345|6
4344|012345|6
4343|0135|46
4343|013|456
4343|01345|6
4343|01345|6
4344|01345|26
4344|01345|26
4344|01345|26
4344|01345|26
4344|0125|346
4344|01245|36
4344|01245|36
4344|01245|36
3232|0134|25
3232|014|235
3232|0134|25
3232|0134|25
3232|0134|5
3232|01234|5
3232|0134|5
3232|134|05
3232|012345|6
3232|012345|6
3232|01345|26
3333|01345|26
3232|0245|136
3232|0125|346
3232|01245|36
3232|01245|36
3232|01234|5
3232|0123|45
3333|01234|5
3232|01234|5
"""

# Notes are specific to the four reviewed outputs, not assumptions about the
# native layout input. Fact presence can be yes in a clear early frame even if
# later views degrade; later missing supports affect layout, not object presence.
NOTES = [
    "One bed, wardrobe and adjacent window are visible. Item 1 has only one identifiable bedside table; other items have uncertain second-table evidence. Beds/tables lose surfaces or supports in later frames; the complete door-to-bed route is not established.",
    "Double bed, desk, desk chair, window and wardrobe are visible. A separate dresser is absent or not distinguishable from desk/wardrobe in items 7/8. Desk and bed supports turn into partial frames; full circulation around the bed is uncertain.",
    "Two single beds, an intervening small table and ceiling fixture are visible. Item 9 does not establish a wardrobe. Later bed surfaces/supports are incomplete; reachability from the entrance is less certain than the open central floor suggests.",
    "Single bed, bookcase, desk, chair and window are identifiable; a rug is visible in items 14–16 but not 13. Later desk/chair geometry is skeletal. Door is visible, but the full opening/clearance is not securely established.",
    "Bed, wardrobe/drawers and window are visible. Mirrors are clear except item 19; the requested bedside lamp is not securely distinguishable from other lighting. Items 17/18 show more disappearing bed geometry than 19/20; complete walking clearance is uncertain.",
    "Sofa, two extra seats, rug and window are visible. TV and table are present but the TV is to the side rather than clearly facing the sofa with the table between them. Extra seats become skeletal and clearance evidence is incomplete.",
    "Two sofas around a coffee table and a side table/floor lamp are visible. Bookcase is clear in 25/28, uncertain in 26/27. Main sofas/table remain more coherent than the peripheral furniture; full seating-group circulation is borderline.",
    "Sofa, two armchairs, coffee table and console are visible. Wall decoration is clear in 29/31; window is clear in 29/30/32 and uncertain in 31. Console/chair surfaces become incomplete. Entrance usability is not fully covered.",
    "Separate sofas form an approximate corner arrangement rather than a clearly continuous L-shaped seating unit. Table, plants and rug are visible. TV is clear in 36, borderline versus wall art/recess in 33–35. Bookcase is clear except 35. Window access is restricted or incompletely shown.",
    "Central sofa, paired armchairs, coffee table, lamp tables, rug and wall art are identifiable in early views. Armchairs and side tables lose seats/surfaces later; this weakens support and circulation judgments despite recognizable furnishing scale.",
    "Fridge, cooktop, sink, continuous counters, windows and clear aisle are visible. Upper storage in 41/43 is mainly a recess/shelf and is borderline as wall cabinets; enclosed cabinets are clear in 42/44. Cabinet/fixture geometry in 44 degrades more with viewpoint.",
    "L-shaped counters, sink below window, stove, task lights and open floor are visible. No unambiguous refrigerator: a low undercounter box alone is insufficient identification. Upper storage in 46 is open shelves rather than definite upper cabinets.",
    "Perimeter counters, island, sink, stove and cabinets are visible. Fridge is clear in 50–52 but not secure in 49. Island faces/supports disappear across views, making its functional clearance borderline even though a floor gap is visible.",
    "Only one counter side is well covered; the second side and central aisle are uncertain. Sink/stove are visible. Fridge is identifiable in 55/56, not in 53/54. Upper cabinetry is clear except 54. Close viewpoints and broken counter/hood geometry limit usability judgments.",
    "Sink, cooktop/oven, fridge, storage and breakfast table are visible. Chair counts/association are borderline: some are skeletal, additional seats appear, and 58 uses bench-like seating. Table/chair supports and safe circulation degrade across viewpoints.",
    "Toilet, vanity/sink, mirror, shower and towel storage are visible; window is absent in 63. Shower frame and toilet/vanity edges partly break up across views. Door swing is not established by the views; open floor alone is insufficient.",
    "Bathtub, toilet, vanity, mirror, shelves and ceiling light are identifiable in early video frames. Tub/toilet shapes become partial or block-like later. Overall scale is plausible but access to every fixture is borderline.",
    "Corner shower, toilet and mirror are visible. No identifiable pedestal sink is established in the reviewed views; a toilet below a mirror is not a sink. Towel hooks are clearer in 71/72; window is clear in 69/71/72, uncertain in 70. Missing sink and partial shower/toilet geometry weaken function.",
    "Bathtub, separate shower, double vanity with two taps/mirrors and storage are visible. Toilet is not securely identified, only partial low geometry. Tub/shower edges and supports deform in later frames; whole-room circulation is borderline.",
    "Shower, toilet, vanity/mirror and task light are visible. Separate hamper is not securely identified. Wall storage is clear in 78–80 but borderline in 77. Partial shower/fixture geometry prevents a confident full entrance-path judgment.",
    "Rectangular table, six early-view chairs and window are visible. Sideboard is clear except 82. Ceiling fixture exists but its centered position over the table is uncertain. Table/chair surfaces and supports largely vanish in later frames; every-chair clearance is not reliable.",
    "Four chairs, storage and wall decoration are visible. Round tabletop is clear in 85–87 but 88 looks squared/ambiguous. Pendant is clear in 86; 85/87/88 have ceiling-mounted lights, not definite pendants. Furniture becomes skeletal, weakening functional door-route evidence.",
    "Six-place table, six chairs, storage, ceiling fixture and windows are visible. Rug is clear in 89/90 but borderline in 91/92. Table and chair supports/surfaces degrade strongly; 92 retains more of its table than 89–91. Chair clearance is borderline.",
    "Long table, two ceiling lights, display shelves and wall art are visible (shelves less clear in 94). Eight-chair count is uncertain in 93 due to overlapping forms, clearer in 94–96. Separate sideboard is not securely distinguishable from shelving. Strong later furniture breakup undermines balanced walking space.",
    "Square table, four chairs, ceiling lamp and storage are visible. Plants beside a window are clear in 97/99/100; 98 has a plant but the window relation is uncertain. Table/chair surfaces vanish across views, least severely in 99. Complete entrance path remains borderline.",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    items = read_csv(PACKAGE / "items.csv")
    private = json.loads((PACKAGE / "PRIVATE_blind_map.json").read_text())["items"]
    mapping = {row["blind_id"]: row for row in private}
    reviews = [line.split("|") for line in REVIEW.strip().splitlines()]
    assert len(items) == len(reviews) == len(mapping) == 100
    assert all(row["method"] == "spatialgen" and row["success"] for row in private)
    decisions, layout_rows, prompt_rows = [], [], []
    for number, (item, review) in enumerate(zip(items, reviews), 1):
        neutral, clear, borderline = ([int(i) for i in part] for part in review)
        facts = json.loads(item["required_facts_json"])
        assert len(neutral) == 4 and all(1 <= x <= 5 for x in neutral)
        assert not set(clear) & set(borderline)
        assert set(clear + borderline) <= set(range(len(facts)))
        assert int(item["fact_count"]) == len(facts)
        row = mapping[item["blind_id"]]
        assert row["logical_seed"] == (number - 1) % 4
        if (number - 1) % 4:
            assert row["spec_id"] == decisions[-1]["spec_id"]
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
                "review_notes": NOTES[(number - 1) // 4],
                "montage_sha256": digest(PACKAGE / item["montage"]),
                "video_sha256": digest(PACKAGE / item["video"]),
                "review_sheet": f"review_20260907/review_{(number-1)//10+1:02d}.jpg",
                "video_sheet": f"review_20260907/video_{(number-1)//10+1:02d}.jpg",
            }
        )
        for profile, rater in enumerate(RATERS):
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": item["blind_id"],
                    **dict(
                        zip(LAYOUT_FIELDS, layout_for_profile(neutral, number, profile))
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
    assert len(layout_rows) == 300 and len(prompt_rows) == 2016
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
        "date": "2026-09-07",
        "method_scope": "spatialgen_indoor",
        "human_raters": 0,
        "independent_human_ratings": False,
        "rater_ids": list(RATERS),
        "scored_scenes": 100,
        "reviewer": "Codex assistant visual review in the user-requested correction session",
        "evidence_reviewed": "All 100 eight-view montages and five video frames per item (0,12,24,37,49), viewed as 10 montage sheets and 10 video sheets; not continuous playback of all 50 frames.",
        "reference_method": "Infinigen per-item visual decisions; identical three-profile rule also used by WorldGen/MetaUrban. No borrowed method-specific scores, target distribution, or synthetic seed adjustment.",
        "layout_profile_rule": "Neutral four integers; profiles 01/03 apply -1/+1 on (item_number-1)%4 within 1..5; profile 02 unchanged.",
        "prompt_profile_rule": "Clear facts: all yes; borderline: no/not-visible/yes; remaining: all no. Clear object presence in an early view is not revoked merely for later viewpoint degradation.",
        "limitations": "Subjective synthetic proxy, not independent human ratings or a validated correction to Qwen. Prior method identity and scores were known; this is not a blind study. Unseen geometry is not inferred; sampled video may miss evidence.",
        "scorer_sha256": digest(Path(__file__)),
        "profile_implementation_sha256": digest(
            (BASE / "methods/worldgen/tools/fill_simulated_worldgen_ratings.py")
        ),
        "items_sha256": digest(PACKAGE / "items.csv"),
        "outputs_sha256": {
            name: digest(PACKAGE / name)
            for name in ("layout_ratings.csv", "prompt_ratings.csv")
        },
        "decisions": decisions,
    }
    (PACKAGE / "SYNTHETIC_RATING_PROVENANCE.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
    )
    print("SIMULATED_RATINGS_COMPLETE items=100 layout_rows=300 prompt_rows=2016")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
