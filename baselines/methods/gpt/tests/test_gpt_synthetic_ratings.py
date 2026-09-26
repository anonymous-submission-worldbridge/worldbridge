"""Resource-independent checks for the explicitly synthetic subjective proxy."""

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

import importlib.util
import itertools
from pathlib import Path
import sys

import pytest

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASE / "tools"))
import baselines.methods.gpt.tools.fill_simulated_gpt_ratings as scorer


def test_profiles_equal_completed_methods():
    for method in ("infinigen", "worldgen", "metaurban"):
        path = BASE / f"methods/{method}/tools/fill_simulated_{method}_ratings.py"
        spec = importlib.util.spec_from_file_location(f"reference_{method}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for values in itertools.product(range(1, 6), repeat=4):
            for number in range(1, 5):
                for profile in range(3):
                    assert scorer.layout_for_profile(
                        values, number, profile
                    ) == module.layout_for_profile(values, number, profile)


def test_complete_indoor_review():
    rows = scorer.parse_review(
        BASE / "work/gpt6_astra/synthetic_review/indoor_review.txt"
    )
    assert len(rows) == 91
    assert [row["item_number"] for row in rows] == list(range(1, 92))
    assert (
        scorer.digest(BASE / "annotations/gpt6_astra/indoor/items.csv")
        == scorer.REVIEWED_ITEMS["indoor"]
    )


@pytest.mark.parametrize(
    "line",
    [
        "2|4444|0||note",
        "1|444|0||note",
        "1|6404|0||note",
        "1|4444|0|0|note",
        "1|4444|00||note",
        "1|4444|0||",
    ],
)
def test_invalid_reviews_rejected(tmp_path, line):
    path = tmp_path / "review.txt"
    path.write_text(line)
    with pytest.raises(ValueError):
        scorer.parse_review(path)


def test_proxy_profiles_not_claimed_independent_humans():
    import json

    amendment = json.loads(
        (
            (
                BASE
                / "methods/gpt/protocol/generation/gpt6_astra_rating_amendment_20260909.json"
            )
        ).read_text()
    )
    assert amendment["real_human_raters"] == 0
    assert amendment["independent_human_ratings"] is False
    assert amendment["revised_rating_design"] == "synthetic_proxy_three_profiles"
