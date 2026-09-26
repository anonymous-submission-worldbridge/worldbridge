#!/usr/bin/env python3
"""Freeze Gemini 3.1 Pro after a complete, metric-valid Pilot."""
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


from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.gemini.adapter import digest
from baselines.methods.gemini.adapter import write_json
from baselines.methods.gemini.tools.audit_gemini import audit


def main() -> int:
    pilot_root = ROOT / "data/gemini_3_1_pro_pilot"
    report = audit(pilot_root, True, True)
    if not report["passed"] or report["expected"] != 20 or report["terminal"] != 20:
        raise RuntimeError("Refusing to freeze an incomplete or invalid Pilot")
    if report["success"] < 10:
        raise RuntimeError("Pilot has too few valid renders to freeze")
    files = [
        "methods/gemini/protocol/generation/gemini_3_1_pro.json",
        "methods/gemini/protocol/generation/gemini_3_1_pro_pilot_infrastructure_amendment_20260917.json",
        "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
        "methods/gpt/protocol/generation/gpt6_astra_output.schema.json",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "protocol/generation/seeds.json",
        "protocol/generation/metrics.lock.json",
        "methods/gemini/adapter.py",
        "methods/gemini/run.py",
        "methods/gemini/evaluate.py",
        "methods/gemini/tools/audit_gemini.py",
        "methods/gemini/tools/freeze_gemini.py",
        "methods/gpt/tools/blender_render_gpt.py",
        "methods/sceneweaver/tools/blender_render_sceneweaver.py",
        "methods/gpt/tools/gpt_camera.py",
        "methods/gpt/tools/make_annotation_package_gpt_high_frozen.py",
        "evaluation/visual/eval_iqa.py",
        "evaluation/visual/generate_semantics.py",
        "evaluation/visual/eval_worldscore_gpt_high_frozen.py",
        "evaluation/visual/eval_diversity.py",
        "evaluation/visual/import_human_ratings.py",
        "evaluation/visual/aggregate_generation.py",
    ]
    config = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    lock = {
        "status": "formal_frozen",
        "method": "gemini_3_1_pro",
        "model": "gemini-3.1-pro-high",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "transport": config["transport"],
        "auth_mode": config["auth_mode"],
        "api_key_billing_forbidden": True,
        "client_helper": config["client_helper"],
        "client_helper_sha256": config["client_helper_sha256"],
        "antigravity_version": config["antigravity_version"],
        "antigravity_binary_sha256": config["antigravity_binary_sha256"],
        "pilot_summary": {
            "expected": report["expected"],
            "terminal": report["terminal"],
            "success": report["success"],
            "quality_failure": report["quality_failure"],
            "per_domain": report["per_domain"],
        },
        "files_sha256": {relative: digest(ROOT / relative) for relative in files},
    }
    target = ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
    if target.exists():
        raise RuntimeError("Gemini formal lock already exists; refusing to overwrite")
    write_json(target, lock)
    print(
        json.dumps(
            {
                "lock": str(target),
                "sha256": digest(target),
                "pilot": lock["pilot_summary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
