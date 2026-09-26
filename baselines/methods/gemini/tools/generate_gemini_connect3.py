#!/usr/bin/env python3
"""Generate compact multi-building connect3 districts through the Gemini account client."""
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


from pathlib import Path
import sys


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES / "tools"))
sys.path.insert(0, str((BASELINES / "methods")))
import baselines.methods.gemini.tools.generate_gemini_connect as generator  # noqa: E402
from baselines.methods.gemini.adapter_connect import check_code  # noqa: E402


generator.OUTPUT = BASELINES / "annotations/gemini_3_1_pro/connect3"
generator.SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect3_specs.json"
)
generator.PROMPT = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect3_prompt.txt"
)
generator.SCHEMA = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_output.schema.json"
)
generator.check_code = check_code
generator.RETRY_MIN_POLYGONS = 90_000
generator.RETRY_MIN_OBJECTS = 450
generator.MAX_ATTEMPTS = 6


if __name__ == "__main__":
    raise SystemExit(generator.main())
