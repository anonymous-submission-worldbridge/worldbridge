#!/usr/bin/env python3
"""Render all successfully generated Gemini 3.1 Pro connected demos."""
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
from pathlib import Path
import subprocess
import sys


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = BASELINES / "annotations/gemini_3_1_pro/connect"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_specs.json"
)
RENDERER = BASELINES / "methods/gemini/tools/render_gemini_connect.py"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))


def main() -> int:
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--stills-only", action="store_true")
    args = parser.parse_args()
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    requested = set(args.scene)
    if requested:
        specs = [spec for spec in specs if spec["demo_id"] in requested]
    failures = []
    for spec in specs:
        demo_id = spec["demo_id"]
        run = OUTPUT / demo_id
        command = [
            str(BLENDER),
            "--factory-startup",
            "-b",
            "--python",
            str(RENDERER),
            "--",
            "--run-dir",
            str(run),
        ]
        if args.build_only:
            command.append("--build-only")
        if args.stills_only:
            command.append("--stills-only")
        log = run / "logs/render.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        print(f"GEMINI_CONNECT_RENDER_START {demo_id}", flush=True)
        with log.open("a", encoding="utf-8") as output:
            process = subprocess.run(
                command, stdout=output, stderr=subprocess.STDOUT, text=True
            )
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        state_ok = (
            bool(manifest.get("build_success"))
            if args.build_only
            else bool(manifest.get("stills_success"))
            if args.stills_only
            else bool(manifest.get("render_success"))
        )
        if process.returncode or not state_ok:
            failures.append(demo_id)
            print(
                f"GEMINI_CONNECT_RENDER_FAILED {demo_id}; see {log}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(f"GEMINI_CONNECT_RENDER_DONE {demo_id}", flush=True)
    if failures:
        print("Failed renders: " + ", ".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
