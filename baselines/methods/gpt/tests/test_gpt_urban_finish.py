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

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
from baselines.methods.gpt.tools.finish_gpt_urban import eligibility


@pytest.mark.parametrize(
    "manifest,cap,expected",
    [
        ({"render_success": True}, 3, "terminal"),
        ({"failure_class": "quality", "build_success": True}, 4, "terminal"),
        ({"build_attempts": [{"started_at_utc": "now"}]}, 3, "old_worker"),
        (
            {"build_success": True, "render_attempts": [{"started_at_utc": "now"}]},
            4,
            "old_worker",
        ),
        ({"generation_success": True}, 3, "build_pending"),
        ({"build_success": True}, 3, "ready"),
        (
            {"build_success": True, "render_attempts": [{"ended_at_utc": "done"}] * 3},
            3,
            "exhausted",
        ),
        (
            {"build_success": True, "render_attempts": [{"ended_at_utc": "done"}] * 3},
            4,
            "ready",
        ),
        (
            {"build_success": True, "render_attempts": [{"ended_at_utc": "done"}] * 4},
            4,
            "exhausted",
        ),
    ],
)
def test_terminal_and_budget_guards(manifest, cap, expected):
    assert eligibility(manifest, cap) == expected
