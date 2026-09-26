"""Limit vLLM's startup-only NVML enumeration to CUDA-visible devices.

This is enabled only when CODEX_VLLM_NVML_VISIBLE_ONLY=1. CUDA itself is not
patched; the shim only prevents vLLM's diagnostic name logger from querying a
known-bad GPU outside CUDA_VISIBLE_DEVICES.
"""
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


import os


if os.environ.get("CODEX_VLLM_NVML_VISIBLE_ONLY") == "1":
    try:
        from vllm.third_party import pynvml

        _real_device_count = pynvml.nvmlDeviceGetCount

        def _visible_device_count():
            visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
            if visible and visible != "-1":
                return len([item for item in visible.split(",") if item.strip()])
            return _real_device_count()

        pynvml.nvmlDeviceGetCount = _visible_device_count
    except Exception:
        # Keep normal interpreter startup behavior; vLLM will report any
        # remaining platform problem with its own detailed traceback.
        pass
