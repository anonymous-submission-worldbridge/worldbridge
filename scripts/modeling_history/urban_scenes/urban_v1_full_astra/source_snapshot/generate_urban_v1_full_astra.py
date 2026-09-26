#!/usr/bin/env python3
"""Canonical Astra production entry: plan -> audit -> full indoor/outdoor geometry.

blender -b --factory-startup --python-exit-code 1 --python scripts/generate_urban_v1_full_astra.py
"""
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT, build_plan, save_plan
from astra_city.audit import layout_audit


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = build_plan()
    save_plan(plan)
    audit = layout_audit(plan)
    (OUT / "layout_audit.json").write_text(json.dumps(audit, indent=2))
    if audit["status"] != "PASS":
        raise RuntimeError("Layout failed: " + str(audit["errors"]))
    if not (OUT / "asset_library.blend").is_file():
        raise RuntimeError("Run scripts/astra_city/prepare_assets.py first")
    from astra_city.build import build

    build(plan)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "generation_failure.txt").write_text(traceback.format_exc())
        raise
