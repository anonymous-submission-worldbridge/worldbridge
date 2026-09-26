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


import json

import pytest

from baselines.methods.gpt.unified.low.recover_schema import recover_one


def reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_first_repair_relabels_only_same_response_evidence():
    original = reply(
        json.dumps({"functional_aqs": 3, "visual_aqs": 4, "spatial_aqs": 3})
    )
    repair = reply(
        '{"functional_aqs": 3, "visual_aqs": 4, "spatial_aqs": 3, '
        '"functional_evidence": "inside", "visual_evidence": "wood", '
        '"spatial_aqs": "wrong layout"}'
    )
    canonical, frozen = recover_one([original] * 3, [repair] * 3)
    assert frozen == {"functional_aqs": 3, "visual_aqs": 4, "spatial_aqs": 3}
    assert (
        json.loads(canonical["choices"][0]["message"]["content"])["spatial_evidence"]
        == "wrong layout"
    )
    assert (
        canonical["choices"][0]["message"]["content"]
        != repair["choices"][0]["message"]["content"]
    )


def test_recovery_refuses_score_drift_or_missing_same_reply_evidence():
    original = reply('{"functional_aqs":3,"visual_aqs":4,"spatial_aqs":3}')
    bad_score = reply('{"functional_aqs":4,"visual_aqs":4,"spatial_aqs":3}')
    with pytest.raises(ValueError, match="changed frozen numeric scores"):
        recover_one([original] * 3, [bad_score] * 3)
    with pytest.raises(ValueError, match="recovery incomplete"):
        recover_one([original] * 3, [original] * 3)
