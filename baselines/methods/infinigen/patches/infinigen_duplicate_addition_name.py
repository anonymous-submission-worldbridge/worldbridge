"""Runtime-only compatibility fix for Infinigen Indoors 1.19.1.

The upstream proposal generator samples twice in this expression::

    next(sample_name() for _ in range(100) if sample_name() not in curr.objs)

The name checked for uniqueness is therefore not the name yielded.  A rare
collision later raises ``AssertionError: target_name not in state.objs`` after
substantial generation work.  This patch keeps the vendored Infinigen source
read-only and only resamples when that specific collision occurs.
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


def apply_patch() -> None:
    import numpy as np

    from infinigen.core.constraints.example_solver.moves.addition import Addition

    if getattr(Addition.apply, "_table2_duplicate_name_fix", False):
        return

    original_apply = Addition.apply

    def collision_safe_apply(self, state):
        target_name = self.names[0]
        if target_name in state.objs:
            for _ in range(1000):
                candidate = f"{np.random.randint(1e6):04d}_{self.gen_class.__name__}"
                if candidate not in state.objs:
                    self.names[0] = candidate
                    break
            else:
                raise RuntimeError("Could not sample a unique Infinigen object name")
        return original_apply(self, state)

    collision_safe_apply._table2_duplicate_name_fix = True
    Addition.apply = collision_safe_apply
