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


import pytest

from baselines.methods.infinigen.patches.infinigen_concrete_wall_kwargs import (
    patch_concrete_class,
)


def test_concrete_patch_ignores_only_registered_wall_kwargs() -> None:
    class Concrete:
        def generate(self):
            return "material"

        __call__ = generate

    patch_concrete_class(Concrete)

    concrete = Concrete()
    assert concrete(vertical=True, alternating=False, shape="square") == "material"
    assert concrete(scale=1.25, is_ceramic=True) == "material"
    with pytest.raises(TypeError):
        concrete(unregistered_option=True)


def test_concrete_patch_is_idempotent() -> None:
    class Concrete:
        def generate(self):
            return "material"

        __call__ = generate

    patch_concrete_class(Concrete)
    patched_generate = Concrete.generate
    patch_concrete_class(Concrete)

    assert Concrete.generate is patched_generate
    assert Concrete()(vertical=True) == "material"
