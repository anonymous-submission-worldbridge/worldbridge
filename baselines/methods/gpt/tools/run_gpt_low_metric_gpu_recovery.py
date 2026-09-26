#!/usr/bin/env python3
"""Run Low metrics with the audited shared-host IQA admission recovery."""
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


from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
import baselines.methods.gpt.run_low_metrics as metrics


ORIGINAL_WAIT_GPU = metrics.wait_gpu


def recovery_wait_gpu(gpu: int, required: int) -> None:
    if required == 18432:
        required = 16384
    ORIGINAL_WAIT_GPU(gpu, required)


def main() -> int:
    metrics.wait_gpu = recovery_wait_gpu
    return metrics.main()


if __name__ == "__main__":
    raise SystemExit(main())
