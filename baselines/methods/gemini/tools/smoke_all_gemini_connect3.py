#!/usr/bin/env python3
"""Run visual-audit renders for selected built connect3 scenes."""
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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import json
from pathlib import Path
import subprocess


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect3"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect3_specs.json"
)
SCRIPT = BASELINES / "methods/gemini/tools/smoke_render_gemini_connect3.py"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", default=[])
    args = parser.parse_args()
    rows = json.loads(SPECS.read_text(encoding="utf-8"))
    requested = set(args.scene)
    if requested:
        rows = [row for row in rows if row["demo_id"] in requested]
    failed = []
    for row in rows:
        demo_id = row["demo_id"]
        run = ROOT / demo_id
        blend = run / f"{demo_id}.blend"
        if not blend.is_file():
            failed.append(demo_id)
            continue
        log = run / "logs/visual_audit.log"
        command = [
            str(BLENDER),
            "-b",
            str(blend),
            "--python",
            str(SCRIPT),
            "--",
            "--run-dir",
            str(run),
        ]
        print(f"GEMINI_CONNECT3_SMOKE_START {demo_id}", flush=True)
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.run(
                command, stdout=output, stderr=subprocess.STDOUT, text=True
            )
        if process.returncode:
            failed.append(demo_id)
            print(f"GEMINI_CONNECT3_SMOKE_FAILED {demo_id}", flush=True)
        else:
            print(f"GEMINI_CONNECT3_SMOKE_DONE {demo_id}", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
