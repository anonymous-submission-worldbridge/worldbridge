"""Runtime-only fix for Concrete used as an Infinigen wall material.

In Infinigen Indoors 1.19.1, ``room_walls`` supplies tile-orientation
keywords to every sampled wall material.  ``Concrete.generate`` accepts no
keywords, so a valid random material choice can fail late in scene assembly.
The keywords below only control tiled/directional materials and have no
Concrete equivalent; ignoring them preserves the sampled Concrete material.
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


from collections.abc import Callable
from typing import Any


IGNORED_WALL_KWARGS = frozenset(
    {"alternating", "is_ceramic", "scale", "shape", "vertical"}
)


def patch_concrete_class(concrete_class: type) -> None:
    """Make a Concrete-like class ignore only known wall-style keywords."""

    if getattr(concrete_class.generate, "_table2_wall_kwargs_fix", False):
        return

    original_generate: Callable[..., Any] = concrete_class.generate

    def compatible_generate(self, *args, **kwargs):
        unsupported = set(kwargs) - IGNORED_WALL_KWARGS
        if unsupported:
            # Preserve the original TypeError for genuinely unknown inputs.
            return original_generate(self, *args, **kwargs)
        return original_generate(self, *args)

    compatible_generate._table2_wall_kwargs_fix = True
    concrete_class.generate = compatible_generate
    # Concrete aliases __call__ to the original function at class definition
    # time, so replacing generate alone is insufficient.
    concrete_class.__call__ = compatible_generate


def apply_patch() -> None:
    from infinigen.assets.materials.ceramic.concrete import Concrete

    patch_concrete_class(Concrete)
