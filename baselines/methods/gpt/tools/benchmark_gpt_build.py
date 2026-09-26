"""Compare Blender CPU thread settings on identical, already-generated code."""

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
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_BLENDER_BIN = _wb_paths["BLENDER_BIN"]

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--domain", default="indoor", choices=["indoor", "urban"])
    p.add_argument("--spec-id", default="indoor_bedroom_00")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--threads", type=int, nargs="+", default=[1, 8])
    args = p.parse_args()
    source = (
        ROOT
        / "data/gpt6_astra_pilot"
        / args.domain
        / "gpt6_astra"
        / args.spec_id
        / f"seed_{args.seed}"
    )
    base = ROOT / "work/gpt6_astra/build_benchmark" / f"{args.spec_id}_seed_{args.seed}"
    results = []
    for threads in args.threads:
        run = base / f"threads_{threads}"
        run.mkdir(parents=True, exist_ok=False)
        (run / "input").mkdir()
        (run / "scene").mkdir()
        shutil.copy2(source / "input/spec.json", run / "input/spec.json")
        shutil.copy2(source / "scene/generated.py", run / "scene/generated.py")
        shutil.copy2(source / "run_manifest.json", run / "run_manifest.json")
        command = [
            "bwrap",
            "--die-with-parent",
            "--unshare-net",
            "--ro-bind",
            "/",
            "/",
            "--dev-bind",
            "/dev",
            "/dev",
            "--proc",
            "/proc",
            "--bind",
            str(run),
            str(run),
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home",
            "--chdir",
            str(run),
            f"{_wb_BLENDER_BIN}",
            "-b",
            "--factory-startup",
            "-t",
            str(threads),
            "--python-exit-code",
            "11",
            "--python",
            str((ROOT / "methods/gpt/tools/blender_render_gpt.py")),
            "--",
            "--run-dir",
            str(run),
            "--phase",
            "build",
        ]
        started = time.monotonic()
        print(f"BENCHMARK_START {args.spec_id} threads={threads}", flush=True)
        with (run / "build.log").open("w") as log:
            result = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=3600
            )
        record = {
            "threads": threads,
            "wall_time_s": time.monotonic() - started,
            "exit_code": result.returncode,
            "generated_code_sha256": hashlib.sha256(
                (run / "scene/generated.py").read_bytes()
            ).hexdigest(),
        }
        if (run / "scene/geometry.json").exists():
            record["geometry_sha256"] = hashlib.sha256(
                (run / "scene/geometry.json").read_bytes()
            ).hexdigest()
        results.append(record)
        (base / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
