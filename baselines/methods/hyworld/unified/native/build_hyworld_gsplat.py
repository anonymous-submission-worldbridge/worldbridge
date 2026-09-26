#!/usr/bin/env python3
"""Build HY-World's patched gsplat extension for this node's RTX A6000."""

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


import glob
import os
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
GSPLAT_ROOT = (
    BASELINES_ROOT
    / "sources/HY-World-2.0/hyworld2/worldgen/third_party/gsplat_maskgaussian/gsplat"
)
BUILD_DIR = BASELINES_ROOT / "hyworld2_runtime/cache/torch_extensions/gsplat_cuda_sm86"

# This must be set before torch.utils.cpp_extension is imported.
os.environ["CUDA_HOME"] = "/usr/local/cuda-12.4"
os.environ["TORCH_CUDA_ARCH_LIST"] = "8.6"
os.environ.setdefault("MAX_JOBS", "8")

from torch.utils.cpp_extension import load  # noqa: E402


def main() -> int:
    source_root = GSPLAT_ROOT / "cuda"
    sources = sorted(glob.glob(str(source_root / "csrc/*.cu")))
    sources += sorted(glob.glob(str(source_root / "csrc/*.cpp")))
    sources.append(str(source_root / "ext.cpp"))
    include_paths = [
        str(source_root / "include"),
        str(BASELINES_ROOT / "sources/glm-1.0.1"),
    ]
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    module = load(
        name="gsplat_cuda_sm86",
        sources=sources,
        extra_cflags=["-O3", "-Wno-attributes"],
        extra_cuda_cflags=[
            "-O3",
            "-use_fast_math",
            "--expt-relaxed-constexpr",
            "-diag-suppress",
            "20012,186",
        ],
        extra_include_paths=include_paths,
        build_directory=str(BUILD_DIR),
        verbose=True,
        with_cuda=True,
        keep_intermediates=True,
    )
    print(Path(module.__file__).resolve(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
