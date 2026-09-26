#!/usr/bin/env python3
"""Build a HY-only CUDA PyTorch3D overlay from the already transferred source."""

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
import hashlib
import json
import os
import subprocess
import sys

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))
import baselines.methods.hyworld.run as matrix


def main():
    source = BASELINES / "sources/pytorch3d-worldgen"
    runtime = BASELINES / "hyworld2_runtime"
    build_lib = runtime / "tmp/pytorch3d_cuda_build/lib"
    build_temp = runtime / "tmp/pytorch3d_cuda_build/temp"
    environment = dict(os.environ)
    environment.update(matrix.HY.runtime_environment())
    environment.update(
        {
            "FORCE_CUDA": "1",
            "PYTORCH3D_FORCE_NO_CUDA": "0",
            "TORCH_CUDA_ARCH_LIST": "8.9",
            "MAX_JOBS": "8",
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONUNBUFFERED": "1",
            "CUB_HOME": str(Path(environment["CUDA_HOME"]) / "include"),
        }
    )
    command = [
        str(matrix.PYTHON),
        str(source / "setup.py"),
        "build_ext",
        "--build-temp",
        str(build_temp),
        "--build-lib",
        str(build_lib),
    ]
    log_path = runtime / "logs/pytorch3d_cuda_build_20260905.log"
    with log_path.open("a") as log:
        log.write(
            json.dumps({"command": command, "cuda_home": environment["CUDA_HOME"]})
            + "\n"
        )
        log.flush()
        completed = subprocess.run(
            command, cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
    if completed.returncode:
        print(f"PYTORCH3D_CUDA_BUILD_FAILED log={log_path}", flush=True)
        return completed.returncode
    built = list((build_lib / "pytorch3d").glob("_C*.so"))
    if len(built) != 1:
        raise RuntimeError("Expected one compiled PyTorch3D extension")
    overlay = runtime / "python/pytorch3d"
    overlay.mkdir(exist_ok=True)
    for path in (source / "pytorch3d").iterdir():
        if path.name.startswith("_C.") or path.name == "__pycache__":
            continue
        target = overlay / path.name
        if not target.exists():
            target.symlink_to(
                os.path.relpath(path, target.parent), target_is_directory=path.is_dir()
            )
    target = overlay / built[0].name
    if target.is_symlink():
        if target.resolve() != built[0].resolve():
            raise RuntimeError(f"Unexpected existing overlay: {target}")
    elif not target.exists():
        target.symlink_to(os.path.relpath(built[0], target.parent))
    else:
        raise RuntimeError(f"Refusing to replace existing library: {target}")
    report = {
        "source": str(source),
        "library": str(target),
        "sha256": hashlib.sha256(built[0].read_bytes()).hexdigest(),
        "cuda_home": environment["CUDA_HOME"],
        "architecture": "sm_89",
        "original_cpu_library_preserved": True,
        "downloads": 0,
    }
    matrix.atomic_json(BASELINES / "results/hyworld2/pytorch3d_cuda_build.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
