"""Run a scoped pipeline step, saving verbose tool output instead of flooding the UI."""

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

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]
_wb_WORLDBRIDGE_MODELS = _wb_paths["WORLDBRIDGE_MODELS"]
_wb_WORLDBRIDGE_CACHE = _wb_paths["WORLDBRIDGE_CACHE"]
_wb_WORLDBRIDGE_PYTHON = _wb_paths["WORLDBRIDGE_PYTHON"]
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths["WORLDBRIDGE_SITE_PACKAGES"]
_wb_BLENDER_BIN = _wb_paths["BLENDER_BIN"]
_wb_BLENDER_RESOURCES = _wb_paths["BLENDER_RESOURCES"]

import argparse, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_astra"
parser = argparse.ArgumentParser()
parser.add_argument(
    "step",
    choices=[
        "build",
        "mesh_audit",
        "export_ue",
        "bake_materials",
        "render",
        "fbx_roundtrip",
    ],
)
parser.add_argument("--blender", default=f"{_wb_BLENDER_BIN}")
parser.add_argument("--gpu", default="0")
parser.add_argument("--views", default="")
parser.add_argument("--reuse-static", action="store_true")
args = parser.parse_args()
env = os.environ.copy()
env["CUDA_VISIBLE_DEVICES"] = args.gpu
if args.views:
    env["ASTRA_VIEWS"] = args.views
if args.reuse_static:
    env["ASTRA_REUSE_STATIC_EXPORTS"] = "1"
cmd = [args.blender, "-b", "-t", "8"]
if args.step == "build":
    cmd += [
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(ROOT / "scripts/generate_urban_v1_full_astra.py"),
    ]
else:
    cmd += [
        str(OUT / "urban_v1_full_astra.blend"),
        "--python-exit-code",
        "1",
        "--python",
        str(ROOT / f"scripts/astra_city/{args.step}.py"),
    ]
logs = OUT / "logs"
logs.mkdir(exist_ok=True)
log = logs / (args.step + "_" + time.strftime("%Y%m%d_%H%M%S") + ".log")
print("STEP_START", args.step, "log:", log, flush=True)
start = time.time()
with log.open("w") as stream:
    result = subprocess.run(
        cmd, cwd=str(ROOT), env=env, stdout=stream, stderr=subprocess.STDOUT
    )
summary = {
    "step": args.step,
    "exit_code": result.returncode,
    "seconds": time.time() - start,
    "log": str(log),
    "command": cmd,
}
(logs / (args.step + "_latest.json")).write_text(json.dumps(summary, indent=2))
print(json.dumps(summary), flush=True)
if result.returncode:
    with log.open() as f:
        from collections import deque

        print("".join(deque(f, maxlen=25)), flush=True)
sys.exit(result.returncode)
