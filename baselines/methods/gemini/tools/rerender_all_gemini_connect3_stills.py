#!/usr/bin/env python3
"""Refresh all connect3 stills on an idle GPU from the existing blend files."""
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

from baselines.methods.gemini.tools.render_all_gemini_connect3 import render_environment


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect3"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect3_specs.json"
)
SCRIPT = BASELINES / "methods/gemini/tools/rerender_gemini_connect3_stills.py"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", default=[])
    args = parser.parse_args()
    requested = set(args.scene)
    failed: list[str] = []
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    if requested:
        specs = [spec for spec in specs if spec["demo_id"] in requested]
    for spec in specs:
        demo_id = spec["demo_id"]
        run = ROOT / demo_id
        blend = run / f"{demo_id}.blend"
        environment, resource = render_environment()
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
        log = run / "logs/stills_refresh.log"
        print(
            f"GEMINI_CONNECT3_STILLS_REFRESH_START {demo_id} resource={resource}",
            flush=True,
        )
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
        if process.returncode:
            failed.append(demo_id)
            print(f"GEMINI_CONNECT3_STILLS_REFRESH_FAILED {demo_id}", flush=True)
        else:
            print(f"GEMINI_CONNECT3_STILLS_REFRESH_DONE {demo_id}", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
