#!/usr/bin/env python3
"""Atomically stamp inherited cache manifests with full-13 run provenance."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"


def atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def main() -> None:
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    run_id = layout["run_id"]
    path = CITY / "render_dependency_packs/render_pack_lineage.json"
    payload = json.loads(path.read_text(encoding="utf8"))
    payload["schema"] = "agent.full13.render_dependency_packs.v1"
    payload["run_id"] = run_id
    payload["scene_revision"] = "urban_v1_full_13"
    atomic(path, payload)


if __name__ == "__main__":
    main()
