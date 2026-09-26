#!/usr/bin/env python3
"""Compatibility entry point for the continuous SynCity 3000 demo builder.

The earlier implementation used image-space portal compositing and is no
longer valid for connected-scene visualization. Keep this filename as a
stable command-line entry point while routing all work to the shared-coordinate
3D implementation.
"""

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


from baselines.methods.syncity.tools.make_syncity_continuous_demo import main


if __name__ == "__main__":
    raise SystemExit(main())
